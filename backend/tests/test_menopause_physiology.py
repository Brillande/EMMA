"""La menopausia y la perimenopausia, leídas: cada cifra con su frase y cada clase con su regla.

Es lo que leerán la línea base (para no ajustar por fase a quien no tiene ciclo regular) y el
simulador (sofocos como picos breves) cuando se decida. Si una cifra se pudiera escribir sin
frase, o un tema sin el respaldo que dice tener, ese ajuste taparía con una cifra inventada una
subida real o fabricaría una falsa alarma: estas pruebas lo impiden. Y lo que no se sabe en vuelo
se dice como tal, con lo buscado.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest

from app.evidence import cycle_physiology, registry
from app.evidence import menopause_physiology as mp
from app.ingest.codes import CATALOG
from app.ingest.simulator import EVIDENCE_CLASSES

RAW: dict[str, Any] = json.loads(mp.READ_PATH.read_text(encoding="utf-8"))


def _raw() -> dict[str, Any]:
    return copy.deepcopy(RAW)


def _finding(raw: dict[str, Any], finding_id: str) -> dict[str, Any]:
    return next(item for item in raw["findings"] if item["id"] == finding_id)


def test_the_file_validates_and_covers_the_three_subjects() -> None:
    mp.read()
    subjects = {mp.topic(key).subject for key in mp.topic_keys()}
    assert subjects == set(mp.SUBJECTS)


def test_the_vocabulary_is_the_simulator_one_and_the_cycle_one() -> None:
    assert set(mp.EVIDENCE) <= set(EVIDENCE_CLASSES)
    assert mp.EVIDENCE == cycle_physiology.EVIDENCE


def test_every_reference_exists_and_is_cited() -> None:
    assert mp.cited_refs() <= set(registry.registry())
    used = {item["ref"] for item in RAW["findings"]} | set(RAW["in_flight"]["searched_refs"])
    for entry in RAW["topics"].values():
        used.update(entry.get("searched_refs", ()))
    assert used == set(RAW["sources"])


def test_every_quote_contains_its_literal() -> None:
    for item in RAW["findings"]:
        assert item["literal"] in item["quote"], item["id"]


def test_an_indicator_is_in_the_catalog_and_its_unit_is_the_catalog_one() -> None:
    for row in mp.table():
        if row["indicator"] is not None:
            assert row["unit"] == CATALOG[row["indicator"]].unit, row["key"]
        else:
            assert RAW["topics"][row["key"]]["why_no_indicator"], row["key"]


def test_an_established_topic_has_its_figure_and_the_others_have_none() -> None:
    for row in mp.table():
        if row["evidence"] == "established":
            assert row["low"] is not None and row["high"] is not None
            assert row["low"] <= row["high"]
        else:
            assert row["low"] is None and row["high"] is None, row
        assert row["refs"], row


def test_what_was_read_is_what_is_served() -> None:
    """Las cifras de lo leído el 2026-11-15 (si cambian, es otra lectura)."""
    heart = mp.topic("hot-flash-heart-rate")
    assert (heart.evidence, heart.direction, heart.low, heart.high, heart.indicator) == (
        "established", "rises", 9, 20, "heart-rate",
    )
    core = mp.topic("hot-flash-core-temperature")
    assert (core.direction, core.low, core.high) == ("falls", -0.6, -0.2)
    # Lo que no va en el sentido del tema también se cita.
    assert "sievert-2013-hot-flash-measures" in core.refs
    duration = mp.topic("hot-flash-episode-duration")
    assert (duration.kind, duration.direction, duration.low, duration.high, duration.unit) == (
        "figure", None, 1.3, 6.5, "min",
    )
    assert mp.topic("hot-flash-frequency").evidence == "unsupported"
    assert mp.topic("perimenopause-irregular-cycle-physiology").evidence == "unsupported"
    flight = mp.topic("flight-bone-loss-rate")
    assert (flight.low, flight.high, flight.unit) == (1, 1.5, "%/mo")
    assert mp.topic("flight-vs-menopause-bone").low == 10


def test_in_flight_nothing_about_menopause_was_measured_and_it_says_so() -> None:
    flight = mp.in_flight()
    assert flight["evidence"] == "unsupported"
    assert "En vuelo no se ha medido nada de la menopausia" in flight["text"]
    refs = {item["ref"] for item in flight["found"]}
    assert {"hughes-fulford-2024-women-in-space", "smith-2014-bone-sex-iss"} <= refs
    for item in flight["found"]:
        assert item["url"], item["id"]
    assert "NTRS" in flight["searched"]


def test_a_topic_that_was_not_read_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        mp.topic("hot-flash-blood-pressure")


def _invent_figure(raw: dict[str, Any]) -> None:
    _finding(raw, "low-hr-during")["magnitude"]["high"] = 12


def _standard_deviation_as_figure(raw: dict[str, Any]) -> None:
    """«0.03 ± 0.12C»: la desviación típica está en la frase, pero no en el trozo de la cifra."""
    _finding(raw, "jones-core-before")["magnitude"].update(low=0.12, high=0.12)
    raw["topics"]["hot-flash-core-temperature-before"].update(low=0.12, high=0.12)


def _integer_part_of_a_decimal(raw: dict[str, Any]) -> None:
    """El 3 de «3.9» no es un 3 escrito."""
    _finding(raw, "kronenberg-finger-during")["magnitude"].update(low=3, high=3.9)
    raw["topics"]["hot-flash-skin-temperature"]["low"] = 3


def _figure_text_not_in_quote(raw: dict[str, Any]) -> None:
    _finding(raw, "low-duration")["magnitude"]["text"] = "range, 1.3-9.5 min"


def _figure_without_text(raw: dict[str, Any]) -> None:
    del _finding(raw, "low-duration")["magnitude"]["text"]


def _searched_refs_on_supported_topic(raw: dict[str, Any]) -> None:
    """Una ficha citada solo en `searched_refs` de un tema con respaldo contaría como leída."""
    raw["sources"]["mmash"] = {"extent": "partial", "what": "x"}
    raw["topics"]["hot-flash-heart-rate"]["searched_refs"] = ["mmash"]


def _envelope_changed(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-heart-rate"]["high"] = 25


def _flip_sign(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-core-temperature"]["direction"] = "rises"


def _figure_sign_against_direction(raw: dict[str, Any]) -> None:
    _finding(raw, "kronenberg-core-during")["magnitude"].update(low=0.2, high=0.6)


def _literal_against(raw: dict[str, Any]) -> None:
    _finding(raw, "thurston-rsa-during")["direction"] = "rises"


def _literal_both_ways(raw: dict[str, Any]) -> None:
    item = _finding(raw, "kronenberg-finger-during")
    item["literal"] = (
        "finger temperature increased an average of 3.9 degrees C and esophageal temperature fell"
    )


def _literal_not_in_quote(raw: dict[str, Any]) -> None:
    _finding(raw, "jones-core-before")["literal"] = "core temperature increased by 0.3"


def _derived_figure(raw: dict[str, Any]) -> None:
    """Aquí no hay restas: una cifra con `derived_from` no pasa."""
    _finding(raw, "greendale-spine")["magnitude"]["derived_from"] = [[10.6, 3.22]]


def _unknown_unit(raw: dict[str, Any]) -> None:
    _finding(raw, "low-duration")["magnitude"]["unit"] = "s"


def _figure_in_other_unit(raw: dict[str, Any]) -> None:
    """Una tasa mensual no es la cifra de una pérdida acumulada en tres años."""
    entry = raw["topics"]["menopause-bone-loss"]
    entry["findings"].append("hrp-flight-rate")
    entry["magnitude_findings"].append("hrp-flight-rate")


def _indicator_unit_mismatch(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-heart-rate"]["unit"] = "ms"


def _skin_as_body_temperature(raw: dict[str, Any]) -> None:
    """La piel del dedo no es la temperatura corporal del catálogo: sin decirlo, falla."""
    del raw["topics"]["hot-flash-skin-temperature"]["why_no_indicator"]


def _unknown_indicator(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-heart-rate"]["indicator"] = "skin-temperature"


def _unknown_related(raw: dict[str, Any]) -> None:
    raw["topics"]["menopause-bone-loss"]["related"] = ["bone-loss-rate"]


def _figure_with_direction(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-episode-duration"]["direction"] = "rises"


def _figure_contested(raw: dict[str, Any]) -> None:
    raw["topics"]["menopause-bone-loss"].update(evidence="contested")


def _direction_with_figure(raw: dict[str, Any]) -> None:
    entry = raw["topics"]["hot-flash-vagal-hrv"]
    entry["low"] = -5.0


def _unsupported_with_findings(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-frequency"]["findings"] = ["low-duration"]


def _unsupported_without_refs(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-frequency"]["searched_refs"] = []


def _unsupported_with_figure(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-frequency"]["low"] = 5


def _contested_one_source(raw: dict[str, Any]) -> None:
    entry = raw["topics"]["hot-flash-core-temperature"]
    entry.update(evidence="contested", direction="contested", low=None, high=None,
                 magnitude_findings=[],
                 findings=["kronenberg-core-during", "kronenberg-finger-during"])
    entry.pop("dissent")
    entry.pop("dissent_note")


def _dissent_hidden(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-core-temperature"].pop("dissent_note")


def _dissent_same_direction(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-core-temperature"]["dissent"] = ["thurston-rsa-during"]


def _change_without_direction_row(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-heart-rate"]["findings"].append("low-duration")


def _flight_claims_support(raw: dict[str, Any]) -> None:
    """Si un día se mide algo en vuelo, será un tema con su clase, no este bloque."""
    raw["in_flight"]["evidence"] = "direction_only"


def _flight_without_search(raw: dict[str, Any]) -> None:
    del raw["in_flight"]["searched"]


def _flight_without_findings(raw: dict[str, Any]) -> None:
    raw["in_flight"]["found"] = []


def _animal_journal_source(raw: dict[str, Any]) -> None:
    _finding(raw, "jones-core-before")["ref"] = "thiel-2017-macrophage-microgravity"
    raw["sources"]["thiel-2017-macrophage-microgravity"] = {"extent": "partial", "what": "x"}


def _idle_source(raw: dict[str, Any]) -> None:
    raw["sources"]["mmash"] = {"extent": "partial", "what": "x"}


def _unused_finding(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-heart-rate"]["findings"].remove("sievert-objective-hr")


def _duplicate_id(raw: dict[str, Any]) -> None:
    raw["findings"].append(copy.deepcopy(_finding(raw, "low-duration")))


def _no_date(raw: dict[str, Any]) -> None:
    raw["read_on"] = "15/11/2026"


def _unknown_subject(raw: dict[str, Any]) -> None:
    raw["topics"]["hot-flash-heart-rate"]["subject"] = "radiation"


@pytest.mark.parametrize(("mutate", "reason"), [
    (_invent_figure, "no está escrito en su frase"),
    (_standard_deviation_as_figure, "no está escrito en su frase"),
    (_integer_part_of_a_decimal, "no está escrito en su frase"),
    (_figure_text_not_in_quote, "sin el trozo de su frase"),
    (_figure_without_text, "sin el trozo de su frase"),
    (_searched_refs_on_supported_topic, "solo en esa clase"),
    (_envelope_changed, "no es la de sus frases"),
    (_flip_sign, "no dicen todas"),
    (_figure_sign_against_direction, "el signo de la cifra"),
    (_literal_against, "el literal no dice"),
    (_literal_both_ways, "el literal dice también"),
    (_literal_not_in_quote, "no está escrito en su frase"),
    (_derived_figure, "sin más"),
    (_unknown_unit, "unidad desconocida"),
    (_figure_in_other_unit, "no está en %"),
    (_indicator_unit_mismatch, "no está en /min"),
    (_skin_as_body_temperature, "sin decir por qué"),
    (_unknown_indicator, "no es un indicador del catálogo"),
    (_unknown_related, "`related`"),
    (_figure_with_direction, "una cifra no tiene sentido"),
    (_figure_contested, "no es «discutida»"),
    (_direction_with_figure, "no lleva cifra"),
    (_unsupported_with_findings, "con frases leídas"),
    (_unsupported_without_refs, "sin sus fichas"),
    (_unsupported_with_figure, "con cifra"),
    (_contested_one_source, "de dos fuentes o más"),
    (_dissent_hidden, "disenso sin decir"),
    (_dissent_same_direction, "en el sentido del tema"),
    (_change_without_direction_row, "frase sin sentido"),
    (_flight_claims_support, "buscado y no encontrado"),
    (_flight_without_search, "sin decir qué se buscó"),
    (_flight_without_findings, "sin las frases leídas"),
    (_animal_journal_source, "solo en personas"),
    (_idle_source, "ninguna frase ni búsqueda"),
    (_unused_finding, "ningún tema usa"),
    (_duplicate_id, "identificador repetido"),
    (_no_date, "read_on"),
    (_unknown_subject, "desconocido"),
])
def test_the_loader_rejects_what_breaks_its_contract(
    mutate: Callable[[dict[str, Any]], None], reason: str,
) -> None:
    raw = _raw()
    mutate(raw)
    with pytest.raises(mp.MenopausePhysiologyError, match=reason):
        mp.validate(raw)


def test_a_contested_change_with_two_sources_that_disagree_is_accepted() -> None:
    raw = _raw()
    entry = raw["topics"]["hot-flash-core-temperature"]
    entry.update(evidence="contested", direction="contested", low=None, high=None,
                 magnitude_findings=[], findings=[*entry["findings"], *entry.pop("dissent")])
    entry.pop("dissent_note")
    mp.validate(raw)


def test_a_nasa_document_that_is_not_only_human_is_accepted_and_a_journal_is_not() -> None:
    """El informe del HRP junta astronautas y roedores; un artículo de revista no puede."""
    assert registry.get("hrp-bone-fracture-evidence-report").population == "human_and_animal"
    mp.validate(_raw())
