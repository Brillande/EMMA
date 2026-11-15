"""La entidad Riesgo, junta (especificación del equipo §3).

Por qué existe: la especificación pide de cada riesgo «risk_id, RIDGE category, human_system,
evidence_refs, severity schema, uncertainty», y EMMA lo tenía todo pero repartido: el dominio y
su peligro RIDGE en `ingest/codes.py`, el riesgo del HRP en `evidence/links.py`, las regiones
del cuerpo en `anatomy.py`, y los umbrales de nivel solo dentro de la huella de
`rules_version`. Nadie podía leer un riesgo entero sin abrir cuatro módulos.

Aquí NO se calcula nada nuevo: cada campo se lee de donde vive su regla. El esquema de niveles
sale de `analysis/risk.py` en cada llamada —no hay copia que pueda divergir— y una prueba falla
si lo que se publica deja de clasificar una puntuación como la clasifica el motor.

LA INCERTIDUMBRE NO LLEVA NÚMERO. EMMA no tiene con qué dar una probabilidad ni un intervalo
de un riesgo, y no se inventan. Lo que sabe decir es lo que sabe de su evidencia: el grado de
cada ficha citada, qué campos de esas fichas están sin verificar, cuántas contramedidas del
dominio son `demo`, y con qué clase de indicadores se evalúa el dominio. Eso se enseña, con
esas palabras, y la respuesta dice que no hay cuantificación.

LA MATRIZ: PELIGRO, EFECTO, VARIABLE, DATO, DETECCIÓN, CONTRAMEDIDA. La conversación de
ideación (`docs/contexto/conversacion-ideacion-v1.md`) propone leer cada riesgo como una cadena
«NASA Hazard → Biological effect → Observable variable → NASA dataset → Detection model →
Countermeasure», y pide para cada problema «cómo se previene, cómo se detecta, qué
contramedidas existen». Los eslabones estaban todos en EMMA, pero la ficha de un riesgo solo
contaba sus contramedidas, mezclaba conjuntos de datos con artículos y no decía con qué regla se
detecta. Ahora cada riesgo lleva su fila entera:

  * el efecto es la relevancia con que se cita el riesgo del HRP del dominio (`evidence/links.py`);
  * el dato separa la evidencia citada en conjuntos de datos y documentos por la clase de
    documento del registro (`evidence_type`), sin reclasificar nada a mano;
  * la detección se LEE DEL MOTOR: las ventanas, cuantiles, persistencia, ráfaga, puntos y
    tendencia son las constantes de `analysis/` en cada consulta, y lo que el motor no tiene en
    una constante —el factor de aislamiento, que no se aplica a la radiación, y lo que suman un
    evento solar o la dosis acumulada— se mide preguntándole a `RiskEngine` con entradas de
    prueba. Una prueba falla si lo publicado deja de ser lo que el motor hace;
  * las contramedidas son las de la biblioteca (`advisor/countermeasures.py`), una a una, con su
    base, y la de refugio dice que va por evento y no por nivel.

QUÉ VALIDA MMASH EN CADA DOMINIO, Y CON QUÉ SE MIDE CADA VARIABLE (decimoquinta ronda). La regla
decía «Dónde se ha medido» con la ficha de MMASH, pero una fila no decía si alguno de sus
indicadores sale de ese conjunto: leída la matriz, la falsa alarma medida con personas sanas
parecía de todos los dominios, y solo unos pocos indicadores salen de MMASH. Ahora cada riesgo dice
cuáles —las claves que emite el cargador (`validation/mmash.py`, `LOADED`), no una lista copiada—
y que eso valida el motor de medida y la falsa alarma en Tierra, no la fisiología espacial; el
dominio sin ninguno lo dice. Y la variable lleva su equipo, el del coste de medir
(`measurement_cost.json`), agrupado: el equipo de a bordo, no el aparato con que se midió en MMASH,
que va aparte con la palabra del cargador. Nada de esto entra en `rules_version`: ni
`validation/` ni el coste de medir deciden nada.

SOBRE QUÉ INDICADORES SE HA MEDIDO LA SENSIBILIDAD (decimosexta ronda). La falsa alarma sale de
MMASH, pero la sensibilidad se mide inyectando deterioros sobre esa fisiología, y solo sobre
algunas claves. La fila decía en general que «la sensibilidad se mide inyectando deterioros solo en
algunos de estos indicadores», sin decir cuáles. Ahora cada indicador dice si recibe un deterioro y
cuál —las claves y formas que construye el inyector (`validation/injection.py`,
`REFERENCE_TARGETS`), no una lista copiada— y la fila remite a `compliance/external-validation.md`
para las cifras, que aquí no se copian. Tampoco entra en `rules_version`.

LAS FICHAS DE LA FRASE DE CADA REGIÓN (decimoséptima ronda). «Sistema humano» enseñaba la frase de
cada región sin las fichas que nombra: la vejiga habla del riesgo de cálculos, el hígado de
MedlinePlus y los pulmones del NHLBI, y en la matriz no se veía de dónde salía nada de eso. La
región ya las lleva (`note_refs` y `analytes_source`, en `anatomy.Region.to_dict`), con la forma de
toda cita (`registry.cite`); aquí se sirven tal cual, sin una lista propia. La capa de evidencia
de investigación del hígado no es de la frase y no viaja con el riesgo: sale solo en su cadena.

Solo lectura y sin tripulante: no mira ninguna observación, no firma nada y no mueve niveles,
umbrales ni alertas (invariante 5). Las entradas de prueba con que se interroga al motor son de
un sujeto ficticio, no pasan por el ledger y no se guardan.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app import anatomy
from app.advisor.countermeasures import BASES, LIBRARY_PATH, SHELTER_ID, for_domain, library
from app.analysis import baseline, risk, trend
from app.analysis.alert_support import BASIS_DISPLAY
from app.analysis.baseline import Deviation, Severity
from app.analysis.inferred import bone_density_band
from app.analysis.risk import RiskEngine, RiskLevel
from app.core import display, i18n
from app.core.versioning import rules_version
from app.environment.donki import EventType, SolarEvent
from app.environment.donki import Severity as SolarSeverity
from app.environment.ephemeris import AUTONOMY_THRESHOLD_MINUTES, CommsWindow
from app.evidence import registry
from app.evidence.links import HRP_RISKS, EvidenceItem, amcl_alignment, evidence_for
from app.ingest.codes import CATALOG, Domain, VitalCode, evaluated_by_domain
from app.ingest.cost import COST_PATH, MODES, costs
from app.ingest.fhir import LOW_CONFIDENCE_THRESHOLD
from app.validation import injection, mmash
from app.validation.mmash import DATASET as VALIDATION_DATASET

# De dónde sale la categoría RIDGE de cada dominio: la ficha que ya cita `ingest/codes.py`.
RIDGE_SOURCE = "nasa-human-body-in-space"

NOT_QUANTIFIED = (
    "EMMA no cuantifica la incertidumbre de este riesgo: no da probabilidad ni intervalo. Lo "
    "que se enseña es cómo de firme es la evidencia que cita y con qué clase de indicadores se "
    "evalúa el dominio."
)
SCHEMA_BASIS = (
    "Umbrales de puntuación que usa el motor (`analysis/risk.py`), leídos de él en cada "
    "consulta. Son de diseño de EMMA, sin fuente clínica; lo que se ha medido de ellos está en "
    "la validación externa (`compliance/external-validation.md`)."
)
HUMAN_SYSTEM_BASIS = (
    "Mapa de presentación de EMMA (`anatomy.py`): dice de qué región habla el dominio, no "
    "afirma nada clínico. Una región sin nivel propio, como el hígado, se nombra en el riesgo "
    "del dominio de su nivel. Bajo la frase de una región van las fichas que esa frase nombra."
)
EVALUATION_BASIS = (
    "Cómo se obtiene cada indicador según el coste de medir (`measurement_cost.json`). Si una "
    "lectura concreta es medida, inferida o predicha lo declara la propia lectura y se ve en "
    "el estado del tripulante."
)
# El modo del coste de medir que dice que un indicador no se mide: se calcula.
CALCULATED_MODE = "derived"
# Con qué se evalúa un dominio, por las palabras con que se enseña.
EVALUATED_WITH: dict[str, str] = {
    "measured": "con indicadores que se miden",
    "calculated-only": "solo con indicadores calculados a partir de otras medidas",
    "none": "con ningún indicador: el dominio no tiene ninguno en el catálogo",
}
DEMO_NOTE = (
    "Una contramedida «demo» solo tiene detrás el riesgo del dominio, no un protocolo que "
    "respalde la acción concreta."
)
# Estados que EMMA solo infiere, por dominio, y de dónde sale cada uno (`analysis/inferred.py`).
# Un estado inferido no entra en la puntuación del dominio: se enseña aparte, rotulado.
_INFERRED = {Domain.BONE: bone_density_band}
INFERRED_NOTE = "Estado inferido, no medido; no entra en la puntuación del dominio."

# --- La matriz de riesgos: los seis eslabones de la conversación, en su orden -----------------
CHAIN_LINKS: tuple[tuple[str, str], ...] = (
    ("hazard", "Peligro"),
    ("effect", "Efecto"),
    ("variables", "Variable"),
    ("data", "Dato"),
    ("detection", "Detección"),
    ("countermeasures", "Contramedida"),
)
CHAIN_BASIS = (
    "Cadena de la conversación de ideación: peligro RIDGE, efecto biológico, variable "
    "observable, conjunto de datos, regla de detección y contramedida. Cada eslabón se lee de "
    "donde vive su regla; la matriz no decide nada ni mueve niveles."
)
EFFECT_BASIS = (
    "Lo que dice del efecto la ficha con que EMMA cita el riesgo del dominio "
    "(`evidence/links.py`)."
)
NO_EFFECT = "Sin riesgo del HRP enlazado para este dominio."
# La clase de documento del registro que es un conjunto de datos; las demás son documentos.
DATASET_TYPE = "dataset"
DATA_BASIS = (
    "Separada por la clase de documento del registro de evidencia (`evidence_type`): los "
    "conjuntos de datos a un lado; artículos, normas, informes y páginas al otro."
)
NO_DATASETS = "Ningún conjunto de datos citado para este dominio."
NO_DOCUMENTS = "Ningún documento citado para este dominio."
DETECTION_BASIS = (
    "Leída del motor (`analysis/`) en cada consulta: las cifras son las constantes que usa, y lo "
    "que no tiene en una constante se mide preguntándole con entradas de prueba. No es una copia."
)
DETECTION_RULE_DISPLAY = "Regla de detección"
VALIDATED_WITH_DISPLAY = "Dónde se ha medido"
VALIDATION_STATEMENT = (
    "La tasa de falsa alarma y la sensibilidad de esta regla se miden sobre este conjunto de "
    "datos; las cifras vigentes están en `compliance/external-validation.md`."
)
# Qué indicadores de cada dominio salen de MMASH (las claves del cargador) y qué valida eso.
MMASH_BASIS = (
    "Las claves que emite el cargador de MMASH (`validation/mmash.py`), leídas de la tabla con "
    "que las emite; una prueba falla si lo cargado deja de ser esa tabla. El aparato es el del "
    "conjunto de datos, no el de a bordo."
)
NO_MMASH = (
    "Ningún indicador de este dominio sale de MMASH: la falsa alarma de sus indicadores no se ha "
    "medido sobre personas reales."
)
# Sobre qué indicadores de cada dominio se mide la sensibilidad, inyectando deterioros.
SENSITIVITY_REFERENCE = "compliance/external-validation.md"
SENSITIVITY_BASIS = (
    "Las claves y formas que construye el inyector (`validation/injection.py`), leídas de sus "
    "deterioros de referencia; una prueba falla si lo publicado deja de ser lo que se inyecta. "
    "Las cifras de sensibilidad no se copian aquí."
)
NO_SENSITIVITY = (
    "Ningún indicador de este dominio recibe un deterioro inyectado: su sensibilidad no se ha "
    "medido."
)
# El equipo de cada variable, del coste de medir; uno sin equipo declarado se dice.
EQUIPMENT_BASIS = (
    "El equipo de cada indicador, del coste de medir (`measurement_cost.json`): con qué se "
    "obtendría a bordo. No decide nada."
)
NO_EQUIPMENT = "sin equipo declarado en el coste de medir"
NO_INDICATORS_DETECTION = "Sin indicadores en el catálogo: no hay desviación ni deriva que detectar"
NO_ISOLATION_PROBE = "Sin indicadores con que comprobar el factor de aislamiento."
NO_ISOLATION = "La puntuación de este dominio no se multiplica por el factor de aislamiento."
ON_EVENT = "Se ofrece con un evento solar activo, no por el nivel del dominio."
# Los tres tramos de `VitalCode.critical_bounds`, por el estado de la lectura: «reposo» es sin
# esfuerzo físico (`baseline.crossed_danger_limit`: la familia de reposo y el sueño), esfuerzo es
# la actividad, y lo demás es una lectura sin estado. La prueba recorre cada estado.
RESTING_STATES = "sin esfuerzo físico (reposo, sueño, trabajo o comida)"
EXERTION_STATE = "en esfuerzo"
OTHER_STATE = "sin estado declarado"
COUNTERMEASURES_BASIS = (
    "Las de la biblioteca de contramedidas (`advisor/countermeasures.py`), en su orden, con la "
    "base de cada una."
)
NO_COUNTERMEASURES = "Ninguna contramedida en la biblioteca para este dominio."
# La gravedad de una lectura y la de un evento solar, con la palabra con que se enseñan.
FINDING_SEVERITY_DISPLAY: dict[Severity, str] = {
    Severity.MILD: "leve",
    Severity.MODERATE: "moderada",
    Severity.SEVERE: "grave",
}
SOLAR_SEVERITY_DISPLAY: dict[SolarSeverity, str] = {
    SolarSeverity.NOMINAL: "nominal",
    SolarSeverity.ELEVATED: "elevada",
    SolarSeverity.HIGH: "alta",
    SolarSeverity.SEVERE: "severa",
}
# Hasta cuántas lecturas en la ventana se enseña la escalera de la ráfaga; más allá sigue
# creciendo, y lo dice la frase. No decide nada: el motor la calcula para cada ventana.
BURST_TABLE_READINGS = 1000
# Las entradas de prueba con que se interroga al motor: un sujeto que no existe, un instante
# cualquiera y un retardo muy por encima de cualquiera real, con el aislamiento ya saturado.
# No pasan por el ledger ni por el almacén; solo se le pregunta a `RiskEngine.assess`.
_PROBE_SUBJECT = "sonda-de-la-matriz"
_PROBE_TIME = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
_PROBE_READINGS = 3
_PROBE_FAR_MINUTES = 100_000
# Cuánto se pasa del umbral de autonomía para leer el primer factor, y cuántas bisecciones bastan
# para fijar el retardo de saturación a la centésima de minuto entre el umbral y el retardo lejano.
_PROBE_STEP_MINUTES = 1e-6
_PROBE_BISECTIONS = 40

# El inglés de las constantes de arriba (`core/i18n.py`): ellas no se mueven —las fijan las pruebas
# en castellano y las campañas de mutantes— y lo que sale por `payload` y `summary` se resuelve
# allí, al servir (`_served`). Dice lo mismo que el castellano y no más: cada «no», cada «sin».
i18n.en_many({
    NOT_QUANTIFIED: (
        "EMMA does not quantify the uncertainty of this risk: it gives no probability or "
        "interval. What is shown is how firm the cited evidence is and with what kind of "
        "indicators the domain is evaluated."
    ),
    SCHEMA_BASIS: (
        "Score thresholds used by the engine (`analysis/risk.py`), read from it on every query. "
        "They are EMMA's design, with no clinical source; what has been measured of them is in "
        "the external validation (`compliance/external-validation.md`)."
    ),
    HUMAN_SYSTEM_BASIS: (
        "EMMA's presentation map (`anatomy.py`): it says which region the domain is about, and "
        "asserts nothing clinical. A region with no level of its own, such as the liver, is "
        "named in the risk of the domain whose level it takes. Under a region's sentence go the "
        "records that sentence names."
    ),
    EVALUATION_BASIS: (
        "How each indicator is obtained according to the measurement cost "
        "(`measurement_cost.json`). Whether a given reading is measured, inferred or predicted "
        "is declared by the reading itself and is seen in the crew member's status."
    ),
    EVALUATED_WITH["measured"]: "with indicators that are measured",
    EVALUATED_WITH["calculated-only"]: "only with indicators calculated from other measurements",
    EVALUATED_WITH["none"]: "with no indicator: the domain has none in the catalog",
    DEMO_NOTE: (
        "A «demo» countermeasure has only the domain's risk behind it, not a protocol that "
        "supports the specific action."
    ),
    INFERRED_NOTE: "Inferred state, not measured; it does not enter the domain's score.",
    "Peligro": "Hazard",
    "Efecto": "Effect",
    "Variable": "Variable",
    "Dato": "Data",
    "Detección": "Detection",
    "Contramedida": "Countermeasure",
    CHAIN_BASIS: (
        "The chain from the ideation conversation: RIDGE hazard, biological effect, observable "
        "variable, dataset, detection rule and countermeasure. Each link is read from where its "
        "rule lives; the matrix decides nothing and moves no levels."
    ),
    EFFECT_BASIS: (
        "What the record with which EMMA cites the domain's risk says about the effect "
        "(`evidence/links.py`)."
    ),
    NO_EFFECT: "No HRP risk linked to this domain.",
    DATA_BASIS: (
        "Split by the document class in the evidence registry (`evidence_type`): datasets on "
        "one side; papers, standards, reports and pages on the other."
    ),
    NO_DATASETS: "No dataset cited for this domain.",
    NO_DOCUMENTS: "No document cited for this domain.",
    DETECTION_BASIS: (
        "Read from the engine (`analysis/`) on every query: the figures are the constants it "
        "uses, and what it does not hold in a constant is measured by asking it with probe "
        "inputs. It is not a copy."
    ),
    DETECTION_RULE_DISPLAY: "Detection rule",
    VALIDATED_WITH_DISPLAY: "Where it has been measured",
    VALIDATION_STATEMENT: (
        "The false alarm rate and the sensitivity of this rule are measured on this dataset; "
        "the current figures are in `compliance/external-validation.md`."
    ),
    MMASH_BASIS: (
        "The keys the MMASH loader emits (`validation/mmash.py`), read from the table it emits "
        "them from; a test fails if what is loaded stops being that table. The device is the "
        "dataset's, not the onboard one."
    ),
    NO_MMASH: (
        "No indicator of this domain comes from MMASH: the false alarm rate of its indicators "
        "has not been measured on real people."
    ),
    SENSITIVITY_BASIS: (
        "The keys and shapes the injector builds (`validation/injection.py`), read from its "
        "reference deteriorations; a test fails if what is published stops being what is "
        "injected. The sensitivity figures are not copied here."
    ),
    NO_SENSITIVITY: (
        "No indicator of this domain receives an injected deterioration: its sensitivity has "
        "not been measured."
    ),
    EQUIPMENT_BASIS: (
        "The equipment of each indicator, from the measurement cost (`measurement_cost.json`): "
        "what it would be obtained with on board. It decides nothing."
    ),
    NO_EQUIPMENT: "no equipment declared in the measurement cost",
    NO_INDICATORS_DETECTION: (
        "No indicators in the catalog: there is no deviation or drift to detect"
    ),
    NO_ISOLATION_PROBE: "No indicators with which to check the isolation factor.",
    NO_ISOLATION: "The score of this domain is not multiplied by the isolation factor.",
    ON_EVENT: "Offered with an active solar event, not by the domain's level.",
    RESTING_STATES: "without physical exertion (rest, sleep, work or meal)",
    EXERTION_STATE: "during exertion",
    OTHER_STATE: "with no declared state",
    COUNTERMEASURES_BASIS: (
        "Those in the countermeasure library (`advisor/countermeasures.py`), in its order, each "
        "with its basis."
    ),
    NO_COUNTERMEASURES: "No countermeasure in the library for this domain.",
    FINDING_SEVERITY_DISPLAY[Severity.MILD]: "mild",
    FINDING_SEVERITY_DISPLAY[Severity.MODERATE]: "moderate",
    FINDING_SEVERITY_DISPLAY[Severity.SEVERE]: "severe",
    SOLAR_SEVERITY_DISPLAY[SolarSeverity.NOMINAL]: "nominal",
    SOLAR_SEVERITY_DISPLAY[SolarSeverity.ELEVATED]: "elevated",
    SOLAR_SEVERITY_DISPLAY[SolarSeverity.HIGH]: "high",
    SOLAR_SEVERITY_DISPLAY[SolarSeverity.SEVERE]: "severe",
})

# Los JSON de otros módulos cuyas cadenas salen de aquí tal cual, sin pasar por quien los sirve:
# la acción de una contramedida y el equipo del coste de medir. Si llevan hermano inglés
# (`<nombre>.en.json`), se aplica; si no, la cadena sale como está.
_SERVED_DATA = (LIBRARY_PATH, COST_PATH)


def _worded(text: str) -> str:
    """Un rótulo o una frase en el idioma de la petición: una constante registrada con `i18n.en`
    (de este módulo o de aquel del que se lee) o una cadena de los JSON de `_SERVED_DATA`."""
    found = i18n.loc(text)
    for path in _SERVED_DATA:
        if found != text:
            break
        found = i18n.localized(text, path)
    return found


def _localized(value: Any, key: str | None = None) -> Any:
    """Recorre lo que se sirve y pone en inglés sus textos enteros; nunca una clave.

    Un identificador (una clave de indicador, un nivel, una clase) no se traduce: solo se mira
    una cadena si va en un campo de rótulo (`display`, `*_display`) o si lleva un espacio, que
    un identificador no lleva. Las frases compuestas ya llegan en inglés (`i18n.tr`).
    """
    if isinstance(value, str):
        labelled = key is not None and (key == "display" or key.endswith("_display"))
        return _worded(value) if labelled or " " in value else value
    if isinstance(value, dict):
        return {name: _localized(item, name) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_localized(item, key) for item in value]
    return value


def _served(value: dict[str, Any]) -> dict[str, Any]:
    """Lo que sale del módulo, en el idioma de la petición. En castellano, el mismo objeto."""
    if i18n.current() != "en":
        return value
    localized: dict[str, Any] = _localized(value)
    return localized


def severity_schema() -> dict[str, Any]:
    """Los niveles del motor con la puntuación desde la que empieza cada uno.

    Se lee de `risk._LEVEL_THRESHOLDS` cada vez: si el motor cambia un umbral, esto lo dice sin
    que nadie lo toque. El nivel sin umbral (nominal) es el de toda puntuación por debajo del
    primero, y por eso su `min_score` es `None` y no un cero puesto a mano.
    """
    floor = {level: minimum for minimum, level in risk._LEVEL_THRESHOLDS}
    base = [level for level in RiskLevel if level not in floor]
    ordered = base + sorted(floor, key=lambda level: floor[level])
    return {
        "levels": [
            {
                "level": str(level),
                # La palabra de cada nivel la da el motor; la interfaz no la escribe.
                "display": level.display,
                "label": level.label,
                "min_score": floor.get(level),
            }
            for level in ordered
        ],
        "basis": SCHEMA_BASIS,
        "rules_version": rules_version(),
    }


def level_from_schema(schema: Mapping[str, Any], score: float) -> str:
    """El nivel que el esquema publicado da a una puntuación. Solo para comprobarlo contra el
    motor (`risk.level_for`): quien consume el esquema lo lee así."""
    found = next(item["level"] for item in schema["levels"] if item["min_score"] is None)
    for item in schema["levels"]:
        if item["min_score"] is not None and score >= item["min_score"]:
            found = item["level"]
    return str(found)


def evaluation(domain: Domain, modes: Mapping[str, str]) -> dict[str, Any]:
    """Con qué clase de indicadores se evalúa un dominio: medidos, solo calculados o ninguno.

    `modes` es el modo de cada indicador en el coste de medir. No mira lecturas: describe el
    catálogo, no a un tripulante.
    """
    # Los descriptivos no evalúan el riesgo: el estado no los lee (`codes.DESCRIPTIVE_ONLY`).
    keys = [code.key for code in evaluated_by_domain(domain)]
    calculated = [key for key in keys if modes.get(key) == CALCULATED_MODE]
    measured = [key for key in keys if key not in calculated]
    kind = "measured" if measured else "calculated-only" if calculated else "none"
    inferred = _INFERRED.get(domain)
    states: list[dict[str, Any]] = []
    if inferred is not None:
        band = inferred(0.0, False)
        states.append({
            "key": band["key"],
            "display": band["display"],
            "observation_type": band["observation_type"],
            "model_version": band["model_version"],
            "basis": band["basis"],
            "note": INFERRED_NOTE,
        })
    return {
        "evaluated_with": kind,
        "evaluated_with_display": EVALUATED_WITH[kind],
        "indicators": len(keys),
        "measured": len(measured),
        "calculated": calculated,
        "calculated_display": MODES[CALCULATED_MODE],
        "inferred_states": states,
        "basis": EVALUATION_BASIS,
    }


def evidence_strength(references: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Lo que el registro único dice de las fichas citadas: su grado y lo que falta verificar."""
    items = [
        {
            "id": ref["id"],
            "title": ref["title"],
            "grade": ref["grade"]["label"],
            "tier": ref["grade"]["tier"],
            "preclinical": bool(ref["grade"]["preclinical"]),
            "unverified": list(ref["unverified"]),
            "unverified_display": list(ref["unverified_display"]),
        }
        for ref in references
    ]
    grades: dict[str, int] = {}
    for item in items:
        grades[item["grade"]] = grades.get(item["grade"], 0) + 1
    return {
        "references": items,
        "count": len(items),
        "by_grade": [{"grade": label, "count": count} for label, count in grades.items()],
        "preclinical": sum(1 for item in items if item["preclinical"]),
        "unverified_fields": sum(len(item["unverified"]) for item in items),
    }


