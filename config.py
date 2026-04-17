# ──────────────────────────────────────────────────────────────
# config.py · PRONACA Dashboard v15
# Constantes globales: archivos, colores, etapas
# ──────────────────────────────────────────────────────────────

# ── Archivos de datos ─────────────────────────────────────────
MAIN_FILE         = "etl/data/produccion_mes_actual.xlsx"
BENCH_FILE        = "data/LOTES_IDEALES_DASHBOARD_COMPATIBLE.xlsx"
MODEL_FILE        = "models/modelo_rf_avicola.joblib"
EDAD_MIN_ANALISIS = 7

# ── Brand tokens ─────────────────────────────────────────────
RED    = "#DA291C"
BLACK  = "#0B0B0C"
BG     = "#F0F3F7"
CARD   = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT   = "#0F172A"
MUTED  = "#64748B"
GREEN  = "#16A34A"
AMBER  = "#D97706"
BLUE   = "#1D4ED8"

# ── Etapas ───────────────────────────────────────────────────
ETAPA_ORDER = [
    "INICIO (1-14)",
    "CRECIMIENTO (15-28)",
    "PRE-ACABADO (29-35)",
    "ACABADO (36+)",
]

ETAPA_COLORS = {
    "INICIO (1-14)":       "#93C5FD",
    "CRECIMIENTO (15-28)": "#3B82F6",
    "PRE-ACABADO (29-35)": "#F59E0B",
    "ACABADO (36+)":       "#DA291C",
}