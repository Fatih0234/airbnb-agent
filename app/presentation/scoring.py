from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from ..schemas import CurationOutput, StayCandidate


class StayScoreBreakdown(BaseModel):
    stay_id: str
    stay_name: str
    total_score: float
    price_score: float
    rating_score: float
    feature_score: float
    trip_fit_score: float
    notes: list[str]


def _normalize_prices(stays: list[StayCandidate]) -> dict[str, float]:
    priced = [stay.price_per_night for stay in stays if stay.price_per_night is not None]
    if not priced:
        return {stay.id: 0.5 for stay in stays}

    low = min(priced)
    high = max(priced)
    if low == high:
        return {stay.id: 1.0 for stay in stays if stay.price_per_night is not None} | {
            stay.id: 0.5 for stay in stays if stay.price_per_night is None
        }

    scores: dict[str, float] = {}
    for stay in stays:
        if stay.price_per_night is None:
            scores[stay.id] = 0.5
            continue
        scores[stay.id] = max(0.0, min(1.0, 1 - ((stay.price_per_night - low) / (high - low))))
    return scores


def _normalize_rating(rating: float | None) -> float:
    if rating is None:
        return 0.5
    return max(0.0, min(1.0, rating / 5))


def _keyword_hits(text: str, weighted_terms: Iterable[tuple[str, float]]) -> tuple[float, list[str]]:
    score = 0.0
    notes: list[str] = []
    for term, weight in weighted_terms:
        if term in text:
            score += weight
            notes.append(term)
    return min(score, 1.0), notes


def _feature_score(stay: StayCandidate) -> tuple[float, list[str]]:
    text = " ".join(
        [
            stay.name.lower(),
            stay.location_description.lower(),
            " ".join(amenity.lower() for amenity in stay.amenities),
        ]
    )
    return _keyword_hits(
        text,
        [
            ("guest favorite", 0.35),
            ("business host", 0.22),
            ("wifi", 0.20),
            ("air conditioning", 0.12),
            ("terrace", 0.14),
            ("balcony", 0.12),
            ("cozy", 0.08),
            ("spacious", 0.10),
            ("studio", 0.08),
            ("walk", 0.08),
        ],
    )


def _trip_fit_score(stay: StayCandidate, trip_type: str) -> tuple[float, list[str]]:
    text = " ".join(
        [
            stay.name.lower(),
            stay.location_description.lower(),
            " ".join(amenity.lower() for amenity in stay.amenities),
        ]
    )
    profiles: dict[str, list[tuple[str, float]]] = {
        "business": [("business host", 0.35), ("wifi", 0.25), ("studio", 0.15), ("air conditioning", 0.10)],
        "workcation": [("wifi", 0.35), ("studio", 0.18), ("terrace", 0.12), ("air conditioning", 0.10)],
        "event_based": [("walk", 0.20), ("guest favorite", 0.20), ("air conditioning", 0.10)],
        "romantic": [("terrace", 0.28), ("balcony", 0.20), ("cozy", 0.18), ("beautiful", 0.14)],
        "family": [("spacious", 0.28), ("2 beds", 0.18), ("kitchen", 0.18), ("family", 0.18)],
        "vacation": [("guest favorite", 0.22), ("terrace", 0.20), ("walk", 0.12), ("balcony", 0.10)],
        "weekend_getaway": [("guest favorite", 0.22), ("cozy", 0.20), ("terrace", 0.18)],
    }
    weighted_terms = profiles.get(trip_type, [("guest favorite", 0.20), ("walk", 0.10)])
    return _keyword_hits(text, weighted_terms)


def rank_stays(result: CurationOutput) -> list[StayScoreBreakdown]:
    stays = result.stays.stays if result.stays is not None else []
    if not stays:
        return []

    price_scores = _normalize_prices(stays)
    max_price = min((stay.price_per_night for stay in stays if stay.price_per_night is not None), default=None)
    max_rating = max((stay.rating for stay in stays if stay.rating is not None), default=None)

    breakdowns: list[StayScoreBreakdown] = []
    for stay in stays:
        feature_score, feature_terms = _feature_score(stay)
        trip_fit_score, trip_terms = _trip_fit_score(stay, result.trip_type)
        rating_score = _normalize_rating(stay.rating)
        price_score = price_scores.get(stay.id, 0.5)

        notes: list[str] = []
        if stay.price_per_night is not None and max_price is not None and stay.price_per_night == max_price:
            notes.append("Lowest nightly price in the shortlist")
        if stay.rating is not None and max_rating is not None and stay.rating == max_rating:
            notes.append("Strongest rating in the shortlist")
        if "guest favorite" in feature_terms:
            notes.append("Guest favorite signal suggests reliable guest satisfaction")
        if "business host" in feature_terms:
            notes.append("Business-host cue supports a smoother operational stay")
        if "wifi" in feature_terms or "wifi" in trip_terms:
            notes.append("Work-friendly signal includes wifi in the listing copy")
        if "terrace" in feature_terms or "balcony" in feature_terms:
            notes.append("Outdoor-space cue raises leisure upside")
        if not notes:
            notes.append("Balanced mix of price, rating, and stay signals")

        total_score = (
            0.40 * price_score
            + 0.35 * rating_score
            + 0.15 * trip_fit_score
            + 0.10 * feature_score
        )

        breakdowns.append(
            StayScoreBreakdown(
                stay_id=stay.id,
                stay_name=stay.name,
                total_score=round(total_score, 4),
                price_score=round(price_score, 4),
                rating_score=round(rating_score, 4),
                feature_score=round(feature_score, 4),
                trip_fit_score=round(trip_fit_score, 4),
                notes=notes,
            )
        )

    return sorted(
        breakdowns,
        key=lambda item: (
            -item.total_score,
            -item.rating_score,
            -item.price_score,
            item.stay_name.lower(),
        ),
    )