def countermeasure_basis(domain: Domain) -> dict[str, Any]:
    """Cuántas contramedidas del dominio tienen protocolo detrás y cuántas son `demo`."""
    found = for_domain(domain)
    return {
        "count": len(found),
        "by_basis": [
            {"basis": basis, "count": sum(1 for item in found if item.basis == basis)}
            for basis in BASES
        ],
        "demo": sum(1 for item in found if item.basis == "demo"),
        "note": DEMO_NOTE,
    }


# --------------------------------------------------------------------------- #
# La matriz: efecto, dato, detección y contramedidas de cada riesgo
# --------------------------------------------------------------------------- #


def _plain(value: float) -> str:
    """Una cifra con los decimales que tiene: «2», «0,5», «1,35»."""
    for decimals in range(4):
        if round(value, decimals) == value:
            return display.number(value, decimals)
    return display.number(value, 3)


def _share(fraction: float) -> str:
    """Una fracción como porcentaje, con los decimales que tiene: «30 %», «99,5 %»."""
    return f"{_plain(round(fraction * 100, 3))} %"


def _span(delta: dt.timedelta) -> str:
    """Una ventana en días si son días enteros; si no, en horas."""
    hours = delta.total_seconds() / 3600
    if hours > 0 and hours % 24 == 0:
        days = hours / 24
        unit = i18n.tr("día" if days == 1 else "días", "day" if days == 1 else "days")
        return f"{_plain(days)} {unit}"
    return f"{_plain(hours)} h"


