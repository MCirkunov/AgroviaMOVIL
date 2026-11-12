"""Motor principal de simulación AgroVIA — versión vectorizada con numpy."""

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from dominio.calculos import calc_dlp, calc_tir, lookup_aws, lookup_rrhh
from dominio.constantes import (
    ADOPTION_CURVE,
    AMORT_SOFTWARE_ANUAL,
    AWS_POR_ANO,
    BASE_PROD_MT,
    CAPITAL_TRABAJO,
    COMBUSTIBLE_LKM,
    COSTO_LEGAL_ADMIN,
    DLP_MIN_FACTOR,
    EXPORTACION_BASE_CAPTURA_MT,
    FACTOR_CO2,
    FEE_AGROVIA,
    HORIZON_YEARS,
    INV_EQUIPOS_Y0_POR_PERSONA,
    INV_FINVOI,
    INV_APP_STORE_Y0,
    INV_GOOGLE_PLAY_Y0,
    INV_REGISTRO_MARCA_Y0,
    INV_MERIDIANO,
    INV_SAS,
    INV_SOFTWARE,
    MATCHES_POTENCIALES_BY_YEAR,
    MATCHES_POTENCIALES_EXCEL,
    PROD_BY_YEAR,
    PROMO_POR_ANO,
    PROMO_Y0,
    RRHH_LOOKUP,
    TAX_RATE,
    VIAJES_CAPTURADOS_BASE,
)
from dominio.datos import cargar_datos, clasificar_flujos
from dominio.tipos import FlujosMensuales, ResultadoAnual, ResultadoSimulacion

# Cachés de nivel módulo — se construyen una sola vez por proceso
_PRECOMP_CACHE: Optional[dict] = None
_PRECOMP_CACHE_KEY: Optional[tuple] = None


def _viajes_capturados_por_formula(exportacion_mt: float) -> float:
    """Calcula viajes capturados con la formula base definida por negocio."""
    return float(exportacion_mt) / EXPORTACION_BASE_CAPTURA_MT * VIAJES_CAPTURADOS_BASE


def _viajes_matching_potenciales_anual(
    idx_anio: int,
    exportacion_mt: float,
    modo_viajes_estimados: str,
) -> float:
    """Devuelve viajes potenciales de matching tipo B para el año.

    - excel: usa la formula de negocio viajes = (exportacion / 92.0) * 25443.
    - lp_anual: usa la serie LP anual y la escala por el shock de exportacion.
    """
    if modo_viajes_estimados == "excel":
        return _viajes_capturados_por_formula(exportacion_mt)

    if modo_viajes_estimados == "lp_anual":
        exportacion_base = PROD_BY_YEAR[idx_anio - 1]
        if exportacion_base <= 0:
            return MATCHES_POTENCIALES_BY_YEAR[idx_anio - 1]
        shock_exportacion = float(exportacion_mt) / float(exportacion_base)
        return MATCHES_POTENCIALES_BY_YEAR[idx_anio - 1] * shock_exportacion

    raise ValueError("modo_viajes_estimados inválido. Use 'lp_anual' o 'excel'.")


def _estimar_camioneros_desde_matriz(
    pc: dict,
    ea: float,
    matching_scale_factor_b: float,
    pct_captura_interp: float,
    viajes_por_camion_mes: float,
) -> int:
    """Estima camioneros requeridos usando la carga pico mensual de la matriz."""
    vpm = max(float(viajes_por_camion_mes), 0.1)
    b_mensual = (pc["vbase_B"] * ea * matching_scale_factor_b).sum(axis=0)
    c_mensual = (pc["vbase_C"] * (ea * pct_captura_interp)).sum(axis=0)
    pico_mensual = float(np.max(b_mensual + c_mensual)) if len(b_mensual) else 0.0
    return max(1, int(math.ceil(pico_mensual / vpm)))


def _normalizar_serie_anual(serie: List[float]) -> List[float]:
    """Normaliza series para indexación 1..HORIZON_YEARS.

    El motor usa índices de año 1..HORIZON_YEARS (deja posición 0 como base).
    Si llega una curva manual de HORIZON_YEARS elementos (años 1..N), agrega una
    posición inicial para mantener compatibilidad.
    """
    if len(serie) == HORIZON_YEARS + 1:
        return list(serie)
    if len(serie) == HORIZON_YEARS:
        return [float(serie[0])] + list(serie)
    raise ValueError(f"Las curvas anuales deben tener {HORIZON_YEARS} o {HORIZON_YEARS + 1} valores.")


