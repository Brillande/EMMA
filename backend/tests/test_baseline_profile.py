"""El perfil de línea base de cada tripulante (especificación §3 `baseline_profile`, §10).

Qué fijan estas pruebas:
- que el perfil enseña **la base que usó el motor**: mediana, dispersión, lecturas y si estaba
  establecida salen de la `Baseline` de la desviación de `evaluate_rolling`, no de otra cuenta;
- que dice de dónde vinieron las lecturas (el estado exacto o su familia) igual que el motor las
  tomó, sin contar las de baja confianza;
- que una base en aprendizaje no enseña mediana y dice contra qué se juzga mientras tanto;
- que los descriptivos dicen por qué no tienen base;
- y las que importan (invariantes 4 y 5): pedir el perfil no escribe ningún asiento ni
  instantánea, `/api/status` devuelve lo mismo antes y después, y el módulo no toca el motor.
"""

import ast
import copy
import datetime as dt
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analysis import baseline_profile
from app.analysis.baseline import (
    _QUANTILE_THRESHOLDS,
    _SAMPLES_FOR_SEVERITY,
    MIN_SAMPLES,
    Baseline,
    BaselineEngine,
    Deviation,
    Severity,
    _severity_from_quantiles,
    cap_for_confidence,
    compute_baseline,
    crossed_danger_limit,
    crossed_personal_cut,
    cut_rules,
    personal_cuts,
    watches,
)
from app.analysis.baseline_profile import (
    CONTEXT_DISPLAY,
    DESCRIPTIVE_REASON,
    REFERENCE_BASIS_DISPLAY,
    profile,
)
from app.api import routes
from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.core.display import number
from app.evidence import flight_direction
from app.ingest.codes import CATALOG, DESCRIPTIVE_ONLY, ReferenceBasis
from app.ingest.codes import get as get_code
from app.ingest.fhir import (
    LOW_CONFIDENCE_THRESHOLD,
    Context,
    EvidenceContext,
    ObservationType,
    VitalObservation,
    observation,
)
from app.main import app
from app.text_guard import check

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)


def _series(
    key: str,
    context: Context,
    count: int,
    start: dt.datetime,
    step: dt.timedelta = dt.timedelta(hours=1),
    value: float = 60.0,
    confidence: float = 1.0,
) -> list[VitalObservation]:
    return [
        observation(key, value + (index % 7), start + index * step, "crew-01", "test",
                    context=context, confidence=confidence)
        for index in range(count)
    ]


def _profile(observations: list[VitalObservation]) -> tuple[dict, list[Deviation]]:
    deviations = BaselineEngine().evaluate_rolling(observations)
    latest = max(obs.effective for obs in observations)
    return profile("crew-01", observations, deviations, latest), deviations


def _row(found: dict, key: str, context: Context) -> dict:
    item = next(item for item in found["indicators"] if item["key"] == key)
    return next(row for row in item["states"] if row["context"] == str(context))


def _deviation(deviations: list[Deviation], key: str, row: dict) -> Deviation:
    when = dt.datetime.fromisoformat(row["reading_effective"])
    (found,) = [dev for dev in deviations if dev.key == key and dev.effective == when]
    return found


# --------------------------------------------------------------------------- #
# Lo que enseña es lo que usó el motor
# --------------------------------------------------------------------------- #


def test_every_figure_is_the_one_the_engine_judged_with() -> None:
    start = NOW - dt.timedelta(days=12)
    observations = (
        _series("heart-rate", Context.REST, 250, start)
        + _series("heart-rate", Context.SLEEP, 40, start + dt.timedelta(minutes=30))
    )
    found, deviations = _profile(observations)
    item = found["indicators"][0]
    assert item["key"] == "heart-rate"
    assert {row["context"] for row in item["states"]} == {"rest", "sleep"}
    for row in item["states"]:
        dev = _deviation(deviations, "heart-rate", row)
        assert dev.baseline is not None
        assert row["samples"] == dev.baseline.samples
        assert row["established"] is (not dev.used_population_range)
        if row["established"]:
            assert row["median"] == dev.baseline.center
            assert row["spread"] == dev.baseline.spread
        # La ventana es la de `evaluate_rolling`: 14 días que terminan 12 h antes.
        assert dt.datetime.fromisoformat(row["window"]["end"]) == dev.effective - dt.timedelta(
            hours=12
        )
        assert dt.datetime.fromisoformat(row["window"]["start"]) == dev.effective - dt.timedelta(
            days=14, hours=12
        )

    rest = _row(found, "heart-rate", Context.REST)
    assert rest["established"] and rest["status_display"] == "establecida"
    assert rest["samples"] >= MIN_SAMPLES


def test_a_learning_base_shows_no_median_and_says_what_judges_meanwhile() -> None:
    observations = _series("heart-rate", Context.SLEEP, 40, NOW - dt.timedelta(days=3))
    observations += _series("hrv-sdnn", Context.SLEEP, 40, NOW - dt.timedelta(days=3), value=80)
    found, _ = _profile(observations)
    heart = _row(found, "heart-rate", Context.SLEEP)
    assert heart["established"] is False
    assert heart["status_display"] == "en aprendizaje"
    assert heart["median"] is None and heart["spread"] is None
    assert heart["samples"] < MIN_SAMPLES and heart["min_samples"] == MIN_SAMPLES
    # En sueño, el límite de reposo del catálogo (110 /min), que es el que mira el motor.
    assert heart["danger_limit"]["high"] == 110
    assert "límite de peligro" in heart["judged_against"]

    sdnn = _row(found, "hrv-sdnn", Context.SLEEP)
    assert sdnn["danger_limit"]["low"] is None and sdnn["danger_limit"]["high"] is None
    assert sdnn["judged_against"].startswith("Mientras aprende no avisa")


