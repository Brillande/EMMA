"""El estado de los sistemas del hábitat, tal y como lo declara una persona.

POR QUÉ EXISTE
--------------
La especificación del equipo pone `system_status` entre los campos de `HabitatState` (§3) y
cita los sistemas del hábitat como telemetría de contexto (§16). EMMA no tenía nada: si el
sistema que retira el CO2 llevaba un día degradado, quien abría una alerta de fatiga veía la
excursión de CO2 y no veía que alguien ya sabía por qué.

LO QUE ES Y LO QUE NO ES
------------------------
**EMMA no lee el estado de ningún sistema.** No hay telemetría de sistemas, ni un modelo de una
nave concreta del que sacarla. Lo que hay es lo mínimo que se puede afirmar sin inventar nada:
una persona declara en la consola «este sistema está así», y esa declaración queda firmada en
el registro, como ya se hace con la ubicación por módulo. Todo lo que sale de aquí va rotulado
«declarado por una persona, no telemetría».

Es descriptivo. No entra en ninguna puntuación, no mueve niveles, alertas ni excursiones
(invariante 5) y no es una regla de `rules_version`: `analysis/risk.py`, `baseline.py` y
`trend.py` no importan este módulo.

EL VOCABULARIO ES DE DISEÑO, Y LO DICE
--------------------------------------
Los sistemas y los estados son una lista cerrada en `data/habitat_systems.json`. No se ha leído
de ninguna nave: es una partición funcional mínima y el fichero la rotula «vocabulario de
diseño de EMMA». Hasta la decimocuarta ronda decía además «sin respaldo bibliográfico»; desde
entonces su base dice qué funciones nombra el resumen técnico del ECLSS (OCHMO-TB-002) y cómo
las agrupa él, y qué hace el control térmico de la ISS (ATCS), con sus dos fichas del registro
de evidencia en `basis_refs`. Una base que cite una ficha que no está en el registro no carga:
la cita tiene que poder abrirse. La relación de un sistema con un parámetro de cabina solo se
declara cuando es de definición (el sistema que retira el CO2 y el CO2): no es conocimiento
médico ni una hipótesis de causa, y ningún análisis la usa.

«SIN DECLARAR» NO ES «NOMINAL»
------------------------------
Un sistema del que nadie ha dicho nada no está bien: no se sabe. Por eso el estado por defecto
es uno propio, que no se puede declarar (nadie firma «no lo sé») y que la interfaz pinta como
dato ausente.

QUÉ DECLARACIÓN VALE
--------------------
De cada sistema y módulo vale el último asiento firmado; los anteriores se conservan. No hay
borrado: una declaración equivocada se corrige declarando de nuevo. «Desde cuándo» es el
instante al que se refiere la primera declaración seguida del estado vigente —quien confirma
dos días después que sigue degradado no reinicia la cuenta—, y es el instante que dijo una
persona, no el del fallo, que EMMA no conoce.

SOPORTE VITAL Y CAUSA COMÚN (2026-10-21)
----------------------------------------
La base de conocimiento del equipo (§6) pone el estado del soporte vital y del control térmico
como «causa común potencial de cambios en varios tripulantes». Para eso el vocabulario dice de
cada sistema si es de soporte vital —con la lectura del resumen técnico de la NASA sobre el
ECLSS, no de memoria (`life_support_basis`)— y de cada estado si es fuera de lo nominal. La
alimentación y el ejercicio (decimonovena ronda) son sistemas porque NASA los llama así en sus
resúmenes técnicos, y no son de soporte vital porque nada leído lo dice: no entran en esa hipótesis.
`off_nominal_spans` da los tramos en que constó un estado así; `analysis/context.correlate` los
propone como coincidencia en el tiempo, nunca como causa, y sigue sin mover nada.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import display, i18n
from app.environment.habitat import DISPLAY_ONLY, MODULES, PARAMETERS, module_display, parameter
from app.evidence import registry

SYSTEMS_PATH = Path(__file__).resolve().parents[1] / "data" / "habitat_systems.json"

# Una declaración sin módulo habla del sistema entero, no de un sitio.
WHOLE_SYSTEM_DISPLAY = "sistema entero"

SINCE_BASIS = (
    "«Desde» es el instante al que se refiere la primera declaración seguida del estado "
    "vigente. Es lo que declaró una persona, no el instante en que cambió el sistema: EMMA no "
    "lo conoce."
)
RULE = (
    "De cada sistema y módulo vale el último asiento firmado por la consola; los anteriores se "
    "conservan. No hay borrado: se corrige declarando de nuevo."
)
i18n.en_many({
    WHOLE_SYSTEM_DISPLAY: "whole system",
    SINCE_BASIS: (
        "“Since” is the instant that the first declaration in a row with the current state "
        "refers to. It is what a person declared, not the instant at which the system changed: "
        "EMMA does not know it."
    ),
    RULE: (
        "For each system and module, the latest entry signed by the console is the one that "
        "counts; the earlier ones are kept. Nothing is deleted: it is corrected by declaring "
        "again."
    ),
})


def _text(value: str) -> str:
    """Un texto del vocabulario en el idioma de la petición.

    El vocabulario es un fichero de datos y su inglés va en el hermano `habitat_systems.en.json`
    (`i18n.localized`); se resuelve aquí, al servir, y no en `load`, que se evalúa una sola vez.
    Las claves de sistema y de estado, que son lo que se firma y se compara, no pasan por aquí.
    """
    return i18n.localized(value, SYSTEMS_PATH)


@dataclass(frozen=True, slots=True)
class HabitatSystem:
    key: str
    display: str
    description: str
    # Parámetros de cabina con los que la relación es de definición. Puede no haber ninguno.
    parameters: tuple[str, ...]
    # Es de soporte vital según el resumen técnico de la NASA sobre el ECLSS
    # (`Vocabulary.life_support_basis`). Solo lo lee `analysis/context.correlate`, para proponerlo
    # como causa común candidata; no sale en `to_dict` ni cambia ninguna otra salida.
    life_support: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display": _text(self.display),
            "description": _text(self.description),
            "parameters": [
                {"key": key, "display": i18n.loc(parameter(key).display)}
                for key in self.parameters
            ],
        }


@dataclass(frozen=True, slots=True)
class SystemState:
    key: str
    display: str
    # «Sin declarar» no se puede declarar: es lo que hay cuando nadie ha dicho nada.
    declarable: bool
    description: str
    # Quien lo declara dice que el sistema no funciona como se espera (degradado, fuera de
    # servicio). «Sin declarar» no lo es: no se sabe. Como `life_support`, solo lo lee `correlate`.
    off_nominal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "display": _text(self.display), "declarable": self.declarable,
            "description": _text(self.description),
        }


@dataclass(frozen=True, slots=True)
class Vocabulary:
    systems: dict[str, HabitatSystem]
    states: dict[str, SystemState]
    default_state: str
    basis: str
    declared_label: str
    declared_note: str
    relation_basis: str
    not_coded: str
    life_support_basis: str
    # Fichas del registro de evidencia en que se apoya `basis`. Puede no haber ninguna.
    basis_refs: tuple[str, ...] = ()


def load(path: Path = SYSTEMS_PATH) -> Vocabulary:
    """El vocabulario declarado, o un error: uno a medias no se carga.

    Es un fichero de datos y no una constante por lo mismo que la lista de módulos: EMMA no
    modela una nave concreta y la lista se cambia por la del vehículo sin tocar código. Lo que
    no se puede cambiar es lo que la hace honesta, y se comprueba aquí: que declare su base y
    su rótulo, que el estado por defecto exista y no se pueda declarar (si se pudiera, «nadie
    ha dicho nada» y «alguien ha dicho que no sabe» serían lo mismo), y que un sistema solo se
    relacione con parámetros de cabina que EMMA de verdad vigila. Y que diga de dónde sale qué
    sistema es de soporte vital y qué estado es «fuera de lo nominal», con verdadero o falso, y
    que «sin declarar» no lo sea: la falta de declaración no propone ninguna causa.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    texts = {
        key: str(raw.get(key, "")).strip()
        for key in (
            "basis", "declared_label", "declared_note", "relation_basis", "not_coded",
            "life_support_basis",
        )
    }
    missing = [key for key, value in texts.items() if not value]
    if missing:
        raise ValueError(f"el vocabulario de sistemas tiene que declarar: {', '.join(missing)}")
    refs = raw.get("basis_refs", [])
    if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
        raise ValueError("`basis_refs` es una lista de identificadores de ficha")
    basis_refs = tuple(refs)
    if len(set(basis_refs)) != len(basis_refs):
        raise ValueError("la base del vocabulario repite una ficha")
    for ref_id in basis_refs:
        registry.get(ref_id)  # una ficha que no está en el registro falla aquí

    states = {
        item["key"]: SystemState(
            item["key"], item["display"], item["declarable"], item["description"],
            item.get("off_nominal"),
        )
        for item in raw["states"]
    }
    if not states or len(states) != len(raw["states"]):
        raise ValueError("lista de estados vacía o con claves repetidas")
    if any(not isinstance(item.declarable, bool) for item in states.values()):
        raise ValueError("cada estado dice con verdadero o falso si se puede declarar")
    if any(not isinstance(item.off_nominal, bool) for item in states.values()):
        raise ValueError("cada estado dice con verdadero o falso si es fuera de lo nominal")
    default = raw["default_state"]
    if default not in states:
        raise ValueError("el estado por defecto no está en la lista de estados")
    if states[default].off_nominal:
        raise ValueError("«sin declarar» no puede ser fuera de lo nominal: no se sabe")
    if [key for key, item in states.items() if not item.declarable] != [default]:
        raise ValueError(
            "el estado por defecto, y solo él, no se puede declarar: es la falta de declaración"
        )
    if len(states) < 2:
        raise ValueError("no hay ningún estado que se pueda declarar")

    systems = {
        item["key"]: HabitatSystem(
            item["key"], item["display"], item["description"], tuple(item["parameters"]),
            item.get("life_support"),
        )
        for item in raw["systems"]
    }
    if not systems or len(systems) != len(raw["systems"]):
        raise ValueError("lista de sistemas vacía o con claves repetidas")
    if any(not isinstance(item.life_support, bool) for item in systems.values()):
        raise ValueError("cada sistema dice con verdadero o falso si es de soporte vital")
    named: Sequence[HabitatSystem | SystemState] = [*systems.values(), *states.values()]
    if any(
        not str(item.key).strip() or not str(item.display).strip()
        or not str(item.description).strip()
        for item in named
    ):
        raise ValueError("un sistema o un estado sin clave, sin nombre o sin descripción")
    for system in systems.values():
        unknown = [key for key in system.parameters if key not in PARAMETERS | DISPLAY_ONLY]
        if unknown:
            raise ValueError(
                f"el sistema {system.key} se relaciona con un parámetro de cabina que EMMA no "
                f"vigila: {', '.join(unknown)}"
            )
        if len(set(system.parameters)) != len(system.parameters):
            raise ValueError(f"el sistema {system.key} repite un parámetro de cabina")
    return Vocabulary(
        systems=systems, states=states, default_state=default, basis_refs=basis_refs, **texts
    )


