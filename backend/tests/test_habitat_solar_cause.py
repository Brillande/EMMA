"""La radiación registrada en la ventana, como causa común candidata (§5.37.5).

La base de conocimiento del equipo pone «Radiación / posición / shielding» entre la telemetría
del hábitat con relevancia sanitaria (§6) y, para el riesgo de radiación, «fusionar hazard +
dosimetría» (§2.1). Estas pruebas fijan lo que eso significa en `context.correlate`, y lo que no
puede pasar:

- sin radiación registrada en la ventana, la salida es la de antes clave por clave (el mismo
  fichero de la prueba de no regresión de la ubicación);
- con ella, entra como «coincidencia temporal, no causa», detrás de las excursiones medidas y
  delante de los sistemas declarados, y dice de dónde sale (dosímetro o NASA DONKI) y que la tasa
  de dosis sola no dice si fue un evento solar;
- con uno o con varios afectados;
- no mueve niveles, afectados, excursiones ni `rules_version` (invariante 5), y respeta el corte
  de Tierra.
"""

import datetime as dt
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import context
from app.analysis.context import (
    COINCIDENCE_LABEL,
    SOLAR_CHECKS,
    SOLAR_KIND,
    SOLAR_NOTE,
    SYSTEM_KIND,
    UNIDENTIFIED_WITH_RADIATION,
    RadiationRecord,
    Stay,
    annotate,
    correlate,
)
from app.api import routes
from app.core.versioning import rules_version
from app.environment.donki import EventType, Severity, SolarEvent
from app.ingest.fhir import VitalObservation, observation
from app.text_guard import check
from tests.test_habitat import GOLDEN, T0, WINDOW, _excursion_in, _golden_cases, _slim

TWO = {"crew-01": "watch", "crew-02": "watch"}
DOSE = "absorbed-dose-rate"


def _hours(value: float) -> dt.datetime:
    return T0 - dt.timedelta(hours=value)


def _dose(value: float, at: dt.datetime, subject: str = "crew-01") -> VitalObservation:
    return observation(DOSE, value, at, subject, "simulator:spe-event")


def _spike(subject: str = "crew-01", since_hours: int = 10) -> list[VitalObservation]:
    """Fondo de 12 µGy/h hasta hace `since_hours` y luego, cada hora, por encima de 100."""
    background = [_dose(12.0, _hours(h), subject) for h in range(30, since_hours, -1)]
    spike = [_dose(400.0 + 10 * h, _hours(h), subject) for h in range(since_hours, -1, -1)]
    return background + spike


def _sep(at: dt.datetime, event_id: str = "2026-11-30T20:00:00-SEP-001") -> SolarEvent:
    return SolarEvent(
        event_id=event_id, event_type=EventType.SEP, time=at, severity=Severity.HIGH,
        instruments=(), linked_event_ids=(), flare_class=None, link="",
    )


def _covering() -> tuple[dt.datetime, dt.datetime]:
    return (T0 - dt.timedelta(days=3), T0 + dt.timedelta(hours=1))


def test_without_radiation_in_the_window_the_output_is_the_one_from_before() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for radiation in (
        None,
        RadiationRecord({}),
        # Fondo, por debajo del límite de peligro.
        RadiationRecord({"crew-01": [_dose(12.0, _hours(h)) for h in range(10)]}),
        # Por encima del límite, pero antes de la ventana de 48 h o después del instante.
        RadiationRecord(
            {"crew-01": [_dose(900.0, _hours(60)), _dose(900.0, T0 + dt.timedelta(hours=1))]}
        ),
        # Otra clave por encima de su propio límite de peligro no es dosis.
        RadiationRecord({"crew-01": [observation("heart-rate", 250.0, _hours(2), "crew-01", "t")]}),
        # Un evento de DONKI fuera de la ventana.
        RadiationRecord({}, [_sep(_hours(60)), _sep(T0 + dt.timedelta(minutes=5))], _covering()),
    ):
        got = {
            name: _slim(correlate(levels, found, T0, WINDOW, None, None, radiation))
            for name, (levels, found) in _golden_cases().items()
        }
        assert json.loads(json.dumps(got)) == golden, radiation


