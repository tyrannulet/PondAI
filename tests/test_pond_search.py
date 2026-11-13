import unittest
from unittest.mock import patch

from scripts import agent


class PondSearchParsingTests(unittest.TestCase):
    def test_invalid_relative_period_does_not_launch_tools(self):
        for prompt in ("last 0 months", "last 999999999999 months"):
            with (
                self.subTest(prompt=prompt),
                patch.object(agent, "understand_request", return_value=None),
                patch.object(agent, "compose_reply", return_value=None),
                patch.object(agent, "find_ponds") as search,
                patch.object(agent, "analyze_pond") as analyze,
            ):
                result = agent.run_agent(prompt, {})
                self.assertEqual(result["status"], "awaiting_input")
                search.assert_not_called()
                analyze.assert_not_called()

    def test_pond_plural_does_not_become_a_pond_name_filter(self):
        prompts = [
            "Zkontrolujte rybníky v Praze v roce 2025",
            "Najdi všechny rybníky v Mníšku pod Brdy",
            "Najdi rybník ve městě Řitka a analyzuj ho v roce 2025",
        ]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertIsNone(agent._extract_pond_name(prompt))

    def test_explicit_pond_name_is_still_extracted(self):
        self.assertEqual(
            agent._extract_pond_name("Najdi rybník Brčálník v Řitce"),
            "Brčálník",
        )
        self.assertEqual(
            agent._extract_pond_name("Najdi rybník s názvem U Dubu v Praze"),
            "U Dubu",
        )

    def test_common_inflected_municipalities_are_canonicalized(self):
        self.assertEqual(
            agent._canonicalize_municipality(agent._extract_municipality("rybníky v Praze")),
            "Praha",
        )
        self.assertEqual(
            agent._canonicalize_municipality(
                agent._extract_municipality("rybníky v Mníšku pod Brdy")
            ),
            "Mníšek pod Brdy",
        )
        self.assertEqual(
            agent._canonicalize_municipality(
                agent._extract_municipality("rybník ve městě Řitka")
            ),
            "Řitka",
        )

    def test_new_municipality_clears_previous_pond_filter(self):
        search_result = {
            "status": "multiple",
            "municipality": "Praha",
            "result": [{"pond_id": "pond-1", "name": "Pražský rybník"}],
            "candidates": [{"number": 1, "pond_id": "pond-1", "name": "Pražský rybník"}],
        }
        state = {
            "last_municipality": "Řitka",
            "last_pond_name": "Řitecký rybník",
            "selected_pond": {"pond_id": "old-pond"},
            "pending_candidates": [{"number": 1, "pond_id": "old-pond"}],
            "pending_ponds": [{"pond_id": "old-pond"}],
            "last_date_from": "2025-01-01",
            "last_date_to": "2025-12-31",
        }
        with (
            patch.object(agent, "understand_request", return_value={
                "action": "search", "municipality": "Praha",
            }),
            patch.object(agent, "compose_reply", return_value="Choose a pond in Prague."),
            patch.object(agent, "find_ponds", return_value=search_result) as find_ponds,
        ):
            result = agent.run_agent("Zkontrolujte rybníky v Praze", state)

        find_ponds.assert_called_once_with("Praha", None, "pond")
        self.assertEqual(result["status"], "awaiting_choice")
        self.assertIsNone(state["selected_pond"])
        self.assertIsNone(state["last_pond_name"])

    def test_english_water_body_requests_and_periods_are_understood(self):
        prompt = "Find all water bodies in Prague for the last three months"

        self.assertEqual(agent._extract_municipality(prompt), "Praha")
        self.assertEqual(agent._extract_water_body_type(prompt), "all")
        self.assertIsNotNone(agent._extract_date_range(prompt))

    def test_reservoir_and_lake_requests_select_their_zabaged_types(self):
        self.assertEqual(
            agent._extract_water_body_type("Find reservoirs in Prague"),
            "reservoir",
        )
        self.assertEqual(
            agent._extract_water_body_type("Find lakes in Prague"),
            "lake",
        )
        self.assertEqual(
            agent._extract_pond_name("Find the reservoir named Slapy in Prague"),
            "Slapy",
        )

    def test_chart_requests_enable_optional_charts_only_when_requested(self):
        self.assertTrue(agent._requests_charts("Show me the charts"))
        self.assertFalse(agent._requests_charts("Report the results without charts"))
