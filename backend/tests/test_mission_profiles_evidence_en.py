"""El inglés de los perfiles de misión y del registro de evidencia (unidad 19).

El castellano no se toca: la suite de siempre lo fija. Aquí se pide el inglés —con `i18n.use("en")`
o con la cabecera— y se comprueba que lo que ve la tripulación sale en inglés, que el inglés no
afirma más que el castellano, que los identificadores son los mismos en los dos idiomas y que
pedir inglés no deja nada cambiado para quien después pide castellano.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from fastapi.testclient import TestClient

from app.core import i18n
from app.core.config import Settings
from app.evidence import design_hypotheses, links, mission_profiles, registry, tier
from app.ingest.codes import Domain
from tests.conftest import ENGLISH_HEADERS

_SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]

# Lo que el inglés de EMMA no dice de sí mismo ni de lo que cita (invariantes 6 y 7).
_OVERCLAIM = re.compile(r"certified|validated|proven|diagnos|administer|must take", re.I)
_SPANISH = re.compile(r"[áéíóúñ¿¡]", re.I)
# Texto que va en el idioma de su fuente aunque la consola esté en inglés.
_SOURCE_KEYS = frozenset({
    "quote", "title", "source", "notes", "scope_caveat", "scope_in_view", "url", "organization",
})


def _texts(value: Any, skip: frozenset[str] = _SOURCE_KEYS) -> list[str]:
    """Cada cadena servida, sin las de los campos que van en el idioma de la fuente."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for key, item in value.items() if key not in skip
                for text in _texts(item, skip)]
    if isinstance(value, list):
        return [text for item in value for text in _texts(item, skip)]
    return []


def _shape(value: Any) -> Any:
    """La forma de lo servido: las claves y los tipos, sin el texto."""
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(item) for item in value]
    return type(value).__name__


# El título de un bloque del marco de NASA leído es de `nasa_framework` (otra unidad): su inglés
# llega con el fichero hermano de ese módulo, y hasta entonces sale en castellano entre comillas.
_FRAMEWORK_PLACE = re.compile(r"^(NASA framework as read: )«.*»$")


def _clean(texts: list[str]) -> None:
    assert texts
    for text in texts:
        text = _FRAMEWORK_PLACE.sub(r"\1", text)
        assert not _OVERCLAIM.search(text), text
        assert not _SPANISH.search(text), text


# --------------------------------------------------------------------------- #
# Perfiles de misión
# --------------------------------------------------------------------------- #


def test_the_overlay_covers_every_spanish_string_of_the_profiles() -> None:
    raw = mission_profiles.catalog()
    served = [
        {
            "display": profile["display"],
            "aspects": [
                {
                    "statement": aspect["statement"],
                    "searched": aspect["searched"],
                    "discrepancy": (aspect["discrepancy"] or {}).get("text"),
                    "sections": [
                        cite["section"] for cite in mission_profiles._aspect_citations(aspect)
                    ],
                }
                for aspect in profile["aspects"].values()
            ],
        }
        for profile in raw["profiles"]
    ]
    # Un apartado que es solo el título que le da la página no tiene nada de EMMA que traducir.
    assert i18n.missing(
        mission_profiles.PROFILES_PATH, served, skip=lambda text: not _SPANISH.search(text)
    ) == []


def test_no_english_string_of_the_overlays_claims_more_or_keeps_spanish() -> None:
    for path in (mission_profiles.PROFILES_PATH, design_hypotheses.HYPOTHESES_PATH):
        strings = i18n.overlay(path)
        assert len(strings) > 30
        _clean(list(strings.values()))
        # Ningún inglés vacío ni igual a su castellano: eso no es una traducción.
        assert all(english.strip() and english != spanish for spanish, english in strings.items())


def test_the_overlay_has_no_key_that_the_catalog_does_not_say() -> None:
    """Una clave que ya no está en el fichero castellano es un inglés huérfano: nadie lo sirve."""
    said = set(_texts(mission_profiles.catalog(), frozenset()))
    assert set(i18n.overlay(mission_profiles.PROFILES_PATH)) <= said
    said = set(_texts(design_hypotheses.inventory(), frozenset()))
    assert set(i18n.overlay(design_hypotheses.HYPOTHESES_PATH)) <= said


