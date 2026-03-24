import logging
import re
import unicodedata

from pydantic_ai import Agent
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..mcp_client import create_google_maps_mcp_server
from ..schemas import CommuteOption, CommuteOutput, IntakeOutput

log = logging.getLogger("commute")

SYSTEM_PROMPT = """You are a commute research agent. Your job is to find transit options
and travel times between a stay area and the user's target destinations.

Instructions:
- Use one consistent origin near a central, stay-friendly area of the destination city.
- For each target destination provided, use maps_directions with mode "transit" to get
  step-by-step public transit directions and travel time.
- Check maps_directions with mode "walking" only if the destination is genuinely close enough to walk.
- Use maps_distance_matrix to compare multiple origins/destinations efficiently if needed.
- Use maps_static_map to generate an overview map showing the destinations, and return its URL.
- Summarize each route clearly: which transit lines, how many stops, total time.
- Return exactly one best commute option per target destination provided.
- Preserve each input destination string verbatim in the `destination` field.
- Never split a single destination into multiple shorter destinations even if it contains commas.
- If no target destinations are provided, return an empty CommuteOutput.
- Return a structured CommuteOutput.
"""


def _build_prompt(intake: IntakeOutput) -> str:
    if not intake.target_destinations:
        return f"No commute destinations specified for trip to {intake.destination}."
    destinations = "\n".join(
        f"{index}. {destination}"
        for index, destination in enumerate(intake.target_destinations, start=1)
    )
    return (
        f"Find the best commute option from a central stay area in {intake.destination}.\n"
        f"Dates: {intake.check_in} to {intake.check_out}.\n"
        "Use this exact destination list and keep each destination string unchanged in the output:\n"
        f"{destinations}"
    )


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_only.lower()).strip()


def _significant_tokens(value: str) -> set[str]:
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "near",
        "street",
        "st",
        "road",
        "rd",
        "avenue",
        "ave",
        "av",
        "carrer",
        "calle",
        "de",
        "del",
        "la",
        "el",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize_text(value))
        if (len(token) >= 3 or token.isdigit()) and token not in stopwords
    }


def _match_target(option: CommuteOption, targets: list[str]) -> tuple[str | None, float]:
    option_text = _normalize_text(option.destination)
    option_tokens = _significant_tokens(option.destination)
    best_target: str | None = None
    best_score = 0.0

    for target in targets:
        target_text = _normalize_text(target)
        target_tokens = _significant_tokens(target)
        if not target_tokens:
            continue

        if option_text == target_text:
            return target, 1.0

        overlap = len(option_tokens & target_tokens)
        if overlap == 0:
            continue

        coverage = overlap / len(target_tokens)
        bonus = 0.2 if option_text in target_text or target_text in option_text else 0.0
        score = min(0.99, coverage + bonus)
        if score > best_score:
            best_target = target
            best_score = score

    return best_target, best_score


def _normalize_commute_output(output: CommuteOutput, intake: IntakeOutput) -> CommuteOutput:
    if not intake.target_destinations or not output.options:
        return output

    best_by_target: dict[str, tuple[float, CommuteOption]] = {}
    dropped = 0
    for option in output.options:
        target, score = _match_target(option, intake.target_destinations)
        if target is None or score < 0.5:
            dropped += 1
            continue

        normalized_option = option.model_copy(update={"destination": target})
        existing = best_by_target.get(target)
        candidate = (score, normalized_option)
        if existing is None:
            best_by_target[target] = candidate
            continue

        existing_score, existing_option = existing
        if score > existing_score or (
            score == existing_score and normalized_option.duration_minutes < existing_option.duration_minutes
        ):
            best_by_target[target] = candidate

    ordered: list[CommuteOption] = []
    for target in intake.target_destinations:
        match = best_by_target.get(target)
        if match is not None:
            ordered.append(match[1])

    if dropped or len(output.options) != len(ordered):
        log.warning(
            "Normalized commute options from %d raw rows to %d validated rows for %s",
            len(output.options),
            len(ordered),
            intake.destination,
        )

    return CommuteOutput(
        options=ordered,
        map_url=output.map_url if ordered else None,
    )


async def run_commute(intake: IntakeOutput) -> CommuteOutput:
    if not intake.target_destinations:
        return CommuteOutput(options=[], map_url=None)

    model = AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    agent = Agent(
        model,
        toolsets=[create_google_maps_mcp_server()],
        output_type=CommuteOutput,
        system_prompt=SYSTEM_PROMPT,
    )
    async with agent:
        result = await agent.run(_build_prompt(intake))
    return _normalize_commute_output(result.output, intake)
