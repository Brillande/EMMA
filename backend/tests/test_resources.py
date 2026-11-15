"""Los recursos de a bordo, declarados por una persona (especificación §3 y §8; KB H5).

EMMA no lleva inventario. Estas pruebas fijan lo que sí hace y lo que no puede pasar: el
vocabulario es cerrado y sale de lo que las contramedidas ya nombraban, sin reescribir un solo
texto; hay tres estados y «sin declarar» nunca es «disponible»; cada declaración es UN asiento
firmado por la consola (invariante 4); y lo declarado se pone al lado de cada recomendación sin
quitarla, reordenarla ni mover un nivel o una alerta (invariante 5).
"""

import ast
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.advisor.countermeasures import LIBRARY_PATH, LibraryError, load, load_closed
from app.api import routes
from app.api.routes import get_store, identity_for
from app.core import resources
from app.core.resources import VocabularyError, load_vocabulary
from app.core.storage import TamperedRecordError
from app.core.versioning import FINGERPRINTED, GUARDED

LABEL = "declarado por una persona; EMMA no lleva inventario"
SCANNER = "ultrasound-scanner"
T0 = dt.datetime(2026, 11, 8, 12, 0, tzinfo=dt.UTC)


def _row(index: int, resource: str = SCANNER, state: str = "unavailable",
         since: dt.datetime = T0, note: str = "") -> dict[str, Any]:
    """Una declaración con la forma en que la entrega el almacén."""
    return {
        "subject": "mision", "resource": resource, "state": state, "since": since.isoformat(),
        "note": note, "declared_by": "CDR", "ledger_index": index,
        "recorded": "2026-11-08T12:00:00+00:00", "signer": "crew-console",
    }


# --------------------------------------------------------------------------- #
# El vocabulario: cerrado, y sacado de lo que hay
# --------------------------------------------------------------------------- #


READ_ON_2026_10_14 = frozenset({
    "bh-protect-sleep", "bh-circadian-lighting", "bone-resistive-load", "bone-calcium-vitd",
})
# El 2026-10-20 (decimotercera ronda, H10) la muestra de saliva ganó tiempo con su frase y la
# ficha que la da como protocolo citado; su base sigue siendo `demo`.
READ_ON_2026_10_20 = frozenset({"imm-viral-sample"})


def _previous_library() -> list[dict[str, Any]]:
    """La biblioteca tal y como estaba antes del vocabulario (el padre del primer cambio)."""
    repo = Path(__file__).resolve().parents[2]
    shown = subprocess.run(
        ["git", "show", "0c7ad01:backend/app/data/countermeasures.json"],
        cwd=repo, capture_output=True, check=False,
    )
    if shown.returncode != 0:
        pytest.skip("sin el historial de git no hay versión anterior con la que comparar")
    entries: list[dict[str, Any]] = json.loads(shown.stdout.decode("utf-8"))["countermeasures"]
    return entries


def _renamed(value: Any) -> Any:
    """El valor de antes con el nombre del proyecto de hoy, y nada más cambiado."""
    if isinstance(value, str):
        return value.replace("HALO", "EMMA")
    if isinstance(value, list):
        return [_renamed(item) for item in value]
    if isinstance(value, dict):
        return {key: _renamed(item) for key, item in value.items()}
    return value


def test_the_library_is_the_same_as_before_except_for_the_shape_of_resources() -> None:
    before = _previous_library()
    now = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))["countermeasures"]
    assert [item["id"] for item in now] == [item["id"] for item in before]
    library = countermeasures.library()
    assert list(library) == [item["id"] for item in before]
    for old, new in zip(before, now, strict=True):
        # Ni una palabra del contenido cambia: todo lo que no es `resources` es idéntico…
        # (salvo `crew_time_basis`, que el 2026-10-13 ganó la frase literal de su fuente; la
        # cifra, `crew_time_minutes`, sigue siendo la misma y se compara).
        # El 2026-10-21 (C1) cada entrada ganó `family`, un campo nuevo que antes no existía:
        # se compara aparte (`test_countermeasure_library.py`), aquí no cuenta.
        changed = {"resources", "crew_time_basis", "family"}
        # El 2026-10-14 (F4) cuatro entradas ganaron, con su frase leída, tiempo, protocolo y
        # base; la del calcio, además, el riesgo del nutriente. Lo comprueba
        # `test_evidence_completion.py`; aquí se compara el resto.
        if old["id"] in READ_ON_2026_10_14:
            changed |= {"crew_time_minutes", "protocol_ref", "basis", "adverse_effects_note"}
        if old["id"] in READ_ON_2026_10_20:
            changed |= {"crew_time_minutes", "protocol_ref"}
        # El 2026-11-02 el proyecto pasó a llamarse EMMA: «diseño HALO» es ahora «diseño EMMA».
        # Ese es el único cambio de texto admitido; se compara con el nombre ya cambiado.
        assert {k: v for k, v in new.items() if k not in changed} == {
            k: _renamed(v) for k, v in old.items() if k not in changed}, old["id"]
        # …y el texto de cada recurso se conserva, en su orden, como su descripción.
        assert [item["description"] for item in new["resources"]] == old["resources"], old["id"]
        loaded = library[old["id"]]
        assert list(loaded.resources) == old["resources"]
        assert loaded.to_dict()["resources"] == old["resources"]
        assert list(loaded.resource_keys) == [item["key"] for item in new["resources"]]


