#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reentrenamiento del modelo CatBoost de curva futura — PRONACA
==============================================================
Entrena con el historico acumulado (etl/data/historico_produccion.xlsx)
usando TODAS las variables del ETL propio (no las del modelo externo PRONACA 2).

Feature set propio del ETL:
  - Horizonte de tiempo (dia actual, dia objetivo, horizonte)
  - Estado del lote hoy: peso, FCR, alimento, mortalidad, aves
  - Atributos del lote: zona, tipo, reproductora, guarda, quintil, raza
  - Estacionalidad: T1-T4, Invierno
  - Features engineered: cuadraticos + interacciones

Uso:
  cd <raiz del proyecto>
  python models/retrain_model.py

Requisitos: pip install catboost scikit-learn joblib pandas openpyxl
"""

import os, json, warnings
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings("ignore")

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
PROJECT         = os.path.dirname(BASE_DIR)
HIST_FILE       = os.path.join(PROJECT, "etl", "data", "historico_produccion.xlsx")
BASE_COMPLETA   = os.path.join(PROJECT, "catboost_info", "base COMPLETA.xlsx")
OUT_MODEL       = os.path.join(BASE_DIR, "modelo_curva_futura_catboost.joblib")
OUT_META        = os.path.join(BASE_DIR, "metadata_modelo.json")

CATBOOST_PARAMS = {
    "iterations":            1800,
    "depth":                 8,
    "learning_rate":         0.04,
    "l2_leaf_reg":           6,
    "bagging_temperature":   1.0,
    "random_strength":       1.5,
    "loss_function":         "RMSE",
    "eval_metric":           "RMSE",
    "random_seed":           42,
    "verbose":               100,
    "early_stopping_rounds": 80,
}

EDAD_MIN = 1
EDAD_MAX = 44

# ── Nombres de columnas ETL ───────────────────────────────────
# Mapeamos: nombre_en_ETL -> nombre_en_modelo
# Los nombres del modelo son los que usara _snapshot_from_hist
ETL_RENAME = {
    "Alimento_Acumulado":           "alimento_acumulado",
    "alimento_dia_kg":              "alimento_diario",
    "conversio alimenticia":        "FCR_actual",
    "MortalidadDescarte_Acumulado": "mort_acumulado",
    "MortalidadDescarte_Diario":    "mort_diario",
    "Aves_vivas":                   "Aves_Netas",
    "Aves_Iniciales":               "Aves_Iniciales",
    "TipoGranjero_Propia":          "Granja_Propia",
    "Quintil":                      "Quintil_Area_Crianza",
    "porcentaje_raza_RAP95":        "porcentaje_raza_RAP95",
    "porcentaje_raza_C500SF":       "porcentaje_raza_C500SF",
    "ponderado_edad_reproductora":  "ponderado_edad_reproductora",
    "ponderado_dias_guarda":        "ponderado_dias_guarda",
    "Reproductora":                 "Reproductora",
    "Guarda":                       "Guarda",
    "BUCAY":                        "BUCAY",
    "aves_m2":                      "aves_m2",
    "Peso_diario":                  "Peso_diario",
}

# Categoricas
CAT_COLS = ["Reproductora", "Guarda", "Quintil_Area_Crianza"]

# Features del snapshot (estado hoy, constantes por lote en cada par)
SNAPSHOT_FEATURES = [
    "Edad^2",
    "alimento_acumulado",
    "alimento_diario",
    "FCR_actual",           # FCR acumulado — muy predictivo
    "mort_acumulado",
    "mort_diario",          # tendencia mortalidad diaria
    "Aves_Netas",
    "Aves_Iniciales",       # tamano inicial del lote
    "BUCAY",
    "Granja_Propia",
    "Reproductora",
    "ponderado_edad_reproductora",
    "Guarda",
    "ponderado_dias_guarda",
    "porcentaje_raza_RAP95",
    "porcentaje_raza_C500SF",
    "aves_m2",          # densidad aves/m2 del galpon
    "Peso_diario",      # incremento de peso del ultimo dia
    "Quintil_Area_Crianza",
    "T1", "T2", "T3", "T4", "Invierno",
]

# Features del par (varian por dia objetivo)
PAIR_FEATURES = [
    "Edad_actual", "Edad_objetivo", "Horizonte_dias",
    "Peso_actual", "etapa_actual", "etapa_objetivo",
]

# Engineered (se calculan en add_engineered)
ENGINEERED = [
    "Edad_actual2", "Edad_objetivo2", "Horizonte_dias2",
    "Peso_actual_x_Horizonte", "Edad_actual_x_Horizonte",
    "Aves_Netas_x_Horizonte", "FCR_x_Horizonte",
]

FEATURE_COLS = PAIR_FEATURES + SNAPSHOT_FEATURES + ENGINEERED


# ──────────────────────────────────────────────────────────────
def _stage(age):
    a = int(age)
    if 1 <= a <= 14:  return 1
    if 15 <= a <= 28: return 2
    if 29 <= a <= 35: return 3
    return 0


def _season(dt):
    if pd.isna(dt):
        dt = datetime.today()
    m = int(pd.Timestamp(dt).month)
    return {
        "T1":       1 if m in (1, 2, 3)    else 0,
        "T2":       1 if m in (4, 5, 6)    else 0,
        "T3":       1 if m in (7, 8, 9)    else 0,
        "T4":       1 if m in (10, 11, 12) else 0,
        "Invierno": 1 if m in (11, 12, 1, 2, 3, 4) else 0,
    }


def add_engineered(df):
    df = df.copy()
    df["Edad_actual2"]            = df["Edad_actual"]    ** 2
    df["Edad_objetivo2"]          = df["Edad_objetivo"]  ** 2
    df["Horizonte_dias2"]         = df["Horizonte_dias"] ** 2
    df["Peso_actual_x_Horizonte"] = df["Peso_actual"]    * df["Horizonte_dias"]
    df["Edad_actual_x_Horizonte"] = df["Edad_actual"]    * df["Horizonte_dias"]
    df["Aves_Netas_x_Horizonte"]  = (
        pd.to_numeric(df.get("Aves_Netas"), errors="coerce").fillna(0)
        * df["Horizonte_dias"]
    )
    df["FCR_x_Horizonte"] = (
        pd.to_numeric(df.get("FCR_actual"), errors="coerce").fillna(0)
        * df["Horizonte_dias"]
    )
    return df


# ──────────────────────────────────────────────────────────────
# 1. CARGAR HISTORICO
# ──────────────────────────────────────────────────────────────
def _limpiar_df(df, fuente):
    """Filtra filas invalidas y renombra columnas al formato del modelo."""
    if "Cerrado" in df.columns:
        df = df[df["Cerrado"] == 1].copy()

    # Excluir filas sinteticas del ETL (peso interpolado, alimento copiado),
    # conservando la fila de edad de venta que ancla el Peso_Venta real.
    if "EsExtendido" in df.columns:
        es_ext = pd.to_numeric(df["EsExtendido"], errors="coerce").fillna(0) == 1
        if "Edad (venta)" in df.columns:
            edad_venta = pd.to_numeric(df["Edad (venta)"], errors="coerce")
            es_ancla = pd.to_numeric(df["Edad"], errors="coerce") == edad_venta
            n_drop = int((es_ext & ~es_ancla).sum())
            df = df[~es_ext | es_ancla].copy()
        else:
            n_drop = int(es_ext.sum())
            df = df[~es_ext].copy()
        if n_drop:
            print(f"   [{fuente}] {n_drop:,} filas extendidas (sinteticas) excluidas")

    df["Edad"]      = pd.to_numeric(df["Edad"],      errors="coerce")
    df["PesoFinal"] = pd.to_numeric(df["PesoFinal"], errors="coerce")
    df = df[
        df["PesoFinal"].notna() & (df["PesoFinal"] > 0) &
        df["Edad"].notna()      & df["Edad"].between(EDAD_MIN, EDAD_MAX)
    ].copy()
    df = df.rename(columns=ETL_RENAME)
    print(f"   [{fuente}] {df['LoteCompleto'].nunique()} lotes | {len(df):,} registros")
    return df


def cargar_historico():
    print(f"[1/5] Cargando historico...")
    fuentes = []

    # ── Fuente 1: base COMPLETA (historico anual completo) ────
    if os.path.exists(BASE_COMPLETA):
        df_base = pd.read_excel(BASE_COMPLETA)
        fuentes.append(_limpiar_df(df_base, "base COMPLETA"))
    else:
        print(f"   [WARN] base COMPLETA no encontrada: {BASE_COMPLETA}")

    # ── Fuente 2: historico ETL (lotes nuevos que van cerrando) ─
    if os.path.exists(HIST_FILE):
        df_hist = pd.read_excel(HIST_FILE, sheet_name="historico")
        df_hist = _limpiar_df(df_hist, "historico ETL")
        fuentes.append(df_hist)
    else:
        print(f"   [WARN] historico ETL no encontrado: {HIST_FILE}")

    if not fuentes:
        raise FileNotFoundError("No se encontro ninguna fuente de datos historicos.")

    # ── Combinar y deduplicar por LoteCompleto + Edad ─────────
    df = pd.concat(fuentes, ignore_index=True)
    df = df.drop_duplicates(subset=["LoteCompleto", "Edad"], keep="last")
    df = df.sort_values(["LoteCompleto", "Edad"]).reset_index(drop=True)

    print(f"   Total combinado: {df['LoteCompleto'].nunique()} lotes | {len(df):,} registros")
    return df


# ──────────────────────────────────────────────────────────────
# 2. CONSTRUIR PARES (snapshot semanal -> dia objetivo)
# ──────────────────────────────────────────────────────────────
def construir_pares(df):
    print("[2/5] Construyendo pares de entrenamiento (snapshots semanales)...")

    # Un registro por edad (ultimo del dia si hay duplicados)
    df_d = (
        df.sort_values(["LoteCompleto", "Edad"])
          .groupby(["LoteCompleto", "Edad"], as_index=False)
          .last()
    )

    # Solo dias multiples de 7 + ultimo dia de cada lote
    mask_sem = df_d["Edad"] % 7 == 0
    last_rows = df_d.groupby("LoteCompleto").tail(1)
    df_snap = (
        pd.concat([df_d[mask_sem], last_rows], ignore_index=True)
          .drop_duplicates(subset=["LoteCompleto", "Edad"], keep="last")
          .sort_values(["LoteCompleto", "Edad"])
          .reset_index(drop=True)
    )

    rows = []
    for lote, lote_df in df_snap.groupby("LoteCompleto"):
        lote_df = lote_df.sort_values("Edad").reset_index(drop=True)
        pesos   = df_d.loc[df_d["LoteCompleto"] == lote, ["Edad", "PesoFinal"]] \
                      .sort_values("Edad").set_index("Edad")["PesoFinal"]

        for _, row_snap in lote_df.iterrows():
            edad_snap = int(row_snap["Edad"])
            peso_snap = float(row_snap["PesoFinal"])
            fecha_ref = row_snap.get("FechaTransaccion")
            seas      = _season(fecha_ref)

            # Dias objetivo: todos los dias posteriores del lote
            dias_futuros = [e for e in pesos.index if e > edad_snap]
            for edad_obj in dias_futuros:
                delta = float(pesos[edad_obj]) - peso_snap
                if delta < 0:
                    continue

                rec = {
                    # Par (varia)
                    "LoteCompleto":   lote,
                    "FechaRef":       fecha_ref,
                    "Edad_actual":    edad_snap,
                    "Edad_objetivo":  int(edad_obj),
                    "Horizonte_dias": int(edad_obj) - edad_snap,
                    "Peso_actual":    peso_snap,
                    "etapa_actual":   _stage(edad_snap),
                    "etapa_objetivo": _stage(edad_obj),
                    # Snapshot (constante para este lote en este dia)
                    "Edad^2":         float(edad_snap) ** 2,
                }
                # Copiar todas las features del snapshot
                for feat in SNAPSHOT_FEATURES:
                    if feat in ("T1","T2","T3","T4","Invierno","Edad^2"):
                        continue
                    rec[feat] = row_snap.get(feat, np.nan)
                rec.update(seas)
                rec["delta_peso"] = delta
                rows.append(rec)

    df_pairs = pd.DataFrame(rows)
    print(f"   {len(df_pairs):,} pares generados de {df_snap['LoteCompleto'].nunique()} lotes")
    return df_pairs


# ──────────────────────────────────────────────────────────────
# 3. PREPROCESAR
# ──────────────────────────────────────────────────────────────
def preprocesar(df_pairs):
    print("[3/5] Preprocesando features...")

    df_pairs = add_engineered(df_pairs)

    numeric_cols = [c for c in FEATURE_COLS if c not in CAT_COLS]

    # Categoricas
    for c in CAT_COLS:
        if c not in df_pairs.columns:
            df_pairs[c] = "MISSING"
        df_pairs[c] = (
            df_pairs[c].fillna("MISSING").astype(str)
                       .replace({"nan": "MISSING", "None": "MISSING", "<NA>": "MISSING"})
        )

    # Numericas + medianas para inferencia
    medians = {}
    for c in numeric_cols:
        if c not in df_pairs.columns:
            df_pairs[c] = np.nan
        df_pairs[c] = pd.to_numeric(df_pairs[c], errors="coerce")
        medians[c] = float(df_pairs[c].median()) if df_pairs[c].notna().any() else 0.0
        df_pairs[c] = df_pairs[c].fillna(medians[c])

    # Garantizar columnas
    for c in FEATURE_COLS:
        if c not in df_pairs.columns:
            df_pairs[c] = medians.get(c, 0.0)

    prep_artifact = {
        "cat_cols":     CAT_COLS,
        "numeric_cols": numeric_cols,
        "medians":      medians,
    }
    return df_pairs, prep_artifact


# ──────────────────────────────────────────────────────────────
# 4. ENTRENAR
# ──────────────────────────────────────────────────────────────
def _split_temporal(df_pairs):
    """
    Test = ultimos 15% de lotes por fecha de cierre (cronologico).
    Replica la condicion real de produccion: predecir lotes futuros.
    Fallback a GroupShuffleSplit si no hay fechas.
    """
    fechas_lote = (
        df_pairs.assign(_f=pd.to_datetime(df_pairs["FechaRef"], errors="coerce"))
        .groupby("LoteCompleto")["_f"].max()
    )

    if fechas_lote.notna().sum() < fechas_lote.size * 0.5:
        print("   [WARN] Fechas insuficientes -> split aleatorio por lote")
        spl = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
        tr_idx, te_idx = next(spl.split(
            df_pairs, groups=df_pairs["LoteCompleto"].values
        ))
        return np.array(tr_idx), np.array(te_idx), "aleatorio_por_lote"

    fechas_lote = fechas_lote.sort_values()
    n_test      = max(1, int(len(fechas_lote) * 0.15))
    lotes_test  = set(fechas_lote.tail(n_test).index)

    mask_test = df_pairs["LoteCompleto"].isin(lotes_test).values
    te_idx = np.where(mask_test)[0]
    tr_idx = np.where(~mask_test)[0]

    f_corte = fechas_lote.tail(n_test).min()
    print(f"   Split temporal: test = {len(lotes_test)} lotes cerrados desde {f_corte:%Y-%m-%d}")
    return tr_idx, te_idx, "temporal_por_lote"


def _reportar_mae_por_horizonte(y_true, y_pred, horizontes):
    """MAE desglosado por horizonte de prediccion (dias hacia adelante)."""
    bins = [(1, 7), (8, 14), (15, 21), (22, 44)]
    print("\n   MAE por horizonte de prediccion:")
    out = {}
    for lo, hi in bins:
        mask = (horizontes >= lo) & (horizontes <= hi)
        if mask.sum() == 0:
            continue
        mae_h = mean_absolute_error(y_true[mask], y_pred[mask])
        out[f"h{lo}-{hi}"] = {"MAE": float(mae_h), "n": int(mask.sum())}
        print(f"     {lo:>2}-{hi:<2} dias  ->  MAE = {mae_h*1000:6.1f} g   ({mask.sum():,} pares)")
    return out


def entrenar(df_pairs):
    try:
        from catboost import CatBoostRegressor, Pool
    except ImportError:
        raise ImportError("Instala catboost: pip install catboost")

    print("[4/5] Entrenando CatBoost...")

    X      = df_pairs[FEATURE_COLS].copy()
    y      = df_pairs["delta_peso"].values
    groups = df_pairs["LoteCompleto"].values

    cat_idxs = [FEATURE_COLS.index(c) for c in CAT_COLS if c in FEATURE_COLS]

    # ── Split temporal: test = lotes mas recientes ────────────
    tr_idx, te_idx, split_tipo = _split_temporal(df_pairs)

    # Validacion interna: aleatoria por lote dentro del train
    spl2 = GroupShuffleSplit(n_splits=1, test_size=0.12, random_state=0)
    g_tr = groups[tr_idx]
    tr2_rel, vl_rel = next(spl2.split(X.iloc[tr_idx], y[tr_idx], g_tr))
    tr2_idx = tr_idx[tr2_rel]
    vl_idx  = tr_idx[vl_rel]

    pool_tr = Pool(X.iloc[tr2_idx], y[tr2_idx], cat_features=cat_idxs)
    pool_vl = Pool(X.iloc[vl_idx],  y[vl_idx],  cat_features=cat_idxs)
    pool_te = Pool(X.iloc[te_idx],  cat_features=cat_idxs)

    # ── Modelo principal (mediana del delta) ──────────────────
    model = CatBoostRegressor(**CATBOOST_PARAMS)
    model.fit(pool_tr, eval_set=pool_vl, use_best_model=True)

    pred_te = model.predict(pool_te)
    mae  = mean_absolute_error(y[te_idx], pred_te)
    rmse = np.sqrt(mean_squared_error(y[te_idx], pred_te))
    r2   = r2_score(y[te_idx], pred_te)

    print(f"\n   Test ({split_tipo}) -> MAE={mae*1000:.1f}g  RMSE={rmse*1000:.1f}g  R2={r2:.4f}")
    print(f"   Pares train/test: {len(tr2_idx)+len(vl_idx):,} / {len(te_idx):,}")

    # ── MAE por horizonte (saber desde cuando confiar) ────────
    horizontes_te = df_pairs["Horizonte_dias"].values[te_idx]
    mae_horizonte = _reportar_mae_por_horizonte(y[te_idx], pred_te, horizontes_te)

    # ── Modelos de cuantiles (banda de prediccion 10%-90%) ────
    modelos_q = {}
    cobertura = None
    q_params_base = {
        k: v for k, v in CATBOOST_PARAMS.items()
        if k not in ("loss_function", "eval_metric")
    }
    for alpha, nombre in [(0.10, "q10"), (0.90, "q90")]:
        print(f"\n   Entrenando cuantil {nombre} (alpha={alpha})...")
        q_params = {
            **q_params_base,
            "loss_function": f"Quantile:alpha={alpha}",
            "eval_metric":   f"Quantile:alpha={alpha}",
            "verbose":       0,
        }
        m_q = CatBoostRegressor(**q_params)
        m_q.fit(pool_tr, eval_set=pool_vl, use_best_model=True)
        modelos_q[nombre] = m_q

    # Cobertura empirica de la banda en el test
    p10 = modelos_q["q10"].predict(pool_te)
    p90 = modelos_q["q90"].predict(pool_te)
    lo  = np.minimum(p10, p90)
    hi  = np.maximum(p10, p90)
    cobertura = float(np.mean((y[te_idx] >= lo) & (y[te_idx] <= hi)))
    print(f"\n   Banda q10-q90: cobertura empirica en test = {cobertura*100:.1f}% (esperado ~80%)")

    # Feature importance
    print("\n   Top 15 features:")
    imps = model.get_feature_importance()
    fi = sorted(zip(FEATURE_COLS, imps), key=lambda x: -x[1])
    for name, imp in fi[:15]:
        bar = "#" * int(imp / max(imps) * 25)
        print(f"     {name:<40} {imp:6.2f}  {bar}")

    metrics = {
        "MAE": mae, "RMSE": rmse, "R2": r2,
        "split": split_tipo,
        "MAE_por_horizonte": mae_horizonte,
        "cobertura_banda_q10_q90": cobertura,
        "n_train": int(len(tr2_idx) + len(vl_idx)),
        "n_test":  int(len(te_idx)),
        "best_iteration": int(model.best_iteration_),
    }
    return model, modelos_q, metrics


# ──────────────────────────────────────────────────────────────
# 5. GUARDAR
# ──────────────────────────────────────────────────────────────
def guardar(model, modelos_q, prep_artifact, metrics, df_pairs):
    print("[5/5] Guardando modelo...")

    package = {
        "model":                 model,
        "model_q10":             modelos_q.get("q10"),
        "model_q90":             modelos_q.get("q90"),
        "feature_cols":          FEATURE_COLS,
        "current_snapshot_cols": SNAPSHOT_FEATURES,
        "prep_artifact":         prep_artifact,
    }
    joblib.dump(package, OUT_MODEL, compress=3)
    size = os.path.getsize(OUT_MODEL) / 1_048_576
    print(f"   Guardado: {OUT_MODEL}  ({size:.1f} MB)")

    meta = {
        "trained_at":            datetime.now().isoformat(),
        "n_lotes":               int(df_pairs["LoteCompleto"].nunique()),
        "n_pares":               int(len(df_pairs)),
        "feature_cols":          FEATURE_COLS,
        "snapshot_features":     SNAPSHOT_FEATURES,
        "cat_cols":              CAT_COLS,
        "etl_rename_map":        ETL_RENAME,
        "test_metrics":          metrics,
        "best_iteration":        metrics.get("best_iteration"),
    }
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"   Metadatos: {OUT_META}")


# ──────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("REENTRENAMIENTO CatBoost — PRONACA (feature set ETL propio)")
    print(f"Fecha: {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 65)

    df_hist  = cargar_historico()
    df_pairs = construir_pares(df_hist)

    if len(df_pairs) < 500:
        raise ValueError(
            f"Solo {len(df_pairs)} pares. Necesitas mas lotes cerrados en el historico."
        )

    df_pairs, prep_art        = preprocesar(df_pairs)
    model, modelos_q, metrics = entrenar(df_pairs)
    guardar(model, modelos_q, prep_art, metrics, df_pairs)

    print(f"\nEntrenamiento completo.")
    print(f"  MAE  = {metrics['MAE']*1000:.1f} g   (split {metrics['split']})")
    print(f"  RMSE = {metrics['RMSE']*1000:.1f} g")
    print(f"  R2   = {metrics['R2']:.4f}")
    if metrics.get("cobertura_banda_q10_q90") is not None:
        print(f"  Banda q10-q90 = {metrics['cobertura_banda_q10_q90']*100:.1f}% cobertura")


if __name__ == "__main__":
    main()
