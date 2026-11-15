"""Capa de evidencia: por que el sistema afirma lo que afirma.

Un astronauta que recibe una recomendacion sin saber en que se apoya tiene dos
opciones malas: obedecer a ciegas o ignorarla. La tercera opcion —entender el
razonamiento y decidir— es la que este modulo hace posible, y es exactamente lo
que pide el reto: que la tripulacion pueda **evaluar** su estado, no solo verlo.

Cada dominio clinico enlaza con el riesgo del NASA Human Research Program que le
corresponde y, cuando existe, con un estudio concreto del OSDR.

VOCABULARIO DE NASA, NO PROPIO
------------------------------
NASA tiene terminos establecidos para lo que hace este sistema, y usarlos situa
el proyecto dentro del programa real en vez de en su propio idioma:

  **EIMO** (Earth-Independent Medical Operations) — operaciones medicas
  independientes de la Tierra. Es el nombre del paradigma hacia el que trabaja
  ExMC, y es exactamente lo que EMMA implementa cuando `isolation_factor()`
  detecta que no hay consulta posible.

  **AMCL** (Accepted Medical Condition List) — la lista de condiciones medicas
  que ExMC considera que pueden ocurrir en exploracion, y el subconjunto tratable
  a bordo. Los cinco dominios clinicos de EMMA se mapean a ella mas abajo.

HONESTIDAD SOBRE EL ALCANCE
---------------------------
OSD-288 es *"Transcriptome analysis of murine spleen in space"*: RNA-Seq de bazo
de raton tras 35 dias en la ISS. Es evidencia **de que el vuelo espacial altera
la expresion genica inmune en un mamifero**. No es evidencia sobre un tripulante
concreto, ni sobre signos vitales humanos. La ficha lo dice con esas palabras,
porque presentar un estudio de raton como si midiera al astronauta seria
exactamente el tipo de exageracion que destruye la credibilidad de un sistema
clinico.
"""

from __future__ import annotations

from app.core import i18n
from app.evidence.registry import Citation, cite
from app.ingest.codes import Domain

# Una referencia citada para un dominio: la ficha vive en el registro unico
# (`evidence/registry.py`, por identificador) y aqui solo se dice por que se cita.
EvidenceItem = Citation


def _english(item: EvidenceItem, english: str) -> None:
    """Registra el inglés de la relevancia de una cita de este módulo. La ficha (título, cita,
    salvedad de alcance) es del registro y no se traduce aquí; `Citation.to_dict` resuelve la
    relevancia al servir."""
    if item.relevance is not None:
        i18n.en(item.relevance, english)


OSD_288 = cite(
    "osd-288",
    relevance=(
        "RNA-Seq de bazo de ratón tras 35 días en la ISS (misión SpaceX-9). "
        "El bazo es órgano linfoide: el estudio documenta alteración de la "
        "expresión génica inmune por exposición al vuelo espacial."
    ),
)
_english(
    OSD_288,
    "RNA-Seq of mouse spleen after 35 days on the ISS (SpaceX-9 mission). The spleen is a "
    "lymphoid organ: the study documents altered immune gene expression from exposure to "
    "spaceflight.",
)

