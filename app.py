import os
import streamlit as st
from datetime import datetime


# ── Módulos propios  ───────────────────────────────────────────
from config import (
    MAIN_FILE, BENCH_FILE, RED, BLACK, BG, CARD, BORDER, TEXT, MUTED, GREEN, AMBER, BLUE,
)
from core.helpers import md
from core.styles import inject_css
from core.data_loader import (
    load_and_prepare,
    load_ideales,
    build_snapshot_activos,
    enriquecer_historial_con_ideal,
)

# ── Módulos del dashboard ─────────────────────────────────────
from dashboard.kpis  import render_kpis_globales
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

hc1, hc2 = st.columns([5, 1.5])

with hc1:
    md(f"""
    <div class="pronaca-header">
      <div>
        <div class="pronaca-header-title">----</div>
        <div class="pronaca-header-title">PRONACA · PRODUCCIÓN AVÍCOLA v15</div>
        <div class="pronaca-header-sub">Dashboard Interactivo · Con acceso a predictor operativo</div>
      </div>
      <div class="pronaca-header-pill">📅 Corte {hoy:%d %b %Y}</div>
    </div>
    """)

with hc2:
    st.write("")
    st.write("")
    if st.button("🔮 Ir a predictor operativo", use_container_width=True):
        go_predictiva()

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
# KPIs GLOBALES
# ──────────────────────────────────────────────────────────────
render_kpis_globales(SF)

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