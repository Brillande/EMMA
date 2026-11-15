"""La interfaz compilada, servida desde el mismo origen que la API.

Es como corre la aplicacion de escritorio. Lo que no puede pasar: que un fichero
tape una ruta de la API, o que una ruta de la API que no existe devuelva la pagina
con un 200 en vez de su 404.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.main import mount_frontend


def _app(dist: Path | None) -> tuple[FastAPI, bool]:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app, mount_frontend(app, dist)


def _dist(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<!doctype html><title>EMMA</title>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('emma')", encoding="utf-8")
    return tmp_path


def test_the_interface_is_served_at_the_root(tmp_path: Path) -> None:
    app, mounted = _app(_dist(tmp_path))
    client = TestClient(app)

    assert mounted
    assert "<title>EMMA</title>" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200


def test_the_api_is_not_shadowed_by_the_interface(tmp_path: Path) -> None:
    app, _ = _app(_dist(tmp_path))
    client = TestClient(app)

    assert client.get("/api/health").json() == {"status": "ok"}


def test_an_unknown_api_route_is_still_a_404(tmp_path: Path) -> None:
    app, _ = _app(_dist(tmp_path))
    response = TestClient(app).get("/api/no-existe")

    assert response.status_code == 404
    assert "EMMA" not in response.text


def test_without_a_build_only_the_api_is_served(tmp_path: Path) -> None:
    app, mounted = _app(tmp_path)  # directorio sin index.html
    client = TestClient(app)

    assert not mounted
    assert client.get("/").status_code == 404
    assert client.get("/api/health").status_code == 200


def test_no_directory_no_mount() -> None:
    _, mounted = _app(None)
    assert not mounted
