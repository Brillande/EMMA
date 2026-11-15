"""Notas de Tierra a bordo: lo que Tierra puede decir a la tripulación, y lo que no.

POR QUÉ EXISTE
--------------
La conversación de ideación (`docs/contexto/conversacion-ideacion-v1.md`) dibuja el nodo de salud
de a bordo con una línea de ida y vuelta a Tierra: «Cuando existe comunicación con Tierra,
sincroniza datos, recibe nuevos modelos/protocolos y permite supervisión médica» (L182) y
«↕ optional synchronization» (L190), con el sistema de cuidados de la tripulación de la ISS
apoyado desde Tierra por sus controladores biomédicos y cirujanos de vuelo (L510). En EMMA solo
existía la mitad de bajada: la consola de Tierra lee, con el retardo aplicado, y `notify_ground`
dice cuándo algo de a bordo merece que Tierra lo sepa. Nada iba de Tierra a bordo (decisión del
usuario, 2026-10-26).

LO QUE ES
---------
Una nota corta, firmada en el registro por la consola de Tierra, con el nombre de quien la firma
(declarado, sin autenticar, como toda acción de consola) y la hora de firma. A bordo se ve
**solo cuando ha pasado un tiempo de luz** desde que se firmó: el mismo corte que la consola de
Tierra aplica a lo que baja (`arrivalCut` en `frontend/src/lib/crew.ts`), al revés.

LO QUE NO ES
------------
**No es una orden médica (invariante 7).** Una nota informa o pregunta; nunca prescribe. Por eso
hay dos clases y ninguna más: `information` y `question` (una pregunta lleva su «?»). El texto
pasa por el filtro de lenguaje de EMMA (`app/text_guard.py`: dosis, diagnóstico, certeza, orden y
absolutos, todo lo que ya bloquea) y, además, por las formas de mandato de abajo (`MANDATE`), que
el filtro general no caza porque un borrador no las escribe y una persona en Tierra sí: «debe»,
«tiene que», «hay que», «es obligatorio», «ordeno» y el imperativo de cortesía de los verbos con
que se da una pauta («tome», «repita», «evite»…). Escritas dentro de una pregunta no cuentan:
«¿Puede repetir la medida?» pasa, «Repita la medida» no.

LÍMITE, dicho para no dar falsa confianza: son patrones. Una prescripción en tono suave y sin
palabras gatillo se escapa, y alguna frase inocente se rechaza («dosis» de radiación, «1 g» de
gravedad: los mismos falsos positivos que ya documenta el filtro). La barrera de fondo es otra:
la nota no toca nada de lo que decide. No es una observación, no entra en el análisis ni en
ninguna alerta, no cambia ningún nivel ni `rules_version`; la tripulación la lee y decide.
"""

from __future__ import annotations

import re

from app import text_guard
from app.core import i18n

GROUND_NOTE_KINDS: dict[str, str] = {
    "information": "información",
    "question": "pregunta",
}
i18n.en_many({
    GROUND_NOTE_KINDS["information"]: "information",
    GROUND_NOTE_KINDS["question"]: "question",
})
# Una nota se lee en un panel de la consola de tripulación, no es un informe.
MAX_TEXT = 600

# Formas de mandato: se buscan sobre el texto normalizado (sin tildes, en minúsculas) y fuera de
# las preguntas. El imperativo va solo en la forma de cortesía (usted, ustedes), que es la de una
# pauta escrita, con o sin pronombre pegado («tómese», «repítala», «evítelo»); la de tú choca con
# el presente («toma» es también «la toma de presión»). Y solo de los verbos con que se da una
# pauta: el de cortesía es también el subjuntivo, y «cuando empiece la EVA» o «cuando vuelva el
# enlace» no mandan nada. «Tiene que ver» tampoco manda.
_PAUTA = (
    "tome|tomen|haga|hagan|aplique|apliquen|repita|repitan|evite|eviten|use|usen|utilice|"
    "utilicen|beba|beban|ingiera|ingieran|descanse|descansen|interrumpa|interrumpan|retire|"
    "retiren|deje|dejen|duerma|duerman|mida|midan|hidrate|hidraten|vigile|vigilen"
)
# El imperativo de pauta con hasta dos pronombres pegados («tómese», «tómeselo», «hágaselo»). Solo
# lo tapa una pregunta abierta con «¿»: «Repita la medida?» sin «¿» es una orden con un «?» al
# final, no una pregunta (revisión de código, 2026-10-26). Se queda aquí y no en el filtro general:
# esas formas son a diario subjuntivo en los textos de EMMA («no dice que se use en vuelo»), y
# el arranque se detendría (§5.39.21 de `compliance/hmi-state-of-the-art.md`).
_IMPERATIVE = r"\b(?:" + _PAUTA + r")" + text_guard.ATTACHED_PRONOUNS + r"\b"
MANDATE: tuple[str, ...] = (
    r"\bdebe(?:s|n)?\b",
    r"\bdebera(?:s|n)?\b",
    r"\btiene(?:s|n)? que\b(?! ver\b)",
    r"\bhay que\b",
    r"\bobligatori\w*\b",
    r"\bes (?:necesario|imprescindible|preciso|obligado) que\b",
    r"\b(?:ordeno|ordenamos|exijo|exigimos|prohibo|prohibimos)\b",
    _IMPERATIVE,
)
# El imperativo se busca aparte (ver `_IMPERATIVE`): solo lo tapa una pregunta abierta con «¿».
_MANDATE_COMPILED = tuple(re.compile(pattern) for pattern in MANDATE if pattern != _IMPERATIVE)
_IMPERATIVE_COMPILED = re.compile(_IMPERATIVE)

