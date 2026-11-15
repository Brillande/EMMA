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


def test_a_cut_part_resumes_where_it_was(tmp_path: Path, published: Path) -> None:
    index = json.loads((published / "emma-modelos-partes.json").read_text(encoding="utf-8"))
    first = index["components"]["voice"]["parts"][0]["name"]
    staging = tmp_path / "EMMA-modelos.descarga" / "partes"
    staging.mkdir(parents=True)
    (staging / (first + ".partial")).write_bytes((published / first).read_bytes()[:1000])
    asked: list[str | None] = []
    settings = settings_for(tmp_path)
    with respx.mock as router:
        def handler(request: httpx.Request) -> httpx.Response:
            name = request.url.path.rsplit("/", 1)[-1]
            data = (published / name).read_bytes()
            if name == first:
                asked.append(request.headers.get("Range"))
            header = request.headers.get("Range")
            if header:
                return httpx.Response(206, content=data[int(header[6:-1]):])
            return httpx.Response(200, content=data)

        router.get(url__startswith=BASE).mock(side_effect=handler)
        job = run(settings, ["voice"])
    assert job["state"] == "done", job
    assert asked == ["bytes=1000-"]


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


def test_big_parts_come_in_ranges_at_once_and_resume_each(
    tmp_path: Path, published: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cada trozo en tramos (`Range`) a la vez: lo que hace la descarga 10 veces más rápida."""
    from app import models_download

    monkeypatch.setattr(models_download, "SEGMENT_MIN", 1)
    index = json.loads((published / "emma-modelos-partes.json").read_text(encoding="utf-8"))
    first = index["components"]["voice"]["parts"][0]
    # Un tramo ya empezado de una vez anterior: se sigue por donde iba.
    staging = tmp_path / "EMMA-modelos.descarga" / "partes"
    staging.mkdir(parents=True)
    begun = (published / first["name"]).read_bytes()[:100]
    (staging / (first["name"] + ".tramo0")).write_bytes(begun)
    asked: list[str] = []
    settings = settings_for(tmp_path)
    with respx.mock as router:
        def handler(request: httpx.Request) -> httpx.Response:
            name = request.url.path.rsplit("/", 1)[-1]
            data = (published / name).read_bytes()
            header = request.headers.get("Range")
            if name == first["name"] and header:
                asked.append(header)
            if header:
                a, _, b = header.removeprefix("bytes=").partition("-")
                return httpx.Response(206, content=data[int(a):int(b) + 1 if b else len(data)])
            return httpx.Response(200, content=data)

        router.get(url__startswith=BASE).mock(side_effect=handler)
        job = run(settings, ["voice"])
    assert job["state"] == "done", job
    step = -(-first["size"] // models_download.SEGMENTS_PER_PART)
    assert sorted(asked) == sorted(
        [f"bytes=100-{step - 1}"]
        + [f"bytes={s}-{min(s + step, first['size']) - 1}"
           for s in range(step, first["size"], step)]
    )
    assert (tmp_path / "EMMA-modelos" / "voice" / "python.exe").read_bytes() == b"py" * 10
    assert job["done_bytes"] == job["total_bytes"]


def test_a_server_without_ranges_is_not_taken_for_a_whole_part(
    tmp_path: Path, published: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import models_download

    monkeypatch.setattr(models_download, "SEGMENT_MIN", 1)
    settings = settings_for(tmp_path)
    with respx.mock as router:
        serve(router, published, ranges=False)
        job = run(settings, ["voice"])
    assert job["state"] == "error" and job["error"] == "network"
    assert not (tmp_path / "EMMA-modelos" / "voice").exists()
