import unittest
from unittest.mock import AsyncMock, patch

from app.agents.neighborhood import run_neighborhood
from app.neighborhood_search import (
    EVIDENCE_PER_TOPIC_LIMIT,
    TOTAL_EVIDENCE_LIMIT,
    SAFETY_AREA_FIT_TOPIC,
    WALKABILITY_CAVEATS_TOPIC,
    build_neighborhood_search_queries,
    collect_neighborhood_evidence,
    dedupe_and_limit_neighborhood_evidence,
    extract_neighborhood_evidence,
)
from app.schemas import IntakeOutput, NeighborhoodOutput


def _sample_intake() -> IntakeOutput:
    return IntakeOutput(
        destination="Lisbon, Portugal",
        trip_type="business",
        check_in="2026-06-09",
        check_out="2026-06-13",
        guests=1,
        budget_per_night=250.0,
        time_preferences="Quiet blocks, easy transit, good coffee",
        origin_airport=None,
    )


def _empty_payload() -> dict[str, object]:
    return {
        "queries": build_neighborhood_search_queries("Lisbon, Portugal", "business"),
        "query_count": 2,
        "failed_queries": 2,
        "raw_result_count": 0,
        "extracted_evidence_count": 0,
        "evidence_count": 0,
        "evidence_by_topic": {
            SAFETY_AREA_FIT_TOPIC: [],
            WALKABILITY_CAVEATS_TOPIC: [],
        },
    }


class NeighborhoodSearchQueryTest(unittest.TestCase):
    def test_build_neighborhood_search_queries_returns_two_fixed_queries(self) -> None:
        queries = build_neighborhood_search_queries("Lisbon, Portugal", "weekend_getaway")

        self.assertEqual(
            queries,
            [
                {
                    "topic": SAFETY_AREA_FIT_TOPIC,
                    "query": "Lisbon, Portugal neighborhood safety area fit best areas for weekend getaway travelers",
                },
                {
                    "topic": WALKABILITY_CAVEATS_TOPIC,
                    "query": "Lisbon, Portugal walkability public transit hills noise practical caveats",
                },
            ],
        )


