"""El agua potable y la microbiología del hábitat: se enseñan con su límite y no se evalúan.

Decisión del usuario del 2026-10-22 (decimoquinta ronda, D18): las lecturas de agua y de
microbiología van junto al límite que se haya leído y no generan excursión, hipótesis, alerta ni
nivel, como la luz. El 2026-10-22 se leyeron, en su PDF oficial, JSC 63414 Rev A (los SWEG,
ficha `jsc-63414-rev-a`) y, otra vez, NASA-STD-3001 Vol 2 Rev F (ficha
`nasa-std-3001-vol2-rev-f`): de la primera salen los valores guía de la plata y del carbono
orgánico total; de la segunda, que la norma pide agua, aire y superficies «microbiologically
safe» sin dar cifra. Sin fuente, sin límite.

Lo que estas pruebas no pueden comprobar es que cada fila esté de verdad en el documento: se
cotejó a mano contra el texto del PDF el día de la lectura. Lo acotan por el otro lado: una cifra
o una fila que cambie sin volver a leer la fuente rompe la huella de abajo, y nada de esto puede
mover lo que decide el motor (invariante 5) ni la huella de reglas. Sin red.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import alert_context
from app.core import versioning
from app.environment import habitat, systems
from app.environment.habitat import (
    DEFAULT_MODULE,
    DISPLAY_ONLY,
    GROUPS,
    MICROBIOLOGY,
    PARAMETERS,
    WATER,
    HabitatReading,
    excursions,
)
from app.evidence import registry
from app.text_guard import check
from tests.test_habitat_sources import _verdict

T0 = dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC)
SWEG, STANDARD = "jsc-63414-rev-a", "nasa-std-3001-vol2-rev-f"
FROM_SWEG = {"water-toc": habitat.TOC_REQUIREMENTS, "water-silver": habitat.SILVER_REQUIREMENTS}
MICROBIAL = {
    "water-microbial": "[V2 6026]",
    "air-microbial": "[V2 6059]",
    "surface-microbial": "[V2 7081]",
}
NEW = (*FROM_SWEG, *MICROBIAL)

# Huella de todo lo que se copió de las fuentes el 2026-10-22: cada fila con su cifra, su
# unidad, su requisito y su condición. Si cambia, es que alguien ha tocado un texto leído: se
# vuelve a abrir el documento, se coteja y solo entonces se pone la huella nueva. No se
# actualiza «para que pase».
READ_FINGERPRINT = "36bcc931d7bb5638"


def _what_was_read() -> str:
    rows = [
        (key, item.requirement, item.table, item.label, item.source_row, item.low, item.high,
         item.stated, item.unit, item.condition)
        for key in NEW
        for item in DISPLAY_ONLY[key].reference_requirements
    ]
    sources = [
        sorted(DISPLAY_ONLY[key].reference_source.to_dict().items())  # type: ignore[union-attr]
        for key in NEW
    ]
    text = json.dumps([rows, sources], ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _readings(key: str, values: list[float], start: dt.datetime = T0) -> list[HabitatReading]:
    return [
        HabitatReading(DEFAULT_MODULE, key, value, start + dt.timedelta(hours=6 * index),
                       "crew-water-kit")
        for index, value in enumerate(values)
    ]


# --------------------------------------------------------------------------- #
# Lo declarado: aparte de lo evaluado, cada uno en su grupo
# --------------------------------------------------------------------------- #

def test_water_and_microbiology_are_display_only_and_never_evaluated() -> None:
    for key in NEW:
        assert key in DISPLAY_ONLY and key not in PARAMETERS, key
        spec = DISPLAY_ONLY[key]
        assert spec.limits == () and spec.limit_note, key
        # Código propio con su porqué (invariante 1): no es una observación sobre una persona.
        assert spec.system == "https://emma.mission/codes" and spec.not_loinc_reason
        published = spec.to_dict()
        assert published["limits"] == [] and published["source"] is None
        assert published["observation_type"] == "measured"
        assert all(item["evaluated"] is False for item in published["reference_requirements"])
        assert "no se evalúa" in published["limit_note"]
        assert not check(published["limit_note"]) and not check(published["reference_label"])
    assert {DISPLAY_ONLY[key].group for key in ("water-toc", "water-silver",
                                                "water-microbial")} == {WATER}
    assert {DISPLAY_ONLY[key].group for key in ("air-microbial",
                                                "surface-microbial")} == {MICROBIOLOGY}
    # Solo la atmósfera de cabina se evalúa; la luz sigue en su tabla.
    assert {item.group for item in PARAMETERS.values()} == {habitat.CABIN}
    assert DISPLAY_ONLY["cabin-light"].group == habitat.CABIN
    assert list(DISPLAY_ONLY)[0] == "cabin-light"
    assert set(GROUPS) == {habitat.CABIN, WATER, MICROBIOLOGY}


def test_a_group_outside_the_list_or_a_requirement_without_its_label_does_not_load() -> None:
    with pytest.raises(ValueError, match="grupo desconocido"):
        habitat._display_only("water-x", "x", "mg/L", 0.0, 1.0, group="kitchen")
    with pytest.raises(ValueError, match="sin rótulo"):
        habitat._display_only(
            "water-x", "x", "mg/L", 0.0, 1.0,
            reference_requirements=habitat.TOC_REQUIREMENTS, reference_source=habitat.SWEG_SOURCE,
        )


# --------------------------------------------------------------------------- #
# Lo leído
# --------------------------------------------------------------------------- #

def test_what_was_copied_from_the_sources_has_not_changed_since_it_was_read() -> None:
    assert _what_was_read() == READ_FINGERPRINT


def test_each_sweg_requirement_carries_the_figure_of_the_cell_it_was_read_from() -> None:
    expected = {
        "water-toc": [("100 days", 5.0), ("1000 days", 5.0)],
        "water-silver": [("1 day", 5.0), ("10 days", 5.0), ("100 days", 0.6),
                         ("1000 days", 0.4)],
    }
    for key, requirements in FROM_SWEG.items():
        spec = DISPLAY_ONLY[key]
        assert spec.unit == "mg/L" and spec.reference_source == habitat.SWEG_SOURCE
        assert spec.reference_label == habitat.SWEG_LABEL
        read = []
        for item in requirements:
            chemical, period, figure, effect = item.source_row.split(" | ")
            assert chemical == {"water-toc": "Total Organic Carbon", "water-silver": "Silver"}[key]
            match = re.fullmatch(r"([\d.]+) mg/L", figure)
            assert match is not None and float(match.group(1)) == item.high
            # Un SWEG es un máximo: no gana un mínimo ni un valor sin comparador.
            assert item.low is None and item.stated is None and item.unit == "mg/L"
            assert effect.strip() and item.same_quantity
            acute = period in ("1 day", "10 days")
            assert ("contingencias" in item.condition) is acute
            assert ("consumo prolongado" in item.condition) is not acute
            assert not check(item.condition) and not check(item.label)
            read.append((period, item.high))
        assert read == expected[key]
    # El TOC no tiene valor de 1 ni de 10 días en la tabla, y la observación de su fila va con él.
    assert all("formaldehído" in item.condition for item in habitat.TOC_REQUIREMENTS)
    assert all(item.table == "JSC 63414 Rev A, p. 14" for item in habitat.TOC_REQUIREMENTS)
    assert all(item.table == "JSC 63414 Rev A, p. 13" for item in habitat.SILVER_REQUIREMENTS)


def test_the_microbial_readings_carry_the_requirement_and_no_figure() -> None:
    for key, requirement in MICROBIAL.items():
        spec = DISPLAY_ONLY[key]
        assert spec.limit_note == habitat.MICROBIAL_NO_LIMIT
        assert "no da cifra" in spec.limit_note and "Sin límite leído" in spec.limit_note
        assert spec.reference_source == habitat.MICROBIAL_SOURCE
        assert spec.reference_source.id == STANDARD
        assert spec.reference_source.read_on == "2026-10-22"
        [item] = spec.reference_requirements
        assert item.requirement == requirement
        # Sin cifra leída no hay cifra: ni mínimo, ni máximo, ni valor de tabla.
        assert (item.low, item.high, item.stated) == (None, None, None)
        assert "microbiologically safe" in item.source_row
        assert item.unit == spec.unit and spec.unit.startswith("{CFU}/")
        assert "no da cifra" in item.condition and not check(item.condition)


def test_both_documents_have_their_entry_with_what_was_read() -> None:
    sweg, standard = registry.get(SWEG), registry.get(STANDARD)
    assert sweg.evidence_type == "technical_standard" and not sweg.unverified
    assert "Rev A" in sweg.source and sweg.date == "2023-11"
    assert sweg.url is not None and sweg.url.startswith("https://www.nasa.gov/")
    assert set(sweg.not_applicable) == {"doi", "evidence_context", "population"}
    notes = sweg.notes or ""
    for said in ("2026-10-22", "Silver", "Total Organic Carbon", "contingency conditions",
                 "does not mean that health impairment is certain", "yodo"):
        assert said in notes, said
    standard_notes = standard.notes or ""
    for said in ("2026-10-22", "[V2 6026]", "[V2 6059]", "[V2 7081]",
                 "allowable levels of microorganisms"):
        assert said in standard_notes, said
    # Desde la decimonovena ronda (U3) el modulo cita tambien los documentos de sus limites
    # evaluados: el del catalogo (OCHMO-TB-002) y el del ruido (OCHMO-TB-035).
    assert habitat.cited_refs() == {
        SWEG, STANDARD, habitat.LIMITS_SOURCE.id, habitat.NOISE_SOURCE.id,
    }


def test_only_the_water_system_names_water_and_nobody_names_the_air_or_surfaces() -> None:
    water = systems.SYSTEMS["water"]
    assert set(water.parameters) == {"water-toc", "water-silver", "water-microbial"}
    named = {key for system in systems.SYSTEMS.values() for key in system.parameters}
    assert not named & {"air-microbial", "surface-microbial"}


# --------------------------------------------------------------------------- #
# Invariante 5: ninguna lectura de estas genera nada
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("key", NEW)
@pytest.mark.parametrize("value", [0.0, 0.4, 5.0, 50.0, 10_000.0])
def test_no_reading_is_an_excursion_whatever_the_value(key: str, value: float) -> None:
    spec = DISPLAY_ONLY[key]
    top = min(value, spec.physical_max)
    assert excursions(_readings(key, [top] * 12)) == []
    assert excursions(_readings(key, [0.0, top, spec.physical_max, top] * 6)) == []


def test_an_impossible_reading_is_still_a_sensor_fault() -> None:
    for key in NEW:
        for value in (-1.0, DISPLAY_ONLY[key].physical_max * 2, float("nan")):
            with pytest.raises(ValueError):
                _readings(key, [value])


def test_the_rules_fingerprint_is_the_one_without_water_or_microbiology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with_them = versioning.fingerprint(versioning.rules())
    assert not set(NEW) & set(versioning.rules()["habitat"])
    for key in NEW:
        monkeypatch.delitem(habitat.DISPLAY_ONLY, key)
    assert versioning.fingerprint(versioning.rules()) == with_them
    assert versioning.rules_version() == f"reglas@{with_them}"


def test_a_sample_does_not_say_the_cabin_was_monitored() -> None:
    # Un contexto de alerta sin ninguna lectura de cabina en la ventana dice «sin dato» aunque
    # haya una muestra de agua o un recuento microbiano: no se vigiló la atmósfera.
    window = (T0 - dt.timedelta(hours=24), T0 + dt.timedelta(hours=24))
    anchor = alert_context._Anchor(
        T0, "el inicio de la alerta", "del inicio de la alerta", "Inicio de la alerta", ""
    )
    samples = [*_readings("water-microbial", [12.0]), *_readings("air-microbial", [140.0])]
    items, source = alert_context._habitat(samples, [], window, anchor)
    assert items == [] and source["status"] == alert_context.NO_DATA
    assert habitat.cabin_readings(samples) == []
    light = _readings("cabin-light", [300.0])
    assert habitat.cabin_readings([*samples, *light]) == light
    _, with_light = alert_context._habitat([*samples, *light], [], window, anchor)
    assert with_light["status"] == alert_context.PARTIAL


def _extreme(reference: str, later: dt.timedelta) -> list[dict[str, Any]]:
    """Una lectura muy alta de cada parámetro nuevo, en el instante de referencia y después."""
    moment = dt.datetime.fromisoformat(reference)
    return [
        {"parameter": key, "value": value, "effective": (moment + shift).isoformat(),
         "source": "crew-water-kit"}
        for key, value in (("water-toc", 50.0), ("water-silver", 9.0),
                           ("water-microbial", 1e6), ("air-microbial", 1e6),
                           ("surface-microbial", 1e6))
        for shift in (dt.timedelta(0), later)
    ]


def test_the_engine_decides_the_same_with_any_water_or_microbial_reading(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 10})
    before = _verdict(client)
    cabin = client.get("/api/habitat").json()
    assert before["active"] and before["hypotheses"]
    reference = cabin["reference_time"]

    # Cada lectura entra por el ledger, firmada por su fuente (invariante 4).
    for payload in _extreme(reference, dt.timedelta(minutes=30)):
        response = client.post("/api/habitat", json=payload)
        assert response.status_code == 201, response.text
        assert response.json()["content_hash"]

    after = _verdict(client)
    assert after == before
    cabin_after = client.get("/api/habitat").json()
    # Una muestra declarada después de la última lectura de cabina no mueve su «ahora» ni da
    # por cerrada la excursión vigente.
    assert cabin_after["reference_time"] == reference
    assert cabin_after["active"] == cabin["active"]
    assert cabin_after["excursions"] == cabin["excursions"]
    shown = {item["parameter"] for item in cabin_after["latest"]}
    assert set(NEW) <= shown
    assert not {item["parameter"] for item in cabin_after["excursions"]} & set(NEW)
    crew = client.get("/api/crew").json()
    for hypothesis in crew["correlation"]["hypotheses"]:
        assert (hypothesis.get("excursion") or {}).get("parameter") not in NEW


def test_a_water_reading_is_signed_with_its_source_and_context(client: TestClient) -> None:
    response = client.post("/api/habitat", json={
        "parameter": "water-silver", "value": 0.3, "effective": T0.isoformat(),
        "source": "crew-water-kit", "evidence_context": "analog_isolation",
    })
    assert response.status_code == 201, response.text
    [latest] = client.get("/api/habitat").json()["latest"]
    assert latest["parameter"] == "water-silver" and latest["unit"] == "mg/L"
    assert latest["source"] == "crew-water-kit" and latest["evidence_context"] == "analog_isolation"
    # Sin nada evaluado, el «ahora» del hábitat es el de lo que hay.
    assert client.get("/api/habitat").json()["reference_time"] == T0.isoformat()
    # Una unidad distinta de la del catálogo o un parámetro desconocido no entran.
    assert client.post("/api/habitat", json={
        "parameter": "water-iodine", "value": 0.3,
    }).status_code == 422


def test_the_api_publishes_each_group_with_its_name(client: TestClient) -> None:
    published = client.get("/api/habitat/parameters").json()
    shown = {item["key"]: item for item in published["display_only"]}
    assert set(NEW) <= set(shown)
    for key in NEW:
        assert shown[key]["group_display"] == GROUPS[shown[key]["group"]]
        assert shown[key]["personal_exposure"] is None
    assert all(item["group"] == "cabin" for item in published["parameters"])
