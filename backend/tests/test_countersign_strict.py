# SPDX-License-Identifier: AGPL-3.0-or-later
"""La segunda firma, más estricta (decisiones del usuario, 2026-10-13 y 2026-10-15).

Una contrafirma de alto riesgo que cita un informe se rechaza —422 y ningún asiento— si la cita
no se localiza en él o si quien firma no declara la frase que vio (2026-10-13). Y desde el
2026-10-15 tiene que citar un informe: una fuente que no es un informe guardado, o ninguna, no
tiene frase que cotejar y se rechaza igual. Lo que ya estaba firmado con una regla anterior sigue
verificándose y leyéndose, sin tocar. Y la frase se puede ver, y guardar, también en la primera
firma, que no se endurece.

Sin red; OCR y modelo simulados. Usa `fuente_clinica` de la copia literal de Polaris sin
modificarla (`polaris/ADOPTADO.txt`), a través de `app/evidence/vault.py`.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient

from app import countersign_rule, polaris
from app.api.routes import CONSOLE_IDENTITY, get_store, identity_for
from app.core.ledger import Identity
from app.core.storage import (
    DRAFT_COUNTERSIGN_ENTRY_TYPE,
    DRAFT_SIGNOFF_ENTRY_TYPE,
    ObservationStore,
)
from app.evidence import vault
from tests.test_interpret import LLM, clean_run
from tests.test_source_quote import ABSENT, LITERAL, TYPED, _high_risk_draft, _seen
from tests.test_vault import report  # noqa: F401  (fixture)

HIGH_RISK = "Acepto; suspender la medicación y repetir la medida en 24 h"
# Ledger escrito con el código de `main` ANTERIOR a este cambio (commit f5877b8, exportado con
# `git archive main backend/app backend/tests polaris`) y guardado tal cual: un estudio, un
# informe y cuatro borradores con primera firma de alto riesgo y su contrafirma.
PRE_CHANGE_LEDGER = Path(__file__).parent / "data" / "countersign_pre_strict.db"
PRE_CHANGE_STUDY = 0
# Los hashes de contenido de las cuatro contrafirmas, tal como los firmó aquel código.
PRE_CHANGE_COUNTERSIGNS = {
    6: "207f5a8920ecc71ed4c47934b7abccea934168f00659ff124173a62627d51180",   # no localizada
    9: "e1746464f3d7d04952a8aa7445b2de5a4f3e0b117ee67f49440382900abe9f01",   # vista: false
    12: "abe9313303c8ccc4c443d97ec914811485fdc793e41c6a0c1051d6949a013cf8",  # localizada y vista
    15: "7b90842922e9f81b180e731adf4daa0a706f848232181a9ea1edfb776f1e6776",  # fuente: un PMID
}
# Ledger escrito con el código de `main` en 534f276, ANTERIOR a la cita obligatoria (2026-10-15),
# y guardado tal cual: un estudio, un informe y tres borradores con primera firma de alto riesgo y
# su contrafirma: una que cita un PMID (`source_quote` = `no_aplica`), una sin fuente y una
# cotejada (la frase localizada y declarada vista).
PRE_CITE_LEDGER = Path(__file__).parent / "data" / "countersign_pre_cite.db"
PRE_CITE_COUNTERSIGNS = {
    6: "8cf29b37338239d5910f758deeed3c0b922e0665bb54bde35d3bd016335d1811",   # fuente: un PMID
    9: "03f9a641d676e784f6d6fc2dbe301897a318bcf9904f6169f77e85eba6dc78c1",   # sin fuente
    12: "bed67a844667964fcae175aaa6c5ab1987026d5582d163044bde6ac5823c9a27",  # cotejada
}


def _entries(kind: str) -> list[dict[str, Any]]:
    found = [e.payload for e in get_store().ledger._view() if e.entry_type == kind]
    assert all(isinstance(payload, dict) for payload in found)
    return found  # type: ignore[return-value]


def _preview(client: TestClient, base: str, cite: dict[str, str]) -> dict[str, Any]:
    answer = client.post(f"{base}/source-quote", json={**cite, "signed_by": "Ingeniera de vuelo"})
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


def _phrase_reads() -> int:
    """Cuántas veces ha salido una frase de la bóveda, según su registro de accesos."""
    log = polaris.configure() / "vault" / "accesos.jsonl"
    if not log.exists():
        return 0
    return sum("FRASE-" in line for line in log.read_text(encoding="utf-8").splitlines())


# --------------------------------------------------------------------------- #
# Lo que se rechaza: 422 y ningún asiento
# --------------------------------------------------------------------------- #


def test_a_citation_that_is_not_in_the_report_is_refused(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    base, second = _high_risk_draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": ABSENT}
    seen = _preview(client, base, cite)
    assert seen["quote"]["estado"] == "no_localizada"
    # La lectura previa ya lo avisa, con el mismo texto con el que luego se rechaza.
    assert seen["second_signature"]["collatable"] is True
    assert seen["second_signature"]["allowed"] is False

    refused = client.post(
        f"{base}/countersign", json={**second, **cite, "seen_quote": _seen(seen["quote"])})
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail == seen["second_signature"]["reason"]
    assert "no se localiza" in detail and f"informe:{report}" in detail
    assert "ningún asiento" in detail and ABSENT not in detail
    assert _entries(DRAFT_COUNTERSIGN_ENTRY_TYPE) == []
    assert get_store().verify_integrity().ok
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert draft["countersign"] is None and draft["record"]["complete"] is False


def test_a_report_that_does_not_exist_or_is_of_someone_else_is_refused(
    client: TestClient, measured: int, report: int, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """No localizada no es solo «el fragmento no está»: tampoco un informe ausente o ajeno."""
    base, second = _high_risk_draft(client, measured)
    missing = {"source": "informe:99999", "source_fragment": TYPED}
    seen = _preview(client, base, missing)["quote"]
    refused = client.post(f"{base}/countersign", json={**second, **missing,
                                                       "seen_quote": _seen(seen)})
    assert refused.status_code == 422 and "informe:99999" in refused.json()["detail"]

    store = get_store()
    monkeypatch.setattr(type(store), "draft_subject", lambda self, index: "crew-02")
    other = {"source": f"informe:{report}", "source_fragment": TYPED}
    seen = _preview(client, base, other)["quote"]
    assert seen["estado"] == "no_localizada"
    refused = client.post(f"{base}/countersign", json={**second, **other,
                                                       "seen_quote": _seen(seen)})
    assert refused.status_code == 422
    assert _entries(DRAFT_COUNTERSIGN_ENTRY_TYPE) == []


def test_a_located_phrase_nobody_declares_having_seen_is_refused(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    base, second = _high_risk_draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": TYPED}
    refused = client.post(f"{base}/countersign", json={**second, **cite})
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert "no declara haber visto la frase" in detail and "ningún asiento" in detail
    assert LITERAL not in detail  # el rechazo no enseña la frase que no se pidió ver
    assert _entries(DRAFT_COUNTERSIGN_ENTRY_TYPE) == []
    assert get_store().verify_integrity().ok


def test_after_a_refusal_the_same_person_can_look_and_countersign(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    """Un rechazo no deja nada a medias: se ve la frase, se declara y entonces sí."""
    base, second = _high_risk_draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": TYPED}
    assert client.post(f"{base}/countersign", json={**second, **cite}).status_code == 422
    seen = _preview(client, base, cite)
    assert seen["second_signature"] == {"collatable": True, "allowed": True, "reason": None}
    body = {**second, **cite, "seen_quote": _seen(seen["quote"])}
    signed = client.post(f"{base}/countersign", json=body)
    assert signed.status_code == 201
    assert signed.json()["collation"]["collated"] is True
    assert signed.json()["collation"]["label"] == countersign_rule.COLLATED
    [entry] = _entries(DRAFT_COUNTERSIGN_ENTRY_TYPE)
    assert entry["source_quote"]["frase"] == LITERAL and entry["source_quote"]["vista"] is True
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert draft["record"]["complete"] is True and draft["countersign_note"] is None
    assert draft["countersign_collation"] == signed.json()["collation"]
    assert get_store().verify_integrity().ok


def test_the_409_of_a_vault_that_no_longer_gives_what_was_seen_is_kept(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    """Se vio una frase y el informe se redactó: no es «no localizada» (422), es otra cosa (409)."""
    base, second = _high_risk_draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": TYPED}
    seen = _preview(client, base, cite)["quote"]
    assert seen["estado"] == "localizada"
    redacted = client.post(f"/api/audit/redact/{report}",
                           json={"reason": "informe de otra persona", "requested_by": "CMO"})
    assert redacted.status_code == 200, redacted.text
    refused = client.post(f"{base}/countersign", json={**second, **cite,
                                                       "seen_quote": _seen(seen)})
    assert refused.status_code == 409 and "vuelve a ver" in refused.json()["detail"]
    assert _entries(DRAFT_COUNTERSIGN_ENTRY_TYPE) == []


def test_the_store_itself_refuses_whoever_calls_it(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    """La regla no vive solo en la ruta: es el almacén quien no escribe."""
    base, second = _high_risk_draft(client, measured)
    store, index = get_store(), int(base.rsplit("/", 1)[1])
    _, located = vault.locate(store, report, TYPED, "crew-01", "Ingeniera de vuelo")
    _, absent = vault.locate(store, report, ABSENT, "crew-01", "Ingeniera de vuelo")
    not_a_report = {"estado": "no_aplica", "frase": "",
                    "detalle": countersign_rule.NOT_COLLATABLE_DETAIL}
    cases: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]] = [
        (f"informe:{report}", located, None), (f"informe:{report}", absent, _seen(absent)),
        (f"informe:{report}", absent, None),
        # Desde el 2026-10-15: otra fuente, o ninguna, tampoco; con o sin algo «visto».
        ("PMID 12345678", not_a_report, None), ("PMID 12345678", not_a_report, _seen(located)),
        ("", None, None), ("", None, _seen(located)),
    ]
    for source, quote, seen in cases:
        with pytest.raises(countersign_rule.CountersignRefused):
            store.countersign_draft(
                index, "accepted", second["signed_by"], "", identity_for(CONSOLE_IDENTITY),
                second["text_sha256"], source=source, source_quote=quote, seen_quote=seen,
            )
    assert _entries(DRAFT_COUNTERSIGN_ENTRY_TYPE) == []


# --------------------------------------------------------------------------- #
# Desde el 2026-10-15: lo que no se puede cotejar también se rechaza
# --------------------------------------------------------------------------- #


def test_a_source_that_is_not_a_report_is_refused(client: TestClient, measured: int) -> None:
    """Una decisión de alto riesgo no se contrafirma citando un PMID: no hay frase que leer."""
    base, second = _high_risk_draft(client, measured)
    cite = {"source": "PMID 12345678", "source_fragment": ""}
    seen = _preview(client, base, cite)
    assert seen["quote"]["estado"] == "no_aplica"
    # La lectura previa ya lo avisa, con el mismo texto con el que luego se rechaza.
    assert seen["second_signature"]["collatable"] is False
    assert seen["second_signature"]["allowed"] is False
    refused = client.post(f"{base}/countersign", json={**second, **cite})
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail == seen["second_signature"]["reason"]
    assert "no es un informe guardado" in detail and countersign_rule.MUST_CITE in detail
    assert "ningún asiento" in detail and "12345678" not in detail
    assert _entries(DRAFT_COUNTERSIGN_ENTRY_TYPE) == []
    assert get_store().verify_integrity().ok
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert draft["countersign"] is None and draft["record"]["complete"] is False
    assert draft["second_signature_rule"]["must_cite"] == countersign_rule.MUST_CITE


def test_a_countersign_that_cites_nothing_is_refused(client: TestClient, measured: int) -> None:
    base, second = _high_risk_draft(client, measured)
    refused = client.post(f"{base}/countersign", json=second)
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert "no cita ninguna fuente" in detail and countersign_rule.MUST_CITE in detail
    assert "ningún asiento" in detail
    # La lectura previa sin fuente dice lo mismo: que no cita nada, no que cite otra cosa.
    gate = _preview(client, base, {"source": "  ", "source_fragment": ""})["second_signature"]
    assert gate == {"collatable": False, "allowed": False, "reason": detail}
    assert _entries(DRAFT_COUNTERSIGN_ENTRY_TYPE) == []
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert draft["countersign"] is None and draft["record"]["complete"] is False


def test_refusing_a_source_that_is_not_a_report_does_not_go_out_to_its_registry(
    client: TestClient, measured: int, tmp_path: Path
) -> None:
    """Con red, una firma consulta el PMID en su registro; para rechazarla no hace falta."""
    from app.core.config import Settings, get_settings
    from app.main import app

    base, second = _high_risk_draft(client, measured)
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=False)
    with respx.mock(assert_all_called=False) as network:
        anywhere = network.route().respond(404)
        refused = client.post(f"{base}/countersign", json={**second, "source": "PMID 12345678"})
    assert refused.status_code == 422, refused.text
    assert anywhere.call_count == 0
    assert _entries(DRAFT_COUNTERSIGN_ENTRY_TYPE) == []


def test_the_checks_of_always_still_answer_409_before_the_422(
    client: TestClient, measured: int
) -> None:
    """La misma persona no es segunda voz, cite lo que cite: eso se dice antes que la regla."""
    base, second = _high_risk_draft(client, measured)
    same = {**second, "signed_by": "CMO", "source": "PMID 12345678"}
    assert client.post(f"{base}/countersign", json=same).status_code == 409
    assert client.post(f"{base}/countersign", json={**same, "source": ""}).status_code == 409
    assert _entries(DRAFT_COUNTERSIGN_ENTRY_TYPE) == []


# --------------------------------------------------------------------------- #
# Lo ya firmado no cambia
# --------------------------------------------------------------------------- #


def _old_ledger(tmp_path: Path, written: Path = PRE_CHANGE_LEDGER) -> ObservationStore:
    path = tmp_path / "ledger.db"
    shutil.copyfile(written, path)
    return ObservationStore.at(path)


def test_countersignatures_signed_under_the_previous_rule_still_verify_and_read(
    tmp_path: Path,
) -> None:
    store = _old_ledger(tmp_path)
    assert store.verify_integrity().ok
    trail = {entry["index"]: entry for entry in store.audit_trail()}
    assert {index: trail[index]["content_hash"] for index in PRE_CHANGE_COUNTERSIGNS} == (
        PRE_CHANGE_COUNTERSIGNS)
    assert all(trail[index]["entry_type"] == DRAFT_COUNTERSIGN_ENTRY_TYPE
               for index in PRE_CHANGE_COUNTERSIGNS)

    absent, unseen, seen, pmid = store.drafts(PRE_CHANGE_STUDY)
    # Se leen enteras, con lo que se firmó entonces: nada se ha marcado ni reescrito.
    assert absent["countersign"]["source_quote"]["estado"] == "no_localizada"
    assert absent["countersign"]["source_quote"]["vista"] is True
    assert unseen["countersign"]["source_quote"]["frase"] == LITERAL
    assert unseen["countersign"]["source_quote"]["vista"] is False
    assert seen["countersign"]["source_quote"]["vista"] is True
    assert "source_quote" not in pmid["countersign"]  # entonces no se decía «no cotejable»
    assert all(draft["record"]["complete"] for draft in (absent, unseen, seen, pmid))

    # El rótulo se deriva al leer, de lo que el asiento dice.
    notes = [countersign_rule.prior_rule_note(draft["countersign"])
             for draft in (absent, unseen, seen, pmid)]
    assert notes[2] is None
    assert notes[0] is not None and "con la cita no localizada" in notes[0]
    assert notes[1] is not None and "sin declarar haber visto la frase" in notes[1]
    for note in notes[:2]:
        assert note is not None
        assert countersign_rule.RULE_DATE in note and "regla anterior" in note
        assert "no se ha modificado" in note
    # La que citaba un PMID la admitía también la regla del 2026-10-13; la de hoy, no. Entonces
    # el asiento no guardaba nada de su fuente, y el rótulo dice eso, no qué fuente era.
    assert notes[3] is not None and countersign_rule.CITE_RULE_DATE in notes[3]
    assert "sin guardar en el asiento una frase cotejada" in notes[3]
    assert "regla anterior" in notes[3] and "no se ha modificado" in notes[3]

    # Leer no escribió nada.
    assert store.verify_integrity().ok
    after = {entry["index"]: entry["content_hash"] for entry in store.audit_trail()}
    assert after == {index: entry["content_hash"] for index, entry in trail.items()}


def test_the_new_rule_applies_on_top_of_an_old_chain_without_touching_it(
    tmp_path: Path,
) -> None:
    """Sobre esa misma cadena: un borrador nuevo se contrafirma ya con la regla nueva."""
    store = _old_ledger(tmp_path)
    before = [entry["content_hash"] for entry in store.audit_trail()]
    old = store.drafts(PRE_CHANGE_STUDY)
    located = dict(old[2]["countersign"]["source_quote"])
    located.pop("vista")
    absent = dict(old[0]["countersign"]["source_quote"])
    absent.pop("vista")

    console = Identity.generate("otra-consola")
    draft = store.record_draft(
        {"study_index": PRE_CHANGE_STUDY, "status": "unvalidated", "text": "texto"},
        Identity.generate("otro-modelo"),
    )
    sha = [d for d in store.drafts(PRE_CHANGE_STUDY)
           if d["ledger_index"] == draft.index][0]["text_sha256"]
    store.sign_draft(draft.index, "accepted", "CMO", HIGH_RISK, console, sha)
    source = old[2]["countersign"]["source"]
    for quote, seen in ((absent, _seen(absent)), (located, None)):
        with pytest.raises(countersign_rule.CountersignRefused):
            store.countersign_draft(draft.index, "accepted", "Ingeniera", "", console, sha,
                                    source=source, source_quote=quote, seen_quote=seen)
    entry = store.countersign_draft(draft.index, "accepted", "Ingeniera", "", console, sha,
                                    source=source, source_quote=located,
                                    seen_quote=_seen(located))
    assert isinstance(entry.payload, dict) and entry.payload["source_quote"]["vista"] is True
    assert store.verify_integrity().ok
    assert [e["content_hash"] for e in store.audit_trail()][:len(before)] == before


def test_the_list_of_drafts_labels_old_countersignatures_without_touching_them(
    client: TestClient, tmp_path: Path
) -> None:
    from app.api import routes

    routes.reset_store(_old_ledger(tmp_path))
    drafts = client.get(f"/api/imaging/studies/{PRE_CHANGE_STUDY}/drafts").json()
    notes = [draft["countersign_note"] for draft in drafts]
    assert notes[0] == countersign_rule.prior_rule_note(drafts[0]["countersign"]) != None  # noqa: E711
    assert "no localizada" in notes[0] and "sin declarar" in notes[1]
    assert notes[2] is None
    assert notes[3] == countersign_rule.prior_rule_note(drafts[3]["countersign"]) != None  # noqa: E711
    assert "countersign_note" not in drafts[0]["countersign"]  # al lado, no dentro del asiento
    # Y si se cotejó, también derivado al leer: solo la localizada y declarada vista lo está.
    collations = [draft["countersign_collation"] for draft in drafts]
    assert [c["collated"] for c in collations] == [False, False, True, False]
    assert collations[0]["why"].startswith("la cita no se localizó en")
    assert collations[1]["why"] == countersign_rule.NOT_DECLARED_DETAIL
    assert collations[2]["why"] is None
    # Entonces una fuente que no era un informe no dejaba nada en el asiento.
    assert collations[3]["why"] == countersign_rule.NO_QUOTE_STORED_DETAIL
    assert all(draft["second_signature_rule"] == countersign_rule.describe() for draft in drafts)
    assert routes.get_store().verify_integrity().ok


def test_countersignatures_admitted_before_the_citation_rule_still_verify_and_read(
    tmp_path: Path,
) -> None:
    """Las que la regla del 2026-10-13 admitía sin informe: siguen ahí, y se rotulan al leer."""
    store = _old_ledger(tmp_path, PRE_CITE_LEDGER)
    assert store.verify_integrity().ok
    trail = {entry["index"]: entry for entry in store.audit_trail()}
    assert {index: trail[index]["content_hash"] for index in PRE_CITE_COUNTERSIGNS} == (
        PRE_CITE_COUNTERSIGNS)
    assert all(trail[index]["entry_type"] == DRAFT_COUNTERSIGN_ENTRY_TYPE
               for index in PRE_CITE_COUNTERSIGNS)

    pmid, nothing, collated = store.drafts(PRE_CHANGE_STUDY)
    # Se leen enteras, con lo que se firmó entonces.
    assert pmid["countersign"]["source"] == "PMID 12345678"
    assert pmid["countersign"]["source_quote"] == {
        "estado": "no_aplica", "frase": "", "detalle": countersign_rule.NOT_COLLATABLE_DETAIL}
    assert set(nothing["countersign"]) == {
        "draft_index", "decision", "signed_by", "comment", "text_sha256", "recorded"}
    assert collated["countersign"]["source_quote"]["vista"] is True
    assert all(draft["record"]["complete"] for draft in (pmid, nothing, collated))

    notes = [countersign_rule.prior_rule_note(draft["countersign"])
             for draft in (pmid, nothing, collated)]
    assert notes[2] is None  # la regla de hoy también la admite
    assert notes[0] is not None and "citando una fuente que no es un informe guardado" in notes[0]
    assert notes[1] is not None and "sin citar ninguna fuente" in notes[1]
    for note in notes[:2]:
        assert note is not None
        assert countersign_rule.CITE_RULE_DATE in note and countersign_rule.RULE_DATE not in note
        assert "regla anterior" in note and "no se ha modificado" in note
    # Y se siguen diciendo «no cotejada», con el motivo de su asiento.
    collations = [countersign_rule.collation(draft["countersign"])
                  for draft in (pmid, nothing, collated)]
    assert [(c or {}).get("why") for c in collations] == [
        countersign_rule.NOT_COLLATABLE_DETAIL, countersign_rule.NO_SOURCE_DETAIL, None]

    # Leer no escribió nada.
    assert store.verify_integrity().ok
    after = {entry["index"]: entry["content_hash"] for entry in store.audit_trail()}
    assert after == {index: entry["content_hash"] for index, entry in trail.items()}


def test_the_citation_rule_applies_on_top_of_a_chain_that_admitted_otherwise(
    client: TestClient, tmp_path: Path
) -> None:
    """Sobre la cadena que admitió un PMID y una sin fuente: hoy esas dos se rechazan."""
    from app.api import routes

    store = _old_ledger(tmp_path, PRE_CITE_LEDGER)
    before = [entry["content_hash"] for entry in store.audit_trail()]
    pmid, nothing, collated = store.drafts(PRE_CHANGE_STUDY)
    located = dict(collated["countersign"]["source_quote"])
    located.pop("vista")

    console = Identity.generate("otra-consola")
    draft = store.record_draft(
        {"study_index": PRE_CHANGE_STUDY, "status": "unvalidated", "text": "texto"},
        Identity.generate("otro-modelo"),
    )
    sha = [d for d in store.drafts(PRE_CHANGE_STUDY)
           if d["ledger_index"] == draft.index][0]["text_sha256"]
    store.sign_draft(draft.index, "accepted", "CMO", HIGH_RISK, console, sha)
    for source, quote in ((pmid["countersign"]["source"], pmid["countersign"]["source_quote"]),
                          ("", None)):
        with pytest.raises(countersign_rule.CountersignRefused):
            store.countersign_draft(draft.index, "accepted", "Ingeniera", "", console, sha,
                                    source=source, source_quote=quote)

    # La lista lo dice al lado de cada asiento, y sin tocarlos.
    routes.reset_store(store)
    listed = client.get(f"/api/imaging/studies/{PRE_CHANGE_STUDY}/drafts").json()
    assert [item["countersign_note"] is not None for item in listed] == [True, True, False, False]
    assert listed[3]["countersign"] is None and listed[3]["record"]["complete"] is False

    entry = store.countersign_draft(draft.index, "accepted", "Ingeniera", "", console, sha,
                                    source=collated["countersign"]["source"],
                                    source_quote=located, seen_quote=_seen(located))
    assert isinstance(entry.payload, dict) and entry.payload["source_quote"]["vista"] is True
    assert store.verify_integrity().ok
    assert [e["content_hash"] for e in store.audit_trail()][:len(before)] == before


# --------------------------------------------------------------------------- #
# La frase, también en la primera firma: opcional, y sin endurecerla
# --------------------------------------------------------------------------- #


def _draft(client: TestClient, measured: int) -> tuple[str, dict[str, Any]]:
    with respx.mock:
        respx.post(f"{LLM}/api/chat").mock(side_effect=clean_run())
        client.post(f"/api/imaging/studies/{measured}/draft")
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    body = {"decision": "accepted", "signed_by": "CMO", "comment": "concuerda",
            "text_sha256": draft["text_sha256"]}
    return f"/api/imaging/drafts/{draft['ledger_index']}", body


def test_the_first_signature_can_see_the_phrase_and_keep_it(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    base, first = _draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": TYPED}
    quote = _preview(client, base, cite)["quote"]
    assert quote["frase"] == LITERAL
    signed = client.post(f"{base}/sign", json={**first, **cite, "seen_quote": _seen(quote)})
    assert signed.status_code == 201, signed.text
    [entry] = _entries(DRAFT_SIGNOFF_ENTRY_TYPE)
    assert entry["source_check"]["estado"] == "confirmada"
    kept = entry["source_quote"]
    assert kept["frase"] == LITERAL and kept["vista"] is True
    assert kept["puntero"] == f"informe:{report}" and kept["asiento"] == report
    assert set(kept) == {"estado", "frase", "puntero", "informe", "asiento", "inicio", "fin",
                         "sha256", "desidentificado", "detalle", "vista"}
    assert get_store().verify_integrity().ok
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    assert draft["signoff"]["source_quote"]["frase"] == LITERAL


def test_the_first_signature_without_looking_is_the_entry_it_always_was(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    """Sin `seen_quote` la bóveda no entrega texto: ni frase en el asiento, ni línea de lectura."""
    base, first = _draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": TYPED}
    reads = _phrase_reads()
    assert client.post(f"{base}/sign", json={**first, **cite}).status_code == 201
    assert _phrase_reads() == reads
    [entry] = _entries(DRAFT_SIGNOFF_ENTRY_TYPE)
    assert set(entry) - {"_salt"} == {
        "draft_index", "decision", "signed_by", "comment", "text_sha256", "high_risk",
        "source", "source_check",
    }
    assert entry["source_check"]["estado"] == "confirmada"


def test_the_first_signature_is_not_blocked_by_a_citation_not_located(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    """La decisión del usuario solo endurece la segunda firma."""
    base, first = _draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": ABSENT}
    quote = _preview(client, base, cite)["quote"]
    signed = client.post(f"{base}/sign", json={**first, **cite, "seen_quote": _seen(quote)})
    assert signed.status_code == 201, signed.text
    [entry] = _entries(DRAFT_SIGNOFF_ENTRY_TYPE)
    assert entry["source_quote"]["estado"] == "no_localizada"
    assert entry["source_quote"]["frase"] == "" and entry["source_quote"]["vista"] is True


def test_the_first_signature_does_not_sign_another_phrase_than_the_one_seen(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    base, first = _draft(client, measured)
    cite = {"source": f"informe:{report}", "source_fragment": TYPED}
    quote = _preview(client, base, cite)["quote"]
    other = {**_seen(quote), "frase": "higado de tamano normal"}
    refused = client.post(f"{base}/sign", json={**first, **cite, "seen_quote": other})
    assert refused.status_code == 409 and "frase" in refused.json()["detail"]
    assert _entries(DRAFT_SIGNOFF_ENTRY_TYPE) == []


def test_a_first_signature_seen_quote_without_a_report_changes_nothing(
    client: TestClient, measured: int
) -> None:
    base, first = _draft(client, measured)
    seen = {"estado": "localizada", "frase": "algo", "sha256": "0" * 64}
    body = {**first, "source": "PMID 12345678", "seen_quote": seen}
    assert client.post(f"{base}/sign", json=body).status_code == 201
    [entry] = _entries(DRAFT_SIGNOFF_ENTRY_TYPE)
    assert "source_quote" not in entry


def test_in_the_store_the_first_signature_says_whether_the_phrase_was_declared_seen(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    """`vista` es de quien firma, no un adorno: sin `seen_quote`, el almacén deja `False`."""
    base, first = _draft(client, measured)
    store, index = get_store(), int(base.rsplit("/", 1)[1])
    _, quote = vault.locate(store, report, TYPED, "crew-01", "CMO")
    store.sign_draft(index, "accepted", "CMO", "", identity_for(CONSOLE_IDENTITY),
                     first["text_sha256"], source=f"informe:{report}", source_quote=quote)
    [entry] = _entries(DRAFT_SIGNOFF_ENTRY_TYPE)
    assert entry["source_quote"]["frase"] == LITERAL and entry["source_quote"]["vista"] is False


def test_the_first_signature_does_not_sign_a_phrase_of_a_report_redacted_meanwhile(
    client: TestClient, measured: int, report: int  # noqa: F811
) -> None:
    base, first = _draft(client, measured)
    store, index = get_store(), int(base.rsplit("/", 1)[1])
    _, quote = vault.locate(store, report, TYPED, "crew-01", "CMO")
    redacted = client.post(f"/api/audit/redact/{report}",
                           json={"reason": "informe de otra persona", "requested_by": "CMO"})
    assert redacted.status_code == 200, redacted.text
    with pytest.raises(ValueError, match="ya no está vigente"):
        store.sign_draft(index, "accepted", "CMO", "", identity_for(CONSOLE_IDENTITY),
                         first["text_sha256"], source=f"informe:{report}",
                         source_quote=quote, seen_quote=_seen(quote))
    assert _entries(DRAFT_SIGNOFF_ENTRY_TYPE) == []


# --------------------------------------------------------------------------- #
# La regla: sus textos y lo que no es
# --------------------------------------------------------------------------- #


def test_the_rule_texts_inform_and_do_not_order() -> None:
    """Invariante 7: el rechazo dice qué falta; no es una orden clínica."""
    texts = [*(str(value) for value in countersign_rule.describe().values()),
             countersign_rule.refusal({"estado": "no_localizada", "puntero": "informe:3"}, {}),
             countersign_rule.refusal({"estado": "localizada", "puntero": "informe:3"}, None),
             countersign_rule.refusal(None, None),
             countersign_rule.refusal({"estado": "no_aplica"}, {}),
             *(countersign_rule.prior_rule_note(signed) for signed in (
                 {"source": ""}, {"source": "PMID 1"},
                 {"source_quote": {"estado": "no_aplica"}},
                 {"source_quote": {"estado": "no_localizada"}},
                 {"source_quote": {"estado": "localizada", "vista": False}})),
             *(str((countersign_rule.collation(signed) or {})["text"]) for signed in (
                 {"source": ""}, {"source": "PMID 1"},
                 {"source_quote": {"estado": "no_aplica"}},
                 {"source_quote": {"estado": "no_localizada", "puntero": "informe:3"}},
                 {"source_quote": {"estado": "localizada", "vista": False}},
                 {"source_quote": {"estado": "localizada", "vista": True}}))]
    assert all(texts)
    for text in texts:
        lowered = str(text).lower()
        assert not any(word in lowered for word in (
            "debe administr", "administre", "suspenda", "trate ", "diagnóstico"))
    assert countersign_rule.refusal({"estado": "localizada"}, {"estado": "localizada"}) is None
    assert countersign_rule.collation(None) is None and countersign_rule.collation({}) is None
    assert countersign_rule.prior_rule_note(None) is None
    assert countersign_rule.prior_rule_note(
        {"source_quote": {"estado": "localizada", "vista": True}}) is None


# --------------------------------------------------------------------------- #
# Invariantes 5 y 6: nada de esto mueve el motor
# --------------------------------------------------------------------------- #


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    return {key: status[key] for key in ("overall_level", "domains", "alerts")}


def test_the_engine_verdict_is_the_same_with_and_without_these_signatures(
    client: TestClient, request: pytest.FixtureRequest
) -> None:
    """Firmas, frases, rechazos y contrafirmas: `/api/status` da los mismos niveles y alertas."""
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 40}
    ).status_code == 201
    measured = int(request.getfixturevalue("measured"))
    scanned = int(request.getfixturevalue("report"))
    reference = client.get("/api/status").json()
    assert reference["alerts"] and reference["overall_level"] != "nominal"
    params = {"until": reference["data"]["reference_time"]}
    before = client.get("/api/status", params=params).json()

    # Una primera firma de alto riesgo con su frase, cuatro rechazos y la contrafirma.
    base, first = _draft(client, measured)
    cite = {"source": f"informe:{scanned}", "source_fragment": TYPED}
    quote = _preview(client, base, cite)["quote"]
    body = {**first, "comment": HIGH_RISK, **cite, "seen_quote": _seen(quote)}
    assert client.post(f"{base}/sign", json=body).status_code == 201
    second = {**first, "signed_by": "Ingeniera de vuelo", "comment": ""}
    assert client.post(f"{base}/countersign", json=second).status_code == 422
    assert client.post(f"{base}/countersign",
                       json={**second, "source": "PMID 12345678"}).status_code == 422
    assert client.post(f"{base}/countersign", json={**second, **cite}).status_code == 422
    absent = {"source": f"informe:{scanned}", "source_fragment": ABSENT}
    seen_absent = _seen(_preview(client, base, absent)["quote"])
    assert client.post(f"{base}/countersign",
                       json={**second, **absent, "seen_quote": seen_absent}).status_code == 422
    assert client.post(f"{base}/countersign",
                       json={**second, **cite, "seen_quote": _seen(quote)}).status_code == 201
    assert len(_entries(DRAFT_COUNTERSIGN_ENTRY_TYPE)) == 1

    after = client.get("/api/status", params=params).json()
    assert _verdict(after) == _verdict(before)
    assert after["recommendations"] == before["recommendations"]