def test_a_dose_above_its_limit_enters_as_a_coincidence_and_says_where_it_comes_from() -> None:
    result = correlate(TWO, [], T0, WINDOW, None, None, RadiationRecord({"crew-01": _spike()}))
    assert [item["kind"] for item in result["hypotheses"]] == [SOLAR_KIND, "shared_unknown"]
    first, unknown = result["hypotheses"]
    assert first["label"] == COINCIDENCE_LABEL == "coincidencia temporal, no causa"
    assert first["title"] == (
        "Tasa de dosis por encima de su límite de peligro dentro de la ventana comparada"
    )
    assert first["affected"] == ["crew-01", "crew-02"] and first["excursion"] is None
    assert first["checks"] == list(SOLAR_CHECKS)
    radiation = first["radiation"]
    assert radiation["statement"] == (
        "Tasa de dosis absorbida por encima de su límite de peligro (100,0 µGy/h) en 11 lecturas "
        "del dosímetro de crew-01, la primera 10,0 h antes del instante comparado, con un máximo "
        "de 500,0 µGy/h; origen de las lecturas: simulator:spe-event. Sin datos de NASA DONKI que "
        "cubran la ventana: la tasa de dosis sola no dice si fue un evento solar."
    )
    dose = radiation["dose"]
    assert (dose["subjects"], dose["readings"], dose["peak"], dose["limit"]) == (
        ["crew-01"], 11, 500.0, 100,
    )
    assert (dose["first"], dose["last"]) == (_hours(10).isoformat(), T0.isoformat())
    assert radiation["donki"] == {"status": "no_data", "events": []}
    # La cita dice para qué se cita, y para qué no.
    [cited] = first["evidence"]
    assert cited["id"] == "nasa-artemis2-eyes-on-sun"
    assert "no dice qué efecto tiene una dosis en las personas" in cited["relevance"]
    # «Sin causa ambiental registrada» sería falso con radiación registrada: no se dice.
    assert unknown["title"] == UNIDENTIFIED_WITH_RADIATION
    assert "sin causa ambiental registrada" not in json.dumps(result, ensure_ascii=False)
    annotate(first)
    assert first["knowledge_note"] == SOLAR_NOTE
    assert "no una causa" in SOLAR_NOTE and "ninguna fuente leída" in SOLAR_NOTE
    steps = {step["key"]: step for step in first["flow"]}
    assert radiation["statement"] in steps["correlate"]["detail"]
    assert "ninguna fuente leída dice que lo explique" in steps["correlate"]["detail"]
    assert steps["evidence"]["detail"] == (
        "1 fuente citada: dónde se mide la tasa de dosis en Orion, no qué efecto tiene una dosis "
        "en las personas."
    )
    assert steps["human_confirmation"]["state"] == "not_applicable"


def test_it_works_the_same_with_one_or_with_several_dosimeters_and_affected() -> None:
    # Varios dosímetros (el escenario a toda la tripulación): una sola hipótesis que los nombra.
    doses = {"crew-01": _spike("crew-01"), "crew-02": _spike("crew-02", 8)}
    [first, _] = correlate(TWO, [], T0, WINDOW, None, None, RadiationRecord(doses))["hypotheses"]
    assert "en 20 lecturas de los dosímetros de crew-01 y crew-02, la primera 10,0 h antes" in (
        first["radiation"]["statement"]
    )
    # Un solo afectado: la radiación se registra aparte de la tripulación, y se propone detrás
    # de la hipótesis individual.
    one = {"crew-01": "concern", "crew-02": "nominal"}
    result = correlate(one, [], T0, WINDOW, None, None, RadiationRecord({"crew-01": _spike()}))
    assert [item["kind"] for item in result["hypotheses"]] == ["individual", SOLAR_KIND]
    assert result["hypotheses"][1]["affected"] == ["crew-01"]
    annotate(result["hypotheses"][1])
    # Si su cambio es la propia tasa de dosis, la frase no la presenta como otra causa.
    assert "Coincide en el tiempo con el cambio de 1 tripulante. La parte de ese cambio que es " \
        "la propia tasa de dosis (dominio de radiación) es la misma medida, no otra causa" in (
        result["hypotheses"][1]["flow"][1]["detail"]
    )
    # Nadie afectado: no hay cambio con el que coincidir.
    nobody = correlate({"crew-01": "nominal"}, [], T0, WINDOW, None, None,
                       RadiationRecord({"crew-01": _spike()}))
    assert nobody["hypotheses"] == []


