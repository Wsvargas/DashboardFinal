# ──────────────────────────────────────────────────────────────
# data_loader.py · PRONACA Dashboard v15
# Adaptado a:
#   produccion_mes_actual_simulada_abiertos.xlsx
#   LOTES_IDEALES_QUINTILES_COMPLETO.xlsx  (Sheet1)
# ──────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import streamlit as st

from config  import EDAD_MIN_ANALISIS
from helpers import get_etapa, parse_num_series, pick_first_col


# ── Mapeos de zona / tipo normalizados ────────────────────────
_ZONA_MAP = {"BUC": "BUCAY", "STO": "SANTO DOMINGO"}
_TIPO_MAP = {
    "GRANJAPROPIA": "PROPIA", "PROPIA": "PROPIA",
    "PCA": "PAC",             "PAC":    "PAC",
}


# ──────────────────────────────────────────────────────────────
# DATOS PRINCIPALES
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_and_prepare(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)
    df.columns = df.columns.astype(str).str.strip()

    # ── Detectar columnas ─────────────────────────────────────
    col_lote  = pick_first_col(df, ["LoteCompleto", "Codigo_Unico", "Lote"])
    if not col_lote:
        raise ValueError("No encuentro columna de lote.")

    col_edad     = pick_first_col(df, ["Edad", "edad", "X4=Edad"])
    col_peso     = pick_first_col(df, ["PesoFinal", "Peso", "Y=Peso comp", "Peso comp"])
    col_aves     = pick_first_col(df, ["Aves_vivas", "AvesVivas", "Aves Vivas", "Aves_netas"])
    col_granja   = pick_first_col(df, ["Granja", "GranjaID"])
    col_galpon   = pick_first_col(df, ["Galpon", "galpon"])
    col_tipo_a   = pick_first_col(df, ["TipoAlimento", "tipo_alimento"])
    col_cost     = pick_first_col(df, ["costo_alimento_acumulado", "CostoAlimentoAcum",
                                       "CostoAlimentoAcumulado"])
    col_cost_dia = pick_first_col(df, ["costo_alimento_dia", "CostoAlimentoDia"])
    col_pricekg  = pick_first_col(df, ["precio_kg", "PrecioKg", "Precio_Kg", "precio kg"])
    col_alimkg   = pick_first_col(df, ["Alimento_Acumulado", "Alimento_acumulado_kg",
                                       "Alimento acum", "AlimAcumKg"])
    col_alim_dia = pick_first_col(df, ["alimento_dia_kg", "AlimentoConsumido",
                                       "Alimento Consumido"])
    col_zona     = pick_first_col(df, ["Zona", "zona"])
    col_tipo     = pick_first_col(df, ["TipoGranjero", "TipoGranja", "Tipo_Granja",
                                       "Tipo de granja", "X30=Granja Propia"])
    col_quint    = pick_first_col(df, ["Quintil", "quintil", "Quintil_Area_Crianza"])
    col_estado   = pick_first_col(df, ["Cerrado", "EstadoLote", "Estado_Lote"])
    col_cierre   = pick_first_col(df, ["Cierre de campaña", "CierreCampaña", "FechaCierre"])
    col_mort_ac  = pick_first_col(df, ["MortalidadDescarte_Acumulado", "MortalidadAcumulada"])
    col_aves_ini = pick_first_col(df, ["Aves_Iniciales", "Aves_netas"])

    # ── Renombres base ────────────────────────────────────────
    rename_map = {col_lote: "LoteCompleto", col_edad: "Edad", col_peso: "PesoFinal"}
    if col_aves:   rename_map[col_aves]   = "AvesVivas"
    if col_galpon: rename_map[col_galpon] = "Galpon"
    if col_tipo_a: rename_map[col_tipo_a] = "TipoAlimento"
    df = df.rename(columns=rename_map)

    # ── Estado del lote (Cerrado=0→ABIERTO, Cerrado=1→CERRADO) ──
    if col_estado:
        raw = df[col_estado]
        if pd.api.types.is_numeric_dtype(raw) or \
           raw.astype(str).str.match(r"^[01]$").fillna(False).any():
            df["EstadoLote"] = np.where(
                parse_num_series(raw).fillna(0).astype(int) == 1, "CERRADO", "ABIERTO"
            )
        else:
            df["EstadoLote"] = raw.astype(str).str.upper().str.strip()
    else:
        df["EstadoLote"] = "ABIERTO"

    # Todos los registros son producción activa
    df["Estatus"] = "ACTIVO"

    # ── Zona → BUCAY / SANTO DOMINGO ─────────────────────────
    if col_zona:
        z = df[col_zona].astype(str).str.upper().str.strip()
        df["ZonaNombre"] = z.map(_ZONA_MAP).fillna("OTRA")
    else:
        pref = df["LoteCompleto"].astype(str).str[:3].str.upper()
        df["ZonaNombre"] = pref.map({"BUC": "BUCAY", "STO": "SANTO DOMINGO"}).fillna("OTRA")

    # ── GranjaID ──────────────────────────────────────────────
    df["GranjaID"] = (
        df[col_granja].astype(str).str.strip()
        if col_granja
        else df["LoteCompleto"].astype(str).str[:7]
    )

    # ── Tipo granja → PROPIA / PAC ────────────────────────────
    if col_tipo:
        t = df[col_tipo].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)
        df["TipoStd"] = t.map(_TIPO_MAP).fillna("PAC")
    else:
        df["TipoStd"] = "PAC"

    # ── Quintil Q1..Q5 ────────────────────────────────────────
    raw_q = df[col_quint] if col_quint else pd.Series("Q5", index=df.index)
    df["Quintil"] = (
        raw_q.astype(str).str.upper().str.strip()
        .str.extract(r"(Q[1-5])", expand=False)
        .fillna("Q5")
    )
    df["Quintil_num"] = df["Quintil"].map(
        {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "Q5": 5}
    ).astype(float)

    # ── Etapa por edad del registro ───────────────────────────
    df["Etapa"] = df.apply(
    lambda r: get_etapa(r["Edad"], r.get("EstadoLote")),
    axis=1
    )   

    # ── Alimento acumulado ────────────────────────────────────
    if col_alimkg:
        df["AlimAcumKg"] = parse_num_series(df[col_alimkg])
    else:
        df["AlimAcumKg"] = np.nan

    # Alimento diario (para debug/KPIs)
    if col_alim_dia:
        df["_alim_dia"] = parse_num_series(df[col_alim_dia]).fillna(0)
        # Si el acumulado es todo NaN, reconstruirlo desde diario
        if df["AlimAcumKg"].isna().all():
            df = df.sort_values(["LoteCompleto", "Edad"]).copy()
            df["AlimAcumKg"] = df.groupby("LoteCompleto")["_alim_dia"].cumsum()
    else:
        df["_alim_dia"] = np.nan

    # ── Costos ────────────────────────────────────────────────
    # ── Costos ────────────────────────────────────────────────
    df["CostoAcum"] = parse_num_series(df[col_cost]) if col_cost else np.nan

    if col_cost_dia:
        df["CostoAlimentoDia"] = parse_num_series(df[col_cost_dia])
    else:
        df["CostoAlimentoDia"] = np.nan

    # Precio real por kg de alimento
    if col_pricekg:
        df["PrecioKg"] = parse_num_series(df[col_pricekg])
    else:
        df["PrecioKg"] = np.nan

    # ── Corte por lote ────────────────────────────────────────
    #   ABIERTO  → hasta último múltiplo de 7 con PesoFinal > 0
    #   CERRADO  → hasta último día con PesoFinal > 0
    df = df.sort_values(["LoteCompleto", "Edad"]).copy()

    cierre_flag = (
        df[col_cierre].notna()
        if (col_cierre and col_cierre in df.columns)
        else pd.Series(False, index=df.index)
    )
    peso_ok = df["PesoFinal"].notna() & (df["PesoFinal"] > 0)

    def _corte_por_lote(g: pd.DataFrame) -> int:
        estado       = str(g["EstadoLote"].iloc[0]).upper()
        tiene_cierre = bool(cierre_flag.loc[g.index].any()) or (estado == "CERRADO")
        gg = g[peso_ok.loc[g.index]].copy()
        if gg.empty:
            return int(g["Edad"].max()) if g["Edad"].notna().any() else 0
        if tiene_cierre:
            return int(gg["Edad"].max())
        gg7 = gg[gg["Edad"].astype(int) % 7 == 0]
        return int(gg7["Edad"].max()) if not gg7.empty else int(gg["Edad"].max())

    cortes = (
        df.groupby("LoteCompleto", sort=False)
        .apply(_corte_por_lote)
        .rename("EdadCorte")
    )
    df = df.merge(cortes, on="LoteCompleto", how="left")
    df = df[df["Edad"] <= df["EdadCorte"]].copy()

    # ── Métricas derivadas ────────────────────────────────────
    # ── Métricas derivadas ────────────────────────────────────
    df["KgLive"]      = (df["AvesVivas"] * df["PesoFinal"]).astype(float)
    df["CostoKg_Cum"] = df["CostoAcum"]  / df["KgLive"].replace(0, np.nan)
    df["FCR_Cum"]     = df["AlimAcumKg"] / df["KgLive"].replace(0, np.nan)

    # Si no vino precio_kg, estimarlo desde costo acumulado / alimento acumulado
    if "PrecioKg" not in df.columns:
        df["PrecioKg"] = np.nan

    df["PrecioKg"] = df["PrecioKg"].fillna(
        df["CostoAcum"] / df["AlimAcumKg"].replace(0, np.nan)
    )

    # ── Mortalidad ────────────────────────────────────────────
    if col_mort_ac and col_aves_ini:
        mort_ac  = parse_num_series(df[col_mort_ac])
        aves_ini = parse_num_series(df[col_aves_ini])
        df["MortPct"] = (mort_ac / aves_ini.replace(0, np.nan) * 100).round(2)
    else:
        df["MortPct"] = np.nan

    # ── Columnas extra para modelo ML ─────────────────────────
    if "X4=Edad"            not in df.columns: df["X4=Edad"]            = df["Edad"]
    if "Edad^2"             not in df.columns: df["Edad^2"]             = df["Edad"] ** 2
    if "alimento acumulado" not in df.columns: df["alimento acumulado"] = df["AlimAcumKg"]

    return df.sort_values(["LoteCompleto", "Edad"])


