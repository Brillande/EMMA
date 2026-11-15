"""Niveles de misión: qué medidas se siguen esperando cuando escasean los recursos.

POR QUÉ EXISTE
--------------
La idea del equipo (2026-11-02): «un protocolo de desconexión progresiva de funciones para ver lo
mínimo básico en ambientes con restricción de recursos, sobre todo energéticos y humanos, y tener
claro qué es lo fundamental en cada momento». Con la energía racionada o la tripulación sin
tiempo, nadie va a tomar una muestra de saliva ni a montar el ecógrafo, y una consola que sigue
esperándolo todo convierte cada medida no tomada en un olvido. Hace falta poder declarar, firmado,
«estamos en nivel reducido», y que se vea qué se sigue esperando y qué no.

LO QUE NUNCA SE APAGA
---------------------
El nivel cambia **qué medidas se esperan**, y nada más. La ingesta por el registro firmado, la
línea base, la tendencia, el riesgo, las alertas y el modo seguro son los mismos en cualquier
nivel: el estado y las alertas con los mismos datos son idénticos (`tests/test_mission_mode.py`).
Es la invariante 5 dicha al revés: se llega al 0 % de falsas alarmas apagando el sistema, y eso
ya pasó. Una medida suspendida que llega igual entra por el ledger y se analiza como cualquier
otra. Ningún módulo de `analysis/` importa este.

DE DÓNDE SALE EL CRITERIO
-------------------------
Los tres niveles son vocabulario de diseño de EMMA (`data/mission_modes.json`, rotulado así): no
se han leído de ningún procedimiento de vuelo. Lo que no es de diseño es el criterio: cada nivel
nombra las clases de medida y el gasto de consumibles que se siguen esperando, y lo que cae de
cada lado sale, indicador a indicador, de rasgos que ya tienen fuente en el coste de medir
(`ingest/cost.py`, `data/measurement_cost.json`). No se gradúa la importancia clínica de una
medida, que EMMA no puede afirmar. Un calculado sigue a sus entradas. La única lista a mano
(`also_expected`) lleva su motivo, y el cargador comprueba que lo que nombra no pide muestra,
laboratorio, consumibles ni análisis en Tierra. No hay potencia eléctrica de los equipos con
fuente, y aquí no se escribe ninguna.

QUIÉN BAJA Y QUIÉN SUBE
-----------------------
El modo seguro toma de Polaris (`codigo_rojo`) «lo activa cualquiera con un motivo, y solo una
persona lo levanta». Aquí la dirección protectora es bajar: quien ve que se acaba la energía no
tiene que esperar a nadie. Así:

* **bajar** lo firma cualquiera con nombre y un motivo, y puede saltar niveles (de nominal a
  mínimo de una vez: una emergencia no va por escalones);
* **subir** lo firma una persona con nombre, sin motivo obligatorio, y **un nivel cada vez**:
  volver a esperar muestras y laboratorio es un compromiso de recursos y se decide paso a paso,
  cada uno con su asiento.

No se firma el nivel vigente otra vez. Las reglas las aplica el almacén bajo su cerrojo
(`storage._change_mission_mode`), como las del modo seguro.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from app.core import display, i18n
from app.environment import systems as habitat_systems
from app.ingest import codes, cost

MODES_PATH = Path(__file__).resolve().parents[1] / "data" / "mission_modes.json"

# De más medidas a menos. El almacén firma solo estas claves; el cargador exige el mismo orden.
LEVELS: tuple[str, ...] = ("nominal", "reduced", "minimal")
NOMINAL = LEVELS[0]
LABEL = "vocabulario de diseño de EMMA"

# Lo que un nivel no puede dejar de esperar a mano: pide muestra, laboratorio o análisis en Tierra.
_SAMPLE_MODES = frozenset({"periodic-invasive", "laboratory"})
_DERIVED = "derived"
_CONSUMES = "consumes"
_GROUND = "ground-or-return"

# Lo que no cambia con el nivel. Una frase por pieza, para la respuesta y para el aviso.
UNCHANGED: tuple[str, ...] = (
    "La ingesta: toda medida que llega entra por el registro firmado, también una suspendida.",
    "El análisis: la línea base, la tendencia y el riesgo leen los mismos datos con las mismas "
    "reglas.",
    "Las alertas: se calculan, se anuncian y se reconocen igual.",
    "El modo seguro: se activa y se levanta igual, y corta lo mismo.",
)
i18n.en_many({
    UNCHANGED[0]: (
        "Ingestion: every measurement that arrives enters through the signed ledger, a "
        "suspended one too."
    ),
    UNCHANGED[1]: (
        "Analysis: the baseline, the trend and the risk read the same data with the same rules."
    ),
    UNCHANGED[2]: "Alerts: they are computed, announced and acknowledged the same way.",
    UNCHANGED[3]: "Safe mode: it is activated and lifted the same way, and cuts the same things.",
})
RULE = (
    "Bajar de nivel lo firma una persona con nombre y un motivo, y puede saltar niveles. Subir lo "
    "firma una persona con nombre, un nivel cada vez. Vale el último asiento firmado por la "
    "consola; no se repite el nivel vigente."
)
NOT_POWER = (
    "EMMA no tiene la potencia eléctrica de los equipos ni mide la energía disponible: el nivel "
    "dice qué medidas se esperan, no cuánta energía se ahorra ni qué equipo se apaga."
)
i18n.en(
    RULE,
    "Lowering the level is signed by a named person with a reason, and may skip levels. Raising "
    "it is signed by a named person, one level at a time. The last entry signed by the console "
    "is the one in force; the level in force is not repeated.",
)
i18n.en(
    NOT_POWER,
    "EMMA does not have the electrical power of the equipment and does not measure the "
    "available energy: the level says which measurements are expected, not how much energy is "
    "saved or which equipment is switched off.",
)


class MissionModeConflict(ValueError):
    """El cambio choca con el nivel vigente (ya está en él, o sube más de un nivel): un 409."""


@dataclass(frozen=True, slots=True)
class Level:
    key: str
    display: str
    description: str
    modes: frozenset[str]
    consumables: frozenset[str]
    # Indicador -> motivo, en el orden del fichero.
    also_expected: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Vocabulary:
    label: str
    basis: str
    levels: dict[str, Level]
    citable_systems: tuple[str, ...]
    citable_basis: str
    expected: dict[str, frozenset[str]]


def _traits(key: str) -> tuple[str, str, str]:
    """Clase de medida, consumibles y dónde se procesa, tal cual los da el coste de medir."""
    dims = cost.dimensions()[key]
    return cost.costs()[key]["mode"], dims["consumables"]["value"], dims["processing"]["value"]


def _by_rule(level: Level, catalog: Sequence[str]) -> set[str]:
    """Lo que el criterio del nivel espera, sin la lista a mano y sin los calculados."""
    found = set()
    for key in catalog:
        mode, consumables, _ = _traits(key)
        if mode != _DERIVED and mode in level.modes and consumables in level.consumables:
            found.add(key)
    return found


def _with_derived(expected: set[str], catalog: Sequence[str]) -> frozenset[str]:
    """Un calculado se espera si se esperan todas sus entradas (un paso: `cost` lo garantiza)."""
    raw = cost.costs()
    derived = {
        key for key in catalog
        if raw[key]["mode"] == _DERIVED and set(raw[key]["inputs"]) <= expected
    }
    return frozenset(expected | derived)


def load(path: Path = MODES_PATH) -> Vocabulary:
    """El vocabulario, o un error: uno a medias no se carga.

    Comprueba que los niveles sean los tres de `LEVELS` y en ese orden; que cada clase de medida
    y cada valor de consumibles exista en el coste de medir (el calculado no se nombra: sigue a
    sus entradas); que lo añadido a mano exista en el catálogo, lleve motivo, no lo espere ya el
    criterio y no pida muestra, laboratorio, consumibles ni análisis en Tierra; que nominal lo
    espere todo; que bajar nunca añada medidas (cada nivel espera un subconjunto del anterior); y
    que los sistemas citables existan en el vocabulario del hábitat.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("label") != LABEL:
        raise ValueError(f"el vocabulario de niveles se rotula «{LABEL}»")
    basis = str(raw.get("basis", "")).strip()
    citable_basis = str(raw.get("citable_basis", "")).strip()
    if not basis or not citable_basis:
        raise ValueError("el vocabulario de niveles declara su base y la de lo que se cita")

    catalog = list(codes.CATALOG)
    if missing := sorted(set(catalog) - cost.costs().keys()):
        raise ValueError(f"indicadores sin coste de medir, que no se pueden clasificar: {missing}")
    modes_allowed = set(cost.MODES) - {_DERIVED}
    consumables_allowed = {*cost.DIMENSIONS["consumables"]["values"], cost.UNCLASSIFIED}

    levels: dict[str, Level] = {}
    for item in raw["levels"]:
        key = item["key"]
        if key in levels:
            raise ValueError(f"nivel repetido: {key}")
        modes, consumables = item["modes"], item["consumables"]
        if not modes or len(set(modes)) != len(modes) or not set(modes) <= modes_allowed:
            raise ValueError(
                f"{key}: clases de medida vacías, repetidas o fuera del coste de medir "
                f"(un calculado no se nombra: sigue a sus entradas)"
            )
        if (
            not consumables or len(set(consumables)) != len(consumables)
            or not set(consumables) <= consumables_allowed
        ):
            raise ValueError(f"{key}: consumibles vacíos, repetidos o fuera del coste de medir")
        if not str(item.get("display", "")).strip() or not str(item.get("description", "")).strip():
            raise ValueError(f"{key}: cada nivel dice su nombre y qué espera")
        added = tuple((entry["key"], str(entry.get("reason", "")).strip())
                      for entry in item.get("also_expected", []))
        levels[key] = Level(
            key, item["display"], item["description"], frozenset(modes), frozenset(consumables),
            added,
        )
    if tuple(levels) != LEVELS:
        raise ValueError(f"los niveles son {', '.join(LEVELS)}, en ese orden")

    expected: dict[str, frozenset[str]] = {}
    for level in levels.values():
        found = _by_rule(level, catalog)
        seen: set[str] = set()
        for key, reason in level.also_expected:
            if key not in codes.CATALOG:
                raise ValueError(f"{level.key}: {key} no está en el catálogo de indicadores")
            if key in seen:
                raise ValueError(f"{level.key}: {key} añadido dos veces")
            seen.add(key)
            if not reason:
                raise ValueError(f"{level.key}: {key} se añade a mano sin motivo")
            if key in found:
                raise ValueError(f"{level.key}: {key} ya lo espera el criterio del nivel")
            mode, consumables, processing = _traits(key)
            if mode in _SAMPLE_MODES or mode == _DERIVED:
                raise ValueError(
                    f"{level.key}: {key} pide muestra o laboratorio, o se calcula: no se añade a "
                    "mano"
                )
            if consumables == _CONSUMES:
                raise ValueError(f"{level.key}: {key} gasta consumibles: no se añade a mano")
            if processing == _GROUND:
                raise ValueError(f"{level.key}: {key} se analiza en Tierra: no se añade a mano")
            found.add(key)
        expected[level.key] = _with_derived(found, catalog)

    if expected[NOMINAL] != frozenset(catalog):
        raise ValueError("el nivel nominal espera todas las medidas del catálogo")
    for upper, lower in zip(LEVELS, LEVELS[1:], strict=False):
        if not expected[lower] <= expected[upper]:
            extra = sorted(expected[lower] - expected[upper])
            raise ValueError(f"bajar a {lower} añadiría medidas que {upper} no espera: {extra}")

    citable = tuple(raw.get("citable_systems", ()))
    if len(set(citable)) != len(citable) or not set(citable) <= set(habitat_systems.SYSTEMS):
        raise ValueError("los sistemas citables son sistemas del hábitat, sin repetir")
    return Vocabulary(LABEL, basis, levels, citable, citable_basis, expected)


