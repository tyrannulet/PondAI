from __future__ import annotations

from datetime import datetime, timedelta
import json
import time
from typing import Any

import requests

from scripts import demo_data
from scripts.config import DEFAULT_NDWI_THRESHOLD, get_copernicus_config, has_real_copernicus
from scripts.geo_sources import get_pond_by_id

TOKEN_CACHE: dict[str, Any] = {"token": None, "expires_at": 0.0}
SENTINEL_HUB_URL = "https://sh.dataspace.copernicus.eu/statistics/v1"


def _now_epoch() -> float:
    return time.time()


def _get_copernicus_token() -> str:
    config = get_copernicus_config()
    token_url = config.get("CDSE_TOKEN_URL")
    client_id = config.get("CDSE_CLIENT_ID")
    client_secret = config.get("CDSE_CLIENT_SECRET")
    if not (token_url and client_id and client_secret):
        raise ValueError("Copernicus přihlašovací údaje chybí.")
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
        raise ValueError("Copernicus OAuth nepřinesl access token.")
    expires_in = int(data.get("expires_in", 3600))
    TOKEN_CACHE["token"] = access_token
    TOKEN_CACHE["expires_at"] = _now_epoch() + max(expires_in - 60, 30)
    return access_token


def _sentinel_hub_statistics(geometry: dict[str, Any], date_from: str, date_to: str, evalscript: str) -> dict[str, Any]:
    token = _get_copernicus_token()
    payload = {
        "input": {
            "bounds": {
                "geometry": {
                    **geometry,
                    "crs": {"type": "name", "properties": {"name": "EPSG:5514"}},
                }
            },
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"timeRange": {"from": date_from, "to": date_to}, "mosaickingOrder": "leastCC"}}],
        },
        "aggregation": {
            "timeRange": {"from": date_from, "to": date_to},
            "aggregationPeriod": {"unit": "P10D", "value": 10},
            "resx": 10,
            "resy": 10,
        },
        "evalscript": evalscript,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post(SENTINEL_HUB_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"error": "Neplatná odpověď Sentinel Hub API"}


def _extract_metric_value(payload: dict[str, Any], metric_name: str) -> float | None:
    if not payload:
        return None
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if key.lower() == metric_name.lower():
                    if isinstance(value, (int, float)):
                        return float(value)
                    if isinstance(value, str):
                        try:
                            return float(value)
                        except ValueError:
                            pass
                stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)
    return None


def _extract_time_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else []
    if not isinstance(data, list):
        return []
    series: list[dict[str, Any]] = []
    for item in data:
        interval = item.get("interval") if isinstance(item, dict) else None
        result = item.get("output") if isinstance(item, dict) else None
        if not isinstance(result, dict):
            continue
        date_from_value = interval.get("from") if isinstance(interval, dict) else None
        date_to_value = interval.get("to") if isinstance(interval, dict) else None
        ndwi = _extract_metric_value(result, "NDWI")
        ndti = _extract_metric_value(result, "NDTI")
        ndci = _extract_metric_value(result, "NDCI")
        water_share = _extract_metric_value(result, "waterShare")
        valid_pixels = _extract_metric_value(result, "validPixels")
        series.append(
            {
                "date": str(date_from_value or date_to_value or "").split("T")[0],
                "ndwi": round(ndwi, 3) if ndwi is not None else None,
                "ndti": round(ndti, 3) if ndti is not None else None,
                "ndci": round(ndci, 3) if ndci is not None else None,
                "water_percent": round(water_share, 2) if water_share is not None else None,
                "valid_pixels": int(valid_pixels) if valid_pixels is not None else None,
                "quality": "zjištěno" if valid_pixels is not None else "neznámá",
            }
        )
    return series


def _sentinel2_evalscript() -> str:
    return """
    //VERSION=3
    function setup() {
      return {
        input: [{bands: ["B03", "B04", "B08", "B05", "SCL", "dataMask"]}],
        output: {bands: 6
      }
      };
    }
    function evaluatePixel(samples) {
      let ndwi = (samples.B03 - samples.B08) / (samples.B03 + samples.B08);
      let ndti = (samples.B04 - samples.B03) / (samples.B04 + samples.B03);
      let ndci = (samples.B05 - samples.B04) / (samples.B05 + samples.B04);
      let valid = samples.dataMask && samples.SCL !== 3 && samples.SCL !== 8 && samples.SCL !== 9 && samples.SCL !== 10 && samples.SCL !== 11;
      return [
        valid ? ndwi : 0,
        valid ? ndti : 0,
        valid ? ndci : 0,
        samples.B03,
        samples.B04,
        valid ? 1 : 0,
      ];
    }
    """


