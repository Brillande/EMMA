# SPDX-License-Identifier: AGPL-3.0-or-later
"""Los rojos de Windows de las pruebas de Polaris, en lo que EMMA ejecuta de verdad.

Por qué existe: varias pruebas del propio Polaris salen o salían en rojo en esta máquina sobre
herramientas que EMMA llama (`fuente_clinica`, `decision_alto_riesgo`, `visor3d`, `seguimiento`) o
que le llegan arrastradas por otra (`cost_guard`, por `ia`; `_lock`, por `seguimiento`); la lista
vigente, con su causa, está en `polaris/PRUEBAS.md`. Un rojo ajeno puede ser solo andamiaje de la
prueba o puede ser un fallo que EMMA hereda sin verlo. Se miraron una a una
(`docs/polaris-divergencias.md`) y aquí queda fijado lo que salió, para que no dependa de que
alguien lo recuerde:

* `test_visor3d_malla_recorte` caía en `import resource`, y con ella quedaba sin comprobar el
  freno de memoria de `_malla`, que es la malla de `app/volumes/geometry.py`. `compat/resource.py`
  le da lo único que pide; aquí se prueba que mide de verdad y que para EMMA no existe.
* `test_lock_dueno` y `test_seguimiento_carrera`: el candado entre procesos de Polaris (`_lock.py`)
  no aguantaba en Windows, porque sondea al dueño con `os.kill(pid, 0)` y porque no puede borrar
  `dueno` mientras otro lo lee. `compat/winlock.py` le da una sonda de proceso de verdad y un
  borrado que insiste; aquí se prueba con procesos reales que el candado de un muerto se reclama
  en el acto, que el de un vivo se respeta y que varios escritores no se pisan.
* Lo que eso NO resuelve, y por eso el veto sigue: `seguimiento` escribe con `os.replace`, que en
  Windows falla si alguien tiene abierto el fichero, y sus lectores no toman el candado. EMMA solo
  lee `seguimiento` con los datos sustituidos; aquí se fija que su ruta no toma ese candado ni
  escribe ese fichero, y que el fallo de `os.replace` sigue ahí. Quien adopte un escritor de
  `seguimiento` rompe esta prueba y tiene que resolver antes esa escritura.
* `test_decision_alto_riesgo` y `test_cost_guard` fallan en los permisos `0600` de un acta y de
  un registro de gasto. EMMA no escribe ninguno de los dos; aquí se fija que siguen sin escribirse.

La huella de `fuente_clinica`, que sí alcanzaba a EMMA, está en `tests/test_vault.py`.

Usa la copia literal de Polaris sin modificarla (commit en `polaris/ADOPTADO.txt`;
AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»); se carga con
`app.polaris.load`.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

import pytest

from app import decision_risk, polaris, timeline
from app.polaris.compat import winlock

COMPAT = Path(polaris.__file__).resolve().parent / "compat"
MB = 2**20

# Lo que haría una prueba de Polaris: pide el pico, toca 96 MB, los suelta y vuelve a pedirlo.
PROBE = """
import json, sys
sys.path.append(sys.argv[1])
import resource
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
block = b"\\x01" * (96 * 2**20)
del block
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({"before": before, "after": after}))
"""


def _run_as(script: Path) -> subprocess.CompletedProcess[str]:
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(PROBE, encoding="utf-8")
    return subprocess.run([sys.executable, str(script), str(COMPAT)], capture_output=True,
                          text=True, timeout=60, check=False)


# --------------------------------------------------------------------------- #
# `resource` para la prueba del freno de memoria de la malla
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(os.name != "nt", reason="el sustituto de resource solo existe en Windows")
def test_the_resource_stand_in_reports_the_peak_in_bytes_and_keeps_it(tmp_path: Path) -> None:
    done = _run_as(tmp_path / "polaris" / "tests" / "test_sonda.py")
    assert done.returncode == 0, done.stderr
    measured = json.loads(done.stdout)
    # Es un pico: sigue ahí después de soltar la memoria. Y va en bytes (convención de macOS, la
    # que asume la prueba de Polaris al dividir por 1024²): en kilobytes el salto no llegaría.
    assert measured["after"] - measured["before"] >= 64 * MB
    assert measured["before"] >= 4 * MB, "un intérprete recién arrancado ya ocupa varios megas"


@pytest.mark.skipif(os.name != "nt", reason="el sustituto de resource solo existe en Windows")
@pytest.mark.parametrize("where", ["tests/test_sonda.py", "polaris/tests/sonda.py", "sonda.py"])
def test_outside_a_polaris_test_there_is_no_resource_module(tmp_path: Path, where: str) -> None:
    """Para EMMA y sus bibliotecas `import resource` sigue fallando como en cualquier Windows."""
    done = _run_as(tmp_path / where)
    assert done.returncode != 0
    assert "ModuleNotFoundError: No module named 'resource'" in done.stderr


def test_the_stand_in_offers_everything_the_copy_asks_of_resource() -> None:
    """Si una copia nueva pide más de `resource`, se ve aquí y no en un rojo de sus pruebas."""
    asked, fields = set(), set()
    for folder in ("tools", "tests"):
        for path in sorted((polaris.root() / folder).glob("*.py")):
            source = path.read_text(encoding="utf-8")
            if not re.search(r"^\s*import resource\b", source, re.M):
                continue
            assert folder == "tests", f"{path.name}: una herramienta de Polaris importa resource"
            asked |= set(re.findall(r"\bresource\.([A-Za-z_]\w*)", source))
            fields |= set(re.findall(r"getrusage\([^)]*\)\.(\w+)", source))
    assert asked == {"getrusage", "RUSAGE_SELF"}
    assert fields == {"ru_maxrss"}


# --------------------------------------------------------------------------- #
# Lo que EMMA no ejecuta, y por eso no hereda
# --------------------------------------------------------------------------- #


def _forbidden(what: str) -> Any:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"la ruta de EMMA llamó a {what}")
    return refuse


# --------------------------------------------------------------------------- #
# El candado entre procesos de Polaris, con la sonda de Windows
# --------------------------------------------------------------------------- #

windows_only = pytest.mark.skipif(os.name != "nt", reason="el pegamento del candado es de Windows")

# Toma el candado, lo dice y se queda con él hasta que lo maten.
HOLDER = """
import sys, time
sys.path.insert(0, sys.argv[1])
import _lock
with _lock.lock("turno", timeout=30):
    print(_lock._dueno_vivo.__module__, flush=True)
    time.sleep(120)
