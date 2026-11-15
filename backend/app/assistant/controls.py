"""Pulsar por voz un botón que está en pantalla: «abdomen hígado 1 de volúmenes 3D».

Por qué existe: el asistente abría pestañas y paneles pero no pulsaba nada dentro de ellos, y
para cargar un TAC de ejemplo o cambiar de vista había que soltar la voz e ir al ratón (el
usuario, 2026-11-06). Los botones no están en ningún inventario del backend: cambian con cada
panel y con los datos (un TAC de ejemplo por cada muestra). Por eso la consola manda, con cada
turno, los rótulos de los botones que tiene a la vista y si cada uno guarda algo; aquí solo se
elige cuál nombra la frase, entre esos y ninguno más.

Qué no hace: pulsar. Eso lo hace la consola (`frontend/src/assistant/intents.ts`), y un botón que
guarda algo no se pulsa sin «confirmo» (decisión del usuario del 2026-11-06: «confirmar solo si
guarda»). Lo que guarde lo guarda el propio botón, por su ruta de siempre y su ledger
(invariante 4): el asistente no firma nada.

Determinista, sin modelo: una palabra mal oída puede, como mucho, proponer otro botón; uno que
guarde, se ve y se dice antes de pulsarlo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.assistant.catalog import plain
from app.core import i18n

# Verbos de pulsar. «Abre» no: abre pestañas y paneles, y un botón que se llamara como un panel
# («Radiación») le quitaría su sitio.
_PRESS = re.compile(
    r"\b(?:puls\w*|dale|da(?:le)? a|toca\w*|aprieta\w*|presiona\w*|clic\w*|carg\w*|"
    r"elig\w*|escog\w*|selecciona\w*|marca\w*|usa)\b"
)
# Palabras que no distinguen un rótulo de otro.
_FILLER = frozenset({
    "de", "del", "la", "el", "los", "las", "un", "una", "y", "a", "en", "al", "con", "por", "o",
})
_NUMBERS = {"uno": "1", "una": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5",
            "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10",
            "primero": "1", "primera": "1", "segundo": "2", "segunda": "2", "tercero": "3",
            "tercera": "3"}
# Lo mismo en inglés. Los verbos, por sus formas enteras y no por su comienzo: «press» es el
# comienzo de «pressure» («how is my blood pressure?» no pulsa nada), «tap» el de «tape» y «load»
# va dentro de «workload». «Open» y «show» no, como «abre»: abren pestañas y paneles. «Check»
# tampoco: «check my alerts» pide leerlas, no pulsar un botón que se llame «Alerts».
_PRESS_EN = re.compile(
    r"\b(?:press(?:es|ed|ing)?|click(?:s|ed|ing)?(?: on)?|tap(?:s|ped|ping)?(?: on)?|"
    r"push(?:es|ed|ing)?|hit|select(?:s|ed|ing)?|choose|pick|load(?:s|ed|ing)?|tick|use)\b"
)
_FILLER_EN = frozenset({
    "of", "the", "a", "an", "and", "to", "in", "on", "at", "with", "for", "by", "or",
})
_NUMBERS_EN = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
               "seven": "7", "eight": "8", "nine": "9", "ten": "10",
               "first": "1", "second": "2", "third": "3"}
MAX_CONTROLS = 200
MAX_LABEL = 120


@dataclass(frozen=True)
class Control:
    """Un botón a la vista: su rótulo tal cual y si pulsarlo guarda algo."""

    label: str
    writes: bool


def _press() -> re.Pattern[str]:
    """Los verbos de pulsar del idioma de la petición."""
    return _PRESS_EN if i18n.current() == "en" else _PRESS


def _tokens(text: str) -> frozenset[str]:
    words = plain(text).split()
    if i18n.current() == "en":
        return frozenset(_NUMBERS_EN.get(word, word) for word in words
                         if word not in _FILLER_EN)
    return frozenset(_NUMBERS.get(word, word) for word in words if word not in _FILLER)


@dataclass(frozen=True)
class Pick:
    """El botón que nombra la frase, o los que empatan si no se puede saber cuál."""

    control: Control | None
    tied: tuple[Control, ...] = ()


def pick(text: str, controls: list[Control]) -> Pick | None:
    """El botón que nombra `text`, o None si no nombra ninguno.

    Nombra un botón si dice todas las palabras de su rótulo (sin las de relleno, y «uno» vale
    «1»). Con un verbo de pulsar basta un rótulo de una palabra; sin él hacen falta dos, para que
    una palabra suelta de otra orden no pulse nada. Gana el de más palabras; un empate es una
    pregunta, no un botón.
    """
    said = _tokens(text)
    verb = bool(_press().search(plain(text)))
    best: list[tuple[int, Control]] = []
    seen: set[str] = set()
    for control in controls:
        words = _tokens(control.label)
        key = plain(control.label)
        if not words or key in seen:
            continue
        seen.add(key)
        if words <= said and (verb or len(words) >= 2):
            best.append((len(words), control))
    if not best:
        return _partial(said, verb, controls)
    top = max(size for size, _ in best)
    winners = tuple(control for size, control in best if size == top)
    if len(winners) == 1:
        return Pick(winners[0])
    return Pick(None, winners)


def _partial(said: frozenset[str], verb: bool, controls: list[Control]) -> Pick | None:
    """Sin rótulo entero: los botones cuyo rótulo lleva todo lo dicho («pulsa abdomen hígado»).

    Solo con verbo de pulsar. Uno solo, ese (si guarda, se
    pregunta igual antes de pulsarlo); varios, se pregunta cuál.
    """
    press = _press()
    content = frozenset(word for word in said if not press.search(f" {word} "))
    if not verb or not content:
        return None
    found: dict[str, Control] = {}
    for control in controls:
        if content <= _tokens(control.label):
            found.setdefault(plain(control.label), control)
    if not found:
        return None
    if len(found) == 1:
        return Pick(next(iter(found.values())))
    return Pick(None, tuple(found.values()))


def reply(found: Pick) -> tuple[str, bool]:
    """Lo que se dice y si hace falta «confirmo» antes de pulsar."""
    if found.control is None:
        names = ", ".join(f"«{control.label}»" for control in found.tied[:4])
        return i18n.tr(f"Hay varios botones que se llaman así: {names}. ¿Cuál pulso?",
                       f"Several buttons have that name: {names}. Which one do I press?"), False
    if found.control.writes:
        # Las palabras de confirmar son las que escucha la consola en cada idioma.
        return (i18n.tr(f"¿Pulso «{found.control.label}»? Guarda en el registro: diga «confirmo» o "
                        "«cancela».",
                        f"Shall I press «{found.control.label}»? It saves to the record: say "
                        "«confirm» or «cancel»."), True)
    return i18n.tr(f"Pulso «{found.control.label}».",
                   f"Pressing «{found.control.label}»."), False
