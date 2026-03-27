import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from config import BLACK, CARD, BORDER, RED, GREEN, AMBER, MUTED
from helpers import md, fmt_num, extract_lote_codigo
from dashboard_kpis import fmt_manager, fmt_signed_short, render_kpi_small

CHART_TEXT = BLACK


def normalizar_historico(hist_cmp):
    """Normaliza columnas del histórico a numéricos"""
    num_cols = [
        "Edad", "PesoFinal", "AvesVivas", "MortPct", "CostoAcum", "CostoKg_Cum",
        "AlimAcumKg", "_alim_dia", "CostoAlimentoDia", "KgLive",
        "PrecioKg", "PrecioKgRealDia", "FCR_Cum",
        "FCR_ideal", "PesoIdeal_comp", "KgLiveIdeal_comp",
        "AlimIdealAcum_comp", "AlimIdealDia_comp",
        "CostoIdealDia_comp", "CostoIdealComp", "GapCostoComp"
    ]
    for c in num_cols:
        if c in hist_cmp.columns:
            hist_cmp[c] = pd.to_numeric(hist_cmp[c], errors="coerce")
    
    # Alias amigables
    hist_cmp["PesoIdeal"] = hist_cmp.get("PesoIdeal_comp", np.nan)
    hist_cmp["KgLiveIdeal_calc"] = hist_cmp.get("KgLiveIdeal_comp", np.nan)
    hist_cmp["AlimIdealAcum_calc"] = hist_cmp.get("AlimIdealAcum_comp", np.nan)
    hist_cmp["AlimIdealDia_calc"] = hist_cmp.get("AlimIdealDia_comp", np.nan)
    hist_cmp["CostoIdealDia_calc"] = hist_cmp.get("CostoIdealDia_comp", np.nan)
    hist_cmp["CostoIdealAcum_calc"] = hist_cmp.get("CostoIdealComp", np.nan)
    hist_cmp["DifCosto_calc"] = hist_cmp.get("GapCostoComp", np.nan)
    
    return hist_cmp


def extraer_metricas_lote(hist_cmp, fcr_col_hist="FCR_Cum"):
    """Extrae métricas finales del lote"""
    last_cmp = hist_cmp.iloc[-1]
    
    aves_v = last_cmp.get("AvesVivas", np.nan)
    mort_pct = last_cmp.get("MortPct", np.nan)
    costo_acum = last_cmp.get("CostoAcum", np.nan)
    alim_acum = last_cmp.get("AlimAcumKg", np.nan)
    kg_live_lote = last_cmp.get("KgLive", np.nan)
    precio_kg_real = last_cmp.get("PrecioKgRealDia", np.nan)
    alim_ideal_acum = last_cmp.get("AlimIdealAcum_calc", np.nan)
    kg_live_ideal_calc = last_cmp.get("KgLiveIdeal_calc", np.nan)
    alim_dia = last_cmp.get("_alim_dia", np.nan)
    
    # Calcular alim_dia si no existe
    if (pd.isna(alim_dia) or alim_dia == 0) and len(hist_cmp) >= 2:
        prev_alim = hist_cmp.iloc[-2].get("AlimAcumKg", np.nan)
        if pd.notna(alim_acum) and pd.notna(prev_alim):
            alim_dia = alim_acum - prev_alim
    
    fcr_real_ult = float(last_cmp.get(fcr_col_hist, np.nan)) if pd.notna(last_cmp.get(fcr_col_hist, np.nan)) else np.nan
    fcr_ideal_ult = float(last_cmp.get("FCR_ideal", np.nan)) if pd.notna(last_cmp.get("FCR_ideal", np.nan)) else np.nan
    costo_ideal_ult = float(last_cmp.get("CostoIdealAcum_calc", np.nan)) if pd.notna(last_cmp.get("CostoIdealAcum_calc", np.nan)) else np.nan
    
    gap_fcr = fcr_real_ult - fcr_ideal_ult if pd.notna(fcr_real_ult) and pd.notna(fcr_ideal_ult) else np.nan
    gap_costo = costo_acum - costo_ideal_ult if pd.notna(costo_acum) and pd.notna(costo_ideal_ult) else np.nan
    gap_costo_kg = (
        gap_costo / kg_live_lote
        if pd.notna(gap_costo) and pd.notna(kg_live_lote) and kg_live_lote > 0
        else np.nan
    )
    
    return {
        "aves_v": aves_v,
        "mort_pct": mort_pct,
        "costo_acum": costo_acum,
        "alim_acum": alim_acum,
        "kg_live_lote": kg_live_lote,
        "precio_kg_real": precio_kg_real,
        "alim_ideal_acum": alim_ideal_acum,
        "kg_live_ideal_calc": kg_live_ideal_calc,
        "alim_dia": alim_dia,
        "fcr_real_ult": fcr_real_ult,
        "fcr_ideal_ult": fcr_ideal_ult,
        "costo_ideal_ult": costo_ideal_ult,
        "gap_fcr": gap_fcr,
        "gap_costo": gap_costo,
        "gap_costo_kg": gap_costo_kg,
    }


