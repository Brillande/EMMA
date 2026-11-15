"""Simulador fisiologico de telemetria de tripulacion.

No existe una API publica de signos vitales de astronautas en tiempo real: son
datos medicos protegidos. Este simulador genera series calibradas con la
literatura de la NASA y del Human Research Program para poder ejercitar el motor
de analisis con derivas realistas.

**Determinista por semilla**: la misma semilla produce exactamente la misma serie.
Es requisito de verificacion — sin reproducibilidad no se puede afirmar que una
alerta se disparo por la razon que se cree.

HONESTIDAD SOBRE LOS PARAMETROS
-------------------------------
Cada valor de `LITERATURE` declara que clase de respaldo tiene. Son tres con
respaldo y dos sin el, y la distincion importa: "contestado" no es lo mismo que
"sin comprobar", ni "se busco y no se encontro" lo mismo que "no se busco".

  `established`     magnitud documentada de forma consistente.
  `direction_only`  el **sentido** del cambio esta documentado, pero no hay una
                    magnitud por semana citable. El valor es una interpolacion
                    razonable a partir del cambio total observado.
  `contested`       los estudios **discrepan**. El modelo usa una deriva muy
                    pequena a proposito, o ninguna: inventar una tendencia clara
                    donde la ciencia no la tiene seria peor que no modelarla. Las
                    excepciones lo dicen en su nota: una deriva de diseno que se
                    reclasifica conserva el valor que tenia hasta que el usuario
                    decida sobre el (la RMSSD y la presion arterial, 2026-10-31).
  `unsupported`     **sin respaldo en lo leido**: se busco, y lo leido no respalda la
                    deriva que el parametro nombra. Declara donde se busco
                    (`searched`) y las fichas de lo leido (`refs`). Con valor 0 el
                    modelo no la aplica; con otro valor, es el de antes mientras el
                    usuario decide. No es una clase de evidencia.
  `design`          **sin respaldo escrito en el repositorio**. Valor de diseno de
                    EMMA, elegido para que el escenario se vea en la demo. No es
                    una clase de evidencia: es la declaracion de que no la hay.

HABIA DERIVAS SIN CLASE. La regla de arriba se cumplia para lo que estaba en
`LITERATURE`, pero varias derivas vivian como numeros sueltos en los modelos y en
los escenarios (-0,6 min de ejercicio, -40 impactos, las de cada escenario): el
simulador decia "cada parametro declara su respaldo" y la mitad no pasaba por
ahi. Ahora toda deriva sale de `LITERATURE`, y una prueba lee este fichero y falla
si una vuelve a escribirse a mano. A las que no tenian fuente no se les ha buscado
una: quedan como `design`, con sus valores intactos.

La revision bibliografica se hizo el 2026-09-20 y corrigio dos parametros que
estaban mal:

  - La caida de SDNN en vuelo **no esta respaldada**. Hay estudios que no
    encuentran diferencias y otros que ven tendencia creciente, hablando de
    plasticidad mas que de declive. Paso de -1,5 ms/semana a `contested`.
  - La subida de FC en reposo era el doble de lo observado: la literatura
    reporta ~54,9 -> 60,0 lpm en misiones de 2-6 meses, no ~9,6 lpm.

Y aquella correccion tambien estaba mal. LO LEIDO EL 2026-10-22 Y EL 2026-10-23
(decimoquinta ronda, D14; decimosexta, E18) contradice dos derivas del modelo
nominal, y se reclasifican SIN cambiar su valor (decision del plan: el valor lo
decide el usuario con la medida de su efecto delante, en
compliance/clinical-decision-rationale.md):

  - `resting_hr_drift_bpm_per_week`: los 54,9 -> 60,0 lpm de Hughson 2012 son de
    DESPUES del vuelo. En vuelo, cuatro estudios ven la FC sin cambio (Hughson
    2012, Xu 2013, Fraser 2012, Baevsky 2007) y uno, con dos tripulantes de la
    Mir, la ve subir (Baevsky 1997). Pasa a `contested`, con el peso de lo leido
    del lado de "sin cambio".
  - `cortisol_rise_per_week`: nada de lo leido dice que el cortisol salival suba
    en vuelo (Mehta 2017: cambia su trayectoria diurna; Buchheim 2019: no cambia
    de forma significativa, sin decir el resumen si en las muestras de vuelo o en
    las de despues). Pasa a `unsupported`. Al cerrar la ronda decimonovena, leido
    Vorobiev 1995 (sube, dos cosmonautas), pasa a `contested`, con el valor en 0.

Y el 2026-10-26 (decimoctava ronda, §5.38.10, decision del usuario) una tercera,
tambien con su valor de siempre:

  - `menu_fatigue_acceptability_drop_per_week`: de `contested` a `unsupported`.
    El unico estudio en vuelo leido (Douglas 2025, ISS) no ve bajar la
    aceptabilidad; el que la ve bajar (Meiselman 2000) es de Tierra con la misma
    comida cinco dias seguidos, y el resumen leido de Sirius-21 no da resultados.

Y EL 2026-10-31 (decimonovena ronda, U22) el usuario decidio sobre las dos derivas
de arriba y sobre cuatro de diseno que lo leido ya juzgaba
(compliance/clinical-decision-rationale.md, «Revision de lo leido (2026-10-31)»; lo
que cambio al corregirlas, medido, en compliance/hmi-state-of-the-art.md §5.39.22):

  - `resting_hr_drift_bpm_per_week` y `cortisol_rise_per_week` pasan a 0 (la segunda, contestada
    tras leer a Vorobiev 1995 y no «sin respaldo»; §5.39.6): el modelo
    nominal ya no sube la FC en reposo ni el cortisol salival en vuelo. Las dos quedan
    en `contested`: la clase dice que leyo EMMA; el valor, que hace el modelo con ello.
  - `systolic_bp_decline_mmhg_per_week` y `diastolic_bp_decline_mmhg_per_week`: de
    `design` a `contested` (Hughson 2012 sin cambio frente a Norsk 2015 y Baevsky
    2007, que las ven bajar), con su valor.
  - `ntx_rise_per_week`: de `design` a `direction_only` (Smith 2005 y Smith 2012: los
    marcadores de resorcion suben en vuelo), con su valor.
  - `hrv_rmssd_decline_ms_per_week`: de `design` a `contested`, con su valor. La
    decision decia «sentido documentado» a partir de la nota del 2026-10-23, escrita
    sobre una lectura que entonces daba la RMSSD a la baja (Xu 2013, Hughson 2012);
    ese mismo dia la lectura del sentido en vuelo (E16) anadio a Baevsky 2007, que no
    ve cambio en la banda de alta frecuencia, y desde entonces la da por discutida
    (el fichero del sentido en vuelo, en `app/data/`; el simulador no lo lee). El
    simulador dice lo mismo que la lectura; si el usuario prefiere «sentido
    documentado», es un cambio de una linea.

`refs` nombra por identificador las fichas de `data/evidence_refs.json` que
sostienen la nota; una que no exista hace fallar las pruebas.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

import numpy as np

from app.ingest.codes import CATALOG, Domain
from app.ingest.fhir import Context, EvidenceContext, VitalObservation, observation
from app.ingest.habitat_simulator import co2_ramp


class Scenario(StrEnum):
    """Escenarios de demo. Cada uno debe disparar una alerta concreta."""

    NOMINAL = "nominal"
    SPE_EVENT = "spe-event"
    PROGRESSIVE_INSOMNIA = "progressive-insomnia"
    ARRHYTHMIA = "arrhythmia"
    CARDIOVASCULAR_DECONDITIONING = "cardiovascular-deconditioning"
    IMMUNE_REACTIVATION = "immune-reactivation"
    # Habitat: el CO2 de cabina sale de limite y afecta a toda la tripulacion a la vez
    # (especificacion del equipo §9, "CO2/fatiga"). Es ambiental (`ENVIRONMENTAL_SCENARIOS`):
    # con varios tripulantes, afecta a todos; los no ambientales, solo a crew-01.
    CO2_FATIGUE = "co2-fatigue"
    # Especificacion §9 "hidratacion/renal": menos liquido, menos orina y mas concentrada.
    DEHYDRATION = "dehydration"
    # Base de conocimiento H7 (hipotesis): la comida gusta menos y se come menos.
    MENU_FATIGUE = "menu-fatigue"
    # El unico que no termina peor de lo que empezo (conversacion de ideacion, la demo
    # "CAUTION -> RECOVERING -> NOMINAL"): unos dias de sueño corto y peor vigilancia que
    # despues cesan. No se modela por que cesan: ninguna contramedida, solo el fin de la
    # perturbacion (`transient_level`).
    TRANSIENT_SLEEP_LOSS = "transient-sleep-loss"
    # El caso de demo de la especificacion (§9, «evento de radiacion»: detectar, contexto,
    # procedimiento y linea temporal de seguimiento) entero: el mismo pico de dosis que
    # `spe-event`, pero antes en la ventana, de modo que la dosis vuelve a su fondo antes del
    # final. En la linea temporal se ve el comienzo, el periodo de monitorizacion intensificada
    # (`app/routines.py`, con la dosis por encima de su limite) y la vuelta a la normalidad. No
    # sube la carga de sintomas: a estas tasas de dosis ninguna ficha leida da sintomas, y
    # `spe-event`, que la sube, se queda como estaba.
    SPE_EVENT_RECOVERY = "spe-event-recovery"


# LO QUE LE PASA A LA NAVE, Y NO A UNA PERSONA.
#
# Con varios tripulantes (`POST /api/simulate`), un escenario de esta lista lo sufren todos y uno
# fuera de ella solo crew-01. El evento solar estuvo fuera hasta la decimoseptima ronda: una
# tormenta de particulas que solo alcanzaba a uno de cuatro tripulantes de la misma nave es
# fisicamente incoherente, y escondia justo el contraste que la correlacion de tripulacion
# existe para ver (lo que le pasa a todos apunta al entorno, no a la persona).
ENVIRONMENTAL_SCENARIOS = frozenset(
    {Scenario.CO2_FATIGUE, Scenario.SPE_EVENT, Scenario.SPE_EVENT_RECOVERY}
)

# Los dos escenarios con el pico de dosis de un evento de particulas solares.
SPE_SCENARIOS = frozenset({Scenario.SPE_EVENT, Scenario.SPE_EVENT_RECOVERY})


EVIDENCE_CLASSES = ("established", "direction_only", "contested", "unsupported", "design")

# Lo que declara como fuente un parametro que no tiene ninguna.
NO_SOURCE = "Diseño de EMMA: sin fuente escrita en el repositorio"


@dataclass(frozen=True, slots=True)
class DriftParameter:
    """Un parametro de deriva con su procedencia declarada."""

    value: float
    evidence: str
    note: str = ""
    source: str = ""
    # Fichas del registro de evidencia que sostienen la nota, por identificador.
    refs: tuple[str, ...] = ()
    # Solo `unsupported`: donde se busco el respaldo y que dice lo leido.
    searched: str = ""


def _p(
    value: float, evidence: str, note: str = "", source: str = "",
    refs: tuple[str, ...] = (), searched: str = "",
) -> DriftParameter:
    return DriftParameter(
        value=value, evidence=evidence, note=note, source=source, refs=refs, searched=searched,
    )


def _design(value: float, what: str) -> DriftParameter:
    """Un valor de diseño: dice que representa y que nada escrito aqui lo respalda."""
    return _p(
        value, "design",
        f"{what}. Valor de diseño de EMMA, sin respaldo escrito en el repositorio: ni el "
        "sentido ni la magnitud se presentan como documentados",
        NO_SOURCE,
    )


# Lo que añade la nota de cada parametro del ciclo: no actua salvo que el tripulante lo tenga.
_CYCLE_ONLY = " (solo si el tripulante simulado tiene ciclo; apagado por defecto)"


LITERATURE: dict[str, DriftParameter] = {
    # --- Magnitud documentada ---
    "bmd_loss_pct_per_month": _p(
        1.25, "established",
        "1-1,5 %/mes en cadera y columna lumbar sin contramedidas",
        "NASA-STD-3001 [V1 4027] fija el umbral de contramedida en 95 % de la DMO previa",
    ),
    "iss_sleep_hours_actual": _p(
        6.0, "established",
        "~6 h de sueño en vuelo en tripulantes de la ISS: Barger 2014 (actigrafía y diarios de 21 "
        "astronautas de la ISS) da 6,09 h en vuelo, frente a 6,95 h la primera semana tras el "
        "regreso",
        "Barger LK et al., Lancet Neurol 2014 (PMID 25127232), resumen leído el 2026-10-22",
        refs=("barger-2014-sleep-spaceflight",),
    ),
    "pvt_lapse_threshold_ms": _p(
        500.0, "established",
        "definición estándar de lapso de la PVT de 10 minutos: «Response times ≥ 500 ms» (Basner "
        "2011, Tabla 3). EMMA cuenta lapso por encima de 500 ms, no desde 500: la diferencia está "
        "declarada en `ingest/pvt.py` y es una decisión pendiente",
        "Basner M, Dinges DF, Sleep 2011 (PMID 21532951), Tabla 3 leída el 2026-10-13",
        refs=("basner-2011-pvt-metrics",),
    ),
    "iss_daily_dose_msv": _p(
        0.5, "established",
        "~0,3-0,8 mSv/día según ciclo solar y altitud",
        "Contrastado con dosimetría real de DosTel vía OSDR RadLab: "
        "0,27 mSv integrados en 24 h del 2022-04-01",
    ),
    "career_dose_limit_msv": _p(
        600.0, "established",
        "límite de dosis efectiva de carrera, universal para toda edad y sexo",
        "NASA-STD-3001 Vol 1 Rev C [V1 4030], texto verbatim del Appendix D",
    ),

    # --- Sentido documentado, magnitud semanal interpolada ---
    "orthostatic_drop_growth_per_week": _p(
        0.5, "direction_only",
        "la intolerancia ortostática es un hallazgo consistente, pero se "
        "manifiesta al volver a gravedad; medirla en microgravedad tiene poco "
        "significado, de ahí una deriva pequeña que satura pronto",
        "Desacondicionamiento cardiovascular: intolerancia ortostática postvuelo",
    ),
    "circadian_drift_h_per_week": _p(
        0.15, "direction_only",
        "el desajuste circadiano en vuelo está documentado: los ritmos no se "
        "reencarrilan a días distintos de 24 h. Con meseta a las 2 semanas "
        "representa un desfase estable, no una deriva sin fin",
        "Ritmos circadianos de cortisol que no entrainan a días de 23,6 h",
    ),
    # De diseño hasta el 2026-10-31 (decisión del usuario): lo leído en vuelo da el sentido, no la
    # magnitud semanal, que es la de antes.
    "ntx_rise_per_week": _p(
        1.1, "direction_only",
        "subida semanal del telopéptido N (marcador de resorción ósea) en el modelo nominal, sin "
        "meseta. El sentido está documentado en vuelo para los marcadores de resorción en "
        "conjunto: Smith 2005 (tripulantes de la Mir, misiones de 4 a 6 meses) los da "
        "«significantly higher than before flight» durante el vuelo, y Smith 2012 (13 "
        "tripulantes de la ISS) «increased in both groups during flight»; el telopéptido N se "
        "nombra en la frase de después del aterrizaje de Smith 2005 y, en vuelo, en Zwart 2018 (17 "
        "astronautas: «N-telopeptide (NTX) and urinary calcium were higher during flight»). La "
        "magnitud semanal es el valor de diseño de antes (reclasificada el 2026-10-31 sin "
        "cambiarlo), no una cifra leída",
        "Smith 2005 (Mir), Smith 2012 (ISS) y Zwart 2018: marcadores de resorción ósea al alza en "
        "vuelo",
        refs=(
            "smith-2005-bone-markers-mir", "smith-2012-bone-resistance-iss",
            "zwart-2018-dietary-acid-load",
        ),
    ),

    # --- Escenario CO2: efectos agudos con el CO2 de cabina fuera de limite ---
    "co2_symptom_burden_rise": _p(
        2.5, "direction_only",
        "la cefalea se asocia al CO2 de cabina en la ISS: la probabilidad de notificarla se "
        "duplica por cada mmHg. Sentido documentado; la subida en la escala de sintomas de "
        "a bordo es de diseño",
        "Law J. et al. J Occup Environ Med 2014;56(5):477-83, PMID 24806559",
    ),

    # --- Escenarios de hidratacion y nutricion: sentido documentado o hipotesis ---
    "dehydration_urine_drop_ml_per_week": _p(
        220.0, "direction_only",
        "menos ingesta de liquido da menos orina y mas concentrada, que es lo que NASA "
        "vigila frente al riesgo de calculos. Sentido documentado; la magnitud semanal es de "
        "diseño",
        "NASA, The Human Body in Space (orina, calculos renales e hidratacion)",
    ),
    # Las cuatro contestadas que no nombraban ficha (esta, las dos del CO2 y la SDNN) la nombran
    # desde la decimoséptima ronda (U10, 2026-10-26), con lo leído ese día. Esta pasó en la
    # decimoctava (§5.38.10, decisión del usuario) de «contestado» a «sin respaldo en lo leído»,
    # con el MISMO valor: el único estudio en vuelo leído no ve la caída, y el único lado que la
    # ve es de Tierra con la misma comida cinco días seguidos, que no es una misión.
    "menu_fatigue_acceptability_drop_per_week": _p(
        0.4, "unsupported",
        "HIPOTESIS H7 de la base de conocimiento: la aceptabilidad de la comida baja con la "
        "duracion de la mision y con ella lo que se come. Lo leído no lo respalda en vuelo: en "
        "la ISS (Douglas 2025, 15 astronautas, una comida a la semana en misiones de 6 meses y "
        "de 1 año) la aceptabilidad no bajó a lo largo de la misión. Lo único leído que la ve "
        "bajar es de Tierra y con monotonía estricta (Meiselman 2000: la misma comida 5 días "
        "seguidos), y el resumen de Sirius-21 (NTRS 20220014371) no da resultados. El valor es "
        "el de antes: cambiarlo es decisión del usuario. Aqui no se da por demostrada",
        "Sin respaldo en lo leído (Douglas 2025 en la ISS; Meiselman 2000, en Tierra; "
        "Sirius-21, sin resultados)",
        refs=(
            "meiselman-2000-variety-monotony", "douglas-2025-iss-food-acceptability",
            "ntrs-20220014371",
        ),
        searched=(
            "Douglas 2025 (Front Psychol, 15 astronautas en la ISS; resumen en PubMed y texto "
            "completo en Europe PMC): «acceptability scores did not decrease over the "
            "mission», sin relación con la duración de la misión (p = 0,35). Meiselman 2000 "
            "(Physiol Behav, resumen en PubMed), al que Douglas cita en su introducción: la "
            "misma comida del mediodía servida 5 días seguidos, en Tierra, bajó de aceptación y "
            "de ingesta; no es vuelo ni una misión. Sirius-21 (NTRS 20220014371, resumen de "
            "congreso; misión análoga de 8 meses): «Data are currently being assessed», sin "
            "resultados; una búsqueda en NTRS («SIRIUS food», «menu fatigue acceptability») no "
            "dio un resumen posterior"
        ),
    ),

    # --- Contestado: los estudios discrepan ---
    "resting_hr_drift_bpm_per_week": _p(
        0.0, "contested",
        "la FC en reposo no deriva DURANTE el vuelo en el modelo nominal (decisión del usuario, "
        "2026-10-31). Lo leído discrepa, con el peso del lado de «sin cambio»: cuatro estudios "
        "no la ven cambiar en vuelo (Hughson 2012, 6 astronautas en la ISS; Xu 2013, 7, durante "
        "el sueño; Fraser 2012, 7, en la actividad diaria; Baevsky 2007, 8 cosmonautas en la "
        "ISS) y uno la ve subir (Baevsky 1997, 2 tripulantes de la Mir, sin decir frente a qué). "
        "Otsuka 2022 resume la literatura así: a veces baja, a veces sube, a veces no cambia. "
        "Hasta el 2026-10-31 subía 0,4 lpm/semana con meseta a las 12 semanas (~5 lpm): la cifra "
        "de la que salía, ~54,9 -> 60,0 lpm sentado (Hughson 2012), es de DESPUÉS del vuelo. El "
        "0 es el lado del peso de lo leído, no una magnitud documentada, y por eso la clase "
        "sigue siendo «contestado». Lo que cambió al corregirla está medido en "
        "compliance/hmi-state-of-the-art.md §5.39.22",
        "Hughson 2012, Xu 2013, Fraser 2012 y Baevsky 2007 (sin cambio en vuelo) frente a "
        "Baevsky 1997 (sube); Otsuka 2022 (resumen de la literatura)",
        refs=(
            "hughson-2012-cardiovascular-iss", "xu-2013-hrv-sleep-iss",
            "fraser-2012-heart-rate-iss", "baevsky-2007-autonomic-iss",
            "baevsky-1997-holter-mir", "otsuka-2022-one-year-hrv",
        ),
    ),
    "co2_pvt_rt_rise_ms": _p(
        12.0, "contested",
        "el efecto del CO2 a niveles de nave sobre la cognicion es contestado, y la unica medida "
        "de la PVT leída no lo ve: Scully 2019 (22 sujetos tipo astronauta, exposiciones agudas "
        "de 600 a 5000 ppm en cámara) no halla efecto significativo del CO2 en la PVT ni una "
        "pauta dosis-respuesta clara en las demás pruebas; Satish 2012 (22 participantes, 1000 y "
        "2500 ppm, en Tierra) ve peores decisiones, y Manzey 1998 (4 sujetos, 26 días confinados "
        "a 0,7 % y a 1,2 %) ve empeorar el seguimiento visomotor a 1,2 %, sin relevancia "
        "operativa según sus autores. Nada de lo leído mide en vuelo. Deriva pequena a proposito",
        "Scully 2019 (sin efecto en la PVT) frente a Satish 2012 y Manzey 1998 (el rendimiento "
        "empeora con el CO2)",
        refs=(
            "scully-2019", "satish-2012-co2-decision-making", "manzey-1998-co2-performance",
        ),
    ),
    "co2_sleep_efficiency_drop_pct": _p(
        3.0, "contested",
        "lo leído discrepa sobre el CO2 y el sueño, y ningún resumen nombra la eficiencia del "
        "sueño: Van Hoy 2026 (dos misiones de 2 semanas en un hábitat análogo, 450-2000 ppm) ve "
        "menos sueño profundo las noches de más CO2, con resultados dispares entre sujetos y una "
        "evidencia que el propio artículo no da por suficiente; Gundel 1998 (4 sujetos, 23 días "
        "a 0,7 % y otros 23 a 1,2 % en un sistema cerrado) concluye que esos niveles no reducen "
        "la calidad del sueño; y en Christian 2024 (30 días de reposo en cama con la cabeza "
        "abajo a 4 mmHg de CO2) el sueño no difiere del de antes, sin separar el CO2 del reposo. "
        "Antes se citaba a Law 2014 por el sueño y la fatiga: su resumen solo habla de cefaleas "
        "(el texto completo no se pudo leer). No hay magnitud citable",
        "Van Hoy 2026 (menos sueño profundo) frente a Gundel 1998 y Christian 2024 (sueño sin "
        "cambio); Law 2014, sin el sueño en su resumen",
        refs=(
            "van-hoy-2026-co2-sleep-analog", "gundel-1998-co2-sleep",
            "christian-2024-hdtbr-co2-sleep", "law-2014",
        ),
    ),

    "hrv_sdnn_decline_ms_per_week": _p(
        0.3, "contested",
        "NO hay consenso en que la SDNN caiga en vuelo, y ningún resumen leído la nombra: Xu "
        "2013 (7 astronautas en la ISS, durante el sueño) ve bajar en vuelo los indicadores de "
        "dominio temporal; Otsuka 2016 (10 astronautas, registros de 24 h) ve subir la potencia "
        "espectral total hacia el día 153; Otsuka 2022 resume la literatura así: a veces baja, a "
        "veces sube, a veces no cambia. Se deja una deriva mínima a propósito: inventar una "
        "tendencia clara donde la ciencia no la tiene sería peor que no modelarla",
        "Xu 2013 (baja durante el sueño) frente a Otsuka 2016 (sube la potencia total); Otsuka "
        "2022 (resumen de la literatura)",
        refs=(
            "xu-2013-hrv-sleep-iss", "otsuka-2016-hrv-time-structure",
            "otsuka-2022-one-year-hrv",
        ),
    ),
    # Tres derivas de diseño del modelo nominal que la lectura del sentido en vuelo (la que
    # acompaña al perfil de línea base) ya juzgaba discutidas: reclasificadas el 2026-10-31
    # (decisión del usuario) con el valor que tenían. El valor no sale de lo leído; la clase sí.
    "hrv_rmssd_decline_ms_per_week": _p(
        0.8, "contested",
        "caída semanal de la RMSSD en el modelo nominal, con meseta a las 16 semanas. Ningún "
        "resumen leído nombra la RMSSD, y lo que miden de cerca discrepa: Xu 2013 (7 astronautas "
        "en la ISS, durante el sueño) ve bajar en vuelo los indicadores de dominio temporal; "
        "Hughson 2012 (6 astronautas en la ISS) ve bajar la banda de alta frecuencia, y Baevsky "
        "2007 (8 cosmonautas en la ISS, registros cortos) no la ve cambiar. El sentido en vuelo "
        "que acompaña al perfil de línea base la da por discutida, y el simulador dice lo mismo. "
        "El valor es el de diseño de antes (reclasificada el 2026-10-31 sin cambiarlo) y no es "
        "la deriva pequeña de esta clase: ~13 ms a la meseta. Cambiarlo es decisión del usuario",
        "Xu 2013 y Hughson 2012 (baja en vuelo) frente a Baevsky 2007 (sin cambio en la banda de "
        "alta frecuencia)",
        refs=(
            "xu-2013-hrv-sleep-iss", "hughson-2012-cardiovascular-iss",
            "baevsky-2007-autonomic-iss",
        ),
    ),
    "systolic_bp_decline_mmhg_per_week": _p(
        0.3, "contested",
        "caída semanal de la presión sistólica en el modelo nominal, sin meseta. Lo leído "
        "discrepa, y mide distinto: Hughson 2012 (6 astronautas en la ISS, medidas cortas "
        "sentados) no ve cambio en vuelo frente a antes; Norsk 2015 (8 astronautas, presión "
        "ambulatoria de 24 h entre los días 85 y 192 en la ISS) la da 8 mmHg más baja, y "
        "Baevsky 2007 (8 cosmonautas en la ISS) dice «BP decreased» sin separar sistólica y "
        "diastólica. El valor es el de diseño de antes (reclasificada el 2026-10-31 sin "
        "cambiarlo): ~7,7 mmHg a los 180 días, del orden de lo que mide Norsk 2015, pero no "
        "sale de él. Cambiarlo es decisión del usuario",
        "Norsk 2015 y Baevsky 2007 (baja en vuelo) frente a Hughson 2012 (sin cambio)",
        refs=(
            "norsk-2015-ambulatory-bp-iss", "baevsky-2007-autonomic-iss",
            "hughson-2012-cardiovascular-iss",
        ),
    ),
    "diastolic_bp_decline_mmhg_per_week": _p(
        0.2, "contested",
        "caída semanal de la presión diastólica en el modelo nominal, sin meseta. Lo leído "
        "discrepa, y mide distinto: Hughson 2012 (6 astronautas en la ISS, medidas cortas "
        "sentados) no ve cambio en vuelo frente a antes; Norsk 2015 (8 astronautas, presión "
        "ambulatoria de 24 h entre los días 85 y 192 en la ISS) la da 9 mmHg más baja, y "
        "Baevsky 2007 (8 cosmonautas en la ISS) dice «BP decreased» sin separar sistólica y "
        "diastólica. El valor es el de diseño de antes (reclasificada el 2026-10-31 sin "
        "cambiarlo): ~5,1 mmHg a los 180 días, por debajo de lo que mide Norsk 2015, y no sale "
        "de él. Cambiarlo es decisión del usuario",
        "Norsk 2015 y Baevsky 2007 (baja en vuelo) frente a Hughson 2012 (sin cambio)",
        refs=(
            "norsk-2015-ambulatory-bp-iss", "baevsky-2007-autonomic-iss",
            "hughson-2012-cardiovascular-iss",
        ),
    ),

    # --- Contestada, a 0: lo leído discrepa y no sostiene una subida del modelo nominal ---
    "cortisol_rise_per_week": _p(
        0.0, "contested",
        "el cortisol salival no sube en el modelo nominal (decisión del usuario, 2026-10-31). "
        "Hasta entonces subía 0,0145 ug/dL por semana porque una fuente decía «elevado durante "
        "misiones de la ISS» sin nombrar estudio. Lo leído después discrepa: Vorobiev 1995 lo ve "
        "subir en dos cosmonautas los primeros 18 días y Buchheim 2019 no ve cambio significativo "
        "en los días 90 y 150; una frase discutida no sostiene una deriva semanal, y el valor "
        "sigue en 0. "
        "Unidad en ug/dL (LOINC 2142-8 es Mass/volume): 0,0145 equivalían a 0,4 nmol/L con PM "
        "362,46 g/mol. El escenario de reactivación inmune conserva su subida propia "
        "(`immune_cortisol_rise_per_week`, de diseño). Lo que cambió al corregirla está medido "
        "en compliance/hmi-state-of-the-art.md §5.39.22. Mehta 2017 (23 astronautas en la ISS): "
        "cambia la trayectoria diurna, no dice que suba; el cortisol en plasma, sin diferencia "
        "significativa. Agha 2020 (8 tripulantes de la ISS): lo elevado antes (L-180) y durante "
        "la misión es el cociente cortisol/DHEA, no el cortisol; su título era la fuente sin "
        "estudio que citaba el parámetro. Buchheim 2019: el resumen no dice en qué muestras",
        "Vorobiev 1995 (sube, 2 cosmonautas, 18 días) frente a Buchheim 2019 (sin cambio "
        "significativo); Mehta 2017 y Agha 2020 no dan el sentido",
        refs=(
            "vorobiev-1995-altair-mir", "buchheim-2019-inflammaging-cosmonauts",
            "mehta-2017-latent-virus-iss", "agha-2020-salivary-iss",
        ),
    ),

    # --- Diseño: sin respaldo escrito en el repositorio ---
    #
    # Estas derivas estaban escritas a mano en los modelos y en los escenarios. Los valores
    # son los mismos; lo nuevo es que se declaran. Ninguna lleva cita porque no hay ninguna
    # escrita en el repositorio, y no se ha ido a buscar una para vestirlas.
    #
    # Modelo nominal. (La RMSSD, la presion arterial y el telopeptido N estuvieron aqui hasta el
    # 2026-10-31: lo leido en vuelo ya los juzgaba y tienen ahora su clase, arriba.)
    "exercise_minutes_decline_per_week": _design(
        0.6, "minutos diarios de ejercicio que se pierden por semana en el modelo nominal"
    ),
    "loading_impacts_decline_per_week": _design(
        40.0, "impactos de carga que se pierden por semana en el modelo nominal"
    ),
    "symptom_burden_rise_per_week": _design(
        0.02, "subida semanal de la carga de sintomas en el modelo nominal"
    ),
    # Escenario de insomnio progresivo.
    "insomnia_sleep_duration_drop_h_per_week": _design(
        0.55, "horas de sueño que se pierden por semana en el escenario de insomnio"
    ),
    "insomnia_sleep_duration_noise_sd_h": _design(
        0.5, "dispersion de la duracion del sueño en el escenario de insomnio"
    ),
    "insomnia_sleep_efficiency_drop_pct_per_week": _design(
        3.5, "puntos de eficiencia del sueño que se pierden por semana en el escenario de insomnio"
    ),
    "insomnia_pvt_rt_rise_ms_per_week": _design(
        14.0, "subida semanal del tiempo de reaccion del PVT en el escenario de insomnio"
    ),
    "insomnia_pvt_lapses_rise_per_week": _design(
        1.5, "lapsos del PVT que se añaden por semana en el escenario de insomnio"
    ),
    "insomnia_mood_drop_per_week": _design(
        0.5, "caida semanal del animo declarado en el escenario de insomnio"
    ),
    # Escenario de deshidratacion (la caida de la orina tiene su entrada arriba).
    "dehydration_intake_to_urine_drop_ratio": _design(
        1.15, "cuanto mas cae la ingesta de liquido que la orina en el escenario de deshidratacion"
    ),
    "dehydration_specific_gravity_rise_per_week": _design(
        0.0035, "subida semanal de la densidad de la orina en el escenario de deshidratacion"
    ),
    # Escenario de fatiga de menu (la caida de la aceptabilidad tiene su entrada arriba).
    "menu_fatigue_energy_kcal_per_acceptability_point": _design(
        300.0, "kcal diarias que se dejan de ingerir por cada punto de aceptabilidad perdido"
    ),
    "menu_fatigue_appetite_per_acceptability_point": _design(
        0.5, "puntos de apetito que se pierden por cada punto de aceptabilidad perdido"
    ),
    "menu_fatigue_rejected_pct_per_acceptability_point": _design(
        2.5, "puntos de racion que se deja de mas por cada punto de aceptabilidad perdido"
    ),
    # Escenario de desacondicionamiento cardiovascular.
    "deconditioning_hr_rise_bpm_per_week": _design(
        2.4, "subida semanal del pulso en el escenario de desacondicionamiento"
    ),
    "deconditioning_sdnn_drop_ms_per_week": _design(
        5.5, "caida semanal de la SDNN en el escenario de desacondicionamiento"
    ),
    "deconditioning_orthostatic_growth_per_week": _design(
        4.0, "crecimiento semanal de la caida ortostatica, sin meseta, en el escenario de "
        "desacondicionamiento"
    ),
    "deconditioning_exercise_drop_min_per_week": _design(
        8.0, "minutos diarios de ejercicio que se pierden por semana en el escenario de "
        "desacondicionamiento"
    ),
    # Escenario de arritmia: no es una deriva, es dispersion.
    "arrhythmia_hr_noise_sd_bpm": _design(
        18.0, "dispersion del pulso en el escenario de arritmia"
    ),
    "arrhythmia_sdnn_noise_sd_ms": _design(
        35.0, "dispersion de la SDNN en el escenario de arritmia"
    ),
    # Escenario de reactivacion inmune.
    "immune_virus_shedding_rise_per_week": _design(
        0.9, "subida semanal de la excrecion de virus latente en el escenario de reactivacion"
    ),
    "immune_virus_shedding_noise_sd": _design(
        0.4, "dispersion de la excrecion de virus latente en el escenario de reactivacion"
    ),
    "immune_symptom_burden_rise_per_week": _design(
        0.5, "subida semanal de la carga de sintomas en el escenario de reactivacion"
    ),
    "immune_cortisol_rise_per_week": _design(
        0.065, "subida semanal del cortisol salival (ug/dL) en el escenario de reactivacion"
    ),
    # Escenario de evento de particulas solares.
    "spe_symptom_burden_rise_per_week": _design(
        0.3, "subida semanal de la carga de sintomas en el escenario de evento solar"
    ),
    "spe_dose_peak_multiplier": _design(
        120.0, "cuantas veces sube la tasa de dosis sobre el fondo en el pico del evento solar"
    ),
    # El perfil del pico, con los valores que ya tenia escritos en `_dose_multiplier` (declarados
    # el 2026-11-04 sin cambiarlos): subida, y constante del decaimiento exponencial.
    "spe_dose_rise_days": _design(
        0.25, "dias que tarda la tasa de dosis en llegar a su pico en el evento solar"
    ),
    "spe_dose_decay_days": _design(
        1.5, "constante, en dias, del decaimiento exponencial de la tasa de dosis tras el pico "
        "del evento solar"
    ),
    "spe_recovery_onset_days_before_end": _design(
        12.0, "dias antes del final de la ventana en que empieza el evento solar del escenario "
        "con vuelta a la normalidad; con el decaimiento declarado, la tasa de dosis vuelve "
        "cerca de su fondo antes del final"
    ),
    # Escenario de falta de sueño pasajera: efectos con la perturbacion entera, y cuando
    # empieza y cuando cesa. Que la falta de sueño empeore la vigilancia es el mismo vinculo
    # que el escenario de insomnio, y como alli, de diseño: ninguna ficha del repositorio da
    # su magnitud. Que cese tampoco se atribuye a nada.
    "transient_sleep_loss_h": _design(
        2.5, "horas de sueño de menos con la perturbacion entera, en la falta de sueño pasajera"
    ),
    "transient_sleep_efficiency_drop_pct": _design(
        15.0, "puntos de eficiencia del sueño de menos con la perturbacion entera, en la falta "
        "de sueño pasajera"
    ),
    "transient_pvt_rt_rise_ms": _design(
        50.0, "milisegundos de mas en el tiempo de reaccion del PVT con la perturbacion entera, "
        "en la falta de sueño pasajera"
    ),
    "transient_pvt_lapses_rise": _design(
        5.0, "lapsos del PVT de mas con la perturbacion entera, en la falta de sueño pasajera"
    ),
    "transient_onset_days_before_end": _design(
        6.0, "dias antes del final de la ventana en que empieza la falta de sueño pasajera"
    ),
    "transient_ceases_days_before_end": _design(
        3.0, "dias antes del final de la ventana en que la falta de sueño pasajera empieza a "
        "cesar, sin causa modelada"
    ),
    "transient_ramp_hours": _design(
        12.0, "horas que tarda la falta de sueño pasajera en llegar entera, y en irse del todo"
    ),
    # Ciclo menstrual opcional de un tripulante (`MenstrualCycle`), lote «ciclo», 2026-11-14. Los
    # siete nacieron de diseño: la bibliografia de la variacion por fase la fichaba otra unidad. El
    # 2026-11-15 (B3) la temperatura y el pulso pasan a magnitud documentada con lo leido; la
    # forma del ciclo (periodo, lutea, rampa) y la bajada de la RMSSD y la SDNN siguen de diseño.
    # Se declaran siempre, como los de cada escenario, pero solo actuan con `CrewMember.cycle`
    # puesto (lo dice la nota de cada uno, `_CYCLE_ONLY`): el nominal no tiene ciclo.
    "cycle_period_days": _design(
        28.0, "duracion, en dias, del ciclo menstrual simulado" + _CYCLE_ONLY
    ),
    "cycle_luteal_days": _design(
        14.0, "dias de fase lutea al final de cada ciclo simulado (de la ovulacion a la regla)"
        + _CYCLE_ONLY
    ),
    "cycle_transition_days": _design(
        2.0, "dias que tarda el escalon luteo en subir tras la ovulacion, y en bajar antes de la "
        "regla, en el ciclo simulado" + _CYCLE_ONLY
    ),
    # Las dos subidas con cifra leida (lote «ciclo», B3, 2026-11-15) pasan a magnitud documentada
    # con las fichas de `evidence/cycle_physiology.py`; el valor elegido cae dentro del rango
    # leido. Las de la RMSSD y la SDNN siguen de diseño: lo leido solo da el sentido.
    "cycle_temperature_luteal_rise_c": _p(
        0.4, "established",
        "subida de la temperatura corporal (°C) en fase lutea frente a la folicular, en el ciclo "
        "simulado: lo leido da 0,23-0,7 °C (temperatura central, revision de Baker 2020, y oral "
        "al despertar, Maijala 2019); 0,4 es un valor dentro de ese rango, no una media publicada"
        + _CYCLE_ONLY,
        "data/cycle_physiology_read.json (body-temperature, fase lutea), leido el 2026-11-14",
        refs=(
            "baker-2020-temperature-menstrual-review", "maijala-2019-oura-finger-temperature",
        ),
    ),
    "cycle_heart_rate_luteal_rise_bpm": _p(
        3.7, "established",
        "subida de la frecuencia cardiaca (lpm, en reposo) en fase lutea frente a la folicular, "
        "en el ciclo simulado: lo leido da 3,42-3,91 lpm, resta de medias nocturnas de un solo "
        "estudio (Goodale 2019, autores de la empresa de la pulsera); 3,7 cae dentro de ese rango"
        + _CYCLE_ONLY,
        "data/cycle_physiology_read.json (heart-rate, fase lutea), leido el 2026-11-14",
        refs=("goodale-2019-wearable-menses-physiology",),
    ),
    "cycle_rmssd_luteal_drop_ms": _design(
        6.0, "bajada de la RMSSD (ms) en fase lutea frente a la folicular, en el ciclo simulado"
        + _CYCLE_ONLY
    ),
    "cycle_sdnn_luteal_drop_ms": _design(
        6.0, "bajada de la SDNN (ms) en fase lutea frente a la folicular, en el ciclo simulado"
        + _CYCLE_ONLY
    ),
}


def cited_refs() -> set[str]:
    """Las fichas del registro de evidencia que citan los parametros."""
    return {ref for param in LITERATURE.values() for ref in param.refs}


def literature_problems(
    literature: dict[str, DriftParameter], known_refs: Iterable[str]
) -> list[str]:
    """Lo que esta mal declarado en `literature`, frente a las fichas que existen.

    Por que existe: la clase de un parametro es una afirmacion sobre lo leido, y una
    afirmacion sin lo leido detras es justo lo que la revision encontro dos veces. Una
    clase sin respaldo que no dice donde se busco, un "contestado" con un solo lado o una
    cita a una ficha que no existe se dicen aqui, por nombre.
    """
    known = set(known_refs)
    problems: list[str] = []
    for name, param in sorted(literature.items()):
        if param.evidence not in EVIDENCE_CLASSES:
            problems.append(f"{name}: clase desconocida {param.evidence!r}")
        if missing := sorted(set(param.refs) - known):
            problems.append(f"{name}: cita fichas que no existen {missing}")
        if len(set(param.refs)) != len(param.refs):
            problems.append(f"{name}: cita una ficha dos veces")
        if param.evidence == "unsupported":
            if not param.searched.strip():
                problems.append(f"{name}: sin respaldo y sin decir donde se busco")
            if not param.refs:
                problems.append(f"{name}: sin respaldo y sin la ficha de lo leido al buscar")
            if param.source == NO_SOURCE:
                problems.append(f"{name}: sin respaldo no es diseño: se busco")
        elif param.searched:
            problems.append(f"{name}: `searched` solo es de la clase sin respaldo")
        if param.evidence == "contested" and len(param.refs) < 2:
            # Cuenta fichas, no lados: que haya una de cada lado lo comprueba la prueba de
            # cada parametro contestado, que nombra los dos. Tambien al que no cite ninguna:
            # antes solo se le pedia al que citara alguna, y cuatro «contestados» sin ficha
            # pasaban (§5.36.18; desde la decimoctava ronda, §5.38.10, ya no).
            problems.append(f"{name}: contestado con una sola ficha: le falta el otro lado")
        if param.evidence == "design" and param.refs:
            problems.append(f"{name}: dice no tener fuente y cita fichas")
    return problems


def evidence_by_class() -> dict[str, list[str]]:
    """Los parametros del modelo agrupados por clase de respaldo."""
    return {
        evidence_class: sorted(
            name for name, param in LITERATURE.items() if param.evidence == evidence_class
        )
        for evidence_class in EVIDENCE_CLASSES
    }


def evidence_report(sources: Iterable[str]) -> dict[str, Any] | None:
    """Lo que el estado declara cuando lo que analiza viene de este simulador, o `None`.

    Lo decide quien firmo las lecturas (`simulator:<escenario>`), no un interruptor: una
    lectura de wearable no lleva estos parametros detras, y la repeticion de Inspiration4
    (`simulator:inspiration4`) tampoco — son analiticas reales reproducidas, no este modelo.

    `evidence` es lo mismo que devuelve `POST /api/simulate`; `parameters` añade el valor, la
    nota y la fuente de cada uno, para que "diseño" se lea con sus palabras y no solo como
    una etiqueta.
    """
    known = {str(scenario) for scenario in Scenario}
    scenarios = sorted(
        {source.split(":", 1)[1] for source in sources if source.startswith("simulator:")}
        & known
    )
    if not scenarios:
        return None
    return {
        "scenarios": scenarios,
        "evidence": evidence_by_class(),
        "parameters": {
            name: {
                "value": param.value, "evidence": param.evidence,
                "note": param.note, "source": param.source,
                "refs": list(param.refs), "searched": param.searched,
            }
            for name, param in sorted(LITERATURE.items())
        },
    }



# Efecto agudo del escenario CO2 sobre cada indicador, al maximo de la excursion. Sale de
# `LITERATURE`, donde cada magnitud declara su clase de evidencia.
_CO2_EFFECTS: dict[str, float] = {
    "symptom-burden": LITERATURE["co2_symptom_burden_rise"].value,
    "pvt-mean-rt": LITERATURE["co2_pvt_rt_rise_ms"].value,
    "sleep-efficiency": -LITERATURE["co2_sleep_efficiency_drop_pct"].value,
}

# Efecto de la falta de sueño pasajera sobre cada indicador, con la perturbacion entera.
_TRANSIENT_EFFECTS: dict[str, float] = {
    "sleep-duration": -LITERATURE["transient_sleep_loss_h"].value,
    "sleep-efficiency": -LITERATURE["transient_sleep_efficiency_drop_pct"].value,
    "pvt-mean-rt": LITERATURE["transient_pvt_rt_rise_ms"].value,
    "pvt-lapses": LITERATURE["transient_pvt_lapses_rise"].value,
}


def transient_level(mission_day: float, total_days: int) -> float:
    """Fraccion 0..1 de la falta de sueño pasajera en un dia de mision.

    POR QUE UN ESCENARIO QUE TERMINA BIEN. Los demas solo empeoran, y el motor ya sabe decir
    «recuperandose» (`analysis/recovery_state.py`): sin un escenario en el que la perturbacion
    cese, esa trayectoria no se veia nunca en la demo, que es justo la que describe la
    conversacion de ideacion (CAUTION -> RECOVERING -> NOMINAL).

    Se ancla al final de la ventana, como el evento solar y el CO2: entra en rampa
    `transient_onset_days_before_end` dias antes del final, se queda entera y desde
    `transient_ceases_days_before_end` vuelve a cero en otra rampa igual. Con esos valores, la
    ventana anterior del estado (dias -4 a -2) la ve y la actual (los dos ultimos) ya no. En una
    ventana mas corta que el arranque no aparece: no se encoge para caber.
    """
    onset = total_days - LITERATURE["transient_onset_days_before_end"].value
    ceases = total_days - LITERATURE["transient_ceases_days_before_end"].value
    ramp_days = LITERATURE["transient_ramp_hours"].value / 24.0
    if onset < 0 or mission_day <= onset:
        return 0.0
    rising = (mission_day - onset) / ramp_days
    falling = 1.0 - (mission_day - ceases) / ramp_days
    # Pasada la segunda rampa, `falling` es negativo y el efecto, cero: la perturbacion cesa.
    return max(0.0, min(1.0, rising, falling))


# Escenarios con un efecto agudo anclado al final de la ventana: sobre que indicadores y con que
# perfil temporal (fraccion 0..1 por dia de mision). Uno solo por escenario y un solo camino en
# `generate`, en vez de un bloque copiado por escenario.
_TIMED_EFFECTS: dict[Scenario, tuple[dict[str, float], Callable[[float, int], float]]] = {
    Scenario.CO2_FATIGUE: (_CO2_EFFECTS, co2_ramp),
    Scenario.TRANSIENT_SLEEP_LOSS: (_TRANSIENT_EFFECTS, transient_level),
}


# --------------------------------------------------------------------------- #
# Ciclo menstrual opcional
# --------------------------------------------------------------------------- #
#
# POR QUE ESTA AQUI. Una tripulante sin supresion menstrual tiene, cada ~4 semanas, dos
# semanas con la temperatura, el pulso en reposo y la variabilidad del pulso desplazados. El
# motor compara cada lectura con la base personal de los ultimos 14 dias: si ese vaiven le
# hace dar falsas alarmas, es una falsa alarma que nadie habia medido, porque MMASH son 24 h
# de varones y el tripulante simulado no tenia ciclo. La invariante 5 pide medirla junto con
# la sensibilidad; para medirla hace falta un ciclo que generar.
#
# LA FORMA: UN ESCALON LUTEO SUAVIZADO, NO UNA SINUSOIDE. La temperatura basal es bifasica: baja
# en la fase folicular, sube en uno o dos dias tras la ovulacion y se queda arriba hasta la
# regla. Una sinusoide repartiria el cambio por todo el ciclo y no tendria meseta, que es
# justo lo que pone a prueba una ventana de 14 dias (dos semanas arriba, dos abajo). Las rampas
# son medio coseno para que no haya saltos instantaneos, que un cuerpo no da. Que el pulso y
# la RMSSD sigan el mismo perfil que la temperatura es una simplificacion de diseño: lo
# respaldado y lo que no lo dira la bibliografia que se esta fichando.
#
# APAGADO POR DEFECTO. `CrewMember.cycle` es `None` salvo que se pida: el nominal y toda serie
# fijada en las pruebas salen identicas, hasta el ultimo decimal.

_CYCLE_AMPLITUDES: dict[str, float] = {
    "body-temperature": LITERATURE["cycle_temperature_luteal_rise_c"].value,
    "heart-rate": LITERATURE["cycle_heart_rate_luteal_rise_bpm"].value,
    "hrv-rmssd": -LITERATURE["cycle_rmssd_luteal_drop_ms"].value,
    "hrv-sdnn": -LITERATURE["cycle_sdnn_luteal_drop_ms"].value,
}


def luteal_level(
    cycle_day: float,
    period_days: float | None = None,
    luteal_days: float | None = None,
    transition_days: float | None = None,
) -> float:
    """Fraccion 0..1 del escalon luteo en un dia del ciclo (0 = primer dia de la regla).

    0 en la fase folicular, 1 en la meseta lutea, con rampas de medio coseno de
    `transition_days`: la subida empieza en la ovulacion (`period - luteal`) y la bajada
    termina con el ciclo, de modo que el dia 0 y el dia `period` valen lo mismo y la funcion es
    continua de un ciclo al siguiente.
    """
    period = period_days if period_days is not None else LITERATURE["cycle_period_days"].value
    luteal = luteal_days if luteal_days is not None else LITERATURE["cycle_luteal_days"].value
    ramp = (
        transition_days if transition_days is not None
        else LITERATURE["cycle_transition_days"].value
    )
    if period <= 0 or not 0 < luteal < period or not 0 < 2 * ramp <= luteal:
        raise ValueError("ciclo mal definido: 0 < 2·transición ≤ lútea < periodo")
    day = cycle_day % period
    ovulation = period - luteal
    if day < ovulation:
        return 0.0
    if day < ovulation + ramp:
        return 0.5 - 0.5 * float(np.cos(np.pi * (day - ovulation) / ramp))
    if day < period - ramp:
        return 1.0
    return 0.5 + 0.5 * float(np.cos(np.pi * (day - (period - ramp)) / ramp))


@dataclass(frozen=True, slots=True)
class MenstrualCycle:
    """Ciclo de un tripulante simulado: periodo, fase al empezar y amplitud lutea por clave.

    `amplitudes` es el desplazamiento de la meseta lutea frente a la folicular, en la unidad
    del indicador y con su signo (la RMSSD baja). `start_cycle_day` es el dia del ciclo en el
    primer instante de la mision (0 = primer dia de la regla).
    """

    period_days: float = LITERATURE["cycle_period_days"].value
    start_cycle_day: float = 0.0
    # Inmutable tras validarla (`__post_init__`); fuera del hash, que no admite un mapa.
    amplitudes: Mapping[str, float] = field(
        default_factory=lambda: dict(_CYCLE_AMPLITUDES), hash=False
    )
    luteal_days: float = LITERATURE["cycle_luteal_days"].value
    transition_days: float = LITERATURE["cycle_transition_days"].value

    def __post_init__(self) -> None:
        if unknown := set(self.amplitudes) - set(CATALOG):
            raise KeyError(f"indicadores desconocidos en el ciclo: {sorted(unknown)}")
        object.__setattr__(self, "amplitudes", MappingProxyType(dict(self.amplitudes)))
        # Valida la forma al crearlo, no a mitad de una serie.
        luteal_level(0.0, self.period_days, self.luteal_days, self.transition_days)

    def label(self) -> str:
        """El ciclo en una cadena estable: va en la procedencia de cada lectura que mueve."""
        amplitudes = ",".join(f"{key}={value:g}" for key, value in sorted(self.amplitudes.items()))
        return (
            f"cycle(period={self.period_days:g},start={self.start_cycle_day:g},"
            f"luteal={self.luteal_days:g},transition={self.transition_days:g},{amplitudes})"
        )

    def level_at(self, mission_day: float) -> float:
        """Fraccion 0..1 del escalon luteo en ese dia de mision."""
        return luteal_level(
            self.start_cycle_day + mission_day,
            self.period_days, self.luteal_days, self.transition_days,
        )

    def offset_at(self, key: str, mission_day: float) -> float:
        """Cuanto desplaza el ciclo la clave en ese dia de mision (0 si no la toca)."""
        amplitude = self.amplitudes.get(key, 0.0)
        return amplitude * self.level_at(mission_day) if amplitude else 0.0



# --------------------------------------------------------------------------- #
# Ritmo circadiano y contexto
# --------------------------------------------------------------------------- #
#
# EL SIMULADOR NO TENIA RITMO DIARIO, Y ESO LO HACIA MAS FACIL QUE LA REALIDAD.
#
# `value_at()` depende de la semana de mision y del ruido, no de la hora. Las
# lecturas salian ademas sin contexto: 3520 observaciones, todas `unknown`. Dos
# consecuencias:
#
#   1. La estratificacion por contexto —comparar el pulso de sueno contra la base
#      de sueno y no contra la de vigilia— **nunca se ejercitaba** en datos de
#      duracion de mision. Solo MMASH la probaba, y MMASH dura 36 h.
#   2. Un generador sin ciclo diario es mas benigno que un cuerpo real: no tiene
#      la fuente de variacion que produjo la tendencia espuria de -92,9 lpm por
#      semana sobre un sujeto sano.
#
# LOS MULTIPLICADORES ESTAN MEDIDOS, NO CITADOS.
# ----------------------------------------------
# Salen de MMASH, 22 sujetos humanos reales, tomando la mediana por sujeto de la
# razon entre contextos y luego la mediana entre sujetos:
#
#   pulso   sueno/reposo    0,765   (rango por sujeto 0,676 - 0,884; n = 21)
#   pulso   actividad/reposo 1,117  (medianas agregadas 82,84 / 74,17)
#
# Para la HRV la razon sueno/reposo va de 0,58 a 2,85 segun el sujeto: **no hay
# efecto consistente que modelar**, y fabricar uno seria inventar fisiologia. Por
# eso solo se modula el pulso. Lo que no esta medido, no se simula.
CIRCADIAN_RATIO: dict[str, dict[Context, float]] = {
    "heart-rate": {Context.SLEEP: 0.765, Context.ACTIVE: 1.117},
}

# Horario de a bordo. El sueno arranca a las 22:00 y dura lo que la literatura
# documenta que **de verdad** duerme la tripulacion de la ISS, no lo que marca el
# plan de vuelo. El bloque de ejercicio son las ~2 h diarias de contramedida.
SLEEP_START_HOUR = 22.0
EXERCISE_START_HOUR = 16.0
EXERCISE_HOURS = 2.0


def context_at(hour: float, sleep_hours: float) -> Context:
    """Que esta haciendo la tripulacion a esa hora del dia."""
    since_sleep = (hour - SLEEP_START_HOUR) % 24.0
    if since_sleep < sleep_hours:
        return Context.SLEEP
    if EXERCISE_START_HOUR <= hour < EXERCISE_START_HOUR + EXERCISE_HOURS:
        return Context.ACTIVE
    return Context.REST


@dataclass(frozen=True, slots=True)
class IndicatorModel:
    """Como evoluciona un indicador a lo largo de la mision."""

    key: str
    baseline: float
    weekly_drift: float = 0.0
    noise_sd: float = 0.0
    floor: float | None = None
    ceiling: float | None = None
    # Limite asintotico de la deriva: el cuerpo se adapta, no deriva sin fin.
    plateau_weeks: float | None = None

    def value_at(
        self, mission_week: float, rng: np.random.Generator, scale: float = 1.0,
        offset: float = 0.0,
    ) -> float:
        """Valor del indicador en ese momento de la mision.

        `scale` es la modulacion circadiana, y se aplica **antes** del suelo y el
        techo a proposito: aplicada despues, un pulso de 35 lpm multiplicado por
        el 0,765 del sueno daba 26,8 y se saltaba el suelo que el propio modelo
        declara. El limite fisiologico es el ultimo filtro, no el penultimo.

        `offset` es el desplazamiento del ciclo menstrual (`MenstrualCycle`), en reposo: se
        suma a la base antes de la modulacion circadiana (el pulso de sueño sube en la misma
        proporcion que el de reposo) y antes del suelo y el techo, por lo mismo. Sin ciclo es 0
        y no se suma, para que la serie sea la de siempre bit a bit.
        """
        effective_weeks = mission_week
        if self.plateau_weeks is not None:
            effective_weeks = min(mission_week, self.plateau_weeks)

        value = self.baseline + self.weekly_drift * effective_weeks
        if offset:
            value += offset
        if self.noise_sd:
            value += rng.normal(0.0, self.noise_sd)
        value *= scale
        if self.floor is not None:
            value = max(value, self.floor)
        if self.ceiling is not None:
            value = min(value, self.ceiling)
        return round(value, 3)


# Indicadores que solo existen en sus escenarios: el nominal no los genera, para que anadirlos
# no cambie lo que el resto de escenarios muestra. Valores nominales de diseño EMMA; la
# ingesta arranca en la provision minima de agua de NASA-STD-3001 [V2 6109], 2,5 L/dia.
def _hydration_models() -> dict[str, IndicatorModel]:
    return {
        "fluid-intake-24h": IndicatorModel("fluid-intake-24h", 2600.0, 0.0, 180.0, floor=300),
        "urine-volume-24h": IndicatorModel("urine-volume-24h", 1800.0, 0.0, 150.0, floor=200),
        "urine-specific-gravity": IndicatorModel(
            "urine-specific-gravity", 1.015, 0.0, 0.002, floor=1.001, ceiling=1.040
        ),
    }


def _nutrition_models() -> dict[str, IndicatorModel]:
    return {
        "energy-intake-daily": IndicatorModel(
            "energy-intake-daily", 2900.0, 0.0, 150.0, floor=800
        ),
        "food-acceptability": IndicatorModel(
            "food-acceptability", 7.2, 0.0, 0.4, floor=1, ceiling=9
        ),
        "appetite-rating": IndicatorModel("appetite-rating", 7.0, 0.0, 0.8, floor=0, ceiling=10),
        "food-rejected-fraction": IndicatorModel(
            "food-rejected-fraction", 8.0, 0.0, 3.0, floor=0, ceiling=100
        ),
    }


SCENARIO_ONLY_KEYS = frozenset({*_hydration_models(), *_nutrition_models()})
DAILY_KEYS = SCENARIO_ONLY_KEYS
DAILY_REPORT_HOUR = 7


def _default_models() -> dict[str, IndicatorModel]:
    """Linea base nominal de un tripulante sano en vuelo de larga duracion.

    NOMINAL ES UN CONTROL DE VERDAD. Aqui solo van las adaptaciones que ocurren
    inevitablemente y que ademas **se estabilizan**: desplazamiento de fluidos,
    desacondicionamiento cardiovascular temprano, recambio oseo. Nada mas.

    La tentacion es meter aqui la "degradacion tipica de una mision larga" —
    sueno que empeora, vigilancia que cae, animo que baja— porque es lo que se
    observa en muchas misiones. Seria un error: si el control ya se deteriora, no
    queda con que comparar los escenarios patologicos, y el sistema alerta en la
    demo que deberia estar tranquila. Ese deterioro vive en los escenarios
    (`PROGRESSIVE_INSOMNIA`, `IMMUNE_REACTIVATION`...), que es donde se puede
    encender y apagar.

    El ciclo menstrual tampoco va aqui: no es un deterioro sino un vaiven normal, y vive en
    `CrewMember.cycle`, apagado salvo que se pida. Asi el nominal sigue siendo el control de
    siempre y el ciclo se mide como lo que es, una fuente de falsa alarma posible.
    """
    lit = LITERATURE
    return {
        # Cardiovascular
        "heart-rate": IndicatorModel(
            "heart-rate", 62.0,
            weekly_drift=lit["resting_hr_drift_bpm_per_week"].value,
            noise_sd=2.5, floor=35, ceiling=190, plateau_weeks=12,
        ),
        "hrv-sdnn": IndicatorModel(
            "hrv-sdnn", 95.0,
            weekly_drift=-lit["hrv_sdnn_decline_ms_per_week"].value,
            noise_sd=6.0, floor=10, plateau_weeks=16,
        ),
        "hrv-rmssd": IndicatorModel(
            "hrv-rmssd", 48.0, -lit["hrv_rmssd_decline_ms_per_week"].value, 4.0,
            floor=5, plateau_weeks=16,
        ),
        "oxygen-saturation": IndicatorModel(
            "oxygen-saturation", 98.0, 0.0, 0.6, floor=70, ceiling=100
        ),
        "systolic-bp": IndicatorModel(
            "systolic-bp", 118.0, -lit["systolic_bp_decline_mmhg_per_week"].value, 4.0,
            floor=70, ceiling=200,
        ),
        "diastolic-bp": IndicatorModel(
            "diastolic-bp", 76.0, -lit["diastolic_bp_decline_mmhg_per_week"].value, 3.0,
            floor=40, ceiling=130,
        ),
        "respiratory-rate": IndicatorModel("respiratory-rate", 15.0, 0.0, 1.2, floor=6),
        "body-temperature": IndicatorModel("body-temperature", 36.7, 0.0, 0.18, floor=34),
        "orthostatic-drop": IndicatorModel(
            "orthostatic-drop", 6.0,
            # En microgravedad la medida ortostatica tiene poco significado:
            # la intolerancia se manifiesta al volver a gravedad. Se modela una
            # deriva pequena que satura pronto.
            weekly_drift=lit["orthostatic_drop_growth_per_week"].value,
            noise_sd=1.5, floor=0, plateau_weeks=6,
        ),
        # Conductual
        "sleep-duration": IndicatorModel(
            "sleep-duration", lit["iss_sleep_hours_actual"].value,
            weekly_drift=0.0, noise_sd=0.7, floor=0, ceiling=12,
        ),
        "sleep-efficiency": IndicatorModel(
            "sleep-efficiency", 88.0, 0.0, 3.0, floor=20, ceiling=100
        ),
        "pvt-mean-rt": IndicatorModel("pvt-mean-rt", 265.0, 0.0, 12.0, floor=150),
        "pvt-lapses": IndicatorModel("pvt-lapses", 1.0, 0.0, 0.8, floor=0),
        "circadian-shift": IndicatorModel(
            "circadian-shift", 0.0,
            weekly_drift=lit["circadian_drift_h_per_week"].value, noise_sd=0.25,
            # La tripulacion se reencarrila con la iluminacion y el horario de
            # mision: el desfase se estabiliza, no crece sin limite.
            plateau_weeks=2,
        ),
        "mood-valence": IndicatorModel("mood-valence", 7.5, 0.0, 0.8, floor=0, ceiling=10),
        # Radiacion
        "absorbed-dose-rate": IndicatorModel(
            "absorbed-dose-rate", 12.0, 0.0, 2.5, floor=0
        ),
        # Osea
        "exercise-minutes": IndicatorModel(
            "exercise-minutes", 95.0, -lit["exercise_minutes_decline_per_week"].value, 15.0,
            floor=0,
        ),
        "loading-impacts": IndicatorModel(
            "loading-impacts", 6500.0, -lit["loading_impacts_decline_per_week"].value, 900.0,
            floor=0,
        ),
        "ntx-telopeptide": IndicatorModel(
            "ntx-telopeptide", 35.0, lit["ntx_rise_per_week"].value, 4.0, floor=0
        ),
        # Inmune
        "symptom-burden": IndicatorModel(
            "symptom-burden", 0.4, lit["symptom_burden_rise_per_week"].value, 0.3,
            floor=0, ceiling=10,
        ),
        "cortisol-salivary": IndicatorModel(
            "cortisol-salivary", 0.29,
            weekly_drift=lit["cortisol_rise_per_week"].value, noise_sd=0.054, floor=0,
        ),
        "latent-virus-shedding": IndicatorModel(
            "latent-virus-shedding", 0.0, 0.0, 0.0, floor=0
        ),
    }


@dataclass
class CrewMember:
    subject_id: str
    models: dict[str, IndicatorModel] = field(default_factory=_default_models)
    # Opcional y apagado por defecto: sin el, la serie es la de siempre (ver `MenstrualCycle`).
    cycle: MenstrualCycle | None = None


class PhysiologicalSimulator:
    """Genera telemetria de tripulacion con derivas realistas.

    Reproducible: misma semilla, misma serie, hasta el ultimo decimal.
    """

    def __init__(
        self,
        scenario: Scenario = Scenario.NOMINAL,
        seed: int = 20261114,
        crew: CrewMember | None = None,
        mission_start: dt.date | None = None,
    ) -> None:
        self.scenario = scenario
        self.seed = seed
        self.crew = crew or CrewMember(subject_id="crew-01")
        self.mission_start = mission_start or dt.date(2026, 11, 1)
        self._models = self._apply_scenario(dict(self.crew.models))
        # Horas que **de verdad** duerme la tripulacion de la ISS, no las que
        # marca el plan de vuelo. Fija la ventana de sueno del horario de a bordo.
        self._sleep_hours = LITERATURE["iss_sleep_hours_actual"].value

    # ------------------------------------------------------------------ #

    def _apply_scenario(self, models: dict[str, IndicatorModel]) -> dict[str, IndicatorModel]:
        """Modifica los modelos base segun el escenario elegido."""
        from dataclasses import replace as _replace

        lit = LITERATURE

        if self.scenario is Scenario.PROGRESSIVE_INSOMNIA:
            models["sleep-duration"] = _replace(
                models["sleep-duration"],
                weekly_drift=-lit["insomnia_sleep_duration_drop_h_per_week"].value,
                noise_sd=lit["insomnia_sleep_duration_noise_sd_h"].value,
            )
            models["sleep-efficiency"] = _replace(
                models["sleep-efficiency"],
                weekly_drift=-lit["insomnia_sleep_efficiency_drop_pct_per_week"].value,
            )
            # La deuda de sueno degrada el rendimiento psicomotor: es el vinculo
            # que el motor de analisis debe detectar.
            models["pvt-mean-rt"] = _replace(
                models["pvt-mean-rt"],
                weekly_drift=lit["insomnia_pvt_rt_rise_ms_per_week"].value,
            )
            models["pvt-lapses"] = _replace(
                models["pvt-lapses"],
                weekly_drift=lit["insomnia_pvt_lapses_rise_per_week"].value,
            )
            models["mood-valence"] = _replace(
                models["mood-valence"], weekly_drift=-lit["insomnia_mood_drop_per_week"].value
            )

        elif self.scenario is Scenario.DEHYDRATION:
            models.update(_hydration_models())
            drop = LITERATURE["dehydration_urine_drop_ml_per_week"].value
            models["urine-volume-24h"] = _replace(
                models["urine-volume-24h"], weekly_drift=-drop
            )
            # Diseño: la ingesta cae algo mas que la orina y la densidad sube en proporcion.
            models["fluid-intake-24h"] = _replace(
                models["fluid-intake-24h"],
                weekly_drift=-drop * lit["dehydration_intake_to_urine_drop_ratio"].value,
            )
            models["urine-specific-gravity"] = _replace(
                models["urine-specific-gravity"],
                weekly_drift=lit["dehydration_specific_gravity_rise_per_week"].value,
            )

        elif self.scenario is Scenario.MENU_FATIGUE:
            models.update(_nutrition_models())
            drop = LITERATURE["menu_fatigue_acceptability_drop_per_week"].value
            models["food-acceptability"] = _replace(
                models["food-acceptability"], weekly_drift=-drop
            )
            # Diseño: menos agrado, menos ingesta, menos apetito y mas comida dejada. Derivas
            # pequeñas a proposito: es una hipotesis contestada, como la SDNN.
            models["energy-intake-daily"] = _replace(
                models["energy-intake-daily"],
                weekly_drift=-drop
                * lit["menu_fatigue_energy_kcal_per_acceptability_point"].value,
            )
            models["appetite-rating"] = _replace(
                models["appetite-rating"],
                weekly_drift=-drop * lit["menu_fatigue_appetite_per_acceptability_point"].value,
            )
            models["food-rejected-fraction"] = _replace(
                models["food-rejected-fraction"],
                weekly_drift=drop
                * lit["menu_fatigue_rejected_pct_per_acceptability_point"].value,
            )

        elif self.scenario is Scenario.CARDIOVASCULAR_DECONDITIONING:
            models["heart-rate"] = _replace(
                models["heart-rate"],
                weekly_drift=lit["deconditioning_hr_rise_bpm_per_week"].value,
            )
            models["hrv-sdnn"] = _replace(
                models["hrv-sdnn"],
                weekly_drift=-lit["deconditioning_sdnn_drop_ms_per_week"].value,
            )
            models["orthostatic-drop"] = _replace(
                models["orthostatic-drop"],
                weekly_drift=lit["deconditioning_orthostatic_growth_per_week"].value,
                plateau_weeks=None,
            )
            models["exercise-minutes"] = _replace(
                models["exercise-minutes"],
                weekly_drift=-lit["deconditioning_exercise_drop_min_per_week"].value,
            )

        elif self.scenario is Scenario.ARRHYTHMIA:
            # Variabilidad anomala: la media apenas se mueve, la dispersion se
            # dispara. Un umbral sobre la media sola no lo veria.
            models["heart-rate"] = _replace(
                models["heart-rate"], noise_sd=lit["arrhythmia_hr_noise_sd_bpm"].value
            )
            models["hrv-sdnn"] = _replace(
                models["hrv-sdnn"], noise_sd=lit["arrhythmia_sdnn_noise_sd_ms"].value
            )

        elif self.scenario is Scenario.IMMUNE_REACTIVATION:
            models["latent-virus-shedding"] = _replace(
                models["latent-virus-shedding"], baseline=0.0,
                weekly_drift=lit["immune_virus_shedding_rise_per_week"].value,
                noise_sd=lit["immune_virus_shedding_noise_sd"].value,
            )
            models["symptom-burden"] = _replace(
                models["symptom-burden"],
                weekly_drift=lit["immune_symptom_burden_rise_per_week"].value,
            )
            models["cortisol-salivary"] = _replace(
                models["cortisol-salivary"],
                weekly_drift=lit["immune_cortisol_rise_per_week"].value,
            )

        elif self.scenario is Scenario.SPE_EVENT:
            # La dosis se modela aparte, en `_dose_multiplier`: un SPE es un pico
            # agudo, no una deriva.
            models["symptom-burden"] = _replace(
                models["symptom-burden"],
                weekly_drift=lit["spe_symptom_burden_rise_per_week"].value,
            )

        return models

    def _spe_onset_day(self, total_days: int) -> float:
        """Cuando ocurre el evento solar dentro de la ventana generada.

        Se ancla al **final** de la ventana, no a un dia fijo. El estado de salud
        se evalua sobre las lecturas recientes, asi que un evento en el dia 5 de
        una mision de 40 ya habria decaido cuando se mira: el escenario existiria
        en los datos y seria invisible en la pantalla. Situarlo cerca del
        presente es lo que hace que la demo muestre lo que dice mostrar.

        En `spe-event-recovery` se ancla tambien al final, pero
        `spe_recovery_onset_days_before_end` dias antes: lo que se quiere ver en el presente es
        la vuelta, y el evento, en la linea temporal.
        """
        if self.scenario is Scenario.SPE_EVENT_RECOVERY:
            return max(0.5, total_days - LITERATURE["spe_recovery_onset_days_before_end"].value)
        return max(0.5, total_days - 1.5)

    def _dose_multiplier(self, mission_day: float, total_days: int) -> float:
        """Perfil temporal de un evento de particulas solares.

        Subida rapida, meseta de unas horas y decaimiento en dias. El pico llega
        a dos ordenes de magnitud sobre el fondo.
        """
        if self.scenario not in SPE_SCENARIOS:
            return 1.0

        elapsed = mission_day - self._spe_onset_day(total_days)
        if elapsed < 0:
            return 1.0
        peak = LITERATURE["spe_dose_peak_multiplier"].value
        rise = LITERATURE["spe_dose_rise_days"].value  # ~6 h de subida
        if elapsed < rise:
            return 1.0 + peak * (elapsed / rise)
        # Decaimiento exponencial con constante de ~1,5 dias
        decay = LITERATURE["spe_dose_decay_days"].value
        return 1.0 + peak * float(np.exp(-(elapsed - rise) / decay))

    # ------------------------------------------------------------------ #

    def generate(
        self,
        days: int = 30,
        samples_per_day: int = 24,
        keys: list[str] | None = None,
    ) -> Iterator[VitalObservation]:
        """Emite observaciones en orden cronologico.

        El orden de generacion es fijo (tiempo, luego clave ordenada) para que la
        secuencia del generador aleatorio sea reproducible.
        """
        rng = np.random.default_rng(self.seed)
        selected = sorted(keys) if keys else sorted(self._models)
        unknown = set(selected) - set(CATALOG)
        if unknown:
            raise KeyError(f"indicadores desconocidos: {sorted(unknown)}")

        start = dt.datetime.combine(self.mission_start, dt.time(0, 0, tzinfo=dt.UTC))
        interval = dt.timedelta(hours=24 / samples_per_day)
        effects, profile = _TIMED_EFFECTS.get(self.scenario, ({}, None))
        # El ciclo, si el tripulante lo tiene, es un termino aditivo por clave que no gasta
        # numeros aleatorios: con o sin el, el ruido de cada lectura es el mismo.
        cycle = self.crew.cycle
        version = f"simulator:{self.scenario}@{self.seed}"
        if cycle:
            version += f"+{cycle.label()}"

        for step in range(days * samples_per_day):
            moment = start + interval * step
            mission_day = step / samples_per_day
            context = context_at(
                moment.hour + moment.minute / 60.0, self._sleep_hours
            )
            # Cuanto del efecto agudo del escenario hay en este instante: igual para todas las
            # claves del paso, asi que se calcula una vez.
            level = profile(mission_day, days) if profile else 0.0
            # El parte diario de este dia, a su hora (`DAILY_REPORT_HOUR`). Lo da el paso cuyo
            # intervalo la contiene, y lleva la hora del parte, no la del paso: antes se pedia
            # `moment.hour == DAILY_REPORT_HOUR`, que con 96 muestras al dia lo repetia cuatro
            # veces y con 1, 2 o 5 no lo daba nunca. Con 24 es el mismo paso y el mismo instante.
            report = dt.datetime.combine(
                moment.date(), dt.time(DAILY_REPORT_HOUR, 0, tzinfo=dt.UTC)
            )
            reports_now = moment <= report < moment + interval
            report_day = (report - start).total_seconds() / 86_400

            for key in selected:
                model = self._models.get(key)
                if model is None:
                    continue
                # Una recogida de 24 h o un total diario se registra una vez al dia, no cada
                # hora: repetirlo 24 veces inventaria 23 medidas que nadie tomo.
                daily = key in DAILY_KEYS
                if daily and not reports_now:
                    continue
                at, at_day, at_context, at_level = (
                    (
                        report, report_day, context_at(float(DAILY_REPORT_HOUR),
                                                       self._sleep_hours),
                        profile(report_day, days) if profile else 0.0,
                    )
                    if daily else (moment, mission_day, context, level)
                )
                value = model.value_at(
                    at_day / 7.0, rng, CIRCADIAN_RATIO.get(key, {}).get(at_context, 1.0),
                    cycle.offset_at(key, at_day) if cycle else 0.0,
                )
                if key == "absorbed-dose-rate":
                    value = round(value * self._dose_multiplier(mission_day, days), 3)
                if at_level and key in effects:
                    value = CATALOG[key].clamp_to_physical(
                        round(value + effects[key] * at_level, 3)
                    )

                yield observation(
                    key=key,
                    value=value,
                    effective=at,
                    subject=self.crew.subject_id,
                    source=f"simulator:{self.scenario}",
                    context=at_context,
                    evidence_context=EvidenceContext.SIMULATED,
                    # Escenario y semilla reproducen la serie exacta (`describe()`); con ciclo,
                    # tambien el ciclo, que la cambia.
                    model_version=version,
                )

    def describe(self) -> dict[str, Any]:
        """Metadatos del escenario, para que la demo declare lo que esta mostrando."""
        return {
            "scenario": str(self.scenario),
            "seed": self.seed,
            "subject": self.crew.subject_id,
            "mission_start": self.mission_start.isoformat(),
            "reproducible": True,
            "evidence": evidence_by_class(),
            **({"cycle": self.crew.cycle.label()} if self.crew.cycle else {}),
        }


def domain_keys(domain: Domain) -> list[str]:
    return sorted(code.key for code in CATALOG.values() if code.domain is domain)
