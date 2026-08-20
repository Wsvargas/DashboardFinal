"""
Model Predictor — PRONACA Dashboard v16
========================================
Usa modelo CatBoost de curva futura.

Arquitectura CORRECTA (no iterativa):
  - Input : snapshot del lote HOY + día objetivo
  - Output: delta de peso predicho para cada día futuro
  - Una sola llamada batch para toda la curva

El modelo predice DELTA (ganancia de peso desde hoy),
no el peso absoluto. Se construye una fila por cada día
objetivo y se hace una predicción batch de toda la curva.

Uso:
  predictor = cargar_predictor("models/modelo_curva_futura_catboost.joblib")
  res = predictor.proyectar_curva(hist_lote=df, target_edad=35)
  if not res["error"]:
      df_curva = res["df"]   # columnas: Dia, Peso_pred_kg
"""

import os
import json
import numpy as np
import pandas as pd
import joblib
from datetime import datetime
from typing import Any, Dict, Optional


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def _stage_from_age(age: int) -> int:
    """Etapa biológica: 1=inicio, 2=crecimiento, 3=pre-acabado, 0=acabado."""
    a = int(age)
    if 1 <= a <= 14:  return 1
    if 15 <= a <= 28: return 2
    if 29 <= a <= 35: return 3
    return 0


def _season_features(dt: Optional[datetime] = None) -> Dict[str, int]:
    """Deriva trimestre e Invierno desde una fecha (Ecuador: rainy=Nov-Apr)."""
    if dt is None:
        dt = datetime.today()
    m = dt.month
    return {
        "T1":      1 if m in (1, 2, 3)   else 0,
        "T2":      1 if m in (4, 5, 6)   else 0,
        "T3":      1 if m in (7, 8, 9)   else 0,
        "T4":      1 if m in (10, 11, 12) else 0,
        "Invierno": 1 if m in (11, 12, 1, 2, 3, 4) else 0,
    }


def _add_engineered(df: pd.DataFrame) -> pd.DataFrame:
    """Feature engineering que el modelo espera en inferencia."""
    df = df.copy()
    df["Edad_actual2"]          = df["Edad_actual"]    ** 2
    df["Edad_objetivo2"]        = df["Edad_objetivo"]  ** 2
    df["Horizonte_dias2"]       = df["Horizonte_dias"] ** 2
    df["Peso_actual_x_Horizonte"] = df["Peso_actual"]   * df["Horizonte_dias"]
    df["Edad_actual_x_Horizonte"] = df["Edad_actual"]   * df["Horizonte_dias"]
    if "Aves Netas" in df.columns:
        df["Aves_Netas_x_Horizonte"] = (
            pd.to_numeric(df["Aves Netas"], errors="coerce") * df["Horizonte_dias"]
        )
    return df


def _preprocess(df: pd.DataFrame, artifact: Dict, feature_cols: list) -> pd.DataFrame:
    """Aplica imputación de medianas y encoding según el artefacto de entrenamiento."""
    cat_cols     = artifact.get("cat_cols", [])
    numeric_cols = artifact.get("numeric_cols", [])
    medians      = artifact.get("medians", {})

    df = df.copy()

    for c in cat_cols:
        if c not in df.columns:
            df[c] = "MISSING"
        df[c] = (
            df[c].fillna("MISSING")
                 .astype(str)
                 .replace({"nan": "MISSING", "None": "MISSING", "<NA>": "MISSING"})
        )

    for c in numeric_cols:
        if c not in df.columns:
            df[c] = medians.get(c, 0.0)
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(medians.get(c, 0.0))

    # Garantizar que todas las columnas del modelo existan
    for c in feature_cols:
        if c not in df.columns:
            df[c] = medians.get(c, 0.0)

    return df[feature_cols]


# ──────────────────────────────────────────────────────────────
# CLASE PRINCIPAL
# ──────────────────────────────────────────────────────────────

