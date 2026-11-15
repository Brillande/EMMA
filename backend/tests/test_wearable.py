"""Ingesta desde wearables: parseo GATT, HRV y exportaciones."""

import datetime as dt

import pytest

from app.ingest.wearable import (
    HRV_MAX_GAP,
    HRV_MIN_RR,
    NO_CONTACT_CONFIDENCE,
    RR_PLAUSIBLE_MS,
    HrvReading,
    RrWindow,
    WearableAdapter,
    confidence_from_contact,
    parse_heart_rate_measurement,
    plausible_rr,
    rmssd,
    sdnn,
)

NOW = dt.datetime(2026, 11, 14, 8, 30, tzinfo=dt.UTC)


def rr_bytes(*intervals_ms: float) -> bytes:
    """Codifica intervalos R-R en el formato GATT (1/1024 s, little endian)."""
    out = bytearray()
    for ms in intervals_ms:
        out += int(ms / 1000 * 1024).to_bytes(2, "little")
    return bytes(out)


# --------------------------------------------------------------------------- #
# Parseo de la trama GATT 0x2A37
# --------------------------------------------------------------------------- #


def test_parses_uint8_heart_rate() -> None:
    measurement = parse_heart_rate_measurement(bytes([0b0000_0000, 72]))
    assert measurement.heart_rate == 72
    assert measurement.rr_intervals_ms == ()
    assert measurement.sensor_contact is None  # sin soporte de contacto


def test_parses_uint16_heart_rate() -> None:
    frame = bytes([0b0000_0001]) + (300).to_bytes(2, "little")
    assert parse_heart_rate_measurement(frame).heart_rate == 300


def test_parses_sensor_contact() -> None:
    supported_and_detected = parse_heart_rate_measurement(bytes([0b0000_0110, 72]))
    supported_not_detected = parse_heart_rate_measurement(bytes([0b0000_0100, 72]))
    assert supported_and_detected.sensor_contact is True
    assert supported_not_detected.sensor_contact is False


def test_parses_energy_expended() -> None:
    frame = bytes([0b0000_1000, 72]) + (250).to_bytes(2, "little")
    assert parse_heart_rate_measurement(frame).energy_expended == 250


def test_parses_rr_intervals() -> None:
    frame = bytes([0b0001_0000, 60]) + rr_bytes(1000.0, 1010.0)
    measurement = parse_heart_rate_measurement(frame)
    assert len(measurement.rr_intervals_ms) == 2
    assert measurement.rr_intervals_ms[0] == pytest.approx(1000, abs=1)


def test_parses_energy_and_rr_together() -> None:
    """El desplazamiento de los R-R depende de si la energia esta presente."""
    frame = bytes([0b0001_1000, 60]) + (250).to_bytes(2, "little") + rr_bytes(1000.0)
    measurement = parse_heart_rate_measurement(frame)
    assert measurement.energy_expended == 250
    assert measurement.rr_intervals_ms[0] == pytest.approx(1000, abs=1)


def test_empty_frame_is_rejected() -> None:
    with pytest.raises(ValueError, match="vacía"):
        parse_heart_rate_measurement(b"")


def test_truncated_frame_is_rejected() -> None:
    with pytest.raises(ValueError, match="truncada"):
        parse_heart_rate_measurement(bytes([0b0000_0001]))  # anuncia uint16, no lo trae


def test_odd_rr_payload_is_rejected() -> None:
    frame = bytes([0b0001_0000, 60]) + b"\x01"
    with pytest.raises(ValueError, match="dos en dos"):
        parse_heart_rate_measurement(frame)


# --------------------------------------------------------------------------- #
# HRV
# --------------------------------------------------------------------------- #


def test_rmssd_of_constant_intervals_is_zero() -> None:
    assert rmssd([800.0] * 10) == 0.0


def test_rmssd_of_known_series() -> None:
    # Diferencias sucesivas: +100, -100, +100 -> RMSSD = 100
    assert rmssd([800.0, 900.0, 800.0, 900.0]) == pytest.approx(100.0)


def test_sdnn_of_constant_intervals_is_zero() -> None:
    assert sdnn([800.0] * 10) == 0.0


def test_hrv_needs_enough_intervals() -> None:
    """Mejor no informar HRV que calcularla sobre dos latidos."""
    assert rmssd([800.0, 810.0]) is None
    assert sdnn([800.0, 810.0]) is None
    assert rmssd([]) is None


