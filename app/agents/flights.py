import json

import anthropic
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.usage import UsageLimits

from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..flight_search import collect_flight_candidates, resolve_airport
from ..schemas import FlightsOutput, IntakeOutput

MODEL_REQUEST_LIMIT = 3
MODEL_CANDIDATE_LIMIT = 10

SYSTEM_PROMPT = """You are a flight ranking agent. Your job is to select the 3–5 best-value flight
options from a precomputed candidate list.

Instructions:
- Use only the provided candidate flights. Do not invent, alter, or infer options beyond the supplied list.
- Select the 3–5 most compelling options: prioritise best value (price vs. stops vs. duration).
- Include at least 1 non-stop or 1-stop economy option and 1 business/premium option if available.
- Never invent flight data.
- Populate cheapest_price_usd with the lowest price among the final options you return.
- Write a concise search_summary (e.g. "8 candidates reviewed; cheapest non-stop economy $320 on Turkish Airlines").
- The search_summary may mention the wider candidate set, but any explicit prices you call out should match
  the options you returned.
- Return a structured FlightsOutput.
"""


def _build_prompt(
    intake: IntakeOutput,
    *,
    origin_code: str,
    destination_code: str,
    candidates: list[dict[str, object]],
    search_metadata: dict[str, object],
) -> str:
    return (
        f"Rank the provided round-trip flight candidates for a trip from {origin_code} to {destination_code} "
        f"for travel dates {intake.check_in} to {intake.check_out} and {intake.guests} adult(s).\n\n"
        f"Original user request:\n"
        f"- origin input: {intake.origin_airport}\n"
        f"- destination input: {intake.destination}\n"
        f"- trip type: {intake.trip_type}\n"
        f"- time preferences: {intake.time_preferences}\n\n"
        f"Search metadata:\n{json.dumps(search_metadata, indent=2)}\n\n"
        f"Candidate flights:\n{json.dumps(candidates, indent=2)}"
    )


async def run_flights(intake: IntakeOutput) -> FlightsOutput:
    if intake.origin_airport is None:
        return FlightsOutput(
            options=[],
            cheapest_price_usd=None,
            search_summary="Flight search skipped because no origin airport was provided.",
        )

    origin = await resolve_airport(intake.origin_airport)
    if origin is None:
        return FlightsOutput(
            options=[],
            cheapest_price_usd=None,
            search_summary=f"Could not confidently resolve an origin airport from '{intake.origin_airport}'.",
        )

    destination = await resolve_airport(intake.destination)
    if destination is None:
        return FlightsOutput(
            options=[],
            cheapest_price_usd=None,
            search_summary=f"Could not confidently resolve a destination airport for '{intake.destination}'.",
        )

    candidates, search_metadata = await collect_flight_candidates(
        origin=origin.iata_code,
        destination=destination.iata_code,
        departure_date=intake.check_in,
        return_date=intake.check_out,
        adults=intake.guests,
    )

    if not candidates:
        return FlightsOutput(
            options=[],
            cheapest_price_usd=None,
            search_summary=(
                f"No useful round-trip flight options were found from {origin.iata_code} "
                f"to {destination.iata_code} for {intake.check_in} to {intake.check_out}."
            ),
        )

    model_candidates = candidates[:MODEL_CANDIDATE_LIMIT]
    prompt = _build_prompt(
        intake,
        origin_code=origin.iata_code,
        destination_code=destination.iata_code,
        candidates=model_candidates,
        search_metadata={
            **search_metadata,
            "origin_resolution": origin.source,
            "destination_resolution": destination.source,
            "candidate_count": len(candidates),
            "model_candidate_count": len(model_candidates),
        },
    )

    model = AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(
            anthropic_client=anthropic.AsyncAnthropic(
                base_url=MINIMAX_BASE_URL,
                api_key=get_minimax_api_key(),
            )
        ),
    )
    agent = Agent(
        model,
        output_type=FlightsOutput,
        system_prompt=SYSTEM_PROMPT,
        max_concurrency=1,
    )
    async with agent:
        result = await agent.run(
            prompt,
            usage_limits=UsageLimits(request_limit=MODEL_REQUEST_LIMIT),
        )

    output = result.output
    if output.options:
        output.cheapest_price_usd = min(option.price_usd for option in output.options)
    elif not output.search_summary:
        output.search_summary = (
            f"Reviewed {len(model_candidates)} precomputed candidates but did not select final options."
        )
    return output