def test_the_vocabulary_is_exactly_what_the_countermeasures_named_before() -> None:
    before = _previous_library()
    texts = list(dict.fromkeys(text for item in before for text in item["resources"]))
    vocabulary = resources.vocabulary()
    # Un nombre por cada texto distinto que ya había, tal cual, y ninguno más.
    assert [item.name for item in vocabulary.values()] == texts
    # Cada texto de antes apunta siempre a la misma clave: se agrupó lo que se nombraba igual.
    for entry in countermeasures.library().values():
        for key, text in zip(entry.resource_keys, entry.resources, strict=True):
            assert vocabulary[key].name == text, entry.id


def test_every_key_is_used_and_every_resource_is_in_the_vocabulary() -> None:
    vocabulary = resources.vocabulary()
    users = countermeasures.resource_users()
    assert set(users) == set(vocabulary)
    assert countermeasures.unused_resources(countermeasures.library(), vocabulary) == []
    assert users[SCANNER] == ["sans-repeat-both-eyes", "gu-void-repeat", "gu-review-postvoid"]
    # Cada clave va con SU texto, en el orden en que la entrada los lista.
    raw = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))["countermeasures"]
    for item in raw:
        entry = countermeasures.get(item["id"])
        assert list(zip(entry.resource_keys, entry.resources, strict=True)) == [
            (listed["key"], listed["description"]) for listed in item["resources"]]
        assert entry.to_dict()["resource_keys"] == list(entry.resource_keys)
        assert all(vocabulary[key].name == text
                   for key, text in zip(entry.resource_keys, entry.resources, strict=True))


def test_the_served_library_is_loaded_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # La que sirve la aplicación falla si el vocabulario trae un recurso que nadie nombra.
    extra = {**resources.vocabulary(), "botiquin": resources.Resource("botiquin", "botiquín")}
    countermeasures.library.cache_clear()
    try:
        monkeypatch.setattr(countermeasures, "resource_vocabulary", lambda: extra)
        with pytest.raises(LibraryError, match="ninguna contramedida nombra.*botiquin"):
            countermeasures.library()
    finally:
        monkeypatch.undo()
        countermeasures.library.cache_clear()
    assert countermeasures.library()


def _library_file(tmp_path: Path, listed: object) -> Path:
    entry = {
        "id": "x", "domain": "cardiovascular", "action": "Repetir la medida.",
        "indication": "i", "resources": listed, "crew_time_minutes": None,
        "crew_time_basis": "sin fuente", "protocol_ref": None,
        "followup_checks": ["heart-rate"], "followup_window_hours": 1,
        "followup_basis": "diseño EMMA", "contraindications_note": None,
        "adverse_effects_note": None, "basis": "demo",
        "family": "check-surveillance",
    }
    path = tmp_path / "library.json"
    path.write_text(json.dumps({"countermeasures": [entry]}), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("listed", "reason"),
    [
        (["ecógrafo"], "lista de"),
        ([{"key": SCANNER}], "lista de"),
        ([{"key": SCANNER, "description": "ecógrafo", "units": 2}], "lista de"),
        ([{"key": "botiquin", "description": "botiquín"}], "fuera del vocabulario"),
        ([{"key": 7, "description": "ecógrafo"}], "fuera del vocabulario"),
        ([{"key": SCANNER, "description": "  "}], "sin `description`"),
        ([{"key": SCANNER, "description": "ecógrafo"},
          {"key": SCANNER, "description": "otro ecógrafo"}], "aparece dos veces"),
    ],
)
def test_a_resource_outside_the_vocabulary_does_not_load(
    tmp_path: Path, listed: object, reason: str
) -> None:
    with pytest.raises(LibraryError, match=reason):
        load(_library_file(tmp_path, listed))


def test_a_key_that_no_countermeasure_names_does_not_load(tmp_path: Path) -> None:
    path = _library_file(tmp_path, [{"key": SCANNER, "description": "ecógrafo"}])
    scanner = resources.vocabulary()[SCANNER]
    assert set(load_closed(path, {SCANNER: scanner})) == {"x"}
    with pytest.raises(LibraryError, match="ninguna contramedida nombra.*botiquin"):
        load_closed(path, {SCANNER: scanner, "botiquin": resources.Resource("botiquin", "b")})
    # La biblioteca real se carga cerrada: es la que sirve la aplicación.
    with pytest.raises(LibraryError, match="ninguna contramedida nombra"):
        load_closed(LIBRARY_PATH, {**resources.vocabulary(),
                                   "botiquin": resources.Resource("botiquin", "b")})


