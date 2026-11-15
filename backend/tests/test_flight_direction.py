"""El sentido en vuelo junto a la línea base (`evidence/flight_direction.py`).

Qué fijan estas pruebas:
- que cada sentido sale de una frase leída de una fuente humana con ficha oficial, que su literal
  está en la frase y dice ese sentido y ningún otro, y que la frase habla del vuelo;
- que «discutido» son frases que no coinciden, que «sin fuente» no lleva frases y que buscar y
  no encontrar no es lo mismo que no buscar;
- lo que la lectura encontró y no se puede perder: la frecuencia cardiaca, sin cambio en vuelo
  (la subida es después);
- que ningún texto suena a «es normal» ni a orden (invariante 7) y que nada del estado lo lee
  (invariante 5).

No salen a la red (invariante 3): lo leído vive en el repositorio.
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path
from typing import Any

import pytest

from app.evidence import flight_direction, registry
from app.evidence.flight_direction import (
    ALSO_READ_PREFIX,
    CONTESTED,
    DIRECTION_DISPLAY,
    FRAME,
    NO_SOURCE,
    NOT_SEARCHED,
    OBSERVED,
    REACTION_TIME,
    SEARCHED_PREFIX,
    FlightDirectionError,
    for_indicator,
    for_profile,
    read,
    validate,
)
from app.evidence.instruments_read import EXTENTS
from app.ingest.codes import CATALOG
from app.text_guard import check

APP = Path(flight_direction.__file__).resolve().parents[1]


def _raw() -> dict[str, Any]:
    return copy.deepcopy(read())


def _statement(raw: dict[str, Any], statement_id: str) -> dict[str, Any]:
    return next(item for item in raw["statements"] if item["id"] == statement_id)


# --------------------------------------------------------------------------- #
# Lo leído
# --------------------------------------------------------------------------- #


def test_every_direction_rests_on_a_read_sentence_from_people_in_flight() -> None:
    raw = read()
    statements = {item["id"]: item for item in raw["statements"]}
    for key, item in raw["indicators"].items():
        assert key in CATALOG
        found = {statements[ref]["direction"] for ref in item["statements"]}
        if item["direction"] == NO_SOURCE:
            assert not item["statements"] and item["searched"].strip()
        elif item["direction"] == CONTESTED:
            assert len(found) >= 2
        else:
            assert found == {item["direction"]}
    for item in raw["statements"]:
        assert item["literal"] in item["quote"]
        ref = registry.get(item["ref"])
        assert ref.population == "human" and ref.url is not None
        assert ref.url.startswith(
            ("https://pubmed.ncbi.nlm.nih.gov/", "https://pmc.ncbi.nlm.nih.gov/")
        )
        assert ref.pmid is not None, "cada frase de aquí se leyó en un registro de PubMed"
        assert item["ref"] in raw["sources"]
    assert flight_direction.cited_refs() == frozenset(raw["sources"])


def test_heart_rate_in_flight_is_unchanged_and_the_rise_is_after_flight() -> None:
    """Lo que la lectura encontró: el simulador subía la FC en reposo en vuelo con la cifra de un
    estudio que la ve sin cambio en vuelo y más alta después (hasta el 2026-10-31, cuando la
    deriva pasó a 0). Aquí se dice lo leído."""
    found = for_indicator("heart-rate")
    assert found["direction"] == "unchanged"
    assert {row["ref"] for row in found["statements"]} == {
        "hughson-2012-cardiovascular-iss", "xu-2013-hrv-sleep-iss", "fraser-2012-heart-rate-iss",
        "baevsky-2007-autonomic-iss",
    }
    assert "después del vuelo" in found["scope"]


def test_the_sdnn_stays_contested_as_the_simulator_declares_it() -> None:
    found = for_indicator("hrv-sdnn")
    assert found["direction"] == CONTESTED
    assert {row["direction"] for row in found["statements"]} == {"rises", "falls"}
    assert found["text"] == (
        "Discutido: las frases leídas no coinciden (1 frase: sube; 1 frase: baja)."
    )


def test_what_the_sixteenth_round_read_for_the_missing_indicators() -> None:
    """Respiración, saturación, sueño frente a antes del vuelo, PVT y analíticas (2026-10-23).

    Lo que la lectura encontró y no se puede perder sin volver a leer: la respiración y la RMSSD
    discutidas (los estudios no coinciden), el sueño más corto y menos eficiente en vuelo (la
    Mir), la PVT más lenta solo al principio del vuelo, y la serie roja al alza en vuelo.
    """
    expected = {
        "respiratory-rate": CONTESTED, "oxygen-saturation": "unchanged",
        "hrv-rmssd": CONTESTED, "sleep-duration": "falls", "sleep-efficiency": "falls",
        "pvt-mean-rt": "rises", "hemoglobin": "rises", "erythrocytes": "rises",
        "hematocrit": "rises", "mch": "falls", "platelets": "rises", "lymphocytes": "unchanged",
        "neutrophils": "rises", "urine-volume-24h": "falls",
        "pvt-lapses": NO_SOURCE, "circadian-shift": NO_SOURCE, "orthostatic-drop": NO_SOURCE,
        "mcv": NO_SOURCE, "mchc": NO_SOURCE, "neutrophil-lymphocyte-ratio": NO_SOURCE,
        "vitamin-d-25oh": NO_SOURCE,
    }
    for key, direction in expected.items():
        assert for_indicator(key)["direction"] == direction, key
    breathing = for_indicator("respiratory-rate")
    assert {row["direction"] for row in breathing["statements"]} == {"rises", "falls"}
    # Lo buscado y no encontrado de esta ronda dice dónde, no «no se ha buscado».
    for key, direction in expected.items():
        if direction == NO_SOURCE:
            assert for_indicator(key)["searched_display"].startswith(SEARCHED_PREFIX), key
    # Lo leído hoy lleva su fecha, no la del fichero.
    assert {row["read_on"] for row in for_indicator("pvt-mean-rt")["statements"]} == {
        "2026-10-23"
    }


def test_what_was_read_alongside_a_direction_is_said_apart() -> None:
    """La hemoglobina sube en vuelo (Kunz 2017); Trudel 2022, leído al buscar, no da su sentido
    en vuelo: se dice como «leído también», con su ficha, y no como «buscado y no encontrado»."""
    found = for_indicator("hemoglobin")
    assert found["direction"] == "rises"
    assert [row["ref"] for row in found["statements"]] == ["kunz-2017-hematologic-indices-iss"]
    assert found["searched_display"].startswith(ALSO_READ_PREFIX)
    # Markin 1998 (la Mir) le da una tendencia a bajar sin estadística: leída, no es un sentido.
    assert found["searched_sources"] == [
        registry.get("trudel-2022-hemolysis").source,
        registry.get("markin-1998-blood-biochemistry-mir").source,
    ]
    assert found["text"] == "En otros vuelos se observó que sube."


def test_a_speed_sentence_says_the_reaction_time_rises_and_only_there() -> None:
    """«Slower performance on the PVT» es un tiempo de reacción mayor: «sube»."""
    found = for_indicator("pvt-mean-rt")
    assert found["direction"] == "rises"
    speed = [item for item in read()["statements"] if item.get("reads_speed")]
    assert [item["id"] for item in speed] == ["dev-2024-pvt-early-flight"]
    cited_by = {key for key, item in read()["indicators"].items()
                if set(item["statements"]) & {row["id"] for row in speed}}
    assert cited_by <= REACTION_TIME


def test_what_the_eighteenth_round_read_for_hormones_and_markers() -> None:
    """Hormonas y marcadores tumorales (decimoctava ronda, U17, 2026-10-26).

    Lo que la lectura encontró y no se puede perder sin volver a leer: la LH sube en vuelo en una
    sola frase (Strollo 1998, 4 astronautas); de la TSH y la T4 libre no hay frase en vuelo
    (Skylab no las midió en vuelo; el transbordador, solo antes y después; el Twins Study midió
    las «thyroid hormones» en vuelo y su texto no da el resultado), y de los marcadores tumorales
    no hay nada medido en vuelo. Buscado y no encontrado no es «no buscado».
    """
    lh = for_indicator("lh")
    assert lh["direction"] == "rises"
    assert [row["ref"] for row in lh["statements"]] == ["strollo-1998-testicular-androgen"]
    assert lh["searched_display"].startswith(ALSO_READ_PREFIX)
    searched = {
        "estradiol", "fsh", "tsh", "free-t4", "beta2-microglobulin", "ca-125", "ca-15-3",
        "ca-19-9", "ca-27-29", "cea", "neuron-specific-enolase", "chromogranin-a",
    }
    for key in searched:
        found = for_indicator(key)
        assert found["direction"] == NO_SOURCE and found["statements"] == [], key
        assert found["searched_display"].startswith(SEARCHED_PREFIX), key
        assert found["searched_read_on"] == ["2026-10-26"] * len(found["searched_sources"]), key
    # Skylab: la tiroxina y la TSH no se midieron en las muestras de vuelo.
    for key in ("tsh", "free-t4"):
        assert "ntrs-19750006310" in read()["indicators"][key]["searched_refs"], key
    # La T4 libre no se confunde con la total ni con su índice.
    assert "que no es la T4 libre" in for_indicator("free-t4")["searched"]
    # Inspiration4 se dice como lo que es: un vuelo de tres días.
    assert "vuelo de tres días" in for_indicator("cea")["searched"]
    # Los seis marcadores tumorales dicen lo mismo, con las mismas fichas: una copia corregida
    # sin las otras se ve aquí.
    tumor = [read()["indicators"][key] for key in (
        "ca-125", "ca-15-3", "ca-19-9", "ca-27-29", "cea", "neuron-specific-enolase",
    )]
    assert len({item["searched"] for item in tumor}) == 1
    assert len({tuple(item["searched_refs"]) for item in tumor}) == 1


def test_what_the_nineteenth_round_read_for_hematology_and_biochemistry() -> None:
    """Hematología y bioquímica (decimonovena ronda, U6, 2026-10-31).

    Lo que la lectura encontró y no se puede perder sin volver a leer: dos indicadores discutidos
    por la duración del vuelo o el momento de la toma, el porcentaje de linfocitos en una sola
    frase, y siete que siguen sin sentido leído por un motivo dicho: entre ellos los que el estudio
    suplementaba, que no se leen como sentido del vuelo.
    """
    expected = {
        "cortisol-salivary": CONTESTED, "leukocytes": CONTESTED, "lymphocytes-percent": "rises",
        "neutrophils-percent": NO_SOURCE, "vitamin-d-25oh": NO_SOURCE,
        "mcv": NO_SOURCE, "mchc": NO_SOURCE, "neutrophil-lymphocyte-ratio": NO_SOURCE,
        "alkaline-phosphatase": NO_SOURCE, "calcium": NO_SOURCE,
    }
    for key, direction in expected.items():
        assert for_indicator(key)["direction"] == direction, key
    for key in ("cortisol-salivary", "leukocytes"):
        rows = for_indicator(key)["statements"]
        assert {row["direction"] for row in rows} == {"rises", "unchanged"}, key
    # «not significantly altered» (Buchheim 2019) es una frase de «sin cambio», con su errata.
    cortisol = {row["ref"]: row for row in for_indicator("cortisol-salivary")["statements"]}
    assert cortisol["buchheim-2019-inflammaging-cosmonauts"]["direction"] == "unchanged"
    words = flight_direction._DIRECTION_WORDS["unchanged"]
    assert words.search("cortisol was not significantly altered")
    assert not words.search("cortisol was significantly altered")
    # Lo suplementado se dice, con un solo sujeto dicho; y la toma temprana del cortisol, también.
    assert "N = 1" in for_indicator("vitamin-d-25oh")["searched"]
    assert "suplementa" in for_indicator("vitamin-d-25oh")["searched"]
    assert "suplementa" in for_indicator("calcium")["searched"]
    assert "primeros 18 días" in read()["indicators"]["cortisol-salivary"]["scope"]
    # Una figura sin leer no da un sentido.
    assert "que no se leyó" in for_indicator("neutrophils-percent")["searched"]
    # La fosfatasa ósea no se sirve como la total, ni el GLR como el NLR, ni el calcio ionizado
    # como el total.
    assert "no la total" in for_indicator("alkaline-phosphatase")["searched"]
    assert "no el NLR" in for_indicator("neutrophil-lymphocyte-ratio")["searched"]
    assert "ionizado, no el total" in for_indicator("calcium")["searched"]


def test_not_searched_is_not_searched_and_not_found() -> None:
    undeclared = next(key for key in CATALOG if key not in read()["indicators"])
    found = for_indicator(undeclared)
    assert found["direction"] == NO_SOURCE and found["statements"] == []
    assert found["text"] == NOT_SEARCHED and found["searched_display"] is None
    searched = for_indicator("mcv")
    assert searched["direction"] == NO_SOURCE
    assert searched["text"] != NOT_SEARCHED
    assert searched["searched_display"].startswith("Buscado y no encontrado: ")
    assert searched["searched_sources"] == [
        registry.get("kunz-2017-hematologic-indices-iss").source,
        registry.get("trudel-2022-hemolysis").source,
    ]
    assert found["searched_sources"] == []
    # Todo lo buscado y no encontrado tiene su ficha leída.
    for key, item in read()["indicators"].items():
        if item["direction"] == NO_SOURCE:
            assert for_indicator(key)["searched_sources"], key


def test_what_the_eighteenth_round_read_for_liver_kidney_electrolytes_and_inflammation() -> None:
    """Hígado, riñón, electrolitos e inflamación (2026-10-26): casi todo, buscado y no encontrado.

    Lo que la lectura encontró y no se puede perder sin volver a leer: solo dos frases con sentido
    medido en vuelo (el magnesio sube y las proteínas totales no cambian, en la ISS); las
    tendencias sin estadística de la Mir y una frase que no dice cuándo se tomó la muestra no se
    leen como sentido; y la PCR y la albúmina solo se vieron cambiar DESPUÉS.
    """
    expected = {
        "magnesium": "rises", "total-protein": "unchanged",
        "ast": NO_SOURCE, "alt": NO_SOURCE, "glucose": NO_SOURCE, "urea": NO_SOURCE,
        "ldh": NO_SOURCE,
        "creatinine": NO_SOURCE, "bun-creatinine-ratio": NO_SOURCE, "ggt": NO_SOURCE,
        "bilirubin-total": NO_SOURCE, "bilirubin-direct": NO_SOURCE, "albumin": NO_SOURCE,
        "sodium": NO_SOURCE, "potassium": NO_SOURCE, "chloride": NO_SOURCE,
        "phosphate": NO_SOURCE, "c-reactive-protein": NO_SOURCE,
    }
    for key, direction in expected.items():
        found = for_indicator(key)
        assert found["direction"] == direction, key
        # Todo lo de esta ronda se leyó el 2026-10-26 y lo dice, frase a frase y ficha a ficha.
        days = {row["read_on"] for row in found["statements"]} | set(found["searched_read_on"])
        # Menos el potasio, que la decimonovena ronda releyó (Smith 1997, el 2026-10-31).
        assert days == ({"2026-10-26", "2026-10-31"} if key == "potassium" else {"2026-10-26"}), key
        if direction == NO_SOURCE:
            assert found["searched_display"].startswith(SEARCHED_PREFIX), key
    protein = for_indicator("total-protein")
    assert [row["ref"] for row in protein["statements"]] == ["zwart-2022-albumin-iss"]
    # La frase de Grigor'ev 1994 no dice si compara tomas de vuelo con las de antes: leída también.
    assert protein["searched_display"].startswith(ALSO_READ_PREFIX)
    # La subida de las transaminasas es una tendencia sin estadística: dicha, no leída como sentido.
    for key in ("ast", "alt"):
        assert "tendency to increase" in for_indicator(key)["searched"], key
    # Nada de esta ronda es una frase de la Mir ni de Grigor'ev: no hay frase de una tendencia.
    assert not {row["ref"] for row in protein["statements"]} & {
        "markin-1998-blood-biochemistry-mir", "grigoriev-1994-biochemical-status",
    }
    # Lo que solo cambió después del vuelo no se sirve como del vuelo: se dice dónde se buscó.
    crp = for_indicator("c-reactive-protein")
    assert "después del aterrizaje" in crp["searched"]
    assert registry.get("garrett-bakelman-2019").source in crp["searched_sources"]
    assert "más baja después del vuelo, no durante" in for_indicator("albumin")["searched"]
    # La glucosa: lo leído no coincide (tendencia a subir, frase sin toma, RMN a la baja) y nada
    # da un sentido medido; se dice con las tres fichas.
    glucose = for_indicator("glucose")
    assert glucose["searched_sources"] == [
        registry.get(ref).source for ref in (
            "markin-1998-blood-biochemistry-mir", "grigoriev-1994-biochemical-status",
            "stroud-2022-metabolomics-iss",
        )
    ]


# Las fichas que la decimonovena ronda (U7) leyó el 2026-10-31 para la función y la cabina.
READ_IN_U7 = frozenset({
    "tu-2022-pvt-prediction-iss", "dijk-2001-sleep-circadian-shuttle",
    "gundel-1997-sleep-circadian-mir", "monk-1998-sleep-circadian-shuttle",
    "fu-2019-orthostatic-tolerance-iss", "wood-2019-inflight-leg-cuff-iss",
    "lee-2015-orthostatic-intolerance-iss-shuttle", "arbeille-2015-vessel-imaging-iss",
    "pavela-2022-jugular-surveillance-iss", "david-2021-right-ijv-tilt-microgravity",
    "zamboni-2026-jugular-venous-pulse-iss", "strollo-1997-spacelab-adrenal-gonadal",
})


def test_what_the_nineteenth_round_read_for_function_and_cabin() -> None:
    """Lapsos de la PVT, desfase circadiano, caída ortostática y yugular derecha (U7, 2026-10-31).

    Lo que la lectura encontró y no se puede perder sin volver a leer: los cuatro siguen «sin
    fuente», pero ya no por falta de estudios en vuelo, sino porque lo que hay no se lee como
    «sube» ni «baja»: un retraso de fase en horas cuyo signo EMMA no declara; una prueba que en
    ingravidez no existe y su sustituto en vuelo; una serie de una sola persona frente a tumbado;
    y frases de la yugular que no dicen el lado. Buscado y no encontrado no es «no buscado».
    """
    expected_refs = {
        "pvt-lapses": [
            "jones-2022-sleep-pvt-iss", "dev-2024-cognition-iss", "tu-2022-pvt-prediction-iss",
        ],
        "circadian-shift": [
            "flynn-evans-2016-circadian-iss", "gundel-1997-sleep-circadian-mir",
            "monk-1998-sleep-circadian-shuttle", "dijk-2001-sleep-circadian-shuttle",
        ],
        "orthostatic-drop": [
            "baevsky-2007-autonomic-iss", "fu-2019-orthostatic-tolerance-iss",
            "lee-2015-orthostatic-intolerance-iss-shuttle", "wood-2019-inflight-leg-cuff-iss",
        ],
        "ijv-csa-right": [
            "marshall-goebel-2019-ijv", "zamboni-2026-jugular-venous-pulse-iss",
            "arbeille-2015-vessel-imaging-iss", "pavela-2022-jugular-surveillance-iss",
            "david-2021-right-ijv-tilt-microgravity",
        ],
    }
    for key, refs in expected_refs.items():
        found = for_indicator(key)
        assert found["direction"] == NO_SOURCE and found["statements"] == [], key
        assert found["searched_display"].startswith(SEARCHED_PREFIX), key
        assert read()["indicators"][key]["searched_refs"] == refs, key
        # Lo leído este día lleva su fecha; lo leído antes conserva la suya.
        for ref, day in zip(refs, found["searched_read_on"], strict=True):
            assert (day == "2026-10-31") == (ref in READ_IN_U7), (key, ref)
    # El retraso de fase de Gundel 1997 se dice con su frase y no se lee como sentido: un signo
    # no es una subida ni una bajada, y EMMA no declara el suyo.
    circadian = for_indicator("circadian-shift")["searched"]
    assert "delayed by about 2 h in space" in circadian and "signo" in circadian
    # En ingravidez no hay ponerse en pie; el sustituto en vuelo (soltar manguitos) se dice como
    # lo que es: la presión media ante otro estímulo.
    orthostatic = for_indicator("orthostatic-drop")["searched"]
    assert "no hay ponerse en pie" in orthostatic and "manguitos" in orthostatic
    # La única serie en vuelo de la yugular derecha es de una persona y frente a tumbado: dicha,
    # no leída; la izquierda no cambia.
    right = for_indicator("ijv-csa-right")
    assert "in orbit" in right["searched"] and "una persona" in right["searched"]
    assert registry.get("zamboni-2026-jugular-venous-pulse-iss").source in right["searched_sources"]
    assert for_indicator("ijv-csa-left")["direction"] == "rises"
    # Strollo 1997 (Spacelab) se leyó en su resumen, que no da resultados: leído también junto a
    # la LH, que sigue con su única frase de Strollo 1998.
    lh = for_indicator("lh")
    assert lh["direction"] == "rises"
    assert registry.get("strollo-1997-spacelab-adrenal-gonadal").source in lh["searched_sources"]
    assert "no da resultados" in lh["searched"]


def test_the_block_follows_the_profile_order_and_counts_what_it_shows() -> None:
    keys = ["exercise-minutes", "heart-rate", "systolic-bp", "body-weight"]
    block = for_profile(keys)
    assert [row["key"] for row in block["indicators"]] == keys
    assert block["note"] == FRAME
    assert block["statement"] == (
        "4 indicadores analizados: 3 con sentido leído en otros vuelos (baja: 1; sin cambio: 1; "
        "discutido: 1) y 1 sin fuente."
    )
    assert for_profile([])["indicators"] == []


def test_each_shown_sentence_carries_its_source_and_what_it_compares_with() -> None:
    for key in read()["indicators"]:
        for row in for_indicator(key)["statements"]:
            assert row["quote_display"] == f"«{row['quote']}»"
            assert row["source"] == registry.get(row["ref"]).source
            assert row["compared_with_display"].startswith("Frente a: ")
            assert row["direction_display"] == OBSERVED[row["direction"]]
            statement = next(item for item in read()["statements"] if item["id"] == row["id"])
            source = read()["sources"][row["ref"]]
            assert row["read_on"] == statement.get(
                "read_on", source.get("read_on", read()["read_on"])
            )


def test_each_sentence_keeps_the_day_it_was_read() -> None:
    """Crucian 2015: la frase de los leucocitos se leyó el 2026-10-22 en el resumen; las de los
    linfocitos y los neutrófilos, el 2026-10-23 en el texto completo. La fecha es de la frase."""
    def day(key: str) -> set[str]:
        return {row["read_on"] for row in for_indicator(key)["statements"]}

    # La segunda frase de los leucocitos es de la decimonovena ronda (Crucian 2013, el 2026-10-31).
    assert day("leukocytes") == {"2026-10-22", "2026-10-31"}
    assert day("lymphocytes") == day("neutrophils") == {"2026-10-23"}
    # El bloque da la lectura más reciente de lo que enseña.
    assert for_profile(["hrv-sdnn"])["read_on"] == "2026-10-22"
    assert for_profile(["hrv-sdnn", "lymphocytes"])["read_on"] == "2026-10-23"
    # Lo buscado y no encontrado también se leyó un día (Flynn-Evans 2016, el 2026-10-23; las tres
    # fichas de la decimonovena ronda, el 2026-10-31), cada ficha el suyo, y cuenta para el bloque
    # aunque no dé frase.
    circadian = for_indicator("circadian-shift")
    assert circadian["statements"] == []
    assert circadian["searched_read_on"] == ["2026-10-23", "2026-10-31", "2026-10-31", "2026-10-31"]
    assert for_profile(["circadian-shift"])["read_on"] == "2026-10-31"
    assert for_indicator("leukocytes")["searched_read_on"] == []
    # Que Crucian da recuentos y no porcentajes se leyó en el texto completo, el 2026-10-23; y
    # cada ficha de lo leído también lleva su día (Barger 2014, el 22; Jones 2022, el 23).
    # (Buchheim 2019 y Crucian 2013, leídos también, son de la decimonovena ronda.)
    assert for_indicator("neutrophils-percent")["searched_read_on"] == [
        "2026-10-23", "2026-10-31", "2026-10-31",
    ]
    assert for_indicator("sleep-duration")["searched_read_on"] == ["2026-10-22", "2026-10-23"]
    # Y cuánto se leyó de cada una, como en las frases (de los dos, el resumen o parte).
    assert for_indicator("sleep-duration")["searched_extent_text"] == [
        EXTENTS[read()["sources"][ref]["extent"]]
        for ref in read()["indicators"]["sleep-duration"]["searched_refs"]
    ]


def test_the_block_date_is_of_what_it_shows_not_of_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La fecha del fichero no se cuela si lo enseñado se leyó antes; sin nada leído, es la suya."""
    raw = _raw()
    raw["read_on"] = "2099-01-01"
    monkeypatch.setattr(flight_direction, "read", lambda: raw)
    assert for_profile(["neutrophils"])["read_on"] == "2026-10-23"
    assert for_profile([])["read_on"] == "2099-01-01"


