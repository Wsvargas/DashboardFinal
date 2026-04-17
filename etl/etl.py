#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL PRODUCCIÓN MENSUAL v2 - SCRIPT AUTOMÁTICO (CORREGIDO)
Transforma 3 archivos CSV en base unificada SIN perder datos

REGLAS:
  ✓ Limpia TODOS los espacios de la data
  ✓ Fechas con formato dd/mm/yyyy
  ✓ Solo lotes cerrados
  ✓ Extiende hasta Edad (venta) si faltan días
  ✓ PesoFinal usa Peso_Venta como punto final obligatorio
  ✓ AlimentoConsumido en BRL se trata como DIARIO real
  ✓ Alimento_Acumulado = suma acumulada por lote
  ✓ Costos por LoteCosto + Fecha con arrastre del último precio real
"""

import os
import re
import unicodedata
import pandas as pd
import numpy as np
from scipy.interpolate import PchipInterpolator
import warnings

warnings.filterwarnings("ignore")

# ============================================================
# CONFIG
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "data")

BRL_FILE = os.path.join(INPUT_DIR, "BRL_protein_mes_actual.csv")
KRI_GALPON_FILE = os.path.join(INPUT_DIR, "KRI_GALPON_protein_mes_actual.csv")
KRI_ALIMENTO_FILE = os.path.join(INPUT_DIR, "KRI_ALIMENTO_protein_mes_actual.csv")
BRIM_FILE = os.path.join(INPUT_DIR, "KRI_ALOJAMIENTO_protein_mes_actual.csv")
AREAS_FILE = os.path.join(INPUT_DIR, "Areas.xlsx")
OUT_XLSX = os.path.join(OUTPUT_DIR, "produccion_mes_actual.xlsx")

ENCODING = "latin-1"
PESO_MAX_OK = 6.0
UMBRAL_EVENTO_CIERRE = 0.20  # 20% de aves iniciales

audit = []

# ============================================================
# HELPERS
# ============================================================
def clean_str(s):
    """Elimina TODOS los espacios en blanco de un string."""
    if isinstance(s, str):
        return re.sub(r"\s+", "", s)
    return s


def normalize_lote(lote_str):
    """Normaliza lote."""
    if pd.isna(lote_str):
        return np.nan
    s = str(lote_str).strip().upper()
    s = s.replace(" ", "").replace("–", "-").replace("—", "-").replace("_", "-")
    s = "-".join([p for p in s.split("-") if p])
    return s


def canonical_name(s):
    """Normaliza nombres de columnas para mapeo robusto."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def parse_fecha_mmddyyyy(fecha_str):
    """
    Mantengo el nombre para no romper tu estructura,
    pero aquí parsea correctamente dd/mm/yyyy.
    """
    if pd.isna(fecha_str):
        return pd.NaT
    try:
        dt = pd.to_datetime(fecha_str, format="%d/%m/%Y", errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(fecha_str, dayfirst=True, errors="coerce")
        return dt
    except Exception:
        return pd.NaT


def to_float(s):
    """Convierte a float."""
    if pd.isna(s):
        return np.nan
    try:
        s = str(s).strip().replace(",", ".").replace("%", "")
        return float(s)
    except Exception:
        return np.nan


def limpiar_peso_mayor_10(peso_val):
    """Corrige pesos > 10."""
    if pd.isna(peso_val) or peso_val == 0:
        return peso_val

    peso = float(peso_val)
    if peso <= 10:
        return peso

    divisiones = 0
    while peso > PESO_MAX_OK and divisiones < 5:
        peso = peso / 10.0
        divisiones += 1

    return peso if peso > 0.05 else 0.0


def crear_lote_sin_sexo(lote_completo):
    """Extrae GRANJA-LOTE-GALPON sin SEXO."""
    if pd.isna(lote_completo):
        return np.nan

    partes = str(lote_completo).split("-")

    if len(partes) == 4 and partes[-1].upper() in ["M", "H", "S"]:
        return "-".join(partes[:3])

    if len(partes) == 3:
        return lote_completo

    return np.nan


def crear_lote_costo(lote_completo):
    """Extrae solo GRANJA-LOTE para cruce con KRI_ALIMENTO."""
    if pd.isna(lote_completo):
        return np.nan

    partes = str(lote_completo).split("-")
    if len(partes) >= 2:
        return f"{partes[0]}-{partes[1]}"
    return np.nan


def validar_columnas(df, requeridas, nombre_df):
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise ValueError(f"{nombre_df} no contiene columnas requeridas: {faltantes}")


# ============================================================
# PASO 1: TRANSFORMAR BRL
# ============================================================
def transformar_brl():
    print("\n[1/9] Leyendo y transformando BRL...")

    df = pd.read_csv(BRL_FILE, encoding=ENCODING)
    df.columns = [col.strip() for col in df.columns]

    n_original = len(df)

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].apply(clean_str)

    rename_map = {}
    for col in df.columns:
        cc = canonical_name(col)

        if cc == "lotecompleto":
            rename_map[col] = "LoteCompleto"
        elif cc == "granja":
            rename_map[col] = "Granja"
        elif cc == "galpon":
            rename_map[col] = "Galpon"
        elif cc == "nombregranja":
            rename_map[col] = "NombreGranja"
        elif cc == "edad":
            rename_map[col] = "Edad"
        elif cc == "peso":
            rename_map[col] = "Peso"
        elif cc == "mortalidad":
            rename_map[col] = "Mortalidad"
        elif cc == "descarte":
            rename_map[col] = "Descarte"
        elif cc == "tipoalimento":
            rename_map[col] = "TipoAlimento"
        elif cc == "alimentoconsumido":
            rename_map[col] = "AlimentoConsumido"
        elif cc == "tipogranjero":
            rename_map[col] = "TipoGranjero"
        elif cc in ["fechatransaccion", "fecha"]:
            rename_map[col] = "FechaTransaccion"

    df = df.rename(columns=rename_map)

    validar_columnas(
        df,
        ["LoteCompleto", "Edad", "Peso", "Mortalidad", "Descarte", "AlimentoConsumido", "FechaTransaccion"],
        "BRL"
    )

    df["LoteCompleto"] = df["LoteCompleto"].apply(normalize_lote)
    df["LoteCompleto_sin_sexo"] = df["LoteCompleto"].apply(crear_lote_sin_sexo)
    df["LoteCosto"] = df["LoteCompleto"].apply(crear_lote_costo)

    df["FechaTransaccion"] = df["FechaTransaccion"].apply(parse_fecha_mmddyyyy)

    df["Edad"] = df["Edad"].apply(to_float)
    df["Peso"] = df["Peso"].apply(to_float)
    df["Mortalidad"] = df["Mortalidad"].apply(to_float).fillna(0)
    df["Descarte"] = df["Descarte"].apply(to_float).fillna(0)
    df["AlimentoConsumido"] = df["AlimentoConsumido"].apply(to_float).fillna(0)

    df["Peso"] = df["Peso"].apply(limpiar_peso_mayor_10)

    df["Zona"] = df["LoteCompleto"].apply(
        lambda x: "BUC" if str(x).startswith("BUC") else ("STO" if str(x).startswith("STO") else "OTRO")
    )

    if "TipoGranjero" not in df.columns:
        df["TipoGranjero"] = np.nan

    df["TipoGranjero_Propia"] = (df["TipoGranjero"] == "GranjaPropia").astype(int)
    df["TipoGranjero_PCA"] = (df["TipoGranjero"] == "PCA").astype(int)

    edad_min_por_lote = df.groupby("LoteCompleto")["Edad"].min()
    lotes_validos = edad_min_por_lote[edad_min_por_lote == 1].index
    df = df[df["LoteCompleto"].isin(lotes_validos)].copy()

    df = df[df["Edad"] > 0].copy()

    df = df.drop(columns=["Temperatura Baja", "Temperatura Alta"], errors="ignore")

    df = df.sort_values(["LoteCompleto", "Edad", "FechaTransaccion"]).reset_index(drop=True)

    df["MortalidadDescarte_Diario"] = df["Mortalidad"] + df["Descarte"]
    df["delta_negativo"] = (df["AlimentoConsumido"] < 0).astype(int)
    df["alimento_dia_kg"] = df["AlimentoConsumido"].fillna(0).clip(lower=0)

    df["Alimento_Acumulado"] = df.groupby("LoteCompleto")["alimento_dia_kg"].cumsum()
    df["MortalidadDescarte_Acumulado"] = df.groupby("LoteCompleto")["MortalidadDescarte_Diario"].cumsum()

    n_final = len(df)
    audit.append(f"BRL: {n_original} → {n_final} registros ({n_original - n_final} eliminados)")

    print(f"   ✓ {n_final} registros válidos")
    return df


