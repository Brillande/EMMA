"""El cargador de LifeSnaps y las variantes de familia, sin el conjunto y sin red.

La muestra (`tests/data/lifesnaps_sample.jsonl`) es sintetica: los documentos que da el volcado,
en texto. Se codifican a BSON aqui para que el lector pase por bytes reales. El pulso se genera:
serian decenas de lineas por ventana.
"""

import datetime as dt
import gzip
import io
import json
import struct
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.analysis.baseline import BaselineEngine
from app.core import egress
from app.ingest.fhir import Context, VitalObservation, observation
from app.validation.family_variants import (
    FAMILY_FALLBACK,
    Variant,
    evaluate,
    rmssd_collapse,
    spread,
)
from app.validation.lifesnaps import (
    DATASET,
    FITBIT_MEMBER,
    MIN_SAMPLES_PER_WINDOW,
    SEMA_MEMBER,
    LifeSnapsLoader,
    normalize,
    read_documents,
)

SAMPLE = Path(__file__).parent / "data" / "lifesnaps_sample.jsonl"
START = dt.datetime(2021, 5, 1, tzinfo=dt.UTC)


def _element(name: str, value: Any) -> bytes:
    key = name.encode() + b"\x00"
    if value is None:
        return b"\x0a" + key
    if isinstance(value, bool):
        return b"\x08" + key + bytes([value])
    if isinstance(value, int):
        return b"\x10" + key + struct.pack("<i", value)
    if isinstance(value, float):
        return b"\x01" + key + struct.pack("<d", value)
    if isinstance(value, str):
        raw = value.encode() + b"\x00"
        return b"\x02" + key + struct.pack("<i", len(raw)) + raw
    if isinstance(value, dict):
        return b"\x03" + key + _document(value)
    raise TypeError(type(value))


def _document(content: dict[str, Any]) -> bytes:
    body = b"".join(_element(name, value) for name, value in content.items()) + b"\x00"
    return struct.pack("<i", len(body) + 4) + body


def _heart(moment: str, bpm: int, confidence: int = 1) -> dict[str, Any]:
    return {
        "id": "persona-a", "type": "heart_rate",
        "data": {"dateTime": moment, "value": {"bpm": bpm, "confidence": confidence}},
    }


def _archive(path: Path) -> Path:
    files: dict[str, list[dict[str, Any]]] = {"fitbit": [], "sema": []}
    for line in SAMPLE.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        files[entry["file"]].append(entry["doc"])
    for clock, bpm in (("2021-05-24T01:0", 50), ("2021-05-24T10:0", 120),
                       ("2021-05-24T12:0", 70), ("2021-05-24T12:3", 72),
                       ("2021-05-24T15:0", 95), ("2021-05-24T18:0", 66)):
        for second in range(0, MIN_SAMPLES_PER_WINDOW):
            files["fitbit"].append(_heart(f"{clock}1:{second:02d}", bpm))
    # Una ventana con pocas muestras y una sin senal no llegan a ser lectura.
    files["fitbit"].append(_heart("2021-05-24T19:00:01", 66))
    for second in range(0, 30):
        files["fitbit"].append(_heart(f"2021-05-24T20:00:{second:02d}", 66, confidence=0))
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(FITBIT_MEMBER, b"".join(_document(d) for d in files["fitbit"]))
        bundle.writestr(SEMA_MEMBER, b"".join(_document(d) for d in files["sema"]))
    return path


@pytest.fixture
def loader(tmp_path: Path) -> LifeSnapsLoader:
    target = tmp_path / "normalized"
    assert normalize(_archive(tmp_path / "sample.zip"), target) == 1
    return LifeSnapsLoader(target)


def test_reader_rebuilds_nested_documents() -> None:
    original = {"id": "x", "n": 3, "f": 1.5, "flag": True, "none": None, "data": {"a": "b"}}
    assert list(read_documents(io.BytesIO(_document(original)))) == [original]


def test_reader_fails_aloud_on_a_truncated_dump() -> None:
    with pytest.raises(ValueError, match="cortado"):
        list(read_documents(io.BytesIO(_document({"a": 1})[:-2])))


