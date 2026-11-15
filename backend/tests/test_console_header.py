"""La cabecera propia de los `POST` que una petición simple podría disparar (§5.39.23).

Qué se comprueba: sin `X-EMMA-Console: 1`, 403 con su motivo en español y nada escrito; con
ella, lo de siempre; otro valor no vale; el 403 gana a la validación (sin la cabecera no se
sondea nada); las rutas con cuerpo JSON validado no la piden, porque una petición simple no les
llega como JSON (422 sin ejecutar nada); OpenAPI la enseña como parámetro obligatorio y ninguna
ruta tiene la dependencia sin el parámetro ni al revés; todo `POST` sin cuerpo declarado está
cubierto o apuntado como pendiente a sabiendas; el CORS refleja la cabecera en la comprobación
previa y sigue denegando un `POST` entre orígenes; y el `TestClient` de la suite nace con ella
puesta (`conftest.py`).
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import app.api as app_api
from app.api.console_header import (
    CONSOLE_HEADER,
    CONSOLE_HEADER_VALUE,
    MISSING_DETAIL,
    PARAMETER_DESCRIPTION,
    console_post,
)
from app.api.routes import get_store
from app.main import app
from app.text_guard import check as check_text

# Las rutas cubiertas: sin cuerpo, o con un cuerpo que se lee tal cual sin mirar su tipo.
GUARDED = {
    "/api/simulate",
    "/api/comms/preload",
    "/api/import/apple-health",
    "/api/import/google-fit",
    "/api/import/observations",
    # El planificador (Marplanner): su POST reenvía el cuerpo tal cual (2026-11-12).
    "/api/planner/app/{path}",
    # El audio de un turno del asistente: cuerpo leído tal cual (2026-11-03).
    "/api/assistant/audio",
    # Pregunta a NTRS por los informes del registro (2026-11-11): sin cuerpo.
    "/api/dossier/ntrs/refresh",
    # El inventario firmado (2026-11-14): cuerpo JSON validado, pero el contrato del lote
    # «reservas» pide la cabecera en sus dos POST.
    "/api/inventory/count",
    "/api/inventory/resupply",
    # La lectura IA de las correlaciones (2026-11-15): cuerpo JSON validado, pero pone a trabajar al
    # modelo local; otra página del navegador no debe poder pedirla.
    "/api/correlations/reading",
    # «Descargar modelos» (2026-11-15): consultar y bajar salen a internet y escriben en disco;
    # otra página del navegador no debe poder lanzarlo.
    "/api/models-pack/check",
    "/api/models-pack/download",
    "/api/models-pack/cancel",
}
# Las cubiertas que no llevan cuerpo (las demás de `GUARDED` lo leen tal cual).
BODYLESS = {
    "/api/simulate", "/api/comms/preload", "/api/dossier/ntrs/refresh",
    "/api/models-pack/check", "/api/models-pack/cancel",
}
# Las cubiertas con cuerpo JSON validado: no las ejecuta una petición simple, pero su contrato
# pide la cabecera igual (el inventario firmado, 2026-11-14).
JSON_GUARDED = {
    "/api/inventory/count", "/api/inventory/resupply", "/api/correlations/reading",
    "/api/models-pack/download",
}
# Los POST sin cuerpo declarado en OpenAPI que una petición simple ejecuta y esta unidad no cubre,
# todos fuera de `api/routes.py`: sin cuerpo, o con un cuerpo leído tal cual que OpenAPI no declara.
# Decisión del usuario pendiente (§5.39.23). Un POST nuevo sin cuerpo y sin la cabecera hace fallar
# la prueba de abajo hasta que se cubra o se apunte aquí a sabiendas.
PENDING_SIMPLE = {
    "/api/imaging/phantom",
    "/api/imaging/samples/{key}",
    "/api/imaging/studies/{ledger_index}/draft",
    "/api/pain/voice",
    "/api/replay/inspiration4",
    "/api/reports",  # sí mira el tipo del cuerpo (415 a `text/plain`), pero sin cabecera
    "/api/volumes",
    "/api/volumes/samples/{key}",
    "/api/volumes/{ledger_index}/segment",
}
# Lo único que una petición simple puede declarar de su cuerpo (junto a formulario y multipart).
TEXT_PLAIN = {"content-type": "text/plain"}
# Declaran cuerpo en OpenAPI y lo leen tal cual: la prueba de `requestBody` no los ve y la del
# código fuente sí. Decisión pendiente, como `PENDING_SIMPLE`.
PENDING_RAW_DECLARED = {"/api/imaging/studies"}
ANOTHER_PAGE = "http://otra-pagina.example"
IMPORTS = (
    ("/api/import/apple-health", b"<HealthData></HealthData>"),
    ("/api/import/observations", b"[]"),
    ("/api/import/google-fit", b'{"point": []}'),
)


def _bare(client: TestClient) -> TestClient:
    """El mismo cliente, sin la cabecera que `conftest.py` le pone al nacer."""
    del client.headers[CONSOLE_HEADER]
    return client


# --- Las rutas cubiertas ----------------------------------------------------------------------


def test_without_the_header_the_simulation_is_refused_with_its_reason_and_writes_nothing(
    client: TestClient,
) -> None:
    response = _bare(client).post(
        "/api/simulate", params={"scenario": "nominal", "replace": "true"}
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail == MISSING_DETAIL
    assert "falta la cabecera X-EMMA-Console: 1" in detail
    assert "No es autenticación" in detail
    assert len(get_store().ledger) == 0


def test_what_a_simple_request_from_another_page_looks_like_here_is_refused(
    client: TestClient,
) -> None:
    """Lo que llega de un `fetch(..., {mode: "no-cors"})` de otra página: `Origin` ajeno, sin la
    cabecera. El CORS no lo frena (solo esconde la respuesta); la cabecera sí."""
    response = _bare(client).post(
        "/api/simulate",
        params={"scenario": "nominal", "replace": "true"},
        headers={"Origin": ANOTHER_PAGE},
    )
    assert response.status_code == 403
    assert len(get_store().ledger) == 0


def test_with_the_header_the_simulation_loads(client: TestClient) -> None:
    assert client.headers[CONSOLE_HEADER] == CONSOLE_HEADER_VALUE
    response = client.post("/api/simulate", params={"scenario": "nominal", "days": 2})
    assert response.status_code == 201, response.text
    assert response.json()["recorded"] > 0


def test_another_value_is_not_the_header(client: TestClient) -> None:
    for value in ("0", "true", "", "yes", CONSOLE_HEADER):
        response = client.post(
            "/api/simulate",
            params={"scenario": "nominal", "days": 1},
            headers={CONSOLE_HEADER: value},
        )
        assert response.status_code == 403, (value, response.status_code)
    assert len(get_store().ledger) == 0


def test_the_refusal_comes_before_validation(client: TestClient) -> None:
    """Sin la cabecera no se sondea nada: ni qué escenarios existen ni qué parámetros valen."""
    response = _bare(client).post("/api/simulate", params={"scenario": "no-existe", "days": 0})
    assert response.status_code == 403


def test_the_preload_asks_for_the_header_first_and_then_for_the_network(
    client: TestClient,
) -> None:
    """Con la cabecera, lo de siempre en modo sin red: el 503 de la puerta de salida, no un 403."""
    assert client.post("/api/comms/preload").status_code == 503
    assert _bare(client).post("/api/comms/preload").status_code == 403


def test_the_imports_read_a_text_plain_body_so_they_ask_for_the_header_too(
    client: TestClient,
) -> None:
    """`_read_capped` lee el cuerpo sin mirar su tipo: una petición simple con `text/plain` lo
    ejecutaba. Con la cabecera con la que nace el cliente, la importación hace lo suyo con ese
    cuerpo (aquí, uno sin lecturas: su 422 de siempre); sin ella, 403 y nada escrito."""
    for path, body in IMPORTS:
        response = client.post(path, content=body, headers=TEXT_PLAIN)
        assert response.status_code == 422, (path, response.text)
        assert "no hay ninguna lectura" in response.text
    bare = _bare(client)
    for path, body in IMPORTS:
        assert bare.post(path, content=body, headers=TEXT_PLAIN).status_code == 403, path
    assert len(get_store().ledger) == 0


# --- Las que no la necesitan ----------------------------------------------------------------


def test_a_json_body_route_needs_no_header_because_a_simple_request_is_not_json(
    client: TestClient,
) -> None:
    """`/api/observations` valida su cuerpo con Pydantic: para FastAPI, `text/plain` no es JSON
    (422, nada escrito), y `application/json` —que ya exige comprobación previa— entra sin la
    cabecera. Por eso la cabecera no va en todos los POST."""
    bare = _bare(client)
    reading = {"key": "heart-rate", "value": 64.0, "subject": "crew-01"}
    simple = bare.post(
        "/api/observations",
        content=json.dumps(reading),
        headers={**TEXT_PLAIN, "Origin": ANOTHER_PAGE},
    )
    assert simple.status_code == 422
    assert len(get_store().ledger) == 0
    assert bare.post("/api/observations", json=reading).status_code == 201


def test_a_json_body_route_does_not_take_a_body_without_content_type(client: TestClient) -> None:
    """Un `Blob` sin tipo sale sin `Content-Type` y sin comprobación previa. FastAPI antiguo lo
    tomaría como JSON y la frase de arriba dejaría de ser cierta: si cambia, esto se pone en rojo.
    """
    reading = {"key": "heart-rate", "value": 64.0, "subject": "crew-01"}
    response = _bare(client).post("/api/observations", content=json.dumps(reading))
    assert "content-type" not in response.request.headers
    assert response.status_code == 422
    assert len(get_store().ledger) == 0


# --- OpenAPI: la dependencia y el parámetro, siempre juntos ---------------------------------


def test_openapi_shows_the_header_as_required_exactly_where_a_bare_post_is_refused(
    client: TestClient,
) -> None:
    """Cada POST de la API, mandado sin cabecera y sin cuerpo: 403 si y solo si OpenAPI enseña la
    cabecera como parámetro obligatorio y el 403 entre sus respuestas. Así ninguna ruta tiene la
    dependencia sin su parámetro ni al revés, y la lista de rutas cubiertas es la de arriba. (Lo
    demás responde lo suyo, nunca un 403; qué rutas ejecutaría una petición simple lo dice la
    prueba siguiente, no esta: un 422 por un parámetro que falta no prueba nada de eso.)"""
    bare = _bare(client)
    refused: set[str] = set()
    for path, operations in app.openapi()["paths"].items():
        for method, operation in operations.items():
            params: list[dict[str, Any]] = [
                p for p in operation.get("parameters", []) if p["name"] == CONSOLE_HEADER
            ]
            if method != "post":
                assert not params, (method, path)
                continue
            response = bare.post(re.sub(r"\{[^}]+\}", "0", path))
            shown = bool(params)
            assert shown == (response.status_code == 403), (path, response.status_code)
            assert shown == ("403" in operation["responses"]), path
            if shown:
                refused.add(path)
                (param,) = params
                assert param["in"] == "header"
                assert param["required"] is True
                assert param["schema"]["enum"] == [CONSOLE_HEADER_VALUE]
                assert param["description"] == PARAMETER_DESCRIPTION
    assert refused == GUARDED


def test_every_post_without_a_declared_body_is_covered_or_listed_as_pending() -> None:
    """Un POST sin `requestBody` en OpenAPI lo ejecuta una petición simple (no tiene cuerpo, o lo
    lee tal cual sin declararlo). O lleva la cabecera, o está en `PENDING_SIMPLE` a sabiendas."""
    without_body = {
        path
        for path, operations in app.openapi()["paths"].items()
        if "post" in operations and "requestBody" not in operations["post"]
    }
    assert without_body == BODYLESS | PENDING_SIMPLE
    assert not (GUARDED & PENDING_SIMPLE)


def test_every_route_that_reads_its_raw_body_is_covered_or_listed_as_pending() -> None:
    """Quien lee el cuerpo con `_read_capped` no mira su tipo, aunque declare `requestBody`: lo
    ejecuta una petición simple con `text/plain`. Esto lo mira en el código de la ruta."""
    routers = [
        router
        for info in pkgutil.iter_modules(app_api.__path__, f"{app_api.__name__}.")
        for router in vars(importlib.import_module(info.name)).values()
        if isinstance(router, APIRouter)
    ]
    raw = {
        # Sin el conversor de Starlette (`{path:path}`): OpenAPI la nombra `{path}`.
        "/api" + re.sub(r":\w+}", "}", route.path)
        for router in routers
        for route in router.routes
        if isinstance(route, APIRoute)
        and "POST" in route.methods
        and "_read_capped(" in inspect.getsource(route.endpoint)
    }
    assert raw >= GUARDED - BODYLESS - JSON_GUARDED  # la búsqueda encuentra algo
    assert raw - GUARDED - PENDING_SIMPLE == PENDING_RAW_DECLARED


def test_console_post_refuses_what_would_overwrite_the_header_openapi() -> None:
    for key in ("parameters", "responses"):
        with pytest.raises(ValueError, match=key):
            console_post(**{key: {}})


def test_the_console_sends_the_header_this_backend_asks_for() -> None:
    """`frontend/src/lib/api.ts` lleva su copia del nombre y del valor: si una se mueve sin la
    otra, cada suite sigue en verde contra sí misma y la consola se queda en 403."""
    api_ts = Path(__file__).parents[2] / "frontend" / "src" / "lib" / "api.ts"
    if not api_ts.exists():
        pytest.skip("copia de `scripts/mutants.py`, que no lleva el frontend")
    source = api_ts.read_text(encoding="utf-8")
    assert f'export const CONSOLE_HEADER = "{CONSOLE_HEADER}";' in source
    assert f'export const CONSOLE_HEADER_VALUE = "{CONSOLE_HEADER_VALUE}";' in source


def test_the_texts_pass_the_language_filter() -> None:
    for text in (MISSING_DETAIL, PARAMETER_DESCRIPTION):
        assert check_text(text) == [], text


# --- CORS -----------------------------------------------------------------------------------


def test_cors_mirrors_the_header_in_the_preflight_and_still_denies_a_cross_origin_post(
    client: TestClient,
) -> None:
    """La consola en :5173 no cruza orígenes (Vite hace de proxy a /api). Si cruzara,
    `allow_headers=["*"]` ya refleja la cabecera en la comprobación previa; y un POST sigue
    denegado por el método, que es lo que hace de la cabecera una barrera: con ella, la orden de
    otra página deja de ser simple, llega aquí como comprobación previa y se deniega."""

    def preflight(origin: str, method: str) -> Any:
        return client.options(
            "/api/simulate",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": CONSOLE_HEADER.lower(),
            },
        )

    allowed = preflight("http://localhost:5173", "GET")
    assert allowed.status_code == 200, allowed.text
    assert allowed.headers["access-control-allow-headers"] == CONSOLE_HEADER.lower()
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = preflight("http://localhost:5173", "POST")
    assert denied.status_code == 400 and "method" in denied.text
    foreign = preflight(ANOTHER_PAGE, "POST")
    assert foreign.status_code == 400 and "origin" in foreign.text and "method" in foreign.text


# --- La suite -------------------------------------------------------------------------------


def test_the_suite_client_is_born_with_the_header_and_a_given_one_wins(
    client: TestClient,
) -> None:
    """También con otra grafía: `x-emma-console: 0` sustituye a la de la suite en vez de viajar
    duplicada (el servidor leería la primera, y el 403 esperado sería un 201)."""
    assert TestClient(app).headers[CONSOLE_HEADER] == CONSOLE_HEADER_VALUE
    custom = TestClient(app, headers={"X-Otra": "a"})
    assert custom.headers[CONSOLE_HEADER] == CONSOLE_HEADER_VALUE
    assert custom.headers["X-Otra"] == "a"
    lower = TestClient(app, headers={"x-emma-console": "0"})
    assert lower.headers.get_list(CONSOLE_HEADER) == ["0"]
    one_day = {"scenario": "nominal", "days": 1}
    assert lower.post("/api/simulate", params=one_day).status_code == 403
    assert client.post("/api/simulate", params=one_day).status_code == 201
