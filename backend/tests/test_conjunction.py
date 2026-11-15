"""Conjunción solar (unidad D6): la elongación de Horizons se lee, se guarda y solo se dice.

Cuatro cosas que no se pueden romper:

1. **La caché antigua sigue cargando.** Las efemérides de una fecha no caducan y todo el sistema
   lee `ephemeris.py`: una entrada guardada antes de leer la elongación (copia literal de una
   del repositorio) se carga con el mismo retardo y la elongación en `None`.
2. **La elongación viene de la consulta de siempre.** La consulta pide la cantidad 23 y el
   analizador de astroquery la entrega como `elong`/`elongFlag`; sin red (se intercepta la
   petición de astroquery, que va por `requests` y no por httpx: `respx` no la vería).
3. **El umbral es el que escribe su frase**, y solo vale para Marte.
4. **No decide nada.** El factor de aislamiento, los niveles, las alertas y las
   recomendaciones son idénticos con la elongación en 0,5°, en 90° o sin ella.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import json
import math
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from astropy.table import MaskedColumn, Table
from astroquery.jplhorizons import HorizonsClass
from astroquery.utils.mocks import MockResponse
from fastapi.testclient import TestClient

from app.analysis.risk import isolation_factor
from app.api import routes
from app.api.routes import new_store, reset_store
from app.core.cache import FileCache
from app.core.config import Settings, get_settings
from app.environment import conjunction
from app.environment.ephemeris import (
    SOLAR_ELONGATION_QUANTITY,
    CommsWindow,
    EphemerisClient,
    solar_elongation,
)
from app.evidence import registry
from app.main import app

DATA = Path(__file__).parent / "data" / "horizons"
BACKEND = Path(__file__).resolve().parents[1]
OLD_ENTRY = json.loads((DATA / "cache_pre_elongation.json").read_text(encoding="utf-8"))


def _mars(elongation: float | None, flag: str | None = "/T") -> CommsWindow:
    return CommsWindow(
        dt.date(2028, 3, 20), 2.38685031840805, 19.85082879, "499",
        solar_elongation_deg=elongation, solar_elongation_flag=flag if elongation else None,
    )


# --- 1. La caché antigua --------------------------------------------------------------------


def test_an_entry_saved_before_the_elongation_loads_with_the_same_delay() -> None:
    window = CommsWindow.from_dict(OLD_ENTRY["data"])
    assert window.solar_elongation_deg is None and window.solar_elongation_flag is None
    assert window.one_way_minutes == OLD_ENTRY["data"]["one_way_minutes"]
    assert window.round_trip_minutes == OLD_ENTRY["data"]["round_trip_minutes"]
    assert window.describe() == OLD_ENTRY["data"]["description"]
    # Lo que servía antes lo sigue sirviendo igual: solo se añaden las dos claves de la elongación
    # y, desde el 2026-11-11, el origen (`source`, Horizons o SPICE local), que de la caché es
    # siempre Horizons; y el contraste con SPICE (`contrast`), que de la caché sale nulo: es de
    # cada consulta, no se guarda.
    served = window.to_dict()
    assert {k: served[k] for k in OLD_ENTRY["data"]} == OLD_ENTRY["data"]
    assert set(served) - set(OLD_ENTRY["data"]) == {
        "solar_elongation_deg", "solar_elongation_flag", "source", "contrast",
    }
    assert served["source"] == "JPL Horizons" and served["contrast"] is None


def test_the_client_serves_the_old_cache_offline_and_says_the_angle_is_missing(
    tmp_path: Path,
) -> None:
    settings = Settings(cache_dir=tmp_path, offline=True)
    cache = FileCache(tmp_path / "ephemeris")
    cache.put(OLD_ENTRY["key"], OLD_ENTRY["data"], source=OLD_ENTRY["source"])
    client = EphemerisClient(settings=settings, cache=cache)
    payload = client.comms_window(dt.date(2026, 10, 21), "499")
    assert payload.from_cache
    assert payload.data.distance_au == OLD_ENTRY["data"]["distance_au"]
    said = conjunction.describe(payload.data, "499")
    assert said["state"] == conjunction.NOT_RECORDED
    assert said["elongation_deg"] is None and said["threshold_deg"] is None
    assert "no trae la elongación" in said["text"]


@pytest.mark.parametrize(
    ("degrees", "flag", "expected"),
    [
        ("0.5", "/T", (None, None)),  # un texto no es un ángulo
        (True, "/T", (None, None)),
        (999.0, "/T", (None, None)),
        (math.inf, "/L", (None, None)),
        (10.0, "/x", (10.0, None)),
        (10, "/L", (10.0, "/L")),
    ],
)
def test_a_touched_cache_entry_passes_the_same_filter_as_horizons(
    degrees: Any, flag: Any, expected: tuple[float | None, str | None]
) -> None:
    raw = {**OLD_ENTRY["data"], "solar_elongation_deg": degrees, "solar_elongation_flag": flag}
    window = CommsWindow.from_dict(raw)
    assert (window.solar_elongation_deg, window.solar_elongation_flag) == expected
    assert window.one_way_minutes == OLD_ENTRY["data"]["one_way_minutes"]
    # Y lo que se dice no falla con ella.
    assert conjunction.describe(window, "499")["state"] in conjunction.STATES


def test_a_window_with_elongation_survives_the_cache() -> None:
    window = _mars(0.8531)
    assert CommsWindow.from_dict(window.to_dict()) == window


# --- 2. La consulta y el analizador ---------------------------------------------------------


def test_the_query_asks_horizons_for_quantity_23(tmp_path: Path) -> None:
    client = EphemerisClient(settings=Settings(cache_dir=tmp_path, offline=True))
    payload = client._query(dt.date(2028, 3, 20), "499").ephemerides_async(
        get_query_payload=True
    )
    asked = payload["QUANTITIES"].strip("'").split(",")
    assert SOLAR_ELONGATION_QUANTITY in asked


@pytest.fixture
def horizons_answers(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """La respuesta de Horizons (fixture con cifras leídas el 2026-10-22), sin salir a la red."""
    asked: list[str] = []

    def request(self: object, method: str, url: str, **kwargs: Any) -> MockResponse:
        asked.append(url)
        return MockResponse(content=(DATA / "mars_2028-03-20.txt").read_bytes(), url=url)

    monkeypatch.setattr(HorizonsClass, "_request", request)
    return asked


def test_astroquery_parses_the_elongation_and_the_client_keeps_it(
    tmp_path: Path, horizons_answers: list[str]
) -> None:
    client = EphemerisClient(settings=Settings(cache_dir=tmp_path, offline=True))
    window = client._fetch(dt.date(2028, 3, 20), "499")
    assert horizons_answers, "la prueba no pasó por la petición de astroquery"
    assert window.solar_elongation_deg == pytest.approx(0.8531)
    assert window.solar_elongation_flag == "/T"
    # El retardo es el de siempre, con su verificación cruzada contra la distancia.
    assert window.one_way_minutes == pytest.approx(19.85082879)
    assert conjunction.describe(window, "499")["state"] == conjunction.WITHIN


def _table(**columns: Any) -> Table:
    return Table({name: [value] for name, value in columns.items()})


@pytest.mark.parametrize(
    "table",
    [
        _table(delta=1.0),  # sin la columna
        _table(elong=181.0, elongFlag="/T"),  # imposible
        _table(elong=-0.1, elongFlag="/T"),
        _table(elong=math.nan, elongFlag="/T"),
        _table(elong="n.a.", elongFlag="/T"),
        Table({"elong": MaskedColumn([1.0], mask=[True]), "elongFlag": ["/T"]}),
    ],
)
def test_a_missing_or_impossible_angle_is_none_not_a_number(table: Table) -> None:
    assert solar_elongation(table) == (None, None)


def test_a_masked_angle_is_read_as_missing_not_converted() -> None:
    """Un hueco de Horizons es «sin dato» desde el principio, no un NaN que se descarta después
    (numpy avisa al convertir un enmascarado: aquí ese aviso sería un error)."""
    table = Table({"elong": MaskedColumn([1.0], mask=[True]), "elongFlag": ["/T"]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert solar_elongation(table) == (None, None)


def test_an_unknown_flag_is_dropped_but_the_angle_kept() -> None:
    assert solar_elongation(_table(elong=10.0, elongFlag="/x")) == (10.0, None)
    assert solar_elongation(_table(elong=10.0)) == (10.0, None)
    assert solar_elongation(_table(elong=180.0, elongFlag="/L")) == (180.0, "/L")


def test_a_bad_angle_does_not_break_the_delay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El retardo decide y la elongación solo se dice: una elongación rota no tumba el retardo."""
    # Con su fecha: la consulta diaria toma la fila de su día (2028-03-20, día juliano 2461850,5).
    table = _table(
        datetime_jd=2461850.5, delta=2.38685031840805, lighttime=19.85082879, elong=999.0,
        elongFlag="/T",
    )

    class Query:
        def ephemerides(self) -> Table:
            return table

    monkeypatch.setattr(EphemerisClient, "_query", lambda self, epoch, target: Query())
    window = EphemerisClient(settings=Settings(cache_dir=tmp_path))._fetch(
        dt.date(2028, 3, 20), "499"
    )
    assert window.one_way_minutes == pytest.approx(19.85082879)
    assert window.solar_elongation_deg is None


