"""El inglés de la anatomía, del dolor referido y de los protocolos ecográficos (unidad 17).

Por qué existe: estas frases las escribe el backend y la interfaz las enseña tal cual. Con dos
idiomas, lo que puede romperse sin que nadie lo vea es que una frase nueva se quede sin inglés,
que el inglés diga más que el castellano, que una clave firmada salga traducida o que el
castellano de siempre cambie al pedirlo sin cabecera. Aquí se pide lo mismo en los dos idiomas y
se comparan: el texto cambia, los identificadores no, y lo firmado es idéntico. Sin red.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import anatomy, pain_on_skeleton
from app.api.routes import get_store, new_store, reset_store
from app.core import i18n
from app.core.config import Settings, get_settings
from app.core.ledger import SALT_FIELD
from app.imaging import protocols
from app.main import app
from app.pain import alarm
from app.pain.catalog import CHARACTERS, MAX_INTENSITY, ZONES
from tests.conftest import ENGLISH_HEADERS

# Nada que suene a certificación, a diagnóstico o a orden médica (CLAUDE.md, invariantes 6 y 7).
FORBIDDEN = re.compile(r"certified|validated|diagnos|administer|must take", re.IGNORECASE)
SPANISH_ONLY = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
WHEN = "2026-09-25T08:00:00+00:00"
CHEST = {"zone": "chest", "intensity": 4, "characters": ["pressing"]}
KNEE = {"zone": "knee-left", "intensity": 3, "characters": ["sharp", "tingling"]}


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """Un registro con pocos días de lecturas, sembrado una vez: las pruebas solo leen."""
    cache_dir: Path = tmp_path_factory.mktemp("anatomy-en")
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=cache_dir, offline=True, assistant_warmup=False
    )
    client = TestClient(app)
    loaded = client.post("/api/simulate", params={"scenario": "nominal", "days": 10, "seed": 7})
    assert loaded.status_code == 201, loaded.text
    yield client
    app.dependency_overrides.clear()
    reset_store(None)


def _both(client: TestClient, path: str) -> tuple[Any, Any]:
    spanish = client.get(path)
    english = client.get(path, headers=ENGLISH_HEADERS)
    assert spanish.status_code == 200 and english.status_code == 200, english.text
    return spanish.json(), english.json()


def _pain_names() -> dict[str, str]:
    names = [*(zone.display for zone in ZONES.values()), *(c.display for c in CHARACTERS.values())]
    with i18n.use("en"):
        return {name: i18n.loc(name) for name in names}


def _alarm_phrases() -> set[str]:
    """Toda frase que `alarm.describe` puede componer, más la del hormigueo de un lado."""
    phrases = {"hormigueo de un lado"}
    for zone in ZONES:
        for intensity in range(1, MAX_INTENSITY + 1):
            for kinds in ([], list(CHARACTERS)):
                phrases.update(alarm.describe(zone, intensity, kinds))
    return phrases


def _skeleton_sentences() -> list[str]:
    return [
        pain_on_skeleton.TOO_FEW_ANCHORS, pain_on_skeleton.NO_FIT, pain_on_skeleton.FLIPPED,
        pain_on_skeleton.BAD_FIT, pain_on_skeleton.BONE_NOT_IN_STUDY,
        pain_on_skeleton.OFF_THE_IMAGE,
    ]


def _protocol_texts(protocol: protocols.Protocol) -> list[str]:
    found = [protocol.display, protocol.rationale, *protocol.checklist, *protocol.sources]
    for view in protocol.views:
        found.append(view.display)
        for sign in view.signs:
            found.extend([sign.display, *sign.values.values()])
    return found


# --------------------------------------------------------------------------- #
# Cobertura: nada de lo que se enseña se queda sin inglés
# --------------------------------------------------------------------------- #


def test_every_region_sentence_has_its_english() -> None:
    missing: list[str] = []
    for region in anatomy.REGIONS:
        texts = [region.display, region.note, region.function, region.function_note]
        cited = [*region.note_refs, *region.function_refs, region.analytes_source,
                 region.research_facility, *(item.citation for item in region.research_refs)]
        texts.extend(item.relevance for item in cited if item is not None)
        texts.extend(item.population for item in region.research_refs)
        missing.extend(text for text in texts if text is not None and text not in anatomy.ENGLISH)
    assert missing == []


def test_every_sentence_constant_of_the_chain_has_its_english() -> None:
    """Las frases sueltas del módulo (notas, bases, rótulos del esqueleto): toda constante de
    texto en mayúsculas que lleve una frase castellana, salvo las que no son texto que se lea."""
    not_sentences = {
        "CUMULATIVE_DOSE", "NO_OWN", "OWN_UNUSABLE", "REFERENCE", "OWN_CT",
        # La atribución de BodyParts3D es su licencia, en inglés ya.
        "SKELETON_ATTRIBUTION",
        # Se sirve ya compuesta con la atribución, y así está registrada.
        "REFERENCE_CAPTION",
    }
    constants = {
        name: value for name, value in vars(anatomy).items()
        if name.isupper() and isinstance(value, str) and name not in not_sentences
    }
    assert len(constants) > 25
    assert [name for name, value in constants.items() if value not in anatomy.ENGLISH] == []
    caption = anatomy.REFERENCE_CAPTION.format(attribution=anatomy.SKELETON_ATTRIBUTION)
    assert caption in anatomy.ENGLISH


def test_every_pain_name_and_flag_phrase_has_its_english() -> None:
    names = _pain_names()
    assert [name for name, english in names.items() if english == name
            and name not in ("Abdomen", "Pelvis")] == []
    with i18n.use("en"):
        assert [phrase for phrase in sorted(_alarm_phrases()) if i18n.loc(phrase) == phrase] == []
        assert i18n.loc(alarm.DISCUSS_NOTE) != alarm.DISCUSS_NOTE
        assert [text for text in _skeleton_sentences() if i18n.loc(text) == text] == []


def test_every_protocol_text_has_its_english() -> None:
    missing = [
        text for protocol in protocols.PROTOCOLS.values() for text in _protocol_texts(protocol)
        # Las fuentes que ya son una cita en inglés se quedan como están.
        if text not in protocols.ENGLISH and SPANISH_ONLY.search(text)
    ]
    assert missing == []
    spanish_words = re.compile(r"\b(de|del|la|el|en|con|sin|por|tras)\b")
    untranslated = [
        text for protocol in protocols.PROTOCOLS.values() for text in _protocol_texts(protocol)
        if text not in protocols.ENGLISH and spanish_words.search(text)
    ]
    assert untranslated == []


def test_the_english_says_no_more_than_the_spanish() -> None:
    english = [
        *anatomy.ENGLISH.values(), *protocols.ENGLISH.values(), *_pain_names().values(),
    ]
    with i18n.use("en"):
        english.extend(i18n.loc(phrase) for phrase in _alarm_phrases())
        english.extend(i18n.loc(text) for text in _skeleton_sentences())
        english.append(i18n.loc(alarm.DISCUSS_NOTE))
        english.extend(anatomy._milestone_display(*case) for case in ((None, 1200), (7, 7), (7, 3)))
        english.extend(
            anatomy._preflight_display(*case) for case in ((90, 90), (180, 200), (90, 120))
        )
    assert len(english) > 150
    assert [text for text in english if FORBIDDEN.search(text)] == []
    assert [text for text in english if SPANISH_ONLY.search(text)] == []
    # Los huecos de las plantillas son los mismos en los dos idiomas.
    holes = re.compile(r"\{(\w+)\}")
    for spanish, text in {**anatomy.ENGLISH, **protocols.ENGLISH}.items():
        assert sorted(holes.findall(spanish)) == sorted(holes.findall(text)), spanish


def test_a_source_quoted_verbatim_stays_as_the_source_wrote_it() -> None:
    quote = re.compile(r"«([^»]*)»")
    for spanish, english in anatomy.ENGLISH.items():
        for quoted in quote.findall(spanish):
            # Las citas en inglés de una fuente pasan iguales; los nombres propios, también.
            if not SPANISH_ONLY.search(quoted) and " " in quoted and quoted[0] != "{":
                assert quoted in english or quoted.lower().startswith(("una ", "un ")), spanish


# --------------------------------------------------------------------------- #
# El mapa y la cadena de cada región
# --------------------------------------------------------------------------- #


def test_the_map_reads_in_english_and_keeps_its_identifiers(seeded: TestClient) -> None:
    spanish, english = _both(seeded, "/api/anatomy")
    # Sin cabecera sale lo de siempre: lo que el módulo compone en castellano, tal cual.
    assert spanish["regions"] == [
        {**region._fields(), **region._function_fields()} for region in anatomy.REGIONS
    ]
    by_key = {item["key"]: item for item in english["regions"]}
    assert by_key["brain"]["display"] == "Brain: sleep, vigilance, mood"
    assert by_key["liver"]["level_note"].startswith("The level is that of the ")
    assert by_key["whole-body"]["function_note"].startswith("It is not an organ or a body system")
    assert by_key["bladder"]["note_refs"][0]["relevance"].startswith("why fluid intake and urine")
    for before, after in zip(spanish["regions"], english["regions"], strict=True):
        for field in ("key", "domains", "analytes", "level_of"):
            assert after[field] == before[field]
        for field in ("display", "note"):
            assert after[field] == anatomy.ENGLISH[before[field]]
        assert not SPANISH_ONLY.search(after["display"] + after["note"])
        if before["function"] is not None:
            assert after["function"] == anatomy.ENGLISH[before["function"]]
        # La ficha es la misma; solo la relevancia, que es de quien cita, cambia de idioma.
        for cited_es, cited_en in zip(
            [*before["note_refs"], *before["function_refs"]],
            [*after["note_refs"], *after["function_refs"]], strict=True,
        ):
            assert cited_en["id"] == cited_es["id"] and cited_en["url"] == cited_es["url"]
            assert cited_en["relevance"] == anatomy.ENGLISH[cited_es["relevance"]]


def test_the_chain_reads_in_english_and_assesses_the_same(seeded: TestClient) -> None:
    spanish, english = _both(seeded, "/api/anatomy/state")
    assert spanish["rules_version"] == english["rules_version"]
    for before, after in zip(spanish["regions"], english["regions"], strict=True):
        assert before == {**before, **anatomy.REGIONS[spanish["regions"].index(before)].to_dict()}
        for field in ("key", "level", "has_data", "domains"):
            assert after[field] == before[field]
        assert [item["key"] for item in after["variables"]] == [
            item["key"] for item in before["variables"]
        ]
        assert [item["value"] for item in after["variables"]] == [
            item["value"] for item in before["variables"]
        ]
        for field in ("data_note", "recommendations_note"):
            if before[field] is not None:
                assert after[field] != before[field] and not FORBIDDEN.search(after[field])
    liver = next(item for item in english["regions"] if item["key"] == "liver")
    assert liver["recommendations_note"].startswith("No countermeasures of its own: those of the ")
    research = liver["research"]
    assert research["note"] == anatomy.ENGLISH[anatomy.RESEARCH_NOTE]
    assert research["items"][0]["population_label"].startswith("humans and animal model: ")
    assert research["items"][0]["id"] == "hayslip-2026"
    brain = next(item for item in english["regions"] if item["key"] == "brain")
    assert brain["research"]["facility"]["note"].startswith("Where part of that research is done")
    # Y en castellano, la capa de investigación de siempre.
    liver_es = next(item for item in spanish["regions"] if item["key"] == "liver")
    assert liver_es["research"]["note"] == anatomy.RESEARCH_NOTE
    assert liver_es["research"]["items"][0]["population_label"].startswith(
        "humanos y modelo animal: "
    )
    assert english["moments"]["current_display"] == "Now: last recorded reading"
    assert spanish["moments"]["current_display"] == anatomy.CURRENT_MOMENT
    assert [item["key"] for item in english["moments"]["items"]] == [
        item["key"] for item in spanish["moments"]["items"]
    ]
    for source in english["moments"]["postflight_milestones"]["sources"]:
        assert source["scope"] in anatomy.ENGLISH.values()
        assert source["source"]["relevance"].startswith("when NASA ")


def test_milestone_labels_follow_the_language() -> None:
    assert anatomy._milestone_display(7, 3) == "Tramo de R+2 a R+7: última lectura, en R+3"
    assert anatomy._preflight_display(180, 200) == "Hasta L-180: última lectura, en L-200"
    past = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
    spanish = anatomy.moment(past)
    assert spanish is not None and spanish["label"] == anatomy.MOMENT_LABEL
    with i18n.use("en"):
        assert anatomy._milestone_display(7, 3) == "Span from R+2 to R+7: last reading, at R+3"
        assert anatomy._milestone_display(7, 7) == "R+7: last reading of that day"
        assert anatomy._milestone_display(None, 1200) == "After R+1095: last reading, at R+1200"
        assert anatomy._preflight_display(90, 90) == "L-90: last reading of that day"
        assert anatomy._preflight_display(180, 200) == "Up to L-180: last reading, at L-200"
        assert anatomy._preflight_display(90, 120) == (
            "Span from L-179 to L-90: last reading, at L-120"
        )
        english = anatomy.moment(past)
    assert english is not None
    assert english["until"] == spanish["until"]
    assert english["label"] == "Recomputed with today's rules, with no ledger entry"
    assert english["basis"][1] == anatomy.ENGLISH[anatomy.MOMENT_EXTERNAL_BASIS]


def test_the_skeleton_says_in_english_whose_body_it_is(seeded: TestClient) -> None:
    spanish, english = _both(seeded, "/api/anatomy/skeleton")
    assert spanish["label"] == anatomy.REFERENCE_LABEL and spanish["alt"] == anatomy.REFERENCE_ALT
    assert english["label"] == "Reference skeleton (BodyParts3D): it is not the crew member's body."
    assert english["caption"].startswith("Reference figure, not the crew member's. BodyParts3D")
    assert english["source"] == spanish["source"] == "reference"
    assert list(english["bones"]) == list(spanish["bones"])
    own_es, own_en = _both(seeded, "/api/anatomy/skeleton/own")
    assert own_es["fallback_reason"] == anatomy.NO_SEGMENTATION
    assert own_en["fallback_reason"] == anatomy.ENGLISH[anatomy.NO_SEGMENTATION]
    assert own_en["fallback_kind"] == own_es["fallback_kind"] == anatomy.NO_OWN
    # La caché del esqueleto de referencia guarda una entrada por idioma: pedirlo en inglés no
    # deja el inglés para el siguiente.
    assert seeded.get("/api/anatomy/skeleton").json()["label"] == anatomy.REFERENCE_LABEL


# --------------------------------------------------------------------------- #
# El dolor referido
# --------------------------------------------------------------------------- #


def test_the_pain_catalogue_names_zones_and_kinds_in_english(seeded: TestClient) -> None:
    spanish, english = _both(seeded, "/api/pain/catalog")
    for field in ("key", "side"):
        assert [zone[field] for zone in english["zones"]] == [
            zone[field] for zone in spanish["zones"]
        ]
    names_es = {zone["key"]: zone["display"] for zone in spanish["zones"]}
    names_en = {zone["key"]: zone["display"] for zone in english["zones"]}
    assert names_es == {key: zone.display for key, zone in ZONES.items()}
    assert names_es["shoulder-left"] == "Hombro izquierdo"
    assert names_es["hand-right"] == "Mano derecha"
    assert names_en["shoulder-left"] == "Left shoulder" and names_en["hand-right"] == "Right hand"
    assert names_en["lower-back"] == "Lower back"
    assert names_en["lower-leg-left"] == "Left lower leg"
    # La lateralidad es la del tripulante en los dos idiomas: la clave y el nombre dicen lo mismo.
    for key, name in names_en.items():
        side = ZONES[key].side
        assert name.startswith("Left ") == (side == "left")
        assert name.startswith("Right ") == (side == "right")
    assert {item["key"]: item["display"] for item in english["characters"]} == {
        "sharp": "Sharp", "dull": "Dull", "burning": "Burning", "pressing": "Pressing",
        "throbbing": "Throbbing", "cramping": "Cramping", "tingling": "Tingling",
    }
    assert english["system"] == spanish["system"] and english["scale"] == spanish["scale"]


def _signed_after_report(client: TestClient, headers: dict[str, str]) -> tuple[Any, list[Any]]:
    reset_store(new_store())
    body = {"zones": [CHEST, KNEE], "reported_by": "cmdr", "effective": WHEN,
            "note": "me duele al respirar hondo", "note_origin": "dictada-revisada"}
    response = client.post("/api/pain/reports", json=body, headers=headers)
    assert response.status_code == 201, response.text
    listed = client.get("/api/pain/reports", headers=headers).json()
    signed = [
        (entry.entry_type, {k: v for k, v in (entry.payload or {}).items() if k != SALT_FIELD})
        for entry in get_store().ledger.entries
    ]
    return (response.json(), listed), signed


def test_a_pain_report_signs_the_same_in_both_languages(client: TestClient) -> None:
    (posted_es, listed_es), signed_es = _signed_after_report(client, {})
    (posted_en, listed_en), signed_en = _signed_after_report(client, ENGLISH_HEADERS)
    assert signed_en == signed_es
    assert posted_es["discuss"] == {
        "reasons": ["opresión en el pecho", "hormigueo de un lado"], "note": alarm.DISCUSS_NOTE,
    }
    assert posted_en["discuss"] == {
        "reasons": ["chest pressure", "tingling on one side"],
        "note": "For discussion with the onboard physician.",
    }
    [report_es], [report_en] = listed_es, listed_en
    assert report_en["discuss"] == posted_en["discuss"]
    assert report_es["discuss"] == posted_es["discuss"]
    # Lo firmado se lee igual: claves de zona y de tipo, la nota tal como se escribió y su origen,
    # que es un identificador persistido y no se traduce.
    for field in ("zones", "note", "note_origin", "reported_by", "effective"):
        assert report_en[field] == report_es[field]
    assert report_en["note_origin"] == "dictada-revisada"
    assert report_en["note"] == "me duele al respirar hondo"


def test_the_pain_overlay_names_zones_and_reasons_in_english() -> None:
    reports = [{"effective": WHEN, "zones": [CHEST, KNEE]}]
    spanish = pain_on_skeleton.overlay(reports)
    with i18n.use("en"):
        english = pain_on_skeleton.overlay(reports)
        assert pain_on_skeleton._reason(pain_on_skeleton.BAD_FIT).startswith(
            "Reported pain is not overlaid: the fit of the pain map"
        )
        # El motivo con que aborta Polaris es suyo y viaja dentro tal como lo escribe.
        aborted = pain_on_skeleton.NO_FIT.format(reason="faltan anclas")
        assert pain_on_skeleton._reason(aborted) == (
            "Reported pain is not aligned on this skeleton: the Polaris fit does not work out "
            "(faltan anclas)."
        )
        assert pain_on_skeleton._reason(None) is None
    assert pain_on_skeleton._reason(aborted) == aborted
    assert spanish["superposable"] and english["superposable"]
    assert {mark["zone"]: mark["display"] for mark in spanish["marks"]} == {
        "chest": "Tórax", "knee-left": "Rodilla izquierda",
    }
    assert {mark["zone"]: mark["display"] for mark in english["marks"]} == {
        "chest": "Chest", "knee-left": "Left knee",
    }
    for before, after in zip(spanish["marks"], english["marks"], strict=True):
        assert {**after, "display": before["display"]} == before
    # El ajuste cacheado sigue en castellano: el inglés se puso al servir, no dentro.
    assert pain_on_skeleton.overlay(reports) == spanish


# --------------------------------------------------------------------------- #
# Los protocolos ecográficos
# --------------------------------------------------------------------------- #


def test_protocol_identifiers_and_the_signed_checklist_stay_as_they_are() -> None:
    with i18n.use("en"):
        assert i18n.loc(protocols.PROTOCOLS["optic-nerve"].display) == "Optic nerve sheath"
        assert i18n.loc(protocols.PROTOCOLS["lung"].views[0].display) == "Right, anterior"
        sliding = protocols.PROTOCOLS["lung"].views[0].signs[0]
        assert i18n.loc(sliding.display) == "Lung sliding"
        assert {key: i18n.loc(text) for key, text in sliding.values.items()} == {
            "presente": "Present", "ausente": "Absent", protocols.NOT_ASSESSABLE: "Not assessable",
        }
        # El registro no cambia con el idioma: el texto de la lista de calidad es además la
        # clave con que el formulario contesta cada punto y con que se firma.
        lung = protocols.PROTOCOLS["lung"]
        assert lung.checklist[0] == "Sonda perpendicular a las costillas."
        assert lung.views[0].key == "derecha-anterior"
        assert protocols.validate_findings(lung, {}) == [
            f"falta la ventana '{view.display}'" for view in lung.views
        ]
    # Ningún identificador (clave de protocolo, ventana, signo o valor) tiene «inglés».
    identifiers = {
        key
        for protocol in protocols.PROTOCOLS.values()
        for key in (
            protocol.key,
            *(view.key for view in protocol.views),
            *(sign.key for view in protocol.views for sign in view.signs),
            *(value for view in protocol.views for sign in view.signs for value in sign.values),
        )
    }
    assert identifiers.isdisjoint(protocols.ENGLISH)
