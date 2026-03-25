import unittest
from unittest.mock import AsyncMock, patch

from app.agents.slides import generate_slides
from app.agents.stays import (
    _candidate_from_search_result,
    _reconcile_ranked_stays,
    _resolve_destination_anchor,
    _search_airbnb,
    run_stays,
)
from app.presentation.deck_spec import build_deck_spec
from app.presentation.scoring import rank_stays
from app.presentation.style_presets import CONCIERGE_LUXURY, PRACTICAL_PLANNER, choose_style_preset
from app.schemas import (
    ActivitiesOutput,
    ActivityItem,
    CurationOutput,
    FlightsOutput,
    FlightOption,
    FoodItem,
    FoodOutput,
    NeighborhoodOutput,
    StayCandidate,
    StaysOutput,
    IntakeOutput,
    WeatherOutput,
)


def _sample_result(trip_type: str = "business") -> CurationOutput:
    return CurationOutput(
        destination="Barcelona, Spain",
        trip_type=trip_type,
        dates="June 9–13, 2026",
        guests=1,
        stays=StaysOutput(
            stays=[
                StayCandidate(
                    id="stay-1",
                    name="Focused studio with fast wifi",
                    price_per_night=110.0,
                    total_price=440.0,
                    url="https://www.airbnb.com/rooms/111",
                    image_urls=["https://images.example.com/stay-1.jpg"],
                    amenities=[],
                    location_description="Studio | Business host | Wifi | Guest favorite",
                    rating=4.92,
                    latitude=41.3902,
                    longitude=2.1540,
                ),
                StayCandidate(
                    id="stay-2",
                    name="Design loft with terrace",
                    price_per_night=170.0,
                    total_price=680.0,
                    url="https://www.airbnb.com/rooms/222",
                    image_urls=["https://images.example.com/stay-2.jpg"],
                    amenities=[],
                    location_description="1 bedroom | Terrace | Guest favorite",
                    rating=4.97,
                    latitude=41.3947,
                    longitude=2.1649,
                ),
                StayCandidate(
                    id="stay-3",
                    name="Budget city room",
                    price_per_night=None,
                    total_price=None,
                    url="https://www.airbnb.com/rooms/333",
                    image_urls=[],
                    amenities=[],
                    location_description="Private room",
                    rating=None,
                    latitude=41.3818,
                    longitude=2.1761,
                ),
            ]
        ),
        neighborhood=NeighborhoodOutput(
            safety_summary="Busy but generally well-trafficked around the core blocks.",
            vibe="Cosmopolitan with a strong cafe and design culture.",
            walkability="High walkability with dense transit coverage.",
            notable_notes=["Lively streets late into the evening.", "Best blocks are easy to cover on foot."],
        ),
        weather=WeatherOutput(
            forecast_summary="Warm days with comfortable evenings.",
            temperature_range="18°C – 26°C",
            conditions="Mostly sunny",
            packing_tips=["Light layers work well.", "Bring one smart casual evening option."],
        ),
        activities=ActivitiesOutput(
            activities=[
                ActivityItem(
                    name="Casa Batllo",
                    description="Architecture walk.",
                    image_url=None,
                    source_url="https://www.casabatllo.es/en/",
                    category="sightseeing",
                )
            ]
        ),
        food=FoodOutput(
            picks=[
                FoodItem(
                    name="Casa Luz",
                    cuisine_type="Modern Tapas",
                    price_range="$$$",
                    description="Rooftop dinner.",
                    image_url=None,
                    source_url="https://www.casaluzrestaurant.com/",
                )
            ]
        ),
        flights=FlightsOutput(
            options=[
                FlightOption(
                    airline="Iberia",
                    departure_time="08:30",
                    arrival_time="10:45",
                    duration_minutes=135,
                    price_usd=210.0,
                    stops=0,
                    seat_class="economy",
                )
            ],
            cheapest_price_usd=210.0,
            search_summary="1 option found, cheapest $210",
        ),
        destination_vibe="cosmopolitan",
    )


class PresentationScoringTest(unittest.TestCase):
    def test_rank_stays_prefers_balanced_value_and_missing_data_stays_sort_last(self) -> None:
        result = _sample_result()
        ranked = rank_stays(result)

        self.assertEqual([item.stay_id for item in ranked], ["stay-1", "stay-2", "stay-3"])
        self.assertGreater(ranked[0].total_score, ranked[1].total_score)
        self.assertLess(ranked[-1].rating_score, ranked[0].rating_score)
        self.assertEqual(ranked[-1].price_score, 0.5)