# --------------------------------------------------------------------------- #
# Lo que dice: ni «es normal» ni una orden
# --------------------------------------------------------------------------- #


def _texts(found: dict[str, Any]) -> list[str]:
    texts = [found["text"], found["direction_display"]]
    texts += [found[name] for name in ("scope", "searched_display") if found[name]]
    for row in found["statements"]:
        texts += [row["quote_display"], row["compared_with_display"], row["population"],
                  row["where"]]
    return texts


def test_every_text_passes_the_guard_and_none_says_it_is_to_be_expected() -> None:
    texts = [FRAME, for_profile(list(CATALOG))["statement"], *DIRECTION_DISPLAY.values()]
    for key in CATALOG:
        texts += _texts(for_indicator(key))
    for text in texts:
        assert check(text) == [], text
        plain = text.lower()
        for said in ("es normal", "lo normal", "esperable", "es de esperar", "como se espera"):
            assert said not in plain, text
    assert "no lo esperado en esta persona" in FRAME


# --------------------------------------------------------------------------- #
# El cargador rechaza lo que no se sostiene
# --------------------------------------------------------------------------- #


def _break_literal_not_in_quote(raw: dict[str, Any]) -> None:
    _statement(raw, "sirek-2014-onsd")["literal"] = "ONSD decreased"