"""

# Suma de uno en uno en un fichero: leer, sumar y escribir, que es donde dos procesos se pisan.
COUNTER = """
import sys
sys.path.insert(0, sys.argv[1])
import _lock
path, rounds = sys.argv[2], int(sys.argv[3])
for _ in range(rounds):
    with _lock.lock("contador", timeout=60):
        with open(path, encoding="utf-8") as handle:
            seen = int(handle.read())
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(str(seen + 1))
print(_lock._dueno_vivo.__module__)
"""

# Lo que hace quien importa un `_lock`: el de una copia de Polaris o el de cualquier otra cosa.
IMPORTER = """
import sys
sys.path.insert(0, sys.argv[1])
import _lock
print(type(_lock.os).__name__, _lock._dueno_vivo.__module__)
"""


def _child_env(state: Path) -> dict[str, str]:
    """El entorno de una prueba de Polaris: `compat/` en `PYTHONPATH` y el estado aparte."""
    return {**os.environ, "PYTHONPATH": str(COMPAT), "BTP_STATE_DIR": str(state),
            "PYTHONDONTWRITEBYTECODE": "1"}


def _spawn(tmp_path: Path, source: str, *args: str) -> subprocess.Popen[str]:
    script = tmp_path / "proceso.py"
    script.write_text(source, encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, str(script), str(polaris.tools_dir()), *args],
        env=_child_env(tmp_path / "estado"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )


@pytest.fixture
def lock(tmp_path: Path) -> Any:
    """Un `_lock` de la copia solo para esta prueba, con el pegamento y su estado aparte."""
    spec = importlib.util.spec_from_file_location("_lock", polaris.tools_dir() / "_lock.py")
    assert spec is not None and spec.loader is not None
    module: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.LOCKS = str(tmp_path / "estado" / "locks")
    return winlock.install(module)


@windows_only
def test_the_probe_tells_a_dead_process_from_a_live_one_and_signals_nobody(
    monkeypatch: pytest.MonkeyPatch, lock: Any, tmp_path: Path,
) -> None:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    monkeypatch.setattr(os, "kill", _forbidden("os.kill"))
    folder = tmp_path / "a.lock"
    folder.mkdir()
    try:
        assert lock._dueno_vivo(str(folder)) == (None, None), "sin dueño declarado no se juzga"
        (folder / lock.DUENO).write_text(f"{child.pid}\n", encoding="utf-8")
        assert lock._dueno_vivo(str(folder)) == (True, child.pid)
        assert winlock.alive(os.getpid()) is True
        assert child.poll() is None, "preguntar por él no le ha hecho nada"
    finally:
        child.terminate()
        child.wait(timeout=30)
    # `child` sigue guardando un asa del proceso: para Windows el PID aún existe, y abrirlo no
    # basta para saber que ha terminado. Es el caso en que `os.kill(pid, 0)` vuelve sin error.
    assert lock._dueno_vivo(str(folder)) == (False, child.pid)
    # Y el caso corriente: un proceso del que ya no queda nada, ni el asa.
    gone = int(subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
    assert winlock.alive(gone) is False
    # El proceso System (PID 4) existe siempre y no se deja abrir: «es de otro», luego vive.
    assert winlock.alive(4) is True


@windows_only
def test_a_live_owner_keeps_the_lock_and_a_killed_one_loses_it_at_once(
    lock: Any, tmp_path: Path,
) -> None:
    holder = _spawn(tmp_path, HOLDER)
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "winlock", "el hijo corre con el pegamento"
        started = time.monotonic()
        with pytest.raises(TimeoutError), lock.lock("turno", timeout=0.5):
            pytest.fail("entró con el dueño vivo dentro")
        assert time.monotonic() - started >= 0.5
    finally:
        holder.kill()  # el hijo no llega a soltar: el candado se queda puesto, con su PID
        holder.communicate(timeout=30)
    assert lock.held("turno")
    started = time.monotonic()
    with lock.lock("turno", timeout=20):
        waited = time.monotonic() - started
    assert waited < 2.0, f"el candado de un muerto se esperó {waited:.1f} s"
    assert not lock.held("turno")


@windows_only
def test_processes_that_compete_for_the_lock_do_not_step_on_each_other(tmp_path: Path) -> None:
    writers, rounds = 6, 25
    counter = tmp_path / "contador.txt"
    counter.write_text("0", encoding="utf-8")
    running = [_spawn(tmp_path, COUNTER, str(counter), str(rounds)) for _ in range(writers)]
    done = [process.communicate(timeout=120) for process in running]
    assert [err for _, err in done if err] == []
    assert [out.strip() for out, _ in done] == ["winlock"] * writers
    assert int(counter.read_text(encoding="utf-8")) == writers * rounds
    assert not (tmp_path / "estado" / "locks" / "contador.lock").exists()


@windows_only
def test_the_owner_lets_go_even_while_someone_is_reading_who_owns_it(lock: Any) -> None:
    """Windows no borra un fichero abierto: sin insistir, el candado se quedaba puesto."""
    with lock.lock("mirado", timeout=5):
        reader = open(Path(lock.LOCKS) / "mirado.lock" / lock.DUENO, encoding="utf-8")  # noqa: SIM115
        threading.Timer(0.2, reader.close).start()
    assert not lock.held("mirado")
    with lock.lock("mirado", timeout=1):
        pass


@windows_only
@pytest.mark.parametrize(("where", "glued"), [("polaris/tools", True), ("otra/tools", False)])
def test_the_hook_only_touches_the_lock_of_a_polaris_copy(
    tmp_path: Path, where: str, glued: bool,
) -> None:
    """`_lock` es un nombre corriente: el de otra biblioteca se queda como está."""
    folder = tmp_path / where
    folder.mkdir(parents=True)
    (folder / "_lock.py").write_bytes((polaris.tools_dir() / "_lock.py").read_bytes())
    script = tmp_path / "importa.py"
    script.write_text(IMPORTER, encoding="utf-8")
    done = subprocess.run([sys.executable, str(script), str(folder)], capture_output=True,
                          text=True, timeout=60, check=False, env=_child_env(tmp_path / "estado"))
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == ("_OsForLocks winlock" if glued else "module _lock")


def test_the_glue_leaves_any_other_module_alone() -> None:
    """`install` se puede llamar desde un gancho de importación, con el módulo que sea."""
    other = types.ModuleType("otro")
    other.os = os  # type: ignore[attr-defined]
    assert winlock.install(other) is other
    assert other.os is os and not hasattr(other, "_dueno_vivo")


@windows_only
def test_a_reader_still_breaks_the_write_of_seguimiento(tmp_path: Path) -> None:
    """Lo que el pegamento del candado no arregla, y por lo que el veto de abajo sigue.

    `_write_atomic` acaba en `os.replace`, y Windows no reemplaza un fichero que alguien tiene
    abierto. Los lectores de `seguimiento.json` no toman el candado: basta uno leyendo para que
    un escritor reviente. El día que esto deje de fallar, el veto se puede volver a mirar.
    """
    follow: Any = polaris.load("seguimiento")
    target = tmp_path / "seguimiento.json"
    target.write_text('{"hilos": []}', encoding="utf-8")
    with open(target, encoding="utf-8"), pytest.raises(PermissionError):
        follow._write_atomic(str(target), {"hilos": [{"titulo": "nuevo"}]})
    assert json.loads(target.read_text(encoding="utf-8")) == {"hilos": []}


# --------------------------------------------------------------------------- #
# Los vetos: lo que la ruta de EMMA sigue sin tocar
# --------------------------------------------------------------------------- #


def test_the_week_of_the_timeline_never_takes_the_polaris_lock_nor_writes_its_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    follow, lock =polaris.load("seguimiento"), polaris.load("_lock")
    monkeypatch.setattr(lock, "lock", _forbidden("_lock.lock"))
    monkeypatch.setattr(follow, "_seg_lock", _forbidden("seguimiento._seg_lock"))
    monkeypatch.setattr(follow, "_write_atomic", _forbidden("seguimiento._write_atomic"))
    now = dt.datetime(2026, 12, 10, 23, tzinfo=dt.UTC)
    soon = (now + dt.timedelta(days=3)).date()
    status = {
        "data": {"reference_time": now.isoformat()},
        "followups": [{"countermeasure": {"id": "cv-repeat-rest"}, "domain": "cardiovascular",
                       "window_ends": f"{soon}T00:00:00Z", "state": "in_window"}],
        "mission": {"events": [{"kind": "eva", "label": "EVA 2", "start": f"{soon}"}]},
    }
    week = timeline.this_week(status, timeline.as_of(status, None, now), 7)
    assert len(week["items"]) == 2 and "EVA 2" in week["block"]
    assert not Path(follow.SEG).exists(), "EMMA no tiene un seguimiento.json que proteger"


def test_the_trigger_of_a_high_risk_decision_writes_no_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = polaris.load("decision_alto_riesgo")
    monkeypatch.setattr(original, "guardar_acta", _forbidden("guardar_acta"))
    assert decision_risk.trigger("Acepto; suspender la medicación", deciding=True).applies
    minutes = Path(original.ACTAS)
    assert polaris.state_dir().resolve() in minutes.resolve().parents
    assert not minutes.exists(), "el acta de EMMA es el asiento firmado, no un fichero de Polaris"


def test_the_cost_ledger_of_polaris_stays_inside_emma_and_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`cost_guard` llega arrastrado por `ia`; EMMA no habla con un cerebro de pago."""
    # `COST` se fija al importar: si otra prueba ya lo cargó con otro estado, se importa de nuevo.
    monkeypatch.delitem(sys.modules, "cost_guard", raising=False)
    guard = polaris.load("cost_guard")
    folder = Path(guard.COST)
    assert polaris.state_dir().resolve() in folder.resolve().parents
    assert not list(folder.glob("detalle-*.jsonl")), "nadie apunta gasto desde EMMA"


@pytest.mark.skipif(sys.platform != "win32", reason="el pegamento solo actúa en Windows")
def test_the_lock_emma_loads_comes_with_the_windows_probe() -> None:
    """Dentro de EMMA no hay `sitecustomize`: el pegamento lo pone el cargador de `app.polaris`."""
    from app import polaris
    from app.polaris.compat import winlock

    polaris.load("seguimiento")  # trae `_lock` por sus imports
    lock = sys.modules["_lock"]
    assert isinstance(lock.os, winlock._OsForLocks)
    assert lock._dueno_vivo.__module__ == winlock.__name__
