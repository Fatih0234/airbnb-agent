from pydantic_ai import Agent
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..mcp_client import create_google_maps_mcp_server
from ..schemas import CommuteOption, CommuteOutput, IntakeOutput

SYSTEM_PROMPT = """You are a commute research agent. Your job is to find transit options
and travel times between a stay area and the user's target destinations.

Instructions:
- For each target destination provided, use maps_directions with mode "transit" to get
  step-by-step public transit directions and travel time.
- Also check maps_directions with mode "walking" for short distances.
- Use maps_distance_matrix to compare multiple origins/destinations efficiently if needed.
- Use maps_static_map to generate an overview map showing the destinations, and return its URL.
- Summarize each route clearly: which transit lines, how many stops, total time.
- If no target destinations are provided, return an empty CommuteOutput.
- Return a structured CommuteOutput.
"""


def _build_prompt(intake: IntakeOutput) -> str:
    if not intake.target_destinations:
        return f"No commute destinations specified for trip to {intake.destination}."
    destinations = ", ".join(intake.target_destinations)
    return (
        f"Find public transit commute times in {intake.destination} "
        f"to these destinations: {destinations}. "
        f"Dates: {intake.check_in} to {intake.check_out}."
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
    return result.output
