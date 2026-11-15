"""La prueba PVT hecha en la consola: sus parámetros, sus textos y lo que quedó firmado.

POR QUÉ EXISTE
--------------
El contexto del equipo cuenta con el rendimiento cognitivo (la tarea de vigilancia
psicomotora) como medida objetiva de bajo coste. El backend ya la puntuaba (`ingest/pvt.py`)
y ya la registraba (`POST /api/pvt`), pero ninguna pantalla la pasaba: la prueba solo «se
hacía» en el simulador.

QUIÉN PASA LA PRUEBA EN PANTALLA (decisión del usuario, 2026-10-13)
-------------------------------------------------------------------
Hasta esa fecha el panel enviaba la prueba a `POST /api/pvt`, que firma como `pvt-test`: la
fuente de CUALQUIER PVT que llegue por la API. Una prueba hecha en un navegador no se
distinguía de la de un equipo dedicado, y no constaba quién estaba en la consola. Ahora la
consola tiene su ruta (`POST /api/pvt/console`), que fija la fuente `console-pvt` y exige el
nombre del operador (`recorded_by`; 422 si falta). `POST /api/pvt` no cambia.

Este módulo NO puntúa nada: la ruta de la consola llama a la misma puntuación
(`ingest.pvt.score`) y a la misma conversión (`to_observations`) que la de siempre, y anexa
al ledger con `store.record_many` (invariante 4). Lo firmado antes como `pvt-test` se sigue
leyendo y enseñando, con su fuente y sin operador («no consta»).

Además, aquí se decide, en el backend, lo que la interfaz no debe decidir:

- **con qué parámetros se pasa la prueba**. Los que la puntuación ya usa se leen de
  `ingest/pvt.py`, no se copian. Los que no están escritos en el repositorio (cuántos
  estímulos, cuánto se espera entre ellos) se declaran con estas palabras: «diseño de EMMA,
  sin fuente leída». No describen ningún protocolo publicado ni pretenden serlo;
- **qué se le dice a quien la hace**, incluido el límite honesto: un navegador y un teclado
  no son un instrumento calibrado, y una sola prueba no es una línea base;
- **cómo se llama cada cifra** del resultado que devuelve `POST /api/pvt`, para que la
  interfaz no la rotule por su cuenta;
- **con qué procedencia y con qué hora** queda firmada.

No toca el análisis (invariante 5): una PVT hecha en pantalla entra en la serie de su
indicador como cualquier otra lectura, que es lo que el motor ya hacía con esa ruta.
Ninguno de los parámetros de diseño de aquí decide un nivel ni una alerta, y por eso no
entran en la huella de reglas (`core/versioning.py`).

LO LEÍDO EN LAS FUENTES (2026-10-13)
------------------------------------
Los dos artículos que definen la prueba se leyeron y sus frases viven en
`data/instruments_read.json` (`evidence/instruments_read.py`). Aquí cada parámetro gana, al
lado de su valor, lo que da la fuente para cada versión publicada de la prueba, con su frase,
y en qué difiere EMMA. La lectura NO cambia ningún valor: los que puntúan (`ingest/pvt.py`)
mueven el indicador de lapsos que el análisis vigila, y cambiarlos es una decisión que no se
toma aquí. Por eso la prueba de la consola no lleva el nombre de ninguna de las dos
publicadas: `identity` dice exactamente qué es.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.analysis.data_quality import source_label
from app.api.diary import (
    NOT_RECORDED,
    RECORDED_BY_NOTE,
    OperatorName,
    _position,
    recorded_by_display,
)
from app.api.routes import (
    SettingsDep,
    StoreDep,
    _recorded_or_422,
    _when,
    identity_for,
    state_reference,
)
from app.core import display
from app.evidence import instruments_read
from app.ingest.codes import CATALOG
from app.ingest.fhir import ObservationType, annotated_by, deployed
from app.ingest.pvt import (
    FALSE_START_THRESHOLD_MS,
    LAPSE_THRESHOLD_MS,
    MIN_TRIALS,
    InsufficientTrials,
    PvtResult,
    is_lapse,
    score,
    to_observations,
)
from app.ingest.simulator import LITERATURE

pvt_router = APIRouter(prefix="/pvt")

# La fuente con que `POST /api/pvt` firma (`routes.submit_pvt`). Se lee de la conversión
# real, no se escribe aquí otra vez: si la ruta cambiara de fuente, esto cambia con ella.
_PROBE = to_observations(
    PvtResult(
        trials=MIN_TRIALS, valid_trials=MIN_TRIALS, mean_rt_ms=LAPSE_THRESHOLD_MS,
        median_rt_ms=LAPSE_THRESHOLD_MS, slowest_10pct_mean_ms=LAPSE_THRESHOLD_MS,
        lapses=0, false_starts=0, response_speed=1.0,
    ),
    "crew-01",
    dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
)
PVT_SOURCE = _PROBE[0].source
# Los indicadores que deja una prueba, en el orden en que la ruta los registra.
RECORDED_KEYS = tuple(item.key for item in _PROBE)

# La fuente propia de la prueba hecha en pantalla. Solo la pone `POST /api/pvt/console`; la
# ingesta genérica la rechaza como reservada (`routes._is_reserved_source`). No es
# `crew-console`, que firma decisiones del operador y no puede firmar una lectura.
CONSOLE_SOURCE = "console-pvt"
# Lo que `GET /api/pvt/sessions` enseña: lo hecho en pantalla y lo que llegó por la ruta de
# siempre, cada prueba con la fuente con que entró.
SESSION_SOURCES = frozenset({CONSOLE_SOURCE, PVT_SOURCE})

RECORDED_BY_LABEL = "Quién está en la consola"
LEGACY_NOTE = (
    f"Las pruebas firmadas como «{source_label(PVT_SOURCE)}» no llevan quién estaba en la "
    f"consola: de ellas se dice «{NOT_RECORDED}»."
)


class ConsolePvtIn(BaseModel):
    """Una prueba entera hecha en pantalla: un tiempo por estímulo, de quién es y quién teclea.

    No lleva hora ni fuente: las pone el backend.
    """

    model_config = ConfigDict(extra="forbid")

    reaction_times_ms: list[float] = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=64)
    recorded_by: OperatorName


def _received() -> dt.datetime:
    """La hora de una prueba hecha en pantalla: la de recepción."""
    return _when(None)

DESIGN = "diseño de EMMA, sin fuente leída"
# Un valor que EMMA fijó por diseño y que, leída la fuente, resulta ser el publicado.
DESIGN_MATCHES = "valor de diseño de EMMA; coincide con el leído en la fuente"

# Cómo queda el valor de EMMA frente a lo publicado. Se calcula, no se escribe a mano.
COMPARISONS = {
    "same_value": "mismo valor que",
    "same_figure_different_operator": "misma cifra, distinto operador que",
    "different_value": "valor distinto del publicado",
    "not_comparable": "no comparable con lo publicado",
    "not_published": "sin valor publicado en lo leído",
}

# La marca de cada valor publicado: si es el de EMMA. Hasta el 2026-10-20 se comparaba solo la
# cifra, y la fila del lapso marcaba «= es el valor de EMMA» junto a «≥ 500 ms» cuando EMMA
# cuenta «> 500 ms»: la misma cifra con otra comparación no es el mismo valor. Ahora, donde la
# fuente escribe un operador, cuenta también; el de EMMA se deduce del código que puntúa.
MARKERS = {
    "same": "= es el valor de EMMA",
    "same_figure_different_operator": "≠ misma cifra, distinto operador",
    "different": "≠ no es el valor de EMMA",
}
# Los operadores que una fuente puede escribir delante de la cifra («≥ 500 ms», «< 100 ms»).
_OPERATORS = frozenset({"≥", "≤", ">", "<"})
_BASIS_TEXT = {"design": DESIGN, "read": DESIGN_MATCHES}

# --------------------------------------------------------------------------- #
# Parámetros de la prueba en pantalla. NINGUNO tiene fuente escrita en el repositorio: son
# diseño de EMMA, y así se declaran en la respuesta y en el panel.
# --------------------------------------------------------------------------- #

# Cuántos estímulos tiene una prueba. La puntuación exige al menos `MIN_TRIALS`.
SESSION_TRIALS = 20
# Espera, de duración variable, antes de cada estímulo. La interfaz sortea un valor entre
# los dos extremos para cada estímulo.
FOREPERIOD_MIN_MS = 2000
FOREPERIOD_MAX_MS = 10000
# Cómo se envía una respuesta dada antes del estímulo. La ruta solo admite tiempos, y la
# puntuación cuenta como salida en falso todo lo que quede por debajo de su umbral: un cero
# dice «no hubo tiempo de reacción» sin inventar uno.
PREMATURE_RESPONSE_MS = 0.0
# Cuánto se espera una respuesta antes de dar la prueba por abandonada. No es un parámetro
# nuevo: es el máximo físico que el catálogo admite para el tiempo de reacción medio. Un
# estímulo sin respuesta no tiene tiempo de reacción, y enviar el tope como si lo fuera
# sería inventar un dato; por eso se abandona y no se envía nada.
_MEAN_RT_MAX = CATALOG["pvt-mean-rt"].physical_max
if _MEAN_RT_MAX is None:  # pragma: no cover - el catálogo lo declara; sin él no hay tope honesto
    raise RuntimeError("pvt-mean-rt sin máximo físico: la prueba en consola no tiene tope")
ABANDON_AFTER_MS = float(_MEAN_RT_MAX)

INSTRUCTIONS = (
    "Tras una espera de duración variable aparece una marca. Al verla, se responde lo "
    "antes posible con la barra espaciadora, con la tecla Intro o con un toque sobre el "
    "recuadro.",
    "Responder antes de que aparezca la marca cuenta como salida en falso.",
    "La prueba se puede abandonar en cualquier momento, con el botón o con la tecla Escape. "
    "Una prueba abandonada no se envía ni se guarda.",
)

# El límite honesto de hacer la prueba en una consola. Descriptivo: lo que el sistema hace
# y lo que no puede afirmar.
LIMITS = (
    "Un navegador, una pantalla y un teclado añaden a cada tiempo una latencia que no está "
    "caracterizada. Esto no es un instrumento calibrado: sus tiempos no se pueden comparar "
    "sin más con los de un equipo de prueba dedicado.",
    "Una sola prueba no es una línea base. El análisis la compara con las lecturas "
    "anteriores del mismo indicador y del mismo tripulante, vengan de donde vengan: no las "
    "separa por fuente.",
    "El número de estímulos es " + DESIGN + ". La tabla dice, parámetro a parámetro, qué dan "
    "las fuentes leídas para cada versión publicada de la prueba y en qué difiere esta.",
)

NOTICES = {
    "premature": "Respuesta antes de la marca: se cuenta como salida en falso.",
    "abandoned": "Prueba abandonada: no se ha enviado ni guardado nada.",
    "no_response": (
        "Sin respuesta dentro del tiempo máximo de espera: la prueba se da por abandonada y "
        "no se ha enviado ni guardado nada."
    ),
}


def _documented_lapse() -> tuple[str, str]:
    """El respaldo del umbral de lapso, tal como ya está escrito en el simulador."""
    entry = LITERATURE["pvt_lapse_threshold_ms"]
    return entry.note, entry.source


def _ms(value: float) -> str:
    return f"{display.number(value, 0)} {display.unit('ms')}"


def _literal_operator(literal: str) -> str | None:
    """El operador que la fuente escribe delante de la cifra, si escribe uno."""
    head = literal.split(" ", 1)[0]
    return head if head in _OPERATORS else None


def _value(
    item: dict[str, Any], emma_ms: float | list[float] | None, emma_operator: str | None,
) -> dict[str, Any]:
    """Un valor publicado y si es el de EMMA: la misma cifra y, si la fuente lo escribe, el
    mismo operador."""
    operator = _literal_operator(str(item["literal"]))
    same_figure = emma_ms is not None and item["value_ms"] == emma_ms
    same = same_figure and (operator is None or operator == emma_operator)
    marker: str | None = None
    # Si la fuente escribe un operador y no se da el de EMMA, no se puede decir ni «=» ni «≠»:
    # el valor queda sin marca, no se adivina (`test_pvt_divergences.py` exige que se dé).
    if emma_ms is None or (operator is not None and emma_operator is None):
        match = "not_comparable"
    else:
        if same:
            match = "same"
        elif same_figure:
            match = "same_figure_different_operator"
        else:
            match = "different"
        marker = MARKERS[match]
        if match == "same_figure_different_operator" and isinstance(emma_ms, int | float):
            marker = f"{marker} (EMMA: {emma_operator} {_ms(emma_ms)})"
    return {
        **item,
        # `same`: es el valor de EMMA, cifra y operador. `same_figure`: solo la cifra.
        "same": same,
        "same_figure": same_figure,
        "operator": operator,
        "emma_operator": emma_operator if operator is not None else None,
        "match": match,
        # Lo que la interfaz pinta junto al valor, tal cual; `None` si no es comparable.
        "marker_display": marker,
    }


def _compare(
    key: str,
    emma_ms: float | list[float] | None,
    difference: str,
    emma_operator: str | None = None,
) -> dict[str, Any]:
    """El valor de EMMA frente al que da la fuente para cada versión publicada de la prueba."""
    read = instruments_read.pvt_published(key)
    values = [_value(item, emma_ms, emma_operator) for item in read["values"]]
    same = [item["variant_display"] for item in values if item["match"] == "same"]
    figure = [
        item["variant_display"] for item in values
        if item["match"] == "same_figure_different_operator"
    ]
    named: list[str] = []
    if not values:
        status = "not_published"
    elif all(item["match"] == "not_comparable" for item in values):
        status = "not_comparable"
    elif same:
        status, named = "same_value", same
    elif figure:
        status, named = "same_figure_different_operator", figure
    else:
        status = "different_value"
    text = COMPARISONS[status]
    return {
        "status": status,
        "status_display": f"{text} {' y '.join(named)}" if named else text,
        "values": values,
        "see_also": read["see_also"],
        # Lo que separa a EMMA de lo publicado, sin adornos. Texto de EMMA, no de la fuente.
        "difference": difference,
    }


def _parameter(
    key: str,
    label: str,
    value: float,
    value_text: str,
    *,
    source: str | None,
    note: str,
    scores: bool,
    emma_ms: float | list[float] | None,
    difference: str,
    emma_operator: str | None = None,
) -> dict[str, Any]:
    published = _compare(key, emma_ms, difference, emma_operator)
    # `repository`: su respaldo está escrito en el repositorio y se da tal cual.
    # `read`: EMMA lo fijó por diseño y el valor leído en la fuente es el mismo.
    # `design`: nada escrito lo respalda.
    basis = "design"
    if source is None and published["status"] == "same_value":
        basis = "read"
    return {
        "key": key,
        "display": label,
        "value": value,
        "value_text": value_text,
        "basis": "repository" if source is not None else basis,
        "basis_display": source if source is not None else _BASIS_TEXT[basis],
        "note": note,
        # Si el valor entra en la puntuación de una prueba (`ingest/pvt.py`).
        "scores": scores,
        "published": published,
    }


def parameters() -> list[dict[str, Any]]:
    """Cada parámetro de la prueba con su valor y con lo que lo respalda, o que nada lo hace."""
    lapse_note, lapse_source = _documented_lapse()
    return [
        _parameter(
            "lapse_threshold_ms", "Lapso: tiempo de reacción por encima de",
            LAPSE_THRESHOLD_MS, _ms(LAPSE_THRESHOLD_MS),
            source=lapse_source, note=lapse_note,
            scores=True, emma_ms=LAPSE_THRESHOLD_MS, emma_operator=lapse_operator(),
            difference=(
                "EMMA cuenta un lapso cuando el tiempo de reacción es mayor que "
                f"{_ms(LAPSE_THRESHOLD_MS)}; las fuentes escriben «≥»: una respuesta de "
                f"exactamente {_ms(LAPSE_THRESHOLD_MS)} es lapso en lo publicado y no en EMMA. "
                "El umbral de EMMA es el de la prueba de 10 minutos; para la versión breve de "
                "3 minutos el artículo da otro, más bajo, y dice que con el mismo umbral la "
                "versión breve cuenta menos lapsos. Este valor puntúa y no se ha cambiado: "
                "moverlo cambia el indicador de lapsos que el análisis vigila."
            ),
        ),
        _parameter(
            "false_start_threshold_ms", "Salida en falso: respuesta por debajo de",
            FALSE_START_THRESHOLD_MS, _ms(FALSE_START_THRESHOLD_MS),
            source=None,
            note="Regla con que el backend puntúa (ingest/pvt.py); una respuesta anterior a "
            "la marca cuenta igual.",
            scores=True, emma_ms=FALSE_START_THRESHOLD_MS,
            emma_operator=false_start_operator(),
            difference=(
                "Mismo valor y mismo sentido que en las fuentes: salida en falso es toda "
                f"respuesta por debajo de {_ms(FALSE_START_THRESHOLD_MS)} o dada sin estímulo. "
                "Hasta esta lectura figuraba como diseño de EMMA sin fuente."
            ),
        ),
        _parameter(
            "min_trials", "Mínimo de estímulos para puntuar",
            MIN_TRIALS, display.number(MIN_TRIALS, 0),
            source=None,
            note="Regla con que el backend puntúa (ingest/pvt.py): con menos, rechaza la prueba.",
            scores=True, emma_ms=None,
            difference=(
                "Ninguno de los dos artículos da, en lo leído, un mínimo de estímulos para "
                "puntuar: las pruebas publicadas duran un tiempo fijo. Sigue siendo diseño de "
                "EMMA."
            ),
        ),
        _parameter(
            "trials", "Estímulos de una prueba",
            SESSION_TRIALS, display.number(SESSION_TRIALS, 0),
            source=None, note="Cada estímulo se cierra con una respuesta, válida o en falso.",
            scores=False, emma_ms=None,
            difference=(
                f"EMMA cierra la prueba al llegar a {display.number(SESSION_TRIALS, 0)} "
                "estímulos; las pruebas publicadas duran un tiempo fijo, y el número de "
                "estímulos resulta de él. Sigue siendo diseño de EMMA."
            ),
        ),
        _parameter(
            "foreperiod_ms", "Espera antes de cada estímulo",
            FOREPERIOD_MAX_MS,
            f"entre {_ms(FOREPERIOD_MIN_MS)} y {_ms(FOREPERIOD_MAX_MS)}",
            source=None,
            note="La consola sortea la espera de cada estímulo entre los dos extremos.",
            scores=False, emma_ms=[FOREPERIOD_MIN_MS, FOREPERIOD_MAX_MS],
            difference=(
                "Los extremos son los de la prueba de 10 minutos, no los de la versión breve "
                "de 3 minutos. Dos diferencias: en lo publicado el intervalo incluye 1 s en "
                "que se enseña el tiempo de reacción y se sortea en segundos enteros; la "
                "consola no enseña el tiempo de reacción y sortea cualquier valor entre los "
                "dos extremos."
            ),
        ),
        _parameter(
            "abandon_after_ms", "Tiempo máximo de espera de una respuesta",
            ABANDON_AFTER_MS, _ms(ABANDON_AFTER_MS),
            source=None,
            note="Es el máximo físico que el catálogo admite para el tiempo de reacción medio. "
            "Pasado ese tiempo la prueba se abandona sola: un estímulo sin respuesta no tiene "
            "tiempo de reacción que enviar.",
            scores=False, emma_ms=ABANDON_AFTER_MS,
            difference=(
                "En lo publicado, un estímulo sin respuesta se cuenta como un lapso con el "
                "tiempo máximo como tiempo de reacción. En EMMA, pasados "
                f"{_ms(ABANDON_AFTER_MS)} sin respuesta la prueba se abandona y no se envía "
                "nada: no se cuenta ningún lapso."
            ),
        ),
    ]


def identity() -> str:
    """Qué prueba es esta, dicho con exactitud: ninguna de las publicadas, y por qué."""
    names = "; ".join(instruments_read.pvt_tests())
    return (
        f"No es ninguna de las pruebas publicadas ({names}). Es una prueba de "
        f"{display.number(SESSION_TRIALS, 0)} estímulos, con la espera entre estímulos de la "
        f"prueba de 10 minutos (entre {_ms(FOREPERIOD_MIN_MS)} y {_ms(FOREPERIOD_MAX_MS)}) y "
        f"lapsos contados por encima de {_ms(LAPSE_THRESHOLD_MS)}, que es el umbral de la "
        "prueba de 10 minutos y no el de la versión breve."
    )


# --------------------------------------------------------------------------- #
# Divergencias con la fuente leída (2026-10-14)
# --------------------------------------------------------------------------- #
# La tabla de parámetros ya decía, uno a uno, en qué difiere EMMA. Pero lo dicho quedaba
# repartido en textos largos, y cuatro diferencias que mueven o pueden mover lo que se cuenta
# merecen estar juntas y con nombre: aquí se declaran como divergencias, cada una con lo que
# hace EMMA —deducido del código que puntúa, no escrito a mano—, la frase leída que dice otra
# cosa y la consecuencia. Declarar no es corregir: ningún valor que puntúa cambia (invariante
# 5; lo fija `tests/test_pvt_divergences.py`). Alinearlos es decisión del usuario.

DIVERGENCES_NOTE = (
    "Diferencias entre lo que hace EMMA y lo que dice la fuente leída, una a una. Se declaran, "
    "no se corrigen: ningún valor que puntúa se ha cambiado, porque moverlo cambia el "
    "indicador de lapsos que el análisis vigila. Alinearlos es una decisión pendiente."
)
KEPT = "No se ha cambiado: es una divergencia declarada, pendiente de decisión."
# Se calcula frente a lo leído: si un día EMMA se alinea, el estado lo dice solo.
DIVERGENCE_STATUS = {
    "differs": "EMMA difiere de lo publicado",
    "matches": "EMMA coincide ya con lo publicado",
    "not_published": "sin valor publicado en lo leído",
}


def _status(differs: bool) -> str:
    return "differs" if differs else "matches"


def lapse_operator() -> str:
    """Con qué comparación cuenta EMMA un lapso, deducida de la regla que puntúa."""
    return "≥" if is_lapse(LAPSE_THRESHOLD_MS) else ">"


def false_start_operator() -> str:
    """Con qué comparación cuenta EMMA una salida en falso, deducida de la puntuación.

    `ingest/pvt.py` no la expone aparte, como `is_lapse`: se le pasa a `score` una respuesta
    justo en el umbral, y su recuento dice si la cuenta o no.
    """
    probe = score([FALSE_START_THRESHOLD_MS] + [LAPSE_THRESHOLD_MS] * MIN_TRIALS)
    return "≤" if probe.false_starts else "<"


def _published(key: str, variant: str) -> dict[str, Any]:
    """El valor leído de un parámetro para una versión de la prueba: literal y cifra."""
    found: dict[str, Any] = next(
        item for item in instruments_read.pvt_published(key)["values"]
        if item["variant"] == variant
    )
    return found


def _statements(*ids: str) -> list[dict[str, Any]]:
    return [instruments_read.statement(ref) for ref in ids]


def divergences() -> dict[str, Any]:
    """Las divergencias de la prueba con lo publicado, con la frase que las sostiene."""
    operator = lapse_operator()
    lapse = _ms(LAPSE_THRESHOLD_MS)
    # Los umbrales leídos, versión a versión: el que coincide en cifra con el de EMMA y los demás.
    thresholds = instruments_read.pvt_published("lapse_threshold_ms")["values"]
    same = next(item for item in thresholds if item["value_ms"] == LAPSE_THRESHOLD_MS)
    others = [item for item in thresholds if item["value_ms"] != LAPSE_THRESHOLD_MS]
    timeout = _published("abandon_after_ms", "both")
    items = [
        {
            "key": "lapse_operator",
            "display": "Cómo se cuenta un lapso en el umbral",
            "emma": f"lapso si el tiempo de reacción es {operator} {lapse}",
            "published": (
                f"lapso si el tiempo de reacción es {same['literal']} "
                f"({same['variant_display']})"
            ),
            "status": _status(not str(same["literal"]).startswith(f"{operator} ")),
            "consequence": (
                f"Una respuesta de exactamente {lapse} es lapso en lo publicado y no en EMMA."
            ),
            "scores": True,
            "sources": _statements("pvt10-lapse-500", "pvt10-lapse-table"),
        },
        {
            "key": "lapse_threshold_version",
            "display": "De qué versión de la prueba es el umbral de lapso",
            "emma": f"umbral de {lapse}, el de la {same['variant_display']}",
            "published": "; ".join(
                f"{item['literal']} en la {item['variant_display']}" for item in thresholds),
            # EMMA no pasa ninguna de las dos: difiere mientras alguna use otro umbral.
            "status": _status(bool(others)),
            "consequence": (
                "La prueba de la consola no es ninguna de las dos publicadas, y su umbral es el "
                "de la de 10 minutos. Según la fuente, con el umbral de 500 ms la versión breve "
                "cuenta menos lapsos; el de 355 ms se eligió para igualarlos, se fijó a "
                "posteriori y puede depender del equipo."
            ),
            "scores": True,
            "sources": _statements(
                "pvt10-lapse-500", "pvtb-lapse-355", "pvtb-lapse-355-why",
                "pvtb-fewer-lapses", "pvtb-lapse-355-limit"),
        },
        {
            "key": "no_response",
            "display": "Un estímulo sin respuesta",
            "emma": (
                f"pasados {_ms(ABANDON_AFTER_MS)} sin respuesta, la prueba se abandona y no se "
                "envía nada"
            ),
            "published": (
                f"pasados {timeout['literal']} sin respuesta, se cuenta un lapso con ese tiempo "
                f"({timeout['variant_display']})"
            ),
            "status": _status(timeout["value_ms"] != ABANDON_AFTER_MS),
            "consequence": (
                "En lo publicado, quien no responde suma un lapso; en EMMA no queda prueba, ni "
                "lapso, de ese estímulo."
            ),
            "scores": False,
            "sources": _statements("timeout-30s", "pvt10-timeout-table"),
        },
        {
            "key": "min_trials",
            "display": "Mínimo de estímulos para puntuar",
            "emma": (
                f"con menos de {display.number(MIN_TRIALS, 0)} estímulos, la prueba se rechaza"
            ),
            "published": "sin valor publicado en lo leído: las pruebas duran un tiempo fijo",
            "status": "not_published",
            "consequence": "El mínimo es diseño de EMMA: no hay frase leída que lo sostenga.",
            "scores": True,
            "sources": [],
            "not_found": [
                line for line in instruments_read.pvt_not_found() if "mínimo" in line
            ],
        },
    ]
    for item in items:
        item["status_display"] = DIVERGENCE_STATUS[str(item["status"])]
        item["kept"] = KEPT
        item.setdefault("not_found", [])
    return {"note": DIVERGENCES_NOTE, "items": items}


PUBLISHED_NOTE = (
    "Lo que dicen los artículos que definen la prueba, con su frase exacta en su idioma y la "
    "fecha en que se leyó, y al lado lo que hace EMMA. La lectura no ha cambiado ningún valor "
    "de la prueba ni de su puntuación."
)

# Qué cifras deja la prueba en el registro frente a las que proponen las fuentes.
OUTCOMES_NOTE = (
    "EMMA registra el tiempo de reacción medio y el número de lapsos. La velocidad de "
    "respuesta (media de 1/TR), que las fuentes ponen entre las medidas principales, EMMA la "
    "calcula y la devuelve con el resultado, pero no la registra."
)


def published() -> dict[str, Any]:
    """Lo leído que no es de un solo parámetro: con quién se estudió, qué queda pendiente."""
    return {
        "note": PUBLISHED_NOTE,
        "read_on": instruments_read.read()["read_on"],
        "sources": instruments_read.pvt_sources(),
        "context": instruments_read.pvt_context(),
        "outcomes_note": OUTCOMES_NOTE,
        "not_found": instruments_read.pvt_not_found(),
    }


# Cómo se llama cada cifra del resultado de `POST /api/pvt` (`PvtResult.to_dict`). Los
# nombres describen la cuenta; no dicen si el valor es bueno o malo.
_RESULT_FIELDS: tuple[tuple[str, str, str, int, str | None], ...] = (
    ("trials", "Estímulos", "", 0, None),
    ("valid_trials", "Respuestas válidas", "", 0, None),
    ("false_starts", "Salidas en falso", "", 0, None),
    ("mean_rt_ms", "Tiempo de reacción medio", "ms", 0, "pvt-mean-rt"),
    ("median_rt_ms", "Mediana del tiempo de reacción", "ms", 0, None),
    ("slowest_10pct_mean_ms", "Media de la décima parte más lenta", "ms", 0, None),
    ("lapses", "Lapsos", "", 0, "pvt-lapses"),
)


def result_fields() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "display": label,
            "unit_display": display.unit(unit) if unit else "",
            "decimals": decimals,
            # El indicador del catálogo con que esta cifra queda en el registro, si queda.
            "recorded_as": recorded_as,
        }
        for key, label, unit, decimals, recorded_as in _RESULT_FIELDS
    ]


@pvt_router.get("/protocol")
def protocol(settings: SettingsDep) -> dict[str, Any]:
    """Con qué parámetros pasa la consola la prueba y qué se le dice a quien la hace."""
    return {
        "title": "Prueba de vigilancia psicomotora (PVT)",
        "identity": identity(),
        "instructions": list(INSTRUCTIONS),
        "limits": list(LIMITS),
        "notices": dict(NOTICES),
        "parameters": parameters(),
        "published": published(),
        "divergences": divergences(),
        # Lo que la consola necesita para pasar la prueba, en cifras.
        "session": {
            "trials": SESSION_TRIALS,
            "foreperiod_min_ms": FOREPERIOD_MIN_MS,
            "foreperiod_max_ms": FOREPERIOD_MAX_MS,
            "premature_response_ms": PREMATURE_RESPONSE_MS,
            "abandon_after_ms": ABANDON_AFTER_MS,
        },
        "result_fields": result_fields(),
        "records": [
            {
                "key": key, "display": CATALOG[key].display,
                "display_es": CATALOG[key].display_es,
            }
            for key in RECORDED_KEYS
        ],
        "provenance": {
            "source": CONSOLE_SOURCE,
            "source_display": source_label(CONSOLE_SOURCE),
            "observation_type": str(ObservationType.MEASURED),
            "evidence_context": str(settings.deployment_context),
            "effective_note": (
                "Las lecturas se firman con la hora en que el backend recibe la prueba, "
                "no con una hora que diga la consola."
            ),
        },
        # Quién teclea: obligatorio en cada envío, y cómo se nombra cuando una prueba no lo lleva.
        "recorded_by": {
            "required": True,
            "label": RECORDED_BY_LABEL,
            "note": RECORDED_BY_NOTE,
            "missing_display": NOT_RECORDED,
            "legacy_note": LEGACY_NOTE,
        },
        "submit_to": "/api/pvt/console",
        "notes": [
            "Es un registro real: mientras exista, el almacén no se puede sustituir por "
            "otro escenario simulado.",
        ],
    }


@pvt_router.post("/console", status_code=201)
def submit_console(
    store: StoreDep, settings: SettingsDep, payload: ConsolePvtIn
) -> dict[str, Any]:
    """Puntúa una prueba hecha en pantalla y la firma con su fuente y con quién tecleó.

    Misma puntuación y misma conversión que `POST /api/pvt`; cambian la fuente, que la fija
    el backend, y el nombre del operador, que va firmado en cada una de sus lecturas.
    """
    try:
        result = score(payload.reaction_times_ms)
    except InsufficientTrials as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        observations = annotated_by(
            deployed(
                to_observations(result, payload.subject, _received(), CONSOLE_SOURCE),
                settings.deployment_context,
            ),
            payload.recorded_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    entries = _recorded_or_422(
        lambda: store.record_many(observations, identity_for(CONSOLE_SOURCE))
    )
    return {
        "result": result.to_dict(),
        "recorded": [entry.index for entry in entries],
        "source": CONSOLE_SOURCE,
        "source_display": source_label(CONSOLE_SOURCE),
        "recorded_by": payload.recorded_by,
    }


@pvt_router.get("/sessions")
def sessions(
    store: StoreDep,
    subject: str = "crew-01",
    limit: int = Query(default=5, ge=1, le=100),
) -> dict[str, Any]:
    """Las pruebas registradas de un tripulante, leídas del registro firmado, la última primero.

    Es lo que la consola enseña tras enviar: qué quedó registrado, a qué hora y si el estado
    lo analiza, no lo que el panel cree que envió. Cuenta las hechas en pantalla y las que
    llegaron por la ruta de siempre; cada una dice con qué fuente entró y quién tecleó, si
    consta.
    """
    readings = store.query(subject)
    # El «ahora» del estado, con su regla (`routes.state_reference`): ni una lectura predicha
    # fechada en el futuro ni una descriptiva lo mueven aqui tampoco (§5.38.7).
    kept, reference, _ = state_reference(readings)
    # Las dos lecturas de una prueba comparten instante, fuente y tipo: es lo que las agrupa. El
    # tipo tambien (§5.39.11): la posicion y el tipo de la fila salen de la primera lectura, y
    # dos altas sueltas por `POST /api/observations` con el mismo instante y fuente pero de tipos
    # distintos (una medida, una inferida) serian una sola fila que callaria el de la segunda.
    grouped: dict[tuple[dt.datetime, str, str], list[Any]] = {}
    for item in readings:
        if item.source in SESSION_SOURCES and item.key in RECORDED_KEYS:
            key = (item.effective, item.source, str(item.observation_type))
            grouped.setdefault(key, []).append(item)

    found = []
    for effective, source, _kind in sorted(grouped, reverse=True)[:limit]:
        items = sorted(
            grouped[effective, source, _kind], key=lambda item: RECORDED_KEYS.index(item.key))
        position, note = _position(items[0], reference)
        found.append(
            {
                "effective": effective.isoformat(),
                "source": source,
                "source_display": source_label(source),
                # Quién tecleó, tal como quedó firmado; `None` si la prueba no lo lleva.
                "recorded_by": items[0].recorded_by,
                "recorded_by_display": recorded_by_display(items[0]),
                "observation_type": str(items[0].observation_type),
                "evidence_context": str(items[0].evidence),
                "position": position,
                "position_note": note,
                "values": [
                    {
                        "key": item.key,
                        "display": item.code.display,
                        "display_es": item.code.display_es,
                        "value": item.value,
                        "value_text": display.quantity(item.key, item.value, item.code.unit),
                    }
                    for item in items
                ],
            }
        )
    return {
        "subject": subject,
        "count": len(grouped),
        # Como el diario: sin ninguna lectura que decida no hay «ahora», y se dice nulo, no la
        # cota con que `_analysable` responde a una lista vacía.
        "reference_time": reference.isoformat() if kept else None,
        "sessions": found,
    }
