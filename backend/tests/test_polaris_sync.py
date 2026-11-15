# SPDX-License-Identifier: AGPL-3.0-or-later
"""El guion que hace la copia de Polaris decide bien qué entra, y copia sin tocar un byte.

Por qué existe: `scripts/polaris_sync.py` es quien escribe `polaris/` y su manifiesto, y
`tests/test_polaris_copy.py` solo vigila que lo escrito no se mueva después. Si el guion elige mal
—una prueba que no se pidió, una fixture de más, un fichero viejo que no borra, un salto de línea
convertido—, el manifiesto sale coherente con el error y nada se pone rojo. La octava ronda le
añadió `test <fichero>` y `fichas auto` sin prueba (auditoría del 2026-10-09).

Todo corre sobre un Polaris de pega en `tmp_path`: sin el clon, sin git y sin tocar `polaris/`
(`LIST`, `TARGET`, `MANIFEST` y `CHANGES` se sustituyen). `imported_roots` y `closure` ya los
prueba `tests/test_packaging.py`. Lo que aquí NO se prueba: `extract`, que saca el árbol de los
objetos de git del clon (necesita el clon, que no viaja con EMMA).

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

BACKEND = Path(__file__).resolve().parents[1]

# Bytes que una copia «de texto» estropearía: CRLF, un CR suelto y algo que no es UTF-8.
BINARY = b"\x00\xff\r\n\rfin\n"
LICENSE = b"Licencia de pega\r\ncon saltos de Windows\r\n"


def _load() -> ModuleType:
    """`scripts/` no es un paquete: el guion se carga por su ruta."""
    spec = importlib.util.spec_from_file_location(
        "emma_polaris_sync_under_test", BACKEND / "scripts" / "polaris_sync.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # `dataclass` busca el módulo por su nombre
    spec.loader.exec_module(module)
    return module


sync = _load()


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """Un Polaris de pega: tres herramientas, de las que se copian `a` y `b` (`b` importa `a`)."""
    root = tmp_path / "polaris-de-pega"
    _write(root / "LICENSE", LICENSE)
    _write(root / "tools" / "a.py", "VALUE = 1\n")
    _write(root / "tools" / "b.py", "import a\n")
    _write(root / "tools" / "c.py", "X = 3\n")  # no se copia
    _write(root / "tools" / "datos" / "tabla.json", "{}\n")
    _write(root / "tools" / "datos" / "node_modules" / "pkg" / "index.js", "// instalable\n")
    for name in ("a.py.json", "b.py.json", "c.py.json"):
        _write(root / "tools" / "fichas" / name, "{}\n")
    _write(root / "tools" / "fichas" / "_heredadas.txt", "a\n")
    # Nombra `a.py`, importa `a` y un ayudante, y usa una fixture.
    _write(root / "tests" / "test_a.py", 'import a\nimport _x\nUSA = ("a.py", "usada.bin")\n')
    # No nombra ninguna herramienta entre comillas: la reconoce por el import.
    _write(root / "tests" / "test_b.py", "import b\n")
    # Nombra una herramienta sin copiar.
    _write(root / "tests" / "test_c.py", 'import a\nUSA = "c.py"\n')
    # Importa una herramienta sin copiar, sin nombrarla.
    _write(root / "tests" / "test_importa_c.py", "import c\n")
    # Importa algo que no está instalado.
    _write(root / "tests" / "test_falta.py", 'import paquete_que_emma_no_tiene\nUSA = "a.py"\n')
    # No nombra ni importa ninguna herramienta.
    _write(root / "tests" / "test_nada.py", "import json\n")
    # Prueba algo copiado que no es un `x.py` (un `.js`): solo entra si se pide por su nombre.
    _write(root / "tests" / "test_web.py", 'USA = "datos/tabla.json"\n')
    _write(root / "tests" / "_x.py", "HELPER = True\n")
    _write(root / "tests" / "fixtures" / "usada.bin", BINARY)
    _write(root / "tests" / "fixtures" / "sin_usar.bin", b"nadie la nombra\n")
    _write(root / "tests" / "mutantes" / "a.json", json.dumps({"objetivo": "tools/a.py"}))
    _write(root / "tests" / "mutantes" / "c.json", json.dumps({"objetivo": "tools/c.py"}))
    return root


@pytest.fixture
def target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """La carpeta de la copia, de pega y con restos de una copia anterior. Nunca `polaris/`."""
    root = tmp_path / "copia"
    monkeypatch.setattr(sync, "TARGET", root)
    monkeypatch.setattr(sync, "LIST", root / "ADOPTADO.txt")
    monkeypatch.setattr(sync, "MANIFEST", root / "MANIFEST.sha256")
    monkeypatch.setattr(sync, "CHANGES", root / "CAMBIOS.json")
    _write(root / "ADOPTADO.txt", LIST_TEXT)
    _write(root / "ORIGEN.md", "origen\n")
    _write(root / "ESTADO.md", "estado\n")
    _write(root / "PRUEBAS.md", "pruebas\n")
    _write(root / "tools" / "viejo.py", "# de una copia anterior\n")
    _write(root / "tools" / "vacia" / "resto.txt", "sobra, y su carpeta con él\n")
    _write(root / "tools" / "datos" / "node_modules" / "pkg" / "index.js", "// local\n")
    _write(root / "tools" / "__pycache__" / "a.cpython-312.pyc", b"\x00")
    return root


LIST_TEXT = """\
# La lista de pega. Una línea de comentario no es una entrada.
commit abc1234

