# SPDX-License-Identifier: AGPL-3.0-or-later
"""De un TAC y sus máscaras a lo que abre el visor: volumen recortado, etiquetas, mallas y resumen.

Por qué existe: un TAC entero pesa decenas de MB y la mayor parte no es el órgano que se mira. El
visor necesita el volumen recortado a la región, un mapa de etiquetas para colorear los cortes,
una malla por estructura para el 3D y un resumen con volúmenes y lesiones candidatas.

Código de Polaris (AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»), de dos
formas. LLAMA a `polaris/tools/visor3d.py` de la copia literal, sin modificarla (commit en
`polaris/ADOPTADO.txt`; se carga con `app.polaris.load`): `nifti_bytes` (`nifti_limpio`, comprimido
en memoria) y, a través de `geometry`, mallas, elipsoides y diámetros. Las constantes (`AIR_HU`,
`WINDOW_WIDTH`) son las de Polaris y una prueba lo comprueba.

ADAPTADO a mano de `tools/visor3d.py` @ 7bf47257 (github.com/BeyondTheProtocol/polaris, el commit
que se copió primero): `build()` sigue siendo la lógica de `assets()` escrita en EMMA, porque el
original no se puede llamar: segmenta, lee la serie DICOM y escribe en la zona clínica de su autora
por sí mismo.
Divergencias con `assets()` (AGPL §5a; pendientes de decisión en `docs/polaris-divergencias.md`):
  * Dirigido por datos: las estructuras de cada preset se declaran en `PRESETS` en vez de estar
    fijas en el hígado. El preset `higado` reproduce el de Polaris (más la vesícula como etiqueta
    5); `ojos` (globos, cristalinos y nervios ópticos, tarea `head_glands_cavities`) es de EMMA,
    por SANS, y Polaris no lo tiene.
  * Vóxel por preset (`Preset.voxel_mm`, la ruta `_hd` de Polaris) y medido del volumen recibido.
  * Parénquima para la ventana: el órgano sin lesiones (Polaris: el órgano sin ninguna otra
    etiqueta); sin parénquima, nivel 40 HU (Polaris: 60).
  * Recibe las máscaras y devuelve los ficheros en memoria; guardarlos y firmarlos es cosa del
    ledger. Sin colores (los pone la interfaz), sin `serie_uid` en la procedencia, sin PET, marcas
    del radiólogo ni segmentos del caso original.
"""

from __future__ import annotations

import gzip
import hashlib
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app import polaris
from app.core import i18n
from app.volumes import geometry

VOXEL_MM = 2.0
AIR_HU = -1024
WINDOW_WIDTH = 180  # HU; Polaris: nivel = mediana del órgano en cada estudio
UNVALIDATED = "segmentación automática sin validar"


@dataclass(frozen=True)
class Structure:
    key: str
    display: str
    label: int
    mask: str  # nombre de la máscara de TotalSegmentator
    smoothing_mm: float = 0.8
    within_organ: bool = False
    min_component_mm3: float = 0.0
    anisotropic: bool = False  # más suavizado cráneo-caudal: los cortes gruesos dejan escalones


@dataclass(frozen=True)
class Preset:
    key: str
    display: str
    # (tarea de TotalSegmentator, subconjunto de clases o None para todas)
    tasks: tuple[tuple[str, tuple[str, ...] | None], ...]
    organ: tuple[str, ...]  # máscaras que definen la región de interés
    margin_mm: float
    structures: tuple[Structure, ...]
    lesion_mask: str | None = None
    second_model_mask: str | None = None
    region_masks: tuple[str, ...] = field(default=())
    # Resolucion de publicacion. Polaris publicaba a 2 mm para la web y tenia una ruta `_hd` a
    # 1 mm para el render (visor3d.py, "2 mm para la web; 1 mm (sufijo _hd) para el render").
    # A 2 mm un ojo de 24 mm son 12 voxeles y el cristalino desaparecia: cada preset elige la suya.
    voxel_mm: float = VOXEL_MM
    # Memoria que pide segmentarlo: una parte fija (modelo, PyTorch, CUDA) más GB por millón de
    # vóxeles del TAC remuestreado a 1,5 mm (la resolución de trabajo de TotalSegmentator); sin
    # ella libre no se lanza (`segment.run`), y es el techo de la guarda de memoria.
    ram_gb_per_mvoxel: float | None = None
    ram_gb_fixed: float = 0.0


