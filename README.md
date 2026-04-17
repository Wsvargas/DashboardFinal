# 📊 Guía de Modularización - Dashboard PRONACA v15

## 📁 Estructura de Archivos

```
├── app.py                          # MAIN - Orquestador principal (muy limpio)
├── dashboard_kpis.py              # KPIs globales + formatters comunes
├── dashboard_sec01.py             # Sección 01: Resumen por Etapa
├── dashboard_sec02.py             # Sección 02: Top 10 Granjas
├── dashboard_sec03.py             # Sección 03: Lote Seleccionado (IDEAL vs REAL)
├── dashboard_sec04.py             # Sección 04: Predicción (Día 35)
│
├── config.py                      # (Ya existía) - Configuración global
├── helpers.py                     # (Ya existía) - Funciones auxiliares
├── styles.py                      # (Ya existía) - CSS/Estilos
├── data_loader.py                 # (Ya existía) - Carga de datos
├── model_predictor.py             # (Ya existía) - Predictor ML
└── tool_predictiva.py             # (Ya existía) - Herramienta de predicción
```

## 🏗️ Arquitectura

### Flujo Principal (`app.py`)

```python
1. Configuración (page_config, CSS)
2. Router (dashboard / predictiva)
3. Carga de datos (DF_ALL, IDEALES, SNAP, DF_FILTRADO)
4. Filtros globales (zona, tipo, quintil, estado)
5. Render KPIs globales
6. Layout 2 columnas (left, right)
   ├── LEFT (Secciones 01, 02, 03)
   └── RIGHT (Sección 04)
```

### Secciones Independientes

#### **SEC 01** (`dashboard_sec01.py`)
- ✅ Gráfico horizontal de lotes por etapa
- ✅ Tabla resumen por etapa
- 📤 **Output:** `etapas_sel` (lista de etapas seleccionadas)

#### **SEC 02** (`dashboard_sec02.py`)
- ✅ Top 10 Granjas por sobrecosto
- ✅ Tabla de galpones por granja
- 📤 **Output:** `lote_sel` (lote seleccionado en la tabla)

#### **SEC 03** (`dashboard_sec03.py`)
- ✅ Tarjetas KPI del lote
- ✅ Gráfico: Peso REAL vs IDEAL
- ✅ Gráfico: Costo REAL vs IDEAL
- 📥 **Input:** `lote_sel` (del sec02)

#### **SEC 04** (`dashboard_sec04.py`)
- ✅ Predicción ML al día 35
- ✅ Gráfico: REAL vs IDEAL vs PROYECCIÓN
- 📥 **Input:** `lote_sel` (del sec02)

---

## 🔄 Flujo de Datos Entre Secciones

```
SEC 01 (etapas)
   ↓
   └─→ Filtra SF por etapas seleccionadas
   
SEC 02 (lote_sel)
   ↓
   └─→ Guardado en st.session_state["lote_sel_sec03"]
   
SEC 03 & SEC 04 (usan lote_sel)
   ↓
   └─→ Muestran análisis detallado
```

---

## 📋 Funciones Principales por Módulo

### `dashboard_kpis.py`
```python
fmt_manager(n, prefix, suffix)        # Formatea números (1M, 1.5 mil, etc)
fmt_signed_short(n, prefix, suffix)   # Formatea con signo (+/-nnnn)
render_kpi_small(value_html, label)   # Renderiza tarjeta KPI
render_kpis_globales(SF)              # Renderiza 6 KPIs superiores
```

### `dashboard_sec01.py`
```python
render_sec01(SF, DF_HIST_COMP) → etapas_sel
  └─ Crea gráfico de barras por etapa
  └─ Retorna etapas seleccionadas por usuario
```

### `dashboard_sec02.py`
```python
render_sec02(SF_02, DF_HIST_COMP, IDEALES) → lote_sel
  └─ Calcula gaps de costo por galpón
  └─ Top 10 granjas por sobrecosto
  └─ Tabla de galpones por granja seleccionada
  └─ Retorna lote/galpón seleccionado
```

### `dashboard_sec03.py`
```python
normalizar_historico(hist_cmp)        # Convierte a numéricos + alias
extraer_metricas_lote(hist_cmp)       # Extrae KPIs finales
render_tarjetas_lote(...)             # Renderiza identidad + KPIs
render_grafico_crecimiento(...)       # Gráfico Peso REAL vs IDEAL
render_grafico_costo(...)             # Gráfico Costo REAL vs IDEAL
render_sec03(lote_sel, SF, ...)       # Orquesta toda la sección
```

### `dashboard_sec04.py`
```python
render_sec04(lote_sel, SF, ...) → None
  └─ Carga/cachea predictor ML
  └─ Calcula curva ideal extendida
  └─ Proyecta curva con adjust de ancla
  └─ Renderiza gráfico REAL + IDEAL + PROYECCIÓN
```

---

