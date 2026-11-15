"""Efectos e interacciones de contramedidas (§5.39.17; conversación de ideación).

«Una intervención puede mejorar una variable y empeorar otra»: la ficha de efectos dice sobre qué
se espera el beneficio y dónde cae cada efecto adverso que la biblioteca declara, y la nota de
co-adopción dice con qué otras contramedidas está adoptada a la vez un tripulante. Estas pruebas
fijan el contrato del fichero (una ficha por contramedida, dominios e indicadores del enumerado,
ningún efecto sin su nota), que la huella de reglas no cambia, que el veredicto no cambia, y lo que
el estado y la biblioteca sirven.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures, effects
from app.advisor.effects import (
    CO_ADOPTION_BASIS,
    NO_SOURCE_ON_INTERACTION,
    NOT_DECLARED,
    NOTE,
    EffectsError,
    co_adopted,
    validate,
    with_effects,
)
from app.advisor.recommendations import Advisor
from app.analysis.risk import CrewHealthStatus, DomainRisk, RiskLevel
from app.core import versioning
from app.environment.habitat import PARAMETERS
from app.ingest.codes import CATALOG, Domain
from app.text_guard import check

APP = Path(effects.__file__).resolve().parents[1]
RAW: dict[str, Any] = json.loads(effects.EFFECTS_PATH.read_text(encoding="utf-8"))
LIBRARY = countermeasures.library()
# Los únicos que pueden leer este módulo: las rutas que sirven el estado, la cadena anatómica y
# la biblioteca, y el arranque, que solo valida el fichero. Ni el análisis ni el asesor: no decide
# nada.
ALLOWED_IMPORTERS = {"api/routes.py", "api/countermeasures.py", "main.py"}
# Una ficha del registro de evidencia que existe (la cita la biblioteca): para la interacción
# sintética de las pruebas, no porque diga nada de dos contramedidas a la vez.
A_REGISTRY_REF = "ochmo-mtb-013"
A_QUOTE = "frase literal de la fuente"


def _raw(**override: Any) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    raw.update(override)
    return raw


def _entry_of(raw: dict[str, Any], ident: str) -> dict[str, Any]:
    return next(item for item in raw["effects"] if item["countermeasure_id"] == ident)


def _with_entry(ident: str, **override: Any) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    _entry_of(raw, ident).update(override)
    return raw


def _with_interaction(**override: Any) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    interaction = {
        "between": ["cv-exercise-session", "cv-hydration-salt"],
        "ref": A_REGISTRY_REF,
        "relevance": "lo que la fuente dice de hacer las dos a la vez",
        "quote": A_QUOTE,
    }
    interaction.update(override)
    raw["interactions"] = [interaction]
    return raw


# --------------------------------------------------------------------------- #
# El fichero real
# --------------------------------------------------------------------------- #


def test_every_countermeasure_has_its_card_and_no_card_is_for_nobody() -> None:
    loaded = effects.loaded()
    assert set(loaded.effects) == set(LIBRARY)
    assert loaded.interactions == ()


def test_an_adverse_effect_is_declared_exactly_when_the_library_writes_its_note() -> None:
    for ident, item in LIBRARY.items():
        card = effects.get(ident)
        assert card.declared == (item.adverse_effects_note is not None), ident
        if card.declared:
            assert card.adverse, ident
            for effect in card.adverse or ():
                if effect.affects.kind == "domain":
                    assert Domain(effect.affects.key).display == effect.affects.display
                else:
                    assert effect.affects.key in CATALOG
                    assert effect.affects.key not in Domain.__members__.values()


def test_the_benefit_is_on_the_domain_treated_or_the_cabin_parameter_checked() -> None:
    for ident, item in LIBRARY.items():
        card = effects.get(ident)
        if item.scope == "habitat":
            assert card.benefit_domain is None
            assert card.benefit_parameter in item.followup_checks
            assert card.benefit_parameter in PARAMETERS
            named = PARAMETERS[card.benefit_parameter].display
        else:
            assert card.benefit_domain is item.domain
            assert card.benefit_parameter is None
            named = item.domain.display if item.domain is not None else ""
        assert named in card.benefit_text
        # Sin cifra: la biblioteca no escribe cuánto, y la frase no la inventa (el «2» de «CO2»
        # es del nombre del parámetro, no una magnitud).
        plain = card.benefit_text.replace(named, "")
        assert not any(char.isdigit() for char in plain), card.benefit_text


def test_the_overview_counts_declared_and_not_declared_and_says_no_source_on_interactions() -> None:
    body = effects.overview()
    assert body["declared"] + body["not_declared"] == len(LIBRARY)
    assert body["declared"] == sum(
        1 for item in LIBRARY.values() if item.adverse_effects_note is not None
    )
    assert body["interactions"] == []
    assert body["interactions_note"] is not None and "ninguna fuente leída" in body[
        "interactions_note"
    ].lower()
    assert body["note"] == NOTE and body["co_adoption_basis"] == CO_ADOPTION_BASIS


def test_every_text_emma_writes_passes_the_language_guard() -> None:
    texts = [NOT_DECLARED, CO_ADOPTION_BASIS, NOTE, NO_SOURCE_ON_INTERACTION]
    for card in effects.loaded().effects.values():
        texts.append(card.benefit_text)
        for effect in card.adverse or ():
            texts += [effect.text, effect.basis]
    assert [(text, check(text)) for text in texts if check(text)] == []


def test_what_is_served_names_the_not_declared_and_never_an_empty_hole() -> None:
    card = effects.library_entry("cv-hydration-salt")
    assert card["adverse_declared"] is False
    assert card["adverse"] == [] and card["adverse_text"] == NOT_DECLARED
    assert card["co_adopted"] == [] and card["co_adoption_basis"] == CO_ADOPTION_BASIS
    declared = effects.library_entry("cv-exercise-session")
    assert declared["adverse_declared"] is True and declared["adverse_text"] is None
    assert {item["affects"] for item in declared["adverse"]} == {"indicator"}
    assert all(item["display"] and item["text"] and item["basis"] for item in declared["adverse"])


# --------------------------------------------------------------------------- #
# El contrato: lo que no carga
# --------------------------------------------------------------------------- #


def test_the_real_file_validates_against_the_library() -> None:
    assert set(validate(RAW, LIBRARY).effects) == set(LIBRARY)


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ([], "objeto con `effects`"),
        (_raw(effects="x"), "objeto con `effects`"),
        (_raw(interactions=None), "objeto con `effects`"),
        # Un id que no existe, uno que falta y uno repetido.
        (_raw(effects=[*RAW["effects"], {**RAW["effects"][1], "countermeasure_id": "nadie"}]),
         "no está en la biblioteca"),
        (_raw(effects=RAW["effects"][1:]), "sin ficha de efectos"),
        (_raw(effects=[*RAW["effects"], RAW["effects"][1]]), "ficha repetida"),
        ({**RAW, "effects": [*RAW["effects"][1:], {"countermeasure_id": "cv-exercise-session"}]},
         "countermeasure_id, benefit, adverse"),
        # El beneficio: sobre el dominio que trata, o el parámetro que comprueba.
        (_with_entry("cv-hydration-salt", benefit={"domain": "hepatic"}), "fuera del enumerado"),
        (_with_entry("cv-hydration-salt", benefit={"domain": "bone"}),
         "no es el dominio que la entrada trata"),
        (_with_entry("cv-hydration-salt", benefit={"parameter": "cabin-ppco2"}),
         "fuera del enumerado"),
        (_with_entry("cv-hydration-salt", benefit={"domain": "cardiovascular", "parameter": "x"}),
         "`benefit` es"),
        (_with_entry("hab-co2-sensor-crosscheck", benefit={"parameter": "cabin-ppo2"}),
         "no es el parámetro que la entrada comprueba"),
        (_with_entry("hab-co2-sensor-crosscheck", benefit={"parameter": "cabin-plasma"}),
         "fuera de los parámetros de cabina"),
        (_with_entry("hab-co2-sensor-crosscheck", benefit={"domain": "radiation"}),
         "fuera de los parámetros de cabina"),
        # Los efectos adversos: solo con la nota de la biblioteca, y sobre algo que exista.
        (_with_entry("cv-hydration-salt", adverse=[
            {"affects": {"domain": "bone"}, "text": "t", "basis": "b"}]), "no escribe su nota"),
        (_with_entry("cv-exercise-session", adverse=None), "no dice dónde cae ninguno"),
        (_with_entry("cv-exercise-session", adverse=[]), "al menos un efecto"),
        (_with_entry("cv-exercise-session", adverse=[
            {"affects": {"domain": "hepatic"}, "text": "t", "basis": "b"}]), "fuera del enumerado"),
        (_with_entry("cv-exercise-session", adverse=[
            {"affects": {"indicator": "liver-fibrosis"}, "text": "t", "basis": "b"}]),
         "fuera del catálogo"),
        (_with_entry("cv-exercise-session", adverse=[
            {"affects": {"organ": "liver"}, "text": "t", "basis": "b"}]), "`affects` desconocido"),
        (_with_entry("cv-exercise-session", adverse=[
            {"affects": {"domain": "bone", "indicator": "calcium"}, "text": "t", "basis": "b"}]),
         "`affects` es"),
        # Una clave que no es texto se dice aquí, no como `TypeError` de una lista no buscable.
        (_with_entry("cv-exercise-session", adverse=[
            {"affects": {"indicator": ["heart-rate"]}, "text": "t", "basis": "b"}]),
         "la clave en texto"),
        (_with_entry("cv-exercise-session", adverse=[
            {"affects": {"domain": {"x": 1}}, "text": "t", "basis": "b"}]), "la clave en texto"),
        (_with_entry("hab-co2-sensor-crosscheck", benefit={"parameter": ["cabin-ppco2"]}),
         "fuera de los parámetros de cabina"),
        (_with_entry("cv-hydration-salt", benefit={"domain": ["cardiovascular"]}),
         "fuera del enumerado"),
        (_with_interaction(between=["cv-exercise-session", ["cv-hydration-salt"]]),
         "dos ids distintos"),
        (_with_entry("cv-exercise-session", adverse=[
            {"affects": {"indicator": "heart-rate"}, "text": " ", "basis": "b"}]), "`text` vacío"),
        (_with_entry("cv-exercise-session", adverse=[
            {"affects": {"indicator": "heart-rate"}, "text": "t"}]), "affects, text, basis"),
        (_with_entry("cv-exercise-session", adverse=[
            {"affects": {"indicator": "heart-rate"},
             "text": "Debe suspenderse el tratamiento si sube.", "basis": "b"}]),
         "suena a pauta u orden"),
        # Las interacciones: dos ids distintos de la biblioteca y una ficha del registro.
        (_with_interaction(between=["cv-exercise-session"]), "dos ids distintos"),
        (_with_interaction(between=["cv-exercise-session", "cv-exercise-session"]),
         "dos ids distintos"),
        (_with_interaction(between=["cv-exercise-session", "nadie"]), "no están en la biblioteca"),
        (_with_interaction(ref="no-such-card"), "no está en el registro"),
        (_with_interaction(quote="  "), "`quote` vacía"),
        (_with_interaction(relevance="Debe tratarse con las dos."), "suena a pauta u orden"),
        ({**_with_interaction(), "interactions": [_with_interaction()["interactions"][0]] * 2},
         "dos veces"),
    ],
)
def test_what_does_not_match_the_library_is_refused(raw: Any, reason: str) -> None:
    with pytest.raises(EffectsError, match=reason):
        validate(raw, LIBRARY)


def test_an_interaction_with_its_registry_card_loads_and_is_served() -> None:
    loaded = validate(_with_interaction(), LIBRARY)
    [interaction] = loaded.interactions
    assert interaction.between == ("cv-exercise-session", "cv-hydration-salt")
    assert interaction.involves("cv-hydration-salt", "cv-exercise-session")
    served = interaction.to_dict()
    assert served["quote"] == A_QUOTE and served["source"]["id"] == A_REGISTRY_REF


# --------------------------------------------------------------------------- #
# Dos a la vez
# --------------------------------------------------------------------------- #


def _followup(ident: str, index: int, state: str) -> dict[str, Any]:
    return {
        "countermeasure": {"id": ident, "action": LIBRARY[ident].action},
        "adoption_index": index,
        "adopted_at": f"2026-12-0{index}T08:00:00+00:00",
        "state": state,
    }


def test_alone_or_with_nothing_else_open_there_is_no_co_adoption_note() -> None:
    mine = _followup("cv-exercise-session", 1, "in_window")
    assert co_adopted("cv-exercise-session", []) == []
    assert co_adopted("cv-exercise-session", [mine]) == []
    # Un seguimiento cerrado no es «adoptada ahora».
    closed = _followup("cv-hydration-salt", 2, "closed")
    assert co_adopted("cv-exercise-session", [mine, closed]) == []


def _two_open() -> list[dict[str, Any]]:
    return [
        _followup("cv-exercise-session", 1, "in_window"),
        _followup("cv-hydration-salt", 2, "due"),
    ]


def test_two_open_at_once_each_names_the_other_and_says_no_source_read() -> None:
    opened = _two_open()
    [note] = co_adopted("cv-exercise-session", opened)
    assert note["countermeasure_id"] == "cv-hydration-salt" and note["adoption_index"] == 2
    assert note["adopted"] is True and note["source"] is None
    assert note["text"] == (
        f"Adoptada junto con «{LIBRARY['cv-hydration-salt'].action}»: {NO_SOURCE_ON_INTERACTION}."
    )
    [other] = co_adopted("cv-hydration-salt", opened)
    assert other["countermeasure_id"] == "cv-exercise-session" and other["adopted"] is True
    assert check(note["text"]) == [] and check(other["text"]) == []


def test_the_same_countermeasure_adopted_twice_without_closing_is_one_note_not_two() -> None:
    """La ruta de adoptar no impide readoptar con el seguimiento abierto: es la misma a la vez."""
    opened = [
        _followup("cv-exercise-session", 1, "in_window"),
        _followup("cv-hydration-salt", 2, "in_window"),
        _followup("cv-hydration-salt", 3, "due"),
    ]
    [note] = co_adopted("cv-exercise-session", opened)
    assert note["countermeasure_id"] == "cv-hydration-salt"
    # Se cuenta por su primera adopción.
    assert note["adoption_index"] == 2


def test_a_broken_effects_file_stops_the_start_with_its_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lo sirven `/status` y la biblioteca: un fichero roto no espera a la primera petición."""
    from app import main

    def broken() -> effects.Loaded:
        raise EffectsError("efectos de x: no está en la biblioteca")

    monkeypatch.setattr(effects, "loaded", broken)
    with pytest.raises(main.ReadFileError, match="countermeasure_effects.json.*no está en la"):
        main.check_read_files()


