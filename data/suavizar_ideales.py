#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
suavizar_ideales.py
Corrige la columna Peso en LOTES_IDEALES_DASHBOARD_COMPATIBLE.xlsx:

PROBLEMA: el ideal tiene interpolacion lineal entre puntos semanales
(dias 7, 14, 21, 28, 35) lo que crea "picos" en las uniones cuando
se compara con la curva real que usa PCHIP suave.

SOLUCION: para cada escenario, toma los puntos de control semanales
y re-interpola todos los dias intermedios con PCHIP (igual que el ETL
hace con los pesos reales).

Ejecutar una sola vez. Sobreescribe el archivo in-place.
"""

import os
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
IDEALES_FILE = os.path.join(BASE_DIR, "LOTES_IDEALES_DASHBOARD_COMPATIBLE.xlsx")

print(f"Leyendo: {IDEALES_FILE}")
xl = pd.ExcelFile(IDEALES_FILE)
sheet = "DATOS_COMPLETOS" if "DATOS_COMPLETOS" in xl.sheet_names else xl.sheet_names[0]
df = pd.read_excel(IDEALES_FILE, sheet_name=sheet)
print(f"  {len(df):,} filas | {df['Etiqueta_Escenario'].nunique()} escenarios")

df["Edad"] = pd.to_numeric(df["Edad"], errors="coerce")
df["Peso"] = pd.to_numeric(df["Peso"], errors="coerce")

# Puntos de control: dias multiples de 7 + primer y ultimo dia del escenario
# (los medidos realmente: 1, 7, 14, 21, 28, 35, dia_venta)
CONTROL_MOD = 7  # cada 7 dias es punto real medido

bloques = []
resumen = []

for esc in sorted(df["Etiqueta_Escenario"].dropna().unique()):
    mask  = df["Etiqueta_Escenario"] == esc
    bloque = df[mask].copy().sort_values("Edad").reset_index(drop=True)

    edades_todas = bloque["Edad"].values.astype(float)
    pesos_todos  = bloque["Peso"].values.astype(float)

    validos = np.isfinite(pesos_todos) & (pesos_todos > 0) & np.isfinite(edades_todas)
    if validos.sum() < 2:
        bloques.append(bloque)
        continue

    edades_v = edades_todas[validos]
    pesos_v  = pesos_todos[validos]

    # Identificar puntos de control: dia 1, multiples de 7, y ultimo dia
    edad_min = int(edades_v.min())
    edad_max = int(edades_v.max())

    control_edades = set()
    control_edades.add(float(edad_min))   # primer dia
    control_edades.add(float(edad_max))   # ultimo dia (cierre/venta)
    for d in range(1, edad_max + 1):
        if d % CONTROL_MOD == 0:
            control_edades.add(float(d))

    # Solo tomar los que tienen datos reales en el archivo
    edades_ctrl = np.array(sorted([e for e in control_edades if e in edades_v]))

    if len(edades_ctrl) < 2:
        bloques.append(bloque)
        continue

    # Obtener pesos en esos puntos de control (promedio si hubiera duplicados)
    pesos_ctrl = np.array([
        pesos_v[np.argmin(np.abs(edades_v - e))]
        for e in edades_ctrl
    ])

    # Forzar monotonia en los puntos de control
    pesos_ctrl = np.maximum.accumulate(pesos_ctrl)

    # PCHIP sobre los puntos de control → regenerar TODOS los dias
    try:
        interp = PchipInterpolator(edades_ctrl, pesos_ctrl, extrapolate=False)
        pesos_nuevos = interp(edades_v)

        # Forzar monotonia sobre resultado interpolado
        pesos_nuevos = np.maximum.accumulate(pesos_nuevos)

        # Para dias fuera del rango de control → mantener valor original
        pesos_final = pesos_todos.copy()
        pesos_final[validos] = pesos_nuevos

        bloque["Peso"] = pesos_final

        resumen.append({
            "escenario": esc,
            "puntos_ctrl": len(edades_ctrl),
            "edades_ctrl": edades_ctrl.astype(int).tolist(),
            "peso_min": round(pesos_ctrl.min(), 3),
            "peso_max": round(pesos_ctrl.max(), 3),
        })

    except Exception as e:
        print(f"  ERROR en {esc}: {e}")

    bloques.append(bloque)

df_corregido = pd.concat(bloques, ignore_index=True)

# Verificar que no queden bajadas
bajadas = 0
for esc, grp in df_corregido.groupby("Etiqueta_Escenario"):
    p = grp.sort_values("Edad")["Peso"].dropna().values
    if len(p) > 1 and (np.diff(p) < -1e-6).any():
        bajadas += 1
        print(f"  BAJADA en {esc}")

print(f"\nEscenarios procesados: {len(resumen)}")
print(f"Bajadas de peso restantes: {bajadas}")

# Mostrar muestra del resultado
r = resumen[0]
print(f"\nMuestra '{r['escenario']}':")
print(f"  Puntos control (dias): {r['edades_ctrl']}")
sample = df_corregido[df_corregido["Etiqueta_Escenario"]==r["escenario"]][["Edad","Peso"]].sort_values("Edad")
print(sample.head(15).to_string(index=False))

# Guardar preservando otras hojas
otras_hojas = [s for s in xl.sheet_names if s != sheet]
print(f"\nGuardando: {IDEALES_FILE}")
with pd.ExcelWriter(IDEALES_FILE, engine="openpyxl") as writer:
    df_corregido.to_excel(writer, sheet_name=sheet, index=False)
    for s in otras_hojas:
        pd.read_excel(IDEALES_FILE, sheet_name=s).to_excel(writer, sheet_name=s, index=False)

print(f"Listo - {len(df_corregido):,} filas guardadas")
