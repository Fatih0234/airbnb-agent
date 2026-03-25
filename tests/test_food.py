from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents import food
from app.food_search import (
    MODEL_CANDIDATE_LIMIT,
    build_food_search_queries,
    collect_food_candidates,
    dedupe_and_limit_food_candidates,
    extract_food_candidates,
)
from app.schemas import FoodItem, FoodOutput, IntakeOutput


def _intake() -> IntakeOutput:
    return IntakeOutput(
        destination="Paris, France",
        trip_type="romantic",
        check_in="2026-05-14",
        check_out="2026-05-18",
        guests=2,
        budget_per_night=320.0,
        time_preferences=(
            "Romantic dinner, great pastry stops, cozy wine bar, and one strong market lunch."
        ),
        origin_airport="JFK",
    )


class FoodSearchQueryTest(unittest.TestCase):
    def test_build_queries_caps_at_two_and_prefers_food_phrases(self) -> None:
        queries = build_food_search_queries(
            "Paris, France",
            "romantic",
            _intake().time_preferences,
        )

        self.assertLessEqual(len(queries), 2)
        self.assertIn("Paris, France", queries[0])
        self.assertTrue(any("dinner" in query or "wine" in query or "pastry" in query for query in queries))


class FoodCandidateExtractionTest(unittest.TestCase):
    def test_extract_candidates_from_tavily_text_blob(self) -> None:
        candidates = extract_food_candidates(
            """Detailed Results:

Title: Septime | Paris restaurant
URL: https://www.septime-charonne.fr/
Content: Michelin-recognized contemporary French restaurant with tasting menu.

Title: Folderol
URL: https://www.folderol.com/
Content: Natural wine bar with excellent ice cream and late-night energy.
""",
            query="best restaurants in Paris romantic dinner",
            query_index=0,
        )

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["name"], "Septime")
        self.assertEqual(candidates[0]["cuisine_type"], "French")
        self.assertEqual(candidates[0]["price_range"], "$$$")
        self.assertEqual(candidates[1]["cuisine_type"], "Bar")

    def test_extract_candidates_from_tavily_results(self) -> None:
        candidates = extract_food_candidates(
            {
                "results": [
                    {
                        "title": "Ten Belles Bread | Paris cafe",
                        "url": "https://www.tenbelles.com/",
                        "content": "Specialty coffee, pastries, and sandwiches near Canal Saint-Martin.",
                    }
                ]
            },
            query="best restaurants in Paris great pastry stops",
            query_index=0,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["name"], "Ten Belles Bread")
        self.assertEqual(candidates[0]["cuisine_type"], "Cafe")
        self.assertEqual(candidates[0]["price_range"], "$$")
        self.assertEqual(candidates[0]["source_url"], "https://www.tenbelles.com/")

    def test_dedupe_by_url_and_name_and_limit_candidates(self) -> None:
        candidates = [
            {
                "name": "Septime",
                "cuisine_type": "French",
                "price_range": "$$$",
                "description": "Contemporary French tasting menu.",
                "image_url": None,
                "source_url": "https://example.com/septime?ref=1",
                "query": "paris romantic dinner",
                "query_index": 0,
                "result_index": 0,
            },
            {
                "name": "Septime",
                "cuisine_type": "French",
                "price_range": "$$$",
                "description": "Duplicate venue with a different URL.",
                "image_url": None,
                "source_url": "https://example.com/another-septime",
                "query": "paris best restaurants",
                "query_index": 1,
                "result_index": 0,
            },
            {
                "name": "Folderol",
                "cuisine_type": "Bar",
                "price_range": "$$",
                "description": "Wine bar and ice cream shop.",
                "image_url": None,
                "source_url": "https://example.com/folderol",
                "query": "paris wine bar",
                "query_index": 0,
                "result_index": 1,
            },
            {
                "name": "Folderol Alt",
                "cuisine_type": "Bar",
                "price_range": "$$",
                "description": "Duplicate URL.",
                "image_url": None,
                "source_url": "https://example.com/folderol",
                "query": "paris late night food",
                "query_index": 1,
                "result_index": 1,
            },
        ]

        deduped = dedupe_and_limit_food_candidates(candidates, limit=MODEL_CANDIDATE_LIMIT)

        self.assertCountEqual([candidate["name"] for candidate in deduped], ["Septime", "Folderol"])

    def test_limit_is_enforced_before_model(self) -> None:
        candidates = [
            {
                "name": f"Candidate {index}",
                "cuisine_type": "Restaurant",
                "price_range": "$$",
                "description": "desc",
                "image_url": None,
                "source_url": f"https://example.com/{index}",
                "query": "best restaurants in paris",
                "query_index": index % 2,
                "result_index": index,
            }
            for index in range(MODEL_CANDIDATE_LIMIT + 4)
        ]

        limited = dedupe_and_limit_food_candidates(candidates, limit=MODEL_CANDIDATE_LIMIT)
        self.assertEqual(len(limited), MODEL_CANDIDATE_LIMIT)


class FoodCollectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_candidates_gracefully_handles_tavily_failure(self) -> None:
        with patch("app.food_search._search_food", new=AsyncMock(return_value=None)):
            candidates, metadata = await collect_food_candidates(
                destination="Paris, France",
                trip_type="romantic",
                time_preferences="romantic dinner and pastry stops",
            )

        self.assertEqual(candidates, [])
        self.assertGreaterEqual(metadata["failed_queries"], 1)

    async def test_collect_candidates_merges_multiple_queries(self) -> None:
        with patch(
            "app.food_search._search_food",
            new=AsyncMock(
                side_effect=[
                    {
                        "results": [
                            {
                                "title": "Septime | Paris restaurant",
                                "url": "https://www.septime-charonne.fr/",
                                "content": "Contemporary French restaurant with tasting menu.",
                            }
                        ]
                    },
                    {
                        "results": [
                            {
                                "title": "Ten Belles Bread | Paris cafe",
                                "url": "https://www.tenbelles.com/",
                                "content": "Coffee, pastries, and a strong breakfast stop.",
                            }
                        ]
                    },
                ]
            ),
        ):
            candidates, metadata = await collect_food_candidates(
                destination="Paris, France",
                trip_type="romantic",
                time_preferences="romantic dinner and great pastry stops",
            )

        self.assertEqual(len(candidates), 2)
        self.assertEqual(metadata["query_count"], 2)


class FoodAgentIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_food_returns_empty_output_without_model_when_no_candidates(self) -> None:
        with patch(
            "app.agents.food.collect_food_candidates",
            new=AsyncMock(return_value=([], {"model_candidate_count": 0})),
        ), patch("app.agents.food.Agent") as agent_cls:
            output = await food.run_food(_intake())

        self.assertEqual(output, FoodOutput(picks=[]))
        agent_cls.assert_not_called()

    async def test_run_food_uses_tool_less_model_on_precomputed_candidates(self) -> None:
        agent_instance = MagicMock()
        agent_instance.__aenter__ = AsyncMock(return_value=agent_instance)
        agent_instance.__aexit__ = AsyncMock(return_value=None)
        agent_instance.run = AsyncMock(
            return_value=SimpleNamespace(
                output=FoodOutput(
                    picks=[
                        FoodItem(
                            name="Septime",
                            cuisine_type="French",
                            price_range="$$$",
                            description="Top romantic tasting-menu choice.",
                            image_url=None,
                            source_url="https://www.septime-charonne.fr/",
                        )
                    ]
                )
            )
        )

        with patch(
            "app.agents.food.collect_food_candidates",
            new=AsyncMock(
                return_value=(
                    [
                        {
                            "name": "Septime",
                            "cuisine_type": "French",
                            "price_range": "$$$",
                            "description": "Contemporary French restaurant with tasting menu.",
                            "image_url": None,
                            "source_url": "https://www.septime-charonne.fr/",
                        }
                    ],
                    {"query_count": 1, "model_candidate_count": 1},
                )
            ),
        ), patch("app.agents.food.get_minimax_api_key", return_value="test-key"), patch(
            "app.agents.food.get_fast_model_name",
            return_value="test-model",
        ), patch(
            "app.agents.food.AnthropicModel",
            return_value=object(),
        ), patch(
            "app.agents.food.Agent",
            return_value=agent_instance,
        ) as agent_cls:
            output = await food.run_food(_intake())

        self.assertEqual(len(output.picks), 1)
        self.assertNotIn("toolsets", agent_cls.call_args.kwargs)
        usage_limits = agent_instance.run.call_args.kwargs["usage_limits"]
        self.assertEqual(usage_limits.request_limit, food.MODEL_REQUEST_LIMIT)
        prompt = agent_instance.run.call_args.args[0]
        self.assertIn("Candidate food picks", prompt)
        self.assertIn("Septime", prompt)

    async def test_run_food_propagates_model_failures(self) -> None:
        agent_instance = MagicMock()
        agent_instance.__aenter__ = AsyncMock(return_value=agent_instance)
        agent_instance.__aexit__ = AsyncMock(return_value=None)
        agent_instance.run = AsyncMock(side_effect=RuntimeError("model unavailable"))

        with patch(
            "app.agents.food.collect_food_candidates",
            new=AsyncMock(
                return_value=(
                    [
                        {
                            "name": "Folderol",
                            "cuisine_type": "Bar",
                            "price_range": "$$",
                            "description": "Wine bar with dessert.",
                            "image_url": None,
                            "source_url": "https://www.folderol.com/",
                        }
                    ],
                    {"query_count": 1, "model_candidate_count": 1},
                )
            ),
        ), patch("app.agents.food.get_minimax_api_key", return_value="test-key"), patch(
            "app.agents.food.get_fast_model_name",
            return_value="test-model",
        ), patch(
            "app.agents.food.AnthropicModel",
            return_value=object(),
        ), patch(
            "app.agents.food.Agent",
            return_value=agent_instance,
        ):
            with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                await food.run_food(_intake())


if __name__ == "__main__":
    unittest.main()