def test_a_recommendation_not_adopted_gets_the_note_in_the_conditional() -> None:
    opened = [_followup("cv-exercise-session", 1, "in_window")]
    [note] = co_adopted("cv-repeat-rest", opened)
    assert note["adopted"] is False
    assert note["text"].startswith("Si se adopta, irá junto con «")
    assert note["text"].endswith(f"en seguimiento: {NO_SOURCE_ON_INTERACTION}.")
    assert check(note["text"]) == []


def test_with_a_source_read_the_note_carries_its_phrase_and_its_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = validate(_with_interaction(), LIBRARY)
    monkeypatch.setattr(effects, "loaded", lambda: loaded)
    opened = _two_open()
    [note] = co_adopted("cv-exercise-session", opened)
    assert A_QUOTE in note["text"] and NO_SOURCE_ON_INTERACTION not in note["text"]
    assert note["source"]["id"] == A_REGISTRY_REF
    # La pareja al revés lleva la misma fuente.
    [other] = co_adopted("cv-hydration-salt", opened)
    assert other["source"]["id"] == A_REGISTRY_REF
    # Y una tercera, sin fuente con ninguna de las dos, sigue diciendo que no la hay.
    for third in co_adopted("cv-repeat-rest", opened):
        assert third["source"] is None and NO_SOURCE_ON_INTERACTION in third["text"]