def test_implausible_intervals_are_filtered() -> None:
    low, high = RR_PLAUSIBLE_MS
    assert plausible_rr([low - 1, 800.0, high + 1]) == [800.0]


def test_artifacts_do_not_create_phantom_hrv() -> None:
    """Un artefacto de movimiento no debe inflar la HRV."""
    clean = [800.0, 810.0, 795.0, 805.0, 800.0]
    with_artifact = [*clean, 50.0, 5000.0]  # valores imposibles
    assert rmssd(with_artifact) == rmssd(clean)


# --------------------------------------------------------------------------- #
# Adaptador
# --------------------------------------------------------------------------- #


def test_ble_frame_yields_heart_rate_only_without_rr() -> None:
    adapter = WearableAdapter(subject="crew-01")
    observations = adapter.from_ble_frame(bytes([0b0000_0000, 72]), NOW)
    assert [obs.key for obs in observations] == ["heart-rate"]
    assert observations[0].value == 72.0


def test_a_single_frame_with_rr_yields_no_hrv() -> None:
    """Cuatro latidos no son HRV: sin ventana, una trama da solo el pulso."""
    adapter = WearableAdapter(subject="crew-01")
    frame = bytes([0b0001_0000, 60]) + rr_bytes(1000, 1010, 990, 1005)
    assert [obs.key for obs in adapter.from_ble_frame(frame, NOW)] == ["heart-rate"]


def test_ble_frames_through_the_window_yield_hrv() -> None:
    adapter = WearableAdapter(subject="crew-01")
    window = RrWindow()
    keys: set[str] = set()
    observations = []
    for second in range(HRV_MIN_RR):
        frame = bytes([0b0001_0000, 60]) + rr_bytes(1000 + (10 if second % 2 else -10))
        observations = adapter.from_ble_frame(
            frame, NOW + dt.timedelta(seconds=second), window
        )
        keys |= {obs.key for obs in observations}

    assert keys == {"heart-rate", "hrv-rmssd", "hrv-sdnn"}
    assert all(obs.validates() for obs in observations)
    assert all(obs.source == "wearable-ble" for obs in observations)
    # La HRV lleva el instante de la trama que cierra la ventana.
    assert {obs.effective for obs in observations} == {
        NOW + dt.timedelta(seconds=HRV_MIN_RR - 1)
    }


def test_the_window_emits_at_most_once_per_interval_and_resets_on_a_gap() -> None:
    window = RrWindow()

    def feed(start: dt.datetime, seconds: int) -> list[HrvReading]:
        out = []
        for second in range(seconds):
            hrv = window.add(
                "crew-01", "band", start + dt.timedelta(seconds=second), (1000.0, 1020.0), True
            )
            if hrv is not None:
                out.append(hrv)
        return out

    # 15 tramas x 2 latidos = 30: la primera HRV en la trama 15; la siguiente, 60 s despues.
    emitted = feed(NOW, 90)
    assert [item.effective - NOW for item in emitted] == [
        dt.timedelta(seconds=14), dt.timedelta(seconds=74)
    ]
    # Un silencio mas largo que HRV_MAX_GAP vacia la ventana: hay que volver a llenarla.
    later = NOW + dt.timedelta(seconds=89) + HRV_MAX_GAP + dt.timedelta(seconds=1)
    assert [item.effective - later for item in feed(later, 15)] == [
        dt.timedelta(seconds=14)
    ]


def test_the_window_drops_old_intervals_and_no_contact_frames() -> None:
    window = RrWindow()
    emitted = [
        hrv
        for second in range(400)
        if (hrv := window.add(
            "crew-01", None, NOW + dt.timedelta(seconds=second), (1000.0,), True
        )) is not None
    ]
    # Se emite en los segundos 29, 89, ..., 389; en el ultimo, la ventana guarda solo los
    # latidos de los 5 min anteriores (segundos 89 a 389, ambos incluidos).
    assert emitted[-1].effective == NOW + dt.timedelta(seconds=389)
    assert emitted[-1].beats == 301

    for second in range(29):
        window.add("crew-01", None, NOW + dt.timedelta(seconds=500 + second), (1000.0,), True)
    # Una trama sin contacto rompe la serie, aunque traiga latidos.
    assert window.add("crew-01", None, NOW + dt.timedelta(seconds=529), (1000.0,), False) is None
    assert window.add("crew-01", None, NOW + dt.timedelta(seconds=530), (1000.0,), True) is None


