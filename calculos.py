"""Funciones auxiliares de cálculo y pricing del simulador."""

from typing import List, Tuple

import numpy as np
import pandas as pd

from dominio.constantes import AWS_LOOKUP, RRHH_LOOKUP


def haversine(lat1, lon1, lat2, lon2) -> float:
    radius = 6371.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return float(2 * radius * np.arctan2(np.sqrt(a), np.sqrt(1 - a)))


def tarifa_fadeeac(km: float, tar_kms: np.ndarray, tar_ars: np.ndarray) -> float:
    if km <= 0:
        return 0.0
    if km <= tar_kms[0]:
        return float(tar_ars[0])
    if km >= tar_kms[-1]:
        return float(tar_ars[-1])
    idx = np.searchsorted(tar_kms, km) - 1
    k0, k1 = tar_kms[idx], tar_kms[idx + 1]
    a0, a1 = tar_ars[idx], tar_ars[idx + 1]
    return float(a0 + (a1 - a0) * (km - k0) / (k1 - k0))


def lookup_rrhh(viajes: float) -> Tuple[float, float]:
    result = RRHH_LOOKUP[0]
    for row in RRHH_LOOKUP:
        if viajes >= row[0]:
            result = row
    return result[1], result[2]


def lookup_aws(viajes: float) -> dict:
    result = AWS_LOOKUP[0][1]
    for desde, data in AWS_LOOKUP:
        if viajes >= desde:
            result = data
    return result


def calc_tir(flujos: List[float]) -> float:
    def npv(rate, flows):
        return sum(flow / (1 + rate) ** period for period, flow in enumerate(flows))

    def dnpv(rate, flows):
        return sum(-period * flow / (1 + rate) ** (period + 1) for period, flow in enumerate(flows))

    rate = 0.1
    for _ in range(200):
        value = npv(rate, flujos)
        derivative = dnpv(rate, flujos)
        if abs(derivative) < 1e-12:
            break
        rate = rate - value / derivative
        if rate < -0.999:
            rate = -0.999
    return rate


def viajes_mes(ton: float, tn_camion: float, escala: float, estac: dict, mes: int) -> float:
    fe = estac.get(mes, 0.0)
    total_fe = sum(estac.values())
    if total_fe == 0 or fe == 0:
        return 0.0
    return (ton / tn_camion) * escala * (fe / total_fe)


def calc_dlp(prov: str, mes: int, tipoA: pd.DataFrame, tipoB: pd.DataFrame, data: dict, escala: float) -> float:
    conv = data["conv"]
    estac = data["estac"]

    oferta = 0.0
    for _, row in tipoA[tipoA["origen_prov"] == prov].iterrows():
        prod = row["producto"]
        oferta += viajes_mes(row["ton"], conv.get(prod, 15), escala, estac.get(prod, {}), mes)

    demanda = 0.0
    for _, row in tipoB[tipoB["dest_prov"] == prov].iterrows():
        prod = row["producto"]
        demanda += viajes_mes(row["ton"], conv.get(prod, 15), escala, estac.get(prod, {}), mes)

    ltr = 1.0 if oferta == 0 else demanda / oferta
    if ltr > 1.20:
        factor_ltr = 1.10
    elif ltr < 0.80:
        factor_ltr = 0.92
    else:
        factor_ltr = 1.00

    return factor_ltr * 0.92