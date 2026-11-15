"""Lo leído sobre la PVT y las escalas de autoinforme (`app/evidence/instruments_read.py`).

Cada valor publicado va con la frase que lo sostiene, lo que EMMA puntúa no se ha movido, y la
prueba de la consola no toma el nombre de una prueba publicada que no es. Sin red: lo leído
está en `app/data/instruments_read.json`.
"""

import copy
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import diary, pvt_console
from app.api.pvt_console import FOREPERIOD_MAX_MS, FOREPERIOD_MIN_MS, SESSION_TRIALS
from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.evidence import instruments_read, registry
from app.evidence.instruments_read import InstrumentsError, validate
from app.evidence.registry import RegistryError
from app.ingest import pvt
from app.ingest.codes import CATALOG
from app.main import app

RAW: dict[str, Any] = json.loads(instruments_read.READ_PATH.read_text(encoding="utf-8"))

# Lo que puntúa una prueba. Si una de estas cambia, cambia el indicador de lapsos que el
# análisis vigila (invariante 5): no se toca en una unidad que solo lee fuentes.
SCORING = {"LAPSE_THRESHOLD_MS": 500.0, "FALSE_START_THRESHOLD_MS": 100.0, "MIN_TRIALS": 10}

# Un mismo conjunto de tiempos y su puntuación, calculada con el código anterior a la lectura.
TIMES = [
    0.0, 99.9, 100.0, 180.0, 245.5, 260.0, 280.0, 300.0, 354.9, 355.0,
    356.0, 420.0, 499.9, 500.0, 500.1, 640.0, 910.0, 1500.0, 30000.0, 310.0,
]
SCORED = {
    "trials": 20,
    "valid_trials": 18,
    "mean_rt_ms": 2095.08,
    "median_rt_ms": 355.5,
    "slowest_10pct_mean_ms": 30000.0,
    "lapses": 5,
    "lapse_rate": 0.2778,
    "false_starts": 2,
    "response_speed": 2.9884,
}


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _protocol(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/pvt/protocol")
    assert response.status_code == 200
    return response.json()


def _by_key(client: TestClient) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in _protocol(client)["parameters"]}


def _broken(change: Any) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    change(raw)
    return raw


# --------------------------------------------------------------------------- #
# Invariante 5: lo que puntúa no se ha movido
# --------------------------------------------------------------------------- #


def test_no_scoring_value_changed() -> None:
    for name, value in SCORING.items():
        assert getattr(pvt, name) == value, name


def test_the_same_times_score_exactly_as_before() -> None:
    assert pvt.score(TIMES).to_dict() == SCORED


def test_a_submitted_test_scores_the_same_through_the_route(client: TestClient) -> None:
    response = client.post("/api/pvt", json={"reaction_times_ms": TIMES})
    assert response.status_code == 201
    assert response.json()["result"] == SCORED


def test_emma_counts_lapses_with_the_ten_minute_threshold_and_strictly() -> None:
    """La diferencia que el panel declara es la que el código tiene, ni más ni menos."""
    # Entre el umbral de la versión breve y el de EMMA no hay lapso.
    assert pvt.score([400.0] * 10).lapses == 0
    # Exactamente en el umbral tampoco: EMMA compara con «mayor que», las fuentes con «≥».
    assert pvt.score([pvt.LAPSE_THRESHOLD_MS] * 10).lapses == 0
    assert pvt.score([pvt.LAPSE_THRESHOLD_MS + 0.1] * 10).lapses == 10
    # La salida en falso sí coincide: por debajo de 100 ms, y 100 ms ya es válida.
    assert pvt.score([99.9] + [300.0] * 9).false_starts == 1
    assert pvt.score([100.0] + [300.0] * 9).false_starts == 0


def test_describing_the_sources_does_not_move_the_verdict(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "progressive-insomnia", "days": 30}
    ).status_code == 201

    def verdict() -> tuple[Any, Any, Any]:
        status = client.get("/api/status").json()
        return status["domains"], status["alerts"], status["rules_version"]

    before = verdict()
    assert before[1], "el escenario tiene que alertar para que la comparación diga algo"
    assert client.get("/api/pvt/protocol").status_code == 200
    assert client.get("/api/diary").status_code == 200
    assert verdict() == before


# --------------------------------------------------------------------------- #
# Lo leído: cada valor con su frase
# --------------------------------------------------------------------------- #


