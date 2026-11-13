from __future__ import annotations

import json
import logging
import math
import re
import calendar
import unicodedata
from datetime import date
from typing import Any

from scripts.config import get_featherless_config, has_real_featherless
from scripts.geo_sources import find_ponds
from scripts.satellite import analyze_algae_bloom, analyze_pond

MUNICIPALITY_ALIASES = {
    "prague": "Praha",
    "praze": "Praha",
    "mníšku pod brdy": "Mníšek pod Brdy",
    "valmez": "Valašské Meziříčí",
    "valmezu": "Valašské Meziříčí",
    "valašském meziříčí": "Valašské Meziříčí",
    "valašským meziříčím": "Valašské Meziříčí",
    "hk": "Hradec Králové",
    "hradecku": "Hradec Králové",
    "čb": "České Budějovice",
    "cb": "České Budějovice",
    "českých budějovicích": "České Budějovice",
    "mb": "Mladá Boleslav",
    "mladé boleslavi": "Mladá Boleslav",
}
MONTH_COUNTS = {
    "jeden": 1,
    "jednu": 1,
    "one": 1,
    "dva": 2,
    "dvě": 2,
    "two": 2,
    "tri": 3,
    "tři": 3,
    "třech": 3,
    "three": 3,
    "čtyři": 4,
    "ctyri": 4,
    "four": 4,
    "pět": 5,
    "pet": 5,
    "five": 5,
}

try:
    from openai import OpenAI, OpenAIError
except ImportError:  # pragma: no cover
    OpenAI = None
    OpenAIError = Exception

LOGGER = logging.getLogger(__name__)
ENGLISH_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

def _extract_years(text: str) -> list[str]:
    return re.findall(r"\b(20\d{2})\b", text)


def _extract_date_range(prompt: str) -> tuple[str | None, str | None]:
    date_matches = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", prompt)
    if len(date_matches) >= 2:
        return date_matches[0], date_matches[1]
    years = _extract_years(prompt)
    if len(years) >= 1:
        start_year = years[0]
        end_year = years[-1]
        return f"{start_year}-01-01", f"{end_year}-12-31"
    month_match = re.search(
        r"\b(?:posledn(?:í|ím|ích)\s+(?:(\d+|jeden|jednu|dva|dvě|tri|tři|třech|čtyři|ctyri|pět|pet)\s+)?měsíc(?:e|ů)?|(?:last|past|previous)\s+(?:(\d+|one|two|three|four|five)\s+)?months?)\b",
        prompt,
        flags=re.IGNORECASE,
    )
    if month_match:
        count = month_match.group(1) or month_match.group(2)
        month_count = int(count) if count and count.isdigit() else MONTH_COUNTS.get((count or "one").casefold(), 1)
        end = date.today()
        month_index = end.year * 12 + end.month - 1 - month_count
        year, month = divmod(month_index, 12)
        start = date(year, month + 1, min(end.day, calendar.monthrange(year, month + 1)[1]))
        return start.isoformat(), end.isoformat()
    return None, None


