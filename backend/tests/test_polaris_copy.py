"""La carpeta `polaris/` es copia literal de Polaris, salvo los cambios decididos y declarados.

Regla del proyecto (CLAUDE.md): adoptar Polaris es copiarlo tal cual y decidir los cambios
después. Esta prueba la impone: editar un fichero copiado, borrarlo o dejar uno sin declarar hace
fallar la suite. Un cambio solo vale si el usuario lo decidió y está en `polaris/CAMBIOS.json`
(lo aplica `scripts/polaris_sync.py`), en `polaris/ORIGEN.md` y dentro del propio fichero.

También vigila los dos documentos de EMMA que describen la copia, porque ya se quedaron atrás una
vez: tras pasar a `0e629e4`, `ORIGEN.md` seguía citando el commit anterior y `ESTADO.md` contaba
91 herramientas donde había 103. Un documento que describe otra copia es peor que no tenerlo.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POLARIS = REPO / "polaris"
EMMA_FILES = {
    "ADOPTADO.txt", "MANIFEST.sha256", "ORIGEN.md", "ESTADO.md", "PRUEBAS.md", "CAMBIOS.json",
}
# Lo único generado que puede vivir dentro de la copia es el bytecode. Ninguna carpeta se exime por
# nombre: ignorar cualquiera llamada `state` dejó pasar `tools/state/enruta_salud.json`, estado que
# una herramienta escribió aquí al ejecutarse sin el adaptador. Tampoco por ruta: el visor web se
# compila fuera (`frontend/scripts/build-polaris.mjs`), así que un `node_modules` o un `dist` en
# `tools/visor3d_web/` es un resto y hace fallar la prueba.
BYTECODE_DIR = "__pycache__"  # lo deja Python al importar, en cualquier carpeta con módulos
CHANGED_MARK = "# cambiado; original"


def manifest_lines() -> list[str]:
    return (POLARIS / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()


def manifest() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in manifest_lines():
        if line and not line.startswith("#"):
            digest, path = line.split("  ")[:2]
            entries[path] = digest
    return entries


def adopted_commit() -> str:
    adopted = (POLARIS / "ADOPTADO.txt").read_text(encoding="utf-8")
    [commit] = [line.split()[1] for line in adopted.splitlines() if line.startswith("commit ")]
    return commit


def is_generated(relative: Path) -> bool:
    """Si la ruta es bytecode: lo único generado que se tolera dentro de la copia."""
    return BYTECODE_DIR in relative.parts


def copy_tree() -> tuple[set[str], set[str]]:
    """Ficheros y carpetas presentes en `polaris/`, sin lo generado."""
    files: set[str] = set()
    dirs: set[str] = set()
    for path in POLARIS.rglob("*"):
        relative = path.relative_to(POLARIS)
        if is_generated(relative):
            continue
        (dirs if path.is_dir() else files).add(relative.as_posix())
    return files, dirs


def test_every_copied_file_matches_the_manifest() -> None:
    entries = manifest()
    assert entries, "el manifiesto está vacío"
    changed = [
        path for path, digest in entries.items()
        if not (POLARIS / path).is_file()
        or hashlib.sha256((POLARIS / path).read_bytes()).hexdigest() != digest
    ]
    assert not changed, f"cambiados o ausentes (decidir y anotar en CAMBIOS.json): {changed}"


def test_nothing_lives_in_the_copy_that_polaris_did_not_ship() -> None:
    present, _ = copy_tree()
    extra = present - EMMA_FILES - set(manifest())
    assert not extra, f"ficheros que Polaris no trae (el estado va fuera): {sorted(extra)}"


def test_no_directory_lives_in_the_copy_that_polaris_did_not_ship() -> None:
    """Una carpeta sobrante también es estado ajeno, aunque esté vacía.

    Mirar solo ficheros dejó pasar `00_FUENTE-DE-VERDAD/00 · Bandeja de entrada/`, creada vacía por
    una herramienta que tomó `polaris/` por su casa.
    """
    _, present = copy_tree()
    shipped = {
        parent.as_posix()
        for path in manifest()
        for parent in Path(path).parents
        if parent != Path(".")
    }
    extra = present - shipped
    assert not extra, f"carpetas que Polaris no trae: {sorted(extra)}"


def test_every_change_to_the_copy_was_decided_and_is_declared() -> None:
    """Lo único distinto del original es lo de `CAMBIOS.json`, y cada fichero lo avisa (AGPL §5a).

    El manifiesto marca los ficheros cambiados con la huella de su original; cada uno tiene que
    estar en `CAMBIOS.json` (con fecha y motivo), en la sección "Cambios" de `ORIGEN.md` y llevar
    dentro el aviso de que EMMA lo modificó.
    """
    lines = manifest_lines()
    assert adopted_commit() in lines[0]
    changed = {line.split("  ")[1] for line in lines[1:] if CHANGED_MARK in line}
    decided = json.loads((POLARIS / "CAMBIOS.json").read_text(encoding="utf-8"))
    assert changed == {entry["ruta"] for entry in decided}
    assert all(entry["fecha"] and entry["motivo"] for entry in decided)
    section = (POLARIS / "ORIGEN.md").read_text(encoding="utf-8").split("## Cambios", 1)[1]
    for path in changed:
        assert f"`{path}`" in section, path
        assert "Modificado por EMMA" in (POLARIS / path).read_text(encoding="utf-8"), path


def test_the_copy_keeps_polaris_legal_notices_but_never_its_assistant_instructions() -> None:
    """Sus avisos legales viajan con el código (AGPL). Sus instrucciones de asistente, no.

    `CLAUDE.md`/`AGENTS.md` de Polaris son reglas para el asistente de su autora: Claude Code las
    cargaría al trabajar dentro de `polaris/` y se mezclarían con las de EMMA.
    """
    for notice in ("LICENSE", "NOTICE", "CITATION.cff"):
        assert (POLARIS / notice).is_file(), notice
    leaked = [p.relative_to(POLARIS).as_posix() for p in POLARIS.rglob("*")
              if p.name in {"CLAUDE.md", "AGENTS.md"}]
    assert not leaked, f"instrucciones de asistente dentro de la copia: {leaked}"


def test_origen_cites_the_adopted_commit_and_no_other_as_current() -> None:
    """`ORIGEN.md` es el aviso de procedencia (AGPL §5a): tiene que nombrar el commit copiado.

    Los commits anteriores se citan abreviados, como historia; entero solo va el vigente, así que
    cualquier otro hash completo en la cabecera es un commit viejo que nadie actualizó.
    """
    header = (POLARIS / "ORIGEN.md").read_text(encoding="utf-8").split("## Cambios", 1)[0]
    assert set(re.findall(r"\b[0-9a-f]{40}\b", header)) == {adopted_commit()}


def test_estado_describes_the_tools_that_are_in_the_copy() -> None:
    """`ESTADO.md` cuenta y nombra exactamente los módulos de `tools/`.

    Cuáles cargan depende de la máquina y no se comprueba aquí (lo hace `test_polaris_bridge.py`);
    que estén todos y ninguno de más, no: si falla, corre `scripts/polaris_estado.py`.
    """
    tools = {path.stem for path in (POLARIS / "tools").glob("*.py")}
    state = (POLARIS / "ESTADO.md").read_text(encoding="utf-8")
    counted = re.search(r"\*\*(\d+) de (\d+) herramientas cargan\.\*\*", state)
    assert counted, "ESTADO.md no lleva el recuento que escribe scripts/polaris_estado.py"
    loading, total = int(counted[1]), int(counted[2])
    assert total == len(tools), "ESTADO.md es de otra copia: corre scripts/polaris_estado.py"
    failing = set(re.findall(r"^\| `(\w+)` \|", state, flags=re.MULTILINE))
    [listed] = re.findall(r"^Cargan: (.*)\.$", state, flags=re.MULTILINE)
    loaded = set(re.findall(r"`(\w+)`", listed))
    assert (len(loaded), len(failing)) == (loading, total - loading)
    assert loaded | failing == tools
