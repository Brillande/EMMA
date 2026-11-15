"""La búsqueda automática de correlaciones y la lectura del modelo local, sin red.

Lo que fijan estas pruebas: la búsqueda ordena por |r|, dice cuántos pares miró, excluye los que
covarían por construcción y respeta el dominio; la lectura del modelo es un borrador que se
rechaza si escribe una cifra que no está en los hechos, habla de causa o dice algo que EMMA no
puede decir; sin modelo, se declara no disponible; y nada del motor importa la lectura
(invariante 6: un borrador nunca entra en el análisis ni en una alerta).
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from app.analysis import correlations as method
from app.ingest.fhir import VitalObservation, observation
from app.interpret import correlation_reading as reading
from app.interpret.llm import LlmUnavailable

REF = dt.datetime(2026, 11, 14, 12, 0, tzinfo=dt.UTC)
APP = Path(__file__).resolve().parents[1] / "app"


def _series(key: str, values: list[float]) -> list[VitalObservation]:
    out: list[VitalObservation] = []
    for index, value in enumerate(values):
        at = (REF - dt.timedelta(days=index + 1)).replace(hour=0)
        out.append(observation(key, value, at, "crew-01", "wearable"))
    return out


BASE = [float(i) for i in range(12)]
SERIES = {
    # El ánimo sube con el sueño (r = 1) y baja con la reacción PVT (r = -1).
    "sleep-duration": _series("sleep-duration", [6.0 + 0.1 * v for v in BASE]),
    "mood-valence": _series("mood-valence", [5.0 + 0.2 * v for v in BASE]),
    "pvt-mean-rt": _series("pvt-mean-rt", [300.0 - 2 * v for v in BASE]),
    # Misma prueba que pvt-mean-rt: covaría por construcción, no se mira.
    "pvt-lapses": _series("pvt-lapses", [10.0 - 0.5 * v for v in BASE]),
    # Ningún indicador conductual: con dominio, sus pares entre sí no se miran.
    "heart-rate": _series("heart-rate", [60.0 + (v % 3) for v in BASE]),
    "systolic-bp": _series("systolic-bp", [115.0 + (v % 4) for v in BASE]),
}


def test_la_busqueda_ordena_por_r_y_dice_cuantos_miro() -> None:
    result = method.search(SERIES, REF)
    rs = [abs(pair["r"]) for pair in result["pairs"]]
    assert rs == sorted(rs, reverse=True)
    assert result["tested"] >= len(result["pairs"])
    assert str(result["tested"]) in result["multiple"]
    for pair in result["pairs"]:
        assert pair["state"] == "computed" and pair["theme"] == method.SEARCH_THEME


def test_no_mira_los_pares_que_covarian_por_construccion() -> None:
    result = method.search(SERIES, REF, limit=50)
    keys = {frozenset((pair["x"]["key"], pair["y"]["key"])) for pair in result["pairs"]}
    assert frozenset(("pvt-lapses", "pvt-mean-rt")) not in keys
    assert method.constructed("systolic-bp", "diastolic-bp")
    assert method.constructed("onsd-left", "onsd-right")
    assert not method.constructed("sleep-duration", "pvt-mean-rt")


def test_con_dominio_solo_los_pares_que_lo_tocan() -> None:
    result = method.search(SERIES, REF, domain="behavioral", limit=50)
    assert result["pairs"]
    for pair in result["pairs"]:
        assert "behavioral" in (
            method.CATALOG[pair["x"]["key"]].domain.value,
            method.CATALOG[pair["y"]["key"]].domain.value,
        )
    keys = {frozenset((pair["x"]["key"], pair["y"]["key"])) for pair in result["pairs"]}
    assert frozenset(("heart-rate", "systolic-bp")) not in keys


def test_la_busqueda_pide_referencia_con_zona_y_limite_valido() -> None:
    with pytest.raises(ValueError):
        method.search(SERIES, REF.replace(tzinfo=None))
    with pytest.raises(ValueError):
        method.search(SERIES, REF, limit=0)


class FakeLlm:
    model = "falso"

    def __init__(self, text: str | None = None, fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.seen: str | None = None

    def structured(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.seen = user
        if self.fail:
            raise LlmUnavailable("sin servidor")
        return {"lectura": self.text}


def _result() -> dict[str, Any]:
    return method.search(SERIES, REF, domain="behavioral")


def test_una_lectura_limpia_pasa_y_va_marcada_como_borrador() -> None:
    llm = FakeLlm(
        "El ánimo y la duración del sueño suben juntos. "
        "Con tantos pares, alguno sale alto por azar."
    )
    out = reading.read(llm, _result())  # type: ignore[arg-type]
    assert out["available"] and out["text"] is not None and out["blocked"] == []
    assert "Clase C" in out["label"]
    # El modelo recibe los hechos ya calculados, envueltos.
    assert llm.seen is not None and "HECHOS" in llm.seen and "r = " in llm.seen


def test_una_cifra_inventada_la_bloquea() -> None:
    out = reading.read(FakeLlm("El ánimo y el sueño van juntos con r = 0,37."), _result())  # type: ignore[arg-type]
    assert out["text"] is None
    assert any("0,37" in reason for reason in out["blocked"])


def test_hablar_de_causa_la_bloquea() -> None:
    out = reading.read(FakeLlm("Dormir poco provoca peor ánimo."), _result())  # type: ignore[arg-type]
    assert out["text"] is None
    assert any("causa" in reason for reason in out["blocked"])


def test_sin_modelo_se_declara_no_disponible() -> None:
    out = reading.read(FakeLlm(fail=True), _result())  # type: ignore[arg-type]
    assert out["available"] is False and out["text"] is None
    assert out["note"].startswith("Lectura IA no disponible")


def test_las_cifras_de_los_hechos_si_se_pueden_citar() -> None:
    result = _result()
    facts = reading.facts_text(result)
    assert reading.invented_numbers("n = 12 días", facts) == []
    assert reading.invented_numbers("n = 97 días", facts) == ["97"]


def test_nada_del_motor_importa_la_lectura() -> None:
    """Invariante 6: el borrador no entra en el análisis, el riesgo, las alertas ni en avisos."""
    for folder in ("analysis", "advisor", "core", "ingest"):
        for path in (APP / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module is not None:
                    assert "correlation_reading" not in node.module, path
                    names = {alias.name for alias in node.names}
                    imported = node.module == "app.interpret" and "correlation_reading" in names
                    assert not imported, path