def test_the_latest_state_comes_first_and_decides_the_indicator() -> None:
    start = NOW - dt.timedelta(days=12)
    observations = _series("heart-rate", Context.REST, 250, start) + [
        observation("heart-rate", 52, NOW + dt.timedelta(days=1), "crew-01", "test",
                    context=Context.SLEEP)
    ]
    found, _ = _profile(observations)
    (item,) = found["indicators"]
    assert [row["context"] for row in item["states"]] == ["sleep", "rest"]
    assert item["states"][0]["latest"] and not item["states"][1]["latest"]
    # La última lectura (sueño) se juzgó sin base: el indicador lo dice, aunque reposo la tenga.
    assert item["established"] is False
    assert "se juzgó sin base personal" in found["statement"]


def test_two_states_at_the_last_instant_are_both_the_latest() -> None:
    """Dos lecturas a la misma última hora en dos estados: las dos son «la última», y el
    indicador solo cuenta como establecido si lo están las dos (no según el orden del motor)."""
    start = NOW - dt.timedelta(days=12)
    last = NOW + dt.timedelta(days=1)
    observations = (
        _series("heart-rate", Context.REST, 250, start)
        + _series("heart-rate", Context.SLEEP, 10, start + dt.timedelta(minutes=30))
        + [
            observation("heart-rate", 61, last, "crew-01", "test", context=Context.REST),
            observation("heart-rate", 52, last, "crew-01", "test", context=Context.SLEEP),
        ]
    )
    found, _ = _profile(observations)
    (item,) = found["indicators"]
    assert [row["latest"] for row in item["states"]] == [True, True]
    assert {row["established"] for row in item["states"]} == {True, False}
    assert item["established"] is False


def test_one_base_is_said_in_singular() -> None:
    found, _ = _profile(_series("heart-rate", Context.REST, 150, NOW - dt.timedelta(days=12)))
    assert found["statement"].startswith(
        "1 indicador analizado, con 1 base (una por estado): 1 establecida y 0 en aprendizaje."
    )


def test_the_danger_limit_shown_is_the_one_the_engine_crosses() -> None:
    """`_danger_bounds` repite la regla de reposo y esfuerzo de `crossed_danger_limit`: se
    contrasta con ella en cada estado y cada indicador con límite, justo fuera de cada borde."""
    for code in CATALOG.values():
        for state in Context:
            low, high = baseline_profile._danger_bounds(code, state)  # noqa: SLF001
            for bound, step in ((low, -1e-3), (high, 1e-3)):
                if bound is None or not code.is_physically_possible(bound + step):
                    continue
                reading = observation(code.key, bound + step, NOW, "crew-01", "test",
                                      context=state)
                assert crossed_danger_limit(reading) == bound, (code.key, state)
            # Y nada que el motor mire queda sin enseñar: dentro de los dos bordes no cruza.
            inside = (low + 1e-3 if low is not None else (high - 1e-3 if high is not None
                                                           else None))
            if inside is not None and code.is_physically_possible(inside) and (
                high is None or inside < high
            ):
                reading = observation(code.key, inside, NOW, "crew-01", "test", context=state)
                assert crossed_danger_limit(reading) is None, (code.key, state)


# --------------------------------------------------------------------------- #
# De dónde salen las lecturas: el estado o su familia, como el motor
# --------------------------------------------------------------------------- #


def test_a_thin_state_borrows_its_family_and_says_which_readings() -> None:
    start = NOW - dt.timedelta(days=12)
    observations = (
        _series("heart-rate", Context.MEAL, 200, start)
        + _series("heart-rate", Context.WORK, 10, start + dt.timedelta(minutes=20))
        + [observation("heart-rate", 70, NOW + dt.timedelta(days=1), "crew-01", "test",
                       context=Context.WORK)]
    )
    found, deviations = _profile(observations)
    work = _row(found, "heart-rate", Context.WORK)
    dev = _deviation(deviations, "heart-rate", work)
    assert dev.baseline is not None and dev.baseline.samples > 10
    assert work["drawn_from"] == "family"
    # La familia del motor son los estados agrupados bajo reposo que no son reposo.
    assert work["drawn_from_display"] == (
        "Lecturas de trabajo y comida: las de trabajo no bastaban (10)."
    )
    assert work["established"] is True

    meal = _row(found, "heart-rate", Context.MEAL)
    assert meal["drawn_from"] == "state"
    assert meal["drawn_from_display"] == "Lecturas de comida."


def test_doubtful_readings_are_not_counted_as_the_state_own() -> None:
    """El motor aparta las de baja confianza de la referencia: aquí tampoco cuentan, o una base
    del propio estado se leería como prestada de la familia."""
    start = NOW - dt.timedelta(days=12)
    observations = (
        _series("heart-rate", Context.REST, 150, start)
        + _series("heart-rate", Context.REST, 30, start + dt.timedelta(minutes=10),
                  confidence=0.2)
    )
    found, deviations = _profile(observations)
    rest = _row(found, "heart-rate", Context.REST)
    dev = _deviation(deviations, "heart-rate", rest)
    assert dev.baseline is not None
    assert rest["samples"] == dev.baseline.samples
    assert rest["drawn_from"] == "state"