def test_reader_fails_aloud_on_an_unknown_type() -> None:
    unknown = b"\x05a\x00" + b"\x00" * 5 + b"\x00"
    with pytest.raises(ValueError, match="tipo BSON"):
        list(read_documents(io.BytesIO(struct.pack("<i", len(unknown) + 4) + unknown)))


def test_loader_gives_only_heart_and_rmssd_with_the_right_state(loader: LifeSnapsLoader) -> None:
    data = loader.load("persona-a")
    assert {o.key for o in data.observations} == {"heart-rate", "hrv-rmssd"}
    state = {(o.key, o.effective.strftime("%H:%M")): o.context for o in data.observations}
    assert state == {
        ("heart-rate", "01:00"): Context.SLEEP,
        ("hrv-rmssd", "01:05"): Context.SLEEP,
        ("heart-rate", "10:00"): Context.ACTIVE,
        # A 30 min de la respuesta WORK/SCHOOL de las 12:40 no, a 10 sí.
        ("heart-rate", "12:00"): Context.REST,
        ("heart-rate", "12:30"): Context.WORK,
        # Un minuto activo dentro de la ventana manda, aunque el primero sea quieto.
        ("heart-rate", "15:00"): Context.ACTIVE,
        # Sin pasos registrados: desconocido, no reposo.
        ("heart-rate", "18:00"): Context.UNKNOWN,
    }


def test_low_coverage_rmssd_is_left_out(loader: LifeSnapsLoader) -> None:
    values = [o.value for o in loader.load("persona-a").observations if o.key == "hrv-rmssd"]
    assert values == [62.5]


def test_clock_is_the_personal_one_labelled_utc(loader: LifeSnapsLoader) -> None:
    first = loader.load("persona-a").observations[0]
    assert first.effective == dt.datetime(2021, 5, 24, 1, 0, tzinfo=dt.UTC)


def test_normalized_files_are_small_and_readable(loader: LifeSnapsLoader) -> None:
    with gzip.open(loader.folder / "persona-a.json.gz", "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["work"] and payload["sleep"] and payload["exercise"]


def test_missing_dataset_says_how_to_get_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="fetch_lifesnaps"):
        LifeSnapsLoader(tmp_path)


def test_the_dataset_card_is_the_ground_one() -> None:
    assert DATASET.id == "lifesnaps-2022"


def test_download_goes_through_the_allowlist() -> None:
    assert egress.ALLOWLIST["datasets"] == frozenset({"zenodo.org"})


# --------------------------------------------------------------------------- #
# Variantes
# --------------------------------------------------------------------------- #


def _reading(hour: float, day: int, context: Context, value: float) -> VitalObservation:
    moment = START + dt.timedelta(days=day, hours=hour)
    return observation("heart-rate", value, moment, "s", "t", context=context)


def _rest_all_day(days: int = 3) -> list[VitalObservation]:
    return [
        _reading(step / 12, day, Context.REST, 60 + (step % 7))
        for day in range(days)
        for step in range(24 * 12)
    ]


def _mixed() -> list[VitalObservation]:
    readings = _rest_all_day()
    readings += [_reading(10 + i / 12, 3, Context.WORK, 75 + i % 3) for i in range(10)]
    readings += [_reading(10 + i / 12, day, Context.WORK, 70.0)
                 for day in range(3) for i in range(30)]
    readings += [_reading(20 + i / 12, 3, Context.MEAL, 85 + i) for i in range(4)]
    readings += [_reading(3 + i / 12, 3, Context.SLEEP, 50.0) for i in range(4)]
    return readings


def _keyed(items: list[Any]) -> list[tuple[Any, ...]]:
    return sorted(
        (d.key, d.effective, d.value, d.severity, d.used_population_range, d.basis,
         d.baseline.samples if d.baseline else None)
        for d in items
    )


def test_current_variant_is_exactly_the_engine() -> None:
    """Lo que hace creibles las otras filas: la copia del bucle no se ha separado del motor."""
    readings = _mixed()
    assert _keyed(evaluate(readings, Variant.CURRENT)) == _keyed(
        BaselineEngine().evaluate_rolling(readings)
    )


