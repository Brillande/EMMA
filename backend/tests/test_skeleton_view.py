# SPDX-License-Identifier: AGPL-3.0-or-later
"""La vista anterior del esqueleto del propio TAC (`volumes/skeleton_view.py`). Sin red.

Lo que no se ve mirando la figura es justo lo que aquí se comprueba: un esqueleto es casi
simétrico, y uno en espejo o con otro cuerpo por debajo se dibuja igual de bien. El maniquí es un
cuerpo de cajas con cada hueso donde lo pone el mapa de dolor (`data/anatomy/pain_points.json`),
para que la misma figura sirva a `test_pain_on_skeleton.py`.

Usa la copia literal de Polaris (`polaris/ADOPTADO.txt`) a través de `app.volumes.skeleton_view`.
"""

from __future__ import annotations

import io
from typing import Any

import nibabel as nib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from nibabel import orientations
from PIL import Image
from sqlalchemy.orm import Session

from app.api import volumes as volumes_api
from app.api.routes import get_store
from app.core.ledger import sha256_hex
from app.core.storage import ImagingBlobRow
from app.volumes import assets, skeleton_view, spine
from app.volumes.samples import load_sample
from tests.test_volumes import upload

PRESET = assets.PRESETS["esqueleto"]
LABEL = {structure.mask: structure.label for structure in PRESET.structures}
VOXEL = 5.0  # mm
GRID_X, GRID_Y = (-300.0, 120), (-100.0, 40)  # origen (mm) y vóxeles
FEET_MM, HEAD_MM = 400.0, 1600.0  # la z del mundo es la altura sobre los pies


def _levels() -> dict[str, float]:
    """Altura (mm) de cada nivel: C4, T5, L3 y el sacro, donde el mapa de dolor los ancla."""
    levels = {f"vertebrae_C{n}": 1550.0 - 20 * n for n in range(1, 8)}
    levels |= {f"vertebrae_T{n}": 1400.0 - 24 * n for n in range(1, 13)}
    levels |= {f"vertebrae_L{n}": 1120.0 - 20 * n for n in range(1, 6)}
    return {**levels, "sacrum": 900.0}


def _boxes() -> dict[str, tuple[float, float, float, float]]:
    """{hueso: (x, y, z bajo, z alto)} en mm del mundo RAS: la izquierda del sujeto es x < 0."""
    boxes = {name: (0.0, -40.0, z - 5, z + 5) for name, z in _levels().items()}
    boxes["sternum"] = (0.0, 60.0, 1275.0, 1285.0)
    for side, sign in (("left", -1.0), ("right", 1.0)):
        for n in range(1, 13):
            z = 1400.0 - 24 * n
            boxes[f"rib_{side}_{n}"] = (sign * 100, 0.0, z - 5, z + 5)
        boxes[f"clavicula_{side}"] = (sign * 80, 40.0, 1415.0, 1425.0)
        boxes[f"scapula_{side}"] = (sign * 150, -60.0, 1325.0, 1335.0)
        boxes[f"humerus_{side}"] = (sign * 250, 0.0, 1090.0, 1310.0)
        boxes[f"hip_{side}"] = (sign * 125, 0.0, 895.0, 905.0)
        boxes[f"femur_{side}"] = (sign * 110, 0.0, 450.0, 870.0)
    return boxes


def phantom(
    missing: tuple[str, ...] = (), floor_mm: float = FEET_MM
) -> tuple[Any, Any]:
    """El mapa de etiquetas del maniquí en rejilla RAS de 5 mm, y su afín. `floor_mm` corta el
    estudio por abajo, como un TAC que no llega a los pies."""
    affine = np.diag([VOXEL, VOXEL, VOXEL, 1.0])
    affine[:3, 3] = (GRID_X[0], GRID_Y[0], floor_mm)
    labels = np.zeros((GRID_X[1], GRID_Y[1], int((HEAD_MM - floor_mm) / VOXEL)), np.uint8)
    for name, (x, y, low, high) in _boxes().items():
        if name in missing or high <= floor_mm:
            continue
        i, j = int((x - GRID_X[0]) / VOXEL), int((y - GRID_Y[0]) / VOXEL)
        k0 = max(0, int((low - floor_mm) / VOXEL))
        k1 = int((high - floor_mm) / VOXEL)
        labels[i - 1:i + 2, j - 1:j + 2, k0:k1 + 1] = LABEL[name]
    return labels, affine


