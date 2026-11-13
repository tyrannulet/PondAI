from __future__ import annotations

import math
from contextlib import contextmanager
from html import escape
from typing import Any, Iterator

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from scripts import demo_data
from scripts.agent import _fallback_chart_interpretation, run_agent
from scripts.config import APP_SUBTITLE, APP_TITLE, get_api_status, has_real_copernicus, has_real_featherless
from scripts.geo_sources import _approximate_location

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
PALETTE = {
    "water":  {"line": "#3B82F6", "fill": "rgba(59,130,246,0.13)",  "accent": "#2563EB"},
    "ndwi":   {"line": "#06B6D4", "fill": "rgba(6,182,212,0.13)",   "accent": "#0891B2"},
    "ndti":   {"line": "#F59E0B", "fill": "rgba(245,158,11,0.13)",  "accent": "#D97706"},
    "ndci":   {"line": "#10B981", "fill": "rgba(16,185,129,0.13)",  "accent": "#059669"},
    "ice":    {"line": "#8B5CF6", "fill": "rgba(139,92,246,0.13)",  "accent": "#7C3AED"},
}

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
    st.session_state.setdefault("show_map", True)
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


def _create_map(location: tuple[float, float]) -> Any:
    """Share the same dark basemap and readable controls in both map views."""
    import folium

    map_obj = folium.Map(
        location=location, zoom_start=14, tiles=None,
        control_scale=True, scrollWheelZoom=False,
    )
    # Style only the base tiles, preserving the colors of polygons and controls.
    folium.TileLayer("OpenStreetMap", class_name="pond-basemap").add_to(map_obj)
    map_obj.get_root().header.add_child(folium.Element("""
        <style>
        .leaflet-container { background: #101b2b; font-family: system-ui, sans-serif; }
        .pond-basemap { filter: invert(1) hue-rotate(180deg) saturate(.65) brightness(.85) contrast(.9); }
        .leaflet-bar { border: 1px solid #475569 !important; border-radius: 8px; overflow: hidden; }
        .leaflet-bar a, .leaflet-bar a:hover { background: #182638; color: #f1f5f9; border-color: #475569; }
        .leaflet-control-attribution { background: #101b2bea !important; color: #cbd5e1; }
        .leaflet-control-attribution a { color: #7dd3fc; }
        .leaflet-control-scale-line { background: #101b2bea; color: #e2e8f0; border-color: #94a3b8; }
        .leaflet-tooltip, .leaflet-popup-content-wrapper, .leaflet-popup-tip {
            background: #182638; color: #f1f5f9; border-color: #475569;
        }
        .leaflet-tooltip { border-radius: 8px; padding: 8px 12px; }
        .pond-marker {
            display: grid; place-items: center; width: 28px; height: 28px;
            border: 2px solid #e2e8f0; border-radius: 50%; color: #0b1120;
            font-size: 13px; font-weight: 800; box-shadow: 0 2px 12px #0008;
        }
        </style>
    """))
    return map_obj


def _display_map(map_obj: Any, key: str) -> None:
    st_folium(
        map_obj, height=360, use_container_width=True,
        returned_objects=[], key=key,
    )


