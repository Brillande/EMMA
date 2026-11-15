"""El estado de los sistemas del hábitat, declarado por una persona (especificación §3).

EMMA no lee el estado de ningún sistema. Estas pruebas fijan lo que sí hace y lo que no puede
pasar: el vocabulario es cerrado y se declara «de diseño»; «sin declarar» no es «nominal»; cada
declaración es UN asiento firmado por la consola (invariante 4); lo vigente es lo último
firmado y se dice desde cuándo; es una fuente más del contexto de una alerta, con su rótulo; y
no mueve un solo nivel, alerta ni excursión (invariante 5).
"""

import ast
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import alert_context
from app.api.routes import get_store, identity_for
from app.core.storage import TamperedRecordError
from app.core.versioning import FINGERPRINTED, GUARDED
from app.environment import systems
from app.environment.habitat import DISPLAY_ONLY, PARAMETERS

CO2_SCENARIO = {"scenario": "co2-fatigue", "days": 10}
AIR = "air-revitalization"
LABEL = "declarado por una persona, no telemetría"
T0 = dt.datetime(2026, 11, 8, 12, 0, tzinfo=dt.UTC)


def _declare(client: TestClient, system: str = AIR, state: str = "degraded", **extra: Any) -> Any:
    return client.post("/api/habitat/systems/status", json={
        "system": system, "state": state, "at": T0.isoformat(), "declared_by": "CDR", **extra,
    })