def test_the_matrix_in_english_names_the_profiles_and_keeps_the_identifiers() -> None:
    spanish = mission_profiles.compare("mars-transit")
    before = copy.deepcopy(spanish)
    with i18n.use("en"):
        english = mission_profiles.compare("mars-transit")
    assert [profile["display"] for profile in english["profiles"]] == [
        "low Earth orbit (space station)",
        "cislunar space (Orion, between Earth and the Moon)",
        "lunar surface",
        "Mars transit",
        "Mars surface",
    ]
    assert [aspect["label"] for aspect in english["aspects"]] == [
        "communication delay", "gravity regime", "return or evacuation", "resupply", "duration",
        "distance", "radiation environment", "surface dust", "day and night cycle",
        "medical capability or autonomy",
    ]
    assert english["no_source"] == "EMMA has no source"
    assert english["note"].startswith("descriptive: ")
    assert english["medical_note"].startswith("EMMA's note: levels of care IV and V")
    assert "not a sentence it read" in english["medical_note"]
    # Misma forma, mismos identificadores, mismas citas literales y mismas fechas.
    assert _shape(english) == _shape(spanish)
    for theirs, ours in zip(english["profiles"], spanish["profiles"], strict=True):
        assert (theirs["id"], theirs["declared"]) == (ours["id"], ours["declared"])
        for cell, original in zip(theirs["cells"], ours["cells"], strict=True):
            assert (cell["key"], cell["status"]) == (original["key"], original["status"])
            assert [
                (cite["ref"], cite["quote"], cite["read_on"], cite["title"], cite["url"])
                for cite in cell["citations"]
            ] == [
                (cite["ref"], cite["quote"], cite["read_on"], cite["title"], cite["url"])
                for cite in original["citations"]
            ]
    assert english["pages_read"] == spanish["pages_read"]
    _clean(_texts(english))
    # Pedir inglés no cambia lo que se sirve en castellano ni lo que estaba cacheado.
    assert spanish == before
    assert mission_profiles.compare("mars-transit") == before


def test_a_cell_keeps_its_hedges_in_english() -> None:
    with i18n.use("en"):
        matrix = mission_profiles.compare("leo")
    cells = {
        (profile["id"], cell["key"]): cell
        for profile in matrix["profiles"] for cell in profile["cells"]
    }
    evacuation = cells[("leo", "return_or_evacuation")]
    assert evacuation["status_text"] == "read in the source"
    assert "it is an estimate, not a flight procedure" in evacuation["text"]
    assert "It is the plan of a mission, not an observed duration" in (
        cells[("lunar-surface", "typical_duration")]["text"]
    )
    dust = cells[("leo", "surface_dust")]
    assert (dust["status_text"], dust["text"]) == ("unverified", "EMMA has no source")
    assert dust["searched"].endswith("no sentence read speaks of dust aboard the space station.")
    gravity = cells[("mars-surface", "gravity_regime")]
    assert gravity["discrepancy"]["text"].endswith("EMMA does not choose and shows both.")
    radiation = cells[("mars-transit", "radiation_environment")]
    assert radiation["emma_note"].startswith("EMMA's note: the measured dose rate mixes")
    assert "it does not say which phase the cycle is in today" in radiation["text"]


def test_a_medical_cell_says_in_english_what_each_quote_was_first_read_for() -> None:
    with i18n.use("en"):
        matrix = mission_profiles.compare("leo")
        described = mission_profiles.describe("mars-transit", _SETTINGS)
    reused = [
        where
        for profile in matrix["profiles"] for cell in profile["cells"]
        for where in cell["reused_from"]
    ]
    assert "«communication delay» of «low Earth orbit (space station)»" in reused
    assert any(where.startswith("NASA framework as read: «") for where in reused)
    assert not any(" de «" in where or "marco de NASA" in where for where in reused)
    medical = described["aspects"][-1]
    assert medical["label"] == "medical capability or autonomy"
    assert "«communication delay» of «Mars transit»" in medical["reused_from"]
    # En castellano, lo de siempre.
    spanish = mission_profiles.describe("mars-transit", _SETTINGS)["aspects"][-1]
    assert "«retardo de comunicaciones» de «tránsito a Marte»" in spanish["reused_from"]
    assert len(spanish["reused_from"]) == len(medical["reused_from"])


