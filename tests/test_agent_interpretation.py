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
            "category": "Zvýšená algální biomasa",
            "interpretation": "Orientační screening.",
            "ndci_trend": self.analysis["timeseries"],
        }
        self.pond = {
            "name": "Testovací rybník",
            "municipality": "Řitka",
            "area_m2": 5000,
        }

    def test_fallback_interprets_each_chart_and_mentions_missing_values(self):
        with patch.object(agent, "has_real_featherless", return_value=False):
            interpretation = agent._interpret_analysis_charts(
                self.pond, self.analysis, self.algae
            )

        self.assertIn("podíl klasifikovaných pixelů", interpretation)
        self.assertIn("NDWI", interpretation)
        self.assertIn("NDTI", interpretation)
        self.assertIn("NDCI", interpretation)
        self.assertIn("1 z 3", interpretation)
        self.assertIn("20 na 40", interpretation)

    def test_model_receives_geospatial_context_and_all_chart_data(self):
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            "Podíl vodních pixelů roste. NDWI roste. "
                            "NDTI je stabilní. NDCI je stabilní."
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

        self.assertIn("Podíl vodních pixelů", result)
        prompt = create_completion.call_args.kwargs
        self.assertIn("10m pixely", prompt["messages"][0]["content"])
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
                    message=SimpleNamespace(content="Podíl vodních pixelů se zvýšil.")
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

        self.assertIn("interpretaci grafů", result)
        self.assertIn("NDWI", result)
        self.assertIn("NDTI", result)
        self.assertIn("NDCI", result)

    def test_speculative_model_response_uses_cautious_chart_summary(self):
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            "Podíl vodních pixelů může naznačovat změnu. "
                            "NDWI stabilní. NDTI stabilní. NDCI stabilní."
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

        self.assertIn("opatrnou interpretaci", result)
        self.assertIn("NDWI", result)
        self.assertIn("NDTI", result)
        self.assertIn("NDCI", result)
        self.assertIn("podíl klasifikovaných pixelů", result)

    def test_analysis_response_ends_with_graph_interpretation(self):
        interpretation = "Interpretace všech čtyř grafů."
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
            )

        self.assertTrue(result["response"].endswith(interpretation))
        self.assertEqual(result["analysis"]["graph_interpretation"], interpretation)
