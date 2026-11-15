# SPDX-License-Identifier: AGPL-3.0-or-later
"""Geometría de un volumen segmentado: medidas de lesiones y mallas 3D.

Por qué existe: una segmentación es un volumen de etiquetas; lo que una persona lee es "lesión de
17 mm en el segmento IVb" y una superficie que puede girar. Este módulo hace ese paso, sin
ningún modelo: geometría sobre vóxeles con el espaciado real.

Adaptador sobre `polaris/tools/visor3d.py` de la copia literal de Polaris, sin modificarla (commit
en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»;
se carga con `app.polaris.load`). Llaman al original: `ply_bytes` (`ply_binario`, a un fichero
temporal), `taubin` (`_taubin`), `mesh` (`_malla`), `icosphere` (`_icosfera`), `ellipsoid`
(`_elipsoide`), `axial_max_diameter` (`_diametro_axial_mayor`), `pair` (`empareja`, traduciendo
`centro_organo_mm`/`region` a sus `centro_higado_mm`/`segmento`) y `evolution` (`evolucion`: el
estado de cada lesión entre dos estudios, con sus textos y sus umbrales). Aquí solo hay nombres en
inglés, tipos y la traducción de claves.

Divergencias con Polaris que siguen siendo código de EMMA (AGPL §5a; decididas con el usuario:
`docs/polaris-divergencias.md` §7 y §7.5):
  * `spacing()`: la norma de cada columna del afín. Polaris usa `abs(diag(afín))`, que con un afín
    oblicuo da un espaciado falso (lo vigila un mutante).
  * `lesions()`: la lógica de `lesiones()` de Polaris, ADAPTADA a mano de `tools/visor3d.py`
    @ 7bf47257 (el commit que se copió primero), que no se puede llamar porque segmenta, lee y
    escribe en disco por sí misma. Recibe las máscaras ya cargadas, usa `spacing()` y llama
    `region` a lo que Polaris llama `segmento`.
  * `with_density()` y `with_stored_density()`: la densidad en unidades Hounsfield dentro de la
    máscara de cada lesión. Código de EMMA entero (decisión del usuario, 2026-10-07): `visor3d`
    no tiene ninguna función que la mida por lesión. Lo más cercano es `fase()`, que da la
    mediana de aorta, porta e hígado para proponer la fase de contraste y no se puede llamar
    (segmenta y lee la serie por sí misma); de ella sale el orden del mínimo de vóxeles
    (`m.sum() > 50`). La referencia es el parénquima con el que `assets.build` centra la
    ventana, como hace Polaris con el nivel de su ventana hepática.
Todo lo que sale de aquí es del modelo de segmentación: "lesión candidata" hasta que una persona
la mida, como en Polaris.

La densidad es DESCRIPTIVA, y por eso este módulo no la interpreta: una cifra de HU dentro de una
máscara automática invita a ponerle nombre a la lesión, y eso es una lectura que EMMA no hace
(`compliance/clinical-decision-rationale.md`). No clasifica, no alerta, no entra en el análisis
ni en el riesgo. Se mide sobre los enteros que se publican en `ct.nii.gz`, para que la cifra
firmada al segmentar y la recalculada desde un zip ya guardado sean la misma.
"""

from __future__ import annotations

import gzip
import io
import logging
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app import polaris

CANDIDATE = "lesión candidata"
SMALL_LESION_MM = 10.0  # Polaris: por debajo, la sensibilidad publicada cae mucho
MIN_VOXELS = 5  # componentes más pequeños = ruido de segmentación
# Umbrales de `evolucion` de Polaris sobre el cambio de diámetro. Allí son literales dentro de la
# función; aquí solo sirven para decir el criterio al lado del estado, y una prueba comprueba en la
# frontera que siguen siendo los de la copia. Quien decide el estado es Polaris, no estas cifras.
GROWS_FROM_PCT = 20
SHRINKS_FROM_PCT = -30
EVOLUTION_CRITERION = (
    "Estado según el cambio del diámetro axial mayor entre los dos estudios: «crece» desde "
    f"+{GROWS_FROM_PCT} %, «se reduce» desde −{abs(SHRINKS_FROM_PCT)} %, «estable» entre ambos. "
    "El emparejado es una propuesta por distancia entre centros, con la distancia a la vista. "
    "Una lesión sin pareja pudo no detectarse en el otro estudio, sobre todo si es pequeña."
)

Mesh = tuple[NDArray[np.float64], NDArray[np.int32]]

log = logging.getLogger(__name__)

