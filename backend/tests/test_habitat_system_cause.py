"""Un sistema de soporte vital declarado degradado, como causa común candidata (§5.34.4).

La base de conocimiento del equipo (§6) pone el estado del soporte vital y del control térmico
como «causa común potencial de cambios en varios tripulantes». Estas pruebas fijan lo que eso
significa en `context.correlate`, y lo que no puede pasar:

- sin ninguna declaración de un sistema de soporte vital fuera de lo nominal que toque la
  ventana, la salida es la de antes clave por clave (el mismo fichero de la prueba de no
  regresión de la ubicación);
- con una, entra como «coincidencia temporal, no causa», detrás de las excursiones medidas y
  delante de la causa sin identificar, y dice que ninguna fuente leída la relaciona con nadie;
- solo con dos o más afectados, como toda causa compartida;
- no mueve niveles, afectados ni excursiones (invariante 5);
- una declaración de un módulo se juzga con la ubicación declarada, como una excursión.
"""

import datetime as dt
import json
from typing import Any

from fastapi.testclient import TestClient

from app.analysis.context import (
    COINCIDENCE_LABEL,
    SYSTEM_CHECKS,
    SYSTEM_KIND,
    SYSTEM_NOT_COMPARABLE,
    SYSTEM_NOTE,
    UNIDENTIFIED_WITH_SYSTEM,
    Stay,
    annotate,
    correlate,
)
from app.environment import systems
from app.text_guard import check
from tests.test_habitat import GOLDEN, T0, WINDOW, _excursion_in, _golden_cases, _slim

AIR = "air-revitalization"
LABEL = "declarado por una persona, no telemetría"
TWO = {"crew-01": "watch", "crew-02": "watch"}