def test_what_was_read_loads_and_every_source_is_registered() -> None:
    read = instruments_read.read()
    assert read["read_on"] == "2026-10-13"
    assert instruments_read.cited_refs() == set(read["sources"])
    for ref_id, source in read["sources"].items():
        ref = registry.get(ref_id)
        # Los artículos, en PubMed Central; las normas, en nasa.gov; desde el 2026-10-16, las
        # medidas de los indicadores descriptivos también en el Human Research Roadmap y NTRS; desde
        # el 2026-11-04, el glucómetro en los CDC y en MedlinePlus; desde el 2026-11-14, las
        # palabras de las escalas del ciclo en la documentación de HealthKit de Apple y en la de
        # Health Connect de Android (lote ciclo).
        assert ref.url and ref.url.startswith((
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC", "https://www.nasa.gov/",
            "https://humanresearchroadmap.nasa.gov/", "https://ntrs.nasa.gov/citations/",
            "https://www.cdc.gov/", "https://medlineplus.gov/",
            "https://developer.apple.com/documentation/healthkit/",
            "https://developer.android.com/reference/kotlin/androidx/health/connect/",
        ))
        # Cuándo se leyó lo que se cita de ella lo dice su ficha (desde la primera lectura, la
        # del 2026-10-13) o, para las leídas después, su ficha o lo que se declara leído.
        dates = {read["read_on"]} | {
            item.get("read_on", read["read_on"])
            for item in read["statements"] if item["ref"] == ref_id
        }
        assert ref.notes and any(date in ref.notes + source["what"] for date in dates), ref_id
    # Toda frase la usa alguien: una frase guardada que nadie enseña no se ha contrastado.
    used = instruments_read._pvt_statement_ids()
    for key, scale in read["scales"].items():
        used |= instruments_read.scale_statement_ids(key)
        if "criterion" in scale:
            used.add(scale["criterion"]["statement"])
    for measure in read["measures"].values():
        used |= set(measure["statements"])
    assert used == {item["id"] for item in read["statements"]}


def test_every_published_value_is_written_in_its_own_quote(client: TestClient) -> None:
    for key, item in _by_key(client).items():
        for value in item["published"]["values"]:
            statement = value["statement"]
            assert value["literal"] in statement["quote"], key
            assert statement["where"] and statement["url"] and statement["read_on"]
            assert statement["extent_text"] in instruments_read.EXTENTS.values()


def test_the_two_published_tests_are_not_mixed(client: TestClient) -> None:
    """La prueba de 10 minutos y la breve dan valores distintos, y cada uno va con su versión."""
    by_key = _by_key(client)

    def published(key: str) -> dict[str, Any]:
        return {item["variant"]: item for item in by_key[key]["published"]["values"]}

    lapse = published("lapse_threshold_ms")
    assert (lapse["pvt-10"]["value_ms"], lapse["pvt-b"]["value_ms"]) == (500, 355)
    assert "500" in lapse["pvt-10"]["literal"] and "355" in lapse["pvt-b"]["literal"]
    assert "PVT-B" in lapse["pvt-b"]["statement"]["quote"]
    wait = published("foreperiod_ms")
    assert wait["pvt-10"]["value_ms"] == [2000, 10000]
    assert wait["pvt-b"]["value_ms"] == [1000, 4000]
    assert "2–10 s" in wait["pvt-10"]["statement"]["quote"]
    assert "1–4 s" in wait["pvt-b"]["statement"]["quote"]
    assert wait["pvt-10"]["statement"]["id"] != wait["pvt-b"]["statement"]["id"]
    duration = published("trials")
    assert (duration["pvt-10"]["value_ms"], duration["pvt-b"]["value_ms"]) == (600000, 180000)
    # El límite que el propio artículo declara del umbral breve va al lado, no se calla.
    also = {item["id"] for item in by_key["lapse_threshold_ms"]["published"]["see_also"]}
    assert {"pvtb-lapse-355-limit", "pvtb-fewer-lapses"} <= also