def test_annotating_only_adds_a_field_in_the_same_order() -> None:
    recommendations = [
        {"domain": "cardiovascular", "action": "a",
         "countermeasure": {"id": "cv-exercise-session", "action": "a"}},
        {"domain": "bone", "action": "b", "countermeasure": None},
        {"domain": "cardiovascular", "action": "c",
         "countermeasure": {"id": "cv-hydration-salt", "action": "c"}},
    ]
    annotated = with_effects(recommendations, [_followup("cv-exercise-session", 1, "in_window")])
    assert [item["action"] for item in annotated] == ["a", "b", "c"]
    for before, after in zip(recommendations, annotated, strict=True):
        assert {key: value for key, value in after.items() if key != "effects"} == before
    assert annotated[1]["effects"] is None
    assert annotated[0]["effects"]["benefit"]["domain"] == "cardiovascular"
    assert annotated[0]["effects"]["co_adopted"] == []
    [note] = annotated[2]["effects"]["co_adopted"]
    assert note["adopted"] is False and note["countermeasure_id"] == "cv-exercise-session"


# --------------------------------------------------------------------------- #
# No decide nada: ni el veredicto ni la huella
# --------------------------------------------------------------------------- #


def _status(domain: Domain, level: RiskLevel) -> CrewHealthStatus:
    return CrewHealthStatus(
        subject="crew-01",
        domains={domain: DomainRisk(domain, 50.0, level, ("x",))},
        comms=None, isolation_factor=1.0, cumulative_dose_msv=0.0, dose_limit_msv=600.0,
        active_solar_event=None,
    )


