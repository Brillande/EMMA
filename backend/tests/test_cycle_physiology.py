"""La variación por fase del ciclo, leída: cada cifra con su frase y cada clase con su regla.

Es lo que leerán la línea base consciente de la fase y el simulador (lote ciclo). Si una cifra se
pudiera escribir sin frase, o una clase sin el respaldo que dice tener, ese ajuste taparía con una
cifra inventada una subida real o una falsa alarma: estas pruebas lo impiden.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest

from app.evidence import cycle_physiology as cp
from app.evidence import registry
from app.ingest.codes import CATALOG
from app.ingest.simulator import EVIDENCE_CLASSES

RAW: dict[str, Any] = json.loads(cp.READ_PATH.read_text(encoding="utf-8"))
KEYS = ("body-temperature", "heart-rate", "hrv-rmssd", "hrv-sdnn")


def _raw() -> dict[str, Any]:
    return copy.deepcopy(RAW)


def _finding(raw: dict[str, Any], finding_id: str) -> dict[str, Any]:
    return next(item for item in raw["findings"] if item["id"] == finding_id)


def test_the_file_validates_and_covers_the_four_indicators() -> None:
    cp.read()
    assert set(KEYS) <= set(cp.keys())
    for key in KEYS:
        assert key in CATALOG
        for phase in ("luteal", "menstrual"):
            assert cp.amplitude(key, phase).evidence in cp.EVIDENCE


def test_the_vocabulary_is_the_simulator_one() -> None:
    assert set(cp.EVIDENCE) <= set(EVIDENCE_CLASSES)


def test_every_reference_exists_is_human_and_is_cited() -> None:
    known = set(registry.registry())
    assert cp.cited_refs() <= known
    for ref_id in cp.cited_refs():
        assert registry.get(ref_id).population == "human", ref_id
    used = {item["ref"] for item in RAW["findings"]} | {RAW["suppression"]["ref"]}
    for phases in RAW["indicators"].values():
        for entry in phases.values():
            used.update(entry.get("searched_refs", ()))
    assert used == set(RAW["sources"])


def test_every_quote_contains_its_literal() -> None:
    for item in RAW["findings"]:
        assert item["literal"] in item["quote"], item["id"]


def test_the_reference_phase_is_zero_by_definition() -> None:
    found = cp.amplitude("body-temperature", "follicular")
    assert (found.low, found.high, found.evidence, found.refs) == (0.0, 0.0, cp.REFERENCE, ())


def test_an_established_amplitude_has_its_figure_and_the_others_have_none() -> None:
    for row in cp.table():
        if row["evidence"] == "established":
            assert row["low"] is not None and row["high"] is not None
            assert row["low"] <= row["high"]
            sign = 1 if row["direction"] == "rises" else -1
            assert row["low"] * sign > 0 and row["high"] * sign > 0
        else:
            assert row["low"] is None and row["high"] is None, row
        assert row["refs"], row


def test_what_was_read_is_what_is_served() -> None:
    """Las cifras de lo leído el 2026-11-14 (si cambian, es otra lectura)."""
    temperature = cp.amplitude("body-temperature", "luteal")
    assert (temperature.evidence, temperature.low, temperature.high) == ("established", 0.23, 0.7)
    assert "baker-2020-temperature-menstrual-review" in temperature.refs
    heart = cp.amplitude("heart-rate", "luteal")
    assert (heart.evidence, heart.direction, heart.low, heart.high) == (
        "established", "rises", 3.42, 3.91,
    )
    rmssd = cp.amplitude("hrv-rmssd", "luteal")
    assert (rmssd.evidence, rmssd.direction) == ("direction_only", "falls")
    assert "schmalenberger-2019-vagal-menstrual-meta" in rmssd.refs
    # Lo que no va en el sentido de la fila también se cita.
    assert "yazar-2016-hrv-menstrual-phase" in rmssd.refs
    assert cp.amplitude("hrv-sdnn", "menstrual").evidence == "unsupported"


def test_an_indicator_that_was_not_searched_is_not_unsupported() -> None:
    with pytest.raises(KeyError):
        cp.amplitude("oxygen-saturation", "luteal")
    with pytest.raises(ValueError):
        cp.amplitude("heart-rate", "ovulatory")


def test_suppression_is_cited_with_its_sentence() -> None:
    item = cp.suppression()
    assert item["ref"] == "jain-2016-amenorrhea-astronauts"
    assert "28725726" in item["source"]
    assert "amenorrhea" in item["quote"]


def _drop_figure(raw: dict[str, Any]) -> None:
    raw["indicators"]["heart-rate"]["luteal"]["low"] = 9.0


def _invent_figure(raw: dict[str, Any]) -> None:
    _finding(raw, "baker-core-luteal")["magnitude"]["high"] = 0.9
    raw["indicators"]["body-temperature"]["luteal"]["high"] = 0.9


def _wrong_derivation(raw: dict[str, Any]) -> None:
    _finding(raw, "goodale-hr-luteal")["magnitude"]["derived_from"] = [[59.98, 50.13]]


def _integer_part_of_a_luteal_decimal(raw: dict[str, Any]) -> None:
    """El 59 de «59.98» no es un 59 escrito (B3, 2026-11-15; el mismo arreglo que C1)."""
    figure = _finding(raw, "goodale-hr-luteal")["magnitude"]
    figure["derived_from"] = [[59, 56.56], [60.47, 56.56]]
    figure["low"] = 2.44
    raw["indicators"]["heart-rate"]["luteal"]["low"] = 2.44


def _rounded_derivation(raw: dict[str, Any]) -> None:
    _finding(raw, "goodale-hr-luteal")["magnitude"]["low"] = 3.5
    raw["indicators"]["heart-rate"]["luteal"]["low"] = 3.5


def _sdnn_figure_for_rmssd(raw: dict[str, Any]) -> None:
    """Una SDNN de 24 h (ms) no da la cifra de la RMSSD (ms): la frase misma dice que no cambió."""
    entry = raw["indicators"]["hrv-rmssd"]["luteal"]
    entry.update(evidence="established", low=-18.0, high=-18.0,
                 findings=[*entry["findings"], "yazar-sdnn-luteal"],
                 magnitude_findings=["yazar-sdnn-luteal"])


def _menses_mean_as_follicular(raw: dict[str, Any]) -> None:
    """La lútea menos la menstruación, servida como lútea menos la folicular."""
    figure = _finding(raw, "goodale-hr-luteal")["magnitude"]
    figure.update(low=2.06, high=2.55, derived_from=[[59.98, 57.92], [60.47, 57.92]])
    raw["indicators"]["heart-rate"]["luteal"].update(low=2.06, high=2.55)


def _written_figure_relabelled(raw: dict[str, Any]) -> None:
    """La piel frente a la ventana fértil, rebautizada «frente a la folicular»."""
    item = _finding(raw, "shilaih-wrist-luteal")
    item["magnitude"] = {"key": "body-temperature", "low": 0.33, "high": 0.33, "unit": "Cel",
                         "compared_with": "follicular"}


def _integer_part_of_a_decimal(raw: dict[str, Any]) -> None:
    """El 57 de «57.92» no es un 57 escrito (la resta cuadra; la cifra no está en la frase)."""
    _finding(raw, "goodale-hr-menses")["magnitude"].update(
        low=0.44, high=0.44, derived_from=[[57, 56.56]]
    )
    raw["indicators"]["heart-rate"]["menstrual"].update(low=0.44, high=0.44)


def _reference_from_other_sentence(raw: dict[str, Any]) -> None:
    _finding(raw, "goodale-hr-luteal")["magnitude"]["reference_from"] = "goodale-wrist-menses"


def _dissent_on_unsupported(raw: dict[str, Any]) -> None:
    raw["indicators"]["hrv-sdnn"]["menstrual"]["dissent"] = ["nope"]


def _phase_not_named(raw: dict[str, Any]) -> None:
    del _finding(raw, "tenan-hr-cycle")["phase_note"]


def _bad_evidence_type(raw: dict[str, Any]) -> None:
    raw["indicators"]["hrv-sdnn"]["luteal"]["evidence"] = ["established"]


def _flip_sign(raw: dict[str, Any]) -> None:
    raw["indicators"]["hrv-rmssd"]["luteal"]["direction"] = "rises"


def _literal_against(raw: dict[str, Any]) -> None:
    _finding(raw, "maijala-oral-luteal")["direction"] = "falls"


def _literal_not_in_quote(raw: dict[str, Any]) -> None:
    _finding(raw, "baker-core-luteal")["literal"] = "0.5°C higher"


def _contested_one_source(raw: dict[str, Any]) -> None:
    entry = raw["indicators"]["hrv-rmssd"]["luteal"]
    # Dos sentidos, pero de la misma revisión.
    entry.update(evidence="contested", direction="contested",
                 findings=["dejager-timedomain-luteal", "dejager-rmssd-null"])
    entry.pop("dissent")
    entry.pop("dissent_note")


def _contested_one_direction(raw: dict[str, Any]) -> None:
    entry = raw["indicators"]["hrv-rmssd"]["luteal"]
    entry.update(evidence="contested", direction="contested")
    entry.pop("dissent")
    entry.pop("dissent_note")


def _dissent_hidden(raw: dict[str, Any]) -> None:
    raw["indicators"]["hrv-rmssd"]["luteal"].pop("dissent_note")


def _direction_with_figure(raw: dict[str, Any]) -> None:
    raw["indicators"]["hrv-sdnn"]["luteal"]["magnitude_findings"] = ["yazar-sdnn-luteal"]


def _skin_as_magnitude(raw: dict[str, Any]) -> None:
    entry = raw["indicators"]["body-temperature"]["luteal"]
    entry["magnitude_findings"] = ["baker-core-luteal", "shilaih-wrist-luteal"]


def _unsupported_without_refs(raw: dict[str, Any]) -> None:
    raw["indicators"]["hrv-sdnn"]["menstrual"]["searched_refs"] = []


def _animal_source(raw: dict[str, Any]) -> None:
    _finding(raw, "tenan-hr-cycle")["ref"] = "osd-288"
    raw["sources"]["osd-288"] = {"extent": "partial", "what": "x"}


def _idle_source(raw: dict[str, Any]) -> None:
    raw["sources"]["mmash"] = {"extent": "partial", "what": "x"}


def _unknown_key(raw: dict[str, Any]) -> None:
    raw["indicators"]["menstrual-mood"] = raw["indicators"].pop("hrv-sdnn")


def _reference_phase_row(raw: dict[str, Any]) -> None:
    raw["indicators"]["heart-rate"]["follicular"] = raw["indicators"]["heart-rate"]["menstrual"]


def _wrong_unit(raw: dict[str, Any]) -> None:
    _finding(raw, "baker-core-luteal")["magnitude"]["unit"] = "[degF]"


@pytest.mark.parametrize(("mutate", "reason"), [
    (_drop_figure, "no es la de sus frases"),
    (_invent_figure, "no está escrito en su frase"),
    (_wrong_derivation, "no es la media de la referencia"),
    (_sdnn_figure_for_rmssd, "da la cifra de otro indicador"),
    (_menses_mean_as_follicular, "no es la media de la referencia"),
    (_written_figure_relabelled, "una cifra escrita no cambia de referencia"),
    (_integer_part_of_a_decimal, "57 no está escrito en su frase"),
    (_reference_from_other_sentence, "sin la media de la referencia"),
    (_dissent_on_unsupported, "con frases leídas"),
    (_phase_not_named, "phase_note"),
    (_bad_evidence_type, "clase desconocida"),
    (_rounded_derivation, "no es la resta de sus medias"),
    (_integer_part_of_a_luteal_decimal, "59 no está escrito en su frase"),
    (_flip_sign, "no dicen todas"),
    (_literal_against, "el literal no dice"),
    (_literal_not_in_quote, "no está escrito en su frase"),
    (_contested_one_source, "de dos fuentes o más"),
    (_contested_one_direction, "no coincidan"),
    (_dissent_hidden, "disenso sin decir"),
    (_direction_with_figure, "no lleva cifra"),
    (_skin_as_magnitude, "no da cifra"),
    (_unsupported_without_refs, "sin sus fichas"),
    (_animal_source, "solo en personas"),
    (_idle_source, "ninguna frase ni búsqueda"),
    (_unknown_key, "no es un indicador del catálogo"),
    (_reference_phase_row, "la de referencia"),
    (_wrong_unit, "no está en"),
])
def test_the_loader_rejects_what_breaks_its_contract(
    mutate: Callable[[dict[str, Any]], None], reason: str,
) -> None:
    raw = _raw()
    mutate(raw)
    with pytest.raises(cp.CyclePhysiologyError, match=reason):
        cp.validate(raw)


def test_a_contested_row_with_two_sources_that_disagree_is_accepted() -> None:
    """«Discutido» es válido con frases de sentidos distintos y de al menos dos fichas."""
    raw = _raw()
    entry = raw["indicators"]["hrv-rmssd"]["luteal"]
    entry.update(evidence="contested", direction="contested",
                 findings=[*entry["findings"], *entry.pop("dissent")])
    entry.pop("dissent_note")
    cp.validate(raw)


def test_a_written_decrease_is_read_without_its_sign() -> None:
    """«5.5 ms lower» se publica sin signo: la cifra negativa de una bajada se busca sin él."""
    raw = _raw()
    item = _finding(raw, "alzueta-rmssd-luteal")
    item["quote"] = "Correspondingly, rMSSD HRV tended to be 5.5 ms lower in the luteal phase."
    item["literal"] = "5.5 ms lower in the luteal phase"
    item["magnitude"] = {"key": "hrv-rmssd", "low": -5.5, "high": -5.5, "unit": "ms"}
    cp.validate(raw)
