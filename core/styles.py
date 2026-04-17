# ──────────────────────────────────────────────────────────────
# styles.py · PRONACA Dashboard v15
# Inyección de CSS global (llama a md() de helpers)
# ──────────────────────────────────────────────────────────────
from config   import RED, BLACK, BG, CARD, BORDER, TEXT, MUTED, GREEN, AMBER, BLUE
from .helpers import md


def inject_css():
    md(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800;900&family=Bebas+Neue&display=swap');

/* ──────────────────────────────────────────────────────────
   BASE GLOBAL
────────────────────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"], .stApp {{
    background: {BG} !important;
    font-family: 'DM Sans', sans-serif !important;
    color: {TEXT} !important;
}}

* {{
    font-family: 'DM Sans', sans-serif !important;
}}

.block-container {{
    padding-top: 0.9rem !important;
    padding-bottom: 1.2rem !important;
    max-width: 100% !important;
}}

footer {{
    visibility: hidden;
}}

/* ──────────────────────────────────────────────────────────
   CARDS / HEADER
────────────────────────────────────────────────────────── */
.card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 12px 14px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}}

.pronaca-header {{
    background: {BLACK};
    border-radius: 14px;
    padding: 14px 20px;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 14px;
}}

.pronaca-header-title {{
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 2.0rem;
    color: #fff;
    letter-spacing: 1.4px;
    line-height: 1.1;
}}

.pronaca-header-sub {{
    font-size: 0.82rem;
    color: rgba(255,255,255,0.60);
    margin-top: 2px;
    font-weight: 600;
}}

.pronaca-header-pill {{
    margin-left: auto;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 0.85rem;
    color: rgba(255,255,255,0.78) !important;
    white-space: nowrap;
    font-weight: 700;
}}

/* ──────────────────────────────────────────────────────────
   FILTROS SUPERIORES
────────────────────────────────────────────────────────── */
.filter-bar {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 12px 14px 10px 14px;
    margin-bottom: 10px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}}

/* Labels de widgets */
div[data-testid="stWidgetLabel"] p,
label[data-testid="stWidgetLabel"] p,
.stMultiSelect label p,
.stSelectbox label p,
.stTextInput label p,
.stNumberInput label p {{
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.90rem !important;
    font-weight: 900 !important;
    color: {TEXT} !important;
    letter-spacing: 0.2px !important;
    opacity: 1 !important;
    margin-bottom: 4px !important;
}}

/* Contenedor del multiselect / select */
div[data-baseweb="select"] > div {{
    min-height: 44px !important;
    border-radius: 10px !important;
    border: 1px solid {BORDER} !important;
    background: #FFFFFF !important;
    box-shadow: none !important;
    transition: all 0.18s ease !important;
}}

div[data-baseweb="select"] > div:hover {{
    border-color: rgba(218,41,28,0.35) !important;
    box-shadow: 0 0 0 1px rgba(218,41,28,0.08) !important;
}}

div[data-baseweb="select"] > div:focus-within {{
    border-color: {RED} !important;
    box-shadow: 0 0 0 2px rgba(218,41,28,0.10) !important;
}}

/* Texto dentro del multiselect */
div[data-baseweb="select"] span,
div[data-baseweb="select"] input,
div[data-baseweb="select"] div {{
    font-family: 'DM Sans', sans-serif !important;
    color: {TEXT} !important;
    font-size: 0.87rem !important;
}}

/* Placeholder */
div[data-baseweb="select"] input::placeholder {{
    color: {MUTED} !important;
    opacity: 1 !important;
}}

/* Tags seleccionados */
div[data-baseweb="tag"] {{
    background: rgba(218,41,28,0.08) !important;
    border: 1px solid rgba(218,41,28,0.18) !important;
    border-radius: 999px !important;
}}

div[data-baseweb="tag"] span {{
    color: {RED} !important;
    font-weight: 800 !important;
    font-size: 0.78rem !important;
}}

/* Dropdown del multiselect */
ul[role="listbox"] {{
    border-radius: 10px !important;
    border: 1px solid {BORDER} !important;
    box-shadow: 0 8px 20px rgba(0,0,0,0.08) !important;
}}

ul[role="listbox"] li {{
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.86rem !important;
    color: {TEXT} !important;
}}

