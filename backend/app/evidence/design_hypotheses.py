"""Las hipótesis de diseño H1-H7, a la vista y sin darlas por probadas.

La base de conocimiento del equipo (`docs/contexto/knowledge-base-v1.md` §13) cierra con siete
«hipótesis prioritarias que deben probarse», y la especificación (§0) lo repite como orden: «no
asumas que las hipótesis biomédicas son hechos». EMMA tiene pieza hecha para varias —la línea
base personal, la banda ósea inferida, la causa compartida, las tres escalas de radiación, la
fatiga de menú— y, salvo H7, ninguna decía de qué hipótesis nacía. Un proyecto con las piezas
construidas y las hipótesis sin nombrar acaba presentando lo construido como si estuviera
demostrado: tener el módulo no es haber contrastado la hipótesis.

Aquí cada hipótesis va con su enunciado literal, qué módulo y qué ruta de EMMA la tocan, en qué
estado queda y qué NO demuestra EMMA sobre ella. **El vocabulario de estados no tiene «probada»**
y la carga rechaza cualquier otro: para afirmar más hay que cambiar este fichero a propósito.

Los identificadores llevan el prefijo `KB-` porque «H1…H18» a secas son los PELIGROS del
expediente de gestión de riesgos (`compliance/risk-management-file.md`), que son otra cosa.

Los anclajes de la especificación (§16) que nadie ha leído van aparte, con sus identificadores y
sin describir su contenido: no están en el registro de evidencia (`evidence/registry.py`) y
aquí no se resumen de oídas.

Es un inventario: no entra en el análisis, en el riesgo ni en ninguna alerta (invariante 5).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from app.core import i18n

HYPOTHESES_PATH = Path(__file__).resolve().parents[1] / "data" / "design_hypotheses.json"

# Las siete de la base de conocimiento §13, en su orden.
EXPECTED_IDS = tuple(f"KB-H{number}" for number in range(1, 8))

# En qué estado puede quedar una hipótesis. No hay «probada», y la carga no admite otro.
STATUSES = {
    "architecture": "hipótesis: EMMA la soporta en su arquitectura y no la prueba",
    "simulated": "hipótesis: con una pieza que la ejercita sobre datos simulados; no la prueba",
    "partly-real-data": "hipótesis: contrastada en parte con datos reales; no probada",
    "outside": "hipótesis: fuera de EMMA",
}
# El inglés tampoco tiene «proven»: «does not prove it», «not proved».
i18n.en_many({
    STATUSES["architecture"]: (
        "hypothesis: EMMA supports it in its architecture and does not prove it"
    ),
    STATUSES["simulated"]: (
        "hypothesis: with a component that exercises it on simulated data; it does not prove it"
    ),
    STATUSES["partly-real-data"]: "hypothesis: partly checked against real data; not proved",
    STATUSES["outside"]: "hypothesis: outside EMMA",
})
# El estado que obliga a decir con qué datos reales y con qué alcance.
REAL_DATA_STATUS = "partly-real-data"
OUTSIDE_STATUS = "outside"

UNREAD = "sin leer: no está en el registro de evidencia de EMMA"
NOTE = (
    "Hipótesis de diseño de la base de conocimiento del equipo, con su enunciado literal. "
    "Ninguna figura como probada: de cada una se dice qué pieza de EMMA la toca y qué no "
    "demuestra EMMA sobre ella. No son los peligros H1…H18 del expediente de gestión de riesgos."
)
i18n.en(UNREAD, "not read: it is not in EMMA's evidence registry")
# El enunciado literal es el castellano de la base de conocimiento: el inglés dice que lo traduce.
i18n.en(
    NOTE,
    "Design hypotheses from the team's knowledge base, each with its statement, translated here "
    "from the Spanish original. None is listed as proved: for each one it says which component "
    "of EMMA touches it and what EMMA does not demonstrate about it. They are not the hazards "
    "H1…H18 of the risk management file.",
)

_METHODS = ("GET", "POST")


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza un inventario que afirme más de lo que EMMA sabe, o que no diga lo que falta."""
    hypotheses = raw["hypotheses"]
    found = tuple(item["id"] for item in hypotheses)
    if found != EXPECTED_IDS:
        raise ValueError(f"se esperaban {EXPECTED_IDS} en ese orden, y hay {found}")
    for item in hypotheses:
        key = item["id"]
        if item["label"] != key.removeprefix("KB-"):
            raise ValueError(f"{key}: el rótulo {item['label']!r} no es el de su identificador")
        if not _text(item, "statement"):
            raise ValueError(f"{key}: falta el enunciado")
        if item["status"] not in STATUSES:
            raise ValueError(f"{key}: estado desconocido {item['status']!r}")
        if not _text(item, "not_demonstrated"):
            raise ValueError(f"{key}: falta lo que EMMA no demuestra sobre ella")
        if (item["status"] == REAL_DATA_STATUS) != _text(item, "real_data"):
            raise ValueError(
                f"{key}: los datos reales y su alcance se declaran solo, y siempre, en "
                f"el estado {REAL_DATA_STATUS!r}"
            )
        if not item["touches"] and item["status"] != OUTSIDE_STATUS:
            raise ValueError(f"{key}: sin ninguna pieza de EMMA, el estado es {OUTSIDE_STATUS!r}")
        for touch in item["touches"]:
            _validate_touch(key, touch)
    for anchor in raw["unread_anchors"]:
        if not _text(anchor, "anchor") or not anchor["references"]:
            raise ValueError("un anclaje sin leer lleva su nombre y sus identificadores")
        for reference in anchor["references"]:
            if not str(reference["ntrs"]).isdigit() or not _text(reference, "title"):
                raise ValueError(f"{anchor['anchor']}: referencia de NTRS mal formada")
    return raw


