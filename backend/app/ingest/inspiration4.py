"""Analíticas reales de la tripulación de Inspiration4 (NASA OSDR, OSD-569).

Por qué existe: EMMA no tiene —ni puede tener— constantes de astronautas: son datos médicos
protegidos. Lo más cercano que es público de verdad son las analíticas de los cuatro tripulantes
civiles de Inspiration4 (septiembre de 2021, 3 días en órbita), que NASA publica procesadas en
OSDR. Son datos humanos de una misión real, y enseñan algo que un simulador no puede demostrar:
**los linfocitos de los cuatro bajaron al volver** (R+1 frente a L-3).

Qué se hace con ellos: se reproducen en la línea de tiempo de EMMA —el lanzamiento en el inicio
de misión configurado y el regreso tres días después—, firmados como simulados, porque no son
lecturas de esta tripulación. La fuente dice de dónde salen.

Qué NO son: constantes continuas, datos en vuelo (no hubo extracción en órbita) ni una muestra
representativa: cuatro civiles y tres días. Tampoco se "limpian" a mano: una fila incoherente
se detecta, se excluye y se declara (ver `load`).

Cita que pide OSDR: "Data are courtesy of the NASA Open Science Data Repository
(https://osdr.nasa.gov/bio/repo)". Estudio: OSD-569, fichero LSDS-7 CBC TRANSFORMED.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

from app.ingest.fhir import EvidenceContext, VitalObservation, observation

DATA_FILE = (
    Path(__file__).resolve().parents[1]
    / "data" / "osdr" / "OSD-569_LSDS-7_Complete_Blood_Count_CBC_TRANSFORMED.csv"
)
# Huella del fichero descargado de OSDR el 2026-09-24. Si cambia, no se reproduce nada: un
# fichero distinto ya no es el que se revisó.
DATA_SHA256 = "32e4f9c97d3b636b5d5c2e72dab8c4d3319dee64c437508b092dad04603b2b8f"
STUDY_URL = "https://osdr.nasa.gov/bio/repo/data/studies/OSD-569"
SOURCE = "simulator:inspiration4"
MISSION_DAYS = 3  # Inspiration4 estuvo tres días en órbita

# Columna del CSV -> (clave del catálogo, divisor hasta 10^3/µL).
_COLUMNS = {
    "white_blood_cell_count_value_thousand_per_microliter": ("leukocytes", 1.0),
    "absolute_lymphocytes_value_cells_per_microliter": ("lymphocytes", 1000.0),
    "absolute_neutrophils_value_cells_per_microliter": ("neutrophils", 1000.0),
}
# Tripulante de OSDR -> sujeto de EMMA.
CREW = {"C001": "crew-01", "C002": "crew-02", "C003": "crew-03", "C004": "crew-04"}

# Porcentaje de cada población en la fórmula, para cotejarlo con su absoluto.
_PERCENT = {
    "lymphocytes": "lymphocytes_value_percent",
    "neutrophils": "neutrophils_value_percent",
}
# Cuánto puede separarse un absoluto de "porcentaje × total" por redondeo del analizador.
_RELATIVE_TOLERANCE = 0.10
_ABSOLUTE_TOLERANCE = 0.1  # 10^3/µL: 100 células


@dataclass
class Replay:
    observations: list[VitalObservation] = field(default_factory=list)
    # Muestras apartadas y por qué. Se devuelven, no se esconden.
    excluded: list[str] = field(default_factory=list)


class DataFileChanged(RuntimeError):
    """El fichero de OSDR no es el que se revisó."""


def moment(timepoint: str, launch: dt.datetime) -> dt.datetime:
    """`L-92` o `R+45` en la línea de tiempo de EMMA."""
    sign_at = 1
    days = int(timepoint[sign_at + 1:])
    if timepoint.startswith("L-"):
        return launch - dt.timedelta(days=days)
    if timepoint.startswith("R+"):
        return launch + dt.timedelta(days=MISSION_DAYS + days)
    raise ValueError(f"momento de muestra desconocido: {timepoint!r}")


def load(launch: dt.datetime, raw: bytes | None = None) -> Replay:
    """Las analíticas reproducidas con el lanzamiento en `launch`."""
    data = DATA_FILE.read_bytes() if raw is None else raw
    if raw is None and hashlib.sha256(data).hexdigest() != DATA_SHA256:
        raise DataFileChanged(f"{DATA_FILE.name} no coincide con la huella revisada")
    replay = Replay()
    for row in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
        crew, _, timepoint, *_ = row["Sample Name"].split("_")
        subject = CREW.get(crew)
        if subject is None:
            replay.excluded.append(f"{row['Sample Name']}: tripulante desconocido")
            continue
        values = {}
        for column, (key, divisor) in _COLUMNS.items():
            try:
                values[key] = float(row[column]) / divisor
            except (KeyError, ValueError):
                values[key] = float("nan")
        percents = {}
        for key, column in _PERCENT.items():
            try:
                percents[key] = float(row[column])
            except (KeyError, ValueError):
                percents[key] = float("nan")
        problem = _incoherent(values, percents)
        if problem is not None:
            replay.excluded.append(f"{crew} {timepoint}: {problem}")
            continue
        when = moment(timepoint, launch)
        replay.observations.extend(
            observation(
                key, round(value, 3), when, subject, SOURCE,
                # Analiticas reales de vuelo, aunque las firme la identidad del simulador.
                evidence_context=EvidenceContext.SPACEFLIGHT,
            )
            for key, value in values.items()
        )
    replay.observations.sort(key=lambda item: item.effective)
    return replay


def _incoherent(values: dict[str, float], percents: dict[str, float]) -> str | None:
    """Por qué una muestra no se puede usar, o `None` si es coherente.

    Cada absoluto tiene que casar con su porcentaje por el total. No basta con que los
    absolutos sumen el total: en OSD-569 hay una fila (C003, L-92) con las columnas
    desplazadas en origen —el "absoluto de linfocitos" es el valor de los neutrófilos, y así
    sucesivamente—, y como son los mismos números permutados, la suma cuadra igual.
    """
    if any(value != value for value in (*values.values(), *percents.values())):  # NaN
        return "falta un valor"
    for key, percent in percents.items():
        expected = percent / 100 * values["leukocytes"]
        if abs(values[key] - expected) > max(_RELATIVE_TOLERANCE * expected, _ABSOLUTE_TOLERANCE):
            return (
                f"{key}: absoluto {values[key]:.2f} frente a {expected:.2f} según su "
                f"porcentaje ({percent} %): columnas desplazadas en origen"
            )
    return None