## 🛠️ Cómo Añadir Nuevas Características

### Ejemplo 1: Añadir métrica a KPI global

**Archivo:** `dashboard_kpis.py`
```python
def render_kpis_globales(SF):
    # ... código existente ...
    
    # NUEVA MÉTRICA
    nuevametrica = SF["AlgunaColumna"].sum()
    
    k7.write(f"Métrica: {fmt_manager(nuevametrica)}")
```

### Ejemplo 2: Añadir filtro global

**Archivo:** `app.py`
```python
# DESPUÉS de los filtros existentes:
with fc5:
    sel_nuevo = st.multiselect("🔍 Nuevo Filtro", [...], default=[...])

# APLICAR FILTRO:
SF = SF[SF["ColumnaFiltro"].isin(sel_nuevo)]
```

### Ejemplo 3: Añadir nueva sección (SEC 05)

1. **Crear archivo:** `dashboard_sec05.py`
```python
def render_sec05(lote_sel, SF, DF_FILTRADO):
    md("""<div class="sec-header">
      <span class="sec-num">05</span>
      <div><div class="sec-title">Tu Sección Nueva</div></div>
    </div>""")
    # Tu código aquí
```

2. **Importar en `app.py`:**
```python
from dashboard_sec05 import render_sec05
```

3. **Llamar en el layout :**
```python
with left:  # o with right:
    render_sec05(lote_sel, SF, DF_FILTRADO)
```

---

## 🎯 Mejores Prácticas

### ✅ QUÉ SÍ:
- Mantener funciones pequeñas y enfocadas (< 50 líneas idealmente)
- Usar docstrings en funciones importantes
- Parametrizar valores hardcodeados (ej: `TARGET_DAY = 35`)
- Separar lógica de datos de lógica de rendering
- Cachear cálculos costosos con `@st.cache_resource`
- Usar `pd.to_numeric(..., errors="coerce")` para conversiones

### ❌ QUÉ NO:
- Mezclar lógica de datos con HTML/CSS
- Hardcodear valores en múltiples lugares
- Crear funciones con >100 líneas sin motivo
- Renderizar sin validar datos antes
- Usar variables globales innecesariamente

---

## 🔧 Debugging & Testing Local

### Correr el app
```bash
streamlit run app.py
```

### Logging
```python
import streamlit as st

# En desarrollo, mostrar info:
if st.checkbox("🐛 Debug Mode"):
    st.write(f"Lote seleccionado: {lote_sel}")
    st.write(df.head())
```

### Cachés
- Limpiar cachés: `streamlit run app.py --logger.level=debug`
- O manualmente: `st.cache_data.clear()`

---

## 📊 Columnas de Datos Esperadas

### Snapshot (SNAP / SF)
```
LoteCompleto, ZonaNombre, TipoStd, Quintil, EstadoLote, Etapa,
Edad, AvesVivas, KgLive, CostoAcum, AlimAcumKg, MortPct, ...
```

### Histórico (DF_HIST_COMP)
```
LoteCompleto, Edad, PesoFinal, AvesVivas, CostoAcum,
AlimAcumKg, FCR_Cum, FCR_ideal, CostoIdealComp, GapCostoComp,
PesoIdeal_comp, KgLiveIdeal_comp, ...
```

### Ideales (IDEALES)
```
ZonaNombre, TipoStd, Quintil, Edad, FCR_ideal, PesoIdeal, ...
```

---

## 📈 Performance Tips

1. **Filtrar temprano:** Aplicar filtros globales lo antes posible
2. **Cachear datos:** 
   ```python
   @st.cache_data
   def cargar_datos():
       return load_and_prepare(MAIN_FILE)
   ```
3. **Evitar reordenamientos múltiples:**
   ```python
   # ❌ MAL:
   df = df.sort_values("col1")
   df = df.sort_values("col2")
   
   # ✅ BIEN:
   df = df.sort_values(["col1", "col2"])
   ```

---

## 🚀 Próximos Pasos de Mejora

- [ ] Extraer formatters a módulo separado
- [ ] Crear tests unitarios para cada sección
- [ ] Agregar export a Excel/PDF
- [ ] Sistema de alertas automáticas
- [ ] API para integración con otros sistemas

---

## 📞 Referencia Rápida

| Tarea | Archivo | Función |
|-------|---------|---------|
| Cambiar color de gráfico | `dashboard_secXX.py` | `fig.update_layout(...)` |
| Agregar KPI | `dashboard_kpis.py` | `render_kpis_globales()` |
| Nueva sección | `dashboard_secNN.py` | `render_secNN(...)` |
| Estilos CSS | `styles.py` | `inject_css()` |
| Carga de datos | `data_loader.py` | Funciones existentes |
| Configuración | `config.py` | Constantes globales |

---

**Versión:** 1.0  
**Última actualización:** Marzo 2026  
**Autor:** PRONACA Analytics Team
