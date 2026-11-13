import unittest

from scripts.satellite import _extract_time_series


class ExtractTimeSeriesTests(unittest.TestCase):
    def test_parses_numeric_strings_from_statistics_response(self):
        response = {
            "data": [
                {
                    "interval": {"from": "2025-01-01T00:00:00Z"},
                    "outputs": {
                        "indices": {
                            "bands": {
                                "B0": {"stats": {"mean": "0.4137", "sampleCount": "4"}},
                                "B1": {"stats": {"mean": "-0.12"}},
                                "B2": {"stats": {"mean": "0.2", "percentiles": {"50.0": "0.18"}}},
                                "B3": {"stats": {"mean": "0.75"}},
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
                    "valid_pixels": 4,
                    "quality": "nízká spolehlivost",
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
        self.assertEqual(result[0]["valid_pixels"], None)