def _validate_touch(key: str, touch: dict[str, Any]) -> None:
    if not str(touch["module"]).startswith("app."):
        raise ValueError(f"{key}: {touch['module']!r} no es un módulo de EMMA")
    if not _text(touch, "what"):
        raise ValueError(f"{key}: {touch['module']} no dice qué hace por la hipótesis")
    route, method = touch["route"], touch["method"]
    if (route is None) != (method is None):
        raise ValueError(f"{key}: {touch['module']} lleva ruta y método, o ninguno de los dos")
    if route is not None and (not route.startswith("/api/") or method not in _METHODS):
        raise ValueError(f"{key}: ruta mal formada {method} {route}")


@cache
def inventory() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(HYPOTHESES_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def _registered(value: Any) -> Any:
    """`value` con cada cadena que es, entera, una constante registrada, en inglés."""
    if isinstance(value, str):
        return i18n.loc(value)
    if isinstance(value, dict):
        return {key: _registered(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_registered(item) for item in value]
    return value


def payload() -> dict[str, Any]:
    """El inventario como se sirve: la frase de cada estado se escribe aquí, no en la interfaz.

    En inglés se pasa entero al salir: lo que viene del fichero, con su hermano
    (`design_hypotheses.en.json`), y las frases de este módulo, con su inglés registrado. Los
    identificadores, los módulos, las rutas y el título del documento no cambian.
    """
    served = _payload()
    if i18n.current() != "en":
        return served
    english: dict[str, Any] = _registered(i18n.localized(served, HYPOTHESES_PATH))
    return english


def _payload() -> dict[str, Any]:
    raw = inventory()
    return {
        "source": dict(raw["source"]),
        "note": NOTE,
        "statuses": [{"id": key, "text": text} for key, text in STATUSES.items()],
        "hypotheses": [
            {
                "id": item["id"],
                "label": item["label"],
                "statement": item["statement"],
                "status": item["status"],
                "status_text": STATUSES[item["status"]],
                "real_data": item.get("real_data"),
                "scenario": item.get("scenario"),
                "documents": list(item.get("documents", [])),
                "touches": [dict(touch) for touch in item["touches"]],
                "not_demonstrated": item["not_demonstrated"],
            }
            for item in raw["hypotheses"]
        ],
        "unread_anchors": [
            {
                "anchor": anchor["anchor"],
                "listed_in": anchor["listed_in"],
                "status": "unread",
                "status_text": UNREAD,
                "references": [dict(reference) for reference in anchor["references"]],
            }
            for anchor in raw["unread_anchors"]
        ],
    }
