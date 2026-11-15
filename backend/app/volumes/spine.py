# SPDX-License-Identifier: AGPL-3.0-or-later
"""Control de la cadena vertebral de una segmentación del esqueleto: entera, en orden y qué falta.

Por qué existe: a primeros de octubre de 2026 una segmentación del preset `esqueleto` salió con
40 de 60 huesos —sin C1-C4 y sin nada de T11 hacia abajo— y nadie avisó: el visor la enseñó como
buena y tapó a la correcta, porque un esqueleto al que le falta media columna se dibuja igual de
bien que uno entero (`compliance/risk-management-file.md`, «Esqueleto incompleto»). Polaris ya
había tropezado con lo mismo (su modelo de 3 mm perdía T11, T12 y C5-C7, y T9 salía con 58 mm³) y
tiene el control hecho. Este módulo lo llama y deja el resultado en el resumen de la segmentación,
para que lo que falta se diga junto al visor en vez de descubrirse mirando.

Es un control de la SEGMENTACIÓN automática, no una lectura de la persona: no bloquea, no borra
nada, no entra en el análisis ni en una alerta. Si el propio control falla, se dice y la
segmentación sigue. Hoy no vuela ningún TAC; estos volúmenes son imagen de referencia previa al
vuelo o de Tierra.

Adaptador sobre Polaris copiado tal cual (`polaris/tools/visor3d.py`; el commit, en
`polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»; se
carga con `app.polaris.load`). Llama al original, sin tocarlo:
  * `_revisa_cadena(nombres, lab, afín)`: huecos en mitad de la cadena, orden y niveles
    reconocidos a medias (`VERTEBRA_MIN_MM3`). No devuelve nada: escribe por consola y aborta con
    `SystemExit`. Aquí se capturan la consola y el aborto, y de su texto se leen los huecos, el
    orden y los niveles pequeños. Si ese texto cambia en la copia, el control se declara no hecho
    (y las pruebas, que dependen de él, se ponen rojas).
  * `_orden_columna(centros)`: el orden con los centroides en milímetros, y qué niveles lo rompen.
  * `CADENA`: el orden de C1 a S1; `VERTEBRA_MIN_MM3`.

Lo que pone EMMA alrededor (AGPL §5a; pendiente de decisión en `docs/polaris-divergencias.md`):
  * La cadena de Polaris acaba en `vertebrae_S1`, que no está entre los 60 huesos del preset. Aquí
    el `sacrum` hace de extremo caudal: se le pasa a Polaris con el nombre de S1.
  * Se le pasa el mapa de etiquetas recortado a la caja de la columna. `_revisa_cadena` recorre el
    volumen entero una vez por nivel (medido el 2026-10-07 en el ejemplo `esqueleto-4`: 5 s con el
    volumen entero; con el recorte, el control completo tarda 0,5 s) y recortar no cambia ni los
    volúmenes ni el orden.
  * Extremos. Para Polaris solo es hueco lo que falta ENTRE dos niveles presentes; lo que falta
    por arriba o por abajo no lo cuenta. El caso de los 40 de 60 era justo ese —faltaban los dos
    extremos y el TAC sí los cubría—, así que el control de Polaris, solo, lo habría dado por
    bueno. Y casi ningún TAC cubre la columna entera: avisar de todo extremo ausente sería avisar
    siempre. EMMA mide cuánto volumen queda más allá del último nivel presente: si cabe otro nivel
    (`FIELD_STEPS` veces el paso entre los dos niveles enteros de ese extremo, medido en ESE
    estudio y no con tallas de libro), pide atención; si no, el volumen acaba ahí y es dato
    ausente. Regla geométrica de EMMA, probada con el caso real y con recortes del ejemplo real,
    sin validar con más estudios.
  * Niveles reconocidos a medias. Polaris los escribe y no aborta. Aquí piden atención en mitad de
    la cadena; en un extremo son el borde del volumen, que corta la última vértebra, y son dato
    ausente (`_edge_run`).
  * El sentido. Polaris da por buena la cadena monótona hacia arriba o hacia abajo, porque no fija
    la rejilla. En NIfTI la z del mundo crece hacia la cabeza: C1 por debajo del sacro es una
    cadena del revés, y se dice.
  * Los huesos del preset sin vóxeles, que Polaris no lista.
  * `niveles_por_conteo` (contar cuerpos por los discos) NO se usa: en `esqueleto-4`, a 2 mm,
    cuenta 18 cuerpos de 24 y no devuelve nada. `niveles_por_reparto` exige `skull`, que tampoco
    está entre los 60 huesos.
"""