def test_a_reading_that_cannot_be_placed_in_one_state_is_left_out_and_counted() -> None:
    start = NOW - dt.timedelta(days=2)
    observations = _series("heart-rate", Context.REST, 5, start) + [
        # El mismo valor y la misma hora que la primera de reposo (60 /min).
        observation("heart-rate", 60, start, "crew-01", "test", context=Context.SLEEP)
    ]
    found, _ = _profile(observations)
    (item,) = found["indicators"]
    assert item["unattributed_readings"] == 2
    assert item["unattributed_display"].startswith("2 lecturas tienen la misma hora")
    assert all(row["reading_effective"] != start.isoformat() for row in item["states"])


# --------------------------------------------------------------------------- #
# Respaldo del catálogo y descriptivos
# --------------------------------------------------------------------------- #


def test_the_catalog_range_is_shown_as_backup_and_not_as_threshold() -> None:
    found, _ = _profile(_series("heart-rate", Context.REST, 5, NOW))
    reference = found["indicators"][0]["reference"]
    assert (reference["low"], reference["high"], reference["basis"]) == (50, 100, "observed")
    assert "medido en población sana" in reference["text"]
    assert "no se avisa por salir de este rango" in reference["text"]


def test_an_indicator_without_range_says_so() -> None:
    code = next(
        code for code in CATALOG.values()
        if code.reference_basis is None and code.key not in DESCRIPTIVE_ONLY
    )
    found, _ = _profile(_series(code.key, Context.REST, 1, NOW, value=code.physical_min or 0))
    assert found["indicators"][0]["reference"] == {
        "low": None, "high": None, "basis": None, "text": baseline_profile.NO_RANGE,
    }


def test_descriptive_indicators_say_why_they_have_no_base() -> None:
    key = sorted(DESCRIPTIVE_ONLY)[0]
    observations = _series("heart-rate", Context.REST, 5, NOW)
    deviations = BaselineEngine().evaluate_rolling(observations)
    found = profile("crew-01", observations, deviations, NOW, [key, key])
    assert found["descriptive"] == [
        {"key": key, "display_es": found["descriptive"][0]["display_es"],
         "reason": DESCRIPTIVE_REASON}
    ]
    assert "descriptivos, sin línea base" in found["statement"]


def test_every_state_and_range_basis_has_its_words() -> None:
    assert set(CONTEXT_DISPLAY) == set(Context)
    assert set(REFERENCE_BASIS_DISPLAY) == set(ReferenceBasis)


def test_the_method_carries_the_engine_figures() -> None:
    text = baseline_profile.method()
    assert "14 días" in text and "12 h" in text and "100 lecturas" in text


def test_every_text_passes_the_guard() -> None:
    start = NOW - dt.timedelta(days=12)
    observations = (
        _series("heart-rate", Context.MEAL, 200, start)
        + _series("heart-rate", Context.WORK, 10, start)
        + _series("hrv-sdnn", Context.SLEEP, 40, start, value=80)
    )
    deviations = BaselineEngine().evaluate_rolling(observations)
    found = profile("crew-01", observations, deviations, NOW, sorted(DESCRIPTIVE_ONLY))
    texts = [found["statement"], found["method"], found["cuts_method"], found["fixed_note"]]
    for item in found["indicators"]:
        texts.append(item["reference"]["text"])
        for row in item["states"]:
            texts += [row["drawn_from_display"], row["danger_limit"]["text"],
                      row["judged_against"], row["status_display"], row["context_display"]]
            texts += [cut["text"] for cut in row["cuts"]]
            texts += [text for text in (row["composition_display"], row["cuts_note"]) if text]
    texts += [baseline_profile.UNKNOWN_COMPOSITION, baseline_profile.EMPTY_COMPOSITION,
              baseline_profile.NOT_KEPT_COMPOSITION, *baseline_profile.ONE_SIDED_NOTE.values()]
    texts += [item["reason"] for item in found["descriptive"]]
    personal = found["personal_data"]
    texts += [personal[key] for key in ("statement", "cycle", "radiation", "elsewhere", "privacy")]
    for text in texts:
        assert check(text) == [], text


# --------------------------------------------------------------------------- #
# Sexo declarado aparte, edad sin campo, y lo que dice la norma (§5.36.19, revisado 2026-11-14)
# --------------------------------------------------------------------------- #