# ============================================================
# PASO 2: TRANSFORMAR KRI_GALPON
# ============================================================
def transformar_kri_galpon():
    print("[2/9] Leyendo y transformando KRI_GALPON...")

    df = pd.read_csv(KRI_GALPON_FILE, encoding=ENCODING)
    df.columns = [col.strip() for col in df.columns]

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].apply(clean_str)

    rename_map = {}
    for col in df.columns:
        cc = canonical_name(col)

        if cc in ["lotecomplejo", "lotecompleto"]:
            rename_map[col] = "LoteCompleto_sin_sexo"
        elif cc == "galpon":
            rename_map[col] = "Galpon"
        elif cc == "cierredecampana":
            rename_map[col] = "Cierre de campaña"
        elif cc == "fecharecepcion":
            rename_map[col] = "Fecha recepción"
        elif cc == "alojamientototal":
            rename_map[col] = "Alojamiento Total"
        elif cc == "avesplanta":
            rename_map[col] = "Aves Planta"
        elif cc == "edadventa":
            rename_map[col] = "Edad (venta)"
        elif cc == "avesneto":
            rename_map[col] = "Aves Neto"
        elif cc == "kilosplanta":
            rename_map[col] = "Kilos Planta"
        elif cc == "kilosneto":
            rename_map[col] = "Kilos Neto"
        elif cc == "consalimtotal":
            rename_map[col] = "Cons Alim Total"
        elif cc == "convreal":
            rename_map[col] = "Conv. Real"
        elif cc == "nombregranja":
            rename_map[col] = "NombreGranja"

    df = df.rename(columns=rename_map)

    validar_columnas(df, ["LoteCompleto_sin_sexo"], "KRI_GALPON")

    df["LoteCompleto_sin_sexo"] = df["LoteCompleto_sin_sexo"].apply(normalize_lote)

    if "Cierre de campaña" in df.columns:
        df["Cierre de campaña"] = df["Cierre de campaña"].apply(parse_fecha_mmddyyyy)
    if "Fecha recepción" in df.columns:
        df["Fecha recepción"] = df["Fecha recepción"].apply(parse_fecha_mmddyyyy)

    numeric_cols = [
        "Alojamiento Total", "Aves Planta", "Edad (venta)", "Aves Neto",
        "Kilos Planta", "Kilos Neto", "Cons Alim Total", "Conv. Real"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(to_float)

    if "Kilos Neto" in df.columns and "Aves Planta" in df.columns:
        df["Peso_Venta"] = df["Kilos Neto"] / df["Aves Planta"]
        df["Peso_Venta"] = df["Peso_Venta"].replace([np.inf, -np.inf], np.nan)
    else:
        df["Peso_Venta"] = np.nan

    if "Edad (venta)" in df.columns:
        df["Cerrado"] = (df["Edad (venta)"] > 0).astype(int)
    else:
        df["Cerrado"] = 0

    if "Aves Planta" in df.columns:
        df["Aves_Iniciales"] = df["Aves Planta"]
    else:
        df["Aves_Iniciales"] = np.nan

    audit.append(f"KRI_GALPON: {len(df)} registros")
    print(f"   ✓ {len(df)} registros")
    return df


# ============================================================
# PASO 3: CRUZAR BRL + KRI_GALPON Y SOLO CERRADOS
# ============================================================
def cruzar_brl_galpon(brl, kri_gal):
    print("[3/9] Cruzando BRL + KRI_GALPON...")

    columnas_merge = [
        "LoteCompleto_sin_sexo", "Edad (venta)", "Peso_Venta", "Cerrado",
        "Aves_Iniciales", "Aves Neto", "Kilos Neto", "NombreGranja", "Fecha recepción"
    ]
    columnas_existentes = [c for c in columnas_merge if c in kri_gal.columns]

    df = brl.merge(
        kri_gal[columnas_existentes],
        on="LoteCompleto_sin_sexo",
        how="left"
    )

    df = df.sort_values(["LoteCompleto", "Edad", "FechaTransaccion"]).reset_index(drop=True)

    for col in ["Edad (venta)", "Peso_Venta", "Cerrado", "Aves_Iniciales", "Aves Neto", "Kilos Neto", "Fecha recepción"]:
        if col in df.columns:
            df[col] = df.groupby("LoteCompleto")[col].transform(lambda x: x.ffill().bfill())

    if "Cerrado" in df.columns:
        df["Cerrado"] = df["Cerrado"].fillna(0).astype(int)
    else:
        df["Cerrado"] = 0

    n_cerrados = int((df["Cerrado"] == 1).sum() / max(df.groupby("LoteCompleto").size().mean(), 1))
    n_abiertos = df["LoteCompleto"].nunique() - n_cerrados
    audit.append(f"Lotes cerrados: ~{n_cerrados} | Lotes abiertos: ~{n_abiertos}")

    if "Aves_Iniciales" in df.columns:
        df["Aves_vivas"] = np.where(
            df["Aves_Iniciales"].notna(),
            df["Aves_Iniciales"] - df["MortalidadDescarte_Acumulado"],
            np.nan
        )
    else:
        df["Aves_vivas"] = np.nan

    audit.append(f"Cruce BRL+GALPON: {len(df)} registros (cerrados + abiertos)")
    print("   ✓ Cruzado, cerrados y abiertos conservados")
    return df


# ============================================================
# PASO 4: EXTENDER CERRADOS HASTA EDAD DE VENTA
# ============================================================
def extender_lotes_cerrados_hasta_venta(df):
    print("[4/9] Extendiendo lotes cerrados hasta Edad (venta)...")

    bloques = []
    filas_agregadas = 0

    for lote in df["LoteCompleto"].dropna().unique():
        lote_df = df[df["LoteCompleto"] == lote].copy()
        lote_df = lote_df.sort_values(["Edad", "FechaTransaccion"]).reset_index(drop=True)
        lote_df["EsExtendido"] = 0

        edad_max_brl = int(lote_df["Edad"].max())
        edad_venta = lote_df["Edad (venta)"].dropna().iloc[0] if lote_df["Edad (venta)"].notna().any() else np.nan

        if pd.isna(edad_venta):
            bloques.append(lote_df)
            continue

        edad_venta = int(edad_venta)

        # si ya llega o supera la edad de venta, no agregamos filas
        if edad_venta <= edad_max_brl:
            # pero igual cortamos después de la edad de venta
            lote_df = lote_df[lote_df["Edad"] <= edad_venta].copy()
            bloques.append(lote_df)
            continue

        ultimo = lote_df.iloc[-1].copy()
        nuevas_filas = []
        fecha_base = ultimo["FechaTransaccion"]

        for nueva_edad in range(edad_max_brl + 1, edad_venta + 1):
            nueva = ultimo.copy()
            nueva["Edad"] = nueva_edad
            nueva["EsExtendido"] = 1

            if pd.notna(fecha_base):
                nueva["FechaTransaccion"] = fecha_base + pd.Timedelta(days=(nueva_edad - edad_max_brl))

            # no hay dato real de peso base en BRL
            nueva["Peso"] = 0

            # en días agregados no hay mortalidad/descarte real
            nueva["Mortalidad"] = 0
            nueva["Descarte"] = 0
            nueva["MortalidadDescarte_Diario"] = 0

            # se alargan los datos del último día conocido
            nueva["AlimentoConsumido"] = ultimo["AlimentoConsumido"]
            nueva["alimento_dia_kg"] = ultimo["AlimentoConsumido"]

            nuevas_filas.append(nueva)

        if nuevas_filas:
            lote_ext = pd.concat([lote_df, pd.DataFrame(nuevas_filas)], ignore_index=True)
            filas_agregadas += len(nuevas_filas)
        else:
            lote_ext = lote_df.copy()

        bloques.append(lote_ext)

    if bloques:
        df = pd.concat(bloques, ignore_index=True)
    else:
        df = df.iloc[0:0].copy()

    df = df.sort_values(["LoteCompleto", "Edad", "FechaTransaccion"]).reset_index(drop=True)

    audit.append(f"Extensión a edad de venta: {filas_agregadas} filas agregadas")
    print(f"   ✓ {filas_agregadas} filas extendidas")
    return df


# ============================================================
# PASO 5: CALCULAR PESO FINAL HASTA PESO_VENTA
# ============================================================
def calcular_peso_final(df):
    print("[5/9] Calculando PesoFinal (forzando Peso_Venta en Edad venta)...")

    df = df.copy()
    df["PesoFinal"] = np.nan

    for lote in df["LoteCompleto"].dropna().unique():
        mask = df["LoteCompleto"] == lote
        lote_data = df.loc[mask].copy()
        idx_originales = lote_data.index.tolist()
        lote_data = lote_data.sort_values("Edad").reset_index(drop=True)

        edades_todas = lote_data["Edad"].values.astype(float)
        pesos_todos = lote_data["Peso"].values.astype(float)

        reales_mask = np.isfinite(pesos_todos) & (pesos_todos > 0)
        edades_reales = edades_todas[reales_mask]
        pesos_reales = pesos_todos[reales_mask]

        peso_inicial = 0.046

        if len(edades_reales) == 0:
            for i, idx_real in enumerate(idx_originales):
                if lote_data.loc[i, "Edad"] == 1:
                    df.loc[idx_real, "PesoFinal"] = peso_inicial
            continue

        if edades_reales[0] > 1:
            edades_control = list(np.concatenate([[1.0], edades_reales]))
            pesos_control = list(np.concatenate([[peso_inicial], pesos_reales]))
        else:
            edades_control = list(edades_reales.copy())
            pesos_control = list(pesos_reales.copy())
            pesos_control[0] = max(pesos_control[0], peso_inicial)

        edad_venta = lote_data["Edad (venta)"].dropna().iloc[0] if lote_data["Edad (venta)"].notna().any() else np.nan
        peso_venta = lote_data["Peso_Venta"].dropna().iloc[0] if lote_data["Peso_Venta"].notna().any() else np.nan

        # Forzar punto final obligatorio en la edad de venta con el peso de venta
        if pd.notna(edad_venta) and pd.notna(peso_venta):
            edad_venta = float(edad_venta)
            peso_venta = float(peso_venta)

            pares = {float(e): float(p) for e, p in zip(edades_control, pesos_control)}
            pares[edad_venta] = peso_venta

            control_df = pd.DataFrame({
                "Edad": list(pares.keys()),
                "Peso": list(pares.values())
            }).sort_values("Edad")
        else:
            control_df = pd.DataFrame({
                "Edad": edades_control,
                "Peso": pesos_control
            }).sort_values("Edad")

        control_df = control_df.groupby("Edad", as_index=False).last().sort_values("Edad")

        edades_control = control_df["Edad"].values.astype(float)
        pesos_control = control_df["Peso"].values.astype(float)

        pesos_control = np.maximum.accumulate(pesos_control)

        if len(edades_control) == 1:
            for i, idx_real in enumerate(idx_originales):
                edad = edades_todas[i]
                if edad == edades_control[0]:
                    df.loc[idx_real, "PesoFinal"] = pesos_control[0]
                elif edad >= 1 and edad < edades_control[0]:
                    df.loc[idx_real, "PesoFinal"] = np.interp(
                        edad,
                        [1.0, edades_control[0]],
                        [peso_inicial, pesos_control[0]]
                    )
                else:
                    df.loc[idx_real, "PesoFinal"] = np.nan
            continue

        try:
            interp = PchipInterpolator(edades_control, pesos_control, extrapolate=False)

            pesos_interp = []
            for edad in edades_todas:
                if edad < edades_control[0]:
                    val = np.interp(edad, [1.0, edades_control[0]], [peso_inicial, pesos_control[0]])
                elif edad <= edades_control[-1]:
                    val = float(interp(edad))
                else:
                    val = np.nan
                pesos_interp.append(val)

            pesos_interp = np.array(pesos_interp, dtype=float)

            valid_mask = np.isfinite(pesos_interp)
            if valid_mask.any():
                pesos_interp[valid_mask] = np.maximum.accumulate(pesos_interp[valid_mask])

            # Forzar exactamente el peso de venta en la última edad de venta
            if pd.notna(edad_venta) and pd.notna(peso_venta):
                for i, edad in enumerate(edades_todas):
                    if edad == edad_venta:
                        pesos_interp[i] = peso_venta

            for i, idx_real in enumerate(idx_originales):
                df.loc[idx_real, "PesoFinal"] = pesos_interp[i]

        except Exception:
            pesos_interp = []
            for edad in edades_todas:
                if edad >= edades_control[0] and edad <= edades_control[-1]:
                    val = np.interp(edad, edades_control, pesos_control)
                elif edad < edades_control[0]:
                    val = np.interp(edad, [1.0, edades_control[0]], [peso_inicial, pesos_control[0]])
                else:
                    val = np.nan
                pesos_interp.append(val)

            pesos_interp = np.array(pesos_interp, dtype=float)
            valid_mask = np.isfinite(pesos_interp)
            if valid_mask.any():
                pesos_interp[valid_mask] = np.maximum.accumulate(pesos_interp[valid_mask])

            if pd.notna(edad_venta) and pd.notna(peso_venta):
                for i, edad in enumerate(edades_todas):
                    if edad == edad_venta:
                        pesos_interp[i] = peso_venta

            for i, idx_real in enumerate(idx_originales):
                df.loc[idx_real, "PesoFinal"] = pesos_interp[i]

    audit.append(f"PesoFinal: calculado hasta Peso_Venta, {df['PesoFinal'].notna().sum()} con datos")
    print("   ✓ PesoFinal calculado hasta Edad (venta) con Peso_Venta final")
    return df


def recortar_hasta_ultimo_peso_final(df):
    print("[5.1/9] Recortando después del último PesoFinal válido...")

    bloques = []
    eliminados = 0

    for lote in df["LoteCompleto"].dropna().unique():
        lote_df = df[df["LoteCompleto"] == lote].copy()
        edades_validas = lote_df.loc[lote_df["PesoFinal"].notna(), "Edad"]

        if len(edades_validas) == 0:
            eliminados += len(lote_df)
            continue

        ultima_edad_valida = edades_validas.max()
        lote_recortado = lote_df[lote_df["Edad"] <= ultima_edad_valida].copy()
        eliminados += len(lote_df) - len(lote_recortado)
        bloques.append(lote_recortado)

    if bloques:
        df = pd.concat(bloques, ignore_index=True)
    else:
        df = df.iloc[0:0].copy()

    df = df.sort_values(["LoteCompleto", "Edad", "FechaTransaccion"]).reset_index(drop=True)

    audit.append(f"Recorte por PesoFinal: {eliminados} registros eliminados")
    print(f"   ✓ {eliminados} registros recortados")
    return df


def eliminar_lotes_con_baja_peso(df, tolerancia=1e-9):
    print("[5.15/9] Eliminando lotes con baja de PesoFinal...")

    df = df.copy()
    df = df.sort_values(["LoteCompleto", "Edad", "FechaTransaccion"]).reset_index(drop=True)

    lotes_con_baja = []

    for lote, lote_df in df.groupby("LoteCompleto", dropna=True, sort=False):
        lote_df = lote_df.sort_values(["Edad", "FechaTransaccion"]).copy()

        # Solo eliminar por baja de peso en lotes cerrados
        # (lotes abiertos pueden tener mediciones temporales bajas)
        es_cerrado = lote_df["Cerrado"].fillna(0).astype(int).max() == 1
        if not es_cerrado:
            continue

        # Diferencia contra el peso anterior
        diffs = lote_df["PesoFinal"].diff()

        # Si alguna diferencia es negativa, hay pérdida de peso
        if (diffs < -tolerancia).any():
            lotes_con_baja.append(lote)

    if lotes_con_baja:
        antes = len(df)
        df = df[~df["LoteCompleto"].isin(lotes_con_baja)].copy()
        despues = len(df)

        audit.append(
            f"Lotes eliminados por baja de PesoFinal: {len(lotes_con_baja)} lotes, "
            f"{antes - despues} registros eliminados"
        )

        # Guardar también los nombres en auditoría
        for lote in lotes_con_baja:
            audit.append(f"  - Eliminado por baja de peso: {lote}")

        print(f"   ✓ {len(lotes_con_baja)} lotes eliminados por baja de peso")
    else:
        audit.append("Lotes eliminados por baja de PesoFinal: 0")
        print("   ✓ No se detectaron lotes con baja de peso")

    return df

def recalcular_series_base(df):
    print("[5.2/9] Recalculando series base...")

    df = df.copy()
    df = df.sort_values(["LoteCompleto", "Edad", "FechaTransaccion"]).reset_index(drop=True)

    df["delta_negativo"] = (df["AlimentoConsumido"] < 0).astype(int)
    df["alimento_dia_kg"] = df["AlimentoConsumido"].fillna(0).clip(lower=0)
    df["Alimento_Acumulado"] = df.groupby("LoteCompleto")["alimento_dia_kg"].cumsum()

    df["MortalidadDescarte_Diario_Raw"] = df["Mortalidad"].fillna(0) + df["Descarte"].fillna(0)

    if "Aves_Iniciales" in df.columns:
        df["evento_cierre_masivo"] = np.where(
            df["Aves_Iniciales"].notna() &
            (df["MortalidadDescarte_Diario_Raw"] > (df["Aves_Iniciales"] * UMBRAL_EVENTO_CIERRE)),
            1,
            0
        )
    else:
        df["evento_cierre_masivo"] = 0

    df["MortalidadDescarte_Diario"] = np.where(
        df["evento_cierre_masivo"] == 1,
        0,
        df["MortalidadDescarte_Diario_Raw"]
    )

    df["MortalidadDescarte_Acumulado"] = df.groupby("LoteCompleto")["MortalidadDescarte_Diario"].cumsum()

    if "Aves_Iniciales" in df.columns:
        df["Aves_vivas"] = np.where(
            df["Aves_Iniciales"].notna(),
            df["Aves_Iniciales"] - df["MortalidadDescarte_Acumulado"],
            np.nan
        )
    else:
        df["Aves_vivas"] = np.nan

    df["Aves_vivas"] = df["Aves_vivas"].clip(lower=0)

    audit.append("Series base recalculadas correctamente")
    print("   ✓ Series base recalculadas")
    return df


# ============================================================
# PASO 6: TRANSFORMAR KRI_ALIMENTO
# ============================================================
def transformar_kri_alimento():
    print("[6/9] Leyendo y transformando KRI_ALIMENTO...")

    df = pd.read_csv(KRI_ALIMENTO_FILE, encoding=ENCODING)
    df.columns = [col.strip() for col in df.columns]

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].apply(clean_str)

    rename_map = {}
    for col in df.columns:
        cc = canonical_name(col)
        if cc == "fechatransaccion":
            rename_map[col] = "FechaTransaccion"
        elif cc == "lotecompleto":
            rename_map[col] = "LoteCompleto"
        elif cc == "costo":
            rename_map[col] = "Costo"
        elif cc == "netorelativo":
            rename_map[col] = "Neto Relativo"

    df = df.rename(columns=rename_map)

    validar_columnas(df, ["FechaTransaccion", "LoteCompleto", "Neto Relativo", "Costo"], "KRI_ALIMENTO")

    df["FechaTransaccion"] = df["FechaTransaccion"].apply(parse_fecha_mmddyyyy)
    df["LoteCompleto"] = df["LoteCompleto"].apply(normalize_lote)

    df["LoteCompleto_sin_sexo"] = df["LoteCompleto"].apply(crear_lote_sin_sexo)
    df["LoteCosto"] = df["LoteCompleto"].apply(crear_lote_costo)

    df["Neto Relativo"] = df["Neto Relativo"].apply(to_float)
    df["Costo"] = df["Costo"].apply(to_float)

    n_antes = len(df)
    df = df[(df["Neto Relativo"] > 0) & (df["Costo"] > 0)].copy()
    df = df.sort_values(["LoteCosto", "FechaTransaccion"]).reset_index(drop=True)
    n_despues = len(df)

    audit.append(f"KRI_ALIMENTO: {n_antes} → {n_despues} registros válidos")
    print(f"   ✓ {n_despues} registros válidos")
    return df