# Densidad por lesión (código de EMMA; ver la cabecera).
DENSITY_KEY = "densidad"
LESION_LABEL_BASE = 10  # `assets.build`: la lesión n lleva la etiqueta 10 + n
HU_UCUM = "[hnsf'U]"  # la unidad Hounsfield en UCUM; la interfaz la escribe «HU»
HU_MODALITY = "CT"
# Por debajo no se da cifra. A 1,5 mm de vóxel son 0,17 ml (una esfera de unos 7 mm): con menos,
# casi todo lo medido es borde, donde cada vóxel mezcla lesión y parénquima. Regla de EMMA, del
# orden del mínimo que Polaris pide a cada región en `fase()`; sin validar con lecturas humanas.
DENSITY_MIN_VOXELS = 50
NOT_ASSESSABLE = "no valorable"
TOO_FEW_VOXELS = (
    "No valorable: {voxels} vóxeles, menos de los {minimum} que se piden. Con tan pocos, casi "
    "todos son borde y mezclan la lesión con lo que la rodea."
)
DENSITY_NOTE = (
    "Densidad dentro de la máscara de cada lesión candidata, de una segmentación automática sin "
    "validar: describe los vóxeles que marcó el modelo, borde incluido. No dice qué es la lesión "
    "ni la clasifica, y no entra en el análisis ni en una alerta. La referencia es la densidad "
    "del órgano fuera de las lesiones candidatas, vasos de su interior incluidos, en el mismo "
    "estudio."
)
PHASE_UNDECLARED = (
    "El estudio no declara la fase de contraste, y la densidad cambia con ella: las cifras de "
    "dos estudios solo se pueden poner una junto a otra si se adquirieron en la misma fase."
)
NOT_CT = (
    "Sin densidad: las unidades Hounsfield solo existen en un TAC y este estudio es de "
    "modalidad {modality}."
)
UNREADABLE = "Sin densidad: no se pudo leer la segmentación guardada ({reason})."


def _visor3d() -> Any:
    """El `visor3d.py` de Polaris, tal cual (perezoso: no se carga hasta que hace falta)."""
    return polaris.load("visor3d")


def spacing(affine: NDArray[np.float64]) -> NDArray[np.float64]:
    """Espaciado en mm de cada eje: la norma de cada columna del afín, válida también oblicuo."""
    return np.asarray(np.linalg.norm(affine[:3, :3], axis=0), dtype=np.float64)


def ply_bytes(vertices: NDArray[Any], faces: NDArray[Any]) -> bytes:
    """PLY binario little-endian: x, y, z y caras, lo que lee NiiVue. Polaris `ply_binario`."""
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "malla.ply"
        _visor3d().ply_binario(str(path), vertices, faces)
        return path.read_bytes()


def _box(mask: NDArray[np.bool_], margin: int) -> tuple[NDArray[np.float64], tuple[slice, ...]]:
    """Caja mínima de la máscara con margen. Polaris `_caja_de`."""
    origin, box = _visor3d()._caja_de(mask, margin)
    return np.asarray(origin, dtype=np.float64), tuple(box)


def taubin(
    vertices: NDArray[Any], faces: NDArray[Any], iterations: int = 12,
    lam: float = 0.5, mu: float = -0.53,
) -> NDArray[np.float64]:
    """Suavizado de Taubin: quita el escalón del vóxel sin encoger la malla. Polaris `_taubin`."""
    smoothed = _visor3d()._taubin(
        np.asarray(vertices), np.asarray(faces), iteraciones=iterations, lam=lam, mu=mu
    )
    return np.asarray(smoothed, dtype=np.float64)


def mesh(
    mask: NDArray[np.bool_],
    affine: NDArray[np.float64],
    smoothing: float | tuple[float, ...] = 1.0,
    oversample: int = 1,
    min_component: int = 0,
    taubin_iterations: int = 12,
) -> Mesh | None:
    """Máscara -> malla en mm del mundo (RAS). Polaris `_malla`: recorta a la caja con margen de
    4 sigma antes de suavizar (suavizar el volumen entero pidió 16 GB para un tumor de 2 cm)."""
    result = _visor3d()._malla(
        mask, affine, suavizado=smoothing, sobremuestreo=oversample,
        min_componente=min_component, taubin=taubin_iterations,
    )
    if result is None:
        return None
    vertices, faces = result
    return np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int32)


def icosphere(subdivisions: int = 3) -> Mesh:
    """Esfera unidad: icosaedro subdividido. Polaris `_icosfera`."""
    vertices, faces = _visor3d()._icosfera(subdivisions)
    return np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int32)


