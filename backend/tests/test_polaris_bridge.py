"""El adaptador de Polaris: dónde escribe, a qué modelo habla y qué dice cuando algo no carga.

Lo que se prueba es el pegamento de EMMA (`app/polaris`), no el código copiado: ese no se toca.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import polaris
from app.api import polaris as polaris_api

# Lo que HOY no importa en Windows, y por qué (polaris/ESTADO.md). Un motivo nuevo es una
# sorpresa que hay que mirar, no un fallo que tolerar.
# `pwd` (2026-10-04, copia 0e629e4): `laminillas_jaulas` y `laminillas_ventanilla`, arrastradas por
# imports, usan los usuarios de Unix. Son de las láminas de su autora; EMMA no las usa.
# `soundfile` salió de aquí el 2026-10-09: era de `transcribe_audios`, que el inventario ya no
# importa (`polaris.NOT_IMPORTED`).
EXPECTED_REASONS = ("No module named 'fcntl'", "No module named 'pwd'")


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(polaris, "state_dir", lambda: tmp_path / "polaris")
    monkeypatch.setattr(polaris, "_configured", False)
    for name in ("BTP_REPO", "BTP_STATE_DIR", "BTP_PERIPHERIES"):
        monkeypatch.delenv(name, raising=False)
    yield tmp_path / "polaris"
    monkeypatch.setattr(polaris, "_configured", False)


def test_the_only_brain_polaris_can_reach_is_local_ollama() -> None:
    registry = polaris.registry()
    brains = registry["cerebros"]
    assert isinstance(brains, list) and len(brains) == 1
    [brain] = brains
    assert brain["name"] == polaris.LOCAL_BRAIN
    assert brain["destino"].startswith("local:") and brain["trusted"] is True
    assert brain["url"].startswith("http://127.0.0.1:") or brain["url"].startswith("http://localhost:")
    # La nota viaja en el fichero que lee Polaris: los cerebros de nube no están «pendientes»,
    # están fuera por decisión del usuario (docs/polaris-divergencias.md §1).
    note = str(registry["_nota"])
    assert "pendiente" not in note and "2026-09-29" in note


def test_polaris_home_and_state_are_emma_directories(isolated: Path) -> None:
    polaris.configure()
    assert Path(os.environ["BTP_REPO"]) == isolated
    assert Path(os.environ["BTP_STATE_DIR"]).is_relative_to(isolated)
    assert Path(os.environ["BTP_PERIPHERIES"]).is_file()
    casa = polaris.load("_casa")
    assert Path(casa.casa_base()) == isolated
    assert Path(casa.state_dir()).is_relative_to(isolated)


def test_a_tool_that_cannot_load_says_why_instead_of_breaking(isolated: Path) -> None:
    with pytest.raises(polaris.PolarisUnavailable, match="no está en la copia"):
        polaris.load("chatgpt")  # no se copió: es un cerebro de nube


def test_every_copied_tool_loads_or_has_a_known_reason(isolated: Path) -> None:
    home = Path.home() / "claudecode"
    existed = home.exists()
    statuses = polaris.inventory()
    assert len(statuses) > 60
    unknown = [
        (status.name, status.reason) for status in statuses
        if status.imported
        and not status.loads
        and not any(r in (status.reason or "") for r in EXPECTED_REASONS)
    ]
    assert not unknown, f"motivos nuevos (mirar y anotar en polaris/ESTADO.md): {unknown}"
    # Importarlo todo no escribe en la casa de su autora.
    assert home.exists() == existed


def test_the_inventory_lists_without_importing_what_does_something_on_import(
    isolated: Path,
) -> None:
    """`NOT_IMPORTED`: en el inventario con su motivo, y sin que nadie las haya importado.

    Que importarlas hace de verdad lo que el motivo dice lo mide `tests/test_soup_polaris.py`, en
    un intérprete aparte; aquí, que la lista es la que el inventario respeta y que no caduca.
    """
    excluded = polaris.NOT_IMPORTED
    assert {"rodaje_muro", "transcribe_audios"} <= set(excluded)
    assert all(len(reason) > 20 for reason in excluded.values()), "un motivo sin escribir"
    tools = {path.stem for path in polaris.tools_dir().glob("*.py")}
    gone = sorted(set(excluded) - tools)
    assert not gone, f"NOT_IMPORTED nombra lo que ya no está en polaris/tools: {gone}"
    # Lo que EMMA llama por su nombre se importa de todos modos: decir de ello «no se importa»
    # sería falso. Si algún día hace falta una de estas, sale de la lista y se mira qué hace.
    both = sorted(set(excluded) & set(polaris_api.EMMA_USES))
    assert not both, f"en EMMA_USES y en NOT_IMPORTED a la vez: {both}"

    # Solo cuenta si no estaban ya importadas por otra prueba del mismo proceso.
    fresh = [name for name in excluded if name not in sys.modules]
    statuses = {status.name: status for status in polaris.inventory()}
    assert set(statuses) == tools
    for name, reason in excluded.items():
        status = statuses[name]
        assert (status.imported, status.loads, status.reason) == (False, False, reason)
    assert {name for name, status in statuses.items() if not status.imported} == set(excluded)
    assert all(status.loads or status.reason for status in statuses.values())
    imported = [name for name in fresh if name in sys.modules]
    assert not imported, f"el inventario importó lo que dice no importar: {imported}"


def test_the_transcription_script_still_runs_whole_when_imported() -> None:
    """El motivo de `transcribe_audios` es que no tiene función de entrada: que siga siendo verdad.

    No se importa para verlo (cargaría un modelo): se lee. Si Polaris le pone un
    `if __name__ == "__main__":`, importarlo dejaría de ejecutarlo y la exclusión se puede revisar.
    """
    source = (polaris.tools_dir() / "transcribe_audios.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "__main__" not in source
    assert any(isinstance(node, ast.For) for node in tree.body), "ya no trabaja a nivel de módulo"


def test_polaris_router_answers_from_local_ollama_and_refuses_clinical_with_it(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ia.ask` de Polaris, tal cual: sin red (`BTP_IA_FAKE`), elige el cerebro local."""
    monkeypatch.setenv("BTP_IA_FAKE", "respuesta de prueba")
    ia = polaris.load("ia")
    routine = ia.ask("resume esto en una frase", clinico=False)
    assert routine["brain"] == polaris.LOCAL_BRAIN and routine["text"] == "respuesta de prueba"
    # Lo clínico exige capacidad ≥ 7 y el registro de Polaris declara 4 para el local: se niega.
    # Decidido que se quede así (docs/polaris-divergencias.md §2): la especificación no deja que
    # el modelo genere acciones clínicas (§63) y EMMA segrega su borrador con firma humana.
    clinical = ia.ask("pregunta clínica", clinico=True)
    assert clinical["parado"] is True and clinical["text"] is None


