"""El detalle de alerta, completo y compuesto por el backend (especificación §3, §6 y §10).

Qué fijan estas pruebas:
- que «qué comprobar» y «qué evidencia lo respalda» llevan lo mismo que antes juntaba la vista
  (las recomendaciones del dominio y sus fichas, una vez cada una), y que sin ninguna se dice;
- que la persistencia que se enseña es la regla del motor (`analysis/risk.py`), llamada y no
  copiada: si la regla cambia, lo que se enseña cambia con ella;
- que la confianza son recuentos, con el umbral de `ingest/fhir.py`, y no hay cifra única;
- que el texto pasa el linter de lenguaje (invariante 7);
- y la que importa (invariante 5): el veredicto de dos escenarios es idéntico con y sin esto.
"""

import ast
import datetime as dt
import inspect
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.advisor.recommendations import Recommendation, Urgency, _evidence
from app.analysis import alert_support, baseline, explain, risk, trend
from app.analysis.alert_support import (
    NO_CHECKS,
    NO_EVIDENCE,
    NO_READINGS,
    NO_SINGLE_FIGURE,
    confidence,
    persistence,
    support,
)
from app.analysis.baseline import Baseline, Deviation, Severity, SeverityBasis
from app.analysis.data_quality import TREND_NOTE
from app.analysis.trend import Direction, Trend
from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence.links import HRP_RISKS
from app.ingest import fhir
from app.ingest.codes import Domain
from app.main import app
from app.text_guard import check

T0 = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.UTC)
KEY = "pvt-mean-rt"  # dominio conductual


def _h(hours: float) -> dt.datetime:
    return T0 + dt.timedelta(hours=hours)


def _deviations(
    key: str = KEY, concerning: int = 0, total: int = 10,
    severity: Severity = Severity.MODERATE, population: bool = False,
) -> list[Deviation]:
    """`total` lecturas horarias de un indicador; las `concerning` primeras, preocupantes."""
    reference = Baseline(
        key=key, center=50.0, spread=5.0, samples=200,
        sorted_values=tuple(float(value) for value in range(40, 61)),
    )
    return [
        Deviation(
            subject="crew-01", key=key, value=70.0 + index if index < concerning else 50.0,
            effective=_h(index), z_score=3.0 if index < concerning else 0.1,
            severity=severity if index < concerning else Severity.NONE, direction="high",
            baseline=reference, used_population_range=population,
            basis=SeverityBasis.PERSONAL_PERCENTILE if index < concerning else None,
        )
        for index in range(total)
    ]


def _falling(key: str) -> Trend:
    return Trend(
        key=key, slope_per_day=-0.5, t_statistic=12.0, points=60, span_days=20.0,
        direction=Direction.FALLING, significant=True, mean_value=6.0, standard_error=0.0,
    )


def _library(domain: Domain) -> list[Recommendation]:
    """Una recomendación por contramedida de la biblioteca del dominio, como las da el consejero."""
    return [
        Recommendation(
            domain=domain, action=item.action, rationale="motivo", urgency=Urgency.ROUTINE,
            evidence=_evidence(item), countermeasure=item,
        )
        for item in countermeasures.for_domain(domain)
    ]


def _everything() -> list[Recommendation]:
    return [item for domain in Domain for item in _library(domain)]


