"""Dash app aligned to agro-via-next UI structure."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import sys

import dash
import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback, dcc, html
from dominio import calcular_score_desde_dash_payload

app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1, viewport-fit=cover"}],
    external_stylesheets=[
        *dmc.styles.ALL,
        "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;800&family=Space+Grotesk:wght@400;600;700&display=swap",
    ],
)
app.title = "AgroVIA UI Clone"
server = app.server

TERMS_DOCX_NAME = "AgroVIA_Terminos_y_Condiciones.docx"


def find_terms_document(app_dir: Path, bundle_dir: Path | None = None) -> Path:
    search_dirs = [app_dir]
    if bundle_dir and bundle_dir != app_dir:
        search_dirs.append(bundle_dir)

    candidates = [
        directory / relative_path / TERMS_DOCX_NAME
        for directory in search_dirs
        for relative_path in (Path("agro-via-next/src"), Path("."), Path("src"))
    ]
    return next((path for path in candidates if path.is_file()), candidates[0])


APP_DIR = Path(__file__).resolve().parent
TERMS_DOCX_PATH = find_terms_document(
    APP_DIR,
    Path(sys._MEIPASS) if getattr(sys, "_MEIPASS", None) else None,
)


def load_docx_paragraphs(path: Path) -> list[str]:
    try:
        with ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")

        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        root = ET.fromstring(document_xml)
        paragraphs = []
        for paragraph in root.findall(".//w:p", ns):
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns)).strip()
            if text:
                paragraphs.append(text)
        return paragraphs
    except Exception:
        return [
            "No se pudo leer el documento de términos. Verifica que "
            "AgroVIA_Terminos_y_Condiciones.docx esté en la raíz del proyecto "
            "o en agro-via-next/src/."
        ]


AGROVIA_TERMINOS = load_docx_paragraphs(TERMS_DOCX_PATH)


def _inject_cancellation_penalties_in_section_3(paragraphs: list[str]) -> list[str]:
    dador_rule = (
        "Si el dador de carga cancela el viaje antes de 48hs de su inicio, "
        "ya aceptado por ambas partes, deberá pagarle una multa del 20% del total del viaje."
    )
    transportista_rule = (
        "Si el transportista cancela el viaje con menos de 48hs de anticipación al inicio pactado, "
        "se aplicará descuento en su score y eventual cargo si el dador incurrió en gastos."
    )

    if any(dador_rule == p.strip() for p in paragraphs) and any(transportista_rule == p.strip() for p in paragraphs):
        return paragraphs

    section3_idx = next((i for i, p in enumerate(paragraphs) if p.strip().startswith("3. Relación entre las Partes")), None)
    if section3_idx is None:
        return paragraphs

    next_section_idx = next(
        (i for i in range(section3_idx + 1, len(paragraphs)) if paragraphs[i].strip().startswith("4. ")),
        len(paragraphs),
    )

    return [
        *paragraphs[:next_section_idx],
        dador_rule,
        transportista_rule,
        *paragraphs[next_section_idx:],
    ]


AGROVIA_TERMINOS = _inject_cancellation_penalties_in_section_3(AGROVIA_TERMINOS)


def _is_terms_section_heading(text: str) -> bool:
    prefix, separator, remainder = text.partition(". ")
    return bool(separator) and prefix.isdigit() and bool(remainder)


def _is_terms_subsection_heading(text: str) -> bool:
    first, dot, remainder = text.partition(".")
    if not dot or not first.isdigit():
        return False
    second, separator, trailing = remainder.partition(". ")
    return second.isdigit() and bool(separator) and bool(trailing)


def render_terms_content(paragraphs: list[str]) -> list[html.Component]:
    blocks: list[html.Component] = []
    for paragraph in paragraphs:
        if paragraph == "AGROVIA S.A.S.":
            blocks.append(
                html.Div(
                    paragraph,
                    style={
                        "fontSize": "12px",
                        "fontWeight": "700",
                        "letterSpacing": "0.12em",
                        "textTransform": "uppercase",
                        "color": "#6b7a6b",
                        "marginBottom": "8px",
                    },
                )
            )
        elif paragraph.startswith("Términos y Condiciones de Uso de la Plataforma"):
            blocks.append(
                html.H2(
                    paragraph,
                    style={
                        "margin": "0 0 8px",
                        "fontSize": "30px",
                        "lineHeight": "1.1",
                        "letterSpacing": "-0.03em",
                        "color": "#152515",
                    },
                )
            )
        elif paragraph.startswith("Versión"):
            blocks.append(
                html.Div(
                    paragraph,
                    style={
                        "fontSize": "13px",
                        "fontWeight": "600",
                        "color": "#7a7f73",
                        "marginBottom": "20px",
                    },
                )
            )
        elif paragraph == "Preámbulo" or _is_terms_section_heading(paragraph):
            blocks.append(
                html.H3(
                    paragraph,
                    style={
                        "margin": "26px 0 10px",
                        "paddingTop": "14px",
                        "borderTop": "1px solid rgba(21,37,21,0.12)",
                        "fontSize": "19px",
                        "fontWeight": "800",
                        "lineHeight": "1.25",
                        "color": "#152515",
                    },
                )
            )
        elif _is_terms_subsection_heading(paragraph):
            blocks.append(
                html.H4(
                    paragraph,
                    style={
                        "margin": "18px 0 8px",
                        "fontSize": "15px",
                        "fontWeight": "700",
                        "color": "#243524",
                    },
                )
            )
        elif paragraph.startswith("AgroVIA S.A.S. — "):
            blocks.append(
                html.Div(
                    paragraph,
                    style={
                        "margin": "24px 0 0",
                        "padding": "14px 16px",
                        "borderRadius": "14px",
                        "background": "rgba(18,35,21,0.06)",
                        "fontSize": "13px",
                        "fontWeight": "600",
                        "color": "#243524",
                    },
                )
            )
        else:
            blocks.append(
                html.P(
                    paragraph,
                    style={
                        "margin": "0 0 12px",
                        "lineHeight": "1.7",
                        "color": "#243524",
                        "fontSize": "14px",
                    },
                )
            )
    return blocks


def create_route_map_figure(origen, destino, eta):
    """Create a Plotly figure for the route map."""
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=[70, 150, 220, 280, 300],
        y=[160, 130, 100, 70, 48],
        mode='lines',
        line=dict(color='#c8a84b', width=4, shape='spline'),
        hoverinfo='skip',
        showlegend=False,
    ))
    
    # Origin circle
    fig.add_trace(go.Scatter(
        x=[70], y=[160],
        mode='markers',
        marker=dict(size=16, color='#22c55e', line=dict(color='#22c55e', width=3)),
        hovertext=f"Origen: {origen}",
        showlegend=False,
    ))
    
    # Destination circle
    fig.add_trace(go.Scatter(
        x=[300], y=[48],
        mode='markers',
        marker=dict(size=16, color='#c8a84b', line=dict(color='#c8a84b', width=3)),
        hovertext=f"Destino: {destino}",
        showlegend=False,
    ))
    
    # Truck position (middle)
    fig.add_trace(go.Scatter(
        x=[214], y=[93],
        mode='markers',
        marker=dict(size=14, color='#efe6d1', line=dict(color='#efe6d1', width=2)),
        hovertext=f"Tu camión · ETA: {eta}",
        showlegend=False,
    ))
    
    fig.update_layout(
        xaxis=dict(
            showgrid=False, zeroline=False, visible=False,
            range=[0, 360],
        ),
        yaxis=dict(
            showgrid=False, zeroline=False, visible=False,
            range=[0, 220],
        ),
        plot_bgcolor='#1a2e1a',
        paper_bgcolor='#1a2e1a',
        margin=dict(l=10, r=10, t=30, b=10),
        height=220,
        hovermode='closest',
    )
    
    return fig


def create_score_gauge_figure(score: float) -> go.Figure:
    """Gauge visual for score 0..100."""
    score = max(0.0, min(100.0, float(score)))
    if score >= 80:
        bar_color = "#22c55e"
    elif score >= 65:
        bar_color = "#c8a84b"
    else:
        bar_color = "#ef4444"

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": "", "font": {"size": 36, "color": "#efe6d1"}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#efe6d1"},
                "bgcolor": "#122315",
                "borderwidth": 0,
                "bar": {"color": bar_color, "thickness": 0.35},
                "steps": [
                    {"range": [0, 50], "color": "rgba(239,68,68,0.25)"},
                    {"range": [50, 80], "color": "rgba(200,168,75,0.25)"},
                    {"range": [80, 100], "color": "rgba(34,197,94,0.25)"},
                ],
            },
        )
    )
    fig.update_layout(
        paper_bgcolor="#122315",
        plot_bgcolor="#122315",
        margin={"l": 10, "r": 10, "t": 10, "b": 0},
        height=180,
    )
    return fig


def create_dador_trip_map_figure(origen, destino, eta, alert_label: str | None = None):
    """Desktop map for dador monitoring views."""
    route_color = "#ef4444" if alert_label else "#1f3d22"
    current_color = "#ef4444" if alert_label else "#c8a84b"
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=[80, 160, 250, 330, 430, 520],
        y=[70, 110, 165, 210, 250, 280],
        mode="lines",
        line=dict(color=route_color, width=5, shape="spline"),
        hoverinfo="skip",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[80],
        y=[70],
        mode="markers",
        marker=dict(size=18, color="#22c55e", line=dict(color="#22c55e", width=3)),
        hovertext=f"Origen: {origen}",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[520],
        y=[280],
        mode="markers",
        marker=dict(size=18, color="#c8a84b", line=dict(color="#c8a84b", width=3)),
        hovertext=f"Destino: {destino}",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[330],
        y=[210],
        mode="markers",
        marker=dict(size=16, color=current_color, line=dict(color=current_color, width=2)),
        hovertext=f"Camión en ruta · ETA {eta}",
        showlegend=False,
    ))

    annotations = [
        dict(x=80, y=48, text=origen, showarrow=False, font=dict(size=12, color="#1a241b", family="DM Sans")),
        dict(x=520, y=302, text=destino, showarrow=False, font=dict(size=12, color="#1a241b", family="DM Sans")),
        dict(x=330, y=188, text=f"Camión · ETA {eta}", showarrow=False, font=dict(size=11, color="#1a241b", family="DM Sans")),
    ]
    if alert_label:
        annotations.append(
            dict(
                x=415,
                y=182,
                text=alert_label,
                showarrow=False,
                bgcolor="#fee2e2",
                bordercolor="#ef4444",
                borderpad=6,
                font=dict(size=11, color="#991b1b", family="DM Sans"),
            )
        )

    fig.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, visible=False, range=[0, 600]),
        yaxis=dict(showgrid=False, zeroline=False, visible=False, range=[0, 360]),
        plot_bgcolor="#f5f2eb",
        paper_bgcolor="#f5f2eb",
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
        annotations=annotations,
        hovermode="closest",
    )
    return fig


def build_dador_timeline_steps(milestones):
    status_map = {
        "done": ("✓", "#22c55e", "rgba(34,197,94,0.18)"),
        "active": ("●", "#c8a84b", "rgba(200,168,75,0.18)"),
        "pending": ("○", "rgba(107,122,107,0.65)", "rgba(215,209,191,0.35)"),
    }
    steps = []
    for idx, milestone in enumerate(milestones):
        last = idx == len(milestones) - 1
        icon, color, background = status_map[milestone["status"]]
        steps.append(
            html.Div(className="d-t-step", children=[
                html.Div(className="d-t-col", children=[
                    html.Div(icon, className="d-t-dot", style={"background": background, "color": color, "border": f"1px solid {color}"}),
                    *([html.Div(className=f"d-t-line {'done' if milestone['status'] in ('done', 'active') else 'pending'}")] if not last else []),
                ]),
                html.Div(className="d-t-body", children=[
                    html.Div(milestone["title"], className="d-t-label" + ("  muted" if milestone["status"] == "pending" else "")),
                    html.Div(f"{milestone['timestamp']} · {milestone['geo']}", className="d-t-time"),
                    html.Div(milestone["detail"], className="traz-val", style={"marginTop": "6px"}),
                ]),
            ])
        )
    return steps


def build_dador_completed_attachments(milestones):
    done_steps = [step for step in milestones if step.get("status") == "done" and step.get("adjuntos")]
    if not done_steps:
        return [html.Span("Sin adjuntos cargados", className="dador-chip")]

    chips = []
    for step in done_steps:
        for adjunto in step["adjuntos"]:
            chips.append(html.Span(step["title"] + " · " + adjunto, className="dador-chip"))
    return chips


def dador_carga_icon(carga: str) -> str:
    icons = {
        "Soja": "🌱",
        "Maíz": "🌽",
        "Trigo": "🌾",
        "Cebada": "🌾",
        "Arroz": "🍚",
        "Sorgo": "🌾",
        "Fertilizante": "🧪",
        "Arena": "🏖️",
        "Harina": "🧺",
    }
    return icons.get(carga, "📦")


def render_dador_active_trip_card(viaje):
    completed_steps = sum(1 for step in viaje["milestones"] if step["status"] == "done")
    progress_pct = int((completed_steps / len(viaje["milestones"])) * 100)
    severity_label = "Alta severidad" if viaje["incidente_activo"] else "Sin incidentes"
    card_body = html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.Span(viaje["id"], className="dador-rich-id"),
                    html.Span(dador_carga_icon(viaje["mercaderia"]) + " " + viaje["mercaderia"], className="dador-type-badge"),
                    html.Span(
                        "Incidente activo" if viaje["incidente_activo"] else "En curso",
                        className="state-transit" if viaje["incidente_activo"] else "state-done",
                        style={"background": "#fee2e2" if viaje["incidente_activo"] else None, "color": "#991b1b" if viaje["incidente_activo"] else None},
                    ),
                ], className="dador-rich-top"),
                html.Div(viaje["origen"] + " → " + viaje["destino"], className="dador-rich-route"),
                html.Div(viaje["mercaderia"] + " · " + viaje["peso"] + " · ETA " + viaje["eta"], className="dador-rich-sub"),
            ], style={"flex": "1"}),
            html.Div([
                html.Div("Transportista", className="dador-rich-label"),
                html.Div(viaje["transportista"], className="dador-rich-value"),
                html.Div("Score " + str(viaje["score"]) + " · " + viaje["camion"], className="dador-rich-sub"),
            ], className="dador-rich-side"),
        ], className="dador-rich-header"),
        html.Div([
            html.Span("GPS " + viaje["gps"], className="dador-chip"),
            html.Span("Tarifa " + _pesos(viaje["tarifa"]), className="dador-chip"),
            html.Span(viaje["cpd"], className="dador-chip"),
            html.Span(viaje["ctg"], className="dador-chip"),
        ], className="dador-chip-row"),
        html.Div(build_dador_completed_attachments(viaje["milestones"]), className="dador-chip-row"),
        html.Div([
            html.Div([
                html.Div("Progreso operativo", className="dador-metric-label"),
                html.Div(str(progress_pct) + "% · " + str(completed_steps) + "/" + str(len(viaje["milestones"])) + " hitos", className="dador-metric-value"),
                html.Div(className="dador-metric-bar", children=[html.Div(className="dador-metric-fill success", style={"width": f"{progress_pct}%"})]),
            ], className="dador-metric-card"),
            html.Div([
                html.Div("Severidad", className="dador-metric-label"),
                html.Div(severity_label, className="dador-metric-value" + (" danger" if viaje["incidente_activo"] else "")),
                html.Div(className="dador-metric-bar", children=[html.Div(className="dador-metric-fill danger" if viaje["incidente_activo"] else "dador-metric-fill muted", style={"width": "82%" if viaje["incidente_activo"] else "18%"})]),
            ], className="dador-metric-card"),
        ], className="dador-metric-grid"),
        html.Div([
            html.Div(viaje["alerta"] if viaje["alerta"] else "Viaje dentro de parámetros operativos", className="dador-rich-alert" + (" danger" if viaje["alerta"] else "")),
            html.Span("Abrir detalle →", className="action-link"),
        ], className="dador-rich-actions"),
    ], className="dador-rich-card")
    return _btn(card_body, f"dador:cargas_en_viaje:{viaje['id']}", className="dador-rich-card-btn")


def render_dador_match_card(carga_id, match, waiting_response=False, waiting_label="Esperando respuesta del transportista"):
    compat_pct = max(0, min(int(match["compat"]), 100))
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.Span(str(match["compat"]) + "% compatibilidad", className="dador-chip emphasis"),
                    html.Span("Score " + str(match["score"]), className="dador-chip"),
                ], className="dador-chip-row"),
                html.Div(match["nombre"], className="dador-rich-route"),
                html.Div(match["cuit"], className="dador-rich-sub"),
                html.Div(match["camion"] + " · " + match["patente"], className="dador-rich-sub", style={"marginTop": "6px"}),
            ], style={"flex": "1"}),
            html.Div([
                html.Div("Rating " + match["rating"], className="dador-rich-value"),
                html.Div(str(match["viajes"]) + " viajes", className="dador-rich-sub"),
                html.Div(match["distancia_origen"] + " al origen", className="dador-rich-sub"),
            ], className="dador-rich-side"),
        ], className="dador-rich-header"),
        html.Div([
            html.Div("Compatibilidad del matching", className="dador-metric-label"),
            html.Div(str(compat_pct) + "%", className="dador-metric-value"),
            html.Div(className="dador-metric-bar", children=[html.Div(className="dador-metric-fill gold", style={"width": f"{compat_pct}%"})]),
        ], className="dador-metric-card", style={"marginTop": "14px"}),
        html.Div(
            [html.Span(match["docs"], className="dador-chip")]
            if "docs" in match
            else [
                html.Span("RTO " + str(match.get("rto", "-")), className="dador-chip"),
                html.Span("Seguro " + str(match.get("seguro", "-")), className="dador-chip"),
                html.Span("Satelital " + str(match.get("satelital", "-")), className="dador-chip"),
            ],
            className="dador-chip-row",
        ),
        html.Div(
            [
                html.Span(waiting_label, className="dador-chip emphasis"),
            ]
            if waiting_response
            else [
                html.Button("Confirmar", className="action-link"),
                html.Button("Rechazar", className="action-link"),
            ],
            className="dador-rich-actions",
            style={"justifyContent": "flex-end"},
        ),
    ], className="dador-rich-card compact")


def render_dador_published_load_card(carga):
    best_match = max((match["compat"] for match in carga["matches"]), default=0)
    estado_publicacion = carga["estado"]
    estado_badge_class = "state-looking" if estado_publicacion == "Publicado" else ("state-done" if estado_publicacion == "Pendiente de inicio" else "state-transit")
    estado_metric_text = "En búsqueda activa"
    estado_metric_fill = "dador-metric-fill muted"
    estado_metric_width = "44%"
    if estado_publicacion == "Aceptado":
        estado_metric_text = "Con asignación pendiente"
        estado_metric_fill = "dador-metric-fill success"
        estado_metric_width = "72%"
    elif estado_publicacion == "Pendiente de inicio":
        estado_metric_text = "Todo OK · pendiente de inicio"
        estado_metric_fill = "dador-metric-fill success"
        estado_metric_width = "90%"
    card_body = html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.Span(carga["id"], className="dador-rich-id"),
                    html.Span(dador_carga_icon(carga["mercaderia"]) + " " + carga["mercaderia"], className="dador-type-badge"),
                    html.Span(estado_publicacion, className=estado_badge_class),
                ], className="dador-rich-top"),
                html.Div(carga["origen"] + " → " + carga["destino"], className="dador-rich-route"),
                html.Div(carga["mercaderia"] + " · " + carga["peso"], className="dador-rich-sub"),
            ], style={"flex": "1"}),
            html.Div([
                html.Div("Ventana de carga", className="dador-rich-label"),
                html.Div(carga["ventana_carga"], className="dador-rich-value"),
                html.Div(carga["ventana_descarga"], className="dador-rich-sub"),
            ], className="dador-rich-side"),
        ], className="dador-rich-header"),
        html.Div([
            html.Span(str(len(carga["matches"])) + " propuestas de matching", className="dador-chip emphasis"),
            html.Span("Estado " + carga["estado"], className="dador-chip"),
            html.Span("Tarifa " + _pesos(carga["tarifa"]), className="dador-chip"),
        ], className="dador-chip-row"),
        html.Div([
            html.Div([
                html.Div("Cobertura de matching", className="dador-metric-label"),
                html.Div(str(best_match) + "% mejor candidato", className="dador-metric-value"),
                html.Div(className="dador-metric-bar", children=[html.Div(className="dador-metric-fill gold", style={"width": f"{best_match}%"})]),
            ], className="dador-metric-card"),
            html.Div([
                html.Div("Estado de publicación", className="dador-metric-label"),
                html.Div(estado_metric_text, className="dador-metric-value"),
                html.Div(className="dador-metric-bar", children=[html.Div(className=estado_metric_fill, style={"width": estado_metric_width})]),
            ], className="dador-metric-card"),
        ], className="dador-metric-grid"),
        html.Div([
            html.Div("Ventanas: carga " + carga["ventana_carga"] + " · descarga " + carga["ventana_descarga"], className="dador-rich-alert"),
            html.Span("Abrir detalle →", className="action-link"),
        ], className="dador-rich-actions"),
    ], className="dador-rich-card")
    return _btn(card_body, f"dador:publicadas:{carga['id']}", className="dador-rich-card-btn")


def render_dador_history_card(viaje):
    closed_steps = len(viaje["milestones"])
    avg_rating = 4.5 if viaje["calif_dada"] == "5/5" else 4.0
    card_body = html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.Span(viaje["id"], className="dador-rich-id"),
                    html.Span(dador_carga_icon(viaje["mercaderia"]) + " " + viaje["mercaderia"], className="dador-type-badge"),
                    html.Span(viaje["estado"], className="state-done"),
                ], className="dador-rich-top"),
                html.Div(viaje["ruta"], className="dador-rich-route"),
                html.Div(viaje["mercaderia"] + " · " + viaje["fecha"], className="dador-rich-sub"),
            ], style={"flex": "1"}),
            html.Div([
                html.Div("Tarifa", className="dador-rich-label"),
                html.Div(_pesos(viaje["tarifa"]), className="dador-rich-value"),
                html.Div("Dada " + viaje["calif_dada"] + " · Recibida " + viaje["calif_recibida"], className="dador-rich-sub"),
            ], className="dador-rich-side"),
        ], className="dador-rich-header"),
        html.Div([
            html.Div([
                html.Div("Cierre documental", className="dador-metric-label"),
                html.Div(str(closed_steps) + " hitos cerrados", className="dador-metric-value"),
                html.Div(className="dador-metric-bar", children=[html.Div(className="dador-metric-fill success", style={"width": "100%"})]),
            ], className="dador-metric-card"),
            html.Div([
                html.Div("Promedio reputacional", className="dador-metric-label"),
                html.Div(f"{avg_rating:.1f}/5", className="dador-metric-value"),
                html.Div(className="dador-metric-bar", children=[html.Div(className="dador-metric-fill gold", style={"width": f"{int(avg_rating * 20)}%"})]),
            ], className="dador-metric-card"),
        ], className="dador-metric-grid"),
        html.Div([html.Span("Docs: " + ", ".join(viaje["docs"]), className="dador-chip")], className="dador-chip-row"),
        html.Div([
            html.Div("4 hitos cerrados con geolocalización y documentos", className="dador-rich-alert"),
            html.Span("Abrir resumen →", className="action-link"),
        ], className="dador-rich-actions"),
    ], className="dador-rich-card")
    return _btn(card_body, f"dador:historial:{viaje['id']}", className="dador-rich-card-btn")

VIAJES = [
    {
        "id": "#5001",
        "origen": "Tucuman",
        "destino": "Rosario",
        "direccion_origen": "Planta San Miguel, Ruta 34 km 1200, Tucumán",
        "direccion_destino": "Terminal 6, San Lorenzo, Santa Fe",
        "carga": "Soja",
        "toneladas": 15,
        "distancia": 820,
        "tarifa": 420000,
        "plazo_pago": "45 días",
        "instrumento": "ECHEQ",
        "empresa_dador": "Cooperativa AgroSur S.A.",
        "cuit": "30-71438920-1",
        "rating": "4,7",
        "viajes_dador": 128,
        "ventana_carga": "18/07 · 08:00 a 11:00",
        "ventana_descarga": "19/07 · 06:00 a 09:00",
        "adelantable": 273000,
        "fee_qp": 18291,
        "neto_qp": 254709,
        "quickpay_habilitado": True,
        "requisito_qp": "",
        "documentacion_ok": True,
        "doc_alerta": "Todos tus documentos están vigentes",
        "retorno": "Fertilizantes | Rosario -> Tucuman | $380.000",
        "score_min": 50,
        "tipo_flujo": "disponible",
        "hito_actual": "inicio_carga",
        "gps_origen_validado": False,
        "gps_destino_validado": False,
    },
    {
        "id": "#5002",
        "origen": "Santiago del Estero",
        "destino": "San Lorenzo",
        "direccion_origen": "Acceso Norte, La Banda, Santiago del Estero",
        "direccion_destino": "Puerto General San Martín, Santa Fe",
        "carga": "Maiz",
        "toneladas": 15,
        "distancia": 680,
        "tarifa": 340000,
        "plazo_pago": "30 días",
        "instrumento": "ECHEQ",
        "empresa_dador": "Molinos del Litoral S.A.",
        "cuit": "30-69874123-8",
        "rating": "4,5",
        "viajes_dador": 84,
        "ventana_carga": "17/07 · 14:00 a 18:00",
        "ventana_descarga": "18/07 · 07:00 a 11:00",
        "adelantable": 0,
        "fee_qp": 0,
        "neto_qp": 0,
        "quickpay_habilitado": False,
        "requisito_qp": "Esperando validación del dador para confirmar el viaje",
        "documentacion_ok": True,
        "doc_alerta": "Propuesta enviada. Pendiente de confirmación del dador",
        "retorno": "",
        "score_min": 50,
        "tipo_flujo": "en_espera",
        "hito_actual": "inicio_carga",
        "gps_origen_validado": False,
        "gps_destino_validado": False,
    },
    {
        "id": "#5003",
        "origen": "Salta",
        "destino": "Rosario",
        "direccion_origen": "Centro de acopio Güemes, Salta",
        "direccion_destino": "Terminal ACA, Rosario, Santa Fe",
        "carga": "Trigo",
        "toneladas": 15,
        "distancia": 1150,
        "tarifa": 580000,
        "plazo_pago": "21 días",
        "instrumento": "Transferencia / ECHEQ",
        "empresa_dador": "Agroexportadora del Norte S.A.",
        "cuit": "30-70999881-2",
        "rating": "4,9",
        "viajes_dador": 212,
        "ventana_carga": "20/07 · 06:00 a 09:00",
        "ventana_descarga": "21/07 · 09:00 a 12:00",
        "adelantable": 377000,
        "fee_qp": 25259,
        "neto_qp": 351741,
        "quickpay_habilitado": True,
        "requisito_qp": "",
        "documentacion_ok": False,
        "doc_alerta": "RTO vencida. Regularizala para iniciar este viaje",
        "retorno": "Agroquimicos | Rosario -> Salta | $420.000",
        "score_min": 60,
        "tipo_flujo": "proximo",
        "hito_actual": "inicio_carga",
        "gps_origen_validado": False,
        "gps_destino_validado": False,
    },
    {
        "id": "#5004",
        "origen": "Corrientes",
        "destino": "San Lorenzo",
        "direccion_origen": "Planta Norte, Corrientes",
        "direccion_destino": "Terminal 6, San Lorenzo, Santa Fe",
        "carga": "Soja",
        "toneladas": 15,
        "distancia": 760,
        "tarifa": 385000,
        "plazo_pago": "35 días",
        "instrumento": "ECHEQ",
        "empresa_dador": "Granos del Litoral S.A.",
        "cuit": "30-70111222-3",
        "rating": "4,6",
        "viajes_dador": 97,
        "ventana_carga": "18/07 · 06:00 a 09:00",
        "ventana_descarga": "19/07 · 05:00 a 08:00",
        "adelantable": 250250,
        "fee_qp": 16767,
        "neto_qp": 233483,
        "quickpay_habilitado": True,
        "requisito_qp": "",
        "documentacion_ok": True,
        "doc_alerta": "Todos tus documentos están vigentes",
        "retorno": "",
        "score_min": 55,
        "tipo_flujo": "proximo",
        "hito_actual": "inicio_carga",
        "gps_origen_validado": False,
        "gps_destino_validado": False,
    },
    {
        "id": "#5005",
        "origen": "Formosa",
        "destino": "Rosario",
        "direccion_origen": "Acopio Este, Formosa",
        "direccion_destino": "Puerto Rosario, Santa Fe",
        "carga": "Sorgo",
        "toneladas": 15,
        "distancia": 1020,
        "tarifa": 510000,
        "plazo_pago": "45 días",
        "instrumento": "ECHEQ",
        "empresa_dador": "Cooperativa Centro Norte",
        "cuit": "30-73322119-4",
        "rating": "4,4",
        "viajes_dador": 51,
        "ventana_carga": "22/07 · 08:00 a 12:00",
        "ventana_descarga": "23/07 · 08:00 a 11:00",
        "adelantable": 0,
        "fee_qp": 0,
        "neto_qp": 0,
        "quickpay_habilitado": False,
        "requisito_qp": "Oferta publicada por vos. Esperando dador.",
        "documentacion_ok": True,
        "doc_alerta": "Oferta activa sin asignación",
        "retorno": "",
        "score_min": 60,
        "tipo_flujo": "oferta_publicada",
        "hito_actual": "inicio_carga",
        "gps_origen_validado": False,
        "gps_destino_validado": False,
    },
]

NOTIFICACIONES_TRANSPORTISTA = [
    {
        "icono": "⚡",
        "titulo": "Acreditación QuickPay",
        "texto": "Meridiano Norte te acredita tu QuickPay en tu cuenta · Viaje Salta → Rosario · $345.300",
        "fecha": "Hoy · 08:42",
        "accion": "tab:perfil",
    },
    {
        "icono": "📦",
        "titulo": "Nuevo viaje propuesto",
        "texto": "Tenés una nueva propuesta de viaje: Tucumán → Rosario · Soja · $420.000",
        "fecha": "Hoy · 07:10",
        "accion": "viaje:5001",
    },
    {
        "icono": "⚠",
        "titulo": "Documento por vencer",
        "texto": "Tu RTO vence en 12 días. Actualizalo para no perder el acceso al matching.",
        "fecha": "Ayer · 18:20",
        "accion": "tab:perfil",
    },
    {
        "icono": "🔧",
        "titulo": "Revisión pre-viaje",
        "texto": "Antes de salir, revisa frenos, luces y neumáticos antes de arrancar",
        "fecha": "Hoy · 06:30",
        "accion": None,
    },
    {
        "icono": "⏱️",
        "titulo": "Descansa",
        "texto": "Llevas 2 horas manejando, es momento de parar y estirarte",
        "fecha": "Hoy · 10:45",
        "accion": None,
    },
    {
        "icono": "⛈️",
        "titulo": "Alerta climática",
        "texto": "Condiciones climáticas adversas en tu ruta: maneja con precaución",
        "fecha": "Hoy · 09:20",
        "accion": None,
    },
    {
        "icono": "🚫",
        "titulo": "Seguridad vial",
        "texto": "No beba mientras maneja",
        "fecha": "Hoy · 08:00",
        "accion": None,
    },
]

PROXIMOS_VIAJES = [
    {
        "id": "#5001",
        "origen": "Tucuman",
        "destino": "Rosario",
        "carga": "Soja",
        "toneladas": 15,
        "tarifa": 420000,
        "ventana": "18/07 · 08:00 a 11:00",
        "quickpay": "QuickPay habilitado · hasta $273.000",
        "dias_inicio": 3,
    },
    {
        "id": "#5003",
        "origen": "Salta",
        "destino": "Rosario",
        "carga": "Trigo",
        "toneladas": 15,
        "tarifa": 580000,
        "ventana": "20/07 · 06:00 a 09:00",
        "quickpay": "QuickPay habilitado · hasta $377.000",
        "dias_inicio": 5,
    },
]

VIAJES_EN_ESPERA = [
    {
        "id": "#5010",
        "origen": "Santiago del Estero",
        "destino": "San Lorenzo",
        "carga": "Maiz",
        "toneladas": 15,
        "tarifa": 340000,
        "espera": "Esperando hace 2 hs",
    },
    {
        "id": "#5011",
        "origen": "Cordoba",
        "destino": "Rosario",
        "carga": "Fertilizante",
        "toneladas": 28,
        "tarifa": 390000,
        "espera": "Esperando hace 35 min",
    },
]

VIAJE_EN_CURSO = {
    "id": "#4821",
    "origen": "Tucuman",
    "destino": "Rosario",
    "carga": "Soja",
    "toneladas": 15,
    "eta": "Llega en 2 hs 30 min",
    "offline": False,
    "empresa_dador": "Cooperativa AgroSur S.A.",
    "cuit": "30-71438920-1",
    "telefono": "+54 9 341 555 8831",
    "rating": "4,7",
}

HITOS_VIAJE_EN_CURSO = [
    {
        "titulo": "Inicio de carga",
        "estado": "done",
        "accion": "CPD firmada adjunta",
        "validacion": "GPS validado en origen · 15/07 08:46",
        "adjunto": "Foto CPD obligatoria",
    },
    {
        "titulo": "Salida en tránsito",
        "estado": "done",
        "accion": "Salida confirmada",
        "validacion": "Tracking GPS activo · 15/07 09:12",
        "adjunto": "Sin adjunto requerido",
    },
    {
        "titulo": "Llegada a destino",
        "estado": "active",
        "accion": "Confirmar arribo al punto de descarga",
        "validacion": "ETA dinámica 2 hs 30 min · espera validación GPS en destino",
        "adjunto": "Sin adjunto requerido",
    },
    {
        "titulo": "Descarga y cierre",
        "estado": "pending",
        "accion": "Adjuntar remito y, si aplica, ticket de balanza para cerrar el viaje",
        "validacion": "Se habilita después de la llegada a destino",
        "adjunto": "Foto de remito (obligatoria) + ticket de balanza si corresponde",
    },
]

# Checklists de buenas prácticas por hito (hito_num 1..4)
# Cada hito puede tener UNA O MÁS listas de verificación.
# El ítem con "solo_granos": True se muestra únicamente si la carga es cereal/grano.
CHECKLIST_POR_HITO: dict[int, list[dict]] = {
    1: [
        {
            "id": "cl_1a",
            "nombre_corto": "Al llegar al punto de carga",
            "titulo": "Checklist · Al llegar al punto de carga",
            "items": [
                {"id": "c1_fosfina",    "texto": "Revisé que el cereal no tiene fosfina activa (o esperé las 48-72 hs)", "solo_granos": True},
                {"id": "c1_viento",     "texto": "Me ubiqué a favor del viento, alejado de la carga",                   "solo_granos": False},
                {"id": "c1_epp",        "texto": "Tengo protección visual y barbijo puestos",                            "solo_granos": False},
                {"id": "c1_carroceria", "texto": "No subí a la carrocería para el desenlonado",                          "solo_granos": False},
            ],
        },
        {
            "id": "cl_1b",
            "nombre_corto": "Al cargar",
            "titulo": "Checklist · Al cargar",
            "items": [
                {"id": "c2_plataforma", "texto": "Verifiqué la distribución del cereal usando la plataforma del establecimiento (no la carrocería)", "solo_granos": False},
                {"id": "c2_ejes",       "texto": "La carga quedó bien distribuida por ejes",                             "solo_granos": False},
                {"id": "c2_lona",       "texto": "La lona quedó bien asegurada con los chicotes",                        "solo_granos": False},
            ],
        },
    ],
    3: [
        {
            "id": "cl_3",
            "nombre_corto": "Al llegar a la playa / precalado",
            "titulo": "Checklist · Al llegar a la playa / precalado",
            "items": [
                {"id": "c3_chaleco", "texto": "Bajé con chaleco reflectivo",                                          "solo_granos": False},
                {"id": "c3_señal",   "texto": "Respeto la señalización interna de circulación",                       "solo_granos": False},
                {"id": "c3_freno",   "texto": "El vehículo quedó con freno de mano y motor apagado",                  "solo_granos": False},
            ],
        },
    ],
    4: [
        {
            "id": "cl_4",
            "nombre_corto": "Al descargar",
            "titulo": "Checklist · Al descargar",
            "items": [
                {"id": "c4_zona",      "texto": "Me ubiqué en la casilla o zona segura delimitada",   "solo_granos": False},
                {"id": "c4_epp",       "texto": "Usé protección visual durante la descarga",           "solo_granos": False},
                {"id": "c4_boquillas", "texto": "Cerré bien boquillas y tapas antes de retirarme",      "solo_granos": False},
            ],
        },
    ],
}

# Lookup rápido cl_id → dict del checklist
_CL_BY_ID: dict[str, dict] = {
    cl["id"]: cl
    for cls in CHECKLIST_POR_HITO.values()
    for cl in cls
}

def _hito_checklist_done(hito_num: int, cl_data: dict) -> bool:
    """True si todos los checklists del hito están confirmados (o el hito no tiene checklists)."""
    cls = CHECKLIST_POR_HITO.get(hito_num, [])
    if not cls:
        return True
    return all(cl_data.get(cl["id"]) for cl in cls)

# Tipos de carga considerados granos/cereales para el ítem de fosfina
_TIPOS_GRANO = {"soja", "maiz", "maíz", "trigo", "cebada", "girasol", "sorgo", "arroz", "cereal", "grano"}

def _es_grano(carga: str) -> bool:
    return any(g in carga.lower() for g in _TIPOS_GRANO)

HIST_DADOR = [
    ["15/07", "#4821", "Soja 15tn",       "Carlos G.",  "74", "$420.000", "En tránsito", "-"],
    ["08/07", "#4817", "Maíz 15tn",        "Roberto M.", "82", "$340.000", "Entregado",   "Calificar"],
    ["01/07", "#4816", "Soja 20tn",        "Carlos G.",  "74", "$450.000", "Cerrado",     "5 ⭐"],
]

VIAJES_POR_MES = [
    {"mes": "Ene", "viajes": 4},
    {"mes": "Feb", "viajes": 6},
    {"mes": "Mar", "viajes": 5},
    {"mes": "Abr", "viajes": 8},
    {"mes": "May", "viajes": 7},
    {"mes": "Jun", "viajes": 9},
    {"mes": "Jul", "viajes": 11},
]

DOCUMENTACION = [
    {"nombre": "Licencia Cat. E", "estado": "ok",      "vence": "12/2026"},
    {"nombre": "Seguro RC",       "estado": "ok",      "vence": "08/2025"},
    {"nombre": "RTO",             "estado": "warning", "vence": "07/2025"},
    {"nombre": "ART",             "estado": "ok",      "vence": "15/07/2025"},
]

PERFIL_TRANSPORTISTA = {
    "iniciales": "CG",
    "nombre": "Carlos González",
    "cuit": "20-28473921-4",
    "fiscal": "Monotributo",
    "telefono": "+54 9 381 555 2184",
    "email": "carlos.gonzalez@agrovia.com",
    "provincia": "Tucumán",
}

CAMIONES_TRANSPORTISTA = [
    {
        "patente": "AE 548 QL",
        "tipo": "Semirremolque",
        "cedula": "Verificada contra CUIT en onboarding",
        "satelital": "Sí",
    },
    {
        "patente": "AF 127 NR",
        "tipo": "Chasis con acoplado",
        "cedula": "Verificada contra CUIT en onboarding",
        "satelital": "Sí",
    },
]

DOCS_CAMION = [
    {"nombre": "Cédula verde",      "detalle": "Reg. Nacional Automotor · Vigente",             "estado": "ok",      "accion": "Actualizar foto", "imagen": "/assets/cedula.avif"},
    {"nombre": "Seguro RC automotor", "detalle": "La Caja · Póliza 448921 · Vence 12/09/2026", "estado": "ok",      "accion": "Actualizar",     "imagen": "/assets/RC_automotor.png"},
    {"nombre": "RTO",                 "detalle": "Vence 30/07/2026",                           "estado": "warning", "accion": "Actualizar foto", "imagen": "/assets/rto.jpg"},
]

DOCS_CONDUCTOR = [
    {"nombre": "Licencia de conducir", "detalle": "Clase E · Vence 14/03/2027",        "estado": "ok", "accion": "Actualizar foto", "imagen": "/assets/LicenciaConducir.jpg"},
    {"nombre": "ART del conductor",    "detalle": "Prevención ART · Vence 15/08/2026", "estado": "ok", "accion": "Actualizar",     "imagen": None},
]

CONFIGURACION_SOPORTE = [
    "Configuraciones",
    "Contactar soporte operativo",
    "Términos y condiciones",
    "Manual de buenas prácticas",
    "Cerrar sesión",
]

HISTORIAL_TRANS = [
    {"fecha": "14/07", "ruta": "Tucumán → Córdoba",        "tarifa": 320000},
    {"fecha": "10/07", "ruta": "Salta → Rosario",          "tarifa": 580000},
    {"fecha": "01/07", "ruta": "Stgo. Estero → S.Lorenzo", "tarifa": 340000},
    {"fecha": "20/06", "ruta": "Córdoba → Buenos Aires",   "tarifa": 410000},
    {"fecha": "08/06", "ruta": "Rosario → Tucumán",        "tarifa": 370000},
]

CALIFICACIONES = [
    {"estrellas": 5, "texto": "Excelente servicio, muy puntual y serio.",    "autor": "Fertil del Norte S.A."},
    {"estrellas": 4, "texto": "Buena comunicación durante el viaje.",        "autor": "AgroSur S.A."},
    {"estrellas": 5, "texto": "Sin novedades, carga entregada perfecta.",   "autor": "Cooperativa Pampa"},
]

PENDIENTES_CALIFICACION = [
    {
        "viaje": "#5003",
        "ruta": "Salta → Rosario",
        "carga": "Trigo · 15 tn",
        "dador": "AgroSur S.A.",
        "fecha": "Entregado 16/07 · 09:18",
        "estado_cobro": "Pendiente",
    },
    {
        "viaje": "#5001",
        "ruta": "Tucumán → Rosario",
        "carga": "Soja · 15 tn",
        "dador": "Fertil del Norte S.A.",
        "fecha": "Entregado 15/07 · 17:40",
        "estado_cobro": "Quick-Pay",
    },
]

_AHORA = datetime.now()
QUICKPAY_PROVEEDORES = [
    {"nombre": "Meridiano", "tasa": 0.067, "etiqueta": "6,7%"},
    {"nombre": "Pymecred", "tasa": 0.083, "etiqueta": "8,3%"},
]

QUICKPAY_PENDIENTES = [
    {"ruta": "Salta → Rosario",           "tarifa": 580000, "adelanto": 377000, "fee": 31700, "neto": 345300, "adelantado": False, "fecha_entrega": _AHORA - timedelta(hours=36)},
    {"ruta": "Tucumán → Córdoba",         "tarifa": 320000, "adelanto": 208000, "fee": 17500, "neto": 190500, "adelantado": False, "fecha_entrega": _AHORA - timedelta(hours=20)},
    {"ruta": "Stgo. Estero → S.Lorenzo",  "tarifa": 340000, "adelanto": 0,      "fee": 0,     "neto": 214200, "adelantado": True,  "fecha_entrega": _AHORA - timedelta(hours=50)},
]


def _fmt_fecha_entrega(dt: datetime) -> str:
    horas = int((datetime.now() - dt).total_seconds() // 3600)
    if horas < 1:
        return "Entregado hace menos de 1 hora"
    if horas < 24:
        return f"Entregado hace {horas} hs"
    dias = horas // 24
    hs = horas % 24
    return f"Entregado hace {dias}d {hs}h" if hs else f"Entregado hace {dias}d"


def _qp_vigente(p: dict) -> bool:
    return p["adelantado"] or (datetime.now() - p["fecha_entrega"]).total_seconds() < 48 * 3600

OFERTAS_TRANSPORTISTA = [
    {
        "ruta": "Tucumán → Córdoba",
        "carga": "Soja · 15 tn",
        "fecha": "Carga 18/07 · 08:00 a 11:00",
        "estado": "Activa",
    },
    {
        "ruta": "Salta → San Lorenzo",
        "carga": "Fertilizante · 28 tn",
        "fecha": "Carga 20/07 · 14:00 a 18:00",
        "estado": "Con interesados",
    },
]

PROPUESTA_ACTUAL = {
    "id": "#5004",
    "origen": "Córdoba",
    "destino": "Rosario",
    "carga": "Soja",
    "toneladas": 28,
    "distancia": 420,
    "tarifa_base": 210000,
    "ajuste_dlp": -8,
    "tarifa_final": 193200,
    "adelantable_pct": 65,
    "adelantable_monto": 125580,
    "score_dador": 4.6,
    "empresa_dador": "AgroSur S.A.",
    "ventana_carga": "18/07 08:00–12:00",
}

INCIDENTES = [
    {"id": "INC-041", "tipo": "B", "viaje": "#4821", "trans": "Carlos G.",  "estado": "Abierto",  "fecha": "15/07", "desc": "Dador modificó tarifa al llegar al punto de carga. Tarifa pactada $420.000, ofrecida $370.000."},
    {"id": "INC-038", "tipo": "A", "viaje": "#4817", "trans": "Roberto M.", "estado": "Resuelto", "fecha": "08/07", "desc": "Demora mecánica. Camión reanudó viaje sin cambios de condiciones."},
    {"id": "INC-031", "tipo": "C", "viaje": "#4810", "trans": "Héctor V.",  "estado": "Resuelto", "fecha": "22/06", "desc": "Robo parcial de carga. Compendio documental generado. Siniestro en resolución."},
]

DADOR_EMPRESA = {
    "razon_social": "Fertil del Norte S.A.",
    "cuit": "30-71234567-8",
    "domicilio": "Av. Circunvalación 2480, San Miguel de Tucumán",
    "email": "operaciones@fertildelnorte.com.ar",
    "telefono": "+54 9 381 555 4400",
    "responsable": "Lucía Fernández",
    "cbu": "2850590940090418135201",
    "plazo_pago": "55 días desde conformidad de entrega",
    "cumplimiento": "92% de pagos en término en los últimos 90 días",
}

DADOR_CARGAS_EN_VIAJE = [
    {
        "id": "#4821",
        "transportista": "Carlos González",
        "cuit_transportista": "20-28473921-4",
        "score": 74,
        "patente": "AE 548 QL",
        "camion": "Semirremolque",
        "origen": "Tucumán",
        "destino": "Rosario",
        "mercaderia": "Soja",
        "peso": "15 tn",
        "distancia": 820,
        "tarifa": 420000,
        "referencia": "FADEEAC + Dynamic Lane Pricing -2%",
        "cpd": "CPD-009821",
        "ctg": "CTG-5531842",
        "eta": "16:40 hs",
        "gps": "Ruta 34 km 487",
        "incidente_activo": True,
        "alerta": "Desvío de 18 km · demora +45 min",
        "congelado": True,
        "incidente": {
            "tipo": "Desvío y reclamo de tarifa",
            "estado": "En gestión con AgroVIA",
            "compendio": "CPD/CTG, traza GPS y 3 fotos ya adjuntadas",
        },
        "milestones": [
            {"title": "Inicio de carga", "timestamp": "15/07 08:46", "geo": "Tucumán · 26.8241,-65.2226", "detail": "Foto CPD firmada validada", "status": "done", "adjuntos": ["Foto CPD firmada", "Geo origen validada"]},
            {"title": "Salida en tránsito", "timestamp": "15/07 09:12", "geo": "Ruta 34 km 1200", "detail": "Seguimiento GPS activo cada 5 min", "status": "done", "adjuntos": ["Snapshot GPS"]},
            {"title": "Llegada a destino", "timestamp": "Estimado 15/07 16:40", "geo": "Terminal 6, Rosario", "detail": "Demora significativa por desvío reportado", "status": "active"},
            {"title": "Descarga", "timestamp": "Pendiente", "geo": "Rosario", "detail": "Se habilita al validar arribo y remito", "status": "pending"},
        ],
    },
    {
        "id": "#4824",
        "transportista": "Roberto Mena",
        "cuit_transportista": "20-30987441-6",
        "score": 82,
        "patente": "AB 334 TR",
        "camion": "Camión simple",
        "origen": "Santiago del Estero",
        "destino": "San Lorenzo",
        "mercaderia": "Maíz",
        "peso": "15 tn",
        "distancia": 680,
        "tarifa": 340000,
        "referencia": "FADEEAC + Dynamic Lane Pricing +1%",
        "cpd": "CPD-010144",
        "ctg": "CTG-5531991",
        "eta": "19:15 hs",
        "gps": "RP 1 km 233",
        "incidente_activo": False,
        "alerta": None,
        "congelado": False,
        "incidente": None,
        "milestones": [
            {"title": "Inicio de carga", "timestamp": "15/07 11:05", "geo": "La Banda", "detail": "Foto CPD firmada OK", "status": "done", "adjuntos": ["Foto CPD firmada", "Checklist unidad"]},
            {"title": "Salida en tránsito", "timestamp": "15/07 11:28", "geo": "RN 34", "detail": "Velocidad y GPS dentro de rango", "status": "active"},
            {"title": "Llegada a destino", "timestamp": "Estimado 15/07 19:15", "geo": "San Lorenzo", "detail": "Sin alertas de desvío", "status": "pending"},
            {"title": "Descarga", "timestamp": "Pendiente", "geo": "San Lorenzo", "detail": "A la espera de remito y ticket", "status": "pending"},
        ],
    },
]

DADOR_CARGAS_PUBLICADAS = [
    {
        "id": "#4901",
        "estado": "Publicado",
        "mercaderia": "Cebada",
        "peso": "28 tn",
        "origen": "Bahía Blanca",
        "destino": "Rosario",
        "tarifa": 560000,
        "ventana_carga": "18/07 · 07:00 a 10:00",
        "ventana_descarga": "19/07 · 06:00 a 09:00",
        "forma_pago": "Transferencia bancaria",
        "plazo_pago_dias": "45 días",
        "observaciones": "Acceso por portería norte. Confirmar contacto operativo 2 hs antes de la carga.",
        "matches": [
            {"nombre": "Carlos González", "cuit": "20-28473921-4", "compat": 92, "score": 74, "camion": "Semirremolque", "patente": "AE 548 QL", "rto": "Sí", "seguro": "Sí", "satelital": "Sí", "rating": "4,8", "viajes": 28, "distancia_origen": "42 km"},
            {"nombre": "Héctor Vera", "cuit": "20-24455119-7", "compat": 86, "score": 69, "camion": "Acoplado", "patente": "AC 120 LK", "rto": "Sí", "seguro": "Sí", "satelital": "No", "rating": "4,5", "viajes": 17, "distancia_origen": "63 km"},
        ],
    },
    {
        "id": "#4902",
        "estado": "Aceptado",
        "mercaderia": "Fertilizante",
        "peso": "15 tn",
        "origen": "Rosario",
        "destino": "Salta",
        "tarifa": 590000,
        "ventana_carga": "20/07 · 14:00 a 18:00",
        "ventana_descarga": "21/07 · 08:00 a 12:00",
        "forma_pago": "eCheq",
        "plazo_pago_dias": "30 días",
        "observaciones": "Carga palletizada. Requiere validación de remito firmado para cursar el pago.",
        "matches": [
            {"nombre": "Roberto Mena", "cuit": "20-30987441-6", "compat": 95, "score": 82, "camion": "Camión simple", "patente": "AB 334 TR", "rto": "Sí", "seguro": "Sí", "satelital": "Sí", "rating": "4,9", "viajes": 41, "distancia_origen": "18 km"},
        ],
    },
    {
        "id": "#4903",
        "estado": "Pendiente de inicio",
        "mercaderia": "Soja",
        "peso": "30 tn",
        "origen": "Rafaela",
        "destino": "Puerto General San Martín",
        "tarifa": 320000,
        "ventana_carga": "22/07 · 06:00 a 09:00",
        "ventana_descarga": "22/07 · 12:00 a 16:00",
        "forma_pago": "Transferencia bancaria",
        "plazo_pago_dias": "15 días",
        "observaciones": "Turno confirmado. Presentarse con chofer y unidad preasignada en ventana de carga.",
        "matches": [
            {"nombre": "Marcos Soria", "cuit": "20-27123456-9", "compat": 94, "score": 79, "camion": "Semirremolque", "patente": "AF 881 TR", "rto": "Sí", "seguro": "Sí", "satelital": "Sí", "rating": "4,7", "viajes": 33, "distancia_origen": "21 km"},
        ],
    },
]

DADOR_PENDIENTES_CALIFICAR = [
    {
        "id": "#4817",
        "ruta": "Santiago del Estero → San Lorenzo",
        "transportista": "Roberto Mena",
        "estado": "Entregado",
        "fecha": "08/07",
        "rating_recibido": "Esperando tu cierre",
        "hitos_adjuntos": [
            {"hito": "Inicio de carga", "adjuntos": ["Foto CPD firmada", "Geo origen validada"]},
            {"hito": "En tránsito", "adjuntos": ["Trazabilidad GPS (snapshot)"]},
            {"hito": "Descarga y cierre", "adjuntos": ["Foto remito", "Ticket de balanza"]},
        ],
    },
    {
        "id": "#4814",
        "ruta": "Tucumán → Rosario",
        "transportista": "Carlos González",
        "estado": "Entregado",
        "fecha": "04/07",
        "rating_recibido": "Esperando tu cierre",
        "hitos_adjuntos": [
            {"hito": "Inicio de carga", "adjuntos": ["Foto CPD firmada"]},
            {"hito": "Llegada destino", "adjuntos": ["Geo destino validada"]},
            {"hito": "Descarga y cierre", "adjuntos": ["Foto remito"]},
        ],
    },
]

DADOR_PENDIENTES_GESTION = [
    {"id": "DIS-114", "tipo": "Modificación de condiciones", "detalle": "Transportista solicita modificar horario de carga", "vence": "Vence en 14 hs", "accion": "Chatear con AgroVIA"},
    {"id": "INC-041", "tipo": "Incidente con coordinación", "detalle": "Desvío de ruta + demora significativa en viaje #4821", "vence": "Responder antes de 24 hs", "accion": "Chatear con AgroVIA"},
]

DADOR_HISTORIAL_VIAJES = [
    {
        "id": "#4817",
        "fecha": "08/07",
        "ruta": "Santiago del Estero → San Lorenzo",
        "mercaderia": "Maíz",
        "estado": "Cerrado",
        "tarifa": 340000,
        "transportista": "Roberto Mena",
        "cuit_transportista": "20-30987441-6",
        "camion": "Camión simple",
        "patente": "AB 334 TR",
        "canal_pago": "Pago tradicional",
        "modalidad_pago": "Transferencia bancaria",
        "fecha_pago": "22/07 · 14:35",
        "estado_pago": "Pagado",
        "detalle_pago": "Liquidado contra remito conformado y ticket de balanza",
        "calif_dada": "4/5",
        "calif_recibida": "5/5",
        "docs": ["CPD firmada", "Remito de descarga", "Ticket de balanza"],
        "milestones": [
            {"title": "Inicio de carga", "timestamp": "08/07 07:40", "geo": "La Banda · 27.733,-64.240", "detail": "CPD firmada cargada", "status": "done"},
            {"title": "Salida", "timestamp": "08/07 08:05", "geo": "RN 34 km 685", "detail": "GPS validado", "status": "done"},
            {"title": "Llegada", "timestamp": "08/07 17:11", "geo": "San Lorenzo · 32.744,-60.736", "detail": "Arribo sin incidentes", "status": "done"},
            {"title": "Descarga y cierre", "timestamp": "08/07 18:02", "geo": "Planta ACA", "detail": "Remito y ticket adjuntos", "status": "done"},
        ],
    },
    {
        "id": "#4816",
        "fecha": "01/07",
        "ruta": "Tucumán → Rosario",
        "mercaderia": "Soja",
        "estado": "Cerrado",
        "tarifa": 450000,
        "transportista": "Carlos González",
        "cuit_transportista": "20-28473921-4",
        "camion": "Semirremolque",
        "patente": "AE 548 QL",
        "canal_pago": "QuickPay",
        "modalidad_pago": "eCheq a 30 días",
        "fecha_pago": "31/07 · 09:10",
        "estado_pago": "Pagado",
        "detalle_pago": "Acreditado según condición comercial pactada al cierre documental",
        "calif_dada": "5/5",
        "calif_recibida": "4/5",
        "docs": ["CPD firmada", "Remito de descarga"],
        "milestones": [
            {"title": "Inicio de carga", "timestamp": "01/07 06:55", "geo": "Tucumán", "detail": "Checklist operativo OK", "status": "done"},
            {"title": "Salida", "timestamp": "01/07 07:20", "geo": "RN 9", "detail": "Sin novedades", "status": "done"},
            {"title": "Llegada", "timestamp": "01/07 16:48", "geo": "Rosario", "detail": "Puntualidad dentro de SLA", "status": "done"},
            {"title": "Descarga y cierre", "timestamp": "01/07 17:35", "geo": "Terminal 6", "detail": "Cierre documental completo", "status": "done"},
        ],
    },
]


def _pesos(value: int) -> str:
    return "$" + f"{value:,}".replace(",", ".")


def _qp_restante(p: dict) -> list:
    """Retorna elementos UI del tiempo restante para solicitar QuickPay."""
    deadline = p["fecha_entrega"] + timedelta(hours=48)
    restante = deadline - datetime.now()
    segundos = int(restante.total_seconds())
    if segundos <= 0:
        return [
            html.Div(
                "⏱️ Plazo vencido · no podés solicitar el adelanto",
                style={"color": "#e05252", "fontSize": "12px", "marginTop": "8px", "marginBottom": "6px"},
            ),
        ]
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    if horas >= 24:
        dias = horas // 24
        hs = horas % 24
        label = f"{dias}d {hs}h {minutos}min"
        color = "#4caf50"
    elif horas >= 6:
        label = f"{horas}h {minutos}min"
        color = "#c8a84b"
    else:
        label = f"{horas}h {minutos}min"
        color = "#e07d52"
    return [
        html.Div(
            f"⏳ Tiempo para solicitar: {label}",
            style={"color": color, "fontSize": "12px", "marginTop": "8px", "marginBottom": "6px", "fontWeight": "600"},
        ),
        html.Button("⚡ Solicitar adelanto", className="btn-quickpay"),
    ]


def _qp_tarifas_rows(adelanto: int, class_name: str = "dlp-row") -> list:
    rows = []
    for proveedor in QUICKPAY_PROVEEDORES:
        fee = int(round(adelanto * proveedor["tasa"]))
        neto = adelanto - fee
        rows.append(
            html.Div(
                [
                    html.Span(f"{proveedor['nombre']} ({proveedor['etiqueta']})"),
                    html.Span(f"Fee {_pesos(fee)} · Neto {_pesos(neto)}"),
                ],
                className=class_name,
            )
        )
    return rows


def _btn(children, action: str, **kwargs) -> html.Button:
    """Crea un botón con patrón de ID uniforme para callbacks dinámicos."""
    return html.Button(children, id={"type": "action-btn", "action": action}, **kwargs)


def _role_btn(title: str, subtitle: str, icon: str, action: str) -> html.Button:
    return html.Button(
        id={"type": "action-btn", "action": action},
        className="role-btn",
        children=[
            html.Div(icon, className="role-icon"),
            html.Div([
                html.Div(title, className="role-text-title"),
                html.Div(subtitle, className="role-text-sub"),
            ]),
        ],
    )


def role_selector_layout() -> html.Div:
    return html.Div(
        className="selector-page",
        children=[
            html.Div(
                className="selector-inner",
                children=[
                    html.Div(
                        className="selector-header",
                        children=[
                            html.Img(src=app.get_asset_url("logo.jpg"), className="brand-logo", alt="Logo"),
                            html.P("Conectamos cargas. Adelantamos cobros.", className="tagline"),
                        ],
                    ),
                    html.Div(
                        className="selector-btns",
                        children=[
                            _role_btn("Soy Transportista",  "Buscá cargas, viajá y cobrá más rápido", "🚛", "role:transportista"),
                            _role_btn("Soy Dador de Carga", "Publicá cargas y seguí tus envíos",      "📦", "role:dador"),
                        ],
                    ),
                ],
            )
        ],
    )


def dador_content(tab: str) -> html.Div:  # noqa: C901
    legacy_map = {
        "dashboard": "cargas_en_viaje",
        "trazabilidad": "cargas_en_viaje:#4821",
        "incidentes": "pendientes",
        "publicar": "publicadas:nueva",
        "calificar": "pendientes",
    }
    tab = legacy_map.get(tab, tab)
    base_tab, _, item_id = tab.partition(":")

    if base_tab == "cargas_en_viaje" and item_id:
        viaje = next((item for item in DADOR_CARGAS_EN_VIAJE if item["id"] == item_id), DADOR_CARGAS_EN_VIAJE[0])
        return html.Div([
            _btn("← Volver a cargas en viaje", "dador:cargas_en_viaje", className="action-link", style={"display": "inline-block", "marginBottom": "16px"}),
            html.H2(f"Carga en viaje {viaje['id']}", className="section-title"),
            html.Div(className="two-col-3-2", children=[
                dmc.Paper([
                    html.Div(html.Div("Mapa en tiempo real", className="panel-title"), className="panel-header"),
                    dcc.Graph(
                        figure=create_dador_trip_map_figure(viaje["origen"], viaje["destino"], viaje["eta"], viaje["alerta"]),
                        config={"displayModeBar": False, "responsive": True},
                        style={"height": "320px", "padding": "12px"},
                    ),
                    html.Div([
                        html.Span(f"Última posición GPS: {viaje['gps']}", className="traz-val"),
                        html.Span(viaje["alerta"] if viaje["alerta"] else "Sin desvíos ni demoras significativas", className="traz-val", style={"color": "#b91c1c" if viaje["alerta"] else "#1f3d22", "fontWeight": "700"}),
                    ], style={"padding": "0 20px 18px", "display": "flex", "justifyContent": "space-between", "gap": "12px"}),
                ], className="panel"),
                html.Div([
                    dmc.Paper([
                        html.Div(html.Div("Datos del viaje", className="panel-title"), className="panel-header"),
                        html.Div([
                            html.Div(className="traz-info-row", children=[html.Span("Mercadería", className="traz-key"), html.Span(viaje["mercaderia"] + " · " + viaje["peso"], className="traz-val")]),
                            html.Div(className="traz-info-row", children=[html.Span("Ruta", className="traz-key"), html.Span(viaje["origen"] + " → " + viaje["destino"], className="traz-val")]),
                            html.Div(className="traz-info-row", children=[html.Span("Distancia", className="traz-key"), html.Span(f"{viaje['distancia']} km", className="traz-val")]),
                            html.Div(className="traz-info-row", children=[html.Span("Tarifa acordada", className="traz-key"), html.Span(_pesos(viaje["tarifa"]), className="traz-val")]),
                            html.Div(className="traz-info-row", children=[html.Span("Base", className="traz-key"), html.Span(viaje["referencia"], className="traz-val")]),
                            html.Div(className="traz-info-row", children=[html.Span("CPD / CTG", className="traz-key"), html.Span(f"{viaje['cpd']} · {viaje['ctg']}", className="traz-val")]),
                        ], style={"padding": "0 20px 6px"}),
                    ], className="panel"),
                    dmc.Paper([
                        html.Div(html.Div("Transportista asignado", className="panel-title"), className="panel-header"),
                        html.Div([
                            html.Div(className="traz-info-row", children=[html.Span("Nombre", className="traz-key"), html.Span(viaje["transportista"], className="traz-val")]),
                            html.Div(className="traz-info-row", children=[html.Span("CUIT", className="traz-key"), html.Span(viaje["cuit_transportista"], className="traz-val")]),
                            html.Div(className="traz-info-row", children=[html.Span("Score AgroVIA", className="traz-key"), html.Span(str(viaje["score"]), className="traz-val")]),
                            html.Div(className="traz-info-row", children=[html.Span("Patente", className="traz-key"), html.Span(viaje["patente"], className="traz-val")]),
                            html.Div(className="traz-info-row", children=[html.Span("Tipo de camión", className="traz-key"), html.Span(viaje["camion"], className="traz-val")]),
                        ], style={"padding": "0 20px 6px"}),
                    ], className="panel"),
                ]),
            ]),
            dmc.Paper([
                html.Div(html.Div("Hitos registrados", className="panel-title"), className="panel-header"),
                html.Div(className="d-timeline", children=build_dador_timeline_steps(viaje["milestones"]), style={"padding": "16px 20px 6px"}),
            ], className="panel"),
            dmc.Paper([
                html.Div(html.Div("Adjuntos de hitos realizados", className="panel-title"), className="panel-header"),
                html.Div(build_dador_completed_attachments(viaje["milestones"]), className="dador-chip-row", style={"padding": "0 20px 16px"}),
            ], className="panel"),
            *([
                dmc.Paper([
                    html.Div(html.Div("Incidente activo", className="panel-title"), className="panel-header"),
                    html.Div([
                        html.Div(className="traz-info-row", children=[html.Span("Tipo", className="traz-key"), html.Span(viaje["incidente"]["tipo"], className="traz-val")]),
                        html.Div(className="traz-info-row", children=[html.Span("Estado", className="traz-key"), html.Span(viaje["incidente"]["estado"], className="traz-val")]),
                        html.Div(className="traz-info-row", children=[html.Span("Compendio", className="traz-key"), html.Span(viaje["incidente"]["compendio"], className="traz-val")]),
                        html.Div("Viaje congelado hasta resolución operativa", className="traz-val", style={"marginTop": "8px", "color": "#b91c1c", "fontWeight": "700"}),
                    ], style={"padding": "0 20px 12px"}),
                ], className="panel"),
            ] if viaje["incidente_activo"] else []),
            html.Div([
                html.Button("Chatear con el transportista", className="btn-pub"),
                html.Button("Chatear con AgroVIA", className="btn-report"),
            ], className="action-row"),
        ])

    if base_tab == "cargas_en_viaje":
        return html.Div([
            html.H2("Cargas en viaje", className="section-title"),
            dmc.Paper([
                html.Div(className="dador-rich-list", children=[render_dador_active_trip_card(viaje) for viaje in DADOR_CARGAS_EN_VIAJE]),
            ], className="panel"),
        ])

    if base_tab == "viajes_disponibles":
        return html.Div([
            html.H2("Viajes disponibles", className="section-title"),
            dmc.Paper([
                html.Div(html.Div("Ofertas de transportistas", className="panel-title"), className="panel-header"),
                html.Div(
                    className="dador-rich-list",
                    children=[
                        html.Div([
                            html.Div(oferta["ruta"], className="dador-rich-route"),
                            html.Div(oferta["carga"], className="dador-rich-sub", style={"marginTop": "6px"}),
                            html.Div(oferta["fecha"], className="dador-rich-sub", style={"marginTop": "6px"}),
                            html.Div(html.Span(oferta["estado"], className="dador-chip"), className="dador-chip-row"),
                        ], className="dador-rich-card")
                        for oferta in OFERTAS_TRANSPORTISTA
                        if oferta["estado"] in {"Activa", "Con interesados"}
                    ] or [html.Div("No hay viajes disponibles en este momento.", className="traz-val")],
                ),
            ], className="panel"),
        ])

    if base_tab == "publicadas" and item_id == "nueva":
        return html.Div([
            _btn("← Volver a cargas publicadas", "dador:publicadas", className="action-link", style={"display": "inline-block", "marginBottom": "16px"}),
            html.H2("Publicar nueva carga", className="section-title"),
            html.Div(className="two-col", children=[
                dmc.Paper([
                    html.Div("Paso 1 · Mercadería y peso", className="form-section-title"),
                    html.Div([html.Label("Tipo de mercadería", className="form-label"), html.Select(className="form-select", children=[html.Option("Seleccionar…", value=""), *[html.Option(m) for m in ["Arena", "Arroz", "Cebada", "Fertilizante", "Girasol", "Harina", "Maíz", "Sorgo", "Soja", "Trigo"]]])], className="form-group"),
                    html.Div([html.Label("Peso estimado", className="form-label"), dcc.Input(type="number", placeholder="28", className="form-input")], className="form-group"),
                ], className="panel", style={"padding": "20px"}),
                dmc.Paper([
                    html.Div("Paso 2 · Ruta y ventanas", className="form-section-title"),
                    html.Div([html.Label("Origen", className="form-label"), dcc.Input(type="text", placeholder="Bahía Blanca", className="form-input")], className="form-group"),
                    html.Div([html.Label("Destino", className="form-label"), dcc.Input(type="text", placeholder="Rosario", className="form-input")], className="form-group"),
                    html.Div([html.Label("Ventana de carga", className="form-label"), dcc.Input(type="text", placeholder="18/07 · 07:00 a 10:00", className="form-input")], className="form-group"),
                    html.Div([html.Label("Ventana de descarga", className="form-label"), dcc.Input(type="text", placeholder="19/07 · 06:00 a 09:00", className="form-input")], className="form-group"),
                    html.Div("Paso 3 · Pago y observaciones", className="form-section-title", style={"marginTop": "18px"}),
                    html.Div([html.Label("Cómo se piensa pagar", className="form-label"), html.Select(className="form-select", children=[html.Option("Seleccionar…", value=""), *[html.Option(m) for m in ["Transferencia bancaria", "eCheq", "Cheque físico", "Efectivo contra entrega", "Otro"]]])], className="form-group"),
                    html.Div([html.Label("Plazo de pago en días", className="form-label"), dcc.Input(type="number", placeholder="55", className="form-input")], className="form-group"),
                    html.Div([html.Label("Observaciones", className="form-label"), html.Textarea(placeholder="Ej.: pago contra remito conformado, requisitos de acceso a planta, contacto operativo, condiciones especiales de carga o descarga.", className="form-input", style={"minHeight": "110px", "resize": "vertical", "paddingTop": "12px"})], className="form-group"),
                    html.Div("Paso 4 · Selección de parámetros de matching manual", className="form-section-title", style={"marginTop": "18px"}),
                    html.Div([
                        html.Span("Parámetros manuales", className="form-label"),
                        dmc.Switch(
                            id="matching-manual-toggle",
                            checked=False,
                            size="lg",
                        ),
                    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "10px"}),
                    html.Div([
                        html.Div("Ajustá el peso de cada criterio. Ocupación del vehículo tiene un mínimo obligatorio de 25%.", className="match-preview", style={"marginBottom": "8px"}),
                        html.Div([
                            html.Label("Eficiencia de ruta", className="form-label"),
                            dcc.Slider(id="matching-eficiencia", min=0, max=75, step=25, value=25, marks={0: "0%", 25: "25%", 50: "50%", 75: "75%"}, included=False, className="hide-slider-values"),
                        ], className="form-group"),
                        html.Div([
                            html.Label("Ocupación del vehículo (mínimo 25%)", className="form-label"),
                            dcc.Slider(id="matching-ocupacion", min=25, max=100, step=25, value=25, marks={25: "25%", 50: "50%", 75: "75%", 100: "100%"}, included=False, className="hide-slider-values"),
                        ], className="form-group"),
                        html.Div([
                            html.Label("Reputación del transportista", className="form-label"),
                            dcc.Slider(id="matching-reputacion", min=0, max=75, step=25, value=50, marks={0: "0%", 25: "25%", 50: "50%", 75: "75%"}, included=False, className="hide-slider-values"),
                        ], className="form-group"),
                        html.Div(id="matching-total-display", className="match-preview", style={"fontWeight": "700", "marginTop": "6px"}),
                        html.Div(id="matching-total-alert", className="viaje-card-sub", style={"marginTop": "4px", "marginBottom": "8px"}),
                    ], id="matching-manual-panel", style={"display": "none", "marginBottom": "6px"}),
                    html.Div("Wizard guiado: AgroVIA te sugerirá transportistas por score de compatibilidad", className="match-preview"),
                    html.Button("Publicar nueva carga", id="publish-new-load-button", className="btn-pub", disabled=False),
                ], className="panel", style={"padding": "20px"}),
            ]),
        ])

    if base_tab == "publicadas" and item_id:
        carga = next((item for item in DADOR_CARGAS_PUBLICADAS if item["id"] == item_id), DADOR_CARGAS_PUBLICADAS[0])
        return html.Div([
            _btn("← Volver a cargas publicadas", "dador:publicadas", className="action-link", style={"display": "inline-block", "marginBottom": "16px"}),
            html.H2(f"Carga publicada {carga['id']}", className="section-title"),
            dmc.Paper([
                html.Div(html.Div("Detalle de la carga", className="panel-title"), className="panel-header"),
                html.Div([
                    html.Div(className="traz-info-row", children=[html.Span("Mercadería", className="traz-key"), html.Span(carga["mercaderia"] + " · " + carga["peso"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Ruta", className="traz-key"), html.Span(carga["origen"] + " → " + carga["destino"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Ventana carga", className="traz-key"), html.Span(carga["ventana_carga"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Ventana descarga", className="traz-key"), html.Span(carga["ventana_descarga"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Cómo se paga", className="traz-key"), html.Span(carga["forma_pago"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Plazo de pago", className="traz-key"), html.Span(carga["plazo_pago_dias"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Observaciones", className="traz-key"), html.Span(carga["observaciones"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Estado", className="traz-key"), html.Span(carga["estado"], className="traz-val")]),
                ], style={"padding": "0 20px 12px"}),
            ], className="panel"),
            dmc.Paper([
                html.Div(html.Div("Transportistas propuestos por matching", className="panel-title"), className="panel-header"),
                html.Div(className="dador-rich-list", children=[
                    render_dador_match_card(
                        carga["id"],
                        match,
                        waiting_response=carga["estado"] in {"Aceptado", "Pendiente de inicio"},
                        waiting_label="Viaje pendiente de inicio" if carga["estado"] == "Pendiente de inicio" else "Esperando respuesta del transportista",
                    )
                    for match in sorted(carga["matches"], key=lambda item: item["compat"], reverse=True)
                ]),
            ], className="panel"),
        ])

    if base_tab == "publicadas":
        return html.Div([
            html.Div([
                html.H2("Cargas publicadas", className="section-title"),
                _btn("＋ Publicar nueva carga", "dador:publicadas:nueva", className="btn-pub"),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "16px"}),
            dmc.Paper([
                html.Div(className="dador-rich-list", children=[render_dador_published_load_card(carga) for carga in DADOR_CARGAS_PUBLICADAS]),
            ], className="panel"),
        ])

    if base_tab == "pendientes":
        return html.Div([
            html.H2("Pendientes", className="section-title"),
            dmc.Paper([
                html.Div(html.Div("Calificar", className="panel-title"), className="panel-header"),
                html.Div([
                    dmc.Paper([
                        html.Div(item["id"] + " · " + item["ruta"], className="form-section-title"),
                        html.Div("Transportista: " + item["transportista"], className="traz-val", style={"marginBottom": "10px"}),
                        html.Div("Adjuntos por hito", className="cal-question-d", style={"marginBottom": "6px"}),
                        html.Div([
                            html.Div([
                                html.Div(hito["hito"], className="traz-key", style={"fontWeight": "700"}),
                                html.Div([
                                    html.Div([
                                        html.Span("📎 " + adj, className="traz-val"),
                                        html.Button("Ver adjunto", className="btn-report", style={"padding": "4px 10px", "fontSize": "11px"}),
                                    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginTop": "4px"})
                                    for adj in hito.get("adjuntos", [])
                                ]),
                            ], style={"padding": "8px 10px", "border": "1px solid rgba(200,168,75,0.25)", "borderRadius": "10px", "marginBottom": "8px", "background": "rgba(18,35,21,0.03)"})
                            for hito in item.get("hitos_adjuntos", [])
                        ], style={"marginBottom": "12px"}),
                        html.Div([
                            html.Div("Cumplimiento operativo", className="cal-question-d"),
                            html.Div([html.Button("★" if idx <= 5 else "☆", className="star-btn-d active" if idx <= 5 else "star-btn-d") for idx in range(1, 6)], className="star-row-d"),
                            html.Div("Comunicación y transparencia", className="cal-question-d", style={"marginTop": "10px"}),
                            html.Div([html.Button("★" if idx <= 4 else "☆", className="star-btn-d active" if idx <= 4 else "star-btn-d") for idx in range(1, 6)], className="star-row-d"),
                            html.Div("Estado del vehículo / condiciones de carga", className="cal-question-d", style={"marginTop": "10px"}),
                            html.Div([html.Button("★" if idx <= 5 else "☆", className="star-btn-d active" if idx <= 5 else "star-btn-d") for idx in range(1, 6)], className="star-row-d"),
                        ]),
                        html.Button("Cerrar viaje con rating", className="btn-pub", style={"marginTop": "12px"}),
                    ], className="panel", style={"padding": "16px", "marginBottom": "12px"})
                    for item in DADOR_PENDIENTES_CALIFICAR
                ], style={"padding": "16px"}),
            ], className="panel"),
            dmc.Paper([
                html.Div(html.Div("Responder", className="panel-title"), className="panel-header"),
                html.Div([
                    dmc.Paper([
                        html.Div(item["id"] + " · " + item["tipo"], className="form-section-title"),
                        html.Div(item["detalle"], className="traz-val"),
                        html.Div(item["vence"], className="traz-val", style={"marginTop": "8px", "color": "#b91c1c", "fontWeight": "700"}),
                        html.Div([
                            html.Button(item["accion"], className="btn-report"),
                            html.Button("Chatear con transportista", className="btn-report"),
                        ], className="action-row", style={"marginTop": "12px"}),
                    ], className="panel", style={"padding": "16px", "marginBottom": "12px"})
                    for item in DADOR_PENDIENTES_GESTION
                ], style={"padding": "16px"}),
            ], className="panel"),
        ])

    if base_tab == "chats":
        conversaciones = [
            {
                "titulo": "Transportista · Carlos Gonzalez",
                "detalle": "Viaje #4821 · Consulta sobre ventana de descarga",
                "estado": "Nuevo mensaje hace 12 min",
            },
            {
                "titulo": "AgroVIA Soporte Operativo",
                "detalle": "INC-041 · Seguimiento de incidente con coordinacion",
                "estado": "Pendiente de respuesta",
            },
            {
                "titulo": "Transportista · Marta Rojas",
                "detalle": "Viaje #4798 · Confirmacion de documentacion cargada",
                "estado": "Ultima actividad: hoy 09:42",
            },
        ]
        return html.Div([
            html.H2("Chats", className="section-title"),
            dmc.Paper([
                html.Div(className="panel-header", children=[html.Div("Conversaciones activas", className="panel-title")]),
                html.Div([
                    dmc.Paper([
                        html.Div(chat["titulo"], className="form-section-title"),
                        html.Div(chat["detalle"], className="traz-val", style={"marginTop": "4px"}),
                        html.Div(chat["estado"], className="traz-val", style={"marginTop": "8px", "color": "#1f3d22", "fontWeight": "700"}),
                        html.Div([
                            html.Button("Abrir chat", className="btn-report"),
                        ], className="action-row", style={"marginTop": "10px"}),
                    ], className="panel", style={"padding": "16px", "marginBottom": "12px"})
                    for chat in conversaciones
                ], style={"padding": "16px"}),
            ], className="panel"),
        ])

    if base_tab == "historial" and item_id:
        viaje = next((item for item in DADOR_HISTORIAL_VIAJES if item["id"] == item_id), DADOR_HISTORIAL_VIAJES[0])
        return html.Div([
            _btn("← Volver al historial", "dador:historial", className="action-link", style={"display": "inline-block", "marginBottom": "16px"}),
            html.H2("Historial de viaje " + viaje["id"], className="section-title"),
            dmc.Paper([
                html.Div(html.Div("Resumen operativo y pago", className="panel-title"), className="panel-header"),
                html.Div([
                    html.Div(className="traz-info-row", children=[html.Span("Ruta", className="traz-key"), html.Span(viaje["ruta"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Mercadería", className="traz-key"), html.Span(viaje["mercaderia"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Tarifa", className="traz-key"), html.Span(_pesos(viaje["tarifa"]), className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Estado del pago", className="traz-key"), html.Span(viaje["estado_pago"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Canal de pago", className="traz-key"), html.Span(viaje["canal_pago"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Cómo se pagó", className="traz-key"), html.Span(viaje["modalidad_pago"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Cuándo se pagó", className="traz-key"), html.Span(viaje["fecha_pago"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Detalle liquidación", className="traz-key"), html.Span(viaje["detalle_pago"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Transportista", className="traz-key"), html.Span(viaje["transportista"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("CUIT", className="traz-key"), html.Span(viaje["cuit_transportista"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Vehículo", className="traz-key"), html.Span(viaje["camion"] + " · " + viaje["patente"], className="traz-val")]),
                ], style={"padding": "0 20px 12px"}),
            ], className="panel"),
            dmc.Paper([
                html.Div(html.Div("Resumen de hitos", className="panel-title"), className="panel-header"),
                html.Div(className="d-timeline", children=build_dador_timeline_steps(viaje["milestones"]), style={"padding": "16px 20px 6px"}),
            ], className="panel"),
            dmc.Paper([
                html.Div(html.Div("Calificaciones", className="panel-title"), className="panel-header"),
                html.Div([
                    html.Div(className="traz-info-row", children=[html.Span("Calificación que diste", className="traz-key"), html.Span(viaje["calif_dada"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Calificación recibida", className="traz-key"), html.Span(viaje["calif_recibida"], className="traz-val")]),
                ], style={"padding": "0 20px 12px"}),
            ], className="panel"),
            dmc.Paper([
                html.Div(html.Div("Documentos descargables", className="panel-title"), className="panel-header"),
                html.Div([
                    html.Button(doc, className="action-link", style={"display": "inline-block", "marginRight": "10px", "marginBottom": "10px"})
                    for doc in viaje["docs"]
                ], style={"padding": "0 20px 18px"}),
            ], className="panel"),
        ])

    if base_tab == "historial":
        return html.Div([
            html.H2("Historial de viajes", className="section-title"),
            dmc.Paper([
                html.Div([
                    dcc.Input(type="text", placeholder="Filtrar por fecha", className="form-input", style={"maxWidth": "180px"}),
                    dcc.Input(type="text", placeholder="Origen / destino", className="form-input", style={"maxWidth": "220px"}),
                    dcc.Dropdown(options=["Arena", "Arroz", "Cebada", "Fertilizante", "Girasol", "Harina", "Maíz", "Sorgo", "Soja", "Trigo"], placeholder="Mercadería", className="form-select", style={"minWidth": "220px"}),
                ], style={"display": "flex", "gap": "12px", "padding": "16px 20px"}),
                html.Div(className="dador-rich-list", style={"padding": "0 20px 20px"}, children=[render_dador_history_card(viaje) for viaje in DADOR_HISTORIAL_VIAJES]),
            ], className="panel"),
        ])

    if base_tab == "perfil":
        reputacion = [
            ("Puntualidad en entrega de carga", "4,7"),
            ("Claridad en instrucciones", "4,5"),
            ("Condiciones del punto de carga", "4,4"),
            ("Respeto de condiciones pactadas", "4,6"),
        ]
        viajes_colaborados = 35
        km_ahorrados_dador = int(round(viajes_colaborados * 122))
        co2_evitado_dador_tn = km_ahorrados_dador * 0.35 * 2.68 / 1000
        viajes_colaborados_txt = f"(con {viajes_colaborados} viajes colaborados)"
        return html.Div([
            html.H2("Perfil", className="section-title"),
            dmc.Paper([
                html.Div(html.Div("Datos de la empresa", className="panel-title"), className="panel-header"),
                html.Div([
                    html.Div(className="traz-info-row", children=[html.Span("Razón social", className="traz-key"), html.Span(DADOR_EMPRESA["razon_social"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("CUIT", className="traz-key"), html.Span(DADOR_EMPRESA["cuit"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Domicilio fiscal", className="traz-key"), html.Span(DADOR_EMPRESA["domicilio"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Email", className="traz-key"), html.Span(DADOR_EMPRESA["email"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Teléfono", className="traz-key"), html.Span(DADOR_EMPRESA["telefono"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Responsable operativo", className="traz-key"), html.Span(DADOR_EMPRESA["responsable"], className="traz-val")]),
                ], style={"padding": "0 20px 12px"}),
            ], className="panel"),
            dmc.Paper([
                html.Div(html.Div("Métodos de pago y condiciones", className="panel-title"), className="panel-header"),
                html.Div([
                    html.Div(className="traz-info-row", children=[html.Span("CBU / CVU", className="traz-key"), html.Span(DADOR_EMPRESA["cbu"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Plazo habitual", className="traz-key"), html.Span(DADOR_EMPRESA["plazo_pago"], className="traz-val")]),
                    html.Div(className="traz-info-row", children=[html.Span("Cumplimiento", className="traz-key"), html.Span(DADOR_EMPRESA["cumplimiento"], className="traz-val")]),
                ], style={"padding": "0 20px 12px"}),
            ], className="panel"),
            dmc.Paper([
                html.Div(html.Div("Reputación como dador", className="panel-title"), className="panel-header"),
                html.Div([
                    html.Div(className="traz-info-row", children=[html.Span(label, className="traz-key"), html.Span(score, className="traz-val")])
                    for label, score in reputacion
                ] + [html.Div("Sin reincidencias graves activas. AgroVIA registra 1 advertencia histórica por demora documental resuelta.", className="traz-val", style={"marginTop": "10px"})], style={"padding": "0 20px 12px"}),
            ], className="panel"),
            dmc.Paper([
                html.Div(html.Div("Impacto de tu operación", className="panel-title"), className="panel-header"),
                html.Div([
                    html.Div([
                        html.Div(f"{km_ahorrados_dador:,}".replace(",", "."), className="dador-impact-value"),
                        html.Div("km de retorno vacío ahorrados", className="dador-impact-label"),
                        html.Div(viajes_colaborados_txt, className="dador-impact-note"),
                    ], className="dador-impact-card"),
                    html.Div([
                        html.Div(f"{co2_evitado_dador_tn:.1f} tn".replace(".", ","), className="dador-impact-value"),
                        html.Div("CO2 evitado", className="dador-impact-label"),
                        html.Div(viajes_colaborados_txt, className="dador-impact-note"),
                    ], className="dador-impact-card"),
                ], className="dador-impact-grid", style={"padding": "0 20px 18px"}),
            ], className="panel"),
            html.Div([
                _btn("Términos y condiciones", "terms:open", className="btn-ghost-light"),
                html.Button("Chatear con AgroVIA", className="btn-report"),
            ], className="action-row"),
        ])

    return dador_content("cargas_en_viaje")


def dador_layout(tab: str) -> html.Div:
    active_tab = tab.split(":", 1)[0]
    nav = [
        ("cargas_en_viaje", "🟢", "Cargas en viaje"),
        ("viajes_disponibles", "🚛", "Viajes disponibles"),
        ("publicadas",      "🟡", "Cargas publicadas"),
        ("pendientes",      "🔴", "Pendientes"),
        ("chats",           "💬", "Chats"),
        ("historial",       "📋", "Historial"),
        ("perfil",          "👤", "Perfil"),
    ]
    return html.Div(
        className="dador-shell",
        children=[
            html.Aside(
                className="dador-sidebar",
                children=[
                    html.Div(html.Img(src=app.get_asset_url("logo.jpg"), className="sidebar-brand-logo", alt="Logo"), className="sidebar-brand-wrap"),
                    html.Div([
                        html.Div("Empresa",             className="sidebar-company-label"),
                        html.Div("Fertil del Norte S.A.", className="sidebar-company"),
                    ], className="sidebar-company-wrap"),
                    html.Div(
                        className="sidebar-nav",
                        children=[
                            _btn(
                                [html.Span(ico, className="sidebar-icon"), html.Span(lbl)],
                                f"dador:{key}",
                                className="sidebar-btn active" if active_tab == key else "sidebar-btn",
                            )
                            for key, ico, lbl in nav
                        ],
                    ),
                ],
            ),
            html.Main(className="dador-main", children=[dador_content(tab)]),
        ],
    )


def _score_bar(score: int) -> html.Div:
    """4 segmentos coloreados según el score."""
    thresholds = [25, 50, 75, 100]
    segs = []
    for th in thresholds:
        lo = th - 25
        if score >= th:
            pct, color = "100%", "green"
        elif score > lo:
            pct = f"{((score - lo) / 25) * 100:.0f}%"
            color = "green" if th >= 75 else "gold"
        else:
            pct, color = "0%", "green"
        segs.append(html.Div(html.Div(className=f"score-bar-fill {color}", style={"width": pct}),
                             className="score-bar-seg"))
    return html.Div(segs, className="score-bars")


FLOW_META = {
    "disponible": {"label": "Disponible", "desc": "Listo para aceptar"},
    "en_espera": {"label": "En espera", "desc": "Pendiente del dador"},
    "proximo": {"label": "Próximo", "desc": "Asignado y próximo a iniciar"},
    "en_curso": {"label": "En curso", "desc": "Viaje activo"},
    "oferta_publicada": {"label": "Oferta publicada", "desc": "Oferta creada por vos"},
}

DOCS_FLOW = {
    "disponible": {
        "ok": ["Licencia C/E vigente", "Seguro RC vigente", "RTO vigente"],
        "req": [
            "Tramitar ART vigente antes de iniciar viaje asignado.",
            "Cargar foto CPD firmada al inicio de carga.",
            "Cargar foto de remito al cierre.",
        ],
    },
    "en_espera": {
        "ok": ["Datos fiscales validados", "Documentos base vigentes"],
        "req": [
            "Si el dador confirma, verificar vigencia documental al iniciar.",
            "Cargar foto CPD al marcar inicio de carga.",
            "Cargar foto de remito/ticket al cierre.",
        ],
    },
    "proximo": {
        "ok": ["Viaje confirmado por dador", "Ventanas de carga/descarga definidas"],
        "req": [
            "Regularizar documento vencido para habilitar inicio.",
            "Foto CPD obligatoria en hito de inicio.",
            "Foto remito obligatoria en descarga y cierre.",
        ],
    },
    "en_curso": {
        "ok": ["CPD registrada", "Tracking GPS activo"],
        "req": [
            "Validar GPS en destino para confirmar arribo.",
            "Subir foto de remito al cierre.",
            "Adjuntar ticket de balanza cuando corresponda.",
        ],
    },
    "oferta_publicada": {
        "ok": ["Oferta publicada", "Vehículo asignado a la oferta"],
        "req": [
            "Mantener documentación vigente para recibir asignación.",
            "Cuando se asigne, cargar foto CPD en inicio.",
            "Cargar foto de remito al finalizar viaje.",
        ],
    },
}

INCIDENTE_CATEGORIAS = {
    "desvio_ruta": {
        "titulo": "Desvío de ruta",
        "grupo": "Desvíos operativos",
        "desc": "Cambio de camino o destino",
        "opciones": [
            {"id": "ruta_clima", "label": "Por condiciones climáticas", "sub": "Lluvia, niebla, nieve o viento"},
            {"id": "ruta_corte", "label": "Ruta cortada o accidentada", "sub": "Accidente, obras o cierre vial"},
            {"id": "ruta_seguridad", "label": "Por razones de seguridad", "sub": "Zona de riesgo o piquete"},
            {"id": "ruta_nueva", "label": "Nuevo destino indicado por dador", "sub": "Cambio en instrucciones"},
            {"id": "ruta_error", "label": "Error de ruta tomada", "sub": "GPS incorrecto u otro"},
        ],
    },
    "demora": {
        "titulo": "Demora",
        "grupo": "Desvíos operativos",
        "desc": "Atraso en carga, ruta o destino",
        "opciones": [
            {"id": "dem_espera_carga", "label": "Espera en punto de carga", "sub": "Más de 12 hs en época de cosecha"},
            {"id": "dem_playa", "label": "Espera en playa de precalado", "sub": "Cola para calado"},
            {"id": "dem_ruta", "label": "Demora en ruta", "sub": "Tráfico, controles o clima"},
            {"id": "dem_mecanico", "label": "Demora por falla mecánica", "sub": ""},
            {"id": "dem_doc", "label": "Demora por documentación", "sub": "CTG vencido o remito rechazado"},
            {"id": "dem_descarga", "label": "Demora en descarga / terminal", "sub": ""},
        ],
    },
    "carga": {
        "titulo": "Problema en carga",
        "grupo": "Desvíos operativos",
        "desc": "Fosfina, rechazo o condiciones",
        "opciones": [
            {"id": "carga_fosfina", "label": "Detección de fosfina", "sub": "Gas tóxico en el cereal"},
            {"id": "carga_rechazo", "label": "Rechazo de carga en calado", "sub": "Humedad, plagas u otro"},
            {"id": "carga_condicion", "label": "Condiciones del cereal no conformes", "sub": ""},
            {"id": "carga_peso", "label": "Discrepancia de peso declarado", "sub": ""},
            {"id": "carga_derrame", "label": "Derrame o pérdida de carga", "sub": "En ruta o en maniobras"},
            {"id": "carga_otro", "label": "Otro problema con la mercadería", "sub": ""},
        ],
    },
    "dador": {
        "titulo": "Dador incumple",
        "grupo": "Desvíos operativos",
        "desc": "Cambio unilateral de condiciones",
        "opciones": [
            {"id": "dad_destino", "label": "Cambio de destino unilateral", "sub": ""},
            {"id": "dad_mercaderia", "label": "Tipo de mercadería diferente", "sub": "No coincide con el remito"},
            {"id": "dad_tarifa", "label": "Pretende modificar la tarifa", "sub": ""},
            {"id": "dad_condiciones", "label": "Condiciones del punto de carga", "sub": "Acceso, infraestructura o tiempos"},
            {"id": "dad_doc", "label": "Documentación incompleta o incorrecta", "sub": ""},
            {"id": "dad_trato", "label": "Trato inadecuado", "sub": ""},
        ],
    },
    "mecanico": {
        "titulo": "Problema mecánico",
        "grupo": "Incidentes de seguridad",
        "desc": "Falla del vehículo",
        "opciones": [
            {"id": "mec_neumatico", "label": "Pinchazo o reventón de neumático", "sub": ""},
            {"id": "mec_frenos", "label": "Falla en sistema de frenos", "sub": ""},
            {"id": "mec_motor", "label": "Falla de motor", "sub": ""},
            {"id": "mec_electrico", "label": "Falla eléctrica", "sub": "Luces, tablero o sistema"},
            {"id": "mec_enganche", "label": "Problema en enganche / acoplado", "sub": ""},
            {"id": "mec_hidraulico", "label": "Falla sistema hidráulico", "sub": "Tolva o batea"},
            {"id": "mec_otro", "label": "Otra falla mecánica", "sub": ""},
        ],
    },
    "accidente": {
        "titulo": "Accidente vial",
        "grupo": "Incidentes de seguridad",
        "desc": "Choque, vuelco u otro",
        "opciones": [
            {"id": "acc_choque", "label": "Choque con otro vehículo", "sub": ""},
            {"id": "acc_vuelco", "label": "Vuelco de la unidad", "sub": ""},
            {"id": "acc_atropello", "label": "Atropellamiento", "sub": ""},
            {"id": "acc_caida", "label": "Caída del conductor", "sub": "Al subir o bajar de la unidad"},
            {"id": "acc_incendio", "label": "Incendio del vehículo", "sub": ""},
        ],
    },
    "robo": {
        "titulo": "Robo o asalto",
        "grupo": "Incidentes de seguridad",
        "desc": "Carga o unidad",
        "opciones": [
            {"id": "rob_carga", "label": "Robo de carga total o parcial", "sub": ""},
            {"id": "rob_unidad", "label": "Robo de la unidad", "sub": ""},
            {"id": "rob_intento", "label": "Intento de robo", "sub": ""},
            {"id": "rob_asalto", "label": "Asalto al conductor", "sub": "Con o sin violencia"},
        ],
    },
    "salud": {
        "titulo": "Emergencia médica",
        "grupo": "Incidentes de seguridad",
        "desc": "Conductor u otra persona",
        "opciones": [
            {"id": "sal_intox", "label": "Intoxicación (fosfina u otro)", "sub": "Mareos, náuseas o dificultad para respirar"},
            {"id": "sal_fatiga", "label": "Fatiga extrema", "sub": "No puede continuar"},
            {"id": "sal_accidente", "label": "Lesión por accidente laboral", "sub": "Caída, golpe o atrapamiento"},
            {"id": "sal_tercero", "label": "Emergencia de un tercero", "sub": "Persona en ruta u otra"},
        ],
    },
    "doc": {
        "titulo": "Problema documental",
        "grupo": "Documentación",
        "desc": "CTG, remito o documentos",
        "opciones": [
            {"id": "doc_ctg", "label": "CTG vencido o inválido", "sub": ""},
            {"id": "doc_remito", "label": "Remito rechazado en destino", "sub": ""},
            {"id": "doc_falta", "label": "Documentación faltante", "sub": "SENASA o carta de porte"},
            {"id": "doc_control", "label": "Retención en control de ruta", "sub": "Gendarmería, AFIP o SENASA"},
        ],
    },
    "otro": {
        "titulo": "Otro",
        "grupo": "Documentación",
        "desc": "Evento no listado",
        "opciones": [
            {"id": "otro_clima", "label": "Fenómeno climático extremo", "sub": "Granizo, inundación o tornado"},
            {"id": "otro_protesta", "label": "Corte de ruta o protesta", "sub": ""},
            {"id": "otro_animal", "label": "Colisión con animal", "sub": ""},
            {"id": "otro_libre", "label": "Otro evento no listado", "sub": ""},
        ],
    },
}

INCIDENTE_URGENCIAS = {
    "informativo": "Informativo",
    "demora": "Demora",
    "critico": "Crítico",
    "emergencia": "Emergencia",
}

INCIDENTE_OPCION_A_CATEGORIA = {
    opt["id"]: cat
    for cat, cfg in INCIDENTE_CATEGORIAS.items()
    for opt in cfg["opciones"]
}


def inferir_urgencia_incidente(categoria: str, opcion_id: str) -> str:
    if opcion_id in {"carga_fosfina", "sal_intox"} or categoria in {"robo", "accidente"}:
        return "emergencia"
    if categoria in {"salud", "mecanico"}:
        return "critico"
    if categoria in {"demora", "dador"}:
        return "demora"
    return "informativo"


def alerta_pre_envio_incidente(categoria: str, opcion_id: str) -> str:
    if opcion_id in {"carga_fosfina", "sal_intox"}:
        return "Riesgo de intoxicación. Al enviar se notificará al equipo de emergencias de AgroVIA."
    if categoria in {"robo", "accidente"}:
        return "Se generará automáticamente el compendio documental del viaje para tu aseguradora."
    if categoria == "dador":
        return "Se abrirá una disputa formal. AgroVIA notificará al dador con 24 hs para responder."
    return ""


def matriz_legal_incidente(categoria: str, opcion_id: str) -> dict[str, str]:
    por_opcion = {
        "rob_carga": {
            "titulo": "Robo total o parcial de la carga",
            "principal": "Transportista (si tiene seguro de carga) y su aseguradora.",
            "secundario": "Dador de carga si contrató seguro de carga propio.",
            "agrovia": "Facilita documentación: GPS, estados y fotos. No es parte del reclamo.",
        },
        "rob_unidad": {
            "titulo": "Robo de la unidad",
            "principal": "Transportista y su aseguradora de automotor.",
            "secundario": "No aplica salvo cobertura adicional del dador.",
            "agrovia": "Aporta trazabilidad del viaje y evidencia operativa.",
        },
        "rob_intento": {
            "titulo": "Intento de robo",
            "principal": "Transportista (denuncia y activación de protocolo de seguridad).",
            "secundario": "No aplica en forma automática.",
            "agrovia": "Registra evento de riesgo y respalda con geolocalización/hitos.",
        },
        "rob_asalto": {
            "titulo": "Asalto al conductor",
            "principal": "Transportista (seguro personal/ART/RC según evento).",
            "secundario": "Aseguradora según póliza y cobertura contratada.",
            "agrovia": "Aporta evidencia operativa; no define responsabilidad legal.",
        },
        "acc_choque": {
            "titulo": "Accidente de tránsito (choque con terceros)",
            "principal": "Transportista. Cubierto por seguro de RC automotor obligatorio.",
            "secundario": "No aplica a AgroVIA.",
            "agrovia": "No es parte del reclamo. Entrega trazabilidad como respaldo.",
        },
        "acc_vuelco": {
            "titulo": "Vuelco de la unidad",
            "principal": "Transportista y su cobertura de automotor / carga según póliza.",
            "secundario": "Aseguradora de carga si corresponde por contrato.",
            "agrovia": "Provee historial de viaje y documentación de hitos.",
        },
        "carga_rechazo": {
            "titulo": "Daños o rechazo de mercadería",
            "principal": "Transportista. Evaluación según contrato de transporte.",
            "secundario": "Aseguradora según condiciones de póliza.",
            "agrovia": "Provee eventos y documentos de carga/descarga como evidencia.",
        },
        "dad_destino": {
            "titulo": "Incumplimiento del dador: cambio unilateral de destino",
            "principal": "Dador de carga. Aplican penalidades del contrato registrado.",
            "secundario": "No aplica.",
            "agrovia": "Registra condiciones originales y deja constancia para disputa.",
        },
        "dad_tarifa": {
            "titulo": "Incumplimiento del dador: modificación de tarifa",
            "principal": "Dador de carga por alteración unilateral de condiciones.",
            "secundario": "No aplica.",
            "agrovia": "Usa evidencia contractual para resolución de disputa.",
        },
        "otro_libre": {
            "titulo": "Fallo del sistema / pérdida de datos",
            "principal": "AgroVIA.",
            "secundario": "No aplica.",
            "agrovia": "Activa recuperación desde respaldos y continuidad operativa.",
        },
    }

    if opcion_id in por_opcion:
        return por_opcion[opcion_id]

    if categoria == "robo":
        return {
            "titulo": "Robo / asalto en viaje",
            "principal": "Transportista y su aseguradora según cobertura contratada.",
            "secundario": "Dador si posee póliza propia sobre la carga.",
            "agrovia": "Facilita trazabilidad y documentación del evento.",
        }
    if categoria == "accidente":
        return {
            "titulo": "Accidente de tránsito",
            "principal": "Transportista (responsabilidad civil y seguro obligatorio).",
            "secundario": "No aplica.",
            "agrovia": "Aporta evidencia operativa, no participa como parte legal.",
        }
    if categoria == "carga":
        return {
            "titulo": "Incidente sobre la mercadería",
            "principal": "Transportista según contrato de transporte.",
            "secundario": "Aseguradora según póliza y peritaje.",
            "agrovia": "Aporta historial de eventos y documentos.",
        }
    if categoria == "dador":
        return {
            "titulo": "Incumplimiento del dador",
            "principal": "Dador de carga según términos pactados.",
            "secundario": "No aplica.",
            "agrovia": "Registra evidencia y canaliza la disputa.",
        }

    return {
        "titulo": "Gestión legal del incidente / desvío",
        "principal": "Se determina por contrato y evidencia del viaje.",
        "secundario": "Puede intervenir aseguradora o contraparte según el caso.",
        "agrovia": "Aporta trazabilidad documental y registro de eventos.",
    }


def flow_actions_for(viaje: dict) -> tuple[dict, dict]:
    tipo = viaje.get("tipo_flujo", "disponible")
    vid = viaje["id"].replace("#", "")
    if tipo == "disponible":
        return (
            {"label": "Aceptar viaje", "action": f"flow:primary:{vid}"},
            {"label": "Ver detalle", "action": f"viaje:{vid}"},
        )
    if tipo == "en_espera":
        return (
            {"label": "Cancelar propuesta", "action": f"flow:primary:{vid}"},
            {"label": "Ver detalle", "action": f"viaje:{vid}"},
        )
    if tipo == "proximo":
        return (
            {"label": "Iniciar viaje", "action": f"flow:primary:{vid}"},
            {"label": "Ver detalle", "action": f"viaje:{vid}"},
        )
    if tipo == "en_curso":
        return (
            {"label": "Ver seguimiento", "action": f"viaje:{vid}"},
            {"label": "Ver detalle", "action": f"viaje:{vid}"},
        )
    return (
        {"label": "Editar oferta", "action": f"flow:primary:{vid}"},
        {"label": "Eliminar oferta", "action": f"flow:secondary:{vid}"},
    )


def transportista_tab_content(tab: str, viaje_id: str | None, hito_actual: int, scoring_data: dict | None = None, checklist_data: dict | None = None, incidente_data: dict | None = None) -> html.Div:  # noqa: C901
    if tab == "propuesta":
        tab = "viajes"

    scoring_data = scoring_data or {}
    score_final = int(round(float(scoring_data.get("score_final", 74))))
    score_financiero = int(round(float(scoring_data.get("score_qp", score_final))))
    tier = str(scoring_data.get("tier", "B"))
    quickpay_pct = int(round(float(scoring_data.get("quickpay_pct", 65))))
    quickpay_habilitado = bool(scoring_data.get("quickpay_habilitado", True))

    subscores = scoring_data.get("subscores", {}) if isinstance(scoring_data, dict) else {}
    sub_historial   = int(round(float(subscores.get("historial",   80))))
    sub_vehiculo    = int(round(float(subscores.get("vehiculo",    85))))
    sub_recencia    = int(round(float(subscores.get("recencia",    90))))
    sub_calificacion = int(round(float(subscores.get("calificacion", 76))))

    pipeline = scoring_data.get("pipeline", {}) if isinstance(scoring_data, dict) else {}
    caps_aplicados = list(pipeline.get("caps_aplicados", [])) if isinstance(pipeline, dict) else []
    trend_points_7d = int(round(float(scoring_data.get("trend_points_7d", 3))))
    trend_color = "#22c55e" if trend_points_7d >= 0 else "#ef4444"
    trend_sign = "+" if trend_points_7d >= 0 else ""

    def _quickpay_pct_from_score(score: int) -> int:
        """Tabla QP segun Score_QP (doc AgroVIA v2): 41-55=50, 56-70=60, 71-84=70, 85+=80."""
        if score >= 85: return 80
        if score >= 71: return 70
        if score >= 56: return 60
        if score >= 41: return 50
        return 0

    def _quickpay_estado_viaje(v: dict) -> tuple[bool, str, str]:
        """Evalua QuickPay por viaje: perfil, score y disponibilidad del dador."""
        score_min = int(v.get("score_min", 0))
        if not quickpay_habilitado:
            return False, "QuickPay restringido", "Tu perfil todavia no habilita QuickPay."
        if score_financiero < score_min:
            return False, f"Score minimo {score_min}", f"Tu score ({score_financiero}) no alcanza para este viaje."
        if not bool(v.get("quickpay_habilitado", False)):
            motivo = str(v.get("requisito_qp") or "El dador no habilito QuickPay para este viaje")
            return False, "QuickPay no disponible", motivo
        return True, "⚡ QuickPay habilitado", f"Te quedan {_pesos(v['neto_qp'])} si usas QuickPay"

    simulaciones = [
        {
            "titulo": "Mejorar puntualidad a >95%",
            "impacto": "+4 pts",
            "score": min(100, score_financiero + 4),
        },
        {
            "titulo": "Completar 3 viajes sin incidente",
            "impacto": "+3 pts",
            "score": min(100, score_financiero + 3),
        },
        {
            "titulo": "Actividad constante 90 días",
            "impacto": "+2 pts",
            "score": min(100, score_financiero + 2),
        },
    ]

    tier_map = {
        "A": "Nivel Destacado",
        "B": "Nivel Oro",
        "C": "Nivel Plata",
        "D": "En consolidación",
        "E": "Sin historial",
    }
    nivel_label = tier_map.get(tier, "Nivel Plata")
    objetivo_destacado = "Ya estás en nivel destacado" if score_financiero >= 85 else f"{85 - score_financiero} pts para Nivel Destacado"

    viajes_realizados = 27
    km_ahorrados = int(round(viajes_realizados * 120))
    co2_evitado_tn = km_ahorrados * 0.35 * 2.68 / 1000

    km_ahorrados_txt = f"{km_ahorrados:,}".replace(",", ".")
    co2_evitado_txt = f"{co2_evitado_tn:.1f}".replace(".", ",")
    viajes_realizados_txt = f"(con {viajes_realizados} viajes realizados)"

    # ── CALIFICAR al dador (detalle del viaje) ───────────────────────────
    if tab == "calificar":
        viaje_calificar = next((p for p in PENDIENTES_CALIFICACION if p["viaje"] == viaje_id), None)
        if not viaje_calificar and PENDIENTES_CALIFICACION:
            viaje_calificar = PENDIENTES_CALIFICACION[0]

        viaje_txt = viaje_calificar["viaje"] if viaje_calificar else "#----"
        ruta_txt = viaje_calificar["ruta"] if viaje_calificar else "Ruta no disponible"
        carga_txt = viaje_calificar["carga"] if viaje_calificar else "Carga no disponible"
        dador_txt = viaje_calificar["dador"] if viaje_calificar else "Dador no disponible"
        fecha_txt = viaje_calificar["fecha"] if viaje_calificar else "Sin fecha"
        estado_cobro_txt = viaje_calificar["estado_cobro"] if viaje_calificar else "Pendiente"

        viaje_detalle = next((v for v in VIAJES if v["id"] == viaje_txt), None)
        tarifa_txt = _pesos(viaje_detalle["tarifa"]) if viaje_detalle else "-"
        ventana_carga_txt = viaje_detalle["ventana_carga"] if viaje_detalle else "-"
        ventana_descarga_txt = viaje_detalle["ventana_descarga"] if viaje_detalle else "-"
        forma_pago_txt = viaje_detalle["instrumento"] if viaje_detalle else "-"
        plazo_pago_txt = viaje_detalle["plazo_pago"] if viaje_detalle else "-"

        return html.Div(className="phone-scroll", children=[
            _btn("← Volver", "tab:historial", className="btn-back"),
            html.Div("Calificá al dador", className="mobile-title", style={"marginBottom": "2px", "marginTop": "8px"}),
            html.Div(f"Viaje {viaje_txt} · {ruta_txt} · {carga_txt}", className="mobile-subtitle"),
            html.Div([
                html.Div(dador_txt, className="perfil-name"),
                html.Div(fecha_txt, className="perfil-cuit"),
            ], className="perfil-header", style={"marginTop": "16px"}),

            html.Div("Detalle del viaje", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "8px"}),
            html.Div([
                html.Div([html.Span("Tarifa"), html.Span(tarifa_txt, className="dlp-total")], className="dlp-row dlp-total-row"),
                html.Div([html.Span("Estado de cobro"), html.Span(estado_cobro_txt, className="gold" if estado_cobro_txt == "Quick-Pay" else "dlp-discount")], className="dlp-row"),
                html.Div([html.Span("Ventana de carga"), html.Span(ventana_carga_txt)], className="dlp-row"),
                html.Div([html.Span("Ventana de descarga"), html.Span(ventana_descarga_txt)], className="dlp-row"),
                html.Div([html.Span("Forma de pago"), html.Span(forma_pago_txt)], className="dlp-row"),
                html.Div([html.Span("Plazo de pago"), html.Span(plazo_pago_txt)], className="dlp-row"),
            ], className="dlp-card"),

            html.Div("Calificación del dador", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "4px"}),
            html.Div([
                html.Div("Condiciones del punto de carga", className="cal-question"),
                html.Div([
                    html.Button("★" if i <= 5 else "☆", className="star-btn" + (" active" if i <= 5 else ""))
                    for i in range(1, 6)
                ], className="star-row"),
            ], className="doc-card"),
            html.Div([
                html.Div("Puntualidad", className="cal-question"),
                html.Div([
                    html.Button("★" if i <= 5 else "☆", className="star-btn" + (" active" if i <= 5 else ""))
                    for i in range(1, 6)
                ], className="star-row"),
            ], className="doc-card", style={"marginTop": "10px"}),
            html.Div([
                html.Div("Respeto de condiciones pactadas", className="cal-question"),
                html.Div([
                    html.Button("★" if i <= 5 else "☆", className="star-btn" + (" active" if i <= 5 else ""))
                    for i in range(1, 6)
                ], className="star-row"),
            ], className="doc-card", style={"marginTop": "10px"}),

            html.Div("Confirmación de pago", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "14px"}),
            html.Div([
                dcc.RadioItems(
                    options=[
                        {"label": " Confirmo pago recibido", "value": "pago_recibido"},
                        {"label": " Aún pendiente de pago", "value": "pendiente"},
                    ],
                    value="pendiente" if estado_cobro_txt == "Pendiente" else "pago_recibido",
                    className="check-terms",
                    inputStyle={"marginRight": "8px"},
                    labelStyle={"display": "block", "marginBottom": "8px", "color": "rgba(239,230,209,0.9)", "fontSize": "13px"},
                )
            ], className="doc-card"),

            html.Div([
                html.Label("Comentario opcional", className="form-label"),
                html.Textarea(placeholder="¿Cómo fue la experiencia?", className="form-textarea"),
            ], className="form-group", style={"marginTop": "12px"}),
            _btn("Enviar calificación", "tab:inicio", className="btn-gold-full"),
        ])

    if tab == "publicar":
        return html.Div(className="phone-scroll", children=[
            html.Div("Publicar disponibilidad", className="mobile-title", style={"marginBottom": "14px"}),
            html.Div([
                html.Div([html.Label("Origen", className="form-label"), dcc.Input(type="text", placeholder="Ciudad y provincia", className="form-input")], className="form-group"),
                html.Div([html.Label("Destino", className="form-label"), dcc.Input(type="text", placeholder="Ciudad y provincia", className="form-input")], className="form-group"),
                html.Div([html.Label("Cargas admitidas", className="form-label"), dcc.Dropdown(
                    options=["Arena", "Arroz", "Cebada", "Fertilizante", "Girasol", "Harina", "Maíz", "Sorgo", "Soja", "Trigo", "Otro"],
                    multi=True,
                    placeholder="Seleccionar cargas...",
                    className="form-select",
                )], className="form-group"),
                html.Div([html.Label("Peso máximo (tn)", className="form-label"), dcc.Input(type="number", placeholder="15", className="form-input")], className="form-group"),
                html.Div([html.Label("Ventana horaria de carga", className="form-label"), dcc.Input(type="text", placeholder="18/07 · 08:00 a 11:00", className="form-input")], className="form-group"),
                html.Div([html.Label("Ventana horaria de descarga", className="form-label"), dcc.Input(type="text", placeholder="19/07 · 09:00 a 12:00", className="form-input")], className="form-group"),
                html.Div([html.Label("Observaciones", className="form-label"), html.Textarea(placeholder="Aclaraciones adicionales", className="form-textarea")], className="form-group"),
                html.Div([
                    html.Label("Vehículo", className="form-label"),
                    dcc.Dropdown(
                        options=[{"label": c["patente"], "value": c["patente"]} for c in CAMIONES_TRANSPORTISTA],
                        value=CAMIONES_TRANSPORTISTA[0]["patente"],
                        clearable=False,
                        className="form-select",
                    ),
                ], className="form-group"),
                html.Div([
                    dcc.Checklist(
                        options=[{"label": "Solo acepto pagos por eCheq", "value": "solo-echeq"}],
                        value=["solo-echeq"],
                        className="check-terms",
                        inputStyle={"marginRight": "8px"},
                        labelStyle={"color": "rgba(239,230,209,0.85)", "fontSize": "13px", "fontWeight": "500"},
                    ),
                ], className="form-group", style={"marginTop": "-4px"}),
                html.Button("Publicar oferta", className="btn-gold-full"),
            ], className="doc-card"),

            html.Div("Mis ofertas publicadas", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "18px"}),
            *[
                html.Div([
                    html.Div([
                        html.Div([html.Span(oferta["ruta"], className="viaje-card-route"), html.Span(oferta["estado"], className="badge-score")], className="viaje-card-top"),
                        html.Div(oferta["carga"], className="viaje-card-sub"),
                        html.Div(oferta["fecha"], className="viaje-card-sub", style={"marginTop": "6px"}),
                    ], style={"flex": "1"}),
                    html.Div([
                        html.Button("✏️", style={"background": "none", "border": "none", "fontSize": "18px", "cursor": "pointer", "padding": "4px", "width": "32px", "height": "32px"}),
                        html.Button("❌", style={"background": "none", "border": "2px solid #ef4444", "fontSize": "14px", "cursor": "pointer", "padding": "4px", "width": "32px", "height": "32px", "borderRadius": "4px", "color": "#ef4444"}),
                    ], style={"display": "flex", "flexDirection": "column", "gap": "8px", "justifyContent": "flex-start"}),
                ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "gap": "12px"}, className="viaje-card")
                for oferta in OFERTAS_TRANSPORTISTA
            ],
        ])

    # ── INICIO ─────────────────────────────────────────────────────────
    if tab == "inicio" and not viaje_id:
        return html.Div(className="phone-scroll", children=[
            html.Div([
                html.Div("Buen día, Carlos 👋", className="mobile-title"),
                html.Div([
                    html.Div("💬", className="mobile-notif", style={"cursor": "pointer"}),
                    html.Details([
                        html.Summary([
                            html.Div("🔔", className="mobile-notif"),
                            html.Div(str(len(NOTIFICACIONES_TRANSPORTISTA)), className="mobile-notif-badge"),
                        ], className="mobile-notif", style={"listStyle": "none", "cursor": "pointer"}),
                        html.Div([
                            html.Div("Notificaciones", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "10px"}),
                            *[
                                _btn([
                                    html.Div([
                                        html.Div(n["icono"], style={"fontSize": "18px", "lineHeight": "1"}),
                                        html.Div([
                                            html.Div(n["titulo"], style={"fontSize": "12px", "fontWeight": "700", "color": "#efe6d1", "marginBottom": "4px"}),
                                            html.Div(n["texto"], className="viaje-card-sub", style={"lineHeight": "1.45"}),
                                            html.Div(n["fecha"], style={"fontSize": "11px", "color": "rgba(239,230,209,0.42)", "marginTop": "6px"}),
                                        ], style={"flex": "1"}),
                                    ], style={"display": "flex", "gap": "12px", "alignItems": "flex-start"}),
                                ], n["accion"], className="viaje-card") if n["accion"]
                                else html.Div([
                                    html.Div([
                                        html.Div(n["icono"], style={"fontSize": "18px", "lineHeight": "1"}),
                                        html.Div([
                                            html.Div(n["titulo"], style={"fontSize": "12px", "fontWeight": "700", "color": "#efe6d1", "marginBottom": "4px"}),
                                            html.Div(n["texto"], className="viaje-card-sub", style={"lineHeight": "1.45"}),
                                            html.Div(n["fecha"], style={"fontSize": "11px", "color": "rgba(239,230,209,0.42)", "marginTop": "6px"}),
                                        ], style={"flex": "1"}),
                                    ], style={"display": "flex", "gap": "12px", "alignItems": "flex-start"}),
                                ], className="viaje-card")
                                for n in NOTIFICACIONES_TRANSPORTISTA
                            ],
                        ], className="notif-panel"),
                    ], className="notif-menu"),
                ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
            ], className="mobile-header"),

            html.Div([
                html.Div([
                    html.Span("Tu Score", className="score-card-label"),
                ], className="score-card-top"),
                dcc.Graph(
                    figure=create_score_gauge_figure(score_financiero),
                    config={"displayModeBar": False, "responsive": True},
                    style={"margin": "4px 0 0"},
                ),
                html.Div(objetivo_destacado, className="viaje-card-sub", style={"marginTop": "10px", "marginBottom": "6px"}),
                html.Div(
                    f"Tendencia 7 días: {trend_sign}{trend_points_7d} pts",
                    className="viaje-card-sub",
                    style={"color": trend_color, "fontWeight": "700", "marginBottom": "6px"},
                ),
                html.Div([
                    html.Span("Podés adelantar hasta el "),
                    html.Span(f"{quickpay_pct}%"),
                    html.Span(" de tu flete"),
                ], className="score-adelanto"),
                _btn("Ver detalle del Quick-Pay →", "quickpay:open", className="score-link"),
            ], className="score-card"),

            html.Div([
                html.Div([
                    html.Div(km_ahorrados_txt, className="impact-kpi-value"),
                    html.Div("km ahorrados", className="impact-kpi-label"),
                    html.Div(viajes_realizados_txt, className="impact-kpi-note"),
                ], className="impact-kpi-card"),
                html.Div([
                    html.Div(f"{co2_evitado_txt} tn", className="impact-kpi-value"),
                    html.Div("CO2 evitado", className="impact-kpi-label"),
                    html.Div(viajes_realizados_txt, className="impact-kpi-note"),
                ], className="impact-kpi-card"),
            ], className="impact-kpi-grid"),

            *([html.Div([
                html.Div("Regla de seguridad activa", className="mobile-section-title", style={"marginBottom": "8px"}),
                html.Div([
                    html.Div("⚠ Tu score está condicionado por reglas de riesgo/documentación.", className="score-bk-tip"),
                    html.Ul([
                        html.Li(cap, style={"marginBottom": "4px", "color": "rgba(239,230,209,0.88)"})
                        for cap in caps_aplicados
                    ], style={"paddingLeft": "18px", "margin": "8px 0 0"}),
                ], className="doc-card"),
            ])] if caps_aplicados else []),

            html.Div([
                html.Div([
                    html.Span("Próximos viajes", className="mobile-section-title"),
                ], className="mobile-section-row"),
                *[
                    _btn([
                        html.Div([
                            html.Span(f"{v['origen']} → {v['destino']}", className="viaje-card-route"),
                            html.Span(_pesos(v["tarifa"]), className="viaje-card-price"),
                        ], className="viaje-card-top"),
                        html.Div(f"{v['carga']} · {v['toneladas']} tn", className="viaje-card-sub"),
                        html.Div(f"Carga: {v['ventana']}", className="viaje-card-sub", style={"marginTop": "6px"}),
                        html.Div(v["quickpay"], className="viaje-card-sub", style={"marginTop": "6px", "color": "#c8a84b"}),
                    ],
                    f"proxviaje:{v['id'].replace('#', '')}",
                    className="viaje-card")
                    for v in PROXIMOS_VIAJES
                ],
            ]),

            html.Div([
                html.Div("En espera", className="mobile-section-title", style={"marginBottom": "8px"}),
                *[
                    html.Div([
                        html.Div([
                            html.Span(f"{v['origen']} → {v['destino']}", className="viaje-card-route"),
                            html.Span(_pesos(v["tarifa"]), className="viaje-card-price"),
                        ], className="viaje-card-top"),
                        html.Div(f"{v['carga']} · {v['toneladas']} tn", className="viaje-card-sub"),
                        html.Div(v["espera"], className="viaje-card-sub", style={"marginTop": "6px"}),
                        html.Div("En espera de confirmación del dador", className="viaje-card-sub", style={"marginTop": "6px", "color": "#c8a84b"}),
                    ], className="viaje-card")
                    for v in VIAJES_EN_ESPERA
                ],
            ]),

            html.Div("Viaje en curso", className="mobile-section-title", style={"marginTop": "18px", "marginBottom": "8px", "color": "#ff9500"}),
            html.Div([
                html.Button([
                    html.Div([
                        html.Div(f"{VIAJE_EN_CURSO['origen']} → {VIAJE_EN_CURSO['destino']}", style={"fontSize": "14px", "fontWeight": "700", "color": "#0b1b0d", "lineHeight": "1.3"}),
                        html.Div(VIAJE_EN_CURSO["eta"], style={"marginTop": "6px", "fontSize": "12px", "color": "rgba(11,27,13,0.7)"}),
                    ], style={"flex": "1", "textAlign": "left"}),
                    html.Div("Abrir", style={"fontWeight": "700", "fontSize": "13px", "color": "#0b1b0d"}),
                ], id={"type": "action-btn", "action": "tab:en_curso"}, n_clicks=0, className="en-curso-sticky-btn"),
            ], className="en-curso-sticky"),

        ])

    # ── VIAJES (lista) ─────────────────────────────────────────────────
    if tab == "viajes" and not viaje_id:
        disponibles_dador = [v for v in VIAJES if v.get("tipo_flujo") == "disponible"]
        en_espera_aceptacion = [v for v in VIAJES if v.get("tipo_flujo") == "en_espera"]
        return html.Div(className="phone-scroll", children=[
            html.Div("Cargas disponibles", className="mobile-title"),
            html.Div("Publicadas por dadores", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "10px"}),
            html.Div("Solo viajes para capturar ahora.", className="viaje-card-sub", style={"marginBottom": "8px"}),
            *[
                html.Div([
                    html.Div([
                        html.Span(f"{v['origen']} → {v['destino']}", className="viaje-card-route"),
                        html.Span(_pesos(v["tarifa"]), className="viaje-card-price"),
                    ], className="viaje-card-top"),
                    html.Div(f"{v['carga']} · {v['toneladas']} tn · {v['distancia']} km", className="viaje-card-sub"),
                    html.Div(f"Te pagan en {v['plazo_pago']} · {v['instrumento']}", className="viaje-card-sub", style={"marginTop": "6px"}),
                    html.Div([
                        html.Span(FLOW_META[v.get("tipo_flujo", "disponible")]["label"], className="badge-retorno"),
                        html.Span(FLOW_META[v.get("tipo_flujo", "disponible")]["desc"], className="viaje-card-sub"),
                    ], style={"display": "flex", "gap": "8px", "alignItems": "center", "marginTop": "8px"}),
                    html.Div(qp_msg, className="viaje-card-adelantable", style={"marginTop": "8px"}),
                    html.Div([
                        html.Span(
                            qp_badge,
                            className="badge-retorno" if qp_ok else "badge-no-retorno",
                        ),
                        html.Span(v["plazo_pago"], className="badge-score"),
                    ], className="viaje-card-footer"),
                    html.Div([
                        _btn(
                            flow_actions_for(v)[0]["label"],
                            flow_actions_for(v)[0]["action"],
                            className="btn-gold-action" if not (v.get("tipo_flujo") == "proximo" and not v.get("documentacion_ok")) else "btn-ghost",
                        ),
                        _btn(
                            flow_actions_for(v)[1]["label"],
                            flow_actions_for(v)[1]["action"],
                            className="btn-ghost",
                        ),
                    ], className="action-row", style={"marginTop": "10px"}),
                    *([
                        html.Div(
                            "No podés iniciar hasta actualizar documentación obligatoria.",
                            className="score-bk-tip",
                            style={"marginTop": "8px"},
                        )
                    ] if v.get("tipo_flujo") == "proximo" and not v.get("documentacion_ok") else []),
                ], className="viaje-card")
                for v in disponibles_dador
                for qp_ok, qp_badge, qp_msg in [_quickpay_estado_viaje(v)]
            ],
            html.Div("En espera de aceptación", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "14px"}),
            html.Div("Viajes donde todavía podés modificar o cancelar propuesta.", className="viaje-card-sub", style={"marginBottom": "8px"}),
            *[
                html.Div([
                    html.Div([
                        html.Span(f"{v['origen']} → {v['destino']}", className="viaje-card-route"),
                        html.Span(_pesos(v["tarifa"]), className="viaje-card-price"),
                    ], className="viaje-card-top"),
                    html.Div(f"{v['carga']} · {v['toneladas']} tn · {v['distancia']} km", className="viaje-card-sub"),
                    html.Div(f"Te pagan en {v['plazo_pago']} · {v['instrumento']}", className="viaje-card-sub", style={"marginTop": "6px"}),
                    html.Div([
                        html.Span(FLOW_META[v.get("tipo_flujo", "disponible")]["label"], className="badge-retorno"),
                        html.Span(FLOW_META[v.get("tipo_flujo", "disponible")]["desc"], className="viaje-card-sub"),
                    ], style={"display": "flex", "gap": "8px", "alignItems": "center", "marginTop": "8px"}),
                    html.Div(qp_msg, className="viaje-card-adelantable", style={"marginTop": "8px"}),
                    html.Div([
                        html.Span(
                            qp_badge,
                            className="badge-retorno" if qp_ok else "badge-no-retorno",
                        ),
                        html.Span(v["plazo_pago"], className="badge-score"),
                    ], className="viaje-card-footer"),
                    html.Div([
                        _btn(
                            flow_actions_for(v)[0]["label"],
                            flow_actions_for(v)[0]["action"],
                            className="btn-gold-action" if not (v.get("tipo_flujo") == "proximo" and not v.get("documentacion_ok")) else "btn-ghost",
                        ),
                        _btn(
                            flow_actions_for(v)[1]["label"],
                            flow_actions_for(v)[1]["action"],
                            className="btn-ghost",
                        ),
                    ], className="action-row", style={"marginTop": "10px"}),
                    *([
                        html.Div(
                            "No podés iniciar hasta actualizar documentación obligatoria.",
                            className="score-bk-tip",
                            style={"marginTop": "8px"},
                        )
                    ] if v.get("tipo_flujo") == "proximo" and not v.get("documentacion_ok") else []),
                ], className="viaje-card")
                for v in en_espera_aceptacion
                for qp_ok, qp_badge, qp_msg in [_quickpay_estado_viaje(v)]
            ],
        ])

    # ── INICIO (detalle de próximo viaje) ──────────────────────────────
    if tab == "inicio" and viaje_id:
        viaje = next((v for v in VIAJES if v["id"] == viaje_id), None)
        if viaje:
            return html.Div(className="phone-scroll", children=[
                _btn("\u2190 Volver al inicio", "tab:inicio", className="btn-back"),
                html.Div(f"Viaje {viaje['id']}", className="mobile-title", style={"marginBottom": "14px"}),
                dcc.Graph(
                    figure=create_route_map_figure(viaje["origen"], viaje["destino"], ""),
                    config={'displayModeBar': False, 'responsive': True},
                    style={"margin": "0 0 14px 0"},
                    className="route-map-svg",
                ),
                html.Div(className="viaje-info-card", children=[
                    html.Div(className="viaje-info-grid", children=[
                        html.Div([html.Div("Origen", className="viaje-info-key"), html.Div(viaje["direccion_origen"], className="viaje-info-val")]),
                        html.Div([html.Div("Destino", className="viaje-info-key"), html.Div(viaje["direccion_destino"], className="viaje-info-val")]),
                        html.Div([html.Div("Carga", className="viaje-info-key"), html.Div(f"{viaje['carga']} \u00b7 {viaje['toneladas']} tn", className="viaje-info-val")]),
                        html.Div([html.Div("Distancia", className="viaje-info-key"), html.Div(f"{viaje['distancia']} km", className="viaje-info-val")]),
                    ]),
                ]),
                html.Div("Condiciones del viaje", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "14px"}),
                html.Div([
                    html.Div([html.Span("Tarifa"), html.Span(_pesos(viaje["tarifa"]), className="dlp-total")], className="dlp-row dlp-total-row"),
                    html.Div([html.Span("Plazo de pago"), html.Span(viaje["plazo_pago"])], className="dlp-row"),
                    html.Div([html.Span("Instrumento"), html.Span(viaje["instrumento"])], className="dlp-row"),
                    html.Div([html.Span("Empresa dadora"), html.Span(viaje["empresa_dador"])], className="dlp-row"),
                    html.Div([html.Span("Ventana de carga"), html.Span(viaje["ventana_carga"])], className="dlp-row"),
                    html.Div([html.Span("Ventana de descarga"), html.Span(viaje["ventana_descarga"])], className="dlp-row"),
                ], className="dlp-card"),

                *[html.Div(
                    f"⏰ Inicia en {prox['dias_inicio']} día{'s' if prox['dias_inicio'] != 1 else ''}",
                    style={"textAlign": "center", "color": "#c8a84b", "fontWeight": "700", "fontSize": "15px", "margin": "18px 0 12px"},
                ) for prox in PROXIMOS_VIAJES if prox["id"] == viaje_id],

                html.Div([
                    _btn("💬 Chatear con dador",         "chat:dador",      className="btn-ghost", style={"width": "100%", "marginBottom": "10px"}),
                    _btn("✏️ Modificación de condiciones", "viaje:modificar", className="btn-ghost", style={"width": "100%", "marginBottom": "10px"}),
                    _btn("✖ Cancelar viaje",              "viaje:cancelar",  className="btn-danger", style={"width": "100%"}),
                ], style={"marginTop": "4px"}),
            ])

    # ── VIAJES (detalle) ───────────────────────────────────────────────
    if tab == "viajes" and viaje_id:
        viaje = next((v for v in VIAJES if v["id"] == viaje_id), VIAJES[0])
        tipo_flujo = viaje.get("tipo_flujo", "disponible")
        primary_action, secondary_action = flow_actions_for(viaje)
        primary_class = "btn-gold-action"
        docs_flow = DOCS_FLOW[tipo_flujo]
        mostrar_secundaria = not secondary_action["action"].startswith("viaje:")
        if tipo_flujo == "proximo" and not viaje["documentacion_ok"]:
            primary_class = "btn-ghost"
        return html.Div(className="phone-scroll", children=[
            _btn("← Atrás", "tab:viajes", className="btn-back"),
            html.Div(f"Viaje {viaje['id']}", className="mobile-title", style={"marginBottom": "14px"}),
            html.Div(FLOW_META[tipo_flujo]["label"], className="badge-retorno", style={"display": "inline-block", "marginBottom": "12px"}),

            dcc.Graph(
                figure=create_route_map_figure(viaje["origen"], viaje["destino"], ""),
                config={'displayModeBar': False, 'responsive': True},
                style={"margin": "0 0 14px 0"},
                className="route-map-svg",
            ),

            html.Div(className="viaje-info-card", children=[
                html.Div(className="viaje-info-grid", children=[
                    html.Div([html.Div("Origen", className="viaje-info-key"), html.Div(viaje["direccion_origen"], className="viaje-info-val")]),
                    html.Div([html.Div("Destino", className="viaje-info-key"), html.Div(viaje["direccion_destino"], className="viaje-info-val")]),
                    html.Div([html.Div("Carga", className="viaje-info-key"), html.Div(f"{viaje['carga']} · {viaje['toneladas']} tn", className="viaje-info-val")]),
                    html.Div([html.Div("Distancia", className="viaje-info-key"), html.Div(f"{viaje['distancia']} km", className="viaje-info-val")]),
                    html.Div([html.Div("Tarifa total", className="viaje-info-key"), html.Div(_pesos(viaje["tarifa"]), className="viaje-info-val gold")]),
                    html.Div([html.Div("Base de cálculo", className="viaje-info-key"), html.Div("Tarifa FADEEAC ajustada por Dynamic Lane Pricing", className="viaje-info-val")]),
                ]),
            ]),

            html.Div([
                html.Div("Datos del dador", className="mobile-section-title", style={"marginBottom": "8px"}),
                html.Div([
                    html.Div([html.Span("Razón social"), html.Span(viaje["empresa_dador"], className="gold")], className="dlp-row"),
                    html.Div([html.Span("CUIT"), html.Span(viaje["cuit"])], className="dlp-row"),
                    html.Div([html.Span("Calificación"), html.Span(f"★ {viaje['rating']}")], className="dlp-row"),
                    html.Div([html.Span("Viajes en AgroVIA"), html.Span(str(viaje["viajes_dador"]))], className="dlp-row"),
                ], className="dlp-card"),
            ], style={"marginBottom": "14px"}),

            html.Div("Condiciones de pago", className="mobile-section-title", style={"marginBottom": "8px"}),
            html.Div([
                html.Div([html.Span("Plazo"), html.Span(viaje["plazo_pago"])], className="dlp-row"),
                html.Div([html.Span("Instrumento"), html.Span(viaje["instrumento"])], className="dlp-row"),
                html.Div([html.Span("Monto a cobrar"), html.Span(_pesos(viaje["tarifa"]), className="dlp-total")], className="dlp-row dlp-total-row"),
            ], className="dlp-card"),

            html.Div("QuickPay", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "14px"}),
            html.Div([
                html.Div([
                    html.Span("Estado"),
                    html.Span("Habilitado" if viaje["quickpay_habilitado"] else "No habilitado", className="dlp-total" if viaje["quickpay_habilitado"] else "dlp-discount"),
                ], className="dlp-row"),
                *([
                    html.Div([html.Span("Monto adelantable"), html.Span(_pesos(viaje["adelantable"]))], className="dlp-row"),
                    html.Div("Tarifas disponibles", className="viaje-card-sub", style={"marginTop": "4px", "fontWeight": "700"}),
                    *_qp_tarifas_rows(viaje["adelantable"]),
                ] if viaje["quickpay_habilitado"] else [
                    html.Div(viaje["requisito_qp"], className="score-bk-tip"),
                ]),
            ], className="dlp-card"),

            html.Div("Estado documental", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "14px"}),
            html.Div([
                html.Div([
                    html.Span("Documentación"),
                    html.Span("Completa" if viaje["documentacion_ok"] else "Incompleta", className="gold" if viaje["documentacion_ok"] else "dlp-discount"),
                ], className="dlp-row"),
                html.Div(viaje["doc_alerta"], className="score-bk-tip" if not viaje["documentacion_ok"] else "viaje-card-sub"),
                html.Div("Obligatorio OK", className="viaje-card-sub", style={"marginTop": "10px", "fontWeight": "700"}),
                html.Ul([
                    html.Li(item, style={"color": "#22c55e", "marginBottom": "4px"}) for item in docs_flow["ok"]
                ], style={"paddingLeft": "18px", "margin": "6px 0"}),
                html.Div("Requisitos", className="viaje-card-sub", style={"marginTop": "8px", "fontWeight": "700"}),
                html.Ul([
                    html.Li(item, style={"color": "rgba(239,230,209,0.85)", "marginBottom": "4px"}) for item in docs_flow["req"]
                ], style={"paddingLeft": "18px", "margin": "6px 0"}),
                html.Div([html.Span("Ventana de carga"), html.Span(viaje["ventana_carga"])], className="dlp-row", style={"marginTop": "10px"}),
                html.Div([html.Span("Ventana de descarga"), html.Span(viaje["ventana_descarga"])], className="dlp-row"),
            ], className="dlp-card"),

            *([
                html.Div("Validación geolocalizada", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "14px"}),
                html.Div([
                    html.Div([html.Span("GPS origen"), html.Span("Validado" if viaje.get("gps_origen_validado") else "Pendiente", className="gold" if viaje.get("gps_origen_validado") else "dlp-discount")], className="dlp-row"),
                    html.Div([html.Span("GPS destino"), html.Span("Validado" if viaje.get("gps_destino_validado") else "Pendiente", className="gold" if viaje.get("gps_destino_validado") else "dlp-discount")], className="dlp-row"),
                ], className="dlp-card"),
            ] if tipo_flujo == "en_curso" else []),

            html.Div([
                _btn("← Atrás", "tab:viajes", className="btn-back"),
            ], className="action-row"),
            html.Div([
                *([_btn("✏️ Modificar condiciones", f"viaje:modificar:{viaje['id'].replace('#', '')}", className="btn-ghost")] if tipo_flujo == "en_espera" else []),
                _btn(primary_action["label"], primary_action["action"], className=primary_class),
            ], className="action-row", style={"marginTop": "10px"}),
            html.Div([
                *([_btn(secondary_action["label"], secondary_action["action"], className="btn-ghost")] if mostrar_secundaria else []),
                *([
                    _btn("Validar GPS origen", f"flow:gps_origen:{viaje['id'].replace('#', '')}", className="btn-ghost")
                ] if tipo_flujo == "en_curso" and not viaje.get("gps_origen_validado") else []),
                *([
                    _btn("Validar GPS destino", f"flow:gps_destino:{viaje['id'].replace('#', '')}", className="btn-ghost")
                ] if tipo_flujo == "en_curso" and not viaje.get("gps_destino_validado") else []),
            ], className="action-row", style={"marginTop": "10px"}),
            *([
                html.Div(
                    "Viaje bloqueado: necesitás documentación vigente para iniciar.",
                    className="score-bk-tip",
                    style={"marginTop": "8px"},
                )
            ] if tipo_flujo == "proximo" and not viaje["documentacion_ok"] else []),
        ])

    if tab == "incidente_reporte":
        incidente_data = incidente_data or {}
        step = int(incidente_data.get("step", 1))
        categoria = str(incidente_data.get("cat") or "")
        opcion_id = str(incidente_data.get("subopt") or "")
        urgencia = str(incidente_data.get("urgency") or "informativo")
        descripcion = str(incidente_data.get("desc") or "")
        enviado = bool(incidente_data.get("submitted"))
        categorias_grupo = {
            "Desvíos operativos": [k for k, v in INCIDENTE_CATEGORIAS.items() if v["grupo"] == "Desvíos operativos"],
            "Incidentes de seguridad": [k for k, v in INCIDENTE_CATEGORIAS.items() if v["grupo"] == "Incidentes de seguridad"],
            "Documentación": [k for k, v in INCIDENTE_CATEGORIAS.items() if v["grupo"] == "Documentación"],
        }
        cfg = INCIDENTE_CATEGORIAS.get(categoria)
        opciones = cfg["opciones"] if cfg else []
        opt_sel = next((o for o in opciones if o["id"] == opcion_id), None)
        alerta = alerta_pre_envio_incidente(categoria, opcion_id)

        if enviado:
            return html.Div(className="phone-scroll", children=[
                html.Div("Incidente reportado", className="mobile-title", style={"marginBottom": "10px"}),
                html.Div([
                    html.Div("✓ Reporte enviado", className="mobile-section-title", style={"color": "#22c55e", "marginBottom": "8px"}),
                    html.Div("El estado del viaje fue actualizado y el dador recibió la notificación.", className="viaje-card-sub"),
                ], className="doc-card"),
                html.Div("¿Qué pasa ahora?", className="mobile-section-title", style={"marginTop": "14px", "marginBottom": "8px"}),
                html.Div([
                    html.Div("• AgroVIA registra el evento con timestamp y geolocalización.", className="viaje-card-sub", style={"marginBottom": "6px"}),
                    html.Div("• El dador visualiza la categoría, motivo y urgencia del reporte.", className="viaje-card-sub", style={"marginBottom": "6px"}),
                    html.Div("• Podés seguir el estado desde el detalle del viaje en curso.", className="viaje-card-sub"),
                ], className="doc-card"),
                html.Div([
                    _btn("Volver al viaje", "incidente:back_en_curso", className="btn-gold-full"),
                ], className="action-row", style={"marginTop": "14px"}),
            ])

        progress = html.Div([
            html.Div(className="dador-metric-bar", style={"height": "4px", "marginBottom": "12px"}, children=[
                html.Div(className="dador-metric-fill success", style={"width": f"{25 * max(1, min(step, 4))}%"})
            ])
        ])

        if step == 1:
            return html.Div(className="phone-scroll", children=[
                _btn("← Volver", "incidente:back_en_curso", className="btn-back"),
                html.Div("Reportar incidente o desvío", className="mobile-title", style={"marginBottom": "4px"}),
                html.Div(f"Viaje {VIAJE_EN_CURSO['id']} · En curso", className="mobile-subtitle", style={"marginBottom": "10px"}),
                progress,
                *[
                    html.Div([
                        html.Div(grupo, className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "10px"}),
                        html.Div([
                            _btn(
                                [
                                    html.Div(INCIDENTE_CATEGORIAS[key]["titulo"], className="viaje-card-route"),
                                    html.Div(INCIDENTE_CATEGORIAS[key]["desc"], className="viaje-card-sub"),
                                ],
                                f"incidente:cat:{key}",
                                className="viaje-card",
                            )
                            for key in keys
                        ]),
                    ])
                    for grupo, keys in categorias_grupo.items()
                ],
            ])

        if step == 2:
            return html.Div(className="phone-scroll", children=[
                _btn("← Volver", "incidente:step:1", className="btn-back"),
                html.Div("Especificá el motivo", className="mobile-title", style={"marginBottom": "4px"}),
                html.Div(cfg["titulo"] if cfg else "", className="mobile-subtitle", style={"marginBottom": "10px"}),
                progress,
                html.Div([
                    _btn(
                        [
                            html.Div(opt["label"], className="viaje-card-route"),
                            html.Div(opt.get("sub") or "", className="viaje-card-sub"),
                        ],
                        f"incidente:opt:{opt['id']}",
                        className="viaje-card",
                        style={"border": "1px solid #22c55e"} if opt["id"] == opcion_id else {},
                    )
                    for opt in opciones
                ]),
                html.Div([
                    _btn("Continuar", "incidente:step:3", className="btn-gold-full", disabled=not bool(opcion_id)),
                ], className="action-row", style={"marginTop": "12px"}),
            ])

        if step == 3:
            caso_legal = matriz_legal_incidente(categoria, opcion_id)

            return html.Div(className="phone-scroll", children=[
                _btn("← Volver", "incidente:step:2", className="btn-back"),
                html.Div("Detalle del incidente o desvío", className="mobile-title", style={"marginBottom": "10px"}),
                progress,
                html.Div([html.Label("Descripción (opcional)", className="form-label"), html.Textarea(descripcion or "Contá qué pasó con el mayor detalle posible...", className="form-textarea", disabled=True)], className="form-group", style={"marginTop": "8px"}),
                html.Div("Adjuntar foto (opcional)", className="viaje-card-sub", style={"marginTop": "8px"}),
                html.Div([
                    _btn("Adjuntar foto", "incidente:foto:adjuntar", className="btn-ghost"),
                ], className="action-row", style={"marginTop": "8px"}),
                html.Div([
                    html.Div(caso_legal["titulo"], className="mobile-section-title", style={"marginBottom": "10px"}),
                    html.Div([
                        html.Div([
                            html.Div("Responsable principal", style={"color": "#ef4444", "fontWeight": "700", "fontSize": "12px", "marginBottom": "6px"}),
                            html.Div(caso_legal["principal"], style={"whiteSpace": "pre-line", "fontSize": "13px", "lineHeight": "1.45"}),
                        ], style={"background": "#2d1818", "border": "1px solid rgba(239,68,68,0.25)", "borderRadius": "10px", "padding": "10px", "marginBottom": "8px"}),
                        html.Div([
                            html.Div("Responsable secundario", style={"color": "#f59e0b", "fontWeight": "700", "fontSize": "12px", "marginBottom": "6px"}),
                            html.Div(caso_legal["secundario"], style={"whiteSpace": "pre-line", "fontSize": "13px", "lineHeight": "1.45"}),
                        ], style={"background": "#2b2417", "border": "1px solid rgba(245,158,11,0.25)", "borderRadius": "10px", "padding": "10px", "marginBottom": "8px"}),
                        html.Div([
                            html.Div("Rol de AgroVIA", style={"color": "#10b981", "fontWeight": "700", "fontSize": "12px", "marginBottom": "6px"}),
                            html.Div(caso_legal["agrovia"], style={"whiteSpace": "pre-line", "fontSize": "13px", "lineHeight": "1.45"}),
                        ], style={"background": "#132a24", "border": "1px solid rgba(16,185,129,0.25)", "borderRadius": "10px", "padding": "10px"}),
                    ]),
                ], className="dlp-card", style={"marginTop": "10px"}),
                html.Div([
                    _btn("Enviar reporte", "incidente:submit", className="btn-gold-full"),
                ], className="action-row", style={"marginTop": "12px"}),
            ])

        return html.Div(className="phone-scroll", children=[
            _btn("← Volver", "incidente:step:3", className="btn-back"),
            html.Div("Confirmá el reporte", className="mobile-title", style={"marginBottom": "10px"}),
            progress,
            html.Div([
                html.Div([html.Span("Categoría"), html.Span(cfg["titulo"] if cfg else "-")], className="dlp-row"),
                html.Div([html.Span("Motivo"), html.Span(opt_sel["label"] if opt_sel else "-")], className="dlp-row"),
                html.Div([html.Span("Urgencia"), html.Span(INCIDENTE_URGENCIAS.get(urgencia, "Informativo"), className="gold")], className="dlp-row"),
            ], className="dlp-card"),
            *([html.Div(alerta, className="score-bk-tip", style={"marginTop": "8px"})] if alerta else []),
            html.Div([
                _btn("Enviar reporte", "incidente:submit", className="btn-gold-full"),
            ], className="action-row", style={"marginTop": "12px"}),
        ])

    # ── VIAJE EN CURSO ────────────────────────────────────────────────
    if tab == "en_curso":
        hito_actual = max(1, min(hito_actual or 3, 5))
        cl_data = checklist_data or {}
        checklist_done = _hito_checklist_done(hito_actual, cl_data)
        status_map = {
            "done": ("✓", "#22c55e", "rgba(34,197,94,0.18)"),
            "active": ("●", "#c8a84b", "rgba(200,168,75,0.18)"),
            "pending": ("○", "rgba(239,230,209,0.5)", "rgba(239,230,209,0.08)"),
        }

        if hito_actual == 1:
            cta_label = "Confirmar inicio de carga + foto CPD"
            cta_sub = "Valida GPS en origen y desbloquea seguimiento"
        elif hito_actual == 2:
            cta_label = "Confirmar salida en tránsito"
            cta_sub = "Registra hora de salida y activa tracking"
        elif hito_actual == 3:
            cta_label = "Confirmar llegada a destino"
            cta_sub = "Valida GPS contra el destino declarado"
        elif hito_actual == 4:
            cta_label = "Confirmar descarga y cierre"
            cta_sub = "Adjuntá remito y ticket de balanza solo cuando aplique"
        else:
            cta_label = "Ir a calificar al dador"
            cta_sub = "Viaje operativo cerrado"

        steps_html = []
        for i, hito in enumerate(HITOS_VIAJE_EN_CURSO):
            last = i == len(HITOS_VIAJE_EN_CURSO) - 1
            step_num = i + 1
            if hito_actual > 4:
                estado = "done"
            elif step_num < hito_actual:
                estado = "done"
            elif step_num == hito_actual:
                estado = "active"
            else:
                estado = "pending"

            icono, color, fondo = status_map[estado]

            # Checklist buttons — active: orange; done: gray; pending: none
            cl_list = CHECKLIST_POR_HITO.get(step_num, [])
            if cl_list and estado in ("active", "done"):
                btn_divs = []
                for cl in cl_list:
                    this_done = bool(cl_data.get(cl["id"]))
                    if estado == "active":
                        label = (f"✔ {cl['nombre_corto']}" if this_done
                                 else f"Completar checklist · {cl['nombre_corto']}")
                        btn_style = {
                            "fontSize": "12px", "padding": "4px 10px", "marginTop": "4px",
                            "color": "#22c55e" if this_done else "#c8a84b",
                            "border": "1px solid " + ("#22c55e" if this_done else "#c8a84b"),
                        }
                    else:  # done hito — gray review button
                        label = f"Checklist · {cl['nombre_corto']}"
                        btn_style = {
                            "fontSize": "12px", "padding": "4px 10px", "marginTop": "4px",
                            "color": "rgba(239,230,209,0.38)",
                            "border": "1px solid rgba(239,230,209,0.18)",
                        }
                    btn_divs.append(
                        _btn(label, f"checklist:open:{cl['id']}", className="btn-ghost", style=btn_style)
                    )
                checklist_badges: html.Div | None = html.Div(btn_divs, style={"display": "flex", "flexDirection": "column", "gap": "2px", "marginTop": "6px"})
            else:
                checklist_badges = None

            body_children = [
                html.Div(hito["titulo"], className="m-t-label" + (" muted" if estado == "pending" else "")),
                html.Div(hito["accion"], className="m-t-time", style={"marginTop": "4px"}),
                html.Div(hito["validacion"], className="viaje-card-sub", style={"marginTop": "6px"}),
                html.Div(hito["adjunto"], className="viaje-card-sub", style={"marginTop": "4px", "color": "#c8a84b" if estado != "pending" else "rgba(239,230,209,0.42)"}),
            ]
            if checklist_badges:
                body_children.append(checklist_badges)

            steps_html.append(
                html.Div(className="m-t-step", children=[
                    html.Div(className="m-t-col", children=[
                        html.Div(icono, className="m-dot", style={"background": fondo, "color": color, "border": f"1px solid {color}"}),
                        *([html.Div(className=f"m-line {'done' if estado in ('done', 'active') else 'pending'}")] if not last else []),
                    ]),
                    html.Div(className="m-t-body", children=body_children),
                ])
            )

        return html.Div(className="phone-scroll", children=[
            _btn("← Home", "tab:inicio", className="btn-back"),
            html.Div(f"Viaje en curso {VIAJE_EN_CURSO['id']}", className="mobile-title", style={"marginBottom": "6px", "color": "#ff9500"}),
            html.Div(
                "Modo offline: eventos se guardan y sincronizan al recuperar señal" if VIAJE_EN_CURSO["offline"] else "GPS en tiempo real activo · eventos sincronizados",
                className="viaje-card-sub",
                style={"marginBottom": "14px", "color": "#c8a84b" if VIAJE_EN_CURSO["offline"] else "rgba(239,230,209,0.58)"},
            ),

            dcc.Graph(
                figure=create_route_map_figure(VIAJE_EN_CURSO["origen"], VIAJE_EN_CURSO["destino"], VIAJE_EN_CURSO["eta"]),
                config={'displayModeBar': False, 'responsive': True},
                style={"margin": "0", "paddingBottom": "0"},
                className="route-map-svg",
            ),

            html.Div([
                html.Div("Viaje activo", className="mobile-section-title", style={"marginBottom": "8px"}),
                html.Div([
                    html.Div([html.Span("Ruta"), html.Span(f"{VIAJE_EN_CURSO['origen']} → {VIAJE_EN_CURSO['destino']}", className="gold")], className="dlp-row"),
                    html.Div([html.Span("Carga"), html.Span(f"{VIAJE_EN_CURSO['carga']} · {VIAJE_EN_CURSO['toneladas']} tn")], className="dlp-row"),
                    html.Div([html.Span("ETA"), html.Span(VIAJE_EN_CURSO["eta"] )], className="dlp-row"),
                ], className="dlp-card"),
            ]),

            html.Div("Hitos operativos", className="mobile-section-title", style={"marginBottom": "10px", "marginTop": "16px"}),
            html.Div(className="m-timeline", children=steps_html),

            html.Div("Validación geolocalizada", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "16px"}),
            html.Div([
                html.Div([html.Span("GPS origen"), html.Span("Validado", className="gold")], className="dlp-row"),
                html.Div([
                    html.Span("GPS destino"),
                    html.Span("Validado" if hito_actual >= 4 else "Pendiente", className="gold" if hito_actual >= 4 else "dlp-discount"),
                ], className="dlp-row"),
                html.Div(
                    "Los hitos de inicio y llegada requieren validación GPS en el punto declarado.",
                    className="viaje-card-sub",
                    style={"marginTop": "8px"},
                ),
            ], className="dlp-card"),

            html.Div("Acciones", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "16px"}),
            html.Div(cta_sub, className="viaje-card-sub", style={"marginBottom": "8px"}),
            html.Div([
                _btn("Reportar incidente o desvío", "incidente:report", className="btn-ghost"),
                _btn(
                    cta_label,
                    "hito:advance",
                    className="btn-gold-action" if hito_actual <= 4 else "btn-gold-full",
                    disabled=(hito_actual <= 4 and not checklist_done),
                    style={"opacity": "0.4", "cursor": "not-allowed"} if (hito_actual <= 4 and not checklist_done) else {},
                ),
            ], className="action-row"),
            html.Div([
                _btn("Soporte AgroVIA", "soporte:open", className="btn-ghost"),
                _btn("Chat con el dador", "chat:dador", className="btn-ghost"),
            ], className="action-row", style={"marginTop": "10px"}),
            _btn("Reiniciar flujo de hitos", "hito:reset", className="score-link", style={"marginTop": "8px"}),

            html.Div("Datos del dador", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "16px"}),
            html.Div([
                html.Div([html.Span("Razón social"), html.Span(VIAJE_EN_CURSO["empresa_dador"], className="gold")], className="dlp-row"),
                html.Div([html.Span("CUIT"), html.Span(VIAJE_EN_CURSO["cuit"])], className="dlp-row"),
                html.Div([html.Span("Teléfono"), html.Span(VIAJE_EN_CURSO["telefono"])], className="dlp-row"),
                html.Div([html.Span("Rating"), html.Span(f"★ {VIAJE_EN_CURSO['rating']}")], className="dlp-row"),
            ], className="dlp-card"),
        ])

    # ── QUICKPAY ────────────────────────────────────────────────────────
    if tab == "quickpay_detalle":
        score_qp_display = score_financiero
        score_comps = [
            ("H · Historial operativo (40%)",    sub_historial,    "blue"   if sub_historial    >= 80 else "yellow"),
            ("V · Estado vehículo (25%)",         sub_vehiculo,     "orange" if sub_vehiculo     >= 80 else "yellow"),
            ("R · Recencia (20%)",                sub_recencia,     "purple" if sub_recencia     >= 80 else "yellow"),
            ("C · Calificación dadores (15%)",    sub_calificacion, "green"  if sub_calificacion >= 80 else "yellow"),
        ]
        return html.Div(className="phone-scroll", children=[
            _btn("← Inicio", "tab:inicio", className="btn-back"),
            html.Div("Detalle Quick-Pay", className="mobile-title", style={"marginBottom": "16px"}),

            # Score breakdown
            html.Div([
                html.Div([
                    html.Span("Tu Score", style={"fontSize": "13px", "color": "rgba(239,230,209,0.65)"}),
                    html.Div([html.Span(str(score_qp_display), className="score-bk-value"), html.Span("/100", className="score-bk-denom")]),
                ], className="score-bk-header"),
                *[
                    html.Div([
                        html.Div([html.Span(lbl), html.Span(f"{pct}%", className="score-comp-pct")], className="score-comp-row"),
                        html.Div(html.Div(className=f"score-comp-fill {color}", style={"width": f"{pct}%"}),
                                 className="score-comp-track"),
                    ], className="score-comp-item")
                    for lbl, pct, color in score_comps
                ],
                html.Div(
                    f"⚡ Quick-Pay {'habilitado' if quickpay_habilitado else 'restringido'} · Adelanto máximo {quickpay_pct}%",
                    className="score-bk-tip",
                ),
                html.Div(
                    f"Tendencia semanal: {trend_sign}{trend_points_7d} pts",
                    className="score-bk-tip",
                    style={"color": trend_color, "fontWeight": "700", "marginTop": "6px"},
                ),
            ], className="score-breakdown"),

            *([html.Div([
                html.Div("Caps activos", className="mobile-section-title", style={"marginBottom": "8px"}),
                html.Div([
                    html.Ul([
                        html.Li(cap, style={"marginBottom": "4px", "color": "rgba(239,230,209,0.88)"})
                        for cap in caps_aplicados
                    ], style={"paddingLeft": "18px", "margin": "0"}),
                ], className="doc-card"),
            ])] if caps_aplicados else []),

            *[
                html.Div([
                    html.Div(sim["titulo"], className="viaje-card-route"),
                    html.Div(sim["impacto"], className="viaje-card-sub", style={"color": "#22c55e", "fontWeight": "700", "marginTop": "4px"}),
                    html.Div([
                        html.Span(f"Score proyectado: {sim['score']} / 100", className="viaje-card-sub"),
                        html.Span(
                            f"Quick-Pay: {_quickpay_pct_from_score(sim['score'])}%",
                            className="badge-retorno" if _quickpay_pct_from_score(sim["score"]) > 0 else "badge-no-retorno",
                        ),
                    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginTop": "8px"}),
                ], className="viaje-card")
                for sim in simulaciones
            ],

            # Pendientes
            html.Div("Viajes pendientes de cobro", className="mobile-section-title", style={"marginBottom": "10px"}),
            *[
                html.Div([
                    *([html.Div("⚡ Adelantado", className="badge-adelantado")] if p["adelantado"] else []),
                    html.Div([html.Span(p["ruta"], className="pago-route"), html.Span(_fmt_fecha_entrega(p["fecha_entrega"]), className="pago-date")],
                             style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"}),
                    *([
                        html.Div(_pesos(p["tarifa"]), className="pago-tarifa"),
                        html.Div([
                            html.Div([
                                html.Div(f"Adelanto disponible: {_pesos(p['adelanto'])} (65%)"),
                                html.Div("Tarifas de servicio disponibles:", style={"marginTop": "6px", "fontWeight": "700"}),
                                *_qp_tarifas_rows(p["adelanto"], class_name="dlp-row"),
                            ], className="pago-details"),
                            *_qp_restante(p),
                        ]),
                    ] if not p["adelantado"] else [
                        html.Div(f"Cobro: {_pesos(p['tarifa'])} · Recibiste: {_pesos(p['neto'])} · Liquidación: 25/08",
                                 className="pago-details"),
                    ]),
                ], className="pago-card")
                for p in QUICKPAY_PENDIENTES if _qp_vigente(p)
            ],
            html.Div(
                "El adelanto es procesado por Meridiano o Pymecred según la opción elegida. AgroVIA facilita la operación.",
                className="qp-disclaimer",
                style={"marginTop": "12px"},
            ),
        ])

    # ── HISTORIAL ───────────────────────────────────────────────────────
    if tab == "historial":
        return html.Div(className="phone-scroll", children=[
            html.Div("Historial", className="mobile-title", style={"marginBottom": "10px"}),

            html.Div("Pendientes de calificación", className="mobile-section-title", style={"marginBottom": "8px"}),
            *[
                html.Div([
                    html.Div([
                        html.Span(p["viaje"], className="viaje-card-route"),
                    ], className="viaje-card-top"),
                    html.Div(p["ruta"], className="viaje-card-sub"),
                    html.Div(f"{p['carga']} · Dador: {p['dador']}", className="viaje-card-sub"),
                    html.Div(p["fecha"], className="viaje-card-sub", style={"marginTop": "4px"}),
                    html.Div([
                        _btn(
                            "Calificar dador",
                            f"calificar:open:{p['viaje'].replace('#', '')}",
                            className="btn-gold-action",
                            style={"width": "100%", "marginTop": "8px"},
                        ),
                    ], style={"marginTop": "8px"}),
                ], className="viaje-card")
                for p in PENDIENTES_CALIFICACION
            ],

            html.Div("Viajes cerrados", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "16px"}),
            html.Div(
                html.Table(className="mobile-table", children=[
                    html.Thead(html.Tr([html.Th("Fecha"), html.Th("Ruta"), html.Th("Tarifa"), html.Th("")])),
                    html.Tbody([
                        html.Tr([
                            html.Td(h["fecha"]),
                            html.Td(h["ruta"]),
                            html.Td(_pesos(h["tarifa"]), className="gold"),
                            html.Td("✅", className="green"),
                        ])
                        for h in HISTORIAL_TRANS
                    ]),
                ]),
                className="mobile-table-card",
            ),
        ])

    # ── PERFIL ──────────────────────────────────────────────────────────
    if tab == "perfil":
        camion_elegido = CAMIONES_TRANSPORTISTA[0]
        return html.Div(className="phone-scroll", children=[
            html.Div([
                html.Div(PERFIL_TRANSPORTISTA["iniciales"], className="perfil-avatar"),
                html.Div([
                    html.Div(PERFIL_TRANSPORTISTA["nombre"], className="perfil-name"),
                    html.Div(f"CUIT: {PERFIL_TRANSPORTISTA['cuit']}", className="perfil-cuit"),
                ]),
            ], className="perfil-header"),

            html.Div([
                html.Span("Perfil del transportista", className="mobile-section-title"),
                html.Button("✏️", style={"background": "none", "border": "none", "fontSize": "16px", "cursor": "pointer", "padding": "0 4px"}),
            ], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "marginBottom": "8px"}),
            html.Div([
                html.Div([html.Span("Nombre"), html.Span(PERFIL_TRANSPORTISTA["nombre"])], className="dlp-row"),
                html.Div([html.Span("CUIT"), html.Span(PERFIL_TRANSPORTISTA["cuit"])], className="dlp-row"),
                html.Div([html.Span("Categoría fiscal"), html.Span(PERFIL_TRANSPORTISTA["fiscal"])], className="dlp-row"),
                html.Div([html.Span("Teléfono"), html.Span(PERFIL_TRANSPORTISTA["telefono"])], className="dlp-row"),
                html.Div([html.Span("Correo"), html.Span(PERFIL_TRANSPORTISTA["email"])], className="dlp-row"),
                html.Div([html.Span("Provincia"), html.Span(PERFIL_TRANSPORTISTA["provincia"])], className="dlp-row"),
            ], className="dlp-card"),

            html.Div([
                html.Span("Datos del camión", className="mobile-section-title"),
                html.Button("✏️", style={"background": "none", "border": "none", "fontSize": "16px", "cursor": "pointer", "padding": "0 4px"}),
            ], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "marginBottom": "8px", "marginTop": "18px"}),
            _btn(
                f"Camión elegido: {camion_elegido['patente']} ▾",
                "camion:select",
                className="btn-ghost-light",
                style={"width": "100%", "marginBottom": "10px", "textAlign": "left"},
            ),
            html.Div([
                html.Div([html.Span("Patente"), html.Span(camion_elegido["patente"], className="gold")], className="dlp-row"),
                html.Div([html.Span("Tipo de vehículo"), html.Span(camion_elegido["tipo"])], className="dlp-row"),
                html.Div([html.Span("Cédula verde / azul"), html.Span(camion_elegido["cedula"])], className="dlp-row"),
                html.Div([html.Span("¿Posee satelital?"), html.Span(camion_elegido["satelital"], className="gold")], className="dlp-row"),
            ], className="dlp-card"),
            _btn(
                "+ Agregar otro vehículo",
                "camion:add",
                className="btn-ghost",
                style={"width": "100%", "marginTop": "10px"},
            ),

            html.Div("Documentación del vehículo", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "18px"}),
            html.Div([
                html.Div([
                    html.Div([
                        html.Span("✓" if d["estado"] == "ok" else "⚠",
                                  className="doc-icon-ok" if d["estado"] == "ok" else "doc-icon-warning"),
                        html.Div([
                            html.Span(d["nombre"],
                                      className="doc-name" if d["estado"] == "ok" else "doc-name warning"),
                            html.Div(d["detalle"], className="viaje-card-sub", style={"marginTop": "4px"}),
                        ]),
                    ], className="doc-left"),
                    html.Div([
                        html.Button(d["accion"], className="action-link"),
                        _btn("Ver foto", f"doc:foto:{d['imagen']}",
                             className="action-link",
                             style={"fontSize": "12px", "marginTop": "4px", "opacity": "0.75"})
                        if d.get("imagen") else None,
                    ], style={"display": "flex", "flexDirection": "column", "alignItems": "flex-end"}),
                ], className="doc-item")
                for d in DOCS_CAMION
            ], className="doc-card"),

            html.Div("Documentación del conductor", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "18px"}),
            html.Div([
                html.Div([
                    html.Div([
                        html.Span("✓" if d["estado"] == "ok" else "⚠",
                                  className="doc-icon-ok" if d["estado"] == "ok" else "doc-icon-warning"),
                        html.Div([
                            html.Span(d["nombre"],
                                      className="doc-name" if d["estado"] == "ok" else "doc-name warning"),
                            html.Div(d["detalle"], className="viaje-card-sub", style={"marginTop": "4px"}),
                        ]),
                    ], className="doc-left"),
                    html.Div([
                        html.Button(d["accion"], className="action-link"),
                        _btn("Ver foto", f"doc:foto:{d['imagen']}",
                             className="action-link",
                             style={"fontSize": "12px", "marginTop": "4px", "opacity": "0.75"})
                        if d.get("imagen") else None,
                    ], style={"display": "flex", "flexDirection": "column", "alignItems": "flex-end"}),
                ], className="doc-item")
                for d in DOCS_CONDUCTOR
            ], className="doc-card"),

            html.Div("Perfil QuickPay", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "18px"}),
            html.Div([
                html.Div([html.Span("Score actual"), html.Span(f"{score_financiero} / 100", className="dlp-total")], className="dlp-row"),
                html.Div([html.Span("Nivel"), html.Span(nivel_label.replace("Nivel ", ""))], className="dlp-row"),
                html.Div([html.Span("Adelanto habilitado"), html.Span(f"Hasta {quickpay_pct}% del flete")], className="dlp-row"),
                html.Div([html.Span("Próximo objetivo"), html.Span(objetivo_destacado)], className="dlp-row"),
                _btn("Ver desglose completo →", "quickpay:open", className="score-link", style={"marginTop": "8px", "textAlign": "left"}),
            ], className="dlp-card"),

            html.Div("Calificaciones recibidas", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "18px"}),
            *[
                html.Div([
                    html.Div(("⭐" * c["estrellas"] + "☆" * (5 - c["estrellas"])), className="stars"),
                    html.Div(f"\"{c['texto']}\"", className="cal-text"),
                    html.Div(f"— {c['autor']}",   className="cal-author"),
                ], className="cal-card")
                for c in CALIFICACIONES
            ],

            html.Div("Configuración y soporte", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "18px"}),
            html.Div([
                (
                    _btn(item, "terms:open", className="doc-item", style={"width": "100%", "textAlign": "left"}) if item == "Términos y condiciones"
                    else html.A(item, href="/assets/manual_buenas_practicas.pdf", target="_blank", className="doc-item", style={"display": "block", "width": "100%", "textAlign": "left", "textDecoration": "none", "color": "inherit"}) if item == "Manual de buenas prácticas"
                    else html.Div(item, className="doc-item")
                )
                for item in CONFIGURACION_SOPORTE
            ], className="doc-card"),
        ])

    # ── FALLBACK: lista de viajes ────────────────────────────────────────

        # ── PROPUESTA recibida ──────────────────────────────────────────────
        if tab == "propuesta":
            p = PROPUESTA_ACTUAL
            dlp_desc   = int(p["tarifa_base"] * abs(p["ajuste_dlp"]) / 100)
            return html.Div(className="phone-scroll", children=[
                html.Div([
                    html.Div("🔔 Nueva propuesta", className="mobile-title"),
                    html.Div("Recibida hace 2 min · Expira en 8 min", className="propuesta-timer"),
                ], style={"marginBottom": "16px"}),
                html.Div(
                    html.Svg(viewBox="0 0 360 180", style={"display": "block", "width": "100%"}, children=[
                        html.Rect(x="0", y="0", width="360", height="180", fill="#1a2e1a"),
                        html.Line(x1="80", y1="50", x2="280", y2="140", stroke="#c8a84b", stroke_width="2", opacity="0.6"),
                        html.Circle(cx="80",  cy="50",  r="8",  fill="#22c55e"),
                        html.Circle(cx="80",  cy="50",  r="13", fill="none", stroke="#22c55e", stroke_width="1.5", opacity="0.4"),
                        html.Text(p["origen"],  x="80",  y="36",  text_anchor="middle", fill="#f0ead8", fontSize="11", font_weight="600"),
                        html.Circle(cx="280", cy="140", r="8",  fill="#c8a84b"),
                        html.Circle(cx="280", cy="140", r="13", fill="none", stroke="#c8a84b", stroke_width="1.5", opacity="0.4"),
                        html.Text(p["destino"], x="280", y="162", text_anchor="middle", fill="#f0ead8", fontSize="11", font_weight="600"),
                    ]),
                    className="route-map-svg",
                ),
                html.Div(className="viaje-info-card", children=[
                    html.Div(className="viaje-info-grid", children=[
                        html.Div([html.Div("Carga",    className="viaje-info-key"), html.Div(f"{p['carga']} · {p['toneladas']} tn",      className="viaje-info-val")]),
                        html.Div([html.Div("Distancia",className="viaje-info-key"), html.Div(f"{p['distancia']} km",                     className="viaje-info-val")]),
                        html.Div([html.Div("Dador",    className="viaje-info-key"), html.Div(f"{p['empresa_dador']} · ★{p['score_dador']}", className="viaje-info-val")]),
                        html.Div([html.Div("Ventana",  className="viaje-info-key"), html.Div(p["ventana_carga"],                          className="viaje-info-val")]),
                    ]),
                ]),
                html.Div("Desglose de tarifa", className="mobile-section-title", style={"marginBottom": "8px"}),
                html.Div([
                    html.Div([html.Span("Tarifa base FADEEAC"),                       html.Span(_pesos(p["tarifa_base"]))],                         className="dlp-row"),
                    html.Div([html.Span(f"Ajuste retorno (DLP {p['ajuste_dlp']}%)"), html.Span(f"-{_pesos(dlp_desc)}", className="dlp-discount")], className="dlp-row"),
                    html.Div([html.Span("Tarifa final"),                              html.Span(_pesos(p["tarifa_final"]), className="dlp-total")],  className="dlp-row dlp-total-row"),
                ], className="dlp-card"),
                html.Div("⚡ Quick-Pay si aceptás", className="mobile-section-title", style={"marginBottom": "8px", "marginTop": "16px"}),
                html.Div([
                    html.Div([html.Span(f"Adelantable ({p['adelantable_pct']}% del flete)"), html.Span(_pesos(p["adelantable_monto"]))],          className="dlp-row"),
                    html.Div("Tarifas disponibles", className="viaje-card-sub", style={"marginTop": "4px", "fontWeight": "700"}),
                    *_qp_tarifas_rows(p["adelantable_monto"]),
                ], className="dlp-card"),
                html.Div([
                    _btn("Rechazar",    "propuesta:reject", className="btn-ghost"),
                    _btn("✓  Aceptar", "propuesta:accept", className="btn-gold-action"),
                ], className="action-row", style={"marginTop": "20px"}),
            ])

    return html.Div(className="phone-scroll", children=[
        html.Div("Cargas disponibles", className="mobile-title", style={"marginBottom": "12px"}),
        *[
            _btn([
                html.Div([
                    html.Span(f"{v['origen']} → {v['destino']}", className="viaje-card-route"),
                    html.Span(_pesos(v["tarifa"]), className="viaje-card-price"),
                ], className="viaje-card-top"),
                html.Div(f"{v['carga']} · {v['distancia']} km", className="viaje-card-sub"),
            ],
            f"viaje:{v['id'].replace('#', '')}",
            className="viaje-card")
            for v in VIAJES
        ],
    ])


def transportista_layout(tab: str, viaje_id: str | None, hito_actual: int, scoring_data: dict | None = None, checklist_data: dict | None = None, incidente_data: dict | None = None) -> html.Div:
    content = transportista_tab_content(tab, viaje_id, hito_actual, scoring_data, checklist_data, incidente_data)
    _t = [
        ("tab:inicio",   "🏠", "Inicio"),
        ("tab:publicar", "📦", "Publicar"),
        ("tab:viajes",   "🚛", "Viajes"),
        ("tab:historial","🕘", "Historial"),
        ("tab:perfil",   "👤", "Perfil"),
    ]
    active_key = f"tab:{tab}"
    return html.Div(
        className="transport-shell",
        children=[
            html.Div(
                className="phone-frame",
                children=[
                    html.Div(className="phone-notch"),
                    html.Div(content, className="phone-content"),
                    html.Div(
                        className="phone-bottom-nav",
                        children=[
                            _btn(
                                [html.Div(ico, className="tab-icon"), html.Div(lbl)],
                                action,
                                className="tab-btn active" if action == active_key else "tab-btn",
                            )
                            for action, ico, lbl in _t
                        ],
                    ),
                ],
            )
        ],
    )




app.layout = dmc.MantineProvider(
    forceColorScheme="light",
    theme={"fontFamily": "DM Sans, sans-serif", "primaryColor": "yellow"},
    children=html.Div(
        [
            dcc.Store(id="role-store", data=None),
            dcc.Store(id="dador-tab-store", data="cargas_en_viaje"),
            dcc.Store(id="trans-tab-store", data="inicio"),
            dcc.Store(id="viaje-store", data=None),
            dcc.Store(id="hito-store", data=3),
            dcc.Store(id="scoring-input-store", data={}),
            dcc.Store(id="scoring-output-store", data={}),
            dcc.Store(id="doc-foto-store", data=None),
            dcc.Store(id="checklist-store", data={}),  # {hito_num: True} cuando completo
            dcc.Store(id="incident-store", data={}),
            html.Div(id="main-root"),
            dmc.Drawer(
                id="doc-foto-drawer",
                opened=False,
                position="bottom",
                size="90%",
                padding="md",
                withCloseButton=False,
                children=html.Div([
                    html.Div([
                        html.Span(id="doc-foto-titulo", style={"fontWeight": "700", "fontSize": "16px"}),
                        _btn("Cerrar", "doc:foto:close", className="btn-ghost"),
                    ], style={"display": "flex", "justifyContent": "space-between",
                               "alignItems": "center", "marginBottom": "16px"}),
                    html.Div(
                        html.Img(id="doc-foto-img", src="",
                                 style={"width": "100%", "borderRadius": "10px",
                                        "maxHeight": "70vh", "objectFit": "contain"}),
                        style={"textAlign": "center"},
                    ),
                ]),
            ),
            dmc.Drawer(
                id="terms-drawer",
                opened=False,
                position="bottom",
                size="78%",
                padding="lg",
                withCloseButton=False,
                title="Términos y condiciones",
                children=html.Div([
                    html.Div([
                        html.Div("AgroVIA · Términos y condiciones", style={"fontWeight": "800", "fontSize": "20px", "color": "#152515"}),
                        _btn("Cerrar", "terms:close", className="btn-ghost"),
                    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "gap": "12px", "marginBottom": "16px"}),
                    html.Div([
                        *render_terms_content(AGROVIA_TERMINOS)
                    ], style={"maxHeight": "70vh", "overflowY": "auto", "paddingRight": "8px"}),
                ]),
            ),
            dmc.Drawer(
                id="checklist-drawer",
                opened=False,
                position="bottom",
                size="85%",
                padding="lg",
                withCloseButton=False,
                children=html.Div(id="checklist-drawer-content"),
            ),
        ]
    ),
)


@callback(
    Output("role-store",      "data"),
    Output("dador-tab-store", "data"),
    Output("trans-tab-store", "data"),
    Output("viaje-store",     "data"),
    Output("hito-store",      "data"),
    Input({"type": "action-btn", "action": ALL}, "n_clicks"),
    State("role-store",      "data"),
    State("dador-tab-store", "data"),
    State("trans-tab-store", "data"),
    State("viaje-store",     "data"),
    State("hito-store",      "data"),
    State("checklist-store", "data"),
    prevent_initial_call=True,
)
def dispatch_action(_clicks, role, dador_tab, trans_tab, viaje_id, hito_actual, checklist_data):
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return role, dador_tab, trans_tab, viaje_id, hito_actual

    action = triggered.get("action", "")

    if action == "role:transportista":
        return "transportista", dador_tab, "inicio", None, 3
    if action == "role:dador":
        return "dador", "cargas_en_viaje", trans_tab, viaje_id, hito_actual
    if action == "reset-role":
        return None, "cargas_en_viaje", "inicio", None, 3

    if action.startswith("dador:"):
        return role, action.replace("dador:", ""), trans_tab, viaje_id, hito_actual

    if action == "quickpay:open":
        return role, dador_tab, "quickpay_detalle", None, hito_actual

    if action == "hito:advance":
        ha = hito_actual or 3
        # Block advance if any checklist for this hito is not completed
        if not _hito_checklist_done(ha, checklist_data or {}):
            return role, dador_tab, trans_tab, viaje_id, hito_actual
        siguiente = min(ha + 1, 5)
        if siguiente > 4:
            return role, dador_tab, "calificar", None, siguiente
        return role, dador_tab, "en_curso", None, siguiente

    if action == "hito:reset":
        return role, dador_tab, "en_curso", None, 1

    if action.startswith("flow:"):
        parts = action.split(":")
        if len(parts) >= 3:
            flow_action = parts[1]
            viaje_ref = "#" + parts[2]
            viaje = next((v for v in VIAJES if v["id"] == viaje_ref), None)
            if not viaje:
                return role, dador_tab, trans_tab, viaje_id, hito_actual

            tipo = viaje.get("tipo_flujo", "disponible")

            if flow_action == "primary":
                if tipo == "disponible":
                    return role, dador_tab, "viajes", viaje_ref, hito_actual
                if tipo == "en_espera":
                    return role, dador_tab, "viajes", None, hito_actual
                if tipo == "proximo":
                    if viaje.get("documentacion_ok"):
                        return role, dador_tab, "en_curso", None, 1
                    return role, dador_tab, "viajes", viaje_ref, hito_actual
                if tipo == "en_curso":
                    return role, dador_tab, trans_tab, viaje_ref, hito_actual
                if tipo == "oferta_publicada":
                    return role, dador_tab, "publicar", None, hito_actual

            if flow_action == "secondary":
                if tipo in {"disponible", "en_espera", "proximo"}:
                    return role, dador_tab, "viajes", viaje_ref, hito_actual
                if tipo == "en_curso":
                    return role, dador_tab, trans_tab, viaje_ref, hito_actual
                if tipo == "oferta_publicada":
                    return role, dador_tab, "viajes", None, hito_actual

            if flow_action == "gps_origen":
                return role, dador_tab, "viajes", viaje_ref, hito_actual

            if flow_action == "gps_destino":
                return role, dador_tab, "viajes", viaje_ref, hito_actual

    if action == "incidente:report":
        return role, dador_tab, "incidente_reporte", viaje_id, hito_actual

    if action == "incidente:back_en_curso":
        return role, dador_tab, "en_curso", None, hito_actual

    if action.startswith("incidente:"):
        return role, dador_tab, "incidente_reporte", viaje_id, hito_actual

    if action in {"soporte:open", "chat:dador", "viaje:modificar", "viaje:cancelar"}:
        return role, dador_tab, trans_tab, viaje_id, hito_actual

    if action.startswith("calificar:open:"):
        return role, dador_tab, "calificar", "#" + action.replace("calificar:open:", ""), hito_actual

    if action.startswith("tab:"):
        target_tab = action.replace("tab:", "")
        if target_tab == "propuesta":
            target_tab = "viajes"
        if target_tab == "quickpay":
            target_tab = "perfil"
        return role, dador_tab, target_tab, None, hito_actual

    if action == "propuesta:accept":
        return role, dador_tab, "inicio", None, hito_actual
    if action == "propuesta:reject":
        return role, dador_tab, "viajes", None, hito_actual

    if action.startswith("proxviaje:"):
        return role, dador_tab, "inicio", "#" + action.replace("proxviaje:", ""), hito_actual

    if action.startswith("viaje:"):
        return role, dador_tab, "viajes", "#" + action.replace("viaje:", ""), hito_actual

    return role, dador_tab, trans_tab, viaje_id, hito_actual


@callback(
    Output("incident-store", "data"),
    Input({"type": "action-btn", "action": ALL}, "n_clicks"),
    State("incident-store", "data"),
    prevent_initial_call=True,
)
def update_incidente_store(_clicks, incident_data):
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update

    action = triggered.get("action", "")
    data = dict(incident_data or {})

    if action == "incidente:report":
        return {
            "step": 1,
            "cat": "",
            "subopt": "",
            "urgency": "informativo",
            "desc": "",
            "submitted": False,
        }

    if action == "incidente:back_en_curso" or action == "reset-role":
        return {}

    if action.startswith("tab:") and action != "tab:incidente_reporte":
        return {}

    if action.startswith("incidente:step:"):
        try:
            data["step"] = int(action.split(":")[2])
        except Exception:
            data["step"] = 1
        data["submitted"] = False
        return data

    if action.startswith("incidente:cat:"):
        cat = action[len("incidente:cat:"):]
        if cat not in INCIDENTE_CATEGORIAS:
            return dash.no_update
        data.update({"cat": cat, "subopt": "", "urgency": "informativo", "step": 2, "submitted": False})
        return data

    if action.startswith("incidente:opt:"):
        option_id = action[len("incidente:opt:"):]
        cat = str(data.get("cat") or "")
        if cat not in INCIDENTE_CATEGORIAS:
            cat = INCIDENTE_OPCION_A_CATEGORIA.get(option_id, "")
            if not cat:
                return dash.no_update
        valid_ids = {o["id"] for o in INCIDENTE_CATEGORIAS[cat]["opciones"]}
        if option_id not in valid_ids:
            return dash.no_update
        data.update({
            "cat": cat,
            "step": 2,
            "subopt": option_id,
            "urgency": inferir_urgencia_incidente(cat, option_id),
            "submitted": False,
        })
        return data

    if action.startswith("incidente:urg:"):
        urg = action[len("incidente:urg:"):]
        if urg not in INCIDENTE_URGENCIAS:
            return dash.no_update
        data["urgency"] = urg
        data["step"] = 3
        data["submitted"] = False
        return data

    if action == "incidente:submit":
        data["step"] = 5
        data["submitted"] = True
        return data

    return dash.no_update


@callback(
    Output("terms-drawer", "opened"),
    Input({"type": "action-btn", "action": ALL}, "n_clicks"),
    State("terms-drawer", "opened"),
    prevent_initial_call=True,
)
def toggle_terms_drawer(_clicks, opened):
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update

    action = triggered.get("action", "")
    if action == "terms:open":
        return True
    if action == "terms:close":
        return False

    return dash.no_update


@callback(
    Output("checklist-drawer", "opened"),
    Output("checklist-drawer-content", "children"),
    Output("checklist-store", "data"),
    Input({"type": "action-btn", "action": ALL}, "n_clicks"),
    State("checklist-store", "data"),
    State("hito-store", "data"),
    prevent_initial_call=True,
)
def toggle_checklist_drawer(_clicks, checklist_data, hito_actual):
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update, dash.no_update, dash.no_update

    action = triggered.get("action", "")
    cl_data = checklist_data or {}

    def _build_content(cl_id: str, cl_data: dict, is_active: bool) -> html.Div:
        cl_info = _CL_BY_ID.get(cl_id, {})
        es_grano = _es_grano(VIAJE_EN_CURSO.get("carga", ""))
        items = [it for it in cl_info.get("items", []) if not it.get("solo_granos") or es_grano]
        item_key = f"items_{cl_id}"
        marked = cl_data.get(item_key, [])
        item_divs = [
            html.Div([
                html.Span("✓ " if it["id"] in marked else "○ ", style={
                    "color": "#22c55e" if it["id"] in marked else "#c8a84b",
                    "fontWeight": "700", "marginRight": "6px",
                }),
                html.Span(it["texto"], style={"fontSize": "14px"}),
                # Only show Marcar button if hito is active
                *([_btn(
                    "Marcar" if it["id"] not in marked else "✓",
                    f"checklist:item:{cl_id}:{it['id']}",
                    className="btn-ghost",
                    style={"fontSize": "11px", "padding": "2px 8px", "marginLeft": "auto",
                           "color": "#22c55e" if it["id"] in marked else "#c8a84b"},
                )] if is_active else []),
            ], style={"display": "flex", "alignItems": "flex-start", "gap": "4px",
                      "padding": "10px 0", "borderBottom": "1px solid rgba(239,230,209,0.1)"})
            for it in items
        ]
        all_done = len(marked) >= len(items)
        return html.Div([
            html.Div([
                html.Div(cl_info.get("titulo", "Checklist"), style={"fontWeight": "800", "fontSize": "17px", "color": "#152515"}),
                _btn("Cerrar", "checklist:close", className="btn-ghost", style={"color": "#c8a84b"}),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
                      "gap": "12px", "marginBottom": "14px"}),
            html.Div(item_divs, style={"marginBottom": "16px"}),
            # Only show confirm button if hito is active and not all done
            *([_btn("✔ Confirmar checklist completo", f"checklist:confirm:{cl_id}",
                     className="btn-gold-full")] if is_active and not all_done else []),
        ])

    if action.startswith("checklist:open:"):
        cl_id = action[len("checklist:open:"):]
        if cl_id not in _CL_BY_ID:
            return dash.no_update, dash.no_update, dash.no_update
        # Find which hito this cl belongs to
        hito_num = next(
            (h for h, cls in CHECKLIST_POR_HITO.items() if any(c["id"] == cl_id for c in cls)),
            None,
        )
        is_active = hito_num == hito_actual
        return True, _build_content(cl_id, cl_data, is_active), dash.no_update

    if action == "checklist:close":
        return False, dash.no_update, cl_data

    if action.startswith("checklist:item:"):
        parts = action.split(":")
        # format: checklist:item:{cl_id}:{item_id}  — cl_id may not contain ':'
        cl_id = parts[2]
        item_id = parts[3]
        item_key = f"items_{cl_id}"
        marked = list(cl_data.get(item_key, []))
        if item_id not in marked:
            marked.append(item_id)
        cl_data = {**cl_data, item_key: marked}
        # Find hito num to check if active
        hito_num = next(
            (h for h, cls in CHECKLIST_POR_HITO.items() if any(c["id"] == cl_id for c in cls)),
            None,
        )
        is_active = hito_num == hito_actual
        return True, _build_content(cl_id, cl_data, is_active), cl_data

    if action.startswith("checklist:confirm:"):
        cl_id = action[len("checklist:confirm:"):]
        cl_info = _CL_BY_ID.get(cl_id, {})
        es_grano = _es_grano(VIAJE_EN_CURSO.get("carga", ""))
        items = [it for it in cl_info.get("items", []) if not it.get("solo_granos") or es_grano]
        item_key = f"items_{cl_id}"
        cl_data = {**cl_data, item_key: [it["id"] for it in items], cl_id: True}
        return False, dash.no_update, cl_data

    return dash.no_update, dash.no_update, dash.no_update


_DOC_NOMBRE_BY_IMG = {
    d["imagen"]: d["nombre"]
    for d in [*DOCS_CAMION, *DOCS_CONDUCTOR]
    if d.get("imagen")
}


@callback(
    Output("doc-foto-drawer", "opened"),
    Output("doc-foto-img", "src"),
    Output("doc-foto-titulo", "children"),
    Input({"type": "action-btn", "action": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def toggle_doc_foto_drawer(_clicks):
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update, dash.no_update, dash.no_update

    action = triggered.get("action", "")
    if action == "doc:foto:close":
        return False, dash.no_update, dash.no_update
    if action.startswith("doc:foto:/"):
        src = action.replace("doc:foto:", "", 1)
        titulo = _DOC_NOMBRE_BY_IMG.get(src, "Documento")
        return True, src, titulo

    return dash.no_update, dash.no_update, dash.no_update


@callback(
    Output("matching-total-display", "children"),
    Output("matching-total-alert", "children"),
    Output("matching-total-alert", "style"),
    Output("publish-new-load-button", "disabled"),
    Input("matching-eficiencia", "value"),
    Input("matching-ocupacion", "value"),
    Input("matching-reputacion", "value"),
    prevent_initial_call=False,
)
def validate_matching_parameters(eficiencia, ocupacion, reputacion):
    eficiencia = int(eficiencia or 0)
    ocupacion = max(int(ocupacion or 25), 25)
    reputacion = int(reputacion or 0)

    total = eficiencia + ocupacion + reputacion
    is_valid = total == 100

    total_label = f"Suma total de parámetros: {total}%"
    if is_valid:
        return (
            total_label,
            "Configuración válida. Ya podés confirmar la publicación.",
            {"marginTop": "4px", "marginBottom": "8px", "color": "#166534", "fontWeight": "700"},
            False,
        )

    return (
        total_label,
        "La suma debe ser exactamente 100%. Ajustá los porcentajes para confirmar.",
        {"marginTop": "4px", "marginBottom": "8px", "color": "#b91c1c", "fontWeight": "700"},
        True,
    )


@callback(
    Output("matching-manual-panel", "style"),
    Input("matching-manual-toggle", "checked"),
    prevent_initial_call=False,
)
def toggle_matching_manual_panel(checked):
    if checked:
        return {"display": "block", "marginBottom": "6px"}
    return {"display": "none", "marginBottom": "6px"}


@callback(
    Output("scoring-input-store", "data"),
    Input("role-store", "data"),
    Input("trans-tab-store", "data"),
    Input("hito-store", "data"),
    prevent_initial_call=False,
)
def build_scoring_input(role, _trans_tab, hito_actual):
    if role != "transportista":
        return {}

    # Baseline v1; luego se puede reemplazar por eventos reales del backend.
    return {
        # H — Historial operativo
        "viajes_ok_ratio": 0.92,
        "puntualidad_ratio": 0.88,
        "ruta_gps_ratio": 0.94,
        "eventos_app_ratio": 0.96 if (hito_actual or 0) >= 3 else 0.85,
        "factor_recencia_h": 1.0,
        # C — Calificación de dadores
        "cal_cumplimiento": 4.0,
        "cal_comunicacion": 4.2,
        "cal_vehiculo_percibido": 4.1,
        # V — Estado del vehículo
        "anios_camion": 6,
        "tipo_unidad": "semirremolque",
        "incidentes_mecanicos": 0,
        "rto_historial": "sin_obs",
        # R — Recencia y actividad
        "viajes_ultimos_90d": len(HISTORIAL_TRANS),
        "ritmo_consistente": 0.78,
        "dias_sin_viaje": 1,
        # Elegibilidad QP
        "viajes_completados_total": len(HISTORIAL_TRANS),
        "penalizaciones": [],
        "bonificaciones": [{"nombre": "racha_operativa", "puntos": 3}],
        "n_viajes_relevantes": len(HISTORIAL_TRANS),
        "k_bayes": 10,
        "score_base_mercado": 65,
        "trend_points_7d": 3,
    }


@callback(
    Output("scoring-output-store", "data"),
    Input("scoring-input-store", "data"),
    prevent_initial_call=False,
)
def compute_scoring_output(payload):
    if not payload:
        return {}
    try:
        return calcular_score_desde_dash_payload(payload)
    except Exception:
        return {}


@callback(
    Output("main-root", "children"),
    Input("role-store",      "data"),
    Input("dador-tab-store", "data"),
    Input("trans-tab-store", "data"),
    Input("viaje-store",     "data"),
    Input("hito-store",      "data"),
    Input("scoring-output-store", "data"),
    Input("checklist-store", "data"),
    Input("incident-store", "data"),
)
def render_app(role, dador_tab, trans_tab, viaje_id, hito_actual, scoring_output, checklist_data, incident_data):
    if not role:
        return role_selector_layout()

    return html.Div(
        className="root-shell",
        children=[
            _btn("Cambiar rol", "reset-role", className="floating-left"),
            transportista_layout(trans_tab, viaje_id, hito_actual, scoring_output, checklist_data, incident_data) if role == "transportista" else dador_layout(dador_tab),
        ],
    )


if __name__ == "__main__":
    app.run(debug=False)