def _read(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/habitat/systems", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _system(body: dict[str, Any], key: str = AIR) -> dict[str, Any]:
    [found] = [item for item in body["systems"] if item["key"] == key]
    return dict(found)


# --------------------------------------------------------------------------- #
# El vocabulario
# --------------------------------------------------------------------------- #


def test_the_vocabulary_is_closed_declared_as_design_and_undeclared_is_not_nominal() -> None:
    vocabulary = systems.VOCABULARY
    assert "Vocabulario de diseño de EMMA" in vocabulary.basis
    assert "no modela una nave concreta" in vocabulary.basis
    assert vocabulary.declared_label == LABEL
    assert "no es una afirmación médica" in vocabulary.relation_basis.lower()
    # El estado por defecto existe, no es «nominal» y nadie puede firmarlo.
    assert systems.UNDECLARED == "undeclared" != "nominal"
    assert systems.STATES[systems.UNDECLARED].declarable is False
    assert systems.DECLARABLE_STATES == ("nominal", "degraded", "out-of-service")
    assert "No quiere decir que funcione" in systems.STATES[systems.UNDECLARED].description
    # Un sistema solo se relaciona con parámetros de cabina que EMMA vigila de verdad, y el
    # ejemplo de definición está: quien retira el CO2, con el CO2.
    known = set(PARAMETERS) | set(DISPLAY_ONLY)
    for system in systems.SYSTEMS.values():
        assert set(system.parameters) <= known, system.key
    assert "cabin-ppco2" in systems.SYSTEMS[AIR].parameters
    assert systems.SYSTEMS["power"].parameters == ()


def _vocabulary(tmp_path: Path, change: Any) -> Path:
    raw = json.loads(systems.SYSTEMS_PATH.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "habitat_systems.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_food_and_exercise_are_systems_by_reading_and_stay_out_of_life_support() -> None:
    assert not systems.SYSTEMS["food"].life_support
    assert not systems.SYSTEMS["exercise"].life_support
    assert systems.SYSTEMS["food"].parameters == systems.SYSTEMS["exercise"].parameters == ()
    assert {"ochmo-tb-013", "ochmo-tb-031"} <= set(systems.VOCABULARY.basis_refs)
    assert "The space food system" in systems.VOCABULARY.basis
    assert "the exercise system" in systems.VOCABULARY.basis
    assert "no como una de sus funciones" in systems.VOCABULARY.life_support_basis


def _drop(key: str) -> Any:
    return lambda raw: raw.update({key: " "})


def _state(raw: dict[str, Any], key: str) -> dict[str, Any]:
    """El estado tal y como está en el fichero: el mismo objeto, para editarlo en sitio."""
    found: dict[str, Any] = next(item for item in raw["states"] if item["key"] == key)
    return found


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_drop("basis"), "tiene que declarar: basis"),
        (_drop("declared_label"), "tiene que declarar: declared_label"),
        (_drop("declared_note"), "tiene que declarar: declared_note"),
        (_drop("relation_basis"), "tiene que declarar: relation_basis"),
        (_drop("not_coded"), "tiene que declarar: not_coded"),
        (lambda raw: raw.update(default_state="unknown"), "no está en la lista de estados"),
        (lambda raw: raw.update(default_state="nominal"), "y solo él, no se puede declarar"),
        (lambda raw: _state(raw, "undeclared").update(declarable=True), "y solo él"),
        (lambda raw: _state(raw, "degraded").update(declarable=False), "y solo él"),
        (lambda raw: _state(raw, "degraded").update(declarable="no"), "verdadero o falso"),
        (lambda raw: raw.update(states=[_state(raw, "undeclared")]), "ningún estado"),
        (lambda raw: raw["states"].append(raw["states"][0]), "estados vacía o con claves"),
        (lambda raw: raw.update(systems=[]), "sistemas vacía o con claves"),
        (lambda raw: raw["systems"].append(raw["systems"][0]), "sistemas vacía o con claves"),
        (lambda raw: raw["systems"][0].update(display=" "), "sin nombre"),
        (lambda raw: raw["systems"][0].update(description=""), "sin descripción"),
        (lambda raw: _state(raw, "degraded").update(display=""), "sin nombre"),
        (lambda raw: raw["systems"][0]["parameters"].append("cabin-mood"), "EMMA no\\s+vigila"),
        (lambda raw: raw["systems"][0]["parameters"].append("cabin-ppco2"), "repite"),
        (lambda raw: raw["basis_refs"].append("ntrs-00000000"), "no está en el registro"),
        (lambda raw: raw["basis_refs"].append(raw["basis_refs"][0]), "repite una ficha"),
        (lambda raw: raw.update(basis_refs="ochmo-tb-002"), "lista de identificadores"),
        (lambda raw: raw["basis_refs"].append(None), "lista de identificadores"),
        (_drop("life_support_basis"), "tiene que declarar: life_support_basis"),
        (lambda raw: raw["systems"][0].pop("life_support"), "si es de soporte vital"),
        (lambda raw: raw["systems"][0].update(life_support="sí"), "si es de soporte vital"),
        (lambda raw: _state(raw, "degraded").pop("off_nominal"), "fuera de lo nominal"),
        (lambda raw: _state(raw, "undeclared").update(off_nominal=True), "no se sabe"),
    ],
)
def test_a_vocabulary_that_cannot_be_honest_is_not_loaded(
    tmp_path: Path, change: Any, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        systems.load(_vocabulary(tmp_path, change))


def test_the_shipped_vocabulary_loads_from_a_copy(tmp_path: Path) -> None:
    loaded = systems.load(_vocabulary(tmp_path, lambda raw: None))
    assert loaded == systems.VOCABULARY


def test_the_basis_says_what_the_eclss_brief_and_the_atcs_back_with_their_cards(
    client: TestClient, tmp_path: Path
) -> None:
    """Decimocuarta ronda: la base deja de decir «sin respaldo bibliográfico» y cita sus fichas."""
    vocabulary = systems.VOCABULARY
    assert vocabulary.basis_refs == (
        "ochmo-tb-002", "nasa-iss-atcs-overview", "ochmo-tb-013", "ochmo-tb-031",
    )
    assert "sin respaldo bibliográfico" not in vocabulary.basis
    assert "OCHMO-TB-002" in vocabulary.basis and "agrupa de otra manera" in vocabulary.basis
    served = _read(client)["basis_sources"]
    assert [item["id"] for item in served] == list(vocabulary.basis_refs)
    assert all(item["url"].startswith("https://www.nasa.gov/") for item in served)
    # Sin fichas declaradas, la base se carga igual y no cita ninguna.
    assert systems.load(_vocabulary(tmp_path, lambda raw: raw.pop("basis_refs"))).basis_refs == ()


# --------------------------------------------------------------------------- #
# El asiento y la lectura
# --------------------------------------------------------------------------- #


def test_nothing_declared_reads_as_unknown_not_as_working(client: TestClient) -> None:
    body = _read(client)
    assert body["label"] == LABEL
    assert "EMMA no lee el estado de ningún sistema" in body["note"]
    assert "Vocabulario de diseño de EMMA" in body["basis"]
    assert [item["key"] for item in body["systems"]] == list(systems.SYSTEMS)
    assert [item["key"] for item in body["states"]] == list(systems.STATES)
    assert body["default_state"] == "undeclared"
    for item in body["systems"]:
        [status] = item["statuses"]
        assert (status["state"], status["state_display"]) == ("undeclared", "sin declarar")
        assert status["declared"] is False and status["since"] is None
        assert status["ledger_index"] is None and status["module"] is None
    assert (body["declared"], body["undeclared"]) == (0, len(systems.SYSTEMS))
    assert "no quiere decir que funcionen" in body["summary"]
    assert body["history"] == []
    relation = _system(body)["parameters"]
    assert {"key": "cabin-ppco2", "display": PARAMETERS["cabin-ppco2"].display} in relation


def test_a_declaration_is_one_signed_entry_and_the_latest_one_holds(client: TestClient) -> None:
    store = get_store()
    size = len(store.ledger)
    first = _declare(client, note="  el lecho 2 no regenera  ")
    assert first.status_code == 201, first.text
    index = first.json()["ledger_index"]
    # UN asiento encadenado y firmado por la consola; el índice que devuelve la API es el suyo.
    assert (index, len(store.ledger)) == (size, size + 1)
    entry = store.ledger.entries[index]
    assert (entry.entry_type, entry.signer) == ("system-status", "crew-console")
    assert {k: v for k, v in entry.payload.items() if k != "_salt"} == {
        "subject": "habitat", "system": AIR, "state": "degraded",
        "at": "2026-11-08T12:00:00+00:00", "note": "el lecho 2 no regenera",
        "declared_by": "CDR",
    }
    assert store.verify_integrity().ok

    status = _system(_read(client))["statuses"]
    assert len(status) == 1
    assert status[0] | {"recorded": None} == {
        "module": None, "module_display": "sistema entero", "state": "degraded",
        "state_display": "degradado", "declared": True,
        "since": "2026-11-08T12:00:00+00:00", "last_declared_at": "2026-11-08T12:00:00+00:00",
        "declarations": 1, "note": "el lecho 2 no regenera", "declared_by": "CDR",
        "ledger_index": index, "recorded": None,
    }
    assert status[0]["recorded"] == entry.recorded.isoformat()

    # Confirmar dos días después que sigue igual no reinicia el «desde».
    later = (T0 + dt.timedelta(days=2)).isoformat()
    again = _declare(client, at=later, declared_by="FE-1")
    status = _system(_read(client))["statuses"][0]
    assert (status["state"], status["since"], status["last_declared_at"]) == (
        "degraded", "2026-11-08T12:00:00+00:00", "2026-11-10T12:00:00+00:00",
    )
    assert (status["declarations"], status["declared_by"], status["note"]) == (2, "FE-1", None)
    assert status["ledger_index"] == again.json()["ledger_index"]

    # Se corrige declarando de nuevo: vale lo último, y lo anterior se conserva.
    fixed = _declare(client, state="nominal", at=(T0 + dt.timedelta(days=3)).isoformat())
    body = _read(client)
    status = _system(body)["statuses"][0]
    assert (status["state"], status["state_display"]) == ("nominal", "nominal")
    assert status["since"] == status["last_declared_at"] == "2026-11-11T12:00:00+00:00"
    assert status["ledger_index"] == fixed.json()["ledger_index"]
    told = body["history"]
    assert [item["state"] for item in told] == ["nominal", "degraded", "degraded"]
    assert [item["previous_state"] for item in told] == ["degraded", "degraded", "undeclared"]
    assert [item["changed"] for item in told] == [True, False, True]
    assert [item["ledger_index"] for item in told] == [index + 2, index + 1, index]
    assert (body["declared"], body["undeclared"]) == (1, len(systems.SYSTEMS) - 1)
    assert len(store.ledger) == size + 3 and store.verify_integrity().ok


def test_a_module_has_its_own_state_and_says_nothing_of_the_whole_system(
    client: TestClient,
) -> None:
    in_lab = _declare(client, "thermal-control", "out-of-service", module="laboratorio")
    assert in_lab.status_code == 201, in_lab.text
    entry = get_store().ledger.entries[in_lab.json()["ledger_index"]]
    assert entry.payload["module"] == "laboratorio"
    statuses = _system(_read(client), "thermal-control")["statuses"]
    # Del sistema entero nadie ha dicho nada: no se rellena una fila «sin declarar» a su lado
    # ni se extiende lo del laboratorio.
    assert [(item["module"], item["state"]) for item in statuses] == [
        ("laboratorio", "out-of-service")
    ]
    assert statuses[0]["module_display"] == "Laboratorio"
    assert statuses[0]["state_display"] == "fuera de servicio"

    _declare(client, "thermal-control", "nominal")
    _declare(client, "thermal-control", "degraded", module="camarotes")
    statuses = _system(_read(client), "thermal-control")["statuses"]
    assert [(item["module"], item["state"], item["declarations"]) for item in statuses] == [
        (None, "nominal", 1), ("laboratorio", "out-of-service", 1), ("camarotes", "degraded", 1),
    ]
    # Lo declarado en un módulo no es el «antes» de otro.
    assert all(item["previous_state"] == "undeclared" for item in _read(client)["history"])
    assert "module" not in get_store().ledger.entries[in_lab.json()["ledger_index"] + 1].payload


def test_outside_the_vocabulary_is_a_422_and_nothing_is_written(client: TestClient) -> None:
    size = len(get_store().ledger)
    for refused in (
        _declare(client, system="warp-drive"),
        _declare(client, system="Air-Revitalization"),
        _declare(client, state="roto"),
        _declare(client, state="Degraded"),
        # «Sin declarar» no se declara: es lo que hay cuando nadie ha dicho nada.
        _declare(client, state="undeclared"),
        _declare(client, module="puente"),
        _declare(client, at="2026-11-08T12:00:00"),
        _declare(client, declared_by="   "),
        _declare(client, declared_by="1234"),
        _declare(client, note="x" * 501),
        _declare(client, subject="crew-01"),
        client.post("/api/habitat/systems/status", json={"system": AIR, "state": "degraded"}),
    ):
        assert refused.status_code == 422, refused.text
    assert len(get_store().ledger) == size
    assert _read(client)["declared"] == 0
    assert client.get("/api/habitat/systems", params={"until": "2026-11-08T12:00:00"}
                      ).status_code == 422


def test_the_store_refuses_what_the_api_refuses(client: TestClient) -> None:
    # El almacén no se fía de quien le llama: la regla está en la escritura del asiento.
    store, console = get_store(), identity_for("crew-console")
    size = len(store.ledger)
    with pytest.raises(ValueError, match="sistema desconocido"):
        store.record_system_status("warp-drive", "degraded", T0, "", "CDR", console)
    for state in ("roto", "undeclared"):
        with pytest.raises(ValueError, match="estado que no se puede declarar"):
            store.record_system_status(AIR, state, T0, "", "CDR", console)
    with pytest.raises(ValueError, match="módulo desconocido"):
        store.record_system_status(AIR, "degraded", T0, "", "CDR", console, module="puente")
    with pytest.raises(ValueError, match="zona horaria"):
        store.record_system_status(AIR, "degraded", T0.replace(tzinfo=None), "", "CDR", console)
    with pytest.raises(ValueError, match="una persona con nombre"):
        store.record_system_status(AIR, "degraded", T0, "", "  ", console)
    assert len(store.ledger) == size
    assert store.system_statuses() == []


def test_only_what_the_console_signed_counts(client: TestClient) -> None:
    store = get_store()
    # Un asiento con la misma forma firmado por otra identidad no es una declaración de la
    # consola: no se da por vigente.
    store.record_system_status(AIR, "out-of-service", T0, "", "nadie", identity_for("otra-fuente"))
    assert len(store.system_statuses()) == 1
    body = _read(client)
    assert body["declared"] == 0 and body["history"] == []
    assert _system(body)["statuses"][0]["state"] == "undeclared"
    # Y uno de la consola de un sistema que ya no está en el vocabulario (es de diseño y puede
    # cambiar) se conserva en el historial con su clave, sin fila vigente.
    store._record_action("system-status", {
        "subject": "habitat", "system": "galley", "state": "degraded",
        "at": T0.isoformat(), "note": "", "declared_by": "CDR",
    }, identity_for("crew-console"))
    body = _read(client)
    assert body["declared"] == 0
    assert [(item["system"], item["system_display"]) for item in body["history"]] == [
        ("galley", "galley")
    ]
    assert store.verify_integrity().ok


def test_a_malformed_entry_is_not_delivered(client: TestClient) -> None:
    # `module` es opcional, pero si está tiene que ser texto, como los demás campos.
    store = get_store()
    store._record_action("system-status", {
        "subject": "habitat", "system": AIR, "state": "degraded", "module": 7,
        "at": T0.isoformat(), "note": "", "declared_by": "CDR",
    }, identity_for("crew-console"))
    with pytest.raises(TamperedRecordError, match="acción mal formada"):
        store.system_statuses()
    assert client.get("/api/habitat/systems").status_code == 409


def test_a_missing_field_is_a_malformed_entry(client: TestClient) -> None:
    store = get_store()
    store._record_action("system-status", {
        "subject": "habitat", "system": AIR, "state": "degraded",
        "at": T0.isoformat(), "declared_by": "CDR",
    }, identity_for("crew-console"))
    with pytest.raises(TamperedRecordError, match="acción mal formada"):
        store.system_statuses()


def test_ground_only_sees_what_existed_at_its_cut(client: TestClient) -> None:
    # Se refiere a un instante anterior al corte, pero se firma ahora: en ese corte no existía.
    assert _declare(client, at="2020-06-01T00:00:00+00:00").status_code == 201
    before_signing = _read(client, until="2021-01-01T00:00:00+00:00")
    assert before_signing["declared"] == 0 and before_signing["history"] == []
    # Ya firmado, pero se refiere a un instante posterior al corte: tampoco.
    assert _declare(client, "power", "degraded", at="2199-01-01T00:00:00+00:00").status_code == 201
    seen = _read(client, until="2100-01-01T00:00:00+00:00")
    assert [item["system"] for item in seen["history"]] == [AIR]
    assert _read(client)["declared"] == 2


# --------------------------------------------------------------------------- #
# Invariante 5 y contexto de una alerta
# --------------------------------------------------------------------------- #


def _what_the_engine_decided(client: TestClient) -> dict[str, Any]:
    """Todo lo que la invariante 5 prohíbe mover: niveles, alertas, excursiones e hipótesis.

    Del detalle de cada alerta se aparta `context`, que es la capa descriptiva donde la
    declaración aparece a propósito; lo que cambia en ella lo fija la prueba del contexto. Y la
    frase del paso «Contextualizar» del flujo de la alerta (§5.34.6), que repite el resumen de
    ese contexto; su estado y el resto de los pasos siguen comparándose.
    """

    def without_context(detail: dict[str, Any]) -> dict[str, Any]:
        kept = {k: v for k, v in detail.items() if k != "context"}
        if "flow" in kept:
            kept["flow"] = {
                **kept["flow"],
                "steps": [
                    {**step, "detail": None} if step["key"] == "contextualize" else step
                    for step in kept["flow"]["steps"]
                ],
            }
        return kept

    decided: dict[str, Any] = {
        "crew": client.get("/api/crew").json(),
        "habitat": client.get("/api/habitat").json(),
    }
    for member in decided["crew"]["crew"]:
        status = client.get("/api/status", params={"subject": member["subject"]}).json()
        decided[member["subject"]] = {
            "alerts": [
                {**alert, "detail": without_context(alert["detail"])}
                for alert in status["alerts"]
            ],
            **{
                key: status[key]
                for key in (
                    "overall_level", "summary", "domains", "recommendations", "rules_version",
                    "predictions",
                )
            },
        }
    return decided


def _contexts(client: TestClient, subject: str) -> list[dict[str, Any]]:
    status = client.get("/api/status", params={"subject": subject}).json()
    return [alert["detail"]["context"] for alert in status["alerts"]]


def _without_systems(context: dict[str, Any]) -> dict[str, Any]:
    """El contexto sin lo que una declaración de sistema puede cambiar en él."""
    items = [item for item in context["items"] if item["kind"] != "system_status"]
    return {
        **context,
        "items": items,
        "sources": [item for item in context["sources"] if item["kind"] != "system_status"],
        "summary": None,
    }


def test_a_declaration_moves_no_level_alert_or_excursion_and_shows_in_the_context(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params=CO2_SCENARIO)
    subject = client.get("/api/crew").json()["crew"][0]["subject"]
    decided = _what_the_engine_decided(client)
    assert decided[subject]["overall_level"] != "nominal" and decided[subject]["alerts"]
    assert decided["habitat"]["excursions"], "el escenario tiene que sacar el CO2 de su límite"
    before = _contexts(client, subject)
    for context in before:
        [source] = [item for item in context["sources"] if item["kind"] == "system_status"]
        assert (source["status"], source["found"]) == ("no_data", 0)
        assert "Nadie ha declarado" in source["note"] and "no se sabe" in source["note"]
        assert not [item for item in context["items"] if item["kind"] == "system_status"]

    # Dos horas antes del inicio de la primera alerta, y otra muy lejos de cualquier ventana.
    anchor = dt.datetime.fromisoformat(before[0]["anchor"])
    near = (anchor - dt.timedelta(hours=2)).isoformat()
    declared = _declare(client, at=near, note="el lecho 2 no regenera")
    far = _declare(client, "power", "out-of-service", at="2026-01-01T00:00:00+00:00")
    assert (declared.status_code, far.status_code) == (201, 201)

    # Invariante 5: ni un nivel, puntuación, alerta, excursión ni versión de reglas. De las
    # hipótesis de tripulación cambia una cosa a propósito (§5.34.4): un sistema de soporte vital
    # declarado degradado dentro de la ventana se añade detrás de la excursión, como
    # coincidencia en el tiempo; las demás quedan como estaban, en el mismo orden.
    now = _what_the_engine_decided(client)
    hypotheses = now["crew"]["correlation"]["hypotheses"]
    added = [item for item in hypotheses if item["kind"] == "declared_system"]
    now["crew"]["correlation"]["hypotheses"] = [
        item for item in hypotheses if item["kind"] != "declared_system"
    ]
    assert now == decided
    # Entra si la declaración cae en la ventana de la vista de tripulación (48 h hasta su
    # instante), y entonces detrás de la excursión de CO2, que es la primera.
    reference = dt.datetime.fromisoformat(decided["crew"]["reference_time"])
    inside = reference - dt.timedelta(days=2) <= dt.datetime.fromisoformat(near) <= reference
    assert [item["system"]["key"] for item in added] == ([AIR] if inside else [])
    assert hypotheses[0]["kind"] == "shared_environment"
    assert hypotheses[: len(hypotheses) - len(added)] == now["crew"]["correlation"]["hypotheses"]
    assert client.get("/api/status").json()["data"]["integrity_ok"] is True

    after = _contexts(client, subject)
    assert [_without_systems(item) for item in after] == [
        _without_systems(item) for item in before
    ]
    context = after[0]
    [item] = [item for item in context["items"] if item["kind"] == "system_status"]
    assert item["label"] == alert_context.LABEL == "correlación temporal, no causa"
    assert item["title"] == (
        "Sistema Revitalización de aire: estado declarado «degradado» "
        "(antes constaba «sin declarar»)"
    )
    assert item["detail"] == "el lecho 2 no regenera"
    index = declared.json()["ledger_index"]
    assert item["source"] == f"{LABEL}; declarado por CDR, asiento {index}"
    assert item["start"] == item["end"] == near
    assert item["timing"].endswith("antes del inicio de la alerta")
    assert (item["value"], item["presence"]) == (None, None)
    [source] = [item for item in context["sources"] if item["kind"] == "system_status"]
    assert (source["status"], source["status_display"], source["found"]) == (
        "with_data", "con dato", 1,
    )
    assert LABEL in source["note"]
    assert context["summary"] != before[0]["summary"]
    # La crónica lo cuenta en el instante al que se refiere, con su rótulo.
    chronicle = client.get("/api/timeline/chronicle", params={"subject": subject}).json()
    told = [event for event in chronicle["events"] if event["fact"] == "system-status-declared"]
    assert [event["at"] for event in told] == ["2026-01-01T00:00:00+00:00", near]
    assert told[1]["que"] == (
        "sistema Revitalización de aire: estado declarado «degradado» (antes constaba «sin "
        f"declarar»; {LABEL}); nota: el lecho 2 no regenera"
    )
    assert (told[1]["tipo"], told[1]["quien"], told[1]["time_basis"]) == ("habitat", "CDR", "data")
    assert told[1]["clave"] == f"ledger:{declared.json()['ledger_index']}"


def test_ground_does_not_get_in_an_alert_what_it_could_not_know(client: TestClient) -> None:
    client.post("/api/simulate", params=CO2_SCENARIO)
    reference = dt.datetime.fromisoformat(
        client.get("/api/status").json()["data"]["reference_time"]
    )
    assert _declare(client, at=reference.isoformat()).status_code == 201

    def sources(**params: Any) -> list[tuple[str, int]]:
        alerts = client.get("/api/status", params=params).json()["alerts"]
        assert alerts
        return [
            (source["status"], source["found"])
            for alert in alerts
            for source in alert["detail"]["context"]["sources"]
            if source["kind"] == "system_status"
        ]

    # A bordo la declaración consta. En el corte de Tierra, una hora antes del instante al que
    # se refiere, todavía no: para Tierra nadie ha declarado nada, y se dice así.
    assert set(sources()) <= {("with_data", 0), ("with_data", 1)}
    cut = (reference - dt.timedelta(hours=1)).isoformat()
    assert set(sources(until=cut)) == {("no_data", 0)}


def test_the_context_source_reads_only_the_window_and_says_when_nothing_changed() -> None:
    onset = dt.datetime(2026, 11, 8, 12, 0, tzinfo=dt.UTC)

    def told(index: int, state: str, hours: float, module: str | None = None) -> dict[str, Any]:
        return {
            "system": AIR, "state": state, "at": (onset + dt.timedelta(hours=hours)).isoformat(),
            "note": "", "declared_by": "CDR", "ledger_index": index,
            "recorded": onset.isoformat(), "signer": "crew-console",
        } | ({} if module is None else {"module": module})

    def around(declarations: list[dict[str, Any]]) -> dict[str, Any]:
        return alert_context.around(
            onset=onset, reference=onset + dt.timedelta(days=1), habitat_readings=[],
            habitat_excursions=[], mission_events=[], solar=None, adoptions=[],
            mission_start=dt.date(2026, 11, 1), mission_days=180, gravity_regime="microgravedad",
            system_declarations=declarations,
        )

    def of(context: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        [source] = [item for item in context["sources"] if item["kind"] == "system_status"]
        return [item for item in context["items"] if item["kind"] == "system_status"], source

    # Los bordes de la ventana cuentan; un minuto fuera, no.
    before, after = alert_context.WINDOW_BEFORE, alert_context.WINDOW_AFTER
    edge = -before.total_seconds() / 3600, after.total_seconds() / 3600
    items, source = of(around([
        told(1, "degraded", edge[0] - 1 / 60), told(2, "degraded", edge[0]),
        told(3, "out-of-service", edge[1], "laboratorio"), told(4, "nominal", edge[1] + 1 / 60),
    ]))
    assert [item["title"] for item in items] == [
        "Sistema Revitalización de aire: estado declarado «degradado» "
        "(sin cambio respecto a lo declarado antes)",
        "Sistema Revitalización de aire en Laboratorio: estado declarado «fuera de servicio» "
        "(antes constaba «sin declarar»)",
    ]
    assert [item["detail"] for item in items] == [None, None]
    assert (source["status"], source["found"]) == ("with_data", 2)
    # Con declaraciones, pero ninguna en la ventana: hay dato y no hay cambio que listar.
    items, source = of(around([told(1, "degraded", -200)]))
    assert items == [] and (source["status"], source["found"]) == ("with_data", 0)
    assert "que no conste un cambio no quiere decir que no lo hubiera" in source["note"]
    # Sin ninguna: no se sabe.
    items, source = of(around([]))
    assert items == [] and (source["status"], source["found"]) == ("no_data", 0)


def test_the_declaration_is_not_a_rule_of_the_engine() -> None:
    # No entra en la huella de reglas, y ningún módulo que decide lo importa.
    assert not [name for name in FINGERPRINTED if "systems" in name]
    root = Path(systems.__file__).resolve().parents[1]
    for name in GUARDED:
        tree = ast.parse((root / Path(*name.split(".")[1:])).with_suffix(".py").read_text("utf-8"))
        imported = {
            alias.name if isinstance(node, ast.Import) else f"{node.module}.{alias.name}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in node.names
        }
        assert not [item for item in imported if "systems" in item or "system_status" in item]
