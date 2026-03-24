from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------

TripType = Literal[
    "vacation",
    "business",
    "workcation",
    "weekend_getaway",
    "family",
    "romantic",
    "event_based",
]


class IntakeOutput(BaseModel):
    destination: str
    trip_type: TripType
    check_in: str  # ISO date string, e.g. "2026-06-10"
    check_out: str  # ISO date string, e.g. "2026-06-17"
    guests: int
    budget_per_night: float | None  # USD, None if not specified
    target_destinations: list[str]  # addresses/places user needs to commute to
    time_preferences: str  # free text: how user wants to spend time
    origin_airport: str | None = None  # departure city or IATA code for flight search


# ---------------------------------------------------------------------------
# Stays
# ---------------------------------------------------------------------------

class StayCandidate(BaseModel):
    name: str
    price_per_night: float | None
    total_price: float | None
    url: str | None
    image_urls: list[str] = []
    amenities: list[str]
    location_description: str
    rating: float | None


class StaysOutput(BaseModel):
    stays: list[StayCandidate]  # max 5


# ---------------------------------------------------------------------------
# Neighborhood
# ---------------------------------------------------------------------------

class NeighborhoodOutput(BaseModel):
    safety_summary: str
    vibe: str
    walkability: str
    notable_notes: list[str]


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

class ActivityItem(BaseModel):
    name: str
    description: str
    image_url: str | None
    category: str  # e.g. "outdoor", "cultural", "nightlife", "sports"


class ActivitiesOutput(BaseModel):
    activities: list[ActivityItem]


# ---------------------------------------------------------------------------
# Food
# ---------------------------------------------------------------------------

class FoodItem(BaseModel):
    name: str
    cuisine_type: str
    price_range: str  # e.g. "$", "$$", "$$$"
    description: str
    image_url: str | None


class FoodOutput(BaseModel):
    picks: list[FoodItem]


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

class WeatherOutput(BaseModel):
    forecast_summary: str
    temperature_range: str  # e.g. "18°C – 26°C"
    conditions: str  # e.g. "Mostly sunny with occasional afternoon showers"
    packing_tips: list[str]


# ---------------------------------------------------------------------------
# Commute
# ---------------------------------------------------------------------------

class CommuteOption(BaseModel):
    origin: str
    destination: str
    mode: str  # "transit", "walking", "driving"
    duration_minutes: int
    summary: str  # human-readable route description


class CommuteOutput(BaseModel):
    options: list[CommuteOption]
    map_url: str | None  # static map image URL from maps_static_map


# ---------------------------------------------------------------------------
# Flights
# ---------------------------------------------------------------------------

class FlightOption(BaseModel):
    airline: str
    departure_time: str  # e.g. "08:30"
    arrival_time: str    # e.g. "12:45"
    duration_minutes: int
    price_usd: float
    stops: int           # 0 = non-stop
    seat_class: str      # e.g. "economy", "business"


class FlightsOutput(BaseModel):
    options: list[FlightOption]
    cheapest_price_usd: float | None
    search_summary: str  # human-readable summary, e.g. "5 options found, cheapest $320"


# ---------------------------------------------------------------------------
# Curation — final assembled content for slide generation
# ---------------------------------------------------------------------------

class CurationOutput(BaseModel):
    destination: str
    trip_type: TripType
    dates: str  # human-readable, e.g. "June 10–17, 2026"
    guests: int
    stays: StaysOutput
    neighborhood: NeighborhoodOutput
    weather: WeatherOutput
    activities: ActivitiesOutput
    food: FoodOutput
    commute: CommuteOutput
    flights: FlightsOutput | None = None
    destination_vibe: str  # descriptor for slide theming, e.g. "coastal", "urban", "mountain"
