"""NASA DONKI: meteorologia espacial y alertas de radiacion solar.

Un evento de particulas energeticas solares (SPE) es la amenaza aguda de
radiacion de una mision: obliga a refugiarse en cuestion de minutos u horas.
Este cliente trae los eventos reales para alimentar la alerta.

HALLAZGOS del spike:
  - `linkedEvents` encadena un SPE con la CME que lo origino: permite reconstruir
    la cascada completa fulguracion -> CME -> SPE.
  - `sentNotifications` trae los mensajes de alerta reales de NASA.
  - Los SEP son escasos: una ventana de 30 dias puede devolver cero. Para la demo
    hay que cachear un periodo con eventos, no confiar en "los ultimos 30 dias".

INSTANTANEA FECHADA PARA LA DEMO SIN RED (2026-11-04)
-----------------------------------------------------
El instalador arranca con la cache vacia: sin red, la consola decia «sin datos de NASA DONKI» y
el evento solar no se veia en ninguna demo. `app/data/donki_snapshot.json` es una respuesta real
de DONKI (los SEP del ultimo año), escrita tal cual por `scripts/fetch_donki_snapshot.py` con la
URL de la consulta, la fecha de descarga y la licencia. Se usa solo si se pide
(`EMMA_DONKI_SNAPSHOT=true`, lo pone la aplicacion de escritorio), sin red (modo offline o red
caida) y sin cache: nunca tapa un dato en vivo ni una cache. Su edad es la de la descarga, asi que
sale caducada (cian) con su fecha, y la fuente lo dice: «instantanea de DONKI del <fecha>, no en
vivo». Sus eventos conservan su fecha real: uno de hace meses no es un evento activo, y la
instantanea no se mueve en el tiempo para parecerlo.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any

import httpx

from app.core import egress, i18n
from app.core.cache import CachedPayload, FileCache, OfflineDataUnavailable
from app.core.config import Settings, get_settings
from app.environment.ephemeris import utc_today

BASE_URL = "https://api.nasa.gov/DONKI"
# Vigencia de una consulta (parámetro de diseño). DONKI publica un evento con decenas de minutos
# de retraso y Tierra lo ve además con el tiempo de luz; 15 min no esconde un SPE y deja la cuota
# de la `DEMO_KEY` (30 peticiones por hora e IP) muy por debajo.
FRESH_FOR = dt.timedelta(minutes=15)

# La instantanea que viaja en el paquete (ver arriba) y su licencia, declarada junto al dato.
SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "donki_snapshot.json"
SNAPSHOT_LICENCE = (
    "NASA DONKI (Community Coordinated Modeling Center, NASA Goddard), servido por api.nasa.gov: "
    "obra del Gobierno de EE. UU., sin copyright en EE. UU. (17 U.S.C. §105; directrices de uso "
    "de material de NASA, https://www.nasa.gov/nasa-brand-center/images-and-media/). Se cita la "
    "fuente y no implica respaldo de NASA."
)
i18n.en(
    SNAPSHOT_LICENCE,
    "NASA DONKI (Community Coordinated Modeling Center, NASA Goddard), served by api.nasa.gov: "
    "work of the U.S. Government, without copyright in the U.S. (17 U.S.C. §105; NASA media "
    "usage guidelines, https://www.nasa.gov/nasa-brand-center/images-and-media/). The source is "
    "cited and no endorsement by NASA is implied.",
)


#: Lo más ancho que DONKI acepta en una consulta, en días naturales contando ambos extremos.
#: api.nasa.gov responde 400 «Date range cannot exceed 60 days» (visto el 2026-11-13 al descargar
#: la instantánea): la consulta de 365 días del estado ya no servía en vivo y caía siempre a la
#: caché o a «sin datos de DONKI». Se pide por tramos de este ancho y se juntan.
MAX_RANGE_DAYS = 60


def query_ranges(start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    """La ventana `[start, end]` en tramos contiguos y sin solape de `MAX_RANGE_DAYS` como mucho."""
    ranges: list[tuple[dt.date, dt.date]] = []
    first = start
    while first <= end:
        last = min(first + dt.timedelta(days=MAX_RANGE_DAYS - 1), end)
        ranges.append((first, last))
        first = last + dt.timedelta(days=1)
    return ranges


def fetch_raw(
    settings: Settings, event_type: str, start: dt.date, end: dt.date
) -> list[dict[str, Any]]:
    """Los eventos de la ventana tal cual los da DONKI, por tramos y por la puerta de salida.

    Un tramo que falla hace fallar la consulta entera: media ventana no es «ningún evento». Un
    evento repetido entre tramos (DONKI filtra por día) sale una vez.
    """
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for first, last in query_ranges(start, end):
        response = egress.get(
            settings, "space-weather", f"{BASE_URL}/{event_type}",
            params={
                "startDate": first.isoformat(),
                "endDate": last.isoformat(),
                "api_key": settings.nasa_api_key,
            },
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            # Un 200 con un cuerpo que no es JSON (una página de error, un cuerpo vacío) no es
            # «ningún evento»: se trata como un fallo de la consulta, que usa la caché o la
            # instantánea, o dice «no disponible». Antes salía de `/api/space-weather` como un 500.
            raise httpx.DecodingError(
                f"DONKI /{event_type} respondió sin JSON utilizable: {exc}"
            ) from exc
        for item in payload if isinstance(payload, list) else []:
            identity = json.dumps(item, sort_keys=True)
            if identity not in seen:
                seen.add(identity)
                events.append(item)
    return events


class EventType(StrEnum):
    SEP = "SEP"  # solar energetic particles: la que dispara el refugio
    FLR = "FLR"  # solar flare
    CME = "CME"  # coronal mass ejection


class Severity(StrEnum):
    NOMINAL = "nominal"
    ELEVATED = "elevated"
    HIGH = "high"
    SEVERE = "severe"


# Clase de fulguracion -> severidad. Escala logaritmica: cada letra es 10x.
_FLARE_SEVERITY: dict[str, Severity] = {
    "A": Severity.NOMINAL,
    "B": Severity.NOMINAL,
    "C": Severity.ELEVATED,
    "M": Severity.HIGH,
    "X": Severity.SEVERE,
}


@dataclass(frozen=True, slots=True)
class SolarEvent:
    """Un evento de meteorologia espacial, normalizado entre tipos."""

    event_id: str
    event_type: EventType
    time: dt.datetime
    severity: Severity
    instruments: tuple[str, ...]
    linked_event_ids: tuple[str, ...]
    flare_class: str | None
    link: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": str(self.event_type),
            "time": self.time.isoformat(),
            "severity": str(self.severity),
            "instruments": list(self.instruments),
            "linked_event_ids": list(self.linked_event_ids),
            "flare_class": self.flare_class,
            "link": self.link,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SolarEvent:
        return cls(
            event_id=raw["event_id"],
            event_type=EventType(raw["event_type"]),
            time=as_utc_if_naive(dt.datetime.fromisoformat(raw["time"])),
            severity=Severity(raw["severity"]),
            instruments=tuple(raw["instruments"]),
            linked_event_ids=tuple(raw["linked_event_ids"]),
            flare_class=raw["flare_class"],
            link=raw["link"],
        )


def _parse_time(value: str) -> dt.datetime:
    """DONKI usa `2025-10-22T00:09Z`, que `fromisoformat` no acepta en 3.10.

    Una hora sin zona se rechaza: comparada luego con una con zona, lanzaba `TypeError` en cada
    `/api/status`, y guardada en caché lo seguía haciendo sin red (auditoría run-2,
    `emma:environment:naive-external-timestamp-cache-poison`).
    """
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"hora sin zona: {value!r}")
    return parsed


def as_utc_if_naive(moment: dt.datetime) -> dt.datetime:
    """Lo leído de una caché escrita antes de exigir zona: se toma como UTC, que es la de DONKI."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=dt.UTC)


