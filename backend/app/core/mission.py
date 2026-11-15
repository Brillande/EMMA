"""Contexto de mision: dia, fase y regimen de gravedad (especificacion del equipo §3, §10).

La especificacion pide un `MissionContext` con fase y dia de mision, y una linea temporal
preflight → dia de mision → intervencion → seguimiento → postflight. Hasta ahora el backend no
sabia en que dia de mision estaba: lo calculaba la interfaz a partir del origen del MET.

SOLO SE EXPONE, NO CAMBIA EL ANALISIS
-------------------------------------
La especificacion (§6) deja para despues las lineas base por fase. Estratificar la base por
fase cambiaria el eje de validacion (invariante 5), asi que aqui la fase se calcula y se
muestra, y el motor no la usa.

LIMITES DE FASE: PARAMETROS DE DISENO, NO CIFRAS CON FUENTE
------------------------------------------------------------
No hay una frontera citable entre "adaptacion" y "fase estable": el sindrome de adaptacion al
espacio se resuelve en dias, pero la adaptacion cardiovascular y osea sigue semanas. Los
limites se declaran como diseno EMMA y se pueden configurar.

EL PERFIL DE MISION VA APARTE
-----------------------------
Que clase de mision es (orbita baja, superficie lunar, transito a Marte) y lo que una fuente
leida dice de ella lo da `app/evidence/mission_profiles.py`, y se anade al contexto como
`profile` donde se compone el estado. `gravity_regime` sigue siendo el texto libre de la
configuracion: el perfil lo acompana, no lo sustituye. Tampoco cambia el analisis.

LA GRAVEDAD DEL MOMENTO Y LA DE LA MISION
-----------------------------------------
Con datos posvuelo, la cabecera decia «posvuelo y recuperacion» junto a «microgravedad»: la
gravedad de configuracion no sigue a la fase, y el tripulante ya esta en Tierra. Decision del
usuario (2026-10-20): en posvuelo se da la gravedad del momento, la de Tierra, y la
configurada se conserva como la gravedad de la mision. Fuera del posvuelo la del momento es la
de la mision. La decision la escribia «en Tierra (1 g)»; aqui dice «en Tierra (gravedad
terrestre)» porque el filtro de lenguaje (`text_guard`, invariante 7) lee «1 g» como una dosis
de un gramo, y todo texto que redacta el sistema lo pasa. Ensanchar el filtro para dejar pasar
«1 g» abriria tambien la dosis: se cambia la frase, no la defensa.

`gravity_regime` sigue siendo la configurada, sin tocar, por compatibilidad; la frase que se
muestra (`gravity_display`) la compone este modulo, no la interfaz. El prevuelo
tambien es en Tierra, pero la decision solo cubre el posvuelo y aqui no se amplia. Solo texto:
nada del analisis lee la gravedad.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any

from app.core import i18n

# Diseno EMMA, sin fuente (ver cabecera).
ADAPTATION_DAYS = 14
RETURN_DAYS = 7


class MissionPhase(StrEnum):
    PREFLIGHT = "preflight"
    ADAPTATION = "adaptation"
    STABLE = "stable"
    RETURN = "return"
    POSTFLIGHT = "postflight"

    @property
    def display(self) -> str:
        return _PHASE_DISPLAY[self]


_PHASE_DISPLAY: dict[MissionPhase, str] = {
    MissionPhase.PREFLIGHT: "prevuelo",
    MissionPhase.ADAPTATION: "adaptación",
    MissionPhase.STABLE: "fase estable",
    MissionPhase.RETURN: "preparación del regreso",
    MissionPhase.POSTFLIGHT: "posvuelo y recuperación",
}
# El inglés va al lado: `display` sigue dando el castellano (lo usan la crónica y las
# pruebas), y quien sirve el nombre lo pasa por `i18n.loc`.
i18n.en_many({
    _PHASE_DISPLAY[MissionPhase.PREFLIGHT]: "preflight",
    _PHASE_DISPLAY[MissionPhase.ADAPTATION]: "adaptation",
    _PHASE_DISPLAY[MissionPhase.STABLE]: "stable phase",
    _PHASE_DISPLAY[MissionPhase.RETURN]: "return preparation",
    _PHASE_DISPLAY[MissionPhase.POSTFLIGHT]: "postflight and recovery",
})


# La gravedad del momento en posvuelo (decision del usuario, 2026-10-20; ver cabecera).
EARTH_GRAVITY = "en Tierra (gravedad terrestre)"
MISSION_GRAVITY_LABEL = "gravedad de la misión, declarada por configuración"
i18n.en(MISSION_GRAVITY_LABEL, "mission gravity, declared by configuration")
# La gravedad configurada es texto libre (`EMMA_GRAVITY_REGIME`): solo tiene inglés el valor
# de fábrica; otro se enseña tal cual se escribió. Va en una tabla propia y no en el registro
# de `i18n.en`: un texto libre no debe encontrar ahí el inglés de la constante de otro módulo.
_GRAVITY_EN = {EARTH_GRAVITY: "on Earth (Earth gravity)", "microgravedad": "microgravity"}
i18n.en_many({EARTH_GRAVITY: _GRAVITY_EN[EARTH_GRAVITY]})


def _regime(gravity: str) -> str:
    """Una gravedad (la de Tierra o la configurada) en el idioma de la peticion, si se le
    conoce ingles."""
    return i18n.tr(gravity, _GRAVITY_EN.get(gravity, gravity))


def gravity_now(phase: MissionPhase, gravity_regime: str) -> str:
    """La gravedad del momento: en posvuelo, la de Tierra; si no, la de la mision."""
    if phase is MissionPhase.POSTFLIGHT:
        return EARTH_GRAVITY
    return gravity_regime


def gravity_display(phase: MissionPhase, gravity_regime: str) -> str:
    """La frase de la gravedad tal cual se muestra: si difiere de la de la mision, las dos.

    En el idioma de la peticion; `gravity_now` da el texto tal cual, sin traducir.
    """
    now = _regime(gravity_now(phase, gravity_regime))
    if phase is not MissionPhase.POSTFLIGHT:
        return now
    return f"{now}; {i18n.loc(MISSION_GRAVITY_LABEL)}: {_regime(gravity_regime)}"


def mission_day(moment: dt.datetime, start: dt.date) -> float:
    origin = dt.datetime.combine(start, dt.time(0, 0, tzinfo=dt.UTC))
    return (moment - origin).total_seconds() / 86_400


def phase_at(moment: dt.datetime, start: dt.date, duration_days: int) -> MissionPhase:
    day = mission_day(moment, start)
    if day < 0:
        return MissionPhase.PREFLIGHT
    if day >= duration_days:
        return MissionPhase.POSTFLIGHT
    if day < ADAPTATION_DAYS:
        return MissionPhase.ADAPTATION
    if day >= duration_days - RETURN_DAYS:
        return MissionPhase.RETURN
    return MissionPhase.STABLE


def context(
    moment: dt.datetime, start: dt.date, duration_days: int, gravity_regime: str
) -> dict[str, Any]:
    phase = phase_at(moment, start, duration_days)
    return {
        "mission_day": round(mission_day(moment, start), 2),
        "duration_days": duration_days,
        "phase": str(phase),
        "phase_display": i18n.loc(phase.display),
        # Todas las fases, en orden y con su nombre: la interfaz pinta la tira de fases con
        # esto. Tenia su propia lista y no coincidia («regreso» frente a «preparación del
        # regreso»): la misma fase con dos nombres.
        "phases": [
            {"key": str(item), "display": i18n.loc(item.display)} for item in MissionPhase
        ],
        # La configurada, sin seguir a la fase: se conserva por compatibilidad. Lo que se
        # muestra es `gravity_display` (ver cabecera).
        "gravity_regime": gravity_regime,
        "gravity_now": _regime(gravity_now(phase, gravity_regime)),
        "gravity_mission": _regime(gravity_regime),
        "gravity_mission_label": i18n.loc(MISSION_GRAVITY_LABEL),
        "gravity_display": gravity_display(phase, gravity_regime),
        "phase_basis": i18n.tr(
            f"diseño EMMA: adaptación los primeros {ADAPTATION_DAYS} días y regreso los "
            f"últimos {RETURN_DAYS}; la fase se muestra y no cambia el análisis",
            f"EMMA design: adaptation for the first {ADAPTATION_DAYS} days and return for the "
            f"last {RETURN_DAYS}; the phase is shown and does not change the analysis",
        ),
    }
