"""Las fuentes del contexto del equipo y el enunciado del reto: `GET /api/context-sources`.

Lo que vigilan estas pruebas es que EMMA no diga del reto más de lo que se leyó. El enunciado se
leyó el 2026-10-31 (decimonovena ronda, U2), en la dirección donde el sitio lo sirve y no en la de
la especificación §17, que sigue dando su página de error: la ficha conserva la de §17 y dice dónde
está; lleva la fecha y la organización leídas en la página; y la tabla de
`compliance/challenge-coverage.md` cita cada frase del enunciado en su fila, con su cobertura, y
cuenta las filas en una línea que estas pruebas recomputan. Cada fuente de las listas del equipo
usa la dirección exacta de §17; lo no leído dice por qué; una fuente leída otro día que el fichero
lo dice con su fecha, y esa fecha está en su ficha; y lo que la tabla nombra existe. **Ninguna
prueba sale a la red**: las lecturas se hicieron el 2026-10-26 y el 2026-10-31.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence import context_sources, registry
from app.evidence.context_sources import ContextSourcesError
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "contexto" / "especificacion-tecnica-v1.1.md"
KB = ROOT / "docs" / "contexto" / "knowledge-base-v1.md"
COVERAGE = ROOT / "compliance" / "challenge-coverage.md"
CHALLENGE = "space-apps-2026-health-monitoring-challenge"
READ_ON = "2026-10-26"
# El enunciado se leyó cinco días después que el resto, en la dirección que el sitio sirve.
CHALLENGE_READ_ON = "2026-10-31"
CHALLENGE_SERVED_AT = (
    "https://www.spaceappschallenge.org/2026/challenges/health-monitoring-software/"
)
COVERAGE_WORDS = ("**sí**", "**en parte**", "**no**", "**pendiente**", "**del equipo**")
# Las clases que la conversación de ideación pide para los recursos del reto.
RESOURCE_CLASSES = ("Health", "Biology", "Environment", "Mission", "Space Weather", "Software")
NO_RESOURCES_YET = "Resources will be available on Friday, November 13."

# Direcciones de la especificación §17 que siguen sin ficha. Tras la decimoséptima ronda (U8)
# quedaban seis; la decimoctava (U19) las leyó todas, ZeroKeyUSB incluido (se sirve sin navegador).
# Solo puede encoger: una dirección nueva en §17 sin ficha hace fallar la prueba.
STILL_WITHOUT_CARD: set[str] = set()
# Las seis fichas de esa lectura (decimoctava ronda, U19), en el orden de §17.
U19_CARDS = (
    "nasa-hrp-roi", "nasa-iss-astronaut-record-holders", "astroquery-docs",
    "nasa-std-3001-appendix-e", "beyondtheprotocol-polaris", "bonilista-zerokeyusb",
)
FOOD = "hrp-food-system-evidence-report"
HACCP = (
    "Similarly, the need to ensure food safety through mission critical, medically limited "
    "situations drove the development of the Hazard Analysis Critical Control Point (HACCP) system "
    "by NASA, U.S. Army Natick Soldier Research, Development & Engineering Center (NSRDEC), and "
    "Pillsbury. HACCP has since improved food safety throughout food industry (Heidelbaugh 1966)."
)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


@pytest.fixture
def raw() -> dict[str, Any]:
    """Una copia del fichero, para estropearla sin tocar la que está en caché."""
    return copy.deepcopy(json.loads(context_sources.CONTEXT_SOURCES_PATH.read_text("utf-8")))


def _spec_17() -> str:
    return SPEC.read_text(encoding="utf-8").split("# 17. URLs de las fuentes", 1)[1]


def _source(raw: dict[str, Any], ref: str) -> dict[str, Any]:
    return next(item for item in raw["sources"] if item["ref"] == ref)


# --------------------------------------------------------------------------- #
# Lo leído y lo no leído
# --------------------------------------------------------------------------- #


def test_every_listed_source_uses_the_exact_address_and_label_of_the_specification() -> None:
    spec = _spec_17()
    lines = [line for line in spec.splitlines() if line.startswith("- ")]
    for item in context_sources.read()["sources"]:
        ref = registry.get(item["ref"])
        if "spec-17" not in item["lists"]:
            continue
        line = next((line for line in lines if ref.url is not None and ref.url in line), None)
        assert line is not None, f"{ref.id}: su dirección no es la de la especificación §17"
        assert line == f"- {item['listed_as']}{ref.url}", ref.id


def test_the_two_x_posts_are_the_ones_the_knowledge_base_left_pending() -> None:
    kb = KB.read_text(encoding="utf-8")
    assert "## 11.3 Referencias X / enlaces no recuperables" in kb
    posts = [item for item in context_sources.read()["sources"] if "kb-11-3" in item["lists"]]
    assert len(posts) == 2
    for item in posts:
        ref = registry.get(item["ref"])
        assert ref.url is not None and ref.url.startswith("https://x.com/")
        assert "§11.3" in (ref.notes or "")


def test_the_challenge_statement_is_read_on_its_own_day_and_says_what_was_not() -> None:
    item = _source(context_sources.read(), CHALLENGE)
    # Leído en parte: el texto entero, no el vídeo ni los recursos (que no están publicados).
    assert item["status"] == "partial" and item["read_on"] == CHALLENGE_READ_ON
    said = item["not_read"]
    for phrase in ("no se ha visto", NO_RESOURCES_YET, "Teams"):
        assert phrase in said, phrase
    ref = registry.get(CHALLENGE)
    # Fecha y organización leídas en la página: ya no queda nada por verificar.
    assert ref.date == "2026-10-29" and ref.organization == "NASA Space Apps Challenge"
    assert ref.unverified == ()
    notes = ref.notes or ""
    # La ficha conserva la dirección de §17 (la que el equipo listó) y dice dónde se sirve de verdad
    # y qué devuelve la otra.
    assert ref.url is not None and ref.url in _spec_17() and ref.url != CHALLENGE_SERVED_AT
    assert CHALLENGE_SERVED_AT in notes and "Oops! Page Not Found" in notes
    for word in (CHALLENGE_READ_ON, "Intermediate", "firstPublishedAt", "lastPublishedAt"):
        assert word in notes, word
    # La lectura del día del fichero no está en la ficha: vale la fecha propia, no la del fichero.
    assert READ_ON not in notes
    # El calendario que explicó el 404 del día 26 sigue en las preguntas frecuentes, con su fecha.
    faqs = registry.get("space-apps-2026-participant-faqs")
    assert "October 28: Challenge Statements available." in (faqs.notes or "")
    assert READ_ON in (faqs.notes or "")


def test_what_was_read_in_part_says_what_was_not() -> None:
    for item in context_sources.read()["sources"]:
        if item["status"] == "read":
            assert item["not_read"] is None, item["ref"]
        else:
            assert item["not_read"], item["ref"]
    # Los dos vídeos no se vieron: ni la ficha ni el inventario dicen lo que enseñan.
    for ref_id in ("nasa-iss-humanity-lab-video", "x-israeldfirzt-protoclone"):
        assert _source(context_sources.read(), ref_id)["status"] == "partial"
        assert "no se ha visto" in (registry.get(ref_id).notes or "")


def test_a_kind_no_class_covers_is_declared_not_forced() -> None:
    """Un vídeo, una publicación en X o una página no oficial no son «página de agencia»."""
    for ref_id in (
        "estacionespacial-columbus", "naukas-stuhlinger-letter", "nasa-iss-humanity-lab-video",
        "x-miriamgonp-liver-render", "x-israeldfirzt-protoclone",
    ):
        ref = registry.get(ref_id)
        assert ref.evidence_type is None and ref.outside_enum == ("evidence_type",), ref_id
        assert "fuera del enumerado" in (ref.notes or ""), ref_id


def test_the_post_about_the_liver_render_keeps_no_clinical_data() -> None:
    notes = registry.get("x-miriamgonp-liver-render").notes or ""
    assert "EMMA no recoge sus datos clínicos" in notes
    # Ni medidas, ni recuentos, ni diagnóstico, ni fechas de pruebas: solo lo que toca al visor.
    assert not re.search(r"\d+\s*mm|\blesion|\bcáncer|\bmetást|\bbiops", notes, re.IGNORECASE)
    assert "todavía no las ha validado nadie" in notes


def test_the_specification_addresses_without_a_card_can_only_shrink() -> None:
    urls = set(re.findall(r"https://\S+", _spec_17()))
    known = {ref.url for ref in registry.registry().values()}
    # Igualdad, no inclusión: una ficha nueva con una de estas direcciones obliga a sacarla de la
    # lista en el mismo cambio.
    assert urls - known == STILL_WITHOUT_CARD


def test_the_six_addresses_left_are_read_and_listed_with_their_card() -> None:
    raw = context_sources.read()
    for ref_id in U19_CARDS:
        assert _source(raw, ref_id)["lists"] == ["spec-17"], ref_id
        notes = registry.get(ref_id).notes or ""
        assert "decimoctava ronda, U19" in notes and READ_ON in notes, ref_id
        # Ninguna es un estudio: ninguna dice haber medido a nadie.
        assert registry.get(ref_id).population is None, ref_id


def test_astroquery_and_zerokeyusb_are_registered_not_adopted() -> None:
    raw = context_sources.read()
    for ref_id in ("astroquery-docs", "bonilista-zerokeyusb"):
        assert _source(raw, ref_id)["emma_use"].startswith("No se adopta"), ref_id
    # La mina de CLAUDE.md, con sus palabras: solo el tiempo de luz, y no es un backend de salud.
    astro = _source(raw, "astroquery-docs")["emma_use"]
    assert "astroquery.jplhorizons" in astro and "tiempo de luz" in astro
    assert "No es un backend de salud" in astro
    assert "EMMA no adopta nada de ZeroKeyUSB" in (registry.get("bonilista-zerokeyusb").notes or "")


def test_the_polaris_card_names_the_commit_emma_copied() -> None:
    adopted = (ROOT / "polaris" / "ADOPTADO.txt").read_text(encoding="utf-8")
    commit = re.search(r"^commit ([0-9a-f]{40})$", adopted, re.MULTILINE)
    assert commit is not None
    notes = registry.get("beyondtheprotocol-polaris").notes or ""
    # La portada leída es de otro commit: la ficha lo dice en vez de darlos por iguales.
    assert commit.group(1) in notes and "no del que se leyó" in notes


def test_the_haccp_sentence_is_copied_from_the_food_report_next_to_stuhlinger() -> None:
    raw = context_sources.read()
    assert HACCP in _source(raw, FOOD)["emma_use"]
    assert HACCP in (registry.get(FOOD).notes or "")
    assert "HACCP" in _source(raw, "naukas-stuhlinger-letter")["emma_use"]


def test_the_miniaturized_care_sentence_is_declared_not_found_not_repeated() -> None:
    item = _source(context_sources.read(), "nasa-iss-humanity-lab-video")
    said = item["not_read"]
    assert "no está en ninguno" in said and "EMMA no repite la frase" in said
    # Lo más cercano se da con su frase y se dice que no es la misma afirmación.
    assert "que no es la misma afirmación" in said


# --------------------------------------------------------------------------- #
# La tabla del reto
# --------------------------------------------------------------------------- #


def test_every_file_and_card_the_coverage_table_names_exists() -> None:
    text = COVERAGE.read_text(encoding="utf-8")
    named = re.findall(r"`([^`\s]+)`", text)
    paths = [name for name in named if "/" in name and not name.startswith("/")]
    assert paths
    for name in paths:
        assert (ROOT / name).exists(), name
    cards = [name for name in named if name in registry.registry()]
    assert {CHALLENGE, "nasa-space-apps-2026-announcement",
            "space-apps-2026-participant-faqs"} <= set(cards)


_SEPARATOR = re.compile(r"^\|\s*:?-+")


def _cells(row: str) -> list[str]:
    """Las celdas de una fila, con o sin barra final."""
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _tables(text: str) -> list[list[list[str]]]:
    """Las tablas del documento: cada una, sus filas ya partidas en celdas (cabecera incluida, sin
    la de guiones). Lo que va dentro de un bloque de código no es una tabla."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if not fenced and line.startswith("|"):
            if _SEPARATOR.match(line) is None:
                current.append(_cells(line))
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def test_every_row_of_a_what_it_says_table_ends_with_its_coverage() -> None:
    text = COVERAGE.read_text(encoding="utf-8")
    graded = [table for table in _tables(text) if table[0][0].startswith("Lo que dice")]
    # El enunciado, lo leído de NASA sobre el concurso y la interpretación del equipo.
    assert len(graded) == 3
    for table in graded:
        assert len(table) > 1
        width = len(table[0])
        for row in table[1:]:
            assert len(row) == width, row
            # La cobertura va en la última celda.
            assert any(word in row[-1] for word in COVERAGE_WORDS), row
    # La interpretación del equipo se presenta como tal, no como el enunciado.
    assert "la interpretación del equipo" in text.lower()