def _canonicalize_municipality(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip(" \t\r\n.,;:!?")
    return MUNICIPALITY_ALIASES.get(cleaned.casefold(), cleaned)


def _normalize_municipality_with_featherless(prompt: str) -> str | None:
    config = get_featherless_config()
    if not has_real_featherless() or OpenAI is None:
        return None

    client = OpenAI(
        base_url=config.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
        api_key=config["FEATHERLESS_API_KEY"],
        timeout=30,
    )
    try:
        response = client.chat.completions.create(
            model=config.get("FEATHERLESS_MODEL", "Qwen/Qwen3-32B"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Understand the full request and identify the Czech municipality "
                        "where the water body should be searched. Separate the municipality "
                        "from the date range (for example, 'in Řitce in 2025' means "
                        "municipality Řitka and year 2025). Convert inflected Czech names "
                        "to the official RÚIAN base form, and recognize common aliases "
                        "(Valmez means Valašské Meziříčí). Never invent a municipality or "
                        "treat a year as one. Return only JSON "
                        "{\"municipality\": \"...\"}; if absent or uncertain, return "
                        "{\"municipality\": null}."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=80,
        )
        content = response.choices[0].message.content
        result = json.loads(content or "{}")
        municipality = result.get("municipality")
        if not isinstance(municipality, str) or not municipality.strip():
            return None
        return _canonicalize_municipality(municipality)
    except (OpenAIError, json.JSONDecodeError, ValueError, TypeError, IndexError) as exc:
        LOGGER.warning(
            "Featherless municipality normalization failed (%s); using local normalization.",
            type(exc).__name__,
        )
        return None


def _extract_municipality(prompt: str) -> str | None:
    stop_words = (
        r"(?:a|za|od|do|pro|během|roce|roku|poslední|minulý|minulém|celý|celou|"
        r"for|during|over|from|to|last|past|previous|year)"
    )
    location = r"(?:v|ve|in|near|around)"
    patterns = [
        rf"\b{location}\s+(?:(?:the\s+)?(?:city|town|municipality)\s+of\s+|(?:městě|obci)\s+)?([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s-]+?)(?=\s+{stop_words}\b|\s+(?:v|ve|in)\s+(?:roce|roku|year)\b|[,;.!?]|$)",
        rf"\b(?:obec|město|městě|city|town|municipality)\s+(?:of\s+)?([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s-]+?)(?=\s+{stop_words}\b|[,;.!?]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            text = match.group(1).strip()
            if text and len(text) > 1:
                return _canonicalize_municipality(text)
    return None


def _extract_pond_name(prompt: str) -> str | None:
    name_pattern = (
        r"([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s-]+?)"
        r"(?=\s+(?:v|ve|u|a|za|od|do|pro|během|roce|roku|analyzuj|analyzovat|"
        r"in|near|at|around|by|for|during|last|past|previous|year|analyze|analyse|named|called)\b"
        r"|[,;.!?]|$)"
    )
    match = re.search(
        rf"\brybník(?:u|a)?\s+(?:s\s+názvem\s+|nazvan(?:ý|ém|ého)?\s+){name_pattern}",
        prompt,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(
            rf"\b(?:ponds?|reservoirs?|lakes?|water bodies?)\s+(?:named|called)\s+{name_pattern}",
            prompt,
            flags=re.IGNORECASE,
        )
    if not match:
        match = re.search(
            rf"\brybník(?:u|a)?\s+(?!v\b|ve\b|u\b|a\b|na\b|podle\b|městě\b|obci\b){name_pattern}",
            prompt,
            flags=re.IGNORECASE,
        )
    if not match:
        match = re.search(
            rf"\b(?:ponds?|reservoirs?|lakes?)\s+(?!in\b|near\b|at\b|around\b|by\b|named\b|called\b){name_pattern}",
            prompt,
            flags=re.IGNORECASE,
        )
    if match:
        name = match.group(1).strip()
        return name or None
    return None


def _is_broad_pond_search(prompt: str) -> bool:
    lowered = prompt.casefold()
    return bool(
        re.search(r"\b(?:všechny|všech|každé|každý)\b", lowered)
        or re.search(r"\brybník(?:y|ů|ům|ech)\b", lowered)
        or re.search(r"\b(?:ponds|reservoirs|lakes|water bodies)\b", lowered)
    )


def _extract_water_body_type(prompt: str) -> str:
    lowered = prompt.casefold()
    if re.search(r"\b(?:all water bodies|all water features|water bodies|water body|všechny vodní plochy|vodní plochy)\b", lowered):
        return "all"
    if re.search(r"\b(?:reservoirs?|water reservoirs?|dams?|přehrad(?:a|y|ní)|vodní nádrž(?:e|í)?|nádrž(?:e|í))\b", lowered):
        return "reservoir"
    if re.search(r"\b(?:lakes?|jezer(?:o|a|u|em))\b", lowered):
        return "lake"
    return "pond"


def _requests_charts(prompt: str) -> bool:
    lowered = prompt.casefold()
    if re.search(r"\b(?:no|hide|without|don't show|do not show)\s+(?:the\s+)?(?:charts?|graphs?|plots?)\b", lowered):
        return False
    return bool(re.search(r"\b(?:charts?|graphs?|plots?|graf(?:y|u|em)?|diagram(?:y|u)?)\b", lowered))


def _dispatch_tool(function_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "find_ponds": lambda: find_ponds(
            arguments.get("municipality", ""),
            arguments.get("pond_name"),
            arguments.get("water_body_type", "pond"),
        ),
        "analyze_pond": lambda: analyze_pond(arguments.get("pond_id", ""), arguments.get("date_from", ""), arguments.get("date_to", "")),
    }
    if function_name not in allowed:
        raise ValueError(f"Unsupported tool: {function_name}")
    return allowed[function_name]()


def _series_values(timeseries: list[dict[str, Any]], metric: str) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for item in timeseries:
        value = item.get(metric)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if math.isfinite(value):
            values.append((str(item.get("date") or "unknown date"), float(value)))
    return values


def _monthly_average_values(
    timeseries: list[dict[str, Any]], metric: str
) -> dict[str, float]:
    monthly: dict[str, list[float]] = {}
    for item in timeseries:
        value = item.get(metric)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        try:
            month_key = date.fromisoformat(str(item.get("date", ""))).strftime("%Y-%m")
        except ValueError:
            continue
        monthly.setdefault(month_key, []).append(float(value))
    return {
        month: sum(values) / len(values)
        for month, values in sorted(monthly.items())
    }


def _summarize_chart(metric: str, label: str, timeseries: list[dict[str, Any]]) -> str:
    values = _series_values(timeseries, metric)
    if not values:
        return (
            f"{label}: no valid values were available to interpret "
            f"({len(timeseries)} intervals without values)."
        )
    start_date, start_value = values[0]
    end_date, end_value = values[-1]
    minimum = min(value for _, value in values)
    maximum = max(value for _, value in values)
    if len(values) == 1:
        trend = f"The only valid value is {start_value:g} ({start_date})"
    else:
        change = end_value - start_value
        direction = "increased" if change > 0 else "decreased" if change < 0 else "remained approximately stable"
        trend = (
            f"{direction} from {start_value:g} to {end_value:g} "
            f"between {start_date} and {end_date}"
        )
    summary = (
        f"{label}: {trend}; observed values ranged from "
        f"{minimum:g} to {maximum:g}."
    )
    missing_count = len(timeseries) - len(values)
    if missing_count:
        summary += f" {missing_count} of {len(timeseries)} intervals had no valid value."
    return summary


def _fallback_chart_interpretation(
    analysis: dict[str, Any], algae: dict[str, Any]
) -> str:
    timeseries = analysis.get("timeseries") or []
    algae_timeseries = algae.get("ndci_trend") or timeseries
    summaries = [
        _summarize_chart("water_percent", "Classified water-pixel share", timeseries)
        + " This is the share of classified pixels inside the mapped boundary, not water level or volume.",
        _summarize_chart("ndwi", "NDWI", timeseries)
        + " This is an average spectral water indicator, not the percentage of water-covered area.",
        _summarize_chart("ndti", "NDTI", timeseries)
        + " This is an optical proxy for suspended particles, not a laboratory turbidity measurement.",
        _summarize_chart("ndci", "NDCI", algae_timeseries)
        + " This is a rough proxy for chlorophyll/phytoplankton, not a direct measurement.",
        _summarize_chart("ice_percent", "Pixels classified as snow/ice", timeseries)
        + " This is a satellite screening classification, not confirmation that the water was frozen.",
    ]
    return (
        "\n".join(f"- {summary}" for summary in summaries)
        + "\nLimitation: Sentinel-2 pixels may include both water and shore; "
        "these indices are not laboratory measurements."
    )


def _interpret_analysis_charts(
    pond: dict[str, Any], analysis: dict[str, Any], algae: dict[str, Any]
) -> str:
    fallback = _fallback_chart_interpretation(analysis, algae)
    if not has_real_featherless() or OpenAI is None:
        return (
            "Automatic chart summary (AI interpretation is not configured):\n"
            + fallback
        )

    config = get_featherless_config()
    chart_data = {
        "pond": {
            "name": pond.get("name"),
            "municipality": pond.get("municipality"),
            "polygon_area_m2": pond.get("area_m2"),
        },
        "period": {
            "from": analysis.get("date_from"),
            "to": analysis.get("date_to"),
            "aggregation": "10-day intervals",
        },
        "data_quality": analysis.get("quality_summary"),
        "precalculated_trends": {
            "water_percent": _summarize_chart(
                "water_percent", "Classified water-pixel share", analysis.get("timeseries") or []
            ),
            "ndwi": _summarize_chart("ndwi", "NDWI", analysis.get("timeseries") or []),
            "ndti": _summarize_chart("ndti", "NDTI", analysis.get("timeseries") or []),
            "ndci": _summarize_chart(
                "ndci",
                "NDCI",
                algae.get("ndci_trend") or analysis.get("timeseries") or [],
            ),
            "possible_ice": _summarize_chart(
                "ice_percent", "Pixels classified as snow/ice", analysis.get("timeseries") or []
            ),
        },
        "water_area_estimate": {
            "definition": (
                "Percentage of valid pixels inside the mapped water-body polygon with NDWI "
                "above 0; this is not water level or volume."
            ),
            "observations": [
                {
                    "date": item.get("date"),
                    "percent": item.get("water_percent"),
                    "valid_pixels": item.get("valid_pixels"),
                }
                for item in analysis.get("timeseries", [])
            ],
        },
        "optical_indices": {
            "definition": (
                "NDWI = (green - NIR)/(green + NIR), a spectral water indicator. "
                "NDTI = (red - green)/(red + green), an optical proxy for suspended "
                "particles, not laboratory turbidity. NDCI = (red-edge - red)/"
                "(red-edge + red), a rough chlorophyll/phytoplankton screening signal, "
                "not confirmation of cyanobacteria or toxins."
            ),
            "observations": [
                {
                    "date": item.get("date"),
                    "ndwi": item.get("ndwi"),
                    "ndti": item.get("ndti"),
                    "ndci": (algae.get("ndci_trend") or analysis.get("timeseries", []))[index].get("ndci")
                    if index < len(algae.get("ndci_trend") or analysis.get("timeseries", []))
                    else None,
                    "valid_pixels": item.get("valid_pixels"),
                }
                for index, item in enumerate(analysis.get("timeseries", []))
            ],
        },
        "algae_screening": {
            "category": algae.get("category"),
            "interpretation": algae.get("interpretation"),
        },
    }
    system_prompt = (
        "You are an expert in geospatial analysis and remote sensing. Interpret only "
        "the supplied measurements. Reply in exactly five sections titled 'Water-pixel "
        "share', 'NDWI', 'NDTI', 'NDCI', and 'Possible snow/ice classification'. Use the precomputed trends as the source "
        "of truth for ranges and direction. In at most two short sentences per section, "
        "describe the trend and missing data, and finish the response. Exclude null "
        "values from ranges and never attribute a specific change to missing data. "
        "Do not invent causes or speculate. Water share is the percentage of pixels "
        "with NDWI > 0 inside a fixed polygon, not surface-area change, water level, "
        "or volume. A 0% share with valid pixels is a real classification result, not "
        "missing data. NDWI is an average spectral index, not a pixel share; 10 m "
        "pixels can mix water and shore. NDTI is an optical proxy for suspended "
        "particles, not laboratory turbidity. NDCI is a rough chlorophyll/"
        "phytoplankton proxy, not a direct measurement or confirmation of "
        "cyanobacteria or toxins. Snow/ice classifications are screening results, not "
        "confirmation that a water surface was frozen. Null values or zero valid pixels mean unavailable "
        "data. Report pixel counts exactly and do not call them low without evidence. "
        "Do not claim laboratory water quality or confirmed freezing."
    )
    try:
        client = OpenAI(
            base_url=config.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
            api_key=config["FEATHERLESS_API_KEY"],
            timeout=45,
        )
        response = client.chat.completions.create(
            model=config.get("FEATHERLESS_MODEL", "Qwen/Qwen3-32B"),
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(chart_data, ensure_ascii=False),
                },
            ],
            temperature=0.2,
            max_tokens=1200,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        choice = response.choices[0]
        content = choice.message.content
        if getattr(choice, "finish_reason", None) == "length":
            raise ValueError("AI chart interpretation was truncated by the token limit.")
        if isinstance(content, str) and content.strip():
            interpretation = content.strip()
            normalized = "".join(
                character
                for character in unicodedata.normalize("NFKD", interpretation.casefold())
                if not unicodedata.combining(character)
            )
            speculative_phrases = (
                "may ",
                "might ",
                "suggest",
                "probably",
                "season",
                "pollution",
                "due to",
            )
            if any(phrase in normalized for phrase in speculative_phrases):
                raise ValueError("AI included unsupported explanations for observed trends.")
            if all(label in normalized for label in ("ndwi", "ndti", "ndci", "ice")) and (
                "water-pixel share" in normalized or "water share" in normalized
            ):
                return interpretation
            raise ValueError("The AI did not interpret all four charts.")
        raise ValueError("Featherless returned an empty chart interpretation.")
    except (OpenAIError, ValueError, TypeError, IndexError) as exc:
        LOGGER.warning(
            "Featherless chart interpretation failed (%s); using data summary.",
            type(exc).__name__,
        )
        reason = (
            "The AI returned an incomplete or insufficiently cautious chart interpretation"
            if isinstance(exc, ValueError)
            else f"AI interpretation was unavailable ({type(exc).__name__})"
        )
        return (
            f"{reason}; "
            "here is an automatic summary of the measured trends:\n"
            + fallback
        )


def _describe_candidate(candidate: dict[str, Any], index: int) -> str:
    number = candidate.get("number", index + 1)
    name = candidate.get("name") or "Unnamed water body"
    area = int(candidate.get("area_m2") or 0)
    area_text = f"{area:,}".replace(",", " ")
    hectares = f"{area / 10_000:.2f}"
    location = candidate.get("approx_location") or {}
    location_text = ""
    if location.get("latitude") is not None and location.get("longitude") is not None:
        location_text = (
            f", approximately {location['latitude']:.4f}° N, "
            f"{location['longitude']:.4f}° E"
        )
    return f"{number}. {name} ({candidate.get('water_body_type', 'water body')}) — {area_text} m² ({hectares} ha){location_text}"


def _plain_language_report(
    water_body: dict[str, Any],
    analysis: dict[str, Any],
    algae: dict[str, Any],
) -> str:
    name = water_body.get("name", "Water body")
    municipality = water_body.get("municipality")
    location = f" in {municipality}" if municipality else ""
    date_from = analysis.get("date_from", "unknown")
    date_to = analysis.get("date_to", "unknown")
    lines = [
        f"## Satellite report: {name}{location}",
        f"**Period:** {date_from} to {date_to}",
    ]

    timeseries = analysis.get("timeseries") or []
    water_values = _series_values(timeseries, "water_percent")
    if water_values:
        start_date, start_share = water_values[0]
        end_date, end_share = water_values[-1]
        low = min(value for _, value in water_values)
        high = max(value for _, value in water_values)
        lines.append(
            f"Satellite images classified {low:g}% to {high:g}% of the valid pixels "
            f"inside the mapped boundary as water. The share changed from "
            f"{start_share:g}% ({start_date}) to {end_share:g}% ({end_date}). "
            "This estimates visible surface-water coverage, not water depth or volume."
        )
    else:
        lines.append("There were no usable satellite observations of the water surface in this period.")

    category = algae.get("category")
    if category:
        lines.append(
            f"The satellite-based algae screening was: **{category}**. "
            "This is an optical screening signal, not a laboratory water-quality or toxin test."
        )
    else:
        lines.append(
            "Water quality cannot be confirmed from these satellite indicators alone; "
            "no laboratory measurements are included."
        )

    monthly_ndci = _monthly_average_values(timeseries, "ndci")
    if len(monthly_ndci) > 1:
        lowest_month = min(monthly_ndci, key=lambda month: monthly_ndci[month])
        highest_month = max(monthly_ndci, key=lambda month: monthly_ndci[month])
        if lowest_month != highest_month:
            lowest_label = date.fromisoformat(f"{lowest_month}-01")
            highest_label = date.fromisoformat(f"{highest_month}-01")
            lines.append(
                f"The algae-related satellite signal was lower in "
                f"{ENGLISH_MONTHS[lowest_label.month - 1]} {lowest_label.year} "
                f"({monthly_ndci[lowest_month]:.2f}) and higher in "
                f"{ENGLISH_MONTHS[highest_label.month - 1]} {highest_label.year} "
                f"({monthly_ndci[highest_month]:.2f}). A higher reading is not by "
                "itself proof of poorer water quality."
            )

    ice = analysis.get("ice") or {}
    ice_status = ice.get("status")
    detections = ice.get("observations") or []
    if ice_status == "possible_ice" and detections:
        found = ", ".join(
            f"{item.get('date')} ({item.get('ice_percent')}% of valid pixels)"
            for item in detections
        )
        lines.append(
            f"**Possible surface ice/snow classification:** {found}. "
            "This is a satellite screening, not confirmation that the water itself was frozen. "
            "A flag requires at least 10 valid pixels and at least 2 pixels (15% or more) "
            "classified as snow/ice."
        )
    elif ice_status == "no_ice_detected":
        lines.append(
            f"No possible ice/snow was classified in {ice.get('usable_intervals', 0)} "
            "usable satellite intervals. This does not prove that the water never froze; "
            "clouds and gaps between satellite visits can hide short events."
        )
    elif ice_status == "not_available":
        lines.append("Ice screening is unavailable for the simulated demo data.")
    else:
        lines.append(
            "Ice status is inconclusive because there were too few clear, valid satellite pixels."
        )

    warning = analysis.get("warning")
    if warning:
        lines.append(f"**Data note:** {warning}")
    return "\n\n".join(lines)


def _analyze_selected_pond(
    pond: dict[str, Any],
    date_from: str,
    date_to: str,
    include_charts: bool = False,
) -> dict[str, Any]:
    analysis = analyze_pond(pond["pond_id"], date_from, date_to)
    algae = analyze_algae_bloom(pond["pond_id"], date_from, date_to)
    report = _plain_language_report(pond, analysis, algae)
    chart_interpretation = (
        _interpret_analysis_charts(pond, analysis, algae) if include_charts else None
    )
    return {
        "response": report,
        "analysis": {
            **analysis,
            "algae": algae,
            "report": report,
            "graph_interpretation": chart_interpretation,
        },
        "selected_pond": pond,
        "status": "completed",
    }


def _call_featherless_tools(
    prompt: str,
    state: dict[str, Any] | None = None,
    normalized_municipality: str | None = None,
) -> dict[str, Any]:
    config = get_featherless_config()
    api_key = config.get("FEATHERLESS_API_KEY")
    if not has_real_featherless() or OpenAI is None:
        raise ValueError("Featherless is not configured.")

    client = OpenAI(base_url=config.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"), api_key=api_key)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "find_ponds",
                "description": "Search a Czech municipality for ponds, reservoirs, lakes, or all mapped water bodies and return candidates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "municipality": {"type": "string", "description": "Czech municipality name"},
                        "pond_name": {"type": "string", "description": "Optional water-body name"},
                        "water_body_type": {
                            "type": "string",
                            "enum": ["pond", "reservoir", "lake", "all"],
                            "description": "Select pond, reservoir, lake, or all mapped water bodies",
                        },
                    },
                    "required": ["municipality"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_pond",
                "description": "Analyze satellite observations for a selected water body and date range.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pond_id": {"type": "string", "description": "Water-body ID from the geodata search"},
                        "date_from": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                        "date_to": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    },
                    "required": ["pond_id", "date_from", "date_to"],
                },
            },
        },
    ]

    system_prompt = (
        "You are PondWatch AI, an assistant for Czech water bodies. Understand Czech "
        "and English requests, including inflected municipality names and local aliases. "
        "Normalize a municipality before searching, then use only the local find_ponds "
        "and analyze_pond tools. Reply in English. Write a concise, plain-language "
        "report by default; only discuss charts when the user asks for them. You are "
        "also an expert in geospatial analysis and remote sensing. NDWI is a spectral "
        "water indicator; water-pixel share is a classification inside a fixed polygon, "
        "not water level or volume. Sentinel-2 pixels can mix water and shore, and "
        "clouds, shadows, vegetation, turbidity, season, and valid-pixel count affect "
        "results. NDTI is only an optical proxy for suspended particles and NDCI is a "
        "rough chlorophyll/phytoplankton screening signal; neither is a laboratory "
        "measurement. Interpret available data and missing observations without "
        "inventing causes. Snow/ice-class pixels are only a satellite screening, not "
        "confirmation that the water itself was frozen. Do not claim laboratory water "
        "quality or confirmed freezing."
    )
    if normalized_municipality:
        system_prompt += (
            f" The municipality normalization step identified the official name "
            f"'{normalized_municipality}'. Use exactly this name as municipality in "
            "the find_ponds tool."
        )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    if state and state.get("chat_history"):
        for item in state["chat_history"]:
            role = "assistant" if item["role"] == "assistant" else "user"
            messages.append({"role": role, "content": item["content"]})

    for _ in range(6):
        completion = client.chat.completions.create(model=config.get("FEATHERLESS_MODEL", "Qwen/Qwen3-32B"), messages=messages, tools=tools, tool_choice="auto")
        message = completion.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            return {"response": message.content or "I could not produce a final answer.", "analysis": None}

        for tool_call in tool_calls:
            func_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            if func_name == "find_ponds" and normalized_municipality:
                arguments["municipality"] = normalized_municipality
            if func_name == "find_ponds":
                arguments.setdefault("water_body_type", _extract_water_body_type(prompt))
            tool_result = _dispatch_tool(func_name, arguments)
            call_message = tool_call.model_dump()
            call_message["function"]["arguments"] = json.dumps(arguments, ensure_ascii=False)
            messages.append({"role": "assistant", "content": "", "tool_calls": [call_message]})
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(tool_result, ensure_ascii=False)})

        last_response = client.chat.completions.create(model=config.get("FEATHERLESS_MODEL", "Qwen/Qwen3-32B"), messages=messages)
        text = last_response.choices[0].message.content
        if text:
            return {"response": text, "analysis": None}

    return {"response": "The agent could not complete the analysis within the allowed number of steps.", "analysis": None}