class Predictor:
    """
    Encapsula el modelo CatBoost de curva futura.

    Attributes:
        model            : CatBoostRegressor cargado
        feature_cols     : lista de columnas que el modelo espera
        current_snapshot_cols : columnas del estado actual del lote
        prep_artifact    : artefacto de preprocesamiento (medianas, encoders)
        max_edad         : día máximo de predicción
    """

    def __init__(self, model_path: str):
        self.model_path  = model_path
        self.model       = None
        self.model_q10   = None
        self.model_q90   = None
        self.feature_cols         = []
        self.current_snapshot_cols = []
        self.prep_artifact        = {}
        self.max_edad             = 44

        if not os.path.exists(model_path):
            print(f"[WARN] Modelo no encontrado: {model_path}")
            return

        try:
            package = joblib.load(model_path)
            self.model                 = package["model"]
            self.model_q10             = package.get("model_q10")
            self.model_q90             = package.get("model_q90")
            self.feature_cols          = package["feature_cols"]
            self.current_snapshot_cols = package.get("current_snapshot_cols", [])
            self.prep_artifact         = package.get("prep_artifact", {})
            banda = " + banda q10-q90" if self.model_q10 is not None else ""
            print(f"[OK] Modelo CatBoost cargado - {len(self.feature_cols)} features{banda}")
        except Exception as e:
            print(f"[ERROR] Error cargando modelo: {e}")
            self.model = None

    # ── Construcción del snapshot ──────────────────────────────
    def _snapshot_from_hist(self, hist_lote: pd.DataFrame) -> Dict[str, Any]:
        """
        Extrae las features del estado actual del lote.
        Soporta tanto el modelo externo (PRONACA 2) como el modelo
        reentrenado con el ETL propio (nombres distintos).
        """
        ultimo = hist_lote.iloc[-1]

        def safe(col, default=0.0):
            v = ultimo.get(col, default)
            try:
                return float(v) if pd.notna(v) else default
            except (TypeError, ValueError):
                return default

        def safe_str(col, *fallbacks, default="MISSING"):
            for c in (col, *fallbacks):
                v = ultimo.get(c)
                if v is not None and pd.notna(v) and str(v).strip() not in ("nan", "None", ""):
                    return str(v).strip()
            return default

        snap = {}

        # ── Zona / tipo ───────────────────────────────────────
        zona = str(ultimo.get("ZonaNombre", "")).upper()
        snap["BUCAY"]         = 1 if "BUCAY" in zona else 0
        snap["Granja Propia"] = 1 if str(ultimo.get("TipoStd", "")).upper() == "PROPIA" else 0
        snap["Granja_Propia"] = snap["Granja Propia"]   # nombre modelo ETL propio

        # ── Reproductora / Guarda ─────────────────────────────
        repro = safe_str("ReproductoraStd", "Reproductora", default="MISSING")
        snap["Reproductora"]               = repro
        snap["Guarda"]                     = safe_str("Guarda")
        snap["ponderado_edad_reproductora"] = safe("ponderado_edad_reproductora")
        snap["ponderado_dias_guarda"]       = safe("ponderado_dias_guarda")

        # ── Aves ──────────────────────────────────────────────
        aves_vivas = safe("AvesVivas")
        snap["Aves Netas"]   = aves_vivas        # modelo externo
        snap["Aves_Netas"]   = aves_vivas        # modelo ETL propio
        snap["Aves_Iniciales"] = safe("Aves_Iniciales", aves_vivas)

        # ── Mortalidad ────────────────────────────────────────
        mort_ac = safe("MortalidadDescarte_Acumulado")
        snap["MORTALIDAD + DESCARTE"] = mort_ac  # modelo externo
        snap["mort_acumulado"]        = mort_ac  # modelo ETL propio
        snap["mort_diario"]           = safe("MortalidadDescarte_Diario")

        # ── Alimento / FCR ────────────────────────────────────
        alim_ac = safe("AlimAcumKg")
        alim_d  = safe("_alim_dia")
        snap["alimento acumulado"]  = alim_ac    # modelo externo
        snap["alimento_acumulado"]  = alim_ac    # modelo ETL propio
        snap["alimento diario"]     = alim_d     # modelo externo
        snap["alimento_diario"]     = alim_d     # modelo ETL propio

        # FCR: primero desde datos calculados por data_loader, luego ETL directo
        fcr = safe("FCR_Cum")
        if fcr == 0.0:
            fcr = safe("conversio alimenticia")
        snap["FCR_actual"] = fcr

        # ── Quintil / Edad^2 ──────────────────────────────────
        snap["Quintil_Area_Crianza"] = safe_str("Quintil", default="Q3")
        snap["Edad^2"]               = safe("Edad") ** 2

        # ── Raza / densidad / incremento diario ───────────────
        snap["porcentaje_raza_RAP95"] = safe("porcentaje_raza_RAP95")
        snap["porcentaje_raza_C500SF"] = safe("porcentaje_raza_C500SF")
        snap["aves_m2"]    = safe("aves_m2")
        snap["Peso_diario"] = safe("Peso_diario")

        # ── Sexo / color (modelo externo, ausentes en ETL propio) ─
        snap["MACHO"]    = safe("MACHO",    0.0)
        snap["MIXTO"]    = safe("MIXTO",    0.0)
        snap["AMARILLO"] = safe("AMARILLO", 0.0)

        # ── Estacionalidad ────────────────────────────────────
        snap.update(_season_features())

        # ── Features restantes → NaN (prep_artifact usa medianas) ─
        for c in self.current_snapshot_cols:
            if c not in snap:
                snap[c] = np.nan

        return snap

    # ── Proyección principal ───────────────────────────────────
    def proyectar_curva(
        self,
        hist_lote: pd.DataFrame,
        target_edad: int = 35,
        **_ignored,   # tolera parametros legacy (ej. enforce_monotonic)
    ) -> Dict[str, Any]:
        """
        Proyecta la curva de peso desde el día actual hasta target_edad.

        Una sola llamada batch al modelo (no iterativa):
          Para cada día objetivo d en [edad_actual+1 .. target_edad]:
            input  = (Edad_actual=hoy, Edad_objetivo=d, Horizonte=d-hoy, snapshot)
            output = delta_peso predicho para el día d

          Peso_d = Peso_actual + delta_d  (con restricción monotónica)

        Returns dict con:
          error       : None o mensaje de error
          df          : DataFrame con columnas [Dia, Peso_pred_kg]
          edad_actual : int
          peso_d35    : float — peso predicho en target_edad
        """
        _ERR = {
            "error": None, "df": pd.DataFrame(), "edad_actual": None,
            "peso_d35": None, "peso_d35_lo": None, "peso_d35_hi": None,
        }

        if self.model is None:
            return {**_ERR, "error": "Modelo no cargado"}

        if hist_lote is None or hist_lote.empty:
            return {**_ERR, "error": "Historial vacío"}

        hist = hist_lote.sort_values("Edad").copy()
        hist = hist[hist["PesoFinal"].notna() & (hist["PesoFinal"] > 0)]
        if hist.empty:
            return {**_ERR, "error": "Sin registros de peso válidos"}

        try:
            ultimo       = hist.iloc[-1]
            edad_actual  = int(float(ultimo["Edad"]))
            peso_actual  = float(ultimo["PesoFinal"])
            target_edad  = max(target_edad, edad_actual)
            target_edad  = min(target_edad, self.max_edad)

            snap = self._snapshot_from_hist(hist)

            # ── Construir batch: una fila por día objetivo ────────
            rows = []
            for age_obj in range(edad_actual + 1, target_edad + 1):
                rec = {
                    "Edad_actual":    edad_actual,
                    "Edad_objetivo":  age_obj,
                    "Horizonte_dias": age_obj - edad_actual,
                    "Peso_actual":    peso_actual,
                    "etapa_actual":   _stage_from_age(edad_actual),
                    "etapa_objetivo": _stage_from_age(age_obj),
                }
                for c in self.current_snapshot_cols:
                    rec[c] = snap.get(c, np.nan)
                rows.append(rec)

            # Si ya está en o pasó el día objetivo
            if not rows:
                df_out = pd.DataFrame({"Dia": [edad_actual], "Peso_pred_kg": [peso_actual]})
                return {
                    "error": None, "df": df_out, "edad_actual": edad_actual,
                    "peso_d35": peso_actual, "peso_d35_lo": None, "peso_d35_hi": None,
                }

            curve_df = pd.DataFrame(rows)
            curve_df = _add_engineered(curve_df)
            X        = _preprocess(curve_df, self.prep_artifact, self.feature_cols)

            # ── Predicción de deltas ──────────────────────────────
            pred_delta   = self.model.predict(X)
            pred_weights = peso_actual + np.array(pred_delta, dtype=float)

            # No puede bajar del peso actual, y debe ser monotónica
            pred_weights = np.maximum(pred_weights, peso_actual)
            pred_weights = np.maximum.accumulate(pred_weights)

            # ── Suavizado PCHIP para visualización ────────────────
            # Los árboles producen escalones; interpolamos sobre puntos
            # clave cada 7 días + inicio + fin para obtener curva suave.
            # El valor final (peso_d35) se preserva exactamente.
            dias_pred = np.array(range(edad_actual + 1, target_edad + 1))
            if len(dias_pred) > 4:
                from scipy.interpolate import PchipInterpolator
                # Anclas: día actual + cada 7 días + último día
                anclas_idx = (
                    [0]
                    + [i for i, d in enumerate(dias_pred) if (d - edad_actual) % 7 == 0]
                )
                if (len(dias_pred) - 1) not in anclas_idx:
                    anclas_idx.append(len(dias_pred) - 1)
                anclas_idx = sorted(set(anclas_idx))
                dias_ancla  = dias_pred[anclas_idx]
                pesos_ancla = pred_weights[anclas_idx]
                interp = PchipInterpolator(dias_ancla, pesos_ancla, extrapolate=False)
                pred_smooth = interp(dias_pred)
                # Garantizar monotónico y ≥ peso_actual tras suavizado
                pred_smooth = np.maximum(pred_smooth, peso_actual)
                pred_smooth = np.maximum.accumulate(pred_smooth)
                # Fijar el último punto exactamente al predicho
                pred_smooth[-1] = pred_weights[-1]
                pred_weights = pred_smooth

            # ── Banda de predicción q10-q90 (si el modelo la trae) ─
            banda_lo = banda_hi = None
            if self.model_q10 is not None and self.model_q90 is not None:
                try:
                    w_q10 = peso_actual + np.array(self.model_q10.predict(X), dtype=float)
                    w_q90 = peso_actual + np.array(self.model_q90.predict(X), dtype=float)

                    banda_lo = np.minimum(w_q10, w_q90)
                    banda_hi = np.maximum(w_q10, w_q90)

                    # Coherencia biológica y con la curva central
                    banda_lo = np.maximum(banda_lo, peso_actual)
                    banda_lo = np.maximum.accumulate(banda_lo)
                    banda_hi = np.maximum.accumulate(np.maximum(banda_hi, peso_actual))
                    banda_lo = np.minimum(banda_lo, pred_weights)
                    banda_hi = np.maximum(banda_hi, pred_weights)
                except Exception:
                    banda_lo = banda_hi = None

            # ── Resultado incluyendo día actual ───────────────────
            dias   = [edad_actual] + list(range(edad_actual + 1, target_edad + 1))
            pesos  = [peso_actual] + list(pred_weights)

            df_out = pd.DataFrame({"Dia": dias, "Peso_pred_kg": pesos})
            df_out["Edad"]          = df_out["Dia"]
            df_out["Peso_pred_g"]   = (df_out["Peso_pred_kg"] * 1000).round(0).astype(int)

            peso_final = float(pred_weights[-1]) if len(pred_weights) > 0 else peso_actual
            peso_lo = peso_hi = None

            if banda_lo is not None:
                df_out["Peso_pred_q10_kg"] = [peso_actual] + list(banda_lo)
                df_out["Peso_pred_q90_kg"] = [peso_actual] + list(banda_hi)
                peso_lo = float(banda_lo[-1])
                peso_hi = float(banda_hi[-1])

            return {
                "error":       None,
                "df":          df_out,
                "edad_actual": edad_actual,
                "peso_d35":    peso_final,
                "peso_d35_lo": peso_lo,
                "peso_d35_hi": peso_hi,
            }

        except Exception as e:
            import traceback
            return {**_ERR, "error": f"Error en proyección: {e}\n{traceback.format_exc()}"}


# ──────────────────────────────────────────────────────────────
# FACTORY
# ──────────────────────────────────────────────────────────────

def cargar_predictor(ruta: str) -> Predictor:
    return Predictor(ruta)