def test_the_profile_says_sex_is_declared_apart_and_nothing_depends_on_it_or_on_age() -> None:
    personal = baseline_profile.personal_data()
    assert personal["no_field"] == ["edad"]
    statement = personal["statement"]
    # El sexo: fuera del perfil, en su asiento, declarado por el tripulante y borrable solo.
    assert "El sexo no es un campo del perfil" in statement
    assert "lo declara el propio tripulante" in statement
    assert "asiento firmado aparte, que se puede borrar solo" in statement
    assert "La edad no tiene campo" in statement
    assert "Ningún rango ni umbral depende de ellos: cada rango" in statement
    # La fecha de nacimiento que sí se guarda (la identidad declarada) se dice, y para qué.
    assert "fecha de nacimiento" in statement
    # Para qué sirve: solo la puerta del ciclo, descriptivo; lo que ajusta la base es la fase.
    cycle = personal["cycle"]
    assert "solo decide si se ofrece el seguimiento del ciclo menstrual" in cycle
    assert "dato descriptivo" in cycle
    assert "la fase del ciclo registrada, no el sexo" in cycle
    # Desde B3 (2026-11-15) en presente: el ajuste por fase existe, con su puerta.
    assert "lo que puede ajustar la línea base es la fase" in cycle
    assert "podrá" not in cycle
    assert "solo con ciclo regular declarado" in cycle
    # La privacidad: por qué se guarda ahora, lo mínimo, y que se borra aparte.
    privacy = personal["privacy"]
    assert "especificación §12" in privacy
    assert "lo mínimo" in privacy and "borrarlo no toca el resto del registro" in privacy
    assert "La edad no se guarda" in privacy
    # Donde la norma sí ajusta por sexo y edad, lo leído en la misma ficha.
    for requirement in ("[V1 4020]", "[V1 4026]"):
        assert requirement in personal["elsewhere"]
        assert requirement in personal["source"]["scope_caveat"]


def test_the_career_limit_sentence_is_the_one_read_in_the_standard() -> None:
    personal = baseline_profile.personal_data()
    quote = "universal for all ages and sexes"
    assert f"«{quote}»" in personal["radiation"]
    assert "[V1 4030]" in personal["radiation"] and "600 mSv" in personal["radiation"]
    source = personal["source"]
    assert source["id"] == "nasa-std-3001-vol1-rev-c"
    # La frase citada está en la ficha leída, no solo aquí.
    assert quote in source["scope_caveat"]
    assert quote in source["relevance"]
    # El límite de la frase es el de la norma y el que EMMA configura por defecto.
    assert Settings.model_fields["career_dose_limit_msv"].default == float(
        baseline_profile.NORM_CAREER_LIMIT_MSV
    )


def test_no_rule_of_emma_reads_sex_or_age() -> None:
    """Lo que hace cierta la frase: ningún fichero de reglas nombra sexo ni edad como dato.

    El sexo declarado (`crew-sex`, 2026-11-14) solo lo lee `api/`, para ofrecer el ciclo; lo que
    llega al análisis es la fase, como observación.
    """
    app_dir = Path(baseline_profile.__file__).resolve().parents[1]
    words = ("sex", "gender", "age_years", "birth_date")
    for folder in ("analysis", "advisor", "ingest"):
        for path in (app_dir / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            names |= {node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)}
            assert not {name for name in names if name.lower() in words}, path


# --------------------------------------------------------------------------- #
# Dónde corta la base y de qué está hecha (decimoséptima ronda, §5.37.2)
# --------------------------------------------------------------------------- #


def _cut(row: dict, severity: str) -> dict:
    (found,) = [cut for cut in row["cuts"] if cut["severity"] == severity]
    return found


def test_the_cuts_are_the_percentiles_the_engine_grades_with() -> None:
    """Cada corte es el cuantil de la misma base, y el motor gradúa justo a cada lado de él."""
    start = NOW - dt.timedelta(days=13)
    observations = _series("heart-rate", Context.REST, 300, start, value=55.0)
    observations = [
        replace(obs, value=obs.value + (index % 31) * 0.5) for index, obs in enumerate(observations)
    ]
    found, deviations = _profile(observations)
    rest = _row(found, "heart-rate", Context.REST)
    dev = _deviation(deviations, "heart-rate", rest)
    base = dev.baseline
    assert base is not None and 200 <= base.samples < 1000
    code = get_code("heart-rate")
    assert [cut["severity"] for cut in rest["cuts"]] == ["mild", "moderate", "severe"]
    assert [cut["quantile"] for cut in rest["cuts"]] == [0.99, 0.995, 0.999]
    for cut in rest["cuts"][:2]:
        assert cut["applies"] is True
        assert cut["min_samples"] <= base.samples
        assert cut["high"] == base.quantile(cut["quantile"])
        assert cut["low"] == base.quantile(1.0 - cut["quantile"])
    # El motor, justo por fuera y justo por dentro de cada corte que se aplica.
    mild, moderate = _cut(rest, "mild"), _cut(rest, "moderate")
    assert _severity_from_quantiles(moderate["high"] + 1e-6, base, code)[0] is Severity.MODERATE
    assert _severity_from_quantiles(moderate["high"] - 1e-6, base, code)[0] in {
        Severity.MILD, Severity.NONE,
    }
    if mild["high"] < moderate["high"]:
        assert _severity_from_quantiles(mild["high"] + 1e-6, base, code)[0] is Severity.MILD
    assert _severity_from_quantiles(mild["high"] - 1e-6, base, code)[0] is Severity.NONE
    assert _severity_from_quantiles(mild["low"] - 1e-6, base, code)[0] is not Severity.NONE
    assert _severity_from_quantiles(mild["low"] + 1e-6, base, code)[0] is Severity.NONE
    # La que la base no sostiene no lleva cifra: el motor no la afirma.
    severe = _cut(rest, "severe")
    assert severe["applies"] is False and severe["high"] is None and severe["low"] is None
    assert severe["text"] == (
        f"Grave: sin corte todavía; pide 1000 lecturas de base y tiene {base.samples}."
    )
    assert _severity_from_quantiles(1e6, base, code)[0] is Severity.MODERATE
    # La cifra, en su unidad, con un decimal más que la lectura y el percentil de cada lado.
    assert mild["text"].startswith(f"Leve: por encima de {number(mild['high'], 1)} /min")
    assert f"por debajo de {number(mild['low'], 1)} /min" in mild["text"]
    assert "/min (percentil 99 de su base) o por debajo de " in mild["text"]
    assert mild["text"].endswith("/min (percentil 1 de su base).")
    assert "(percentil 99,5 de su base)" in moderate["text"]
    assert "(percentil 0,5 de su base)" in moderate["text"]
    assert rest["cuts_note"] is None