# ============================================================
# PASO 7: PRECIOS PONDERADOS
# ============================================================
def calcular_precios_ponderados(kri_ali):
    print("[7/9] Calculando precios ponderados cronológicos...")

    trabajo = kri_ali.copy()
    trabajo["FechaTransaccion"] = pd.to_datetime(trabajo["FechaTransaccion"], errors="coerce").dt.normalize()

    trabajo = trabajo[
        trabajo["LoteCosto"].notna() &
        trabajo["FechaTransaccion"].notna() &
        trabajo["Neto Relativo"].notna() &
        trabajo["Costo"].notna() &
        (trabajo["Neto Relativo"] > 0) &
        (trabajo["Costo"] > 0)
    ].copy()

    precios_dia = trabajo.groupby(["LoteCosto", "FechaTransaccion"]).agg({
        "Neto Relativo": "sum",
        "Costo": "sum"
    }).reset_index()

    precios_dia["precio_kg_real"] = precios_dia["Costo"] / precios_dia["Neto Relativo"]
    precios_dia["FechaPrecioAplicado"] = precios_dia["FechaTransaccion"]
    precios_dia = precios_dia.sort_values(["LoteCosto", "FechaTransaccion"]).reset_index(drop=True)

    promedio_lote = trabajo.groupby("LoteCosto").agg({
        "Neto Relativo": "sum",
        "Costo": "sum"
    }).reset_index()

    promedio_lote["precio_promedio_lote"] = promedio_lote["Costo"] / promedio_lote["Neto Relativo"]
    promedio_lote = promedio_lote[["LoteCosto", "precio_promedio_lote"]]

    audit.append(
        f"Precios cronológicos: {len(precios_dia)} fechas reales y {len(promedio_lote)} promedios lote"
    )

    print(f"   ✓ {len(precios_dia)} precios reales por fecha")
    return precios_dia, promedio_lote