def test_the_declared_profile_says_in_english_what_light_time_did() -> None:
    with i18n.use("en"):
        scaled = mission_profiles.describe(
            "mars-transit", _SETTINGS, round_trip_minutes=24.0, isolation_factor=1.5
        )
        below = mission_profiles.describe(
            "mars-transit", _SETTINGS, round_trip_minutes=0.04, isolation_factor=1.0
        )
        none = mission_profiles.describe("mars-transit", _SETTINGS)
        no_target = mission_profiles.describe("leo", _SETTINGS)
        unknown = mission_profiles.describe("venus", _SETTINGS)
        ignored = mission_profiles.describe(
            "leo", Settings(_env_file=None, target_body="301")  # type: ignore[call-arg]
        )
    assert scaled["display"] == "Mars transit"
    assert scaled["ephemeris"]["text"] == (
        "Light time is calculated toward Mars (JPL Horizons code 499), the ephemeris target of "
        "this profile. In this state the round trip is 24 min, and the risk is scaled with it "
        "(isolation factor 1.50)."
    )
    assert below["ephemeris"]["text"].endswith(
        "In this state the round trip is 2.4 s, below the autonomy threshold: it does not scale "
        "the risk."
    )
    assert none["ephemeris"]["text"].endswith(
        "In this state there is no ephemeris for its day, so the risk is not scaled with any "
        "light time; the day there is one, it will be scaled with that."
    )
    assert no_target["ephemeris"]["text"].startswith(
        "This profile has no ephemeris target in EMMA: the delay with Earth is not calculated"
    )
    assert ignored["ephemeris"]["text"].endswith(
        " The configuration carries EMMA_TARGET_BODY=301: it is not used, because the target "
        "is decided by the profile."
    )
    assert unknown["display"] == "unrecognized profile"
    assert unknown["unknown_text"].startswith(
        "The declared profile ('venus') is not in EMMA's catalog, which has leo, cislunar"
    )
    for served in (scaled, below, none, no_target, unknown, ignored):
        assert served["note"].startswith("descriptive: ")
        assert served["declared"].startswith("The starting environment is the one in the")
        _clean(_texts(served))
    # Las mismas decisiones en los dos idiomas: el idioma no toca ni el objetivo ni el estado.
    spanish = mission_profiles.describe(
        "mars-transit", _SETTINGS, round_trip_minutes=24.0, isolation_factor=1.5
    )
    for key in ("state", "target_body", "configured_target_body", "configured_ignored",
                "risk_scaled"):
        assert scaled["ephemeris"][key] == spanish["ephemeris"][key]
    assert spanish["ephemeris"]["text"].endswith(
        "En este estado son 24 min de ida y vuelta, y el riesgo se escala con ellos (factor de "
        "aislamiento 1,50)."
    )


def test_the_route_serves_the_matrix_in_the_language_asked(client: TestClient) -> None:
    before = client.get("/api/mission/profiles").json()
    english = client.get("/api/mission/profiles", headers=ENGLISH_HEADERS).json()
    after = client.get("/api/mission/profiles").json()
    assert before == after
    assert before["no_source"] == "EMMA no tiene fuente"
    assert english["no_source"] == "EMMA has no source"
    assert english["declared_id"] == before["declared_id"]
    assert english["profiles"][0]["display"] == "low Earth orbit (space station)"
    assert "órbita baja terrestre" not in str(english)
    assert before["profiles"][0]["display"] == "órbita baja terrestre (estación espacial)"


# --------------------------------------------------------------------------- #
# Hipótesis de diseño
# --------------------------------------------------------------------------- #


def test_the_overlay_covers_every_spanish_string_of_the_hypotheses() -> None:
    raw = design_hypotheses.inventory()
    served = [
        {
            "statement": item["statement"],
            "real_data": item.get("real_data"),
            "not_demonstrated": item["not_demonstrated"],
            "touches": [touch["what"] for touch in item["touches"]],
        }
        for item in raw["hypotheses"]
    ]
    assert i18n.missing(design_hypotheses.HYPOTHESES_PATH, served) == []


def test_no_hypothesis_is_given_as_proved_in_english_either() -> None:
    spanish = design_hypotheses.payload()
    with i18n.use("en"):
        english = design_hypotheses.payload()
    assert _shape(english) == _shape(spanish)
    assert [item["id"] for item in english["statuses"]] == list(design_hypotheses.STATUSES)
    for status in english["statuses"]:
        assert status["text"].startswith("hypothesis: ")
    for theirs, ours in zip(english["hypotheses"], spanish["hypotheses"], strict=True):
        for key in ("id", "label", "status", "scenario", "documents"):
            assert theirs[key] == ours[key]
        assert [
            (touch["module"], touch["method"], touch["route"]) for touch in theirs["touches"]
        ] == [(touch["module"], touch["method"], touch["route"]) for touch in ours["touches"]]
        assert theirs["statement"] != ours["statement"]
        assert theirs["status_text"].startswith("hypothesis: ")
        assert theirs["not_demonstrated"] != ours["not_demonstrated"]
    # La nota dice que el enunciado es una traducción: el literal es el castellano.
    assert "translated here from the Spanish original" in english["note"]
    assert "None is listed as proved" in english["note"]
    # El título del apartado es el del documento del equipo y no se traduce.
    assert english["source"] == spanish["source"]
    _clean(_texts(english, frozenset({"source"})))
    assert design_hypotheses.payload() == spanish
    assert spanish["note"].startswith("Hipótesis de diseño")


