"""Los textos de EMMA sobre la copia de Polaris dicen lo que hay en el código.

Por qué existe: son avisos de procedencia (AGPL §5a) y se escribieron a mano, así que se quedan
atrás sin que nada lo note. El 2026-10-08 `polaris/ORIGEN.md` y `polaris/ESTADO.md` solo nombraban
`compat/fcntl.py` cuando la carpeta ya tenía cinco módulos, y la tabla «llaman a la copia» de
`NOTICE` callaba dos funciones de `visor3d` que `app/volumes/geometry.py` llama (`_caja_de` y
`_diametro_axial_mayor`), además de otras de otras herramientas. Aquí los textos se atan a su
fuente:

  * Cada módulo de `backend/app/polaris/compat/` está nombrado en `ORIGEN.md`, en `ESTADO.md` y
    en `NOTICE`; y la lista de `ESTADO.md` es la que escribe hoy `scripts/polaris_estado.py`.
  * De cada herramienta de la tabla de `NOTICE`, los nombres entre paréntesis son exactamente los
    atributos que el código de EMMA le pide, fichero a fichero. Se lee con `ast`, como
    `tests/test_polaris_bridge.py` lee `EMMA_USES`.

Lo que NO ve el lector: un módulo de la copia pasado como argumento a otra función, o guardado en
un atributo. Hoy ninguna herramienta de la tabla se usa así; si pasa, la tabla quedará corta sin
que esto falle. Tampoco juzga si las frases de alrededor son ciertas: solo los nombres.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

from app import polaris

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
COMPAT = BACKEND / "app" / "polaris" / "compat"
ADAPTER = BACKEND / "app" / "polaris"
BULLET = re.compile(r"^- `backend/app/polaris/compat/(\w+\.py)`: .+$", flags=re.MULTILINE)
COMPUTED = "<calculado>"


def _estado_script() -> ModuleType:
    """`scripts/` no es un paquete: el guion se carga por su ruta."""
    spec = importlib.util.spec_from_file_location(
        "polaris_estado_script", BACKEND / "scripts" / "polaris_estado.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compat_modules() -> list[str]:
    return sorted(path.name for path in COMPAT.glob("*.py"))


# --- compat/ ------------------------------------------------------------------------------


def test_the_compat_folder_is_the_one_the_texts_talk_about() -> None:
    """Si la carpeta se moviera, las pruebas de abajo pasarían sin mirar nada."""
    assert {"fcntl.py", "memguard.py", "resource.py"} <= set(_compat_modules())


def test_origen_names_every_compat_module() -> None:
    text = (REPO / "polaris" / "ORIGEN.md").read_text(encoding="utf-8")
    glue = text.split("## Pegamento de EMMA", 1)[1].split("## Cambios", 1)[0]
    missing = [name for name in _compat_modules() if f"`compat/{name}`" not in glue]
    assert not missing, f"polaris/ORIGEN.md no nombra en su sección de pegamento: {missing}"
    stale = sorted(set(re.findall(r"`compat/(\w+\.py)`", glue)) - set(_compat_modules()))
    assert not stale, f"polaris/ORIGEN.md nombra módulos de compat/ que ya no existen: {stale}"


def test_notice_names_every_compat_module() -> None:
    text = (REPO / "NOTICE").read_text(encoding="utf-8")
    missing = [name for name in _compat_modules() if f"compat/{name}" not in text]
    assert not missing, f"NOTICE no nombra: {missing}"
    stale = sorted(set(re.findall(r"\bcompat/(\w+\.py)", text)) - set(_compat_modules()))
    assert not stale, f"NOTICE nombra módulos de compat/ que ya no existen: {stale}"


def test_estado_lists_the_compat_folder_as_its_script_writes_it_today() -> None:
    """`ESTADO.md` se genera: su lista de `compat/` tiene que ser la del guion y la de la carpeta.

    Si falla, corre `scripts/polaris_estado.py` (no se edita a mano).
    """
    script = _estado_script()
    rendered = script.render(
        [polaris.ToolStatus("a", True, None), polaris.ToolStatus("b", False, "motivo")]
    )
    written = (REPO / "polaris" / "ESTADO.md").read_text(encoding="utf-8")
    assert BULLET.findall(rendered) == _compat_modules(), "el guion no lista la carpeta entera"
    in_render = [match.group(0) for match in BULLET.finditer(rendered)]
    in_file = [match.group(0) for match in BULLET.finditer(written)]
    assert in_file == in_render, "ESTADO.md es de otra carpeta compat/: corre el guion"
    # Cada línea dice algo del módulo (la primera línea de su docstring), no solo su nombre.
    assert all(len(line.split(": ", 1)[1]) > 20 for line in in_render)
    # Y el resto del fichero sigue siendo el que el guion escribe.
    assert "**1 de 2 herramientas cargan.**" in rendered and "| `b` | motivo |" in rendered
    assert "\nCargan: `a`.\n" in rendered
    # Sin nada excluido del inventario, no hay segunda tabla.
    assert "No se importan" not in rendered


def test_estado_tells_apart_what_fails_to_load_from_what_is_not_imported() -> None:
    """Lo que el inventario no importa (`polaris.NOT_IMPORTED`) no se cuenta como fallo de carga.

    Va en su propia tabla, con su motivo, y no entra ni en «cargan» ni en la tabla de las que no.
    """
    rendered = _estado_script().render(
        [
            polaris.ToolStatus("a", True, None),
            polaris.ToolStatus("b", False, "motivo"),
            polaris.ToolStatus("c", False, "hace algo al importarse", imported=False),
        ]
    )
    assert "**1 de 3 herramientas cargan.**" in rendered
    assert "**No se importan para hacer este inventario: 1.**" in rendered
    failing, skipped = rendered.split("**No se importan", 1)
    assert "| `b` | motivo |" in failing and "`c`" not in failing
    assert "| `c` | hace algo al importarse |" in skipped and "| `b` |" not in skipped
    assert "\nCargan: `a`.\n" in skipped


# --- la tabla «llaman a la copia» de NOTICE -------------------------------------------------


def _literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def attributes_taken(source: str, inside_adapter: bool = False) -> dict[str, set[str]]:
    """Qué atributos pide un módulo a cada herramienta de la copia: `{herramienta: {nombres}}`.

    Reconoce cómo llega EMMA a una herramienta: `polaris.load("x")` (y `load("x")` dentro del
    adaptador), una función que lo devuelve (`def _tool(): return polaris.load("x")`), una que
    carga el nombre que le dan (`_tool("x")`, la de `timeline`), y una variable a la que se asigna
    cualquiera de esas. Los nombres de variable se miran por fichero, no por función: uno que
    valga dos herramientas distintas en el mismo fichero es un error, no una duda.
    """
    tree = ast.parse(source)
    variables: dict[str, str] = {}
    getters: dict[str, str] = {}
    passthrough: set[str] = set()

    def is_load(func: ast.AST) -> bool:
        direct = (
            isinstance(func, ast.Attribute)
            and func.attr == "load"
            and isinstance(func.value, ast.Name)
            and func.value.id == "polaris"
        )
        return direct or (inside_adapter and isinstance(func, ast.Name) and func.id == "load")

    def tool_of(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return variables.get(node.id)
        if not isinstance(node, ast.Call):
            return None
        if is_load(node.func):
            return _literal(node.args[0]) if node.args else None
        if isinstance(node.func, ast.Name):
            if node.func.id in passthrough:
                return _literal(node.args[0]) if node.args else None
            return getters.get(node.func.id)
        return None

    def pairs(node: ast.AST) -> list[tuple[ast.AST, ast.AST]]:
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            return [(node.target, node.value)]
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            return []
        target, value = node.targets[0], node.value
        if (
            isinstance(target, ast.Tuple)
            and isinstance(value, ast.Tuple)
            and len(target.elts) == len(value.elts)
        ):
            return list(zip(target.elts, value.elts, strict=True))
        return [(target, value)]

    # Tres vueltas: una función puede devolver una variable que se asigna de otra función.
    for _ in range(3):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                params = {arg.arg for arg in node.args.args}
                for inner in ast.walk(node):
                    if not (isinstance(inner, ast.Return) and inner.value is not None):
                        continue
                    value = inner.value
                    if (
                        isinstance(value, ast.Call)
                        and is_load(value.func)
                        and value.args
                        and isinstance(value.args[0], ast.Name)
                        and value.args[0].id in params
                    ):
                        passthrough.add(node.name)
                    elif tool := tool_of(value):
                        getters[node.name] = tool
            for target, value in pairs(node):
                tool = tool_of(value)
                if isinstance(target, ast.Name) and tool:
                    assert variables.setdefault(target.id, tool) == tool, (
                        f"`{target.id}` vale dos herramientas en el mismo fichero"
                    )

    taken: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and (tool := tool_of(node.value)):
            taken.setdefault(tool, set()).add(node.attr)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "setattr", "hasattr"}
            and len(node.args) >= 2
            and (tool := tool_of(node.args[0]))
        ):
            taken.setdefault(tool, set()).add(_literal(node.args[1]) or COMPUTED)
    return taken


def emma_takes() -> dict[str, dict[str, set[str]]]:
    """`{herramienta: {fichero de backend/: {atributos}}}` para `app/` y `scripts/`."""
    found: dict[str, dict[str, set[str]]] = {}
    for folder in ("app", "scripts"):
        for path in sorted((BACKEND / folder).rglob("*.py")):
            source = path.read_text(encoding="utf-8-sig")
            for tool, names in attributes_taken(source, path.parent == ADAPTER).items():
                found.setdefault(tool, {})[path.relative_to(BACKEND).as_posix()] = names
    return found


@dataclass(frozen=True)
class Row:
    tool: str
    names: frozenset[str]
    files: frozenset[str]
    text: str


def notice_rows(notice: str) -> list[Row]:
    """Las filas de la tabla «LLAMAN a la copia literal» de `NOTICE`.

    Una fila empieza en `  tools/<herramienta>.py` y sigue hasta la siguiente. A la izquierda de
    `backend/` está el origen, con los nombres entre paréntesis; a la derecha, los ficheros.
    """
    section = notice.split("LLAMAN a la copia literal", 1)[1]
    table = section.split("Destino en EMMA", 1)[1].split("\n\n", 1)[0]
    blocks: list[list[str]] = []
    for line in table.splitlines():
        if line.startswith("  tools/"):
            blocks.append([line])
        elif line.strip():
            assert blocks, f"línea suelta antes de la primera fila: {line!r}"
            blocks[-1].append(line)
    rows = []
    for block in blocks:
        text = "\n".join(block)
        head = re.match(r"  tools/(\w+)\.py\b", block[0])
        assert head, f"fila sin herramienta: {text}"
        origin = " ".join(line.partition("backend/")[0] for line in block)
        inside = [part for group in re.findall(r"\(([^)]*)\)", origin) for part in group.split(",")]
        names = [part.strip() for part in inside]
        loose = [name for name in names if not name.isidentifier()]
        assert names and not loose, f"entre paréntesis van solo nombres de la copia: {text}"
        files = re.findall(r"\bbackend/([\w/]+\.py)\b", text)
        assert files, f"fila sin fichero de destino: {text}"
        rows.append(Row(head[1], frozenset(names), frozenset(files), text))
    return rows


def table_problems(rows: list[Row], takes: dict[str, dict[str, set[str]]]) -> list[str]:
    """Lo que la tabla dice y el código no hace, y al revés. Vacío si coinciden."""
    problems = []
    for row in rows:
        by_file = takes.get(row.tool, {})
        real: set[str] = set().union(*(by_file.get(name, set()) for name in row.files))
        if missing := sorted(real - row.names):
            problems.append(f"{row.tool} en {sorted(row.files)}: faltan {missing}")
        if extra := sorted(row.names - real):
            problems.append(f"{row.tool} en {sorted(row.files)}: sobran {extra}")
    for tool in sorted({row.tool for row in rows}):
        listed = set().union(*(row.files for row in rows if row.tool == tool))
        if unlisted := sorted(set(takes.get(tool, {})) - listed):
            problems.append(f"{tool}: también lo usan {unlisted}")
    return problems


READER_SAMPLE = '''
from app import polaris

CONSTANT = polaris.load("uno")._ANTI

def _tool():
    return polaris.load("dos")

def _named(name):
    return polaris.load(name)

def _through_a_variable():
    border = polaris.load("tres")
    return border

def work(other):
    tool = _tool()
    a, b = _named("cuatro"), _named("cinco")
    typed: object = polaris.load("seis")
    return (
        _tool().directa(), tool.por_variable, a.en_tupla, b.en_tupla_dos, typed.anotada,
        _through_a_variable().por_funcion, getattr(tool, "por_getattr"), getattr(tool, other),
        other.ajeno, load("siete").sin_adaptador,
    )
'''


def test_the_reader_sees_every_way_emma_reaches_a_tool() -> None:
    """Un lector que no ve una forma de llamar daría por buena una tabla corta."""
    assert attributes_taken(READER_SAMPLE) == {
        "uno": {"_ANTI"},
        "dos": {"directa", "por_variable", "por_getattr", COMPUTED},
        "tres": {"por_funcion"},
        "cuatro": {"en_tupla"},
        "cinco": {"en_tupla_dos"},
        "seis": {"anotada"},
    }
    # `load("x")` a secas solo es la copia dentro del adaptador.
    assert attributes_taken(READER_SAMPLE, inside_adapter=True)["siete"] == {"sin_adaptador"}
    with pytest.raises(AssertionError, match="dos herramientas"):
        attributes_taken('x = polaris.load("a")\nx = polaris.load("b")\n')


def test_the_reader_finds_what_the_code_really_takes() -> None:
    takes = emma_takes()
    assert {"_caja_de", "_diametro_axial_mayor"} <= takes["visor3d"]["app/volumes/geometry.py"]
    assert takes["borde"]["app/polaris/__init__.py"] == {"CANARIO_FILE"}
    assert takes["mutantes"] == {"scripts/mutants.py": {"Campana"}}
    assert takes["cronica"] == {"app/timeline.py": {"_linea_bitacora"}}


def test_the_table_reader_tells_names_from_files_and_refuses_prose() -> None:
    table = (
        "Ficheros que LLAMAN a la copia literal:\n\n"
        "  Origen en Polaris                               Destino en EMMA\n"
        "  tools/uno.py (alfa, _beta,                      backend/app/a.py (envuelta)\n"
        "    GAMMA)                                        backend/app/b.py\n"
        "  tools/dos.py                                    backend/scripts/c.py, backend/tests/x/\n"
        "    (delta)\n"
        "\nOtra cosa: tools/tres.py (no) backend/app/no.py\n"
    )
    rows = notice_rows(table)
    assert [(row.tool, set(row.names), set(row.files)) for row in rows] == [
        ("uno", {"alfa", "_beta", "GAMMA"}, {"app/a.py", "app/b.py"}),
        ("dos", {"delta"}, {"scripts/c.py"}),
    ]
    takes = {"uno": {"app/a.py": {"alfa", "_beta"}, "app/b.py": {"GAMMA"}}}
    assert table_problems(rows[:1], takes) == []
    takes["uno"]["app/b.py"] = {"GAMMA", "nueva"}
    takes["uno"]["app/z.py"] = {"alfa"}
    assert table_problems(rows[:1], takes) == [
        "uno en ['app/a.py', 'app/b.py']: faltan ['nueva']",
        "uno: también lo usan ['app/z.py']",
    ]
    assert table_problems(rows[1:], takes) == ["dos en ['scripts/c.py']: sobran ['delta']"]
    with pytest.raises(AssertionError, match="solo nombres"):
        notice_rows(table.replace("(delta)", "(clase delta)"))
    with pytest.raises(AssertionError, match="solo nombres"):
        notice_rows(table.replace("    (delta)\n", ""))


def test_notice_names_everything_emma_takes_from_the_tools_in_its_table() -> None:
    """Fila a fila: los nombres entre paréntesis son los que esos ficheros piden a la copia."""
    rows = notice_rows((REPO / "NOTICE").read_text(encoding="utf-8"))
    assert {"visor3d", "borde", "deid", "mutantes"} <= {row.tool for row in rows}
    problems = table_problems(rows, emma_takes())
    assert not problems, "NOTICE («llaman a la copia») y el código no coinciden:\n" + "\n".join(
        problems
    )