# ============================================================
# PASO 8: CRUZAR BRL + PRECIOS
# ============================================================
def cruzar_brl_precios(df, precios_dia, promedio_lote):
    print("[8/9] Cruzando BRL con costos...")

    df = df.copy()
    df["FechaTransaccion"] = pd.to_datetime(df["FechaTransaccion"], errors="coerce").dt.normalize()
    df = df.sort_values(["LoteCompleto", "Edad", "FechaTransaccion"]).reset_index(drop=True)

    precios_dia = precios_dia.copy()
    precios_dia["FechaTransaccion"] = pd.to_datetime(precios_dia["FechaTransaccion"], errors="coerce").dt.normalize()
    precios_dia["FechaPrecioAplicado"] = pd.to_datetime(precios_dia["FechaPrecioAplicado"], errors="coerce").dt.normalize()

    refs = precios_dia[["LoteCosto", "FechaTransaccion", "FechaPrecioAplicado", "precio_kg_real"]].copy()
    refs = refs.sort_values(["LoteCosto", "FechaTransaccion"]).reset_index(drop=True)

    bloques = []

    for lote_costo, base_lote in df.groupby("LoteCosto", dropna=False, sort=False):
        base_lote = base_lote.copy()

        base_valid = base_lote[base_lote["FechaTransaccion"].notna()].copy()
        base_invalid = base_lote[base_lote["FechaTransaccion"].isna()].copy()

        partes = []

        if not base_invalid.empty:
            base_invalid["FechaPrecioAplicado"] = pd.NaT
            base_invalid["precio_kg_real"] = np.nan
            base_invalid["precio_fecha_exacta"] = 0
            base_invalid["precio_arrastrado"] = 0
            partes.append(base_invalid)

        if not base_valid.empty:
            base_valid = base_valid.sort_values("FechaTransaccion").copy()

            if pd.isna(lote_costo):
                base_valid["FechaPrecioAplicado"] = pd.NaT
                base_valid["precio_kg_real"] = np.nan
                base_valid["precio_fecha_exacta"] = 0
                base_valid["precio_arrastrado"] = 0
                partes.append(base_valid)
            else:
                ref_lote = refs[refs["LoteCosto"] == lote_costo][
                    ["FechaTransaccion", "FechaPrecioAplicado", "precio_kg_real"]
                ].copy().sort_values("FechaTransaccion")

                if ref_lote.empty:
                    base_valid["FechaPrecioAplicado"] = pd.NaT
                    base_valid["precio_kg_real"] = np.nan
                    base_valid["precio_fecha_exacta"] = 0
                    base_valid["precio_arrastrado"] = 0
                    partes.append(base_valid)
                else:
                    merged = pd.merge_asof(
                        base_valid,
                        ref_lote,
                        on="FechaTransaccion",
                        direction="backward",
                        allow_exact_matches=True
                    )

                    merged["precio_fecha_exacta"] = (
                        merged["FechaPrecioAplicado"].notna() &
                        (merged["FechaTransaccion"] == merged["FechaPrecioAplicado"])
                    ).astype(int)

                    merged["precio_arrastrado"] = (
                        merged["FechaPrecioAplicado"].notna() &
                        (merged["FechaTransaccion"] > merged["FechaPrecioAplicado"])
                    ).astype(int)

                    partes.append(merged)

        if len(partes) > 0:
            lote_final = pd.concat(partes, ignore_index=False)
            bloques.append(lote_final)

    if bloques:
        df = pd.concat(bloques, ignore_index=False).sort_index().reset_index(drop=True)
    else:
        df = df.iloc[0:0].copy()

    df = df.merge(promedio_lote, on="LoteCosto", how="left")

    df["precio_kg"] = df["precio_kg_real"]
    df["precio_es_real"] = df["precio_kg"].notna().astype(int)

    df["delta_negativo"] = (df["AlimentoConsumido"] < 0).astype(int)
    df["alimento_dia_kg"] = df["AlimentoConsumido"].fillna(0).clip(lower=0)

    df = df.sort_values(["LoteCompleto", "Edad", "FechaTransaccion"]).reset_index(drop=True)
    df["Alimento_Acumulado"] = df.groupby("LoteCompleto")["alimento_dia_kg"].cumsum()

    df["costo_alimento_dia"] = np.where(
        df["precio_kg"].notna(),
        df["alimento_dia_kg"] * df["precio_kg"],
        np.nan
    )

    df["costo_alimento_acumulado"] = np.nan

    for codigo in df["LoteCompleto"].dropna().unique():
        mask = df["LoteCompleto"] == codigo
        serie = df.loc[mask, "costo_alimento_dia"].copy()

        acum = serie.fillna(0).cumsum()
        acum[serie.isna()] = np.nan

        df.loc[mask, "costo_alimento_acumulado"] = acum.values

    exactos = int(df["precio_fecha_exacta"].fillna(0).sum())
    arrastrados = int(df["precio_arrastrado"].fillna(0).sum())
    sin_precio = int(df["precio_kg"].isna().sum())

    audit.append(
        f"Costos cronológicos: {exactos} exactos, {arrastrados} arrastrados, {sin_precio} sin precio"
    )

    print("   ✓ Costos asignados cronológicamente")
    return df