class StayExtractionTest(unittest.TestCase):
    def test_candidate_from_search_result_populates_coordinates(self) -> None:
        raw_listing = {
            "id": "321",
            "url": "https://www.airbnb.com/rooms/321",
            "demandStayListing": {
                "description": {
                    "name": {
                        "localizedStringWithTranslationPreference": "Airy apartment"
                    }
                },
                "location": {
                    "coordinate": {
                        "latitude": 41.401,
                        "longitude": 2.17,
                    }
                },
            },
            "structuredContent": {
                "primaryLine": "Eixample",
            },
            "avgRatingA11yLabel": "4.9 out of 5 stars",
        }

        candidate = _candidate_from_search_result(raw_listing)

        self.assertEqual(candidate.latitude, 41.401)
        self.assertEqual(candidate.longitude, 2.17)

    def test_reconcile_ranked_stays_retains_validated_coordinates(self) -> None:
        validated_candidate = StayCandidate(
            id="111",
            name="Focused studio with fast wifi",
            price_per_night=110.0,
            total_price=440.0,
            url="https://www.airbnb.com/rooms/111",
            image_urls=[],
            amenities=[],
            location_description="Studio",
            rating=4.92,
            latitude=41.3902,
            longitude=2.1540,
        )
        ranked_candidate = StayCandidate(
            id="111",
            name="Focused studio with fast wifi",
            price_per_night=110.0,
            total_price=440.0,
            url="https://www.airbnb.com/rooms/111",
            image_urls=[],
            amenities=[],
            location_description="Studio",
            rating=4.92,
            latitude=None,
            longitude=None,
        )

        inspection = type(
            "Inspection",
            (),
            {
                "room_id": "111",
                "candidate": validated_candidate,
            },
        )()

        reconciled = _reconcile_ranked_stays([ranked_candidate], [inspection])

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0].latitude, 41.3902)
        self.assertEqual(reconciled[0].longitude, 2.1540)


