import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

# ── Módulos propios ───────────────────────────────────────────
from config import (
    MAIN_FILE, BENCH_FILE, EDAD_MIN_ANALISIS,
    RED, BLACK, BG, CARD, BORDER, TEXT, MUTED, GREEN, AMBER, BLUE,
    ETAPA_ORDER, ETAPA_COLORS,
)

from helpers import (
    md, _file_mtime, get_etapa, fmt_num,
    extract_lote_codigo, _console_df_info,
    _limpiar_historial_para_modelo,
)

from styles import inject_css

from data_loader import (
    load_and_prepare, load_ideales,
    build_snapshot_activos, enriquecer_historial_con_ideal,
    calcular_gaps_lotes, calcular_fcr_gaps_galpones,
    calcular_fcr_gaps_granjas, get_curva_ideal_promedio,
)

CHART_TEXT = BLACK


def fmt_manager(n, prefix="", suffix=""):
    if pd.isna(n):
        return "—"

    x = float(n)
    sign = "-" if x < 0 else ""
    x = abs(x)

    if x >= 1_000_000:
        txt = f"{x / 1_000_000:.1f} M"
    elif x >= 1_000:
        txt = f"{x / 1_000:.1f} mil"
    else:
        txt = f"{x:,.0f}"

    txt = txt.replace(".0 M", " M").replace(".0 mil", " mil")
    return f"{sign}{prefix}{txt}{suffix}"


# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="\n PRONACA | Producción Avícola v15",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ──────────────────────────────────────────────────────────────
# ROUTER simple (dashboard / predictiva)
# ──────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state["page"] = "dashboard"


def go_predictiva():
    st.session_state["page"] = "predictiva"
    st.rerun()


def go_dashboard():
    st.session_state["page"] = "dashboard"
    st.rerun()


if st.session_state["page"] == "predictiva":
    import tool_predictiva
    tool_predictiva.render(go_dashboard=go_dashboard)
    st.stop()

# ──────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────
inject_css()

# ──────────────────────────────────────────────────────────────
# PREDICTOR (cacheado por mtime del modelo)
# ──────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_predictor_cached(model_path: str, model_mtime: float):
    from model_predictor import cargar_predictor
    return cargar_predictor(model_path)

# ──────────────────────────────────────────────────────────────
# CARGA DE DATOS
# ──────────────────────────────────────────────────────────────
if not os.path.exists(MAIN_FILE):
    st.error(f"❌ No se encontró {MAIN_FILE}")
    st.stop()

with st.spinner("Cargando datos…"):
    DF_ALL = load_and_prepare(MAIN_FILE)
    IDEALES = load_ideales(BENCH_FILE)

with st.spinner("Procesando histórico comparable…"):
    DF_HIST_COMP = enriquecer_historial_con_ideal(DF_ALL, IDEALES)

with st.spinner("Procesando snapshot…"):
    SNAP = build_snapshot_activos(DF_HIST_COMP)

if SNAP.empty:
    st.warning("No hay lotes ACTIVO en el archivo.")
    st.stop()

# ── Session state ─────────────────────────────────────────────
if "lote_anterior" not in st.session_state:
    st.session_state.lote_anterior = None
if "prediccion_resultado" not in st.session_state:
    st.session_state.prediccion_resultado = None

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────
hoy = datetime.today()
md(f"""
<div class="pronaca-header">
  <div>
    <div class="pronaca-header-title">----</div>
    <div class="pronaca-header-title">PRONACA · PRODUCCIÓN AVÍCOLA v15</div>
    <div class="pronaca-header-sub">Dashboard Interactivo · Con Botón de Predicción Manual</div>
  </div>
  <div class="pronaca-header-pill">📅 Corte {hoy:%d %b %Y}</div>
</div>
""")

# ──────────────────────────────────────────────────────────────
# FILTROS SUPERIORES
# ──────────────────────────────────────────────────────────────
md('<div class="filter-bar">')
fc1, fc2, fc3, fc4, fc5 = st.columns([1.3, 1.2, 1.2, 1.2, 1.35])
with fc1:
    sel_zona = st.multiselect("📍 Zona", ["BUCAY", "SANTO DOMINGO"], default=["BUCAY", "SANTO DOMINGO"])
with fc2:
    sel_tipo = st.multiselect("🏠 Tipo", ["PROPIA", "PAC"], default=["PROPIA", "PAC"])
