"""El enlace con Tierra simulado: el corte de Tierra con el enlace caído y lo pendiente de enviar.

POR QUÉ EXISTE
--------------
La consola de Tierra enseña lo que había a bordo hace un tiempo de luz (`groundCut` en la
interfaz). Eso supone que el enlace está siempre arriba. La conversación de ideación pide además
«pérdida de comunicaciones» entre las variables de misión, y el ideograma del usuario (P3,
«Sincronizar con enlace roto», idea 10 de `docs/contexto/prioridades-evento.md`) pide la
sincronización diferida. Con el enlace caído, Tierra deja de recibir. Lo firmado a bordo mientras
tanto no se pierde: espera en el registro y, al volver el enlace, llega a Tierra en el orden en que
se firmó. Sin esto, la consola de Tierra seguía avanzando con el enlace declarado caído.

QUÉ ES, Y POR QUÉ NO ES LA DECLARACIÓN DEL SISTEMA «COMUNICACIONES»
-------------------------------------------------------------------
Es un asiento propio (`simulated-link`, `record-integrity.md` §3.29) que firma una persona desde la
consola de a bordo: «enlace con Tierra simulado: caído» o «restablecido», desde un instante. **No**
es la declaración del sistema Comunicaciones (`environment/systems.py`). Esa sigue siendo solo
texto, por decisión del usuario del 2026-10-21, y nada la lee para cortar. Unificar las dos es una
decisión pendiente del usuario. Hasta entonces pueden discrepar, y cada una dice lo que es.

EMMA no mide el enlace. En este prototipo no hay enlace: las dos consolas corren en la misma
máquina y leen el mismo registro. Esto simula el efecto de un enlace caído sobre lo que Tierra
puede tener, y no lo transporta.

QUIÉN LO LEE, Y QUIÉN NO
------------------------
Solo dos cosas lo leen: el corte de Tierra (`ground_cut`) y la cola de lo pendiente (`backlog`).
No lo leen el riesgo ni su factor de aislamiento, que sale del tiempo de luz de las efemérides.
Tampoco las alertas, las recomendaciones ni `notify_ground`. `analysis/` y `advisor/` no importan
este módulo, y `tests/test_link_sync.py` lo comprueba (invariante 5).

LA CUENTA
---------
Los instantes son los de los datos: el de cada lectura y, para las acciones, la hora de su firma.
Es la misma regla con que la consola corta hoy lo que pide. `L` es el corte por tiempo de luz (la
hora de a bordo menos el retardo de un sentido; sin efemérides no hay `L` y vale «todo»). Un corte
del enlace es un tramo `[caído, restablecido)`. Lo firmado en el instante de la caída ya salió;
lo posterior espera.

    corte = inicio del tramo que contiene `L`, si lo hay; si no, `L`.

Con el enlace arriba, todo lo anterior a `L` ha llegado: lo retenido salió al restablecerse y ya
viajó su tiempo de luz. Con `L` dentro de un corte, Tierra tiene solo hasta su inicio. El corte de
Tierra **nunca queda por delante del último instante con enlace**, y como los tramos van en orden,
lo retenido aparece de golpe y entero al pasar `L` el restablecimiento: no se salta ni se reordena
nada.

Los tramos van en orden porque el almacén lo exige. Un cambio no puede referirse a un instante
anterior al del último cambio, y el estado vigente no se repite. Sin ningún asiento el enlace está
arriba, que es lo que la consola de Tierra ha supuesto siempre.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from app.core import display, i18n
from app.core.identities import CONSOLE_IDENTITY

DOWN = "down"
UP = "up"
STATES = (DOWN, UP)
STATE_DISPLAY = {DOWN: "caído", UP: "restablecido"}
# El inglés va en una tabla propia y no en el registro de `i18n.en`: «caído» lo pueden decir
# otros módulos con otro inglés, y una cadena tiene un solo inglés registrado.
_STATE_DISPLAY_EN = {DOWN: "down", UP: "restored"}

# La identidad con que firma la consola de Tierra (`routes.GROUND_IDENTITY`): lo que firma Tierra
# sube; no está a bordo esperando a bajar y no cuenta como pendiente.
GROUND_SIGNER = "ground-console"

LABEL = "Enlace con Tierra simulado (declarado por una persona)"
NOT_MEASURED = (
    "EMMA no mide el enlace: lo declara una persona a bordo. En este prototipo las dos consolas "
    "corren en la misma máquina y no hay enlace real; esto simula lo que Tierra puede tener."
)
RULE = (
    "Tierra tiene lo firmado a bordo hasta el tiempo de luz, salvo que ese instante caiga con el "
    "enlace caído: entonces, hasta la caída. Lo firmado mientras tanto espera a bordo y, al "
    "restablecerse, llega a Tierra un tiempo de luz después, en el orden en que se firmó. No se "
    "pierde nada."
)
NOT_READ_BY = (
    "Solo lo leen el corte de Tierra y esta cola. El riesgo y su factor de aislamiento, las "
    "alertas, las recomendaciones y el aviso a Tierra no lo leen. La declaración del sistema "
    "Comunicaciones sigue siendo solo texto (decisión del usuario del 2026-10-21); unificar las "
    "dos es una decisión pendiente del usuario."
)
KNOWN_ONLY_HERE = (
    "En una misión real Tierra no sabría cuántos asientos le faltan: aquí lo sabe porque las dos "
    "consolas leen el mismo registro."
)
INSTANT_BASIS = (
    "El instante de una lectura es su hora; el de cualquier otro asiento, la hora de su firma. Es "
    "la misma regla con que la consola de Tierra pide lo que ha llegado."
)
i18n.en(LABEL, "Simulated link with Earth (declared by a person)")
i18n.en(
    NOT_MEASURED,
    "EMMA does not measure the link: a person on board declares it. In this prototype the two "
    "consoles run on the same machine and there is no real link; this simulates what Earth may "
    "have.",
)
i18n.en(
    RULE,
    "Earth has what was signed on board up to the light time, unless that instant falls while "
    "the link is down: then, up to the drop. What is signed in the meantime waits on board and, "
    "once the link is restored, reaches Earth one light time later, in the order in which it "
    "was signed. Nothing is lost.",
)
i18n.en(
    NOT_READ_BY,
    "Only the Earth cut and this queue read it. The risk and its isolation factor, the alerts, "
    "the recommendations and the notice to Earth do not read it. The declaration of the "
    "Communications system is still text only (user decision of 2026-10-21); unifying the two "
    "is a decision pending from the user.",
)
i18n.en(
    KNOWN_ONLY_HERE,
    "In a real mission Earth would not know how many entries it is missing: here it knows "
    "because the two consoles read the same ledger.",
)
i18n.en(
    INSTANT_BASIS,
    "The instant of a reading is its time; that of any other entry, the time it was signed. It "
    "is the same rule with which the Earth console asks for what has arrived.",
)


class LinkConflict(ValueError):
    """El cambio choca con lo ya firmado: repite el estado vigente o va hacia atrás (un 409)."""


def _at(item: dict[str, Any]) -> dt.datetime:
    return dt.datetime.fromisoformat(item["at"])


def _utc(moment: dt.datetime) -> str:
    return f"{moment.astimezone(dt.UTC):%Y-%m-%d %H:%M} UTC"


def transitions(entries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Los cambios que cuentan, en orden de firma: solo los de la consola de a bordo."""
    return sorted(
        (item for item in entries if item.get("signer") == CONSOLE_IDENTITY),
        key=lambda item: item["ledger_index"],
    )


