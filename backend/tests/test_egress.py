"""La única salida a internet: lista blanca, sin red, modo seguro, contenido y traza. Sin red real.

Las peticiones que sí salen se simulan con respx (invariante 3).
"""

from __future__ import annotations

import datetime as dt
import importlib
import inspect
import json
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import polaris
from app.core import egress
from app.core.config import Settings

DONKI = "https://api.nasa.gov/DONKI/FLR"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(cache_dir=tmp_path, offline=False)


@pytest.fixture(autouse=True)
def no_safe_mode() -> Iterator[None]:
    # Se devuelve el proveedor que había (el de la aplicación): dejarlo en None apagaba el modo
    # seguro para todas las pruebas que vinieran después.
    previous = egress._safe_mode
    egress.set_safe_mode_provider(None)
    yield
    egress.set_safe_mode_provider(previous)


def audit(settings: Settings) -> list[dict[str, str]]:
    [path] = (Path(settings.cache_dir) / "egress").glob("audit-*.jsonl")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_host_off_the_allowlist_fails_loudly(settings: Settings) -> None:
    with pytest.raises(egress.EgressNotAllowed):
        egress.authorize(settings, "space-weather", "https://example.com/x")
    with pytest.raises(egress.EgressNotAllowed):
        egress.authorize(settings, "unknown-purpose", DONKI)


def test_offline_blocks_and_the_client_can_degrade(tmp_path: Path) -> None:
    with pytest.raises(egress.EgressBlocked) as caught:
        egress.authorize(Settings(cache_dir=tmp_path, offline=True), "space-weather", DONKI)
    assert isinstance(caught.value, httpx.HTTPError)  # los clientes ya degradan a su caché


def test_safe_mode_blocks_every_exit(settings: Settings) -> None:
    egress.set_safe_mode_provider(lambda: "prueba de modo seguro")
    for purpose, url in (
        ("space-weather", DONKI),
        ("citations", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"),
    ):
        with pytest.raises(egress.EgressBlocked, match="modo seguro"):
            egress.authorize(settings, purpose, url)


def test_health_data_in_a_query_does_not_leave(settings: Settings) -> None:
    with pytest.raises(egress.EgressBlocked, match="sensible"):
        egress.authorize(
            settings, "citations", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            "term=paciente DNI 12345678Z",
        )


def test_a_canary_in_a_query_does_not_leave(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BTP_CANARIOS", "BTPCAN-pruebaEMMA")
    with pytest.raises(egress.EgressBlocked, match="canario"):
        egress.authorize(settings, "space-weather", DONKI, "q=BTPCAN-pruebaEMMA")


@respx.mock
def test_an_allowed_request_goes_out_and_the_trace_keeps_no_query(settings: Settings) -> None:
    route = respx.get(DONKI).mock(return_value=httpx.Response(200, json=[]))
    response = egress.get(
        settings, "space-weather", DONKI, params={"startDate": "2026-01-01", "api_key": "SECRETO"}
    )
    assert response.status_code == 200 and route.called
    [line] = audit(settings)
    assert line["verdict"] == "allow" and line["host"] == "api.nasa.gov"
    assert "SECRETO" not in json.dumps(line) and "2026-01-01" not in json.dumps(line)


def _gzip_bomb(size: int) -> httpx.Response:
    import gzip

    return httpx.Response(
        200, headers={"Content-Encoding": "gzip", "Content-Type": "text/plain"},
        content=gzip.compress(b"\x00" * size),
    )


@respx.mock
def test_a_decompressed_response_stops_at_its_cap(settings: Settings) -> None:
    """Unos kilobytes gzip de un sitio de fuera no se vuelven gigas aquí (auditoría run-2,
    `emma:egress:unbounded-decompressed-response`): se deja de leer al pasar del tope."""
    respx.get(DONKI).mock(return_value=_gzip_bomb(4 * 1024 * 1024))
    with pytest.raises(egress.OversizedResponse):
        egress.get(settings, "space-weather", DONKI, max_bytes=1024 * 1024)


@respx.mock
def test_below_the_cap_the_body_arrives_decompressed_and_usable(settings: Settings) -> None:
    import gzip

    respx.get(DONKI).mock(return_value=httpx.Response(
        200, headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
        content=gzip.compress(b'[{"flrID": "x"}]'),
    ))
    response = egress.get(settings, "space-weather", DONKI)
    assert response.json() == [{"flrID": "x"}]
    assert "content-encoding" not in response.headers
    assert response.headers["content-type"] == "application/json"


@respx.mock
def test_the_planner_fetch_answers_502_to_a_bomb(settings: Settings) -> None:
    """Marplanner pide la cita del día por la puerta: un cuerpo inflado da su 502 de siempre."""
    from app.api.planner import MAX_FETCH_BYTES
    from app.core.config import get_settings
    from app.main import app

    url = "https://zenquotes.io/api/today"
    respx.get(url).mock(return_value=_gzip_bomb(MAX_FETCH_BYTES * 4))
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = TestClient(app).post(
            "/api/planner/fetch", json={"purpose": "planner-quotes", "url": url}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 502
    assert "demasiado grande" in response.json()["detail"]


@respx.mock
def test_a_transient_error_is_retried_politely(settings: Settings) -> None:
    respx.get(DONKI).mock(side_effect=[httpx.Response(503), httpx.Response(200, json=[])])
    assert egress.get(settings, "space-weather", DONKI).status_code == 200


@respx.mock
def test_a_long_retry_after_fails_at_once_instead_of_waiting(settings: Settings) -> None:
    """Un 429 con `Retry-After` de horas no bloquea la consola: se falla ya (el cliente tira de
    caché). Pasó con `DEMO_KEY` agotada: cada `/api/status` esperaba 4 min."""
    route = respx.get(DONKI).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "23983"})
    )
    started = time.monotonic()
    with pytest.raises(httpx.HTTPStatusError):
        egress.get(settings, "space-weather", DONKI)
    assert time.monotonic() - started < 2
    assert route.call_count == 1


