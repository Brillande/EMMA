# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cotejo de presencia y ausencia: lo que el borrador dice de un signo, contra lo anotado.

Por qué existe: la comprobación de cifras (`draft.unsupported_numbers`) no ve las palabras. Un
borrador puede escribir "no se observa líquido libre" sin una sola cifra, con el signo sin
anotar o anotado como "no valorable". Eso convierte "no se pudo ver" en "no está", que es el
error más caro de una ecografía: una ausencia inventada tranquiliza a quien la lee.

Incorpora código de Polaris (github.com/BeyondTheProtocol/polaris @ 7bf47257, AGPL-3.0-or-later,
© 2026 la autora de Polaris, «Beyond the Protocol»), de `tools/cotejo_invariante.py`: los
léxicos `_AUSENCIA` y `_PRESENCIA`, la negación `_NEG_RE` y la lógica de sentido de
`afirma_estado_alteracion()` (un verbo de presencia negado cuenta como ausencia; con señales de
los dos sentidos, "ambiguo"). Cambios respecto al original (AGPL §5a):
  * Allí la afirmación es de estado de una alteración genética y se reconoce por la forma de un
    símbolo de gen; aquí se reconoce porque nombra un signo del protocolo del estudio.
  * Se quitan los términos genómicos ("wild-type", "en el perfil", "mutad", "amplificad"…) y se
    añaden los valores de los signos de EMMA ("visto", "aisladas", "múltiples", "se observa").
  * Allí la afirmación se coteja contra un informe primario con fuente y fecha; aquí contra los
    hallazgos firmados del propio estudio.
  * "No valorable" se aparta antes de decidir el sentido: no es una ausencia, es lo contrario.
La regla que se conserva tal cual: una ausencia no se afirma si no está anotada. Se dice "no
anotado", nunca "no existe".

SIGUE ADAPTADO, NO COPIADO (regla del proyecto: copiar Polaris literal y decidir los cambios; esta
es una divergencia pendiente de decisión, `docs/polaris-divergencias.md`). El original
`afirma_estado_alteracion()` solo reconoce una afirmación si nombra una alteración o un símbolo de
gen: con las frases de una ecografía ("no se observa líquido libre") devuelve `(False, None)`, y
llamarlo apagaría la barrera contra ausencias inventadas (lo demuestran `tests/test_cotejo.py` y
los mutantes de `tests/mutants/cotejo.json`).

LÍMITE: se coteja por signo en todo el estudio, no ventana por ventana. "Ausente" anotado en una
ventana deja pasar "no se observa" aunque en otra esté presente; eso lo sigue cubriendo la firma
humana, que lee el borrador junto a los hallazgos.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.imaging.protocols import Protocol
from app.text_guard import normalize

# Valores de signo que son una afirmación de ausencia o de presencia. Los demás (p. ej. la
# ecogenicidad "mayor/igual/menor") no dicen si algo está o no.
_ABSENT_VALUES = frozenset({"ausente", "ninguna", "no-visto"})
_PRESENT_VALUES = frozenset({"presente", "aisladas", "multiples", "visto"})

# De Polaris `_AUSENCIA`, sin genómica, sin tildes (se busca sobre texto normalizado).
_ABSENCE = (
    "no esta", "no aparece", "no presente", "ausente", "ausencia", "negativ", "sin ",
    "no se detect", "no detectad", "no hay", "no figura", "no consta", "no presenta",
    "no muestra", "descartad", "excluid", "no observ", "no se observ", "no se visualiz",
    "no se encontr", "no encontrad", "no se identific", "ningun", "limpio", "normal para",
    "no visto", "no se ve",
)
# De Polaris `_PRESENCIA`, sin genómica, más los valores y verbos de la ecografía.
_PRESENCE = (
    "presente", "positiv", "detectad", "se detect", "presenta", "confirmad", "hallazgo",
    "encontrad", "consta", "se observ", "observad", "se visualiz", "visualizad", "se ve ",
    "visto", "aislad", "multiple",
)
# De Polaris `_NEG_RE`: una negación justo antes de un verbo de presencia lo vuelve ausencia.
_NEGATION_BEFORE = re.compile(r"\b(no|sin|nunca|jamas|ningun|ninguna|ni)\b\s*\S*$")
_ANY_NEGATION = re.compile(r"\b(no|sin|nunca|jamas|ningun|ninguna|ni)\b")
_NOT_ASSESSABLE = re.compile(r"\bno\s+(?:es\s+|fue\s+|ha sido\s+)?valorabl\w*|\bsin\s+valorar\b")
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")


