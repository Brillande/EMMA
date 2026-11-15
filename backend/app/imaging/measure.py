"""Medidas ecográficas a partir de los calibres que marca el operador.

Por qué existe: una ecografía sin medida es una imagen que alguien tiene que interpretar, y
en una nave hacia Marte ese alguien no está al otro lado de la radio. Una medida, en cambio,
es un número que entra en la misma línea base personal que el pulso o el sueño, y cuya
evolución se puede vigilar sin radiólogo.

Qué hace y qué no. Convierte puntos en píxeles a milímetros con la calibración que declaró
el propio ecógrafo, y comprueba que la medida está bien planteada: que los puntos caen en
una misma región calibrada, que la vaina del nervio se mide a la profundidad convenida, que
los diámetros de la vejiga son perpendiculares. Una medida mal planteada se **rechaza** con
el motivo; no se degrada en silencio a un número con peor confianza. No segmenta la imagen:
los puntos los pone una persona. La segmentación automática, si llega, tendrá que producir
estos mismos puntos y pasar estas mismas comprobaciones.

Cada parámetro del método declara su respaldo, como los del simulador: `established`,
`contested` o `design` (lo fija el proyecto, sin respaldo bibliográfico). Se exponen en
`/api/imaging/protocols`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.display import number
from app.imaging.dicom import CalibratedRegion

MEASUREMENT_EVIDENCE = ("established", "contested", "design")


@dataclass(frozen=True)
class MethodParameter:
    value: float
    evidence: str
    note: str
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value, "evidence": self.evidence,
            "note": self.note, "source": self.source,
        }


METHOD: dict[str, MethodParameter] = {
    "onsd_depth_mm": MethodParameter(
        3.0, "contested",
        "La vaina se mide 3 mm por detrás del globo. Es la convención de la técnica "
        "transorbital y la que usa la literatura, pero el punto de referencia anatómico "
        "desde el que se cuentan esos 3 mm está en discusión.",
        "Helmke K, Hansen HC. Pediatr Radiol 1996 (PMID 8805599); "
        "Crit Care Med 2025 (PMID 40459386)",
    ),
    "onsd_depth_tolerance_mm": MethodParameter(
        0.5, "design",
        "Cuánto puede separarse la línea de medida de los 3 mm antes de rechazarla. "
        "Sin respaldo bibliográfico: lo fija el proyecto.",
    ),
    "right_angle_tolerance_deg": MethodParameter(
        15.0, "design",
        "Desviación admitida respecto de 90° entre dos ejes que deben ser perpendiculares "
        "(la vaina y el eje del nervio; alto y ancho de la vejiga). Lo fija el proyecto.",
    ),
    "bladder_coefficient": MethodParameter(
        0.57, "established",
        "Alto × ancho × largo × 0,57. Lo fija la definición del código LOINC 15309-8; "
        "cambiarlo y seguir usando el código sería mentir sobre el método. Su exactitud "
        "frente al volumen real no se ha verificado en este proyecto.",
        "LOINC 15309-8; Brunn J, Ruf G. Sonografische Zystometrie, 1980",
    ),
    "min_contour_points": MethodParameter(
        6.0, "design",
        "Puntos mínimos para contornear la sección de la yugular. Con menos, el polígono "
        "recorta demasiado una sección casi elíptica. Lo fija el proyecto.",
    ),
}


# Lo que la tripulación tiene que saber antes de fiarse de la falta de alertas.
# Ver `compliance/clinical-decision-rationale.md`, "Lo que sigue abierto".
ALERTING_NOTE = (
    "Las medidas ecográficas se registran y forman historial, pero todavía no generan "
    "alertas: la línea base personal necesita más lecturas de las que da una ecografía. "
    "Que no haya alerta no significa que la medida sea normal."
)


class MeasurementError(ValueError):
    """La medida no se puede calcular tal como está planteada. El mensaje dice por qué."""


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Annotation:
    """Puntos marcados sobre un fotograma."""

    frame: int
    points: tuple[Point, ...]


@dataclass(frozen=True)
class Measurement:
    key: str
    value: float
    # Lo que justifica el valor: distancias intermedias, profundidad, ángulos.
    details: dict[str, float]


@dataclass(frozen=True)
class MeasureSpec:
    """Una medida del registro: de qué protocolo sale y qué anotaciones exige."""

    name: str
    protocol: str
    display: str
    labels: Mapping[str, int]  # etiqueta -> puntos exactos (0 = contorno, mínimo aparte)
    lateral: bool
    # Qué marcar en cada etiqueta. Lo escribe el backend: la interfaz no redacta texto
    # clínico, lo muestra.
    instructions: Mapping[str, str]

    def key(self, laterality: str | None) -> str:
        if self.lateral:
            if laterality not in ("right", "left"):
                raise MeasurementError("esta medida exige lado: 'right' o 'left'")
            return f"{self.name}-{laterality}"
        if laterality is not None:
            raise MeasurementError("esta medida no tiene lado")
        return self.name


MEASURES: dict[str, MeasureSpec] = {
    spec.name: spec
    for spec in (
        MeasureSpec(
            "onsd", "optic-nerve", "Diámetro de la vaina del nervio óptico",
            {"globe": 1, "sheath": 2}, lateral=True,
            instructions={
                "globe": "Un punto en la pared posterior del globo, donde entra el nervio.",
                "sheath": "Los dos bordes externos de la vaina, en una línea perpendicular "
                          "al nervio y 3 mm por detrás del globo.",
            },
        ),
        MeasureSpec(
            "ijv-csa", "jugular-vein", "Área de sección de la yugular interna",
            {"contour": 0}, lateral=True,
            instructions={
                "contour": "El borde interno de la vena en el corte transversal, punto a "
                           "punto y sin cruzar el trazo. Al menos 6 puntos.",
            },
        ),
        MeasureSpec(
            "bladder-volume", "bladder", "Volumen vesical",
            {"height": 2, "width": 2, "length": 2}, lateral=False,
            instructions={
                "height": "Alto: de la pared anterior a la posterior, en el corte transversal.",
                "width": "Ancho: de pared lateral a pared lateral en el mismo corte, "
                         "perpendicular al alto.",
                "length": "Largo: de la cúpula al cuello vesical, en el corte sagital.",
            },
        ),
    )
}


def measure(
    name: str,
    laterality: str | None,
    annotations: Mapping[str, Annotation],
    regions: Sequence[CalibratedRegion],
    frames: int,
) -> Measurement:
    """Calcula una medida registrada, o explica por qué no se puede."""
    spec = MEASURES.get(name)
    if spec is None:
        raise MeasurementError(f"medida desconocida: {name!r}. Admitidas: {', '.join(MEASURES)}")
    key = spec.key(laterality)
    if not regions:
        raise MeasurementError(
            "el estudio no declara calibración física: se puede ver, no medir en milímetros"
        )
    if set(annotations) != set(spec.labels):
        raise MeasurementError(
            f"'{name}' exige las anotaciones {sorted(spec.labels)}, llegaron {sorted(annotations)}"
        )
    for label, expected in spec.labels.items():
        annotation = annotations[label]
        if not 0 <= annotation.frame < frames:
            raise MeasurementError(f"'{label}': fotograma {annotation.frame} fuera del estudio")
        if expected and len(annotation.points) != expected:
            raise MeasurementError(f"'{label}' exige {expected} puntos")
        if not all(math.isfinite(p.x) and math.isfinite(p.y) for p in annotation.points):
            raise MeasurementError(f"'{label}' tiene coordenadas no finitas")

    if spec.name == "onsd":
        value, details = _onsd(annotations, regions)
    elif spec.name == "ijv-csa":
        value, details = _vein_area(annotations["contour"], regions)
    else:
        value, details = _bladder(annotations, regions)
    return Measurement(key=key, value=round(value, 3), details=details)


# --------------------------------------------------------------------------- #
# Geometría
# --------------------------------------------------------------------------- #


def _region_of(points: Sequence[Point], regions: Sequence[CalibratedRegion]) -> CalibratedRegion:
    """La región calibrada que contiene todos los puntos.

    Dos puntos en regiones distintas —el modo B y un Doppler al lado— no forman una
    distancia: cada región tiene su escala, y mezclarlas da un número sin sentido.
    """
    for region in regions:
        if all(region.x0 <= p.x <= region.x1 and region.y0 <= p.y <= region.y1 for p in points):
            return region
    raise MeasurementError("los puntos no caen dentro de una misma región calibrada")


def _mm(p: Point, region: CalibratedRegion) -> tuple[float, float]:
    return p.x * region.mm_per_px_x, p.y * region.mm_per_px_y


def distance_mm(a: Point, b: Point, region: CalibratedRegion) -> float:
    """Distancia en milímetros con la escala de cada eje. Es lo que valida HC18."""
    (ax, ay), (bx, by) = _mm(a, region), _mm(b, region)
    return math.hypot(bx - ax, by - ay)


def _angle_deg(u: tuple[float, float], v: tuple[float, float]) -> float:
    """Ángulo entre dos direcciones, en [0, 90]: la orientación de un eje no tiene signo."""
    norm = math.hypot(*u) * math.hypot(*v)
    if norm == 0:
        raise MeasurementError("dos puntos coinciden: no definen una dirección")
    cosine = abs(u[0] * v[0] + u[1] * v[1]) / norm
    return math.degrees(math.acos(min(1.0, cosine)))


def _check_right_angle(angle: float, what: str) -> None:
    tolerance = METHOD["right_angle_tolerance_deg"].value
    if abs(90.0 - angle) > tolerance:
        raise MeasurementError(
            f"{what} forman {number(angle, 0)}°: tienen que ser perpendiculares "
            f"(±{number(tolerance, 0)}°)"
        )


def _onsd(
    annotations: Mapping[str, Annotation], regions: Sequence[CalibratedRegion]
) -> tuple[float, dict[str, float]]:
    """Diámetro de la vaina a 3 mm tras el globo, perpendicular al eje del nervio."""
    if annotations["globe"].frame != annotations["sheath"].frame:
        raise MeasurementError("el globo y la vaina tienen que marcarse en el mismo fotograma")
    globe = annotations["globe"].points[0]
    edge_a, edge_b = annotations["sheath"].points
    region = _region_of([globe, edge_a, edge_b], regions)

    diameter = distance_mm(edge_a, edge_b, region)
    middle = Point((edge_a.x + edge_b.x) / 2, (edge_a.y + edge_b.y) / 2)
    depth = distance_mm(globe, middle, region)
    target, tolerance = METHOD["onsd_depth_mm"].value, METHOD["onsd_depth_tolerance_mm"].value
    if abs(depth - target) > tolerance:
        raise MeasurementError(
            f"la vaina se ha medido a {number(depth, 1)} mm del globo: tiene que ser a "
            f"{number(target, 0)} ± {number(tolerance, 1)} mm"
        )
    (gx, gy), (mx, my) = _mm(globe, region), _mm(middle, region)
    (ax, ay), (bx, by) = _mm(edge_a, region), _mm(edge_b, region)
    angle = _angle_deg((mx - gx, my - gy), (bx - ax, by - ay))
    _check_right_angle(angle, "la línea de la vaina y el eje del nervio")
    return diameter, {"depth_mm": round(depth, 3), "angle_deg": round(angle, 1)}


def _bladder(
    annotations: Mapping[str, Annotation], regions: Sequence[CalibratedRegion]
) -> tuple[float, dict[str, float]]:
    """Volumen por alto × ancho × largo × 0,57 (LOINC 15309-8), en cm³.

    Alto y ancho salen del corte transversal y el largo del sagital, así que pueden venir
    de fotogramas distintos. Si alto y ancho están en el mismo fotograma se comprueba que
    son perpendiculares, como exige la definición del código.
    """
    lengths: dict[str, float] = {}
    for label in ("height", "width", "length"):
        a, b = annotations[label].points
        lengths[label] = distance_mm(a, b, _region_of([a, b], regions))
        if lengths[label] == 0:
            raise MeasurementError(f"'{label}': los dos puntos coinciden")
    details = {f"{label}_mm": round(value, 3) for label, value in lengths.items()}

    height, width = annotations["height"], annotations["width"]
    if height.frame == width.frame:
        region = _region_of([*height.points, *width.points], regions)
        (h0x, h0y), (h1x, h1y) = (_mm(p, region) for p in height.points)
        (w0x, w0y), (w1x, w1y) = (_mm(p, region) for p in width.points)
        angle = _angle_deg((h1x - h0x, h1y - h0y), (w1x - w0x, w1y - w0y))
        _check_right_angle(angle, "el alto y el ancho")
        details["height_width_angle_deg"] = round(angle, 1)

    cubic_mm = lengths["height"] * lengths["width"] * lengths["length"]
    return cubic_mm * METHOD["bladder_coefficient"].value / 1000.0, details


def _vein_area(
    contour: Annotation, regions: Sequence[CalibratedRegion]
) -> tuple[float, dict[str, float]]:
    """Área del polígono que contornea la sección de la vena (fórmula del lazo), en mm²."""
    minimum = int(METHOD["min_contour_points"].value)
    points = contour.points
    if len(points) < minimum:
        raise MeasurementError(f"el contorno necesita al menos {minimum} puntos")
    region = _region_of(points, regions)
    if _self_intersects(points):
        raise MeasurementError("el contorno se cruza consigo mismo: su área no es la de la vena")
    mm = [_mm(p, region) for p in points]
    twice_area = sum(
        x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(mm, mm[1:] + mm[:1], strict=True)
    )
    area = abs(twice_area) / 2
    if area == 0:
        raise MeasurementError("el contorno no encierra área")
    return area, {"contour_points": float(len(points))}


def _self_intersects(points: Sequence[Point]) -> bool:
    """¿Se cruzan dos lados no contiguos del polígono? Cuadrático, con pocos puntos basta."""
    edges = list(zip(points, [*points[1:], points[0]], strict=True))
    count = len(edges)
    for i in range(count):
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue  # lados contiguos: comparten un vértice
            if _segments_cross(*edges[i], *edges[j]):
                return True
    return False


def _segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    def orient(p: Point, q: Point, r: Point) -> float:
        return (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x)

    d1, d2 = orient(c, d, a), orient(c, d, b)
    d3, d4 = orient(a, b, c), orient(a, b, d)
    return (d1 * d2 < 0) and (d3 * d4 < 0)
