import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai.exceptions import UsageLimitExceeded
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .agents.activities import run_activities
from .agents.commute import run_commute
from .agents.curation import run_curation
from .agents.flights import run_flights
from .agents.food import run_food
from .agents.neighborhood import run_neighborhood
from .agents.stays import run_stays
from .agents.weather import run_weather
from .schemas import (
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

log = logging.getLogger("pipeline")

OUTPUT_DIR = Path(__file__).parent.parent / "output"

_AGENT_NAMES = ["stays", "neighborhood", "activities", "food", "weather", "commute"]
_AGENT_NAMES_WITH_FLIGHTS = _AGENT_NAMES + ["flights"]


# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------

@dataclass
class RunSummary:
    succeeded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    curation_ok: bool = True

    @property
    def is_degraded(self) -> bool:
        return bool(self.failed) or not self.curation_ok


# ---------------------------------------------------------------------------
# Retry wrappers
# ---------------------------------------------------------------------------

def _retried(fn):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception(lambda e: not isinstance(e, UsageLimitExceeded)),
        reraise=True,
    )(fn)


@_retried
async def _run_stays(intake: IntakeOutput) -> StaysOutput:
    return await run_stays(intake)


@_retried
async def _run_neighborhood(intake: IntakeOutput) -> NeighborhoodOutput:
    return await run_neighborhood(intake)


@_retried
async def _run_activities(intake: IntakeOutput) -> ActivitiesOutput:
    return await run_activities(intake)


@_retried
async def _run_food(intake: IntakeOutput) -> FoodOutput:
    return await run_food(intake)


@_retried
async def _run_weather(intake: IntakeOutput) -> WeatherOutput:
    return await run_weather(intake)


@_retried
async def _run_commute(intake: IntakeOutput) -> CommuteOutput:
    return await run_commute(intake)


@_retried
async def _run_flights(intake: IntakeOutput) -> FlightsOutput:
    return await run_flights(intake)


# ---------------------------------------------------------------------------
# Fallbacks — used when an agent fails all retries
# ---------------------------------------------------------------------------

def _fallback_stays() -> StaysOutput:
    return StaysOutput(stays=[])


def _fallback_neighborhood() -> NeighborhoodOutput:
    return NeighborhoodOutput(
        safety_summary="", vibe="", walkability="", notable_notes=[]
    )


def _fallback_activities() -> ActivitiesOutput:
    return ActivitiesOutput(activities=[])


def _fallback_food() -> FoodOutput:
    return FoodOutput(picks=[])


def _fallback_weather() -> WeatherOutput:
    return WeatherOutput(
        forecast_summary="", temperature_range="", conditions="", packing_tips=[]
    )


def _fallback_commute() -> CommuteOutput:
    return CommuteOutput(options=[], map_url=None)


def _fallback_flights() -> FlightsOutput:
    return FlightsOutput(options=[], cheapest_price_usd=None, search_summary="")


_FALLBACKS = [
    _fallback_stays,
    _fallback_neighborhood,
    _fallback_activities,
    _fallback_food,
    _fallback_weather,
    _fallback_commute,
]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def run_pipeline(intake: IntakeOutput) -> tuple[CurationOutput, RunSummary]:
    log.info("Starting research pipeline for %s (%s)", intake.destination, intake.trip_type)
    t0 = time.monotonic()

    include_flights = intake.origin_airport is not None
    agent_names = _AGENT_NAMES_WITH_FLIGHTS if include_flights else _AGENT_NAMES
    fallbacks = _FALLBACKS + [_fallback_flights] if include_flights else _FALLBACKS

    coros = [
        _run_stays(intake),
        _run_neighborhood(intake),
        _run_activities(intake),
        _run_food(intake),
        _run_weather(intake),
        _run_commute(intake),
    ]
    if include_flights:
        log.info("Flight search enabled (origin: %s)", intake.origin_airport)
        coros.append(_run_flights(intake))

    raw = await asyncio.gather(*coros, return_exceptions=True)

    summary = RunSummary()
    resolved = []
    for name, result, fallback in zip(agent_names, raw, fallbacks):
        if isinstance(result, Exception):
            log.warning("Agent '%s' failed: %s", name, type(result).__name__)
            summary.failed.append(name)
            resolved.append(fallback())
        else:
            log.info("Agent '%s' OK", name)
            summary.succeeded.append(name)
            resolved.append(result)

    stays, neighborhood, activities, food, weather, commute = resolved[:6]
    flights: FlightsOutput | None = resolved[6] if include_flights else None

    if summary.is_degraded:
        log.warning(
            "Degraded run — %d/%d agents failed: %s",
            len(summary.failed),
            len(agent_names),
            ", ".join(summary.failed),
        )

    log.info("Research complete in %.1fs. Running curation...", time.monotonic() - t0)

    _run_curation_retried = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=15),
        reraise=True,
    )(run_curation)

    try:
        output = await _run_curation_retried(intake, stays, neighborhood, weather, activities, food, commute, flights)
        log.info("Curation OK")
    except Exception as exc:
        log.error("Curation failed: %s", type(exc).__name__)
        summary.curation_ok = False
        raise

    log.info("Pipeline finished in %.1fs", time.monotonic() - t0)
    return output, summary


# ---------------------------------------------------------------------------
# Output persistence
# ---------------------------------------------------------------------------

def _safe_filename_stem(result: CurationOutput) -> str:
    safe_dates = (
        result.dates
        .replace(" ", "_")
        .replace("–", "-")
        .replace(",", "")
    )
    return f"{result.destination.lower().replace(' ', '_')}_{safe_dates}"


def save_output(result: CurationOutput) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"{_safe_filename_stem(result)}.json"
    path.write_text(result.model_dump_json(indent=2))
    return path


def save_html(result: CurationOutput, html: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"{_safe_filename_stem(result)}.html"
    path.write_text(html, encoding="utf-8")
    return path
