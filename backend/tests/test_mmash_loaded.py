"""Lo que el cargador de MMASH dice que produce es lo que produce (`validation/mmash.py`).

La matriz de riesgos publica, dominio a dominio, qué indicadores salen de MMASH y, por tanto,
sobre cuáles se ha medido la falsa alarma con personas reales. Esa lista es `mmash.LOADED`, la
tabla con que el cargador emite cada observación. Si alguien añade una lectura al cargador sin
ponerla en la tabla, o la quita de él y no de ella, la matriz diría lo que no es: estas pruebas
cargan un archivo sintético con la forma de MMASH —sin red y sin el dataset— y fallan si lo
emitido, clave y fuente, no es exactamente la tabla. La de `external` hace lo mismo con el real.

Y que nada de esto entra en `rules_version`: `validation/` no decide ningún nivel.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest

from app.core import versioning
from app.ingest.codes import CATALOG, DESCRIPTIVE_ONLY
from app.validation import mmash
from app.validation.mmash import ROOT_IN_ZIP, MmashLoader

SUBJECT = "user_1"


def _table(rows: list[dict[str, object]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _archive(path: Path) -> Path:
    """Un MMASH de un sujeto, con lo mínimo para que cada lectura del cargador salga una vez.

    Diez minutos de latidos (dos ventanas de cinco), una noche con dos segmentos de sueño, el
    acelerómetro de esos minutos, un tramo del diario y la ficha con el peso. Los valores son de
    una persona cualquiera: aquí no se mide nada, se mira qué claves salen.
    """
    rr = []
    for index in range(600):
        seconds = index
        rr.append({
            "": index, "ibi_s": 0.95 if index % 2 else 1.05, "day": 1,
            "time": f"10:{seconds // 60:02d}:{seconds % 60:02d}",
        })
    actigraph = [
        {"": second, "Steps": 0, "Inclinometer Off": 0} for second in range(0, 600, 10)
    ]
    sleep = [
        {"Onset Date": 1, "Onset Time": "23:00", "Out Bed Date": 2, "Out Bed Time": "02:00",
         "Total Sleep Time (TST)": 170, "Efficiency": 90},
        {"Onset Date": 2, "Onset Time": "02:30", "Out Bed Date": 2, "Out Bed Time": "07:00",
         "Total Sleep Time (TST)": 250, "Efficiency": 85},
    ]
    activity = [{"Activity": 2, "Start": "10:00", "End": "10:05", "Day": 1}]
    user_info = [{"Gender": "M", "Weight": 70, "Height": 175, "Age": 25}]
    archive = path / "MMASH.zip"
    base = f"{ROOT_IN_ZIP}/{SUBJECT}"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(f"{base}/RR.csv", _table(rr))
        bundle.writestr(f"{base}/Actigraph.csv", _table(actigraph))
        bundle.writestr(f"{base}/sleep.csv", _table(sleep))
        bundle.writestr(f"{base}/Activity.csv", _table(activity))
        bundle.writestr(f"{base}/user_info.csv", _table(user_info))
    return archive


@pytest.fixture
def loaded(tmp_path: Path) -> mmash.SubjectData:
    return MmashLoader(_archive(tmp_path)).load(SUBJECT)


def test_the_loader_emits_exactly_its_table(loaded: mmash.SubjectData) -> None:
    """Cada clave de la tabla sale, con su fuente, y no sale ninguna otra."""
    emitted = {(item.key, item.source) for item in loaded.observations}
    assert emitted == set(mmash.LOADED.items())


def test_the_published_keys_are_the_table_in_its_order() -> None:
    assert tuple(mmash.LOADED) == mmash.LOADED_KEYS
    assert len(set(mmash.LOADED_KEYS)) == len(mmash.LOADED_KEYS)


def test_every_loaded_key_is_an_evaluated_catalog_indicator() -> None:
    """Lo que sale de MMASH entra en el motor: una clave fuera del catálogo o descriptiva no
    mediría ninguna falsa alarma, y la matriz la contaría."""
    for key in mmash.LOADED_KEYS:
        assert key in CATALOG, key
        assert key not in DESCRIPTIVE_ONLY, key


def test_every_source_has_its_words() -> None:
    assert set(mmash.LOADED.values()) == set(mmash.SOURCE_DISPLAY)
    assert all(mmash.SOURCE_DISPLAY.values())
    # La cadencia de la banda es la ventana con que el cargador agrega los latidos.
    minutes = int(mmash.WINDOW.total_seconds() // 60)
    assert f"una lectura cada {minutes} min" in mmash.SOURCE_DISPLAY[mmash.POLAR_SOURCE]


def test_a_night_without_weighted_minutes_loses_its_efficiency_not_the_subject(
    tmp_path: Path,
) -> None:
    """Un segmento de cero minutos con eficiencia y otro sin ella: no hay eficiencia que ponderar,
    y la carga sigue (antes dividía por cero)."""
    archive = _archive(tmp_path)
    sleep = [
        {"Onset Date": 1, "Onset Time": "23:00", "Out Bed Date": 2, "Out Bed Time": "02:00",
         "Total Sleep Time (TST)": 0, "Efficiency": 80},
        {"Onset Date": 2, "Onset Time": "02:30", "Out Bed Date": 2, "Out Bed Time": "07:00",
         "Total Sleep Time (TST)": 250, "Efficiency": ""},
    ]
    rebuilt = tmp_path / "rebuilt.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(rebuilt, "w") as target:
        for name in source.namelist():
            body = _table(sleep) if name.endswith("/sleep.csv") else source.read(name).decode()
            target.writestr(name, body)
    data = MmashLoader(rebuilt).load(SUBJECT)
    keys = {item.key for item in data.observations}
    assert mmash.SLEEP_DURATION in keys
    assert mmash.SLEEP_EFFICIENCY not in keys


def test_cortisol_and_mood_stay_out_of_the_table() -> None:
    """Las dos decisiones de no cargar del módulo, vistas desde la tabla."""
    assert "cortisol-salivary" not in mmash.LOADED
    assert "mood-valence" not in mmash.LOADED


def test_the_scope_says_earth_and_not_space_physiology() -> None:
    assert "en Tierra" in mmash.VALIDATES
    assert "no fisiología espacial" in mmash.VALIDATES
    assert "falsa alarma" in mmash.VALIDATES


def test_validation_does_not_enter_the_rules_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """`validation/` no está en la huella, y cambiar lo que dice cargar no la mueve."""
    assert not any(name.startswith("app.validation") for name in versioning.FINGERPRINTED)
    before = versioning.fingerprint(versioning.rules())
    monkeypatch.setattr(mmash, "LOADED", {})
    monkeypatch.setattr(mmash, "VALIDATES", "otra cosa")
    assert versioning.fingerprint(versioning.rules()) == before
