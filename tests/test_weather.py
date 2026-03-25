import unittest
from unittest.mock import AsyncMock, patch

from app.schemas import IntakeOutput
from app.weather_data import (
    build_packing_tips,
    build_weather_output,
    filter_trip_window,
    summarize_window,
    _extract_city,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _intake(**overrides) -> IntakeOutput:
    defaults = dict(
        destination="Barcelona, Spain",
        trip_type="vacation",
        check_in="2026-06-10",
        check_out="2026-06-17",
        guests=2,
        budget_per_night=200.0,
        time_preferences="Beach and sightseeing",
    )
    defaults.update(overrides)
    return IntakeOutput(**defaults)


def _forecast_entry(
    dt_txt: str,
    temp: float = 22.0,
    temp_min: float = 20.0,
    temp_max: float = 24.0,
    humidity: int = 60,
    condition_main: str = "Clear",
    condition_desc: str = "clear sky",
    wind_speed: float = 3.5,
    pop: float = 0.1,
) -> dict:
    return {
        "dt_txt": dt_txt,
        "main": {
            "temp": temp,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "humidity": humidity,
        },
        "weather": [{"main": condition_main, "description": condition_desc}],
        "wind": {"speed": wind_speed},
        "pop": pop,
    }


def _forecast_response(entries: list[dict], city: str = "Barcelona") -> dict:
    return {
        "city": {"name": city},
        "list": entries,
    }


# ---------------------------------------------------------------------------
# _extract_city
# ---------------------------------------------------------------------------


class ExtractCityTest(unittest.TestCase):
    def test_single_city(self) -> None:
        self.assertEqual(_extract_city("Tokyo"), "Tokyo")

    def test_compound_destination(self) -> None:
        self.assertEqual(_extract_city("Kadikoy, Istanbul"), "Kadikoy")

    def test_triple_segment(self) -> None:
        self.assertEqual(_extract_city("SoHo, Manhattan, New York"), "SoHo")

    def test_whitespace_handling(self) -> None:
        self.assertEqual(_extract_city("  Rome , Italy  "), "Rome")

    def test_empty_string(self) -> None:
        self.assertEqual(_extract_city(""), "")


# ---------------------------------------------------------------------------
# filter_trip_window
# ---------------------------------------------------------------------------


class FilterTripWindowTest(unittest.TestCase):
    def test_filters_entries_in_range(self) -> None:
        entries = [
            _forecast_entry("2026-06-09 12:00:00"),  # before check_in
            _forecast_entry("2026-06-10 12:00:00"),  # check_in day
            _forecast_entry("2026-06-12 06:00:00"),  # mid-trip
            _forecast_entry("2026-06-16 18:00:00"),  # last day (check_out is 17th)
            _forecast_entry("2026-06-17 12:00:00"),  # check_out day, excluded
        ]
        raw = _forecast_response(entries)
        result = filter_trip_window(raw, "2026-06-10", "2026-06-17")
        self.assertEqual(len(result), 3)

    def test_empty_when_trip_beyond_window(self) -> None:
        entries = [_forecast_entry("2026-06-10 12:00:00")]
        raw = _forecast_response(entries)
        result = filter_trip_window(raw, "2026-07-01", "2026-07-05")
        self.assertEqual(result, [])

    def test_empty_forecast_list(self) -> None:
        result = filter_trip_window(_forecast_response([]), "2026-06-10", "2026-06-17")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# summarize_window
# ---------------------------------------------------------------------------


class SummarizeWindowTest(unittest.TestCase):
    def test_empty_entries(self) -> None:
        self.assertEqual(summarize_window([]), {})

    def test_temp_min_max(self) -> None:
        entries = [
            _forecast_entry("2026-06-10 06:00:00", temp_min=15, temp_max=20),
            _forecast_entry("2026-06-10 12:00:00", temp_min=22, temp_max=28),
            _forecast_entry("2026-06-10 18:00:00", temp_min=18, temp_max=25),
        ]
        s = summarize_window(entries)
        self.assertEqual(s["temp_min"], 15.0)
        self.assertEqual(s["temp_max"], 28.0)

    def test_dominant_condition(self) -> None:
        entries = [
            _forecast_entry("2026-06-10 06:00:00", condition_main="Clouds"),
            _forecast_entry("2026-06-10 12:00:00", condition_main="Clear"),
            _forecast_entry("2026-06-10 18:00:00", condition_main="Clear"),
            _forecast_entry("2026-06-11 06:00:00", condition_main="Clear"),
        ]
        s = summarize_window(entries)
        self.assertEqual(s["dominant_condition"], "Clear")

    def test_rain_pop_max(self) -> None:
        entries = [
            _forecast_entry("2026-06-10 06:00:00", pop=0.1),
            _forecast_entry("2026-06-10 12:00:00", pop=0.7),
            _forecast_entry("2026-06-10 18:00:00", pop=0.3),
        ]
        s = summarize_window(entries)
        self.assertEqual(s["rain_pop_max"], 0.7)

    def test_wind_max(self) -> None:
        entries = [
            _forecast_entry("2026-06-10 06:00:00", wind_speed=2.0),
            _forecast_entry("2026-06-10 12:00:00", wind_speed=12.5),
        ]
        s = summarize_window(entries)
        self.assertEqual(s["wind_max"], 12.5)

    def test_humidity_avg(self) -> None:
        entries = [
            _forecast_entry("2026-06-10 06:00:00", humidity=40),
            _forecast_entry("2026-06-10 12:00:00", humidity=80),
        ]
        s = summarize_window(entries)
        self.assertEqual(s["humidity_avg"], 60)


# ---------------------------------------------------------------------------
# build_packing_tips
# ---------------------------------------------------------------------------


class BuildPackingTipsTest(unittest.TestCase):
    def test_empty_summary(self) -> None:
        self.assertEqual(build_packing_tips({}, "vacation"), [])

    def test_rain_tip(self) -> None:
        tips = build_packing_tips(
            {"rain_pop_max": 0.6, "temp_max": 20, "temp_min": 15, "wind_max": 3},
            "vacation",
        )
        self.assertTrue(any("umbrella" in t.lower() for t in tips))

    def test_heat_tip(self) -> None:
        tips = build_packing_tips(
            {"rain_pop_max": 0.0, "temp_max": 35, "temp_min": 22, "wind_max": 2},
            "vacation",
        )
        self.assertTrue(any("sunscreen" in t.lower() for t in tips))

    def test_cold_tip(self) -> None:
        tips = build_packing_tips(
            {"rain_pop_max": 0.0, "temp_max": 10, "temp_min": -2, "wind_max": 2},
            "vacation",
        )
        self.assertTrue(any("warm jacket" in t.lower() for t in tips))

    def test_wind_tip(self) -> None:
        tips = build_packing_tips(
            {"rain_pop_max": 0.0, "temp_max": 20, "temp_min": 12, "wind_max": 15},
            "vacation",
        )
        self.assertTrue(any("windbreaker" in t.lower() for t in tips))

    def test_business_trip_tip(self) -> None:
        tips = build_packing_tips(
            {"rain_pop_max": 0.0, "temp_max": 22, "temp_min": 14, "wind_max": 3},
            "business",
        )
        self.assertTrue(any("smart layer" in t.lower() for t in tips))

    def test_mild_fallback(self) -> None:
        tips = build_packing_tips(
            {"rain_pop_max": 0.05, "temp_max": 22, "temp_min": 14, "wind_max": 3},
            "vacation",
        )
        self.assertTrue(len(tips) >= 1)


# ---------------------------------------------------------------------------
# build_weather_output (integration)
# ---------------------------------------------------------------------------


class BuildWeatherOutputTest(unittest.IsolatedAsyncioTestCase):
    @patch("app.weather_data.fetch_forecast", new_callable=AsyncMock)
    async def test_full_forecast(self, mock_fetch: AsyncMock) -> None:
        entries = [
            _forecast_entry(
                f"2026-06-{day:02d} 12:00:00",
                temp_min=18,
                temp_max=26,
                condition_main="Clear",
                pop=0.1,
                wind_speed=4,
            )
            for day in range(10, 17)
        ]
        mock_fetch.return_value = _forecast_response(entries)

        result = await build_weather_output(_intake())

        self.assertIn("18", result.temperature_range)
        self.assertIn("26", result.temperature_range)
        self.assertTrue(len(result.packing_tips) > 0)
        self.assertTrue(len(result.forecast_summary) > 0)
        self.assertNotIn("5-day limit", result.forecast_summary)
        mock_fetch.assert_awaited_once_with("Barcelona")

    @patch("app.weather_data.fetch_forecast", new_callable=AsyncMock)
    async def test_trip_beyond_window(self, mock_fetch: AsyncMock) -> None:
        entries = [_forecast_entry("2026-06-10 12:00:00")]
        mock_fetch.return_value = _forecast_response(entries)

        result = await build_weather_output(
            _intake(check_in="2026-07-20", check_out="2026-07-25"),
        )

        self.assertEqual(result.temperature_range, "")
        self.assertEqual(result.conditions, "")
        self.assertIn("not yet available", result.forecast_summary.lower())

    @patch("app.weather_data.fetch_forecast", new_callable=AsyncMock)
    async def test_partial_forecast(self, mock_fetch: AsyncMock) -> None:
        entries = [
            _forecast_entry(f"2026-06-{day:02d} 12:00:00", temp_min=20, temp_max=28)
            for day in range(10, 13)  # only 3 days of data
        ]
        mock_fetch.return_value = _forecast_response(entries)

        result = await build_weather_output(
            _intake(
                check_in="2026-06-10",
                check_out="2026-06-17",
            )
        )

        self.assertIn("5-day limit", result.forecast_summary)

    @patch("app.weather_data.fetch_forecast", new_callable=AsyncMock)
    async def test_api_error_returns_graceful(self, mock_fetch: AsyncMock) -> None:
        import httpx

        mock_fetch.side_effect = httpx.HTTPStatusError(
            "404",
            request=unittest.mock.MagicMock(),
            response=unittest.mock.MagicMock(status_code=404),
        )

        result = await build_weather_output(_intake())

        self.assertEqual(result.temperature_range, "")
        self.assertIn("unavailable", result.forecast_summary.lower())

    @patch("app.weather_data.fetch_forecast", new_callable=AsyncMock)
    async def test_city_extraction(self, mock_fetch: AsyncMock) -> None:
        entries = [
            _forecast_entry("2026-06-10 12:00:00", temp_min=20, temp_max=25),
        ]
        mock_fetch.return_value = _forecast_response(entries)

        await build_weather_output(_intake(destination="Kadikoy, Istanbul"))

        mock_fetch.assert_awaited_once_with("Kadikoy")
