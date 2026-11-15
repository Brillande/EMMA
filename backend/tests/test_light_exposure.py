"""La exposición personal a la luz: lo leído se sirve con su frase, y nada se evalúa.

La pregunta de la undécima ronda (F3) era si hay un límite o una recomendación publicada para
la luz que recibe un tripulante. NASA no da ninguno: estas pruebas fijan que la respuesta lo
diga, que la cifra de Tierra no se cuele como límite de vuelo y que la luz de cabina siga sin
evaluarse.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.environment.habitat import DEFAULT_MODULE, DISPLAY_ONLY, HabitatReading, excursions
from app.evidence import instruments_read, light_exposure, registry
from app.evidence.light_exposure import LightExposureError, validate
from app.evidence.registry import RegistryError

RAW: dict[str, Any] = json.loads(light_exposure.READ_PATH.read_text(encoding="utf-8"))


def _broken(change: Any) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    change(raw)
    return raw


def _item(raw: dict[str, Any], period: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        item for item in raw["recommendations"]["items"] if item["period"] == period
    )
    return found


# --------------------------------------------------------------------------- #
# Lo leído
# --------------------------------------------------------------------------- #


def test_nasa_gives_no_personal_limit_and_says_where_it_looked() -> None:
    summary = light_exposure.summary()
    assert summary["nasa_personal_limit"] is None
    assert summary["status"] == light_exposure.NO_NASA_LIMIT
    assert "Sin límite personal publicado por NASA" in summary["status"]
    searched = " ".join(summary["searched"])
    for where in ("[V2 8055]", "[V2 6117]", "[V1 6001]", "OCHMO-TB-026", "Lighting Effects"):
        assert where in searched


def test_the_requirements_that_look_personal_are_quoted_as_what_they_are() -> None:
    context = {item["id"]: item for item in light_exposure.summary()["context"]}
    # [V2 8055] se mide en la córnea, pero obliga al sistema de iluminación.
    assert context["v2-8055-requirement"]["quote"].startswith("The system shall provide")
    assert "measured at the cornea" in context["v2-8055-cornea"]["quote"]
    # [V2 6117] es de seguridad del ojo y la piel, fuente a fuente.
    assert "artificial light sources" in context["v2-6117-requirement"]["quote"]
    assert "ocular and skin injury" in context["v2-6117-rationale"]["quote"]
    for item in context.values():
        assert item["read_on"] == "2026-10-14"
        assert item["url"] and item["where"] and item["extent_text"]


def test_the_ground_recommendation_carries_its_own_scope() -> None:
    recommendations = light_exposure.summary()["recommendations"]
    assert recommendations["setting"] == "interiores en Tierra"
    assert "en el ojo" in recommendations["quantity"]
    assert "No son un límite de vuelo" in recommendations["note"]
    scope = " ".join(item["quote"] for item in recommendations["scope"])
    assert "healthy adults (aged 18 to 55) with regular daytime schedules" in scope
    assert "not intended for this purpose" in scope
    by_period = {item["period"]: item for item in recommendations["items"]}
    assert (by_period["day"]["low"], by_period["day"]["high"]) == (250.0, None)
    assert (by_period["evening"]["low"], by_period["evening"]["high"]) == (None, 10.0)
    assert (by_period["sleep"]["low"], by_period["sleep"]["high"]) == (None, 1.0)
    for item in by_period.values():
        assert item["literal"] in item["statement"]["quote"]
        assert item["statement"]["ref"] == "brown-2022-melanopic-light"


def test_nothing_is_evaluated_and_the_cabin_light_still_has_no_excursion() -> None:
    summary = light_exposure.summary()
    assert summary["evaluated"] is False
    assert "no mide la luz que llega a los ojos" in summary["not_measured"]
    # Una lectura de cabina muy por debajo de la recomendación de día no da excursión.
    reading = HabitatReading(
        module=DEFAULT_MODULE, parameter="cabin-light", value=0.0,
        effective=dt.datetime(2026, 10, 14, 12, tzinfo=dt.UTC), source="habitat-telemetry",
    )
    assert excursions([reading]) == []
    assert "cabin-light" in DISPLAY_ONLY


def test_every_source_is_a_registry_card_on_an_official_site() -> None:
    for ref_id in light_exposure.cited_refs():
        ref = registry.get(ref_id)
        assert ref.url is not None and ref.url.startswith("https://")
        assert ref.url.split("/")[2] in instruments_read.OFFICIAL_HOSTS


# --------------------------------------------------------------------------- #
# La API
# --------------------------------------------------------------------------- #


def test_the_cabin_light_carries_the_personal_reading(client: TestClient) -> None:
    response = client.get("/api/habitat/parameters")
    assert response.status_code == 200
    display_only = {item["key"]: item for item in response.json()["display_only"]}
    light = display_only["cabin-light"]
    assert light["personal_exposure"] == light_exposure.summary()
    # Lo de antes sigue igual: sin límite general y con los requisitos de referencia.
    assert light["limits"] == [] and light["reference_requirements"]
    assert response.json()["parameters"]
    assert all("personal_exposure" not in item for item in response.json()["parameters"])


# --------------------------------------------------------------------------- #
# El cargador
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda raw: raw.pop("read_on"), "read_on"),
        (lambda raw: raw["statements"][0].update(where=" "), "falta `where`"),
        (lambda raw: raw["statements"][0].update(quote=""), "falta `quote`"),
        (lambda raw: raw["sources"].pop("brown-2022-melanopic-light"), "cuánto se leyó"),
        (lambda raw: raw["sources"]["ochmo-tb-026"].update(extent="todo"), "cuánto se leyó"),
        (lambda raw: raw["statements"].append(dict(raw["statements"][0])), "repetido"),
        # Un límite de NASA sin frase que lo escriba.
        (lambda raw: raw.update(nasa_personal_limit="inventada"), "ninguna frase leída"),
        (lambda raw: raw.update(searched=[]), "dónde se buscó"),
        (lambda raw: raw["searched"].append(" "), "searched"),
        # Una cifra que su frase no escribe.
        (lambda raw: _item(raw, "day").update(statement="brown-evening"), "no está escrito"),
        (lambda raw: _item(raw, "day").update(low=300.0), "no es la cifra"),
        (lambda raw: _item(raw, "day").update(low=None, high=250.0), "maximum"),
        (lambda raw: _item(raw, "day").update(high=1000.0), "un mínimo o un máximo"),
        (lambda raw: _item(raw, "day").update(statement="inventada"), "ninguna frase leída"),
        (lambda raw: raw["recommendations"]["items"].append(_item(raw, "day")), "repetido"),
        # Una recomendación sin a quién se aplica.
        (lambda raw: raw["recommendations"].update(scope=[]), "a quién se aplican"),
        (lambda raw: raw["recommendations"]["scope"].append("inventada"), "no es una frase"),
        (lambda raw: raw["context"].append("inventada"), "no es una frase leída"),
    ],
)
def test_the_loader_rejects_what_cannot_be_held(change: Any, message: str) -> None:
    with pytest.raises(LightExposureError, match=message):
        validate(_broken(change))


def test_the_loader_rejects_a_source_that_is_not_registered_or_not_official(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unregistered(raw: dict[str, Any]) -> None:
        raw["sources"]["no-existe"] = {"extent": "full", "what": "x"}

    # Con el error del cargador y el motivo del registro (el contrato común, `read_contract`).
    with pytest.raises(LightExposureError, match="no-existe: .*no está en el registro") as caught:
        validate(_broken(unregistered))
    assert isinstance(caught.value.__cause__, RegistryError)
    monkeypatch.setattr(light_exposure, "OFFICIAL_HOSTS", frozenset({"www.nasa.gov"}))
    with pytest.raises(LightExposureError, match="no es la revista"):
        validate(copy.deepcopy(RAW))


def test_the_shipped_reading_passes_its_own_contract() -> None:
    assert validate(copy.deepcopy(RAW)) == RAW