def ellipsoid(
    mask: NDArray[np.bool_], affine: NDArray[np.float64], diameter_mm: float | None = None
) -> Mesh | None:
    """Elipsoide ajustado a los vóxeles, para lesiones de menos de 8 mm. Polaris `_elipsoide`,
    con el espaciado de `spacing()` (ver la cabecera)."""
    result = _visor3d()._elipsoide(mask, affine, spacing(affine), diametro_mm=diameter_mm)
    if result is None:
        return None
    vertices, faces = result
    return np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int32)


def axial_max_diameter(mask: NDArray[np.bool_], voxel_mm: NDArray[np.float64]) -> float:
    """Máximo diámetro en cualquier corte axial, entre centros de vóxel. Polaris
    `_diametro_axial_mayor` (el Feret de scikit-image sobreestimaba un píxel)."""
    return float(_visor3d()._diametro_axial_mayor(mask, voxel_mm))


def lesions(
    organ: NDArray[np.bool_],
    lesion_mask: NDArray[np.bool_],
    affine: NDArray[np.float64],
    regions: NDArray[np.integer[Any]] | None = None,
    second_model: NDArray[np.bool_] | None = None,
) -> tuple[list[dict[str, Any]], NDArray[np.uint8]]:
    """Lesiones candidatas dentro de un órgano, de mayor a menor volumen. De Polaris `lesiones()`.

    `regions`: subdivisión del órgano (p. ej. segmentos de Couinaud) para decir dónde está cada una.
    `second_model`: otra segmentación de la lesión; se da qué fracción coincide. Dos modelos que
    coinciden no validan nada, pero uno que discrepa es una bandera útil.
    """
    from scipy import ndimage

    voxel = spacing(affine)
    voxel_ml = float(np.prod(voxel)) / 1000.0
    inside = ndimage.binary_dilation(organ, iterations=3)
    components, count = ndimage.label(lesion_mask & inside)
    found: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        component = components == i
        voxels = int(component.sum())
        if voxels < MIN_VOXELS:
            continue
        center = (affine @ np.append(np.argwhere(component).mean(axis=0), 1.0))[:3]
        region = None
        if regions is not None:
            values = regions[component]
            values = values[values > 0]
            region = int(np.bincount(values.astype(np.int64)).argmax()) if values.size else None
        diameter = axial_max_diameter(component, voxel)
        found.append({
            "_component": i,
            "estado": CANDIDATE,
            "diametro_mm": round(diameter, 1),
            "volumen_ml": round(voxels * voxel_ml, 2),
            "centro_mm": [round(float(c), 1) for c in center],
            "region": region,
            "pequena": diameter < SMALL_LESION_MM,
            "acuerdo_2o_modelo": (
                round(float(second_model[component].mean()), 2)
                if second_model is not None else None
            ),
        })
    found.sort(key=lambda item: -item["volumen_ml"])
    ids = np.zeros(components.shape, np.uint8)
    for number, item in enumerate(found, start=1):
        item["id"] = number
        ids[components == item.pop("_component")] = number
    return found, ids


def pair(
    before: dict[str, Any], after: dict[str, Any],
    tolerance_mm: float = 15.0, same_region_tolerance_mm: float = 25.0,
) -> list[dict[str, Any]]:
    """Empareja lesiones de dos estudios. Polaris `empareja`: húngaro sobre la distancia entre
    centroides tras alinear el centro del órgano, con la región como desempate.

    Ayuda, no verdad: el emparejado bueno sale del informe radiológico; aquí se propone, con la
    distancia a la vista.
    """
    def as_polaris(study: dict[str, Any]) -> dict[str, Any]:
        return {
            "centro_higado_mm": study["centro_organo_mm"],
            "lesiones": [{**item, "segmento": item.get("region")} for item in study["lesiones"]],
        }

    pairs = _visor3d().empareja(
        as_polaris(before), as_polaris(after),
        tolerancia_mm=tolerance_mm, tolerancia_mismo_segmento_mm=same_region_tolerance_mm,
    )
    return [dict(item) for item in pairs]


def evolution(
    pairs: list[dict[str, Any]], lesions_after: list[dict[str, Any]]
) -> dict[int, dict[str, Any]]:
    """Estado de cada lesión del estudio posterior respecto al anterior. Polaris `evolucion`, tal
    cual: los textos («crece», «se reduce», «estable», «no vista en el TC previo») y los umbrales
    son suyos.

    «No vista antes» no es «nueva»: el modelo pudo no detectarla en el estudio previo. Describe
    un cambio de tamaño entre dos segmentaciones automáticas; no es una lectura ni una respuesta
    al tratamiento.
    """
    states = _visor3d().evolucion(pairs, lesions_after)
    return {int(lesion): dict(state) for lesion, state in states.items()}