def test_family_fallback_includes_the_state_group() -> None:
    assert set(FAMILY_FALLBACK) == {Context.REST, Context.WORK, Context.MEAL}
    assert set(FAMILY_FALLBACK[Context.WORK]) == {Context.REST, Context.MEAL}


def _work_reading_base(variant: Variant, readings: list[VitalObservation]) -> bool:
    deviations = evaluate(readings, variant)
    work = [d for d in deviations if d.effective.day == 4 and d.effective.hour == 10]
    return all(not d.used_population_range for d in work)


def test_variants_differ_where_they_should() -> None:
    """Pocas de trabajo y mucho reposo: la vigente cae a población, A y B no."""
    readings = _rest_all_day() + [
        _reading(10 + i / 12, 3, Context.WORK, 72.0) for i in range(6)
    ]
    assert not _work_reading_base(Variant.CURRENT, readings)
    assert _work_reading_base(Variant.FAMILY, readings)
    assert _work_reading_base(Variant.COVERED, readings)


def test_coverage_refuses_a_family_from_the_other_half_of_the_day() -> None:
    readings = [
        _reading(14 + step / 12, day, Context.REST, 60.0 + step % 5)
        for day in range(3)
        for step in range(5 * 12)
    ] + [_reading(4 + i / 12, 3, Context.WORK, 72.0) for i in range(3)]
    deviations = evaluate(readings, Variant.FAMILY)
    late = [d for d in deviations if d.effective.day == 4]
    assert all(not d.used_population_range for d in late)
    covered = [d for d in evaluate(readings, Variant.COVERED) if d.effective.day == 4]
    assert all(d.used_population_range for d in covered)


def test_c_also_gates_the_own_base() -> None:
    readings = [
        _reading(14 + step / 12, day, Context.REST, 60.0 + step % 5)
        for day in range(3)
        for step in range(5 * 12)
    ] + [_reading(4, 3, Context.REST, 72.0)]
    target = dt.datetime(2021, 5, 4, 4, 0, tzinfo=dt.UTC)
    pick = {
        variant: next(d for d in evaluate(readings, variant) if d.effective == target)
        for variant in (Variant.COVERED, Variant.ALL_COVERED)
    }
    assert not pick[Variant.COVERED].used_population_range
    assert pick[Variant.ALL_COVERED].used_population_range


def test_judge_from_keeps_the_base_and_skips_the_verdict() -> None:
    readings = _mixed()
    cut = START + dt.timedelta(days=3)
    partial = evaluate(readings, Variant.CURRENT, judge_from=cut)
    full = [d for d in evaluate(readings, Variant.CURRENT) if d.effective >= cut]
    assert _keyed(partial) == _keyed(full)


def test_rmssd_collapse_is_a_step_on_rmssd() -> None:
    readings = [
        observation("hrv-rmssd", 40.0, START, "s", "t", context=Context.SLEEP),
        observation("hrv-rmssd", 3.0, START + dt.timedelta(hours=1), "s", "t",
                    context=Context.SLEEP),
        observation("heart-rate", 60.0, START + dt.timedelta(hours=1), "s", "t"),
    ]
    series = rmssd_collapse(readings, START + dt.timedelta(minutes=30))
    assert [o.value for o in series.observations] == [40.0, 1.5, 60.0]
    assert (series.perturbed, series.clamped) == (1, 0)
    assert [o.value for o in series.affected] == [1.5]


def test_spread_resamples_people_and_pairs_the_difference() -> None:
    people = [
        {v: {"readings": 100, "flagged": flagged + shift, "days": 1, "days_flagged": 0}
         for v, shift in (("vigente", 0), ("C", -1))}
        for flagged in (2, 3, 4, 5)
    ]
    out = spread({"per_subject": people}, resamples=200)
    assert out["C"]["difference"] == [-1.0, -1.0]
    assert out["vigente"]["difference"] == [0.0, 0.0]
    assert out["vigente"]["median_person"] == 3.5