def test_the_statement_table_quotes_each_sentence_and_its_counts_match_the_summary() -> None:
    text = COVERAGE.read_text(encoding="utf-8")
    statement = next(
        table for table in _tables(text) if table[0][0].startswith("Lo que dice el enunciado")
    )
    rows = statement[1:]
    # Cada fila cita el enunciado entre comillas angulares: no se parafrasea lo que pide.
    for row in rows:
        assert "«" in row[0] and "»" in row[0], row
    counts = {word: sum(word in row[-1] for row in rows) for word in COVERAGE_WORDS}
    # El enunciado no trae reglas del concurso: nada suyo es «del equipo».
    assert counts["**del equipo**"] == 0
    summary = re.search(
        r"Cobertura del enunciado: (\d+) filas — (\d+) sí, (\d+) en parte, (\d+) no, "
        r"(\d+) pendiente",
        text,
    )
    assert summary is not None, "falta la línea de recuento"
    assert [int(group) for group in summary.groups()] == [
        len(rows), counts["**sí**"], counts["**en parte**"], counts["**no**"],
        counts["**pendiente**"],
    ]
    # Lo que EMMA tiene a medias se dice, no se calla: la gamificación son solo las rachas
    # (2026-11-02), así que su fila queda «en parte» y no «sí».
    assert any("gamification" in row[0] and "**en parte**" in row[-1] for row in rows)
    # Dónde se sirve el enunciado y cuándo se leyó, en el documento.
    assert CHALLENGE_SERVED_AT in text and CHALLENGE_READ_ON in text


