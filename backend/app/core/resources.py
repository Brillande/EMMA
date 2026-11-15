"""Los recursos de a bordo, tal y como los declara una persona.

POR QUÉ EXISTE
--------------
La especificación del equipo pone `available_resources` en el contexto de misión (§3) y
`resources` en cada contramedida (§3, §8); su base de conocimiento pide un «Countermeasure Twin
que conozca recursos» (H5). EMMA tenía la mitad: cada contramedida decía qué pide, en texto
libre, y nada decía si eso está a bordo. Una tarjeta que recomienda «repetir la ecografía» no
avisaba de que el ecógrafo constaba averiado desde hacía una semana.

LO QUE ES Y LO QUE NO ES
------------------------
**EMMA no lleva inventario.** No sabe qué hay a bordo, no cuenta unidades y no lee ningún
sistema de estiba. Lo que hay es lo mínimo que se puede afirmar sin inventar nada (decisión del
usuario, 2026-10-09):

* un VOCABULARIO CERRADO de recursos (`app/data/resources.json`), que sale de lo que ya
  nombraban las contramedidas de la biblioteca y de nada más: no es la lista de una nave ni de
  un botiquín, y no lleva cantidades;
* una declaración, hecha por una persona en la consola y firmada en el registro, de que un
  recurso está o no está disponible desde un instante.

TRES ESTADOS, NO DOS
--------------------
«Declarado no disponible», «declarado disponible» y «sin declarar». **Sin declarar no es
disponible**: es que EMMA no sabe. Es el caso por defecto —casi nada estará declarado— y se
enseña como dato ausente, nunca como un visto bueno. No existe un estado «sin declarar» que se
pueda firmar: se declara lo que se sabe.

NO DECIDE NADA
--------------
Lo declarado se pone AL LADO de cada recomendación: qué recursos pide y cuáles constan como no
disponibles o sin declarar. No quita una contramedida, no la reordena y no toca su urgencia,
ningún nivel ni ninguna alerta (invariante 5); el análisis no lo lee y no es una regla de
`rules_version`. Una contramedida a la que le falta un recurso se sigue ofreciendo, con el aviso:
si se puede hacer lo valora una persona (invariante 7).

QUÉ DECLARACIÓN VALE
--------------------
La última firmada por la consola para cada recurso. Se corrige declarando de nuevo; no hay
borrado y las anteriores se conservan. `since` es desde cuándo vale lo que se declara, según
quien lo declara; no decide cuál manda.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from app.core import display, i18n

VOCABULARY_PATH = Path(__file__).resolve().parents[1] / "data" / "resources.json"

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
UNDECLARED = "undeclared"
# Lo que una persona puede firmar. «Sin declarar» no se firma: es no haber dicho nada.
DECLARABLE = (AVAILABLE, UNAVAILABLE)
STATE_DISPLAY: dict[str, str] = {
    AVAILABLE: "declarado disponible",
    UNAVAILABLE: "declarado no disponible",
    UNDECLARED: "sin declarar",
}
# El inglés de los estados va aquí y no en el registro de `i18n.en`: «sin declarar» lo dicen
# también otros módulos, y una cadena tiene un solo inglés registrado.
_STATE_DISPLAY_EN: dict[str, str] = {
    AVAILABLE: "declared available",
    UNAVAILABLE: "declared unavailable",
    UNDECLARED: "undeclared",
}

DECLARED_LABEL = "declarado por una persona; EMMA no lleva inventario"
DECLARED_NOTE = (
    "EMMA no sabe qué hay a bordo: no lleva inventario ni cantidades. Esto es lo que una "
    "persona declaró en la consola, firmado en el registro."
)
UNDECLARED_NOTE = (
    "Sin declarar no es disponible: de un recurso del que nadie ha declarado nada, EMMA no sabe "
    "si está a bordo ni si funciona."
)
VOCABULARY_BASIS = (
    "El vocabulario es cerrado y sale de lo que nombran las contramedidas de la biblioteca: no "
    "es el inventario de una nave ni de un botiquín."
)
RULE = (
    "Vale la última declaración firmada por la consola para cada recurso; las anteriores se "
    "conservan. No hay borrado: se corrige declarando de nuevo."
)
SCOPE = (
    "Lo declarado no cambia qué se recomienda, ni el orden, ni la urgencia, y no mueve niveles "
    "ni alertas. Una contramedida a la que le falta un recurso se sigue ofreciendo, con el "
    "aviso al lado: si se puede hacer lo valora una persona."
)
i18n.en(DECLARED_LABEL, "declared by a person; EMMA keeps no inventory")
i18n.en(
    DECLARED_NOTE,
    "EMMA does not know what is on board: it keeps no inventory or quantities. This is what a "
    "person declared in the console, signed in the ledger.",
)
i18n.en(
    UNDECLARED_NOTE,
    "Undeclared is not available: of a resource nobody has declared anything about, EMMA does "
    "not know whether it is on board or whether it works.",
)
i18n.en(
    VOCABULARY_BASIS,
    "The vocabulary is closed and comes from what the countermeasures in the library name: it "
    "is not the inventory of a spacecraft or of a medical kit.",
)
i18n.en(
    RULE,
    "The last declaration signed by the console for each resource is the one in force; earlier "
    "ones are kept. Nothing is deleted: it is corrected by declaring again.",
)
i18n.en(
    SCOPE,
    "What is declared does not change what is recommended, nor the order, nor the urgency, and "
    "does not move levels or alerts. A countermeasure that lacks a resource is still offered, "
    "with the notice beside it: whether it can be done is for a person to judge.",
)

NONE_REQUIRED = "none-required"
ALL_AVAILABLE = "all-available"
SOME_UNDECLARED = "some-undeclared"
SOME_UNAVAILABLE = "some-unavailable"

_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class VocabularyError(ValueError):
    """El vocabulario de recursos no cumple su propio contrato: no se carga."""


@dataclass(frozen=True, slots=True)
class Resource:
    key: str
    name: str


def load_vocabulary(path: Path = VOCABULARY_PATH) -> dict[str, Resource]:
    """El vocabulario, validado. Una clave o un nombre repetidos harían dos recursos de uno."""
    raw = json.loads(path.read_text(encoding="utf-8")).get("resources")
    if not isinstance(raw, list) or not raw:
        raise VocabularyError("vocabulario de recursos vacío o sin lista `resources`")
    found: dict[str, Resource] = {}
    names: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"key", "name"}:
            raise VocabularyError("cada recurso del vocabulario es {key, name}, y nada más")
        key, name = item["key"], item["name"]
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise VocabularyError(f"clave de recurso no válida: {key!r}")
        if not isinstance(name, str) or not name.strip() or name != name.strip():
            raise VocabularyError(f"recurso {key}: nombre vacío o con espacios sobrantes")
        if key in found:
            raise VocabularyError(f"recurso {key}: clave repetida")
        if name.casefold() in names:
            raise VocabularyError(f"recurso {key}: nombre repetido ({name})")
        names.add(name.casefold())
        found[key] = Resource(key, name)
    return found


@cache
def vocabulary() -> dict[str, Resource]:
    return load_vocabulary()


def check(resource: str, state: str) -> None:
    """Lo que se puede firmar. Lo usan la ruta y el almacén: nadie más escribe una declaración."""
    if resource not in vocabulary():
        raise ValueError(
            f"recurso fuera del vocabulario: {resource}; solo se declara un recurso que "
            "alguna contramedida nombra"
        )
    if state not in DECLARABLE:
        raise ValueError(f"estado desconocido: {state}; uno de {', '.join(DECLARABLE)}")


def name_of(key: str) -> str:
    """El nombre del recurso en el idioma de la petición; el vocabulario no se traduce."""
    known = vocabulary().get(key)
    return shown(known.name) if known is not None else key


def shown(text: str) -> str:
    """Un nombre del vocabulario en el idioma de la petición. Vale también para el texto con que
    una contramedida nombra un recurso cuando es ese mismo nombre; otro texto se queda como lo dé
    la biblioteca, que es quien lo traduce.
    """
    return i18n.localized(text, VOCABULARY_PATH)


def state_display(state: str) -> str:
    """La palabra de un estado; uno que no está en el vocabulario, tal cual se firmó."""
    return i18n.tr(STATE_DISPLAY.get(state, state), _STATE_DISPLAY_EN.get(state, state))


def visible(
    declarations: Sequence[dict[str, Any]], until: dt.datetime | None
) -> list[dict[str, Any]]:
    """Lo que Tierra puede tener en su corte: nada que valga desde un instante posterior."""
    if until is None:
        return list(declarations)
    return [
        item for item in declarations if dt.datetime.fromisoformat(item["since"]) <= until
    ]


def history(declarations: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada declaración, en el orden en que se firmó, con lo que constaba justo antes.

    `declarations` son los asientos tal y como los entrega el almacén. «Antes» es la
    declaración anterior del mismo recurso; sin ninguna, sin declarar.
    """
    last: dict[str, str] = {}
    told: list[dict[str, Any]] = []
    for item in sorted(declarations, key=lambda entry: entry["ledger_index"]):
        previous = last.get(item["resource"], UNDECLARED)
        last[item["resource"]] = item["state"]
        told.append({
            "resource": item["resource"],
            "name": name_of(item["resource"]),
            "state": item["state"],
            "state_display": state_display(item["state"]),
            "previous_state": previous,
            "previous_state_display": state_display(previous),
            "changed": previous != item["state"],
            "since": item["since"],
            "note": item["note"] or None,
            "declared_by": item["declared_by"],
            "ledger_index": item["ledger_index"],
            "recorded": item["recorded"],
        })
    return told


