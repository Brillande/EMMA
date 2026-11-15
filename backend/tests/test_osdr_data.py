"""La ficha de los estudios de OSDR, leída en su API y comparada con la de EMMA. Sin red: respx.

Las respuestas de `tests/data/osdr/` son las reales de la Biological Data API v2 de OSDR para
OSD-288 y OSD-343, descargadas tal cual el 2026-11-11 (`spikes/spike_osdr_data.py`; datos de NASA,
obra del Gobierno de EE. UU.). La prueba de contrato contra la API real está marcada `live`.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core import egress
from app.core.cache import FileCache
from app.core.config import Settings, get_settings
from app.evidence import osdr_data, registry
from app.evidence.osdr_data import BASE_URL, OsdrDataClient
from app.main import app

DATA = Path(__file__).parent / "data" / "osdr"


def _body(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _mock(
    accession: str, metadata: Any = None, samples: Any = None, router: Any = respx
) -> tuple[Any, Any]:
    meta_route = router.get(f"{BASE_URL}/dataset/{accession}/").mock(
        return_value=httpx.Response(200, json=metadata or _body(f"{accession}_metadata.json"))
    )
    samples_route = router.get(f"{BASE_URL}/dataset/{accession}/samples/").mock(
        return_value=httpx.Response(200, json=samples or _body(f"{accession}_samples.json"))
    )
    return meta_route, samples_route


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(cache_dir=tmp_path)


def _checks(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {check["field"]: check for check in view["checks"]}


# --- respuesta buena ------------------------------------------------------------------------


@respx.mock
def test_osd_288_is_read_and_agrees_with_the_ficha(settings: Settings) -> None:
    _mock("OSD-288")
    view = osdr_data.study("osd-288", OsdrDataClient(settings))
    assert view["available"] and view["status"] == "agrees"
    record = view["osdr"]
    assert record["title"] == "Transcriptome analysis of murine spleen in space"
    assert record["organisms"] == ["Mus musculus"]
    assert record["mission"]["name"] == "SpaceX-9"
    assert record["technology_types"] == ["RNA Sequencing (RNA-Seq)"]
    assert record["release_date"] == "2019-06-18"
    assert record["sample_count"] == 9
    checks = _checks(view)
    assert {name: check["verdict"] for name, check in checks.items()} == {
        "title": "match", "date": "match", "population": "match", "sample_count": "match",
    }
    assert view["age"]["from_cache"] is False


@respx.mock
def test_osd_288_says_mice_not_astronauts(settings: Settings) -> None:
    """La mina de CLAUDE.md: lo que sale de la API dice que son ratones."""
    _mock("OSD-288")
    view = osdr_data.study("osd-288", OsdrDataClient(settings))
    scope = view["osdr"]["scope"]
    assert view["osdr"]["population"] == "animal"
    assert "Mus musculus" in scope and "no son de astronautas" in scope


@respx.mock
def test_osd_288_mission_end_is_explained_not_taken_as_the_return(settings: Settings) -> None:
    """«9/26/16» es el fin del registro de misión de OSDR; los ratones amerizaron el 26-ago-2016
    (protocolo del estudio y NASA RELEASE16-090, leídos el 2026-11-11)."""
    _mock("OSD-288")
    view = osdr_data.study("osd-288", OsdrDataClient(settings))
    assert view["osdr"]["mission"]["end date"] == "9/26/16"
    (note,) = view["mission_notes"]
    assert note["field"] == "end date" and note["osdr"] == "9/26/16"
    assert "26 August 2016" in note["note"] and "RELEASE16-090" in note["note"]
    assert view["status"] == "agrees"  # la nota no es una discrepancia de la ficha
    # El protocolo grabado de la API dice lo que cita la nota.
    protocol = " ".join(_body("OSD-288_metadata.json")["OSD-288"]["metadata"]
                        ["study protocol description"])
    assert "splashed down in the Pacific Ocean offshore from California on 26 August 2016" in (
        protocol
    )


def test_a_mission_note_does_not_cover_another_value() -> None:
    """Si OSDR cambia la fecha, la nota vieja no se pega a la nueva."""
    record = osdr_data.parse(
        "OSD-288", _body("OSD-288_metadata.json"), _body("OSD-288_samples.json")
    )
    assert osdr_data.mission_notes(record)
    changed = dataclasses.replace(
        record, mission={**(record.mission or {}), "end date": "8/26/16"}
    )
    assert osdr_data.mission_notes(changed) == []


@respx.mock
def test_a_human_and_animal_ficha_is_compatible_with_mouse_files(settings: Settings) -> None:
    """OSD-343 analiza astronautas, pero sus muestras depositadas son de ratón: no discrepa."""
    _mock("OSD-343")
    view = osdr_data.study("osd-343", OsdrDataClient(settings))
    assert _checks(view)["population"]["verdict"] == "compatible"
    assert view["status"] == "agrees"
    # Sin cifra de muestras afirmada por EMMA, no se compara ninguna.
    assert "sample_count" not in _checks(view)


@respx.mock
def test_a_different_sample_count_is_declared_not_corrected(settings: Settings) -> None:
    samples = _body("OSD-288_samples.json")
    assay = next(iter(samples["OSD-288"]["assays"].values()))
    assay["samples"].popitem()
    _mock("OSD-288", samples=samples)
    view = osdr_data.study("osd-288", OsdrDataClient(settings))
    check = _checks(view)["sample_count"]
    assert (check["emma"], check["osdr"], check["verdict"]) == (9, 8, "mismatch")
    assert view["status"] == "disagrees"
    # La ficha sigue diciendo lo suyo: comparar no la toca.
    assert "publica 9 muestras" in (registry.get("osd-288").notes or "")


@respx.mock
def test_a_different_title_or_date_is_a_mismatch(settings: Settings) -> None:
    metadata = _body("OSD-288_metadata.json")
    metadata["OSD-288"]["metadata"]["study title"] = "Otro título"
    metadata["OSD-288"]["metadata"]["study public release date"] = 0
    _mock("OSD-288", metadata=metadata)
    checks = _checks(osdr_data.study("osd-288", OsdrDataClient(settings)))
    assert checks["title"]["verdict"] == "mismatch"
    assert checks["date"]["verdict"] == "mismatch"
    assert checks["date"]["osdr"] == "1970-01-01"


@respx.mock
def test_an_unknown_organism_is_not_compared(settings: Settings) -> None:
    metadata = _body("OSD-288_metadata.json")
    metadata["OSD-288"]["metadata"]["organism"] = "Rattus norvegicus"
    _mock("OSD-288", metadata=metadata)
    view = osdr_data.study("osd-288", OsdrDataClient(settings))
    assert _checks(view)["population"]["verdict"] == "not_comparable"
    assert view["osdr"]["population"] is None
    assert "sin clasificar" in view["osdr"]["scope"]


def test_a_partly_unknown_organism_list_is_not_classified() -> None:
    """Un organismo sin clasificar entre otros conocidos tampoco se adivina."""
    record = osdr_data.parse(
        "OSD-288", _body("OSD-288_metadata.json"), _body("OSD-288_samples.json")
    )
    mixed = dataclasses.replace(record, organisms=("Mus musculus", "Rattus norvegicus"))
    assert mixed.population is None
    both = dataclasses.replace(record, organisms=("Mus musculus", "Homo sapiens"))
    assert both.population == "human_and_animal"


def test_every_claimed_sample_count_is_said_in_its_ficha() -> None:
    """La cifra que se compara es la que EMMA afirma: si la ficha cambia, esto lo ve."""
    for ref_id, (count, phrase) in osdr_data.CLAIMED_SAMPLES.items():
        notes = registry.get(ref_id).notes or ""
        assert phrase in notes and str(count) in phrase


def test_the_osdr_studies_are_the_ficha_ones() -> None:
    ids = [ref.id for ref in osdr_data.osdr_refs()]
    assert {"osd-288", "osd-569", "osd-343", "osd-51"} <= set(ids)
    assert "nasa-osdr-portal" not in ids


# --- sin red --------------------------------------------------------------------------------


def test_offline_serves_the_cache_with_its_age(settings: Settings, tmp_path: Path) -> None:
    with respx.mock() as router:
        _mock("OSD-288", router=router)
        OsdrDataClient(settings).study("OSD-288")
    with respx.mock(assert_all_called=False) as router:
        blocked = router.get(url__startswith=BASE_URL)
        offline = Settings(cache_dir=tmp_path, offline=True)
        view = osdr_data.study("osd-288", OsdrDataClient(offline))
    assert not blocked.called
    assert view["available"] and view["age"]["from_cache"] is True
    assert view["osdr"]["sample_count"] == 9


@respx.mock
def test_offline_without_cache_is_unavailable_not_invented(tmp_path: Path) -> None:
    route = respx.get(url__startswith=BASE_URL)
    view = osdr_data.study("osd-288", OsdrDataClient(Settings(cache_dir=tmp_path, offline=True)))
    assert not route.called
    assert view["available"] is False and view["osdr"] is None and view["checks"] == []
    # Lo corta el propio cliente, antes de llegar a la puerta de salida.
    assert view["status"] == "unavailable" and "no leída aún" in view["reason"]


def test_a_stale_cache_is_used_when_the_network_fails(settings: Settings) -> None:
    client = OsdrDataClient(settings)
    with respx.mock() as router:
        _mock("OSD-288", router=router)
        client.study("OSD-288")
    path = client.cache.path_for("osdr-data:OSD-288")
    raw = json.loads(path.read_text(encoding="utf-8"))
    old = dt.datetime.now(dt.UTC) - osdr_data.FRESH_FOR - dt.timedelta(days=1)
    raw["fetched_at"] = old.isoformat()
    path.write_text(json.dumps(raw), encoding="utf-8")
    with respx.mock() as router:
        route = router.get(url__startswith=BASE_URL).mock(
            side_effect=httpx.ConnectError("sin enlace")
        )
        payload = client.study("OSD-288")
    assert route.called
    assert payload.from_cache and payload.age > osdr_data.FRESH_FOR


@respx.mock
def test_a_recent_cache_is_not_requested_again(settings: Settings) -> None:
    meta, _ = _mock("OSD-288")
    client = OsdrDataClient(settings)
    client.study("OSD-288")
    client.study("OSD-288")
    assert meta.call_count == 1


# --- cuerpo roto y error HTTP ---------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize("body", [b"<html>", b'{"error": "cuota"}', b'{"OSD-288": {}}'])
def test_a_broken_body_is_unavailable(settings: Settings, body: bytes) -> None:
    respx.get(f"{BASE_URL}/dataset/OSD-288/").mock(return_value=httpx.Response(200, content=body))
    respx.get(f"{BASE_URL}/dataset/OSD-288/samples/").mock(
        return_value=httpx.Response(200, json=_body("OSD-288_samples.json"))
    )
    view = osdr_data.study("osd-288", OsdrDataClient(settings))
    assert view["status"] == "unavailable" and view["osdr"] is None


@respx.mock
def test_samples_without_their_list_are_unavailable(settings: Settings) -> None:
    _mock("OSD-288", samples={"OSD-288": {"assays": {"a": {"REST_URL": "x"}}}})
    view = osdr_data.study("osd-288", OsdrDataClient(settings))
    assert view["status"] == "unavailable"


@respx.mock
def test_an_http_error_is_unavailable(settings: Settings) -> None:
    respx.get(f"{BASE_URL}/dataset/OSD-288/").mock(
        return_value=httpx.Response(422, json={"code": 422, "HTTPError": "UNPROCESSABLE_ENTITY"})
    )
    view = osdr_data.study("osd-288", OsdrDataClient(settings))
    assert view["status"] == "unavailable" and "422" in view["reason"]


@respx.mock
def test_one_study_failing_does_not_take_down_the_others(settings: Settings) -> None:
    _mock("OSD-288")
    respx.get(url__startswith=f"{BASE_URL}/dataset/OSD-343/").mock(
        return_value=httpx.Response(422, json={})
    )
    refs = [registry.get("osd-288"), registry.get("osd-343")]
    payload = osdr_data.studies(OsdrDataClient(settings), refs)
    assert payload["counts"] == {"agrees": 1, "disagrees": 0, "unavailable": 1}


# --- lo que sale ----------------------------------------------------------------------------


@respx.mock
def test_the_request_carries_only_the_public_study_identifier(
    settings: Settings, tmp_path: Path
) -> None:
    """Nada nuestro en la petición: solo el identificador público del estudio, con un
    User-Agent genérico; ni identificadores de tripulante, ni rutas locales, ni el proyecto."""
    meta, samples = _mock("OSD-288")
    OsdrDataClient(settings).study("OSD-288")
    for route in (meta, samples):
        request = route.calls.last.request
        assert request.url.host == "visualization.osdr.nasa.gov"
        assert dict(request.url.params) == {"format": "json"}
        sent = " ".join([str(request.url), *(f"{k}: {v}" for k, v in request.headers.items()),
                         request.content.decode("utf-8", "replace")]).lower()
        assert request.headers["user-agent"].startswith("python-httpx/")
        for forbidden in ("crew", "astronaut", "subject", "emma", "ellande", "c:\\", "/users/",
                          str(tmp_path).lower(), "tripul"):
            assert forbidden not in sent, forbidden
        assert request.method == "GET" and not request.content


def test_osdr_data_goes_out_only_through_its_purpose(settings: Settings) -> None:
    assert egress.ALLOWLIST[osdr_data.PURPOSE] == frozenset({"visualization.osdr.nasa.gov"})
    with pytest.raises(egress.EgressNotAllowed):
        egress.authorize(settings, osdr_data.PURPOSE, "https://osdr.nasa.gov/osdr/data/osd/meta/1")


# --- ruta -----------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path: Path) -> Any:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, assistant_warmup=False
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def test_route_offline_without_cache_says_unavailable(api: TestClient) -> None:
    payload = api.get("/api/osdr/studies").json()
    assert payload["studies"] and all(not s["available"] for s in payload["studies"])
    assert payload["counts"]["unavailable"] == len(payload["studies"])


def test_route_serves_a_cached_study(api: TestClient, tmp_path: Path) -> None:
    record = osdr_data.parse(
        "OSD-288", _body("OSD-288_metadata.json"), _body("OSD-288_samples.json")
    )
    FileCache(tmp_path / "osdr-data").put(
        "osdr-data:OSD-288", record.to_dict(), source=osdr_data.SOURCE
    )
    view = api.get("/api/osdr/studies/osd-288").json()
    assert view["status"] == "agrees" and view["age"]["from_cache"] is True


@pytest.mark.parametrize("ref_id", ["no-existe", "nasa-osdr-portal"])
def test_route_unknown_or_not_osdr_is_404(api: TestClient, ref_id: str) -> None:
    assert api.get(f"/api/osdr/studies/{ref_id}").status_code == 404


def test_record_round_trips() -> None:
    record = osdr_data.parse(
        "OSD-288", _body("OSD-288_metadata.json"), _body("OSD-288_samples.json")
    )
    assert osdr_data.StudyRecord.from_dict(record.to_dict()) == record
    assert dataclasses.asdict(record)["sample_count"] == 9
