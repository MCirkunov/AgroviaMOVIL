"""Carga y clasificación de datos base del simulador."""

import os
import re
from typing import Tuple
import unicodedata

import numpy as np
import pandas as pd

from dominio.calculos import haversine
from dominio.constantes import RETORNO_PRODUCTOS, ROSARIO_LAT, ROSARIO_LNG


_DATA_CACHE = None
_DATA_CACHE_KEY = None


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _detect_year_columns(df: pd.DataFrame) -> dict[int, int]:
    """Detecta columnas de años consecutivos (p. ej., 0..5) en FlujodeCaja."""
    # Caso 1: los años ya están en los nombres de columnas (pandas header=0).
    by_columns: dict[int, int] = {}
    for idx, col_name in enumerate(df.columns.tolist()):
        try:
            token = str(col_name).strip().lower().replace("año", "").replace("ano", "").strip()
            year_val = int(float(token))
        except Exception:
            continue
        by_columns[year_val] = idx

    if by_columns and 0 in by_columns:
        ordered_years = sorted(by_columns.keys())
        if ordered_years == list(range(ordered_years[0], ordered_years[-1] + 1)):
            return {y: by_columns[y] for y in ordered_years}

    # Caso 2: los años están en alguna fila del contenido.
    best: dict[int, int] = {}
    max_cols = int(df.shape[1])
    max_rows = min(60, int(df.shape[0]))

    for r in range(max_rows):
        row_vals = [df.iat[r, c] for c in range(max_cols)]
        for c0 in range(max_cols):
            mapping: dict[int, int] = {}
            expected = 0
            for c in range(c0, max_cols):
                raw = row_vals[c]
                try:
                    token = str(raw).strip().lower().replace("año", "").replace("ano", "").strip()
                    val = int(float(token))
                except Exception:
                    break
                if val != expected:
                    break
                mapping[val] = c
                expected += 1

            if len(mapping) > len(best):
                best = mapping

    return best


def _get_sheet(workbook: dict, *candidates: str) -> pd.DataFrame:
    """Busca una hoja por nombre exacto o normalizado."""
    for name in candidates:
        if name in workbook:
            return workbook[name]

    target = {_normalize_text(name) for name in candidates}
    for sheet_name, sheet_df in workbook.items():
        if _normalize_text(sheet_name) in target:
            return sheet_df

    raise KeyError(f"No se encontró hoja entre candidatos: {', '.join(candidates)}")


def _extract_extra_opex_from_flujodecaja(fc_sheet: pd.DataFrame) -> tuple[dict[int, float], dict[int, dict[str, float]], dict[int, float]]:
    """Extrae costos operativos extra dentro de 'Egresos afectados a impuestos'.

    Devuelve:
    - total_extra_by_year: suma de filas extra por año
    - detail_extra_by_year: detalle por etiqueta original y año
    - app_store_by_year: suma de filas relacionadas a App/Play Store por año
    """
    year_cols = _detect_year_columns(fc_sheet)
    if not year_cols:
        return {}, {}, {}

    known_core = {
        "recursoshumanos",
        "amazonec2",
        "amazons3",
        "amazonrds",
        "googlemapsapi",
        "googlemapsdirectionsapi",
        "promocion",
        "promocioneinstitucional",
        "gastoslegalesyadministrativos",
    }

    total_extra_by_year = {y: 0.0 for y in year_cols.keys()}
    detail_extra_by_year = {y: {} for y in year_cols.keys()}
    app_store_by_year = {y: 0.0 for y in year_cols.keys()}

    in_opex_section = False
    for r in range(fc_sheet.shape[0]):
        label_raw = "" if pd.isna(fc_sheet.iat[r, 0]) else str(fc_sheet.iat[r, 0]).strip()
        if not label_raw:
            continue
        label_norm = _normalize_text(label_raw)

        if (
            "egresos" in label_norm
            and "impuestos" in label_norm
            and "operativos" in label_norm
            and "noafectados" not in label_norm
        ):
            in_opex_section = True
            continue
        if label_norm == "gastosnodesembolsables":
            in_opex_section = False
            continue

        # En algunos formatos, el bloque de OPEX termina en la fila de total.
        if in_opex_section and (
            "totalegresosoperativos" in label_norm
            or "amortizacion" in label_norm
            or "utilidadantesdeimpuesto" in label_norm
        ):
            in_opex_section = False
            continue
        if not in_opex_section:
            continue

        if "total" in label_norm:
            continue

        if label_norm in known_core:
            continue

        row_values: dict[int, float] = {}
        for y, c in year_cols.items():
            val = fc_sheet.iat[r, c]
            if pd.isna(val):
                continue
            try:
                num = float(val)
            except Exception:
                continue
            row_values[y] = num

        if not row_values:
            continue

        is_store_row = bool(re.search(r"app\s*store|play\s*store|google\s*play|apple\s*store", label_raw, re.IGNORECASE))
        for y, num in row_values.items():
            total_extra_by_year[y] += num
            detail_extra_by_year[y][label_raw] = num
            if is_store_row:
                app_store_by_year[y] += num

    # Limpieza de años sin movimientos para simplificar serialización.
    total_extra_by_year = {y: v for y, v in total_extra_by_year.items() if abs(v) > 0}
    detail_extra_by_year = {y: d for y, d in detail_extra_by_year.items() if d}
    app_store_by_year = {y: v for y, v in app_store_by_year.items() if abs(v) > 0}
    return total_extra_by_year, detail_extra_by_year, app_store_by_year


