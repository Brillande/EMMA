"""El log no guarda contenido personal (especificación §12). Sin red.

Qué se prueba, y contra qué inventario: el de `app/core/log_privacy.py` (trazas de excepción,
líneas de acceso de uvicorn con su cadena de consulta, y los mensajes propios con argumentos).

  * Caminos con datos sensibles, capturando el log: un informe que falla al leerse con su texto
    en el mensaje del error, un trabajo de segmentación que revienta con un nombre en el mensaje,
    un NIfTI rechazado por llevar la identidad declarada del tripulante y la comprobación de
    datos personales rota; y el sexo declarado, en una firma que revienta y en la lectura de
    Tierra. Ni el nombre, ni el texto, ni el sexo, ni quién registra aparecen en el log.
  * Guardia sobre el código: ningún `log.*` de `backend/app` interpola nada al escribir el
    mensaje, y sus argumentos salen de una lista cerrada. Añadir una línea de log con un
    argumento nuevo hace fallar la prueba: es deliberado, obliga a decidir si es contenido
    personal antes de que llegue a `backend.log`.
  * Invariante 5: el veredicto del motor es el mismo con y sin la pieza.

Límite de la prueba, dicho: `TestClient` no pasa por uvicorn. La excepción no prevista es la real,
la que lanza la ruta; lo que se reproduce a mano es la llamada con la que uvicorn la anota
(`uvicorn/protocols/http/h11_impl.py`: `logger.error("Exception in ASGI application\\n",
exc_info=exc)` y la línea de acceso `'%s - "%s %s HTTP/%s" %d'`). Con un uvicorn de verdad se
comprobó a mano en el humo de la unidad. La rotación de `backend.log` (`desktop/main.cjs`) no
tiene prueba automática: `desktop/` no tiene pruebas de JS.
"""

from __future__ import annotations

import ast
import io
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.routes import get_store, new_store, reset_store
from app.core import log_privacy
from app.reports import ocr
from app.volumes import assets, privacy
from tests.test_volumes import fake_segmenter, nifti_bytes, synthetic_ct, upload, wait

__all__ = ["fake_segmenter"]  # fixture de `test_volumes`: TotalSegmentator simulado

BACKEND = Path(__file__).resolve().parents[1]
DESKTOP_ENTRY = BACKEND / "desktop_entry.py"
# La copia en la que corre una campaña de mutantes (`scripts/mutants.py`) lleva `app/` y `tests/`,
# no el punto de entrada de escritorio. Solo ahí se deja de mirar; en el repositorio, si falta,
# la prueba falla.
MUTANT_SANDBOX = (BACKEND / "_emma_mutant_runner.py").is_file() and not DESKTOP_ENTRY.is_file()

# Todo inventado. Nada de esto puede aparecer en el log.
PATIENT = "Garmendia"
BIRTH = "19850307"
REPORT_TEXT = "Hemoglobina 9,1 g/dL de Ane Garmendia Zubiri"
OPERATOR = "Itziar-Olabarria"
SUBJECT = "crew-07"
SECRETS = (PATIENT, BIRTH, "Zubiri", "9,1 g/dL", OPERATOR, SUBJECT)


@pytest.fixture
def log(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    caplog.set_level(logging.DEBUG)
    yield caplog


def written(log: pytest.LogCaptureFixture) -> str:
    """Todo lo que un manejador podría escribir de lo capturado: el texto formateado y, por si un
    formateador propio fuera a buscarlos, los argumentos y la excepción de cada registro."""
    parts = [log.text]
    for record in log.records:
        parts += [record.getMessage(), repr(record.args), repr(record.exc_info)]
        parts.append(str(record.exc_text))
    return "\n".join(parts)


def assert_no_secret(text: str) -> None:
    for secret in SECRETS:
        assert secret.lower() not in text.lower(), f"{secret!r} ha llegado al log"


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (300, 400), 255).save(buffer, format="PNG")
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Caminos con datos sensibles
# --------------------------------------------------------------------------- #


def test_the_app_installs_it() -> None:
    """Importar la aplicación basta: no depende de que quien arranca se acuerde."""
    import app.main  # noqa: F401

    assert log_privacy.installed()


