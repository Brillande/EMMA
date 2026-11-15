"""Cabecera propia de los `POST` que una petición simple podría disparar: barrera, no autenticación.

Por qué existe: `POST /api/simulate` y `POST /api/comms/preload` no llevan cuerpo, y las dos
importaciones (`/import/apple-health`, `/import/google-fit`) leen el suyo tal cual, sin mirar su
tipo. Un `POST` así es una «petición simple» del navegador: cualquier página abierta en el mismo
navegador que la consola puede mandarlo con `fetch(..., {mode: "no-cors"})` o con un formulario,
y el navegador lo envía sin la comprobación previa (`OPTIONS`) de CORS. El CORS solo impide leer
la respuesta; la orden se ejecuta igual: una página ajena podía sustituir la sesión simulada,
lanzar una consulta a JPL Horizons o meter lecturas por una importación. Lo dejó escrito la
ronda 16 (E6) y el usuario decidió el 2026-10-31 exigir una cabecera propia.

Una cabecera fuera de la lista segura (`X-EMMA-Console`) convierte la petición en una con
comprobación previa: el navegador pregunta antes con `OPTIONS`, y el CORS de `app/main.py` —que
entre orígenes solo admite `GET`— la deniega; la orden no llega a salir. La consola
(`frontend/src/lib/api.ts`) la pone en todos sus `POST`; quien llame a mano añade
`-H "X-EMMA-Console: 1"`.

Lo que NO es: autenticación. El valor es fijo y público; no identifica a nadie ni autoriza nada.
La API sigue sin autenticar operadores (`compliance/record-integrity.md` §7.5), y el 403 lo dice.

Los `POST` con cuerpo JSON validado por Pydantic no la necesitan: una petición simple solo puede
llevar `text/plain`, un formulario, `multipart` o ningún `Content-Type` (un `Blob` sin tipo), y
FastAPI 0.141 no toma nada de eso como JSON (422 sin ejecutar nada; lo vigila una prueba, porque
depende de la versión instalada).

**La cobertura es parcial, a sabiendas.** La cabecera va en las cuatro rutas de `api/routes.py`
que una petición simple ejecutaba; fuera de ese fichero quedan otros `POST` igual de expuestos,
por decidir (`PENDING_SIMPLE` y `PENDING_RAW_DECLARED` en `tests/test_console_header.py`,
§5.39.23). Esa prueba comprueba también que ninguna ruta tiene la dependencia sin su parámetro en
OpenAPI ni al revés.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request

CONSOLE_HEADER = "X-EMMA-Console"
CONSOLE_HEADER_VALUE = "1"

MISSING_DETAIL = (
    f"falta la cabecera {CONSOLE_HEADER}: {CONSOLE_HEADER_VALUE}. La pone la consola de EMMA en "
    f'cada POST; a mano, curl -H "{CONSOLE_HEADER}: {CONSOLE_HEADER_VALUE}". Sin ella, esta orden '
    "la podría mandar cualquier página abierta en el mismo navegador como petición simple, que el "
    "CORS no detiene. No es autenticación: la API no autentica a quien la llama."
)

PARAMETER_DESCRIPTION = (
    "Cabecera propia de la consola de EMMA, con este valor fijo. Sin ella, 403: es una barrera a "
    "la petición simple que otra página del navegador podría mandar, no autenticación (la API no "
    "autentica a quien la llama)."
)


def require_console_header(request: Request) -> None:
    """Deniega con 403, y su motivo, la orden que no traiga `X-EMMA-Console: 1`.

    Se lee la cabecera a mano y no con `Header(...)`: declarada como parámetro obligatorio, su
    falta saldría como un 422 de validación en inglés; declarada opcional, OpenAPI la enseñaría
    como opcional. Lo que OpenAPI enseña lo pone `console_header_openapi()`.
    """
    if request.headers.get(CONSOLE_HEADER) != CONSOLE_HEADER_VALUE:
        raise HTTPException(status_code=403, detail=MISSING_DETAIL)


CONSOLE_HEADER_DEPENDENCIES: list[Any] = [Depends(require_console_header)]


def console_header_openapi() -> dict[str, Any]:
    """El trozo de OpenAPI de una ruta cubierta, nuevo cada vez: FastAPI lo mezcla en la operación
    y así ninguna comparte sus diccionarios con otra."""
    return {
        "parameters": [
            {
                "in": "header",
                "name": CONSOLE_HEADER,
                "required": True,
                "schema": {"type": "string", "enum": [CONSOLE_HEADER_VALUE]},
                "description": PARAMETER_DESCRIPTION,
            }
        ],
        "responses": {
            "403": {"description": f"Sin la cabecera {CONSOLE_HEADER}: {CONSOLE_HEADER_VALUE}."}
        },
    }


def console_post(**openapi_extra: Any) -> dict[str, Any]:
    """Los dos argumentos del decorador de una ruta cubierta: `@router.post(..., **console_post())`.

    La dependencia y su trozo de OpenAPI (la cabecera como parámetro obligatorio, el 403 entre las
    respuestas) salen de aquí juntos, para que una ruta no pueda tener lo uno sin lo otro. Lo que
    la ruta quiera añadir a su OpenAPI (el `requestBody` de una importación) va como argumento,
    salvo `parameters` y `responses`: pisarían los de la cabecera y se rechazan al importar.
    """
    overridden = openapi_extra.keys() & {"parameters", "responses"}
    if overridden:
        raise ValueError(f"console_post pisaría {sorted(overridden)} de la cabecera")
    return {
        "dependencies": CONSOLE_HEADER_DEPENDENCIES,
        "openapi_extra": {**console_header_openapi(), **openapi_extra},
    }
