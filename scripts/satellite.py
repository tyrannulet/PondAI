from __future__ import annotations

import math
import time
from typing import Any

from pyproj import Transformer
import requests

from scripts import demo_data
from scripts.config import DEFAULT_NDWI_THRESHOLD, get_copernicus_config, has_real_copernicus
from scripts.date_utils import validate_date_range
from scripts.geo_sources import get_pond_by_id

TOKEN_CACHE: dict[str, Any] = {"token": None, "expires_at": 0.0}
SENTINEL_HUB_URL = "https://sh.dataspace.copernicus.eu/statistics/v1"
SENTINEL_HUB_CRS = "http://www.opengis.net/def/crs/EPSG/0/3035"
_WGS84_TO_SENTINEL_HUB_TRANSFORMER = Transformer.from_crs(
    "EPSG:4326", "EPSG:3035", always_xy=True
)


def _now_epoch() -> float:
    return time.time()


def _get_copernicus_token() -> str:
    config = get_copernicus_config()
    token_url = config.get("CDSE_TOKEN_URL")
    client_id = config.get("CDSE_CLIENT_ID")
    client_secret = config.get("CDSE_CLIENT_SECRET")
    if not (token_url and client_id and client_secret):
        raise ValueError("Copernicus credentials are missing.")
    if TOKEN_CACHE["token"] and _now_epoch() < TOKEN_CACHE["expires_at"]:
        return TOKEN_CACHE["token"]

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    response = requests.post(token_url, data=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise ValueError("Copernicus OAuth did not return an access token.")
    expires_in = int(data.get("expires_in", 3600))
    TOKEN_CACHE["token"] = access_token
    TOKEN_CACHE["expires_at"] = _now_epoch() + max(expires_in - 60, 30)
    return access_token


def _sentinel_hub_statistics(geometry: dict[str, Any], date_from: str, date_to: str, evalscript: str) -> dict[str, Any]:
    token = _get_copernicus_token()
    start = _as_utc_datetime(date_from, end_of_day=False)
    end = _as_utc_datetime(date_to, end_of_day=True)
    payload = {
        "input": {
            "bounds": {
                "geometry": geometry,
                "properties": {"crs": SENTINEL_HUB_CRS},
            },
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"mosaickingOrder": "leastCC"}}],
        },
        "aggregation": {
            "timeRange": {"from": start, "to": end},
            "aggregationInterval": {"of": "P10D"},
            "evalscript": evalscript,
            "resx": 10,
            "resy": 10,
        },
        "calculations": {
            "default": {
                "statistics": {
                    "default": {"percentiles": {"k": [50]}},
                }
            }
        },
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post(SENTINEL_HUB_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"error": "Invalid response from the Sentinel Hub API"}


def _as_utc_datetime(value: str, end_of_day: bool) -> str:
    date_value = value.strip()
    if "T" not in date_value:
        date_value += "T23:59:59Z" if end_of_day else "T00:00:00Z"
    elif date_value.endswith("+00:00"):
        date_value = date_value[:-6] + "Z"
    return date_value


def _extract_metric_value(payload: dict[str, Any], metric_name: str) -> float | None:
    if not payload:
        return None
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if key.lower() == metric_name.lower():
                    parsed_value = _as_float(value)
                    if parsed_value is not None:
                        return parsed_value
                stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        parsed_value = float(value)
    except (OverflowError, ValueError):
        return None
    return parsed_value if math.isfinite(parsed_value) else None


def _project_coordinates(coordinates: Any) -> Any:
    if (
        isinstance(coordinates, (list, tuple))
        and len(coordinates) >= 2
        and isinstance(coordinates[0], (int, float))
        and isinstance(coordinates[1], (int, float))
    ):
        x, y = _WGS84_TO_SENTINEL_HUB_TRANSFORMER.transform(
            float(coordinates[0]), float(coordinates[1])
        )
        return [x, y, *coordinates[2:]]
    if isinstance(coordinates, (list, tuple)):
        return [_project_coordinates(part) for part in coordinates]
    raise ValueError("Water-body geometry has invalid coordinates.")


def _project_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, (list, tuple)):
        raise ValueError("Water-body geometry does not contain valid coordinates.")
    return {**geometry, "coordinates": _project_coordinates(coordinates)}


