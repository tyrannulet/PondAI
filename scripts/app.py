from __future__ import annotations

from contextlib import contextmanager
from html import escape
from typing import Any, Iterator

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from scripts import demo_data
from scripts.agent import _fallback_chart_interpretation, _requests_charts, run_agent
from scripts.config import APP_SUBTITLE, APP_TITLE, get_api_status, has_real_copernicus, has_real_featherless


THINKING_ICONS = (
    "🎣", "🐟", "🚣", "🏊", "🛶", "🏄", "⛵", "🏖️", "💧",
)


@contextmanager
def _pond_thinking(message: str) -> Iterator[None]:
    """Cycle pond motifs in the browser while the agent runs synchronously."""
    placeholder = st.empty()
    duration = len(THINKING_ICONS) * 1.2
    visible_percent = 100 / len(THINKING_ICONS)
    icons = "".join(
        f'<span style="animation-delay: {index * 1.2:.1f}s">{icon}</span>'
        for index, icon in enumerate(THINKING_ICONS)
    )
    placeholder.markdown(
        f"""
        <style>
        .pond-thinking {{
            display: flex; align-items: center; gap: .75rem;
            padding: .75rem 0;
        }}
        .pond-thinking-icons {{
            display: inline-grid; flex: 0 0 2.75rem;
            width: 2.75rem; height: 2.75rem;
            place-items: center; font-size: 2rem; line-height: 1;
        }}
        .pond-thinking-icons span {{
            grid-area: 1 / 1; opacity: 0;
            animation: pond-icon-cycle {duration:.1f}s linear infinite;
        }}
        @keyframes pond-icon-cycle {{
            0%, {visible_percent - .01:.2f}% {{ opacity: 1; }}
            {visible_percent:.2f}%, 100% {{ opacity: 0; }}
        }}
        @media (prefers-reduced-motion: reduce) {{
            .pond-thinking-icons span {{ animation: none; }}
            .pond-thinking-icons span:first-child {{ opacity: 1; }}
        }}
        </style>
        <div class="pond-thinking" role="status">
            <span class="pond-thinking-icons" aria-hidden="true">{icons}</span>
            <span>{escape(message)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    try:
        yield
    finally:
        placeholder.empty()


def _default_analysis() -> dict[str, Any]:
    return demo_data.generate_demo_analysis("ritka-pond-1", "2025-01-01", "2025-12-31")


def _ensure_session() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("show_charts", False)
    st.session_state.setdefault("analysis", None if has_real_copernicus() else _default_analysis())
    st.session_state.setdefault(
        "selected_pond",
        None
        if has_real_copernicus()
        else {"pond_id": "ritka-pond-1", "name": "Demo pond in Řitka", "water_body_type": "pond", "municipality": "Řitka", "area_m2": 142500},
    )
    st.session_state.setdefault("pending_candidates", None)
    if has_real_copernicus() and (st.session_state.get("analysis") or {}).get("demo_mode"):
        st.session_state["analysis"] = None
        st.session_state["selected_pond"] = None


def _render_map(geometry: dict[str, Any] | None, pond_name: str) -> None:
    if not geometry:
        st.info("No polygon is available to display on the map.")
        return
    coords = geometry.get("coordinates", [])
    if not coords:
        st.info("The polygon is not available yet.")
        return
    shape = coords[0] if isinstance(coords[0], list) and coords[0] and isinstance(coords[0][0], list) else coords
    if not shape:
        st.info("The polygon is empty.")
        return

    import folium

    m = folium.Map(location=[shape[0][1], shape[0][0]], zoom_start=14, tiles="OpenStreetMap")
    folium.Polygon(locations=[[point[1], point[0]] for point in shape], color="green", fill=True, fill_opacity=0.4, tooltip=pond_name).add_to(m)
    st_folium(m, width=700, height=420)
    st.caption(f"Map: {pond_name}")


def _pond_option_label(pond: dict[str, Any], index: int) -> str:
    name = pond.get("name") or "Unnamed water body"
    area = int(pond.get("area_m2") or 0)
    area_text = f"{area:,}".replace(",", " ")
    hectares = f"{area / 10_000:.2f}"
    location = pond.get("approx_location") or {}
    location_text = ""
    if location.get("latitude") is not None and location.get("longitude") is not None:
        location_text = f" · approx. {location['latitude']:.4f}° N, {location['longitude']:.4f}° E"
    water_type = pond.get("water_body_type", "water body")
    return f"{index + 1}. {name} · {water_type} · {area_text} m² ({hectares} ha){location_text}"


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
        st.info("No candidate polygons are available to display on the map.")
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
            tooltip=f"Candidate {index + 1}",
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

    st.subheader("Choose a water body")
    st.caption("Polygons and markers on the map match the candidates in the list. Hover or click to see details.")
    _render_candidate_map(ponds)
    selected_index = st.selectbox(
        "Water body by area and approximate location",
        options=range(len(ponds)),
        format_func=lambda index: _pond_option_label(ponds[index], index),
        key="pond_candidate_selection",
    )
    if st.button("Select water body and continue", key="select_pond_candidate"):
        pond = ponds[selected_index]
        candidate = next(
            (item for item in options if item.get("pond_id") == pond.get("pond_id")),
            options[selected_index],
        )
        with _pond_thinking("Preparing the selected water-body analysis…"):
            result = run_agent(str(candidate["number"]), st.session_state)
        st.session_state["analysis"] = result.get("analysis")
        st.session_state["selected_pond"] = result.get("selected_pond") or pond
        st.session_state["messages"].append(
            {"role": "user", "content": f"Selected: {_pond_option_label(pond, selected_index)}"}
        )
        st.session_state["messages"].append(
            {"role": "assistant", "content": result["response"]}
        )
        st.rerun()


def _render_line_chart(df: pd.DataFrame, metric: str, title: str, color: str) -> None:
    fig = px.line(df, x="date", y=metric, markers=True, title=title, color_discrete_sequence=[color])
    fig.update_layout(xaxis_title="Date", yaxis_title=metric)
    st.plotly_chart(fig, use_container_width=True)


def _render_algae_panel(analysis: dict[str, Any]) -> None:
    algae = analysis.get("algae", {})
    st.subheader("Satellite algae screening")
    if algae:
        chart_df = pd.DataFrame(algae.get("ndci_trend", []))
        if not chart_df.empty:
            _render_line_chart(chart_df, "ndci", "NDCI trend", "#2E8B57")
        st.info(algae.get("interpretation", ""))
        st.write(f"Screening result: {algae.get('category', 'unknown')}")
        st.write(f"Data quality: {algae.get('quality', {}).get('data_quality', 'unknown')}")
    else:
        st.info("No satellite algae-screening data are available.")


st.set_page_config(page_title=APP_TITLE, page_icon="🌊", layout="wide")


def main() -> None:
    _ensure_session()

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    api_status = get_api_status()
    if not has_real_copernicus():
        st.warning("DEMO MODE — these are simulated values, not a real satellite analysis.")
    elif not has_real_featherless():
        st.info("Satellite data are available, but Featherless AI is not configured. You can continue with an English or Czech request.")
    else:
        st.success("API connections are active. Satellite observations will be loaded for your selected dates.")

    with st.sidebar:
        st.header("API status")
        st.write("Featherless:", api_status["featherless"]["ready"])
        st.write("Copernicus:", api_status["copernicus"]["ready"])
        if not has_real_copernicus():
            st.info("Add API credentials to api/featherless.txt and api/copernicus.txt, then restart the app.")

    if "messages" in st.session_state and st.session_state["messages"]:
        for message in st.session_state["messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    if prompt := st.chat_input("Ask in English or Czech, e.g. 'Analyze ponds in Řitka for 2025.'"):
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        if _requests_charts(prompt):
            st.session_state["show_charts"] = True
        with _pond_thinking("Understanding your request and preparing the analysis…"):
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
        st.info("Enter a request in the chat above. Results appear after selecting a water body and completing the satellite analysis.")
        return

    st.subheader(f"Selected water body: {selected_pond.get('name', 'Unknown water body')}")
    col_map, col_meta = st.columns([2, 1])
    with col_map:
        _render_map(
            analysis.get("geometry")
            or selected_pond.get("geometry")
            or demo_data.DEMO_PONDS.get(selected_pond.get("pond_id"), {}).get("geometry"),
            selected_pond.get("name", "Water body"),
        )
    with col_meta:
        st.write(f"ID: {selected_pond.get('pond_id', 'unknown')}")
        st.write(f"Type: {selected_pond.get('water_body_type', 'water body')}")
        st.write(f"Municipality: {selected_pond.get('municipality', 'unknown')}")
        st.write(f"Area: {selected_pond.get('area_m2', 'unknown')} m²")
        st.write(f"Data quality: {analysis.get('quality_summary', {}).get('data_quality', 'unknown')}")
        st.write(f"Reliability: {analysis.get('quality_summary', {}).get('reliability', 'unknown')}")

    st.subheader("Plain-language report")
    st.markdown(analysis.get("report", "The report is not available for this analysis."))

    series = analysis.get("timeseries") or []
    if series:
        if st.checkbox("Show optional charts and measurements", key="show_charts"):
            df = pd.DataFrame(series)
            st.subheader("Water surface")
            _render_line_chart(df, "water_percent", "Classified water-pixel share (%)", "#1f77b4")
            st.subheader("Optical water indicators")
            _render_line_chart(df, "ndwi", "NDWI trend", "#17becf")
            _render_line_chart(df, "ndti", "NDTI trend", "#ff7f0e")
            st.subheader("Possible ice cover")
            if "ice_percent" in df:
                _render_line_chart(df, "ice_percent", "Pixels classified as snow/ice (%)", "#86c5da")
            _render_algae_panel(analysis)
            st.subheader("Chart interpretation")
            st.markdown(
                analysis.get("graph_interpretation")
                or _fallback_chart_interpretation(analysis, analysis.get("algae", {}))
            )
            st.subheader("Measurements")
            columns = [
                column
                for column in ("date", "ndwi", "ndti", "water_percent", "ice_percent", "valid_pixels")
                if column in df
            ]
            st.dataframe(df[columns], use_container_width=True)
    else:
        st.info("No observations are available. Submit a new request to run another analysis.")

    st.subheader("Measurement quality and limitations")
    quality = analysis.get("quality_summary", {})
    st.write(f"- Valid pixels: {quality.get('valid_pixels', 'not reported')}")
    st.write(f"- Data availability: {quality.get('data_quality', 'unknown')}")
    st.write(f"- Limitations: {quality.get('limitations', 'No specific limitations reported.')}")
    st.write(f"- AI/data note: {analysis.get('warning', 'No additional notes.')}")


main()
