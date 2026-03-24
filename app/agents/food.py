from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..search_agent import run_search_backed_agent
from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..mcp_client import create_tavily_mcp_server
from ..schemas import FoodOutput, IntakeOutput

SYSTEM_PROMPT = """You are a food research agent. Your job is to find the best restaurants,
cafes, and food experiences for the traveler.

Instructions:
- Make at most 2 tavily-search calls total for discovery.
- Use tavily-search first to find strong candidates.
- Use tavily-extract on at most 2 high-value URLs only if the search snippets are too thin to write
  grounded descriptions.
- After those calls, immediately compile and return the results — do not search further.
- For each pick, include `source_url` whenever possible.
- Prefer the venue's official page as `source_url`; if that is not discoverable, use the best evidence page
  you actually found in search results.
- Never invent a `source_url` or `image_url`.
- Leave `image_url` null unless a trustworthy image URL is directly present in the tool results.
- Factor in trip type: business trips need convenient options near likely office areas;
  romantic trips need ambiance; family trips need kid-friendly options.
- Also consider any food preferences mentioned in time_preferences.
- Curate 6–8 picks covering a range of cuisines, price ranges, and meal types.
- Include price range ($, $$, $$$), cuisine type, and description for each.
- Return a structured FoodOutput.
"""


def _build_prompt(intake: IntakeOutput) -> str:
    return (
        f"Find the best restaurants and food experiences in {intake.destination}. "
        f"Trip type: {intake.trip_type}. "
        f"User preferences: \"{intake.time_preferences}\". "
        f"Guests: {intake.guests}."
    )


async def run_food(intake: IntakeOutput) -> FoodOutput:
    model = AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    agent = Agent(
        model,
        toolsets=[create_tavily_mcp_server()],
        output_type=FoodOutput,
        system_prompt=SYSTEM_PROMPT,
        max_concurrency=1,
    )
    async with agent:
        result = await run_search_backed_agent(
            agent,
            _build_prompt(intake),
            usage_limits=UsageLimits(request_limit=6),
        )
    return result.output
