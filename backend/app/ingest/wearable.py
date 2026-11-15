"""Ingesta desde wearables reales.

Dos vias, ambas desembocando en el mismo `VitalObservation`:

  1. **BLE en vivo**: caracteristica Heart Rate Measurement (UUID 0x2A37) del
     perfil GATT estandar. La trama trae, ademas del pulso, los intervalos R-R,
     que permiten calcular HRV de verdad en lugar de aceptar el numero que el
     fabricante quiera dar.
  2. **Exportaciones**: Apple Health (XML) y Google Fit (JSON).

El parseo de la trama BLE sigue la especificacion Bluetooth SIG de la
caracteristica Heart Rate Measurement:

    byte 0: flags
        bit 0  formato del pulso   0 = uint8, 1 = uint16
        bit 1  estado del sensor de contacto
        bit 2  soporte de sensor de contacto
        bit 3  energia consumida presente (uint16)
        bit 4  intervalos R-R presentes (uint16 cada uno, en 1/1024 s)
    bytes siguientes: pulso, [energia], [intervalos R-R...]
"""

from __future__ import annotations

import datetime as dt
import math
import threading
from collections import OrderedDict, deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from app.ingest.fhir import FULL_CONFIDENCE, VitalObservation, observation

# Los intervalos R-R del perfil GATT vienen en unidades de 1/1024 de segundo.
RR_UNITS_PER_SECOND = 1024.0

# Un intervalo R-R fuera de este rango no es fisiologico: es un artefacto de
# medida (movimiento, mal contacto). Filtrarlo evita HRV fantasma.
RR_PLAUSIBLE_MS = (300.0, 2000.0)

# Confianza asignada cuando el sensor declara que NO hay contacto con la piel.
#
# El perfil GATT expone ese bit y hasta ahora se parseaba para tirarlo. Una
# lectura sin contacto no vale lo mismo que una con buen contacto: el error del
# PPG es ~30 % mayor durante actividad y varia 3x entre dispositivos, y el mal
# contacto es la causa dominante de artefacto.
#
# No se descarta la lectura —podria ser real— pero deja de poder sostener por si
# sola un hallazgo grave.
NO_CONTACT_CONFIDENCE = 0.3


@dataclass(frozen=True, slots=True)
class HeartRateMeasurement:
    """Una trama decodificada de la caracteristica 0x2A37."""

    heart_rate: int
    rr_intervals_ms: tuple[float, ...]
    sensor_contact: bool | None
    energy_expended: int | None


def parse_heart_rate_measurement(frame: bytes) -> HeartRateMeasurement:
    """Decodifica una trama GATT Heart Rate Measurement."""
    if not frame:
        raise ValueError("trama vacía")

    flags = frame[0]
    offset = 1

    hr_is_uint16 = bool(flags & 0b0000_0001)
    contact_supported = bool(flags & 0b0000_0100)
    contact_detected = bool(flags & 0b0000_0010)
    has_energy = bool(flags & 0b0000_1000)
    has_rr = bool(flags & 0b0001_0000)

    if hr_is_uint16:
        if len(frame) < offset + 2:
            raise ValueError("trama truncada: falta el pulso de 16 bits")
        heart_rate = int.from_bytes(frame[offset : offset + 2], "little")
        offset += 2
    else:
        if len(frame) < offset + 1:
            raise ValueError("trama truncada: falta el pulso")
        heart_rate = frame[offset]
        offset += 1

    energy: int | None = None
    if has_energy:
        if len(frame) < offset + 2:
            raise ValueError("trama truncada: se anuncia energía consumida y no viene")
        energy = int.from_bytes(frame[offset : offset + 2], "little")
        offset += 2

    rr_intervals: list[float] = []
    if has_rr:
        remaining = frame[offset:]
        if len(remaining) % 2:
            raise ValueError("trama truncada: los intervalos R-R van de dos en dos bytes")
        for index in range(0, len(remaining), 2):
            raw = int.from_bytes(remaining[index : index + 2], "little")
            rr_intervals.append(raw / RR_UNITS_PER_SECOND * 1000.0)

    return HeartRateMeasurement(
        heart_rate=heart_rate,
        rr_intervals_ms=tuple(rr_intervals),
        sensor_contact=contact_detected if contact_supported else None,
        energy_expended=energy,
    )