def _render_map(geometry: dict[str, Any] | None, pond_name: str) -> None:
    if not geometry:
        st.info("No polygon is available to display on the map.")
        return
    location = _approximate_location(geometry)
    if not location:
        st.info("The polygon is not available yet.")
        return

    import folium

    m = _create_map((location["latitude"], location["longitude"]))
    layer = folium.GeoJson(
        geometry, tooltip=escape(pond_name),
        style_function=lambda _: {
            "color": "#67e8f9", "weight": 3,
            "fillColor": "#22d3ee", "fillOpacity": 0.28,
        },
        highlight_function=lambda _: {"weight": 4, "fillOpacity": 0.4},
    ).add_to(m)
    m.fit_bounds(layer.get_bounds(), padding=(35, 35), max_zoom=16)
    _display_map(m, "selected_pond_map")
    st.caption(f"Cyan outline · {pond_name} · Scroll the page; use + / − to zoom the map.")


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

    candidates: list[tuple[int, dict[str, Any], dict[str, Any], tuple[float, float]]] = []
    for index, pond in enumerate(ponds):
        geometry = pond.get("geometry") or {}
        location = _approximate_location(geometry)
        if not location:
            continue
        candidates.append((index, pond, geometry, (location["latitude"], location["longitude"])))

    if not candidates:
        st.info("No candidate polygons are available to display on the map.")
        return

    center = (
        sum(item[3][0] for item in candidates) / len(candidates),
        sum(item[3][1] for item in candidates) / len(candidates),
    )
    map_obj = _create_map(center)
    colors = ["#67e8f9", "#fda4af", "#6ee7b7", "#c4b5fd", "#fcd34d", "#fb923c", "#93c5fd"]
    all_points: list[tuple[float, float]] = []
    for index, pond, geometry, location in candidates:
        color = colors[index % len(colors)]
        label = _pond_option_label(pond, index)
        layer = folium.GeoJson(
            geometry,
            style_function=lambda _, color=color: {
                "color": color, "weight": 3, "fillColor": color, "fillOpacity": 0.25,
            },
            tooltip=escape(label),
        ).add_to(map_obj)
        folium.Marker(
            location=location,
            tooltip=f"Candidate {index + 1}",
            popup=escape(label),
            icon=folium.DivIcon(
                html=f'<span class="pond-marker" style="background:{color}">{index + 1}</span>',
                icon_size=(28, 28), icon_anchor=(14, 14),
            ),
        ).add_to(map_obj)
        all_points.extend(tuple(point) for point in layer.get_bounds())

    if all_points:
        latitudes = [point[0] for point in all_points]
        longitudes = [point[1] for point in all_points]
        map_obj.fit_bounds(
            [[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]],
            padding=(35, 35), max_zoom=16,
        )
    _display_map(map_obj, "candidate_pond_map")


def _render_pond_picker() -> None:
    ponds = st.session_state.get("pending_ponds") or []
    options = st.session_state.get("pending_candidates") or []
    if not ponds or not options:
        return

    st.subheader("Choose a water body")
    st.caption("Polygons and markers on the map match the candidates in the list. Hover or click to see details.")
    if st.checkbox("Show candidate map", value=True, key="show_candidate_map"):
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


# ---------------------------------------------------------------------------
# CSS injection for card-based analytics widget
# ---------------------------------------------------------------------------
_WIDGET_CSS = """
<style>
.stApp { background: #0b1120; color: #e2e8f0; }
[data-testid="stMainBlockContainer"] { max-width: 1600px; padding-top: 2rem; }
.st-key-visual_workspace, .st-key-report, .st-key-pond_details {
    background: #111c2e;
    border: 1px solid #2b3b52;
    border-radius: 20px;
    padding: 1.25rem;
    box-shadow: 0 12px 32px #02061726;
}
.st-key-visual_workspace { border-top: 2px solid #38bdf8; }
.st-key-visual_workspace [data-testid="stCaptionContainer"],
.st-key-pond_details [data-testid="stCaptionContainer"] { color: #a8b8cd; }
.st-key-visual_workspace [data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid #2b3b52;
}
.st-key-visual_workspace iframe { border: 1px solid #33465e; border-radius: 12px; }
.st-key-visual_workspace [data-testid="stExpander"] {
    border: 1px solid #33465e; border-radius: 12px; background: #142034;
}
/* Each native container encloses the title, sparkline AND statistics. */
[class*="st-key-metric_"] {
    background: #182638;
    border: 1px solid #33465e;
    border-radius: 14px;
    padding: .85rem;
    box-shadow: 0 4px 12px #02061726;
}
.card-header { display: flex; align-items: center; gap: .45rem; }
.card-icon { font-size: 1rem; line-height: 1; }
.card-title { font-size: .85rem; font-weight: 600; color: #e2e8f0; }
.stat-row { display: flex; justify-content: space-between; gap: .5rem; padding: .12rem 0; }
.stat-label { font-size: .72rem; color: #a8b8cd; }
.stat-value { font-size: .8rem; font-weight: 600; color: #f1f5f9; text-align: right; }
.trend-up { color: #6ee7b7; }
.trend-down { color: #fda4af; }
.trend-flat { color: #cbd5e1; }
/* The document scrolls separately from the visual dock on wide screens. */
@media (min-width: 1100px) {
    [data-testid="stColumn"]:has(.st-key-visual_workspace) {
        position: sticky;
        top: 4.5rem;
        align-self: flex-start;
    }
    .st-key-visual_workspace {
        max-height: calc(100dvh - 10rem);
        overflow-y: auto;
        scrollbar-width: thin;
        scrollbar-color: #475569 #111c2e;
        scrollbar-gutter: stable;
    }
}
@media (max-width: 1099px) {
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-visual_workspace) {
        flex-direction: column;
    }
    [data-testid="stColumn"]:has(.st-key-reading_workspace),
    [data-testid="stColumn"]:has(.st-key-visual_workspace) {
        width: 100%; flex: 1 1 100%;
    }
}
@media (max-width: 600px) {
    .st-key-visual_workspace, .st-key-report, .st-key-pond_details { padding: .85rem; }
}
</style>
"""