class NeighborhoodEvidenceExtractionTest(unittest.TestCase):
    def test_extract_neighborhood_evidence_ignores_malformed_results_and_tags_metadata(self) -> None:
        search_result = {
            "results": [
                {
                    "title": "Chiado guide | Local Lens",
                    "url": "https://www.example.com/chiado#overview",
                    "content": "Central and lively, with a strong cafe culture and heavy foot traffic.",
                },
                {
                    "title": "Missing URL",
                    "content": "Should be ignored.",
                },
                {
                    "title": "   ",
                    "url": "https://www.example.com/no-text",
                },
                {
                    "url": "https://city.example.com/walkability",
                    "snippet": "Hilly streets can slow luggage-heavy trips, but transit coverage is strong.",
                },
            ]
        }

        evidence = extract_neighborhood_evidence(
            search_result,
            topic=SAFETY_AREA_FIT_TOPIC,
            query="Lisbon, Portugal neighborhood safety area fit best areas for business travelers",
            query_index=0,
        )

        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence[0]["title"], "Chiado guide")
        self.assertEqual(evidence[0]["url"], "https://www.example.com/chiado")
        self.assertEqual(evidence[0]["source_domain"], "example.com")
        self.assertEqual(evidence[0]["topic"], SAFETY_AREA_FIT_TOPIC)
        self.assertEqual(evidence[0]["query_index"], 0)
        self.assertEqual(evidence[0]["result_index"], 0)
        self.assertIn("foot traffic", evidence[0]["snippet"])

        self.assertEqual(
            evidence[1]["title"],
            "Hilly streets can slow luggage-heavy trips, but transit coverage is strong.",
        )
        self.assertEqual(evidence[1]["result_index"], 3)

    def test_dedupe_and_limit_neighborhood_evidence_bounds_payload(self) -> None:
        evidence = [
            {
                "title": f"Safety item {index}",
                "url": f"https://safety.example.com/{index}",
                "snippet": "Well-trafficked blocks.",
                "source_domain": "safety.example.com",
                "topic": SAFETY_AREA_FIT_TOPIC,
                "query": "safety query",
                "query_index": 0,
                "result_index": index,
            }
            for index in range(EVIDENCE_PER_TOPIC_LIMIT + 2)
        ]
        evidence.extend(
            [
                {
                    "title": "Safety item 0",
                    "url": "https://duplicate.example.com/same-title",
                    "snippet": "Duplicate by title.",
                    "source_domain": "duplicate.example.com",
                    "topic": WALKABILITY_CAVEATS_TOPIC,
                    "query": "walkability query",
                    "query_index": 1,
                    "result_index": 0,
                },
                {
                    "title": "Walkability item 1",
                    "url": "https://walk.example.com/shared",
                    "snippet": "Duplicate by url.",
                    "source_domain": "walk.example.com",
                    "topic": WALKABILITY_CAVEATS_TOPIC,
                    "query": "walkability query",
                    "query_index": 1,
                    "result_index": 1,
                },
                {
                    "title": "Walkability item 2",
                    "url": "https://walk.example.com/shared",
                    "snippet": "Same url should collapse.",
                    "source_domain": "walk.example.com",
                    "topic": WALKABILITY_CAVEATS_TOPIC,
                    "query": "walkability query",
                    "query_index": 1,
                    "result_index": 2,
                },
            ]
        )
        evidence.extend(
            [
                {
                    "title": f"Walkability unique {index}",
                    "url": f"https://walk.example.com/{index}",
                    "snippet": "Some hills and transit notes.",
                    "source_domain": "walk.example.com",
                    "topic": WALKABILITY_CAVEATS_TOPIC,
                    "query": "walkability query",
                    "query_index": 1,
                    "result_index": index + 3,
                }
                for index in range(EVIDENCE_PER_TOPIC_LIMIT + 2)
            ]
        )

        bounded = dedupe_and_limit_neighborhood_evidence(evidence)
        total = sum(len(bucket) for bucket in bounded.values())

        self.assertLessEqual(len(bounded[SAFETY_AREA_FIT_TOPIC]), EVIDENCE_PER_TOPIC_LIMIT)
        self.assertLessEqual(len(bounded[WALKABILITY_CAVEATS_TOPIC]), EVIDENCE_PER_TOPIC_LIMIT)
        self.assertLessEqual(total, TOTAL_EVIDENCE_LIMIT)
        self.assertEqual(
            len({item["url"] for bucket in bounded.values() for item in bucket}),
            total,
        )
        self.assertNotIn(
            "https://duplicate.example.com/same-title",
            {item["url"] for bucket in bounded.values() for item in bucket},
        )


class NeighborhoodEvidenceCollectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_neighborhood_evidence_keeps_partial_results_when_one_query_fails(self) -> None:
        with patch(
            "app.neighborhood_search._search_neighborhood",
            new=AsyncMock(
                side_effect=[
                    None,
                    {
                        "results": [
                            {
                                "title": "Transit and hills",
                                "url": "https://city.example.com/transit",
                                "content": "Metro coverage is strong, but hills can make some walks slower.",
                            }
                        ]
                    },
                ]
            ),
        ):
            payload = await collect_neighborhood_evidence(
                destination="Lisbon, Portugal",
                trip_type="business",
            )

        self.assertEqual(payload["query_count"], 2)
        self.assertEqual(payload["failed_queries"], 1)
        self.assertEqual(payload["raw_result_count"], 1)
        self.assertEqual(payload["evidence_count"], 1)
        self.assertEqual(payload["evidence_by_topic"][SAFETY_AREA_FIT_TOPIC], [])
        self.assertEqual(len(payload["evidence_by_topic"][WALKABILITY_CAVEATS_TOPIC]), 1)


class NeighborhoodAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_neighborhood_returns_empty_default_without_model_when_no_evidence(self) -> None:
        with patch(
            "app.agents.neighborhood.collect_neighborhood_evidence",
            new=AsyncMock(return_value=_empty_payload()),
        ), patch("app.agents.neighborhood.Agent") as mock_agent:
            output = await run_neighborhood(_sample_intake())

        self.assertEqual(
            output,
            NeighborhoodOutput(
                safety_summary="",
                vibe="",
                walkability="",
                notable_notes=[],
            ),
        )
        mock_agent.assert_not_called()

    async def test_run_neighborhood_uses_tool_less_model_with_bounded_prompt(self) -> None:
        payload = {
            "queries": build_neighborhood_search_queries("Lisbon, Portugal", "business"),
            "query_count": 2,
            "failed_queries": 1,
            "raw_result_count": 3,
            "extracted_evidence_count": 2,
            "evidence_count": 2,
            "evidence_by_topic": {
                SAFETY_AREA_FIT_TOPIC: [
                    {
                        "title": "Chiado area overview",
                        "url": "https://safety.example.com/chiado",
                        "snippet": "Busy central streets with plenty of foot traffic and a polished cafe-heavy feel.",
                        "source_domain": "safety.example.com",
                        "topic": SAFETY_AREA_FIT_TOPIC,
                        "query": "safety query",
                        "query_index": 0,
                        "result_index": 0,
                    }
                ],
                WALKABILITY_CAVEATS_TOPIC: [
                    {
                        "title": "Transit and hills",
                        "url": "https://walk.example.com/transit",
                        "snippet": "Metro access is strong, though steep streets can make longer luggage walks less pleasant.",
                        "source_domain": "walk.example.com",
                        "topic": WALKABILITY_CAVEATS_TOPIC,
                        "query": "walkability query",
                        "query_index": 1,
                        "result_index": 0,
                    }
                ],
            },
        }
        captured: dict[str, object] = {}

        class FakeAgent:
            def __init__(self, model: object, **kwargs: object) -> None:
                captured["model"] = model
                captured["agent_kwargs"] = kwargs

            async def __aenter__(self) -> "FakeAgent":
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def run(self, prompt: str, *, usage_limits) -> object:
                captured["prompt"] = prompt
                captured["usage_limits"] = usage_limits
                return type(
                    "Result",
                    (),
                    {
                        "output": NeighborhoodOutput(
                            safety_summary="Generally comfortable in the core blocks, with the usual city awareness at night.",
                            vibe="Central, polished, and cafe-heavy.",
                            walkability="Strong transit coverage and easy core-area walking, but hills can add friction.",
                            notable_notes=["Expect lively streets into the evening."],
                        )
                    },
                )()

        with patch(
            "app.agents.neighborhood.collect_neighborhood_evidence",
            new=AsyncMock(return_value=payload),
        ), patch("app.agents.neighborhood.get_fast_model_name", return_value="fake-model"), patch(
            "app.agents.neighborhood.get_minimax_api_key",
            return_value="fake-key",
        ), patch(
            "app.agents.neighborhood.anthropic.AsyncAnthropic",
            return_value=object(),
        ), patch(
            "app.agents.neighborhood.AnthropicProvider",
            side_effect=lambda anthropic_client: {"anthropic_client": anthropic_client},
        ), patch(
            "app.agents.neighborhood.AnthropicModel",
            side_effect=lambda *args, **kwargs: {"args": args, "kwargs": kwargs},
        ), patch(
            "app.agents.neighborhood.Agent",
            FakeAgent,
        ):
            output = await run_neighborhood(_sample_intake())

        self.assertEqual(output.vibe, "Central, polished, and cafe-heavy.")
        self.assertEqual(captured["agent_kwargs"]["output_type"], NeighborhoodOutput)
        self.assertEqual(captured["agent_kwargs"]["max_concurrency"], 1)
        self.assertNotIn("toolsets", captured["agent_kwargs"])
        self.assertEqual(captured["usage_limits"].request_limit, 3)
        self.assertIn("Precomputed evidence payload", captured["prompt"])
        self.assertIn("Busy central streets", captured["prompt"])
        self.assertIn('"failed_queries": 1', captured["prompt"])
        self.assertNotIn("tavily_search", captured["prompt"])
        self.assertNotIn("Make at most 2 Tavily searches", captured["prompt"])


if __name__ == "__main__":
    unittest.main()