def run_agent(prompt: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    if state is None:
        state = {}
    if _requests_charts(prompt):
        state["show_charts"] = True
    raw_municipality = _extract_municipality(prompt)
    municipality = raw_municipality or state.get("last_municipality")
    normalized_municipality = None
    is_pond_choice = bool(state.get("pending_candidates")) and re.fullmatch(r"\s*\d+\s*", prompt)
    if (
        has_real_featherless()
        and not is_pond_choice
        and (raw_municipality or not state.get("selected_pond"))
    ):
        normalized_municipality = _normalize_municipality_with_featherless(prompt)
        if normalized_municipality:
            municipality = normalized_municipality

    previous_municipality = state.get("last_municipality")
    municipality_changed = bool(
        municipality
        and previous_municipality
        and _canonicalize_municipality(municipality).casefold()
        != _canonicalize_municipality(previous_municipality).casefold()
    )
    if municipality_changed or _is_broad_pond_search(prompt):
        state["selected_pond"] = None
        state["pending_candidates"] = None
        state["pending_ponds"] = None
        state["last_pond_name"] = None
        state["last_date_from"] = None
        state["last_date_to"] = None

    if has_real_featherless() and not is_pond_choice:
        try:
            ai_result = _call_featherless_tools(
                prompt, state, normalized_municipality
            )
            if ai_result.get("analysis") is not None or ai_result.get("status"):
                return ai_result
        except Exception:
            pass

    pond_name = _extract_pond_name(prompt)
    if pond_name is None:
        pond_name = state.get("last_pond_name")
    date_from, date_to = _extract_date_range(prompt)
    if date_from and date_to:
        state["last_date_from"] = date_from
        state["last_date_to"] = date_to
    elif state.get("pending_candidates"):
        date_from = state.get("last_date_from")
        date_to = state.get("last_date_to")

    if not municipality:
        return {"response": "I could not identify the municipality. Please specify a Czech municipality, for example 'a pond in Řitka'.", "analysis": None, "status": "awaiting_input"}

    state["last_municipality"] = municipality
    state["last_pond_name"] = pond_name

    if state.get("pending_candidates") and re.search(r"\b\d+\b", prompt):
        selection = re.search(r"\b(\d+)\b", prompt)
        if selection:
            choice = int(selection.group(1))
            candidates = state["pending_candidates"]
            selected_candidate = next((item for item in candidates if int(item["number"]) == choice), None)
            if selected_candidate:
                selected = next(
                    (
                        item
                        for item in state.get("pending_ponds", [])
                        if item.get("pond_id") == selected_candidate["pond_id"]
                    ),
                    selected_candidate,
                )
                state["selected_pond"] = selected
                if not date_from or not date_to:
                    state["pending_candidates"] = None
                    state["pending_ponds"] = None
                    return {"response": "Selected: " + selected["name"] + ". Please specify a date range, for example '2025-01-01 to 2025-12-31'.", "analysis": None, "selected_pond": selected, "status": "awaiting_input"}
                state["pending_candidates"] = None
                state["pending_ponds"] = None
                return _analyze_selected_pond(
                    selected, date_from, date_to, bool(state.get("show_charts"))
                )

    explicit_municipality = _extract_municipality(prompt)
    if (
        state.get("selected_pond")
        and date_from
        and date_to
        and explicit_municipality is None
        and not state.get("pending_candidates")
    ):
        return _analyze_selected_pond(
            state["selected_pond"], date_from, date_to, bool(state.get("show_charts"))
        )

    pond_search = find_ponds(
        municipality, pond_name, _extract_water_body_type(prompt)
    )
    if pond_search.get("status") == "multiple":
        state["pending_candidates"] = pond_search["candidates"]
        state["pending_ponds"] = pond_search.get("result", [])
        choices = "; ".join(
            _describe_candidate(item, index)
            for index, item in enumerate(pond_search["candidates"])
        )
        return {
            "response": (
                f"Using the municipality “{pond_search.get('municipality', municipality)}”. "
                "I found multiple water bodies. Choose one on the map or from the list below: "
                + choices
                + "."
            ),
            "analysis": None,
            "status": "awaiting_choice",
            "choices": pond_search["candidates"],
        }

    if pond_search.get("status") in ("not_found", "error"):
        return {"response": pond_search.get("message", "No water body was found. Please refine your request."), "analysis": None, "status": "not_found"}

    pond = pond_search["result"][0]
    state["selected_pond"] = pond
    if not date_from or not date_to:
        canonical_name = pond_search.get("municipality", municipality)
        return {
            "response": (
                f"Using the municipality “{canonical_name}”. "
                f"Found: {pond['name']}. Please specify a date range, "
                "for example “2025-01-01 to 2025-12-31”."
            ),
            "analysis": None,
            "selected_pond": pond,
            "status": "awaiting_input",
        }

    return _analyze_selected_pond(
        pond, date_from, date_to, bool(state.get("show_charts"))
    )
