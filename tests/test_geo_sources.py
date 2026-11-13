import unittest
from unittest.mock import patch

from scripts.geo_sources import find_ponds


class WaterBodySearchTests(unittest.TestCase):
    def setUp(self):
        self.community = {
            "features": [
                {
                    "attributes": {"nazev": "Test"},
                    "geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                }
            ]
        }

    def test_reservoir_search_uses_zabaged_reservoir_code(self):
        reservoir = {
            "features": [
                {
                    "attributes": {
                        "typ_vp_k": "1",
                        "fid_zbg": "reservoir-1",
                        "Shape_Area": 12000,
                    },
                    "geometry": {
                        "rings": [[[14.0, 50.0], [14.1, 50.0], [14.0, 50.0]]]
                    },
                }
            ]
        }
        with patch(
            "scripts.geo_sources._call_arcgis",
            side_effect=[self.community, reservoir],
        ) as call_arcgis:
            result = find_ponds("Test", water_body_type="reservoir")

        self.assertEqual(call_arcgis.call_args_list[1].args[1]["where"], "typ_vp_k IN ('1')")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"][0]["water_body_type"], "reservoir")

    def test_all_water_bodies_includes_all_observed_zabaged_codes(self):
        with patch(
            "scripts.geo_sources._call_arcgis",
            side_effect=[self.community, {"features": []}],
        ) as call_arcgis:
            result = find_ponds("Test", water_body_type="all")

        self.assertEqual(
            call_arcgis.call_args_list[1].args[1]["where"],
            "typ_vp_k IN ('1', '2', '3', '4', '5', '6', '7', '8', '9', '10')",
        )
        self.assertEqual(result["status"], "not_found")

    def test_unknown_water_body_type_is_rejected(self):
        with self.assertRaises(ValueError):
            find_ponds("Test", water_body_type="river")
