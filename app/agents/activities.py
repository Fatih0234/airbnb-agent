from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..search_agent import run_search_backed_agent
from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..mcp_client import create_tavily_mcp_server
from ..schemas import ActivitiesOutput, IntakeOutput

SEARCH_REQUEST_LIMIT = 5

SYSTEM_PROMPT = """You are an activities research agent. Your job is to find activities
that closely match how the user wants to spend their time.

Instructions:
- Read the user's time_preferences carefully — these are the primary filter for what to find.
- Make at most 2 tavily-search calls total for discovery.
- Use tavily-search first to find strong candidates.
- Prefer writing from strong search snippets and source metadata instead of calling tavily-extract.
- Use tavily-extract on at most 1 high-value URL only if the best candidates still cannot be described
  accurately from the search results alone.
- After those calls, immediately compile and return the results — do not search further.
- For each activity, include `source_url` whenever possible.
- Prefer the venue's official page as `source_url`; if that is not discoverable, use the best evidence page
  you actually found in search results.
- Never invent a `source_url` or `image_url`.
- Leave `image_url` null unless a trustworthy image URL is directly present in the tool results.
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
        toolsets=[create_tavily_mcp_server()],
        output_type=ActivitiesOutput,
        system_prompt=SYSTEM_PROMPT,
        max_concurrency=1,
    )
    async with agent:
        result = await run_search_backed_agent(
            agent,
            _build_prompt(intake),
            usage_limits=UsageLimits(request_limit=SEARCH_REQUEST_LIMIT),
        )
    return result.output