def _extract_time_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else []
    if not isinstance(data, list):
        return []
    series: list[dict[str, Any]] = []
    for item in data:
        interval = item.get("interval") if isinstance(item, dict) else None
        outputs = item.get("outputs") if isinstance(item, dict) else None
        indices = outputs.get("indices") if isinstance(outputs, dict) else None
        bands = indices.get("bands") if isinstance(indices, dict) else None
        if not isinstance(bands, dict):
            continue
        date_from_value = interval.get("from") if isinstance(interval, dict) else None
        date_to_value = interval.get("to") if isinstance(interval, dict) else None
        band_stats = [((bands.get(f"B{index}") or {}).get("stats") or {}) for index in range(5)]
        means = [_as_float(stat.get("mean")) for stat in band_stats]
        ndwi, ndti, ndci, water_share, ice_share = means
        sample_count = _as_float(band_stats[0].get("sampleCount"))
        no_data_count = _as_float(band_stats[0].get("noDataCount"))
        valid_pixels = (
            max(0, round(sample_count - (no_data_count or 0)))
            if sample_count is not None
            else None
        )
        ndci_median = _as_float((band_stats[2].get("percentiles") or {}).get("50.0"))
        if not valid_pixels:
            ndwi = ndti = ndci = ndci_median = None
        series.append(
            {
                "date": str(date_from_value or date_to_value or "").split("T")[0],
                "ndwi": round(ndwi, 3) if ndwi is not None else None,
                "ndti": round(ndti, 3) if ndti is not None else None,
                "ndci": round(ndci, 3) if ndci is not None else None,
                "ndci_median": round(ndci_median, 3) if ndci_median is not None else None,
                "water_percent": round(water_share * 100, 2) if water_share is not None and valid_pixels else None,
                "ice_percent": round(ice_share * 100, 2) if ice_share is not None and valid_pixels else None,
                "valid_pixels": valid_pixels,
                "quality": "low confidence" if valid_pixels is not None and valid_pixels < 10 else "observed",
            }
        )
    return series


def analyze_ice(timeseries: list[dict[str, Any]]) -> dict[str, Any]:
    usable_intervals = 0
    clear_intervals = 0
    detections: list[dict[str, Any]] = []
    for item in timeseries:
        valid_pixels = item.get("valid_pixels")
        ice_percent = item.get("ice_percent")
        if (
            type(valid_pixels) is not int
            or valid_pixels < 10
            or type(ice_percent) not in (int, float)
            or not math.isfinite(ice_percent)
            or not 0 <= ice_percent <= 100
        ):
            item["ice_status"] = "inconclusive"
            continue

        usable_intervals += 1
        ice_pixels = round(valid_pixels * ice_percent / 100)
        if ice_percent >= 15 and ice_pixels >= 2:
            item["ice_status"] = "possible_ice"
            detections.append(
                {
                    "date": item.get("date"),
                    "ice_percent": ice_percent,
                    "valid_pixels": valid_pixels,
                }
            )
        elif ice_pixels == 0:
            item["ice_status"] = "no_ice_detected"
            clear_intervals += 1
        else:
            item["ice_status"] = "inconclusive"

    status = (
        "possible_ice"
        if detections
        else "no_ice_detected"
        if usable_intervals and clear_intervals == usable_intervals
        else "inconclusive"
    )
    return {
        "status": status,
        "source": "Sentinel-2 Scene Classification Layer (snow/ice class)",
        "observations": detections,
        "usable_intervals": usable_intervals,
        "limitations": (
            "This is a satellite screening for pixels classified as snow or ice, "
            "not a direct confirmation that the water surface was frozen. "
            "Clouds, mixed shore pixels, and the 20 m classification resolution "
            "can limit reliability. An interval is flagged only with at least 10 "
            "valid pixels, 15% classified snow/ice, and at least 2 classified pixels."
        ),
    }


def _sentinel2_evalscript() -> str:
    return """
    //VERSION=3
    function setup() {
      return {
        input: [{bands: ["B03", "B04", "B08", "B05", "SCL", "dataMask"]}],
        output: [
          {id: "indices", bands: 5, sampleType: "FLOAT32"},
          {id: "dataMask", bands: 1}
        ]
      };
    }
    function evaluatePixel(samples) {
      let ndwiSum = samples.B03 + samples.B08;
      let ndtiSum = samples.B04 + samples.B03;
      let ndciSum = samples.B05 + samples.B04;
      let valid = samples.dataMask === 1 && samples.SCL !== 3 && samples.SCL !== 8 && samples.SCL !== 9 && samples.SCL !== 10;
      let ndwi = ndwiSum !== 0 ? (samples.B03 - samples.B08) / ndwiSum : 0;
      let ndti = ndtiSum !== 0 ? (samples.B04 - samples.B03) / ndtiSum : 0;
      let ndci = ndciSum !== 0 ? (samples.B05 - samples.B04) / ndciSum : 0;
      let possibleIce = samples.SCL === 11 ? 1 : 0;
      return {
        indices: [ndwi, ndti, ndci, ndwi > 0 ? 1 : 0, possibleIce],
        dataMask: [valid && ndwiSum !== 0 && ndtiSum !== 0 && ndciSum !== 0 ? 1 : 0]
      };
    }
    """