def test_a_report_that_fails_leaves_neither_its_text_nor_who_recorded_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, log: pytest.LogCaptureFixture
) -> None:
    def unreadable(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"página 1 ilegible tras leer: {REPORT_TEXT}")

    monkeypatch.setattr(ocr, "read", unreadable)
    params = {"kind": "analitica", "recorded_by": OPERATOR, "subject": SUBJECT}
    request = client.build_request(
        "POST", "/api/reports", params=params, content=png(),
        headers={"Content-Type": "image/png"},
    )
    with pytest.raises(RuntimeError) as failure:
        client.send(request)
    assert REPORT_TEXT in str(failure.value), "la excepción real sí lleva el texto"
    target = request.url.raw_path.decode()
    assert OPERATOR in target and SUBJECT in target, "y la consulta real, quién y de quién"

    # Lo que uvicorn anota de esa petición (ver el límite declarado en la cabecera del fichero).
    logging.getLogger("uvicorn.error").error(
        "Exception in ASGI application\n", exc_info=failure.value
    )
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "127.0.0.1:50123", "POST", target, "1.1", 500
    )

    text = written(log)
    assert_no_secret(text)
    # Y sigue sirviendo para diagnosticar: qué clase de fallo, dónde y en qué ruta.
    assert "RuntimeError" in text
    assert "api/reports.py:" in text and "en _upload" in text
    assert f'"POST /api/reports{log_privacy.QUERY_OMITTED} HTTP/1.1" 500' in text


def test_a_segmentation_that_blows_up_leaves_type_and_place_only(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch,
    log: pytest.LogCaptureFixture,
) -> None:
    """`log.exception` del trabajo en segundo plano: la traza entera iba al log."""

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"cabecera inesperada: {PATIENT}^Ane {BIRTH}")

    monkeypatch.setattr(assets, "resample", broken)
    image, _ = synthetic_ct()
    study = upload(client, image)
    done = wait(client, client.post(f"/api/volumes/{study}/segment").json()["job"])
    assert done["state"] == "failed"

    text = written(log)
    assert "segmentación" in text and "fallida" in text, "el fallo sí se anota"
    assert "RuntimeError" in text and "api/volumes.py:" in text
    assert_no_secret(text)


def test_a_refused_nifti_and_a_broken_check_do_not_name_the_crew_member(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, log: pytest.LogCaptureFixture
) -> None:
    declared = {
        "given_name": "Ane", "surnames": f"{PATIENT} Zubiri", "birth_date": "1985-03-07",
        "declared_by": "CMO",
    }
    assert client.post("/api/crew/identity", json=declared).status_code == 201
    image, _ = synthetic_ct()
    image.header["descrip"] = f"{PATIENT}^Ane {BIRTH}".encode()
    refused = client.post(
        "/api/volumes", params={"recorded_by": "CMO"}, content=nifti_bytes(image),
        headers={"Content-Type": "application/gzip"},
    )
    assert refused.status_code == 422, refused.text

    real = privacy._tool()

    class Broken:
        _trozos_pii = staticmethod(real._trozos_pii)

        @staticmethod
        def verifica_sin_pii(path: str, values: list[str]) -> None:
            raise RuntimeError(f"no se pudo comparar con {values}: descrip={PATIENT}")

    monkeypatch.setattr(privacy, "_tool", lambda: Broken)
    unavailable = client.post(
        "/api/volumes", params={"recorded_by": "CMO"}, content=nifti_bytes(image),
        headers={"Content-Type": "application/gzip"},
    )
    assert unavailable.status_code == 503, unavailable.text

    text = written(log)
    assert "comprobación de datos personales fallida: RuntimeError" in text
    assert_no_secret(text)


