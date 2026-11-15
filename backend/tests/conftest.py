"""Fixtures compartidas por las pruebas del borrador de interpretación y de su firma, y la
cabecera con la que nace todo `TestClient` de la suite.

Los módulos que definen su propio `client` lo siguen usando: una fixture del módulo tapa a la de
este fichero.

**La cabecera de la consola.** `POST /api/simulate`, `/api/comms/preload` y las dos
importaciones exigen `X-EMMA-Console: 1` (`app/api/console_header.py`, §5.39.23). Más de
ochenta ficheros de pruebas siembran con `/api/simulate`, y cerca de sesenta construyen su
propio `TestClient(app)`: ponerla en cada construcción repetiría lo mismo decenas de veces y cada
prueba nueva lo olvidaría. Aquí el `TestClient` de la suite nace con la cabecera puesta, como
nace la consola (`frontend/src/lib/api.ts`), y una cabecera dada al construirlo manda sobre ella.
La prueba que quiere ver el 403 la quita (`tests/test_console_header.py`); nada más la toca.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.console_header import CONSOLE_HEADER, CONSOLE_HEADER_VALUE
from app.api.routes import new_store, reset_store
from app.assistant import catalog as assistant_catalog
from app.core import i18n
from app.core.config import Settings, get_settings
from app.main import app

_TESTCLIENT_INIT = TestClient.__init__


def _init_with_console_header(
    self: TestClient, *args: Any, headers: Mapping[str, str] | None = None, **kwargs: Any
) -> None:
    # `httpx.Headers` no distingue mayúsculas: `x-emma-console` dada al construir sustituye a la
    # de la suite en vez de viajar duplicada (y entonces el servidor leería la primera).
    merged = httpx.Headers({CONSOLE_HEADER: CONSOLE_HEADER_VALUE})
    merged.update(headers or {})
    _TESTCLIENT_INIT(self, *args, headers=merged, **kwargs)


TestClient.__init__ = _init_with_console_header  # type: ignore[method-assign]

# La suite corre en castellano: es el idioma de sus asertos, de las campañas de mutantes y del
# registro. `app.main` deja puesto el de `EMMA_LANG` (inglés) al importarse, y aquí se devuelve.
# El inglés se prueba pidiéndolo: la fixture `english`, o la cabecera `ENGLISH_HEADERS`.
i18n.set_default("es")
assistant_catalog.use_set_aside(False)
ENGLISH_HEADERS = {i18n.HEADER: "en"}


@pytest.fixture(autouse=True)
def _spanish_by_default() -> Iterator[None]:
    """Cada prueba empieza en castellano aunque la anterior cambiara el idioma por defecto."""
    i18n.set_default("es")
    yield
    i18n.set_default("es")


@pytest.fixture
def english() -> Iterator[None]:
    """El cuerpo de la prueba corre en inglés (llamadas directas, sin pasar por la API)."""
    with i18n.use("en"):
        yield


@pytest.fixture(autouse=True)
def _no_local_spice_kernels(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Ninguna prueba calcula con los núcleos SPICE que haya bajado quien la corre (`data/spice`).

    El cálculo local del retardo (`environment/spice.py`) sirve los días sin efeméride de JPL
    Horizons en caché si hay `spiceypy` y núcleos: sin esto, el resultado de una prueba
    dependería de lo instalado en la máquina. Las pruebas de SPICE fijan su propia carpeta.
    """
    from app.environment import spice

    spice.KERNEL_DIR = tmp_path_factory.getbasetemp() / "spice-sin-nucleos"
    yield
    spice.KERNEL_DIR = None


@pytest.fixture(autouse=True)
def _empty_ble_rr_window() -> Iterator[None]:
    """Cada prueba empieza sin intervalos R-R de otra: la ventana de HRV vive en el proceso."""
    from app.ingest.wearable import BLE_RR_WINDOW

    BLE_RR_WINDOW.clear()
    yield
    BLE_RR_WINDOW.clear()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, assistant_warmup=False
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


@pytest.fixture
def measured(client: TestClient) -> int:
    study = client.post("/api/imaging/phantom", params={"protocol": "optic-nerve"}).json()
    index = int(study["ledger_index"])
    response = client.post(
        f"/api/imaging/studies/{index}/measurements",
        json={
            "measure": "onsd", "laterality": "right", "measured_by": "CMO",
            "annotations": {
                "globe": {"points": [[200, 110]]},
                "sheath": {"points": [[145, 170], [255, 170]]},
            },
        },
    )
    assert response.status_code == 201, response.text
    return index
