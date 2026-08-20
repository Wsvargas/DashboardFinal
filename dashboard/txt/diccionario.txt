"""
Diccionario de términos del dashboard — popup modal ejecutivo.
Explica cada indicador, clasificación y concepto que aparece en pantalla.

Todo el contenido se renderiza dentro de una tarjeta blanca propia para
que sea legible sin importar el tema (claro u oscuro) de Streamlit.
"""

import streamlit as st

from config import RED, BORDER
from core.helpers import md

# Colores fijos sobre la tarjeta blanca (independientes del tema)
_TXT  = "#0F172A"
_MUT  = "#64748B"


def _termino(nombre: str, definicion: str) -> str:
    return f"""
<div style="padding:6px 0;border-bottom:1px solid {BORDER};">
  <span style="font-weight:800;color:{_TXT};font-size:.85rem;">{nombre}</span><br>
  <span style="color:{_MUT};font-size:.8rem;line-height:1.45;">{definicion}</span>
</div>"""


def _seccion(titulo: str) -> str:
    return f"""
<div style="font-weight:900;color:{RED};font-size:.78rem;text-transform:uppercase;
            letter-spacing:.6px;margin:14px 0 2px 0;">{titulo}</div>"""


@st.dialog("📖 Diccionario del Dashboard", width="large")
def mostrar_diccionario():
    partes = []

    partes.append(_seccion("Identificación"))
    partes.append(_termino(
        "Lote (LoteCompleto)",
        "Grupo de aves criadas juntas en un galpón. Formato del código: "
        "GRANJA-LOTE-GALPÓN-SEXO (ej. BUC3023-2602-02-M). M=macho, H=hembra, S=mixto.",
    ))
    partes.append(_termino(
        "Galpón",
        "Instalación física dentro de una granja donde se aloja un lote.",
    ))
    partes.append(_termino(
        "Estado ABIERTO / CERRADO",
        "ABIERTO: lote aún en crianza (producción activa). "
        "CERRADO: lote ya enviado a planta, con peso de venta real registrado.",
    ))

    partes.append(_seccion("Indicadores productivos"))
    partes.append(_termino(
        "Kg live",
        "Biomasa total del lote: aves vivas × peso promedio por ave. "
        "Es el kilaje de carne en pie que existe hoy.",
    ))
    partes.append(_termino(
        "Conversión alimenticia (FCR / Conv)",
        "Kg de alimento consumido por cada kg de peso vivo producido. "
        "Menor es mejor: FCR 1.6 significa que se necesitaron 1.6 kg de alimento "
        "por cada kg de pollo.",
    ))
    partes.append(_termino(
        "Mortalidad % (M%)",
        "Porcentaje acumulado de aves muertas + descartadas sobre las aves iniciales del lote.",
    ))
    partes.append(_termino(
        "Aves/m²",
        "Densidad del galpón: aves vivas por metro cuadrado de área de crianza.",
    ))
    partes.append(_termino(
        "Etapas del ciclo",
        "INICIO (día 1-14) · CRECIMIENTO (15-28) · PRE-ACABADO (29-35) · ACABADO (36+). "
        "El ciclo comercial típico termina entre el día 35 y 45.",
    ))

    partes.append(_seccion("Costos"))
    partes.append(_termino(
        "Costo total / Costo acumulado",
        "Dólares gastados en alimento del lote hasta la fecha, valorados al precio "
        "real del alimento de cada día (no un promedio genérico).",
    ))
    partes.append(_termino(
        "Costo medio/kg ($UKg)",
        "Costo de alimento acumulado dividido por los kg live actuales. "
        "Cuánto ha costado producir cada kg de carne en pie.",
    ))
    partes.append(_termino(
        "Precio/kg real",
        "Precio del alimento del día, según las compras registradas del lote. "
        "Si un día no hay compra, se arrastra el último precio conocido.",
    ))

    partes.append(_seccion("Comparación vs ideal"))
    partes.append(_termino(
        "Ideal / Curva ideal",
        "Benchmark de referencia: cómo debería crecer y cuánto debería costar un lote "
        "del mismo escenario. No es una meta genérica — es específica por escenario.",
    ))
    partes.append(_termino(
        "Escenario",
        "Combinación Zona + Tipo de granja + Reproductora + Quintil que determina "
        "qué curva ideal le corresponde a cada lote (ej. BUC_PCA_Adulta_Q2).",
    ))
    partes.append(_termino(
        "Gap / Sobrecosto vs ideal",
        "Costo real − costo ideal comparable. El costo ideal se calcula con el "
        "mismo precio de alimento del lote, por lo que la comparación es justa. "
        "Positivo = el lote está gastando más de lo que debería.",
    ))
    partes.append(_termino(
        "Gap Con (Gap de conversión)",
        "Conversión real − conversión ideal. Positivo = el lote necesita más "
        "alimento por kg producido de lo que debería.",
    ))
    partes.append(_termino(
        "Ahorro potencial",
        "Suma de los sobrecostos de los lotes con desvío: cuánto se ahorraría "
        "si esos lotes operaran en su ideal comparable.",
    ))

    partes.append(_seccion("Abreviaturas de las tablas"))
    partes.append(_termino(
        "$ALI",
        "Costo de alimento acumulado del grupo (en dólares).",
    ))
    partes.append(_termino(
        "Con Real / Con Ideal",
        "Conversión alimenticia real del lote vs la conversión ideal de su escenario.",
    ))
    partes.append(_termino(
        "Real vs Ideal",
        "Diferencia de costo en dólares entre lo que el lote gastó y lo que "
        "debería haber gastado según su ideal comparable.",
    ))
    partes.append(_termino(
        "Costo real / Costo ideal",
        "Costo de alimento efectivamente gastado vs el costo que tendría el lote "
        "si creciera y convirtiera según su curva ideal, al mismo precio de alimento.",
    ))
    partes.append(_termino(
        "Día hoy / Días",
        "Edad actual del lote en días desde el alojamiento.",
    ))
    partes.append(_termino(
        "Proy. D35 / Ideal D35",
        "Peso proyectado por el modelo al día 35 vs el peso que marca la curva "
        "ideal del escenario en ese mismo día.",
    ))
    partes.append(_termino(
        "Déficit g/ave",
        "Gramos que le faltarían a cada ave al día 35 respecto a su ideal, "
        "según la proyección del modelo.",
    ))
    partes.append(_termino(
        "Kg en riesgo",
        "Déficit por ave × aves vivas del lote: kilos de carne en pie que se "
        "dejarían de producir si no se interviene.",
    ))
    partes.append(_termino(
        "Piso probable",
        "Límite inferior de la banda de predicción (cuantil 10): el peso mínimo "
        "razonable que tendría el lote en un escenario pesimista.",
    ))

    partes.append(_seccion("Clasificaciones"))
    partes.append(_termino(
        "Quintil (Q1–Q5)",
        "Clasificación de granjas por área de crianza en 5 grupos. "
        "Los benchmarks respetan este nivel: una granja Q1 no se compara contra el ideal de una Q5.",
    ))
    partes.append(_termino(
        "Reproductora (Joven / Adulta / Vieja)",
        "Edad de la reproductora de origen del lote: Joven &lt;35 semanas, "
        "Adulta 35-50, Vieja 51+. Afecta la curva de crecimiento esperada del pollito.",
    ))
    partes.append(_termino(
        "Guarda (Óptima / Moderada / Crítica)",
        "Días de descanso del galpón entre camadas: Óptima 3-6 días, "
        "Moderada 7-12, Crítica 13+.",
    ))
    partes.append(_termino(
        "Zona (BUCAY / SANTO DOMINGO)",
        "Ubicación geográfica de la granja. Cada zona tiene sus propias curvas ideales.",
    ))
    partes.append(_termino(
        "Tipo (PROPIA / PAC)",
        "PROPIA: granja de la empresa. PAC: granja de productor asociado/integrado.",
    ))

    partes.append(_seccion("Predicción"))
    partes.append(_termino(
        "Peso proyectado D35",
        "Peso promedio por ave que el modelo de machine learning (CatBoost) estima "
        "que tendrá el lote al día 35, según su desempeño actual.",
    ))
    partes.append(_termino(
        "Rango probable / Banda 80%",
        "Intervalo dentro del cual caerá el peso real en ~8 de cada 10 casos.",
    ))
    partes.append(_termino(
        "Lotes en Riesgo",
        "Lotes abiertos cuya proyección al día 35 queda por debajo de su ideal: "
        "🟠 ALERTA con déficit ≥ 3% · 🔴 CRÍTICO con déficit ≥ 6%.",
    ))
    partes.append(_termino(
        "Error del modelo (±g)",
        "Error promedio de las predicciones al validar el modelo con lotes históricos "
        "que nunca vio durante el entrenamiento. Ej: ±48 g significa que en promedio "
        "la predicción se desvía 48 gramos del peso real.",
    ))

    # Tarjeta blanca autocontenida: legible en tema claro u oscuro
    md(f"""
<div style="background:#FFFFFF;border:1px solid {BORDER};border-radius:12px;
            padding:6px 18px 14px 18px;">
{"".join(partes)}
</div>""")
