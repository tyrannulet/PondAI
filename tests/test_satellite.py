import unittest

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
