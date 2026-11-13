import copy
import json
import unittest
from unittest.mock import patch

from scripts import agent, conversation, satellite


POND = {"pond_id": "pond-1", "name": "Test pond", "municipality": "Řitka", "area_m2": 5000}
ANALYSIS = {
    "status": "ok", "pond_id": "pond-1", "pond_name": "Test pond",
    "date_from": "2025-01-01", "date_to": "2025-12-31",
    "quality_summary": {"valid_pixels": 20, "reliability": "medium"},
    "timeseries": [
        {"date": "2025-01-01", "water_percent": 20, "ndci": 0.1, "valid_pixels": 10},
        {"date": "2025-12-31", "water_percent": 40, "ndci": 0.2, "valid_pixels": 10},
    ],
}


class ConversationContextTests(unittest.TestCase):
    def test_history_is_chronological_and_current_prompt_occurs_once(self):
        state = {"messages": [
            {"role": "user", "content": "Analyze Řitka for 2025"},
            {"role": "assistant", "content": "Water-pixel share increased."},
            {"role": "user", "content": "Why?"},
        ]}
        messages = conversation._messages("system", "Why?", state, {})
        self.assertEqual(messages[1:3], state["messages"][:2])
        self.assertEqual(messages[-1], {"role": "user", "content": "Why?"})
        self.assertEqual(sum(item["content"] == "Why?" for item in messages), 1)

    def test_context_contains_data_and_selected_pond_without_geometry_or_secrets(self):
        state = {
            "selected_pond": {**POND, "geometry": {"coordinates": [1, 2]}},
            "analysis": ANALYSIS, "FEATHERLESS_API_KEY": "never-send-this",
        }
        context = conversation.conversation_context(state)
        self.assertEqual(context["selected_pond"]["pond_id"], "pond-1")
        self.assertEqual(context["period"]["from"], "2025-01-01")
        self.assertEqual(context["analysis"]["statistics_for_full_period"]["water_percent"]["max"], 40)
        self.assertNotIn("coordinates", json.dumps(context))
        self.assertNotIn("never-send-this", json.dumps(context))

    def test_long_series_are_bounded_but_statistics_include_unsampled_extremes(self):
        series = [{"date": str(i), "ndwi": 0.1} for i in range(100)]
        series[2]["ndwi"] = 0.9
        context = conversation.analysis_context({"timeseries": series})
        self.assertEqual(len(context["observations"]), conversation.MAX_OBSERVATIONS)
        self.assertEqual(context["observations"][-1]["date"], "99")
        self.assertTrue(context["observations_sampled"])
        self.assertEqual(context["statistics_for_full_period"]["ndwi"]["max"], 0.9)

    def test_model_receives_the_actual_followup_and_new_and_previous_periods(self):
        state = {"selected_pond": POND, "analysis": ANALYSIS, "messages": [
            {"role": "user", "content": "Piš česky, stručně."},
            {"role": "assistant", "content": "Dobře."},
        ]}
        new_analysis = {**ANALYSIS, "date_from": "2024-06-01", "date_to": "2024-08-31"}
        result = {"status": "completed", "response": "Data summary", "analysis": new_analysis, "selected_pond": POND}
        with (
            patch.object(conversation, "has_real_featherless", return_value=True),
            patch.object(conversation, "_complete", return_value="Srovnání obou období.") as complete,
        ):
            reply = conversation.compose_reply("Porovnej to s předchozím.", state, result)
        self.assertEqual(reply, "Srovnání obou období.")
        messages = complete.call_args.args[0]
        self.assertEqual(messages[1]["content"], "Piš česky, stručně.")
        self.assertEqual(messages[-1]["content"], "Porovnej to s předchozím.")
        context = json.loads(messages[-2]["content"].split("\n", 1)[1])
        self.assertEqual(context["analysis"]["date_from"], "2025-01-01")
        self.assertEqual(context["action_result"]["analysis"]["date_from"], "2024-06-01")
        self.assertIn("not water level", messages[0]["content"])

    def test_invalid_plans_are_rejected(self):
        invalid = [
            [], {"action": "delete"}, {"action": "select", "candidate_number": True},
            {"action": "analyze", "date_from": "2025-02-30", "date_to": "2025-03-01"},
            {"action": "analyze", "date_from": "2025-03-01", "date_to": "2025-01-01"},
            {"action": "analyze", "date_from": "2025-01-01"},
            {"action": "search", "water_body_type": "ocean"},
        ]
        for intent in invalid:
            with (
                self.subTest(intent=intent),
                patch.object(conversation, "has_real_featherless", return_value=True),
                patch.object(conversation, "_complete", return_value=json.dumps(intent)),
            ):
                self.assertIsNone(conversation.understand_request("request", {}))

    def test_redundant_search_fields_for_known_candidate_are_treated_as_selection(self):
        state = {"last_municipality": "Řitka", "pending_candidates": [{"number": 2, **POND}]}
        plan = {"action": "search", "municipality": "Řitka", "pond_name": "Test pond", "candidate_number": 2}
        with (
            patch.object(conversation, "has_real_featherless", return_value=True),
            patch.object(conversation, "_complete", return_value=json.dumps(plan)),
        ):
            intent = conversation.understand_request("Vezmi ten větší.", state)
        self.assertEqual(intent["action"], "select")
        self.assertEqual(intent["candidate_number"], 2)

    def test_unsupported_numerical_claims_trigger_a_model_correction(self):
        with (
            patch.object(conversation, "has_real_featherless", return_value=True),
            patch.object(conversation, "_complete", side_effect=["Water coverage was 82%.", "Choose one of the listed ponds."]) as complete,
        ):
            reply = conversation.compose_reply("Vezmi ten větší.", {}, {"status": "awaiting_choice", "response": "Choose a pond."})
        self.assertEqual(reply, "Choose one of the listed ponds.")
        self.assertEqual(complete.call_count, 2)

    def test_numerical_grounding_accepts_locale_formatting_and_supplied_statistics(self):
        context = {"area_m2": 9000, "water_percent": 40, "date": "2025-08-31", "ndwi": -0.234}
        self.assertEqual(conversation._unsupported_numbers("9 000 m², 40 %, NDWI -0,23 (31. 8. 2025).", context, ""), [])
        self.assertEqual(conversation._unsupported_numbers("Water share is 82%.", context, ""), [82])

    def test_repeated_unsupported_numbers_are_rejected(self):
        with (
            patch.object(conversation, "has_real_featherless", return_value=True),
            patch.object(conversation, "_complete", return_value="Water share is 82%.") as complete,
        ):
            reply = conversation.compose_reply("What did you find?", {}, {"status": "awaiting_choice"})
        self.assertIsNone(reply)
        self.assertEqual(complete.call_count, 2)


class ConversationalAgentTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "selected_pond": copy.deepcopy(POND), "analysis": copy.deepcopy(ANALYSIS),
            "last_municipality": "Řitka", "last_date_from": "2025-01-01", "last_date_to": "2025-12-31",
        }

    def test_followup_uses_model_answer_and_preserves_analysis_without_fetching(self):
        for prompt in ("A proč?", "Vysvětli NDWI.", "Stručněji prosím."):
            with (
                self.subTest(prompt=prompt),
                patch.object(agent, "understand_request", return_value={"action": "chat"}),
                patch.object(agent, "compose_reply", return_value="Odpověď na konkrétní otázku."),
                patch.object(agent, "find_ponds") as search,
                patch.object(agent, "analyze_pond") as analyze,
            ):
                result = agent.run_agent(prompt, self.state)
                self.assertEqual(result["response"], "Odpověď na konkrétní otázku.")
                self.assertEqual(result["response_source"], "model")
                self.assertEqual(result["status"], "conversation")
                self.assertEqual(self.state["analysis"], ANALYSIS)
                search.assert_not_called()
                analyze.assert_not_called()

    def test_changed_period_uses_selected_pond_and_stores_model_report(self):
        intent = {"action": "analyze", "date_from": "2024-06-01", "date_to": "2024-08-31"}
        with (
            patch.object(agent, "understand_request", return_value=intent),
            patch.object(agent, "compose_reply", return_value="V létě 2024…"),
            patch.object(agent, "find_ponds") as search,
            patch.object(agent, "analyze_pond", return_value=copy.deepcopy(ANALYSIS)) as analyze,
            patch.object(agent, "analyze_algae_bloom", return_value={}),
        ):
            result = agent.run_agent("A za předloňské léto?", self.state)
        analyze.assert_called_once_with("pond-1", "2024-06-01", "2024-08-31")
        search.assert_not_called()
        self.assertEqual(result["analysis"]["report"], "V létě 2024…")
        self.assertIs(self.state["analysis"], result["analysis"])

    def test_natural_candidate_selection_uses_existing_candidate_and_period(self):
        self.state["selected_pond"] = None
        self.state["pending_candidates"] = [
            {"number": 1, **POND}, {"number": 2, "pond_id": "pond-2", "name": "Large pond", "area_m2": 9000},
        ]
        self.state["pending_ponds"] = self.state["pending_candidates"]
        with (
            patch.object(agent, "understand_request", return_value={"action": "select", "candidate_number": 2}),
            patch.object(agent, "compose_reply", return_value="Vybral jsem větší rybník."),
            patch.object(agent, "_analyze_selected_pond", return_value={"response": "facts", "analysis": copy.deepcopy(ANALYSIS), "status": "completed"}) as analyze,
            patch.object(agent, "find_ponds") as search,
        ):
            agent.run_agent("Vezmi ten větší.", self.state)
        self.assertEqual(analyze.call_args.args[0]["pond_id"], "pond-2")
        self.assertEqual(analyze.call_args.args[1:3], ("2025-01-01", "2025-12-31"))
        self.assertIsNone(self.state["pending_candidates"])
        search.assert_not_called()

    def test_unknown_candidate_cannot_launch_an_analysis(self):
        self.state["pending_candidates"] = [{"number": 1, **POND}]
        with (
            patch.object(agent, "understand_request", return_value={"action": "select", "candidate_number": 99}),
            patch.object(agent, "compose_reply", return_value="Vyber položku ze seznamu."),
            patch.object(agent, "analyze_pond") as analyze,
        ):
            result = agent.run_agent("Ten devadesátý devátý.", self.state)
        self.assertEqual(result["status"], "awaiting_choice")
        self.assertEqual(len(self.state["pending_candidates"]), 1)
        analyze.assert_not_called()

    def test_selection_in_a_different_municipality_does_not_use_stale_candidates(self):
        self.state["selected_pond"] = None
        self.state["pending_candidates"] = [{"number": 1, **POND}]
        with (
            patch.object(agent, "understand_request", return_value={"action": "select", "candidate_number": 1, "municipality": "Praha"}),
            patch.object(agent, "compose_reply", return_value="Vyber rybník v Praze."),
            patch.object(agent, "find_ponds", return_value={"status": "multiple", "candidates": [], "result": []}) as search,
            patch.object(agent, "analyze_pond") as analyze,
        ):
            agent.run_agent("Ten větší, ale v Praze.", self.state)
        search.assert_called_once_with("Praha", None, "pond")
        analyze.assert_not_called()
        self.assertIsNone(self.state["selected_pond"])

    def test_numeric_choice_bypasses_understanding_but_still_uses_model_reply(self):
        self.state["pending_candidates"] = [{"number": 1, **POND}]
        with (
            patch.object(agent, "understand_request") as understand,
            patch.object(agent, "compose_reply", return_value="Analýza vybraného rybníka."),
            patch.object(agent, "_analyze_selected_pond", return_value={"response": "facts", "analysis": copy.deepcopy(ANALYSIS), "status": "completed"}),
        ):
            result = agent.run_agent("1", self.state)
        understand.assert_not_called()
        self.assertEqual(result["understanding_source"], "selection")
        self.assertEqual(result["response_source"], "model")

    def test_year_is_not_mistaken_for_a_candidate_and_dates_keep_pending_list(self):
        self.state["selected_pond"] = None
        self.state["pending_candidates"] = [{"number": 1, **POND}]
        with (
            patch.object(agent, "understand_request", return_value=None),
            patch.object(agent, "compose_reply", return_value=None),
            patch.object(agent, "find_ponds") as search,
            patch.object(agent, "analyze_pond") as analyze,
        ):
            result = agent.run_agent("2024", self.state)
        self.assertEqual(result["status"], "awaiting_choice")
        self.assertEqual(self.state["last_date_from"], "2024-01-01")
        self.assertEqual(len(self.state["pending_candidates"]), 1)
        search.assert_not_called()
        analyze.assert_not_called()

    def test_unavailable_model_is_visible_and_local_invalid_dates_do_not_fetch(self):
        with (
            patch.object(agent, "understand_request", return_value=None),
            patch.object(agent, "compose_reply", return_value=None),
            patch.object(agent, "analyze_pond") as analyze,
        ):
            result = agent.run_agent("2025-02-30 to 2025-03-01", self.state)
        self.assertEqual(result["status"], "awaiting_input")
        self.assertEqual(result["response_source"], "fallback")
        self.assertIn("unavailable", result["ai_note"])
        self.assertEqual(self.state["last_date_from"], "2025-01-01")
        analyze.assert_not_called()

    def test_chart_preference_can_be_changed_without_recomputing(self):
        with (
            patch.object(agent, "understand_request", return_value={"action": "chat", "show_charts": False}),
            patch.object(agent, "compose_reply", return_value="Grafy jsou skryté."),
            patch.object(agent, "analyze_pond") as analyze,
        ):
            agent.run_agent("Skryj grafy.", self.state)
        self.assertFalse(self.state["show_charts"])
        analyze.assert_not_called()

    def test_satellite_failure_is_not_reported_as_a_completed_analysis(self):
        with (
            patch.object(agent, "analyze_pond", return_value={"status": "error", "message": "No satellite access"}),
            patch.object(agent, "analyze_algae_bloom") as algae,
        ):
            result = agent._analyze_selected_pond(POND, "2025-01-01", "2025-12-31")
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["analysis"])
        algae.assert_not_called()

    def test_failed_new_period_does_not_leave_previous_charts_visible(self):
        with (
            patch.object(agent, "understand_request", return_value={
                "action": "analyze", "date_from": "2024-01-01", "date_to": "2024-12-31",
            }),
            patch.object(agent, "compose_reply", return_value=None),
            patch.object(agent, "analyze_pond", return_value={"status": "error"}),
        ):
            result = agent.run_agent("A pro rok 2024?", self.state)
        self.assertEqual(result["status"], "error")
        self.assertIsNone(self.state["analysis"])

    def test_changing_water_body_type_searches_instead_of_reusing_selected_pond(self):
        with (
            patch.object(agent, "understand_request", return_value={
                "action": "analyze", "water_body_type": "reservoir",
            }),
            patch.object(agent, "compose_reply", return_value=None),
            patch.object(agent, "find_ponds", return_value={"status": "not_found"}) as search,
            patch.object(agent, "analyze_pond") as analyze,
        ):
            agent.run_agent("Teď analyzuj nádrže v té samé obci.", self.state)
        search.assert_called_once_with("Řitka", None, "reservoir")
        analyze.assert_not_called()

    def test_algae_screening_reuses_the_existing_satellite_response(self):
        with (
            patch.object(satellite, "has_real_copernicus", return_value=True),
            patch.object(satellite, "analyze_pond") as analyze,
        ):
            result = satellite.analyze_algae_bloom("pond-1", "2025-01-01", "2025-12-31", analysis=ANALYSIS)
        analyze.assert_not_called()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["ndci_trend"], ANALYSIS["timeseries"])


if __name__ == "__main__":
    unittest.main()
