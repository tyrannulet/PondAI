import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import agent


class ChartInterpretationTests(unittest.TestCase):
    def setUp(self):
        self.analysis = {
            "date_from": "2025-01-01",
            "date_to": "2025-01-20",
            "quality_summary": {"valid_pixels": 20, "reliability": "střední"},
            "timeseries": [
                {
                    "date": "2025-01-01",
                    "water_percent": 20.0,
                    "ndwi": -0.2,
                    "ndti": 0.1,
                    "ndci": 0.3,
                    "valid_pixels": 10,
                },
                {
                    "date": "2025-01-11",
                    "water_percent": None,
                    "ndwi": None,
                    "ndti": None,
                    "ndci": None,
                    "valid_pixels": 0,
                },
                {
                    "date": "2025-01-20",
                    "water_percent": 40.0,
                    "ndwi": 0.1,
                    "ndti": 0.2,
                    "ndci": 0.4,
                    "valid_pixels": 10,
                },
            ],
        }
        self.algae = {
            "category": "Elevated algae-related signal",
            "interpretation": "Satellite screening only.",
            "ndci_trend": self.analysis["timeseries"],
        }
        self.pond = {
            "name": "Test pond",
            "municipality": "Řitka",
            "area_m2": 5000,
        }

    def test_fallback_interprets_each_chart_and_mentions_missing_values(self):
        with patch.object(agent, "has_real_featherless", return_value=False):
            interpretation = agent._interpret_analysis_charts(
                self.pond, self.analysis, self.algae
            )

        self.assertIn("mapped boundary", interpretation)
        self.assertIn("NDWI", interpretation)
        self.assertIn("NDTI", interpretation)
        self.assertIn("NDCI", interpretation)
        self.assertIn("1 of 3", interpretation)
        self.assertIn("20 to 40", interpretation)

    def test_model_receives_geospatial_context_and_all_chart_data(self):
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            "Water-pixel share increases. NDWI increases. "
                            "NDTI is stable. NDCI is stable. "
                            "Possible snow/ice classification: none observed."
                        )
                    )
                )
            ]
        )
        create_completion = Mock(return_value=completion)
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create_completion)
            )
        )
        with (
            patch.object(agent, "has_real_featherless", return_value=True),
            patch.object(agent, "OpenAI", return_value=client),
            patch.object(
                agent,
                "get_featherless_config",
                return_value={
                    "FEATHERLESS_API_KEY": "test-key",
                    "FEATHERLESS_MODEL": "test-model",
                },
            ),
        ):
            result = agent._interpret_analysis_charts(
                self.pond, self.analysis, self.algae
            )

        self.assertIn("Water-pixel share", result)
        prompt = create_completion.call_args.kwargs
        self.assertIn("10 m pixels", prompt["messages"][0]["content"])
        self.assertFalse(
            prompt["extra_body"]["chat_template_kwargs"]["enable_thinking"]
        )
        data = json.loads(prompt["messages"][1]["content"])
        self.assertEqual(data["pond"]["municipality"], "Řitka")
        self.assertEqual(data["water_area_estimate"]["observations"][1]["valid_pixels"], 0)
        self.assertEqual(data["optical_indices"]["observations"][0]["ndwi"], -0.2)
        self.assertIn("-0.2", data["precalculated_trends"]["ndwi"])
        self.assertIn("0.1", data["precalculated_trends"]["ndwi"])

    def test_incomplete_model_response_falls_back_to_all_chart_summaries(self):
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Water-pixel share increased.")
                )
            ]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(return_value=completion))
            )
        )
        with (
            patch.object(agent, "has_real_featherless", return_value=True),
            patch.object(agent, "OpenAI", return_value=client),
            patch.object(
                agent,
                "get_featherless_config",
                return_value={"FEATHERLESS_API_KEY": "test-key"},
            ),
        ):
            result = agent._interpret_analysis_charts(
                self.pond, self.analysis, self.algae
            )

        self.assertIn("chart interpretation", result)
        self.assertIn("NDWI", result)
        self.assertIn("NDTI", result)
        self.assertIn("NDCI", result)

    def test_speculative_model_response_uses_cautious_chart_summary(self):
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            "Water-pixel share may suggest a change. "
                            "NDWI stable. NDTI stable. NDCI stable."
                        )
                    )
                )
            ]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(return_value=completion))
            )
        )
        with (
            patch.object(agent, "has_real_featherless", return_value=True),
            patch.object(agent, "OpenAI", return_value=client),
            patch.object(
                agent,
                "get_featherless_config",
                return_value={"FEATHERLESS_API_KEY": "test-key"},
            ),
        ):
            result = agent._interpret_analysis_charts(
                self.pond, self.analysis, self.algae
            )

        self.assertIn("insufficiently cautious", result)
        self.assertIn("NDWI", result)
        self.assertIn("NDTI", result)
        self.assertIn("NDCI", result)
        self.assertIn("mapped boundary", result)

    def test_analysis_report_is_plain_language_and_charts_are_opt_in(self):
        interpretation = "Interpretation of all four charts."
        with (
            patch.object(
                agent,
                "analyze_pond",
                return_value={
                    "metrics": {},
                    "warning": "",
                    "date_from": "2025-01-01",
                    "date_to": "2025-01-20",
                    "timeseries": [],
                },
            ),
            patch.object(
                agent,
                "analyze_algae_bloom",
                return_value={"interpretation": "", "ndci_trend": []},
            ),
            patch.object(
                agent,
                "_interpret_analysis_charts",
                return_value=interpretation,
            ),
        ):
            result = agent._analyze_selected_pond(
                {**self.pond, "pond_id": "test-pond"},
                "2025-01-01",
                "2025-01-20",
                include_charts=True,
            )

        self.assertIn("Satellite report", result["response"])
        self.assertEqual(result["analysis"]["graph_interpretation"], interpretation)
        self.assertEqual(result["analysis"]["report"], result["response"])

    def test_plain_language_report_explains_satellite_quality_limits(self):
        report = agent._plain_language_report(
            self.pond,
            {
                "date_from": "2025-01-01",
                "date_to": "2025-01-20",
                "timeseries": self.analysis["timeseries"],
                "ice": {"status": "no_ice_detected", "usable_intervals": 2},
            },
            {"category": "No strong change detected"},
        )

        self.assertIn("20% to 40%", report)
        self.assertIn("not water depth or volume", report)
        self.assertIn("does not prove that the water never froze", report)
        self.assertIn("laboratory", report)

    def test_charts_are_not_interpreted_until_requested(self):
        with (
            patch.object(
                agent,
                "analyze_pond",
                return_value={
                    "date_from": "2025-01-01",
                    "date_to": "2025-01-20",
                    "timeseries": [],
                    "warning": "",
                },
            ),
            patch.object(agent, "analyze_algae_bloom", return_value={}),
            patch.object(agent, "_interpret_analysis_charts") as interpret_charts,
        ):
            result = agent._analyze_selected_pond(
                {**self.pond, "pond_id": "test-pond"},
                "2025-01-01",
                "2025-01-20",
            )

        interpret_charts.assert_not_called()
        self.assertIsNone(result["analysis"]["graph_interpretation"])
        self.assertIn("Satellite report", result["response"])

    def test_report_compares_monthly_algae_related_signals(self):
        report = agent._plain_language_report(
            self.pond,
            {
                "date_from": "2025-01-01",
                "date_to": "2025-02-20",
                "timeseries": [
                    {"date": "2025-01-10", "ndci": 0.1},
                    {"date": "2025-02-10", "ndci": 0.4},
                ],
                "ice": {"status": "inconclusive"},
            },
            {"category": "Elevated algae-related signal"},
        )

        self.assertIn("lower in January 2025", report)
        self.assertIn("higher in February 2025", report)
        self.assertIn("not by itself proof of poorer water quality", report)
