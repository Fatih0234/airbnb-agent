import json
import anthropic
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.usage import UsageLimits

from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..food_search import MODEL_CANDIDATE_LIMIT, collect_food_candidates
from ..schemas import FoodOutput, IntakeOutput

MODEL_REQUEST_LIMIT = 3
SEARCH_REQUEST_LIMIT = MODEL_REQUEST_LIMIT

SYSTEM_PROMPT = """You are a food ranking agent. Your job is to select the best restaurants,
cafes, and food experiences from a precomputed candidate list.

Instructions:
- Use only the provided food candidates. Do not search or invent additional options.
- Curate a focused list of 6–8 picks when enough candidates are available.
- Match the trip brief: business trips need convenience, romantic trips need ambiance,
  family trips need kid-friendly range, and time_preferences should shape the mix.
- Never invent or replace `source_url` or `image_url`; preserve them only from provided candidates.
- You may refine descriptions for clarity and keep cuisine_type/price_range aligned with the supplied evidence.
- Include price range ($, $$, $$$), cuisine type, and description for each.
- Return a structured FoodOutput.
"""


def _build_prompt(
    intake: IntakeOutput,
    *,
    candidates: list[dict[str, object]],
    search_metadata: dict[str, object],
) -> str:
    return (
        f"Rank the provided food candidates for a trip to {intake.destination}.\n\n"
        f"Trip context:\n"
        f"- trip type: {intake.trip_type}\n"
        f"- dates: {intake.check_in} to {intake.check_out}\n"
        f"- guests: {intake.guests}\n"
        f"- time preferences: {intake.time_preferences}\n\n"
        f"Search metadata:\n{json.dumps(search_metadata, indent=2)}\n\n"
        f"Candidate food picks:\n{json.dumps(candidates, indent=2)}"
    )


async def run_food(intake: IntakeOutput) -> FoodOutput:
    candidates, search_metadata = await collect_food_candidates(
        destination=intake.destination,
        trip_type=intake.trip_type,
        time_preferences=intake.time_preferences,
        limit=MODEL_CANDIDATE_LIMIT,
    )

    if not candidates:
        return FoodOutput(picks=[])

    model = AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    agent = Agent(
        model,
        output_type=FoodOutput,
        system_prompt=SYSTEM_PROMPT,
        max_concurrency=1,
    )
    async with agent:
        result = await agent.run(
            _build_prompt(
                intake,
                candidates=candidates,
                search_metadata={
                    **search_metadata,
                    "candidate_count": len(candidates),
                },
            ),
            usage_limits=UsageLimits(request_limit=MODEL_REQUEST_LIMIT),
        )
    return result.output