# ============================================================
# PASO 8.1: PROCESAR ARCHIVO BRIM (REPRODUCTORAS)
# ============================================================
def transformar_brim():
    print("\n[8.1/9] Procesando archivo BRIM (reproductoras)...")

    if not os.path.exists(BRIM_FILE):
        print(f"   ⚠ Archivo BRIM no encontrado: {BRIM_FILE}")
        print("   → Las columnas de reproductora quedarán vacías")
        return None

    df = pd.read_csv(BRIM_FILE, encoding=ENCODING, sep=None, engine="python")

    # Limpiar espacios en nombres de columna
    df.columns = [c.strip() for c in df.columns]

    # Limpiar espacios en columnas clave (explícito, compatible con todas las versiones de pandas)
    for col in df.columns:
        try:
            stripped = df[col].astype(str).str.strip()
            # Solo aplicar si la columna NO es puramente numérica
            if not pd.to_numeric(stripped, errors="coerce").notna().all():
                df[col] = stripped.where(stripped != "nan", other=pd.NA)
        except Exception:
            pass

    # Verificar columnas mínimas necesarias
    cols_req = ["Galpon/Corral", "Aves Alojadas", "Edad", "Días_guarda", "Raza"]
    faltantes = [c for c in cols_req if c not in df.columns]
    if faltantes:
        print(f"   ❌ Columnas faltantes en BRIM: {faltantes}")
        return None

    # Convertir a numérico
    df["Aves Alojadas"] = pd.to_numeric(df["Aves Alojadas"], errors="coerce")
    df["Edad"] = pd.to_numeric(df["Edad"], errors="coerce")
    df["Días_guarda"] = pd.to_numeric(df["Días_guarda"], errors="coerce")

    # Eliminar filas sin peso de ponderación
    df = df.dropna(subset=["Aves Alojadas", "Galpon/Corral"])
    df = df[df["Aves Alojadas"] > 0]

    # Renombrar y normalizar clave de join (igual que normalize_lote en BRL)
    df = df.rename(columns={"Galpon/Corral": "LoteCompleto"})
    df["LoteCompleto"] = df["LoteCompleto"].apply(normalize_lote)

    # ── Promedios ponderados por galpon ──────────────────────────────────────
    def wprom(grp, col_val, col_peso):
        mask = grp[col_val].notna()
        if mask.sum() == 0:
            return np.nan
        return (grp.loc[mask, col_val] * grp.loc[mask, col_peso]).sum() / grp.loc[mask, col_peso].sum()

    # Columna de aves totales por galpon (para Aves_Iniciales de lotes abiertos)
    total_house_col = next(
        (c for c in df.columns if "total" in c.lower() and "house" in c.lower()),
        None
    )
    if total_house_col:
        df[total_house_col] = pd.to_numeric(df[total_house_col], errors="coerce")

    def _agg_grupo(grp, key_col, key_val):
        total_aves = grp["Aves Alojadas"].sum()
        row = {key_col: key_val}
        row["ponderado_edad_reproductora"] = wprom(grp, "Edad", "Aves Alojadas")
        row["ponderado_dias_guarda"]       = wprom(grp, "Días_guarda", "Aves Alojadas")
        razas_validas = [r for r in grp["Raza"].dropna().unique() if str(r).strip() != ""]
        for raza in razas_validas:
            aves_raza = grp.loc[grp["Raza"] == raza, "Aves Alojadas"].sum()
            row[f"porcentaje_raza_{raza}"] = round((aves_raza / total_aves) * 100, 2) if total_aves > 0 else np.nan
        # Aves totales del galpón (para usarse como Aves_Iniciales en lotes sin KRI_GALPON)
        if total_house_col:
            row["aves_totales_brim"] = grp[total_house_col].max()
        else:
            row["aves_totales_brim"] = total_aves
        return row

    # ── Nivel 1: por LoteCompleto (join exacto) ──────────────────
    agg_rows = []
    for lote, grp in df.groupby("LoteCompleto"):
        agg_rows.append(_agg_grupo(grp, "LoteCompleto", lote))
    brim_agg = pd.DataFrame(agg_rows)

    # ── Nivel 2: por granja+número_galpon (fallback para distinto mes) ──
    # Extrae: BUC3023-2602-02-S → clave BUC3023_02
    df["_granja_galpon"] = df["LoteCompleto"].apply(
        lambda x: f"{str(x).split('-')[0]}_{str(x).split('-')[2]}"
        if len(str(x).split("-")) >= 3 else str(x).split("-")[0]
    )
    agg_rows2 = []
    for gg, grp in df.groupby("_granja_galpon"):
        agg_rows2.append(_agg_grupo(grp, "_granja_galpon", gg))
    brim_agg_galpon = pd.DataFrame(agg_rows2)

    # ── Nivel 3: por granja (fallback amplio) ──────────────────
    df["_granja"] = df["LoteCompleto"].apply(lambda x: str(x).split("-")[0])
    agg_rows3 = []
    for g, grp in df.groupby("_granja"):
        agg_rows3.append(_agg_grupo(grp, "_granja", g))
    brim_agg_granja = pd.DataFrame(agg_rows3)

    # Asegurar columnas de raza en los tres niveles
    for raza_col in ["porcentaje_raza_RAP95", "porcentaje_raza_C500SF"]:
        for tbl in [brim_agg, brim_agg_galpon, brim_agg_granja]:
            if raza_col not in tbl.columns:
                tbl[raza_col] = np.nan

    print(f"   ✓ BRIM procesado: {len(brim_agg)} galpones únicos (lote), "
          f"{len(brim_agg_galpon)} (granja+galpon), {len(brim_agg_granja)} (granja)")
    print(f"   ✓ Razas encontradas: {[c for c in brim_agg.columns if c.startswith('porcentaje_raza_')]}")
    return brim_agg, brim_agg_galpon, brim_agg_granja


