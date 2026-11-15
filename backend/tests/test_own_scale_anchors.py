"""Las anclas de las tres escalas propias: decisión de diseño de EMMA, sin validar.

Por qué existe: ánimo, síntomas y apetito son escalas que EMMA definió para la misión. No hay
instrumento publicado detrás y, por tanto, nada que leer sobre sus puntos (de la escala
hedónica sí se leyeron sus rótulos: `tests/test_pvt_sources.py`). El 2026-10-15 el usuario
decidió que sus anclas se publiquen igual, como lo que son. El riesgo de publicarlas es que se
lean como lo que no son, y estas pruebas lo impiden de tres maneras:

1. presentarlas como validadas: cada una lleva la marca «decisión de diseño de EMMA, sin
   validar», y ningún texto sobre ellas dice «validada» ni «validated»;
2. citarles una ficha de evidencia como si fuera su instrumento: sus anclas no tienen campo
   donde llevar frase, ficha ni enlace, y ningún identificador, título o URL del registro de
   evidencia aparece en su escala;
3. que un texto de EMMA diga «escala validada», de estas o de cualquier otra: nadie ha leído
   la validación de ninguna escala del catálogo.

Y que publicarlas no mueva nada que puntúe: rango, unidad, referencia y extremo vigilado
siguen como estaban (invariante 5). Ninguna prueba sale a la red (invariante 3).
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import diary
from app.api.routes import new_store, reset_store
from app.core import versioning
from app.core.config import Settings, get_settings
from app.evidence import instruments_read, registry
from app.ingest.codes import (
    CATALOG,
    MISSION_SPECIFIC,
    OWN_SCALE_ANCHORS,
    OWN_SCALES_DECIDED_ON,
    ReferenceBasis,
)
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent

# Cualquier forma de «validada» o «validated». «sin validar» se quita antes de buscar: es la
# marca, no una afirmación.
VALIDATED = re.compile(
    r"\bvalidad[oa]s?\b|\bvalidated\b|\bvalidaci[oó]n\b|\bvalidation\b", re.IGNORECASE
)
UNVALIDATED = re.compile(r"\bsin validar\b", re.IGNORECASE)

# «escala validada», «escala propia de la misión validada», «validated mood scale», «the scale
# was validated». Una negación entre medias («la escala no está validada») no lo dice.
VALIDATED_SCALE = re.compile(
    r"\bescalas?\s+(?:[\w-]+\s+){0,4}?validad[oa]s?\b"
    r"|\bvalidated\s+(?:[\w-]+\s+){0,3}?scales?\b"
    r"|\bscales?\s+(?:[\w-]+\s+){0,3}?validated\b",
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(no|ni|sin|not|nor|never)\b", re.IGNORECASE)

# Lo que se recorre: los textos que escribe EMMA. La documentación del equipo
# (`docs/contexto/`, salvo su README de comparación) no es de EMMA, y una frase de una fuente
# (`quote`) dice lo que dice la fuente. La interfaz no viaja a la copia de las campañas de
# mutantes (`scripts/mutants.py`): allí se recorre el resto.
FRONTEND = ROOT / "frontend" / "src"
SCANNED = [
    *sorted((BACKEND / "app").rglob("*.py")),
    *sorted((BACKEND / "app" / "data").glob("*.json")),
    *sorted(
        path for pattern in ("*.ts", "*.tsx")
        for path in (FRONTEND.rglob(pattern) if FRONTEND.is_dir() else ())
        if ".test." not in path.name
    ),
    *sorted((ROOT / "compliance").rglob("*.md")),
    *sorted((ROOT / "docs").glob("*.md")),
    ROOT / "docs" / "contexto" / "README.md",
]

# Lo que la escala de cada una tenía antes de publicar sus anclas, y tiene que seguir teniendo:
# unidad, rango físico, referencia, extremo vigilado y límites de peligro.
PINNED = {
    "mood-valence": ("{score}", 0, 10, 4, 10, "low", None, None),
    "symptom-burden": ("{score}", 0, 10, 0, 2, "high", None, None),
    "appetite-rating": ("{score}", 0, 10, None, None, "low", None, None),
}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _scales(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/diary")
    assert response.status_code == 200
    return {
        item["key"]: item["scale"]
        for item in response.json()["indicators"]
        if item["scale"] is not None
    }


def _strings(value: Any, skip: frozenset[str] = frozenset()) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in skip:
                yield from _strings(item, skip)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item, skip)


def _claims_validated(text: str) -> list[str]:
    return VALIDATED.findall(UNVALIDATED.sub("", text))


def _says_validated_scale(text: str) -> list[str]:
    return [
        match.group()
        for match in VALIDATED_SCALE.finditer(text)
        if not NEGATION.search(match.group())
    ]


def _texts_about(key: str, scale: dict[str, Any]) -> list[str]:
    """Todo lo que EMMA dice de una escala propia: lo servido y lo escrito en el catálogo."""
    anchors = OWN_SCALE_ANCHORS[key]
    return [
        *_strings(scale),
        MISSION_SPECIFIC[key],
        anchors.low,
        anchors.high,
        anchors.why,
        diary.SCALE_OWN,
    ]


# --------------------------------------------------------------------------- #
# Qué se publica
# --------------------------------------------------------------------------- #


def test_the_anchors_are_declared_for_exactly_the_mission_own_scales() -> None:
    assert set(OWN_SCALE_ANCHORS) == instruments_read.OWN_SCALES == {
        "mood-valence", "symptom-burden", "appetite-rating",
    }
    # Las tres tienen código propio con su razón, y ninguna tiene nada leído.
    assert set(OWN_SCALE_ANCHORS) <= set(MISSION_SPECIFIC)
    raw = json.loads(instruments_read.READ_PATH.read_text(encoding="utf-8"))
    assert not set(OWN_SCALE_ANCHORS) & set(raw["scales"])


def test_each_own_scale_publishes_its_anchors_marked_as_an_unvalidated_design_decision(
    client: TestClient,
) -> None:
    scales = _scales(client)
    for key, decided in OWN_SCALE_ANCHORS.items():
        scale = scales[key]
        code = CATALOG[key]
        anchors = scale["design_anchors"]
        assert anchors["status"] == diary.DESIGN_STATUS == "design"
        assert anchors["status_display"] == "decisión de diseño de EMMA, sin validar"
        assert anchors["decided_on"] == OWN_SCALES_DECIDED_ON == "2026-10-15"
        # Por qué decide EMMA: no hay instrumento publicado.
        assert anchors["why"] == decided.why
        assert anchors["why"].startswith("No hay instrumento publicado detrás")
        # Los extremos del rango del catálogo, y nada en medio.
        assert anchors["anchors"] == [
            {"value": code.physical_min, "label": decided.low},
            {"value": code.physical_max, "label": decided.high},
        ]
        assert anchors["between"] == "Entre 0 y 10 ningún punto lleva ancla."
        # Siguen sin rótulos leídos: un ancla decidida no ocupa el sitio de uno.
        assert scale["labels"] is None and scale["labels_status"] == "own"
        assert scale["labels_note"].startswith(diary.SCALE_UNLABELLED)
        assert anchors["status_display"] in scale["labels_note"]


def test_the_reference_the_scale_already_had_is_published_with_its_origin(
    client: TestClient,
) -> None:
    scales = _scales(client)
    assert scales["mood-valence"]["design_anchors"]["reference"] == (
        "El catálogo le da de 4,0 a 10,0 como rango de referencia, también decidido por EMMA: "
        "no se observó en población."
    )
    assert scales["symptom-burden"]["design_anchors"]["reference"] == (
        "El catálogo le da de 0,0 a 2,0 como rango de referencia, también decidido por EMMA: "
        "no se observó en población."
    )
    assert scales["appetite-rating"]["design_anchors"]["reference"] == (
        "El catálogo no le da rango de referencia."
    )
    assert CATALOG["mood-valence"].reference_basis is ReferenceBasis.DESIGN
    assert CATALOG["symptom-burden"].reference_basis is ReferenceBasis.DESIGN


def test_a_half_reference_range_says_the_end_it_has() -> None:
    # El catálogo admite medio rango (`fluid-intake-24h` solo tiene extremo bajo). Ninguna
    # escala propia lo tiene hoy, así que el caso es sintético: el extremo que hay se dice
    # («desde»/«hasta», como el rango físico) y no se da por ausente el rango entero.
    mood = CATALOG["mood-valence"]
    only_low = dataclasses.replace(mood, reference_high=None)
    only_high = dataclasses.replace(mood, reference_low=None)
    assert diary._reference_text(only_low) == (
        "El catálogo le da desde 4,0 como rango de referencia, también decidido por EMMA: "
        "no se observó en población."
    )
    assert diary._reference_text(only_high) == (
        "El catálogo le da hasta 10,0 como rango de referencia, también decidido por EMMA: "
        "no se observó en población."
    )
    neither = dataclasses.replace(
        mood, reference_low=None, reference_high=None, reference_basis=None
    )
    assert diary._reference_text(neither) == "El catálogo no le da rango de referencia."


def test_a_read_scale_and_an_unread_one_carry_no_design_anchors(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    hedonic = _scales(client)["food-acceptability"]
    assert hedonic["labels_status"] == "read" and hedonic["design_anchors"] is None
    # Una escala de puntos de la que no se leyó nada y que no es propia: ni rótulos ni anclas.
    monkeypatch.setattr(instruments_read, "OWN_SCALES", frozenset())
    unread = _scales(client)["mood-valence"]
    assert unread["labels_status"] == "unverified" and unread["design_anchors"] is None


# --------------------------------------------------------------------------- #
# 1. No se presentan como validadas
# --------------------------------------------------------------------------- #


def test_no_text_about_an_own_scale_presents_it_as_validated(client: TestClient) -> None:
    scales = _scales(client)
    for key in OWN_SCALE_ANCHORS:
        for text in _texts_about(key, scales[key]):
            assert not _claims_validated(text), (key, text)
        assert UNVALIDATED.search(scales[key]["design_anchors"]["status_display"])
        assert UNVALIDATED.search(scales[key]["labels_note"])


@pytest.mark.parametrize("text", [
    "Escala validada por EMMA.",
    "Anclas validadas en vuelo.",
    "Validated in astronauts.",
    "Pendiente de validación.",
])
def test_the_validated_rule_catches_a_claim(text: str) -> None:
    assert _claims_validated(text)


def test_the_validated_rule_lets_the_mark_through() -> None:
    assert not _claims_validated("decisión de diseño de EMMA, sin validar")


# --------------------------------------------------------------------------- #
# 2. No se les cita una ficha como si fuera su instrumento
# --------------------------------------------------------------------------- #


def test_no_evidence_card_is_cited_as_the_instrument_of_an_own_scale(
    client: TestClient,
) -> None:
    refs = registry.registry().values()
    # Identificadores, títulos y enlaces del registro de evidencia.
    needles = {ref.id for ref in refs} | {ref.title for ref in refs} | {
        ref.url for ref in refs if ref.url
    }
    scales = _scales(client)
    for key in OWN_SCALE_ANCHORS:
        scale = scales[key]
        assert scale["labels_sources"] == [] and scale["labels_see_also"] == []
        assert scale["labels_not_found"] == [] and scale["labels_language"] is None
        # Las anclas no tienen dónde llevar una cita: ni frase, ni ficha, ni enlace.
        assert set(scale["design_anchors"]) == {
            "status", "status_display", "decided_on", "why", "anchors", "between", "reference",
        }
        for anchor in scale["design_anchors"]["anchors"]:
            assert set(anchor) == {"value", "label"}
        for text in _texts_about(key, scale):
            assert "http" not in text, (key, text)
            for needle in needles:
                assert not re.search(rf"(?<![\w-]){re.escape(needle)}(?![\w-])", text), (
                    key, needle, text,
                )


def test_an_own_scale_cannot_borrow_a_read_source_through_the_reader() -> None:
    """Ponerle a una escala propia la frase de otra se rechaza al cargar lo leído."""
    raw = json.loads(instruments_read.READ_PATH.read_text(encoding="utf-8"))
    for key in OWN_SCALE_ANCHORS:
        borrowed = json.loads(json.dumps(raw))
        borrowed["scales"][key] = raw["scales"]["food-acceptability"]
        with pytest.raises(instruments_read.InstrumentsError, match="escala propia de la misión"):
            instruments_read.validate(borrowed)


# --------------------------------------------------------------------------- #
# 3. Ningún texto de EMMA dice «escala validada»
# --------------------------------------------------------------------------- #


def _scanned_texts(path: Path) -> Iterator[str]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        yield from _strings(json.loads(raw), skip=frozenset({"quote"}))
    else:
        yield raw


def test_no_emma_text_says_validated_scale() -> None:
    assert len(SCANNED) > 50 and all(path.is_file() for path in SCANNED)
    if FRONTEND.is_dir():
        assert any(path.is_relative_to(FRONTEND) for path in SCANNED)
        assert any(path.name == "DiaryPanel.tsx" for path in SCANNED)
    found = [
        f"{path.relative_to(ROOT)}: {hit!r}"
        for path in SCANNED
        for text in _scanned_texts(path)
        for hit in _says_validated_scale(text)
    ]
    assert found == []


@pytest.mark.parametrize("text", [
    "La escala de ánimo es una escala validada.",
    "Escala propia de la misión validada por EMMA.",
    "A validated mood scale.",
    "The appetite scale was validated in flight.",
    "Escalas validadas: ánimo, síntomas y apetito.",
])
def test_the_validated_scale_rule_catches_the_phrase(text: str) -> None:
    assert _says_validated_scale(text)


@pytest.mark.parametrize("text", [
    "Escala propia, decisión de diseño de EMMA, sin validar.",
    "La escala no está validada.",
    "This scale is not validated.",
    "The PVT-B was validated in controlled laboratory studies.",
])
def test_the_validated_scale_rule_lets_honest_text_through(text: str) -> None:
    assert not _says_validated_scale(text)


# --------------------------------------------------------------------------- #
# Nada que puntúe se mueve
# --------------------------------------------------------------------------- #


def test_publishing_the_anchors_moved_nothing_that_scores() -> None:
    for key, pinned in PINNED.items():
        code = CATALOG[key]
        assert (
            code.unit, code.physical_min, code.physical_max, code.reference_low,
            code.reference_high, code.concerning, code.critical_low, code.critical_high,
        ) == pinned
    # Lo que decide la versión de las reglas no ve las anclas: no son una regla.
    catalog = versioning.rules()["catalog"]
    assert catalog["mood-valence"] == [
        "mood-valence", "{score}", 4, 10, None, None, "design", "low",
    ]
    assert catalog["symptom-burden"] == [
        "symptom-burden", "{score}", 0, 2, None, None, "design", "high",
    ]
    assert catalog["appetite-rating"] == [
        # Sin rango no hay base (decisión del usuario, 2026-10-20): `null`, no «observada».
        "appetite-rating", "{score}", None, None, None, None, None, "low",
    ]
    assert "anchor" not in json.dumps(versioning.rules()).lower()