VOCABULARY = load()
SYSTEMS = VOCABULARY.systems
STATES = VOCABULARY.states
UNDECLARED = VOCABULARY.default_state
DECLARABLE_STATES = tuple(key for key, item in STATES.items() if item.declarable)
DECLARED_LABEL = VOCABULARY.declared_label
# El rótulo lo importan otros módulos como constante: su inglés se registra también para
# `i18n.loc`, con el mismo texto que el hermano inglés del vocabulario (lo comprueba la prueba).
i18n.en(DECLARED_LABEL, "declared by a person, not telemetry")


def check(system: str, state: str, module: str | None) -> None:
    """Lo que se puede firmar. Lo usan la ruta y el almacén: nadie más escribe una declaración."""
    if system not in SYSTEMS:
        raise ValueError(f"sistema desconocido: {system}; uno de {', '.join(SYSTEMS)}")
    if state not in DECLARABLE_STATES:
        raise ValueError(
            f"estado que no se puede declarar: {state}; uno de {', '.join(DECLARABLE_STATES)}"
        )
    if module is not None and module not in MODULES:
        raise ValueError(f"módulo desconocido: {module}; uno de {', '.join(MODULES)}")


def system_display(key: str) -> str:
    """El nombre de un sistema; el de uno que ya no está en el vocabulario es su clave."""
    return _text(SYSTEMS[key].display) if key in SYSTEMS else key