def sentence(item: dict[str, Any]) -> str:
    """Una declaración de `history` en una frase, con su rótulo. La nota de la persona, al final."""
    before = (
        i18n.tr(
            f"antes constaba {item['previous_state_display']}",
            f"previously on record as {item['previous_state_display']}",
        )
        if item["changed"]
        else i18n.tr(
            "sin cambio respecto a lo declarado antes", "no change from what was declared before"
        )
    )
    note = (
        i18n.tr(f"; nota: {item['note']}", f"; note: {item['note']}") if item["note"] else ""
    )
    label = i18n.loc(DECLARED_LABEL)
    return i18n.tr(
        f"recurso «{item['name']}»: {item['state_display']} ({before}; {label}){note}",
        f"resource «{item['name']}»: {item['state_display']} ({before}; {label}){note}",
    )


def in_force(declarations: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """La declaración vigente de cada recurso declarado: la última firmada."""
    return {item["resource"]: item for item in history(declarations)}


def _row(key: str, held: dict[str, Any] | None) -> dict[str, Any]:
    """Un recurso con su estado. Sin declaración, «sin declarar»: nunca disponible por defecto."""
    state = held["state"] if held is not None else UNDECLARED
    return {
        "key": key,
        "name": name_of(key),
        "state": state,
        "state_display": state_display(state),
        "since": held["since"] if held is not None else None,
        "note": held["note"] if held is not None else None,
        "declared_by": held["declared_by"] if held is not None else None,
        "ledger_index": held["ledger_index"] if held is not None else None,
        "recorded": held["recorded"] if held is not None else None,
    }


def available(declarations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """`available_resources` del contexto de misión: lo declarado vigente, con su rótulo.

    Solo lo que una persona declaró. De lo demás no se da una lista de «disponibles»: se dice
    cuántos recursos del vocabulario están sin declarar, y que eso no es un visto bueno.
    """
    held = in_force(declarations)
    declared = [_row(key, held[key]) for key in vocabulary() if key in held]
    # Un asiento antiguo de un recurso que ya no esté en el vocabulario sigue constando.
    declared += [_row(key, item) for key, item in held.items() if key not in vocabulary()]
    undeclared = sum(1 for key in vocabulary() if key not in held)
    figures = (
        display.number(len(declared), 0),
        display.number(sum(1 for row in declared if row["state"] == UNAVAILABLE), 0),
        display.number(undeclared, 0),
    )
    return {
        "label": i18n.loc(DECLARED_LABEL),
        "note": i18n.loc(DECLARED_NOTE),
        "undeclared_note": i18n.loc(UNDECLARED_NOTE),
        "declared": declared,
        "available": [row["key"] for row in declared if row["state"] == AVAILABLE],
        "unavailable": [row["key"] for row in declared if row["state"] == UNAVAILABLE],
        "undeclared_count": undeclared,
        "summary": i18n.tr(
            f"Recursos declarados: {figures[0]} ({figures[1]} no disponibles). Sin declarar: "
            f"{figures[2]}; de esos EMMA no sabe si están a bordo.",
            f"Declared resources: {figures[0]} ({figures[1]} unavailable). Undeclared: "
            f"{figures[2]}; of those EMMA does not know whether they are on board.",
        ),
    }


def describe(
    countermeasure: Mapping[str, Any], declarations: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Qué recursos pide una contramedida y cómo consta cada uno. Describe; no decide nada.

    `countermeasure` es la contramedida tal y como la publica la biblioteca (`to_dict`): sus
    claves y, al lado, el texto con que ella nombra cada recurso, que se conserva.
    """
    held = in_force(declarations)
    keys = list(countermeasure.get("resource_keys") or ())
    texts = list(countermeasure.get("resources") or ())
    items = [
        {**_row(key, held.get(key)), "description": shown(text)}
        for key, text in zip(keys, texts, strict=True)
    ]
    unavailable = [item["description"] for item in items if item["state"] == UNAVAILABLE]
    undeclared = [item["description"] for item in items if item["state"] == UNDECLARED]
    if not items:
        state = NONE_REQUIRED
        text = i18n.tr("No pide recursos.", "It asks for no resources.")
    elif unavailable:
        state = SOME_UNAVAILABLE
        text = i18n.tr(
            f"Consta como no disponible: {'; '.join(unavailable)}.",
            f"On record as unavailable: {'; '.join(unavailable)}.",
        )
        if undeclared:
            text += i18n.tr(
                f" Sin declarar: {'; '.join(undeclared)}.",
                f" Undeclared: {'; '.join(undeclared)}.",
            )
    elif undeclared:
        state = SOME_UNDECLARED
        text = i18n.tr(
            f"Sin declarar: {'; '.join(undeclared)}.", f"Undeclared: {'; '.join(undeclared)}."
        )
    else:
        state = ALL_AVAILABLE
        text = i18n.tr(
            "Todos los recursos que pide constan declarados disponibles.",
            "All the resources it asks for are on record as declared available.",
        )
    return {
        "state": state,
        "label": i18n.loc(DECLARED_LABEL),
        "items": items,
        "unavailable": unavailable,
        "undeclared": undeclared,
        "text": text,
        # Va siempre que haya algo que leer mal: lo ausente no es un visto bueno, y el aviso
        # no retira la contramedida.
        "caveat": (
            None if state in (NONE_REQUIRED, ALL_AVAILABLE)
            else i18n.tr(
                f"{UNDECLARED_NOTE} La contramedida se ofrece igual: si se puede hacer lo "
                "valora una persona.",
                f"{i18n.loc(UNDECLARED_NOTE)} The countermeasure is offered all the same: "
                "whether it can be done is for a person to judge.",
            )
        ),
    }


def with_resources(
    recommendations: Sequence[dict[str, Any]], declarations: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Cada recomendación con el estado de los recursos de su contramedida, o `None` sin ella.

    Solo AÑADE el campo `resource_status`: ni quita, ni reordena, ni toca la urgencia.
    """
    annotated: list[dict[str, Any]] = []
    for item in recommendations:
        measure = item.get("countermeasure")
        annotated.append({
            **item,
            "resource_status": describe(measure, declarations) if measure else None,
        })
    return annotated


def overview(
    declarations: Sequence[dict[str, Any]], used_by: Mapping[str, Sequence[str]]
) -> dict[str, Any]:
    """Todo el vocabulario con su estado, el historial y cómo leerlo.

    `used_by` dice qué contramedidas nombran cada recurso (lo da la biblioteca; este módulo no
    la importa).
    """
    held = in_force(declarations)
    told = history(declarations)
    count: dict[str, int] = {}
    for item in told:
        count[item["resource"]] = count.get(item["resource"], 0) + 1
    rows = [
        {**_row(key, held.get(key)), "declarations": count.get(key, 0),
         "used_by": list(used_by.get(key, ()))}
        for key in vocabulary()
    ]
    return {
        **available(declarations),
        "vocabulary_basis": i18n.loc(VOCABULARY_BASIS),
        "rule": i18n.loc(RULE),
        "scope": i18n.loc(SCOPE),
        "states": [{"key": key, "display": state_display(key)} for key in DECLARABLE],
        "undeclared_display": state_display(UNDECLARED),
        "resources": rows,
        # Lo más reciente primero: es lo que se mira al abrir el panel.
        "history": told[::-1],
    }
