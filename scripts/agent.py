from __future__ import annotations

import json
import re
from typing import Any

from scripts.config import get_featherless_config, has_real_featherless
from scripts.geo_sources import find_ponds
from scripts.satellite import analyze_algae_bloom, analyze_pond

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


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
    return None, None


def _extract_municipality(prompt: str) -> str | None:
    patterns = [
        r"v\s+([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s-]+?)(?:\s+za\b|\s+od\b|\s+do\b|\s+pro\b|\.|\?|!|$)",
        r"obec\s+([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s-]+?)(?:\s+za\b|\s+od\b|\s+do\b|\.|\?|!|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            text = match.group(1).strip()
            if text and len(text) > 1:
                return text
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


def _call_featherless_tools(prompt: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
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

    messages: list[dict[str, Any]] = [{"role": "system", "content": "Jsi asistent pro PondWatch AI. Rozumíš českým dotazům o rybnících, satelitních datech a vodní kvalitě. Proveď pouze lokální nástroje find_ponds a analyze_pond. Odpovídej česky."}, {"role": "user", "content": prompt}]
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
            tool_result = _dispatch_tool(func_name, arguments)
            messages.append({"role": "assistant", "content": "", "tool_calls": [tool_call.model_dump()]})
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(tool_result, ensure_ascii=False)})

        last_response = client.chat.completions.create(model=config.get("FEATHERLESS_MODEL", "Qwen/Qwen3-32B"), messages=messages)
        text = last_response.choices[0].message.content
        if text:
            return {"response": text, "analysis": None}

    return {"response": "Agent nedokázal dokončit analýzu v daném počtu cyklů.", "analysis": None}


def run_agent(prompt: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = state or {}
    if has_real_featherless():
        try:
            return _call_featherless_tools(prompt, state)
        except Exception:
            pass

    municipality = _extract_municipality(prompt) or state.get("last_municipality")
    pond_name = _extract_pond_name(prompt) or state.get("last_pond_name")
    date_from, date_to = _extract_date_range(prompt)

    if not municipality:
        return {"response": "Neslyšel jsem název obce. Uveďte prosím obec, např. „rybník v Řitce“.", "analysis": None, "status": "awaiting_input"}

    state["last_municipality"] = municipality
    state["last_pond_name"] = pond_name

    if state.get("pending_candidates") and re.search(r"\b\d+\b", prompt):
        selection = re.search(r"\b(\d+)\b", prompt)
        if selection:
            choice = int(selection.group(1))
            candidates = state["pending_candidates"]
            selected = next((item for item in candidates if int(item["number"]) == choice), None)
            if selected:
                pond_id = selected["pond_id"]
                state["selected_pond"] = selected
                if not date_from or not date_to:
                    return {"response": "Vybral jsem rybník: " + selected["name"] + ". Uveďte prosím časové období, např. „od 2025-01-01 do 2025-12-31“.", "analysis": None, "selected_pond": selected, "status": "awaiting_input"}
                analysis = analyze_pond(pond_id, date_from, date_to)
                algae = analyze_algae_bloom(pond_id, date_from, date_to)
                response = (
                    f"Analýza pro {selected['name']} za období {date_from} až {date_to}:\n\n"
                    f"{analysis.get('warning', '')}\n\n"
                    f"Průměrný NDWI: {analysis.get('metrics', {}).get('average_ndwi')}\n"
                    f"Průměrný NDTI: {analysis.get('metrics', {}).get('average_ndti')}\n"
                    f"Průměrný NDCI: {_ndci_summary(algae)}\n\n"
                    f"{algae.get('interpretation', '')}"
                )
                state["pending_candidates"] = None
                return {"response": response, "analysis": {**analysis, "algae": algae}, "selected_pond": selected, "status": "completed"}

    pond_search = find_ponds(municipality, pond_name)
    if pond_search.get("status") == "multiple":
        state["pending_candidates"] = pond_search["candidates"]
        choices = ", ".join(f"{item['number']}: {item['name']} ({item['area_m2']} m²)" for item in pond_search["candidates"])
        return {"response": "Našel jsem více rybníků v obci. Vyberte prosím jeden z kandidátů: " + choices + ".", "analysis": None, "status": "awaiting_choice", "choices": pond_search["candidates"]}

    if pond_search.get("status") == "not_found":
        return {"response": pond_search.get("message", "Rybník nebyl nalezen. Uveďte prosím upřesnění."), "analysis": None, "status": "not_found"}

    pond = pond_search["result"][0]
    state["selected_pond"] = pond
    if not date_from or not date_to:
        return {"response": f"Nalezen rybník: {pond['name']}. Uveďte prosím časové období, například „od 2025-01-01 do 2025-12-31“.", "analysis": None, "selected_pond": pond, "status": "awaiting_input"}

    analysis = analyze_pond(pond["pond_id"], date_from, date_to)
    algae = analyze_algae_bloom(pond["pond_id"], date_from, date_to)
    data_text = analysis.get("warning", "")
    metrics = analysis.get("metrics", {})
    response = (
        f"Vyhodnocení rybníka {pond['name']} ({pond['area_m2']} m²) pro období {date_from} až {date_to}.\n"
        f"{data_text}\n"
        f"Průměrný NDWI: {metrics.get('average_ndwi', 'n/a')}\n"
        f"Průměrný NDTI: {metrics.get('average_ndti', 'n/a')}\n"
        f"Průměrný NDCI: {_ndci_summary(algae)}\n"
        f"{algae.get('interpretation', '')}\n"
        f"Kvalita dat: {analysis.get('quality_summary', {}).get('data_quality', 'neznámá')}"
    )
    return {"response": response, "analysis": {**analysis, "algae": algae}, "selected_pond": pond, "status": "completed"}
