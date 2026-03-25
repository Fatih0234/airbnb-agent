import logging
from collections import Counter
from datetime import date, datetime, timedelta

import httpx

from .config import get_open_weather_api_key
from .schemas import IntakeOutput, WeatherOutput

log = logging.getLogger("weather_data")

_API_URL = "https://api.openweathermap.org/data/2.5/forecast"

# Weather condition -> readable phrase used in conditions/summary strings
_CONDITION_PHRASES: dict[str, str] = {
    "Clear": "clear skies",
    "Clouds": "cloudy",
    "Rain": "rain",
    "Drizzle": "light rain",
    "Thunderstorm": "thunderstorms",
    "Snow": "snow",
    "Mist": "misty conditions",
    "Fog": "fog",
    "Haze": "hazy conditions",
}


# ---------------------------------------------------------------------------
# City extraction
# ---------------------------------------------------------------------------


def _extract_city(destination: str) -> str:
    """Take the first comma-separated segment (the city).

    'Barcelona, Spain'   -> 'Barcelona'
    'Mexico City, Mexico' -> 'Mexico City'
    'Tokyo'              -> 'Tokyo'
    """
    parts = [p.strip() for p in destination.split(",") if p.strip()]
    return parts[0] if parts else destination.strip()


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------


async def fetch_forecast(city: str) -> dict:
    """Call OpenWeatherMap 5-day / 3-hour forecast API. Returns parsed JSON."""
    api_key = get_open_weather_api_key()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _API_URL,
            params={"q": city, "appid": api_key, "units": "metric"},
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Date filtering
# ---------------------------------------------------------------------------


def _parse_entry_date(entry: dict) -> date | None:
    raw = entry.get("dt_txt", "")
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").date()
    except (ValueError, TypeError):
        return None


def filter_trip_window(
    raw: dict,
    check_in: str,
    check_out: str,
) -> list[dict]:
    """Return forecast entries whose date falls within [check_in, check_out)."""
    start = date.fromisoformat(check_in)
    end = date.fromisoformat(check_out)
    entries = raw.get("list", [])
    return [
        e
        for e in entries
        if (d := _parse_entry_date(e)) is not None and start <= d < end
    ]


# ---------------------------------------------------------------------------
# Summary computation
# ---------------------------------------------------------------------------


def summarize_window(entries: list[dict]) -> dict:
    """Compute aggregated stats from a list of forecast entries.

    Returns dict with keys:
        temp_min, temp_max, dominant_condition, rain_pop_max,
        wind_max, humidity_avg
    Returns empty dict if entries is empty.
    """
    if not entries:
        return {}

    temps: list[float] = []
    conditions: list[str] = []
    pops: list[float] = []
    winds: list[float] = []
    humidities: list[float] = []

    for e in entries:
        main = e.get("main", {})
        temps.append(main.get("temp_min", main.get("temp", 0)))
        temps.append(main.get("temp_max", main.get("temp", 0)))

        weather_list = e.get("weather", [])
        if weather_list:
            conditions.append(weather_list[0].get("main", "Unknown"))

        pops.append(e.get("pop", 0))
        winds.append(e.get("wind", {}).get("speed", 0))
        humidities.append(main.get("humidity", 0))

    dominant = "Unknown"
    if conditions:
        dominant = Counter(conditions).most_common(1)[0][0]

    return {
        "temp_min": round(min(temps), 1) if temps else 0,
        "temp_max": round(max(temps), 1) if temps else 0,
        "dominant_condition": dominant,
        "rain_pop_max": round(max(pops), 2) if pops else 0,
        "wind_max": round(max(winds), 1) if winds else 0,
        "humidity_avg": round(sum(humidities) / len(humidities)) if humidities else 0,
    }


# ---------------------------------------------------------------------------
# Packing tips
# ---------------------------------------------------------------------------


def build_packing_tips(summary: dict, trip_type: str) -> list[str]:
    """Rule-based packing tips from weather summary."""
    if not summary:
        return []

    tips: list[str] = []
    pop = summary.get("rain_pop_max", 0)
    t_max = summary.get("temp_max", 20)
    t_min = summary.get("temp_min", 15)
    wind = summary.get("wind_max", 0)

    if pop > 0.4:
        tips.append("Pack an umbrella and waterproof shoes — rain is likely.")
    elif pop > 0.2:
        tips.append("Consider a compact umbrella — some rain possible.")

    if t_max > 30:
        tips.append("Bring light, breathable clothing and sunscreen for the heat.")
    elif t_max > 25:
        tips.append("Pack light layers — warm daytime temperatures expected.")

    if t_min < 5:
        tips.append("Bring a warm jacket — evenings will be cold.")
    elif t_min < 10:
        tips.append("Pack a light jacket for cool evenings.")

    if wind > 8:
        tips.append("A windbreaker is a good idea — expect strong winds.")

    if trip_type == "business":
        tips.append("Include one weather-appropriate smart layer for meetings.")
    elif trip_type in ("romantic", "event_based"):
        tips.append("Pack one smart-casual outfit for dining or events.")

    if not tips:
        tips.append("Mild weather expected — pack comfortable, versatile layers.")

    return tips


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _format_temp_range(t_min: float, t_max: float) -> str:
    return f"{int(round(t_min))}\u00b0C \u2013 {int(round(t_max))}\u00b0C"


