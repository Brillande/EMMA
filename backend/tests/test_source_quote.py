# SPDX-License-Identifier: AGPL-3.0-or-later
"""La frase literal del informe citado, a la vista antes de la segunda firma y dentro de su asiento.

Quien contrafirma una decisión de alto riesgo lee lo que el informe dice, no lo que tecleó quien
cita: la frase sale de la bóveda de EMMA (`evidence/vault.py`, `locate`), tal cual, y si no se
localiza no se rellena con nada. Sin red; OCR y modelo simulados.

Usa `fuente_clinica` de la copia literal de Polaris sin modificarla (`polaris/ADOPTADO.txt`).
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient

from app import polaris
from app.api.routes import get_store
from app.core.storage import DRAFT_COUNTERSIGN_ENTRY_TYPE
from app.evidence import vault
from tests.test_interpret import LLM, clean_run
from tests.test_vault import REPORT_TEXT, _TwoPages, report  # noqa: F401  (`report`: fixture)

# Como lo teclearía alguien: sin tildes y con otras mayúsculas que el informe.
TYPED = "HIGADO de tamano normal, sin lesiones"
# El informe se firma des-identificado y, tal como lo deja esa cadena, sin tildes.
LITERAL = "higado de tamano normal, sin lesiones"
ABSENT = "lesion hipoecoica de 2 cm en el segmento VI"


def _stored(report: int) -> str:  # noqa: F811
    """El texto del informe tal como está firmado: el que se copia a la bóveda."""
    blob, _ = get_store().report_blob(report)
    return "\n\n".join(str(page["text"]) for page in blob["ocr"]["pages"])


def _high_risk_draft(client: TestClient, measured: int) -> tuple[str, dict[str, Any]]:
    """Un borrador con una primera firma de alto riesgo: la base de la ruta y el cuerpo común."""
    with respx.mock:
        respx.post(f"{LLM}/api/chat").mock(side_effect=clean_run())
        client.post(f"/api/imaging/studies/{measured}/draft")
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    first = {
        "decision": "accepted", "signed_by": "CMO",
        "comment": "Acepto; suspender la medicación y repetir la medida en 24 h",
        "text_sha256": draft["text_sha256"],
    }
    base = f"/api/imaging/drafts/{draft['ledger_index']}"
    assert client.post(f"{base}/sign", json=first).status_code == 201
    return base, {**first, "signed_by": "Ingeniera de vuelo", "comment": ""}


def _seen(quote: dict[str, Any]) -> dict[str, Any]:
    return {key: quote[key] for key in ("estado", "frase", "sha256")}


def _countersign_entry(measured: int) -> dict[str, Any]:
    [payload] = [
        entry.payload for entry in get_store().ledger._view()
        if entry.entry_type == DRAFT_COUNTERSIGN_ENTRY_TYPE
    ]
    assert isinstance(payload, dict)
    return payload


# --------------------------------------------------------------------------- #
# La bóveda: de dónde sale la frase
# --------------------------------------------------------------------------- #


def test_the_phrase_is_the_one_in_the_vault_not_the_one_typed(
    client: TestClient, report: int  # noqa: F811
) -> None:
    status, quote = vault.locate(get_store(), report, TYPED, "crew-01", "Ingeniera de vuelo")
    assert status["estado"] == "confirmada"
    assert quote["estado"] == "localizada"
    assert quote["frase"] == LITERAL and quote["frase"] != TYPED
    assert _stored(report)[quote["inicio"]:quote["fin"]] == LITERAL
    assert quote["puntero"] == f"informe:{report}" and quote["asiento"] == report
    assert quote["sha256"] == hashlib.sha256(_stored(report).encode("utf-8")).hexdigest()
    assert quote["desidentificado"] is True


def test_a_phrase_keeps_its_line_breaks_and_loose_accents() -> None:
    """Tal cual: con el salto de línea del informe, y con la tilde aunque venga suelta (NFD)."""

    class _Decomposed(_TwoPages):
        PAGES = (unicodedata.normalize("NFD", "Se repitió la medición y no varió. Sin más."),)

    _, quote = vault.locate(_TwoPages(), 424243, "abdominal higado de tamano", "crew-01", "CMO")
    assert quote["frase"] == "abdominal.\nHígado de tamaño"
    _, loose = vault.locate(_Decomposed(), 424243, "la medicion y no vario", "crew-01", "CMO")
    assert loose["frase"] == unicodedata.normalize("NFD", "la medición y no varió")
    (vault._vault() / "informe-424243.md").unlink()


def test_a_citation_that_is_not_there_gets_no_phrase(
    client: TestClient, report: int  # noqa: F811
) -> None:
    status, quote = vault.locate(get_store(), report, ABSENT, "crew-01", "CMO")
    assert status["estado"] == "fragmento_ausente"
    assert quote["estado"] == "no_localizada"
    assert quote["frase"] == "" and quote["inicio"] is None and quote["fin"] is None
    assert ABSENT not in str(quote)  # ni lo tecleado, ni una paráfrasis


def test_a_report_of_someone_else_shows_no_phrase(
    client: TestClient, report: int  # noqa: F811
) -> None:
    _, quote = vault.locate(get_store(), report, TYPED, "crew-02", "CMO")
    assert quote["estado"] == "no_localizada" and quote["frase"] == ""


def test_the_text_read_must_be_the_text_just_checked(
    client: TestClient, report: int, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """Si la copia no es la que `cotejar` acaba de sellar, no se enseña nada de ella."""
    real = vault._check  # `locate` coteja ya con el cerrojo tomado: no pasa por `check`

    def other_hash(*args: Any) -> dict[str, Any]:
        return {**real(*args), "sha256": "0" * 64}

    monkeypatch.setattr(vault, "_check", other_hash)
    _, quote = vault.locate(get_store(), report, TYPED, "crew-01", "CMO")
    assert quote["estado"] == "no_localizada" and quote["frase"] == ""


def test_a_normalisation_that_stops_matching_polaris_shows_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La posición se saca con una normalización propia: solo vale si da lo mismo que la suya."""
    tool = polaris.load("fuente_clinica")
    assert vault._span(tool, REPORT_TEXT, TYPED) is not None
    real = vault._normalised

    def drifted(text: str) -> tuple[str, list[int]]:
        normal, origin = real(text)
        return normal + " x", [*origin, origin[-1], origin[-1]]

    monkeypatch.setattr(vault, "_normalised", drifted)
    assert vault._span(tool, REPORT_TEXT, TYPED) is None


