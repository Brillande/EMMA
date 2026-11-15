"""La correlación de los pares declarados (`analysis/correlations.py`, `GET /api/correlations`).

Lo que fijan estas pruebas, sin red: el r es el de Pearson sobre medias diarias, solo de lo medido
y dentro de la ventana; con pocos días o una serie plana no se da cifra; el intervalo es el de
Fisher; los pares existen en el catálogo; y nada del motor (análisis, riesgo, alertas,
recomendaciones) importa el módulo: correlación no es causa y no decide nada.
"""

from __future__ import annotations

import ast
import datetime as dt
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analysis import correlations as method
from app.api import routes
from app.core.ledger import Identity
from app.ingest.codes import CATALOG
from app.ingest.fhir import EvidenceContext, ObservationType, VitalObservation, observation

REF = dt.datetime(2026, 11, 14, 12, 0, tzinfo=dt.UTC)
ENERGY = [2000.0 + 50 * i for i in range(12)]
PVT = [250.0 + 3 * (i % 4) for i in range(12)]
APP = Path(__file__).resolve().parents[1] / "app"


def _series(
    key: str, values: list[float], per_day: int = 1, **over: object
) -> list[VitalObservation]:
    """Una lectura (o `per_day`) por día hacia atrás desde la víspera de la referencia."""
    out: list[VitalObservation] = []
    for index, value in enumerate(values):
        # Desde medianoche UTC: las `per_day` lecturas caen en el mismo día.
        day = (REF - dt.timedelta(days=index + 1)).replace(hour=0)
        for hour in range(per_day):
            at = day + dt.timedelta(hours=hour)
            out.append(observation(key, value, at, "crew-01", "wearable", **over))  # type: ignore[arg-type]
    return out


def test_los_pares_son_del_catalogo_y_distintos() -> None:
    for pair in method.PAIRS:
        assert pair.x in CATALOG and pair.y in CATALOG
        assert pair.x != pair.y
    assert len({(pair.x, pair.y) for pair in method.PAIRS}) == len(method.PAIRS)


def test_pearson_y_fisher() -> None:
    assert method.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert method.pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)
    assert method.pearson([1, 2, 3], [5, 5, 5]) is None
    low, high = method.fisher_interval(0.5, 30)
    z = math.atanh(0.5)
    assert low == pytest.approx(math.tanh(z - 1.959964 / math.sqrt(27)))
    assert high == pytest.approx(math.tanh(z + 1.959964 / math.sqrt(27)))
    with pytest.raises(ValueError):
        method.fisher_interval(0.5, 3)


def test_media_diaria_y_ventana() -> None:
    xs = [2000.0 + 50 * i for i in range(12)]
    ys = [250.0 + 2 * i for i in range(12)]
    pair = method.PAIRS[1]
    # 24 lecturas al día iguales no cuentan 24 veces: la media del día es la misma.
    result = method.pair_result(pair, _series(pair.x, xs, per_day=24), _series(pair.y, ys), REF)
    assert result["state"] == "computed"
    assert result["n"] == 12
    assert result["r"] == pytest.approx(1.0)
    assert result["ci_low"] <= result["r"] <= result["ci_high"]
    assert "n = 12 días" in result["text"]
    # Fuera de la ventana no entra.
    old = [observation(pair.x, 99.0, REF - dt.timedelta(days=40), "crew-01", "wearable")]
    assert method.pair_result(pair, old, _series(pair.y, ys), REF)["n"] == 0


def test_pocos_dias_o_serie_plana_sin_cifra() -> None:
    pair = method.PAIRS[1]
    xs = _series(pair.x, [1900.0, 2000.0, 2100.0])
    few = method.pair_result(pair, xs, _series(pair.y, [300.0, 280.0, 260.0]), REF)
    assert few["state"] == "insufficient" and few["r"] is None
    assert few["points"] and len(few["points"]) == 3
    rising = _series(pair.y, [250.0 + i for i in range(12)])
    flat = method.pair_result(pair, _series(pair.x, [2000.0] * 12), rising, REF)
    assert flat["state"] == "constant" and flat["r"] is None


def test_solo_lo_medido_y_lo_simulado_se_dice() -> None:
    pair = method.PAIRS[1]
    inferred = _series(
        pair.x, ENERGY, observation_type=ObservationType.INFERRED, model_version="m-1"
    )
    assert method.pair_result(pair, inferred, _series(pair.y, PVT), REF)["n"] == 0
    simulated = _series(pair.x, ENERGY, evidence_context=EvidenceContext.SIMULATED)
    result = method.pair_result(pair, simulated, _series(pair.y, PVT), REF)
    assert result["simulated"] is True


def test_la_respuesta_declara_metodo_y_alcance() -> None:
    body = method.correlations({}, REF)
    assert body["window_days"] == method.WINDOW_DAYS and body["min_days"] == method.MIN_DAYS
    assert "no causa" in body["scope"] and "alertas" in body["scope"]
    assert len(body["pairs"]) == len(method.PAIRS)
    assert all(item["state"] == "insufficient" for item in body["pairs"])
    with pytest.raises(ValueError):
        method.correlations({}, REF.replace(tzinfo=None))


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_nada_del_motor_lo_importa() -> None:
    engine = [
        *(APP / "analysis").glob("*.py"), *(APP / "advisor").glob("*.py"), APP / "api" / "routes.py"
    ]
    for path in engine:
        if path.name == "correlations.py":
            continue
        assert not [name for name in _imports(path) if "correlations" in name], path


def test_la_ruta(client: TestClient) -> None:
    store = routes.get_store()
    source = Identity.generate("wearable")
    pair = method.PAIRS[3]
    xs = _series(pair.x, [6.0 + 0.1 * i for i in range(12)])
    ys = _series(pair.y, [300.0 - i for i in range(12)])
    for item in [*xs, *ys]:
        store.record(item, source)
    body = client.get("/api/correlations", params={"until": REF.isoformat()}).json()
    found = next(
        item for item in body["pairs"] if (item["x"]["key"], item["y"]["key"]) == (pair.x, pair.y)
    )
    assert found["state"] == "computed"
    assert found["r"] == pytest.approx(-1.0)
    assert found["x"]["display_es"] == CATALOG[pair.x].display_es
    naive = client.get("/api/correlations", params={"until": "2026-11-14T12:00:00"})
    assert naive.status_code == 422
