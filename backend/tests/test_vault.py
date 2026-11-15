"""Una firma que cita un informe escaneado: el fragmento citado tiene que estar dentro de él
(`fuente_clinica.cotejar` de Polaris sobre la bóveda de EMMA). Sin red; OCR y modelo simulados.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient

from app.evidence import vault
from app.reports import ocr
from tests.test_interpret import LLM, clean_run
from tests.test_reports import png, upload

REPORT_TEXT = (
    "Ecografía abdominal: hígado de tamaño normal, sin lesiones focales. Vesícula alitiásica."
)


@pytest.fixture
def report(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> int:
    fake = tmp_path / "tesseract.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(ocr, "find_tesseract", lambda configured=None: str(fake))
    monkeypatch.setattr(ocr, "version", lambda executable: "tesseract 5.5.0")
    monkeypatch.setattr(ocr, "ocr_image", lambda executable, image: (REPORT_TEXT, 95.0, 12))
    index = upload(client, png())["ledger_index"]
    assert isinstance(index, int)
    return index


def _sign(client: TestClient, measured: int, source: str, fragment: str) -> dict:  # type: ignore[type-arg]
    with respx.mock:
        respx.post(f"{LLM}/api/chat").mock(side_effect=clean_run())
        client.post(f"/api/imaging/studies/{measured}/draft")
    [draft] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    body = {
        "decision": "accepted", "signed_by": "CMO", "comment": "concuerda",
        "text_sha256": draft["text_sha256"], "source": source, "source_fragment": fragment,
    }
    response = client.post(f"/api/imaging/drafts/{draft['ledger_index']}/sign", json=body)
    assert response.status_code == 201, response.text  # nunca bloquea la firma
    [signed] = client.get(f"/api/imaging/studies/{measured}/drafts").json()
    check: dict = signed["signoff"]["source_check"]  # type: ignore[type-arg]
    return check


def test_a_quoted_fragment_found_in_the_report_is_confirmed(
    client: TestClient, measured: int, report: int
) -> None:
    check = _sign(client, measured, f"informe:{report}", "higado de tamano normal, sin lesiones")
    assert check["estado"] == "confirmada" and check["sha256"]
    assert check["identidad"] == "no_consta"  # sin identidad declarada: servible


def test_a_fragment_that_is_not_in_the_report_is_flagged(
    client: TestClient, measured: int, report: int
) -> None:
    absent = "lesion hipoecoica de 2 cm en el segmento VI"
    check = _sign(client, measured, f"informe:{report}", absent)
    assert check["estado"] == "fragmento_ausente"
    assert f"informe:{report}" in check["detalle"]


def test_a_report_that_does_not_exist_is_not_sealed(client: TestClient, measured: int) -> None:
    assert _sign(client, measured, "informe:99999", "cualquier fragmento largo")["estado"] == (
        "no_existe")


def test_a_report_of_another_crew_member_does_not_count(
    client: TestClient, measured: int, report: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import routes

    store = routes.get_store()
    monkeypatch.setattr(type(store), "draft_subject", lambda self, index: "crew-02")
    check = _sign(client, measured, f"informe:{report}", "higado de tamano normal, sin lesiones")
    assert check["estado"] == "identidad_ajena"


def test_a_short_fragment_matches_anything_and_is_refused(
    client: TestClient, measured: int, report: int
) -> None:
    assert _sign(client, measured, f"informe:{report}", "higado")["estado"] == "fragmento_corto"


def test_the_copy_is_restored_and_each_check_is_logged(
    client: TestClient, measured: int, report: int
) -> None:
    from app import polaris

    tool = polaris.load("fuente_clinica")
    before = (tool.bovedas, tool._IDENTIDAD, tool._LOG)
    _sign(client, measured, f"informe:{report}", "higado de tamano normal, sin lesiones")
    after = (tool.bovedas, tool._IDENTIDAD, tool._LOG)
    assert all(now is then for now, then in zip(after, before, strict=True))
    log = polaris.configure() / "vault" / "accesos.jsonl"
    assert "confirmada" in log.read_text(encoding="utf-8").splitlines()[-1]


class _TwoPages:
    """Un almacén con un informe de dos páginas y saltos de línea dentro de una."""

    PAGES = ("Ecografía abdominal.\nHígado de tamaño normal, sin lesiones focales.",
             "Vesícula alitiásica.")

    def report_blob(self, index: int) -> tuple[dict[str, object], None]:
        pages = [{"text": text} for text in self.PAGES]
        return {"subject": "crew-01", "ocr": {"pages": pages}}, None


def test_the_source_hash_is_the_one_of_the_report_text_on_any_machine() -> None:
    """La huella que queda en la firma es la del texto del informe, no la de sus saltos de línea.

    En Windows el fichero de la bóveda se escribía con CRLF y la huella salía distinta que en
    Linux para el mismo informe (el rojo de `test_fuente_clinica` de Polaris en esta máquina).
    """
    import hashlib

    from app.evidence.vault import _vault

    result = vault.check(_TwoPages(), 424242, "higado de tamano normal, sin lesiones", "crew-01",
                         "CMO")
    text = "\n\n".join(_TwoPages.PAGES)
    assert result["estado"] == "confirmada"
    assert result["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert b"\r" not in (_vault() / "informe-424242.md").read_bytes()
    (_vault() / "informe-424242.md").unlink()


def test_only_report_references_go_to_the_vault() -> None:
    assert vault.report_index("informe:12") == 12
    assert vault.report_index("PMID 12345678") is None


def test_a_redacted_report_leaves_the_vault(client: TestClient, report: int) -> None:
    from app.api import routes
    from app.evidence.vault import _vault

    store = routes.get_store()
    fragment = "higado de tamano normal, sin lesiones"
    assert vault.check(store, report, fragment, "crew-01", "CMO")["estado"] == "confirmada"
    assert (_vault() / f"informe-{report}.md").is_file()
    redacted = client.post(f"/api/audit/redact/{report}",
                           json={"reason": "informe de otra persona", "requested_by": "CMO"})
    assert redacted.status_code == 200, redacted.text
    assert vault.check(store, report, fragment, "crew-01", "CMO")["estado"] == "no_existe"
    assert not (_vault() / f"informe-{report}.md").exists()


# --------------------------------------------------------------------------- #
# Dos cotejos a la vez: la copia de la bóveda se pone y se lee bajo el mismo cerrojo
# --------------------------------------------------------------------------- #

FRAGMENT = "higado de tamano normal, sin lesiones"


class _OnePage:
    """Un almacén con un informe de una página, del tamaño que se le pida."""

    def __init__(self, filler: int = 0) -> None:
        self.text = REPORT_TEXT + " Sin otros hallazgos." * filler
        self.locked: list[bool] = []

    def report_blob(self, index: int) -> tuple[dict[str, object], None]:
        self.locked.append(vault._LOCK.locked())
        return {"subject": "crew-01", "ocr": {"pages": [{"text": self.text}]}}, None


class _Redacted:
    def report_blob(self, index: int) -> tuple[dict[str, object], None]:
        raise KeyError(index)


def _stamp(path: Path) -> tuple[int, int, int] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def test_nobody_touches_the_copy_while_another_check_is_reading_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mientras un cotejo lee el informe, otro del mismo espera: ni lo reescribe ni lo borra.

    Antes la copia se escribía (o se borraba) antes de tomar el cerrojo: el segundo cotejo la
    truncaba con el primero a media lectura.
    """
    import threading
    import time

    index = 424243
    target = vault._vault() / f"informe-{index}.md"
    tool = vault._tool()
    real = tool.cotejar
    reading, started = threading.Event(), threading.Event()
    seen: dict[str, object] = {}

    def slow(*args: object, **kwargs: object) -> object:
        if not reading.is_set():
            seen["before"] = _stamp(target)
            reading.set()
            started.wait(5)
            time.sleep(0.3)  # a los otros cotejos les sobra tiempo para pisar la copia
            seen["after"] = _stamp(target)
        return real(*args, **kwargs)

    monkeypatch.setattr(tool, "cotejar", slow)
    results: dict[str, str] = {}

    def run(name: str, store: object) -> None:
        results[name] = vault.check(store, index, FRAGMENT, "crew-01", "CMO")["estado"]

    # Además del primero: uno que reescribe la copia y uno que la borra (informe ya redactado).
    threads = [threading.Thread(target=run, args=(name, store)) for name, store in (
        ("first", _OnePage()), ("again", _OnePage()), ("redacted", _Redacted()))]
    try:
        threads[0].start()
        assert reading.wait(5)
        threads[1].start()
        threads[2].start()
        started.set()
        for thread in threads:
            thread.join(10)
    finally:
        target.unlink(missing_ok=True)
    assert seen["before"] is not None and seen["after"] == seen["before"]
    assert results == {"first": "confirmada", "again": "confirmada", "redacted": "no_existe"}


