"""La puerta de la línea base consciente de la fase del ciclo (lote «ciclo», unidad B3).

POR QUÉ VIVE EN `api/` Y NO EN `analysis/`
------------------------------------------
Para saber si una tripulante tiene un ciclo cuya fase ajustar hace falta su sexo declarado
(`crew-sex`, que solo lee `api/`: `test_no_rule_of_emma_reads_sex_or_age`) y su estado
reproductivo declarado. El motor (`analysis/cycle_phase.py`) recibe solo los inicios de regla y
devuelve un desplazamiento por clave e instante; nunca ve el sexo.

LA PUERTA: LAS TRES COSAS, O NADA
---------------------------------
El ajuste solo se aplica si se cumplen las tres:

1. El último sexo declarado vigente (no redactado y, para Tierra, dentro de su corte `until`) es
   `female`.
2. El último `reproductive-status` declarado es exactamente `REGULAR_CYCLE_STATUS` (1, «ciclo
   menstrual regular»). La ingesta acepta no enteros: se compara con 1, no se redondea. La
   supresión menstrual o la anticoncepción continua (3, lo habitual en misiones largas), la
   perimenopausia (4) o la posmenopausia (5) cierran la puerta: en ellas no hay una fase que
   situar con inicios de regla, y descontar una subida lútea taparía lo que no es ciclo.
3. Hay inicios de regla (`menstruation-start` = 1) suficientes para situar la fase
   (`cycle_phase.MIN_STARTS`).

Si falta cualquiera, el motor recibe `None` —exactamente el de siempre— y la respuesta dice cuál
falta, con una frase fija que la consola enseña tal cual. Con la puerta abierta, el ajuste se
aplica a toda la historia evaluada con la fase que cada instante tenía en directo (causal); si la
puerta se cierra después (otra declaración), se deja de aplicar también a lo pasado.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.analysis import cycle_phase
from app.analysis.cycle_phase import CyclePhaseModel, PhaseOffset
from app.core import display, i18n
from app.core.storage import TamperedRecordError
from app.ingest.codes import MENSTRUATION_START, REGULAR_CYCLE_STATUS, REPRODUCTIVE_STATUS, get
from app.ingest.fhir import VitalObservation

# El valor de `crew-sex` que abre la puerta.
FEMALE = "female"

# Frases fijas: la consola (`frontend/src/cycle/CyclePanel.tsx`, prop `phaseBaseline`) las
# enseña tal cual, sin redactar nada.
CLOSED = "Sin ajuste de la línea base por fase del ciclo: "
NO_DECLARED = CLOSED + "no hay sexo declarado."
NOT_FEMALE = CLOSED + "el sexo declarado no es femenino."
NO_STATUS = CLOSED + "no hay estado reproductivo declarado."
NOT_REGULAR = (
    CLOSED + "el último estado reproductivo declarado no es «ciclo menstrual regular» "
    "(supresión menstrual, perimenopausia, posmenopausia u otro): no hay fase que situar."
)
# Un asiento de sexo mal formado no tumba el estado (sí `GET /api/crew/sex`, con su 409): cierra
# la puerta y lo dice.
MALFORMED = CLOSED + "el asiento del sexo declarado está mal formado."
OPEN = "Línea base ajustada por fase del ciclo"
# Las claves sin cifra leída, por su nombre en el catálogo: si lo leído cambia, la frase cambia.
UNADJUSTED = (
    "La "
    + " y la ".join(
        get(key).display_es[:1].lower() + get(key).display_es[1:]
        for key in cycle_phase.UNADJUSTED_KEYS
    )
    + " no se ajustan: lo leído dice cómo cambian en la fase lútea, pero no cuánto."
)

# El inglés de las frases fijas (`core/i18n.py`). Se resuelve donde se sirven: `_closed` y `gate`.
_CLOSED_EN = "No baseline adjustment for cycle phase: "
i18n.en_many({
    NO_DECLARED: _CLOSED_EN + "there is no declared sex.",
    NOT_FEMALE: _CLOSED_EN + "the declared sex is not female.",
    NO_STATUS: _CLOSED_EN + "there is no declared reproductive status.",
    NOT_REGULAR: (
        _CLOSED_EN + "the latest declared reproductive status is not “regular menstrual cycle” "
        "(menstrual suppression, perimenopause, postmenopause or other): there is no phase to "
        "place."
    ),
    MALFORMED: _CLOSED_EN + "the declared-sex entry is malformed.",
    OPEN: "Baseline adjusted for cycle phase",
})


def _unadjusted() -> str:
    """`UNADJUSTED` en el idioma de la petición.

    La constante se compone al importar, con los nombres en castellano; en inglés la frase se
    compone aquí, con los nombres del catálogo, porque su orden es otro.
    """
    if i18n.current() != "en":
        return UNADJUSTED
    # Los nombres del catálogo tal cual: no se les cambia la caja (hay siglas y nombres de LOINC).
    names = [get(key).display_es for key in cycle_phase.UNADJUSTED_KEYS]
    listed = " and ".join(names)
    verb = "is" if len(names) == 1 else "are"
    return (
        f"{listed} {verb} not adjusted: what was read says how they change in the luteal phase, "
        f"but not by how much."
    )


@dataclass(frozen=True, slots=True)
class CycleGate:
    """Lo que la puerta decidió: el desplazamiento para el motor y lo que se enseña.

    `applied` dice si el motor recibió el desplazamiento (la puerta está abierta), aunque hoy no
    se sitúe la fase: lo pasado que cayó en fase lútea se juzgó ajustado, y eso no se calla.
    `phase` es la de hoy, o `None` si hoy no se sitúa.
    """

    offset: PhaseOffset | None
    applied: bool
    phase: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"applied": self.applied, "phase": self.phase, "reason": self.reason}


def _closed(reason: str) -> CycleGate:
    # `reason` es una de las frases fijas de arriba: aquí, donde se sirve, va al idioma pedido.
    return CycleGate(offset=None, applied=False, phase=None, reason=i18n.loc(reason))


def _latest_value(observations: Sequence[VitalObservation], key: str) -> float | None:
    found = [item for item in observations if item.key == key]
    if not found:
        return None
    return max(found, key=lambda item: item.effective).value


def _discounted(model: CyclePhaseModel, now: dt.datetime) -> str:
    """Lo que se descuenta hoy, por clave, con su unidad.

    Con dos decimales y no los de la lectura: 0,23 °C y 3,42 lpm, las cifras leídas, se leerían
    «0,2 °C» y «3 /min», que no son lo que se descuenta.
    """
    parts = []
    for key in cycle_phase.LUTEAL_OFFSETS:
        code = get(key)
        amount = f"{display.number(model.luteal_rise(key, now), 2)} {display.unit(code.unit)}"
        name = code.display_es.lower()
        parts.append(i18n.tr(f"{amount} de {name}", f"{amount} of {name}"))
    return ", ".join(parts)


def gate(
    store: Any,
    subject: str,
    until: dt.datetime | None,
    stored: Sequence[VitalObservation],
    analysed: Sequence[VitalObservation],
    now: dt.datetime,
    decides: Callable[[VitalObservation], bool],
) -> CycleGate:
    """La puerta del ajuste por fase para `subject` en `now`, con lo que Tierra tiene en `until`.

    `stored` son todas las lecturas hasta el corte (también las descriptivas, de donde salen el
    estado reproductivo y los inicios); `analysed`, las que juzga el motor, de las que sale la
    subida lútea propia de los ciclos ya cerrados. `decides` es la regla del estado sobre el tipo
    de lectura (`routes.is_analysed_type`): un inicio o un estado inferido o predicho no abre la
    puerta, ni uno de baja confianza.
    """
    # Importado aquí: `mission` importa `routes`, y `routes` importa este módulo.
    from app.api.mission import latest_crew_sex

    try:
        declared = latest_crew_sex(store, subject, until)
    except TamperedRecordError:
        return _closed(MALFORMED)
    if declared is None:
        return _closed(NO_DECLARED)
    if declared["sex"] != FEMALE:
        return _closed(NOT_FEMALE)
    declared_readings = [
        item for item in stored if decides(item) and not item.is_low_confidence
    ]
    status = _latest_value(declared_readings, REPRODUCTIVE_STATUS.key)
    if status is None:
        return _closed(NO_STATUS)
    if status != REGULAR_CYCLE_STATUS:
        return _closed(NOT_REGULAR)
    starts = [
        item.effective for item in declared_readings
        if item.key == MENSTRUATION_START.key and item.value == cycle_phase.START_MARK
    ]
    model = CyclePhaseModel.from_starts(starts, analysed)
    found = model.phase_at(now)
    if found.reason == "too_few_starts":
        # Con menos inicios hasta hoy, también los hubo en todo lo anterior: nada se ajusta.
        return _closed(i18n.tr(
            CLOSED + cycle_phase.REASONS["too_few_starts"] + ".",
            _CLOSED_EN + i18n.loc(cycle_phase.REASONS["too_few_starts"]) + ".",
        ))
    opened = i18n.loc(OPEN)
    if found.phase is None:
        # La puerta está abierta y lo pasado que cayó en fase lútea se ajusta; hoy, no.
        reason = i18n.tr(
            f"{OPEN} en los días lúteos ya pasados; hoy no se sitúa la fase: "
            f"{cycle_phase.REASONS[found.reason]}. {UNADJUSTED}",
            f"{opened} on the luteal days already past; today the phase is not placed: "
            f"{i18n.loc(cycle_phase.REASONS[found.reason])}. {_unadjusted()}",
        )
    elif found.phase == cycle_phase.ADJUSTED_PHASE:
        reason = i18n.tr(
            f"{OPEN}: fase lútea; se descuenta lo que la fase sube "
            f"({_discounted(model, now)}). {UNADJUSTED}",
            f"{opened}: luteal phase; what the phase raises is discounted "
            f"({_discounted(model, now)}). {_unadjusted()}",
        )
    else:
        reason = i18n.tr(
            f"{OPEN}: fase folicular, la referencia; hoy no se descuenta nada. {UNADJUSTED}",
            f"{opened}: follicular phase, the reference; nothing is discounted today. "
            f"{_unadjusted()}",
        )
    return CycleGate(offset=model.offset, applied=True, phase=found.phase, reason=reason)