def current_state(changes: Sequence[dict[str, Any]]) -> str:
    """El estado vigente: el del último cambio. Sin ninguno, arriba."""
    return str(changes[-1]["state"]) if changes else UP


def check_change(
    changes: Sequence[dict[str, Any]], state: str, at: dt.datetime, declared_by: str
) -> None:
    """Lo que se puede firmar, o `ValueError` con el motivo. El almacén lo aplica bajo su cerrojo.

    Un dato malo (estado desconocido, instante sin zona, firmante sin nombre) es `ValueError`; lo
    que choca con lo ya firmado, `LinkConflict`.
    """
    if state not in STATES:
        raise ValueError(f"estado del enlace desconocido: {state}; uno de {', '.join(STATES)}")
    if at.tzinfo is None:
        raise ValueError("el instante del cambio debe llevar zona horaria")
    if not any(char.isalpha() for char in declared_by):
        raise ValueError("el enlace simulado lo declara una persona con nombre")
    if state == current_state(changes):
        raise LinkConflict(f"el enlace simulado ya está {STATE_DISPLAY[state]}")
    if changes and at < _at(changes[-1]):
        raise LinkConflict(
            "el cambio no puede referirse a un instante anterior al del último cambio "
            f"({_utc(_at(changes[-1]))}): los tramos del enlace van en orden"
        )