def test_the_resources_table_classifies_each_resource_or_says_none_is_published() -> None:
    text = COVERAGE.read_text(encoding="utf-8")
    table = next(table for table in _tables(text) if table[0][0].startswith("Recurso"))
    rows = table[1:]
    assert rows
    for row in rows:
        if "ninguno" in row[0]:
            # Mientras la pestaña no enlace nada, la fila lo dice con la frase de la pestaña.
            assert NO_RESOURCES_YET in row[-1], row
            continue
        # Un recurso publicado va en una de las seis clases de la conversación de ideación.
        assert any(cls in row[1] for cls in RESOURCE_CLASSES), row


# --------------------------------------------------------------------------- #
# El contrato del inventario
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda s: s.update(ref="no-existe"), "no está en el registro"),
        (lambda s: s.update(not_read=None), "por qué"),
        (lambda s: s.update(status="leido"), "estado desconocido"),
        (lambda s: s.update(listed_as=None), "rótulo"),
        (lambda s: s.update(why_added="porque sí"), "rótulo"),
        (lambda s: s.update(lists=["otra"]), "listas desconocidas"),
        (lambda s: s.update(emma_use=" "), "para qué"),
        (lambda s: s.update(extra=1), "campos desconocidos"),
    ],
)
def test_the_inventory_rejects_what_breaks_its_contract(
    raw: dict[str, Any], change: Any, reason: str
) -> None:
    change(_source(raw, CHALLENGE))
    with pytest.raises(ContextSourcesError, match=reason):
        context_sources.validate(raw)