def cruzar_brim(df, brim_resultado):
    _BRIM_COLS = [
        "ponderado_edad_reproductora", "ponderado_dias_guarda",
        "porcentaje_raza_RAP95", "porcentaje_raza_C500SF", "aves_totales_brim"
    ]

    if brim_resultado is None:
        print("   ⚠ Sin datos BRIM — columnas de reproductora quedarán en NaN")
        for col in _BRIM_COLS:
            df[col] = np.nan
        return df

    brim_lote, brim_galpon, brim_granja = brim_resultado

    print("\n[8.2/9] Cruzando datos BRIM con producción (cascada 3 niveles)...")
    antes = len(df)

    # ── Nivel 1: join exacto por LoteCompleto ────────────────────
    brim_cols_lote = ["LoteCompleto"] + [c for c in _BRIM_COLS if c in brim_lote.columns]
    df = df.merge(brim_lote[brim_cols_lote], on="LoteCompleto", how="left")

    # ── Nivel 2: fallback por granja+galpon para lotes sin match ──
    sin_match = df["ponderado_edad_reproductora"].isna()
    if sin_match.any() and not brim_galpon.empty:
        df["_granja_galpon"] = df["LoteCompleto"].apply(
            lambda x: f"{str(x).split('-')[0]}_{str(x).split('-')[2]}"
            if len(str(x).split("-")) >= 3 else str(x).split("-")[0]
        )
        brim_cols_gg = ["_granja_galpon"] + [c for c in _BRIM_COLS if c in brim_galpon.columns]
        tmp = df[sin_match][["_granja_galpon"]].merge(
            brim_galpon[brim_cols_gg], on="_granja_galpon", how="left"
        )
        for col in _BRIM_COLS:
            if col in tmp.columns:
                df.loc[sin_match, col] = tmp[col].values
        df = df.drop(columns=["_granja_galpon"], errors="ignore")

    # ── Nivel 3: fallback solo por granja ────────────────────────
    sin_match = df["ponderado_edad_reproductora"].isna()
    if sin_match.any() and not brim_granja.empty:
        df["_granja"] = df["LoteCompleto"].apply(lambda x: str(x).split("-")[0])
        brim_cols_g = ["_granja"] + [c for c in _BRIM_COLS if c in brim_granja.columns]
        tmp = df[sin_match][["_granja"]].merge(
            brim_granja[brim_cols_g], on="_granja", how="left"
        )
        for col in _BRIM_COLS:
            if col in tmp.columns:
                df.loc[sin_match, col] = tmp[col].values
        df = df.drop(columns=["_granja"], errors="ignore")

    # ── Rellenar Aves_Iniciales con aves_totales_brim cuando esté vacío ──
    if "aves_totales_brim" in df.columns and "Aves_Iniciales" in df.columns:
        mask_sin_aves = df["Aves_Iniciales"].isna() & df["aves_totales_brim"].notna()
        df.loc[mask_sin_aves, "Aves_Iniciales"] = df.loc[mask_sin_aves, "aves_totales_brim"]
        n_rellenos = int(mask_sin_aves.sum())
        if n_rellenos > 0:
            print(f"   ✓ Aves_Iniciales rellenadas desde BRIM: {n_rellenos} registros")
            # Recalcular Aves_vivas para los lotes que ahora tienen Aves_Iniciales
            lotes_nuevos = df.loc[mask_sin_aves, "LoteCompleto"].unique()
            for lote in lotes_nuevos:
                mask_lote = df["LoteCompleto"] == lote
                aves_ini = df.loc[mask_lote, "Aves_Iniciales"].iloc[0]
                if pd.notna(aves_ini):
                    df.loc[mask_lote, "Aves_vivas"] = (
                        aves_ini - df.loc[mask_lote, "MortalidadDescarte_Acumulado"]
                    ).clip(lower=0)
            print(f"   ✓ Aves_vivas recalculadas para {len(lotes_nuevos)} lotes abiertos")

    print(f"   ✓ Join completado: {antes} filas → {len(df)} filas")
    lotes_con_brim = df.loc[df["ponderado_edad_reproductora"].notna(), "LoteCompleto"].nunique()
    lotes_sin_brim = df.loc[df["ponderado_edad_reproductora"].isna(), "LoteCompleto"].nunique()
    print(f"   ✓ Lotes con BRIM: {lotes_con_brim} | Sin BRIM: {lotes_sin_brim}")
    return df