def test_no_module_of_the_engine_or_the_advisor_imports_the_effects() -> None:
    importers = set()
    for path in APP.rglob("*.py"):
        if path == Path(effects.__file__):
            continue
        text = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text)):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or "", *(alias.name for alias in node.names)]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            if any(name.endswith("effects") for name in names):
                importers.add(path.relative_to(APP).as_posix())
        if "countermeasure_effects.json" in text:
            importers.add(path.relative_to(APP).as_posix())
    assert importers == ALLOWED_IMPORTERS


def test_the_advisor_offers_the_same_with_or_without_the_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def offered() -> list[tuple[str, str | None, str]]:
        return [
            (str(item.domain), item.countermeasure.id if item.countermeasure else None,
             str(item.urgency))
            for domain in Domain
            for level in (RiskLevel.WATCH, RiskLevel.CONCERN, RiskLevel.CRITICAL)
            for item in Advisor().recommend(_status(domain, level))
        ]

    before = offered()
    monkeypatch.setattr(effects, "loaded", lambda: effects.Loaded(effects={}, interactions=()))
    assert offered() == before


def test_the_rules_fingerprint_does_not_read_the_effects_file() -> None:
    rules = versioning.rules()
    # Los periodos de las rutinas entran en la huella desde la monitorización intensificada
    # (`routines`); los efectos y las contramedidas en investigación siguen fuera.
    assert set(rules) == {"parameters", "catalog", "habitat", "countermeasures_sha256", "routines"}
    assert rules["countermeasures_sha256"] == hashlib.sha256(
        countermeasures.LIBRARY_PATH.read_bytes()
    ).hexdigest()
    assert effects.EFFECTS_PATH != countermeasures.LIBRARY_PATH
    text = json.dumps(rules, ensure_ascii=False)
    assert "countermeasure_effects" not in text and NOT_DECLARED not in text
    assert versioning.rules_version() == f"reglas@{versioning.fingerprint(rules)}"
    # Y `versioning.py` no nombra el fichero ni el módulo.
    source = Path(str(versioning.__file__)).read_text(encoding="utf-8")
    assert "effects" not in source


