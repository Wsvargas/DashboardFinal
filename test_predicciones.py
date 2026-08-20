#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prueba de predicciones del modelo CatBoost
Toma 3 lotes abiertos reales y genera curvas de peso proyectadas.
Salida: test_resultados_prediccion.xlsx
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from core.model_predictor import cargar_predictor
from core.data_loader import cargar_datos

# ── Config ────────────────────────────────────────────────────
MODEL_PATH  = "models/modelo_curva_futura_catboost.joblib"
PROD_FILE   = "etl/data/produccion_mes_actual.xlsx"
OUT_FILE    = "test_resultados_prediccion.xlsx"
TARGET_DAY  = 35

# Lotes seleccionados: variedad de edades y zonas
LOTES_TEST = [
    "STO2006-2602-01-S",   # Dia 7  - horizonte maximo (28 dias por predecir)
    "STO5044-2601-04-S",   # Dia 28 - horizonte medio  (7 dias por predecir)
    "STO5044-2601-06-S",   # Dia 28 - mismo horizonte, peso diferente
]

# ── Cargar modelo ─────────────────────────────────────────────
print(f"\nCargando modelo: {MODEL_PATH}")
predictor = cargar_predictor(MODEL_PATH)
if predictor.model is None:
    print("[ERROR] Modelo no cargado")
    sys.exit(1)
print(f"  Features: {len(predictor.feature_cols)}")

# ── Cargar datos de produccion ────────────────────────────────
print(f"\nCargando produccion: {PROD_FILE}")
df_prod = pd.read_excel(PROD_FILE, sheet_name="produccion")
print(f"  {len(df_prod)} registros | {df_prod['LoteCompleto'].nunique()} lotes")

# ── Ejecutar predicciones ─────────────────────────────────────
resumen_rows = []
curvas       = {}

for lote in LOTES_TEST:
    print(f"\n{'='*60}")
    print(f"LOTE: {lote}")

    hist = df_prod[df_prod["LoteCompleto"] == lote].copy()

    # Mapear columnas ETL a lo que espera _snapshot_from_hist
    hist = hist.rename(columns={
        "Alimento_Acumulado":           "AlimAcumKg",
        "alimento_dia_kg":              "_alim_dia",
        "MortalidadDescarte_Acumulado": "MortalidadDescarte_Acumulado",
        "Aves_vivas":                   "AvesVivas",
        "TipoGranjero_Propia":          "TipoStd",
        "Quintil":                      "Quintil",
        "Reproductora":                 "ReproductoraStd",
    })
    # TipoStd: 1 -> PROPIA, 0 -> PCA
    if "TipoStd" in hist.columns:
        hist["TipoStd"] = hist["TipoStd"].map({1: "PROPIA", 0: "PAC"}).fillna("PAC")

    # ZonaNombre desde BUCAY
    if "BUCAY" in hist.columns:
        hist["ZonaNombre"] = hist["BUCAY"].map({1: "BUCAY", 0: "SANTO DOMINGO"}).fillna("OTRA")

    hist = hist.sort_values("Edad").reset_index(drop=True)
    hist_valido = hist[hist["PesoFinal"].notna() & (hist["PesoFinal"] > 0)].copy()

    if hist_valido.empty:
        print("  [WARN] Sin datos de peso validos")
        continue

    ultimo    = hist_valido.iloc[-1]
    edad_hoy  = int(float(ultimo["Edad"]))
    peso_hoy  = float(ultimo["PesoFinal"])
    horizonte = TARGET_DAY - edad_hoy

    print(f"  Dia actual : {edad_hoy}")
    print(f"  Peso hoy   : {peso_hoy:.3f} kg  ({peso_hoy*1000:.0f} g)")
    print(f"  Horizonte  : {horizonte} dias por predecir")

    # Ejecutar prediccion
    res = predictor.proyectar_curva(hist_valido, target_edad=TARGET_DAY)

    if res["error"]:
        print(f"  [ERROR] {res['error']}")
        continue

    df_curva = res["df"]
    peso_d35 = res["peso_d35"]
    ganancia = peso_d35 - peso_hoy

    print(f"  Peso D{TARGET_DAY}   : {peso_d35:.3f} kg  ({peso_d35*1000:.0f} g)")
    print(f"  Ganancia   : +{ganancia:.3f} kg  (+{ganancia*1000:.0f} g) en {horizonte} dias")
    print(f"  Ganancia/d : +{ganancia/horizonte*1000:.1f} g/dia" if horizonte > 0 else "")

    print(f"\n  Curva de prediccion:")
    print(f"  {'Dia':>4}  {'Peso pred (kg)':>14}  {'Peso pred (g)':>13}  {'Ganancia dia (g)':>16}")
    pesos_prev = peso_hoy
    for _, row in df_curva.iterrows():
        d = int(row["Dia"])
        p = float(row["Peso_pred_kg"])
        g = (p - pesos_prev) * 1000 if d > edad_hoy else 0
        marker = " <-- HOY" if d == edad_hoy else ""
        print(f"  {d:>4}  {p:>14.3f}  {p*1000:>13.0f}  {g:>+16.1f}{marker}")
        pesos_prev = p

    # Guardar para Excel
    curvas[lote] = df_curva.copy()
    curvas[lote]["Lote"]        = lote
    curvas[lote]["Edad_hoy"]    = edad_hoy
    curvas[lote]["Peso_hoy_kg"] = peso_hoy
    curvas[lote]["Es_real"]     = curvas[lote]["Dia"] == edad_hoy

    resumen_rows.append({
        "Lote":             lote,
        "Zona":             hist["ZonaNombre"].iloc[0] if "ZonaNombre" in hist.columns else "?",
        "Dia_actual":       edad_hoy,
        "Peso_actual_kg":   round(peso_hoy, 3),
        "Peso_actual_g":    round(peso_hoy * 1000, 0),
        f"Peso_D{TARGET_DAY}_kg":  round(peso_d35, 3),
        f"Peso_D{TARGET_DAY}_g":   round(peso_d35 * 1000, 0),
        "Ganancia_total_kg": round(ganancia, 3),
        "Ganancia_total_g":  round(ganancia * 1000, 0),
        "Dias_restantes":    horizonte,
        "Ganancia_g_por_dia": round(ganancia * 1000 / horizonte, 1) if horizonte > 0 else 0,
    })

# ── Exportar a Excel ──────────────────────────────────────────
print(f"\n\nExportando resultados a: {OUT_FILE}")
with pd.ExcelWriter(OUT_FILE, engine="openpyxl") as writer:

    # Hoja 1: Resumen ejecutivo
    df_res = pd.DataFrame(resumen_rows)
    df_res.to_excel(writer, sheet_name="Resumen", index=False)

    # Hoja 2-4: Curva detallada por lote
    for lote, df_c in curvas.items():
        nombre_hoja = lote.replace("/", "-")[:31]
        cols = ["Dia", "Peso_pred_kg", "Peso_pred_g", "Es_real"]
        df_c[cols].to_excel(writer, sheet_name=nombre_hoja, index=False)

    # Hoja 5: Todas las curvas juntas para graficar
    df_todas = pd.concat(curvas.values(), ignore_index=True) if curvas else pd.DataFrame()
    if not df_todas.empty:
        df_todas[["Lote", "Dia", "Peso_pred_kg", "Peso_pred_g", "Es_real"]]\
            .to_excel(writer, sheet_name="Curvas_completas", index=False)

print(f"[OK] Archivo generado: {OUT_FILE}")
print(f"     Hojas: Resumen + {len(curvas)} curvas individuales + Curvas_completas")
