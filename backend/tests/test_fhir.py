"""El modelo canonico debe producir FHIR valido y sobrevivir el viaje de ida y vuelta."""

import json
from datetime import UTC, datetime

import pytest

from app.core.storage import _to_payload
from app.ingest.codes import (
    CATALOG,
    DENSITOMETRY_KEYS,
    LAB_REPORT_ONLY,
    MISSION_SPECIFIC,
    NO_LOINC_AVAILABLE,
    ULTRASOUND_MEASURES,
    CodeSystem,
    Domain,
    NoCategory,
    ObservationCategory,
    ReferenceBasis,
    by_domain,
    get,
)
from app.ingest.fhir import CATEGORY_DISPLAY, VitalObservation, category_of, observation

NOW = datetime(2026, 11, 14, 8, 30, tzinfo=UTC)


def a_valid_value(key: str) -> float:
    """Un valor plausible para el indicador, sea cual sea su magnitud.

    Antes estas pruebas usaban 1.0 y 42.5 para todo el catalogo, y eso solo
    funcionaba porque nada validaba el rango. Con limites fisicos, un pulso de
    1 lpm o un animo de 42,5 se rechazan — correctamente.
    """
    code = CATALOG[key]
    if code.reference_low is not None and code.reference_high is not None:
        return (code.reference_low + code.reference_high) / 2
    if code.physical_min is not None and code.physical_max is not None:
        return (code.physical_min + code.physical_max) / 2
    return max(code.physical_min or 0.0, 1.0)


@pytest.fixture
def heart_rate() -> VitalObservation:
    return observation("heart-rate", 62.0, NOW, subject="crew-01", source="wearable-01")


def test_produces_valid_fhir(heart_rate: VitalObservation) -> None:
    assert heart_rate.validates()


@pytest.mark.parametrize("key", sorted(CATALOG))
def test_every_catalog_entry_produces_valid_fhir(key: str) -> None:
    """Ningun indicador del catalogo puede generar un recurso invalido."""
    obs = observation(key, a_valid_value(key), NOW, subject="crew-01", source="test")
    assert obs.validates(), f"{key} genera FHIR inválido"


@pytest.mark.parametrize("key", sorted(CATALOG))
def test_roundtrip_preserves_everything(key: str) -> None:
    original = observation(
        key, a_valid_value(key), NOW, subject="crew-02", source="wearable-07"
    )
    restored = VitalObservation.from_fhir(original.to_fhir())
    assert restored == original


def test_fhir_uses_loinc_system_for_standard_vitals(heart_rate: VitalObservation) -> None:
    coding = heart_rate.to_fhir()["code"]["coding"][0]
    assert coding["system"] == "http://loinc.org"
    assert coding["code"] == "8867-4"


def test_mission_specific_codes_are_not_disguised_as_loinc() -> None:
    """Un codigo propio jamas debe presentarse bajo el sistema LOINC."""
    pvt = observation("pvt-mean-rt", 280.0, NOW, subject="crew-01", source="tablet")
    coding = pvt.to_fhir()["code"]["coding"][0]
    assert coding["system"] == "https://emma.mission/codes"
    assert not get("pvt-mean-rt").is_standard


def test_naive_datetime_is_rejected() -> None:
    """Una marca de tiempo sin zona rompe la trazabilidad de 21 CFR 11.10(e)."""
    with pytest.raises(ValueError, match="zona horaria"):
        observation("heart-rate", 62.0, datetime(2026, 11, 14, 8, 30), "crew-01", "w")


def test_unit_mismatch_is_rejected(heart_rate: VitalObservation) -> None:
    resource = heart_rate.to_fhir()
    resource["valueQuantity"]["code"] = "kg"  # unidad que no corresponde
    with pytest.raises(ValueError, match="unidad incompatible"):
        VitalObservation.from_fhir(resource)


def test_unknown_coding_is_rejected(heart_rate: VitalObservation) -> None:
    resource = heart_rate.to_fhir()
    resource["code"]["coding"][0]["code"] = "0000-0"
    with pytest.raises(KeyError, match="no reconocido"):
        VitalObservation.from_fhir(resource)


