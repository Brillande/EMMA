"""Ningún texto presenta como abierto un hueco de NASA que se leyó cerrado, fusionado o archivado.

Por qué existe: la lectura del Human Research Roadmap del 2026-10-13 encontró Med07 cerrado, Med10
fusionado en Medical-701, los huecos Food-01…04 divididos y el de fatiga de menú (FN-205)
archivado, mientras `/api/framework` seguía presentando Med 07 y Med 10 como «huecos de NASA que
EMMA aborda». Corregir el texto una vez no basta: el siguiente que escriba sobre un hueco tiene
que tropezar con lo leído. El estado de cada hueco vive en `data/nasa_framework_read.json`
(campo `gap`); estas pruebas lo cruzan con todo lo que EMMA dice de ellos.

Dos reglas, a propósito sencillas:

1. Ninguna palabra que presente un hueco como abierto, o como algo que EMMA cierra o aborda,
   se refiere —por ser el hueco nombrado más cerca en la misma frase— a uno que no figura
   abierto, salvo negada.
2. Todo texto propio de EMMA que nombre un hueco que no figura abierto dice también su estado.

Las frases de NASA (`quote`) se excluyen de la regla 1: son lo que dice la fuente. Ninguna prueba
sale a la red (invariante 3).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence import nasa_framework
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent

# Lo que, junto al nombre de un hueco que no figura abierto, lo presenta como abierto o como
# algo que EMMA cierra. «cerrado» no está: es el estado leído de Med07.
OPEN_WORDS = re.compile(
    r"\b(abiert[oa]s?|open|vigentes?|pendientes?|aborda\w*|cierra\w*|cierre|cerrar\w*|"
    r"resuelve\w*|llena\w*|cubre\w*|ocupa\w*|closes?|addresses?)\b",
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(no|ni|ninguno|ninguna|not|nor)\b", re.IGNORECASE)
NEGATION_WINDOW = 5
SENTENCE = re.compile(r"(?<!\d)\.(?!\d)|[;\n]")
# Cualquier nombre con forma de hueco del Roadmap, tenga o no estado leído (FN-206, N13…): sirve
# para saber de qué hueco habla una palabra, no para juzgarlo.
ANY_GAP = re.compile(r"\b(?:Medical|Med|Food|FN|N)[- ]?\d{1,3}\b", re.IGNORECASE)

# Las palabras del estado leído, en castellano o como lo escribe NASA.
STATUS_WORDS = {
    "closed": r"cerrad|closed",
    "merged": r"fusion|merged",
    "archived": r"archiv",
    "split": r"dividi|split",
}

# Los textos que no son de EMMA: la documentación del equipo no se toca (`docs/contexto`).
SOURCES_READ = BACKEND / "app" / "data" / "nasa_framework_read.json"


def _pattern(gap_id: str) -> re.Pattern[str]:
    """«Med07» casa con «Med 07», «Med7» y «Med-07»; «FN-205» con «FN 205»."""
    match = re.fullmatch(r"([A-Za-z]+)[- ]?0*(\d+)", gap_id)
    assert match, gap_id
    prefix, number = match.groups()
    return re.compile(rf"\b{re.escape(prefix)}[- ]?0*{number}\b", re.IGNORECASE)


def _not_open() -> dict[str, str]:
    return {
        gap: status for gap, status in nasa_framework.gap_statuses().items() if status != "open"
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


def _negated(sentence: str, start: int) -> bool:
    """Si una negación precede de cerca («EMMA no aborda», «ninguno figura hoy como vigente»)."""
    return bool(NEGATION.search(" ".join(sentence[:start].split()[-NEGATION_WINDOW:])))


def _presents_as_open(text: str) -> list[str]:
    """Las palabras de «abierto» cuyo hueco más cercano en la frase es uno que no figura abierto.

    El hueco más cercano es el último nombrado antes de la palabra o, si no hay ninguno, el
    primero después: «Med10 se fusionó en Medical-701, que sigue abierto» habla de Medical-701;
    «Huecos que EMMA aborda: Med 07 y Med 10» habla de Med 07.
    """
    not_open = [_pattern(gap) for gap in _not_open()]
    found = []
    for sentence in SENTENCE.split(text):
        mentions = list(ANY_GAP.finditer(sentence))
        if not mentions:
            continue
        for word in OPEN_WORDS.finditer(sentence):
            if _negated(sentence, word.start()):
                continue
            before = [m for m in mentions if m.end() <= word.start()]
            nearest = before[-1] if before else next(
                (m for m in mentions if m.start() >= word.end()), None
            )
            if nearest is not None and any(p.fullmatch(nearest.group()) for p in not_open):
                found.append(f"{nearest.group()} · {word.group()}: {sentence.strip()!r}")
    return found


def _silent_about_status(text: str) -> list[str]:
    """Los huecos no abiertos que el texto nombra sin decir en qué estado figuran."""
    return [
        gap
        for gap, status in _not_open().items()
        if _pattern(gap).search(text)
        and not re.search(STATUS_WORDS[status], text, re.IGNORECASE)
    ]


def _markdown_sections(path: Path) -> list[str]:
    return re.split(r"\n(?=## )", path.read_text(encoding="utf-8"))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


# --------------------------------------------------------------------------- #
# Lo leído
# --------------------------------------------------------------------------- #


def test_the_read_statuses_are_the_ones_the_roadmap_published() -> None:
    statuses = nasa_framework.gap_statuses()
    assert statuses["Med07"] == "closed"
    assert statuses["Med10"] == "merged"
    assert statuses["Medical-701"] == "open"
    assert statuses["FN-205"] == "archived"
    assert {statuses[f"Food-0{n}"] for n in range(1, 5)} == {"split"}


def test_each_status_comes_from_its_roadmap_page() -> None:
    for gap in nasa_framework.gap_statuses():
        status = nasa_framework.gap_status(gap)
        assert status["url"].startswith("https://humanresearchroadmap.nasa.gov/Gaps/gap.aspx?i=")
        assert status["read_on"] == nasa_framework.read()["read_on"]
        assert status["status_text"] == nasa_framework.GAP_STATUSES[status["status"]]


def test_a_gap_without_read_status_is_not_served_as_if_open() -> None:
    with pytest.raises(nasa_framework.FrameworkError, match="no hay estado leído"):
        nasa_framework.gap_status("Med99")


# --------------------------------------------------------------------------- #
# Las reglas, contra textos escritos a propósito
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text", [
    "Huecos de NASA que EMMA aborda: Med 07 y Med 10.",
    "EMMA cierra el hueco Med07.",
    "El hueco Med 10 sigue abierto y EMMA lo cubre.",
    "FN-205 (fatiga de menú) es un hueco vigente.",
    "Food-01 está pendiente.",
])
def test_rule_one_catches_a_gap_presented_as_open(text: str) -> None:
    assert _presents_as_open(text)


@pytest.mark.parametrize("text", [
    "Med07 está cerrado y Med10 se fusionó en Medical-701, que sigue abierto.",
    "EMMA no aborda FN-205, que figura archivado.",
])
def test_rule_one_lets_through_the_status_as_read(text: str) -> None:
    assert not _presents_as_open(text)


def test_rule_two_catches_a_gap_named_without_its_status() -> None:
    assert _silent_about_status("EMMA responde a la pregunta de Med 07.") == ["Med07"]
    assert not _silent_about_status("Med 07, hoy cerrado, preguntaba otra cosa.")


# --------------------------------------------------------------------------- #
# Lo que EMMA sirve y escribe
# --------------------------------------------------------------------------- #


def test_the_framework_route_does_not_present_a_closed_gap_as_open(client: TestClient) -> None:
    body = client.get("/api/framework").json()
    # Regla 1: todo lo servido, menos las frases de NASA.
    offending = [
        hit for text in _strings(body, skip=frozenset({"quote"})) for hit in _presents_as_open(text)
    ]
    assert offending == []
    # Regla 2: los textos propios de EMMA fuera de lo leído, uno a uno; cada hueco de
    # `exmc_gaps` como una unidad, porque su nombre y su estado viajan en campos hermanos.
    gap_rows = [body["exmc_gaps"][key] for key in ("med07", "med10")]
    units = [json.dumps(row, ensure_ascii=False) for row in gap_rows]
    rest = {key: value for key, value in body.items() if key not in ("read_sources", "exmc_gaps")}
    units += [*_strings(rest), body["exmc_gaps"]["note"], body["exmc_gaps"]["source"]]
    silent = [(text, gaps) for text in units if (gaps := _silent_about_status(text))]
    assert silent == []
    # Lo leído, por bloque: el estado va en la etiqueta de la frase que lo da.
    for block in body["read_sources"]["blocks"]:
        assert _silent_about_status(json.dumps(block, ensure_ascii=False)) == [], block["id"]


def test_each_exmc_gap_is_served_with_its_read_status(client: TestClient) -> None:
    gaps = client.get("/api/framework").json()["exmc_gaps"]
    assert gaps["med07"]["status"] == nasa_framework.gap_status("Med07")
    assert gaps["med10"]["status"] == nasa_framework.gap_status("Med10")
    assert gaps["med10"]["merged_into"] == nasa_framework.gap_status("Medical-701")
    for key in ("med07", "med10"):
        assert gaps[key]["status"]["status"] != "open"
        # El enunciado de 2020 sigue siendo el de la fuente: se fecha, no se reescribe.
        assert gaps[key]["gap"].startswith("We do not have the capability")
    assert "2020" in gaps["note"] and "no figuran como huecos abiertos" in gaps["note"]


@pytest.mark.parametrize("path", [
    BACKEND / "app" / "data" / "design_hypotheses.json",
    BACKEND / "app" / "data" / "evidence_refs.json",
    SOURCES_READ,
])
def test_the_data_files_do_not_present_a_closed_gap_as_open(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    offending = [
        hit for text in _strings(data, skip=frozenset({"quote"})) for hit in _presents_as_open(text)
    ]
    assert offending == []


def test_the_hypotheses_name_each_gap_with_its_status() -> None:
    data = json.loads((BACKEND / "app" / "data" / "design_hypotheses.json").read_text("utf-8"))
    silent = [(text, gaps) for text in _strings(data) if (gaps := _silent_about_status(text))]
    assert silent == []


def test_the_rationale_does_not_present_a_closed_gap_as_open() -> None:
    for section in _markdown_sections(ROOT / "compliance" / "clinical-decision-rationale.md"):
        assert _presents_as_open(section) == []
        assert _silent_about_status(section) == [], section[:80]


@pytest.mark.parametrize("name", ["framework.ts", "FrameworkPanel.tsx"])
def test_the_ground_console_does_not_name_a_gap_on_its_own(name: str) -> None:
    """La consola no escribe el nombre de un hueco: lo toma del backend, con su estado."""
    text = (ROOT / "frontend" / "src" / "ground" / name).read_text(encoding="utf-8")
    assert _presents_as_open(text) == []
    assert _silent_about_status(text) == []
