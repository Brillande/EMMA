"""Lo que el congelado deja fuera no puede ser algo que el código importe, ni un aviso legal.

`packaging/freeze.py` excluye módulos para que el ejecutable pese menos. Si el código empieza a
usar uno, la suite sigue en verde (aquí está instalado) y el fallo solo aparece en la app
instalada. Pasó con `scipy` (2026-10-04): toda segmentación del visor 3D moría al remuestrear.

Lo mismo con lo que sí tiene que viajar. El ejecutable lleva el código AGPL de Polaris, y hasta el
2026-10-06 lo llevaba sin su licencia, su aviso ni el registro de cambios a los que remite el
`NOTICE` de EMMA: nada en la suite lo notaba, porque en el repositorio están.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


def load(path: Path) -> ModuleType:
    """Un script por su ruta: `packaging/` y `scripts/` no son paquetes. `freeze.py` se puede
    importar aquí porque solo pide PyInstaller al ejecutarse, no al importarse."""
    spec = importlib.util.spec_from_file_location(f"emma_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # los dataclasses buscan ahí su módulo
    spec.loader.exec_module(module)
    return module


freeze = load(BACKEND / "packaging" / "freeze.py")
polaris_sync = load(BACKEND / "scripts" / "polaris_sync.py")

# Los avisos de Polaris que tienen que estar en lo entregado, escritos aquí otra vez a propósito:
# la licencia, el aviso y la cita de su autora, el origen y los cambios (AGPL §4 y §5a), y lo que
# hace falta para seguirlos sin el repositorio (su README y su CHANGELOG, la lista de la copia y el
# fichero al que remiten las cabeceras de EMMA).
POLARIS_NOTICES = (
    "LICENSE", "NOTICE", "CITATION.cff", "ORIGEN.md", "CAMBIOS.json",
    "README.md", "CHANGELOG.md", "MANIFEST.sha256", "ADOPTADO.txt",
)

# Las cuatro formas que la expresión regular anterior leía mal o no leía.
SOURCE = '''
import json as _json
import os, shutil
from scipy import ndimage as _nd
from PIL import (
    Image,
    ImageDraw as _draw,
)
from . import vecino
from .hermano import cosa

def perezosa():
    import reportlab.lib.colors
    from nibabel.processing import resample_to_output as _resample
    return "import fantasma"
'''


def imported_roots(path: Path) -> set[str]:
    """Paquetes raíz importados en un fichero, también los importados dentro de una función."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_nothing_the_app_imports_is_left_out_of_the_executable() -> None:
    left_out = set(freeze.EXCLUDED)
    assert left_out, "freeze.py ya no declara EXCLUDED"
    offenders = {
        str(path.relative_to(BACKEND)): sorted(imported_roots(path) & left_out)
        for path in (BACKEND / "app").rglob("*.py")
        if imported_roots(path) & left_out
    }
    assert offenders == {}


def test_scipy_travels_because_the_3d_viewer_needs_it() -> None:
    # nibabel.processing (remuestreo del visor) lo pide en ejecución, sin import visible en app/.
    assert "scipy" not in freeze.EXCLUDED


def test_the_executable_carries_every_polaris_legal_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Las opciones enteras, las que recibe PyInstaller. Sin buscar qué paquetes hay instalados:
    # eso importaría medio entorno dentro de la suite y aquí no se comprueba.
    monkeypatch.setattr(freeze, "find_spec", lambda name: None)
    packed = freeze.options()
    for name in POLARIS_NOTICES:
        source = REPO / "polaris" / name
        assert source.is_file(), f"falta polaris/{name}"
        # Destino `polaris`: junto a `polaris/tools`, donde `app/polaris` busca la copia congelada.
        assert f"--add-data={source}{os.pathsep}polaris" in packed, name
    assert f"--add-data={REPO / 'polaris' / 'tools' / '*.py'}{os.pathsep}polaris/tools" in packed


def test_every_polaris_tool_travels_with_its_card(monkeypatch: pytest.MonkeyPatch) -> None:
    # `/api/polaris/estado` lee la ficha de cada herramienta de `polaris/tools/fichas/`: en el
    # repositorio están siempre, y en el ejecutable solo si se declaran.
    monkeypatch.setattr(freeze, "find_spec", lambda name: None)
    cards = REPO / "polaris" / "tools" / "fichas"
    assert list(cards.glob("*.py.json")), "la copia de Polaris ya no trae fichas"
    assert f"--add-data={cards}{os.pathsep}polaris/tools/fichas" in freeze.options()