def test_many_checks_of_one_report_at_once_all_see_the_whole_report() -> None:
    """Ocho hilos cotejando el mismo informe: todos confirman, con la misma huella, la del texto."""
    import hashlib
    from concurrent.futures import ThreadPoolExecutor

    index = 424244
    store = _OnePage(filler=20000)
    try:
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(
                lambda _: vault.check(store, index, FRAGMENT, "crew-01", "CMO"), range(24)))
    finally:
        (vault._vault() / f"informe-{index}.md").unlink(missing_ok=True)
    assert {result["estado"] for result in results} == {"confirmada"}
    assert {result["sha256"] for result in results} == {
        hashlib.sha256(store.text.encode("utf-8")).hexdigest()}
    assert all(store.locked)  # el asiento se lee ya con el cerrojo: copia y lectura, un solo paso


def test_the_copy_is_replaced_whole_and_leaves_nothing_beside_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La copia se cambia de golpe y con el cerrojo tomado; no queda un `.tmp` en la bóveda."""
    index = 424245
    target = vault._vault() / f"informe-{index}.md"
    real = vault.os.replace
    swaps: list[tuple[str, str, bool]] = []

    def replace(source: Path, destination: Path) -> None:
        swaps.append((Path(source).name, Path(destination).name, vault._LOCK.locked()))
        real(source, destination)

    monkeypatch.setattr(vault.os, "replace", replace)
    try:
        assert vault.check(_OnePage(), index, FRAGMENT, "crew-01", "CMO")["estado"] == "confirmada"
        assert swaps == [(target.name + ".tmp", target.name, True)]
        assert [path.name for path in target.parent.glob(f"informe-{index}*")] == [target.name]
    finally:
        target.unlink(missing_ok=True)


def test_the_literal_phrase_is_read_under_the_same_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """`locate` no suelta el cerrojo entre el cotejo y la lectura de la frase."""
    index = 424246
    real = vault._span
    held: list[bool] = []

    def span(tool: object, text: str, fragment: str) -> tuple[int, int] | None:
        held.append(vault._LOCK.locked())
        return real(tool, text, fragment)

    monkeypatch.setattr(vault, "_span", span)
    try:
        _, quote = vault.locate(_OnePage(), index, FRAGMENT, "crew-01", "CMO")
    finally:
        (vault._vault() / f"informe-{index}.md").unlink(missing_ok=True)
    assert quote["estado"] == vault.LOCATED and held == [True]
    assert not vault._LOCK.locked()