def _condition_phrase(condition: str) -> str:
    return _CONDITION_PHRASES.get(condition, condition.lower())


def _build_full_summary(summary: dict) -> str:
    """e.g. 'Warm days (18–26°C), mostly clear with 30% chance of afternoon rain.'"""
    t_min = summary["temp_min"]
    t_max = summary["temp_max"]
    condition = summary["dominant_condition"]
    pop = summary["rain_pop_max"]

    # Temperature descriptor
    if t_max > 30:
        temp_desc = "Hot"
    elif t_max > 25:
        temp_desc = "Warm"
    elif t_max > 15:
        temp_desc = "Mild"
    elif t_max > 5:
        temp_desc = "Cool"
    else:
        temp_desc = "Cold"

    phrase = _condition_phrase(condition)
    parts = [f"{temp_desc} days ({int(round(t_min))}\u2013{int(round(t_max))}\u00b0C)"]

    if pop > 0.4:
        parts.append(f"{phrase} with high chance of rain ({int(pop * 100)}%)")
    elif pop > 0.2:
        parts.append(f"mostly {phrase} with {int(pop * 100)}% chance of showers")
    else:
        parts.append(f"predominantly {phrase}")

    return ", ".join(parts) + "."


def _build_partial_summary(
    entries: list[dict],
    summary: dict,
    check_in: str,
    check_out: str,
) -> str:
    """Note when forecast only covers part of the trip."""
    entry_dates = {_parse_entry_date(e) for e in entries}
    entry_dates.discard(None)
    if not entry_dates:
        return _build_no_data_summary(check_in, check_out)

    covered_start = min(entry_dates)
    covered_end = max(entry_dates)

    range_str = (
        f"{covered_start.strftime('%b %d')}\u2013{covered_end.strftime('%b %d')}"
    )
    temp_str = _format_temp_range(summary["temp_min"], summary["temp_max"])
    phrase = _condition_phrase(summary["dominant_condition"])

    return (
        f"Forecast covers {range_str} only (5-day limit). Expect {temp_str}, {phrase}."
    )


def _build_no_data_summary(check_in: str, check_out: str) -> str:
    start = date.fromisoformat(check_in)
    return (
        f"Extended forecast not yet available for "
        f"{start.strftime('%B %d')} \u2013 check closer to departure."
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def build_weather_output(intake: IntakeOutput) -> WeatherOutput:
    city = _extract_city(intake.destination)
    log.info("Fetching weather for city='%s' (from '%s')", city, intake.destination)

    try:
        raw = await fetch_forecast(city)
    except httpx.HTTPStatusError as exc:
        log.warning("Weather API error for '%s': %s", city, exc)
        return WeatherOutput(
            forecast_summary=f"Weather data unavailable for {city}.",
            temperature_range="",
            conditions="",
            packing_tips=[],
        )
    except Exception as exc:
        log.warning("Weather fetch failed for '%s': %s", city, exc)
        return WeatherOutput(
            forecast_summary=f"Weather data unavailable for {city}.",
            temperature_range="",
            conditions="",
            packing_tips=[],
        )

    all_entries = raw.get("list", [])
    trip_entries = filter_trip_window(raw, intake.check_in, intake.check_out)

    start = date.fromisoformat(intake.check_in)
    end = date.fromisoformat(intake.check_out)
    trip_days = (end - start).days
    forecast_max_date = max(
        (_parse_entry_date(e) for e in all_entries),
        default=None,
    )

    if not trip_entries:
        # Entire trip is beyond the 5-day window
        return WeatherOutput(
            forecast_summary=_build_no_data_summary(intake.check_in, intake.check_out),
            temperature_range="",
            conditions="",
            packing_tips=[],
        )

    summary = summarize_window(trip_entries)
    tips = build_packing_tips(summary, intake.trip_type)

    is_partial = forecast_max_date is not None and forecast_max_date < (
        (end - timedelta(days=1)) if trip_days > 0 else start
    )

    if is_partial:
        forecast_summary = _build_partial_summary(
            trip_entries,
            summary,
            intake.check_in,
            intake.check_out,
        )
    else:
        forecast_summary = _build_full_summary(summary)

    conditions_phrase = _condition_phrase(summary["dominant_condition"])
    if summary["rain_pop_max"] > 0.2:
        conditions_phrase += (
            f" with {int(summary['rain_pop_max'] * 100)}% chance of rain"
        )

    return WeatherOutput(
        forecast_summary=forecast_summary,
        temperature_range=_format_temp_range(summary["temp_min"], summary["temp_max"]),
        conditions=conditions_phrase.capitalize(),
        packing_tips=tips,
    )
