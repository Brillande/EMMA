"""Conjunción solar: cuándo el Sol se interpone entre la Tierra y Marte, dicho y no decidido.

Por qué existe: el retardo (`environment/ephemeris.py`) dice cuánto tarda una respuesta de
Tierra, pero no si puede llegar. Cada unos 26 meses Marte pasa casi detrás del Sol visto desde la
Tierra, el Sol perturba la radio entre los dos planetas y las misiones de Marte de NASA dejan de
recibir órdenes durante unas dos semanas. Una tripulación en tránsito con ese mismo retardo de
siempre se quedaría además sin enlace. La conversación de ideación lo pide entre las variables de
misión («Comunicación: latencia con Tierra, ventanas de comunicación, pérdida de comunicaciones y
autonomía exigida», `docs/contexto/conversacion-ideacion-v1.md`), y EMMA no lo decía.

Lo que se lee, con sus dos fichas del registro:

- **El ángulo**: la elongación solar que Horizons ya trae en la misma tabla del retardo (la
  cantidad 23 de su manual, «Sun-Observer-Target (apparent solar elongation) angle», en grados).
  No sale nada nuevo a la red: astroquery pedía ya todas las cantidades.
- **El umbral**: los dos grados de la nota de JPL de 2015 («During that period, the sun will be
  within two degrees of Mars in Earth's sky.»), el periodo en que se suspendieron las órdenes.
  Es una cifra de las misiones robóticas de Marte en una conjunción concreta, no una norma de
  enlace ni un dato de misiones tripuladas, y la frase lo dice. Solo vale para Marte: para otro
  objetivo EMMA no tiene umbral leído y no dice si hay conjunción.

Lo que NO hace, y por qué: no entra en el riesgo. `risk.isolation_factor` lee el retardo, no la
elongación, y los niveles, las alertas y las recomendaciones tampoco cambian con ella (prueba en
`tests/test_conjunction.py`). Con más de 10 min de ida y vuelta el sistema ya opera en autonomía;
convertir los dos grados de una pausa de órdenes a robots en un factor clínico sería inventar una
relación que ninguna fuente leída da. Como con las comunicaciones declaradas caídas, solo se dice.
Sin efemérides (`EMMA_OFFLINE=true` sin caché, el modo nominal) se dice «sin efemérides», como el
retardo; con una entrada de caché de antes de leer la elongación, que la entrada no la trae.
"""

from __future__ import annotations

import math
import re
from typing import Any

from app.core import display, i18n
from app.environment.ephemeris import CommsWindow
from app.evidence import registry

LABEL = "Conjunción solar"

NO_EPHEMERIS = "no_ephemeris"
NOT_RECORDED = "not_recorded"
WITHIN = "within"
CLEAR = "clear"
NO_THRESHOLD = "no_threshold"
STATES = (NO_EPHEMERIS, NOT_RECORDED, WITHIN, CLEAR, NO_THRESHOLD)