def test_the_declared_sex_never_reaches_the_log(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, log: pytest.LogCaptureFixture
) -> None:
    """El sexo declarado (`crew-sex`, lote «ciclo»): ni por la traza ni por la consulta.

    Una declaración que revienta al firmarse con el valor y quién lo declara en el mensaje del
    error, y la lectura de Tierra con su sujeto y su corte en la cadena de consulta."""
    sex = re.compile(r"\b(fe)?male\b", re.IGNORECASE)
    # El cliente de pruebas (httpx) anota la URL entera de cada petición: es el lado del que
    # llama, no el `backend.log` del servidor, y aquí se calla.
    monkeypatch.setattr(logging.getLogger("httpx"), "disabled", True)
    assert client.post(
        "/api/crew/sex", json={"subject": SUBJECT, "sex": "male", "declared_by": OPERATOR}
    ).status_code == 201

    def unsignable(subject: str, value: str, declared_by: str, identity: Any) -> Any:
        raise RuntimeError(f"no se firmó sex={value} de {subject} por {declared_by}")

    monkeypatch.setattr(get_store(), "record_crew_sex", unsignable)
    request = client.build_request(
        "POST", "/api/crew/sex",
        json={"subject": SUBJECT, "sex": "female", "declared_by": OPERATOR},
    )
    with pytest.raises(RuntimeError) as failure:
        client.send(request)
    assert "female" in str(failure.value), "la excepción real sí lleva el valor"

    read = client.get("/api/crew/sex", params={"subject": SUBJECT, "until": "2100-01-01T00:00:00Z"})
    assert read.json()["sex"] == "male"
    target = read.request.url.raw_path.decode()
    assert SUBJECT in target

    # Lo que uvicorn anota de las dos peticiones (límite declarado en la cabecera del fichero).
    logging.getLogger("uvicorn.error").error(
        "Exception in ASGI application\n", exc_info=failure.value
    )
    access = logging.getLogger("uvicorn.access")
    access.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:50123", "POST", "/api/crew/sex", "1.1", 500)
    access.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:50123", "GET", target, "1.1", 200)

    text = written(log)
    assert not sex.search(text), "el sexo declarado ha llegado al log"
    assert_no_secret(text)
    assert "RuntimeError" in text and "api/mission.py:" in text
    assert f'"GET /api/crew/sex{log_privacy.QUERY_OMITTED} HTTP/1.1" 200' in text


# --------------------------------------------------------------------------- #
# La pieza, suelta
# --------------------------------------------------------------------------- #


def record(name: str = "app.prueba", **kwargs: Any) -> logging.LogRecord:
    """Un registro hecho por la fábrica instalada, como lo haría cualquier `logger`."""
    assert log_privacy.installed()
    fields: dict[str, Any] = {
        "name": name, "level": logging.ERROR, "fn": __file__, "lno": 1, "msg": "fallo",
        "args": (), "exc_info": None,
    }
    return logging.getLogger(name).makeRecord(**{**fields, **kwargs})


def raised(inner: str, outer: str) -> BaseException:
    try:
        try:
            raise KeyError(inner)
        except KeyError as cause:
            raise ValueError(outer) from cause
    except ValueError as exc:
        return exc


def test_a_trace_keeps_types_and_places_of_the_whole_chain() -> None:
    exc = raised(f"paciente {PATIENT}", f"informe: {REPORT_TEXT}")
    made = record(exc_info=(type(exc), exc, exc.__traceback__))
    text = logging.Formatter().format(made)
    assert "ValueError" in text and "causada por:" in text and "KeyError" in text
    assert "tests/test_logs_privacy.py:" in text and "en raised" in text
    assert_no_secret(text)
    assert made.exc_info is None, "la excepción no viaja en el registro: nadie la reformatea"


def test_a_trace_does_not_carry_the_user_folder() -> None:
    """La ruta completa de cada marco lleva el nombre de usuario de Windows."""
    exc = raised("a", "b")
    text = log_privacy.safe_trace(exc)
    assert str(BACKEND) not in text and str(Path.home()) not in text
    assert log_privacy._place(r"C:\Users\Ane Garmendia\emma\app\api\reports.py") == (
        "api/reports.py"
    )


def test_an_implicit_cause_is_followed_and_a_suppressed_one_is_not() -> None:
    try:
        try:
            raise KeyError(PATIENT)
        except KeyError:
            raise ValueError(PATIENT)  # noqa: B904 — la causa implícita es lo que se prueba
    except ValueError as exc:
        implicit = exc
    assert "KeyError" in log_privacy.safe_trace(implicit)
    implicit.__suppress_context__ = True
    assert "KeyError" not in log_privacy.safe_trace(implicit)


