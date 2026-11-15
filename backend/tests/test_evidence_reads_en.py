"""Lo leído de fisiología y de credibilidad, en inglés, frente al castellano que sigue al lado.

Por qué existe: estos cinco cargadores (`credibility`, `flight_direction`, `light_exposure`,
`cycle_physiology`, `menopause_physiology`) son contratos de lectura: qué dice una fuente, en
quién, con qué medida, y qué se buscó y no se encontró. Su inglés es un fichero hermano
(`<nombre>_read.en.json`) emparejado por la cadena castellana entera: si el castellano cambia una
coma, la cadena deja de traducirse sin que nada falle; y un inglés que cambie una cifra, afirme
más que el castellano o suene a orden médica miente en el otro idioma. Aquí se coteja la cobertura
de lo que redacta EMMA, que las cifras sean las mismas, que las citas de la fuente no se toquen y
que lo servido en castellano sea idéntico a lo de antes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core import i18n
from app.evidence import (
    credibility,
    cycle_physiology,
    flight_direction,
    light_exposure,
    menopause_physiology,
)
from app.ingest.codes import CATALOG
from tests.conftest import ENGLISH_HEADERS

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_FORBIDDEN = re.compile(
    r"certified|validated|proves|confirms that|diagnos|administer|must take|should take",
    re.IGNORECASE,
)
_SPANISH_ONLY = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
# Nombres propios con tilde que el inglés conserva.
_PROPER_NAMES = ("Gimunová",)
_QUOTED = re.compile(r"«([^»]*)»")
# Lo que va entre comillas angulares en castellano y NO es una cita de la fuente: palabras de
# EMMA, que se traducen. Todo lo demás entre comillas tiene que salir igual en inglés.
_OWN_WORDS = frozenset({
    "simulado", "¿Acertaron las proyecciones?", "no es un pronóstico clínico", "sube", "baja",
    "frecuentes",
})


def _raw(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _fields(items: list[dict[str, Any]], *fields: str) -> list[str]:
    return [item[field] for item in items for field in fields if field in item]


def _credibility_texts() -> list[str]:
    """Lo que redacta EMMA en `credibility_read.json` y se sirve."""
    raw = _raw(credibility.READ_PATH)
    block = raw["criticality"]
    texts = [text for _where, text in credibility._emma_texts(raw)]
    texts += [block[field] for field in ("title", "about", "not_applied")]
    texts += _fields(block["statements"], "label", "where")
    texts += _fields(block["axes"], "name_es", "where")
    for layer in raw["layers"]:
        texts += [layer["display"], *layer["served_in"]]
        texts += [layer["model_note"]] if layer["model_note"] else []
        texts += [*layer["factors"].values(), *layer["criticality"].values()]
    return texts


def _flight_direction_texts() -> list[str]:
    raw = _raw(flight_direction.READ_PATH)
    texts = _fields(raw["statements"], "where", "compared_with", "population")
    texts += _fields(list(raw["indicators"].values()), "scope", "searched")
    return texts


def _light_exposure_texts() -> list[str]:
    raw = _raw(light_exposure.READ_PATH)
    recommendations = raw["recommendations"]
    texts = _fields(raw["statements"], "label", "where")
    texts += [*raw["searched"], recommendations["quantity"], recommendations["setting"]]
    texts += _fields(recommendations["items"], "label")
    return texts


def _cycle_texts() -> list[str]:
    raw = _raw(cycle_physiology.READ_PATH)
    texts = [raw["suppression"]["where"], raw["suppression"]["text"]]
    texts += _fields(raw["findings"], "where", "measure", "population")
    for phases in raw["indicators"].values():
        texts += _fields(list(phases.values()), "note", "searched")
    return texts


def _menopause_texts() -> list[str]:
    raw = _raw(menopause_physiology.READ_PATH)
    texts = _fields(raw["findings"], "where", "measure", "population")
    texts += _fields(list(raw["topics"].values()), "context", "note", "searched")
    texts += [raw["in_flight"]["text"], raw["in_flight"]["searched"]]
    return texts


def _same_in_both_credibility(text: str) -> bool:
    """Secciones que la norma nombra en inglés o con solo su número, y rutas sin texto detrás."""
    return (
        text in {"Foreword", "Document History Log, Revision B"}
        or re.fullmatch(r"(\[M&S \d+\]|§[\d.]+)(,? ?(\[M&S \d+\]|p\. \d+))*", text) is not None
        or (text.startswith("/api/") and "(" not in text)
    )


def _same_in_both_light(text: str) -> bool:
    """Sitios de la fuente escritos enteros en inglés: el título de su sección."""
    return text == "§6.8.2.4, [V2 6117], Rationale" or text.startswith(
        "Expert consensus-based recommendations, «"
    )


def _none(_text: str) -> bool:
    return False


READS: dict[str, tuple[Path, Callable[[], list[str]], Callable[[str], bool]]] = {
    "credibility": (credibility.READ_PATH, _credibility_texts, _same_in_both_credibility),
    "flight_direction": (flight_direction.READ_PATH, _flight_direction_texts, _none),
    "light_exposure": (light_exposure.READ_PATH, _light_exposure_texts, _same_in_both_light),
    "cycle_physiology": (cycle_physiology.READ_PATH, _cycle_texts, _none),
    "menopause_physiology": (menopause_physiology.READ_PATH, _menopause_texts, _none),
}


def _overlay(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = _raw(i18n.overlay_path(path))["strings"]
    return loaded


def _numbers(text: str) -> list[str]:
    return sorted(found.replace(",", ".") for found in _NUMBER.findall(text))


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for inner in value.values():
            yield from _strings(inner)
    elif isinstance(value, list | tuple):
        for inner in value:
            yield from _strings(inner)


def _shape(value: Any) -> Any:
    """La forma de una respuesta sin sus textos: claves, longitudes y lo que no es texto."""
    if isinstance(value, dict):
        return {key: _shape(inner) for key, inner in value.items()}
    if isinstance(value, list | tuple):
        return [_shape(inner) for inner in value]
    return "texto" if isinstance(value, str) else value


def _pick(value: Any, *fields: str) -> list[Any]:
    """Los valores de esos campos, a cualquier profundidad y en orden."""
    found: list[Any] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            if key in fields:
                found.append(inner)
            else:
                found.extend(_pick(inner, *fields))
    elif isinstance(value, list | tuple):
        for inner in value:
            found.extend(_pick(inner, *fields))
    return found


# --------------------------------------------------------------------------- #
# Los ficheros hermanos
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", list(READS))
def test_every_text_emma_writes_and_serves_has_its_english(name: str) -> None:
    path, texts, same_in_both = READS[name]
    assert i18n.missing(path, texts(), skip=same_in_both) == []


@pytest.mark.parametrize("name", list(READS))
def test_the_overlay_only_translates_what_emma_writes(name: str) -> None:
    """Ni una cita de la fuente, ni un identificador, ni una cadena que ya no está en el fichero."""
    path, texts, same_in_both = READS[name]
    written = set(texts())
    strings = _overlay(path)
    assert sorted(set(strings) - written) == []
    assert [text for text in strings if same_in_both(text)] == []
    raw = _raw(path)
    source_words = set(_strings(_pick(
        raw, "quote", "literal", "question", "name", "id", "ref", "model_version", "sites",
        "tests",
    )))
    assert source_words & set(strings) == set()
    assert all(english.strip() and english != spanish for spanish, english in strings.items())


@pytest.mark.parametrize("name", list(READS))
def test_the_english_keeps_every_figure(name: str) -> None:
    """Las mismas cifras en los dos idiomas (salvo la coma decimal): n, días, porcentajes, años."""
    different = [
        (spanish, english)
        for spanish, english in _overlay(READS[name][0]).items()
        if _numbers(spanish) != _numbers(english)
    ]
    assert different == []


@pytest.mark.parametrize("name", list(READS))
def test_the_english_claims_no_more_and_orders_nothing(name: str) -> None:
    for english in _overlay(READS[name][0]).values():
        assert _FORBIDDEN.search(english) is None, english
        plain = english
        for proper in _PROPER_NAMES:
            plain = plain.replace(proper, "")
        assert _SPANISH_ONLY.search(plain) is None, english


@pytest.mark.parametrize("name", list(READS))
def test_a_quote_inside_a_text_stays_in_the_language_of_its_source(name: str) -> None:
    for spanish, english in _overlay(READS[name][0]).items():
        for quoted in _QUOTED.findall(spanish):
            if quoted not in _OWN_WORDS:
                assert f"«{quoted}»" in english, (quoted, english)


def test_the_english_of_the_credibility_cards_passes_the_contract_of_the_spanish() -> None:
    """Ni nivel, ni reclamo de conformidad o validación, ni categoría de la matriz."""
    for english in _overlay(credibility.READ_PATH).values():
        credibility._emma_writes("inglés", english)
    with i18n.use("en"):
        credibility._emma_writes("nota", credibility.payload()["note"])


def test_the_factor_names_are_the_ones_of_the_standard() -> None:
    """`name_es` en inglés es el nombre oficial del factor (`name`), no otra traducción."""
    raw = _raw(credibility.READ_PATH)
    strings = _overlay(credibility.READ_PATH)
    for factor in raw["factors"]:
        assert strings[factor["name_es"]] == factor["name"]
    # Los grupos y los ejes llevan en castellano una glosa, no el nombre: en inglés también, y
    # el nombre oficial (`name`) va al lado en la consola, sin repetirse.
    for item in (*raw["groups"], *raw["criticality"]["axes"]):
        assert item["name"] not in strings[item["name_es"]]


# --------------------------------------------------------------------------- #
# Lo que se sirve
# --------------------------------------------------------------------------- #


def _served() -> dict[str, Callable[[], Any]]:
    return {
        "credibility": credibility.payload,
        "flight_direction": lambda: flight_direction.for_profile(list(CATALOG)),
        "light_exposure": light_exposure.summary,
        "cycle_physiology": lambda: [cycle_physiology.table(), cycle_physiology.suppression()],
        "menopause_physiology": lambda: [
            menopause_physiology.table(), menopause_physiology.in_flight(),
        ],
    }


@pytest.mark.parametrize("name", list(READS))
def test_the_answer_changes_language_and_nothing_else(name: str) -> None:
    serve = _served()[name]
    spanish = serve()
    with i18n.use("en"):
        english = serve()
    # El castellano de después es el de antes: el inglés no se queda en ninguna caché.
    assert serve() == spanish
    assert _shape(english) == _shape(spanish)
    # Lo que es de la fuente, los identificadores y las cifras no cambian.
    kept = (
        "quote", "literal", "question", "name", "id", "ref", "key", "url", "source", "read_on",
        "direction", "evidence", "observation_type", "model_version", "sites", "tests", "low",
        "high", "unit", "phase", "subject", "kind", "indicator", "refs", "period", "extent",
        "searched_refs", "group", "axis", "magnitude",
    )
    assert _pick(english, *kept) == _pick(spanish, *kept)
    # Ningún texto de EMMA con inglés se queda en castellano.
    strings = _overlay(READS[name][0])
    assert [text for text in _strings(english) if text in strings] == []
    assert any(text in strings for text in _strings(spanish))


def test_the_credibility_cards_read_in_english(english: None) -> None:
    body = credibility.payload()
    assert body["title"] == "Credibility of each layer that predicts or infers"
    assert body["note"].startswith("What there is under each NASA-STD-7009B credibility factor")
    assert "INFERRED or PREDICTED" in body["note"]
    assert {layer["observation_type_text"] for layer in body["layers"]} == {
        "INFERRED", "PREDICTED",
    }
    assert {source["extent_text"] for source in body["sources"]} == {"read in part"}
    layer = body["layers"][0]
    assert layer["display"] == "Projection of drifts to the relevance horizon"
    assert [factor["name_es"] for factor in layer["factors"]][:3] == [
        "M&S Data Pedigree", "M&S Verification", "M&S Validation",
    ]
    states = {factor["id"]: factor["state"] for factor in layer["factors"]}
    assert states["validation"].startswith("None against a referent.")
    assert body["not_assessed"].startswith("EMMA has not assessed any layer")
    assert "has not applied the Appendix D matrix" in body["criticality"]["not_applied"]
    assert body["statements"][0]["quote"].startswith("ensuring the credibility of the results")
    assert "Ninguna" not in json.dumps(body, ensure_ascii=False)


def test_the_flight_direction_reads_in_english(english: None) -> None:
    block = flight_direction.for_profile(["heart-rate", "pvt-mean-rt", "cortisol-salivary", "tsh"])
    assert block["note"].startswith("What was observed on other flights, not what is expected")
    by_key = {row["key"]: row for row in block["indicators"]}
    rate = by_key["heart-rate"]
    assert rate["direction_display"] == "no change"
    assert rate["text"] == "On other flights no change was observed."
    first = rate["statements"][0]
    assert first["compared_with_display"].startswith("Compared with: before flight")
    assert first["population"].startswith("6 male astronauts, 2 to 6 months on the ISS")
    assert first["where"] == "Abstract" and first["extent_text"] == "read in part"
    assert first["quote_display"] == f"«{first['quote']}»"
    contested = by_key["cortisol-salivary"]
    assert contested["direction_display"] == "contested"
    assert contested["text"] == (
        "Contested: the sentences read do not agree (1 sentence: rises; 1 sentence: no change)."
    )
    searched = by_key["tsh"]
    assert searched["direction_display"] == "no source"
    assert searched["text"] == "No source read on its direction in flight."
    assert searched["searched_display"].startswith("Searched and not found: on Skylab (Leach")
    assert block["statement"] == (
        "4 indicators analysed: 3 with a direction read on other flights "
        "(rises: 1; no change: 1; contested: 1) and 1 with no source."
    )
    assert flight_direction.for_profile([])["statement"] == (
        "No indicator analysed: there is no direction in flight to show."
    )
    not_searched = flight_direction.for_indicator("mood-valence")
    if not_searched["searched"] is None and not_searched["direction"] == "no_source":
        assert not_searched["text"].endswith("it has not been searched for.")


def test_the_personal_light_exposure_reads_in_english(english: None) -> None:
    body = light_exposure.summary()
    assert body["display"] == "Personal light exposure"
    assert body["label"] == "context read; not assessed"
    assert body["status"].startswith("No personal limit published by NASA")
    assert "None of this is compared with any reading" in body["not_measured"]
    assert body["recommendations"]["note"].endswith("They are not a flight limit.")
    assert body["recommendations"]["setting"] == "indoor environments on Earth"
    labels = [item["label"] for item in body["recommendations"]["items"]]
    assert labels[0] == "By day (minimum)"
    assert all("lux" in item["literal"] for item in body["recommendations"]["items"])
    assert body["searched"][0].startswith("NASA-STD-3001 Vol 2 Rev F: [V2 8055]")
    assert "Neither is a light dose for a person." in body["searched"][0]


def test_the_cycle_and_menopause_reads_in_english(english: None) -> None:
    rows = {(row["key"], row["phase"]): row for row in cycle_physiology.table()}
    luteal = rows[("body-temperature", "luteal")]
    assert luteal["phase_display"] == "luteal phase"
    assert luteal["evidence_display"] == "documented magnitude"
    assert luteal["note"].startswith("The figure comes from core temperature (0.3 to 0.7 °C")
    assert {row["evidence_display"] for row in rows.values()} <= {
        "documented magnitude", "documented direction", "contested", "searched and not found",
    }
    suppression = cycle_physiology.suppression()
    assert suppression["text"].endswith("this variation refers to women with a natural cycle.")
    assert suppression["quote"].startswith("During long-duration missions")
    topics = menopause_physiology.table()
    assert {row["subject_display"] for row in topics} == {
        "hot flashes", "perimenopause", "bone",
    }
    assert {row["unit_display"] for row in topics} >= {"bpm", "°C", "years"}
    flight = menopause_physiology.in_flight()
    assert flight["evidence_display"] == "searched and not found"
    assert flight["text"].startswith("Nothing about menopause has been measured in flight")
    assert all(_SPANISH_ONLY.search(item["measure"]) is None for item in flight["found"])


def test_the_spanish_vocabulary_is_still_the_one_the_loaders_validate() -> None:
    """Las tablas castellanas no se mueven: las leen los validadores y los mensajes de rechazo."""
    assert flight_direction.DIRECTION_DISPLAY["contested"] == "discutido"
    assert cycle_physiology.EVIDENCE["established"] == "magnitud documentada"
    assert cycle_physiology.PHASES["luteal"] == "fase lútea"
    assert menopause_physiology.SUBJECTS["hot_flash"] == "sofocos"
    assert set(flight_direction._DIRECTION_EN) == set(flight_direction.DIRECTION_DISPLAY)
    assert set(cycle_physiology._EVIDENCE_EN) == set(cycle_physiology.EVIDENCE)
    assert set(cycle_physiology._PHASES_EN) == set(cycle_physiology.PHASES)
    assert set(menopause_physiology._SUBJECTS_EN) == set(menopause_physiology.SUBJECTS)
    assert set(menopause_physiology._UNITS_EN) == set(menopause_physiology.UNITS)
    assert set(credibility._OBSERVATION_TYPES_EN) == set(credibility.OBSERVATION_TYPES)
    # Cuánto se leyó: la tabla castellana es de otro módulo, y cada rótulo suyo tiene inglés.
    assert set(credibility._EXTENT_TEXT_EN) == set(credibility.EXTENTS.values())
    assert set(flight_direction._EXTENT_TEXT_EN) == set(flight_direction.EXTENTS.values())
    assert set(light_exposure._EXTENT_TEXT_EN) == set(light_exposure.EXTENTS.values())


# --------------------------------------------------------------------------- #
# Las rutas
# --------------------------------------------------------------------------- #


def test_the_routes_answer_in_the_language_asked(client: TestClient) -> None:
    spanish = client.get("/api/framework").json()["credibility"]
    english = client.get("/api/framework", headers=ENGLISH_HEADERS).json()["credibility"]
    assert spanish == credibility.payload()
    assert english["title"] == "Credibility of each layer that predicts or infers"
    assert spanish["title"] == "Credibilidad de cada capa que predice o infiere"
    assert client.get("/api/framework").json()["credibility"] == spanish

    def light(headers: dict[str, str] | None) -> dict[str, Any]:
        body = client.get("/api/habitat/parameters", headers=headers).json()
        shown = {item["key"]: item for item in body["display_only"]}
        found: dict[str, Any] = shown["cabin-light"]["personal_exposure"]
        return found

    assert light(None) == light_exposure.summary()
    assert light(ENGLISH_HEADERS)["display"] == "Personal light exposure"
    assert light(None)["display"] == "Exposición personal a la luz"

    seeded = client.post("/api/simulate", params={"scenario": "spe-event", "days": 3})
    assert seeded.status_code == 201
    profile = client.get("/api/baseline-profile", headers=ENGLISH_HEADERS).json()
    assert profile["flight_direction"]["note"].startswith("What was observed on other flights")
    again = client.get("/api/baseline-profile").json()["flight_direction"]
    assert again["note"] == flight_direction.FRAME
    assert again["indicators"] and profile["flight_direction"]["indicators"]