def analyze_pond(pond_id: str, date_from: str, date_to: str) -> dict[str, Any]:
    pond = get_pond_by_id(pond_id)
    if not pond:
        return {"status": "not_available", "message": "Rybník nebyl nalezen nebo není dostupný pro analýzu."}

    if not has_real_copernicus():
        return demo_data.generate_demo_analysis(pond_id, date_from, date_to)

    geometry = pond.get("geometry")
    if not geometry:
        return {"status": "not_available", "message": "Pro daný rybník není k dispozici polygon pro analýzu."}

    try:
        api_response = _sentinel_hub_statistics(geometry, date_from, date_to, _sentinel2_evalscript())
    except (requests.RequestException, ValueError) as exc:
        return {
            "status": "error",
            "message": f"Sentinel Hub nevrátil očekávaná data: {exc}",
            "quality_summary": {"data_quality": "nedostupná", "reliability": "nízká", "limitations": "Chyba při přístupu ke Sentinel Hub."},
        }

    timeseries = _extract_time_series(api_response)
    metrics = {
        "average_ndwi": round(sum(item["ndwi"] for item in timeseries if item.get("ndwi") is not None) / max(1, len([item for item in timeseries if item.get("ndwi") is not None])), 3) if timeseries else None,
        "average_ndti": round(sum(item["ndti"] for item in timeseries if item.get("ndti") is not None) / max(1, len([item for item in timeseries if item.get("ndti") is not None])), 3) if timeseries else None,
        "average_ndci": round(sum(item["ndci"] for item in timeseries if item.get("ndci") is not None) / max(1, len([item for item in timeseries if item.get("ndci") is not None])), 3) if timeseries else None,
        "water_area_estimate_m2": None,
    }
    quality = {
        "data_quality": "částečně dostupná" if timeseries else "nedostupná",
        "valid_pixels": sum(item["valid_pixels"] for item in timeseries if item.get("valid_pixels") is not None) if timeseries else 0,
        "reliability": "střední" if timeseries else "nízká",
        "limitations": "Nedostatečné pokrytí nebo nízká validita dat může ovlivnit spolehlivost odhadu.",
    }
    return {
        "status": "ok",
        "pond_id": pond["pond_id"],
        "pond_name": pond["name"],
        "municipality": pond.get("municipality", "neznámá"),
        "date_from": date_from,
        "date_to": date_to,
        "source": "Copernicus Sentinel-2 (Statistical API)",
        "metrics": metrics,
        "quality_summary": quality,
        "timeseries": timeseries,
        "warning": "NDWI a NDTI jsou orientační satelitní indikátory. Nevypovídají o přímé chemické nebo mikrobiologické kvalitě vody.",
        "ndwi_threshold": DEFAULT_NDWI_THRESHOLD,
    }


def analyze_algae_bloom(pond_id: str, date_from: str, date_to: str) -> dict[str, Any]:
    if not has_real_copernicus():
        return demo_data.generate_demo_algae_bloom(pond_id, date_from, date_to)

    analysis = analyze_pond(pond_id, date_from, date_to)
    if analysis.get("status") != "ok":
        return {
            "status": "not_available",
            "source": "sentinel-2",
            "category": "Nedostatek dat",
            "interpretation": "Pro dané období nebyly k dispozici dostatečné satelitní údaje pro experimentální posouzení algální biomasy.",
            "quality": analysis.get("quality_summary", {}),
        }

    ndci_values = [item["ndci"] for item in analysis.get("timeseries", []) if item.get("ndci") is not None]
    mean_ndci = sum(ndci_values) / max(len(ndci_values), 1)
    if mean_ndci > 0.24:
        category = "Možný signál vodního květu"
    elif mean_ndci > 0.18:
        category = "Zvýšená algální biomasa"
    else:
        category = "Bez výrazné změny"

    return {
        "status": "ok",
        "source": "Sentinel-2 NDCI",
        "ndci_trend": analysis.get("timeseries", []),
        "category": category,
        "interpretation": "NDCI je orientační indikátor chlorofylu-a a fytoplanktonové biomasy. Nepředstavuje přímé potvrzení sinic, cyanotoxinů ani infekčních agens.",
        "quality": analysis.get("quality_summary", {}),
    }
