"""El contrato de lo leído: las fuentes de un fichero de lectura, y lo que EMMA no dice de sí.

Seis cargadores de `evidence/` (`credibility`, `flight_direction`, `instruments_read`,
`light_exposure`, `nasa_framework` y `research_countermeasures`) sirven lo leído en una fuente con
la misma forma: un bloque `sources` que dice, ficha a ficha del registro, cuánto se leyó (`extent`)
y qué (`what`). Cada uno llevaba su copia de esa comprobación, y las copias se habían separado: el
de las contramedidas en investigación rechazaba con su motivo un `sources` que no es un objeto, una
ficha que no es un objeto o un `extent` que no es texto; los otros cinco rompían ahí con un
`AttributeError` o un `TypeError` sin explicación, que llegaba a la consola como un 500. Una ficha
que no está en el registro salía con el error del registro en tres, con el del cargador en otro y
como «fichero mal formado» en el sexto. Arreglar una copia no arreglaba las otras (decimosexta
ronda, §5.36.15: «la sexta copia del mismo contrato»).

Aquí queda una sola vez lo que comparten, con los mensajes que ya daban: cada ficha está en el
registro, se dice cuánto se leyó con un alcance de la tabla del cargador y qué se leyó, y cada fallo
sale con el error del cargador y su motivo. Lo que solo pide alguno va como parámetro y sigue siendo
suyo: la lista de sitios oficiales de la ficha (`credibility`), la fecha de lectura propia de una
fuente (`nasa_framework` y `flight_direction`, cada uno con su forma de fecha) y el linter sobre lo
que escribe EMMA (`research_countermeasures`).

Y lo que EMMA no puede decir de sí mismo por citar una fuente (invariante 6): las palabras las pone
cada panel, pero que una negación cercana («no es conforme», «ninguna implementación») no cuente
como reclamo se decide aquí, para los dos paneles que se enseñan juntos. El panel de lo leído de
NASA comparaba subcadenas y rechazaba justo la frase honrada que niega.

No sale a la red ni entra en el análisis: comprueba ficheros que viajan con el paquete.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

from app.evidence import registry

# La negación cuenta si va en la misma frase que la palabra y a tres palabras o menos.
_NEGATIONS = frozenset({
    "no", "ni", "sin", "nunca", "ningún", "ninguna", "ninguno", "ningunas", "ningunos",
    "not", "never", "without", "none",
})
_NEGATION_REACH = 3
# Lo que lleva una palabra de negación y no niega, sino que refuerza: «es sin duda conforme» o
# «no solo implementa» afirman más, no menos. Se quita antes de buscar la negación.
_NOT_A_NEGATION = re.compile(
    r"\b(?:sin (?:ninguna |lugar a )?dudas?|no s[oó]lo|not only|not just|ni más ni menos|"
    r"no cabe duda|no hay duda|without (?:a |any )?doubt|no doubt)\b"
)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_sources(
    raw: Mapping[str, Any],
    error: type[ValueError],
    extents: Mapping[str, str],
    *,
    official_hosts: frozenset[str] | None = None,
    own_read_on: Callable[[Any, str], None] | None = None,
    authored: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Comprueba `raw["sources"]` y lo devuelve; cada fallo, como `error` y con su motivo.

    `extents` es la tabla de alcances del cargador. `official_hosts`, si se da, son los sitios en
    que tiene que estar la dirección de cada ficha. `own_read_on(valor, ficha)` comprueba la fecha
    de lectura propia de una fuente cuando la lleva. `authored(ficha, texto)` pasa por el linter lo
    que EMMA escribe de cada fuente (`what`).
    """
    sources = raw.get("sources")
    if not isinstance(sources, dict):
        raise error("`sources` tiene que decir, por ficha, cuánto se leyó")
    for ref_id, source in sources.items():
        try:
            ref = registry.get(ref_id)
        except registry.RegistryError as exc:
            raise error(f"{ref_id}: {exc}") from exc
        # Una ficha que no es un objeto, o un `extent` que no es texto (no se puede buscar en la
        # tabla), se rechazan con su motivo y no con un 500 sin explicación.
        if not isinstance(source, dict):
            raise error(f"{ref_id}: falta cuánto se leyó (`extent` y `what`)")
        extent = source.get("extent")
        if not isinstance(extent, str) or extent not in extents or not _text(source.get("what")):
            raise error(f"{ref_id}: falta cuánto se leyó (`extent` y `what`)")
        if official_hosts is not None:
            parts = urlsplit(ref.url or "")
            if parts.scheme != "https" or parts.hostname not in official_hosts:
                raise error(f"{ref_id}: {ref.url!r} no es una fuente oficial de NASA")
        if own_read_on is not None and "read_on" in source:
            own_read_on(source["read_on"], ref_id)
        if authored is not None:
            authored(ref_id, source["what"])
    return sources


def _negated(before: str) -> bool:
    """Si lo anterior a una palabra, en su misma frase y a tres palabras o menos, la niega."""
    clause = re.split(r"[.;:,!?¿¡()«»]", before)[-1]
    clause = _NOT_A_NEGATION.sub(" ", clause)
    return bool(_NEGATIONS & set(re.findall(r"\w+", clause)[-_NEGATION_REACH:]))


def claims(text: str, words: Iterable[str]) -> list[str]:
    """Las palabras de `words` que el texto dice sin negarlas (se comparan en minúsculas)."""
    lowered = text.lower()
    return [
        word for word in words
        if any(
            not _negated(lowered[: found.start()])
            for found in re.finditer(re.escape(word), lowered)
        )
    ]