def _break_literal_without_its_direction(raw: dict[str, Any]) -> None:
    _statement(raw, "sirek-2014-onsd")["literal"] = "ONSD"


def _break_literal_with_two_directions(raw: dict[str, Any]) -> None:
    item = _statement(raw, "xu-2013-hr-sleep")
    item["literal"] = "HR was unchanged inflight and elevated postflight"


def _break_literal_after_flight(raw: dict[str, Any]) -> None:
    """El error del simulador, escrito como dato: la subida de después, servida como del vuelo."""
    item = _statement(raw, "xu-2013-hr-sleep")
    item["direction"], item["literal"] = "rises", "elevated postflight"
    raw["indicators"]["heart-rate"]["statements"] = ["xu-2013-hr-sleep"]
    raw["indicators"]["heart-rate"]["direction"] = "rises"


def _break_searched_without_card(raw: dict[str, Any]) -> None:
    del raw["indicators"]["cortisol-salivary"]["searched_refs"]


def _break_searched_card_unread(raw: dict[str, Any]) -> None:
    raw["indicators"]["hemoglobin"]["searched_refs"] = ["osd-288"]


def _break_idle_source(raw: dict[str, Any]) -> None:
    raw["sources"]["law-2014"] = {"extent": "partial", "what": "el resumen"}


