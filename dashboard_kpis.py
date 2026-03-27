import numpy as np
import pandas as pd
import streamlit as st
from config import RED, BLACK, BG, CARD, BORDER, TEXT, MUTED, GREEN, AMBER, BLUE
from helpers import md, fmt_num

# ──────────────────────────────────────────────────────────────
# FORMATTERS COMUNES
# ──────────────────────────────────────────────────────────────

def fmt_manager(n, prefix="", suffix=""):
    """Formatea números grandes con unidades (M, mil, etc)"""
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


def fmt_signed_short(n, prefix="", suffix=""):
    """Formatea números con signo (+ o -)"""
    if pd.isna(n):
        return "—"
    x = float(n)
    base = fmt_manager(abs(x), prefix=prefix, suffix=suffix)
    if x > 0:
        return f"+{base}"
    elif x < 0:
        return f"-{base}"
    return base


# ──────────────────────────────────────────────────────────────
# HELPERS VISUALES
# ──────────────────────────────────────────────────────────────

def render_kpi_small(value_html, label, accent=False):
    """Renderiza una tarjeta KPI pequeña"""
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


# ──────────────────────────────────────────────────────────────
# KPIs GLOBALES
# ──────────────────────────────────────────────────────────────

def render_kpis_globales(SF):
    """Renderiza los 6 KPIs globales superiores"""
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