def _said(
    system: str, state: str, at: dt.datetime, index: int, module: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Una declaración tal y como la entrega el almacén (`store.system_statuses`)."""
    item: dict[str, Any] = {
        "system": system, "state": state, "at": at.isoformat(), "note": note,
        "declared_by": "CDR", "ledger_index": index, "recorded": at.isoformat(),
    }
    if module is not None:
        item["module"] = module
    return item


def _hours(value: float) -> dt.datetime:
    return T0 - dt.timedelta(hours=value)


def test_the_life_support_systems_are_the_ones_the_eclss_brief_names() -> None:
    life = {key for key, item in systems.SYSTEMS.items() if item.life_support}
    assert life == {
        "air-revitalization", "pressure-control", "thermal-control", "contaminant-control",
        "water",
    }
    off = {key for key, item in systems.STATES.items() if item.off_nominal}
    assert off == {"degraded", "out-of-service"}
    basis = systems.VOCABULARY.life_support_basis
    for said in ("OCHMO-TB-002 Rev B", "2026-10-21", "provides clean air and water to crew",
                 "no dice qué efecto tiene en las personas"):
        assert said in basis
    # Nada de esto sale por la ruta del estado de los sistemas: su salida no cambia.
    assert "life_support" not in systems.SYSTEMS[AIR].to_dict()
    assert "off_nominal" not in systems.STATES["degraded"].to_dict()


def test_without_an_off_nominal_life_support_system_the_output_is_the_one_from_before() -> None:
    # No regresión: el fichero es el de la prueba de la ubicación, generado antes de que
    # existieran los sistemas declarados. Nada de esto toca la ventana con un sistema de
    # soporte vital fuera de lo nominal, y la salida tiene que ser esa clave por clave.
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for declarations in (
        None,
        [],
        [_said(AIR, "nominal", _hours(5), 1)],
        # Degradado y vuelto a nominal antes de la ventana de 48 h.
        [_said(AIR, "degraded", _hours(100), 1), _said(AIR, "nominal", _hours(60), 2)],
        # Sistemas que no son de soporte vital.
        [_said("communications", "out-of-service", _hours(5), 1),
         _said("lighting", "degraded", _hours(5), 2), _said("power", "degraded", _hours(5), 3)],
        # Declarado para un instante posterior al comparado.
        [_said(AIR, "degraded", T0 + dt.timedelta(hours=1), 1)],
        # Corregido después con un instante anterior: el tramo degradado no existe.
        [_said(AIR, "degraded", _hours(5), 1), _said(AIR, "nominal", _hours(6), 2)],
        # Un sistema que ya no está en el vocabulario.
        [_said("propulsion", "degraded", _hours(5), 1)],
    ):
        got = {
            name: _slim(correlate(levels, found, T0, WINDOW, None, declarations))
            for name, (levels, found) in _golden_cases().items()
        }
        assert json.loads(json.dumps(got)) == golden, declarations


def test_a_degraded_life_support_system_enters_as_a_coincidence_not_as_a_cause() -> None:
    told = [_said(AIR, "degraded", _hours(10), 7, note="el lecho 2 no regenera")]
    result = correlate(TWO, [], T0, WINDOW, None, told)
    kinds = [item["kind"] for item in result["hypotheses"]]
    assert kinds == [SYSTEM_KIND, "shared_unknown"]
    first, unknown = result["hypotheses"]
    assert first["label"] == COINCIDENCE_LABEL == "coincidencia temporal, no causa"
    assert first["title"] == (
        "Sistema Revitalización de aire declarado «degradado» dentro de la ventana comparada"
    )
    assert first["affected"] == ["crew-01", "crew-02"] and first["excursion"] is None
    assert first["checks"] == list(SYSTEM_CHECKS)
    assert first["system"]["statement"] == (
        "Declarado «degradado» desde 10,0 h antes del instante comparado, y es lo último "
        f"declarado; lo declaró CDR (asiento 7): {LABEL}."
    )
    assert (first["system"]["key"], first["system"]["note"]) == (AIR, "el lecho 2 no regenera")
    # La cita es del resumen técnico del ECLSS y dice para qué se cita, y para qué no.
    [cited] = first["evidence"]
    assert cited["id"] == "ochmo-tb-002"
    assert "no dice qué efecto tiene en las personas" in cited["relevance"]
    # «Sin causa ambiental registrada» sería falso con un sistema declarado: no se dice.
    assert unknown["title"] == UNIDENTIFIED_WITH_SYSTEM
    assert "sin causa ambiental registrada" not in json.dumps(result, ensure_ascii=False)
    # Lo que la interfaz pinta: la nota de que no hay fuente que lo relacione, y el flujo.
    annotate(first)
    assert first["knowledge_note"] == SYSTEM_NOTE
    assert "no una causa" in SYSTEM_NOTE and "ninguna fuente leída" in SYSTEM_NOTE
    steps = {step["key"]: step for step in first["flow"]}
    assert first["system"]["statement"] in steps["correlate"]["detail"]
    assert "ninguna fuente leída dice que lo explique" in steps["correlate"]["detail"]
    assert steps["human_confirmation"]["state"] == "not_applicable"
    # La evidencia dice para qué se cita la ficha, sin repetir la nota.
    assert steps["evidence"]["detail"] == (
        "1 fuente citada: qué funciones forman el soporte vital, no qué efecto tiene en las "
        "personas que falle un sistema."
    )


def test_the_measured_excursion_goes_first_and_one_crew_member_alone_gets_no_system() -> None:
    told = [_said("thermal-control", "out-of-service", _hours(30), 3)]
    co2 = _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
    result = correlate(TWO, co2, T0, WINDOW, None, told)
    assert [item["kind"] for item in result["hypotheses"]] == [
        "shared_environment", SYSTEM_KIND,
    ]
    assert "«fuera de servicio»" in result["hypotheses"][1]["title"]
    alone = correlate({"crew-01": "watch", "crew-02": "nominal"}, [], T0, WINDOW, None, told)
    assert [item["kind"] for item in alone["hypotheses"]] == ["individual"]


def test_a_declared_system_moves_no_level_affected_or_excursion() -> None:
    levels = {"crew-01": "concern", "crew-02": "watch", "crew-03": "nominal"}
    co2 = _excursion_in("habitat-principal", "cabin-ppco2", 5.0, T0)
    before = correlate(dict(levels), co2, T0, WINDOW)
    given = dict(levels)
    after = correlate(given, co2, T0, WINDOW, None, [_said(AIR, "degraded", _hours(2), 1)])
    assert given == levels
    for key in ("affected", "habitat_excursions", "window_hours", "assumption"):
        assert after[key] == before[key]
    # Lo de antes sigue entero y en su sitio; lo nuevo va detrás.
    assert after["hypotheses"][: len(before["hypotheses"])] == before["hypotheses"]
    assert [item["kind"] for item in after["hypotheses"][len(before["hypotheses"]):]] == [
        SYSTEM_KIND,
    ]


def test_a_system_that_recovered_inside_the_window_counts_and_says_until_when() -> None:
    told = [_said(AIR, "degraded", _hours(20), 1), _said(AIR, "nominal", _hours(4), 2)]
    [first, _] = correlate(TWO, [], T0, WINDOW, None, told)["hypotheses"]
    assert "desde 20,0 h antes del instante comparado, hasta 4,0 h antes" in (
        first["system"]["statement"]
    )
    # Varias declaraciones seguidas del mismo estado son un solo tramo, desde la primera.
    told = [_said(AIR, "degraded", _hours(20), 1), _said(AIR, "degraded", _hours(3), 2)]
    [first, _] = correlate(TWO, [], T0, WINDOW, None, told)["hypotheses"]
    assert "desde 20,0 h antes" in first["system"]["statement"]
    assert "(asientos 1 a 2)" in first["system"]["statement"]
    # Uno por sistema y módulo: el último tramo fuera de lo nominal que toca la ventana.
    told = [_said(AIR, "degraded", _hours(20), 1), _said(AIR, "out-of-service", _hours(5), 2)]
    hypotheses = correlate(TWO, [], T0, WINDOW, None, told)["hypotheses"]
    assert [item["kind"] for item in hypotheses] == [SYSTEM_KIND, "shared_unknown"]
    assert hypotheses[0]["system"]["state"] == "out-of-service"


def test_who_declared_and_the_note_are_those_signed_up_to_the_compared_instant() -> None:
    # Abre el tramo CDR sin nota; FE lo confirma con una nota; y una confirmación firmada para
    # después del instante comparado no presta ni su asiento ni su nota.
    later = {**_said(AIR, "degraded", T0 + dt.timedelta(hours=3), 9, note="ya no regenera"),
             "declared_by": "MS"}
    told = [
        _said(AIR, "degraded", _hours(20), 3),
        {**_said(AIR, "degraded", _hours(6), 5, note="lecho 2 sin regenerar"), "declared_by": "FE"},
        later,
    ]
    [first, _] = correlate(TWO, [], T0, WINDOW, None, told)["hypotheses"]
    system = first["system"]
    assert system["statement"] == (
        "Declarado «degradado» desde 20,0 h antes del instante comparado, y es lo último "
        f"declarado; lo declararon CDR y FE (asientos 3 a 5): {LABEL}."
    )
    assert (system["note"], system["note_by"]) == ("lecho 2 sin regenerar", "FE")
    assert system["declared_by"] == ["CDR", "FE"]
    assert (system["ledger_index"], system["last_ledger_index"]) == (3, 5)
    # Sin ninguna nota en lo firmado hasta el instante, no hay nota.
    [first, _] = correlate(TWO, [], T0, WINDOW, None, [told[0], later])["hypotheses"]
    assert (first["system"]["note"], first["system"]["note_by"]) == (None, None)
    assert "(asiento 3)" in first["system"]["statement"]


def test_a_module_declaration_is_judged_with_the_declared_location() -> None:
    told = [_said(AIR, "degraded", _hours(10), 4, module="laboratorio")]
    span = (T0 - dt.timedelta(days=3), T0 + dt.timedelta(days=1))
    away = [Stay("habitat-principal", *span, 1)]
    result = correlate(TWO, [], T0, WINDOW, {"crew-01": away, "crew-02": away}, told)
    assert [item["kind"] for item in result["hypotheses"]] == ["shared_unknown", SYSTEM_KIND]
    last = result["hypotheses"][1]
    assert last["title"].startswith("Sistema Revitalización de aire en Laboratorio declarado")
    assert last["likelihood"] == "less_likely"
    assert "no estaban en Laboratorio durante el tramo declarado" in last["likelihood_reason"]
    assert last["location"]["elsewhere"] == ["crew-01", "crew-02"]
    # Allí estaban: sigue la primera.
    there = [Stay("laboratorio", *span, 1)]
    result = correlate(TWO, [], T0, WINDOW, {"crew-01": there, "crew-02": there}, told)
    assert result["hypotheses"][0]["kind"] == SYSTEM_KIND
    assert result["hypotheses"][0]["likelihood"] == "primary"
    # Una declaración del sistema entero no está en ningún módulo: ninguna ubicación la baja.
    whole = [_said(AIR, "degraded", _hours(10), 4)]
    result = correlate(TWO, [], T0, WINDOW, {"crew-01": away, "crew-02": away}, whole)
    first = result["hypotheses"][0]
    assert (first["kind"], first["likelihood"], first["likelihood_reason"]) == (
        SYSTEM_KIND, "primary", None,
    )
    assert "location" not in first


def test_every_new_text_passes_the_guard() -> None:
    texts = [SYSTEM_NOTE, SYSTEM_NOT_COMPARABLE, UNIDENTIFIED_WITH_SYSTEM, *SYSTEM_CHECKS,
             systems.VOCABULARY.life_support_basis]
    span = (T0 - dt.timedelta(days=3), T0 + dt.timedelta(days=1))
    away = [Stay("habitat-principal", *span, 1)]
    for told, locations in (
        ([_said(AIR, "degraded", _hours(10), 1)], None),
        ([_said("water", "out-of-service", _hours(30), 1), _said("water", "nominal", _hours(2), 2)],
         None),
        ([_said(AIR, "degraded", _hours(10), 1, module="laboratorio")],
         {"crew-01": away, "crew-02": away}),
    ):
        for item in correlate(TWO, [], T0, WINDOW, locations, told)["hypotheses"]:
            annotate(item)
            texts += [item["title"], *item["checks"], item.get("likelihood_reason") or "",
                      item.get("knowledge_note") or "",
                      *(step["detail"] for step in item["flow"])]
            if "system" in item:
                texts.append(item["system"]["statement"])
    assert [(t, check(t)) for t in texts if t and check(t)] == []


def test_the_crew_view_reads_the_signed_declarations_and_ground_only_what_it_can_know(
    client: TestClient,
) -> None:
    client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 10})
    before = client.get("/api/crew").json()
    reference = dt.datetime.fromisoformat(before["reference_time"])
    at = reference - dt.timedelta(hours=6)
    response = client.post("/api/habitat/systems/status", json={
        "system": "thermal-control", "state": "degraded", "at": at.isoformat(),
        "declared_by": "CDR",
    })
    assert response.status_code == 201
    after = client.get("/api/crew").json()
    # Invariante 5: los niveles de cada tripulante son los mismos.
    assert after["crew"] == before["crew"]
    kinds = [item["kind"] for item in after["correlation"]["hypotheses"]]
    assert kinds.count(SYSTEM_KIND) == 1 and kinds[0] == "shared_environment"
    [added] = [item for item in after["correlation"]["hypotheses"] if item["kind"] == SYSTEM_KIND]
    assert added["system"]["key"] == "thermal-control"
    assert added["review"] is None
    assert added["knowledge_note"] == SYSTEM_NOTE
    assert [step["key"] for step in added["flow"]][0] == "detect"
    # Tierra, con un corte anterior a la declaración, no la conoce.
    ground = client.get(
        "/api/crew", params={"until": (at - dt.timedelta(minutes=1)).isoformat()}
    ).json()
    assert SYSTEM_KIND not in [item["kind"] for item in ground["correlation"]["hypotheses"]]
