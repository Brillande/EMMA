"""Dónde está un tripulante en un instante, de dónde sale y cómo se dice cuando no se sabe.

POR QUÉ EXISTE
--------------
La regla vivía en `api/habitat.py` (`_location_at`) y sus palabras en `api/crew_radiation.py`.
Cuando la pidió también el estado (`GET /api/status`, `mission.location`, para el panel
«Sububicación» del inicio, que decía «el backend no lo da»), `routes.py` no podía importarlas: los
dos módulos importan `routes`. Aquí no dependen de ninguna ruta, y las tres vistas —tripulación,
radiación de la tripulación y estado— dicen de la ubicación lo mismo, con las mismas palabras.

DE DÓNDE SALE (decisión del usuario, 2026-11-10: «no las queremos simuladas, las queremos reales»)
--------------------------------------------------------------------------------------------------
Hay dos fuentes, y ninguna es el simulador:

- **La consola**: una persona declara el módulo, firmado (`POST /api/mission/events`).
- **Las anclas de módulo**: emisores fijos de la NAVE (BLE hoy; UWB o el RFID de la nave podrían
  entrar por el mismo contrato), cada uno declarado en un módulo por la consola
  (`POST /api/location/anchors`). El wearable o una pasarela solo ESCUCHAN y mandan lo que oyen
  (`POST /api/location/sightings`, firmado como `location-anchors`). EMMA no añade emisores ni
  pilas: un emisor nuevo a bordo tendría que pasar EMC y la norma de baterías, y el patrón que sí
  voló (REALM-1, DLR Wireless Compose) es el de anclas de la nave. La viabilidad, con sus fuentes,
  está en `compliance/location-sensing-feasibility.md` y en `data/location_sensing.json`.

CÓMO SE ESTIMA (`estimate`, función pura)
-----------------------------------------
La granularidad es el MÓDULO, nunca metros. En cada instante con lecturas se mira la ventana
`window_s` anterior; de cada módulo cuenta la señal más fuerte de sus anclas (por encima de
`min_rssi_dbm`). Si el primero saca al segundo `margin_db` o más, ese módulo; si no, los dos
compiten y el tramo queda **indeterminado entre módulos**: no se fuerza una respuesta. Para dejar
el módulo vigente (por otro o por la indeterminación) el cambio tiene que durar `min_dwell_s`
(histéresis: un cuerpo que tapa un ancla un instante no mueve a nadie). Sin lecturas durante
`stale_after_s`, la estimación caduca. Un ancla que nadie ha declarado se guarda pero no se usa.
Los cinco parámetros son **sin respaldo: calibrar en cada nave**.

QUÉ MANDA
---------
`context.prevailing`, la única regla: la consola sobre las anclas, aunque sea anterior; entre dos
del mismo tipo, la de asiento posterior. Es descriptiva: no firma nada ni entra en ningún nivel
ni en ninguna alerta (invariante 5); solo ordena hipótesis.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from functools import cache
from itertools import groupby
from pathlib import Path
from typing import Any

from app.analysis.context import ANCHOR_LOCATION, CONSOLE_LOCATION, Stay, prevailing
from app.core import i18n
from app.environment.habitat import MODULES, module_display

SENSING_PATH = Path(__file__).resolve().parents[1] / "data" / "location_sensing.json"

LOCATION_BASIS = (
    "la ubicación del instante de referencia: la que declara una persona en la consola o, si no "
    "hay ninguna, la que estiman las anclas de módulo de la nave por la señal más fuerte (solo el "
    "módulo, no una posición en metros; sin validar dentro de un módulo metálico). Manda la de "
    "la consola aunque sea anterior. No entra en ningún nivel ni en ninguna alerta"
)
LOCATION_MISSING = "ubicación sin declarar ni estimar"
LOCATION_UNAVAILABLE = (
    "ubicación sin declarar; la medida no está disponible: no hay anclas de módulo declaradas"
)
i18n.en_many({
    LOCATION_BASIS: (
        "the location at the reference time: the one a person declares in the console or, if "
        "there is none, the one the ship's module anchors estimate from the strongest signal "
        "(the module only, not a position in metres; not checked inside a metal module). The "
        "console one prevails even if it is earlier. It does not enter any level or any alert"
    ),
    LOCATION_MISSING: "location neither declared nor estimated",
    LOCATION_UNAVAILABLE: (
        "location not declared; the measurement is not available: no module anchors have been "
        "declared"
    ),
})

# Los seis estados de `mission.location_state` (contrato con la interfaz).
DECLARED = "declared"
ESTIMATED = "estimated"
AMBIGUOUS = "ambiguous"
STALE = "stale"
UNAVAILABLE = "unavailable"
MISSING = "missing"
STATES = (DECLARED, ESTIMATED, AMBIGUOUS, STALE, UNAVAILABLE, MISSING)

@dataclass(frozen=True, slots=True)
class Sensing:
    """Los parámetros de la estimación, de `data/location_sensing.json`."""

    window_s: float
    margin_db: float
    min_dwell_s: float
    stale_after_s: float
    min_rssi_dbm: float
    evidence: str
    evidence_note: str
    not_coded: str
    basis: tuple[dict[str, Any], ...]

    @property
    def lookback(self) -> dt.timedelta:
        """Cuánto hay que leer hacia atrás para decir el estado de un instante.

        La ventana y la permanencia para decidir, y dos caducidades: una para que lo vigente
        pueda seguir vigente y otra para poder decir «caducada» en vez de «sin estimar».
        """
        return dt.timedelta(
            seconds=self.window_s + self.min_dwell_s + 2 * self.stale_after_s
        )


def sensing(path: Path = SENSING_PATH) -> Sensing:
    """Los parámetros, con sus textos en el idioma de la petición.

    Lo leído y validado se cachea en castellano (`_read_sensing`); el inglés, que está en el
    hermano `location_sensing.en.json`, se pone aquí, al salir, y no dentro de lo cacheado: así
    quien lo sirve (`api/location_anchors.py`) no tiene que saber de idiomas. Las cifras y
    `evidence` (un identificador) no cambian.
    """
    params = _read_sensing(path)
    if i18n.current() != "en":
        return params
    return replace(
        params,
        evidence_note=i18n.localized(params.evidence_note, path),
        not_coded=i18n.localized(params.not_coded, path),
        basis=i18n.localized(params.basis, path),
    )


@cache
def _read_sensing(path: Path) -> Sensing:
    raw = json.loads(path.read_text(encoding="utf-8"))
    values = {
        key: float(raw[key])
        for key in ("window_s", "margin_db", "min_dwell_s", "stale_after_s", "min_rssi_dbm")
    }
    if values["window_s"] <= 0 or values["stale_after_s"] <= 0:
        raise ValueError("location_sensing.json: la ventana y la caducidad tienen que ser > 0")
    if values["margin_db"] < 0 or values["min_dwell_s"] < 0:
        raise ValueError("location_sensing.json: el margen y la permanencia no pueden ser < 0")
    return Sensing(
        **values,
        evidence=raw["evidence"],
        evidence_note=raw["evidence_note"],
        not_coded=raw["not_coded"],
        basis=tuple(raw["basis"]),
    )


@dataclass(frozen=True, slots=True)
class Anchor:
    """Un ancla declarada en un módulo desde un instante, por el asiento `order`."""

    anchor_id: str
    module: str
    since: dt.datetime
    order: int


@dataclass(frozen=True, slots=True)
class Sighting:
    """Lo que oyó el receptor de un tripulante: un ancla, su señal y cuándo."""

    anchor_id: str
    rssi_dbm: float
    at: dt.datetime
    order: int


@dataclass(frozen=True, slots=True)
class Undecided:
    """Un tramo en que las anclas de dos o más módulos se oyen casi igual: no se decide."""

    start: dt.datetime
    end: dt.datetime
    modules: tuple[str, ...]
    last_seen: dt.datetime


@dataclass(frozen=True, slots=True)
class Whereabouts:
    """Todo lo que se sabe de dónde estuvo un tripulante: lo declarado y lo estimado.

    `anchors` dice si había alguna ancla declarada: sin ninguna, la medida no está disponible.
    """

    stays: list[Stay] = field(default_factory=list)
    undecided: list[Undecided] = field(default_factory=list)
    anchors: bool = False


def module_of(anchors: Sequence[Anchor], anchor_id: str, at: dt.datetime) -> str | None:
    """El módulo de un ancla en ese instante: de sus declaraciones con `since` ≤ `at`, la última.

    Una lectura antigua se juzga con el ancla que valía en SU instante, como un vínculo de
    sensor (`ingest/bindings.py`). Sin ninguna, None: el ancla es desconocida y no se usa.
    """
    valid = [item for item in anchors if item.anchor_id == anchor_id and item.since <= at]
    if not valid:
        return None
    return max(valid, key=lambda item: item.order).module


@dataclass(slots=True)
class _Segment:
    """Un tramo abierto mientras se recorre: un módulo o la indeterminación (`module` None)."""

    module: str | None
    modules: tuple[str, ...]
    start: dt.datetime
    last_seen: dt.datetime
    order: int


def _observed(
    window: Sequence[tuple[Sighting, str]], margin: float
) -> tuple[str | None, tuple[str, ...]]:
    """Lo que dice una ventana: el módulo que gana por `margin`, o None y los que compiten."""
    best: dict[str, float] = {}
    for sighting, module in window:
        best[module] = max(best.get(module, -math.inf), sighting.rssi_dbm)
    ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))
    top = ranked[0][1]
    if len(ranked) == 1 or top - ranked[1][1] >= margin:
        return ranked[0][0], (ranked[0][0],)
    return None, tuple(sorted(module for module, value in ranked if top - value < margin))


def estimate(
    sightings: Sequence[Sighting], anchors: Sequence[Anchor], params: Sensing | None = None
) -> tuple[list[Stay], list[Undecided]]:
    """Los módulos estimados (`Stay` con `source="anchors"`) y los tramos sin decidir.

    Función pura: las mismas lecturas y anclas dan siempre lo mismo. Reglas en la cabecera.
    """
    params = params or sensing()
    window = dt.timedelta(seconds=params.window_s)
    dwell = dt.timedelta(seconds=params.min_dwell_s)
    stale = dt.timedelta(seconds=params.stale_after_s)
    usable: list[tuple[Sighting, str]] = []
    for item in sightings:
        module = module_of(anchors, item.anchor_id, item.at)
        if module is not None and module in MODULES and item.rssi_dbm >= params.min_rssi_dbm:
            usable.append((item, module))
    usable.sort(key=lambda pair: (pair[0].at, pair[0].order))

    closed: list[tuple[_Segment, dt.datetime]] = []
    current: _Segment | None = None
    # La desviacion en curso: desde cuando se oye sin cortes lo MISMO distinto de lo vigente.
    deviating: dt.datetime | None = None
    pending: str | None = None
    heard: dt.datetime | None = None
    low = 0
    for moment, group in groupby(usable, key=lambda pair: pair[0].at):
        order = max(pair[0].order for pair in group)
        while usable[low][0].at < moment - window:
            low += 1
        high = low
        while high < len(usable) and usable[high][0].at <= moment:
            high += 1
        module, modules = _observed(usable[low:high], params.margin_db)
        # Caduca si no se ha oido NADA en `stale_after_s` (no solo el modulo vigente): mientras
        # llegan lecturas de otro modulo, lo que decide es la permanencia, no la caducidad.
        if current is not None and heard is not None and moment - heard > stale:
            closed.append((current, current.last_seen + stale))
            current, deviating = None, None
        heard = moment
        if current is None:
            current = _Segment(module, modules, moment, moment, order)
            continue
        if module == current.module:
            current.last_seen, current.order, current.modules = moment, order, modules
            deviating = None
            continue
        # Un cambio es a UN destino: si lo que se oye cambia otra vez, la cuenta empieza de nuevo.
        if deviating is None or module != pending:
            deviating, pending = moment, module
        if moment - deviating >= dwell:
            closed.append((current, deviating))
            current = _Segment(module, modules, deviating, moment, order)
            deviating = None
    if current is not None:
        closed.append((current, current.last_seen + stale))

    stays: list[Stay] = []
    undecided: list[Undecided] = []
    for segment, end in closed:
        if segment.module is None:
            undecided.append(Undecided(segment.start, end, segment.modules, segment.last_seen))
        else:
            stays.append(Stay(
                module=segment.module, start=segment.start, end=end, order=segment.order,
                source=ANCHOR_LOCATION, last_seen=segment.last_seen,
            ))
    return stays, undecided


def location_at(stays: Sequence[Stay], moment: dt.datetime) -> dict[str, Any] | None:
    """El módulo de ese instante (el que manda según `prevailing`), o None.

    `source` dice de dónde sale (`console` o `anchors`) y `last_seen`, en una estimada, la última
    lectura que la sostiene: la interfaz no puede presentar una estimada como la declaración de
    una persona, ni sin su antigüedad.
    """
    covering = [item for item in stays if item.start <= moment <= item.end]
    if not covering:
        return None
    return _location(prevailing(covering))


def _location(stay: Stay) -> dict[str, Any]:
    return {
        "module": stay.module,
        "display": i18n.loc(module_display(stay.module)),
        "start": stay.start.isoformat(),
        "end": stay.end.isoformat(),
        "ledger_index": stay.order,
        "source": stay.source,
        "last_seen": None if stay.last_seen is None else stay.last_seen.isoformat(),
    }


def _modules_text(modules: Sequence[str]) -> str:
    names = [i18n.loc(module_display(item)) for item in modules]
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} {i18n.tr('y', 'and')} {names[-1]}"


def view(whereabouts: Whereabouts, moment: dt.datetime) -> dict[str, Any]:
    """`location`, `location_state`, `location_missing_text` y `location_basis` de un instante.

    - `declared` / `estimated`: hay una que manda en ese instante (consola o anclas).
    - `ambiguous`: las anclas no deciden entre módulos; `location` null y el texto los nombra.
    - `stale`: lo último de las anclas caducó antes del instante. Si lo último era un módulo, va
      en `location` con su `last_seen`, para que se vea qué era y de cuándo; el texto lo dice.
    - `missing`: hay anclas declaradas pero nada de ellas ni de la consola para ese instante.
    - `unavailable`: nada de la consola y ninguna ancla declarada: no se puede medir.
    """
    location = location_at(whereabouts.stays, moment)
    if location is not None:
        state = DECLARED if location["source"] == CONSOLE_LOCATION else ESTIMATED
        return _view(location, state, None)
    for item in whereabouts.undecided:
        if item.start <= moment <= item.end:
            return _view(None, AMBIGUOUS, i18n.tr(
                "ubicación indeterminada: las anclas de "
                f"{_modules_text(item.modules)} se oyen casi igual y no se elige entre ellas",
                "location undetermined: the anchors of "
                f"{_modules_text(item.modules)} are heard almost equally and none is chosen",
            ))
    past: list[Stay | Undecided] = [
        *(item for item in whereabouts.stays if item.source == ANCHOR_LOCATION),
        *whereabouts.undecided,
    ]
    before = [item for item in past if item.end < moment]
    if before:
        last = max(before, key=lambda item: item.end)
        minutes = round(sensing().stale_after_s / 60)
        text = i18n.tr(
            f"estimación caducada: más de {minutes} min sin lecturas de las anclas de módulo",
            f"estimate expired: more than {minutes} min without readings from the module anchors",
        )
        return _view(_location(last) if isinstance(last, Stay) else None, STALE, text)
    if whereabouts.anchors:
        return _view(None, MISSING, LOCATION_MISSING)
    return _view(None, UNAVAILABLE, LOCATION_UNAVAILABLE)


def _view(location: dict[str, Any] | None, state: str, text: str | None) -> dict[str, Any]:
    return {
        "location": location,
        "location_state": state,
        # Las dos frases fijas (`LOCATION_MISSING`, `LOCATION_UNAVAILABLE`) y la base llegan
        # como constantes castellanas: se resuelven aquí, al servir.
        "location_missing_text": None if text is None else i18n.loc(text),
        "location_basis": i18n.loc(LOCATION_BASIS),
    }