def test_a_source_outside_the_lists_says_why_it_was_added(raw: dict[str, Any]) -> None:
    item = _source(raw, "nasa-space-apps-2026-announcement")
    item["why_added"] = None
    with pytest.raises(ContextSourcesError, match="motivo"):
        context_sources.validate(raw)


@pytest.mark.parametrize("reason", ["no", "", " "])
def test_a_read_source_does_not_carry_a_reason_for_not_reading(
    raw: dict[str, Any], reason: str
) -> None:
    """Ni un motivo, ni uno vacío: lo leído entero lleva `null`."""
    _source(raw, "nasa-living-in-space")["not_read"] = reason
    with pytest.raises(ContextSourcesError, match="lo leído entero"):
        context_sources.validate(raw)


def test_a_source_not_read_with_an_empty_reason_is_rejected(raw: dict[str, Any]) -> None:
    _source(raw, CHALLENGE)["not_read"] = "  "
    with pytest.raises(ContextSourcesError, match="dice por qué"):
        context_sources.validate(raw)


def test_a_repeated_source_or_list_is_rejected(raw: dict[str, Any]) -> None:
    twice = copy.deepcopy(raw)
    twice["sources"].append(copy.deepcopy(twice["sources"][0]))
    with pytest.raises(ContextSourcesError, match="fuente repetida"):
        context_sources.validate(twice)
    _source(raw, "x-miriamgonp-liver-render")["lists"] = ["spec-17", "spec-17"]
    with pytest.raises(ContextSourcesError, match="lista repetida"):
        context_sources.validate(raw)