def _get_data(base_dir: str) -> dict:
    """Carga datos del Excel con cache invalidable por fecha de archivo."""
    return cargar_datos(base_dir)


# ---------------------------------------------------------------------------
# Pre-cómputo de matrices base
# ---------------------------------------------------------------------------

def _precomputar_matrices(
    tipoA: pd.DataFrame,
    tipoB: pd.DataFrame,
    tipoC: pd.DataFrame,
    data: dict,
) -> dict:
    """Pre-computa matrices base de viajes y tarifas para operaciones vectorizadas.

    El resultado sólo depende de los datos cargados (no de parámetros de simulación),
    por lo que se calcula una sola vez y se reutiliza en todas las llamadas siguientes.
    """
    conv = data["conv"]
    estac = data["estac"]
    tar_kms = data["tar_kms"]
    tar_ars = data["tar_ars"]

    def _vbase(df: pd.DataFrame) -> np.ndarray:
        """Matriz (n_filas × 12): vbase[i, m] = viajes_mes(fila_i, escala=1, mes=m+1)."""
        n = len(df)
        mat = np.zeros((n, 12))
        for i, (_, row) in enumerate(df.iterrows()):
            prod = row["producto"]
            tn = conv.get(prod, 15)
            es = estac.get(prod, {})
            total_fe = sum(es.values())
            if total_fe == 0 or tn == 0:
                continue
            base = row["ton"] / tn / total_fe
            for m in range(1, 13):
                mat[i, m - 1] = base * es.get(m, 0.0)
        return mat

    tipoA_r = tipoA.reset_index(drop=True)
    tipoB_r = tipoB.reset_index(drop=True)
    tipoC_r = tipoC.reset_index(drop=True)

    vbase_A = _vbase(tipoA_r)
    vbase_B = _vbase(tipoB_r)
    vbase_C = _vbase(tipoC_r)

    # Tarifas por fila — constantes, sólo dependen de la distancia
    tar_B = np.interp(tipoB_r["dist_km"].values, tar_kms, tar_ars)
    tar_C = np.interp(tipoC_r["dist_km"].values, tar_kms, tar_ars)

    # Tarifas por tramo (umbral inferior), usadas cuando dynamic pricing está apagado.
    idx_B_floor = np.searchsorted(tar_kms, tipoB_r["dist_km"].values, side="right") - 1
    idx_C_floor = np.searchsorted(tar_kms, tipoC_r["dist_km"].values, side="right") - 1
    idx_B_floor = np.clip(idx_B_floor, 0, len(tar_ars) - 1)
    idx_C_floor = np.clip(idx_C_floor, 0, len(tar_ars) - 1)
    tar_B_floor = tar_ars[idx_B_floor]
    tar_C_floor = tar_ars[idx_C_floor]

    # Mapa DLP (provincia, mes) → factor
    # LTR = demanda/oferta es invariante a la escala → se calcula una sola vez
    all_provs = set(tipoB_r["dest_prov"].unique()) | set(tipoC_r["dest_prov"].unique())
    dlp_map: Dict = {}
    for prov in all_provs:
        for m in range(1, 13):
            dlp_map[(prov, m)] = calc_dlp(prov, m, tipoA_r, tipoB_r, data, escala=1.0)

    dlp_B = np.array([
        [dlp_map.get((prov, m + 1), 1.0) for m in range(12)]
        for prov in tipoB_r["dest_prov"].values
    ])
    dlp_C = np.array([
        [dlp_map.get((prov, m + 1), 1.0) for m in range(12)]
        for prov in tipoC_r["dest_prov"].values
    ])

    # Oferta/demanda por provincia para restricción un_camion_un_retorno
    orig_prov_A = tipoA_r["origen_prov"].values
    dest_prov_B_arr = tipoB_r["dest_prov"].values
    orig_prov_C = tipoC_r["origen_prov"].values

    oferta_prov: Dict[str, np.ndarray] = {}
    for prov in np.unique(orig_prov_A):
        oferta_prov[prov] = vbase_A[orig_prov_A == prov, :].sum(axis=0)

    demanda_prov_B: Dict[str, np.ndarray] = {}
    for prov in np.unique(dest_prov_B_arr):
        demanda_prov_B[prov] = vbase_B[dest_prov_B_arr == prov, :].sum(axis=0)

    # Capacidad neta: prov_cap_C[i, m] = max(0, oferta_prov − demanda_B_prov) con escala=1
    prov_cap_C = np.zeros((len(tipoC_r), 12))
    for prov in np.unique(orig_prov_C):
        mask = orig_prov_C == prov
        of = oferta_prov.get(prov, np.zeros(12))
        dm = demanda_prov_B.get(prov, np.zeros(12))
        prov_cap_C[mask, :] = np.maximum(0.0, of - dm)[np.newaxis, :]

    return dict(
        tipoA_r=tipoA_r,
        tipoB_r=tipoB_r,
        tipoC_r=tipoC_r,
        vbase_A=vbase_A,
        vbase_B=vbase_B,
        vbase_C=vbase_C,
        tar_B=tar_B,
        tar_C=tar_C,
        tar_B_floor=tar_B_floor,
        tar_C_floor=tar_C_floor,
        dlp_B=dlp_B,
        dlp_C=dlp_C,
        dlp_map=dlp_map,
        prov_cap_C=prov_cap_C,
        dist_B=tipoB_r["dist_km"].values,
        dist_C=tipoC_r["dist_km"].values,
        dist_rosario_orig_C=tipoC_r["dist_rosario_orig"].values,
        dist_rosario_dest_C=tipoC_r["dist_rosario_dest"].values,
    )