HRP_RISKS: dict[Domain, EvidenceItem] = {
    Domain.CARDIOVASCULAR: cite(
        "hrp-risk-cardiovascular",
        relevance=(
            "El vuelo prolongado produce desacondicionamiento cardiovascular, "
            "reducción de volumen sistólico e intolerancia ortostática."
        ),
    ),
    Domain.BEHAVIORAL: cite(
        "hrp-risk-behavioral",
        relevance=(
            "El aislamiento, el confinamiento y la alteración circadiana degradan "
            "el sueño, el estado de ánimo y el rendimiento psicomotor."
        ),
    ),
    Domain.RADIATION: cite(
        "hrp-risk-radiation",
        relevance=(
            "Los rayos cósmicos galácticos y los eventos de partículas solares "
            "son la exposición que el blindaje de la nave no elimina."
        ),
    ),
    Domain.BONE: cite(
        "hrp-risk-bone",
        relevance=(
            "La descarga mecánica produce pérdida de densidad mineral ósea en "
            "hueso de carga, del orden de 1-1,5 % al mes sin contramedidas."
        ),
    ),
    Domain.IMMUNE: cite(
        "hrp-risk-immune",
        relevance=(
            "El vuelo espacial altera la función inmune y favorece la "
            "reactivación de herpesvirus latentes."
        ),
    ),
    Domain.NEURO_OCULAR: cite(
        "hrp-sans-evidence-report",
        relevance=(
            "El informe documenta la distensión de la vaina del nervio óptico en vuelo y "
            "describe la ecografía ocular antes, durante y después de la misión para "
            "vigilarla."
        ),
    ),
    Domain.GENITOURINARY: cite(
        "hrr-urinary-retention",
        relevance=(
            "Descrita en vuelo en varias ocasiones, sobre todo en las primeras 48 horas, "
            "como parte del síndrome de adaptación al espacio. Ha llegado a requerir "
            "sondaje a bordo."
        ),
    ),
    Domain.MUSCULOSKELETAL: cite(
        "kerstman-2012",
        relevance=(
            "Revisión de historias clínicas de Mercury a la ISS: el 52 % de los astronautas "
            "(382 de 728) refirió dolor de espalda al adaptarse a la microgravedad; en su "
            "mayoría leve (86 %), moderado en el 11 % y grave en el 3 %."
        ),
    ),
    Domain.NUTRITION: cite(
        "hrp-food-system-evidence-report",
        relevance=(
            "Ordena el sistema alimentario en seguridad, nutrición, aceptabilidad y uso de "
            "recursos, y trata la comida como factor modificable a diario: si no se come, "
            "una dieta completa no protege."
        ),
    ),
}
_english(
    HRP_RISKS[Domain.CARDIOVASCULAR],
    "Long-duration flight produces cardiovascular deconditioning, reduced stroke volume and "
    "orthostatic intolerance.",
)
_english(
    HRP_RISKS[Domain.BEHAVIORAL],
    "Isolation, confinement and circadian disruption degrade sleep, mood and psychomotor "
    "performance.",
)
_english(
    HRP_RISKS[Domain.RADIATION],
    "Galactic cosmic rays and solar particle events are the exposure that the spacecraft's "
    "shielding does not eliminate.",
)
_english(
    HRP_RISKS[Domain.BONE],
    "Mechanical unloading produces loss of bone mineral density in weight-bearing bone, on the "
    "order of 1-1.5 % per month without countermeasures.",
)
_english(
    HRP_RISKS[Domain.IMMUNE],
    "Spaceflight alters immune function and favors the reactivation of latent herpesviruses.",
)
_english(
    HRP_RISKS[Domain.NEURO_OCULAR],
    "The report documents the distension of the optic nerve sheath in flight and describes "
    "ocular ultrasound before, during and after the mission to watch it.",
)
_english(
    HRP_RISKS[Domain.GENITOURINARY],
    "Described in flight on several occasions, above all in the first 48 hours, as part of "
    "space adaptation syndrome. It has come to require catheterization on board.",
)
_english(
    HRP_RISKS[Domain.MUSCULOSKELETAL],
    "Review of medical records from Mercury to the ISS: 52 % of astronauts (382 of 728) "
    "reported back pain while adapting to microgravity; mostly mild (86 %), moderate in 11 % "
    "and severe in 3 %.",
)
_english(
    HRP_RISKS[Domain.NUTRITION],
    "It organizes the food system into safety, nutrition, acceptability and resource use, and "
    "treats food as a factor that can be modified daily: if it is not eaten, a complete diet "
    "does not protect.",
)

