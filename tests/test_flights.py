from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents import flights
from app.flight_search import ResolvedAirport, collect_flight_candidates, resolve_airport
from app.schemas import FlightsOutput, FlightOption, IntakeOutput


def _intake() -> IntakeOutput:
    return IntakeOutput(
        destination="Mexico City, Mexico",
        trip_type="event_based",
        check_in="2026-09-03",
        check_out="2026-09-07",
        guests=2,
        budget_per_night=230.0,
        time_preferences="Concert weekend with good food and easy returns.",
        origin_airport="MIA",
    )


def _option(
    *,
    airline: str,
    departure_time: str,
    arrival_time: str,
    duration_minutes: int,
    price_usd: float,
    stops: int,
    seat_class: str,
) -> dict[str, object]:
    return {
        "airline": airline,
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "duration_minutes": duration_minutes,
        "price_usd": price_usd,
        "stops": stops,
        "seat_class": seat_class,
    }


class FlightResolutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_known_city_override_resolves_without_tavily(self) -> None:
        with patch(
            "app.flight_search.search_airports",
            return_value=[],
        ), patch(
            "app.flight_search._lookup_airport_code_with_tavily",
            new=AsyncMock(),
        ) as tavily_lookup:
            resolved = await resolve_airport("Mexico City, Mexico")

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.iata_code, "MEX")
        self.assertEqual(resolved.airport_name, "Mexico City International Airport")
        self.assertEqual(resolved.source, "override")
        tavily_lookup.assert_not_awaited()

    async def test_direct_iata_input_resolves_without_tavily(self) -> None:
        with patch(
            "app.flight_search.search_airports",
            return_value=[{"airport_name": "Miami International Airport", "iata_code": "MIA"}],
        ), patch(
            "app.flight_search._lookup_airport_code_with_tavily",
            new=AsyncMock(),
        ) as tavily_lookup:
            resolved = await resolve_airport("MIA")

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.iata_code, "MIA")
        self.assertEqual(resolved.source, "iata_confirmed")
        tavily_lookup.assert_not_awaited()

    async def test_ambiguous_destination_uses_tavily_fallback_and_confirms_code(self) -> None:
        def fake_search(query: str, limit: int = 8) -> list[dict[str, str]]:
            if query == "Istanbul, Turkey":
                return []
            if query == "Istanbul":
                return []
            if query == "IST":
                return [{"airport_name": "Istanbul Airport", "iata_code": "IST"}]
            return []

        with patch("app.flight_search.search_airports", side_effect=fake_search), patch(
            "app.flight_search._lookup_airport_code_with_tavily",
            new=AsyncMock(return_value="IST"),
        ) as tavily_lookup:
            resolved = await resolve_airport("Istanbul, Turkey")

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.iata_code, "IST")
        self.assertEqual(resolved.airport_name, "Istanbul Airport")
        self.assertEqual(resolved.source, "tavily")
        tavily_lookup.assert_awaited_once()


class FlightCollectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_exact_date_results_sufficient_so_flexible_search_is_skipped(self) -> None:
        economy = [
            _option(
                airline="Airline A",
                departure_time="08:00",
                arrival_time="11:00",
                duration_minutes=180,
                price_usd=220.0,
                stops=0,
                seat_class="economy",
            ),
            _option(
                airline="Airline B",
                departure_time="09:00",
                arrival_time="13:00",
                duration_minutes=240,
                price_usd=250.0,
                stops=1,
                seat_class="economy",
            ),
        ]
        business = [
            _option(
                airline="Airline C",
                departure_time="10:00",
                arrival_time="13:30",
                duration_minutes=210,
                price_usd=540.0,
                stops=0,
                seat_class="business",
            )
        ]

        with patch(
            "app.flight_search.search_round_trip_flights",
            side_effect=[{"options": economy}, {"options": business}],
        ) as exact_search, patch(
            "app.flight_search.search_round_trip_flights_flexible",
            side_effect=AssertionError("flexible search should not run"),
        ):
            candidates, metadata = await collect_flight_candidates(
                origin="MIA",
                destination="MEX",
                departure_date="2026-09-03",
                return_date="2026-09-07",
                adults=2,
            )

        self.assertEqual(exact_search.call_count, 2)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(metadata["flexible_economy_count"], 0)

    async def test_flexible_search_runs_once_when_exact_results_are_too_sparse(self) -> None:
        economy = [
            _option(
                airline="Airline A",
                departure_time="08:00",
                arrival_time="11:00",
                duration_minutes=180,
                price_usd=220.0,
                stops=0,
                seat_class="economy",
            )
        ]
        flexible = [
            _option(
                airline="Airline B",
                departure_time="07:30",
                arrival_time="10:30",
                duration_minutes=180,
                price_usd=210.0,
                stops=0,
                seat_class="economy",
            ),
            _option(
                airline="Airline C",
                departure_time="12:00",
                arrival_time="16:00",
                duration_minutes=240,
                price_usd=260.0,
                stops=1,
                seat_class="economy",
            ),
        ]

        with patch(
            "app.flight_search.search_round_trip_flights",
            side_effect=[{"options": economy}, {"options": []}],
        ), patch(
            "app.flight_search.search_round_trip_flights_flexible",
            return_value={"options": flexible},
        ) as flexible_search:
            candidates, metadata = await collect_flight_candidates(
                origin="MIA",
                destination="MEX",
                departure_date="2026-09-03",
                return_date="2026-09-07",
                adults=2,
            )

        flexible_search.assert_called_once()
        self.assertEqual(len(candidates), 3)
        self.assertEqual(metadata["flexible_economy_count"], 2)


class FlightAgentIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_flights_returns_empty_result_when_destination_cannot_be_resolved(self) -> None:
        with patch(
            "app.agents.flights.resolve_airport",
            side_effect=[
                ResolvedAirport(
                    original_query="MIA",
                    lookup_query="MIA",
                    iata_code="MIA",
                    airport_name="Miami International Airport",
                    source="iata_confirmed",
                ),
                None,
            ],
        ):
            output = await flights.run_flights(_intake())

        self.assertEqual(output.options, [])
        self.assertIsNone(output.cheapest_price_usd)
        self.assertIn("Could not confidently resolve a destination airport", output.search_summary)

    async def test_run_flights_uses_model_only_ranking_and_recomputes_cheapest_price(self) -> None:
        agent_instance = MagicMock()
        agent_instance.__aenter__ = AsyncMock(return_value=agent_instance)
        agent_instance.__aexit__ = AsyncMock(return_value=None)
        agent_instance.run = AsyncMock(
            return_value=SimpleNamespace(
                output=FlightsOutput(
                    options=[
                        FlightOption(
                            airline="Airline B",
                            departure_time="09:00",
                            arrival_time="13:00",
                            duration_minutes=240,
                            price_usd=320.0,
                            stops=1,
                            seat_class="economy",
                        ),
                        FlightOption(
                            airline="Airline A",
                            departure_time="08:00",
                            arrival_time="11:00",
                            duration_minutes=180,
                            price_usd=210.0,
                            stops=0,
                            seat_class="economy",
                        ),
                    ],
                    cheapest_price_usd=None,
                    search_summary="2 candidates reviewed; cheapest $210",
                )
            )
        )

        with patch(
            "app.agents.flights.resolve_airport",
            side_effect=[
                ResolvedAirport(
                    original_query="MIA",
                    lookup_query="MIA",
                    iata_code="MIA",
                    airport_name="Miami International Airport",
                    source="iata_confirmed",
                ),
                ResolvedAirport(
                    original_query="Mexico City, Mexico",
                    lookup_query="Mexico City",
                    iata_code="MEX",
                    airport_name="Mexico City International Airport",
                    source="tavily",
                ),
            ],
        ), patch(
            "app.agents.flights.collect_flight_candidates",
            new=AsyncMock(
                return_value=(
                    [
                        _option(
                            airline="Airline A",
                            departure_time="08:00",
                            arrival_time="11:00",
                            duration_minutes=180,
                            price_usd=210.0,
                            stops=0,
                            seat_class="economy",
                        ),
                        _option(
                            airline="Airline B",
                            departure_time="09:00",
                            arrival_time="13:00",
                            duration_minutes=240,
                            price_usd=320.0,
                            stops=1,
                            seat_class="economy",
                        ),
                    ],
                    {
                        "exact_economy_count": 1,
                        "exact_business_count": 1,
                        "flexible_economy_count": 0,
                    },
                )
            ),
        ), patch("app.agents.flights.get_minimax_api_key", return_value="test-key"), patch(
            "app.agents.flights.get_fast_model_name",
            return_value="test-model",
        ), patch(
            "app.agents.flights.AnthropicModel",
            return_value=object(),
        ), patch(
            "app.agents.flights.Agent",
            return_value=agent_instance,
        ) as agent_cls:
            output = await flights.run_flights(_intake())

        self.assertEqual(output.cheapest_price_usd, 210.0)
        self.assertNotIn("toolsets", agent_cls.call_args.kwargs)
        usage_limits = agent_instance.run.call_args.kwargs["usage_limits"]
        self.assertEqual(usage_limits.request_limit, flights.MODEL_REQUEST_LIMIT)


if __name__ == "__main__":
    unittest.main()