def test_a_one_sided_indicator_cuts_only_on_its_side_and_says_so() -> None:
    start = NOW - dt.timedelta(days=12)
    found, deviations = _profile(
        _series("oxygen-saturation", Context.REST, 150, start, value=94.0)
    )
    rest = _row(found, "oxygen-saturation", Context.REST)
    base = _deviation(deviations, "oxygen-saturation", rest).baseline
    assert base is not None
    mild = _cut(rest, "mild")
    assert mild["high"] is None and mild["low"] == base.quantile(0.01)
    assert "por encima" not in mild["text"]
    assert rest["cuts_note"] == baseline_profile.ONE_SIDED_NOTE["low"]
    code = get_code("oxygen-saturation")
    # Lo que dice la nota: por arriba no hay percentil que avise.
    assert _severity_from_quantiles(1e3, base, code)[0] is Severity.NONE


def test_a_learning_base_has_no_cuts() -> None:
    found, _ = _profile(_series("heart-rate", Context.SLEEP, 40, NOW - dt.timedelta(days=3)))
    sleep = _row(found, "heart-rate", Context.SLEEP)
    assert sleep["cuts"] == [] and sleep["cuts_note"] is None
    # Pero sí se dice de qué están hechas sus lecturas.
    assert sleep["composition"]["samples"] == sleep["samples"]


def test_the_cut_words_are_the_finding_words() -> None:
    from app.risk_entity import FINDING_SEVERITY_DISPLAY

    assert baseline_profile.CUT_SEVERITY_DISPLAY == FINDING_SEVERITY_DISPLAY
    assert set(baseline_profile.CUT_SEVERITY_DISPLAY) == {
        severity for _, severity in _QUANTILE_THRESHOLDS
    }


def test_the_composition_counts_environment_and_type_of_the_base_readings() -> None:
    start = NOW - dt.timedelta(days=12)
    measured = _series("heart-rate", Context.REST, 120, start)
    iss = [
        replace(obs, evidence_context=EvidenceContext.ISS)
        for obs in _series("heart-rate", Context.REST, 30, start + dt.timedelta(minutes=10))
    ]
    inferred = [
        replace(obs, observation_type=ObservationType.INFERRED, model_version="modelo-1")
        for obs in _series("heart-rate", Context.REST, 20, start + dt.timedelta(minutes=20))
    ]
    # Las de baja confianza no entran en la base: tampoco en su composición.
    doubtful = _series("heart-rate", Context.REST, 15, start + dt.timedelta(minutes=30),
                       confidence=0.2)
    found, deviations = _profile(measured + iss + inferred + doubtful)
    rest = _row(found, "heart-rate", Context.REST)
    base = _deviation(deviations, "heart-rate", rest).baseline
    assert base is not None
    composition = rest["composition"]
    assert composition["samples"] == base.samples == rest["samples"]
    assert sum(composition["evidence_context"].values()) == base.samples
    assert sum(composition["observation_type"].values()) == base.samples
    assert set(composition["evidence_context"]) == {"ground", "iss"}
    assert set(composition["observation_type"]) == {"measured", "inferred"}
    # De la más frecuente a la menos.
    assert list(composition["evidence_context"]) == ["ground", "iss"]
    others = composition["observation_type"]["inferred"]
    assert rest["composition_display"] == (
        f"Mezcla lecturas de 2 entornos de evidencia; se cuentan por separado. {others} de las "
        f"{base.samples} no son medidas: son inferidas o predichas."
    )
    assert "1 base mezcla lecturas de varios entornos de evidencia." in found["statement"]
    assert "1 base incluye valores que no son medidas." in found["statement"]


def test_one_environment_all_measured_needs_no_sentence() -> None:
    found, _ = _profile(_series("heart-rate", Context.REST, 150, NOW - dt.timedelta(days=12)))
    rest = _row(found, "heart-rate", Context.REST)
    assert rest["composition"]["evidence_context"] == {"ground": rest["samples"]}
    assert rest["composition"]["observation_type"] == {"measured": rest["samples"]}
    assert rest["composition_display"] is None
    assert "entornos" not in found["statement"] and "no son medidas" not in found["statement"]


def test_a_borrowed_base_counts_the_family_readings() -> None:
    start = NOW - dt.timedelta(days=12)
    meal = [
        replace(obs, evidence_context=EvidenceContext.ANALOG_ISOLATION)
        for obs in _series("heart-rate", Context.MEAL, 200, start)
    ]
    observations = (
        meal
        + _series("heart-rate", Context.WORK, 10, start + dt.timedelta(minutes=20))
        + [observation("heart-rate", 70, NOW + dt.timedelta(days=1), "crew-01", "test",
                       context=Context.WORK)]
    )
    found, deviations = _profile(observations)
    work = _row(found, "heart-rate", Context.WORK)
    base = _deviation(deviations, "heart-rate", work).baseline
    assert work["drawn_from"] == "family" and base is not None
    composition = work["composition"]
    assert composition["samples"] == base.samples
    assert composition["evidence_context"]["analog_isolation"] > 0
    assert composition["evidence_context"]["ground"] == 10