@pytest.mark.skipif(os.name != "nt", reason="el sustituto de fcntl solo existe en Windows")
def test_the_windows_fcntl_stand_in_locks_like_flock(tmp_path: Path) -> None:
    from app.polaris.compat import fcntl

    path = tmp_path / "cerrojo"
    path.write_text("x")
    with path.open("r+") as first, path.open("r+") as second:
        fcntl.flock(first, fcntl.LOCK_EX)
        with pytest.raises(BlockingIOError):
            fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(first, fcntl.LOCK_UN)
        fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(second, fcntl.LOCK_UN)


def test_the_api_says_which_polaris_tools_load_here(client: TestClient) -> None:
    body = client.get("/api/polaris/estado").json()
    failing, skipped = body["no_cargan"], body["no_se_importan"]
    # Tres recuentos que suman el total: cargan, no cargan y no se importan.
    assert body["total"] > 60
    assert body["cargan"] + len(failing) + len(skipped) == body["total"]
    rows = {row["herramienta"]: row for row in body["herramientas"]}
    assert len(rows) == body["total"]
    assert [name for name, row in rows.items() if row["carga"] is False] == [
        row["herramienta"] for row in failing
    ]
    assert [name for name, row in rows.items() if row["carga"] is None] == [
        row["herramienta"] for row in skipped
    ]
    assert sum(1 for row in rows.values() if row["carga"] is True) == body["cargan"]
    assert all(row["motivo"] for row in rows.values() if not row["carga"])
    assert all(row["motivo"] is None for row in rows.values() if row["carga"])
    # El estado va escrito por el backend (la consola no lo redacta) y dice lo mismo que `carga`.
    words = {True: "carga", False: "no carga", None: "no se importa"}
    assert all(row["estado"] == words[row["carga"]] for row in rows.values())


def test_the_api_says_what_the_inventory_does_not_import_and_why(client: TestClient) -> None:
    body = client.get("/api/polaris/estado").json()
    assert body["no_se_importan"] == [
        {"herramienta": name, "motivo": polaris.NOT_IMPORTED[name]}
        for name in sorted(polaris.NOT_IMPORTED)
    ]
    rows = {row["herramienta"]: row for row in body["herramientas"]}
    for name, reason in polaris.NOT_IMPORTED.items():
        row = rows[name]
        assert (row["carga"], row["estado"], row["motivo"]) == (None, "no se importa", reason)
    # No se cuelan entre las que fallan: de ellas no se ha visto ningún fallo.
    assert not {row["herramienta"] for row in body["no_cargan"]} & set(polaris.NOT_IMPORTED)