# ---------------------------------------------------------------------------
# Sparkline & detail-chart helpers
# ---------------------------------------------------------------------------

def _safe_values(series: list[dict[str, Any]], metric: str) -> tuple[list[str], list[float]]:
    """Extract (dates, values) pairs, skipping None entries."""
    dates: list[str] = []
    vals: list[float] = []
    for item in series:
        v = item.get(metric)
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            continue
        dates.append(str(item.get("date", "")))
        vals.append(float(v))
    return dates, vals


def _trend_arrow(values: list[float]) -> tuple[str, str]:
    """Return (arrow, css_class) for the first→last change."""
    if len(values) < 2:
        return "—", "trend-flat"
    delta = values[-1] - values[0]
    if abs(delta) < 1e-9:
        return "→", "trend-flat"
    if delta > 0:
        return "↗", "trend-up"
    return "↘", "trend-down"


def _sparkline_figure(
    dates: list[str],
    values: list[float],
    color_key: str,
) -> go.Figure:
    """Build a minimal sparkline (no axes, no toolbar)."""
    pal = PALETTE.get(color_key, PALETTE["water"])
    fig = go.Figure(
        go.Scatter(
            x=dates,
            y=values,
            mode="lines",
            line=dict(color=pal["line"], width=2.5, shape="spline", smoothing=1.3),
            fill="tozeroy",
            fillcolor=pal["fill"],
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=80,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False, showgrid=False, zeroline=False),
        yaxis=dict(visible=False, showgrid=False, zeroline=False),
        showlegend=False,
        dragmode=False,
    )
    return fig


def _detail_chart(
    dates: list[str],
    values: list[float],
    color_key: str,
    y_label: str,
    reference_line: float | None = None,
    bands: list[tuple[float, float, str, str]] | None = None,
) -> go.Figure:
    """Full interactive chart for the expanded view."""
    pal = PALETTE.get(color_key, PALETTE["water"])
    fig = go.Figure()

    # Interpretation / reference bands
    if bands:
        for y0, y1, band_color, label in bands:
            fig.add_hrect(
                y0=y0, y1=y1,
                fillcolor=band_color,
                layer="below",
                line_width=0,
                annotation_text=label,
                annotation_position="top left",
                annotation_font_size=10,
                annotation_font_color="#94a3b8",
            )

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=values,
            mode="lines+markers",
            line=dict(color=pal["line"], width=2.5, shape="spline", smoothing=1.3),
            marker=dict(size=7, color=pal["line"], line=dict(width=1.5, color="#111c2e")),
            fill="tozeroy",
            fillcolor=pal["fill"],
            hovertemplate="%{x|%d %b %Y}<br><b>%{y:.3f}</b><extra></extra>",
        )
    )

    if reference_line is not None:
        fig.add_hline(
            y=reference_line,
            line_dash="dot",
            line_color="#94a3b8",
            line_width=1,
            annotation_text="threshold",
            annotation_position="bottom right",
            annotation_font_size=10,
            annotation_font_color="#94a3b8",
        )

    # Min / max annotations
    if values:
        min_idx = values.index(min(values))
        max_idx = values.index(max(values))
        fig.add_annotation(
            x=dates[min_idx], y=values[min_idx],
            text=f"Min {values[min_idx]:.3g}",
            showarrow=True, arrowhead=0, arrowcolor="#94a3b8",
            font=dict(size=10, color="#e2e8f0"),
            bgcolor="#182638", bordercolor="#475569", borderwidth=1, borderpad=3,
            ay=30,
        )
        if max_idx != min_idx:
            fig.add_annotation(
                x=dates[max_idx], y=values[max_idx],
                text=f"Max {values[max_idx]:.3g}",
                showarrow=True, arrowhead=0, arrowcolor="#94a3b8",
                font=dict(size=10, color="#e2e8f0"),
                bgcolor="#182638", bordercolor="#475569", borderwidth=1, borderpad=3,
                ay=-30,
            )

    fig.update_layout(
        height=370,
        margin=dict(l=45, r=20, t=25, b=45),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=True, gridcolor="rgba(148,163,184,0.15)", gridwidth=1,
            title=None,
            rangeslider=dict(visible=True, thickness=0.06, bgcolor="#182638"),
            zerolinecolor="#475569",
        ),
        yaxis=dict(
            showgrid=True, gridcolor="rgba(148,163,184,0.15)", gridwidth=1,
            title=dict(text=y_label, font=dict(size=11, color="#cbd5e1")),
            zerolinecolor="#475569",
        ),
        font=dict(family="Inter, system-ui, -apple-system, sans-serif", color="#cbd5e1"),
        hoverlabel=dict(bgcolor="#182638", bordercolor="#475569", font_color="#f1f5f9"),
        showlegend=False,
        hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# Card-based analytics widget
