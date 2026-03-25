import json
import unittest

from app.agents import activities, flights, food, neighborhood
from app.mcp_client import TAVILY_DEFAULT_PARAMETERS


class TavilyConfigTest(unittest.TestCase):
    def test_default_parameters_are_conservative(self) -> None:
        self.assertEqual(
            TAVILY_DEFAULT_PARAMETERS,
            {
                "search_depth": "advanced",
                "max_results": 5,
                "include_images": False,
                "include_raw_content": False,
            },
        )

    def test_default_parameters_json_round_trip(self) -> None:
        encoded = json.dumps(TAVILY_DEFAULT_PARAMETERS)
        self.assertEqual(json.loads(encoded), TAVILY_DEFAULT_PARAMETERS)


class TavilyBudgetPromptTest(unittest.TestCase):
    def test_neighborhood_budget_is_tighter(self) -> None:
        self.assertEqual(neighborhood.SEARCH_REQUEST_LIMIT, 4)
        self.assertIn("at most 2 Tavily searches total", neighborhood.SYSTEM_PROMPT)
        self.assertIn("Use only tavily-search", neighborhood.SYSTEM_PROMPT)

    def test_activities_is_model_only_ranking(self) -> None:
        self.assertEqual(activities.MODEL_REQUEST_LIMIT, 3)
        self.assertIn("Use only the provided candidate activities.", activities.SYSTEM_PROMPT)
        self.assertIn("Do not search or invent additional options.", activities.SYSTEM_PROMPT)

    def test_food_prefers_search_snippets_over_extract(self) -> None:
        self.assertEqual(food.SEARCH_REQUEST_LIMIT, 5)
        self.assertIn("Prefer writing from strong search snippets", food.SYSTEM_PROMPT)
        self.assertIn("at most 1 high-value URL", food.SYSTEM_PROMPT)

    def test_flights_prefers_local_airport_lookup_before_tavily(self) -> None:
        self.assertEqual(flights.MODEL_REQUEST_LIMIT, 3)
        self.assertIn("Use only the provided candidate flights.", flights.SYSTEM_PROMPT)
        self.assertIn("Never invent flight data.", flights.SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