from __future__ import annotations

import ast
import gzip
import io
import logging
import re
import zipfile
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

from app import polaris
from app.polaris import console

if TYPE_CHECKING:
    from app.volumes.assets import Preset

log = logging.getLogger(__name__)

KEY = "cadena_vertebral"
PRESET = "esqueleto"
CONTROL = "Polaris visor3d._revisa_cadena y _orden_columna"
CAUDAL_END = "sacrum"  # hace de `vertebrae_S1`, el final de la cadena de Polaris
POLARIS_END = "vertebrae_S1"
# Cuántos pasos entre niveles tiene que quedar del último nivel presente al borde del volumen para
# decir que el siguiente cabía entero: uno hasta su centro y medio más hasta su borde.
FIELD_STEPS = 1.5

# Niveles del aviso, con el significado de la tabla F.5-1 de NASA-STD-3001 (la interfaz les pone
# el color): "attention required" y "missing or stale data". No son niveles de riesgo.
ATTENTION = "atencion"
MISSING = "dato_ausente"

_SCOPE = " Es un control del modelo de segmentación, no un hallazgo sobre la persona."
NOTICES = {
    ATTENTION: (
        "Control automático de esta segmentación, sin validar: la cadena vertebral no sale entera "
        "o en orden, y los nombres de los niveles vecinos pueden no corresponder." + _SCOPE
    ),
    MISSING: (
        "Control automático de esta segmentación, sin validar: hay huesos del preset que no "
        "aparecen o que salen a medias en un extremo de la columna. Puede ser que el volumen no "
        "los cubra o que el modelo no los encontrara." + _SCOPE
    ),
}
NOT_DONE = (
    "No se pudo hacer el control automático de la cadena vertebral de esta segmentación "
    "({reason}). Sin él no se sabe si la columna sale entera y en orden."
)
END_TITLES = {
    True: ("el volumen continúa más allá", ATTENTION),
    False: ("el volumen termina ahí", MISSING),
    None: ("no se pudo medir si el volumen continúa", MISSING),
}

_GAPS = re.compile(r"huecos: (?P<gaps>.+?) · en orden: (?P<order>True|False)\)")
_BREAKS = re.compile(r"rompen: (?P<levels>\[.*?\])\)")
_SMALL = re.compile(r"(vertebrae_\w+) \((\d+) mm³\)")


def _from_polaris(name: str) -> str:
    return CAUDAL_END if name == POLARIS_END else name


def _to_polaris(name: str) -> str:
    return POLARIS_END if name == CAUDAL_END else name


Span = tuple[float, float]
# El campo de un volumen en los tres ejes del mundo (x, y, z en mm, RAS como todo NIfTI).
Field = tuple[Span, Span, Span]


def field_mm(shape: tuple[int, ...], affine: NDArray[np.float64]) -> Field:
    """El tramo que cubre un volumen en cada eje del mundo (mm): entre sus vóxeles extremos.

    Es la caja de la REJILLA. Si la reconstrucción no la llena (un campo circular dentro de ella),
    un hueso que ese campo corta sin llegar al borde de la rejilla no se ve aquí.
    """
    corners = np.array(
        [[i, j, k, 1.0] for i in (0, shape[0] - 1) for j in (0, shape[1] - 1)
         for k in (0, shape[2] - 1)]
    )
    world = (np.asarray(affine, dtype=np.float64) @ corners.T)[:3]
    x, y, z = ((float(axis.min()), float(axis.max())) for axis in world)
    return x, y, z


def field_z_mm(shape: tuple[int, ...], affine: NDArray[np.float64]) -> Span:
    """El tramo craneocaudal (z del mundo, mm) que cubre un volumen: entre sus vóxeles extremos."""
    return field_mm(shape, affine)[2]


