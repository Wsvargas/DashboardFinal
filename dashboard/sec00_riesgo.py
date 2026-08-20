"""
Sección 00: Lotes en Riesgo — Alerta predictiva ejecutiva
==========================================================
Corre el modelo sobre TODOS los lotes activos y compara el peso
proyectado al día 35 contra el ideal del escenario de cada lote.

Clasificación:
  CRÍTICO : déficit proyectado >= 6% vs ideal
  ALERTA  : déficit proyectado >= 3% vs ideal
  EN META : dentro del rango o por encima del ideal
"""

import numpy as np
import pandas as pd
import streamlit as st

from config import RED, GREEN, AMBER, BORDER, MUTED, MODEL_FILE
from core.helpers import md, extract_lote_codigo, _limpiar_historial_para_modelo
from core.data_loader import get_curva_ideal_promedio
from .kpis import fmt_manager

TARGET_DAY      = 35
UMBRAL_ALERTA   = 0.03   # 3% bajo el ideal
UMBRAL_CRITICO  = 0.06   # 6% bajo el ideal
EDAD_MIN_PRED   = 7      # edad mínima para proyectar con sentido


@st.cache_data(show_spinner=False)
def _calcular_riesgo_lotes(_df_all, _snap, _ideales, data_key, model_mtime):
    """
    Predicción masiva cacheada. Se recalcula solo cuando cambian los
    datos (data_key) o el modelo (model_mtime); los DataFrames van con
    guion bajo para no hashearlos en cada rerun.
    """
    from core.model_predictor import cargar_predictor

    predictor = cargar_predictor(MODEL_FILE)
    if predictor.model is None:
        return pd.DataFrame()

    filas = []
    for _, row in _snap.iterrows():
        estado = str(row.get("EstadoLote", "")).upper()
        edad = row.get("Edad")
        if estado != "ABIERTO" or pd.isna(edad):
            continue
        edad = int(edad)
        if edad < EDAD_MIN_PRED or edad >= TARGET_DAY:
            continue

        lote = row["LoteCompleto"]
        hist_raw = _df_all[_df_all["LoteCompleto"] == lote].sort_values("Edad")
        hist_pred = _limpiar_historial_para_modelo(hist_raw)
        if hist_pred.empty:
            continue

        res = predictor.proyectar_curva(hist_lote=hist_pred, target_edad=TARGET_DAY)
        if res.get("error") or res.get("peso_d35") is None:
            continue

        # Ideal del escenario del lote al día 35
        curva_ideal = get_curva_ideal_promedio(
            row.get("ZonaNombre"), row.get("TipoStd"), row.get("Quintil"),
            _ideales, edad_max=TARGET_DAY,
            reproductora=row.get("ReproductoraStd"),
        )
        ideal_d35 = np.nan
        if curva_ideal is not None and not curva_ideal.empty and "Peso" in curva_ideal.columns:
            ci = curva_ideal.dropna(subset=["Edad", "Peso"]).sort_values("Edad")
            if not ci.empty:
                ideal_d35 = float(np.interp(
                    TARGET_DAY, ci["Edad"].values, ci["Peso"].values
                ))

        aves = pd.to_numeric(pd.Series([row.get("AvesVivas")]), errors="coerce").iloc[0]

        filas.append({
            "LoteCompleto":  lote,
            "Granja":        str(row.get("NombreGranja", row.get("GranjaID", "—"))),
            "Galpon":        row.get("Galpon"),
            "Edad":          edad,
            "AvesVivas":     aves,
            "PesoActual":    row.get("PesoFinal"),
            "PesoProy35":    float(res["peso_d35"]),
            "PisoProy35":    res.get("peso_d35_lo"),
            "Ideal35":       ideal_d35,
        })

    if not filas:
        return pd.DataFrame()

    df = pd.DataFrame(filas)
    df["DeficitKgAve"] = df["Ideal35"] - df["PesoProy35"]
    df["DeficitPct"] = df["DeficitKgAve"] / df["Ideal35"].replace(0, np.nan)
    df["KgEnRiesgo"] = (df["DeficitKgAve"].clip(lower=0) * df["AvesVivas"]).fillna(0)

    df["Severidad"] = np.select(
        [df["DeficitPct"] >= UMBRAL_CRITICO, df["DeficitPct"] >= UMBRAL_ALERTA],
        ["CRÍTICO", "ALERTA"],
        default="EN META",
    )
    df.loc[df["Ideal35"].isna(), "Severidad"] = "SIN IDEAL"

    return df.sort_values("KgEnRiesgo", ascending=False).reset_index(drop=True)


