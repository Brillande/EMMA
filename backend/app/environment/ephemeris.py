"""Efemerides JPL Horizons: cuanto tarda una respuesta desde la Tierra.

Este es el unico uso de astroquery en el proyecto, y es el que sostiene toda la
premisa de autonomia: el sistema sabe, con datos reales del JPL, cuanto tardaria
una consulta al cirujano de vuelo. Con 22 minutos de ida y vuelta no hay consulta
en vivo, y el software debe decidir solo.

HALLAZGO del spike (ver `spikes/HALLAZGOS.md`): Horizons no devuelve tabla si
`start == stop`, y falla con un error opaco. Hay que pedir una ventana real.
La tabla trae `lighttime` ya calculado en minutos; se contrasta con el calculo
propio a partir de la distancia como verificacion cruzada.

La misma tabla trae la elongacion solar (cantidad 23 del manual de Horizons, «S-O-T»: el
angulo Sol-observador-objetivo, en grados), que astroquery llama `elong`, con su marca `/T` o
`/L` (`elongFlag`). Se guarda junto al retardo para decir si el objetivo esta en conjuncion
solar (`environment/conjunction.py`); el retardo, el riesgo y las recomendaciones no la leen.
Una entrada de cache guardada antes de leerse no la trae y sigue cargando igual: las
efemerides de una fecha no caducan, y el retardo que guarda sigue siendo el mismo.

PRECARGA (decimosexta ronda, E6): sin red, el modo nominal, un dia sin efemeride en cache es un
dia con el retardo «sin dato». `EphemerisClient.preload` pide a Horizons, con paso de un dia, UNA
consulta por cada tramo seguido de dias que falten, y escribe cada fila en la misma cache, con la
misma clave (`cache_key`) y el mismo formato (`CommsWindow.to_dict`) que la consulta diaria: la
lectura diaria la aprovecha sin cambios. Cada fila pasa por la misma verificacion cruzada y el
mismo filtro de la elongacion que la consulta de un dia (`window_from_row`). Que dias de la mision
quedan cubiertos lo dice `environment/ephemeris_coverage.py`.

ROBUSTEZ (decimoseptima ronda, §5.37.12): la consulta diaria toma la fila de su dia, no la
primera que llegue; una fila sin fecha o fuera de las 00:00 UT no se guarda bajo ningun dia, pero
ya no tumba la precarga entera; un fallo de disco al escribir o un proposito quitado de la lista
blanca de la puerta al precargar salen como «no disponible» con su motivo, no como un error del
servidor; y lo recordado de cada fichero (`_LOADABLE`) tiene tope.

UNA PRECARGA A LA VEZ (decimoctava ronda, §5.38.9): dos `POST /api/comms/preload` seguidos (dos
consolas, una orden repetida) pedian a Horizons y escribian los mismos dias dos veces. Ahora la
precarga toma un cerrojo por carpeta de cache (`_preload_lock`) antes de mirar que falta. La
segunda espera a la primera, con tope (`PRELOAD_WAIT_SECONDS`), y despues mira la cache como
siempre: lo que la primera escribio ya no falta, no se pide ni se reescribe, y su resultado lo
dice (`waited_for_another`). Asi reutiliza lo que hizo la primera sin guardar su respuesta
aparte. Si la primera no acaba dentro del tope, la segunda no pide nada y dice que ya hay una en
curso (`PreloadInProgress`, 409 en la ruta): no deja una peticion colgada sin limite. El cerrojo
es del proceso: el guion corre en el suyo, y una precarga del guion a la vez que una de la ruta
sigue pudiendo escribir dos veces lo mismo (entradas enteras, `FileCache.put`).

CALCULO LOCAL (2026-11-11, `environment/spice.py`): un dia sin cache, sin red o con Horizons
inservible ya no sale «sin dato» si estan `spiceypy` y los nucleos de NAIF: `comms_window` lo
calcula con SPICE, la ventana lo dice (`CommsWindow.source`) y no se guarda en esta cache.

SPICE PRIMERO (decision del usuario, 2026-11-11, `spikes/HALLAZGOS.md` §10): sin red es el modo
nominal, y SPICE da en local lo mismo que Horizons (peor diferencia medida: 0,003 ms de tiempo de
luz en 181 dias). Si SPICE puede calcular el dia, la ventana sale de SPICE sin salir a la red;
Horizons queda de CONTRASTE (su entrada en cache de ese dia, si la hay: no se pide nada en vivo
para contrastar) y de RESPALDO (cache y despues en vivo, como antes, cuando SPICE no calcula el
dia). Si el contraste discrepa por encima del error declarado, se dice (`Contrast`) y ese dia se
usa Horizons, la referencia. Esta cache sigue siendo solo de Horizons.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import numbers
import os
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any

from app.core import display, egress, i18n
from app.core.cache import CachedPayload, FileCache, OfflineDataUnavailable
from app.core.config import Settings, get_settings

# Constante IAU 2012: segundos que tarda la luz en recorrer una unidad astronomica.
LIGHT_SECONDS_PER_AU = 499.004783836

# Por encima de este retardo de ida y vuelta, una consulta a Tierra deja de ser
# util para una decision clinica y el sistema opera en modo autonomo.
AUTONOMY_THRESHOLD_MINUTES = 10.0

# Tolerancia al contrastar el `lighttime` de Horizons con el calculo propio.
CROSS_CHECK_TOLERANCE_MINUTES = 0.01

# La cantidad del manual de Horizons que da la elongacion solar («23. Sun-Observer-Target
# (apparent solar elongation) angle»). astroquery la pide por defecto con las demas y la
# devuelve en estas columnas; una prueba comprueba que sigue en la consulta.
SOLAR_ELONGATION_QUANTITY = "23"
SOLAR_ELONGATION_COLUMN = "elong"
SOLAR_ELONGATION_FLAG_COLUMN = "elongFlag"
# Lo que puede valer un angulo Sol-observador-objetivo, en grados.
_ELONGATION_RANGE = (0.0, 180.0)
_ELONGATION_FLAGS = frozenset({"/T", "/L", "/?"})

# A donde sale la consulta (la puerta la autoriza antes; la hace astroquery) y como se firma lo
# que se guarda: lo mismo en la consulta diaria y en la precarga.
HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
SOURCE = "JPL Horizons"
# La fecha de cada fila de la tabla: el dia juliano de la columna `datetime_jd` de astroquery.
# Se lee del numero y no del texto («2026-Nov-01 00:00»), que lleva el mes en ingles.
EPOCH_COLUMN = "datetime_jd"
_JD_UNIX_EPOCH = 2440587.5  # dia juliano del 1970-01-01 a las 00:00 UT


_log = logging.getLogger(__name__)

# Si cada fichero de cache carga como ventana, con la version que se leyo (fecha y tamano). Una
# efemeride no cambia: lo que cambia es el fichero, y entonces cambia su fecha. Una entrada por
# ruta: reescribir un fichero sustituye lo recordado de el, no lo acumula; un fichero que ya no
# esta se olvida. Con tope (`_LOADABLE_MAX`): cada carpeta de cache distinta (otro objetivo, otra
# configuracion) suma rutas, y un proceso largo no debe crecer sin limite. Lleno, se olvida lo mas
# antiguo: volver a leerlo es correcto, solo cuesta abrir el fichero otra vez. El tope deja
# holgura para varias misiones largas (900 dias a Marte, ida y vuelta) a la vez.
_LOADABLE: dict[str, tuple[tuple[int, int], bool]] = {}
_LOADABLE_MAX = 10_000
# Las dos consolas piden `/api/status` a la vez, en hilos distintos: olvidar lo mas antiguo se
# hace con cerrojo (dos hilos podrian elegir la misma ruta, o iterar mientras otro inserta).
_LOADABLE_LOCK = threading.Lock()

# La precarga junta en una consulta dos tramos que falten separados por esta cantidad de dias en
# cache, o menos: pedir unas filas de mas (llegan y se ignoran, sin reescribir nada) cuesta menos
# que otra ida y vuelta, y acota las consultas cuando la cache tiene huecos sueltos (dias que la
# consulta diaria fue llenando). Con huecos mas separados, una consulta por tramo.
PRELOAD_BRIDGE_DAYS = 7

# Cuanto espera una precarga a otra en curso sobre la misma cache antes de decir que ya hay una.
# Decision de diseno, sin fuente: cubre la precarga de un tramo (una consulta a Horizons) y no
# deja la peticion de la consola colgada mientras otra pide la mision entera por tramos.
PRELOAD_WAIT_SECONDS = 30.0
# Un cerrojo por carpeta de cache: dos precargas sobre carpetas distintas (otra configuracion,
# las pruebas) no se estorban. Crece una entrada por carpeta, no por precarga.
_PRELOAD_LOCKS: dict[str, threading.Lock] = {}
_PRELOAD_LOCKS_LOCK = threading.Lock()


def _preload_lock(root: os.PathLike[str] | str) -> threading.Lock:
    """El cerrojo de precarga de una carpeta de cache, el mismo para la misma carpeta."""
    key = os.path.normcase(os.path.abspath(root))
    with _PRELOAD_LOCKS_LOCK:
        return _PRELOAD_LOCKS.setdefault(key, threading.Lock())


def _remember(path: str, version: tuple[int, int], loads: bool) -> None:
    """Recuerda si un fichero carga, con su version, sin pasar de `_LOADABLE_MAX` entradas."""
    with _LOADABLE_LOCK:
        _LOADABLE.pop(path, None)
        while len(_LOADABLE) >= _LOADABLE_MAX:
            _LOADABLE.pop(next(iter(_LOADABLE)), None)
        _LOADABLE[path] = (version, loads)


def _forget(path: str) -> None:
    """Olvida un fichero que ya no está, con el mismo cerrojo que `_remember`.

    Lógica 1 (2026-11-11): se olvidaba sin cerrojo, y `_remember` recorre lo recordado con él
    (`next(iter(_LOADABLE))`). Un cerrojo solo protege si lo toman todos los que escriben.
    """
    with _LOADABLE_LOCK:
        _LOADABLE.pop(path, None)


def _finite(value: Any) -> bool:
    """Si es un numero real finito (un `bool` no cuenta)."""
    return (
        not isinstance(value, bool) and isinstance(value, numbers.Real) and math.isfinite(value)
    )


def servable(window: CommsWindow) -> bool:
    """Si una ventana sirve como retardo: distancia y retardo son numeros finitos.

    La misma regla para la cobertura (`is_cached`) y para lo que lee el retardo
    (`comms_window`): si no, la cobertura podria decir «falta» de un dia cuyo retardo NaN se
    estaria usando, o al reves.
    """
    return _finite(window.distance_au) and _finite(window.one_way_minutes)


def utc_today() -> dt.date:
    """El día de hoy en tiempo universal: el de la efeméride que vale ahora.

    LÓGICA 1 (2026-11-11): el retardo de «hoy», su cobertura y la conjunción leían
    `date.today()`, el día del reloj LOCAL, mientras que cada efeméride es la de las 00:00 UT de
    su día (`epoch_of_row`) y la misión empieza a las 00:00 UTC (`core/mission.py`). En España,
    de las 00:00 a la 01:00 (02:00 en verano) se pedía la efeméride de mañana, y la cobertura
    decía «hoy» de un día que en UT aún no había empezado.
    """
    return dt.datetime.now(dt.UTC).date()


def cache_key(target: str, observer: str, epoch: dt.date) -> str:
    """La clave de cache de la efemeride de un dia: la misma en la consulta diaria y la precarga."""
    return f"horizons:{target}:{observer}:{epoch.isoformat()}"


@dataclass(frozen=True, slots=True)
class Contrast:
    """El cálculo local de SPICE de un día frente a la efeméride de Horizons en caché de ese día.

    Lo calcula `spice.contrast`. `agrees` es si las dos coinciden dentro del error declarado
    (`spice.DECLARED_MAX_ERROR`); `used`, la fuente que sirve el día: SPICE si coinciden, Horizons
    (la referencia) si no. Una elongación ausente en una de las dos no se compara (`None`): no es
    un cero ni una discrepancia.
    """

    local: str
    reference: str
    reference_fetched_at: dt.datetime
    one_way_seconds_difference: float
    elongation_deg_difference: float | None
    one_way_seconds_tolerance: float
    elongation_deg_tolerance: float
    agrees: bool
    used: str

    def describe(self) -> str:
        # En milisegundos: la diferencia real con Horizons es de microsegundos (§10 de HALLAZGOS),
        # y en segundos con cuatro decimales salía «0,0000 s».
        millis = display.number(self.one_way_seconds_difference * 1000, 3)
        if i18n.current() == "en":
            return self._describe_en(millis)
        found = f"{millis} ms de tiempo de luz"
        if self.elongation_deg_difference is not None:
            found += f" y {display.number(self.elongation_deg_difference, 5)}° de elongación"
        limit = (
            f"{display.number(self.one_way_seconds_tolerance, 1)} s y "
            f"{display.number(self.elongation_deg_tolerance, 2)}°"
        )
        if self.agrees:
            return (
                f"Contrastado con {self.reference} (en caché): {found} de diferencia, dentro del "
                f"error declarado ({limit})."
            )
        return (
            f"El cálculo local ({self.local}) discrepa de {self.reference}: {found} de "
            f"diferencia, por encima del error declarado ({limit}). Este día se usa "
            f"{self.reference}, la referencia."
        )

    def _describe_en(self, millis: str) -> str:
        """La misma frase en inglés, para enseñarla. La que se firma no pasa por aquí: quien arma
        el asiento la pide en el idioma del registro (`comms_status.discrepancy_payload`)."""
        local, reference = i18n.loc(self.local), i18n.loc(self.reference)
        found = f"{millis} ms of light time"
        if self.elongation_deg_difference is not None:
            found += f" and {display.number(self.elongation_deg_difference, 5)}° of elongation"
        limit = (
            f"{display.number(self.one_way_seconds_tolerance, 1)} s and "
            f"{display.number(self.elongation_deg_tolerance, 2)}°"
        )
        if self.agrees:
            return (
                f"Checked against {reference} (cached): a difference of {found}, within the "
                f"declared error ({limit})."
            )
        return (
            f"The local computation ({local}) disagrees with {reference}: a difference of "
            f"{found}, above the declared error ({limit}). On this day {reference}, the "
            "reference, is used."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "local": self.local,
            "reference": self.reference,
            "reference_fetched_at": self.reference_fetched_at.isoformat(),
            "one_way_seconds_difference": self.one_way_seconds_difference,
            "elongation_deg_difference": self.elongation_deg_difference,
            "declared_max_error": {
                "one_way_seconds": self.one_way_seconds_tolerance,
                "elongation_deg": self.elongation_deg_tolerance,
            },
            "agrees": self.agrees,
            "used": self.used,
            "text": self.describe(),
        }


@dataclass(frozen=True, slots=True)
class CommsWindow:
    """Condiciones de comunicacion con la Tierra en una fecha dada."""

    epoch: dt.date
    distance_au: float
    one_way_minutes: float
    target: str
    # Elongacion solar (S-O-T) en grados y su marca de Horizons (`/T` el objetivo va detras del
    # Sol, `/L` delante). `None` si la entrada de cache es anterior a leerse, o si Horizons no
    # la dio: no es un cero, y nada de lo que decide la lee.
    solar_elongation_deg: float | None = None
    solar_elongation_flag: str | None = None
    # De donde sale (2026-11-11): «JPL Horizons» (la consulta o su cache) o «SPICE local, nucleo
    # X» (`environment/spice.py`). La cache solo guarda ventanas de Horizons: una ventana de
    # SPICE no se escribe en ella, y las dos fuentes no se mezclan sin decirlo.
    source: str = SOURCE
    # El contraste de SPICE con Horizons de ese día (2026-11-11, `Contrast`), o `None` si no lo
    # hubo: SPICE no calculaba el día, o Horizons no tenía ese día en caché. No se guarda en la
    # caché (`from_dict` no lo lee): es de cada consulta.
    contrast: Contrast | None = None

    @property
    def round_trip_minutes(self) -> float:
        return self.one_way_minutes * 2

    @property
    def autonomy_required(self) -> bool:
        return self.round_trip_minutes > AUTONOMY_THRESHOLD_MINUTES

    def describe(self) -> str:
        """Frase para la interfaz: lo primero que ve el astronauta."""
        if not self.autonomy_required:
            return i18n.tr(
                f"Consulta con Tierra disponible (~{self.round_trip_minutes:.0f} min)",
                f"Consultation with Earth available (~{self.round_trip_minutes:.0f} min)",
            )
        return i18n.tr(
            f"Sin consulta en vivo: la respuesta de Tierra tardaría "
            f"{self.round_trip_minutes:.0f} min",
            f"No live consultation: Earth's answer would take "
            f"{self.round_trip_minutes:.0f} min",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch.isoformat(),
            "distance_au": self.distance_au,
            "one_way_minutes": self.one_way_minutes,
            "round_trip_minutes": self.round_trip_minutes,
            "autonomy_required": self.autonomy_required,
            "target": self.target,
            "description": self.describe(),
            "solar_elongation_deg": self.solar_elongation_deg,
            "solar_elongation_flag": self.solar_elongation_flag,
            "source": self.source,
            "contrast": None if self.contrast is None else self.contrast.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CommsWindow:
        # COMPATIBILIDAD HACIA ATRAS: la cache de antes de leer la elongacion no la trae y no
        # caduca nunca. Se carga igual, con la elongacion en `None`; el retardo es el mismo. Lo
        # que traiga la cache pasa el mismo filtro que la respuesta de Horizons: una entrada
        # tocada a mano no tumba el estado ni sirve un angulo imposible. La cache es solo de
        # Horizons (las ventanas de SPICE no se guardan): su origen es Horizons, diga lo que diga
        # una entrada tocada a mano.
        checked_deg, checked_flag = checked_elongation(
            raw.get("solar_elongation_deg"), raw.get("solar_elongation_flag")
        )
        return cls(
            epoch=dt.date.fromisoformat(raw["epoch"]),
            distance_au=raw["distance_au"],
            one_way_minutes=raw["one_way_minutes"],
            target=raw["target"],
            solar_elongation_deg=checked_deg,
            solar_elongation_flag=checked_flag,
        )


def light_minutes_from_au(distance_au: float) -> float:
    return distance_au * LIGHT_SECONDS_PER_AU / 60.0


def _first(table: Any, column: str, row: int = 0) -> Any:
    """Una fila de una columna (la primera, por defecto), o `None` si la columna no viene.

    Un hueco de Horizons llega enmascarado (`numpy.ma.masked`), que no es un `numbers.Real`:
    `checked_elongation` lo descarta sin convertirlo (convertirlo daria NaN con un aviso).
    """
    return table[column][row] if column in table.columns else None


def solar_elongation(table: Any, row: int = 0) -> tuple[float | None, str | None]:
    """La elongacion solar de una fila y su marca, o `(None, None)` si no sirve.

    Un valor ausente o imposible NO hace fallar la consulta: el retardo, que si decide, salio
    bien, y la elongacion solo se dice. Se guarda `None` y la conjuncion se declara sin dato.
    """
    return checked_elongation(
        _first(table, SOLAR_ELONGATION_COLUMN, row),
        _first(table, SOLAR_ELONGATION_FLAG_COLUMN, row),
    )


def epoch_of_row(table: Any, row: int) -> dt.date:
    """El dia de una fila de la tabla, a las 00:00 UT.

    Se pide paso de un dia desde una medianoche: una fila que no caiga en medianoche, o sin fecha,
    no es la efemeride de ningun dia, y se dice (`HorizonsResponseError`) en vez de guardar la de
    una hora bajo la clave de otro dia.
    """
    raw = _first(table, EPOCH_COLUMN, row)
    if not _finite(raw):
        raise HorizonsResponseError(f"fila {row} de Horizons sin fecha ({EPOCH_COLUMN})")
    days = float(raw) - _JD_UNIX_EPOCH
    if days != math.floor(days):
        raise HorizonsResponseError(
            f"fila {row} de Horizons fuera de las 00:00 UT (día juliano {float(raw)})"
        )
    return dt.date(1970, 1, 1) + dt.timedelta(days=int(days))


def rows_by_day(table: Any) -> tuple[dict[dt.date, int], int]:
    """La fila de cada dia de la tabla (la primera, si se repite) y cuantas filas no son de ninguno.

    Una fila sin fecha o fuera de las 00:00 UT no se guarda bajo ningun dia (`epoch_of_row`), pero
    tampoco tumba las demas: antes abortaba la precarga entera aunque fuera la de un dia ya
    guardado. El dia que no tenga fila de medianoche queda sin efemeride, y se dice.

    Pero una tabla con filas y NINGUNA de medianoche no es una fila rara: es la API que ha
    cambiado (otra escala de tiempo, otro paso), y se dice como respuesta inservible
    (`HorizonsResponseError`), igual que antes, en vez de dar todos sus dias por «no recibidos».
    """
    rows: dict[dt.date, int] = {}
    unusable = 0
    for row in range(len(table)):
        try:
            epoch = epoch_of_row(table, row)
        except HorizonsResponseError:
            unusable += 1
            continue
        rows.setdefault(epoch, row)
    if len(table) and not rows:
        raise HorizonsResponseError(
            f"ninguna de las {len(table)} filas de Horizons cae a las 00:00 UT con fecha "
            f"({EPOCH_COLUMN}): la tabla no es la pedida"
        )
    return rows, unusable


def day_runs(days: Sequence[dt.date], bridge: int = 0) -> list[tuple[dt.date, dt.date]]:
    """Los tramos de una lista ordenada de dias sin repetir, como (primero, ultimo).

    Con `bridge`, dos tramos separados por `bridge` dias o menos (que no estan en la lista) se
    juntan en uno. La cobertura usa los tramos seguidos (`bridge=0`); la precarga junta los que
    estan cerca (`PRELOAD_BRIDGE_DAYS`).
    """
    runs: list[tuple[dt.date, dt.date]] = []
    for day in days:
        if runs and (day - runs[-1][1]).days <= bridge + 1:
            runs[-1] = (runs[-1][0], day)
        else:
            runs.append((day, day))
    return runs


def _finite_cell(table: Any, column: str, row: int, epoch: dt.date) -> float:
    """El valor de una celda como numero finito, o `HorizonsResponseError` si no lo es."""
    raw = table[column][row]
    if not _finite(raw):
        raise HorizonsResponseError(
            f"la tabla de Horizons para {epoch} trae {column} sin valor utilizable ({raw!r})"
        )
    return float(raw)


def window_from_row(table: Any, row: int, epoch: dt.date, target: str) -> CommsWindow:
    """La ventana de comunicacion de una fila: la misma para la consulta diaria y la precarga.

    Verificacion cruzada: Horizons ya trae `lighttime`. Si diverge del calculo desde la
    distancia, algo cambio en la API y hay que enterarse, no seguir callando (`ValueError`).
    Una tabla sin distancia tampoco es una ventana: `HorizonsResponseError`, no un `KeyError`
    que saldria como error del servidor. Un hueco (`numpy.ma.masked`) o un valor no finito en la
    distancia o en el tiempo de luz, tampoco: convertido daria NaN, NaN pasa la verificacion
    cruzada (toda comparacion con NaN es falsa) y se guardaria como un retardo «disponible».
    """
    if "delta" not in table.columns:
        raise HorizonsResponseError(f"la tabla de Horizons para {epoch} no trae la distancia")
    distance_au = _finite_cell(table, "delta", row, epoch)
    computed = light_minutes_from_au(distance_au)

    if "lighttime" in table.columns:
        reported = _finite_cell(table, "lighttime", row, epoch)
        if abs(reported - computed) > CROSS_CHECK_TOLERANCE_MINUTES:
            raise ValueError(
                f"discrepancia en tiempo de luz para {epoch}: Horizons informa "
                f"{reported:.4f} min, el cálculo desde delta da {computed:.4f} min"
            )
        computed = reported

    elongation, flag = solar_elongation(table, row)
    return CommsWindow(
        epoch=epoch,
        distance_au=distance_au,
        one_way_minutes=computed,
        target=target,
        solar_elongation_deg=elongation,
        solar_elongation_flag=flag,
    )


@dataclass(frozen=True, slots=True)
class PreloadResult:
    """Lo que hizo una precarga: que rango se pidio, cuantas filas llegaron y que se escribio."""

    start: dt.date
    stop: dt.date
    target: str
    # Dias del rango que ya estaban en cache antes de empezar (no se reescriben).
    already_cached: int
    # Del inicio de la primera consulta al fin de la ultima, o `None` si no faltaba nada y no
    # salio nada a la red. Lo que se pidio tal cual (START_TIME, STOP_TIME) esta en `queries`.
    requested: tuple[dt.date, dt.date] | None
    rows_received: int
    written: tuple[dt.date, ...]
    # Dias que faltaban y para los que Horizons no devolvio fila: siguen sin efemeride.
    not_received: tuple[dt.date, ...] = ()
    # Cada consulta a Horizons, una por tramo seguido de dias que faltaban.
    queries: tuple[tuple[dt.date, dt.date], ...] = ()
    # Filas sin fecha o fuera de las 00:00 UT: no se guardan bajo ningun dia.
    rows_unusable: int = 0
    # Si espero a otra precarga en curso sobre la misma cache antes de mirar que faltaba: lo que
    # aquella escribio cuenta aqui como `already_cached`. Si aquella fallo sin escribir, esta
    # pide lo que siga faltando, y `written` lo dice: esperar no promete que no se pidiera nada.
    waited_for_another: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "stop": self.stop.isoformat(),
            "target": self.target,
            "already_cached": self.already_cached,
            "requested": (
                None if self.requested is None
                else {"start": self.requested[0].isoformat(), "stop": self.requested[1].isoformat()}
            ),
            "queries": [
                {"start": first.isoformat(), "stop": last.isoformat()}
                for first, last in self.queries
            ],
            "rows_received": self.rows_received,
            "rows_unusable": self.rows_unusable,
            "written": len(self.written),
            "written_first": self.written[0].isoformat() if self.written else None,
            "written_last": self.written[-1].isoformat() if self.written else None,
            "not_received": [day.isoformat() for day in self.not_received],
            "waited_for_another": self.waited_for_another,
        }


def days_between(start: dt.date, stop: dt.date) -> list[dt.date]:
    """Los dias de `start` a `stop`, ambos incluidos (vacio si `stop` es anterior)."""
    return [start + dt.timedelta(days=n) for n in range((stop - start).days + 1)]


def checked_elongation(degrees: Any, flag: Any) -> tuple[float | None, str | None]:
    """Un angulo S-O-T y su marca, si son posibles; si no, `(None, None)` o la marca en `None`.

    Lo usan la respuesta de Horizons y la cache: un numero real (no un texto ni un booleano)
    finito entre 0 y 180 grados, y una marca de las que da Horizons.
    """
    if isinstance(degrees, bool) or not isinstance(degrees, numbers.Real):
        return None, None
    value = float(degrees)
    low, high = _ELONGATION_RANGE
    if not math.isfinite(value) or not low <= value <= high:
        return None, None
    flag_text = str(flag).strip() if flag is not None else None
    return value, flag_text if flag_text in _ELONGATION_FLAGS else None


class HorizonsResponseError(ValueError):
    """Horizons respondio, pero con algo que no sirve: error del servicio o tabla rota.

    No es "sin red", y no debe presentarse como tal: sin red se espera y se usa la
    cache; una respuesta incoherente es un cambio en la API que hay que investigar.
    Hereda de `ValueError` para que el estado degrade igual que con la discrepancia
    del tiempo de luz.
    """


class EphemerisCacheWriteError(OfflineDataUnavailable):
    """La precarga no pudo escribir en la cache de efemerides (disco lleno, sin permiso...).

    Antes salia de `POST /api/comms/preload` como un error del servidor (500). No es una
    respuesta inservible de Horizons (502), y la efemeride sigue sin estar en cache para cuando
    falte la red: «no disponible» (503), con el motivo y lo que si quedo escrito. Hereda de
    `OfflineDataUnavailable` para que la ruta y el guion la traten como tal sin tocarlos.
    """


class PreloadInProgress(RuntimeError):
    """Ya hay una precarga en curso sobre la misma cache y no acabo dentro del tope de espera.

    No es «sin red» (503) ni una respuesta inservible (502): es un conflicto con otra orden que
    sigue en marcha (409). No se pidio nada a Horizons ni se escribio nada.
    """


class EphemerisClient:
    """Consulta JPL Horizons, con cache permanente.

    Las efemerides de una fecha pasada no cambian nunca, asi que la cache no
    caduca: una vez obtenida una fecha, el sistema no vuelve a necesitar la red
    para ella.
    """

    def __init__(self, settings: Settings | None = None, cache: FileCache | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or FileCache(self.settings.cache_dir / "ephemeris")

    def comms_window(self, epoch: dt.date, target: str) -> CachedPayload:
        """Ventana de comunicacion en una fecha. Devuelve el dato con su antiguedad.

        `target` es obligatorio desde el 2026-11-11: lo decide el perfil de mision
        (`mission_profiles.ephemeris_target`), no `EMMA_TARGET_BODY`. Ningun metodo de este
        cliente lo rellena por su cuenta.

        PRECEDENCIA (decision del usuario, 2026-11-11, `environment/spice.py`): SPICE primero. Si
        SPICE puede calcular el dia (instalado, nucleos verificados, dia dentro del nucleo y
        objetivo soportado), la ventana sale de SPICE y no sale nada a la red. Si ademas hay una
        efemeride de Horizons de ese dia en cache, se contrastan (`spice.contrast`): si coinciden
        dentro del error declarado se sirve SPICE con el contraste; si no, se sirve Horizons, la
        referencia, con el contraste que lo dice, y queda en el registro como error. Si SPICE no
        puede, el orden de antes: la cache de Horizons, Horizons en vivo y, si nada, «no
        disponible» con el motivo de Horizons y el de SPICE. La ventana dice de donde sale
        (`CommsWindow.source`, y `source` del resultado); lo de SPICE no se guarda en la cache.
        """
        key = cache_key(target, self.settings.observer_body, epoch)

        # Una entrada que no carga como ventana servible (rota, sin la forma de la cache, o con un
        # retardo que no es un numero) cuenta como no cacheada, con la misma regla que la
        # cobertura (`_cached_window`): no se sirve un «~nan min», y una entrada tocada a mano no
        # es un error del servidor.
        found = self._cached_window(key)
        local = self._spice_window(epoch, target)
        if isinstance(local, CachedPayload):
            return local if found is None else self._contrasted(local, *found)
        if found is not None:
            cached, window = found
            return CachedPayload(
                data=window,
                fetched_at=cached.fetched_at,
                source=cached.source,
                from_cache=True,
            )

        try:
            return self._horizons_window(epoch, target, key)
        except OfflineDataUnavailable as unavailable:
            raise OfflineDataUnavailable(f"{unavailable}. Cálculo local: {local}") from unavailable

    def _contrasted(
        self, local: CachedPayload, cached: CachedPayload, reference: CommsWindow
    ) -> CachedPayload:
        """SPICE contrastado con la efemeride de Horizons en cache del mismo dia.

        Discrepar por encima del error declarado no se esconde: la ventana lleva el contraste, el
        registro lo guarda como error (algo no es lo que se valido: el nucleo, la API, la cache) y
        ese dia se usa Horizons, la referencia que valida la verificacion cruzada.
        """
        from app.environment import spice  # aqui: `spice` importa este modulo

        contrast = spice.contrast(local.data, reference, cached.fetched_at)
        if contrast.agrees:
            return replace(local, data=replace(local.data, contrast=contrast))
        _log.error(
            "SPICE discrepa de JPL Horizons para %s por encima del error declarado; se usa "
            "Horizons: %s", reference.epoch, contrast.describe(),
        )
        return CachedPayload(
            data=replace(reference, contrast=contrast),
            fetched_at=cached.fetched_at,
            source=cached.source,
            from_cache=True,
        )

    def _spice_window(self, epoch: dt.date, target: str) -> CachedPayload | str:
        """La ventana de SPICE como resultado, o el motivo por el que no se puede calcular."""
        from app.environment import spice  # aqui: `spice` importa este modulo

        try:
            window = spice.window(self.settings, epoch, target)
        except spice.SpiceUnavailable as exc:
            return str(exc)
        return CachedPayload(
            data=window, fetched_at=dt.datetime.now(dt.UTC), source=window.source,
            from_cache=False,
        )

    def _horizons_window(self, epoch: dt.date, target: str, key: str) -> CachedPayload:
        """La consulta a Horizons de un dia sin cache, guardada en la cache si se puede."""
        if self.settings.offline:
            raise OfflineDataUnavailable(
                f"efemérides de {epoch} no cacheadas y el sistema está en modo offline"
            )

        with _horizons_errors(str(epoch)):
            # astroquery sale por `requests`: la puerta autoriza antes (lista blanca, modo
            # seguro, contenido) y la llamada la hace su librería.
            egress.authorize(
                self.settings, "ephemeris", HORIZONS_URL,
                f"target={target} epoch={epoch.isoformat()}",
            )
            window = self._fetch(epoch, target)
        try:
            stored = self.cache.put(key, window.to_dict(), source=SOURCE)
        except OSError as exc:
            # La efemeride llego y paso la verificacion: se sirve aunque no se haya podido
            # guardar (antes, un error del servidor). Sin guardar, ese dia sin red seguira sin
            # dato, y la cobertura lo dira; aqui queda en el registro.
            _log.warning(
                "efeméride de %s obtenida pero no guardada en caché: %s", epoch, type(exc).__name__
            )
            return CachedPayload(
                data=window, fetched_at=dt.datetime.now(dt.UTC), source=SOURCE,
                from_cache=False,
            )
        return CachedPayload(
            data=window,
            fetched_at=stored.fetched_at,
            source=stored.source,
            from_cache=False,
        )

    def is_cached(self, epoch: dt.date, target: str) -> bool:
        """Si `comms_window` serviria ese dia sin red: hay entrada y carga como ventana.

        Una entrada corrupta o tocada a mano que no carga no cuenta como cubierta: sin red, ese
        dia el retardo saldria igual de «sin dato». `/api/status` lo pregunta por cada dia de la
        mision en cada consulta: lo leido se recuerda por fichero, con su fecha y su tamano
        (`_LOADABLE`), y un fichero que no existe ni se abre. Para muchos dias a la vez,
        `cached_days`, que lee la carpeta una vez en vez de mirar fichero a fichero.
        """
        key = cache_key(target, self.settings.observer_body, epoch)
        path = self.cache.path_for(key)
        try:
            stat = path.stat()
        except OSError:
            _forget(str(path))
            return False
        return self._known(key, str(path), (stat.st_mtime_ns, stat.st_size))

    def cached_days(self, days: Sequence[dt.date], target: str) -> list[bool]:
        """`is_cached` de cada dia, leyendo la carpeta de la cache UNA vez.

        La cobertura lo pregunta por cada dia de la mision en cada `/api/status`: antes era un
        `stat` por dia (181 en la mision configurada, 900 en una a Marte con regreso). Ahora un
        solo listado de la carpeta trae el nombre, la fecha y el tamano de cada fichero (en
        Windows, sin abrir ninguno), y la misma regla de `is_cached` decide con lo recordado. Una
        carpeta que no se puede leer es una cache sin nada: ningun dia cubierto.
        """
        try:
            with os.scandir(self.cache.root) as entries:
                listing = {entry.name: entry for entry in entries if entry.name.endswith(".json")}
        except OSError:
            return [False] * len(days)
        covered: list[bool] = []
        for day in days:
            key = cache_key(target, self.settings.observer_body, day)
            path = self.cache.path_for(key)
            entry = listing.get(path.name)
            try:
                stat = entry.stat() if entry is not None else None
            except OSError:
                stat = None
            if stat is None:
                _forget(str(path))
                covered.append(False)
                continue
            covered.append(self._known(key, str(path), (stat.st_mtime_ns, stat.st_size)))
        return covered

    def _known(self, key: str, path: str, version: tuple[int, int]) -> bool:
        """Si el fichero de `key` carga como ventana: de memoria si no ha cambiado, si no leido."""
        known = _LOADABLE.get(path)
        if known is not None and known[0] == version:
            return known[1]
        loads = self._loads(key)
        _remember(path, version, loads)
        return loads

    def cached(self, epoch: dt.date, target: str) -> tuple[CachedPayload, CommsWindow] | None:
        """La efemeride de Horizons de un dia en cache, si carga y es servible. Sin red."""
        return self._cached_window(cache_key(target, self.settings.observer_body, epoch))

    def _loads(self, key: str) -> bool:
        return self._cached_window(key) is not None

    def _cached_window(self, key: str) -> tuple[CachedPayload, CommsWindow] | None:
        """La entrada de `key` y su ventana, si carga y es servible; si no, `None`.

        JSON valido pero sin la forma de la cache (sin `fetched_at`, una lista, una fecha
        imposible) hace fallar `FileCache.get` o `from_dict` con KeyError, TypeError o
        ValueError: no cuenta, y no tumba `/api/status` ni `/api/comms`. Un retardo o una
        distancia que no son un numero finito no son una ventana servible aunque `from_dict` los
        cargue. La misma regla para la cobertura y para el retardo.
        """
        try:
            cached = self.cache.get(key)
            if cached is None or not isinstance(cached.data, dict):
                return None
            window = CommsWindow.from_dict(cached.data)
        except (KeyError, TypeError, ValueError):
            return None
        return (cached, window) if servable(window) else None

    def preload(self, start: dt.date, stop: dt.date, target: str) -> PreloadResult:
        """Precarga en cache las efemerides de `start` a `stop`, ambos incluidos.

        Se pide UNA consulta por cada tramo de dias sin cache, con paso de un dia (la API de
        Horizons lo admite con START_TIME, STOP_TIME y STEP_SIZE): antes era un solo tramo del
        primer dia que faltaba al ultimo, y con casi todo en cache en medio se volvia a pedir la
        mision entera. Dos tramos separados por `PRELOAD_BRIDGE_DAYS` dias en cache o menos van
        en la misma consulta. Lo ya cacheado no se reescribe: una efemeride de un dia no cambia,
        y su `fetched_at` es el de cuando se obtuvo; si llega una fila suya (un hueco entre tramos
        juntados, o el dia de despues de un tramo de un dia), se ignora sin comprobarla. La
        salida pasa por la puerta (`core/egress.py`), una autorizacion por consulta: sin red, en
        modo seguro o con el freno HALT, no sale nada y se dice (`OfflineDataUnavailable`); un
        proposito quitado de la lista blanca, tambien, con lo que dijo la puerta.

        Todas las consultas se hacen y todas las filas que se van a guardar se comprueban antes de
        escribir ninguna: una red caida a la segunda consulta o una discrepancia del tiempo de luz
        dejan la cache como estaba. Una fila sin fecha o fuera de medianoche no se guarda bajo
        ningun dia, pero no tumba las demas (`rows_by_day`; se cuentan en `rows_unusable`). Los
        dias que falten y no lleguen se devuelven en `not_received`. Un fallo de disco al escribir
        es `EphemerisCacheWriteError`, con lo que si quedo escrito.

        Una sola precarga a la vez por carpeta de cache: con otra en curso, espera a que acabe
        (como mucho `PRELOAD_WAIT_SECONDS`) y despues mira que falta, que ya no es lo que aquella
        escribio (`waited_for_another`); si no acaba a tiempo, `PreloadInProgress` sin pedir nada.
        """
        if stop < start:
            raise ValueError(f"rango vacío: {start} es posterior a {stop}")
        lock = _preload_lock(self.cache.root)
        waited = not lock.acquire(blocking=False)
        if waited and not lock.acquire(timeout=PRELOAD_WAIT_SECONDS):
            raise PreloadInProgress(
                f"ya hay una precarga de efemérides en curso sobre esta caché ({self.cache.root}) "
                f"y no acabó en {PRELOAD_WAIT_SECONDS:g} s; no se ha pedido nada a JPL Horizons. "
                "Vuelve a pedirla cuando acabe: lo que aquella escriba ya no se pedirá"
            )
        try:
            result = self._preload(start, stop, target)
        finally:
            lock.release()
        return replace(result, waited_for_another=waited) if waited else result

    def _preload(self, start: dt.date, stop: dt.date, target: str) -> PreloadResult:
        """La precarga, ya con el cerrojo de su carpeta tomado."""
        days = days_between(start, stop)
        missing = [day for day, ok in zip(days, self.cached_days(days, target), strict=True)
                   if not ok]
        if not missing:
            return PreloadResult(start, stop, target, len(days), None, 0, ())

        # Horizons exige una ventana: con inicio igual a fin devuelve la ficha del objeto sin
        # tabla. Lo que se pide es lo que se dice que se pidio.
        queries = tuple(
            (first, max(last, first + dt.timedelta(days=1)))
            for first, last in day_runs(missing, bridge=PRELOAD_BRIDGE_DAYS)
        )
        tables: list[Any] = []
        with _horizons_errors(f"{missing[0]} a {missing[-1]}", not_allowed_unavailable=True):
            for first, last in queries:
                egress.authorize(
                    self.settings, "ephemeris", HORIZONS_URL,
                    f"target={target} start={first.isoformat()} stop={last.isoformat()}",
                )
                tables.append(self._range_query(first, last, target).ephemerides())

        wanted = set(missing)
        windows: dict[dt.date, CommsWindow] = {}
        unusable = 0
        for table in tables:
            rows, skipped = rows_by_day(table)
            unusable += skipped
            for epoch, row in rows.items():
                if epoch in wanted and epoch not in windows:
                    windows[epoch] = window_from_row(table, row, epoch, target)
        written = tuple(sorted(windows))
        self._write(target, windows, written)
        return PreloadResult(
            start, stop, target, len(days) - len(missing), (queries[0][0], queries[-1][1]),
            sum(len(table) for table in tables), written,
            not_received=tuple(day for day in missing if day not in windows),
            queries=queries,
            rows_unusable=unusable,
        )

    def _write(
        self, target: str, windows: dict[dt.date, CommsWindow], days: tuple[dt.date, ...]
    ) -> None:
        """Escribe cada dia en la cache; un fallo de disco es `EphemerisCacheWriteError`.

        Cada escritura es atomica (`FileCache.put`): un fallo a mitad deja escritos, enteros, los
        dias de antes, que son efemerides buenas, y ninguno a medias. Se dice cuantos.
        """
        for done, epoch in enumerate(days):
            try:
                self.cache.put(
                    cache_key(target, self.settings.observer_body, epoch),
                    windows[epoch].to_dict(),
                    source=SOURCE,
                )
            except OSError as exc:
                raise EphemerisCacheWriteError(
                    f"no se pudo escribir la efeméride del {epoch} en la caché "
                    f"({self.cache.root}): {exc}. Quedaron escritos {done} de {len(days)} días; "
                    "los demás siguen sin efeméride"
                ) from exc

    def _range_query(self, start: dt.date, stop: dt.date, target: str) -> Any:
        """La consulta a Horizons de un rango de dias, con paso de un dia.

        Horizons exige una ventana: con start == stop devuelve la ficha del objeto sin tabla, y
        astroquery falla con un error sin mensaje util. Quien llama pide siempre `stop > start`.
        """
        from astroquery.jplhorizons import Horizons

        return Horizons(
            id=target,
            location=self.settings.observer_body,
            epochs={"start": start.isoformat(), "stop": stop.isoformat(), "step": "1d"},
        )

    def _query(self, epoch: dt.date, target: str) -> Any:
        """La consulta a Horizons de una fecha (aparte para comprobar que pide la elongacion)."""
        return self._range_query(epoch, epoch + dt.timedelta(days=1), target)

    def _fetch(self, epoch: dt.date, target: str) -> CommsWindow:
        # La consulta es la de siempre: astroquery pide por defecto todas las cantidades de la
        # tabla de observador, la 23 (elongacion solar) incluida. No sale nada nuevo a la red.
        #
        # Se toma la fila del dia pedido, no la primera que llegue (decimoseptima ronda): una
        # tabla que empezara en otro dia, o a otra hora, guardaria la efemeride de ese otro
        # instante bajo la clave de este dia. La misma regla que la precarga (`rows_by_day`).
        table = self._query(epoch, target).ephemerides()
        rows, unusable = rows_by_day(table)
        if epoch not in rows:
            raise HorizonsResponseError(
                f"la tabla de Horizons no trae la fila del {epoch} a las 00:00 UT "
                f"({len(table)} filas, {unusable} sin fecha o fuera de medianoche)"
            )
        return window_from_row(table, rows[epoch], epoch, target)


@contextmanager
def _horizons_errors(when: str, *, not_allowed_unavailable: bool = False) -> Iterator[None]:
    """Traduce los fallos de una consulta a Horizons a los dos que el resto entiende.

    SIN RED NO ERA UN 500. DONKI y RadLab traducian ya un fallo de red a
    `OfflineDataUnavailable`; este cliente no, y un corte de red durante la consulta salia por
    `/api/comms` como un error del servidor. astroquery habla por `requests`, cuyas excepciones
    de red derivan de `OSError`, y tiene un `TimeoutError` propio que no deriva del de Python.
    La precarga traduce igual que la consulta diaria.

    Un proposito `ephemeris` que no este en la lista blanca de la puerta (`EgressNotAllowed`) es
    un error de configuracion, y la puerta pide que falle ruidosamente. En la consulta diaria se
    deja pasar tal cual: el estado (`_fetch_comms`) convierte «no disponible» en un retardo «sin
    dato» mudo, y esconderia el error. En la precarga (`not_allowed_unavailable`), que es una
    orden explicita con su respuesta, sale como «no consultable» (503) con lo que dijo la puerta
    y queda en el registro como error: antes era un 500 sin motivo.
    """
    from astroquery.exceptions import (
        EmptyResponseError,
        RemoteServiceError,
        TableParseError,
    )
    from astroquery.exceptions import TimeoutError as HorizonsTimeout

    try:
        yield
    except egress.EgressBlocked as exc:
        raise OfflineDataUnavailable(
            f"JPL Horizons no consultable ({exc.reason}) y sin efemérides en caché para {when}"
        ) from exc
    except egress.EgressNotAllowed as exc:
        if not not_allowed_unavailable:
            raise
        _log.error("precarga de efemérides denegada por la lista blanca: %s", type(exc).__name__)
        raise OfflineDataUnavailable(
            f"JPL Horizons no consultable (la puerta de salida no lo permite: {exc}) y sin "
            f"efemérides en caché para {when}"
        ) from exc
    except (OSError, HorizonsTimeout) as exc:
        raise OfflineDataUnavailable(
            f"JPL Horizons inaccesible y sin efemérides en caché para {when}: {exc}"
        ) from exc
    except (RemoteServiceError, TableParseError, EmptyResponseError) as exc:
        raise HorizonsResponseError(
            f"JPL Horizons respondió sin datos utilizables para {when}: {exc}"
        ) from exc
