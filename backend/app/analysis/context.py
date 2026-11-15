"""Correlacion con el contexto compartido: el "Human FDIR" de la especificacion (§7).

Si varios tripulantes cambian a la vez y el habitat que comparten se ha salido de limite, lo
primero que hay que mirar es el habitat, no a cada persona por separado. Es la leccion del
control termico de la ISS que la conversacion de ideacion del equipo resume como "SENSE →
COMPARE → DETECT ANOMALY → ISOLATE → RESPOND → RECOVER" y la base de conocimiento (§6) como
"Human FDIR". La fuente leida (ficha `nasa-iss-atcs-overview` del registro de evidencia,
p. 17, el 2026-10-21) no usa esa cadena: dice "Fault Detection, Isolation, and Recovery (FDIR)
software is used to monitor the performance of the TCS and, if there is a problem, alert the
crew and flight controllers". Lo leido se sirve en `/api/framework` (bloque
`habitat-systems`). EMMA no reproduce ese FDIR: aqui se aplica al revés de lo habitual, y
antes de tratar tres anomalias individuales se pregunta si hay una causa comun.

LO QUE ES Y LO QUE NO ES
------------------------
Es una capa de **hipotesis**, no una prueba de causalidad, y lo dice en cada salida. Esta
por encima de `RiskEngine`, que evalua un sujeto cada vez y no debe mezclar sujetos: no toca
puntuaciones, umbrales ni alertas fisiologicas (invariante 5). Lo unico que decide es el orden
en que se proponen las causas candidatas.

La regla es deliberadamente simple y declarada:
- "Afectado" = tripulante con algun dominio fuera de nominal en su estado actual.
- "Excursion" = parametro de habitat fuera de su limite **normativo** (NASA-STD-3001) dentro de
  la misma ventana. No se inventa un umbral de "subida": sin limite cruzado, no hay excursion.
- Dos o mas afectados + excursion en la ventana → primera hipotesis: contexto ambiental
  compartido. Dos o mas sin excursion → causa comun no identificada. Uno solo → individual.
- Dos o mas afectados + un sistema de soporte vital declarado fuera de lo nominal en la ventana
  → hipotesis «coincidencia temporal, no causa», detras de las excursiones y delante de la
  causa sin identificar (base de conocimiento §6; ver `_system_hypothesis`).
- Radiacion registrada dentro de la ventana (una tasa de dosis que cruza su limite de peligro o
  un evento de particulas solares de NASA DONKI) y algun afectado → hipotesis «coincidencia
  temporal, no causa», con uno o con varios afectados (base de conocimiento §6 y §2.1; ver
  `_solar_hypothesis`).

UBICACION (especificacion §3, HabitatState "module/location" y MissionContext "location")
-----------------------------------------------------------------------------------------
La ubicacion la declara una persona, firmada, como un evento de mision, o la estiman las anclas
de modulo de la nave (`analysis/location.py`: equipo de la nave que EMMA solo escucha; la
granularidad es el modulo, nunca metros). Con una ubicacion que toque la ventana, una excursion
en un modulo donde un tripulante NO estaba deja de explicar su cambio; si quedan menos de dos a
los que si pudo alcanzar, la hipotesis pasa a "menos probable", va detras y dice por que. Es
solo orden y texto: los niveles entran y salen tal cual.

SUPUESTO DECLARADO: sin ubicacion declarada se supone que toda la tripulacion comparte el
habitat, y la salida lo dice; ese camino no cambia con lo anterior (tiene prueba de no
regresion). A quien no declara donde estaba en un tramo se le aplica el mismo supuesto: la
falta de dato nunca descarta una causa ambiental.

Si en un tramo hay a la vez una declaracion de la consola y una estimacion de las anclas, manda
la de la consola aunque sea anterior (`prevailing`): lo que dice una persona no lo corrige una
lectura de RSSI. Cada `Stay` lleva quien la puso (`source`) y los textos no presentan una
estimada como la declaracion de una persona. Un tramo en que las anclas no deciden entre dos
modulos no es un `Stay`: cuenta como sin ubicacion, que nunca exculpa al habitat.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from app.advisor import countermeasures
from app.analysis.baseline import crossed_danger_limit
from app.core import display, i18n
from app.environment import systems as habitat_systems
from app.environment.donki import SolarEvent
from app.environment.habitat import (
    MODULES,
    STANDARD_READ_ON,
    STANDARD_REF,
    Excursion,
    module_display,
    parameter,
)
from app.evidence import registry
from app.ingest.codes import get as indicator
from app.ingest.fhir import VitalObservation

LABEL = "correlación, no causa"
# La norma que fija los limites de cabina: su ficha en el registro unico de evidencia
# (`evidence/registry.py`). Se resuelve al importar: un identificador que no existe no arranca.
LIMITS_SOURCE = registry.get("ochmo-tb-002")
# La comparacion de un indicador entre tripulantes solo cuenta quien se aparta y desde cuando:
# ni siquiera llega a correlacion con una causa candidata, y se rotula como lo que es.
COINCIDENCE_LABEL = "coincidencia temporal, no causa"
# Esa comparacion enumera las excursiones de cabina de la ventana sin mirar donde estaba cada
# tripulante. Con alguna ubicacion declarada ya no vale decir que EMMA no la registra: se dice
# que aqui no se usa, para que nadie lea la lista como "todos estaban alli".
COMPARISON_IGNORES_LOCATION = (
    "Esta comparación no usa la ubicación declarada de cada tripulante: enumera las excursiones "
    "del hábitat de la ventana, estuviera o no cada uno en ese módulo."
)
ASSUMPTION = (
    "EMMA no registra en qué módulo está cada tripulante: se supone que toda la tripulación "
    "comparte el hábitat."
)
ASSUMPTION_LOCATED = (
    "La ubicación de cada tripulante la declara una persona; EMMA no la mide. A quien no la ha "
    "declarado en un tramo se le supone en el hábitat compartido."
)
# Lo mismo cuando alguna de las que mandan la estimaron las anclas de modulo: no la declaro nadie.
ASSUMPTION_ESTIMATED_LOCATED = (
    "La ubicación de cada tripulante la declara una persona o la estiman las anclas de módulo de "
    "la nave por la señal más fuerte (solo el módulo, sin validar dentro de un módulo metálico). "
    "A quien no la tiene en un tramo se le supone en el hábitat compartido."
)
UNIDENTIFIED_LOCATED = (
    "Cambio simultáneo en varios tripulantes sin causa ambiental común según la ubicación "
    "declarada"
)
CHECK_LOCATION = "Comprobar que la ubicación declarada de cada tripulante es correcta."
# Lo mismo cuando alguna de esas ubicaciones la estimaron las anclas de modulo.
UNIDENTIFIED_ESTIMATED_LOCATED = (
    "Cambio simultáneo en varios tripulantes sin causa ambiental común según la ubicación "
    "declarada o estimada por las anclas"
)
CHECK_ESTIMATED_LOCATION = (
    "Comprobar la ubicación de cada tripulante: alguna la estiman las anclas de módulo, no una "
    "persona."
)
NOT_COMPARABLE = (
    "El módulo de esta medida no está en la lista declarada: no se puede comparar con la "
    "ubicación de nadie y se mantiene el supuesto de hábitat compartido."
)
STEPS = (
    "Detectar", "Correlacionar con el contexto", "Causas candidatas", "Evidencia",
    "Comprobaciones", "Confirmación humana", "Seguimiento de la recuperación",
)
# Los mismos siete nombres en inglés, en su orden. Tabla paralela y no el registro común de
# `i18n`: son palabras sueltas («Evidencia», «Comprobaciones») que otra unidad puede nombrar.
STEPS_EN = (
    "Detect", "Correlate with the context", "Candidate causes", "Evidence",
    "Checks", "Human confirmation", "Recovery follow-up",
)
i18n.en_many({
    LABEL: "correlation, not cause",
    COINCIDENCE_LABEL: "coincidence in time, not cause",
    COMPARISON_IGNORES_LOCATION: (
        "This comparison does not use each crew member's declared location: it lists the "
        "habitat excursions in the window, whether or not each one was in that module."
    ),
    ASSUMPTION: (
        "EMMA does not record which module each crew member is in: the whole crew is assumed to "
        "share the habitat."
    ),
    ASSUMPTION_LOCATED: (
        "Each crew member's location is declared by a person; EMMA does not measure it. Anyone "
        "who has not declared it for a span is assumed to be in the shared habitat."
    ),
    ASSUMPTION_ESTIMATED_LOCATED: (
        "Each crew member's location is declared by a person or estimated by the ship's module "
        "anchors from the strongest signal (the module only, not checked inside a metal "
        "module). Anyone without one for a span is assumed to be in the shared habitat."
    ),
    UNIDENTIFIED_LOCATED: (
        "Simultaneous change in several crew members with no common environmental cause "
        "according to the declared location"
    ),
    CHECK_LOCATION: "Check that each crew member's declared location is correct.",
    UNIDENTIFIED_ESTIMATED_LOCATED: (
        "Simultaneous change in several crew members with no common environmental cause "
        "according to the location declared or estimated by the anchors"
    ),
    CHECK_ESTIMATED_LOCATION: (
        "Check each crew member's location: some are estimated by the module anchors, not by a "
        "person."
    ),
    NOT_COMPARABLE: (
        "The module of this measurement is not in the declared list: it cannot be compared with "
        "anyone's location and the shared-habitat assumption is kept."
    ),
})

# Lo que se sabe de cada parametro y que comprobar, con su fuente. Texto fijo del sistema: pasa
# por `text_guard` en las pruebas como toda salida a la tripulacion.
_KNOWLEDGE: dict[str, dict[str, Any]] = {
    "cabin-ppco2": {
        "what_is_known": (
            "En la ISS, cada mmHg más de CO2 se asoció con el doble de probabilidad de "
            "notificar cefalea (Law et al. 2014). El efecto sobre la cognición es contestado: "
            "un estudio controlado no halló relación clara entre concentración y efecto "
            "(Scully et al. 2019)."
        ),
        "checks": (
            "Contrastar la lectura de CO2 con un segundo sensor o una medida portátil.",
            "Revisar el estado del sistema de eliminación de CO2 y la ventilación del módulo.",
            "Registrar cefalea, sueño y fatiga de cada tripulante en el diario clínico.",
        ),
        # Citadas por identificador; para que sirven lo dice `what_is_known`.
        "evidence": (registry.cite("law-2014"), registry.cite("scully-2019")),
    },
}

_GENERIC_CHECKS = (
    "Contrastar la lectura con un segundo sensor.",
    "Revisar el sistema de control ambiental del módulo.",
)
# Lo que revisa cualquier hipótesis sin causa identificada (`_unidentified`) o individual.
_UNRECORDED_CHECK = "Revisar los parámetros del hábitat que no se registran en EMMA."
_SCHEDULE_CHECK = "Revisar si la agenda, la carga de trabajo o un evento común coinciden."
_INDIVIDUAL_CHECK = "Revisar el estado de ese tripulante en su consola."
_UNIDENTIFIED = "Cambio simultáneo en varios tripulantes sin causa ambiental registrada"
i18n.en_many({
    _KNOWLEDGE["cabin-ppco2"]["what_is_known"]: (
        "On the ISS, each additional mmHg of CO2 was associated with twice the probability of "
        "reporting headache (Law et al. 2014). The effect on cognition is contested: a "
        "controlled study found no clear relationship between concentration and effect "
        "(Scully et al. 2019)."
    ),
    _KNOWLEDGE["cabin-ppco2"]["checks"][0]: (
        "Cross-check the CO2 reading against a second sensor or a portable measurement."
    ),
    _KNOWLEDGE["cabin-ppco2"]["checks"][1]: (
        "Review the state of the CO2 removal system and the module's ventilation."
    ),
    _KNOWLEDGE["cabin-ppco2"]["checks"][2]: (
        "Record each crew member's headache, sleep and fatigue in the clinical diary."
    ),
    _GENERIC_CHECKS[0]: "Cross-check the reading against a second sensor.",
    _GENERIC_CHECKS[1]: "Review the module's environmental control system.",
    _UNRECORDED_CHECK: "Review the habitat parameters that are not recorded in EMMA.",
    _SCHEDULE_CHECK: "Review whether the schedule, the workload or a common event coincide.",
    _INDIVIDUAL_CHECK: "Review that crew member's state in their console.",
    _UNIDENTIFIED: (
        "Simultaneous change in several crew members with no environmental cause on record"
    ),
})


def _in_language(hypothesis: dict[str, Any]) -> None:
    """Pone en el idioma de la petición lo que una hipótesis lleva de texto fijo.

    Las hipótesis se construyen en castellano, con sus constantes (rótulo, título, lo que se
    sabe, comprobaciones, pasos, para qué se cita cada ficha), y aquí se resuelven una vez, al
    salir de `correlate`. Lo redactado con cifras ya viene en su idioma. En castellano no cambia
    nada: la salida de `correlate` es la de siempre.
    """
    if i18n.current() != "en":
        return
    for key in ("label", "title", "what_is_known"):
        if hypothesis.get(key) is not None:
            hypothesis[key] = i18n.loc(hypothesis[key])
    hypothesis["checks"] = [i18n.loc(item) for item in hypothesis["checks"]]
    hypothesis["steps"] = list(STEPS_EN)
    hypothesis["evidence"] = [
        {**item, "relevance": i18n.loc(item["relevance"])} if item.get("relevance") else item
        for item in hypothesis["evidence"]
    ]


def _hypothesis_for(excursion: Excursion, affected: Sequence[str]) -> dict[str, Any]:
    spec = parameter(excursion.parameter)
    known = _KNOWLEDGE.get(excursion.parameter, {})
    return {
        "kind": "shared_environment",
        "label": LABEL,
        "title": i18n.tr(
            f"Contexto ambiental compartido: {spec.display} fuera de límite",
            f"Shared environmental context: {i18n.loc(spec.display)} outside its limit",
        ),
        "affected": list(affected),
        "excursion": excursion.to_dict(),
        "what_is_known": known.get("what_is_known"),
        "checks": list(known.get("checks", _GENERIC_CHECKS)),
        # Las comprobaciones ambientales como contramedidas de la biblioteca (§8): con
        # recursos, tiempo, protocolo y cuando mirar si el parametro ha vuelto a su limite.
        "countermeasures": [
            item.to_dict() for item in countermeasures.for_habitat(excursion.parameter)
        ],
        "evidence": [
            *(item.to_dict() for item in known.get("evidence", ())),
            # El limite cruzado: la ficha es el resumen tecnico de la norma; el requisito
            # concreto es para lo que se cita aqui.
            registry.Citation(
                LIMITS_SOURCE, f"NASA-STD-3001 Vol 2 {excursion.requirement}"
            ).to_dict(),
        ],
        "steps": list(STEPS),
    }


@dataclass(frozen=True, slots=True)
class Stay:
    """Un tripulante en un modulo durante un intervalo, declarado o estimado por las anclas.

    `order` es el indice del asiento que lo dice (en una estimada, el del ultimo lote de lecturas
    que la sostiene). Si dos se solapan manda la que diga `prevailing`.
    """

    module: str
    start: dt.datetime
    end: dt.datetime
    order: int
    # Quien la puso: la consola (la declara una persona) o las anclas de modulo (la estiman por
    # la senal mas fuerte). Cambia como se dice y cual manda (`prevailing`), no la regla.
    source: str = "console"
    # Solo en una estimada: la ultima lectura de las anclas que la sostiene.
    last_seen: dt.datetime | None = None


# Los dos valores de `Stay.source`, y de `source` en la ubicacion que sirve la API.
CONSOLE_LOCATION = "console"
ANCHOR_LOCATION = "anchors"


def prevailing(covering: Sequence[Stay]) -> Stay:
    """De varias ubicaciones que cubren un tramo, la que manda. La UNICA regla, para todos.

    Manda la de la consola sobre la estimada por las anclas, aunque la de la consola sea anterior
    en el ledger: lo que declara una persona no lo corrige una lectura de RSSI (decision del
    usuario, 2026-11-10). Entre dos del mismo tipo, la de asiento posterior, que es como se
    corrige una ubicacion mal declarada en un registro de solo anadir.
    """
    return max(covering, key=lambda stay: (stay.source == CONSOLE_LOCATION, stay.order))


def estimated_location(stays: Sequence[Stay], start: dt.datetime, end: dt.datetime) -> bool:
    """True si alguna ubicacion que MANDA en un tramo de `[start, end]` la estimaron las anclas.

    Cuenta la que decide (`prevailing` en cada tramo, la misma regla que `_presence`), no
    cualquiera que se solape: una declaracion de la consola que tapa la estimada se dice como
    declarada. Basta un tramo decidido por las anclas: entonces el texto no puede decir que todo
    lo que ordena lo declaro una persona.
    """
    return any(stay.source == ANCHOR_LOCATION for stay in _deciding(stays, start, end))


def _deciding(stays: Sequence[Stay], start: dt.datetime, end: dt.datetime) -> list[Stay]:
    """La ubicacion que manda en cada tramo de `[start, end]` que tiene alguna."""
    cuts = sorted(
        {start, end, *(t for stay in stays for t in (stay.start, stay.end) if start < t < end)}
    )
    found: list[Stay] = []
    for low, high in list(pairwise(cuts)) or [(start, start)]:
        covering = [stay for stay in stays if stay.start <= low and stay.end >= high]
        if covering:
            found.append(prevailing(covering))
    return found


PRESENT, ELSEWHERE, UNDECLARED = "present", "elsewhere", "undeclared"


def _presence(
    stays: Sequence[Stay], module: str, start: dt.datetime, end: dt.datetime
) -> str:
    """Donde estaba alguien, segun lo declarado, mientras duro la excursion `[start, end]`.

    `present` si en algun tramo estaba en el modulo; `elsewhere` solo si TODO el intervalo esta
    declarado y en otros modulos; `undeclared` si queda algun tramo sin declarar. Un tramo sin
    declarar no exculpa al habitat: se trata como el supuesto de habitat compartido.
    """
    cuts = sorted(
        {start, end, *(t for stay in stays for t in (stay.start, stay.end) if start < t < end)}
    )
    # Una excursion de una sola lectura es un instante: un unico tramo de longitud cero.
    spans = list(pairwise(cuts)) or [(start, start)]
    whole = True
    for low, high in spans:
        covering = [stay for stay in stays if stay.start <= low and stay.end >= high]
        if not covering:
            whole = False
        elif prevailing(covering).module == module:
            return PRESENT
    return ELSEWHERE if whole else UNDECLARED


def presence(stays: Sequence[Stay], module: str, start: dt.datetime, end: dt.datetime) -> str:
    """Donde estaba alguien durante `[start, end]`, con la regla que ordena las hipotesis.

    Publica para `alert_context`: el detalle de una alerta tiene que decir de la ubicacion lo
    mismo que la vista de tripulacion. Un modulo que no esta en la lista declarada no se puede
    comparar con la ubicacion de nadie: `undeclared`, que nunca exculpa al habitat.
    """
    if module not in MODULES:
        return UNDECLARED
    return _presence(stays, module, start, end)


def _names(subjects: Sequence[str]) -> str:
    if len(subjects) == 1:
        return subjects[0]
    return f"{', '.join(subjects[:-1])} {i18n.tr('y', 'and')} {subjects[-1]}"


@dataclass(frozen=True, slots=True)
class _Span:
    """Lo que se compara con la ubicacion: un modulo, un intervalo y como se nombra.

    Una excursion de cabina y un sistema declarado fuera de lo nominal en un modulo se juzgan
    con la misma regla; solo cambian las palabras.
    """

    module: str
    start: dt.datetime
    end: dt.datetime
    during: str = "la excursión"
    not_comparable: str = NOT_COMPARABLE


# Cómo se nombra en inglés el intervalo de un `_Span` (`during`): fragmento de frase.
_DURING_EN = {"la excursión": "the excursion", "el tramo declarado": "the declared span"}


def _absent_reason_en(
    elsewhere: Sequence[str], name: str, during: str, estimated: bool, less_likely: bool
) -> str:
    """Por qué una hipótesis no alcanza a alguien según su ubicación, en inglés."""
    was = "was" if len(elsewhere) == 1 else "were"
    basis = (
        "the location declared or estimated by the anchors" if estimated
        else "the declared location"
    )
    absent = (
        f"according to {basis}, {_names(elsewhere)} {was} not in {name} during "
        f"{_DURING_EN.get(during, during)}"
    )
    if not less_likely:
        return f"It does not explain everyone's change: {absent}."
    who = (
        "The module anchors estimate it from the strongest signal, and this has not been "
        "checked inside a metal module"
        if estimated else "The location is declared by a person; it is not measured"
    )
    return f"Less likely explanation: {absent}. {who}: if it is not correct, neither is this order."


def _located(
    hypothesis: dict[str, Any],
    span: _Span,
    affected: Sequence[str],
    locations: Mapping[str, Sequence[Stay]],
    since: dt.datetime,
    reference: dt.datetime,
) -> bool:
    """Anota en la hipotesis quien estaba en el modulo. True si pasa a menos probable."""
    # Solo cuenta el tramo que cae en la ventana, como en la regla de siempre: lo que paso
    # antes de la ventana no explica un cambio de ahora.
    start, end = max(span.start, since), min(span.end, reference)
    # Una lectura firmada antes de que existiera la lista puede traer un modulo que no esta en
    # ella. No se puede comparar con la ubicacion de nadie, y no comparar no es estar ausente.
    comparable = span.module in MODULES
    where = {
        subject: (
            _presence(locations.get(subject, ()), span.module, start, end)
            if comparable else UNDECLARED
        )
        for subject in affected
    }
    elsewhere = [subject for subject in affected if where[subject] == ELSEWHERE]
    name = i18n.loc(module_display(span.module))
    estimated = any(
        estimated_location(locations.get(subject, ()), start, end) for subject in elsewhere
    )
    # La regla de siempre —dos o mas afectados— contada solo sobre quienes pudo alcanzar.
    less_likely = len(affected) - len(elsewhere) < 2
    reason: str | None = None
    if not comparable:
        reason = i18n.loc(span.not_comparable)
    elif elsewhere:
        was = "no estaba" if len(elsewhere) == 1 else "no estaban"
        basis = (
            "la ubicación declarada o estimada por las anclas" if estimated
            else "la ubicación declarada"
        )
        absent = f"según {basis}, {_names(elsewhere)} {was} en {name} durante {span.during}"
        who = (
            "La estiman las anclas de módulo por la señal más fuerte, sin validar dentro de un "
            "módulo metálico"
            if estimated else "La ubicación la declara una persona, no se mide"
        )
        reason = (
            f"Explicación menos probable: {absent}. {who}: si no es correcta, este orden "
            "tampoco."
            if less_likely
            else f"No explica el cambio de todos: {absent}."
        )
        if i18n.current() == "en":
            reason = _absent_reason_en(elsewhere, name, span.during, estimated, less_likely)
    hypothesis["likelihood"] = "less_likely" if less_likely else "primary"
    hypothesis["likelihood_reason"] = reason
    hypothesis["location"] = {
        "module": span.module,
        "module_display": name,
        PRESENT: [subject for subject in affected if where[subject] == PRESENT],
        ELSEWHERE: elsewhere,
        UNDECLARED: [subject for subject in affected if where[subject] == UNDECLARED],
    }
    return less_likely


def _unidentified(
    affected: Sequence[str], title: str, first_checks: Sequence[str] = ()
) -> dict[str, Any]:
    return {
        "kind": "shared_unknown",
        "label": LABEL,
        "title": title,
        "affected": list(affected),
        "excursion": None,
        "what_is_known": None,
        "checks": [
            *first_checks,
            _UNRECORDED_CHECK,
            _SCHEDULE_CHECK,
        ],
        "evidence": [],
        "steps": list(STEPS),
    }


# --------------------------------------------------------------------------- #
# Un sistema de soporte vital declarado fuera de lo nominal (base de conocimiento §6)
# --------------------------------------------------------------------------- #
#
# POR QUE EXISTE. La base de conocimiento del equipo pone «estado de life support / thermal
# control» como «causa común potencial de cambios en varios tripulantes». Hasta el 2026-10-21,
# con dos o mas tripulantes fuera de nominal y ninguna excursion de cabina, la hipotesis decia
# «sin causa ambiental registrada» y proponia revisar lo que EMMA no registra, aunque alguien
# hubiera declarado en la consola que la revitalizacion de aire llevaba un dia degradada.
#
# LO QUE NO ES. EMMA no tiene ninguna fuente leida que diga que sistema explica el cambio de
# que dominio, y no la inventa: la hipotesis dice que el sistema CONSTA declarado asi dentro de
# la ventana, rotulada «coincidencia temporal, no causa», y lo repite en su nota. Va detras de
# las excursiones medidas (una lectura que cruza su limite es mas que una declaracion) y delante
# de la causa sin identificar. Que sistemas son de soporte vital lo dice el vocabulario, con la
# lectura del resumen tecnico de la NASA sobre el ECLSS (`environment/systems.py`).
#
# Sin ninguna declaracion de un sistema de soporte vital fuera de lo nominal que toque la
# ventana, la salida es la de antes clave por clave (prueba de no regresion). Es solo orden y
# texto: no mueve niveles, alertas ni excursiones (invariante 5).

SYSTEM_KIND = "declared_system"
# Hay un sistema declarado pero ninguna excursion: «sin causa ambiental registrada» seria falso.
UNIDENTIFIED_WITH_SYSTEM = (
    "Cambio simultáneo en varios tripulantes sin ninguna excursión del hábitat registrada"
)
SYSTEM_NOTE = (
    "EMMA no tiene ninguna fuente leída que relacione el estado de este sistema con el cambio "
    "de estos tripulantes: solo consta que una persona lo declaró así dentro de la ventana "
    "comparada. Es una coincidencia en el tiempo, no una causa."
)
SYSTEM_NOT_COMPARABLE = (
    "El módulo de esta declaración no está en la lista declarada: no se puede comparar con la "
    "ubicación de nadie y se mantiene el supuesto de hábitat compartido."
)
SYSTEM_CHECKS = (
    "Contrastar el estado declarado del sistema con su propia telemetría o con quien lo "
    "declaró: EMMA no lee el estado de ningún sistema.",
    "Revisar si el cambio de cada tripulante empezó antes o después de que constara ese "
    "estado declarado.",
)
SYSTEM_RELEVANCE = (
    "qué funciones forman el soporte vital (ECLSS); no dice qué efecto tiene en las personas "
    "que falle un sistema concreto"
)
i18n.en_many({
    UNIDENTIFIED_WITH_SYSTEM: (
        "Simultaneous change in several crew members with no habitat excursion on record"
    ),
    SYSTEM_NOTE: (
        "EMMA has no source it has read that relates the state of this system to the change in "
        "these crew members: it is only on record that a person declared it so within the "
        "compared window. It is a coincidence in time, not a cause."
    ),
    SYSTEM_NOT_COMPARABLE: (
        "The module of this declaration is not in the declared list: it cannot be compared with "
        "anyone's location and the shared-habitat assumption is kept."
    ),
    SYSTEM_CHECKS[0]: (
        "Cross-check the declared state of the system against its own telemetry or with whoever "
        "declared it: EMMA does not read the state of any system."
    ),
    SYSTEM_CHECKS[1]: (
        "Review whether each crew member's change began before or after that declared state "
        "was on record."
    ),
    SYSTEM_RELEVANCE: (
        "which functions make up life support (ECLSS); it does not say what effect the failure "
        "of a specific system has on people"
    ),
})


def _ago(moment: dt.datetime, reference: dt.datetime) -> str:
    return f"{display.number(abs((reference - moment).total_seconds()) / 3600, 1)} h"


@dataclass(frozen=True, slots=True)
class _Declared:
    """Un tramo fuera de lo nominal que toca la ventana, con lo firmado hasta el instante comparado.

    `told` son las declaraciones de la racha que se refieren a un instante no posterior al
    comparado: una confirmacion firmada para despues no presta ni su asiento ni su nota a una
    hipotesis sobre la ventana. Nunca esta vacio: la primera es la que abre el tramo.
    """

    span: Mapping[str, Any]
    start: dt.datetime
    end: dt.datetime | None
    told: tuple[Mapping[str, Any], ...]


def _system_hypothesis(
    found: _Declared, affected: Sequence[str], reference: dt.datetime
) -> dict[str, Any]:
    span = found.span
    where = "" if span["module"] is None else f" en {span['module_display']}"
    since = f"desde {_ago(found.start, reference)} antes del instante comparado"
    if found.end is None:
        until = "y es lo último declarado"
    elif found.end > reference:
        until = "y seguía así en ese instante"
    else:
        until = f"hasta {_ago(found.end, reference)} antes"
    first, last = found.told[0]["ledger_index"], found.told[-1]["ledger_index"]
    entries = f"asiento {first}" if first == last else f"asientos {first} a {last}"
    names = list(dict.fromkeys(str(item["declared_by"]) for item in found.told))
    who = f"lo declaró {names[0]}" if len(names) == 1 else f"lo declararon {_names(names)}"
    # La nota mas reciente de la racha, con quien la escribio: no tiene por que ser quien abrio
    # el tramo.
    noted = [item for item in found.told if item["note"]]
    note = noted[-1] if noted else None
    hypothesis: dict[str, Any] = {
        "kind": SYSTEM_KIND,
        "label": COINCIDENCE_LABEL,
        "title": (
            f"Sistema {span['system_display']}{where} declarado «{span['state_display']}» "
            "dentro de la ventana comparada"
        ),
        "affected": list(affected),
        "excursion": None,
        "system": {
            "key": span["system"],
            "display": span["system_display"],
            "state": span["state"],
            "state_display": span["state_display"],
            "module": span["module"],
            "module_display": span["module_display"],
            "start": span["start"],
            "end": span["end"],
            "declared_by": names,
            "ledger_index": first,
            "last_ledger_index": last,
            "note": None if note is None else note["note"],
            "note_by": None if note is None else note["declared_by"],
            "label": habitat_systems.DECLARED_LABEL,
            # La frase entera, para que la interfaz no la componga.
            "statement": (
                f"Declarado «{span['state_display']}» {since}, {until}; {who} ({entries}): "
                f"{habitat_systems.DECLARED_LABEL}."
            ),
        },
        "what_is_known": None,
        "checks": list(SYSTEM_CHECKS),
        "evidence": [registry.Citation(LIMITS_SOURCE, SYSTEM_RELEVANCE).to_dict()],
        "steps": list(STEPS),
    }
    if i18n.current() == "en":
        _system_in_english(hypothesis, found, reference, names)
    return hypothesis


def _system_in_english(
    hypothesis: dict[str, Any], found: _Declared, reference: dt.datetime, names: Sequence[str]
) -> None:
    """El título y la frase de `_system_hypothesis` en inglés: mismas ramas, mismas cifras."""
    span = found.span
    where = "" if span["module"] is None else f" in {span['module_display']}"
    since = f"since {_ago(found.start, reference)} before the compared time"
    if found.end is None:
        until = "and it is the last thing declared"
    elif found.end <= reference:
        until = f"until {_ago(found.end, reference)} before"
    else:
        until = "and it was still so at that time"
    first, last = found.told[0]["ledger_index"], found.told[-1]["ledger_index"]
    entries = f"ledger entry {first}" if first == last else f"ledger entries {first} to {last}"
    label = i18n.loc(habitat_systems.DECLARED_LABEL)
    hypothesis["title"] = (
        f"System {span['system_display']}{where} declared «{span['state_display']}» within the "
        "compared window"
    )
    hypothesis["system"]["label"] = label
    hypothesis["system"]["statement"] = (
        f"Declared «{span['state_display']}» {since}, {until}; declared by {_names(names)} "
        f"({entries}): {label}."
    )


def _systems_in_window(
    declarations: Sequence[Mapping[str, Any]], since: dt.datetime, reference: dt.datetime
) -> list[_Declared]:
    """El ultimo tramo fuera de lo nominal de cada sistema y modulo que toca la ventana.

    «Ultimo» en el orden en que se firmo, como «lo vigente» en `systems.overview`: una
    correccion firmada despues manda aunque se refiera a un instante anterior. El sistema entero
    y cada modulo son ambitos distintos, como alli: un «nominal» del sistema entero no cierra un
    «degradado» de un modulo.
    """
    latest: dict[tuple[str, str | None], _Declared] = {}
    for span in habitat_systems.off_nominal_spans([dict(item) for item in declarations]):
        start = dt.datetime.fromisoformat(span["start"])
        end = None if span["end"] is None else dt.datetime.fromisoformat(span["end"])
        if start <= reference and (end is None or end >= since):
            told = tuple(
                item for item in span["declarations"]
                if dt.datetime.fromisoformat(item["at"]) <= reference
            )
            latest[(span["system"], span["module"])] = _Declared(span, start, end, told)
    return list(latest.values())


# --------------------------------------------------------------------------- #
# Radiacion registrada dentro de la ventana (base de conocimiento §6 y §2.1)
# --------------------------------------------------------------------------- #
#
# POR QUE EXISTE. La base de conocimiento pone «Radiación / posición / shielding» entre la
# telemetria del habitat con relevancia sanitaria (§6) y, para el riesgo de radiacion, «fusionar
# hazard + dosimetría» (§2.1). Hasta el 2026-10-26 esta capa solo proponia la cabina y los
# sistemas declarados: en el escenario `spe-event`, con la tasa de dosis de un tripulante en
# 1394,9 µGy/h, la vista de tripulacion decia «sin causa ambiental registrada».
#
# DE DONDE SALE EL EVENTO. De dos cosas que EMMA ya tiene, y de ninguna mas:
# - la DOSIMETRIA: las lecturas de tasa de dosis absorbida de cada tripulante (las mismas que lee
#   su estado, con el corte de Tierra ya aplicado), juzgadas con la regla del motor
#   (`baseline.crossed_danger_limit`, el limite de peligro del catalogo). En el escenario simulado
#   el evento solo existe ahi: el simulador sube la tasa de dosis (`_dose_multiplier`) y firma las
#   lecturas como `simulator:spe-event`, y la frase lo dice;
# - el HAZARD: los eventos de particulas solares (SEP) de NASA DONKI que tiene el estado
#   (`environment/donki.py`), con el intervalo que esos datos cubren. Fuera de el no se dice
#   «ningun evento»: se dice que no hay dato, como en el contexto de una alerta.
#
# LO QUE NO ES. Una tasa de dosis alta no dice por si sola que hubo un evento solar, y la frase
# lo dice cuando DONKI no lo registra. Ninguna fuente leida relaciona esa dosis con el cambio de
# esos tripulantes: va rotulada «coincidencia temporal, no causa», como un sistema declarado. A
# diferencia de las causas compartidas se propone tambien con UN afectado: la radiacion se
# registra aparte de la tripulacion (dosimetro, DONKI), no se deduce de que varios cambien a la
# vez. No se juzga con la ubicacion declarada: EMMA no sabe el blindaje de cada modulo.
#
# Con dos o mas afectados va detras de las excursiones de cabina (su hipotesis cita lo que se
# sabe del parametro; esta no tiene nada que citar sobre las personas) y delante de los sistemas
# declarados (una lectura que cruza su limite es mas que una declaracion). Con uno, detras de la
# individual. Sin radiacion en la ventana, la salida es la de antes clave por clave (prueba de no
# regresion). Es solo orden y texto: no mueve niveles, alertas, excursiones ni `rules_version`
# (invariante 5).

SOLAR_KIND = "solar_event"
DOSE_KEY = "absorbed-dose-rate"
# Una tasa de dosis por encima de su limite no es una excursion de la cabina: con radiacion en la
# ventana, «sin causa ambiental registrada» seria falso y «sin ninguna excursion del habitat»,
# ambiguo.
UNIDENTIFIED_WITH_RADIATION = (
    "Cambio simultáneo en varios tripulantes sin ninguna excursión de los parámetros de cabina "
    "registrada"
)
SOLAR_NOTE = (
    "EMMA no tiene ninguna fuente leída que relacione esta radiación con el cambio de estos "
    "tripulantes: solo consta que se registró dentro de la ventana comparada. Es una "
    "coincidencia en el tiempo, no una causa; la parte del cambio que es la propia tasa de dosis "
    "(dominio de radiación) es la misma medida. La tasa de dosis cambia de un punto a otro de la "
    "nave y EMMA no conoce el blindaje de cada módulo: la ubicación declarada no ordena esta "
    "hipótesis."
)
SOLAR_CHECKS = (
    "Contrastar la tasa de dosis con otro dosímetro de la nave y con el aviso de radiación de a "
    "bordo: EMMA no lee ese aviso.",
    "Revisar qué parte del cambio de cada tripulante es la propia tasa de dosis (dominio de "
    "radiación) y qué parte está en otros dominios.",
    "Revisar si el cambio de cada tripulante empezó antes o después de la radiación registrada.",
)
SOLAR_RELEVANCE = (
    "en Orion varios sensores miden la tasa de dosis en distintas partes de la cabina, con un "
    "umbral de precaución y otro de refugio cuyas cifras no da; no dice qué efecto tiene una "
    "dosis en las personas"
)
SOLAR_SOURCE = registry.get("nasa-artemis2-eyes-on-sun")
_SOLAR_TITLE_EVENT = (
    "Evento de partículas solares registrado en NASA DONKI dentro de la ventana comparada"
)
_SOLAR_TITLE_DOSE = (
    "Tasa de dosis por encima de su límite de peligro dentro de la ventana comparada"
)
i18n.en_many({
    UNIDENTIFIED_WITH_RADIATION: (
        "Simultaneous change in several crew members with no excursion of the cabin parameters "
        "on record"
    ),
    SOLAR_NOTE: (
        "EMMA has no source it has read that relates this radiation to the change in these crew "
        "members: it is only on record that it was registered within the compared window. It is "
        "a coincidence in time, not a cause; the part of the change that is the dose rate "
        "itself (radiation domain) is the same measurement. The dose rate varies from one point "
        "of the ship to another and EMMA does not know the shielding of each module: the "
        "declared location does not order this hypothesis."
    ),
    SOLAR_CHECKS[0]: (
        "Cross-check the dose rate against another dosimeter on the ship and against the "
        "onboard radiation warning: EMMA does not read that warning."
    ),
    SOLAR_CHECKS[1]: (
        "Review which part of each crew member's change is the dose rate itself (radiation "
        "domain) and which part is in other domains."
    ),
    SOLAR_CHECKS[2]: (
        "Review whether each crew member's change began before or after the recorded radiation."
    ),
    SOLAR_RELEVANCE: (
        "in Orion several sensors measure the dose rate in different parts of the cabin, with a "
        "caution threshold and a shelter threshold whose figures it does not give; it does not "
        "say what effect a radiation dose has on people"
    ),
    _SOLAR_TITLE_EVENT: "Solar particle event recorded in NASA DONKI within the compared window",
    _SOLAR_TITLE_DOSE: "Dose rate above its danger limit within the compared window",
})
DONKI_WITH_DATA, DONKI_PARTIAL, DONKI_NO_DATA = "with_data", "partial", "no_data"


@dataclass(frozen=True, slots=True)
class RadiationRecord:
    """Lo que EMMA tiene de radiacion para comparar con la ventana: dosimetria y NASA DONKI.

    `doses` son las lecturas de cada tripulante (solo cuentan las de tasa de dosis absorbida).
    `solar_events` son los SEP de DONKI que tiene el estado y `solar_known` el intervalo que
    cubren esos datos, o None si no hay ninguno: fuera de el no se puede decir «ningun evento».
    """

    doses: Mapping[str, Sequence[VitalObservation]]
    solar_events: Sequence[SolarEvent] = ()
    solar_known: tuple[dt.datetime, dt.datetime] | None = None


@dataclass(frozen=True, slots=True)
class _Radiation:
    """La radiacion que toca la ventana: lecturas por encima de su limite y eventos de DONKI."""

    above: tuple[VitalObservation, ...]
    any_dose: bool
    events: tuple[SolarEvent, ...]
    donki: str


def _donki_coverage(
    known: tuple[dt.datetime, dt.datetime] | None, since: dt.datetime, reference: dt.datetime
) -> str:
    if known is None or known[1] < known[0] or known[1] < since or known[0] > reference:
        return DONKI_NO_DATA
    if known[0] <= since and known[1] >= reference:
        return DONKI_WITH_DATA
    return DONKI_PARTIAL


def _radiation_in_window(
    record: RadiationRecord | None, since: dt.datetime, reference: dt.datetime
) -> _Radiation | None:
    """La radiacion registrada en `[since, reference]`, o None si no hay nada que proponer."""
    if record is None:
        return None
    doses = [
        item for series in record.doses.values() for item in series
        if item.key == DOSE_KEY and since <= item.effective <= reference
    ]
    # Solo el cruce por arriba: es lo que la frase dice («por encima de su límite»).
    above = tuple(
        sorted(
            (
                item for item in doses
                if (limit := crossed_danger_limit(item)) is not None and item.value > limit
            ),
            key=lambda item: (item.effective, item.subject),
        )
    )
    events = tuple(
        sorted(
            (item for item in record.solar_events if since <= item.time <= reference),
            key=lambda item: item.time,
        )
    )
    if not above and not events:
        return None
    return _Radiation(
        above, bool(doses), events, _donki_coverage(record.solar_known, since, reference)
    )


def _dose_sentence(found: _Radiation, reference: dt.datetime) -> tuple[str, dict[str, Any] | None]:
    if not found.above:
        if found.any_dose:
            return i18n.tr(
                "Ninguna lectura de tasa de dosis de la tripulación pasó de su límite de peligro "
                "en la ventana.",
                "No crew dose rate reading went above its danger limit in the window.",
            ), None
        return i18n.tr(
            "Sin lecturas de tasa de dosis de la tripulación en la ventana.",
            "No crew dose rate readings in the window.",
        ), None
    code = indicator(DOSE_KEY)
    unit = display.unit(code.unit)
    # El limite que cruzo cada lectura, el mismo que juzga el motor (depende del estado de la
    # lectura): con uno solo se da ese; con varios, el menor, que es el que todas superan.
    limit = min(
        (value for item in found.above if (value := crossed_danger_limit(item)) is not None),
        default=None,
    )
    subjects = sorted({item.subject for item in found.above})
    sources = sorted({item.source for item in found.above})
    peak = max(found.above, key=lambda item: item.value)
    first = found.above[0]
    who = (
        f"del dosímetro de {subjects[0]}" if len(subjects) == 1
        else f"de los dosímetros de {_names(subjects)}"
    )
    limit_text = "" if limit is None else f" ({display.number(limit, 1)} {unit})"
    sentence = (
        f"Tasa de dosis absorbida por encima de su límite de peligro{limit_text} en "
        f"{_count(len(found.above), 'lectura', 'lecturas')} {who}, la primera "
        f"{_ago(first.effective, reference)} antes del instante comparado, con un máximo de "
        f"{display.number(peak.value, 1)} {unit}; origen de las lecturas: {', '.join(sources)}."
    )
    if i18n.current() == "en":
        who = (
            f"from {subjects[0]}'s dosimeter" if len(subjects) == 1
            else f"from the dosimeters of {_names(subjects)}"
        )
        sentence = (
            f"Absorbed dose rate above its danger limit{limit_text} in "
            f"{_count(len(found.above), 'reading', 'readings')} {who}, the first "
            f"{_ago(first.effective, reference)} before the compared time, with a maximum of "
            f"{display.number(peak.value, 1)} {unit}; source of the readings: "
            f"{', '.join(sources)}."
        )
    return sentence, {
        "key": DOSE_KEY,
        "unit": code.unit,
        "limit": limit,
        "subjects": subjects,
        "readings": len(found.above),
        "first": first.effective.isoformat(),
        "last": found.above[-1].effective.isoformat(),
        "peak": peak.value,
        "peak_subject": peak.subject,
        "sources": sources,
    }


def _donki_sentence_en(found: _Radiation, reference: dt.datetime) -> str:
    """La frase de `_donki_sentence` en inglés: mismas ramas, mismas cifras."""
    if found.events:
        listed = ", ".join(
            f"{item.event_id} ({_ago(item.time, reference)} before the compared time)"
            for item in found.events
        )
        events = _count(len(found.events), "solar particle event", "solar particle events")
        sentence = f"NASA DONKI records {events} in the window: {listed}."
        if found.donki == DONKI_PARTIAL:
            sentence += " Its data cover only part of the window."
        return sentence
    if found.donki == DONKI_WITH_DATA:
        return (
            "NASA DONKI records no solar particle event in the window: the dose rate alone does "
            "not say whether it was a solar event."
        )
    if found.donki == DONKI_PARTIAL:
        return (
            "The NASA DONKI data cover only part of the window and record no solar particle "
            "event in it: it is not known whether it was a solar event."
        )
    return (
        "No NASA DONKI data covering the window: the dose rate alone does not say whether it "
        "was a solar event."
    )


def _donki_sentence(found: _Radiation, reference: dt.datetime) -> str:
    if i18n.current() == "en":
        return _donki_sentence_en(found, reference)
    if found.events:
        listed = ", ".join(
            f"{item.event_id} ({_ago(item.time, reference)} antes del instante comparado)"
            for item in found.events
        )
        sentence = (
            f"NASA DONKI registra {_count(len(found.events), 'evento', 'eventos')} de "
            f"partículas solares en la ventana: {listed}."
        )
        if found.donki == DONKI_PARTIAL:
            sentence += " Sus datos cubren solo una parte de la ventana."
        return sentence
    if found.donki == DONKI_WITH_DATA:
        return (
            "NASA DONKI no registra ningún evento de partículas solares en la ventana: la tasa "
            "de dosis sola no dice si fue un evento solar."
        )
    if found.donki == DONKI_PARTIAL:
        return (
            "Los datos de NASA DONKI cubren solo una parte de la ventana y no registran en ella "
            "ningún evento de partículas solares: no se sabe si fue un evento solar."
        )
    return (
        "Sin datos de NASA DONKI que cubran la ventana: la tasa de dosis sola no dice si fue un "
        "evento solar."
    )


def _solar_hypothesis(
    found: _Radiation, affected: Sequence[str], reference: dt.datetime, declared: bool
) -> dict[str, Any]:
    dose_text, dose = _dose_sentence(found, reference)
    donki_text = _donki_sentence(found, reference)
    hypothesis: dict[str, Any] = {
        "kind": SOLAR_KIND,
        "label": COINCIDENCE_LABEL,
        "title": _SOLAR_TITLE_EVENT if found.events else _SOLAR_TITLE_DOSE,
        "affected": list(affected),
        "excursion": None,
        "radiation": {
            "dose": dose,
            "donki": {
                "status": found.donki,
                "events": [item.to_dict() for item in found.events],
            },
            # La frase entera, para que la interfaz no la componga.
            "statement": f"{dose_text} {donki_text}",
        },
        "what_is_known": None,
        "checks": list(SOLAR_CHECKS),
        "evidence": [registry.Citation(SOLAR_SOURCE, SOLAR_RELEVANCE).to_dict()],
        "steps": list(STEPS),
    }
    if declared:
        # Como un sistema entero: no esta en un modulo, y ninguna ubicacion la baja.
        hypothesis["likelihood"] = "primary"
        hypothesis["likelihood_reason"] = None
    return hypothesis


def _in_window(
    excursions: Sequence[Excursion], reference: dt.datetime, window: dt.timedelta
) -> list[Excursion]:
    """Excursiones de limite normativo (`health`) que tocan `[reference - window, reference]`."""
    since = reference - window
    return [
        item for item in excursions
        if item.kind == "health" and item.end >= since and item.start <= reference
    ]


def coincidence(
    display: str,
    onsets: Mapping[str, dt.datetime | None],
    drifting: Collection[str],
    excursions: Sequence[Excursion],
    reference: dt.datetime,
    window: dt.timedelta,
    located: bool = False,
) -> dict[str, Any]:
    """Cuantos tripulantes se desvian a la vez en UN indicador, y desde cuando.

    Es la lectura descriptiva de la comparacion entre tripulantes (especificacion §10): no
    propone causa ni comprobaciones —eso es `correlate`, sobre el estado completo—, solo cuenta.

    `onsets` lleva a cada tripulante CON lecturas en la ventana: su primera lectura fuera de lo
    esperado, o None si no tiene ninguna que cuente. Quien no tiene lecturas no entra: no pasa
    por "dentro de lo esperado". `drifting` son los que tienen una deriva que preocupa. Quien
    decide ambas cosas es el motor (persistencia y tendencia); aqui no hay umbral ninguno.

    "A la vez" empieza con el ultimo en desviarse. Si alguno lo hace solo por una deriva no hay
    instante que dar —una pendiente no tiene inicio— y se dice en vez de inventarlo. La
    excursion de cabina se juzga con la misma regla que en `correlate`. `located`: alguno de
    los comparados ha declarado donde estaba en la ventana; cambia lo que se declara como
    supuesto, no lo que se cuenta.
    """
    deviating = sorted(
        subject for subject, onset in onsets.items() if onset is not None or subject in drifting
    )
    dated = [onset for subject in deviating if (onset := onsets[subject]) is not None]
    undated = len(deviating) - len(dated)
    relevant = _in_window(excursions, reference, window)
    if not onsets:
        text = (
            f"{display}: ningún tripulante tiene lecturas en la ventana comparada; no hay nada "
            "que comparar."
        )
        english = (
            f"{display}: no crew member has readings in the compared window; there is nothing "
            "to compare."
        )
    elif not deviating:
        text = (
            f"{display}: ningún tripulante tiene lecturas fuera de lo esperado ni una deriva "
            "sostenida en la ventana comparada."
        )
        english = (
            f"{display}: no crew member has readings outside the expected range or a sustained "
            "drift in the compared window."
        )
    elif len(deviating) == 1:
        text = (
            f"{display}: solo {deviating[0]} tiene lecturas fuera de lo esperado o una deriva "
            "sostenida; no hay coincidencia entre tripulantes."
        )
        english = (
            f"{display}: only {deviating[0]} has readings outside the expected range or a "
            "sustained drift; there is no coincidence between crew members."
        )
    else:
        text = (
            f"{display}: {len(deviating)} de {len(onsets)} tripulantes con lecturas tienen a la "
            "vez lecturas fuera de lo esperado o una deriva sostenida. Es una coincidencia en el "
            "tiempo: por sí sola no señala una causa común."
        )
        english = (
            f"{display}: {len(deviating)} of {len(onsets)} crew members with readings have, at "
            "the same time, readings outside the expected range or a sustained drift. It is a "
            "coincidence in time: on its own it does not point to a common cause."
        )
        if relevant:
            names = ", ".join(sorted({parameter(item.parameter).display for item in relevant}))
            text += f" En la misma ventana estuvo fuera de su límite normativo: {names}."
            names = ", ".join(
                sorted({i18n.loc(parameter(item.parameter).display) for item in relevant})
            )
            english += (
                f" In the same window, the following was outside its normative limit: {names}."
            )
    simultaneous = len(deviating) >= 2 and undated == 0
    text = i18n.tr(text, english)
    said: dict[str, Any] = {
        "label": COINCIDENCE_LABEL,
        "text": text,
        "deviating": deviating,
        "with_data": len(onsets),
        "first_onset": min(dated).isoformat() if dated else None,
        "simultaneous_since": max(dated).isoformat() if simultaneous else None,
        "onset_basis": i18n.tr(
            "primera lectura fuera de lo esperado dentro de la ventana comparada",
            "first reading outside the expected range within the compared window",
        ),
        "undated_note": i18n.tr(
            "Al menos una de las desviaciones es una deriva sostenida: se describe por su "
            "pendiente y no tiene instante de inicio.",
            "At least one of the deviations is a sustained drift: it is described by its slope "
            "and has no onset time.",
        ) if undated else None,
        "habitat_excursions": [item.to_dict() for item in relevant],
        "assumption": COMPARISON_IGNORES_LOCATION if located else ASSUMPTION,
        "window_hours": window.total_seconds() / 3600,
    }
    # El rótulo y el supuesto son constantes: se resuelven al servir, en el idioma de la petición.
    said["label"] = i18n.loc(said["label"])
    said["assumption"] = i18n.loc(said["assumption"])
    return said


def correlate(
    levels_by_subject: dict[str, str],
    excursions: Sequence[Excursion],
    reference: dt.datetime,
    window: dt.timedelta,
    locations: Mapping[str, Sequence[Stay]] | None = None,
    systems: Sequence[Mapping[str, Any]] | None = None,
    radiation: RadiationRecord | None = None,
) -> dict[str, Any]:
    """Hipotesis ordenadas: primero lo compartido, despues lo individual.

    `levels_by_subject` es el nivel global actual de cada tripulante; `excursions`, las del
    habitat. Solo cuentan las excursiones de limite normativo (`health`) que tocan la ventana
    `[reference - window, reference]`. `locations` es la ubicacion declarada de cada
    tripulante; sin ninguna que toque la ventana, la salida es la del habitat compartido.
    `systems` son las declaraciones del estado de los sistemas (`api.systems`); un sistema de
    soporte vital declarado fuera de lo nominal dentro de la ventana entra como coincidencia
    en el tiempo, detras de las excursiones. `radiation` es la dosimetria y lo que el estado
    tiene de NASA DONKI; radiacion registrada en la ventana entra tambien como coincidencia,
    con uno o con varios afectados. Sin ninguno de los dos, la salida es la de antes.
    """
    affected = sorted(s for s, level in levels_by_subject.items() if level != "nominal")
    since = reference - window
    relevant = _in_window(excursions, reference, window)
    located = locations or {}
    declared = sorted(
        subject for subject in levels_by_subject
        if any(
            stay.end >= since and stay.start <= reference
            for stay in located.get(subject, ())
        )
    )
    solar = _radiation_in_window(radiation, since, reference) if affected else None
    hypotheses: list[dict[str, Any]] = []
    if len(affected) >= 2:
        demoted: list[dict[str, Any]] = []
        for item in relevant:
            hypothesis = _hypothesis_for(item, affected)
            span = _Span(item.module, item.start, item.end)
            if declared and _located(hypothesis, span, affected, located, since, reference):
                demoted.append(hypothesis)
            else:
                hypotheses.append(hypothesis)
        environment_first = bool(hypotheses)
        if solar is not None:
            hypotheses.append(_solar_hypothesis(solar, affected, reference, bool(declared)))
        candidates = _systems_in_window(systems or (), since, reference)
        for found in candidates:
            hypothesis = _system_hypothesis(found, affected, reference)
            module = found.span["module"]
            if declared and module is not None:
                span = _Span(
                    module, found.start, reference if found.end is None else found.end,
                    "el tramo declarado", SYSTEM_NOT_COMPARABLE,
                )
                if _located(hypothesis, span, affected, located, since, reference):
                    demoted.append(hypothesis)
                    continue
            elif declared:
                # Un sistema entero no esta en un modulo: no hay ubicacion que lo descarte.
                hypothesis["likelihood"] = "primary"
                hypothesis["likelihood_reason"] = None
            hypotheses.append(hypothesis)
        if not relevant:
            hypotheses.append(_unidentified(
                affected,
                UNIDENTIFIED_WITH_RADIATION if solar is not None
                else UNIDENTIFIED_WITH_SYSTEM if candidates
                else _UNIDENTIFIED,
            ))
        elif not environment_first:
            # Ninguna excursion alcanza a dos o mas segun lo declarado: va una causa comun sin
            # identificar delante de las ambientales. Como todo depende de una declaracion, lo
            # primero que se propone es comprobarla.
            # Si alguna de esas ubicaciones la estimaron las anclas, no se dice «declarada».
            estimated = any(
                estimated_location(located.get(subject, ()), since, reference)
                for subject in declared
            )
            hypotheses.append(
                _unidentified(
                    affected, UNIDENTIFIED_ESTIMATED_LOCATED, (CHECK_ESTIMATED_LOCATION,)
                )
                if estimated
                else _unidentified(affected, UNIDENTIFIED_LOCATED, (CHECK_LOCATION,))
            )
        hypotheses.extend(demoted)
    for subject in affected:
        if len(affected) < 2:
            hypotheses.append({
                "kind": "individual",
                "label": LABEL,
                "title": i18n.tr(
                    f"Cambio individual en {subject}", f"Individual change in {subject}"
                ),
                "affected": [subject],
                "excursion": None,
                "what_is_known": None,
                "checks": [_INDIVIDUAL_CHECK],
                "evidence": [],
                "steps": list(STEPS),
            })
    if len(affected) == 1 and solar is not None:
        # La radiacion se registra aparte de la tripulacion: con un solo afectado tambien
        # coincide en el tiempo con su cambio, y va detras de la hipotesis individual.
        hypotheses.append(_solar_hypothesis(solar, affected, reference, bool(declared)))
    for hypothesis in hypotheses:
        _in_language(hypothesis)
    result: dict[str, Any] = {
        "hypotheses": hypotheses,
        "affected": affected,
        "habitat_excursions": [item.to_dict() for item in relevant],
        "assumption": ASSUMPTION,
        "window_hours": window.total_seconds() / 3600,
    }
    if declared:
        result["assumption"] = (
            ASSUMPTION_ESTIMATED_LOCATED
            if any(
                estimated_location(located.get(subject, ()), since, reference)
                for subject in declared
            )
            else ASSUMPTION_LOCATED
        )
        result["location_declared"] = declared
    result["assumption"] = i18n.loc(result["assumption"])
    return result


# --------------------------------------------------------------------------- #
# Los siete pasos del flujo, con su estado (especificacion §7)
# --------------------------------------------------------------------------- #
#
# POR QUE EXISTE. Cada hipotesis llevaba `steps`: los siete nombres del flujo, iguales para
# todas, y la interfaz no los pintaba porque no decian nada. Lo que la tripulacion necesita ver
# es POR DONDE VA cada hipotesis: que ha hecho ya el sistema, que espera a una persona y que no
# le corresponde. Ese estado sale de datos que ya estan en la hipotesis y en su revision
# firmada; aqui solo se lee y se redacta, para que la interfaz no deduzca nada.
#
# No decide nada: no toca niveles, alertas ni el orden de las hipotesis (invariante 5). Va
# aparte de `correlate` —que tiene su salida fijada por una prueba de no regresion— y la llama
# la ruta cuando ya ha unido la revision humana.
#
# "Comprobaciones" esta hecho cuando el sistema las PROPONE, que es lo que pide el paso
# ("comprobaciones sugeridas"): EMMA no registra si alguien las ha hecho, y el texto lo dice.

DONE, AWAITING_HUMAN, NOT_APPLICABLE, IN_PROGRESS = (
    "done", "awaiting_human", "not_applicable", "in_progress",
)
STEP_STATE_DISPLAY = {
    DONE: "hecho",
    AWAITING_HUMAN: "pendiente de una persona",
    NOT_APPLICABLE: "no aplica",
    IN_PROGRESS: "en seguimiento",
}
# Tabla paralela, y no el registro común de `i18n`: «hecho» es una palabra suelta.
STEP_STATE_DISPLAY_EN = {
    DONE: "done",
    AWAITING_HUMAN: "awaiting a person",
    NOT_APPLICABLE: "not applicable",
    IN_PROGRESS: "in follow-up",
}
STEP_KEYS = (
    "detect", "correlate", "candidates", "evidence", "checks", "human_confirmation", "recovery",
)
# Lo unico que EMMA tiene de la mayoria de parametros es el limite que cruzan. Se dice, en vez
# de dejar un hueco que parezca un olvido o de rellenarlo con efectos que nadie ha leido.
LIMIT_ONLY = (
    "De este parámetro EMMA solo cita el límite que se ha cruzado: no tiene ninguna fuente "
    "leída sobre su efecto en las personas."
)
_DECISION_DISPLAY = {"confirmed": "Confirmada", "discarded": "Descartada"}
_DECISION_DISPLAY_EN = {"confirmed": "Confirmed", "discarded": "Discarded"}
# Dos pasos del flujo se dicen con una frase fija: su inglés se registra por la frase y lo
# resuelve `flow` al servir cada paso.
_AWAITING_REVIEW = "Pendiente de que una persona confirme o descarte la hipótesis."
_DISCARDED = "Hipótesis descartada: no se sigue su recuperación."
i18n.en_many({
    LIMIT_ONLY: (
        "For this parameter EMMA only cites the limit that has been crossed: it has no source "
        "it has read on its effect on people."
    ),
    _AWAITING_REVIEW: "Awaiting a person to confirm or discard the hypothesis.",
    _DISCARDED: "Hypothesis discarded: its recovery is not followed.",
})
# Lo que cuenta `_count` con nombre castellano y tiene que salir en inglés sin tocar la llamada.
_COUNTED_EN = {
    "fuente citada": "source cited", "fuentes citadas": "sources cited",
    "tripulante": "crew member", "tripulantes": "crew members",
    "comprobación propuesta": "check proposed",
    "comprobaciones propuestas": "checks proposed",
}


def _count(amount: int, singular: str, plural: str) -> str:
    word = singular if amount == 1 else plural
    return f"{amount} {i18n.tr(word, _COUNTED_EN.get(word, word))}"


def knowledge_note(hypothesis: Mapping[str, Any]) -> str | None:
    """Que decir donde iria "lo que se sabe" cuando solo esta la cita del limite.

    De un sistema declarado o de la radiacion registrada, que EMMA no sabe nada de su efecto en
    estas personas.
    """
    if hypothesis.get("kind") == SYSTEM_KIND:
        return SYSTEM_NOTE
    if hypothesis.get("kind") == SOLAR_KIND:
        return SOLAR_NOTE
    if hypothesis.get("excursion") is None or hypothesis.get("what_is_known") is not None:
        return None
    return LIMIT_ONLY


def _evidence_step(hypothesis: Mapping[str, Any]) -> tuple[str, str]:
    cited = len(hypothesis.get("evidence") or ())
    if not cited:
        return NOT_APPLICABLE, i18n.tr(
            "Esta hipótesis no señala un parámetro concreto: no hay fuente que citar.",
            "This hypothesis does not point to a specific parameter: there is no source to cite.",
        )
    if hypothesis.get("kind") == SYSTEM_KIND:
        # La nota de que nada lo relaciona con nadie ya va en `knowledge_note`; aqui, para que
        # se cita lo que se cita.
        return DONE, i18n.tr(
            f"{_count(cited, 'fuente citada', 'fuentes citadas')}: qué funciones forman el "
            "soporte vital, no qué efecto tiene en las personas que falle un sistema.",
            f"{_count(cited, 'fuente citada', 'fuentes citadas')}: which functions make up "
            "life support, not what effect the failure of a system has on people.",
        )
    if hypothesis.get("kind") == SOLAR_KIND:
        return DONE, i18n.tr(
            f"{_count(cited, 'fuente citada', 'fuentes citadas')}: dónde se mide la tasa de "
            "dosis en Orion, no qué efecto tiene una dosis en las personas.",
            f"{_count(cited, 'fuente citada', 'fuentes citadas')}: where the dose rate is "
            "measured in Orion, not what effect a radiation dose has on people.",
        )
    note = knowledge_note(hypothesis)
    return DONE, note or f"{_count(cited, 'fuente citada', 'fuentes citadas')}."


def _confirmation_step(hypothesis: Mapping[str, Any]) -> tuple[str, str]:
    if hypothesis.get("excursion") is None:
        return NOT_APPLICABLE, i18n.tr(
            "Solo se revisan las hipótesis que señalan una excursión concreta del hábitat.",
            "Only hypotheses that point to a specific habitat excursion are reviewed.",
        )
    review = hypothesis.get("review")
    if review is None:
        return AWAITING_HUMAN, _AWAITING_REVIEW
    decision = _DECISION_DISPLAY.get(review["decision"], str(review["decision"]))
    decision_en = _DECISION_DISPLAY_EN.get(review["decision"], str(review["decision"]))
    return DONE, i18n.tr(
        f"{decision} por {review['decided_by']} (asiento {review['ledger_index']} del registro).",
        f"{decision_en} by {review['decided_by']} (ledger entry {review['ledger_index']}).",
    )


def _recovery_step(hypothesis: Mapping[str, Any]) -> tuple[str, str]:
    review = hypothesis.get("review")
    if hypothesis.get("excursion") is None or review is None:
        return NOT_APPLICABLE, i18n.tr(
            "Solo se sigue la recuperación de una hipótesis confirmada.",
            "Only the recovery of a confirmed hypothesis is followed.",
        )
    recovery = review.get("recovery")
    if review["decision"] != "confirmed" or recovery is None:
        return NOT_APPLICABLE, _DISCARDED
    still = list(recovery["still_affected"])
    cabin = (
        i18n.tr("El parámetro ha vuelto a su límite", "The parameter is back within its limit")
        if recovery["habitat_within_limit"]
        else i18n.tr(
            "El parámetro sigue fuera de su límite", "The parameter is still outside its limit"
        )
    )
    crew = (
        i18n.tr(
            f"siguen fuera de nominal: {_names(still)}",
            f"still outside nominal: {_names(still)}",
        )
        if still
        else i18n.tr(
            "ningún afectado sigue fuera de nominal",
            "no affected crew member is still outside nominal",
        )
    )
    recovered = recovery["habitat_within_limit"] and not still
    return (DONE if recovered else IN_PROGRESS), f"{cabin}; {crew}."


def flow(hypothesis: Mapping[str, Any]) -> list[dict[str, str]]:
    """Los siete pasos de una hipotesis, cada uno con su estado y una frase.

    `hypothesis` es una de las que da `correlate`, ya con su `review` (o sin el: se lee como
    "sin revisar"). El orden y los nombres son los de `STEPS`.
    """
    affected = list(hypothesis["affected"])
    excursion = hypothesis.get("excursion")
    kind = hypothesis["kind"]
    if excursion is not None:
        correlated = (
            f"{excursion['display']} fuera de {excursion['requirement']} en "
            f"{module_display(excursion['module'])}, dentro de la ventana comparada."
        )
    elif kind == "individual":
        correlated = (
            "Un solo tripulante fuera de nominal: la regla no propone una causa compartida."
        )
    elif kind == SYSTEM_KIND:
        correlated = (
            f"{hypothesis['system']['statement']} Coincide en el tiempo con el cambio de dos o "
            "más tripulantes; ninguna fuente leída dice que lo explique."
        )
    elif kind == SOLAR_KIND:
        correlated = (
            f"{hypothesis['radiation']['statement']} Coincide en el tiempo con el cambio de "
            f"{_count(len(affected), 'tripulante', 'tripulantes')}. La parte de ese cambio que es "
            "la propia tasa de dosis (dominio de radiación) es la misma medida, no otra causa; "
            "del resto, ninguna fuente leída dice que lo explique."
        )
    else:
        correlated = (
            "Ninguna excursión del hábitat explica, en la ventana comparada, el cambio de dos "
            "o más tripulantes."
        )
    if i18n.current() == "en":
        correlated = _correlated_en(hypothesis, affected)
    proposed = _count(
        len(hypothesis.get("checks") or ()), "comprobación propuesta", "comprobaciones propuestas"
    )
    library = len(hypothesis.get("countermeasures") or ())
    if library:
        proposed += i18n.tr(
            f" y {library} de la biblioteca de contramedidas",
            f" and {library} from the countermeasure library",
        )
    crew = _count(len(affected), "tripulante", "tripulantes")
    states: tuple[tuple[str, str], ...] = (
        (DONE, i18n.tr(
            f"{crew} fuera de nominal: {_names(affected)}.",
            f"{crew} outside nominal: {_names(affected)}.",
        )),
        (DONE, correlated),
        (DONE, i18n.tr(
            f"{hypothesis['title']}. Es una hipótesis: {hypothesis['label']}.",
            f"{hypothesis['title']}. It is a hypothesis: {hypothesis['label']}.",
        )),
        _evidence_step(hypothesis),
        (DONE, i18n.tr(
            f"{proposed}. EMMA no registra si se han hecho.",
            f"{proposed}. EMMA does not record whether they have been done.",
        )),
        _confirmation_step(hypothesis),
        _recovery_step(hypothesis),
    )
    names = STEPS_EN if i18n.current() == "en" else STEPS
    return [
        # `loc` resuelve los pasos que se dicen con una frase fija; los demás ya vienen redactados.
        {"key": key, "name": name, "state": state,
         "state_display": i18n.tr(STEP_STATE_DISPLAY[state], STEP_STATE_DISPLAY_EN[state]),
         "detail": i18n.loc(detail)}
        for key, name, (state, detail) in zip(STEP_KEYS, names, states, strict=True)
    ]


def _correlated_en(hypothesis: Mapping[str, Any], affected: Sequence[str]) -> str:
    """Con qué se correlaciona una hipótesis, en inglés: las mismas cinco ramas de `flow`."""
    excursion = hypothesis.get("excursion")
    kind = hypothesis["kind"]
    if excursion is not None:
        return (
            f"{i18n.loc(excursion['display'])} outside {excursion['requirement']} in "
            f"{i18n.loc(module_display(excursion['module']))}, within the compared window."
        )
    if kind == "individual":
        return "Only one crew member outside nominal: the rule does not propose a shared cause."
    if kind == SYSTEM_KIND:
        return (
            f"{hypothesis['system']['statement']} It coincides in time with the change of two "
            "or more crew members; no source read says that it explains it."
        )
    if kind == SOLAR_KIND:
        return (
            f"{hypothesis['radiation']['statement']} It coincides in time with the change of "
            f"{_count(len(affected), 'tripulante', 'tripulantes')}. The part of that change "
            "that is the dose rate itself (radiation domain) is the same measurement, not "
            "another cause; for the rest, no source read says that it explains it."
        )
    return (
        "No habitat excursion explains, in the compared window, the change of two or more crew "
        "members."
    )


# --------------------------------------------------------------------------- #
# Lo que la norma escribe de cada parametro que no es CO2
# --------------------------------------------------------------------------- #
#
# POR QUE EXISTE. De ocho de los nueve parametros de cabina EMMA solo citaba el limite cruzado
# (`LIMIT_ONLY`). El 2026-10-13 se leyeron las dos fuentes de esos limites —NASA-STD-3001 Vol 2
# Rev F y JSC 20584 Rev C, en su PDF oficial— buscando UNA cosa: que escribe cada documento
# junto al limite. Lo que sigue es eso y nada mas: la justificacion (Rationale) del requisito
# o la fila de la tabla de SMAC, con su frase literal, su seccion y la fecha de lectura.
#
# LO QUE NO ES. No es un estudio sobre personas ni un diagnostico: es el motivo que la norma da
# para su limite, y el texto lo dice ("la norma lo justifica por..."). Donde la norma NO
# describe un efecto por salir del rango (O2, presion) se dice asi, en vez de deducirlo.
#
# DONDE VA. En `annotate`, no en `_KNOWLEDGE`: la salida de `correlate` esta fijada por una
# prueba de no regresion y no cambia. Es solo texto y citas: no toca niveles, alertas ni el
# orden de las hipotesis (invariante 5), y no anade comprobaciones ni contramedidas.


@dataclass(frozen=True, slots=True)
class SourcedStatement:
    """Una frase o una fila de tabla leida en la fuente, con donde esta.

    Una frase va literal. Una fila de tabla va celda a celda, separadas por " | " y cada valor
    con la cabecera de su columna delante (1 hr, 24 hr...): las celdas son las del documento.
    """

    ref: str
    requirement: str
    locator: str
    quote: str
    # El dia en que se leyo ESTA frase, si no es el de la primera lectura (`SOURCES_READ_ON`).
    read_on: str | None = None

    def to_dict(self) -> dict[str, str]:
        return {
            "ref": self.ref, "requirement": self.requirement, "locator": self.locator,
            "quote": self.quote, "read_on": self.read_on or SOURCES_READ_ON,
        }


SOURCES_READ_ON = STANDARD_READ_ON
# La segunda lectura de NASA-STD-3001 Vol 2 Rev F, la de las clases de limite de la cabina
# (`environment/habitat.py`, cabecera).
REREAD_ON = "2026-10-14"
SMAC_REF = "jsc-20584-rev-c"
KNOWLEDGE_BASIS = (
    "Es la justificación que la norma escribe junto a su límite, leída en el documento "
    "oficial: no es un estudio sobre esta tripulación ni un diagnóstico."
)
STANDARD_RELEVANCE = "justificación del límite, leída en el documento"
# La advertencia del propio documento de SMAC, que acompana a los tres contaminantes.
_SMAC_CAVEAT = (
    "El documento advierte de que superar un SMAC no implica un daño seguro: indica que la "
    "tripulación puede estar expuesta a un riesgo mayor."
)
_SMAC_CAVEAT_SOURCE = SourcedStatement(
    SMAC_REF, "SMAC", "§1.0 Background, página 6",
    "Conversely, exceedance of a SMAC does not mean that health impairment is certain (there "
    "are many other factors that influence ultimate health outcomes), although it does "
    "indicate that the crew may be subject to increased risks that must be closely evaluated.",
)
_THERMAL = SourcedStatement(
    STANDARD_REF, "[V2 6012]", "§6.2.3.1 Crew Health Environmental Limits, Rationale",
    "Operations outside of these boundaries may cause crewmembers to experience health "
    "impacts (dry, stuffy and/or irritated mucous membranes), skin rashes (due to microbial "
    "growth at high humidity levels) thermal discomfort (overheating depending on tasks), "
    "and/or decreased performance.",
)
_THERMAL_TEXT = (
    "NASA-STD-3001 Vol 2 Rev F [V2 6012] justifica sus límites de temperatura y humedad "
    "porque fuera de ellos la tripulación puede tener las mucosas secas, congestionadas o "
    "irritadas, erupciones de la piel (por crecimiento microbiano con humedad alta), malestar "
    "térmico y menor rendimiento. La norma da los dos límites juntos, en una sola figura, y "
    "no separa qué efecto corresponde a la temperatura y cuál a la humedad. EMMA sitúa cada "
    "lectura en esa figura con sus cuatro vértices rotulados: la humedad sola, y la "
    "temperatura con la humedad del mismo instante."
)
_THERMAL_FIGURE = SourcedStatement(
    STANDARD_REF, "[V2 6012]", "Figure 6.2-2 Crew Health Environmental Limits, rótulos de los "
    "vértices",
    "(18C, 75%) | (25.7C, 75%) | (27C, 25%) | (19.1C, 25%) | Operating Limit",
    read_on=REREAD_ON,
)

_STANDARD_KNOWLEDGE: dict[str, tuple[str, tuple[SourcedStatement, ...]]] = {
    "cabin-ppo2": (
        "NASA-STD-3001 Vol 2 Rev F [V2 6003] da 145-155 mmHg como rango objetivo de normoxia "
        "y no describe un efecto por salir de él: lo justifica porque los límites "
        "fisiológicos de la hipoxia y la hiperoxia en vuelo se desconocen. Su tabla 6.2-1 "
        "admite por debajo una hipoxia leve, hasta 127 mmHg en media de una hora y con 122 "
        "como mínimo absoluto, de duración indefinida con vigilancia, y por encima una "
        "hiperoxia de duración indefinida hasta 356 mmHg: esos son los límites que EMMA "
        "evalúa, y salir de 145-155 es solo un aviso. El requisito se refiere al oxígeno "
        "inspirado (PIO2); la lectura de EMMA es la presión parcial de la cabina.",
        (
            SourcedStatement(
                STANDARD_REF, "[V2 6003]",
                "§6.2.1.2 O2 Partial Pressure Range for Crew Exposure, Rationale",
                "Since physiological limits for hypoxic (and hyperoxic) exposure during "
                "spaceflight are unknown, systems designed for humans are to be normoxic "
                "unless strong rationale is provided for an alternative suggestion.",
            ),
            SourcedStatement(
                STANDARD_REF, "[V2 6003]",
                "Table 6.2-1 Inspired Oxygen Partial Pressure Exposure Ranges, fila PIO2 (mmHg)",
                "Normoxia Target Range 145-155 | Indefinite Hyperoxia Upper Limit 356 | "
                "Short-Term Hyperoxia Upper Limit 791 | Mild Hypoxia Lower Limit 127**** | "
                "Acceptable Duration: Indefinite | Indefinite | 6-9 Hours* | Indefinite with "
                "monitoring**",
            ),
            SourcedStatement(
                STANDARD_REF, "[V2 6003]", "Table 6.2-1, nota ****",
                "1-hour time-weighted average with an absolute lower limit for the minimum "
                "hypoxia range of 122 mmHg/2.36 psia",
                read_on=REREAD_ON,
            ),
        ),
    ),
    "cabin-pressure": (
        "NASA-STD-3001 Vol 2 Rev F [V2 6006] fija este rango como el de exposición indefinida "
        "sin deterioro medible de la salud ni del rendimiento, y no describe qué efecto tiene "
        "salir de él. Su justificación añade que una presión total baja exige más proporción "
        "de oxígeno en la atmósfera, y que una atmósfera rica en oxígeno alimenta el fuego.",
        (
            SourcedStatement(
                STANDARD_REF, "[V2 6006]",
                "§6.2.2.1 Total Pressure Tolerance Range for Indefinite Crew Exposure, "
                "texto del requisito (fragmento)",
                "for indefinite human exposure without measurable impairments to health or "
                "performance.",
            ),
            SourcedStatement(
                STANDARD_REF, "[V2 6006]", "§6.2.2.1, Rationale",
                "Low total pressure requires a higher percentage of oxygen in the atmosphere "
                "to provide an acceptable PIO2. Oxygen-rich atmospheres, however, present "
                "safety hazards because of their ability to feed fires.",
            ),
        ),
    ),
    "cabin-temperature": (_THERMAL_TEXT, (_THERMAL, _THERMAL_FIGURE)),
    "cabin-humidity": (
        f"{_THERMAL_TEXT} Del límite inferior de humedad dice además que evita un ambiente "
        "tan seco que acumule electricidad estática.",
        (
            _THERMAL,
            SourcedStatement(
                STANDARD_REF, "[V2 6012]", "§6.2.3.1, Rationale",
                "From an engineering perspective, average humidity is to be maintained above "
                "this lower limit (25%) to ensure that the environment is not too dry to "
                "prevent static electricity buildup within the cabin, which could pose an "
                "electrical hazard to crew and a possible ignition hazard.",
            ),
            _THERMAL_FIGURE,
        ),
    ),
    "cabin-noise": (
        "NASA-STD-3001 Vol 2 Rev F [V2 6077] llama a 85 dBA el límite de ruido peligroso y lo "
        "justifica para que no haya interferencia con la comunicación por voz y con las "
        "alarmas, ni más riesgo de pérdida de audición. El requisito es para operaciones "
        "fuera de lo nominal, comunicaciones, válvulas de presurización y mantenimiento: el "
        "ruido nominal lo limitan otros requisitos que EMMA no comprueba.",
        (
            SourcedStatement(
                STANDARD_REF, "[V2 6077]",
                "§6.6.1.5 Hazardous Noise Limits for All Phases Except Launch, Entry, and "
                "Abort, Rationale",
                "The 85 dBA overall SPL defines the hazardous noise limit during all phases "
                "except launch, entry, and abort, at which action to reduce the noise level "
                "is to be taken so that interference with voice communications and alarms, "
                "as well as increased risk for hearing loss, does not occur.",
            ),
            SourcedStatement(
                STANDARD_REF, "[V2 6077]", "§6.6.1.5, Rationale",
                "This is not intended for nominal hardware emissions but to limit the sound "
                "level of sources such as communications systems, depressurization valves, "
                "and levels that occur during planned off-nominal operations and maintenance "
                "activities.",
            ),
        ),
    ),
    "cabin-co": (
        "La tabla de SMAC de la NASA (JSC 20584 Rev C) da, como órganos y efectos que fijan "
        "el límite del monóxido de carbono, el sistema nervioso central (depresión) y el "
        f"cardiovascular (arritmia), con la carboxihemoglobina como referencia. {_SMAC_CAVEAT}",
        (
            SourcedStatement(
                SMAC_REF, "SMAC", "§2.0 Published SMACs, página 11, fila «Carbon monoxide»",
                "Carbon monoxide | CAS #: 630-08-0 | REMARKS: Carboxyhemoglobin target | "
                "1 hr 425 (485) | 24 hr 100 (114) | 7 d 55 (63) | 30 d 15 (17) | 180 d 15 (17) "
                "| 1000 d 15 (17) | Organ: CNS, CV | Effect: Depression, Arrhythmia",
            ),
            _SMAC_CAVEAT_SOURCE,
        ),
    ),
    "cabin-ammonia": (
        "La tabla de SMAC de la NASA (JSC 20584 Rev C) da, como órganos y efectos que fijan "
        "el límite del amoníaco, los ojos (irritación) y el sistema nervioso central "
        f"(cefalea). {_SMAC_CAVEAT}",
        (
            SourcedStatement(
                SMAC_REF, "SMAC", "§2.0 Published SMACs, página 9, fila «Ammonia»",
                "Ammonia | CAS #: 7664-41-7 | 1 hr 30 (20) | 24 hr 20 (14) | 7 d 3 (2) | "
                "30 d 3 (2) | 180 d 3 (2) | 1000 d 3 (2) | Organ: Eye, CNS | Effect: "
                "Irritation, Headache",
            ),
            _SMAC_CAVEAT_SOURCE,
        ),
    ),
    "cabin-formaldehyde": (
        "La tabla de SMAC de la NASA (JSC 20584 Rev C) da, como órgano y efecto que fijan el "
        "límite del formaldehído, las mucosas (irritación); en el de 1000 días añade la nariz "
        f"(cáncer). Lo anota como carcinógeno y sus valores como valores techo. {_SMAC_CAVEAT}",
        (
            SourcedStatement(
                SMAC_REF, "SMAC", "§2.0 Published SMACs, página 15, fila «Formaldehyde»",
                "Formaldehyde | CAS #: 50-00-0 | REMARKS: Ceiling values, Carcinogen | "
                "1 hr 0.8 (1.0) | 24 hr 0.5 (0.6) | 7 d 0.1 (0.12) | 30 d 0.1 (0.12) | "
                "180 d 0.1 (0.12) | 1000 d 0.1 (0.12) | Organ: Mucosa (1000 d: Mucosa, Nose) | "
                "Effect: Irritation (1000 d: Irritation, Cancer)",
            ),
            _SMAC_CAVEAT_SOURCE,
        ),
    ),
}


def standard_evidence() -> dict[str, tuple[registry.Citation, ...]]:
    """Las fichas que cita lo escrito por la norma, por parametro (una por documento)."""
    return {
        key: tuple(
            registry.cite(ref, STANDARD_RELEVANCE)
            for ref in dict.fromkeys(item.ref for item in sources)
        )
        for key, (_, sources) in _STANDARD_KNOWLEDGE.items()
    }


# Se resuelve al importar: una ficha que no existe no arranca, como `LIMITS_SOURCE`.
_STANDARD_EVIDENCE = standard_evidence()

# EL INGLÉS DE LO QUE LA NORMA ESCRIBE. Las citas (`quote`) ya son las del documento, en inglés,
# y no se tocan; se traduce lo que EMMA redacta sobre ellas y la parte castellana de dónde está
# cada una (`locator`: «página», «fila», «nota»). Dice lo mismo que el castellano, no más.
_SMAC_CAVEAT_EN = (
    "The document warns that exceeding a SMAC does not mean that harm is certain: it indicates "
    "that the crew may be exposed to a higher risk."
)
_SMAC_TABLE_EN = "NASA's SMAC table (JSC 20584 Rev C) gives, as the"
_THERMAL_TEXT_EN = (
    "NASA-STD-3001 Vol 2 Rev F [V2 6012] justifies its temperature and humidity limits because "
    "outside them the crew may have dry, stuffy or irritated mucous membranes, skin rashes "
    "(from microbial growth at high humidity), thermal discomfort and decreased performance. "
    "The standard gives the two limits together, in a single figure, and does not separate "
    "which effect belongs to temperature and which to humidity. EMMA places each reading in "
    "that figure with its four labelled vertices: humidity on its own, and temperature with the "
    "humidity of the same instant."
)
i18n.en_many({
    KNOWLEDGE_BASIS: (
        "It is the rationale the standard writes next to its limit, read in the official "
        "document: it is not a study of this crew, nor a clinical judgement."
    ),
    STANDARD_RELEVANCE: "rationale for the limit, read in the document",
    _STANDARD_KNOWLEDGE["cabin-ppo2"][0]: (
        "NASA-STD-3001 Vol 2 Rev F [V2 6003] gives 145-155 mmHg as the normoxia target range "
        "and does not describe an effect of leaving it: it justifies it because the "
        "physiological limits of hypoxia and hyperoxia in flight are unknown. Its table 6.2-1 "
        "allows, below it, mild hypoxia down to 127 mmHg as a one-hour average and with 122 as "
        "the absolute minimum, of indefinite duration with monitoring, and, above it, hyperoxia "
        "of indefinite duration up to 356 mmHg: those are the limits EMMA evaluates, and "
        "leaving 145-155 is only a notice. The requirement refers to inspired oxygen (PIO2); "
        "EMMA's reading is the partial pressure in the cabin."
    ),
    _STANDARD_KNOWLEDGE["cabin-pressure"][0]: (
        "NASA-STD-3001 Vol 2 Rev F [V2 6006] sets this range as that of indefinite exposure "
        "without measurable impairment of health or performance, and does not describe what "
        "effect leaving it has. Its rationale adds that a low total pressure requires a higher "
        "proportion of oxygen in the atmosphere, and that an oxygen-rich atmosphere feeds fire."
    ),
    _THERMAL_TEXT: _THERMAL_TEXT_EN,
    _STANDARD_KNOWLEDGE["cabin-humidity"][0]: (
        f"{_THERMAL_TEXT_EN} Of the lower humidity limit it also says that it avoids an "
        "environment so dry that static electricity builds up."
    ),
    _STANDARD_KNOWLEDGE["cabin-noise"][0]: (
        "NASA-STD-3001 Vol 2 Rev F [V2 6077] calls 85 dBA the hazardous noise limit and "
        "justifies it so that there is no interference with voice communication and alarms, "
        "nor a higher risk of hearing loss. The requirement is for off-nominal operations, "
        "communications, pressurization valves and maintenance: nominal noise is limited by "
        "other requirements that EMMA does not check."
    ),
    _STANDARD_KNOWLEDGE["cabin-co"][0]: (
        f"{_SMAC_TABLE_EN} organs and effects that set the carbon monoxide limit, the central "
        "nervous system (depression) and the cardiovascular system (arrhythmia), with "
        f"carboxyhemoglobin as the reference. {_SMAC_CAVEAT_EN}"
    ),
    _STANDARD_KNOWLEDGE["cabin-ammonia"][0]: (
        f"{_SMAC_TABLE_EN} organs and effects that set the ammonia limit, the eyes "
        f"(irritation) and the central nervous system (headache). {_SMAC_CAVEAT_EN}"
    ),
    _STANDARD_KNOWLEDGE["cabin-formaldehyde"][0]: (
        f"{_SMAC_TABLE_EN} organ and effect that set the formaldehyde limit, the mucous "
        "membranes (irritation); in the 1000-day limit it adds the nose (cancer). It notes it "
        f"as a carcinogen and its values as ceiling values. {_SMAC_CAVEAT_EN}"
    ),
    "§1.0 Background, página 6": "§1.0 Background, page 6",
    "Figure 6.2-2 Crew Health Environmental Limits, rótulos de los vértices": (
        "Figure 6.2-2 Crew Health Environmental Limits, vertex labels"
    ),
    "Table 6.2-1 Inspired Oxygen Partial Pressure Exposure Ranges, fila PIO2 (mmHg)": (
        "Table 6.2-1 Inspired Oxygen Partial Pressure Exposure Ranges, row PIO2 (mmHg)"
    ),
    "Table 6.2-1, nota ****": "Table 6.2-1, note ****",
    (
        "§6.2.2.1 Total Pressure Tolerance Range for Indefinite Crew Exposure, texto del "
        "requisito (fragmento)"
    ): (
        "§6.2.2.1 Total Pressure Tolerance Range for Indefinite Crew Exposure, requirement text "
        "(fragment)"
    ),
    "§2.0 Published SMACs, página 11, fila «Carbon monoxide»": (
        "§2.0 Published SMACs, page 11, row «Carbon monoxide»"
    ),
    "§2.0 Published SMACs, página 9, fila «Ammonia»": (
        "§2.0 Published SMACs, page 9, row «Ammonia»"
    ),
    "§2.0 Published SMACs, página 15, fila «Formaldehyde»": (
        "§2.0 Published SMACs, page 15, row «Formaldehyde»"
    ),
})


def _add_standard_knowledge(hypothesis: dict[str, Any]) -> None:
    """Pone lo que la norma escribe donde el CO2 tiene `what_is_known`, si no hay nada ya."""
    excursion = hypothesis.get("excursion")
    hypothesis.setdefault("what_is_known_basis", None)
    hypothesis.setdefault("what_is_known_sources", [])
    if excursion is None or hypothesis.get("what_is_known") is not None:
        return
    found = _STANDARD_KNOWLEDGE.get(excursion["parameter"])
    if found is None:
        return
    text, sources = found
    hypothesis["what_is_known"] = text
    hypothesis["what_is_known_basis"] = KNOWLEDGE_BASIS
    hypothesis["what_is_known_sources"] = [item.to_dict() for item in sources]
    hypothesis["evidence"] = [
        *hypothesis.get("evidence", ()),
        *(item.to_dict() for item in _STANDARD_EVIDENCE[excursion["parameter"]]),
    ]
    if i18n.current() == "en":
        # Lo que se acaba de poner son constantes castellanas: se sirven en inglés. Las citas
        # literales del documento (`quote`) no se tocan.
        hypothesis["what_is_known"] = i18n.loc(text)
        hypothesis["what_is_known_basis"] = i18n.loc(KNOWLEDGE_BASIS)
        hypothesis["what_is_known_sources"] = [
            {**item, "locator": i18n.loc(item["locator"])}
            for item in hypothesis["what_is_known_sources"]
        ]
        hypothesis["evidence"] = [
            {**item, "relevance": i18n.loc(item["relevance"])} if item.get("relevance") else item
            for item in hypothesis["evidence"]
        ]


def annotate(hypothesis: dict[str, Any]) -> None:
    """Anade a una hipotesis ya revisada lo que la interfaz pinta sin deducir nada."""
    _add_standard_knowledge(hypothesis)
    note = knowledge_note(hypothesis)
    hypothesis["knowledge_note"] = None if note is None else i18n.loc(note)
    hypothesis["flow"] = flow(hypothesis)
