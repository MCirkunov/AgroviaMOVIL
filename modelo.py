"""Fachada pública del dominio del simulador AgroVIA."""

from dominio.calculos import calc_dlp, calc_tir, haversine, lookup_aws, lookup_rrhh, tarifa_fadeeac, viajes_mes
from dominio.constantes import ADOPTION_CURVE, ADELANTO_PCT, PROD_BY_YEAR, QP_TABLE, ROSARIO_LAT, ROSARIO_LNG
from dominio.datos import cargar_datos, clasificar_flujos
from dominio.simulador import ejecutar_simulacion, calcular_arcos_mes
from dominio.tipos import FlujosMensuales, ResultadoAnual, ResultadoSimulacion

MonthlyFlows = FlujosMensuales
SimulationResult = ResultadoSimulacion
YearResult = ResultadoAnual

load_data = cargar_datos
classify_flows = clasificar_flujos
run_simulation = ejecutar_simulacion
get_monthly_arcs = calcular_arcos_mes

__all__ = [
    "ADOPTION_CURVE",
    "ADELANTO_PCT",
    "FlujosMensuales",
    "MonthlyFlows",
    "PROD_BY_YEAR",
    "QP_TABLE",
    "ROSARIO_LAT",
    "ROSARIO_LNG",
    "ResultadoAnual",
    "ResultadoSimulacion",
    "SimulationResult",
    "YearResult",
    "calc_dlp",
    "calc_tir",
    "cargar_datos",
    "classify_flows",
    "clasificar_flujos",
    "ejecutar_simulacion",
    "haversine",
    "load_data",
    "lookup_aws",
    "lookup_rrhh",
    "run_simulation",
    "tarifa_fadeeac",
    "viajes_mes",
]