import os
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from config import BENCH_FILE
from data_loader import load_ideales, get_curva_ideal_promedio


# =========================================================
# CONFIGURACIÓN VISUAL LOCAL
# =========================================================
PAGE_BG = "#FFFFFF"
CARD_BG = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT = "#0F172A"
MUTED = "#64748B"
PRIMARY = "#E11D48"
PRIMARY_HOVER = "#BE123C"
BLUE = "#3B82F6"
RED = "#EF4444"
AMBER = "#F59E0B"

TARGET_DEFAULT = 35


# =========================================================
# PAGE CONFIG
# =========================================================
def apply_page_config():
    st.set_page_config(
        page_title="PRONACA | Proyección Operativa de Peso",
        layout="wide",
        initial_sidebar_state="expanded",
    )


# =========================================================
# CSS LOCAL
# =========================================================
def inject_local_css():
    st.markdown(
        f"""
        <style>
        .stApp {{
            background: {PAGE_BG};
            color: {TEXT};
        }}

        [data-testid="stAppViewContainer"] {{
            background: {PAGE_BG};
        }}

        [data-testid="stHeader"] {{
            background: transparent;
        }}

        .block-container {{
            padding-top: 1.6rem;
            padding-bottom: 2.2rem;
            max-width: 1200px;
        }}

        .main-card {{
            background: {CARD_BG};
            border: 1px solid {BORDER};
            border-radius: 16px;
            padding: 22px 24px;
            margin-bottom: 18px;
            box-shadow: 0 2px 10px rgba(15, 23, 42, 0.05);
            border-left: 5px solid {PRIMARY};
        }}

        .main-title {{
            font-size: 1.55rem;
            font-weight: 800;
            color: {TEXT};
            margin-bottom: 6px;
            letter-spacing: -0.3px;
        }}

        .main-subtitle {{
            font-size: 0.98rem;
            color: {MUTED};
            line-height: 1.55;
        }}

        .section-title {{
            font-size: 1.08rem;
            font-weight: 800;
            color: {TEXT};
            margin: 20px 0 12px 0;
            padding-bottom: 8px;
            border-bottom: 1px solid {BORDER};
        }}

        .kpi-card {{
            background: {CARD_BG};
            border: 1px solid {BORDER};
            border-radius: 14px;
            padding: 18px;
            min-height: 96px;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}

        .kpi-value {{
            font-size: 1.35rem;
            font-weight: 800;
            color: {TEXT};
            line-height: 1.1;
        }}

        .kpi-label {{
            font-size: 0.82rem;
            color: {MUTED};
            margin-top: 6px;
            line-height: 1.2;
        }}

        .info-strip {{
            background: #F8FAFC;
            border: 1px solid {BORDER};
            border-radius: 12px;
            padding: 14px 16px;
            margin: 14px 0;
            color: {TEXT};
            font-size: 0.93rem;
        }}

        .stButton > button {{
            width: 100%;
            height: 48px;
            border-radius: 12px;
            background: {PRIMARY};
            color: white;
            border: 0;
            font-weight: 700;
            font-size: 0.96rem;
            box-shadow: 0 2px 8px rgba(225, 29, 72, 0.18);
        }}

        .stButton > button:hover {{
            background: {PRIMARY_HOVER};
            color: white;
        }}

        [data-testid="stWidgetLabel"] p,
        [data-testid="stWidgetLabel"] span,
        label {{
            color: {TEXT} !important;
            font-weight: 600 !important;
        }}

        [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
            background: {CARD_BG} !important;
            border: 1px solid {BORDER} !important;
            border-radius: 10px !important;
            min-height: 42px !important;
        }}

        [data-testid="stSelectbox"] div[data-baseweb="select"] *,
        [data-testid="stSelectbox"] div[data-baseweb="select"] span,
        [data-testid="stSelectbox"] div[data-baseweb="select"] div,
        [data-testid="stSelectbox"] div[data-baseweb="select"] input,
        [data-testid="stSelectbox"] div[data-baseweb="select"] p {{
            color: {TEXT} !important;
            fill: {TEXT} !important;
            -webkit-text-fill-color: {TEXT} !important;
            opacity: 1 !important;
        }}

        [data-testid="stSelectbox"] div[data-baseweb="select"] input::placeholder {{
            color: {TEXT} !important;
            -webkit-text-fill-color: {TEXT} !important;
            opacity: 1 !important;
        }}

        [data-testid="stSelectbox"] svg {{
            fill: {TEXT} !important;
            color: {TEXT} !important;
        }}

        div[data-baseweb="popover"] *,
        div[data-baseweb="popover"] ul,
        div[data-baseweb="popover"] li,
        div[data-baseweb="popover"] div[role="option"],
        ul[role="listbox"],
        li[role="option"] {{
            background: {CARD_BG} !important;
            color: {TEXT} !important;
            fill: {TEXT} !important;
            -webkit-text-fill-color: {TEXT} !important;
        }}

        div[data-testid="stNumberInputContainer"] input {{
            background: {CARD_BG} !important;
            color: {TEXT} !important;
            -webkit-text-fill-color: {TEXT} !important;
            border: 1px solid {BORDER} !important;
            border-radius: 10px !important;
            opacity: 1 !important;
        }}

        div[data-testid="stDataFrame"] {{
            border: 1px solid {BORDER};
            border-radius: 12px;
            overflow: hidden;
            background: {CARD_BG};
        }}

        details {{
            background: {CARD_BG};
            border: 1px solid {BORDER};
            border-radius: 12px;
            padding: 8px 12px;
        }}

        summary {{
            color: {TEXT};
            font-weight: 700;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# MODELO
# =========================================================
def load_predictor(model_path: str):
    from model_predictor import cargar_predictor
    return cargar_predictor(model_path)


# =========================================================
# HELPERS VISUALES
# =========================================================
def render_header():
    st.markdown(
        f"""
        <div class="main-card">
            <div class="main-title">Proyección Operativa de Peso</div>
            <div class="main-subtitle">
                Ingrese los datos base del lote para estimar el peso esperado al día objetivo.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_data_dictionary():
    with st.expander("Diccionario de datos", expanded=False):
        st.markdown(
            f"""
            <div style="color:{MUTED};line-height:1.8;font-size:0.95rem;">
                <b style="color:{TEXT}">Zona:</b> ubicación operativa del lote.<br>
                <b style="color:{TEXT}">Tipo de granja:</b> clasificación de la granja.<br>
                <b style="color:{TEXT}">Quintil:</b> grupo de referencia del lote.<br>
                <b style="color:{TEXT}">Reproductora:</b> categoría usada como referencia.<br>
                <b style="color:{TEXT}">Edad actual:</b> edad del lote al momento de la consulta.<br>
                <b style="color:{TEXT}">Peso actual:</b> peso promedio actual del lote en kilogramos.<br>
                <b style="color:{TEXT}">Aves vivas:</b> cantidad estimada de aves vivas del lote.<br>
                <b style="color:{TEXT}">Día objetivo:</b> día hasta el cual se desea proyectar.
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_kpi_card(value: str, label: str):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-value">{value}</div>
            <div class="kpi-label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def detectar_columna_peso(df: pd.DataFrame) -> Optional[str]:
    for c in ["Peso", "Peso_ideal", "PesoIdeal"]:
        if c in df.columns:
            return c
    return None


# =========================================================
# BASE DIARIA PARA EL MODELO
# =========================================================
def seed_history_from_ideal(
    ideal_curve: pd.DataFrame,
    edad_actual: int,
    peso_actual: float,
    aves_vivas: float,
    zona: str,
    tipo: str,
    quintil: str,
    reproductora: str,
) -> pd.DataFrame:
    curve = ideal_curve.copy()
    peso_col = detectar_columna_peso(curve)
    if peso_col is None:
        raise ValueError("La curva de referencia no tiene columna de peso reconocible.")

    curve["Edad"] = pd.to_numeric(curve["Edad"], errors="coerce")
    curve[peso_col] = pd.to_numeric(curve[peso_col], errors="coerce")
    curve["FCR_ideal"] = pd.to_numeric(curve.get("FCR_ideal"), errors="coerce")
    curve = curve.dropna(subset=["Edad", peso_col]).sort_values("Edad").copy()

    if curve.empty:
        raise ValueError("La curva de referencia está vacía para la combinación seleccionada.")

    start_day = 7
    dias = np.arange(start_day, edad_actual + 1, dtype=int)

    ideal_today = np.interp(edad_actual, curve["Edad"].values, curve[peso_col].values)
    if not np.isfinite(ideal_today) or ideal_today <= 0:
        raise ValueError("No se pudo interpolar el peso de referencia del día actual.")

    factor = peso_actual / ideal_today
    ideal_w = np.interp(dias, curve["Edad"].values, curve[peso_col].values)

    if "FCR_ideal" in curve.columns and curve["FCR_ideal"].notna().any():
        fcr_base = curve["FCR_ideal"].ffill().bfill()
        ideal_fcr = np.interp(dias, curve["Edad"].values, fcr_base.values)
    else:
        ideal_fcr = np.full(len(dias), np.nan)

    pesos = ideal_w * factor
    pesos[-1] = float(peso_actual)
    if len(pesos) > 1:
        pesos[:-1] = np.minimum(pesos[:-1], float(peso_actual))
    pesos = np.maximum.accumulate(pesos)

    rows = []
    for d, weight, fcr_d in zip(dias, pesos, ideal_fcr):
        kg_live = aves_vivas * weight if np.isfinite(aves_vivas) else np.nan
        alim_acum = fcr_d * kg_live if np.isfinite(fcr_d) and np.isfinite(kg_live) else np.nan

        rows.append(
            {
                "LoteCompleto": "OPERATIVO-MANUAL-01",
                "Edad": int(d),
                "PesoFinal": float(weight),
                "AvesVivas": aves_vivas,
                "ZonaNombre": zona,
                "TipoStd": tipo,
                "Quintil": quintil,
                "ReproductoraStd": reproductora,
                "EstadoLote": "ABIERTO",
                "X4=Edad": int(d),
                "Edad^2": int(d) ** 2,
                "KgLive": kg_live,
                "FCR_Cum": fcr_d,
                "AlimAcumKg": alim_acum,
                "alimento acumulado": alim_acum,
            }
        )

    return pd.DataFrame(rows).sort_values("Edad").reset_index(drop=True)


def prepare_seed_for_model(seed_hist: pd.DataFrame) -> pd.DataFrame:
    hist = seed_hist.copy().sort_values("Edad").reset_index(drop=True)

    num_cols = [
        "Edad", "PesoFinal", "AvesVivas", "X4=Edad", "Edad^2",
        "KgLive", "FCR_Cum", "AlimAcumKg", "alimento acumulado"
    ]
    for c in num_cols:
        if c in hist.columns:
            hist[c] = pd.to_numeric(hist[c], errors="coerce")

    return hist


# =========================================================
# POSTPROCESO DE PROYECCIÓN CON FORMA MÁS REAL
# =========================================================
def postprocess_projection(
    df_curve: pd.DataFrame,
    ideal_curve: pd.DataFrame,
    edad_actual: int,
    peso_actual: float,
    target_day: int
):
    if df_curve is None or df_curve.empty:
        return pd.DataFrame(), None

    raw = df_curve.copy()
    raw["Dia"] = pd.to_numeric(raw["Dia"], errors="coerce")
    raw = raw[raw["Dia"].notna()].copy()
    raw["Dia"] = raw["Dia"].astype(int)

    ycol_raw = "Peso_pred_kg" if "Peso_pred_kg" in raw.columns else ("Peso_kg" if "Peso_kg" in raw.columns else None)
    if ycol_raw is None:
        return pd.DataFrame(), None

    raw[ycol_raw] = pd.to_numeric(raw[ycol_raw], errors="coerce")

    fila_obj = raw[raw["Dia"] == target_day]
    if not fila_obj.empty and pd.notna(fila_obj.iloc[0][ycol_raw]):
        peso_objetivo_modelo = float(fila_obj.iloc[0][ycol_raw])
    else:
        raw_valid = raw.dropna(subset=[ycol_raw]).sort_values("Dia")
        if raw_valid.empty:
            return pd.DataFrame(), None
        peso_objetivo_modelo = float(raw_valid.iloc[-1][ycol_raw])

    peso_objetivo_modelo = max(float(peso_actual), peso_objetivo_modelo)

    curve = ideal_curve.copy()
    peso_col = detectar_columna_peso(curve)
    if peso_col is None:
        return pd.DataFrame(), None

    curve["Edad"] = pd.to_numeric(curve["Edad"], errors="coerce")
    curve[peso_col] = pd.to_numeric(curve[peso_col], errors="coerce")
    curve = curve.dropna(subset=["Edad", peso_col]).sort_values("Edad").copy()

    dias = np.arange(edad_actual, target_day + 1, dtype=int)
    ideal_daily = np.interp(dias, curve["Edad"].values, curve[peso_col].values)

    ideal_today = float(np.interp(edad_actual, curve["Edad"].values, curve[peso_col].values))
    ideal_gain = np.maximum(ideal_daily - ideal_today, 0)

    total_ideal_gain = float(ideal_gain[-1]) if len(ideal_gain) > 0 else 0.0
    model_gain = float(peso_objetivo_modelo - peso_actual)

    if total_ideal_gain <= 0 or model_gain <= 0:
        pesos_proj = np.linspace(float(peso_actual), float(peso_objetivo_modelo), len(dias))
    else:
        progreso = ideal_gain / total_ideal_gain
        pesos_proj = float(peso_actual) + model_gain * progreso

    pesos_proj[0] = float(peso_actual)
    pesos_proj = np.maximum(pesos_proj, float(peso_actual))
    pesos_proj = np.maximum.accumulate(pesos_proj)

    proj = pd.DataFrame({
        "Dia": dias,
        "Peso_proyectado_kg": pesos_proj
    })

    return proj, "Peso_proyectado_kg"


# =========================================================
# GRÁFICO
# =========================================================
def plot_projection(seed_hist: pd.DataFrame, proj_curve: pd.DataFrame, ycol_pred: str, target_day: int):
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=seed_hist["Edad"],
            y=seed_hist["PesoFinal"],
            mode="lines+markers",
            name="Base",
            line=dict(color=BLUE, width=3, shape="spline"),
            marker=dict(size=7, color=CARD_BG, line=dict(color=BLUE, width=2)),
            hovertemplate="<b>Día %{x}</b><br>Peso base: %{y:.3f} kg<extra></extra>",
        )
    )

    if not proj_curve.empty and ycol_pred:
        fig.add_trace(
            go.Scatter(
                x=proj_curve["Dia"],
                y=proj_curve[ycol_pred],
                mode="lines",
                name="Proyección",
                line=dict(color=RED, width=3, dash="dash", shape="spline"),
                hovertemplate="<b>Día %{x}</b><br>Proyección: %{y:.3f} kg<extra></extra>",
            )
        )

        fig.add_trace(
            go.Scatter(
                x=proj_curve["Dia"],
                y=proj_curve[ycol_pred],
                mode="lines",
                fill="tozeroy",
                fillcolor="rgba(239, 68, 68, 0.05)",
                line=dict(color="rgba(255,255,255,0)", width=0, shape="spline"),
                showlegend=False,
                hoverinfo="skip"
            )
        )

        obj = proj_curve[proj_curve["Dia"] == target_day]
        if not obj.empty:
            valor_obj = float(obj.iloc[0][ycol_pred])
            fig.add_trace(
                go.Scatter(
                    x=[target_day],
                    y=[valor_obj],
                    mode="markers+text",
                    name=f"Día {target_day}",
                    text=[f"{valor_obj:.2f} kg"],
                    textposition="top center",
                    textfont=dict(color=TEXT, size=12),
                    marker=dict(size=12, symbol="diamond", color=AMBER, line=dict(color=CARD_BG, width=2)),
                    hovertemplate=f"<b>Día {target_day}</b><br>%{{y:.3f}} kg<extra></extra>",
                )
            )

    hoy = int(seed_hist["Edad"].max())

    fig.add_vline(
        x=hoy,
        line_dash="dot",
        line_width=2,
        line_color=MUTED,
        annotation_text=f"HOY (Día {hoy})",
        annotation_position="top left",
        annotation_font=dict(color=MUTED, size=10),
    )

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=450,
        margin=dict(l=10, r=10, t=40, b=10),
        font=dict(size=12, color=TEXT),
        legend=dict(
            orientation="h",
            y=-0.15,
            x=0.5,
            xanchor="center",
            font=dict(color=TEXT, size=12),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            title="Edad de las aves (días)",
            gridcolor=BORDER,
            gridwidth=1,
            zeroline=False,
            color=TEXT,
            title_font=dict(color=MUTED, size=12),
            range=[0, target_day + 2],
            showline=True,
            linecolor=BORDER,
        ),
        yaxis=dict(
            title="Peso promedio (kg)",
            gridcolor=BORDER,
            gridwidth=1,
            zeroline=False,
            color=TEXT,
            title_font=dict(color=MUTED, size=12),
            showline=True,
            linecolor=BORDER,
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=CARD_BG,
            font=dict(color=TEXT, size=13),
            bordercolor=BORDER,
        ),
        title=dict(
            text="Evolución y proyección del peso",
            x=0.01,
            font=dict(size=16, color=TEXT),
        ),
    )

    st.plotly_chart(fig, use_container_width=True)


# =========================================================
# APP PRINCIPAL
# =========================================================
def main(go_dashboard=None):
    inject_local_css()

    # Botón de regreso si viene desde el dashboard principal
    if go_dashboard is not None:
        cb1, cb2 = st.columns([1.5, 4.5])
        with cb1:
            if st.button("⬅ Volver al dashboard", use_container_width=True):
                go_dashboard()
        with cb2:
            st.write("")

    render_header()
    render_data_dictionary()

    if not os.path.exists(BENCH_FILE):
        st.error(f"No se encontró el benchmark: {BENCH_FILE}")
        st.stop()

    model_path = "modelo_rf_avicola.joblib"
    predictor = None
    if os.path.exists(model_path):
        predictor = load_predictor(model_path)

    ideales = load_ideales(BENCH_FILE)
    if ideales is None or ideales.empty:
        st.error("No se pudo cargar la base de referencia.")
        st.stop()

    ref = ideales.copy()

    if "Zona_Nombre" not in ref.columns or "TipoGranja" not in ref.columns or "Quintil" not in ref.columns:
        st.error("La base de referencia no tiene la estructura esperada.")
        st.stop()

    if "ReproductoraStd" not in ref.columns:
        ref["ReproductoraStd"] = "SIN_DATO"

    st.markdown('<div class="section-title">Parámetros de entrada</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        zonas = sorted(ref["Zona_Nombre"].dropna().astype(str).unique().tolist())
        zona = st.selectbox("Zona", zonas)

    ref_1 = ref[ref["Zona_Nombre"] == zona].copy()

    with c2:
        tipos = sorted(ref_1["TipoGranja"].dropna().astype(str).unique().tolist())
        tipo = st.selectbox("Tipo de granja", tipos)

    ref_2 = ref_1[ref_1["TipoGranja"] == tipo].copy()

    with c3:
        quintiles = sorted(ref_2["Quintil"].dropna().astype(str).unique().tolist())
        quintil = st.selectbox("Quintil", quintiles)

    ref_3 = ref_2[ref_2["Quintil"] == quintil].copy()

    with c4:
        repros = sorted(ref_3["ReproductoraStd"].dropna().astype(str).unique().tolist())
        reproductora = st.selectbox("Reproductora", repros)

    st.write("")

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        edad_actual = int(
            st.number_input("Edad actual (días)", min_value=7, max_value=45, value=28, step=1)
        )
    with c6:
        peso_actual = float(
            st.number_input("Peso actual (kg)", min_value=0.10, max_value=5.00, value=1.95, step=0.01, format="%.2f")
        )
    with c7:
        aves_vivas = float(
            st.number_input("Aves vivas", min_value=1.0, max_value=1000000.0, value=10000.0, step=100.0, format="%.0f")
        )
    with c8:
        target_day = int(
            st.number_input("Día objetivo", min_value=edad_actual, max_value=45, value=max(TARGET_DEFAULT, edad_actual), step=1)
        )

    st.markdown(
        f"""
        <div class="info-strip">
            El cálculo toma el peso actual como punto de partida y genera la proyección hacia adelante utilizando el modelo entrenado.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    if st.button("Calcular proyección operativa", type="primary", use_container_width=True):
        ideal_curve = get_curva_ideal_promedio(
            zona,
            tipo,
            quintil,
            ideales,
            edad_max=target_day,
            reproductora=reproductora,
        )

        if ideal_curve is None or ideal_curve.empty:
            st.error("No existe base de referencia para la combinación seleccionada.")
            st.stop()

        try:
            seed_hist = seed_history_from_ideal(
                ideal_curve=ideal_curve,
                edad_actual=edad_actual,
                peso_actual=peso_actual,
                aves_vivas=aves_vivas,
                zona=zona,
                tipo=tipo,
                quintil=quintil,
                reproductora=reproductora,
            )
        except Exception as e:
            st.error(f"No se pudo construir la base de cálculo: {e}")
            st.stop()

        if predictor is None or getattr(predictor, "model", None) is None:
            st.error("No se encontró el modelo para calcular la proyección.")
            st.stop()

        hist_model = prepare_seed_for_model(seed_hist)

        res = predictor.proyectar_curva(
            hist_lote=hist_model,
            target_edad=target_day,
            enforce_monotonic="isotonic",
        )

        if res.get("error"):
            st.error(f"Error del predictor: {res['error']}")
            st.stop()

        proj_curve, ycol_pred = postprocess_projection(
            df_curve=res.get("df"),
            ideal_curve=ideal_curve,
            edad_actual=edad_actual,
            peso_actual=peso_actual,
            target_day=target_day,
        )

        if proj_curve.empty or not ycol_pred:
            st.info("No se generó proyección para la combinación ingresada.")
            st.stop()

        fila_obj = proj_curve[proj_curve["Dia"] == target_day]
        peso_objetivo = float(fila_obj.iloc[0][ycol_pred]) if not fila_obj.empty else float(proj_curve.iloc[-1][ycol_pred])
        dias_rest = max(0, target_day - edad_actual)
        crecimiento = peso_objetivo - peso_actual

        st.markdown('<div class="section-title">Resultados de la proyección</div>', unsafe_allow_html=True)

        r1, r2, r3, r4 = st.columns(4)
        with r1:
            render_kpi_card(f"{peso_actual:.3f} kg", "Peso base")
        with r2:
            render_kpi_card(f"{peso_objetivo:.3f} kg", "Peso proyectado")
        with r3:
            render_kpi_card(f"{crecimiento:+.3f} kg", "Crecimiento esperado")
        with r4:
            render_kpi_card(f"{dias_rest} días", "Tiempo restante")

        st.write("")
        plot_projection(seed_hist, proj_curve, ycol_pred, target_day)

        st.write("")
        c_tbl1, c_tbl2 = st.columns(2)

        with c_tbl1:
            with st.expander("Tabla de proyección diaria", expanded=True):
                st.dataframe(
                    proj_curve[["Dia", ycol_pred]].rename(columns={ycol_pred: "Peso proyectado (kg)"}),
                    use_container_width=True,
                    hide_index=True,
                )

        with c_tbl2:
            with st.expander("Base de cálculo utilizada", expanded=False):
                st.dataframe(seed_hist, use_container_width=True, hide_index=True)


def render(go_dashboard=None):
    apply_page_config()
    main(go_dashboard=go_dashboard)


if __name__ == "__main__":
    apply_page_config()
    main()