def test_each_crew_member_and_device_has_its_own_window() -> None:
    window = RrWindow()
    for second in range(14):
        moment = NOW + dt.timedelta(seconds=second)
        window.add("crew-01", "a", moment, (1000.0, 1010.0), True)
        assert window.add("crew-02", "a", moment, (1000.0, 1010.0), True) is None
    moment = NOW + dt.timedelta(seconds=14)
    assert window.add("crew-01", "b", moment, (1000.0, 1010.0), True) is None
    assert window.add("crew-01", "a", moment, (1000.0, 1010.0), True)


def test_apple_health_import() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <HealthData>
      <Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" value="64"
              startDate="2026-09-01 08:30:00 +0000"/>
      <Record type="HKQuantityTypeIdentifierOxygenSaturation" unit="%" value="0.97"
              startDate="2026-09-01 08:31:00 +0000"/>
      <Record type="HKQuantityTypeIdentifierStepCount" unit="count" value="1200"
              startDate="2026-09-01 08:32:00 +0000"/>
    </HealthData>"""

    observations = list(WearableAdapter(subject="crew-01").from_apple_health_export(xml))

    assert [obs.key for obs in observations] == ["heart-rate", "oxygen-saturation"]
    # Apple da SpO2 como fraccion; el catalogo lo espera en porcentaje.
    assert observations[1].value == pytest.approx(97.0)


def test_apple_health_reports_unparseable_values() -> None:
    """Antes lo no numerico se saltaba en silencio; ahora se dice."""
    xml = """<HealthData>
      <Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" value="no-es-un-número"
              startDate="2026-09-01 08:30:00 +0000"/>
      <Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" value="64"
              startDate="2026-09-01 08:31:00 +0000"/>
    </HealthData>"""
    rejected: list[str] = []
    observations = list(WearableAdapter(subject="crew-01").from_apple_health_export(xml, rejected))
    assert len(observations) == 1
    assert len(rejected) == 1 and "no numérico" in rejected[0]


def test_google_fit_import() -> None:
    payload = {
        "point": [
            {
                "dataTypeName": "com.google.heart_rate.bpm",
                "startTimeNanos": "1788249600000000000",
                "value": [{"fpVal": 66.0}],
            },
            {
                "dataTypeName": "com.google.step_count.delta",
                "startTimeNanos": "1788249660000000000",
                "value": [{"intVal": 1200}],
            },
        ]
    }
    observations = list(WearableAdapter(subject="crew-01").from_google_fit(payload))
    assert len(observations) == 1
    assert observations[0].key == "heart-rate"
    assert observations[0].value == 66.0
    assert observations[0].effective.tzinfo is not None


# --------------------------------------------------------------------------- #
# Confianza de medida
# --------------------------------------------------------------------------- #


def test_no_contact_lowers_confidence() -> None:
    """El bit de contacto del GATT se parseaba y se tiraba. Ahora vale para algo."""
    assert confidence_from_contact(False) == NO_CONTACT_CONFIDENCE
    assert confidence_from_contact(True) == 1.0


def test_unsupported_contact_detection_is_not_distrust() -> None:
    """`None` significa que el dispositivo no lo soporta, no que falte contacto."""
    assert confidence_from_contact(None) == 1.0


def test_ble_frame_without_contact_yields_low_confidence() -> None:
    adapter = WearableAdapter(subject="crew-01")
    # Soporta contacto (bit 2) y NO lo detecta (bit 1 a cero).
    frame = bytes([0b0000_0100, 72])
    observation = adapter.from_ble_frame(frame, NOW)[0]

    assert observation.is_low_confidence
    assert observation.confidence == NO_CONTACT_CONFIDENCE


def test_ble_frame_with_contact_yields_full_confidence() -> None:
    adapter = WearableAdapter(subject="crew-01")
    frame = bytes([0b0000_0110, 72])  # soporta y detecta contacto
    observation = adapter.from_ble_frame(frame, NOW)[0]

    assert not observation.is_low_confidence
    assert observation.confidence == 1.0


def test_confidence_survives_the_fhir_roundtrip() -> None:
    """Si no viaja en el recurso, se pierde en el primer limite del sistema."""
    from app.ingest.fhir import VitalObservation

    adapter = WearableAdapter(subject="crew-01")
    original = adapter.from_ble_frame(bytes([0b0000_0100, 72]), NOW)[0]
    restored = VitalObservation.from_fhir(original.to_fhir())

    assert restored.confidence == original.confidence
    assert restored.is_low_confidence


# --------------------------------------------------------------------------- #
# Quinta revision (2026-09-22): unidades, fechas y descartes
# --------------------------------------------------------------------------- #


def _apple(*records: str) -> str:
    return "<HealthData>" + "".join(records) + "</HealthData>"


def _rec(kind: str, value: str, unit: str | None, date: str = "2026-09-01 08:00:00 +0000") -> str:
    unit_attr = f' unit="{unit}"' if unit is not None else ""
    return (
        f'<Record type="HKQuantityTypeIdentifier{kind}"{unit_attr} value="{value}" '
        f'startDate="{date}"/>'
    )


def test_apple_units_are_converted_to_the_catalog() -> None:
    """Ignorar la unidad metia 170 lb como 170 kg sin ningun aviso."""
    xml = _apple(
        _rec("BodyMass", "170", "lb"),
        _rec("BodyMass", "70500", "g"),
        _rec("BodyTemperature", "98.6", "degF"),
    )

    values = [obs.value for obs in WearableAdapter(subject="crew-01").from_apple_health_export(xml)]

    assert values == pytest.approx([77.1107, 70.5, 37.0], abs=1e-3)


def test_an_unknown_or_missing_unit_is_reported() -> None:
    xml = _apple(
        _rec("BodyMass", "11", "st"),
        _rec("HeartRate", "64", None),
        _rec("HeartRate", "65", "count/min"),
    )
    rejected: list[str] = []

    observations = list(WearableAdapter(subject="crew-01").from_apple_health_export(xml, rejected))

    assert [obs.value for obs in observations] == [65.0]
    assert len(rejected) == 2
    assert all("unidad" in reason for reason in rejected)


def test_readings_with_incredible_dates_are_reported() -> None:
    """Una lectura de 2099 tapaba las desviaciones de hoy; una del ano 1 daba 500."""
    xml = _apple(
        _rec("HeartRate", "60", "count/min", "2099-01-01 08:00:00 +0000"),
        _rec("HeartRate", "61", "count/min", "1999-12-31 08:00:00 +0000"),
        _rec("HeartRate", "62", "count/min", "0001-01-01 00:00:00 +2359"),
        _rec("HeartRate", "63", "count/min"),
    )
    rejected: list[str] = []

    observations = list(WearableAdapter(subject="crew-01").from_apple_health_export(xml, rejected))

    assert [obs.value for obs in observations] == [63.0]
    assert len(rejected) == 3
    assert all("fecha" in reason for reason in rejected)


def test_without_a_collector_nothing_is_dropped_silently() -> None:
    xml = _apple(_rec("HeartRate", "no-es-un-número", "count/min"))
    with pytest.raises(ValueError, match="no numérico"):
        list(WearableAdapter(subject="crew-01").from_apple_health_export(xml))


def test_google_fit_rejects_non_numeric_and_out_of_range_points() -> None:
    """Instantes y valores gigantes tumbaban la importacion entera con un 500."""
    good = 1_788_249_600_000_000_000  # 2026-09-01 08:00 UTC
    hr = "com.google.heart_rate.bpm"
    ok = [{"fpVal": 70.0}]
    payload = {
        "point": [
            {"dataTypeName": hr, "startTimeNanos": str(good), "value": [{"fpVal": 70.0}]},
            {"dataTypeName": hr, "startTimeNanos": "1e29", "value": [{"fpVal": 70.0}]},
            {"dataTypeName": hr, "startTimeNanos": 10**400, "value": [{"fpVal": 70.0}]},
            {"dataTypeName": hr, "startTimeNanos": str(good), "value": [{"fpVal": 10**400}]},
            {"dataTypeName": hr, "startTimeNanos": str(good), "value": [{"fpVal": "70"}]},
            {"dataTypeName": hr, "startTimeNanos": "-62135596800000000000", "value": ok},
            {"dataTypeName": hr, "startTimeNanos": "4102444800000000000", "value": ok},
        ]
    }
    rejected: list[str] = []

    observations = list(WearableAdapter(subject="crew-01").from_google_fit(payload, rejected))

    assert [obs.value for obs in observations] == [70.0]
    assert len(rejected) == 6


# --------------------------------------------------------------------------- #
# El ciclo y la anticoncepción (lote «ciclo», unidad B1, 2026-11-15)
# --------------------------------------------------------------------------- #


def _cat(
    kind: str, value: str, start: str | None = None, date: str = "2026-09-01 08:00:00 +0000"
) -> str:
    """Un registro de categoría como los del export real, con la marca de inicio si se da."""
    meta = f'<MetadataEntry key="HKMenstrualCycleStart" value="{start}"/>' if start else ""
    return (
        f'<Record type="HKCategoryTypeIdentifier{kind}" sourceName="Salud" value="{value}" '
        f'startDate="{date}" endDate="2026-09-02 08:00:00 +0000">{meta}</Record>'
    )


def _cycle(xml: str) -> tuple[list[tuple[str, float]], list[str]]:
    rejected: list[str] = []
    readings = WearableAdapter(subject="crew-01").from_apple_health_export(xml, rejected)
    return [(obs.key, obs.value) for obs in readings], rejected


FLOW_FAMILIES = ["HKCategoryValueMenstrualFlow", "HKCategoryValueVaginalBleeding"]


@pytest.mark.parametrize("family", FLOW_FAMILIES)
@pytest.mark.parametrize(
    ("name", "number"), [("None", 0.0), ("Light", 1.0), ("Medium", 2.0), ("Heavy", 3.0)]
)
def test_menstrual_flow_reads_both_value_families(family: str, name: str, number: float) -> None:
    """iOS 18 renombró el enum (no el tipo): un export trae cualquiera de los dos nombres."""
    readings, rejected = _cycle(_apple(_cat("MenstrualFlow", f"{family}{name}", start="0")))
    assert readings == [("menstrual-flow", number), ("menstruation-start", 0.0)]
    assert rejected == []


def test_a_flow_without_the_start_flag_says_the_start_is_unknown() -> None:
    """HealthKit exige la marca en todo flujo: si falta, la cantidad entra y la falta se dice."""
    readings, rejected = _cycle(_apple(_cat("MenstrualFlow", "HKCategoryValueMenstrualFlowLight")))
    assert readings == [("menstrual-flow", 1.0)]
    assert len(rejected) == 1 and "sin la marca HKMenstrualCycleStart" in rejected[0]


def test_another_types_unscaled_value_is_unknown_not_unscaled() -> None:
    """El motivo es el del tipo del registro, no el de otro enum que comparte el valor."""
    readings, rejected = _cycle(_apple(_cat("Contraceptive", f"{_OVULATION}Indeterminate")))
    assert readings == []
    assert len(rejected) == 1 and "desconocido para contraceptive-in-use" in rejected[0]


def test_the_cycle_start_flag_is_read_before_the_record_is_cleared() -> None:
    """`clear()` borraba el `<MetadataEntry>` antes de mirarlo: el inicio se perdía."""
    readings, rejected = _cycle(_apple(
        _cat("MenstrualFlow", "HKCategoryValueMenstrualFlowHeavy", start="1"),
        _cat("MenstrualFlow", "HKCategoryValueVaginalBleedingMedium", start="0"),
    ))
    assert readings == [
        ("menstrual-flow", 3.0), ("menstruation-start", 1.0),
        ("menstrual-flow", 2.0), ("menstruation-start", 0.0),
    ]
    assert rejected == []


def test_the_start_of_an_unspecified_flow_is_kept() -> None:
    """La cantidad sin especificar no tiene número; el inicio de la regla sí es un dato."""
    readings, rejected = _cycle(
        _apple(_cat("MenstrualFlow", "HKCategoryValueMenstrualFlowUnspecified", start="1"))
    )
    assert readings == [("menstruation-start", 1.0)]
    assert len(rejected) == 1 and "no tiene número" in rejected[0]


def test_an_unreadable_start_flag_is_reported_and_the_flow_kept() -> None:
    readings, rejected = _cycle(
        _apple(_cat("MenstrualFlow", "HKCategoryValueMenstrualFlowLight", start="sí"))
    )
    assert readings == [("menstrual-flow", 1.0)]
    assert len(rejected) == 1 and "HKMenstrualCycleStart" in rejected[0]


def test_the_cycle_start_is_dated_by_the_start_date() -> None:
    xml = _apple(_cat(
        "MenstrualFlow", "HKCategoryValueMenstrualFlowLight", start="1",
        date="2026-09-03 06:15:00 +0200",
    ))
    readings = list(WearableAdapter(subject="crew-01").from_apple_health_export(xml))
    assert {obs.effective for obs in readings} == {dt.datetime(2026, 9, 3, 4, 15, tzinfo=dt.UTC)}


_OVULATION = "HKCategoryValueOvulationTestResult"
_CONTRACEPTIVE = "HKCategoryValueContraceptive"


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [
        ("IntermenstrualBleeding", "HKCategoryValueNotApplicable", ("intermenstrual-bleeding", 1)),
        ("OvulationTestResult", f"{_OVULATION}Negative", ("ovulation-test", 0)),
        ("OvulationTestResult", f"{_OVULATION}EstrogenSurge", ("ovulation-test", 1)),
        ("OvulationTestResult", f"{_OVULATION}LuteinizingHormoneSurge", ("ovulation-test", 2)),
        # Obsoleto desde iOS 13: «Use luteinizingHormoneSurge instead.»
        ("OvulationTestResult", f"{_OVULATION}Positive", ("ovulation-test", 2)),
        ("Contraceptive", f"{_CONTRACEPTIVE}Unspecified", ("contraceptive-in-use", 1)),
        ("Contraceptive", f"{_CONTRACEPTIVE}Implant", ("contraceptive-in-use", 2)),
        ("Contraceptive", f"{_CONTRACEPTIVE}Injection", ("contraceptive-in-use", 3)),
        ("Contraceptive", f"{_CONTRACEPTIVE}IntrauterineDevice", ("contraceptive-in-use", 4)),
        ("Contraceptive", f"{_CONTRACEPTIVE}IntravaginalRing", ("contraceptive-in-use", 5)),
        ("Contraceptive", f"{_CONTRACEPTIVE}Oral", ("contraceptive-in-use", 6)),
        ("Contraceptive", f"{_CONTRACEPTIVE}Patch", ("contraceptive-in-use", 7)),
    ],
)
def test_cycle_categories_get_their_catalog_number(
    kind: str, value: str, expected: tuple[str, float]
) -> None:
    readings, rejected = _cycle(_apple(_cat(kind, value)))
    assert readings == [expected]
    assert rejected == []


@pytest.mark.parametrize(
    ("kind", "value", "reason"),
    [
        ("OvulationTestResult", f"{_OVULATION}Indeterminate", "no tiene número"),
        ("MenstrualFlow", "HKCategoryValueVaginalBleedingUnspecified", "no tiene número"),
        ("Contraceptive", f"{_CONTRACEPTIVE}Condom", "desconocido"),
        ("IntermenstrualBleeding", "HKCategoryValueMenstrualFlowLight", "desconocido"),
        ("OvulationTestResult", "2", "desconocido"),
        ("Contraceptive", "", "sin valor"),
    ],
)
def test_cycle_values_without_a_number_are_reported(kind: str, value: str, reason: str) -> None:
    """Nunca se inventa un punto de la escala ni se descarta en silencio."""
    # Con la marca de inicio (solo la lee el flujo), para que el único rechazo sea el valor.
    readings, rejected = _cycle(_apple(_cat(kind, value, start="1")))
    assert [reading for reading in readings if reading[0] != "menstruation-start"] == []
    assert len(rejected) == 1 and reason in rejected[0] and kind in rejected[0]


def test_without_a_collector_an_unscaled_cycle_value_raises() -> None:
    xml = _apple(_cat("OvulationTestResult", f"{_OVULATION}Indeterminate"))
    with pytest.raises(ValueError, match="no tiene número"):
        list(WearableAdapter(subject="crew-01").from_apple_health_export(xml))


def test_a_vaginal_bleeding_type_is_not_read() -> None:
    """Apple no tiene un tipo `vaginalBleeding` (leído el 2026-11-15): no se inventa."""
    xml = _apple(_cat("VaginalBleeding", "HKCategoryValueVaginalBleedingLight"))
    readings, rejected = _cycle(xml)
    assert readings == [] and rejected == []


def test_basal_body_temperature_converts_its_units() -> None:
    readings, rejected = _cycle(_apple(
        _rec("BasalBodyTemperature", "36.4", "degC"),
        _rec("BasalBodyTemperature", "97.7", "degF"),
        _rec("BasalBodyTemperature", "309.5", "K"),
    ))
    assert [key for key, _ in readings] == ["basal-body-temperature"] * 2
    assert [value for _, value in readings] == pytest.approx([36.4, 36.5], abs=1e-3)
    assert len(rejected) == 1 and "unidad" in rejected[0]
