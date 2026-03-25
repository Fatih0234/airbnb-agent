from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from ..geocoding import geocode_destination_center
from ..schemas import CurationOutput, StayCandidate
from .formatters import format_duration, format_money, format_trip_type
from .layout_rules import (
    COMPARISON_MAX_STAYS,
    HERO_MAX_METRICS,
    LOGISTICS_MAX_ROWS,
    RECOMMENDATION_MAX_REASONS,
    cap_items,
)
from .scoring import StayScoreBreakdown, rank_stays


SectionType = Literal[
    "hero",
    "recommendation",
    "stay_map",
    "comparison",
    "neighborhood",
    "logistics",
    "weather",
    "activities",
    "food",
    "flights",
    "closing",
]


class KeyMetric(BaseModel):
    label: str
    value: str
    emphasis: Literal["high", "medium", "low"] = "medium"


class DeckSection(BaseModel):
    id: str
    type: SectionType
    heading: str
    subheading: str | None = None
    layout: str
    content: dict[str, Any]


class DeckSpec(BaseModel):
    title: str
    subtitle: str
    travel_mode: str
    style_preset: str
    trip_thesis: str
    recommended_stay_id: str | None
    runner_up_stay_id: str | None
    top_decision_factors: list[str]
    warnings: list[str]
    key_metrics: list[KeyMetric]
    sections: list[DeckSection]


def _stay_lookup(result: CurationOutput) -> dict[str, StayCandidate]:
    stays = result.stays.stays if result.stays is not None else []
    return {stay.id: stay for stay in stays}


def _score_lookup(scores: list[StayScoreBreakdown]) -> dict[str, StayScoreBreakdown]:
    return {score.stay_id: score for score in scores}


def _build_trip_thesis(
    result: CurationOutput,
    recommended: StayCandidate | None,
    recommended_score: StayScoreBreakdown | None,
) -> str:
    trip_prefix = {
        "business": "Best for a low-friction base that keeps business days easy to run.",
        "workcation": "Best for balancing productive days with a calmer home base.",
        "event_based": "Best for keeping event-day movement simple and predictable.",
        "romantic": "Best for a polished, memorable stay with a stronger sense of occasion.",
        "family": "Best for a dependable base that keeps daily choices simple.",
        "weekend_getaway": "Best for getting maximum upside from a short stay.",
        "vacation": "Best for a relaxed stay with strong local upside built around the city rhythm.",
    }.get(result.trip_type, "Best for a balanced trip brief with one clear booking lead.")

    if recommended is None:
        return trip_prefix

    suffix_parts: list[str] = []
    if recommended.price_per_night is not None:
        suffix_parts.append(f"Top pick lands around {format_money(recommended.price_per_night)}/night")
    if result.food is not None and result.food.picks:
        suffix_parts.append(f"with {len(result.food.picks)} food pick(s) already curated")
    elif result.activities is not None and result.activities.activities:
        suffix_parts.append(f"with {len(result.activities.activities)} activity option(s) to round out the trip")

    if recommended_score is not None and recommended_score.notes:
        suffix_parts.append(recommended_score.notes[0].rstrip("."))

    if not suffix_parts:
        return trip_prefix

    return f"{trip_prefix} {'. '.join(suffix_parts)}."


def _short_phrase(value: str, max_words: int = 9) -> str:
    first_sentence = value.split(".", 1)[0].strip()
    words = first_sentence.split()
    if len(words) <= max_words:
        return first_sentence
    return " ".join(words[:max_words]) + "…"


def _build_key_metrics(result: CurationOutput, recommended: StayCandidate | None) -> list[KeyMetric]:
    metrics: list[KeyMetric] = []
    if recommended is not None and recommended.price_per_night is not None:
        metrics.append(KeyMetric(label="Lead stay", value=format_money(recommended.price_per_night) + "/night", emphasis="high"))
    if result.flights is not None and result.flights.cheapest_price_usd is not None:
        metrics.append(KeyMetric(label="Best flight", value=format_money(result.flights.cheapest_price_usd), emphasis="medium"))
    if result.weather is not None and result.weather.temperature_range:
        metrics.append(KeyMetric(label="Weather window", value=result.weather.temperature_range, emphasis="low"))
    if result.activities is not None and result.activities.activities:
        metrics.append(KeyMetric(label="Activity picks", value=str(len(result.activities.activities)), emphasis="low"))
    return cap_items(metrics, HERO_MAX_METRICS)


def _build_warnings(result: CurationOutput, recommended: StayCandidate | None) -> list[str]:
    warnings: list[str] = []
    stay_count = len(result.stays.stays) if result.stays is not None else 0
    if stay_count and stay_count < 3:
        warnings.append(f"Only {stay_count} validated stay option(s) made the shortlist.")
    if result.stays is None or not result.stays.stays:
        warnings.append("No validated stay shortlist was available for this brief.")
    if recommended is not None and recommended.rating is None:
        warnings.append("The recommended stay does not include a rating signal in the current data.")
    return warnings


