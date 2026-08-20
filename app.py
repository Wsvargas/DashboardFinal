import os
import pandas as pd
import streamlit as st
from datetime import datetime


# ── Módulos propios  ───────────────────────────────────────────
from config import (
    MAIN_FILE, BENCH_FILE, MODEL_FILE, RED, BLACK, BG, CARD, BORDER, TEXT, MUTED, GREEN, AMBER, BLUE,
    ETAPA_ORDER,
)
from core.helpers import md, _file_mtime
from core.styles import inject_css
from core.data_loader import (
    load_and_prepare,
    load_ideales,
    build_snapshot_activos,
    enriquecer_historial_con_ideal,
)

# ── Módulos del dashboard ─────────────────────────────────────
from dashboard.kpis  import render_kpis_globales, render_kpi_sobrecosto
from dashboard.sec00_riesgo import render_lotes_riesgo
from dashboard.diccionario import mostrar_diccionario
from dashboard.sec01 import render_sec01
from dashboard.sec02 import render_sec02
from dashboard.sec03 import render_sec03
from dashboard.sec04 import render_sec04


# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PRONACA | Producción Avícola v15",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ──────────────────────────────────────────────────────────────
# ROUTER simple (dashboard / predictiva operativa)
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
    from predictor import operativo as app_predictor_operativo
    app_predictor_operativo.render(go_dashboard=go_dashboard)
    st.stop()

# ──────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────
inject_css()

# ──────────────────────────────────────────────────────────────
# PREDICTOR CACHEADO
# ──────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_predictor_cached(model_path: str, model_mtime: float):
    from core.model_predictor import cargar_predictor
    return cargar_predictor(model_path)

# ──────────────────────────────────────────────────────────────
# CARGA DE DATOS
# ──────────────────────────────────────────────────────────────
if not os.path.exists(MAIN_FILE):
    st.error(f"❌ No se encontró {MAIN_FILE}")
    st.stop()

if not os.path.exists(BENCH_FILE):
    st.error(f"❌ No se encontró {BENCH_FILE}")
    st.stop()

with st.spinner("Cargando datos…"):
    DF_ALL = load_and_prepare(MAIN_FILE)
    IDEALES = load_ideales(BENCH_FILE)

if DF_ALL is None or DF_ALL.empty:
    st.error("❌ No se pudo cargar la base principal o está vacía.")
    st.stop()

if IDEALES is None or IDEALES.empty:
    st.error("❌ No se pudo cargar la base de ideales o está vacía.")
    st.stop()

with st.spinner("Procesando histórico comparable…"):
    DF_HIST_COMP = enriquecer_historial_con_ideal(DF_ALL, IDEALES)

if DF_HIST_COMP is None or DF_HIST_COMP.empty:
    st.error("❌ No se pudo construir el histórico comparable.")
    st.stop()

with st.spinner("Procesando snapshot…"):
    SNAP = build_snapshot_activos(DF_HIST_COMP)

if SNAP is None or SNAP.empty:
    st.warning("No hay lotes ACTIVO en el archivo.")
    st.stop()

# ── Session state ─────────────────────────────────────────────
if "lote_anterior" not in st.session_state:
    st.session_state["lote_anterior"] = None

if "prediccion_resultado" not in st.session_state:
    st.session_state["prediccion_resultado"] = None

if "lote_sel_sec03" not in st.session_state:
    st.session_state["lote_sel_sec03"] = None

if "pred_cache" not in st.session_state:
    st.session_state["pred_cache"] = {}

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────
hoy = datetime.today()

# Fecha de corte REAL de los datos (última transacción del ETL,
# excluyendo filas extendidas que llevan fechas proyectadas a futuro)
try:
    _df_fechas = DF_ALL
    if "EsExtendido" in DF_ALL.columns:
        _no_ext = pd.to_numeric(DF_ALL["EsExtendido"], errors="coerce").fillna(0) != 1
        _df_fechas = DF_ALL[_no_ext]
    _fecha_corte = pd.to_datetime(_df_fechas["FechaTransaccion"], errors="coerce").max()
    corte_txt = f"{_fecha_corte:%d %b %Y}" if pd.notna(_fecha_corte) else f"{hoy:%d %b %Y}"
except Exception:
    corte_txt = f"{hoy:%d %b %Y}"

hc1, hc2, hc3 = st.columns([4.3, 1.5, 1.0])

with hc1:
    md(f"""
    <div class="pronaca-header">
      <div>
        <div class="pronaca-header-title">----</div>
        <div class="pronaca-header-title">PRONACA · PRODUCCIÓN AVÍCOLA v15</div>
        <div class="pronaca-header-sub">Dashboard Interactivo · Con acceso a predictor operativo</div>
      </div>
      <div class="pronaca-header-pill">📅 Datos al corte: {corte_txt}</div>
    </div>
    """)

with hc2:
    st.write("")
    st.write("")
    if st.button("🔮 Ir a predictor operativo", use_container_width=True):
        go_predictiva()

with hc3:
    st.write("")
    st.write("")
    if st.button("📖 Diccionario", use_container_width=True):
        mostrar_diccionario()

# ──────────────────────────────────────────────────────────────
# FILTROS SUPERIORES
# ──────────────────────────────────────────────────────────────
md('<div class="filter-bar">')

fc1, fc2, fc3, fc4 = st.columns([1.3, 1.2, 1.2, 1.2])

with fc1:
    sel_zona = st.multiselect(
        "📍 Zona",
        ["BUCAY", "SANTO DOMINGO"],
        default=["BUCAY", "SANTO DOMINGO"],
    )