def test_what_mmash_does_not_show_stays_said_in_english() -> None:
    with i18n.use("en"):
        served = {item["id"]: item for item in design_hypotheses.payload()["hypotheses"]}
    assert "It is not flight physiology." in served["KB-H2"]["real_data"]
    assert "does not validate flight drift" in served["KB-H2"]["not_demonstrated"]
    assert "having read the documents does not prove it" in served["KB-H1"]["not_demonstrated"]
    assert "not proof of causality" in served["KB-H4"]["not_demonstrated"]


# --------------------------------------------------------------------------- #
# Registro de evidencia, nivel de evidencia y enlaces
# --------------------------------------------------------------------------- #


def test_a_record_labels_its_fields_in_english_and_keeps_its_identifiers() -> None:
    spanish = registry.get("osd-288").to_dict()
    with i18n.use("en"):
        english = registry.get("osd-288").to_dict()
        assert registry.get("osd-288").evidence_type_display == "dataset"
    assert spanish["evidence_type_display"] == "conjunto de datos"
    assert english["evidence_type_display"] == "dataset"
    assert english["population_display"] == "animal"
    for key in ("id", "title", "source", "url", "doi", "pmid", "date", "evidence_type",
                "evidence_context", "population", "not_applicable", "outside_enum",
                "unverified"):
        assert english[key] == spanish[key]
    # La salvedad de alcance no se traduce en esta versión: sale tal cual, no a medias.
    assert english["notes"] == spanish["notes"]
    assert english["grade"]["tier"] == spanish["grade"]["tier"] == "modelo_animal"
    assert english["grade"]["basis"] == "text"
    assert english["grade"]["label"] == (
        "animal model (preclinical) · from the text of the citation, not from the record"
    )
    assert english["grade"]["reason"] == (
        "bench signal (animal) with no signal of people · no PMID: read from the text of the "
        "citation, not from the record"
    )
    assert registry.get("osd-288").to_dict() == spanish


def test_every_label_of_the_registry_has_its_english() -> None:
    with i18n.use("en"):
        summary = registry.summary()
        labels = [
            *summary["evidence_types"].values(), *summary["populations"].values(),
            *(i18n.loc(text) for text in registry.OPTIONAL_FIELDS.values()),
            i18n.loc(registry.UNCLASSIFIED), i18n.loc(registry.NOT_APPLICABLE),
            i18n.loc(registry.OUTSIDE_ENUM),
        ]
        displays = [
            text
            for item in summary["references"]
            for text in (
                item["evidence_type_display"], item["population_display"],
                *item["unverified_display"], *item["outside_enum_display"],
            )
        ]
    assert list(summary["evidence_types"]) == list(registry.EVIDENCE_TYPES)
    assert list(summary["populations"]) == list(registry.POPULATIONS)
    assert summary["evidence_types"]["preprint"] == "preprint, not peer-reviewed"
    assert summary["populations"] == {
        "human": "human", "animal": "animal", "human_and_animal": "human and animal",
    }
    _clean(labels)
    _clean(displays)
    assert set(displays) <= set(labels)
    spanish = registry.summary()
    assert spanish["evidence_types"] == registry.EVIDENCE_TYPES
    assert spanish["count"] == summary["count"]
    assert spanish["unverified_fields"] == summary["unverified_fields"]