def test_the_measured_excursion_goes_first_and_a_declared_system_after() -> None:
    told = [{
        "system": "thermal-control", "state": "degraded", "at": _hours(30).isoformat(),
        "note": "", "declared_by": "CDR", "ledger_index": 3, "recorded": _hours(30).isoformat(),
    }]
    co2 = _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
    radiation = RadiationRecord({"crew-01": _spike()})
    result = correlate(TWO, co2, T0, WINDOW, None, told, radiation)
    assert [item["kind"] for item in result["hypotheses"]] == [
        "shared_environment", SOLAR_KIND, SYSTEM_KIND,
    ]
    # Sin excursión: radiación, sistema y la causa sin identificar, que habla de la cabina.
    result = correlate(TWO, [], T0, WINDOW, None, told, radiation)
    assert [item["kind"] for item in result["hypotheses"]] == [
        SOLAR_KIND, SYSTEM_KIND, "shared_unknown",
    ]
    assert result["hypotheses"][-1]["title"] == UNIDENTIFIED_WITH_RADIATION


def test_radiation_moves_no_level_affected_or_excursion() -> None:
    levels = {"crew-01": "concern", "crew-02": "watch", "crew-03": "nominal"}
    co2 = _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
    before = correlate(dict(levels), co2, T0, WINDOW)
    given = dict(levels)
    after = correlate(given, co2, T0, WINDOW, None, None, RadiationRecord({"crew-01": _spike()}))
    assert given == levels
    for key in ("affected", "habitat_excursions", "window_hours", "assumption"):
        assert after[key] == before[key]
    assert after["hypotheses"][: len(before["hypotheses"])] == before["hypotheses"]
    assert [item["kind"] for item in after["hypotheses"][len(before["hypotheses"]):]] == [
        SOLAR_KIND,
    ]


def test_donki_is_said_with_what_its_data_covers() -> None:
    # Un SEP de DONKI en la ventana, sin ninguna dosis por encima: entra igual, por el hazard.
    covered = RadiationRecord(
        {"crew-01": [_dose(12.0, _hours(1))]}, [_sep(_hours(5))], _covering(),
    )
    [first, _] = correlate(TWO, [], T0, WINDOW, None, None, covered)["hypotheses"]
    assert first["title"] == (
        "Evento de partículas solares registrado en NASA DONKI dentro de la ventana comparada"
    )
    assert first["radiation"]["statement"] == (
        "Ninguna lectura de tasa de dosis de la tripulación pasó de su límite de peligro en la "
        "ventana. NASA DONKI registra 1 evento de partículas solares en la ventana: "
        "2026-11-30T20:00:00-SEP-001 (5,0 h antes del instante comparado)."
    )
    assert first["radiation"]["dose"] is None
    assert first["radiation"]["donki"]["status"] == "with_data"
    assert first["radiation"]["donki"]["events"][0]["event_id"] == "2026-11-30T20:00:00-SEP-001"
    # Sin ninguna lectura de dosis en la ventana, se dice; y una cobertura parcial, también.
    partial = (T0 - dt.timedelta(hours=10), T0 + dt.timedelta(hours=1))
    [first, _] = correlate(
        TWO, [], T0, WINDOW, None, None, RadiationRecord({}, [_sep(_hours(5))], partial)
    )["hypotheses"]
    assert first["radiation"]["statement"].startswith(
        "Sin lecturas de tasa de dosis de la tripulación en la ventana. NASA DONKI registra"
    )
    assert first["radiation"]["statement"].endswith(
        " Sus datos cubren solo una parte de la ventana."
    )
    # Con la dosis por encima: DONKI que cubre la ventana y no registra nada, o solo una parte.
    for known, said in (
        (_covering(), "NASA DONKI no registra ningún evento de partículas solares en la ventana: "
                      "la tasa de dosis sola no dice si fue un evento solar."),
        (partial, "Los datos de NASA DONKI cubren solo una parte de la ventana y no registran en "
                  "ella ningún evento de partículas solares: no se sabe si fue un evento solar."),
        # Datos de DONKI más viejos que la ventana entera: no se sabe nada de ella.
        ((T0 - dt.timedelta(days=6), T0 - dt.timedelta(days=5)),
         "Sin datos de NASA DONKI que cubran la ventana: la tasa de dosis sola no dice si fue un "
         "evento solar."),
    ):
        record = RadiationRecord({"crew-01": _spike()}, [], known)
        [first, _] = correlate(TWO, [], T0, WINDOW, None, None, record)["hypotheses"]
        assert first["radiation"]["statement"].endswith(said), known