def test_unknown_catalog_key() -> None:
    with pytest.raises(KeyError, match="desconocido"):
        get("no-existe")


# --------------------------------------------------------------------------- #
# Integridad del catalogo
# --------------------------------------------------------------------------- #


def test_every_domain_has_indicators() -> None:
    """Los cinco dominios del reto deben estar cubiertos, sin excepcion."""
    for domain in Domain:
        assert by_domain(domain), f"el dominio {domain} no tiene indicadores"


def test_catalog_keys_match_their_entries() -> None:
    for key, code in CATALOG.items():
        assert code.key == key


def test_loinc_codes_have_loinc_shape() -> None:
    """Un codigo LOINC real tiene forma N-N a NNNNN-N y un digito de control correcto.

    La version anterior exigia 4 o 5 cifras y rechazaba codigos reales y activos como 731-0
    (linfocitos) y 751-8 (neutrofilos), verificados en su ficha oficial: los LOINC antiguos
    son mas cortos. Lo que atrapa inventos por descuido es el digito de control (mod 10 de
    LOINC), no la longitud.
    """
    import re

    for code in CATALOG.values():
        if code.system is CodeSystem.LOINC:
            assert re.fullmatch(r"\d{1,5}-\d", code.code), (
                f"{code.key}: {code.code!r} no tiene forma de código LOINC"
            )
            body, check = code.code.split("-")
            assert _loinc_check_digit(body) == int(check), (
                f"{code.key}: {code.code!r} tiene un dígito de control incorrecto"
            )


def _loinc_check_digit(body: str) -> int:
    """Digito de control de LOINC: mod 10, duplicando las posiciones impares desde la derecha."""
    digits = [int(c) for c in reversed(body)]
    doubled = "".join(str(d * 2) if i % 2 == 0 else str(d) for i, d in enumerate(digits))
    return (10 - sum(int(c) for c in doubled) % 10) % 10


def test_no_loinc_list_refers_to_real_non_standard_keys() -> None:
    """La lista de los que no tienen LOINC debe referirse a claves reales."""
    for key in NO_LOINC_AVAILABLE:
        assert key in CATALOG, f"{key} figura como sin-LOINC pero no está en el catálogo"
        assert not CATALOG[key].is_standard


def test_every_custom_code_declares_why_it_is_not_loinc() -> None:
    """Anadir un indicador con codigo propio obliga a justificarlo.

    Es la invariante que hace cumplible la regla de no inventar codigos LOINC:
    o el indicador usa un codigo estandar verificado, o dice por que no puede.
    """
    custom = {code.key for code in CATALOG.values() if not code.is_standard}
    declared = set(NO_LOINC_AVAILABLE) | set(MISSION_SPECIFIC)

    assert custom == declared, (
        f"sin justificar: {sorted(custom - declared)} | "
        f"justificados pero ya migrados o inexistentes: {sorted(declared - custom)}"
    )


def test_mission_specific_reasons_are_not_empty() -> None:
    for key, reason in MISSION_SPECIFIC.items():
        assert reason.strip(), f"{key} figura como propio de misión sin razon"


def test_reference_ranges_are_ordered() -> None:
    for code in CATALOG.values():
        if code.reference_low is not None and code.reference_high is not None:
            assert code.reference_low <= code.reference_high, f"{code.key} tiene rango invertido"


def test_concerning_direction_is_valid() -> None:
    for code in CATALOG.values():
        assert code.concerning in {"high", "low", "both"}, code.key


# --------------------------------------------------------------------------- #
# Procedencia de los rangos de referencia
# --------------------------------------------------------------------------- #


def test_a_guideline_is_never_used_as_a_danger_limit() -> None:
    """Una recomendacion no puede convertirse en umbral de alarma.

    Es el error que marcaba al 95 % de los sujetos sanos en `sleep-duration` y al
    52 % en `sleep-efficiency`: 7-9 h es lo que conviene dormir, no el rango en
    que esta la gente sana.
    """
    for code in CATALOG.values():
        if code.reference_basis is not ReferenceBasis.GUIDELINE:
            continue
        assert code.critical_low is None and code.critical_high is None, (
            f"{code.key} declara su rango como guia y aun así define un límite "
            f"de peligro a partir de el"
        )


