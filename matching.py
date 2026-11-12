"""Lógica reutilizable de matching LP para el simulador AgroVIA."""

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import pandas as pd
from dominio.constantes import RETORNO_PRODUCTOS

try:
    import pulp as pl
except ImportError:
    pl = None


# Constantes de matching LP
GRAINS = ['Soja', 'Maiz', 'Trigo', 'Cebada', 'Sorgo', 'Girasol']

ESTACIONALIDAD = {
    'Arena para Construcción': [1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1],
    'Arroz': [0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
    'Cebada': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
    'Fertilizantes': [0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0],
    'Girasol': [0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    'Harinas y derivados': [0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0],
    'Maiz': [0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0],
    'Mineral de Hierro': [0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0],
    'Soja': [0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
    'Sorgo': [0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
    'Trigo': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
}

TN_POR_CAMION = {
    'Cebada': 15.0,
    'Fertilizantes': 15.0,
    'Girasol': 10.0,
    'Harinas y derivados': 15.0,
    'Maiz': 15.0,
    'Soja': 15.0,
    'Sorgo': 15.0,
    'Trigo': 15.0,
    'Arena para Construcción': 14.0,
    'Arroz': 15.0,
}

COMPATIBILIDAD_TUPLAS = [
    ('Soja', 'Fertilizantes', 1),
    ('Soja', 'Harinas y derivados', 1),
    ('Soja', 'Arroz', 1),
    ('Soja', 'Arena para Construcción', 1),
    ('Maiz', 'Fertilizantes', 1),
    ('Maiz', 'Harinas y derivados', 1),
    ('Maiz', 'Arroz', 1),
    ('Maiz', 'Arena para Construcción', 1),
    ('Trigo', 'Fertilizantes', 1),
    ('Trigo', 'Harinas y derivados', 1),
    ('Trigo', 'Arroz', 1),
    ('Trigo', 'Arena para Construcción', 1),
    ('Cebada', 'Fertilizantes', 1),
    ('Cebada', 'Harinas y derivados', 1),
    ('Cebada', 'Arroz', 1),
    ('Cebada', 'Arena para Construcción', 1),
    ('Sorgo', 'Fertilizantes', 1),
    ('Sorgo', 'Harinas y derivados', 1),
    ('Sorgo', 'Arroz', 1),
    ('Sorgo', 'Arena para Construcción', 1),
    ('Girasol', 'Fertilizantes', 1),
    ('Girasol', 'Harinas y derivados', 1),
    ('Girasol', 'Arroz', 1),
    ('Girasol', 'Arena para Construcción', 1),
]

SANTA_FE = 'SANTA FE'


def tn_a_camiones(prod: str, tn: float) -> float:
    """Convierte toneladas a camiones según la capacidad del producto."""
    tpc = TN_POR_CAMION.get(prod, 15.0)
    return tn / tpc if tpc > 0 else 0.0


def _mapa_estacionalidad(estac: Optional[dict] = None) -> dict:
    """Normaliza estacionalidad a listas de 12 meses con pesos no negativos."""
    if estac is None:
        return ESTACIONALIDAD

    estacionalidad = {}
    for producto, meses in estac.items():
        mask = [0.0] * 12
        for mes, valor in meses.items():
            try:
                mes_idx = int(mes) - 1
            except Exception:
                continue
            if 0 <= mes_idx < 12:
                try:
                    peso = float(valor)
                except Exception:
                    peso = 0.0
                mask[mes_idx] = max(peso, 0.0)
        estacionalidad[producto] = mask
    return estacionalidad


def _mapa_tn_por_camion(conv: Optional[dict] = None) -> dict:
    """Usa conversión del Excel cuando esté disponible y hace fallback al mapa interno."""
    if not conv:
        return TN_POR_CAMION
    capacidad = dict(TN_POR_CAMION)
    for producto, valor in conv.items():
        try:
            capacidad[producto] = float(valor)
        except Exception:
            continue
    return capacidad


def expandir_a_meses(
    od: pd.DataFrame,
    escala: float = 1.0,
    estac: Optional[dict] = None,
    conv: Optional[dict] = None,
) -> List[dict]:
    """
    Expande OD anual a mensual, aplicando escala y estacionalidad.
    
    Args:
        od: DataFrame con columnas [origen_prov, dest_prov, producto, ton]
        escala: Factor de escala (ej: 1.6625 para Año 1 con 80 MT base)
    
    Returns:
        Lista de dict {mes, origen_prov, dest_prov, producto, tn, camiones}
    """
    rows = []
    estacionalidad = _mapa_estacionalidad(estac)
    tn_por_camion = _mapa_tn_por_camion(conv)
    for _, row in od.iterrows():
        prod = row["producto"]
        tn_anual = float(row["ton"]) * escala
        mask = estacionalidad.get(prod, [1] * 12)
        peso_total = sum(mask)
        
        if peso_total <= 0 or tn_anual == 0:
            continue

        for m_idx, peso in enumerate(mask, start=1):
            if peso > 0:
                tn_mes = tn_anual * peso / peso_total
                rows.append({
                    "mes": m_idx,
                    "origen_prov": row["origen_prov"],
                    "dest_prov": row["dest_prov"],
                    "producto": prod,
                    "tn": tn_mes,
                    "camiones": tn_mes / tn_por_camion.get(prod, 15.0) if tn_por_camion.get(prod, 15.0) > 0 else 0.0
                })
    
    return rows


def construir_LS(expandidas: List[dict]) -> Tuple[dict, dict]:
    """
    Construye diccionarios de llegadas (L) y salidas (S).
    
    L: (SANTA_FE, producto_grano, mes) → camiones
    S: (SANTA_FE, producto_retorno, mes) → camiones
    """
    L = defaultdict(float)
    S = defaultdict(float)
    
    for r in expandidas:
        t = r["mes"]
        prod = r["producto"]
        cam = r["camiones"]
        
        # Llegadas: solo 6 granos que llegan a SANTA FE desde otras provincias
        if r["dest_prov"] == SANTA_FE and r["origen_prov"] != SANTA_FE and prod in GRAINS:
            L[(SANTA_FE, prod, t)] += cam
        
        # Salidas: solo productos de retorno desde SANTA FE a otras provincias
        if r["origen_prov"] == SANTA_FE and r["dest_prov"] != SANTA_FE and prod in RETORNO_PRODUCTOS:
            S[(SANTA_FE, prod, t)] += cam
    
    return dict(L), dict(S)


def compat_map(compat_excel: Optional[dict] = None, limpieza_excel: Optional[dict] = None) -> Tuple[set, dict, dict]:
    """Construye estructuras auxiliares de compatibilidad y limpieza."""
    comp = set()
    pesos = {}
    limpieza = {}

    if compat_excel:
        for grano, retornos in compat_excel.items():
            for retorno in retornos:
                comp.add((grano, retorno))
                pesos[(grano, retorno)] = 1.0
                limpieza[(grano, retorno)] = 1 if limpieza_excel and limpieza_excel.get((grano, retorno), False) else 0
        return comp, pesos, limpieza

    for grano, retorno, activo in COMPATIBILIDAD_TUPLAS:
        if int(activo) != 1:
            continue
        comp.add((grano, retorno))
        pesos[(grano, retorno)] = 1.0
        limpieza[(grano, retorno)] = 0
    return comp, pesos, limpieza


def construir_resumen_flujos(expandidas: List[dict]) -> dict:
    """Resume llegadas y salidas por mes, provincia y producto."""
    mensual = {mes: {"llegadas": 0.0, "salidas": 0.0, "matched": 0.0} for mes in range(1, 13)}
    llegadas_por_provincia = defaultdict(float)
    salidas_por_provincia = defaultdict(float)
    llegadas_por_producto = defaultdict(float)
    salidas_por_producto = defaultdict(float)

    for row in expandidas:
        mes = row["mes"]
        producto = row["producto"]
        camiones = row["camiones"]

        if row["dest_prov"] == SANTA_FE and row["origen_prov"] != SANTA_FE and producto in GRAINS:
            mensual[mes]["llegadas"] += camiones
            llegadas_por_provincia[row["origen_prov"]] += camiones
            llegadas_por_producto[producto] += camiones

        if row["origen_prov"] == SANTA_FE and row["dest_prov"] != SANTA_FE and producto in RETORNO_PRODUCTOS:
            mensual[mes]["salidas"] += camiones
            salidas_por_provincia[row["dest_prov"]] += camiones
            salidas_por_producto[producto] += camiones

    return {
        "mensual": mensual,
        "llegadas_por_provincia": dict(llegadas_por_provincia),
        "salidas_por_provincia": dict(salidas_por_provincia),
        "llegadas_por_producto": dict(llegadas_por_producto),
        "salidas_por_producto": dict(salidas_por_producto),
    }


def resolver_lp_detallado(
    L: dict,
    S: dict,
    estac: Optional[dict] = None,
    compat_excel: Optional[dict] = None,
    limpieza_excel: Optional[dict] = None,
) -> Tuple[List[dict], dict]:
    """Resuelve el LP y devuelve matches por arco junto con el resumen mensual."""
    if pl is None:
        raise ImportError("PuLP no está instalado. Instala con: pip install pulp")

    estacionalidad = _mapa_estacionalidad(estac)
    comp, pesos, limpieza = compat_map(compat_excel=compat_excel, limpieza_excel=limpieza_excel)
    resultados = []
    mensual = {mes: {"llegadas": 0.0, "salidas": 0.0, "matched": 0.0} for mes in range(1, 13)}
    nodo = SANTA_FE

    for mes in range(1, 13):
        mensual[mes]["llegadas"] = sum(L.get((nodo, prod, mes), 0.0) for prod in GRAINS)
        mensual[mes]["salidas"] = sum(
            valor for (nn, _prod, tt), valor in S.items() if nn == nodo and tt == mes
        )

        granos = sorted({
            prod for (nn, prod, tt), valor in L.items()
            if nn == nodo and tt == mes and valor > 0
        })
        retornos = sorted({
            prod for (nn, prod, tt), valor in S.items()
            if nn == nodo and tt == mes and valor > 0
        })

        if not granos or not retornos:
            continue

        arcos = []
        for grano in granos:
            if estacionalidad.get(grano, [0] * 12)[mes - 1] <= 0:
                continue
            for retorno in retornos:
                if estacionalidad.get(retorno, [0] * 12)[mes - 1] <= 0:
                    continue
                if (grano, retorno) in comp:
                    arcos.append((grano, retorno))

        if not arcos:
            continue

        oferta = {grano: L[(nodo, grano, mes)] for grano in granos}
        demanda = {retorno: S[(nodo, retorno, mes)] for retorno in retornos}

        prob = pl.LpProblem(f"match_SF_{mes}", pl.LpMaximize)
        x = pl.LpVariable.dicts("x", arcos, lowBound=0)

        prob += pl.lpSum([pesos[(grano, retorno)] * x[(grano, retorno)] for (grano, retorno) in arcos])

        for grano in granos:
            prob += pl.lpSum([x[(gg, retorno)] for (gg, retorno) in arcos if gg == grano]) <= oferta[grano]

        for retorno in retornos:
            prob += pl.lpSum([x[(grano, rr)] for (grano, rr) in arcos if rr == retorno]) <= demanda[retorno]

        prob.solve(pl.PULP_CBC_CMD(msg=False))

        for grano, retorno in arcos:
            valor = x[(grano, retorno)].value() or 0.0
            if valor <= 1e-9:
                continue
            mensual[mes]["matched"] += valor
            resultados.append(
                {
                    "mes": mes,
                    "producto_ida": grano,
                    "producto_retorno": retorno,
                    "match_camiones": valor,
                    "requiere_limpieza": limpieza[(grano, retorno)],
                }
            )

    return resultados, mensual


def resolver_lp_matching(L: dict, S: dict) -> float:
    """
    Resuelve el LP de matching y retorna total de camiones emparejados.
    
    Args:
        L: Llegadas {(SANTA_FE, grano, mes): camiones}
        S: Salidas {(SANTA_FE, retorno, mes): camiones}
    
    Returns:
        Total de camiones emparejados (float)
    """
    resultados, _mensual = resolver_lp_detallado(L, S)
    return sum(item["match_camiones"] for item in resultados)


def calcular_resumen_matching(data_or_od, escala: float = 1.0) -> dict:
    """Calcula matching LP y devuelve un resumen completo listo para reportar."""
    if isinstance(data_or_od, dict):
        data = data_or_od
        od = data["od"]
        estac = data.get("estac")
        conv = data.get("conv")
        compat_excel = data.get("compat")
        limpieza_excel = data.get("limpieza")
    else:
        od = data_or_od
        estac = None
        conv = None
        compat_excel = None
        limpieza_excel = None

    expandidas = expandir_a_meses(od, escala=escala, estac=estac, conv=conv)
    L, S = construir_LS(expandidas)
    resultados, mensual = resolver_lp_detallado(
        L,
        S,
        estac=estac,
        compat_excel=compat_excel,
        limpieza_excel=limpieza_excel,
    )
    flujos = construir_resumen_flujos(expandidas)

    viajes_emparejados = sum(item["match_camiones"] for item in resultados)
    viajes_con_limpieza = sum(item["match_camiones"] for item in resultados if item["requiere_limpieza"] == 1)
    viajes_sin_limpieza = viajes_emparejados - viajes_con_limpieza

    por_par = defaultdict(float)
    por_producto_ida_matched = defaultdict(float)
    por_producto_retorno_matched = defaultdict(float)
    for item in resultados:
        por_par[(item["producto_ida"], item["producto_retorno"])] += item["match_camiones"]
        por_producto_ida_matched[item["producto_ida"]] += item["match_camiones"]
        por_producto_retorno_matched[item["producto_retorno"]] += item["match_camiones"]

    return {
        "viajes_emparejados": viajes_emparejados,
        "viajes_con_limpieza": viajes_con_limpieza,
        "viajes_sin_limpieza": viajes_sin_limpieza,
        "mensual": mensual,
        "llegadas_por_provincia": flujos["llegadas_por_provincia"],
        "salidas_por_provincia": flujos["salidas_por_provincia"],
        "llegadas_por_producto": flujos["llegadas_por_producto"],
        "salidas_por_producto": flujos["salidas_por_producto"],
        "matched_por_producto_ida": dict(por_producto_ida_matched),
        "matched_por_producto_retorno": dict(por_producto_retorno_matched),
        "matched_por_par": {
            f"{grano} -> {retorno}": valor for (grano, retorno), valor in por_par.items()
        },
        "resultados": resultados,
    }


def calcular_viajes_base_matching(od: pd.DataFrame, escala: float = 1.0) -> float:
    """
    Calcula el total de viajes matcheados para una escala dada.
    
    Args:
        od: DataFrame de la matriz OD
        escala: Factor de escala (producción / BASE_PROD_MT)
    
    Returns:
        Total de viajes matcheados (camiones)
    """
    # Expandir a meses con escala
    expandidas = expandir_a_meses(od, escala=escala)
    
    # Construir L y S
    L, S = construir_LS(expandidas)
    
    # Resolver LP
    total = resolver_lp_matching(L, S)
    
    return total