def test_the_declared_location_does_not_demote_it() -> None:
    span = (T0 - dt.timedelta(days=3), T0 + dt.timedelta(days=1))
    away = [Stay("laboratorio", *span, 1)]
    result = correlate(TWO, [], T0, WINDOW, {"crew-01": away, "crew-02": away}, None,
                       RadiationRecord({"crew-01": _spike()}))
    first = result["hypotheses"][0]
    assert (first["kind"], first["likelihood"], first["likelihood_reason"]) == (
        SOLAR_KIND, "primary", None,
    )
    assert "location" not in first
    # Sin ubicación declarada, ni siquiera lleva esas claves (como el resto de hipótesis).
    [first, _] = correlate(
        TWO, [], T0, WINDOW, None, None, RadiationRecord({"crew-01": _spike()})
    )["hypotheses"]
    assert "likelihood" not in first


def test_every_new_text_passes_the_guard() -> None:
    texts = [SOLAR_NOTE, UNIDENTIFIED_WITH_RADIATION, *SOLAR_CHECKS, context.SOLAR_RELEVANCE]
    for record in (
        RadiationRecord({"crew-01": _spike()}),
        RadiationRecord({"crew-01": _spike(), "crew-02": _spike("crew-02")}, [], _covering()),
        RadiationRecord({}, [_sep(_hours(5)), _sep(_hours(2), "otro")], _covering()),
    ):
        for item in correlate(TWO, [], T0, WINDOW, None, None, record)["hypotheses"]:
            annotate(item)
            texts += [item["title"], *item["checks"], item.get("knowledge_note") or "",
                      *(step["detail"] for step in item["flow"])]
            if "radiation" in item:
                texts.append(item["radiation"]["statement"])
    # «dosis» a secas es la dosis de radiación, no una de fármaco: el filtro la caza siempre
    # (categoría `dosing`), y se aparta como en la escala de radiación
    # (`test_radiation_projection.py`). Todo lo demás —órdenes, certezas, diagnósticos, dosis con
    # vía o pauta— sí tiene que pasar.
    found = [
        (text, finding) for text in texts if text for finding in check(text)
        if (finding.category, finding.match.lower()) != ("dosing", "dosis")
    ]
    assert found == []


# --------------------------------------------------------------------------- #
# La vista de tripulación, con el escenario `spe-event`
# --------------------------------------------------------------------------- #


def _solar(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in body["correlation"]["hypotheses"] if item["kind"] == SOLAR_KIND]


