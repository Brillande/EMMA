# SPDX-License-Identifier: AGPL-3.0-or-later
"""Analíticas escaneadas → lecturas por confirmar, con el extractor de Polaris tal cual.

Por qué existe: una analítica en papel trae cuarenta cifras que el sistema podría vigilar, pero
el OCR se equivoca de formas que no se ven —una coma perdida, la unidad de otro laboratorio, un
«<9» leído como 9—. Polaris (`biomarcadores.py`) ya resolvió la parte de leer: un diccionario
curado de analitos, la familia de unidades y una confianza por lectura. Aquí se usa sin tocar y
se añade lo único que EMMA necesita encima: **ninguna cifra leída entra en el análisis hasta que
una persona la confirma** (`POST /api/reports/{índice}/labs/confirm`), y la que no se puede fiar
—unidad de otra familia, valor censurado— no se confirma sin corregir.

El extractor corre sobre el texto del OCR **antes** de des-identificarlo: la des-identificación
puede tapar una fecha o un número que no es un identificador, y la cifra de un analito no lo es.
De ese texto solo se guarda lo estructurado (analito, valor, unidad, rango), nunca la línea.

Licencia y origen (AGPL §5a): usa `polaris/tools/biomarcadores.py` de la copia literal de Polaris,
sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: la confirmación humana de cada
lectura antes de que entre en el análisis.
"""

from __future__ import annotations

import datetime as dt
import threading
from functools import cache
from typing import Any

from app import polaris
from app.ingest.codes import LAB_REPORT_ONLY, get
from app.ingest.fhir import require_catalog_unit

# Clave de Polaris → indicador de EMMA. Leucocitos y los recuentos absolutos ya existían en el
# catálogo (`leukocytes`, `lymphocytes`, `neutrophils`) y se reutilizan: dos claves para la misma
# magnitud partirían su serie en dos.
LAB_KEYS: dict[str, str] = {
    "leucocitos": "leukocytes",
    "neutrofilos_abs": "neutrophils",
    "neutrofilos_pct": "neutrophils-percent",
    "linfocitos_abs": "lymphocytes",
    "linfocitos_pct": "lymphocytes-percent",
    "nlr": "neutrophil-lymphocyte-ratio",
    "hematies": "erythrocytes",
    "chcm": "mchc",
    "hcm": "mch",
    "hemoglobina": "hemoglobin",
    "hematocrito": "hematocrit",
    "vcm": "mcv",
    "plaquetas": "platelets",
    "glucosa": "glucose",
    "urea": "urea",
    "creatinina": "creatinine",
    "proteinas_totales": "total-protein",
    "albumina": "albumin",
    "got": "ast",
    "gpt": "alt",
    "ggt": "ggt",
    "fosfatasa_alcalina": "alkaline-phosphatase",
    "bilirrubina_total": "bilirubin-total",
    "bilirrubina_directa": "bilirubin-direct",
    "ldh": "ldh",
    "pcr": "c-reactive-protein",
    "sodio": "sodium",
    "potasio": "potassium",
    "cloro": "chloride",
    "calcio": "calcium",
    "magnesio": "magnesium",
    "fosforo": "phosphate",
    "ca153": "ca-15-3",
    "cea": "cea",
    "ca125": "ca-125",
    "ca199": "ca-19-9",
    "ca2729": "ca-27-29",
    "b2m": "beta2-microglobulin",
    "cga": "chromogranin-a",
    "nse": "neuron-specific-enolase",
    "tsh": "tsh",
    "t4l": "free-t4",
    "estradiol": "estradiol",
    "fsh": "fsh",
    "lh": "lh",
    # Derivado por Polaris (`_añadir_bun_cr`: urea / 2,14 ÷ creatinina), no leído.
    "bun_cr": "bun-creatinine-ratio",
}

PENDING = "por_confirmar"
_LOCK = threading.Lock()
# El nombre con que Polaris rotula el cociente que deriva (`_añadir_bun_cr`). No está en su
# `ANALITOS` salvo mientras se calcula: se escribe aquí una vez para la lectura y para `names`.
_BUN_CR_NAME = "Ratio BUN/Creatinina (derivado)"


@cache
def _biomarkers() -> Any:
    return polaris.load("biomarcadores")


@cache
def names() -> dict[str, str]:
    """Indicador de EMMA → el nombre en español con que EMMA enseña su lectura de una analítica.

    Es el `nombre` del diccionario de Polaris (`ANALITOS`), por el mismo `LAB_KEYS`: el que lleva
    cada lectura extraída (`name`). Es la referencia contra la que se comprueba el nombre de
    origen `polaris` de `ingest/names_es.py`, que lo lee del `nombre` copiado en
    `data/lab_loinc.json` para no cargar Polaris en cada frase del análisis: una prueba exige que
    los dos coincidan, así la copia no se separa de esta.
    """
    # `_derived_bun_cr` añade y quita una entrada de `ANALITOS` bajo este cerrojo.
    with _LOCK:
        entries = list(_biomarkers().ANALITOS)
    found = {
        LAB_KEYS[str(entry["key"])]: str(entry["nombre"])
        for entry in entries
        if str(entry["key"]) in LAB_KEYS
    }
    found.setdefault(LAB_KEYS["bun_cr"], _BUN_CR_NAME)
    return found


