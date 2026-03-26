import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Any

import anthropic
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..airbnb_images import enrich_stays_with_images
from ..airbnb_search import search_airbnb
from ..config import MINIMAX_BASE_URL, get_fast_model_name, get_minimax_api_key
from ..exceptions import NoResultsError, RateLimitError
from ..geocoding import geocode_destination_center
from ..schemas import IntakeOutput, StayCandidate, StaysOutput

log = logging.getLogger("stays")

DESTINATION_RADIUS_KM = 25.0

RANKING_SYSTEM_PROMPT = """You rank Airbnb stay candidates that have already been destination-validated.

Instructions:
- Only select listings from the provided validated payload.
- Return up to 5 StayCandidate entries.
- Copy fields exactly from the provided candidate payload; do not rewrite text, prices, or URLs.
- Always preserve the exact listing URL from the source payload.
- Never invent or guess any field values.
"""


@dataclass(frozen=True)
class DestinationAnchor:
    destination: str
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True)
class ListingInspection:
    room_id: str
    candidate: StayCandidate
    latitude: float | None
    longitude: float | None
    distance_km: float | None
    accepted: bool
    reason: str


def _create_model() -> AnthropicModel:
    return AnthropicModel(
        get_fast_model_name(),
        provider=AnthropicProvider(
            anthropic_client=anthropic.AsyncAnthropic(
                base_url=MINIMAX_BASE_URL,
                api_key=get_minimax_api_key(),
            )
        ),
    )


def _build_ranking_prompt(
    intake: IntakeOutput, validated: list[ListingInspection]
) -> str:
    payload = [
        {
            "room_id": inspection.room_id,
            "distance_km": round(inspection.distance_km, 2)
            if inspection.distance_km is not None
            else None,
            "candidate": inspection.candidate.model_dump(),
        }
        for inspection in validated
    ]
    budget_str = (
        f"${intake.budget_per_night}/night max"
        if intake.budget_per_night
        else "no fixed budget"
    )
    return (
        f"Choose up to 5 best-value Airbnb stays for a {intake.trip_type} trip to {intake.destination} "
        f"from {intake.check_in} to {intake.check_out} for {intake.guests} guest(s), {budget_str}. "
        "Prefer strong value, good ratings, and practical business-travel fit. "
        "Return only entries from this validated JSON payload:\n"
        f"{json.dumps(payload, ensure_ascii=True, indent=2)}"
    )


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_only.lower()).strip()


def _primary_destination_segment(destination: str) -> str:
    parts = [part.strip() for part in destination.split(",") if part.strip()]
    return parts[0] if parts else destination.strip()


def _destination_matchers(destination: str) -> list[tuple[str, list[str]]]:
    matchers: list[tuple[str, list[str]]] = []
    for segment in [part.strip() for part in destination.split(",") if part.strip()]:
        normalized = _normalize_text(segment)
        if not normalized:
            continue
        words = [
            word for word in re.findall(r"[a-z0-9]+", normalized) if len(word) >= 4
        ]
        if not words:
            continue
        matchers.append((normalized, words))

    if not matchers:
        normalized = _normalize_text(destination)
        words = [
            word for word in re.findall(r"[a-z0-9]+", normalized) if len(word) >= 4
        ]
        if normalized and words:
            matchers.append((normalized, words))
    return matchers


def _stay_matches_destination(stay: StayCandidate, intake: IntakeOutput) -> bool:
    haystack = _normalize_text(
        " ".join(
            part
            for part in [stay.name, stay.location_description, stay.url or ""]
            if part
        )
    )
    for phrase, words in _destination_matchers(intake.destination):
        if phrase and phrase in haystack:
            return True
        if words and all(word in haystack for word in words):
            return True
    return False


def _normalize_listing_url(url: str | None) -> str | None:
    if not url:
        return None
    normalized = url.strip()
    if not normalized:
        return None
    normalized = normalized.split("?", 1)[0].rstrip("/")
    return normalized


