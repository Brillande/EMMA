"""Qué se puede firmar de las anclas de módulo: su declaración y lo que oye un receptor.

POR QUÉ EXISTE
--------------
El almacén (`core/storage.py`) tiene que rechazar un asiento mal formado aunque se le llame desde
fuera de la API, y la API tiene que dar el mismo 422 antes de escribir nada. Si cada uno
comprobara por su cuenta, un ancla declarada como «AA:BB» nunca coincidiría con la lectura que
llega como «aa:bb». Aquí está la regla una sola vez, sin depender del análisis: la estimación
del módulo vive en `analysis/location.py`.

Un ancla es equipo de la nave (BLE hoy; UWB o el RFID de la nave podrían entrar por el mismo
contrato). EMMA no la enciende ni la alimenta: solo guarda en qué módulo dice una persona que
está, y lo que oyó el receptor de un tripulante.
"""

from __future__ import annotations

import datetime as dt
import math
import re

from app.environment.habitat import MODULES

# Un ancla es una etiqueta corta, como un identificador de dispositivo: iBeacon
# (`uuid:major:minor`) y Eddystone-UID caben. Se guarda en minúsculas.
MAX_ANCHOR_LENGTH = 64
_ANCHOR = re.compile(r"[a-z0-9][a-z0-9:._-]*")
# El RSSI de BLE cabe en un byte con signo hasta +20 dBm: fuera de ahí no es una lectura.
MIN_RSSI = -127.0
MAX_RSSI = 20.0
# Lecturas por lote: una entrada de ledger por lote, y un lote no es un volcado.
MAX_SIGHTINGS = 500
MAX_SUBJECT_LENGTH = 64


def anchor_key(anchor_id: str) -> str:
    """El identificador de un ancla tal y como se guarda y se compara. ValueError si no vale."""
    key = anchor_id.strip().casefold()
    if not key or len(key) > MAX_ANCHOR_LENGTH or not _ANCHOR.fullmatch(key):
        raise ValueError(
            "identificador de ancla no válido: hasta "
            f"{MAX_ANCHOR_LENGTH} caracteres entre letras sin acento, cifras y : . _ -"
        )
    return key


def check_anchor(anchor_id: str, module: str, declared_by: str) -> str:
    """Lo que se puede firmar como ancla: un identificador válido, en un módulo de la lista, y
    dicho por una persona con nombre. Devuelve el identificador normalizado."""
    if module not in MODULES:
        raise ValueError(f"módulo desconocido: {module}; uno de {', '.join(MODULES)}")
    if not any(char.isalpha() for char in declared_by):
        raise ValueError("un ancla la declara una persona con nombre")
    return anchor_key(anchor_id)


def check_rssi(rssi_dbm: float) -> float:
    if (
        isinstance(rssi_dbm, bool)
        or not math.isfinite(rssi_dbm)
        or not MIN_RSSI <= rssi_dbm <= MAX_RSSI
    ):
        raise ValueError(f"RSSI fuera de [{MIN_RSSI:g}, {MAX_RSSI:g}] dBm: {rssi_dbm}")
    return float(rssi_dbm)


def check_batch(subject: str, count: int) -> None:
    if not subject.strip() or len(subject.strip()) > MAX_SUBJECT_LENGTH:
        raise ValueError("un lote de lecturas va a un tripulante")
    if not 1 <= count <= MAX_SIGHTINGS:
        raise ValueError(f"un lote lleva entre 1 y {MAX_SIGHTINGS} lecturas")


def aware(moment: dt.datetime) -> dt.datetime:
    if moment.tzinfo is None:
        raise ValueError("el instante debe llevar zona horaria")
    return moment