def test_danger_limits_sit_outside_the_reference_range() -> None:
    """El peligro tiene que ser mas extremo que lo simplemente inusual."""
    for code in CATALOG.values():
        if code.critical_low is not None and code.reference_low is not None:
            assert code.critical_low <= code.reference_low, (
                f"{code.key}: límite de peligro {code.critical_low} por encima "
                f"del inicio del rango normal {code.reference_low}"
            )
        if code.critical_high is not None and code.reference_high is not None:
            assert code.critical_high >= code.reference_high, (
                f"{code.key}: límite de peligro {code.critical_high} por debajo "
                f"del final del rango normal {code.reference_high}"
            )


def test_resting_limits_are_stricter_than_general_ones() -> None:
    """Si existe un limite en reposo, tiene que apretar mas que el general.

    145 lpm corriendo es normal; en reposo es un hallazgo. Al reves no tiene
    sentido.
    """
    for code in CATALOG.values():
        if code.resting_critical_high is not None and code.critical_high is not None:
            assert code.resting_critical_high <= code.critical_high, code.key
        if code.resting_critical_low is not None and code.critical_low is not None:
            assert code.resting_critical_low >= code.critical_low, code.key


def test_every_indicator_with_a_range_declares_its_basis() -> None:
    for code in CATALOG.values():
        if code.reference_low is not None or code.reference_high is not None:
            assert isinstance(code.reference_basis, ReferenceBasis), code.key


def test_sleep_ranges_are_concern_thresholds_not_recommendations() -> None:
    """Regresion de las dos correcciones que salieron de MMASH.

    Sueno: la recomendacion son 7-9 h y los adultos sanos dormian 4-6.
    Eficiencia: el objetivo es 85 % y la mediana sana fue 84,9 %.
    """
    duration = CATALOG["sleep-duration"]
    efficiency = CATALOG["sleep-efficiency"]

    assert duration.reference_low <= 5, "7 h es la recomendacion, no el umbral"
    assert efficiency.reference_low <= 75, "85 % es el objetivo, no el umbral"


# --------------------------------------------------------------------------- #
# Dato invalido != dato extremo
# --------------------------------------------------------------------------- #


def test_nan_is_rejected_loudly() -> None:
    """NaN atravesaba el sistema en silencio.

    Toda comparacion con NaN es falsa, asi que ni los cuantiles ni los limites de
    peligro lo veian: la lectura desaparecia sin dejar rastro ni alerta. En
    monitorizacion clinica, un dato que se esfuma sin avisar es peor que uno que
    da error.
    """
    import math

    with pytest.raises(ValueError, match="no finito"):
        observation("heart-rate", math.nan, NOW, "crew-01", "wearable")


def test_infinity_is_rejected() -> None:
    import math

    with pytest.raises(ValueError, match="no finito"):
        observation("heart-rate", math.inf, NOW, "crew-01", "wearable")


def test_confidence_outside_zero_to_one_is_rejected(heart_rate: VitalObservation) -> None:
    """La confianza es una fracción de 0 a 1, también fuera de la API.

    `POST /api/observations` la acota (`ge=0, le=1`), pero el modelo no: un recurso FHIR con
    `valueDecimal` NaN entraba por `from_fhir`, y como `NaN < 0,5` es falso la lectura se
    trataba como de confianza plena, la que puede sostener sola un hallazgo grave.
    """
    import math

    for bad in (math.nan, -0.1, 1.5, math.inf):
        with pytest.raises(ValueError, match="confianza"):
            observation("heart-rate", 70.0, NOW, "crew-01", "wearable", confidence=bad)
        resource = heart_rate.to_fhir()
        for item in resource["extension"]:
            if item["url"].endswith("/confidence"):
                item["valueDecimal"] = bad
        with pytest.raises(ValueError, match="confianza"):
            VitalObservation.from_fhir(resource)
    for good in (0.0, 0.3, 1.0):
        assert observation(
            "heart-rate", 70.0, NOW, "crew-01", "wearable", confidence=good
        ).confidence == good