def _ref_fields(ref: registry.EvidenceRef) -> dict[str, Any]:
    """Lo que la matriz enseña de una ficha: qué es, de qué clase y sobre quién se midió."""
    full = ref.to_dict()
    return {
        name: full[name]
        for name in (
            "id", "title", "url", "evidence_type", "evidence_type_display", "population",
            "population_display", "not_applicable", "outside_enum",
        )
    }


def effect(domain: Domain) -> dict[str, Any]:
    """El efecto biológico: la relevancia con que se cita el riesgo del dominio, tal cual."""
    hrp = HRP_RISKS.get(domain)
    if hrp is None or not hrp.relevance:
        return {"source": None, "statement": NO_EFFECT, "basis": EFFECT_BASIS}
    return {"source": _ref_fields(hrp.ref), "statement": hrp.relevance, "basis": EFFECT_BASIS}


def data_sources(cited: Iterable[EvidenceItem]) -> dict[str, Any]:
    """La evidencia citada, partida en conjuntos de datos y documentos por su clase en el registro.

    Una ficha sin clase (`evidence_type` nulo) no se da por conjunto de datos: va con los
    documentos, y su clase sale «sin clasificar», que es lo que dice el registro.
    """
    datasets: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    for item in cited:
        row = {**_ref_fields(item.ref), "relevance": item.relevance}
        (datasets if item.ref.evidence_type == DATASET_TYPE else documents).append(row)
    return {
        "datasets": datasets,
        "documents": documents,
        "datasets_empty": None if datasets else NO_DATASETS,
        "documents_empty": None if documents else NO_DOCUMENTS,
        "basis": DATA_BASIS,
    }