# Los 60 huesos del esqueleto de referencia (F8, `app/data/anatomy/esqueleto.json`), con los
# nombres de las clases de TotalSegmentator. Una estructura por hueso: el 3D distingue cada
# vértebra, que es lo que Polaris buscaba con su preset (`visor3d.PRESETS["esqueleto"]`).
_SIDE = {"left": "izquierdo", "right": "derecho"}
_BONE_NAMES = {
    "clavicula": "Clavícula", "femur": "Fémur", "hip": "Coxal", "humerus": "Húmero",
    "scapula": "Escápula", "sacrum": "Sacro", "sternum": "Esternón",
}
_FEMININE_BONES = frozenset({"clavicula", "scapula"})
BONES = (
    *[f"vertebrae_{level}" for level in (
        *(f"C{n}" for n in range(1, 8)), *(f"T{n}" for n in range(1, 13)),
        *(f"L{n}" for n in range(1, 6)),
    )],
    *[f"rib_{side}_{n}" for side in ("left", "right") for n in range(1, 13)],
    "sternum", "sacrum",
    *[f"{bone}_{side}" for bone in ("clavicula", "scapula", "humerus", "hip", "femur")
      for side in ("left", "right")],
)


def bone_display(mask: str) -> str:
    """"vertebrae_T5" → "Vértebra T5"; "rib_left_3" → "Costilla izquierda 3"."""
    if mask.startswith("vertebrae_"):
        return f"Vértebra {mask.removeprefix('vertebrae_')}"
    if mask.startswith("rib_"):
        _, side, number = mask.split("_")
        return f"Costilla {_SIDE[side][:-1]}a {number}"
    bone, _, side = mask.partition("_")
    name = _BONE_NAMES[bone]
    if not side:
        return name
    # «Clavícula» y «Escápula» son femeninos: «Clavícula izquierda», no «izquierdo».
    return f"{name} {_SIDE[side][:-1]}a" if bone in _FEMININE_BONES else f"{name} {_SIDE[side]}"