def test_a_cycle_of_causes_ends() -> None:
    first, second = ValueError("a"), KeyError("b")
    first.__cause__, second.__cause__ = second, first
    assert log_privacy.safe_trace(first).count("causada por:") == 1


def test_an_os_error_keeps_its_number_not_its_path() -> None:
    exc = FileNotFoundError(2, "No such file", rf"C:\Users\{PATIENT}\informe.pdf")
    text = log_privacy.safe_trace(exc)
    assert "FileNotFoundError (errno 2)" in text
    assert_no_secret(text)


def test_an_exception_passed_as_an_argument_becomes_its_type() -> None:
    exc = ValueError(REPORT_TEXT)
    assert record(msg="no se pudo: %s", args=(exc,)).getMessage() == "no se pudo: ValueError"
    by_name = record(msg="no se pudo: %(why)s", args=({"why": exc},))
    assert by_name.getMessage() == "no se pudo: ValueError"
    assert record(msg="asiento %s en %s ms", args=(12, 3.5)).getMessage() == "asiento 12 en 3.5 ms"


def test_only_the_access_line_loses_its_query() -> None:
    line = '%s - "%s %s HTTP/%s" %d'
    path = f"/api/knowledge/search?q={PATIENT}&k=3"
    access = record(
        log_privacy.ACCESS_LOGGER, msg=line, args=("127.0.0.1:1", "GET", path, "1.1", 200)
    )
    assert access.getMessage() == (
        f'127.0.0.1:1 - "GET /api/knowledge/search{log_privacy.QUERY_OMITTED} HTTP/1.1" 200'
    )
    plain = record(
        log_privacy.ACCESS_LOGGER, msg=line, args=("127.0.0.1:1", "GET", "/api/status", "1.1", 200)
    )
    assert plain.getMessage() == '127.0.0.1:1 - "GET /api/status HTTP/1.1" 200'
    other = record(msg="%s %s %s", args=("a", "b", "¿seguro?"))
    assert other.getMessage() == "a b ¿seguro?", "fuera de la línea de acceso no se toca nada"


def test_installing_twice_does_not_nest() -> None:
    factory = logging.getLogRecordFactory()
    log_privacy.install()
    assert logging.getLogRecordFactory() is factory


# --------------------------------------------------------------------------- #
# Guardia sobre el código
# --------------------------------------------------------------------------- #

LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}
LOGGER_NAMES = {"log", "logger", "_log", "_logger", "LOG", "LOGGER", "logging"}
# Lo único que una línea de log de EMMA puede llevar como argumento, y por qué no es contenido
# personal. `type(x).__name__` se admite siempre. Lo demás, aquí o no entra.
ALLOWED_ARGS = {
    "job": "identificador aleatorio de un trabajo de segmentación",
    "epoch": "fecha de la efeméride pedida a JPL Horizons: un instante de misión, no una persona",
    "reference.epoch": (
        "fecha de la efeméride de Horizons contrastada con SPICE: un instante de misión"
    ),
    "contrast.describe()": (
        "diferencias de tiempo de luz y elongación entre SPICE y Horizons, con sus tolerancias y "
        "los nombres de las dos fuentes (`Contrast.describe`): cifras de geometría, nada personal"
    ),
    "ledger_index": "índice de un asiento del ledger",
    "view.build_ms": "milisegundos que tardó una proyección",
}
ALLOWED_KEYWORDS = {"exc_info", "stack_info", "stacklevel"}


def _is_type_name(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "__name__"
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "type"
    )


def log_calls(tree: ast.AST) -> list[ast.Call]:
    loggers = set(LOGGER_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and "getLogger" in ast.unparse(node.value):
            loggers |= {target.id for target in node.targets if isinstance(target, ast.Name)}
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in LEVELS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in loggers
    ]