# ---------------------------------------------------------------------------

def _fmt(value: float | None, suffix: str = "", precision: int = 3) -> str:
    if value is None:
        return "—"
    if precision == 0:
        return f"{value:.0f}{suffix}"
    return f"{value:.{precision}g}{suffix}"


def _render_analytics_widget(analysis: dict[str, Any]) -> None:
    """Render the 4–5 metric preview cards + click-to-expand detail charts."""

    timeseries = analysis.get("timeseries") or []
    algae = analysis.get("algae") or {}
    algae_series = algae.get("ndci_trend") or timeseries

    if not timeseries:
        st.info("No observations are available. Submit a new request to run another analysis.")
        return

    # ── Gather data for each card ──────────────────────────────────────
    cards_config: list[dict[str, Any]] = []

    # 1) Water %
    w_dates, w_vals = _safe_values(timeseries, "water_percent")
    if w_vals:
        avg_w = sum(w_vals) / len(w_vals)
        arrow, css = _trend_arrow(w_vals)
        delta = w_vals[-1] - w_vals[0]
        cards_config.append({
            "key": "water", "icon": "💧", "title": "Water coverage",
            "dates": w_dates, "values": w_vals,
            "stats": [
                ("Average", _fmt(avg_w, " %", 1)),
                ("Δ Trend", f'<span class="{css}">{arrow} {delta:+.1f} %</span>'),
                ("Range", f"{min(w_vals):.0f} – {max(w_vals):.0f} %"),
            ],
            "y_label": "Water %",
            "detail_extra": {},
        })

    # 2) NDWI
    n_dates, n_vals = _safe_values(timeseries, "ndwi")
    if n_vals:
        avg_n = sum(n_vals) / len(n_vals)
        arrow, css = _trend_arrow(n_vals)
        delta = n_vals[-1] - n_vals[0]
        cards_config.append({
            "key": "ndwi", "icon": "🌊", "title": "NDWI",
            "dates": n_dates, "values": n_vals,
            "stats": [
                ("Average", _fmt(avg_n)),
                ("Δ Trend", f'<span class="{css}">{arrow} {delta:+.3f}</span>'),
                ("Range", f"{min(n_vals):.3f} – {max(n_vals):.3f}"),
            ],
            "y_label": "NDWI",
            "detail_extra": {"reference_line": 0.0},
        })

    # 3) NDTI
    t_dates, t_vals = _safe_values(timeseries, "ndti")
    if t_vals:
        avg_t = sum(t_vals) / len(t_vals)
        arrow, css = _trend_arrow(t_vals)
        delta = t_vals[-1] - t_vals[0]
        cards_config.append({
            "key": "ndti", "icon": "🟠", "title": "NDTI",
            "dates": t_dates, "values": t_vals,
            "stats": [
                ("Average", _fmt(avg_t)),
                ("Δ Trend", f'<span class="{css}">{arrow} {delta:+.3f}</span>'),
                ("Range", f"{min(t_vals):.3f} – {max(t_vals):.3f}"),
            ],
            "y_label": "NDTI",
            "detail_extra": {
                "bands": [
                    (-1, 0.1, "rgba(16,185,129,0.06)", "Low"),
                    (0.1, 0.25, "rgba(245,158,11,0.06)", "Moderate"),
                    (0.25, 1, "rgba(239,68,68,0.06)", "High"),
                ],
            },
        })

    # 4) NDCI
    c_dates, c_vals = _safe_values(algae_series, "ndci")
    if c_vals:
        avg_c = sum(c_vals) / len(c_vals)
        arrow, css = _trend_arrow(c_vals)
        cat = algae.get("category", "—")
        cards_config.append({
            "key": "ndci", "icon": "🌿", "title": "NDCI",
            "dates": c_dates, "values": c_vals,
            "stats": [
                ("Average", _fmt(avg_c)),
                ("Screening", cat),
                ("Trend", f'<span class="{css}">{arrow}</span>'),
            ],
            "y_label": "NDCI",
            "detail_extra": {
                "bands": [
                    (-1, 0.18, "rgba(16,185,129,0.06)", "Normal"),
                    (0.18, 0.24, "rgba(245,158,11,0.06)", "Elevated"),
                    (0.24, 1, "rgba(239,68,68,0.06)", "Bloom risk"),
                ],
            },
        })

    # 5) Ice (if present)
    i_dates, i_vals = _safe_values(timeseries, "ice_percent")
    if i_vals and any(v > 0 for v in i_vals):
        avg_i = sum(i_vals) / len(i_vals)
        ice_info = analysis.get("ice") or {}
        ice_status = ice_info.get("status", "—")
        cards_config.append({
            "key": "ice", "icon": "❄️", "title": "Ice screening",
            "dates": i_dates, "values": i_vals,
            "stats": [
                ("Average", _fmt(avg_i, " %", 1)),
                ("Status", ice_status.replace("_", " ").title()),
                ("Range", f"{min(i_vals):.1f} – {max(i_vals):.1f} %"),
            ],
            "y_label": "Ice %",
            "detail_extra": {"reference_line": 15.0},
        })

    if not cards_config:
        st.info("No valid metric data found in the satellite observations.")
        return

    st.markdown("#### Analytics overview")
    st.caption("Preview the trends, then expand a metric for the interactive chart.")

    for offset in range(0, len(cards_config), 2):
        cols = st.columns(2)
        for col, card in zip(cols, cards_config[offset:offset + 2]):
            with col, st.container(key=f"metric_{card['key']}"):
                stats_html = "".join(
                    f'<div class="stat-row"><span class="stat-label">{label}</span>'
                    f'<span class="stat-value">{value}</span></div>'
                    for label, value in card["stats"]
                )
                st.markdown(
                    f'<div class="card-header">'
                    f'<span class="card-icon">{card["icon"]}</span>'
                    f'<span class="card-title">{card["title"]}</span></div>',
                    unsafe_allow_html=True,
                )
                spark = _sparkline_figure(card["dates"], card["values"], card["key"])
                st.plotly_chart(
                    spark, use_container_width=True, theme=None,
                    config={"displayModeBar": False, "scrollZoom": False},
                )
                st.markdown(f'<div>{stats_html}</div>', unsafe_allow_html=True)

    # ── Expandable detail charts ──────────────────────────────────────
    for card in cards_config:
        with st.expander(f"{card['icon']}  {card['title']} — detailed chart", expanded=False):
            detail = _detail_chart(
                card["dates"],
                card["values"],
                card["key"],
                card["y_label"],
                **card["detail_extra"],
            )
            st.plotly_chart(
                detail, use_container_width=True, theme=None,
                config={"displaylogo": False, "scrollZoom": False},
            )
            # Extra context per metric
            if card["key"] == "ndci":
                interp = algae.get("interpretation")
                if interp:
                    st.caption(interp)
            if card["key"] == "ice":
                ice_info = analysis.get("ice") or {}
                lim = ice_info.get("limitations")
                if lim:
                    st.caption(lim)


