import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from helpers import _file_mtime, _limpiar_historial_para_modelo
from model_predictor import cargar_predictor

APP_TITLE = "PRONACA · Predictor Standalone"
DEFAULT_MODEL = "modelo_rf_avicola.joblib"

REQUIRED_MIN_COLS = ["Edad", "PesoFinal", "EstadoLote"]
OPTIONAL_COLS = [
    "LoteCompleto",
    "ZonaNombre",
    "TipoStd",
    "Quintil",
    "ReproductoraStd",
    "AvesVivas",
    "AlimAcumKg",
    "CostoAcum",
    "PrecioKg",
    "PrecioKgRealDia",
    "MortPct",
]


def make_default_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "LoteCompleto": ["MANUAL-LOTE-01"] * 4,
            "Edad": [7, 14, 21, 28],
            "PesoFinal": [0.18, 0.46, 0.98, 1.72],
            "EstadoLote": ["ABIERTO"] * 4,
            "ZonaNombre": ["BUCAY"] * 4,
            "TipoStd": ["PAC"] * 4,
            "Quintil": ["Q3"] * 4,
            "ReproductoraStd": ["SIN_DATO"] * 4,
            "AvesVivas": [12000, 11920, 11840, 11790],
            "AlimAcumKg": [2600, 7300, 14600, 24800],
            "CostoAcum": [1300, 3650, 7300, 12400],
            "PrecioKg": [0.50, 0.50, 0.50, 0.50],
            "PrecioKgRealDia": [0.50, 0.50, 0.50, 0.50],
            "MortPct": [0.2, 0.5, 0.8, 1.0],
        }
    )


def validate_history(df: pd.DataFrame) -> list[str]:
    errors = []
    for col in REQUIRED_MIN_COLS:
        if col not in df.columns:
            errors.append(f"Falta la columna obligatoria: {col}")

    if errors:
        return errors

    test = df.copy()
    test["Edad"] = pd.to_numeric(test["Edad"], errors="coerce")
    test["PesoFinal"] = pd.to_numeric(test["PesoFinal"], errors="coerce")

    if test["Edad"].notna().sum() == 0:
        errors.append("No hay edades válidas en la historia.")
    if test["PesoFinal"].notna().sum() == 0:
        errors.append("No hay pesos válidos en la historia.")

    if (test["PesoFinal"].fillna(0) <= 0).all():
        errors.append("Todos los pesos son 0 o vacíos.")

    return errors


def build_template() -> pd.DataFrame:
    return make_default_history()[REQUIRED_MIN_COLS + [c for c in OPTIONAL_COLS if c in make_default_history().columns]]


@st.cache_resource(show_spinner=False)
def get_predictor(model_path: str, mtime: float):
    return cargar_predictor(model_path)


def run_prediction(history_df: pd.DataFrame, target_day: int, monotonic: str):
    hist_clean = _limpiar_historial_para_modelo(history_df)
    if hist_clean.empty:
        raise ValueError("La historia quedó vacía después de la limpieza. Revisa Edad y PesoFinal.")

    model_path = DEFAULT_MODEL
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No encuentro {model_path}. Pon este archivo en la misma carpeta de la app."
        )

    predictor = get_predictor(model_path, _file_mtime(model_path))
    if predictor is None or getattr(predictor, "model", None) is None:
        raise RuntimeError("No se pudo cargar el predictor.")

    result = predictor.proyectar_curva(
        hist_lote=hist_clean,
        target_edad=target_day,
        enforce_monotonic=monotonic,
    )

    if result.get("error"):
        raise RuntimeError(result["error"])

    return hist_clean, result


