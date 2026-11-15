"""Deterioros conocidos inyectados sobre fisiologia humana real.

EL PROBLEMA QUE RESUELVE
------------------------
MMASH da especificidad: 22 personas sanas, asi que toda alerta es falsa. Pero no
da **sensibilidad**: como nadie se deteriora, no dice nada sobre si EMMA
detectaria un deterioro real.

Sin ese segundo eje, cualquier cambio que reduzca la tasa de falsa alarma es
indistinguible de volver sordo al sistema. Se puede llegar al 0 % de falsas
alarmas apagando las alertas.

COMO FUNCIONA
-------------
Se toma la serie real de un sujeto y se le aplica una perturbacion **de magnitud
conocida** a partir de un instante conocido. La fisiologia de base sigue siendo
humana y real —con su variabilidad circadiana, sus artefactos y sus colas
pesadas—; lo unico sintetico es el deterioro.

Eso permite medir las dos cosas sobre el mismo sustrato:

    especificidad  = 1 - (alarmas sobre el tramo sano)
    sensibilidad   = fraccion de deterioros inyectados que se detectan

QUE SIGUE SIN VALIDAR
---------------------
Que las perturbaciones se parezcan a un deterioro clinico real. Son derivas y
eventos agudos parametricos, no casos documentados. Miden si el motor **reacciona
ante un cambio de magnitud dada**, no si ese cambio es el que produce una sepsis.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from app.ingest.fhir import VitalObservation
from app.ingest.simulator import MenstrualCycle


class Perturbation(StrEnum):
    """Forma temporal del deterioro inyectado."""

    DRIFT = "drift"
    ACUTE = "acute"
    STEP = "step"
    # No es un deterioro: es el vaiven del ciclo menstrual (escalón lúteo suavizado, la forma de
    # `simulator.luteal_level`). Sirve para medir si el motor lo confunde con uno, y por eso no
    # está en `REFERENCE_INJECTIONS`: allí rotularía como sensibilidad lo que es una molestia.
    CYCLE = "cycle"


# La forma temporal de cada perturbación, con la palabra con que se enseña (`risk_entity.py`).
PERTURBATION_DISPLAY: dict[Perturbation, str] = {
    Perturbation.DRIFT: "deriva progresiva",
    Perturbation.ACUTE: "episodio agudo",
    Perturbation.STEP: "escalón sostenido",
    Perturbation.CYCLE: "variación cíclica",
}

# Lo que mide la sensibilidad por inyección y lo que no (el bloque «QUE SIGUE SIN VALIDAR» de
# arriba), en una frase para quien lee la matriz de riesgos.
MEASURES = (
    "Mide si el motor reacciona ante un cambio de magnitud conocida sobre fisiología real en "
    "Tierra, no si ese cambio es el de un deterioro clínico de vuelo."
)


@dataclass(frozen=True, slots=True)
class Injection:
    """Un deterioro de magnitud y momento conocidos."""

    key: str
    kind: Perturbation
    magnitude: float
    onset: dt.datetime
    # Solo para ACUTE: cuanto dura el episodio.
    duration: dt.timedelta = dt.timedelta(hours=2)
    # Solo para CYCLE: la forma del ciclo (periodo, fase lútea, rampas, y en qué día del ciclo cae
    # `onset`, 0 = primer día de la regla). La amplitud es `magnitude`, la meseta lútea frente a la
    # folicular; las `amplitudes` del ciclo no se leen aquí (las reparte `cyclic`).
    cycle: MenstrualCycle | None = None

    def applies_to(self, observation: VitalObservation) -> bool:
        if observation.key != self.key or observation.effective < self.onset:
            return False
        if self.kind is Perturbation.ACUTE:
            return observation.effective <= self.onset + self.duration
        return True

    def offset_at(self, moment: dt.datetime) -> float:
        """Cuanto se desplaza el valor en ese instante."""
        elapsed = moment - self.onset
        if elapsed < dt.timedelta(0):
            return 0.0

        if self.kind is Perturbation.STEP:
            return self.magnitude

        if self.kind is Perturbation.ACUTE:
            if elapsed > self.duration:
                return 0.0
            # Subida rapida y meseta durante el episodio.
            ramp = min(1.0, elapsed / (self.duration / 4)) if self.duration else 1.0
            return self.magnitude * ramp

        if self.kind is Perturbation.CYCLE:
            # La forma temporal es la del simulador (`level_at`), no una segunda copia. La amplitud
            # es `magnitude`, no la del ciclo: el ciclo da solo la forma, y `cyclic` es quien las
            # hace coincidir. Una diferencia, a sabiendas: el simulador suma la amplitud antes de
            # su ritmo circadiano (el pulso de sueño sube un 0,765 de lo que sube el de reposo);
            # aquí se suma entera a cada lectura, porque la serie real ya trae su ritmo y no hay
            # un factor medido que aplicarle. En la temperatura, sin ritmo modelado, coinciden.
            cycle = self.cycle or MenstrualCycle()
            return self.magnitude * cycle.level_at(elapsed.total_seconds() / 86400.0)

        # DRIFT: progresivo, `magnitude` es el desplazamiento **por dia**.
        return self.magnitude * (elapsed.total_seconds() / 86400.0)


@dataclass
class InjectedSeries:
    """Serie con deterioro, mas la verdad de que se toco."""

    observations: list[VitalObservation]
    injection: Injection
    perturbed: int = 0
    # Lecturas que chocaron con el limite fisico. Si son muchas, el deterioro
    # inyectado ya no es el que dice la etiqueta.
    clamped: int = 0

    @property
    def clean(self) -> list[VitalObservation]:
        return [o for o in self.observations if not self.injection.applies_to(o)]

    @property
    def affected(self) -> list[VitalObservation]:
        return [o for o in self.observations if self.injection.applies_to(o)]


def inject(
    observations: Sequence[VitalObservation], injection: Injection
) -> InjectedSeries:
    """Aplica un deterioro conocido a una serie real.

    UN DETERIORO INYECTADO SIGUE SIENDO FISIOLOGIA.
    ----------------------------------------------
    Un desplazamiento aditivo fijo puede sacar el valor de lo que un cuerpo puede
    hacer. Medido sobre MMASH: `-30 ms` de SDNN sobre un sujeto cuya SDNN real ya
    era 29,46 ms daba **-0,54 ms**, y una deriva de 15 lpm/dia acumulaba hasta
    370 lpm. Ninguna de las dos cosas existe.

    Eso no es un detalle de implementacion: si la inyeccion fabrica valores
    imposibles, parte de la sensibilidad medida se gano **detectando disparates**,
    no deterioro clinico. El numero publicado quedaria inflado por lecturas que un
    sensor real nunca produce.

    Por eso el valor inyectado se acota al rango fisicamente posible. La medida se
    vuelve mas dura, no mas benevola: el deterioro no puede pasarse de lo que la
    fisiologia permite para hacerse mas facil de ver. Cuantas lecturas se acotaron
    queda contado en `clamped`, porque un deterioro que choca contra el techo en
    masa ya no es el deterioro que dice la etiqueta.
    """
    out: list[VitalObservation] = []
    touched = 0
    clamped = 0

    for obs in observations:
        if injection.applies_to(obs):
            shifted = obs.value + injection.offset_at(obs.effective)
            bounded = obs.code.clamp_to_physical(shifted)
            if bounded != shifted:
                clamped += 1
            out.append(replace(obs, value=round(bounded, 3)))
            touched += 1
        else:
            out.append(obs)

    return InjectedSeries(
        observations=out, injection=injection, perturbed=touched, clamped=clamped
    )


def onset_after(
    observations: Sequence[VitalObservation], fraction: float = 0.6
) -> dt.datetime:
    """Instante a partir del cual inyectar, dejando historial limpio delante.

    Sin historial previo no hay linea base contra la que comparar, asi que el
    deterioro seria indetectable por construccion y la medida de sensibilidad
    diria mas del diseno del experimento que del sistema.
    """
    times = sorted(obs.effective for obs in observations)
    if not times:
        raise ValueError("serie vacía")
    span = times[-1] - times[0]
    return times[0] + span * fraction


def cyclic(onset: dt.datetime, cycle: MenstrualCycle | None = None) -> tuple[Injection, ...]:
    """El ciclo menstrual sobre todas las claves que mueve: una inyección por clave.

    Un ciclo no desplaza un indicador solo (temperatura, pulso y variabilidad a la vez), y una
    `Injection` es de una clave: aquí se reparten, cada una con su amplitud y el mismo ciclo,
    para componerlas con `inject_all`. `onset` es el instante en que el ciclo está en su día
    `start_cycle_day`; antes de él no se desplaza nada, así que se pone en la primera lectura.
    """
    cycle = cycle or MenstrualCycle()
    return tuple(
        Injection(key, Perturbation.CYCLE, amplitude, onset, cycle=cycle)
        for key, amplitude in sorted(cycle.amplitudes.items())
        if amplitude
    )


def inject_all(
    observations: Sequence[VitalObservation], injections: Sequence[Injection]
) -> list[VitalObservation]:
    """Aplica varias perturbaciones una tras otra (p. ej., el ciclo y además un deterioro).

    Se componen sumando: cada una parte de la serie que dejó la anterior, y cada valor se sigue
    acotando a lo físicamente posible en cada paso (`inject`).
    """
    out = list(observations)
    for injection in injections:
        out = inject(out, injection).observations
    return out


# --------------------------------------------------------------------------- #
# Deterioros de referencia
# --------------------------------------------------------------------------- #
#
# Las magnitudes son **clinicamente apreciables**, no marginales: el objetivo es
# medir si el motor ve un cambio que un medico consideraria relevante. Si falla
# con estos, falla con todo.

def tachycardia(onset: dt.datetime) -> Injection:
    """Pulso en reposo +25 lpm de forma sostenida."""
    return Injection("heart-rate", Perturbation.STEP, 25.0, onset)


def progressive_tachycardia(onset: dt.datetime) -> Injection:
    """Pulso subiendo 15 lpm al dia: desacondicionamiento acelerado."""
    return Injection("heart-rate", Perturbation.DRIFT, 15.0, onset)


def acute_episode(onset: dt.datetime) -> Injection:
    """Episodio agudo: +40 lpm durante dos horas."""
    return Injection("heart-rate", Perturbation.ACUTE, 40.0, onset)


def hrv_collapse(onset: dt.datetime) -> Injection:
    """Caida sostenida de 30 ms en SDNN."""
    return Injection("hrv-sdnn", Perturbation.STEP, -30.0, onset)


REFERENCE_INJECTIONS = {
    "taquicardia sostenida (+25 lpm)": tachycardia,
    "taquicardia progresiva (+15 lpm/día)": progressive_tachycardia,
    "episodio agudo (+40 lpm, 2 h)": acute_episode,
    "colapso de HRV (-30 ms SDNN)": hrv_collapse,
}


# --------------------------------------------------------------------------- #
# Sobre qué indicadores se mide la sensibilidad
# --------------------------------------------------------------------------- #
#
# La matriz de riesgos (`risk_entity.py`) decía qué indicadores salen de MMASH, pero no sobre
# cuáles se mide la sensibilidad: las claves vivían dentro de las funciones de arriba. Aquí se leen
# de ellas, construyendo cada deterioro de referencia con un inicio cualquiera: no hay una segunda
# lista que pueda divergir de lo que se inyecta, y añadir un deterioro la cambia sola. El inicio no
# importa: solo se mira la clave y la forma. Qué se inyecta y cómo no cambia.
_TARGET_ONSET = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)


def _target(build: Callable[[dt.datetime], Injection]) -> tuple[str, Perturbation]:
    built = build(_TARGET_ONSET)
    return built.key, built.kind


# Cada deterioro de referencia, por su etiqueta: la clave sobre la que se inyecta y su forma.
REFERENCE_TARGETS: dict[str, tuple[str, Perturbation]] = {
    label: _target(build) for label, build in REFERENCE_INJECTIONS.items()
}

# Las claves de indicador que reciben algún deterioro, en el orden en que aparecen; se derivan de
# la tabla de arriba, que es la que lee la matriz.
INJECTED_KEYS: tuple[str, ...] = tuple(dict.fromkeys(key for key, _ in REFERENCE_TARGETS.values()))