def test_physically_impossible_is_invalid_data_not_an_emergency() -> None:
    """Un pulso de -50 no es bradicardia: es un sensor roto.

    Antes cruzaba el limite de peligro y se reportaba como urgencia clinica,
    mandando a la tripulacion a investigar un problema que no existe.
    """
    with pytest.raises(ValueError, match="físicamente posible"):
        observation("heart-rate", -50.0, NOW, "crew-01", "wearable")

    with pytest.raises(ValueError, match="físicamente posible"):
        observation("oxygen-saturation", 120.0, NOW, "crew-01", "wearable")


def test_extreme_but_possible_values_are_accepted() -> None:
    """El limite fisico no puede comerse los hallazgos reales.

    205 lpm es peligroso y perfectamente posible: tiene que entrar y alarmar, no
    rechazarse como dato roto.
    """
    assert observation("heart-rate", 205.0, NOW, "crew-01", "w").value == 205.0
    assert observation("oxygen-saturation", 60.0, NOW, "crew-01", "w").value == 60.0


def test_danger_limits_sit_inside_the_physically_possible_range() -> None:
    """Si el limite de peligro cayera fuera de lo posible, seria inalcanzable."""
    for code in CATALOG.values():
        if code.critical_high is not None and code.physical_max is not None:
            assert code.critical_high <= code.physical_max, code.key
        if code.critical_low is not None and code.physical_min is not None:
            assert code.critical_low >= code.physical_min, code.key


# Indicadores que SI pueden ser negativos, con su razon. Todo lo demas mide una
# magnitud que no admite signo.
SIGNED_INDICATORS = {
    "circadian-shift": "un desfase de fase puede ir en cualquier sentido",
    "orthostatic-drop": "hay quien sube la tension al levantarse en vez de bajarla",
}


def test_every_indicator_declares_a_physical_range() -> None:
    """Sin suelo fisico, un valor imposible se cuela como hallazgo clinico."""
    for code in CATALOG.values():
        assert code.physical_min is not None, f"{code.key} sin suelo físico"
        if code.key not in SIGNED_INDICATORS:
            assert code.physical_min >= 0, (
                f"{code.key} admite negativos y no está en SIGNED_INDICATORS"
            )


def test_signed_indicators_are_declared_with_a_reason() -> None:
    for key, reason in SIGNED_INDICATORS.items():
        assert key in CATALOG
        assert reason.strip()
        assert CATALOG[key].physical_min is not None
        assert CATALOG[key].physical_min < 0


def _category(key: str) -> str:
    resource = observation(key, a_valid_value(key), NOW, "crew-01", "manual").to_fhir()
    return str(resource["category"][0]["coding"][0]["code"])


def test_every_lab_analyte_is_laboratory_whatever_its_domain() -> None:
    """El calcio del dominio óseo salía «activity», el sodio «imaging», la hemoglobina
    «vital-signs» (un perfil que no admite su código): la categoría es la de lo que es."""
    for key in LAB_REPORT_ONLY:
        assert _category(key) == "laboratory", key
    for key in ("calcium", "phosphate", "magnesium", "estradiol", "fsh", "lh"):
        assert CATALOG[key].domain is Domain.BONE
    assert _category("ntx-telopeptide") == "laboratory"
    assert _category("vitamin-d-25oh") == "laboratory"


def test_the_bone_domain_keeps_activity_for_what_is_not_a_lab() -> None:
    assert _category("exercise-minutes") == "activity"
    assert _category("loading-impacts") == "activity"


def test_the_category_is_not_signed() -> None:
    """Corregirla no cambia ningún asiento: el ledger no la guarda."""
    for key in LAB_REPORT_ONLY:
        reading = observation(key, a_valid_value(key), NOW, "crew-01", "manual")
        assert "category" not in json.dumps(_to_payload(reading))


