import json

import anthropic
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.usage import UsageLimits

from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..neighborhood_search import collect_neighborhood_evidence
from ..schemas import IntakeOutput, NeighborhoodOutput

MODEL_REQUEST_LIMIT = 3

SYSTEM_PROMPT = """You are a neighborhood synthesis agent. Your job is to turn precomputed
search evidence into an honest, well-scoped neighborhood summary.

Instructions:
- Use only the provided evidence payload. Do not search, infer hidden facts, or invent unsupported claims.
- Be balanced and practical: honest about caveats without sounding alarmist.
- If the evidence is weak for a field, leave that field empty rather than guessing.
- `vibe` may synthesize neighborhood character only when it is supported by the evidence.
- Keep `notable_notes` concise and limit them to practical, non-redundant points.
- Return a structured NeighborhoodOutput.
"""


def _empty_neighborhood_output() -> NeighborhoodOutput:
    return NeighborhoodOutput(
        safety_summary="",
        vibe="",
        walkability="",
        notable_notes=[],
    )


def _build_prompt(
    intake: IntakeOutput,
    *,
    evidence_payload: dict[str, object],
) -> str:
    return (
        f"Synthesize a neighborhood summary for {intake.destination}.\n\n"
        f"Trip context:\n"
        f"- trip type: {intake.trip_type}\n"
        f"- dates: {intake.check_in} to {intake.check_out}\n"
        f"- guests: {intake.guests}\n"
        f"- time preferences: {intake.time_preferences}\n\n"
        f"Precomputed evidence payload:\n{json.dumps(evidence_payload, indent=2)}"
    )


async def run_neighborhood(intake: IntakeOutput) -> NeighborhoodOutput:
    evidence_payload = await collect_neighborhood_evidence(
        destination=intake.destination,
        trip_type=intake.trip_type,
    )
    if not evidence_payload["evidence_count"]:
        return _empty_neighborhood_output()

    model = AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    agent = Agent(
        model,
        output_type=NeighborhoodOutput,
        system_prompt=SYSTEM_PROMPT,
        max_concurrency=1,
    )
    async with agent:
        result = await agent.run(
            _build_prompt(
                intake,
                evidence_payload=evidence_payload,
            ),
            usage_limits=UsageLimits(request_limit=MODEL_REQUEST_LIMIT),
        )
    return result.output
