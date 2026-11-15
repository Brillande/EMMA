"""El vínculo sensor-tripulante, tal y como lo declara una persona.

POR QUÉ EXISTE
--------------
La especificación del equipo pone «sensor bindings» entre los campos del astronauta (§3). EMMA
no tenía nada: el sujeto de una lectura de wearable es el que dice la petición, y si la pasarela
de un reloj se configura con el tripulante equivocado, sus pulsaciones se archivan bajo otra
persona sin que nada lo señale.

LO QUE ES Y LO QUE NO ES
------------------------
**EMMA no comprueba quién lleva puesto un reloj.** No hay emparejamiento, ni biometría, ni una
clave por dispositivo. Lo que hay es lo mínimo que se puede afirmar sin inventar nada: una
persona declara en la consola «este dispositivo lo lleva este tripulante desde tal instante», y
esa declaración queda firmada en el registro. Todo lo que sale de aquí va rotulado «declarado
por una persona».

Sirve para una sola cosa: si llega una lectura de un dispositivo que consta vinculado a OTRO
tripulante, la respuesta de la ingesta lo dice. **La lectura entra igual** (decisión del
usuario, 2026-10-09: no se bloquea; quien decide es una persona). No entra en el análisis, no
mueve niveles ni alertas (invariante 5) y no es una regla de `rules_version`.

QUÉ ES «UN DISPOSITIVO»
-----------------------
Lo que la ingesta sabe distinguir, y nada más. Hasta esta pieza solo distinguía la FUENTE
(`wearable-ble`, `apple-health`, `google-fit`): con dos tripulantes y una sola fuente, EMMA no
puede distinguir sus relojes, y un vínculo de fuente entera solo tiene sentido si esa fuente la
usa una sola persona. Por eso las tres rutas de ingesta admiten un identificador de dispositivo
OPCIONAL, que pone quien envía (EMMA no lo lee de la trama ni del export: no viene en ellos).
Un vínculo es, entonces, de un identificador dentro de una fuente o, sin identificador, de las
lecturas de esa fuente que llegan sin él.

Una lectura con identificador se compara solo con el vínculo de ese identificador; una sin
identificador, solo con el de la fuente sin identificador. No se mezclan: lo declarado de un
reloj concreto no dice nada de otro.

UN DISPOSITIVO SIN VÍNCULO NO ES UN ERROR
-----------------------------------------
La mayoría de los datos de la demo vienen del simulador y casi nada está declarado. De lo no
declarado no se avisa: no hay nada con lo que comparar.

QUÉ DECLARACIÓN VALE, Y EN QUÉ INSTANTE
---------------------------------------
Una declaración vale desde su `since` en adelante, hasta que otra firmada después la sustituya
desde el suyo. El vínculo vigente es el de la última firmada. Desvincular es otra declaración;
no hay borrado. Una lectura antigua (un export trae meses) se juzga contra el vínculo que
valía en SU instante, no contra el de hoy: de las declaraciones del dispositivo con `since`
anterior o igual al instante de la lectura, manda la firmada más tarde.

PRIVACIDAD
----------
Un identificador de dispositivo puede ser un dato personal (una dirección MAC). Va en el
asiento firmado, que es donde tiene que constar, y en la respuesta a quien lo pregunta. No se
escribe en el log, y la crónica no lo repite.

EL AVISO, TAMBIÉN DESPUÉS DE LA INGESTA (decisión del usuario, 2026-10-13)
--------------------------------------------------------------------------
El aviso solo existía en la respuesta de la ingesta: quien abría la consola una hora después
veía esas lecturas como las demás. Ahora cada lectura firmada lleva, si quien envía lo puso, el
identificador de su dispositivo (`VitalObservation.device`), y `in_readings` rehace la misma
comparación sobre las lecturas recientes para que el estado lo diga. Sigue siendo descriptivo:
esas lecturas se analizan igual, y decidir si son de ese tripulante es de una persona. En el
estado el identificador va ABREVIADO (`device_short`): el estado lo leen más pantallas que el
panel de vínculos, que es donde está entero.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from app.core import display
from app.ingest.codes import get

if TYPE_CHECKING:
    from app.ingest.fhir import VitalObservation

# Las fuentes de wearable que la ingesta distingue hoy. No es un vocabulario de diseño: son las
# tres rutas que existen (`/api/wearable/ble`, `/api/import/apple-health` y
# `/api/import/google-fit`).
SOURCES: dict[str, str] = {
    "wearable-ble": "pulsómetro Bluetooth LE",
    "apple-health": "export de Apple Health",
    "google-fit": "datos de Google Fit",
}

BIND = "bind"
UNBIND = "unbind"
ACTIONS = (BIND, UNBIND)

# Un identificador es una etiqueta corta, no un texto libre: letras, cifras y `: . _ -`. Se
# guarda en minúsculas para que «AA:BB» y «aa:bb» no sean dos relojes.
MAX_DEVICE_LENGTH = 64
_DEVICE = re.compile(r"[a-z0-9][a-z0-9:._-]*")
MAX_CREW_LENGTH = 64

DECLARED_LABEL = "declarado por una persona"
DECLARED_NOTE = (
    "EMMA no comprueba quién lleva puesto un dispositivo. Esto es lo que una persona declaró "
    "en la consola, firmado en el registro."
)
DEVICE_BASIS = (
    "Un dispositivo es lo que la ingesta sabe distinguir: la fuente y, si quien envía lo pone, "
    "un identificador. EMMA no lo lee de la trama ni del export. Sin identificador, el vínculo "
    "es de la fuente entera: con dos tripulantes y una sola fuente, EMMA no puede distinguir "
    "sus relojes."
)
RULE = (
    "Una declaración vale desde su instante en adelante, hasta que otra firmada después la "
    "sustituya. Vale la última firmada por la consola; las anteriores se conservan. No hay "
    "borrado: desvincular o corregir es otra declaración."
)
SCOPE = (
    "El vínculo no bloquea ninguna lectura, no entra en el análisis y no mueve niveles ni "
    "alertas. Solo sirve para avisar, en la respuesta de la ingesta y en la calidad del dato "
    "del estado, de una lectura que llega "
    "para un tripulante desde un dispositivo que consta vinculado a otro. De un dispositivo sin "
    "vínculo declarado no se avisa."
)
WHOLE_SOURCE_DISPLAY = "sin identificador (la fuente entera)"


def device_key(device: str | None) -> str | None:
    """El identificador tal y como se guarda y se compara, o `None` si no hay.

    Lo usan la declaración y la ingesta: si cada una normalizara por su cuenta, un vínculo
    declarado nunca coincidiría con la lectura que tenía que señalar.
    """
    if device is None:
        return None
    key = device.strip().casefold()
    if not key:
        return None
    if len(key) > MAX_DEVICE_LENGTH or not _DEVICE.fullmatch(key):
        raise ValueError(
            "identificador de dispositivo no válido: hasta "
            f"{MAX_DEVICE_LENGTH} caracteres entre letras sin acento, cifras y : . _ -"
        )
    return key


def check(source: str, action: str, crew: str | None, device: str | None) -> str | None:
    """Lo que se puede firmar; devuelve el identificador normalizado.

    Lo usan la ruta y el almacén: nadie más escribe una declaración.
    """
    if source not in SOURCES:
        raise ValueError(f"fuente desconocida: {source}; una de {', '.join(SOURCES)}")
    if action not in ACTIONS:
        raise ValueError(f"acción desconocida: {action}; una de {', '.join(ACTIONS)}")
    if action == BIND:
        if crew is None or not crew.strip():
            raise ValueError("vincular exige decir a qué tripulante")
        if len(crew.strip()) > MAX_CREW_LENGTH:
            raise ValueError(f"tripulante de más de {MAX_CREW_LENGTH} caracteres")
    elif crew is not None:
        raise ValueError("desvincular no lleva tripulante: retira el vínculo que hubiera")
    return device_key(device)


def source_display(key: str) -> str:
    return SOURCES.get(key, key)


def device_display(device: str | None) -> str:
    return WHOLE_SOURCE_DISPLAY if device is None else device


def _instant(text: str) -> dt.datetime:
    moment = dt.datetime.fromisoformat(text)
    return (moment if moment.tzinfo else moment.replace(tzinfo=dt.UTC)).astimezone(dt.UTC)


def _scope(item: dict[str, Any]) -> tuple[str, str | None]:
    return item["source"], item.get("device")


def history(declarations: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada declaración, en el orden en que se firmó, con lo que constaba justo antes.

    `declarations` son los asientos tal y como los entrega el almacén. «Antes» es la
    declaración anterior del mismo dispositivo; sin ninguna, sin vínculo.
    """
    last: dict[tuple[str, str | None], str | None] = {}
    told: list[dict[str, Any]] = []
    for item in sorted(declarations, key=lambda entry: entry["ledger_index"]):
        scope = _scope(item)
        crew = item.get("crew") if item["action"] == BIND else None
        previous = last.get(scope)
        last[scope] = crew
        told.append({
            "source": item["source"],
            "source_display": source_display(item["source"]),
            "device": item.get("device"),
            "device_display": device_display(item.get("device")),
            "action": item["action"],
            "bound": crew is not None,
            "crew": crew,
            "previous_crew": previous,
            "changed": previous != crew,
            "since": item["since"],
            "note": item["note"] or None,
            "declared_by": item["declared_by"],
            "ledger_index": item["ledger_index"],
            "recorded": item["recorded"],
        })
    return told