def problems(source: str) -> list[str]:
    """Por qué una fuente podría llevar contenido al log. Vacío si no hay motivo."""
    tree = ast.parse(source)
    found = []
    for call in log_calls(tree):
        where = f"línea {call.lineno}"
        args = call.args[1:] if call.func.attr == "log" else call.args  # type: ignore[attr-defined]
        if not args or not (isinstance(args[0], ast.Constant) and isinstance(args[0].value, str)):
            found.append(f"{where}: el mensaje no es un texto fijo (se interpola al escribirlo)")
            continue
        for arg in args[1:]:
            if not _is_type_name(arg) and ast.unparse(arg) not in ALLOWED_ARGS:
                found.append(f"{where}: argumento fuera de la lista cerrada: {ast.unparse(arg)}")
        for keyword in call.keywords:
            if keyword.arg not in ALLOWED_KEYWORDS:
                found.append(f"{where}: palabra clave no admitida: {keyword.arg}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name == "print" or name.startswith("traceback.print_"):
                found.append(f"línea {node.lineno}: {name} escribe sin pasar por el log")
    return found


@pytest.mark.parametrize(
    "line",
    [
        'log.warning(f"informe ilegible: {text}")',
        'log.warning("informe ilegible: %s" % text)',
        'log.warning("informe ilegible: {}".format(text))',
        'log.warning("informe ilegible: " + text)',
        'log.warning("informe ilegible: %s", text)',
        'log.warning("fallo: %s", exc)',
        'log.info("subida de %s", payload.recorded_by)',
        'log.info("subida", extra={"body": body})',
        'logging.error("fallo: %s", exc)',
        'log.log(30, "fallo: %s", exc)',
        'mine = logging.getLogger("x")\nmine.error("fallo: %s", exc)',
        'print(text)',
        'traceback.print_exc()',
    ],
)
def test_the_guard_sees_each_way_of_leaking(line: str) -> None:
    assert problems(line), "la guardia no ve esta forma de escribir un dato en el log"


def test_the_guard_accepts_what_emma_writes_today() -> None:
    fine = (
        'log.warning("limpieza fallida: %s", type(exc).__name__)\n'
        'log.exception("segmentación %s fallida", job)\n'
        'log.log(20, "asiento %s en %s ms", ledger_index, view.build_ms)\n'
    )
    assert problems(fine) == []


def test_no_log_line_of_emma_interpolates_request_or_report_content() -> None:
    sources = sorted((BACKEND / "app").rglob("*.py"))
    if not MUTANT_SANDBOX:
        sources.append(DESKTOP_ENTRY)
    seen = 0
    failures = []
    for path in sources:
        source = path.read_text(encoding="utf-8")
        seen += len(log_calls(ast.parse(source)))
        failures += [f"{path.relative_to(BACKEND)}, {problem}" for problem in problems(source)]
    assert seen >= 5, "la guardia no encuentra las líneas de log que hay: no está mirando nada"
    assert failures == [], "\n".join(failures)


def test_the_desktop_backend_does_not_write_access_lines() -> None:
    """`backend.log` no lleva líneas de acceso porque uvicorn arranca en `warning`: si alguien lo
    baja a `info`, las rutas de cada petición empiezan a guardarse en el perfil del usuario."""
    if MUTANT_SANDBOX:
        pytest.skip("la copia de la campaña de mutantes no lleva desktop_entry.py")
    tree = ast.parse(DESKTOP_ENTRY.read_text(encoding="utf-8"))
    [run] = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "uvicorn.run"
    ]
    levels = {k.arg: ast.unparse(k.value) for k in run.keywords}
    assert levels.get("log_level") == "'warning'"
    assert "access_log" not in levels and "log_config" not in levels


# --------------------------------------------------------------------------- #
# Invariante 5
# --------------------------------------------------------------------------- #


def verdict(client: TestClient) -> dict[str, Any]:
    reset_store(new_store())
    created = client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 40}
    )
    assert created.status_code == 201
    status = client.get("/api/status").json()
    return {
        "overall": status["overall_level"],
        "domains": {name: domain["level"] for name, domain in status["domains"].items()},
        "alerts": [(alert["id"], alert["domain"], alert["level"]) for alert in status["alerts"]],
    }


def test_the_engine_verdict_is_the_same_with_and_without_it(client: TestClient) -> None:
    assert log_privacy.installed()
    with_it = verdict(client)
    mine = logging.getLogRecordFactory()
    logging.setLogRecordFactory(logging.LogRecord)
    try:
        assert not log_privacy.installed()
        without_it = verdict(client)
    finally:
        logging.setLogRecordFactory(mine)
    assert with_it == without_it
    assert with_it["alerts"] and with_it["overall"] != "nominal", "el escenario sí dispara algo"
