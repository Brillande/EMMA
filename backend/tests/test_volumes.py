"""Visor 3D (portado de Polaris `visor3d.py`): geometría, segmentación y ledger. Sin red.

TotalSegmentator se simula: la prueba escribe las máscaras que él escribiría. Así se ejercita todo
el camino —subida, segmentación en segundo plano, ficheros del visor firmados— sin PyTorch.
"""

from __future__ import annotations

import gzip
import io
import time
import zipfile
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import memguard
from app.api.routes import get_store
from app.core.storage import ImagingBlobRow
from app.volumes import assets, geometry, segment

EYE = np.eye(4)


def ball(shape: tuple[int, int, int], center: tuple[int, int, int], radius: float) -> Any:
    grid = np.indices(shape)
    return sum((g - c) ** 2 for g, c in zip(grid, center, strict=True)) <= radius**2


# --------------------------------------------------------------------------- #
# Geometría
# --------------------------------------------------------------------------- #


def test_axial_diameter_is_between_voxel_centres() -> None:
    """Polaris: el Feret de scikit-image medía 21,5 mm en una esfera de 20."""
    sphere = ball((60, 60, 60), (30, 30, 30), 10)
    assert geometry.axial_max_diameter(sphere, np.ones(3)) == pytest.approx(20.0)


def test_spacing_comes_from_the_columns_even_if_oblique() -> None:
    angle = np.deg2rad(30)
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0],
                         [0, 0, 1]])
    affine = np.eye(4)
    affine[:3, :3] = rotation @ np.diag([2.0, 2.0, 3.0])
    assert geometry.spacing(affine) == pytest.approx([2.0, 2.0, 3.0])
    assert not np.allclose(np.abs(np.diag(affine)[:3]), [2.0, 2.0, 3.0])  # la diagonal mentía


def test_a_lesion_is_measured_inside_its_organ() -> None:
    organ = ball((60, 60, 60), (30, 30, 30), 25)
    lesion = ball((60, 60, 60), (30, 30, 30), 5)
    found, ids = geometry.lesions(organ, lesion, EYE)
    [item] = found
    assert item["estado"] == geometry.CANDIDATE
    assert item["diametro_mm"] == pytest.approx(10.0)
    assert item["volumen_ml"] == pytest.approx(4 / 3 * np.pi * 5**3 / 1000, rel=0.1)
    assert (ids == 1).sum() == lesion.sum()


def test_a_lesion_outside_the_organ_is_not_counted() -> None:
    """Polaris recorta las lesiones al órgano dilatado: lo de fuera es de otra estructura."""
    organ = ball((60, 60, 60), (20, 20, 20), 10)
    lesion = ball((60, 60, 60), (45, 45, 45), 5)
    found, _ = geometry.lesions(organ, lesion, EYE)
    assert found == []


def test_a_mesh_keeps_the_size_of_its_mask() -> None:
    """Taubin quita el escalón sin encoger: el radio de la malla es el de la esfera."""
    surface = geometry.mesh(ball((60, 60, 60), (30, 30, 30), 10), EYE)
    assert surface is not None
    radius = np.linalg.norm(surface[0] - 30, axis=1).mean()
    # Medido: 9,90 mm con Taubin; 9,63 si solo se aplica el paso que encoge (sin mu).
    assert radius == pytest.approx(10.0, abs=0.15)
    ply = geometry.ply_bytes(*surface)
    assert ply.startswith(b"ply\nformat binary_little_endian 1.0\n")


def test_pairing_follows_the_organ_shift() -> None:
    before = {"centro_organo_mm": [0, 0, 0], "lesiones": [
        {"id": 1, "centro_mm": [10, 0, 0], "diametro_mm": 12.0, "volumen_ml": 1.0, "region": 4},
    ]}
    after = {"centro_organo_mm": [5, 0, 0], "lesiones": [
        {"id": 1, "centro_mm": [15, 1, 0], "diametro_mm": 15.0, "volumen_ml": 1.5, "region": 4},
    ]}
    [pair] = geometry.pair(before, after)
    assert pair["antes"] == 1 and pair["despues"] == 1
    assert pair["distancia_mm"] == pytest.approx(1.0)
    assert pair["delta_diametro_pct"] == pytest.approx(25.0)


# --------------------------------------------------------------------------- #
# Construcción de lo que abre el visor
# --------------------------------------------------------------------------- #


def synthetic_ct() -> tuple[Any, dict[str, Any]]:
    """Un "TAC" de 1 mm con un órgano de radio 30 mm, una lesión de 8 mm y una vena."""
    shape = (90, 90, 90)
    data = np.full(shape, -1000, np.int16)
    organ = ball(shape, (45, 45, 45), 30)
    lesion = ball(shape, (45, 45, 60), 8)
    vein = np.zeros(shape, bool)
    # 6 mm de grosor: una de 4 mm son 2 vóxeles a 1,5 mm y el suavizado de Polaris la borra
    # (la cava real ronda los 20 mm).
    vein[42:48, 42:48, 10:80] = True
    data[organ] = 60
    data[lesion] = 20
    image = nib.Nifti1Image(data, EYE)
    masks = {
        "liver": nib.Nifti1Image(organ.astype(np.uint8), EYE),
        "liver_lesions": nib.Nifti1Image(lesion.astype(np.uint8), EYE),
        "inferior_vena_cava": nib.Nifti1Image(vein.astype(np.uint8), EYE),
    }
    return image, masks


def test_build_gives_labels_meshes_and_an_unvalidated_summary() -> None:
    image, masks = synthetic_ct()
    reference = assets.resample(image, assets.PRESETS["higado"].voxel_mm)
    files, summary = assets.build(
        reference, assets.mask_loader(reference, masks), assets.PRESETS["higado"]
    )
    assert summary["estado"] == assets.UNVALIDATED
    assert {"ct.nii.gz", "etiquetas.nii.gz", "higado.ply", "vci.ply"} <= set(files)
    [lesion] = summary["lesiones"]
    assert lesion["diametro_mm"] == pytest.approx(16.0, abs=2.5)  # a 2 mm de vóxel
    assert lesion["malla"] in files
    assert "serie_uid" not in summary  # Polaris lo filtraba a la web
    labels = nib.Nifti1Image.from_bytes(gzip.decompress(files["etiquetas.nii.gz"]))
    assert set(np.unique(np.asarray(labels.dataobj))) >= {0, 1, 4, 11}
    assert summary["ventana_hu"] == [60 - 90, 60 + 90]  # centrada en el órgano de este estudio


def test_no_organ_is_said_so() -> None:
    image, _ = synthetic_ct()
    reference = assets.resample(image)
    with pytest.raises(ValueError, match="no encontró"):
        assets.build(reference, lambda name: None, assets.PRESETS["higado"])


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def nifti_bytes(image: Any) -> bytes:
    return gzip.compress(image.to_bytes())


