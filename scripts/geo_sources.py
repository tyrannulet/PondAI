from __future__ import annotations

import json
from typing import Any

import requests

from scripts import demo_data

RUIAN_URL = "https://ags.cuzk.gov.cz/arcgis/rest/services/RUIAN/MapServer/12/query"
ZABAGED_URL = "https://ags.cuzk.cz/arcgis/rest/services/ZABAGED_POLOHOPIS/MapServer/132/query"
REQUEST_TIMEOUT = 25


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
    if geometry.get("type") == "Polygon":
        return geometry
    if geometry.get("rings"):
        return {
            "type": "Polygon",
            "coordinates": geometry["rings"],
        }
    return geometry


def _approximate_location(geometry: dict[str, Any] | None) -> dict[str, float] | None:
    if not geometry:
        return None
    coordinates = geometry.get("coordinates") or []
    if not coordinates or not isinstance(coordinates[0], list):
        return None
    ring = coordinates[0]
    points = [point for point in ring if isinstance(point, (list, tuple)) and len(point) >= 2]
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if not points:
        return None
    return {
        "longitude": sum(float(point[0]) for point in points) / len(points),
        "latitude": sum(float(point[1]) for point in points) / len(points),
    }


def _normalise_pond_result(feature: dict[str, Any]) -> dict[str, Any]:
    attrs = feature.get("attributes") or {}
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
        or "Bezejmenný rybník"
    )
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
        "name": str(name) if name else "Bezejmenný rybník",
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


def find_ponds(municipality: str, pond_name: str | None = None) -> dict[str, Any]:
    municipality = (municipality or "").strip()
    pond_name = (pond_name or "").strip()
    if not municipality:
        return {"status": "not_found", "message": "Chybí název obce. Uveďte prosím obec, ve které chcete hledat rybník."}

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
                "message": f"Obec '{municipality}' nebyla nalezena v RÚIAN. Zkontrolujte prosím její název.",
                "candidates": [],
            }
        municipality = str((community.get("attributes") or {}).get("nazev") or municipality)
        community_geometry = community.get("geometry")
        if community_geometry is None:
            raise ValueError("Municipality geometry not available")

        payload = {
            "where": "typ_vp_k = '2'",
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
            if isinstance(attrs.get("typ_vp_k"), str) and attrs.get("typ_vp_k") != "2":
                continue
            if attrs.get("typ_vp_k") not in ("2", 2):
                continue
            cleaned.append(_normalise_pond_result(feature))

        if pond_name:
            lowered = pond_name.lower()
            cleaned = [item for item in cleaned if lowered in item["name"].lower()]

        if not cleaned:
            return {
                "status": "not_found",
                "municipality": municipality,
                "message": f"V obci '{municipality}' nebyl nalezen žádný rybník odpovídající filtru. Zkuste prosím upřesnit název rybníka.",
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
            "message": "Bylo nalezeno více rybníků. Vyberte prosím konkrétní kandidáta.",
        }
    except (requests.RequestException, ValueError, TypeError) as exc:
        return {
            "status": "error",
            "municipality": municipality,
            "message": f"Vyhledávání rybníků se nepodařilo dokončit: {type(exc).__name__}. Zkuste to prosím později.",
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
            "area_m2": demo_map[pond_id]["area_m2"],
            "geometry": demo_map[pond_id]["geometry"],
            "municipality": demo_map[pond_id]["municipality"],
        }

    try:
        response = _call_arcgis(
            ZABAGED_URL,
            {
                "where": f"fid_zbg = '{str(pond_id)}'",
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