@cache
def vocabulary() -> Vocabulary:
    return load()


def shown(text: str) -> str:
    """Un texto del vocabulario (nombre o descripción de un nivel, su base) en el idioma de la
    petición. El vocabulario cacheado se queda en castellano: se traduce al servir.
    """
    return i18n.localized(text, MODES_PATH)


def expected_measurements(level: str) -> frozenset[str]:
    """Las claves del catálogo que se siguen esperando en `level`.

    Es la pieza que se cablea a las rutinas (`routines.py`): una rutina cuya medida no se espera
    no se recuerda como pendiente. No decide nada del análisis.
    """
    return vocabulary().expected[level]


def suspended_measurements(level: str) -> frozenset[str]:
    """Las que se dejan de esperar en `level`: el catálogo menos las esperadas."""
    return frozenset(codes.CATALOG) - expected_measurements(level)


def rank(level: str) -> int:
    """0 es nominal; cuanto más alto, menos medidas se esperan."""
    return LEVELS.index(level)


def check_change(current: str, new: str, reason: str, declared_by: str) -> None:
    """Las reglas de un cambio de nivel. Las aplica el almacén, bajo su cerrojo.

    `ValueError` para lo que falta en la petición (un 422); `MissionModeConflict` para lo que
    choca con el nivel vigente (un 409).
    """
    if new not in LEVELS:
        raise ValueError(f"nivel desconocido: {new}; uno de {', '.join(LEVELS)}")
    if not any(char.isalpha() for char in declared_by):
        raise ValueError("el nivel lo cambia una persona con nombre")
    if new == current:
        raise MissionModeConflict(f"el nivel ya es {vocabulary().levels[new].display}")
    if rank(new) > rank(current) and not any(char.isalnum() for char in reason):
        raise ValueError("bajar de nivel exige un motivo")
    if rank(new) < rank(current) - 1:
        raise MissionModeConflict("se sube un nivel cada vez")