def analyze_pond(pond_id: str, date_from: str, date_to: str) -> dict[str, Any]:
    try:
        validate_date_range(date_from, date_to)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    pond = get_pond_by_id(pond_id)
    if not pond:
        return {"status": "not_available", "message": "Water body was not found or is unavailable for analysis."}

    if not has_real_copernicus():
        return demo_data.generate_demo_analysis(pond_id, date_from, date_to, pond=pond)

    geometry = pond.get("geometry")
    if not geometry:
        return {"status": "not_available", "message": "No polygon is available for this water body."}

    try:
        projected_geometry = _project_geometry(geometry)
        api_response = _sentinel_hub_statistics(
            projected_geometry, date_from, date_to, _sentinel2_evalscript()
        )
        if (
            not isinstance(api_response, dict) or "error" in api_response
            or not isinstance(api_response.get("data"), list)
        ):
            raise ValueError("Sentinel Hub returned an invalid statistics response.")
    except (requests.RequestException, ValueError) as exc:
        return {
            "status": "error",
            "message": f"Sentinel Hub did not return the expected data: {exc}",
            "quality_summary": {"data_quality": "unavailable", "reliability": "low", "limitations": "Sentinel Hub access failed."},
        }

    timeseries = _extract_time_series(api_response)
    ice = analyze_ice(timeseries)
    metrics = {"water_area_estimate_m2": None}
    for metric in ("ndwi", "ndti", "ndci"):
        values = [_as_float(item.get(metric)) for item in timeseries]
        values = [value for value in values if value is not None]
        metrics[f"average_{metric}"] = round(sum(values) / len(values), 3) if values else None
    pixel_counts = [item["valid_pixels"] for item in timeseries if item.get("valid_pixels") is not None]
    valid_pixel_count = sum(pixel_counts)
    # Repeated observations of the same few pixels do not improve spatial coverage.
    max_valid_pixels = max(pixel_counts, default=0)
    low_confidence = max_valid_pixels < 10
    quality = {
        "data_quality": "too few valid pixels" if low_confidence and timeseries else "partially available" if timeseries else "unavailable",
        "valid_pixels": valid_pixel_count,
        "max_valid_pixels_per_interval": max_valid_pixels,
        "reliability": "low" if low_confidence else "medium",
        "limitations": "Limited coverage or few valid pixels may reduce estimate reliability.",
    }
    return {
        "status": "ok",
        "pond_id": pond["pond_id"],
        "pond_name": pond["name"],
        "municipality": pond.get("municipality", "unknown"),
        "date_from": date_from,
        "date_to": date_to,
        "source": "Copernicus Sentinel-2 (Statistical API)",
        "metrics": metrics,
        "quality_summary": quality,
        "timeseries": timeseries,
        "ice": ice,
        "warning": "NDWI, NDTI, and NDCI are satellite screening indicators, not direct measurements of chemical or microbiological water quality.",
        "ndwi_threshold": DEFAULT_NDWI_THRESHOLD,
    }


def analyze_algae_bloom(
    pond_id: str,
    date_from: str,
    date_to: str,
    *,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if analysis is None:
        analysis = analyze_pond(pond_id, date_from, date_to)
    if analysis.get("demo_mode"):
        ndci = analysis.get("metrics", {}).get("average_ndci")
        return {
            "status": "demo", "source": "simulated",
            "ndci_trend": analysis.get("timeseries", []),
            "category": "Elevated algae-related signal" if ndci is not None and ndci > 0.2 else "No strong change detected",
            "interpretation": "This is a simulated screening result. NDCI does not identify cyanotoxin concentrations or specific cyanobacteria.",
            "quality": analysis.get("quality_summary", {}),
        }
    if analysis.get("status") != "ok":
        return {
            "status": "not_available",
            "source": "sentinel-2",
            "category": "Insufficient data",
            "interpretation": "There were not enough satellite observations in this period for an algae screening.",
            "quality": analysis.get("quality_summary", {}),
        }

    ndci_values = [
        value for item in analysis.get("timeseries", [])
        if (item.get("valid_pixels") or 0) >= 10
        and (value := _as_float(item.get("ndci"))) is not None
    ]
    if not ndci_values or analysis.get("quality_summary", {}).get("valid_pixels", 0) < 10:
        return {
            "status": "not_available",
            "source": "Sentinel-2 NDCI",
            "ndci_trend": analysis.get("timeseries", []),
            "category": "Insufficient data",
            "interpretation": "There were not enough valid NDCI observations with sufficient pixels for an algae screening.",
            "quality": analysis.get("quality_summary", {}),
        }
    mean_ndci = sum(ndci_values) / len(ndci_values)
    if mean_ndci > 0.24:
        category = "Possible algae-bloom signal"
    elif mean_ndci > 0.18:
        category = "Elevated algae-related signal"
    else:
        category = "No strong change detected"

    return {
        "status": "ok",
        "source": "Sentinel-2 NDCI",
        "ndci_trend": analysis.get("timeseries", []),
        "category": category,
        "interpretation": "NDCI is a rough indicator related to chlorophyll-a and phytoplankton biomass. It does not confirm cyanobacteria, toxins, or pathogens.",
        "quality": analysis.get("quality_summary", {}),
    }
