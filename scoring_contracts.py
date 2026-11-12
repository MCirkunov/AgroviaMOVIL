"""Contratos de entrada/salida para integrar scoring V1 con Dash.

Define estructuras simples para callbacks y adaptadores hacia/desde
el motor puro de scoring en dominio.scoring_v1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from dominio.scoring_v1 import (
    BonificacionActiva,
    PenalizacionActiva,
    ScoreBreakdownV1,
    ScoringInputV1,
    calcular_score_v1,
)


def _safe_pct(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "si", "sÃ­", "ok", "yes"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


@dataclass(frozen=True)
class DashScoringRequest:
    """Request de callback para calcular Score_T y Score_QP del transportista.

    H  viajes_ok_ratio Â· puntualidad_ratio Â· ruta_gps_ratio Â· eventos_app_ratio
    C  cal_cumplimiento Â· cal_comunicacion Â· cal_vehiculo_percibido  (1..5)
    V  anios_camion Â· tipo_unidad Â· incidentes_mecanicos Â· rto_historial
    R  viajes_ultimos_90d Â· ritmo_consistente Â· dias_sin_viaje
    """

    # H â€” Historial operativo (0..1 cada uno)
    viajes_ok_ratio: float = 0.0
    puntualidad_ratio: float = 0.0
    ruta_gps_ratio: float = 0.0
    eventos_app_ratio: float = 0.0
    factor_recencia_h: float = 1.0

    # C â€” CalificaciÃ³n de dadores (1..5)
    cal_cumplimiento: float = 3.0
    cal_comunicacion: float = 3.0
    cal_vehiculo_percibido: float = 3.0

    # V â€” Estado del vehÃ­culo
    anios_camion: int = 5
    tipo_unidad: str = "semirremolque"
    incidentes_mecanicos: int = 0
    rto_historial: str = "sin_obs"

    # R â€” Recencia
    viajes_ultimos_90d: int = 0
    ritmo_consistente: float = 0.5
    dias_sin_viaje: int = 0

    # Elegibilidad QP
    viajes_completados_total: int = 0

    # Ajustes temporales (Score_QP)
    penalizaciones: List[Dict[str, Any]] = field(default_factory=list)
    bonificaciones: List[Dict[str, Any]] = field(default_factory=list)

    # Anti-gaming
    n_viajes_relevantes: int = 0
    k_bayes: int = 10
    score_base_mercado: float = 65.0


def request_from_dash_payload(payload: Dict[str, Any]) -> DashScoringRequest:
    """Normaliza un dict de Dash a DashScoringRequest."""
    return DashScoringRequest(
        viajes_ok_ratio=_safe_pct(payload.get("viajes_ok_ratio")),
        puntualidad_ratio=_safe_pct(payload.get("puntualidad_ratio")),
        ruta_gps_ratio=_safe_pct(payload.get("ruta_gps_ratio")),
        eventos_app_ratio=_safe_pct(payload.get("eventos_app_ratio")),
        factor_recencia_h=_safe_pct(payload.get("factor_recencia_h"), default=1.0),
        cal_cumplimiento=_safe_pct(payload.get("cal_cumplimiento"), default=3.0),
        cal_comunicacion=_safe_pct(payload.get("cal_comunicacion"), default=3.0),
        cal_vehiculo_percibido=_safe_pct(payload.get("cal_vehiculo_percibido"), default=3.0),
        anios_camion=_safe_int(payload.get("anios_camion"), default=5),
        tipo_unidad=_safe_str(payload.get("tipo_unidad"), default="semirremolque"),
        incidentes_mecanicos=_safe_int(payload.get("incidentes_mecanicos")),
        rto_historial=_safe_str(payload.get("rto_historial"), default="sin_obs"),
        viajes_ultimos_90d=_safe_int(payload.get("viajes_ultimos_90d")),
        ritmo_consistente=_safe_pct(payload.get("ritmo_consistente"), default=0.5),
        dias_sin_viaje=_safe_int(payload.get("dias_sin_viaje")),
        viajes_completados_total=_safe_int(payload.get("viajes_completados_total")),
        penalizaciones=list(payload.get("penalizaciones", []) or []),
        bonificaciones=list(payload.get("bonificaciones", []) or []),
        n_viajes_relevantes=_safe_int(payload.get("n_viajes_relevantes")),
        k_bayes=max(1, _safe_int(payload.get("k_bayes"), default=10)),
        score_base_mercado=_safe_pct(payload.get("score_base_mercado"), default=65.0),
    )


def _to_penalizaciones(items: List[Dict[str, Any]]) -> List[PenalizacionActiva]:
    return [
        PenalizacionActiva(
            nombre=str(it.get("nombre", "penalizacion")),
            puntos=max(0.0, _safe_pct(it.get("puntos"))),
        )
        for it in items
    ]


def _to_bonificaciones(items: List[Dict[str, Any]]) -> List[BonificacionActiva]:
    return [
        BonificacionActiva(
            nombre=str(it.get("nombre", "bonificacion")),
            puntos=max(0.0, _safe_pct(it.get("puntos"))),
        )
        for it in items
    ]


def build_scoring_input_v1(req: DashScoringRequest) -> ScoringInputV1:
    """Convierte DashScoringRequest a ScoringInputV1 del motor."""
    return ScoringInputV1(
        viajes_ok_ratio=_safe_pct(req.viajes_ok_ratio, 0.0),
        puntualidad_ratio=_safe_pct(req.puntualidad_ratio, 0.0),
        ruta_gps_ratio=_safe_pct(req.ruta_gps_ratio, 0.0),
        eventos_app_ratio=_safe_pct(req.eventos_app_ratio, 0.0),
        factor_recencia_h=_safe_pct(req.factor_recencia_h, 1.0),
        cal_cumplimiento=max(1.0, min(5.0, req.cal_cumplimiento)),
        cal_comunicacion=max(1.0, min(5.0, req.cal_comunicacion)),
        cal_vehiculo_percibido=max(1.0, min(5.0, req.cal_vehiculo_percibido)),
        anios_camion=max(0, req.anios_camion),
        tipo_unidad=req.tipo_unidad,
        incidentes_mecanicos=max(0, req.incidentes_mecanicos),
        rto_historial=req.rto_historial,
        viajes_ultimos_90d=max(0, req.viajes_ultimos_90d),
        ritmo_consistente=_safe_pct(req.ritmo_consistente, 0.5),
        dias_sin_viaje=max(0, req.dias_sin_viaje),
        viajes_completados_total=max(0, req.viajes_completados_total),
        penalizaciones_activas=_to_penalizaciones(req.penalizaciones),
        bonificaciones_activas=_to_bonificaciones(req.bonificaciones),
        n_viajes_relevantes=max(0, req.n_viajes_relevantes),
        k_bayes=max(1, req.k_bayes),
        score_base_mercado=req.score_base_mercado,
    )


def score_to_dash_payload(res: ScoreBreakdownV1) -> Dict[str, Any]:
    """Transforma el resultado en un payload simple para dcc.Store/UI."""
    return {
        "score_final": round(res.score_t, 2),
        "score_qp": round(res.score_qp, 2),
        "tier": res.tier,
        "quickpay_habilitado": res.quickpay_habilitado,
        "quickpay_pct": round(res.quickpay_pct * 100.0, 1),
        "subscores": {
            "historial":    round(res.h_pct, 2),
            "calificacion": round(res.c_pct, 2),
            "vehiculo":     round(res.v_pct, 2),
            "recencia":     round(res.r_pct, 2),
        },
        "pipeline": {
            "score_t":              round(res.score_t, 2),
            "score_qp_base":        round(res.score_qp_base, 2),
            "score_qp":             round(res.score_qp, 2),
            "total_bonos":          round(res.total_bonos, 2),
            "total_penalizaciones": round(res.total_penalizaciones, 2),
            "caps_aplicados":       [],   # docs son filtro duro pre-matching, no caps
            "suspendido":           res.suspendido,
        },
        "ui_messages": {
            "tier_label":    f"Tier {res.tier}",
            "quickpay_label": "Quick-Pay habilitado" if res.quickpay_habilitado else "Quick-Pay no habilitado",
            "score_label":   f"Score_T: {round(res.score_t, 1)} / 100",
            "score_qp_label": f"Score_QP: {round(res.score_qp, 1)} / 100",
        },
    }


def calcular_score_desde_dash_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Atajo end-to-end para usar directo dentro de callbacks."""
    req = request_from_dash_payload(payload)
    engine_input = build_scoring_input_v1(req)
    result = calcular_score_v1(engine_input)
    return score_to_dash_payload(result)