def outages(changes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Los tramos con el enlace caído, en orden: `start`, `end` (None si sigue caído), asientos."""
    spans: list[dict[str, Any]] = []
    for item in changes:
        if item["state"] == DOWN:
            spans.append({"start": _at(item), "end": None, "down": item, "up": None})
        elif spans and spans[-1]["end"] is None:
            spans[-1]["end"] = _at(item)
            spans[-1]["up"] = item
    return spans


def holding(
    light_cut: dt.datetime | None, changes: Sequence[dict[str, Any]]
) -> dict[str, Any] | None:
    """El tramo caído que contiene el corte por tiempo de luz, si lo hay.

    Sin efemérides (`light_cut` None) no hay retardo y el corte sería «todo». Solo lo retiene un
    corte que siga abierto.
    """
    for span in outages(changes):
        if light_cut is None:
            if span["end"] is None:
                return span
            continue
        if span["start"] <= light_cut and (span["end"] is None or span["end"] > light_cut):
            return span
    return None


def ground_cut(
    light_cut: dt.datetime | None, changes: Sequence[dict[str, Any]]
) -> dt.datetime | None:
    """Hasta dónde tiene Tierra: el inicio del corte que retiene `light_cut`, o `light_cut`.

    `None` es «todo lo de a bordo» (sin efemérides y con el enlace arriba). Nunca queda por delante
    de `light_cut` ni del último instante con enlace.
    """
    span = holding(light_cut, changes)
    if span is None:
        return light_cut
    start: dt.datetime = span["start"]
    return start if light_cut is None else min(light_cut, start)


def backlog(
    instants: Sequence[dict[str, Any]], after: dt.datetime | None
) -> dict[str, Any]:
    """Los asientos de a bordo posteriores a `after`, en orden; con `after` None, ninguno.

    `instants` son los de `ObservationStore.ledger_instants`. Lo que firma Tierra no cuenta: sube,
    no baja. El orden es el del instante y, a igualdad, el de la firma, que es el orden en que
    Tierra los verá aparecer.
    """
    if after is None:
        waiting: list[dict[str, Any]] = []
    else:
        waiting = sorted(
            (
                item for item in instants
                if item["signer"] != GROUND_SIGNER
                and dt.datetime.fromisoformat(item["instant"]) > after
            ),
            key=lambda item: (dt.datetime.fromisoformat(item["instant"]), item["index"]),
        )
    readings = sum(1 for item in waiting if item["basis"] == "effective")
    return {
        "count": len(waiting),
        "readings": readings,
        "other": len(waiting) - readings,
        "first": waiting[0]["instant"] if waiting else None,
        "last": waiting[-1]["instant"] if waiting else None,
        "first_index": waiting[0]["index"] if waiting else None,
    }


def _entries_phrase(count: int) -> str:
    return i18n.tr(
        f"{display.number(count, 0)} asiento{'' if count == 1 else 's'}",
        f"{display.number(count, 0)} {'entry' if count == 1 else 'entries'}",
    )


def view(
    entries: Sequence[dict[str, Any]],
    instants: Sequence[dict[str, Any]],
    light_cut: dt.datetime | None,
) -> dict[str, Any]:
    """El enlace simulado, el corte de Tierra y lo pendiente, con las frases que lo dicen.

    `to_send` es lo que espera a bordo (la consola de tripulación: «pendiente de enviar»): con el
    enlace caído ahora, lo firmado después de la caída. `to_arrive` es lo que le falta a Tierra
    respecto de a bordo (la consola de Tierra: «faltan N por llegar»), lo retenido y lo que va de
    camino. Las frases las compone este módulo; la interfaz no las redacta.
    """
    changes = transitions(entries)
    state = current_state(changes)
    last = changes[-1] if changes else None
    spans = outages(changes)
    open_span = spans[-1] if spans and spans[-1]["end"] is None else None
    held = holding(light_cut, changes)
    cut = ground_cut(light_cut, changes)
    to_send = backlog(instants, open_span["start"] if open_span is not None else None)
    to_arrive = backlog(instants, cut)

    if open_span is not None:
        who = open_span["down"]["declared_by"]
        pending = (
            i18n.tr(
                f"{_entries_phrase(to_send['count'])} "
                f"pendiente{'' if to_send['count'] == 1 else 's'} de enviar a Tierra desde "
                f"{_utc(dt.datetime.fromisoformat(to_send['first']))}",
                f"{_entries_phrase(to_send['count'])} waiting to be sent to Earth since "
                f"{_utc(dt.datetime.fromisoformat(to_send['first']))}",
            )
            if to_send["count"]
            else i18n.tr("Nada pendiente de enviar todavía", "Nothing waiting to be sent yet")
        )
        crew = i18n.tr(
            f"Enlace con Tierra simulado caído desde {_utc(open_span['start'])}, declarado por "
            f"{who}. {pending}. Se envían en el orden en que se firmaron cuando se declare "
            "restablecido; no se pierde nada.",
            f"Simulated link with Earth down since {_utc(open_span['start'])}, declared by "
            f"{who}. {pending}. They are sent in the order in which they were signed once it is "
            "declared restored; nothing is lost.",
        )
    elif last is not None:
        crew = i18n.tr(
            f"Enlace con Tierra simulado restablecido desde {_utc(_at(last))}, declarado por "
            f"{last['declared_by']}. Nada pendiente de enviar: lo firmado a bordo sale al "
            "firmarse.",
            f"Simulated link with Earth restored since {_utc(_at(last))}, declared by "
            f"{last['declared_by']}. Nothing waiting to be sent: what is signed on board "
            "leaves when it is signed.",
        )
    else:
        crew = i18n.tr(
            "Nadie ha declarado caído el enlace con Tierra simulado: está arriba, como ha supuesto "
            "siempre la consola de Tierra. Nada pendiente de enviar.",
            "Nobody has declared the simulated link with Earth down: it is up, as the Earth "
            "console has always assumed. Nothing waiting to be sent.",
        )

    if cut is None:
        ground = i18n.tr(
            "Tierra tiene todo lo de a bordo: sin efemérides no hay retardo y el enlace está "
            "arriba.",
            "Earth has everything from on board: without ephemerides there is no delay and the "
            "link is up.",
        )
    elif held is not None:
        back = (
            i18n.tr(
                f" Se restableció el {_utc(held['end'])}; lo retenido llega a Tierra un tiempo de "
                "luz después, en el orden en que se firmó.",
                f" It was restored on {_utc(held['end'])}; what was held reaches Earth one light "
                "time later, in the order in which it was signed.",
            )
            if held["end"] is not None else ""
        )
        ground = i18n.tr(
            f"Tierra tiene datos hasta {_utc(cut)}: entonces se declaró caído el enlace simulado. "
            f"Faltan {_entries_phrase(to_arrive['count'])} por llegar.{back}",
            f"Earth has data up to {_utc(cut)}: the simulated link was declared down then. "
            f"{_entries_phrase(to_arrive['count'])} still to arrive.{back}",
        )
    else:
        ground = i18n.tr(
            f"Tierra tiene datos hasta {_utc(cut)}, un tiempo de luz por detrás de a bordo. Faltan "
            f"{_entries_phrase(to_arrive['count'])} por llegar: van de camino.",
            f"Earth has data up to {_utc(cut)}, one light time behind on board. "
            f"{_entries_phrase(to_arrive['count'])} still to arrive: on the way.",
        )

    return {
        "label": i18n.loc(LABEL),
        "state": state,
        "state_display": i18n.tr(
            "caído" if state == DOWN else "arriba", "down" if state == DOWN else "up"
        ),
        "declared": last is not None,
        "since": last["at"] if last is not None else None,
        "declared_by": last["declared_by"] if last is not None else None,
        "note": (last["note"] or None) if last is not None else None,
        "ledger_index": last["ledger_index"] if last is not None else None,
        "light_cut": light_cut.isoformat() if light_cut is not None else None,
        "cut": cut.isoformat() if cut is not None else None,
        "held": held is not None,
        "held_since": held["start"].isoformat() if held is not None else None,
        "to_send": to_send,
        "to_arrive": to_arrive,
        "crew_sentence": crew,
        "ground_sentence": ground,
        "rule": i18n.loc(RULE),
        "not_measured": i18n.loc(NOT_MEASURED),
        "not_read_by": i18n.loc(NOT_READ_BY),
        "known_only_here": i18n.loc(KNOWN_ONLY_HERE),
        "instant_basis": i18n.loc(INSTANT_BASIS),
        # Lo más reciente primero, como el historial de los sistemas.
        "history": [
            {
                "state": item["state"],
                "state_display": i18n.tr(
                    STATE_DISPLAY[item["state"]], _STATE_DISPLAY_EN[item["state"]]
                ),
                "at": item["at"], "note": item["note"] or None,
                "declared_by": item["declared_by"], "ledger_index": item["ledger_index"],
                "recorded": item["recorded"],
            }
            for item in reversed(changes)
        ],
        "version": len(entries),
    }
