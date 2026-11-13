import unittest
from unittest.mock import patch
from shapely.geometry import Point, shape

from scripts.geo_sources import _approximate_location, _normalise_geometry, find_ponds, get_pond_by_id


class GeometryTests(unittest.TestCase):
    def test_disjoint_arcgis_rings_and_holes_keep_their_areas(self):
        outer = [[0, 0], [0, 6], [6, 6], [6, 0], [0, 0]]
        hole = [[1, 1], [5, 1], [5, 5], [1, 5], [1, 1]]
        second = [[10, 0], [10, 2], [12, 2], [12, 0], [10, 0]]
        geometry = _normalise_geometry({"rings": [hole, second, outer]})
        self.assertEqual(geometry["type"], "MultiPolygon")
        self.assertTrue(shape(geometry).is_valid)
        self.assertEqual(shape(geometry).area, 24)
        location = _approximate_location(geometry)
        self.assertTrue(shape(geometry).contains(Point(location["longitude"], location["latitude"])))

    def test_marker_does_not_fall_in_a_polygon_hole(self):
        geometry = {"type": "Polygon", "coordinates": [
            [[0, 0], [6, 0], [6, 6], [0, 6], [0, 0]],
            [[1, 1], [1, 5], [5, 5], [5, 1], [1, 1]],
        ]}
        location = _approximate_location(geometry)
        self.assertTrue(shape(geometry).contains(Point(location["longitude"], location["latitude"])))

    def test_pond_id_is_escaped_in_arcgis_query(self):
        with patch("scripts.geo_sources._call_arcgis", return_value={"features": []}) as query:
            get_pond_by_id("pond'42")
        self.assertEqual(query.call_args.args[1]["where"], "fid_zbg = 'pond''42'")


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