def sense(sentence: str) -> str | None:
    """'presencia', 'ausencia', 'ambiguo' o None, de una frase ya normalizada.

    Portado de `afirma_estado_alteracion()`: la presencia solo cuenta si no va negada.
    """
    text = _NOT_ASSESSABLE.sub(" ", sentence)
    absence = any(term in text for term in _ABSENCE) or bool(_ANY_NEGATION.search(text))
    presence = False
    for term in _PRESENCE:
        for match in re.finditer(re.escape(term), text):
            if _NEGATION_BEFORE.search(text[max(0, match.start() - 12):match.start()]):
                continue
            presence = True
            break
        if presence:
            break
    if absence and not presence:
        return "ausencia"
    if presence and not absence:
        return "presencia"
    if presence and absence:
        return "ambiguo"
    return None


def unannotated_claims(
    text: str, protocol: Protocol | None, annotated: Iterable[dict[str, Any]]
) -> list[str]:
    """Frases del borrador que afirman presencia o ausencia de un signo sin anotación que lo diga.

    Las preguntas no afirman nada y no se cotejan.
    """
    if protocol is None:
        return []
    names: dict[str, str] = {}
    for view in protocol.views:
        for sign in view.signs:
            if set(sign.values) & (_ABSENT_VALUES | _PRESENT_VALUES):
                names[normalize(sign.display)] = sign.key
    values: dict[str, set[str]] = {}
    for record in annotated:
        for signs in dict(record.get("findings") or {}).values():
            for key, value in dict(signs).items():
                values.setdefault(str(key), set()).add(str(value))

    problems: list[str] = []
    for match in _SENTENCE.finditer(normalize(text)):
        sentence = match.group(0).strip()
        if not sentence or sentence.endswith("?"):
            continue
        for name, key in names.items():
            if name not in sentence:
                continue
            said = sense(sentence)
            # "No valorable" no está ni entre los valores de ausencia ni entre los de presencia:
            # por eso no respalda ni una cosa ni la otra. (Restarlo aquí era redundante: lo
            # destapó una campaña de mutantes, `tests/mutants/cotejo.json`.)
            recorded = values.get(key, set())
            has_absent = bool(recorded & _ABSENT_VALUES)
            has_present = bool(recorded & _PRESENT_VALUES)
            if said == "ausencia" and not has_absent:
                problems.append(f"afirma la ausencia de «{name}» sin que esté anotada")
            elif said == "presencia" and not has_present:
                problems.append(f"afirma la presencia de «{name}» sin que esté anotada")
            elif said == "ambiguo" and not (has_absent or has_present):
                problems.append(f"habla de «{name}» sin que esté anotado")
    return problems


def annotated_from_facts(
    protocol: Protocol | None, readable: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Los hallazgos de los HECHOS (con nombres legibles) vueltos a claves del protocolo.

    Así se coteja contra lo mismo que ve el modelo, sin una segunda lectura del almacén.
    """
    if protocol is None:
        return []
    views = {view.display: view for view in protocol.views}
    out: list[dict[str, Any]] = []
    for item in readable:
        findings: dict[str, dict[str, str]] = {}
        for view_name, signs in dict(item.get("signos") or {}).items():
            view = views.get(view_name)
            if view is None:
                continue
            by_display = {sign.display: sign for sign in view.signs}
            for sign_name, value_name in dict(signs).items():
                sign = by_display.get(sign_name)
                if sign is None:
                    continue
                keys = [key for key, shown in sign.values.items() if shown == value_name]
                if keys:
                    findings.setdefault(view.key, {})[sign.key] = keys[0]
        out.append({"findings": findings})
    return out