def _vocabulary_file(tmp_path: Path, body: object) -> Path:
    path = tmp_path / "resources.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({}, "vacío"),
        ({"resources": []}, "vacío"),
        ({"resources": ["ecógrafo"]}, "es \\{key, name\\}"),
        ({"resources": [{"key": "a", "name": "A", "units": 3}]}, "es \\{key, name\\}"),
        ({"resources": [{"key": "Ecógrafo", "name": "A"}]}, "clave de recurso no válida"),
        ({"resources": [{"key": "a b", "name": "A"}]}, "clave de recurso no válida"),
        ({"resources": [{"key": 3, "name": "A"}]}, "clave de recurso no válida"),
        ({"resources": [{"key": "a", "name": "  "}]}, "nombre vacío"),
        ({"resources": [{"key": "a", "name": " A"}]}, "nombre vacío"),
        ({"resources": [{"key": "a", "name": 3}]}, "nombre vacío"),
        ({"resources": [{"key": "a", "name": "A"}, {"key": "a", "name": "B"}]},
         "clave repetida"),
        ({"resources": [{"key": "a", "name": "Agua"}, {"key": "b", "name": "agua"}]},
         "nombre repetido"),
    ],
)
def test_a_vocabulary_that_breaks_its_contract_does_not_load(
    tmp_path: Path, body: object, reason: str
) -> None:
    with pytest.raises(VocabularyError, match=reason):
        load_vocabulary(_vocabulary_file(tmp_path, body))


def test_the_vocabulary_carries_no_quantities_and_says_what_it_is() -> None:
    raw = json.loads(resources.VOCABULARY_PATH.read_text(encoding="utf-8"))
    assert all(set(item) == {"key", "name"} for item in raw["resources"])
    assert "no lleva cantidades" in raw["_nota"] and "inventario" in raw["_nota"]
    assert resources.DECLARED_LABEL == LABEL
    assert "no lleva inventario ni cantidades" in resources.DECLARED_NOTE
    assert "Sin declarar no es disponible" in resources.UNDECLARED_NOTE
    assert "no cambia qué se recomienda" in resources.SCOPE
    assert "lo valora una persona" in resources.SCOPE


# --------------------------------------------------------------------------- #
# Tres estados, y cuál vale
# --------------------------------------------------------------------------- #


def test_only_two_states_can_be_signed_and_undeclared_is_not_one_of_them() -> None:
    assert resources.DECLARABLE == ("available", "unavailable")
    assert resources.STATE_DISPLAY == {
        "available": "declarado disponible", "unavailable": "declarado no disponible",
        "undeclared": "sin declarar",
    }
    resources.check(SCANNER, "available")
    resources.check(SCANNER, "unavailable")
    for state in ("undeclared", "Available", "", "roto"):
        with pytest.raises(ValueError, match="estado desconocido"):
            resources.check(SCANNER, state)
    for name in ("botiquin", "ecógrafo", "", "Ultrasound-Scanner"):
        with pytest.raises(ValueError, match="fuera del vocabulario"):
            resources.check(name, "available")


def test_the_latest_signed_holds_and_the_history_keeps_what_was_there_before() -> None:
    told = [
        _row(12, state="available", note="reparado"),
        _row(10, state="unavailable", note="sonda averiada"),
        _row(11, resource="ared", state="unavailable"),
        _row(13, state="available"),
    ]
    history = resources.history(told)
    assert [(item["ledger_index"], item["resource"], item["previous_state"], item["state"],
             item["changed"]) for item in history] == [
        (10, SCANNER, "undeclared", "unavailable", True),
        (11, "ared", "undeclared", "unavailable", True),
        (12, SCANNER, "unavailable", "available", True),
        (13, SCANNER, "available", "available", False),
    ]
    held = resources.in_force(told)
    assert {key: (item["state"], item["ledger_index"]) for key, item in held.items()} == {
        SCANNER: ("available", 13), "ared": ("unavailable", 11),
    }
    lines = [resources.sentence(item) for item in history]
    assert all(LABEL in line for line in lines)
    assert lines[0] == (
        "recurso «ecógrafo»: declarado no disponible (antes constaba sin declarar; "
        f"{LABEL}); nota: sonda averiada"
    )
    assert "declarado disponible (antes constaba declarado no disponible" in lines[2]
    assert "sin cambio respecto a lo declarado antes" in lines[3]


def test_undeclared_is_never_available() -> None:
    measure = countermeasures.get("sans-repeat-both-eyes").to_dict()
    block = resources.describe(measure, [])
    assert block["state"] == "some-undeclared" and block["label"] == LABEL
    assert [(item["key"], item["state"], item["state_display"], item["description"])
            for item in block["items"]] == [
        (SCANNER, "undeclared", "sin declarar", "ecógrafo"),
        ("trained-operator", "undeclared", "sin declarar", "operador entrenado"),
    ]
    assert block["undeclared"] == ["ecógrafo", "operador entrenado"]
    assert block["unavailable"] == []
    assert block["text"] == "Sin declarar: ecógrafo; operador entrenado."
    assert "Sin declarar no es disponible" in block["caveat"]
    assert "se ofrece igual" in block["caveat"] and "lo valora una persona" in block["caveat"]
    mission = resources.available([])
    assert mission["declared"] == [] and mission["available"] == []
    assert mission["undeclared_count"] == len(resources.vocabulary())
    assert mission["label"] == LABEL and "EMMA no sabe" in mission["summary"]


