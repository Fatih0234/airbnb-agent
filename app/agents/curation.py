import json

from pydantic_ai import Agent
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..config import MINIMAX_BASE_URL, get_minimax_api_key, get_model_name
from ..schemas import (
    ActivitiesOutput,
    CommuteOutput,
    CurationOutput,
    FlightsOutput,
    FoodOutput,
    IntakeOutput,
    NeighborhoodOutput,
    StaysOutput,
    WeatherOutput,
)

SYSTEM_PROMPT = """You are a trip curation agent. You receive raw research from multiple
specialized agents and synthesize it into a polished, structured travel brief.

Instructions:
- Review all research sections provided (stays, neighborhood, weather, activities, food, commute,
  and flights if present).
- Select and curate the best options from each section — don't just copy everything verbatim.
- Write clear, useful copy for each section that a traveler can act on.
- Assign a destination_vibe that captures the character of the destination in one word or short
  phrase. Examples: "coastal", "urban", "historic", "mountain", "tropical", "cosmopolitan".
  This will be used to style the output slides.
- If a research section is empty or failed, omit it gracefully — don't mention the failure.
- If flights data is present and has options, include it in the output as-is (preserve all fields).
  If flights is null or has no options, set flights to null in CurationOutput.
- Format dates as human-readable (e.g. "June 10–17, 2026").
- Return a complete, structured CurationOutput.
"""


def _build_prompt(
    intake: IntakeOutput,
    stays: StaysOutput,
    neighborhood: NeighborhoodOutput,
    weather: WeatherOutput,
    activities: ActivitiesOutput,
    food: FoodOutput,
    commute: CommuteOutput,
    flights: FlightsOutput | None,
) -> str:
    research = {
        "intake": intake.model_dump(),
        "stays": stays.model_dump(),
        "neighborhood": neighborhood.model_dump(),
        "weather": weather.model_dump(),
        "activities": activities.model_dump(),
        "food": food.model_dump(),
        "commute": commute.model_dump(),
        "flights": flights.model_dump() if flights is not None else None,
    }
    return (
        f"Synthesize the following trip research into a complete CurationOutput.\n\n"
        f"```json\n{json.dumps(research, indent=2)}\n```"
    )


async def run_curation(
    intake: IntakeOutput,
    stays: StaysOutput,
    neighborhood: NeighborhoodOutput,
    weather: WeatherOutput,
    activities: ActivitiesOutput,
    food: FoodOutput,
    commute: CommuteOutput,
    flights: FlightsOutput | None = None,
) -> CurationOutput:
    model = AnthropicModel(
        get_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    agent = Agent(
        model,
        output_type=CurationOutput,
        system_prompt=SYSTEM_PROMPT,
        retries=3,
    )
    result = await agent.run(
        _build_prompt(intake, stays, neighborhood, weather, activities, food, commute, flights)
    )
    return result.output
