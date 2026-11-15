"""Un cambio de turno o de horario de sueño, declarado como evento de misión firmado.

Por qué existe: la conversación de ideación (`docs/contexto/conversacion-ideacion-v1.md`) pide
«carga de trabajo, turnos y eventos críticos» y el «ciclo día/noche» entre lo que el sistema tiene
que saber de la misión. EMMA tenía EVA, bloques de trabajo y ubicación (`mission-event`), y nada
que dijera que el horario de dormir se había movido. Decisión del usuario (2026-10-26): el turno
entra como cuarto tipo del mismo asiento, `shift`, y como una fuente más del contexto de una
alerta. Este módulo dice qué es, en qué se distingue de un bloque de trabajo y qué dice la fuente.

UN TURNO NO ES UN BLOQUE DE TRABAJO
-----------------------------------
- Un **bloque de trabajo** (`workload`) es el intervalo en que se trabajó: dice cuándo hubo
  actividad, y nada del horario de sueño.
- Un **cambio de turno** (`shift`) es el intervalo en que el horario de sueño y vigilia impuesto
  queda desplazado respecto al habitual: dormir horas antes o después para estar despierto cuando
  toca un atraque, o pasar a otro turno. Puede no llevar ni una hora más de trabajo.

Son dos cosas que pasan por separado: un turno doble sin mover la hora de dormir es un bloque de
trabajo; dormir seis horas antes para un atraque es un cambio de turno aunque ese día no se trabaje
más. Si pasan las dos, se declaran las dos.

LO QUE DICE LA FUENTE, Y LO QUE NO
----------------------------------
Flynn-Evans 2016 (npj Microgravity; actigrafía de 21 astronautas en la ISS), en su introducción:
«ISS astronauts are often required to “slam-shift,” whereby they suddenly are required to sleep at
a time many hours before or after their nominal bedtime in order to have scheduled wakefulness
coincide with mission events», y «These abrupt shifts in the imposed sleep–wake schedule can
induce circadian misalignment». En sus resultados, los sueños desalineados en vuelo duraron menos
que los alineados (5,4 ± 1,4 h frente a 6,4 ± 1,2 h).

Lo que no dice: el estudio no clasifica sus sueños por si hubo cambio de turno (los clasifica por
si el mínimo de temperatura estimado cae dentro del sueño); no da cuántas horas de desplazamiento
cuentan ni cuánto dura el efecto tras un cambio. Por eso aquí no hay umbral de horas ni ventana
propia: se usa la del contexto (`analysis/alert_context.py`, diseño EMMA), y el turno no entra en
el riesgo ni en `rules_version`. Es texto que coincide en el tiempo con una alerta, no su causa.

Lo leído, con fecha, está en la ficha `flynn-evans-2016-circadian-iss` de `data/evidence_refs.json`.
"""

from __future__ import annotations

from typing import Any

from app.core import i18n
from app.core.storage import SHIFT_EVENT_KIND
from app.evidence import registry

KIND = SHIFT_EVENT_KIND
DISPLAY = "Cambio de turno o de horario de sueño"
SOURCE_REF = "flynn-evans-2016-circadian-iss"

DISTINCTION = (
    "Un cambio de turno es el intervalo en que el horario de sueño y vigilia queda desplazado "
    "respecto al habitual (dormir horas antes o después, o pasar a otro turno). Un bloque de "
    "trabajo es el intervalo en que se trabajó y no dice nada del horario de sueño. Si pasan las "
    "dos cosas, se declaran las dos."
)
SOURCE_SAYS = (
    "Flynn-Evans 2016 (npj Microgravity, 21 astronautas en la ISS) dice en su introducción que "
    "los cambios bruscos del horario de sueño impuesto pueden desalinear el ritmo circadiano "
    "(«These abrupt shifts in the imposed sleep–wake schedule can induce circadian "
    "misalignment»). No clasifica sus sueños por si hubo cambio de turno ni dice cuánto dura el "
    "efecto tras un cambio: en el contexto de una alerta solo se lista si coincide en el tiempo."
)
# Se resuelve al pedirla (`describe`), no al importar: el contexto de las alertas y la crónica
# importan este módulo, y una ficha que falte tiene que tumbar esta ruta, no el arranque.
RELEVANCE = (
    "Introducción: en la ISS se pide a menudo dormir muchas horas antes o después de la hora "
    "habitual para estar despierto en los eventos de misión («slam-shift»), y esos cambios "
    "bruscos del horario impuesto pueden desalinear el ritmo circadiano"
)
i18n.en(DISPLAY, "Shift or sleep schedule change")
i18n.en(
    DISTINCTION,
    "A shift change is the interval in which the sleep and wake schedule is displaced from the "
    "usual one (sleeping hours earlier or later, or moving to another shift). A work block is "
    "the interval in which work was done and says nothing about the sleep schedule. If both "
    "happen, both are declared.",
)
i18n.en(
    SOURCE_SAYS,
    "Flynn-Evans 2016 (npj Microgravity, 21 astronauts on the ISS) says in its introduction "
    "that abrupt changes of the imposed sleep schedule can misalign the circadian rhythm "
    "(«These abrupt shifts in the imposed sleep–wake schedule can induce circadian "
    "misalignment»). It does not classify its sleep episodes by whether there was a shift "
    "change, nor does it say how long the effect lasts after a change: in the context of an "
    "alert it is only listed if it coincides in time.",
)
i18n.en(
    RELEVANCE,
    "Introduction: on the ISS crew are often asked to sleep many hours before or after the "
    "usual time in order to be awake for mission events («slam-shift»), and those abrupt "
    "changes of the imposed schedule can misalign the circadian rhythm",
)


def describe() -> dict[str, Any]:
    """Qué es un cambio de turno, en qué se distingue de un bloque de trabajo y su fuente."""
    return {
        "kind": KIND,
        "display": i18n.loc(DISPLAY),
        "distinction": i18n.loc(DISTINCTION),
        "source_says": i18n.loc(SOURCE_SAYS),
        "source": registry.cite(SOURCE_REF, i18n.loc(RELEVANCE)).to_dict(),
    }