def test_each_countermeasure_says_what_is_missing() -> None:
    measure = countermeasures.get("sans-repeat-both-eyes").to_dict()
    told = [_row(10, note="sonda averiada")]
    block = resources.describe(measure, told)
    assert block["state"] == "some-unavailable"
    assert block["text"] == (
        "Consta como no disponible: ecógrafo. Sin declarar: operador entrenado."
    )
    assert block["items"][0] | {"recorded": None} == {
        "key": SCANNER, "name": "ecógrafo", "state": "unavailable",
        "state_display": "declarado no disponible", "since": T0.isoformat(),
        "note": "sonda averiada", "declared_by": "CDR", "ledger_index": 10, "recorded": None,
        "description": "ecógrafo",
    }
    assert block["caveat"] is not None
    told.append(_row(11, resource="trained-operator", state="available"))
    assert resources.describe(measure, told)["text"] == "Consta como no disponible: ecógrafo."
    # Solo con TODO declarado disponible se dice que consta todo, y entonces sin advertencia.
    told.append(_row(12, state="available"))
    whole = resources.describe(measure, told)
    assert (whole["state"], whole["caveat"]) == ("all-available", None)
    assert whole["text"] == "Todos los recursos que pide constan declarados disponibles."
    assert whole["unavailable"] == [] and whole["undeclared"] == []
    # Lo declarado de otro recurso no dice nada de estos.
    other = resources.describe(measure, [_row(10, resource="ared", state="available")])
    assert other["state"] == "some-undeclared"
    # Una contramedida que no pide nada lo dice, y no se confunde con «todo disponible».
    nothing = resources.describe({"resources": [], "resource_keys": []}, told)
    assert (nothing["state"], nothing["text"], nothing["items"]) == (
        "none-required", "No pide recursos.", [])


def test_the_annotation_only_adds_a_field() -> None:
    measure = countermeasures.get("gu-void-repeat").to_dict()
    recommendations = [
        {"domain": "renal", "urgency": "alta", "text": "a", "countermeasure": measure},
        {"domain": "renal", "urgency": "baja", "text": "b", "countermeasure": None},
    ]
    for told in ([], [_row(10)], [_row(10, state="available")]):
        annotated = resources.with_resources(recommendations, told)
        assert [{k: v for k, v in item.items() if k != "resource_status"}
                for item in annotated] == recommendations
        assert annotated[1]["resource_status"] is None
        assert annotated[0]["resource_status"] == resources.describe(measure, told)
    assert "resource_status" not in recommendations[0], "no se toca lo que se recibe"


def test_available_resources_gives_only_what_a_person_declared() -> None:
    told = [_row(10, note="sonda averiada"), _row(11, resource="ared", state="available")]
    mission = resources.available(told)
    # En el orden del vocabulario, no en el de la firma.
    assert [(row["key"], row["state"]) for row in mission["declared"]] == [
        ("ared", "available"), (SCANNER, "unavailable"),
    ]
    assert (mission["available"], mission["unavailable"]) == (["ared"], [SCANNER])
    assert mission["undeclared_count"] == len(resources.vocabulary()) - 2
    assert mission["summary"].startswith("Recursos declarados: 2 (1 no disponibles).")
    assert set(mission) == {
        "label", "note", "undeclared_note", "declared", "available", "unavailable",
        "undeclared_count", "summary",
    }, "sin cantidades ni inventario"


def test_ground_does_not_get_what_holds_from_after_its_cut() -> None:
    told = [_row(10, since=T0), _row(11, resource="ared", since=T0 + dt.timedelta(days=2))]
    assert resources.visible(told, None) == told
    assert resources.visible(told, T0 + dt.timedelta(days=1)) == told[:1]
    assert resources.visible(told, T0) == told[:1]
    assert resources.visible(told, T0 - dt.timedelta(seconds=1)) == []


# --------------------------------------------------------------------------- #
# El asiento
# --------------------------------------------------------------------------- #


def test_a_declaration_is_one_signed_entry_in_the_ledger(client: TestClient) -> None:
    store, console = get_store(), identity_for("crew-console")
    size = len(store.ledger)
    entry = store.record_resource_availability(
        SCANNER, "unavailable", T0, "  sonda averiada ", " CDR ", console)
    assert (entry.index, len(store.ledger)) == (size, size + 1)
    assert (entry.entry_type, entry.signer) == ("resource-availability", "crew-console")
    # Recurso, estado, desde cuándo, nota y quién: ni cantidades ni nada más.
    assert {k: v for k, v in entry.payload.items() if k != "_salt"} == {
        "subject": "mision", "resource": SCANNER, "state": "unavailable",
        "since": "2026-11-08T12:00:00+00:00", "note": "sonda averiada", "declared_by": "CDR",
    }
    store.record_resource_availability(SCANNER, "available", T0, "", "CDR", console)
    assert store.verify_integrity().ok
    read = store.resource_declarations()
    assert [(item["ledger_index"], item["state"]) for item in read] == [
        (size, "unavailable"), (size + 1, "available"),
    ]
    assert all(item["signer"] == "crew-console" for item in read)