def severity_from_flare_class(flare_class: str | None) -> Severity:
    if not flare_class:
        return Severity.NOMINAL
    return _FLARE_SEVERITY.get(flare_class[0].upper(), Severity.NOMINAL)


def normalize(event_type: EventType, raw: dict[str, Any]) -> SolarEvent:
    linked = tuple(
        item["activityID"] for item in (raw.get("linkedEvents") or []) if "activityID" in item
    )
    instruments = tuple(
        item["displayName"] for item in (raw.get("instruments") or []) if "displayName" in item
    )

    if event_type is EventType.SEP:
        return SolarEvent(
            event_id=raw["sepID"],
            event_type=event_type,
            time=_parse_time(raw["eventTime"]),
            # Un SPE confirmado es siempre relevante para la tripulacion.
            severity=Severity.HIGH,
            instruments=instruments,
            linked_event_ids=linked,
            flare_class=None,
            link=raw.get("link", ""),
        )
    if event_type is EventType.FLR:
        flare_class = raw.get("classType")
        return SolarEvent(
            event_id=raw["flrID"],
            event_type=event_type,
            time=_parse_time(raw["beginTime"]),
            severity=severity_from_flare_class(flare_class),
            instruments=instruments,
            linked_event_ids=linked,
            flare_class=flare_class,
            link=raw.get("link", ""),
        )
    return SolarEvent(
        event_id=raw["activityID"],
        event_type=event_type,
        time=_parse_time(raw["startTime"]),
        severity=Severity.ELEVATED,
        instruments=instruments,
        linked_event_ids=linked,
        flare_class=None,
        link=raw.get("link", ""),
    )