# El umbral y la frase que lo escribe: la cifra se lee de su frase (`_validate`), en palabras
# como la escribe JPL; un número que no esté en esta tabla no se acepta.
THRESHOLD_DEG = 2.0
_WRITTEN = re.compile(r"within (\w+) degrees")
_WORD_NUMBERS = {"one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0}
# Para qué objetivo vale el umbral leído (código de JPL Horizons -> nombre que se enseña).
THRESHOLD_TARGETS = {"499": "Marte"}

READ_ON = "2026-10-22"
_ANGLE = {
    "ref": "jpl-horizons-manual",
    "section": "Definition of Observer Table Quantities, 23",
    "quote": (
        "Sun-Observer-Target apparent SOLAR ELONGATION ANGLE seen from the observers' location "
        "at print-time."
    ),
    "read_on": READ_ON,
}
_THRESHOLD = {
    "ref": "jpl-2015-mars-conjunction",
    "section": "noticia 2015-190",
    "quote": "During that period, the sun will be within two degrees of Mars in Earth's sky.",
    "read_on": READ_ON,
}
_WHY = {
    "ref": "jpl-2015-mars-conjunction",
    "section": "noticia 2015-190",
    "quote": (
        "The sun disrupts radio communications between the planets during the conjunction "
        "period."
    ),
    "read_on": READ_ON,
}
CITATIONS = (_ANGLE, _THRESHOLD, _WHY)

NOTE = (
    "Solo se dice: el retardo, el factor de aislamiento, los niveles, las alertas y las "
    "recomendaciones no leen la elongación. Los 2° son el periodo de la pausa de órdenes a las "
    "misiones robóticas de Marte de junio de 2015 (JPL), no una norma de enlace ni un dato de "
    "misiones tripuladas; JPL añade restricciones de órdenes los días de antes y de después."
)
i18n.en_many({
    LABEL: "Solar conjunction",
    "Marte": "Mars",
    "noticia 2015-190": "news release 2015-190",
    NOTE: (
        "Stated only: the delay, the isolation factor, the levels, the alerts and the "
        "recommendations do not read the elongation. The 2° are the period of the command "
        "pause for the Mars robotic missions in June 2015 (JPL), not a link standard or a "
        "figure from crewed missions; JPL adds command restrictions on the days before and "
        "after."
    ),
})


def _validate() -> None:
    """La cifra del umbral está en su frase, y cada cita es de una ficha del registro."""
    written = _WRITTEN.search(_THRESHOLD["quote"])
    if written is None or _WORD_NUMBERS.get(written.group(1)) != THRESHOLD_DEG:
        raise ValueError("el umbral de la conjunción no es el que escribe su frase")
    for cite in CITATIONS:
        registry.get(cite["ref"])


_validate()


def cited_refs() -> set[str]:
    """Las fichas del registro que cita la conjunción."""
    return {cite["ref"] for cite in CITATIONS}


def _citation(cite: dict[str, str]) -> dict[str, Any]:
    ref = registry.get(cite["ref"])
    return {**cite, "section": i18n.loc(cite["section"]), "title": ref.title, "url": ref.url}


def _degrees(value: float) -> str:
    return f"{display.number(value, 1)}°"


def _state(window: CommsWindow | None) -> str:
    if window is None:
        return NO_EPHEMERIS
    elongation = window.solar_elongation_deg
    if elongation is None or not math.isfinite(elongation):
        return NOT_RECORDED
    if window.target not in THRESHOLD_TARGETS:
        return NO_THRESHOLD
    return WITHIN if elongation <= THRESHOLD_DEG else CLEAR


def _text_en(state: str, window: CommsWindow | None, target_body: str) -> str:
    """La misma frase de `_text`, en inglés: las mismas ramas, las mismas cifras."""
    code = target_body if window is None else window.target
    known = THRESHOLD_TARGETS.get(code)
    name = i18n.loc(known) if known is not None else f"the target (code {code})"
    if window is None:
        return (
            f"No ephemeris: it is not known how many degrees from the Sun {name} is as seen "
            "from Earth, or whether it is in solar conjunction."
        )
    if state == NOT_RECORDED or window.solar_elongation_deg is None:
        return (
            "The ephemeris for this date does not carry the solar elongation (it was stored "
            "before EMMA read it, or Horizons did not give it): the delay is the one from that "
            f"ephemeris, but it is not known whether {name} is in solar conjunction."
        )
    angle = _degrees(window.solar_elongation_deg)
    threshold = f"{display.number(THRESHOLD_DEG, 0)}°"
    if state == NO_THRESHOLD:
        return (
            f"{name[0].upper()}{name[1:]} is {angle} from the Sun as seen from Earth. EMMA has "
            "only read a conjunction threshold for Mars: for this target it does not say "
            "whether it is in conjunction."
        )
    where = "inside" if state == WITHIN else "outside"
    return (
        f"{name} is {angle} from the Sun as seen from Earth: {where} the {threshold} of the "
        "period in which, at the solar conjunction of June 2015, NASA's Mars missions stopped "
        "receiving commands because the Sun disrupts radio between the planets."
    )


def _text(state: str, window: CommsWindow | None, target_body: str) -> str:
    if i18n.current() == "en":
        return _text_en(state, window, target_body)
    if window is None:
        name = THRESHOLD_TARGETS.get(target_body, f"el objetivo (código {target_body})")
        return (
            f"Sin efemérides: no se sabe a cuántos grados del Sol está {name} visto desde la "
            "Tierra, ni si está en conjunción solar."
        )
    name = THRESHOLD_TARGETS.get(window.target, f"el objetivo (código {window.target})")
    if state == NOT_RECORDED or window.solar_elongation_deg is None:
        return (
            "La efeméride de esta fecha no trae la elongación solar (se guardó antes de que EMMA "
            f"la leyera, o Horizons no la dio): el retardo es el de esa efeméride, pero no se "
            f"sabe si {name} está en conjunción solar."
        )
    angle = _degrees(window.solar_elongation_deg)
    threshold = f"{display.number(THRESHOLD_DEG, 0)}°"
    if state == NO_THRESHOLD:
        return (
            f"{name[0].upper()}{name[1:]} está a {angle} del Sol visto desde la Tierra. EMMA "
            "solo tiene leído un umbral de conjunción para Marte: para este objetivo no dice si "
            "está en conjunción."
        )
    where = "dentro" if state == WITHIN else "fuera"
    return (
        f"{name} está a {angle} del Sol visto desde la Tierra: {where} de los {threshold} del "
        "periodo en que, en la conjunción solar de junio de 2015, las misiones de Marte de NASA "
        "dejaron de recibir órdenes porque el Sol perturba la radio entre los planetas."
    )


def describe(window: CommsWindow | None, target_body: str) -> dict[str, Any]:
    """La conjunción solar del día de las efemérides, para decirla. No decide nada."""
    state = _state(window)
    return {
        "label": i18n.loc(LABEL),
        "state": state,
        "epoch": window.epoch.isoformat() if window is not None else None,
        "target_body": window.target if window is not None else target_body,
        "elongation_deg": window.solar_elongation_deg if window is not None else None,
        "elongation_flag": window.solar_elongation_flag if window is not None else None,
        "threshold_deg": THRESHOLD_DEG if state in (WITHIN, CLEAR) else None,
        "text": _text(state, window, target_body),
        "note": i18n.loc(NOTE),
        "citations": [_citation(cite) for cite in CITATIONS],
    }