# ---------------------------------------------------------------------------
# Simulación principal
# ---------------------------------------------------------------------------

def ejecutar_simulacion(
    adopcion_manual: bool = False,
    adopcion_override: Optional[List[float]] = None,
    pct_captura_interp: float = 0.0,
    radio_desvio_km: float = 300.0,
    un_camion_un_retorno: bool = True,
    dynamic_pricing: bool = False,
    modo_viajes_estimados: str = "lp_anual",
    camioneros_disponibles: Optional[int] = None,
    viajes_por_camion_mes: float = 1.0,
    export_factor: float = 1.0,
    fee_agrovia: float = FEE_AGROVIA,
    tasa_descuento: float = 0.2016,
    base_dir: str = ".",
) -> ResultadoSimulacion:
    global _PRECOMP_CACHE, _PRECOMP_CACHE_KEY

    data = _get_data(base_dir)
    tipoA, tipoB, tipoC = clasificar_flujos(data)

    data_cache_key = tuple(data.get("data_cache_key", ()))
    if _PRECOMP_CACHE is None or _PRECOMP_CACHE_KEY != data_cache_key:
        _PRECOMP_CACHE = _precomputar_matrices(tipoA, tipoB, tipoC, data)
        _PRECOMP_CACHE_KEY = data_cache_key
    pc = _PRECOMP_CACHE

    adoption_raw = adopcion_override if adopcion_manual and adopcion_override else ADOPTION_CURVE
    adoption = _normalizar_serie_anual(list(adoption_raw))

    if modo_viajes_estimados == "lp_anual" and len(MATCHES_POTENCIALES_BY_YEAR) < len(PROD_BY_YEAR):
        raise ValueError("MATCHES_POTENCIALES_BY_YEAR debe cubrir todos los años de PROD_BY_YEAR")
    if export_factor <= 0:
        raise ValueError("export_factor debe ser mayor a 0")
    if viajes_por_camion_mes <= 0:
        raise ValueError("viajes_por_camion_mes debe ser mayor a 0")

    personas_y0 = RRHH_LOOKUP[0][1]
    inv_equipos_y0 = personas_y0 * INV_EQUIPOS_Y0_POR_PERSONA
    inversion_y0 = -(
        inv_equipos_y0
        + INV_SOFTWARE
        + INV_SAS
        + INV_MERIDIANO
        + INV_FINVOI
        + INV_APP_STORE_Y0
        + INV_GOOGLE_PLAY_Y0
        + INV_REGISTRO_MARCA_Y0
        + CAPITAL_TRABAJO
        + PROMO_Y0
    )

    year_results: List[ResultadoAnual] = []
    flujos_netos = [inversion_y0]
    flujo_acum = inversion_y0
    personas_prev = personas_y0
    # Usamos ceil para contar dispositivos enteros (laptops), igual que Excel.
    personas_prev_ceil = math.ceil(personas_y0)
    amort_equip_pools = [(0, inv_equipos_y0)]

    # Filtro de radio: constante por llamado
    radio_mask = pc["dist_rosario_dest_C"] <= pc["dist_rosario_orig_C"] + radio_desvio_km

    for y in range(1, HORIZON_YEARS + 1):
        idx = y
        exportacion_mt = PROD_BY_YEAR[idx - 1] * export_factor
        escala = exportacion_mt / BASE_PROD_MT
        adopcion = adoption[idx]
        qp_pct = 1.0
        adelanto_pct = 1.0
        ea = escala * adopcion  # factor combinado

        viajes_matching_potenciales = _viajes_matching_potenciales_anual(
            idx_anio=idx,
            exportacion_mt=exportacion_mt,
            modo_viajes_estimados=modo_viajes_estimados,
        )
        viajes_base_total_matching = viajes_matching_potenciales * adopcion

        viajes_base_total = 0.0
        viajes_interp_total = 0.0
        monto_facturado_total = 0.0
        co2_total_ano = 0.0
        dist_total_ano = 0.0
        
        # Pre-calcular suma de tipoB (para distribuir matching proporcionalmente)
        viajes_typeB_sin_matching = 0.0
        for m in range(1, 13):
            mi = m - 1
            v_B = pc["vbase_B"][:, mi] * ea
            viajes_typeB_sin_matching += v_B.sum()

        if viajes_typeB_sin_matching > 0:
            scale_factor = viajes_base_total_matching / viajes_typeB_sin_matching
        else:
            scale_factor = 0.0

        if camioneros_disponibles is None:
            camioneros_eff = _estimar_camioneros_desde_matriz(
                pc=pc,
                ea=ea,
                matching_scale_factor_b=scale_factor,
                pct_captura_interp=pct_captura_interp,
                viajes_por_camion_mes=viajes_por_camion_mes,
            )
        else:
            camioneros_eff = max(1, int(camioneros_disponibles))

        capacidad_mensual_flotilla = camioneros_eff * float(viajes_por_camion_mes)
        pico_viajes_mes = 0.0

        for m in range(1, 13):
            mi = m - 1

            # --- tipoB: usar matching en lugar del cálculo directo ---
            # Distribuir viajes_base_total_matching según proporción mensual de tipoB
            v_B = pc["vbase_B"][:, mi] * ea
            v_B_scaled = v_B * scale_factor

            viajes_b_mes = float(v_B_scaled.sum())
            if viajes_b_mes > capacidad_mensual_flotilla and viajes_b_mes > 0:
                v_B_scaled = v_B_scaled * (capacidad_mensual_flotilla / viajes_b_mes)
                viajes_b_mes = capacidad_mensual_flotilla

            capacidad_restante = max(0.0, capacidad_mensual_flotilla - viajes_b_mes)

            mask_B = v_B_scaled > 0
            if mask_B.any():
                dlp_B_m = pc["dlp_B"][:, mi]
                tar_base_B = pc["tar_B"] if dynamic_pricing else pc["tar_B_floor"]
                tar_ef_B = np.maximum(tar_base_B * DLP_MIN_FACTOR, tar_base_B * dlp_B_m) if dynamic_pricing else tar_base_B
                vv = v_B_scaled[mask_B]
                viajes_base_total += vv.sum()
                monto_facturado_total += np.dot(vv, tar_ef_B[mask_B])
                dist_total_ano += np.dot(vv, pc["dist_B"][mask_B])
                co2_total_ano += np.dot(vv, pc["dist_B"][mask_B]) * COMBUSTIBLE_LKM * FACTOR_CO2 / 1000

            # --- tipoC: operaciones vectorizadas ---
            v_C = pc["vbase_C"][:, mi] * (ea * pct_captura_interp)
            if un_camion_un_retorno:
                cap = pc["prov_cap_C"][:, mi] * ea
                v_C = np.minimum(v_C, cap)

            viajes_c_mes = float(v_C.sum())
            if viajes_c_mes > capacidad_restante and viajes_c_mes > 0:
                v_C = v_C * (capacidad_restante / viajes_c_mes)
                viajes_c_mes = capacidad_restante

            pico_viajes_mes = max(pico_viajes_mes, viajes_b_mes + viajes_c_mes)

            mask_C = radio_mask & (v_C > 0)
            if mask_C.any():
                dlp_C_m = pc["dlp_C"][:, mi]
                tar_base_C = pc["tar_C"] if dynamic_pricing else pc["tar_C_floor"]
                tar_ef_C = np.maximum(tar_base_C * DLP_MIN_FACTOR, tar_base_C * dlp_C_m) if dynamic_pricing else tar_base_C
                vv = v_C[mask_C]
                viajes_interp_total += vv.sum()
                monto_facturado_total += np.dot(vv, tar_ef_C[mask_C])
                dist_total_ano += np.dot(vv, pc["dist_C"][mask_C])
                co2_total_ano += np.dot(vv, pc["dist_C"][mask_C]) * COMBUSTIBLE_LKM * FACTOR_CO2 / 1000

        viajes_total = viajes_base_total + viajes_interp_total
        if viajes_total > 0:
            if dynamic_pricing:
                tarifa_prom = monto_facturado_total / viajes_total
            else:
                km_promedio_ano = dist_total_ano / viajes_total
                # Lookup escalonado: si km cae entre dos tramos, usa el superior
                idx_tarifa = int(np.searchsorted(data["tar_kms"], km_promedio_ano, side="left"))
                idx_tarifa = int(np.clip(idx_tarifa, 0, len(data["tar_ars"]) - 1))
                tarifa_prom = float(data["tar_ars"][idx_tarifa])
        else:
            tarifa_prom = 0.0

        # Si FlujodeCaja define tarifa anual explícita, usarla para alinear el
        # resultado financiero con la hoja de referencia.
        tarifa_override = float(data.get("tarifa_flujocaja_by_year", {}).get(y, 0.0))
        if tarifa_override > 0:
            tarifa_prom = tarifa_override

        fee_effectivo = float(data.get("fee_flujocaja_by_year", {}).get(y, fee_agrovia))
        # Nuevo flujo: el ingreso AgroVIA surge del total capturado anual.
        viajes_cobrados = viajes_total
        monto_facturado_total = tarifa_prom * viajes_cobrados
        monto_adelantado = monto_facturado_total
        ingreso_qp = monto_facturado_total * fee_effectivo

        personas, costo_rrhh = lookup_rrhh(viajes_total)
        # Use year-based AWS lookup (exact values from Excel)
        aws = AWS_POR_ANO.get(y, dict(ec2=0, s3=0, rds=0, maps=0, total=0))
        costo_aws = aws["total"]
        costo_opex_extra = float(data.get("extra_opex_by_year", {}).get(y, 0.0))
        costo_app_store = float(data.get("app_store_by_year", {}).get(y, 0.0))
        costo_opex_extra_detail = dict(data.get("extra_opex_detail_by_year", {}).get(y, {}))

        # Equipos: usar ceil para contar dispositivos enteros igual que Excel.
        personas_ceil = math.ceil(personas)
        nuevas_personas = max(0, personas_ceil - personas_prev_ceil)
        compra_equipos = nuevas_personas * INV_EQUIPOS_Y0_POR_PERSONA
        if nuevas_personas > 0:
            amort_equip_pools.append((y, compra_equipos))
        personas_prev = personas
        personas_prev_ceil = personas_ceil

        # Amortización lineal a 5 años: empieza al año siguiente a la compra.
        amort_equipos = sum(
            monto / 5
            for anio_compra, monto in amort_equip_pools
            if anio_compra < y <= anio_compra + 5
        )
        amort_software = AMORT_SOFTWARE_ANUAL if y <= 5 else 0.0

        promo = PROMO_POR_ANO.get(y, 1_000_000)
        costos_op = costo_rrhh + costo_aws + promo + COSTO_LEGAL_ADMIN + costo_opex_extra

        ganancia = ingreso_qp - costos_op - amort_equipos - amort_software
        impuesto = max(0.0, ganancia * TAX_RATE)
        utilidad_despues_imp = ganancia - impuesto
        flujo_neto = utilidad_despues_imp + amort_equipos + amort_software - compra_equipos
        valor_residual_equipos = 0.0
        if y == HORIZON_YEARS:
            # Prioriza recuperos explícitos del FlujodeCaja cuando existen.
            residual_override = float(data.get("residual_equipos_by_year", {}).get(y, 0.0))
            recupero_ct_override = float(data.get("recupero_ct_by_year", {}).get(y, 0.0))

            if residual_override > 0:
                valor_residual_equipos = residual_override
            else:
                # Recupera como valor residual el remanente no amortizado de equipos al cierre del horizonte.
                valor_residual_equipos = 0.0
                for anio_compra, monto in amort_equip_pools:
                    anios_amort_hasta_horizonte = min(5, max(0, HORIZON_YEARS - anio_compra))
                    amort_hasta_horizonte = monto * (anios_amort_hasta_horizonte / 5)
                    valor_residual_equipos += max(0.0, monto - amort_hasta_horizonte)

            flujo_neto += valor_residual_equipos
            flujo_neto += recupero_ct_override if recupero_ct_override > 0 else CAPITAL_TRABAJO

        flujo_desc = flujo_neto / (1 + tasa_descuento) ** y
        flujo_acum += flujo_desc
        flujos_netos.append(flujo_neto)

        year_results.append(
            ResultadoAnual(
                anio=y,
                exportacion_mt=exportacion_mt,
                viajes_matching_potenciales=viajes_matching_potenciales,
                viajes_base=viajes_base_total,
                viajes_interp=viajes_interp_total,
                viajes_total=viajes_total,
                tarifa_prom=tarifa_prom,
                monto_facturado=monto_facturado_total,
                monto_adelantado=monto_adelantado,
                ingreso_qp=ingreso_qp,
                adopcion=adopcion,
                qp_pct=qp_pct,
                adelanto_pct=adelanto_pct,
                fee_agrovia=fee_effectivo,
                costo_rrhh=costo_rrhh,
                costo_aws=costo_aws,
                costo_aws_detail=aws,
                costo_equipos_compra=compra_equipos,
                costo_equipos_amort=amort_equipos,
                costo_software_amort=amort_software,
                costo_promo=promo,
                costo_legal=COSTO_LEGAL_ADMIN,
                costo_opex_extra=costo_opex_extra,
                costo_app_store=costo_app_store,
                costo_opex_extra_detail=costo_opex_extra_detail,
                costos_totales=costos_op + amort_equipos + amort_software,
                ganancia_antes_imp=ganancia,
                impuesto=impuesto,
                flujo_neto=flujo_neto,
                flujo_descontado=flujo_desc,
                flujo_acumulado=flujo_acum,
                valor_residual_equipos=valor_residual_equipos,
                co2_tn=co2_total_ano,
                personas=personas,
                camioneros_disponibles=camioneros_eff,
                camioneros_requeridos_pico=int(math.ceil(pico_viajes_mes / max(float(viajes_por_camion_mes), 0.1))),
                utilizacion_flotilla_pico_pct=(
                    (pico_viajes_mes / capacidad_mensual_flotilla) * 100.0 if capacidad_mensual_flotilla > 0 else 0.0
                ),
            )
        )

    van = sum(flow / (1 + tasa_descuento) ** period for period, flow in enumerate(flujos_netos))
    tir = calc_tir(flujos_netos)
    payback = next((yr.anio for yr in year_results if yr.flujo_acumulado >= 0), None)
    co2_total = sum(yr.co2_tn for yr in year_results)

    return ResultadoSimulacion(
        years=year_results,
        van=van,
        tir=tir,
        payback=payback,
        co2_total=co2_total,
        inversion_y0=abs(inversion_y0),
    )