PRESETS: dict[str, Preset] = {
    "higado": Preset(
        key="higado",
        display="Hígado",
        tasks=(
            ("total", ("liver", "inferior_vena_cava", "portal_vein_and_splenic_vein",
                       "gallbladder")),
            ("liver_vessels", None),
            ("liver_segments", None),
            ("liver_lesions", None),
        ),
        organ=("liver",),
        margin_mm=15.0,
        structures=(
            Structure("higado", "Hígado", 1, "liver", 1.2, anisotropic=True),
            Structure("vasos", "Vasos hepáticos", 2, "liver_vessels", 0.6, within_organ=True,
                      min_component_mm3=300.0),
            Structure("porta", "Porta y esplénica", 3, "portal_vein_and_splenic_vein", 0.8),
            Structure("vci", "Vena cava inferior", 4, "inferior_vena_cava", 0.8),
            Structure("vesicula", "Vesícula", 5, "gallbladder", 1.0),
        ),
        lesion_mask="liver_lesions",
        second_model_mask="liver_tumor",
        region_masks=tuple(f"liver_segment_{n}" for n in range(1, 9)),
        voxel_mm=1.5,
    ),
    "ojos": Preset(
        key="ojos",
        display="Órbitas y nervios ópticos",
        tasks=(("head_glands_cavities", None),),
        organ=("eye_left", "eye_right", "optic_nerve_left", "optic_nerve_right"),
        margin_mm=20.0,
        structures=(
            Structure("ojo_der", "Globo ocular derecho", 1, "eye_right", 0.6),
            Structure("ojo_izq", "Globo ocular izquierdo", 2, "eye_left", 0.6),
            Structure("cristalino_der", "Cristalino derecho", 3, "eye_lens_right", 0.4),
            Structure("cristalino_izq", "Cristalino izquierdo", 4, "eye_lens_left", 0.4),
            Structure("nervio_der", "Nervio óptico derecho", 5, "optic_nerve_right", 0.4),
            Structure("nervio_izq", "Nervio óptico izquierdo", 6, "optic_nerve_left", 0.4),
        ),
        voxel_mm=1.0,
    ),
    # Polaris `visor3d.PRESETS["esqueleto"]`: TAC de cuerpo entero, la tarea `total` y sin margen.
    # La tarea corre ENTERA, como en Polaris, y de ella se pintan los 60 huesos. Hasta el
    # 2026-10-06 EMMA la limitaba con `--roi_subset`: TotalSegmentator recorta entonces con un
    # modelo rápido de 6 mm, y en el ejemplo `esqueleto-4` ese recorte perdía 20 de 60 huesos
    # (C1-C4 y todo de T11 abajo). Medido allí contra la segmentación del TAC original, Dice medio:
    # subconjunto 0,50 (40 huesos), `--roi_subset_robust` 0,74 (57), tarea entera 0,85 (60). El
    # subconjunto no ahorraba memoria (7,5 frente a 7,4 GB), solo tiempo (60 s frente a 250).
    #
    # Su segmentación pidió 20 GB en una máquina de 16 (Polaris, 20-sep-2026) y se cortó. La memoria
    # NO es proporcional al volumen: hay un fijo grande. Picos de la tarea entera, con GPU, por
    # millones de vóxeles a 1,5 mm (2026-10-06): ojos-3 0,24 → 6,3 GB; higado-1 1,72 → 6,3;
    # higado-2 2,76 → 6,4; s0013 12,2 → 7,3; esqueleto-4 25,5 → 7,4; s1152 (politrauma, 82 cm)
    # 60,8 → 15,5 GB, 60 de 60 huesos en 469 s. Recta que los cubre: 6,0 GB + 0,16 GB por millón
    # (15,7 para s1152; 19,7 con el margen). El primer modelo (0,6 GB por millón, solo con s0013)
    # ponía 1,3 GB de techo a higado-1 y la guarda mataba toda segmentación de un TAC pequeño.
    "esqueleto": Preset(
        key="esqueleto",
        display="Esqueleto (TAC de cuerpo entero)",
        tasks=(("total", None),),
        organ=BONES,
        margin_mm=0.0,
        structures=tuple(
            Structure(mask, bone_display(mask), label, mask, 0.8)
            for label, mask in enumerate(BONES, start=1)
        ),
        voxel_mm=2.0,
        ram_gb_per_mvoxel=0.16,
        ram_gb_fixed=6.0,
    ),
}


def _bone_english(mask: str) -> str:
    """"vertebrae_T5" → "T5 vertebra"; "rib_left_3" → "Left rib 3"."""
    if mask.startswith("vertebrae_"):
        return f"{mask.removeprefix('vertebrae_')} vertebra"
    if mask.startswith("rib_"):
        _, side, number = mask.split("_")
        return f"{side.capitalize()} rib {number}"
    bone, _, side = mask.partition("_")
    name = {"clavicula": "clavicle", "hip": "hip bone"}.get(bone, bone)
    return f"{side.capitalize()} {name}" if side else name.capitalize()


# El inglés de lo que la consola enseña de una segmentación (decisión del usuario, 2026-11-15: la
# interfaz en inglés no enseña el hígado en castellano). Lo firmado sigue en castellano; el inglés
# se pone al servir, con `i18n.loc` (`api/volumes.py: _localized`).
i18n.en_many({
    "Hígado": "Liver",
    "Vasos hepáticos": "Hepatic vessels",
    "Porta y esplénica": "Portal and splenic veins",
    "Vena cava inferior": "Inferior vena cava",
    "Vesícula": "Gallbladder",
    "Órbitas y nervios ópticos": "Orbits and optic nerves",
    "Globo ocular derecho": "Right eyeball",
    "Globo ocular izquierdo": "Left eyeball",
    "Cristalino derecho": "Right lens",
    "Cristalino izquierdo": "Left lens",
    "Nervio óptico derecho": "Right optic nerve",
    "Nervio óptico izquierdo": "Left optic nerve",
    "Esqueleto (TAC de cuerpo entero)": "Skeleton (whole-body CT)",
    UNVALIDATED: "automatic segmentation, not validated",
    **{bone_display(mask): _bone_english(mask) for mask in BONES},
})

