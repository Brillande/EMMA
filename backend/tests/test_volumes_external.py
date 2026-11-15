"""La segmentación local frente a la de referencia del dataset (`-m external`).

    .venv/Scripts/python.exe -m pytest -m external tests/test_volumes_external.py

Cada TAC del dataset de TotalSegmentator (CC BY 4.0) trae sus máscaras de referencia, revisadas por
expertos. Aquí se mide cuánto coincide con ellas lo que segmenta TotalSegmentator en esta máquina
(Dice del hígado).

Solo cuentan los sujetos del reparto `test`: TotalSegmentator se entrenó con los de `train` y
`val`, y medir con ellos sería medir lo que el modelo ya vio. Con esos daba 0,986-0,992: un
número bonito que no valida nada.

Mide coincidencia de contorno, no si se detecta lo que importa clínicamente; eso no lo mide nadie
aquí, y así se dice (`risk-management-file.md`, H18). Sin datos segmentados, se salta.
"""

from __future__ import annotations

import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

SOURCES = Path(__file__).resolve().parents[2] / "data" / "ct-sources"
# Suelo de regresión fijado tras medir (`compliance/external-validation.md`). No es un criterio
# clínico: si baja, cambió el modelo, sus pesos o la forma de llamarlo.
# Medido el 2026-09-26 con 5 sujetos de test (s0013, s0235, s0450, s0735, s0829): 0,990-0,995.
MIN_DICE = 0.98


def dice(a: np.ndarray, b: np.ndarray) -> float:
    total = a.sum() + b.sum()
    return float(2 * (a & b).sum() / total) if total else 1.0


def held_out() -> list[Path]:
    found = []
    for path in sorted(SOURCES.glob("s*")):
        manifest = path / "manifest.json"
        if not (path / "seg-higado" / "total" / "liver.nii.gz").is_file() or not manifest.is_file():
            continue
        if json.loads(manifest.read_text(encoding="utf-8"))["meta"].get("split") == "test":
            found.append(path)
    return found


@pytest.mark.external
def test_local_liver_segmentation_agrees_with_the_reference_on_unseen_scans() -> None:
    subjects = held_out()
    if not subjects:
        pytest.skip("sin sujetos de test segmentados en data/ct-sources")
    scores = {}
    for subject in subjects:
        local = np.asarray(nib.load(subject / "seg-higado" / "total" / "liver.nii.gz").dataobj) > 0
        reference = np.asarray(nib.load(subject / "segmentations" / "liver.nii.gz").dataobj) > 0
        scores[subject.name] = dice(local, reference)
    print({name: round(score, 4) for name, score in scores.items()})
    assert min(scores.values()) >= MIN_DICE, scores


SEGMENTER = Path(__file__).resolve().parents[1] / ".venv-seg" / "Scripts" / "TotalSegmentator.exe"


@pytest.mark.external
def test_the_skeleton_segments_within_the_memory_it_announces(tmp_path: Path) -> None:
    """Preset `esqueleto` (Polaris) de verdad, sobre s0013 (45 cm de abdomen y pelvis, reparto
    `test`). Medido el 2026-10-02: 29 huesos con máscara, picos de 6,0 y 7,4 GB. La memoria
    estimada por tamaño (`segment.required_ram_gb`) tiene que cubrir el pico medido."""
    import threading
    import time

    from app.volumes import assets, segment

    ct = SOURCES / "s0013" / "ct.nii.gz"
    if not (SEGMENTER.is_file() and ct.is_file()):
        pytest.skip("sin TotalSegmentator (.venv-seg) o sin el TAC s0013")
    preset = assets.PRESETS["esqueleto"]
    needed = segment.required_ram_gb(ct, preset)
    start = segment.free_ram_gb()
    assert needed is not None and start is not None
    lowest, done = [start], threading.Event()

    def sample() -> None:
        while not done.is_set():
            lowest[0] = min(lowest[0], segment.free_ram_gb() or lowest[0])
            time.sleep(0.5)

    threading.Thread(target=sample, daemon=True).start()
    try:
        masks = segment.run(str(SEGMENTER), ct, tmp_path / "seg", preset)
    finally:
        done.set()
    present = {
        name for name, path in masks.items()
        if name in assets.BONES and np.asarray(nib.load(path).dataobj).any()
    }
    peak = start - lowest[0]
    print({"huesos": len(present), "pico_gb": round(peak, 1), "estimado_gb": round(needed, 1)})
    assert {"vertebrae_L1", "vertebrae_L5", "sacrum", "femur_left", "hip_right"} <= present
    assert len(present) >= 25
    assert peak <= needed


@pytest.mark.external
def test_the_real_scans_pass_the_personal_data_gate() -> None:
    """El otro eje de la puerta de datos personales (`volumes/privacy.py`). La suite normal mide
    que un volumen con un nombre dentro no entra; aquí, que un TAC real y limpio sí. Una puerta
    que lo rechaza todo tampoco deja pasar ningún nombre. Los ficheros son los del dataset byte a
    byte (`scripts/fetch_ct_samples.py`), no reescritos aquí. Medido el 2026-10-07: pasan los 15
    bajados (de 2 a 65 MB; el mayor se comprueba en 0,1 s). No usa TotalSegmentator."""
    from app.volumes import privacy

    scans = sorted(SOURCES.glob("s*/ct.nii.gz"))
    if not scans:
        pytest.skip("sin TAC del dataset en data/ct-sources")
    refused = {}
    for scan in scans:
        try:
            privacy.ensure_clean(scan.read_bytes(), None)
        except (privacy.PersonalDataFound, privacy.CheckUnavailable) as reason:
            refused[scan.parent.name] = str(reason)
    print({"pasan": len(scans) - len(refused), "de": len(scans)})
    assert not refused, refused
