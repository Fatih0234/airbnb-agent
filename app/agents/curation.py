from __future__ import annotations

from collections import Counter
from datetime import date

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


def _format_dates(check_in: str, check_out: str) -> str:
    start = date.fromisoformat(check_in)
    end = date.fromisoformat(check_out)

    if start.year == end.year and start.month == end.month:
        return f"{start.strftime('%B')} {start.day}\u2013{end.day}, {start.year}"
    if start.year == end.year:
        return f"{start.strftime('%B')} {start.day} \u2013 {end.strftime('%B')} {end.day}, {start.year}"
    return f"{start.strftime('%B')} {start.day}, {start.year} \u2013 {end.strftime('%B')} {end.day}, {end.year}"


def _has_neighborhood_data(neighborhood: NeighborhoodOutput) -> bool:
    return bool(
        neighborhood.safety_summary
        or neighborhood.vibe
        or neighborhood.walkability
        or neighborhood.notable_notes
    )


def _has_weather_data(weather: WeatherOutput) -> bool:
    return bool(
        weather.forecast_summary
        or weather.temperature_range
        or weather.conditions
        or weather.packing_tips
    )


def _infer_destination_vibe(
    intake: IntakeOutput,
    neighborhood: NeighborhoodOutput,
    activities: ActivitiesOutput,
) -> str:
    texts = [
        intake.destination,
        intake.time_preferences,
        neighborhood.vibe,
        neighborhood.walkability,
        neighborhood.safety_summary,
        *neighborhood.notable_notes,
        *(activity.name for activity in activities.activities),
        *(activity.description for activity in activities.activities),
    ]
    haystack = " ".join(part.lower() for part in texts if part)

    keywords = {
        "coastal": ["coast", "coastal", "beach", "waterfront", "seaside", "marina", "mediterranean", "sea"],
        "historic": ["historic", "history", "old town", "medieval", "cathedral", "castle", "roman", "gothic"],
        "mountain": ["mountain", "alpine", "peaks", "hiking", "summit"],
        "tropical": ["tropical", "island", "palm", "jungle", "lagoon"],
        "romantic": ["romantic", "honeymoon", "sunset", "couples"],
        "cosmopolitan": ["cosmopolitan", "international", "design", "luxury", "global", "business"],
        "urban": ["urban", "city", "downtown", "nightlife", "metro", "walkable", "business district"],
    }

    scores: Counter[str] = Counter()
    for vibe, vibe_keywords in keywords.items():
        for keyword in vibe_keywords:
            if keyword in haystack:
                scores[vibe] += 1

    if scores:
        return scores.most_common(1)[0][0]

    trip_defaults = {
        "business": "urban",
        "workcation": "cosmopolitan",
        "romantic": "romantic",
        "family": "historic",
        "event_based": "urban",
        "weekend_getaway": "historic",
        "vacation": "coastal",
    }
    return trip_defaults.get(intake.trip_type, "urban")


async def run_curation(
    intake: IntakeOutput,
    stays: StaysOutput,
    neighborhood: NeighborhoodOutput,
    weather: WeatherOutput,
    activities: ActivitiesOutput,
    food: FoodOutput,
    commute: CommuteOutput,
    flights: FlightsOutput | None = None,
    failed_sections: list[str] | None = None,
) -> CurationOutput:
    failed = set(failed_sections or [])

    curated_stays = None if "stays" in failed or not stays.stays else stays
    curated_neighborhood = None if "neighborhood" in failed or not _has_neighborhood_data(neighborhood) else neighborhood
    curated_weather = None if "weather" in failed or not _has_weather_data(weather) else weather
    curated_activities = None if "activities" in failed or not activities.activities else activities
    curated_food = None if "food" in failed or not food.picks else food
    curated_commute = None if "commute" in failed or (not commute.options and not commute.map_url) else commute
    curated_flights = None if "flights" in failed or flights is None or not flights.options else flights

    return CurationOutput(
        destination=intake.destination,
        trip_type=intake.trip_type,
        dates=_format_dates(intake.check_in, intake.check_out),
        guests=intake.guests,
        stays=curated_stays,
        neighborhood=curated_neighborhood,
        weather=curated_weather,
        activities=curated_activities,
        food=curated_food,
        commute=curated_commute,
        flights=curated_flights,
        destination_vibe=_infer_destination_vibe(
            intake,
            curated_neighborhood or NeighborhoodOutput(
                safety_summary="",
                vibe="",
                walkability="",
                notable_notes=[],
            ),
            curated_activities or ActivitiesOutput(activities=[]),
        ),
    )