with fc3:
    sel_quint = st.multiselect("🧩 Quintil", ["Q1", "Q2", "Q3", "Q4", "Q5"], default=["Q2", "Q3", "Q4", "Q5"])
with fc4:
    sel_estado = st.multiselect("🔄 Estado", ["ABIERTO", "CERRADO"], default=["ABIERTO"])


# ── Snapshot filtrado por filtros globales ───────────────────
SF = SNAP.copy()
SF = SF[SF["ZonaNombre"].isin(sel_zona)]
SF = SF[SF["TipoStd"].isin(sel_tipo)]
SF = SF[SF["Quintil"].isin(sel_quint)]
SF = SF[SF["EstadoLote"].isin(sel_estado)]

if SF.empty:
    st.info("Sin datos para los filtros seleccionados.")
    st.stop()

LOTES_FILTRADOS = SF["LoteCompleto"].dropna().unique().tolist()
DF_FILTRADO = DF_HIST_COMP[DF_HIST_COMP["LoteCompleto"].isin(LOTES_FILTRADOS)].copy()

# ──────────────────────────────────────────────────────────────
# KPIs GLOBALES
# ──────────────────────────────────────────────────────────────
kg_total = pd.to_numeric(SF["KgLive"], errors="coerce").sum()
costo_total = pd.to_numeric(SF["CostoAcum"], errors="coerce").sum()
cpkg = costo_total / (kg_total if pd.notna(kg_total) and kg_total > 0 else np.nan)

if "Granja" in SF.columns:
    granjas_total = SF["Granja"].nunique()
elif "GranjaID" in SF.columns:
    granjas_total = SF["GranjaID"].nunique()
else:
    granjas_total = SF["NombreGranja"].nunique()

k1, k2, k3, k4, k5, k6 = st.columns(6)
for col_, val_, lbl_, acc in [
    (k1, f"{SF['LoteCompleto'].nunique():,}", "Lotes activos", True),
    (k2, f"{granjas_total:,}", "Granjas totales", True),
    (k3, fmt_manager(pd.to_numeric(SF["AvesVivas"], errors="coerce").sum()), "Aves vivas", True),
    (k4, fmt_manager(kg_total, suffix=" kg"), "Kg live", True),
    (k5, fmt_manager(costo_total, prefix="$"), "Costo total", True),
    (k6, fmt_num(cpkg, 3, prefix="$", suffix="/kg"), "Costo medio/kg", False),
]:
    with col_:
        md(f'<div class="kpi-chip {"accent" if acc else ""}"><div class="kv">{val_}</div><div class="kl">{lbl_}</div></div>')

# ──────────────────────────────────────────────────────────────
# LAYOUT PRINCIPAL
# ──────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ══════════════════════════════════════════════════════════════
# COLUMNA IZQUIERDA
# ══════════════════════════════════════════════════════════════
with left:

    # ── SEC 01 · Resumen por Etapa ────────────────────────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">01</span>
  <div>
    <div class="sec-title">Resumen por Etapa</div>
    <div class="sec-sub">🖱️ Haz clic en una barra para filtrar granjas abajo</div>
  </div>
