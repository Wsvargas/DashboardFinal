import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from config import (
    ETAPA_ORDER, ETAPA_COLORS, BLUE, BLACK, CARD, BORDER, MUTED
)
from core.helpers import md, fmt_num
from .kpis import fmt_manager


CHART_TEXT = BLACK


def render_sec01(SF, DF_HIST_COMP):
    """
    Sección 01: Resumen por Etapa
    Retorna lista de etapas seleccionadas
    """
    
    md(f"""
<div class="sec-header">
  <span class="sec-num">01</span>
  <div>
    <div class="sec-title">Resumen por Etapa</div>
    <div class="sec-sub">🖱️ Haz clic en una barra para filtrar granjas abajo</div>
  </div>
</div>""")
    
    # ── Calcular datos por etapa ──────────────────────────────
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
        
        # Badge según costo/kg
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
    
    # ── Layout: gráfico + tabla ───────────────────────────────
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
        
        # Detectar etapas seleccionadas
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
    
    # ── Tabla resumen ─────────────────────────────────────────
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
    
    return etapas_sel