@dataclass(frozen=True, slots=True)
class Snapshot:
    """La instantanea fechada de DONKI: la respuesta tal cual, con de donde y cuando salio."""

    event_type: EventType
    source_url: str
    retrieved_at: dt.datetime
    start: dt.date
    end: dt.date
    licence: str
    raw: tuple[dict[str, Any], ...]

    @property
    def note(self) -> str:
        """Lo que se dice de ella donde se dice su edad: nunca se lee como dato en vivo."""
        day = f"{self.retrieved_at.astimezone(dt.UTC):%Y-%m-%d}"
        return i18n.tr(
            f"instantánea de DONKI del {day}, no en vivo",
            f"DONKI snapshot of {day}, not live",
        )

    @property
    def label(self) -> str:
        """La fuente tal como se ensena."""
        return f"NASA DONKI /{self.event_type} · {self.note}"

    def to_dict(self) -> dict[str, Any]:
        """Lo que la API declara de la instantanea, sin los eventos."""
        return {
            "label": self.label,
            "note": self.note,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at.isoformat(),
            "window": {"start": self.start.isoformat(), "end": self.end.isoformat()},
            "licence": i18n.loc(self.licence),
            "live": False,
        }


@dataclass(frozen=True, slots=True)
class SnapshotPayload(CachedPayload):
    """Un `CachedPayload` que sale de la instantanea: su edad se dice con lo que es.

    Quien enseña la edad de DONKI (el estado, el habitat, la tripulacion ante un evento) la lee
    de `describe_age`; asi todos dicen «instantánea de DONKI del <fecha>, no en vivo» sin que
    cada uno tenga que saber de donde salio el dato.
    """

    note: str = ""
    # `Snapshot.to_dict()`: de donde salio, cuando y con que licencia.
    snapshot: dict[str, Any] = field(default_factory=dict)

    def describe_age(self) -> str:
        return f"{self.note} ({CachedPayload.describe_age(self)})"


@cache
def load_snapshot(path: Path) -> Snapshot | None:
    """La instantanea del paquete, o None si no viaja. Una mal formada es un fallo, no un None."""
    if not path.exists():
        return None
    body = json.loads(path.read_text(encoding="utf-8"))
    return Snapshot(
        event_type=EventType(body["event_type"]),
        source_url=body["source_url"],
        retrieved_at=dt.datetime.fromisoformat(body["retrieved_at"]),
        start=dt.date.fromisoformat(body["window"]["startDate"]),
        end=dt.date.fromisoformat(body["window"]["endDate"]),
        licence=body["licence"],
        raw=tuple(body["raw"]),
    )


def _latest_key(event_type: EventType, start: dt.date, end: dt.date) -> str:
    """La clave de la última consulta de un tipo con una anchura de ventana (`DonkiClient._latest`).

    Por anchura y no por tipo solo: una consulta de 30 días no dice nada de los 335 de antes que
    pide el estado, y no debe sustituir a la última de 365.
    """
    return f"donki:{event_type}:latest:{(end - start).days}d"