# --------------------------------------------------------------------------- #
# Qué comprobar y qué evidencia lo respalda
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("domain", list(Domain))
def test_checks_and_evidence_are_what_the_view_used_to_join(domain: Domain) -> None:
    mine = _library(domain)
    result = support(domain, _everything())
    checks, fiches = result["checks"]["items"], result["evidence"]["items"]

    # Las comprobaciones: las recomendaciones del dominio, con su id y su título, y nada más.
    assert [item["id"] for item in checks] == [rec.countermeasure.id for rec in mine]  # type: ignore[union-attr]
    assert [item["title"] for item in checks] == [rec.action for rec in mine]
    for item, rec in zip(checks, mine, strict=True):
        assert rec.countermeasure is not None
        assert item["demo"] is (rec.countermeasure.basis == "demo")
        assert item["basis_display"]
        assert item["evidence_ids"] == list(dict.fromkeys(ref.id for ref in rec.evidence))

    # Las fichas: cada una una vez, en el orden en que se citan, con su grado.
    cited = [item.id for rec in mine for item in rec.evidence]
    assert [item["id"] for item in fiches] == list(dict.fromkeys(cited))
    for item in fiches:
        assert item["grade"]["label"]
        assert item["role_display"]
        citing = [rec for rec in mine if item["id"] in {ref.id for ref in rec.evidence}]
        assert item["cited_by"] == [rec.countermeasure.id for rec in citing]  # type: ignore[union-attr]
        # `demo`: ninguna de las comprobaciones que la citan tiene protocolo propio.
        assert item["demo"] is all(rec.countermeasure.basis == "demo" for rec in citing)  # type: ignore[union-attr]
        assert (item["demo_display"] is not None) is item["demo"]
        is_protocol = any(
            rec.countermeasure.protocol_ref is not None  # type: ignore[union-attr]
            and rec.countermeasure.protocol_ref.id == item["id"]  # type: ignore[union-attr]
            for rec in citing
        )
        assert item["role"] == ("protocol" if is_protocol else "domain_risk")


def test_the_library_exercises_both_bases() -> None:
    """Si la biblioteca dejara de tener `demo` o protocolos, la prueba de arriba no diría nada."""
    fiches = [
        item for domain in Domain for item in support(domain, _everything())["evidence"]["items"]
    ]
    checks = [
        item for domain in Domain for item in support(domain, _everything())["checks"]["items"]
    ]
    assert {item["demo"] for item in checks} == {True, False}
    assert {item["demo"] for item in fiches} == {True, False}
    assert {item["role"] for item in fiches} == {"protocol", "domain_risk"}


def test_the_why_is_the_first_cited_relevance_and_is_quoted_verbatim() -> None:
    mine = _library(Domain.BEHAVIORAL)
    expected = next(
        cited for rec in mine for cited in rec.evidence if cited.relevance is not None
    )
    why = support(Domain.BEHAVIORAL, mine)["relevance_evidence"]
    assert why == {"id": expected.id, "title": expected.title, "text": expected.relevance}
    # Con dos fichas que lo redactan, la primera citada; no la última ni otra.
    first, second = HRP_RISKS[Domain.BONE], HRP_RISKS[Domain.CARDIOVASCULAR]
    assert first.relevance and second.relevance and first.id != second.id
    both = Recommendation(
        domain=Domain.BEHAVIORAL, action="acción", rationale="motivo", urgency=Urgency.ROUTINE,
        evidence=(first, second),
    )
    assert support(Domain.BEHAVIORAL, [both])["relevance_evidence"] == {
        "id": first.id, "title": first.title, "text": first.relevance,
    }
    # Sin contramedida de la biblioteca, la comprobación va sin id y sin base inventada.
    [loose] = support(Domain.BEHAVIORAL, [both])["checks"]["items"]
    assert (loose["id"], loose["basis"], loose["basis_display"], loose["demo"]) == (
        None, None, None, False
    )


def test_without_checks_it_says_so_instead_of_leaving_the_gap() -> None:
    # Recomendaciones de otro dominio: no son de esta alerta.
    result = support(Domain.BONE, _library(Domain.BEHAVIORAL))
    assert result["checks"] == {
        "items": [], "statement": NO_CHECKS, "order_note": None, "unclassified_note": None,
    }
    assert result["evidence"] == {"items": [], "statement": NO_EVIDENCE}
    assert result["relevance_evidence"] is None
    assert NO_CHECKS == "sin comprobación estructurada para este dominio"
    # Y quien llama a `detail` sin recomendaciones recibe lo mismo, no una clave que falta.
    bare = explain.detail(Domain.BONE, [], [])
    assert bare["checks"]["statement"] == NO_CHECKS
    assert bare["evidence"]["statement"] == NO_EVIDENCE


def test_a_repeated_check_is_listed_once() -> None:
    mine = _library(Domain.BEHAVIORAL)
    result = support(Domain.BEHAVIORAL, [*mine, *mine])
    assert len(result["checks"]["items"]) == len(mine)
    assert all(
        len(item["cited_by"]) == len(set(item["cited_by"]))
        for item in result["evidence"]["items"]
    )