def check_cited(system: str | None) -> None:
    """Un sistema citado es uno de los citables del vocabulario, o ninguno."""
    if system is not None and system not in vocabulary().citable_systems:
        raise ValueError(
            f"sistema que no se puede citar: {system}; uno de "
            f"{', '.join(vocabulary().citable_systems)}"
        )


def cited_state(declarations: Sequence[dict[str, Any]], system: str) -> str:
    """El estado declarado del sistema entero que consta ahora, o «sin declarar».

    Es el mismo que enseña el panel del hábitat (`systems.overview`): la primera fila de un
    sistema es la del sistema entero si alguien la declaró. Lo que se declara en un módulo habla
    de ese módulo, no del sistema (como `earth_link`).
    """
    row = next(item for item in habitat_systems.overview(declarations)["systems"]
               if item["key"] == system)
    first = row["statuses"][0]
    return str(first["state"]) if first["module"] is None else habitat_systems.UNDECLARED


def entry_problem(entry: Mapping[str, Any]) -> str | None:
    """Lo que hace inservible un asiento firmado de nivel, o None.

    Un nivel fuera del vocabulario, o una cita a medias (sistema sin estado o al revés) o fuera
    del vocabulario del hábitat: firmado, pero no se adivina qué quiso decir.
    """
    if entry["level"] not in LEVELS:
        return "nivel desconocido"
    system, state = entry.get("cited_system"), entry.get("cited_state")
    if (system is None) != (state is None):
        return "cita a medias: sistema sin estado o estado sin sistema"
    if system is not None and (
        system not in habitat_systems.SYSTEMS or state not in habitat_systems.STATES
    ):
        return "cita fuera del vocabulario del hábitat"
    return None


