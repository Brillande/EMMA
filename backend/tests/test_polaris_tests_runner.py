# SPDX-License-Identifier: AGPL-3.0-or-later
"""El guion que corre las pruebas de Polaris no toca la copia ni se equivoca de Python.

Por qué existe: `scripts/polaris_tests.py` dejó dos veces una carpeta de la autora dentro de
`polaris/` (la huella de la copia dejó de casar) y lanzaba los `python3` de Polaris con un Python
del sistema que no era el de EMMA. Aquí se comprueba con un Polaris de juguete —tres pruebas que
tardan un segundo, no las suyas—, sin red, y se vigila que la tabla de causas del informe no
explique pruebas que no existen.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris; corre el guion que
ejecuta las pruebas de la copia literal (`polaris/ADOPTADO.txt`).
"""

from __future__ import annotations

import importlib.util
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest

from app import polaris

BACKEND = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    """`scripts/` no es un paquete: el guion se carga por su ruta."""
    spec = importlib.util.spec_from_file_location(
        "polaris_tests", BACKEND / "scripts" / "polaris_tests.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # `dataclass` busca el módulo por su nombre
    spec.loader.exec_module(module)
    return module


runner = _load()

# Lo que hacía `biomarcadores`: calcular su casa desde `__file__` y crear ahí una carpeta.
WRITES_AT_HOME = """
import pathlib
home = pathlib.Path(__file__).resolve().parents[1]
(home / "00_FUENTE-DE-VERDAD" / "00 · Bandeja de entrada").mkdir(parents=True)
(home / "tools" / "estado.json").write_text("{}", encoding="utf-8")
print("escrito en", home)
"""

# Lo que hace `replay_guard`: lanzar `python3` por nombre. Verde solo si es este mismo Python y
# ve sus dependencias (numpy solo está en el venv de EMMA).
CALLS_PYTHON3 = """
import subprocess, sys
probe = "import sys, numpy; print(sys.version_info[:2] == (%d, %d))"
for name in ("python3", "python"):
    done = subprocess.run([name, "-c", probe], capture_output=True, text=True)
    if done.stdout.strip() != "True":
        sys.exit(name + " es otro Python: " + (done.stderr.strip() or done.stdout.strip())[-150:])
"""

# Lo que hacen muchas suyas: un `mkdtemp` que nadie borra. El prefijo es único para poder buscarlo.
LEAVES_A_TEMP = """
import tempfile
print(tempfile.mkdtemp(prefix="emma_runner_resto_"))
"""

FAILS = "import pathlib, sys\nsys.exit('AssertionError en ' + str(pathlib.Path(__file__)))\n"
SKIPS = "import sys\nprint('SKIP: falta su entorno')\nsys.exit(77)\n"


@pytest.fixture
def toy(tmp_path: Path) -> Path:
    root = tmp_path / "polaris"
    (root / "tests").mkdir(parents=True)
    (root / "tools" / "visor3d_web" / "node_modules" / "pesado").mkdir(parents=True)
    (root / "tools" / "visor3d_web" / "node_modules" / "pesado" / "index.js").write_text("x")
    (root / "tools" / "util.py").write_text("X = 1\n", encoding="utf-8")
    tests = {
        "test_escribe_en_casa.py": WRITES_AT_HOME,
        "test_python3.py": CALLS_PYTHON3 % sys.version_info[:2],
        "test_roja.py": FAILS,
        "test_saltada.py": SKIPS,
        "test_temporal.py": LEAVES_A_TEMP,
    }
    for name, source in tests.items():
        (root / "tests" / name).write_text(source, encoding="utf-8")
    return root


def _tree(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


def test_the_tests_run_on_a_copy_and_leave_the_original_untouched(toy: Path) -> None:
    before = _tree(toy)

    tests, mutants = runner.run_suite(toy)

    outcomes = {result.name: result.outcome for result in tests}
    assert outcomes["test_escribe_en_casa.py"] == "verde", tests
    assert _tree(toy) == before, "una prueba de Polaris escribió en la copia versionada"
    assert mutants is None


def test_python3_by_name_is_the_interpreter_running_the_script(toy: Path) -> None:
    tests, _ = runner.run_suite(toy)

    result = next(result for result in tests if result.name == "test_python3.py")
    assert result.outcome == "verde", result.detail


def test_outcomes_follow_polaris_convention_and_details_name_no_temporary_path(toy: Path) -> None:
    tests, _ = runner.run_suite(toy)

    by_name = {result.name: result for result in tests}
    assert by_name["test_roja.py"].outcome == "rojo"
    assert by_name["test_saltada.py"].outcome == "saltada"
    # La copia tiene un nombre aleatorio: si saliera al informe, cambiaría entero en cada pasada.
    assert "polaris_pruebas_" not in by_name["test_roja.py"].detail
    assert by_name["test_roja.py"].detail.endswith(str(Path("polaris", "tests", "test_roja.py")))
    assert by_name["test_escribe_en_casa.py"].detail == "escrito en polaris"


def test_the_tests_temporary_folders_stay_inside_the_pass_and_go_with_it(toy: Path) -> None:
    """Sus `mkdtemp` caían en el temporal del sistema y se quedaban allí, cientos por pasada."""
    system = Path(tempfile.gettempdir())
    before = set(system.glob("emma_runner_resto_*"))

    tests, _ = runner.run_suite(toy)

    result = next(result for result in tests if result.name == "test_temporal.py")
    assert result.outcome == "verde", result.detail
    assert result.detail.startswith(str(Path("<tmp>", "emma_runner_resto_"))), result.detail
    assert set(system.glob("emma_runner_resto_*")) == before


def test_the_pass_folder_is_removed_even_with_read_only_files() -> None:
    # Los objetos de un repositorio git de prueba son de solo lectura, y en Windows eso frena un
    # borrado ingenuo.
    with runner.pass_folder() as scratch:
        temporary = runner.pass_temp(scratch)
        blocked = temporary / "repo" / "objeto"
        blocked.parent.mkdir()
        blocked.write_text("x", encoding="utf-8")
        blocked.chmod(stat.S_IREAD)
        environment = runner.environment(scratch / "estado", None, temporary)
    assert not scratch.exists()
    assert temporary.parent == scratch
    assert {environment[name] for name in ("TMP", "TEMP", "TMPDIR")} == {str(temporary)}


class _Stubborn(tempfile.TemporaryDirectory):  # type: ignore[type-arg]
    """Una carpeta que no se deja borrar: en Windows lo hace un fichero abierto; aquí, a mano,
    para que la prueba corra en cualquier sistema."""

    def cleanup(self) -> None:
        self._finalizer.detach()  # type: ignore[attr-defined]


def test_what_resists_the_cleanup_is_named_not_hidden(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(runner.tempfile, "TemporaryDirectory", _Stubborn)
    with runner.pass_folder() as scratch:
        runner.pass_temp(scratch)
    try:
        assert scratch.exists()
        assert f"queda en {scratch}" in capsys.readouterr().err
    finally:
        shutil.rmtree(scratch)


def test_the_sandbox_does_not_drag_node_modules(toy: Path, tmp_path: Path) -> None:
    copy = runner.sandbox(toy, tmp_path / "scratch")

    assert (copy / "tools" / "util.py").is_file()
    assert not (copy / "tools" / "visor3d_web" / "node_modules").exists()


def test_every_cause_explains_a_test_that_exists() -> None:
    """Una causa para una prueba que Polaris ya no trae (o mal escrita) no explica nada."""
    assert runner.unknown_causes(polaris.root() / "tests") == []
    assert all(kind in runner.KINDS and why for kind, why in runner.CAUSES.values())


def test_unknown_causes_names_the_entry_without_a_test(toy: Path) -> None:
    runner.CAUSES["test_que_no_existe"] = (runner.WINDOWS, "inventada")
    try:
        assert "test_que_no_existe" in runner.unknown_causes(toy / "tests")
    finally:
        del runner.CAUSES["test_que_no_existe"]


def test_the_report_gives_every_red_its_cause_and_flags_the_unexplained() -> None:
    explained = next(iter(runner.CAUSES))
    tests = [
        runner.Result(f"{explained}.py", "rojo", "FAILED"),
        runner.Result("test_nueva_roja.py", "rojo", "a | b"),
        runner.Result("test_verde.py", "verde", "ok"),
    ]

    text = runner.report(tests, [runner.Result("lector_clinico.json", "rojo", "rc 1")])

    kind, why = runner.CAUSES[explained]
    assert f"| `{explained}.py` | rojo | {kind}: {why} | FAILED |" in text
    assert "| `test_nueva_roja.py` | rojo | **sin explicar** | a / b |" in text
    assert "| **sin explicar** | 1 |" in text
    assert "| `test_verde.py` | verde |  | ok |" in text
    assert runner.CAMPAIGN_CAUSES["lector_clinico.json"] in text


def test_a_cause_whose_test_is_no_longer_red_is_reported_as_stale() -> None:
    explained = next(iter(runner.CAUSES))

    text = runner.report([runner.Result(f"{explained}.py", "verde", "ok")], None)

    assert "Causas caducadas (la prueba ya no está en rojo; quítalas de `CAUSES`): " in text
    assert f"`CAUSES`): `{explained}.py`." in text
    assert "Campañas de mutantes" not in text