def _extract_core_flujocaja_assumptions(fc_sheet: pd.DataFrame) -> tuple[dict[int, float], dict[int, float]]:
    """Extrae supuestos clave de FlujodeCaja (tarifa por viaje y fee por año)."""
    year_cols = _detect_year_columns(fc_sheet)
    if not year_cols:
        return {}, {}

    tarifa_by_year: dict[int, float] = {}
    fee_by_year: dict[int, float] = {}

    for r in range(fc_sheet.shape[0]):
        label_raw = "" if pd.isna(fc_sheet.iat[r, 0]) else str(fc_sheet.iat[r, 0]).strip()
        if not label_raw:
            continue
        label_norm = _normalize_text(label_raw)

        is_tarifa = "tarifaporviaje" in label_norm
        is_fee = "feeagrovia" in label_norm
        if not (is_tarifa or is_fee):
            continue

        for y, c in year_cols.items():
            val = fc_sheet.iat[r, c]
            if pd.isna(val):
                continue
            try:
                num = float(val)
            except Exception:
                continue
            if is_tarifa and num > 0:
                tarifa_by_year[y] = num
            if is_fee and num > 0:
                fee_by_year[y] = num

    return tarifa_by_year, fee_by_year


def _extract_flujocaja_recoveries(fc_sheet: pd.DataFrame) -> tuple[dict[int, float], dict[int, float]]:
    """Extrae recuperos no afectados a impuesto por año."""
    year_cols = _detect_year_columns(fc_sheet)
    if not year_cols:
        return {}, {}

    residual_equipos_by_year: dict[int, float] = {}
    recupero_ct_by_year: dict[int, float] = {}

    for r in range(fc_sheet.shape[0]):
        label_raw = "" if pd.isna(fc_sheet.iat[r, 0]) else str(fc_sheet.iat[r, 0]).strip()
        if not label_raw:
            continue
        label_norm = _normalize_text(label_raw)

        is_residual = "valorresidualequipos" in label_norm
        is_recupero_ct = "recuperocapitaldetrabajo" in label_norm
        if not (is_residual or is_recupero_ct):
            continue

        for y, c in year_cols.items():
            val = fc_sheet.iat[r, c]
            if pd.isna(val):
                continue
            try:
                num = float(val)
            except Exception:
                continue
            if num <= 0:
                continue
            if is_residual:
                residual_equipos_by_year[y] = num
            if is_recupero_ct:
                recupero_ct_by_year[y] = num

    return residual_equipos_by_year, recupero_ct_by_year


def _resolve_workbook_path(base_dir: str, *candidates: str) -> str:
    for candidate in candidates:
        path = os.path.join(base_dir, candidate)
        if os.path.exists(path):
            return path

    normalized_candidates = {
        re.sub(r"[^a-z0-9]", "", candidate.lower())
        for candidate in candidates
    }

    for entry in os.listdir(base_dir):
        if not entry.lower().endswith(".xlsx"):
            continue
        normalized_entry = re.sub(r"[^a-z0-9]", "", entry.lower())
        if normalized_entry in normalized_candidates:
            return os.path.join(base_dir, entry)

    raise FileNotFoundError(
        f"No se encontró ninguno de los archivos esperados: {', '.join(candidates)}"
    )


