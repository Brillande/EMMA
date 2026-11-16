"""El inglés de lo que redactan las rutas (unidad 11): `api/routes.py` y sus rutas vecinas.

El castellano no se mueve: sin cabecera sale lo de siempre, y con `X-EMMA-Lang: en` sale el inglés
de lo que estas rutas componen por su cuenta (la capacidad de vigilancia, las notas del estado, la
base del veredicto, el marco de NASA, el descarte de alertas, el aviso del freno HALT, el
inventario de Polaris). Los identificadores —claves, niveles, causas— son los mismos en los dos
idiomas, y lo que `GET /api/status` firma por su cuenta no depende de quién lea
(`compliance/record-integrity.md`, «Idioma del registro»).
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import polaris
from app.api import routes
from app.api.safe_mode import EXIT_NAMES, halt_notice
from app.core import egress, i18n
from app.core.ledger import SALT_FIELD
from app.environment import comms_status
from app.ingest.fhir import ObservationType
from tests.conftest import ENGLISH_HEADERS


def _get(client: TestClient, path: str, english: bool = False) -> Any:
    response = client.get(path, headers=ENGLISH_HEADERS if english else {})
    assert response.status_code == 200, response.text
    return response.json()


def _seed(client: TestClient, scenario: str = "nominal", days: int = 14) -> dt.datetime:
    seeded = client.post("/api/simulate", params={"scenario": scenario, "days": days})
    assert seeded.status_code == 201, seeded.text
    return dt.datetime.fromisoformat(_get(client, "/api/status")["data"]["reference_time"])


def _capabilities(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in status["monitoring"]["capabilities"]}


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


# --------------------------------------------------------------------------- #
# /api/status
# --------------------------------------------------------------------------- #


def test_the_monitoring_block_is_written_in_the_language_asked(client: TestClient) -> None:
    _seed(client)
    spanish = _capabilities(_get(client, "/api/status"))
    english = _capabilities(_get(client, "/api/status", english=True))

    # El castellano, como antes.
    assert spanish["personal-baseline"]["label"] == "Línea base personal"
    assert spanish["light-time"]["label"] == "Retardo con Tierra"
    assert spanish["career-dose"]["consequence"] == (
        "Sin dosis acumulada: no se evalúa el límite de carrera de [V1 4030]."
    )
    # El inglés, con la misma afirmación.
    assert english["personal-baseline"]["label"] == "Personal baseline"
    assert english["light-time"]["label"] == "Delay to Earth"
    assert english["space-weather"]["label"] == "Space weather"
    assert english["reading-dates"]["label"] == "Reading dates"
    assert english["alert-annunciation"]["label"] == "Alert annunciation"
    assert english["record-integrity"]["label"] == "Record integrity"
    assert english["career-dose"]["consequence"] == (
        "No cumulative dose: the career limit of [V1 4030] is not assessed."
    )
    # Lo que el código compara no se traduce.
    assert list(english) == list(spanish)
    for key, item in english.items():
        assert item["available"] == spanish[key]["available"]
        assert item["cause"] == spanish[key]["cause"]


def test_the_basis_of_the_verdict_is_said_in_english(client: TestClient) -> None:
    _seed(client)
    spanish = _get(client, "/api/status")
    english = _get(client, "/api/status", english=True)
    assert spanish["data"]["basis"] in (
        "línea base personal",
        "principalmente límites de peligro absoluto: faltan muestras para una línea base personal",
    )
    assert english["data"]["basis"] in (
        "personal baseline",
        "mainly absolute danger limits: there are not enough samples for a personal baseline",
    )
    assert "línea base" not in english["data"]["basis"]
    # Lo demás que se compara, igual: niveles, claves de dominio, versión de reglas, instante.
    assert english["overall_level"] == spanish["overall_level"]
    assert list(english["domains"]) == list(spanish["domains"])
    assert english["rules_version"] == spanish["rules_version"]
    assert english["data"]["reference_time"] == spanish["data"]["reference_time"]
    assert english["monitoring"]["level"] == spanish["monitoring"]["level"]
    assert english["mission"]["mode"] == spanish["mission"]["mode"]


def test_the_set_aside_notes_carry_the_figure_with_a_decimal_point(client: TestClient) -> None:
    reference = _seed(client)
    posted = client.post(
        "/api/observations",
        json={
            "key": "cumulative-dose", "value": 123.4, "subject": "crew-01",
            "effective": (reference - dt.timedelta(hours=1)).isoformat(),
            "observation_type": "predicted", "model_version": "modelo-de-prueba@1",
        },
    )
    assert posted.status_code == 201, posted.text

    spanish = _get(client, "/api/status")["notes"]
    english = _get(client, "/api/status", english=True)["notes"]

    said = [note for note in spanish if note.startswith("La dosis acumulada registrada como")]
    assert len(said) == 1 and "(123,4 mSv) no cuenta para el límite de carrera" in said[0]
    assert any(note.endswith("solo deciden las medidas") for note in spanish)

    told = [note for note in english if note.startswith("The cumulative dose recorded as")]
    assert len(told) == 1
    assert "(123.4 mSv) does not count towards the career limit" in told[0]
    assert "123,4" not in told[0]
    assert any(note.endswith("only measured readings decide") for note in english)
    assert not any("no cuenta para el límite" in note for note in english)
    assert not any("solo deciden las medidas" in note for note in english)
    # El tipo con que se registró es un identificador: el mismo en los dos idiomas.
    assert _get(client, "/api/status", english=True)["dose"]["set_aside"]["recorded_type"] == (
        "predicted"
    )


def test_an_inhibition_is_told_in_english_with_who_asked(client: TestClient) -> None:
    _seed(client, "arrhythmia", 40)
    status = _get(client, "/api/status")
    assert status["alerts"], "el escenario de arritmia debe alertar"
    alert = status["alerts"][0]
    silenced = client.post(
        "/api/alerts/inhibit",
        json={
            "domain": alert["domain"], "reference_time": status["data"]["reference_time"],
            "reason": "sensor de pulso con mal contacto", "requested_by": "comandante",
            "level": alert["level"], "duration_hours": 24,
        },
    )
    assert silenced.status_code == 201, silenced.text

    spanish = _capabilities(_get(client, "/api/status"))["alert-annunciation"]
    english = _capabilities(_get(client, "/api/status", english=True))["alert-annunciation"]
    assert spanish["consequence"].startswith("Alertas inhibidas: ")
    assert "(lo pidió comandante: sensor de pulso con mal contacto)" in spanish["consequence"]
    assert spanish["consequence"].endswith(". No se anuncian mientras dure la inhibición.")

    assert english["consequence"].startswith("Alerts inhibited: ")
    # Lo que escribió la persona no se traduce: es suyo y está firmado.
    assert "(requested by comandante: sensor de pulso con mal contacto)" in english["consequence"]
    assert english["consequence"].endswith(
        ". They are not annunciated while the inhibition lasts."
    )
    assert "lo pidió" not in english["consequence"]
    assert english["cause"] == spanish["cause"] == "manual"


def test_the_capabilities_in_english_say_what_is_lost_without_ordering(english: None) -> None:
    """Llamada directa: cada consecuencia en inglés, sin la frase castellana."""
    monitoring = routes._monitoring(
        personal_fraction=0.0, has_comms=False, has_solar=True, has_dose=False, ignored=1234,
        integrity_ok=False, solar_stale_age="12 días",
    )
    lost = {item["key"]: item["consequence"] for item in monitoring["capabilities"]}
    assert lost["personal-baseline"].startswith("There are not enough readings")
    assert lost["light-time"] == "No ephemeris: the thresholds are not adjusted for isolation."
    assert lost["space-weather"].startswith("Stale NASA DONKI data (12 días)")
    assert lost["reading-dates"].startswith("1234 readings set aside")
    assert lost["record-integrity"] == (
        "The signed chain does not verify: the verdict has no signature backing."
    )
    assert lost["alert-annunciation"] is None
    assert monitoring["level"] == "reduced"
    for text in lost.values():
        assert text is None or not any(
            word in text for word in ("Sin ", "lecturas", "no se ", "certified", "diagnos")
        )


def test_without_donki_the_english_says_what_is_not_detected(english: None) -> None:
    monitoring = routes._monitoring(
        personal_fraction=1.0, has_comms=True, has_solar=False, has_dose=True, ignored=0,
        integrity_ok=True,
    )
    lost = {item["key"]: item["consequence"] for item in monitoring["capabilities"]}
    assert lost["space-weather"] == "No NASA DONKI data: solar particle events are not detected."


def test_the_words_of_the_types_that_decide_follow_the_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "ANALYSED_TYPES", tuple(ObservationType)[:2])
    spanish = routes.analysed_type_words()
    assert spanish.count(" o ") == 1
    with i18n.use("en"):
        # El inglés de cada palabra lo registra `analysis/alert_support.py`; aquí, la conjunción.
        told = routes.analysed_type_words()
    assert told.count(" or ") == 1 and " o " not in told


# --------------------------------------------------------------------------- #
# Otras rutas de lectura
# --------------------------------------------------------------------------- #


def test_the_framework_is_told_in_english_with_the_same_structure(client: TestClient) -> None:
    spanish = _get(client, "/api/framework")
    english = _get(client, "/api/framework", english=True)

    assert spanish["standard"] == "NASA-STD-3001 Vol 1 Rev C — requisito central [V1 3004] h"
    assert english["standard"] == "NASA-STD-3001 Vol 1 Rev C — core requirement [V1 3004] h"
    gaps_es, gaps_en = spanish["exmc_gaps"], english["exmc_gaps"]
    assert gaps_es["note"].startswith("Enunciados de 2020")
    assert gaps_en["note"].startswith("Statements from 2020")
    assert "not that it closes the gap" in gaps_en["note"]
    assert gaps_en["med07"]["emma"].startswith("It responds to the question in the statement")
    # No afirma más que el castellano: ni contribuyó al cierre ni diagnostica o prescribe.
    assert "has not contributed to that closure" in gaps_en["med07"]["emma"]
    assert "does not diagnose or prescribe" in gaps_en["med10"]["emma"]
    assert "Responde a la pregunta" not in gaps_en["med07"]["emma"]
    assert english["imm"]["what"].startswith("NASA model that")
    assert english["imm"]["not_duplicated"].startswith("EMMA does not forecast the mission")
    # Las citas literales de NASA y los identificadores, tal cual en los dos.
    for gap in ("med07", "med10"):
        assert gaps_en[gap]["gap"] == gaps_es[gap]["gap"]
        assert gaps_en[gap]["label"] == gaps_es[gap]["label"]
    assert gaps_en["url"] == gaps_es["url"] and gaps_en["source"] == gaps_es["source"]
    assert list(english["ridge"]) == list(spanish["ridge"])
    for domain, item in english["ridge"].items():
        assert item["hazard"] == spanish["ridge"][domain]["hazard"]
    assert list(english["amcl_alignment"]) == list(spanish["amcl_alignment"])


def test_what_a_dismissal_is_is_told_in_english(client: TestClient) -> None:
    spanish = _get(client, "/api/alerts/dismissal-reasons")
    english = _get(client, "/api/alerts/dismissal-reasons", english=True)
    assert spanish["basis"] == routes.DISMISSAL_BASIS
    assert english["basis"].startswith("Dismissing leaves it stated, signed and with its reason")
    assert "It changes no calculation" in english["basis"]
    assert "Descartar deja dicho" not in english["basis"]
    # Los códigos de motivo son el vocabulario firmado: no cambian.
    assert [item["code"] for item in english["reasons"]] == [
        item["code"] for item in spanish["reasons"]
    ]
    assert [item["note_required"] for item in english["reasons"]] == [
        item["note_required"] for item in spanish["reasons"]
    ]


def test_the_catalogue_and_the_scenarios_keep_their_identifiers(client: TestClient) -> None:
    spanish = _get(client, "/api/indicators")
    english = _get(client, "/api/indicators", english=True)
    assert english["count"] == spanish["count"]
    for ours, theirs in zip(english["indicators"], spanish["indicators"], strict=True):
        for field in ("key", "unit", "domain", "system", "is_standard_code", "decimals"):
            assert ours[field] == theirs[field]
    assert _get(client, "/api/scenarios", english=True) == _get(client, "/api/scenarios")
    assert _get(client, "/api/audit", english=True)["integrity_ok"] is True


def test_the_polaris_inventory_names_each_state_in_english(client: TestClient) -> None:
    spanish = _get(client, "/api/polaris/estado")
    english = _get(client, "/api/polaris/estado", english=True)
    assert {tool["estado"] for tool in spanish["herramientas"]} <= {
        "carga", "no carga", "no se importa"
    }
    assert {tool["estado"] for tool in english["herramientas"]} <= {
        "loads", "does not load", "not imported"
    }
    # Las claves y lo que el código lee (`carga`, `en_uso`) no cambian.
    for ours, theirs in zip(english["herramientas"], spanish["herramientas"], strict=True):
        assert ours["herramienta"] == theirs["herramienta"]
        assert ours["carga"] == theirs["carga"] and ours["en_uso"] == theirs["en_uso"]
    assert english["total"] == spanish["total"] and english["cargan"] == spanish["cargan"]


# --------------------------------------------------------------------------- #
# El aviso del freno HALT
# --------------------------------------------------------------------------- #


@pytest.fixture
def halt(tmp_path: Path) -> Iterator[Path]:
    """El fichero de freno de EMMA, en una carpeta temporal (como `tests/test_halt_notice.py`)."""
    path = tmp_path / "estado" / ".HALT"
    path.parent.mkdir()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(polaris, "halt_file", lambda: path)
            polaris.load("borde")
            yield path
    finally:
        polaris.load("borde")


def test_the_halt_notice_is_told_in_english(client: TestClient, halt: Path) -> None:
    halt.write_text("prueba", encoding="utf-8")
    moment = dt.datetime(2026, 9, 1, 12, 30, 15, tzinfo=dt.UTC).timestamp()
    os.utime(halt, (moment, moment))

    spanish = _get(client, "/api/safe-mode")["halt"]["notice"]
    english = _get(client, "/api/safe-mode", english=True)["halt"]["notice"]

    assert spanish["title"] == "Freno HALT de Polaris"
    assert spanish["summary"] == (
        "Siguen las constantes, el análisis, las alertas y el modelo local."
    )
    assert english["title"] == "Polaris HALT brake"
    assert english["headline"] == "set · no internet egress"
    assert english["summary"] == (
        "The vital signs, the analysis, the alerts and the local model keep running."
    )
    assert english["since_label"] == "since (file date, unsigned)"
    assert english["details_label"] == "What it is and how to remove it"
    assert english["since"] == spanish["since"]
    assert len(english["details"]) == len(spanish["details"])
    text = " ".join(english["details"])
    assert "not safe mode" in text and "lifting safe mode does not remove it" in text
    # Las salidas, nombradas en inglés y enlazadas con «and».
    assert "space weather (NASA DONKI)" in text
    assert "ephemeris for the delay to Earth (JPL Horizons)" in text
    assert "the planner's on-this-day entries (Wikipedia), " in text
    assert " and the search for and download of new EMMA versions (GitHub)." in text
    assert str(halt) in text and "by deleting the file" in text
    assert "EMMA is also in offline mode" in text
    for spanish_word in ("freno", "fichero", "puerta de salida", "clima espacial", " y las "):
        assert spanish_word not in text, spanish_word


def test_every_exit_has_its_english_name(english: None) -> None:
    notice = halt_notice({"active": True, "since": None, "file": "x"}, offline=False)
    assert notice is not None
    sentence = notice["details"][1]
    assert set(EXIT_NAMES) == set(egress.ALLOWLIST)
    for purpose, spanish in EXIT_NAMES.items():
        assert i18n.loc(spanish) != spanish, purpose
        assert i18n.loc(spanish) in sentence, purpose
        assert spanish not in sentence, purpose


# --------------------------------------------------------------------------- #
# El idioma del registro: leer en inglés firma lo mismo que leer en castellano
# --------------------------------------------------------------------------- #

READS = (
    "/api/status",
    "/api/status?subject=crew-01",
    "/api/anatomy/state",
    "/api/indicators",
    "/api/framework",
    "/api/scenarios",
    "/api/audit",
    "/api/alerts/dismissal-reasons",
    "/api/safe-mode",
    "/api/mission-mode",
    "/api/link-sync",
    "/api/help-requests",
    "/api/inventory",
    "/api/crew/profile",
    "/api/mission/shift",
    "/api/timeline/chronicle",
    "/api/timeline/week",
    "/api/timeline/routines",
    "/api/timeline/waiting",
    "/api/replay/recovery",
    "/api/polaris/estado",
)


def _ledger_after_reading(
    client: TestClient, headers: dict[str, str], scenario: str
) -> list[Any]:
    routes.reset_store(routes.new_store())
    seeded = client.post("/api/simulate", params={"scenario": scenario, "seed": 7, "days": 40})
    assert seeded.status_code == 201, seeded.text
    answered = [client.get(path, headers=headers).status_code for path in READS]
    assert answered.count(200) >= len(READS) - 2, list(zip(READS, answered, strict=True))
    store = routes.get_store()
    # La sal de cada asiento es aleatoria a propósito: se compara lo demás.
    return [
        (entry.entry_type, {k: v for k, v in (entry.payload or {}).items() if k != SALT_FIELD})
        for entry in store.ledger.entries
    ]


@pytest.mark.parametrize("scenario", ["arrhythmia", "progressive-insomnia"])
def test_reading_an_alerting_state_in_english_signs_the_same(
    client: TestClient, scenario: str
) -> None:
    spanish = _ledger_after_reading(client, {}, scenario)
    english = _ledger_after_reading(client, ENGLISH_HEADERS, scenario)
    assert len(spanish) > 10
    # El estado de a bordo firma instantáneas de proyección al leerse: tienen que estar.
    kinds = [kind for kind, _ in spanish]
    assert [kind for kind, _ in english] == kinds
    assert english == spanish


def test_the_signed_discrepancy_is_written_in_the_record_language(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La frase del asiento `ephemeris-discrepancy` se compone en el idioma del registro aunque
    quien lea el estado pida inglés."""
    asked: list[str] = []

    def payload(window: Any, observer: str) -> None:
        asked.append(i18n.current())
        return None

    monkeypatch.setattr(comms_status, "discrepancy_payload", payload)
    with i18n.use("en"):
        assert routes._ephemeris_discrepancy_view(
            routes.get_settings(), routes.get_store(), object(), None  # type: ignore[arg-type]
        ) is None
        assert i18n.current() == "en"
    assert asked == [i18n.RECORD_LANG]


def test_no_spanish_sentence_of_this_unit_is_left_in_the_english_status(
    client: TestClient,
) -> None:
    """Las frases que componen estas rutas no salen en castellano en el estado en inglés. Lo que
    escriben otros módulos tiene su propia prueba."""
    _seed(client, "arrhythmia", 40)
    english = _get(client, "/api/status", english=True)
    ours = (
        "Línea base personal", "Retardo con Tierra", "Meteorología espacial", "Dosis de carrera",
        "Fechas de las lecturas", "Anuncio de alertas", "Integridad del registro",
        "Sin dosis acumulada", "Sin efemérides:", "Sin datos de NASA DONKI",
        "línea base personal", "se apartaron del análisis",
    )
    for text in _strings({"monitoring": english["monitoring"], "data": english["data"]["basis"],
                          "notes": english["notes"]}):
        for sentence in ours:
            assert sentence not in text, text