def confidence_from_contact(sensor_contact: bool | None) -> float:
    """Confianza de medida derivada del bit de contacto del sensor GATT.

    `None` significa que el dispositivo no soporta la deteccion de contacto, no
    que no haya contacto: en ese caso no hay motivo para desconfiar.
    """
    if sensor_contact is False:
        return NO_CONTACT_CONFIDENCE
    return FULL_CONFIDENCE


def plausible_rr(intervals: list[float] | tuple[float, ...]) -> list[float]:
    """Descarta intervalos no fisiologicos antes de calcular HRV."""
    low, high = RR_PLAUSIBLE_MS
    return [value for value in intervals if low <= value <= high]


def rmssd(rr_intervals_ms: list[float] | tuple[float, ...]) -> float | None:
    """Raiz cuadratica media de las diferencias sucesivas, en ms.

    Devuelve None si no hay suficientes intervalos validos: es preferible no
    informar HRV a informar un numero calculado sobre dos latidos.
    """
    values = plausible_rr(rr_intervals_ms)
    if len(values) < 3:
        return None
    diffs = [later - earlier for earlier, later in zip(values, values[1:], strict=False)]
    return round(math.sqrt(sum(d * d for d in diffs) / len(diffs)), 2)


def sdnn(rr_intervals_ms: list[float] | tuple[float, ...]) -> float | None:
    """Desviacion tipica de los intervalos N-N, en ms."""
    values = plausible_rr(rr_intervals_ms)
    if len(values) < 3:
        return None
    average = sum(values) / len(values)
    variance = sum((value - average) ** 2 for value in values) / len(values)
    return round(math.sqrt(variance), 2)


# --------------------------------------------------------------------------- #
# HRV sobre una ventana de intervalos R-R
# --------------------------------------------------------------------------- #
#
# POR QUE UNA VENTANA Y NO LA TRAMA.
# Una banda real (p. ej. COOSPO HW9) notifica ~1 trama por segundo con uno o dos
# intervalos R-R cada una. Calcular HRV por trama exigia tres intervalos en la misma
# trama: con una banda de verdad la HRV no salia nunca, y cuando salia era un numero
# sobre tres latidos, que no es HRV. Aqui se acumulan los R-R de tramas consecutivas
# del mismo tripulante y dispositivo, y la HRV se calcula sobre la ventana.

# Ventana de 5 min: es el registro corto de referencia para RMSSD y SDNN (Task Force
# ESC/NASPE 1996). Mas corta no es comparable con la literatura; mas larga mezcla
# cambios de postura y actividad.
HRV_WINDOW = dt.timedelta(minutes=5)

# Minimo de intervalos plausibles en la ventana para informar HRV. Eleccion de diseno,
# no un umbral validado: unos 30 latidos (~medio minuto en reposo) es lo minimo para que
# la cifra no la domine un par de latidos, y deja ver la HRV pronto tras conectar la
# banda. La ventana sigue creciendo hasta 5 min y cada HRV posterior la usa entera.
HRV_MIN_RR = 30

# Una HRV por minuto como maximo: la ventana se desliza con cada trama, y escribir una
# observacion por trama llenaria el ledger de valores casi identicos y autocorrelados.
HRV_EMIT_EVERY = dt.timedelta(seconds=60)

# Mas de 10 s sin tramas (o una trama anterior a la ultima) rompe la serie: faltan
# latidos, y una diferencia sucesiva entre latidos no contiguos no es RMSSD. Se empieza
# de cero en vez de calcular sobre un hueco.
HRV_MAX_GAP = dt.timedelta(seconds=10)

# Tope de series vivas. El sujeto y el dispositivo los pone quien envia: sin tope, un
# cliente que cambiara de sujeto en cada trama haria crecer la memoria sin limite. Se
# expulsa la serie usada hace mas tiempo.
HRV_MAX_STREAMS = 64


@dataclass(frozen=True, slots=True)
class HrvReading:
    """HRV calculada sobre la ventana que acaba en la trama `effective`."""

    rmssd_ms: float
    sdnn_ms: float
    effective: dt.datetime
    beats: int


@dataclass(slots=True)
class _RrStream:
    last_frame: dt.datetime
    last_emitted: dt.datetime | None = None
    intervals: deque[tuple[dt.datetime, float]] = field(default_factory=deque)


