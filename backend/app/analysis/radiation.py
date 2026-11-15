"""Radiacion en tres escalas: aguda, de mision y de carrera (base de conocimiento §7).

La base de conocimiento (§7) pone «HERA/Orion y dosimetria: deteccion de hazard y alertas
operacionales», y la conversacion de ideacion lo resume: «HERA tells the crew when radiation is
dangerous. Our system could help determine what that exposure means for each crew member over
time». HERA es ahi el Hybrid Electronic Radiation Assessor, el instrumento de radiacion de Orion
(fichas `nasa-orion-radiation-protection`, `nasa-artemis1-radiation-research` y
`nasa-artemis2-eyes-on-sun`), no el analogo terrestre Human Exploration Research Analog de los
bancos de prueba, que comparte siglas. EMMA no lee HERA; desde la decimosexta ronda (E8) el
panel lo dice, con la fase del ciclo solar y lo que una fuente dice del fin del refugio
(`evidence/radiation_read.py`). Antes de este modulo EMMA tenia dos piezas
sueltas: el evento solar activo (DONKI) y una dosis de carrera que alguien tenia que facilitar.
Faltaba la escala intermedia —cuanto lleva esta mision— y el tiempo hasta la accion.

- **Aguda** (minutos a horas): evento de particulas solares activo. Tiempo hasta la accion con
  el procedimiento de Orion (NASA): hasta 1 h para montar el refugio con la masa de a bordo y
  hasta 24 h de permanencia. Se muestra; no cambia el riesgo.
- **Mision** (dias a meses): integral de la tasa de dosis absorbida registrada desde el inicio
  de la mision, por el factor de calidad medio medido en vuelo (el mismo de
  `environment/dosimetry.py`). Es una dosis equivalente **inferida**, y se rotula asi.
- **Carrera** (anos): la dosis previa que declara el perfil del tripulante mas la de esta
  mision, frente a los 600 mSv de NASA-STD-3001 [V1 4030]. Sin dosis previa declarada, no se
  supone cero: se dice que falta.

PROYECCION, TIPOS Y LIMITES A CORTO PLAZO (decimocuarta ronda, C7)
------------------------------------------------------------------
La conversacion de origen pide para el evento solar «detectar → predecir exposicion → alertar»
y la base de conocimiento §7 que el proyecto distinga los tipos de radiacion. Faltaban tres
cosas, y las tres se muestran sin tocar el riesgo:

- **Proyeccion al fin de mision configurado.** La justificacion de [V1 4030] dice que la dosis
  de carrera «includes all past spaceflight radiation exposures, plus the projected exposure for
  an upcoming mission». La tasa media registrada se prolonga hasta el fin configurado
  (`core/mission.py`): es PREDICHA, con su `model_version`, y supone tasa constante, asi que no
  preve eventos solares. **No entra en `cumulative_dose_msv` ni en ningun nivel**: el riesgo de
  radiacion sigue leyendo solo la dosis acumulada facilitada (`analysis/risk.py`).
- **Horquilla por tipo de radiacion.** La dosis absorbida proyectada por los factores de calidad
  medidos con TEPC en el SLS-1 para radiacion atrapada (1,83) y rayos cosmicos galacticos (2,74),
  los de `environment/dosimetry.py`, ahora con ficha (`badhwar-1992-sls1-tepc`, leida en PubMed).
  Es INFERIDA y no es un intervalo de confianza: dice cuanto seria si toda la dosis fuera de un
  tipo o del otro. EMMA no sabe la mezcla de tipos de esta mision (OSDR RadLab no da espectro).
- **Limites de 30 dias y 1 ano** de la Tabla 4.8-1 de NASA-STD-3001 Vol 1 Rev C, por organo.
  Estan en mGy-Eq (dosis absorbida ponderada por RBE) o en mGy (sistema nervioso central), no en
  la dosis efectiva en mSv que lleva EMMA: se muestran en su unidad, sin convertir, y no se
  comparan con ninguna dosis de EMMA, que no tiene dosis por organo.
"""

from __future__ import annotations

import copy
import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any

from app.core import display, i18n
from app.core.mission import mission_day
from app.environment.dosimetry import DEFAULT_MODEL, MEAN_QUALITY_FACTORS, QualityFactorModel
from app.evidence import radiation_read, registry
from app.ingest.fhir import VitalObservation

