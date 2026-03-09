# ──────────────────────────────────────────────────────────────
# helpers.py · PRONACA Dashboard v15
# Funciones utilitarias: formato, parsing, etapas, debug, modelo
# ──────────────────────────────────────────────────────────────
import os
from textwrap import dedent

import numpy as np
import pandas as pd
import streamlit as st


# ── Render HTML ───────────────────────────────────────────────
def md(html: str):
    st.markdown(dedent(html), unsafe_allow_html=True)


# ── Filesystem ───────────────────────────────────────────────
def _file_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


# ── Etapa por edad ───────────────────────────────────────────
def get_etapa(edad, estado_lote=None):
    try:
        estado = str(estado_lote).upper().strip() if estado_lote is not None else ""

        # Regla de negocio:
        # si el lote ya está cerrado, clasificarlo como ACABADO
        if estado == "CERRADO":
            return "ACABADO (36+)"

        e = int(edad)
        if e <= 14:
            return "INICIO (1-14)"
        if e <= 28:
            return "CRECIMIENTO (15-28)"
        if e <= 35:
            return "PRE-ACABADO (29-35)"
        return "ACABADO (36+)"
    except Exception:
        return "INICIO (1-14)"


# ── Formato numérico ─────────────────────────────────────────
def fmt_num(x, dec=2, prefix="", suffix=""):
    try:
        if x is None or pd.isna(x): return "—"
        v = float(x)
        if dec == 0: return f"{prefix}{int(round(v)):,}{suffix}"
        return f"{prefix}{v:,.{dec}f}{suffix}"
    except Exception:
        return "—"


# ── Parsing numérico tolerante (formatos ES/EC) ───────────────
def parse_num_series(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s
    ss = s.astype(str).str.strip()
    ss = ss.str.replace("\u00A0", "", regex=False).str.replace(" ", "", regex=False)
    ss = ss.str.replace(r"[^0-9,\.\-]", "", regex=True)
    has_dot   = ss.str.contains(r"\.", regex=True)
    has_comma = ss.str.contains(",", regex=False)
    mask = has_dot & has_comma
    ss.loc[mask]  = ss.loc[mask].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    ss.loc[~mask] = ss.loc[~mask].str.replace(",", ".", regex=False)
    return pd.to_numeric(ss, errors="coerce")


# ── Detección flexible de columnas ───────────────────────────
def pick_first_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


# ── Código corto de lote ──────────────────────────────────────
def extract_lote_codigo(lote_completo: str) -> str:
    parts = str(lote_completo).split("-")
    if len(parts) >= 3:
        return f"{parts[1]}-{parts[2]}"
    return str(lote_completo)


# ── Debug por consola ─────────────────────────────────────────
def _console_df_info(df: pd.DataFrame, nombre: str, cols: list | None = None, head: int = 8):
    try:
        print("\n" + "=" * 90)
        print(f"[DEBUG] {nombre}")
        print(f"  shape: {df.shape}")
        if cols:
            cols_ok = [c for c in cols if c in df.columns]
            print(f"  cols: {cols_ok}")
        if len(df) > 0:
            subset = df[cols_ok] if cols else df
            print(subset.head(head).to_string(index=False))
        print("=" * 90 + "\n")
    except Exception as e:
        print(f"[DEBUG] Error imprimiendo df '{nombre}': {e}")


# ── Reset de predicción al cambiar de lote ───────────────────
def _reset_pred_if_lote_changed(lote_sel: str):
    if st.session_state.get("lote_anterior") != lote_sel:
        st.session_state["prediccion_resultado"] = None
        st.session_state["lote_anterior"] = lote_sel
        print(f"[DEBUG] Lote cambió -> reset prediccion_resultado. lote_anterior={lote_sel}")


# ── Limpieza de historial para el modelo ML ──────────────────
def _limpiar_historial_para_modelo(hist: pd.DataFrame) -> pd.DataFrame:
    h = hist.copy()

    # Edad
    h["Edad"] = pd.to_numeric(h.get("Edad"), errors="coerce")
    h = h[h["Edad"].notna()].copy()
    h["Edad"] = h["Edad"].astype(int)

    # PesoFinal
    h["PesoFinal"] = pd.to_numeric(h.get("PesoFinal"), errors="coerce")
    h = h[h["PesoFinal"].notna()].copy()
    h = h[h["PesoFinal"] > 0].copy()   # fuera ceros

    h = h.sort_values("Edad").copy()

    # Si ABIERTO: múltiplos de 7 + último registro válido
    estado = str(
        h["EstadoLote"].iloc[-1] if "EstadoLote" in h.columns else "ABIERTO"
    ).upper()

    if estado != "CERRADO":
        h7       = h[h["Edad"] % 7 == 0].copy()
        last_row = h.iloc[[-1]].copy()
        h = pd.concat([h7, last_row], ignore_index=True) if not h7.empty else last_row
        h = h.drop_duplicates(subset=["Edad"], keep="last").copy()

    h = h.drop_duplicates(subset=["Edad"], keep="last").copy()
    return h
