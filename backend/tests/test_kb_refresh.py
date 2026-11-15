"""La huella del índice de la documentación describe el índice que hay (§5.37.11).

Existe porque en el cierre de §5.36.10 la huella de `app/kb.py` quedó escrita sobre un índice que
no casaba con ella y una prueba de búsqueda semántica se puso roja a mitad de suite. Se buscaron
las vías por las que eso puede pasar y cada una tiene aquí su prueba, sobre carpetas temporales
(nunca el índice compartido de `data/cache/polaris`) y sin red:

* un documento editado entre la huella y la copia;
* `build()` de Polaris que devuelve 0 sin rehacer nada (otro proceso tiene su cerrojo);
* los vectores que no se pudieron calcular, con la huella diciendo «vectores»;
* dos procesos tocando el mismo corpus a la vez;
* y la espera a ese otro proceso, con tope (§5.38.10).
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import kb

OLD, NEW = "# Uno\n\nTexto viejo.\n", "# Uno\n\nTexto nuevo.\n"


@pytest.fixture
def docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Any]:
    """Una documentación mínima, un estado temporal y `kb` sin capa vectorial (más rápido)."""
    root, state = tmp_path / "repo", tmp_path / "estado"
    (root / "compliance").mkdir(parents=True)
    (root / "compliance" / "uno.md").write_text(OLD, encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "dos.md").write_text("# Dos\n\nOtro documento.\n", encoding="utf-8")
    tool = kb._tool()
    monkeypatch.setattr(tool.kb_embed, "disponible", lambda: False)
    return root, state, tool


def _stamp(state: Path) -> str:
    return (state / kb.CORPUS / kb.STAMP).read_text()


def _copied(state: Path) -> str:
    return (state / kb.CORPUS / "compliance" / "uno.md").read_text(encoding="utf-8")


def _sources(root: Path) -> str:
    return kb._fingerprint(
        [(str(path.relative_to(root)), path.read_bytes()) for path in kb.sources(root)]
    )


def test_the_stamp_is_of_what_was_copied_even_if_a_document_changes_meanwhile(
    docs: tuple[Path, Path, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, state, tool = docs
    edited: list[bool] = []
    calls: list[bool] = []

    def edit_while_refreshing() -> bool:
        # Otra sesión edita el documento en plena actualización, después de leerlo: la tercera
        # pregunta por el modelo es la de la reindexación, ya leídos los documentos (las dos
        # primeras son las de «¿está al día?», fuera y dentro del cerrojo entre procesos).
        calls.append(True)
        if len(calls) == 3:
            (root / "compliance" / "uno.md").write_text(NEW, encoding="utf-8")
            edited.append(True)
        return False

    monkeypatch.setattr(tool.kb_embed, "disponible", edit_while_refreshing)
    assert kb._refresh(root, state)["rebuilt"] is True
    assert edited
    # La huella es la de lo copiado e indexado (el texto viejo), no la del texto de después.
    assert _copied(state) == OLD
    assert _stamp(state) != _sources(root) + kb.WORDS
    # Así, la siguiente vez se ve el cambio y se reindexa...
    assert kb._refresh(root, state)["rebuilt"] is True
    assert _copied(state) == NEW and _stamp(state) == _sources(root) + kb.WORDS
    # ...y si el documento vuelve a su texto de antes, también: la huella sigue a lo indexado.
    (root / "compliance" / "uno.md").write_text(OLD, encoding="utf-8")
    assert kb._refresh(root, state)["rebuilt"] is True
    assert _copied(state) == OLD
    assert kb._refresh(root, state)["rebuilt"] is False


def test_a_build_that_did_not_replace_the_index_writes_no_stamp(
    docs: tuple[Path, Path, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, state, tool = docs
    assert kb._refresh(root, state)["rebuilt"] is True
    (root / "compliance" / "uno.md").write_text(NEW, encoding="utf-8")
    # `build()` de Polaris sale en verde sin hacer nada si otro proceso tiene su cerrojo.
    monkeypatch.setattr(tool, "build", lambda: 0)
    result = kb._refresh(root, state)
    # Se sirve el índice que hay, pero no se firma como si fuera el de estos documentos.
    assert result["rebuilt"] is False and result["available"] is True
    assert "otro proceso" in result["note"]
    assert not (state / kb.CORPUS / kb.STAMP).exists()
    monkeypatch.undo()
    monkeypatch.setattr(tool.kb_embed, "disponible", lambda: False)
    # El siguiente intento reindexa de verdad, en vez de dar por bueno el índice viejo.
    assert kb._refresh(root, state)["rebuilt"] is True
    assert _stamp(state) == _sources(root) + kb.WORDS


def test_vectors_are_stamped_only_when_this_build_wrote_them(
    docs: tuple[Path, Path, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, state, tool = docs
    monkeypatch.setattr(tool.kb_embed, "disponible", lambda: True)
    written: list[bool] = []
    attempts: list[bool] = []

    def vectors(rows: list[Any], path: str) -> None:
        # Como `_build_vectors` de Polaris: si no puede, borra el fichero y deja solo palabras.
        attempts.append(True)
        if written:
            Path(path).write_bytes(b"vectores")
        else:
            Path(path).unlink(missing_ok=True)

    monkeypatch.setattr(tool, "_build_vectors", vectors)
    failed = kb._refresh(root, state)
    assert failed["rebuilt"] is True and failed["semantic"] is False
    assert _stamp(state) == _sources(root) + kb.VECTORS_FAILED
    assert not kb._indexed_vectors(tool)
    # Se dice, y no se reintenta en cada búsqueda: rehacer el índice entero en cada consulta
    # sería peor que ordenar por palabras hasta el siguiente cambio de la documentación.
    assert kb._refresh(root, state)["rebuilt"] is False
    assert len(attempts) == 1
    written.append(True)
    (root / "compliance" / "uno.md").write_text(NEW, encoding="utf-8")
    done = kb._refresh(root, state)
    assert done["rebuilt"] is True and done["semantic"] is True
    assert _stamp(state) == _sources(root) + kb.VECTORS
    assert kb._indexed_vectors(tool)
    assert kb._refresh(root, state)["rebuilt"] is False
    # Una huella «con vectores» sin su fichero de vectores no se da por buena.
    Path(tool.VEC).unlink()
    assert not kb._indexed_vectors(tool)
    assert kb._refresh(root, state)["rebuilt"] is True


def _holder(lock: Path, seconds: float) -> subprocess.Popen[str]:
    backend = Path(kb.__file__).resolve().parents[1]
    code = (
        "import sys, time\n"
        f"sys.path.insert(0, {str(backend)!r})\n"
        "from pathlib import Path\n"
        "from app.kb import _across_processes\n"
        "with _across_processes(Path(sys.argv[1]), time.monotonic() + 60):\n"
        "    print('dentro', flush=True)\n"
        f"    time.sleep({seconds})\n"
    )
    return subprocess.Popen(
        [sys.executable, "-c", code, str(lock)], stdout=subprocess.PIPE, text=True,
    )


def test_a_refresh_waits_while_another_process_has_the_corpus(
    docs: tuple[Path, Path, Any],
) -> None:
    root, state, _tool = docs
    holder = _holder(state / kb.REFRESH_LOCK, 2.0)
    try:
        assert holder.stdout is not None
        # Si el proceso muere sin decir nada, `readline` devuelve "" y la prueba falla aquí.
        assert holder.stdout.readline().strip() == "dentro"
        started = time.monotonic()
        assert kb._refresh(root, state)["rebuilt"] is True
        waited = time.monotonic() - started
        assert waited > 1.0, waited
    finally:
        try:
            holder.wait(timeout=60)
        except subprocess.TimeoutExpired:
            holder.kill()
            raise


def test_the_wait_for_another_process_has_a_limit_and_a_clear_error(
    docs: tuple[Path, Path, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin tope, una búsqueda esperaba para siempre a un proceso atascado, y con ella las demás
    del mismo proceso, detrás del cerrojo de hilos (§5.37.11, «Queda»)."""
    root, state, _tool = docs
    monkeypatch.setattr(kb, "REFRESH_WAIT_S", 0.5)
    holder = _holder(state / kb.REFRESH_LOCK, 20.0)
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "dentro"
        started = time.monotonic()
        with pytest.raises(kb.RefreshBusyError, match="no lo ha soltado en 0.5 s") as busy:
            kb._refresh(root, state)
        assert time.monotonic() - started < 10
        # El mensaje llega a la API: sin la ruta de la carpeta, que dice el usuario del equipo.
        assert str(state) not in str(busy.value)
        assert not isinstance(busy.value, OSError)
        # No se tocó el corpus, y el cerrojo de hilos queda libre para las demás búsquedas.
        assert not (state / kb.CORPUS).exists()
        assert kb._LOCK.acquire(blocking=False)
        kb._LOCK.release()
    finally:
        holder.kill()
        holder.wait(timeout=60)
    # Muerto el otro proceso, el sistema suelta su cerrojo y se reindexa.
    assert kb._refresh(root, state)["rebuilt"] is True


