"""Carga de LifeSnaps: semanas de una misma persona para medir lo que MMASH no puede.

POR QUE EXISTE ESTE MODULO
--------------------------
MMASH son 24 h por persona. Con 12 h de desfase, la base de una lectura temprana sale siempre de
la otra mitad del dia, y solo 102 de sus 18 460 lecturas llegan a juzgarse con base personal
(hallazgo 29). La regla de cobertura de la hora y el respaldo de familia no se pueden decidir
ahi. El usuario decidio el 2026-10-23 no adoptar nada y «medir antes con LifeSnaps o RELAX».

LifeSnaps (Zenodo, doi:10.5281/zenodo.7229547, CC BY 4.0) son 71 personas con un Fitbit Sense
durante unas 8 semanas: pulso cada pocos segundos, pasos por minuto, registros de sueno y de
ejercicio, y encuestas de «donde estas» tres veces al dia.

QUE VALIDA Y QUE NO
-------------------
**Valida** el motor de linea base con varias semanas por persona: la tasa de falsa alarma sobre
vida diaria en Tierra y la sensibilidad a deterioros inyectados sobre esa misma serie. **No
valida** fisiologia espacial: son adultos en su vida diaria, y no se reclutaron como «sanos» con
un cribado clinico: nadie declara un deterioro, pero tampoco se descarta (un catarro de dos dias
cuenta aqui como falsa alarma).

LO QUE ESTE CONJUNTO NO TRAE, DICHO ANTES DE USARLO
---------------------------------------------------
- **No hay RR ni SDNN.** La VFC es la RMSSD que calcula el reloj cada 5 min, y **solo durante el
  sueno**. El colapso de HRV de referencia (-30 ms de SDNN) no se puede inyectar aqui: se inyecta
  en la RMSSD nocturna (`family_variants.rmssd_collapse`), y es otra cifra, no la misma.
- **No hay diario de actividad.** El estado sale del registro de sueno, del de ejercicio, de los
  pasos (independientes del pulso, como en MMASH) y de la encuesta. `MEAL` no existe aqui.
- **Las marcas son del reloj local de la persona, sin zona.** Se etiquetan UTC solo porque
  `VitalObservation` exige zona: es lo que hace que «la misma hora» sea la del dia de esa persona.

CONTEXTO DE TRABAJO: UNA ETIQUETA DE MOMENTO
--------------------------------------------
La encuesta dice «WORK/SCHOOL» o «HOME_OFFICE» en un instante, no un horario. Se etiquetan como
trabajo las lecturas quietas a menos de `WORK_TAG_HALF_WIDTH` de la respuesta. Es de diseno de
esta medida, y sale pobre a proposito: es justo el caso para el que existe la familia, un estado
fino con menos lecturas que la base minima. Lo que no se hace es deducir el trabajo del calendario
(lunes a viernes de 9 a 17): seria inventar el dato que se quiere medir.

POR QUE HAY UN PASO DE NORMALIZACION
------------------------------------
`fitbit.bson` son 9,7 GB dentro del zip: decenas de millones de documentos. `normalize` los reduce
una vez a un fichero pequeno por persona en `normalized/`, y el cargador lee solo eso. Lector de
BSON propio, de lo que el volcado usa, para no traer una dependencia por un guion de validacion:
un tipo que no conoce falla en voz alta.
"""

from __future__ import annotations

import bisect
import datetime as dt
import gzip
import json
import os
import struct
import zipfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from app.evidence import registry
from app.ingest.fhir import Context, VitalObservation, observation
from app.validation.mmash import ACTIVE_STEPS_PER_MINUTE