# --- La categoría declarada en el catálogo (decimoctava ronda, §5.38.9) --------------------------

# Los nueve códigos del sistema oficial de FHIR R4 (observation-category 4.0.1), leídos el
# 2026-10-26 en hl7.org/fhir/R4/codesystem-observation-category.html, con su `display`.
OFFICIAL_CATEGORIES = {
    "social-history": "Social History",
    "vital-signs": "Vital Signs",
    "imaging": "Imaging",
    "laboratory": "Laboratory",
    "procedure": "Procedure",
    "survey": "Survey",
    "exam": "Exam",
    "therapy": "Therapy",
    "activity": "Activity",
}


def _resource(key: str) -> dict[str, object]:
    return observation(key, a_valid_value(key), NOW, "crew-01", "manual").to_fhir()


def test_the_categories_are_the_nine_official_ones_with_their_display() -> None:
    assert {item.value: CATEGORY_DISPLAY[item] for item in ObservationCategory} == (
        OFFICIAL_CATEGORIES
    )
    for key in CATALOG:
        category = _resource(key).get("category")
        if category is None:
            continue
        [coding] = category[0]["coding"]  # type: ignore[index]
        assert coding["system"] == "http://terminology.hl7.org/CodeSystem/observation-category"
        assert OFFICIAL_CATEGORIES[coding["code"]] == coding["display"], key


def test_what_was_left_with_its_domain_category_says_what_it_is() -> None:
    """El peso salía «activity» (óseo), la orina de 24 h «imaging» (genitourinario), la carga de
    síntomas «laboratory» (inmune) y el sueño del actígrafo «survey» (conductual)."""
    assert _category("body-weight") == "vital-signs"
    assert _category("urine-volume-24h") == "laboratory"
    assert _category("urine-specific-gravity") == "laboratory"
    assert _category("symptom-burden") == "survey"
    assert _category("sleep-duration") == "activity"
    assert _category("sleep-efficiency") == "activity"
    # Lo que es lo típico de su dominio sigue igual.
    assert _category("bladder-volume") == "imaging"  # ecografía
    assert _category("heart-rate") == "vital-signs"
    assert _category("mood-valence") == "survey"
    assert _category("cortisol-salivary") == "laboratory"


def test_an_intake_record_goes_without_a_category_and_still_validates() -> None:
    """Ninguna de las nueve describe el registro de lo que se come o se bebe: sin la clave, en
    vez de «imaging» o «survey». `Observation.category` es 0..*, y el recurso sigue validando."""
    for key in ("fluid-intake-24h", "energy-intake-daily", "food-rejected-fraction"):
        assert CATALOG[key].category is NoCategory.NONE_FITS
        assert category_of(CATALOG[key]) is None
        assert "category" not in _resource(key), key
        assert observation(key, a_valid_value(key), NOW, "crew-01", "manual").validates()


def test_only_an_ultrasound_measure_is_imaging() -> None:
    """El dominio neuro-ocular y el genitourinario dan «imaging» por defecto: un indicador nuevo
    de esos dominios que no sea una ecografía (un analito de orina, un cuestionario) tiene que
    declarar la suya en el catálogo, o cae aquí. La otra imagen del catálogo es la densitometría
    (DXA, rayos X), que la declara: la densidad ósea y, desde la decimonovena ronda, la masa
    magra de la composición corporal del mismo equipo."""
    imaging = {key for key, code in CATALOG.items()
               if category_of(code) is ObservationCategory.IMAGING}
    assert imaging == set(ULTRASOUND_MEASURES) | DENSITOMETRY_KEYS | {"dxa-lean-mass"}


def test_a_declared_category_does_not_contradict_the_ultrasound_or_lab_rule() -> None:
    """La declarada manda; que no diga otra cosa que «imaging» para una ecografía ni que
    «laboratory» para un analito de analítica."""
    for key in ULTRASOUND_MEASURES:
        assert CATALOG[key].category in (None, ObservationCategory.IMAGING), key
    for key in LAB_REPORT_ONLY:
        assert CATALOG[key].category in (None, ObservationCategory.LABORATORY), key