class RrWindow:
    """Intervalos R-R recientes por (tripulante, dispositivo), en memoria del proceso.

    Las rutas sincronas de FastAPI corren en un pool de hilos: dos tramas pueden llegar a
    la vez, de ahi el cerrojo. No es estado clinico: lo que se registra es la HRV que sale
    de aqui, por el ledger; perder la ventana (reinicio) solo retrasa la siguiente HRV.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._streams: OrderedDict[tuple[str, str], _RrStream] = OrderedDict()

    def clear(self) -> None:
        with self._lock:
            self._streams.clear()

    def add(
        self,
        subject: str,
        device: str | None,
        effective: dt.datetime,
        rr_intervals_ms: tuple[float, ...],
        sensor_contact: bool | None,
    ) -> HrvReading | None:
        """Anade los R-R de una trama; devuelve HRV si toca informarla ahora."""
        key = (subject, device or "")
        with self._lock:
            if sensor_contact is False:
                # Sin contacto los R-R son artefacto, y descartarlos deja un hueco en la
                # serie: se empieza de cero, igual que tras un silencio.
                self._streams.pop(key, None)
                return None

            stream = self._streams.get(key)
            if (
                stream is None
                or effective < stream.last_frame
                or effective - stream.last_frame > HRV_MAX_GAP
            ):
                stream = _RrStream(last_frame=effective)
                self._streams[key] = stream
            stream.last_frame = effective
            self._streams.move_to_end(key)
            while len(self._streams) > HRV_MAX_STREAMS:
                self._streams.popitem(last=False)

            for value in plausible_rr(rr_intervals_ms):
                stream.intervals.append((effective, value))
            oldest = effective - HRV_WINDOW
            while stream.intervals and stream.intervals[0][0] < oldest:
                stream.intervals.popleft()

            if len(stream.intervals) < HRV_MIN_RR:
                return None
            if (
                stream.last_emitted is not None
                and effective - stream.last_emitted < HRV_EMIT_EVERY
            ):
                return None
            values = [value for _moment, value in stream.intervals]
            rmssd_ms, sdnn_ms = rmssd(values), sdnn(values)
            if rmssd_ms is None or sdnn_ms is None:
                return None
            stream.last_emitted = effective
            return HrvReading(rmssd_ms, sdnn_ms, effective, len(values))


# La ventana de la ruta BLE. Una sola por proceso, como el almacen.
BLE_RR_WINDOW = RrWindow()


@dataclass(frozen=True, slots=True)
class BleReading:
    """Lo que da una trama: su decodificacion, lo que se registra y la HRV, si toco."""

    measurement: HeartRateMeasurement
    observations: list[VitalObservation]
    hrv: HrvReading | None


class WearableAdapter:
    """Convierte lecturas de un wearable en observaciones canonicas."""

    def __init__(self, subject: str, source: str = "wearable-ble") -> None:
        self.subject = subject
        self.source = source

    def read_ble_frame(
        self,
        frame: bytes,
        effective: dt.datetime,
        window: RrWindow | None = None,
        device: str | None = None,
    ) -> BleReading:
        """Decodifica una trama: siempre el pulso; la HRV, solo desde la ventana.

        Sin `window` no hay HRV: una sola trama no tiene latidos suficientes para que
        el numero signifique algo (ver `HRV_MIN_RR`).
        """
        measurement = parse_heart_rate_measurement(frame)
        confidence = confidence_from_contact(measurement.sensor_contact)

        observations = [
            observation(
                "heart-rate", float(measurement.heart_rate), effective, self.subject,
                self.source, confidence=confidence,
            )
        ]

        hrv = None
        if window is not None:
            hrv = window.add(
                self.subject, device, effective, measurement.rr_intervals_ms,
                measurement.sensor_contact,
            )
        if hrv is not None:
            # Las tramas sin contacto vacian la ventana, asi que la HRV que sale de ella
            # es de tramas con contacto (o sin deteccion de contacto): confianza plena.
            for key, value in (("hrv-rmssd", hrv.rmssd_ms), ("hrv-sdnn", hrv.sdnn_ms)):
                observations.append(
                    observation(key, value, hrv.effective, self.subject, self.source)
                )

        return BleReading(measurement, observations, hrv)

    def from_ble_frame(
        self,
        frame: bytes,
        effective: dt.datetime,
        window: RrWindow | None = None,
        device: str | None = None,
    ) -> list[VitalObservation]:
        """Las observaciones de una trama BLE (pulso, y HRV si la ventana la da)."""
        return self.read_ble_frame(frame, effective, window, device).observations

    def from_apple_health_export(
        self, export: str | bytes, rejected: list[str] | None = None
    ) -> Iterator[VitalObservation]:
        """Lee un export de Apple Health (Salud > exportar datos).

        El XML es grande, asi que se recorre en streaming y se libera cada registro
        tras leerlo.

        UNA LECTURA DESCARTADA SE DICE.
        --------------------------------
        Con `rejected`, cada registro de un tipo que se sabe interpretar pero que no se
        puede importar —sin valor, no numerico, unidad desconocida, fecha ilegible o
        increible, valor imposible— se anota ahi con su motivo y se salta, en vez de
        detener la importacion. Sin `rejected`, cualquiera de ellos lanza: no queda
        ningun camino en que una lectura se pierda en silencio. Antes, lo no numerico
        se saltaba sin avisar.

        EL CICLO Y LA ANTICONCEPCION (lote «ciclo», unidad B1, 2026-11-15).
        --------------------------------------------------------------------
        Ademas de las cantidades (`HKQuantityTypeIdentifier*`), se leen los registros de
        categoria del ciclo (`_APPLE_CATEGORIES`) y la temperatura basal, que es una
        cantidad. Un registro de flujo menstrual da dos lecturas independientes: la
        cantidad (`menstrual-flow`) y, si trae la marca `HKMenstrualCycleStart`, el
        inicio de ciclo (`menstruation-start`). Son independientes a proposito: un flujo
        «unspecified» no tiene numero en la escala de cantidad y se rechaza, pero el
        inicio de la regla que marca sigue siendo un dato, y es el que necesita la linea
        base consciente de la fase. Por eso un registro de flujo puede dar dos rechazos
        con el mismo numero de registro, uno por lectura: lo que se cuenta y se firma son
        lecturas, y el tope de la API (`MAX_IMPORT_RECORDS`) tambien las cuenta a ellas.
        """
        import xml.etree.ElementTree as ET

        # Mapa de tipos de Apple Health a claves del catalogo. Solo se importan
        # los que sabemos interpretar; el resto se ignora en silencio a proposito.
        # Los de categoria del ciclo estan en `_APPLE_CATEGORIES`.
        mapping = {
            "HKQuantityTypeIdentifierHeartRate": "heart-rate",
            "HKQuantityTypeIdentifierRespiratoryRate": "respiratory-rate",
            "HKQuantityTypeIdentifierOxygenSaturation": "oxygen-saturation",
            "HKQuantityTypeIdentifierBodyTemperature": "body-temperature",
            "HKQuantityTypeIdentifierBodyMass": "body-weight",
            "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv-sdnn",
            "HKQuantityTypeIdentifierBasalBodyTemperature": "basal-body-temperature",
        }

        # `element.clear()` vacia el registro, pero el elemento vacio sigue colgado del
        # nodo raiz hasta que termina el parseo. Soltarlo cuesta poco y hay que hacerlo,
        # aunque no sea lo que mas pesa: medido con 20 000 registros, el pico baja de
        # 11,3 a 9,6 MB, unos 80 bytes por registro.
        #
        # LO QUE DE VERDAD MARCA EL PICO ES EL TAMANO DEL FICHERO, NO SU NUMERO DE
        # REGISTROS: unas 4 veces, entre el texto ya decodificado, su copia en el
        # stream y el buffer del parser. Con 200 registros grandes el pico es el mismo
        # que con 20 000 pequenos del mismo tamano total. Por eso el tope que importa es
        # `MAX_IMPORT_BYTES`, y cuantas importaciones corren a la vez (`routes.py`).
        #
        # Para soltar los hermanos ya vistos hace falta la raiz, y la raiz solo llega
        # con el evento `start`.
        context = ET.iterparse(_as_stream(export), events=("start", "end"))
        try:
            _first, root = next(context)
        except StopIteration:  # documento vacio: el bucle no dara ninguna vuelta
            root = None

        number = 0
        for event, element in context:
            if event != "end" or element.tag != "Record":
                continue
            number += 1
            kind = element.get("type", "")
            key = mapping.get(kind)
            raw_value = element.get("value")
            raw_unit = element.get("unit")
            raw_date = element.get("startDate")
            # La marca de inicio de ciclo viaja en un hijo `<MetadataEntry>` del registro, y
            # `clear()` borra los hijos: se lee antes. Solo se mira en el flujo, que es el
            # unico tipo que la lleva, y el registro ya esta entero (evento `end`), asi que
            # leerla no retiene nada mas que el propio registro, que se suelta enseguida.
            raw_start = (
                _cycle_start_flag(element) if kind == _MENSTRUAL_FLOW_TYPE else None
            )
            element.clear()
            if root is not None:
                root.clear()  # sin esto, cada registro leido se queda en memoria vacio
            builders: list[Callable[[], VitalObservation]]
            if key is not None:
                builders = [partial(self._apple_reading, key, raw_value, raw_unit, raw_date)]
            elif kind in _APPLE_CATEGORIES:
                builders = [partial(self._apple_category_reading, kind, raw_value, raw_date)]
                if kind == _MENSTRUAL_FLOW_TYPE:
                    builders.append(partial(self._apple_cycle_start, raw_start, raw_date))
            else:
                continue
            for build in builders:
                try:
                    reading = build()
                except ValueError as exc:
                    if rejected is None:
                        raise
                    rejected.append(f"registro {number} ({kind}): {exc}")
                    continue
                yield reading

    def _apple_category_reading(
        self, kind: str, raw_value: str | None, raw_date: str | None
    ) -> VitalObservation:
        """Un registro de categoria del ciclo, con el numero que EMMA da a su valor.

        El momento es `startDate`, como en las cantidades. Los registros de categoria
        traen tambien `endDate` (un flujo puede cubrir un dia o la regla entera), pero una
        observacion de EMMA es un valor en un instante: el que importa es el comienzo,
        porque es el que HealthKit pide para el inicio de la regla («pass the start of the
        menstrual period to the startDate parameter») y el que fecha el test o el
        anticonceptivo declarado. La duracion no se guarda; no se inventa un instante
        intermedio.
        """
        key, scale = _APPLE_CATEGORIES[kind]
        if not raw_value or not raw_date:
            raise _Unusable("sin valor o sin fecha")
        number = scale.get(raw_value)
        if number is None:
            reason = _APPLE_UNSCALED.get((kind, raw_value))
            if reason is not None:
                raise _Unusable(f"{raw_value[:60]!r} {reason}")
            raise _Unusable(f"valor {raw_value[:60]!r} desconocido para {key}")
        return observation(
            key, number, _apple_moment(raw_date), self.subject, "apple-health"
        )

    def _apple_cycle_start(
        self, raw_start: str | None, raw_date: str | None
    ) -> VitalObservation:
        """La marca `HKMenstrualCycleStart` de un flujo: 1 inicia ciclo, 0 no.

        HealthKit la exige en toda muestra de flujo. Un flujo sin ella (otra aplicacion, un
        export manipulado) entra con su cantidad, pero que no se sepa si abre un ciclo se
        dice como rechazo del inicio: la linea base por fase depende de ese dato, y su
        ausencia no puede pasar en silencio.
        """
        if raw_start is None:
            raise _Unusable(
                f"sin la marca {_CYCLE_START_KEY}, que HealthKit exige en todo flujo: "
                f"el inicio de ciclo no se importa"
            )
        number = _CYCLE_START_VALUES.get(raw_start)
        if number is None:
            raise _Unusable(
                f"marca {_CYCLE_START_KEY} {raw_start[:40]!r} no es 1 ni 0: "
                f"el inicio de ciclo no se importa"
            )
        if not raw_date:
            raise _Unusable("inicio de ciclo sin fecha")
        return observation(
            "menstruation-start", number, _apple_moment(raw_date), self.subject, "apple-health"
        )

    def _apple_reading(
        self, key: str, raw_value: str | None, raw_unit: str | None, raw_date: str | None
    ) -> VitalObservation:
        if not raw_value or not raw_date:
            raise _Unusable("sin valor o sin fecha")
        convert = _APPLE_UNITS[key].get(raw_unit or "")
        if convert is None:
            # Truncada como el resto de partes variables: el motivo viaja en la respuesta
            # de la importacion, y una unidad de 500 KB por registro devolvia al cliente
            # un JSON del tamano de su propia peticion.
            shown = raw_unit[:40] if isinstance(raw_unit, str) else raw_unit
            raise _Unusable(f"unidad {shown!r} no admitida para {key}")
        try:
            value = convert(float(raw_value))
        except ValueError:
            raise _Unusable(f"valor no numérico {raw_value[:40]!r}") from None
        # LA ESCALA DE LA SATURACION LA DECIDE EL FORMATO, NO LA MAGNITUD.
        # ----------------------------------------------------------------
        # Apple exporta SpO2 como fraccion 0-1 aunque la unidad diga "%", y el catalogo
        # la espera en porcentaje. Antes se multiplicaba por 100 "si el valor es <= 1",
        # que es adivinar: `physical_min` de este indicador es 0, asi que un "1" es un
        # valor aceptable —1 % de saturacion, muy por debajo del limite critico de 88— y
        # se convertia en un 100 % perfecto. La alerta mas grave posible quedaba nominal,
        # en silencio y ya firmada en el ledger.
        #
        # Ahora no se adivina: en este formato el valor **es** una fraccion, siempre se
        # escala, y lo que no quepa en 0-1 se rechaza y se dice. Un fichero de otra
        # aplicacion que ponga 97 no entra como 97 % por casualidad: entra como rechazo
        # con su motivo, que es lo unico honesto cuando no se sabe en que escala viene.
        if key == "oxygen-saturation":
            if value > 1.0:
                raise _Unusable(
                    f"saturación {raw_value[:40]!r} fuera de 0-1: "
                    f"Apple Health la exporta como fracción, no como porcentaje"
                )
            value *= 100.0
        return observation(key, value, _apple_moment(raw_date), self.subject, "apple-health")

    def from_google_fit(
        self, payload: dict[str, Any], rejected: list[str] | None = None
    ) -> Iterator[VitalObservation]:
        """Lee la respuesta de `users.dataSources.datasets.get` de Google Fit.

        `rejected` funciona como en `from_apple_health_export`: cada punto de un tipo
        conocido que no se puede importar se anota con su motivo y se salta.
        """
        for number, point in enumerate(payload.get("point", []), start=1):
            try:
                reading = self._fit_reading(point)
            # OverflowError y OSError: un instante o un valor gigantes, que antes
            # tumbaban la importacion entera con un 500.
            except (KeyError, TypeError, ValueError, AttributeError, OverflowError, OSError) as exc:
                if rejected is None:
                    raise
                reason = str(exc) if isinstance(exc, _Unusable) else f"{type(exc).__name__} {exc}"
                rejected.append(f"punto {number}: {reason}"[:300])
                continue
            if reading is not None:
                yield reading

    def _fit_reading(self, point: dict[str, Any]) -> VitalObservation | None:
        mapping = {
            "com.google.heart_rate.bpm": "heart-rate",
            "com.google.oxygen_saturation": "oxygen-saturation",
            "com.google.body.temperature": "body-temperature",
            "com.google.weight": "body-weight",
        }

        key = mapping.get(point.get("dataTypeName", ""))
        if not key:
            return None  # un tipo que no se importa, como los pasos: no es un descarte
        values = point.get("value", [])
        value = values[0].get("fpVal") if values else None
        if value is None:
            raise _Unusable(f"{key} sin valor")
        # Un numero de verdad: "70" como texto o `true` no son una medida.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _Unusable(f"valor no numérico {str(value)[:40]!r}")
        raw_nanos = point["startTimeNanos"]
        try:
            # Google Fit marca el tiempo en nanosegundos desde epoch.
            effective = dt.datetime.fromtimestamp(int(raw_nanos) / 1_000_000_000, tz=dt.UTC)
            number = float(value)
        except (TypeError, ValueError, OverflowError, OSError):
            raise _Unusable(f"instante o valor fuera de rango ({str(raw_nanos)[:40]!r})") from None
        return observation(key, number, _checked_moment(effective), self.subject, "google-fit")


def _same(value: float) -> float:
    return value


# Unidades con que Apple Health exporta cada indicador, y su conversion a la unidad del
# catalogo. Ignorar la unidad metia 170 lb como 170 kg sin ningun aviso, y rechazaba una
# temperatura en degF como "fisicamente imposible": el error que prohibe la invariante 2
# del proyecto, que compila, pasa las pruebas y miente.
_APPLE_UNITS: dict[str, dict[str, Callable[[float], float]]] = {
    "heart-rate": {"count/min": _same},
    "respiratory-rate": {"count/min": _same},
    "oxygen-saturation": {"%": _same},
    "body-temperature": {"degC": _same, "degF": lambda value: (value - 32.0) * 5.0 / 9.0},
    "body-weight": {
        "kg": _same,
        "lb": lambda value: value * 0.45359237,
        "g": lambda value: value / 1000.0,
    },
    "hrv-sdnn": {"ms": _same},
    # La misma propiedad que la temperatura corporal (Temp, °C): misma conversion.
    "basal-body-temperature": {
        "degC": _same, "degF": lambda value: (value - 32.0) * 5.0 / 9.0,
    },
}

# --------------------------------------------------------------------------- #
# El ciclo y la anticoncepcion en el export de Apple Health (lote «ciclo», B1)
#
# Leido en developer.apple.com el 2026-11-15 (datos JSON de las paginas de HealthKit):
#   * `HKCategoryTypeIdentifier`: los tipos son `menstrualFlow`, `intermenstrualBleeding`,
#     `ovulationTestResult` y `contraceptive`. NO EXISTE un tipo `vaginalBleeding`: en
#     iOS 18 no se renombro el tipo sino su enum de valores. Por eso no se mapea ningun
#     `HKCategoryTypeIdentifierVaginalBleeding`; inventarlo seria leer algo que Apple no
#     exporta.
#   * `HKCategoryValueMenstrualFlow` (unspecified, none, light, medium, heavy) esta
#     obsoleto desde iOS 18.0 con `"renamed": "HKCategoryValueVaginalBleeding"`, que tiene
#     los mismos cinco casos. Un export puede traer cualquiera de las dos familias de
#     nombres segun la version que escribio la muestra: se aceptan las dos.
#     (`HKCategoryValueVaginalBleeding` se usa tambien con `bleedingAfterMenopause` y
#     el sangrado en el embarazo, que no estan en el catalogo y no se leen.)
#   * `menstrualFlow` «must include HKMetadataKeyMenstrualCycleStart metadata», verdadero
#     en la primera muestra de la regla y falso en las demas. La pagina no da la cadena
#     de la clave: el export la escribe como `HKMenstrualCycleStart`, con valor 1 o 0.
#   * El valor `positive` del test de ovulacion esta obsoleto desde iOS 13.0: «Use
#     luteinizingHormoneSurge instead.» Se lee como el ascenso de LH.
#   * El sangrado intermenstrual se registra con `HKCategoryValueNotApplicable`: la
#     muestra ES el registro, sin cantidad.
# El numero de cada categoria es el del catalogo (`codes.py`, unidad A3) y sus frases estan
# en `data/instruments_read.json`. Lo que la fuente no ordena no tiene numero y se rechaza
# con su motivo (`_APPLE_UNSCALED`), nunca se le inventa un punto de la escala.
# --------------------------------------------------------------------------- #

_MENSTRUAL_FLOW_TYPE = "HKCategoryTypeIdentifierMenstrualFlow"
_CYCLE_START_KEY = "HKMenstrualCycleStart"
_CYCLE_START_VALUES = {"1": 1.0, "0": 0.0}

_FLOW_AMOUNTS = {"None": 0.0, "Light": 1.0, "Medium": 2.0, "Heavy": 3.0}

_APPLE_CATEGORIES: dict[str, tuple[str, dict[str, float]]] = {
    _MENSTRUAL_FLOW_TYPE: (
        "menstrual-flow",
        {
            f"{family}{name}": number
            for family in ("HKCategoryValueMenstrualFlow", "HKCategoryValueVaginalBleeding")
            for name, number in _FLOW_AMOUNTS.items()
        },
    ),
    "HKCategoryTypeIdentifierIntermenstrualBleeding": (
        "intermenstrual-bleeding", {"HKCategoryValueNotApplicable": 1.0},
    ),
    "HKCategoryTypeIdentifierOvulationTestResult": (
        "ovulation-test",
        {
            "HKCategoryValueOvulationTestResultNegative": 0.0,
            "HKCategoryValueOvulationTestResultEstrogenSurge": 1.0,
            "HKCategoryValueOvulationTestResultLuteinizingHormoneSurge": 2.0,
            # Obsoleto desde iOS 13: «Use luteinizingHormoneSurge instead.»
            "HKCategoryValueOvulationTestResultPositive": 2.0,
        },
    ),
    "HKCategoryTypeIdentifierContraceptive": (
        "contraceptive-in-use",
        {
            "HKCategoryValueContraceptiveUnspecified": 1.0,
            "HKCategoryValueContraceptiveImplant": 2.0,
            "HKCategoryValueContraceptiveInjection": 3.0,
            "HKCategoryValueContraceptiveIntrauterineDevice": 4.0,
            "HKCategoryValueContraceptiveIntravaginalRing": 5.0,
            "HKCategoryValueContraceptiveOral": 6.0,
            "HKCategoryValueContraceptivePatch": 7.0,
        },
    ),
}

# Valores que la fuente define para ESE tipo pero que no son un punto de su escala. Por
# (tipo, valor): el valor de otro enum en un tipo que no le toca es «desconocido», no esto.
_FLOW_UNSPECIFIED = (
    "no tiene número: una cantidad de flujo sin especificar no es un punto de la escala"
)
_APPLE_UNSCALED = {
    (_MENSTRUAL_FLOW_TYPE, "HKCategoryValueMenstrualFlowUnspecified"): _FLOW_UNSPECIFIED,
    (_MENSTRUAL_FLOW_TYPE, "HKCategoryValueVaginalBleedingUnspecified"): _FLOW_UNSPECIFIED,
    (
        "HKCategoryTypeIdentifierOvulationTestResult",
        "HKCategoryValueOvulationTestResultIndeterminate",
    ): "no tiene número: un test inconcluso no es un punto entre negativo y positivo",
}


def _cycle_start_flag(record: Any) -> str | None:
    """El valor crudo de `HKMenstrualCycleStart` en los hijos del registro, si lo trae."""
    for child in record:
        if child.tag == "MetadataEntry" and child.get("key") == _CYCLE_START_KEY:
            value = child.get("value")
            return value if isinstance(value, str) else ""
    return None


# Una lectura importada viene del reloj de un dispositivo real, y fuera de este intervalo
# no es creible. Una sola lectura fechada en 2099 desplazaba al futuro la ventana del
# estado actual y tapaba las desviaciones de hoy; una del ano 1 dejaba `/api/status` en
# 500 para siempre. Basta un reloj de wearable mal puesto, sin ninguna malicia.
EARLIEST_IMPORTED_READING = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
MAX_CLOCK_SKEW = dt.timedelta(minutes=10)


def _checked_moment(moment: dt.datetime) -> dt.datetime:
    try:
        utc = moment.astimezone(dt.UTC)
    except (OverflowError, ValueError):  # p. ej. el ano 1 con un desfase de +23:59
        raise _Unusable("fecha fuera de rango") from None
    if not EARLIEST_IMPORTED_READING <= utc <= dt.datetime.now(dt.UTC) + MAX_CLOCK_SKEW:
        raise _Unusable(f"fecha {utc.isoformat()} fuera del intervalo admitido")
    return utc


def _parse_apple_date(value: str) -> dt.datetime:
    """Apple Health usa `2026-11-14 08:30:00 +0000`."""
    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")


def _apple_moment(raw_date: str) -> dt.datetime:
    """La fecha de un registro de Apple Health, legible y creible, en UTC."""
    try:
        moment = _parse_apple_date(raw_date)
    except ValueError:
        raise _Unusable(f"fecha ilegible {raw_date[:40]!r}") from None
    return _checked_moment(moment)


class _Unusable(ValueError):
    """Un registro de un tipo conocido que no trae un valor utilizable."""


def _as_stream(export: str | bytes) -> Any:
    # En bytes deja que el propio XML declare su codificacion. Hoy la API no usa esa
    # rama —`_xml_text` decodifica y comprueba la codificacion declarada antes de
    # llamar aqui—, pero el adaptador es publico y se le puede dar un fichero tal cual.
    from io import BytesIO, StringIO

    return BytesIO(export) if isinstance(export, bytes) else StringIO(export)