def test_reading_the_phrase_restores_the_copy_and_leaves_its_own_line(
    client: TestClient, report: int  # noqa: F811
) -> None:
    tool = polaris.load("fuente_clinica")
    before = (tool.bovedas, tool._IDENTIDAD, tool._LOG)
    vault.locate(get_store(), report, TYPED, "crew-01", "Ingeniera de vuelo")
    after = (tool.bovedas, tool._IDENTIDAD, tool._LOG)
    assert all(now is then for now, then in zip(after, before, strict=True))
    log = polaris.configure() / "vault" / "accesos.jsonl"
    last = log.read_text(encoding="utf-8").splitlines()[-1]
    assert "FRASE-localizada" in last and "Ingeniera de vuelo" in last
    assert LITERAL not in last  # el registro de accesos no copia el texto


# --------------------------------------------------------------------------- #
# El recorrido: ver la frase, contrafirmar, y lo que queda en el asiento
# --------------------------------------------------------------------------- #


def test_the_phrase_seen_is_signed_with_its_pointer_and_hash(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    base, second = _high_risk_draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": TYPED}
    seen = client.post(f"{base}/source-quote", json={**cite, "signed_by": second["signed_by"]})
    assert seen.status_code == 200, seen.text
    quote = seen.json()["quote"]
    assert quote["estado"] == "localizada" and quote["frase"] == LITERAL

    body = {**second, **cite, "seen_quote": _seen(quote)}
    assert client.post(f"{base}/countersign", json=body).status_code == 201

    signed = _countersign_entry(measured)["source_quote"]
    assert signed["frase"] == LITERAL and signed["vista"] is True
    assert signed["puntero"] == f"informe:{report}" and signed["asiento"] == report
    assert signed["sha256"] == hashlib.sha256(_stored(report).encode("utf-8")).hexdigest()
    assert _stored(report)[signed["inicio"]:signed["fin"]] == signed["frase"]
    assert get_store().verify_integrity().ok
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert draft["countersign"]["source_quote"]["frase"] == LITERAL
    assert "source_quote" not in draft["signoff"]  # la primera firma no cambia


def test_another_phrase_than_the_one_seen_is_not_signed(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    base, second = _high_risk_draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": TYPED}
    quote = client.post(f"{base}/source-quote", json={**cite, "signed_by": "x"}).json()["quote"]
    other = {**_seen(quote), "frase": "higado de tamano normal"}
    refused = client.post(f"{base}/countersign", json={**second, **cite, "seen_quote": other})
    assert refused.status_code == 409 and "frase" in refused.json()["detail"]
    assert not [e for e in get_store().ledger._view()
                if e.entry_type == DRAFT_COUNTERSIGN_ENTRY_TYPE]


def test_another_report_text_than_the_one_seen_is_not_signed(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    base, second = _high_risk_draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": TYPED}
    quote = client.post(f"{base}/source-quote", json={**cite, "signed_by": "x"}).json()["quote"]
    other = {**_seen(quote), "sha256": "0" * 64}
    refused = client.post(f"{base}/countersign", json={**second, **cite, "seen_quote": other})
    assert refused.status_code == 409 and "informe" in refused.json()["detail"]
    assert not [e for e in get_store().ledger._view()
                if e.entry_type == DRAFT_COUNTERSIGN_ENTRY_TYPE]


def test_a_phrase_of_a_report_redacted_meanwhile_is_not_signed(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    """La frase se lee antes del cerrojo del almacén: si el informe se redacta entre medias, no."""
    from app.api.routes import CONSOLE_IDENTITY, identity_for

    base, second = _high_risk_draft(client, measured)
    store = get_store()
    _, quote = vault.locate(store, report, TYPED, "crew-01", "Ingeniera de vuelo")
    redacted = client.post(f"/api/audit/redact/{report}",
                           json={"reason": "informe de otra persona", "requested_by": "CMO"})
    assert redacted.status_code == 200, redacted.text
    with pytest.raises(ValueError, match="ya no está vigente"):
        store.countersign_draft(
            int(base.rsplit("/", 1)[1]), "accepted", second["signed_by"], "",
            identity_for(CONSOLE_IDENTITY), second["text_sha256"],
            source=f"informe:{report}", source_quote=quote, seen_quote=_seen(quote),
        )
    assert not [e for e in store.ledger._view() if e.entry_type == DRAFT_COUNTERSIGN_ENTRY_TYPE]


def test_a_citation_not_located_is_said_and_is_not_countersigned(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    """Desde el 2026-10-13 (`tests/test_countersign_strict.py`): se ve como tal, y no se firma."""
    base, second = _high_risk_draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": ABSENT}
    quote = client.post(f"{base}/source-quote", json={**cite, "signed_by": "x"}).json()["quote"]
    assert quote["estado"] == "no_localizada" and quote["frase"] == ""
    body = {**second, **cite, "seen_quote": _seen(quote)}
    assert client.post(f"{base}/countersign", json=body).status_code == 422
    assert not [e for e in get_store().ledger._view()
                if e.entry_type == DRAFT_COUNTERSIGN_ENTRY_TYPE]


def test_a_countersign_that_does_not_say_what_it_saw_is_not_written(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    """Hasta el 2026-10-13 se firmaba con `vista: false`; ya no (`test_countersign_strict.py`)."""
    base, second = _high_risk_draft(client, measured)
    body = {**second, "source": f"informe:{report}", "source_fragment": TYPED}
    assert client.post(f"{base}/countersign", json=body).status_code == 422
    assert not [e for e in get_store().ledger._view()
                if e.entry_type == DRAFT_COUNTERSIGN_ENTRY_TYPE]


def test_a_countersign_without_a_report_is_not_written(
    client: TestClient, measured: int
) -> None:
    """Hasta el 2026-10-15 se firmaba con el asiento de siempre; ya no.

    Lo prueba entero `test_countersign_strict.py`; las ya escritas así siguen verificándose
    (`tests/data/countersign_pre_cite.db`).
    """
    base, second = _high_risk_draft(client, measured)
    assert client.post(f"{base}/countersign", json=second).status_code == 422
    assert not [e for e in get_store().ledger._view()
                if e.entry_type == DRAFT_COUNTERSIGN_ENTRY_TYPE]
    assert get_store().verify_integrity().ok


def test_only_a_report_has_a_phrase_to_show(client: TestClient, measured: int) -> None:
    base, _ = _high_risk_draft(client, measured)
    other = client.post(f"{base}/source-quote", json={"source": "PMID 12345678", "signed_by": "x"})
    assert other.status_code == 200 and other.json()["quote"]["estado"] == "no_aplica"
    missing = client.post("/api/imaging/drafts/99999/source-quote",
                          json={"source": "informe:1", "signed_by": "x"})
    assert missing.status_code == 404


def test_the_same_report_quoted_from_several_consoles_at_once_reads_whole(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    """Ocho peticiones a la vez por la ruta: la misma frase y la misma huella en todas.

    La copia de la bóveda se reescribía fuera del cerrojo, y una petición podía leerla a medias:
    «vacía» o `no_localizada` sin que el informe hubiera cambiado.
    """
    from concurrent.futures import ThreadPoolExecutor

    base, second = _high_risk_draft(client, measured)
    body = {"source": f"informe:{report}", "source_fragment": TYPED,
            "signed_by": second["signed_by"]}
    with ThreadPoolExecutor(8) as pool:
        answers = list(pool.map(
            lambda _: client.post(f"{base}/source-quote", json=body), range(16)))
    assert {answer.status_code for answer in answers} == {200}
    quotes = [answer.json()["quote"] for answer in answers]
    assert {(quote["estado"], quote["frase"]) for quote in quotes} == {("localizada", LITERAL)}
    assert {quote["sha256"] for quote in quotes} == {
        hashlib.sha256(_stored(report).encode("utf-8")).hexdigest()}