@respx.mock
def test_the_citations_client_passes_every_request_through_the_gate(settings: Settings) -> None:
    egress.set_safe_mode_provider(lambda: "modo seguro")
    with egress.client(settings, "citations") as client, pytest.raises(egress.EgressBlocked):
        client.get("https://api.crossref.org/works/10.1000/xyz")


@respx.mock
def test_the_app_update_reaches_only_github_and_follows_its_redirect(settings: Settings) -> None:
    """«Actualizar EMMA»: GitHub y su almacén de ficheros, y nada más; la redirección de la
    descarga también pasa por la puerta (las dos peticiones quedan en la traza)."""
    latest = "https://github.com/Brillande/EMMA/releases/latest/download/emma-update.json"
    stored = "https://release-assets.githubusercontent.com/x/emma-update.json"
    respx.get(latest).mock(return_value=httpx.Response(302, headers={"Location": stored}))
    respx.get(stored).mock(return_value=httpx.Response(200, json={}))
    with egress.client(settings, "app-update") as client:
        assert client.get(latest).status_code == 200
    assert [line["host"] for line in audit(settings)] == [
        "github.com", "release-assets.githubusercontent.com"]
    with pytest.raises(egress.EgressNotAllowed):
        egress.authorize(settings, "app-update", "https://example.com/EMMA.Setup.0.1.5.exe")
    with pytest.raises(egress.EgressNotAllowed):
        egress.authorize(settings, "app-update", "https://api.nasa.gov/emma-update.json")


# --------------------------------------------------------------------------- #
# Señuelos (Polaris `canarios`)
# --------------------------------------------------------------------------- #


def _decoy_token() -> str:
    from app import polaris

    seeded = json.loads(Path(polaris.seed_decoy()).read_text(encoding="utf-8"))
    token: str = seeded["token"]
    return token


def test_a_decoy_is_seeded_where_the_border_reads_and_not_rotated() -> None:
    from app import polaris

    first = _decoy_token()
    assert first.startswith("BTPCAN-")
    border_file = Path(polaris.load("borde").CANARIO_FILE)
    assert first in json.loads(border_file.read_text(encoding="utf-8"))
    assert _decoy_token() == first  # sembrar otra vez no lo rota