with fc2:
    sel_tipo = st.multiselect(
        "🏠 Tipo",
        ["PROPIA", "PAC"],
        default=["PROPIA", "PAC"],
    )

with fc3:
    sel_quint = st.multiselect(
        "🧩 Quintil",
        ["Q1", "Q2", "Q3", "Q4", "Q5"],
        default=["Q1", "Q2", "Q3", "Q4", "Q5"],
    )

with fc4:
    sel_estado = st.multiselect(
        "🔄 Estado",
        ["ABIERTO", "CERRADO"],
        default=["ABIERTO"],
    )

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
# KPIs GLOBALES — dinámicos según selección activa
# Lee el estado de los widgets ANTES de renderizarlos (Streamlit
# actualiza session_state con la selección del frontend antes de
# ejecutar el script, por eso esto funciona sin lag).
# ──────────────────────────────────────────────────────────────
def _puntos_widget(key):
    """Extrae la lista de puntos seleccionados de un chart por su key."""
    ws = st.session_state.get(key)
    if ws is None:
        return []
    try:
        sel = ws.selection if hasattr(ws, "selection") else ws.get("selection", {})
        return (sel or {}).get("points", [])
    except Exception:
        return []

# 1. Etapa: chart_etapas (SEC01) — mapeamos point_index a nombre de etapa
_etapas_disponibles = [e for e in ETAPA_ORDER if e in SF["Etapa"].values]
_etapas_kpi = []
for _p in _puntos_widget("chart_etapas"):
    _idx = _p.get("point_index")
    if _idx is not None and 0 <= _idx < len(_etapas_disponibles):
        _etapas_kpi.append(_etapas_disponibles[_idx])

# 2. Granja: chart_granjas (SEC02) — customdata[0] = GranjaID
_granja_kpi = None
_pts_g = _puntos_widget("chart_granjas")
if _pts_g:
    try:
        _granja_kpi = _pts_g[0]["customdata"][0]
    except Exception:
        pass

# 3. Lote: ya guardado en session_state por SEC02/SEC03
_lote_kpi = st.session_state.get("lote_sel_sec03")

# Jerarquía: lote > granja > etapa > todos
SF_KPI = SF.copy()
_ctx = None
if _lote_kpi and _lote_kpi in SF["LoteCompleto"].values:
    SF_KPI = SF[SF["LoteCompleto"] == _lote_kpi]
    _ctx = f"🔖 {_lote_kpi}"
elif _granja_kpi and _granja_kpi in SF["GranjaID"].values:
    SF_KPI = SF[SF["GranjaID"] == _granja_kpi]
    _ctx = f"🏭 Granja {_granja_kpi}"
elif _etapas_kpi:
    SF_KPI = SF[SF["Etapa"].isin(_etapas_kpi)]
    _ctx = "📊 " + " + ".join(
        e.split("(")[1].rstrip(")") if "(" in e else e for e in _etapas_kpi
    )

render_kpis_globales(SF_KPI, context_label=_ctx)

# ── Sobrecosto acumulado / ahorro potencial ───────────────────
render_kpi_sobrecosto(SF_KPI)

# ──────────────────────────────────────────────────────────────
# LOTES EN RIESGO — alerta predictiva (todos los lotes abiertos)
# ──────────────────────────────────────────────────────────────
render_lotes_riesgo(
    SF=SF,
    DF_ALL=DF_ALL,
    IDEALES=IDEALES,
    data_key=_file_mtime(MAIN_FILE),
    model_mtime=_file_mtime(MODEL_FILE),
)

# ──────────────────────────────────────────────────────────────
# LAYOUT PRINCIPAL
# ──────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ══════════════════════════════════════════════════════════════
# COLUMNA IZQUIERDA
# ══════════════════════════════════════════════════════════════
with left:
    etapas_sel = render_sec01(SF, DF_HIST_COMP)

    SF_02 = SF.copy()
    if etapas_sel:
        SF_02 = SF_02[SF_02["Etapa"].isin(etapas_sel)]

    lote_sel = render_sec02(SF_02, DF_HIST_COMP, IDEALES)

    if lote_sel:
        st.session_state["lote_sel_sec03"] = lote_sel

    # Si el lote guardado ya no está en el SF activo (cambio de filtros),
    # lo limpiamos para evitar errores en sec03/sec04.
    lote_guardado = st.session_state.get("lote_sel_sec03")
    if lote_guardado and lote_guardado not in SF["LoteCompleto"].values:
        st.session_state["lote_sel_sec03"] = None

    render_sec03(
        lote_sel=st.session_state.get("lote_sel_sec03"),
        SF=SF,
        DF_FILTRADO=DF_FILTRADO,
        DF_ALL=DF_ALL,
        IDEALES=IDEALES,
    )

# ══════════════════════════════════════════════════════════════
# COLUMNA DERECHA — SEC 04 · PREDICCIÓN
# ══════════════════════════════════════════════════════════════
with right:
    render_sec04(
        lote_sel=st.session_state.get("lote_sel_sec03"),
        SF=SF,
        DF_FILTRADO=DF_FILTRADO,
        DF_ALL=DF_ALL,
        IDEALES=IDEALES,
        get_predictor_cached=get_predictor_cached,
        pred_cache=st.session_state.get("pred_cache", {}),
    )

# ──────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────
md(f"""
<div style="text-align:center;font-size:.72rem;color:{MUTED};
border-top:1px solid {BORDER};padding-top:10px;margin-top:20px">
PRONACA · Dashboard v15 ++ · MODULARIZADO · {hoy:%d/%m/%Y %H:%M}
</div>
""")