def render_result(hist_clean: pd.DataFrame, result: dict, target_day: int):
    df_curve = result.get("df")
    if df_curve is None or not isinstance(df_curve, pd.DataFrame) or df_curve.empty:
        st.warning("El modelo no devolvió una curva usable.")
        return

    ycol = "Peso_pred_kg" if "Peso_pred_kg" in df_curve.columns else "Peso_kg"
    if ycol not in df_curve.columns:
        st.warning("La salida del modelo no trae la columna de peso esperada.")
        return

    df_curve = df_curve.copy()
    df_curve["Dia"] = pd.to_numeric(df_curve["Dia"], errors="coerce")
    df_curve[ycol] = pd.to_numeric(df_curve[ycol], errors="coerce")
    df_curve = df_curve.dropna(subset=["Dia", ycol]).sort_values("Dia")

    h = hist_clean.copy().sort_values("Edad")
    h["Edad"] = pd.to_numeric(h["Edad"], errors="coerce")
    h["PesoFinal"] = pd.to_numeric(h["PesoFinal"], errors="coerce")

    today_age = int(h.iloc[-1]["Edad"])
    today_weight = float(h.iloc[-1]["PesoFinal"])

    pred_target = df_curve[df_curve["Dia"] == target_day]
    if pred_target.empty:
        pred_target = df_curve.tail(1)

    target_weight = float(pred_target.iloc[0][ycol]) if not pred_target.empty else np.nan
    delta_weight = target_weight - today_weight if pd.notna(target_weight) else np.nan

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Edad actual", f"{today_age} d")
    with c2:
        st.metric("Peso actual", f"{today_weight:.3f} kg")
    with c3:
        st.metric(
            f"Peso proyectado D{target_day}",
            f"{target_weight:.3f} kg" if pd.notna(target_weight) else "—",
            f"{delta_weight:.3f} kg" if pd.notna(delta_weight) else None,
        )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=h["Edad"],
            y=h["PesoFinal"],
            mode="lines+markers",
            name="Histórico",
            line=dict(width=3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df_curve["Dia"],
            y=df_curve[ycol],
            mode="lines+markers",
            name="Proyección",
            line=dict(width=3, dash="dash"),
        )
    )
    fig.add_vline(x=today_age, line_dash="dot", annotation_text=f"Hoy: {today_age}")
    fig.add_vline(x=target_day, line_dash="dot", annotation_text=f"Meta: {target_day}")
    fig.update_layout(
        template="plotly_white",
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_title="Edad (días)",
        yaxis_title="Peso (kg)",
        hovermode="x unified",
        title="Proyección del lote",
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Ver historia limpia usada por el modelo"):
        st.dataframe(hist_clean, use_container_width=True)

    with st.expander("Ver curva completa devuelta por el modelo"):
        st.dataframe(df_curve, use_container_width=True)


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption("App aparte para usar el mismo modelo predictivo con carga manual o por archivo.")

    with st.sidebar:
        st.subheader("Parámetros")
        target_day = st.number_input("Día objetivo", min_value=1, max_value=60, value=35, step=1)
        monotonic = st.selectbox(
            "Suavizado / monotonicidad",
            options=["isotonic", "none"],
            index=0,
            help="Usa la misma opción que tu dashboard actual por defecto.",
        )
        st.markdown("---")
        st.write("Modelo esperado:", DEFAULT_MODEL)
        st.write("Existe:", os.path.exists(DEFAULT_MODEL))

    tab1, tab2, tab3 = st.tabs(["Manual", "Subir archivo", "Plantilla"])

    with tab1:
        st.write("Ingresa una mini historia del lote. Lo ideal es usar edades 7, 14, 21, 28 y el último día disponible.")
        base_df = make_default_history()
        edited = st.data_editor(
            base_df,
            num_rows="dynamic",
            use_container_width=True,
            key="manual_history_editor",
        )

        if st.button("Predecir con historia manual", type="primary"):
            errors = validate_history(edited)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                try:
                    hist_clean, result = run_prediction(edited, int(target_day), monotonic)
                    render_result(hist_clean, result, int(target_day))
                except Exception as e:
                    st.error(f"Error ejecutando el modelo: {e}")

    with tab2:
        st.write("Sube un Excel o CSV con al menos: Edad, PesoFinal y EstadoLote. Mientras más columnas reales tenga, más fiel será al flujo actual.")
        up = st.file_uploader("Archivo historial", type=["xlsx", "xls", "csv"])
        if up is not None:
            try:
                if up.name.lower().endswith(".csv"):
                    df_up = pd.read_csv(up)
                else:
                    df_up = pd.read_excel(up)
                st.dataframe(df_up.head(20), use_container_width=True)

                if st.button("Predecir con archivo", type="primary"):
                    errors = validate_history(df_up)
                    if errors:
                        for e in errors:
                            st.error(e)
                    else:
                        try:
                            hist_clean, result = run_prediction(df_up, int(target_day), monotonic)
                            render_result(hist_clean, result, int(target_day))
                        except Exception as e:
                            st.error(f"Error ejecutando el modelo: {e}")
            except Exception as e:
                st.error(f"No pude leer el archivo: {e}")

    with tab3:
        tpl = build_template()
        st.write("Esta es una plantilla base para llenar y luego usar en la pestaña de carga.")
        st.dataframe(tpl, use_container_width=True)
        csv_bytes = tpl.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Descargar plantilla CSV",
            data=csv_bytes,
            file_name="plantilla_predictor_lote.csv",
            mime="text/csv",
        )

        st.markdown(
            """
**Columnas mínimas obligatorias**
- `Edad`
- `PesoFinal`
- `EstadoLote`

**Columnas recomendadas**
- `LoteCompleto`
- `ZonaNombre`
- `TipoStd`
- `Quintil`
- `ReproductoraStd`
- `AvesVivas`
- `AlimAcumKg`
- `CostoAcum`
- `PrecioKg`
- `PrecioKgRealDia`
            """
        )


if __name__ == "__main__":
    main()