# --------------------------------------------------------------------------- #
# Persistencia: la regla del motor, no una segunda
# --------------------------------------------------------------------------- #

def _only(result: dict[str, Any]) -> dict[str, Any]:
    [item] = result["indicators"]
    return item  # type: ignore[no-any-return]


def test_persistence_counts_readings_out_of_expected_over_the_window() -> None:
    item = _only(persistence(Domain.BEHAVIORAL, _deviations(concerning=4), []))
    assert (item["key"], item["readings"], item["out_of_expected"]) == (KEY, 10, 4)
    assert item["fraction"] == 0.4
    assert (item["sustained"], item["rule"], item["trend"]) == (True, "persistence", False)
    assert "4 de 10 lecturas de la ventana actual fuera de lo esperado (40 %)" in item["statement"]
    assert "Cuenta como hallazgo" in item["statement"]


def test_isolated_readings_are_shown_and_said_not_to_count() -> None:
    result = persistence(Domain.BEHAVIORAL, _deviations(concerning=2), [])
    item = _only(result)
    assert (item["out_of_expected"], item["sustained"], item["rule"]) == (2, False, None)
    assert "no cuenta como hallazgo" in item["statement"]
    assert result["sustained"] == 0


def test_each_indicator_agrees_with_the_engine_at_every_count() -> None:
    """Lo que se enseña como sostenido es exactamente lo que el motor toma como hallazgo."""
    for severity in (Severity.MILD, Severity.MODERATE, Severity.SEVERE):
        for total in (5, 10, 40):
            for concerning in range(1, total + 1):
                series = _deviations(concerning=concerning, total=total, severity=severity)
                item = _only(persistence(Domain.BEHAVIORAL, series, []))
                engine = risk.representative_deviation(series) is not None
                assert item["sustained"] is engine, (severity, total, concerning)
                assert (item["rule"] is not None) is engine


def test_a_burst_of_severe_readings_counts_below_the_fraction() -> None:
    total = 40
    needed = risk.min_severe_readings(total)
    assert needed / total < risk._PERSISTENCE_FRACTION, "la prueba necesita una ráfaga corta"
    series = _deviations(concerning=needed, total=total, severity=Severity.SEVERE)
    item = _only(persistence(Domain.BEHAVIORAL, series, []))
    assert (item["sustained"], item["rule"]) == (True, "burst")
    assert (item["severe"], item["required_severe"]) == (needed, needed)
    assert "por ráfaga" in item["statement"]
    # Una menos ya no es ráfaga.
    fewer = _deviations(concerning=needed - 1, total=total, severity=Severity.SEVERE)
    assert _only(persistence(Domain.BEHAVIORAL, fewer, []))["sustained"] is False


def test_if_the_engine_rule_changes_what_is_shown_changes_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = _deviations(concerning=4)
    assert _only(persistence(Domain.BEHAVIORAL, series, []))["required_fraction"] == (
        risk._PERSISTENCE_FRACTION
    )
    # La fracción del motor sube: 4 de 10 deja de contar, y la frase da la fracción nueva.
    monkeypatch.setattr(risk, "_PERSISTENCE_FRACTION", 0.5)
    moved = _only(persistence(Domain.BEHAVIORAL, series, []))
    assert (moved["sustained"], moved["required_fraction"]) == (False, 0.5)
    assert "(50 %)" in moved["statement"]
    # Y si el motor deja de dar hallazgo, aquí tampoco: se le pregunta a él.
    monkeypatch.setattr(risk, "_PERSISTENCE_FRACTION", 0.3)
    monkeypatch.setattr(risk, "representative_deviation", lambda series: None)
    gone = _only(persistence(Domain.BEHAVIORAL, _deviations(concerning=9), []))
    assert gone["sustained"] is False
    # La ráfaga también sale del motor.
    monkeypatch.setattr(risk, "min_severe_readings", lambda readings: 7)
    assert _only(persistence(Domain.BEHAVIORAL, series, []))["required_severe"] == 7