def cargar_datos(base_dir: str = ".") -> dict:
    global _DATA_CACHE, _DATA_CACHE_KEY

    mz_path = _resolve_workbook_path(
        base_dir,
        "Matriz_de_viaje_1.xlsx",
        "Matriz_de_viaje.xlsx",
        "Matriz de viaje (1).xlsx",
    )
    fc_path = _resolve_workbook_path(
        base_dir,
        "Flujo_de_caja_1.xlsx",
        "Flujo_de _caja.xlsx",
        "Flujo_de_caja.xlsx",
        "Flujo de caja (1).xlsx",
    )

    cache_key = (
        os.path.abspath(mz_path),
        os.path.getmtime(mz_path),
        os.path.abspath(fc_path),
        os.path.getmtime(fc_path),
    )
    if _DATA_CACHE is not None and _DATA_CACHE_KEY == cache_key:
        return _DATA_CACHE

    mz = pd.read_excel(mz_path, sheet_name=None)
    fc = pd.read_excel(fc_path, sheet_name=None)

    od = _get_sheet(mz, "Matriz OD anual").copy()
    od["dist_km"] = od["dist_km"].astype(str).str.replace(",", ".").astype(float)

    def parse_coord(value):
        try:
            lat, lng = str(value).split(",")
            return float(lat.strip()), float(lng.strip())
        except Exception:
            return (np.nan, np.nan)

    od[["orig_lat", "orig_lng"]] = pd.DataFrame(od["origen_coor"].apply(parse_coord).tolist(), index=od.index)
    od[["dest_lat", "dest_lng"]] = pd.DataFrame(od["dest_coor"].apply(parse_coord).tolist(), index=od.index)

    conv_sheet = _get_sheet(mz, "Conversión", "Conversion", "Conversi�n")
    conv = dict(zip(conv_sheet["producto"], conv_sheet["tn_camion"]))

    estac_df = _get_sheet(mz, "Estacionalidad")
    estac = {}
    for prod, grp in estac_df.groupby("producto"):
        estac[prod] = dict(zip(grp["mes"].astype(int), grp["estacionalidad"].astype(float)))

    compat_df = _get_sheet(mz, "Compatibilidad")
    compat = {}
    for _, row in compat_df[compat_df["compatibilidad"] == 1].iterrows():
        compat.setdefault(row["producto_ida"], set()).add(row["producto_retorno"])

    limpieza = {}
    for _, row in compat_df.iterrows():
        limpieza[(row["producto_ida"], row["producto_retorno"])] = bool(row["requiere_limpieza"])

    tar_raw = _get_sheet(fc, "Tarifas_Distancia", "Tarifa_FEE", "Tarifas")
    tar_kms, tar_ars = [], []
    for _, row in tar_raw.iterrows():
        numeric_values = []
        for val in row.tolist():
            try:
                numeric_values.append(float(val))
            except Exception:
                continue
        if len(numeric_values) < 2:
            continue

        km = numeric_values[0]
        ars = max(numeric_values[1:])
        if km > 0 and km <= 5000 and ars > 0:
            tar_kms.append(km)
            tar_ars.append(ars)

    if not tar_kms or not tar_ars:
        raise ValueError("No se pudieron extraer tarifas válidas desde la hoja de tarifas del flujo de caja")

    extra_opex_by_year = {}
    extra_opex_detail_by_year = {}
    app_store_by_year = {}
    tarifa_flujocaja_by_year = {}
    fee_flujocaja_by_year = {}
    residual_equipos_by_year = {}
    recupero_ct_by_year = {}
    if "FlujodeCaja" in fc:
        (
            extra_opex_by_year,
            extra_opex_detail_by_year,
            app_store_by_year,
        ) = _extract_extra_opex_from_flujodecaja(fc["FlujodeCaja"])
        tarifa_flujocaja_by_year, fee_flujocaja_by_year = _extract_core_flujocaja_assumptions(fc["FlujodeCaja"])
        residual_equipos_by_year, recupero_ct_by_year = _extract_flujocaja_recoveries(fc["FlujodeCaja"])

    _DATA_CACHE = dict(
        od=od,
        conv=conv,
        estac=estac,
        compat=compat,
        limpieza=limpieza,
        tar_kms=np.array(tar_kms),
        tar_ars=np.array(tar_ars),
        extra_opex_by_year=extra_opex_by_year,
        extra_opex_detail_by_year=extra_opex_detail_by_year,
        app_store_by_year=app_store_by_year,
        tarifa_flujocaja_by_year=tarifa_flujocaja_by_year,
        fee_flujocaja_by_year=fee_flujocaja_by_year,
        residual_equipos_by_year=residual_equipos_by_year,
        recupero_ct_by_year=recupero_ct_by_year,
        data_cache_key=cache_key,
    )
    _DATA_CACHE_KEY = cache_key
    return _DATA_CACHE


def clasificar_flujos(data: dict) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Clasifica la Matriz OD en flujos TipoA, TipoB y TipoC."""
    od = data["od"]

    tipoA = od[
        (od["dest_prov"] == "SANTA FE")
        & (od["origen_prov"] != "SANTA FE")
        & (od["grupo"] == "Granos")
    ].copy()

    tipoB = od[
        (od["origen_prov"] == "SANTA FE")
        & (od["dest_prov"] != "SANTA FE")
        & (od["dist_km"] > 0)
        & (od["producto"].isin(RETORNO_PRODUCTOS))
    ].copy()

    tipoC_base = od[
        (od["origen_prov"] != "SANTA FE")
        & (od["dest_prov"] != "SANTA FE")
        & (od["dist_km"] > 50)
        & (od["producto"].isin(RETORNO_PRODUCTOS))
    ].copy()

    prov_granos = set(tipoA["origen_prov"].unique())
    compat = data["compat"]

    def es_compatible(row):
        if row["origen_prov"] not in prov_granos:
            return False
        for _, retornos in compat.items():
            if row["producto"] in retornos:
                return True
        return False

    tipoC = tipoC_base[tipoC_base.apply(es_compatible, axis=1)].copy()
    tipoC["dist_rosario_orig"] = tipoC.apply(
        lambda row: haversine(ROSARIO_LAT, ROSARIO_LNG, row["orig_lat"], row["orig_lng"]),
        axis=1,
    )
    tipoC["dist_rosario_dest"] = tipoC.apply(
        lambda row: haversine(ROSARIO_LAT, ROSARIO_LNG, row["dest_lat"], row["dest_lng"]),
        axis=1,
    )

    return tipoA, tipoB, tipoC