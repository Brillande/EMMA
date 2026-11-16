"""«Descargar modelos»: partir el paquete, bajarlo, comprobarlo e instalarlo. Sin red real.

Un paquete de juguete con la forma del de `packaging/models_pack.py` se parte con
`packaging/models_parts.py` y se sirve con respx desde la URL publicada (invariante 3).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tarfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx

from app.core import egress
from app.core.config import Settings
from app.models_download import Downloader, installed

BASE = "https://github.com/Brillande/EMMA/releases/latest/download"
PACKAGING = Path(__file__).resolve().parents[1] / "packaging"


def _load_parts() -> ModuleType:
    spec = importlib.util.spec_from_file_location("models_parts", PACKAGING / "models_parts.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["models_parts"] = module
    spec.loader.exec_module(module)
    return module


parts_mod = _load_parts()


@pytest.fixture(autouse=True)
def no_safe_mode() -> Iterator[None]:
    previous = egress._safe_mode
    egress.set_safe_mode_provider(None)
    yield
    egress.set_safe_mode_provider(previous)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_pack(root: Path) -> Path:
    """Un paquete pequeño: dos piezas, una con un fichero que cruza varios trozos."""
    pack = root / "pack"
    contents = {
        "voice/python.exe": b"py" * 10,
        "voice/Lib/site-packages/whisper/base.pt": bytes(range(256)) * 40,
        "tesseract/tesseract.exe": b"ocr",
        "tesseract/tessdata/spa.traineddata": b"spa" * 50,
        "LEEME.txt": b"leeme",
        "instalar.cmd": b"@echo off",
        "instalar.ps1": b"# ps",
    }
    files: dict[str, list[Any]] = {}
    for rel, data in contents.items():
        path = pack / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[rel] = [len(data), _sha(data)]
    manifest = {
        "emma_models_pack": 1, "created": "2026-11-15T10:00:00+00:00",
        "components": {"voice": {"path": "voice"}, "tesseract": {"path": "tesseract"}},
        "left_out": {}, "files": files,
    }
    (pack / "MANIFIESTO.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pack


@pytest.fixture
def published(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    # Trozos de 4 KiB: el tar de `voice` ocupa varios, y un fichero cae entre dos.
    parts_mod.build(make_pack(tmp_path), out, 4096)
    return out


def serve(router: respx.Router, folder: Path, *, ranges: bool = True) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        path = folder / name
        if not path.is_file():
            return httpx.Response(404)
        data = path.read_bytes()
        header = request.headers.get("Range")
        if ranges and header:
            first, _, last = header.removeprefix("bytes=").partition("-")
            end = int(last) + 1 if last else len(data)
            return httpx.Response(206, content=data[int(first):end])
        return httpx.Response(200, content=data)

    router.get(url__startswith=BASE).mock(side_effect=handler)


def settings_for(tmp_path: Path, **extra: Any) -> Settings:
    return Settings(cache_dir=tmp_path / "cache", offline=False,
                    models_dir=tmp_path / "EMMA-modelos", models_url=BASE, **extra)


def run(settings: Settings, components: list[str] | None = None) -> dict[str, Any]:
    downloader = Downloader()
    downloader.start(settings, components)
    downloader.wait(30)
    return downloader.snapshot()["job"]


def test_the_split_keeps_each_part_under_its_limit_and_fingerprinted(published: Path) -> None:
    index = json.loads((published / "emma-modelos-partes.json").read_text(encoding="utf-8"))
    voice = index["components"]["voice"]
    assert len(voice["parts"]) > 1
    for part in voice["parts"]:
        data = (published / part["name"]).read_bytes()
        assert len(data) == part["size"] <= 4096
        assert _sha(data) == part["sha256"]
    # Ni enlaces ni nada que no sea un fichero normal en el tar.
    joined = b"".join((published / p["name"]).read_bytes() for p in voice["parts"])
    tar_path = published / "voice.tar"
    tar_path.write_bytes(joined)
    with tarfile.open(tar_path) as tar:
        assert all(m.isfile() for m in tar.getmembers())
        assert sorted(m.name for m in tar.getmembers()) == [
            "voice/Lib/site-packages/whisper/base.pt", "voice/python.exe"]


def test_everything_together_installs_and_activates(tmp_path: Path, published: Path) -> None:
    settings = settings_for(tmp_path)
    with respx.mock as router:
        serve(router, published)
        job = run(settings)
    assert job["state"] == "done", job
    dest = tmp_path / "EMMA-modelos"
    assert (dest / "voice" / "Lib" / "site-packages" / "whisper" / "base.pt").read_bytes() == (
        bytes(range(256)) * 40)
    assert (dest / "tesseract" / "tesseract.exe").read_bytes() == b"ocr"
    assert (dest / "LEEME.txt").read_bytes() == b"leeme"
    assert set(installed(dest)) == {"voice", "tesseract"}
    record = json.loads((dest / "instalado.json").read_text(encoding="utf-8"))
    assert record["via"] == "descarga"
    assert job["done_bytes"] == job["total_bytes"] > 0
    # Los trozos se borran según se usan: no se queda el doble de disco.
    assert not (tmp_path / "EMMA-modelos.descarga").exists()


def test_one_piece_installs_only_that_piece(tmp_path: Path, published: Path) -> None:
    settings = settings_for(tmp_path)
    with respx.mock as router:
        serve(router, published)
        job = run(settings, ["tesseract"])
    assert job["state"] == "done"
    assert set(installed(tmp_path / "EMMA-modelos")) == {"tesseract"}
    assert not (tmp_path / "EMMA-modelos" / "voice").exists()


def test_offline_downloads_nothing(tmp_path: Path, published: Path) -> None:
    settings = settings_for(tmp_path).model_copy(update={"offline": True})
    with respx.mock(assert_all_called=False) as router:
        serve(router, published)
        job = run(settings)
        assert not router.calls
    assert job["state"] == "error" and job["error"] == "blocked"
    assert not (tmp_path / "EMMA-modelos" / "instalado.json").exists()


def test_a_tampered_part_is_refused_and_nothing_is_activated(
    tmp_path: Path, published: Path
) -> None:
    index = json.loads((published / "emma-modelos-partes.json").read_text(encoding="utf-8"))
    name = index["components"]["voice"]["parts"][1]["name"]
    data = bytearray((published / name).read_bytes())
    data[10] ^= 0xFF
    (published / name).write_bytes(bytes(data))
    settings = settings_for(tmp_path)
    with respx.mock as router:
        serve(router, published)
        job = run(settings, ["voice"])
    assert job["state"] == "error" and job["error"] == "bad-part"
    assert not (tmp_path / "EMMA-modelos" / "voice").exists()
    assert installed(tmp_path / "EMMA-modelos") == {}


def test_a_file_the_manifest_does_not_name_is_refused(tmp_path: Path) -> None:
    pack = make_pack(tmp_path)
    out = tmp_path / "out"
    parts_mod.build(pack, out, 1 << 20)
    # Un tar rehecho con una ruta que escapa de la carpeta, con trozo e índice coherentes.
    evil = tmp_path / "evil.tar"
    with tarfile.open(evil, "w") as tar:
        info = tarfile.TarInfo("voice/../../fuera.txt")
        info.size = 3
        import io
        tar.addfile(info, io.BytesIO(b"mal"))
    data = evil.read_bytes()
    index = json.loads((out / "emma-modelos-partes.json").read_text(encoding="utf-8"))
    for part in index["components"]["voice"]["parts"]:
        (out / part["name"]).unlink()
    index["components"]["voice"]["parts"] = [
        {"name": "emma-modelos-voice.tar.000", "size": len(data), "sha256": _sha(data)}]
    (out / "emma-modelos-voice.tar.000").write_bytes(data)
    (out / "emma-modelos-partes.json").write_text(json.dumps(index), encoding="utf-8")
    settings = settings_for(tmp_path)
    with respx.mock as router:
        serve(router, out)
        job = run(settings, ["voice"])
    assert job["state"] == "error" and job["error"] == "bad-archive"
    assert not (tmp_path / "fuera.txt").exists()
    assert not (tmp_path / "EMMA-modelos" / "voice").exists()


def test_a_cut_part_resumes_by_its_blocks(
    tmp_path: Path, published: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lo bajado de una vez anterior queda anotado por bloques: solo se piden los que faltan."""
    from app import models_fetch

    monkeypatch.setattr(models_fetch, "BLOCK", 1024)
    index = json.loads((published / "emma-modelos-partes.json").read_text(encoding="utf-8"))
    first = index["components"]["voice"]["parts"][0]
    data = (published / first["name"]).read_bytes()
    staging = tmp_path / "EMMA-modelos.descarga" / "partes"
    staging.mkdir(parents=True)
    # Un trozo a medias: el bloque 0 bajado y anotado, el resto en blanco.
    partial = bytearray(len(data))
    partial[:1024] = data[:1024]
    (staging / (first["name"] + ".partial")).write_bytes(bytes(partial))
    (staging / (first["name"] + ".bloques.json")).write_text(json.dumps(
        {"size": first["size"], "sha256": first["sha256"], "block": 1024, "done": [0]}
    ), encoding="utf-8")
    asked: list[str] = []
    settings = settings_for(tmp_path)
    with respx.mock as router:
        def handler(request: httpx.Request) -> httpx.Response:
            name = request.url.path.rsplit("/", 1)[-1]
            body = (published / name).read_bytes()
            header = request.headers.get("Range")
            if name == first["name"] and header:
                asked.append(header)
            if header:
                a, _, b = header.removeprefix("bytes=").partition("-")
                return httpx.Response(206, content=body[int(a):int(b) + 1 if b else len(body)])
            return httpx.Response(200, content=body)

        router.get(url__startswith=BASE).mock(side_effect=handler)
        job = run(settings, ["voice"])
    assert job["state"] == "done", job
    assert "bytes=0-1023" not in asked
    assert "bytes=1024-2047" in asked
    assert job["done_bytes"] == job["total_bytes"]


