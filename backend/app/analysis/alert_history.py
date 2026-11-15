"""La historia de las alertas ya cerradas, recalculada (especificación §3 `Alert`, §10).

Por qué existe: el `id` de una alerta es `dominio:nivel`, que no identifica un episodio, y el
análisis no guarda historia. La crónica conocía el inicio de las alertas activas y el cambio de
nivel frente a una ventana antes; de un episodio que empezó y acabó hace más tiempo solo quedaba
rastro si alguien había firmado algo. Una alerta que nadie reconoció desaparecía sin dejar nada.

Decisión del usuario (2026-10-09): la historia se RECALCULA y no se firma. Un asiento por
episodio habría hecho que consultar el estado escribiera en el ledger. Aquí no se escribe nada:
se recorre la serie hacia atrás en pasos del tamaño de la ventana del estado, se pregunta al
mismo motor qué nivel da a cada dominio en cada paso (`level_at`, que lo pone quien llama: este
módulo no evalúa nada) y se juntan los pasos contiguos por encima de nominal en episodios.

LO QUE ESTO ES Y LO QUE NO ES, Y VA EN CADA RESPUESTA
-----------------------------------------------------
Es un recálculo hecho ahora, con las reglas de hoy y con los datos que hay hoy en el ledger. No
es lo que el sistema enseñó entonces: las reglas pueden haber cambiado y pueden haber llegado
después lecturas con fecha anterior. Presentarlo como historia registrada sería afirmar algo que
nadie firmó. Por eso el rótulo y sus límites los redacta este módulo y viajan en la respuesta:
la interfaz los pinta, no los escribe.

Tampoco es fino: un episodio «empieza» en un paso, no en un instante. Y no dice quién lo vio ni
qué se hizo: eso son los asientos firmados, que se enseñan al lado (`signed`) sin mezclarlos.

EL TOPE
-------
`MAX_STEPS` es diseño de EMMA, sin fuente: acota el coste de recalcular (cada paso es una
evaluación del motor y un ajuste de tendencias) y no decide ningún nivel. No entra en la huella
de reglas porque no cambia ningún veredicto; lo que deja sin mirar se declara en la respuesta.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.analysis.recovery_state import _ORDER
from app.analysis.risk import RiskLevel
from app.core import display, i18n
from app.ingest.codes import Domain

# Cuántos pasos se recalculan como mucho, contando el actual. Diseño de EMMA, sin fuente.
MAX_STEPS = 30

LABEL = "Recalculado con las reglas de hoy"
# Lo que es un recálculo y lo que no, con las mismas palabras dondequiera que se enseñe uno (aquí
# y en el modo anatómico en un momento pasado, `anatomy.moment_basis`).
RECOMPUTED_BASIS = (
    "Es un recálculo hecho ahora, con las reglas de hoy y con los datos que hay hoy en el "
    "registro. No es lo que el sistema enseñó entonces: las reglas pueden haber cambiado y "
    "pueden haber llegado después lecturas con fecha anterior."
)
NOT_STORED = "No se guarda ni se firma: cada consulta lo vuelve a calcular."

MAX_STEPS_BASIS = "diseño de EMMA, sin fuente: acota el coste del recálculo, no decide niveles"

# Cómo se nombra cada estado de un episodio. La interfaz lo pinta: no lo escribe.
_STATE_DISPLAY = {True: "sigue abierto", False: "cerrado"}

START_UNKNOWN = (
    "Ya estaba así en el paso más antiguo recalculado: su comienzo queda antes y no se ha mirado."
)
i18n.en_many({
    LABEL: "Recomputed with today's rules",
    RECOMPUTED_BASIS: (
        "It is a recomputation done now, with today's rules and with the data that are in the "
        "record today. It is not what the system showed then: the rules may have changed and "
        "readings with an earlier date may have arrived later."
    ),
    NOT_STORED: "It is neither stored nor signed: each query computes it again.",
    MAX_STEPS_BASIS: (
        "EMMA design, with no source: it bounds the cost of the recomputation, it does not "
        "decide levels"
    ),
    START_UNKNOWN: (
        "It was already like this in the oldest recomputed step: its start lies earlier and "
        "has not been looked at."
    ),
})
# Palabras sueltas: tabla paralela, no el registro común (otra unidad puede decir «cerrado»).
_STATE_DISPLAY_EN = {True: "still open", False: "closed"}


def _label(level: RiskLevel) -> str:
    """La palabra del nivel como rótulo, en el idioma de la petición (la da `risk`)."""
    return i18n.loc(level.display).capitalize()

LevelAt = Callable[[dt.datetime, dt.datetime], Mapping[Domain, RiskLevel]]


@dataclass(frozen=True, slots=True)
class Step:
    """Un paso: `[start, end)`, y el nivel que el motor da hoy a cada dominio con sus lecturas.

    El paso actual (`index` 0) es la ventana del estado y sí incluye su final.
    """

    index: int
    start: dt.datetime
    end: dt.datetime
    levels: Mapping[Domain, RiskLevel]


def bounds(
    latest: dt.datetime, earliest: dt.datetime, window: dt.timedelta, max_steps: int | None = None
) -> list[tuple[dt.datetime, dt.datetime]]:
    """Los pasos, del actual hacia atrás, hasta cubrir la primera lectura o agotar el tope."""
    # El tope se lee al llamar: es el que la respuesta declara.
    limit = MAX_STEPS if max_steps is None else max_steps
    found: list[tuple[dt.datetime, dt.datetime]] = []
    end = latest
    while len(found) < limit:
        found.append((end - window, end))
        end -= window
        if end <= earliest:
            # Antes de este paso no hay ninguna lectura: no queda nada que recalcular.
            break
    return found


def walk(
    latest: dt.datetime, earliest: dt.datetime, window: dt.timedelta, level_at: LevelAt,
    max_steps: int | None = None,
) -> list[Step]:
    """Cada paso con sus niveles, del actual (índice 0) hacia atrás."""
    return [
        Step(index, start, end, dict(level_at(start, end)))
        for index, (start, end) in enumerate(bounds(latest, earliest, window, max_steps))
    ]


def _peak(levels: Sequence[RiskLevel]) -> RiskLevel:
    return max(levels, key=_ORDER.index)


def episodes(steps: Sequence[Step], examined_all: bool) -> list[dict[str, Any]]:
    """Los pasos contiguos por encima de nominal de cada dominio, juntos en un episodio.

    Del más reciente al más antiguo. Un episodio que toca el paso actual sigue abierto; uno que
    toca el paso más antiguo recalculado, habiendo lecturas anteriores sin mirar, ya estaba así
    cuando empieza lo recalculado: su comienzo no se conoce y se dice.
    """
    found: list[dict[str, Any]] = []
    for domain in Domain:
        run: list[Step] = []
        # De antiguo a reciente; un centinela nominal al final cierra el último tramo.
        for step in [*reversed(steps), None]:
            level = step.levels.get(domain, RiskLevel.NOMINAL) if step is not None else None
            if step is not None and level is not RiskLevel.NOMINAL:
                run.append(step)
                continue
            if run:
                found.append(_episode(domain, run, steps, examined_all))
                run = []
    found.sort(key=lambda item: (item["last_step_end"], item["domain"]), reverse=True)
    return found


def _episode(
    domain: Domain, run: Sequence[Step], steps: Sequence[Step], examined_all: bool
) -> dict[str, Any]:
    peak = _peak([step.levels[domain] for step in run])
    first, last = run[0], run[-1]
    is_open = last.index == 0
    cut_short = first.index == steps[-1].index and not examined_all
    return {
        # Identifica el episodio dentro de ESTE recálculo: con otras reglas u otros datos, el
        # mismo tramo puede no existir. No es el `id` de una alerta ni se firma en ningún sitio.
        "id": f"recomputed:{domain}:{first.start.isoformat()}",
        "domain": str(domain),
        "domain_display": i18n.loc(domain.display),
        "peak_level": str(peak),
        "peak_level_display": _label(peak),
        # La resolución es la del paso: no hay instante de inicio ni de fin, hay pasos.
        "first_step_start": first.start.isoformat(),
        "last_step_end": last.end.isoformat(),
        "steps": len(run),
        "open": is_open,
        "state_display": i18n.tr(_STATE_DISPLAY[is_open], _STATE_DISPLAY_EN[is_open]),
        "start_unknown": cut_short,
        "start_note": i18n.loc(START_UNKNOWN) if cut_short else None,
        "levels": [
            {"step_start": step.start.isoformat(), "step_end": step.end.isoformat(),
             "level": str(step.levels[domain]), "level_display": _label(step.levels[domain])}
            for step in run
        ],
        "signed": [],
    }


def attach_signed(
    found: Sequence[dict[str, Any]], signed: Sequence[Mapping[str, Any]]
) -> None:
    """Pone al lado de cada episodio lo que alguien firmó de ese dominio en sus pasos.

    `signed` son asientos ya filtrados por quien llama (qué firmas cuentan lo decide el estado):
    `{ledger_index, kind, kind_display, domain, by, reference_time, rules}`. Se listan, no se
    interpretan: un reconocimiento firmado sobre otro nivel sigue siendo un hecho firmado.
    """
    for episode in found:
        start = dt.datetime.fromisoformat(episode["first_step_start"])
        end = dt.datetime.fromisoformat(episode["last_step_end"])
        episode["signed"] = sorted(
            (
                dict(item) for item in signed
                if item["domain"] == episode["domain"]
                and start <= dt.datetime.fromisoformat(item["reference_time"]) <= end
            ),
            key=lambda item: item["ledger_index"],
        )


def describe(
    steps: Sequence[Step],
    earliest: dt.datetime,
    window: dt.timedelta,
    rules_version: str,
    max_steps: int | None = None,
    external_basis: str = "",
) -> dict[str, Any]:
    """La respuesta entera: episodios, rótulo, límites y tope, todo redactado aquí."""
    oldest = steps[-1].start
    examined_all = oldest <= earliest
    days = len(steps) * window / dt.timedelta(days=1)
    # `:g` y no `display.number`: los días salen sin ceros de más («30», «2,5») y `number` pide
    # decimales fijos. Solo cambia el separador, que es el del idioma de la petición.
    span = f"{days:g}".replace(".", display.decimal_mark())
    if examined_all:
        coverage = i18n.tr(
            f"Historia recalculada de los últimos {span} días, que es toda la serie: no hay "
            f"lecturas anteriores.",
            f"History recomputed for the last {span} days, which is the whole series: there are "
            f"no earlier readings.",
        )
    else:
        coverage = i18n.tr(
            f"Historia recalculada de los últimos {span} días; antes de eso no se ha "
            f"recalculado: hay lecturas anteriores que no se han mirado.",
            f"History recomputed for the last {span} days; before that nothing has been "
            f"recomputed: there are earlier readings that have not been looked at.",
        )
    found = episodes(steps, examined_all)
    resting = i18n.loc(RiskLevel.NOMINAL.display)
    return {
        "label": i18n.loc(LABEL),
        # La palabra del nivel bajo el que no hay episodio: quien cuente uno no la escribe.
        "resting_level_display": resting,
        "rules_version": rules_version,
        "basis": [
            i18n.loc(RECOMPUTED_BASIS),
            i18n.tr(
                f"La resolución es la del paso ({window / dt.timedelta(hours=1):g} h, la ventana "
                f"del estado): un episodio empieza y acaba en un paso, no en un instante. El "
                f"inicio fino solo lo tiene la alerta activa.",
                f"The resolution is that of the step ({window / dt.timedelta(hours=1):g} h, the "
                f"window of the state): an episode starts and ends in a step, not at an "
                f"instant. Only the active alert has the fine-grained onset.",
            ),
            i18n.tr(
                "No dice quién lo vio ni qué se hizo. Eso son los asientos firmados, que se "
                "listan al lado de cada episodio sin mezclarlos con él.",
                "It does not say who saw it or what was done. That is the signed entries, which "
                "are listed beside each episode without mixing them with it.",
            ),
            *([i18n.loc(external_basis)] if external_basis else []),
            i18n.loc(NOT_STORED),
        ],
        "window_hours": window / dt.timedelta(hours=1),
        "steps_examined": len(steps),
        "max_steps": MAX_STEPS if max_steps is None else max_steps,
        "max_steps_basis": i18n.loc(MAX_STEPS_BASIS),
        "examined_from": oldest.isoformat(),
        "examined_until": steps[0].end.isoformat(),
        "first_reading": earliest.isoformat(),
        "complete": examined_all,
        "coverage": coverage,
        "episodes": found,
        "none_display": (
            None if found
            else i18n.tr(
                f"Ningún dominio pasa de {RiskLevel.NOMINAL.display} en los pasos recalculados.",
                f"No domain goes above {resting} in the recomputed steps.",
            )
        ),
    }