def _break_quote_not_in_flight(raw: dict[str, Any]) -> None:
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = item["literal"] = "ONSD increased relative to before"


def _break_animal_source(raw: dict[str, Any]) -> None:
    raw["sources"]["osd-288"] = {"extent": "partial", "what": "metadatos"}
    _statement(raw, "sirek-2014-onsd")["ref"] = "osd-288"


def _break_unread_source(raw: dict[str, Any]) -> None:
    del raw["sources"]["sirek-2014-onsd-iss"]


def _break_no_comparison(raw: dict[str, Any]) -> None:
    _statement(raw, "sirek-2014-onsd")["compared_with"] = " "


def _break_contested_that_agrees(raw: dict[str, Any]) -> None:
    raw["indicators"]["hrv-sdnn"]["statements"] = ["xu-2013-hrv-sleep"]


def _break_direction_its_sentences_do_not_say(raw: dict[str, Any]) -> None:
    raw["indicators"]["heart-rate"]["direction"] = "rises"


def _break_direction_without_sentence(raw: dict[str, Any]) -> None:
    raw["indicators"]["glucose"] = {"direction": "rises", "statements": []}


def _break_no_source_with_sentences(raw: dict[str, Any]) -> None:
    raw["indicators"]["leukocytes"] = {
        "direction": NO_SOURCE, "statements": ["crucian-2015-wbc"], "searched": "x",
    }


