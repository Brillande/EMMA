# SPDX-License-Identifier: AGPL-3.0-or-later
"""El dolor referido, sobre el esqueleto real: `visor3d_superpone_focos.alinea` de Polaris tal cual.

Por qué existe: el mapa de dolor es un cuerpo dibujado a mano (`pain/bodyModel.ts`) y el
esqueleto de referencia (F8) es anatomía real de BodyParts3D. Ver dónde cae una zona dolorida
sobre el hueso ayuda a leerla ("lumbar" es L1-L5, no un rectángulo). Pegar las coordenadas del
dibujo sobre el esqueleto las deja fuera de sitio: tienen proporciones distintas. Polaris resolvió
justo eso para sus focos óseos: con las zonas que nombran un hueso de centroide conocido (anclas)
ajusta por mínimos cuadrados una escala y una traslación por eje, la aplica a todas, y el error
residual de las anclas dice si el ajuste vale.

Su `FOCOS`, `ANCLAS` y `VB` son del caso de su autora: se sustituyen por los de EMMA durante la
llamada y bajo cerrojo (patrón de `timeline.py`); la copia no se toca. No se usa su `main()`:
pinta con su ámbar (en EMMA, color de precaución) en su carpeta de marca.

**Umbral** (de la geometría, no ajustado a los datos): el ajuste vale si el error medio de las
anclas es menor que la mitad de la zona anclada más pequeña (desde el cuerpo de 2026-11-09, el
cuello: 0,16 m de 1,73; antes, pelvis y cadera con 0,14): con eso el punto cae dentro de su zona.
Las alturas son las de `bodyModel.ts`, copiadas en `pain_points.json` y vigiladas por su prueba.
Si no, se dice "no se superpone" en vez de pintar mal.

Es una figura de referencia: el punto dice dónde se refirió el dolor, no qué tiene el hueso.

**Sobre el propio TAC** (2026-10-07). Cuando el tripulante tiene una segmentación del esqueleto
vigente, la figura es la suya (`volumes/skeleton_view.py`) y el mismo ajuste se hace sobre ella,
con tres diferencias que salen de que un TAC casi nunca trae el cuerpo entero:
  * Solo vale de ancla un hueso que el estudio trae ENTERO. El centroide de un fémur cortado por
    el borde es el de su trozo, y con él el ajuste se va.
  * Una recta por eje pasa siempre por dos puntos: con menos de `MIN_POSITIONS` posiciones
    distintas de las anclas a lo ancho o a lo alto, el error sale nulo por construcción y el
    umbral no comprobaría nada. Entonces no se alinea, y se dice.
  * La zona cuyo hueso de anclaje no está, o que el ajuste deja fuera de la imagen, no se pinta en
    otro sitio: se declara «fuera del estudio».
El umbral es el mismo (la mitad de la zona anclada más pequeña), en milímetros físicos: la
proyección dice cuántos abarca la imagen. Y un ajuste con escala negativa en un eje —las anclas
pidiendo un espejo— no coloca nada, por pequeño que le salga el error.

**Modo DIRECTO de Polaris** (decisión del usuario, 2026-10-20). El ajuste estira el dibujo, y en
`esqueleto-4` dejaba la zona lumbar a 75 mm de L3, su propio hueso. Polaris ya lo resolvió en su
`main()`: «cuando el mapa trae niveles vertebrales, cada foco va al centroide de SU vértebra y no
hace falta alinear nada» (`px, py = c["u"] * W, c["v"] * H`). Aquí se hace eso mismo, zona a zona:
la que tiene de ancla un hueso que la figura trae entero se pone en el centroide de ese hueso
(`placed_on: "bone"`), en la de referencia y en la del TAC. Dos diferencias con Polaris, porque
`main()` no se puede llamar (pinta en su carpeta de marca) y su regla es de todo o nada —si un
solo foco no tiene hueso, alinea todos—, que con el mapa de EMMA no se daría nunca (cabeza,
abdomen o rodilla no tienen hueso en el mapa):
  * Las demás zonas —sin hueso, o con su hueso cortado por el borde del estudio— se siguen
    colocando con el ajuste (`placed_on: "fit"`), o se declaran fuera del estudio, como antes.
    El centroide de un hueso cortado es el de su trozo: ponerla ahí sería inventar la posición.
  * El ajuste se sigue calculando y sigue decidiendo si se pinta algo: su error, su umbral y el
    rechazo del espejo no cambian. Lo que deja de medir es la posición de las zonas ancladas, que
    ya no salen de él.

Licencia y origen (AGPL §5a): usa `polaris/tools/visor3d_superpone_focos.py` de la copia literal de
Polaris, sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de
Polaris, «Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: los focos, las anclas y
el umbral del ajuste.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from functools import cache
from pathlib import Path
from typing import Any

from app import polaris
from app.core import i18n
from app.pain.catalog import ZONES

DATA = Path(__file__).resolve().parent / "data" / "anatomy"
_LOCK = threading.Lock()
RECENT = dt.timedelta(days=7)

# De dónde sale la figura sobre la que se coloca (lo dice `anatomy.subject_skeleton`).
REFERENCE = "reference"
OWN_CT = "own-ct"
# Posiciones distintas de las anclas que hacen falta, a lo ancho y a lo alto, para que el error
# del ajuste diga algo (abajo, en `_align`, por qué).
MIN_POSITIONS = 3

TOO_FEW_ANCHORS = (
    "El dolor referido no se alinea sobre este estudio: el TAC no trae enteros huesos de anclaje "
    "suficientes (hacen falta al menos tres posiciones distintas a lo ancho y a lo alto del "
    "cuerpo) para comprobar el ajuste."
)
NO_FIT = (
    "El dolor referido no se alinea sobre este esqueleto: el ajuste de Polaris no sale ({reason})."
)
FLIPPED = (
    "El dolor referido no se superpone: las anclas piden darle la vuelta al mapa de dolor para "
    "encajarlo en este esqueleto."
)
BAD_FIT = (
    "El dolor referido no se superpone: el ajuste del mapa de dolor a este esqueleto no vale "
    "(el error medio de las anclas supera la mitad de la zona anclada más pequeña)."
)
BONE_NOT_IN_STUDY = "Fuera del estudio: el hueso de esta zona no está en el TAC."
# Cómo se ha colocado cada zona (arriba, «Modo DIRECTO»): sobre el centroide de su hueso o con el
# ajuste.
ON_BONE = "bone"
BY_FIT = "fit"
OFF_THE_IMAGE = "Fuera del estudio: la zona cae más allá de lo que cubre el TAC."

# El inglés de esas frases (2026-11-15). El ajuste se calcula y se guarda en castellano
# (`alignment` está cacheado y no sabe quién pregunta); el idioma se pone al servir, en `overlay`.
i18n.en_many({
    TOO_FEW_ANCHORS: (
        "Reported pain is not aligned on this study: the CT does not include enough whole anchor "
        "bones (at least three distinct positions across the width and the height of the body "
        "are needed) to check the fit."
    ),
    NO_FIT: (
        "Reported pain is not aligned on this skeleton: the Polaris fit does not work out "
        "({reason})."
    ),
    FLIPPED: (
        "Reported pain is not overlaid: the anchors call for flipping the pain map to fit it "
        "onto this skeleton."
    ),
    BAD_FIT: (
        "Reported pain is not overlaid: the fit of the pain map to this skeleton does not hold "
        "(the mean anchor error exceeds half of the smallest anchored zone)."
    ),
    BONE_NOT_IN_STUDY: "Outside the study: the bone of this zone is not in the CT.",
    OFF_THE_IMAGE: "Outside the study: the zone falls beyond what the CT covers.",
})


def _reason(text: str | None) -> str | None:
    """Por qué no se superpone, en el idioma de la petición. La frase de `NO_FIT` lleva dentro el
    motivo con que aborta Polaris, que es suyo y se queda como lo escribe: se traduce lo de fuera.
    """
    if text is None:
        return None
    before, _, after = NO_FIT.partition("{reason}")
    if text.startswith(before) and text.endswith(after):
        inner = text[len(before):len(text) - len(after)]
        return i18n.loc(NO_FIT).format(reason=inner)
    return i18n.loc(text)


@cache
def _tool() -> Any:
    return polaris.load("visor3d_superpone_focos")


@cache
def points() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((DATA / "pain_points.json").read_text(encoding="utf-8"))
    return data


@cache
def skeleton() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((DATA / "esqueleto.json").read_text(encoding="utf-8"))
    return data


@cache
def alignment() -> dict[str, Any]:
    """Cada zona del mapa de dolor en la imagen del esqueleto de referencia, y si el ajuste vale."""
    figure = skeleton()
    width, height = figure["tamano"]
    # La figura de referencia es un cuerpo entero: su alto es la talla del modelo.
    return _align(figure["huesos"], width, height, height / float(points()["body_height_m"]))


def alignment_on(figure: dict[str, Any]) -> dict[str, Any]:
    """Lo mismo sobre la figura que da `anatomy.subject_skeleton`: la de referencia o la del TAC.

    En la del TAC la escala es física (la proyección dice cuántos milímetros abarca), así que el
    umbral son milímetros de verdad y no una fracción de un cuerpo entero que la imagen no trae.
    """
    if figure.get("source") != OWN_CT:
        return alignment()
    top, bottom = figure["extent_mm"]["z"]
    return _align(
        {name: point for name, point in figure["bones"].items() if not point["truncated"]},
        figure["width"], figure["height"], figure["height"] / (abs(top - bottom) / 1000.0),
        present=frozenset(figure["bones"]),
    )


def _align(
    bones: dict[str, Any], width: int, height: int, px_per_m: float,
    present: frozenset[str] | None = None,
) -> dict[str, Any]:
    """El ajuste de Polaris sobre una figura: `bones` son los centroides que valen de ancla;
    `present`, los huesos que la figura trae (si no se da, los mismos)."""
    model = points()
    body = float(model["body_height_m"])
    zones = model["zones"]
    present = frozenset(bones) if present is None else present
    # Coordenadas de dibujo de Polaris: x desde la izquierda de la imagen, y desde arriba.
    foci = [
        (number, float(item["x"]) + 0.5, body - float(item["y"]), item.get("bone", ""), key)
        for number, (key, item) in enumerate(zones.items(), start=1)
    ]
    anchors = [number for number, *_rest, bone, _key in foci if bone and bone in bones]
    anchored = [zones[key] for number, *_rest, key in foci if number in anchors]
    fit: dict[str, Any] = {
        "superposable": False, "error_px": None, "anchors": len(anchors), "zones": {},
        "outside": {}, "reason": None,
    }
    # Una recta por eje pasa siempre por dos posiciones: con menos de tres distintas el error de
    # las anclas sale nulo por construcción y el umbral no comprobaría nada.
    if min(len({float(item[axis]) for item in anchored}) for axis in ("x", "y")) < MIN_POSITIONS:
        return {**fit, "reason": TOO_FEW_ANCHORS}
    tool = _tool()
    with _LOCK:
        saved = (tool.FOCOS, tool.ANCLAS, tool.VB)
        tool.FOCOS, tool.ANCLAS, tool.VB = foci, anchors, (1.0, body)
        try:
            place, (mean_px, worst_px) = tool.alinea({"huesos": bones}, width, height)
            # Su `fn` lee `VB` del módulo al llamarla: se coloca antes de devolverle el suyo.
            placed = {}
            for _number, x, y, bone, key in foci:
                px, py = place(x, y)
                placed[key] = {
                    "u": round(px / width, 4), "v": round(py / height, 4), "bone": bone or None,
                    "placed_on": BY_FIT,
                }
            origin, across, down = place(0.0, 0.0), place(1.0, 0.0), place(0.0, body)
        except SystemExit as stop:  # así aborta Polaris: anclas de menos o en línea
            return {**fit, "reason": NO_FIT.format(reason=stop.code)}
        finally:
            tool.FOCOS, tool.ANCLAS, tool.VB = saved
    smallest = min(float(item["height_m"]) for item in anchored)
    threshold_px = smallest / 2 * px_per_m
    error = {"mean": round(mean_px, 1), "worst": round(worst_px, 1),
             "threshold": round(threshold_px, 1)}
    # Un ajuste que le da la vuelta al cuerpo (escala negativa en un eje) no coloca nada, por
    # pequeño que le salga el error: las anclas dirían que la figura está en espejo o del revés.
    if not (across[0] > origin[0] and down[1] > origin[1]):
        return {**fit, "error_px": error, "reason": FLIPPED}
    # Modo DIRECTO de Polaris: la zona anclada va al centroide de su hueso, no a donde la deja el
    # ajuste. Solo las anclas: `bones` son los huesos que la figura trae enteros.
    for number, *_rest, bone, key in foci:
        if number in anchors:
            centroid = bones[bone]
            placed[key] = {
                "u": round(float(centroid["u"]), 4), "v": round(float(centroid["v"]), 4),
                "bone": bone, "placed_on": ON_BONE,
            }
    outside = {}
    for key, point in placed.items():
        bone = point["bone"]
        if bone is not None and bone not in present:
            outside[key] = BONE_NOT_IN_STUDY
        elif not (0 <= point["u"] <= 1 and 0 <= point["v"] <= 1):
            outside[key] = OFF_THE_IMAGE
    superposable = mean_px < threshold_px
    return {
        **fit,
        "superposable": superposable,
        "error_px": error,
        "zones": placed,
        "outside": outside if superposable else {},
        "reason": None if superposable else BAD_FIT,
    }


def overlay(
    pain_reports: list[dict[str, Any]], now: dt.datetime | None = None,
    figure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Las zonas con dolor referido en los últimos días, colocadas sobre el esqueleto: el de
    referencia, o la `figure` que se pase (la de `anatomy.subject_skeleton`)."""
    fit = alignment() if figure is None else alignment_on(figure)
    recent: dict[str, dict[str, Any]] = {}
    times = [dt.datetime.fromisoformat(str(item["effective"])) for item in pain_reports]
    now = now or max(times, default=dt.datetime.now(dt.UTC))
    for report, when in zip(pain_reports, times, strict=True):
        if now - when > RECENT:
            continue
        for item in report.get("zones") or []:
            zone = str(item["zone"])
            entry = recent.setdefault(zone, {"reports": 0, "last": None, "intensity": None})
            entry["reports"] += 1
            if entry["last"] is None or when.isoformat() > entry["last"]:
                entry["last"] = when.isoformat()
                entry["intensity"] = item.get("intensity")
    marks = [
        {"zone": zone, "display": i18n.loc(ZONES[zone].display), **fit["zones"][zone], **info}
        for zone, info in sorted(recent.items())
        if zone in fit["zones"] and zone in ZONES and zone not in fit["outside"]
    ] if fit["superposable"] else []
    # El dolor referido en una zona que esta figura no trae no se pinta en otro sitio: se dice.
    # (Sin ajuste que valga no hay zonas fuera ni dentro: lo que se dice entonces es `reason`.)
    outside = [
        {
            "zone": zone, "display": i18n.loc(ZONES[zone].display),
            "reason": i18n.loc(fit["outside"][zone]), **info,
        }
        for zone, info in sorted(recent.items())
        if zone in fit["outside"] and zone in ZONES
    ]
    own = figure is not None and figure.get("source") == OWN_CT
    return {
        "superposable": fit["superposable"],
        "error_px": fit["error_px"],
        "window_days": RECENT.days,
        "marks": marks,
        # Sobre qué figura se ha colocado: la interfaz solo pinta las marcas sobre esa misma.
        "source": OWN_CT if own else REFERENCE,
        "segmentation_index": figure["ledger"]["segmentation_index"] if own and figure else None,
        "anchors": fit["anchors"],
        "reason": _reason(fit["reason"]),
        "outside_study": outside,
    }