def _hu(values: NDArray[Any]) -> dict[str, Any]:
    """Lo que se dice de un conjunto de vóxeles: cuántos son y, si bastan, mediana, media,
    desviación y percentiles 10 y 90 en HU."""
    block: dict[str, Any] = {
        "valorable": False, "voxeles": int(values.size), "mediana_hu": None, "media_hu": None,
        "desviacion_hu": None, "p10_hu": None, "p90_hu": None, "motivo": None,
    }
    if values.size < DENSITY_MIN_VOXELS:
        block["motivo"] = TOO_FEW_VOXELS.format(
            voxels=int(values.size), minimum=DENSITY_MIN_VOXELS
        )
        return block
    sample = values.astype(np.float64)
    low, median, high = np.percentile(sample, [10, 50, 90])
    block.update({
        "valorable": True,
        "mediana_hu": round(float(median), 1),
        "media_hu": round(float(sample.mean()), 1),
        "desviacion_hu": round(float(sample.std()), 1),
        "p10_hu": round(float(low), 1),
        "p90_hu": round(float(high), 1),
    })
    return block


def no_density(reason: str | None) -> dict[str, Any]:
    """El bloque de una segmentación de la que no se da densidad, con su motivo."""
    return {
        "disponible": False, "motivo": reason, "unidad": HU_UCUM,
        "minimo_voxeles": DENSITY_MIN_VOXELS, "no_valorable": NOT_ASSESSABLE,
        "referencia": None, "notas": [],
    }


def with_density(
    summary: dict[str, Any], ct: NDArray[Any], labels: NDArray[Any],
    parenchyma_labels: Sequence[int], reference_name: str,
) -> dict[str, Any]:
    """El resumen de una segmentación con la densidad (HU) de cada lesión candidata y la del
    parénquima como referencia. Devuelve una copia: no toca lo que recibe.

    `ct` y `labels` son los que se publican (`ct.nii.gz`, `etiquetas.nii.gz`), ya en HU reales
    (nibabel aplica `scl_slope` y `scl_inter` al leer `dataobj`). `parenchyma_labels`: las etiquetas
    del órgano y de lo que queda dentro de él; las lesiones (10 + n) nunca están entre ellas.

    Sin lesiones no añade nada. Fuera de un TAC no hay unidades Hounsfield: se dice y no se da
    ninguna cifra.
    """
    lesions = list(summary.get("lesiones") or [])
    if not lesions:
        return summary
    modality = str(summary.get("modalidad"))
    if modality != HU_MODALITY:
        return {**summary, DENSITY_KEY: no_density(NOT_CT.format(modality=modality))}
    measured = [
        {**item, DENSITY_KEY: _hu(ct[labels == LESION_LABEL_BASE + int(item["id"])])}
        for item in lesions
    ]
    block = {
        **no_density(None),
        "disponible": True,
        "referencia": {
            "nombre": reference_name, **_hu(ct[np.isin(labels, list(parenchyma_labels))]),
        },
        # Un NIfTI no lleva la fase y EMMA no la propone: aquí va vacía. Si una persona la
        # declara (`contrast_phase.py`), se pone al servir en lugar de la nota: la declaración
        # puede llegar después de esta firma, y lo firmado no se reescribe.
        "fase_contraste": None,
        "notas": [DENSITY_NOTE, PHASE_UNDECLARED],
    }
    return {**summary, "lesiones": measured, DENSITY_KEY: block}


def with_stored_density(
    segmentation: dict[str, Any], archive: bytes, parenchyma_labels: Sequence[int],
    reference_name: str,
) -> dict[str, Any]:
    """Lo mismo para una segmentación ya guardada sin densidad, desde su zip firmado. No lanza
    excepciones: si el zip no se puede leer, el bloque dice que no hay densidad y por qué."""
    import nibabel as nib

    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            ct: Any = nib.Nifti1Image.from_bytes(gzip.decompress(bundle.read("ct.nii.gz")))
            labels: Any = nib.Nifti1Image.from_bytes(
                gzip.decompress(bundle.read("etiquetas.nii.gz"))
            )
        return with_density(
            segmentation, np.asarray(ct.dataobj), np.asarray(labels.dataobj),
            parenchyma_labels, reference_name,
        )
    except Exception as exc:  # noqa: BLE001 — un zip ilegible no impide listar la segmentación
        log.exception("no se pudo leer la segmentación guardada para medir su densidad")
        reason = UNREADABLE.format(reason=f"{type(exc).__name__}: {exc}")
        return {**segmentation, DENSITY_KEY: no_density(reason)}
