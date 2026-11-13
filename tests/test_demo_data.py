import unittest
from unittest.mock import patch

from scripts import demo_data, satellite


class DemoAnalysisTests(unittest.TestCase):
    def test_series_covers_the_entire_requested_year(self):
        result = demo_data.generate_demo_analysis("ritka-pond-1", "2025-01-01", "2025-12-31")
        self.assertEqual(result["timeseries"][0]["date"], "2025-01-01")
        self.assertEqual(result["timeseries"][-1]["date"], "2025-12-31")
        self.assertGreater(len(result["timeseries"]), 30)

    def test_short_period_keeps_both_endpoints(self):
        result = demo_data.generate_demo_analysis("ritka-pond-1", "2025-06-01", "2025-06-03")
        self.assertEqual([row["date"] for row in result["timeseries"]], ["2025-06-01", "2025-06-03"])

    def test_unknown_id_does_not_silently_analyze_another_pond(self):
        with self.assertRaises(ValueError):
            demo_data.generate_demo_analysis("unknown-id", "2025-01-01", "2025-01-02")

    def test_real_selection_keeps_identity_and_geometry_in_demo_mode(self):
        pond = {
            "pond_id": "real-pond", "name": "Selected pond", "municipality": "Test",
            "area_m2": 5000, "geometry": demo_data.DEMO_PONDS["lazne-pond-2"]["geometry"],
        }
        with (
            patch.object(satellite, "get_pond_by_id", return_value=pond),
            patch.object(satellite, "has_real_copernicus", return_value=False),
            patch.object(satellite, "_sentinel_hub_statistics") as fetch,
        ):
            result = satellite.analyze_pond("real-pond", "2025-01-01", "2025-01-02")
            algae = satellite.analyze_algae_bloom("real-pond", "2025-01-01", "2025-01-02", analysis=result)
        self.assertEqual(result["pond_id"], "real-pond")
        self.assertEqual(result["pond_name"], "Selected pond")
        self.assertEqual(result["geometry"], pond["geometry"])
        self.assertEqual(algae["ndci_trend"], result["timeseries"])
        self.assertTrue(result["demo_mode"])
        fetch.assert_not_called()