MaskLoader = Callable[[str], NDArray[np.bool_] | None]


def parenchyma_labels(preset: Preset) -> tuple[int, ...]:
    """Las etiquetas del órgano y de lo que queda dentro de él: el parénquima con el que se
    centra la ventana, que es también la referencia de la densidad de las lesiones."""
    return tuple(
        s.label for s in preset.structures if s.mask in preset.organ or s.within_organ
    )


def _density_reference(preset: Preset) -> str:
    return f"{preset.display} sin lesiones candidatas"


# Densidad de las segmentaciones guardadas SIN ella, por la huella firmada de su zip: solo
# depende de esos bytes y de la lista de lesiones firmada con ellos. En memoria.
_densities: dict[str, dict[str, Any]] = {}


def with_density(
    segmentation: dict[str, Any], read_archive: Callable[[], bytes]
) -> dict[str, Any]:
    """Una segmentación con la densidad (HU) de sus lesiones candidatas (`geometry.with_density`).

    Las nuevas la llevan firmada en su resumen (`build`). Las guardadas antes —y los ejemplos
    precalculados, cuyo zip tiene huella fija— no: se calcula al servir, desde el zip firmado, y
    viaja solo en la respuesta, como el control de la cadena vertebral. No se reescribe nada en
    el ledger. `read_archive` solo se llama si hace falta; si falla, se dice y se sigue.
    """
    key = geometry.DENSITY_KEY
    preset = PRESETS.get(str(segmentation.get("preset")))
    if preset is None or key in segmentation or not segmentation.get("lesiones"):
        return segmentation
    # Sin huella no hay con qué recordar: dos segmentaciones distintas compartirían la entrada.
    signed = segmentation.get("sha256")
    digest = signed if isinstance(signed, str) and signed else None
    known = None if digest is None else _densities.get(digest)
    if known is not None:
        # Las cifras recordadas se ponen sobre las lesiones de ESTA segmentación, por su id.
        by_id = {int(item["id"]): item[key] for item in known["lesiones"]}
        ids = [int(item["id"]) for item in segmentation["lesiones"]]
        if sorted(ids) != sorted(by_id):
            known = None
        else:
            lesions = [{**item, key: by_id[int(item["id"])]} for item in segmentation["lesiones"]]
            return {**segmentation, "lesiones": lesions, key: known[key]}
    if known is None:
        try:
            archive = read_archive()
        except Exception as exc:  # noqa: BLE001 — un binario ilegible no impide listar
            reason = geometry.UNREADABLE.format(reason=str(exc.args[0] if exc.args else exc))
            return {**segmentation, key: geometry.no_density(reason)}
        measured = geometry.with_stored_density(
            segmentation, archive, parenchyma_labels(preset), _density_reference(preset)
        )
        known = {"lesiones": measured["lesiones"], key: measured[key]}
        if known[key]["disponible"] and digest is not None:
            _densities[digest] = known
    return {**segmentation, **known}


def nifti_bytes(data: NDArray[Any], affine: NDArray[np.float64], dtype: Any) -> bytes:
    """NIfTI comprimido sin nada que no sea imagen. Polaris `nifti_limpio`, en memoria."""
    image = polaris.load("visor3d").nifti_limpio(data, affine, dtype)
    return gzip.compress(bytes(image.to_bytes()), compresslevel=6, mtime=0)


