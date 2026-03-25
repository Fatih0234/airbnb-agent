from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
import logging
import re
from typing import Any

from fast_flights import FlightData, Passengers, get_flights, search_airport

from .mcp_client import create_tavily_mcp_server

log = logging.getLogger("flight_search")

_PRICE_RE = re.compile(r"[^0-9.]")
_HOUR_RE = re.compile(r"(\d+)\s*hr")
_MINUTE_RE = re.compile(r"(\d+)\s*min")
_IATA_RE = re.compile(r"\b[A-Z]{3}\b")
_IATA_HINT_RE = re.compile(
    r"(?:iata(?:\s*code)?|airport code(?:\s*iata)?)\s*[:|\-–]\s*([A-Z]{3})\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")

_CITY_AIRPORT_OVERRIDES: dict[str, tuple[str, str]] = {
    "buenos aires": ("EZE", "Ministro Pistarini International Airport"),
    "cape town": ("CPT", "Cape Town International Airport"),
    "cdmx": ("MEX", "Mexico City International Airport"),
    "frankfurt": ("FRA", "Frankfurt Airport"),
    "kyoto": ("KIX", "Kansai International Airport"),
    "marrakech": ("RAK", "Marrakesh Menara Airport"),
    "marrakesh": ("RAK", "Marrakesh Menara Airport"),
    "mexico city": ("MEX", "Mexico City International Airport"),
    "miami": ("MIA", "Miami International Airport"),
}


@dataclass(slots=True)
class ResolvedAirport:
    original_query: str
    lookup_query: str
    iata_code: str
    airport_name: str | None
    source: str


def _parse_price_usd(price: str) -> float | None:
    cleaned = _PRICE_RE.sub("", price)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_duration_minutes(duration: str) -> int | None:
    hours_match = _HOUR_RE.search(duration)
    minutes_match = _MINUTE_RE.search(duration)
    hours = int(hours_match.group(1)) if hours_match else 0
    minutes = int(minutes_match.group(1)) if minutes_match else 0
    total = hours * 60 + minutes
    return total or None


def _normalize_options(
    *,
    options: list[Any],
    seat_class: str,
    outbound_date: str,
    return_date: str,
    limit: int,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for option in options:
        price_usd = _parse_price_usd(option.price)
        duration_minutes = _parse_duration_minutes(option.duration)
        if price_usd is None or duration_minutes is None:
            continue
        dedupe_key = (
            option.name,
            option.departure,
            option.arrival,
            duration_minutes,
            price_usd,
            option.stops,
            seat_class,
            outbound_date,
            return_date,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "airline": option.name,
                "departure_time": option.departure,
                "arrival_time": option.arrival,
                "duration_minutes": duration_minutes,
                "duration_text": option.duration,
                "price_usd": price_usd,
                "stops": option.stops,
                "seat_class": seat_class,
                "is_best": option.is_best,
                "outbound_date": outbound_date,
                "return_date": return_date,
            }
        )
    normalized.sort(key=lambda item: (item["price_usd"], item["stops"], item["duration_minutes"]))
    return normalized[:limit]


def search_airports(query: str, limit: int = 8) -> list[dict[str, str]]:
    """Find likely airport matches for a query.

    Args:
        query: Airport, city, or IATA-like text to search for.
        limit: Maximum number of results to return.
    """
    matches = search_airport(query)
    return [
        {
            "airport_name": match.name.replace("_", " ").title(),
            "iata_code": match.value,
        }
        for match in matches[:limit]
    ]


def search_round_trip_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    adults: int = 1,
    seat_class: str = "economy",
    max_stops: int | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    """Search exact-date round-trip flights with local Playwright.

    Args:
        origin: Origin IATA code.
        destination: Destination IATA code.
        departure_date: Outbound date in YYYY-MM-DD format.
        return_date: Return date in YYYY-MM-DD format.
        adults: Adult passenger count.
        seat_class: One of economy, premium-economy, business, or first.
        max_stops: Optional maximum number of stops.
        limit: Maximum number of normalized options to return.
    """
    result = get_flights(
        flight_data=[
            FlightData(date=departure_date, from_airport=origin, to_airport=destination),
            FlightData(date=return_date, from_airport=destination, to_airport=origin),
        ],
        trip="round-trip",
        passengers=Passengers(adults=adults),
        seat=seat_class,
        fetch_mode="local",
        max_stops=max_stops,
    )
    options = _normalize_options(
        options=result.flights,
        seat_class=seat_class,
        outbound_date=departure_date,
        return_date=return_date,
        limit=limit,
    )
    return {
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "return_date": return_date,
        "seat_class": seat_class,
        "price_band": result.current_price,
        "options": options,
    }