def test_the_store_refuses_what_cannot_be_signed(client: TestClient) -> None:
    # El almacén no se fía de quien le llama: la regla está en la escritura del asiento.
    store, console = get_store(), identity_for("crew-console")
    size = len(store.ledger)
    with pytest.raises(ValueError, match="fuera del vocabulario"):
        store.record_resource_availability("botiquin", "available", T0, "", "CDR", console)
    with pytest.raises(ValueError, match="estado desconocido"):
        store.record_resource_availability(SCANNER, "undeclared", T0, "", "CDR", console)
    with pytest.raises(ValueError, match="zona horaria"):
        store.record_resource_availability(
            SCANNER, "available", T0.replace(tzinfo=None), "", "CDR", console)
    with pytest.raises(ValueError, match="una persona con nombre"):
        store.record_resource_availability(SCANNER, "available", T0, "", " 12 ", console)
    assert len(store.ledger) == size
    assert store.resource_declarations() == []


def test_a_malformed_entry_is_not_delivered(client: TestClient) -> None:
    store = get_store()
    store._record_action("resource-availability", {
        "subject": "mision", "resource": SCANNER, "state": "unavailable",
        "since": T0.isoformat(), "declared_by": "CDR",
    }, identity_for("crew-console"))
    with pytest.raises(TamperedRecordError, match="acción mal formada"):
        store.resource_declarations()


def test_what_was_already_signed_still_verifies_and_reads(client: TestClient) -> None:
    # Invariante 4: el tipo nuevo no cambia la lectura de los asientos que ya existían.
    store, console = get_store(), identity_for("crew-console")
    store.record_hypothesis_review("confirmed", "cabin-ppco2", T0, "visto", "CDR", console)
    store.record_sensor_binding("wearable-ble", "bind", T0, "", "CDR", console, crew="crew-01")
    client.post("/api/observations", json={"key": "heart-rate", "value": 61, "subject": "crew-01"})
    store.record_resource_availability(SCANNER, "unavailable", T0, "", "CDR", console)
    assert store.verify_integrity().ok
    assert len(store.hypothesis_reviews()) == 1 and len(store.sensor_bindings()) == 1
    assert len(store.resource_declarations()) == 1
    assert client.get("/api/observations", params={"subject": "crew-01"}).json()["count"] == 1


# --------------------------------------------------------------------------- #
# La ruta: declarar y leer
# --------------------------------------------------------------------------- #


def _declare(client: TestClient, resource: str = SCANNER, state: str = "unavailable",
             **extra: Any) -> Any:
    return client.post("/api/resources", json={
        "resource": resource, "state": state, "since": T0.isoformat(), "declared_by": "CDR",
        **extra,
    })


def _read(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/resources", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_nothing_declared_is_everything_undeclared_not_everything_available(
    client: TestClient,
) -> None:
    body = _read(client)
    vocabulary = resources.vocabulary()
    assert body["label"] == LABEL
    assert [row["key"] for row in body["resources"]] == list(vocabulary)
    assert all(row["state"] == "undeclared" and row["state_display"] == "sin declarar"
               and row["since"] is None and row["declarations"] == 0
               for row in body["resources"])
    assert all(row["used_by"] for row in body["resources"]), "ninguno sin contramedida"
    assert body["declared"] == [] and body["available"] == [] and body["history"] == []
    assert body["undeclared_count"] == len(vocabulary)
    assert body["states"] == [
        {"key": "available", "display": "declarado disponible"},
        {"key": "unavailable", "display": "declarado no disponible"},
    ]
    assert body["undeclared_display"] == "sin declarar"
    assert "Sin declarar no es disponible" in body["undeclared_note"]
    assert "no es el inventario" in body["vocabulary_basis"]
    assert "no cambia qué se recomienda" in body["scope"]
    # Cada contramedida de la biblioteca dice qué le consta, también las de hábitat.
    assert [item["id"] for item in body["countermeasures"]] == list(countermeasures.library())
    assert {item["resource_status"]["state"] for item in body["countermeasures"]} == {
        "some-undeclared"}