def sentence(item: dict[str, Any]) -> str:
    """Una declaración de `history` en una frase, con su rótulo. La nota de la persona, al final.

    No repite el identificador del dispositivo: puede ser un dato personal, y la crónica se
    escribe en más sitios que la respuesta a quien lo pregunta.
    """
    which = (
        f"la fuente {item['source_display']} entera" if item["device"] is None
        else f"un dispositivo con identificador de la fuente {item['source_display']}"
    )
    if item["bound"]:
        before = (
            f"antes constaba {item['previous_crew']}" if item["previous_crew"] and item["changed"]
            else "sin cambio respecto a lo declarado antes" if not item["changed"]
            else "antes no constaba vínculo"
        )
        what = f"vinculado a {item['crew']} ({before}; {DECLARED_LABEL})"
    else:
        before = (
            f"antes constaba {item['previous_crew']}" if item["previous_crew"]
            else "no constaba vínculo"
        )
        what = f"vínculo retirado ({before}; {DECLARED_LABEL})"
    note = f"; nota: {item['note']}" if item["note"] else ""
    return f"vínculo sensor-tripulante de {which}: {what}{note}"


def in_force(
    declarations: Sequence[dict[str, Any]], source: str, device: str | None, at: dt.datetime
) -> dict[str, Any] | None:
    """La declaración que valía para ese dispositivo en ese instante, o `None`.

    De las del dispositivo con `since` anterior o igual al instante, la firmada más tarde. Si
    esa es una retirada, también es la que valía: se devuelve, y quien llama mira `action`.
    """
    moment = at.astimezone(dt.UTC)
    held = [
        item for item in declarations
        if _scope(item) == (source, device) and _instant(item["since"]) <= moment
    ]
    return max(held, key=lambda item: item["ledger_index"]) if held else None


