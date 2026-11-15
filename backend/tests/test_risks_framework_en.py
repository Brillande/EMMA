"""El marco de NASA y los riesgos, en inglés (unidad 18 de los dos idiomas, `core/i18n.py`).

Qué se comprueba: que `/api/risks`, `/api/risks/hrp-coverage` y lo leído del marco
(`/api/framework` → `read_sources`) salen en inglés cuando se pide, que sin pedirlo salen como
salían, y que el inglés no cambia nada que no sea texto: ni un identificador, ni una cifra, ni una
frase de la fuente. Y que no dice más que el castellano: ninguna palabra que reclame lo que EMMA no
reclama (invariantes 6 y 7).

Lo que otros módulos redactan (el nombre de un nivel, de un dominio, lo que valida MMASH) lleva su
inglés en la unidad de cada uno: aquí se aparta antes de mirar las frases que se componen con ello.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import risk_entity
from app.analysis.risk import RiskLevel
from app.api import routes
from app.core import i18n
from app.evidence import hrp_coverage, nasa_framework
from app.ingest.codes import Domain
from app.validation import injection, mmash
from tests.conftest import ENGLISH_HEADERS

# Lo que el inglés de esta unidad no dice de EMMA, ni negándolo: el valor del proyecto está en que
# no exagera. Y lo que delata una frase a medio traducir.
OVERSTATED = re.compile(r"certified|validated|compliant with|diagnos|administer|must take", re.I)
SPANISH = re.compile(r"[áéíóúñü¿¡]", re.I)
DIGITS = re.compile(r"\d+")
QUOTED = re.compile(r"«([^«»]+)»")
# Lo que el texto sobre EMMA no puede reclamar por citar un documento: el inglés de `CLAIM_WORDS`.
CLAIMS = re.compile(
    r"\b(implements|aligned with|conforms|complies|certif\w*|satisfies|compatible with)\b", re.I
)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _overlay(path: Any) -> dict[str, str]:
    strings: dict[str, str] = json.loads(i18n.overlay_path(path).read_text(encoding="utf-8"))[
        "strings"
    ]
    return strings


def _sober(texts: Iterator[str] | list[str]) -> None:
    for text in texts:
        assert OVERSTATED.search(text) is None, text
        assert SPANISH.search(text) is None, text


# --------------------------------------------------------------------------- #
# El marco de NASA, leído
# --------------------------------------------------------------------------- #

# Lo que en el fichero no redacta EMMA o no es texto: la frase de la fuente y lo que pide, las
# rutas, los identificadores y las fechas.
_FRAMEWORK_NOT_PROSE = {
    "_nota", "read_on", "ref", "url", "id", "quote", "asks", "files", "extent", "status",
    "rests_on", "statement",
}


# Lo que va entre comillas angulares y no es una frase de la fuente: palabras de EMMA (las de la
# tabla de cobertura, su vocabulario de sistemas) y de la base de conocimiento del equipo, que
# está en castellano. Todo lo demás entrecomillado es de NASA y no se traduce.
_OWN_QUOTED = {
    "Cubre", "En parte", "control térmico y de humedad", "lógica de votación",
    "el estado del vehículo modifica el estado humano",
    "Sensibilidad de los resultados a las especificaciones de misión",
    "validaciones históricas con diferencias entre predicción y eventos observados",
}


def _framework_prose(value: Any, key: str | None = None) -> Iterator[str]:
    if isinstance(value, str):
        if key != "coverage":  # la de una fila es su clave; la del bloque es un objeto
            yield value
    elif isinstance(value, dict):
        for name, item in value.items():
            if name not in _FRAMEWORK_NOT_PROSE:
                yield from _framework_prose(item, name)
    elif isinstance(value, list):
        for item in value:
            yield from _framework_prose(item, key)


def test_every_sentence_emma_writes_about_the_framework_has_its_english() -> None:
    prose = list(_framework_prose(nasa_framework.read()))
    assert len(prose) > 300
    assert i18n.missing(nasa_framework.READ_PATH, prose) == []


def test_the_english_of_the_framework_keeps_every_figure_and_overstates_nothing() -> None:
    strings = _overlay(nasa_framework.READ_PATH)
    for spanish, english in strings.items():
        # Una fecha, una página o un número de registro no cambian al traducir.
        assert sorted(DIGITS.findall(spanish)) == sorted(DIGITS.findall(english)), spanish
        # Lo que cita entre comillas angulares es de la fuente: sigue letra por letra. Salvo lo
        # que es castellano de EMMA o de la base de conocimiento del equipo, que se traduce.
        kept = [cited for cited in QUOTED.findall(spanish) if cited not in _OWN_QUOTED]
        assert all(f"«{cited}»" in english for cited in kept), spanish
    _sober(list(strings.values()))


def test_the_framework_is_served_in_english_and_the_source_is_not_touched() -> None:
    spanish = nasa_framework.payload()
    with i18n.use("en"):
        english = nasa_framework.payload()
    assert english["note"].startswith("What NASA's official sources say")
    assert "EMMA claims conformity with none" in english["note"]
    assert [item["text"] for item in english["extents"]] == [
        "read in full", "read in part", "read: NTRS abstract; the full document, not",
    ]
    assert [item["text"] for item in english["gap_statuses"]] == [
        "open", "closed", "merged into another gap",
        "archived and withdrawn from the current research plan", "split into other gaps",
    ]
    assert [item["text"] for item in english["coverages"]] == ["covers", "partly", "no"]
    assert english["read_on"] == spanish["read_on"]
    for es_source, en_source in zip(spanish["sources"], english["sources"], strict=True):
        assert {k: v for k, v in en_source.items() if k not in ("extent_text", "what")} == {
            k: v for k, v in es_source.items() if k not in ("extent_text", "what")
        }
        assert en_source["what"] != es_source["what"]
    for es_block, en_block in zip(spanish["blocks"], english["blocks"], strict=True):
        assert en_block["id"] == es_block["id"]
        assert en_block["title"] != es_block["title"]
        assert en_block["emma"] != es_block["emma"]
        assert CLAIMS.search(en_block["emma"]) is None, en_block["emma"]
        assert len(en_block["not_read"]) == len(es_block["not_read"])
        for es_item, en_item in zip(es_block["statements"], en_block["statements"], strict=True):
            # La frase es de NASA y está en inglés en los dos idiomas: ni una letra distinta.
            for name in ("id", "quote", "ref", "source", "title", "url", "read_on", "extent"):
                assert en_item[name] == es_item[name]
            assert en_item["label"] != es_item["label"]
            if es_item["gap"] is not None:
                assert en_item["gap"]["id"] == es_item["gap"]["id"]
                assert en_item["gap"]["status"] == es_item["gap"]["status"]
        if es_block["coverage"] is not None:
            assert en_block["coverage"]["counts"] == es_block["coverage"]["counts"]
            rows = zip(es_block["coverage"]["rows"], en_block["coverage"]["rows"], strict=True)
            for es_row, en_row in rows:
                for name in ("statement", "asks", "coverage", "files"):
                    assert en_row[name] == es_row[name]
                assert en_row["emma"] != es_row["emma"]
                assert CLAIMS.search(en_row["emma"]) is None, en_row["emma"]
                assert en_row["coverage_text"] in ("covers", "partly", "no")
    # Lo servido en inglés no lleva ya nada de lo que EMMA redacta en castellano.
    translated = {es for es, en in _overlay(nasa_framework.READ_PATH).items() if es != en}
    assert translated.isdisjoint(set(_strings(english)))
    # Y el castellano sigue siendo el del fichero: la copia inglesa no lo ha tocado.
    assert nasa_framework.payload() == spanish


def test_the_english_answer_still_quotes_its_sentences_letter_by_letter() -> None:
    with i18n.use("en"):
        blocks = nasa_framework.payload()["blocks"]
    asked = [block for block in blocks if block["question"] is not None]
    assert asked
    for block in asked:
        question = block["question"]
        quotes = {item["id"]: item["quote"] for item in block["statements"]}
        rests_on = [quotes[item["id"]] for item in question["rests_on"]]
        cited = QUOTED.findall(question["answer"])
        assert cited
        assert all(any(text in quote for quote in rests_on) for text in cited)
        assert "No source read says that the replacement has happened" in question["answer"]


def test_the_status_of_a_gap_is_read_in_english() -> None:
    spanish = nasa_framework.gap_status("Med10")
    with i18n.use("en"):
        english = nasa_framework.gap_status("Med10")
    assert spanish["status_text"] == "fusionado en otro hueco"
    assert english["status_text"] == "merged into another gap"
    assert english["where"] == "header of the Med10 gap page"
    assert {k: v for k, v in english.items() if k not in ("status_text", "where")} == {
        k: v for k, v in spanish.items() if k not in ("status_text", "where")
    }


def test_the_framework_route_answers_in_the_language_asked(client: TestClient) -> None:
    english = client.get("/api/framework", headers=ENGLISH_HEADERS).json()["read_sources"]
    spanish = client.get("/api/framework").json()["read_sources"]
    assert spanish == nasa_framework.payload()
    assert spanish["note"] == nasa_framework.NOTE
    assert english["note"].startswith("What NASA's official sources say")
    assert english["blocks"][0]["title"] == "ExMC CDSS architecture"
    assert spanish["blocks"][0]["title"] == "Arquitectura del CDSS de ExMC"


# --------------------------------------------------------------------------- #
# La cobertura de los riesgos del HRP
# --------------------------------------------------------------------------- #


def test_every_reason_of_the_coverage_has_its_english() -> None:
    raw = hrp_coverage.load()
    prose = [raw["listing"]["updates"]]
    for item in raw["risks"]:
        prose += [item["ridge_note"], item["reason"], *item["pending"]]
    assert len(prose) > 50
    assert i18n.missing(hrp_coverage.COVERAGE_PATH, prose) == []
    strings = _overlay(hrp_coverage.COVERAGE_PATH)
    for spanish, english in strings.items():
        assert sorted(DIGITS.findall(spanish)) == sorted(DIGITS.findall(english)), spanish
        assert all(f"«{cited}»" in english for cited in QUOTED.findall(spanish)), spanish
    _sober(list(strings.values()))


def test_the_coverage_is_served_in_english_with_the_names_nasa_gives() -> None:
    spanish = hrp_coverage.payload()
    with i18n.use("en"):
        english = hrp_coverage.payload()
    assert english["note"].startswith("The risks the Human Research Roadmap publishes")
    assert "not that EMMA covers it in full" in english["note"]
    assert english["coverage_display"] == {
        "covered": "covered", "partial": "partly", "outside": "outside EMMA's scope",
    }
    assert english["counts"] == spanish["counts"]
    counts = english["counts"]
    assert english["summary"] == (
        f"Of the {english['count']} risks in the listing, {counts['covered']} are the one an "
        f"EMMA domain cites, {counts['partial']} are covered partly, watched or only recorded "
        f"depending on the row, and {counts['outside']} are outside its scope."
    )
    own = [english[name] for name in (
        "note", "summary", "element_basis", "ridge_note", "pending_note", "in_catalog_note",
    )]
    assert all(text != spanish_text for text, spanish_text in zip(own, [
        spanish[name] for name in (
            "note", "summary", "element_basis", "ridge_note", "pending_note", "in_catalog_note",
        )
    ], strict=True))
    _sober(own + [english["listing"]["updates"]])
    for name in ("count_quote", "element_quote"):
        assert english["listing"][name] == spanish["listing"][name]
    for es_risk, en_risk in zip(spanish["risks"], english["risks"], strict=True):
        # El título, el nombre corto y el elemento son los de la página del Roadmap.
        for name in (
            "hrr_id", "url", "title", "short_title", "status", "hrp_element", "last_published",
            "coverage",
        ):
            assert en_risk[name] == es_risk[name]
        assert en_risk["ridge"]["category"] == es_risk["ridge"]["category"]
        assert en_risk["ridge"]["basis"] == es_risk["ridge"]["basis"]
        assert [item["key"] for item in en_risk["domains"]] == [
            item["key"] for item in es_risk["domains"]
        ]
        assert [item["key"] for item in en_risk["in_catalog"]] == [
            item["key"] for item in es_risk["in_catalog"]
        ]
        assert en_risk["status_display"] in ("active", "inactive")
        assert en_risk["ridge"]["basis_display"] in (
            "named by a NASA source", "inferred by EMMA; no source read names it",
        )
        assert en_risk["coverage_display"] == english["coverage_display"][en_risk["coverage"]]
        assert en_risk["reason"] != es_risk["reason"]
        assert en_risk["ridge"]["note"] != es_risk["ridge"]["note"]
        assert len(en_risk["pending"]) == len(es_risk["pending"])
        _sober([en_risk["reason"], en_risk["ridge"]["note"], *en_risk["pending"]])
        for analyte in en_risk["in_catalog"]:
            if analyte["descriptive_only"]:
                assert analyte["descriptive_display"] == (
                    "descriptive: it is recorded and shown, and the status does not read it"
                )
    assert hrp_coverage.payload() == spanish


def test_the_coverage_sentence_reads_as_english() -> None:
    bone, cardio = str(Domain.BONE), str(Domain.CARDIOVASCULAR)
    assert hrp_coverage.coverage_statement("partial", [bone, cardio]) == (
        f"en parte, por los dominios {Domain.BONE.display} y {Domain.CARDIOVASCULAR.display}"
    )
    with i18n.use("en"):
        one = hrp_coverage.coverage_statement("covered", [bone])
        two = hrp_coverage.coverage_statement("partial", [bone, cardio])
        partly_one = hrp_coverage.coverage_statement("partial", [bone])
        assert one == f"covered by the {Domain.BONE.display} domain"
        assert two == (
            f"partly, by the {Domain.BONE.display} and {Domain.CARDIOVASCULAR.display} domains"
        )
        assert partly_one == f"partly, by the {Domain.BONE.display} domain"
        assert hrp_coverage.coverage_statement("outside", []) == "outside EMMA's scope"


def test_the_coverage_route_answers_in_the_language_asked(client: TestClient) -> None:
    english = client.get("/api/risks/hrp-coverage", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/risks/hrp-coverage").json()
    assert spanish == hrp_coverage.payload()
    assert spanish["note"] == hrp_coverage.NOTE
    assert english["note"] != spanish["note"]
    assert english["risks"][0]["title"] == spanish["risks"][0]["title"]
    assert english["risks"][0]["reason"] != spanish["risks"][0]["reason"]


# --------------------------------------------------------------------------- #
# La entidad Riesgo
# --------------------------------------------------------------------------- #

# Las constantes del módulo que se enseñan: todas tienen inglés registrado.
_RISK_CONSTANTS = (
    "NOT_QUANTIFIED", "SCHEMA_BASIS", "HUMAN_SYSTEM_BASIS", "EVALUATION_BASIS", "DEMO_NOTE",
    "INFERRED_NOTE", "CHAIN_BASIS", "EFFECT_BASIS", "NO_EFFECT", "DATA_BASIS", "NO_DATASETS",
    "NO_DOCUMENTS", "DETECTION_BASIS", "DETECTION_RULE_DISPLAY", "VALIDATED_WITH_DISPLAY",
    "VALIDATION_STATEMENT", "MMASH_BASIS", "NO_MMASH", "SENSITIVITY_BASIS", "NO_SENSITIVITY",
    "EQUIPMENT_BASIS", "NO_EQUIPMENT", "NO_INDICATORS_DETECTION", "NO_ISOLATION_PROBE",
    "NO_ISOLATION", "ON_EVENT", "RESTING_STATES", "EXERTION_STATE", "OTHER_STATE",
    "COUNTERMEASURES_BASIS", "NO_COUNTERMEASURES",
)


def _risk_words() -> list[str]:
    words = [getattr(risk_entity, name) for name in _RISK_CONSTANTS]
    words += list(risk_entity.EVALUATED_WITH.values())
    words += [word for _, word in risk_entity.CHAIN_LINKS]
    words += list(risk_entity.FINDING_SEVERITY_DISPLAY.values())
    words += list(risk_entity.SOLAR_SEVERITY_DISPLAY.values())
    return words


def test_every_constant_of_the_risk_entity_has_its_english() -> None:
    same_in_both = {"Variable", "nominal"}
    with i18n.use("en"):
        english = {word: i18n.loc(word) for word in _risk_words()}
    assert [word for word, text in english.items() if text == word] == sorted(same_in_both)
    _sober(list(english.values()))
    # El inglés no afirma más: lo que no se cuantifica, no se mide o no decide, lo sigue diciendo.
    assert "does not quantify" in english[risk_entity.NOT_QUANTIFIED]
    assert "with no clinical source" in english[risk_entity.SCHEMA_BASIS]
    assert "asserts nothing clinical" in english[risk_entity.HUMAN_SYSTEM_BASIS]
    assert "has not been measured on real people" in english[risk_entity.NO_MMASH]
    assert "has not been measured" in english[risk_entity.NO_SENSITIVITY]
    assert "decides nothing and moves no levels" in english[risk_entity.CHAIN_BASIS]


def _own(text: str) -> str:
    """Una frase compuesta sin lo que redactan otros módulos (cada uno lleva su inglés)."""
    foreign = [level.display for level in RiskLevel]
    foreign += [mmash.VALIDATES, *injection.REFERENCE_TARGETS]
    for fragment in sorted(foreign, key=len, reverse=True):
        text = text.replace(fragment, "…")
    return text


def _figures(value: Any) -> Any:
    """Las cifras y las claves de un bloque `values`, sin la palabra con que se enseña cada una."""
    if isinstance(value, dict):
        return {name: _figures(item) for name, item in value.items() if name != "display"}
    if isinstance(value, list):
        return [_figures(item) for item in value]
    return value


def test_the_composed_sentences_of_the_risk_entity_read_as_english() -> None:
    spanish = risk_entity.payload(routes.CURRENT_WINDOW)
    with i18n.use("en"):
        english = risk_entity.payload(routes.CURRENT_WINDOW)
    rule = {step["key"]: step for step in english["detection_rule"]["steps"]}
    assert [step["display"] for step in english["detection_rule"]["steps"]] == [
        "Personal baseline", "Reading outside what is expected", "Persistence",
        "Sustained drift", "Domain score", "Level",
    ]
    assert rule["baseline"]["statement"].startswith(
        "Each reading is compared with the crew member's own readings over the preceding "
    )
    assert " days, in the same physiological state and with a gap of " in (
        rule["baseline"]["statement"]
    )
    assert "mild if it falls in the most extreme " in rule["deviation"]["statement"]
    assert "does not go beyond mild" in rule["deviation"]["statement"]
    assert "a burst of severe readings" in rule["persistence"]["statement"]
    assert rule["trend"]["statement"].startswith("Line fitted to the readings of the last ")
    assert rule["points"]["statement"].startswith("Each finding adds points (mild ")
    assert rule["levels"]["statement"].startswith("By points: ")
    # El punto decimal es el del idioma y la cifra es la misma (`core/display.py`).
    es_rule = {step["key"]: step for step in spanish["detection_rule"]["steps"]}
    for key, step in rule.items():
        assert _figures(step["values"]) == _figures(es_rule[key]["values"])
        assert DIGITS.findall(step["statement"]) == DIGITS.findall(es_rule[key]["statement"])
    composed = [step["statement"] for step in rule.values()]
    seen: set[str] = set()
    for es_risk, en_risk in zip(spanish["risks"], english["risks"], strict=True):
        detection = en_risk["detection"]
        composed += [detection["summary"], detection["isolation_statement"]]
        composed += [row["statement"] for row in detection["danger_limits"]]
        composed += [item["statement"] for item in detection["environment"]]
        composed += [item["summary"] for item in detection["environment"]]
        composed += [en_risk["validation"]["statement"], en_risk["sensitivity"]["statement"]]
        assert DIGITS.findall(detection["summary"]) == DIGITS.findall(
            es_risk["detection"]["summary"]
        )
        seen.update(row["statement"].split(": ", 1)[1] for row in detection["danger_limits"])
        if en_risk["validation"]["keys"]:
            assert " from MMASH (" in en_risk["validation"]["statement"]
        if en_risk["sensitivity"]["keys"]:
            assert en_risk["sensitivity"]["statement"].startswith("Sensitivity measured on ")
            assert "by injecting deteriorations into MMASH physiology" in (
                en_risk["sensitivity"]["statement"]
            )
            assert en_risk["sensitivity"]["statement"].endswith(
                "Figures in compliance/external-validation.md."
            )
    assert any(text.startswith("below ") or " below " in text for text in seen)
    assert any("above " in text for text in seen)
    assert any("without physical exertion (rest, sleep, work or meal), " in text for text in seen)
    summaries = [risk["detection"]["summary"] for risk in english["risks"]]
    assert any("with forced autonomy, factor of up to " in text for text in summaries)
    assert any("no isolation factor" in text for text in summaries)
    assert any("active solar event (" in text and " points)" in text for text in summaries)
    assert any("cumulative dose (" in text for text in summaries)
    _sober([_own(text) for text in composed])
    spanish_words = re.compile(
        r"\b(lecturas?|indicador(es)?|desde|puntos|hallazgo|deriva|umbral|dosis|sin|con|por)\b"
    )
    for text in composed:
        assert spanish_words.search(_own(text)) is None, text


def _identifiers(payload: dict[str, Any]) -> list[Any]:
    found: list[Any] = [payload["count"], payload["severity_schema"]["rules_version"]]
    found += [(item["level"], item["min_score"]) for item in payload["severity_schema"]["levels"]]
    found += [item["key"] for item in payload["chain"]["links"]]
    found += [payload["detection_rule"]["isolation"]]
    for risk in payload["risks"]:
        found += [risk["risk_id"], risk["ridge"]["category"], risk["hrp_risk_id"]]
        found += [
            (item["key"], item["unit"], item["mode"], item["from_mmash"], item["display"])
            for item in risk["indicators"]
        ]
        found += [(item["id"], item["basis"]) for item in risk["countermeasures"]["items"]]
        found += [item["id"] for item in risk["evidence_refs"]]
        found += [risk["detection"]["indicators"], risk["detection"]["isolation_applies"]]
        found += [row["key"] for row in risk["detection"]["danger_limits"]]
        uncertainty = risk["uncertainty"]
        found += [uncertainty["quantified"], uncertainty["evaluation"]["evaluated_with"]]
        found += [risk["validation"]["dataset_id"], risk["sensitivity"]["reference"]]
    return found


def test_the_risks_route_answers_in_the_language_asked(client: TestClient) -> None:
    english = client.get("/api/risks", headers=ENGLISH_HEADERS).json()
    spanish = client.get("/api/risks").json()
    # Sin la cabecera, lo de siempre: el castellano de las constantes, letra por letra.
    assert spanish["uncertainty_statement"] == risk_entity.NOT_QUANTIFIED
    assert spanish["chain"]["basis"] == risk_entity.CHAIN_BASIS
    assert [item["display"] for item in spanish["chain"]["links"]] == [
        word for _, word in risk_entity.CHAIN_LINKS
    ]
    assert spanish["detection_rule"]["steps"][0]["display"] == "Línea base personal"
    # Con ella, el inglés; y ni un identificador ni una cifra distintos.
    assert english["uncertainty_statement"].startswith("EMMA does not quantify the uncertainty")
    assert [item["display"] for item in english["chain"]["links"]] == [
        "Hazard", "Effect", "Variable", "Data", "Detection", "Countermeasure",
    ]
    assert english["detection_rule"]["display"] == "Detection rule"
    assert english["detection_rule"]["validated_with"]["display"] == "Where it has been measured"
    assert _identifiers(english) == _identifiers(spanish)
    assert english["count"] == len(Domain)
    # Ninguna constante castellana de este módulo queda en lo servido en inglés.
    served = set(_strings(english))
    left = [
        word for word in _risk_words()
        if word in served and word not in ("Variable", "nominal")
    ]
    assert left == []
    for risk in english["risks"]:
        assert risk["uncertainty"]["statement"] == english["uncertainty_statement"]
        assert risk["human_system"]["basis"].startswith("EMMA's presentation map")
        assert risk["uncertainty"]["countermeasures"]["note"].startswith("A «demo» countermeasure")
        assert risk["detection"]["basis"].startswith("Read from the engine")


def test_the_risk_summary_of_a_region_is_served_in_english() -> None:
    spanish = risk_entity.summary(Domain.BONE)
    with i18n.use("en"):
        english = risk_entity.summary(Domain.BONE)
    assert spanish["uncertainty_statement"] == risk_entity.NOT_QUANTIFIED
    assert english["uncertainty_statement"].startswith("EMMA does not quantify")
    assert english["risk_id"] == spanish["risk_id"] == "bone"
    assert english["ridge"]["category"] == spanish["ridge"]["category"]
    assert english["hrp_risk"]["id"] == spanish["hrp_risk"]["id"]


def test_an_identifier_is_never_taken_for_a_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aunque alguien registrase un castellano que coincide con una clave, la clave no cambia."""
    monkeypatch.setitem(i18n._registry, "bone", "hueso-traducido")
    monkeypatch.setitem(i18n._registry, "dos palabras", "two words")
    with i18n.use("en"):
        served = risk_entity._served({
            "risk_id": "bone", "display": "bone", "note": "dos palabras", "key": "dos-palabras",
            "items": [{"id": "bone", "kind_display": "dos palabras"}], "count": 3, "none": None,
        })
    assert served == {
        "risk_id": "bone", "display": "hueso-traducido", "note": "two words",
        "key": "dos-palabras",
        "items": [{"id": "bone", "kind_display": "two words"}], "count": 3, "none": None,
    }
    value = {"note": "dos palabras"}
    assert risk_entity._served(value) is value