def _break_no_source_without_where(raw: dict[str, Any]) -> None:
    del raw["indicators"]["mcv"]["searched"]


def _break_searched_with_sentence(raw: dict[str, Any]) -> None:
    """Junto a un sentido, lo leído también necesita su ficha como lo buscado."""
    raw["indicators"]["leukocytes"]["searched"] = "x"


def _break_also_read_without_text(raw: dict[str, Any]) -> None:
    del raw["indicators"]["hemoglobin"]["searched"]


def _break_also_read_card_unread(raw: dict[str, Any]) -> None:
    raw["indicators"]["hemoglobin"]["searched_refs"] = ["osd-288"]


def _break_speed_undeclared(raw: dict[str, Any]) -> None:
    """«Slower» sin declararse de rapidez no dice con las palabras de siempre que suba."""
    del _statement(raw, "dev-2024-pvt-early-flight")["reads_speed"]


def _break_speed_for_another_indicator(raw: dict[str, Any]) -> None:
    raw["indicators"]["pvt-lapses"] = {
        "direction": "rises", "statements": ["dev-2024-pvt-early-flight"],
    }


def _break_speed_with_value_words(raw: dict[str, Any]) -> None:
    """«Reduced speed»: con palabras del valor, la rapidez no se puede leer."""
    item = _statement(raw, "dev-2024-pvt-early-flight")
    item["quote"] = "Slower and reduced performance on the PVT was observed during early flight."
    item["literal"] = "Slower and reduced performance"