MISSION_DOSE_MODEL = "dosis-mision:trapecio-uGy/h×Q-medio@1"
PROJECTION_MODEL = "proyeccion-dosis-mision:tasa-media-constante×Q-medio@1"
# Los factores de calidad por tipo de radiacion, medidos con TEPC en el SLS-1: la ficha que
# nombran en `environment/dosimetry.py` (`ref_id`), no otra copia de la fuente.
TEPC_SOURCE = registry.cite(
    str(MEAN_QUALITY_FACTORS[QualityFactorModel.TRAPPED].ref_id),
    "factores de calidad medidos en el Spacelab SLS-1 (1991, órbita baja) para radiación "
    "atrapada (1,83), rayos cósmicos galácticos (2,74) y el vuelo entero (2,38)",
)
# La tabla de limites a corto plazo por organo.
SHORT_TERM_SOURCE = registry.cite(
    "nasa-std-3001-vol1-rev-c",
    "Tabla 4.8-1, «Dose Limits for Career/Non-Cancer Effects (in mGy-Eq. or mGy)», página 40",
)
# El inglés de para qué se cita cada ficha: la ficha es del registro; la frase, de este módulo.
i18n.en_many({
    str(TEPC_SOURCE.relevance): (
        "quality factors measured on Spacelab SLS-1 (1991, low Earth orbit) for trapped "
        "radiation (1.83), galactic cosmic rays (2.74) and the whole flight (2.38)"
    ),
    str(SHORT_TERM_SOURCE.relevance): (
        "Table 4.8-1, “Dose Limits for Career/Non-Cancer Effects (in mGy-Eq. or mGy)”, page 40"
    ),
})
SHELTER_BUILD = dt.timedelta(hours=1)
SHELTER_MAX_STAY = dt.timedelta(hours=24)
# El procedimiento de refugio: su ficha en el registro unico de evidencia
# (`evidence/registry.py`), citada por identificador.
ORION_SOURCE = registry.cite("nasa-orion-radiation-protection")
# Lo leído junto a la radiacion (E8), validado al importar como las fichas de arriba: un fichero
# roto se ve al arrancar, no como un fallo de `/status` a media mision.
READINGS_REFS = frozenset(radiation_read.cited_refs())


@dataclass(frozen=True, slots=True)
class _Integral:
    """La dosis absorbida integrada desde el inicio de la mision, y sobre que tramo."""

    absorbed_ugy: float
    samples: int
    first: dt.datetime
    last: dt.datetime

    @property
    def hours_covered(self) -> float:
        return (self.last - self.first).total_seconds() / 3600


def _origin(mission_start: dt.date) -> dt.datetime:
    return dt.datetime.combine(mission_start, dt.time(0, 0, tzinfo=dt.UTC))


def _integral(rates: Sequence[VitalObservation], mission_start: dt.date) -> _Integral | None:
    """Regla del trapecio sobre la tasa absorbida (µGy/h) registrada desde el inicio."""
    origin = _origin(mission_start)
    series = sorted(
        (item for item in rates if item.key == "absorbed-dose-rate" and item.effective >= origin),
        key=lambda item: item.effective,
    )
    if len(series) < 2:
        return None
    absorbed_ugy = 0.0
    for before, after in zip(series, series[1:], strict=False):
        hours = (after.effective - before.effective).total_seconds() / 3600
        absorbed_ugy += (before.value + after.value) / 2 * hours
    return _Integral(absorbed_ugy, len(series), series[0].effective, series[-1].effective)


def mission_dose(
    rates: Sequence[VitalObservation], mission_start: dt.date
) -> dict[str, Any] | None:
    """Dosis equivalente de esta mision a partir de la tasa absorbida registrada (µGy/h)."""
    integral = _integral(rates, mission_start)
    if integral is None:
        return None
    absorbed_ugy = integral.absorbed_ugy
    quality = MEAN_QUALITY_FACTORS[DEFAULT_MODEL]
    return {
        "value_msv": round(absorbed_ugy / 1000 * quality.value, 3),
        "absorbed_mgy": round(absorbed_ugy / 1000, 3),
        "quality_factor": quality.value,
        "quality_source": i18n.loc(quality.source),
        # La ficha del registro que respalda el Q aplicado (decimocuarta ronda, C7).
        "quality_ref": quality.ref_id,
        "samples": integral.samples,
        "hours_covered": round(integral.hours_covered, 1),
        "observation_type": "inferred",
        "model_version": MISSION_DOSE_MODEL,
        "basis": i18n.tr(
            "integral de la tasa de dosis absorbida registrada desde el inicio de la misión, "
            "por el factor de calidad medio medido en vuelo; no es una dosis medida",
            "integral of the absorbed dose rate recorded since the start of the mission, times "
            "the mean quality factor measured in flight; it is not a measured dose",
        ),
    }