def test_declaring_writes_one_console_entry_and_the_latest_holds(client: TestClient) -> None:
    store = get_store()
    size = len(store.ledger)
    first = _declare(client, note="  sonda averiada ")
    assert first.status_code == 201, first.text
    index = first.json()["ledger_index"]
    assert (index, len(store.ledger)) == (size, size + 1)
    entry = store.ledger.entries[index]
    assert (entry.entry_type, entry.signer) == ("resource-availability", "crew-console")
    assert {k: v for k, v in entry.payload.items() if k != "_salt"} == {
        "subject": "mision", "resource": SCANNER, "state": "unavailable",
        "since": "2026-11-08T12:00:00+00:00", "note": "sonda averiada", "declared_by": "CDR",
    }
    body = _read(client)
    [row] = [item for item in body["resources"] if item["key"] == SCANNER]
    assert row == {
        "key": SCANNER, "name": "ecógrafo", "state": "unavailable",
        "state_display": "declarado no disponible", "since": "2026-11-08T12:00:00+00:00",
        "note": "sonda averiada", "declared_by": "CDR", "ledger_index": index,
        "recorded": entry.recorded.isoformat(), "declarations": 1,
        "used_by": ["sans-repeat-both-eyes", "gu-void-repeat", "gu-review-postvoid"],
    }
    assert body["unavailable"] == [SCANNER]
    assert body["undeclared_count"] == len(resources.vocabulary()) - 1
    by_id = {item["id"]: item["resource_status"] for item in body["countermeasures"]}
    assert by_id["gu-void-repeat"]["state"] == "some-unavailable"
    assert by_id["gu-void-repeat"]["text"] == "Consta como no disponible: ecógrafo."
    assert by_id["cv-repeat-rest"]["state"] == "some-undeclared"
    assert len(by_id) == len(countermeasures.library()), "ninguna se retira"

    # Se corrige declarando de nuevo: vale lo último firmado y lo anterior se conserva.
    again = _declare(client, state="available", declared_by="FE-1")
    body = _read(client)
    [row] = [item for item in body["resources"] if item["key"] == SCANNER]
    assert (row["state"], row["declarations"], row["declared_by"], row["ledger_index"]) == (
        "available", 2, "FE-1", again.json()["ledger_index"])
    assert [(item["state"], item["previous_state"]) for item in body["history"]] == [
        ("available", "unavailable"), ("unavailable", "undeclared"),
    ]
    assert len(store.ledger) == size + 2 and store.verify_integrity().ok
    assert client.get("/api/resources", params={"until": "2026-11-08T12:00:00"}
                      ).status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"resource": "botiquin"},
        {"resource": "ecógrafo"},
        {"resource": ""},
        {"state": "undeclared"},
        {"state": "roto"},
        {"state": "Available"},
        {"since": "2026-11-08T12:00:00"},
        {"since": "ayer"},
        {"declared_by": "   "},
        {"declared_by": "x" * 65},
        {"declared_by": "123"},
        {"note": "n" * 501},
        {"quantity": 3},
        {"signer": "crew-console"},
    ],
)
def test_what_cannot_be_signed_is_a_422_and_nothing_is_written(
    client: TestClient, change: dict[str, Any]
) -> None:
    size = len(get_store().ledger)
    assert _declare(client, **change).status_code == 422, change
    assert len(get_store().ledger) == size


def test_every_field_but_the_note_is_required(client: TestClient) -> None:
    size = len(get_store().ledger)
    for missing in ("resource", "state", "since", "declared_by"):
        body = {"resource": SCANNER, "state": "available", "since": T0.isoformat(),
                "declared_by": "CDR"}
        del body[missing]
        assert client.post("/api/resources", json=body).status_code == 422, missing
    assert len(get_store().ledger) == size


def test_only_what_the_console_signed_counts(client: TestClient) -> None:
    store = get_store()
    # Con la clave de un wearable no se declara qué hay a bordo.
    store.record_resource_availability(
        SCANNER, "available", T0, "", "nadie", identity_for("wearable-ble"))
    assert len(store.resource_declarations()) == 1
    body = _read(client)
    assert body["declared"] == [] and body["history"] == []
    assert body["undeclared_count"] == len(resources.vocabulary())


def test_ground_only_sees_what_existed_at_its_cut(client: TestClient) -> None:
    # Vale desde un instante anterior al corte, pero se firma ahora: en ese corte no existía.
    assert _declare(client, since="2020-06-01T00:00:00+00:00").status_code == 201
    assert _read(client, until="2021-01-01T00:00:00+00:00")["history"] == []
    # Ya firmado, pero vale desde un instante posterior al corte: tampoco.
    assert _declare(client, "ared", since="2199-01-01T00:00:00+00:00").status_code == 201
    seen = _read(client, until="2100-01-01T00:00:00+00:00")
    assert [item["resource"] for item in seen["history"]] == [SCANNER]
    assert len(_read(client)["declared"]) == 2


# --------------------------------------------------------------------------- #
# El estado: al lado de cada recomendación, y en el contexto de misión
# --------------------------------------------------------------------------- #


FAR = "2100-01-01T00:00:00+00:00"


@pytest.fixture
def insomnia(client: TestClient) -> dict[str, Any]:
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 40}
    ).status_code == 201
    status: dict[str, Any] = client.get("/api/status", params={"until": FAR}).json()
    return status