def _break_speed_says_faster(raw: dict[str, Any]) -> None:
    item = _statement(raw, "dev-2024-pvt-early-flight")
    item["quote"] = "Slower then faster performance on the PVT was observed during early flight."
    item["literal"] = "Slower then faster performance"


def _break_speed_not_a_flag(raw: dict[str, Any]) -> None:
    _statement(raw, "dev-2024-pvt-early-flight")["reads_speed"] = "sí"


def _break_source_date(raw: dict[str, Any]) -> None:
    raw["sources"]["dev-2024-cognition-iss"]["read_on"] = "hoy"


def _break_statement_date(raw: dict[str, Any]) -> None:
    _statement(raw, "crucian-2015-lymphocytes")["read_on"] = "ayer"


def _break_speed_unflagged_value_word(raw: dict[str, Any]) -> None:
    """«Reduced response speed» sin declararse de rapidez diría que el tiempo baja."""
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = "Reduced response speed was observed during flight."
    item["literal"] = "Reduced response speed"
    item["direction"] = "falls"
    raw["indicators"]["onsd-right"] = raw["indicators"]["onsd-left"] = {
        "direction": "falls", "statements": ["sirek-2014-onsd"],
    }


def _break_speed_plural_unflagged(raw: dict[str, Any]) -> None:
    """«Response speeds decreased»: «speeds» también habla de rapidez."""
    _break_speed_unflagged_value_word(raw)
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = item["literal"] = "Response speeds decreased during flight"


def _break_negated_word(raw: dict[str, Any]) -> None:
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = item["literal"] = "ONSD was not increased during flight"


def _break_negated_after_the_word(raw: dict[str, Any]) -> None:
    """La negación detrás de la palabra («increased, but not significantly») también cuenta."""
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = item["literal"] = "ONSD increased, but not significantly, during flight"


def _break_negated_by_failing(raw: dict[str, Any]) -> None:
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = item["literal"] = "ONSD failed to increase during flight"


def _break_negated_far_from_the_word(raw: dict[str, Any]) -> None:
    """«not ~16% higher»: un número entre la negación y la palabra no la esconde."""
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = item["literal"] = "ONSD was not ~16% or more higher during flight"


def _break_negated_unchanged(raw: dict[str, Any]) -> None:
    """«not unaltered» es lo contrario de «sin cambio»."""
    item = _statement(raw, "crucian-2015-lymphocytes")
    item["quote"] = item["literal"] = "lymphocytes were not unaltered during flight"


