from __future__ import annotations

import json
from typing import Any

import requests
from shapely.geometry import Polygon, shape
from shapely.errors import ShapelyError

from scripts import demo_data

RUIAN_URL = "https://ags.cuzk.gov.cz/arcgis/rest/services/RUIAN/MapServer/12/query"
ZABAGED_URL = "https://ags.cuzk.cz/arcgis/rest/services/ZABAGED_POLOHOPIS/MapServer/132/query"
REQUEST_TIMEOUT = 25
WATER_BODY_TYPES = {
    "1": "reservoir",
    "2": "pond",
    "3": "artificial lake",
    "4": "natural lake",
    "5": "backwater pool",
    "6": "swimming area",
    "7": "fish-farming pond",
    "8": "settling basin",
    "9": "other water body",
    "10": "unspecified water body",
}
WATER_BODY_TYPE_CODES = {
    "pond": ("2",),
    "reservoir": ("1",),
    "lake": ("3", "4"),
    "all": tuple(WATER_BODY_TYPES),
}


def _call_arcgis(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(url, data=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and "error" in payload:
        raise ValueError(str(payload["error"]))
    return payload


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        clean = value.replace(" ", "").replace(",", ".")
        try:
            return float(clean)
        except ValueError:
            return None
    return None


def _normalise_geometry(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not geometry:
        return None
    if geometry.get("type") in ("Polygon", "MultiPolygon"):
        return geometry
    if geometry.get("rings"):
        rings = geometry["rings"]
        polygons = [Polygon(ring) for ring in rings]
        # Containment works regardless of ring order or winding direction. Each
        # odd-depth ring is a hole; an island inside a hole starts a new polygon.
        parents = []
        for index, polygon in enumerate(polygons):
            containers = [
                other for other, candidate in enumerate(polygons)
                if other != index and candidate.area > polygon.area and candidate.covers(polygon)
            ]
            parents.append(min(containers, key=lambda other: polygons[other].area) if containers else None)
        depths = []
        for index in range(len(rings)):
            depth, parent = 0, parents[index]
            while parent is not None:
                depth += 1
                parent = parents[parent]
            depths.append(depth)
        coordinates = [
            [ring, *[rings[child] for child, parent in enumerate(parents) if parent == index and depths[child] % 2]]
            for index, ring in enumerate(rings) if depths[index] % 2 == 0
        ]
        if len(coordinates) == 1:
            return {"type": "Polygon", "coordinates": coordinates[0]}
        return {"type": "MultiPolygon", "coordinates": coordinates}
    return geometry


def _approximate_location(geometry: dict[str, Any] | None) -> dict[str, float] | None:
    if not geometry:
        return None
    try:
        point = shape(geometry).representative_point()
        if point.is_empty:
            return None
        return {"longitude": point.x, "latitude": point.y}
    except (ShapelyError, ValueError, TypeError, KeyError):
        return None


def _normalise_pond_result(feature: dict[str, Any]) -> dict[str, Any]:
    attrs = feature.get("attributes") or {}
    type_code = str(attrs.get("typ_vp_k") or "")
    area = attrs.get("Shape_Area")
    if area is None:
        area = attrs.get("ploscha")
    if area is None:
        area = attrs.get("area")
    if area is None:
        area = attrs.get("shape_area")
    area_val = _to_float(area) or 0.0
    name = (
        attrs.get("nazev")
        or attrs.get("nazev_vp")
        or attrs.get("jmeno")
        or attrs.get("name")
    )
    water_body_type = WATER_BODY_TYPES.get(type_code, "water body")
    pond_id = (
        attrs.get("fid_zbg")
        or attrs.get("OBJECTID")
        or attrs.get("id")
        or attrs.get("globalid")
        or attrs.get("fid")
        or ""
    )
    geometry = _normalise_geometry(feature.get("geometry"))
    return {
        "pond_id": str(pond_id),
        "name": str(name) if name else f"Unnamed {water_body_type}",
        "water_body_type": water_body_type,
        "area_m2": int(round(area_val)),
        "geometry": geometry,
        "approx_location": _approximate_location(geometry),
        "attributes": attrs,
    }


def _select_municipality_in_response(features: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    lowered = target.lower().strip()
    if not lowered:
        return None
    for feature in features:
        attrs = feature.get("attributes") or {}
        name = str(attrs.get("nazev") or "").lower()
        if lowered in name:
            return feature
    return features[0] if features else None


def find_ponds(
    municipality: str,
    pond_name: str | None = None,
    water_body_type: str = "pond",
) -> dict[str, Any]:
    municipality = (municipality or "").strip()
    pond_name = (pond_name or "").strip()
    type_codes = WATER_BODY_TYPE_CODES.get(water_body_type)
    if type_codes is None:
        raise ValueError(f"Unsupported water-body type: {water_body_type}")
    if not municipality:
        return {"status": "not_found", "message": "A municipality is required."}

    try:
        name_variants = [municipality]
        if municipality.casefold().endswith("ce"):
            name_variants.append(municipality[:-2] + "ka")
        community = None
        for variant in name_variants:
            escaped_name = variant.replace("'", "''")
            ruians = _call_arcgis(
                RUIAN_URL,
                {
                    "where": f"nazev = '{escaped_name}'",
                    "outFields": "nazev",
                    "returnGeometry": "true",
                    "outSR": 5514,
                    "f": "json",
                },
            )
            community = _select_municipality_in_response(ruians.get("features") or [], variant)
            if community is not None:
                break
        if community is None:
            return {
                "status": "not_found",
                "municipality": municipality,
                "message": f"Municipality '{municipality}' was not found in RÚIAN.",
                "candidates": [],
            }
        municipality = str((community.get("attributes") or {}).get("nazev") or municipality)
        community_geometry = community.get("geometry")
        if community_geometry is None:
            raise ValueError("Municipality geometry not available")

        type_filter = ", ".join(f"'{code}'" for code in type_codes)
        payload = {
            "where": f"typ_vp_k IN ({type_filter})",
            "geometry": json.dumps(community_geometry),
            "geometryType": "esriGeometryPolygon",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": 5514,
            "outSR": 4326,
            "outFields": "*",
            "returnGeometry": "true",
            "f": "json",
        }
        zabaged = _call_arcgis(ZABAGED_URL, payload)
        pond_features = zabaged.get("features") or []
        cleaned: list[dict[str, Any]] = []
        for feature in pond_features:
            attrs = feature.get("attributes") or {}
            if str(attrs.get("typ_vp_k") or "") not in type_codes:
                continue
            cleaned.append(_normalise_pond_result(feature))

        if pond_name:
            lowered = pond_name.lower()
            cleaned = [item for item in cleaned if lowered in item["name"].lower()]

        if not cleaned:
            type_label = "water body" if water_body_type == "all" else water_body_type
            return {
                "status": "not_found",
                "municipality": municipality,
                "message": (
                    f"No {type_label.replace('_', ' ')} matching the filter was found "
                    f"in '{municipality}'. Try a different name or water-body type."
                ),
                "candidates": [],
            }

        if len(cleaned) == 1:
            result = cleaned[0]
            return {
                "status": "ok",
                "municipality": municipality,
                "result": [result],
                "candidates": [
                    {
                        "number": 1,
                        "pond_id": result["pond_id"],
                        "name": result["name"],
                        "water_body_type": result["water_body_type"],
                        "area_m2": result["area_m2"],
                        "approx_location": result["approx_location"],
                    }
                ],
            }

        candidates = [
            {
                "number": index + 1,
                "pond_id": item["pond_id"],
                "name": item["name"],
                "water_body_type": item["water_body_type"],
                "area_m2": item["area_m2"],
                "approx_location": item["approx_location"],
            }
            for index, item in enumerate(cleaned)
        ]
        return {
            "status": "multiple",
            "municipality": municipality,
            "result": cleaned,
            "candidates": candidates,
            "message": "Multiple water bodies were found. Please choose one.",
        }
    except (requests.RequestException, ValueError, TypeError) as exc:
        return {
            "status": "error",
            "municipality": municipality,
            "message": f"Water-body search failed ({type(exc).__name__}). Please try again later.",
            "candidates": [],
        }


def get_pond_by_id(pond_id: str) -> dict[str, Any] | None:
    if not pond_id:
        return None

    demo_map = demo_data.DEMO_PONDS
    if pond_id in demo_map:
        return {
            "pond_id": demo_map[pond_id]["pond_id"],
            "name": demo_map[pond_id]["name"],
            "water_body_type": demo_map[pond_id]["water_body_type"],
            "area_m2": demo_map[pond_id]["area_m2"],
            "geometry": demo_map[pond_id]["geometry"],
            "municipality": demo_map[pond_id]["municipality"],
        }

    try:
        escaped_id = str(pond_id).replace("'", "''")
        response = _call_arcgis(
            ZABAGED_URL,
            {
                "where": f"fid_zbg = '{escaped_id}'",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "f": "json",
            },
        )
        features = response.get("features") or []
        if not features:
            return None
        result = _normalise_pond_result(features[0])
        return result
    except (requests.RequestException, ValueError, TypeError):
        return None
