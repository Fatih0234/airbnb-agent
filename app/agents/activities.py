from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..mcp_client import create_brave_mcp_server
from ..schemas import ActivitiesOutput, IntakeOutput

SYSTEM_PROMPT = """You are an activities research agent. Your job is to find activities
that closely match how the user wants to spend their time.

Instructions:
- Read the user's time_preferences carefully — these are the primary filter for what to find.
- Call brave_local_search 2–3 times with targeted queries based on the user's preferences.
  Do not use any other search tools.
- After your searches, immediately compile and return the results — do not search further.
- Set image_url to null for all activities.
- Curate a focused list (6–10 activities) matched to the user's preferences, not a generic top-10.
- Categorize each activity (outdoor, cultural, nightlife, sports, food, sightseeing, etc.).
- Return a structured ActivitiesOutput.
"""


def _build_prompt(intake: IntakeOutput) -> str:
    return (
        f"Find activities in {intake.destination} matched to these preferences: "
        f'"{intake.time_preferences}". '
        f"Trip type: {intake.trip_type}. "
        f"Dates: {intake.check_in} to {intake.check_out}, {intake.guests} guest(s)."
    )


async def run_activities(intake: IntakeOutput) -> ActivitiesOutput:
    model = AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    agent = Agent(
        model,
        toolsets=[create_brave_mcp_server()],
        output_type=ActivitiesOutput,
        system_prompt=SYSTEM_PROMPT,
    )
    async with agent:
        result = await agent.run(_build_prompt(intake), usage_limits=UsageLimits(request_limit=8))
    return result.output
