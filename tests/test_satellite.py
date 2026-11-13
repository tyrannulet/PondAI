import unittest
from unittest.mock import patch

from scripts import satellite

from scripts.satellite import _extract_time_series, _project_geometry, analyze_ice


class ExtractTimeSeriesTests(unittest.TestCase):
    def test_parses_numeric_strings_from_statistics_response(self):
        response = {
            "data": [
                {
                    "interval": {"from": "2025-01-01T00:00:00Z"},
                    "outputs": {
                        "indices": {
                            "bands": {
                                "B0": {
                                    "stats": {
                                        "mean": "0.4137",
                                        "sampleCount": "4",
                                        "noDataCount": "2",
                                    }
                                },
                                "B1": {"stats": {"mean": "-0.12"}},
                                "B2": {"stats": {"mean": "0.2", "percentiles": {"50.0": "0.18"}}},
                                "B3": {"stats": {"mean": "0.75"}},
                                "B4": {"stats": {"mean": "0.25"}},
                            }
                        }
                    },
                }
            ]
        }

        result = _extract_time_series(response)

        self.assertEqual(
            result,
            [
                {
                    "date": "2025-01-01",
                    "ndwi": 0.414,
                    "ndti": -0.12,
                    "ndci": 0.2,
                    "ndci_median": 0.18,
                    "water_percent": 75.0,
                    "ice_percent": 25.0,
                    "valid_pixels": 2,
                    "quality": "low confidence",
                }
            ],
        )

    def test_ignores_non_numeric_statistics(self):
        response = {
            "data": [
                {
                    "outputs": {
                        "indices": {
                            "bands": {
                                "B0": {"stats": {"mean": "n/a", "sampleCount": "n/a"}},
                                "B1": {"stats": {"mean": None}},
                                "B2": {"stats": {"mean": "NaN", "percentiles": {"50.0": "n/a"}}},
                                "B3": {"stats": {"mean": "Infinity"}},
                                "B4": {"stats": {"mean": "n/a"}},
                            }
                        }
                    },
                }
            ]
        }

        result = _extract_time_series(response)

        self.assertEqual(result[0]["ndwi"], None)
        self.assertEqual(result[0]["ndti"], None)
        self.assertEqual(result[0]["ndci"], None)
        self.assertEqual(result[0]["ndci_median"], None)
        self.assertEqual(result[0]["water_percent"], None)
        self.assertEqual(result[0]["ice_percent"], None)
        self.assertEqual(result[0]["valid_pixels"], None)

    def test_projects_wgs84_polygon_to_metric_sentinel_crs(self):
        geometry = {
            "type": "Polygon",
            "coordinates": [[[14.2934, 49.8956], [14.2944, 49.8956], [14.2934, 49.8956]]],
        }

        projected = _project_geometry(geometry)
        longitude_m, latitude_m = projected["coordinates"][0][0]

        self.assertGreater(longitude_m, 100_000)
        self.assertGreater(latitude_m, 100_000)
        self.assertNotEqual(projected["coordinates"][0][0], geometry["coordinates"][0][0])


class IceAnalysisTests(unittest.TestCase):
    def test_subthreshold_snow_pixels_remain_inconclusive(self):
        result = analyze_ice([{"date": "2025-01-01", "ice_percent": 10, "valid_pixels": 20}])
        self.assertEqual(result["status"], "inconclusive")

    def test_invalid_ice_values_do_not_crash_or_become_detections(self):
        for value in (float("nan"), float("inf"), -10, 150, True):
            with self.subTest(value=value):
                result = analyze_ice([{"ice_percent": value, "valid_pixels": 20}])
                self.assertEqual(result["status"], "inconclusive")

    def test_detects_possible_ice_only_with_enough_valid_pixels(self):
        series = [
            {
                "date": "2025-01-11",
                "ice_percent": 25.0,
                "valid_pixels": 20,
            }
        ]

        result = analyze_ice(series)

        self.assertEqual(result["status"], "possible_ice")
        self.assertEqual(result["observations"][0]["date"], "2025-01-11")
        self.assertEqual(series[0]["ice_status"], "possible_ice")
        self.assertIn("not a direct confirmation", result["limitations"])

    def test_reports_no_ice_only_for_usable_observations(self):
        result = analyze_ice(
            [{"date": "2025-06-01", "ice_percent": 0.0, "valid_pixels": 10}]
        )

        self.assertEqual(result["status"], "no_ice_detected")
        self.assertEqual(result["usable_intervals"], 1)

    def test_insufficient_pixels_make_ice_status_inconclusive(self):
        result = analyze_ice(
            [{"date": "2025-01-01", "ice_percent": 50.0, "valid_pixels": 4}]
        )

        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(result["usable_intervals"], 0)


