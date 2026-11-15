# SPDX-License-Identifier: AGPL-3.0-or-later
"""La vista anterior del esqueleto, sacada del TAC que el tripulante tiene en su registro.

Por qué existe: el modo anatómico enseñaba siempre el esqueleto de REFERENCIA (BodyParts3D), un
cuerpo que no es el de nadie de la tripulación, aunque EMMA ya guarda en el ledger la segmentación
del preset `esqueleto` de quien la tiene (60 huesos, con su mapa de etiquetas firmado). El dolor
referido se colocaba sobre ese cuerpo ajeno. Aquí, de la segmentación vigente, sale la misma
figura con el mismo contrato (imagen RGBA de frente y centroide de cada hueso en fracción de la
imagen), para que la interfaz y `pain_on_skeleton` no distingan más que por lo que la respuesta
dice.

Es una imagen de referencia previa al vuelo o de Tierra (hoy no vuela ningún TAC), de una
segmentación automática sin validar: dice dónde está cada hueso segmentado, no qué le pasa. No
entra en el análisis ni en una alerta, y no escribe nada en el ledger: se calcula al servir, desde
el binario firmado (que `segmentation_blob` comprueba contra su huella en cada entrega).

Adaptador sobre Polaris copiado tal cual (`polaris/tools/visor3d.py`; el commit, en
`polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»; se
carga con `app.polaris.load`). Llama al original, sin tocarlo:
  * `proyecta_anterior(mask, afín)`: el vóxel de hueso más anterior de cada punto de la pantalla,
    sombreado por profundidad, y la extensión en milímetros de los bordes de la imagen.
  * `_uv(mm, extremos)`: de milímetros del mundo a fracción de la imagen.

Lo que pone EMMA alrededor (AGPL §5a; pendiente de decisión en `docs/polaris-divergencias.md`):
  * La orientación. `proyecta_anterior` dibuja con los ÍNDICES de la rejilla y su comentario dice
    que la máscara llega «en canónica RAS»; medido el 2026-10-07 con el ejemplo `esqueleto-4`, que
    EMMA guarda en RAS, la figura sale cabeza abajo (el freno de `_cmd_esqueleto` la habría
    abortado). Aquí el mapa se reorienta según su afín a derecha-anterior-INFERIOR antes de
    llamarla, que es la rejilla con la que su figura sale de pie, y después se comprueba en la
    extensión que devuelve: la derecha del sujeto a la izquierda de la imagen y la cabeza arriba.
    Si no, no se enseña. Una rejilla oblicua tampoco: Polaris proyecta por índices.
  * El espejo. Polaris lo comprueba con el hígado y el bazo; el mapa que EMMA publica solo lleva
    hueso. Aquí se contrasta el nombre de cada par (izquierdo, derecho) con el afín, y la cadena
    vertebral con la z. No es una comprobación independiente: si el afín del NIfTI miente,
    TotalSegmentator hereda la mentira. Lo que caza es una reorientación mal hecha AQUÍ.
  * No se reconstruye. `visor3d.esqueleto` une fragmentos, simetriza costillas, puentea la columna
    y rellena huecos (`_reconstruye`: «deja de ser SOLO medida»). Nada de eso se llama: un hueso
    sin vóxeles no se dibuja, se lista como ausente (`spine.py`), y un TAC parcial es lo normal.
  * Huesos cortados. Un hueso que llega a un borde del estudio tiene el centroide de su trozo, no
    el suyo: se dice, y `pain_on_skeleton` no lo usa de ancla ni pone su zona sobre él. Se miran
    los seis bordes (arriba y abajo, los dos lados, delante y detrás; `spine.field_mm`), con la
    misma tolerancia en cada eje. Hasta el 2026-10-21 solo se miraba el craneocaudal, y un húmero
    cortado por el lado del campo habría anclado el dolor con el centroide de su trozo. En
    `esqueleto-4` no cambia nada: su estudio es el TAC recortado a la caja del hueso con 3 vóxeles
    de holgura (`assets.build`), y a los lados, delante y detrás el hueso más cercano queda a 6 mm
    del borde, fuera de la tolerancia (4 mm). Lo que corta un campo de reconstrucción circular, o
    un estudio inclinado, sin llegar a la caja de las esquinas de su rejilla no se ve
    (`spine.field_mm`).
  * Centroides por etiqueta con `numpy.bincount` sobre los vóxeles de hueso (Polaris usa
    `center_of_mass` sobre el volumen entero, que en `esqueleto-4` son 0,7 s solo para eso).
  * Tamaño y memoria: se trabaja sobre el mapa publicado (2 mm, ya recortado a la caja del hueso)
    y se niega por encima de `MAX_VOXELS`. Medido el 2026-10-07 en `esqueleto-4` (212×152×334):
    0,6 s la figura entera, PNG incluido, y 0,5 s más el control de la cadena si no viene
    firmado; 1,2 s la primera petición por la API y unos 10 ms las siguientes. Una figura por
    segmentación queda en memoria (`_views`, las `KEEP` últimas; cada PNG ronda 1 MB).
"""

