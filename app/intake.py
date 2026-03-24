import asyncio
from datetime import date

from .schemas import IntakeOutput, TripType

TRIP_TYPES: list[TripType] = [
    "vacation",
    "business",
    "workcation",
    "weekend_getaway",
    "family",
    "romantic",
    "event_based",
]

TRIP_TYPE_LABELS = {
    "vacation": "Vacation",
    "business": "Business",
    "workcation": "Workcation (work + leisure)",
    "weekend_getaway": "Weekend getaway",
    "family": "Family trip",
    "romantic": "Romantic / honeymoon",
    "event_based": "Event-based (concert, conference, match...)",
}

COMMUTE_TRIP_TYPES = {"business", "workcation", "event_based"}


def _ask(prompt: str) -> str:
    return input(prompt).strip()


def _ask_date(prompt: str) -> str:
    while True:
        raw = _ask(prompt)
        try:
            date.fromisoformat(raw)
            return raw
        except ValueError:
            print("  Please enter a date in YYYY-MM-DD format.")


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = _ask(prompt)
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            print(f"  Please enter a number (or press Enter for {default}).")


def _ask_float_optional(prompt: str) -> float | None:
    raw = _ask(prompt)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def collect_intake() -> IntakeOutput:
    print("=" * 50)
    print("  Trip Planner — Tell us about your trip")
    print("=" * 50)

    destination = ""
    while not destination:
        destination = _ask("\nDestination (city / region): ")

    print("\nTrip type:")
    for i, key in enumerate(TRIP_TYPES, 1):
        print(f"  {i}. {TRIP_TYPE_LABELS[key]}")
    trip_type: TripType = TRIP_TYPES[0]
    while True:
        raw = _ask("Choose (1–7): ")
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(TRIP_TYPES):
                trip_type = TRIP_TYPES[idx]
                break
        except ValueError:
            pass
        print("  Please enter a number between 1 and 7.")

    print()
    check_in = _ask_date("Check-in date (YYYY-MM-DD): ")
    check_out = _ask_date("Check-out date (YYYY-MM-DD): ")

    guests = _ask_int("\nNumber of guests [1]: ", default=1)

    budget = _ask_float_optional(
        "Budget per night in USD (press Enter to skip): "
    )

    target_destinations: list[str] = []
    if trip_type in COMMUTE_TRIP_TYPES:
        print(
            "\nCommute destinations — enter addresses/places you need to reach"
            " (comma-separated, or press Enter to skip):"
        )
        raw = _ask("> ")
        if raw:
            target_destinations = [t.strip() for t in raw.split(",") if t.strip()]

    print(
        "\nHow do you want to spend your time there?"
        "\n(e.g. 'explore local food scene, some museums, outdoor activities')"
    )
    time_preferences = _ask("> ")
    if not time_preferences:
        time_preferences = "General sightseeing and local experiences"

    origin_raw = _ask(
        "\nWhere are you flying from? (city or airport code, e.g. 'Istanbul' or 'IST')\n"
        "Press Enter to skip flight search: "
    )
    origin_airport = origin_raw if origin_raw else None

    print()
    return IntakeOutput(
        destination=destination,
        trip_type=trip_type,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        budget_per_night=budget,
        target_destinations=target_destinations,
        time_preferences=time_preferences,
        origin_airport=origin_airport,
    )