def mission_projection(
    rates: Sequence[VitalObservation],
    *,
    mission_start: dt.date,
    mission_days: int,
    prior_career_msv: float | None,
    limit_msv: float,
) -> dict[str, Any] | None:
    """La dosis de esta mision proyectada al fin configurado, PREDICHA (ver cabecera).

    Se muestra y no alimenta nada: ni `cumulative_dose_msv` ni ningun nivel. `None` sin dosis de
    mision que prolongar (la escala de mision ya dice que falta la tasa).

    Como la dosis de mision, empieza en la primera lectura de tasa: el tramo anterior, si lo hay,
    no se extrapola hacia atras, y la base dice cuantos dias quedan fuera.
    """
    integral = _integral(rates, mission_start)
    if integral is None:
        return None
    end = _origin(mission_start) + dt.timedelta(days=mission_days)
    common: dict[str, Any] = {
        "observation_type": "predicted",
        "model_version": PROJECTION_MODEL,
        "mission_end": end.date().isoformat(),
        "end_day": mission_days,
        "scope": i18n.tr(
            "se muestra; no entra en la dosis acumulada del riesgo ni en ningún nivel",
            "shown only; it does not enter the cumulative dose used for risk or any level",
        ),
    }
    # El fin de mision con la misma regla que la fase posvuelo (`core/mission.py`).
    ended = mission_day(integral.last, mission_start) >= mission_days
    if ended or integral.hours_covered <= 0:
        reason = (
            f"la misión configurada terminó el día {mission_days}: no queda tramo que proyectar"
            if ended
            else "las lecturas de tasa no cubren ningún intervalo: no hay tasa media que prolongar"
        )
        if i18n.current() == "en":
            reason = (
                f"the configured mission ended on day {mission_days}: there is no stretch left "
                "to project"
                if ended
                else "the rate readings cover no interval: there is no mean rate to extend"
            )
        return {**common, "value_msv": None, "basis": reason}
    rate_ugy_h = integral.absorbed_ugy / integral.hours_covered
    remaining_h = (end - integral.last).total_seconds() / 3600
    absorbed_mgy = (integral.absorbed_ugy + rate_ugy_h * remaining_h) / 1000
    mean = MEAN_QUALITY_FACTORS[DEFAULT_MODEL]
    trapped = MEAN_QUALITY_FACTORS[QualityFactorModel.TRAPPED]
    cosmic = MEAN_QUALITY_FACTORS[QualityFactorModel.GALACTIC_COSMIC]
    value_msv = absorbed_mgy * mean.value
    uncovered_days = int(mission_day(integral.first, mission_start))
    uncovered = (
        f"; no cuenta los {uncovered_days} días anteriores a la primera lectura de tasa"
        if uncovered_days >= 1
        else ""
    )
    uncovered_en = uncovered and (
        f"; it does not count the {uncovered_days} "
        f"{'day' if uncovered_days == 1 else 'days'} before the first rate reading"
    )
    career: dict[str, Any]
    if prior_career_msv is None:
        career = {
            "value_msv": None,
            "basis": (
                "sin dosis previa declarada en el perfil del tripulante: la carrera no se "
                "proyecta y no se supone cero"
            ),
        }
        if i18n.current() == "en":
            career["basis"] = (
                "no prior dose declared in the crew member's profile: the career dose is not "
                "projected and zero is not assumed"
            )
    else:
        career = _career_total(
            prior_career_msv, value_msv, limit_msv, "predicted",
            i18n.tr(
                "dosis previa declarada más la proyectada de esta misión; la justificación de "
                "[V1 4030] cuenta en la carrera la exposición proyectada de la misión",
                "declared prior dose plus the projected dose of this mission; the rationale of "
                "[V1 4030] counts the projected exposure of the mission in the career dose",
            ),
        )
    return {
        **common,
        "value_msv": round(value_msv, 3),
        "absorbed_mgy": round(absorbed_mgy, 3),
        "quality_factor": mean.value,
        "rate_ugy_per_h": round(rate_ugy_h, 3),
        "remaining_days": round(remaining_h / 24, 1),
        "basis": i18n.tr(
            f"dosis de esta misión más la tasa media registrada "
            f"({display.number(rate_ugy_h, 2)} µGy/h) prolongada hasta el fin de misión "
            f"configurado (día {mission_days}), por el factor de calidad medio; supone tasa "
            "constante: no prevé eventos solares, y la media incluye todo lo registrado, "
            f"también un evento solar pasado si lo hubo{uncovered}",
            f"dose of this mission plus the mean recorded rate "
            f"({display.number(rate_ugy_h, 2)} µGy/h) extended to the configured end of "
            f"mission (day {mission_days}), times the mean quality factor; it assumes a "
            "constant rate: it does not foresee solar events, and the mean includes everything "
            f"recorded, also a past solar event if there was one{uncovered_en}",
        ),
        # La horquilla por tipo de radiacion: INFERIDA, con la fuente de sus dos Q.
        "by_type": {
            "low_msv": round(absorbed_mgy * trapped.value, 3),
            "high_msv": round(absorbed_mgy * cosmic.value, 3),
            "low_quality_factor": trapped.value,
            "high_quality_factor": cosmic.value,
            "observation_type": "inferred",
            "basis": i18n.tr(
                "si toda la dosis absorbida proyectada fuera radiación atrapada (Q "
                f"{display.number(trapped.value, 2)}) o toda rayos cósmicos galácticos (Q "
                f"{display.number(cosmic.value, 2)}), factores medidos con TEPC en el "
                "Spacelab SLS-1 (1991, órbita baja); no es un intervalo de confianza: EMMA no "
                "sabe la mezcla de tipos de esta misión",
                "if all the projected absorbed dose were trapped radiation (Q "
                f"{display.number(trapped.value, 2)}) or all galactic cosmic rays (Q "
                f"{display.number(cosmic.value, 2)}), factors measured with a TEPC on "
                "Spacelab SLS-1 (1991, low Earth orbit); it is not a confidence interval: EMMA "
                "does not know the mix of radiation types of this mission",
            ),
            "source": _tepc_source(),
        },
        "career": {**career, "limit_msv": limit_msv, "limit_source": "NASA-STD-3001 [V1 4030]"},
    }


