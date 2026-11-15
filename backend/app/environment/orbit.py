"""SSCweb (Satellite Situation Center, NASA Goddard): dónde está la ISS y si pasa por la SAA.

Por qué existe: en órbita baja la dosis no sube solo con un evento solar. Cada día la ISS cruza
varias veces la Anomalía del Atlántico Sur (SAA), donde el cinturón interior de protones baja más
cerca de la Tierra, y una buena parte de la dosis de la estación se recibe en esos pasos. EMMA
tenía la dosis medida (RadLab) y el clima espacial (DONKI), pero no podía decir «ahora mismo la
nave está sobre la SAA», que es lo que explica un pico de la dosimetría sin evento solar.

Qué da: la posición de la ISS (latitud, longitud y distancia al centro de la Tierra) de las
efemérides de SSCweb para el instante actual, y si ese punto cae dentro de un contorno publicado
de la SAA a la altura de la ISS (`SAA_REGION`). Es **descriptivo**: no cambia el riesgo, los
niveles, los umbrales ni ninguna alerta, y no entra en el ledger porque no es una observación de
nadie (invariante 4: solo las observaciones van por el ledger). Solo tiene sentido con el perfil
de órbita baja (`leo`); con otro perfil la ruta dice «no aplica» y no sale a la red.

HALLAZGOS del spike (`spikes/HALLAZGOS.md` §6, 2026-11-11):
  - Servicio REST público, sin clave: `GET /locations/iss/<inicio>,<fin>/geo/`.
  - **El formato depende de `Accept`.** Sin `Accept: application/json` responde XML. Por eso se
    usa `egress.client` (deja pasar la cabecera) y no `egress.get`.
  - El JSON es el de Jackson con tipos: cada objeto es `["clase java", {...}]` y cada lista
    `["java.util.ArrayList", [...]]`. `_unwrap` quita esa envoltura.
  - Un satélite inexistente responde **200** con `StatusCode: ERROR`: el código HTTP no basta.
  - Fuera de las efemérides disponibles responde 200, `SUCCESS` y **sin `Data`**: no es un error,
    es «no hay posición para ese tramo», y así se dice.
  - La ISS se sirve a 60 s y sus efemérides llegan unas semanas por delante: lo que se da para
    «ahora» es una efeméride (definitiva o predicha), no telemetría de la nave.
  - La longitud viene en 0-360°.

Sin red: la ventana pedida cubre las próximas horas, así que una consulta reciente sigue sirviendo
mientras el instante caiga dentro de ella, con su edad (la de la consulta). Fuera de la ventana no
se extrapola: «no disponible».
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import httpx

from app.core import egress, i18n
from app.core.cache import CachedPayload, FileCache, OfflineDataUnavailable
from app.core.config import Settings, get_settings

BASE_URL = "https://sscweb.gsfc.nasa.gov/WS/sscr/2"
OBSERVATORY = "iss"
PURPOSE = "orbit"
SOURCE = "NASA SSCweb (Satellite Situation Center, Goddard) · ISS, coordenadas GEO"
# En la caché se guarda siempre la misma; donde se enseña (`describe`), en el idioma de quien pide.
i18n.en(SOURCE, "NASA SSCweb (Satellite Situation Center, Goddard) · ISS, GEO coordinates")
# Parámetros de diseño, no de la API. La ventana cubre las próximas horas (unas cuatro órbitas)
# para que una consulta siga valiendo un rato sin red; una consulta de más de `FRESH_FOR` se
# repite si hay red, porque las efemérides predichas de la ISS se corrigen con cada maniobra.
WINDOW_BEFORE = dt.timedelta(minutes=5)
WINDOW_AHEAD = dt.timedelta(hours=6)
FRESH_FOR = dt.timedelta(minutes=30)
# Resolución de SSCweb para la ISS (60 s, `/observatories`). Una muestra a más de esto del
# instante pedido no es «la posición de ahora»: la ventana no lo cubre.
MAX_SAMPLE_GAP = dt.timedelta(seconds=90)
CACHE_KEY = "sscweb:iss:latest"

# El contorno de la SAA, con su respaldo (verificado en fuente el 2026-11-11). Es el contorno
# `SAACONT` que NASA GSFC publica en la CALDB de NICER, un instrumento que va montado en la propia
# ISS: es, por tanto, un contorno a la altura de la estación y medido desde ella, que es lo que la
# caja de 1996 (a 500 km) no era. Ver `SAA_REGION["limits"]`: es el contorno donde los detectores
# de NICER ven fondo de partículas, no un contorno de dosis. Por eso la ruta dice «dentro del
# contorno publicado», no «dentro de la SAA», y no se usa para nada más que para enseñarlo.
SAA_REGION: dict[str, Any] = {
    # Vértices (longitud, latitud) en grados geográficos, longitud en -180..180, tal cual los da
    # la columna `ASCII_REGION` del fichero (polígono cerrado: el último repite el primero).
    "polygon": [
        (-67.68, -2.36), (-86.40, -10.28), (-84.49, -31.85), (-72.35, -43.99),
        (-54.56, -52.58), (-28.19, -53.63), (0.21, -46.89), (15.51, -42.67),
        (28.80, -34.04), (12.96, -21.08), (-9.36, -21.08), (-23.76, -16.04),
        (-43.20, 0.52), (-67.68, -2.36),
    ],
    "altitude": "la de la órbita de la ISS: NICER va instalado en ella",
    "valid_from": "2017-06-01",
    "evidence": "magnitud documentada",
    "source": {
        "ref": "NASA GSFC HEASARC, CALDB de NICER/XTI, «NICER SAA Region», "
               "nixtisaareg20170601v003.fits (REGTYPE SAACONT, creado 2018-02-26, "
               "válido desde 2017-06-01)",
        "url": "https://heasarc.gsfc.nasa.gov/FTP/caldb/data/nicer/xti/bcf/saa/"
               "nixtisaareg20170601v003.fits",
        "doc_url": "https://heasarc.gsfc.nasa.gov/lheasoft/ftools/headas/niprefilter2.html",
        "quote": "The NICER_SAA is a custom definition of SAA for the NICER payload on the ISS. "
                 "It is produced from NICER data.",
        "status": "verified",
        "read_on": "2026-11-11",
        "read_via": "fichero FITS descargado de la CALDB y leído (cabecera y tabla REGION); "
                    "ayuda de niprefilter2 y nimaketime en HEASARC",
    },
    "limits": [
        "es el contorno donde los detectores de rayos X de NICER ven fondo de partículas, no un "
        "contorno de dosis ni de flujo de protones: un punto dentro no dice cuánta dosis se "
        "recibe, y el fichero no declara el umbral con que se trazó",
        "es propio de NICER: su ayuda (nimaketime) dice que es más pequeño que el contorno "
        "genérico de SAA de prefilter, que es más conservador",
        "se trazó con datos de NICER hasta 2017-2018 y la SAA se desplaza hacia el oeste año a "
        "año: el contorno no sigue esa deriva",
        "es un contorno geográfico en dos dimensiones para la órbita de la ISS; no vale para "
        "otra altura",
    ],
    # La caja que EMMA usaba antes. Leída ya en su fuente primaria (la página de NASA sigue
    # publicada, ahora en `ask_astro/earth.html`, pregunta 961004), pero es a 500 km y de 1996:
    # se conserva para que conste qué se sustituyó y por qué, no se usa.
    "superseded": {
        "lat_min": -50.0, "lat_max": 0.0, "lon_min": -90.0, "lon_max": 40.0,
        "altitude_km": 500,
        "ref": "NASA GSFC, Imagine the Universe!, «Ask an Astrophysicist», pregunta 961004 "
               "«What are the boundaries of the South Atlantic Anomaly?» (enviada el 4 de "
               "octubre de 1996)",
        "url": "https://imagine.gsfc.nasa.gov/ask_astro/earth.html",
        "quote": "At an altitude of 500 km, the SAA ranges between -90 and +40 in geographic "
                 "longitude and -50 to 0 in geographic latitude. In this region, the extent of "
                 "the SAA increases with increasing altitude.",
        "status": "verified",
        "read_on": "2026-11-11",
        "why_replaced": "es una caja a 500 km y la ISS vuela más baja; la propia fuente dice "
                        "que la SAA crece con la altura, así que a la altura de la ISS la caja "
                        "la exageraba",
    },
}
# El inglés de lo que EMMA escribe del contorno. Las frases de la fuente (`quote`) ya están en su
# idioma y no se tocan; las cifras son las mismas.
i18n.en_many({
    SAA_REGION["altitude"]: "that of the ISS orbit: NICER is installed on the station",
    SAA_REGION["evidence"]: "documented magnitude",
    SAA_REGION["source"]["ref"]: (
        "NASA GSFC HEASARC, NICER/XTI CALDB, “NICER SAA Region”, "
        "nixtisaareg20170601v003.fits (REGTYPE SAACONT, created 2018-02-26, "
        "valid from 2017-06-01)"
    ),
    SAA_REGION["source"]["read_via"]: (
        "FITS file downloaded from the CALDB and read (header and REGION table); "
        "niprefilter2 and nimaketime help pages at HEASARC"
    ),
    SAA_REGION["limits"][0]: (
        "it is the contour where NICER's X-ray detectors see particle background, not a dose "
        "or proton-flux contour: a point inside does not say how much dose is received, and "
        "the file does not declare the threshold it was drawn with"
    ),
    SAA_REGION["limits"][1]: (
        "it is specific to NICER: its help page (nimaketime) says it is smaller than the "
        "generic SAA contour of prefilter, which is more conservative"
    ),
    SAA_REGION["limits"][2]: (
        "it was drawn with NICER data up to 2017-2018 and the SAA drifts westwards year after "
        "year: the contour does not follow that drift"
    ),
    SAA_REGION["limits"][3]: (
        "it is a two-dimensional geographic contour for the ISS orbit; it does not hold for "
        "another altitude"
    ),
    SAA_REGION["superseded"]["ref"]: (
        "NASA GSFC, Imagine the Universe!, “Ask an Astrophysicist”, question 961004 "
        "“What are the boundaries of the South Atlantic Anomaly?” (submitted on 4 October "
        "1996)"
    ),
    SAA_REGION["superseded"]["why_replaced"]: (
        "it is a box at 500 km and the ISS flies lower; the source itself says the SAA grows "
        "with altitude, so at the altitude of the ISS the box overstated it"
    ),
})


def _in_language(value: Any) -> Any:
    """Una copia con cada cadena registrada en el idioma de la petición; las claves, igual."""
    if isinstance(value, str):
        return i18n.loc(value)
    if isinstance(value, dict):
        return {key: _in_language(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_in_language(item) for item in value]
    return value


def saa_region() -> dict[str, Any]:
    """El contorno para servirlo: una copia, con lo que escribe EMMA en el idioma de quien pide."""
    region: dict[str, Any] = _in_language(SAA_REGION)
    return region


def _on_segment(x: float, y: float, a: tuple[float, float], b: tuple[float, float]) -> bool:
    (x1, y1), (x2, y2) = a, b
    cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
    return (
        abs(cross) <= 1e-9
        and min(x1, x2) <= x <= max(x1, x2)
        and min(y1, y2) <= y <= max(y1, y2)
    )


def _in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """Punto en polígono por cruce de rayo; un punto sobre el borde cuenta como dentro."""
    inside = False
    for a, b in zip(polygon, polygon[1:], strict=False):
        if _on_segment(x, y, a, b):
            return True
        (x1, y1), (x2, y2) = a, b
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


class OrbitDataError(ValueError):
    """La respuesta de SSCweb no tiene la forma esperada (cuerpo roto o `StatusCode: ERROR`)."""


@dataclass(frozen=True, slots=True)
class OrbitSample:
    """Una muestra de las efemérides de SSCweb para la ISS."""

    time: dt.datetime
    latitude: float  # grados, geográfica (GEO)
    longitude: float  # grados, -180..180 (SSCweb la da en 0..360)
    radial_km: float  # distancia al centro de la Tierra

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time.isoformat(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radial_km": self.radial_km,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> OrbitSample:
        return cls(
            time=dt.datetime.fromisoformat(raw["time"]),
            latitude=float(raw["latitude"]),
            longitude=float(raw["longitude"]),
            radial_km=float(raw["radial_km"]),
        )


def in_saa_region(latitude: float, longitude: float) -> bool:
    """Si un punto cae dentro del contorno publicado de la SAA (bordes incluidos)."""
    return _in_polygon(normalize_longitude(longitude), latitude, SAA_REGION["polygon"])


def normalize_longitude(longitude: float) -> float:
    """0..360 -> -180..180, que es como da el contorno su fuente."""
    lon = longitude % 360.0
    return lon - 360.0 if lon > 180.0 else lon


def _stamp(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def _unwrap(value: Any) -> Any:
    """Quita la envoltura de tipos de Jackson: `["clase", valor]` -> valor."""
    if (
        isinstance(value, list) and len(value) == 2 and isinstance(value[0], str)
        and value[0].startswith(("java.", "javax.", "gov.nasa."))
    ):
        return value[1]
    return value


def parse_locations(body: Any) -> list[OrbitSample]:
    """Las muestras de una respuesta de `/locations`. Lista vacía si SSCweb no tiene ese tramo.

    Falla con `OrbitDataError` si el cuerpo no es lo esperado: un cuerpo roto no es «sin datos».
    """
    try:
        result = _unwrap(_unwrap(body)["Result"])
        status = result["StatusCode"]
        if status != "SUCCESS":
            text = _unwrap(result.get("StatusText")) or []
            raise OrbitDataError(f"SSCweb respondió {status}: {'; '.join(map(str, text))}")
        data = _unwrap(result.get("Data")) or []
        if not data:
            return []
        satellite = _unwrap(data[0])
        coords = _unwrap(_unwrap(satellite["Coordinates"])[0])
        if str(coords.get("CoordinateSystem")).upper() != "GEO":
            system = coords.get("CoordinateSystem")
            raise OrbitDataError(f"sistema de coordenadas inesperado: {system}")
        times = [dt.datetime.fromisoformat(_unwrap(item)) for item in _unwrap(satellite["Time"])]
        lats = _unwrap(coords["Latitude"])
        lons = _unwrap(coords["Longitude"])
        radial = _unwrap(satellite["RadialLength"])
    except OrbitDataError:
        raise
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise OrbitDataError(f"respuesta de SSCweb con forma inesperada: {exc!r}") from exc
    if not (len(times) == len(lats) == len(lons) == len(radial)):
        raise OrbitDataError("SSCweb devolvió series de distinta longitud")
    try:
        return [
            OrbitSample(
                time=moment.astimezone(dt.UTC), latitude=float(lat),
                longitude=normalize_longitude(float(lon)), radial_km=float(dist),
            )
            for moment, lat, lon, dist in zip(times, lats, lons, radial, strict=True)
        ]
    except (TypeError, ValueError) as exc:
        raise OrbitDataError(f"valor no numérico en la respuesta de SSCweb: {exc!r}") from exc


def nearest(samples: list[OrbitSample], moment: dt.datetime) -> OrbitSample | None:
    """La muestra más cercana a `moment`, si está a menos de `MAX_SAMPLE_GAP`; si no, None."""
    if not samples:
        return None
    best = min(samples, key=lambda sample: abs(sample.time - moment))
    return best if abs(best.time - moment) <= MAX_SAMPLE_GAP else None


def next_saa_entry(samples: list[OrbitSample], moment: dt.datetime) -> dt.datetime | None:
    """La primera muestra tras `moment` que entra en el contorno, o None si la ventana acaba antes.

    Se llama con la nave fuera del contorno en `moment`: la primera muestra dentro es la entrada.
    """
    later = [sample for sample in sorted(samples, key=lambda s: s.time) if sample.time > moment]
    previous_inside = False
    for sample in later:
        inside = in_saa_region(sample.latitude, sample.longitude)
        if inside and previous_inside is False:
            return sample.time
        previous_inside = inside
    return None


class OrbitClient:
    """Efemérides de la ISS de SSCweb, con caché y sin red como modo nominal."""

    def __init__(self, settings: Settings | None = None, cache: FileCache | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or FileCache(self.settings.cache_dir / "sscweb")

    def samples(self, now: dt.datetime | None = None) -> CachedPayload:
        """Las muestras que cubren `now`: de la red si toca, de la caché si no.

        Lanza `OfflineDataUnavailable` si nada cubre `now`. Nunca extrapola.
        """
        now = now or dt.datetime.now(dt.UTC)
        cached = self._cached()
        covers = cached is not None and nearest(cached.data, now) is not None
        if cached is not None and covers and (
            self.settings.offline or not cached.is_stale(FRESH_FOR)
        ):
            return cached
        if self.settings.offline:
            raise OfflineDataUnavailable(
                "posición de la ISS no cacheada para este instante y el sistema está en modo "
                "sin red"
            )
        try:
            samples = self._fetch(now - WINDOW_BEFORE, now + WINDOW_AHEAD)
        except (httpx.HTTPError, OrbitDataError) as exc:
            if cached is not None and covers:
                return cached
            raise OfflineDataUnavailable(
                f"SSCweb inaccesible y sin caché que cubra ahora: {exc}"
            ) from exc
        stored = self.cache.put(
            CACHE_KEY, [sample.to_dict() for sample in samples], source=SOURCE
        )
        return CachedPayload(
            data=samples, fetched_at=stored.fetched_at, source=SOURCE, from_cache=False
        )

    def _cached(self) -> CachedPayload | None:
        cached = self.cache.get(CACHE_KEY)
        if cached is None:
            return None
        try:
            data = [OrbitSample.from_dict(item) for item in cached.data]
        except (KeyError, TypeError, ValueError):
            return None  # caché rota: ausente, nunca dato
        return CachedPayload(
            data=data, fetched_at=cached.fetched_at, source=cached.source, from_cache=True
        )

    def _fetch(self, start: dt.datetime, end: dt.datetime) -> list[OrbitSample]:
        # Lo único que sale: el identificador público de la ISS, dos instantes y el sistema de
        # coordenadas. `egress.client` deja pasar `Accept`; el User-Agent es el genérico de httpx.
        url = f"{BASE_URL}/locations/{OBSERVATORY}/{_stamp(start)},{_stamp(end)}/geo/"
        with egress.client(self.settings, PURPOSE) as http:
            response = http.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise OrbitDataError(f"SSCweb respondió sin JSON utilizable: {exc}") from exc
        samples = parse_locations(body)
        if not samples:
            raise OrbitDataError("SSCweb no tiene efemérides de la ISS para este tramo")
        return samples


def describe(payload: CachedPayload, now: dt.datetime) -> dict[str, Any]:
    """La posición de ahora con su edad y el contorno de la SAA, o «no disponible» si no hay."""
    sample = nearest(payload.data, now)
    base: dict[str, Any] = {
        "source": i18n.loc(payload.source),
        "fetched_at": payload.fetched_at.isoformat(),
        "age": payload.describe_age(),
        "age_seconds": payload.age_seconds,
        "from_cache": payload.from_cache,
        "kind": i18n.tr(
            "efeméride de SSCweb (definitiva o predicha), no telemetría de la nave",
            "SSCweb ephemeris (definitive or predicted), not spacecraft telemetry",
        ),
    }
    if sample is None:
        return {**base, "available": False,
                "reason": i18n.tr(
                    "la consulta guardada no cubre este instante; no se extrapola",
                    "the stored query does not cover this instant; it is not extrapolated",
                )}
    inside = in_saa_region(sample.latitude, sample.longitude)
    entry = None if inside else next_saa_entry(payload.data, now)
    return {
        **base,
        "available": True,
        "position": sample.to_dict(),
        "in_saa_region": inside,
        "next_saa_region_entry": entry.isoformat() if entry else None,
        "window_end": max(s.time for s in payload.data).isoformat(),
    }
