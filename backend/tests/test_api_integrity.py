"""La API ante un registro cuya integridad ya no se sostiene.

`query()` se niega a entregar un asiento cuyo contenido no casa con su hash
firmado. Esa negativa tiene que llegar a quien consulta como lo que es —
integridad comprometida, y en que asiento—, no como un 500 generico que se
confunde con cualquier otro fallo del servidor.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.routes import reset_store
from app.core.config import Settings, get_settings
from app.core.storage import ObservationStore
from app.main import app


@pytest.fixture
def tampered(tmp_path) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    store = ObservationStore.in_memory()
    reset_store(store)
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True
    )
    client = TestClient(app)
    client.post(
        "/api/simulate",
        params={"scenario": "nominal", "days": 1, "samples_per_day": 2},
    )
    # `ledger[i]` devuelve una copia: se manipula el estado interno, que es lo que
    # un fallo de memoria o de programacion alteraria.
    store.ledger._entries[2].payload["value"] = 140.0  # type: ignore[index]
    yield client
    app.dependency_overrides.clear()
    reset_store(None)


@pytest.mark.parametrize("path", ["/api/status", "/api/observations"])
def test_a_tampered_record_is_reported_not_crashed(
    tampered: TestClient, path: str
) -> None:
    response = tampered.get(path)

    assert response.status_code == 409
    body = response.json()
    assert "integridad comprometida" in body["detail"]
    assert "asiento 2" in body["detail"]
    assert body["integrity_ok"] is False
