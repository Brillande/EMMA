"""Lo único que ve el modelo del asistente: el texto que el backend ya da a esa consola.

Por qué existe: un modelo que contesta «¿cuál es mi frecuencia cardiaca?» con lo que recuerda, o
con lo que le parece razonable, inventa. Aquí se compone, sin escribir nada, lo que las rutas ya
sirven a la consola —el resumen de `Advisor.summarize`, las alertas con sus frases, la trayectoria
de cada dominio, la última lectura de cada indicador y la del día antes, las rutinas que no van al
día y la crónica—, y ese texto es todo el mundo del modelo. La barrera de cifras compara su
respuesta con este mismo texto: una cifra que no esté aquí no se dice.

TIERRA VE LO QUE HA LLEGADO. Con `console="ground"` el corte es el de la consola de Tierra
(`frontend/src/lib/crew.ts::groundCut`): el instante de la última lectura de a bordo menos un
tiempo de luz, y todo se evalúa con `until` en ese corte, como hacen las rutas de Tierra. Sin
efemérides no hay retardo y Tierra ve hasta la última lectura, igual que la consola.

NI UNA ESCRITURA. No llama a `crew_status`, que a bordo firma instantáneas de proyección
(`record-integrity.md` §3.18): usa la evaluación (`routes._assess`) y las piezas de solo lectura
que ya comparte la crónica (`routes.chronicle_status`). Lo comprueba
`tests/test_assistant.py::test_a_turn_writes_nothing_in_the_ledger`.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

from app.advisor.recommendations import Advisor
from app.analysis.risk import RiskLevel
from app.api import routes
from app.core import display, i18n
from app.core.config import Settings
from app.core.i18n import tr
from app.core.storage import ObservationStore
from app.ingest.codes import Domain, get
from app.ingest.fhir import VitalObservation

# Lo que se le da al modelo, como mucho. Con el contexto de 8192 tokens del cliente local caben
# de sobra el sistema, el catálogo, ocho turnos de historial y esto.
MAX_CONTEXT_CHARS = 6000
MAX_LINE_CHARS = 300
# Cuántas frases de cambio y de tendencia por alerta, y cuántos hechos de la crónica.
PER_ALERT = 3
CHRONICLE_EVENTS = 6
RECOMMENDATIONS = 3
DAY = dt.timedelta(days=1)


@dataclass
class AssistantContext:
    """El texto del backend por apartados, y lo que la propuesta de escritura necesita leer."""

    subject: str
    console: str
    cut: dt.datetime | None = None
    summary: str = ""
    alert_lines: list[str] = field(default_factory=list)
    # Solo el titular de cada alerta (dominio, nivel, si está reconocida): lo que se lee en voz
    # alta sin modelo, que con todas sus frases sería un párrafo.
    alert_headlines: list[str] = field(default_factory=list)
    domain_lines: list[str] = field(default_factory=list)
    recommendation_lines: list[str] = field(default_factory=list)
    readings: dict[str, str] = field(default_factory=dict)
    # Las mismas lecturas por piezas (nombre, valor, instante, valor y instante de un día antes):
    # el texto del modelo las agrupa por instante para no repetir la fecha en cada una (medido el
    # 2026-11-04: la mitad del contexto eran fechas repetidas, y el modelo local evalúa el prompt
    # entero en cada turno).
    reading_rows: dict[str, tuple[str, str, str, str | None, str | None]] = field(
        default_factory=dict)
    routine_lines: list[str] = field(default_factory=list)
    chronicle_lines: list[str] = field(default_factory=list)
    # Las alertas tal cual (dominio, nivel, instante del estado): las lee la propuesta de
    # reconocer una alerta, que no inventa ni el nivel ni el instante.
    alerts: list[dict[str, Any]] = field(default_factory=list)
    reference_time: dt.datetime | None = None
    empty_reason: str | None = None
    # La dosis de carrera como la pinta «Radiación» (`DoseMeter`): la cifra y el límite, o que no
    # se ha facilitado (sin dato no hay cero). «¿Cuánta radiación llevo?» se contesta con esto.
    dose_line: str = ""
    # El aire de la cabina como lo da `GET /api/habitat`: la última lectura de cada parámetro y lo
    # que está fuera de límite ahora. «¿Cómo está el aire de la nave?» se contesta con esto.
    habitat_lines: list[str] = field(default_factory=list)

    def text(self) -> str:
        """Todo, recortado: primero lo que más se pregunta."""
        parts: list[str] = []
        if self.cut is not None:
            parts.append(tr(f"Consola de Tierra: datos recibidos hasta {_when(self.cut)}.",
                            f"Earth console: data received up to {_when(self.cut)}."))
        if self.empty_reason:
            parts.append(self.empty_reason)
        if self.summary:
            parts.append(tr(f"Resumen del estado: {self.summary}",
                            f"Status summary: {self.summary}"))
        parts += self.alert_lines or ([] if self.empty_reason else [
            tr("Sin alertas activas.", "No active alerts.")])
        if self.dose_line:
            parts.append(self.dose_line)
        parts += self.habitat_lines
        last = tr("Última lectura.", "Latest reading.")
        parts += (_grouped(self.reading_rows) if self.reading_rows
                  else [f"{last} {line}" for line in self.readings.values()])
        parts += self.routine_lines
        parts += self.domain_lines
        parts += self.recommendation_lines
        parts += self.chronicle_lines
        out: list[str] = []
        used = 0
        for part in parts:
            # Las listas compuestas aquí (lecturas agrupadas, aire de la cabina) llevan su propio
            # tope: recortarlas dejaría fuera la cifra que se pregunta.
            grouped = part.startswith(_GROUPED_HEADS)
            limit = MAX_GROUPED_CHARS if grouped else MAX_LINE_CHARS
            line = part if len(part) <= limit else part[: limit - 1] + "…"
            if used + len(line) + 1 > MAX_CONTEXT_CHARS:
                break
            out.append(line)
            used += len(line) + 1
        return "\n".join(out)


# Cómo empiezan las listas compuestas aquí, en los dos idiomas: `text` no las recorta como a una
# línea suelta. Son los comienzos de `_grouped` y de `_habitat`.
_GROUPED_HEADS = ("Últimas lecturas (", "Hábitat, aire de la cabina",
                  "Latest readings (", "Habitat, cabin air")


def _when(instant: dt.datetime) -> str:
    return instant.astimezone(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")


def _level_word(level: str) -> str:
    try:
        return RiskLevel(level).display
    except ValueError:
        return level


def _domain_word(domain: str) -> str:
    try:
        return Domain(domain).display
    except ValueError:
        return domain


def _shown(reading: VitalObservation) -> str:
    code = get(reading.key)
    value = display.number(reading.value, display.decimals_for(reading.key))
    return f"{value} {display.unit(code.unit)}".strip()


Row = tuple[str, str, str, str | None, str | None]
# Cuántas lecturas por línea del texto agrupado: el tope de una línea es `MAX_GROUPED_CHARS`.
PER_GROUPED_LINE = 6
MAX_GROUPED_CHARS = 600


def _readings(observations: list[VitalObservation]) -> tuple[dict[str, str], dict[str, Row]]:
    """La última lectura de cada indicador y la más cercana a un día antes, si la hay: en una
    frase por indicador (lo que se dice tal cual) y por piezas (lo que se agrupa para el modelo)."""
    by_key: dict[str, list[VitalObservation]] = {}
    for reading in observations:
        by_key.setdefault(reading.key, []).append(reading)
    lines: dict[str, str] = {}
    rows: dict[str, Row] = {}
    for key, readings in by_key.items():
        readings.sort(key=lambda item: item.effective)
        last = readings[-1]
        line = f"{get(key).display_es}: {_shown(last)} ({_when(last.effective)})"
        before = [item for item in readings if item.effective <= last.effective - DAY]
        row: Row = (get(key).display_es, _shown(last), _when(last.effective), None, None)
        if before:
            day_before = before[-1]
            line += tr(f"; un día antes, {_shown(day_before)} ({_when(day_before.effective)})",
                       f"; one day earlier, {_shown(day_before)} ({_when(day_before.effective)})")
            row = (*row[:3], _shown(day_before), _when(day_before.effective))
        lines[key] = line + "."
        rows[key] = row
    return lines, rows


def _grouped(rows: dict[str, Row]) -> list[str]:
    """Las lecturas agrupadas por instante: la fecha una vez por grupo, no una vez por lectura."""
    groups: dict[tuple[str, str | None], list[Row]] = {}
    for row in rows.values():
        groups.setdefault((row[2], row[4]), []).append(row)
    out: list[str] = []
    for (when, before_when), members in groups.items():
        head = tr(f"Últimas lecturas ({when}", f"Latest readings ({when}")
        head += (tr(f"; entre paréntesis, la de un día antes, {before_when}):",
                    f"; in parentheses, the one from a day earlier, {before_when}):")
                 if before_when else "):")
        for start in range(0, len(members), PER_GROUPED_LINE):
            said = "; ".join(
                f"{name} {value}" + (f" ({before})" if before is not None else "")
                for name, value, _, before, _ in members[start:start + PER_GROUPED_LINE]
            )
            out.append(f"{head} {said}.")
    return out


def _alerts(context: AssistantContext, status: dict[str, Any]) -> None:
    for alert in status.get("alerts") or []:
        domain, level = str(alert["domain"]), str(alert["level"])
        context.alerts.append(alert)
        state = (tr("reconocida", "acknowledged") if alert.get("acknowledged")
                 else tr("sin reconocer", "not acknowledged"))
        line = tr(f"Alerta de {_domain_word(domain)}: {_level_word(level)}, {state}.",
                  f"{_domain_word(domain)} alert: {_level_word(level)}, {state}.")
        context.alert_headlines.append(line)
        detail = alert.get("detail") or {}
        said = [str(item["description"]) for item in detail.get("changed") or []
                if item.get("description")][:PER_ALERT]
        said += [str(item["description"]) for item in detail.get("trends") or []
                 if item.get("description")][:PER_ALERT]
        if said:
            line += " " + "; ".join(said) + "."
        context.alert_lines.append(line)
    for domain, item in (status.get("domains") or {}).items():
        trajectory = (item or {}).get("trajectory") or {}
        if trajectory.get("display"):
            context.domain_lines.append(
                tr(f"Dominio {_domain_word(domain)}: {trajectory['display']}.",
                   f"{_domain_word(domain)} domain: {trajectory['display']}.")
            )


def _routines(context: AssistantContext, body: dict[str, Any]) -> None:
    late = [item for item in body.get("routines") or []
            if item.get("state") not in ("al-dia", None) and not item.get("suspended")]
    if not body.get("routines"):
        return
    if not late:
        context.routine_lines.append(tr("Rutinas: todas las medidas periódicas al día.",
                                        "Routines: every periodic measurement is up to date."))
        return
    for item in late:
        state = str(item["state"]).replace("-", " ")
        if i18n.current() == "en":
            state = _ROUTINE_STATES_EN.get(str(item["state"]), state)
        context.routine_lines.append(
            tr(f"Rutina {item.get('display_es') or item['key']}: {state}.",
               f"Routine {item.get('display_es') or item['key']}: {state}."))


# Los estados de una rutina son identificadores de Polaris (`estado_rutina.clasificar`): en
# castellano se leen quitándoles el guion; en inglés se dicen con estas palabras. Uno que no esté
# aquí se dice como en castellano antes que callarlo.
_ROUTINE_STATES_EN = {
    "atrasada": "overdue",
    "rota": "broken (its last run cannot be taken as good)",
    "nunca-corrio": "never run",
}


def _dose(assessed: routes._Assessment) -> str:
    """La dosis de carrera del panel «Radiación»: la cifra si se ha facilitado; si no, lo dice."""
    limit = assessed.status.dose_limit_msv
    limit_text = f"{display.number(limit, 0)} mSv"
    if assessed.cumulative_dose_msv is None:
        return tr(f"Dosis de carrera acumulada: sin dato, no se ha facilitado y no se supone cero; "
                  f"el límite de carrera es {limit_text} (panel «Radiación»).",
                  f"Cumulative career radiation dose: no data, not provided and zero is not "
                  f"assumed; the career limit is {limit_text} («Radiation» panel).")
    percent = display.number(assessed.status.dose_fraction * 100, 1)
    dose = display.number(assessed.cumulative_dose_msv, 1)
    return tr(f"Dosis de carrera acumulada: {dose} mSv "
              f"de {limit_text}, el {percent} % del límite (panel «Radiación»).",
              f"Cumulative career radiation dose: {dose} mSv "
              f"of {limit_text}, {percent} % of the limit («Radiation» panel).")


def _habitat_figure(value: float, ucum: str) -> str:
    # Los decimales de la consola (`habitat/flow.ts::decimalsFor`): las cifras pequeñas, con dos.
    shown = display.number(value, 2 if abs(value) < 1 else 1)
    return f"{shown} {display.unit(ucum)}".strip()


def _habitat(store: ObservationStore, until: dt.datetime | None) -> list[str]:
    """El aire de la cabina de `GET /api/habitat`: la última lectura y lo fuera de límite ahora."""
    # Import tardío: la ruta del hábitat importa `routes`, como este módulo.
    from app.environment.habitat import cabin_readings, excursions, latest_by_parameter
    from app.environment.habitat import parameter as habitat_parameter

    readings = store.habitat_readings(until=until)
    cabin = cabin_readings(readings)
    if not cabin:
        return [tr("Hábitat: no hay lecturas del aire de la cabina.",
                   "Habitat: there are no cabin air readings.")]
    reference = max(item.effective for item in cabin)
    latest = sorted(latest_by_parameter(cabin).values(),
                    key=lambda item: (item.module, item.parameter))
    said = "; ".join(
        f"{spec.display} {_habitat_figure(item.value, spec.unit)}"
        for item, spec in ((item, habitat_parameter(item.parameter)) for item in latest)
    )
    lines = [tr(f"Hábitat, aire de la cabina, última lectura ({_when(reference)}): {said}.",
                f"Habitat, cabin air, latest reading ({_when(reference)}): {said}.")]
    active = [item for item in excursions(readings)
              if item.kind == "health" and item.end >= reference - dt.timedelta(hours=1)]
    if active:
        lines.append(tr("Hábitat, fuera de límite ahora: ", "Habitat, out of limits now: ")
                     + "; ".join(habitat_parameter(item.parameter).display for item in active)
                     + ".")
    else:
        lines.append(tr("Hábitat: ningún parámetro del aire de la cabina fuera de límite ahora.",
                        "Habitat: no cabin air parameter is out of limits now."))
    return lines


def _assess(
    settings: Settings, store: ObservationStore, subject: str, until: dt.datetime | None
) -> routes._Assessment | None:
    try:
        return routes._assess(settings, store, subject, None, None, until)
    except HTTPException:
        return None


def ground_cut(assessed: routes._Assessment) -> dt.datetime | None:
    """El corte de Tierra: la última lectura de a bordo menos un tiempo de luz (`groundCut`)."""
    comms = assessed.status.comms
    if comms is None:
        return None
    return assessed.latest - dt.timedelta(minutes=comms.one_way_minutes)


# LA EVALUACIÓN SE REUTILIZA ENTRE TURNOS SEGUIDOS. Casi todo el tiempo de un turno era evaluar el
# estado otra vez (medido el 2026-11-03: 6-15 s por turno con datos). Mientras el registro no
# cambia, el contexto tampoco: se guarda por almacén (y su época), tripulante, consola y número de
# asientos del registro, y cualquier anexo —una lectura, un reconocimiento, un nivel de misión—
# cambia ese número y lo invalida. Con un plazo corto además, porque la crónica y la vigencia de un
# evento solar dependen también de la hora.
CACHE_SECONDS = 60.0
CACHE_ENTRIES = 8
# El contexto es texto, y el texto tiene idioma: la clave lleva también el de la petición (detrás
# de lo de `_cache_key`), para que un turno en inglés no reciba el contexto compuesto en castellano.
_cache: dict[tuple[int, int, int, int, str, str, str], tuple[float, AssistantContext]] = {}
_cache_lock = threading.Lock()


def _cache_key(settings: Settings, store: ObservationStore, subject: str,
               console: str) -> tuple[int, int, int, int, str, str]:
    return (id(settings), id(store), store.epoch, len(store.ledger), subject, console)


def build(
    settings: Settings, store: ObservationStore, subject: str, console: str
) -> AssistantContext:
    """El contexto de un turno, reutilizado mientras el registro no cambie (ver arriba)."""
    key = (*_cache_key(settings, store, subject, console), str(i18n.current()))
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    context = _build(settings, store, subject, console)
    with _cache_lock:
        # Lo de otro tamaño del registro ya no vale: se tira, y se queda en unas pocas entradas.
        for old in [k for k in _cache if k[:3] == key[:3] and k[3] != key[3]]:
            del _cache[old]
        _cache[key] = (now, context)
        while len(_cache) > CACHE_ENTRIES:
            del _cache[min(_cache, key=lambda k: _cache[k][0])]
    return context


def member_line(settings: Settings, store: ObservationStore, member: str, console: str) -> str:
    """El estado de otro tripulante como lo da su propia consola, con su nombre delante.

    Para «¿qué tal está mi compañero?»: el contexto de cada turno es el de UN tripulante, y su
    texto no vale para otro. Esto es el resumen de `Advisor.summarize` y los titulares de las
    alertas DE ESE TRIPULANTE (con el corte de Tierra si la consola es la de Tierra), compuestos
    como para su propia consola y reutilizados de la misma caché. Se calcula solo cuando alguien
    pregunta por otra persona: evaluar a toda la tripulación en cada turno costaría segundos.
    """
    other = build(settings, store, member, console)
    said = other.summary or other.empty_reason or tr("sin estado que leer", "no status to read")
    alerts = " ".join(other.alert_headlines)
    return f"{member}: {said}{' ' + alerts if alerts else ''}"


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _build(
    settings: Settings, store: ObservationStore, subject: str, console: str
) -> AssistantContext:
    """El contexto de un turno. No escribe nada; sin lecturas, lo dice."""
    context = AssistantContext(subject=subject, console=console)
    onboard = _assess(settings, store, subject, None)
    if onboard is None:
        context.empty_reason = tr(f"No hay lecturas que analizar de {subject}.",
                                  f"There are no readings to analyse for {subject}.")
        return context
    until: dt.datetime | None = None
    assessed: routes._Assessment | None = onboard
    if console == "ground":
        until = ground_cut(onboard)
        context.cut = until
        if until is not None:
            assessed = _assess(settings, store, subject, until)
    if assessed is None:
        context.empty_reason = tr("A Tierra aún no ha llegado ninguna lectura de este tripulante.",
                                  "No reading from this crew member has reached Ground yet.")
        return context
    context.reference_time = assessed.latest
    context.summary = Advisor().summarize(assessed.status)
    status = routes.chronicle_status(settings, store, subject, until, assessed)
    _alerts(context, status)
    context.readings, context.reading_rows = _readings(assessed.observations)
    context.dose_line = _dose(assessed)
    context.habitat_lines = _habitat(store, until)
    for item in Advisor().recommend(assessed.status, routes._driver_keys(assessed))[
        :RECOMMENDATIONS
    ]:
        context.recommendation_lines.append(
            tr(f"Qué hacer ({_domain_word(str(item.domain))}): {item.action}",
               f"What to do ({_domain_word(str(item.domain))}): {item.action}")
        )
    # Imports tardíos: estos módulos de rutas importan `routes`, como este.
    from app import timeline
    from app.api.alert_history import history_view
    from app.api.mission import latest_mission_history
    from app.api.timeline import read_routines

    with contextlib.suppress(HTTPException):
        _routines(context, read_routines(store, settings, subject, until))
    # La crónica de `api/timeline.py::chronicle_view` sobre la evaluación que ya está hecha:
    # llamarla evaluaba otra vez todo el historial en cada turno (revisión de código del
    # 2026-11-03). Sin los momentos de «Cuerpo», que el asistente no lee.
    try:
        history = history_view(settings, store, subject, until, assessed)
    except HTTPException:
        history = None
    chronicle = timeline.chronicle(
        store, subject, status, timeline.as_of(status, until, routes._now()),
        settings.mission_start, settings.mission_days, until, history, None,
        assessed.stored, latest_mission_history(store, subject, until),
    )
    events = chronicle.get("events") or []
    for event in events[-CHRONICLE_EVENTS:]:
        context.chronicle_lines.append(
            tr(f"Crónica, {event.get('fecha')}: {event.get('que')}.",
               f"Chronicle, {event.get('fecha')}: {event.get('que')}."))
    return context
