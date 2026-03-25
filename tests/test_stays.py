import unittest

from app.agents.stays import (
    DESTINATION_RADIUS_KM,
    DestinationAnchor,
    ListingInspection,
    _airbnb_location_query,
    _inspect_search_result,
    _reconcile_ranked_stays,
)
from app.schemas import IntakeOutput, StayCandidate


def _raw_listing(
    *,
    room_id: str,
    name: str,
    lat: float | None,
    lng: float | None,
    url: str | None = None,
    location_bits: tuple[str, str, str] = ("", "", ""),
) -> dict:
    coordinate = {}
    if lat is not None:
        coordinate["latitude"] = lat
    if lng is not None:
        coordinate["longitude"] = lng

    return {
        "id": room_id,
        "url": url or f"https://www.airbnb.com/rooms/{room_id}",
        "demandStayListing": {
            "description": {
                "name": {
                    "localizedStringWithTranslationPreference": name,
                }
            },
            "location": {
                "coordinate": coordinate,
            },
        },
        "structuredContent": {
            "mapSecondaryLine": location_bits[0],
            "primaryLine": location_bits[1],
            "secondaryLine": location_bits[2],
        },
        "structuredDisplayPrice": {
            "primaryLine": {"accessibilityLabel": "EUR 220 total"},
            "explanationData": {"priceDetails": "4 nights x EUR 55.00: EUR 220.00"},
        },
        "avgRatingA11yLabel": "4.8 out of 5 average rating, 20 reviews",
    }


class StaysHelpersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.intake = IntakeOutput(
            destination="Barcelona, Spain",
            trip_type="business",
            check_in="2026-06-09",
            check_out="2026-06-13",
            guests=1,
            budget_per_night=260,
            time_preferences="Conference during the day.",
            origin_airport="Amsterdam",
        )
        self.anchor = DestinationAnchor(
            destination=self.intake.destination,
            latitude=41.3874374,
            longitude=2.1686496,
        )

    def test_airbnb_query_uses_full_destination_text(self) -> None:
        anchored = _airbnb_location_query(self.intake, self.anchor)
        self.assertEqual(anchored, "Barcelona, Spain")

        no_coords_anchor = DestinationAnchor(
            destination=self.intake.destination,
            latitude=None,
            longitude=None,
        )
        fallback = _airbnb_location_query(self.intake, no_coords_anchor)
        self.assertEqual(fallback, "Barcelona, Spain")

    def test_coordinate_validation_accepts_barcelona_and_rejects_vigo(self) -> None:
        barcelona_listing = _raw_listing(
            room_id="111",
            name="Plaça Espanya studio",
            lat=41.3707,
            lng=2.1446,
            location_bits=("Barcelona", "1 bed", "Business host"),
        )
        vigo_listing = _raw_listing(
            room_id="222",
            name="Vigo apartment",
            lat=42.22923,
            lng=-8.71908,
            location_bits=("Barcelona", "1 bed", "Business host"),
        )

        accepted = _inspect_search_result(barcelona_listing, self.intake, self.anchor)
        rejected = _inspect_search_result(vigo_listing, self.intake, self.anchor)

        self.assertTrue(accepted.accepted)
        self.assertEqual(accepted.reason, "within_radius")
        self.assertEqual(accepted.candidate.id, "111")
        self.assertIsNotNone(accepted.distance_km)
        self.assertLessEqual(accepted.distance_km, DESTINATION_RADIUS_KM)

        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.reason, "outside_radius")
        self.assertIsNotNone(rejected.distance_km)
        self.assertGreater(rejected.distance_km, DESTINATION_RADIUS_KM)

    def test_text_fallback_only_applies_when_coordinates_missing(self) -> None:
        no_coords_listing = _raw_listing(
            room_id="333",
            name="Barcelona business room",
            lat=None,
            lng=None,
            location_bits=("Barcelona", "1 bed", "Business host"),
        )
        wrong_city_with_barcelona_text = _raw_listing(
            room_id="444",
            name="Barcelona titled but actually Vigo",
            lat=42.22923,
            lng=-8.71908,
            location_bits=("Barcelona", "1 bed", "Business host"),
        )

        fallback_match = _inspect_search_result(no_coords_listing, self.intake, self.anchor)
        coord_reject = _inspect_search_result(wrong_city_with_barcelona_text, self.intake, self.anchor)

        self.assertTrue(fallback_match.accepted)
        self.assertEqual(fallback_match.reason, "text_match")
        self.assertIsNone(fallback_match.distance_km)

        self.assertFalse(coord_reject.accepted)
        self.assertEqual(coord_reject.reason, "outside_radius")

    def test_reconcile_ranked_stays_drops_invented_urls(self) -> None:
        validated = [
            ListingInspection(
                room_id="111",
                candidate=StayCandidate(
                    id="111",
                    name="Validated stay",
                    price_per_night=55,
                    total_price=220,
                    url="https://www.airbnb.com/rooms/111",
                    image_urls=[],
                    amenities=[],
                    location_description="Barcelona",
                    rating=4.8,
                ),
                latitude=41.38,
                longitude=2.17,
                distance_km=1.2,
                accepted=True,
                reason="within_radius",
            )
        ]
        ranked = [
            StayCandidate(
                id="999",
                name="Invented stay",
                price_per_night=10,
                total_price=40,
                url="https://www.airbnb.com/rooms/999",
                image_urls=[],
                amenities=[],
                location_description="Nowhere",
                rating=5.0,
            ),
            StayCandidate(
                id="111",
                name="Validated stay",
                price_per_night=55,
                total_price=220,
                url="https://www.airbnb.com/rooms/111",
                image_urls=[],
                amenities=[],
                location_description="Barcelona",
                rating=4.8,
            ),
        ]

        reconciled = _reconcile_ranked_stays(ranked, validated)
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0].id, "111")
        self.assertEqual(reconciled[0].url, "https://www.airbnb.com/rooms/111")


if __name__ == "__main__":
    unittest.main()
