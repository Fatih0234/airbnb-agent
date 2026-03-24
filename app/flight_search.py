from __future__ import annotations

from datetime import date, timedelta
import re
from typing import Any

from fast_flights import FlightData, Passengers, get_flights, search_airport


_PRICE_RE = re.compile(r"[^0-9.]")
_HOUR_RE = re.compile(r"(\d+)\s*hr")
_MINUTE_RE = re.compile(r"(\d+)\s*min")


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
