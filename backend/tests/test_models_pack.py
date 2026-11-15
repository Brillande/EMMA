"""El paquete de modelos (`packaging/models_pack.py`): qué lleva de Ollama y de Python.

Lo que se prueba aquí es lo que decide qué entra, sin construir nada real (sin Ollama, sin red).
La construcción entera se comprueba al ejecutar el script: arranca el Ollama del paquete y las
copias de Python antes de escribir el manifiesto.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "models_pack", BACKEND / "packaging" / "models_pack.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["models_pack"] = module
    spec.loader.exec_module(module)
    return module


pack = _load()


def _blob(models: Path, digest: str, content: bytes) -> None:
    path = models / "blobs" / digest.replace(":", "-")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_a_model_takes_its_manifests_and_blobs_and_nothing_else(tmp_path: Path) -> None:
    models = tmp_path
    weights = b"\0" * 1_000_001
    child = json.dumps({"config": {"digest": "sha256:cfg"},
                        "layers": [{"digest": "sha256:w"}]}).encode()
    _blob(models, "sha256:child", child)
    _blob(models, "sha256:cfg", b"{}")
    _blob(models, "sha256:w", weights)
    _blob(models, "sha256:other", weights)  # de otro modelo: no entra
    v2 = models / "manifests-v2" / "ollama.com" / "library" / "gemma4" / "e4b"
    v2.parent.mkdir(parents=True)
    # La variante mlx no está en disco: se lleva lo que hay.
    v2.write_text(json.dumps({"manifests": [{"digest": "sha256:child"},
                                            {"digest": "sha256:mlx"}]}))
    files = {p.relative_to(models).as_posix() for p in pack.model_files(models, "gemma4:e4b")}
    assert files == {
        "manifests-v2/ollama.com/library/gemma4/e4b",
        "blobs/sha256-child", "blobs/sha256-cfg", "blobs/sha256-w",
    }


def test_a_model_without_weights_on_disk_stops_the_build(tmp_path: Path) -> None:
    manifest = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5" / "9b"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"layers": [{"digest": "sha256:missing"}]}))
    with pytest.raises(SystemExit):
        pack.model_files(tmp_path, "qwen3.5:9b")
    with pytest.raises(SystemExit):
        pack.model_files(tmp_path, "not-pulled")


def test_a_model_name_without_tag_is_latest() -> None:
    assert pack.split_name("emma-qwen3.5-9b-v2") == ("emma-qwen3.5-9b-v2", "latest")
    assert pack.split_name("gemma4:12b-it-qat") == ("gemma4", "12b-it-qat")


def test_the_python_copy_leaves_out_system_packages_and_is_isolated(tmp_path: Path) -> None:
    home, venv, out = tmp_path / "home", tmp_path / "venv", tmp_path / "out"
    (home / "Lib" / "site-packages" / "foreign").mkdir(parents=True)
    (home / "Lib" / "site-packages" / "foreign" / "x.py").write_text("")
    (home / "Lib" / "os.py").write_text("")
    (home / "Scripts").mkdir()
    (home / "Scripts" / "pip.exe").write_text("")
    for name in ("python.exe", "python312.dll"):
        (home / name).write_text("")
    (venv / "Lib" / "site-packages" / "whisper").mkdir(parents=True)
    (venv / "Lib" / "site-packages" / "whisper" / "__init__.py").write_text("")
    (venv / "pyvenv.cfg").write_text(f"home = {home}\nversion = 3.12.10\n")

    pack.python_copy(venv, out, link=False)
    assert (out / "python.exe").is_file()
    assert (out / "Lib" / "os.py").is_file()
    assert (out / "Lib" / "site-packages" / "whisper" / "__init__.py").is_file()
    assert not (out / "Lib" / "site-packages" / "foreign").exists()
    assert not (out / "Scripts").exists()
    pth = (out / "python312._pth").read_text(encoding="utf-8").splitlines()
    assert pth == ["DLLs", "Lib", r"Lib\site-packages", "import site"]


def test_the_installer_scripts_travel_with_the_pack() -> None:
    folder = BACKEND / "packaging" / "models_pack"
    for name in ("instalar.ps1", "instalar.cmd", "LEEME.txt"):
        assert (folder / name).is_file()
    # PowerShell 5 lee sin BOM como ANSI: las tildes se romperían.
    assert (folder / "instalar.ps1").read_bytes().startswith(b"\xef\xbb\xbf")