def test_the_decoy_token_never_leaves(settings: Settings) -> None:
    token = _decoy_token()
    with pytest.raises(egress.EgressBlocked):
        egress.authorize(settings, "citations", "https://api.crossref.org/works", token)
    [line] = audit(settings)
    assert line["verdict"] == "deny" and token not in json.dumps(line)


def test_no_emma_file_contains_the_decoy() -> None:
    token = _decoy_token()
    app_dir = Path(egress.__file__).resolve().parents[1]
    for path in app_dir.rglob("*.py"):
        assert token not in path.read_text(encoding="utf-8"), path


# --------------------------------------------------------------------------- #
# El primer uso, desde varios hilos a la vez
# --------------------------------------------------------------------------- #

THREADS = 8


def _at_once(call: Callable[[], Any]) -> list[Any]:
    """`call` desde `THREADS` hilos que salen a la vez. Si alguno lanza, la prueba lo ve."""
    barrier = threading.Barrier(THREADS)

    def run(_: int) -> Any:
        barrier.wait(5)
        return call()

    with ThreadPoolExecutor(THREADS) as pool:
        return list(pool.map(run, range(THREADS)))


def _counting(real: Callable[..., Any], calls: list[int]) -> Callable[..., Any]:
    """`real`, apuntando cada entrada y tardando lo justo para que los demás hilos lo alcancen."""

    def slow(*args: Any, **kwargs: Any) -> Any:
        calls.append(threading.get_ident())
        time.sleep(0.05)
        return real(*args, **kwargs)

    return slow


def test_the_decoy_is_seeded_once_when_several_threads_arrive_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin señuelo y con ocho hilos a la vez: siembra uno, y los demás encuentran el suyo.

    Sin cerrojo sembraban todos, cada uno con su token, por el mismo `.tmp` de `canarios`: en
    Windows, `PermissionError` en el `os.replace` del segundo.
    """
    border, decoys = polaris.load("borde"), polaris.load("canarios")
    calls: list[int] = []
    try:
        with monkeypatch.context() as patch:
            patch.setattr(border, "CANARIO_FILE", str(tmp_path / "borde" / "canarios.json"))
            patch.setattr(decoys, "sembrar_estado", _counting(decoys.sembrar_estado, calls))
            places = _at_once(polaris.seed_decoy)
            assert len(calls) == 1
            assert set(places) == {str(tmp_path / "borde" / "senuelo_no_leer.json")}
            token = json.loads(Path(places[0]).read_text(encoding="utf-8"))["token"]
            seeded = json.loads((tmp_path / "borde" / "canarios.json").read_text(encoding="utf-8"))
            assert seeded == [token]
    finally:
        polaris.seed_decoy()  # `canarios` vuelve a apuntar al señuelo de verdad


def test_the_border_is_loaded_and_seeded_once_on_a_concurrent_first_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La consola arranca y pide tres fuentes casi a la par: un solo sembrado, el mismo borde."""
    calls: list[int] = []
    monkeypatch.setattr(egress, "_border_module", None)
    monkeypatch.setattr(polaris, "seed_decoy", _counting(polaris.seed_decoy, calls))
    borders = _at_once(egress._border)
    assert len(calls) == 1
    assert all(border is polaris.load("borde") for border in borders)
    egress._border()
    assert len(calls) == 1  # y ya no se vuelve a sembrar


def test_a_failed_first_seeding_is_tried_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si el señuelo no se pudo sembrar, la puerta no se da por lista: la siguiente lo reintenta."""
    real = polaris.seed_decoy
    attempts: list[int] = []

    def flaky() -> str:
        attempts.append(1)
        if len(attempts) == 1:
            raise PermissionError("disco ocupado")
        return real()

    monkeypatch.setattr(egress, "_border_module", None)
    monkeypatch.setattr(polaris, "seed_decoy", flaky)
    with pytest.raises(PermissionError):
        egress._border()
    assert egress._border() is polaris.load("borde") and len(attempts) == 2


def test_polaris_is_configured_once_when_several_threads_arrive_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El registro de cerebros se escribe una vez, y el gancho y la ruta entran una sola vez."""
    calls: list[int] = []
    tools = str(polaris.tools_dir())
    monkeypatch.setattr(polaris, "_configured", False)
    monkeypatch.setattr(polaris, "registry", _counting(polaris.registry, calls))
    hook = polaris._BRAKE_HOOK
    monkeypatch.setattr(sys, "meta_path", [f for f in sys.meta_path if f is not hook])
    monkeypatch.setattr(sys, "path", [entry for entry in sys.path if entry != tools])
    states = _at_once(polaris.configure)
    assert len(calls) == 1 and set(states) == {polaris.state_dir()}
    assert sys.meta_path.count(polaris._BRAKE_HOOK) == 1 and sys.path.count(tools) == 1
    written = json.loads((polaris.state_dir() / "peripheries.json").read_text(encoding="utf-8"))
    assert [brain["name"] for brain in written["cerebros"]] == [polaris.LOCAL_BRAIN]