def render_tarjetas_lote(info, nombre_g, lote_codigo, galpon_v, zona_v, tipo_v, repro_v, quint_v):
    """Renderiza tarjetas de identidad y KPIs del lote"""
    md(f'''<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;">
<div class="sel-pill-neutral">🏭 <strong>{nombre_g}</strong></div>
<div class="sel-pill-neutral">🔖 {lote_codigo}</div>
<div class="sel-pill-neutral">🏠 Galpón <strong>{galpon_v}</strong></div>
<div class="sel-pill-neutral">📍 {zona_v} · {tipo_v} · {repro_v} · {quint_v}</div>
</div>''')
    
    edad_act = int(info.get("edad_act", 0))
    
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        render_kpi_small(f"{edad_act} d", "Edad actual")
    with c2:
        render_kpi_small(fmt_manager(info["kg_live_lote"], suffix=" kg"), "Kg vivo real")
    with c3:
        render_kpi_small(fmt_num(info["precio_kg_real"], 3, prefix="$", suffix="/kg"), "$ kg real")
    with c4:
        render_kpi_small(fmt_manager(info["costo_acum"], prefix="$"), "$ Real Acum", accent=True)
    with c5:
        render_kpi_small(fmt_manager(info["costo_ideal_ult"], prefix="$"), "$ Ideal Com")
    with c6:
        diff_badge = "red" if pd.notna(info["gap_costo"]) and info["gap_costo"] > 0 else "green"
        diff_txt = fmt_signed_short(info["gap_costo"], prefix="$")
        render_kpi_small(f'<span class="badge {diff_badge}">{diff_txt}</span>', "Sobrecosto vs ideal", accent=True)
    
    c7, c8, c9, c10, c11, c12 = st.columns(6)
    with c7:
        render_kpi_small(fmt_num(info["fcr_real_ult"], 4), "Conv Real")
    with c8:
        render_kpi_small(fmt_num(info["fcr_ideal_ult"], 4), "Conv Ideal")
    with c9:
        gap_badge = "red" if pd.notna(info["gap_fcr"]) and info["gap_fcr"] > 0 else "green"
        gap_txt = fmt_signed_short(info["gap_fcr"])
        render_kpi_small(f'<span class="badge {gap_badge}">{gap_txt}</span>', "Gap Conv")
    with c10:
        render_kpi_small(fmt_manager(info["alim_ideal_acum"], suffix=" kg"), "Alim ideal")
    with c11:
        render_kpi_small(fmt_num(info["gap_costo_kg"], 4, prefix="$"), "Gap $/kg")
    with c12:
        render_kpi_small(fmt_num(info["mort_pct"], 2, suffix="%"), "Mortalidad")


