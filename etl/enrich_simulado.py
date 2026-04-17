#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enrich_simulado.py
Enriquece data/produccion_mes_actual_simulada_abiertos.xlsx con columnas de
reproductora/guarda/etiqueta, cruzando el BRIM al nivel de GRANJA (no lote)
porque el archivo simulado tiene lotes -2601- y el BRIM tiene lotes -2602-.

Columnas que rellena:
  ponderado_edad_reproductora, ponderado_dias_guarda,
  porcentaje_raza_RAP95, porcentaje_raza_C500SF,
  Reproductora, Guarda, TipoGranja_norm, Etiqueta_Escenario
"""

import os
import sys
import re
import unicodedata
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings("ignore")

# ── Rutas ────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # DashboardFinal/
DATA_DIR   = os.path.join(BASE_DIR, "data")
ETL_DATA   = os.path.join(BASE_DIR, "etl", "data")

SIM_FILE   = os.path.join(DATA_DIR,  "produccion_mes_actual_simulada_abiertos.xlsx")
BRIM_FILE  = os.path.join(ETL_DATA,  "KRI_ALOJAMIENTO_protein_mes_actual.csv")
AREAS_FILE = os.path.join(ETL_DATA,  "Areas.xlsx")
OUT_FILE   = SIM_FILE   # sobreescribe el mismo archivo

ENCODING = "latin-1"


# ── Helpers ──────────────────────────────────────────────────
def to_str_series(s: pd.Series) -> pd.Series:
    """Convierte cualquier dtype (incluso ArrowStringArray) a object str limpio."""
    return pd.array(s.to_numpy(dtype=object, na_value=None)).astype(str)


def normalize_lote(lote_str):
    if pd.isna(lote_str) or str(lote_str).strip() in ("", "nan", "None"):
        return np.nan
    s = str(lote_str).strip().upper()
    s = s.replace(" ", "").replace("–", "-").replace("—", "-").replace("_", "-")
    s = "-".join([p for p in s.split("-") if p])
    return s


def wprom(grp, col_val, col_peso):
    mask = grp[col_val].notna()
    if mask.sum() == 0:
        return np.nan
    return (grp.loc[mask, col_val] * grp.loc[mask, col_peso]).sum() / grp.loc[mask, col_peso].sum()


# ── 1. Leer archivo simulado ─────────────────────────────────
print("Leyendo archivo simulado...")
df = pd.read_excel(SIM_FILE, engine="openpyxl")
print(f"  {len(df):,} filas, {len(df.columns)} columnas")

# Forzar dtype str en columnas clave para evitar ArrowStringArray
for col in ["LoteCompleto", "Zona", "TipoGranjero", "Quintil", "Codigo_Unico"]:
    if col in df.columns:
        arr = df[col].to_numpy(dtype=object, na_value=None)
        df[col] = [str(v).strip() if v is not None else None for v in arr]

# Extraer código de granja (BUC1002-2601-03-S  →  BUC1002)
df["_granja"] = df["LoteCompleto"].apply(
    lambda x: str(x).split("-")[0].upper().strip() if x else None
)

# ── 2. Leer y agregar BRIM al nivel de GRANJA ────────────────
print("Procesando BRIM...")
brim_raw = pd.read_csv(BRIM_FILE, encoding=ENCODING, sep=None, engine="python")
brim_raw.columns = [c.strip() for c in brim_raw.columns]

# Renombrar columna de días con posible corrupción de encoding
dias_col = next(
    (c for c in brim_raw.columns if re.sub(r"[^a-z]", "", c.lower()) == "diasguarda"),
    "Días_guarda"
)
if dias_col != "Días_guarda" and dias_col in brim_raw.columns:
    brim_raw = brim_raw.rename(columns={dias_col: "Días_guarda"})

cols_req = ["Galpon/Corral", "Aves Alojadas", "Edad", "Días_guarda", "Raza"]
missing = [c for c in cols_req if c not in brim_raw.columns]
if missing:
    print(f"  ❌ Columnas faltantes en BRIM: {missing}")
    print(f"  Columnas disponibles: {list(brim_raw.columns)}")
    sys.exit(1)

# Limpiar strings
for col in brim_raw.columns:
    try:
        brim_raw[col] = brim_raw[col].astype(str).str.strip()
    except Exception:
        pass

brim_raw["Galpon/Corral"] = brim_raw["Galpon/Corral"].apply(normalize_lote)
brim_raw["Aves Alojadas"] = pd.to_numeric(brim_raw["Aves Alojadas"], errors="coerce")
brim_raw["Edad"]          = pd.to_numeric(brim_raw["Edad"],          errors="coerce")
brim_raw["Días_guarda"]   = pd.to_numeric(brim_raw["Días_guarda"],   errors="coerce")

brim_raw = brim_raw.dropna(subset=["Aves Alojadas", "Galpon/Corral"])
brim_raw = brim_raw[brim_raw["Aves Alojadas"] > 0]

# Extraer granja del galpon (BUC1002-2602-03-S → BUC1002)
brim_raw["_granja"] = brim_raw["Galpon/Corral"].apply(
    lambda x: str(x).split("-")[0].upper().strip() if x and str(x) != "nan" else None
)
brim_raw = brim_raw.dropna(subset=["_granja"])
brim_raw = brim_raw[brim_raw["_granja"] != ""]

# Agregar por GRANJA (no por galpon, porque los lotes son diferentes)
agg_rows = []
for granja, grp in brim_raw.groupby("_granja"):
    total_aves = grp["Aves Alojadas"].sum()
    row = {"_granja": granja}
    row["ponderado_edad_reproductora"] = wprom(grp, "Edad",        "Aves Alojadas")
    row["ponderado_dias_guarda"]       = wprom(grp, "Días_guarda", "Aves Alojadas")

    razas_validas = [r for r in grp["Raza"].dropna().unique()
                     if str(r).strip() not in ("", "nan")]
    for raza in razas_validas:
        aves_raza = grp.loc[grp["Raza"] == raza, "Aves Alojadas"].sum()
        row[f"porcentaje_raza_{raza}"] = round((aves_raza / total_aves) * 100, 2) if total_aves > 0 else np.nan

    agg_rows.append(row)

brim_granja = pd.DataFrame(agg_rows)
for raza_col in ["porcentaje_raza_RAP95", "porcentaje_raza_C500SF"]:
    if raza_col not in brim_granja.columns:
        brim_granja[raza_col] = np.nan

# Asegurar que la clave de join es str puro
brim_granja["_granja"] = brim_granja["_granja"].astype(str).str.strip()

print(f"  BRIM agregado: {len(brim_granja)} granjas únicas")
print(f"  Granjas BRIM: {sorted(brim_granja['_granja'].tolist())}")

# ── 3. Verificar solapamiento ────────────────────────────────
sim_granjas  = set(df["_granja"].dropna().unique())
brim_granjas = set(brim_granja["_granja"].unique())
comunes      = sim_granjas & brim_granjas
solo_sim     = sim_granjas - brim_granjas
print(f"\n  Granjas simulado:  {len(sim_granjas)}")
print(f"  Granjas BRIM:      {len(brim_granjas)}")
print(f"  Solapamiento:      {len(comunes)} granjas")
if solo_sim:
    print(f"  Sin match BRIM:    {sorted(solo_sim)}")

# ── 4. Limpiar columnas viejas del simulado ──────────────────
cols_a_limpiar = [
    "ponderado_edad_reproductora", "ponderado_dias_guarda",
    "porcentaje_raza_RAP95", "porcentaje_raza_C500SF",
    "ponderado_edad_reproductora_brim", "ponderado_dias_guarda_brim",
    "porcentaje_raza_RAP95_brim", "porcentaje_raza_C500SF_brim",
    "Reproductora", "Guarda", "TipoGranja_norm", "Etiqueta_Escenario",
]
for col in cols_a_limpiar:
    if col in df.columns:
        df[col] = np.nan

# ── 5. Merge granja → simulado ───────────────────────────────
print("\nHaciendo merge granja-level...")
df["_granja"] = df["_granja"].astype(str).str.strip()

antes = len(df)
df = df.merge(
    brim_granja[["_granja", "ponderado_edad_reproductora", "ponderado_dias_guarda",
                 "porcentaje_raza_RAP95", "porcentaje_raza_C500SF"]],
    on="_granja",
    how="left",
    suffixes=("", "_brim_new")
)

# Si hay sufijos (no debería), limpiarlos
for col in ["ponderado_edad_reproductora", "ponderado_dias_guarda",
            "porcentaje_raza_RAP95", "porcentaje_raza_C500SF"]:
    brim_col = f"{col}_brim_new"
    if brim_col in df.columns:
        df[col] = df[brim_col]
        df = df.drop(columns=[brim_col])

print(f"  Filas antes: {antes} | después: {len(df)}")
print(f"  Filas con ponderado_edad_reproductora: {df['ponderado_edad_reproductora'].notna().sum()}")

# ── 6. Clasificar Reproductora ───────────────────────────────
edad_base = df["ponderado_edad_reproductora"]
df["Reproductora"] = np.select(
    [
        edad_base < 35,
        (edad_base >= 35) & (edad_base < 51),
        edad_base >= 51,
    ],
    ["Joven", "Adulta", "Vieja"],
    default=None
)
print(f"\n  Reproductora — {df['Reproductora'].value_counts().to_dict()}")

# ── 7. Clasificar Guarda ─────────────────────────────────────
guarda_base = df["ponderado_dias_guarda"]
df["Guarda"] = np.select(
    [
        (guarda_base >= 3) & (guarda_base < 7),
        (guarda_base >= 7) & (guarda_base < 13),
        guarda_base >= 13,
    ],
    ["Optima", "Moderada", "Critica"],
    default=None
)
print(f"  Guarda       — {df['Guarda'].value_counts().to_dict()}")

# ── 8. TipoGranja_norm ───────────────────────────────────────
tipo_map = {
    "GranjaPropia": "Propia",
    "PROPIA":       "Propia",
    "Propia":       "Propia",
    "PCA":          "PCA",
}
df["TipoGranja_norm"] = (
    df["TipoGranjero"]
    .astype(str)
    .str.strip()
    .map(tipo_map)
    .fillna("PCA")
)
print(f"  TipoGranja_norm — {df['TipoGranja_norm'].value_counts().to_dict()}")

# ── 9. Etiqueta_Escenario ────────────────────────────────────
zona     = df["Zona"].astype(str).str.strip()
tipo     = df["TipoGranja_norm"].astype(str).str.strip()
repro    = df["Reproductora"].astype(str).str.strip()
quintil  = df["Quintil"].astype(str).str.strip()

etiqueta = zona + "_" + tipo + "_" + repro + "_" + quintil

mask_invalida = (
    zona.isin(["nan", "None", ""]) |
    tipo.isin(["nan", "None", ""]) |
    repro.isin(["nan", "None", "None"]) |
    quintil.isin(["nan", "None", ""])
)
etiqueta[mask_invalida] = None
df["Etiqueta_Escenario"] = etiqueta

n_etiqueta = df["Etiqueta_Escenario"].notna().sum()
print(f"\n  Etiqueta_Escenario: {n_etiqueta}/{len(df)} filas con etiqueta")
print(f"  Etiquetas únicas: {sorted(df['Etiqueta_Escenario'].dropna().unique())[:10]}")

# ── 10. Eliminar columna auxiliar ────────────────────────────
df = df.drop(columns=["_granja"], errors="ignore")

# ── 11. Guardar ──────────────────────────────────────────────
print(f"\nGuardando en {OUT_FILE}...")
with pd.ExcelWriter(OUT_FILE, engine="openpyxl") as writer:
    df.to_excel(writer, index=False)

print(f"OK - Listo: {len(df):,} filas guardadas")