def countermeasure_list(domain: Domain) -> dict[str, Any]:
    """Las contramedidas del dominio, una a una, en el orden de la biblioteca.

    Incluye la de refugio, que el recuento de `countermeasure_basis` deja fuera porque no la
    ofrece el nivel del dominio: aquí se dice que va por evento. `family` se enseña si la
    biblioteca la declara; si no, queda en `None` y nadie la deduce.
    """
    items: list[dict[str, Any]] = []
    for entry in library().values():
        if entry.domain is not domain:
            continue
        declared = entry.to_dict()
        on_event = entry.id == SHELTER_ID
        items.append({
            "id": entry.id,
            "action": entry.action,
            "basis": entry.basis,
            "basis_display": BASIS_DISPLAY[entry.basis],
            "family": declared.get("family"),
            "family_display": declared.get("family_display"),
            "on_event": on_event,
            "trigger_display": ON_EVENT if on_event else None,
        })
    return {
        "items": items,
        "empty": None if items else NO_COUNTERMEASURES,
        "basis": COUNTERMEASURES_BASIS,
    }


def _mmash_key(code: VitalCode) -> dict[str, Any]:
    source = mmash.LOADED[code.key]
    return {
        "key": code.key,
        "display_es": code.display_es,
        "domain": str(code.domain),
        "source": source,
        "source_display": mmash.SOURCE_DISPLAY[source],
    }


def mmash_keys() -> list[dict[str, Any]]:
    """Las claves que emite el cargador de MMASH, en el orden de su tabla, con su dominio.

    Una clave que el cargador emitiera y el catálogo no tuviera rompería aquí (`CATALOG[key]`):
    la prueba del cargador lo dice antes, pero no se publica a medias.
    """
    return [_mmash_key(CATALOG[key]) for key in mmash.LOADED_KEYS]