def _career_total(
    prior_msv: float, added_msv: float, limit_msv: float, observation_type: str, basis: str
) -> dict[str, Any]:
    """La carrera con dosis previa declarada: previa + la de esta mision, sobre el limite."""
    total = prior_msv + added_msv
    return {
        "value_msv": round(total, 3),
        "prior_msv": prior_msv,
        # Sin limite positivo no hay fraccion que dar (y no se divide por cero).
        "fraction": round(total / limit_msv, 4) if limit_msv > 0 else None,
        "observation_type": observation_type,
        "basis": basis,
    }


@cache
def _tepc_source_cached() -> dict[str, Any]:
    return TEPC_SOURCE.to_dict()


def _tepc_source() -> dict[str, Any]:
    # La ficha resuelta no cambia en vida del proceso: se resuelve una vez (el nivel de evidencia
    # pasa por el lexico de Polaris) y cada respuesta lleva su copia.
    return _relevance_in_language(copy.deepcopy(_tepc_source_cached()))


def _relevance_in_language(cited: dict[str, Any]) -> dict[str, Any]:
    """Una ficha citada con su `relevance` en el idioma de la petición; el resto, del registro."""
    if cited.get("relevance") is not None:
        cited["relevance"] = i18n.loc(cited["relevance"])
    return cited


# --------------------------------------------------------------------------- #
# Limites a corto plazo por organo: NASA-STD-3001 Vol 1 Rev C, Tabla 4.8-1
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Cell:
    """Una casilla de la tabla: la cifra, o lo que dice la norma cuando no da cifra."""

    value: float | None
    absent: str | None = None
    # El texto de la norma en esa casilla, tal cual («Not applicable», «-»). Va aparte de
    # `absent` porque, dentro de la casilla, una columna estrecha no lo cabia.
    literal: str | None = None


def _absent(literal: str, meaning: str) -> Cell:
    return Cell(None, meaning, literal)


@dataclass(frozen=True, slots=True)
class OrganLimit:
    """Una fila de la Tabla 4.8-1, tal cual (página 40 de 86, leída el 2026-10-21)."""

    organ: str
    organ_display: str
    thirty_day: Cell
    one_year: Cell
    career: Cell
    unit: str
    note: str | None = None


# Las dos unidades de la tabla. Ninguna es el mSv de EMMA, y no se convierten (ver cabecera).
RBE_WEIGHTED = "mGy-Eq"
ABSORBED = "mGy"