def test_a_search_queued_behind_another_one_of_this_process_also_has_the_limit(
    docs: tuple[Path, Path, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otra búsqueda del mismo proceso con el cerrojo de hilos tomado: la que espera detrás no
    espera más que el tope (no el tope por cada una que tenga delante)."""
    root, state, _tool = docs
    monkeypatch.setattr(kb, "REFRESH_WAIT_S", 0.3)
    # La búsqueda que espera va en otro hilo y se la espera con plazo: con el cerrojo pedido sin
    # tope, el mismo hilo que lo tiene se quedaría colgado para siempre (y la prueba con él, en vez
    # de ponerse roja; pasó en la campaña de mutantes).
    outcome: list[BaseException | dict[str, Any]] = []

    def queued() -> None:
        try:
            outcome.append(kb._refresh(root, state))
        except BaseException as exc:  # noqa: BLE001 — se mira abajo, en el hilo de la prueba
            outcome.append(exc)

    assert kb._LOCK.acquire(blocking=False)
    try:
        worker = threading.Thread(target=queued, daemon=True)
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive(), "la búsqueda en cola espera al cerrojo de hilos sin tope"
    finally:
        kb._LOCK.release()
    worker.join(timeout=60)
    assert len(outcome) == 1
    assert isinstance(outcome[0], kb.RefreshBusyError)
    assert "otra búsqueda de este proceso" in str(outcome[0])
    assert kb._refresh(root, state)["rebuilt"] is True


def test_the_route_says_the_index_is_busy_with_a_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def busy(query: str, k: int = 6) -> dict[str, Any]:
        raise kb.RefreshBusyError("otro proceso lleva más de 300 s reindexando la documentación")

    monkeypatch.setattr(kb, "search", busy)
    response = client.get("/api/kb", params={"q": "IEC 62304"})
    assert response.status_code == 503
    assert "otro proceso" in response.json()["detail"]


def test_a_search_is_not_called_semantic_without_vectors_in_the_index(
    docs: tuple[Path, Path, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, state, tool = docs
    monkeypatch.setattr(tool.kb_embed, "disponible", lambda: True)

    def no_vectors(rows: list[Any], path: str) -> None:
        Path(path).unlink(missing_ok=True)

    monkeypatch.setattr(tool, "_build_vectors", no_vectors)
    assert kb._refresh(root, state)["semantic"] is False
    # La búsqueda sobre ese índice, con el modelo presente: ordena por palabras y lo dice.
    monkeypatch.setattr(kb, "refresh", lambda: {"available": True})
    monkeypatch.setattr(kb.polaris, "configure", lambda: state)
    monkeypatch.setattr(tool, "retrieve", lambda query, k, scope: [])
    assert kb.search("cualquier cosa")["semantic"] is False
