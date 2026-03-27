import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from config import BLACK, CARD, BORDER, RED, GREEN, AMBER, MUTED, BG
from helpers import md, fmt_num, extract_lote_codigo, _file_mtime, _limpiar_historial_para_modelo
from data_loader import get_curva_ideal_promedio
from dashboard_kpis import fmt_manager, fmt_signed_short, render_kpi_small

CHART_TEXT = BLACK
TARGET_DAY = 35


def render_sec04(lote_sel, SF, DF_FILTRADO, DF_ALL, IDEALES, get_predictor_cached, pred_cache):
    """
    Sección 04: Predicción - Proyección al Día 35
    """
    
    # ── Cargar predictor ──────────────────────────────────────
    try:
        MODEL_PATH = "modelo_rf_avicola.joblib"
        predictor = get_predictor_cached(MODEL_PATH, _file_mtime(MODEL_PATH)) if os.path.exists(MODEL_PATH) else None
        pred_activo = predictor is not None and predictor.model is not None
    except Exception as e:
        st.warning(f"⚠️ No se pudo cargar el predictor: {e}")
        pred_activo = False
    
    if not pred_activo:
        md(f"""
<div class="card" style="border:1px dashed {BORDER};background:{BG};min-height:900px;
display:flex;align-items:center;justify-content:center;">
  <div style="text-align:center;color:{MUTED};font-weight:800;
              text-transform:uppercase;letter-spacing:.7px;">
    📊 Predicción de Lotes<br><br>⚠️ Modelo no disponible<br>
    Coloca <strong>modelo_rf_avicola.joblib</strong><br>en la carpeta del app
  </div>
</div>""")
        return
    
    # ── Header ────────────────────────────────────────────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">04</span>
  <div>
    <div class="sec-title">Predicción: Proyección al Día {TARGET_DAY}</div>
    <div class="sec-sub">Real vs Ideal vs Proyección · costo comparable con precio/kg del lote</div>
  </div>