def test_a_base_whose_readings_cannot_be_found_says_so() -> None:
    """Si las lecturas de la ventana no son las de la base, no se cuenta otra cosa."""
    observations = _series("heart-rate", Context.REST, 150, NOW - dt.timedelta(days=12))
    deviations = BaselineEngine().evaluate_rolling(observations)
    # El motor juzgó con unas lecturas que el perfil no recibe.
    found = profile("crew-01", observations[40:], deviations, NOW)
    rest = _row(found, "heart-rate", Context.REST)
    assert rest["composition"] is None
    assert rest["composition_display"] == baseline_profile.UNKNOWN_COMPOSITION
    assert "no se puede decir de qué entorno ni tipo son sus lecturas" in found["statement"]
    # Tantas lecturas como la base, pero no las mismas: tampoco se cuentan.
    changed = [replace(obs, value=obs.value + 100) for obs in observations[:-1]]
    found = profile("crew-01", [*changed, observations[-1]], deviations, NOW)
    rest = _row(found, "heart-rate", Context.REST)
    assert rest["drawn_from"] == "state"
    assert rest["composition"] is None
    assert rest["composition_display"] == baseline_profile.UNKNOWN_COMPOSITION


def test_a_base_that_keeps_no_values_says_that_and_not_another_reason() -> None:
    observations = _series("heart-rate", Context.REST, 150, NOW - dt.timedelta(days=12))
    deviations = BaselineEngine().evaluate_rolling(observations)
    last = max(deviations, key=lambda dev: dev.effective)
    assert last.baseline is not None
    bare = replace(last, baseline=replace(last.baseline, sorted_values=()))
    found = profile("crew-01", observations,
                    [bare if dev is last else dev for dev in deviations], NOW)
    rest = _row(found, "heart-rate", Context.REST)
    assert rest["composition"] is None
    assert rest["composition_display"] == baseline_profile.NOT_KEPT_COMPOSITION
    assert all(cut["applies"] is False and cut["high"] is None for cut in rest["cuts"])
    assert _cut(rest, "mild")["text"] == f"Leve: {baseline_profile.NO_VALUES}."


def test_the_cuts_method_carries_the_engine_figures_and_the_confidence_cap() -> None:
    text = baseline_profile.cuts_method()
    assert "leve por encima del 99 (con 100 lecturas de base o más)" in text
    assert "moderada por encima del 99,5 (con 200 lecturas de base o más)" in text
    assert "grave por encima del 99,9 (con 1000 lecturas de base o más)" in text
    assert "por abajo, por debajo del 1, del 0,5 y del 0,1." in text
    assert "confianza por debajo de 0,5 que cruce un corte se queda en leve" in text
    # Lo que dice del tope es lo que hace el motor.
    assert cap_for_confidence(Severity.SEVERE, LOW_CONFIDENCE_THRESHOLD - 0.01) is Severity.MILD
    assert cap_for_confidence(Severity.SEVERE, LOW_CONFIDENCE_THRESHOLD) is Severity.SEVERE


# --------------------------------------------------------------------------- #
# Una sola función de cortes para el motor y el perfil (§5.38.11)
# --------------------------------------------------------------------------- #


def _rule_before_the_shared_function(
    value: float, base: Baseline, concerning: str
) -> tuple[float, float, Severity] | None:
    """La regla de `crossed_personal_cut` tal como estaba antes de `personal_cuts`, congelada.

    Es el oráculo del refactor: el motor tiene que graduar exactamente igual que con ella. Lee
    las tablas del motor, no las copia: lo que se congela es el algoritmo (lados, mínimos, orden
    de búsqueda, borde estricto), así que reajustar un umbral no hace fallar esta prueba.
    """
    direction = "high" if value >= base.center else "low"
    if concerning != "both" and concerning != direction:
        return None
    for fraction, severity in _QUANTILE_THRESHOLDS:
        if base.samples < _SAMPLES_FOR_SEVERITY[severity]:
            continue
        quantile = fraction if direction == "high" else 1.0 - fraction
        cut = base.quantile(quantile)
        if cut is None:
            break
        if (direction == "high" and value > cut) or (direction == "low" and value < cut):
            return quantile, cut, severity
    return None


def _bases() -> list[Baseline]:
    """Bases de todos los tamaños que importan: por debajo y justo en cada mínimo, y sin valores."""
    import random

    rng = random.Random(538)
    bases = []
    for samples in (99, 100, 101, 150, 199, 200, 201, 500, 999, 1000, 1001, 1500):
        values = [rng.gauss(60.0, 6.0) for _ in range(samples)]
        bases.append(compute_baseline("heart-rate", values))
    # Una serie con valores repetidos: cortes que coinciden entre gravedades.
    bases.append(compute_baseline("heart-rate", [float(index % 7) for index in range(1200)]))
    bases.append(replace(bases[-2], sorted_values=()))  # una base que no guarda sus valores
    return bases


def _values_around(base: Baseline) -> list[float]:
    """Cada corte posible, justo encima, justo debajo y en él; el centro y los extremos."""
    points = [base.center, base.center + 1e-9, base.center - 1e-9, -1e9, 1e9]
    for fraction in (0.999, 0.995, 0.990, 0.010, 0.005, 0.001):
        cut = base.quantile(fraction)
        if cut is not None:
            points += [cut, cut + 1e-9, cut - 1e-9, cut + 0.5, cut - 0.5]
    return points