def archive_of(labels: Any, affine: Any) -> bytes:
    return assets.zip_files(
        {"etiquetas.nii.gz": assets.nifti_bytes(labels, affine, np.uint8)}, b"{}"
    )


def regridded(labels: Any, affine: Any, codes: tuple[str, str, str]) -> tuple[Any, Any]:
    """El MISMO cuerpo guardado en otra rejilla (ejes volteados o permutados), con su afín."""
    transform = orientations.ornt_transform(
        orientations.io_orientation(affine), orientations.axcodes2ornt(codes)
    )
    moved = orientations.apply_orientation(labels, transform)
    return np.ascontiguousarray(moved), affine @ orientations.inv_ornt_aff(transform, labels.shape)


def cut_study(
    labels: Any, affine: Any, axis: int, start: int = 0, stop: int | None = None
) -> tuple[Any, Any]:
    """El mismo cuerpo en un estudio que solo cubre los índices `start:stop` de un eje: un TAC con
    el campo más estrecho por un lado, por delante o por detrás."""
    index = [slice(None)] * 3
    index[axis] = slice(start, stop)
    moved = np.array(affine, dtype=np.float64)
    moved[:3, 3] = (moved @ np.array([start if n == axis else 0 for n in range(3)] + [1.0]))[:3]
    return np.ascontiguousarray(labels[tuple(index)]), moved


def view(**kwargs: Any) -> skeleton_view.View:
    labels, affine = phantom(**kwargs)
    field = spine.field_mm(labels.shape, affine)
    return skeleton_view.build(archive_of(labels, affine), PRESET, field)


def pixel(found: skeleton_view.View, bone: str) -> tuple[int, ...]:
    """El píxel RGBA de la imagen en el centroide de un hueso."""
    image = Image.open(io.BytesIO(found.png)).convert("RGBA")
    assert image.size == (found.width, found.height)
    point = found.bones[bone]
    value: tuple[int, ...] = image.getpixel(
        (round(point["u"] * (found.width - 1)), round(point["v"] * (found.height - 1)))
    )
    return value


def record_skeleton(
    client: TestClient, labels: Any, affine: Any, **signed: Any
) -> tuple[int, int]:
    """Un estudio y su segmentación del esqueleto en el ledger, como los deja la ruta de
    volúmenes, sin pasar por el remuestreo a 2 mm (el maniquí entero tardaría medio minuto).
    `signed` son campos de más en el resumen firmado."""
    study_index = upload(client, nib.Nifti1Image(np.zeros(labels.shape, np.int16), affine))
    store = get_store()
    study, _ = store.volume_blob(study_index)
    archive = archive_of(labels, affine)
    payload = {
        "preset": "esqueleto", "estado": assets.UNVALIDATED, "study_index": study_index,
        "study_sha256": study["sha256"], "sha256": sha256_hex(archive),
        "size_bytes": len(archive), "files": ["etiquetas.nii.gz"], **signed,
    }
    entry = store.record_volume_segmentation(
        payload, archive, volumes_api.identity_for(volumes_api.SEGMENTER_SIGNER)
    )
    return study_index, entry.index


