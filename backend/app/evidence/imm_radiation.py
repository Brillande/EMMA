"""Lo que el Integrated Medical Model (IMM) de NASA publica sobre radiación, y nada más.

Por qué existe: la maqueta «Panel EMMA: Radiación y Salud Espacial» (2026-11-14) llevaba cifras
por ubicación que EMMA no tenía, y el usuario pidió simularlas «con el IMM», «solo con los
parámetros del IMM». El IMM es la herramienta de Monte Carlo de NASA; su código no es público y
EMMA no lo ejecuta ni lo duplica (especificación del equipo, §16: «evitar duplicarlo»). Lo que sí
es público es su salida: el informe «Ranking of Medical Conditions by Probability» (2 de febrero
de 2015, iMED v5.0) da, para doce misiones de referencia de un tripulante, la probabilidad de al
menos un evento de cada condición. De radiación, solo una: el síndrome agudo de radiación. No da
dosis, eventos solares, índices geomagnéticos ni pronósticos, y EMMA no los inventa.

Lo leído vive en `data/imm_ars.json`. Este cargador es la defensa:

- la ficha (`imm-ranking-2015`) está en el registro y su nota dice «Leída el» con el día de
  lectura del fichero;
- cada probabilidad está, tal cual, en la fila citada de su tabla, y esa fila nombra la condición;
  los meses y las EVA de cada misión de referencia están en la fila citada de la Tabla 1, y la
  cifra de meses también en el título de su tabla cuando la escribe con cifras;
- cada perfil de misión de EMMA (`evidence/mission_profiles.py`) se asimila a una misión de
  referencia del IMM con su motivo: esa asimilación es de EMMA, no del IMM, y se dice. Ningún
  perfil queda sin ella y ninguna apunta a una misión que no esté en la tabla;
- los textos que escribe EMMA (`display`, `reason`, `measure_display`, `caveat_display`) no
  llevan cifras: las cifras son las del informe.

No entra en el análisis, en el riesgo, en la proyección de dosis ni en ninguna alerta
(invariante 5): se muestra. No sale a la red: la lectura se hizo una vez, en Tierra.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

from app.core import i18n
from app.evidence import mission_profiles, registry

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "imm_ars.json"

TOP_FIELDS = frozenset({
    "_nota", "ref", "read_on", "condition", "condition_display", "measure_quote", "measure_display",
    "caveat_quote", "caveat_display", "drms", "profiles",
})
DRM_FIELDS = frozenset({
    "key", "display", "drm_quote", "table", "row_quote", "probability", "months", "evas",
})
PROFILE_FIELDS = frozenset({"drm", "reason"})
SERVED = ("key", "display", "drm_quote", "table", "row_quote", "months", "evas")
# Lo que escribe EMMA: sin una cifra suya.
WRITTEN = ("condition_display", "measure_display", "caveat_display")
# «1.41E-03»: la forma en que el informe escribe la probabilidad.
PROBABILITY = re.compile(r"^\d\.\d{2}E-0\d$")


class ImmError(ValueError):
    """`data/imm_ars.json` no cumple su contrato."""


def _space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fields(where: str, value: Any, allowed: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ImmError(f"{where}: no es un objeto")
    missing = allowed - set(value) - {"_nota"}
    extra = set(value) - allowed
    if missing or extra:
        raise ImmError(f"{where}: faltan {sorted(missing)} o sobran {sorted(extra)}")
    return value


def _text(where: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImmError(f"{where}: texto vacío")
    return value


def _no_figures(where: str, text: str) -> None:
    if re.search(r"\d", text):
        raise ImmError(f"{where}: una cifra escrita por EMMA; las cifras son las del informe")


def validate(raw: Any) -> dict[str, Any]:
    """El fichero, comprobado. Lanza `ImmError` con el primer fallo."""
    data = _fields("imm_ars", raw, TOP_FIELDS)
    ref = registry.registry().get(_text("ref", data["ref"]))
    if ref is None:
        raise ImmError(f"ref: {data['ref']!r} no está en el registro de evidencia")
    read_on = _text("read_on", data["read_on"])
    dt.date.fromisoformat(read_on)
    if f"Leída el {read_on}" not in (ref.notes or ""):
        raise ImmError(f"ref: la nota de la ficha no dice «Leída el {read_on}»")
    condition = _text("condition", data["condition"])
    _text("measure_quote", data["measure_quote"])
    if condition not in _space(_text("caveat_quote", data["caveat_quote"])):
        raise ImmError("caveat_quote: la salvedad citada no nombra la condición")
    for name in WRITTEN:
        _no_figures(name, _text(name, data[name]))

    drms = data["drms"]
    if not isinstance(drms, list) or not drms:
        raise ImmError("drms: lista vacía")
    keys: set[str] = set()
    for index, item in enumerate(drms):
        where = f"drms[{index}]"
        drm = _fields(where, item, DRM_FIELDS)
        key = _text(f"{where}.key", drm["key"])
        if key in keys:
            raise ImmError(f"{where}: clave repetida {key!r}")
        keys.add(key)
        _no_figures(f"{where}.display", _text(f"{where}.display", drm["display"]))
        probability = _text(f"{where}.probability", drm["probability"])
        if not PROBABILITY.match(probability):
            raise ImmError(f"{where}: {probability!r} no está escrita como en el informe")
        row = _space(_text(f"{where}.row_quote", drm["row_quote"]))
        if condition not in row or probability not in row.split():
            raise ImmError(f"{where}: la fila citada no trae la condición con {probability}")
        months, evas = drm["months"], drm["evas"]
        counts = (months, evas)
        if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in counts):
            raise ImmError(f"{where}: meses y EVA son enteros positivos")
        parameters = _space(_text(f"{where}.drm_quote", drm["drm_quote"])).split()
        month_word = "month" if months == 1 else "months"
        if not re.search(rf"\b{months} {month_word} {evas}\b", " ".join(parameters)):
            raise ImmError(f"{where}: la Tabla 1 no dice {months} {month_word} y {evas} EVA")
        _text(f"{where}.table", drm["table"])

    profiles = data["profiles"]
    if not isinstance(profiles, dict):
        raise ImmError("profiles: no es un objeto")
    known = set(mission_profiles.EXPECTED_IDS)
    if set(profiles) != known:
        raise ImmError(f"profiles: tienen que ser los de EMMA {sorted(known)}, ni más ni menos")
    for profile, value in profiles.items():
        item = _fields(f"profiles.{profile}", value, PROFILE_FIELDS)
        if item["drm"] not in keys:
            raise ImmError(f"profiles.{profile}: {item['drm']!r} no es una misión de la tabla")
        where = f"profiles.{profile}.reason"
        _no_figures(where, _text(where, item["reason"]))
    return data


@cache
def _loaded() -> dict[str, Any]:
    return validate(json.loads(DATA_PATH.read_text(encoding="utf-8")))


def describe(declared: str | None) -> dict[str, Any]:
    """Lo que se sirve: cada misión de referencia con su probabilidad y su cita, y cada perfil de
    EMMA con la suya y el motivo; el declarado, señalado."""
    data = _loaded()
    ref = registry.get(data["ref"])
    drms = {
        item["key"]: {
            **{name: item[name] for name in SERVED},
            "probability_text": item["probability"],
            "probability": float(Decimal(item["probability"])),
        }
        for item in data["drms"]
    }
    # El idioma se pone al servir, con el hermano `imm_ars.en.json`: lo validado y lo cacheado es
    # el castellano; las filas y las frases del informe (`*_quote`, `table`) van en su idioma.
    return i18n.localized({
        "condition": data["condition"],
        "condition_display": data["condition_display"],
        "measure": data["measure_display"],
        "measure_quote": data["measure_quote"],
        "caveat": data["caveat_display"],
        "caveat_quote": data["caveat_quote"],
        "source": {
            "id": ref.id, "title": ref.title, "source": ref.source,
            "url": ref.url, "date": ref.date,
        },
        "read_on": data["read_on"],
        "drms": list(drms.values()),
        "profiles": [
            {
                "id": profile,
                "declared": profile == declared,
                "drm": item["drm"],
                "reason": item["reason"],
                "probability": drms[item["drm"]]["probability"],
                "probability_text": drms[item["drm"]]["probability_text"],
            }
            for profile, item in data["profiles"].items()
        ],
        "assigned_by": i18n.tr(
            "EMMA: el IMM no tiene los perfiles de EMMA; cada uno se asimila a su misión de "
            "referencia por el motivo que lleva",
            "EMMA: the IMM does not have EMMA's profiles; each one is matched to its reference "
            "mission for the reason it carries",
        ),
        "scope": i18n.tr(
            "se muestra; no entra en ningún nivel, alerta ni riesgo, y no es la probabilidad de "
            "este tripulante",
            "shown only; it does not enter any level, alert or risk, and it is not the "
            "probability of this crew member",
        ),
    }, DATA_PATH)


def cited_refs() -> frozenset[str]:
    """Las fichas que cita este módulo: la del informe del IMM."""
    return frozenset({_loaded()["ref"]})


# Un fichero roto se ve al arrancar, no a media misión.
_loaded()
