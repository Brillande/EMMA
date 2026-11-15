"""La biblioteca de contramedidas para leerla entera, y la familia de cada entrada (§5.34.1).

La base de conocimiento (§15, P1) pide «contramedidas por RIDGE: biblioteca evidence-linked de
acciones y recursos», y el usuario decidio el 2026-10-21 que cada entrada lleve su familia de un
vocabulario cerrado, con la farmacologica fuera del alcance de EMMA. Estas pruebas fijan: que la
carga rechaza una familia ausente, desconocida o farmacologica; que el reparto de las cuarenta
entradas es el escrito (por lo que la accion es); que la API agrupa por RIDGE sin perder ni
repetir ninguna; que los textos nuevos no suenan a orden medica; y que la familia no cambia que
se recomienda.
"""

import dataclasses
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.advisor.countermeasures import (
    FAMILIES,
    FAMILY_BASIS,
    IN_SCOPE_FAMILIES,
    LIBRARY_NOTE,
    PHARMACOLOGICAL,
    RIDGE_BASIS,
    LibraryError,
    load,
)
from app.advisor.recommendations import Advisor
from app.analysis.risk import CrewHealthStatus, DomainRisk, RiskLevel
from app.ingest.codes import Domain, Ridge
from app.text_guard import check

# El reparto, entrada a entrada. Escrito aqui para que un cambio de familia sea deliberado: se
# asigna por lo que la accion es (`FAMILIES`, criterio de cada una).
PHYSICAL = {"cv-exercise-session", "rad-storm-shelter", "bone-resistive-load"}
OPERATIONAL = {
    "bh-protect-sleep", "bh-circadian-lighting", "bh-social-contact", "rad-shielded-module",
    "rad-hold-eva", "imm-hygiene", "gu-hydration-target", "nut-menu-variety",
}


def _entry(**override: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": "x", "domain": "cardiovascular", "action": "Repetir la medida.",
        "indication": "i", "crew_time_minutes": None,
        "resources": [{"key": "same-sensor", "description": "el mismo sensor"}],
        "crew_time_basis": "sin fuente", "protocol_ref": None,
        "followup_checks": ["heart-rate"], "followup_window_hours": 1,
        "followup_basis": "diseño EMMA", "contraindications_note": None,
        "adverse_effects_note": None, "basis": "demo", "family": "check-surveillance",
    }
    entry.update(override)
    return entry


