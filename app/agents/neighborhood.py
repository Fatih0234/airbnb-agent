from pydantic_ai import Agent
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..mcp_client import create_brave_mcp_server
from ..schemas import IntakeOutput, NeighborhoodOutput

SYSTEM_PROMPT = """You are a neighborhood research agent. Your job is to give an honest,
well-sourced summary of the destination's neighborhood character.

Instructions:
- Use brave_llm_context_search to research the destination's safety reputation, overall vibe,
  and walkability. Search for things like "{destination} neighborhood safety", "{destination}
  best areas to stay", "{destination} walkability".
- Use brave_web_search as a fallback or for supplementary context.
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
        toolsets=[create_brave_mcp_server()],
        output_type=NeighborhoodOutput,
        system_prompt=SYSTEM_PROMPT,
    )
    async with agent:
        result = await agent.run(_build_prompt(intake))
    return result.output
