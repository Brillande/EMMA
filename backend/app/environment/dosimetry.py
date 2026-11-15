"""Conversion de dosis absorbida a dosis equivalente.

POR QUE ESTE MODULO EXISTE
--------------------------
La primera version integraba la dosis con un factor de calidad Q = 1, declarado
como "aproximacion valida para la componente de fondo". Era peor que una
aproximacion: era **un error de magnitud**. El factor de calidad medio medido en
vuelo esta en torno a 2,4, asi que Q = 1 subestima la dosis equivalente unas dos
veces y media.

El contraste lo confirma: la serie real de DosTel del 2022-04-01 integra
0,27 mSv/dia con Q = 1, por debajo del rango documentado de 0,3-0,8 mSv/dia para
la ISS. Con Q = 2,38 da 0,65 mSv/dia, dentro del rango.

QUE SE PUEDE Y QUE NO SE PUEDE CALCULAR CON LOS DATOS DISPONIBLES
-----------------------------------------------------------------
NASA-STD-3001 [V1 4030] especifica que la dosis efectiva se calcula con el
modelo NASA Q y parametros de mujer de 35 anos. Ese modelo necesita el espectro
de particulas (LET por particula). Se comprobo empiricamente que **OSDR RadLab
no lo proporciona**:

  - `quality_factor`, `lineal_energy` y `let` devuelven HTTP 500: no existen.
  - `dose_equivalent_rate` **si existe en el esquema** pero nunca esta poblado:
    98 688 filas revisadas en cuatro ventanas entre 2011 y 2022, con diez
    instrumentos distintos (DosTel1/2, Lidal, REM-Lid, Liulin-5-D1/D3,
    SPACEDOS02A-F, y varios REM/RAD de Columbus), todas con el campo nulo.

Asi que el modelo NASA Q **no es implementable con esta fuente de datos**. No es
una carencia de la implementacion: es un limite del dato, establecido midiendolo.

QUE HACE ESTE MODULO EN CONSECUENCIA
------------------------------------
1. Implementa la funcion Q(L) de **ICRP 60**, que es la que se usaria en cuanto
   hubiera espectro. Es un estandar nombrado y verificable, no una constante
   inventada.
2. Cuando hay dosis equivalente **medida**, la usa y lo dice.
3. Cuando no la hay, aplica un factor de calidad medio **citado**, y la
   estimacion viaja con su procedencia: quien la lea sabe si es medida o
   estimada, y con que Q.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core import display, i18n

# --------------------------------------------------------------------------- #
# ICRP 60: Q en funcion de la transferencia lineal de energia
# --------------------------------------------------------------------------- #

# Fronteras de la funcion por tramos, en keV/um de LET no restringida en agua.
ICRP60_LOW_LET = 10.0
ICRP60_HIGH_LET = 100.0


def icrp60_quality_factor(let_kev_per_um: float) -> float:
    """Factor de calidad Q(L) segun ICRP 60.

        Q = 1                 si L < 10 keV/um
        Q = 0.32 L - 2.2      si 10 <= L <= 100 keV/um
        Q = 300 / sqrt(L)     si L > 100 keV/um

    Disponible para cuando exista espectro de particulas. Hoy ninguna fuente del
    proyecto lo proporciona, pero la funcion esta implementada y probada para que
    conectarla sea trivial.
    """
    if let_kev_per_um < 0:
        raise ValueError(f"LET negativa: {let_kev_per_um}")
    if let_kev_per_um < ICRP60_LOW_LET:
        return 1.0
    if let_kev_per_um <= ICRP60_HIGH_LET:
        return 0.32 * let_kev_per_um - 2.2
    return 300.0 / math.sqrt(let_kev_per_um)


# --------------------------------------------------------------------------- #
# Factores de calidad medios, medidos en vuelo
# --------------------------------------------------------------------------- #


class QualityFactorModel(StrEnum):
    """De donde sale el factor de calidad aplicado."""

    MEASURED = "measured"
    MISSION_AVERAGE = "mission-average"
    TRAPPED = "trapped-radiation"
    GALACTIC_COSMIC = "galactic-cosmic"
    UNIT = "unit"


@dataclass(frozen=True, slots=True)
class MeanQualityFactor:
    value: float
    uncertainty: float | None
    source: str
    # La ficha del registro de evidencia que respalda el valor (`data/evidence_refs.json`).
    ref_id: str | None = None


# Valores medidos en vuelo con TEPC (Spacelab SLS-1). Son los que se aplican
# cuando no hay dosis equivalente medida. Su fuente tiene ficha desde la decimocuarta
# ronda (C7): `badhwar-1992-sls1-tepc` en `data/evidence_refs.json`, leida en PubMed el
# 2026-10-21 (STS-40, 1991: 1,83 +/- 0,1 atrapada, 2,74 +/- 0,1 GCR, 2,38 el vuelo).
# Cada factor la nombra en `ref_id`, y `analysis/radiation.py` la cita por ahi; la cadena de
# `source` se deja como estaba.
MEAN_QUALITY_FACTORS: dict[QualityFactorModel, MeanQualityFactor] = {
    QualityFactorModel.MISSION_AVERAGE: MeanQualityFactor(
        2.38, None, "Factor de calidad global de misión medido con TEPC (Spacelab SLS-1)",
        "badhwar-1992-sls1-tepc",
    ),
    QualityFactorModel.TRAPPED: MeanQualityFactor(
        1.83, 0.1, "Radiación atrapada, medida con TEPC (Spacelab SLS-1)",
        "badhwar-1992-sls1-tepc",
    ),
    QualityFactorModel.GALACTIC_COSMIC: MeanQualityFactor(
        2.74, 0.1, "Rayos cósmicos galácticos, medidos con TEPC (Spacelab SLS-1)",
        "badhwar-1992-sls1-tepc",
    ),
    QualityFactorModel.UNIT: MeanQualityFactor(
        1.0, None, "Q = 1. Solo para comparación: subestima la dosis equivalente real"
    ),
}

DEFAULT_MODEL = QualityFactorModel.MISSION_AVERAGE

# De dónde sale una dosis equivalente que trae el instrumento (`effective_dose`).
MEASURED_SOURCE = "dose_equivalent_rate del instrumento"
i18n.en_many({
    MEAN_QUALITY_FACTORS[QualityFactorModel.MISSION_AVERAGE].source: (
        "Whole-mission quality factor measured with a TEPC (Spacelab SLS-1)"
    ),
    MEAN_QUALITY_FACTORS[QualityFactorModel.TRAPPED].source: (
        "Trapped radiation, measured with a TEPC (Spacelab SLS-1)"
    ),
    MEAN_QUALITY_FACTORS[QualityFactorModel.GALACTIC_COSMIC].source: (
        "Galactic cosmic rays, measured with a TEPC (Spacelab SLS-1)"
    ),
    MEAN_QUALITY_FACTORS[QualityFactorModel.UNIT].source: (
        "Q = 1. For comparison only: it underestimates the actual dose equivalent"
    ),
    MEASURED_SOURCE: "dose_equivalent_rate from the instrument",
})


@dataclass(frozen=True, slots=True)
class DoseEstimate:
    """Una dosis acumulada, con su procedencia declarada.

    Nunca se devuelve un numero de dosis pelado: quien lo lea tiene que poder
    distinguir una medida de una estimacion, y con que factor se estimo.
    """

    value_msv: float
    model: QualityFactorModel
    # `None` con la dosis equivalente medida: no se aplicó ningún Q. Antes era NaN, y un NaN no
    # cabe en JSON: `/api/radiation/dose` caía con un 500 justo en el caso preferente (Lógica 1).
    quality_factor: float | None
    samples: int
    hours_covered: float
    source_note: str

    @property
    def is_measured(self) -> bool:
        return self.model is QualityFactorModel.MEASURED

    @property
    def per_day_msv(self) -> float:
        if self.hours_covered <= 0:
            return 0.0
        return self.value_msv * 24.0 / self.hours_covered

    def describe(self) -> str:
        if self.is_measured or self.quality_factor is None:
            return i18n.tr(
                f"{display.number(self.value_msv, 3)} mSv (dosis equivalente medida)",
                f"{display.number(self.value_msv, 3)} mSv (measured dose equivalent)",
            )
        return i18n.tr(
            f"{display.number(self.value_msv, 3)} mSv (estimada: dosis absorbida x Q = "
            f"{display.number(self.quality_factor, 2)})",
            f"{display.number(self.value_msv, 3)} mSv (estimated: absorbed dose x Q = "
            f"{display.number(self.quality_factor, 2)})",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "value_msv": round(self.value_msv, 6),
            "per_day_msv": round(self.per_day_msv, 6),
            "measured": self.is_measured,
            # Etiqueta comun de toda cifra (especificacion §2): con Q medio es inferida.
            "observation_type": "measured" if self.is_measured else "inferred",
            "model": str(self.model),
            "quality_factor": self.quality_factor,
            "samples": self.samples,
            "hours_covered": round(self.hours_covered, 3),
            "source": i18n.loc(self.source_note),
            "description": self.describe(),
        }


def _trapezoidal_ugy(samples: Sequence[Any], attribute: str) -> tuple[float, float]:
    """Integra una serie de tasa por regla del trapecio.

    Devuelve (total en unidades de tasa x hora, horas cubiertas). Se integra
    sobre los intervalos reales entre muestras, no asumiendo cadencia fija:
    RadLab tiene huecos de instrumento.
    """
    usable = [s for s in samples if getattr(s, attribute, None) is not None]
    if len(usable) < 2:
        return 0.0, 0.0

    ordered = sorted(usable, key=lambda s: s.timestamp)
    total = 0.0
    hours = 0.0

    for earlier, later in zip(ordered, ordered[1:], strict=False):
        span = (later.timestamp - earlier.timestamp).total_seconds() / 3600.0
        if span <= 0:
            continue
        mean_rate = (
            getattr(earlier, attribute) + getattr(later, attribute)
        ) / 2.0
        total += mean_rate * span
        hours += span

    return total, hours


def effective_dose(
    samples: Sequence[Any],
    model: QualityFactorModel = DEFAULT_MODEL,
) -> DoseEstimate:
    """Dosis acumulada en mSv a partir de una serie de dosimetria.

    Prefiere la dosis equivalente medida si la serie la trae. Si no, integra la
    dosis absorbida y aplica el factor de calidad medio del modelo indicado.
    """
    # Camino preferente: dosis equivalente medida (uSv/h -> mSv).
    measured_usv, measured_hours = _trapezoidal_ugy(samples, "dose_equivalent_rate")
    if measured_usv > 0:
        return DoseEstimate(
            value_msv=measured_usv / 1000.0,
            model=QualityFactorModel.MEASURED,
            quality_factor=None,
            samples=len(samples),
            hours_covered=measured_hours,
            source_note=MEASURED_SOURCE,
        )

    # Respaldo: dosis absorbida (uGy/h -> mGy) por el factor de calidad.
    absorbed_ugy, hours = _trapezoidal_ugy(samples, "absorbed_dose_rate")
    factor = MEAN_QUALITY_FACTORS[model]

    return DoseEstimate(
        value_msv=(absorbed_ugy / 1000.0) * factor.value,
        model=model,
        quality_factor=factor.value,
        samples=len(samples),
        hours_covered=hours,
        source_note=factor.source,
    )