SHORT_TERM_LIMITS: tuple[OrganLimit, ...] = (
    OrganLimit(
        "Lens", "Cristalino", Cell(1000.0), Cell(2000.0), Cell(4000.0), RBE_WEIGHTED,
        "la norma los fija para prevenir cataratas graves tempranas (menos de 5 años), por "
        "ejemplo por un evento solar",
    ),
    OrganLimit("Skin", "Piel", Cell(1500.0), Cell(3000.0), Cell(6000.0), RBE_WEIGHTED),
    OrganLimit(
        "Blood-forming Organs", "Órganos hematopoyéticos", Cell(250.0), Cell(500.0),
        _absent("Not applicable", "no aplica"), RBE_WEIGHTED,
    ),
    OrganLimit(
        "Circulatory System", "Sistema circulatorio", Cell(250.0), Cell(500.0), Cell(1000.0),
        RBE_WEIGHTED, "promedio sobre el músculo cardiaco y las arterias adyacentes",
    ),
    OrganLimit(
        "Central Nervous System", "Sistema nervioso central", Cell(500.0), Cell(1000.0),
        Cell(1500.0), ABSORBED, "calculado en el hipocampo",
    ),
    OrganLimit(
        "Central Nervous System (Z≥10)", "Sistema nervioso central (Z ≥ 10)",
        _absent("-", "sin cifra"), Cell(100.0), Cell(250.0), ABSORBED,
        "calculado en el hipocampo",
    ),
)
# El inglés de lo que EMMA escribe de cada fila. `organ` ya es el nombre de la norma, en inglés.
i18n.en_many({
    "Cristalino": "Lens",
    "Piel": "Skin",
    "Órganos hematopoyéticos": "Blood-forming organs",
    "Sistema circulatorio": "Circulatory system",
    "Sistema nervioso central": "Central nervous system",
    "Sistema nervioso central (Z ≥ 10)": "Central nervous system (Z ≥ 10)",
    "no aplica": "not applicable",
    "sin cifra": "no figure",
    "la norma los fija para prevenir cataratas graves tempranas (menos de 5 años), por "
    "ejemplo por un evento solar": (
        "the standard sets them to prevent early (under 5 years) severe cataracts, for example "
        "from a solar event"
    ),
    "promedio sobre el músculo cardiaco y las arterias adyacentes": (
        "average over the heart muscle and the adjacent arteries"
    ),
    "calculado en el hipocampo": "calculated at the hippocampus",
})


def _cell(cell: Cell, unit: str) -> dict[str, Any]:
    if cell.value is None:
        absent = None if cell.absent is None else i18n.loc(cell.absent)
        return {"value": None, "unit": None, "absent": absent, "literal": cell.literal}
    return {"value": cell.value, "unit": unit, "absent": None, "literal": None}


@i18n.lang_cache
def _short_term_limits() -> dict[str, Any]:
    return {
        "rows": [
            {
                "organ": row.organ,
                "organ_display": i18n.loc(row.organ_display),
                # La unidad de la fila: la misma en sus tres casillas con cifra.
                "unit": row.unit,
                "thirty_day": _cell(row.thirty_day, row.unit),
                "one_year": _cell(row.one_year, row.unit),
                "career": _cell(row.career, row.unit),
                "note": None if row.note is None else i18n.loc(row.note),
            }
            for row in SHORT_TERM_LIMITS
        ],
        "units": i18n.tr(
            "en la unidad de la norma: mGy-Eq (dosis absorbida ponderada por la eficacia "
            "biológica relativa, RBE) y mGy en el sistema nervioso central; no son los mSv de "
            "dosis efectiva que lleva EMMA y no se convierten; «no aplica» y «sin cifra» son "
            "«Not applicable» y «-» en la tabla",
            "in the unit of the standard: mGy-Eq (absorbed dose weighted by relative biological "
            "effectiveness, RBE) and mGy for the central nervous system; they are not the mSv "
            "of effective dose that EMMA carries and they are not converted; “not applicable” "
            "and “no figure” are “Not applicable” and “-” in the table",
        ),
        "scope": i18n.tr(
            "se muestran; EMMA no tiene dosis por órgano y no les compara ninguna cifra suya, "
            "ni cambian el riesgo",
            "shown only; EMMA has no per-organ dose and compares none of its figures with "
            "them, and they do not change the risk",
        ),
        "source": _relevance_in_language(SHORT_TERM_SOURCE.to_dict()),
    }