# --- 3. El umbral y lo que se dice ----------------------------------------------------------


@pytest.mark.parametrize(
    ("elongation", "state"),
    [(0.8121, conjunction.WITHIN), (2.0, conjunction.WITHIN), (2.05, conjunction.CLEAR),
     (75.1768, conjunction.CLEAR)],
)
def test_mars_is_said_within_or_clear_of_the_two_degrees(elongation: float, state: str) -> None:
    said = conjunction.describe(_mars(elongation), "499")
    assert said["state"] == state
    assert said["threshold_deg"] == 2.0
    assert said["elongation_deg"] == elongation
    assert ("dentro" in said["text"]) is (state == conjunction.WITHIN)
    assert "2°" in said["text"]


def test_the_angle_is_written_in_spanish() -> None:
    assert "0,8°" in conjunction.describe(_mars(0.8121), "499")["text"]
    assert "75,2°" in conjunction.describe(_mars(75.1768), "499")["text"]


def test_without_ephemeris_it_says_so() -> None:
    said = conjunction.describe(None, "499")
    assert said["state"] == conjunction.NO_EPHEMERIS
    assert said["text"].startswith("Sin efemérides")
    assert said["elongation_deg"] is None and said["epoch"] is None


def test_the_threshold_is_only_for_mars() -> None:
    moon = CommsWindow(dt.date(2026, 10, 22), 0.0027, 0.02, "301", solar_elongation_deg=1.0)
    said = conjunction.describe(moon, "301")
    assert said["state"] == conjunction.NO_THRESHOLD
    assert said["threshold_deg"] is None
    assert "solo tiene leído un umbral de conjunción para Marte" in said["text"]


