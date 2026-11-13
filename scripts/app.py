from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from scripts import demo_data
from scripts.agent import _fallback_chart_interpretation, run_agent
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


def _pond_option_label(pond: dict[str, Any], index: int) -> str:
    name = pond.get("name") or "Bezejmenný rybník"
    area = int(pond.get("area_m2") or 0)
    area_text = f"{area:,}".replace(",", " ")
    hectares = f"{area / 10_000:.2f}".replace(".", ",")
    location = pond.get("approx_location") or {}
    location_text = ""
    if location.get("latitude") is not None and location.get("longitude") is not None:
        location_text = f" · přibližně {location['latitude']:.4f}° N, {location['longitude']:.4f}° E"
    return f"{index + 1}. {name} · {area_text} m² ({hectares} ha){location_text}"


def _render_candidate_map(ponds: list[dict[str, Any]]) -> None:
    import folium

    candidates: list[tuple[int, dict[str, Any], list[list[float]], tuple[float, float]]] = []
    for index, pond in enumerate(ponds):
        geometry = pond.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        if not coordinates or not coordinates[0]:
            continue
        ring = coordinates[0]
        points = [point for point in ring if isinstance(point, (list, tuple)) and len(point) >= 2]
        if not points:
            continue
        location = pond.get("approx_location") or {}
        longitude = location.get("longitude", sum(float(point[0]) for point in points) / len(points))
        latitude = location.get("latitude", sum(float(point[1]) for point in points) / len(points))
        candidates.append((index, pond, points, (float(latitude), float(longitude))))

    if not candidates:
        st.info("Pro kandidáty nejsou dostupné polygony k zobrazení na mapě.")
        return

    center = (
        sum(item[3][0] for item in candidates) / len(candidates),
        sum(item[3][1] for item in candidates) / len(candidates),
    )
    map_obj = folium.Map(location=center, zoom_start=14, tiles="OpenStreetMap")
    colors = ["blue", "red", "green", "purple", "orange", "darkred", "cadetblue"]
    all_points: list[tuple[float, float]] = []
    for index, pond, ring, location in candidates:
        color = colors[index % len(colors)]
        label = _pond_option_label(pond, index)
        folium.Polygon(
            locations=[[float(point[1]), float(point[0])] for point in ring],
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.35,
            tooltip=label,
        ).add_to(map_obj)
        folium.Marker(
            location=location,
            tooltip=f"Kandidát {index + 1}",
            popup=label,
            icon=folium.Icon(color=color, icon="info-sign"),
        ).add_to(map_obj)
        all_points.extend((float(point[1]), float(point[0])) for point in ring)

    if all_points:
        latitudes = [point[0] for point in all_points]
        longitudes = [point[1] for point in all_points]
        map_obj.fit_bounds([[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]])
    st_folium(map_obj, width=700, height=420)


def _render_pond_picker() -> None:
    ponds = st.session_state.get("pending_ponds") or []
    options = st.session_state.get("pending_candidates") or []
    if not ponds or not options:
        return

    st.subheader("Vyberte rybník")
    st.caption("Polygony a značky na mapě odpovídají kandidátům v seznamu. Najetím nebo kliknutím zobrazíte jejich popisek.")
    _render_candidate_map(ponds)
    selected_index = st.selectbox(
        "Rybník podle plochy a přibližné polohy",
        options=range(len(ponds)),
        format_func=lambda index: _pond_option_label(ponds[index], index),
        key="pond_candidate_selection",
    )
    if st.button("Vybrat rybník a pokračovat", key="select_pond_candidate"):
        pond = ponds[selected_index]
        candidate = next(
            (item for item in options if item.get("pond_id") == pond.get("pond_id")),
            options[selected_index],
        )
        with st.spinner("Připravuji analýzu vybraného rybníka…"):
            result = run_agent(str(candidate["number"]), st.session_state)
        st.session_state["analysis"] = result.get("analysis")
        st.session_state["selected_pond"] = result.get("selected_pond") or pond
        st.session_state["messages"].append(
            {"role": "user", "content": f"Vybral/a jsem: {_pond_option_label(pond, selected_index)}"}
        )
        st.session_state["messages"].append(
            {"role": "assistant", "content": result["response"]}
        )
        st.rerun()


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
        if result.get("status") == "awaiting_choice":
            st.session_state["analysis"] = None
            st.session_state["selected_pond"] = None
        elif result.get("analysis") is not None:
            st.session_state["analysis"] = result["analysis"]
        if result.get("selected_pond") is not None:
            st.session_state["selected_pond"] = result["selected_pond"]
        st.session_state["messages"].append({"role": "assistant", "content": result["response"]})
        with st.chat_message("assistant"):
            st.markdown(result["response"])

    _render_pond_picker()

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
        st.subheader("Interpretace grafů")
        st.markdown(
            analysis.get(
                "graph_interpretation",
                _fallback_chart_interpretation(
                    analysis, analysis.get("algae", {})
                ),
            )
        )
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