@pytest.fixture(autouse=True)
def no_kept_views(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(skeleton_view, "_views", {})


# --------------------------------------------------------------------------- #
# La figura
# --------------------------------------------------------------------------- #


def test_the_view_is_anterior_upright_and_each_bone_is_where_it_is_drawn() -> None:
    found = view()
    assert set(found.bones) == set(assets.BONES) and found.absent == ()
    assert all(0 <= p["u"] <= 1 and 0 <= p["v"] <= 1 for p in found.bones.values())
    # Vista anterior: la izquierda del sujeto a la derecha de la imagen, en todos los pares.
    for name in assets.BONES:
        if "left" in name:
            assert found.bones[name]["u"] > 0.5 > found.bones[name.replace("left", "right")]["u"]
    # De pie: de C1 al sacro bajando, y el fémur por debajo.
    column = [found.bones[name]["v"] for name in skeleton_view.spine_chain()]
    assert column == sorted(column) and found.bones["femur_left"]["v"] > column[-1]
    # Solo la caja del hueso, en proporción física: 103 × 218 vóxeles (de húmero a húmero, del
    # pie del fémur a C1).
    assert found.width == skeleton_view.WIDTH
    assert found.height == round(found.width * 218 / 103)
    # El punto cae sobre hueso dibujado, y entre dos huesos no hay nada.
    for bone in ("sternum", "femur_left", "humerus_right", "vertebrae_L3", "rib_left_7"):
        assert pixel(found, bone)[3] > 200, bone  # el borde se suaviza al ampliar
    image = Image.open(io.BytesIO(found.png)).convert("RGBA")
    between = (found.bones["femur_left"]["u"] + found.bones["femur_right"]["u"]) / 2
    assert image.getpixel(
        (round(between * found.width), round(found.bones["femur_left"]["v"] * found.height))
    )[3] < 30


def test_polaris_gets_the_grid_its_projection_draws_from_the_front(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`proyecta_anterior` se queda con el hueso de ÍNDICE mayor en el segundo eje y pinta el
    tercero hacia abajo: para que eso sea «el más anterior» y «de pie», la rejilla que recibe
    crece hacia la derecha, hacia delante y hacia los pies, la guardara como la guardara el
    estudio. Desde atrás la silueta es la misma: mirando la imagen no se distingue."""
    from app import polaris

    visor3d = polaris.load("visor3d")
    original, seen = visor3d.proyecta_anterior, []

    def spy(mask: Any, affine: Any, ancho: int = 880) -> Any:
        seen.append((mask.shape, np.asarray(affine).copy()))
        return original(mask, affine, ancho)

    monkeypatch.setattr(visor3d, "proyecta_anterior", spy)
    labels, affine = phantom()
    for codes in (("R", "A", "S"), ("L", "P", "S"), ("P", "S", "R")):
        skeleton_view.build(archive_of(*regridded(labels, affine, codes)), PRESET)
    assert len(seen) == 3
    for shape, given in seen:
        assert shape == (103, 27, 218), "solo la caja del hueso"
        step = np.diag(given)[:3]
        assert step[0] > 0 and step[1] > 0 and step[2] < 0
        assert np.count_nonzero(given[:3, :3]) == 3


@pytest.mark.parametrize("codes", [
    ("L", "A", "S"), ("R", "P", "S"), ("R", "A", "I"), ("L", "P", "I"), ("A", "R", "S"),
    ("S", "L", "P"),
])
def test_a_flipped_or_permuted_grid_gives_the_same_figure(codes: tuple[str, str, str]) -> None:
    """El afín manda, no los índices: el mismo cuerpo guardado con un eje volteado (o los ejes en
    otro orden) da la misma imagen y los mismos puntos, ni en espejo ni del revés."""
    labels, affine = phantom()
    field = spine.field_mm(labels.shape, affine)
    straight = skeleton_view.build(archive_of(labels, affine), PRESET, field)
    moved = skeleton_view.build(archive_of(*regridded(labels, affine, codes)), PRESET, field)
    assert moved.bones == straight.bones
    assert moved.extent_mm == straight.extent_mm and moved.truncated == straight.truncated
    assert np.array_equal(
        np.asarray(Image.open(io.BytesIO(moved.png))),
        np.asarray(Image.open(io.BytesIO(straight.png))),
    )


def test_a_mirrored_body_is_refused_instead_of_drawn() -> None:
    """Un volteo que el afín NO cuenta: los huesos «izquierdos» quedan a la derecha del mundo."""
    labels, affine = phantom()
    with pytest.raises(skeleton_view.Unavailable, match="en espejo"):
        skeleton_view.build(archive_of(labels[::-1], affine), PRESET)


def test_an_upside_down_body_is_refused_instead_of_drawn() -> None:
    labels, affine = phantom()
    with pytest.raises(skeleton_view.Unavailable, match="del revés"):
        skeleton_view.build(archive_of(labels[:, :, ::-1], affine), PRESET)


def test_the_projection_is_checked_against_what_polaris_says_of_its_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si la copia cambiara de sentido su vista, no se enseña: lo dice su propia extensión."""
    from app import polaris

    visor3d = polaris.load("visor3d")
    original = visor3d.proyecta_anterior

    def mirrored(mask: Any, affine: Any, ancho: int = 880) -> Any:
        rgba, extent = original(mask, affine, ancho)
        return rgba[:, ::-1], {"x": extent["x"][::-1], "z": extent["z"]}

    monkeypatch.setattr(visor3d, "proyecta_anterior", mirrored)
    with pytest.raises(skeleton_view.Unavailable, match="de frente y de pie"):
        view()


def test_absent_bones_are_listed_and_not_drawn() -> None:
    whole = view()
    found = view(missing=("humerus_right", "rib_left_5", "vertebrae_T7"))
    assert set(found.absent) == {"humerus_right", "rib_left_5", "vertebrae_T7"}
    assert not set(found.absent) & set(found.bones), "sin vóxeles no hay centroide inventado"
    assert found.spine["huesos_sin_voxeles"] == list(found.absent)
    assert found.spine["huecos"] == ["vertebrae_T7"] and found.spine["nivel"] == "atencion"
    # Donde estaría la costilla no hay nada pintado. (El húmero derecho era el borde de la
    # figura: sin él la caja se estrecha, así que se mira un hueso que no la mueve.)
    lone = view(missing=("rib_left_5",))
    assert lone.bones["rib_left_4"] == whole.bones["rib_left_4"]
    image = Image.open(io.BytesIO(lone.png)).convert("RGBA")
    spot = whole.bones["rib_left_5"]
    assert image.getpixel(
        (round(spot["u"] * (lone.width - 1)), round(spot["v"] * (lone.height - 1)))
    )[3] < 30
    assert pixel(whole, "rib_left_5")[3] > 200


def test_a_bone_cut_by_the_edge_of_the_study_is_declared() -> None:
    """Un TAC que acaba a media pierna: el fémur que entra es un trozo, y su punto, el del trozo."""
    whole, cut = view(), view(floor_mm=700.0)
    assert whole.truncated == () and whole.truncation_checked is True
    assert cut.truncated == ("femur_left", "femur_right") and cut.absent == ()
    labels, affine = phantom(floor_mm=700.0)
    unmeasured = skeleton_view.build(archive_of(labels, affine), PRESET)
    assert unmeasured.truncated == () and unmeasured.truncation_checked is False


@pytest.mark.parametrize(("axis", "start", "stop", "cut"), [
    # El campo acaba a la derecha del sujeto en el húmero (x = 250 mm, índices 109-111)…
    (0, 0, 111, ("humerus_right",)),
    # … o empieza a su izquierda en el otro (x = −250 mm, índices 9-11).
    (0, 10, None, ("humerus_left",)),
    # Por delante, en el esternón (y = 60 mm, índices 31-33); las clavículas quedan a 15 mm.
    (1, 0, 33, ("sternum",)),
    # Por detrás, en las escápulas (y = −60 mm, índices 7-9); las vértebras quedan a 15 mm.
    (1, 8, None, ("scapula_left", "scapula_right")),
])
def test_a_bone_cut_by_a_side_the_front_or_the_back_of_the_study_is_declared(
    axis: int, start: int, stop: int | None, cut: tuple[str, ...],
) -> None:
    """No solo de arriba abajo: un húmero que el campo corta por el lado tiene el centroide de su
    trozo igual que un fémur cortado por abajo. Los demás huesos, a más de dos vóxeles, no."""
    labels, affine = cut_study(*phantom(), axis, start, stop)
    found = skeleton_view.build(
        archive_of(labels, affine), PRESET, spine.field_mm(labels.shape, affine)
    )
    assert found.truncated == cut and found.absent == ()
    # Sin el campo del estudio no se mide, y se dice.
    unmeasured = skeleton_view.build(archive_of(labels, affine), PRESET)
    assert unmeasured.truncated == () and unmeasured.truncation_checked is False


def test_a_grid_twisted_within_tolerance_still_finds_the_bone_cut_by_the_side() -> None:
    """Una rejilla torcida por debajo de `OBLIQUE_TOLERANCE` se proyecta, y a lo largo de un
    cuerpo entero ese giro son milímetros: el húmero cortado por el lado queda 11 mm «dentro» del
    campo si sus extremos se leen solo con la diagonal del afín (el mapa se recorta a la caja del
    hueso, cuyo origen está a la altura de C1). Con el afín entero, a 7 mm: cortado."""
    labels, affine = cut_study(*phantom(), 0, 0, 111)
    affine[0, 2] = -0.98 * skeleton_view.OBLIQUE_TOLERANCE * VOXEL  # x retrocede al subir
    found = skeleton_view.build(
        archive_of(labels, affine), PRESET, spine.field_mm(labels.shape, affine)
    )
    assert found.truncated == ("humerus_right",)


def test_the_field_of_a_study_is_measured_on_the_three_axes() -> None:
    """Entre los vóxeles extremos, en mm del mundo, guarde la rejilla sus ejes como los guarde."""
    def flat(field: spine.Field) -> list[float]:
        return [end for span in field for end in span]

    labels, affine = phantom()
    expected = ((-300.0, 295.0), (-100.0, 95.0), (400.0, 1595.0))
    assert spine.field_mm(labels.shape, affine) == expected
    assert spine.field_z_mm(labels.shape, affine) == expected[2]
    for codes in (("L", "P", "I"), ("P", "S", "R")):
        moved, moved_affine = regridded(labels, affine, codes)
        assert flat(spine.field_mm(moved.shape, moved_affine)) == pytest.approx(flat(expected))
    volume = assets.nifti_bytes(np.zeros(labels.shape, np.uint8), affine, np.uint8)
    assert flat(spine.volume_field_mm(volume)) == pytest.approx(flat(expected))
    assert spine.volume_field_z_mm(volume) == pytest.approx(expected[2])


def test_what_cannot_be_projected_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    labels, affine = phantom()
    with pytest.raises(skeleton_view.Unavailable, match="no se puede leer"):
        skeleton_view.build(b"no es un zip", PRESET)
    with pytest.raises(skeleton_view.Unavailable, match="ningún hueso"):
        skeleton_view.build(archive_of(np.zeros_like(labels), affine), PRESET)
    tilted = affine.copy()
    tilted[0, 2] = 1.0  # un eje de la rejilla ya no es un eje del cuerpo
    with pytest.raises(skeleton_view.Unavailable, match="oblicua"):
        skeleton_view.build(archive_of(labels, tilted), PRESET)
    monkeypatch.setattr(skeleton_view, "MAX_VOXELS", labels.size - 1)
    with pytest.raises(skeleton_view.Unavailable, match="vóxeles"):
        skeleton_view.build(archive_of(labels, affine), PRESET)


def test_the_real_whole_body_sample_stands_upright_with_its_cut_bones() -> None:
    """`esqueleto-4` (s1152, reparto `test`): los 60 huesos, y el estudio acaba en la pelvis."""
    _, volume, archive = load_sample("esqueleto-4")
    found = skeleton_view.build(archive, PRESET, spine.volume_field_mm(volume))
    assert len(found.bones) == 60 and found.absent == ()
    assert found.bones["femur_left"]["u"] > 0.5 > found.bones["femur_right"]["u"]
    assert found.bones["vertebrae_C1"]["v"] < 0.1 < 0.8 < found.bones["sacrum"]["v"]
    # Solo el borde de abajo corta. A los lados, delante y detrás su estudio es el TAC recortado a
    # la caja del hueso con 3 vóxeles de holgura (`assets.build`): el hueso más cercano (húmeros,
    # vértebras dorsales) queda a 6 mm, fuera de la tolerancia de 4 mm. Medido el 2026-10-21.
    assert set(found.truncated) == {"femur_left", "femur_right", "hip_left", "hip_right", "sacrum"}
    assert found.pairs_checked == 17 and found.spine["nivel"] is None
    assert pixel(found, "sternum")[3] > 200


# --------------------------------------------------------------------------- #
# Del ledger a la respuesta
# --------------------------------------------------------------------------- #

PNG = b"\x89PNG\r\n\x1a\n"


def test_without_a_skeleton_segmentation_the_reference_is_shown_and_said(
    client: TestClient,
) -> None:
    plain = client.get("/api/anatomy/skeleton").json()
    assert plain["source"] == "reference" and plain["fallback_reason"] is None
    assert "no es el cuerpo del tripulante" in plain["label"] and plain["ledger"] is None
    assert plain["bones"]["vertebrae_T5"]["display"] == "Vértebra T5"
    client.post("/api/volumes/samples/higado-1")  # un TAC que no es del esqueleto no cuenta
    body = client.get("/api/anatomy/skeleton/own").json()
    assert body["source"] == "reference" and body["bones"] == plain["bones"]
    assert "no tiene una segmentación del esqueleto vigente" in body["fallback_reason"]
    assert body["fallback_kind"] == "no-segmentation" and plain["fallback_kind"] is None
    pain = client.get("/api/anatomy/pain-on-skeleton").json()
    assert pain["source"] == "reference" and pain["segmentation_index"] is None


def test_the_own_ct_is_shown_with_its_ledger_entry_and_its_gaps(client: TestClient) -> None:
    labels, affine = phantom(missing=("rib_right_9",), floor_mm=700.0)
    study, index = record_skeleton(client, labels, affine)
    entries = len(get_store().ledger)
    body = client.get("/api/anatomy/skeleton/own").json()
    assert body["source"] == "own-ct" and body["simulated"] is False
    assert body["ledger"]["segmentation_index"] == index and body["ledger"]["study_index"] == study
    day = body["ledger"]["study_recorded"][:10]
    assert f"estudio registrado el {day} (asiento {study} del ledger)" in body["label"]
    assert f"(asiento {index})" in body["label"]
    assert body["caption"].startswith("Segmentación automática sin validar.")
    assert "no es un diagnóstico a bordo" in body["caption"]
    assert body["absent_bones"] == [{"name": "rib_right_9", "display": "Costilla derecha 9"}]
    assert [item["name"] for item in body["truncated_bones"]] == ["femur_left", "femur_right"]
    assert body["bones"]["femur_left"]["truncated"] is True
    assert body["bones"]["hip_left"] == {
        **body["bones"]["hip_left"], "truncated": False, "display": "Coxal izquierdo",
    }
    assert len(body["notes"]) == 2 and "rib_right_9" not in body["bones"]
    assert body["spine"]["listas"][0]["elementos"] == ["Costilla derecha 9"]

    image = client.get(f"/api/anatomy/skeleton/own/{index}.png")
    assert image.status_code == 200 and image.content.startswith(PNG)
    assert image.headers["cache-control"] == "no-store"
    assert Image.open(io.BytesIO(image.content)).size == (body["width"], body["height"])
    assert len(get_store().ledger) == entries, "se calcula al servir: nada se escribe"


def test_a_sample_ct_is_labelled_as_a_dataset_patient(client: TestClient) -> None:
    index = client.post("/api/volumes/samples/esqueleto-4").json()["segmentation"]
    body = client.get("/api/anatomy/skeleton/own").json()
    assert body["source"] == "own-ct" and body["simulated"] is True
    assert "dato simulado, no el cuerpo del tripulante" in body["label"]
    assert "CC BY 4.0" in body["attribution"] and "Wasserthal" in body["attribution"]
    assert body["ledger"]["segmentation_index"] == index
    # El último esqueleto registrado es el que se enseña.
    later = client.post("/api/volumes/samples/esqueleto-4").json()["segmentation"]
    assert client.get("/api/anatomy/skeleton/own").json()["ledger"]["segmentation_index"] == later
    assert client.get("/api/anatomy/skeleton/own", params={"subject": "crew-02"}).json()[
        "source"
    ] == "reference"


def test_the_image_route_only_serves_skeleton_segmentations(client: TestClient) -> None:
    liver = client.post("/api/volumes/samples/higado-1").json()
    assert client.get("/api/anatomy/skeleton/own/999.png").status_code == 404
    assert client.get(f"/api/anatomy/skeleton/own/{liver['ledger_index']}.png").status_code == 404
    refused = client.get(f"/api/anatomy/skeleton/own/{liver['segmentation']}.png")
    assert refused.status_code == 404 and "esqueleto" in refused.json()["detail"]


def test_a_changed_file_falls_back_to_the_reference_even_after_being_shown(
    client: TestClient,
) -> None:
    """La figura ya calculada no se sirve de un zip que ha dejado de ser el firmado."""
    labels, affine = phantom()
    _, index = record_skeleton(client, labels, affine)
    assert client.get("/api/anatomy/skeleton/own").json()["source"] == "own-ct"
    store = get_store()
    with Session(store.engine) as session:
        row = session.get(ImagingBlobRow, index)
        assert row is not None
        row.data = b"zip manipulado"
        session.commit()
    body = client.get("/api/anatomy/skeleton/own").json()
    assert body["source"] == "reference"
    assert f"(asiento {index} del ledger) no se usa" in body["fallback_reason"]
    assert "no coincide con el hash firmado" in body["fallback_reason"]
    assert body["fallback_kind"] == "not-usable"
    assert client.get(f"/api/anatomy/skeleton/own/{index}.png").status_code == 404
    assert client.get("/api/anatomy/pain-on-skeleton").json()["source"] == "reference"


def test_a_signed_spine_review_is_shown_as_signed_and_never_without_its_lists(
    client: TestClient,
) -> None:
    """El control firmado en el asiento es el que se enseña (no se recalcula otro), y uno firmado
    sin listas no llega a la interfaz con un nulo donde espera recorrer una lista."""
    labels, affine = phantom()
    notice = {"nivel": "atencion", "aviso": "Control firmado con el asiento."}
    record_skeleton(client, labels, affine, cadena_vertebral=notice)
    body = client.get("/api/anatomy/skeleton/own").json()
    assert body["source"] == "own-ct"
    assert body["spine"] == {**notice, "listas": []}


def test_a_body_that_cannot_be_oriented_falls_back_and_says_so(client: TestClient) -> None:
    labels, affine = phantom()
    _, index = record_skeleton(client, labels[::-1], affine)
    body = client.get("/api/anatomy/skeleton/own").json()
    assert body["source"] == "reference" and "en espejo" in body["fallback_reason"]
    assert f"asiento {index}" in body["fallback_reason"]
