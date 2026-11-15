"""Informes de NTRS cotejados con la ficha de EMMA (`app/evidence/ntrs.py`). Sin red: respx.

La respuesta grabada (`tests/data/ntrs/20170004345.json`) es la ficha real de NTRS del memorando
NASA/TM-2017-219290, descargada el 2026-11-11 (obra del Gobierno de EE. UU.).
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.api.console_header import CONSOLE_HEADER
from app.core.config import Settings
from app.evidence import citations, ntrs, registry
from app.evidence.citations import EXISTS, NOT_FOUND, NOT_IN_NTRS, UNRESOLVABLE

RECORDED = Path(__file__).parent / "data" / "ntrs" / "20170004345.json"
TM_ID = "20170004345"
TM_URL = f"{citations.NTRS_API}/{TM_ID}"


def _recorded() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(RECORDED.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def online(tmp_path: Path) -> Settings:
    return Settings(cache_dir=tmp_path, offline=False)


def _offline(settings: Settings) -> Settings:
    return Settings(cache_dir=settings.cache_dir, offline=True)


def _stale(client: ntrs.NtrsClient, ntrs_id: str) -> None:
    """Envejece la consulta guardada más allá de `FRESH_FOR`."""
    path = client.cache.path_for(f"ntrs:{ntrs_id}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["fetched_at"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(raw), encoding="utf-8")


# --- La ficha de NTRS ----------------------------------------------------------------------------


def test_the_recorded_record_is_parsed() -> None:
    record = ntrs.parse_record(_recorded())
    assert record.ntrs_id == TM_ID
    assert record.title.startswith("Interpretation of NASA-STD-3001 Levels of Care")
    assert record.authors[0] == "Hailey, Melinda"
    assert record.years == (2017,)
    # Sin el prefijo «Report Number: » y sin repetir.
    assert "NASA/TM-2017-219290" in record.report_numbers
    assert len(record.report_numbers) == len(set(record.report_numbers))
    assert not any(n.startswith("Report Number") for n in record.report_numbers)


@pytest.mark.parametrize("raw", [[], {"id": 1}, {"title": "x"}, {"id": "abc", "title": "x"}])
def test_a_body_that_is_not_a_record_is_refused(raw: Any) -> None:
    with pytest.raises(ValueError):
        ntrs.parse_record(raw)


# --- El cliente: red, caché, sin red, errores -----------------------------------------------------


@respx.mock
def test_good_response_is_served_and_cached(online: Settings) -> None:
    route = respx.get(TM_URL).mock(return_value=httpx.Response(200, json=_recorded()))
    client = ntrs.NtrsClient(online)
    first = client.lookup(TM_ID)
    assert first.status == EXISTS
    assert first.record is not None and first.record.ntrs_id == TM_ID
    assert first.payload is not None and not first.payload.from_cache
    # Recién consultada, no se vuelve a preguntar.
    again = client.lookup(TM_ID)
    assert route.call_count == 1
    assert again.payload is not None and again.payload.from_cache


@respx.mock
def test_offline_serves_the_cache_with_its_age(online: Settings) -> None:
    respx.get(TM_URL).mock(return_value=httpx.Response(200, json=_recorded()))
    ntrs.NtrsClient(online).lookup(TM_ID)
    offline = ntrs.NtrsClient(_offline(online))
    _stale(offline, TM_ID)
    result = offline.lookup(TM_ID).to_dict()
    assert result["status"] == EXISTS
    assert result["from_cache"] is True
    assert result["age_seconds"] > 30 * 86400
    assert result["fetched_at"].startswith("2020-01-01")
    assert result["age"].startswith("hace ")


def test_offline_without_cache_is_unavailable_and_does_not_go_out(tmp_path: Path) -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url__regex=r".*")
        result = ntrs.NtrsClient(Settings(cache_dir=tmp_path, offline=True)).lookup(TM_ID)
    assert route.call_count == 0
    assert result.status == UNRESOLVABLE
    assert result.record is None and result.payload is None
    assert "no disponible" in result.detail
    assert result.to_dict()["status_display"] == "no disponible"


@respx.mock
def test_a_broken_body_is_unresolvable_and_not_cached(online: Settings) -> None:
    respx.get(TM_URL).mock(return_value=httpx.Response(200, text="<html>mantenimiento</html>"))
    client = ntrs.NtrsClient(online)
    result = client.lookup(TM_ID)
    assert result.status == UNRESOLVABLE
    assert result.record is None
    assert not client.cache.path_for(f"ntrs:{TM_ID}").exists()


@respx.mock
def test_a_record_without_title_is_unresolvable(online: Settings) -> None:
    respx.get(TM_URL).mock(return_value=httpx.Response(200, json={"id": int(TM_ID)}))
    assert ntrs.NtrsClient(online).lookup(TM_ID).status == UNRESOLVABLE


@respx.mock
def test_http_error_is_unresolvable_without_cache(online: Settings) -> None:
    respx.get(TM_URL).mock(return_value=httpx.Response(503))
    result = ntrs.NtrsClient(online).lookup(TM_ID)
    assert result.status == UNRESOLVABLE
    assert "503" in result.detail


@respx.mock
def test_http_error_falls_back_to_the_stale_cache_and_says_so(online: Settings) -> None:
    route = respx.get(TM_URL).mock(return_value=httpx.Response(200, json=_recorded()))
    client = ntrs.NtrsClient(online)
    client.lookup(TM_ID)
    _stale(client, TM_ID)
    route.mock(return_value=httpx.Response(503))
    result = client.lookup(TM_ID)
    assert route.call_count >= 2
    assert result.status == EXISTS
    assert result.payload is not None and result.payload.from_cache
    assert "falló" in result.detail and "503" in result.detail


@respx.mock
def test_not_in_ntrs_is_never_called_fabricated(online: Settings) -> None:
    respx.get(TM_URL).mock(return_value=httpx.Response(404, json={"statusCode": 404}))
    client = ntrs.NtrsClient(online)
    result = client.lookup(TM_ID)
    assert result.status == NOT_IN_NTRS != NOT_FOUND
    assert "no prueba que la cita sea inventada" in result.detail.lower()
    # El «no está» también se guarda con su edad: sin red se sigue sabiendo.
    assert ntrs.NtrsClient(_offline(online)).lookup(TM_ID).status == NOT_IN_NTRS


def test_a_malformed_number_is_refused_before_going_out(online: Settings) -> None:
    with pytest.raises(ValueError):
        ntrs.NtrsClient(online).lookup("2017000434")


# --- Lo que sale: solo el número público --------------------------------------------------------

GENERIC_HEADERS = {"host", "accept", "accept-encoding", "connection", "user-agent"}


@respx.mock
def test_the_request_carries_only_the_public_number(online: Settings) -> None:
    """Ni tripulación, ni usuario, ni proyecto, ni rutas locales: el número de NTRS y nada más."""
    route = respx.get(url__regex=r"https://ntrs\.nasa\.gov/.*").mock(
        return_value=httpx.Response(200, json=_recorded())
    )
    ntrs.NtrsClient(online).lookup(TM_ID)
    [call] = route.calls
    request = call.request
    assert str(request.url) == f"https://ntrs.nasa.gov/api/citations/{TM_ID}"
    assert request.url.query == b""
    assert request.content == b""
    assert {name.lower() for name in request.headers} <= GENERIC_HEADERS
    assert request.headers["user-agent"].startswith("python-httpx/")
    sent = f"{request.url} {dict(request.headers)}".lower()
    for private in (str(online.cache_dir).lower(), str(Path.home()).lower(), "emma", "crew"):
        assert private not in sent
    # Nada de identificadores de tripulante (los del simulador son siglas o «crew-…»).
    assert re.fullmatch(r"https://ntrs\.nasa\.gov/api/citations/\d{11}", str(request.url))


# --- Cotejo con la ficha de EMMA -----------------------------------------------------------------


def _ref(**changes: Any) -> registry.EvidenceRef:
    return dataclasses.replace(registry.get("ntrs-20170004345"), **changes)


def test_the_registry_entry_of_the_memorandum_matches_ntrs() -> None:
    fields = ntrs.compare(_ref(), ntrs.parse_record(_recorded()))
    assert {name: field["state"] for name, field in fields.items()} == {
        "title": ntrs.MATCH, "authors": ntrs.MATCH, "year": ntrs.MATCH,
        "report_number": ntrs.MATCH,
    }


def test_each_field_that_differs_says_both_sides() -> None:
    record = ntrs.parse_record(_recorded())
    fields = ntrs.compare(
        _ref(title="Otro título", authors=("Hailey M", "Pérez J", "et al."), date="2019-04",
             source="NASA/TM-2017-999999 (abril de 2017)"),
        record,
    )
    assert fields["title"]["state"] == ntrs.DIFFERS
    assert fields["title"]["ntrs"] == record.title
    assert fields["authors"]["state"] == ntrs.DIFFERS
    assert "Pérez J" in fields["authors"]["detail"] and "et al." not in fields["authors"]["emma"]
    assert fields["year"] == {"state": ntrs.DIFFERS, "emma": 2019, "ntrs": [2017], "detail": ""}
    assert fields["report_number"]["state"] == ntrs.DIFFERS
    assert "NASA/TM-2017-999999" in fields["report_number"]["detail"]


def _smo_record(title: str) -> ntrs.NtrsRecord:
    """La ficha de NTRS 20130000839 como la dio NTRS el 2026-11-11, con el título que se pida."""
    return ntrs.NtrsRecord(
        ntrs_id="20130000839", title=title,
        authors=("Smith, Scott M.", "Heer, M. A.", "Zwart, S. R."), years=(2012, 2013),
        report_numbers=(), sti_type="CONFERENCE_PAPER",
    )


def test_a_reviewed_difference_is_explained_with_its_reason() -> None:
    """«SMO -16E» es errata de NTRS: la portada dice «SMO 016E». Sale explicada, no «difiere»."""
    fields = ntrs.compare(
        registry.get("ntrs-20130000839"), _smo_record("Nutritional Status Assessment (SMO -16E)")
    )
    assert fields["title"]["state"] == ntrs.EXPLAINED
    assert "SMO 016E" in fields["title"]["detail"] and "errata" in fields["title"]["detail"].lower()
    assert fields["title"]["ntrs"] == "Nutritional Status Assessment (SMO -16E)"


def test_an_explanation_stops_holding_when_ntrs_changes() -> None:
    """Si NTRS cambia lo que escribe, la explicación vieja no tapa la diferencia nueva."""
    fields = ntrs.compare(
        registry.get("ntrs-20130000839"), _smo_record("Nutritional Status Assessment (SMO 99)")
    )
    assert fields["title"]["state"] == ntrs.DIFFERS


def test_an_explanation_stops_holding_when_emma_changes() -> None:
    ref = dataclasses.replace(registry.get("ntrs-20130000839"), title="Otro título")
    fields = ntrs.compare(ref, _smo_record("Nutritional Status Assessment (SMO -16E)"))
    assert fields["title"]["state"] == ntrs.DIFFERS


def test_explained_differences_name_real_registry_entries_and_fields() -> None:
    known = {ref.id for ref in ntrs.ntrs_references()}
    for ref_id, fields in ntrs.EXPLAINED_DIFFERENCES.items():
        assert ref_id in known, ref_id
        for name, explanation in fields.items():
            assert name in {"title", "authors", "year", "report_number"}, (ref_id, name)
            assert explanation["why"] and "emma" in explanation and "ntrs" in explanation
    # Lo que EMMA escribe en cada explicación es lo que escribe hoy la ficha: si se corrige la
    # ficha, la explicación se revisa con ella.
    for ref_id, fields in ntrs.EXPLAINED_DIFFERENCES.items():
        ref = registry.get(ref_id)
        if "title" in fields:
            assert fields["title"]["emma"] == ref.title, ref_id
        if "authors" in fields:
            assert fields["authors"]["emma"] == list(ref.authors), ref_id


def test_what_emma_does_not_write_is_not_checkable() -> None:
    fields = ntrs.compare(
        _ref(authors=(), date=None, source="NASA NTRS 20170004345"),
        ntrs.parse_record(_recorded()),
    )
    assert fields["authors"]["state"] == ntrs.UNCHECKABLE
    assert fields["year"]["state"] == ntrs.UNCHECKABLE
    assert fields["report_number"]["state"] == ntrs.UNCHECKABLE


@pytest.mark.parametrize(
    ("emma", "ntrs_name"),
    [("Myers JG Jr", "Myers, Jerry G., Jr."), ("Pletcher DL", "David L Pletcher"),
     ("Clément GR", "Clement, Gilles R."), ("De Dios YE", "De Dios, Yiri E.")],
)
def test_author_surnames_match_across_ntrs_spellings(emma: str, ntrs_name: str) -> None:
    record = dataclasses.replace(ntrs.parse_record(_recorded()), authors=(ntrs_name,))
    assert ntrs.compare(_ref(authors=(emma,)), record)["authors"]["state"] == ntrs.MATCH


def test_report_numbers_match_with_other_punctuation() -> None:
    record = dataclasses.replace(
        ntrs.parse_record(_recorded()), report_numbers=("JSC-20584/REVC", "HRP-48032 Rev. B")
    )
    for source in ("JSC 20584 Rev C — NASA JSC (2024)", "HRP-48032 Rev. B (2023)"):
        assert ntrs.compare(_ref(source=source), record)["report_number"]["state"] == ntrs.MATCH


def test_every_ntrs_reference_of_the_registry_has_a_valid_number() -> None:
    references = ntrs.ntrs_references()
    assert len(references) > 10
    assert all(re.fullmatch(r"\d{11}", ntrs.ntrs_id_of(ref) or "") for ref in references)
    # Una URL de descarga de NTRS también da el número.
    assert ntrs.ntrs_id_of(registry.get("jsc-20584-rev-c")) == "20240007713"


# --- La comprobación de citas: NTRS es un registro más --------------------------------------------


@pytest.mark.parametrize(
    "raw", ["NTRS 20170004345", "NASA NTRS: 20170004345",
            "https://ntrs.nasa.gov/citations/20170004345"],
)
def test_classify_finds_an_ntrs_number(raw: str) -> None:
    assert citations.classify(raw) == ("ntrs", TM_ID)


def test_find_identifiers_takes_ntrs_only_with_its_word_or_url() -> None:
    text = (
        "Hailey 2017 (NTRS 20170004345); ver https://ntrs.nasa.gov/api/citations/20240007713/"
        "downloads/x.pdf. Una cifra suelta de once dígitos, 12345678901, no es una cita."
    )
    found = {pair for pair in citations.find_identifiers(text) if pair[0] == "ntrs"}
    assert found == {("ntrs", TM_ID), ("ntrs", "20240007713")}


@pytest.mark.parametrize(
    ("response", "status"),
    [(httpx.Response(200, json={"id": 20170004345, "title": "T"}), EXISTS),
     (httpx.Response(404), NOT_IN_NTRS),
     (httpx.Response(400), citations.UNPARSEABLE),
     (httpx.Response(200, text="no json"), UNRESOLVABLE),
     (httpx.Response(502), UNRESOLVABLE)],
)
def test_verify_asks_ntrs_for_an_ntrs_number(response: httpx.Response, status: str) -> None:
    with respx.mock:
        respx.get(TM_URL).mock(return_value=response)
        with httpx.Client() as client:
            [verdict] = citations.verify(client, [("ntrs", TM_ID)])
    assert verdict.status == status
    assert verdict.registry == "NTRS"


# --- La ruta ------------------------------------------------------------------------------------


def test_route_lists_the_ntrs_references_offline(client: TestClient) -> None:
    body = client.get("/api/dossier/ntrs").json()
    assert body["offline"] is True
    assert body["count"] == len(ntrs.ntrs_references())
    assert body["by_status"][UNRESOLVABLE] == body["count"]
    assert all(item["fields"] is None for item in body["references"])
    assert "no significa cita inventada" in body["scope"]


def test_route_for_one_reference_and_its_404s(client: TestClient) -> None:
    body = client.get("/api/dossier/ntrs/ntrs-20170004345").json()
    assert body["ntrs_id"] == TM_ID and body["status"] == UNRESOLVABLE
    assert client.get("/api/dossier/ntrs/no-existe").status_code == 404
    assert client.get("/api/dossier/ntrs/law-2014").status_code == 404  # sin número de NTRS


def test_refresh_needs_the_console_header_and_does_not_fail_offline(client: TestClient) -> None:
    assert client.post("/api/dossier/ntrs/refresh").status_code == 200
    del client.headers[CONSOLE_HEADER]
    assert client.post("/api/dossier/ntrs/refresh").status_code == 403