# Estudios OSDR asociados a cada dominio. Solo donde hay respaldo real: no se
# rellena por simetria.
OSD_569 = cite(
    "osd-569",
    relevance=(
        "Hemograma real de los cuatro tripulantes civiles de Inspiration4, antes y "
        "después de tres días en órbita. Los linfocitos de los cuatro bajaron al volver."
    ),
)
_english(
    OSD_569,
    "Real blood counts of the four civilian crew members of Inspiration4, before and after "
    "three days in orbit. The lymphocytes of all four fell on return.",
)

# Leido en su ficha de OSDR el 2026-09-28. La conversacion de origen lo presentaba como "datos
# de 59 astronautas": el estudio los analiza, pero los ficheros abiertos que deposita son de raton.
OSD_343 = cite(
    "osd-343",
    relevance=(
        "Análisis conjunto de cientos de muestras de vuelo, métricas de 59 astronautas y datos "
        "del Twins Study: enriquecimiento de la actividad mitocondrial y de la inmunidad "
        "innata en la respuesta al vuelo."
    ),
)
_english(
    OSD_343,
    "Joint analysis of hundreds of flight samples, metrics from 59 astronauts and data from the "
    "Twins Study: enrichment of mitochondrial activity and of innate immunity in the response "
    "to flight.",
)

TWINS_STUDY = cite(
    "nasa-twins-study",
    relevance=(
        "Casi un año en la ISS frente a su gemelo en Tierra, con diez equipos estudiando "
        "cambios fisiológicos, moleculares y cognitivos, antes, durante y después del vuelo."
    ),
)
_english(
    TWINS_STUDY,
    "Almost a year on the ISS compared with his twin on Earth, with ten teams studying "
    "physiological, molecular and cognitive changes before, during and after the flight.",
)

OSDR_BY_DOMAIN: dict[Domain, tuple[EvidenceItem, ...]] = {
    Domain.IMMUNE: (OSD_288, OSD_569, OSD_343, TWINS_STUDY),
}

# RIESGOS DEL HRP QUE UN DOMINIO CITA ADEMÁS DEL SUYO (decimosexta ronda, E9, 2026-10-23).
#
# El dominio genitourinario se construyó sobre la retención urinaria, pero su región y su alcance
# hablan también de «hidratación frente al riesgo de cálculos», y ese riesgo del HRP no tenía
# ficha. Se cita aquí y no en `HRP_RISKS`: el riesgo propio del dominio sigue siendo el mismo, y
# la cobertura de todos los riesgos del Roadmap (`evidence/hrp_coverage.py`) lo da como vigilado «en
# parte», porque EMMA no mide la química de la orina con que se valora. Citar no decide nada: no
# entra en `rules_version` ni mueve niveles, alertas o recomendaciones, y la evidencia de las
# recomendaciones sigue siendo la de antes (`countermeasure_evidence`).
RENAL_STONE = cite(
    "hrp-risk-renal-stone",
    relevance=(
        "El HRP lo enuncia así: con la bioquímica urinaria alterada en vuelo pueden aparecer "
        "cálculos sintomáticos. Su informe de evidencia de 2024 señala la deshidratación relativa, "
        "la orina sobresaturada y la mayor excreción de calcio por la pérdida ósea, y un modelo en "
        "que el riesgo sube cuando la orina baja de 1,5 litros al día."
    ),
)
_english(
    RENAL_STONE,
    "The HRP states it this way: with urinary biochemistry altered in flight, symptomatic "
    "stones may appear. Its 2024 evidence report points to relative dehydration, "
    "supersaturated urine and the greater excretion of calcium from bone loss, and to a model "
    "in which the risk rises when urine falls below 1.5 liters a day.",
)
ADDITIONAL_HRP_RISKS: dict[Domain, tuple[EvidenceItem, ...]] = {
    Domain.GENITOURINARY: (RENAL_STONE,),
}