def test_a_trend_only_indicator_is_listed_as_such() -> None:
    drift = _falling("mood-valence")
    assert drift.is_concerning
    result = persistence(
        Domain.BEHAVIORAL, _deviations("mood-valence", concerning=0), [drift]
    )
    item = _only(result)
    assert (item["out_of_expected"], item["sustained"], item["trend"]) == (0, False, True)
    assert item["readings"] == 10, "sus lecturas de la ventana se siguen contando"
    assert "tendencia sostenida cuenta aparte" in item["statement"]
    # Sin ninguna lectura en la ventana: se dice igual, sin fracción.
    bare = _only(persistence(Domain.BEHAVIORAL, [], [drift]))
    assert (bare["readings"], bare["fraction"], bare["trend"]) == (0, None, True)


def test_persistence_only_looks_at_the_domain_of_the_alert() -> None:
    series = _deviations(concerning=5)
    assert persistence(Domain.BONE, series, [_falling("mood-valence")]) == {
        "indicators": [], "sustained": 0, "statement": NO_READINGS,
        "basis": alert_support.PERSISTENCE_BASIS,
    }


# --------------------------------------------------------------------------- #
# Confianza: recuentos, sin cifra única
# --------------------------------------------------------------------------- #

def _observations(series: list[Deviation], confidences: dict[int, float]) -> list[Any]:
    return [
        fhir.observation(
            item.key, item.value, item.effective, "crew-01", "wearable-ble",
            confidence=confidences.get(index, fhir.FULL_CONFIDENCE),
        )
        for index, item in enumerate(series)
    ]


def test_confidence_counts_the_readings_out_of_expected_of_the_domain() -> None:
    series = _deviations(concerning=4)
    below = fhir.LOW_CONFIDENCE_THRESHOLD - 0.01
    # Una dudosa, una declarada, dos sin declarar; y una dudosa dentro de lo esperado.
    observed = _observations(series, {0: below, 1: 0.8, 7: below})
    result = confidence(Domain.BEHAVIORAL, series, observed)
    [item] = result["indicators"]
    assert (item["readings"], item["low_confidence"], item["declared"], item["undeclared"]) == (
        4, 1, 1, 2
    )
    assert (item["not_found"], item["personal_baseline"], item["population_range"]) == (0, 4, 0)
    assert item["compared_with"] == ["línea base personal"]
    assert item["statement"] == (
        "Tiempo de reacción medio en la tarea de vigilancia psicomotora (PVT): 4 lecturas fuera "
        "de lo esperado; de "
        "baja confianza de medida, 1; sin confianza declarada, 2; frente a línea base personal."
    )
    assert (result["readings"], result["low_confidence"], result["undeclared"]) == (4, 1, 2)
    assert result["statement"] == (
        "Lecturas fuera de lo esperado de este dominio en la ventana actual: 4. De baja "
        "confianza de medida: 1. Sin confianza declarada: 2. Juzgadas contra la línea base "
        "personal: 4; contra el rango poblacional: 0."
    )
    assert result["trend_note"] is None


def test_the_low_confidence_boundary_is_the_one_of_the_ingest() -> None:
    series = _deviations(concerning=2)
    threshold = fhir.LOW_CONFIDENCE_THRESHOLD
    result = confidence(
        Domain.BEHAVIORAL, series, _observations(series, {0: threshold, 1: threshold - 1e-9})
    )
    assert result["low_confidence_threshold"] == threshold
    # En el umbral justo no es baja (la regla es `<`, la de `VitalObservation`).
    assert (result["low_confidence"], result["declared"]) == (1, 1)


def test_it_says_against_what_each_indicator_was_judged() -> None:
    personal = _deviations(concerning=3)
    population = _deviations("sleep-efficiency", concerning=2, population=True)
    current = [*personal, *population]
    result = confidence(Domain.BEHAVIORAL, current, _observations(current, {}))
    by_key = {item["key"]: item for item in result["indicators"]}
    assert by_key[KEY]["compared_with"] == ["línea base personal"]
    assert by_key["sleep-efficiency"]["compared_with"] == ["rango poblacional"]
    assert (result["personal_baseline"], result["population_range"]) == (3, 2)