def state_display(key: str) -> str:
    return _text(STATES[key].display) if key in STATES else key


def scope_display(module: str | None) -> str:
    return i18n.loc(WHOLE_SYSTEM_DISPLAY) if module is None else module_display(module)


def history(declarations: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada declaración, en el orden en que se firmó, con lo que constaba justo antes.

    `declarations` son los asientos tal y como los entrega el almacén. «Antes» es la
    declaración anterior del mismo sistema y módulo; sin ninguna, «sin declarar».
    """
    last: dict[tuple[str, str | None], str] = {}
    told: list[dict[str, Any]] = []
    for item in sorted(declarations, key=lambda entry: entry["ledger_index"]):
        module = item.get("module")
        scope = (item["system"], module)
        previous = last.get(scope, UNDECLARED)
        last[scope] = item["state"]
        told.append({
            "system": item["system"],
            "system_display": system_display(item["system"]),
            "state": item["state"],
            "state_display": state_display(item["state"]),
            "previous_state": previous,
            "previous_state_display": state_display(previous),
            "changed": previous != item["state"],
            "module": module,
            "module_display": scope_display(module),
            "at": item["at"],
            "note": item["note"] or None,
            "declared_by": item["declared_by"],
            "ledger_index": item["ledger_index"],
            "recorded": item["recorded"],
        })
    return told


def sentence(item: dict[str, Any]) -> str:
    """Una declaración de `history` en una frase, con su rótulo. La nota de la persona, al final."""
    where = "" if item["module"] is None else f" en {item['module_display']}"
    before = (
        f"antes constaba «{item['previous_state_display']}»" if item["changed"]
        else "sin cambio respecto a lo declarado antes"
    )
    note = f"; nota: {item['note']}" if item["note"] else ""
    return i18n.tr(
        f"sistema {item['system_display']}{where}: estado declarado "
        f"«{item['state_display']}» ({before}; {DECLARED_LABEL}){note}",
        _sentence_en(item),
    )


def _sentence_en(item: dict[str, Any]) -> str:
    """`sentence` en inglés, frase entera: la misma declaración, el mismo rótulo y la misma nota.

    Los nombres de `item` salen en el idioma en que se llamó a `history`; la nota es de la
    persona y va tal cual.
    """
    where = "" if item["module"] is None else f" in {item['module_display']}"
    before = (
        f"“{item['previous_state_display']}” was on record before" if item["changed"]
        else "no change from what was declared before"
    )
    note = f"; note: {item['note']}" if item["note"] else ""
    return (
        f"system {item['system_display']}{where}: declared state "
        f"“{item['state_display']}” ({before}; {i18n.loc(DECLARED_LABEL)}){note}"
    )


def off_nominal_spans(declarations: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Los tramos en que constó declarado fuera de lo nominal un sistema de soporte vital.

    De cada sistema y módulo, en el orden en que se firmó, cada racha de declaraciones con el
    mismo estado es un tramo: empieza en el instante de su primera declaración (como «desde» en
    `overview`) y acaba en el de la primera declaración con otro estado, o sigue abierto
    (`end` None) si es la última. Una declaración posterior que se refiere a un instante anterior
    corrige la racha: si su instante no queda después del comienzo, el tramo no existe. Solo los
    estados fuera de lo nominal y los sistemas de soporte vital; uno que ya no esté en el
    vocabulario no se propone, porque no se sabe qué era. Cada tramo lleva sus declaraciones
    (`declarations`), en el orden en que se firmaron.
    """
    runs: dict[tuple[str, str | None], list[list[dict[str, Any]]]] = {}
    for item in history(declarations):
        scope = runs.setdefault((item["system"], item["module"]), [])
        if scope and scope[-1][-1]["state"] == item["state"]:
            scope[-1].append(item)
        else:
            scope.append([item])
    spans = []
    for (system, _), scope in runs.items():
        if system not in SYSTEMS or not SYSTEMS[system].life_support:
            continue
        for position, run in enumerate(scope):
            first = run[0]
            if first["state"] not in STATES or not STATES[first["state"]].off_nominal:
                continue
            following = scope[position + 1][0] if position + 1 < len(scope) else None
            end = following["at"] if following is not None else None
            if end is not None and dt.datetime.fromisoformat(end) <= dt.datetime.fromisoformat(
                first["at"]
            ):
                continue
            spans.append({**first, "start": first["at"], "end": end, "declarations": run})
    return spans


def _undeclared() -> dict[str, Any]:
    return {
        "module": None,
        "module_display": i18n.loc(WHOLE_SYSTEM_DISPLAY),
        "state": UNDECLARED,
        "state_display": state_display(UNDECLARED),
        "declared": False,
        "since": None,
        "last_declared_at": None,
        "declarations": 0,
        "note": None,
        "declared_by": None,
        "ledger_index": None,
        "recorded": None,
    }


def _current(told: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """El estado vigente de un sistema en un módulo: la última declaración y desde cuándo."""
    last = told[-1]
    run = [last]
    for item in reversed(told[:-1]):
        if item["state"] != last["state"]:
            break
        run.append(item)
    return {
        "module": last["module"],
        "module_display": last["module_display"],
        "state": last["state"],
        "state_display": last["state_display"],
        "declared": True,
        "since": run[-1]["at"],
        "last_declared_at": last["at"],
        "declarations": len(told),
        "note": last["note"],
        "declared_by": last["declared_by"],
        "ledger_index": last["ledger_index"],
        "recorded": last["recorded"],
    }


def overview(declarations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """El estado vigente de cada sistema del vocabulario, el historial y cómo leerlo.

    Un sistema sin ninguna declaración sale igualmente, «sin declarar». Uno declarado solo en
    un módulo sale con ese módulo y nada más: del sistema entero nadie ha dicho nada, y no se
    rellena. Una declaración de un sistema que ya no está en el vocabulario se conserva en el
    historial, con su clave, y no tiene fila vigente.
    """
    told = history(declarations)
    systems = []
    for system in SYSTEMS.values():
        scopes: dict[str | None, list[dict[str, Any]]] = {}
        for item in told:
            if item["system"] == system.key:
                scopes.setdefault(item["module"], []).append(item)
        # El sistema entero primero; después los módulos en el orden de la lista declarada, y
        # al final los que ya no estén en ella.
        order = [None, *MODULES, *sorted(key for key in scopes if key and key not in MODULES)]
        statuses = [_current(scopes[key]) for key in order if key in scopes]
        systems.append({**system.to_dict(), "statuses": statuses or [_undeclared()]})
    declared = sum(1 for item in systems if item["statuses"][0]["declared"])
    payload: dict[str, Any] = {
        "label": DECLARED_LABEL,
        "note": VOCABULARY.declared_note,
        "basis": VOCABULARY.basis,
        # Las fichas en que se apoya la base, con su título y su dirección: la cita se abre.
        "basis_sources": [
            {"id": ref.id, "title": ref.title, "source": ref.source, "url": ref.url}
            for ref in (registry.get(ref_id) for ref_id in VOCABULARY.basis_refs)
        ],
        "relation_basis": VOCABULARY.relation_basis,
        "not_coded": VOCABULARY.not_coded,
        "rule": RULE,
        "since_basis": SINCE_BASIS,
        "default_state": UNDECLARED,
        # Cómo se nombra una declaración sin módulo, para quien la ofrece al declarar.
        "whole_system_display": WHOLE_SYSTEM_DISPLAY,
        "states": [item.to_dict() for item in STATES.values()],
        "systems": systems,
        "declared": declared,
        "undeclared": len(systems) - declared,
        "summary": i18n.tr(
            f"Sistemas con algún estado declarado: {display.number(declared, 0)} de "
            f"{display.number(len(systems), 0)}. De los demás no se sabe nada: que nadie lo "
            "haya declarado no quiere decir que funcionen.",
            f"Systems with some declared state: {display.number(declared, 0)} of "
            f"{display.number(len(systems), 0)}. Nothing is known about the others: that nobody "
            "has declared it does not mean that they work.",
        ),
        # Lo más reciente primero: es lo que se mira al abrir el panel.
        "history": told[::-1],
    }
    # Los textos del vocabulario (su inglés, en el hermano del fichero) y los de este módulo
    # (registrados junto a cada constante), en el idioma de la petición. Se hace a la salida
    # para que el diccionario de arriba siga siendo, línea a línea, el castellano de siempre.
    for key in ("label", "note", "basis", "relation_basis", "not_coded"):
        payload[key] = _text(payload[key])
    for key in ("rule", "since_basis", "whole_system_display"):
        payload[key] = i18n.loc(payload[key])
    return payload


# --------------------------------------------------------------------------- #
# El enlace con Tierra, tal y como lo declara una persona
# --------------------------------------------------------------------------- #
#
# POR QUÉ: la base de conocimiento pone la pérdida de comunicaciones junto a la latencia en el
# riesgo «Distance» (§2.1), y el vocabulario ya dejaba firmar «Comunicaciones: fuera de
# servicio». Nadie lo leía: la franja seguía diciendo «ida 12 min» y la ficha de Tierra «Tierra
# tiene datos hasta…» como si el enlace funcionara, con una persona habiendo firmado que no.
#
# Es SOLO TEXTO (decisión del usuario, 2026-10-21). El retardo sigue saliendo de las efemérides;
# el factor de aislamiento, las recomendaciones, `notify_ground` y el corte de Tierra no leen
# esto. EMMA no mide el enlace: dice lo que alguien declaró, quién, desde cuándo, con su rótulo.

LINK_SYSTEM = "communications"
# El estado que no pide atención. Cualquier otro declarado —también uno que el vocabulario
# añada mañana— se señala: ante la duda, se ve.
NOMINAL = "nominal"
LINK_SCOPE_RULE = (
    "Cuenta la declaración del sistema Comunicaciones entero: una hecha en un módulo habla del "
    "enlace de ese módulo, no del enlace con Tierra."
)
LINK_NOT_MEASURED = (
    "EMMA no mide el enlace: el retardo sale de las efemérides y no cambia con esta declaración."
)
i18n.en_many({
    LINK_SCOPE_RULE: (
        "The declaration that counts is the one for the whole Communications system: one made "
        "in a module is about that module's link, not about the link with Earth."
    ),
    LINK_NOT_MEASURED: (
        "EMMA does not measure the link: the delay comes from the ephemerides and does not "
        "change with this declaration."
    ),
})


def _utc(iso: str) -> str:
    return f"{dt.datetime.fromisoformat(iso).astimezone(dt.UTC):%Y-%m-%d %H:%M} UTC"


def earth_link(declarations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """El estado declarado del enlace con Tierra, con las frases que lo cuentan.

    `declarations` son los asientos que cuentan (los de la consola y, para Tierra, los de su
    corte). Solo vale la declaración del sistema entero (`LINK_SCOPE_RULE`). `attention` dice si
    hay que señalarlo: declarado y no «nominal». `headline` es la frase corta de la franja y de
    la ficha de Tierra, y `sentence` la entera; las dos llevan el rótulo de lo declarado y las
    compone este módulo para que ninguna pantalla las redacte. Sin `attention` no hay
    `headline`: no hay nada que señalar.
    """
    told = [
        item for item in history(declarations)
        if item["system"] == LINK_SYSTEM and item["module"] is None
    ]
    current = _current(told) if told else _undeclared()
    declared = bool(current["declared"])
    attention = declared and current["state"] != NOMINAL
    name = system_display(LINK_SYSTEM)
    # Quién declaró el estado vigente: el de la primera declaración seguida de ese estado, la del
    # «desde». Quien lo confirma después no lo declaró desde entonces, y se nombra aparte.
    started_by = None
    if told:
        started_by = told[-1]["declared_by"]
        for item in reversed(told[:-1]):
            if item["state"] != told[-1]["state"]:
                break
            started_by = item["declared_by"]
    headline = None
    if not declared:
        sentence = (
            f"Nadie ha declarado el estado del enlace con Tierra (sistema {name}): no se sabe "
            f"si funciona. {LINK_NOT_MEASURED}"
        )
    else:
        confirmed = (
            "" if current["declared_by"] == started_by
            else f", confirmado por {current['declared_by']}"
        )
        told_as = (
            f"«{current['state_display']}» desde {_utc(current['since'])} por "
            f"{started_by}{confirmed} ({DECLARED_LABEL})"
        )
        note = f" Nota de quien lo declaró: {current['note']}" if current["note"] else ""
        sentence = f"Enlace con Tierra declarado {told_as}. {LINK_NOT_MEASURED}{note}"
        if attention:
            headline = f"Enlace declarado {told_as}"
    # Las dos frases, en inglés, se componen enteras aparte: el castellano de arriba no se toca.
    english = _earth_link_en(current, started_by, name)
    sentence = i18n.tr(sentence, english[1])
    if headline is not None:
        headline = i18n.tr(headline, english[0])
    return {
        "system": LINK_SYSTEM,
        "system_display": name,
        "state": current["state"],
        "state_display": current["state_display"],
        "declared": declared,
        "attention": attention,
        "since": current["since"],
        # Quien firmó la declaración del «desde» y quien firmó la última (pueden ser el mismo).
        "since_declared_by": started_by,
        "declared_by": current["declared_by"],
        "note": current["note"],
        "ledger_index": current["ledger_index"],
        "label": _text(VOCABULARY.declared_label),
        "headline": headline,
        "sentence": sentence,
        "scope_rule": i18n.loc(LINK_SCOPE_RULE),
    }


def _earth_link_en(
    current: dict[str, Any], started_by: str | None, name: str
) -> tuple[str, str]:
    """La frase corta y la entera de `earth_link`, en inglés: (`headline`, `sentence`).

    Las mismas piezas y el mismo orden que el castellano —estado, desde cuándo, quién lo declaró
    y quién lo confirmó, el rótulo de lo declarado, que EMMA no mide el enlace y la nota de la
    persona—, redactadas como frase inglesa y no palabra a palabra. Quien llama decide si hay
    `headline`.
    """
    not_measured = i18n.loc(LINK_NOT_MEASURED)
    if not current["declared"]:
        return "", (
            f"Nobody has declared the state of the link with Earth (system {name}): it is not "
            f"known whether it works. {not_measured}"
        )
    confirmed = (
        "" if current["declared_by"] == started_by
        else f", confirmed by {current['declared_by']}"
    )
    told_as = (
        f"“{current['state_display']}” since {_utc(current['since'])} by "
        f"{started_by}{confirmed} ({i18n.loc(DECLARED_LABEL)})"
    )
    note = ""
    if current["note"]:
        note = f" Note from the person who declared it: {current['note']}"
    return (
        f"Link declared {told_as}",
        f"Link with Earth declared {told_as}. {not_measured}{note}",
    )