def overview(declarations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Los vínculos vigentes, el historial y cómo leerlo.

    Vigente es la última declaración firmada de cada dispositivo, si vincula; un dispositivo
    cuya última declaración lo retira no sale entre los vigentes, y sigue en el historial.
    """
    told = history(declarations)
    latest: dict[tuple[str, str | None], dict[str, Any]] = {}
    count: dict[tuple[str, str | None], int] = {}
    for item in told:
        latest[_scope(item)] = item
        count[_scope(item)] = count.get(_scope(item), 0) + 1
    current = [
        {
            "source": item["source"],
            "source_display": item["source_display"],
            "device": item["device"],
            "device_display": item["device_display"],
            "crew": item["crew"],
            "since": item["since"],
            "note": item["note"],
            "declared_by": item["declared_by"],
            "declarations": count[scope],
            "ledger_index": item["ledger_index"],
            "recorded": item["recorded"],
        }
        for scope, item in sorted(latest.items(), key=lambda pair: (pair[0][0], pair[0][1] or ""))
        if item["bound"]
    ]
    # Lo que no se puede distinguir, dicho donde pasa: una fuente entera vinculada a alguien.
    for row in current:
        row["caveat"] = (
            "Vínculo de fuente entera: vale para las lecturas de esta fuente que llegan sin "
            "identificador. Si la usa más de un tripulante, EMMA no puede distinguir sus "
            "dispositivos." if row["device"] is None else None
        )
    return {
        "label": DECLARED_LABEL,
        "note": DECLARED_NOTE,
        "device_basis": DEVICE_BASIS,
        "rule": RULE,
        "scope": SCOPE,
        "whole_source_display": WHOLE_SOURCE_DISPLAY,
        "sources": [{"key": key, "display": name} for key, name in SOURCES.items()],
        "actions": list(ACTIONS),
        "bindings": current,
        "summary": (
            f"Dispositivos con vínculo declarado: {display.number(len(current), 0)}. De los "
            "demás no hay nada declarado, y eso no es un fallo: no se avisa de ellos."
        ),
        # Lo más reciente primero: es lo que se mira al abrir el panel.
        "history": told[::-1],
    }


def notice(
    declarations: Sequence[dict[str, Any]], source: str, device: str | None, subject: str,
    instants: Sequence[dt.datetime],
) -> dict[str, Any] | None:
    """El aviso de la ingesta, o `None` si no hay nada que decir.

    Cada lectura se juzga contra el vínculo que valía en su instante. Solo se avisa de las que
    llegan para un tripulante desde un dispositivo que entonces constaba vinculado a OTRO: sin
    vínculo, con el vínculo retirado o con el vínculo del propio tripulante, no hay aviso.
    Describe; no rechaza nada: quien llama ya ha registrado las lecturas.
    """
    others: dict[int, dict[str, Any]] = {}
    for at in instants:
        held = in_force(declarations, source, device, at)
        # Sin tripulante no hay con quien comparar (un asiento de vinculo sin `crew`).
        if held is None or held["action"] != BIND or held.get("crew") in (None, subject):
            continue
        row = others.setdefault(held["ledger_index"], {
            "crew": held["crew"], "since": held["since"], "declared_by": held["declared_by"],
            "ledger_index": held["ledger_index"], "readings": 0,
        })
        row["readings"] += 1
    if not others:
        return None
    bound_to = sorted(others.values(), key=lambda row: row["ledger_index"])
    mismatched = sum(row["readings"] for row in bound_to)
    which = (
        f"la fuente {source_display(source)}, sin identificador de dispositivo" if device is None
        else f"el dispositivo «{device}» de la fuente {source_display(source)}"
    )
    crews = "; ".join(
        f"{row['crew']} desde {row['since']} ({display.number(row['readings'], 0)} "
        f"{'lectura' if row['readings'] == 1 else 'lecturas'})"
        for row in bound_to
    )
    return {
        "kind": "bound-to-other-crew",
        "label": DECLARED_LABEL,
        "source": source,
        "source_display": source_display(source),
        "device": device,
        "device_display": device_display(device),
        "subject": subject,
        "readings": len(instants),
        "mismatched": mismatched,
        "bound_to": bound_to,
        # La lectura entra siempre: el aviso no decide nada.
        "accepted": True,
        "text": (
            f"Lecturas recibidas para {subject} desde {which}: "
            f"{display.number(mismatched, 0)} de {display.number(len(instants), 0)} son de un "
            f"instante en el que ese dispositivo constaba vinculado a otro tripulante ({crews}). "
            f"El vínculo es {DECLARED_LABEL}: EMMA no comprueba quién lo lleva puesto. Las "
            "lecturas se han registrado igual; si el vínculo o el envío no son correctos, lo "
            "valora una persona."
        ),
    }


def unavailable(source: str, device: str | None, subject: str, readings: int) -> dict[str, Any]:
    """Lo que se dice cuando el registro de vínculos no se puede leer con garantías.

    Las lecturas ya están registradas: esto no es un rechazo, es decir que no se ha comparado.
    """
    return {
        "kind": "not-checked",
        "label": DECLARED_LABEL,
        "source": source,
        "source_display": source_display(source),
        "device": device,
        "device_display": device_display(device),
        "subject": subject,
        "readings": readings,
        "mismatched": None,
        "bound_to": [],
        "accepted": True,
        "text": (
            "No se ha podido comparar con los vínculos declarados: algún asiento de vínculo "
            "no supera la comprobación de integridad del registro. Las lecturas se han "
            "registrado igual."
        ),
    }


# --------------------------------------------------------------------------- #
# El aviso sobre las lecturas ya firmadas (el estado y la consola)
# --------------------------------------------------------------------------- #

# Cuánto del identificador se enseña fuera del panel de vínculos. Diseño de EMMA: lo justo para
# distinguir dos relojes en una frase sin repetir una dirección entera.
SHORT_DEVICE_TAIL = 4
ANALYSED_ANYWAY = (
    "EMMA las analiza igual; decidir si son de este tripulante es de una persona."
)
SHORT_DEVICE_NOTE = (
    "El identificador del dispositivo se enseña abreviado; entero está en el panel de vínculos, "
    "en la declaración que se cita."
)


def device_short(device: str | None) -> str:
    """El identificador como se enseña en el estado: sus últimos caracteres, no entero."""
    if device is None:
        return WHOLE_SOURCE_DISPLAY
    if len(device) <= SHORT_DEVICE_TAIL:
        return device
    return f"…{device[-SHORT_DEVICE_TAIL:]}"


def _count(count: int, one: str, many: str) -> str:
    return f"{display.number(count, 0)} {one if count == 1 else many}"


def _day(instant: str) -> str:
    return f"{_instant(instant):%Y-%m-%d %H:%M} UTC"


def _group_text(group: dict[str, Any]) -> str:
    which = (
        f"la fuente {group['source_display']}, sin identificador de dispositivo"
        if group["whole_source"]
        else f"el dispositivo «{group['device_display']}» de la fuente {group['source_display']}"
    )
    indicators = ", ".join(
        f"{item['display_es']} ({display.number(item['readings'], 0)})"
        for item in group["indicators"]
    )
    return (
        f"{_count(group['readings'], 'lectura', 'lecturas')} desde {which}, que constaba "
        f"vinculado a {group['crew']} desde el {_day(group['since'])}: {indicators}; "
        f"la primera, del {_day(group['first'])}"
    )


def in_readings(
    declarations: Sequence[dict[str, Any]] | None,
    observations: Sequence[VitalObservation],
    subject: str,
    span: str,
) -> dict[str, Any]:
    """Lo que el estado dice de las lecturas recientes y los vínculos declarados.

    `observations` son las lecturas recientes de `subject`, ya analizadas; `span`, cómo se
    llama esa ventana («los últimos 2 días»). Cada lectura de una fuente de wearable se juzga
    contra el vínculo que valía en SU instante, igual que en la ingesta (`notice`): con su
    identificador si lo lleva firmado, y si no, contra el vínculo de la fuente entera.
    `declarations` a `None` es «el registro de vínculos no se pudo leer con garantías».

    Describe y nada más: no quita lecturas, no les baja la confianza y no devuelve nada que el
    análisis lea (invariante 5).
    """
    compared = [obs for obs in observations if obs.source in SOURCES]
    base: dict[str, Any] = {
        "label": DECLARED_LABEL,
        "readings": len(compared),
        "with_device": sum(1 for obs in compared if obs.device is not None),
        "mismatched": 0,
        "groups": [],
        "indicators": [],
        "since": None,
        "text": None,
        "analysis_note": None,
        "device_note": None,
    }
    if declarations is None:
        return {
            **base, "kind": "not-checked", "mismatched": None,
            "text": (
                "No se ha podido comparar las lecturas con los vínculos declarados: algún "
                "asiento de vínculo no supera la comprobación de integridad del registro."
            ),
        }
    if not declarations:
        # El caso normal: nadie ha declarado nada, y de lo no declarado no se avisa.
        return {**base, "kind": "none"}

    groups: dict[int, dict[str, Any]] = {}
    per_group: dict[int, dict[str, int]] = {}
    for obs in compared:
        held = in_force(declarations, obs.source, obs.device, obs.effective)
        # Sin vínculo, con el vínculo retirado o sin tripulante en el asiento no hay con quién
        # comparar; y el vínculo del propio tripulante no es un aviso.
        bound_to = held.get("crew") if held is not None and held["action"] == BIND else None
        if held is None or bound_to is None or bound_to == subject:
            continue
        at = obs.effective.astimezone(dt.UTC).isoformat()
        group = groups.setdefault(held["ledger_index"], {
            "source": obs.source,
            "source_display": source_display(obs.source),
            "whole_source": obs.device is None,
            "device_display": device_short(obs.device),
            "crew": held["crew"],
            "since": held["since"],
            "declared_by": held["declared_by"],
            "ledger_index": held["ledger_index"],
            "readings": 0,
            "first": at,
            "last": at,
        })
        group["readings"] += 1
        group["first"], group["last"] = min(group["first"], at), max(group["last"], at)
        counts = per_group.setdefault(held["ledger_index"], {})
        counts[obs.key] = counts.get(obs.key, 0) + 1
    if not groups:
        return {
            **base, "kind": "none",
            "text": (
                f"Ninguna lectura de {span} llegó desde un dispositivo que constara vinculado "
                f"a otro tripulante ({DECLARED_LABEL})."
            ),
        }

    told = sorted(groups.values(), key=lambda group: group["ledger_index"])
    overall: dict[str, int] = {}
    for group in told:
        counts = per_group[group["ledger_index"]]
        group["indicators"] = [
            {
                "key": key, "display": get(key).display,
                "display_es": get(key).display_es, "readings": counts[key],
            }
            for key in sorted(counts)
        ]
        group["text"] = _group_text(group)
        for key, count in counts.items():
            overall[key] = overall.get(key, 0) + count
    mismatched = sum(group["readings"] for group in told)
    return {
        **base,
        "kind": "bound-to-other-crew",
        "mismatched": mismatched,
        "groups": told,
        "indicators": [
            {
                "key": key, "display": get(key).display,
                "display_es": get(key).display_es, "readings": overall[key],
            }
            for key in sorted(overall)
        ],
        "since": min(group["first"] for group in told),
        "text": (
            f"{display.number(mismatched, 0)} de {_count(len(compared), 'lectura', 'lecturas')} "
            f"de wearable de {span} "
            f"{'llegó' if mismatched == 1 else 'llegaron'} para {subject} desde un dispositivo "
            f"que en su instante constaba vinculado a otro tripulante: "
            f"{'; '.join(group['text'] for group in told)}. El vínculo es {DECLARED_LABEL}: "
            f"EMMA no comprueba quién lo lleva puesto. {ANALYSED_ANYWAY}"
        ),
        "analysis_note": ANALYSED_ANYWAY,
        "device_note": SHORT_DEVICE_NOTE,
    }