def test_every_tier_label_and_every_reason_of_the_hierarchy_has_its_english() -> None:
    original = tier._original()
    # Cada regla de `teje()`, sola y con la marca de preprint; las dos de banco; y ninguna.
    cases: list[dict[str, bool]] = [{}, {"preprint": True}]
    for name in original.SENALES:
        cases.append({name: True})
        cases.append({name: True, "preprint": True})
    cases.append({"prospectivo": True, "retrospectivo": True})
    seen: set[str] = set()
    for given in cases:
        spanish = tier.weave(given)
        with i18n.use("en"):
            english = tier.weave(given)
        seen.add(str(spanish["tier"]))
        for key in ("tier", "preclinical", "signals", "missing"):
            assert english[key] == spanish[key]
        _clean([english["label"], english["reason"]])
        assert english["label"] != spanish["label"] or spanish["tier"] == "preprint"
    assert seen == set(tier.LABELS)
    with i18n.use("en"):
        assert tier.weave({"rct": True, "preprint": True})["reason"] == (
            "randomized trial · preprint, not peer-reviewed"
        )
        unknown = tier.weave({})
        assert unknown["label"] == "unknown: cannot be classified from the record"
        # Los nombres de las señales son identificadores: los mismos en los dos idiomas.
        assert unknown["reason"] == (
            f"no design signal resolved (missing: {', '.join(unknown['missing'])})"
        )
        assert tier.grade("Autor et al. PubMed")["reason"].startswith(
            "the citation names PubMed but its PMID cannot be read"
        )
        assert tier.grade("NASA HRP")["reason"].startswith("no PMID: there is no record")
        assert tier.grade("PMID 99999999")["reason"] == (
            "record not stored: run scripts/grade_sources.py"
        )
    assert tier.grade("PMID 99999999")["reason"].startswith("registro no guardado")


def test_what_a_domain_cites_says_in_english_why_and_how_far() -> None:
    cited = [item for domain in Domain for item in links.evidence_for(domain)]
    assert len(cited) > 10
    with i18n.use("en"):
        english = [item.to_dict() for item in cited]
        scopes = [links.amcl_alignment(domain) for domain in Domain]
        eimo = i18n.loc(links.EIMO_DESCRIPTION)
    spanish = [item.to_dict() for item in cited]
    for theirs, ours in zip(english, spanish, strict=True):
        assert theirs["id"] == ours["id"]
        assert theirs["relevance"] != ours["relevance"]
        assert ours["relevance"] == next(
            item.relevance for item in cited if item.id == ours["id"]
        )
    _clean([item["relevance"] for item in english])
    _clean([*scopes, eimo])
    assert [links.amcl_alignment(domain) for domain in Domain] == [
        links.AMCL_ALIGNMENT[domain] for domain in Domain
    ]
    by_id = {item["id"]: item["relevance"] for item in english}
    # OSD-288 sigue siendo bazo de ratón, también en inglés.
    assert by_id["osd-288"].startswith("RNA-Seq of mouse spleen after 35 days on the ISS")
    assert "52 % of astronauts (382 of 728)" in by_id["kerstman-2012"]
    with i18n.use("en"):
        cardiovascular = links.amcl_alignment(Domain.CARDIOVASCULAR)
        nutrition = links.amcl_alignment(Domain.NUTRITION)
    # Apoyo a la decisión: el alcance dice lo que no hace, sin sonar a orden médica.
    assert cardiovascular.endswith("it does not identify the specific arrhythmia")
    assert nutrition.endswith("no diet or supplements are prescribed")
    assert eimo.startswith("Earth-Independent Medical Operations: the gradual transition")


def test_a_relevance_without_english_is_served_as_written() -> None:
    with i18n.use("en"):
        served = registry.cite("osd-288", "solo en castellano, sin inglés registrado").to_dict()
        assert registry.cite("osd-288").to_dict()["relevance"] is None
    assert served["relevance"] == "solo en castellano, sin inglés registrado"


def test_the_routes_serve_the_evidence_in_the_language_asked(client: TestClient) -> None:
    before = client.get("/api/dossier/references").json()
    english = client.get("/api/dossier/references", headers=ENGLISH_HEADERS).json()
    assert client.get("/api/dossier/references").json() == before
    assert before["evidence_types"]["dataset"] == "conjunto de datos"
    assert english["evidence_types"]["dataset"] == "dataset"
    assert [item["id"] for item in english["references"]] == [
        item["id"] for item in before["references"]
    ]
    assert "conjunto de datos" not in {
        item["evidence_type_display"] for item in english["references"]
    }
    framework = client.get("/api/framework", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/framework").json()
    assert framework["amcl_alignment"]["cardiovascular"].startswith(
        "Arrhythmias and cardiovascular deconditioning."
    )
    assert spanish["amcl_alignment"]["cardiovascular"].startswith("Arritmias y ")
    assert framework["design_hypotheses"]["note"].startswith("Design hypotheses from the team")
    assert spanish["design_hypotheses"]["note"].startswith("Hipótesis de diseño")
    assert [item["id"] for item in framework["design_hypotheses"]["hypotheses"]] == [
        item["id"] for item in spanish["design_hypotheses"]["hypotheses"]
    ]