def volume_field_mm(volume: bytes) -> Field:
    """`field_mm` de un NIfTI guardado (.nii o .nii.gz): solo se lee la cabecera, no el volumen."""
    import nibabel as nib

    zipped = volume[:2] == b"\x1f\x8b"
    stream: Any = gzip.GzipFile(fileobj=io.BytesIO(volume)) if zipped else io.BytesIO(volume)
    header: Any = nib.Nifti1Header.from_fileobj(stream)  # type: ignore[no-untyped-call]
    return field_mm(tuple(header.get_data_shape()[:3]), header.get_best_affine())


def volume_field_z_mm(volume: bytes) -> Span:
    """`field_z_mm` de un NIfTI guardado: solo se lee la cabecera, no el volumen."""
    return volume_field_mm(volume)[2]


def _call(function: Any, *args: Any) -> tuple[str, str | None]:
    """Llama a una función de Polaris: (lo que escribió por consola, el motivo si abortó).

    La consola es de todo el proceso y de ese texto sale el control: se captura bajo el cerrojo
    común (`app/polaris/console.py`), el mismo que usan `export.py` y `kb.py`. Con uno propio, un
    PDF exportado a la vez se llevaba el texto y la cadena salía «no revisada».
    """
    with console.captured() as out:
        try:
            function(*args)
        except SystemExit as stop:
            return out.getvalue(), str(stop.code)
    return out.getvalue(), None


def _levels(text: str) -> list[str]:
    """Una lista de niveles tal como la escribe Polaris (`['vertebrae_T7']` o `ninguno`)."""
    if text == "ninguno":
        return []
    parsed = ast.literal_eval(text)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError(f"Polaris no da una lista de niveles: {text!r}")
    return [_from_polaris(item) for item in parsed]


def _unrecognised(function: str, text: str) -> ValueError:
    return ValueError(f"no se reconoce lo que dice `{function}` de Polaris: {text!r}")


