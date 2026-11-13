import unittest
from unittest.mock import patch

from scripts import agent


class PondSearchParsingTests(unittest.TestCase):
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
            patch.object(agent, "has_real_featherless", return_value=True),
            patch.object(agent, "_normalize_municipality_with_featherless", return_value="Praha"),
            patch.object(agent, "_call_featherless_tools", return_value={"analysis": None}),
            patch.object(agent, "find_ponds", return_value=search_result) as find_ponds,
        ):
            result = agent.run_agent("Zkontrolujte rybníky v Praze", state)

        find_ponds.assert_called_once_with("Praha", None)
        self.assertEqual(result["status"], "awaiting_choice")
        self.assertIsNone(state["selected_pond"])
        self.assertIsNone(state["last_pond_name"])
