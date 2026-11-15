"""CCMC iSWA por HAPI: la serie continua de flujo de protones y de viento solar.

Por qué existe: DONKI (`environment/donki.py`) da eventos sueltos ya catalogados —un SEP con su
hora—, y entre un evento y otro EMMA no sabía nada del entorno de partículas: ni cuánto flujo
había ni si estaba subiendo. La consola de Tierra preguntaba «¿está tranquilo el Sol ahora?» y la
respuesta era «no hay ningún SEP catalogado», que no es lo mismo. iSWA, el servidor del Community
Coordinated Modeling Center (NASA Goddard), redistribuye por el protocolo HAPI, sin clave, la serie
de tiempo real de GOES y del viento solar: con ella la consola ve la curva, no solo el evento.

LO QUE ES Y LO QUE NO (spike del 2026-11-11, `spikes/HALLAZGOS.md` §6):
  - El flujo de protones es el **canal P10** del conjunto `goesp_part_flux_P5M` (GOES primario,
    medias de 5 min). La ficha HAPI no escribe «integral ≥10 MeV»: lo es porque coincide valor a
    valor con la serie integral ≥10 MeV de NOAA SWPC (comprobado en el spike), y la familia de
    canales P1…P500 es la de los canales integrales de GOES. La unidad de la ficha es
    «Protons/cm^2 - s^-1 - sr», que es la definición de la pfu; si la ficha cambia de unidad, el
    canal se declara no disponible y no se reetiqueta.
  - El viento solar es `swpc_rtsw_plasma_P1M`: velocidad, densidad y temperatura de protones del
    satélite que NOAA SWPC tenga como primario (el conjunto lo dice en `source`).
  - **El dato es de NOAA (GOES y RTSW), servido por la NASA (CCMC iSWA).** EMMA sale solo a iSWA.
  - Es el entorno en órbita geoestacionaria y en L1, no el de la nave: no es dosis de nadie ni
    entra en ningún nivel, alerta ni riesgo. Se muestra y no se evalúa.

Reglas del cliente, las de las demás fuentes del entorno:
  - toda serie viaja con la edad de su consulta y con la de su última muestra (la serie llega con
    unos 10 min de retraso: la consulta puede ser de ahora y el último dato, no);
  - sin red (`EMMA_OFFLINE`, nominal en misión) se sirve la última consulta guardada con su edad,
    o «no disponible»; nunca se inventa una serie;
  - un valor de relleno (`fill` de la ficha) es un hueco, no un cero;
  - un parámetro pedido que no vuelve en la cabecera es un cuerpo roto: HAPI de iSWA ignora en
    silencio un parámetro desconocido y devuelve solo la columna de tiempo (spike).

Configuración: sin entrada en `core/config.py`; la vigencia y la ventana son constantes de este
módulo (parámetros de diseño, abajo).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from app.core import egress, i18n
from app.core.cache import CachedPayload, FileCache, OfflineDataUnavailable
from app.core.config import Settings, get_settings

BASE_URL = "https://iswa.gsfc.nasa.gov/IswaSystemWebApp/hapi"
PURPOSE = "space-weather-series"
# Vigencia de una consulta (parámetro de diseño): la cadencia de la serie de protones es de 5 min;
# volver a salir antes no trae ninguna muestra nueva.
FRESH_FOR = dt.timedelta(minutes=5)
# Ventana que se pide siempre (parámetro de diseño). Fija, para que la caché sea una sola por serie
# y valga para cualquier ventana más corta que se pida después; HAPI de iSWA admite hasta 31 días.
WINDOW = dt.timedelta(hours=72)
MAX_HOURS = 72

# La unidad que la ficha HAPI da al canal de protones: es la definición de la pfu.
PFU_UNITS = "Protons/cm^2 - s^-1 - sr"

LICENCE = (
    "Datos de NOAA SWPC (GOES y viento solar en tiempo real), redistribuidos por NASA CCMC iSWA "
    "(https://iswa.gsfc.nasa.gov) por HAPI: obras del Gobierno de EE. UU., sin copyright en "
    "EE. UU. (17 U.S.C. §105). Se cita la fuente y no implica respaldo de NASA ni de NOAA."
)
SCOPE = (
    "Entorno en órbita geoestacionaria (GOES) y en L1 (viento solar), no en la nave: no es la "
    "dosis de ningún tripulante. Se muestra y no se evalúa: no cambia ningún nivel, alerta ni "
    "riesgo."
)
# Referencia, no umbral de EMMA: la escala S de NOAA empieza en S1 a 10 pfu de ≥10 MeV. Se muestra
# junto a la curva para leerla; EMMA no compara con ella ni alerta por ella.
S1_REFERENCE: dict[str, Any] = {
    "label": "S1 (menor) de la escala de tormentas de radiación solar de NOAA",
    "value": 10.0,
    "unit": "pfu",
    "channel": "≥10 MeV",
    "source": "NOAA Space Weather Scales, https://www.swpc.noaa.gov/noaa-scales-explanation",
    "evaluated": False,
}
i18n.en_many({
    LICENCE: (
        "NOAA SWPC data (GOES and real-time solar wind), redistributed by NASA CCMC iSWA "
        "(https://iswa.gsfc.nasa.gov) over HAPI: works of the U.S. Government, without "
        "copyright in the U.S. (17 U.S.C. §105). The source is cited and no endorsement by "
        "NASA or NOAA is implied."
    ),
    SCOPE: (
        "Environment in geostationary orbit (GOES) and at L1 (solar wind), not at the "
        "spacecraft: it is not the dose of any crew member. Shown, not evaluated: it does not "
        "change any level, alert or risk."
    ),
    str(S1_REFERENCE["label"]): "S1 (minor) on the NOAA solar radiation storm scale",
})


def s1_reference() -> dict[str, Any]:
    """La referencia S1 para servir: una copia, con su rótulo en el idioma de la petición."""
    return {**S1_REFERENCE, "label": i18n.loc(S1_REFERENCE["label"])}


class Series(StrEnum):
    PROTONS = "protons"
    SOLAR_WIND = "solar-wind"


@dataclass(frozen=True, slots=True)
class Channel:
    """Un parámetro HAPI tal como EMMA lo enseña."""

    parameter: str  # nombre en la ficha HAPI
    name: str  # nombre en la respuesta de EMMA
    unit: str  # unidad tal como la enseña EMMA
    hapi_units: str  # unidad exigida en la ficha: si no coincide, no se reetiqueta
    label: str


@dataclass(frozen=True, slots=True)
class Dataset:
    series: Series
    dataset_id: str
    title: str
    channels: tuple[Channel, ...]
    # La columna que dice de qué satélite sale cada fila.
    origin_parameter: str


DATASETS: dict[Series, Dataset] = {
    Series.PROTONS: Dataset(
        series=Series.PROTONS,
        dataset_id="goesp_part_flux_P5M",
        title="Flujo integral de protones ≥10 MeV, GOES primario (medias de 5 min)",
        channels=(
            Channel("P10", "flux_ge_10mev", "pfu", PFU_UNITS,
                    "flujo integral de protones ≥10 MeV (canal P10 de GOES)"),
        ),
        origin_parameter="satelliteProton",
    ),
    Series.SOLAR_WIND: Dataset(
        series=Series.SOLAR_WIND,
        dataset_id="swpc_rtsw_plasma_P1M",
        title="Viento solar en tiempo real de NOAA SWPC (medias de 1 min)",
        channels=(
            Channel("BulkSpeed", "speed", "km/s", "km/s", "velocidad del viento solar"),
            Channel("ProtonDensity", "density", "p/cm³", "p/cc", "densidad de protones"),
            Channel("IonTemperature", "temperature", "K", "K", "temperatura de iones"),
        ),
        origin_parameter="source",
    ),
}
i18n.en_many({
    "Flujo integral de protones ≥10 MeV, GOES primario (medias de 5 min)": (
        "Integral proton flux ≥10 MeV, primary GOES (5 min averages)"
    ),
    "flujo integral de protones ≥10 MeV (canal P10 de GOES)": (
        "integral proton flux ≥10 MeV (GOES P10 channel)"
    ),
    "Viento solar en tiempo real de NOAA SWPC (medias de 1 min)": (
        "NOAA SWPC real-time solar wind (1 min averages)"
    ),
    "velocidad del viento solar": "solar wind speed",
    "densidad de protones": "proton density",
    "temperatura de iones": "ion temperature",
})


class HapiBodyError(httpx.DecodingError):
    """Un 200 que no es la serie pedida: se trata como un fallo de la consulta."""


def _parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _hapi_time(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(dataset: Dataset, body: Any) -> list[dict[str, Any]]:
    """Las filas de una respuesta HAPI en JSON, o `HapiBodyError` si no es la serie pedida.

    Cada fila: `time` (ISO 8601), un valor por canal (None si es relleno) y `origin`.
    """
    if not isinstance(body, dict):
        raise HapiBodyError("la respuesta HAPI no es un objeto JSON")
    status = body.get("status")
    if not isinstance(status, dict) or status.get("code") != 1200:
        raise HapiBodyError(f"estado HAPI distinto de 1200: {status!r}")
    header = body.get("parameters")
    rows = body.get("data")
    if not isinstance(header, list) or not isinstance(rows, list):
        raise HapiBodyError("la respuesta HAPI no trae `parameters` y `data`")
    columns = {
        item.get("name"): (index, item) for index, item in enumerate(header)
        if isinstance(item, dict)
    }
    if "Time" not in columns:
        raise HapiBodyError("la respuesta HAPI no trae la columna Time")
    for channel in dataset.channels:
        if channel.parameter not in columns:
            # iSWA ignora en silencio un parámetro que no conoce: sin esta comprobación, una serie
            # sin valores pasaría por una serie de huecos.
            raise HapiBodyError(f"la respuesta no trae el parámetro {channel.parameter}")
        units = columns[channel.parameter][1].get("units")
        if units != channel.hapi_units:
            raise HapiBodyError(
                f"{channel.parameter} llega en {units!r}, no en {channel.hapi_units!r}: "
                "no se reetiqueta"
            )
    time_index = columns["Time"][0]
    origin_index = columns.get(dataset.origin_parameter, (None, None))[0]
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list):
            raise HapiBodyError("una fila de la serie no es una lista")
        try:
            moment = _parse_time(str(row[time_index]))
        except (IndexError, ValueError) as exc:
            raise HapiBodyError(f"fila sin hora legible: {row!r}") from exc
        sample: dict[str, Any] = {"time": moment.isoformat()}
        for channel in dataset.channels:
            index, item = columns[channel.parameter]
            sample[channel.name] = _value(row, index, item.get("fill"))
        origin = row[origin_index] if origin_index is not None and origin_index < len(row) else None
        sample["origin"] = None if origin in (None, "-1", -1) else str(origin)
        parsed.append(sample)
    return parsed


def _value(row: list[Any], index: int, fill: Any) -> float | None:
    """El valor de una celda, o None si es relleno o falta: un hueco no es un cero."""
    if index >= len(row) or row[index] is None:
        return None
    try:
        value = float(row[index])
    except (TypeError, ValueError):
        return None
    try:
        if fill is not None and fill != "null" and value == float(fill):
            return None
    except (TypeError, ValueError):
        pass
    return value


class IswaClient:
    """Cliente HAPI de iSWA con caché y degradación sin red."""

    def __init__(self, settings: Settings | None = None, cache: FileCache | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or FileCache(self.settings.cache_dir / "iswa")

    @staticmethod
    def _key(dataset: Dataset) -> str:
        return f"iswa:{dataset.dataset_id}:{int(WINDOW.total_seconds() // 3600)}h"

    def series(self, which: Series) -> CachedPayload:
        """La última serie de `WINDOW`, con su edad; o `OfflineDataUnavailable`."""
        dataset = DATASETS[which]
        key = self._key(dataset)
        cached = self.cache.get(key)
        usable = cached if cached is not None and isinstance(cached.data, list) else None
        if usable is not None and (self.settings.offline or not usable.is_stale(FRESH_FOR)):
            return usable
        if self.settings.offline:
            raise OfflineDataUnavailable(
                f"serie {dataset.dataset_id} de iSWA no guardada y el sistema está en modo sin red"
            )
        try:
            rows = self._fetch(dataset)
        except httpx.HTTPError as exc:
            # La red o el servidor fallaron: la última serie, con su edad, mejor que ninguna.
            if usable is not None:
                return usable
            raise OfflineDataUnavailable(
                f"iSWA inaccesible y sin serie guardada de {dataset.dataset_id}: {exc}"
            ) from exc
        return self.cache.put(key, rows, source=source_label(dataset))

    def _fetch(self, dataset: Dataset) -> list[dict[str, Any]]:
        now = dt.datetime.now(dt.UTC)
        parameters = [channel.parameter for channel in dataset.channels]
        parameters.append(dataset.origin_parameter)
        response = egress.get(
            self.settings, PURPOSE, f"{BASE_URL}/data",
            params={
                "id": dataset.dataset_id,
                "time.min": _hapi_time(now - WINDOW),
                "time.max": _hapi_time(now),
                "parameters": ",".join(parameters),
                "format": "json",
            },
        )
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise HapiBodyError(f"iSWA respondió sin JSON utilizable: {exc}") from exc
        return parse(dataset, body)


def source_label(dataset: Dataset) -> str:
    return f"NASA CCMC iSWA (HAPI) · {dataset.dataset_id} · datos de NOAA SWPC"


def _source_in_language(source: str) -> str:
    """La fuente de una serie para enseñarla. En la caché se guarda la de `source_label`, la
    misma pida quien pida; aquí se dice en el idioma de la petición si es una de las de EMMA."""
    if i18n.current() != "en":
        return source
    for dataset in DATASETS.values():
        if source == source_label(dataset):
            return f"NASA CCMC iSWA (HAPI) · {dataset.dataset_id} · NOAA SWPC data"
    return source


def describe(which: Series, payload: CachedPayload, hours: int) -> dict[str, Any]:
    """El bloque de una serie para la API: valores, unidades, edad y fuente; nada evaluado."""
    dataset = DATASETS[which]
    since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours)
    samples = [row for row in payload.data if _parse_time(row["time"]) >= since]
    measured = [
        row for row in samples
        if any(row.get(channel.name) is not None for channel in dataset.channels)
    ]
    last = measured[-1] if measured else None
    last_age = (
        int((dt.datetime.now(dt.UTC) - _parse_time(last["time"])).total_seconds())
        if last is not None else None
    )
    return {
        "available": True,
        "dataset": dataset.dataset_id,
        "title": i18n.loc(dataset.title),
        "channels": [
            {"name": channel.name, "label": i18n.loc(channel.label), "unit": channel.unit,
             "hapi_parameter": channel.parameter, "hapi_units": channel.hapi_units}
            for channel in dataset.channels
        ],
        "window_hours": hours,
        "samples": samples,
        "latest": last,
        # Dos edades: la de la consulta y la de su última muestra con valor.
        "last_sample_age_seconds": last_age,
        "data_age": payload.describe_age(),
        "data_age_seconds": payload.age_seconds,
        "from_cache": payload.from_cache,
        "live": not payload.from_cache,
        "source": _source_in_language(payload.source),
    }


def unavailable(which: Series, reason: str) -> dict[str, Any]:
    dataset = DATASETS[which]
    return {
        "available": False,
        "dataset": dataset.dataset_id,
        "title": i18n.loc(dataset.title),
        "reason": reason,
        "source": _source_in_language(source_label(dataset)),
    }