def search_round_trip_flights_flexible(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    adults: int = 1,
    seat_class: str = "economy",
    flexibility_days: int = 2,
    max_stops: int | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    """Search a small date window around the requested round-trip dates.

    Args:
        origin: Origin IATA code.
        destination: Destination IATA code.
        departure_date: Preferred outbound date in YYYY-MM-DD format.
        return_date: Preferred return date in YYYY-MM-DD format.
        adults: Adult passenger count.
        seat_class: One of economy, premium-economy, business, or first.
        flexibility_days: Number of days to search before and after each date.
        max_stops: Optional maximum number of stops.
        limit: Maximum number of normalized options to return.
    """
    departure = date.fromisoformat(departure_date)
    returning = date.fromisoformat(return_date)

    all_options: list[dict[str, Any]] = []
    for departure_offset in range(-flexibility_days, flexibility_days + 1):
        for return_offset in range(-flexibility_days, flexibility_days + 1):
            outbound = departure + timedelta(days=departure_offset)
            inbound = returning + timedelta(days=return_offset)
            if inbound <= outbound:
                continue
            try:
                result = get_flights(
                    flight_data=[
                        FlightData(date=outbound.isoformat(), from_airport=origin, to_airport=destination),
                        FlightData(date=inbound.isoformat(), from_airport=destination, to_airport=origin),
                    ],
                    trip="round-trip",
                    passengers=Passengers(adults=adults),
                    seat=seat_class,
                    fetch_mode="local",
                    max_stops=max_stops,
                )
            except Exception:
                continue
            all_options.extend(
                _normalize_options(
                    options=result.flights,
                    seat_class=seat_class,
                    outbound_date=outbound.isoformat(),
                    return_date=inbound.isoformat(),
                    limit=limit,
                )
            )

    all_options.sort(key=lambda item: (item["price_usd"], item["stops"], item["duration_minutes"]))
    return {
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "return_date": return_date,
        "seat_class": seat_class,
        "flexibility_days": flexibility_days,
        "options": all_options[:limit],
    }


def _normalize_text(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.lower()))


def _query_variants(query: str) -> list[str]:
    raw = query.strip()
    first_part = raw.split(",")[0].strip()
    variants: list[str] = []
    for candidate in (raw, first_part):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def _resolve_airport_override(query: str) -> tuple[str, str] | None:
    raw = query.strip()
    if not raw:
        return None

    candidates = [raw, raw.split(",")[0].strip()]
    for candidate in candidates:
        normalized = _normalize_text(candidate)
        override = _CITY_AIRPORT_OVERRIDES.get(normalized)
        if override is not None:
            return override
    return None


