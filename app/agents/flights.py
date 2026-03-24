from pydantic_ai import Agent
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..mcp_client import create_brave_mcp_server, create_google_flights_mcp_server
from ..schemas import FlightsOutput, IntakeOutput

SYSTEM_PROMPT = """You are a flight research agent. Your job is to find 3–5 best-value flight
options for the user's trip.

Instructions:
- The user may have provided a city name or IATA code as their origin. If it looks like a city
  name (not a 3-letter IATA code), use brave_web_search to look up the main IATA airport code
  for that city first (e.g. search "Istanbul main airport IATA code").
- Similarly, if the destination looks like a city name, look up its primary IATA airport code.
- Once you have IATA codes, call get_round_trip_flights with the origin, destination, check-in
  date (outbound), check-out date (return), and guest count as adults.
- If get_round_trip_flights returns no results, try find_all_flights_in_range with a ±2 day
  window around the travel dates.
- Select the 3–5 most compelling options: prioritise best value (price vs. stops vs. duration).
  Include at least 1 non-stop or 1-stop economy option and 1 business/premium option if available.
- Never invent flight data. Only report what the tool returns.
- Populate cheapest_price_usd with the lowest price among options.
- Write a concise search_summary (e.g. "6 options found; cheapest non-stop economy $320 on Turkish Airlines").
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
    agent = Agent(
        model,
        toolsets=[create_brave_mcp_server(), create_google_flights_mcp_server()],
        output_type=FlightsOutput,
        system_prompt=SYSTEM_PROMPT,
    )
    async with agent:
        result = await agent.run(_build_prompt(intake))
    return result.output