root b                 # arrastra `a` por imports
data datos
extra LICENSE
tests auto
fichas auto
test test_web.py       # prueba un .json, no una herramienta `x.py`
"""

ADOPTED = {
    "commit": "abc1234", "roots": ["b"], "data": ["datos"], "extra": ["LICENSE"],
    "tests": True, "named_tests": ["test_web.py"], "cards": True,
}

# Lo que se copia del árbol de pega con esa lista, en el orden del manifiesto.
WANTED = [
    "tools/a.py",
    "tools/b.py",
    "tools/datos/tabla.json",
    "LICENSE",
    "tests/test_a.py",
    "tests/test_b.py",
    "tests/test_web.py",
    "tests/_x.py",
    "tests/fixtures/usada.bin",
    "tests/mutantes/a.json",
    "tools/fichas/a.py.json",
    "tools/fichas/b.py.json",
    "tools/fichas/_heredadas.txt",
]
# Lo que `sync` no toca aunque no venga de Polaris.
SPARED = [
    "ADOPTADO.txt", "ORIGEN.md", "ESTADO.md", "PRUEBAS.md",
    "tools/datos/node_modules/pkg/index.js", "tools/__pycache__/a.cpython-312.pyc",
]


def _adopted(**overrides: object) -> object:
    return sync.Adopted(**{**ADOPTED, **overrides})


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _dirs(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir()}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- read_list ----------------------------------------------------------------------------------


def test_read_list_reads_every_kind_of_entry(target: Path) -> None:
    adopted = sync.read_list()

    assert {name: getattr(adopted, name) for name in ADOPTED} == ADOPTED


@pytest.mark.parametrize(
    "line", ["herramienta a", "tests manual", "fichas todas", "root", "root a b", "root a b  # c"]
)
def test_read_list_aborts_on_an_unknown_entry(target: Path, line: str) -> None:
    _write(target / "ADOPTADO.txt", LIST_TEXT + line + "\n")

    with pytest.raises(SystemExit, match="entrada desconocida"):
        sync.read_list()


def test_read_list_aborts_without_a_commit(target: Path) -> None:
    _write(target / "ADOPTADO.txt", LIST_TEXT.replace("commit abc1234\n", ""))

    with pytest.raises(SystemExit, match="commit"):
        sync.read_list()


# --- qué pruebas entran ---------------------------------------------------------------------------


def test_eligible_tests_are_those_that_only_use_what_is_copied(source: Path) -> None:
    # `test_a` nombra `a.py`; `test_b` solo importa `b`. Fuera: la que nombra `c.py`, la que
    # importa `c`, la que importa algo sin instalar y la que no prueba ninguna herramienta
    # (`test_nada`, `test_web`).
    assert sync.eligible_tests(source, {"a", "b"}) == ["test_a.py", "test_b.py"]


def test_eligible_tests_follow_what_is_copied(source: Path) -> None:
    assert sync.eligible_tests(source, {"a", "b", "c"}) == [
        "test_a.py", "test_b.py", "test_c.py", "test_importa_c.py",
    ]
    assert sync.eligible_tests(source, {"a"}) == ["test_a.py"]


def test_named_tests_abort_when_the_file_does_not_exist(source: Path) -> None:
    with pytest.raises(SystemExit, match="test_no_existe.py"):
        sync.named_tests(source, ["test_web.py", "test_no_existe.py"])


def test_a_named_test_enters_even_if_not_eligible(source: Path) -> None:
    assert "test_web.py" not in sync.eligible_tests(source, {"a", "b"})

    _, _, tests = sync.files_of(source, _adopted())
    assert tests == ["test_a.py", "test_b.py", "test_web.py"]

    # Sin `tests auto`, solo las pedidas.
    _, _, tests = sync.files_of(source, _adopted(tests=False))
    assert tests == ["test_web.py"]


def test_a_test_named_and_eligible_is_copied_once(source: Path) -> None:
    wanted, _, tests = sync.files_of(source, _adopted(named_tests=["test_a.py", "test_web.py"]))

    assert tests == ["test_a.py", "test_b.py", "test_web.py"]
    assert [path.as_posix() for path in wanted].count("tests/test_a.py") == 1


def test_a_missing_named_test_aborts_the_whole_listing(source: Path) -> None:
    with pytest.raises(SystemExit, match="test_no_existe.py"):
        sync.files_of(source, _adopted(named_tests=["test_no_existe.py"]))


# --- lo que acompaña a las pruebas y las fichas ---------------------------------------------------


def test_support_is_helpers_named_fixtures_and_campaigns_of_what_is_copied(source: Path) -> None:
    support = sync.test_support(source, ["test_a.py", "test_b.py"], {"a", "b"})

    assert [path.as_posix() for path in support] == [
        "tests/_x.py", "tests/fixtures/usada.bin", "tests/mutantes/a.json",
    ]


def test_helpers_travel_even_if_no_chosen_test_imports_them(source: Path) -> None:
    support = sync.test_support(source, ["test_b.py"], {"b"})

    # Ni la fixture (nadie la nombra ya) ni la campaña de `a` (ya no se copia): solo el ayudante.
    assert [path.as_posix() for path in support] == ["tests/_x.py"]


def test_cards_are_only_those_of_copied_tools_plus_the_inherited_list(source: Path) -> None:
    copied = [Path("tools/a.py"), Path("tools/datos/tabla.json"), Path("tests/test_a.py")]

    assert [path.as_posix() for path in sync.cards_for(source, copied)] == [
        "tools/fichas/a.py.json", "tools/fichas/_heredadas.txt",
    ]


def test_cards_without_inherited_list_or_card(source: Path) -> None:
    (source / "tools" / "fichas" / "_heredadas.txt").unlink()
    (source / "tools" / "fichas" / "a.py.json").unlink()

    assert sync.cards_for(source, [Path("tools/a.py"), Path("tools/b.py")]) == [
        Path("tools/fichas/b.py.json"),
    ]


def test_files_of_lists_exactly_what_the_list_asks_for(source: Path) -> None:
    wanted, modules, _ = sync.files_of(source, _adopted())

    assert [path.as_posix() for path in wanted] == WANTED
    assert modules == {"a", "b"}


def test_cards_and_tests_are_opt_in(source: Path) -> None:
    wanted, _, tests = sync.files_of(source, _adopted(tests=False, named_tests=[], cards=False))

    assert tests == []
    assert [path.as_posix() for path in wanted] == WANTED[:4]


def test_a_data_or_extra_entry_that_does_not_exist_aborts(source: Path) -> None:
    with pytest.raises(SystemExit, match="no_esta"):
        sync.files_of(source, _adopted(data=["no_esta"]))
    with pytest.raises(SystemExit, match="NOTICE"):
        sync.files_of(source, _adopted(extra=["NOTICE"]))


# --- sync, de punta a punta -----------------------------------------------------------------------


def test_sync_copies_byte_for_byte_and_removes_leftovers(source: Path, target: Path) -> None:
    spared = {name: (target / name).read_bytes() for name in SPARED}

    sync.sync(source, sync.read_list())

    tree = _tree(target)
    assert set(tree) == {*WANTED, *SPARED, "MANIFEST.sha256"}
    for name in WANTED:
        assert tree[name] == (source / name).read_bytes(), name
    assert tree["tests/fixtures/usada.bin"] == BINARY
    assert tree["LICENSE"] == LICENSE
    # Los ficheros de EMMA y lo instalable siguen como estaban.
    assert {name: tree[name] for name in SPARED} == spared
    # La carpeta que se quedó vacía al borrar su resto también se va.
    assert "tools/vacia" not in _dirs(target)


def test_sync_writes_the_manifest_of_what_it_copied(source: Path, target: Path) -> None:
    sync.sync(source, sync.read_list())

    raw = (target / "MANIFEST.sha256").read_bytes()
    assert b"\r" not in raw  # saltos de Unix también en Windows: el manifiesto no depende de dónde
    lines = raw.decode("utf-8").splitlines()
    assert lines[0].startswith("#") and "abc1234" in lines[0]
    assert lines[1:] == [f"{_sha((source / name).read_bytes())}  {name}" for name in WANTED]
    assert raw.endswith(b"\n")


def test_sync_twice_changes_nothing(source: Path, target: Path) -> None:
    _write(target / "CAMBIOS.json", json.dumps([CHANGE]))
    sync.sync(source, sync.read_list())
    first, first_dirs = _tree(target), _dirs(target)

    sync.sync(source, sync.read_list())

    assert _tree(target) == first
    assert _dirs(target) == first_dirs


# --- los cambios decididos (CAMBIOS.json, AGPL §5a) -----------------------------------------------

CHANGE = {
    "ruta": "tools/a.py", "fecha": "2026-10-09", "motivo": "de pega",
    "reemplazos": [{"viejo": "VALUE = 1", "nuevo": "VALUE = 2"}],
}


def test_sync_applies_a_decided_change_and_records_the_original(
    source: Path, target: Path
) -> None:
    _write(target / "CAMBIOS.json", json.dumps([CHANGE]))

    sync.sync(source, sync.read_list())

    changed = (target / "tools" / "a.py").read_bytes()
    assert changed == b"VALUE = 2\n"
    assert (source / "tools" / "a.py").read_bytes() == b"VALUE = 1\n"  # el origen no se toca
    lines = (target / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    original = _sha(b"VALUE = 1\n")
    assert f"{_sha(changed)}  tools/a.py  # cambiado; original {original}" in lines
    # Los demás, sin marca.
    assert sum("cambiado" in line for line in lines[1:]) == 1


def test_a_change_to_a_file_that_is_not_copied_aborts(source: Path, target: Path) -> None:
    _write(target / "CAMBIOS.json", json.dumps([{**CHANGE, "ruta": "tools/c.py"}]))

    with pytest.raises(SystemExit, match="tools/c.py"):
        sync.sync(source, sync.read_list())


@pytest.mark.parametrize("missing", ["ruta", "fecha", "motivo", "reemplazos"])
def test_a_change_without_its_reason_aborts(target: Path, missing: str) -> None:
    _write(target / "CAMBIOS.json", json.dumps([{**CHANGE, missing: ""}]))

    with pytest.raises(SystemExit, match="CAMBIOS.json"):
        sync.decided_changes()


def test_no_changes_file_means_no_changes(target: Path) -> None:
    assert sync.decided_changes() == {}


@pytest.mark.parametrize(
    ("text", "count"), [("otra cosa\n", 0), ("VALUE = 1\nVALUE = 1\n", 2)]
)
def test_apply_changes_aborts_unless_the_old_text_is_there_once(
    tmp_path: Path, text: str, count: int
) -> None:
    path = tmp_path / "a.py"
    _write(path, text)

    with pytest.raises(SystemExit, match=f"aparece {count} veces"):
        sync.apply_changes(path, [{"viejo": "VALUE = 1", "nuevo": "VALUE = 2"}])

    assert path.read_bytes() == text.encode("utf-8")  # y no deja el fichero a medias


def test_apply_changes_keeps_the_line_endings_of_the_original(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    _write(path, b"VALUE = 1\r\nOTRA = 1\n")

    sync.apply_changes(path, [{"viejo": "VALUE = 1", "nuevo": "VALUE = 2"}])

    assert path.read_bytes() == b"VALUE = 2\r\nOTRA = 1\n"