def test_not_published_yet_says_so(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    with respx.mock as router:
        router.get(url__startswith=BASE).mock(return_value=httpx.Response(404))
        job = run(settings)
    assert job["state"] == "error" and job["error"] == "not-published"


def test_a_folder_that_is_not_the_pack_is_never_written(tmp_path: Path, published: Path) -> None:
    dest = tmp_path / "EMMA-modelos"
    dest.mkdir()
    (dest / "mio.txt").write_text("no tocar", encoding="utf-8")
    settings = settings_for(tmp_path)
    with respx.mock(assert_all_called=False) as router:
        serve(router, published)
        job = run(settings)
    assert job["state"] == "error" and job["error"] == "foreign-dir"
    assert sorted(p.name for p in dest.iterdir()) == ["mio.txt"]


def test_the_purpose_only_reaches_github(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    with pytest.raises(egress.EgressNotAllowed):
        egress.authorize(settings, "models-pack", "https://example.com/emma-modelos-partes.json")


def test_the_api_reports_and_starts(tmp_path: Path, published: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.api import models_pack
    from app.core.config import get_settings
    from app.main import app

    fresh = Downloader()
    monkeypatch.setattr(models_pack, "downloader", fresh)
    settings = settings_for(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client, respx.mock(assert_all_called=False) as router:
            router.route(host="testserver").pass_through()
            serve(router, published)
            body = client.get("/api/models-pack").json()
            assert body["checked"] is False and body["pieces"] == []
            body = client.post("/api/models-pack/check", headers={"X-EMMA-Console": "1"}).json()
            assert {p["name"] for p in body["pieces"]} == {"voice", "tesseract"}
            assert all(p["download_bytes"] > 0 and not p["installed"] for p in body["pieces"])
            response = client.post("/api/models-pack/download", json={},
                                   headers={"X-EMMA-Console": "1"})
            assert response.status_code == 202
            fresh.wait(30)
            body = client.get("/api/models-pack").json()
            assert body["job"]["state"] == "done"
            assert all(p["installed"] and p["current"] for p in body["pieces"])
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_the_installer_choice_downloads_everything_on_first_start(
    tmp_path: Path, published: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import models_pack

    fresh = Downloader()
    monkeypatch.setattr(models_pack, "downloader", fresh)
    # Sin la marca del instalador, nada.
    assert models_pack.autostart(settings_for(tmp_path)) is False
    # Sin red, tampoco: ni lo intenta.
    offline = settings_for(tmp_path, models_autodownload=True).model_copy(update={"offline": True})
    assert models_pack.autostart(offline) is False
    settings = settings_for(tmp_path, models_autodownload=True)
    with respx.mock as router:
        serve(router, published)
        assert models_pack.autostart(settings) is True
        fresh.wait(30)
    assert fresh.snapshot()["job"]["state"] == "done"
    # Con algo ya instalado, al arrancar otra vez no vuelve a bajar.
    assert models_pack.autostart(settings) is False


def test_each_part_comes_in_blocks_and_every_block_is_asked_once(
    tmp_path: Path, published: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cada trozo por bloques (`Range`), muchos a la vez: lo que hace la descarga rápida."""
    from app import models_fetch

    monkeypatch.setattr(models_fetch, "BLOCK", 1024)
    index = json.loads((published / "emma-modelos-partes.json").read_text(encoding="utf-8"))
    first = index["components"]["voice"]["parts"][0]
    asked: list[str] = []
    settings = settings_for(tmp_path)
    with respx.mock as router:
        def handler(request: httpx.Request) -> httpx.Response:
            name = request.url.path.rsplit("/", 1)[-1]
            body = (published / name).read_bytes()
            header = request.headers.get("Range")
            if name == first["name"] and header:
                asked.append(header)
            if header:
                a, _, b = header.removeprefix("bytes=").partition("-")
                return httpx.Response(206, content=body[int(a):int(b) + 1 if b else len(body)])
            return httpx.Response(200, content=body)

        router.get(url__startswith=BASE).mock(side_effect=handler)
        job = run(settings, ["voice"])
    assert job["state"] == "done", job
    size = first["size"]
    assert sorted(asked) == sorted(
        f"bytes={s}-{min(s + 1024, size) - 1}" for s in range(0, size, 1024)
    )
    assert (tmp_path / "EMMA-modelos" / "voice" / "python.exe").read_bytes() == b"py" * 10
    assert job["done_bytes"] == job["total_bytes"]
    assert job["connections"] >= 1


def test_the_controller_opens_while_it_pays_and_stops_when_not() -> None:
    from app.models_fetch import Controller

    control = Controller(start=8, top=64)
    assert control.update(10.0, 0) == 12      # sube: más
    assert control.update(20.0, 4) == 18      # sube: más
    assert control.update(20.5, 8) == 12      # ya no sube: al que dio lo mejor, y quieto
    assert control.update(30.0, 20) == 12     # quieto hasta volver a probar
    assert control.update(30.0, 40) == 15     # a los 30 s, prueba con algo más
    big = Controller(start=60, top=64)
    big.update(10.0, 0)
    assert big.update(50.0, 4) == 64          # nunca pasa del tope


def test_a_server_without_ranges_is_not_taken_for_a_whole_part(
    tmp_path: Path, published: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import models_fetch

    monkeypatch.setattr(models_fetch, "BLOCK", 1024)
    settings = settings_for(tmp_path)
    with respx.mock as router:
        serve(router, published, ranges=False)
        job = run(settings, ["voice"])
    assert job["state"] == "error" and job["error"] == "network"
    assert not (tmp_path / "EMMA-modelos" / "voice").exists()


def test_a_cut_download_resumes_on_the_next_start_with_a_piece_installed(
    tmp_path: Path, published: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con la primera pieza ya instalada, al volver a abrir EMMA se sigue con las demás."""
    from app.api import models_pack

    first = Downloader()
    monkeypatch.setattr(models_pack, "downloader", first)
    settings = settings_for(tmp_path, models_autodownload=True)
    with respx.mock as router:
        serve(router, published)
        first.start(settings, ["tesseract"])
        first.wait(30)
    assert set(installed(tmp_path / "EMMA-modelos")) == {"tesseract"}
    again = Downloader()
    monkeypatch.setattr(models_pack, "downloader", again)
    with respx.mock as router:
        serve(router, published)
        assert models_pack.autostart(settings) is True
        again.wait(30)
    assert set(installed(tmp_path / "EMMA-modelos")) == {"tesseract", "voice"}


@pytest.mark.parametrize(
    "rel",
    [
        "voice/../../fuera.txt", "voice/a/../../../fuera.txt", "voice//vacio.txt", "voice/./x",
        "voice/C:/Windows/x.dll", "voice/C:x", r"voice/a\..\..\x", "voice", "voice/",
    ],
)
def test_a_manifest_path_cannot_leave_the_pack_folder(tmp_path: Path, rel: str) -> None:
    """La ruta de cada fichero viene del manifiesto publicado: ni `..`, ni vacíos, ni unidades,
    ni barras invertidas, ni la carpeta misma (revisión de seguridad, 2026-11-16)."""
    from app.models_download import PackError, _inside

    with pytest.raises(PackError):
        _inside(tmp_path / "pieza", rel)


def test_an_ordinary_manifest_path_lands_inside(tmp_path: Path) -> None:
    from app.models_download import _inside

    target = tmp_path / "pieza"
    assert _inside(target, "voice/bin/whisper.exe") == target / "bin" / "whisper.exe"


def _tar_part(tmp_path: Path, name: str, data: bytes) -> Path:
    import io as _io

    part = tmp_path / "parte.tar"
    with tarfile.open(part, "w") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, _io.BytesIO(data))
    return part


def test_extracting_a_climbing_member_writes_nothing_outside(tmp_path: Path) -> None:
    """Por `_extract`, como en una descarga: el fichero que trepa no llega a escribirse."""
    from app.models_download import Downloader, PackError

    data = b"fuera"
    rel = "voice/../../fuera.txt"
    part = _tar_part(tmp_path, rel, data)
    target = tmp_path / "staging" / "voice"
    target.mkdir(parents=True)
    expected = {rel: (len(data), hashlib.sha256(data).hexdigest())}
    with pytest.raises(PackError):
        Downloader()._extract(iter([part]), target, expected, set())
    assert not (tmp_path / "fuera.txt").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="enlace de directorio de Windows (junction)")
def test_a_link_inside_the_folder_cannot_lead_outside(tmp_path: Path) -> None:
    """Los componentes son limpios, pero un enlace ya presente dentro llevaría fuera: lo mira la
    ruta resuelta."""
    import _winapi  # type: ignore[import-not-found]

    from app.models_download import PackError, _inside

    target, outside = tmp_path / "pieza", tmp_path / "fuera"
    target.mkdir()
    outside.mkdir()
    _winapi.CreateJunction(str(outside), str(target / "enlace"))
    with pytest.raises(PackError):
        _inside(target, "voice/enlace/x.txt")