# --------------------------------------------------------------------------- #
# Lo servido
# --------------------------------------------------------------------------- #


@pytest.fixture
def deconditioning(client: TestClient) -> dict[str, Any]:
    assert client.post(
        "/api/simulate", params={"scenario": "cardiovascular-deconditioning", "days": 40}
    ).status_code == 201
    status: dict[str, Any] = client.get("/api/status").json()
    return status


def test_every_recommendation_carries_the_effects_of_its_countermeasure(
    deconditioning: dict[str, Any],
) -> None:
    recommendations = deconditioning["recommendations"]
    assert recommendations
    for item in recommendations:
        card = item["effects"]
        assert card["countermeasure_id"] == item["countermeasure"]["id"]
        assert card["benefit"]["domain"] == item["domain"]
        assert card["benefit"]["text"].startswith("Beneficio esperado")
        assert card["adverse_declared"] == (
            item["countermeasure"]["adverse_effects_note"] is not None
        )
        assert card["co_adopted"] == []


def test_two_adopted_at_once_each_carries_the_note_about_the_other(
    client: TestClient, deconditioning: dict[str, Any],
) -> None:
    offered = [item["countermeasure"]["id"] for item in deconditioning["recommendations"]]
    assert len(offered) >= 2, "el escenario ofrece al menos dos contramedidas"
    first, second = offered[:2]
    reference = deconditioning["data"]["reference_time"]
    for ident in (first, second):
        adopted = client.post("/api/countermeasures/adopt", json={
            "countermeasure_id": ident, "reference_time": reference, "adopted_by": "CDR",
        })
        assert adopted.status_code == 201, adopted.text

    status = client.get("/api/status").json()
    assert {item["countermeasure"]["id"] for item in status["followups"]} == {first, second}
    by_id = {item["countermeasure"]["id"]: item["effects"] for item in status["recommendations"]}
    [note] = by_id[first]["co_adopted"]
    assert note["countermeasure_id"] == second and note["adopted"] is True
    assert note["text"].startswith("Adoptada junto con «")
    assert note["text"].endswith(f"{NO_SOURCE_ON_INTERACTION}.")
    [other] = by_id[second]["co_adopted"]
    assert other["countermeasure_id"] == first and other["adopted"] is True
    # Una tercera recomendación, si la hay, lo dice en condicional y nombra a las dos.
    for ident, card in by_id.items():
        if ident in (first, second):
            continue
        assert {item["countermeasure_id"] for item in card["co_adopted"]} == {first, second}
        assert all(item["adopted"] is False for item in card["co_adopted"])
    # La versión de reglas es la misma que antes de adoptar: la nota no decide nada.
    assert status["rules_version"] == deconditioning["rules_version"]


