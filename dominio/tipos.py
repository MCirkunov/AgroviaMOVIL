"""Tipos de resultados del simulador."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FlujosMensuales:
    """Viajes capturados y métricas por mes."""

    mes: int
    anio: int
    tipoA_arcs: List[dict] = field(default_factory=list)
    tipoB_arcs: List[dict] = field(default_factory=list)
    tipoC_arcs: List[dict] = field(default_factory=list)
    prov_summary: Dict[str, dict] = field(default_factory=dict)
    viajes_base: float = 0.0
    viajes_interp: float = 0.0
    monto_facturado: float = 0.0
    co2_tn: float = 0.0


@dataclass
class ResultadoAnual:
    """Resultado financiero y operativo de un año."""

    anio: int
    exportacion_mt: float
    viajes_matching_potenciales: float
    viajes_base: float
    viajes_interp: float
    viajes_total: float
    tarifa_prom: float
    monto_facturado: float
    monto_adelantado: float
    ingreso_qp: float
    adopcion: float
    qp_pct: float
    adelanto_pct: float
    fee_agrovia: float
    costo_rrhh: float
    costo_aws: float
    costo_aws_detail: dict
    costo_equipos_compra: float
    costo_equipos_amort: float
    costo_software_amort: float
    costo_promo: float
    costo_legal: float
    costo_opex_extra: float
    costo_app_store: float
    costo_opex_extra_detail: dict
    costos_totales: float
    ganancia_antes_imp: float
    impuesto: float
    flujo_neto: float
    flujo_descontado: float
    flujo_acumulado: float
    co2_tn: float
    personas: float
    valor_residual_equipos: float = 0.0
    camioneros_disponibles: Optional[int] = None
    camioneros_requeridos_pico: Optional[int] = None
    utilizacion_flotilla_pico_pct: Optional[float] = None


@dataclass
class ResultadoSimulacion:
    """Resultado completo de una simulación."""

    years: List[ResultadoAnual]
    van: float
    tir: float
    payback: Optional[int]
    co2_total: float
    inversion_y0: float