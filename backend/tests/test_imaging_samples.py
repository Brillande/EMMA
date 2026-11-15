"""Ecografías reales de ejemplo: se ven, no se miden, citan su origen y entran como simuladas.

Las imágenes viajan en el paquete con su huella: estas pruebas no tocan la red (invariante 3).
"""

from __future__ import annotations

import io
import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.routes import get_store, new_store, reset_store
from app.core.config import Settings, get_settings
from app.imaging import samples
from app.imaging.dicom import read_ultrasound
from app.imaging.protocols import PROTOCOLS
from app.imaging.render import frame_png
from app.main import app


def test_every_sample_is_cc_by_with_a_doi_and_a_known_protocol() -> None:
    catalog = samples.catalog()
    assert catalog
    for sample in catalog:
        assert sample.protocol in PROTOCOLS
        assert sample.dataset["license"] == "CC BY 4.0"
        assert sample.dataset["doi"] and sample.dataset["citation"]


def test_keys_do_not_give_away_the_dataset_label() -> None:
    """La clave se ve en la interfaz: si dijera "graso", sesgaría a quien anota los signos."""
    manifest = json.loads((samples.SAMPLES_DIR / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["samples"]:
        for word in ("healthy", "other", "normal", "fatty", "esteatosis"):
            assert word not in entry["key"]
    public = json.dumps([s.as_public() for s in samples.catalog()])
    assert "dataset_label" not in public and "original" not in public


@pytest.mark.parametrize("key", [s.key for s in samples.catalog()])
def test_each_sample_builds_as_an_uncalibrated_ultrasound(key: str) -> None:
    sample, data = samples.build(key)
    study = read_ultrasound(data)
    assert study.frames == sample.frames
    # Sin escala publicada no hay región calibrada: se puede ver, no medir en mm.
    assert not study.regions
    assert study.burned_in_annotation == ("YES" if sample.burned_in else "NO")


def test_the_pixels_are_the_published_ones() -> None:
    sample, data = samples.build("lung-1")
    [file] = json.loads(
        (samples.SAMPLES_DIR / "manifest.json").read_text(encoding="utf-8")
    )["samples"][0]["files"]
    original = np.asarray(Image.open(samples.SAMPLES_DIR / file).convert("L"))
    rendered = np.asarray(Image.open(io.BytesIO(frame_png(data, 0))))
    assert sample.frames == 1
    assert np.array_equal(rendered, original)


def test_a_changed_image_is_refused(tmp_path: Path) -> None:
    copy = tmp_path / "samples"
    shutil.copytree(samples.SAMPLES_DIR, copy)
    image = next(copy.glob("lung-1*.png"))
    Image.new("L", (8, 8)).save(image)
    with pytest.raises(samples.SampleFileChanged):
        samples.build("lung-1", copy)


def test_an_unknown_sample_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        samples.build("does-not-exist")


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def test_the_catalog_is_listed_with_its_citation(client: TestClient) -> None:
    listed = client.get("/api/imaging/samples").json()
    assert {s["protocol"] for s in listed} == {"lung", "liver"}
    assert all("doi" in s["dataset"] for s in listed)


def test_a_sample_enters_signed_as_simulated_and_cites_its_dataset(client: TestClient) -> None:
    response = client.post("/api/imaging/samples/liver-2", params={"subject": "crew-02"})
    assert response.status_code == 201, response.text
    index = response.json()["ledger_index"]

    [study] = client.get("/api/imaging/studies", params={"subject": "crew-02"}).json()
    assert study["source"] == samples.SAMPLE_SOURCE
    assert study["synthetic"] is False  # es real, pero no de este tripulante
    assert study["dataset"]["doi"] == "10.5281/zenodo.1009146"
    assert study["calibration"] == []
    assert study["burned_in_annotation"] == "YES"
    assert "dataset_label" not in study
    assert get_store().reading_signers() == {"simulator"}

    frame = client.get(f"/api/imaging/studies/{index}/frames/9")
    assert frame.status_code == 200
    assert Image.open(io.BytesIO(frame.content)).mode == "L"


def test_a_sample_cannot_be_measured(client: TestClient) -> None:
    index = client.post("/api/imaging/samples/lung-1").json()["ledger_index"]
    response = client.post(
        f"/api/imaging/studies/{index}/measurements",
        json={
            "measure": "onsd", "laterality": "right", "measured_by": "demo",
            "annotations": {
                "globe": {"points": [[200, 110]]},
                "sheath": {"points": [[145, 170], [255, 170]]},
            },
        },
    )
    assert response.status_code == 422


def test_a_sample_never_blocks_switching_scenario(client: TestClient) -> None:
    client.post("/api/imaging/samples/lung-2")
    response = client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 1, "replace": "true"}
    )
    assert response.status_code == 201, response.text


def test_an_unknown_sample_is_404(client: TestClient) -> None:
    assert client.post("/api/imaging/samples/nope").status_code == 404


def test_the_draft_facts_say_where_the_image_comes_from_in_words(client: TestClient) -> None:
    """Con booleanos, el modelo real escribía "la calibración es falsa" de una ecografía real."""
    from app.imaging.protocols import NOT_ASSESSABLE, PROTOCOLS
    from app.interpret.draft import facts_for

    lung = PROTOCOLS["lung"]
    index = client.post("/api/imaging/samples/lung-1").json()["ledger_index"]
    findings = {
        view.key: {sign.key: NOT_ASSESSABLE for sign in view.signs} for view in lung.views
    }
    recorded = client.post(
        f"/api/imaging/studies/{index}/findings",
        json={
            "checklist": dict.fromkeys(lung.checklist, True),
            "findings": findings,
            "recorded_by": "demo",
        },
    )
    assert recorded.status_code == 201, recorded.text
    facts = facts_for(get_store(), index)
    assert "no de este tripulante" in facts["origen_de_la_imagen"]
    assert facts["calibracion"].startswith("sin calibrar")
    assert not any(isinstance(value, bool) for value in facts.values())