# ──────────────────────────────────────────────────────────────
# CURVAS IDEALES (benchmark)
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_ideales(path: str) -> pd.DataFrame:
    import os
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        xl    = pd.ExcelFile(path)
        # Prioridad: DATOS_COMPLETOS (legacy) → Sheet1 → primera hoja
        sheet = xl.sheet_names[0]
        if "DATOS_COMPLETOS" in xl.sheet_names:
            sheet = "DATOS_COMPLETOS"
        elif "Sheet1" in xl.sheet_names:
            sheet = "Sheet1"

        df = pd.read_excel(path, sheet_name=sheet)
        df.columns = df.columns.astype(str).str.strip()

        # Zona_Nombre: BUC→BUCAY, STO→SANTO DOMINGO
        zona_col = pick_first_col(df, ["Zona", "zona"])
        if zona_col:
            z = df[zona_col].astype(str).str.upper().str.strip()
            df["Zona_Nombre"] = z.map(_ZONA_MAP).fillna("OTRA")
        else:
            df["Zona_Nombre"] = "BUCAY"

        # TipoGranja: Propia→PROPIA, PCA→PAC
        tipo_col = pick_first_col(df, ["TipoGranja", "Tipo_Granja"])
        if tipo_col:
            t = df[tipo_col].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)
            df["TipoGranja"] = t.map(_TIPO_MAP).fillna("PAC")
        else:
            df["TipoGranja"] = "PAC"

        # Quintil normalizado
        # FUENTE PRIMARIA: columna 'Escenario' (ej: "STO_PCA_Q5")
        # Quintil_Area_Crianza tiene errores documentados — 538 filas con quintil incorrecto
        if "Escenario" in df.columns:
            df["Quintil"] = (
                df["Escenario"].astype(str).str.upper().str.strip()
                .str.extract(r"(Q[1-5])", expand=False)
                .fillna("Q5")
            )
        else:
            quint_col = pick_first_col(df, ["Quintil_Area_Crianza", "Quintil", "quintil"])
            df["Quintil"] = (
                df[quint_col].astype(str).str.upper().str.strip()
                .str.extract(r"(Q[1-5])", expand=False)
                .fillna("Q5")
            ) if quint_col else "Q5"

        # Asegurar columna 'Peso'
        if "Peso" not in df.columns:
            peso_col = pick_first_col(df, ["PesoFinal", "peso", "Peso_ideal"])
            if peso_col:
                df["Peso"] = df[peso_col]

        return df

    except Exception as e:
        st.warning(f"⚠️ Error cargando ideales: {e}")
        return pd.DataFrame()