def test_each_parameter_says_how_emma_compares(client: TestClient) -> None:
    by_key = _by_key(client)
    status = {key: item["published"]["status"] for key, item in by_key.items()}
    assert status == {
        "lapse_threshold_ms": "same_figure_different_operator",
        "false_start_threshold_ms": "same_value",
        "min_trials": "not_published",
        "trials": "not_comparable",
        "foreperiod_ms": "same_value",
        "abandon_after_ms": "different_value",
    }
    # El «mismo valor» se calcula contra el valor de EMMA, y dice de qué versión es. En el
    # lapso la cifra es la de la prueba de 10 minutos, pero el operador no (≥ frente a >).
    lapse = by_key["lapse_threshold_ms"]["published"]
    assert [item["same"] for item in lapse["values"]] == [False, False]
    assert [item["same_figure"] for item in lapse["values"]] == [True, False]
    assert lapse["values"][0]["value_ms"] == pvt.LAPSE_THRESHOLD_MS
    assert lapse["status_display"] == "misma cifra, distinto operador que PVT de 10 minutos"
    wait = by_key["foreperiod_ms"]["published"]
    assert wait["values"][0]["value_ms"] == [FOREPERIOD_MIN_MS, FOREPERIOD_MAX_MS]
    assert [item["same"] for item in wait["values"]] == [True, False]
    false_start = by_key["false_start_threshold_ms"]["published"]
    assert false_start["values"][0]["value_ms"] == pvt.FALSE_START_THRESHOLD_MS
    assert by_key["abandon_after_ms"]["published"]["values"][0]["value_ms"] == 30000
    assert by_key["min_trials"]["published"]["values"] == []
    # Y cada uno dice, con palabras de EMMA, en qué difiere.
    for item in by_key.values():
        assert item["published"]["difference"].strip()
    assert "«≥»" in lapse["difference"] and "no se ha cambiado" in lapse["difference"]
    assert "no se envía nada" in by_key["abandon_after_ms"]["published"]["difference"]


def test_only_the_scoring_values_are_marked_as_scoring(client: TestClient) -> None:
    scoring = {key for key, item in _by_key(client).items() if item["scores"]}
    assert scoring == {"lapse_threshold_ms", "false_start_threshold_ms", "min_trials"}


def test_a_design_value_that_matches_the_source_says_so_and_the_rest_stay_design(
    client: TestClient,
) -> None:
    basis = {key: item["basis"] for key, item in _by_key(client).items()}
    assert basis == {
        "lapse_threshold_ms": "repository",
        "false_start_threshold_ms": "read",
        "min_trials": "design",
        "trials": "design",
        "foreperiod_ms": "read",
        "abandon_after_ms": "design",
    }
    for item in _by_key(client).values():
        if item["basis"] == "read":
            assert item["basis_display"] == pvt_console.DESIGN_MATCHES
            assert "sin fuente leída" not in item["basis_display"]


def test_the_console_test_does_not_take_the_name_of_a_published_one(client: TestClient) -> None:
    protocol = _protocol(client)
    assert "PVT-B" not in protocol["title"] and "breve" not in protocol["title"]
    identity = protocol["identity"]
    assert identity.startswith("No es ninguna de las pruebas publicadas")
    assert "(PVT de 10 minutos; PVT-B de 3 minutos)" in identity
    assert instruments_read.pvt_tests() == ["PVT de 10 minutos", "PVT-B de 3 minutos"]
    assert f"{SESSION_TRIALS} estímulos" in identity
    assert "500 ms" in identity and "no el de la versión breve" in identity
    # Lo que la frase afirma sigue siendo cierto: la espera y el umbral son los de 10 minutos.
    by_key = {item["key"]: item for item in protocol["parameters"]}
    # La frase habla de la cifra del umbral; su operador es otro (`test_pvt_divergences.py`).
    for key in ("foreperiod_ms", "lapse_threshold_ms"):
        same = [v["variant"] for v in by_key[key]["published"]["values"] if v["same_figure"]]
        assert same == ["pvt-10"], key
    # Fuera de lo leído y de esa frase, ningún texto de la prueba nombra la versión breve.
    own = {
        key: value for key, value in protocol.items()
        if key not in {"identity", "published", "divergences"}
    }
    for item in own["parameters"]:
        item.pop("published")
    assert "pvt-b" not in json.dumps(own, ensure_ascii=False).lower()
    # Las divergencias (2026-10-14) la nombran solo al citar: en su frase y en lo publicado,
    # nunca en lo que dicen de EMMA.
    for item in protocol["divergences"]["items"]:
        assert "pvt-b" not in " ".join((item["emma"], item["kept"])).lower()


