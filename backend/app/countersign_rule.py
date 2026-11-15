# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cuándo se rechaza la segunda firma de una decisión de alto riesgo por lo que cita.

Por qué existe: hasta el 2026-10-13 se podía contrafirmar citando un informe cuya frase no se
localizaba, y la API aceptaba una contrafirma que no declaraba haber visto la frase (el asiento
quedaba con `vista: false`). La segunda firma existe para que otra persona LEA aquello en lo que
se apoya la decisión; firmar sobre una cita que no está, o sin haberla leído, la vacía. Decisión
del usuario (2026-10-13): las dos cosas se rechazan, y no se escribe ningún asiento.

Quedaba un hueco, declarado: solo se puede cotejar una fuente que sea un informe guardado
(`informe:<n>`), y una contrafirma que citaba otra cosa (PMID, DOI, NCT, una contramedida) o nada
no tenía frase que localizar y se admitía; desde el 2026-10-14 se rotulaba «no cotejada», pero
bastaba no citar un informe para que la regla no se aplicara. Decisión del usuario (2026-10-15):
toda segunda firma de alto riesgo tiene que citar un informe guardado, con la frase localizada en
él y declarada vista; si no, se rechaza igual, sin asiento. No hay segunda firma que no sea de
alto riesgo (el almacén exige que la primera lo registrara), y la primera firma no cambia.

La regla y sus textos viven aquí, en un solo sitio, porque los usan tres: el almacén, que es
quien se niega a escribir (`core/storage.py`, `_quoted`); la lectura previa, que le dice a la
consola si con esa cita se podrá contrafirmar (`POST /api/imaging/drafts/{i}/source-quote`); y la
lista de borradores, que da los textos de la regla y rotula lo que se contrafirmó con una regla
anterior. La interfaz no redacta ninguno de estos textos: los pinta.

Lo ya firmado no se toca: las contrafirmas que una regla anterior admitió siguen en la cadena y se
verifican igual. Al leerlas, `prior_rule_note` dice con qué regla se admitieron y `collation`, si
se cotejaron («cotejada» / «no cotejada» y por qué), derivado de lo que dice el asiento.