def evidence_for(domain: Domain) -> list[EvidenceItem]:
    """Todas las referencias que respaldan la vigilancia de un dominio: su riesgo del HRP, los
    que cita además y sus estudios de OSDR, en ese orden."""
    return [*_own_risk(domain), *ADDITIONAL_HRP_RISKS.get(domain, ()),
            *OSDR_BY_DOMAIN.get(domain, ())]


def _own_risk(domain: Domain) -> tuple[EvidenceItem, ...]:
    risk = HRP_RISKS.get(domain)
    return (risk,) if risk is not None else ()


def countermeasure_evidence(domain: Domain) -> list[EvidenceItem]:
    """Lo que respalda las contramedidas del dominio cuando no tienen protocolo propio: su riesgo
    del HRP y sus estudios de OSDR, sin los riesgos que el dominio cita además.

    Por qué aparte: el detalle de una alerta rotula esas fichas «riesgo del dominio», y una
    comprobación de retención urinaria no se apoya en el riesgo de cálculos. Así, citar un riesgo
    además no cambia la evidencia de ninguna recomendación."""
    return [*_own_risk(domain), *OSDR_BY_DOMAIN.get(domain, ())]


# --------------------------------------------------------------------------- #
# Marco de ExMC: EIMO y AMCL
# --------------------------------------------------------------------------- #

EIMO_DESCRIPTION = (
    "Earth-Independent Medical Operations: la transición gradual de la asistencia "
    "médica y de la toma de decisiones de los recursos en Tierra a los del espacio "
    "(ConOps de EIMO, NTRS 20240001402). ExMC lo llama un paradigma nuevo, necesario "
    "para los futuros sistemas de Artemis y Marte (NTRS 20230015831)."
)
i18n.en(
    EIMO_DESCRIPTION,
    "Earth-Independent Medical Operations: the gradual transition of medical care and of "
    "decision-making from the resources on Earth to those in space (EIMO ConOps, NTRS "
    "20240001402). ExMC calls it a new paradigm, necessary for the future Artemis and Mars "
    "systems (NTRS 20230015831).",
)