def test_the_crew_view_reads_the_dosimetry_moves_no_level_and_ground_only_what_it_can_know(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.post("/api/simulate", params={"scenario": "spe-event", "days": 10, "crew_size": 4})
    body = client.get("/api/crew").json()
    [solar] = _solar(body)
    dose = solar["radiation"]["dose"]
    # El escenario sube la tasa de dosis de quien lo sufre, y lo firma el simulador.
    assert "crew-01" in dose["subjects"] and dose["sources"] == ["simulator:spe-event"]
    assert solar["radiation"]["donki"]["status"] == "no_data"  # sin red y sin caché
    assert solar["affected"] == body["correlation"]["affected"]
    assert solar["review"] is None and solar["knowledge_note"] == SOLAR_NOTE
    # Invariante 5, con cifras: los niveles de cada tripulante son los de su estado, y son los
    # mismos sin el paso de la radiación; las demás hipótesis, también.
    levels = {item["subject"]: item["overall_level"] for item in body["crew"]}
    for subject, level in levels.items():
        status = client.get("/api/status", params={"subject": subject}).json()
        assert status["overall_level"] == level
        assert status["rules_version"] == rules_version()
    monkeypatch.setattr(context, "_radiation_in_window", lambda *_: None)
    without = client.get("/api/crew").json()
    monkeypatch.undo()
    assert without["crew"] == body["crew"]
    others = [item for item in body["correlation"]["hypotheses"] if item["kind"] != SOLAR_KIND]
    assert [item["kind"] for item in without["correlation"]["hypotheses"]] == [
        item["kind"] for item in others
    ]
    # Tierra, con un corte anterior a la primera lectura por encima del límite, no la conoce.
    first = dt.datetime.fromisoformat(dose["first"])
    ground = client.get(
        "/api/crew", params={"until": (first - dt.timedelta(minutes=1)).isoformat()}
    ).json()
    assert _solar(ground) == []
    # Con un corte posterior, solo las lecturas que ya habían llegado.
    cut = first + dt.timedelta(hours=3)
    [later] = _solar(client.get("/api/crew", params={"until": cut.isoformat()}).json())
    assert dt.datetime.fromisoformat(later["radiation"]["dose"]["last"]) <= cut
    assert later["radiation"]["dose"]["readings"] < dose["readings"]


def test_the_crew_view_reads_donki_with_what_its_data_covers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.post("/api/simulate", params={"scenario": "spe-event", "days": 10, "crew_size": 2})
    reference = dt.datetime.fromisoformat(client.get("/api/crew").json()["reference_time"])
    event = _sep(reference - dt.timedelta(hours=5), "SEP-PRUEBA")
    # Lo que el estado trae de DONKI (sin red en las pruebas) y un reloj fijo: los datos, pedidos
    # hace diez minutos, cubren de tres días antes del reloj hasta él.
    monkeypatch.setattr(routes, "_fetch_solar_events", lambda settings: ([event], ("10 min", 600)))
    monkeypatch.setattr(routes, "_now", lambda: reference + dt.timedelta(hours=1))
    [solar] = _solar(client.get("/api/crew").json())
    assert solar["title"] == (
        "Evento de partículas solares registrado en NASA DONKI dentro de la ventana comparada"
    )
    assert solar["radiation"]["donki"]["status"] == "with_data"
    assert [item["event_id"] for item in solar["radiation"]["donki"]["events"]] == ["SEP-PRUEBA"]
    assert (
        "NASA DONKI registra 1 evento de partículas solares en la ventana: SEP-PRUEBA (5,0 h"
        in solar["radiation"]["statement"]
    )
    # La dosimetría sigue en la misma frase: las dos fuentes, juntas (base de conocimiento §2.1).
    assert solar["radiation"]["dose"] is not None
    # Unos datos de DONKI pedidos hace cuatro días no cubren la ventana: no se dice «ninguno».
    monkeypatch.setattr(routes, "_fetch_solar_events", lambda settings: ([], ("4 d", 4 * 86400)))
    [solar] = _solar(client.get("/api/crew").json())
    assert solar["radiation"]["donki"]["status"] == "no_data"
    assert "Sin datos de NASA DONKI que cubran la ventana" in solar["radiation"]["statement"]