# Por qué `elapsed_minutes` puede venir sin cifra (`time_to_action`).
SHELTER_NOT_STARTED = (
    "El refugio empieza después del corte de Tierra: en este instante de referencia no hay tiempo "
    "transcurrido que contar"
)
i18n.en(
    SHELTER_NOT_STARTED,
    "The shelter starts after Earth's cut-off: at this reference instant there is no elapsed "
    "time to count",
)


def short_term_limits() -> dict[str, Any]:
    """La Tabla 4.8-1 para mostrar: en su unidad, sin convertir y sin comparar con nada.

    Es fija: se compone una vez y cada respuesta lleva su copia (nadie comparte el diccionario).
    """
    return copy.deepcopy(_short_term_limits())


def time_to_action(event_time: dt.datetime | None, now: dt.datetime) -> dict[str, Any] | None:
    """Detección → refugio montado → permanencia máxima, con el procedimiento de Orion.

    El tiempo transcurrido se cuenta hasta `now`, que en Tierra es la referencia de su corte y el
    evento es el del reloj real: puede ser posterior. Antes salía negativo. Ahora, como lo que
    `/crew/compare` no cuenta (sin cifra y con su frase): `null` y `elapsed_note`. Un 0 diría que
    el refugio acaba de empezar, y en esa referencia todavía no ha empezado.
    """
    if event_time is None:
        return None
    started = now >= event_time
    action: dict[str, Any] = {
        "detected_at": event_time.isoformat(),
        "shelter_ready_by": (event_time + SHELTER_BUILD).isoformat(),
        "max_stay_until": (event_time + SHELTER_MAX_STAY).isoformat(),
        "elapsed_minutes": round((now - event_time).total_seconds() / 60) if started else None,
        "elapsed_note": None if started else SHELTER_NOT_STARTED,
        "basis": i18n.tr(
            "procedimiento de Orion: hasta 1 h para montar el refugio con la masa de a bordo y "
            "hasta 24 h dentro; se muestra y no cambia el riesgo",
            "Orion procedure: up to 1 h to build the shelter with the mass on board and up to "
            "24 h inside; shown only, it does not change the risk",
        ),
        "source": ORION_SOURCE.to_dict(),
    }
    if action["elapsed_note"] is not None:
        action["elapsed_note"] = i18n.loc(action["elapsed_note"])
    return action


def scales(
    *,
    active_event: dict[str, Any] | None,
    event_time: dt.datetime | None,
    now: dt.datetime,
    mission: dict[str, Any] | None,
    prior_career_msv: float | None,
    limit_msv: float,
    projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    career: dict[str, Any]
    if prior_career_msv is None:
        career = {
            "value_msv": None,
            "basis": "sin dosis previa declarada en el perfil del tripulante: no se supone cero",
        }
        if i18n.current() == "en":
            career["basis"] = (
                "no prior dose declared in the crew member's profile: zero is not assumed"
            )
    else:
        this_mission = mission["value_msv"] if mission is not None else 0.0
        career = _career_total(
            prior_career_msv, this_mission, limit_msv, "inferred",
            i18n.tr(
                "dosis previa declarada más la inferida de esta misión",
                "declared prior dose plus the inferred dose of this mission",
            ),
        )
    readings = radiation_read.describe()
    return {
        "acute": {
            "active_event": active_event,
            "time_to_action": time_to_action(event_time, now),
            # Decimosexta ronda (E8): a bordo de Orion el aviso lo da HERA, y EMMA no lo lee; y lo
            # que una fuente dice del fin del refugio, como fuente. Ninguno de los dos cambia la
            # permanencia de arriba ni el riesgo.
            "onboard_warning": readings["onboard_warning"],
            "shelter_exit": readings["shelter_exit"],
        },
        "mission": mission,
        "career": {**career, "limit_msv": limit_msv, "limit_source": "NASA-STD-3001 [V1 4030]"},
        # Lo de C7 (ver cabecera): PREDICHA al fin configurado y los limites de 30 dias y 1 ano.
        # Ninguno de los dos alimenta `cumulative_dose_msv` ni un nivel.
        "projection": projection,
        "short_term_limits": short_term_limits(),
        # La fase del ciclo solar segun la nota fechada de NASA y NOAA (E8): descriptiva. La
        # proyeccion de arriba no la lee y sigue suponiendo tasa constante.
        "solar_cycle": readings["solar_cycle"],
    }