class DonkiClient:
    """Cliente de DONKI con cache y degradacion offline."""

    def __init__(self, settings: Settings | None = None, cache: FileCache | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or FileCache(self.settings.cache_dir / "donki")

    def events(
        self, event_type: EventType, start: dt.date, end: dt.date
    ) -> CachedPayload:
        key = f"donki:{event_type}:{start.isoformat()}:{end.isoformat()}"

        cached = self.cache.get(key)
        if cached is not None and (self.settings.offline or not cached.is_stale(FRESH_FOR)):
            # Con red, una caché reciente se usa sin salir: antes cada estado de salud llamaba a
            # DONKI, y con la cuota agotada la consola esperaba. Su edad se declara igual.
            return self._rehydrate(cached)

        if self.settings.offline:
            if (fallback := self._fallback(event_type, start, end)) is not None:
                return fallback
            raise OfflineDataUnavailable(
                f"eventos {event_type} de {start} a {end} no cacheados y el sistema "
                f"está en modo offline"
            )

        try:
            raw_events = self._fetch(event_type, start, end)
            # Dentro del mismo `try`: un evento ilegible (hora sin zona, campo que falta) se trata
            # como un fallo de la consulta, con caché o instantánea, y nunca se guarda.
            try:
                events = [normalize(event_type, item) for item in raw_events]
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise httpx.DecodingError(f"DONKI /{event_type}: evento ilegible: {exc}") from exc
        except httpx.HTTPError as exc:
            # La red fallo. Un dato viejo con su edad declarada es mucho mejor
            # que ningun dato: el astronauta decide con lo que hay.
            if cached is not None:
                return self._rehydrate(cached)
            if (fallback := self._fallback(event_type, start, end)) is not None:
                return fallback
            raise OfflineDataUnavailable(
                f"DONKI inaccesible y sin cache para {event_type}: {exc}"
            ) from exc

        serialised = [event.to_dict() for event in events]
        source = f"NASA DONKI /{event_type}"
        stored = self.cache.put(key, serialised, source=source)
        self.cache.put(
            _latest_key(event_type, start, end),
            # La hora de la consulta va dentro: la de esta entrada es la de su escritura, un
            # instante después, y la edad que se declare tiene que ser la de la consulta.
            {
                "start": start.isoformat(), "end": end.isoformat(),
                "fetched_at": stored.fetched_at.isoformat(), "events": serialised,
            },
            source=source,
        )
        return CachedPayload(
            data=events, fetched_at=stored.fetched_at, source=stored.source, from_cache=False
        )

    def _fallback(
        self, event_type: EventType, start: dt.date, end: dt.date
    ) -> CachedPayload | None:
        """Sin la consulta exacta: la última consulta guardada o la instantánea, la más reciente.

        La última consulta podría ser de hace meses y la instantánea del paquete, de una versión
        instalada después: la más nueva sabe más, y cada una lleva su edad.
        """
        found = [
            payload
            for payload in (
                self._latest(event_type, start, end), self._snapshot(event_type, start, end)
            )
            if payload is not None
        ]
        return max(found, key=lambda payload: payload.fetched_at, default=None)

    def _latest(
        self, event_type: EventType, start: dt.date, end: dt.date
    ) -> CachedPayload | None:
        """La última consulta guardada con la misma anchura de ventana, si cubre el principio.

        LÓGICA 1 (2026-11-11): la ventana de quien pregunta corre con el día (`end` es hoy), y la
        clave de la caché lleva sus fechas. Sin red, la consulta de ayer no casaba con la clave de
        hoy y no se usaba: el estado decía «sin datos de DONKI», o enseñaba la instantánea del
        paquete, más vieja, con una caché de un día en el disco. Ahora se usa la última consulta
        de la misma anchura, con su edad (`fetched_at`), que es lo que dice hasta cuándo se sabe:
        lo de después de esa consulta no se sabe y la edad lo declara. Solo si su ventana empieza
        en el principio pedido o antes: un tramo inicial que nunca se pidió no se da por vacío.
        """
        cached = self.cache.get(_latest_key(event_type, start, end))
        if cached is None or not isinstance(cached.data, dict):
            return None
        try:
            first = dt.date.fromisoformat(cached.data["start"])
            fetched_at = dt.datetime.fromisoformat(cached.data["fetched_at"])
            events = [SolarEvent.from_dict(item) for item in cached.data["events"]]
        except (KeyError, TypeError, ValueError):
            return None
        if first > start:
            return None
        return CachedPayload(
            data=[event for event in events if start <= event.time.date() <= end],
            fetched_at=fetched_at,
            source=cached.source,
            from_cache=True,
        )

    def _snapshot(
        self, event_type: EventType, start: dt.date, end: dt.date
    ) -> CachedPayload | None:
        """Los eventos de la instantanea dentro de la ventana pedida, o None si no toca usarla.

        Solo con `donki_snapshot` y si es del mismo tipo. No se guarda en la cache: una cache
        escrita desde la instantanea pareceria, al leerla despues, una consulta a DONKI. Su edad
        es la de la descarga y su fuente lo dice (`Snapshot.label`); los eventos, con su fecha.
        """
        if not self.settings.donki_snapshot:
            return None
        snapshot = load_snapshot(SNAPSHOT)
        if snapshot is None or snapshot.event_type is not event_type:
            return None
        events = [
            event for event in (normalize(event_type, item) for item in snapshot.raw)
            if start <= event.time.date() <= end
        ]
        return SnapshotPayload(
            data=events, fetched_at=snapshot.retrieved_at, source=snapshot.label,
            from_cache=True, note=snapshot.note, snapshot=snapshot.to_dict(),
        )

    def _rehydrate(self, cached: CachedPayload) -> CachedPayload:
        return CachedPayload(
            data=[SolarEvent.from_dict(item) for item in cached.data],
            fetched_at=cached.fetched_at,
            source=cached.source,
            from_cache=True,
        )

    def _fetch(
        self, event_type: EventType, start: dt.date, end: dt.date
    ) -> list[dict[str, Any]]:
        return fetch_raw(self.settings, event_type, start, end)

    def latest_sep(self, lookback_days: int = 365) -> SolarEvent | None:
        """El SPE mas reciente, o None si no hubo ninguno en la ventana."""
        end = utc_today()  # DONKI fecha en UTC, como las efemérides
        start = end - dt.timedelta(days=lookback_days)
        events: list[SolarEvent] = self.events(EventType.SEP, start, end).data
        return max(events, key=lambda event: event.time) if events else None