class StayGeocodingBehaviorTest(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_destination_anchor_tolerates_geocode_failure(self) -> None:
        intake = IntakeOutput(
            destination="Barcelona, Spain",
            trip_type="business",
            check_in="2026-06-09",
            check_out="2026-06-13",
            guests=1,
            budget_per_night=260.0,
            time_preferences="Conference and good tapas",
            origin_airport=None,
        )

        with patch("app.agents.stays.geocode_destination_center", return_value=None):
            anchor = await _resolve_destination_anchor(intake)

        self.assertEqual(anchor.destination, "Barcelona, Spain")
        self.assertIsNone(anchor.latitude)
        self.assertIsNone(anchor.longitude)

    async def test_search_airbnb_uses_full_destination_and_never_sends_place_id(self) -> None:
        intake = IntakeOutput(
            destination="Barcelona, Spain",
            trip_type="business",
            check_in="2026-06-09",
            check_out="2026-06-13",
            guests=1,
            budget_per_night=260.0,
            time_preferences="Conference and good tapas",
            origin_airport=None,
        )
        anchor = type(
            "Anchor",
            (),
            {
                "destination": intake.destination,
                "latitude": 41.3874,
                "longitude": 2.1686,
            },
        )()
        mock_server = type("MockServer", (), {"direct_call_tool": AsyncMock(return_value={})})()

        with patch("app.agents.stays.create_airbnb_mcp_server", return_value=mock_server):
            await _search_airbnb(intake, anchor)

        mock_server.direct_call_tool.assert_awaited_once()
        tool_name, args = mock_server.direct_call_tool.await_args.args
        self.assertEqual(tool_name, "airbnb_search")
        self.assertEqual(args["location"], "Barcelona, Spain")
        self.assertNotIn("placeId", args)

    async def test_run_stays_retries_with_primary_segment_after_zero_validated_results(self) -> None:
        intake = IntakeOutput(
            destination="Barcelona, Spain",
            trip_type="business",
            check_in="2026-06-09",
            check_out="2026-06-13",
            guests=1,
            budget_per_night=260.0,
            time_preferences="Conference and good tapas",
            origin_airport=None,
        )
        first_response = {
            "searchResults": [
                {
                    "id": "999",
                    "url": "https://www.airbnb.com/rooms/999",
                    "demandStayListing": {
                        "description": {"name": {"localizedStringWithTranslationPreference": "Far away stay"}},
                        "location": {"coordinate": {"latitude": 42.22923, "longitude": -8.71908}},
                    },
                    "structuredContent": {"primaryLine": "Barcelona"},
                    "structuredDisplayPrice": {
                        "primaryLine": {"accessibilityLabel": "EUR 220 total"},
                        "explanationData": {"priceDetails": "4 nights x EUR 55.00: EUR 220.00"},
                    },
                    "avgRatingA11yLabel": "4.8 out of 5 average rating, 20 reviews",
                }
            ]
        }
        second_response = {
            "searchResults": [
                {
                    "id": "111",
                    "url": "https://www.airbnb.com/rooms/111",
                    "demandStayListing": {
                        "description": {"name": {"localizedStringWithTranslationPreference": "Validated stay"}},
                        "location": {"coordinate": {"latitude": 41.3875, "longitude": 2.1700}},
                    },
                    "structuredContent": {"primaryLine": "Barcelona"},
                    "structuredDisplayPrice": {
                        "primaryLine": {"accessibilityLabel": "EUR 220 total"},
                        "explanationData": {"priceDetails": "4 nights x EUR 55.00: EUR 220.00"},
                    },
                    "avgRatingA11yLabel": "4.8 out of 5 average rating, 20 reviews",
                }
            ]
        }
        mock_server = type(
            "MockServer",
            (),
            {"direct_call_tool": AsyncMock(side_effect=[first_response, second_response])},
        )()

        with (
            patch("app.agents.stays.create_airbnb_mcp_server", return_value=mock_server),
            patch("app.agents.stays.geocode_destination_center", return_value=(41.3874, 2.1686)),
            patch("app.agents.stays._create_model"),
            patch("app.agents.stays._rank_validated_stays", new=AsyncMock(side_effect=lambda _m, _i, validated: [validated[0].candidate])),
            patch("app.agents.stays.enrich_stays_with_images", new=AsyncMock(side_effect=lambda stays: stays)),
        ):
            result = await run_stays(intake)

        self.assertEqual(len(result.stays), 1)
        self.assertEqual(result.stays[0].id, "111")
        first_call = mock_server.direct_call_tool.await_args_list[0].args[1]
        second_call = mock_server.direct_call_tool.await_args_list[1].args[1]
        self.assertEqual(first_call["location"], "Barcelona, Spain")
        self.assertEqual(second_call["location"], "Barcelona")


class DeckSpecBuilderTest(unittest.TestCase):
    def test_business_deck_places_logistics_early_and_selects_practical_preset(self) -> None:
        result = _sample_result("business")
        deck = build_deck_spec(result)
        style = choose_style_preset(deck, result)

        self.assertEqual(deck.recommended_stay_id, "stay-1")
        self.assertEqual(deck.runner_up_stay_id, "stay-2")
        self.assertEqual(style.name, PRACTICAL_PLANNER.name)
        self.assertEqual([section.id for section in deck.sections[:5]], ["hero", "recommendation", "stay-map", "comparison", "logistics"])
        self.assertNotIn("Fastest commute", [metric.label for metric in deck.key_metrics])
        self.assertTrue(deck.warnings == [] or isinstance(deck.warnings, list))

    def test_romantic_deck_selects_concierge_preset(self) -> None:
        result = _sample_result("romantic")
        deck = build_deck_spec(result)
        style = choose_style_preset(deck, result)

        self.assertEqual(style.name, CONCIERGE_LUXURY.name)

    def test_empty_sections_are_omitted_from_deck(self) -> None:
        result = _sample_result()
        result = result.model_copy(
            update={
                "activities": None,
                "food": None,
                "weather": None,
                "neighborhood": None,
                "flights": None,
            }
        )
        deck = build_deck_spec(result)

        section_ids = [section.id for section in deck.sections]
        self.assertNotIn("activities", section_ids)
        self.assertNotIn("food", section_ids)
        self.assertNotIn("weather", section_ids)
        self.assertNotIn("neighborhood", section_ids)
        self.assertNotIn("flights", section_ids)

    def test_stay_map_section_is_added_with_recommended_marker_flag(self) -> None:
        deck = build_deck_spec(_sample_result())

        stay_map = next(section for section in deck.sections if section.id == "stay-map")
        self.assertEqual(stay_map.type, "stay_map")
        self.assertEqual(len(stay_map.content["markers"]), 3)
        self.assertTrue(any(marker["is_recommended"] for marker in stay_map.content["markers"]))

    def test_stay_map_section_is_omitted_when_no_stays_have_coordinates(self) -> None:
        result = _sample_result().model_copy(
            update={
                "stays": StaysOutput(
                    stays=[
                        stay.model_copy(update={"latitude": None, "longitude": None})
                        for stay in _sample_result().stays.stays
                    ]
                )
            }
        )

        deck = build_deck_spec(result)

        self.assertNotIn("stay-map", [section.id for section in deck.sections])


class PresentationRenderingTest(unittest.IsolatedAsyncioTestCase):
    async def test_renderer_outputs_navigation_summary_and_motion_contract(self) -> None:
        html = await generate_slides(_sample_result())

        self.assertIn('id="hero"', html)
        self.assertIn('id="comparison"', html)
        self.assertIn('id="progress-bar"', html)
        self.assertIn("Jump to booking options", html)
        self.assertIn("prefers-reduced-motion: reduce", html)
        self.assertIn("Recommended", html)
        self.assertIn("data-target=\"comparison\"", html)
        self.assertIn("Visit link", html)
        self.assertIn("casabatllo.es", html)
        self.assertIn("casaluzrestaurant.com", html)
        self.assertIn("leaflet.css", html)
        self.assertIn("leaflet.js", html)
        self.assertIn("stay-map-leaflet", html)
        self.assertIn('"is_recommended": true', html)
        self.assertIn("map.fitBounds(points", html)
        self.assertIn("map.setView(points[0]", html)
        self.assertNotIn("Commute Map", html)

    async def test_renderer_handles_single_marker_map_payload(self) -> None:
        result = _sample_result().model_copy(
            update={
                "stays": StaysOutput(stays=[_sample_result().stays.stays[0]]),
            }
        )

        with patch("app.presentation.deck_spec.geocode_destination_center", return_value=(41.3874, 2.1686)):
            html = await generate_slides(result)

        self.assertIn('"fallback_center": {"latitude": 41.3874, "longitude": 2.1686}', html)
        self.assertIn("Stay map", html)


class FormatterHelpersTest(unittest.TestCase):
    def test_truncate_to_headline_short_text_returns_no_remainder(self) -> None:
        from app.presentation.formatters import truncate_to_headline

        headline, remainder = truncate_to_headline("Safe and quiet area.")
        self.assertEqual(headline, "Safe and quiet area.")
        self.assertIsNone(remainder)

    def test_truncate_to_headline_splits_on_first_sentence(self) -> None:
        from app.presentation.formatters import truncate_to_headline

        text = "Generally safe. The streets are well-lit and there is regular foot traffic. Avoid the outskirts late at night."
        headline, remainder = truncate_to_headline(text)
        self.assertEqual(headline, "Generally safe.")
        self.assertIsNotNone(remainder)
        self.assertIn("well-lit", remainder)

    def test_truncate_to_headline_caps_long_single_sentence(self) -> None:
        from app.presentation.formatters import truncate_to_headline

        long_text = " ".join(["word"] * 40)
        headline, remainder = truncate_to_headline(long_text, max_words=10)
        self.assertTrue(headline.endswith("\u2026"))
        self.assertIsNotNone(remainder)

    def test_inline_svg_icon_returns_svg_for_known_names(self) -> None:
        from app.presentation.formatters import inline_svg_icon

        for name in ("shield", "sparkles", "walking", "plane", "dollar", "layers"):
            svg = inline_svg_icon(name)
            self.assertIn("<svg", svg, f"Expected SVG for icon '{name}'")

    def test_inline_svg_icon_returns_empty_for_unknown(self) -> None:
        from app.presentation.formatters import inline_svg_icon

        self.assertEqual(inline_svg_icon("nonexistent"), "")


class CardGridRenderingTest(unittest.IsolatedAsyncioTestCase):
    async def test_comparison_renders_all_stays_as_cards_with_images(self) -> None:
        html = await generate_slides(_sample_result())

        # All 3 stays should appear in the comparison card grid
        self.assertIn("Focused studio with fast wifi", html)
        self.assertIn("Design loft with terrace", html)
        self.assertIn("Budget city room", html)
        # Image should be present for stays that have one
        self.assertIn("stay-1.jpg", html)
        self.assertIn("stay-2.jpg", html)
        # Card grid class should be used
        self.assertIn("stay-card", html)

    async def test_neighborhood_renders_with_icons_and_truncation(self) -> None:
        html = await generate_slides(_sample_result())

        # SVG icons should be present
        self.assertIn("icon-inline", html)
        # Section headings
        self.assertIn("Safety", html)
        self.assertIn("Vibe", html)
        self.assertIn("Walkability", html)

    async def test_logistics_renders_structured_flight_stats(self) -> None:
        html = await generate_slides(_sample_result())

        self.assertIn("flight-stats", html)
        self.assertIn("Iberia", html)
        self.assertIn("Non-stop", html)
        self.assertIn("$210", html)

    async def test_summary_rail_shows_trip_at_a_glance(self) -> None:
        html = await generate_slides(_sample_result())

        self.assertIn("Trip at a glance", html)
        self.assertNotIn("Quick brief", html)
        self.assertIn("rail-metric", html)


if __name__ == "__main__":
    unittest.main()