def test_the_registry_note_says_what_is_true_about_the_cloud_brains() -> None:
    """Los cerebros de nube están en la copia; lo que no están es registrados (divergencias §1).

    La nota decía «ni se registran ni se copian». Lo segundo era falso, y un documento que exagera
    lo que EMMA deja fuera es justo lo que el proyecto no se permite.
    """
    copied = json.loads((polaris.tools_dir() / "peripheries.json").read_text(encoding="utf-8"))
    assert len(copied["cerebros"]) > 1 and (polaris.tools_dir() / "nvidia.py").is_file()
    registry = polaris.registry()
    assert [brain["name"] for brain in registry["cerebros"]] == [polaris.LOCAL_BRAIN]  # type: ignore[attr-defined]
    note = str(registry["_nota"])
    assert "ni se copian" not in note and "están en la copia" in note
    assert "no se pueden alcanzar" in note


# --------------------------------------------------------------------------- #
# El freno por fichero de Polaris (`HALT_FILES`), confinado al estado de EMMA
# --------------------------------------------------------------------------- #

ON = {"active": True, "reason": "sospecha de fuga por la red", "declared_by": "CMO"}
OFF = {"active": False, "declared_by": "Comandante"}
# La fecha de un freno puesto hace semanas y olvidado; se le da al fichero con `os.utime`.
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
        # Con `halt_file` ya restaurado: sin esto, la puerta seguiría mirando el de la prueba.
        polaris.load("borde")


def _tools_with_the_brake_constant() -> dict[str, Any]:
    """Las herramientas de Polaris ya importadas que definen `HALT_FILES`."""
    tools = polaris.tools_dir().resolve()
    return {
        name: module for name, module in list(sys.modules.items())
        if isinstance(module, ModuleType) and "HALT_FILES" in vars(module)
        and Path(str(module.__file__)).resolve().parent == tools
    }


@pytest.fixture
def factory_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Una carpeta personal de mentira (nunca la real) con el freno de fábrica puesto."""
    home = tmp_path / "casa"
    home.mkdir()
    (home / ".btp.HALT").write_text("ajeno", encoding="utf-8")
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(home))
    monkeypatch.delenv("BTP_HALT_FILES", raising=False)
    return home


def _import_again(monkeypatch: pytest.MonkeyPatch, name: str) -> Any:
    """Importa `name` de cero con un `import` corriente, como lo haría una herramienta dentro de
    una función, sin pasar por `polaris.load`. Al acabar la prueba vuelve el módulo que había."""
    monkeypatch.setitem(sys.modules, name, None)  # deja apuntado qué restaurar, lo hubiera o no
    del sys.modules[name]
    return importlib.import_module(name)


def test_a_halt_file_in_the_user_home_does_not_cut_emma(
    settings: Settings, halt: Path, factory_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`~/.btp.HALT` y `polaris/.HALT` son los frenos de fábrica del borde. Se importa de nuevo,
    tal cual y sin el gancho de EMMA, con la carpeta personal que tiene el fichero: así cortaba
    toda la salida. Al pasar por `polaris.load`, la puerta deja de mirarlos."""
    home = factory_home
    hookless = [finder for finder in sys.meta_path if finder is not polaris._BRAKE_HOOK]
    monkeypatch.setattr(sys, "meta_path", hookless)
    raw = _import_again(monkeypatch, "borde")  # sin pasar por el adaptador de EMMA
    assert [Path(item) for item in raw.HALT_FILES] == [home / ".btp.HALT", polaris.root() / ".HALT"]
    assert raw.egress_check(DONKI, destino="externo:prueba").motivo == "HALT activo"

    assert polaris.load("borde") is raw
    assert [Path(item) for item in raw.HALT_FILES] == [halt]
    monkeypatch.setattr(egress, "_border", lambda: raw)
    egress.authorize(settings, "space-weather", DONKI)
    [line] = audit(settings)
    assert line["verdict"] == "allow"


