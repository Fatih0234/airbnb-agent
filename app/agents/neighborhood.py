from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..search_agent import run_search_backed_agent
from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..mcp_client import create_tavily_mcp_server
from ..schemas import IntakeOutput, NeighborhoodOutput

SEARCH_REQUEST_LIMIT = 4

SYSTEM_PROMPT = """You are a neighborhood research agent. Your job is to give an honest,
well-sourced summary of the destination's neighborhood character.

Instructions:
- Make at most 2 Tavily searches total for the entire run.
- Use only tavily-search for this task. Do not use tavily-extract.
- Use 1 search for safety plus area fit, and 1 search for walkability plus practical caveats.
- Do not loop, broaden the search repeatedly, or run extra follow-up searches after those 2.
- Never make claims without finding supporting search results.
- Summarize into: safety (honest, not alarmist), vibe (character, atmosphere, who goes there),
  walkability, and any notable notes the traveler should know.
- Return a structured NeighborhoodOutput.
"""


def _build_prompt(intake: IntakeOutput) -> str:
    return (
        f"Research the neighborhood safety, vibe, and walkability of {intake.destination}. "
        f"Trip type: {intake.trip_type}. "
        f"Dates: {intake.check_in} to {intake.check_out}."
    )


async def run_neighborhood(intake: IntakeOutput) -> NeighborhoodOutput:
    model = AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    agent = Agent(
        model,
        toolsets=[create_tavily_mcp_server()],
        output_type=NeighborhoodOutput,
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