st.set_page_config(page_title=APP_TITLE, page_icon="🌊", layout="wide")


def main() -> None:
    _ensure_session()
    st.markdown(_WIDGET_CSS, unsafe_allow_html=True)

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

    # A top-level chat input uses Streamlit's fixed bottom composer.
    prompt = st.chat_input("Ask in English or Czech, e.g. 'Analyze ponds in Řitka for 2025.'")

    reading_column, visual_column = st.columns([1, 1.15], gap="large")
    with reading_column, st.container(key="reading_workspace"):
        st.subheader("Conversation & report")
        st.caption("Ask a question or explore the analysis. Maps and charts have their own panel.")
        for message in st.session_state["messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt:
            st.session_state["messages"].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

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

        if st.session_state.get("ai_note"):
            st.caption(st.session_state["ai_note"])

        analysis = st.session_state.get("analysis")
        selected_pond = st.session_state.get("selected_pond")
        if analysis and selected_pond:
            with st.container(key="report"):
                st.subheader("Plain-language report")
                st.markdown(analysis.get("report", "The report is not available for this analysis."))
            with st.expander("Measurement quality and limitations"):
                quality = analysis.get("quality_summary", {})
                st.write(f"- Valid pixels: {quality.get('valid_pixels', 'not reported')}")
                st.write(f"- Data availability: {quality.get('data_quality', 'unknown')}")
                st.write(f"- Limitations: {quality.get('limitations', 'No specific limitations reported.')}")
                st.write(f"- AI/data note: {analysis.get('warning', 'No additional notes.')}")
        elif selected_pond:
            st.info(f"Selected: {selected_pond.get('name', 'Water body')}. No completed analysis is available yet; see the response above.")
        else:
            st.info("Enter a request here. Results appear after selecting a water body and completing the satellite analysis.")

    with visual_column, st.container(key="visual_workspace"):
        st.subheader("Visual workspace")
        if st.session_state.get("pending_candidates"):
            _render_pond_picker()
        elif analysis and selected_pond:
            st.markdown(f"**{selected_pond.get('name', 'Unknown water body')}**")
            date_from, date_to = analysis.get("date_from"), analysis.get("date_to")
            if date_from and date_to:
                st.caption(f"{date_from} → {date_to}")
            map_control, chart_control = st.columns(2)
            with map_control:
                show_map = st.checkbox("Show map", key="show_map")
            with chart_control:
                show_charts = st.checkbox("Show analytics charts", key="show_charts")

            views = []
            if show_charts:
                views.append("Analytics")
            if show_map:
                views.append("Map")
            if views:
                tabs = st.tabs(views)
                for name, tab in zip(views, tabs):
                    with tab:
                        if name == "Map":
                            _render_map(
                                analysis.get("geometry")
                                or selected_pond.get("geometry")
                                or demo_data.DEMO_PONDS.get(selected_pond.get("pond_id"), {}).get("geometry"),
                                selected_pond.get("name", "Water body"),
                            )
                            with st.container(key="pond_details"):
                                st.caption("WATER BODY DETAILS")
                                st.write(
                                    f"Type: {selected_pond.get('water_body_type', 'water body')} · "
                                    f"Municipality: {selected_pond.get('municipality', 'unknown')}"
                                )
                                st.write(f"Area: {selected_pond.get('area_m2', 'unknown')} m²")
                                quality = analysis.get("quality_summary", {})
                                st.caption(
                                    f"Data quality: {quality.get('data_quality', 'unknown')} · "
                                    f"Reliability: {quality.get('reliability', 'unknown')}"
                                )
                        else:
                            _render_analytics_widget(analysis)
            else:
                st.caption("Visualizations are hidden. Enable the map or analytics above to display them.")
        else:
            st.caption("Your map and chart previews will appear here once a water body is selected.")

    if analysis and selected_pond:
        with reading_column:
            series = analysis.get("timeseries") or []
            if series:
                if st.checkbox("Show measurements table", key="show_table", value=False):
                    df = pd.DataFrame(series)
                    st.subheader("Measurements")
                    columns = [
                        column
                        for column in ("date", "ndwi", "ndti", "ndci", "water_percent", "ice_percent", "valid_pixels")
                        if column in df
                    ]
                    st.dataframe(df[columns], use_container_width=True)
                if st.checkbox("Show chart interpretation", key="show_interp", value=False):
                    st.subheader("Chart interpretation")
                    st.markdown(
                        analysis.get("graph_interpretation")
                        or _fallback_chart_interpretation(analysis, analysis.get("algae", {}))
                    )
            else:
                st.info("No observations are available. Submit a new request to run another analysis.")


main()