from __future__ import annotations

import gzip
import io
import itertools
import logging
import threading
import time
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

from app import polaris
from app.volumes import assets, spine

if TYPE_CHECKING:
    from app.core.storage import ObservationStore

log = logging.getLogger(__name__)

PRESET = spine.PRESET
WIDTH = 880  # el ancho del esqueleto de referencia: mismo contrato para la interfaz
MAX_VOXELS = 64_000_000  # ~6× el ejemplo de cuerpo entero a 2 mm; por encima no se proyecta
# Polaris dibuja con los índices: con esta rejilla su vista sale de frente y de pie.
PROJECTION_AXES = ("R", "A", "I")
OBLIQUE_TOLERANCE = 0.01  # coseno fuera del eje a partir del cual la rejilla no es recta
# A cuántos vóxeles de un borde del estudio (en ese eje) se da un hueso por cortado: el del borde
# y uno más, que es lo que puede comerse el remuestreo a la rejilla de publicación.
EDGE_VOXELS = 2.0
KEEP = 4

UNREADABLE = "su mapa de etiquetas no se puede leer ({reason})"
TOO_BIG = "su mapa de etiquetas tiene {voxels} vóxeles y solo se proyecta hasta {limit}"
OBLIQUE = "su rejilla es oblicua y la proyección de Polaris trabaja por índices"
NO_BONE = "no tiene ningún hueso con vóxeles"
MIRRORED = (
    "los huesos que el segmentador nombra izquierdos quedan a la derecha según el afín: la vista "
    "saldría en espejo"
)
UPSIDE_DOWN = (
    "la columna queda con las cervicales por debajo del sacro según el afín: la vista saldría "
    "del revés"
)
NOT_ANTERIOR = "la proyección no sale de frente y de pie con esta rejilla"