# ──────────────────────────────────────────────────────────────
# SNAPSHOT
# Último registro por lote → una sola Etapa por lote (sin duplicar)
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def build_snapshot_activos(df_all: pd.DataFrame) -> pd.DataFrame:
    act = df_all[df_all["Estatus"].astype(str).str.upper().eq("ACTIVO")].copy()
    if act.empty:
        return pd.DataFrame()
    snap = (
        act.sort_values(["LoteCompleto", "Edad"])
        .groupby("LoteCompleto", as_index=False)
        .last()
    )
    # Etapa asignada por edad del snapshot → cada lote pertenece a UNA sola etapa
    snap["Etapa"] = snap.apply(
    lambda r: get_etapa(r["Edad"], r.get("EstadoLote")),
    axis=1
    )
    return snap


# ──────────────────────────────────────────────────────────────
# GAPS vs IDEAL
# ──────────────────────────────────────────────────────────────
def calcular_gaps_lotes(lotes_ids, df_hist, ideales_df):
    resultados = []
    for lote in lotes_ids:
        lote_hist = df_hist[
            (df_hist["LoteCompleto"] == lote) &
            (df_hist["Edad"] >= EDAD_MIN_ANALISIS)
        ]
        if lote_hist.empty:
            continue
        snap = lote_hist.iloc[-1]
        ideal = ideales_df[
            (ideales_df["Zona_Nombre"] == snap["ZonaNombre"]) &
            (ideales_df["TipoGranja"]  == snap["TipoStd"]) &
            (ideales_df["Quintil"]     == snap["Quintil"])
        ]
        if ideal.empty:
            continue
        gs = gc = 0
        for _, ir in ideal.iterrows():
            pr = lote_hist[lote_hist["Edad"] == ir.get("Edad")]
            if not pr.empty and pd.notna(ir.get("Peso")):
                g = ir["Peso"] - pr.iloc[0]["PesoFinal"]
                if g > 0:
                    gs += g
                    gc += 1
        if gc > 0:
            resultados.append({"LoteCompleto": lote, "gap_promedio": gs / gc})
    return resultados


