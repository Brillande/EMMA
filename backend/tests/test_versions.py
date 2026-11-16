"""La versión del repositorio y la publicación del instalador (`packaging/publish_app.py`).

Por qué existe: el EMMA instalado se compara con `emma-update.json` de la última versión de
GitHub. Si los cuatro sitios que declaran la versión discrepan, el programa diría una y el
manifiesto otra. Y el manifiesto tiene que cumplir el contrato que lee el instalado (nombre del
fichero con puntos, tamaño, SHA-256) y subir después del instalador.

Aquí nunca se ejecuta `gh`: `subprocess.run` está simulado y se mira el orden de las llamadas.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGING = ROOT / "backend" / "packaging"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("publish_app", PACKAGING / "publish_app.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["publish_app"] = module
    spec.loader.exec_module(module)
    return module


pa = _load()


class FakeRun:
    """Sustituye a `subprocess.run`: anota cada orden y responde lo que se le diga."""

    def __init__(self, view_rc: int = 1, view_err: str = "release not found") -> None:
        self.calls: list[list[str]] = []
        self.view_rc = view_rc
        self.view_err = view_err

    def __call__(self, cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "gh"
        self.calls.append(list(cmd[1:]))
        if cmd[1:3] == ["release", "view"]:
            return subprocess.CompletedProcess(cmd, self.view_rc, "", self.view_err)
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> FakeRun:
    fake = FakeRun()
    monkeypatch.setattr(pa.subprocess, "run", fake)
    monkeypatch.setattr(pa.time, "sleep", lambda _s: None)
    return fake


def _fake_repo(root: Path, version: str = "1.2.3", main_version: str | None = None) -> Path:
    (root / "backend" / "app").mkdir(parents=True)
    (root / "frontend").mkdir()
    (root / "desktop" / "release").mkdir(parents=True)
    (root / "backend" / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8")
    (root / "backend" / "app" / "main.py").write_text(
        f'app = FastAPI(\n    title="EMMA",\n    version="{main_version or version}",\n)\n',
        encoding="utf-8")
    for d in ("frontend", "desktop"):
        (root / d / "package.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    exe = root / "desktop" / "release" / f"EMMA Setup {version}.exe"
    exe.write_bytes(b"MZ" + b"\0" * 1000)
    return exe


# --- (a) La versión del repositorio --------------------------------------------------------


def test_version_is_the_same_in_the_four_places() -> None:
    versions = pa.read_versions(ROOT)
    assert len(versions) == 4
    assert len(set(versions.values())) == 1, versions
    assert re.fullmatch(r"\d+\.\d+\.\d+", pa.agreed_version(versions))


def test_disagreeing_versions_stop(tmp_path: Path) -> None:
    _fake_repo(tmp_path, "1.2.3", main_version="1.2.2")
    with pytest.raises(pa.PublishError, match="no coincide"):
        pa.agreed_version(pa.read_versions(tmp_path))


def test_non_semver_version_stops() -> None:
    with pytest.raises(pa.PublishError):
        pa.agreed_version({"a": "1.2", "b": "1.2"})


# --- (b) El manifiesto y el orden de publicación ---------------------------------------------


def test_asset_name_uses_dots_like_github() -> None:
    assert pa.local_installer_name("0.1.4") == "EMMA Setup 0.1.4.exe"
    assert pa.asset_name("0.1.4") == "EMMA.Setup.0.1.4.exe"
    assert pa.tag_for("0.1.4") == "v0.1.4"


def test_manifest_meets_the_contract(tmp_path: Path) -> None:
    exe = tmp_path / "EMMA Setup 1.2.3.exe"
    exe.write_bytes(b"instalador falso")
    m = pa.build_manifest(exe, "1.2.3", "  Arreglos.\n")
    assert set(m) == {"schema", "version", "installer", "size", "sha256", "notes"}
    assert m["schema"] == 1
    assert m["version"] == "1.2.3"
    assert m["installer"] == "EMMA.Setup.1.2.3.exe"
    assert m["size"] == len(b"instalador falso")
    assert re.fullmatch(r"[0-9a-f]{64}", m["sha256"])
    assert m["sha256"] == pa.sha256_of(exe)
    assert m["notes"] == "Arreglos."


def test_manifest_without_notes_stops(tmp_path: Path) -> None:
    exe = tmp_path / "x.exe"
    exe.write_bytes(b"x")
    with pytest.raises(pa.PublishError):
        pa.build_manifest(exe, "1.2.3", "   ")


def test_publish_order_manifest_after_exe_and_latest_last(
    tmp_path: Path, fake_run: FakeRun, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_repo(tmp_path)
    assert pa.main(["--notes", "Arreglos."], root=tmp_path) == 0
    calls = fake_run.calls
    assert calls[0][:3] == ["release", "view", "v1.2.3"]
    assert calls[1][:4] == ["release", "create", "v1.2.3", "--draft"]
    uploads = [c for c in calls if c[:2] == ["release", "upload"]]
    assert [Path(c[3]).name for c in uploads] == ["EMMA.Setup.1.2.3.exe", "emma-update.json"]
    assert calls.index(uploads[0]) < calls.index(uploads[1])
    assert calls[-1][:3] == ["release", "edit", "v1.2.3"]
    assert "--draft=false" in calls[-1] and "--latest" in calls[-1]
    assert all("Brillande/EMMA" in c for c in calls)
    printed = json.loads(capsys.readouterr().out.split("PUBLICADO")[0])
    assert printed["installer"] == "EMMA.Setup.1.2.3.exe"


def test_existing_tag_stops_before_creating(tmp_path: Path, fake_run: FakeRun) -> None:
    _fake_repo(tmp_path)
    fake_run.view_rc = 0
    assert pa.main(["--notes", "x"], root=tmp_path) == 1
    assert [c[:2] for c in fake_run.calls] == [["release", "view"]]


def test_unknown_view_error_stops(tmp_path: Path, fake_run: FakeRun) -> None:
    _fake_repo(tmp_path)
    fake_run.view_err = "authentication required"
    assert pa.main(["--notes", "x"], root=tmp_path) == 1
    assert len(fake_run.calls) == 1


def test_disagreeing_versions_never_call_gh(tmp_path: Path, fake_run: FakeRun) -> None:
    _fake_repo(tmp_path, "1.2.3", main_version="1.2.2")
    assert pa.main(["--notes", "x"], root=tmp_path) == 1
    assert fake_run.calls == []


def test_missing_installer_stops(tmp_path: Path, fake_run: FakeRun) -> None:
    _fake_repo(tmp_path).unlink()
    assert pa.main(["--notes", "x"], root=tmp_path) == 1
    assert fake_run.calls == []


def test_dry_run_never_calls_gh(tmp_path: Path, fake_run: FakeRun,
                                capsys: pytest.CaptureFixture[str]) -> None:
    _fake_repo(tmp_path)
    other = tmp_path / "otro.exe"
    other.write_bytes(b"otro")
    notes = tmp_path / "notas.md"
    notes.write_text("Notas largas.\n", encoding="utf-8")
    assert pa.main(["--notes-file", str(notes), "--installer", str(other), "--dry-run"],
                   root=tmp_path) == 0
    assert fake_run.calls == []
    out = capsys.readouterr().out
    manifest = json.loads(out.split("(simulacro)")[0])
    assert manifest["size"] == 4 and manifest["notes"] == "Notas largas."
    assert out.index("EMMA.Setup.1.2.3.exe --clobber") < out.index("emma-update.json --clobber")


def test_failed_upload_never_publishes_and_says_how_to_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_repo(tmp_path)
    fake = FakeRun()
    real_call = fake.__call__

    def failing(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        done = real_call(cmd, **kw)
        if cmd[1:3] == ["release", "upload"]:
            return subprocess.CompletedProcess(cmd, 1, "", "red caída")
        return done

    monkeypatch.setattr(pa.subprocess, "run", failing)
    monkeypatch.setattr(pa.time, "sleep", lambda _s: None)
    assert pa.main(["--notes", "x"], root=tmp_path) == 1
    assert not any(c[:2] == ["release", "edit"] for c in fake.calls)
    assert "gh release delete v1.2.3" in capsys.readouterr().err


def test_unreadable_notes_file_is_a_clean_stop(tmp_path: Path, fake_run: FakeRun) -> None:
    _fake_repo(tmp_path)
    assert pa.main(["--notes-file", str(tmp_path / "no-existe.md")], root=tmp_path) == 1
    assert fake_run.calls == []