def test_the_orchestrators_table_travels_next_to_the_tools_that_cite_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `cost_guard` y `enruta_comite` remiten a `tools/orquestadores.json` (octava ronda). El
    # nombre, escrito aquí otra vez: si se cae de la lista de `freeze.py`, tiene que notarse.
    monkeypatch.setattr(freeze, "find_spec", lambda name: None)
    packed = freeze.options()
    tools = REPO / "polaris" / "tools"
    assert "orquestadores.json" in freeze.POLARIS_DATA
    for name in freeze.POLARIS_DATA:
        assert (tools / name).is_file(), f"falta polaris/tools/{name}"
        assert f"--add-data={tools / name}{os.pathsep}polaris/tools" in packed, name


def test_every_non_code_entry_of_the_copy_travels_or_says_why_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Los `.py` viajan por comodín; un dato nuevo de la copia no, y en el repositorio está siempre:
    # nada notaría que falta en la aplicación instalada. Cada fichero o carpeta que no sea código
    # está en una lista de `freeze.py`, y en una sola.
    monkeypatch.setattr(freeze, "find_spec", lambda name: None)
    tools = REPO / "polaris" / "tools"
    present = {
        path.name for path in tools.iterdir() if path.suffix != ".py" and path.name != "__pycache__"
    }
    files, folders = set(freeze.POLARIS_DATA), set(freeze.POLARIS_DIRS)
    left_out = set(freeze.POLARIS_NOT_SHIPPED)
    assert present - files - folders - left_out == set(), "sin declarar en packaging/freeze.py"
    # Ni un nombre de más: una línea de algo que ya no está en la copia es una afirmación falsa.
    assert (files | folders | left_out) - present == set()
    assert not (files & folders or files & left_out or folders & left_out)
    assert all((tools / name).is_file() for name in files)
    assert all((tools / name).is_dir() for name in folders)
    assert all(len(reason.strip()) >= 20 for reason in freeze.POLARIS_NOT_SHIPPED.values())
    # Y lo declarado es lo que pasa: lo que «no viaja» no está entre lo que recibe PyInstaller.
    sources = {
        Path(option.removeprefix("--add-data=").rsplit(os.pathsep, 1)[0])
        for option in freeze.options()
        if option.startswith("--add-data=")
    }
    shipped = {source.name for source in sources if source.parent == tools}
    assert shipped == files | folders | {"*.py"}
    assert tools not in sources, "polaris/tools entera arrastraría lo declarado como «no viaja»"


def test_the_installer_puts_the_polaris_notices_where_the_emma_notice_points() -> None:
    # `resources/NOTICE` remite a `polaris/NOTICE`, `polaris/ORIGEN.md` y `polaris/CAMBIOS.json`:
    # quien abra la carpeta de instalación tiene que encontrarlos con esa ruta.
    package = json.loads((REPO / "desktop" / "package.json").read_text(encoding="utf-8"))
    shipped = {entry["from"]: entry["to"] for entry in package["build"]["extraResources"]}
    # La lista de esta prueba y no la de `freeze.py`: si se acorta allí, aquí tiene que notarse.
    for name in POLARIS_NOTICES:
        assert shipped.get(f"../polaris/{name}") == f"polaris/{name}", name
        assert (REPO / "desktop" / f"../polaris/{name}").is_file()


def test_the_executable_and_the_installer_carry_the_same_notices() -> None:
    # Dos listas escritas a mano en dos ficheros: que ninguna lleve un aviso que la otra no.
    package = json.loads((REPO / "desktop" / "package.json").read_text(encoding="utf-8"))
    installed = {
        entry["from"].removeprefix("../polaris/")
        for entry in package["build"]["extraResources"]
        if entry["from"].startswith("../polaris/")
    }
    assert installed == set(freeze.POLARIS_NOTICES) == set(POLARIS_NOTICES)