No es una regla del motor: no entra en el análisis, en los niveles ni en las alertas (no va en
la huella de `core/versioning.py`). Solo decide si se escribe un asiento de firma.
"""

from __future__ import annotations

from typing import Any

# Desde cuándo rige cada parte. Solo para rotular: nada se decide por fecha, sino por lo que dice
# el asiento. La frase localizada y declarada vista, desde el 2026-10-13; la cita obligatoria de
# un informe guardado, desde el 2026-10-15.
RULE_DATE = "2026-10-13"
CITE_RULE_DATE = "2026-10-15"

LOCATED, NOT_LOCATED, NOT_APPLICABLE = "localizada", "no_localizada", "no_aplica"

# Lo que lleva el asiento de una contrafirma cuya fuente no es un informe guardado. Desde el
# 2026-10-15 ya no se escribe ninguna; queda para leer las anteriores (`collation`).
NOT_COLLATABLE_DETAIL = "la fuente no es un informe guardado: no hay frase que cotejar"

MUST_CITE = (
    "La segunda firma de una decisión de alto riesgo tiene que citar un informe guardado "
    "(informe:<n>), con la frase localizada en él y declarada leída."
)
MUST_LOOK = (
    "Antes de la segunda firma hay que pedir la frase del informe citado y tenerla delante."
)
DECLARATION = "He leído esta frase en el informe citado"
MUST_DECLARE = (
    "La segunda firma no se ofrece hasta declarar que se ha leído la frase del informe citado."
)
NOT_COLLATABLE_NOTE = (
    "Esta fuente no es un informe guardado: no hay frase que cotejar, y sin ella la segunda "
    "firma de una decisión de alto riesgo no se admite."
)
_REFUSED = "Segunda firma rechazada: "
_NO_ENTRY = " No se ha escrito ningún asiento."


# Lo que se dice a la vista de una segunda firma, según su asiento (`collation`).
COLLATED, NOT_COLLATED = "cotejada", "no cotejada"
NO_SOURCE_DETAIL = "no cita ninguna fuente: no hay frase que cotejar"
NO_QUOTE_STORED_DETAIL = "el asiento no guarda ninguna frase cotejada de la fuente que cita"
NOT_DECLARED_DETAIL = "la frase se localizó, pero la firma no declaró haberla visto"


class CountersignRefused(ValueError):
    """La segunda firma se rechaza por lo que cita. La ruta lo devuelve como 422."""


def refusal(quote: dict[str, Any] | None, seen: dict[str, Any] | None) -> str | None:
    """Por qué no se contrafirma con esta cita; None si se puede.

    `quote` es lo que la bóveda da al firmar (`vault.locate`): None si la firma no cita nada, y
    `no_aplica` si cita algo que no es un informe guardado. `seen` es lo que la firma declara
    haber visto. Que lo visto y lo que da la bóveda coincidan se comprueba aparte y antes (409).
    """
    if not quote:
        return f"{_REFUSED}no cita ninguna fuente. {MUST_CITE}{_NO_ENTRY}"
    if quote.get("estado") == NOT_APPLICABLE:
        return (
            f"{_REFUSED}la fuente citada no es un informe guardado y no hay frase que cotejar. "
            f"{MUST_CITE}{_NO_ENTRY}"
        )
    pointer = str(quote.get("puntero") or "el informe citado")
    if quote.get("estado") != LOCATED:
        detail = str(quote.get("detalle") or "").strip()
        return (
            f"{_REFUSED}la cita no se localiza en {pointer}"
            + (f" ({detail})" if detail else "")
            + f".{_NO_ENTRY}"
        )
    if seen is None:
        return (
            f"{_REFUSED}cita {pointer} y no declara haber visto la frase literal. Hay que pedir "
            f"la frase, leerla y declararlo al firmar.{_NO_ENTRY}"
        )
    return None


def gate(quote: dict[str, Any] | None) -> dict[str, Any]:
    """Lo que la lectura previa dice de la segunda firma con esta cita, antes de intentarla.

    `collatable`: si la cita es de un informe guardado. Con la frase a la vista solo falta
    declararla leída: `seen` se da aquí por declarado, y `reason` es el texto del 422.
    """
    collatable = bool(quote) and dict(quote or {}).get("estado") != NOT_APPLICABLE
    reason = refusal(quote, {})
    return {"collatable": collatable, "allowed": reason is None, "reason": reason}


def describe() -> dict[str, Any]:
    """Los textos de la regla, para que la consola los pinte sin redactar ninguno."""
    return {
        "since": CITE_RULE_DATE,
        "must_cite": MUST_CITE,
        "must_look": MUST_LOOK,
        "declaration": DECLARATION,
        "must_declare": MUST_DECLARE,
        "not_collatable": NOT_COLLATABLE_NOTE,
    }


def prior_rule_note(countersign: dict[str, Any] | None) -> str | None:
    """Rótulo, derivado al leer, de una contrafirma que la regla de hoy no habría admitido.

    No toca el asiento ni lo invalida: sigue firmado y se verifica igual. Se deduce de lo que el
    asiento dice, no de su fecha: hoy solo se escribe la que cita un informe con la frase
    localizada y declarada vista, así que cualquier otra se admitió con una regla anterior. La
    fecha que nombra es la de la parte de la regla que no cumple.
    """
    if not countersign:
        return None
    quote = dict(countersign.get("source_quote") or {})
    state = quote.get("estado")
    if state == LOCATED and quote.get("vista") is True:
        return None
    if not quote:
        since = CITE_RULE_DATE
        cited = str(countersign.get("source") or "").strip()
        what = ("sin guardar en el asiento una frase cotejada de la fuente que cita" if cited
                else "sin citar ninguna fuente")
    elif state == NOT_APPLICABLE:
        since, what = CITE_RULE_DATE, "citando una fuente que no es un informe guardado"
    elif state != LOCATED:
        since, what = RULE_DATE, "con la cita no localizada"
    else:
        since, what = RULE_DATE, "sin declarar haber visto la frase"
    return (
        f"Contrafirmada antes del {since}, con la regla anterior: entonces se admitía una "
        f"segunda firma {what}. El asiento es el que se firmó y no se ha modificado."
    )


def collation(countersign: dict[str, Any] | None) -> dict[str, Any] | None:
    """Si la segunda firma se cotejó con la frase del informe citado, y si no, por qué.

    Solo hay cotejo cuando el asiento lleva la frase localizada y declarada vista: desde el
    2026-10-15 es la única segunda firma que se escribe. Las demás se admitieron con una regla
    anterior y se dicen «no cotejada», con el motivo que da el propio asiento. Se deriva al leer:
    no toca el asiento ni lo invalida. None si no hay segunda firma.
    """
    if not countersign:
        return None
    quote = dict(countersign.get("source_quote") or {})
    state = quote.get("estado")
    if state == LOCATED and quote.get("vista") is True:
        return {"collated": True, "label": COLLATED, "why": None,
                "text": f"Segunda firma {COLLATED} con la frase del informe citado."}
    if not quote:
        source = str(countersign.get("source") or "").strip()
        why = NO_QUOTE_STORED_DETAIL if source else NO_SOURCE_DETAIL
    elif state == NOT_APPLICABLE:
        why = str(quote.get("detalle") or "").strip() or NOT_COLLATABLE_DETAIL
    elif state != LOCATED:
        why = f"la cita no se localizó en {quote.get('puntero') or 'el informe citado'}"
    else:
        why = NOT_DECLARED_DETAIL
    return {"collated": False, "label": NOT_COLLATED, "why": why,
            "text": f"Segunda firma {NOT_COLLATED}: {why}."}