</div>""")

    rows_etapa = []
    for etapa in ETAPA_ORDER:
        g = SF[SF["Etapa"] == etapa]
        if g.empty:
            continue

        n = g["LoteCompleto"].nunique()
        av = pd.to_numeric(g["AvesVivas"], errors="coerce").sum()
        kg = pd.to_numeric(g["KgLive"], errors="coerce").sum()
        co = pd.to_numeric(g["CostoAcum"], errors="coerce").sum()
        mo = pd.to_numeric(g["MortPct"], errors="coerce").mean()
        al = pd.to_numeric(g["AlimAcumKg"], errors="coerce").sum()
        fcr = al / kg if pd.notna(kg) and kg > 0 else np.nan
        ck = co / kg if pd.notna(kg) and kg > 0 else np.nan

        bdg = "green"
        if pd.notna(ck) and ck >= 0.9:
            bdg = "red"
        elif pd.notna(ck) and ck >= 0.75:
            bdg = "amber"

        etapa_txt = str(etapa)
        rango_txt = etapa_txt
        if "(" in etapa_txt and ")" in etapa_txt:
            rango_txt = etapa_txt.split("(")[-1].split(")")[0].strip()

        rows_etapa.append({
            "etapa_full": etapa,
            "rango": rango_txt,
            "n": n,
            "av": av,
            "kg": kg,
            "co": co,
            "fcr": fcr,
            "ck": ck,
            "mo": mo,
            "bdg": bdg,
            "dot": ETAPA_COLORS.get(etapa, BLUE),
        })

    cg, ct = st.columns([0.4, 0.6], gap="small")

    with cg:
        df_etapas_plot = pd.DataFrame(rows_etapa).copy()

        fig_e = go.Figure()
        fig_e.add_trace(go.Bar(
            y=df_etapas_plot["rango"],
            x=df_etapas_plot["n"],
            orientation="h",
            marker=dict(color=df_etapas_plot["dot"]),
            text=df_etapas_plot["n"],
            textposition="auto",
            textfont=dict(color=CHART_TEXT, size=10),
            customdata=df_etapas_plot[["etapa_full", "co", "kg", "ck", "fcr", "mo"]].values,
            hovertemplate=(
                "<b>Rango %{y} días</b><br>"
                "Lotes: %{x}<br>"
                "Costo: %{customdata[1]:,.0f}<br>"
                "Kg live: %{customdata[2]:,.0f}<br>"
                "Cost_Al_Conv: %{customdata[3]:.3f}<br>"
                "Con_A: %{customdata[4]:.3f}<br>"
                "Mortalidad: %{customdata[5]:.2f}%"
                "<extra></extra>"
            ),
        ))

        fig_e.update_layout(
            template="plotly_white",
            paper_bgcolor=CARD,
            plot_bgcolor=CARD,
            height=240,
            margin=dict(l=8, r=8, t=10, b=8),
            font=dict(family="DM Sans", size=8, color=CHART_TEXT),
            showlegend=False,
            xaxis=dict(
                title="Lotes",
                gridcolor=BORDER,
                color=CHART_TEXT,
                tickfont=dict(color=CHART_TEXT, size=8),
                title_font=dict(color=CHART_TEXT, size=8),
            ),
            yaxis=dict(
                title="",
                gridcolor=BORDER,
                color=CHART_TEXT,
                tickfont=dict(color=CHART_TEXT, size=8),
                title_font=dict(color=CHART_TEXT, size=8),
                autorange="reversed",
            ),
            bargap=0.22,
        )

        sel_e = st.plotly_chart(
            fig_e,
            on_select="rerun",
            selection_mode="points",
            key="chart_etapas",
            config={"displayModeBar": False},
            width="stretch",
        )

        etapas_sel = []
        if sel_e and sel_e.selection:
            for p in sel_e.selection.get("points", []):
                idx = p.get("point_index")
                if idx is not None and 0 <= idx < len(df_etapas_plot):
                    etapas_sel.append(df_etapas_plot.iloc[idx]["etapa_full"])

        if etapas_sel:
            rangos_sel = [
                df_etapas_plot.loc[df_etapas_plot["etapa_full"] == e, "rango"].iloc[0]
                for e in etapas_sel
                if not df_etapas_plot.loc[df_etapas_plot["etapa_full"] == e, "rango"].empty
            ]
            md(f'<div class="sel-pill">🔍 Filtrando: {" + ".join(rangos_sel)}</div>')
        else:
            md('<div class="hint-text">Clic en barra para filtrar ↓</div>')

    with ct:
        tbody = ""
        for r in rows_etapa:
            act = r["etapa_full"] in etapas_sel if etapas_sel else False

            tbody += f"""
<tr style="border-bottom:1px solid {BORDER};background:{'rgba(218,41,28,.05)' if act else 'transparent'}">
<td style="padding:4px 6px;font-weight:{'900' if act else '700'};font-size:.68rem;text-align:left">
    <span style="display:inline-block;width:7px;height:7px;border-radius:2px;
                background:{r['dot']};margin-right:4px;vertical-align:middle"></span>
    {r['rango']}
</td>
<td style="text-align:right;padding:4px 6px;font-size:.68rem">{fmt_manager(r['co'], prefix="$")}</td>
<td style="text-align:right;padding:4px 6px;font-size:.68rem">{fmt_manager(r['av'])}</td>
<td style="text-align:right;padding:4px 6px;font-size:.68rem">{fmt_manager(r['kg'], suffix=" kg")}</td>
<td style="text-align:right;padding:4px 6px;font-size:.68rem">
    <span class="badge {r['bdg']}">{fmt_num(r['ck'],3,prefix="$")}</span>
