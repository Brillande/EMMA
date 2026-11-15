"""Carga del dataset MMASH: fisiologia humana real para validacion externa.

POR QUE EXISTE ESTE MODULO
--------------------------
EMMA se validaba solo contra su propio simulador. Es el patron exacto del Epic
Sepsis Model: AUC 0,846 en validacion interna, 0,761 en externa, y en produccion
se le escapaba el 67 % de las sepsis mientras alertaba sobre el 18 % de todos los
ingresados. Un sistema probado unicamente contra los datos que el mismo genera no
ha demostrado nada.

MMASH (Multilevel Monitoring of Activity and Sleep in Healthy people) aporta
fisiologia humana real: 22 sujetos sanos, 24 h continuas, intervalos latido a
latido con banda Polar H7, actigrafia, metricas de sueno y cuestionarios.
Open Access bajo ODbL v1.0.

QUE VALIDA Y QUE NO
-------------------
**Valida** el motor de medida y analisis sobre fisiologia real: el calculo de
HRV, el filtrado de artefactos, la linea base movil y —lo que mas importa— la
**tasa de falsa alarma sobre personas sanas**.

**No valida** el modelo de deriva de vuelo espacial. Son 24 h de varones jovenes
sanos en Tierra. Quien presente esto como validacion de la fisiologia espacial
estaria mintiendo.

DECISIONES DE MAPEO
-------------------
`RR.csv` da `ibi_s` en **segundos**; el codigo de HRV de `ingest/wearable.py`
trabaja en milisegundos. Se convierte explicitamente.

**El cortisol de MMASH NO se carga.** `saliva.csv` da `Cortisol NORM` normalizado
a proteina (valores ~0,03-0,08), no en ug/dL como exige el catalogo (LOINC 2142-8
es Mass/volume). No existe conversion directa. Cargarlo bajo la unidad del
catalogo seria falsificar el dato, que es exactamente el error de propiedad de
medida contra el que advierte `ingest/codes.py`. Solo cabria analisis relativo, y
queda fuera del alcance de este cargador.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import statistics
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.evidence import registry
from app.ingest.fhir import Context, VitalObservation, observation
from app.ingest.wearable import RR_PLAUSIBLE_MS, plausible_rr, rmssd, sdnn

DATASET_URL = "https://physionet.org/files/mmash/1.0.0/MMASH.zip"
# La ficha del dataset en el registro unico de evidencia (`evidence/registry.py`): personas, en
# Tierra. No es fisiologia de vuelo, y quien cite esta validacion lo lee en la propia ficha.
DATASET = registry.get("mmash")
DATASET_LICENCE = "Open Data Commons Open Database License (ODbL) v1.0"
# Lo que MMASH no puede medir: con 24 h por persona, la base de una lectura temprana es siempre
# de la otra mitad del dia (hallazgo 29). Estos conjuntos abiertos tienen varias semanas por
# persona y licencia CC BY 4.0 leida en su pagina el 2026-10-23 (decimosexta ronda, E1). Solo
# LifeSnaps se ha descargado y medido (`validation/lifesnaps.py`, hallazgo 31).
MULTI_WEEK_CANDIDATES: tuple[str, ...] = (
    "lifesnaps-2022",
    "relax-2026-six-week-stress",
    "pmdata-2020",
)
# Lo que dice la literatura de comparar a la misma hora y en la misma condicion (hallazgo 29,
# «Que dice la literatura»; decimosexta ronda, E1, leido el 2026-10-23). Respalda el principio
# de la cobertura de la hora que se midio en MMASH, no sus numeros. El motor no la aplica: la
# regla quedo en su rama sin adoptar, por decision del usuario (2026-10-23). No decide nada.
FAMILY_BASELINE_LITERATURE: tuple[str, ...] = (
    "task-force-hrv-1996",
    "bonnemeier-2003-circadian-hrv",
    "boudreau-2013-circadian-hrv-sleep",
    "lu-1999-postprandial-hrv",
    "laborde-2017-hrv-recommendations",
    "buchheit-2014-hr-monitoring",
    "michael-2017-post-exercise-hrv",
    "mishra-2020-presymptomatic-smartwatch",
    "alavi-2022-realtime-alerting-wearables",
)
ROOT_IN_ZIP = "DataPaper"

# MMASH registra "dia 1" y "dia 2" sin fecha absoluta. Se ancla a una fecha
# sintetica para poder construir marcas de tiempo con zona horaria, que es lo que
# exige `VitalObservation`. La fecha en si no significa nada.
ANCHOR_DATE = dt.date(2018, 1, 1)

# Ventana sobre la que se agregan los latidos para producir una observacion.
# Cinco minutos da ~288 puntos por sujeto y dia, suficiente para la linea base
# movil sin generar cientos de miles de observaciones.
WINDOW = dt.timedelta(minutes=5)

# Latidos minimos en una ventana para que el calculo de HRV signifique algo.
MIN_BEATS_PER_WINDOW = 30

# Codigos de `Activity.csv`:
# 1=dormir 2=laboral 3=luz 4=media 5=intensa 6=comer 7=pantalla
# 8=deporte 9=transporte 10=aseo 11=social 12=siesta
ACTIVE_CODES = {3, 4, 5, 8, 9}
SLEEP_CODES = {1, 12}
WORK_CODES = {2}
MEAL_CODES = {6}

# INFERENCIA DE CONTEXTO DESDE ACELEROMETRIA
#
# El diario deja un tercio de las lecturas sin contexto. Los pasos permiten
# clasificarlas, y son **independientes del pulso**: inferir el estado a partir
# de la frecuencia cardiaca para luego juzgar la frecuencia cardiaca contra ese
# estado seria circular, y enmascararia una bradicardia real.
#
# Umbral medido en el propio dataset: durante actividad declarada la mediana es
# de 14 pasos/min (p75 = 28); fuera de ella, 2 (p75 = 8).
#
# El inclinometro NO sirve: durante las horas de cama marca "Off" el 72 % del
# tiempo y "Lying" solo el 11 %, menos que despierto (14 %).
ACTIVE_STEPS_PER_MINUTE = 10

# LO QUE ESTE CARGADOR PRODUCE, EN UN SOLO SITIO.
#
# La matriz de riesgos (`risk_entity.py`) dice de cada dominio que indicadores salen de MMASH, y
# por tanto sobre que se ha medido la falsa alarma con personas reales. Una lista escrita alli a
# mano se quedaria vieja con el siguiente indicador que se cargue o se deje de cargar. Por eso las
# claves y la fuente de MMASH de cada una viven aqui, y el cargador las emite **desde esta tabla**
# (cada `observation` de abajo la lee): lo que se publica es lo que se carga. Una prueba carga un
# archivo sintetico con la forma de MMASH y falla si lo emitido no es exactamente esta tabla, y
# otra (`external`) hace lo mismo con el dataset real.
#
# El cortisol y el animo no estan, y es deliberado (ver arriba y `_mood`).
HEART_RATE = "heart-rate"
HRV_RMSSD = "hrv-rmssd"
HRV_SDNN = "hrv-sdnn"
SLEEP_DURATION = "sleep-duration"
SLEEP_EFFICIENCY = "sleep-efficiency"
BODY_WEIGHT = "body-weight"
# De que parte de MMASH sale cada lectura: es el `source` de la observacion.
POLAR_SOURCE = "mmash:polar-h7"
ACTIGRAPH_SOURCE = "mmash:actigraph"
USER_INFO_SOURCE = "mmash:user-info"
LOADED: dict[str, str] = {
    HEART_RATE: POLAR_SOURCE,
    HRV_RMSSD: POLAR_SOURCE,
    HRV_SDNN: POLAR_SOURCE,
    SLEEP_DURATION: ACTIGRAPH_SOURCE,
    SLEEP_EFFICIENCY: ACTIGRAPH_SOURCE,
    BODY_WEIGHT: USER_INFO_SOURCE,
}
LOADED_KEYS: tuple[str, ...] = tuple(LOADED)
# Con que se midio en MMASH, dicho para quien lo lee: el aparato del dataset, no el de a bordo.
# Sale de lo que el cargador lee (`RR.csv` de la banda, `sleep.csv` del actigrafo y
# `user_info.csv`), descrito en el bloque de arriba.
# Y cuántas lecturas da: no pesa lo mismo una lectura cada cinco minutos que una por persona. La
# cadencia de la banda es la ventana con que se agregan los latidos (`WINDOW`), leída de ella.
SOURCE_DISPLAY: dict[str, str] = {
    POLAR_SOURCE: (
        f"banda de pecho Polar H7 (intervalos latido a latido; una lectura cada "
        f"{int(WINDOW.total_seconds() // 60)} min)"
    ),
    ACTIGRAPH_SOURCE: "actígrafo (registros de cama; una lectura por noche)",
    USER_INFO_SOURCE: "ficha del participante (user_info.csv; una lectura por persona)",
}
# Lo que valida y lo que no, en una frase: la de la ficha del registro, para el dominio.
VALIDATES = "motor de medida y falsa alarma en Tierra, no fisiología espacial"
# Y hasta dónde: con un día por persona, casi ninguna lectura reúne una línea base personal, y lo
# que se mide es sobre todo el rango de población y los límites de peligro. La cifra está en
# `compliance/external-validation.md` (hallazgo 12); aquí no se copia.
VALIDATES_NOTE = (
    "Con un día de registro por persona, casi ninguna lectura llega a tener línea base personal: "
    "lo que mide es sobre todo el rango de población y los límites de peligro "
    "(`compliance/external-validation.md`, hallazgo 12). La sensibilidad se mide aparte, "
    "inyectando deterioros sobre algunos de estos indicadores: cada riesgo dice cuáles "
    "(`validation/injection.py`)."
)


@dataclass(frozen=True, slots=True)
class ActivityWindow:
    """Un intervalo de actividad declarada por el sujeto."""

    code: int
    start: dt.datetime
    end: dt.datetime

    @property
    def is_active(self) -> bool:
        return self.code in ACTIVE_CODES

    @property
    def context(self) -> Context:
        if self.code in SLEEP_CODES:
            return Context.SLEEP
        if self.code in ACTIVE_CODES:
            return Context.ACTIVE
        if self.code in WORK_CODES:
            return Context.WORK
        if self.code in MEAL_CODES:
            return Context.MEAL
        return Context.REST

    def contains(self, moment: dt.datetime) -> bool:
        return self.start <= moment <= self.end


@dataclass
class SubjectData:
    """Todo lo cargado de un sujeto de MMASH."""

    subject: str
    observations: list[VitalObservation] = field(default_factory=list)
    activity: list[ActivityWindow] = field(default_factory=list)
    beats: int = 0
    rejected_beats: int = 0
    # Pasos por minuto, para inferir contexto donde el diario no llega.
    steps_per_minute: dict[dt.datetime, int] = field(default_factory=dict)
    # Minutos en los que el acelerometro declara que NO lo llevan puesto.
    unworn_minutes: set[dt.datetime] = field(default_factory=set)

    def inferred_context(self, moment: dt.datetime) -> Context:
        """Estado deducido de la acelerometria cuando no hay diario.

        Solo distingue movimiento de quietud. No intenta separar sueno de
        reposo tranquilo —los pasos no lo permiten— porque el sueno ya viene de
        los registros de cama, que son un dato mejor.
        """
        minute = moment.replace(second=0, microsecond=0)
        # CERO PASOS CON EL APARATO QUITADO NO ES REPOSO, ES SILENCIO.
        #
        # El inclinometro declara "Off" cuando no detecta orientacion: el
        # acelerometro no esta puesto. Sin esta comprobacion, sus cero pasos se
        # leian como quietud. Medido: 170 lecturas de pulso de los 22 sujetos
        # entraban como reposo con el aparato quitado, y **son la causa de las
        # alarmas de user_15**: dos horas con el pulso entre 112 y 192, con
        # aceleracion cero y el inclinometro en "Off" todo el rato —lo que deja
        # un actigrafo fuera del cuerpo mientras la banda de pecho sigue
        # midiendo—, comparadas contra el limite de peligro **en reposo**, 110.
        # Desconocido las compara contra 150, que es lo que el motor ya hacia
        # bien cuando no sabe.
        if minute in self.unworn_minutes:
            return Context.UNKNOWN
        steps = self.steps_per_minute.get(minute)
        if steps is None:
            return Context.UNKNOWN
        return Context.ACTIVE if steps >= ACTIVE_STEPS_PER_MINUTE else Context.REST

    @property
    def artifact_rate(self) -> float:
        total = self.beats + self.rejected_beats
        return self.rejected_beats / total if total else 0.0

    def is_active_at(self, moment: dt.datetime) -> bool:
        return any(window.is_active and window.contains(moment) for window in self.activity)

    def resolved_context(self, moment: dt.datetime) -> Context:
        """Contexto declarado si lo hay; si no, el inferido de acelerometria."""
        declared = self.context_at(moment)
        if declared is not Context.UNKNOWN:
            return declared
        return self.inferred_context(moment)

    def context_at(self, moment: dt.datetime) -> Context:
        """Estado declarado por el sujeto en ese instante.

        Es lo que permite que la linea base compare reposo con reposo. En una
        mision el equivalente es el horario de a bordo, que es aun mas fiable que
        un diario de actividad.
        """
        for window in self.activity:
            if window.contains(moment):
                return window.context
        return Context.UNKNOWN


# MMASH TRAE UNA ETIQUETA DE DIA CORRUPTA EN DOS SUJETOS.
#
# El protocolo es de ~36 h y la columna `day` vale 1 o 2. En **user_8 y user_9**
# vale `-29` en lugar de `2`. Tomado al pie de la letra, coloca la segunda mitad
# del registro **30 dias en el pasado**: esos dos sujetos abarcaban 31,5 dias con
# un hueco de 710 h, frente a los 1,36-1,45 dias de los otros veinte.
#
# Que `-29` es el dia 2 no es una suposicion, esta medido. Las franjas horarias
# coinciden exactamente con las de un sujeto sano:
#
#   user_15 (sano)   day=1: 09:30 -> 23:59    day=2:   00:00 -> 10:59
#   user_8  (roto)   day=1: 09:53 -> 23:59    day=-29: 00:00 -> 09:08
#   user_9  (roto)   day=1: 10:06 -> 23:59    day=-29: 00:00 -> 09:24
#
# Una etiqueta no positiva es la jornada siguiente, no un viaje al pasado.
#
# Por que importa y no es cosmetico: con el eje temporal roto, la ventana movil
# de 14 dias descartaba medio registro, el ajuste de tendencia cruzaba un vacio
# de un mes, y una inyeccion de deriva de 15 lpm/dia acumulaba sobre 30 dias
# falsos hasta 370 lpm. Lo delato el limite de posibilidad fisica: sin esa
# comprobacion, el dataset llevaba dos sujetos corruptos **en silencio** desde la
# primera medida de falsa alarma.
NONPOSITIVE_DAY_IS_SECOND = 2


def _moment(day: str, clock: str) -> dt.datetime | None:
    """Convierte (dia, hora) de MMASH en una marca de tiempo con zona."""
    try:
        index = int(float(day))
    except (TypeError, ValueError):
        return None

    if index < 1:
        index = NONPOSITIVE_DAY_IS_SECOND
    day_offset = index - 1

    parts = clock.strip().split(":")
    try:
        hour, minute = int(parts[0]), int(parts[1])
        second = int(float(parts[2])) if len(parts) > 2 else 0
    except (IndexError, TypeError, ValueError):
        return None

    return dt.datetime.combine(
        ANCHOR_DATE + dt.timedelta(days=day_offset),
        dt.time(hour % 24, minute % 60, second % 60),
        tzinfo=dt.UTC,
    )


def _read_csv(archive: zipfile.ZipFile, path: str) -> list[dict[str, str]]:
    try:
        with archive.open(path) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
            return list(csv.DictReader(text))
    except KeyError:
        return []


# El protocolo de MMASH dura unas 36 h. Se deja margen holgado: el objetivo no es
# ajustar fino, es que un eje temporal roto **falle en voz alta** en vez de
# producir en silencio una serie de 31 dias que nadie mira.
MAX_PLAUSIBLE_SPAN = dt.timedelta(days=3)


def _reject_implausible_span(data: SubjectData) -> None:
    """Falla si el registro de un sujeto abarca mas de lo que dura el protocolo.

    La leccion de `day = -29` no es que haya que arreglar ese valor: es que una
    etiqueta corrupta produjo una serie absurda **sin que nada protestara**, y
    siguio alimentando la tasa de falsa alarma publicada. Si el dataset trae otro
    defecto que no he encontrado, esto lo para aqui en vez de dejarlo entrar en
    una medida que luego se presenta como evidencia.
    """
    if not data.observations:
        return
    span = data.observations[-1].effective - data.observations[0].effective
    if span > MAX_PLAUSIBLE_SPAN:
        raise ValueError(
            f"{data.subject}: el registro abarca {span.days} días, más de los "
            f"{MAX_PLAUSIBLE_SPAN.days} plausibles para el protocolo de MMASH. "
            f"Sospecha de etiqueta de día corrupta"
        )


class MmashLoader:
    """Lee MMASH desde el zip y lo normaliza al modelo canonico de EMMA."""

    def __init__(self, archive_path: Path) -> None:
        if not archive_path.exists():
            raise FileNotFoundError(
                f"no se encuentra MMASH en {archive_path}. Descargar de "
                f"{DATASET_URL} ({DATASET_LICENCE})"
            )
        self.archive_path = archive_path

    def subjects(self) -> list[str]:
        with zipfile.ZipFile(self.archive_path) as archive:
            names = {
                name.split("/")[1]
                for name in archive.namelist()
                if name.startswith(f"{ROOT_IN_ZIP}/") and len(name.split("/")) > 2
            }
        return sorted(names, key=lambda name: int(name.split("_")[1]))

    # ------------------------------------------------------------------ #

    def load(self, subject: str) -> SubjectData:
        data = SubjectData(subject=subject)
        with zipfile.ZipFile(self.archive_path) as archive:
            base = f"{ROOT_IN_ZIP}/{subject}"
            # El diario de actividad casi no registra el sueno —nadie apunta
            # "estoy dormido"— pero `sleep.csv` trae las horas reales de cama.
            # Sin esto, las lecturas nocturnas se comparan contra una base de
            # vigilia y se marcan por pulso bajo: la bradicardia del sueno es
            # fisiologia normal, no un hallazgo.
            data.activity = list(self._sleep_windows(archive, base)) + list(
                self._activity(archive, base)
            )
            data.steps_per_minute, data.unworn_minutes = self._steps(archive, base)
            self._load_cardiac(archive, base, data)
            data.observations.extend(self._sleep(archive, base, subject))
            data.observations.extend(self._body(archive, base, subject))
            data.observations.extend(self._mood(archive, base, subject))
        data.observations.sort(key=lambda item: item.effective)
        _reject_implausible_span(data)
        return data

    def load_all(self) -> Iterator[SubjectData]:
        for subject in self.subjects():
            yield self.load(subject)

    # ------------------------------------------------------------------ #

    def _steps(
        self, archive: zipfile.ZipFile, base: str
    ) -> tuple[dict[dt.datetime, int], set[dt.datetime]]:
        """Pasos por minuto y minutos con el aparato quitado, alineados con los latidos.

        ALINEACION VERIFICADA. El indice de `Actigraph.csv` es un contador
        continuo de segundos desde el inicio del registro, no segundos del dia:
        para user_1 el dia 1 abarca 82..49853 y el dia 2 sigue en 49860, sin
        reiniciarse. La frontera de medianoche cae donde debe si el origen es el
        inicio de la serie de RR (de 10:10 a medianoche hay 49 800 s).

        Se comprobo antes de usarla: sin verificar, alinear mal desplazaria todo
        el contexto y el resultado pareceria valido igualmente.
        """
        rows = _read_csv(archive, f"{base}/Actigraph.csv")
        rr = _read_csv(archive, f"{base}/RR.csv")
        if not rows or not rr:
            return {}, set()

        start = _moment(rr[0].get("day", ""), rr[0].get("time", ""))
        if start is None:
            return {}, set()

        indices = [int(row[""]) for row in rows if row.get("", "").strip().isdigit()]
        if not indices:
            return {}, set()
        origin = min(indices)

        per_minute: dict[dt.datetime, int] = {}
        # Muestras con y sin orientacion detectada, por minuto: un minuto cuenta
        # como "quitado" si la mayoria de sus muestras dicen que lo esta.
        off_samples: dict[dt.datetime, int] = {}
        samples: dict[dt.datetime, int] = {}
        for row in rows:
            raw = row.get("", "").strip()
            if not raw.isdigit():
                continue
            moment = start + dt.timedelta(seconds=int(raw) - origin)
            minute = moment.replace(second=0, microsecond=0)
            samples[minute] = samples.get(minute, 0) + 1
            if (row.get("Inclinometer Off") or "0").strip() == "1":
                off_samples[minute] = off_samples.get(minute, 0) + 1
            try:
                per_minute[minute] = per_minute.get(minute, 0) + int(row.get("Steps", 0) or 0)
            except (TypeError, ValueError):
                continue

        unworn = {
            minute
            for minute, total in samples.items()
            if off_samples.get(minute, 0) * 2 > total
        }
        return per_minute, unworn

    def _sleep_windows(
        self, archive: zipfile.ZipFile, base: str
    ) -> Iterator[ActivityWindow]:
        """Ventanas de sueno reales, de `sleep.csv`.

        Van **primero** en la lista de actividad para que `context_at` las
        encuentre antes que cualquier solape del diario: si el sujeto estaba
        dormido, eso manda sobre lo que hubiera apuntado.
        """
        for row in _read_csv(archive, f"{base}/sleep.csv"):
            start = _moment(row.get("Onset Date", ""), row.get("Onset Time", ""))
            end = _moment(row.get("Out Bed Date", ""), row.get("Out Bed Time", ""))
            if start is None or end is None:
                continue
            if end < start:
                # Cruza medianoche: el despertar es del dia siguiente.
                end += dt.timedelta(days=1)
            yield ActivityWindow(code=1, start=start, end=end)

    def _activity(self, archive: zipfile.ZipFile, base: str) -> Iterator[ActivityWindow]:
        for row in _read_csv(archive, f"{base}/Activity.csv"):
            start = _moment(row.get("Day", ""), row.get("Start", ""))
            end = _moment(row.get("Day", ""), row.get("End", ""))
            if start is None or end is None or end < start:
                continue
            try:
                code = int(float(row.get("Activity", "")))
            except (TypeError, ValueError):
                continue
            yield ActivityWindow(code=code, start=start, end=end)

    def _load_cardiac(
        self, archive: zipfile.ZipFile, base: str, data: SubjectData
    ) -> None:
        """Agrega los latidos en ventanas y calcula pulso y HRV reales.

        Los intervalos pasan por `plausible_rr` de `ingest/wearable.py`, el mismo
        filtro que usa la ingesta en vivo. Que un dataset real lo atraviese es
        parte de lo que se esta validando.
        """
        buckets: dict[dt.datetime, list[float]] = {}

        for row in _read_csv(archive, f"{base}/RR.csv"):
            moment = _moment(row.get("day", ""), row.get("time", ""))
            if moment is None:
                continue
            try:
                interval_ms = float(row["ibi_s"]) * 1000.0  # MMASH da segundos
            except (KeyError, TypeError, ValueError):
                continue

            low, high = RR_PLAUSIBLE_MS
            if not (low <= interval_ms <= high):
                data.rejected_beats += 1
                continue

            data.beats += 1
            key = _floor_to_window(moment)
            buckets.setdefault(key, []).append(interval_ms)

        for key, intervals in sorted(buckets.items()):
            if len(intervals) < MIN_BEATS_PER_WINDOW:
                continue

            clean = plausible_rr(intervals)
            if not clean:
                continue

            mean_interval = statistics.fmean(clean)
            state = data.resolved_context(key)
            data.observations.append(
                observation(
                    HEART_RATE, round(60000.0 / mean_interval, 2), key,
                    data.subject, LOADED[HEART_RATE], context=state,
                )
            )
            for name, value in ((HRV_RMSSD, rmssd(clean)), (HRV_SDNN, sdnn(clean))):
                if value is not None:
                    data.observations.append(
                        observation(
                            name, value, key, data.subject, LOADED[name],
                            context=state,
                        )
                    )

    def _sleep(
        self, archive: zipfile.ZipFile, base: str, subject: str
    ) -> Iterator[VitalObservation]:
        """Sueno agregado por noche, no por segmento.

        MMASH registra el sueno **fragmentado**: user_1 tiene dos episodios la
        misma noche (144 y 196 min). Emitir cada segmento como si fuera una noche
        entera daba duraciones de 2-3 h y marcaba al 95 % de los sujetos. Era un
        error de lectura del dataset, no un hallazgo clinico.

        La eficiencia se pondera por el tiempo dormido de cada segmento: la media
        simple daria el mismo peso a una siesta de 20 min que a seis horas.
        """
        nights: dict[str, list[tuple[float, float, dt.datetime]]] = {}

        for row in _read_csv(archive, f"{base}/sleep.csv"):
            moment = _moment(row.get("Out Bed Date", ""), row.get("Out Bed Time", ""))
            minutes = _number(row.get("Total Sleep Time (TST)"))
            if moment is None or minutes is None:
                continue
            efficiency = _number(row.get("Efficiency"))
            night = row.get("Out Bed Date", "").strip()
            nights.setdefault(night, []).append(
                (minutes, efficiency if efficiency is not None else float("nan"), moment)
            )

        for segments in nights.values():
            total_minutes = sum(minutes for minutes, _, _ in segments)
            if total_minutes <= 0:
                continue
            wake = max(moment for _, _, moment in segments)

            yield observation(
                SLEEP_DURATION, round(total_minutes / 60.0, 3), wake,
                subject, LOADED[SLEEP_DURATION],
            )

            weighted = [
                (minutes, efficiency)
                for minutes, efficiency, _ in segments
                if efficiency == efficiency  # descarta NaN
            ]
            covered = sum(minutes for minutes, _ in weighted)
            # Una noche cuyos segmentos con eficiencia suman cero minutos no tiene eficiencia
            # que ponderar: se calla, en vez de dividir por cero y tumbar la carga del sujeto.
            if covered > 0:
                mean_efficiency = sum(m * e for m, e in weighted) / covered
                yield observation(
                    SLEEP_EFFICIENCY, round(mean_efficiency, 2), wake,
                    subject, LOADED[SLEEP_EFFICIENCY],
                )

    def _body(
        self, archive: zipfile.ZipFile, base: str, subject: str
    ) -> Iterator[VitalObservation]:
        for row in _read_csv(archive, f"{base}/user_info.csv"):
            weight = _number(row.get("Weight"))
            if weight is not None:
                yield observation(
                    BODY_WEIGHT, weight,
                    dt.datetime.combine(ANCHOR_DATE, dt.time(0, 0), tzinfo=dt.UTC),
                    subject, LOADED[BODY_WEIGHT],
                )

    def _mood(
        self, archive: zipfile.ZipFile, base: str, subject: str
    ) -> Iterator[VitalObservation]:
        """NO se carga el animo. Se deja aqui la razon, que es la parte util.

        La tentacion era mapear el afecto positivo de PANAS (10-50) al indicador
        `mood-valence` del catalogo (0-10) con un reescalado lineal. Se probo, y
        la mediana de PANAS en MMASH (25) caia en 3,75 — justo por debajo del
        umbral de 4 del catalogo. El resultado: la mitad de los sujetos sanos
        marcados por un mapeo que yo mismo habia inventado.

        PANAS y una escala de valencia **no miden lo mismo**, y no existe
        conversion publicada entre ambas. Inventar una y presentarla como
        equivalencia es el mismo error que usar un codigo LOINC con la unidad de
        otra propiedad: una falsedad silenciosa que sobrevive porque nadie la
        comprueba.

        Igual que con el cortisol, la decision es no cargarlo. El dominio
        conductual queda cubierto por sueno, que si tiene correspondencia directa.
        """
        return
        yield  # pragma: no cover - marca la funcion como generador


def _floor_to_window(moment: dt.datetime) -> dt.datetime:
    seconds = int(WINDOW.total_seconds())
    stamp = int(moment.timestamp()) // seconds * seconds
    return dt.datetime.fromtimestamp(stamp, tz=dt.UTC)


def _number(raw: Any) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
