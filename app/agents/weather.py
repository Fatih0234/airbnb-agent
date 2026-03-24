from pydantic_ai import Agent
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..mcp_client import create_openweather_mcp_server
from ..schemas import IntakeOutput, WeatherOutput

SYSTEM_PROMPT = """You are a weather research agent. Your job is to provide an accurate
weather summary for the traveler's destination and dates.

Instructions:
- Use the weather tool to get current conditions and forecast for the destination city.
- Summarize the expected weather during the travel dates (temperature range, conditions).
- Provide practical packing tips based on the forecast (3–5 specific tips).
- Note any weather patterns relevant to the trip type (e.g. rain gear for outdoor activities,
  formal attire considerations for business trips).
- Return a structured WeatherOutput.
"""


def _build_prompt(intake: IntakeOutput) -> str:
    return (
        f"Get the weather forecast for {intake.destination} "
        f"for travel dates {intake.check_in} to {intake.check_out}. "
        f"Trip type: {intake.trip_type}."
    )


async def run_weather(intake: IntakeOutput) -> WeatherOutput:
    model = AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    agent = Agent(
        model,
        toolsets=[create_openweather_mcp_server()],
        output_type=WeatherOutput,
        system_prompt=SYSTEM_PROMPT,
    )
    async with agent:
        result = await agent.run(_build_prompt(intake))
    return result.output