def build(
    ct: Any, masks: MaskLoader, preset: Preset, modality: str = "CT"
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Ficheros del visor y resumen del estudio. `ct` es un Nifti1Image; `masks` da cada máscara
    ya remuestreada a la rejilla del TAC a 2 mm (o None si el segmentador no la produjo)."""
    from scipy import ndimage

    affine = np.asarray(ct.affine, dtype=np.float64)
    data = np.asarray(ct.dataobj)
    organ = np.zeros(data.shape, bool)
    for name in preset.organ:
        found = masks(name)
        if found is not None:
            organ |= found
    if not organ.any():
        raise ValueError(f"el segmentador no encontró {preset.display.lower()} en este volumen")

    labels = np.zeros(data.shape, np.uint8)
    volumes: dict[str, float] = {}
    voxel_ml = float(np.prod(geometry.spacing(affine))) / 1000.0
    kept: dict[str, NDArray[np.bool_]] = {}
    for structure in preset.structures:
        mask = masks(structure.mask)
        if mask is None or not mask.any():
            continue
        if structure.within_organ:
            mask = mask & organ
        labels[mask] = structure.label
        kept[structure.key] = mask
        volumes[structure.key] = round(float(mask.sum()) * voxel_ml, 1)

    lesions: list[dict[str, Any]] = []
    if preset.lesion_mask:
        lesion = masks(preset.lesion_mask)
        if lesion is not None and lesion.any():
            regions = np.zeros(data.shape, np.uint8)
            for number, name in enumerate(preset.region_masks, start=1):
                region = masks(name)
                if region is not None:
                    regions[region] = number
            second = masks(preset.second_model_mask) if preset.second_model_mask else None
            lesions, ids = geometry.lesions(
                organ, lesion, affine, regions if preset.region_masks else None, second
            )
            for item in lesions:
                labels[ids == item["id"]] = 10 + item["id"]

    # Región publicada: el órgano dilatado; fuera, aire. Recorte a su caja.
    # El vóxel real del volumen recibido, no el del preset: si alguien lo remuestrea a otro
    # tamaño, margen, suavizado y componentes mínimos se miden igual en milímetros.
    voxel_mm = float(np.mean(ct.header.get_zooms()[:3]))
    iterations = max(1, int(round(preset.margin_mm / voxel_mm)))
    region = ndimage.binary_dilation(organ, iterations=iterations)
    healthy = organ & ~(labels >= 10)
    level = int(round(float(np.median(data[healthy])))) if healthy.any() else 40
    window = [level - WINDOW_WIDTH // 2, level + WINDOW_WIDTH // 2]
    data = np.where(region, data, AIR_HU)
    labels[~region] = 0
    idx = np.argwhere(region)
    lo = np.maximum(idx.min(0) - 2, 0)
    hi = np.minimum(idx.max(0) + 3, region.shape)
    box = tuple(slice(int(a), int(b)) for a, b in zip(lo, hi, strict=True))
    cropped_affine = affine.copy()
    cropped_affine[:3, 3] = (affine @ np.append(lo, 1.0))[:3]

    # Los enteros que se publican: la densidad de las lesiones se mide sobre ellos, para que la
    # firmada aquí y la recalculada desde el zip sean la misma.
    published = data[box].astype(np.int16)
    files: dict[str, bytes] = {
        "ct.nii.gz": nifti_bytes(published, cropped_affine, np.int16),
        "etiquetas.nii.gz": nifti_bytes(labels[box], cropped_affine, np.uint8),
    }
    half_voxel = voxel_mm / 2.0
    structures_out = []
    for structure in preset.structures:
        if structure.key not in kept:
            continue
        sigma = structure.smoothing_mm / half_voxel
        smoothing: float | tuple[float, ...] = (
            (sigma, sigma, sigma * 1.6) if structure.anisotropic else sigma
        )
        surface = geometry.mesh(
            kept[structure.key][box], cropped_affine, smoothing,
            min_component=int(structure.min_component_mm3 / voxel_mm**3),
            taubin_iterations=30 if structure.anisotropic else 12,
        )
        mesh_name = None
        if surface is not None:
            mesh_name = f"{structure.key}.ply"
            files[mesh_name] = geometry.ply_bytes(*surface)
        structures_out.append({
            "key": structure.key, "nombre": structure.display, "etiqueta": structure.label,
            "malla": mesh_name, "volumen_ml": volumes[structure.key],
        })
    for item in lesions:
        mask = labels[box] == 10 + item["id"]
        if item["diametro_mm"] < 8:
            surface = geometry.ellipsoid(mask, cropped_affine, item["diametro_mm"])
        else:
            sigma_mm = min(1.2, max(0.3, item["diametro_mm"] / 10.0))
            # Como Polaris: a 1 mm o menos, las lesiones se sobremuestrean x2.
            surface = geometry.mesh(
                mask, cropped_affine, sigma_mm / voxel_mm,
                oversample=2 if voxel_mm <= 1.0 else 1,
            )
        if surface is not None:
            item["malla"] = f"lesion{item['id']:02d}.ply"
            files[item["malla"]] = geometry.ply_bytes(*surface)

    center = (affine @ np.append(np.argwhere(organ).mean(axis=0), 1.0))[:3]
    summary: dict[str, Any] = {
        "preset": preset.key,
        "preset_nombre": preset.display,
        "estado": UNVALIDATED,
        "modalidad": modality,
        "voxel_mm": voxel_mm,
        "ventana_hu": window,
        "estructuras": structures_out,
        "centro_organo_mm": [round(float(c), 1) for c in center],
        "volumen_organo_ml": round(float(organ.sum()) * voxel_ml, 1),
        "lesiones": lesions,
        "volumen_lesiones_ml": round(sum(item["volumen_ml"] for item in lesions), 2),
        "sha256": {name: hashlib.sha256(blob).hexdigest() for name, blob in sorted(files.items())},
    }
    summary = geometry.with_density(
        summary, published, labels[box], parenchyma_labels(preset), _density_reference(preset)
    )
    if preset.key == "esqueleto":
        # Qué falta de la columna y de los 60 huesos, dicho en el resumen (`spine.py` cuenta el
        # caso). Sobre el mapa de etiquetas que se publica: es lo mismo que se recalcula al
        # servir, desde el zip firmado, para las segmentaciones guardadas sin él.
        from app.volumes import spine  # solo este preset carga el control

        summary[spine.KEY] = spine.review(
            labels[box], cropped_affine, preset, spine.field_z_mm(data.shape, affine)
        )
    return files, summary


def resample(image: Any, voxel_mm: float = VOXEL_MM) -> Any:
    """El volumen a `voxel_mm` isótropos, interpolación lineal (Polaris, `resample_to_output`)."""
    from nibabel.processing import resample_to_output

    return resample_to_output(  # type: ignore[no-untyped-call]
        image, voxel_sizes=voxel_mm, order=1
    )


def mask_loader(reference: Any, paths: dict[str, Any]) -> MaskLoader:
    """Cargador de máscaras por nombre, remuestreadas a la rejilla de `reference` (vecino)."""
    import nibabel as nib
    from nibabel.processing import resample_from_to

    cache: dict[str, NDArray[np.bool_] | None] = {}

    def load(name: str) -> NDArray[np.bool_] | None:
        if name not in cache:
            source = paths.get(name)
            if source is None:
                cache[name] = None
            else:
                image = nib.load(source) if not hasattr(source, "affine") else source
                resampled = resample_from_to(  # type: ignore[no-untyped-call]
                    image, reference, order=0
                )
                cache[name] = np.asarray(resampled.dataobj) > 0
        return cache[name]

    return load


def zip_files(files: dict[str, bytes], summary_json: bytes) -> bytes:
    """Los ficheros del visor en un zip sin compresión adicional (NIfTI ya va comprimido)."""
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for name, blob in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            archive.writestr(info, blob)
        archive.writestr(zipfile.ZipInfo("estudio.json", date_time=(2026, 1, 1, 0, 0, 0)),
                         summary_json)
    return buffer.getvalue()