def _break_compact_date(raw: dict[str, Any]) -> None:
    """«20991231» pasa por `fromisoformat` y, ordenada como texto, no sería la más reciente."""
    raw["sources"]["dev-2024-cognition-iss"]["read_on"] = "20991231"


def _break_ground_analog(raw: dict[str, Any]) -> None:
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = "ONSD increased with simulated microG relative to before."
    item["literal"] = "ONSD increased"


def _break_literal_return_day(raw: dict[str, Any]) -> None:
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = "ONSD increased at R+0 relative to values in flight."
    item["literal"] = "ONSD increased at R+0"


def _break_negated_just_before_the_literal(raw: dict[str, Any]) -> None:
    """«was not» justo fuera del literal le da la vuelta igual."""
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = "ONSD was not increased during flight relative to before flight"
    item["literal"] = "increased during flight"


def _break_literal_before_flight(raw: dict[str, Any]) -> None:
    item = _statement(raw, "sirek-2014-onsd")
    item["quote"] = "ONSD increased at L-10 compared with in flight."
    item["literal"] = "ONSD increased at L-10"


def _break_reaction_time_from_performance(raw: dict[str, Any]) -> None:
    """«PVT performance decreased» no dice que el tiempo baje: dice que empeoró."""
    item = _statement(raw, "dev-2024-pvt-early-flight")
    item["reads_speed"] = False
    item["direction"] = "falls"
    item["quote"] = item["literal"] = "PVT performance decreased during early flight"
    raw["indicators"]["pvt-mean-rt"]["direction"] = "falls"


def _break_repeated_searched_card(raw: dict[str, Any]) -> None:
    refs = raw["indicators"]["hemoglobin"]["searched_refs"]
    refs.append(refs[0])


def _break_also_read_gives_the_sentence(raw: dict[str, Any]) -> None:
    raw["indicators"]["hemoglobin"]["searched_refs"].append("kunz-2017-hematologic-indices-iss")


def _break_unknown_indicator(raw: dict[str, Any]) -> None:
    raw["indicators"]["no-existe"] = raw["indicators"].pop("leukocytes")


def _break_unused_sentence(raw: dict[str, Any]) -> None:
    del raw["indicators"]["leukocytes"]


def _break_no_date(raw: dict[str, Any]) -> None:
    raw["read_on"] = "ayer"


def _break_observed_word_as_sentence_direction(raw: dict[str, Any]) -> None:
    _statement(raw, "sirek-2014-onsd")["direction"] = CONTESTED


def _break_no_difference_with_a_rise(raw: dict[str, Any]) -> None:
    """«No significant differences» es la frase de «sin cambio»: junto a una subida, son dos."""
    item = _statement(raw, "zwart-2022-total-protein")
    item["quote"] = item["literal"] = (
        "No significant differences were detected early, but total protein increased during flight"
    )


def _break_no_difference_between_groups(raw: dict[str, Any]) -> None:
    """«No differences among groups» compara grupos, no el vuelo con antes: no es «sin cambio»."""
    item = _statement(raw, "zwart-2022-total-protein")
    item["literal"] = "no differences were detected among groups"


def _break_group_just_after_the_literal(raw: dict[str, Any]) -> None:
    """La comparación entre grupos justo fuera del literal, en su misma oración, también cuenta."""
    item = _statement(raw, "zwart-2022-total-protein")
    item["quote"] = (
        "No significant differences were detected among countermeasure groups during flight"
    )
    item["literal"] = "No significant differences were detected"


def _break_rise_between_groups(raw: dict[str, Any]) -> None:
    """Una subida entre grupos tampoco es un cambio en el tiempo."""
    item = _statement(raw, "smith-2015-serum-magnesium")
    item["quote"] = item["literal"] = "Serum magnesium was higher among women late in flight"


def _break_literal_after_space_flight(raw: dict[str, Any]) -> None:
    """«After space flight», en dos palabras, es después del vuelo."""
    item = _statement(raw, "smith-2015-serum-magnesium")
    item["quote"] = "Measured in flight; serum magnesium increased after space flight"
    item["literal"] = "serum magnesium increased after space flight"


def _break_literal_post_space_flight(raw: dict[str, Any]) -> None:
    """Y «post space flight», también."""
    item = _statement(raw, "smith-2015-serum-magnesium")
    item["quote"] = "Measured in flight; serum magnesium increased post space flight"
    item["literal"] = "serum magnesium increased post space flight"


def _break_negated_no_difference(raw: dict[str, Any]) -> None:
    """Quitada la frase de «sin cambio», otra negación sigue sin dejarla leer."""
    item = _statement(raw, "zwart-2022-total-protein")
    item["quote"] = item["literal"] = (
        "No significant differences were not detected for total protein during flight"
    )


