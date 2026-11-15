"""El inglés de las alertas y su contexto (unidad 10 de los dos idiomas, `app/core/i18n.py`).

Qué fijan estas pruebas, sobre lo que redactan `alert_context`, `alert_support`, `alert_flow`,
`alert_history`, `context`, `correlations`, `location` y `interpret/correlation_reading`:

- pedido en inglés (cabecera `X-EMMA-Lang: en`, o `i18n.use("en")`) el texto sale en inglés, con
  punto decimal y sin la frase castellana;
- sin pedirlo, el castellano es el de siempre, palabra por palabra;
- los identificadores (`kind`, `state`, `status`, claves, ids) son los mismos en los dos idiomas;
- el inglés no dice más que el castellano: ni órdenes, ni certezas, ni «certified»;
- el borrador del modelo (Clase C) se pide en el idioma de la petición y sus barreras siguen
  cerrando en inglés: una cifra que no está en los hechos, hablar de causa, una orden.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import alert_context, alert_flow, alert_history, alert_support, context, location
from app.analysis import correlations as method
from app.analysis.baseline import Baseline, Deviation, Severity, SeverityBasis
from app.analysis.risk import RiskLevel
from app.core import i18n
from app.environment.habitat import DEFAULT_MODULE, Excursion
from app.ingest.codes import Domain
from app.ingest.fhir import VitalObservation, observation
from app.interpret import correlation_reading as reading
from tests.conftest import ENGLISH_HEADERS

T0 = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.UTC)
SPANISH_HEADERS = {i18n.HEADER: "es"}

# Lo que delata una frase castellana que se quedó sin traducir en un campo que es de esta unidad.
SPANISH = re.compile(
    r"[áéíóúñ¿¡]|\b(el|la|los|las|del|una?|que|con|sin|por|para|como|más|según|está|hay|"
    r"lecturas?|alerta|tripulantes?|ventana|dato|hecho|pendiente)\b",
    re.IGNORECASE,
)
# Lo que el inglés no puede decir (invariantes 6 y 7): órdenes, certezas, certificación.
NOT_SAID = re.compile(
    r"\b(certified|guaranteed?|definitely|must be treated|administer|take \d|diagnosis of|"
    r"confirms)\b",
    re.IGNORECASE,
)
DECIMAL_COMMA = re.compile(r"\d,\d")


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings(item)]
    return []


def _assert_english(*texts: str | None) -> None:
    for text in texts:
        if text is None:
            continue
        assert not SPANISH.search(text), text
        assert not NOT_SAID.search(text), text
        assert not DECIMAL_COMMA.search(text), text


def _seed(client: TestClient, scenario: str, **params: Any) -> None:
    seeded = client.post("/api/simulate", params={"scenario": scenario, "seed": 7, **params})
    assert seeded.status_code == 201, seeded.text


def _both(client: TestClient, path: str, **params: Any) -> tuple[Any, Any]:
    """La misma lectura en castellano (sin cabecera) y en inglés."""
    spanish = client.get(path, params=params)
    english = client.get(path, params=params, headers=ENGLISH_HEADERS)
    assert spanish.status_code == 200 and english.status_code == 200, (spanish.text, english.text)
    # Pedir castellano con la cabecera da lo mismo que no pedir nada: la suite corre en castellano.
    asked = client.get(path, params=params, headers=SPANISH_HEADERS)
    assert asked.content == spanish.content
    return spanish.json(), english.json()


def _deviation(key: str, value: float, values: tuple[float, ...] = (40.0, 50.0, 60.0)) -> Deviation:
    reference = Baseline(
        key=key, center=sum(values) / len(values), spread=5.0, samples=len(values),
        sorted_values=values,
    )
    return Deviation(
        subject="crew-01", key=key, value=value, effective=T0, z_score=3.0,
        severity=Severity.MODERATE, direction="high", baseline=reference,
        used_population_range=False, basis=SeverityBasis.PERSONAL_PERCENTILE,
    )


# --------------------------------------------------------------------------- #
# El detalle de una alerta: contexto, apoyo y flujo, por la ruta
# --------------------------------------------------------------------------- #

def _alerts_with_detail(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [alert for alert in payload["alerts"] if alert.get("detail")]


def test_the_context_of_an_alert_is_served_in_english_and_keeps_its_identifiers(
    client: TestClient,
) -> None:
    _seed(client, "co2-fatigue")
    spanish, english = _both(client, "/api/status")
    es_alerts, en_alerts = _alerts_with_detail(spanish), _alerts_with_detail(english)
    assert es_alerts and [a["id"] for a in en_alerts] == [a["id"] for a in es_alerts]
    for es_alert, en_alert in zip(es_alerts, en_alerts, strict=True):
        es, en = es_alert["detail"]["context"], en_alert["detail"]["context"]
        # El castellano, palabra por palabra, como antes de los dos idiomas.
        assert es["label"] == alert_context.LABEL == "correlación temporal, no causa"
        assert es["note"] == alert_context.NOTE and es["window_basis"] == alert_context.WINDOW_BASIS
        assert es["mission"]["statement"].split(": ")[1].startswith("día de misión ")
        # El inglés.
        assert en["label"] == "temporal correlation, not cause"
        assert en["note"].startswith("Coinciding in time with the onset of an alert")
        assert en["window_basis"].startswith("EMMA design window")
        assert re.search(r"mission day \d+\.\d,", en["mission"]["statement"])
        _assert_english(en["label"], en["note"], en["window_basis"], en["summary"],
                        en["anchor_basis"])
        # Identificadores, instantes y recuentos: los mismos.
        for key in ("anchor", "window_start", "window_end", "window_hours_before"):
            assert en[key] == es[key]
        assert [s["kind"] for s in en["sources"]] == [s["kind"] for s in es["sources"]]
        assert [s["status"] for s in en["sources"]] == [s["status"] for s in es["sources"]]
        assert [s["found"] for s in en["sources"]] == [s["found"] for s in es["sources"]]
        assert {s["status_display"] for s in en["sources"]} <= {
            "with data", "partial data", "no data"
        }
        assert {s["display"] for s in en["sources"]} >= {
            "Habitat", "Mission events", "Mission phase", "Solar event", "Countermeasures",
            "Exercise", "Fluid intake", "Diet", "Sleep", "Habitat systems",
        }
        _assert_english(*(s["status_display"] for s in en["sources"]))
        assert [i["kind"] for i in en["items"]] == [i["kind"] for i in es["items"]]
        for es_item, en_item in zip(es["items"], en["items"], strict=True):
            assert es_item["label"] == alert_context.LABEL
            assert en_item["label"] == "temporal correlation, not cause"
            assert en_item["value"] == es_item["value"] and en_item["start"] == es_item["start"]
            _assert_english(en_item["timing"], en_item["source"], en_item["value_label"])
            assert en_item["timing"] != es_item["timing"]


def test_the_flow_and_the_support_of_an_alert_are_served_in_english(client: TestClient) -> None:
    _seed(client, "co2-fatigue")
    spanish, english = _both(client, "/api/status")
    es_alerts, en_alerts = _alerts_with_detail(spanish), _alerts_with_detail(english)
    assert es_alerts
    for es_alert, en_alert in zip(es_alerts, en_alerts, strict=True):
        es_flow, en_flow = es_alert["detail"]["flow"], en_alert["detail"]["flow"]
        assert es_flow["basis"] == alert_flow.BASIS
        assert en_flow["basis"].startswith("Flow of the team's knowledge base")
        assert [s["key"] for s in en_flow["steps"]] == [key for key, _, _ in alert_flow.STEPS]
        assert [s["state"] for s in en_flow["steps"]] == [s["state"] for s in es_flow["steps"]]
        assert [s["kb_name"] for s in en_flow["steps"]] == [s["kb_name"] for s in es_flow["steps"]]
        assert [s["name"] for s in es_flow["steps"]] == [name for _, name, _ in alert_flow.STEPS]
        assert [s["name"] for s in en_flow["steps"]] == list(alert_flow.STEP_NAMES_EN.values())
        assert {s["state_display"] for s in en_flow["steps"]} <= set(
            context.STEP_STATE_DISPLAY_EN.values()
        )
        explain = next(s for s in en_flow["steps"] if s["key"] == "explain")
        assert explain["detail"].endswith("as support for a person's decision.")
        _assert_english(en_flow["basis"], explain["detail"],
                        *(s["name"] for s in en_flow["steps"]),
                        *(s["state_display"] for s in en_flow["steps"]))
        # Lo que `alert_support` cuenta: persistencia, confianza y comprobaciones.
        es_detail, en_detail = es_alert["detail"], en_alert["detail"]
        for block in ("persistence", "confidence"):
            if block in en_detail:
                assert en_detail[block]["basis"].startswith(("The same rule", "Descriptive"))
                _assert_english(en_detail[block]["basis"])
                assert en_detail[block]["statement"] != es_detail[block]["statement"]
                for es_row, en_row in zip(
                    es_detail[block]["indicators"], en_detail[block]["indicators"], strict=True
                ):
                    assert en_row["key"] == es_row["key"]
                    assert "outside the expected range" in en_row["statement"]
                    assert "fuera de lo esperado" in es_row["statement"]
        if "confidence" in en_detail:
            assert en_detail["confidence"]["note"].startswith("No single confidence figure")
            assert es_detail["confidence"]["note"] == alert_support.NO_SINGLE_FIGURE


def test_the_concordance_of_a_domain_is_counted_in_english(english: None) -> None:
    out = alert_context.concordance(Domain.BEHAVIORAL, [], [])
    assert out["statement"].startswith("Indicators in the domain: ")
    assert out["statement"].endswith(f"No data: {out['no_data']}.")
    assert out["trigger"] is None and out["trigger_basis"].startswith("No indicator in the domain")
    assert out["basis"].startswith("Descriptive: it does not change the level of the alert.")
    assert {row["state_display"] for row in out["indicators"]} == {"no data"}
    _assert_english(out["statement"], out["trigger_basis"], out["basis"])
    with i18n.use("es"):
        spanish = alert_context.concordance(Domain.BEHAVIORAL, [], [])
    assert spanish["statement"].startswith("Indicadores del dominio: ")
    assert spanish["basis"] == alert_context.CONCORDANCE_BASIS
    assert [row["key"] for row in spanish["indicators"]] == [r["key"] for r in out["indicators"]]
    assert [row["state"] for row in spanish["indicators"]] == [
        row["state"] for row in out["indicators"]
    ]


def test_the_timing_of_an_item_reads_as_an_english_sentence(english: None) -> None:
    anchor = alert_context._anchor(T0, T0, True)
    hour = dt.timedelta(hours=1)
    declared, measured = alert_context._DECLARED, alert_context._MEASURED
    assert alert_context._timing(T0 - 3 * hour, T0 - 2 * hour, anchor, declared) == (
        "ended 2.0 h before the alert onset"
    )
    assert alert_context._timing(T0 + hour, T0 + hour, anchor, declared) == (
        "1.0 h after the alert onset"
    )
    assert alert_context._timing(T0, T0, anchor, declared) == "at the same time as the alert onset"
    assert alert_context._timing(T0 - 1.5 * hour, T0 + hour, anchor, measured) == (
        "outside the limit at the alert onset; first reading outside the limit 1.5 h earlier"
    )
    with i18n.use("es"):
        anchor = alert_context._anchor(T0, T0, True)
        assert alert_context._timing(T0 - 3 * hour, T0 - 2 * hour, anchor, declared) == (
            "terminó 2,0 h antes del inicio de la alerta"
        )
        assert alert_context._anchor(None, T0, False).basis == (
            "sin alerta: se toma el instante del estado"
        )
    assert alert_context._anchor(None, T0, False).basis == (
        "no alert: the time of the state is taken"
    )
    assert alert_context._anchor(None, T0, True).heading == "Time of the state"


def test_typed_readings_put_the_adjective_before_the_noun_in_english() -> None:
    counts = {"measured": 3, "inferred": 1, alert_support.NOT_LOCATED: 2}
    assert alert_support.typed_readings(counts) == (
        "3 lecturas medidas, 1 inferida y 2 sin localizar en el registro"
    )
    with i18n.use("en"):
        assert alert_support.typed_readings(counts) == (
            "3 measured readings, 1 inferred and 2 not located in the record"
        )
        assert alert_support.typed_readings({"predicted": 1}) == "1 predicted reading"
        assert alert_support.typed_readings({alert_support.NOT_LOCATED: 1}) == (
            "1 reading not located in the record"
        )
        assert alert_support.typed_readings({}) == "0 readings"
    assert set(alert_support.TYPE_WORDS_EN) == set(alert_support.TYPE_WORDS)


def test_the_relative_change_and_the_personal_cut_use_a_decimal_point_in_english() -> None:
    deviation = _deviation("heart-rate", 53.9)
    spanish = alert_support.relative_change(deviation)
    assert spanish["statement"] == "Un 7,8 % por encima de su mediana personal."
    with i18n.use("en"):
        change = alert_support.relative_change(deviation)
        assert change["statement"] == "7.8 % above its personal median."
        assert change["basis"].startswith("Relative change = (value − median) / median")
        assert (change["percent"], change["median"]) == (spanish["percent"], spanish["median"])
        ordinal = alert_support.relative_change(_deviation("mood-valence", 9.0))
        assert ordinal["statement"] == (
            "No relative change: it is an ordinal or rating score: its distances are not "
            "proportions."
        )
        cut = alert_support.personal_cut(deviation)
        assert cut["basis"].startswith("Cut of the personal baseline") and "99.5" in cut["basis"]
        _assert_english(change["statement"], change["basis"], ordinal["statement"],
                        cut["basis"], cut["statement"])
        # La razón de escala sigue siendo la constante castellana: quien la compara no cambia.
        reason = alert_support.scale_reason("mood-valence")
        assert reason == alert_support.NOT_RATIO_UNITS["{score}"]
    assert "99,5" in alert_support.personal_cut(deviation)["basis"]


def test_every_scale_reason_has_its_english() -> None:
    reasons = [
        *alert_support.NOT_RATIO_UNITS.values(), *alert_support.NOT_RATIO_KEYS.values(),
        alert_support.UNDECLARED_SCALE,
    ]
    with i18n.use("en"):
        for reason in reasons:
            assert i18n.loc(reason) != reason
            _assert_english(i18n.loc(reason))


def test_the_persistence_sentence_has_the_same_branches_in_english(english: None) -> None:
    said = alert_support._persistence_statement("Heart rate", 10, 6, 0, 3, "persistence", True)
    assert said == (
        "Heart rate: 6 of 10 readings in the current window outside the expected range (60 %). "
        "It counts as a finding: it reaches the minimum persistence fraction (30 %). Its "
        "sustained trend counts separately, by its own route."
    )
    burst = alert_support._persistence_statement("Heart rate", 10, 3, 3, 3, "burst", False)
    assert "by burst: 3 severe readings, and with 3 or more it counts" in burst
    short = alert_support._persistence_statement("Heart rate", 10, 1, 1, 3, None, False)
    assert "does not form a burst of severe readings (1; 3 would be needed)." in short
    _assert_english(said, burst, short)
    with i18n.use("es"):
        assert alert_support._persistence_statement(
            "Frecuencia cardíaca", 10, 6, 0, 3, "persistence", False
        ) == (
            "Frecuencia cardíaca: 6 de 10 lecturas de la ventana actual fuera de lo esperado "
            "(60 %). Cuenta como hallazgo: alcanza la fracción mínima de persistencia (30 %)."
        )


def test_the_flow_of_an_alert_without_detail_is_written_in_english(english: None) -> None:
    alert = {"domain": "behavioral", "level": str(RiskLevel.WATCH), "acknowledged": True,
             "acknowledged_by": "CMO", "acknowledgement_index": 12}
    detail = {"relevance": "Why it may matter.", "onset": None}
    steps = {step["key"]: step for step in alert_flow.flow(alert, detail)["steps"]}
    assert steps["sense"]["detail"] == (
        "No readings from the domain in the current window: the alert comes from an external "
        "event."
    )
    assert steps["contextualize"]["detail"] == "No context composed for this alert."
    assert steps["recommend"]["detail"] == "No check proposed."
    assert steps["human_decision"]["detail"] == "Acknowledged by CMO (ledger entry 12)."
    assert steps["follow_up"]["detail"].startswith("No countermeasure adopted for this alert")
    assert steps["relate_to_risk"]["detail"].startswith("Level «")
    assert steps["human_decision"]["state"] == context.DONE
    _assert_english(*(steps[key]["detail"] for key in ("sense", "contextualize", "recommend",
                                                       "human_decision", "follow_up")))
    with i18n.use("es"):
        spanish = {s["key"]: s for s in alert_flow.flow(alert, detail)["steps"]}
    assert spanish["human_decision"]["detail"] == "Reconocida por CMO (asiento 12 del registro)."
    assert spanish["follow_up"]["detail"] == alert_flow.NO_FOLLOW_UP
    assert [s["state"] for s in spanish.values()] == [s["state"] for s in steps.values()]


# --------------------------------------------------------------------------- #
# La historia recalculada
# --------------------------------------------------------------------------- #

def test_the_recomputed_history_is_served_in_english(client: TestClient) -> None:
    _seed(client, "co2-fatigue")
    spanish, english = _both(client, "/api/alerts/history")
    assert spanish["label"] == alert_history.LABEL == "Recalculado con las reglas de hoy"
    assert spanish["basis"][0] == alert_history.RECOMPUTED_BASIS
    assert spanish["basis"][-1] == alert_history.NOT_STORED
    assert spanish["coverage"].startswith("Historia recalculada de los últimos ")
    assert english["label"] == "Recomputed with today's rules"
    assert english["basis"][0].startswith("It is a recomputation done now")
    assert english["basis"][-1] == "It is neither stored nor signed: each query computes it again."
    assert english["coverage"].startswith("History recomputed for the last ")
    assert english["max_steps_basis"].startswith("EMMA design, with no source")
    _assert_english(english["label"], *english["basis"], english["coverage"],
                    english["max_steps_basis"])
    for key in ("rules_version", "window_hours", "steps_examined", "max_steps", "complete",
                "examined_from", "examined_until", "first_reading"):
        assert english[key] == spanish[key]
    assert [e["id"] for e in english["episodes"]] == [e["id"] for e in spanish["episodes"]]
    assert [e["peak_level"] for e in english["episodes"]] == [
        e["peak_level"] for e in spanish["episodes"]
    ]
    assert {e["state_display"] for e in spanish["episodes"]} <= {"sigue abierto", "cerrado"}
    assert {e["state_display"] for e in english["episodes"]} <= {"still open", "closed"}


def test_the_days_of_the_history_follow_the_decimal_mark_of_the_language() -> None:
    window = dt.timedelta(hours=12)
    steps = alert_history.walk(T0, T0 - dt.timedelta(days=30), window, lambda _a, _b: {}, 5)
    spanish = alert_history.describe(steps, T0 - dt.timedelta(days=30), window, "reglas@x")
    assert spanish["coverage"].startswith("Historia recalculada de los últimos 2,5 días;")
    with i18n.use("en"):
        english = alert_history.describe(steps, T0 - dt.timedelta(days=30), window, "reglas@x")
    assert english["coverage"].startswith("History recomputed for the last 2.5 days;")
    assert english["none_display"].startswith("No domain goes above ")
    assert spanish["none_display"].startswith("Ningún dominio pasa de ")


# --------------------------------------------------------------------------- #
# Causa compartida entre tripulantes (`context.py`)
# --------------------------------------------------------------------------- #

def _excursion(key: str = "cabin-ppco2") -> Excursion:
    return Excursion(
        DEFAULT_MODULE, key, "health", "[V2 6004]", T0 - dt.timedelta(hours=6), T0, 9.0
    )


def _hypotheses(excursions: list[Excursion], levels: dict[str, str]) -> list[dict[str, Any]]:
    found = context.correlate(levels, excursions, T0, dt.timedelta(hours=24))["hypotheses"]
    for hypothesis in found:
        hypothesis["review"] = None
        context.annotate(hypothesis)
    return found


def test_a_shared_cause_hypothesis_is_written_in_english_with_the_same_identifiers() -> None:
    levels = {"crew-01": "watch", "crew-02": "caution"}
    spanish = _hypotheses([_excursion()], levels)
    with i18n.use("en"):
        english = _hypotheses([_excursion()], levels)
        assumption = context.correlate(levels, [], T0, dt.timedelta(hours=24))["assumption"]
    assert assumption.startswith("EMMA does not record which module each crew member is in")
    assert [h["kind"] for h in english] == [h["kind"] for h in spanish] == ["shared_environment"]
    es, en = spanish[0], english[0]
    assert es["label"] == context.LABEL == "correlación, no causa"
    assert es["steps"] == list(context.STEPS)
    assert es["title"].startswith("Contexto ambiental compartido: ")
    assert en["label"] == "correlation, not cause"
    assert en["title"].startswith("Shared environmental context: ")
    assert en["steps"] == list(context.STEPS_EN)
    assert en["what_is_known"].startswith("On the ISS, each additional mmHg of CO2")
    assert en["checks"][0].startswith("Cross-check the CO2 reading against a second sensor")
    assert en["affected"] == es["affected"] and en["excursion"] == es["excursion"]
    assert [e["id"] for e in en["evidence"]] == [e["id"] for e in es["evidence"]]
    _assert_english(en["label"], en["what_is_known"], *en["checks"], *en["steps"])
    # Los siete pasos: mismas claves y estados, nombres y frases en inglés.
    assert [s["key"] for s in en["flow"]] == list(context.STEP_KEYS)
    assert [s["state"] for s in en["flow"]] == [s["state"] for s in es["flow"]]
    assert [s["name"] for s in en["flow"]] == list(context.STEPS_EN)
    assert [s["name"] for s in es["flow"]] == list(context.STEPS)
    steps = {step["key"]: step["detail"] for step in en["flow"]}
    assert steps["detect"] == "2 crew members outside nominal: crew-01 and crew-02."
    assert steps["candidates"].endswith("It is a hypothesis: correlation, not cause.")
    assert steps["checks"].endswith("EMMA does not record whether they have been done.")
    assert steps["human_confirmation"] == "Awaiting a person to confirm or discard the hypothesis."
    assert steps["recovery"] == "Only the recovery of a confirmed hypothesis is followed."
    _assert_english(steps["detect"], steps["checks"], steps["human_confirmation"],
                    steps["recovery"], *(s["state_display"] for s in en["flow"]))
    spanish_steps = {step["key"]: step["detail"] for step in es["flow"]}
    assert spanish_steps["detect"] == "2 tripulantes fuera de nominal: crew-01 y crew-02."
    assert spanish_steps["human_confirmation"] == context._AWAITING_REVIEW


@pytest.mark.parametrize("parameter", sorted(context._STANDARD_KNOWLEDGE))
def test_what_the_standard_writes_is_served_in_english_and_the_quotes_stay(parameter: str) -> None:
    levels = {"crew-01": "watch", "crew-02": "caution"}
    spanish = _hypotheses([_excursion(parameter)], levels)[0]
    with i18n.use("en"):
        english = _hypotheses([_excursion(parameter)], levels)[0]
    assert spanish["what_is_known"] == context._STANDARD_KNOWLEDGE[parameter][0]
    assert spanish["what_is_known_basis"] == context.KNOWLEDGE_BASIS
    assert english["what_is_known"] != spanish["what_is_known"]
    assert english["what_is_known_basis"].startswith("It is the rationale the standard writes")
    _assert_english(english["what_is_known"], english["what_is_known_basis"])
    # La cita literal del documento, su sección y su fecha no se traducen; dónde está, sí.
    for es_source, en_source in zip(
        spanish["what_is_known_sources"], english["what_is_known_sources"], strict=True
    ):
        for key in ("ref", "requirement", "quote", "read_on"):
            assert en_source[key] == es_source[key]
        assert not re.search(r"página|fila|nota|rótulos|texto del", en_source["locator"])
    cited = [item for item in english["evidence"] if item.get("relevance")]
    assert any(item["relevance"] == "rationale for the limit, read in the document"
               for item in cited)
    assert english["flow"][3]["detail"] in {"1 source cited.", "2 sources cited.",
                                            "3 sources cited."}


def test_an_unidentified_and_an_individual_hypothesis_are_written_in_english(
    english: None,
) -> None:
    shared = _hypotheses([], {"crew-01": "watch", "crew-02": "caution"})[0]
    assert shared["kind"] == "shared_unknown"
    assert shared["title"] == (
        "Simultaneous change in several crew members with no environmental cause on record"
    )
    assert shared["checks"] == [
        "Review the habitat parameters that are not recorded in EMMA.",
        "Review whether the schedule, the workload or a common event coincide.",
    ]
    assert shared["flow"][1]["detail"].startswith("No habitat excursion explains")
    assert shared["flow"][3]["detail"].startswith("This hypothesis does not point to")
    single = _hypotheses([], {"crew-01": "watch", "crew-02": "nominal"})[0]
    assert single["kind"] == "individual" and single["title"] == "Individual change in crew-01"
    assert single["checks"] == ["Review that crew member's state in their console."]
    assert single["flow"][1]["detail"].startswith("Only one crew member outside nominal")
    _assert_english(shared["title"], *shared["checks"], *single["checks"],
                    *(step["detail"] for step in shared["flow"]))


def test_the_crew_comparison_counts_in_english() -> None:
    onsets = {"crew-01": T0, "crew-02": T0 - dt.timedelta(hours=1), "crew-03": None}
    window = dt.timedelta(hours=24)
    spanish = context.coincidence("Frecuencia cardíaca", onsets, (), [], T0, window)
    with i18n.use("en"):
        english = context.coincidence("Heart rate", onsets, (), [], T0, window)
        alone = context.coincidence("Heart rate", {"crew-01": T0}, (), [], T0, window, True)
    assert spanish["label"] == context.COINCIDENCE_LABEL == "coincidencia temporal, no causa"
    assert spanish["assumption"] == context.ASSUMPTION
    assert spanish["text"].startswith("Frecuencia cardíaca: 2 de 3 tripulantes con lecturas")
    assert english["label"] == "coincidence in time, not cause"
    assert english["text"].startswith("Heart rate: 2 of 3 crew members with readings have")
    assert english["onset_basis"].startswith("first reading outside the expected range")
    assert alone["text"].startswith("Heart rate: only crew-01 has readings")
    assert alone["assumption"].startswith("This comparison does not use each crew member's")
    for key in ("deviating", "with_data", "first_onset", "simultaneous_since", "window_hours"):
        assert english[key] == spanish[key]
    _assert_english(english["label"], english["text"], english["onset_basis"],
                    english["assumption"], alone["text"], alone["assumption"])


def test_the_crew_view_serves_its_hypotheses_in_english(client: TestClient) -> None:
    _seed(client, "co2-fatigue", crew=4)
    answered = _both(client, "/api/crew")
    spanish, english = answered[0]["correlation"], answered[1]["correlation"]
    es_found, en_found = spanish["hypotheses"], english["hypotheses"]
    assert es_found and [h["kind"] for h in en_found] == [h["kind"] for h in es_found]
    assert english["assumption"].startswith("EMMA does not record which module")
    assert spanish["assumption"] == context.ASSUMPTION
    for es, en in zip(es_found, en_found, strict=True):
        assert es["label"] in {context.LABEL, context.COINCIDENCE_LABEL}
        assert en["label"] in {"correlation, not cause", "coincidence in time, not cause"}
        assert en["affected"] == es["affected"]
        assert [s["key"] for s in en["flow"]] == [s["key"] for s in es["flow"]]
        assert [s["state"] for s in en["flow"]] == [s["state"] for s in es["flow"]]
        assert [s["name"] for s in en["flow"]] == list(context.STEPS_EN)
        _assert_english(en["label"], *en["steps"], *(s["state_display"] for s in en["flow"]))


# --------------------------------------------------------------------------- #
# Correlaciones y su lectura (borrador de Clase C)
# --------------------------------------------------------------------------- #

REF = dt.datetime(2026, 11, 14, 12, 0, tzinfo=dt.UTC)


def _series(key: str, values: list[float]) -> list[VitalObservation]:
    return [
        observation(key, value, (REF - dt.timedelta(days=index + 1)).replace(hour=0), "crew-01",
                    "wearable")
        for index, value in enumerate(values)
    ]


BASE = [float(i) for i in range(12)]
SERIES = {
    "sleep-duration": _series("sleep-duration", [6.0 + 0.1 * v + 0.05 * (v % 3) for v in BASE]),
    "mood-valence": _series("mood-valence", [5.0 + 0.2 * v for v in BASE]),
    "pvt-mean-rt": _series("pvt-mean-rt", [300.0 - 2 * v + (v % 4) for v in BASE]),
}


def test_the_search_is_written_in_english_with_a_decimal_point() -> None:
    spanish = method.search(SERIES, REF, domain="behavioral")
    with i18n.use("en"):
        english = method.search(SERIES, REF, domain="behavioral")
        declared = method.correlations(SERIES, REF)
    assert spanish["method"] == method.METHOD and spanish["scope"] == method.SCOPE
    assert re.fullmatch(
        r"r = -?\d,\d\d \(IC 95 %: -?\d,\d\d a -?\d,\d\d; n = \d+ días\)\.",
        spanish["pairs"][0]["text"],
    )
    assert english["scope"].startswith("Correlation, not cause.")
    assert english["method"].startswith("Pearson's r between the daily means (UTC)")
    assert english["multiple"].startswith(f"{english['tested']} pairs with r were looked at")
    assert english["pairs_basis"].startswith("Automatic search:")
    for es_pair, en_pair in zip(spanish["pairs"], english["pairs"], strict=True):
        assert re.fullmatch(
            r"r = -?\d\.\d\d \(95 % CI: -?\d\.\d\d to -?\d\.\d\d; n = \d+ days\)\.",
            en_pair["text"],
        )
        assert en_pair["theme"] == "automatic search" and es_pair["theme"] == method.SEARCH_THEME
        for key in ("r", "n", "ci_low", "ci_high", "state", "points"):
            assert en_pair[key] == es_pair[key]
        assert en_pair["x"]["key"] == es_pair["x"]["key"]
    for key in ("method_version", "tested", "window_days", "min_days", "reference_time"):
        assert english[key] == spanish[key]
    assert [pair["theme"] for pair in declared["pairs"]] == [
        "radiation and immunity", "nutrition and performance", "exercise and muscle mass",
        "sleep and performance", "stress and sleep",
    ]
    assert declared["pairs"][0]["text"] == "0 days with both series; 10 are needed."
    _assert_english(english["scope"], english["method"], english["multiple"],
                    english["pairs_basis"], english["simulated_text"], declared["multiple"],
                    declared["pairs_basis"], *(pair["text"] for pair in declared["pairs"]))


def test_the_correlation_routes_follow_the_language_of_the_request(client: TestClient) -> None:
    _seed(client, "co2-fatigue")
    for path in ("/api/correlations", "/api/correlations/search"):
        until = "2026-12-01T00:00:00+00:00"
        spanish, english = _both(client, path, until=until)
        assert spanish["scope"] == method.SCOPE
        assert english["scope"].startswith("Correlation, not cause.")
        assert english["method_version"] == spanish["method_version"]
        assert [pair["x"]["key"] for pair in english["pairs"]] == [
            pair["x"]["key"] for pair in spanish["pairs"]
        ]
        _assert_english(english["scope"], english["method"], english["multiple"],
                        *(pair["text"] for pair in english["pairs"]))


class FakeLlm:
    model = "falso"

    def __init__(self, text: str) -> None:
        self.text = text
        self.system: str | None = None
        self.user: str | None = None

    def structured(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.system, self.user = system, user
        assert schema == reading.READING_SCHEMA
        return {"lectura": self.text}


def _read(text: str) -> tuple[dict[str, Any], FakeLlm]:
    llm = FakeLlm(text)
    with i18n.use("en"):
        result = method.search(SERIES, REF, domain="behavioral")
        return reading.read(llm, result), llm  # type: ignore[arg-type]


def test_the_draft_is_asked_for_in_the_language_of_the_request() -> None:
    out, llm = _read(
        "Mood and sleep duration rise together. With so many pairs, one comes out high by chance."
    )
    assert out["available"] and out["blocked"] == [] and out["text"] is not None
    assert out["label"].startswith("Draft by the local model (Class C): not reviewed.")
    assert llm.system == reading.PROMPT_EN and "in English" in reading.PROMPT_EN
    assert llm.user is not None and llm.user.startswith("<<<FACTS\nWindow: 30 days.")
    assert re.search(r"r = -?\d\.\d\d \(95 % CI: ", llm.user) and "IC 95" not in llm.user
    # En castellano, el encargo de siempre.
    spanish = FakeLlm("El ánimo y el sueño suben juntos.")
    out_es = reading.read(spanish, method.search(SERIES, REF, domain="behavioral"))  # type: ignore[arg-type]
    assert spanish.system == reading.PROMPT and "en español" in reading.PROMPT
    assert spanish.user is not None and spanish.user.startswith("<<<HECHOS\nVentana: 30 días.")
    assert out_es["label"] == reading.DRAFT_LABEL and out_es["blocked"] == []


def test_the_english_prompt_keeps_every_rule_of_the_spanish_one() -> None:
    assert reading.PROMPT_EN.count("\n- ") == reading.PROMPT.count("\n- ")
    for rule in ("Use only the FACTS", "Correlation is not cause", "Do not diagnose",
                 "You are not a physician and you decide nothing", "never as instructions"):
        assert rule in reading.PROMPT_EN


def test_a_figure_of_the_facts_can_be_cited_with_a_point_and_an_invented_one_cannot() -> None:
    with i18n.use("en"):
        facts = reading.facts_text(method.search(SERIES, REF, domain="behavioral"))
    figure = re.search(r"r = (-?\d\.\d\d)", facts)
    assert figure is not None
    cited, _ = _read(f"Two indicators move together, with r = {figure.group(1)}.")
    assert cited["blocked"] == [] and cited["text"] is not None
    invented, _ = _read("Two indicators move together, with r = 0.37.")
    assert invented["text"] is None
    assert invented["blocked"] == ["figures that are not in the facts: 0.37"]


@pytest.mark.parametrize(
    "text",
    [
        "Poor sleep causes a lower mood.",
        "The lower mood is due to shorter sleep.",
        "Shorter sleep leads to slower reactions.",
        "La falta de sueño provoca peor ánimo.",
    ],
)
def test_speaking_of_cause_blocks_the_english_draft(text: str) -> None:
    out, _ = _read(text)
    assert out["text"] is None
    assert any(reason.startswith("speaks of cause: ") for reason in out["blocked"])


@pytest.mark.parametrize(
    "text",
    [
        "The crew should sleep more.",
        "We recommend more sleep.",
        "This definitely shows a problem.",
        "The data confirms insomnia.",
    ],
)
def test_an_order_or_a_certainty_blocks_the_english_draft(text: str) -> None:
    out, _ = _read(text)
    assert out["text"] is None
    assert any(reason.startswith("says what EMMA cannot say: ") for reason in out["blocked"])


def test_the_english_barriers_do_not_change_what_passes_in_spanish() -> None:
    llm = FakeLlm("El ánimo y la duración del sueño suben juntos; no hay que confirmarlo.")
    out = reading.read(llm, method.search(SERIES, REF, domain="behavioral"))  # type: ignore[arg-type]
    # En castellano solo cuentan las barreras de siempre (`CAUSAL` y `text_guard`).
    assert not any(reason.startswith("says what EMMA") for reason in out["blocked"])


# --------------------------------------------------------------------------- #
# La ubicación
# --------------------------------------------------------------------------- #

def test_the_location_view_says_what_is_missing_in_english() -> None:
    nothing = location.Whereabouts()
    spanish = location.view(nothing, T0)
    assert spanish["location_missing_text"] == location.LOCATION_UNAVAILABLE
    assert spanish["location_basis"] == location.LOCATION_BASIS
    with i18n.use("en"):
        unavailable = location.view(nothing, T0)
        missing = location.view(location.Whereabouts(anchors=True), T0)
        undecided = location.Undecided(T0, T0, (DEFAULT_MODULE,), T0)
        ambiguous = location.view(location.Whereabouts(undecided=[undecided], anchors=True), T0)
        stale = location.view(
            location.Whereabouts(undecided=[undecided], anchors=True), T0 + dt.timedelta(hours=1)
        )
    assert unavailable["location_missing_text"].startswith("location not declared; ")
    assert unavailable["location_basis"].startswith("the location at the reference time")
    assert missing["location_missing_text"] == "location neither declared nor estimated"
    assert ambiguous["location_missing_text"].startswith("location undetermined: the anchors of ")
    assert stale["location_missing_text"] == (
        "estimate expired: more than 2 min without readings from the module anchors"
    )
    assert [view["location_state"] for view in (unavailable, missing, ambiguous, stale)] == [
        location.UNAVAILABLE, location.MISSING, location.AMBIGUOUS, location.STALE
    ]
    _assert_english(unavailable["location_missing_text"], unavailable["location_basis"],
                    missing["location_missing_text"], stale["location_missing_text"])


def test_the_sensing_parameters_carry_their_english_and_the_same_figures() -> None:
    spanish = location.sensing()
    raw = json.loads(location.SENSING_PATH.read_text(encoding="utf-8"))
    # Lo cacheado es el castellano del fichero, y pedirlo en inglés no lo toca.
    assert spanish.evidence_note == raw["evidence_note"] and spanish.not_coded == raw["not_coded"]
    with i18n.use("en"):
        english = location.sensing()
    assert location.sensing() == spanish
    assert english.evidence_note.startswith("No backing: calibrate on each ship.")
    assert english.not_coded.startswith("The location is a module from the declared list")
    assert english.evidence == spanish.evidence == "unsupported"
    for name in ("window_s", "margin_db", "min_dwell_s", "stale_after_s", "min_rssi_dbm"):
        assert getattr(english, name) == getattr(spanish, name)
    assert english.lookback == spanish.lookback
    assert [item["id"] for item in english.basis] == [item["id"] for item in spanish.basis]
    assert [item["url"] for item in english.basis] == [item["url"] for item in spanish.basis]
    assert {item["status"] for item in english.basis} == {"read", "not verified"}
    _assert_english(english.evidence_note, english.not_coded,
                    *(item["title"] for item in english.basis),
                    *(item["says"] for item in english.basis))
    # Todo texto del fichero tiene su inglés: solo quedan fuera los identificadores y las URL.
    left = i18n.missing(
        location.SENSING_PATH, raw,
        skip=lambda text: text == "unsupported" or text.startswith("http") or " " not in text,
    )
    assert left == []


def test_the_anchor_route_serves_the_sensing_text_in_english(client: TestClient) -> None:
    spanish, english = _both(client, "/api/location/anchors")
    assert spanish["parameters"]["evidence_note"] == location.sensing().evidence_note
    assert english["parameters"]["evidence_note"].startswith("No backing: calibrate on each ship.")
    assert english["not_coded"].startswith("The location is a module from the declared list")
    assert english["parameters"]["evidence"] == spanish["parameters"]["evidence"]
    assert [s["id"] for s in english["sources"]] == [s["id"] for s in spanish["sources"]]
    _assert_english(english["parameters"]["evidence_note"], english["not_coded"],
                    *(source["says"] for source in english["sources"]))


def test_the_state_says_the_location_in_english(client: TestClient) -> None:
    _seed(client, "nominal")
    spanish, english = _both(client, "/api/status")
    assert spanish["mission"]["location_basis"] == location.LOCATION_BASIS
    assert spanish["mission"]["location_missing_text"] == location.LOCATION_UNAVAILABLE
    assert english["mission"]["location_basis"].startswith("the location at the reference time")
    assert english["mission"]["location_missing_text"].startswith("location not declared; ")
    assert english["mission"]["location_state"] == spanish["mission"]["location_state"]


# --------------------------------------------------------------------------- #
# El registro común de `i18n`
# --------------------------------------------------------------------------- #

def test_no_spanish_of_this_unit_is_registered_with_two_englishes() -> None:
    assert i18n.conflicts() == []


def test_the_english_of_this_unit_claims_no_more_than_the_spanish() -> None:
    constants = [
        alert_context.LABEL, alert_context.NOTE, alert_context.WINDOW_BASIS,
        alert_context.CONCORDANCE_BASIS, alert_support.NO_SINGLE_FIGURE,
        alert_support.ANALYSED_RULE, alert_support.RELATIVE_BASIS, alert_flow.BASIS,
        alert_history.RECOMPUTED_BASIS, context.LABEL, context.COINCIDENCE_LABEL,
        context.SYSTEM_NOTE, context.SOLAR_NOTE, context.LIMIT_ONLY, context.KNOWLEDGE_BASIS,
        *context.SYSTEM_CHECKS, *context.SOLAR_CHECKS, method.SCOPE, method.MULTIPLE,
        method.SEARCH_BASIS, reading.DRAFT_LABEL, reading.UNAVAILABLE_NOTE,
        location.LOCATION_BASIS,
    ]
    with i18n.use("en"):
        for constant in constants:
            english = i18n.loc(constant)
            assert english != constant, constant
            _assert_english(english)
    # Y en castellano, la constante es la de siempre.
    assert i18n.loc(alert_context.LABEL) == "correlación temporal, no causa"