def render_grafico_crecimiento(hist_v, info, zona_v, tipo_v, repro_v, quint_v, nombre_g, galpon_v, lote_sel, EDAD_MIN_ANALISIS):
    """Renderiza gráfico de crecimiento REAL vs IDEAL"""
    
    fcr_col_hist = "FCR_Cum"
    custom_real = np.array([
        [
            fmt_num(r.get(fcr_col_hist, np.nan), 4),
            fmt_num(r.get("FCR_ideal", np.nan), 4),
            fmt_num(r.get("PrecioKgRealDia", np.nan), 3, prefix="$", suffix="/kg"),
            fmt_manager(r.get("CostoAcum", np.nan), prefix="$"),
            fmt_manager(r.get("CostoIdealAcum_calc", np.nan), prefix="$"),
            fmt_signed_short(r.get("DifCosto_calc", np.nan), prefix="$"),
            fmt_manager(r.get("AlimAcumKg", np.nan), suffix=" kg"),
            fmt_manager(r.get("AlimIdealAcum_calc", np.nan), suffix=" kg"),
        ]
        for _, r in hist_v.iterrows()
    ], dtype=object)
    
    hover_real = (
        "<b>── REAL ──</b><br>"
        "Día %{x}<br>"
        "Peso real: <b>%{y:.3f} kg</b><br>"
        "FCR real: %{customdata[0]}<br>"
        "FCR ideal: %{customdata[1]}<br>"
        "Precio kg real: %{customdata[2]}<br>"
        "Costo real acum: <b>%{customdata[3]}</b><br>"
        "Costo ideal comparable: %{customdata[4]}<br>"
        "Diferencia: %{customdata[5]}<br>"
        "Alim real acum: %{customdata[6]}<br>"
        "Alim ideal acum: %{customdata[7]}"
        "<extra></extra>"
    )
    
    fig_ri = go.Figure()
    fig_ri.add_trace(go.Scatter(
        x=hist_v["Edad"], y=hist_v["PesoFinal"],
        mode="lines+markers", name="🔴 REAL",
        line=dict(color=RED, width=3),
        marker=dict(size=6, color=RED, line=dict(color="white", width=1)),
        customdata=custom_real,
        hovertemplate=hover_real,
    ))
    
    tiene_ideal = hist_v["PesoIdeal"].notna().any()
    if tiene_ideal:
        ideal_plot = hist_v[hist_v["PesoIdeal"].notna()].copy()
        custom_ideal = np.array([
            [
                fmt_num(r.get(fcr_col_hist, np.nan), 4),
                fmt_num(r.get("FCR_ideal", np.nan), 4),
                fmt_num(r.get("PrecioKgRealDia", np.nan), 3, prefix="$", suffix="/kg"),
                fmt_manager(r.get("CostoAcum", np.nan), prefix="$"),
                fmt_manager(r.get("CostoIdealAcum_calc", np.nan), prefix="$"),
                fmt_signed_short(r.get("DifCosto_calc", np.nan), prefix="$"),
                fmt_manager(r.get("AlimAcumKg", np.nan), suffix=" kg"),
                fmt_manager(r.get("AlimIdealAcum_calc", np.nan), suffix=" kg"),
            ]
            for _, r in ideal_plot.iterrows()
        ], dtype=object)
        
        hover_ideal = (
            "<b>── IDEAL ──</b><br>"
            "Día %{x}<br>"
            "Peso ideal: <b>%{y:.3f} kg</b><br>"
            "FCR real: %{customdata[0]}<br>"
            "FCR ideal: %{customdata[1]}<br>"
            "Precio kg real: %{customdata[2]}<br>"
            "Costo real acum: %{customdata[3]}<br>"
            "Costo ideal comparable: <b>%{customdata[4]}</b><br>"
            "Diferencia: %{customdata[5]}<br>"
            "Alim real acum: %{customdata[6]}<br>"
            "Alim ideal acum: %{customdata[7]}"
            "<extra></extra>"
        )
        
        fig_ri.add_trace(go.Scatter(
            x=ideal_plot["Edad"], y=ideal_plot["PesoIdeal"],
            mode="lines+markers", name="🟢 IDEAL",
            line=dict(color=GREEN, width=2.5, dash="dash"),
            marker=dict(size=5, symbol="diamond", color=GREEN, line=dict(color="white", width=1)),
            customdata=custom_ideal,
            hovertemplate=hover_ideal,
        ))
        
        hm = hist_v[hist_v["PesoIdeal"].notna()].copy()
        if not hm.empty:
            fig_ri.add_trace(go.Scatter(
                x=hm["Edad"].tolist() + hm["Edad"].tolist()[::-1],
                y=hm["PesoFinal"].tolist() + hm["PesoIdeal"].tolist()[::-1],
                fill="toself", name="GAP",
                fillcolor="rgba(218,41,28,0.28)",
                line=dict(color="rgba(255,255,255,0)"),
                hoverinfo="skip", showlegend=True,
            ))
    
    edad_act = info.get("edad_act", 0)
    edad_max_lote = pd.to_numeric(hist_v["Edad"], errors="coerce").max()
    dtick_x = 1 if pd.notna(edad_max_lote) and edad_max_lote <= 10 else 7
    
    fig_ri.add_vline(
        x=edad_act, line_dash="dot", line_color=AMBER,
        annotation_text=f"Hoy: día {edad_act}",
        annotation_font=dict(size=9, color=CHART_TEXT),
        annotation_position="top right",
    )
    
    fig_ri.update_layout(
        template="plotly_white",
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        height=320,
        margin=dict(l=8, r=8, t=28, b=8),
        font=dict(family="DM Sans", size=11, color=CHART_TEXT),
        legend=dict(
            orientation="h",
            y=-0.16,
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10, color=CHART_TEXT)
        ),
        xaxis=dict(
            title="Edad (días)",
            gridcolor=BORDER,
            color=CHART_TEXT,
            tickfont=dict(color=CHART_TEXT),
            title_font=dict(color=CHART_TEXT),
            dtick=dtick_x,
            tick0=0
        ),
        yaxis=dict(
            title="Peso vivo (kg)",
            gridcolor=BORDER,
            color=CHART_TEXT,
            tickfont=dict(color=CHART_TEXT),
            title_font=dict(color=CHART_TEXT)
        ),
        title=dict(
            text=f"Crecimiento · {zona_v} · {tipo_v} · {repro_v} · {quint_v} · {nombre_g} Gal.{galpon_v}",
            font=dict(size=10, color=CHART_TEXT),
            x=0,
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", font=dict(color="black")),
    )
    st.plotly_chart(fig_ri, width="stretch", key=f"chart_ri_{lote_sel}")