class Unavailable(Exception):
    """No hay figura del propio TAC que enseñar. El texto es el motivo, ya redactado."""

    def __init__(self, reason: str, segmentation_index: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.segmentation_index = segmentation_index


@dataclass(frozen=True)
class View:
    """La figura de una segmentación: lo que sale solo de sus bytes firmados."""

    png: bytes
    width: int
    height: int
    bones: dict[str, dict[str, float]]  # {hueso: {u, v}}, como `esqueleto.json`
    absent: tuple[str, ...]  # huesos del preset sin vóxeles
    truncated: tuple[str, ...]  # huesos que llegan a algún borde del estudio, en cualquier eje
    truncation_checked: bool
    # Milímetros del mundo en los bordes de la imagen: x (izquierda, derecha), z (arriba, abajo).
    extent_mm: dict[str, list[float]]
    spine: dict[str, Any]  # el bloque `cadena_vertebral` (firmado o calculado al servir)
    pairs_checked: int
    build_ms: int


@dataclass(frozen=True)
class Found:
    view: View
    segmentation: dict[str, Any]  # el asiento de la segmentación, sin el binario
    study: dict[str, Any]  # el asiento de su estudio


def _reorient(
    labels: NDArray[Any], affine: NDArray[np.float64], codes: tuple[str, str, str]
) -> tuple[NDArray[Any], NDArray[np.float64]]:
    """El mismo volumen con los ejes de la rejilla en el sentido de `codes`, y su afín."""
    from nibabel import orientations

    transform = orientations.ornt_transform(
        orientations.io_orientation(affine),  # type: ignore[no-untyped-call]
        orientations.axcodes2ornt(codes),  # type: ignore[no-untyped-call]
    )
    moved = orientations.apply_orientation(labels, transform)  # type: ignore[no-untyped-call]
    shift = orientations.inv_ornt_aff(transform, labels.shape)  # type: ignore[no-untyped-call]
    return np.asarray(moved), np.asarray(affine @ shift, dtype=np.float64)


def _centroids(labels: NDArray[Any], affine: NDArray[np.float64]) -> dict[int, NDArray[np.float64]]:
    """Centroide de cada etiqueta en milímetros del mundo, mirando solo los vóxeles de hueso."""
    index = np.nonzero(labels)
    values = labels[index].astype(np.intp)
    count = np.bincount(values)
    sums = np.stack([np.bincount(values, weights=axis) for axis in index], axis=1)
    return {
        int(label): (affine @ np.append(sums[label] / count[label], 1.0))[:3]
        for label in np.flatnonzero(count)
    }


def _extent(box: tuple[slice, ...], affine: NDArray[np.float64]) -> NDArray[np.float64]:
    """(mínimo, máximo) en mm del mundo de cada eje, de las esquinas de una caja de índices.

    Con el afín entero: la rejilla puede torcerse hasta `OBLIQUE_TOLERANCE` por vóxel, y sin los
    términos fuera de la diagonal eso son milímetros a lo largo de un cuerpo entero.
    """
    corners = np.array(
        [[*point, 1.0] for point in itertools.product(*((s.start, s.stop - 1) for s in box))]
    )
    world = (affine @ corners.T)[:3]
    return np.stack([world.min(axis=1), world.max(axis=1)], axis=1)


def _side_pairs(names: dict[str, int]) -> list[tuple[int, int]]:
    """(etiqueta izquierda, etiqueta derecha) de cada hueso par del preset."""
    return [
        (label, names[name.replace("left", "right")])
        for name, label in names.items()
        if "left" in name and name.replace("left", "right") in names
    ]


def build(
    archive: bytes,
    preset: assets.Preset,
    field: spine.Field | None = None,
    signed_spine: dict[str, Any] | None = None,
) -> View:
    """La figura de un zip de segmentación del esqueleto. Lanza `Unavailable` con el motivo.

    `field` es lo que cubre el volumen del estudio en x, y y z (`spine.volume_field_mm`); sin él
    no se sabe qué huesos corta el borde y se dice (`truncation_checked`).
    """
    import nibabel as nib
    from PIL import Image
    from scipy import ndimage

    started = time.perf_counter()
    known = {structure.mask: structure.label for structure in preset.structures}
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            raw = bundle.read("etiquetas.nii.gz")
        # Primero la cabecera sola: el tamaño se decide antes de descomprimir el volumen.
        header: Any = nib.Nifti1Header.from_fileobj(  # type: ignore[no-untyped-call]
            gzip.GzipFile(fileobj=io.BytesIO(raw))
        )
        shape = tuple(int(n) for n in header.get_data_shape())
        if len(shape) != 3:
            raise ValueError(f"el mapa no es un volumen 3D: {shape}")
        voxels = int(np.prod(shape))
        if voxels > MAX_VOXELS:
            raise Unavailable(TOO_BIG.format(voxels=voxels, limit=MAX_VOXELS))
        image: Any = nib.Nifti1Image.from_bytes(gzip.decompress(raw))
        source_affine = np.asarray(image.affine, dtype=np.float64)
        labels = np.asarray(image.dataobj)
        labels = np.where(np.isin(labels, list(known.values())), labels, 0).astype(np.uint8)
        # Con un afín degenerado no hay orientación que resolver: también es «no se puede leer».
        upright = _reorient(labels, source_affine, ("R", "A", "S"))
        labels, affine = _reorient(labels, source_affine, PROJECTION_AXES)
    except Unavailable:
        raise
    except Exception as exc:  # noqa: BLE001 — un zip ilegible se dice; no tumba el modo anatómico
        raise Unavailable(UNREADABLE.format(reason=f"{type(exc).__name__}: {exc}")) from exc
    if not labels.any():
        raise Unavailable(NO_BONE)

    rotation = affine[:3, :3]
    spacing = np.abs(np.diag(rotation))
    off_axis = np.abs(rotation - np.diag(np.diag(rotation))).max()
    if spacing.min() <= 0 or off_axis > OBLIQUE_TOLERANCE * spacing.min():
        raise Unavailable(OBLIQUE)

    # Solo la caja del hueso: la proyección y los filtros de Polaris recorren lo que reciben.
    occupied = np.argwhere(labels > 0)
    low, high = occupied.min(axis=0), occupied.max(axis=0) + 1
    labels = labels[tuple(slice(int(a), int(b)) for a, b in zip(low, high, strict=True))]
    affine = affine.copy()
    affine[:3, 3] = (affine @ np.append(low, 1.0))[:3]

    centres = _centroids(labels, affine)
    present = {name: label for name, label in known.items() if label in centres}
    # Los nombres contra el afín (ver la cabecera: caza un volteo mal resuelto, no un afín falso).
    pairs = _side_pairs(present)
    wrong = sum(1 for left, right in pairs if centres[left][0] > centres[right][0])
    if wrong * 2 > len(pairs):
        raise Unavailable(MIRRORED)
    column = [name for name in spine_chain() if name in present]
    if len(column) > 1 and centres[present[column[0]]][2] < centres[present[column[-1]]][2]:
        raise Unavailable(UPSIDE_DOWN)

    visor3d: Any = polaris.load("visor3d")
    rgba, extent = visor3d.proyecta_anterior(labels > 0, affine)
    # Lo que dice la propia proyección de sus bordes: derecha del sujeto (x mayor en RAS) a la
    # izquierda de la imagen, y la cabeza (z mayor) arriba.
    if not (extent["x"][0] > extent["x"][1] and extent["z"][0] > extent["z"][1]):
        raise Unavailable(NOT_ANTERIOR)

    # El control de la cadena y los huesos ausentes, de `spine.py`: firmado si la segmentación lo
    # trae; si no, el mismo cálculo que hace el listado de volúmenes, sobre la rejilla canónica.
    # Después de las negativas: es medio segundo que no se gasta en una figura que no se enseña.
    block = (
        signed_spine if signed_spine is not None
        else spine.review(*upright, preset, None if field is None else field[2])
    )

    def at(point: NDArray[np.float64]) -> dict[str, float]:
        return {
            "u": round(float(visor3d._uv(point[0], extent["x"])), 5),
            "v": round(float(visor3d._uv(point[2], extent["z"])), 5),
        }

    bones = {name: at(centres[label]) for name, label in sorted(present.items())}

    truncated: list[str] = []
    if field is not None:
        # La rejilla es casi recta (arriba, `OBLIQUE`) y sus ejes son los del mundo en ese orden:
        # en cada eje, los extremos del hueso contra los del estudio, con la tolerancia del eje.
        boxes = ndimage.find_objects(labels)
        for name, label in present.items():
            reach = _extent(boxes[label - 1], affine)
            for axis, (first, last) in enumerate(field):
                lowest, highest = (float(end) for end in reach[axis])
                margin = EDGE_VOXELS * float(spacing[axis])
                if lowest - first <= margin or last - highest <= margin:
                    truncated.append(name)
                    break

    picture = Image.fromarray(rgba)  # (alto, ancho, 4) uint8: RGBA
    # Proporción física, no la de los índices: con un vóxel anisótropo la figura no se estira.
    height = max(1, round(WIDTH * (rgba.shape[0] * spacing[2]) / (rgba.shape[1] * spacing[0])))
    picture = picture.resize((WIDTH, height), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    picture.save(out, "PNG", optimize=True)
    return View(
        png=out.getvalue(),
        width=WIDTH,
        height=height,
        bones=bones,
        absent=tuple(name for name in known if name not in present),
        truncated=tuple(sorted(truncated)),
        truncation_checked=field is not None,
        extent_mm={axis: [round(float(v), 1) for v in extent[axis]] for axis in ("x", "z")},
        spine=block,
        pairs_checked=len(pairs),
        build_ms=round((time.perf_counter() - started) * 1000),
    )


def spine_chain() -> list[str]:
    """De C1 al sacro, con los nombres del preset (el `sacrum` hace de final, como en `spine`)."""
    return [name for name in assets.BONES if name.startswith("vertebrae_")] + [spine.CAUDAL_END]


# Una figura por segmentación, por la huella firmada de su zip y la de su estudio (el borde del
# estudio decide qué hueso está cortado). En memoria: un reinicio la pierde y se vuelve a calcular.
_views: dict[tuple[str, str], View] = {}
_views_lock = threading.Lock()


def view_of(store: ObservationStore, ledger_index: int) -> View:
    """La figura de una segmentación guardada. Lanza `Unavailable` con el motivo.

    El binario se pide al ledger en cada llamada, que lo comprueba contra su huella firmada: una
    figura ya calculada no se sirve de un zip que ha dejado de ser el firmado.
    """
    from app.core.storage import TamperedRecordError

    try:
        segmentation, archive = store.segmentation_blob(ledger_index)
    except (KeyError, TamperedRecordError) as exc:
        raise Unavailable(str(exc.args[0]), ledger_index) from exc
    if segmentation.get("preset") != PRESET:
        raise Unavailable(
            f"el asiento {ledger_index} no es una segmentación del esqueleto", ledger_index
        )
    key = (str(segmentation["sha256"]), str(segmentation["study_sha256"]))
    with _views_lock:
        view = _views.get(key)
    if view is not None:
        return view
    field: spine.Field | None = None
    try:
        # Solo la cabecera del volumen del estudio, y solo la primera vez (son decenas de MB).
        _, volume = store.volume_blob(int(segmentation["study_index"]))
        field = spine.volume_field_mm(volume)
    except Exception:  # noqa: BLE001 — sin el estudio no se miden los bordes; la figura sí sale
        log.exception("no se pudo leer el estudio de la segmentación %s", ledger_index)
    try:
        view = build(archive, assets.PRESETS[PRESET], field, segmentation.get(spine.KEY))
    except Unavailable as exc:
        raise Unavailable(exc.reason, ledger_index) from exc
    log.info("esqueleto del asiento %s proyectado en %s ms", ledger_index, view.build_ms)
    if view.truncation_checked:  # sin los bordes medidos se reintenta la próxima vez
        with _views_lock:
            _views[key] = view
            while len(_views) > KEEP:
                del _views[next(iter(_views))]
    return view


def current(store: ObservationStore, subject: str) -> Found | None:
    """La figura del propio TAC de un tripulante: la de su segmentación del esqueleto vigente más
    reciente (por asiento). None si no tiene ninguna; `Unavailable` si la tiene y no vale."""
    from app.core.storage import TamperedRecordError

    try:
        found = [
            (study, segmentation)
            for study in store.volume_studies(subject)
            for segmentation in store.volume_segmentations(int(study["ledger_index"]))
            if segmentation.get("preset") == PRESET
        ]
    except TamperedRecordError as exc:  # el modo anatómico no se cae por un asiento manipulado
        raise Unavailable(str(exc.args[0])) from exc
    if not found:
        return None
    study, segmentation = max(found, key=lambda pair: int(pair[1]["ledger_index"]))
    return Found(view_of(store, int(segmentation["ledger_index"])), segmentation, study)