def test_a_reading_without_its_observation_is_not_given_a_confidence() -> None:
    series = _deviations(concerning=3)
    result = confidence(Domain.BEHAVIORAL, series, _observations(series, {})[1:])
    assert (result["not_found"], result["undeclared"], result["low_confidence"]) == (1, 2, 0)


def test_there_is_no_single_confidence_figure() -> None:
    series = _deviations(concerning=4)
    result = confidence(Domain.BEHAVIORAL, series, _observations(series, {0: 0.2}))
    assert result["note"] == NO_SINGLE_FIGURE
    assert "Sin cifra única de confianza" in result["note"]
    # Todo número del bloque es un recuento, salvo el umbral del motor.
    figures = {
        key: value for key, value in result.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    assert figures.pop("low_confidence_threshold") == fhir.LOW_CONFIDENCE_THRESHOLD
    assert all(isinstance(value, int) for value in figures.values()), figures
    assert not {"confidence", "score", "value", "level"} & result.keys()


def test_an_alert_held_by_a_trend_says_the_trend_ignores_confidence() -> None:
    drift = _falling("mood-valence")
    result = confidence(Domain.BEHAVIORAL, _deviations(concerning=0), [], [drift])
    assert (result["readings"], result["indicators"]) == (0, [])
    assert result["statement"] == NO_READINGS
    assert result["trend_note"] == TREND_NOTE


# --------------------------------------------------------------------------- #
# Lenguaje y segregación
# --------------------------------------------------------------------------- #

def test_every_sentence_passes_the_language_guard() -> None:
    texts: list[str] = [NO_CHECKS, NO_EVIDENCE, NO_READINGS, NO_SINGLE_FIGURE,
                        alert_support.PERSISTENCE_BASIS, alert_support.CONFIDENCE_BASIS,
                        alert_support.DEMO_EVIDENCE, *alert_support.BASIS_DISPLAY.values(),
                        *alert_support.ROLE_DISPLAY.values()]
    burst = _deviations(concerning=risk.min_severe_readings(40), total=40, severity=Severity.SEVERE)
    for series in (_deviations(concerning=4), _deviations(concerning=1), burst):
        shown = persistence(Domain.BEHAVIORAL, series, [_falling(KEY)])
        texts += [shown["statement"], *(item["statement"] for item in shown["indicators"])]
        counted = confidence(Domain.BEHAVIORAL, series, _observations(series, {}))
        texts += [counted["statement"], *(item["statement"] for item in counted["indicators"])]
    for domain in Domain:
        result = support(domain, _everything())
        texts += [result["checks"]["statement"], result["evidence"]["statement"]]
    assert len(set(texts)) > 20, "la prueba tiene que mirar textos de verdad"
    assert [(text, check(text)) for text in texts if check(text)] == []


def _imported_names(module: object) -> set[str]:
    tree = ast.parse(inspect.getsource(module))  # type: ignore[arg-type]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def test_the_engine_does_not_know_this_layer_and_the_layer_cannot_decide() -> None:
    for engine in (risk, baseline, trend):
        assert not [name for name in _imported_names(engine) if "alert_support" in name]
    source = inspect.getsource(alert_support)
    for decides in ("RiskEngine", "BaselineEngine", "level_for", "combine_findings"):
        assert decides not in source
    # Y no se trae una copia de la fracción: la lee del motor cada vez.
    assert "_PERSISTENCE_FRACTION =" not in source
    assert "0.30" not in source and "0.3," not in source


def test_the_layer_does_not_alter_what_it_reads() -> None:
    current = _deviations(concerning=4)
    trends = [_falling("mood-valence")]
    observed = _observations(current, {0: 0.2})
    before = (list(current), list(trends), list(observed))
    persistence(Domain.BEHAVIORAL, current, trends)
    confidence(Domain.BEHAVIORAL, current, observed, trends)
    assert (current, trends, observed) == before


# --------------------------------------------------------------------------- #
# De punta a punta: las siete respuestas, y el veredicto no se mueve (invariante 5)
# --------------------------------------------------------------------------- #

@pytest.fixture
def client(tmp_path: Any) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    """Todo lo que el estado decide: niveles, puntuaciones, motivos, alertas y consejo."""
    return {
        "overall": status["overall_level"],
        "summary": status["summary"],
        "domains": {
            key: (value["score"], value["level"], value["drivers"])
            for key, value in status["domains"].items()
        },
        "alerts": [
            {key: value for key, value in alert.items() if key != "detail"}
            | {"onset": alert["detail"]["onset"]}
            for alert in status["alerts"]
        ],
        "recommendations": status["recommendations"],
    }


@pytest.mark.parametrize("scenario", ["co2-fatigue", "dehydration", "progressive-insomnia"])
def test_the_verdict_is_identical_with_and_without_the_new_detail(
    scenario: str, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/simulate", params={"scenario": scenario, "days": 40, "crew_size": 1})
    full = client.get("/api/status").json()
    assert full["alerts"], "el escenario tiene que alertar para que la prueba diga algo"

    for alert in full["alerts"]:
        detail = alert["detail"]
        # Las siete preguntas de §10, todas del backend.
        for answer in ("changed", "onset_basis", "context", "relevance", "checks", "evidence"):
            assert answer in detail, answer
        assert all("compared_with" in item for item in detail["changed"])
        # Qué comprobar y qué evidencia: lo mismo que el estado recomienda para el dominio.
        related = [item for item in full["recommendations"] if item["domain"] == detail["domain"]]
        assert related, "una alerta activa tiene recomendación en su dominio"
        assert [item["title"] for item in detail["checks"]["items"]] == [
            item["action"] for item in related
        ]
        assert [item["id"] for item in detail["checks"]["items"]] == [
            item["countermeasure"]["id"] for item in related
        ]
        cited = [ref["id"] for item in related for ref in item["evidence"]]
        assert [item["id"] for item in detail["evidence"]["items"]] == list(dict.fromkeys(cited))
        assert all(item["grade"]["label"] for item in detail["evidence"]["items"])

        # Persistencia: los indicadores sostenidos por sus lecturas más las tendencias son
        # exactamente los motivos que el motor dio para el dominio (radiación suma entorno).
        drivers = full["domains"][detail["domain"]]["drivers"]
        shown = detail["persistence"]
        if detail["domain"] != "radiation":
            assert shown["sustained"] + len(detail["trends"]) == len(drivers)
        for item in shown["indicators"]:
            assert 0 <= item["out_of_expected"] <= item["readings"]
            assert item["required_fraction"] == risk._PERSISTENCE_FRACTION
        # Los indicadores de «qué cambió» son los que tienen lecturas fuera de lo esperado.
        assert {item["key"] for item in detail["changed"]} == {
            item["key"] for item in shown["indicators"] if item["out_of_expected"]
        }

        # Confianza: recuentos que cuadran, y el simulador no declara confianza.
        counted = detail["confidence"]
        assert counted["readings"] == sum(item["out_of_expected"] for item in shown["indicators"])
        assert counted["readings"] == (
            counted["low_confidence"] + counted["declared"] + counted["undeclared"]
            + counted["not_found"]
        )
        assert (counted["not_found"], counted["low_confidence"]) == (0, 0)
        assert counted["undeclared"] == counted["readings"]
        assert counted["readings"] == counted["personal_baseline"] + counted["population_range"]
        assert counted["note"] == NO_SINGLE_FIGURE

    # Sin la pieza nueva: el veredicto es el mismo, cifra a cifra.
    monkeypatch.setattr(alert_support, "support", lambda *args, **kwargs: {})
    monkeypatch.setattr(alert_support, "persistence", lambda *args, **kwargs: {})
    monkeypatch.setattr(alert_support, "confidence", lambda *args, **kwargs: {})
    bare = client.get("/api/status").json()
    for alert in bare["alerts"]:
        assert "checks" not in alert["detail"] and "evidence" not in alert["detail"]
        assert (alert["detail"]["persistence"], alert["detail"]["confidence"]) == ({}, {})
    assert _verdict(bare) == _verdict(full)