def _stripped(status: dict[str, Any]) -> dict[str, Any]:
    """El estado sin lo que esta pieza añade."""
    return {
        **status,
        "mission": {k: v for k, v in status["mission"].items() if k != "available_resources"},
        "recommendations": [
            {key: value for key, value in item.items() if key != "resource_status"}
            for item in status["recommendations"]
        ],
    }


def test_the_status_brings_each_recommendation_with_its_resources_undeclared(
    insomnia: dict[str, Any],
) -> None:
    with_measure = [item for item in insomnia["recommendations"] if item["countermeasure"]]
    assert with_measure
    for item in insomnia["recommendations"]:
        if item["countermeasure"] is None:
            assert item["resource_status"] is None
            continue
        block = item["resource_status"]
        assert block["state"] == "some-undeclared" and block["label"] == LABEL
        assert [row["description"] for row in block["items"]] == (
            item["countermeasure"]["resources"])
        assert [row["key"] for row in block["items"]] == item["countermeasure"]["resource_keys"]
        assert all(row["state"] == "undeclared" for row in block["items"])
    mission = insomnia["mission"]["available_resources"]
    assert mission["label"] == LABEL and mission["declared"] == []
    assert mission["undeclared_count"] == len(resources.vocabulary())
    # El resto del contexto de misión sigue ahí.
    assert {"phase", "mission_day", "gravity_regime", "events"} <= set(insomnia["mission"])