def validation(domain: Domain) -> dict[str, Any]:
    """Qué indicadores del dominio salen de MMASH y qué valida eso: el motor de medida y la
    falsa alarma en Tierra, no la fisiología espacial. El dominio sin ninguno lo dice."""
    codes = evaluated_by_domain(domain)
    found = [_mmash_key(code) for code in codes if code.key in mmash.LOADED]
    if found:
        names = ", ".join(item["display_es"] for item in found)
        statement = i18n.tr(
            f"{_plain(len(found))} de {_plain(len(codes))} "
            f"{'indicador' if len(codes) == 1 else 'indicadores'} "
            f"{'sale' if len(found) == 1 else 'salen'} de MMASH "
            f"({names}): {mmash.VALIDATES}.",
            f"{_plain(len(found))} of {_plain(len(codes))} "
            f"{'indicator' if len(codes) == 1 else 'indicators'} "
            f"{'comes' if len(found) == 1 else 'come'} from MMASH "
            f"({names}): {i18n.loc(mmash.VALIDATES)}.",
        )
    else:
        statement = NO_MMASH
    return {
        "dataset_id": VALIDATION_DATASET.id,
        "keys": found,
        "indicators": len(codes),
        "statement": statement,
        "validates": mmash.VALIDATES if found else None,
        # Hasta dónde llega lo medido: sin claves no hay nada que acotar.
        "note": mmash.VALIDATES_NOTE if found else None,
        "empty": None if found else NO_MMASH,
        "basis": MMASH_BASIS,
    }


def injections_for(key: str) -> list[dict[str, str]]:
    """Los deterioros de referencia que el inyector aplica a un indicador, en su orden."""
    return [
        {
            "label": label,
            "kind": str(kind),
            "kind_display": injection.PERTURBATION_DISPLAY[kind],
        }
        for label, (target, kind) in injection.REFERENCE_TARGETS.items()
        if target == key
    ]


def sensitivity(domain: Domain) -> dict[str, Any]:
    """Sobre qué indicadores del dominio se ha medido la sensibilidad, y con qué deterioro.

    Lee la tabla del inyector (`REFERENCE_TARGETS`, construida al importarlo llamando a cada
    deterioro de referencia) en cada consulta. Sin cifras: la frase remite a la validación
    externa, que es su fuente de verdad. El dominio sin ninguno lo dice.
    """
    codes = evaluated_by_domain(domain)
    # Un indicador cuenta si el inyector le aplica algún deterioro: una sola tabla decide si está
    # y con qué, para que la marca y la lista no puedan contar cosas distintas.
    found: list[dict[str, Any]] = [
        {"key": code.key, "display_es": code.display_es, "injections": injected}
        for code in codes
        if (injected := injections_for(code.key))
    ]
    if found:
        named = "; ".join(
            f"{item['display_es']}: "
            + ", ".join(i18n.loc(entry["label"]) for entry in item["injections"])
            for item in found
        )
        statement = i18n.tr(
            f"Sensibilidad medida en {_plain(len(found))} de {_plain(len(codes))} "
            f"{'indicador' if len(codes) == 1 else 'indicadores'}, inyectando deterioros sobre "
            f"la fisiología de MMASH. {named}. Cifras en {SENSITIVITY_REFERENCE}.",
            f"Sensitivity measured on {_plain(len(found))} of {_plain(len(codes))} "
            f"{'indicator' if len(codes) == 1 else 'indicators'}, by injecting deteriorations "
            f"into MMASH physiology. {named}. Figures in {SENSITIVITY_REFERENCE}.",
        )
    else:
        statement = NO_SENSITIVITY
    return {
        "keys": found,
        "indicators": len(codes),
        "statement": statement,
        "measures": injection.MEASURES if found else None,
        "reference": SENSITIVITY_REFERENCE,
        "empty": None if found else NO_SENSITIVITY,
        "basis": SENSITIVITY_BASIS,
    }


def equipment(domain: Domain, equipment_by_key: Mapping[str, str | None]) -> dict[str, Any]:
    """El equipo de cada variable del dominio, agrupado: cada equipo con sus indicadores, en el
    orden en que aparece el primero de ellos en el catálogo."""
    groups: dict[str, list[dict[str, str]]] = {}
    for code in evaluated_by_domain(domain):
        word = equipment_by_key.get(code.key) or NO_EQUIPMENT
        groups.setdefault(word, []).append({"key": code.key, "display_es": code.display_es})
    return {
        "groups": [{"equipment": word, "indicators": items} for word, items in groups.items()],
        "basis": EQUIPMENT_BASIS,
    }


def burst_steps(limit: int = BURST_TABLE_READINGS) -> list[dict[str, int]]:
    """Desde cuántas lecturas en la ventana pide el motor cada número de lecturas graves.

    Es `risk.min_severe_readings` recorrida de una en una: con menos lecturas que las pedidas
    no hay ráfaga posible y ese tramo no se enseña. Se llama a la función sin su caché
    (`__wrapped__`): mil entradas que solo sirven para enseñar la escalera desplazarían las que
    usa la ruta de estado.
    """
    count = risk.min_severe_readings.__wrapped__
    steps: list[dict[str, int]] = []
    for readings in range(1, limit + 1):
        needed = count(readings)
        if needed <= readings and (not steps or needed != steps[-1]["severe"]):
            steps.append({"from_readings": readings, "severe": needed})
    return steps


def _probe_comms(round_trip_minutes: float) -> CommsWindow:
    return CommsWindow(
        epoch=_PROBE_TIME.date(), distance_au=0.0,
        one_way_minutes=round_trip_minutes / 2, target=_PROBE_SUBJECT,
    )


def isolation_curve() -> dict[str, float]:
    """Desde qué retardo multiplica el motor, hasta cuánto y con qué retardo llega al tope.

    Se lee de `risk.isolation_factor`: el retardo de saturación está escrito dentro de la función
    y no en una constante, así que preguntarle es la única forma de no copiarlo. Se busca por
    bisección (el factor no baja al crecer el retardo), y se dice también cuánto vale justo al
    pasar el umbral de autonomía: no arranca en 1, salta.
    """
    def factor(minutes: float) -> float:
        return risk.isolation_factor(_probe_comms(minutes))

    top = factor(_PROBE_FAR_MINUTES)
    low, high = float(AUTONOMY_THRESHOLD_MINUTES), float(_PROBE_FAR_MINUTES)
    for _ in range(_PROBE_BISECTIONS):
        middle = (low + high) / 2
        if factor(middle) >= top:
            high = middle
        else:
            low = middle
    return {
        "autonomy_above_minutes": AUTONOMY_THRESHOLD_MINUTES,
        "factor_above_threshold": factor(AUTONOMY_THRESHOLD_MINUTES + _PROBE_STEP_MINUTES),
        "max_factor": top,
        "saturates_at_minutes": round(high, 2),
    }


def _probe_deviations(code: VitalCode) -> list[Deviation]:
    """Una ráfaga de lecturas graves de un indicador: lo mínimo para que el motor puntúe."""
    return [
        Deviation(
            subject=_PROBE_SUBJECT, key=code.key, value=0.0,
            effective=_PROBE_TIME + dt.timedelta(minutes=index), z_score=10.0,
            severity=Severity.SEVERE, direction="high", baseline=None,
            used_population_range=True,
        )
        for index in range(_PROBE_READINGS)
    ]


def isolation_applies(domain: Domain) -> bool | None:
    """Si el motor multiplica la puntuación de este dominio por el aislamiento.

    Se le pregunta: la misma ráfaga con y sin un retardo enorme. `None` si el dominio no tiene
    indicadores con que preguntarlo.
    """
    codes = evaluated_by_domain(domain)
    if not codes:
        return None
    engine = RiskEngine()
    burst = _probe_deviations(codes[0])
    near = engine.assess(_PROBE_SUBJECT, burst).domains[domain].score
    far = engine.assess(
        _PROBE_SUBJECT, burst, comms=_probe_comms(_PROBE_FAR_MINUTES)
    ).domains[domain].score
    return far > near


def _probe_event(severity: SolarSeverity) -> SolarEvent:
    return SolarEvent(
        event_id=_PROBE_SUBJECT, event_type=EventType.SEP, time=_PROBE_TIME,
        severity=severity, instruments=(), linked_event_ids=(), flare_class=None, link="",
    )