def history(entries: Sequence[Mapping[str, Any]]) -> list[tuple[str, Mapping[str, Any]]]:
    """Cada asiento que cuenta, en orden de firma, con el nivel que dejaba atrás.

    El anterior es el del asiento que contaba justo antes entre los mismos (`entries`, ya
    filtrados como los filtra `storage.mission_mode`), o nominal si es el primero. Un asiento
    redactado (§3.6) ya no llega aquí: el siguiente cuenta desde el que quede, igual que la
    versión, que baja en uno. Un asiento inservible es un error, no se adivina.
    """
    previous = NOMINAL
    told: list[tuple[str, Mapping[str, Any]]] = []
    for item in sorted(entries, key=lambda entry: entry["ledger_index"]):
        problem = entry_problem(item)
        if problem is not None:
            raise ValueError(f"asiento {item['ledger_index']}: {problem}")
        told.append((previous, item))
        previous = item["level"]
    return told


def chronicle_sentence(previous: str, entry: Mapping[str, Any]) -> str:
    """El cambio de nivel en una frase para la crónica: de qué nivel a cuál, el motivo y la cita.

    La redacta el backend; dice lo firmado y no manda nada (invariante 7). El estado del sistema
    citado es el declarado al firmar, no telemetría.
    """
    levels = vocabulary().levels
    before, after = shown(levels[previous].display), shown(levels[entry['level']].display)
    text = i18n.tr(
        f"nivel de misión: de {before} a {after}",
        f"mission level: from {before} to {after}",
    )
    reason = str(entry.get("reason") or "").strip()
    if reason:
        text += i18n.tr(f"; motivo: {reason}", f"; reason: {reason}")
    if entry.get("cited_system") is not None:
        system = habitat_systems.system_display(entry['cited_system'])
        state = habitat_systems.state_display(entry['cited_state'])
        text += i18n.tr(
            f"; cita {system}: {state} al firmar (declarado, no telemetría)",
            f"; cites {system}: {state} when signed (declared, not telemetry)",
        )
    return text


