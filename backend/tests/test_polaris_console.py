"""La consola del proceso se le quita a Polaris bajo UN cerrojo (`app/polaris/console.py`).

`redirect_stdout` cambia `sys.stdout`, que es de todo el proceso. Con un cerrojo por adaptador
(`kb`, `export`, `volumes/spine`), dos capturas se solapaban: el texto de una caía en el búfer de
la otra —y de ese texto lee `spine` el control de la cadena vertebral, que va al resumen firmado—
y la consola podía quedarse apuntando a un búfer muerto.

Sin esperas afortunadas: el cerrojo se cambia por uno que avisa cuando alguien tiene que esperar,
y cada hilo avisa cuando entra en la función capturada. La prueba espera a que cada hilo haya
hecho una de las dos cosas y entonces mira cuál.
"""

from __future__ import annotations

import io
import re
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app import export, kb, polaris
from app.polaris import console
from app.volumes import spine

ADAPTERS = ("spine", "export", "kb")
PATIENCE = 20.0  # segundos; solo se agota si algo se cuelga, nunca en una pasada buena


class _Spy:
    """Un cerrojo reentrante que marca al hilo que lo encuentra tomado, antes de esperarlo."""

    def __init__(self, progress: dict[str, threading.Event]) -> None:
        self._inner = threading.RLock()
        self._progress = progress

    def __enter__(self) -> _Spy:
        if not self._inner.acquire(blocking=False):
            self._progress[threading.current_thread().name].set()
            self._inner.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self._inner.release()