def upload(client: TestClient, image: Any) -> int:
    response = client.post(
        "/api/volumes", params={"recorded_by": "CMO"}, content=nifti_bytes(image),
        headers={"Content-Type": "application/gzip"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["ledger_index"])


@pytest.fixture
def fake_segmenter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """TotalSegmentator simulado: escribe las máscaras del TAC sintético."""
    _, masks = synthetic_ct()
    executable = tmp_path / "TotalSegmentator.exe"
    executable.write_bytes(b"")

    def run(exe: str, ct: Path, out: Path, preset: assets.Preset, device: str = "gpu") -> Any:
        out.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name, mask in masks.items():
            path = out / f"{name}.nii.gz"
            nib.save(mask, path)
            paths[name] = path
        return paths

    monkeypatch.setattr(segment, "find", lambda configured=None: str(executable))
    monkeypatch.setattr(segment, "telemetry_off", lambda exe: True)
    monkeypatch.setattr(segment, "run", run)


def wait(client: TestClient, job: str) -> dict[str, Any]:
    for _ in range(200):
        status: dict[str, Any] = client.get(f"/api/volumes/jobs/{job}").json()
        if status["state"] != "running":
            return status
        time.sleep(0.05)
    raise AssertionError("la segmentación no terminó")


def test_upload_segment_and_serve_the_viewer_files(
    client: TestClient, fake_segmenter: None
) -> None:
    image, _ = synthetic_ct()
    study = upload(client, image)
    started = client.post(f"/api/volumes/{study}/segment", params={"preset": "higado"})
    assert started.status_code == 202, started.text
    done = wait(client, started.json()["job"])
    assert done["state"] == "done", done

    [listed] = client.get("/api/volumes").json()
    [segmentation] = listed["segmentations"]
    assert segmentation["estado"] == assets.UNVALIDATED
    assert segmentation["study_sha256"] == listed["sha256"]
    index = segmentation["ledger_index"]
    ply = client.get(f"/api/volumes/segmentations/{index}/files/higado.ply")
    assert ply.status_code == 200 and ply.content.startswith(b"ply")
    assert client.get(f"/api/volumes/segmentations/{index}/files/otro.ply").status_code == 404
    # Nada de esto es una lectura: no entra en el análisis.
    assert get_store().query("crew-01") == []
    # Y la verificación del disco coteja también los binarios del visor, y pasa limpia.
    assert get_store().verify_integrity().ok


def test_without_segmenter_it_is_declared_absent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(segment, "find", lambda configured=None: None)
    status = client.get("/api/volumes/segmenter").json()
    assert status["available"] is False and "no disponible" in status["note"]
    image, _ = synthetic_ct()
    study = upload(client, image)
    assert client.post(f"/api/volumes/{study}/segment").status_code == 503


def test_an_unexpected_failure_ends_the_job_instead_of_hanging(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un error que nadie previó cierra el trabajo como fallido: la interfaz no espera sin fin."""

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise ModuleNotFoundError("No module named 'scipy'")

    monkeypatch.setattr(assets, "resample", broken)
    image, _ = synthetic_ct()
    study = upload(client, image)
    done = wait(client, client.post(f"/api/volumes/{study}/segment").json()["job"])
    assert done["state"] == "failed" and "scipy" in done["error"]


def test_a_changed_viewer_file_is_refused(client: TestClient, fake_segmenter: None) -> None:
    image, _ = synthetic_ct()
    study = upload(client, image)
    wait(client, client.post(f"/api/volumes/{study}/segment").json()["job"])
    [listed] = client.get("/api/volumes").json()
    index = listed["segmentations"][0]["ledger_index"]
    store = get_store()
    with Session(store.engine) as session:
        row = session.get(ImagingBlobRow, index)
        assert row is not None
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("higado.ply", b"ply manipulado")
        row.data = buffer.getvalue()
        session.commit()
    assert client.get(f"/api/volumes/segmentations/{index}/files/higado.ply").status_code == 409
    assert not store.verify_integrity().ok


def test_a_volume_is_a_real_record_but_not_a_reading(client: TestClient) -> None:
    image, _ = synthetic_ct()
    upload(client, image)
    assert get_store().query("crew-01") == []
    replace = client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 1, "replace": "true"}
    )
    assert replace.status_code == 409


def test_garbage_is_not_a_volume(client: TestClient) -> None:
    response = client.post(
        "/api/volumes", params={"recorded_by": "CMO"}, content=b"hola",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Datos personales en la cabecera NIfTI (Polaris `verifica_sin_pii`, tal cual)
# --------------------------------------------------------------------------- #

# Nombre inventado: no puede aparecer en ninguna respuesta.
PATIENT = "Garmendia"


def post_volume(client: TestClient, image: Any) -> Any:
    return client.post(
        "/api/volumes", params={"recorded_by": "CMO"}, content=nifti_bytes(image),
        headers={"Content-Type": "application/gzip"},
    )


def assert_nothing_was_saved(client: TestClient, entries_before: int) -> None:
    assert len(get_store().ledger) == entries_before
    assert client.get("/api/volumes").json() == []


def test_a_volume_with_a_name_in_its_header_is_not_saved(client: TestClient) -> None:
    image, _ = synthetic_ct()
    image.header["descrip"] = f"{PATIENT}^Ane 19850307".encode()
    before = len(get_store().ledger)
    response = post_volume(client, image)
    assert response.status_code == 422, response.text
    assert "descrip" in response.text, "el motivo dice qué campo"
    assert "No se ha guardado nada" in response.text, "y que no se ha limpiado en silencio"
    assert PATIENT.lower() not in response.text.lower()
    assert "19850307" not in response.text
    assert_nothing_was_saved(client, before)


@pytest.mark.parametrize("field", ["aux_file", "intent_name", "db_name"])
def test_every_free_text_field_of_the_header_is_looked_at(client: TestClient, field: str) -> None:
    image, _ = synthetic_ct()
    image.header[field] = PATIENT.encode()
    response = post_volume(client, image)
    assert response.status_code == 422, response.text
    assert field in response.text
    assert PATIENT.lower() not in response.text.lower()


def test_a_volume_with_an_extension_is_not_saved(client: TestClient) -> None:
    """Los conversores guardan ahí la cabecera DICOM entera, con nombre y fecha de nacimiento."""
    image, _ = synthetic_ct()
    dicom_like = f"(0010,0010) PN [{PATIENT}^Ane]".encode()
    image.header.extensions.append(nib.nifti1.Nifti1Extension("comment", dicom_like))
    before = len(get_store().ledger)
    response = post_volume(client, image)
    assert response.status_code == 422, response.text
    assert "extensi" in response.text
    assert PATIENT.lower() not in response.text.lower()
    assert_nothing_was_saved(client, before)


def test_the_declared_identity_is_searched_where_the_structure_does_not_look(
    client: TestClient,
) -> None:
    """`data_type` es texto libre que la comprobación estructural no mira: ahí un nombre solo se
    ve si se sabe cuál buscar. Sin identidad declarada pasa; es el límite declarado en H18."""
    image, _ = synthetic_ct()
    image.header["data_type"] = PATIENT.upper().encode()
    upload(client, image)

    declared = {
        "given_name": "Ane", "surnames": f"{PATIENT} Zubiri", "birth_date": "1985-03-07",
        "declared_by": "CMO",
    }
    assert client.post("/api/crew/identity", json=declared).status_code == 201
    before = len(get_store().ledger)
    response = post_volume(client, image)
    assert response.status_code == 422, response.text
    # Polaris dice "de la serie" (la suya, DICOM); al operador se le dice de quién es el valor.
    assert "valor identificativo del tripulante" in response.text
    assert PATIENT.lower() not in response.text.lower()
    assert len(get_store().ledger) == before
    # Y con la identidad declarada, un volumen limpio sigue entrando.
    clean, _ = synthetic_ct()
    upload(client, clean)


def test_if_the_check_cannot_run_nothing_is_saved(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import polaris
    from app.volumes import privacy

    def missing() -> Any:
        raise polaris.PolarisUnavailable("no está la copia de Polaris")

    monkeypatch.setattr(privacy, "_tool", missing)
    image, _ = synthetic_ct()
    before = len(get_store().ledger)
    response = post_volume(client, image)
    assert response.status_code == 503, response.text
    assert "no pudo ejecutarse" in response.text
    assert_nothing_was_saved(client, before)


def test_a_check_that_does_not_say_clean_is_not_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Polaris devuelve `True` o aborta. Cualquier otra cosa no es "limpio"."""
    from app.volumes import privacy

    class Silent:
        @staticmethod
        def verifica_sin_pii(path: str, values: list[str]) -> None:
            return None

    monkeypatch.setattr(privacy, "_tool", lambda: Silent)
    image, _ = synthetic_ct()
    with pytest.raises(privacy.CheckUnavailable):
        privacy.ensure_clean(nifti_bytes(image), None)


def test_the_reason_never_repeats_what_was_searched() -> None:
    """Hoy Polaris no nombra el valor; si un día lo hiciera, el motivo se sustituye entero."""
    from app.volumes import privacy

    assert privacy._reason("ABORTA: el NIfTI lleva texto en descrip", [PATIENT]) == (
        "el NIfTI lleva texto en descrip"
    )
    leaked = privacy._reason(f"ABORTA: la cabecera contiene {PATIENT.upper()}", [PATIENT])
    assert PATIENT.lower() not in leaked.lower()


@pytest.mark.parametrize("compressed", [True, False])
def test_a_gap_between_header_and_voxels_is_not_a_hiding_place(
    client: TestClient, compressed: bool
) -> None:
    """Polaris lee `vox_offset` de una cabecera que nibabel ya ha puesto a cero: solo mira 352
    bytes. Medido: un nombre en el byte 360 pasaba incluso con la identidad declarada."""
    import struct

    image, _ = synthetic_ct()
    raw = bytearray(image.to_bytes())
    raw[352:352] = PATIENT.upper().encode().ljust(48, b"\x00")
    struct.pack_into("<f", raw, 108, 400.0)
    assert nib.Nifti1Image.from_bytes(bytes(raw)).shape == image.shape, "sigue siendo legible"
    before = len(get_store().ledger)
    response = client.post(
        "/api/volumes", params={"recorded_by": "CMO"},
        content=gzip.compress(bytes(raw)) if compressed else bytes(raw),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 422, response.text
    assert "entre la cabecera y los vóxeles" in response.text
    assert PATIENT.lower() not in response.text.lower()
    assert_nothing_was_saved(client, before)


@pytest.mark.parametrize(
    "written",
    ["MUÑOZ".encode(), "MUÑOZ".encode("latin-1"), "Muñoz".encode(), b"MUNOZ", b"munoz"],
    ids=["utf8-mayusculas", "latin1-mayusculas", "utf8", "sin-tilde-mayusculas", "sin-tilde"],
)
def test_a_name_with_an_accent_is_found_however_it_was_written(written: bytes) -> None:
    """Polaris compara en minúsculas ASCII y UTF-8: «MUÑOZ» en mayúsculas o en Latin-1 (lo
    habitual en DICOM) se le escapaba. Medido antes de añadir las grafías de EMMA."""
    import datetime as dt

    from app.reports.identity import Declared
    from app.volumes import privacy

    declared = Declared("Íñigo", "Muñoz Ibáñez", dt.date(1985, 3, 7))
    image, _ = synthetic_ct()
    privacy.ensure_clean(nifti_bytes(image), declared)
    image.header["data_type"] = written
    with pytest.raises(privacy.PersonalDataFound) as refused:
        privacy.ensure_clean(nifti_bytes(image), declared)
    assert "identificativo" in str(refused.value)
    assert "mu" not in str(refused.value).lower().replace("muestra", "")


@pytest.mark.parametrize(
    "written",
    ["19850307", "1985-03-07", "07/03/1985", "07-03-1985", "07.03.1985", "03/07/1985"],
    ids=["dicom", "iso", "dia-mes", "guiones", "puntos", "mes-dia"],
)
def test_the_birth_date_is_found_however_it_was_written(written: str) -> None:
    import datetime as dt

    from app.reports.identity import Declared
    from app.volumes import privacy

    declared = Declared("Ane", f"{PATIENT} Zubiri", dt.date(1985, 3, 7))
    image, _ = synthetic_ct()
    image.header["data_type"] = b"19850308"  # otra fecha: no es la suya y no se rechaza
    privacy.ensure_clean(nifti_bytes(image), declared)
    image.header["data_type"] = written.encode()
    with pytest.raises(privacy.PersonalDataFound) as refused:
        privacy.ensure_clean(nifti_bytes(image), declared)
    assert written not in str(refused.value)


def test_a_file_name_kept_by_gzip_is_not_saved(client: TestClient) -> None:
    """`gzip fichero.nii` guarda en el envoltorio el nombre que tenía el fichero, y los de un
    paciente suelen llamarse como él. Va fuera del NIfTI: la comprobación de Polaris no lo ve, y
    EMMA firma el `.gz` entero."""
    image, _ = synthetic_ct()
    wrapped = io.BytesIO()
    with gzip.GzipFile(filename=f"{PATIENT}_Ane.nii", mode="wb", fileobj=wrapped) as stream:
        stream.write(image.to_bytes())
    raw = wrapped.getvalue()
    assert PATIENT.encode() in raw[:40], "el nombre va en claro al principio del fichero"
    before = len(get_store().ledger)
    response = client.post(
        "/api/volumes", params={"recorded_by": "CMO"}, content=raw,
        headers={"Content-Type": "application/gzip"},
    )
    assert response.status_code == 422, response.text
    assert "el envoltorio gzip guarda el nombre original del fichero" in response.text
    assert "gzip -n" in response.text, "y dice cómo comprimirlo sin nombre"
    assert PATIENT.lower() not in response.text.lower()
    assert_nothing_was_saved(client, before)


def test_an_uncompressed_volume_is_checked_too(client: TestClient) -> None:
    image, _ = synthetic_ct()
    plain = {"Content-Type": "application/octet-stream"}
    ok = client.post(
        "/api/volumes", params={"recorded_by": "CMO"}, content=image.to_bytes(), headers=plain
    )
    assert ok.status_code == 201, ok.text
    image.header["descrip"] = PATIENT.encode()
    refused = client.post(
        "/api/volumes", params={"recorded_by": "CMO"}, content=image.to_bytes(), headers=plain
    )
    assert refused.status_code == 422, refused.text


def test_the_four_samples_still_enter(client: TestClient) -> None:
    """Los ejemplos van por su ruta, con huella fija, y además su cabecera está limpia."""
    from app.volumes import privacy
    from app.volumes.samples import catalog, load_sample

    keys = [sample.key for sample in catalog()]
    assert len(keys) == 4
    for key in keys:
        privacy.ensure_clean(load_sample(key)[1], None)
        assert client.post(f"/api/volumes/samples/{key}").status_code == 201, key
    assert len(client.get("/api/volumes").json()) == 4


# --------------------------------------------------------------------------- #
# La puerta ofrece limpiar: solo si se pide, y lo limpio vuelve a pasar la puerta
# --------------------------------------------------------------------------- #

# Lo que deja un conversor de DICOM: técnico, sin nada de nadie, y aun así rechazado.
TECHNICAL = b"TE=2.3;Time=101530.000;phase=1"


def post_raw(client: TestClient, raw: bytes, **params: Any) -> Any:
    return client.post(
        "/api/volumes", params={"recorded_by": "CMO", **params}, content=raw,
        headers={"Content-Type": "application/octet-stream"},
    )


def scanner_like(text: bytes = TECHNICAL) -> bytes:
    """Un NIfTI como sale de un escáner: en crudo con su escala, `qform` y `sform` distintos y con
    códigos propios, unidades, y texto en `descrip`. Sin comprimir."""
    import struct

    data = (np.asarray(synthetic_ct()[0].dataobj) + 1024).astype(np.uint16)
    sform = np.diag([0.8, 0.8, 2.5, 1.0])
    sform[:3, 3] = (-120.0, -95.5, 300.25)
    image = nib.Nifti1Image(data, sform)
    image.set_sform(sform, code=2)
    turned = sform.copy()
    turned[:3, 3] = (5.0, 6.0, 7.0)
    image.set_qform(turned, code=1)
    image.header.set_xyzt_units("mm", "sec")
    image.header["descrip"] = text
    raw = bytearray(image.to_bytes())
    struct.pack_into("<ff", raw, 112, 1.0, -1024.0)  # scl_slope y scl_inter: nibabel no los guarda
    struct.pack_into("<f", raw, 76 + 4 * 4, 1.75)  # pixdim[4]
    return bytes(raw)


def unzipped(raw: bytes) -> bytes:
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def file_header(raw: bytes) -> Any:
    """La cabecera tal como está en el fichero (nibabel, al cargar la imagen, repone la escala)."""
    return nib.Nifti1Header.from_fileobj(io.BytesIO(unzipped(raw)))


def stored_volume(index: int) -> tuple[dict[str, Any], bytes]:
    return get_store().volume_blob(index)


def test_a_refusal_says_that_cleaning_here_would_let_it_in(client: TestClient) -> None:
    from app.volumes import privacy

    before = len(get_store().ledger)
    response = post_raw(client, scanner_like())
    assert response.status_code == 422, response.text
    body = response.json()
    assert "descrip" in body["detail"] and "No se ha guardado nada" in body["detail"]
    assert body["cleanable"] is True
    assert (body["clean_offer"], body["clean_label"]) == (privacy.CLEAN_OFFER, privacy.CLEAN_LABEL)
    assert TECHNICAL.decode() not in response.text, "el motivo nombra el campo, no su contenido"
    assert_nothing_was_saved(client, before)


def test_without_asking_nothing_is_cleaned(client: TestClient) -> None:
    """`clean` solo vale dicho: ni por omisión ni con `false` se guarda nada de un rechazado."""
    before = len(get_store().ledger)
    assert post_raw(client, scanner_like()).status_code == 422
    assert post_raw(client, scanner_like(), clean="false").status_code == 422
    assert_nothing_was_saved(client, before)


def test_asking_to_clean_a_clean_volume_changes_nothing(client: TestClient) -> None:
    """Lo que ya pasa la puerta se guarda como llegó aunque se pida limpiar: no hay nada que
    limpiar y el asiento no dice que se limpió."""
    raw = nifti_bytes(synthetic_ct()[0])
    response = post_raw(client, raw, clean="true")
    assert response.status_code == 201, response.text
    assert "cleaned" not in response.json()
    payload, kept = stored_volume(int(response.json()["ledger_index"]))
    assert kept == raw and "cleaned" not in payload
    assert "cleaned" not in client.get("/api/volumes").json()[0]


def test_cleaning_on_request_saves_the_clean_volume_and_the_entry_says_so(
    client: TestClient,
) -> None:
    from app.core.ledger import sha256_hex
    from app.volumes import privacy

    raw = scanner_like()
    response = post_raw(client, raw, clean="true")
    assert response.status_code == 201, response.text
    body = response.json()
    payload, kept = stored_volume(int(body["ledger_index"]))

    # Se guarda el limpio, no el recibido, y lo guardado pasa la puerta por sí solo.
    assert kept != raw
    privacy.ensure_clean(kept, None)
    assert not bytes(file_header(kept)["descrip"].tobytes()).strip(b"\x00")
    # El asiento firmado lo declara: campos por su nombre y las dos huellas.
    declared = payload["cleaned"]
    assert declared["fields"] == ["descrip"]
    assert declared["received_sha256"] == sha256_hex(raw) != payload["sha256"]
    assert declared["received_size_bytes"] == len(raw)
    assert payload["sha256"] == sha256_hex(kept) == body["sha256"]
    assert declared["note"] == privacy.CLEANED_NOTE
    assert body["cleaned"] == declared
    assert client.get("/api/volumes").json()[0]["cleaned"] == declared
    assert get_store().verify_integrity().ok


def test_a_cleaned_volume_is_the_same_study_voxel_by_voxel(client: TestClient) -> None:
    """Vóxeles bit a bit, y afín (`sform`/`qform` con sus códigos), dimensiones, `pixdim`, tipo,
    escala y unidades como en el fichero recibido."""
    from app.volumes import privacy

    raw = scanner_like()
    response = post_raw(client, raw, clean="true")
    assert response.status_code == 201, response.text
    _, kept = stored_volume(int(response.json()["ledger_index"]))
    was, now = file_header(raw), file_header(kept)

    assert kept[352:] == raw[352:], "los bytes de los vóxeles, uno a uno"
    for field in privacy.CONSERVED:
        assert np.array_equal(now[field], was[field], equal_nan=True), field
    assert (float(now["scl_slope"]), float(now["scl_inter"])) == (1.0, -1024.0)
    assert (int(now["qform_code"]), int(now["sform_code"])) == (1, 2)
    assert float(now["pixdim"][4]) == 1.75 and now.get_xyzt_units() == ("mm", "sec")
    assert now.get_data_dtype() == np.uint16

    before, after = nib.Nifti1Image.from_bytes(raw), nib.Nifti1Image.from_bytes(kept)
    assert np.array_equal(after.get_sform(), before.get_sform())
    assert np.array_equal(after.get_qform(), before.get_qform())
    assert not np.array_equal(after.get_qform(), after.get_sform()), "cada uno, el suyo"
    assert np.array_equal(after.get_fdata(), before.get_fdata()), "y las mismas HU"
    assert after.get_fdata().min() == -1000


def test_what_was_cleaned_is_never_shown_anywhere(client: TestClient) -> None:
    """El nombre va en `descrip`, en `data_type`, en una extensión, detrás de los vóxeles y en el
    envoltorio gzip. Tras limpiar no está en la respuesta, ni en el asiento, ni en lo guardado."""
    import json

    image, _ = synthetic_ct()
    image.header["descrip"] = f"{PATIENT}^Ane 19850307".encode()
    image.header["data_type"] = PATIENT.upper().encode()
    image.header.extensions.append(
        nib.nifti1.Nifti1Extension("comment", f"(0010,0010) PN [{PATIENT}^Ane]".encode())
    )
    plain = bytearray(image.to_bytes())
    plain += PATIENT.encode()
    assert np.array_equal(
        nib.Nifti1Image.from_bytes(bytes(plain)).dataobj, image.dataobj
    ), "sigue siendo legible"
    wrapped = io.BytesIO()
    with gzip.GzipFile(filename=f"{PATIENT}_Ane.nii", mode="wb", fileobj=wrapped) as stream:
        stream.write(bytes(plain))
    raw = wrapped.getvalue()

    refused = post_raw(client, raw)
    assert refused.status_code == 422 and refused.json()["cleanable"] is True
    response = post_raw(client, raw, clean="true")
    assert response.status_code == 201, response.text
    payload, kept = stored_volume(int(response.json()["ledger_index"]))
    assert set(payload["cleaned"]["fields"]) == {
        "descrip", "data_type", "extensiones", "datos detrás de los vóxeles", "envoltorio gzip",
    }
    listed = client.get("/api/volumes").text
    for where in (refused.text, response.text, listed, json.dumps(payload, ensure_ascii=False)):
        assert PATIENT.lower() not in where.lower() and "19850307" not in where
    for stored in (kept, unzipped(kept)):
        assert PATIENT.lower().encode() not in stored.lower()
    assert kept[:2] == b"\x1f\x8b" and kept[3] == 0 and kept[4:8] == b"\x00" * 4
    assert np.array_equal(nib.Nifti1Image.from_bytes(unzipped(kept)).dataobj, image.dataobj)
    assert len(unzipped(kept)) == 352 + image.dataobj.size * 2, "cabecera y vóxeles, nada más"


def test_a_cleaned_volume_goes_through_the_same_gate_again(client: TestClient) -> None:
    """Un valor del tripulante en un campo numérico que la limpieza conserva: limpiar no lo quita,
    la puerta lo vuelve a ver y no se guarda nada. Y el rechazo ya decía que limpiar no servía."""
    import struct

    identity = {
        "given_name": "Ane", "surnames": "Muno Zubiri", "birth_date": "1985-03-07",
        "declared_by": "CMO",
    }
    assert client.post("/api/crew/identity", json=identity).status_code == 201
    raw = bytearray(scanner_like())
    raw[76 + 4 * 6 : 76 + 4 * 7] = b"MUNO"  # pixdim[6]: un float cuyos cuatro bytes son el apellido
    assert struct.unpack_from("<f", raw, 76 + 4 * 6)[0] > 0
    before = len(get_store().ledger)

    refused = post_raw(client, bytes(raw))
    assert refused.status_code == 422 and refused.json()["cleanable"] is False
    assert refused.json()["clean_offer"] is None
    response = post_raw(client, bytes(raw), clean="true")
    assert response.status_code == 422, response.text
    body = response.json()
    assert "después de limpiar la cabecera" in body["detail"]
    assert "valor identificativo del tripulante" in body["detail"]
    assert "No se ha guardado nada" in body["detail"] and body["cleanable"] is False
    assert "muno" not in response.text.lower()
    assert len(get_store().ledger) == before
    # Sin ese valor, el mismo fichero limpio entra con la identidad declarada.
    assert post_raw(client, scanner_like(), clean="true").status_code == 201


def test_a_cleaning_that_leaks_does_not_get_in(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Como la prueba de Polaris con su `limpio_con_fuga`: si la limpieza dejara texto, la puerta
    de después lo para."""
    from app.volumes import privacy

    tool = privacy._tool()

    class Leaky:
        verifica_sin_pii = staticmethod(tool.verifica_sin_pii)
        _trozos_pii = staticmethod(tool._trozos_pii)

        @staticmethod
        def nifti_limpio(data: Any, affine: Any, dtype: Any) -> Any:
            image = tool.nifti_limpio(data, affine, dtype)
            image.header["aux_file"] = PATIENT.encode()
            return image

    monkeypatch.setattr(privacy, "_tool", lambda: Leaky)
    before = len(get_store().ledger)
    response = post_raw(client, scanner_like(), clean="true")
    assert response.status_code == 422, response.text
    assert "aux_file" in response.text and PATIENT.lower() not in response.text.lower()
    assert_nothing_was_saved(client, before)


@pytest.mark.parametrize("compressed", [True, False])
def test_a_gap_after_the_header_is_cleaned_and_declared(
    client: TestClient, compressed: bool
) -> None:
    """Lo guardado va como llegó: comprimido si llegó comprimido, y sin hueco."""
    import struct

    image, _ = synthetic_ct()
    plain = bytearray(image.to_bytes())
    plain[352:352] = PATIENT.upper().encode().ljust(48, b"\x00")
    struct.pack_into("<f", plain, 108, 400.0)
    raw = gzip.compress(bytes(plain)) if compressed else bytes(plain)
    response = post_raw(client, raw, clean="true")
    assert response.status_code == 201, response.text
    payload, kept = stored_volume(int(response.json()["ledger_index"]))
    assert payload["cleaned"]["fields"] == ["hueco entre la cabecera y los vóxeles"]
    assert (kept[:2] == b"\x1f\x8b") is compressed
    assert unzipped(kept) == image.to_bytes(), "el mismo fichero que sin el hueco"
    assert PATIENT.upper().encode() not in unzipped(kept)
    assert float(file_header(kept)["vox_offset"]) == 352.0


def test_a_cleaning_that_would_change_the_image_is_not_done(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La limpieza se comprueba a sí misma antes de la puerta: si un campo que dice dónde está
    cada vóxel no quedara como en el fichero recibido, no hay limpieza y no se guarda nada."""
    from app.volumes import privacy

    raw = scanner_like()
    with monkeypatch.context() as patched:
        patched.setattr(privacy, "_same", lambda left, right: False)
        with pytest.raises(privacy.CheckUnavailable, match="habría cambiado la imagen"):
            privacy.clean(raw, None)

    # Y lo mismo con los vóxeles: lo que devuelva `nifti_limpio` tiene que ser lo recibido.
    tool = privacy._tool()

    class Shifted:
        verifica_sin_pii = staticmethod(tool.verifica_sin_pii)
        _trozos_pii = staticmethod(tool._trozos_pii)

        @staticmethod
        def nifti_limpio(data: Any, affine: Any, dtype: Any) -> Any:
            return tool.nifti_limpio(np.asarray(data) + 1, affine, dtype)

    monkeypatch.setattr(privacy, "_tool", lambda: Shifted)
    with pytest.raises(privacy.CheckUnavailable, match="habría cambiado la imagen"):
        privacy.clean(raw, None)
    before = len(get_store().ledger)
    assert post_raw(client, raw).json()["cleanable"] is False
    response = post_raw(client, raw, clean="true")
    assert response.status_code == 503, response.text
    assert_nothing_was_saved(client, before)


def test_if_the_header_cannot_be_cleaned_nothing_is_saved(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.volumes import privacy

    tool = privacy._tool()

    class Broken:
        verifica_sin_pii = staticmethod(tool.verifica_sin_pii)
        _trozos_pii = staticmethod(tool._trozos_pii)

        @staticmethod
        def nifti_limpio(data: Any, affine: Any, dtype: Any) -> Any:
            raise RuntimeError(f"cabecera ilegible: {PATIENT}")

    monkeypatch.setattr(privacy, "_tool", lambda: Broken)
    before = len(get_store().ledger)
    response = post_raw(client, scanner_like(PATIENT.encode()), clean="true")
    assert response.status_code == 503, response.text
    assert "no se pudo limpiar (RuntimeError)" in response.text
    assert PATIENT.lower() not in response.text.lower(), "del error solo sale el tipo"
    assert_nothing_was_saved(client, before)


def test_a_big_endian_volume_keeps_its_values_when_cleaned() -> None:
    """Se escribe en el orden de bytes de la máquina: los mismos valores, uno a uno."""
    from app.volumes import privacy

    data = np.asarray(synthetic_ct()[0].dataobj)
    header = nib.Nifti1Header(endianness=">")
    header["descrip"] = TECHNICAL
    header.set_data_dtype(np.int16)
    image = nib.Nifti1Image(data.astype(">i2"), np.diag([1.5, 1.5, 3.0, 1.0]), header)
    raw = bytes(image.to_bytes())
    assert raw[:4] == b"\x00\x00\x01\x5c", "cabecera big-endian"
    cleaned = privacy.clean(raw, None)
    after = nib.Nifti1Image.from_bytes(cleaned.data)
    assert np.array_equal(np.asarray(after.dataobj), data) and after.get_data_dtype() == np.int16
    assert np.array_equal(after.affine, image.affine)
    assert "descrip" in cleaned.fields


def test_what_the_gate_says_about_cleaning_passes_the_language_guard() -> None:
    from app import text_guard
    from app.volumes import privacy

    for text in (privacy.CLEAN_OFFER, privacy.CLEAN_LABEL, privacy.CLEANED_NOTE,
                 privacy.STILL_FOUND):
        assert text_guard.check(text) == [], text
    # Lo que no cubre va dicho donde se ofrece y donde queda firmado.
    for text in (privacy.CLEAN_OFFER, privacy.CLEANED_NOTE):
        assert "dentro de la propia imagen" in text


# --------------------------------------------------------------------------- #
# TAC reales de ejemplo (dataset de TotalSegmentator, CC BY 4.0)
# --------------------------------------------------------------------------- #


def test_the_samples_are_cc_by_and_cite_their_dataset() -> None:
    from app.volumes.samples import catalog

    items = catalog()
    assert {item.preset for item in items} == {"higado", "ojos", "esqueleto"}
    for item in items:
        assert item.dataset["license"] == "CC BY 4.0"
        assert item.dataset["doi"] == "10.5281/zenodo.10047292"


def test_the_skeleton_sample_is_a_whole_body_with_every_bone(client: TestClient) -> None:
    """s1152 (politrauma, reparto `test`): el único ejemplo en el que el preset esqueleto tiene
    sentido. Los demás son recortes de hígado y órbitas: allí salen trozos de costilla o nada."""
    response = client.post("/api/volumes/samples/esqueleto-4")
    assert response.status_code == 201, response.text
    [study] = client.get("/api/volumes").json()
    assert study["source"] == "simulator:dataset"
    [segmentation] = study["segmentations"]
    assert segmentation["preset"] == "esqueleto"
    assert segmentation["estado"] == assets.UNVALIDATED
    assert {s["key"] for s in segmentation["estructuras"]} == set(assets.BONES)
    extent = [n * z for n, z in zip(study["shape"], study["voxel_mm"], strict=True)]
    assert max(extent) > 600, "de cuello a cadera, no un recorte"
    index = segmentation["ledger_index"]
    for name in ("vertebrae_L1.ply", "femur_left.ply", "rib_right_1.ply"):
        assert client.get(f"/api/volumes/segmentations/{index}/files/{name}").status_code == 200


def test_a_sample_enters_as_simulated_with_its_viewer_files(client: TestClient) -> None:
    response = client.post("/api/volumes/samples/higado-1")
    assert response.status_code == 201, response.text
    [study] = client.get("/api/volumes").json()
    assert study["source"] == "simulator:dataset"
    assert study["dataset"]["license"] == "CC BY 4.0"
    [segmentation] = study["segmentations"]
    assert segmentation["estado"] == assets.UNVALIDATED
    assert segmentation["lesiones"], "el ejemplo hepático tiene lesiones candidatas"
    index = segmentation["ledger_index"]
    for name in ("ct.nii.gz", "etiquetas.nii.gz", "higado.ply"):
        assert client.get(f"/api/volumes/segmentations/{index}/files/{name}").status_code == 200
    # Firmado como simulado: un cambio de escenario lo puede descartar.
    assert get_store().reading_signers() == {"simulator"}


def test_the_scenario_preloads_the_liver_sample_and_keeps_it_on_change(
    client: TestClient,
) -> None:
    """Decisión del usuario (2026-11-15): el hígado «tiene que salir precargado» en «Distancia y
    nodos». Va con el escenario, en su mismo almacén, y un cambio de escenario no lo pierde."""
    headers = {"X-EMMA-Console": "1"}
    params = {"scenario": "nominal", "days": 2, "volume_sample": "higado-1"}
    assert client.post("/api/simulate", params=params, headers=headers).status_code == 201
    [study] = client.get("/api/volumes", params={"subject": "crew-01"}).json()
    assert study["sample"] == "higado-1"
    [segmentation] = study["segmentations"]
    assert segmentation["preset"] == "higado"
    replaced = client.post(
        "/api/simulate", params={**params, "replace": "true"}, headers=headers
    )
    assert replaced.status_code == 201, replaced.text
    assert len(client.get("/api/volumes", params={"subject": "crew-01"}).json()) == 1


def test_the_liver_reads_in_english_but_stays_signed_in_spanish(client: TestClient) -> None:
    assert client.post("/api/volumes/samples/higado-1").status_code == 201
    [study] = client.get("/api/volumes", headers={"X-EMMA-Lang": "en"}).json()
    [segmentation] = study["segmentations"]
    assert segmentation["preset_nombre"] == "Liver"
    assert segmentation["estado"] == "automatic segmentation, not validated"
    assert segmentation["estructuras"][0]["nombre"] == "Liver"
    [spanish] = client.get("/api/volumes", headers={"X-EMMA-Lang": "es"}).json()
    assert spanish["segmentations"][0]["preset_nombre"] == "Hígado"


def test_an_unknown_preloaded_sample_seeds_nothing(client: TestClient) -> None:
    response = client.post(
        "/api/simulate", params={"days": 2, "volume_sample": "no-existe"},
        headers={"X-EMMA-Console": "1"},
    )
    assert response.status_code == 404
    assert len(get_store().ledger) == 0


def test_a_changed_sample_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import shutil

    from app.volumes import samples

    copy = tmp_path / "volume_samples"
    shutil.copytree(samples.SAMPLES_DIR, copy)
    (copy / "higado-1" / "visor.zip").write_bytes(b"cambiado")
    monkeypatch.setattr(samples, "SAMPLES_DIR", copy)
    with pytest.raises(samples.SampleFileChanged):
        samples.load_sample("higado-1")


def test_comparison_refuses_different_presets(client: TestClient) -> None:
    liver = client.post("/api/volumes/samples/higado-1").json()["segmentation"]
    eyes = client.post("/api/volumes/samples/ojos-3").json()["segmentation"]
    mixed = client.get("/api/volumes/compare", params={"before": liver, "after": eyes})
    assert mixed.status_code == 409
    same = client.post("/api/volumes/samples/higado-2").json()["segmentation"]
    compared = client.get("/api/volumes/compare", params={"before": liver, "after": same})
    assert compared.status_code == 200 and "pares" in compared.json()


# --------------------------------------------------------------------------- #
# Evolución de lesiones entre dos estudios (Polaris `visor3d.evolucion`)
# --------------------------------------------------------------------------- #

# Centros (vóxel = mm) de cinco lesiones dentro del órgano sintético, a 15 mm de su centro.
SAME, GROWING, SHRINKING, UNSEEN, GONE = (
    (45, 45, 60), (45, 60, 45), (60, 45, 45), (45, 30, 45), (30, 45, 45),
)
EARLIER = {SAME: 8, GROWING: 6, SHRINKING: 8, GONE: 5}
LATER = {SAME: 8, GROWING: 9, SHRINKING: 4, UNSEEN: 5}


def ct_with_lesions(lesions: dict[tuple[int, int, int], float]) -> tuple[Any, dict[str, Any]]:
    """El TAC sintético con las lesiones que se pidan: {centro: radio en mm}."""
    image, masks = synthetic_ct()
    mask = np.zeros(image.shape, bool)
    for center, radius in lesions.items():
        mask |= ball(image.shape, center, radius)
    masks["liver_lesions"] = nib.Nifti1Image(mask.astype(np.uint8), EYE)
    return image, masks


def segmented(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
    lesions: dict[tuple[int, int, int], float], subject: str = "crew-01",
) -> int:
    """Sube un TAC con esas lesiones, lo "segmenta" y devuelve el asiento de la segmentación."""
    image, masks = ct_with_lesions(lesions)

    def run(exe: str, ct: Path, out: Path, preset: assets.Preset, device: str = "gpu") -> Any:
        out.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name, mask in masks.items():
            paths[name] = out / f"{name}.nii.gz"
            nib.save(mask, paths[name])
        return paths

    monkeypatch.setattr(segment, "run", run)
    uploaded = client.post(
        "/api/volumes", params={"recorded_by": "CMO", "subject": subject},
        content=nifti_bytes(image), headers={"Content-Type": "application/gzip"},
    )
    assert uploaded.status_code == 201, uploaded.text
    study = uploaded.json()["ledger_index"]
    done = wait(client, client.post(f"/api/volumes/{study}/segment").json()["job"])
    assert done["state"] == "done", done
    return int(done["ledger_index"])


def by_centre(rows: list[dict[str, Any]], lesions: list[dict[str, Any]]) -> dict[Any, Any]:
    """Las filas de la comparación, por el centro sintético más cercano a cada lesión."""
    centres = {item["id"]: item["centro_mm"] for item in lesions}
    known = (SAME, GROWING, SHRINKING, UNSEEN, GONE)
    return {
        min(known, key=lambda c: float(np.linalg.norm(np.subtract(c, centres[row["id"]])))): row
        for row in rows
    }


def test_each_lesion_says_how_it_changed_between_two_studies(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = segmented(client, monkeypatch, EARLIER)
    after = segmented(client, monkeypatch, LATER)
    response = client.get("/api/volumes/compare", params={"before": before, "after": after})
    assert response.status_code == 200, response.text
    body = response.json()
    # El mismo rótulo que el resto: nada de esto es una lectura.
    assert body["estado"] == assets.UNVALIDATED
    assert body["criterio"] == geometry.EVOLUTION_CRITERION and body["aviso"] is None
    lesions_after = get_store().segmentation_blob(after)[0]["lesiones"]
    rows = by_centre(body["lesiones"], lesions_after)
    assert len(body["lesiones"]) == len(LATER) == len(rows)
    assert rows[SAME]["evolucion"]["estado"] == "estable"
    assert rows[GROWING]["evolucion"]["estado"] == "crece"
    assert rows[SHRINKING]["evolucion"]["estado"] == "se reduce"
    # "No vista antes" no es "nueva": el modelo pudo no detectarla. Sin medida previa ni cambio.
    unseen = rows[UNSEEN]
    assert unseen["evolucion"] == {"estado": "no vista en el TC previo", "id_previo": None}
    assert unseen["previa"] is None
    for row in body["lesiones"]:
        assert row["estado"] == geometry.CANDIDATE
    # Antes y después, con las medidas de cada asiento firmado.
    lesions_before = {
        item["id"]: item for item in get_store().segmentation_blob(before)[0]["lesiones"]
    }
    growing = rows[GROWING]
    prior = lesions_before[growing["evolucion"]["id_previo"]]
    assert growing["previa"] == {
        "id": prior["id"], "diametro_mm": prior["diametro_mm"], "volumen_ml": prior["volumen_ml"],
        "densidad": prior["densidad"],
    }
    assert growing["diametro_mm"] > prior["diametro_mm"]
    assert growing["evolucion"]["delta_diametro_pct"] == pytest.approx(
        (growing["diametro_mm"] - prior["diametro_mm"]) / prior["diametro_mm"] * 100, abs=0.1
    )
    # La que estaba y ya no se encuentra se lista con su medida y sin estado, como en Polaris.
    [gone] = body["no_reencontradas"]
    assert lesions_before[gone["id_previo"]]["diametro_mm"] == gone["diametro_mm"]
    assert "estado" not in gone
    # Comparar no es medir: no entra en el análisis.
    assert get_store().query("crew-01") == []


def test_the_state_of_each_lesion_is_decided_by_polaris(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La respuesta lleva, sin tocar, lo que devuelve `visor3d.evolucion` de la copia."""
    from app import polaris

    before = segmented(client, monkeypatch, EARLIER)
    after = segmented(client, monkeypatch, LATER)
    params = {"before": before, "after": after}
    body = client.get("/api/volumes/compare", params=params).json()
    visor3d = polaris.load("visor3d")
    lesions_after = get_store().segmentation_blob(after)[0]["lesiones"]
    expected = visor3d.evolucion(body["pares"], lesions_after)
    assert {row["id"]: row["evolucion"] for row in body["lesiones"]} == expected
    assert {state["estado"] for state in expected.values()} == {
        "estable", "crece", "se reduce", "no vista en el TC previo",
    }
    # Y si Polaris dijera otra cosa, EMMA diría esa: aquí no hay una segunda regla.
    monkeypatch.setattr(
        visor3d, "evolucion",
        lambda pares, lesiones: {item["id"]: {"estado": "centinela", "id_previo": None}
                                 for item in lesiones},
    )
    again = client.get("/api/volumes/compare", params=params).json()
    assert {row["evolucion"]["estado"] for row in again["lesiones"]} == {"centinela"}


@pytest.mark.parametrize(("delta", "state"), [
    (geometry.GROWS_FROM_PCT, "crece"), (geometry.GROWS_FROM_PCT - 0.1, "estable"),
    (geometry.SHRINKS_FROM_PCT, "se reduce"), (geometry.SHRINKS_FROM_PCT + 0.1, "estable"),
    (None, "estable"),
])
def test_the_declared_criterion_is_the_one_polaris_applies(delta: float | None, state: str) -> None:
    """El criterio que se enseña junto al estado cita los umbrales de la copia: en la frontera."""
    pairs = [{"antes": 3, "despues": 1, "distancia_mm": 2.0, "delta_diametro_pct": delta,
              "delta_volumen_pct": 0.0}]
    [(lesion, result)] = geometry.evolution(pairs, [{"id": 1}]).items()
    assert lesion == 1 and result["estado"] == state and result["id_previo"] == 3
    assert f"+{geometry.GROWS_FROM_PCT} %" in geometry.EVOLUTION_CRITERION
    assert f"−{abs(geometry.SHRINKS_FROM_PCT)} %" in geometry.EVOLUTION_CRITERION


def test_the_evolution_texts_are_neither_an_order_nor_a_diagnosis() -> None:
    """Invariante 7: lo que sale junto a una lesión describe un tamaño; no ordena ni diagnostica."""
    from app import text_guard
    from app.api.volumes import DIFFERENT_PEOPLE_NOTE

    pairs = [
        {"antes": 1, "despues": 1, "delta_diametro_pct": 40.0},
        {"antes": 2, "despues": 2, "delta_diametro_pct": -40.0},
        {"antes": 3, "despues": 3, "delta_diametro_pct": 0.0},
        {"antes": None, "despues": 4},
    ]
    states = {
        item["estado"] for item in geometry.evolution(pairs, [{"id": n} for n in (1, 2, 3, 4)])
        .values()
    }
    assert len(states) == 4
    for text in (*states, geometry.EVOLUTION_CRITERION, DIFFERENT_PEOPLE_NOTE):
        assert text_guard.check(text) == [], text


def test_two_crew_members_are_not_compared(
    client: TestClient, fake_segmenter: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Emparejar las lesiones de dos personas no mide la evolución de ninguna."""
    mine = segmented(client, monkeypatch, EARLIER)
    theirs = segmented(client, monkeypatch, LATER, subject="crew-02")
    mixed = client.get("/api/volumes/compare", params={"before": mine, "after": theirs})
    assert mixed.status_code == 409 and "tripulante" in mixed.json()["detail"]


def test_two_dataset_patients_are_compared_with_a_warning(client: TestClient) -> None:
    """Los dos hígados de ejemplo son de pacientes distintos: se dice, no se vende de evolución."""
    first = client.post("/api/volumes/samples/higado-1").json()["segmentation"]
    second = client.post("/api/volumes/samples/higado-2").json()["segmentation"]
    body = client.get("/api/volumes/compare", params={"before": first, "after": second}).json()
    assert "pacientes distintos" in body["aviso"]
    assert body["estado"] == assets.UNVALIDATED and body["lesiones"]
    same = client.post("/api/volumes/samples/higado-1").json()["segmentation"]
    again = client.get("/api/volumes/compare", params={"before": first, "after": same}).json()
    assert again["aviso"] is None
    assert {row["evolucion"]["estado"] for row in again["lesiones"]} == {"estable"}


# --------------------------------------------------------------------------- #
# Densidad (HU) de cada lesión candidata: descriptiva, sin veredicto
# --------------------------------------------------------------------------- #

LIVER = assets.PRESETS["higado"]
ORGAN_HU, LESION_HU = 60, 20  # los del TAC sintético


def built(lesions: dict[tuple[int, int, int], float], image: Any = None) -> tuple[Any, Any]:
    """Ficheros y resumen del TAC sintético con esas lesiones (o de `image`, si se da otro)."""
    synthetic, masks = ct_with_lesions(lesions)
    reference = assets.resample(synthetic if image is None else image, LIVER.voxel_mm)
    return assets.build(reference, assets.mask_loader(reference, masks), LIVER)


def published(files: dict[str, bytes]) -> tuple[Any, Any]:
    """Lo que se publica en el zip: el TAC recortado y su mapa de etiquetas."""
    return tuple(  # type: ignore[return-value]
        np.asarray(nib.Nifti1Image.from_bytes(gzip.decompress(files[name])).dataobj)
        for name in ("ct.nii.gz", "etiquetas.nii.gz")
    )


def bare(summary: dict[str, Any], digest: str = "huella-de-prueba") -> dict[str, Any]:
    """El resumen como el de una segmentación guardada antes de que hubiera densidad."""
    return {
        **{key: value for key, value in summary.items() if key != "densidad"},
        "lesiones": [
            {k: v for k, v in item.items() if k != "densidad"} for item in summary["lesiones"]
        ],
        "sha256": digest,
    }


def test_each_lesion_carries_its_density_with_the_parenchyma_as_reference() -> None:
    files, summary = built({SAME: 8})
    ct, labels = published(files)
    [lesion] = summary["lesiones"]
    inside = ct[labels == 11].astype(float)
    density = lesion["densidad"]
    assert density["valorable"] and density["voxeles"] == inside.size >= geometry.DENSITY_MIN_VOXELS
    assert density["mediana_hu"] == pytest.approx(LESION_HU, abs=1)
    assert density["mediana_hu"] == round(float(np.median(inside)), 1)
    assert density["media_hu"] == round(float(inside.mean()), 1)
    assert density["desviacion_hu"] == round(float(inside.std()), 1)
    assert [density["p10_hu"], density["p90_hu"]] == [
        round(float(p), 1) for p in np.percentile(inside, [10, 90])
    ]
    # El borde mezcla lesión y órgano: la media queda por encima de la mediana, y se ve.
    assert density["p90_hu"] > density["mediana_hu"]

    block = summary["densidad"]
    assert block["disponible"] and block["unidad"] == "[hnsf'U]"
    assert block["minimo_voxeles"] == geometry.DENSITY_MIN_VOXELS
    reference = block["referencia"]
    # El órgano sin la lesión (etiqueta 1; la cava de dentro lleva la 4 y es de otra estructura).
    assert reference["voxeles"] == int((labels == 1).sum())
    assert reference["mediana_hu"] == ORGAN_HU and reference["valorable"]
    assert reference["nombre"] == "Hígado sin lesiones candidatas"
    # La misma mediana con la que se centra la ventana de este estudio.
    assert sum(summary["ventana_hu"]) / 2 == reference["mediana_hu"]
    # Sigue siendo lo que era: candidata, de una segmentación sin validar.
    assert lesion["estado"] == geometry.CANDIDATE and summary["estado"] == assets.UNVALIDATED


def test_the_density_is_in_real_hounsfield_units_when_the_volume_is_scaled() -> None:
    """Un TAC guardado en crudo (enteros sin signo, `scl_slope` y `scl_inter` en la cabecera)."""
    def raw_bytes(hounsfield: Any) -> bytes:
        image = nib.Nifti1Image((np.asarray(hounsfield) + 1024).astype(np.uint16), EYE)
        image.header.set_slope_inter(1.0, -1024.0)
        return bytes(image.to_bytes())

    plain, _ = synthetic_ct()
    stored = nib.Nifti1Image.from_bytes(raw_bytes(plain.dataobj))
    assert stored.dataobj.get_unscaled().min() == 24  # en disco, -1000 HU es un 24
    files, summary = built({SAME: 8}, stored)
    assert summary["lesiones"][0]["densidad"]["mediana_hu"] == pytest.approx(LESION_HU, abs=1)
    assert summary["densidad"]["referencia"]["mediana_hu"] == ORGAN_HU

    # Y al recalcular desde un zip cuyo `ct.nii.gz` está escalado.
    ct, _ = published(files)
    archive = assets.zip_files(
        {**files, "ct.nii.gz": gzip.compress(raw_bytes(ct))}, b"{}"
    )
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        on_disk = nib.Nifti1Image.from_bytes(gzip.decompress(bundle.read("ct.nii.gz")))
    # El zip lleva el crudo, no las HU: sin la escala de la cabecera saldrían 1024 de más.
    assert (on_disk.dataobj.slope, on_disk.dataobj.inter) == (1.0, -1024.0)
    assert on_disk.dataobj.get_unscaled().dtype == np.uint16
    again = geometry.with_stored_density(bare(summary), archive, (1, 2), "x")
    assert again["lesiones"][0]["densidad"] == summary["lesiones"][0]["densidad"]


def test_a_lesion_of_a_few_voxels_has_no_density_figure() -> None:
    """Radio 3 mm a 1,5 mm de vóxel: unas decenas de vóxeles, casi todos de borde."""
    _, summary = built({SAME: 8, GROWING: 3})
    large, small = summary["lesiones"]
    assert large["densidad"]["valorable"]
    density = small["densidad"]
    assert geometry.MIN_VOXELS <= density["voxeles"] < geometry.DENSITY_MIN_VOXELS
    assert not density["valorable"]
    assert f"{density['voxeles']} vóxeles" in density["motivo"]
    assert str(geometry.DENSITY_MIN_VOXELS) in density["motivo"]
    figures = ("mediana_hu", "media_hu", "desviacion_hu", "p10_hu", "p90_hu")
    assert all(density[name] is None for name in figures)
    # En la frontera: el mínimo declarado es el que se aplica.
    assert not geometry._hu(np.zeros(geometry.DENSITY_MIN_VOXELS - 1))["valorable"]
    assert geometry._hu(np.zeros(geometry.DENSITY_MIN_VOXELS))["valorable"]


def test_the_signed_density_is_the_one_recomputed_from_the_archive() -> None:
    files, summary = built({SAME: 8, SHRINKING: 6})
    stored = bare(summary, "huella-de-prueba-recalculo")
    again = assets.with_density(stored, lambda: assets.zip_files(files, b"{}"))
    assert again["densidad"] == summary["densidad"]
    assert again["lesiones"] == summary["lesiones"]
    assert "densidad" not in stored and "densidad" not in stored["lesiones"][0]  # copia

    def must_not_read() -> bytes:
        raise AssertionError("la que ya la lleva firmada no se recalcula")

    assert assets.with_density(summary, must_not_read) is summary


def test_a_remembered_density_never_lands_on_another_segmentation() -> None:
    """Lo recordado va por la huella firmada del zip, y sin huella no se recuerda nada."""
    files_one, one = built({SAME: 8})
    files_two, two = built({SAME: 8, SHRINKING: 6})
    files_small, small = built({SAME: 6})  # la misma lesión 1, con otros vóxeles
    assert small["lesiones"][0]["densidad"] != one["lesiones"][0]["densidad"]
    for summary, files in ((one, files_one), (small, files_small)):
        unsigned = {k: v for k, v in bare(summary).items() if k != "sha256"}
        again = assets.with_density(unsigned, lambda files=files: assets.zip_files(files, b"{}"))
        assert again["lesiones"] == summary["lesiones"]
    # Con la misma huella, las cifras se ponen sobre las lesiones de quien pregunta, por su id.
    first = assets.with_density(
        bare(one, "huella-de-prueba-recordada"), lambda: assets.zip_files(files_one, b"{}")
    )
    asked = bare(one, "huella-de-prueba-recordada")
    asked["lesiones"][0]["nota_propia"] = "sigue aquí"

    def must_not_read() -> bytes:
        raise AssertionError("ya estaba medida")

    second = assets.with_density(asked, must_not_read)
    assert second["lesiones"][0]["nota_propia"] == "sigue aquí"
    assert second["lesiones"][0]["densidad"] == first["lesiones"][0]["densidad"]
    assert second["densidad"] == first["densidad"]
    # Y si las lesiones no son las mismas, lo recordado no vale: se vuelve a medir.
    other = assets.with_density(
        bare(two, "huella-de-prueba-recordada"), lambda: assets.zip_files(files_two, b"{}")
    )
    assert other["lesiones"] == two["lesiones"]


def test_outside_a_ct_there_are_no_hounsfield_units() -> None:
    files, summary = built({SAME: 8})
    ct, labels = published(files)
    stored = bare(summary)
    said = geometry.with_density({**stored, "modalidad": "MR"}, ct, labels, (1, 2), "x")
    assert not said["densidad"]["disponible"] and "MR" in said["densidad"]["motivo"]
    assert said["densidad"]["referencia"] is None
    assert said["lesiones"] == stored["lesiones"]
    assert all("densidad" not in item for item in said["lesiones"])
    # Sin lesiones no hay nada que describir.
    empty = geometry.with_density({**stored, "lesiones": []}, ct, labels, (1,), "x")
    assert "densidad" not in empty


def test_an_unreadable_archive_says_so_and_the_segmentation_stays() -> None:
    files, summary = built({SAME: 8})
    stored = bare(summary, "huella-de-prueba-ilegible")
    broken = assets.with_density(stored, lambda: b"esto no es un zip")
    assert not broken["densidad"]["disponible"] and "BadZipFile" in broken["densidad"]["motivo"]
    assert broken["lesiones"] == stored["lesiones"]

    def gone() -> bytes:
        raise KeyError("el binario ya no es el firmado")

    missing = assets.with_density(stored, gone)
    assert "ya no es el firmado" in missing["densidad"]["motivo"]
    # Un fallo no se recuerda: en cuanto el zip se puede leer, la cifra sale.
    again = assets.with_density(stored, lambda: assets.zip_files(files, b"{}"))
    assert again["densidad"] == summary["densidad"]


def test_a_stored_sample_gets_its_density_without_touching_the_ledger(client: TestClient) -> None:
    index = client.post("/api/volumes/samples/higado-1").json()["segmentation"]
    entries = len(get_store().ledger)
    [study] = client.get("/api/volumes").json()
    [segmentation] = study["segmentations"]
    payload, archive = get_store().segmentation_blob(index)
    assert "densidad" not in payload  # el ejemplo está precalculado: su zip tiene huella fija
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        ct, labels = published({name: bundle.read(name) for name in bundle.namelist()})
    assert segmentation["densidad"]["disponible"]
    valued = 0
    for lesion in segmentation["lesiones"]:
        inside = ct[labels == 10 + lesion["id"]]
        density = lesion["densidad"]
        assert density["voxeles"] == inside.size
        assert density["valorable"] is (inside.size >= geometry.DENSITY_MIN_VOXELS)
        if density["valorable"]:
            valued += 1
            assert density["mediana_hu"] == float(np.median(inside))
            assert -100 < density["mediana_hu"] < 300  # tejido blando, con o sin contraste
    assert 0 < valued < len(segmentation["lesiones"]), "el ejemplo trae de las dos clases"
    reference = segmentation["densidad"]["referencia"]
    # El parénquima de la ventana: el órgano y los vasos de su interior, sin las lesiones.
    assert reference["voxeles"] == int(np.isin(labels, (1, 2)).sum()) > int((labels == 1).sum())
    assert reference["mediana_hu"] == float(np.median(ct[np.isin(labels, (1, 2))]))
    assert abs(sum(segmentation["ventana_hu"]) / 2 - reference["mediana_hu"]) <= 1
    # Se calcula al servir: ni un asiento más, ni un byte firmado distinto.
    assert len(get_store().ledger) == entries
    assert get_store().segmentation_blob(index)[0] == payload


def test_the_comparison_gives_both_densities_and_no_verdict(client: TestClient) -> None:
    from app import polaris

    first = client.post("/api/volumes/samples/higado-1").json()["segmentation"]
    second = client.post("/api/volumes/samples/higado-2").json()["segmentation"]
    body = client.get("/api/volumes/compare", params={"before": first, "after": second}).json()
    listed = {
        item["ledger_index"]: item
        for study in client.get("/api/volumes").json() for item in study["segmentations"]
    }
    assert body["densidad"] == {
        "antes": listed[first]["densidad"], "despues": listed[second]["densidad"],
    }
    for side in ("antes", "despues"):
        assert geometry.PHASE_UNDECLARED in body["densidad"][side]["notas"]
    before = {item["id"]: item["densidad"] for item in listed[first]["lesiones"]}
    after = {item["id"]: item["densidad"] for item in listed[second]["lesiones"]}
    paired = 0
    for row in body["lesiones"]:
        assert row["densidad"] == after[row["id"]]
        if row["previa"] is not None:
            paired += 1
            assert row["previa"]["densidad"] == before[row["previa"]["id"]]
        # El estado sigue saliendo del diámetro, y nada resta ni califica las dos densidades.
        assert not any("densidad" in key or "hu" in key for key in row["evolucion"])
    assert paired or body["no_reencontradas"]
    for gone in body["no_reencontradas"]:
        assert gone["densidad"] == before[gone["id_previo"]]
    stored = get_store().segmentation_blob(second)[0]["lesiones"]
    expected = polaris.load("visor3d").evolucion(body["pares"], stored)
    assert {row["id"]: row["evolucion"] for row in body["lesiones"]} == expected


def test_what_is_said_next_to_a_density_describes_and_does_not_classify() -> None:
    """Invariantes 6 y 7: ni orden, ni diagnóstico, ni el nombre de lo que la lesión podría ser."""
    from app import text_guard

    _, summary = built({SAME: 8, GROWING: 3})
    shown = [
        *summary["densidad"]["notas"], summary["densidad"]["referencia"]["nombre"],
        summary["densidad"]["no_valorable"], summary["lesiones"][1]["densidad"]["motivo"],
        geometry.NOT_CT.format(modality="MR"), geometry.UNREADABLE.format(reason="motivo"),
    ]
    assert geometry.DENSITY_NOTE in shown and geometry.PHASE_UNDECLARED in shown
    assert "sin validar" in geometry.DENSITY_NOTE
    assert "fase de contraste" in geometry.PHASE_UNDECLARED
    for text in shown:
        assert text_guard.check(text) == [], text
        lowered = text.lower()
        for word in ("quiste", "metást", "benign", "malign", "tumor", "hemangioma", "grasa"):
            assert word not in lowered, text


# --------------------------------------------------------------------------- #
# Defensas del lanzador y del ledger
# --------------------------------------------------------------------------- #


def test_segmentation_refuses_to_run_with_telemetry_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Polaris aborta si TotalSegmentator envía estadísticas de uso: un TAC no genera avisos."""
    home = tmp_path / "totalseg"
    home.mkdir()
    (home / "config.json").write_text('{"send_usage_stats": true}', encoding="utf-8")
    monkeypatch.setenv("TOTALSEG_HOME_DIR", str(home))
    assert segment.telemetry_off("x") is False

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no se debía lanzar TotalSegmentator")

    monkeypatch.setattr(segment.subprocess, "run", never)
    with pytest.raises(segment.SegmenterUnavailable, match="telemetría"):
        segment.run("x", tmp_path / "ct.nii.gz", tmp_path / "out", assets.PRESETS["ojos"])
    (home / "config.json").write_text('{"send_usage_stats": false}', encoding="utf-8")
    assert segment.telemetry_off("x") is True


def test_a_task_that_fails_on_the_gpu_is_repeated_on_the_cpu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """nnU-Net aún falla en GPU: esa tarea se repite en CPU, las que quedan ya van a CPU (no se
    pierde un intento de GPU en cada una) y la segmentación termina."""
    monkeypatch.setattr(segment, "telemetry_off", lambda exe: True)
    monkeypatch.setattr(segment, "required_ram_gb", lambda ct, preset: None)
    devices: list[tuple[str, str]] = []

    def fake(command: list[str], **kwargs: Any) -> Any:
        task, device = command[command.index("-ta") + 1], command[command.index("-d") + 1]
        devices.append((task, device))
        if device == "gpu" and len(devices) == 1:
            return type("R", (), {"returncode": 1, "stderr": "CUDA error: illegal memory access",
                                  "stdout": ""})()
        out = Path(command[command.index("-o") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{task}.nii.gz").write_bytes(b"")
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(segment.subprocess, "run", fake)
    preset = assets.PRESETS["higado"]
    masks = segment.run("x", tmp_path / "ct.nii.gz", tmp_path / "out", preset)
    first = preset.tasks[0][0]
    assert devices[:2] == [(first, "gpu"), (first, "cpu")]
    assert [device for _, device in devices[2:]] == ["cpu"] * (len(preset.tasks) - 1)
    assert set(masks) == {task for task, _ in preset.tasks}

    def always_fails(command: list[str], **kwargs: Any) -> Any:
        devices.append((command[command.index("-ta") + 1], command[command.index("-d") + 1]))
        return type("R", (), {"returncode": 1, "stderr": "otro fallo", "stdout": ""})()

    monkeypatch.setattr(segment.subprocess, "run", always_fails)
    devices.clear()
    with pytest.raises(segment.SegmenterUnavailable, match="falló"):
        segment.run("x", tmp_path / "ct.nii.gz", tmp_path / "out2", preset, device="cpu")
    assert devices == [(first, "cpu")]


def test_a_segmentation_must_cite_the_signed_volume(client: TestClient) -> None:
    image, _ = synthetic_ct()
    study = upload(client, image)
    payload = {"study_index": study, "study_sha256": "0" * 64, "sha256": "", "preset": "higado",
               "estado": assets.UNVALIDATED}
    archive = b"zip"
    payload["sha256"] = __import__("hashlib").sha256(archive).hexdigest()
    payload["size_bytes"] = len(archive)
    from app.api.routes import identity_for

    with pytest.raises(ValueError, match="otro volumen"):
        get_store().record_volume_segmentation(payload, archive, identity_for("segmentation-local"))


def test_the_polaris_viewer_reads_this_segmentation_in_its_own_layout(
    client: TestClient,
) -> None:
    """El visor de Polaris (copia literal) pide `./indice.json` y `./<fecha>/...`: del ledger."""
    index = client.post("/api/volumes/samples/higado-1").json()["segmentation"]
    base = f"/api/volumes/segmentations/{index}/polaris"
    assert client.get(f"{base}/indice.json").json() == {"fechas": ["estudio"]}
    study = client.get(f"{base}/estudio/estudio.json").json()
    assert study["mallas"]["higado"] == "higado.ply"
    assert study["volumen_higado_ml"] > 0 and len(study["ventana_hu"]) == 2
    assert all("segmento" in lesion for lesion in study["lesiones"])
    ply = client.get(f"{base}/estudio/{study['mallas']['higado']}")
    assert ply.status_code == 200 and ply.content.startswith(b"ply")
    # Solo lo que guarda el binario firmado, y nada fuera de esa carpeta.
    assert client.get(f"{base}/estudio/otro.ply").status_code == 404
    assert client.get(f"{base}/comparacion.json").status_code == 404
    assert client.get(f"{base}/../../../main.py").status_code == 404


def test_the_viewer_constants_are_polaris_own() -> None:
    """Lo que no se llama al original (constantes al nivel de módulo) tiene que ser idéntico."""
    from app import polaris

    visor3d = polaris.load("visor3d")
    assert assets.AIR_HU == visor3d.AIRE_HU
    assert assets.WINDOW_WIDTH == visor3d.VENTANA_ANCHO
    assert geometry.CANDIDATE == visor3d.ESTADO_CANDIDATA
    assert geometry.SMALL_LESION_MM == visor3d.UMBRAL_PEQUENA_MM
    assert geometry.MIN_VOXELS == visor3d.MIN_VOXELES


# --------------------------------------------------------------------------- #
# Esqueleto (Polaris `visor3d.PRESETS["esqueleto"]`)
# --------------------------------------------------------------------------- #


def test_the_skeleton_preset_is_the_reference_skeleton_bone_by_bone() -> None:
    import json

    preset = assets.PRESETS["esqueleto"]
    reference = json.loads(
        (Path(assets.__file__).parents[1] / "data" / "anatomy" / "esqueleto.json")
        .read_text(encoding="utf-8")
    )
    assert {item.mask for item in preset.structures} == set(reference["huesos"])
    assert [item.label for item in preset.structures] == list(range(1, 61))
    # La tarea entera, sin `--roi_subset`: con él se perdían 20 de 60 huesos (2026-10-06).
    assert preset.tasks == (("total", None),) and preset.margin_mm == 0.0
    assert assets.bone_display("rib_left_3") == "Costilla izquierda 3"
    assert assets.bone_display("hip_right") == "Coxal derecho"
    # El lado concuerda con el género del hueso (salía «Clavícula izquierdo»).
    assert assets.bone_display("clavicula_left") == "Clavícula izquierda"
    assert assets.bone_display("scapula_right") == "Escápula derecha"
    assert assets.bone_display("sternum") == "Esternón"


def test_the_skeleton_builds_from_bone_masks() -> None:
    shape = (60, 60, 60)
    data = np.full(shape, -1000, np.int16)
    femur = ball(shape, (30, 30, 20), 10)
    vertebra = ball(shape, (30, 30, 45), 8)
    data[femur | vertebra] = 700
    image = nib.Nifti1Image(data, EYE)
    masks = {
        "femur_left": nib.Nifti1Image(femur.astype(np.uint8), EYE),
        "vertebrae_L1": nib.Nifti1Image(vertebra.astype(np.uint8), EYE),
    }
    preset = assets.PRESETS["esqueleto"]
    reference = assets.resample(image, preset.voxel_mm)
    files, summary = assets.build(reference, assets.mask_loader(reference, masks), preset)
    assert {"femur_left.ply", "vertebrae_L1.ply"} <= set(files)
    assert summary["estado"] == assets.UNVALIDATED


# --------------------------------------------------------------------------- #
# Control de la cadena vertebral (Polaris `_revisa_cadena` y `_orden_columna`, `volumes/spine.py`)
# --------------------------------------------------------------------------- #

SKELETON = assets.PRESETS["esqueleto"]
CHAIN = [bone for bone in assets.BONES if bone.startswith("vertebrae_")] + ["sacrum"]
PITCH = 14  # mm entre niveles del esqueleto sintético
SPINE_AFFINE = np.diag([2.0, 2.0, 2.0, 1.0])
# Los 20 huesos que perdió la segmentación real del ejemplo de cuerpo entero (40 de 60).
LOST_IN_THE_REAL_CASE = (
    "vertebrae_C1", "vertebrae_C2", "vertebrae_C3", "vertebrae_C4", "vertebrae_T11",
    "vertebrae_T12", "vertebrae_L1", "vertebrae_L2", "vertebrae_L3", "vertebrae_L4",
    "vertebrae_L5", "sacrum", "hip_left", "hip_right", "femur_left", "femur_right",
    "rib_left_11", "rib_left_12", "rib_right_11", "rib_right_12",
)


def skeleton_masks(
    missing: tuple[str, ...] = (), order: list[str] | None = None, cut_below: str | None = None,
    thin: tuple[str, ...] = (), only_the_spine: bool = False,
) -> dict[str, Any]:
    """Los 60 huesos en una rejilla de 2 mm: la columna apilada en z (C1 arriba), el resto al lado.

    `missing` quita huesos; `order` da el orden en que se apilan los niveles (por defecto, el de
    la cadena); `cut_below` acaba el volumen justo bajo ese nivel; `thin` deja esos niveles en una
    lámina de menos de 2000 mm³; `only_the_spine` deja fuera los otros 35 huesos.
    """
    order = order or CHAIN
    floor = (len(CHAIN) - 1 - CHAIN.index(cut_below)) * PITCH if cut_below else 0
    shape = (80, 40, (20 + PITCH * len(CHAIN) - floor) // 2 + 15)
    masks: dict[str, Any] = {}
    for slot, name in enumerate(order):
        z = (10 + PITCH * (len(CHAIN) - 1 - slot) - floor) // 2
        mask = np.zeros(shape, bool)
        if z >= 0:
            mask[5:15, 5:15, z:z + (1 if name in thin else 5)] = True  # 20×20×10 mm = 4000 mm³
        masks[name] = mask
    others = [] if only_the_spine else [name for name in assets.BONES if name not in CHAIN]
    for slot, name in enumerate(others):
        mask = np.zeros(shape, bool)
        x, z = 30 + 5 * (slot % 7), 5 + 5 * (slot // 7)
        mask[x:x + 3, 10:14, z:z + 3] = True
        masks[name] = mask
    return {name: mask for name, mask in masks.items() if name not in missing and mask.any()}


def spine_review(**kwargs: Any) -> dict[str, Any]:
    """El control sobre el mapa de etiquetas de ese esqueleto, compuesto como en `assets.build`."""
    from app.volumes import spine

    masks = skeleton_masks(**kwargs)
    labels = np.zeros(next(iter(masks.values())).shape, np.uint8)
    for structure in SKELETON.structures:
        if structure.mask in masks:
            labels[masks[structure.mask]] = structure.label
    field = spine.field_z_mm(labels.shape, SPINE_AFFINE)
    return spine.review(labels, SPINE_AFFINE, SKELETON, field)


def titles(review: dict[str, Any]) -> dict[str, tuple[str, list[str]]]:
    return {item["titulo"]: (item["nivel"], item["elementos"]) for item in review["listas"]}


def test_a_whole_spine_in_order_raises_no_notice() -> None:
    review = spine_review()
    assert review["revisada"] is True and review["control"].startswith("Polaris visor3d")
    assert review["niveles_presentes"] == CHAIN and review["niveles_esperados"] == 25
    assert review["niveles_ausentes"] == [] and review["huecos"] == []
    assert review["extremos"] == [] and review["niveles_pequenos"] == []
    assert review["orden_coherente"] is True and review["invertida"] is False
    assert review["huesos_sin_voxeles"] == [] and review["huesos_esperados"] == 60
    assert review["nivel"] is None and review["aviso"] is None and review["listas"] == []


def test_a_level_missing_in_the_middle_is_a_gap() -> None:
    review = spine_review(missing=("vertebrae_T7",))
    assert review["huecos"] == ["vertebrae_T7"] == review["niveles_ausentes"]
    assert review["orden_coherente"] is True and review["extremos"] == []
    assert review["huesos_sin_voxeles"] == ["vertebrae_T7"]
    assert review["nivel"] == "atencion" and "no un hallazgo sobre la persona" in review["aviso"]
    assert titles(review) == {
        "Niveles ausentes en mitad de la cadena": ("atencion", ["Vértebra T7"]),
    }


def test_the_lower_end_missing_while_the_volume_goes_on_is_said() -> None:
    """La columna acaba en T12 y el volumen sigue: Polaris no lo cuenta como hueco; EMMA lo dice."""
    lost = ("vertebrae_L1", "vertebrae_L2", "vertebrae_L3", "vertebrae_L4", "vertebrae_L5",
            "sacrum", "hip_left", "hip_right")
    review = spine_review(missing=lost)
    assert review["huecos"] == [], "para Polaris un extremo no es un hueco"
    [end] = review["extremos"]
    assert end["lado"] == "caudal" and end["niveles"] == list(lost[:6])
    assert end["volumen_continua"] is True
    assert end["paso_mm"] == PITCH and end["margen_mm"] >= 1.5 * PITCH
    assert review["huesos_sin_voxeles"] == list(lost)
    assert review["nivel"] == "atencion"
    assert titles(review) == {
        "Niveles ausentes en el extremo caudal: el volumen continúa más allá": (
            "atencion",
            ["Vértebra L1", "Vértebra L2", "Vértebra L3", "Vértebra L4", "Vértebra L5", "Sacro"],
        ),
        "Otros huesos sin vóxeles": ("dato_ausente", ["Coxal izquierdo", "Coxal derecho"]),
    }


def test_the_upper_end_missing_while_the_volume_goes_on_is_said() -> None:
    review = spine_review(missing=("vertebrae_C1", "vertebrae_C2"))
    [end] = review["extremos"]
    assert end["lado"] == "craneal" and end["niveles"] == ["vertebrae_C1", "vertebrae_C2"]
    assert end["volumen_continua"] is True
    assert review["nivel"] == "atencion"


def test_an_end_where_the_volume_stops_is_not_a_caution() -> None:
    """Un TAC que acaba en T12 no ha perdido la lumbar: no la tiene. Dato ausente, no precaución."""
    from app.volumes import spine

    review = spine_review(cut_below="vertebrae_T12")
    [end] = review["extremos"]
    assert end["niveles"][0] == "vertebrae_L1" and end["volumen_continua"] is False
    assert end["margen_mm"] < 1.5 * end["paso_mm"]
    assert review["huecos"] == [] and review["orden_coherente"] is True
    assert review["nivel"] == "dato_ausente"
    assert review["aviso"] == spine.NOTICES["dato_ausente"]
    assert {level for level, _ in titles(review).values()} == {"dato_ausente"}
    assert "Niveles ausentes en el extremo caudal: el volumen termina ahí" in titles(review)


def test_the_room_beyond_an_end_is_measured_between_whole_levels() -> None:
    """El paso es el de los dos niveles ENTEROS de ese extremo: con un hueco entre ellos se reparte
    entre los niveles que separa, y una vértebra a medias en el borde no lo acorta."""
    review = spine_review(missing=("vertebrae_C1", "vertebrae_C3"))
    [end] = review["extremos"]
    assert end["lado"] == "craneal" and end["paso_mm"] == PITCH
    assert review["huecos"] == ["vertebrae_C3"]
    review = spine_review(missing=("vertebrae_C1",), thin=("vertebrae_C2",))
    [end] = review["extremos"]
    assert end["paso_mm"] == PITCH and end["volumen_continua"] is True


def test_shuffled_levels_are_out_of_order() -> None:
    """Polaris lo midió: el modelo nombraba la columna C7→S1→C6→C5… y el render se veía perfecto."""
    order = list(CHAIN)
    a, b = order.index("vertebrae_T5"), order.index("vertebrae_T9")
    order[a], order[b] = order[b], order[a]
    review = spine_review(order=order, missing=("vertebrae_C1",))
    assert review["orden_coherente"] is False and review["invertida"] is False
    assert review["huecos"] == []
    assert review["rompen_orden"], "Polaris dice qué niveles lo rompen"
    assert set(review["rompen_orden"]) <= set(CHAIN)
    assert review["nivel"] == "atencion"
    level, shown = titles(review)["Niveles fuera del orden craneocaudal"]
    assert level == "atencion" and shown
    # Con el orden roto no se sabe hacia dónde queda cada extremo: no se mide.
    [end] = review["extremos"]
    assert end["volumen_continua"] is None and end["margen_mm"] is None
    assert "no se pudo medir si el volumen continúa" in " ".join(titles(review))


def test_a_spine_upside_down_is_out_of_order() -> None:
    """Monótona en el otro sentido: Polaris la acepta, y con la z del mundo está del revés."""
    review = spine_review(order=CHAIN[::-1])
    assert review["orden_coherente"] is False and review["invertida"] is True
    assert review["nivel"] == "atencion"
    assert any(title.startswith("Cadena del revés") for title in titles(review))


def test_a_level_recognised_by_halves_in_the_middle_is_said() -> None:
    """El caso de Polaris: T9 con 58 mm³ en mitad de una cadena que se veía entera."""
    review = spine_review(thin=("vertebrae_T9",))
    assert review["niveles_pequenos"] == [
        {"nivel": "vertebrae_T9", "volumen_mm3": 800, "en_extremo": False},
    ]
    assert review["umbral_pequeno_mm3"] == 2000
    assert review["nivel"] == "atencion"
    assert titles(review) == {
        "Niveles reconocidos a medias en mitad de la cadena": ("atencion", ["Vértebra T9"]),
    }


def test_levels_cut_by_the_edge_of_the_volume_are_not_a_caution() -> None:
    """Donde el volumen acaba, la última vértebra sale cortada: es el borde, no un fallo."""
    review = spine_review(thin=("vertebrae_C1", "vertebrae_C2", "sacrum"))
    assert [item["en_extremo"] for item in review["niveles_pequenos"]] == [True, True, True]
    assert review["nivel"] == "dato_ausente"
    assert titles(review) == {
        "Niveles reconocidos a medias en un extremo de la cadena": (
            "dato_ausente", ["Vértebra C1", "Vértebra C2", "Sacro"],
        ),
    }


def test_without_any_vertebra_it_is_missing_data() -> None:
    review = spine_review(missing=tuple(CHAIN))
    assert review["revisada"] is True and review["niveles_presentes"] == []
    assert review["orden_coherente"] is None and review["extremos"] == []
    assert review["nivel"] == "dato_ausente"
    assert len(titles(review)["Sin niveles vertebrales en esta segmentación"][1]) == 25


def test_if_polaris_says_something_else_the_review_is_declared_not_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El veredicto se lee del texto con el que Polaris aborta. Si la copia lo cambia, no se da la
    cadena ni por buena ni por mala: se dice que el control no se hizo. Y no lanza: la
    segmentación que describe sigue adelante."""
    from app import polaris

    def other_words(*args: Any) -> None:
        raise SystemExit("ABORTA: con otras palabras")

    monkeypatch.setattr(polaris.load("visor3d"), "_revisa_cadena", other_words)
    review = spine_review(missing=("vertebrae_T7",))
    assert review["revisada"] is False and "_revisa_cadena" in review["motivo"]
    assert review["orden_coherente"] is None and review["huecos"] == []
    assert review["nivel"] == "dato_ausente" and "No se pudo hacer el control" in review["aviso"]
    # Lo que no depende de Polaris se sigue diciendo.
    assert review["huesos_sin_voxeles"] == ["vertebrae_T7"]
    assert titles(review) == {"Huesos sin vóxeles": ("dato_ausente", ["Vértebra T7"])}


def test_what_the_review_says_passes_the_language_guard() -> None:
    """Texto que ve la tripulación: ni orden, ni diagnóstico, ni certeza (invariante 7)."""
    from app import text_guard
    from app.volumes import spine

    shown = [*spine.NOTICES.values(), spine.NOT_DONE.format(reason="motivo")]
    for kwargs in (
        {"missing": ("vertebrae_T7", "vertebrae_C1", "hip_left")},
        {"cut_below": "vertebrae_T12", "thin": ("vertebrae_T9", "vertebrae_C1")},
        {"order": CHAIN[::-1]},
        {"missing": tuple(CHAIN)},
    ):
        review = spine_review(**kwargs)
        shown += [review["aviso"], *titles(review)]
    for text in shown:
        assert text_guard.check(text) == [], text
    for notice in spine.NOTICES.values():
        assert "sin validar" in notice and "no un hallazgo sobre la persona" in notice


def test_only_the_skeleton_preset_carries_the_spine_review() -> None:
    image, masks = synthetic_ct()
    reference = assets.resample(image)
    _, summary = assets.build(
        reference, assets.mask_loader(reference, masks), assets.PRESETS["higado"]
    )
    assert "cadena_vertebral" not in summary


def _sample_labels() -> tuple[Any, Any, tuple[float, float]]:
    """El mapa de etiquetas y el campo del ejemplo real `esqueleto-4`, tal como viajan."""
    from app.volumes import spine
    from app.volumes.samples import load_sample

    _, volume, archive = load_sample("esqueleto-4")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        raw = gzip.decompress(bundle.read("etiquetas.nii.gz"))
    image = nib.Nifti1Image.from_bytes(raw)
    return np.asarray(image.dataobj), image.affine, spine.volume_field_z_mm(volume)


def test_the_real_case_of_40_bones_out_of_60_now_raises_a_caution() -> None:
    """El fallo que motivó el control, sobre la anatomía real del ejemplo: sin C1-C4 y sin nada de
    T11 hacia abajo. No hay hueco en medio —Polaris, solo, lo daba por bueno— y el volumen sí
    cubría los dos extremos."""
    from app.volumes import spine

    labels, affine, field = _sample_labels()
    label_of = {structure.mask: structure.label for structure in SKELETON.structures}
    lost = [label_of[name] for name in LOST_IN_THE_REAL_CASE]
    labels = np.where(np.isin(labels, lost), 0, labels)
    review = spine.review(labels, affine, SKELETON, field)
    assert review["revisada"] is True and len(review["huesos_sin_voxeles"]) == 20
    assert review["huecos"] == [] and review["orden_coherente"] is True
    upper, lower = review["extremos"]
    assert upper["lado"] == "craneal" and upper["niveles"][-1] == "vertebrae_C4"
    assert lower["lado"] == "caudal" and lower["niveles"][0] == "vertebrae_T11"
    assert upper["volumen_continua"] is True and lower["volumen_continua"] is True
    assert review["nivel"] == "atencion"
    assert [level for level, _ in titles(review).values()] == [
        "atencion", "atencion", "dato_ausente",
    ]


@pytest.mark.parametrize(("top", "bottom"), [
    ("vertebrae_C7", "vertebrae_T12"), ("vertebrae_T1", "vertebrae_L5"),
])
def test_a_real_volume_that_stops_at_a_level_is_not_a_caution(top: str, bottom: str) -> None:
    """El otro eje: el mismo ejemplo real, con el volumen acabado entre esas dos vértebras. Casi
    ningún TAC cubre la columna entera; si eso pidiera atención, el aviso no valdría nada. En el
    borde quedan vértebras cortadas (aquí, 64 y 1288 mm³): son el borde, no un fallo."""
    from app.volumes import spine

    labels, affine, _ = _sample_labels()
    label_of = {structure.mask: structure.label for structure in SKELETON.structures}
    rows = np.nonzero(np.isin(labels, [label_of[top], label_of[bottom]]))[2]
    cut = labels[:, :, rows.min():rows.max() + 1]
    moved = affine.copy()
    moved[:3, 3] = (affine @ [0, 0, rows.min(), 1.0])[:3]
    review = spine.review(cut, moved, SKELETON, spine.field_z_mm(cut.shape, moved))
    assert review["revisada"] is True and review["extremos"]
    assert review["huecos"] == [] and review["orden_coherente"] is True
    assert {end["volumen_continua"] for end in review["extremos"]} == {False}
    assert review["niveles_pequenos"], "el borde corta una vértebra"
    assert all(item["en_extremo"] for item in review["niveles_pequenos"])
    assert review["nivel"] == "dato_ausente"


def _skeleton_segmenter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, masks: dict[str, Any]
) -> None:
    """TotalSegmentator simulado para el preset esqueleto: escribe esas máscaras de hueso."""
    executable = tmp_path / "TotalSegmentator.exe"
    executable.write_bytes(b"")

    def run(exe: str, ct: Path, out: Path, preset: assets.Preset, device: str = "gpu") -> Any:
        out.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name, mask in masks.items():
            paths[name] = out / f"{name}.nii.gz"
            nib.save(nib.Nifti1Image(mask.astype(np.uint8), SPINE_AFFINE), paths[name])
        return paths

    monkeypatch.setattr(segment, "find", lambda configured=None: str(executable))
    monkeypatch.setattr(segment, "telemetry_off", lambda exe: True)
    monkeypatch.setattr(segment, "run", run)


def test_a_new_skeleton_segmentation_is_signed_with_its_spine_review(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Las nuevas llevan el control en su resumen firmado, y recalculado desde su zip da lo mismo
    (que es lo que se hace al servir las guardadas sin él)."""
    import json

    from app.volumes import spine

    kwargs: dict[str, Any] = {
        "missing": ("vertebrae_T7", "vertebrae_L5", "sacrum"), "only_the_spine": True,
    }
    masks = skeleton_masks(**kwargs)
    bone = np.any(list(masks.values()), axis=0)
    image = nib.Nifti1Image(np.where(bone, 700, -1000).astype(np.int16), SPINE_AFFINE)
    _skeleton_segmenter(monkeypatch, tmp_path, masks)
    study = upload(client, image)
    started = client.post(f"/api/volumes/{study}/segment", params={"preset": "esqueleto"})
    done = wait(client, started.json()["job"])
    assert done["state"] == "done", done

    [listed] = client.get("/api/volumes").json()
    [segmentation] = listed["segmentations"]
    review = segmentation["cadena_vertebral"]
    assert review == spine_review(**kwargs), "en la rejilla publicada dice lo mismo"
    assert review["huecos"] == ["vertebrae_T7"] and review["nivel"] == "atencion"
    [end] = review["extremos"]
    assert end["niveles"] == ["vertebrae_L5", "sacrum"] and end["volumen_continua"] is True
    assert len(review["huesos_sin_voxeles"]) == 38
    store = get_store()
    stored, archive = store.segmentation_blob(segmentation["ledger_index"])
    assert stored["cadena_vertebral"] == review, "firmado en el asiento"
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        assert json.loads(bundle.read("estudio.json"))["cadena_vertebral"] == review
    _, volume = store.volume_blob(study)
    assert spine.review_stored(archive, volume, SKELETON) == review
    unmeasured = spine.review_stored(archive, None, SKELETON)
    assert unmeasured["extremos"][0]["volumen_continua"] is None
    assert unmeasured["huecos"] == ["vertebrae_T7"]
    assert store.query("crew-01") == [], "no es una lectura: no entra en el análisis"
    assert store.verify_integrity().ok


def test_a_control_that_fails_does_not_stop_the_segmentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Es descriptivo: si el control revienta, la segmentación se construye igual y lo dice."""
    from app import polaris

    def broken(*args: Any) -> None:
        raise RuntimeError("roto")

    monkeypatch.setattr(polaris.load("visor3d"), "_orden_columna", broken)
    masks = skeleton_masks(only_the_spine=True, missing=tuple(CHAIN[3:]))
    bone = np.any(list(masks.values()), axis=0)
    image = nib.Nifti1Image(np.where(bone, 700, -1000).astype(np.int16), SPINE_AFFINE)
    loader = assets.mask_loader(
        image, {n: nib.Nifti1Image(m.astype(np.uint8), SPINE_AFFINE) for n, m in masks.items()}
    )
    files, summary = assets.build(image, loader, SKELETON)
    assert "vertebrae_C1.ply" in files
    review = summary["cadena_vertebral"]
    assert review["revisada"] is False and review["motivo"] == "RuntimeError: roto"
    assert review["nivel"] == "dato_ausente"


def _skeleton_sample_stored_without_its_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`esqueleto-4` como viajó hasta el 2026-10-08: guardado SIN el control en su índice.

    Desde que se regeneró (para corregir «Clavícula izquierdo») lo lleva firmado, como toda
    segmentación nueva, y dejó de ser el caso «guardada antes del control». Ese camino sigue
    existiendo para las segmentaciones antiguas de un almacén real: aquí se rehace sobre una
    copia, con los mismos binarios y el índice sin esa clave."""
    import hashlib
    import json
    import shutil

    from app.volumes import samples

    copy = tmp_path / "volume_samples"
    shutil.copytree(samples.SAMPLES_DIR, copy)
    path = copy / "esqueleto-4" / "visor.zip"
    with zipfile.ZipFile(path) as bundle:
        files = {n: bundle.read(n) for n in bundle.namelist() if n != "estudio.json"}
        summary = json.loads(bundle.read("estudio.json"))
    del summary["cadena_vertebral"]
    archive = assets.zip_files(files, json.dumps(summary, ensure_ascii=False).encode("utf-8"))
    path.write_bytes(archive)
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    [entry] = [item for item in manifest["samples"] if item["key"] == "esqueleto-4"]
    entry["sha256"]["visor.zip"] = hashlib.sha256(archive).hexdigest()
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(samples, "SAMPLES_DIR", copy)


def test_the_skeleton_sample_signs_todays_bone_names_and_its_spine_review(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El índice firmado del ejemplo dice lo que dice hoy el código: los nombres de `bone_display`
    (viajó con «Clavícula izquierdo» y «Escápula derecho» hasta que se regeneró) y el control de
    la cadena, que es el mismo que sale de recalcularlo desde su zip y su volumen."""
    import json

    from app.api import volumes as volumes_api
    from app.volumes import spine
    from app.volumes.samples import load_sample

    _, volume, archive = load_sample("esqueleto-4")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        signed = json.loads(bundle.read("estudio.json"))
    names = {item["key"]: item["nombre"] for item in signed["estructuras"]}
    assert names == {structure.key: structure.display for structure in SKELETON.structures}
    assert names["clavicula_left"] == "Clavícula izquierda"
    assert names["scapula_right"] == "Escápula derecha"
    assert signed["cadena_vertebral"] == spine.review_stored(archive, volume, SKELETON)

    # Al servirlo no se recalcula nada: sale lo firmado, nombres incluidos.
    monkeypatch.setattr(volumes_api.spine, "review_stored", None)
    client.post("/api/volumes/samples/esqueleto-4")
    [segmentation] = client.get("/api/volumes").json()[0]["segmentations"]
    assert segmentation["cadena_vertebral"] == signed["cadena_vertebral"]
    assert {item["key"]: item["nombre"] for item in segmentation["estructuras"]} == names
    assert get_store().verify_integrity().ok


def test_a_skeleton_stored_without_its_spine_review_gets_it_without_touching_the_ledger(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Una segmentación guardada antes del control tiene su zip firmado sin él: se calcula al
    servir, desde lo firmado, y viaja solo en la respuesta."""
    from app.api import volumes as volumes_api

    _skeleton_sample_stored_without_its_review(monkeypatch, tmp_path)
    monkeypatch.setattr(volumes_api, "_spine_reviews", {})
    client.post("/api/volumes/samples/esqueleto-4")
    [study] = client.get("/api/volumes").json()
    [segmentation] = study["segmentations"]
    review = segmentation["cadena_vertebral"]
    assert review["revisada"] is True
    assert len(review["niveles_presentes"]) == review["niveles_esperados"] == 25
    assert review["huecos"] == [] and review["orden_coherente"] is True
    assert review["huesos_sin_voxeles"] == [] and review["nivel"] is None
    [stored] = get_store().volume_segmentations(study["ledger_index"])
    assert "cadena_vertebral" not in stored, "lo firmado no cambia"
    assert stored["sha256"] == segmentation["sha256"]
    assert get_store().verify_integrity().ok
    # La segunda vez no se vuelve a calcular: sale de las huellas firmadas.
    monkeypatch.setattr(volumes_api.spine, "review_stored", None)
    assert client.get("/api/volumes").json()[0]["segmentations"][0]["cadena_vertebral"] == review
    # Los demás presets no lo llevan.
    client.post("/api/volumes/samples/higado-1")
    [liver] = [
        item for item in client.get("/api/volumes").json()
        if item["ledger_index"] != study["ledger_index"]
    ]
    assert "cadena_vertebral" not in liver["segmentations"][0]


def test_a_review_that_could_not_be_done_is_tried_again(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Solo se guarda un control hecho: el que falló (hoy no carga Polaris) se reintenta."""
    from app.api import volumes as volumes_api
    from app.volumes import spine

    _skeleton_sample_stored_without_its_review(monkeypatch, tmp_path)
    monkeypatch.setattr(volumes_api, "_spine_reviews", {})
    client.post("/api/volumes/samples/esqueleto-4")
    with monkeypatch.context() as patch:
        patch.setattr(
            spine, "review_stored", lambda *args: spine.unreviewed(SKELETON, "sin Polaris")
        )
        failed = client.get("/api/volumes").json()[0]["segmentations"][0]["cadena_vertebral"]
    assert failed["revisada"] is False and "sin Polaris" in failed["aviso"]
    again = client.get("/api/volumes").json()[0]["segmentations"][0]["cadena_vertebral"]
    assert again["revisada"] is True and again["nivel"] is None


def test_a_changed_skeleton_file_does_not_take_the_list_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """El control no bloquea: con el binario cambiado en disco el listado sigue, el bloque dice
    que no se pudo hacer y por qué, y el visor sigue negándose a servirlo."""
    from app.api import volumes as volumes_api

    _skeleton_sample_stored_without_its_review(monkeypatch, tmp_path)
    monkeypatch.setattr(volumes_api, "_spine_reviews", {})
    index = client.post("/api/volumes/samples/esqueleto-4").json()["segmentation"]
    store = get_store()
    with Session(store.engine) as session:
        row = session.get(ImagingBlobRow, index)
        assert row is not None
        row.data = b"zip manipulado"
        session.commit()
    listed = client.get("/api/volumes")
    assert listed.status_code == 200, listed.text
    review = listed.json()[0]["segmentations"][0]["cadena_vertebral"]
    assert review["revisada"] is False and review["nivel"] == "dato_ausente"
    assert "no coincide con el hash firmado" in review["aviso"]
    assert volumes_api._spine_reviews == {}, "un control no hecho no se guarda"
    assert client.get(
        f"/api/volumes/segmentations/{index}/files/vertebrae_L1.ply"
    ).status_code == 409


def _ct_of_extent(tmp_path: Path, extent_mm: float) -> Path:
    """Un TAC diminuto en datos pero con la extensión de uno real (vóxeles enormes)."""
    path = tmp_path / f"ct-{extent_mm:.0f}.nii.gz"
    side = extent_mm / 10
    nib.save(nib.Nifti1Image(np.zeros((10, 10, 10), np.int16), np.diag([side, side, side, 1])),
             path)
    return path


def test_the_memory_follows_the_size_of_the_ct(tmp_path: Path) -> None:
    """Un fijo (modelo, PyTorch, CUDA) más una parte que crece con el volumen, con su margen."""
    preset = assets.PRESETS["esqueleto"]
    small = segment.required_ram_gb(_ct_of_extent(tmp_path, 300), preset)
    large = segment.required_ram_gb(_ct_of_extent(tmp_path, 600), preset)
    assert small is not None and large is not None
    assert small == pytest.approx((6.0 + 0.16 * (300 / 1.5) ** 3 / 1e6) * 1.25)
    assert large == pytest.approx((6.0 + 0.16 * (600 / 1.5) ** 3 / 1e6) * 1.25)
    assert segment.required_ram_gb(_ct_of_extent(tmp_path, 300), assets.PRESETS["higado"]) is None


# Picos medidos con GPU (M vóxeles a 1,5 mm, GB) de la tarea `total` entera, el 2026-10-06: las
# muestras de la app, s0013 y s1152 (politrauma de 82 cm, reparto `test`, 60 de 60 huesos). La
# guarda usa la estimación como techo: por debajo de un pico, mata la segmentación.
MEASURED_PEAKS = [
    (0.24, 6.27), (1.72, 6.33), (2.76, 6.41), (12.17, 7.27), (25.5, 7.4), (60.8, 15.45),
]


@pytest.mark.parametrize(("mvoxels", "peak_gb"), MEASURED_PEAKS)
def test_the_memory_estimate_covers_every_measured_peak(
    tmp_path: Path, mvoxels: float, peak_gb: float
) -> None:
    """El primer modelo (proporcional) daba 1,3 GB a un TAC de 1,72 M y la guarda lo mataba."""
    side = (mvoxels * 1e6) ** (1 / 3) * 1.5
    needed = segment.required_ram_gb(_ct_of_extent(tmp_path, side), assets.PRESETS["esqueleto"])
    assert needed is not None and needed >= peak_gb


def test_the_skeleton_is_not_launched_without_its_memory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Polaris lo vio morir a medias por memoria (20 GB en una máquina de 16): no se lanza."""
    monkeypatch.setattr(segment, "telemetry_off", lambda exe: True)
    big = _ct_of_extent(tmp_path, 600)  # 64 M vóxeles: ~20 GB
    monkeypatch.setattr(segment, "free_ram_gb", lambda: 12.0)

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no se debía lanzar TotalSegmentator")

    monkeypatch.setattr(segment.subprocess, "run", never)
    with pytest.raises(segment.SegmenterUnavailable, match="necesita unos 20"):
        segment.run("x", big, tmp_path / "out", assets.PRESETS["esqueleto"])
    monkeypatch.setattr(segment, "free_ram_gb", lambda: None)  # sin dato, tampoco
    with pytest.raises(segment.SegmenterUnavailable, match="desconocida"):
        segment.run("x", big, tmp_path / "out", assets.PRESETS["esqueleto"])


def test_a_ct_that_fits_is_launched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """El caso real medido: con 17 GB libres, un TAC de 45 cm (~9 GB) se lanza."""
    monkeypatch.setattr(segment, "telemetry_off", lambda exe: True)
    monkeypatch.setattr(segment, "free_ram_gb", lambda: 17.0)
    launched: list[tuple[list[str], float]] = []

    def fake(command: list[str], ceiling_gb: float, **kwargs: Any) -> Any:
        launched.append((command, ceiling_gb))
        return memguard.Outcome(0, 3.0)

    monkeypatch.setattr(segment.memguard, "run", fake)
    ct = _ct_of_extent(tmp_path, 300)
    segment.run("x", ct, tmp_path / "out", assets.PRESETS["esqueleto"])
    [(command, ceiling)] = launched
    # La tarea entera: con `--roi_subset` TotalSegmentator recorta con su modelo de 6 mm y en el
    # ejemplo de cuerpo entero perdía 20 de 60 huesos.
    assert command[command.index("-ta") + 1] == "total" and "--roi_subset" not in command
    # Con el techo de la memoria estimada para este TAC (guarda de Polaris).
    assert ceiling == pytest.approx(segment.required_ram_gb(ct, assets.PRESETS["esqueleto"]))


def test_a_skeleton_cut_for_memory_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(segment, "telemetry_off", lambda exe: True)
    monkeypatch.setattr(segment, "free_ram_gb", lambda: 17.0)
    monkeypatch.setattr(segment.memguard, "run",
                        lambda command, ceiling_gb, **kw: memguard.Outcome(99, 12.0))
    with pytest.raises(segment.SegmenterUnavailable, match="se cortó"):
        segment.run("x", _ct_of_extent(tmp_path, 300), tmp_path / "out",
                    assets.PRESETS["esqueleto"])
    monkeypatch.setattr(segment.memguard, "run",
                        lambda command, ceiling_gb, **kw: memguard.Outcome(98, 1.0))
    with pytest.raises(segment.SegmenterUnavailable, match="colgado"):
        segment.run("x", _ct_of_extent(tmp_path, 300), tmp_path / "out",
                    assets.PRESETS["esqueleto"])


def test_free_memory_is_read_from_the_system() -> None:
    free = segment.free_ram_gb()
    assert free is None or free > 0


def test_totalsegmentator_can_be_called_through_a_python_copy() -> None:
    """El paquete de modelos no lleva el lanzador del venv (con la ruta de otra máquina escrita)."""
    assert segment.command_prefix(r"C:\m\seg\python.exe") == [
        r"C:\m\seg\python.exe", "-m", "totalsegmentator.bin.TotalSegmentator"
    ]
    assert segment.command_prefix(r"C:\v\Scripts\TotalSegmentator.exe") == [
        r"C:\v\Scripts\TotalSegmentator.exe"
    ]