def environment_findings() -> dict[Domain, list[dict[str, Any]]]:
    """Lo que suman al riesgo el evento solar activo y la dosis acumulada, y en qué dominio.

    Se le pregunta al motor sin ninguna lectura: cada severidad de evento por separado, y la
    dosis en la mitad y en el total del límite de carrera. Lo que no suma nada no se enseña.
    """
    engine = RiskEngine()
    found: dict[Domain, list[dict[str, Any]]] = {}
    solar: dict[Domain, list[dict[str, Any]]] = {}
    for severity in SolarSeverity:
        status = engine.assess(_PROBE_SUBJECT, [], solar_events=[_probe_event(severity)])
        for domain, item in status.domains.items():
            if item.score > 0:
                solar.setdefault(domain, []).append({
                    "severity": str(severity),
                    "display": SOLAR_SEVERITY_DISPLAY[severity],
                    "points": item.score,
                })
    for domain, rows in solar.items():
        words = ", ".join(
            f"{i18n.loc(row['display'])} {_plain(row['points'])}" for row in rows
        )
        found.setdefault(domain, []).append({
            "key": "solar_event",
            "values": rows,
            "statement": i18n.tr(
                f"Evento solar activo, puntos por severidad: {words}.",
                f"Active solar event, points by severity: {words}.",
            ),
            "summary": i18n.tr(
                f"evento solar activo ({words} puntos)",
                f"active solar event ({words} points)",
            ),
        })
    half = engine.assess(_PROBE_SUBJECT, [], cumulative_dose_msv=engine.dose_limit_msv / 2)
    full = engine.assess(_PROBE_SUBJECT, [], cumulative_dose_msv=engine.dose_limit_msv)
    for domain, item in full.domains.items():
        if item.score <= 0:
            continue
        at_half = half.domains[domain].score
        found.setdefault(domain, []).append({
            "key": "cumulative_dose",
            "values": {"points_at_half": at_half, "points_at_limit": item.score},
            "statement": i18n.tr(
                f"Dosis acumulada: {_plain(item.score)} puntos al llegar al 100 % del límite "
                f"de carrera, {_plain(at_half)} al 50 %.",
                f"Cumulative dose: {_plain(item.score)} points on reaching 100 % of the career "
                f"limit, {_plain(at_half)} at 50 %.",
            ),
            "summary": i18n.tr(
                f"dosis acumulada ({_plain(item.score)} puntos al 100 % del límite de carrera)",
                f"cumulative dose ({_plain(item.score)} points at 100 % of the career limit)",
            ),
        })
    return found


def _bounds_text(code: VitalCode, bounds: tuple[float | None, float | None]) -> str:
    low, high = bounds
    parts = []
    if low is not None:
        below = display.quantity(code.key, low, code.unit)
        parts.append(i18n.tr(f"por debajo de {below}", f"below {below}"))
    if high is not None:
        above = display.quantity(code.key, high, code.unit)
        parts.append(i18n.tr(f"por encima de {above}", f"above {above}"))
    return i18n.tr(" o ", " or ").join(parts) if parts else i18n.tr("sin límite", "no limit")


def danger_limits(domain: Domain) -> list[dict[str, Any]]:
    """Los límites de peligro absoluto de los indicadores del dominio, por estado.

    Salen de `VitalCode.critical_bounds`, la misma función con que `analysis/baseline.py` decide
    si una lectura cruza uno: en reposo o sueño, en esfuerzo y en cualquier otro estado.
    """
    rows: list[dict[str, Any]] = []
    for code in evaluated_by_domain(domain):
        general = code.critical_bounds(False, False)
        resting = code.critical_bounds(True)
        exertion = code.critical_bounds(False, True)
        if all(value is None for value in (*general, *resting, *exertion)):
            continue
        pieces = [_bounds_text(code, general)]
        if resting != general or exertion != general:
            pieces = []
            if resting != general:
                pieces.append(f"{i18n.loc(RESTING_STATES)}, {_bounds_text(code, resting)}")
            if exertion != general:
                pieces.append(f"{i18n.loc(EXERTION_STATE)}, {_bounds_text(code, exertion)}")
            pieces.append(f"{i18n.loc(OTHER_STATE)}, {_bounds_text(code, general)}")
        rows.append({
            "key": code.key,
            "display_es": code.display_es,
            "general": list(general),
            "resting": list(resting),
            "exertion": list(exertion),
            "statement": f"{code.display_es}: " + "; ".join(pieces) + ".",
        })
    return rows