RECORD_URL = "https://zenodo.org/api/records/7229547"
ARCHIVE_NAME = "rais_anonymized.zip"
# La huella que publica Zenodo para ese fichero (leida en su API el 2026-11-01).
ARCHIVE_MD5 = "726afe263ab4b900a721eac19b2ca13a"
DATASET = registry.get("lifesnaps-2022")
DATASET_LICENCE = "Creative Commons Attribution 4.0 International"
DATASET_CITATION = (
    "Yfantidou S et al. LifeSnaps, a 4-month multi-modal dataset capturing unobtrusive snapshots "
    "of our lives in the wild. Sci Data 2022;9:663. doi:10.5281/zenodo.7229547"
)
FITBIT_MEMBER = "rais_anonymized/mongo_rais_anonymized/fitbit.bson"
SEMA_MEMBER = "rais_anonymized/mongo_rais_anonymized/sema.bson"


def dataset_dir() -> Path:
    """Donde esta el conjunto: `data/lifesnaps/`, o `EMMA_LIFESNAPS_DIR` desde otra copia."""
    configured = os.environ.get("EMMA_LIFESNAPS_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "data" / "lifesnaps"


# La misma ventana de 5 min de MMASH (`mmash.WINDOW`): las dos tasas por lectura se comparan.
WINDOW_SECONDS = 300
# Muestras de pulso minimas en una ventana. El reloj da una cada 5-15 s, 20-60 en 5 min: por debajo
# de 10 el reloj apenas vio el pulso. De diseno de esta medida.
MIN_SAMPLES_PER_WINDOW = 10
# La confianza 0 del reloj es «sin senal»; lo demas se acepta como lo da.
NO_SIGNAL_CONFIDENCE = 0
# Fraccion de los 5 min con senal util que el reloj declara para su RMSSD. De diseno.
MIN_RMSSD_COVERAGE = 0.5
WORK_TAG_HALF_WIDTH = dt.timedelta(minutes=30)
WORK_PLACES = frozenset({"WORK/SCHOOL", "HOME_OFFICE"})

HEART_RATE = "heart-rate"
HRV_RMSSD = "hrv-rmssd"
FITBIT_SOURCE = "lifesnaps:fitbit-sense"
LOADED: dict[str, str] = {HEART_RATE: FITBIT_SOURCE, HRV_RMSSD: FITBIT_SOURCE}


# --------------------------------------------------------------------------- #
# BSON
# --------------------------------------------------------------------------- #


def _elements(buffer: bytes, position: int, end: int) -> dict[str, Any]:
    """Los elementos de un documento BSON, de `position` a su byte final (exclusivo)."""
    out: dict[str, Any] = {}
    while position < end:
        kind = buffer[position]
        name_end = buffer.index(b"\x00", position + 1)
        name = buffer[position + 1 : name_end].decode("utf-8")
        position = name_end + 1
        value: Any
        if kind == 0x01:
            value = struct.unpack_from("<d", buffer, position)[0]
            position += 8
        elif kind == 0x02:
            size = struct.unpack_from("<i", buffer, position)[0]
            value = buffer[position + 4 : position + 3 + size].decode("utf-8", "replace")
            position += 4 + size
        elif kind in (0x03, 0x04):
            size = struct.unpack_from("<i", buffer, position)[0]
            inner = _elements(buffer, position + 4, position + size - 1)
            value = list(inner.values()) if kind == 0x04 else inner
            position += size
        elif kind == 0x07:
            value = buffer[position : position + 12].hex()
            position += 12
        elif kind == 0x08:
            value = buffer[position] != 0
            position += 1
        elif kind == 0x09:
            value = struct.unpack_from("<q", buffer, position)[0]
            position += 8
        elif kind == 0x0A:
            value = None
        elif kind == 0x10:
            value = struct.unpack_from("<i", buffer, position)[0]
            position += 4
        elif kind == 0x12:
            value = struct.unpack_from("<q", buffer, position)[0]
            position += 8
        else:
            raise ValueError(f"tipo BSON {kind:#x} en {name!r}: este lector no lo conoce")
        out[name] = value
    return out


def read_documents(stream: IO[bytes]) -> Iterator[dict[str, Any]]:
    """Los documentos de un volcado BSON, uno a uno y sin cargarlo entero."""
    while True:
        head = stream.read(4)
        if not head:
            return
        if len(head) < 4:
            raise ValueError("volcado BSON cortado en la cabecera de un documento")
        size = struct.unpack("<i", head)[0]
        body = stream.read(size - 4)
        if len(body) != size - 4:
            raise ValueError("volcado BSON cortado a mitad de un documento")
        yield _elements(head + body, 4, size - 1)


# --------------------------------------------------------------------------- #
# Normalizacion: una pasada por el volcado, un fichero por persona
# --------------------------------------------------------------------------- #


def _epoch(text: str) -> int:
    """Segundos de la marca del reloj de la persona, leida como si fuera UTC (ver arriba)."""
    if "/" in text:
        moment = dt.datetime.strptime(text, "%m/%d/%y %H:%M:%S")
    else:
        moment = dt.datetime.fromisoformat(text)
    return int(moment.replace(tzinfo=dt.UTC).timestamp())


def _bin(epoch: int) -> int:
    return epoch // WINDOW_SECONDS * WINDOW_SECONDS


@dataclass
class _Raw:
    """Lo que se conserva de una persona durante la pasada."""

    heart: dict[int, list[float]] = field(default_factory=dict)  # ventana -> [suma, muestras]
    steps: dict[int, int] = field(default_factory=dict)  # ventana -> maximo de pasos/min
    rmssd: dict[int, tuple[float, float]] = field(default_factory=dict)  # marca -> (ms, cobertura)
    sleep: set[tuple[int, int]] = field(default_factory=set)
    exercise: set[tuple[int, int]] = field(default_factory=set)
    work: set[int] = field(default_factory=set)


def _take_fitbit(raw: _Raw, kind: str, data: dict[str, Any]) -> None:
    if kind == "heart_rate":
        value = data["value"]
        if value["confidence"] != NO_SIGNAL_CONFIDENCE:
            slot = raw.heart.setdefault(_bin(_epoch(data["dateTime"])), [0.0, 0.0])
            slot[0] += value["bpm"]
            slot[1] += 1
    elif kind == "steps":
        window = _bin(_epoch(data["dateTime"]))
        raw.steps[window] = max(raw.steps.get(window, 0), int(data["value"]))
    elif kind == "Heart Rate Variability Details":
        raw.rmssd[_epoch(data["timestamp"])] = (data["rmssd"], data["coverage"])
    elif kind == "sleep":
        raw.sleep.add((_epoch(data["startTime"]), _epoch(data["endTime"])))
    elif kind == "exercise":
        start = _epoch(data["startTime"])
        raw.exercise.add((start, start + data["duration"] // 1000))


_FITBIT_KINDS = frozenset({
    "heart_rate", "steps", "Heart Rate Variability Details", "sleep", "exercise",
})


def normalize(
    archive: Path, destination: Path, progress: Callable[[int], None] | None = None,
) -> int:
    """Reduce el volcado a un `<persona>.json.gz` por persona. Devuelve cuantas personas."""
    people: dict[str, _Raw] = {}
    with zipfile.ZipFile(archive) as bundle:
        with bundle.open(FITBIT_MEMBER) as stream:
            for count, document in enumerate(read_documents(stream)):
                kind = document.get("type")
                if kind in _FITBIT_KINDS:
                    _take_fitbit(people.setdefault(document["id"], _Raw()), kind, document["data"])
                if progress is not None and count % 5_000_000 == 0:
                    progress(count)
        with bundle.open(SEMA_MEMBER) as stream:
            for document in read_documents(stream):
                data = document["data"]
                if data.get("PLACE") in WORK_PLACES and data.get("COMPLETED_TS"):
                    raw = people.setdefault(document["user_id"], _Raw())
                    raw.work.add(_epoch(data["COMPLETED_TS"]))

    destination.mkdir(parents=True, exist_ok=True)
    for subject, raw in people.items():
        payload = {
            "subject": subject,
            "heart": sorted(
                [window, round(total / samples, 3), int(samples)]
                for window, (total, samples) in raw.heart.items()
            ),
            "steps": sorted([window, most] for window, most in raw.steps.items()),
            "rmssd": sorted([moment, *pair] for moment, pair in raw.rmssd.items()),
            "sleep": sorted(list(item) for item in raw.sleep),
            "exercise": sorted(list(item) for item in raw.exercise),
            "work": sorted(raw.work),
        }
        with gzip.open(destination / f"{subject}.json.gz", "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
    return len(people)


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #


def _moment(epoch: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(epoch, dt.UTC)


def _merged(intervals: list[list[int]]) -> list[list[int]]:
    """Los intervalos ordenados y sin solapes: el registro de sueno trae siestas y duplicados."""
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        elif end > start:
            merged.append([start, end])
    return merged


def _inside(intervals: list[list[int]], starts: list[int], epoch: int) -> bool:
    position = bisect.bisect_right(starts, epoch)
    return position > 0 and epoch <= intervals[position - 1][1]


@dataclass
class SubjectSeries:
    """Las lecturas de una persona de LifeSnaps, ya con su estado."""

    subject: str
    observations: list[VitalObservation] = field(default_factory=list)

    @property
    def days(self) -> int:
        """Dias con alguna lectura: los que cuentan como registro, sin los huecos."""
        return len({item.effective.date() for item in self.observations})


def context_resolver(payload: dict[str, Any]) -> Callable[[int], Context]:
    """El estado de una ventana. Sueno y ejercicio mandan; despues, los pasos; y la encuesta.

    Una ventana sin pasos registrados queda desconocida, no quieta: igual que en MMASH, callar no
    es reposo. Los pasos son de los 5 min de la ventana, no de su primer minuto como en MMASH:
    `normalize` guarda el minuto mas activo de cada una.
    """
    sleep = _merged(payload["sleep"])
    exercise = _merged(payload["exercise"])
    sleep_starts = [item[0] for item in sleep]
    exercise_starts = [item[0] for item in exercise]
    steps: dict[int, int] = {window: most for window, most in payload["steps"]}
    work: list[int] = payload["work"]
    half = int(WORK_TAG_HALF_WIDTH.total_seconds())

    def resolve(epoch: int) -> Context:
        if _inside(sleep, sleep_starts, epoch):
            return Context.SLEEP
        if _inside(exercise, exercise_starts, epoch):
            return Context.ACTIVE
        window = _bin(epoch)
        if window not in steps:
            return Context.UNKNOWN
        if steps[window] >= ACTIVE_STEPS_PER_MINUTE:
            return Context.ACTIVE
        if bisect.bisect_right(work, epoch + half) > bisect.bisect_left(work, epoch - half):
            return Context.WORK
        return Context.REST

    return resolve


def _observations(payload: dict[str, Any]) -> Iterator[VitalObservation]:
    subject = payload["subject"]
    state = context_resolver(payload)
    for window, mean, samples in payload["heart"]:
        if samples >= MIN_SAMPLES_PER_WINDOW:
            yield observation(
                HEART_RATE, mean, _moment(window), subject, LOADED[HEART_RATE],
                context=state(window),
            )
    for moment, rmssd, coverage in payload["rmssd"]:
        if coverage >= MIN_RMSSD_COVERAGE:
            yield observation(
                HRV_RMSSD, rmssd, _moment(moment), subject, LOADED[HRV_RMSSD],
                context=state(moment),
            )


class LifeSnapsLoader:
    """Lee lo que dejo `normalize` y lo pasa al modelo canonico de EMMA."""

    def __init__(self, folder: Path) -> None:
        if not folder.is_dir() or not any(folder.glob("*.json.gz")):
            raise FileNotFoundError(
                f"no esta LifeSnaps normalizado en {folder}: scripts/fetch_lifesnaps.py"
            )
        self.folder = folder

    def subjects(self) -> list[str]:
        return sorted(path.name.removesuffix(".json.gz") for path in self.folder.glob("*.json.gz"))

    def load(self, subject: str) -> SubjectSeries:
        with gzip.open(self.folder / f"{subject}.json.gz", "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        return SubjectSeries(subject, sorted(_observations(payload), key=lambda o: o.effective))

    def load_all(self) -> Iterable[SubjectSeries]:
        return (self.load(subject) for subject in self.subjects())
