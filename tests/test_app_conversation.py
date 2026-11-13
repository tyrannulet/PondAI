import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from scripts import agent, config

APP_PATH = str(Path(__file__).resolve().parents[1] / "scripts" / "app.py")
MULTIPOLYGON = {"type": "MultiPolygon", "coordinates": [
    [[[14, 50], [14.02, 50], [14.02, 50.02], [14, 50.02], [14, 50]],
     [[14.005, 50.005], [14.005, 50.015], [14.015, 50.015], [14.015, 50.005], [14.005, 50.005]]],
    [[[14.03, 50], [14.04, 50], [14.04, 50.01], [14.03, 50.01], [14.03, 50]]],
]}


class ChatInterfaceTests(unittest.TestCase):
    def test_visualizations_can_be_hidden_without_losing_the_report_or_analysis(self):
        with (
            patch.object(config, "has_real_copernicus", return_value=False),
            patch.object(agent, "run_agent") as run_agent,
        ):
            app = AppTest.from_file(APP_PATH, default_timeout=15).run()
            original_analysis = app.session_state["analysis"]
            self.assertEqual(len(app.get("component_instance")), 1)
            app.checkbox(key="show_map").uncheck().run()
            self.assertEqual(len(app.get("component_instance")), 0)
            self.assertEqual(len(app.get("plotly_chart")), 0)
            self.assertTrue(any("Visualizations are hidden" in item.value for item in app.caption))
            self.assertTrue(any(original_analysis["report"] == item.value for item in app.markdown))

            app.checkbox(key="show_charts").check().run()
            self.assertEqual([tab.label for tab in app.tabs], ["Analytics"])
            self.assertGreater(len(app.get("plotly_chart")), 0)
            self.assertEqual(len(app.get("component_instance")), 0)
            app.checkbox(key="show_map").check().run()
            self.assertEqual([tab.label for tab in app.tabs], ["Analytics", "Map"])
            self.assertEqual(len(app.get("component_instance")), 1)
            self.assertEqual(app.session_state["analysis"], original_analysis)
            run_agent.assert_not_called()
        self.assertEqual(len(app.exception), 0)

    def test_demo_starts_and_displays_all_metrics_and_measurements(self):
        with patch.object(config, "has_real_copernicus", return_value=False):
            app = AppTest.from_file(APP_PATH, default_timeout=15).run()
            app.checkbox(key="show_charts").check().run()
            app.checkbox(key="show_table").check().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("DEMO MODE" in warning.value for warning in app.warning))
        self.assertGreaterEqual(len(app.get("plotly_chart")), 8)
        self.assertIn("ndci", app.dataframe[0].value.columns)
        self.assertEqual(app.dataframe[0].value.iloc[-1]["date"], "2025-12-31")

    def test_multipolygon_with_holes_can_be_selected_from_the_map(self):
        pond = {"pond_id": "test", "name": "Test", "geometry": MULTIPOLYGON}
        candidate = {"number": 1, "pond_id": "test", "name": "Test"}
        analysis = {"pond_id": "test", "report": "Test report", "timeseries": []}
        with (
            patch.object(config, "has_real_copernicus", return_value=True),
            patch.object(agent, "compose_reply", return_value=None),
            patch.object(agent, "_analyze_selected_pond", return_value={
                "status": "completed", "analysis": analysis, "selected_pond": pond, "response": "Test report",
            }) as analyze,
        ):
            app = AppTest.from_file(APP_PATH, default_timeout=15).run()
            app.session_state["pending_ponds"] = [pond]
            app.session_state["pending_candidates"] = [candidate]
            app.session_state["last_date_from"] = "2025-01-01"
            app.session_state["last_date_to"] = "2025-12-31"
            app.run()
            self.assertEqual(len(app.exception), 0)
            app.button(key="select_pond_candidate").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["selected_pond"]["pond_id"], "test")
        self.assertIsNone(app.session_state["pending_candidates"])
        self.assertEqual(analyze.call_count, 1)

    def test_model_unavailability_is_visible_in_the_chat_interface(self):
        with (
            patch.object(config, "has_real_copernicus", return_value=True),
            patch.object(agent, "understand_request", return_value=None),
            patch.object(agent, "compose_reply", return_value=None),
        ):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "scripts" / "app.py"), default_timeout=15).run()
            app.chat_input[0].set_value("Ahoj").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("automatic response" in caption.value for caption in app.caption))

    def test_model_followups_keep_data_and_control_chart_visibility(self):
        analysis = {
            "pond_id": "test-pond", "date_from": "2025-01-01", "date_to": "2025-12-31",
            "report": "Original analysis report", "quality_summary": {},
            "timeseries": [
                {"date": "2025-01-01", "water_percent": 20, "ndwi": -0.2, "ndti": 0.1, "ndci": 0.1},
                {"date": "2025-12-31", "water_percent": 40, "ndwi": 0.1, "ndti": 0.2, "ndci": 0.2},
            ],
        }
        with (
            patch.object(config, "has_real_copernicus", return_value=True),
            patch.object(config, "has_real_featherless", return_value=True),
            patch.object(agent, "understand_request", side_effect=[
                {"action": "chat", "show_charts": True},
                {"action": "chat", "show_charts": False},
            ]),
            patch.object(agent, "compose_reply", side_effect=["Tady jsou grafy k dosavadním datům.", "Grafy jsou skryté."]),
            patch.object(agent, "analyze_pond") as analyze,
            patch.object(agent, "find_ponds") as search,
        ):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "scripts" / "app.py"), default_timeout=15).run()
            app.session_state["analysis"] = analysis
            app.session_state["selected_pond"] = {"pond_id": "test-pond", "name": "Test pond", "municipality": "Řitka"}
            app.chat_input[0].set_value("Ukaž mi grafy.").run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(app.checkbox(key="show_charts").value)
            self.assertGreater(len(app.get("plotly_chart")), 0)
            self.assertEqual(app.session_state["messages"][-1]["content"], "Tady jsou grafy k dosavadním datům.")
            app.chat_input[0].set_value("Skryj grafy.").run()
            self.assertEqual(len(app.exception), 0)
            self.assertFalse(app.checkbox(key="show_charts").value)
            self.assertEqual(len(app.get("plotly_chart")), 0)
            self.assertEqual(app.session_state["analysis"]["report"], "Original analysis report")
            self.assertEqual(app.session_state["messages"][-1]["content"], "Grafy jsou skryté.")
            analyze.assert_not_called()
            search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