def test_a_missing_resource_is_said_next_to_the_recommendation_and_nothing_else_moves(
    client: TestClient, insomnia: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariante 5: mismo ledger de lecturas, con declaraciones y sin ellas."""
    assert insomnia["alerts"] and insomnia["overall_level"] != "nominal"
    chosen = next(item for item in insomnia["recommendations"] if item["countermeasure"])
    position = insomnia["recommendations"].index(chosen)
    needed = chosen["countermeasure"]["resource_keys"]
    assert needed
    assert _declare(client, needed[0], "unavailable", note="no consta a bordo").status_code == 201
    assert _declare(client, "ared", "available").status_code == 201

    after = client.get("/api/status", params={"until": FAR}).json()
    # La recomendación sigue saliendo, en el mismo sitio, con el aviso al lado.
    same = after["recommendations"][position]
    assert same["countermeasure"]["id"] == chosen["countermeasure"]["id"]
    block = same["resource_status"]
    assert block["state"] == "some-unavailable"
    assert block["text"].startswith(
        f"Consta como no disponible: {chosen['countermeasure']['resources'][0]}.")
    assert block["items"][0]["note"] == "no consta a bordo"
    assert "se ofrece igual" in block["caveat"]
    mission = after["mission"]["available_resources"]
    assert mission["unavailable"] == [needed[0]] and mission["available"] == ["ared"]
    # Mismas recomendaciones en el mismo orden, mismos niveles y alertas…
    assert [(item["domain"], item["action"], item["urgency"])
            for item in after["recommendations"]] == [
        (item["domain"], item["action"], item["urgency"])
        for item in insomnia["recommendations"]]
    assert after["overall_level"] == insomnia["overall_level"]
    assert after["domains"] == insomnia["domains"]
    assert after["alerts"] == insomnia["alerts"]
    assert after["rules_version"] == insomnia["rules_version"]
    # …y, de hecho, el estado entero salvo lo que esta pieza añade.
    assert _stripped(after) == _stripped(insomnia)

    # Y sin la pieza, sobre ese mismo ledger: lo mismo.
    monkeypatch.setattr(routes.resource_rules, "with_resources", lambda recs, _told: list(recs))
    monkeypatch.setattr(routes.resource_rules, "available", lambda _told: None)
    without = client.get("/api/status", params={"until": FAR}).json()
    assert all("resource_status" not in item for item in without["recommendations"])
    assert _stripped(without) == _stripped(after)


def test_the_countermeasure_can_still_be_adopted_when_a_resource_is_missing(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    # Decidir si se puede hacer es de una persona (invariante 7): el aviso no bloquea nada.
    chosen = next(item for item in insomnia["recommendations"] if item["countermeasure"])
    measure = chosen["countermeasure"]
    for key in measure["resource_keys"]:
        assert _declare(client, key, "unavailable").status_code == 201
    adopted = client.post("/api/countermeasures/adopt", json={
        "countermeasure_id": measure["id"],
        "reference_time": insomnia["data"]["reference_time"], "adopted_by": "CDR",
    })
    assert adopted.status_code == 201, adopted.text


def test_ground_status_does_not_see_a_declaration_signed_after_its_cut(
    client: TestClient, insomnia: dict[str, Any]
) -> None:
    chosen = next(item for item in insomnia["recommendations"] if item["countermeasure"])
    key = chosen["countermeasure"]["resource_keys"][0]
    # Ya firmada, pero vale desde un instante posterior al corte de Tierra: en él no consta.
    assert _declare(client, key, "unavailable", since="2199-01-01T00:00:00+00:00"
                    ).status_code == 201
    cut = client.get("/api/status", params={"until": FAR}).json()
    assert [item for item in cut["recommendations"] if item["countermeasure"]]
    assert cut["mission"]["available_resources"]["declared"] == []
    assert all(item["resource_status"]["state"] == "some-undeclared"
               for item in cut["recommendations"] if item["countermeasure"])
    # Una firmada por otra identidad no cuenta, en ningún corte.
    get_store().record_resource_availability(
        "ared", "unavailable", T0, "", "nadie", identity_for("wearable-ble"))
    assert _declare(client, key, "unavailable").status_code == 201
    live = client.get("/api/status", params={"until": FAR}).json()
    assert live["mission"]["available_resources"]["unavailable"] == [key]
    # Y la tripulación, sin corte, ve lo mismo que consta firmado por la consola.
    crew = client.get("/api/status").json()
    assert crew["mission"]["available_resources"]["unavailable"] == [key]


def test_no_text_sounds_like_an_order_or_like_a_go_ahead() -> None:
    # Invariante 7 y «sin declarar no es disponible»: ni órdenes, ni vistos buenos por omisión.
    measure = countermeasures.get("sans-repeat-both-eyes").to_dict()
    texts = [resources.DECLARED_NOTE, resources.UNDECLARED_NOTE, resources.SCOPE, resources.RULE,
             resources.VOCABULARY_BASIS, resources.available([])["summary"]]
    for told in ([], [_row(10)], [_row(10, state="available")]):
        block = resources.describe(measure, told)
        texts += [block["text"], block["caveat"] or ""]
    joined = " ".join(texts).casefold()
    for word in ("debe", "prohib", "no realizar", "no puede hacerse", "obligatori", "suspend"):
        assert word not in joined, word
    undeclared = resources.describe(measure, [])
    assert "disponible" not in undeclared["text"].casefold()


# --------------------------------------------------------------------------- #
# La crónica
# --------------------------------------------------------------------------- #


def test_the_chronicle_tells_the_declaration_with_its_label(client: TestClient) -> None:
    client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 10})
    crew = [item["subject"] for item in client.get("/api/crew").json()["crew"]]
    reference = dt.datetime.fromisoformat(
        client.get("/api/status", params={"subject": crew[0]}).json()["data"]["reference_time"])
    since = reference - dt.timedelta(days=2)
    first = _declare(client, since=since.isoformat(), note="sonda averiada")
    second = _declare(
        client, state="available", since=(since + dt.timedelta(days=1)).isoformat())
    # Es de la misión: sale en la crónica de todos.
    for subject in crew[:2]:
        chronicle = client.get("/api/timeline/chronicle", params={"subject": subject}).json()
        told = [event for event in chronicle["events"] if event["tipo"] == "recurso"]
        assert sorted(event["clave"] for event in told) == sorted([
            f"ledger:{first.json()['ledger_index']}", f"ledger:{second.json()['ledger_index']}",
        ])
        assert {event["fact"] for event in told} == {"resource-availability-declared"}
        [declared] = [event for event in told
                      if event["clave"] == f"ledger:{first.json()['ledger_index']}"]
        assert declared["at"] == since.astimezone(dt.UTC).isoformat()
        assert (declared["time_basis"], declared["quien"]) == ("data", "CDR")
        assert declared["que"] == (
            "recurso «ecógrafo»: declarado no disponible (antes constaba sin declarar; "
            f"{LABEL}); nota: sonda averiada"
        )
    # Tierra no ve una declaración firmada después de su corte.
    cut = client.get("/api/timeline/chronicle", params={
        "subject": crew[0], "until": "2020-01-01T00:00:00+00:00"}).json()
    assert not [event for event in cut["events"] if event["tipo"] == "recurso"]

    # Y con un corte entre el instante de datos y la firma: una declaración que vale desde antes
    # del corte, pero firmada después. Solo este caso distingue el filtro por firma
    # (`timeline.counted`) del instante de datos de `_signed`: con 2020 los dos la quitan.
    past = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    late = _declare(client, state="available", since=past.isoformat())
    assert late.status_code == 201, late.text
    cut = client.get("/api/timeline/chronicle", params={
        "subject": crew[0], "until": (past + dt.timedelta(hours=1)).isoformat()}).json()
    assert not [event for event in cut["events"] if event["tipo"] == "recurso"]


# --------------------------------------------------------------------------- #
# No es una regla del motor
# --------------------------------------------------------------------------- #


def test_the_declared_resources_are_not_a_rule_of_the_engine() -> None:
    # Las declaraciones no entran en la huella de reglas, y ningún módulo que decide las lee.
    assert not [name for name in FINGERPRINTED if "resources" in name]
    root = Path(resources.__file__).resolve().parents[1]
    for name in GUARDED:
        tree = ast.parse((root / Path(*name.split(".")[1:])).with_suffix(".py").read_text("utf-8"))
        imported = {
            alias.name if isinstance(node, ast.Import) else f"{node.module}.{alias.name}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in node.names
        }
        assert not [item for item in imported if "resources" in item], name
