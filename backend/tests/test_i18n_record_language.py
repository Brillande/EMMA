"""Lo que EMMA firma no depende del idioma de quien lee (`compliance/record-integrity.md`,
«Idioma del registro»).

`GET /api/status` y otras lecturas firman asientos por su cuenta (instantáneas de predicción,
discrepancias de efemérides). Si ese texto saliera en el idioma de la petición, dos consolas en
idiomas distintos dejarían registros distintos. Aquí se siembra dos veces lo mismo, se lee todo
en castellano en una y en inglés en la otra, y los dos registros tienen que ser idénticos.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.api import routes
from app.core.ledger import SALT_FIELD
from tests.conftest import ENGLISH_HEADERS

READS = (
    "/api/status",
    "/api/indicators",
    "/api/alerts/history",
    "/api/habitat",
    "/api/risks",
)


def _ledger_after_reading(client: TestClient, headers: dict[str, str]) -> list[Any]:
    routes.reset_store(routes.new_store())
    seeded = client.post("/api/simulate", params={"scenario": "nominal", "seed": 7})
    assert seeded.status_code == 201, seeded.text
    answered = [client.get(path, headers=headers).status_code for path in READS]
    assert 200 in answered
    store = routes.get_store()
    # La sal de cada asiento es aleatoria a propósito: se compara lo demás.
    return [
        (entry.entry_type, {k: v for k, v in (entry.payload or {}).items() if k != SALT_FIELD})
        for entry in store.ledger.entries
    ]


def test_reading_in_english_signs_the_same_as_reading_in_spanish(client: TestClient) -> None:
    spanish = _ledger_after_reading(client, {})
    english = _ledger_after_reading(client, ENGLISH_HEADERS)
    assert len(spanish) > 10
    assert [kind for kind, _ in english] == [kind for kind, _ in spanish]
    assert english == spanish