def test_the_threshold_is_the_one_its_sentence_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "within two degrees of Mars" in conjunction._THRESHOLD["quote"]
    monkeypatch.setattr(conjunction, "THRESHOLD_DEG", 3.0)
    with pytest.raises(ValueError, match="umbral"):
        conjunction._validate()
    # La cifra sale de la frase: con otra frase, el mismo número deja de valer.
    monkeypatch.setattr(conjunction, "THRESHOLD_DEG", 2.0)
    conjunction._validate()
    other = {**conjunction._THRESHOLD, "quote": "the sun will be within three degrees of Mars"}
    monkeypatch.setattr(conjunction, "_THRESHOLD", other)
    with pytest.raises(ValueError, match="umbral"):
        conjunction._validate()


def test_every_citation_is_a_registry_card_with_its_sentence() -> None:
    said = conjunction.describe(_mars(1.0), "499")
    assert {cite["ref"] for cite in said["citations"]} == conjunction.cited_refs()
    for cite in said["citations"]:
        ref = registry.get(cite["ref"])
        assert cite["title"] == ref.title and cite["url"] == ref.url
        # La frase citada está copiada en la nota de su ficha: no es de oídas.
        assert cite["quote"].rstrip(".") in ref.notes
        assert cite["read_on"] in ref.notes