class _Crossing:
    """Los tres adaptadores con herramientas de Polaris de pega, cada uno en su hilo.

    La de `holder` se queda DENTRO de su captura hasta que la prueba la suelta; las otras dos
    escriben y vuelven. `progress[nombre]` se pone cuando ese hilo entra en su función capturada o
    cuando encuentra tomado el cerrojo de consola: una de las dos cosas pasa siempre.
    """

    def __init__(self, holder: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.holder = holder
        self.progress = {name: threading.Event() for name in ADAPTERS}
        self.release = threading.Event()
        self.inside: list[str] = []  # quién ha entrado en su función capturada, por orden
        self.results: dict[str, Any] = {}
        self.errors: list[BaseException] = []
        self._tmp = tmp_path
        monkeypatch.setattr(console, "_LOCK", _Spy(self.progress))

        docs = tmp_path / "docs-raiz"
        (docs / "compliance").mkdir(parents=True)
        (docs / "compliance" / "uno.md").write_text("# Uno\n\ntexto\n", encoding="utf-8")
        monkeypatch.setattr(kb, "docs_root", lambda: docs)
        monkeypatch.setattr(polaris, "configure", lambda: tmp_path / "estado")
        embed = SimpleNamespace(
            MODEL_FILE=str(kb.MODEL / "model_qint8_avx512_vnni.onnx"), disponible=lambda: False
        )
        fake_kb = SimpleNamespace(kb_embed=embed, DB="", VEC="")

        def build() -> None:
            # Como el de verdad, deja un índice nuevo: `kb` solo da por hecha la reindexación
            # si el fichero del índice cambió (§5.37.11).
            self._speak("kb")
            Path(fake_kb.DB).write_bytes(b"indice de pega")

        fake_kb.build = build
        monkeypatch.setattr(kb, "_tool", lambda: fake_kb)

        def main() -> None:
            self._speak("export")
            Path(sys.argv[2]).write_bytes(b"%PDF de pega")

        fake_pdf = SimpleNamespace(SimpleDocTemplate=object, main=main)
        monkeypatch.setattr(export, "_tool", lambda: fake_pdf)

    def _speak(self, name: str) -> None:
        """Lo que hace la herramienta de pega, ya con la consola capturada."""
        self.inside.append(name)
        print(f"{name}: principio")
        self.progress[name].set()
        if name == self.holder and not self.release.wait(PATIENCE):
            raise TimeoutError("nadie soltó al hilo que tenía la consola")
        print(f"{name}: fin", file=sys.stderr)

    def _stopping(self) -> None:
        self._speak("spine")
        raise SystemExit("motivo de Polaris")  # así abortan `_revisa_cadena` y `_orden_columna`

    def _run(self, name: str) -> None:
        calls: dict[str, Callable[[], Any]] = {
            "spine": lambda: spine._call(self._stopping),
            "export": lambda: export.to_pdf("# Prueba\n", "EMMA — prueba"),
            "kb": kb.refresh,
        }
        try:
            self.results[name] = calls[name]()
        except BaseException as exc:  # noqa: BLE001 — se revisa en el hilo de la prueba
            self.errors.append(exc)

    def cross(self) -> list[str]:
        """Devuelve quién estaba dentro de su captura mientras `holder` tenía la consola."""
        threads = {name: threading.Thread(target=self._run, args=(name,), name=name)
                   for name in ADAPTERS}
        try:
            threads[self.holder].start()
            assert self.progress[self.holder].wait(PATIENCE)
            for name in ADAPTERS:
                if name != self.holder:
                    threads[name].start()
                    assert self.progress[name].wait(PATIENCE)
            return list(self.inside)
        finally:
            self.release.set()
            for thread in threads.values():
                if thread.ident is not None:
                    thread.join(PATIENCE)
            assert not any(thread.is_alive() for thread in threads.values())


@pytest.mark.parametrize("holder", ADAPTERS)
def test_while_one_adapter_holds_the_console_the_other_two_wait(
    holder: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout, stderr = sys.stdout, sys.stderr
    crossing = _Crossing(holder, tmp_path, monkeypatch)
    during = crossing.cross()
    # Con un cerrojo por adaptador, los otros dos entraban y aquí salían los tres.
    assert during == [holder]
    assert crossing.errors == []
    assert sorted(crossing.inside) == sorted(ADAPTERS)  # al soltar, los otros dos sí pasan
    # Cada uno se lleva SU texto entero (stdout y stderr), y el aborto de Polaris se recoge.
    assert crossing.results["spine"] == ("spine: principio\nspine: fin\n", "motivo de Polaris")
    assert crossing.results["export"] == b"%PDF de pega"
    assert crossing.results["kb"]["rebuilt"] is True
    # Y la consola del proceso vuelve a ser la que era.
    assert sys.stdout is stdout and sys.stderr is stderr


def test_the_capture_gives_back_the_console_when_polaris_aborts() -> None:
    stdout, stderr = sys.stdout, sys.stderr
    with pytest.raises(SystemExit), console.captured() as out:
        print("antes de abortar")
        raise SystemExit("fuera")
    assert out.getvalue() == "antes de abortar\n"
    assert sys.stdout is stdout and sys.stderr is stderr


def test_a_nested_capture_in_the_same_thread_does_not_deadlock() -> None:
    stdout = sys.stdout
    said: dict[str, str] = {}

    def nested() -> None:
        with console.captured() as outer:
            print("fuera")
            with console.captured() as inner:
                print("dentro")
            print("fuera otra vez")
        said["outer"], said["inner"] = outer.getvalue(), inner.getvalue()

    # En un hilo aparte: con un cerrojo no reentrante esto se cuelga, y la prueba tiene que fallar.
    thread = threading.Thread(target=nested, daemon=True)
    thread.start()
    thread.join(5.0)
    assert not thread.is_alive(), "la captura anidada se quedó esperándose a sí misma"
    assert said == {"outer": "fuera\nfuera otra vez\n", "inner": "dentro\n"}
    assert sys.stdout is stdout


def test_the_real_pdf_export_leaves_the_console_as_it_was() -> None:
    stdout, stderr = sys.stdout, sys.stderr
    assert export.to_pdf("# Prueba\n", "EMMA — prueba").startswith(b"%PDF")
    assert sys.stdout is stdout and sys.stderr is stderr


_OWN_REDIRECT = re.compile(r"redirect_std(out|err)\s*\(|sys\.std(out|err)\s*=[^=]")


def test_no_module_of_emma_redirects_the_console_on_its_own() -> None:
    app_dir = Path(console.__file__).resolve().parents[1]
    own = Path(console.__file__).resolve()
    offenders = [
        f"{path.relative_to(app_dir).as_posix()}:{number}"
        for path in sorted(app_dir.rglob("*.py"))
        if path.resolve() != own
        for number, line in enumerate(io.StringIO(path.read_text(encoding="utf-8")), start=1)
        if _OWN_REDIRECT.search(line.split("#", 1)[0])
    ]
    assert offenders == [], "la consola se captura con app.polaris.console.captured()"
