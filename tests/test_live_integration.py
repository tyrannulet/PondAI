"""Opt-in integration check; uses configured services and their API quota."""
import json
import os
import unittest
from unittest.mock import patch

from scripts import agent, config


@unittest.skipUnless(os.getenv("PONDAI_LIVE_TESTS") == "1", "Set PONDAI_LIVE_TESTS=1 to call real APIs.")
class LiveIntegrationTests(unittest.TestCase):
    def test_search_analysis_and_followup_use_real_services(self):
        self.assertTrue(config.has_real_copernicus(), "Copernicus is not configured.")
        self.assertTrue(config.has_real_featherless(), "Featherless is not configured.")
        state = {"messages": []}

        def ask(prompt):
            state["messages"].append({"role": "user", "content": prompt})
            result = agent.run_agent(prompt, state)
            state["messages"].append({"role": "assistant", "content": result["response"]})
            return result

        with (
            patch.object(agent, "find_ponds", wraps=agent.find_ponds) as search,
            patch.object(agent, "analyze_pond", wraps=agent.analyze_pond) as analyze,
        ):
            result = ask("Najdi rybníky v Řitce od 2025-06-01 do 2025-06-30.")
            self.assertEqual(result["understanding_source"], "model")
            self.assertIn(result["status"], ("awaiting_choice", "completed"))
            if result["status"] == "awaiting_choice":
                largest = max(state["pending_candidates"], key=lambda item: item.get("area_m2") or 0)
                result = ask(str(largest["number"]))
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["response_source"], "model")
            analysis = result["analysis"]
            self.assertFalse(analysis.get("demo_mode"))
            self.assertEqual((analysis["date_from"], analysis["date_to"]), ("2025-06-01", "2025-06-30"))
            self.assertTrue(analysis["timeseries"], "No satellite observations returned.")
            followup = ask("Vysvětli stručně, co znamená NDWI u těchto výsledků.")
            self.assertEqual(followup["status"], "conversation")
            self.assertEqual(followup["response_source"], "model")
            self.assertEqual(search.call_count, 1)
            self.assertEqual(analyze.call_count, 1)
        print(json.dumps({
            "live_check": "passed", "observations": len(analysis["timeseries"]),
            "reliability": analysis.get("quality_summary", {}).get("reliability"),
            "search_calls": search.call_count, "analysis_calls": analyze.call_count,
        }))


if __name__ == "__main__":
    unittest.main()
