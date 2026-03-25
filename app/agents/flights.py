from pydantic_ai import Agent, FunctionToolset
from pydantic_ai.usage import UsageLimits
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..search_agent import run_search_backed_agent
from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..flight_search import (
    search_airports,
    search_round_trip_flights,
    search_round_trip_flights_flexible,
)
from ..mcp_client import create_tavily_mcp_server
from ..schemas import FlightsOutput, IntakeOutput

SEARCH_REQUEST_LIMIT = 4

SYSTEM_PROMPT = """You are a flight research agent. Your job is to find 3–5 best-value flight
options for the user's trip.

Instructions:
- Call search_airports for the origin and destination first.
- If search_airports returns a plausible exact or near-exact airport match, use that result and skip Tavily.
- Only if search_airports does not produce a confident code should you use tavily-search to look up the main
  IATA airport code for that city (for example, search "Istanbul main airport IATA code").
- After a Tavily lookup, use search_airports once to confirm the airport name or code.
- Use tavily-search only for airport-code lookups. Do not use tavily-extract.
- Do not use more than 2 Tavily searches total for airport-code lookups, and use at most 1 Tavily search
  per unresolved endpoint.
- Once you have IATA codes, call search_round_trip_flights for economy.
- Also call search_round_trip_flights for business if it is likely to exist.
- If the exact-date search returns no useful options, call search_round_trip_flights_flexible
  once with flexibility_days=2.
- Select the 3–5 most compelling options: prioritise best value (price vs. stops vs. duration).
  Include at least 1 non-stop or 1-stop economy option and 1 business/premium option if available.
- Never invent flight data. Only report what the tool returns.
- Do not call more than 4 flight-search tools total, and do not loop or repeat airport searches once
  you have a plausible IATA code.
- Populate cheapest_price_usd with the lowest price among the final options you return.
- Write a concise search_summary (e.g. "6 options found; cheapest non-stop economy $320 on Turkish Airlines").
- The search_summary may mention the wider search set, but any explicit prices you call out should match
  the options you returned.
- Return a structured FlightsOutput.
"""


def _build_prompt(intake: IntakeOutput) -> str:
    return (
        f"Find round-trip flights from '{intake.origin_airport}' to '{intake.destination}' "
        f"departing {intake.check_in}, returning {intake.check_out}, "
        f"for {intake.guests} adult(s). Seat class: economy (also check business if available)."
    )


async def run_flights(intake: IntakeOutput) -> FlightsOutput:
    model = AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    flight_toolset = FunctionToolset(
        [
            search_airports,
            search_round_trip_flights,
            search_round_trip_flights_flexible,
        ]
    )
    agent = Agent(
        model,
        toolsets=[create_tavily_mcp_server(), flight_toolset],
        output_type=FlightsOutput,
        system_prompt=SYSTEM_PROMPT,
        max_concurrency=1,
    )
    async with agent:
        result = await run_search_backed_agent(
            agent,
            _build_prompt(intake),
            usage_limits=UsageLimits(request_limit=SEARCH_REQUEST_LIMIT),
        )
    output = result.output
    if output.options:
        output.cheapest_price_usd = min(option.price_usd for option in output.options)
    return output