def detection(
    domain: Domain,
    environment: Mapping[Domain, Sequence[Mapping[str, Any]]] | None = None,
    curve: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Con qué regla detecta el motor un problema en este dominio, leída de él.

    La parte común (base, cuantiles, persistencia, tendencia, puntos) va una vez en
    `detection_rule`; aquí, lo que cambia de un dominio a otro: cuántos indicadores, sus límites
    de peligro, si se aplica el aislamiento y qué suma el entorno. `environment` y `curve` no
    dependen del dominio: `payload` los calcula una vez y los pasa.
    """
    codes = evaluated_by_domain(domain)
    limits = danger_limits(domain)
    applies = isolation_applies(domain)
    curve = isolation_curve() if curve is None else curve
    found = list((environment_findings() if environment is None else environment).get(domain, ()))
    if applies is None:
        isolation_text = NO_ISOLATION_PROBE
    elif applies:
        isolation_text = i18n.tr(
            f"Sin consulta en vivo (ida y vuelta de más de "
            f"{_plain(curve['autonomy_above_minutes'])} min), la puntuación se multiplica por un "
            f"factor que depende del retardo: "
            f"{display.number(curve['factor_above_threshold'], 2)} nada más pasar ese umbral, "
            f"hasta {_plain(round(curve['max_factor'], 3))} a partir de "
            f"{_plain(round(curve['saturates_at_minutes'], 1))} min.",
            f"Without live consultation (round trip of more than "
            f"{_plain(curve['autonomy_above_minutes'])} min), the score is multiplied by a "
            f"factor that depends on the delay: "
            f"{display.number(curve['factor_above_threshold'], 2)} just past that threshold, "
            f"up to {_plain(round(curve['max_factor'], 3))} from "
            f"{_plain(round(curve['saturates_at_minutes'], 1))} min onward.",
        )
    else:
        isolation_text = NO_ISOLATION
    if codes:
        lead = i18n.tr(
            f"Desviación persistente, ráfaga de lecturas graves o deriva sostenida en "
            f"{_plain(len(codes))} {'indicador' if len(codes) == 1 else 'indicadores'}",
            f"Persistent deviation, burst of severe readings or sustained drift in "
            f"{_plain(len(codes))} {'indicator' if len(codes) == 1 else 'indicators'}",
        )
        if limits:
            lead += i18n.tr(
                f", {_plain(len(limits))} con límite de peligro absoluto",
                f", {_plain(len(limits))} with an absolute danger limit",
            )
    else:
        lead = i18n.loc(NO_INDICATORS_DETECTION)
    parts = [lead]
    if applies is True:
        parts.append(i18n.tr(
            f"con autonomía obligada, factor de hasta {_plain(round(curve['max_factor'], 3))}",
            f"with forced autonomy, factor of up to {_plain(round(curve['max_factor'], 3))}",
        ))
    elif applies is False:
        parts.append(i18n.tr("sin factor de aislamiento", "no isolation factor"))
    parts.extend(str(item["summary"]) for item in found)
    return {
        "indicators": len(codes),
        "danger_limits": limits,
        "isolation_applies": applies,
        "isolation_statement": isolation_text,
        "environment": found,
        "summary": "; ".join(parts) + ".",
        "basis": DETECTION_BASIS,
    }


def detection_rule(
    current_window: dt.timedelta,
    schema: Mapping[str, Any],
    curve: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """La regla común con que el motor convierte lecturas en nivel, con las cifras que usa.

    `current_window` es la ventana de «lo actual» de la ruta de estado (`api/routes.py`): se
    recibe de quien la tiene, no se escribe aquí.
    """
    window = baseline.DEFAULT_ROLLING_WINDOW
    lag = baseline.DEFAULT_ROLLING_LAG
    graded = sorted(baseline.cut_rules(), key=lambda rule: rule.fraction)  # de leve a grave
    quantiles = [
        {
            "severity": str(rule.severity),
            "display": FINDING_SEVERITY_DISPLAY[rule.severity],
            "quantile": rule.fraction,
            "min_samples": rule.min_samples,
        }
        for rule in graded
    ]
    # El corte es el cuantil `fraction` si lo que preocupa es subir y `1 - fraction` si es bajar
    # (`baseline._severity_from_quantiles`): por eso se dice como la cola que queda fuera.
    quantile_text = ", ".join(
        i18n.tr(
            f"{FINDING_SEVERITY_DISPLAY[rule.severity]} si cae en el "
            f"{_share(1.0 - rule.fraction)} más extremo de su base por ese lado (con "
            f"{_plain(rule.min_samples)} lecturas de base o más)",
            f"{i18n.loc(FINDING_SEVERITY_DISPLAY[rule.severity])} if it falls in the most "
            f"extreme {_share(1.0 - rule.fraction)} of its baseline on that side (with "
            f"{_plain(rule.min_samples)} baseline readings or more)",
        )
        for rule in graded
    )
    steps = burst_steps()
    ladder = ", ".join(
        i18n.tr(
            f"{_plain(step['severe'])} desde {_plain(step['from_readings'])}",
            f"{_plain(step['severe'])} from {_plain(step['from_readings'])}",
        )
        for step in steps
    )
    points = {
        FINDING_SEVERITY_DISPLAY[severity]: value
        for severity, value in risk._SEVERITY_POINTS.items()
        if severity in FINDING_SEVERITY_DISPLAY
    }
    points_text = ", ".join(
        f"{i18n.loc(word)} {_plain(value)}" for word, value in points.items()
    )
    floors = [item for item in schema["levels"] if item["min_score"] is not None]
    levels_text = ", ".join(
        i18n.tr(
            f"{item['display']} desde {_plain(item['min_score'])}",
            f"{i18n.loc(item['display'])} from {_plain(item['min_score'])}",
        )
        for item in floors
    )
    rule = [
        {
            "key": "baseline",
            "display": i18n.tr("Línea base personal", "Personal baseline"),
            "statement": i18n.tr(
                f"Cada lectura se compara con las del propio tripulante en los {_span(window)} "
                f"anteriores, en el mismo estado fisiológico y con {_span(lag)} de hueco; la "
                f"base cuenta desde {_plain(baseline.MIN_SAMPLES)} lecturas. Sin base, solo "
                f"avisa un límite de peligro absoluto.",
                f"Each reading is compared with the crew member's own readings over the "
                f"preceding {_span(window)}, in the same physiological state and with a gap of "
                f"{_span(lag)}; the baseline counts from {_plain(baseline.MIN_SAMPLES)} "
                f"readings. Without a baseline, only an absolute danger limit raises a notice.",
            ),
            "values": {
                "window_hours": window.total_seconds() / 3600,
                "lag_hours": lag.total_seconds() / 3600,
                "min_samples": baseline.MIN_SAMPLES,
            },
        },
        {
            "key": "deviation",
            "display": i18n.tr("Lectura fuera de lo esperado", "Reading outside what is expected"),
            "statement": i18n.tr(
                f"En la dirección que preocupa del indicador: {quantile_text}. Cruzar un límite "
                f"de peligro del catálogo es grave con o sin base; una lectura de confianza "
                f"menor que {_plain(LOW_CONFIDENCE_THRESHOLD)} no pasa de leve.",
                f"In the indicator's direction of concern: {quantile_text}. Crossing a catalog "
                f"danger limit is severe with or without a baseline; a reading with confidence "
                f"below {_plain(LOW_CONFIDENCE_THRESHOLD)} does not go beyond mild.",
            ),
            "values": {"quantiles": quantiles, "low_confidence_below": LOW_CONFIDENCE_THRESHOLD},
        },
        {
            "key": "persistence",
            "display": i18n.tr("Persistencia", "Persistence"),
            "statement": i18n.tr(
                f"Un indicador cuenta como hallazgo si se desvía al menos el "
                f"{_share(risk._PERSISTENCE_FRACTION)} de sus lecturas de los últimos "
                f"{_span(current_window)}, o si reúne una ráfaga de lecturas graves: {ladder} "
                f"lecturas en la ventana, y más con más lecturas. Por persistencia, su gravedad "
                f"es la de la lectura que solo supera el "
                f"{_share(1.0 - risk._FINDING_PERCENTILE)} más extremo de la ventana, no la más "
                f"llamativa; por ráfaga, la de la lectura grave más alejada de su base.",
                f"An indicator counts as a finding if at least "
                f"{_share(risk._PERSISTENCE_FRACTION)} of its readings over the last "
                f"{_span(current_window)} deviate, or if it gathers a burst of severe readings: "
                f"{ladder} readings in the window, and more with more readings. By persistence, "
                f"its severity is that of the reading that exceeds only the most extreme "
                f"{_share(1.0 - risk._FINDING_PERCENTILE)} of the window, not the most striking "
                f"one; by burst, that of the severe reading farthest from its baseline.",
            ),
            "values": {
                "fraction": risk._PERSISTENCE_FRACTION,
                "current_window_hours": current_window.total_seconds() / 3600,
                "burst": steps,
                "representative_percentile": risk._FINDING_PERCENTILE,
            },
        },
        {
            "key": "trend",
            "display": i18n.tr("Deriva sostenida", "Sustained drift"),
            "statement": i18n.tr(
                f"Recta sobre las lecturas de los últimos {_span(trend.TREND_WINDOW)}, con al "
                f"menos {_plain(trend.MIN_POINTS)} que abarquen {_plain(trend.MIN_SPAN_DAYS)} "
                f"días; cuenta si la pendiente supera con |t| de {_plain(trend.T_SIGNIFICANCE)} "
                f"o más la deriva relevante, el {_share(trend.RELEVANCE_FRACTION_OF_RANGE)} del "
                f"rango de referencia en {_plain(trend.RELEVANCE_HORIZON_WEEKS)} semanas (el "
                f"{_share(trend.RELEVANCE_FRACTION_OF_LEVEL)} del nivel si no hay rango), en la "
                f"dirección que preocupa.",
                f"Line fitted to the readings of the last {_span(trend.TREND_WINDOW)}, with at "
                f"least {_plain(trend.MIN_POINTS)} spanning {_plain(trend.MIN_SPAN_DAYS)} days; "
                f"it counts if the slope exceeds, with |t| of {_plain(trend.T_SIGNIFICANCE)} or "
                f"more, the relevant drift, {_share(trend.RELEVANCE_FRACTION_OF_RANGE)} of the "
                f"reference range in {_plain(trend.RELEVANCE_HORIZON_WEEKS)} weeks "
                f"({_share(trend.RELEVANCE_FRACTION_OF_LEVEL)} of the level if there is no "
                f"range), in the direction of concern.",
            ),
            "values": {
                "window_hours": trend.TREND_WINDOW.total_seconds() / 3600,
                "min_points": trend.MIN_POINTS,
                "min_span_days": trend.MIN_SPAN_DAYS,
                "t_significance": trend.T_SIGNIFICANCE,
                "relevance_fraction_of_range": trend.RELEVANCE_FRACTION_OF_RANGE,
                "relevance_fraction_of_level": trend.RELEVANCE_FRACTION_OF_LEVEL,
                "relevance_horizon_weeks": trend.RELEVANCE_HORIZON_WEEKS,
            },
        },
        {
            "key": "points",
            "display": i18n.tr("Puntuación del dominio", "Domain score"),
            "statement": i18n.tr(
                f"Cada hallazgo suma puntos ({points_text}; una deriva, "
                f"{_plain(risk._TREND_POINTS)}): el mayor entero y cada uno de los siguientes "
                f"al {_share(risk._ADDITIONAL_FINDING_DECAY)} del anterior.",
                f"Each finding adds points ({points_text}; a drift, "
                f"{_plain(risk._TREND_POINTS)}): the largest in full and each of the following "
                f"at {_share(risk._ADDITIONAL_FINDING_DECAY)} of the previous one.",
            ),
            "values": {
                "severity_points": [
                    {"severity": str(severity), "points": value}
                    for severity, value in risk._SEVERITY_POINTS.items()
                    if severity in FINDING_SEVERITY_DISPLAY
                ],
                "trend_points": risk._TREND_POINTS,
                "additional_finding_decay": risk._ADDITIONAL_FINDING_DECAY,
            },
        },
        {
            "key": "levels",
            "display": i18n.tr("Nivel", "Level"),
            "statement": i18n.tr(f"Por puntos: {levels_text}.", f"By points: {levels_text}."),
            "values": {"levels": [
                {"level": item["level"], "min_score": item["min_score"]} for item in floors
            ]},
        },
    ]
    return {
        "display": DETECTION_RULE_DISPLAY,
        "steps": rule,
        "isolation": dict(isolation_curve() if curve is None else curve),
        "validated_with": {
            "display": VALIDATED_WITH_DISPLAY,
            "dataset": _ref_fields(VALIDATION_DATASET),
            "scope": VALIDATION_DATASET.scope_in_view,
            "statement": VALIDATION_STATEMENT,
            # Las claves que salen de MMASH, del cargador; cada riesgo dice las suyas.
            "keys": mmash_keys(),
            "validates": mmash.VALIDATES,
            "note": mmash.VALIDATES_NOTE,
            "keys_basis": MMASH_BASIS,
        },
        "basis": DETECTION_BASIS,
        "rules_version": rules_version(),
    }


def ridge(domain: Domain) -> dict[str, Any]:
    """La categoría RIDGE del dominio, con la ficha de la que sale."""
    source = registry.get(RIDGE_SOURCE)
    return {
        "category": str(domain.ridge),
        "display": domain.ridge.display,
        "source": {"id": source.id, "title": source.title, "url": source.url},
    }


def summary(domain: Domain) -> dict[str, Any]:
    """El paso RIESGO de la cadena anatómica (KB §11.1): qué riesgo es, de qué peligro RIDGE
    procede y qué ficha le corresponde (la de `hrp_risk_id` en `entity`, aquí con su título y su
    clase y no solo el id). Es un subconjunto de `entity`, leído de las mismas funciones y de las
    mismas fichas: el modo anatómico no compone un riesgo propio, y la incertidumbre va solo con
    su frase (el desglose está en `/risks`).

    La ficha no es siempre un riesgo del HRP (la del dolor de espalda es un artículo): va con la
    clase de documento que declara el registro, para que nadie la rotule de lo que no es.
    """
    hrp = HRP_RISKS.get(domain)
    return _served({
        "risk_id": str(domain),
        "display": domain.display,
        "ridge": ridge(domain),
        "hrp_risk": (
            {
                "id": hrp.id, "title": hrp.title, "url": hrp.url,
                "evidence_type_display": hrp.to_dict()["evidence_type_display"],
            }
            if hrp is not None else None
        ),
        "uncertainty_statement": NOT_QUANTIFIED,
    })


def entity(
    domain: Domain,
    modes: Mapping[str, str],
    schema: Mapping[str, Any],
    environment: Mapping[Domain, Sequence[Mapping[str, Any]]] | None = None,
    curve: Mapping[str, float] | None = None,
    equipment_by_key: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Un riesgo entero, con los seis campos de la especificación y de dónde sale cada uno.

    Y su fila de la matriz: `effect`, `data_sources`, `detection` y `countermeasures`; el
    peligro y las variables ya estaban (`ridge`, `indicators`). Desde la decimoquinta ronda,
    `equipment` (el equipo de cada variable) y `validation` (qué sale de MMASH); desde la
    decimosexta, `sensitivity` (sobre qué indicadores se inyecta un deterioro).
    """
    if equipment_by_key is None:
        equipment_by_key = _equipment_by_key()
    cited_items = evidence_for(domain)
    cited = [item.to_dict() for item in cited_items]
    hrp = HRP_RISKS.get(domain)
    return {
        "risk_id": str(domain),
        "display": domain.display,
        "ridge": ridge(domain),
        # Las regiones de las que habla el dominio, también las que no tienen nivel propio y
        # cuentan en el suyo (el hígado en nutrición, decimosexta ronda, §5.36.19): se lee de
        # `anatomy.Region.engine_domains`, no de una lista escrita aquí.
        "human_system": {
            "regions": [
                region.to_dict() for region in anatomy.REGIONS if domain in region.engine_domains
            ],
            "basis": HUMAN_SYSTEM_BASIS,
        },
        # La ficha del riesgo del HRP que corresponde al dominio, y todo lo que se cita con él.
        "hrp_risk_id": hrp.id if hrp is not None else None,
        "evidence_refs": cited,
        # Qué parte de la condición vigila EMMA y cuál no (marco de ExMC).
        "amcl_alignment": amcl_alignment(domain),
        "severity_schema": schema,
        "indicators": [
            {
                "key": code.key,
                "display": code.display,
                "display_es": code.display_es,
                "unit": code.unit,
                "is_standard_code": code.is_standard,
                "mode": modes.get(code.key),
                "mode_display": MODES[modes[code.key]] if code.key in modes else None,
                "equipment": equipment_by_key.get(code.key),
                "from_mmash": code.key in mmash.LOADED,
                # Si la sensibilidad se ha medido inyectándole un deterioro, y con cuál.
                "sensitivity_measured": bool(injected),
                "sensitivity_injections": injected,
            }
            for code in evaluated_by_domain(domain)
            for injected in (injections_for(code.key),)
        ],
        # La fila de la matriz: lo que faltaba entre el peligro y las variables, y después.
        "effect": effect(domain),
        "data_sources": data_sources(cited_items),
        "detection": detection(domain, environment, curve),
        "countermeasures": countermeasure_list(domain),
        "equipment": equipment(domain, equipment_by_key),
        "validation": validation(domain),
        "sensitivity": sensitivity(domain),
        "uncertainty": {
            "quantified": False,
            "statement": NOT_QUANTIFIED,
            "evidence": evidence_strength(cited),
            "countermeasures": countermeasure_basis(domain),
            "evaluation": evaluation(domain, modes),
        },
    }


def _equipment_by_key() -> dict[str, str | None]:
    """El equipo de cada indicador en el coste de medir; `None` si la entrada no lo declara (o lo
    deja vacío): así el indicador y su grupo dicen lo mismo."""
    return {key: item.get("equipment") or None for key, item in costs().items()}


def payload(current_window: dt.timedelta) -> dict[str, Any]:
    """Todos los riesgos de EMMA: uno por dominio clínico, en el orden del catálogo.

    `current_window` es la ventana de «lo actual» con que la ruta de estado elige las lecturas
    que entran en el motor; la da quien la usa (`api/risks.py`, desde `api/routes.py`).
    """
    modes = {key: str(item["mode"]) for key, item in costs().items()}
    schema = severity_schema()
    environment = environment_findings()
    curve = isolation_curve()
    equipment_by_key = _equipment_by_key()
    risks = [
        entity(domain, modes, schema, environment, curve, equipment_by_key) for domain in Domain
    ]
    return _served({
        "count": len(risks),
        "risks": risks,
        "severity_schema": schema,
        "uncertainty_statement": NOT_QUANTIFIED,
        "chain": {
            "links": [{"key": key, "display": word} for key, word in CHAIN_LINKS],
            "basis": CHAIN_BASIS,
        },
        "detection_rule": detection_rule(current_window, schema, curve),
    })