# ============================================================
# PASO 8.3: PROCESAR ARCHIVO AREAS (QUINTIL POR GRANJA)
# ============================================================
def transformar_areas():
    print("\n[8.3/9] Procesando archivo AREAS (quintil por granja)...")

    if not os.path.exists(AREAS_FILE):
        print(f"   ⚠ Archivo AREAS no encontrado: {AREAS_FILE}")
        return None

    df = pd.read_excel(AREAS_FILE)
    df.columns = [c.strip() for c in df.columns]

    cols_req = ["Granja", "Quintil_Granja", "Tipo granja", "Zona"]
    faltantes = [c for c in cols_req if c not in df.columns]
    if faltantes:
        print(f"   ❌ Columnas faltantes en AREAS: {faltantes}")
        return None

    # Normalizar strings
    for col in ["Granja", "Quintil_Granja", "Tipo granja", "Zona"]:
        df[col] = df[col].astype(str).str.strip()

    # Normalizar TipoGranja al formato del archivo de ideales: Propia / PCA
    df["TipoGranja_norm"] = df["Tipo granja"].str.upper().map({
        "GRANJA PROPIA": "Propia",
        "PROPIA":        "Propia",
        "PCA":           "PCA",
    }).fillna("PCA")

    # Deduplicar a nivel granja (una fila por Granja)
    areas_granja = (
        df.groupby("Granja")[["Quintil_Granja", "TipoGranja_norm", "Zona"]]
        .first()
        .reset_index()
    )

    print(f"   ✓ AREAS procesado: {len(areas_granja)} granjas únicas")
    print(f"   ✓ Quintiles: {sorted(areas_granja['Quintil_Granja'].unique())}")
    return areas_granja


def cruzar_areas(df, areas_df):
    if areas_df is None or areas_df.empty:
        print("   ⚠ Sin datos AREAS — Quintil y Etiqueta_Escenario quedarán en NaN")
        df["Quintil"] = np.nan
        df["Etiqueta_Escenario"] = np.nan
        return df

    print("\n[8.4/9] Cruzando AREAS con producción...")

    # Extraer código de granja desde LoteCompleto (BUC1001-2602-02-H → BUC1001)
    df["_granja_key"] = df["LoteCompleto"].astype(str).str.split("-").str[0].str.upper()

    antes = len(df)
    # Solo traer Quintil y TipoGranja_norm (Zona ya viene del BRL)
    cols_areas = ["Granja", "Quintil_Granja", "TipoGranja_norm"]
    df = df.merge(
        areas_df[cols_areas].rename(columns={"Granja": "_granja_key"}),
        on="_granja_key",
        how="left"
    )
    df = df.drop(columns=["_granja_key"])

    lotes_con = df.loc[df["Quintil_Granja"].notna(), "LoteCompleto"].nunique()
    lotes_sin = df.loc[df["Quintil_Granja"].isna(), "LoteCompleto"].nunique()
    print(f"   ✓ Join completado: {antes} filas → {len(df)} filas")
    print(f"   ✓ Lotes con Quintil: {lotes_con} | Sin Quintil: {lotes_sin}")

    df = df.rename(columns={"Quintil_Granja": "Quintil"})
    return df


def calcular_etiqueta_escenario(df):
    """
    Construye Etiqueta_Escenario en el formato del archivo de ideales:
    {Zona}_{TipoGranja}_{Reproductora}_{Quintil}
    Ej: BUC_PCA_Adulta_Q2  |  STO_Propia_Joven_Q1
    """
    zona       = df["Zona"].astype(str).str.strip()
    tipo       = df["TipoGranja_norm"].astype(str).str.strip() if "TipoGranja_norm" in df.columns else pd.Series("PCA", index=df.index)
    repro      = df["Reproductora"].astype(str).str.strip()
    quintil    = df["Quintil"].astype(str).str.strip()

    etiqueta = zona + "_" + tipo + "_" + repro + "_" + quintil

    # Si algún componente es NaN/nan → dejar NaN
    mask_invalida = (
        zona.eq("nan") | tipo.eq("nan") | repro.eq("nan") | repro.eq("None") | quintil.eq("nan")
    )
    etiqueta[mask_invalida] = np.nan

    df["Etiqueta_Escenario"] = etiqueta
    conteo = df["Etiqueta_Escenario"].notna().sum()
    total  = len(df)
    print(f"   ✓ Etiqueta_Escenario calculada: {conteo}/{total} filas con etiqueta")
    print(f"   ✓ Etiquetas únicas: {sorted(df['Etiqueta_Escenario'].dropna().unique())[:8]} ...")
    return df


