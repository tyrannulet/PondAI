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
    "dva": 2,
    "dvě": 2,
    "tri": 3,
    "tři": 3,
    "třech": 3,
    "čtyři": 4,
    "ctyri": 4,
    "pět": 5,
    "pet": 5,
}

try:
    from openai import OpenAI, OpenAIError
except ImportError:  # pragma: no cover
    OpenAI = None
    OpenAIError = Exception

LOGGER = logging.getLogger(__name__)

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
        r"\bposledn(?:í|ím|ích)\s+(?:(\d+|jeden|jednu|dva|dvě|tri|tři|třech|čtyři|ctyri|pět|pet)\s+)?měsíc(?:e|ů)?\b",
        prompt,
        flags=re.IGNORECASE,
    )
    if month_match:
        count = month_match.group(1)
        month_count = int(count) if count and count.isdigit() else MONTH_COUNTS.get((count or "jeden").casefold(), 1)
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
                        "Nejprve pochop celý uživatelský požadavek a z něj urč jednu obec, "
                        "ve které se má hledat rybník. Odděl název obce od časového období "
                        "(například „v Řitce v roce 2025“ obsahuje obec Řitka a rok 2025). "
                        "Převeď skloňovaný název do úředního základního tvaru používaného "
                        "v RÚIAN (např. Řitce → Řitka), rozpoznej známé zkratky a místní "
                        "názvy (např. Valmez → Valašské Meziříčí). Obec nevymýšlej a "
                        "nepovažuj rok ani jinou časovou informaci za název obce. Vrať "
                        "pouze JSON objekt {\"municipality\": \"...\"}; pokud obec v "
                        "požadavku není nebo si nejsi jistý, vrať "
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
    stop_words = r"(?:a|za|od|do|pro|během|roce|roku|poslední|minulý|minulém|celý|celou)"
    patterns = [
        rf"\b(?:v|ve)\s+([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s-]+?)(?=\s+{stop_words}\b|\s+(?:v|ve)\s+(?:roce|roku)\b|[,;.!?]|$)",
        rf"\b(?:obec|město|městě)\s+([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s-]+?)(?=\s+{stop_words}\b|[,;.!?]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            text = match.group(1).strip()
            if text and len(text) > 1:
                return _canonicalize_municipality(text)
    return None


def _extract_pond_name(prompt: str) -> str | None:
    match = re.search(r"rybník(?:\s+u\s+)?(?:s\s+názvem\s+|nazvan(?:ý|ém|ého)?\s+|\s+)([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s-]+?)(?:\s+v\s+|\s+za\b|\.|\?|!|$)", prompt, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _dispatch_tool(function_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "find_ponds": lambda: find_ponds(arguments.get("municipality", ""), arguments.get("pond_name")),
        "analyze_pond": lambda: analyze_pond(arguments.get("pond_id", ""), arguments.get("date_from", ""), arguments.get("date_to", "")),
    }
    if function_name not in allowed:
        raise ValueError(f"Nedovolený nástroj: {function_name}")
    return allowed[function_name]()


def _ndci_summary(algae: dict[str, Any]) -> str:
    trend = algae.get("ndci_trend") or []
    if not trend:
        return "n/a"
    first = trend[0].get("ndci")
    return str(first) if first is not None else "n/a"


def _series_values(timeseries: list[dict[str, Any]], metric: str) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for item in timeseries:
        value = item.get(metric)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if math.isfinite(value):
            values.append((str(item.get("date") or "neznámé datum"), float(value)))
    return values


def _summarize_chart(metric: str, label: str, timeseries: list[dict[str, Any]]) -> str:
    values = _series_values(timeseries, metric)
    if not values:
        return (
            f"{label}: za toto období nejsou platné hodnoty k interpretaci "
            f"({len(timeseries)} intervalů bez hodnot)."
        )
    start_date, start_value = values[0]
    end_date, end_value = values[-1]
    minimum = min(value for _, value in values)
    maximum = max(value for _, value in values)
    if len(values) == 1:
        trend = f"Jediná platná hodnota je {start_value:g} ({start_date})"
    else:
        change = end_value - start_value
        direction = "vzrostla" if change > 0 else "klesla" if change < 0 else "zůstala přibližně stejná"
        trend = (
            f"mezi {start_date} a {end_date} {direction} "
            f"z {start_value:g} na {end_value:g}"
        )
    summary = (
        f"{label}: {trend}; rozsah pozorovaných hodnot je "
        f"{minimum:g} až {maximum:g}."
    )
    missing_count = len(timeseries) - len(values)
    if missing_count:
        summary += f" Bez platné hodnoty je {missing_count} z {len(timeseries)} intervalů."
    return summary


def _fallback_chart_interpretation(
    analysis: dict[str, Any], algae: dict[str, Any]
) -> str:
    timeseries = analysis.get("timeseries") or []
    algae_timeseries = algae.get("ndci_trend") or timeseries
    summaries = [
        _summarize_chart("water_percent", "Podíl vodních pixelů", timeseries)
        + " Jde o podíl klasifikovaných pixelů uvnitř polygonu, ne o hladinu či objem vody.",
        _summarize_chart("ndwi", "NDWI", timeseries)
        + " Je to průměrný spektrální indikátor vody, ne procento vodní plochy.",
        _summarize_chart("ndti", "NDTI", timeseries)
        + " Je to optický proxy suspendovaných částic, ne laboratorní měření zákalu.",
        _summarize_chart("ndci", "NDCI", algae_timeseries)
        + " Je to orientační proxy chlorofylu/fytoplanktonu, ne jeho přímé měření.",
    ]
    return (
        "\n".join(f"- {summary}" for summary in summaries)
        + "\nOmezení: Sentinel-2 pixely o velikosti 10 m mohou zahrnovat současně "
        "vodu i břeh; indexy nejsou laboratorní rozbor."
    )


def _interpret_analysis_charts(
    pond: dict[str, Any], analysis: dict[str, Any], algae: dict[str, Any]
) -> str:
    fallback = _fallback_chart_interpretation(analysis, algae)
    if not has_real_featherless() or OpenAI is None:
        return (
            "Automatické shrnutí grafů (AI interpretace není nakonfigurována):\n"
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
            "aggregation": "desetidenní časové intervaly",
        },
        "data_quality": analysis.get("quality_summary"),
        "precalculated_trends": {
            "water_percent": _summarize_chart(
                "water_percent", "Podíl vodních pixelů", analysis.get("timeseries") or []
            ),
            "ndwi": _summarize_chart("ndwi", "NDWI", analysis.get("timeseries") or []),
            "ndti": _summarize_chart("ndti", "NDTI", analysis.get("timeseries") or []),
            "ndci": _summarize_chart(
                "ndci",
                "NDCI",
                algae.get("ndci_trend") or analysis.get("timeseries") or [],
            ),
        },
        "water_area_estimate": {
            "definition": (
                "Procento platných pixelů uvnitř rybničního polygonu, jejichž NDWI "
                "překročilo práh 0; nejde o výšku hladiny ani objem vody."
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
                "NDWI = (zelené - NIR)/(zelené + NIR), orientační spektrální "
                "indikátor vody. NDTI = (červené - zelené)/(červené + zelené), "
                "optický proxy suspendovaných látek, ne laboratorní zákal. "
                "NDCI = (red-edge - červené)/(red-edge + červené), screening "
                "chlorofylu/fytoplanktonu, ne potvrzení sinic ani toxinů."
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
        "Jsi expert na geoinformatiku a dálkový průzkum Země. Interpretuj pouze "
        "dodaná měření. Odpověz česky přesně čtyřmi částmi a těmito nadpisy: "
        "„Podíl vodních pixelů“, „NDWI“, „NDTI“, „NDCI“. Použij předpočítané trendy "
        "jako zdroj pravdy pro rozsah a směr. V každé části maximálně dvěma krátkými "
        "větami popiš trend a chybějící data; odpověď dokonči. Hodnoty null zcela "
        "vynech z rozsahu a nikdy je nepřiřazuj konkrétní odchylce. Neuváděj příčiny, "
        "hypotézy ani spekulativní výrazy jako "
        "„může naznačovat“. Podíl vody je procento pixelů s NDWI > 0 uvnitř pevného "
        "polygonu, ne změna rozlohy, hladina ani objem. Nulový podíl při kladném "
        "počtu validních pixelů je skutečný výsledek klasifikace, ne chybějící hodnota. "
        "NDWI je průměrný spektrální index, nikoli podíl pixelů; 10m pixely mohou "
        "míchat vodu a břeh. NDTI je optický proxy suspendovaných částic, ne laboratorní "
        "zákal. NDCI je orientační proxy chlorofylu/fytoplanktonu, ne jeho přímé "
        "měření ani potvrzení sinic/toxinů. Hodnoty označené null nebo s 0 validními "
        "pixely jsou nedostupné. Uváděj počty pixelů přesně podle dat a neoznačuj "
        "je za nízké bez podkladu. Netvrď laboratorní kvalitu vody ani zamrznutí."
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
            raise ValueError("AI interpretace byla useknuta limitem tokenů.")
        if isinstance(content, str) and content.strip():
            interpretation = content.strip()
            normalized = "".join(
                character
                for character in unicodedata.normalize("NFKD", interpretation.casefold())
                if not unicodedata.combining(character)
            )
            speculative_phrases = (
                "muze ",
                "mohou ",
                "naznac",
                "pravdepodob",
                "sezon",
                "znecisten",
                "vlivem",
            )
            if any(phrase in normalized for phrase in speculative_phrases):
                raise ValueError("AI uvedla nepodložené příčiny trendů.")
            if all(label in normalized for label in ("ndwi", "ndti", "ndci")) and (
                "vodnich pixel" in normalized or "podil vody" in normalized
            ):
                return interpretation
            raise ValueError("AI neinterpretovala všechny čtyři grafy.")
        raise ValueError("Featherless vrátil prázdnou interpretaci grafů.")
    except (OpenAIError, ValueError, TypeError, IndexError) as exc:
        LOGGER.warning(
            "Featherless chart interpretation failed (%s); using data summary.",
            type(exc).__name__,
        )
        reason = (
            "AI nevrátila úplnou nebo dostatečně opatrnou interpretaci grafů"
            if isinstance(exc, ValueError)
            else f"AI interpretace nebyla dostupná ({type(exc).__name__})"
        )
        return (
            f"{reason}; "
            "následuje automatické shrnutí naměřených trendů:\n"
            + fallback
        )


def _describe_candidate(candidate: dict[str, Any], index: int) -> str:
    number = candidate.get("number", index + 1)
    name = candidate.get("name") or "Bezejmenný rybník"
    area = int(candidate.get("area_m2") or 0)
    area_text = f"{area:,}".replace(",", " ")
    hectares = f"{area / 10_000:.2f}".replace(".", ",")
    location = candidate.get("approx_location") or {}
    location_text = ""
    if location.get("latitude") is not None and location.get("longitude") is not None:
        location_text = (
            f", přibližně {location['latitude']:.4f}° N, "
            f"{location['longitude']:.4f}° E"
        )
    return f"{number}. {name} — {area_text} m² ({hectares} ha){location_text}"


def _analyze_selected_pond(
    pond: dict[str, Any], date_from: str, date_to: str
) -> dict[str, Any]:
    analysis = analyze_pond(pond["pond_id"], date_from, date_to)
    algae = analyze_algae_bloom(pond["pond_id"], date_from, date_to)
    metrics = analysis.get("metrics", {})
    chart_interpretation = _interpret_analysis_charts(pond, analysis, algae)
    response = (
        f"Vyhodnocení rybníka {pond['name']} ({pond.get('area_m2', 'neznámá')} m²) "
        f"pro období {date_from} až {date_to}.\n"
        f"{analysis.get('warning', '')}\n"
        f"Průměrný NDWI: {metrics.get('average_ndwi', 'n/a')}\n"
        f"Průměrný NDTI: {metrics.get('average_ndti', 'n/a')}\n"
        f"Průměrný NDCI: {_ndci_summary(algae)}\n"
        f"{algae.get('interpretation', '')}\n"
        "Podíl vodních pixelů je odhad vodní plochy v polygonu, ne měření výšky hladiny "
        "ani objemu vody. Zalednění WIC zatím aplikace nedokáže ověřit.\n\n"
        "Interpretace grafů:\n"
        f"{chart_interpretation}"
    )
    return {
        "response": response,
        "analysis": {
            **analysis,
            "algae": algae,
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
        raise ValueError("Featherless není nakonfigurován.")

    client = OpenAI(base_url=config.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"), api_key=api_key)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "find_ponds",
                "description": "Vyhledá rybníky v obci včetně bezejmenných kandidátů a vrátí seznam možností.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "municipality": {"type": "string", "description": "Název obce v Česku"},
                        "pond_name": {"type": "string", "description": "Volitelný název rybníka, pokud je známý"},
                    },
                    "required": ["municipality"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_pond",
                "description": "Analyzuje satelitní data pro vybraný rybník v zadaném časovém období.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pond_id": {"type": "string", "description": "ID rybníka z geodat"},
                        "date_from": {"type": "string", "description": "Počáteční datum ve formátu YYYY-MM-DD"},
                        "date_to": {"type": "string", "description": "Konečné datum ve formátu YYYY-MM-DD"},
                    },
                    "required": ["pond_id", "date_from", "date_to"],
                },
            },
        },
    ]

    system_prompt = (
        "Jsi asistent pro PondWatch AI. Rozumíš českým dotazům o rybnících, jejich "
        "přezdívkám i skloňovaným názvům obcí. Před vyhledáním obce použij její základní "
        "tvar. Proveď pouze lokální nástroje find_ponds a analyze_pond. Odpovídej česky. "
        "Jsi také odborník na geoinformatiku a dálkový průzkum Země. NDWI je spektrální "
        "indikátor vody; podíl vody je klasifikace pixelů uvnitř polygonu, ne hladina "
        "ani objem. Sentinel-2 pixel 10 m může míchat vodu a břeh; výsledek ovlivňují "
        "oblačnost, stíny, vegetace, zákal, sezóna a počet platných pixelů. NDTI je "
        "pouze optický proxy suspendovaných látek, NDCI orientační screening "
        "chlorofylu/fytoplanktonu; žádný z indexů není laboratorní měření. Po analýze "
        "vždy na konci interpretuj každý zobrazený graf, trend i chybějící data, "
        "zohledni spolehlivost a nevyvozuj nepodložené příčiny. Pokud WIC data nejsou "
        "ve výsledku, netvrď, zda rybník zamrzl."
    )
    if normalized_municipality:
        system_prompt += (
            f" Předchozí normalizační krok určil základní tvar obce "
            f"„{normalized_municipality}“. Přesně tento název použij jako municipality "
            "v nástroji find_ponds."
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
            return {"response": message.content or "Nemám k dispozici finální odpověď.", "analysis": None}

        for tool_call in tool_calls:
            func_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            if func_name == "find_ponds" and normalized_municipality:
                arguments["municipality"] = normalized_municipality
            tool_result = _dispatch_tool(func_name, arguments)
            call_message = tool_call.model_dump()
            call_message["function"]["arguments"] = json.dumps(arguments, ensure_ascii=False)
            messages.append({"role": "assistant", "content": "", "tool_calls": [call_message]})
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(tool_result, ensure_ascii=False)})

        last_response = client.chat.completions.create(model=config.get("FEATHERLESS_MODEL", "Qwen/Qwen3-32B"), messages=messages)
        text = last_response.choices[0].message.content
        if text:
            return {"response": text, "analysis": None}

    return {"response": "Agent nedokázal dokončit analýzu v daném počtu cyklů.", "analysis": None}


def run_agent(prompt: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    if state is None:
        state = {}
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

    if has_real_featherless() and not is_pond_choice:
        try:
            ai_result = _call_featherless_tools(
                prompt, state, normalized_municipality
            )
            if ai_result.get("analysis") is not None or ai_result.get("status"):
                return ai_result
        except Exception:
            pass

    pond_name = _extract_pond_name(prompt) or state.get("last_pond_name")
    date_from, date_to = _extract_date_range(prompt)
    if date_from and date_to:
        state["last_date_from"] = date_from
        state["last_date_to"] = date_to
    elif state.get("pending_candidates"):
        date_from = state.get("last_date_from")
        date_to = state.get("last_date_to")

    if not municipality:
        return {"response": "Neslyšel jsem název obce. Uveďte prosím obec, např. „rybník v Řitce“.", "analysis": None, "status": "awaiting_input"}

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
                    return {"response": "Vybral jsem rybník: " + selected["name"] + ". Uveďte prosím časové období, např. „od 2025-01-01 do 2025-12-31“.", "analysis": None, "selected_pond": selected, "status": "awaiting_input"}
                state["pending_candidates"] = None
                state["pending_ponds"] = None
                return _analyze_selected_pond(selected, date_from, date_to)

    explicit_municipality = _extract_municipality(prompt)
    if (
        state.get("selected_pond")
        and date_from
        and date_to
        and explicit_municipality is None
        and not state.get("pending_candidates")
    ):
        return _analyze_selected_pond(state["selected_pond"], date_from, date_to)

    pond_search = find_ponds(municipality, pond_name)
    if pond_search.get("status") == "multiple":
        state["pending_candidates"] = pond_search["candidates"]
        state["pending_ponds"] = pond_search.get("result", [])
        choices = "; ".join(
            _describe_candidate(item, index)
            for index, item in enumerate(pond_search["candidates"])
        )
        return {
            "response": (
                f"Obec jsem převedl do základního tvaru „{pond_search.get('municipality', municipality)}“. "
                "Našel jsem více rybníků. Vyberte prosím jednoho v mapě a seznamu níže: "
                + choices
                + "."
            ),
            "analysis": None,
            "status": "awaiting_choice",
            "choices": pond_search["candidates"],
        }

    if pond_search.get("status") in ("not_found", "error"):
        return {"response": pond_search.get("message", "Rybník nebyl nalezen. Uveďte prosím upřesnění."), "analysis": None, "status": "not_found"}

    pond = pond_search["result"][0]
    state["selected_pond"] = pond
    if not date_from or not date_to:
        canonical_name = pond_search.get("municipality", municipality)
        return {
            "response": (
                f"Obec jsem převedl do základního tvaru „{canonical_name}“. "
                f"Nalezen rybník: {pond['name']}. Uveďte prosím časové období, "
                "například „od 2025-01-01 do 2025-12-31“."
            ),
            "analysis": None,
            "selected_pond": pond,
            "status": "awaiting_input",
        }

    return _analyze_selected_pond(pond, date_from, date_to)