def test_no_polaris_test_nor_test_only_shim_travels(monkeypatch: pytest.MonkeyPatch) -> None:
    # Lo entregado no lleva herramientas de prueba: ni las pruebas de la copia ni un sustituto de
    # `compat/` que solo exista para correrlas. De `compat/` viaja como fichero suelto solo
    # `fcntl.py`, que es el que las herramientas importan por su nombre en ejecución.
    monkeypatch.setattr(freeze, "find_spec", lambda name: None)
    data = [
        option.removeprefix("--add-data=").rsplit(os.pathsep, 1)
        for option in freeze.options()
        if option.startswith("--add-data=")
    ]
    polaris_tests = REPO / "polaris" / "tests"
    assert not [source for source, _ in data if Path(source).is_relative_to(polaris_tests)]
    assert not [target for _, target in data if target.startswith("polaris/tests")]
    compat = BACKEND / "app" / "polaris" / "compat"
    assert [Path(source).name for source, _ in data if Path(source).parent == compat] == [
        "fcntl.py"
    ]
    # Tampoco por otra puerta: ni la carpeta entera (o una de las que la contienen) como dato, ni
    # como módulo declarado. `resource.py` y `sitecustomize.py` existen solo para correr las
    # pruebas de la copia en Windows (`scripts/polaris_tests.py`).
    assert not [source for source, _ in data if compat.is_relative_to(Path(source))]
    hidden = {
        option.removeprefix("--hidden-import=")
        for option in freeze.options()
        if option.startswith("--hidden-import=")
    }
    for name in ("resource", "sitecustomize"):
        assert (compat / f"{name}.py").is_file(), f"compat/{name}.py ya no existe: revisa esto"
        assert name not in hidden and f"app.polaris.compat.{name}" not in hidden


def test_the_compat_modules_emma_imports_are_declared_to_the_freezer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `app/polaris` importa `winlock` al arrancar y `app/memguard.py`, `memguard`: sin ellos en el
    # ejecutable la aplicación instalada no arranca. `compat/` no tiene `__init__.py`, así que no
    # se deja a que PyInstaller siga el `import`: se declaran. Y lo declarado es justo lo que
    # `app/` importa de esa carpeta, ni más (un sustituto de pruebas) ni menos.
    monkeypatch.setattr(freeze, "find_spec", lambda name: None)
    compat = BACKEND / "app" / "polaris" / "compat"
    prefix = "app.polaris.compat"
    imported: set[str] = set()
    for path in (BACKEND / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == prefix:
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith(f"{prefix}."):
                imported.add((node.module or "").split(".")[3])
            elif isinstance(node, ast.Import):
                imported.update(
                    alias.name.split(".")[3]
                    for alias in node.names
                    if alias.name.startswith(f"{prefix}.")
                )
    assert imported == set(freeze.COMPAT_MODULES) == {"winlock", "memguard"}
    packed = freeze.options()
    for name in freeze.COMPAT_MODULES:
        assert (compat / f"{name}.py").is_file()
        assert f"--hidden-import={prefix}.{name}" in packed, name


# Las bibliotecas de terceros que nombra la copia de Polaris, medidas el 2026-10-08 con sus 138
# herramientas (134 desde el 2026-10-09): las mismas que con las 103 de antes.
# `polaris_options` declara al congelador las
# que encuentre instaladas en el entorno limpio, así que un nombre nuevo aquí es una biblioteca
# que puede entrar en el instalador sin que nadie lo decida. Si esta lista cambia, antes de
# tocarla: ¿tiene ficha de SOUP (`compliance/software-safety-classification.md`)?
POLARIS_THIRD_PARTY = {
    "PIL", "SimpleITK", "matplotlib", "nibabel", "nnunetv2", "numpy", "onnxruntime", "pydicom",
    "pypdf", "reportlab", "scipy", "skimage", "soundfile", "tokenizers", "torch",
    "totalsegmentator", "transformers", "whisper",
}
def test_the_copy_names_no_third_party_library_nobody_reviewed() -> None:
    tools = REPO / "polaris" / "tools"
    local = {path.stem for path in tools.glob("*.py")}
    named: set[str] = set()
    for path in tools.glob("*.py"):
        named |= {name.split(".")[0] for name in freeze.imported_names(path.read_text("utf-8"))}
    third_party = named - local - set(sys.stdlib_module_names)
    # `fcntl` y `resource` son de la biblioteca estándar de Unix: Python los cuenta también aquí.
    assert third_party == POLARIS_THIRD_PARTY


def test_no_copied_tool_imports_a_polaris_test() -> None:
    """Las pruebas de la copia no viajan: una herramienta que importe una fallaría instalada.

    Lo hacía la orden `cotejado` de `estado_actual` (`test_perfil_clinico_al_dia.fecha_cotejo`)
    hasta el cambio §5a del 2026-10-20 (`polaris/CAMBIOS.json`).
    """
    tools = REPO / "polaris" / "tools"
    tests = {path.stem for path in (REPO / "polaris" / "tests").glob("*.py")}
    assert "test_perfil_clinico_al_dia" in tests  # la prueba sigue en la copia: el veto mira algo
    offenders = {
        path.name: sorted(names & tests)
        for path in tools.glob("*.py")
        if (names := {n.split(".")[0] for n in freeze.imported_names(path.read_text("utf-8"))})
        & tests
    }
    assert offenders == {}
    # La otra mitad del patrón: poner `tests/` en `sys.path` para importarla después por su nombre,
    # que un lector de `import` no ve si el nombre llega en una cadena.
    reaches = re.compile(r"sys\.path\.(?:insert|append)\([^\n]*[\"']tests[\"']")
    assert [p.name for p in tools.glob("*.py") if reaches.search(p.read_text("utf-8"))] == []


def test_the_cotejo_date_brought_into_estado_actual_is_still_the_test_s_own() -> None:
    """La prueba de Polaris sigue definiendo su `fecha_cotejo`: si Polaris cambia la suya al poner
    la copia al día, la traída a la herramienta (cambio §5a) se quedaría atrás sin avisar."""

    def function(path: Path) -> str:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        [found] = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "fecha_cotejo"
        ]
        return ast.dump(found)

    copy = REPO / "polaris"
    assert function(copy / "tools" / "estado_actual.py") == function(
        copy / "tests" / "test_perfil_clinico_al_dia.py"
    )