def test_what_was_read_about_the_study_and_what_was_not_found(client: TestClient) -> None:
    published = _protocol(client)["published"]
    assert published["read_on"] == "2026-10-13"
    # Solo los documentos de la prueba: el de la escala de alimentos no es una fuente de esto.
    assert [item["ref"] for item in published["sources"]] == [
        "basner-2011-pvt-b", "basner-2011-pvt-metrics",
    ]
    for source in published["sources"]:
        assert source["extent"] == "partial" and source["what"]
    context = {item["id"]: item for item in published["context"]}
    assert "74 healthy subjects" in context["pvtb-population"]["quote"]
    assert "still needs to be established" in context["pvtb-applied-pending"]["quote"]
    assert any("mínimo de estímulos" in line for line in published["not_found"])
    assert any("manuscrito de autor" in line for line in published["not_found"])
    assert "no la registra" in published["outcomes_note"]
    assert "no ha cambiado ningún valor" in published["note"]


# --------------------------------------------------------------------------- #
# El cargador rechaza lo que no se puede sostener
# --------------------------------------------------------------------------- #


def test_the_file_as_written_is_valid() -> None:
    assert validate(copy.deepcopy(RAW)) == RAW


def _first_published(raw: dict[str, Any]) -> dict[str, Any]:
    published: dict[str, Any] = raw["pvt"]["parameters"]["lapse_threshold_ms"]["published"][1]
    return published


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda raw: raw.pop("read_on"), "read_on"),
        (lambda raw: raw["statements"][0].update(where=" "), "falta `where`"),
        (lambda raw: raw["statements"][0].update(quote=""), "falta `quote`"),
        (lambda raw: raw["sources"].pop("basner-2011-pvt-metrics"), "cuánto se leyó"),
        (lambda raw: raw["sources"]["basner-2011-pvt-b"].update(extent="todo"), "cuánto se leyó"),
        (lambda raw: raw["sources"]["basner-2011-pvt-b"].update(what=""), "cuánto se leyó"),
        (lambda raw: raw["statements"].append(dict(raw["statements"][0])), "repetido"),
        # Un valor que su frase no dice: «355» junto a la cita de los 500 ms.
        (lambda raw: _first_published(raw).update(statement="pvt10-lapse-500"), "no está escrito"),
        (lambda raw: _first_published(raw).update(literal=""), "no está escrito"),
        (lambda raw: _first_published(raw).update(statement="inventada"), "ninguna frase leída"),
        (lambda raw: _first_published(raw).update(variant="pvt-5"), "qué versión"),
        (lambda raw: _first_published(raw).update(value_ms=None), "value_ms"),
        (lambda raw: _first_published(raw).update(value_ms=[4000, 1000]), "por debajo del máximo"),
        (lambda raw: raw["pvt"]["context"].append("inventada"), "no es una frase leída"),
        (
            lambda raw: raw["pvt"]["parameters"]["trials"]["see_also"].append("inventada"),
            "no es una frase leída",
        ),
        (lambda raw: raw["pvt"]["not_found"].append(" "), "not_found"),
    ],
)
def test_the_loader_rejects_what_cannot_be_held(change: Any, message: str) -> None:
    with pytest.raises(InstrumentsError, match=message):
        validate(_broken(change))