# ============================================================
# PASO 8.5: CLASIFICACIÓN REPRODUCTORA / GUARDA / ETAPA
# ============================================================
def clasificar_reproductora_guarda_etapa(df):
    df = df.copy()

    # -----------------------------
    # REPRODUCTORA (edad reproductora)
    # -----------------------------
    if "ponderado_edad_reproductora" in df.columns:
        edad_base = df["ponderado_edad_reproductora"]
    elif "edad_reproductora" in df.columns:
        edad_base = df["edad_reproductora"]
    else:
        edad_base = None

    if edad_base is not None:
        df["Reproductora"] = np.select(
            [
                edad_base < 35,
                (edad_base >= 35) & (edad_base < 51),
                (edad_base >= 51)
            ],
            ["Joven", "Adulta", "Vieja"],
            default=None
        )
    else:
        df["Reproductora"] = None

    # -----------------------------
    # GUARDA (días de guarda)
    # -----------------------------
    if "ponderado_dias_guarda" in df.columns:
        guarda_base = df["ponderado_dias_guarda"]
    elif "dias_guarda" in df.columns:
        guarda_base = df["dias_guarda"]
    else:
        guarda_base = None

    if guarda_base is not None:
        df["Guarda"] = np.select(
            [
                (guarda_base >= 3) & (guarda_base < 7),
                (guarda_base >= 7) & (guarda_base < 13),
                (guarda_base >= 13)
            ],
            ["Optima", "Moderada", "Critica"],
            default=None
        )
    else:
        df["Guarda"] = None

    # -----------------------------
    # ETAPA (edad del lote)
    # -----------------------------
    if "Edad" in df.columns:
        df["etapa"] = np.select(
            [
                (df["Edad"] >= 1) & (df["Edad"] <= 14),
                (df["Edad"] >= 15) & (df["Edad"] <= 28),
                (df["Edad"] >= 29) & (df["Edad"] <= 35),
                (df["Edad"] >= 36)
            ],
            [1, 2, 3, 0],
            default=np.nan
        )
    else:
        df["etapa"] = np.nan

    return df


# ============================================================
# PASO 9: PREPARAR SALIDA
# ============================================================
def preparar_salida(df):
    print("\n[9/9] Preparando salida...")

    df["Codigo_Unico"] = df["LoteCompleto"]
    df["Edad^2"] = df["Edad"] ** 2
    df["BUCAY"] = (df["Zona"] == "BUC").astype(int)
    df["SANTODOMINGO"] = (df["Zona"] == "STO").astype(int)

    if "Cerrado" in df.columns:
        df["Cerrado"] = df["Cerrado"].fillna(0).astype(int)
    else:
        df["Cerrado"] = 0

    df["conversio alimenticia"] = np.where(
        (df["PesoFinal"] > 0) & (df["Aves_vivas"] > 0) & (df["Alimento_Acumulado"] > 0),
        df["Alimento_Acumulado"] / (df["PesoFinal"] * df["Aves_vivas"]),
        np.nan
    )

    cols_finales = [
        "Codigo_Unico", "LoteCosto", "PesoFinal", "Edad", "Edad^2", "Alimento_Acumulado", "conversio alimenticia",
        "BUCAY", "SANTODOMINGO", "TipoGranjero_Propia", "TipoGranjero_PCA",
        "LoteCompleto", "Granja", "Galpon", "NombreGranja", "TipoAlimento", "TipoGranjero",
        "Zona", "Cerrado", "Edad (venta)", "Peso_Venta", "Aves_vivas", "Aves_Iniciales",
        "FechaTransaccion", "FechaPrecioAplicado", "Mortalidad", "Descarte",
        "MortalidadDescarte_Diario_Raw", "MortalidadDescarte_Diario", "evento_cierre_masivo",
        "MortalidadDescarte_Acumulado",
        "alimento_dia_kg", "delta_negativo", "EsExtendido",
        "precio_kg_real", "precio_fecha_exacta", "precio_arrastrado",
        "precio_es_real", "precio_promedio_lote", "precio_kg",
        "costo_alimento_dia", "costo_alimento_acumulado",
        "ponderado_edad_reproductora", "ponderado_dias_guarda",
        "porcentaje_raza_RAP95", "porcentaje_raza_C500SF",
        "Reproductora", "Guarda", "etapa",
        "Quintil", "Etiqueta_Escenario"
    ]

    for col in cols_finales:
        if col not in df.columns:
            df[col] = np.nan

    df_final = df[cols_finales].copy()
    df_final = df_final.sort_values(["Codigo_Unico", "Edad", "FechaTransaccion"]).reset_index(drop=True)

    return df_final


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 80)
    print("ETL PRODUCCIÓN MENSUAL v2 - INICIO")
    print("=" * 80)

    try:
        print("BRL_FILE:", BRL_FILE)
        print("KRI_GALPON_FILE:", KRI_GALPON_FILE)
        print("KRI_ALIMENTO_FILE:", KRI_ALIMENTO_FILE)
        print("BRIM_FILE:", BRIM_FILE)
        print("OUT_XLSX:", OUT_XLSX)

        brl = transformar_brl()
        kri_gal = transformar_kri_galpon()

        df = cruzar_brl_galpon(brl, kri_gal)
        df = extender_lotes_cerrados_hasta_venta(df)
        df = calcular_peso_final(df)
        df = recortar_hasta_ultimo_peso_final(df)
        df = eliminar_lotes_con_baja_peso(df)
        df = recalcular_series_base(df)

        kri_ali = transformar_kri_alimento()
        precios_dia, promedio_lote = calcular_precios_ponderados(kri_ali)
        df = cruzar_brl_precios(df, precios_dia, promedio_lote)

        brim = transformar_brim()  # retorna (brim_lote, brim_galpon, brim_granja) o None
        df = cruzar_brim(df, brim)
        df = clasificar_reproductora_guarda_etapa(df)

        areas = transformar_areas()
        df = cruzar_areas(df, areas)
        print("\n[8.5/9] Calculando Etiqueta_Escenario...")
        df = calcular_etiqueta_escenario(df)

        df_final = preparar_salida(df)

        # ============================================================
        print("\n[EXPORTANDO] Generando archivo Excel...")
        with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
            df_final.to_excel(writer, sheet_name="produccion", index=False)
            audit_df = pd.DataFrame([{"Paso": s} for s in audit])
            audit_df.to_excel(writer, sheet_name="audit", index=False)

        print(f"\n✅ ÉXITO")
        print(f"   Archivo: {OUT_XLSX}")
        print(f"   Registros: {len(df_final)}")
        print(f"   Lotes únicos: {df_final['Codigo_Unico'].nunique()}")
        print(f"   Período: {df_final['FechaTransaccion'].min()} a {df_final['FechaTransaccion'].max()}")
        print(f"   Aves_vivas calculado: {df_final['Aves_vivas'].notna().sum()} registros")
        print(f"   PesoFinal calculado: {df_final['PesoFinal'].notna().sum()} registros")
        print(f"   Filas extendidas: {int(df_final['EsExtendido'].fillna(0).sum())}")
        print(f"   Precios reales/asignados: {int(df_final['precio_es_real'].fillna(0).sum())}")
        print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()