def test_the_import_reader_understands_every_import_form() -> None:
    names = freeze.imported_names(SOURCE)
    assert names == {
        "json", "os", "shutil",
        "scipy", "scipy.ndimage",
        "PIL", "PIL.Image", "PIL.ImageDraw",
        "reportlab.lib.colors",
        "nibabel.processing", "nibabel.processing.resample_to_output",
    }


def test_the_copy_closure_sees_every_import_form() -> None:
    assert polaris_sync.imported_roots(SOURCE) == {
        "json", "os", "shutil", "scipy", "PIL", "reportlab", "nibabel",
    }


def test_the_copy_closure_follows_the_second_name_of_an_import(tmp_path: Path) -> None:
    # `import a, b`: la expresión regular solo veía `a`, y `b` se habría quedado sin copiar.
    (tmp_path / "raiz.py").write_text("import json, segunda\n", encoding="utf-8")
    (tmp_path / "segunda.py").write_text(
        "def f():\n    from tercera import x as y\n    return y\n", encoding="utf-8"
    )
    (tmp_path / "tercera.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "ajena.py").write_text("", encoding="utf-8")
    assert polaris_sync.closure(tmp_path, ["raiz"]) == {"raiz", "segunda", "tercera"}


# --- SPICE dentro del instalador (decisión del usuario, 2026-11-11) -----------------------------
# El retardo con Tierra sale sin red desde el primer arranque: viajan `spiceypy` (con CSPICE) y
# los núcleos fijados, y solo si verifican. Sin red: los núcleos de estas pruebas son de mentira,
# fijados aquí con su tamaño y su huella, y la descarga es una función de prueba.


def test_the_executable_carries_spiceypy_its_license_and_the_kernels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.environment import spice

    monkeypatch.setattr(freeze, "find_spec", lambda name: None)
    packed = freeze.options()
    # `spice.py` importa `spiceypy` por nombre en ejecución: PyInstaller no lo ve si no se declara
    # (y sin él tampoco entra el hook que recoge `cspice.dll`).
    assert "--hidden-import=spiceypy" in packed
    assert "--copy-metadata=spiceypy" in packed  # su dist-info, con la licencia MIT
    target = spice.BUNDLED_SUBDIR
    for name in [kernel.name for kernel in spice.KERNELS] + [freeze.SPICE_README]:
        # Desde la carpeta de preparación, la que solo llena `stage_spice_kernels` comprobando.
        assert f"--add-data={freeze.SPICE_STAGE / name}{os.pathsep}{target}" in packed, name
    # Ningún núcleo sale directamente de `data/spice` (sin pasar por la comprobación).
    assert not [option for option in packed if "data" + os.sep + "spice" in option]


def test_the_clean_build_environment_installs_the_spice_extra() -> None:
    script = (REPO / "desktop" / "scripts" / "build-backend.mjs").read_text(encoding="utf-8")
    assert '".[desktop,spice]"' in script
    pyproject = (BACKEND / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^spice = \[\s*"spiceypy', pyproject, re.MULTILINE)


def _pinned_kernels(
    monkeypatch: pytest.MonkeyPatch, content: dict[str, bytes]
) -> dict[str, bytes]:
    import hashlib

    from app.environment import spice

    monkeypatch.setattr(spice, "KERNELS", tuple(
        spice.Kernel(
            name=name, url=f"https://{spice.NAIF_HOST}/pub/naif/generic_kernels/{name}",
            kind="SPK" if name.endswith(".bsp") else "LSK", size=len(data),
            sha256=hashlib.sha256(data).hexdigest(), md5=None, integrity_source="prueba",
            covers="prueba",
        )
        for name, data in content.items()
    ))
    return content


KERNEL_FILES = {"a.tls": b"lsk de prueba", "b.bsp": b"spk de prueba"}


def test_verified_kernels_are_staged_with_their_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.environment import spice

    files = _pinned_kernels(monkeypatch, KERNEL_FILES)
    source, stage = tmp_path / "data-spice", tmp_path / "stage"
    source.mkdir()
    for name, data in files.items():
        (source / name).write_bytes(data)

    def no_network() -> int:
        raise AssertionError("con los núcleos verificados no se descarga nada")

    staged = freeze.stage_spice_kernels(source, stage, fetch=no_network)
    assert sorted(path.name for path in staged) == sorted([*files, freeze.SPICE_README])
    for name, data in files.items():
        assert (stage / name).read_bytes() == data
    readme = (stage / freeze.SPICE_README).read_text(encoding="utf-8")
    assert "SIN MODIFICAR" in readme and spice.RULES_URL in readme
    assert all(kernel.sha256 in readme and kernel.url in readme for kernel in spice.KERNELS)


def test_a_kernel_that_does_not_verify_is_not_packaged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _pinned_kernels(monkeypatch, KERNEL_FILES)
    source, stage = tmp_path / "data-spice", tmp_path / "stage"
    source.mkdir()
    (source / "a.tls").write_bytes(files["a.tls"])
    (source / "b.bsp").write_bytes(b"spk de prueba, cambiado")
    # Lo de una preparación anterior no puede quedarse y acabar en el paquete.
    stage.mkdir()
    (stage / "b.bsp").write_bytes(files["b.bsp"])
    asked: list[bool] = []
    with pytest.raises(freeze.SpiceKernelsRefused, match="sin verificar: b.bsp mide"):
        freeze.stage_spice_kernels(source, stage, fetch=lambda: asked.append(True) or 4)
    # Se intentó bajar (el guion solo guarda lo que verifica), y como sigue sin verificar, nada.
    assert asked == [True]
    assert not stage.exists()


def test_missing_kernels_are_fetched_before_packaging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _pinned_kernels(monkeypatch, KERNEL_FILES)
    source, stage = tmp_path / "data-spice", tmp_path / "stage"

    def fetch() -> int:  # lo que hace el guion de descarga: deja los fijados en la carpeta
        source.mkdir()
        for name, data in files.items():
            (source / name).write_bytes(data)
        return 0

    freeze.stage_spice_kernels(source, stage, fetch=fetch)
    assert all((stage / name).read_bytes() == data for name, data in files.items())


def test_without_kernels_nor_network_the_freeze_says_how_to_get_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pinned_kernels(monkeypatch, KERNEL_FILES)
    with pytest.raises(freeze.SpiceKernelsRefused) as refused:
        freeze.stage_spice_kernels(tmp_path / "vacia", tmp_path / "stage", fetch=lambda: 2)
    assert "falta a.tls" in str(refused.value)
    assert "fetch_spice_kernels.py" in str(refused.value)
    assert not (tmp_path / "stage").exists()


def test_the_freeze_fetches_with_the_download_script() -> None:
    # La descarga del empaquetado es la del guion: por la puerta de salida y comprobada.
    assert freeze.SPICE_FETCH == BACKEND / "scripts" / "fetch_spice_kernels.py"
    assert freeze.SPICE_FETCH.is_file()