def test_a_card_that_does_not_say_it_was_read_that_day_is_rejected(raw: dict[str, Any]) -> None:
    raw["read_on"] = "2026-10-27"
    with pytest.raises(ContextSourcesError, match="2026-10-27"):
        context_sources.validate(raw)


def test_a_reading_without_a_date_is_rejected(raw: dict[str, Any]) -> None:
    raw["read_on"] = " "
    with pytest.raises(ContextSourcesError, match="read_on"):
        context_sources.validate(raw)


def test_a_source_read_another_day_needs_that_day_in_its_card(raw: dict[str, Any]) -> None:
    # Un día en que no se leyó: la ficha no lo tiene y el error lo nombra.
    _source(raw, CHALLENGE)["read_on"] = "2026-10-30"
    with pytest.raises(ContextSourcesError, match="2026-10-30"):
        context_sources.validate(raw)


def test_without_its_own_day_a_source_falls_back_to_the_file_date(raw: dict[str, Any]) -> None:
    """La ficha del enunciado no dice nada del 2026-10-26: sin su fecha propia no pasa."""
    _source(raw, CHALLENGE)["read_on"] = None
    with pytest.raises(ContextSourcesError, match=READ_ON):
        context_sources.validate(raw)


@pytest.mark.parametrize("day", ["31 de octubre", "", "2026-10", 20261031, "2026-13-45"])
def test_a_source_day_that_is_not_a_real_full_iso_date_is_rejected(
    raw: dict[str, Any], day: Any
) -> None:
    """Ni otra forma, ni la forma correcta de un día que no existe."""
    _source(raw, "nasa-living-in-space")["read_on"] = day
    with pytest.raises(ContextSourcesError, match="ISO 8601"):
        context_sources.validate(raw)


@pytest.mark.parametrize("day", ["26 de octubre", "2026-02-30", 20261026])
def test_the_file_date_is_checked_as_a_date_the_same_way(raw: dict[str, Any], day: Any) -> None:
    """La del fichero es la que más se sirve: no se vigila menos que la propia de una fuente."""
    raw["read_on"] = day
    with pytest.raises(ContextSourcesError, match="ISO 8601"):
        context_sources.validate(raw)


def test_an_inventory_without_the_challenge_statement_is_not_served(raw: dict[str, Any]) -> None:
    raw["sources"] = [item for item in raw["sources"] if item["ref"] != CHALLENGE]
    with pytest.raises(ContextSourcesError, match="enunciado"):
        context_sources.validate(raw)


# --------------------------------------------------------------------------- #
# La ruta
# --------------------------------------------------------------------------- #


def test_the_route_serves_each_source_with_its_card_offline(client: TestClient) -> None:
    body = client.get("/api/context-sources").json()
    assert body["read_on"] == READ_ON
    assert {item["ref"] for item in body["sources"]} == context_sources.cited_refs()
    for item in body["sources"]:
        assert item["status_text"] == context_sources.STATUSES[item["status"]]
        card = item["card"]
        assert card["id"] == item["ref"]
        assert card == registry.get(item["ref"]).to_dict()
    # Cada fuente sirve el día en que se leyó: el suyo si lo trae, el del fichero si no.
    for item in body["sources"]:
        expected = CHALLENGE_READ_ON if item["ref"] == CHALLENGE else READ_ON
        assert item["read_on"] == expected, item["ref"]
    challenge = next(item for item in body["sources"] if item["ref"] == CHALLENGE)
    assert challenge["status_text"] == "leída en parte"
    assert challenge["card"]["unverified"] == []
    assert challenge["card"]["date"] == "2026-10-29"
    # La nota toma del inventario el día en que se leyó el enunciado: no lo lleva escrito a mano.
    assert f"se leyó el {CHALLENGE_READ_ON}" in body["note"] and READ_ON not in body["note"]