def _measure(key: str) -> dict[str, Any]:
    """Una medida con los rasgos que la ponen de un lado o del otro, del coste de medir."""
    item = cost.costs()[key]
    dims = cost.dimensions()[key]
    return {
        "key": key,
        "name": codes.get(key).display_es,
        "mode": item["mode"],
        "mode_display": i18n.loc(cost.MODES[item["mode"]]),
        "consumables": dims["consumables"]["value"],
        "consumables_display": i18n.loc(dims["consumables"]["display"]),
        "crew_time_minutes": item["crew_time_minutes"],
        "crew_time_basis": i18n.loc(item["crew_time_basis"]),
        "inputs": list(item.get("inputs", [])),
    }


def _measure_class(mode: str) -> str:
    name = i18n.loc(cost.MODES[mode])
    return i18n.tr(f"clase de medida: {name}", f"measurement class: {name}")


def _why_suspended(level: Level, key: str, expected: frozenset[str]) -> str:
    """Qué parte del criterio deja fuera la medida, en una frase."""
    item = cost.costs()[key]
    if item["mode"] == _DERIVED:
        missing = [codes.get(name).display_es for name in item["inputs"] if name not in expected]
        return i18n.tr(
            f"se calcula de medidas que no se esperan: {', '.join(missing)}",
            f"calculated from measurements that are not expected: {', '.join(missing)}",
        )
    if item["mode"] not in level.modes:
        return _measure_class(item["mode"])
    consumables = i18n.loc(cost.dimensions()[key]['consumables']['display'])
    return i18n.tr(f"consumibles: {consumables}", f"consumables: {consumables}")


def _why_expected(level: Level, key: str) -> str:
    added = dict(level.also_expected)
    if key in added:
        return i18n.tr(f"añadida a mano: {added[key]}", f"added by hand: {shown(added[key])}")
    item = cost.costs()[key]
    if item["mode"] == _DERIVED:
        return i18n.tr(
            "se calcula de medidas que se esperan",
            "calculated from measurements that are expected",
        )
    return _measure_class(item["mode"])


def level_view(key: str) -> dict[str, Any]:
    """Un nivel con lo que espera y lo que suspende, cada medida con su porqué."""
    vocab = vocabulary()
    level = vocab.levels[key]
    expected = vocab.expected[key]
    order = list(codes.CATALOG)
    return {
        "key": key,
        "display": shown(level.display),
        "description": shown(level.description),
        "rank": rank(key),
        "expected": [
            {**_measure(name), "why": _why_expected(level, name)}
            for name in order if name in expected
        ],
        "suspended": [
            {**_measure(name), "why": _why_suspended(level, name, expected)}
            for name in order if name not in expected
        ],
    }


