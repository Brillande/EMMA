# SPDX-License-Identifier: AGPL-3.0-or-later
"""Qué informes de dolor conviene comentar pronto con el médico de a bordo.

Por qué existe: el mapa de dolor registra, pero no distingue un calambre en la pantorrilla de una
opresión en el pecho. Algunos dolores no deberían esperar a la revisión rutinaria, y la
tripulación no tiene por qué saber cuáles.

Qué NO es: una alerta. No entra en el motor de riesgo ni en las alarmas de la consola. Una vía de
alerta nueva exige medir falsa alarma y sensibilidad juntas (invariante 5), y no hay datos de
dolor con los que medirlas (`compliance/external-validation.md`). Es una marca informativa:
"comentar con el médico de a bordo", nunca una orden ni un diagnóstico (invariante 7).

Usa `polaris/tools/sintomas.py` de la copia literal de Polaris, sin modificarla (commit en
`polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»; se
carga con `app.polaris.load`): su `es_alarma()`, con su lista conservadora `ALARMA`, que marca un
síntoma para "contarlo pronto" sin interpretarlo. Lo que es de EMMA (AGPL §5a):
  * Allí se busca en el texto libre del diario; en EMMA el informe de dolor no tiene texto libre
    (listas cerradas, `app/pain/catalog.py`). Así que cada zona marcada se describe con una frase
    fija compuesta desde el catálogo —"opresión en el pecho", "dolor de espalda intenso"— y esa
    frase pasa por `is_alarm()`, que es `es_alarma()` tal cual. Las entradas de la lista que un
    mapa de dolor no puede producir (disnea, fiebre, sangrado…) están pero nunca casan.
  * "Intenso" se traduce a la escala 0-10 con el corte de Serlin et al. (Pain 1995, PMID
    7659438): 7-10 es dolor intenso. Se estableció en pacientes oncológicos, no en tripulantes;
    es la convención clínica más citada, no un umbral validado en vuelo.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app import polaris
from app.core import i18n
from app.pain.catalog import ZONES

# Serlin et al. 1995: 1-4 leve, 5-6 moderado, 7-10 intenso.
SEVERE_FROM = 7

DISCUSS_NOTE = "Comentar con el médico de a bordo."

# El inglés de la marca y de sus frases fijas (2026-11-15). Las frases se componen y se cotejan en
# castellano, porque la lista `ALARMA` de Polaris está en castellano: traducirlas antes de
# `is_alarm` haría que ninguna casara. El inglés se pone después, al servir (`api/pain.py`).
i18n.en_many({
    DISCUSS_NOTE: "For discussion with the onboard physician.",
    "opresión en el pecho": "chest pressure",
    "dolor en el pecho": "chest pain",
    "dolor de cabeza intenso": "severe headache",
    "dolor de espalda intenso": "severe back pain",
    "hormigueo de un lado": "tingling on one side",
})

def is_alarm(*texts: str) -> bool:
    """True si algo casa con la lista conservadora. Es `es_alarma()` de Polaris, con su lista
    `ALARMA` entera, llamado en la copia literal (`polaris/`)."""
    return bool(polaris.load("sintomas").es_alarma(*texts))


def describe(zone: str, intensity: int, characters: Iterable[str]) -> list[str]:
    """Las frases fijas con que se describe una zona marcada. Solo salen del catálogo."""
    kinds = set(characters)
    severe = intensity >= SEVERE_FROM
    phrases: list[str] = []
    if zone == "chest":
        phrases.append("opresión en el pecho" if "pressing" in kinds else "dolor en el pecho")
    if zone == "head" and severe:
        phrases.append("dolor de cabeza intenso")
    if zone in ("upper-back", "lower-back") and severe:
        phrases.append("dolor de espalda intenso")
    return phrases


def discuss(report: dict[str, Any]) -> list[str]:
    """Las frases de un informe que casan con la lista. Vacía: nada que marcar."""
    flagged: list[str] = []
    tingling_sides: set[str] = set()
    for zone in report.get("zones") or []:
        key, kinds = str(zone.get("zone")), list(zone.get("characters") or [])
        for phrase in describe(key, int(zone.get("intensity", 0)), kinds):
            if is_alarm(phrase) and phrase not in flagged:
                flagged.append(phrase)
        side = ZONES[key].side if key in ZONES else None
        if "tingling" in kinds and side is not None:
            tingling_sides.add(side)
    # Hormigueo en un solo lado del cuerpo; en los dos lados no es "de un lado".
    if len(tingling_sides) == 1 and is_alarm("hormigueo de un lado"):
        flagged.append("hormigueo de un lado")
    return flagged