def test_the_loader_rejects_a_source_that_is_not_registered_or_not_official(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unregistered(raw: dict[str, Any]) -> None:
        raw["sources"]["no-existe"] = {"extent": "full", "what": "x"}

    # Con el error del cargador y el motivo del registro (el contrato común, `read_contract`).
    with pytest.raises(InstrumentsError, match="no-existe: .*no está en el registro") as caught:
        validate(_broken(unregistered))
    assert isinstance(caught.value.__cause__, RegistryError)
    # Una ficha del registro cuya dirección no es la revista ni PubMed Central no sirve.
    monkeypatch.setattr(
        instruments_read, "OFFICIAL_HOSTS", frozenset({"www.nasa.gov"})
    )
    with pytest.raises(InstrumentsError, match="no es la revista"):
        validate(copy.deepcopy(RAW))


# --------------------------------------------------------------------------- #
# Las escalas de autoinforme
# --------------------------------------------------------------------------- #


def _scales(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/diary")
    assert response.status_code == 200
    return {
        item["key"]: item["scale"]
        for item in response.json()["indicators"]
        if item["scale"] is not None
    }


def test_the_hedonic_scale_has_the_nine_labels_that_were_read(client: TestClient) -> None:
    scale = _scales(client)["food-acceptability"]
    assert scale["labels_status"] == "read"
    # En el idioma de la fuente y sin traducir. Los extremos, de NASA hoy (2025); del 2 al 8,
    # del informe de JSC de 1981 (leído el 2026-10-20), con su «or» donde se espera «nor».
    assert scale["labels_language"] == "en"
    assert [(item["value"], item["label"]) for item in scale["labels"]] == [
        (1, "Dislike Extremely"), (2, "Dislike Very Much"), (3, "Dislike Moderately"),
        (4, "Dislike Slightly"), (5, "Neither Like or Dislike"), (6, "Like Slightly"),
        (7, "Like Moderately"), (8, "Like Very Much"), (9, "Like Extremely"),
    ]
    for item in scale["labels"]:
        statement = item["statement"]
        assert statement["where"]
        if item["value"] in (1, 9):
            assert f"{item['value']} = {item['label']}" in statement["quote"]
            assert statement["ref"] == "douglas-2025-iss-food-acceptability"
            assert statement["url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC12611640/"
            assert statement["read_on"] == "2026-10-13"
        else:
            # La fuente pone un punto por línea: «8-Like Very Much».
            assert f"{item['value']}-{item['label']}" in statement["quote"]
            assert statement["ref"] == "ahmed-1981-high-density-foods"
            assert statement["url"] == "https://ntrs.nasa.gov/citations/19820015234"
            assert statement["read_on"] == "2026-10-20"
    # La nota dice de dónde sale cada rótulo y que los intermedios no son la papeleta de hoy.
    assert "no se traducen" in scale["labels_note"]
    assert "1981" in scale["labels_note"] and "no los de la papeleta" in scale["labels_note"]
    assert "con «or»" in scale["labels_note"]
    assert any("Peryam y Pilgrim" in line for line in scale["labels_not_found"])
    assert any(line.startswith("Búsqueda del 2026-10-20") for line in scale["labels_not_found"])
    assert [item["ref"] for item in scale["labels_sources"]] == [
        "douglas-2025-iss-food-acceptability", "ahmed-1981-high-density-foods",
        "massa-2015-leafy-greens-iss",
    ]
    see_also = {item["id"]: item for item in scale["labels_see_also"]}
    assert list(see_also) == [
        "hedonic-anchors-crew", "hedonic-labels-iss-2025-legend", "hedonic-labels-jsc-2015",
    ]
    # Búsqueda de la papeleta de hoy (2026-10-21): no está publicada. Lo leído más reciente dice
    # «nor» en el punto 5, y se enseña junto a los rótulos sin sustituirlos: la leyenda de 2025
    # no numera y el artículo de 2015 numera con mayúsculas desiguales.
    legend = see_also["hedonic-labels-iss-2025-legend"]
    assert "Neither Like Nor Dislike" in legend["quote"] and legend["read_on"] == "2026-10-21"
    assert not any(char.isdigit() for char in legend["quote"])
    panel = see_also["hedonic-labels-jsc-2015"]
    assert "5=neither like nor dislike" in panel["quote"]
    assert panel["url"] == "https://ntrs.nasa.gov/citations/20150018899"
    assert "Ninguna de las dos es la papeleta" in scale["labels_note"]
    assert any(line.startswith("Búsqueda del 2026-10-21") for line in scale["labels_not_found"])


def test_a_label_counts_only_next_to_its_own_point() -> None:
    written = instruments_read._written_with_its_point
    quote = "a: 9-Like Extremely / 18-Like Slightly / 8-Like Very Much; b: 1 = Dislike Extremely)"
    assert written(9, "Like Extremely", quote) and written(8, "Like Very Much", quote)
    assert written(1, "Dislike Extremely", quote)
    # El número de otro punto, un número que solo termina en el del punto y otro separador.
    assert not written(7, "Like Very Much", quote)
    assert not written(8, "Like Slightly", quote)
    assert not written(9, "Like Very Much", quote)
    assert not written(1, "Like Extremely", quote)
    assert not written(9, "Like Extremely", "9: Like Extremely")
    # Un trozo del rótulo escrito no es el rótulo, ni lo es una palabra con guion de la prosa.
    assert not written(9, "Like Extreme", quote)
    assert not written(9, "Like", quote)
    assert not written(5, "Neither Like", "5-Neither Like or Dislike / 4-Dislike Slightly")
    prose = "using a 9-pt hedonic scale (1 = Dislike Extremely; 9 = Like Extremely)."
    assert written(9, "Like Extremely", prose) and not written(9, "pt", prose)


def test_the_mission_own_scales_get_no_borrowed_labels_and_say_why(client: TestClient) -> None:
    scales = _scales(client)
    own = {key for key, scale in scales.items() if scale["labels_status"] == "own"}
    assert own == instruments_read.OWN_SCALES == {
        "mood-valence", "symptom-burden", "appetite-rating",
    }
    for key in own:
        scale = scales[key]
        assert scale["labels"] is None and scale["labels_language"] is None
        assert scale["labels_sources"] == [] and scale["labels_see_also"] == []
        assert scale["labels_note"].startswith(diary.SCALE_UNLABELLED)
        assert "ninguna fuente la define" in scale["labels_note"]
        # Desde el 2026-10-15 sus anclas están decididas, y la nota dice de quién y cómo
        # (detalle en `tests/test_own_scale_anchors.py`).
        assert "decisión de diseño de EMMA, sin validar, no un dato leído" in scale["labels_note"]
        assert "pendiente" not in scale["labels_note"]
    # Ninguna escala queda en un estado sin explicar: leída, propia o, desde el 2026-10-16,
    # la de un instrumento publicado cuya fuente se leyó sin rótulos «n = rótulo» (los
    # indicadores descriptivos con escala de puntos; detalle en test_descriptive_indicators.py).
    assert {scale["labels_status"] for scale in scales.values()} == {"read", "own", "instrument"}
    assert not instruments_read.OWN_SCALES & set(RAW["scales"])


def test_reading_labels_did_not_touch_the_catalogue_ranges() -> None:
    code = CATALOG["food-acceptability"]
    assert (code.physical_min, code.physical_max) == (1, 9)
    assert (code.reference_low, code.reference_high, code.concerning) == (6, 9, "low")


def _hedonic(raw: dict[str, Any]) -> dict[str, Any]:
    scale: dict[str, Any] = raw["scales"]["food-acceptability"]
    return scale


def _label(raw: dict[str, Any], value: int) -> dict[str, Any]:
    found: dict[str, Any] = next(
        item for item in _hedonic(raw)["labels"] if item["value"] == value
    )
    return found


@pytest.mark.parametrize(
    ("change", "message"),
    [
        # Las anclas de otra escala puestas a una escala propia de la misión.
        (
            lambda raw: raw["scales"].update({"mood-valence": _hedonic(raw)}),
            "escala propia de la misión",
        ),
        (lambda raw: raw["scales"].update({"pvt-lapses": _hedonic(raw)}), "no es una escala"),
        (lambda raw: raw["scales"].update({"no-existe": _hedonic(raw)}), "no es una escala"),
        # Un rótulo «de los de siempre» que la frase no escribe: la de 1981 dice «or».
        (
            lambda raw: _label(raw, 5).update(label="Neither Like nor Dislike"),
            "no está escrito en su frase",
        ),
        # Un rótulo intermedio apoyado en la frase de 2025, que solo escribe los extremos.
        (
            lambda raw: _label(raw, 8).update(statement="hedonic-anchors-panel"),
            "no está escrito en su frase",
        ),
        # El rótulo de un extremo puesto en el otro.
        (lambda raw: _hedonic(raw)["labels"][0].update(value=9), "no está escrito en su frase"),
        (lambda raw: _hedonic(raw)["labels"][0].update(value=0), "fuera del rango"),
        (lambda raw: _hedonic(raw)["labels"][0].update(value=1.0), "es un entero"),
        (
            lambda raw: _hedonic(raw)["labels"].append(dict(_hedonic(raw)["labels"][0])),
            "lleva dos rótulos",
        ),
        (lambda raw: _hedonic(raw)["labels"][0].update(statement="x"), "ninguna frase leída"),
        (lambda raw: _hedonic(raw).update(labels=[]), "sin ningún rótulo leído"),
        (lambda raw: _hedonic(raw).update(language=""), "idioma"),
        (lambda raw: _hedonic(raw).update(labels_note=" "), "idioma"),
        (lambda raw: _hedonic(raw)["see_also"].append("x"), "no es una frase leída"),
        (lambda raw: _hedonic(raw)["not_found"].append(""), "not_found"),
    ],
)
def test_the_loader_rejects_a_label_that_was_not_read(change: Any, message: str) -> None:
    with pytest.raises(InstrumentsError, match=message):
        validate(_broken(change))
