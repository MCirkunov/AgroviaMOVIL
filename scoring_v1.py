"""Motor de scoring V1 para matching y Quick-Pay â€” Transportista.

Dos scores distintos con los mismos 4 componentes:

  Score_T  = 0.45Â·H + 0.20Â·C + 0.20Â·V + 0.15Â·R  â†’ matching + tier
  Score_QP = 0.40Â·H + 0.25Â·V + 0.20Â·R + 0.15Â·C + bonos âˆ’ penalizaciones â†’ % adelanto QP

Tabla Quick-Pay (Score_QP):
    < 5 viajes completados            â†’ sin QP (mÃ­nimo obligatorio)
    QP < 41                           â†’ sin QP
    41â€“55  Â· usuario nuevo            â†’ 50%
    56â€“70  Â· en consolidaciÃ³n         â†’ 60%
    71â€“84  Â· usuario confiable        â†’ 70%
    85â€“100 Â· usuario destacado        â†’ 80%

DocumentaciÃ³n (RTO, seguro, ART, cÃ©dula) es filtro duro pre-matching,
NO es componente de scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _stars_to_ratio(stars: float) -> float:
    """Convierte estrellas 1..5 a ratio 0..1 usando escala (stars-1)/4."""
    return _clip((float(stars) - 1.0) / 4.0, 0.0, 1.0)


@dataclass(frozen=True)
class PenalizacionActiva:
    nombre: str
    puntos: float


@dataclass(frozen=True)
class BonificacionActiva:
    nombre: str
    puntos: float


@dataclass(frozen=True)
class ScoringInputV1:
    # H â€” Historial operativo (4 sub-variables, ratio 0..1)
    viajes_ok_ratio: float          # viajes_ok / total_aceptados
    puntualidad_ratio: float        # % llegadas en ventana horaria
    ruta_gps_ratio: float           # % sin desvÃ­o GPS ni paradas injustificadas
    eventos_app_ratio: float        # % hitos registrados correctamente en app
    factor_recencia_h: float = 1.0  # ventana deslizante promedio (0..1); default sin penalizaciÃ³n

    # C â€” CalificaciÃ³n de dadores (escala 1..5)
    cal_cumplimiento: float = 3.0           # Cumplimiento operativo (8 pts max)
    cal_comunicacion: float = 3.0           # ComunicaciÃ³n y transparencia (6 pts max)
    cal_vehiculo_percibido: float = 3.0     # Estado vehÃ­culo percibido (6 pts max)

    # V â€” Estado del vehÃ­culo (datos objetivos CNRT)
    anios_camion: int = 5
    tipo_unidad: str = "semirremolque"   # "semirremolque"|"batea"|"menor"|"otro"
    incidentes_mecanicos: int = 0        # 0|1|2|â‰¥3
    rto_historial: str = "sin_obs"       # "sin_obs"|"menores"|"graves"

    # R â€” Recencia y actividad
    viajes_ultimos_90d: int = 0
    ritmo_consistente: float = 0.5   # distribuciÃ³n en el perÃ­odo, 0..1
    dias_sin_viaje: int = 0

    # Elegibilidad Quick-Pay
    viajes_completados_total: int = 0

    # Ajustes temporales (aplicados sÃ³lo sobre Score_QP)
    penalizaciones_activas: List[PenalizacionActiva] = field(default_factory=list)
    bonificaciones_activas: List[BonificacionActiva] = field(default_factory=list)

    # Anti-gaming / suavizado bayesiano
    n_viajes_relevantes: int = 0
    k_bayes: int = 10
    score_base_mercado: float = 65.0


@dataclass(frozen=True)
class ScoreBreakdownV1:
    # Componentes en puntos (sobre mÃ¡ximo de cada uno)
    h_pts: float    # 0..45
    c_pts: float    # 0..20
    v_pts: float    # 0..20
    r_pts: float    # 0..15

    # Mismos componentes en % (0..100)
    h_pct: float
    c_pct: float
    v_pct: float
    r_pct: float

    # Scores
    score_t: float          # Score_T = h+c+v+r pts suavizado (0..100)
    score_qp_base: float    # Score_QP antes de ajustes
    score_qp: float         # Score_QP con ajustes

    total_bonos: float
    total_penalizaciones: float

    # Quick-Pay
    quickpay_habilitado: bool
    quickpay_pct: float     # 0.50 | 0.60 | 0.70 | 0.80 | 0.0

    # Campos de compatibilidad con el resto de la app
    score_final: float      # = score_t
    tier: str               # A/B/C/D/E
    suspendido: bool


# â”€â”€ Sub-score H â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def calcular_h(
    viajes_ok_ratio: float,
    puntualidad_ratio: float,
    ruta_gps_ratio: float,
    eventos_app_ratio: float,
    factor_recencia: float = 1.0,
) -> Tuple[float, float]:
    """H â€” Historial operativo. Max 45 pts.

    Sub-variables: completados 16 Â· puntualidad 14 Â· ruta GPS 9 Â· eventos app 6.
    factor_recencia: ventana deslizante (1.0 = sin penalizaciÃ³n por antigÃ¼edad).
    Retorna (h_pts, h_pct).
    """
    vo = _clip(viajes_ok_ratio, 0.0, 1.0)
    pt = _clip(puntualidad_ratio, 0.0, 1.0)
    rg = _clip(ruta_gps_ratio, 0.0, 1.0)
    ev = _clip(eventos_app_ratio, 0.0, 1.0)
    fr = _clip(factor_recencia, 0.0, 1.0)

    bruto = vo * 16.0 + pt * 14.0 + rg * 9.0 + ev * 6.0   # 0..45
    h_pts = _clip(bruto * fr, 0.0, 45.0)
    h_pct = (h_pts / 45.0) * 100.0
    return h_pts, h_pct


# â”€â”€ Sub-score C â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def calcular_c(
    cal_cumplimiento: float,
    cal_comunicacion: float,
    cal_vehiculo_percibido: float,
) -> Tuple[float, float]:
    """C â€” CalificaciÃ³n de dadores. Max 20 pts.

    Pesos: cumplimiento 8, comunicaciÃ³n 6, vehÃ­culo percibido 6.
    Escala: (stars - 1) / 4 Ã— max_pts.
    Retorna (c_pts, c_pct).
    """
    r1 = _stars_to_ratio(cal_cumplimiento)
    r2 = _stars_to_ratio(cal_comunicacion)
    r3 = _stars_to_ratio(cal_vehiculo_percibido)
    c_pts = _clip(r1 * 8.0 + r2 * 6.0 + r3 * 6.0, 0.0, 20.0)
    c_pct = (c_pts / 20.0) * 100.0
    return c_pts, c_pct


# â”€â”€ Sub-score V â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _pts_antiguedad(anios: int) -> float:
    if anios <= 5:   return 7.0
    if anios <= 10:  return 5.0
    if anios <= 15:  return 3.0
    if anios <= 20:  return 1.0
    return 0.0


def _pts_tipo_unidad(tipo: str) -> float:
    t = (tipo or "").lower()
    if "semirremolque" in t or "tolva" in t: return 4.0
    if "batea" in t:                          return 3.0
    if "menor" in t:                          return 2.0
    return 0.0


def _pts_incidentes_mecanicos(n: int) -> float:
    if n == 0: return 4.0
    if n == 1: return 3.0
    if n == 2: return 2.0
    return 0.0


def _pts_rto_historial(estado: str) -> float:
    e = (estado or "").lower().strip()
    if e in {"sin_obs", "sin observaciones"}: return 5.0
    if e == "menores":                         return 2.0
    return 0.0


def calcular_v(
    anios_camion: int,
    tipo_unidad: str,
    incidentes_mecanicos: int,
    rto_historial: str,
) -> Tuple[float, float]:
    """V â€” Estado del vehÃ­culo (datos objetivos CNRT/padrÃ³n). Max 20 pts.

    antigÃ¼edad 7 + tipo unidad 4 + incidentes mecÃ¡nicos 4 + RTO historial 5.
    Retorna (v_pts, v_pct).
    """
    v_pts = (
        _pts_antiguedad(anios_camion)
        + _pts_tipo_unidad(tipo_unidad)
        + _pts_incidentes_mecanicos(incidentes_mecanicos)
        + _pts_rto_historial(rto_historial)
    )
    v_pts = _clip(v_pts, 0.0, 20.0)
    v_pct = (v_pts / 20.0) * 100.0
    return v_pts, v_pct


# â”€â”€ Sub-score R â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _factor_degradacion(dias: int) -> float:
    """Factor de inactividad: afecta SOLO a R, nunca a H."""
    d = max(0, int(dias))
    if d <= 30:  return 1.00
    if d <= 60:  return 0.95
    if d <= 90:  return 0.85
    if d <= 120: return 0.70
    if d <= 180: return 0.55
    return 0.40


def _pts_volumen_90d(n: int) -> float:
    if n == 0:  return 0.0
    if n <= 2:  return 4.0
    if n <= 5:  return 8.0
    if n <= 10: return 11.0
    return 15.0


def calcular_r(
    viajes_ultimos_90d: int,
    ritmo_consistente: float,
    dias_sin_viaje: int,
) -> Tuple[float, float]:
    """R â€” Recencia y actividad. Max 15 pts (normalizado desde base 25).

    Volumen 90d (max 15) + ritmo (max 10) = R_base (max 25) â†’ normalizado a 15.
    DegradaciÃ³n por inactividad aplicada sobre R_base.
    Retorna (r_pts, r_pct).
    """
    vol_pts   = _pts_volumen_90d(viajes_ultimos_90d)
    ritmo_pts = _clip(float(ritmo_consistente), 0.0, 1.0) * 10.0
    r_base    = vol_pts + ritmo_pts           # 0..25
    factor    = _factor_degradacion(dias_sin_viaje)
    r_degradado = r_base * factor             # 0..25

    r_pts = _clip((r_degradado / 25.0) * 15.0, 0.0, 15.0)
    r_pct = (r_pts / 15.0) * 100.0 if r_pts > 0 else 0.0
    return r_pts, r_pct


# â”€â”€ Score_T â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def calcular_score_t(h_pts: float, c_pts: float, v_pts: float, r_pts: float) -> float:
    """Score_T = H + C + V + R en puntos (max 100).

    Equivale a: 0.45Â·H_pct + 0.20Â·C_pct + 0.20Â·V_pct + 0.15Â·R_pct.
    """
    return _clip(h_pts + c_pts + v_pts + r_pts)


# â”€â”€ Score_QP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def calcular_score_qp(
    h_pct: float,
    c_pct: float,
    v_pct: float,
    r_pct: float,
    penalizaciones_activas: List[PenalizacionActiva],
    bonificaciones_activas: List[BonificacionActiva],
) -> Tuple[float, float, float, float]:
    """Score_QP = 0.40Â·H + 0.25Â·V + 0.20Â·R + 0.15Â·C + bonos âˆ’ penalizaciones.

    Retorna (score_qp_base, score_qp, total_bonos, total_penalizaciones).
    """
    base = (
        0.40 * _clip(h_pct)
        + 0.25 * _clip(v_pct)
        + 0.20 * _clip(r_pct)
        + 0.15 * _clip(c_pct)
    )
    total_bonos = sum(max(0.0, b.puntos) for b in bonificaciones_activas)
    total_pens  = sum(max(0.0, p.puntos) for p in penalizaciones_activas)
    qp = _clip(base + total_bonos - total_pens)
    return base, qp, total_bonos, total_pens


# â”€â”€ Tabla Quick-Pay â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def asignar_quickpay(qp_score: float, viajes_completados: int) -> Tuple[bool, float]:
    """Asigna habilitaciÃ³n y porcentaje de adelanto segÃºn Score_QP.

    Tabla oficial (documento AgroVIA v2):
        < 5 viajes                    â†’ False, 0.0
        QP < 41                       â†’ False, 0.0
        41â€“55 Â· usuario nuevo         â†’ True, 0.50
        56â€“70 Â· en consolidaciÃ³n      â†’ True, 0.60
        71â€“84 Â· usuario confiable     â†’ True, 0.70
        85â€“100 Â· usuario destacado    â†’ True, 0.80
    """
    if viajes_completados < 5:
        return False, 0.0
    s = _clip(qp_score)
    if s < 41.0:  return False, 0.0
    if s <= 55.0: return True, 0.50
    if s <= 70.0: return True, 0.60
    if s <= 84.0: return True, 0.70
    return True, 0.80


# â”€â”€ Tier (basado en Score_T, alineado con rangos QP) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def asignar_tier(score_t: float) -> str:
    """Tier del transportista basado en Score_T."""
    s = _clip(score_t)
    if s >= 85.0: return "A"
    if s >= 71.0: return "B"
    if s >= 56.0: return "C"
    if s >= 41.0: return "D"
    return "E"


# â”€â”€ Suavizado bayesiano â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def suavizar_score_bayes(score: float, n_viajes: int, k: int = 10, score_base: float = 65.0) -> float:
    """Estabiliza el score cuando hay pocos viajes acumulados."""
    n  = max(0, int(n_viajes))
    kk = max(1, int(k))
    return _clip((n / (n + kk)) * _clip(score) + (kk / (n + kk)) * _clip(score_base))


# â”€â”€ Pipeline completo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def calcular_score_v1(inp: ScoringInputV1) -> ScoreBreakdownV1:
    """Pipeline completo: H Â· C Â· V Â· R â†’ Score_T + Score_QP â†’ QP table â†’ tier."""
    h_pts, h_pct = calcular_h(
        inp.viajes_ok_ratio,
        inp.puntualidad_ratio,
        inp.ruta_gps_ratio,
        inp.eventos_app_ratio,
        inp.factor_recencia_h,
    )
    c_pts, c_pct = calcular_c(
        inp.cal_cumplimiento,
        inp.cal_comunicacion,
        inp.cal_vehiculo_percibido,
    )
    v_pts, v_pct = calcular_v(
        inp.anios_camion,
        inp.tipo_unidad,
        inp.incidentes_mecanicos,
        inp.rto_historial,
    )
    r_pts, r_pct = calcular_r(
        inp.viajes_ultimos_90d,
        inp.ritmo_consistente,
        inp.dias_sin_viaje,
    )

    score_t_raw = calcular_score_t(h_pts, c_pts, v_pts, r_pts)
    score_t = suavizar_score_bayes(
        score_t_raw,
        n_viajes=inp.n_viajes_relevantes,
        k=inp.k_bayes,
        score_base=inp.score_base_mercado,
    )

    score_qp_base, score_qp_raw, total_bonos, total_pens = calcular_score_qp(
        h_pct, c_pct, v_pct, r_pct,
        inp.penalizaciones_activas,
        inp.bonificaciones_activas,
    )
    # Score_QP también se suaviza con el mismo factor bayesiano que Score_T
    # para que ambos scores sean comparables cuando hay pocos viajes.
    score_qp = suavizar_score_bayes(
        score_qp_raw,
        n_viajes=inp.n_viajes_relevantes,
        k=inp.k_bayes,
        score_base=inp.score_base_mercado,
    )

    qp_hab, qp_pct = asignar_quickpay(score_qp, inp.viajes_completados_total)
    tier = asignar_tier(score_t)

    return ScoreBreakdownV1(
        h_pts=h_pts,
        c_pts=c_pts,
        v_pts=v_pts,
        r_pts=r_pts,
        h_pct=h_pct,
        c_pct=c_pct,
        v_pct=v_pct,
        r_pct=r_pct,
        score_t=score_t,
        score_qp_base=score_qp_base,
        score_qp=score_qp,
        total_bonos=total_bonos,
        total_penalizaciones=total_pens,
        quickpay_habilitado=qp_hab,
        quickpay_pct=qp_pct,
        score_final=score_t,
        tier=tier,
        suspendido=False,
    )