def _listing_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"/rooms/(\d+)", url)
    return match.group(1) if match else None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _parse_localized_amount(text: str | None) -> float | None:
    if not text:
        return None

    tokens = re.findall(r"\d[\d.,]*", text)
    if not tokens:
        return None

    token = tokens[0]
    if "," in token and "." in token:
        if token.rfind(".") > token.rfind(","):
            normalized = token.replace(",", "")
        else:
            normalized = token.replace(".", "").replace(",", ".")
    elif "," in token:
        head, tail = token.rsplit(",", 1)
        normalized = token.replace(",", "") if len(tail) == 3 else f"{head}.{tail}"
    else:
        head, tail = token.rsplit(".", 1) if "." in token else (token, "")
        normalized = token.replace(".", "") if tail and len(tail) == 3 else token

    try:
        return float(normalized)
    except ValueError:
        return None


def _extract_total_price(raw_listing: dict[str, Any]) -> float | None:
    label = (
        raw_listing.get("structuredDisplayPrice", {})
        .get("primaryLine", {})
        .get("accessibilityLabel")
    )
    return _parse_localized_amount(label)


def _extract_price_per_night(raw_listing: dict[str, Any]) -> float | None:
    details = (
        raw_listing.get("structuredDisplayPrice", {})
        .get("explanationData", {})
        .get("priceDetails")
    )
    if not details:
        return None

    # priceDetails is a flattened string like "5 nights x € 68.39: € 341.93"
    if not isinstance(details, str):
        details = str(details)

    match = re.search(r"x\s*[^\d]*([\d.,]+)", details)
    if match:
        return _parse_localized_amount(match.group(1))
    return _parse_localized_amount(details)


def _extract_rating(raw_listing: dict[str, Any]) -> float | None:
    label = raw_listing.get("avgRatingA11yLabel")
    if not label:
        return None

    match = re.search(r"([0-9]+(?:\.[0-9]+)?) out of 5", label)
    return float(match.group(1)) if match else None


def _extract_coordinates(
    raw_listing: dict[str, Any],
) -> tuple[float | None, float | None]:
    coordinate = (
        raw_listing.get("demandStayListing", {})
        .get("location", {})
        .get("coordinate", {})
    )
    return _coerce_float(coordinate.get("latitude")), _coerce_float(
        coordinate.get("longitude")
    )


