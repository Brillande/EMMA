"""El traspaso de una actualización, del backend al proceso principal de escritorio.

El backend baja el instalador por `app/core/egress.py` y deja `listo.json` e `instalar.json` en la
carpeta de actualización; `desktop/main.cjs` lo lanza tras comprobarlo con
`desktop/update-handoff.cjs`. Lo que no se puede romper sin que nadie lo note en la suite: que el
proceso principal no salga a internet (invariante 3 bis), que el SHA-256 se mida otra vez antes de
ejecutar nada, que el instalador se lance como actualización (conserva el perfil, ver el comentario
de `main.cjs`) y que en desarrollo no se instale encima. `main.cjs` se lee como texto, igual que en
`test_packaging.py`; las funciones puras del módulo se ejecutan con `node` si está.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DESKTOP = REPO / "desktop"
MAIN = DESKTOP / "main.cjs"
HANDOFF = DESKTOP / "update-handoff.cjs"

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="sin node en el PATH")

# Cualquier forma de salir a la red desde JavaScript, también `electron-updater` (se saltaría
# `egress.py`). El nombre sí puede salir en un comentario que explica por qué no se usa.
NETWORK = re.compile(
    r"""require\(\s*["'](?:node:)?(?:https?|net|http2|dgram|tls|electron-updater)["']\s*\)"""
    r"""|\bfetch\s*\(|net\.request|autoUpdater|\bhttps?\.(?:get|request)\s*\("""
)


def main_source() -> str:
    return MAIN.read_text(encoding="utf-8")


def update_section() -> str:
    """El código de la actualización en `main.cjs`: de su cabecera a `async function main`."""
    source = main_source()
    start = source.index("// --- La actualización")
    end = source.index("async function main()", start)
    return source[start:end]


def test_the_backend_gets_the_version_and_the_folder() -> None:
    source = main_source()
    assert "EMMA_APP_VERSION: app.getVersion()" in source
    assert "EMMA_UPDATE_DIR:" in source
    assert re.search(r'path\.join\(app\.getPath\("userData"\),\s*"actualizacion"\)', source)
    # La carpeta se crea antes de arrancar el backend.
    assert "fs.mkdirSync(updates, { recursive: true })" in source


def test_the_installer_hash_is_measured_again_here() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    assert 'createHash("sha256")' in handoff
    assert "createReadStream" in handoff  # por trozos: el instalador pesa cientos de MB
    assert 'require("./update-handoff.cjs")' in main_source()
    assert "handoff.validateHandoff(" in update_section()


def test_the_installer_runs_silent_as_an_update() -> None:
    section = update_section()
    assert re.search(r'INSTALLER_ARGS = \["/S", "--updated", "--force-run"\]', section)
    assert re.search(r"detached:\s*true", section)
    assert re.search(r'stdio:\s*"ignore"', section)
    assert "child.unref()" in section
    assert "app.quit()" in section


def test_neither_main_nor_the_handoff_go_to_the_network() -> None:
    assert not NETWORK.search(update_section())
    assert not NETWORK.search(HANDOFF.read_text(encoding="utf-8"))
    assert not re.search(r"""require\(\s*["']electron-updater""", main_source())
    package = json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    assert "electron-updater" not in deps


def test_the_module_travels_in_the_package() -> None:
    package = json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))
    assert "update-handoff.cjs" in package["build"]["files"]


def test_only_the_packaged_app_launches_the_installer() -> None:
    section = update_section()
    guard = section.index("if (!app.isPackaged)")
    launch = section.index("launchInstaller(result.exe")
    assert guard < launch
    # La rama de desarrollo vuelve antes de lanzar.
    assert "return;" in section[guard:launch]
    # Solo hay una llamada que lance el instalador, y es la de después de la guarda.
    assert section.count("launchInstaller(result.exe") == 1


def test_one_flag_keeps_it_from_launching_twice_and_before_quit_stops_once() -> None:
    source = main_source()
    assert "if (updating || quitting) return;" in update_section()
    assert "if (servicesStopped) return;" in source
    before_quit = source[source.index('app.on("before-quit"'):]
    before_quit = before_quit[: before_quit.index("});")]
    assert "stopServices()" in before_quit


# --- Las funciones puras, con node ------------------------------------------------------------