def test_the_library_serves_the_effects_of_every_entry_and_the_counts(
    client: TestClient,
) -> None:
    body = client.get("/api/countermeasures").json()
    for item in body["countermeasures"]:
        card = item["effects"]
        assert card["countermeasure_id"] == item["id"]
        assert card["co_adopted"] == []
        if item["scope"] == "habitat":
            assert card["benefit"]["parameter"] in item["followup_checks"]
        else:
            assert card["benefit"]["domain"] == item["domain"]
    overview = body["effects_overview"]
    assert overview["declared"] == sum(
        1 for item in body["countermeasures"] if item["adverse_effects_note"] is not None
    )
    assert overview["declared"] + overview["not_declared"] == len(body["countermeasures"])
    assert overview["interactions"] == []
    assert overview["note"] == NOTE
    # El resumen no tiene la forma de una ficha, y no se llama como ella.
    assert "effects" not in body


def test_the_library_header_is_not_silent_when_an_interaction_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with_one = validate(_with_interaction(), LIBRARY)
    monkeypatch.setattr(effects, "loaded", lambda: with_one)
    note = effects.overview()["interactions_note"]
    assert "1" in note and "ninguna fuente" not in note.lower()
    assert not check(note)


def test_the_cards_are_validated_again_against_a_replaced_library() -> None:
    first = effects.loaded()
    assert effects.loaded() is first
    monkey = dict(countermeasures.library())
    original = countermeasures.library
    countermeasures.library = lambda: monkey  # type: ignore[assignment]
    try:
        assert effects.loaded() is not first
    finally:
        countermeasures.library = original
        effects._validated = None