def test_the_engine_grades_exactly_as_before_the_shared_function() -> None:
    """Sin cambio de conducta: grado a grado, el motor y la regla de antes dicen lo mismo."""
    codes = [code for code in CATALOG.values() if code.concerning in {"high", "low", "both"}]
    assert {code.concerning for code in codes} == {"high", "low", "both"}
    compared = 0
    for base in _bases():
        for value in _values_around(base):
            for code in codes:
                before = _rule_before_the_shared_function(value, base, code.concerning)
                cut = crossed_personal_cut(value, base, code)
                now = None if cut is None else (cut.quantile, cut.value, cut.severity)
                assert now == before, (code.key, base.samples, value)
                expected = before[2] if before is not None else Severity.NONE
                assert _severity_from_quantiles(value, base, code)[0] is expected
                compared += 1
    assert compared > 10_000


def test_the_profile_cuts_are_the_engine_cuts() -> None:
    """El perfil no recalcula nada: cada fila es un `personal_cuts` del motor, de leve a grave."""
    start = NOW - dt.timedelta(days=13)
    observations = [
        replace(obs, value=obs.value + (index % 31) * 0.5)
        for index, obs in enumerate(_series("heart-rate", Context.REST, 300, start, value=55.0))
    ]
    found, deviations = _profile(observations)
    rest = _row(found, "heart-rate", Context.REST)
    base = _deviation(deviations, "heart-rate", rest).baseline
    assert base is not None
    engine = sorted(personal_cuts(base, get_code("heart-rate")), key=lambda cut: cut.rule.fraction)
    assert [
        (cut["severity"], cut["quantile"], cut["min_samples"], cut["applies"], cut["high"],
         cut["low"])
        for cut in rest["cuts"]
    ] == [
        (str(cut.rule.severity), cut.rule.fraction, cut.rule.min_samples,
         cut.supported and cut.has_values, cut.high, cut.low)
        for cut in engine
    ]
    # Y las reglas son las tablas del motor, en su orden de búsqueda (la más exigente primero).
    assert [(rule.fraction, rule.severity) for rule in cut_rules()] == list(_QUANTILE_THRESHOLDS)
    assert {rule.severity: rule.min_samples for rule in cut_rules()} == _SAMPLES_FOR_SEVERITY


@pytest.mark.parametrize("concerning", ["high", "low", "both"])
def test_the_cuts_follow_the_side_that_concerns(concerning: str) -> None:
    (code,) = [item for item in CATALOG.values() if item.concerning == concerning][:1]
    base = _bases()[-3]  # 1500 lecturas: sostiene las tres gravedades
    for cut in personal_cuts(base, code):
        assert cut.supported
        assert (cut.high is not None) is (concerning in {"high", "both"})
        assert (cut.low is not None) is (concerning in {"low", "both"})
        assert watches(code, "high") is (cut.high is not None)
        assert watches(code, "low") is (cut.low is not None)
    # Pedir un solo lado (lo que hace el motor) da ese lado igual y deja el otro sin calcular.
    for side, other in (("high", "low"), ("low", "high")):
        for full, single in zip(
            personal_cuts(base, code), personal_cuts(base, code, sides=(side,)), strict=True
        ):
            assert single.on(side) == full.on(side) and single.on(other) is None
    # Una base sin sus valores lo dice en su campo, no con un `None` que haya que adivinar.
    bare = _bases()[-1]
    assert all(cut.supported and not cut.has_values and cut.high is None and cut.low is None
               for cut in personal_cuts(bare, code))


# --------------------------------------------------------------------------- #
# No toca el motor
# --------------------------------------------------------------------------- #


def test_the_module_reads_the_engine_and_never_drives_it() -> None:
    source = Path(baseline_profile.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.analysis.baseline"
        for alias in node.names
    }
    # Solo constantes y el tipo de la desviación: ni el motor ni la función de la base.
    assert imported == {
        "DEFAULT_ROLLING_LAG", "DEFAULT_ROLLING_WINDOW", "MAD_TO_SD", "MIN_SAMPLES", "Deviation",
        # Para enseñar los cortes: la base que juzgó, la palabra de la gravedad y la función de
        # cortes del motor (§5.38.11), con sus reglas sin base para la frase del método. Las dos
        # son puras: leen la base y no deciden nada.
        "Baseline", "Severity", "cut_rules", "personal_cuts",
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not {"BaselineEngine", "compute_baseline", "store", "ledger"} & (names | attributes)
    # Ni copia la regla de los cortes: las tablas del motor no se leen aquí, ni por su nombre.
    assert not {"_QUANTILE_THRESHOLDS", "_SAMPLES_FOR_SEVERITY"} & (names | attributes)


def test_profiling_leaves_the_deviations_as_they_were() -> None:
    start = NOW - dt.timedelta(days=12)
    observations = _series("heart-rate", Context.REST, 150, start)
    deviations = BaselineEngine().evaluate_rolling(observations)
    before = copy.deepcopy(deviations)
    profile("crew-01", observations, deviations, NOW)
    assert deviations == before


# --------------------------------------------------------------------------- #
# La ruta, contra el estado
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    cache: Path = tmp_path_factory.mktemp("cache")
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=cache, offline=True)
    client = TestClient(app)
    response = client.post("/api/simulate", params={"scenario": "spe-event", "days": 20})
    assert response.status_code == 201
    yield client
    app.dependency_overrides.clear()
    reset_store(None)


