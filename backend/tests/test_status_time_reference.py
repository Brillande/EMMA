"""El "ahora" de `/api/status` no puede decidirlo una sola lectura.

El estado se evalua sobre las desviaciones de los ultimos dias, contados desde
la lectura mas reciente. Una sola lectura mal fechada —un reloj de dispositivo
roto, una importacion con la zona horaria equivocada— movia esa referencia: un
peso fechado en 2099 dejaba fuera todas las desviaciones de hoy, y una arritmia
en CONCERN pasaba a WATCH con la integridad en verde. Una lectura del año 1
tumbaba el endpoint.

El ledger es de solo anadir: una lectura asi, una vez dentro, se queda. El
analisis tiene que sobrevivirla, y decir que la ha apartado.
"""

import datetime as dt
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.routes import (
    _analysable,
    get_store,
    identity_for,
    new_store,
    reset_store,
)
from app.core.config import Settings, get_settings
from app.ingest.fhir import observation
from app.main import app


@pytest.fixture
def arrhythmia(tmp_path) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True
    )
    client = TestClient(app)
    client.post("/api/simulate", params={"scenario": "arrhythmia", "days": 40})
    yield client
    app.dependency_overrides.clear()
    reset_store(None)


def _ingest(client: TestClient, when: dt.datetime) -> None:
    response = client.post(
        "/api/observations",
        json={
            "subject": "crew-01",
            "key": "body-weight",
            "value": 72.0,
            "effective": when.isoformat(),
            "source": "manual",
        },
    )
    assert response.status_code == 201, response.text


def test_a_future_dated_reading_does_not_move_now(arrhythmia: TestClient) -> None:
    antes = arrhythmia.get("/api/status").json()
    assert antes["domains"]["cardiovascular"]["level"] == "concern"

    _ingest(arrhythmia, dt.datetime(2099, 1, 1, tzinfo=dt.UTC))
    despues = arrhythmia.get("/api/status").json()

    assert despues["domains"]["cardiovascular"]["level"] == "concern"
    assert despues["data"]["readings_ignored"]["after_reference"] == 1


def _weights(days: list[float]) -> list:
    inicio = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    return [
        observation(
            "body-weight", 72.0, inicio + dt.timedelta(days=d), "crew-01", "manual"
        )
        for d in days
    ]


def test_sparse_data_also_refuses_an_isolated_future_reading() -> None:
    """El caso que la primera version no cubria, y que la hacia inutil.

    Exigia tres lecturas en dos dias para corroborar. Con un peso cada cinco
    dias ninguna lo cumple, ninguna corrobora, y la referencia recaia otra vez en
    la ultima sin corroborar: el fallo que esta regla existe para impedir. Solo
    funcionaba con datos densos, que eran los del test de arriba.
    """
    disperso = _weights([0, 5, 10, 15, 20, 25, 30, 35, 40, 45])

    _, referencia, ignoradas = _analysable([*disperso, *_weights([26663])])

    assert referencia == disperso[-1].effective
    assert ignoradas["after_reference"] == 1


def test_a_gap_does_not_discard_the_data_that_comes_after() -> None:
    """El contrapeso: un hueco no es una fecha mala.

    Ni el muestreo espaciado ni un apagon de semanas pueden apartar lecturas
    buenas. Es lo que rompia el arreglo evidente —tomar la lectura mas antigua—,
    que anclaba el "ahora" al primer dia de la mision para siempre.
    """
    espaciado = _weights([0, 5, 10, 15, 20, 25, 30, 35, 40, 45])
    _, referencia, ignoradas = _analysable(espaciado)
    assert referencia == espaciado[-1].effective
    assert ignoradas["after_reference"] == 0

    tras_apagon = _weights([i / 24 for i in range(100)] + [60 + i / 24 for i in range(50)])
    _, referencia, ignoradas = _analysable(tras_apagon)
    assert referencia == tras_apagon[-1].effective
    assert ignoradas["after_reference"] == 0


def test_the_api_refuses_a_reading_from_year_one(arrhythmia: TestClient) -> None:
    response = arrhythmia.post(
        "/api/observations",
        json={
            "subject": "crew-01",
            "key": "body-weight",
            "value": 72.0,
            "effective": dt.datetime(1, 1, 2, tzinfo=dt.UTC).isoformat(),
            "source": "manual",
        },
    )
    assert response.status_code == 422


def test_a_reading_from_year_one_already_stored_does_not_break_status(
    arrhythmia: TestClient,
) -> None:
    """La ingesta ya la rechaza; pero una que entro antes de esa validacion se
    queda en el ledger para siempre, y el analisis tiene que sobrevivirla."""
    get_store().record(
        observation(
            "body-weight", 72.0, dt.datetime(1, 1, 2, tzinfo=dt.UTC), "crew-01", "manual"
        ),
        identity_for("manual"),
    )
    response = arrhythmia.get("/api/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domains"]["cardiovascular"]["level"] == "concern"
    assert body["data"]["readings_ignored"]["implausibly_old"] == 1