def test_the_note_says_it_decides_nothing() -> None:
    note = conjunction.describe(_mars(1.0), "499")["note"]
    assert note.startswith("Solo se dice")
    assert "factor de aislamiento" in note


# --- 4. No decide nada -----------------------------------------------------------------------


def test_the_isolation_factor_does_not_read_the_elongation() -> None:
    reference = isolation_factor(_mars(None))
    assert reference > 1.0
    for elongation in (0.5, 2.0, 90.0, 180.0):
        assert isolation_factor(_mars(elongation)) == reference


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_nothing_that_decides_reads_the_elongation_or_the_conjunction() -> None:
    deciders = [*sorted((BACKEND / "app" / "analysis").glob("*.py")),
                *sorted((BACKEND / "app" / "advisor").glob("*.py"))]
    assert any(path.name == "risk.py" for path in deciders)
    for module in deciders:
        assert "app.environment.conjunction" not in _imports(module), module.name
        text = module.read_text(encoding="utf-8")
        assert "solar_elongation" not in text, module.name
        assert "conjunction" not in text, module.name


@pytest.fixture
def api(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    client = TestClient(app)
    client.post("/api/simulate", params={"scenario": "progressive-insomnia", "days": 40})
    yield client
    app.dependency_overrides.clear()
    reset_store(None)


def _status(client: TestClient, monkeypatch: pytest.MonkeyPatch, window: CommsWindow) -> Any:
    monkeypatch.setattr(routes, "_fetch_comms", lambda settings, epoch, target: (window, None))
    response = client.get("/api/status")
    assert response.status_code == 200, response.text
    return response.json()


def _without_the_conjunction(status: dict[str, Any]) -> dict[str, Any]:
    status = copy.deepcopy(status)
    said = status["mission"]["profile"].pop("solar_conjunction")
    for key in ("solar_elongation_deg", "solar_elongation_flag"):
        status["comms"].pop(key)
    return {"status": status, "said": said}


def test_levels_alerts_recommendations_and_isolation_do_not_change_with_the_elongation(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = _without_the_conjunction(_status(api, monkeypatch, _mars(None)))
    assert reference["status"]["isolation_factor"] > 1.0
    assert reference["status"]["alerts"], "el escenario tiene que disparar al menos una alerta"
    assert reference["status"]["recommendations"]
    seen = {reference["said"]["state"]}
    for elongation in (0.5, 90.0):
        other = _without_the_conjunction(_status(api, monkeypatch, _mars(elongation)))
        seen.add(other["said"]["state"])
        # Todo lo demás —niveles, puntuaciones, alertas, recomendaciones, factor de
        # aislamiento, versión de reglas— es idéntico: la conjunción solo añade su bloque.
        assert other["status"] == reference["status"]
    # Y el bloque sí cambia: la prueba no pasa porque la elongación se ignore al servirla.
    assert seen == {conjunction.NOT_RECORDED, conjunction.WITHIN, conjunction.CLEAR}


def test_the_status_without_ephemeris_says_so_in_the_profile(api: TestClient) -> None:
    profile = api.get("/api/status").json()["mission"]["profile"]
    assert profile["solar_conjunction"]["state"] == conjunction.NO_EPHEMERIS


def test_comms_carries_the_conjunction_of_the_same_day(
    api: TestClient, tmp_path: Path, horizons_answers: list[str]
) -> None:
    # La efeméride entra en la caché como entraría tras consultar (la petición de astroquery,
    # interceptada), y la API la sirve sin red, que es el modo nominal.
    settings = Settings(cache_dir=tmp_path, offline=True)
    window = EphemerisClient(settings=settings)._fetch(dt.date(2028, 3, 20), "499")
    FileCache(tmp_path / "ephemeris").put(
        f"horizons:499:{settings.observer_body}:2028-03-20", window.to_dict(), source="prueba"
    )
    found = api.get("/api/comms", params={"epoch": "2028-03-20"}).json()
    assert horizons_answers
    assert found["solar_elongation_deg"] == pytest.approx(0.8531)
    assert found["solar_conjunction"]["state"] == conjunction.WITHIN
    assert found["solar_conjunction"]["epoch"] == "2028-03-20"