# ──────────────────────────────────────────────────────────────
# GAP FCR POR GALPÓN  (Sec 02 nueva)
# Gap = FCR_real − FCR_ideal en el último día del lote
# Positivo = peor conversión que el ideal
# ──────────────────────────────────────────────────────────────
def calcular_fcr_gaps_galpones(snap_df: pd.DataFrame, ideales_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula gap por lote-galpón usando:
      - FCR ideal del benchmark
      - biomasa real actual del lote-galpón
      - precio_kg real actual del lote-galpón

    Costo ideal recalculado = (FCR_ideal * KgLive_real) * PrecioKg_real
    """
    if snap_df.empty or ideales_df.empty:
        return pd.DataFrame()

    fcr_col = "conversio alimenticia" if "conversio alimenticia" in snap_df.columns else "FCR_Cum"

    filas = []
    for _, row in snap_df.iterrows():
        edad_lote = int(row.get("Edad", 0) or 0)
        if edad_lote < EDAD_MIN_ANALISIS:
            continue

        ideal_sub = ideales_df[
            (ideales_df["Zona_Nombre"] == row["ZonaNombre"]) &
            (ideales_df["TipoGranja"]  == row["TipoStd"]) &
            (ideales_df["Quintil"]     == row["Quintil"])
        ].copy()

        if ideal_sub.empty:
            continue

        dia_exact = ideal_sub[ideal_sub["Edad"] == edad_lote]
        if not dia_exact.empty:
            fila_ideal = dia_exact.iloc[0]
        else:
            fila_ideal = ideal_sub.iloc[(ideal_sub["Edad"] - edad_lote).abs().argsort()[:1]].iloc[0]

        fcr_real = float(row.get(fcr_col, np.nan)) if pd.notna(row.get(fcr_col, np.nan)) else np.nan
        if pd.isna(fcr_real):
            continue

        fcr_ideal = float(fila_ideal["conversio alimenticia"]) if "conversio alimenticia" in fila_ideal.index else np.nan
        if pd.isna(fcr_ideal):
            continue

        kg_live    = float(row.get("KgLive", 0) or 0)
        costo_real = float(row.get("CostoAcum", 0) or 0)

        # PrecioKg real del lote-galpón actual
        precio_kg_real = float(row.get("PrecioKg", np.nan)) if pd.notna(row.get("PrecioKg", np.nan)) else np.nan

        # fallback robusto
        if pd.isna(precio_kg_real):
            alim_acum = float(row.get("AlimAcumKg", np.nan)) if pd.notna(row.get("AlimAcumKg", np.nan)) else np.nan
            if pd.notna(alim_acum) and alim_acum > 0 and pd.notna(costo_real):
                precio_kg_real = costo_real / alim_acum

        # Recalcular ideal con biomasa real y precio real
        alim_ideal_acum = fcr_ideal * kg_live if pd.notna(fcr_ideal) and pd.notna(kg_live) else np.nan
        costo_ideal_calc = alim_ideal_acum * precio_kg_real if pd.notna(alim_ideal_acum) and pd.notna(precio_kg_real) else np.nan

        gap_fcr      = fcr_real - fcr_ideal if pd.notna(fcr_real) and pd.notna(fcr_ideal) else np.nan
        gap_costo    = costo_real - costo_ideal_calc if pd.notna(costo_real) and pd.notna(costo_ideal_calc) else np.nan
        gap_costo_kg = gap_costo / kg_live if pd.notna(gap_costo) and pd.notna(kg_live) and kg_live > 0 else np.nan

        filas.append({
            "Granja":         str(row.get("GranjaID", row.get("Granja", "—"))),
            "NombreGranja":   str(row.get("NombreGranja", "—")),
            "Galpon":         row.get("Galpon", "—"),
            "LoteCompleto":   row["LoteCompleto"],
            "Edad":           edad_lote,

            "KgLive":         kg_live,
            "PrecioKgReal":   precio_kg_real,
            "AlimIdealAcum":  alim_ideal_acum,

            "FCR_real":       round(fcr_real, 4),
            "FCR_ideal":      round(fcr_ideal, 4),
            "Gap_FCR":        round(gap_fcr, 4) if pd.notna(gap_fcr) else np.nan,

            "CostoReal":      costo_real,
            "CostoIdeal":     costo_ideal_calc,
            "GapCosto":       gap_costo,
            "GapCostoKg":     gap_costo_kg,

            "ZonaNombre":     row["ZonaNombre"],
            "TipoStd":        row["TipoStd"],
            "Quintil":        row["Quintil"],
        })

    return pd.DataFrame(filas)

# ──────────────────────────────────────────────────────────────
# RESUMEN A NIVEL DE GRANJA  (Sec 02 gráfico de barras)
# ──────────────────────────────────────────────────────────────
def calcular_fcr_gaps_granjas(gaps_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """
    Resume por granja el sobrecosto recalculado vs ideal.
    """
    if gaps_df.empty:
        return pd.DataFrame()

    con_prob = gaps_df[gaps_df["GapCosto"] > 0].copy()
    if con_prob.empty:
        return pd.DataFrame()

    grp = (
        con_prob.groupby(["Granja", "NombreGranja"])
        .agg(
            NumGalpones    = ("Galpon", "nunique"),
            KgLiveTotal    = ("KgLive", "sum"),
            FCR_real       = ("FCR_real", "mean"),
            FCR_ideal      = ("FCR_ideal", "mean"),
            Gap_FCR_medio  = ("Gap_FCR", "mean"),
            CostoRealTotal = ("CostoReal", "sum"),
            CostoIdealTotal= ("CostoIdeal", "sum"),
            GapCostoTotal  = ("GapCosto", "sum"),
        )
        .reset_index()
    )

    grp["GapCostoKg"] = grp["GapCostoTotal"] / grp["KgLiveTotal"].replace(0, np.nan)

    grp = grp.sort_values(
        ["GapCostoTotal", "GapCostoKg"],
        ascending=[False, False]
    ).head(top_n).reset_index(drop=True)

    return grp
# ──────────────────────────────────────────────────────────────
# CURVA IDEAL PROMEDIADA PARA UN LOTE  (Sec 03)
# Promedia Peso, FCR, CostoAcum y CostoDia de TODOS los lotes
# ideales del mismo combo (Zona·Tipo·Quintil) por día.
# Devuelve DataFrame con: Edad, Peso, FCR_ideal,
#   CostoAcum_ideal, CostoDia_ideal
# ──────────────────────────────────────────────────────────────
def get_curva_ideal_promedio(zona: str, tipo: str, quintil: str,
                             ideales_df: pd.DataFrame,
                             edad_max: int | None = None) -> pd.DataFrame:
    """
    Parámetros normalizados: zona='BUCAY', tipo='PROPIA', quintil='Q2'
    """
    sub = ideales_df[
        (ideales_df["Zona_Nombre"] == zona) &
        (ideales_df["TipoGranja"]  == tipo) &
        (ideales_df["Quintil"]     == quintil)
    ].copy()

    if sub.empty:
        return pd.DataFrame()

    # Columnas disponibles
    agg_dict = {}
    if "Peso"                     in sub.columns: agg_dict["Peso"]             = ("Peso",                     "mean")
    if "conversio alimenticia"    in sub.columns: agg_dict["FCR_ideal"]        = ("conversio alimenticia",    "mean")
    if "costo_alimento_acumulado" in sub.columns: agg_dict["CostoAcum_ideal"]  = ("costo_alimento_acumulado", "mean")
    if "costo_alimento_dia"       in sub.columns: agg_dict["CostoDia_ideal"]   = ("costo_alimento_dia",       "mean")

    if not agg_dict:
        return pd.DataFrame()

    cur = sub.groupby("Edad").agg(**agg_dict).reset_index().sort_values("Edad")

    if edad_max is not None:
        cur = cur[cur["Edad"] <= edad_max + 1]

    return cur

# ══════════════════════════════════════════════════════════════════════════════
# TOP 10 PEORES GRANJAS POR CONVERSIÓN ALIMENTICIA
# ══════════════════════════════════════════════════════════════════════════════

def agrupar_granjalote(df):
    """
    Agrupa por LoteCompleto (GRANJA-LOTE) y toma el ÚLTIMO registro
    (máxima Edad = snapshot), que contiene la conversión acumulada real.
    Compatible con el DataFrame que genera load_and_prepare().
    """
    df = df.copy()

    # Código de granja: primera parte de LoteCompleto (ej: BUC1002)
    df['Granja'] = df['LoteCompleto'].str.split('-').str[0]

    # Detectar columnas flexibles
    alim_col  = 'AlimAcumKg'  if 'AlimAcumKg'  in df.columns else (
                'Alimento_Acumulado' if 'Alimento_Acumulado' in df.columns else None)
    peso_col  = 'PesoFinal'   if 'PesoFinal'   in df.columns else (
                'Peso'        if 'Peso'         in df.columns else None)
    costo_col = 'CostoAcum'   if 'CostoAcum'   in df.columns else 'costo_alimento_acumulado'
    galpon_col = 'Galpon'     if 'Galpon'       in df.columns else None

    agg_dict = {
        'conversio alimenticia': 'last',   # último día = FCR acumulado real
        'Codigo_Unico':          'first',
        'Granja':                'first',
        'NombreGranja':          'first',
        costo_col:               'max',
        'Edad':                  'max',
    }
    if alim_col:  agg_dict[alim_col]  = 'max'
    if peso_col:  agg_dict[peso_col]  = 'max'
    if galpon_col: agg_dict[galpon_col] = 'first'

    df_granjalote = (
        df.sort_values(['LoteCompleto', 'Edad'])
        .groupby('LoteCompleto')
        .agg(agg_dict)
        .reset_index()
    )

    # Renombres estables
    rename_map = {
        'conversio alimenticia': 'Conv_GranjaLote',
        costo_col:               'CostoAcum',
    }
    if alim_col:   rename_map[alim_col]  = 'AlimAcumKg'
    if peso_col:   rename_map[peso_col]  = 'Peso'
    df_granjalote = df_granjalote.rename(columns=rename_map)

    return df_granjalote


def agrupar_granjas_top10(df_granjalote, top_n=10):
    """
    Agrupa por GRANJA y calcula FCR promedio de sus lotes.
    Retorna TOP N peores (mayor FCR = peor conversión).
    Incluye NombreGranja para mostrar en el gráfico.
    """
    agg_dict = {
        'LoteCompleto':    'count',
        'Conv_GranjaLote': ['mean', 'max', 'min'],
        'CostoAcum':       'sum',
        'NombreGranja':    'first',
    }
    if 'AlimAcumKg' in df_granjalote.columns:
        agg_dict['AlimAcumKg'] = 'sum'
    if 'Edad' in df_granjalote.columns:
        agg_dict['Edad'] = 'mean'

    df_granjas = df_granjalote.groupby('Granja').agg(agg_dict).reset_index()

    # Aplanar columnas multi-nivel
    df_granjas.columns = ['_'.join(c).strip('_') if isinstance(c, tuple) else c
                          for c in df_granjas.columns]

    col_map = {
        'LoteCompleto_count':    'NumLotes',
        'Conv_GranjaLote_mean':  'Conv_Promedio',
        'Conv_GranjaLote_max':   'Conv_Max',
        'Conv_GranjaLote_min':   'Conv_Min',
        'CostoAcum_sum':         'CostoTotal',
        'NombreGranja_first':    'NombreGranja',
        'AlimAcumKg_sum':        'AlimTotal',
        'Edad_mean':             'EdadPromedio',
    }
    df_granjas = df_granjas.rename(columns={k: v for k, v in col_map.items()
                                            if k in df_granjas.columns})

    return df_granjas.sort_values('Conv_Promedio', ascending=False).head(top_n).reset_index(drop=True)


def filtrar_lotes_granja(df_granjalote, granja_codigo):
    """
    Devuelve los lotes/galpones de una granja, ordenados por peor FCR primero.
    """
    lotes = df_granjalote[df_granjalote['Granja'] == granja_codigo].copy()
    return lotes.sort_values('Conv_GranjaLote', ascending=False).reset_index(drop=True)