def notice(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """El aviso para la consola fuera de nominal, o None en nominal.

    La interfaz no redacta: el texto sale de aquí. Dice qué es el nivel y qué no toca, sin el
    motivo libre de quien lo firmó (ese va aparte, en `reason`). Es información, no una orden.
    """
    key = state["level"]
    if key == NOMINAL:
        return None
    vocab = vocabulary()
    level = vocab.levels[key]
    total = len(codes.CATALOG)
    suspended = total - len(vocab.expected[key])
    details = [
        shown(level.description),
        i18n.tr(
            "Una medida suspendida no se espera, y su falta no cuenta como un olvido. Si llega, "
            "entra por el registro firmado y se analiza como cualquier otra.",
            "A suspended measurement is not expected, and its absence does not count as an "
            "omission. If it arrives, it enters through the signed ledger and is analysed like "
            "any other.",
        ),
        *(i18n.loc(item) for item in UNCHANGED),
        i18n.tr(
            "Qué se suspende sale de la clase de medida y del gasto de consumibles de cada "
            "indicador en el coste de medir, no de una valoración clínica de su importancia.",
            "What is suspended follows from the measurement class and the use of consumables of "
            "each indicator in the cost of measuring, not from a clinical assessment of its "
            "importance.",
        ),
        i18n.loc(NOT_POWER),
        i18n.loc(RULE),
    ]
    if state.get("cited_system") is not None:
        system = habitat_systems.system_display(state['cited_system'])
        cited = habitat_systems.state_display(state['cited_state'])
        details.insert(
            1,
            i18n.tr(
                f"El cambio cita {system}. Su estado al firmarlo: {cited}. Es lo que consta "
                "declarado en la consola, no telemetría.",
                f"The change cites {system}. Its state when signed: {cited}. It is what is on "
                "record as declared in the console, not telemetry.",
            ),
        )
    figures = display.number(suspended, 0), display.number(total, 0)
    return {
        "title": i18n.tr(
            f"Nivel de misión {level.display}", f"Mission level {shown(level.display)}"
        ),
        "headline": i18n.tr(
            f"{figures[0]} de {figures[1]} medidas sin esperar",
            f"{figures[0]} of {figures[1]} measurements not expected",
        ),
        "summary": i18n.tr(
            "Siguen la ingesta, el análisis, el riesgo, las alertas y el modo seguro.",
            "Ingestion, analysis, risk, alerts and safe mode carry on.",
        ),
        "since": state.get("since"),
        "since_label": i18n.tr(
            "desde (hora del asiento firmado)", "since (time of the signed entry)"
        ),
        "details_label": i18n.tr("Qué cambia y qué no", "What changes and what does not"),
        "details": details,
    }


def view(state: Mapping[str, Any]) -> dict[str, Any]:
    """El estado firmado con lo que espera, lo que suspende, los niveles y el aviso."""
    vocab = vocabulary()
    cited = state.get("cited_system")
    return {
        **state,
        "level_display": shown(vocab.levels[state["level"]].display),
        "cited_system_display": None if cited is None else habitat_systems.system_display(cited),
        "cited_state_display": (
            None if cited is None else habitat_systems.state_display(state["cited_state"])
        ),
        "label": shown(vocab.label),
        "basis": shown(vocab.basis),
        "rule": i18n.loc(RULE),
        "not_power": i18n.loc(NOT_POWER),
        "unchanged": [i18n.loc(item) for item in UNCHANGED],
        "citable_systems": [
            {"key": key, "display": habitat_systems.system_display(key)}
            for key in vocab.citable_systems
        ],
        "citable_basis": shown(vocab.citable_basis),
        "levels": [
            {"key": key, "display": shown(level.display),
             "description": shown(level.description),
             "rank": rank(key), "expected": len(vocab.expected[key])}
            for key, level in vocab.levels.items()
        ],
        "current": level_view(state["level"]),
        "notice": notice(state),
    }
