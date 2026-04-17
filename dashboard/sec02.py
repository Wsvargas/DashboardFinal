import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from config import BLACK, CARD, BORDER, MUTED
from core.helpers      import md, fmt_num, extract_lote_codigo
from core.data_loader  import calcular_fcr_gaps_galpones
from .kpis             import fmt_manager

CHART_TEXT = BLACK


def render_sec02(SF_02, DF_HIST_COMP, IDEALES):
    """
    Sección 02: Top 10 Granjas con mayor sobrecosto vs ideal
    Retorna el lote seleccionado en la tabla
    """
    
    md(f"""
<div class="sec-header">
  <span class="sec-num">02</span>
  <div>
    <div class="sec-title">Top 10 Granjas · Sobrecosto vs Ideal</div>
    <div class="sec-sub">🖱️ Clic en barra → ver lote/galpón con mayor impacto en dólares</div>
  </div>
</div>""")
    
    if SF_02.empty:
        st.info("Sin lotes para los filtros actuales.")
        return None
    
    gaps_galpon_df = calcular_fcr_gaps_galpones(SF_02, IDEALES)
    
    if gaps_galpon_df.empty:
        st.info("No hay galpones para analizar con los filtros actuales.")
        return None
    
    # ── Normalizar columnas de granja ─────────────────────────
    gaps_galpon_df = gaps_galpon_df.copy()
    if "Granja" not in gaps_galpon_df.columns:
        gaps_galpon_df["Granja"] = gaps_galpon_df.get("NombreGranja", "—")
    if "NombreGranja" not in gaps_galpon_df.columns:
        gaps_galpon_df["NombreGranja"] = gaps_galpon_df["Granja"]
    if "Galpon" not in gaps_galpon_df.columns:
        gaps_galpon_df["Galpon"] = np.nan
    
    # ── Convertir a numéricos ─────────────────────────────────
    num_cols = [
        "Edad", "AvesVivas", "KgLive", "PesoIdeal", "KgLiveIdeal",
        "PrecioKgReal", "AlimIdealAcum", "FCR_real", "FCR_ideal",
        "Gap_FCR", "CostoReal", "CostoIdeal", "GapCosto", "GapCostoKg", "Galpon"
    ]
    for c in num_cols:
        if c in gaps_galpon_df.columns:
            gaps_galpon_df[c] = pd.to_numeric(gaps_galpon_df[c], errors="coerce")
    
    # ── Validar que hay datos de ideal ────────────────────────
    if gaps_galpon_df["CostoIdeal"].notna().sum() == 0:
        sf_warn = SF_02.copy()

        if "ReproductoraStd" not in sf_warn.columns:
            sf_warn["ReproductoraStd"] = "SIN_DATO"

        combos = (
            sf_warn.groupby(["ZonaNombre", "TipoStd", "ReproductoraStd", "Quintil"])
            .size()
            .reset_index()
        )

        combos_str = " | ".join([
            f"{r['ZonaNombre']}·{r['TipoStd']}·{r['ReproductoraStd']}·{r['Quintil']}"
            for _, r in combos.iterrows()
        ])

        st.warning(
            f"No se pudo calcular el ideal comparable para los galpones filtrados.\n\n"
            f"**Combinaciones buscadas:** {combos_str}"
        )
        return None
    
    # ── Filtrar solo galpones con sobrecosto ──────────────────
    con_prob = gaps_galpon_df[gaps_galpon_df["GapCosto"] > 0].copy()

    if con_prob.empty:
        # Hay lotes pero todos están por debajo del ideal → buen desempeño
        n_lotes = gaps_galpon_df["LoteCompleto"].nunique()
        st.success(
            f"✅ {n_lotes} lote(s) en los filtros actuales — todos con costo real **por debajo** del ideal comparable. Sin sobrecosto."
        )
        # Mostrar igual la tabla para verificación
        tabla_todos = gaps_galpon_df.copy()
        tabla_todos["Código"] = tabla_todos["LoteCompleto"].apply(extract_lote_codigo)
        tabla_todos["GapCostoFmt"] = tabla_todos["GapCosto"].apply(
            lambda x: fmt_manager(x, prefix="$") if pd.notna(x) else "—"
        )
        tabla_todos["CostoRealFmt"] = tabla_todos["CostoReal"].apply(
            lambda x: fmt_manager(x, prefix="$") if pd.notna(x) else "—"
        )
        tabla_todos["CostoIdealFmt"] = tabla_todos["CostoIdeal"].apply(
            lambda x: fmt_manager(x, prefix="$") if pd.notna(x) else "—"
        )
        tabla_todos = tabla_todos.sort_values("GapCosto", ascending=True).reset_index(drop=True)
        sel_t2 = st.dataframe(
            tabla_todos[["Código", "Galpon", "Edad", "GapCostoFmt", "CostoRealFmt", "CostoIdealFmt", "FCR_real", "FCR_ideal", "Gap_FCR"]],
            on_select="rerun",
            selection_mode="single-row",
            key="df_lotes_sec02_ok",
            hide_index=True,
            width="stretch",
            height=min(320, 35 * (len(tabla_todos) + 1)),
            column_config={
                "Código":        st.column_config.TextColumn("🔖 Lote"),
                "Galpon":        st.column_config.NumberColumn("Galpón", format="%d", width="small"),
                "Edad":          st.column_config.NumberColumn("Días", format="%d d", width="small"),
                "GapCostoFmt":   st.column_config.TextColumn("Real vs Ideal"),
                "CostoRealFmt":  st.column_config.TextColumn("Costo real"),
                "CostoIdealFmt": st.column_config.TextColumn("Costo ideal"),
                "FCR_real":      st.column_config.NumberColumn("Con Real", format="%.4f", width="small"),
                "FCR_ideal":     st.column_config.NumberColumn("Con Ideal", format="%.4f", width="small"),
                "Gap_FCR":       st.column_config.NumberColumn("Gap Con", format="+%.4f", width="small"),
            },
        )
        rows_sel2 = sel_t2.selection.get("rows", []) if sel_t2 and sel_t2.selection else []
        if rows_sel2:
            return tabla_todos.iloc[int(rows_sel2[0])]["LoteCompleto"]
        return None
    
    # ── Agregar por granja ────────────────────────────────────
    md('<div class="hint-text">Sobrecosto acumulado por granja respecto al ideal comparable (Top 10 peores)</div>')
    df_granjas = (
        con_prob.groupby(["Granja", "NombreGranja"], as_index=False)
        .agg(
            NumGalpones     = ("Galpon", "nunique"),
            CostoRealTotal  = ("CostoReal", "sum"),
            CostoIdealTotal = ("CostoIdeal", "sum"),
            GapCostoTotal   = ("GapCosto", "sum"),
            FCR_real        = ("FCR_real", "mean"),
            FCR_ideal       = ("FCR_ideal", "mean"),
            Gap_FCR_medio   = ("Gap_FCR", "mean"),
        )
    )
    
    if df_granjas.empty:
        st.info("No se pudo consolidar el sobrecosto por granja.")
        return None
    
    # ── Top 10 con peor sobrecosto ────────────────────────────
    df_plot = df_granjas.sort_values(
        ["GapCostoTotal", "Gap_FCR_medio"],
        ascending=[False, False]
    ).head(10).copy()
    
    df_plot["NombreMostrar"] = df_plot["NombreGranja"].fillna(df_plot["Granja"])
    
    # ── Clasificación por semáforo ────────────────────────────
    q_bajo = df_plot["GapCostoTotal"].quantile(0.33)
    q_medio = df_plot["GapCostoTotal"].quantile(0.66)
    
    def clasificar_semaforo(v):
        if pd.isna(v):
            return "BAJO"
        elif v >= q_medio:
            return "CRITICO"
        elif v >= q_bajo:
            return "MEDIO"
        return "BAJO"
    
    df_plot["Semaforo"] = df_plot["GapCostoTotal"].apply(clasificar_semaforo)
    
    color_map = {
        "CRITICO": "#dc2626",
        "MEDIO":   "#f59e0b",
        "BAJO":    "#16a34a",
    }
    df_plot["ColorBarra"] = df_plot["Semaforo"].map(color_map)
    
    # ── Gráfico de barras ─────────────────────────────────────
    fig_g = go.Figure()
    fig_g.add_trace(go.Bar(
        x=df_plot["NombreMostrar"],
        y=df_plot["GapCostoTotal"],
        marker=dict(
            color=df_plot["ColorBarra"],
            line=dict(color="rgba(0,0,0,0.15)", width=0.8)
        ),
        customdata=df_plot[[
            "Granja", "NombreMostrar", "CostoRealTotal", "CostoIdealTotal",
            "GapCostoTotal", "NumGalpones", "Gap_FCR_medio", "Semaforo"
        ]].values,
        hovertemplate=(
            "<b>%{customdata[1]}</b><br>"
            "Código granja: %{customdata[0]}<br>"
            "Sobrecosto acumulado: <b>$%{customdata[4]:,.0f}</b><br>"
            "Costo real total: $%{customdata[2]:,.0f}<br>"
            "Costo ideal comparable: $%{customdata[3]:,.0f}<br>"
            "Galpones afectados: %{customdata[5]}<br>"
            "Gap FCR medio: %{customdata[6]:.4f}<br>"
            "Severidad: <b>%{customdata[7]}</b>"
            "<extra></extra>"
        ),
    ))
    
    fig_g.update_layout(
        template="plotly_white",
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        height=390,
        margin=dict(l=8, r=8, t=18, b=90),
        font=dict(family="DM Sans", size=9, color=CHART_TEXT),
        showlegend=False,
        xaxis=dict(
            title="Granja",
            tickangle=-35,
            gridcolor=BORDER,
            color=CHART_TEXT,
            tickfont=dict(color=CHART_TEXT),
            title_font=dict(color=CHART_TEXT)
        ),
        yaxis=dict(
            title="Sobrecosto acumulado vs ideal ($)",
            gridcolor=BORDER,
            color=CHART_TEXT,
            tickfont=dict(color=CHART_TEXT),
            title_font=dict(color=CHART_TEXT)
        ),
    )
    
    sel_g = st.plotly_chart(
        fig_g,
        on_select="rerun",
        selection_mode="points",
        key="chart_granjas",
        config={"displayModeBar": False},
        width="stretch",
    )
    
    # ── Detectar granja seleccionada ──────────────────────────
    puntos_sel = sel_g.selection.get("points", []) if sel_g and sel_g.selection else []
    granja_activa_codigo = (
        puntos_sel[0]["customdata"][0]
        if puntos_sel
        else df_plot["Granja"].iloc[0]
    )
    
    fila_act = df_plot[df_plot["Granja"] == granja_activa_codigo]
    granja_activa_nombre = (
        fila_act["NombreMostrar"].iloc[0]
        if not fila_act.empty
        else granja_activa_codigo
    )
    
    if puntos_sel:
        md(f'<div class="sel-pill">🏭 {granja_activa_codigo} · <strong>{granja_activa_nombre}</strong></div>')
    else:
        md(f'<div class="hint-text">Clic en barra para seleccionar granja · Activa: <strong>{granja_activa_nombre}</strong></div>')
    
    # ── Tabla de galpones de la granja seleccionada ──────────
    galpones_granja = (
        con_prob[con_prob["Granja"] == granja_activa_codigo]
        .copy()
        .sort_values(["GapCosto", "Gap_FCR"], ascending=[False, False])
    )
    
    if galpones_granja.empty:
        st.info(f"Sin datos de galpones para {granja_activa_nombre}.")
        return None
    
    tabla_galp = galpones_granja[[
        "LoteCompleto", "Galpon", "Edad",
        "GapCosto", "FCR_real", "FCR_ideal", "Gap_FCR",
        "CostoReal", "CostoIdeal", "AlimIdealAcum", "PrecioKgReal"
    ]].copy()
    
    tabla_galp["Código"] = tabla_galp["LoteCompleto"].apply(extract_lote_codigo)
    tabla_galp["Galpon"] = pd.to_numeric(tabla_galp["Galpon"], errors="coerce")
    tabla_galp["SobrecostoFmt"] = tabla_galp["GapCosto"].apply(
        lambda x: fmt_manager(x, prefix="$") if pd.notna(x) else "—"
    )
    tabla_galp["CostoRealFmt"] = tabla_galp["CostoReal"].apply(
        lambda x: fmt_manager(x, prefix="$") if pd.notna(x) else "—"
    )
    tabla_galp["CostoIdealFmt"] = tabla_galp["CostoIdeal"].apply(
        lambda x: fmt_manager(x, prefix="$") if pd.notna(x) else "—"
    )
    
    tabla_galp = tabla_galp.sort_values(
        ["GapCosto", "Gap_FCR", "Edad"],
        ascending=[False, False, False]
    ).reset_index(drop=True)
    
    md(f'<div class="hint-text">{len(tabla_galp)} galpón(es) en problema en <strong>{granja_activa_nombre}</strong> · mayor sobrecosto primero</div>')
    
    tabla_galp_show = tabla_galp[[
        "Código", "Galpon", "Edad", "SobrecostoFmt",
        "CostoRealFmt", "CostoIdealFmt", "FCR_real", "FCR_ideal", "Gap_FCR"
    ]].copy()
    
    sel_t = st.dataframe(
        tabla_galp_show,
        on_select="rerun",
        selection_mode="single-row",
        key="df_lotes_sec02",
        hide_index=True,
        width="stretch",
        height=min(320, 35 * (len(tabla_galp_show) + 1)),
        column_config={
            "Código":         st.column_config.TextColumn("🔖 Lote"),
            "Galpon":         st.column_config.NumberColumn("Galpón", format="%d", width="small"),
            "Edad":           st.column_config.NumberColumn("Días", format="%d d", width="small"),
            "SobrecostoFmt":  st.column_config.TextColumn("Real vs Ideal"),
            "CostoRealFmt":   st.column_config.TextColumn("Costo real"),
            "CostoIdealFmt":  st.column_config.TextColumn("Costo ideal"),
            "FCR_real":       st.column_config.NumberColumn("Con Real", format="%.4f", width="small"),
            "FCR_ideal":      st.column_config.NumberColumn("Con Ideal", format="%.4f", width="small"),
            "Gap_FCR":        st.column_config.NumberColumn("Gap Con ↑", format="+%.4f", width="small"),
        },
    )
    
    # ── Retornar lote seleccionado ────────────────────────────
    rows_sel = sel_t.selection.get("rows", [])
    idx = rows_sel[0] if rows_sel else None
    
    if idx is not None and 0 <= int(idx) < len(tabla_galp):
        nuevo_lote = tabla_galp.iloc[int(idx)]["LoteCompleto"]
        return nuevo_lote
    elif idx is not None:
        st.info("La lista cambió por los filtros. Selecciona un galpón nuevamente 👇")
    
    return None