</td>
<td style="text-align:right;padding:4px 6px;font-size:.68rem">{fmt_num(r['fcr'],3)}</td>
<td style="text-align:right;padding:4px 6px;font-size:.68rem">{fmt_num(r['mo'],2,suffix="%")}</td>
</tr>"""

        md(f"""
<div class="card" style="padding:0;overflow:auto;height:240px">
<table style="width:100%;border-collapse:collapse">
<thead style="position:sticky;top:0;background:#F8FAFC;z-index:1">
<tr style="border-bottom:1px solid {BORDER}">
<th style="text-align:left;padding:4px 6px;color:{MUTED};font-size:.58rem;text-transform:uppercase;letter-spacing:.2px">Edad</th>
<th style="text-align:right;padding:4px 6px;color:{MUTED};font-size:.58rem;text-transform:uppercase">$Ali</th>
<th style="text-align:right;padding:4px 6px;color:{MUTED};font-size:.58rem;text-transform:uppercase">Aves</th>
<th style="text-align:right;padding:4px 6px;color:{MUTED};font-size:.58rem;text-transform:uppercase">Kg</th>
<th style="text-align:right;padding:4px 6px;color:{MUTED};font-size:.58rem;text-transform:uppercase">$UKg</th>
<th style="text-align:right;padding:4px 6px;color:{MUTED};font-size:.58rem;text-transform:uppercase">Conv</th>
<th style="text-align:right;padding:4px 6px;color:{MUTED};font-size:.58rem;text-transform:uppercase">M%</th>
</tr>
</thead>
<tbody>{tbody}</tbody>
</table></div>""")

    # ── SEC 02 · Top 10 Granjas con mayor sobrecosto vs ideal ────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">02</span>
  <div>
    <div class="sec-title">Top 10 Granjas · Sobrecosto vs Ideal</div>
    <div class="sec-sub">🖱️ Clic en barra → ver lote/galpón con mayor impacto en dólares</div>
  </div>
</div>""")

    SF_02 = SF.copy()
    if etapas_sel:
        SF_02 = SF_02[SF_02["Etapa"].isin(etapas_sel)]

    if SF_02.empty:
        st.info("Sin lotes para los filtros actuales.")
    else:
        gaps_galpon_df = calcular_fcr_gaps_galpones(SF_02, IDEALES)

        if gaps_galpon_df.empty:
            st.info("No hay galpones para analizar con los filtros actuales.")
        else:
            gaps_galpon_df = gaps_galpon_df.copy()

            if "Granja" not in gaps_galpon_df.columns:
                gaps_galpon_df["Granja"] = gaps_galpon_df.get("NombreGranja", "—")

            if "NombreGranja" not in gaps_galpon_df.columns:
                gaps_galpon_df["NombreGranja"] = gaps_galpon_df["Granja"]

            if "Galpon" not in gaps_galpon_df.columns:
                gaps_galpon_df["Galpon"] = np.nan

            num_cols = [
                "Edad", "AvesVivas", "KgLive", "PesoIdeal", "KgLiveIdeal",
                "PrecioKgReal", "AlimIdealAcum", "FCR_real", "FCR_ideal",
                "Gap_FCR", "CostoReal", "CostoIdeal", "GapCosto", "GapCostoKg", "Galpon"
            ]
            for c in num_cols:
                if c in gaps_galpon_df.columns:
                    gaps_galpon_df[c] = pd.to_numeric(gaps_galpon_df[c], errors="coerce")

            if gaps_galpon_df["CostoIdeal"].notna().sum() == 0:
                combos = SF_02.groupby(["ZonaNombre", "TipoStd", "Quintil"]).size().reset_index()
                combos_str = " | ".join([
                    f"{r['ZonaNombre']}·{r['TipoStd']}·{r['Quintil']}"
                    for _, r in combos.iterrows()
                ])
                st.warning(
                    f"No se pudo calcular el ideal comparable para los galpones filtrados.\n\n"
                    f"**Combinaciones buscadas:** {combos_str}\n\n"
                    f"Verifica que `{BENCH_FILE}` tenga curvas para estas combinaciones."
                )
            else:
                con_prob = gaps_galpon_df[gaps_galpon_df["GapCosto"] > 0].copy()

                if con_prob.empty:
                    st.info("Ninguna granja presenta sobrecosto positivo vs ideal con los filtros actuales.")
                else:
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
                    else:
                        df_plot = df_granjas.sort_values(
                            ["GapCostoTotal", "Gap_FCR_medio"],
                            ascending=[False, False]
                        ).head(10).copy()

                        df_plot["NombreMostrar"] = df_plot["NombreGranja"].fillna(df_plot["Granja"])

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

                        galpones_granja = (
                            con_prob[con_prob["Granja"] == granja_activa_codigo]
                            .copy()
                            .sort_values(["GapCosto", "Gap_FCR"], ascending=[False, False])
                        )

                        if galpones_granja.empty:
                            st.info(f"Sin datos de galpones para {granja_activa_nombre}.")
                        else:
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

                            rows_sel = sel_t.selection.get("rows", [])
                            idx = rows_sel[0] if rows_sel else None

                            if idx is not None and 0 <= int(idx) < len(tabla_galp):
                                nuevo_lote = tabla_galp.iloc[int(idx)]["LoteCompleto"]
                                if st.session_state.get("lote_sel_sec03") != nuevo_lote:
                                    st.session_state["lote_sel_sec03"] = nuevo_lote
                                    st.rerun()
                            elif idx is not None:
                                st.info("La lista cambió por los filtros. Selecciona un galpón nuevamente 👇")

    # ── SEC 03 · Lote Seleccionado: IDEAL vs REAL ─────────────
    # ── SEC 03 · Lote Seleccionado: IDEAL vs REAL ─────────────
    md(f"""
<div class="sec-header">
<span class="sec-num">03</span>
<div>
    <div class="sec-title">Lote Seleccionado: Crecimiento IDEAL vs REAL</div>
    <div class="sec-sub">Análisis detallado · selecciona un galpón en la tabla de arriba</div>
</div>
</div>""")

    # ── Helpers visuales sec 03 ───────────────────────────────
    def fmt_signed_short(n, prefix="", suffix=""):
        if pd.isna(n):
            return "—"
        x = float(n)
        base = fmt_manager(abs(x), prefix=prefix, suffix=suffix)
        if x > 0:
            return f"+{base}"
        elif x < 0:
            return f"-{base}"
        return base

    def render_kpi_small(value_html, label, accent=False):
        cls = "kpi-chip accent" if accent else "kpi-chip"
        md(f'''
<div class="{cls}" style="
    padding:10px 10px;
    min-height:74px;
    display:flex;
    flex-direction:column;
    justify-content:center;
">
    <div class="kv" style="
        font-size:1rem;
        line-height:1.05;
        white-space:normal;
        word-break:break-word;
        overflow-wrap:anywhere;
    ">{value_html}</div>
    <div class="kl" style="
        font-size:.66rem;
        line-height:1.1;
        margin-top:4px;
    ">{label}</div>
</div>''')

    lotes_disp = SF["LoteCompleto"].dropna().unique().tolist()
    if (
        "lote_sel_sec03" not in st.session_state
        or st.session_state["lote_sel_sec03"] not in lotes_disp
    ):
        st.session_state["lote_sel_sec03"] = lotes_disp[0] if lotes_disp else None

    lote_sel = st.session_state.get("lote_sel_sec03")
    if not lote_sel:
        st.info("Selecciona un galpón en la tabla de arriba.")
        st.stop()

    il = SF[SF["LoteCompleto"] == lote_sel].iloc[0]
    hist = DF_FILTRADO[DF_FILTRADO["LoteCompleto"] == lote_sel].sort_values("Edad").copy()

    if hist.empty:
        st.warning("No hay historial para este lote.")
        st.stop()

    hist_cmp = hist.copy().reset_index(drop=True)
    hist_ord = hist_cmp.sort_values("Edad").copy()
    snap_last = hist_ord.iloc[-1]

    zona_v = il["ZonaNombre"]
    tipo_v = il["TipoStd"]
    quint_v = il["Quintil"]
    edad_act = int(il["Edad"])
    nombre_g = snap_last.get("NombreGranja", il.get("GranjaID", "—"))
    galpon_v = snap_last.get("Galpon", "—")

    # ── Normalización de columnas del histórico enriquecido ──
    for c in [
        "Edad", "PesoFinal", "AvesVivas", "MortPct", "CostoAcum", "CostoKg_Cum",
        "AlimAcumKg", "_alim_dia", "CostoAlimentoDia", "KgLive",
        "PrecioKg", "PrecioKgRealDia", "FCR_Cum",
        "FCR_ideal", "PesoIdeal_comp", "KgLiveIdeal_comp",
        "AlimIdealAcum_comp", "AlimIdealDia_comp",
        "CostoIdealDia_comp", "CostoIdealComp", "GapCostoComp"
    ]:
        if c in hist_cmp.columns:
            hist_cmp[c] = pd.to_numeric(hist_cmp[c], errors="coerce")

    fcr_col_hist = "FCR_Cum"

    # Alias amigables
    hist_cmp["PesoIdeal"] = hist_cmp.get("PesoIdeal_comp", np.nan)
    hist_cmp["KgLiveIdeal_calc"] = hist_cmp.get("KgLiveIdeal_comp", np.nan)
    hist_cmp["AlimIdealAcum_calc"] = hist_cmp.get("AlimIdealAcum_comp", np.nan)
    hist_cmp["AlimIdealDia_calc"] = hist_cmp.get("AlimIdealDia_comp", np.nan)
    hist_cmp["CostoIdealDia_calc"] = hist_cmp.get("CostoIdealDia_comp", np.nan)
    hist_cmp["CostoIdealAcum_calc"] = hist_cmp.get("CostoIdealComp", np.nan)
    hist_cmp["DifCosto_calc"] = hist_cmp.get("GapCostoComp", np.nan)

    tiene_ideal = hist_cmp["CostoIdealAcum_calc"].notna().any()

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

    edad_max_lote = pd.to_numeric(hist_cmp["Edad"], errors="coerce").max()
    dtick_x = 1 if pd.notna(edad_max_lote) and edad_max_lote <= 10 else 7

    # ── TARJETAS DE IDENTIDAD ─────────────────────────────────
    md(f'''<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;">
<div class="sel-pill-neutral">🏭 <strong>{nombre_g}</strong></div>
<div class="sel-pill-neutral">🔖 {extract_lote_codigo(lote_sel)}</div>
<div class="sel-pill-neutral">🏠 Galpón <strong>{galpon_v}</strong></div>
<div class="sel-pill-neutral">📍 {zona_v} · {tipo_v} · {quint_v}</div>
</div>''')

    # ── TARJETAS GERENCIALES ──────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        render_kpi_small(f"{edad_act} d", "Edad actual")

    with c2:
        render_kpi_small(fmt_manager(kg_live_lote, suffix=" kg"), "Kg vivo real")

    with c3:
        render_kpi_small(fmt_num(precio_kg_real, 3, prefix="$", suffix="/kg"), "$ kg real")

    with c4:
        render_kpi_small(fmt_manager(costo_acum, prefix="$"), "$ Real Acum", accent=True)

    with c5:
        render_kpi_small(fmt_manager(costo_ideal_ult, prefix="$"), "$ Ideal Com")

    with c6:
        diff_badge = "red" if pd.notna(gap_costo) and gap_costo > 0 else "green"
        diff_txt = fmt_signed_short(gap_costo, prefix="$")
        render_kpi_small(f'<span class="badge {diff_badge}">{diff_txt}</span>', "Sobrecosto vs ideal", accent=True)

    c7, c8, c9, c10, c11, c12 = st.columns(6)

    with c7:
        render_kpi_small(fmt_num(fcr_real_ult, 4), "Conv Real")

    with c8:
        render_kpi_small(fmt_num(fcr_ideal_ult, 4), "Conv Ideal")

    with c9:
        gap_badge = "red" if pd.notna(gap_fcr) and gap_fcr > 0 else "green"
        gap_txt = fmt_signed_short(gap_fcr)
        render_kpi_small(f'<span class="badge {gap_badge}">{gap_txt}</span>', "Gap Conv")

    with c10:
        render_kpi_small(fmt_manager(alim_ideal_acum, suffix=" kg"), "Alim ideal")

    with c11:
        render_kpi_small(fmt_num(gap_costo_kg, 4, prefix="$"), "Gap $/kg")

    with c12:
        render_kpi_small(fmt_num(mort_pct, 2, suffix="%"), "Mortalidad")

    # ── GRÁFICO CRECIMIENTO REAL vs IDEAL ─────────────────────
    hist_v = hist_cmp[hist_cmp["PesoFinal"].notna() & (hist_cmp["PesoFinal"] > 0)].copy()

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

    if tiene_ideal and "PesoIdeal" in hist_v.columns:
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
            text=f"Crecimiento · {zona_v} · {tipo_v} · {quint_v} · {nombre_g} Gal.{galpon_v}",
            font=dict(size=10, color=CHART_TEXT),
            x=0,
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", font=dict(color="black")),
    )
    st.plotly_chart(fig_ri, width="stretch", key=f"chart_ri_{lote_sel}")

    # ── GRÁFICO COSTO ACUMULADO REAL vs IDEAL ────────────────
    st.caption("**Costo acumulado comparable: REAL vs IDEAL usando el precio/kg real del galpón**")

    if pd.notna(edad_max_lote) and edad_max_lote <= EDAD_MIN_ANALISIS:
        hist_c = hist_cmp.copy()
    else:
        hist_c = hist_cmp[hist_cmp["Edad"] >= EDAD_MIN_ANALISIS].copy()

    fig_c = go.Figure()

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

    fig_c.add_trace(go.Scatter(
        x=hist_c["Edad"], y=hist_c["CostoAcum"],
        mode="lines+markers", name="Costo Real",
        line=dict(color=RED, width=3),
        marker=dict(size=6, color=RED, line=dict(color="white", width=1)),
        fill="tozeroy", fillcolor="rgba(218,41,28,0.08)",
        customdata=custom_real_c,
        hovertemplate=hover_real_c,
    ))

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
# ══════════════════════════════════════════════════════════════
# COLUMNA DERECHA — SEC 04 · PREDICCIÓN
# ══════════════════════════════════════════════════════════════
with right:

    def fmt_signed_short_r(n, prefix="", suffix=""):
        if pd.isna(n):
            return "—"
        x = float(n)
        base = fmt_manager(abs(x), prefix=prefix, suffix=suffix)
        if x > 0:
            return f"+{base}"
        elif x < 0:
            return f"-{base}"
        return base

    def render_kpi_small_r(value_html, label, accent=False):
        cls = "kpi-chip accent" if accent else "kpi-chip"
        md(f'''
<div class="{cls}" style="
    padding:10px 10px;
    min-height:74px;
    display:flex;
    flex-direction:column;
    justify-content:center;
">
    <div class="kv" style="
        font-size:1rem;
        line-height:1.05;
        white-space:normal;
        word-break:break-word;
        overflow-wrap:anywhere;
    ">{value_html}</div>
    <div class="kl" style="
        font-size:.66rem;
        line-height:1.1;
        margin-top:4px;
    ">{label}</div>
</div>''')

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
    else:
        TARGET_DAY = 35

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
        else:
            st.write(f"📋 Lote: **{extract_lote_codigo(lote_sel)}**")

            # ── Datos base del lote ────────────────────────────
            info_plot_pred = SF[SF["LoteCompleto"] == lote_sel].iloc[0]
            zona_pred = info_plot_pred["ZonaNombre"]
            tipo_pred = info_plot_pred["TipoStd"]
            quint_pred = info_plot_pred["Quintil"]

            # HISTÓRICO VISUAL = ya enriquecido con ideal comparable
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
                st.stop()

            edad_actual = int(hist_real_plot.iloc[-1]["Edad"])
            peso_actual = float(hist_real_plot.iloc[-1]["PesoFinal"])
            aves_actual = (
                float(hist_real_plot.iloc[-1]["AvesVivas"])
                if "AvesVivas" in hist_real_plot.columns and pd.notna(hist_real_plot.iloc[-1]["AvesVivas"])
                else np.nan
            )

            display_day_max = TARGET_DAY
            target_pred_day = max(TARGET_DAY, edad_actual)

            # ── Precio/kg real del galpón por día ──────────────
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

            # ── Cache de predicción ─────────────────────────────
            if "pred_cache" not in st.session_state:
                st.session_state["pred_cache"] = {}

            cache_key = f"{lote_sel}__d{target_pred_day}"

            if cache_key not in st.session_state["pred_cache"]:
                with st.spinner("⏳ Calculando predicción..."):
                    # Para el modelo usamos la base original
                    hist_raw_model = DF_ALL[DF_ALL["LoteCompleto"] == lote_sel].sort_values("Edad").copy()
                    hist_pred = _limpiar_historial_para_modelo(hist_raw_model)

                    if hist_pred.empty:
                        st.session_state["pred_cache"][cache_key] = {
                            "error": "Historial vacío (PesoFinal válido)"
                        }
                    else:
                        res = predictor.proyectar_curva(
                            hist_lote=hist_pred,
                            target_edad=target_pred_day,
                            enforce_monotonic="isotonic",
                        )
                        st.session_state["pred_cache"][cache_key] = {
                            "res": res,
                            "hist_pred": hist_pred
                        }

            cache_item = st.session_state["pred_cache"].get(cache_key, {})
            if cache_item.get("error"):
                st.error(f"❌ {cache_item['error']}")
            else:
                res = cache_item.get("res", {})
                hist_pred_guardado = cache_item.get("hist_pred")

                if res.get("error"):
                    st.error(f"❌ Error en predicción: {res['error']}")
                else:
                    df_curve = res.get("df")

                    if not hist_real_plot.empty:
                        edad_actual = int(hist_real_plot.iloc[-1]["Edad"])
                        peso_actual = float(hist_real_plot.iloc[-1]["PesoFinal"])
                    else:
                        edad_actual = int(res.get("edad_actual", int(hist_pred_guardado.iloc[-1]["Edad"])))
                        peso_actual = float(hist_pred_guardado.iloc[-1]["PesoFinal"])

                    dias_rest = max(0, TARGET_DAY - edad_actual)

                    # ── Curva ideal extendida hasta día 35 ───────
                    ideal_pred_plot = get_curva_ideal_promedio(
                        zona_pred, tipo_pred, quint_pred, IDEALES,
                        edad_max=TARGET_DAY
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

                    # ── Ajuste SHIFT/ANCLA de la curva proyectada ─
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

                    # ── REAL histórico con costo ideal comparable ─
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

                    # ── IDEAL line con costo comparable usando precio real del lote ─
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

                    # ── PROYECCIÓN con costo comparable hasta día 35 ─
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

                    # Fallback si el lote ya pasó de 35 o no hay proyección útil
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

                    # ── KPIs superiores ────────────────────────────
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        render_kpi_small_r(f"{peso_objetivo:.3f} kg", f"Peso objetivo D{TARGET_DAY}", accent=True)
                    with c2:
                        render_kpi_small_r(f"{dias_rest} d", "Días restantes")
                    with c3:
                        render_kpi_small_r(fmt_manager(costo_estimado_obj, prefix="$"), f"Costo estimado D{TARGET_DAY}")
                    with c4:
                        render_kpi_small_r(fmt_manager(gap_estimado_obj, prefix="$"), f"Gap estimado D{TARGET_DAY}")

                    # ── Gráfico: REAL + IDEAL + PROYECCIÓN ─────────
                    fig_p = go.Figure()

                    # 1) REAL
                    if not hist_real_hover.empty:
                        custom_real_pred = np.array([
                            [
                                fmt_num(r.get("PrecioKgRealDia", np.nan), 3, prefix="$", suffix="/kg"),
                                fmt_manager(r.get("CostoAcum", np.nan), prefix="$"),
                                fmt_manager(r.get("CostoIdealAcum_comp", np.nan), prefix="$"),
                                fmt_signed_short_r(r.get("GapCosto_comp", np.nan), prefix="$"),
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
                            line=dict(color=BLUE, width=3),
                            marker=dict(size=6, color=BLUE, line=dict(color="white", width=1)),
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
                                fmt_signed_short_r(r.get("GapCosto_line", np.nan), prefix="$"),
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
                                fmt_signed_short_r(r.get("GapCosto_estimado", np.nan), prefix="$"),
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
                            text=f"Real vs Ideal vs Proyección · {zona_pred} · {tipo_pred} · {quint_pred}",
                            font=dict(size=10, color=CHART_TEXT),
                            x=0,
                        ),
                    )

                    st.plotly_chart(fig_p, width="stretch", key=f"chart_pred_{lote_sel}")


# ──────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────
md(f"""
<div style="text-align:center;font-size:.72rem;color:{MUTED};
border-top:1px solid {BORDER};padding-top:10px;margin-top:20px">
PRONACA · Dashboard v15 ++ · MODULARIZADO · {hoy:%d/%m/%Y %H:%M}
</div>
""")