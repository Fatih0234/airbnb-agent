from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.activity_search import (
    MODEL_CANDIDATE_LIMIT,
    build_activity_search_queries,
    collect_activity_candidates,
    dedupe_and_limit_activity_candidates,
    extract_activity_candidates,
)
from app.agents import activities
from app.schemas import ActivitiesOutput, ActivityItem, IntakeOutput


def _intake() -> IntakeOutput:
    return IntakeOutput(
        destination="Mexico City, Mexico",
        trip_type="event_based",
        check_in="2026-09-03",
        check_out="2026-09-07",
        guests=2,
        budget_per_night=230.0,
        time_preferences=(
            "Long weekend built around a major Saturday night concert, so prioritize great coffee, "
            "standout taco spots, one contemporary Mexican dinner, one art-heavy afternoon, "
            "and daytime plans that feel energizing."
        ),
        origin_airport="MIA",
    )


class ActivitySearchQueryTest(unittest.TestCase):
    def test_build_queries_caps_at_two_and_prefers_activity_phrases(self) -> None:
        queries = build_activity_search_queries(
            "Mexico City, Mexico",
            "event_based",
            _intake().time_preferences,
        )

        self.assertLessEqual(len(queries), 2)
        self.assertIn("Mexico City, Mexico", queries[0])
        self.assertTrue(any("concert" in query or "art" in query or "coffee" in query for query in queries))


class ActivityCandidateExtractionTest(unittest.TestCase):
    def test_extract_candidates_from_tavily_text_blob(self) -> None:
        candidates = extract_activity_candidates(
            """Detailed Results:

Title: Museo Jumex | Contemporary Art Museum
URL: https://www.fundacionjumex.org/en
Content: Contemporary art museum with rotating exhibitions in Polanco.

Title: Lago Algo
URL: https://www.lago-algo.mx/
Content: Lakefront cultural space with exhibitions and coffee.
""",
            query="best things to do in Mexico City art-heavy afternoon",
            query_index=0,
        )

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["name"], "Museo Jumex")
        self.assertEqual(candidates[1]["category"], "cultural")

    def test_extract_candidates_from_tavily_results(self) -> None:
        candidates = extract_activity_candidates(
            {
                "results": [
                    {
                        "title": "Museo Jumex | Contemporary Art Museum",
                        "url": "https://www.fundacionjumex.org/en",
                        "content": "Contemporary art museum with rotating exhibitions in Polanco.",
                    }
                ]
            },
            query="best things to do in Mexico City art-heavy afternoon",
            query_index=0,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["name"], "Museo Jumex")
        self.assertEqual(candidates[0]["category"], "cultural")
        self.assertEqual(candidates[0]["source_url"], "https://www.fundacionjumex.org/en")

    def test_dedupe_by_url_and_name_and_limit_candidates(self) -> None:
        candidates = [
            {
                "name": "Museo Jumex",
                "description": "Contemporary art museum.",
                "source_url": "https://example.com/jumex?ref=1",
                "category": "cultural",
                "image_url": None,
                "query": "art in mexico city",
                "query_index": 0,
                "result_index": 0,
            },
            {
                "name": "Museo Jumex",
                "description": "Art museum duplicate name.",
                "source_url": "https://example.com/another-jumex",
                "category": "cultural",
                "image_url": None,
                "query": "museum mexico city",
                "query_index": 1,
                "result_index": 0,
            },
            {
                "name": "Casa Taco",
                "description": "Late lunch tacos.",
                "source_url": "https://example.com/tacos",
                "category": "food",
                "image_url": None,
                "query": "tacos mexico city",
                "query_index": 0,
                "result_index": 1,
            },
            {
                "name": "Casa Taco Alt",
                "description": "Duplicate URL.",
                "source_url": "https://example.com/tacos",
                "category": "food",
                "image_url": None,
                "query": "food mexico city",
                "query_index": 1,
                "result_index": 1,
            },
        ]

        deduped = dedupe_and_limit_activity_candidates(candidates, limit=MODEL_CANDIDATE_LIMIT)

        self.assertEqual([candidate["name"] for candidate in deduped], ["Museo Jumex", "Casa Taco"])

    def test_limit_is_enforced_before_model(self) -> None:
        candidates = [
            {
                "name": f"Candidate {index}",
                "description": "desc",
                "source_url": f"https://example.com/{index}",
                "category": "sightseeing",
                "image_url": None,
                "query": "top attractions mexico city",
                "query_index": index % 2,
                "result_index": index,
            }
            for index in range(MODEL_CANDIDATE_LIMIT + 4)
        ]

        limited = dedupe_and_limit_activity_candidates(candidates, limit=MODEL_CANDIDATE_LIMIT)
        self.assertEqual(len(limited), MODEL_CANDIDATE_LIMIT)


class ActivityCollectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_candidates_gracefully_handles_tavily_failure(self) -> None:
        with patch("app.activity_search._search_activities", new=AsyncMock(return_value=None)):
            candidates, metadata = await collect_activity_candidates(
                destination="Mexico City, Mexico",
                trip_type="event_based",
                time_preferences="concert weekend and art museums",
            )

        self.assertEqual(candidates, [])
        self.assertGreaterEqual(metadata["failed_queries"], 1)

    async def test_collect_candidates_merges_multiple_queries(self) -> None:
        with patch(
            "app.activity_search._search_activities",
            new=AsyncMock(
                side_effect=[
                    {
                        "results": [
                            {
                                "title": "Museo Jumex | Contemporary Art Museum",
                                "url": "https://www.fundacionjumex.org/en",
                                "content": "Contemporary art museum in Polanco.",
                            }
                        ]
                    },
                    {
                        "results": [
                            {
                                "title": "Lago Algo",
                                "url": "https://www.lago-algo.mx/",
                                "content": "Lakefront cultural space with exhibitions and coffee.",
                            }
                        ]
                    },
                ]
            ),
        ):
            candidates, metadata = await collect_activity_candidates(
                destination="Mexico City, Mexico",
                trip_type="event_based",
                time_preferences="art-heavy afternoon and great coffee",
            )

        self.assertEqual(len(candidates), 2)
        self.assertEqual(metadata["query_count"], 2)


class ActivityAgentIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_activities_returns_empty_output_without_model_when_no_candidates(self) -> None:
        with patch(
            "app.agents.activities.collect_activity_candidates",
            new=AsyncMock(return_value=([], {"model_candidate_count": 0})),
        ), patch("app.agents.activities.Agent") as agent_cls:
            output = await activities.run_activities(_intake())

        self.assertEqual(output, ActivitiesOutput(activities=[]))
        agent_cls.assert_not_called()

    async def test_run_activities_uses_tool_less_model_on_precomputed_candidates(self) -> None:
        agent_instance = MagicMock()
        agent_instance.__aenter__ = AsyncMock(return_value=agent_instance)
        agent_instance.__aexit__ = AsyncMock(return_value=None)
        agent_instance.run = AsyncMock(
            return_value=SimpleNamespace(
                output=ActivitiesOutput(
                    activities=[
                        ActivityItem(
                            name="Museo Jumex",
                            description="Strong contemporary art pick.",
                            image_url=None,
                            source_url="https://www.fundacionjumex.org/en",
                            category="cultural",
                        )
                    ]
                )
            )
        )

        with patch(
            "app.agents.activities.collect_activity_candidates",
            new=AsyncMock(
                return_value=(
                    [
                        {
                            "name": "Museo Jumex",
                            "description": "Contemporary art museum in Polanco.",
                            "source_url": "https://www.fundacionjumex.org/en",
                            "category": "cultural",
                            "image_url": None,
                        }
                    ],
                    {"query_count": 1, "model_candidate_count": 1},
                )
            ),
        ), patch("app.agents.activities.get_minimax_api_key", return_value="test-key"), patch(
            "app.agents.activities.get_fast_model_name",
            return_value="test-model",
        ), patch(
            "app.agents.activities.AnthropicModel",
            return_value=object(),
        ), patch(
            "app.agents.activities.Agent",
            return_value=agent_instance,
        ) as agent_cls:
            output = await activities.run_activities(_intake())

        self.assertEqual(len(output.activities), 1)
        self.assertNotIn("toolsets", agent_cls.call_args.kwargs)
        usage_limits = agent_instance.run.call_args.kwargs["usage_limits"]
        self.assertEqual(usage_limits.request_limit, activities.MODEL_REQUEST_LIMIT)
        prompt = agent_instance.run.call_args.args[0]
        self.assertIn("Candidate activities", prompt)
        self.assertIn("Museo Jumex", prompt)


if __name__ == "__main__":
    unittest.main()