def test_the_api_shows_the_copy_as_its_own_files_say(client: TestClient) -> None:
    """Commit, fichas y cambios salen literales de `polaris/`: la ruta no redacta nada."""
    root = polaris.root()
    body = client.get("/api/polaris/estado").json()
    assert body["faltan"] == []
    assert len(body["commit"]) == 40
    assert f"\ncommit {body['commit']}\n" in (root / "ADOPTADO.txt").read_text(encoding="utf-8")

    rows = {row["herramienta"]: row for row in body["herramientas"]}
    card = json.loads((root / "tools" / "fichas" / "borde.py.json").read_text(encoding="utf-8"))
    assert rows["borde"]["ficha"] == card
    # Una herramienta sin ficha (las hay) no rompe ni se le inventa una.
    cards = root / "tools" / "fichas"
    without = [name for name in rows if not (cards / f"{name}.py.json").is_file()]
    assert without and all(rows[name]["ficha"] is None for name in without)
    assert all(rows[name]["ficha"] for name in rows if name not in without)

    changes = json.loads((root / "CAMBIOS.json").read_text(encoding="utf-8"))
    assert changes and body["cambios"] == [
        {
            "ruta": change["ruta"],
            "fecha": change["fecha"],
            "motivo": change["motivo"],
            "reemplazos": len(change["reemplazos"]),
        }
        for change in changes
    ]


def _loads_by_module(folder: str = "app") -> dict[str, set[str]]:
    """Qué ficheros de `backend/<folder>` piden cada herramienta a la copia, leído con `ast`.

    Cuenta `polaris.load("x")` en cualquier módulo, `_tool("x")` (el envoltorio de `timeline`) y
    `load("x")` dentro del propio adaptador. Solo literales: un nombre calculado no se puede atar.
    Las rutas van relativas a `backend/`. Lo usa también `tests/test_soup_polaris.py`, para que
    la ficha de la copia no diga que la llama un módulo que no la llama.
    """
    backend = Path(polaris.__file__).resolve().parents[2]
    adapter = backend / "app" / "polaris"
    found: dict[str, set[str]] = {}
    for path in (backend / folder).rglob("*.py"):
        inside_adapter = path.parent == adapter
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            func, first = node.func, node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            direct = (
                isinstance(func, ast.Attribute)
                and func.attr == "load"
                and isinstance(func.value, ast.Name)
                and func.value.id == "polaris"
            )
            wrapped = isinstance(func, ast.Name) and (
                func.id == "_tool" or (inside_adapter and func.id == "load")
            )
            if direct or wrapped:
                found.setdefault(first.value, set()).add(path.relative_to(backend).as_posix())
    return found


def _loads_in_emma_sources() -> set[str]:
    """Los nombres que `backend/app` pide a la copia."""
    return set(_loads_by_module())


def test_what_emma_declares_it_uses_is_what_its_code_loads(client: TestClient) -> None:
    """`EMMA_USES` viaja como dato (el instalador no lleva fuentes): aquí se ata a las fuentes."""
    declared = set(polaris_api.EMMA_USES)
    assert len(declared) == len(polaris_api.EMMA_USES), "nombre repetido en EMMA_USES"
    assert declared == _loads_in_emma_sources()

    body = client.get("/api/polaris/estado").json()
    used = {row["herramienta"] for row in body["herramientas"] if row["en_uso"]}
    # Todo lo que EMMA llama está en la copia, y lo que solo viaja no se cuenta como usado.
    assert used == declared and body["en_uso"] == len(declared)
    assert 0 < body["en_uso"] < body["total"]


def test_the_api_still_answers_when_the_optional_files_are_missing(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El instalador no lleva `ADOPTADO.txt` ni las fichas: se dice, y lo demás sigue saliendo."""
    real = polaris.root()
    bare = tmp_path / "copia"
    (bare / "tools").mkdir(parents=True)
    monkeypatch.setattr(polaris_api, "_copy_root", lambda: bare)
    body = client.get("/api/polaris/estado").json()
    adopted, cards, changes = "polaris/ADOPTADO.txt", "polaris/tools/fichas", "polaris/CAMBIOS.json"
    assert body["faltan"] == [adopted, cards, changes]
    assert body["commit"] is None and body["cambios"] == []
    assert body["total"] > 60 and all(row["ficha"] is None for row in body["herramientas"])

    # Un fichero estropeado es un fichero que falta, no un 500.
    (bare / "CAMBIOS.json").write_text("{ no es json", encoding="utf-8")
    (bare / "ADOPTADO.txt").write_text("# antes, el commit 7bf4725\nroot kb\n", encoding="utf-8")
    (bare / "tools" / "fichas").mkdir()
    (bare / "tools" / "fichas" / "borde.py.json").write_text("[1, 2]", encoding="utf-8")
    body = client.get("/api/polaris/estado").json()
    assert body["faltan"] == [adopted, changes] and body["commit"] is None
    assert all(row["ficha"] is None for row in body["herramientas"])

    shutil.copy(real / "CAMBIOS.json", bare / "CAMBIOS.json")
    shutil.copy(real / "ADOPTADO.txt", bare / "ADOPTADO.txt")
    body = client.get("/api/polaris/estado").json()
    assert body["faltan"] == [] and body["commit"] and body["cambios"]