def _build_decision_factors(
    result: CurationOutput,
    recommended_score: StayScoreBreakdown | None,
) -> list[str]:
    factors: list[str] = []
    if recommended_score is not None:
        factors.extend(recommended_score.notes[:2])
    if result.neighborhood is not None and result.neighborhood.vibe:
        factors.append(f"Neighborhood tone: {_short_phrase(result.neighborhood.vibe)}")
    if result.flights is not None and result.flights.cheapest_price_usd is not None:
        factors.append(f"Flight floor starts around {format_money(result.flights.cheapest_price_usd)}")
    deduped: list[str] = []
    for factor in factors:
        if factor not in deduped:
            deduped.append(factor)
    return deduped[:3]


def _tradeoff_note(recommended: StayCandidate | None, runner_up: StayCandidate | None) -> str | None:
    if recommended is None or runner_up is None:
        return None

    if recommended.price_per_night is not None and runner_up.price_per_night is not None:
        if recommended.price_per_night > runner_up.price_per_night:
            return (
                f"Tradeoff: the lead option is {format_money(recommended.price_per_night - runner_up.price_per_night)} "
                "more per night than the runner-up."
            )
        if recommended.price_per_night < runner_up.price_per_night:
            return "Tradeoff: the lead option wins on value, but the runner-up may feel more premium."

    if recommended.rating is not None and runner_up.rating is not None and recommended.rating < runner_up.rating:
        return "Tradeoff: the runner-up has the stronger rating signal, but the lead option prices better overall."

    return "Tradeoff: the lead option is the best all-around pick, while the runner-up is the cleaner alternative if priorities shift."