@pytest.mark.parametrize("late", ["salida", "codigo_rojo", "cost_guard", "cosecha_whatsapp"])
def test_a_tool_imported_late_is_born_with_the_emma_halt_file(
    halt: Path, factory_home: Path, monkeypatch: pytest.MonkeyPatch, late: str
) -> None:
    """Lo que una herramienta importa dentro de una función (`seguimiento` trae `salida`; el
    borde, `codigo_rojo`; `atascos`, `cost_guard`) no pasa por `load`. Llegaba con las rutas de
    fábrica: con un fichero en la carpeta personal se paraba, y lo que escribe el freno lo habría
    escrito allí."""
    module = _import_again(monkeypatch, late)
    assert [Path(item) for item in module.HALT_FILES] == [halt], late
    assert not any(Path(item).exists() for item in module.HALT_FILES)
    # El cargador original sigue respondiendo a lo demás (trazas, `inspect`).
    assert "HALT_FILES" in inspect.getsource(module)
    assert Path(module.__spec__.origin).parent == polaris.tools_dir()


def test_the_late_form_of_the_brake_that_is_a_function_is_confined_too(
    halt: Path, factory_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support = _import_again(monkeypatch, "soporte_cita")
    assert list(support._halt_files()) == [str(halt)] and not support.halt_activo()


def test_the_import_hook_is_installed_once_and_comes_back_if_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polaris.configure()
    polaris.configure()
    assert sys.meta_path.count(polaris._BRAKE_HOOK) == 1
    hookless = [finder for finder in sys.meta_path if finder is not polaris._BRAKE_HOOK]
    monkeypatch.setattr(sys, "meta_path", hookless)
    polaris.load("borde")
    assert sys.meta_path.count(polaris._BRAKE_HOOK) == 1


def test_the_import_hook_leaves_another_copy_of_polaris_alone(
    halt: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`scripts/mutants.py` y `scripts/polaris_tests.py` trabajan con copias de Polaris en
    carpetas temporales: un módulo con nombre de herramienta que no sale de `polaris/tools` no es
    asunto del gancho, y lo que no es de Polaris ni se mira."""
    other = tmp_path / "otra_copia"
    other.mkdir()
    (other / "salida.py").write_text('HALT_FILES = ("suyo",)\n', encoding="utf-8")
    polaris.configure()
    monkeypatch.syspath_prepend(str(other))
    stranger = _import_again(monkeypatch, "salida")
    assert Path(stranger.__file__).parent == other
    assert stranger.HALT_FILES == ("suyo",)
    assert not isinstance(stranger.__spec__.loader, polaris._ConfiningLoader)
    assert not isinstance(json.__spec__.loader, polaris._ConfiningLoader)
    assert polaris._BRAKE_HOOK.find_spec("no_existe_en_ningun_sitio", None) is None
    assert polaris._BRAKE_HOOK.find_spec("app.polaris", None) is None


def test_any_load_confines_every_tool_even_when_the_import_fails(
    halt: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`borde` y `cost_guard` llegan también arrastrados por otras herramientas, y una importación
    que falla a medias ya puede haberlos traído: se confina en cada `load`, salga bien o mal."""
    foreign = tmp_path / "ajeno.HALT"
    foreign.write_text("ajeno", encoding="utf-8")
    border = polaris.load("borde")
    border.HALT_FILES = (str(foreign),)
    assert border.halted()
    polaris.load("deid")  # otra herramienta, no el borde
    assert not border.halted()

    def half_done(name: str) -> None:
        border.HALT_FILES = (str(foreign),)
        raise ImportError("a medias")

    with monkeypatch.context() as patch, pytest.raises(polaris.PolarisUnavailable):
        patch.setattr(polaris.importlib, "import_module", half_done)
        polaris.load("deid")
    assert not border.halted()


def test_every_loaded_polaris_tool_reads_only_the_emma_halt_file(halt: Path) -> None:
    """Las dos formas del freno en la copia: la constante `HALT_FILES` y `_halt_files()`."""
    polaris.load("cost_guard")  # su `_panic` ESCRIBE en `HALT_FILES`: tampoco puede salir de EMMA
    support = polaris.load("soporte_cita")
    braked = _tools_with_the_brake_constant()
    assert {"borde", "cost_guard"} <= set(braked)
    for name, module in braked.items():
        assert list(module.HALT_FILES) == [str(halt)], name
    assert list(support._halt_files()) == [str(halt)] and not support.halt_activo()
    halt.write_text("prueba", encoding="utf-8")
    assert support.halt_activo() and braked["borde"].halted()


def test_a_module_that_is_not_polaris_keeps_its_own_names(
    halt: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stranger = ModuleType("ajeno_con_freno")
    vars(stranger).update(__file__=str(tmp_path / "ajeno_con_freno.py"), HALT_FILES=("suyo",))
    monkeypatch.setitem(sys.modules, stranger.__name__, stranger)
    polaris.load("borde")
    assert vars(stranger)["HALT_FILES"] == ("suyo",)


def test_the_emma_halt_file_cuts_the_exit_and_says_which_file(
    settings: Settings, halt: Path
) -> None:
    assert egress.halt_state() == {"active": False, "file": str(halt), "since": None}
    halt.write_text("prueba", encoding="utf-8")
    assert egress.halt_state()["active"] is True
    with pytest.raises(egress.EgressBlocked) as caught:
        egress.authorize(settings, "space-weather", DONKI)
    assert "HALT" in caught.value.reason and str(halt) in caught.value.reason
    assert "no es el modo seguro" in caught.value.reason
    [line] = audit(settings)
    assert line["verdict"] == "deny" and "HALT" in line["reason"]
    halt.unlink()
    egress.authorize(settings, "space-weather", DONKI)  # borrado el fichero, vuelve a salir


def test_the_brake_shows_next_to_safe_mode_and_lifting_safe_mode_leaves_it(
    client: TestClient, halt: Path
) -> None:
    """No es un asiento del ledger, pero corta la salida: se ve donde se mira por qué no sale
    nada, y levantar el modo seguro no lo quita."""
    unset = {"active": False, "file": str(halt), "since": None, "notice": None}
    assert client.get("/api/safe-mode").json()["halt"] == unset
    halt.write_text("prueba", encoding="utf-8")
    os.utime(halt, (FORGOTTEN.timestamp(), FORGOTTEN.timestamp()))
    put = {"active": True, "file": str(halt), "since": FORGOTTEN_ISO}
    read = client.get("/api/safe-mode").json()["halt"]
    # El aviso (`notice`) lo prueba `tests/test_halt_notice.py`; aquí, que viaja con el freno.
    assert read.pop("notice")["since"] == FORGOTTEN_ISO and read == put
    declared = client.post("/api/safe-mode", json=ON).json()
    assert declared["halt"]["notice"] is not None
    assert {k: v for k, v in declared["halt"].items() if k != "notice"} == put
    # Dos fechas distintas: la del asiento firmado del modo seguro y la del fichero del freno.
    assert declared["since"] != FORGOTTEN_ISO
    state = client.post("/api/safe-mode", json=OFF).json()
    assert state["active"] is False and state["halt"].pop("notice") is not None
    assert state["halt"] == put


def test_the_brake_says_since_when_with_the_date_of_its_file(halt: Path) -> None:
    """Un freno olvidado no se nota (en Polaris paró una rutina semanas): se dice desde cuándo
    está puesto. Es la fecha de modificación del fichero, en UTC, no la de creación ni la hora
    local; y no hay fecha si no está puesto."""
    halt.write_text("prueba", encoding="utf-8")
    os.utime(halt, (FORGOTTEN.timestamp(), FORGOTTEN.timestamp()))
    assert egress.halt_state() == {"active": True, "file": str(halt), "since": FORGOTTEN_ISO}
    assert dt.datetime.fromisoformat(egress.halt_state()["since"]) == FORGOTTEN
    halt.unlink()
    assert egress.halt_state() == {"active": False, "file": str(halt), "since": None}


class _Vanishing:
    """Un fichero de freno que está al mirar y ya no al leer su fecha: lo acaban de borrar."""

    def exists(self) -> bool:
        return True

    def stat(self) -> os.stat_result:
        raise FileNotFoundError(2, "No such file or directory", str(self))

    def __str__(self) -> str:
        return "estado/.HALT"


def test_a_brake_removed_between_the_look_and_its_date_does_not_break_the_answer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Levantar el freno es borrar el fichero, y puede pasar justo entre las dos lecturas."""
    monkeypatch.setattr(polaris, "halt_file", _Vanishing)
    gone = {"active": False, "file": "estado/.HALT", "since": None}
    assert egress.halt_state() == gone
    response = client.get("/api/safe-mode")
    assert response.status_code == 200 and response.json()["halt"] == {**gone, "notice": None}


def test_the_real_halt_file_lives_in_emma_state() -> None:
    assert polaris.halt_file().is_relative_to(polaris.state_dir())
    assert not polaris.halt_file().is_relative_to(polaris.root())


@respx.mock
def test_the_gated_client_reads_with_a_cap_too(settings: Settings) -> None:
    """`egress.client` (citas, actualizador, modelos, órbita): `client.get` también para en el
    tope, ya descomprimido (revisión de seguridad 2026-11-16)."""
    respx.get(DONKI).mock(return_value=_gzip_bomb(4 * 1024 * 1024))
    with (
        egress.client(settings, "space-weather", max_bytes=1024 * 1024) as http,
        pytest.raises(egress.OversizedResponse),
    ):
        http.get(DONKI)


@respx.mock
def test_the_gated_client_still_streams_without_its_cap(settings: Settings) -> None:
    """`client.stream` pasa tal cual: quien lo abre (`fetch_verified`) pone su propio tope."""
    import gzip

    body = b"x" * (2 * 1024 * 1024)
    respx.get(DONKI).mock(return_value=httpx.Response(
        200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(body)
    ))
    with (
        egress.client(settings, "space-weather", max_bytes=1024) as http,
        http.stream("GET", DONKI) as response,
    ):
        assert b"".join(response.iter_bytes()) == body


@respx.mock
def test_below_the_cap_the_gated_client_answers_as_before(settings: Settings) -> None:
    respx.get(DONKI).mock(return_value=httpx.Response(200, json={"ok": True}))
    with egress.client(settings, "space-weather") as http:
        response = http.get(DONKI)
    assert response.json() == {"ok": True}
    response.raise_for_status()


@respx.mock
def test_a_citation_registry_bomb_leaves_the_source_unverified(settings: Settings) -> None:
    """El comprobador de citas va con `CITATION_MAX_BYTES`: una respuesta inflada no se junta, y
    la fuente se queda sin comprobar en vez de tumbar la firma."""
    from app.evidence.citations import UNRESOLVABLE, check_pmid
    from app.evidence.source_check import CITATION_MAX_BYTES

    respx.route(host="eutils.ncbi.nlm.nih.gov").mock(
        return_value=_gzip_bomb(CITATION_MAX_BYTES * 2)
    )
    with egress.client(settings, "citations", max_bytes=CITATION_MAX_BYTES) as http:
        verdict = check_pmid(http, "12345678")
    assert verdict.status == UNRESOLVABLE


def test_the_signoff_checks_its_source_with_the_citation_cap(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La firma de un borrador pide el cliente con `CITATION_MAX_BYTES`, no con el tope general."""
    from app.api import imaging
    from app.evidence.source_check import CITATION_MAX_BYTES

    asked: list[int | None] = []
    real = egress.client

    def spy(cfg: Settings, purpose: str, *, max_bytes: int | None = None) -> httpx.Client:
        asked.append(max_bytes)
        return real(cfg, purpose, max_bytes=max_bytes)

    monkeypatch.setattr(imaging.egress, "client", spy)
    with respx.mock:
        respx.route().mock(return_value=httpx.Response(404))
        imaging._source_check(settings, "PMID 12345678")
    assert asked == [CITATION_MAX_BYTES]
