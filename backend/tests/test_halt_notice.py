"""El aviso del freno HALT de Polaris: lo compone el backend y la consola lo pinta sola.

Un freno olvidado no se nota (en Polaris paró una rutina semanas), y hasta ahora solo lo veía quien
leyera `GET /api/safe-mode`. El aviso tiene que decir lo que el freno es en EMMA y nada más: corta
la salida a internet, no es el modo seguro, no para las constantes ni el modelo local, la fecha es
la del fichero y se quita borrándolo. En modo sin red no se presenta como la causa del corte.

El fichero de freno vive en una carpeta temporal (nunca en la carpeta personal ni en el estado
real de EMMA), y sin red (invariante 3).
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import polaris
from app.api.safe_mode import EXIT_NAMES, halt_notice
from app.core import egress
from app.core.config import Settings, get_settings
from app.main import app

ON = {"active": True, "reason": "sospecha de fuga por la red", "declared_by": "CMO"}
OFF = {"active": False, "declared_by": "Comandante"}
FORGOTTEN = dt.datetime(2026, 9, 1, 12, 30, 15, tzinfo=dt.UTC)
FORGOTTEN_ISO = "2026-09-01T12:30:15+00:00"


@pytest.fixture
def halt(tmp_path: Path) -> Iterator[Path]:
    """El fichero de freno de EMMA, en una carpeta temporal mientras dura la prueba."""
    path = tmp_path / "estado" / ".HALT"
    path.parent.mkdir()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(polaris, "halt_file", lambda: path)
            polaris.load("borde")  # cada carga vuelve a confinar
            yield path
    finally:
        polaris.load("borde")  # con `halt_file` ya restaurado


@pytest.fixture
def online(client: TestClient, tmp_path: Path) -> TestClient:
    """La misma consola con red: el aviso no lleva la nota del modo sin red."""
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=False)
    return client


def _put(halt: Path) -> None:
    halt.write_text("prueba", encoding="utf-8")
    os.utime(halt, (FORGOTTEN.timestamp(), FORGOTTEN.timestamp()))


def _text(notice: dict[str, object]) -> str:
    details = notice["details"]
    assert isinstance(details, list)
    return " ".join([str(notice[key]) for key in ("title", "headline", "summary")] + details)


def test_without_the_brake_there_is_no_notice(client: TestClient, halt: Path) -> None:
    assert client.get("/api/safe-mode").json()["halt"]["notice"] is None
    assert halt_notice(egress.halt_state(), offline=False) is None


def test_with_the_brake_the_notice_says_what_it_is_since_when_and_how_it_goes(
    online: TestClient, halt: Path
) -> None:
    _put(halt)
    notice = online.get("/api/safe-mode").json()["halt"]["notice"]
    assert notice["title"] == "Freno HALT de Polaris"
    assert notice["since"] == FORGOTTEN_ISO  # la del fichero, que la consola formatea
    assert "sin firma" in notice["since_label"]
    text = _text(notice)
    # Qué es, y qué no: no es el modo seguro, y levantar este no lo quita.
    assert "no el modo seguro" in text and "levantar el modo seguro no lo quita" in text
    # Qué deja de hacer: la salida a internet, por la puerta de salida, de cada fuente.
    assert "sin salida a internet" in notice["headline"]
    for exit_ in ("DONKI", "OSDR", "JPL Horizons", "citas"):
        assert exit_ in text, exit_
    # Qué no: las constantes, el análisis, las alertas y el modelo local siguen.
    for kept in ("constantes", "análisis", "alertas", "modelo local"):
        assert kept in notice["summary"], kept
    # Cómo se quita: borrando ese fichero, y no desde la consola.
    assert str(halt) in text and "borrando" in text
    # Con red, el freno es el que corta: nada de la nota del modo sin red.
    assert "modo sin red" not in text


def test_in_offline_mode_the_notice_does_not_claim_to_be_the_cause(
    client: TestClient, halt: Path
) -> None:
    """Sin red (el nominal de misión) ya no salía nada: el aviso lo dice, sin exagerar."""
    _put(halt)
    notice = client.get("/api/safe-mode").json()["halt"]["notice"]
    text = _text(notice)
    assert "modo sin red" in text and "con freno o sin él" in text
    assert halt_notice(egress.halt_state(), offline=False) != halt_notice(
        egress.halt_state(), offline=True
    )


def test_the_notice_survives_lifting_safe_mode_and_goes_when_the_file_goes(
    online: TestClient, halt: Path
) -> None:
    _put(halt)
    online.post("/api/safe-mode", json=ON)
    lifted = online.post("/api/safe-mode", json=OFF).json()
    assert lifted["active"] is False and lifted["halt"]["notice"]["since"] == FORGOTTEN_ISO
    halt.unlink()
    assert online.get("/api/safe-mode").json()["halt"]["notice"] is None


def test_the_notice_names_every_exit_the_gate_has(
    online: TestClient, halt: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lo que corta sale de `egress.ALLOWLIST`, la única lista de lo que sale: cada propósito
    tiene nombre legible, y uno nuevo sale en el aviso aunque sea por su clave."""
    assert set(EXIT_NAMES) == set(egress.ALLOWLIST)
    _put(halt)
    monkeypatch.setitem(egress.ALLOWLIST, "registro-nuevo", frozenset({"example.org"}))
    text = _text(online.get("/api/safe-mode").json()["halt"]["notice"])
    for name in [*EXIT_NAMES.values(), "registro-nuevo"]:
        assert name in text, name


def test_the_notice_is_information_not_an_order() -> None:
    """Invariante 7, por extensión: el aviso informa; no manda a nadie hacer nada."""
    notice = halt_notice({"active": True, "file": "estado/.HALT", "since": FORGOTTEN_ISO}, False)
    assert notice is not None
    text = _text(notice).lower()
    for order in ("borre ", "debe ", "tiene que", "elimine", "active ", "desactive"):
        assert order not in text, order
