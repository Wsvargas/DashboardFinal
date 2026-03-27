import numpy as np
import pandas as pd
import streamlit as st

from config import EDAD_MIN_ANALISIS
from helpers import get_etapa, parse_num_series, pick_first_col


# ── Mapeos de zona / tipo normalizados ────────────────────────
_ZONA_MAP = {"BUC": "BUCAY", "STO": "SANTO DOMINGO"}
_TIPO_MAP = {
    "GRANJAPROPIA": "PROPIA", "PROPIA": "PROPIA",
    "PCA": "PAC",             "PAC":    "PAC",
}

# ── Mapeo de reproductora normalizada ─────────────────────────
_REPRO_MAP = {
    "ADULTA": "ADULTA",
    "JOVEN": "JOVEN",
    "VIEJA": "VIEJA",
}


# ──────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ──────────────────────────────────────────────────────────────
def _safe_num(s):
    return pd.to_numeric(s, errors="coerce")


def _ensure_columns(df: pd.DataFrame, cols: list[str], fill_value=np.nan) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = fill_value
    return out


def _empty_comp_columns(hist: pd.DataFrame) -> pd.DataFrame:
    out = hist.copy()
    for c in [
        "PesoIdeal_comp",
        "FCR_ideal",
        "KgLiveIdeal_comp",
        "AlimIdealAcum_comp",
        "AlimIdealDia_comp",
        "CostoIdealDia_comp",
        "CostoIdealComp",
        "GapCostoComp",
    ]:
        if c not in out.columns:
            out[c] = np.nan
    return out


def _norm_text(s) -> str:
    if pd.isna(s):
        return ""
    x = str(s).strip().upper()
    x = (
        x.replace("Á", "A")
         .replace("É", "E")
         .replace("Í", "I")
         .replace("Ó", "O")
         .replace("Ú", "U")
         .replace("Ñ", "N")
    )
    return x


def _norm_reproductora_value(x) -> str:
    x = _norm_text(x)
    if not x:
        return "SIN_DATO"

    # Intenta detectar aunque venga dentro de un texto más largo
    for k in _REPRO_MAP.keys():
        if k in x:
            return _REPRO_MAP[k]

    return "SIN_DATO"


