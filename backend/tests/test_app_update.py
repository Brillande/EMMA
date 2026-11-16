"""«Actualizar EMMA»: comprobar, bajar, verificar y pedir la instalación. Sin red real.

La última versión publicada se sirve con respx desde la URL de GitHub (invariante 3): un
`emma-update.json` y un instalador de juguete.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import app_update
from app.app_update import UpdateError, Updater, check_manifest, is_newer
from app.core import egress
from app.core.config import Settings

BASE = "https://github.com/Brillande/EMMA/releases/latest/download"
# El instalador se pide a su versión, no a `latest`, que puede moverse entretanto.
EXE = "https://github.com/Brillande/EMMA/releases/download/v0.1.5/EMMA.Setup.0.1.5.exe"
INSTALLER = b"MZ" + bytes(range(256)) * 64
SHA = hashlib.sha256(INSTALLER).hexdigest()
CONSOLE = {"X-EMMA-Console": "1"}


@pytest.fixture(autouse=True)
def no_safe_mode() -> Iterator[None]:
    previous = egress._safe_mode
    egress.set_safe_mode_provider(None)
    yield
    egress.set_safe_mode_provider(previous)


def manifest(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"schema": 1, "version": "0.1.5", "installer": "EMMA.Setup.0.1.5.exe",
                            "size": len(INSTALLER), "sha256": SHA, "notes": "Arreglos."}
    data.update(changes)
    return data


def settings_for(tmp_path: Path, version: str | None = "0.1.4", **extra: Any) -> Settings:
    return Settings(cache_dir=tmp_path / "cache", offline=False, update_url=BASE,
                    update_dir=tmp_path / "actualizacion", app_version=version, **extra)


def serve(router: respx.Router, *, data: dict[str, Any] | None = None,
          body: bytes = INSTALLER, ranges: bool = True,
          asked: list[str | None] | None = None) -> None:
    router.get(f"{BASE}/emma-update.json").mock(
        return_value=httpx.Response(200, json=data if data is not None else manifest()))

    def installer(request: httpx.Request) -> httpx.Response:
        header = request.headers.get("Range")
        if asked is not None:
            asked.append(header)
        if ranges and header:
            first = int(header.removeprefix("bytes=").rstrip("-"))
            return httpx.Response(206, content=body[first:])
        return httpx.Response(200, content=body)

    router.get(EXE).mock(side_effect=installer)


def download(settings: Settings, updater: Updater | None = None) -> Updater:
    updater = updater or Updater()
    updater.start(settings)
    updater.wait(30)
    return updater


# --- manifiesto -----------------------------------------------------------------------------


def test_a_valid_manifest_is_taken_as_published() -> None:
    checked = check_manifest(manifest(sha256=SHA.upper()))
    assert checked == {"version": "0.1.5", "installer": "EMMA.Setup.0.1.5.exe",
                       "size": len(INSTALLER), "sha256": SHA, "notes": "Arreglos."}


@pytest.mark.parametrize("change", [
    {"schema": 2}, {"schema": "1"},
    {"version": "v0.1.5"}, {"version": "0.1"}, {"version": "0.1.5-beta"}, {"version": "01.1.5"},
    {"installer": "../EMMA.Setup.0.1.5.exe"}, {"installer": "sub/EMMA.Setup.exe"},
    {"installer": "sub\\EMMA.Setup.exe"}, {"installer": "EMMA..exe"},
    {"installer": "EMMA.Setup.0.1.5.msi"}, {"installer": "C:EMMA.exe"},
    {"installer": "EMMA.exe:stream.exe"}, {"installer": ".exe"}, {"installer": 5},
    {"size": 0}, {"size": -1}, {"size": "100"}, {"size": True}, {"size": 1.5},
    {"sha256": "abc"}, {"sha256": "g" * 64}, {"sha256": SHA + "0"},
    {"notes": 3},
])
def test_an_invalid_manifest_is_refused(change: dict[str, Any]) -> None:
    with pytest.raises(UpdateError) as caught:
        check_manifest(manifest(**change))
    assert caught.value.code == "bad-manifest"


def test_a_manifest_without_a_field_or_not_an_object_is_refused() -> None:
    for key in ("schema", "version", "installer", "size", "sha256"):
        data = manifest()
        del data[key]
        with pytest.raises(UpdateError, match="bad-manifest"):
            check_manifest(data)
    with pytest.raises(UpdateError, match="bad-manifest"):
        check_manifest([manifest()])


def test_versions_compare_as_numbers() -> None:
    assert is_newer("0.1.10", "0.1.9") is True
    assert is_newer("0.2.0", "0.1.99") is True
    assert is_newer("0.1.4", "0.1.4") is False
    assert is_newer("0.1.3", "0.1.4") is False
    assert is_newer("0.1.5", None) is None
    assert is_newer("0.1.5", "desarrollo") is None


# --- comprobar ------------------------------------------------------------------------------


def test_check_finds_a_newer_version(tmp_path: Path) -> None:
    updater = Updater()
    with respx.mock as router:
        serve(router)
        updater.check(settings_for(tmp_path))
    assert updater.snapshot()["manifest"]["version"] == "0.1.5"


def test_an_invalid_published_manifest_is_bad_manifest(tmp_path: Path) -> None:
    updater = Updater()
    with respx.mock as router:
        serve(router, data=manifest(installer="../../fuera.exe"))
        with pytest.raises(UpdateError) as caught:
            updater.check(settings_for(tmp_path))
    assert caught.value.code == "bad-manifest"
    assert updater.snapshot()["error"][0] == "bad-manifest"


def test_offline_goes_nowhere_and_says_offline(tmp_path: Path) -> None:
    settings = settings_for(tmp_path).model_copy(update={"offline": True})
    updater = Updater()
    with respx.mock(assert_all_called=False) as router:
        serve(router)
        with pytest.raises(UpdateError) as caught:
            updater.check(settings)
        download(settings, updater)
        assert not router.calls
    assert caught.value.code == "offline"
    assert updater.snapshot()["error"][0] == "offline"
    assert not (tmp_path / "actualizacion" / "listo.json").exists()


def test_safe_mode_is_blocked_not_offline(tmp_path: Path) -> None:
    egress.set_safe_mode_provider(lambda: "prueba")
    updater = Updater()
    with respx.mock(assert_all_called=False) as router:
        serve(router)
        with pytest.raises(UpdateError) as caught:
            updater.check(settings_for(tmp_path))
        assert not router.calls
    assert caught.value.code == "blocked"


# --- descargar ------------------------------------------------------------------------------


def test_a_newer_version_downloads_and_is_left_ready(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    with respx.mock as router:
        serve(router)
        updater = download(settings)
    snap = updater.snapshot()
    assert snap["job"]["state"] == "done", snap
    assert snap["job"]["done_bytes"] == snap["job"]["total_bytes"] == len(INSTALLER)
    folder = tmp_path / "actualizacion"
    assert (folder / "EMMA.Setup.0.1.5.exe").read_bytes() == INSTALLER
    assert not (folder / "EMMA.Setup.0.1.5.exe.partial").exists()
    assert json.loads((folder / "listo.json").read_text(encoding="utf-8")) == {
        "version": "0.1.5", "file": "EMMA.Setup.0.1.5.exe", "sha256": SHA,
        "size": len(INSTALLER)}


@pytest.mark.parametrize("current", ["0.1.5", "0.2.0"])
def test_the_same_or_an_older_version_is_not_downloaded(tmp_path: Path, current: str) -> None:
    settings = settings_for(tmp_path, current)
    with respx.mock(assert_all_called=False) as router:
        serve(router)
        updater = download(settings)
        assert not any("Setup" in str(call.request.url) for call in router.calls)
        assert updater.snapshot()["error"][0] == "same-version"
        # Ya comprobado: ni se lanza.
        with pytest.raises(UpdateError, match="same-version"):
            updater.start(settings)
    assert not (tmp_path / "actualizacion" / "listo.json").exists()


def test_an_unknown_current_version_is_available_but_not_comparable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import app_update as route

    settings = settings_for(tmp_path, None)
    updater = Updater()
    monkeypatch.setattr(route, "updater", updater)
    assert route._state(settings)["comparable"] is False
    with respx.mock as router:
        serve(router)
        updater.check(settings)
    state = route._state(settings)
    assert state["state"] == "available"
    assert state["comparable"] is False
    assert state["available"] == {"version": "0.1.5", "size": len(INSTALLER),
                                  "notes": "Arreglos."}


def test_a_cut_download_resumes_with_range(tmp_path: Path) -> None:
    folder = tmp_path / "actualizacion"
    folder.mkdir()
    (folder / "EMMA.Setup.0.1.5.exe.partial").write_bytes(INSTALLER[:1000])
    asked: list[str | None] = []
    with respx.mock as router:
        serve(router, asked=asked)
        updater = download(settings_for(tmp_path))
    assert updater.snapshot()["job"]["state"] == "done"
    assert asked == ["bytes=1000-"]
    assert (folder / "EMMA.Setup.0.1.5.exe").read_bytes() == INSTALLER


def test_a_server_that_does_not_resume_starts_again(tmp_path: Path) -> None:
    folder = tmp_path / "actualizacion"
    folder.mkdir()
    (folder / "EMMA.Setup.0.1.5.exe.partial").write_bytes(b"x" * 1000)
    with respx.mock as router:
        serve(router, ranges=False)
        updater = download(settings_for(tmp_path))
    snap = updater.snapshot()
    assert snap["job"]["state"] == "done", snap
    assert snap["job"]["done_bytes"] == len(INSTALLER)
    assert (folder / "EMMA.Setup.0.1.5.exe").read_bytes() == INSTALLER


def test_a_bad_hash_is_tried_once_more_from_zero_and_then_refused(tmp_path: Path) -> None:
    tampered = bytearray(INSTALLER)
    tampered[100] ^= 0xFF
    asked: list[str | None] = []
    with respx.mock as router:
        serve(router, body=bytes(tampered), asked=asked)
        updater = download(settings_for(tmp_path))
    snap = updater.snapshot()
    assert snap["job"]["state"] == "error"
    assert snap["error"][0] == "bad-hash"
    assert asked == [None, None]  # dos veces, las dos desde cero
    folder = tmp_path / "actualizacion"
    assert not (folder / "listo.json").exists()
    assert not (folder / "EMMA.Setup.0.1.5.exe").exists()
    assert not (folder / "EMMA.Setup.0.1.5.exe.partial").exists()


def test_a_bad_first_try_and_a_good_second_one_is_ready(tmp_path: Path) -> None:
    folder = tmp_path / "actualizacion"
    folder.mkdir()
    # Lo que había a medias era de otra cosa: no casa, se borra y se baja de cero.
    (folder / "EMMA.Setup.0.1.5.exe.partial").write_bytes(b"x" * 1000)
    asked: list[str | None] = []
    with respx.mock as router:
        serve(router, asked=asked)
        updater = download(settings_for(tmp_path))
    assert updater.snapshot()["job"]["state"] == "done"
    assert asked == ["bytes=1000-", None]
    assert (folder / "listo.json").exists()


def test_no_space_downloads_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil

    usage = shutil.disk_usage(tmp_path)
    monkeypatch.setattr(app_update.shutil, "disk_usage",
                        lambda _p: usage._replace(free=10))
    with respx.mock(assert_all_called=False) as router:
        serve(router)
        updater = download(settings_for(tmp_path))
        assert not any("Setup" in str(call.request.url) for call in router.calls)
    assert updater.snapshot()["error"][0] == "no-space"


def test_cancel_stops_and_keeps_what_came_for_later(tmp_path: Path) -> None:
    import threading

    # El servidor no responde hasta que se ha pedido cancelar.
    updater = Updater()
    gate = threading.Event()

    def slow(request: httpx.Request) -> httpx.Response:
        gate.wait(5)
        return httpx.Response(200, content=INSTALLER)

    with respx.mock as router:
        router.get(f"{BASE}/emma-update.json").mock(
            return_value=httpx.Response(200, json=manifest()))
        router.get(EXE).mock(side_effect=slow)
        updater.start(settings_for(tmp_path))
        updater.cancel()
        gate.set()
        updater.wait(30)
    assert updater.snapshot()["job"]["state"] == "cancelled"
    assert not (tmp_path / "actualizacion" / "listo.json").exists()


def test_the_installer_cannot_leave_the_update_folder(tmp_path: Path) -> None:
    folder = tmp_path / "actualizacion"
    for name in ("../fuera.exe", "..\\fuera.exe", "/tmp/fuera.exe", "C:\\fuera.exe"):
        with pytest.raises(UpdateError, match="bad-manifest"):
            app_update._inside(folder, name)
    # Tampoco un `listo.json` manipulado en disco hace que se instale algo de fuera.
    folder.mkdir()
    outside = tmp_path / "fuera.exe"
    outside.write_bytes(INSTALLER)
    (folder / "listo.json").write_text(json.dumps({
        "version": "0.1.5", "file": "../fuera.exe", "sha256": SHA, "size": len(INSTALLER)}),
        encoding="utf-8")
    settings = settings_for(tmp_path)
    assert app_update.ready(settings) is None
    with pytest.raises(UpdateError, match="not-ready"):
        Updater().request_install(settings)
    assert not (folder / "instalar.json").exists()


def test_the_installer_comes_from_its_version_not_from_latest(tmp_path: Path) -> None:
    assert app_update.installer_url(settings_for(tmp_path), "0.1.5", "EMMA.Setup.0.1.5.exe") == EXE
    other = settings_for(tmp_path).model_copy(update={"update_url": "https://github.com/x/y"})
    assert app_update.installer_url(other, "0.1.5", "a.exe") == "https://github.com/x/y/a.exe"


def test_a_redirect_off_the_allowlist_ends_in_an_error_not_in_downloading(tmp_path: Path) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE}/emma-update.json").mock(
            return_value=httpx.Response(200, json=manifest()))
        router.get(EXE).mock(return_value=httpx.Response(
            302, headers={"Location": "https://example.com/EMMA.Setup.0.1.5.exe"}))
        updater = download(settings_for(tmp_path))
    snap = updater.snapshot()
    assert snap["job"]["state"] == "error"
    assert snap["error"][0] == "blocked"


def test_partials_of_other_versions_are_cleaned_after_a_download(tmp_path: Path) -> None:
    folder = tmp_path / "actualizacion"
    folder.mkdir()
    (folder / "EMMA.Setup.0.1.4.exe.partial").write_bytes(b"viejo")
    with respx.mock as router:
        serve(router)
        download(settings_for(tmp_path))
    assert not (folder / "EMMA.Setup.0.1.4.exe.partial").exists()


def test_a_failed_download_is_not_hidden_behind_an_older_ready_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import app_update as route

    settings = settings_for(tmp_path)
    updater = Updater()
    monkeypatch.setattr(route, "updater", updater)
    with respx.mock as router:
        serve(router)
        download(settings, updater)
    tampered = bytearray(INSTALLER)
    tampered[0] ^= 0xFF
    newer = manifest(version="0.1.6", installer="EMMA.Setup.0.1.6.exe",
                     sha256=hashlib.sha256(bytes(tampered)).hexdigest()[::-1])
    with respx.mock as router:
        router.get(f"{BASE}/emma-update.json").mock(return_value=httpx.Response(200, json=newer))
        router.get(url__regex=r".*EMMA\.Setup\.0\.1\.6\.exe$").mock(
            return_value=httpx.Response(200, content=bytes(tampered)))
        download(settings, updater)
    state = route._state(settings)
    assert state["state"] == "error" and state["error"]["code"] == "bad-hash"
    # Al empezar la 0.1.6, lo de la 0.1.5 pasó a sobrar y se borró.
    assert state["ready"] is None
    assert not list((tmp_path / "actualizacion").glob("*.exe"))


@pytest.mark.parametrize("name", ["NUL.exe", "con.exe", "COM1.exe", "lpt9.exe", "AUX.setup.exe",
                                  "CONIN$.exe"])
def test_a_windows_device_name_is_not_an_installer(name: str) -> None:
    with pytest.raises(UpdateError, match="bad-manifest"):
        check_manifest(manifest(installer=name))


def test_a_missing_installer_is_not_a_missing_manifest(tmp_path: Path) -> None:
    with respx.mock as router:
        router.get(f"{BASE}/emma-update.json").mock(
            return_value=httpx.Response(200, json=manifest()))
        router.get(EXE).mock(return_value=httpx.Response(404))
        updater = download(settings_for(tmp_path))
    assert updater.snapshot()["error"][0] == "installer-missing"


def test_a_new_download_clears_what_other_versions_left(tmp_path: Path) -> None:
    folder = tmp_path / "actualizacion"
    folder.mkdir()
    (folder / "EMMA.Setup.0.1.3.exe").write_bytes(b"viejo")
    (folder / "instalar.json").write_text(json.dumps({"file": "EMMA.Setup.0.1.3.exe"}),
                                          encoding="utf-8")
    (folder / "otro.txt").write_text("no es nuestro", encoding="utf-8")
    (folder / "sub").mkdir()
    (folder / "sub" / "dentro.exe").write_bytes(b"x")
    outside = tmp_path / "fuera.exe"
    outside.write_bytes(b"x")
    with respx.mock as router:
        serve(router)
        download(settings_for(tmp_path))
    assert sorted(p.name for p in folder.iterdir()) == [
        "EMMA.Setup.0.1.5.exe", "listo.json", "otro.txt", "sub"]
    assert (folder / "sub" / "dentro.exe").exists() and outside.exists()


def test_once_the_new_version_runs_its_leftovers_are_cleared(tmp_path: Path) -> None:
    with respx.mock as router:
        serve(router)
        download(settings_for(tmp_path))
    folder = tmp_path / "actualizacion"
    (folder / "instalar.json").write_text(json.dumps({"version": "0.1.5"}), encoding="utf-8")
    assert app_update.ready(settings_for(tmp_path, "0.1.5")) is None
    assert list(folder.iterdir()) == []


def test_install_during_a_download_is_busy(tmp_path: Path) -> None:
    import threading

    gate = threading.Event()

    def slow(request: httpx.Request) -> httpx.Response:
        gate.wait(5)
        return httpx.Response(200, content=INSTALLER)

    updater = Updater()
    with respx.mock as router:
        router.get(f"{BASE}/emma-update.json").mock(
            return_value=httpx.Response(200, json=manifest()))
        router.get(EXE).mock(side_effect=slow)
        updater.start(settings_for(tmp_path))
        try:
            with pytest.raises(UpdateError) as caught:
                updater.request_install(settings_for(tmp_path))
        finally:
            gate.set()
            updater.wait(30)
    assert caught.value.code == "busy"


# --- instalar -------------------------------------------------------------------------------


def test_install_without_a_ready_installer_is_not_ready(tmp_path: Path) -> None:
    with pytest.raises(UpdateError) as caught:
        Updater().request_install(settings_for(tmp_path))
    assert caught.value.code == "not-ready"


def test_install_with_a_ready_installer_writes_the_request(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    with respx.mock as router:
        serve(router)
        updater = download(settings)
    record = updater.request_install(settings)
    written = json.loads((tmp_path / "actualizacion" / "instalar.json").read_text(
        encoding="utf-8"))
    assert written == record
    assert {k: written[k] for k in ("version", "file", "sha256")} == {
        "version": "0.1.5", "file": "EMMA.Setup.0.1.5.exe", "sha256": SHA}
    assert written["requested_at"].endswith("+00:00")


def test_an_installer_changed_after_the_download_is_not_installed(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    with respx.mock as router:
        serve(router)
        updater = download(settings)
    exe = tmp_path / "actualizacion" / "EMMA.Setup.0.1.5.exe"
    data = bytearray(exe.read_bytes())
    data[5] ^= 0xFF
    exe.write_bytes(bytes(data))
    with pytest.raises(UpdateError, match="bad-hash"):
        updater.request_install(settings)
    assert not (tmp_path / "actualizacion" / "instalar.json").exists()


def test_safe_mode_blocks_installing_even_a_ready_installer(tmp_path: Path) -> None:
    # Decisión del usuario (2026-11-16): con el modo seguro no se cambia de versión, aunque el
    # instalador ya esté bajado y comprobado y no haga falta red para instalarlo.
    settings = settings_for(tmp_path)
    with respx.mock as router:
        serve(router)
        updater = download(settings)
    egress.set_safe_mode_provider(lambda: "contingencia")
    with pytest.raises(UpdateError) as caught:
        updater.request_install(settings)
    assert (caught.value.code, caught.value.detail) == ("safe-mode", "contingencia")
    assert not (tmp_path / "actualizacion" / "instalar.json").exists()
    assert app_update.ready(settings) is not None
    egress.set_safe_mode_provider(None)
    assert updater.request_install(settings)["version"] == "0.1.5"


def test_once_running_the_new_version_nothing_is_ready(tmp_path: Path) -> None:
    with respx.mock as router:
        serve(router)
        download(settings_for(tmp_path))
    assert app_update.ready(settings_for(tmp_path)) is not None
    assert app_update.ready(settings_for(tmp_path, "0.1.5")) is None


# --- la API ---------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Updater]]:
    from app.api import app_update as route
    from app.core.config import get_settings
    from app.main import app

    fresh = Updater()
    monkeypatch.setattr(route, "updater", fresh)
    settings = settings_for(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            yield client, fresh
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_the_api_checks_downloads_and_asks_to_install(
    api: tuple[TestClient, Updater],
) -> None:
    client, fresh = api
    with respx.mock(assert_all_called=False) as router:
        router.route(host="testserver").pass_through()
        serve(router)
        body = client.get("/api/app-update").json()
        assert body == {
            "state": "idle", "phase": None, "current_version": "0.1.4", "available": None,
            "comparable": True, "done_bytes": 0, "total_bytes": 0, "ready": None,
            "install_requested": False, "error": None, "network": True, "network_note": None,
            "restart_note": body["restart_note"],
        }
        assert client.post("/api/app-update/install", headers=CONSOLE).status_code == 409
        body = client.post("/api/app-update/check", headers=CONSOLE).json()
        assert body["state"] == "available" and body["comparable"] is True
        assert body["available"]["version"] == "0.1.5"
        response = client.post("/api/app-update/download", headers=CONSOLE)
        assert response.status_code == 202
        fresh.wait(30)
        body = client.get("/api/app-update").json()
        assert body["state"] == "ready" and body["ready"] == {"version": "0.1.5"}
        assert body["install_requested"] is False
        body = client.post("/api/app-update/install", headers=CONSOLE).json()
        assert body["install_requested"] is True
        assert client.post("/api/app-update/cancel", headers=CONSOLE).status_code == 200


def test_the_api_refuses_to_install_in_safe_mode(api: tuple[TestClient, Updater]) -> None:
    client, fresh = api
    with respx.mock(assert_all_called=False) as router:
        router.route(host="testserver").pass_through()
        serve(router)
        client.post("/api/app-update/check", headers=CONSOLE)
        client.post("/api/app-update/download", headers=CONSOLE)
        fresh.wait(30)
        egress.set_safe_mode_provider(lambda: "contingencia")
        response = client.post("/api/app-update/install", headers=CONSOLE)
    assert response.status_code == 423
    assert "contingencia" in response.json()["detail"]
    assert client.get("/api/app-update").json()["install_requested"] is False


def test_the_api_offline_says_so_and_goes_nowhere(
    api: tuple[TestClient, Updater], tmp_path: Path,
) -> None:
    from app.core.config import get_settings
    from app.main import app

    client, _fresh = api
    offline = settings_for(tmp_path).model_copy(update={"offline": True})
    app.dependency_overrides[get_settings] = lambda: offline
    body = client.get("/api/app-update").json()
    assert body["network"] is False and body["network_note"]
    response = client.post("/api/app-update/check", headers=CONSOLE)
    assert response.status_code == 503
    body = client.get("/api/app-update").json()
    assert body["state"] == "error" and body["error"]["code"] == "offline"
    response = client.post("/api/app-update/install", headers=CONSOLE)
    assert response.status_code == 409


def test_the_api_posts_need_the_console_header(api: tuple[TestClient, Updater]) -> None:
    client, _fresh = api
    del client.headers["X-EMMA-Console"]
    for path in ("check", "download", "cancel", "install"):
        assert client.post(f"/api/app-update/{path}").status_code == 403, path


def test_nothing_checks_for_updates_on_start() -> None:
    """Decisión del usuario: no hay comprobación automática al arrancar."""
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert "app_update import app_update_router" in source
    assert "updater" not in source
