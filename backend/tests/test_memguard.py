"""El techo de memoria de Polaris (`guarda_memoria.corre`) en Windows: se mata el árbol que se
pasa, no el que cabe. Procesos reales y pequeños; sin red.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app import memguard
from app.polaris.compat import memguard as windows

HOG = ("import time; b = bytearray(2 * 1024 ** 3); b[::4096] = b'x' * len(b[::4096]); "
       "time.sleep(30)")


@pytest.mark.skipif(sys.platform != "win32", reason="las lecturas de Windows")
def test_a_tree_over_its_ceiling_is_killed() -> None:
    outcome = memguard.run([sys.executable, "-c", HOG], 1.0, interval_s=0.5)
    assert outcome.killed_for_memory and outcome.peak_gb >= 1.0


@pytest.mark.skipif(sys.platform != "win32", reason="las lecturas de Windows")
def test_a_tree_under_its_ceiling_finishes() -> None:
    small = "import time; b = bytearray(100 * 1024 ** 2); time.sleep(1)"
    outcome = memguard.run([sys.executable, "-c", small], 1.0, interval_s=0.5)
    assert outcome.code == 0 and outcome.peak_gb < 1.0


@pytest.mark.skipif(sys.platform != "win32", reason="las lecturas de Windows")
def test_an_idle_tree_is_cut_as_hung() -> None:
    outcome = memguard.run([sys.executable, "-c", "import time; time.sleep(60)"], 1.0,
                           interval_s=0.5, idle_s=3.0)
    assert outcome.code == memguard.HUNG


@pytest.mark.skipif(sys.platform != "win32", reason="las lecturas de Windows")
def test_the_whole_tree_is_watched_not_only_the_child() -> None:
    # El hijo directo no consume, el nieto sí: la primera guarda de Polaris solo miraba al padre.
    grandchild = f"import subprocess, sys; subprocess.run([sys.executable, '-c', {HOG!r}])"
    outcome = memguard.run([sys.executable, "-c", grandchild], 1.0, interval_s=0.5)
    assert outcome.killed_for_memory


@pytest.mark.skipif(sys.platform != "win32", reason="las lecturas de Windows")
def test_a_busy_tree_is_not_taken_for_hung() -> None:
    busy = "import time\nend = time.time() + 5\nwhile time.time() < end: pass"
    outcome = memguard.run([sys.executable, "-c", busy], 1.0, interval_s=0.5, idle_s=2.0)
    assert outcome.code == 0


@pytest.mark.skipif(sys.platform != "win32", reason="la sustitución de Windows")
def test_an_interrupted_run_takes_its_tree_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Al interrumpir (Ctrl-C), `corre` llama a `os.killpg`, que en Windows no existe: su
    `try/except` se tragaba el fallo y el árbol quedaba vivo. Con un doble: no se lanza nada."""

    class Interrupted:
        pid = 4242

        def poll(self) -> None:
            raise KeyboardInterrupt

    tool = memguard._tool()
    killed: list[int] = []
    monkeypatch.setattr(tool, "subprocess", SimpleNamespace(Popen=lambda *a, **kw: Interrupted()))
    monkeypatch.setattr(windows, "_taskkill", killed.append)
    with pytest.raises(KeyboardInterrupt):
        tool.corre(["no-se-lanza"], None, inactivo_s=1.0)
    assert killed == [4242]
    assert tool.os.path.sep == "\\"  # el resto de `os` sigue siendo el de verdad