def _looks_like_iata_code(query: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{3}", query.strip()))


def _find_exact_iata_match(matches: list[dict[str, str]], code: str) -> dict[str, str] | None:
    target = code.upper()
    for match in matches:
        if match.get("iata_code", "").upper() == target:
            return match
    return None


def _pick_confident_airport_match(query: str, matches: list[dict[str, str]]) -> dict[str, str] | None:
    if not matches:
        return None

    raw = query.strip()
    if _looks_like_iata_code(raw):
        return _find_exact_iata_match(matches, raw)

    normalized_query = _normalize_text(raw.split(",")[0])
    if not normalized_query:
        return None

    containing = [
        match for match in matches if normalized_query in _normalize_text(match["airport_name"])
    ]
    if containing:
        containing.sort(key=lambda match: (len(match["airport_name"]), match["airport_name"]))
        return containing[0]

    return None


def _score_iata_codes_from_tavily_text(text: str, query: str) -> list[tuple[str, int]]:
    query_tokens = [token for token in _TOKEN_RE.findall(query.lower().split(",")[0]) if len(token) > 2]
    scores: dict[str, int] = {}

    for match in _IATA_HINT_RE.finditer(text):
        code = match.group(1).upper()
        scores[code] = scores.get(code, 0) + 10

    for match in _IATA_RE.finditer(text.upper()):
        code = match.group(0)
        start = max(0, match.start() - 120)
        end = min(len(text), match.end() + 120)
        context = text[start:end].lower()

        score = 0
        if "iata" in context:
            score += 5
        if "airport" in context:
            score += 2
        if any(token in context for token in query_tokens):
            score += 3
        if "main airport" in context or "international airport" in context:
            score += 1
        if score:
            scores[code] = scores.get(code, 0) + score

    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


async def _lookup_airport_code_with_tavily(query: str) -> str | None:
    lookup_query = query.split(",")[0].strip()
    server = create_tavily_mcp_server()
    try:
        result = await server.direct_call_tool(
            "tavily_search",
            {
                "query": f"{lookup_query} main airport IATA code",
                "max_results": 5,
                "search_depth": "advanced",
                "include_images": False,
                "include_raw_content": False,
            },
        )
    except Exception as exc:
        log.warning("Tavily airport lookup failed for '%s': %s", query, exc)
        return None

    if not isinstance(result, str):
        result = str(result)

    scored_codes = _score_iata_codes_from_tavily_text(result, lookup_query)
    if not scored_codes:
        return None

    return scored_codes[0][0]


async def resolve_airport(query: str) -> ResolvedAirport | None:
    raw_query = query.strip()
    if not raw_query:
        return None

    if _looks_like_iata_code(raw_query):
        code = raw_query.upper()
        matches = await asyncio.to_thread(search_airports, code)
        exact = _find_exact_iata_match(matches, code)
        if exact is not None:
            return ResolvedAirport(
                original_query=raw_query,
                lookup_query=code,
                iata_code=code,
                airport_name=exact["airport_name"],
                source="iata_confirmed",
            )
        return ResolvedAirport(
            original_query=raw_query,
            lookup_query=code,
            iata_code=code,
            airport_name=None,
            source="iata_input",
        )

    override = _resolve_airport_override(raw_query)
    if override is not None:
        code, default_name = override
        matches = await asyncio.to_thread(search_airports, code)
        exact = _find_exact_iata_match(matches, code)
        airport_name = exact["airport_name"] if exact is not None else default_name
        return ResolvedAirport(
            original_query=raw_query,
            lookup_query=raw_query.split(",")[0].strip(),
            iata_code=code,
            airport_name=airport_name,
            source="override",
        )

    for candidate_query in _query_variants(raw_query):
        matches = await asyncio.to_thread(search_airports, candidate_query)
        confident = _pick_confident_airport_match(candidate_query, matches)
        if confident is not None:
            return ResolvedAirport(
                original_query=raw_query,
                lookup_query=candidate_query,
                iata_code=confident["iata_code"],
                airport_name=confident["airport_name"],
                source="local_search",
            )

    tavily_code = await _lookup_airport_code_with_tavily(raw_query)
    if tavily_code is None:
        return None

    matches = await asyncio.to_thread(search_airports, tavily_code)
    exact = _find_exact_iata_match(matches, tavily_code)
    airport_name = exact["airport_name"] if exact is not None else None
    return ResolvedAirport(
        original_query=raw_query,
        lookup_query=raw_query.split(",")[0].strip(),
        iata_code=tavily_code,
        airport_name=airport_name,
        source="tavily",
    )


def _flight_option_key(option: dict[str, Any]) -> tuple[Any, ...]:
    return (
        option.get("airline"),
        option.get("departure_time"),
        option.get("arrival_time"),
        option.get("duration_minutes"),
        option.get("price_usd"),
        option.get("stops"),
        option.get("seat_class"),
    )


def merge_flight_options(*option_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for options in option_lists:
        for option in options:
            key = _flight_option_key(option)
            if key in seen:
                continue
            seen.add(key)
            merged.append(option)

    merged.sort(key=lambda item: (item["price_usd"], item["stops"], item["duration_minutes"]))
    return merged


async def _search_exact_options(
    *,
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    adults: int,
    seat_class: str,
) -> list[dict[str, Any]]:
    try:
        result = await asyncio.to_thread(
            search_round_trip_flights,
            origin,
            destination,
            departure_date,
            return_date,
            adults,
            seat_class,
        )
    except Exception as exc:
        log.warning(
            "Exact flight search failed for %s->%s (%s): %s",
            origin,
            destination,
            seat_class,
            exc,
        )
        return []
    return result.get("options", [])


async def _search_flexible_options(
    *,
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    adults: int,
    seat_class: str,
    flexibility_days: int = 2,
) -> list[dict[str, Any]]:
    try:
        result = await asyncio.to_thread(
            search_round_trip_flights_flexible,
            origin,
            destination,
            departure_date,
            return_date,
            adults,
            seat_class,
            flexibility_days,
        )
    except Exception as exc:
        log.warning(
            "Flexible flight search failed for %s->%s (%s): %s",
            origin,
            destination,
            seat_class,
            exc,
        )
        return []
    return result.get("options", [])


async def collect_flight_candidates(
    *,
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    adults: int,
    min_exact_candidates: int = 3,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    exact_economy = await _search_exact_options(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        adults=adults,
        seat_class="economy",
    )
    exact_business = await _search_exact_options(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        adults=adults,
        seat_class="business",
    )
    exact_merged = merge_flight_options(exact_economy, exact_business)

    flexible_economy: list[dict[str, Any]] = []
    if len(exact_merged) < min_exact_candidates:
        flexible_economy = await _search_flexible_options(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            adults=adults,
            seat_class="economy",
            flexibility_days=2,
        )

    merged = merge_flight_options(exact_merged, flexible_economy)
    metadata = {
        "exact_economy_count": len(exact_economy),
        "exact_business_count": len(exact_business),
        "flexible_economy_count": len(flexible_economy),
    }
    return merged, metadata