</div>""")
    
    if not lote_sel:
        st.info("Selecciona un lote en la Sección 03 para ver la predicción.")
        return
    
    st.write(f"📋 Lote: **{extract_lote_codigo(lote_sel)}**")
    
    # ── Datos base del lote ───────────────────────────────────
    info_plot_pred = SF[SF["LoteCompleto"] == lote_sel].iloc[0]
    zona_pred = info_plot_pred["ZonaNombre"]
    tipo_pred = info_plot_pred["TipoStd"]
    quint_pred = info_plot_pred["Quintil"]
    repro_pred = info_plot_pred["ReproductoraStd"] if "ReproductoraStd" in info_plot_pred.index else "SIN_DATO"
    
    # ── Histórico para visualización ──────────────────────────
    hist_real_plot = DF_FILTRADO[DF_FILTRADO["LoteCompleto"] == lote_sel].copy()
    hist_real_plot["Edad"] = pd.to_numeric(hist_real_plot["Edad"], errors="coerce")
    hist_real_plot["PesoFinal"] = pd.to_numeric(hist_real_plot["PesoFinal"], errors="coerce")
    
    for c in [
        "AvesVivas", "CostoAcum", "CostoAlimentoDia", "_alim_dia", "AlimAcumKg",
        "PrecioKg", "PrecioKgRealDia", "KgLive", "FCR_Cum",
        "FCR_ideal", "PesoIdeal_comp", "KgLiveIdeal_comp",
        "AlimIdealAcum_comp", "AlimIdealDia_comp",
        "CostoIdealDia_comp", "CostoIdealComp", "GapCostoComp"
    ]:
        if c in hist_real_plot.columns:
            hist_real_plot[c] = pd.to_numeric(hist_real_plot[c], errors="coerce")
    
    hist_real_plot = (
        hist_real_plot[
            hist_real_plot["Edad"].notna() &
            hist_real_plot["PesoFinal"].notna() &
            (hist_real_plot["PesoFinal"] > 0)
        ]
        .sort_values("Edad")
        .copy()
    )
    
    if hist_real_plot.empty:
        st.warning("No hay historial válido para este lote.")
        return
    
    edad_actual = int(hist_real_plot.iloc[-1]["Edad"])
    peso_actual = float(hist_real_plot.iloc[-1]["PesoFinal"])
    aves_actual = (
        float(hist_real_plot.iloc[-1]["AvesVivas"])
        if "AvesVivas" in hist_real_plot.columns and pd.notna(hist_real_plot.iloc[-1]["AvesVivas"])
        else np.nan
    )
    
    target_pred_day = max(TARGET_DAY, edad_actual)
    dias_rest = max(0, TARGET_DAY - edad_actual)
    
    # ── Precio/kg del galpón ──────────────────────────────────
    if "PrecioKgRealDia" not in hist_real_plot.columns:
        hist_real_plot["PrecioKgRealDia"] = np.nan
    
    hist_real_plot["PrecioKgRealDia"] = pd.to_numeric(hist_real_plot["PrecioKgRealDia"], errors="coerce")
    hist_real_plot["PrecioKgRealDia"] = hist_real_plot["PrecioKgRealDia"].ffill().bfill()
    
    serie_precios_validos = hist_real_plot["PrecioKgRealDia"].dropna()
    precio_kg_ultimo = (
        float(serie_precios_validos.iloc[-1])
        if not serie_precios_validos.empty
        else np.nan
    )
    precio_kg_promedio_ref = (
        float(serie_precios_validos.tail(7).mean())
        if not serie_precios_validos.empty
        else np.nan
    )
    
    if pd.isna(precio_kg_promedio_ref):
        precio_kg_promedio_ref = precio_kg_ultimo
    if pd.isna(precio_kg_ultimo):
        precio_kg_ultimo = precio_kg_promedio_ref
    
    # ── Cache de predicción ───────────────────────────────────
    cache_key = f"{lote_sel}__d{target_pred_day}"
    
    if cache_key not in pred_cache:
        with st.spinner("⏳ Calculando predicción..."):
            hist_raw_model = DF_ALL[DF_ALL["LoteCompleto"] == lote_sel].sort_values("Edad").copy()
            hist_pred = _limpiar_historial_para_modelo(hist_raw_model)
            
            if hist_pred.empty:
                pred_cache[cache_key] = {"error": "Historial vacío (PesoFinal válido)"}
            else:
                res = predictor.proyectar_curva(
                    hist_lote=hist_pred,
                    target_edad=target_pred_day,
                    enforce_monotonic="isotonic",
                )
                pred_cache[cache_key] = {"res": res, "hist_pred": hist_pred}
    
    cache_item = pred_cache.get(cache_key, {})
    
    if cache_item.get("error"):
        st.error(f"❌ {cache_item['error']}")
        return
    
    res = cache_item.get("res", {})
    hist_pred_guardado = cache_item.get("hist_pred")
    
    if res.get("error"):
        st.error(f"❌ Error en predicción: {res['error']}")
        return
    
    # ── Procesar predicción ───────────────────────────────────
    df_curve = res.get("df")
    
    if not hist_real_plot.empty:
        edad_actual = int(hist_real_plot.iloc[-1]["Edad"])
        peso_actual = float(hist_real_plot.iloc[-1]["PesoFinal"])
    else:
        edad_actual = int(res.get("edad_actual", int(hist_pred_guardado.iloc[-1]["Edad"])))
        peso_actual = float(hist_pred_guardado.iloc[-1]["PesoFinal"])
    
    # ── Curva ideal extendida ─────────────────────────────────
    ideal_pred_plot = get_curva_ideal_promedio(
        zona_pred,
        tipo_pred,
        quint_pred,
        IDEALES,
        edad_max=TARGET_DAY,
        reproductora=repro_pred,
    )
    
    ideal_ycol = None
    if ideal_pred_plot is not None and not ideal_pred_plot.empty:
        ideal_pred_plot = ideal_pred_plot.copy()
        ideal_pred_plot["Edad"] = pd.to_numeric(ideal_pred_plot["Edad"], errors="coerce")
        
        for c in ["Peso", "Peso_ideal", "PesoIdeal"]:
            if c in ideal_pred_plot.columns:
                ideal_ycol = c
                break
        
        if ideal_ycol is not None:
            ideal_pred_plot[ideal_ycol] = pd.to_numeric(ideal_pred_plot[ideal_ycol], errors="coerce")
            if "FCR_ideal" in ideal_pred_plot.columns:
                ideal_pred_plot["FCR_ideal"] = pd.to_numeric(ideal_pred_plot["FCR_ideal"], errors="coerce")
            else:
                ideal_pred_plot["FCR_ideal"] = np.nan
            
            dias_full = pd.DataFrame({"Edad": np.arange(1, TARGET_DAY + 1, dtype=int)})
            ideal_pred_plot = dias_full.merge(ideal_pred_plot, on="Edad", how="left").sort_values("Edad")
            ideal_pred_plot[ideal_ycol] = (
                pd.to_numeric(ideal_pred_plot[ideal_ycol], errors="coerce")
                .interpolate(limit_direction="both")
                .ffill()
                .bfill()
            )
            ideal_pred_plot["FCR_ideal"] = (
                pd.to_numeric(ideal_pred_plot["FCR_ideal"], errors="coerce")
                .ffill()
                .bfill()
            )
            ideal_pred_plot = ideal_pred_plot[ideal_pred_plot["Edad"] <= TARGET_DAY].copy()
    
    # ── Proyección ajustada ───────────────────────────────────
    peso_objetivo = np.nan
    costo_estimado_obj = np.nan
    gap_estimado_obj = np.nan
    ycol_pred = None
    df_curve_plot = pd.DataFrame()
    
    if df_curve is not None and isinstance(df_curve, pd.DataFrame) and not df_curve.empty:
        df_curve_plot = df_curve.copy()
        df_curve_plot["Dia"] = pd.to_numeric(df_curve_plot["Dia"], errors="coerce").astype(int)
        
        ycol_pred = (
            "Peso_pred_kg" if "Peso_pred_kg" in df_curve_plot.columns
            else ("Peso_kg" if "Peso_kg" in df_curve_plot.columns else None)
        )
        
        if ycol_pred:
            df_curve_plot[ycol_pred] = pd.to_numeric(df_curve_plot[ycol_pred], errors="coerce")
            
            if not (df_curve_plot["Dia"] == edad_actual).any():
                df_curve_plot = pd.concat(
                    [df_curve_plot, pd.DataFrame({"Dia": [edad_actual], ycol_pred: [np.nan]})],
                    ignore_index=True,
                ).sort_values("Dia")
            
            pred_en_hoy = df_curve_plot.loc[df_curve_plot["Dia"] == edad_actual, ycol_pred].iloc[0]
            if pd.isna(pred_en_hoy):
                pred_en_hoy = peso_actual
            
            delta = float(peso_actual) - float(pred_en_hoy)
            m = df_curve_plot["Dia"] >= edad_actual
            df_curve_plot.loc[m, ycol_pred] = df_curve_plot.loc[m, ycol_pred].astype(float) + delta
            df_curve_plot.loc[m, ycol_pred] = np.maximum(df_curve_plot.loc[m, ycol_pred].values, float(peso_actual))
            df_curve_plot.loc[m, ycol_pred] = np.maximum.accumulate(df_curve_plot.loc[m, ycol_pred].values)
            
            df_curve_plot = df_curve_plot[df_curve_plot["Dia"] <= TARGET_DAY].copy()
    
    # ── Datos para visualización ──────────────────────────────
    hist_real_hover = hist_real_plot.copy().sort_values("Edad").reset_index(drop=True)
    hist_real_hover["CostoIdealAcum_comp"] = hist_real_hover.get("CostoIdealComp", np.nan)
    hist_real_hover["GapCosto_comp"] = hist_real_hover.get("GapCostoComp", np.nan)
    hist_real_hover["AlimIdealAcum_comp"] = hist_real_hover.get("AlimIdealAcum_comp", np.nan)
    hist_real_hover["FCR_ideal"] = hist_real_hover.get("FCR_ideal", np.nan)
    hist_real_hover = hist_real_hover[hist_real_hover["Edad"] <= TARGET_DAY].copy()
    
    costo_real_hoy = (
        float(hist_real_hover.iloc[-1]["CostoAcum"])
        if not hist_real_hover.empty and pd.notna(hist_real_hover.iloc[-1]["CostoAcum"])
        else np.nan
    )
    costo_ideal_hoy = (
        float(hist_real_hover.iloc[-1]["CostoIdealAcum_comp"])
        if not hist_real_hover.empty and pd.notna(hist_real_hover.iloc[-1]["CostoIdealAcum_comp"])
        else np.nan
    )
    alim_ideal_hoy = (
        float(hist_real_hover.iloc[-1]["AlimIdealAcum_comp"])
        if not hist_real_hover.empty and pd.notna(hist_real_hover.iloc[-1]["AlimIdealAcum_comp"])
        else np.nan
    )
    
    factor_desvio = (
        costo_real_hoy / costo_ideal_hoy
        if pd.notna(costo_real_hoy) and pd.notna(costo_ideal_hoy) and costo_ideal_hoy > 0
        else 1.0
    )
    
    # ── Ideal line con costo comparable ───────────────────────
    ideal_line_df = pd.DataFrame()
    if ideal_pred_plot is not None and not ideal_pred_plot.empty and ideal_ycol is not None:
        ideal_line_df = ideal_pred_plot.copy()
        ideal_line_df = ideal_line_df.rename(columns={ideal_ycol: "PesoIdeal"})
        ideal_line_df = ideal_line_df.merge(
            hist_real_plot[["Edad", "PrecioKgRealDia", "AvesVivas", "CostoAcum", "AlimAcumKg", "FCR_Cum"]],
            on="Edad", how="left"
        ).sort_values("Edad")
        
        ideal_line_df["PrecioKgRealDia"] = (
            ideal_line_df["PrecioKgRealDia"]
            .ffill()
            .bfill()
            .fillna(precio_kg_promedio_ref)
        )
        ideal_line_df["AvesVivas"] = ideal_line_df["AvesVivas"].ffill().bfill().fillna(aves_actual)
        ideal_line_df["CostoAcum"] = ideal_line_df["CostoAcum"].ffill()
        ideal_line_df["AlimAcumKg"] = ideal_line_df["AlimAcumKg"].ffill()
        ideal_line_df["FCR_Cum"] = ideal_line_df["FCR_Cum"].ffill()
        
        ideal_line_df["KgLiveIdeal"] = ideal_line_df["AvesVivas"] * ideal_line_df["PesoIdeal"]
        ideal_line_df["AlimIdealAcum_line"] = ideal_line_df["FCR_ideal"] * ideal_line_df["KgLiveIdeal"]
        ideal_line_df["AlimIdealDia_line"] = ideal_line_df["AlimIdealAcum_line"].diff()
        
        if not ideal_line_df.empty:
            ideal_line_df.loc[ideal_line_df.index[0], "AlimIdealDia_line"] = ideal_line_df.iloc[0]["AlimIdealAcum_line"]
        
        ideal_line_df["AlimIdealDia_line"] = ideal_line_df["AlimIdealDia_line"].clip(lower=0)
        ideal_line_df["CostoIdealDia_line"] = ideal_line_df["AlimIdealDia_line"] * ideal_line_df["PrecioKgRealDia"]
        ideal_line_df["CostoIdealAcum_line"] = ideal_line_df["CostoIdealDia_line"].fillna(0).cumsum()
        ideal_line_df["GapCosto_line"] = ideal_line_df["CostoAcum"] - ideal_line_df["CostoIdealAcum_line"]
        
        ideal_line_df = ideal_line_df[ideal_line_df["Edad"] <= TARGET_DAY].copy()
    
    # ── Proyección con costo comparable ───────────────────────
    proj_cost_df = pd.DataFrame()
    if not df_curve_plot.empty and ycol_pred is not None:
        proj_cost_df = df_curve_plot.copy()
        
        if ideal_pred_plot is not None and not ideal_pred_plot.empty and "FCR_ideal" in ideal_pred_plot.columns:
            proj_cost_df = proj_cost_df.merge(
                ideal_pred_plot[["Edad", "FCR_ideal"]].rename(columns={"Edad": "Dia"}),
                on="Dia", how="left"
            )
        else:
            proj_cost_df["FCR_ideal"] = np.nan
        
        proj_cost_df["FCR_ideal"] = (
            pd.to_numeric(proj_cost_df["FCR_ideal"], errors="coerce")
            .ffill()
            .bfill()
        )
        proj_cost_df["AvesRef"] = aves_actual
        proj_cost_df["PrecioKgRef"] = precio_kg_promedio_ref
        proj_cost_df["KgLivePred"] = proj_cost_df["AvesRef"] * proj_cost_df[ycol_pred]
        proj_cost_df["AlimIdealAcum_pred"] = proj_cost_df["FCR_ideal"] * proj_cost_df["KgLivePred"]
        
        if pd.notna(alim_ideal_hoy):
            proj_cost_df["DeltaAlimIdeal_pred"] = (proj_cost_df["AlimIdealAcum_pred"] - alim_ideal_hoy).clip(lower=0)
        else:
            proj_cost_df["DeltaAlimIdeal_pred"] = np.nan
        
        if pd.notna(costo_ideal_hoy):
            proj_cost_df["CostoIdealAcum_pred"] = costo_ideal_hoy + (
                proj_cost_df["DeltaAlimIdeal_pred"] * proj_cost_df["PrecioKgRef"]
            )
        else:
            proj_cost_df["CostoIdealAcum_pred"] = proj_cost_df["AlimIdealAcum_pred"] * proj_cost_df["PrecioKgRef"]
        
        proj_cost_df["CostoAcum_estimado"] = proj_cost_df["CostoIdealAcum_pred"] * factor_desvio
        proj_cost_df["GapCosto_estimado"] = proj_cost_df["CostoAcum_estimado"] - proj_cost_df["CostoIdealAcum_pred"]
        
        proj_cost_df = proj_cost_df[
            (proj_cost_df["Dia"] >= edad_actual) &
            (proj_cost_df["Dia"] <= TARGET_DAY)
        ].copy()
        
        fila_obj = proj_cost_df[proj_cost_df["Dia"] == TARGET_DAY]
        if fila_obj.empty and not proj_cost_df.empty:
            fila_obj = proj_cost_df.tail(1)
        
        if not fila_obj.empty:
            peso_objetivo = float(fila_obj.iloc[0][ycol_pred]) if pd.notna(fila_obj.iloc[0][ycol_pred]) else np.nan
            costo_estimado_obj = float(fila_obj.iloc[0]["CostoAcum_estimado"]) if pd.notna(fila_obj.iloc[0]["CostoAcum_estimado"]) else np.nan
            gap_estimado_obj = float(fila_obj.iloc[0]["GapCosto_estimado"]) if pd.notna(fila_obj.iloc[0]["GapCosto_estimado"]) else np.nan
    
    # Fallback si no hay proyección
    if pd.isna(peso_objetivo):
        fila_real_obj = hist_real_hover[hist_real_hover["Edad"] == TARGET_DAY]
        if fila_real_obj.empty and not hist_real_hover.empty:
            fila_real_obj = hist_real_hover.tail(1)
        
        if not fila_real_obj.empty:
            peso_objetivo = float(fila_real_obj.iloc[0]["PesoFinal"]) if pd.notna(fila_real_obj.iloc[0]["PesoFinal"]) else peso_actual
            costo_estimado_obj = float(fila_real_obj.iloc[0]["CostoAcum"]) if pd.notna(fila_real_obj.iloc[0]["CostoAcum"]) else np.nan
            gap_estimado_obj = float(fila_real_obj.iloc[0]["GapCosto_comp"]) if pd.notna(fila_real_obj.iloc[0]["GapCosto_comp"]) else np.nan
        else:
            peso_objetivo = peso_actual
    
    # ── KPIs superiores ───────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_small(f"{peso_objetivo:.3f} kg", f"Peso objetivo D{TARGET_DAY}", accent=True)
    with c2:
        render_kpi_small(f"{dias_rest} d", "Días restantes")
    with c3:
        render_kpi_small(fmt_manager(costo_estimado_obj, prefix="$"), f"Costo estimado D{TARGET_DAY}")
    with c4:
        render_kpi_small(fmt_manager(gap_estimado_obj, prefix="$"), f"Gap estimado D{TARGET_DAY}")
    
    # ── Gráfico: REAL + IDEAL + PROYECCIÓN ────────────────────
    fig_p = go.Figure()
    
    # 1) REAL
    if not hist_real_hover.empty:
        custom_real_pred = np.array([
            [
                fmt_num(r.get("PrecioKgRealDia", np.nan), 3, prefix="$", suffix="/kg"),
                fmt_manager(r.get("CostoAcum", np.nan), prefix="$"),
                fmt_manager(r.get("CostoIdealAcum_comp", np.nan), prefix="$"),
                fmt_signed_short(r.get("GapCosto_comp", np.nan), prefix="$"),
                fmt_manager(r.get("AlimAcumKg", np.nan), suffix=" kg"),
                fmt_manager(r.get("AlimIdealAcum_comp", np.nan), suffix=" kg"),
                fmt_num(r.get("FCR_Cum", np.nan), 4),
                fmt_num(r.get("FCR_ideal", np.nan), 4),
            ]
            for _, r in hist_real_hover.iterrows()
        ], dtype=object)
        
        fig_p.add_trace(go.Scatter(
            x=hist_real_hover["Edad"],
            y=hist_real_hover["PesoFinal"],
            mode="lines+markers",
            name="REAL",
            line=dict(color="#0066cc", width=3),
            marker=dict(size=6, color="#0066cc", line=dict(color="white", width=1)),
            customdata=custom_real_pred,
            hovertemplate=(
                "<b>── REAL ──</b><br>"
                "Día %{x}<br>"
                "Peso: <b>%{y:.3f} kg</b><br>"
                "Precio kg real: %{customdata[0]}<br>"
                "Costo real: <b>%{customdata[1]}</b><br>"
                "Costo ideal comparable: %{customdata[2]}<br>"
                "Gap: %{customdata[3]}<br>"
                "Alim real acum: %{customdata[4]}<br>"
                "Alim ideal acum: %{customdata[5]}<br>"
                "FCR real: %{customdata[6]}<br>"
                "FCR ideal: %{customdata[7]}"
                "<extra></extra>"
            ),
        ))
    
    # 2) IDEAL
    if not ideal_line_df.empty:
        custom_ideal_pred = np.array([
            [
                fmt_num(r.get("PrecioKgRealDia", np.nan), 3, prefix="$", suffix="/kg"),
                fmt_manager(r.get("CostoAcum", np.nan), prefix="$"),
                fmt_manager(r.get("CostoIdealAcum_line", np.nan), prefix="$"),
                fmt_signed_short(r.get("GapCosto_line", np.nan), prefix="$"),
                fmt_manager(r.get("AlimAcumKg", np.nan), suffix=" kg"),
                fmt_manager(r.get("AlimIdealAcum_line", np.nan), suffix=" kg"),
                fmt_num(r.get("FCR_Cum", np.nan), 4),
                fmt_num(r.get("FCR_ideal", np.nan), 4),
            ]
            for _, r in ideal_line_df.iterrows()
        ], dtype=object)
        
        fig_p.add_trace(go.Scatter(
            x=ideal_line_df["Edad"],
            y=ideal_line_df["PesoIdeal"],
            mode="lines+markers",
            name="IDEAL",
            line=dict(color=GREEN, width=3, dash="dot"),
            marker=dict(size=5, symbol="diamond", color=GREEN, line=dict(color="white", width=1)),
            customdata=custom_ideal_pred,
            hovertemplate=(
                "<b>── IDEAL ──</b><br>"
                "Día %{x}<br>"
                "Peso ideal: <b>%{y:.3f} kg</b><br>"
                "Precio kg referencia: %{customdata[0]}<br>"
                "Costo real: %{customdata[1]}<br>"
                "Costo ideal comparable: <b>%{customdata[2]}</b><br>"
                "Gap: %{customdata[3]}<br>"
                "Alim real acum: %{customdata[4]}<br>"
                "Alim ideal acum: %{customdata[5]}<br>"
                "FCR real: %{customdata[6]}<br>"
                "FCR ideal: %{customdata[7]}"
                "<extra></extra>"
            ),
        ))
    
    # 3) PROYECCIÓN
    if not proj_cost_df.empty and ycol_pred is not None:
        custom_pred_cost = np.array([
            [
                fmt_num(r.get("PrecioKgRef", np.nan), 3, prefix="$", suffix="/kg"),
                fmt_manager(r.get("CostoIdealAcum_pred", np.nan), prefix="$"),
                fmt_manager(r.get("CostoAcum_estimado", np.nan), prefix="$"),
                fmt_signed_short(r.get("GapCosto_estimado", np.nan), prefix="$"),
                fmt_manager(r.get("AlimIdealAcum_pred", np.nan), suffix=" kg"),
                fmt_num(r.get("FCR_ideal", np.nan), 4),
            ]
            for _, r in proj_cost_df.iterrows()
        ], dtype=object)
        
        fig_p.add_trace(go.Scatter(
            x=proj_cost_df["Dia"],
            y=proj_cost_df[ycol_pred],
            mode="lines+markers",
            name="PROYECCIÓN",
            line=dict(color=RED, width=3, dash="dash"),
            marker=dict(size=5, color=RED),
            customdata=custom_pred_cost,
            hovertemplate=(
                "<b>── PROYECCIÓN ──</b><br>"
                "Día %{x}<br>"
                "Peso proyectado: <b>%{y:.3f} kg</b><br>"
                "Precio kg referencia: %{customdata[0]}<br>"
                "Costo ideal proyectado: %{customdata[1]}<br>"
                "Costo estimado proyectado: <b>%{customdata[2]}</b><br>"
                "Gap estimado: %{customdata[3]}<br>"
                "Alim ideal acum: %{customdata[4]}<br>"
                "FCR ideal: %{customdata[5]}"
                "<extra></extra>"
            ),
        ))
    
    # 4) Punto objetivo
    if not proj_cost_df.empty and ycol_pred is not None:
        fila_d = proj_cost_df[proj_cost_df["Dia"] == TARGET_DAY]
        if not fila_d.empty:
            fig_p.add_trace(go.Scatter(
                x=[TARGET_DAY],
                y=[float(fila_d.iloc[0][ycol_pred])],
                mode="markers",
                name=f"D{TARGET_DAY}",
                marker=dict(size=10, symbol="diamond", color=RED),
                hovertemplate=f"Día {TARGET_DAY}<br>%{{y:.3f}} kg<extra></extra>",
            ))
    
    if edad_actual <= TARGET_DAY:
        fig_p.add_vline(
            x=edad_actual,
            line_dash="dot",
            line_color=AMBER,
            annotation_text=f"Hoy: día {edad_actual}",
            annotation_font=dict(size=9, color=CHART_TEXT),
            annotation_position="top right",
        )
    
    fig_p.update_layout(
        template="plotly_white",
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        height=340,
        margin=dict(l=8, r=8, t=22, b=8),
        font=dict(family="DM Sans", size=11, color=CHART_TEXT),
        legend=dict(
            orientation="h",
            y=-0.17,
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=CHART_TEXT)
        ),
        xaxis=dict(
            title="Edad (días)",
            gridcolor=BORDER,
            color=CHART_TEXT,
            tickfont=dict(color=CHART_TEXT),
            title_font=dict(color=CHART_TEXT),
            dtick=7,
            range=[0, TARGET_DAY]
        ),
        yaxis=dict(
            title="Peso (kg)",
            gridcolor=BORDER,
            color=CHART_TEXT,
            tickfont=dict(color=CHART_TEXT),
            title_font=dict(color=CHART_TEXT)
        ),
        hovermode="x unified",
        title=dict(
            text=f"Real vs Ideal vs Proyección · {zona_pred} · {tipo_pred} · {repro_pred} · {quint_pred}",
            font=dict(size=10, color=CHART_TEXT),
            x=0,
        ),
    )
    st.plotly_chart(fig_p, width="stretch", key=f"chart_pred_{lote_sel}")