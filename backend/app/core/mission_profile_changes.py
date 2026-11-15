"""El entorno de la misión, declarado en el registro firmado: quién lo cambia y qué cuenta.

POR QUÉ EXISTE
--------------
Lo pidió el usuario (2026-11-04): «poder elegir el entorno: como está seleccionado entorno de la
misión Tránsito a Marte, poder elegir las otras opciones como órbita baja». Hasta aquí el perfil
de misión salía solo de la configuración (`EMMA_MISSION_PROFILE`), y cambiarlo pedía reiniciar el
backend con otro `.env`: nadie a bordo podía decir «ya estamos en la superficie», y nada dejaba
constancia de quién lo dijo ni cuándo. Ahora la configuración da el valor de partida y cada cambio
es un asiento firmado por la consola, con el patrón del nivel de misión (`core/mission_modes.py`):
una persona con nombre, un motivo opcional, la versión que sube con cada cambio y, para Tierra, lo
firmado hasta su corte.

SIGUE SIENDO DESCRIPTIVO
------------------------
Declarar otro entorno cambia **qué perfil se describe** y, desde el 2026-11-11 (decisión del
usuario), **hacia qué cuerpo se calculan las efemérides**: el objetivo lo decide el perfil
(`mission_profiles.ephemeris_target`), y uno sin objetivo no consulta Horizons. El riesgo se sigue
escalando con el tiempo de luz REAL de las efemérides (`analysis/risk.py`), no con lo que diga el
perfil (decisión del 2026-10-13); lo que cambia es de qué cuerpo es ese tiempo de luz. Ningún
módulo de `analysis/` ni de `advisor/` importa este, y las pruebas fijan que, fuera de ese tiempo
de luz, el estado y las alertas son idénticos antes y después de un cambio
(`tests/test_mission_profile_declaration.py`, `tests/test_mission_profile.py`, invariante 5).

LAS REGLAS
----------
* el entorno nuevo es uno del catálogo (`mission_profiles.EXPECTED_IDS`); otro es un 422;
* lo firma una persona con nombre; el motivo es opcional;
* no se firma el entorno vigente otra vez (409);
* el asiento lleva también el entorno que dejaba atrás (`previous`), el vigente al firmar: así la
  crónica dice «de X a Y» con lo firmado, también en el primer cambio, cuyo anterior es el de la
  configuración, que no está en el registro.

Las aplica el almacén bajo su cerrojo (`storage._change_mission_profile`), como las del nivel.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core import i18n
from app.evidence import mission_profiles

REGISTRY = "registro"
CONFIGURATION = "configuración"

RULE = (
    "El entorno de partida es el de la configuración. Cada cambio lo firma una persona con nombre, "
    "con un motivo opcional, y vale el último asiento firmado por la consola; no se repite el "
    "entorno vigente."
)
DESCRIPTIVE = (
    "Declarar un entorno cambia qué perfil se describe y hacia qué cuerpo se calcula el tiempo de "
    "luz real de las efemérides, que es lo que escala el riesgo (un entorno sin ese cuerpo no lo "
    "escala). Nada más del entorno cambia un nivel, una puntuación o una alerta."
)
i18n.en(
    RULE,
    "The starting environment is the one in the configuration. Each change is signed by a named "
    "person, with an optional reason, and the last entry signed by the console is the one in "
    "force; the environment in force is not repeated.",
)
i18n.en(
    DESCRIPTIVE,
    "Declaring an environment changes which profile is described and towards which body the "
    "real light time of the ephemerides is computed, which is what scales the risk (an "
    "environment without that body does not scale it). Nothing else about the environment "
    "changes a level, a score or an alert.",
)


class MissionProfileConflict(ValueError):
    """El cambio choca con el entorno vigente (ya es ese): un 409."""


def display(profile_id: str) -> str:
    """El nombre del perfil en el catálogo; uno que no está, entre comillas y dicho así."""
    for profile in mission_profiles.catalog()["profiles"]:
        if profile["id"] == profile_id:
            return str(profile["display"])
    return i18n.tr(
        f"«{profile_id}» (no está en el catálogo)", f"«{profile_id}» (not in the catalogue)"
    )


def check_change(current: str, new: str, declared_by: str) -> None:
    """Las reglas de un cambio de entorno. Las aplica el almacén, bajo su cerrojo.

    `ValueError` para lo que falta o sobra en la petición (un 422); `MissionProfileConflict` para
    lo que choca con el entorno vigente (un 409).
    """
    if new not in mission_profiles.EXPECTED_IDS:
        raise ValueError(
            f"entorno desconocido: {new}; uno de {', '.join(mission_profiles.EXPECTED_IDS)}"
        )
    if not any(char.isalpha() for char in declared_by):
        raise ValueError("el entorno lo declara una persona con nombre")
    if new == current:
        raise MissionProfileConflict(f"el entorno de la misión ya es {display(new)}")


def entry_problem(entry: Mapping[str, Any]) -> str | None:
    """Lo que hace inservible un asiento firmado de entorno, o None.

    Un entorno fuera del catálogo, o igual al que dejaba atrás: firmado, pero no es un cambio que
    la API habría aceptado, y no se adivina qué quiso decir. El anterior puede ser uno que no
    está en el catálogo: es el de la configuración, que no se valida al arrancar.
    """
    if entry["profile"] not in mission_profiles.EXPECTED_IDS:
        return "entorno desconocido"
    if entry["profile"] == entry["previous"]:
        return "el entorno firmado es el mismo que dejaba atrás"
    return None


def chronicle_sentence(entry: Mapping[str, Any]) -> str:
    """El cambio en una frase para la crónica: de qué entorno a cuál, y el motivo. No manda nada."""
    before, after = display(entry['previous']), display(entry['profile'])
    text = i18n.tr(
        f"entorno de la misión: de {before} a {after}",
        f"mission environment: from {before} to {after}",
    )
    reason = str(entry.get("reason") or "").strip()
    if reason:
        text += i18n.tr(f"; motivo: {reason}", f"; reason: {reason}")
    return text


def source_text(state: Mapping[str, Any]) -> str:
    """De dónde sale el entorno vigente, en una frase."""
    if state["source"] == REGISTRY:
        return i18n.tr(
            f"Declarado en el registro firmado (asiento {state['ledger_index']}) por "
            f"{state['declared_by']}.",
            f"Declared in the signed ledger (entry {state['ledger_index']}) by "
            f"{state['declared_by']}.",
        )
    return i18n.tr(
        "Valor de partida de la configuración (EMMA_MISSION_PROFILE): no se ha firmado ningún "
        "cambio.",
        "Starting value from the configuration (EMMA_MISSION_PROFILE): no change has been "
        "signed.",
    )


def view(state: Mapping[str, Any]) -> dict[str, Any]:
    """El entorno vigente con su nombre, de dónde sale, la regla y los entornos que se pueden
    declarar."""
    return {
        **state,
        "display": display(state["id"]),
        "configured_display": display(state["configured"]),
        "source_text": source_text(state),
        "rule": i18n.loc(RULE),
        "descriptive": i18n.loc(DESCRIPTIVE),
        "profiles": [
            {"id": str(profile["id"]), "display": str(profile["display"])}
            for profile in mission_profiles.catalog()["profiles"]
        ],
    }