def calcular_arcos_mes(
    anio: int,
    mes: int,
    adopcion_manual: bool = False,
    adopcion_override: Optional[List[float]] = None,
    pct_captura_interp: float = 0.0,
    radio_desvio_km: float = 300.0,
    un_camion_un_retorno: bool = True,
    dynamic_pricing: bool = True,
    modo_viajes_estimados: str = "lp_anual",
    camioneros_disponibles: Optional[int] = None,
    viajes_por_camion_mes: float = 1.0,
    export_factor: float = 1.0,
    base_dir: str = ".",
) -> "FlujosMensuales":
    """Calcula los arcos del mapa para un año y mes específico. Rápido (~50ms)."""
    global _PRECOMP_CACHE
    data = _get_data(base_dir)
    tipoA, tipoB, tipoC = clasificar_flujos(data)
    if _PRECOMP_CACHE is None:
        _PRECOMP_CACHE = _precomputar_matrices(tipoA, tipoB, tipoC, data)
    pc = _PRECOMP_CACHE

    adoption_raw = adopcion_override if adopcion_manual and adopcion_override else ADOPTION_CURVE
    adoption = _normalizar_serie_anual(list(adoption_raw))
    exportacion_mt = PROD_BY_YEAR[anio - 1] * export_factor
    escala = exportacion_mt / BASE_PROD_MT
    adopcion = adoption[anio]
    ea = escala * adopcion

    viajes_objetivo_anual = _viajes_matching_potenciales_anual(
        idx_anio=anio,
        exportacion_mt=exportacion_mt,
        modo_viajes_estimados=modo_viajes_estimados,
    ) * adopcion
    viajes_typeB_sin_matching = float((pc["vbase_B"] * ea).sum())
    matching_scale_factor_B = (
        viajes_objetivo_anual / viajes_typeB_sin_matching if viajes_typeB_sin_matching > 0 else 0.0
    )

    if camioneros_disponibles is None:
        camioneros_eff = _estimar_camioneros_desde_matriz(
            pc=pc,
            ea=ea,
            matching_scale_factor_b=matching_scale_factor_B,
            pct_captura_interp=pct_captura_interp,
            viajes_por_camion_mes=viajes_por_camion_mes,
        )
    else:
        camioneros_eff = max(1, int(camioneros_disponibles))

    return _calcular_flujos_mensuales(
        anio=anio,
        mes=mes,
        data=data,
        adopcion=adopcion,
        escala=escala,
        matching_scale_factor_B=matching_scale_factor_B,
        pct_captura_interp=pct_captura_interp,
        radio_desvio_km=radio_desvio_km,
        un_camion_un_retorno=un_camion_un_retorno,
        camioneros_disponibles=camioneros_eff,
        viajes_por_camion_mes=viajes_por_camion_mes,
        dynamic_pricing=dynamic_pricing,
        pc=pc,
    )