def _entry_types() -> list[str]:
    return [entry["entry_type"] for entry in get_store().audit_trail(limit=10**9)]


def test_asking_for_the_profile_writes_nothing(seeded: TestClient) -> None:
    """Invariante 4. Va la primera: aún no hay instantáneas de predicción."""
    store = get_store()
    before = len(store.ledger)
    assert store.prediction_snapshots("crew-01") == []
    assert seeded.get("/api/baseline-profile").status_code == 200
    assert len(store.ledger) == before
    assert store.prediction_snapshots("crew-01") == []

    seeded.get("/api/status")
    after_status = len(store.ledger)
    types = _entry_types()
    seeded.get("/api/baseline-profile")
    assert len(store.ledger) == after_status
    assert _entry_types() == types


def test_status_is_identical_with_and_without_the_profile(seeded: TestClient) -> None:
    """Invariante 5: niveles, alertas y todo lo demás de `/api/status`, igual."""
    seeded.get("/api/status")
    before = seeded.get("/api/status").json()
    seeded.get("/api/baseline-profile")
    assert seeded.get("/api/status").json() == before


def test_the_route_shows_the_bases_the_status_used(seeded: TestClient) -> None:
    body = seeded.get("/api/baseline-profile").json()
    status = seeded.get("/api/status").json()
    assert body["reference_time"] == status["data"]["reference_time"]
    assert body["kind"] == "rolling"
    assert body["personal_data"] == baseline_profile.personal_data()
    # El simulador no produce descriptivos: ninguno se lista sin lecturas.
    assert body["descriptive"] == []

    assessed = routes._assess(get_settings(), get_store(), "crew-01", None, None, None)
    newest: dict[str, Deviation] = {}
    for dev in assessed.deviations:
        if dev.key not in newest or dev.effective > newest[dev.key].effective:
            newest[dev.key] = dev
    assert {item["key"] for item in body["indicators"]} == set(newest)
    for item in body["indicators"]:
        dev = newest[item["key"]]
        (head,) = [row for row in item["states"] if row["latest"]]
        assert head is item["states"][0] or head == item["states"][0]
        assert head["reading_effective"] == dev.effective.isoformat()
        assert dev.baseline is not None
        assert head["samples"] == dev.baseline.samples
        assert item["established"] is (not dev.used_population_range)
        # De qué está hecha: las mismas lecturas que la base, todas del simulador.
        for row in item["states"]:
            assert row["composition"] is not None, (item["key"], row["context"])
            assert row["composition"]["samples"] == row["samples"]
            assert set(row["composition"]["evidence_context"]) <= {"simulated"}
        # Dónde corta: los cuantiles de la base que juzgó la última lectura.
        for cut in head["cuts"]:
            if cut["high"] is not None:
                assert cut["high"] == dev.baseline.quantile(cut["quantile"])
            if cut["low"] is not None:
                assert cut["low"] == dev.baseline.quantile(1.0 - cut["quantile"])


def test_until_gives_only_what_ground_has(seeded: TestClient) -> None:
    full = seeded.get("/api/baseline-profile").json()
    cut = dt.datetime.fromisoformat(full["reference_time"]) - dt.timedelta(days=5)
    body = seeded.get("/api/baseline-profile", params={"until": cut.isoformat()}).json()
    assert dt.datetime.fromisoformat(body["reference_time"]) <= cut
    assert body["until"] == cut.isoformat()
    for item in body["indicators"]:
        for row in item["states"]:
            assert dt.datetime.fromisoformat(row["reading_effective"]) <= cut


def test_unknown_subject_is_refused(seeded: TestClient) -> None:
    assert seeded.get("/api/baseline-profile", params={"subject": "nadie"}).status_code == 404


def test_the_route_gives_what_other_flights_showed_for_each_analyzed_indicator(
    seeded: TestClient,
) -> None:
    """Decimoquinta ronda (D14): junto a la base, el sentido observado en otros vuelos, uno por
    indicador analizado y en su mismo orden; con `until`, el de los indicadores que Tierra tiene."""
    body = seeded.get("/api/baseline-profile").json()
    block = body["flight_direction"]
    assert block == flight_direction.for_profile(item["key"] for item in body["indicators"])
    assert [row["key"] for row in block["indicators"]] == [
        item["key"] for item in body["indicators"]
    ]
    assert block["note"] == flight_direction.FRAME
    heart = next(row for row in block["indicators"] if row["key"] == "heart-rate")
    assert heart["direction"] == "unchanged"
    # No toca el perfil: lo de la base es lo mismo con el bloque que sin él.
    assessed = routes._assess(get_settings(), get_store(), "crew-01", None, None, None)
    alone = profile("crew-01", assessed.observations, assessed.deviations, assessed.latest)
    assert {key: body[key] for key in alone} == alone
    cut = dt.datetime.fromisoformat(body["reference_time"]) - dt.timedelta(days=5)
    earlier = seeded.get("/api/baseline-profile", params={"until": cut.isoformat()}).json()
    assert [row["key"] for row in earlier["flight_direction"]["indicators"]] == [
        item["key"] for item in earlier["indicators"]
    ]