def render_grafico_costo(hist_c, info, lote_sel, EDAD_MIN_ANALISIS, edad_max_lote):
    """Renderiza gráfico de costo acumulado REAL vs IDEAL"""
    
    st.caption("**Costo acumulado comparable: REAL vs IDEAL usando el precio/kg real del galpón**")
    
    fcr_col_hist = "FCR_Cum"
    custom_real_c = np.array([
        [
            fmt_num(r.get("PrecioKgRealDia", np.nan), 3, prefix="$", suffix="/kg"),
            fmt_manager(r.get("CostoAcum", np.nan), prefix="$"),
            fmt_manager(r.get("CostoIdealAcum_calc", np.nan), prefix="$"),
            fmt_signed_short(r.get("DifCosto_calc", np.nan), prefix="$"),
            fmt_manager(r.get("AlimAcumKg", np.nan), suffix=" kg"),
            fmt_manager(r.get("AlimIdealAcum_calc", np.nan), suffix=" kg"),
            fmt_num(r.get(fcr_col_hist, np.nan), 4),
            fmt_num(r.get("FCR_ideal", np.nan), 4),
        ]
        for _, r in hist_c.iterrows()
    ], dtype=object)
    
    hover_real_c = (
        "<b>── REAL ──</b><br>"
        "Día %{x}<br>"
        "Costo real acum: <b>%{customdata[1]}</b><br>"
        "Costo ideal comparable: %{customdata[2]}<br>"
        "Diferencia: %{customdata[3]}<br>"
        "Precio kg real: %{customdata[0]}<br>"
        "FCR real: %{customdata[6]}<br>"
        "FCR ideal: %{customdata[7]}<br>"
        "Alim real acum: %{customdata[4]}<br>"
        "Alim ideal acum: %{customdata[5]}"
        "<extra></extra>"
    )
    
    fig_c = go.Figure()
    fig_c.add_trace(go.Scatter(
        x=hist_c["Edad"], y=hist_c["CostoAcum"],
        mode="lines+markers", name="Costo Real",
        line=dict(color=RED, width=3),
        marker=dict(size=6, color=RED, line=dict(color="white", width=1)),
        fill="tozeroy", fillcolor="rgba(218,41,28,0.08)",
        customdata=custom_real_c,
        hovertemplate=hover_real_c,
    ))
    
    tiene_ideal = hist_c["CostoIdealAcum_calc"].notna().any()
    if tiene_ideal:
        ideal_c = hist_c[hist_c["CostoIdealAcum_calc"].notna()].copy()
        if not ideal_c.empty:
            custom_ideal_c = np.array([
                [
                    fmt_num(r.get("PrecioKgRealDia", np.nan), 3, prefix="$", suffix="/kg"),
                    fmt_manager(r.get("CostoAcum", np.nan), prefix="$"),
                    fmt_manager(r.get("CostoIdealAcum_calc", np.nan), prefix="$"),
                    fmt_signed_short(r.get("DifCosto_calc", np.nan), prefix="$"),
                    fmt_manager(r.get("AlimAcumKg", np.nan), suffix=" kg"),
                    fmt_manager(r.get("AlimIdealAcum_calc", np.nan), suffix=" kg"),
                    fmt_num(r.get(fcr_col_hist, np.nan), 4),
                    fmt_num(r.get("FCR_ideal", np.nan), 4),
                ]
                for _, r in ideal_c.iterrows()
            ], dtype=object)
            
            hover_ideal_c = (
                "<b>── IDEAL ──</b><br>"
                "Día %{x}<br>"
                "Costo real acum: %{customdata[1]}<br>"
                "Costo ideal comparable: <b>%{customdata[2]}</b><br>"
                "Diferencia: %{customdata[3]}<br>"
                "Precio kg real: %{customdata[0]}<br>"
                "FCR real: %{customdata[6]}<br>"
                "FCR ideal: %{customdata[7]}<br>"
                "Alim real acum: %{customdata[4]}<br>"
                "Alim ideal acum: %{customdata[5]}"
                "<extra></extra>"
            )
            
            fig_c.add_trace(go.Scatter(
                x=ideal_c["Edad"], y=ideal_c["CostoIdealAcum_calc"],
                mode="lines+markers", name="Costo Ideal Comparable",
                line=dict(color=GREEN, width=2, dash="dash"),
                marker=dict(size=5, symbol="diamond", color=GREEN, line=dict(color="white", width=1)),
                customdata=custom_ideal_c,
                hovertemplate=hover_ideal_c,
            ))
    
    dtick_x = 1 if pd.notna(edad_max_lote) and edad_max_lote <= 10 else 7
    
    fig_c.update_layout(
        template="plotly_white",
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        height=270,
        margin=dict(l=8, r=8, t=18, b=8),
        font=dict(family="DM Sans", size=11, color=CHART_TEXT),
        legend=dict(
            orientation="h",
            y=-0.18,
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10, color=CHART_TEXT)
        ),
        xaxis=dict(
            title="Edad (días)",
            gridcolor=BORDER,
            color=CHART_TEXT,
            tickfont=dict(color=CHART_TEXT),
            title_font=dict(color=CHART_TEXT),
            dtick=dtick_x
        ),
        yaxis=dict(
            title="Costo alimento acum ($)",
            gridcolor=BORDER,
            color=CHART_TEXT,
            tickfont=dict(color=CHART_TEXT),
            title_font=dict(color=CHART_TEXT)
        ),
        hovermode="x unified",
    )
    st.plotly_chart(fig_c, width="stretch", key=f"chart_costo_{lote_sel}")


