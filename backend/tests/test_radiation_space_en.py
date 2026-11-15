"""La radiación y la geometría espacial en inglés (unidad 14 del idioma por petición).

Por qué existe: estas frases las escribe el backend y la interfaz las enseña tal cual. Aquí se
fija que, pedidas en inglés, salen en inglés con las mismas cifras (y el punto decimal), que la
respuesta en castellano sigue siendo la de antes, que los identificadores, las claves y las frases
de la fuente no cambian, y que lo que EMMA firma (la discrepancia SPICE-Horizons) se escribe en
castellano pida quien pida. También que el inglés no afirma más que el castellano: ni
«certificado», ni «validado», ni «diagnóstico», ni una orden médica.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import radiation
from app.api import crew_radiation
from app.core import i18n
from app.core.cache import CachedPayload
from app.core.config import Settings
from app.environment import (
    comms_status,
    conjunction,
    distances,
    donki,
    dosimetry,
    ephemeris_coverage,
    iswa,
    orbit,
    spice,
)
from app.environment.ephemeris import SOURCE, CommsWindow, Contrast
from app.evidence import imm_radiation, radiation_read
from app.ingest.fhir import VitalObservation, observation
from tests.conftest import ENGLISH_HEADERS

T0 = dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC)
START = dt.date(2026, 11, 1)

_SPANISH_ONLY = re.compile(r"[áéíóúñ¿¡«»]", re.IGNORECASE)
_FORBIDDEN = re.compile(r"certified|validated|diagnos|administer|must take", re.IGNORECASE)
# Frases castellanas que no pueden quedar en una respuesta inglesa (por muestreo, una por pieza).
_SPANISH_SENTENCES = (
    "no se supone cero", "se muestra", "tripulante", "Sin efemérides", "No aplica", "Retardo",
    "no en vivo", "misión", "Tierra", "órbita", "días", "núcleo",
)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings(item)]
    return []


def _assert_english(text: str) -> None:
    assert not _SPANISH_ONLY.search(text), text
    assert not _FORBIDDEN.search(text), text
    for sentence in _SPANISH_SENTENCES:
        assert sentence not in text, (sentence, text)


def _rates(values: list[tuple[int, float]]) -> list[VitalObservation]:
    return [
        observation("absorbed-dose-rate", value, T0 + dt.timedelta(hours=hour), "CDR", "d")
        for hour, value in values
    ]


# --------------------------------------------------------------------------- #
# Los dos hermanos ingleses: cobertura, y un inglés que no afirma de más
# --------------------------------------------------------------------------- #


def _is_not_prose(text: str) -> bool:
    """Lo que no se traduce: identificadores, fechas, direcciones y lo que ya está en inglés."""
    return not _SPANISH_ONLY.search(text) and not re.search(
        r"\b(?:de|del|la|el|los|las|sobre|sin|con|que|se)\b", text
    )


def test_the_radiation_readings_overlay_covers_everything_emma_writes() -> None:
    spanish = radiation_read.describe()
    quotes = {item["quote"] for entry in spanish.values() for item in entry["quotes"]}
    # Las fichas son del registro (otra unidad) y las frases de la fuente van en su idioma.
    own = {
        name: {key: value for key, value in entry.items() if key != "sources"}
        for name, entry in spanish.items()
    }
    missing = i18n.missing(
        radiation_read.READ_PATH, own, skip=lambda text: text in quotes or _is_not_prose(text)
    )
    assert missing == []


def test_the_imm_overlay_covers_everything_emma_writes() -> None:
    spanish = imm_radiation.describe("leo")
    verbatim = {spanish["measure_quote"], spanish["caveat_quote"], spanish["condition"]}
    verbatim |= {
        item[key] for item in spanish["drms"] for key in ("drm_quote", "table", "row_quote")
    }
    own = {key: value for key, value in spanish.items() if key != "source"}
    missing = i18n.missing(
        imm_radiation.DATA_PATH, own, skip=lambda text: text in verbatim or _is_not_prose(text)
    )
    # Las dos frases que se escriben en el código llevan su inglés con `tr`, no en el hermano.
    assert missing == [spanish["assigned_by"], spanish["scope"]]


@pytest.mark.parametrize("path", [radiation_read.READ_PATH, imm_radiation.DATA_PATH])
def test_the_overlays_keep_the_figures_and_claim_no_more(path: Path) -> None:
    strings = json.loads(i18n.overlay_path(path).read_text(encoding="utf-8"))["strings"]
    assert strings
    for spanish, english in strings.items():
        assert english.strip() and english != spanish
        assert not _SPANISH_ONLY.search(english), english
        assert not _FORBIDDEN.search(english), english
        # Las mismas cifras: solo cambia la coma decimal por el punto, y «25 %» por «25%».
        figures_es = sorted(re.findall(r"\d+(?:[.,]\d+)?", spanish.replace(",", ".")))
        figures_en = sorted(re.findall(r"\d+(?:\.\d+)?", english))
        assert figures_en == figures_es, (spanish, english)


def test_the_radiation_readings_in_english_keep_quotes_and_identifiers(english: None) -> None:
    served = radiation_read.describe()
    with i18n.use("es"):
        spanish = radiation_read.describe()
    assert served["onboard_warning"]["label"] == "Onboard warning"
    assert served["solar_cycle"]["label"] == "Solar cycle"
    assert served["shelter_exit"]["label"] == "End of sheltering"
    assert "EMMA does not read HERA" in served["onboard_warning"]["text"]
    assert "with 94.4," in served["solar_cycle"]["text"]
    assert "94,4" not in served["solar_cycle"]["text"]
    for name, entry in served.items():
        assert entry["read_on"] == spanish[name]["read_on"]
        for field in ("label", "text", "scope", "not_found"):
            _assert_english(entry[field])
        for quote, original in zip(entry["quotes"], spanish[name]["quotes"], strict=True):
            assert quote["quote"] == original["quote"]
            assert quote["ref"] == original["ref"]
            assert quote["read_on"] == original["read_on"]
            _assert_english(quote["where"])
    assert served["onboard_warning"]["emma_reads_it"] is False


def test_the_imm_in_english_is_the_same_figure_and_nothing_more(english: None) -> None:
    served = imm_radiation.describe("leo")
    with i18n.use("es"):
        spanish = imm_radiation.describe("leo")
    assert served["condition_display"] == "acute radiation syndrome"
    assert served["measure"] == (
        "probability of at least one acute radiation syndrome during the mission, for one crew "
        "member"
    )
    assert "it is not the probability of this crew member" in served["scope"]
    for key in ("condition", "measure_quote", "caveat_quote", "read_on", "source"):
        assert served[key] == spanish[key]
    for drm, original in zip(served["drms"], spanish["drms"], strict=True):
        for key in ("key", "drm_quote", "table", "row_quote", "probability", "probability_text"):
            assert drm[key] == original[key]
        _assert_english(drm["display"])
    for profile, original in zip(served["profiles"], spanish["profiles"], strict=True):
        for key in ("id", "declared", "drm", "probability", "probability_text"):
            assert profile[key] == original[key]
        _assert_english(profile["reason"])
    for key in ("measure", "caveat", "assigned_by", "scope"):
        _assert_english(served[key])


# --------------------------------------------------------------------------- #
# Las tres escalas de radiación
# --------------------------------------------------------------------------- #


def _scales() -> dict[str, Any]:
    rates = _rates([(0, 10.0), (12, 14.5), (24, 11.25)])
    mission = radiation.mission_dose(rates, START)
    projection = radiation.mission_projection(
        rates, mission_start=START, mission_days=180, prior_career_msv=120.0, limit_msv=600.0,
    )
    return radiation.scales(
        active_event={"id": "sep-1"}, event_time=T0, now=T0 + dt.timedelta(minutes=30),
        mission=mission, prior_career_msv=None, limit_msv=600.0, projection=projection,
    )


def test_the_dose_scales_in_english_keep_their_class_and_their_figures(english: None) -> None:
    served = _scales()
    with i18n.use("es"):
        spanish = _scales()
    mission, projection = served["mission"], served["projection"]
    # La clase de cada cifra es un identificador: no se traduce ni se sube de categoría.
    assert mission["observation_type"] == "inferred"
    assert projection["observation_type"] == "predicted"
    assert projection["by_type"]["observation_type"] == "inferred"
    assert mission["basis"].endswith("it is not a measured dose")
    assert mission["quality_factor"] == 2.38
    assert mission["quality_source"] == (
        "Whole-mission quality factor measured with a TEPC (Spacelab SLS-1)"
    )
    assert "it assumes a constant rate: it does not foresee solar events" in projection["basis"]
    assert "(Q 1.83)" in projection["by_type"]["basis"]
    assert "(Q 2.74)" in projection["by_type"]["basis"]
    assert "it is not a confidence interval" in projection["by_type"]["basis"]
    assert "(1.83)" in projection["by_type"]["source"]["relevance"]
    assert "1,83" in spanish["projection"]["by_type"]["basis"]
    assert "µGy/h" in projection["basis"] and "," not in projection["basis"].split("µGy/h")[0][-8:]
    assert served["career"]["basis"] == (
        "no prior dose declared in the crew member's profile: zero is not assumed"
    )
    assert served["career"]["limit_source"] == "NASA-STD-3001 [V1 4030]"
    assert served["acute"]["time_to_action"]["basis"].startswith("Orion procedure: up to 1 h")
    # Los números son los mismos en los dos idiomas.
    for key in ("value_msv", "absorbed_mgy", "samples", "hours_covered", "model_version"):
        assert mission[key] == spanish["mission"][key]
    for key in ("value_msv", "rate_ugy_per_h", "remaining_days", "model_version", "mission_end"):
        assert projection[key] == spanish["projection"][key]
    for text in (
        mission["basis"], projection["basis"], projection["scope"],
        projection["by_type"]["basis"], projection["career"]["basis"],
        served["career"]["basis"], served["acute"]["time_to_action"]["basis"],
    ):
        _assert_english(text)


def test_the_short_term_limits_in_english_keep_the_table_of_the_standard(english: None) -> None:
    served = radiation.short_term_limits()
    with i18n.use("es"):
        spanish = radiation.short_term_limits()
    assert [row["organ"] for row in served["rows"]] == [row["organ"] for row in spanish["rows"]]
    assert served["rows"][0]["organ_display"] == "Lens"
    assert spanish["rows"][0]["organ_display"] == "Cristalino"
    blood = served["rows"][2]
    assert blood["career"] == {
        "value": None, "unit": None, "absent": "not applicable", "literal": "Not applicable",
    }
    assert spanish["rows"][2]["career"]["absent"] == "no aplica"
    for row, original in zip(served["rows"], spanish["rows"], strict=True):
        assert row["unit"] == original["unit"]
        assert row["thirty_day"]["value"] == original["thirty_day"]["value"]
        _assert_english(row["organ_display"])
        if row["note"] is not None:
            _assert_english(row["note"])
    assert "they are not converted" in served["units"]
    assert served["source"]["relevance"].startswith("Table 4.8-1")
    assert served["source"]["id"] == spanish["source"]["id"]
    # Una copia por idioma: pedir en inglés no cambia lo que después se sirve en castellano.
    with i18n.use("es"):
        assert radiation.short_term_limits() == spanish


def test_the_shelter_note_follows_the_language() -> None:
    later = T0 + dt.timedelta(hours=2)
    spanish = radiation.time_to_action(later, T0)
    with i18n.use("en"):
        served = radiation.time_to_action(later, T0)
    assert spanish is not None and served is not None
    assert spanish["elapsed_note"] == radiation.SHELTER_NOT_STARTED
    assert served["elapsed_note"].startswith("The shelter starts after Earth's cut-off")
    assert served["elapsed_minutes"] is None


def test_the_dose_estimate_in_english_keeps_its_quality_factor(english: None) -> None:
    estimate = dosimetry.DoseEstimate(
        value_msv=0.647, model=dosimetry.DEFAULT_MODEL, quality_factor=2.38, samples=4,
        hours_covered=24.0,
        source_note=dosimetry.MEAN_QUALITY_FACTORS[dosimetry.DEFAULT_MODEL].source,
    )
    served = estimate.to_dict()
    assert served["description"] == "0.647 mSv (estimated: absorbed dose x Q = 2.38)"
    assert served["observation_type"] == "inferred"
    assert served["source"].startswith("Whole-mission quality factor measured with a TEPC")
    with i18n.use("es"):
        assert estimate.to_dict()["description"] == (
            "0,647 mSv (estimada: dosis absorbida x Q = 2,38)"
        )
    unit = dosimetry.MEAN_QUALITY_FACTORS[dosimetry.QualityFactorModel.UNIT].source
    assert i18n.loc(unit) == (
        "Q = 1. For comparison only: it underestimates the actual dose equivalent"
    )


# --------------------------------------------------------------------------- #
# DONKI, iSWA y la órbita
# --------------------------------------------------------------------------- #


def test_the_donki_snapshot_says_it_is_not_live_in_both_languages() -> None:
    snapshot = donki.load_snapshot(donki.SNAPSHOT)
    assert snapshot is not None
    day = f"{snapshot.retrieved_at.astimezone(dt.UTC):%Y-%m-%d}"
    assert snapshot.note == f"instantánea de DONKI del {day}, no en vivo"
    with i18n.use("en"):
        assert snapshot.note == f"DONKI snapshot of {day}, not live"
        assert snapshot.label.endswith(f"DONKI snapshot of {day}, not live")
        served = snapshot.to_dict()
        assert served["live"] is False
        assert "no endorsement by NASA is implied" in served["licence"]
        _assert_english(served["licence"])
    assert snapshot.to_dict()["licence"] == donki.SNAPSHOT_LICENCE


def test_the_particle_series_in_english_keep_units_and_identifiers(english: None) -> None:
    now = dt.datetime.now(dt.UTC)
    rows = [{"time": now.isoformat(), "flux_ge_10mev": 0.25, "origin": "GOES-18"}]
    dataset = iswa.DATASETS[iswa.Series.PROTONS]
    payload = CachedPayload(
        data=rows, fetched_at=now, source=iswa.source_label(dataset), from_cache=True,
    )
    served = iswa.describe(iswa.Series.PROTONS, payload, 24)
    with i18n.use("es"):
        spanish = iswa.describe(iswa.Series.PROTONS, payload, 24)
    assert served["title"] == "Integral proton flux ≥10 MeV, primary GOES (5 min averages)"
    assert served["channels"][0]["label"] == "integral proton flux ≥10 MeV (GOES P10 channel)"
    assert served["source"] == f"NASA CCMC iSWA (HAPI) · {dataset.dataset_id} · NOAA SWPC data"
    assert spanish["source"] == iswa.source_label(dataset)
    for key in ("dataset", "samples", "latest", "window_hours"):
        assert served[key] == spanish[key]
    assert served["channels"][0]["unit"] == "pfu"
    reference = iswa.s1_reference()
    assert reference["label"] == "S1 (minor) on the NOAA solar radiation storm scale"
    assert reference["evaluated"] is False and reference["value"] == 10.0
    # La constante no se toca: quien la lea en castellano la ve como estaba.
    assert iswa.S1_REFERENCE["label"].startswith("S1 (menor)")
    _assert_english(i18n.loc(iswa.SCOPE))
    _assert_english(i18n.loc(iswa.LICENCE))
    wind = iswa.unavailable(iswa.Series.SOLAR_WIND, "x")
    assert wind["title"] == "NOAA SWPC real-time solar wind (1 min averages)"


def test_the_saa_contour_in_english_keeps_its_source_and_its_limits(english: None) -> None:
    served = orbit.saa_region()
    original = orbit.SAA_REGION
    assert served["polygon"] == original["polygon"]
    assert served["source"]["quote"] == original["source"]["quote"]
    assert served["source"]["url"] == original["source"]["url"]
    assert served["superseded"]["quote"] == original["superseded"]["quote"]
    assert served["evidence"] == "documented magnitude"
    assert len(served["limits"]) == len(original["limits"])
    assert "not a dose or proton-flux contour" in served["limits"][0]
    for text in [*served["limits"], served["altitude"], served["source"]["read_via"],
                 served["superseded"]["why_replaced"]]:
        _assert_english(text)
    with i18n.use("es"):
        assert orbit.saa_region() == original
    assert original["evidence"] == "magnitud documentada"


# --------------------------------------------------------------------------- #
# El retardo, la conjunción, la cobertura y SPICE
# --------------------------------------------------------------------------- #


def _window(**extra: Any) -> CommsWindow:
    return CommsWindow(
        epoch=dt.date(2026, 12, 1), distance_au=1.5, one_way_minutes=12.475, target="499", **extra,
    )


def _contrast(agrees: bool) -> Contrast:
    return Contrast(
        local=spice.source_label(), reference=SOURCE,
        reference_fetched_at=T0, one_way_seconds_difference=0.25 if not agrees else 0.000002,
        elongation_deg_difference=0.00012, one_way_seconds_tolerance=0.1,
        elongation_deg_tolerance=0.01, agrees=agrees,
        used=spice.source_label() if agrees else SOURCE,
    )


def test_the_delay_sentence_follows_the_language() -> None:
    window = _window()
    assert window.describe() == "Sin consulta en vivo: la respuesta de Tierra tardaría 25 min"
    with i18n.use("en"):
        assert window.describe() == "No live consultation: Earth's answer would take 25 min"
        near = replace(window, one_way_minutes=1.0)
        assert near.describe() == "Consultation with Earth available (~2 min)"
        # La firma de la ventana no se traduce: la compara el código y va al registro.
        assert window.to_dict()["source"] == SOURCE


def test_the_delay_status_words_in_english_and_its_keys_unchanged(english: None) -> None:
    day = dt.date(2026, 12, 1)
    none = comms_status.describe(None, None, day, profile_id="leo")
    assert (none["state"], none["word"]) == (comms_status.NOT_APPLICABLE, "Not applicable")
    assert "no ephemeris target" in none["text"]
    missing = comms_status.describe(None, "499", day, profile_id="mars-transit")
    assert (missing["state"], missing["word"]) == (comms_status.MISSING, "No ephemeris")
    assert missing["text"].endswith("The delay is not made up.")
    local = comms_status.describe(
        _window(source=spice.source_label()), "499", day, profile_id="mars-transit",
    )
    assert local["state"] == comms_status.AVAILABLE
    assert local["source"] == comms_status.SPICE
    assert local["word"] == "Delay computed locally (SPICE)"
    assert local["text"] == (
        f"Delay for 2026-12-01 computed locally (SPICE) (local SPICE, kernel {spice.spk_name()})."
    )
    horizons = comms_status.describe(_window(), "499", day, profile_id="mars-transit")
    assert horizons["word"] == "Delay from JPL Horizons"
    assert horizons["source_text"] == "JPL Horizons"
    for block in (none, missing, local, horizons):
        _assert_english(block["word"])
        _assert_english(block["text"])
    with i18n.use("es"):
        spanish = comms_status.describe(None, "499", day, profile_id="mars-transit")
    assert (spanish["state"], spanish["word"]) == (comms_status.MISSING, "Sin efemérides")


def test_the_discrepancy_is_shown_in_english_and_signed_in_spanish(english: None) -> None:
    contrast = _contrast(agrees=False)
    window = _window(contrast=contrast)
    shown = comms_status.describe(window, "499", window.epoch, profile_id="mars-transit")
    assert shown["discrepancy"]["word"] == "SPICE and JPL Horizons disagree"
    assert shown["discrepancy"]["text"] == (
        f"The local computation (local SPICE, kernel {spice.spk_name()}) disagrees with JPL "
        "Horizons: a difference of 250.000 ms of light time and 0.00012° of elongation, above "
        "the declared error (0.1 s and 0.01°). On this day JPL Horizons, the reference, is used."
    )
    # Lo que se firma es castellano y con coma decimal, aunque lo pida una consola en inglés.
    signed = comms_status.discrepancy_payload(window, "500@399")
    assert signed is not None
    with i18n.use("es"):
        assert signed == comms_status.discrepancy_payload(window, "500@399")
        assert signed["text"] == contrast.describe()
    assert signed["text"].startswith("El cálculo local (SPICE local, núcleo")
    assert "250,000 ms de tiempo de luz" in signed["text"]
    assert signed["local"] == spice.source_label()
    agreed = _contrast(agrees=True).describe()
    assert agreed.startswith("Checked against JPL Horizons (cached): a difference of 0.002 ms")


def test_the_conjunction_in_english_keeps_the_threshold_and_its_quotes(english: None) -> None:
    inside = conjunction.describe(_window(solar_elongation_deg=1.25), "499")
    assert inside["label"] == "Solar conjunction"
    assert inside["state"] == conjunction.WITHIN
    assert inside["text"].startswith(
        "Mars is 1.3° from the Sun as seen from Earth: inside the 2° of the period"
    ) or inside["text"].startswith(
        "Mars is 1.2° from the Sun as seen from Earth: inside the 2° of the period"
    )
    clear = conjunction.describe(_window(solar_elongation_deg=47.5), "499")
    assert "Mars is 47.5° from the Sun as seen from Earth: outside the 2°" in clear["text"]
    unknown = conjunction.describe(None, "499")
    assert unknown["text"] == (
        "No ephemeris: it is not known how many degrees from the Sun Mars is as seen from "
        "Earth, or whether it is in solar conjunction."
    )
    other = conjunction.describe(replace(_window(solar_elongation_deg=10.0), target="301"), "301")
    assert other["state"] == conjunction.NO_THRESHOLD
    assert other["text"].startswith("The target (code 301) is 10.0° from the Sun")
    unrecorded = conjunction.describe(_window(), "499")
    assert unrecorded["state"] == conjunction.NOT_RECORDED
    with i18n.use("es"):
        spanish = conjunction.describe(_window(solar_elongation_deg=47.5), "499")
    assert "Marte está a 47,5° del Sol" in spanish["text"]
    assert spanish["note"] == conjunction.NOTE
    for block in (inside, clear, unknown, other, unrecorded):
        _assert_english(block["text"])
        _assert_english(block["note"])
        for cite, original in zip(block["citations"], spanish["citations"], strict=True):
            assert cite["quote"] == original["quote"]
            assert cite["ref"] == original["ref"]
            _assert_english(cite["section"])


def test_the_coverage_sentences_in_english_carry_the_same_counts(tmp_path: Path) -> None:
    settings = Settings(
        cache_dir=tmp_path, offline=True, mission_start=START, mission_days=9,
    )
    spanish = ephemeris_coverage.coverage(settings, target="499")
    with i18n.use("en"):
        served = ephemeris_coverage.coverage(settings, target="499")
    assert spanish["state"] == served["state"] == ephemeris_coverage.NONE
    assert "Ningún día de la misión" in spanish["text"]
    assert served["text"] == (
        "No day of the mission (from 2026-11-01 to 2026-11-10, launch and return included, 10 "
        "days) has ephemeris cached: offline, the delay and the solar conjunction come out with "
        "no data."
    )
    assert served["day"]["served_by"] is None
    assert served["day"]["served_text"].startswith("no ephemeris: neither the local computation")
    assert spanish["how_to_preload"] == ephemeris_coverage.HOW_TO_PRELOAD
    assert served["how_to_preload"].startswith("They are preloaded with network access")
    assert "X-EMMA-Console: 1" in served["how_to_preload"]
    assert served["spice"]["available"] is False
    for text in (
        served["text"], served["note"], served["how_to_preload"], served["day"]["served_text"],
        served["spice"]["reason"], served["spice"]["precedence"],
        served["spice"]["contrast_policy"],
        *(row["covers"] for row in served["spice"]["kernels"]),
        *(row["integrity"] for row in served["spice"]["kernels"]),
    ):
        _assert_english(text)
    for key in ("days", "covered_days", "missing_days", "missing", "served_by", "offline_state"):
        assert served[key] == spanish[key]
    with i18n.use("en"):
        first = ephemeris_coverage._text(
            ephemeris_coverage.PARTIAL, 10, 4, 1, START, START + dt.timedelta(days=9),
            spice.source_label(), {"spice": 10, "horizons_cache": 0, "none": 0}, 1,
        )
        partial = ephemeris_coverage._text(
            ephemeris_coverage.PARTIAL, 10, 4, 2, START, START + dt.timedelta(days=9),
        )
    assert first == (
        "Offline, the delay and the solar conjunction of the 10 days of the mission (from "
        "2026-11-01 to 2026-11-10, launch and return included) are computed locally (local "
        f"SPICE, kernel {spice.spk_name()}). JPL Horizons has 4 days cached; 1 day serves as a "
        "cross-check of the local computation."
    )
    assert partial.startswith("4 of the 10 days of the mission")
    assert "6 days are missing in 2 stretches" in partial
    with i18n.use("en"):
        as_contrast = i18n.loc(ephemeris_coverage.HOW_TO_PRELOAD_AS_CONTRAST)
    assert as_contrast.startswith("Not needed for the offline delay")
    assert as_contrast.endswith("with the header X-EMMA-Console: 1.")


def test_the_distances_in_english_keep_states_and_identifiers(tmp_path: Path) -> None:
    settings = Settings(cache_dir=tmp_path, offline=True)
    day = dt.date(2026, 12, 1)
    spanish = distances.describe(settings, day, "lunar-surface")
    with i18n.use("en"):
        served = distances.describe(settings, day, "lunar-surface")
        unknown = distances.describe(settings, day, "venus")
        en_route = distances.describe(settings, day, "mars-transit")
    assert served["scope"].startswith("Descriptive: it does not change the risk")
    assert served["observer"] == "from the geocentre (centre of the Earth), centre to centre"
    assert served["crew_place"] == {"body": "moon", "text": "On the surface of the Moon."}
    assert [body["id"] for body in served["bodies"]] == ["moon", "mars"]
    assert [body["label"] for body in served["bodies"]] == ["Moon", "Mars"]
    assert [body["label"] for body in spanish["bodies"]] == ["Luna", "Marte"]
    assert [body["state"] for body in served["bodies"]] == [
        body["state"] for body in spanish["bodies"]
    ]
    assert served["earth_link"]["state"] == spanish["earth_link"]["state"]
    assert unknown["unknown_text"] == (
        "The profile 'venus' is not in EMMA's catalogue: nothing is computed for it."
    )
    assert en_route["crew_place"]["text"].startswith("En route: the spacecraft is between two")
    assert en_route["earth_link"]["state"] == distances.MISSING
    assert en_route["earth_link"]["text"].startswith("No ephemeris of Mars for 2026-12-01")
    for text in (
        served["scope"], served["observer"], served["crew_place"]["text"],
        en_route["crew_place"]["text"], *(body["note"] for body in served["bodies"]),
    ):
        _assert_english(text)


def test_spice_availability_in_english_and_its_signature_unchanged(tmp_path: Path) -> None:
    settings = Settings(cache_dir=tmp_path / "cache", offline=True)
    spanish = spice.availability(settings).to_dict()
    with i18n.use("en"):
        served = spice.availability(settings).to_dict()
        # La firma de lo calculado con SPICE es la misma pida quien pida.
        assert spice.source_label() == f"SPICE local, núcleo {spice.spk_name()}"
        assert i18n.loc(spice.source_label()) == f"local SPICE, kernel {spice.spk_name()}"
        assert i18n.loc(spice.ORIGINS["bundled"]) == "kernels bundled with the desktop application"
        _assert_english(i18n.loc(spice.TARGETS["499"][1]))
    assert served["available"] is spanish["available"] is False
    assert [row["name"] for row in served["kernels"]] == [row["name"] for row in spanish["kernels"]]
    assert served["reason"] != spanish["reason"]
    assert "as before" in served["reason"]
    _assert_english(served["reason"])


# --------------------------------------------------------------------------- #
# Las rutas: en inglés con la cabecera, y en castellano como antes sin ella
# --------------------------------------------------------------------------- #


def _seed(client: TestClient, scenario: str = "spe-event") -> None:
    seeded = client.post("/api/simulate", params={"scenario": scenario, "seed": 7})
    assert seeded.status_code == 201, seeded.text


def test_the_crew_radiation_route_in_english(client: TestClient) -> None:
    _seed(client)
    spanish = client.get("/api/crew/radiation").json()
    served = client.get("/api/crew/radiation", headers=ENGLISH_HEADERS).json()
    assert spanish["display"] == crew_radiation.DISPLAY
    assert spanish["basis"] == crew_radiation.BASIS
    assert spanish["shielding"] == crew_radiation.NO_SHIELDING
    assert spanish["note"] == crew_radiation.NOT_EVALUATED
    assert served["display"] == "The crew facing a solar event"
    assert served["shielding"].startswith("No shielding factors: EMMA does not model")
    assert served["note"].startswith("Shown, not evaluated")
    assert served["evaluated"] is False
    assert [row["subject"] for row in served["crew"]] == [row["subject"] for row in spanish["crew"]]
    for row, original in zip(served["crew"], spanish["crew"], strict=True):
        if row["mission"] is None:
            assert row["mission_missing_text"] is None or row["mission_missing_text"].startswith(
                "no dose for this mission"
            )
            continue
        assert row["mission"]["value_msv"] == original["mission"]["value_msv"]
        assert row["mission"]["observation_type"] == "inferred"
        assert row["mission"]["basis"].endswith("it is not a measured dose")
        assert original["mission"]["basis"].endswith("no es una dosis medida")
        _assert_english(row["career"]["basis"])
    for text in (served["display"], served["basis"], served["shielding"], served["note"]):
        _assert_english(text)
    if served["shelter"] is not None:
        assert served["shelter"]["basis"].startswith("Orion procedure")
        assert spanish["shelter"]["basis"].startswith("procedimiento de Orion")
    else:
        assert served["shelter_missing_text"].startswith("no solar event in force")
        assert spanish["shelter_missing_text"] == crew_radiation.NO_EVENT_SHELTER


def test_the_status_radiation_block_in_english(client: TestClient) -> None:
    _seed(client)
    spanish = client.get("/api/status").json()["radiation"]
    served = client.get("/api/status", headers=ENGLISH_HEADERS).json()["radiation"]
    assert served["career"]["limit_source"] == spanish["career"]["limit_source"]
    assert served["short_term_limits"]["rows"][1]["organ_display"] == "Skin"
    assert spanish["short_term_limits"]["rows"][1]["organ_display"] == "Piel"
    assert served["solar_cycle"]["label"] == "Solar cycle"
    assert spanish["solar_cycle"]["label"] == "Ciclo solar"
    assert served["acute"]["onboard_warning"]["emma_reads_it"] is False
    assert served["acute"]["shelter_exit"]["label"] == "End of sheltering"
    if served["mission"] is not None:
        assert served["mission"]["value_msv"] == spanish["mission"]["value_msv"]
        assert served["mission"]["observation_type"] == "inferred"
        _assert_english(served["mission"]["basis"])
    if served["projection"] is not None:
        assert served["projection"]["observation_type"] == "predicted"
        assert served["projection"]["value_msv"] == spanish["projection"]["value_msv"]
        _assert_english(served["projection"]["basis"])


def test_the_distances_and_series_routes_in_english(client: TestClient) -> None:
    _seed(client, "nominal")
    spanish = client.get("/api/distances", params={"epoch": "2026-12-01"}).json()
    served = client.get(
        "/api/distances", params={"epoch": "2026-12-01"}, headers=ENGLISH_HEADERS
    ).json()
    assert spanish["scope"] == distances.SCOPE
    assert spanish["observer"] == distances.OBSERVER_TEXT
    assert served["scope"].startswith("Descriptive:")
    assert served["declared_profile"] == spanish["declared_profile"]
    assert [body["id"] for body in served["bodies"]] == [body["id"] for body in spanish["bodies"]]

    spanish = client.get("/api/space-weather/series").json()
    served = client.get("/api/space-weather/series", headers=ENGLISH_HEADERS).json()
    assert spanish["scope"] == iswa.SCOPE and spanish["licence"] == iswa.LICENCE
    assert spanish["series"]["protons"]["reference"] == iswa.S1_REFERENCE
    assert served["scope"].startswith("Environment in geostationary orbit (GOES)")
    assert served["events"] == (
        "The catalogued events (SEP) are at GET /api/space-weather (NASA DONKI)."
    )
    assert served["series"]["protons"]["reference"]["label"].startswith("S1 (minor)")
    assert set(served["series"]) == set(spanish["series"]) == {"protons", "solar-wind"}
    for text in (served["scope"], served["licence"], served["events"]):
        _assert_english(text)


def test_the_orbit_spice_and_imm_routes_in_english(client: TestClient) -> None:
    _seed(client, "nominal")
    spanish = client.get("/api/orbit/iss").json()
    served = client.get("/api/orbit/iss", headers=ENGLISH_HEADERS).json()
    assert spanish["saa_region"]["limits"] == orbit.SAA_REGION["limits"]
    assert served["scope"].startswith("descriptive: it does not change the risk")
    assert served["mission_profile"] == spanish["mission_profile"]
    assert served["applies"] is spanish["applies"]
    if not served["applies"]:
        assert served["reason"].startswith("not applicable: the mission profile is")
    assert "not a dose or proton-flux contour" in served["saa_region"]["limits"][0]

    spanish = client.get("/api/spice").json()
    served = client.get("/api/spice", headers=ENGLISH_HEADERS).json()
    assert spanish["precedence"] == spice.PRECEDENCE
    assert spanish["contrast_policy"] == spice.CONTRAST_POLICY
    assert served["precedence"].startswith("SPICE first:")
    assert served["license"] == spanish["license"]
    assert served["declared_max_error"] == spanish["declared_max_error"]
    assert set(served["supported_targets"]) == set(spanish["supported_targets"])
    for text in (served["precedence"], served["contrast_policy"],
                 *served["supported_targets"].values()):
        _assert_english(text)

    spanish = client.get("/api/radiation/imm").json()
    served = client.get("/api/radiation/imm", headers=ENGLISH_HEADERS).json()
    assert spanish["condition_display"] == "síndrome agudo de radiación"
    assert served["condition_display"] == "acute radiation syndrome"
    assert [item["probability"] for item in served["drms"]] == [
        item["probability"] for item in spanish["drms"]
    ]
    assert [item["declared"] for item in served["profiles"]] == [
        item["declared"] for item in spanish["profiles"]
    ]


def test_no_english_of_this_unit_is_registered_twice() -> None:
    assert i18n.conflicts() == []
