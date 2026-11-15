"""Las cinco preguntas de los gemelos: la tabla de la base de conocimiento, respondida.

Por qué existe: la base de conocimiento del equipo (`docs/contexto/knowledge-base-v1.md` §10,
«Arquitectura conceptual consolidada») resume el sistema en cinco capas —Human, Habitat, Mission y
Countermeasure Twin, y la capa de decisión— y le hace a cada una una pregunta. EMMA ya responde a
las cinco, pero cada respuesta vive en un panel distinto (dominios, hábitat, misión, «Qué hacer»,
«Espera por una persona»), y nadie juntaba las cinco para un tripulante: quien quisiera saber si el
sistema contesta a lo que el equipo pidió tenía que recorrer la consola entera y adivinar qué panel
responde a qué.

LO QUE ES Y LO QUE NO ES
------------------------
Es una **composición**. Cada respuesta se arma con lo que el estado ya calculó (`/api/status`), con
las hipótesis de la vista de tripulación frente al hábitat (`/api/crew`) y con lo que lleva días
esperando a una persona (`app/waiting.py`), y dice de dónde sale cada parte (`sources`). Aquí no se
calcula ningún nivel, umbral, hipótesis ni recomendación, no se firma nada y nada vuelve al motor:
un panel más que lee lo mismo que los otros, con sus palabras.

Las preguntas y los nombres de las capas son los del documento, **literales** y en su idioma (la
tabla mezcla «Twin» en inglés con el castellano): una prueba compara esta tabla con la del fichero,
para que una edición del documento no deje aquí una pregunta que ya no es la suya.

Lo que EMMA no sabe responder se dice. A «¿qué efecto esperamos?» no responde con una predicción:
EMMA no modela el efecto de una contramedida, y lo que da es qué se vuelve a medir para verlo y qué
pasó las otras veces que se adoptó, con la advertencia de causalidad que ya lleva esa respuesta.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core import display, i18n
from app.ingest.codes import domain_name
from app.waiting import unacknowledged_title

SOURCE = (
    "Base de conocimiento del equipo (docs/contexto/knowledge-base-v1.md), §10 «Arquitectura "
    "conceptual consolidada»: las columnas «Twin / capa», «Contenido» y «Pregunta», copiadas "
    "literales."
)
NOTE = (
    "Cada respuesta junta lo que el estado ya calculó y dice de dónde sale. Esta vista no calcula "
    "nada nuevo, no firma nada en el registro y no cambia ningún nivel ni alerta."
)
# Para la consola de Tierra (`until`): lo posterior al corte del retardo no ha llegado.
GROUND_NOTE = (
    "Es lo que Tierra puede saber: las cinco respuestas salen de lo llegado hasta su corte, y lo "
    "registrado a bordo después sigue en tránsito."
)

# Estados de una respuesta. La interfaz elige con ellos la marca, no la frase.
ANSWERED = "answered"
NOTHING = "nothing"
UNAVAILABLE = "unavailable"

_STATUS = "GET /api/status"


@dataclass(frozen=True)
class Layer:
    """Una fila de la tabla de §10, tal cual."""

    key: str
    twin: str
    content: str
    question: str


# Literal de `docs/contexto/knowledge-base-v1.md` §10 (lo comprueba `tests/test_twins.py`).
LAYERS: tuple[Layer, ...] = (
    Layer(
        "human", "Human Twin",
        "fisiología, biología, cognición, nutrición, historial, baseline",
        "¿qué está cambiando en esta persona?",
    ),
    Layer(
        "habitat", "Habitat Twin",
        "atmósfera, térmico, radiación, microbiología, life support",
        "¿hay una causa ambiental o sistémica?",
    ),
    Layer(
        "mission", "Mission Twin",
        "fase, posición, duración, gravedad, EVA, workload, comunicaciones, recursos",
        "¿qué contexto operacional explica/modifica el riesgo?",
    ),
    Layer(
        "countermeasure", "Countermeasure Twin",
        "ejercicio, dieta, descanso, protección, procedimientos, recursos y respuesta previa",
        "¿qué puede hacerse ahora y qué efecto esperamos?",
    ),
    Layer(
        "decision", "Decision layer",
        "fusión, anomalía, explicación, evidencia, recomendación y seguimiento",
        "¿qué necesita saber/hacer la tripulación, con qué confianza?",
    ),
)

# Del nivel más grave al más leve: lo que más cambia, primero.
_SEVERITY = ("critical", "concern", "watch")

# Las mismas palabras que el flujo de una alerta (`analysis/alert_flow.py`), y la del cierre.
_FOLLOW_UP_DISPLAY = {
    "in_window": "en su ventana de seguimiento",
    "due": "ventana cumplida, lista para revisar y cerrar",
    "closed": "cerrada",
}

RADIATION_SOURCE = (
    "GET /api/habitat → radiation (última tasa de dosis de cada dosímetro y evento solar "
    "vigente; se muestra y no se evalúa)"
)

NO_EFFECT_MODEL = (
    "EMMA no predice el efecto de una contramedida: dice qué se vuelve a medir para verlo y qué "
    "pasó las otras veces que se adoptó, que no prueba que fuera por ella."
)

# EL INGLÉS (`core/i18n.py`). La tabla de arriba sigue siendo la del documento, literal y en su
# idioma, y la prueba la compara con él. Para quien lee la consola en inglés se sirve además la
# traducción de EMMA de «Contenido» y «Pregunta» (los nombres de las capas ya están en inglés en
# el documento), y la frase de la fuente lo dice: el original está en castellano. Sin esto las
# cinco preguntas, que son el título de cada bloque, no las entendería quien no lee castellano.
i18n.en_many({
    SOURCE: (
        "The team's knowledge base (docs/contexto/knowledge-base-v1.md), §10 «Arquitectura "
        "conceptual consolidada»: the columns «Twin / capa», «Contenido» and «Pregunta». The "
        "original is in Spanish; the content and the questions are shown here in EMMA's "
        "translation."
    ),
    NOTE: (
        "Each answer puts together what the status has already computed and says where it "
        "comes from. This view computes nothing new, signs nothing in the ledger and changes "
        "no level and no alert."
    ),
    GROUND_NOTE: (
        "It is what Earth can know: the five answers come from what had arrived up to its "
        "cut-off, and what was recorded on board afterwards is still in transit."
    ),
    LAYERS[0].content: "physiology, biology, cognition, nutrition, history, baseline",
    LAYERS[0].question: "what is changing in this person?",
    LAYERS[1].content: "atmosphere, thermal, radiation, microbiology, life support",
    LAYERS[1].question: "is there an environmental or systemic cause?",
    LAYERS[2].content: (
        "phase, position, duration, gravity, EVA, workload, communications, resources"
    ),
    LAYERS[2].question: "what operational context explains/modifies the risk?",
    LAYERS[3].content: (
        "exercise, diet, rest, protection, procedures, resources and prior response"
    ),
    LAYERS[3].question: "what can be done now and what effect do we expect?",
    LAYERS[4].content: (
        "fusion, anomaly, explanation, evidence, recommendation and follow-up"
    ),
    LAYERS[4].question: "what does the crew need to know/do, and with what confidence?",
    _FOLLOW_UP_DISPLAY["in_window"]: "within its follow-up window",
    _FOLLOW_UP_DISPLAY["due"]: "window complete, ready to review and close",
    _FOLLOW_UP_DISPLAY["closed"]: "closed",
    RADIATION_SOURCE: (
        "GET /api/habitat → radiation (latest dose rate of each dosimeter and current solar "
        "event; it is shown and not evaluated)"
    ),
    NO_EFFECT_MODEL: (
        "EMMA does not predict the effect of a countermeasure: it says what is measured again "
        "to see it and what happened the other times it was adopted, which does not prove "
        "that it was because of it."
    ),
})


def _count(amount: int, singular: str, plural: str) -> str:
    return f"{display.number(amount, 0)} {singular if amount == 1 else plural}"


def _count_of(amount: int, spanish: tuple[str, str], english: tuple[str, str]) -> str:
    """`_count` con el singular y el plural del idioma de la petición."""
    singular, plural = english if i18n.current() == "en" else spanish
    return _count(amount, singular, plural)


def _item(text: str, level: str | None = None) -> dict[str, Any]:
    return {"text": text, "level": level}


def _answer(
    layer: Layer,
    state: str,
    answer: str,
    items: Sequence[dict[str, Any]] = (),
    notes: Sequence[str] = (),
    sources: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "key": layer.key,
        "twin": layer.twin,
        # La tabla es la del documento; en inglés, la traducción de EMMA registrada arriba.
        "content": i18n.loc(layer.content),
        "question": i18n.loc(layer.question),
        "state": state,
        "answer": answer,
        "items": list(items),
        # Las notas y las fuentes que son una constante de este módulo salen con su inglés; las
        # que vienen redactadas de otro sitio, como llegan.
        "notes": [i18n.loc(note) for note in notes],
        "sources": [i18n.loc(source) for source in sources],
    }


def human(status: Mapping[str, Any]) -> dict[str, Any]:
    """¿Qué está cambiando? Los dominios fuera de nominal, con sus causas y su trayectoria."""
    domains = status.get("domains") or {}
    changing = sorted(
        (
            (key, value) for key, value in domains.items()
            if value.get("level") in _SEVERITY
        ),
        key=lambda pair: (_SEVERITY.index(pair[1]["level"]), domain_name(pair[0])),
    )
    items = []
    for key, value in changing:
        level = value["level"]
        causes = "; ".join(value.get("drivers") or []) or i18n.tr(
            "sin causa enumerada", "no cause listed"
        )
        trajectory = (value.get("trajectory") or {}).get("display")
        # El nivel va en `level` (la interfaz lo pinta con su insignia), no en la frase.
        text = f"{domain_name(key).capitalize()}: {causes}"
        items.append(_item(
            i18n.tr(
                f"{text}. Frente a una ventana antes: {trajectory}.",
                f"{text}. Against one window earlier: {trajectory}.",
            ) if trajectory else f"{text}.",
            level,
        ))
    return _answer(
        LAYERS[0],
        ANSWERED if items else NOTHING,
        str(status.get("summary") or ""),
        items,
        sources=[i18n.tr(
            f"{_STATUS} → summary y domains (nivel, causas y trayectoria de cada dominio)",
            f"{_STATUS} → summary and domains (level, causes and trajectory of each domain)",
        )],
    )


def habitat(
    status: Mapping[str, Any],
    crew: Mapping[str, Any] | None,
    radiation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """¿Causa ambiental o sistémica? Las hipótesis de la vista de tripulación que le incluyen, y
    lo registrado alrededor de cada alerta suya.

    La radiación del hábitat (`GET /api/habitat` → `radiation`, 2026-10-26) va como nota, con la
    frase del backend: se muestra y no se evalúa, así que no es una respuesta a la pregunta ni
    cambia el estado de la capa."""
    subject = str(status.get("subject"))
    sources = [
        i18n.tr(
            "GET /api/crew → correlation (hipótesis de tripulación frente al hábitat)",
            "GET /api/crew → correlation (crew hypotheses against the habitat)",
        ),
        i18n.tr(
            f"{_STATUS} → alerts[].detail.context (lo registrado alrededor de cada alerta)",
            f"{_STATUS} → alerts[].detail.context (what was recorded around each alert)",
        ),
    ]
    radiation_notes: list[str] = []
    if radiation is not None and radiation.get("summary"):
        radiation_notes.append(str(radiation["summary"]))
        sources.append(RADIATION_SOURCE)
    around = [
        _item(
            i18n.tr(
                f"Alrededor de la alerta {domain_name(alert['domain'])} "
                f"({alert['detail']['context']['label']}): "
                f"{alert['detail']['context']['summary']}",
                f"Around the {domain_name(alert['domain'])} alert "
                f"({alert['detail']['context']['label']}): "
                f"{alert['detail']['context']['summary']}",
            ),
            alert.get("level"),
        )
        for alert in status.get("alerts") or []
        if (alert.get("detail") or {}).get("context")
    ]
    if crew is None:
        return _answer(
            LAYERS[1], UNAVAILABLE,
            i18n.tr(
                "La vista de tripulación frente al hábitat no respondió: sin ella no hay "
                "hipótesis que dar.",
                "The crew view against the habitat did not respond: without it there are no "
                "hypotheses to give.",
            ),
            around, radiation_notes, sources=sources,
        )
    correlation = crew.get("correlation") or {}
    mine = [
        item for item in correlation.get("hypotheses") or []
        if subject in (item.get("affected") or [])
    ]
    items = [
        _item(
            f"{item['title']} ({item['label']})."
            + (
                i18n.tr(
                    f" Menos probable: {item['likelihood_reason']}",
                    f" Less likely: {item['likelihood_reason']}",
                )
                if item.get("likelihood") == "less_likely" and item.get("likelihood_reason")
                else ""
            )
        )
        for item in mine
    ]
    notes = [str(correlation["assumption"])] if correlation.get("assumption") else []
    notes += radiation_notes
    if subject not in (correlation.get("affected") or []):
        answer = i18n.tr(
            f"{subject} no tiene ningún dominio fuera de nominal: la vista de tripulación no "
            f"propone para él ninguna hipótesis.",
            f"{subject} has no domain outside nominal: the crew view proposes no hypothesis "
            f"for this crew member.",
        )
    elif mine:
        answer = i18n.tr(
            f"La vista de tripulación propone {display.number(len(mine), 0)} hipótesis "
            f"que {'incluye' if len(mine) == 1 else 'incluyen'} a {subject}; la primera: "
            f"{mine[0]['title']}.",
            f"The crew view proposes {display.number(len(mine), 0)} "
            f"{'hypothesis that includes' if len(mine) == 1 else 'hypotheses that include'} "
            f"{subject}; the first: {mine[0]['title']}.",
        )
    else:
        answer = i18n.tr(
            f"La vista de tripulación no propone ninguna hipótesis que incluya a {subject}.",
            f"The crew view proposes no hypothesis that includes {subject}.",
        )
    return _answer(
        LAYERS[1], ANSWERED if items or around else NOTHING, answer, items + around, notes, sources
    )


def mission(status: Mapping[str, Any]) -> dict[str, Any]:
    """¿Qué contexto operacional? Día, fase y gravedad; perfil; enlace con Tierra y eventos."""
    info = status.get("mission") or {}
    items = []
    if info.get("mission_day") is not None:
        statement = i18n.tr(
            f"Día de misión {display.number(float(info['mission_day']), 1)} de "
            f"{display.number(float(info['duration_days']), 0)}, {info['phase_display']}, "
            f"{info['gravity_display']}.",
            f"Mission day {display.number(float(info['mission_day']), 1)} of "
            f"{display.number(float(info['duration_days']), 0)}, {info['phase_display']}, "
            f"{info['gravity_display']}.",
        )
    else:
        statement = i18n.tr(
            "Sin día de misión: no se puede situar el estado en la misión.",
            "No mission day: the status cannot be placed in the mission.",
        )
    profile = info.get("profile") or {}
    if profile:
        name = profile.get("display") if profile.get("known") else profile.get("unknown_text")
        items.append(_item(i18n.tr(
            f"Perfil de misión: {name} ({profile.get('note')}).",
            f"Mission profile: {name} ({profile.get('note')}).",
        )))
    comms = status.get("comms")
    no_delay = i18n.tr("Retardo con Tierra: sin dato.", "Delay with Earth: no data.")
    if comms:
        items.append(_item(i18n.tr(
            f"Retardo con Tierra: {comms['description']}.",
            f"Delay with Earth: {comms['description']}.",
        )))
    else:
        missing = next(
            (
                item for item in (status.get("monitoring") or {}).get("capabilities") or []
                if item.get("key") == "light-time" and not item.get("available")
            ),
            None,
        )
        items.append(_item(
            f"{no_delay} {missing['consequence']}"
            if missing and missing["consequence"]
            else no_delay
        ))
    link = (status.get("declared_link") or {}).get("sentence")
    if link:
        items.append(_item(str(link)))
    events = info.get("events") or []
    items.append(_item(i18n.tr(
        f"Eventos de misión declarados (EVA, bloques de trabajo, ubicación): "
        f"{display.number(len(events), 0)}.",
        f"Declared mission events (EVA, work blocks, location): "
        f"{display.number(len(events), 0)}.",
    )))
    return _answer(
        LAYERS[2], ANSWERED, statement, items,
        notes=[str(info["phase_basis"])] if info.get("phase_basis") else [],
        sources=[
            i18n.tr(
                f"{_STATUS} → mission (día, fase, gravedad, perfil y eventos declarados)",
                f"{_STATUS} → mission (day, phase, gravity, profile and declared events)",
            ),
            i18n.tr(
                f"{_STATUS} → comms, monitoring y declared_link (enlace con Tierra)",
                f"{_STATUS} → comms, monitoring and declared_link (link with Earth)",
            ),
        ],
    )


def countermeasure(status: Mapping[str, Any]) -> dict[str, Any]:
    """¿Qué puede hacerse ahora? Las recomendaciones con lo decidido, sus recursos, lo que se
    vuelve a medir y la respuesta previa; los seguimientos abiertos."""
    items = []
    for rec in status.get("recommendations") or []:
        parts = [str(rec["action"])]
        decision = (rec.get("decision") or {}).get("text")
        if decision:
            parts.append(str(decision))
        countermeasure_ = rec.get("countermeasure") or {}
        checks = countermeasure_.get("followup_checks_display") or []
        if checks and countermeasure_.get("followup_window_hours") is not None:
            parts.append(i18n.tr(
                f"Se vuelve a medir: {', '.join(checks)}, en "
                f"{display.number(float(countermeasure_['followup_window_hours']), 0)} h "
                f"({countermeasure_.get('followup_basis')}).",
                f"Measured again: {', '.join(checks)}, in "
                f"{display.number(float(countermeasure_['followup_window_hours']), 0)} h "
                f"({countermeasure_.get('followup_basis')}).",
            ))
        resources = (rec.get("resource_status") or {}).get("text")
        if resources:
            parts.append(str(resources))
        prior = (rec.get("prior_response") or {}).get("text")
        if prior:
            parts.append(str(prior))
        items.append(_item(" ".join(parts)))
    open_followups = [
        item for item in status.get("followups") or [] if item.get("state") != "closed"
    ]
    for item in open_followups:
        state = i18n.loc(_FOLLOW_UP_DISPLAY.get(str(item["state"]), str(item["state"])))
        text = i18n.tr(
            f"Seguimiento de «{item['countermeasure']['action']}»: {state}.",
            f"Follow-up of «{item['countermeasure']['action']}»: {state}.",
        )
        evaluation = (item.get("evaluation") or {}).get("text")
        items.append(_item(f"{text} {evaluation}" if evaluation else text))
    recommendations = len(status.get("recommendations") or [])
    if recommendations or open_followups:
        offered = _count_of(
            recommendations, ("recomendación", "recomendaciones"),
            ("recommendation", "recommendations"),
        )
        followed = _count_of(
            len(open_followups), ("seguimiento abierto", "seguimientos abiertos"),
            ("open follow-up", "open follow-ups"),
        )
        answer = i18n.tr(f"{offered} y {followed}.", f"{offered} and {followed}.")
    else:
        answer = i18n.tr(
            "Ninguna recomendación ni seguimiento abierto.",
            "No recommendation and no open follow-up.",
        )
    resources_summary = ((status.get("mission") or {}).get("available_resources") or {}).get(
        "summary"
    )
    notes = [NO_EFFECT_MODEL] + ([str(resources_summary)] if resources_summary else [])
    return _answer(
        LAYERS[3], ANSWERED if items else NOTHING, answer, items, notes,
        sources=[
            i18n.tr(
                f"{_STATUS} → recommendations (con decision, resource_status y prior_response)",
                f"{_STATUS} → recommendations (with decision, resource_status and "
                f"prior_response)",
            ),
            i18n.tr(
                f"{_STATUS} → followups y mission.available_resources",
                f"{_STATUS} → followups and mission.available_resources",
            ),
        ],
    )


def decision(status: Mapping[str, Any], waiting: Mapping[str, Any] | None) -> dict[str, Any]:
    """¿Qué necesita saber o hacer la tripulación, con qué confianza? Lo que espera a una persona
    —las alertas sin reconocer del estado y lo que lleva días esperando— y sobre qué se apoya el
    veredicto."""
    data = status.get("data") or {}
    notes = []
    if data.get("basis"):
        notes.append(f"El veredicto se apoya en: {data['basis']}.")
    if notes and i18n.current() == "en":
        # La misma nota, dicha en inglés (la de arriba es la única que hay hasta aquí).
        notes[-1] = f"The verdict rests on: {data['basis']}."
    quality = (data.get("quality") or {}).get("summary")
    if quality:
        notes.append(str(quality))
    for capability in (status.get("monitoring") or {}).get("capabilities") or []:
        # El retardo con Tierra ya lo dice la capa de misión: aquí no se repite.
        if capability.get("key") == "light-time":
            continue
        if not capability.get("available") and capability.get("consequence"):
            notes.append(i18n.tr(
                f"{capability['label']}, no disponible. {capability['consequence']}",
                f"{capability['label']}, not available. {capability['consequence']}",
            ))
    sources = [
        i18n.tr(
            f"{_STATUS} → alerts (las que nadie ha reconocido todavía)",
            f"{_STATUS} → alerts (those that no one has acknowledged yet)",
        ),
        i18n.tr(
            "GET /api/timeline/waiting → waiting e incongruences (lo que lleva días esperando)",
            "GET /api/timeline/waiting → waiting and incongruences (what has been waiting "
            "for days)",
        ),
        i18n.tr(
            f"{_STATUS} → data.basis, data.quality y monitoring (con qué confianza)",
            f"{_STATUS} → data.basis, data.quality and monitoring (with what confidence)",
        ),
    ]
    old = list((waiting or {}).get("waiting") or [])
    unacknowledged = [
        alert for alert in status.get("alerts") or [] if not alert.get("acknowledged")
    ]
    # `app/waiting.py` titula «Alerta <dominio> sin reconocer» la que lleva días así, con el
    # nombre del dominio: esa va una vez, con sus días y con el nivel de la alerta.
    by_title = {unacknowledged_title(alert["domain"]): alert for alert in unacknowledged}
    counted = {str(item["title"]) for item in old}

    def waited(item: Mapping[str, Any]) -> dict[str, Any]:
        days = _count_of(int(item["days"]), ("día", "días"), ("day", "days"))
        alert = by_title.get(str(item["title"]))
        if i18n.current() == "en":
            level = None if alert is None else alert.get("level")
            return _item(f"{item['title']}: waiting {days}.", level)
        return _item(
            f"{item['title']}: {days} esperando.", None if alert is None else alert.get("level")
        )

    items = [
        _item(f"{title}.", alert.get("level"))
        for title, alert in by_title.items()
        if title not in counted
    ] + [waited(item) for item in old] + [
        _item(i18n.tr(
            f"Dos informes no coinciden en {item['key']} ({item['sample']}).",
            f"Two reports do not agree on {item['key']} ({item['sample']}).",
        ))
        for item in (waiting or {}).get("incongruences") or []
    ]
    if waiting is None:
        alerts = _count_of(len(unacknowledged), ("alerta", "alertas"), ("alert", "alerts"))
        answer = i18n.tr(
            "No se pudo leer lo que lleva días esperando a una persona",
            "What has been waiting for a person for days could not be read",
        ) + (
            i18n.tr(f"; sin reconocer: {alerts}.", f"; unacknowledged: {alerts}.")
            if unacknowledged else "."
        )
        return _answer(LAYERS[4], UNAVAILABLE, answer, items, notes, sources)
    threshold = waiting.get("threshold_days")
    if threshold is not None:
        length = _count_of(int(threshold), ("día", "días"), ("day", "days"))
        since = i18n.tr(f"{length} o más", f"{length} or more")
    else:
        since = i18n.tr("días", "several days")
    parts = []
    if unacknowledged:
        parts.append(_count_of(
            len(unacknowledged), ("alerta sin reconocer", "alertas sin reconocer"),
            ("unacknowledged alert", "unacknowledged alerts"),
        ))
    if old:
        matters = _count_of(len(old), ("asunto", "asuntos"), ("matter", "matters"))
        parts.append(i18n.tr(f"{matters} con {since} de espera", f"{matters} waiting {since}"))
    if waiting.get("incongruences"):
        parts.append(_count_of(
            len(waiting["incongruences"]),
            ("par de informes que no coinciden", "pares de informes que no coinciden"),
            ("pair of reports that do not agree", "pairs of reports that do not agree"),
        ))
    answer = (
        i18n.tr(
            f"Espera a una persona: {'; '.join(parts)}.",
            f"Waiting for a person: {'; '.join(parts)}.",
        ) if parts
        else i18n.tr(
            f"Nada espera a una persona: ninguna alerta sin reconocer y nada con {since} de "
            f"espera.",
            f"Nothing is waiting for a person: no unacknowledged alert and nothing waiting "
            f"{since}.",
        )
    )
    return _answer(LAYERS[4], ANSWERED if items else NOTHING, answer, items, notes, sources)


def compose(
    status: Mapping[str, Any],
    crew: Mapping[str, Any] | None,
    waiting: Mapping[str, Any] | None,
    until: dt.datetime | None = None,
    radiation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Las cinco preguntas de §10 de un tripulante, cada una con su respuesta y su origen.

    `status` es la respuesta de `/api/status`; `crew`, la de `/api/crew` (o `None` si no la hay);
    `waiting`, la de `app/waiting.py` para ese mismo estado (o `None`); `radiation`, la del
    hábitat (`/api/habitat` → `radiation`, o `None`). Con `until` (Tierra), todos vienen ya
    cortados en ese instante, y la nota lo dice.
    """
    body = {
        "subject": status.get("subject"),
        "reference_time": (status.get("data") or {}).get("reference_time"),
        "until": until.isoformat() if until is not None else None,
        "rules_version": status.get("rules_version"),
        "source": i18n.loc(SOURCE),
        "note": NOTE if until is None else f"{NOTE} {GROUND_NOTE}",
        "questions": [
            human(status),
            habitat(status, crew, radiation),
            mission(status),
            countermeasure(status),
            decision(status, waiting),
        ],
    }
    if i18n.current() == "en":
        # La nota, con sus dos frases en inglés: la de siempre y, para Tierra, la del corte.
        body["note"] = (
            i18n.loc(NOTE) if until is None else f"{i18n.loc(NOTE)} {i18n.loc(GROUND_NOTE)}"
        )
    return body