def _write(tmp_path: Path, entry: dict[str, object]) -> Path:
    path = tmp_path / "library.json"
    path.write_text(json.dumps({"countermeasures": [entry]}), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Vocabulario y carga
# --------------------------------------------------------------------------- #


def test_the_vocabulary_is_closed_and_says_its_criterion() -> None:
    assert list(FAMILIES) == ["physical-mass", "operational", "check-surveillance", PHARMACOLOGICAL]
    assert IN_SCOPE_FAMILIES == ("physical-mass", "operational", "check-surveillance")
    assert not FAMILIES[PHARMACOLOGICAL].in_scope
    assert "fuera del alcance de EMMA" in FAMILIES[PHARMACOLOGICAL].display
    for family in FAMILIES.values():
        assert family.display.strip() and len(family.criterion) > 60, family.key


def test_a_pharmacological_entry_is_not_adopted(tmp_path: Path) -> None:
    with pytest.raises(LibraryError, match="fuera del alcance de EMMA"):
        load(_write(tmp_path, _entry(family=PHARMACOLOGICAL)))


@pytest.mark.parametrize("family", [None, "", "biological", "Physical-Mass"])
def test_a_missing_or_unknown_family_is_refused(tmp_path: Path, family: object) -> None:
    entry = _entry(family=family)
    if family is None:
        del entry["family"]
    with pytest.raises(LibraryError, match="familia desconocida o ausente"):
        load(_write(tmp_path, entry))


@pytest.mark.parametrize("family", IN_SCOPE_FAMILIES)
def test_every_in_scope_family_loads_with_its_word(tmp_path: Path, family: str) -> None:
    item = load(_write(tmp_path, _entry(family=family)))["x"]
    assert item.family == family
    assert item.to_dict()["family"] == family
    assert item.to_dict()["family_display"] == FAMILIES[family].display


def test_each_of_the_forty_has_the_family_of_what_it_is() -> None:
    library = countermeasures.library()
    assert len(library) == 40
    for ident, item in library.items():
        expected = (
            "physical-mass" if ident in PHYSICAL
            else "operational" if ident in OPERATIONAL
            else "check-surveillance"
        )
        assert item.family == expected, ident
    # Las de cabina contrastan o revisan: todas son comprobaciones.
    assert {item.family for item in library.values() if item.scope == "habitat"} == {
        "check-surveillance"
    }
    assert PHARMACOLOGICAL not in {item.family for item in library.values()}


# --------------------------------------------------------------------------- #
# La API
# --------------------------------------------------------------------------- #


def test_the_api_groups_the_whole_library_by_ridge(client: TestClient) -> None:
    body = client.get("/api/countermeasures").json()
    ids = [item["id"] for item in body["countermeasures"]]
    assert ids == list(countermeasures.library())
    groups = body["by_ridge"]
    assert [group["ridge"] for group in groups] == [str(ridge) for ridge in Ridge]
    grouped = [ident for group in groups for ident in group["countermeasures"]]
    # Cada entrada en un grupo y solo en uno, y en el de su peligro.
    assert sorted(grouped) == sorted(ids)
    by_id = {item["id"]: item for item in body["countermeasures"]}
    for group in groups:
        assert group["ridge_display"] == Ridge(group["ridge"]).display
        assert group["count"] == len(group["countermeasures"])
        assert {by_id[ident]["ridge"] for ident in group["countermeasures"]} <= {group["ridge"]}
    # Todos los peligros tienen hoy alguna entrada (la distancia, por la nutricion).
    assert all(group["count"] > 0 for group in groups)


def test_the_api_serves_every_family_with_its_count_also_the_one_out_of_scope(
    client: TestClient,
) -> None:
    body = client.get("/api/countermeasures").json()
    families = {item["key"]: item for item in body["families"]}
    assert list(families) == list(FAMILIES)
    assert families[PHARMACOLOGICAL]["count"] == 0
    assert families[PHARMACOLOGICAL]["in_scope"] is False
    assert sum(item["count"] for item in families.values()) == len(body["countermeasures"])
    assert families["physical-mass"]["count"] == len(PHYSICAL)
    assert families["operational"]["count"] == len(OPERATIONAL)
    for item in body["countermeasures"]:
        assert item["family_display"] == families[item["family"]]["display"]
    assert body["note"] == LIBRARY_NOTE
    assert body["family_basis"] == FAMILY_BASIS
    assert body["ridge_basis"] == RIDGE_BASIS


def test_the_new_texts_do_not_read_as_medical_orders() -> None:
    texts = [LIBRARY_NOTE, FAMILY_BASIS, RIDGE_BASIS]
    texts += [text for family in FAMILIES.values() for text in (family.display, family.criterion)]
    assert [(text, check(text)) for text in texts if check(text)] == []


# --------------------------------------------------------------------------- #
# La familia no decide nada
# --------------------------------------------------------------------------- #


def _status(domain: Domain, level: RiskLevel) -> CrewHealthStatus:
    return CrewHealthStatus(
        subject="crew-01",
        domains={domain: DomainRisk(domain, 50.0, level, ("x",))},
        comms=None, isolation_factor=1.0, cumulative_dose_msv=0.0, dose_limit_msv=600.0,
        active_solar_event=None,
    )


def test_the_family_does_not_change_what_is_recommended(monkeypatch: pytest.MonkeyPatch) -> None:
    def offered() -> list[list[tuple[str, str | None, str]]]:
        return [
            [
                (
                    str(item.domain),
                    item.countermeasure.id if item.countermeasure else None,
                    str(item.urgency),
                )
                for item in Advisor().recommend(_status(domain, level))
            ]
            for domain in Domain
            for level in (RiskLevel.WATCH, RiskLevel.CONCERN, RiskLevel.CRITICAL)
        ]

    before = offered()
    swapped = {
        ident: dataclasses.replace(item, family="operational")
        for ident, item in countermeasures.library().items()
    }
    monkeypatch.setattr(countermeasures, "library", lambda: swapped)
    assert offered() == before