/* Botón principal */
.stButton > button {{
    width: 100% !important;
    min-height: 44px !important;
    border-radius: 10px !important;
    border: 1px solid {RED} !important;
    background: linear-gradient(180deg, {RED} 0%, #c61f14 100%) !important;
    color: white !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.88rem !important;
    font-weight: 900 !important;
    letter-spacing: 0.2px !important;
    box-shadow: 0 2px 8px rgba(218,41,28,0.18) !important;
    transition: all 0.18s ease !important;
}}

.stButton > button:hover {{
    background: linear-gradient(180deg, #c61f14 0%, #a91910 100%) !important;
    border-color: #a91910 !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(218,41,28,0.24) !important;
}}

.stButton > button:focus {{
    box-shadow: 0 0 0 2px rgba(218,41,28,0.14) !important;
}}

/* ──────────────────────────────────────────────────────────
   KPI CARDS
────────────────────────────────────────────────────────── */
.kpi-chip {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 10px 14px;
    min-width: 150px;
    flex: 1;
    box-shadow: 0 1px 5px rgba(0,0,0,0.04);
}}

.kpi-chip.accent {{
    border-left: 4px solid {RED};
}}

.kv {{
    font-size: 1.35rem;
    font-weight: 900;
    color: {TEXT};
    line-height: 1;
}}

.kl {{
    font-size: 0.70rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: {MUTED} !important;
    margin-top: 3px;
}}

/* ──────────────────────────────────────────────────────────
   SECCIONES
────────────────────────────────────────────────────────── */
.sec-header {{
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 8px 0 6px 0;
    margin: 4px 0 6px 0;
    border-bottom: 2px solid {BORDER};
}}

.sec-num {{
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 2.0rem;
    color: {RED};
    line-height: 1;
}}

.sec-title {{
    font-size: 1.0rem;
    font-weight: 900;
    color: {TEXT};
    line-height: 1.2;
}}

.sec-sub {{
    font-size: 0.78rem;
    color: {MUTED} !important;
    margin-top: 1px;
    font-weight: 600;
}}

/* ──────────────────────────────────────────────────────────
   BADGES / PILLS / TEXTOS AUXILIARES
────────────────────────────────────────────────────────── */
.badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 900;
    border: 1px solid {BORDER};
    background: #F8FAFC;
}}

.badge.red {{
    color: {RED};
    border-color: rgba(218,41,28,.25);
    background: rgba(218,41,28,.06);
}}

.badge.amber {{
    color: {AMBER};
    border-color: rgba(217,119,6,.25);
    background: rgba(217,119,6,.07);
}}

.badge.green {{
    color: {GREEN};
    border-color: rgba(22,163,74,.25);
    background: rgba(22,163,74,.07);
}}

.sel-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(218,41,28,0.08);
    border: 1px solid rgba(218,41,28,0.25);
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 0.72rem;
    font-weight: 800;
    color: {RED};
    margin-bottom: 6px;
}}

.sel-pill-neutral {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(29,78,216,0.08);
    border: 1px solid rgba(29,78,216,0.20);
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 0.72rem;
    font-weight: 800;
    color: {BLUE};
    margin-bottom: 6px;
}}

.hint-text {{
    font-size: 0.72rem;
    color: {MUTED};
    font-style: italic;
    margin-bottom: 4px;
    font-weight: 600;
}}

/* ──────────────────────────────────────────────────────────
   DATAFRAME / TABLAS STREAMLIT
────────────────────────────────────────────────────────── */
div[data-testid="stDataFrame"] {{
    border: 1px solid {BORDER};
    border-radius: 12px;
    overflow: hidden;
}}

div[data-testid="stDataFrame"] * {{
    font-family: 'DM Sans', sans-serif !important;
}}

/* ──────────────────────────────────────────────────────────
   CAPTIONS / METRICS
────────────────────────────────────────────────────────── */
[data-testid="stCaptionContainer"] {{
    color: {MUTED} !important;
    font-weight: 600 !important;
}}

[data-testid="stMetricValue"] {{
    font-weight: 900 !important;
    color: {TEXT} !important;
}}

[data-testid="stMetricLabel"] {{
    color: {MUTED} !important;
    font-weight: 700 !important;
}}
</style>
""")