def render_sec03(lote_sel, SF, DF_FILTRADO, DF_ALL, IDEALES, EDAD_MIN_ANALISIS=15):
    """
    Sección 03: Lote Seleccionado - IDEAL vs REAL
    """
    
    md(f"""
<div class="sec-header">
<span class="sec-num">03</span>
<div>
    <div class="sec-title">Lote Seleccionado: Crecimiento IDEAL vs REAL</div>
    <div class="sec-sub">Análisis detallado · selecciona un galpón en la tabla de arriba</div>
</div>
</div>""")
    
    # ── Obtener lote disponibles ──────────────────────────────
    lotes_disp = SF["LoteCompleto"].dropna().unique().tolist()
    
    if not lote_sel or lote_sel not in lotes_disp:
        lote_sel = lotes_disp[0] if lotes_disp else None
    
    if not lote_sel:
        st.info("Selecciona un galpón en la tabla de arriba.")
        st.stop()
    
    # ── Cargar datos del lote ─────────────────────────────────
    il = SF[SF["LoteCompleto"] == lote_sel].iloc[0]
    hist = DF_FILTRADO[DF_FILTRADO["LoteCompleto"] == lote_sel].sort_values("Edad").copy()
    
    if hist.empty:
        st.warning("No hay historial para este lote.")
        st.stop()
    
    hist_cmp = hist.copy().reset_index(drop=True)
    hist_cmp = normalizar_historico(hist_cmp)
    hist_ord = hist_cmp.sort_values("Edad").copy()
    snap_last = hist_ord.iloc[-1]
    
    zona_v = il["ZonaNombre"]
    tipo_v = il["TipoStd"]
    quint_v = il["Quintil"]
    repro_v = il["ReproductoraStd"] if "ReproductoraStd" in il.index else "SIN_DATO"
    edad_act = int(il["Edad"])
    nombre_g = snap_last.get("NombreGranja", il.get("GranjaID", "—"))
    galpon_v = snap_last.get("Galpon", "—")
    
    # ── Extraer métricas ──────────────────────────────────────
    info = extraer_metricas_lote(hist_cmp)
    info["edad_act"] = edad_act
    
    # ── Renderizar tarjetas ───────────────────────────────────
    render_tarjetas_lote(
        info,
        nombre_g,
        extract_lote_codigo(lote_sel),
        galpon_v,
        zona_v,
        tipo_v,
        repro_v,
        quint_v
    )
    
    # ── Gráfico de crecimiento ────────────────────────────────
    hist_v = hist_cmp[hist_cmp["PesoFinal"].notna() & (hist_cmp["PesoFinal"] > 0)].copy()
    edad_max_lote = pd.to_numeric(hist_v["Edad"], errors="coerce").max()
    
    render_grafico_crecimiento(
        hist_v,
        info,
        zona_v,
        tipo_v,
        repro_v,
        quint_v,
        nombre_g,
        galpon_v,
        lote_sel,
        EDAD_MIN_ANALISIS
    )
    
    # ── Gráfico de costo ──────────────────────────────────────
    if pd.notna(edad_max_lote) and edad_max_lote <= EDAD_MIN_ANALISIS:
        hist_c = hist_cmp.copy()
    else:
        hist_c = hist_cmp[hist_cmp["Edad"] >= EDAD_MIN_ANALISIS].copy()
    
    render_grafico_costo(hist_c, info, lote_sel, EDAD_MIN_ANALISIS, edad_max_lote)