def _candidate_from_search_result(raw_listing: dict[str, Any]) -> StayCandidate:
    room_id = str(
        raw_listing.get("id") or _listing_id_from_url(raw_listing.get("url")) or ""
    )
    name = (
        raw_listing.get("demandStayListing", {})
        .get("description", {})
        .get("name", {})
        .get("localizedStringWithTranslationPreference")
    ) or "Unknown Airbnb listing"
    latitude, longitude = _extract_coordinates(raw_listing)

    structured_content = raw_listing.get("structuredContent", {})
    location_bits: list[str] = []
    for key in ("mapSecondaryLine", "primaryLine", "secondaryLine"):
        value = structured_content.get(key)
        if value and value not in location_bits:
            location_bits.append(value)

    badges = raw_listing.get("badges")
    if badges and badges not in location_bits:
        location_bits.append(str(badges))

    return StayCandidate(
        id=room_id,
        name=name,
        price_per_night=_extract_price_per_night(raw_listing),
        total_price=_extract_total_price(raw_listing),
        url=raw_listing.get("url"),
        image_urls=raw_listing.get("image_urls", []),
        amenities=[],
        location_description=" | ".join(location_bits),
        rating=_extract_rating(raw_listing),
        latitude=latitude,
        longitude=longitude,
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    haversine = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
    return 2 * radius_km * asin(sqrt(haversine))


def _airbnb_location_query(intake: IntakeOutput, anchor: DestinationAnchor) -> str:
    return intake.destination


def _inspect_search_result(
    raw_listing: dict[str, Any],
    intake: IntakeOutput,
    anchor: DestinationAnchor,
) -> ListingInspection:
    room_id = str(raw_listing.get("id") or "")
    candidate = _candidate_from_search_result(raw_listing)
    latitude, longitude = _extract_coordinates(raw_listing)

    if (
        latitude is not None
        and longitude is not None
        and anchor.latitude is not None
        and anchor.longitude is not None
    ):
        distance_km = _haversine_km(
            anchor.latitude, anchor.longitude, latitude, longitude
        )
        accepted = distance_km <= DESTINATION_RADIUS_KM
        return ListingInspection(
            room_id=room_id,
            candidate=candidate,
            latitude=latitude,
            longitude=longitude,
            distance_km=distance_km,
            accepted=accepted,
            reason="within_radius" if accepted else "outside_radius",
        )

    # If listing has no coordinates (from scraper), accept it since Airbnb
    # already filtered by location in the search
    if latitude is None or longitude is None:
        return ListingInspection(
            room_id=room_id,
            candidate=candidate,
            latitude=latitude,
            longitude=longitude,
            distance_km=None,
            accepted=True,
            reason="no_coords_airbnb_search",
        )

    # Otherwise try text matching
    accepted = _stay_matches_destination(candidate, intake)
    return ListingInspection(
        room_id=room_id,
        candidate=candidate,
        latitude=latitude,
        longitude=longitude,
        distance_km=None,
        accepted=accepted,
        reason="text_match" if accepted else "text_mismatch",
    )


def _log_dropped_results(
    dropped: list[ListingInspection], intake: IntakeOutput
) -> None:
    if not dropped:
        return

    sample: list[str] = []
    for inspection in dropped[:5]:
        if inspection.distance_km is not None:
            sample.append(
                f"{inspection.room_id or 'unknown'}({inspection.distance_km:.1f}km)"
            )
        else:
            sample.append(f"{inspection.room_id or 'unknown'}({inspection.reason})")

    log.warning(
        "Dropped %d Airbnb search results for '%s': %s",
        len(dropped),
        intake.destination,
        ", ".join(sample),
    )


def _reconcile_ranked_stays(
    ranked_stays: list[StayCandidate],
    validated: list[ListingInspection],
) -> list[StayCandidate]:
    by_url = {
        normalized_url: inspection
        for inspection in validated
        if (normalized_url := _normalize_listing_url(inspection.candidate.url))
    }
    by_room_id = {
        inspection.room_id: inspection for inspection in validated if inspection.room_id
    }

    reconciled: list[StayCandidate] = []
    seen_ids: set[str] = set()
    for stay in ranked_stays:
        inspection: ListingInspection | None = None
        normalized_url = _normalize_listing_url(stay.url)
        if normalized_url:
            inspection = by_url.get(normalized_url)
        if inspection is None:
            room_id = _listing_id_from_url(stay.url)
            if room_id:
                inspection = by_room_id.get(room_id)

        if inspection is None or inspection.room_id in seen_ids:
            continue

        seen_ids.add(inspection.room_id)
        reconciled.append(inspection.candidate.model_copy(deep=True))
        if len(reconciled) >= 5:
            break

    return reconciled


async def _resolve_destination_anchor(intake: IntakeOutput) -> DestinationAnchor:
    default_anchor = DestinationAnchor(
        destination=intake.destination,
        latitude=None,
        longitude=None,
    )

    center = geocode_destination_center(intake.destination)
    if center is None:
        log.warning("Destination geocode failed for '%s'", intake.destination)
        return default_anchor

    anchor = DestinationAnchor(
        destination=intake.destination,
        latitude=center[0],
        longitude=center[1],
    )
    log.info(
        "Destination geocode resolved '%s' -> lat=%s lng=%s",
        intake.destination,
        f"{anchor.latitude:.6f}" if anchor.latitude is not None else "n/a",
        f"{anchor.longitude:.6f}" if anchor.longitude is not None else "n/a",
    )
    return anchor


async def _search_airbnb(
    intake: IntakeOutput,
    anchor: DestinationAnchor,
    *,
    location_override: str | None = None,
) -> dict[str, Any]:
    """Search Airbnb via HTTP (mirrors MCP server approach).

    Returns results in MCP-compatible format.
    """
    location_query = location_override or _airbnb_location_query(intake, anchor)

    log.info(
        "Searching Airbnb for '%s' (location='%s')",
        intake.destination,
        location_query,
    )

    try:
        result = await search_airbnb(
            location=location_query,
            checkin=intake.check_in,
            checkout=intake.check_out,
            adults=intake.guests,
            max_price=int(intake.budget_per_night) if intake.budget_per_night else None,
        )

        log.info(
            "Airbnb search completed: %d listings for '%s'",
            len(result.listings),
            intake.destination,
        )

        return {
            "searchResults": result.listings,
            "searchUrl": result.search_url,
            "totalFound": result.total_found,
        }

    except NoResultsError as e:
        log.info("No results found for '%s': %s", intake.destination, e)
        return {"searchResults": []}
    except RateLimitError as e:
        log.error("Rate limited for '%s': %s", intake.destination, e)
        return {"searchResults": []}
    except Exception as e:
        log.error("Airbnb search failed for '%s': %s", intake.destination, e)
        return {"searchResults": []}


def _validated_search_results(
    raw_results: list[dict[str, Any]],
    intake: IntakeOutput,
    anchor: DestinationAnchor,
) -> list[ListingInspection]:
    inspections = [
        _inspect_search_result(raw_listing, intake, anchor)
        for raw_listing in raw_results
    ]
    accepted = [inspection for inspection in inspections if inspection.accepted]
    dropped = [inspection for inspection in inspections if not inspection.accepted]

    log.info(
        "Airbnb validation for '%s': raw=%d accepted=%d dropped=%d",
        intake.destination,
        len(raw_results),
        len(accepted),
        len(dropped),
    )
    _log_dropped_results(dropped, intake)
    return accepted


async def _rank_validated_stays(
    model: AnthropicModel,
    intake: IntakeOutput,
    validated: list[ListingInspection],
) -> list[StayCandidate]:
    ranker = Agent(
        model,
        output_type=StaysOutput,
        system_prompt=RANKING_SYSTEM_PROMPT,
    )
    result = await ranker.run(_build_ranking_prompt(intake, validated))
    reconciled = _reconcile_ranked_stays(result.output.stays, validated)
    log.info(
        "Ranked %d validated Airbnb stays into %d reconciled stays for '%s'",
        len(validated),
        len(reconciled),
        intake.destination,
    )
    return reconciled


async def run_stays(intake: IntakeOutput) -> StaysOutput:
    model = _create_model()
    anchor = await _resolve_destination_anchor(intake)
    search_response = await _search_airbnb(intake, anchor)
    raw_results = (
        search_response.get("searchResults", [])
        if isinstance(search_response, dict)
        else []
    )

    if not raw_results:
        log.warning(
            "Airbnb search returned zero raw results for '%s'; returning empty stays",
            intake.destination,
        )
        return StaysOutput(stays=[])

    validated = _validated_search_results(raw_results, intake, anchor)
    if not validated:
        fallback_query = _primary_destination_segment(intake.destination)
        if fallback_query and fallback_query != intake.destination:
            log.warning(
                "No validated Airbnb stays for '%s' using full destination; retrying with '%s'",
                intake.destination,
                fallback_query,
            )
            search_response = await _search_airbnb(
                intake, anchor, location_override=fallback_query
            )
            raw_results = (
                search_response.get("searchResults", [])
                if isinstance(search_response, dict)
                else []
            )
            if raw_results:
                validated = _validated_search_results(raw_results, intake, anchor)

    if not validated:
        if anchor.latitude is not None and anchor.longitude is not None:
            log.warning(
                "All %d Airbnb results failed coordinate validation for '%s'; returning empty stays",
                len(raw_results),
                intake.destination,
            )
        else:
            log.warning(
                "No Airbnb results passed text fallback validation for '%s' after geocode fallback; returning empty stays",
                intake.destination,
            )
        return StaysOutput(stays=[])

    ranked = await _rank_validated_stays(model, intake, validated)
    if not ranked:
        log.warning(
            "Ranking returned only unverifiable Airbnb stays for '%s'; returning empty stays",
            intake.destination,
        )
        return StaysOutput(stays=[])

    ranked = await enrich_stays_with_images(ranked)
    return StaysOutput(stays=ranked)