def extract(text: str) -> dict[str, Any]:
    """Fecha del informe y una lectura por línea reconocida, todas por confirmar.

    `unit` es la unidad UCUM del catálogo; `report_unit` la que Polaris esperaba leer. Si la
    familia leída no era la esperada, Polaris baja la confianza a `baja` y la cifra **no** está en
    la unidad del catálogo: se exige corregir. Igual un valor censurado («<9»): solo dice que está
    por debajo de un límite, y una observación es un número.
    """
    source = _biomarkers()
    readings: list[dict[str, Any]] = []
    for line in text.splitlines():
        parsed = source.parse_line(line)
        if parsed is None:
            continue
        entry, point = parsed
        key = LAB_KEYS.get(str(entry["key"]))
        if key is None:
            continue
        comparator = point.get("cmp")
        confidence = str(point["confianza"])
        readings.append(
            {
                "polaris_key": str(entry["key"]),
                "key": key,
                "name": str(entry["nombre"]),
                "value": float(point["valor"]),
                "unit": get(key).unit,
                "report_unit": str(point["unidad"]),
                "ref_low": point["ref_low"],
                "ref_high": point["ref_high"],
                "ref_phase": point.get("ref_fase"),
                "out_of_range": bool(point["fuera"]),
                "confidence": confidence,
                "comparator": comparator,
                "requires_correction": confidence == "baja" or comparator is not None,
                "status": PENDING,
            }
        )
    readings.extend(_derived_bun_cr(readings))
    return {"date": source.fecha_de("", text), "readings": readings}


def _derived_bun_cr(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """El cociente BUN/creatinina, con `_añadir_bun_cr` de Polaris tal cual.

    Esa función añade además una entrada a su `ANALITOS` global en cada llamada: aquí se devuelve
    la lista a su estado, bajo cerrojo (la copia no se toca). Un derivado de una cifra que exige
    corrección también la exige: se calcula con la cifra sin corregir.
    """
    by_key = {item["polaris_key"]: item for item in readings}
    urea, creatinine = by_key.get("urea"), by_key.get("creatinina")
    if urea is None or creatinine is None:
        return []
    source = _biomarkers()
    data: dict[str, Any] = {
        "urea": {"_": {"valor": urea["value"], "confianza": urea["confidence"]}},
        "creatinina": {"_": {"valor": creatinine["value"], "confianza": creatinine["confidence"]}},
    }
    with _LOCK:
        size = len(source.ANALITOS)
        try:
            source._añadir_bun_cr(data)
        finally:
            del source.ANALITOS[size:]
    point = (data.get("bun_cr") or {}).get("_")
    if point is None:
        return []
    needs = bool(urea["requires_correction"] or creatinine["requires_correction"])
    return [{
        "polaris_key": "bun_cr",
        "key": LAB_KEYS["bun_cr"],
        "name": _BUN_CR_NAME,
        "value": float(point["valor"]),
        "unit": get(LAB_KEYS["bun_cr"]).unit,
        "report_unit": "",
        "ref_low": point["ref_low"],
        "ref_high": point["ref_high"],
        "ref_phase": None,
        "out_of_range": bool(point["fuera"]),
        "confidence": str(point["confianza"]),
        "comparator": None,
        "requires_correction": needs,
        "status": PENDING,
        "derived_from": str(point["fuente"]),
    }]


def confirmed_value(
    reading: dict[str, Any], value: float | None, unit: str | None
) -> float:
    """La cifra que se registra al confirmar, o `ValueError` si no se puede fiar.

    Una lectura que exige corrección solo se confirma con valor **y** unidad nuevos, y la unidad
    tiene que ser la del catálogo: EMMA no convierte unidades por su cuenta (una conversión mal
    elegida es el error silencioso del invariante 2). Sin corrección, la persona puede cambiar el
    valor —lo ha leído en el papel— pero no la unidad.
    """
    key = str(reading["key"])
    if key not in LAB_REPORT_ONLY and key not in LAB_KEYS.values():
        raise ValueError(f"'{key}' no es un analito de analítica")
    code = get(key)
    if unit is not None:
        # La comparación es la de toda la ingesta (`ingest.fhir.require_catalog_unit`), no una
        # propia: el mismo motivo por todas las vías. Lo que se añade es lo que puede hacer la
        # persona que tiene el papel delante; la conversión la hace ella, y EMMA no.
        try:
            require_catalog_unit(code, unit)
        except ValueError as exc:
            raise ValueError(
                f"{exc}. Para confirmarla, convierte el valor leído en el papel y declara "
                f"{code.unit!r}"
            ) from exc
    if reading.get("requires_correction") and (value is None or unit is None):
        raise ValueError(
            "esta lectura exige corrección (unidad de otra familia o valor censurado): "
            "indica el valor y la unidad leídos en el original"
        )
    return float(reading["value"]) if value is None else value


def effective_at(day: dt.date) -> dt.datetime:
    """La fecha de la extracción, a medianoche UTC: el informe no da la hora."""
    return dt.datetime.combine(day, dt.time(0, 0), tzinfo=dt.UTC)