def run_node(script: str) -> object:
    assert NODE is not None
    result = subprocess.run(
        [NODE, "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def node_require() -> str:
    return f"const h = require({json.dumps(str(HANDOFF))});"


@needs_node
def test_file_names() -> None:
    names = [
        "EMMA.Setup.0.2.0.exe",
        "EMMA.Setup.0.2.0.EXE",
        "../EMMA.Setup.0.2.0.exe",
        "..\\EMMA.exe",
        "sub/EMMA.exe",
        "sub\\EMMA.exe",
        "C:EMMA.exe",
        "EMMA.exe:flujo",
        "EMMA.Setup.0.2.0.msi",
        "EMMA.exe.",
        "EMMA.exe ",
        "..",
        "",
        "a..exe",
        "NUL.exe",
        "com1.exe",
    ]
    got = run_node(
        f"{node_require()} console.log(JSON.stringify({json.dumps(names)}.map(h.isSafeFileName)))"
    )
    assert got == [True, True] + [False] * 14


@needs_node
def test_versions() -> None:
    pairs = [
        ["0.2.0", "0.1.4"],
        ["v0.2.0", "0.1.4"],
        ["0.1.10", "0.1.9"],
        ["1.0.0", "0.99.99"],
        ["0.1.4", "0.1.4"],
        ["0.1.3", "0.1.4"],
        ["0.2", "0.1.4"],
        ["0.2.0-beta", "0.1.4"],
        ["01.2.0", "0.1.4"],
        [None, "0.1.4"],
    ]
    script = (
        f"{node_require()} console.log(JSON.stringify({json.dumps(pairs)}"
        ".map(([a, b]) => h.isNewerVersion(a, b))))"
    )
    assert run_node(script) == [True, True, True, True, False, False, False, False, False, False]


def write_handoff(
    folder: Path,
    *,
    request: dict[str, object] | None = None,
    ready: dict[str, object] | None = None,
    content: bytes = b"MZ instalador falso",
) -> None:
    name = "EMMA.Setup.0.2.0.exe"
    (folder / name).write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    base_ready = {"version": "0.2.0", "file": name, "sha256": digest, "size": len(content)}
    base_request = {
        "version": "0.2.0", "file": name, "sha256": digest, "requested_at": "2026-11-16T10:00:00Z",
    }
    listo = json.dumps({**base_ready, **(ready or {})})
    instalar = json.dumps({**base_request, **(request or {})})
    (folder / "listo.json").write_text(listo, encoding="utf-8")
    (folder / "instalar.json").write_text(instalar, encoding="utf-8")


def validate(folder: Path, current: str = "0.1.4") -> dict[str, object]:
    script = (
        f"{node_require()} h.validateHandoff({json.dumps(str(folder))}, {json.dumps(current)})"
        ".then((r) => console.log(JSON.stringify(r)))"
    )
    got = run_node(script)
    assert isinstance(got, dict)
    return got


@needs_node
def test_a_good_handoff_is_accepted(tmp_path: Path) -> None:
    write_handoff(tmp_path)
    got = validate(tmp_path)
    assert got["ok"] is True, got
    assert Path(str(got["exe"])) == tmp_path / "EMMA.Setup.0.2.0.exe"


@needs_node
@pytest.mark.parametrize(
    ("request_", "ready", "current", "why"),
    [
        ({"sha256": "0" * 64}, {"sha256": "0" * 64}, "0.1.4", "sha256 del instalador"),
        ({"sha256": "0" * 64}, None, "0.1.4", "listo.json"),
        ({"file": "../EMMA.Setup.0.2.0.exe"}, None, "0.1.4", "nombre"),
        (None, None, "0.2.0", "posterior"),
        (None, None, "0.3.0", "posterior"),
        ({"version": "0.2.1"}, None, "0.1.4", "otra versión"),
        ({"file": "otro.exe"}, None, "0.1.4", "otro fichero"),
        (None, {"size": 1}, "0.1.4", "tamaño"),
        ({"sha256": "no-es-un-hash"}, None, "0.1.4", "mal formado"),
    ],
)
def test_a_bad_handoff_is_refused(tmp_path: Path, request_: dict[str, object] | None,
                                  ready: dict[str, object] | None, current: str, why: str) -> None:
    write_handoff(tmp_path, request=request_, ready=ready)
    got = validate(tmp_path, current)
    assert got["ok"] is False
    assert why in str(got["reason"])


@needs_node
def test_a_missing_or_broken_request_is_refused(tmp_path: Path) -> None:
    write_handoff(tmp_path)
    (tmp_path / "instalar.json").write_text("{no es json", encoding="utf-8")
    assert validate(tmp_path)["ok"] is False
    (tmp_path / "instalar.json").unlink()
    assert validate(tmp_path)["ok"] is False