# ---------------------------------------------------------------------------
# Flujos mensuales para el mapa
# ---------------------------------------------------------------------------

def _calcular_flujos_mensuales(
    anio: int,
    mes: int,
    data: dict,
    adopcion: float,
    escala: float,
    matching_scale_factor_B: float,
    pct_captura_interp: float,
    radio_desvio_km: float,
    un_camion_un_retorno: bool,
    camioneros_disponibles: int,
    viajes_por_camion_mes: float,
    dynamic_pricing: bool,
    pc: dict,
) -> FlujosMensuales:
    mi = mes - 1
    ea = escala * adopcion
    result = FlujosMensuales(mes=mes, anio=anio)

    tipoA_r = pc["tipoA_r"]
    tipoB_r = pc["tipoB_r"]
    tipoC_r = pc["tipoC_r"]

    # --- arcos tipoA ---
    v_A = pc["vbase_A"][:, mi] * ea
    for i in range(len(tipoA_r)):
        if v_A[i] <= 0:
            continue
        row = tipoA_r.iloc[i]
        result.tipoA_arcs.append({
            "orig_lat": row["orig_lat"],
            "orig_lng": row["orig_lng"],
            "dest_lat": row["dest_lat"],
            "dest_lng": row["dest_lng"],
            "origen": row["origen_ciudad"],
            "destino": row["dest_ciudad"],
            "prov_orig": row["origen_prov"],
            "prov_dest": row["dest_prov"],
            "producto": row["producto"],
            "viajes": round(v_A[i], 1),
            "dist_km": row["dist_km"],
            "ton": row["ton"],
        })

    # --- arcos tipoB ---
    v_B = pc["vbase_B"][:, mi] * ea * matching_scale_factor_B
    capacidad_mensual_flotilla = max(0.0, float(camioneros_disponibles) * float(viajes_por_camion_mes))
    viajes_b_mes = float(v_B.sum())
    if viajes_b_mes > capacidad_mensual_flotilla and viajes_b_mes > 0:
        v_B = v_B * (capacidad_mensual_flotilla / viajes_b_mes)
        viajes_b_mes = capacidad_mensual_flotilla

    capacidad_restante = max(0.0, capacidad_mensual_flotilla - viajes_b_mes)

    dlp_B_m = pc["dlp_B"][:, mi]
    tar_base_B = pc["tar_B"] if dynamic_pricing else pc["tar_B_floor"]
    tar_ef_B = np.maximum(tar_base_B * DLP_MIN_FACTOR, tar_base_B * dlp_B_m) if dynamic_pricing else tar_base_B

    for i in range(len(tipoB_r)):
        if v_B[i] <= 0:
            continue
        row = tipoB_r.iloc[i]
        prov_dest = row["dest_prov"]
        dlp = dlp_B_m[i]
        vv = v_B[i]

        result.viajes_base += vv
        result.monto_facturado += vv * tar_ef_B[i]
        result.co2_tn += vv * pc["dist_B"][i] * COMBUSTIBLE_LKM * FACTOR_CO2 / 1000

        resumen = result.prov_summary.setdefault(
            prov_dest, {"viajes_base": 0, "viajes_interp": 0, "ltr_factor": dlp}
        )
        resumen["viajes_base"] += vv

        result.tipoB_arcs.append({
            "orig_lat": row["orig_lat"],
            "orig_lng": row["orig_lng"],
            "dest_lat": row["dest_lat"],
            "dest_lng": row["dest_lng"],
            "origen": row["origen_ciudad"],
            "destino": row["dest_ciudad"],
            "prov_orig": row["origen_prov"],
            "prov_dest": prov_dest,
            "producto": row["producto"],
            "viajes": round(vv, 1),
            "dist_km": pc["dist_B"][i],
            "tarifa_ef": round(tar_ef_B[i]),
            "dlp": round(dlp, 3),
            "requiere_limpieza": False,
        })

    # --- arcos tipoC ---
    v_C = pc["vbase_C"][:, mi] * (ea * pct_captura_interp)
    if un_camion_un_retorno:
        cap = pc["prov_cap_C"][:, mi] * ea
        v_C = np.minimum(v_C, cap)

    viajes_c_mes = float(v_C.sum())
    if viajes_c_mes > capacidad_restante and viajes_c_mes > 0:
        v_C = v_C * (capacidad_restante / viajes_c_mes)

    radio_mask = pc["dist_rosario_dest_C"] <= pc["dist_rosario_orig_C"] + radio_desvio_km
    dlp_C_m = pc["dlp_C"][:, mi]
    tar_base_C = pc["tar_C"] if dynamic_pricing else pc["tar_C_floor"]
    tar_ef_C = np.maximum(tar_base_C * DLP_MIN_FACTOR, tar_base_C * dlp_C_m) if dynamic_pricing else tar_base_C

    compat = data["compat"]
    limpieza = data["limpieza"]

    for i in range(len(tipoC_r)):
        if not radio_mask[i] or v_C[i] <= 0:
            continue
        row = tipoC_r.iloc[i]
        prov_dest = row["dest_prov"]
        dlp = dlp_C_m[i]
        vv = v_C[i]
        prod = row["producto"]

        result.viajes_interp += vv
        result.monto_facturado += vv * tar_ef_C[i]
        result.co2_tn += vv * pc["dist_C"][i] * COMBUSTIBLE_LKM * FACTOR_CO2 / 1000

        resumen = result.prov_summary.setdefault(
            prov_dest, {"viajes_base": 0, "viajes_interp": 0, "ltr_factor": dlp}
        )
        resumen["viajes_interp"] += vv

        req_limp = any(limpieza.get((prod_ida, prod), False) for prod_ida in compat)
        result.tipoC_arcs.append({
            "orig_lat": row["orig_lat"],
            "orig_lng": row["orig_lng"],
            "dest_lat": row["dest_lat"],
            "dest_lng": row["dest_lng"],
            "origen": row["origen_ciudad"],
            "destino": row["dest_ciudad"],
            "prov_orig": row["origen_prov"],
            "prov_dest": prov_dest,
            "producto": prod,
            "viajes": round(vv, 1),
            "dist_km": pc["dist_C"][i],
            "tarifa_ef": round(tar_ef_C[i]),
            "dlp": round(dlp, 3),
            "requiere_limpieza": req_limp,
        })

    return result