BREAKS = {
    "literal fuera de la frase": (_break_literal_not_in_quote, "no está escrito"),
    "literal sin su sentido": (_break_literal_without_its_direction, "no dice que sube"),
    "literal con dos sentidos": (_break_literal_with_two_directions, "dice también"),
    "frase que no es de vuelo": (_break_quote_not_in_flight, "en vuelo"),
    "literal de después del vuelo": (_break_literal_after_flight, "después del vuelo"),
    "buscado sin ficha": (_break_searched_without_card, "sin su ficha"),
    "buscado con ficha sin lectura": (_break_searched_card_unread, "cuánto se leyó"),
    "ficha declarada que nada usa": (_break_idle_source, "ninguna frase ni búsqueda"),
    "fuente con ratones": (_break_animal_source, "solo en personas"),
    "fuente sin lectura declarada": (_break_unread_source, "cuánto se leyó"),
    "sin comparación": (_break_no_comparison, "compared_with"),
    "discutido que coincide": (_break_contested_that_agrees, "no coincidan"),
    "sentido que sus frases no dicen": (_break_direction_its_sentences_do_not_say, "no dicen"),
    "sentido sin frase": (_break_direction_without_sentence, "sin fuente"),
    "sin fuente con frases": (_break_no_source_with_sentences, "con frases"),
    "sin fuente sin dónde": (_break_no_source_without_where, "dónde se buscó"),
    "leído también sin ficha": (_break_searched_with_sentence, "sin su ficha"),
    "leído también sin decir qué": (_break_also_read_without_text, "qué dice"),
    "leído también con ficha sin lectura": (_break_also_read_card_unread, "cuánto se leyó"),
    "rapidez sin declarar": (_break_speed_undeclared, "no dice que sube"),
    "rapidez en otro indicador": (_break_speed_for_another_indicator, "tiempo de reacción"),
    "rapidez con palabras del valor": (_break_speed_with_value_words, "mezcla"),
    "rapidez con dos sentidos": (_break_speed_says_faster, "dice también"),
    "rapidez sin bandera": (_break_speed_not_a_flag, "verdadero o falso"),
    "fecha de fuente mala": (_break_source_date, "no es una fecha"),
    "fecha de frase mala": (_break_statement_date, "no es una fecha"),
    "rapidez sin declarar con palabra del valor": (
        _break_speed_unflagged_value_word, "rapidez sin declararlo",
    ),
    "rapidez en plural sin declarar": (_break_speed_plural_unflagged, "rapidez sin declararlo"),
    "palabra de sentido negada": (_break_negated_word, "niega"),
    "negación detrás de la palabra": (_break_negated_after_the_word, "niega"),
    "negación por no lograr": (_break_negated_by_failing, "niega"),
    "negación lejos de la palabra": (_break_negated_far_from_the_word, "niega"),
    "sin cambio negado": (_break_negated_unchanged, "niega"),
    "fecha compacta": (_break_compact_date, "AAAA-MM-DD"),
    "análogo en tierra": (_break_ground_analog, "análogo"),
    "literal del día del regreso": (_break_literal_return_day, "después del vuelo"),
    "leído también que da la frase": (_break_also_read_gives_the_sentence, "a la vez"),
    "negación justo antes del literal": (_break_negated_just_before_the_literal, "niega"),
    "literal de antes del vuelo": (_break_literal_before_flight, "antes del vuelo"),
    "tiempo de reacción leído del rendimiento": (
        _break_reaction_time_from_performance, "nombre el tiempo",
    ),
    "ficha repetida en lo buscado": (_break_repeated_searched_card, "repetida"),
    "indicador desconocido": (_break_unknown_indicator, "catálogo"),
    "frase sin indicador": (_break_unused_sentence, "ningún indicador"),
    "sin fecha": (_break_no_date, "read_on"),
    "frase discutida": (_break_observed_word_as_sentence_direction, "no cambia"),
    "sin diferencia junto a una subida": (_break_no_difference_with_a_rise, "dice también"),
    "sin diferencia entre grupos": (_break_no_difference_between_groups, "compara grupos"),
    "grupos justo después del literal": (_break_group_just_after_the_literal, "compara grupos"),
    "subida entre grupos": (_break_rise_between_groups, "compara grupos"),
    "literal de después del vuelo en dos palabras": (
        _break_literal_after_space_flight, "después del vuelo",
    ),
    "literal de «post space flight»": (_break_literal_post_space_flight, "después del vuelo"),
    "sin diferencia negada": (_break_negated_no_difference, "niega"),
}


@pytest.mark.parametrize("literal", [
    # Compara momentos, no grupos: es un «sin cambio» en el tiempo.
    "No significant differences between preflight and inflight values were detected",
    "No significant differences between study phases were detected for total protein during flight",
    # Con «statistically», sigue siendo la frase de «sin cambio», no una negación suelta.
    "No statistically significant differences were detected for total protein during flight",
])
def test_an_unchanged_over_time_is_read(literal: str) -> None:
    raw = _raw()
    item = _statement(raw, "zwart-2022-total-protein")
    item["quote"] = item["literal"] = literal
    validate(raw)


@pytest.mark.parametrize("label", sorted(BREAKS))
def test_the_loader_rejects_what_the_source_does_not_sustain(label: str) -> None:
    breaker, reason = BREAKS[label]
    raw = _raw()
    validate(copy.deepcopy(raw))  # lo de verdad pasa
    breaker(raw)
    with pytest.raises(FlightDirectionError, match=reason):
        validate(raw)


# --------------------------------------------------------------------------- #
# Nada del estado lo lee
# --------------------------------------------------------------------------- #


def test_the_module_reads_no_engine_and_nothing_of_the_state_reads_it() -> None:
    tree = ast.parse(Path(flight_direction.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app")
    }
    assert imported == {"app.core", "app.evidence", "app.evidence.instruments_read",
                        "app.evidence.read_contract", "app.ingest.codes"}
    readers = sorted(
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if "flight_direction" in path.read_text(encoding="utf-8")
        and path != Path(flight_direction.__file__)
    )
    # Solo la ruta del perfil de línea base: ni el análisis, ni el consejero, ni el estado. El
    # arranque valida el fichero (`main.check_read_files`) y el contrato común lo nombra en su
    # explicación; ninguno de los dos usa lo que dice.
    assert readers == ["api/baseline_profile.py", "evidence/read_contract.py", "main.py"]
