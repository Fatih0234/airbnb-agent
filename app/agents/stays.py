from pydantic_ai import Agent
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..airbnb_images import enrich_stays_with_images
from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..mcp_client import create_airbnb_mcp_server
from ..schemas import IntakeOutput, StaysOutput

SYSTEM_PROMPT = """You are a stay research agent. Your job is to find the 5 best Airbnb listings
that match the user's trip requirements.

Instructions:
- Call airbnb_search ONCE with the destination, dates, guests, and budget. Always set ignoreRobotsText to true.
- From the search results, select the 5 best-value listings that fit the requirements.
- Do NOT call airbnb_listing_details — all needed information is in the search results.
- Leave image_urls as an empty list; images are fetched separately.
- Never invent or guess any field values. Only use data that appears in the search response.
- Return a structured StaysOutput with up to 5 StayCandidate entries.
"""


def _build_prompt(intake: IntakeOutput) -> str:
    budget_str = f"${intake.budget_per_night}/night max" if intake.budget_per_night else "no fixed budget"
    return (
        f"Find Airbnb stays in {intake.destination} "
        f"from {intake.check_in} to {intake.check_out} "
        f"for {intake.guests} guest(s), {budget_str}. "
        f"Trip type: {intake.trip_type}."
    )


async def run_stays(intake: IntakeOutput) -> StaysOutput:
    model = AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    agent = Agent(
        model,
        toolsets=[create_airbnb_mcp_server()],
        output_type=StaysOutput,
        system_prompt=SYSTEM_PROMPT,
    )
    async with agent:
        result = await agent.run(_build_prompt(intake))
    output = result.output
    output.stays = await enrich_stays_with_images(output.stays)
    return output