def _extract_reproductora_from_scenario(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.upper().str.strip()
    s = (
        s.str.replace("Á", "A", regex=False)
         .str.replace("É", "E", regex=False)
         .str.replace("Í", "I", regex=False)
         .str.replace("Ó", "O", regex=False)
         .str.replace("Ú", "U", regex=False)
         .str.replace("Ñ", "N", regex=False)
    )

    out = pd.Series("SIN_DATO", index=s.index, dtype="object")
    out[s.str.contains("ADULTA", na=False)] = "ADULTA"
    out[s.str.contains("JOVEN", na=False)] = "JOVEN"
    out[s.str.contains("VIEJA", na=False)] = "VIEJA"
    return out


def _filtrar_ideal_sub(
    ideales_df: pd.DataFrame,
    zona: str,
    tipo: str,
    quint: str,
    reproductora: str | None = None,
) -> pd.DataFrame:
    """
    Filtro robusto:
    1) intenta Zona + Tipo + Quintil + Reproductora
    2) si no encuentra, cae a Zona + Tipo + Quintil
    """
    if ideales_df is None or ideales_df.empty:
        return pd.DataFrame()

    base = ideales_df[
        (ideales_df["Zona_Nombre"] == zona) &
        (ideales_df["TipoGranja"] == tipo) &
        (ideales_df["Quintil"] == quint)
    ].copy()

    if base.empty:
        return base

    if "ReproductoraStd" not in base.columns:
        return base

    repro = _norm_reproductora_value(reproductora)
    if repro == "SIN_DATO":
        return base

    exact = base[base["ReproductoraStd"] == repro].copy()
    if not exact.empty:
        return exact

    # Fallback al esquema viejo
    return base


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
    col_nombre_g = pick_first_col(df, ["NombreGranja", "Nombre Granja", "Nombre_Granja"])
    col_tipo_a   = pick_first_col(df, ["TipoAlimento", "tipo_alimento"])
    col_cost     = pick_first_col(df, ["costo_alimento_acumulado", "CostoAlimentoAcum", "CostoAlimentoAcumulado"])
    col_cost_dia = pick_first_col(df, ["costo_alimento_dia", "CostoAlimentoDia"])
    col_pricekg  = pick_first_col(df, ["precio_kg", "PrecioKg", "Precio_Kg", "precio kg", "Precio kg"])
    col_alimkg   = pick_first_col(df, ["Alimento_Acumulado", "Alimento_acumulado_kg", "Alimento acum", "AlimAcumKg"])
    col_alim_dia = pick_first_col(df, ["alimento_dia_kg", "AlimentoConsumido", "Alimento Consumido"])
    col_zona     = pick_first_col(df, ["Zona", "zona"])
    col_tipo     = pick_first_col(df, ["TipoGranjero", "TipoGranja", "Tipo_Granja", "Tipo de granja", "X30=Granja Propia"])
    col_quint    = pick_first_col(df, ["Quintil", "quintil", "Quintil_Area_Crianza"])
    col_repro    = pick_first_col(df, ["Reproductora", "reproductora", "Categoria_Reproductora", "TipoReproductora", "Edad_Reproductora", "ReproductoraStd"])
    col_estado   = pick_first_col(df, ["Cerrado", "EstadoLote", "Estado_Lote"])
    col_cierre   = pick_first_col(df, ["Cierre de campaña", "CierreCampaña", "FechaCierre"])
    col_mort_ac  = pick_first_col(df, ["MortalidadDescarte_Acumulado", "MortalidadAcumulada"])
    col_aves_ini = pick_first_col(df, ["Aves_Iniciales", "Aves_netas"])

    # ── Renombres base ────────────────────────────────────────
    rename_map = {col_lote: "LoteCompleto", col_edad: "Edad", col_peso: "PesoFinal"}
    if col_aves:
        rename_map[col_aves] = "AvesVivas"
    if col_galpon:
        rename_map[col_galpon] = "Galpon"
    if col_tipo_a:
        rename_map[col_tipo_a] = "TipoAlimento"
    if col_pricekg:
        rename_map[col_pricekg] = "PrecioKg"
    if col_nombre_g:
        rename_map[col_nombre_g] = "NombreGranja"
    if col_repro:
        rename_map[col_repro] = "ReproductoraRaw"

    df = df.rename(columns=rename_map)

    # ── Estado del lote (Cerrado=0→ABIERTO, Cerrado=1→CERRADO) ──
    if col_estado:
        raw = df[col_estado]
        raw_num = parse_num_series(raw)
        if raw_num.notna().any():
            df["EstadoLote"] = np.where(
                raw_num.fillna(0).astype(int) == 1, "CERRADO", "ABIERTO"
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

    if "NombreGranja" not in df.columns:
        df["NombreGranja"] = df["GranjaID"]

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

    # ── NUEVO: Reproductora normalizada ───────────────────────
    if "ReproductoraRaw" in df.columns:
        df["ReproductoraStd"] = df["ReproductoraRaw"].apply(_norm_reproductora_value)
    else:
        df["ReproductoraStd"] = "SIN_DATO"

    # ── Tipos numéricos principales ───────────────────────────
    df["Edad"] = parse_num_series(df["Edad"])
    df["PesoFinal"] = parse_num_series(df["PesoFinal"])

    if "AvesVivas" not in df.columns:
        df["AvesVivas"] = np.nan
    else:
        df["AvesVivas"] = parse_num_series(df["AvesVivas"])

    if "Galpon" not in df.columns:
        df["Galpon"] = np.nan
    else:
        df["Galpon"] = parse_num_series(df["Galpon"])

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

    # Alimento diario
    if col_alim_dia:
        df["_alim_dia"] = parse_num_series(df[col_alim_dia]).fillna(0)
        if df["AlimAcumKg"].isna().all():
            df = df.sort_values(["LoteCompleto", "Edad"]).copy()
            df["AlimAcumKg"] = df.groupby("LoteCompleto")["_alim_dia"].cumsum()
    else:
        df["_alim_dia"] = np.nan

    # ── Costos ────────────────────────────────────────────────
    df["CostoAcum"] = parse_num_series(df[col_cost]) if col_cost else np.nan

    if col_cost_dia:
        df["CostoAlimentoDia"] = parse_num_series(df[col_cost_dia])
    else:
        df["CostoAlimentoDia"] = np.nan

    if "PrecioKg" in df.columns:
        df["PrecioKg"] = parse_num_series(df["PrecioKg"])
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
        estado = str(g["EstadoLote"].iloc[0]).upper()
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
    df["KgLive"] = (df["AvesVivas"] * df["PesoFinal"]).astype(float)
    df["CostoKg_Cum"] = df["CostoAcum"] / df["KgLive"].replace(0, np.nan)
    df["FCR_Cum"] = df["AlimAcumKg"] / df["KgLive"].replace(0, np.nan)

    # Si no vino PrecioKg, estimarlo desde costo acumulado / alimento acumulado
    df["PrecioKg"] = df["PrecioKg"].fillna(
        df["CostoAcum"] / df["AlimAcumKg"].replace(0, np.nan)
    )

    # PrecioKg real diario comparable
    df["PrecioKgRealDia"] = df["PrecioKg"].copy()

    df["PrecioKgRealDia"] = df["PrecioKgRealDia"].fillna(
        df["CostoAlimentoDia"] / df["_alim_dia"].replace(0, np.nan)
    )

    df["PrecioKgRealDia"] = df["PrecioKgRealDia"].fillna(
        df["CostoAcum"] / df["AlimAcumKg"].replace(0, np.nan)
    )

    df["PrecioKgRealDia"] = (
        df.sort_values(["LoteCompleto", "Edad"])
          .groupby("LoteCompleto")["PrecioKgRealDia"]
          .transform(lambda s: s.ffill().bfill())
    )

    # ── Mortalidad ────────────────────────────────────────────
    if col_mort_ac and col_aves_ini:
        mort_ac = parse_num_series(df[col_mort_ac])
        aves_ini = parse_num_series(df[col_aves_ini])
        df["MortPct"] = (mort_ac / aves_ini.replace(0, np.nan) * 100).round(2)
    else:
        df["MortPct"] = np.nan

    # ── Columnas extra para modelo ML ─────────────────────────
    if "X4=Edad" not in df.columns:
        df["X4=Edad"] = df["Edad"]
    if "Edad^2" not in df.columns:
        df["Edad^2"] = df["Edad"] ** 2
    if "alimento acumulado" not in df.columns:
        df["alimento acumulado"] = df["AlimAcumKg"]

    return df.sort_values(["LoteCompleto", "Edad"]).reset_index(drop=True)


# ──────────────────────────────────────────────────────────────
# CURVAS IDEALES (benchmark)
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_ideales(path: str) -> pd.DataFrame:
    import os

    if not os.path.exists(path):
        return pd.DataFrame()

    try:
        xl = pd.ExcelFile(path)

        # Prioridad: DATOS_COMPLETOS → Sheet1 → primera hoja
        sheet = xl.sheet_names[0]
        if "DATOS_COMPLETOS" in xl.sheet_names:
            sheet = "DATOS_COMPLETOS"
        elif "Sheet1" in xl.sheet_names:
            sheet = "Sheet1"

        df = pd.read_excel(path, sheet_name=sheet)
        df.columns = df.columns.astype(str).str.strip()

        # Zona_Nombre
        zona_col = pick_first_col(df, ["Zona", "zona", "Zona_Nombre"])
        if zona_col:
            z = df[zona_col].astype(str).str.upper().str.strip()
            df["Zona_Nombre"] = z.map(_ZONA_MAP).fillna(z)
            df["Zona_Nombre"] = df["Zona_Nombre"].replace({"BUCAY": "BUCAY", "SANTO DOMINGO": "SANTO DOMINGO"})
        else:
            df["Zona_Nombre"] = "BUCAY"

        # TipoGranja
        tipo_col = pick_first_col(df, ["TipoGranja", "Tipo_Granja", "TipoGranjero", "TipoStd"])
        if tipo_col:
            t = df[tipo_col].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)
            df["TipoGranja"] = t.map(_TIPO_MAP).fillna(t)
            df["TipoGranja"] = df["TipoGranja"].replace({"PROPIA": "PROPIA", "PAC": "PAC", "PCA": "PAC"})
        else:
            df["TipoGranja"] = "PAC"

        # Quintil normalizado
        if "Escenario" in df.columns:
            df["Quintil"] = (
                df["Escenario"].astype(str).str.upper().str.strip()
                .str.extract(r"(Q[1-5])", expand=False)
                .fillna("Q5")
            )
        elif "Etiqueta_Escenario" in df.columns:
            df["Quintil"] = (
                df["Etiqueta_Escenario"].astype(str).str.upper().str.strip()
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

        # ── NUEVO: Reproductora benchmark ──────────────────────
        repro_col = pick_first_col(
            df,
            ["Reproductora", "reproductora", "ReproductoraStd", "Categoria_Reproductora", "TipoReproductora"]
        )

        if repro_col:
            df["ReproductoraStd"] = df[repro_col].apply(_norm_reproductora_value)
        elif "Etiqueta_Escenario" in df.columns:
            df["ReproductoraStd"] = _extract_reproductora_from_scenario(df["Etiqueta_Escenario"])
        elif "Escenario" in df.columns:
            df["ReproductoraStd"] = _extract_reproductora_from_scenario(df["Escenario"])
        else:
            df["ReproductoraStd"] = "SIN_DATO"

        # Columnas base benchmark
        edad_col = pick_first_col(df, ["Edad", "edad"])
        if edad_col:
            df["Edad"] = parse_num_series(df[edad_col])

        if "Peso" not in df.columns:
            peso_col = pick_first_col(df, ["PesoFinal", "peso", "Peso_ideal", "PesoIdeal", "Peso_comp_corregido", "Peso"])
            if peso_col:
                df["Peso"] = df[peso_col]

        if "Peso" in df.columns:
            df["Peso"] = parse_num_series(df["Peso"])

        # Normalizar FCR ideal
        if "FCR_ideal" not in df.columns:
            fcr_col = pick_first_col(
                df,
                ["conversio alimenticia", "FCR", "FCRIdeal", "FCR_ideal", "conversion"]
            )
            if fcr_col:
                df["FCR_ideal"] = parse_num_series(df[fcr_col])
            else:
                df["FCR_ideal"] = np.nan
        else:
            df["FCR_ideal"] = parse_num_series(df["FCR_ideal"])

        # Otras columnas opcionales
        costo_acum_col = pick_first_col(df, ["costo_alimento_acumulado", "CostoAcum_ideal"])
        costo_dia_col = pick_first_col(df, ["costo_alimento_dia", "CostoDia_ideal"])

        if costo_acum_col:
            df["costo_alimento_acumulado"] = parse_num_series(df[costo_acum_col])

        if costo_dia_col:
            df["costo_alimento_dia"] = parse_num_series(df[costo_dia_col])

        return (
            df.sort_values(["Zona_Nombre", "TipoGranja", "ReproductoraStd", "Quintil", "Edad"])
              .reset_index(drop=True)
        )

    except Exception as e:
        st.warning(f"⚠️ Error cargando ideales: {e}")
        return pd.DataFrame()


# ──────────────────────────────────────────────────────────────
# SNAPSHOT
# Último registro por lote → una sola Etapa por lote
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

    snap["Etapa"] = snap.apply(
        lambda r: get_etapa(r["Edad"], r.get("EstadoLote")),
        axis=1
    )

    return snap


# ──────────────────────────────────────────────────────────────
# UTILIDAD: resolver precio/kg real diario
# ──────────────────────────────────────────────────────────────
def resolver_precio_kg_real(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if "PrecioKgRealDia" not in out.columns:
        out["PrecioKgRealDia"] = np.nan

    if "PrecioKg" in out.columns:
        out["PrecioKgRealDia"] = out["PrecioKgRealDia"].fillna(
            pd.to_numeric(out["PrecioKg"], errors="coerce")
        )

    if "CostoAlimentoDia" in out.columns and "_alim_dia" in out.columns:
        costo_dia = pd.to_numeric(out["CostoAlimentoDia"], errors="coerce")
        alim_dia = pd.to_numeric(out["_alim_dia"], errors="coerce")
        out["PrecioKgRealDia"] = out["PrecioKgRealDia"].fillna(
            costo_dia / alim_dia.replace(0, np.nan)
        )

    if "CostoAcum" in out.columns and "AlimAcumKg" in out.columns:
        costo_acum = pd.to_numeric(out["CostoAcum"], errors="coerce")
        alim_acum = pd.to_numeric(out["AlimAcumKg"], errors="coerce")
        out["PrecioKgRealDia"] = out["PrecioKgRealDia"].fillna(
            costo_acum / alim_acum.replace(0, np.nan)
        )

    if "LoteCompleto" in out.columns and "Edad" in out.columns:
        out = out.sort_values(["LoteCompleto", "Edad"]).copy()
        out["PrecioKgRealDia"] = out.groupby("LoteCompleto")["PrecioKgRealDia"].transform(
            lambda s: s.ffill().bfill()
        )
    else:
        out["PrecioKgRealDia"] = out["PrecioKgRealDia"].ffill().bfill()

    return out


# ──────────────────────────────────────────────────────────────
# UTILIDAD: historial real + ideal comparable para UN lote
# ──────────────────────────────────────────────────────────────
def construir_historial_ideal_comparable(
    hist_df: pd.DataFrame,
    ideal_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Lógica correcta:

      KgLiveIdeal_comp   = PesoIdeal * AvesVivas_reales
      AlimIdealAcum_comp = FCR_ideal * KgLiveIdeal_comp
      AlimIdealDia_comp  = diff(AlimIdealAcum_comp)
      CostoIdealDia_comp = AlimIdealDia_comp * PrecioKgRealDia
      CostoIdealComp     = acumulado de CostoIdealDia_comp

    Reglas extra:
      - usa edad ideal más cercana si no hay match exacto
      - si _alim_dia == 0 en el lote real, ese día no genera costo ideal
      - cualquier delta negativo del ideal se fuerza a 0
    """
    hist = hist_df.copy().sort_values("Edad").reset_index(drop=True)
    hist = _ensure_columns(
        hist,
        ["Edad", "PesoFinal", "AvesVivas", "CostoAcum", "CostoAlimentoDia", "_alim_dia", "AlimAcumKg", "KgLive", "PrecioKg", "PrecioKgRealDia"]
    )

    for c in ["Edad", "PesoFinal", "AvesVivas", "CostoAcum", "CostoAlimentoDia", "_alim_dia", "AlimAcumKg", "KgLive", "PrecioKg", "PrecioKgRealDia"]:
        hist[c] = _safe_num(hist[c])

    hist = resolver_precio_kg_real(hist)

    if "KgLive" not in hist.columns or hist["KgLive"].isna().all():
        hist["KgLive"] = hist["AvesVivas"] * hist["PesoFinal"]

    if ideal_df is None or ideal_df.empty:
        return _empty_comp_columns(hist)

    ideal = ideal_df.copy()
    ideal = _ensure_columns(ideal, ["Edad", "Peso", "FCR_ideal"])
    ideal["Edad"] = _safe_num(ideal["Edad"])
    ideal["Peso"] = _safe_num(ideal["Peso"])
    ideal["FCR_ideal"] = _safe_num(ideal["FCR_ideal"])

    ideal = (
        ideal[["Edad", "Peso", "FCR_ideal"]]
        .dropna(subset=["Edad"])
        .sort_values("Edad")
        .reset_index(drop=True)
    )

    if ideal.empty:
        return _empty_comp_columns(hist)

    hist_merge = pd.merge_asof(
        hist.sort_values("Edad"),
        ideal.rename(columns={"Peso": "PesoIdeal_comp"}).sort_values("Edad"),
        on="Edad",
        direction="nearest"
    )

    hist_merge["KgLiveIdeal_comp"] = hist_merge["PesoIdeal_comp"] * hist_merge["AvesVivas"]
    hist_merge["AlimIdealAcum_comp"] = hist_merge["FCR_ideal"] * hist_merge["KgLiveIdeal_comp"]

    hist_merge["AlimIdealDia_comp"] = hist_merge["AlimIdealAcum_comp"].diff()
    if not hist_merge.empty:
        hist_merge.loc[hist_merge.index[0], "AlimIdealDia_comp"] = hist_merge.iloc[0]["AlimIdealAcum_comp"]

    # Regla: no hay consumo negativo
    hist_merge["AlimIdealDia_comp"] = hist_merge["AlimIdealDia_comp"].clip(lower=0)

    # Regla: si el lote real no consumió alimento ese día, el ideal tampoco debe costearse
    if "_alim_dia" in hist_merge.columns:
        mask_sin_gasto = _safe_num(hist_merge["_alim_dia"]).fillna(0).eq(0)
        hist_merge.loc[mask_sin_gasto, "AlimIdealDia_comp"] = 0

    hist_merge["CostoIdealDia_comp"] = hist_merge["AlimIdealDia_comp"] * hist_merge["PrecioKgRealDia"]
    hist_merge["CostoIdealDia_comp"] = hist_merge["CostoIdealDia_comp"].fillna(0)
    hist_merge["CostoIdealComp"] = hist_merge["CostoIdealDia_comp"].cumsum()
    hist_merge["GapCostoComp"] = hist_merge["CostoAcum"] - hist_merge["CostoIdealComp"]

    return hist_merge


# ──────────────────────────────────────────────────────────────
# ENRIQUECER TODO EL HISTÓRICO CON IDEAL COMPARABLE
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def enriquecer_historial_con_ideal(
    df_hist: pd.DataFrame,
    ideales_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Enriquece TODO el histórico real con columnas del ideal comparable.
    Esto se ejecuta una sola vez y luego todos los gráficos reutilizan
    estas columnas ya calculadas.
    """
    if df_hist.empty:
        return df_hist.copy()

    if ideales_df is None or ideales_df.empty:
        return _empty_comp_columns(df_hist)

    base = df_hist.copy().sort_values(["LoteCompleto", "Edad"]).reset_index(drop=True)
    base = resolver_precio_kg_real(base)

    resultados = []

    for lote, hist_lote in base.groupby("LoteCompleto", sort=False):
        hist_lote = hist_lote.copy().sort_values("Edad").reset_index(drop=True)

        zona = hist_lote["ZonaNombre"].iloc[0] if "ZonaNombre" in hist_lote.columns else None
        tipo = hist_lote["TipoStd"].iloc[0] if "TipoStd" in hist_lote.columns else None
        quint = hist_lote["Quintil"].iloc[0] if "Quintil" in hist_lote.columns else None
        repro = hist_lote["ReproductoraStd"].iloc[0] if "ReproductoraStd" in hist_lote.columns else "SIN_DATO"

        ideal_sub = _filtrar_ideal_sub(
            ideales_df=ideales_df,
            zona=zona,
            tipo=tipo,
            quint=quint,
            reproductora=repro,
        )

        hist_comp = construir_historial_ideal_comparable(hist_lote, ideal_sub)
        resultados.append(hist_comp)

    if not resultados:
        return _empty_comp_columns(base)

    out = pd.concat(resultados, ignore_index=True)
    return out.sort_values(["LoteCompleto", "Edad"]).reset_index(drop=True)


# ──────────────────────────────────────────────────────────────
# GAPS vs IDEAL · peso promedio de lote vs benchmark
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
        repro = snap["ReproductoraStd"] if "ReproductoraStd" in snap.index else "SIN_DATO"

        ideal = _filtrar_ideal_sub(
            ideales_df=ideales_df,
            zona=snap["ZonaNombre"],
            tipo=snap["TipoStd"],
            quint=snap["Quintil"],
            reproductora=repro,
        )

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
# GAP FCR / COSTO POR GALPÓN
# ──────────────────────────────────────────────────────────────
def calcular_fcr_gaps_galpones(snap_df: pd.DataFrame, ideales_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula gap por lote-galpón usando el snapshot ya enriquecido.
    Si el snapshot proviene de enriquecer_historial_con_ideal(), entonces:
      - CostoIdeal = CostoIdealComp
      - GapCosto   = GapCostoComp
      - FCR_ideal  = FCR_ideal del benchmark emparejado por edad
    """
    if snap_df.empty:
        return pd.DataFrame()

    snap = snap_df.copy()

    snap = _ensure_columns(
        snap,
        [
            "GranjaID", "Granja", "NombreGranja", "Galpon", "LoteCompleto", "Edad",
            "AvesVivas", "KgLive", "PrecioKgRealDia", "PrecioKg",
            "PesoIdeal_comp", "KgLiveIdeal_comp", "AlimIdealAcum_comp",
            "FCR_Cum", "FCR_ideal", "CostoAcum", "CostoIdealComp", "GapCostoComp",
            "ZonaNombre", "TipoStd", "Quintil", "ReproductoraStd"
        ]
    )

    filas = []
    for _, row in snap.iterrows():
        edad_lote = int(row.get("Edad", 0) or 0)
        if edad_lote < EDAD_MIN_ANALISIS:
            continue

        fcr_real = _safe_num(pd.Series([row.get("FCR_Cum", np.nan)])).iloc[0]
        fcr_ideal = _safe_num(pd.Series([row.get("FCR_ideal", np.nan)])).iloc[0]

        costo_real = _safe_num(pd.Series([row.get("CostoAcum", np.nan)])).iloc[0]
        costo_ideal = _safe_num(pd.Series([row.get("CostoIdealComp", np.nan)])).iloc[0]
        gap_costo = _safe_num(pd.Series([row.get("GapCostoComp", np.nan)])).iloc[0]

        kg_live_real = _safe_num(pd.Series([row.get("KgLive", np.nan)])).iloc[0]
        precio_kg_real = _safe_num(pd.Series([row.get("PrecioKgRealDia", np.nan)])).iloc[0]
        if pd.isna(precio_kg_real):
            precio_kg_real = _safe_num(pd.Series([row.get("PrecioKg", np.nan)])).iloc[0]

        gap_fcr = (
            fcr_real - fcr_ideal
            if pd.notna(fcr_real) and pd.notna(fcr_ideal)
            else np.nan
        )

        gap_costo_kg = (
            gap_costo / kg_live_real
            if pd.notna(gap_costo) and pd.notna(kg_live_real) and kg_live_real > 0
            else np.nan
        )

        filas.append({
            "Granja":           str(row.get("GranjaID", row.get("Granja", "—"))),
            "NombreGranja":     str(row.get("NombreGranja", "—")),
            "Galpon":           row.get("Galpon", "—"),
            "LoteCompleto":     row["LoteCompleto"],
            "Edad":             edad_lote,

            "AvesVivas":        row.get("AvesVivas", np.nan),
            "KgLive":           kg_live_real,
            "PesoIdeal":        row.get("PesoIdeal_comp", np.nan),
            "KgLiveIdeal":      row.get("KgLiveIdeal_comp", np.nan),
            "PrecioKgReal":     precio_kg_real,
            "AlimIdealAcum":    row.get("AlimIdealAcum_comp", np.nan),

            "FCR_real":         round(float(fcr_real), 4) if pd.notna(fcr_real) else np.nan,
            "FCR_ideal":        round(float(fcr_ideal), 4) if pd.notna(fcr_ideal) else np.nan,
            "Gap_FCR":          round(float(gap_fcr), 4) if pd.notna(gap_fcr) else np.nan,

            "CostoReal":        costo_real,
            "CostoIdeal":       costo_ideal,
            "GapCosto":         gap_costo,
            "GapCostoKg":       gap_costo_kg,

            "ZonaNombre":       row.get("ZonaNombre", np.nan),
            "TipoStd":          row.get("TipoStd", np.nan),
            "Quintil":          row.get("Quintil", np.nan),
            "ReproductoraStd":  row.get("ReproductoraStd", np.nan),
        })

    return pd.DataFrame(filas)


# ──────────────────────────────────────────────────────────────
# RESUMEN A NIVEL DE GRANJA
# ──────────────────────────────────────────────────────────────
def calcular_fcr_gaps_granjas(gaps_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """
    Resume por granja el sobrecosto recalculado vs ideal comparable.
    """
    if gaps_df.empty:
        return pd.DataFrame()

    con_prob = gaps_df[gaps_df["GapCosto"] > 0].copy()
    if con_prob.empty:
        return pd.DataFrame()

    grp = (
        con_prob.groupby(["Granja", "NombreGranja"])
        .agg(
            NumGalpones     = ("Galpon", "nunique"),
            KgLiveTotal     = ("KgLive", "sum"),
            FCR_real        = ("FCR_real", "mean"),
            FCR_ideal       = ("FCR_ideal", "mean"),
            Gap_FCR_medio   = ("Gap_FCR", "mean"),
            CostoRealTotal  = ("CostoReal", "sum"),
            CostoIdealTotal = ("CostoIdeal", "sum"),
            GapCostoTotal   = ("GapCosto", "sum"),
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
# CURVA IDEAL PROMEDIADA PARA UN LOTE
# ──────────────────────────────────────────────────────────────
def get_curva_ideal_promedio(
    zona: str,
    tipo: str,
    quintil: str,
    ideales_df: pd.DataFrame,
    edad_max: int | None = None,
    reproductora: str | None = None,
) -> pd.DataFrame:
    sub = _filtrar_ideal_sub(
        ideales_df=ideales_df,
        zona=zona,
        tipo=tipo,
        quint=quintil,
        reproductora=reproductora,
    ).copy()

    if sub.empty:
        return pd.DataFrame()

    agg_dict = {}
    if "Peso" in sub.columns:
        agg_dict["Peso"] = ("Peso", "mean")
    if "FCR_ideal" in sub.columns:
        agg_dict["FCR_ideal"] = ("FCR_ideal", "mean")
    if "costo_alimento_acumulado" in sub.columns:
        agg_dict["CostoAcum_ideal"] = ("costo_alimento_acumulado", "mean")
    if "costo_alimento_dia" in sub.columns:
        agg_dict["CostoDia_ideal"] = ("costo_alimento_dia", "mean")

    if not agg_dict:
        return pd.DataFrame()

    cur = sub.groupby("Edad").agg(**agg_dict).reset_index().sort_values("Edad")

    if edad_max is not None:
        cur = cur[cur["Edad"] <= edad_max + 1]

    return cur


# ══════════════════════════════════════════════════════════════
# TOP 10 PEORES GRANJAS POR CONVERSIÓN ALIMENTICIA
# ══════════════════════════════════════════════════════════════
def agrupar_granjalote(df):
    """
    Agrupa por LoteCompleto (GRANJA-LOTE) y toma el último registro.
    """
    df = df.copy()
    df["Granja"] = df["LoteCompleto"].astype(str).str.split("-").str[0]

    alim_col = "AlimAcumKg" if "AlimAcumKg" in df.columns else (
        "Alimento_Acumulado" if "Alimento_Acumulado" in df.columns else None
    )
    peso_col = "PesoFinal" if "PesoFinal" in df.columns else (
        "Peso" if "Peso" in df.columns else None
    )
    costo_col = "CostoAcum" if "CostoAcum" in df.columns else "costo_alimento_acumulado"
    galpon_col = "Galpon" if "Galpon" in df.columns else None

    conv_col = "conversio alimenticia" if "conversio alimenticia" in df.columns else "FCR_Cum"

    agg_dict = {
        conv_col:        "last",
        "Granja":        "first",
        "NombreGranja":  "first" if "NombreGranja" in df.columns else "first",
        "ReproductoraStd": "first" if "ReproductoraStd" in df.columns else "first",
        costo_col:       "max",
        "Edad":          "max",
    }

    if "Codigo_Unico" in df.columns:
        agg_dict["Codigo_Unico"] = "first"
    if alim_col:
        agg_dict[alim_col] = "max"
    if peso_col:
        agg_dict[peso_col] = "max"
    if galpon_col:
        agg_dict[galpon_col] = "first"

    df_granjalote = (
        df.sort_values(["LoteCompleto", "Edad"])
        .groupby("LoteCompleto")
        .agg(agg_dict)
        .reset_index()
    )

    rename_map = {
        conv_col:  "Conv_GranjaLote",
        costo_col: "CostoAcum",
    }
    if alim_col:
        rename_map[alim_col] = "AlimAcumKg"
    if peso_col:
        rename_map[peso_col] = "Peso"

    df_granjalote = df_granjalote.rename(columns=rename_map)
    return df_granjalote


def agrupar_granjas_top10(df_granjalote, top_n=10):
    """
    Agrupa por granja y calcula FCR promedio de sus lotes.
    """
    agg_dict = {
        "LoteCompleto":    "count",
        "Conv_GranjaLote": ["mean", "max", "min"],
        "CostoAcum":       "sum",
    }

    if "NombreGranja" in df_granjalote.columns:
        agg_dict["NombreGranja"] = "first"
    if "ReproductoraStd" in df_granjalote.columns:
        agg_dict["ReproductoraStd"] = "first"
    if "AlimAcumKg" in df_granjalote.columns:
        agg_dict["AlimAcumKg"] = "sum"
    if "Edad" in df_granjalote.columns:
        agg_dict["Edad"] = "mean"

    df_granjas = df_granjalote.groupby("Granja").agg(agg_dict).reset_index()

    df_granjas.columns = [
        "_".join(c).strip("_") if isinstance(c, tuple) else c
        for c in df_granjas.columns
    ]

    col_map = {
        "LoteCompleto_count":   "NumLotes",
        "Conv_GranjaLote_mean": "Conv_Promedio",
        "Conv_GranjaLote_max":  "Conv_Max",
        "Conv_GranjaLote_min":  "Conv_Min",
        "CostoAcum_sum":        "CostoTotal",
        "NombreGranja_first":   "NombreGranja",
        "ReproductoraStd_first": "ReproductoraStd",
        "AlimAcumKg_sum":       "AlimTotal",
        "Edad_mean":            "EdadPromedio",
    }
    df_granjas = df_granjas.rename(columns={k: v for k, v in col_map.items() if k in df_granjas.columns})

    return df_granjas.sort_values("Conv_Promedio", ascending=False).head(top_n).reset_index(drop=True)


def filtrar_lotes_granja(df_granjalote, granja_codigo):
    """
    Devuelve los lotes/galpones de una granja, ordenados por peor FCR primero.
    """
    lotes = df_granjalote[df_granjalote["Granja"] == granja_codigo].copy()
    return lotes.sort_values("Conv_GranjaLote", ascending=False).reset_index(drop=True)