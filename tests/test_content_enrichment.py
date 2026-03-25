import unittest

from app.agents.slides import generate_slides
from app.content_enrichment import (
    extract_image_url_from_html,
    normalize_activities_output,
    normalize_food_output,
)
from app.schemas import (
    ActivitiesOutput,
    ActivityItem,
    CurationOutput,
    FoodItem,
    FoodOutput,
)


class ContentEnrichmentTest(unittest.TestCase):
    def test_extracts_og_image(self) -> None:
        html = """
        <html><head>
          <meta property="og:image" content="https://cdn.example.com/hero.jpg">
        </head></html>
        """
        image_url = extract_image_url_from_html("https://example.com/place", html)
        self.assertEqual(image_url, "https://cdn.example.com/hero.jpg")

    def test_extracts_twitter_image_when_og_missing(self) -> None:
        html = """
        <html><head>
          <meta name="twitter:image" content="https://cdn.example.com/twitter.jpg">
        </head></html>
        """
        image_url = extract_image_url_from_html("https://example.com/place", html)
        self.assertEqual(image_url, "https://cdn.example.com/twitter.jpg")

    def test_extracts_json_ld_relative_image(self) -> None:
        html = """
        <html><head>
          <script type="application/ld+json">
            {
              "@context": "https://schema.org",
              "@type": "Restaurant",
              "image": "/assets/dining-room.jpg"
            }
          </script>
        </head></html>
        """
        image_url = extract_image_url_from_html("https://example.com/restaurants/casa-luz", html)
        self.assertEqual(image_url, "https://example.com/assets/dining-room.jpg")

    def test_extracts_link_image_src_when_other_metadata_missing(self) -> None:
        html = """
        <html><head>
          <link rel="image_src" href="https://cdn.example.com/gallery.jpg">
        </head></html>
        """
        image_url = extract_image_url_from_html("https://example.com/place", html)
        self.assertEqual(image_url, "https://cdn.example.com/gallery.jpg")

    def test_returns_none_when_no_valid_image_exists(self) -> None:
        html = "<html><head><title>No metadata</title></head></html>"
        image_url = extract_image_url_from_html("https://example.com/place", html)
        self.assertIsNone(image_url)

    def test_rejects_logo_like_assets(self) -> None:
        html = """
        <html><head>
          <meta property="og:image" content="https://cdn.example.com/static/logo.png">
        </head></html>
        """
        image_url = extract_image_url_from_html("https://example.com/place", html)
        self.assertIsNone(image_url)

    def test_normalize_activities_drops_unlinked_when_enough_linked_exist(self) -> None:
        linked = [
            ActivityItem(
                name=f"Linked {index}",
                description="desc",
                image_url=None,
                source_url=f"https://example.com/activity-{index}",
                category="sightseeing",
            )
            for index in range(6)
        ]
        output = ActivitiesOutput(
            activities=linked + [
                ActivityItem(
                    name="Missing source",
                    description="desc",
                    image_url=None,
                    source_url=None,
                    category="sightseeing",
                )
            ]
        )

        normalized = normalize_activities_output(output)
        self.assertEqual(len(normalized.activities), 6)
        self.assertTrue(all(item.source_url for item in normalized.activities))

    def test_normalize_food_dedupes_duplicate_urls_and_names(self) -> None:
        output = FoodOutput(
            picks=[
                FoodItem(
                    name="Casa Luz",
                    cuisine_type="Modern Tapas",
                    price_range="$$$",
                    description="desc",
                    image_url=None,
                    source_url="https://example.com/casa-luz?ref=search",
                ),
                FoodItem(
                    name="Casa Luz",
                    cuisine_type="Modern Tapas",
                    price_range="$$$",
                    description="desc",
                    image_url=None,
                    source_url="https://example.com/another-casa-luz",
                ),
                FoodItem(
                    name="El Nacional",
                    cuisine_type="Spanish",
                    price_range="$$",
                    description="desc",
                    image_url=None,
                    source_url="not-a-url",
                ),
                FoodItem(
                    name="Paco Meralgo",
                    cuisine_type="Tapas",
                    price_range="$$",
                    description="desc",
                    image_url=None,
                    source_url="https://example.com/paco-meralgo",
                ),
            ]
        )

        normalized = normalize_food_output(output)
        self.assertEqual([item.name for item in normalized.picks], ["Casa Luz", "Paco Meralgo", "El Nacional"])
        self.assertEqual(normalized.picks[0].source_url, "https://example.com/casa-luz?ref=search")
        self.assertIsNone(normalized.picks[-1].source_url)


class SlidesRenderingTest(unittest.IsolatedAsyncioTestCase):
    async def test_activity_and_food_cards_render_source_links(self) -> None:
        result = CurationOutput(
            destination="Barcelona, Spain",
            trip_type="business",
            dates="June 9–13, 2026",
            guests=1,
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
            destination_vibe="cosmopolitan",
        )

        html = await generate_slides(result)
        self.assertIn("Visit link", html)
        self.assertIn("casabatllo.es", html)
        self.assertIn("casaluzrestaurant.com", html)


if __name__ == "__main__":
    unittest.main()