def review(
    labels: NDArray[Any],
    affine: NDArray[np.float64],
    preset: Preset,
    field_z: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """El bloque `cadena_vertebral` de una segmentación del esqueleto. No lanza excepciones.

    `labels` y `affine` son el mapa de etiquetas que se publica (`etiquetas.nii.gz`), en la rejilla
    canónica en la que EMMA remuestrea todo volumen (`assets.resample`: el tercer eje es el
    craneocaudal, que es lo que da por hecho Polaris). `field_z` es el tramo de z que cubre el
    volumen del estudio (`field_z_mm`); sin él no se mide si un extremo ausente cabía.
    """
    seen = {int(value) for value in np.unique(labels)}
    block = _blank(preset)
    block["huesos_sin_voxeles"] = [s.mask for s in preset.structures if s.label not in seen]
    try:
        block.update(_chain(labels, np.asarray(affine, dtype=np.float64), preset, seen, field_z))
        block["revisada"] = True
    except Exception as exc:  # noqa: BLE001 — el control no tumba la segmentación que describe
        log.exception("el control de la cadena vertebral no se pudo hacer")
        block["motivo"] = f"{type(exc).__name__}: {exc}"
    return _with_notice(block, preset)


def _blank(preset: Preset) -> dict[str, Any]:
    """El bloque antes de mirar nada: sin revisar y sin listas. Con `revisada` a False, las listas
    de niveles no dicen nada (ni que falten ni que estén)."""
    return {
        "revisada": False,
        "control": CONTROL,
        "motivo": None,
        "niveles_esperados": None,
        "niveles_presentes": [],
        "niveles_ausentes": [],
        "huecos": [],
        "extremos": [],
        "orden_coherente": None,
        "invertida": None,
        "rompen_orden": [],
        "niveles_pequenos": [],
        "umbral_pequeno_mm3": None,
        "huesos_esperados": len(preset.structures),
        "huesos_sin_voxeles": [],
    }


def _chain(
    labels: NDArray[Any], affine: NDArray[np.float64], preset: Preset, seen: set[int],
    field_z: tuple[float, float] | None,
) -> dict[str, Any]:
    """Lo que dicen las funciones de Polaris de la cadena, más los extremos (regla de EMMA)."""
    from scipy import ndimage

    visor3d: Any = polaris.load("visor3d")
    label_of = {structure.mask: structure.label for structure in preset.structures}
    chain = [name for name in map(_from_polaris, visor3d.CADENA) if name in label_of]
    present = [name for name in chain if label_of[name] in seen]
    found: dict[str, Any] = {
        "niveles_esperados": len(chain),
        "niveles_presentes": present,
        "niveles_ausentes": [name for name in chain if label_of[name] not in seen],
        "umbral_pequeno_mm3": int(visor3d.VERTEBRA_MIN_MM3),
    }
    if not present:
        return found
    ids = [label_of[name] for name in present]
    # Solo la caja de la columna: Polaris recorre todo lo que recibe una vez por nivel.
    index = np.argwhere(np.isin(labels, ids))
    low, high = index.min(axis=0), index.max(axis=0) + 1
    crop = labels[tuple(slice(int(a), int(b)) for a, b in zip(low, high, strict=True))]

    names = {label_of[name]: _to_polaris(name) for name in chain}
    said, stopped = _call(visor3d._revisa_cadena, names, crop, affine)
    gaps: list[str] = []
    in_order = True
    if stopped is not None:
        verdict = _GAPS.search(stopped)
        if verdict is None:
            raise _unrecognised("_revisa_cadena", stopped)
        gaps, in_order = _levels(verdict["gaps"]), verdict["order"] == "True"

    # Centroides en milímetros del mundo, como los que Polaris da a `_orden_columna`.
    centres = {
        _to_polaris(name): [
            float(v) for v in (affine @ np.append(np.asarray(centre) + low, 1.0))[:3]
        ]
        for name, centre in zip(
            present, ndimage.center_of_mass(crop > 0, crop, ids), strict=True
        )
    }
    _, disorder = _call(visor3d._orden_columna, centres)
    breaks: list[str] = []
    if disorder is not None:
        broken = _BREAKS.search(disorder)
        if broken is None:
            raise _unrecognised("_orden_columna", disorder)
        breaks = _levels(broken["levels"])

    def z_of(name: str) -> float:
        return centres[_to_polaris(name)][2]

    monotonic = in_order and disorder is None
    # Monótona para Polaris, pero con el primer nivel por debajo del último: del revés.
    inverted = monotonic and len(present) > 1 and z_of(present[0]) < z_of(present[-1])
    coherent = monotonic and not inverted
    small = {_from_polaris(name): int(mm3) for name, mm3 in _SMALL.findall(said)}
    edge = _edge_run(present, set(small))
    solid = [name for name in present if name not in small]
    found.update({
        "huecos": gaps,
        "orden_coherente": coherent,
        "invertida": inverted,
        "rompen_orden": breaks,
        "niveles_pequenos": [
            {"nivel": name, "volumen_mm3": mm3, "en_extremo": name in edge}
            for name, mm3 in small.items()
        ],
        "extremos": _ends(chain, present, solid, z_of, field_z if coherent else None),
    })
    return found


def _edge_run(present: list[str], small: set[str]) -> set[str]:
    """Los niveles pequeños seguidos desde un extremo de la cadena presente (regla de EMMA).

    Casi ningún TAC cubre la columna entera, y donde el volumen acaba la última vértebra queda
    cortada: sale con pocos vóxeles sin que el modelo haya fallado (medido recortando el ejemplo
    `esqueleto-4`: 64 a 1808 mm³ en el último nivel de cada extremo). En mitad de la cadena un
    nivel pequeño no tiene esa explicación, que es el caso de Polaris (T9 con 58 mm³).
    """
    edge: set[str] = set()
    for ordered in (present, present[::-1]):
        for name in ordered:
            if name not in small:
                break
            edge.add(name)
    return edge


def _ends(
    chain: list[str], present: list[str], solid: list[str], z_of: Callable[[str], float],
    field_z: tuple[float, float] | None,
) -> list[dict[str, Any]]:
    """Lo que falta por arriba y por abajo, y si el volumen seguía más allá (regla de EMMA).

    El margen va del centroide del último nivel presente al borde del volumen. El paso se mide
    entre los dos niveles enteros (`solid`, los no pequeños) de ese extremo: el centroide de una
    vértebra cortada por el borde no está en su centro, y con él el paso salía de 3 mm. Con el
    orden roto no se sabe hacia dónde queda cada extremo: se llama sin `field_z` y no se mide;
    tampoco con menos de dos niveles enteros.
    """
    position = {name: slot for slot, name in enumerate(chain)}
    ends = []
    for side, outer, pair, names in (
        ("craneal", present[0], solid[:2], chain[:position[present[0]]]),
        ("caudal", present[-1], solid[-2:], chain[position[present[-1]] + 1:]),
    ):
        if not names:
            continue
        step: float | None = None
        room: float | None = None
        continues: bool | None = None
        if field_z is not None and len(pair) == 2:
            step = abs(z_of(pair[0]) - z_of(pair[1])) / (position[pair[1]] - position[pair[0]])
            # En NIfTI la z del mundo crece hacia la cabeza.
            room = field_z[1] - z_of(outer) if side == "craneal" else z_of(outer) - field_z[0]
            continues = room >= FIELD_STEPS * step
        ends.append({
            "lado": side,
            "niveles": names,
            "volumen_continua": continues,
            "margen_mm": None if room is None else round(room, 1),
            "paso_mm": None if step is None else round(step, 1),
        })
    return ends


def _with_notice(block: dict[str, Any], preset: Preset) -> dict[str, Any]:
    """Lo que se enseña junto al visor, ya redactado: nivel, aviso y listas con sus nombres."""
    display = {structure.mask: structure.display for structure in preset.structures}
    lists: list[dict[str, Any]] = []

    def add(title: str, names: list[str], level: str) -> None:
        if names:
            lists.append({
                "titulo": title, "nivel": level, "elementos": [display[name] for name in names],
            })

    present, absent = block["niveles_presentes"], block["niveles_ausentes"]
    add("Niveles ausentes en mitad de la cadena", block["huecos"], ATTENTION)
    if block["invertida"]:
        add("Cadena del revés: el primer nivel queda por debajo del último", present, ATTENTION)
    elif block["orden_coherente"] is False:
        add("Niveles fuera del orden craneocaudal", block["rompen_orden"] or present, ATTENTION)
    for at_the_edge, title, level in (
        (False, "Niveles reconocidos a medias en mitad de la cadena", ATTENTION),
        (True, "Niveles reconocidos a medias en un extremo de la cadena", MISSING),
    ):
        add(
            title,
            [item["nivel"] for item in block["niveles_pequenos"]
             if item["en_extremo"] is at_the_edge],
            level,
        )
    for end in block["extremos"]:
        measured, level = END_TITLES[end["volumen_continua"]]
        add(f"Niveles ausentes en el extremo {end['lado']}: {measured}", end["niveles"], level)
    if not present:
        add("Sin niveles vertebrales en esta segmentación", absent, MISSING)
    chain = {*present, *absent}
    add(
        "Otros huesos sin vóxeles" if chain else "Huesos sin vóxeles",
        [name for name in block["huesos_sin_voxeles"] if name not in chain], MISSING,
    )

    overall: str | None = None
    notice: str | None = None
    if not block["revisada"]:
        overall, notice = MISSING, NOT_DONE.format(reason=block["motivo"])
    elif lists:
        overall = ATTENTION if any(item["nivel"] == ATTENTION for item in lists) else MISSING
        notice = NOTICES[overall]
    return {**block, "nivel": overall, "aviso": notice, "listas": lists}


def unreviewed(preset: Preset, reason: str) -> dict[str, Any]:
    """El bloque de una segmentación cuyo mapa de etiquetas no se pudo leer: se dice por qué."""
    return _with_notice({**_blank(preset), "motivo": reason}, preset)


def review_stored(archive: bytes, volume: bytes | None, preset: Preset) -> dict[str, Any]:
    """El mismo bloque para una segmentación ya guardada, desde lo firmado: su zip y, para medir
    los extremos, el volumen de su estudio (None si no se pudo leer)."""
    import nibabel as nib

    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            raw = bundle.read("etiquetas.nii.gz")
        image: Any = nib.Nifti1Image.from_bytes(gzip.decompress(raw))
        labels, affine = np.asarray(image.dataobj), image.affine
        field_z = None if volume is None else volume_field_z_mm(volume)
    except Exception as exc:  # noqa: BLE001 — un zip ilegible no impide listar la segmentación
        log.exception("no se pudo leer la segmentación guardada para su control")
        return unreviewed(preset, f"{type(exc).__name__}: {exc}")
    return review(labels, affine, preset, field_z)