class SatelliteFailureTests(unittest.TestCase):
    def setUp(self):
        self.pond = {"pond_id": "test", "name": "Test", "geometry": {
            "type": "Polygon", "coordinates": [[[14, 50], [14.01, 50], [14, 50.01], [14, 50]]],
        }}

    def analyze(self, payload):
        with (
            patch.object(satellite, "get_pond_by_id", return_value=self.pond),
            patch.object(satellite, "has_real_copernicus", return_value=True),
            patch.object(satellite, "_sentinel_hub_statistics", return_value=payload),
        ):
            return satellite.analyze_pond("test", "2025-01-01", "2025-12-31")

    def test_api_error_payload_is_not_a_successful_analysis(self):
        result = self.analyze({"error": {"message": "Invalid request"}})
        self.assertEqual(result["status"], "error")

    def test_dates_are_validated_before_any_external_call(self):
        for start, end in (
            ("2025-02-30", "2025-03-01"), ("2025-03-01", "2025-01-01"),
            ("2025-W01-1", "2025-03-01"),
        ):
            with (
                self.subTest(start=start),
                patch.object(satellite, "get_pond_by_id") as lookup,
                patch.object(satellite, "_sentinel_hub_statistics") as fetch,
            ):
                result = satellite.analyze_pond("test", start, end)
                self.assertEqual(result["status"], "error")
                lookup.assert_not_called()
                fetch.assert_not_called()

    def test_missing_measurements_are_not_zero_averages(self):
        with patch.object(satellite, "_extract_time_series", return_value=[{
            "date": "2025-01-01", "ndwi": None, "ndti": None, "ndci": None, "valid_pixels": 0,
        }]):
            result = self.analyze({"data": []})
        for metric in ("average_ndwi", "average_ndti", "average_ndci"):
            self.assertIsNone(result["metrics"][metric])

    def test_many_poor_intervals_do_not_raise_reliability(self):
        rows = [{"date": "2025-01-01", "valid_pixels": 2, "ndci": 0.3} for _ in range(12)]
        with patch.object(satellite, "_extract_time_series", return_value=rows):
            result = self.analyze({"data": []})
        self.assertEqual(result["quality_summary"]["reliability"], "low")
        with patch.object(satellite, "has_real_copernicus", return_value=True):
            algae = satellite.analyze_algae_bloom("test", "2025-01-01", "2025-12-31", analysis=result)
        self.assertEqual(algae["status"], "not_available")

    def test_zero_valid_pixels_discard_all_indices(self):
        result = _extract_time_series({"data": [{"outputs": {"indices": {"bands": {
            f"B{i}": {"stats": {"mean": 0.2, "sampleCount": 4, "noDataCount": 4}}
            for i in range(5)
        }}}}]})
        for metric in ("ndwi", "ndti", "ndci", "ndci_median", "water_percent", "ice_percent"):
            self.assertIsNone(result[0][metric])

    def test_missing_ndci_cannot_report_no_algae_signal(self):
        with patch.object(satellite, "has_real_copernicus", return_value=True):
            result = satellite.analyze_algae_bloom("test", "2025-01-01", "2025-12-31", analysis={
                "status": "ok", "timeseries": [{"ndci": None, "valid_pixels": 20}],
                "quality_summary": {"valid_pixels": 20, "reliability": "medium"},
            })
        self.assertEqual(result["status"], "not_available")
