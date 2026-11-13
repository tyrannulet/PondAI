from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


DEMO_PONDS = {
    "ritka-pond-1": {
        "pond_id": "ritka-pond-1",
        "name": "Rybník v Řitce",
        "municipality": "Řítek",
        "area_m2": 142500,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [14.4383, 49.3218],
                    [14.4402, 49.3222],
                    [14.4415, 49.3211],
                    [14.4398, 49.3199],
                    [14.4383, 49.3218],
                ]
            ],
        },
    },
    "lazne-pond-2": {
        "pond_id": "lazne-pond-2",
        "name": "Bezejmenný rybník",
        "municipality": "Lázně Bělohrad",
        "area_m2": 87500,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [15.6655, 50.4160],
                    [15.6666, 50.4168],
                    [15.6682, 50.4162],
                    [15.6674, 50.4149],
                    [15.6655, 50.4160],
                ]
            ],
        },
    },
}


def get_demo_ponds_for_municipality(municipality: str | None = None) -> list[dict[str, Any]]:
    text = (municipality or "").strip().lower()
    results: list[dict[str, Any]] = []
    for item in DEMO_PONDS.values():
        if not text or text in item["municipality"].lower() or text in item["name"].lower():
            results.append(item)
    return results


def _iso_dates(start: str | None, end: str | None) -> tuple[date, date]:
    start_day = date.fromisoformat(start) if start else date(2025, 1, 1)
    end_day = date.fromisoformat(end) if end else date(2025, 12, 31)
    if end_day < start_day:
        start_day, end_day = end_day, start_day
    return start_day, end_day


def _generate_period_series(start: date, end: date) -> list[date]:
    cursor = start
    items: list[date] = []
    while cursor <= end:
        items.append(cursor)
        cursor += timedelta(days=10)
    if not items:
        items = [start]
    if items[-1] != end:
        items[-1] = end
    return items


def generate_demo_analysis(pond_id: str, date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    pond = DEMO_PONDS.get(pond_id) or next(iter(DEMO_PONDS.values()))
    start_day, end_day = _iso_dates(date_from, date_to)
    periods = _generate_period_series(start_day, end_day)
    ndwi_values = [0.11, 0.18, 0.22, 0.15, 0.09, 0.26, 0.20, 0.17, 0.14, 0.12]
    ndti_values = [0.28, 0.23, 0.19, 0.21, 0.18, 0.16, 0.12, 0.15, 0.18, 0.22]
    water_pct = [62, 66, 73, 70, 68, 76, 72, 69, 65, 63]
    ndci_values = [0.12, 0.14, 0.21, 0.18, 0.16, 0.25, 0.22, 0.19, 0.17, 0.16]
    valid_pixels = [5300, 5900, 6200, 6450, 6100, 6550, 6300, 6000, 5750, 5600]
    timeseries: list[dict[str, Any]] = []
    for index, current_day in enumerate(periods[: len(ndwi_values)]):
        timeseries.append(
            {
                "date": current_day.isoformat(),
                "ndwi": round(ndwi_values[index], 3),
                "ndti": round(ndti_values[index], 3),
                "water_percent": round(water_pct[index], 2),
                "ndci": round(ndci_values[index], 3),
                "valid_pixels": valid_pixels[index],
                "quality": "dobrá" if valid_pixels[index] > 5000 else "omezená",
                "cloud_cover": "nízká",
            }
        )

    average_ndwi = round(sum(item["ndwi"] for item in timeseries) / max(len(timeseries), 1), 3)
    average_ndti = round(sum(item["ndti"] for item in timeseries) / max(len(timeseries), 1), 3)
    average_ndci = round(sum(item["ndci"] for item in timeseries) / max(len(timeseries), 1), 3)
    average_water = round(sum(item["water_percent"] for item in timeseries) / max(len(timeseries), 1), 2)

    algae_signal = "Bez výrazné změny"
    if average_ndci > 0.2:
        algae_signal = "Zvýšená algální biomasa"
    if average_ndci > 0.25:
        algae_signal = "Možný signál vodního květu"

    return {
        "status": "demo",
        "demo_mode": True,
        "warning": "DEMO REŽIM – zobrazená data jsou simulovaná, nejde o skutečnou satelitní analýzu.",
        "pond_id": pond["pond_id"],
        "pond_name": pond["name"],
        "municipality": pond["municipality"],
        "date_from": start_day.isoformat(),
        "date_to": end_day.isoformat(),
        "source": "Sentinel-2 demo dataset",
        "quality_summary": {
            "data_quality": "dobrá",
            "valid_pixels": int(sum(item["valid_pixels"] for item in timeseries) / max(len(timeseries), 1)),
            "reliability": "střední až dobrá pro větší rybník",
            "limitations": "Nízké rozlišení a simulovaná data neodrážejí skutečnou chemickou kvalitu vody.",
        },
        "metrics": {
            "average_ndwi": average_ndwi,
            "average_ndti": average_ndti,
            "average_ndci": average_ndci,
            "average_water_percent": average_water,
            "water_area_estimate_m2": round(pond["area_m2"] * (average_water / 100), 0),
        },
        "timeseries": timeseries,
        "biological_quality": {
            "ndci_value": average_ndci,
            "algae_signal": algae_signal,
            "interpretation": "NDCI naznačuje omezený nárůst algální biomasy, ale nejedná se o potvrzení sinic nebo cyanotoxinů.",
            "reliability": "Experimentální indikace, vhodné pro screening a následnou terénní kontrolu.",
        },
        "ice": {
            "status": "not_available",
            "message": "Pro demo režim nejsou k dispozici simulovaná data zalednění.",
        },
    }


def generate_demo_algae_bloom(pond_id: str, date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    base = generate_demo_analysis(pond_id, date_from, date_to)
    ndci = base["metrics"]["average_ndci"]
    if ndci > 0.2:
        category = "Zvýšená algální biomasa"
    elif ndci > 0.1:
        category = "Bez výrazné změny"
    else:
        category = "Bez výrazné změny"

    return {
        "status": "demo",
        "source": "simulated",
        "ndci_trend": base["timeseries"],
        "category": category,
        "interpretation": "Jedná se o experimentální orientační indikaci. NDCI neodhaluje koncentraci cyanotoxinů ani konkrétní druhy sinic.",
        "quality": base["quality_summary"],
    }
