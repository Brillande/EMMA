"""Zonas del cuerpo y tipos de dolor que el tripulante puede elegir.

LISTAS CERRADAS, DECLARADAS AQUÍ
--------------------------------
La interfaz no redacta texto clínico (CLAUDE.md, invariante 7): los nombres de las zonas y
de los tipos de dolor salen de este módulo y la consola los muestra tal cual. Y no hay
texto libre: una descripción libre del dolor no se puede seguir en el tiempo ni comparar
entre dos informes, y es la vía por la que entra lenguaje de diagnóstico.

POR QUÉ LAS ZONAS NO USAN SNOMED CT
-----------------------------------
SNOMED CT codifica estructuras anatómicas con precisión clínica, pero estas zonas son
regiones de un mapa corporal pensado para señalar con un dedo, no estructuras anatómicas:
"lumbar" es donde el tripulante toca, no la columna lumbar. Etiquetarlas con un código de
estructura diría más de lo que el informe sabe. Se identifican con el sistema propio de
EMMA, igual que los indicadores propios de misión (`app/ingest/codes.py`), y no se
adoptará un código SNOMED sin comprobarlo antes en su ficha oficial.

LATERALIDAD DEL PACIENTE, NO DE QUIEN MIRA
------------------------------------------
"left" es el lado izquierdo **del tripulante**. Un mapa corporal visto de frente pone la
izquierda del paciente a la derecha de la pantalla: confundirlo es apuntar el lado
equivocado, el mismo error que la cirugía de sitio equivocado. La interfaz lo prueba.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core import i18n

PAIN_ZONE_SYSTEM = "https://emma.mission/codes/pain-zone"

Side = Literal["left", "right"]

# Escala numérica verbal de 0 a 10: enteros, como la pregunta que se hace en la clínica.
MIN_INTENSITY = 0
MAX_INTENSITY = 10


@dataclass(frozen=True)
class PainZone:
    key: str
    display: str
    # None para las zonas de la línea media (cabeza, lumbar...).
    side: Side | None = None


@dataclass(frozen=True)
class PainCharacter:
    key: str
    display: str


_CENTRAL: tuple[PainZone, ...] = (
    PainZone("head", "Cabeza"),
    PainZone("face", "Cara"),
    PainZone("neck", "Cuello"),
    PainZone("chest", "Tórax"),
    PainZone("upper-back", "Espalda alta"),
    PainZone("abdomen", "Abdomen"),
    PainZone("lower-back", "Zona lumbar"),
    PainZone("pelvis", "Pelvis"),
)

# Zonas pares: (clave, nombre). Se generan las dos, con el lado en la clave y en el nombre.
_PAIRED: tuple[tuple[str, str], ...] = (
    ("shoulder", "Hombro"),
    ("upper-arm", "Brazo"),
    ("elbow", "Codo"),
    ("forearm", "Antebrazo"),
    ("hand", "Mano"),
    ("hip", "Cadera"),
    ("thigh", "Muslo"),
    ("knee", "Rodilla"),
    ("lower-leg", "Pierna"),
    ("foot", "Pie"),
)

_SIDE_DISPLAY: dict[Side, str] = {"left": "izquierda", "right": "derecha"}
# "Hombro izquierdo", "Mano izquierda": el adjetivo concuerda con el nombre.
_FEMININE = frozenset({"hand", "hip", "knee", "lower-leg"})


def _side_word(base: str, side: Side) -> str:
    word = _SIDE_DISPLAY[side]
    return word if base in _FEMININE else word[:-1] + "o"


ZONES: dict[str, PainZone] = {
    zone.key: zone
    for zone in (
        *_CENTRAL,
        *(
            PainZone(f"{base}-{side}", f"{display} {_side_word(base, side)}", side)
            for base, display in _PAIRED
            for side in ("left", "right")
        ),
    )
}

CHARACTERS: dict[str, PainCharacter] = {
    character.key: character
    for character in (
        PainCharacter("sharp", "Punzante"),
        PainCharacter("dull", "Sordo"),
        PainCharacter("burning", "Quemante"),
        PainCharacter("pressing", "Opresivo"),
        PainCharacter("throbbing", "Pulsátil"),
        PainCharacter("cramping", "Calambre"),
        PainCharacter("tingling", "Hormigueo"),
    )
}

# EL INGLÉS DE LOS NOMBRES (2026-11-15, dos idiomas con selector). Las claves son lo que se firma
# en el ledger y no se traducen; el nombre se resuelve al leer. `display` sigue siendo el
# castellano —lo usan el asistente, que casa lo que oye con él, y el borrador— y quien lo enseña
# en pantalla lo pide con `i18n.loc`. En inglés el lado va delante («Left shoulder»), así que
# cada zona par se nombra entera, no por partes. Una zona o un tipo nuevos sin inglés no arrancan.
_CENTRAL_ENGLISH: dict[str, str] = {
    "head": "Head",
    "face": "Face",
    "neck": "Neck",
    "chest": "Chest",
    "upper-back": "Upper back",
    "abdomen": "Abdomen",
    "lower-back": "Lower back",
    "pelvis": "Pelvis",
}
_PAIRED_ENGLISH: dict[str, str] = {
    "shoulder": "shoulder",
    "upper-arm": "upper arm",
    "elbow": "elbow",
    "forearm": "forearm",
    "hand": "hand",
    "hip": "hip",
    "thigh": "thigh",
    "knee": "knee",
    "lower-leg": "lower leg",
    "foot": "foot",
}
_SIDE_ENGLISH: dict[Side, str] = {"left": "Left", "right": "Right"}
_CHARACTERS_ENGLISH: dict[str, str] = {
    "sharp": "Sharp",
    "dull": "Dull",
    "burning": "Burning",
    "pressing": "Pressing",
    "throbbing": "Throbbing",
    "cramping": "Cramping",
    "tingling": "Tingling",
}


def _english_name(zone: PainZone) -> str:
    if zone.side is None:
        return _CENTRAL_ENGLISH[zone.key]
    return f"{_SIDE_ENGLISH[zone.side]} {_PAIRED_ENGLISH[zone.key.removesuffix(f'-{zone.side}')]}"


i18n.en_many({zone.display: _english_name(zone) for zone in ZONES.values()})
i18n.en_many({item.display: _CHARACTERS_ENGLISH[item.key] for item in CHARACTERS.values()})


def validate_zones(zones: list[tuple[str, int, list[str]]]) -> list[str]:
    """Problemas de un informe, en frases que la consola muestra tal cual. Vacía si vale.

    `zones` es (zona, intensidad, tipos). Una zona repetida es un informe ambiguo: dos
    intensidades para el mismo sitio. Una zona sin dolor (0) no es una zona marcada: para
    decir "no me duele nada" está el informe sin zonas.
    """
    problems: list[str] = []
    seen: set[str] = set()
    for zone, intensity, characters in zones:
        if zone not in ZONES:
            problems.append(f"zona desconocida: {zone!r}")
            continue
        name = ZONES[zone].display
        if zone in seen:
            problems.append(f"{name}: la zona aparece dos veces")
        seen.add(zone)
        if not MIN_INTENSITY < intensity <= MAX_INTENSITY:
            problems.append(
                f"{name}: la intensidad de una zona marcada va de 1 a {MAX_INTENSITY}"
            )
        unknown = [c for c in characters if c not in CHARACTERS]
        if unknown:
            problems.append(f"{name}: tipo de dolor desconocido: {', '.join(unknown)}")
        if len(set(characters)) != len(characters):
            problems.append(f"{name}: un tipo de dolor aparece dos veces")
    return problems


def describe() -> dict[str, object]:
    """Lo que la consola necesita para pintar el mapa y el formulario."""
    return {
        "system": PAIN_ZONE_SYSTEM,
        "scale": {"min": MIN_INTENSITY, "max": MAX_INTENSITY, "unit": "{score}"},
        "zones": [
            {"key": zone.key, "display": i18n.loc(zone.display), "side": zone.side}
            for zone in ZONES.values()
        ],
        "characters": [
            {"key": character.key, "display": i18n.loc(character.display)}
            for character in CHARACTERS.values()
        ],
    }