# Lo que la nota es y lo que no, en las palabras con que lo enseñan las dos consolas.
BASIS = (
    "Una nota de Tierra informa o pregunta; no es una orden médica. Llega a bordo un tiempo de "
    "luz después de firmarse. No toca ningún cálculo: no es una lectura, no cambia ningún nivel "
    "ni ninguna alerta, y quien la lee decide."
)
REFUSED = (
    "Se rechaza, con el motivo: lo que el filtro de lenguaje de EMMA no deja decir (dosis y "
    "fármacos, diagnósticos, certezas, órdenes y tratamientos, absolutos) y las formas de mandato "
    "(«debe», «tiene que», «hay que», «es obligatorio», «repita», «tome»…) fuera de una pregunta. "
    "«¿Puede repetir la medida?» pasa; «Repita la medida» no. Una pregunta lleva su «?»."
)
# El inglés de lo que enseñan las dos consolas, registrado para que quien lo sirve
# (`api/ground_notes.py`) lo pase por `i18n.loc`.
# Las formas de mandato se citan en castellano: son las que el filtro busca.
i18n.en(
    BASIS,
    "A note from Earth informs or asks; it is not a medical order. It arrives on board one "
    "light time after it is signed. It does not touch any calculation: it is not a reading, it "
    "does not change any level or any alert, and whoever reads it decides.",
)
i18n.en(
    REFUSED,
    "It is rejected, with the reason: what the EMMA language filter does not allow (doses and "
    "drugs, clinical verdicts, certainties, orders and treatments, absolutes) and mandate "
    "forms («debe», «tiene que», «hay que», «es obligatorio», «repita», «tome»…) outside a "
    "question. «¿Puede repetir la medida?» passes; «Repita la medida» does not. A question "
    "carries its «?».",
)


def mandate_findings(text: str) -> list[str]:
    """Las formas de mandato del texto, fuera de sus preguntas. Lista vacía = ninguna.

    Qué es una pregunta lo dice el filtro general (`text_guard.stated`), en un solo sitio.
    """
    plain = text_guard.normalize(text)
    said = text_guard.stated(plain)
    found = [match.group(0) for pattern in _MANDATE_COMPILED for match in pattern.finditer(said)]
    unopened = text_guard.outside_opened_questions(plain)
    return found + [match.group(0) for match in _IMPERATIVE_COMPILED.finditer(unopened)]


def problem(kind: str, text: str, signed_by: str) -> str | None:
    """Por qué no se puede firmar (o no se enseña) una nota; `None` si se puede.

    Una sola regla para quien escribe (`ObservationStore.record_ground_note`) y para quien lee lo
    firmado (`api/ground_notes`): una nota firmada por fuera de la API no vale más que una firmada
    por ella, y una que el filtro vigente rechazaría no se enseña.
    """
    if kind not in GROUND_NOTE_KINDS:
        return f"clase de nota desconocida: {kind!r}; una de {tuple(GROUND_NOTE_KINDS)}"
    body = text.strip()
    if not any(char.isalpha() for char in body):
        return "una nota de Tierra dice algo con palabras"
    if len(body) > MAX_TEXT:
        return f"una nota de Tierra tiene como mucho {MAX_TEXT} caracteres"
    if not any(char.isalpha() for char in signed_by):
        return "una nota de Tierra la firma una persona con nombre"
    if kind == "question" and "?" not in body:
        return "una pregunta lleva su «?»"
    blocked = text_guard.check(body)
    if blocked:
        found = "; ".join(f"{item.category}: «{item.match}»" for item in blocked)
        return f"el texto no pasa el filtro de lenguaje (invariante 7) — {found}"
    mandates = mandate_findings(body)
    if mandates:
        found = "; ".join(f"«{item}»" for item in mandates)
        return (
            "una nota de Tierra informa o pregunta, no da órdenes: forma de mandato fuera de una "
            f"pregunta — {found}"
        )
    return None
