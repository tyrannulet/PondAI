from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from folium import Polygon
from streamlit_folium import st_folium

from scripts import demo_data
from scripts.agent import run_agent
from scripts.config import APP_SUBTITLE, APP_TITLE, get_api_status, has_real_copernicus, has_real_featherless


def _default_analysis() -> dict[str, Any]:
    return demo_data.generate_demo_analysis("ritka-pond-1", "2025-01-01", "2025-12-31")


def _ensure_session() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("analysis", None if has_real_copernicus() else _default_analysis())
    st.session_state.setdefault(
        "selected_pond",
        None
        if has_real_copernicus()
        else {"pond_id": "ritka-pond-1", "name": "Rybník v Řitce", "municipality": "Řítek", "area_m2": 142500},
    )
    st.session_state.setdefault("pending_candidates", None)
    if has_real_copernicus() and (st.session_state.get("analysis") or {}).get("demo_mode"):
        st.session_state["analysis"] = None
        st.session_state["selected_pond"] = None


def _render_map(geometry: dict[str, Any] | None, pond_name: str) -> None:
    if not geometry:
        st.info("Pro tento rybník není k dispozici polygon pro zobrazení na mapě.")
        return
    coords = geometry.get("coordinates", [])
    if not coords:
        st.info("Polygon zatím není k dispozici.")
        return
    shape = coords[0] if isinstance(coords[0], list) and coords[0] and isinstance(coords[0][0], list) else coords
    if not shape:
        st.info("Polygon je prázdný.")
        return

    import folium

    m = folium.Map(location=[shape[0][1], shape[0][0]], zoom_start=14, tiles="OpenStreetMap")
    folium.Polygon(locations=[[point[1], point[0]] for point in shape], color="green", fill=True, fill_opacity=0.4, tooltip=pond_name).add_to(m)
    st_folium(m, width=700, height=420)
    st.caption(f"Mapa: {pond_name}")


def _render_line_chart(df: pd.DataFrame, metric: str, title: str, color: str) -> None:
    fig = px.line(df, x="date", y=metric, markers=True, title=title, color_discrete_sequence=[color])
    fig.update_layout(xaxis_title="Datum", yaxis_title=metric)
    st.plotly_chart(fig, use_container_width=True)


def _render_algae_panel(analysis: dict[str, Any]) -> None:
    algae = analysis.get("algae", {})
    st.subheader("Biologická kvalita vody")
    if algae:
        chart_df = pd.DataFrame(algae.get("ndci_trend", []))
        if not chart_df.empty:
            _render_line_chart(chart_df, "ndci", "Vývoj NDCI", "#2E8B57")
        st.info(algae.get("interpretation", ""))
        st.write(f"Kategorie: {algae.get('category', 'neznámá')}")
        st.write(f"Kvalita měření: {algae.get('quality', {}).get('data_quality', 'neznámá')}")
    else:
        st.info("Nebyly k dispozici experimentální údaje o biologické kvalitě vody.")


st.set_page_config(page_title=APP_TITLE, page_icon="🌊", layout="wide")


def main() -> None:
    _ensure_session()

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    api_status = get_api_status()
    if not has_real_copernicus():
        st.warning("DEMO REŽIM – zobrazená data jsou simulovaná, nejde o skutečnou satelitní analýzu.")
    elif not has_real_featherless():
        st.info("Satelitní data lze načíst, ale Featherless AI není nastaven. Pokračovat můžete běžným českým promptem.")
    else:
        st.success("Aplikace má aktivní připojení k API. Přesné satelitní údaje budou načteny podle konfigurace.")

    with st.sidebar:
        st.header("Stav API")
        st.write("Featherless:", api_status["featherless"]["ready"])
        st.write("Copernicus:", api_status["copernicus"]["ready"])
        if not has_real_copernicus():
            st.info("Přidejte API klíče do souborů api/featherless.txt a api/copernicus.txt a restartujte aplikaci.")

    if "messages" in st.session_state and st.session_state["messages"]:
        for message in st.session_state["messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    if prompt := st.chat_input("Zadejte požadavek, například: Analyzuj rybník v Řitce za celý rok 2025."):
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("Přemýšlím a připravuji analýzu…"):
            result = run_agent(prompt, st.session_state)
        st.session_state["analysis"] = result.get("analysis") or st.session_state["analysis"]
        st.session_state["selected_pond"] = result.get("selected_pond") or st.session_state["selected_pond"]
        st.session_state["messages"].append({"role": "assistant", "content": result["response"]})
        with st.chat_message("assistant"):
            st.markdown(result["response"])

    analysis = st.session_state.get("analysis")
    selected_pond = st.session_state.get("selected_pond")
    if not analysis or not selected_pond:
        st.info("Zadejte požadavek do chatu výše. Skutečné výsledky se zobrazí po výběru rybníka a dokončení satelitní analýzy.")
        return

    st.subheader(f"Vybraný rybník: {selected_pond.get('name', 'Neznámý rybník')}")
    col_map, col_meta = st.columns([2, 1])
    with col_map:
        _render_map(
            analysis.get("geometry")
            or selected_pond.get("geometry")
            or demo_data.DEMO_PONDS.get(selected_pond.get("pond_id"), {}).get("geometry"),
            selected_pond.get("name", "Rybník"),
        )
    with col_meta:
        st.write(f"ID: {selected_pond.get('pond_id', 'neznámé')}")
        st.write(f"Obec: {selected_pond.get('municipality', 'neznámá')}")
        st.write(f"Plocha: {selected_pond.get('area_m2', 'neznámá')} m²")
        st.write(f"Kvalita dat: {analysis.get('quality_summary', {}).get('data_quality', 'neznámá')}")
        st.write(f"Spolehlivost: {analysis.get('quality_summary', {}).get('reliability', 'neznámá')}")

    series = analysis.get("timeseries") or []
    if series:
        df = pd.DataFrame(series)
        st.subheader("Vodní plocha")
        _render_line_chart(df, "water_percent", "Podíl vodní plochy (%)", "#1f77b4")
        st.subheader("Optické indikátory vody")
        _render_line_chart(df, "ndwi", "Vývoj NDWI", "#17becf")
        _render_line_chart(df, "ndti", "Vývoj NDTI", "#ff7f0e")
        st.subheader("Zalednění")
        st.info("Analýza zalednění WIC zatím není implementována; aplikace nemůže ověřit, zda byl rybník zamrzlý.")
        _render_algae_panel(analysis)
        st.subheader("Tabulka naměřených hodnot")
        st.dataframe(df[["date", "ndwi", "ndti", "water_percent", "valid_pixels"]], use_container_width=True)
    else:
        st.info("Žádná data k zobrazení. Zadejte nový požadavek pro spuštění analýzy.")

    st.subheader("Kvalita a spolehlivost měření")
    quality = analysis.get("quality_summary", {})
    st.write(f"- Počet platných pixelů: {quality.get('valid_pixels', 'neuvedeno')}")
    st.write(f"- Dostupnost dat: {quality.get('data_quality', 'neznámá')}")
    st.write(f"- Omezení: {quality.get('limitations', 'Nejsou uplatněna žádná zvláštní omezení.')}")
    st.write(f"- AI interpretace: {analysis.get('warning', 'Bez poznámek.')}")


main()
