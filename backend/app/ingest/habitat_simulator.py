"""Simulador determinista de la atmosfera de cabina.

Existe para el escenario de la especificacion del equipo (§9) "CO2/fatiga": sin datos de
cabina no hay forma de ensenar que una alteracion simultanea en varios tripulantes apunta al
habitat. No hay telemetria publica de cabina de la ISS a ese nivel; los valores son de diseno y
cada uno lo declara, como los parametros de deriva del simulador fisiologico.

Valores nominales (diseno EMMA, dentro de los limites de NASA-STD-3001 Vol 2):
- ppCO2 2,0 mmHg: por debajo del limite de 3 mmHg [V2 6004]. No se afirma que sea el valor
  tipico de la ISS.
- ppO2 150 mmHg: centro del rango OBJETIVO 145-155 [V2 6003] (no es un limite de salud: los
  de exposicion de la tabla 6.2-1 son 127 en media de 1 h, 122 y 356).
- Presion 101,3 kPa: atmosfera a nivel del mar, dentro de 34,5-103 [V2 6006].
- 22,5 degC y 45 % de humedad: dentro de la zona de rendimiento [V2 6013].
- Ruido 62 dBA, CO 1 ppm, amoniaco 0,3 ppm y formaldehido 0,02 ppm: diseño, muy por debajo de
  [V2 6077] y de los SMAC de JSC 20584 Rev C.
- Luz 300 lx: diseño EMMA SIN FUENTE. No se afirma que sea la de ninguna nave ni que sea
  adecuada: la luz solo se muestra, no tiene limite verificado y no se evalua
  (`environment/habitat.py`, `DISPLAY_ONLY`). Es constante con ruido: no se simula ningun ciclo
  de dia y noche.

Escenario CO2: en los ultimos 3 dias el ppCO2 sube en 12 h hasta 5 mmHg y se queda alli
(diseno: supera el limite con claridad para la demo). El efecto sobre las personas lo pone el
simulador fisiologico (`Scenario.CO2_FATIGUE`), con la evidencia de cada efecto clasificada.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Sequence

import numpy as np

from app.core import i18n
from app.environment.habitat import DEFAULT_MODULE, HabitatReading
from app.ingest.fhir import EvidenceContext

NOMINAL: dict[str, tuple[float, float]] = {
    # parametro: (valor nominal, desviacion tipica del ruido). Diseno EMMA.
    "cabin-ppco2": (2.0, 0.15),
    "cabin-ppo2": (150.0, 1.0),
    "cabin-pressure": (101.3, 0.15),
    "cabin-temperature": (22.5, 0.4),
    "cabin-humidity": (45.0, 2.0),
    # Diseño EMMA, por debajo de su limite con holgura; no se afirma que sean los de la ISS.
    "cabin-noise": (62.0, 2.0),
    "cabin-co": (1.0, 0.2),
    "cabin-ammonia": (0.3, 0.05),
    "cabin-formaldehyde": (0.02, 0.004),
    # Solo se muestra: la norma leida fija niveles por tarea, no un limite general
    # (`environment/habitat.py`). El valor simulado es diseño EMMA sin fuente.
    "cabin-light": (300.0, 15.0),
}
# La luz se anadio despues que los demas. Sale de un generador propio y detras de ellos para que
# la serie de los parametros que SI se evaluan sea, lectura a lectura, la que ya era: meterla en
# el mismo generador habria movido el ruido de todos y, con el, las excursiones (invariante 5).
OWN_STREAM = ("cabin-light",)
OWN_STREAM_SEED_OFFSET = 500
LIGHT_EVIDENCE = (
    "diseño EMMA sin fuente: valor constante con ruido, sin ciclo de día y noche; la luz solo "
    "se muestra y no se evalúa: la norma leída fija niveles por tarea, no un límite general"
)
i18n.en(
    LIGHT_EVIDENCE,
    "EMMA design without a source: constant value with noise, with no day and night cycle; the "
    "light is only shown and not evaluated: the standard read sets levels per task, not a "
    "general limit",
)

CO2_EXCURSION_MMHG = 5.0
CO2_ONSET_DAYS_BEFORE_END = 3.0
CO2_RAMP_HOURS = 12.0

# Modulos (especificacion §3, "module/location"). Clasificacion del respaldo, como pide CLAUDE.md
# para todo parametro del simulador: ninguna de las tres clases bibliograficas aplica. Que la
# excursion ocurra en un solo modulo y los demas sigan nominales es un SUPUESTO DE DISENO SIN
# RESPALDO BIBLIOGRAFICO: no se modela el intercambio de aire entre modulos ni se cita nada.
# Sirve para ensenar que la correlacion distingue donde estaba cada persona, y nada mas.
MODULES_EVIDENCE = (
    "supuesto de diseño sin respaldo bibliográfico: la excursión ocurre en un solo módulo y "
    "los demás se simulan nominales e independientes; no se modela la mezcla de aire entre "
    "módulos"
)
i18n.en(
    MODULES_EVIDENCE,
    "design assumption without bibliographic support: the excursion happens in a single module "
    "and the others are simulated nominal and independent; the mixing of air between modules "
    "is not modelled",
)
EXTRA_MODULE_SEED_STEP = 1009


def co2_ramp(mission_day: float, total_days: int) -> float:
    """Fraccion 0..1 de la excursion de CO2 en un dia de mision. Compartida con el fisiologico."""
    onset = total_days - CO2_ONSET_DAYS_BEFORE_END
    elapsed_hours = (mission_day - onset) * 24.0
    if elapsed_hours <= 0:
        return 0.0
    return min(1.0, elapsed_hours / CO2_RAMP_HOURS)


class HabitatSimulator:
    def __init__(
        self,
        co2_excursion: bool,
        seed: int = 20261114,
        mission_start: dt.date = dt.date(2026, 11, 1),
        module: str = DEFAULT_MODULE,
        extra_modules: Sequence[str] = (),
    ) -> None:
        self.co2_excursion = co2_excursion
        self.seed = seed
        self.mission_start = mission_start
        # `module` es donde ocurre la excursion; `extra_modules` se quedan siempre nominales.
        self.module = module
        self.extra_modules = tuple(extra_modules)
        if module in self.extra_modules or len(set(self.extra_modules)) != len(
            self.extra_modules
        ):
            raise ValueError("un módulo no puede simularse dos veces")

    @property
    def source(self) -> str:
        return "simulator:habitat-co2" if self.co2_excursion else "simulator:habitat"

    def generate(self, days: int, samples_per_day: int = 24) -> Iterator[HabitatReading]:
        modules = (self.module, *self.extra_modules)
        # Un generador por modulo: anadir modulos no cambia la serie del primero, que es la
        # que ya estaba firmada en demos y pruebas con una sola cabina.
        rngs = [
            np.random.default_rng(self.seed + 7 + EXTRA_MODULE_SEED_STEP * index)
            for index in range(len(modules))
        ]
        own_rngs = [
            np.random.default_rng(
                self.seed + 7 + EXTRA_MODULE_SEED_STEP * index + OWN_STREAM_SEED_OFFSET
            )
            for index in range(len(modules))
        ]
        shared = [key for key in sorted(NOMINAL) if key not in OWN_STREAM]
        own_keys = [key for key in OWN_STREAM if key in NOMINAL]
        start = dt.datetime.combine(self.mission_start, dt.time(0, 0, tzinfo=dt.UTC))
        interval = dt.timedelta(hours=24 / samples_per_day)
        for step in range(days * samples_per_day):
            moment = start + interval * step
            mission_day = step / samples_per_day
            for module, rng, own in zip(modules, rngs, own_rngs, strict=True):
                for key in (*shared, *own_keys):
                    nominal, noise = NOMINAL[key]
                    source = own if key in OWN_STREAM else rng
                    value = nominal + float(source.normal(0.0, noise))
                    if key == "cabin-ppco2" and self.co2_excursion and module == self.module:
                        value += (CO2_EXCURSION_MMHG - nominal) * co2_ramp(mission_day, days)
                    yield HabitatReading(
                        module=module, parameter=key, value=round(max(value, 0.0), 3),
                        effective=moment, source=self.source,
                        evidence_context=EvidenceContext.SIMULATED,
                    )

    def describe(self) -> dict[str, object]:
        # Solo se sirve (respuesta de `POST /api/simulate`); no se firma: lo firmado son las
        # lecturas, que no llevan texto. El ingles dice lo mismo: diseño, sin respaldo, no real.
        return {
            "module": self.module,
            "extra_modules": list(self.extra_modules),
            "modules_basis": i18n.loc(MODULES_EVIDENCE),
            "seed": self.seed,
            "co2_excursion": self.co2_excursion,
            "basis": i18n.tr(
                "valores de diseño dentro de NASA-STD-3001 Vol 2; no es telemetría real",
                "design values within NASA-STD-3001 Vol 2; it is not real telemetry",
            ),
            "display_only": {
                key: i18n.loc(LIGHT_EVIDENCE) for key in OWN_STREAM if key in NOMINAL
            },
        }