def _comparison_rows(
    stay_lookup: dict[str, StayCandidate],
    scores: list[StayScoreBreakdown],
    recommended_id: str | None,
    runner_up_id: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, score in enumerate(scores):
        stay = stay_lookup.get(score.stay_id)
        if stay is None:
            continue

        label = ""
        if stay.id == recommended_id:
            label = "Recommended"
        elif stay.id == runner_up_id:
            label = "Runner-up"
        elif index == 0:
            label = "Best overall"

        rows.append(
            {
                "id": stay.id,
                "name": stay.name,
                "nightly": format_money(stay.price_per_night),
                "total": format_money(stay.total_price),
                "rating": f"{stay.rating:.2f}" if stay.rating is not None else "N/A",
                "highlights": score.notes[:2],
                "label": label,
                "url": stay.url,
                "image_url": stay.image_urls[0] if stay.image_urls else None,
                "location_description": stay.location_description,
                "amenities": stay.amenities[:3],
            }
        )
    return rows


def _stay_map_content(
    result: CurationOutput,
    scores: list[StayScoreBreakdown],
    stay_lookup: dict[str, StayCandidate],
    recommended_id: str | None,
) -> dict[str, Any] | None:
    markers: list[dict[str, Any]] = []
    for score in scores:
        stay = stay_lookup.get(score.stay_id)
        if stay is None or stay.latitude is None or stay.longitude is None:
            continue
        markers.append(
            {
                "id": stay.id,
                "name": stay.name,
                "latitude": stay.latitude,
                "longitude": stay.longitude,
                "price_per_night": stay.price_per_night,
                "rating": stay.rating,
                "location_description": stay.location_description,
                "url": stay.url,
                "is_recommended": stay.id == recommended_id,
            }
        )

    if not markers:
        return None

    fallback_center = None
    if len(markers) == 1:
        destination_center = geocode_destination_center(result.destination)
        if destination_center is not None:
            fallback_center = {
                "latitude": destination_center[0],
                "longitude": destination_center[1],
            }

    return {
        "summary_badge": f"{len(markers)} stay location(s)",
        "markers": markers,
        "fallback_center": fallback_center,
    }


def _build_sections(
    result: CurationOutput,
    stay_lookup: dict[str, StayCandidate],
    recommended: StayCandidate | None,
    runner_up: StayCandidate | None,
    scores: list[StayScoreBreakdown],
    recommended_score: StayScoreBreakdown | None,
) -> list[DeckSection]:
    sections: list[DeckSection] = [
        DeckSection(
            id="hero",
            type="hero",
            heading=result.destination,
            subheading=None,
            layout="hero",
            content={},
        )
    ]

    if recommended is not None:
        sections.append(
            DeckSection(
                id="recommendation",
                type="recommendation",
                heading="Recommendation",
                subheading="Best overall booking choice",
                layout="feature",
                content={
                    "recommended_stay_id": recommended.id,
                    "runner_up_stay_id": runner_up.id if runner_up is not None else None,
                    "reasons": (recommended_score.notes if recommended_score is not None else [])[:RECOMMENDATION_MAX_REASONS],
                    "tradeoff": _tradeoff_note(recommended, runner_up),
                    "cta_href": recommended.url,
                    "cta_label": "Open Airbnb listing",
                },
            )
        )

    stay_map_content = _stay_map_content(
        result,
        scores,
        stay_lookup,
        recommended.id if recommended is not None else None,
    )
    if stay_map_content is not None:
        sections.append(
            DeckSection(
                id="stay-map",
                type="stay_map",
                heading="Stay map",
                subheading="See how the shortlisted stays cluster across the destination",
                layout="map",
                content=stay_map_content,
            )
        )

    if scores:
        sections.append(
            DeckSection(
                id="comparison",
                type="comparison",
                heading="Stay comparison",
                subheading="Top shortlist ranked by price, rating, and stay signals",
                layout="table",
                content={
                    "rows": _comparison_rows(
                        stay_lookup,
                        scores,
                        recommended.id if recommended is not None else None,
                        runner_up.id if runner_up is not None else None,
                    )
                },
            )
        )

    logistics_section = None
    if result.flights is not None:
        cheapest_option = None
        if result.flights.cheapest_price_usd is not None:
            for opt in result.flights.options:
                if opt.price_usd == result.flights.cheapest_price_usd:
                    cheapest_option = opt
                    break

        logistics_section = DeckSection(
            id="logistics",
            type="logistics",
            heading="Logistics",
            subheading="Flight timing and booking practicality",
            layout="grid",
            content={
                "summary_badge": "Flight snapshot",
                "rows": [],
                "flight_summary": result.flights.search_summary,
                "flight_price": (
                    format_money(result.flights.cheapest_price_usd)
                    if result.flights.cheapest_price_usd is not None
                    else None
                ),
                "cheapest_airline": cheapest_option.airline if cheapest_option else None,
                "cheapest_stops": cheapest_option.stops if cheapest_option else None,
                "cheapest_duration": (
                    format_duration(cheapest_option.duration_minutes)
                    if cheapest_option
                    else None
                ),
            },
        )

    if result.trip_type in {"business", "workcation", "event_based"} and logistics_section is not None:
        sections.append(logistics_section)

    if result.neighborhood is not None:
        sections.append(
            DeckSection(
                id="neighborhood",
                type="neighborhood",
                heading="Neighborhood fit",
                subheading="What the surrounding area adds or subtracts",
                layout="cards",
                content={},
            )
        )

    if result.weather is not None:
        sections.append(
            DeckSection(
                id="weather",
                type="weather",
                heading="Weather and packing",
                subheading="Conditions that will shape the trip rhythm",
                layout="split",
                content={},
            )
        )

    if result.trip_type not in {"business", "workcation", "event_based"} and logistics_section is not None:
        sections.append(logistics_section)

    if result.activities is not None and result.activities.activities:
        sections.append(
            DeckSection(
                id="activities",
                type="activities",
                heading="Experience layer",
                subheading="High-upside activities matched to the brief",
                layout="grid",
                content={},
            )
        )

    if result.food is not None and result.food.picks:
        sections.append(
            DeckSection(
                id="food",
                type="food",
                heading="Food picks",
                subheading="Where the trip is most likely to eat well",
                layout="grid",
                content={},
            )
        )

    if result.flights is not None and result.flights.options:
        sections.append(
            DeckSection(
                id="flights",
                type="flights",
                heading="Flights",
                subheading="Cheapest and most practical air options",
                layout="table",
                content={},
            )
        )

    sections.append(
        DeckSection(
            id="closing",
            type="closing",
            heading="Decision summary",
            subheading="What to book next and what to verify before checkout",
            layout="summary",
            content={
                "recommended_stay_id": recommended.id if recommended is not None else None,
                "next_steps": [
                    "Open the lead stay and verify cancellation terms.",
                    "Double-check nightly rate and cleaning fees on Airbnb before booking.",
                    "Use the stay map and neighborhood summary to sanity-check the area before booking.",
                ],
            },
        )
    )

    return sections


def build_deck_spec(result: CurationOutput) -> DeckSpec:
    stay_lookup = _stay_lookup(result)
    scores = rank_stays(result)
    score_lookup = _score_lookup(scores)
    recommended_score = scores[0] if scores else None
    runner_up_score = scores[1] if len(scores) > 1 else None
    recommended = stay_lookup.get(recommended_score.stay_id) if recommended_score is not None else None
    runner_up = stay_lookup.get(runner_up_score.stay_id) if runner_up_score is not None else None

    subtitle = f"{result.dates} · {format_trip_type(result.trip_type)} · {result.guests} guest(s)"
    trip_thesis = _build_trip_thesis(result, recommended, recommended_score)
    key_metrics = _build_key_metrics(result, recommended)
    warnings = _build_warnings(result, recommended)
    top_decision_factors = _build_decision_factors(result, recommended_score)
    sections = _build_sections(result, stay_lookup, recommended, runner_up, scores, recommended_score)

    return DeckSpec(
        title=result.destination,
        subtitle=subtitle,
        travel_mode=result.trip_type,
        style_preset="auto",
        trip_thesis=trip_thesis,
        recommended_stay_id=recommended.id if recommended is not None else None,
        runner_up_stay_id=runner_up.id if runner_up is not None else None,
        top_decision_factors=top_decision_factors,
        warnings=warnings,
        key_metrics=key_metrics,
        sections=sections,
    )