def render_lotes_riesgo(SF, DF_ALL, IDEALES, data_key, model_mtime):
    """
    Sección ejecutiva de lotes en riesgo, en formato compacto:
      - todo en meta → una sola línea delgada
      - hay riesgos  → línea resumen + expander con la tabla
    """
    with st.spinner("Proyectando lotes activos…"):
        riesgo_df = _calcular_riesgo_lotes(DF_ALL, SF, IDEALES, data_key, model_mtime)

    def _strip(texto, color_txt, bg, borde):
        md(f'''
<div style="display:flex;align-items:center;gap:8px;margin:2px 0 6px 0;
            background:{bg};border:1px solid {borde};border-radius:8px;
            padding:4px 12px;font-size:.78rem;font-weight:700;color:{color_txt};">
  {texto}
</div>''')

    if riesgo_df.empty:
        _strip(
            f"⚠ Riesgo D{TARGET_DAY}: sin lotes abiertos en rango de proyección (día {EDAD_MIN_PRED}–{TARGET_DAY - 1})",
            MUTED, "#F8FAFC", BORDER,
        )
        return

    # Solo los lotes visibles en el filtro actual
    riesgo_df = riesgo_df[riesgo_df["LoteCompleto"].isin(SF["LoteCompleto"])].copy()
    if riesgo_df.empty:
        _strip(
            f"⚠ Riesgo D{TARGET_DAY}: sin lotes abiertos en rango de proyección con los filtros actuales",
            MUTED, "#F8FAFC", BORDER,
        )
        return

    n_total   = len(riesgo_df)
    en_riesgo = riesgo_df[riesgo_df["Severidad"].isin(["CRÍTICO", "ALERTA"])]
    n_crit    = int((riesgo_df["Severidad"] == "CRÍTICO").sum())
    n_aler    = int((riesgo_df["Severidad"] == "ALERTA").sum())
    kg_riesgo = float(en_riesgo["KgEnRiesgo"].sum())

    if en_riesgo.empty:
        _strip(
            f"✅ Riesgo D{TARGET_DAY}: los {n_total} lotes proyectables van en meta "
            f"(ninguno con déficit ≥ {UMBRAL_ALERTA:.0%} vs su ideal)",
            "#166534", "rgba(22,163,74,.07)", "rgba(22,163,74,.3)",
        )
        return

    resumen = (
        f"⚠️ Lotes en Riesgo D{TARGET_DAY} — 🔴 {n_crit} crítico(s) · "
        f"🟠 {n_aler} en alerta · {fmt_manager(kg_riesgo, suffix=' kg')} live en riesgo "
        f"· {n_total - n_crit - n_aler} en meta"
    )
    with st.expander(resumen, expanded=bool(n_crit)):
        _render_tabla_riesgo(en_riesgo)


def _render_tabla_riesgo(en_riesgo):
    tabla = en_riesgo.copy()
    tabla["Código"] = tabla["LoteCompleto"].apply(extract_lote_codigo)
    tabla["DeficitGrAve"] = (tabla["DeficitKgAve"] * 1000).round(0)
    tabla["Sem"] = np.where(tabla["Severidad"] == "CRÍTICO", "🔴", "🟠")

    st.dataframe(
        tabla[[
            "Sem", "Código", "Granja", "Edad", "AvesVivas",
            "PesoProy35", "PisoProy35", "Ideal35", "DeficitGrAve", "KgEnRiesgo",
        ]],
        hide_index=True,
        width="stretch",
        height=min(260, 38 * (len(tabla) + 1)),
        column_config={
            "Sem":          st.column_config.TextColumn("", width="small"),
            "Código":       st.column_config.TextColumn("🔖 Lote"),
            "Granja":       st.column_config.TextColumn("Granja"),
            "Edad":         st.column_config.NumberColumn("Día hoy", format="%d", width="small"),
            "AvesVivas":    st.column_config.NumberColumn("Aves", format="%d", width="small"),
            "PesoProy35":   st.column_config.NumberColumn(f"Proy. D{TARGET_DAY}", format="%.3f kg"),
            "PisoProy35":   st.column_config.NumberColumn("Piso probable", format="%.3f kg",
                                                          help="Límite inferior de la banda de predicción (q10)"),
            "Ideal35":      st.column_config.NumberColumn(f"Ideal D{TARGET_DAY}", format="%.3f kg"),
            "DeficitGrAve": st.column_config.NumberColumn("Déficit g/ave", format="%d g"),
            "KgEnRiesgo":   st.column_config.NumberColumn("Kg en riesgo", format="%.0f kg",
                                                          help="Déficit por ave × aves vivas del lote"),
        },
    )

    md(f'<div class="hint-text">Ordenado por kg live en riesgo · umbral alerta {UMBRAL_ALERTA:.0%} · crítico {UMBRAL_CRITICO:.0%} vs ideal del escenario</div>')