# Como se relaciona cada dominio de EMMA con la lista de condiciones de ExMC.
# Se declara el **alcance real**: que parte de la condicion vigila el sistema y
# cual no, para no dar a entender que cubre la condicion entera.
AMCL_ALIGNMENT: dict[Domain, str] = {
    Domain.CARDIOVASCULAR: (
        "Arritmias y desacondicionamiento cardiovascular. EMMA vigila la "
        "tendencia y la desviación; no diagnostica la arritmia concreta"
    ),
    Domain.BEHAVIORAL: (
        "Salud conductual y deterioro del rendimiento. Vigilancia objetiva por "
        "PVT y sueño; la evaluación conductual formal es de un profesional"
    ),
    Domain.RADIATION: (
        "Exposición aguda a partículas solares y dosis de carrera acumulada. "
        "Alerta y refugio, no tratamiento del síndrome de radiación"
    ),
    Domain.BONE: (
        "Pérdida de masa ósea y riesgo de fractura. Se vigila la adherencia a la "
        "contramedida y el marcador de resorción; no se mide densidad ósea"
    ),
    Domain.IMMUNE: (
        "Desregulación inmune y reactivación de virus latentes. Registro de "
        "síntomas y marcadores; no hay hemograma de uso ordinario a bordo. En la ISS se "
        "contaron leucocitos en una demostración tecnológica (diciembre de 2020 y enero de "
        "2021), no con un equipo de uso ordinario (Perusek et al., 2022, NTRS 20210026808; "
        "Gilkey et al., 2024, NTRS 20240004905)"
    ),
    Domain.NEURO_OCULAR: (
        "Síndrome neuro-ocular asociado al vuelo. Se vigila la vaina del nervio "
        "óptico por ecografía frente a la línea base; no hay fondo de ojo ni OCT"
    ),
    Domain.GENITOURINARY: (
        "Retención urinaria de adaptación al vuelo e hidratación frente al riesgo de "
        "cálculos. Se mide el volumen vesical por ecografía y se registran ingesta y orina; "
        "la decisión de sondar es del médico de a bordo y no hay análisis de orina completo"
    ),
    Domain.MUSCULOSKELETAL: (
        "Dolor de espalda de adaptación y lesiones musculoesqueléticas. Se registra el "
        "dolor que refiere el tripulante, dónde y cómo; no hay exploración física ni "
        "imagen de columna. Agrupa además, solo descriptivas y sin evaluarlas, la prensión, la "
        "masa magra por DXA, la tracción isométrica y dos pruebas funcionales de equilibrio y "
        "marcha de antes y después del vuelo"
    ),
    Domain.NUTRITION: (
        "Sistema alimentario: ingesta real y aceptabilidad de la comida. Se registra lo que "
        "se come y cómo se valora; no se prescribe dieta ni suplementos"
    ),
}
# El inglés dice lo mismo y calla lo mismo: qué vigila el sistema y qué no. Donde el castellano
# dice «no diagnostica», el inglés dice que no identifica: EMMA no nombra una enfermedad.
i18n.en_many({
    AMCL_ALIGNMENT[Domain.CARDIOVASCULAR]: (
        "Arrhythmias and cardiovascular deconditioning. EMMA watches the trend and the "
        "deviation; it does not identify the specific arrhythmia"
    ),
    AMCL_ALIGNMENT[Domain.BEHAVIORAL]: (
        "Behavioral health and performance decrements. Objective monitoring by PVT and sleep; "
        "the formal behavioral assessment belongs to a professional"
    ),
    AMCL_ALIGNMENT[Domain.RADIATION]: (
        "Acute exposure to solar particles and accumulated career dose. Alert and shelter, not "
        "treatment of radiation syndrome"
    ),
    AMCL_ALIGNMENT[Domain.BONE]: (
        "Loss of bone mass and fracture risk. Adherence to the countermeasure and the "
        "resorption marker are watched; bone density is not measured"
    ),
    AMCL_ALIGNMENT[Domain.IMMUNE]: (
        "Immune dysregulation and reactivation of latent viruses. Record of symptoms and "
        "markers; there is no blood count in ordinary use on board. On the ISS, leukocytes "
        "were counted in a technology demonstration (December 2020 and January 2021), not with "
        "equipment in ordinary use (Perusek et al., 2022, NTRS 20210026808; Gilkey et al., "
        "2024, NTRS 20240004905)"
    ),
    AMCL_ALIGNMENT[Domain.NEURO_OCULAR]: (
        "Spaceflight-associated neuro-ocular syndrome. The optic nerve sheath is watched by "
        "ultrasound against the baseline; there is no fundus examination or OCT"
    ),
    AMCL_ALIGNMENT[Domain.GENITOURINARY]: (
        "Urinary retention of adaptation to flight, and hydration against the risk of stones. "
        "Bladder volume is measured by ultrasound and intake and urine are recorded; the "
        "decision to catheterize belongs to the on-board physician and there is no complete "
        "urinalysis"
    ),
    AMCL_ALIGNMENT[Domain.MUSCULOSKELETAL]: (
        "Back pain of adaptation and musculoskeletal injuries. The pain the crew member "
        "reports is recorded, where and how; there is no physical examination or spine "
        "imaging. It also groups, descriptive only and without evaluating them, grip strength, "
        "lean mass by DXA, isometric pull and two functional tests of balance and gait from "
        "before and after the flight"
    ),
    AMCL_ALIGNMENT[Domain.NUTRITION]: (
        "Food system: actual intake and acceptability of food. What is eaten and how it is "
        "rated is recorded; no diet or supplements are prescribed"
    ),
})


def amcl_alignment(domain: Domain) -> str:
    """Que parte del marco de ExMC cubre este dominio, y que parte no."""
    return i18n.loc(AMCL_ALIGNMENT[domain])
