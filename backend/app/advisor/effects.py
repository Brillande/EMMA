"""Efectos e interacciones de las contramedidas: dónde cae cada efecto, y qué se adopta a la vez.

La conversación de ideación del equipo, leyendo el estudio de los antagomirs (`hayslip-2026`: el
tratamiento movió unas señales en un sentido y «increased the expression of fibrosis-associated
transcripts» en el otro), saca la lección para el software: «una intervención puede mejorar una
variable y empeorar otra», y por eso no se modela «riesgo → contramedida» aislado sino «estado →
contramedida → expected benefits / possible adverse effects / interactions → nuevo estado». De
eso EMMA tenía la mitad: cada entrada de la biblioteca lleva `adverse_effects_note` como texto
libre y la tarjeta lo enseña. No decía SOBRE QUÉ dominio o indicador cae cada efecto, no decía
sobre qué se espera el beneficio, y nada en `advisor/` sabía que un tripulante tenía dos
contramedidas adoptadas a la vez. La «trayectoria esperada con y sin contramedida» del esquema
de la ideación se rechazó en el plan (2026-10-31): no hay fuente que la sostenga.

FUERA DE LA HUELLA, Y POR QUÉ
-----------------------------
`core/versioning.py` resume `countermeasures.json` entero: tocarlo cambia `rules_version`, y
eso es lo correcto cuando cambia una contramedida. Decir dónde cae un efecto que la nota ya
escribe no cambia qué se recomienda ni ningún nivel, así que vive en un fichero aparte
(`data/countermeasure_effects.json`) que solo lee este módulo, y la huella sigue siendo la misma
(`tests/test_countermeasure_effects.py` lo comprueba). Lo que sí hace la carga es validar contra
la biblioteca: una ficha por contramedida, ni una menos ni una de más; un id que no exista, un
dominio fuera del enumerado o un indicador fuera del catálogo no cargan; y el beneficio tiene que
ser sobre el dominio que la entrada trata (o, en las comprobaciones de hábitat, sobre el
parámetro de cabina que comprueban): no se inventa ni magnitud ni destino.

Un efecto adverso se declara aquí SOLO si la nota de la entrada lo escribe; si la nota es `null`,
la ficha dice «no declarado», y declarar un efecto sin nota no carga. «No declarado» no es «no
tiene»: la frase que se sirve lo dice.

DOS A LA VEZ
------------
Los seguimientos abiertos (`advisor/followup.py`) dicen qué contramedidas tiene adoptadas un
tripulante en el estado que se mira. Cuando hay más de una, cada recomendación lleva junto a sus
efectos la nota «adoptada junto con «otra»: ninguna fuente leída dice cómo interactúan»; y una
recomendación sin adoptar, con otra en seguimiento, la misma nota en condicional. Si alguna
fuente leída dijera cómo interactúan dos de la biblioteca, iría en `interactions` con su ficha del
registro de evidencia y su frase literal, y la nota llevaría esa frase en vez de la de ausencia.
Hoy la lista está vacía. Nada de este módulo lo lee el análisis ni el asesor: solo AÑADE el campo
`effects` a lo que ya se sirve.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.advisor import countermeasures
from app.advisor.countermeasures import Countermeasure
from app.core import i18n
from app.environment.habitat import PARAMETERS
from app.evidence.registry import Citation, RegistryError, cite
from app.ingest.codes import CATALOG, Domain
from app.ingest.codes import get as get_code
from app.text_guard import check

EFFECTS_PATH = Path(__file__).resolve().parents[1] / "data" / "countermeasure_effects.json"

# Lo que se dice de una entrada cuya nota de efectos adversos es `null`. Callar se leería como
# «no tiene»; esto dice lo que se sabe: que no está escrito.
NOT_DECLARED = (
    "No declarado: la entrada de la biblioteca no escribe ningún efecto adverso, y que no esté "
    "escrito no quiere decir que no lo haya."
)
NO_SOURCE_ON_INTERACTION = "ninguna fuente leída dice cómo interactúan"
CO_ADOPTION_BASIS = (
    "La nota de co-adopción sale de los seguimientos abiertos de este tripulante, no de ninguna "
    "fuente: dice qué otras contramedidas están adoptadas a la vez. Ninguna fuente leída dice "
    "cómo interactúan dos de la biblioteca; si alguna lo dijera, iría aquí con su ficha."
)
NOTE = (
    "Por cada contramedida, sobre qué se espera el beneficio (el dominio que trata o el parámetro "
    "de cabina que comprueba, sin magnitud: la biblioteca no escribe cuánto) y dónde puede caer "
    "cada efecto adverso que su entrada declara. Fuera de la huella de reglas: no cambia ninguna "
    "recomendación ni ningún nivel."
)
i18n.en_many({
    NOT_DECLARED: (
        "Not declared: the library entry writes no adverse effect, and its not being written "
        "does not mean there is none."
    ),
    NO_SOURCE_ON_INTERACTION: "no source read says how they interact",
    CO_ADOPTION_BASIS: (
        "The co-adoption note comes from this crew member's open follow-ups, not from any "
        "source: it says which other countermeasures are adopted at the same time. No source "
        "read says how two of the library interact; if one did, it would go here with its "
        "reference."
    ),
    NOTE: (
        "For each countermeasure, what the benefit is expected on (the domain it addresses or "
        "the cabin parameter it checks, with no magnitude: the library does not write how "
        "much) and where each adverse effect declared by its entry may fall. Outside the rules "
        "fingerprint: it changes no recommendation and no level."
    ),
})
# Los estados de un seguimiento que cuentan como «adoptada ahora».
OPEN_STATES = ("in_window", "due")


class EffectsError(ValueError):
    """El fichero de efectos no cumple su contrato con la biblioteca: no se carga."""


@dataclass(frozen=True, slots=True)
class Affected:
    """Dónde puede caer un efecto adverso: un dominio del enumerado o un indicador del catálogo."""

    kind: str
    key: str
    display: str

    def to_dict(self) -> dict[str, Any]:
        return {"affects": self.kind, "key": self.key, "display": self._display_now()}

    def _display_now(self) -> str:
        """El nombre en el idioma de la petición. `display` se guardó al cargar la ficha, en
        castellano (`validate`): servirlo tal cual dejaría el nombre sin traducir."""
        if i18n.current() != "en":
            return self.display
        if self.kind == "domain":
            return Domain(self.key).display
        return get_code(self.key).display_es


@dataclass(frozen=True, slots=True)
class AdverseEffect:
    affects: Affected
    # Lo que la nota de la entrada dice de él, y de dónde sale. Texto de EMMA: pasa el linter.
    text: str
    basis: str

    def to_dict(self) -> dict[str, Any]:
        # El texto y su base son del fichero de datos: su inglés, del hermano `.en.json`.
        return {
            **self.affects.to_dict(),
            "text": i18n.localized(self.text, EFFECTS_PATH),
            "basis": i18n.localized(self.basis, EFFECTS_PATH),
        }


@dataclass(frozen=True, slots=True)
class Effects:
    countermeasure_id: str
    # Sobre qué se espera el beneficio: el dominio que trata (crew) o el parámetro de cabina que
    # comprueba (habitat). Uno de los dos, nunca ambos.
    benefit_domain: Domain | None
    benefit_parameter: str | None
    benefit_text: str
    # `None` = la entrada no escribe ningún efecto adverso («no declarado»).
    adverse: tuple[AdverseEffect, ...] | None

    @property
    def declared(self) -> bool:
        return self.adverse is not None

    def _benefit_now(self) -> str:
        """La frase del beneficio en el idioma de la petición.

        `benefit_text` se compuso al cargar, en castellano, y la ficha queda guardada: en inglés
        se vuelve a componer con la entrada de la biblioteca contra la que se validó. Si la ficha
        es de otra biblioteca (una prueba), se sirve la guardada.
        """
        if i18n.current() != "en":
            return self.benefit_text
        item = countermeasures.library().get(self.countermeasure_id)
        if item is None:
            return self.benefit_text
        return _benefit_text(item, self.benefit_parameter)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "countermeasure_id": self.countermeasure_id,
            "benefit": {
                "domain": str(self.benefit_domain) if self.benefit_domain is not None else None,
                "domain_display": (
                    self.benefit_domain.display if self.benefit_domain is not None else None
                ),
                "parameter": self.benefit_parameter,
                "parameter_display": (
                    PARAMETERS[self.benefit_parameter].display
                    if self.benefit_parameter is not None else None
                ),
                "text": self._benefit_now(),
            },
            "adverse_declared": self.declared,
            "adverse": [item.to_dict() for item in self.adverse or ()],
            "adverse_text": None if self.declared else NOT_DECLARED,
        }
        if body["adverse_text"] is not None:
            body["adverse_text"] = i18n.loc(body["adverse_text"])
        return body


@dataclass(frozen=True, slots=True)
class Interaction:
    """Lo que una fuente leída dice de dos contramedidas adoptadas a la vez."""

    between: tuple[str, str]
    source: Citation
    quote: str

    def involves(self, first: str, second: str) -> bool:
        return set(self.between) == {first, second}

    def to_dict(self) -> dict[str, Any]:
        return {
            "between": list(self.between),
            "source": self.source.to_dict(),
            "quote": self.quote,
        }


@dataclass(frozen=True, slots=True)
class Loaded:
    effects: dict[str, Effects]
    interactions: tuple[Interaction, ...]


def _guarded(fail: Any, name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise fail(f"`{name}` vacío")
    found = check(value)
    if found:
        raise fail(f"`{name}` suena a pauta u orden ({found[0].category}): {value!r}")
    return value


def _benefit_text(item: Countermeasure, parameter: str | None) -> str:
    """Sobre qué se espera el beneficio, en palabras: sin magnitud, porque no la hay escrita."""
    if parameter is not None:
        return i18n.tr(
            f"Beneficio esperado: sobre {PARAMETERS[parameter].display}, el parámetro que "
            "comprueba. Es una comprobación: dice qué hay tras la lectura, no cambia la cabina.",
            f"Expected benefit: on {PARAMETERS[parameter].display}, the parameter it checks. It "
            "is a check: it says what lies behind the reading, it does not change the cabin.",
        )
    assert item.domain is not None
    domain = item.domain.display
    if item.family == "check-surveillance":
        return i18n.tr(
            f"Beneficio esperado: sobre el dominio {domain}, el que trata. Es una comprobación o "
            "un registro: dice si lo visto es real y cómo evoluciona, no cambia por sí misma el "
            "nivel.",
            f"Expected benefit: on the {domain} domain, the one it addresses. It is a check or a "
            "record: it says whether what was seen is real and how it evolves, it does not by "
            "itself change the level.",
        )
    # El nombre del indicador de seguimiento no entra en la frase: va en `followup_checks_display`
    # de la contramedida, y algunos («tasa de dosis…») harian saltar el linter de lenguaje.
    return i18n.tr(
        f"Beneficio esperado: sobre el dominio {domain}, el que trata; si se ve, lo dice su "
        "seguimiento. Sin magnitud: la biblioteca no escribe cuánto.",
        f"Expected benefit: on the {domain} domain, the one it addresses; if it shows, its "
        "follow-up says so. No magnitude: the library does not write how much.",
    )


def _adverse(raw: Any, fail: Any) -> AdverseEffect:
    if not isinstance(raw, dict) or set(raw) != {"affects", "text", "basis"}:
        raise fail("cada efecto adverso es {affects, text, basis}")
    affects = raw["affects"]
    if not isinstance(affects, dict) or len(affects) != 1:
        raise fail("`affects` es {domain} o {indicator}: dónde puede caer el efecto")
    ((kind, key),) = affects.items()
    # La clave se consulta en el enumerado o en el catálogo: si no es texto, lo dice este módulo
    # y no un `TypeError` de una lista que no se puede buscar.
    if not isinstance(key, str):
        raise fail(f"`affects.{kind}` tiene que ser la clave en texto: {key!r}")
    if kind == "domain":
        try:
            display = Domain(key).display
        except ValueError:
            raise fail(f"`affects.domain` fuera del enumerado de dominios: {key!r}") from None
    elif kind == "indicator":
        if key not in CATALOG:
            raise fail(f"`affects.indicator` fuera del catálogo: {key!r}")
        display = get_code(key).display_es
    else:
        raise fail(f"`affects` desconocido: {kind!r}; es `domain` o `indicator`")
    return AdverseEffect(
        affects=Affected(kind=str(kind), key=str(key), display=display),
        text=_guarded(fail, "text", raw["text"]),
        basis=_guarded(fail, "basis", raw["basis"]),
    )


def _entry(raw: Any, library: Mapping[str, Countermeasure]) -> Effects:
    if not isinstance(raw, dict) or set(raw) != {"countermeasure_id", "benefit", "adverse"}:
        raise EffectsError("cada ficha de efectos es {countermeasure_id, benefit, adverse}")
    ident = str(raw["countermeasure_id"])

    def fail(reason: str) -> EffectsError:
        return EffectsError(f"efectos de {ident}: {reason}")

    item = library.get(ident)
    if item is None:
        raise fail("no está en la biblioteca")
    benefit = raw["benefit"]
    if not isinstance(benefit, dict) or len(benefit) != 1:
        raise fail("`benefit` es {domain} o {parameter}: sobre qué se espera el beneficio")
    benefit_domain: Domain | None = None
    benefit_parameter: str | None = None
    if item.scope == "habitat":
        parameter = benefit.get("parameter")
        if not isinstance(parameter, str) or parameter not in PARAMETERS:
            raise fail(f"`benefit.parameter` fuera de los parámetros de cabina: {parameter!r}")
        if parameter not in item.followup_checks:
            raise fail(
                f"`benefit.parameter` ({parameter}) no es el parámetro que la entrada comprueba "
                f"({list(item.followup_checks)})"
            )
        benefit_parameter = parameter
    else:
        try:
            benefit_domain = Domain(benefit["domain"])
        except (KeyError, TypeError, ValueError):
            raise fail(
                f"`benefit.domain` fuera del enumerado de dominios: {benefit.get('domain')!r}"
            ) from None
        if benefit_domain is not item.domain:
            raise fail(
                f"`benefit.domain` ({benefit_domain}) no es el dominio que la entrada trata "
                f"({item.domain})"
            )
    adverse_raw = raw["adverse"]
    adverse: tuple[AdverseEffect, ...] | None = None
    if adverse_raw is not None:
        if item.adverse_effects_note is None:
            raise fail(
                "declara efectos adversos y la entrada de la biblioteca no escribe su nota: la "
                "nota va primero, en la biblioteca (y cambia la versión de reglas, que es lo "
                "correcto)"
            )
        if not isinstance(adverse_raw, list) or not adverse_raw:
            raise fail("`adverse` es null (no declarado) o una lista con al menos un efecto")
        adverse = tuple(_adverse(entry, fail) for entry in adverse_raw)
    elif item.adverse_effects_note is not None:
        raise fail(
            "la entrada escribe una nota de efectos adversos y la ficha no dice dónde cae ninguno"
        )
    return Effects(
        countermeasure_id=ident,
        benefit_domain=benefit_domain,
        benefit_parameter=benefit_parameter,
        benefit_text=_benefit_text(item, benefit_parameter),
        adverse=adverse,
    )


def _interaction(raw: Any, library: Mapping[str, Countermeasure]) -> Interaction:
    if not isinstance(raw, dict) or set(raw) != {"between", "ref", "relevance", "quote"}:
        raise EffectsError("cada interacción es {between, ref, relevance, quote}")
    between = raw["between"]
    if (
        not isinstance(between, list)
        or len(between) != 2
        or not all(isinstance(ident, str) for ident in between)
        or len(set(between)) != 2
    ):
        raise EffectsError("`between` son dos ids distintos de la biblioteca")
    unknown = [ident for ident in between if ident not in library]
    if unknown:
        raise EffectsError(
            f"interacción entre contramedidas que no están en la biblioteca: {unknown}"
        )

    def fail(reason: str) -> EffectsError:
        return EffectsError(f"interacción {between}: {reason}")

    relevance = _guarded(fail, "relevance", raw["relevance"])
    quote = raw["quote"]
    # La frase literal es de la fuente, en su idioma: no se reescribe ni pasa el linter.
    if not isinstance(quote, str) or not quote.strip():
        raise fail("`quote` vacía: la frase literal de la fuente")
    try:
        source = cite(str(raw["ref"]), relevance)
    except RegistryError as exc:
        raise fail(str(exc)) from exc
    first, second = sorted(str(ident) for ident in between)
    return Interaction(between=(first, second), source=source, quote=quote)


def validate(raw: Any, library: Mapping[str, Countermeasure]) -> Loaded:
    """El fichero entero contra la biblioteca: una ficha por contramedida, y nada que no exista."""
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("effects"), list)
        or not isinstance(raw.get("interactions"), list)
    ):
        raise EffectsError("el fichero es un objeto con `effects` (lista) e `interactions` (lista)")
    effects: dict[str, Effects] = {}
    for entry in raw["effects"]:
        # La ficha se guarda (`loaded`) y la piden los dos idiomas: lo que se compone al cargar
        # —la frase del beneficio, el nombre de donde cae un efecto— va en castellano, lo pida
        # quien lo pida primero; el inglés se compone al servir (`to_dict`).
        with i18n.use("es"):
            item = _entry(entry, library)
        if item.countermeasure_id in effects:
            raise EffectsError(f"efectos de {item.countermeasure_id}: ficha repetida")
        effects[item.countermeasure_id] = item
    missing = [ident for ident in library if ident not in effects]
    if missing:
        raise EffectsError(f"contramedidas sin ficha de efectos: {missing}")
    interactions = tuple(_interaction(entry, library) for entry in raw["interactions"])
    pairs = [item.between for item in interactions]
    if len(set(pairs)) != len(pairs):
        raise EffectsError("una misma pareja de contramedidas aparece dos veces en `interactions`")
    return Loaded(effects=effects, interactions=interactions)


def load(
    path: Path = EFFECTS_PATH, library: Mapping[str, Countermeasure] | None = None
) -> Loaded:
    known = countermeasures.library() if library is None else library
    return validate(json.loads(path.read_text(encoding="utf-8")), known)


_validated: tuple[Mapping[str, Countermeasure], Loaded] | None = None


def loaded() -> Loaded:
    """El fichero validado contra LA biblioteca que hay ahora.

    Se guarda junto al propio diccionario de la biblioteca y se compara con `is`: si alguien la
    sustituye (una prueba, una recarga), la ficha se vuelve a validar contra la nueva en vez de
    servir la de la anterior. Por el diccionario y no por su `id()`, que se reutiliza al liberarse.
    """
    global _validated
    library = countermeasures.library()
    if _validated is None or _validated[0] is not library:
        _validated = (library, load(library=library))
    return _validated[1]


def get(countermeasure_id: str) -> Effects:
    try:
        return loaded().effects[countermeasure_id]
    except KeyError as exc:
        raise KeyError(f"contramedida sin ficha de efectos: {countermeasure_id}") from exc


def interactions() -> tuple[Interaction, ...]:
    return loaded().interactions


def interaction_between(first: str, second: str) -> Interaction | None:
    return next((item for item in interactions() if item.involves(first, second)), None)


def open_adoptions(followups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Las contramedidas sin cerrar del tripulante, tal y como el estado ya las derivó.

    Una por contramedida: adoptar la misma dos veces sin cerrar la primera (la ruta de adoptar no
    lo impide) es la misma contramedida a la vez, no dos, y se cuenta por su primera adopción.
    """
    opened: dict[str, dict[str, Any]] = {}
    for item in followups:
        if item["state"] in OPEN_STATES:
            opened.setdefault(item["countermeasure"]["id"], {
                "countermeasure_id": item["countermeasure"]["id"],
                "action": item["countermeasure"]["action"],
                "adoption_index": item["adoption_index"],
                "adopted_at": item["adopted_at"],
            })
    return list(opened.values())


def co_adopted(countermeasure_id: str, followups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Con qué otras contramedidas está (o iría) adoptada a la vez, una nota por cada una.

    El texto lo compone el backend y la interfaz lo pinta tal cual. Sin fuente leída que diga cómo
    interactúan, lo dice así; con una (`interactions`), lleva su frase y su ficha.
    """
    opened = open_adoptions(followups)
    adopted = any(item["countermeasure_id"] == countermeasure_id for item in opened)
    notes: list[dict[str, Any]] = []
    for other in opened:
        if other["countermeasure_id"] == countermeasure_id:
            continue
        interaction = interaction_between(countermeasure_id, other["countermeasure_id"])
        if interaction is None:
            tail = NO_SOURCE_ON_INTERACTION
            source = None
        else:
            tail = i18n.tr(
                f"{interaction.source.ref.title} dice: «{interaction.quote}»",
                f"{interaction.source.ref.title} says: «{interaction.quote}»",
            )
            source = interaction.source.to_dict()
        head = (
            f"Adoptada junto con «{other['action']}»" if adopted
            else f"Si se adopta, irá junto con «{other['action']}», en seguimiento"
        )
        if i18n.current() == "en":
            head = (
                f"Adopted together with «{other['action']}»" if adopted
                else f"If adopted, it will go together with «{other['action']}», under follow-up"
            )
        notes.append({
            **other,
            "adopted": adopted,
            # Sin fuente, `tail` es la constante de arriba y sale con su inglés registrado.
            "text": f"{head}: {i18n.loc(tail)}.",
            "source": source,
        })
    return notes


def describe(countermeasure_id: str, followups: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Los efectos de una contramedida y con qué otras está adoptada a la vez."""
    return {
        **get(countermeasure_id).to_dict(),
        "co_adopted": co_adopted(countermeasure_id, followups),
        "co_adoption_basis": i18n.loc(CO_ADOPTION_BASIS),
    }


def library_entry(countermeasure_id: str) -> dict[str, Any]:
    """La ficha para la biblioteca: sin tripulante, no hay co-adopción que contar."""
    return describe(countermeasure_id, ())


def with_effects(
    recommendations: Sequence[dict[str, Any]], followups: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Cada recomendación con los efectos de su contramedida, o `None` si no lleva una.

    `followups` es lo que el estado ya derivó (`advisor.followup.followups`): mismas firmas y
    mismo corte. Solo AÑADE el campo `effects`: ni quita, ni reordena, ni toca la urgencia.
    """
    annotated: list[dict[str, Any]] = []
    for item in recommendations:
        measure = item.get("countermeasure")
        annotated.append({
            **item,
            "effects": describe(measure["id"], followups) if measure else None,
        })
    return annotated


def _interactions_note(pairs: int) -> str:
    """La cabecera de la biblioteca no se queda muda: ni sin interacciones leídas ni con ellas."""
    if pairs == 0:
        return i18n.tr(
            "Ninguna fuente leída dice cómo interactúan dos contramedidas de la biblioteca.",
            "No source read says how two countermeasures of the library interact.",
        )
    return i18n.tr(
        f"Parejas de contramedidas de las que una fuente leída dice cómo interactúan: {pairs}. "
        "La frase de la fuente va en la nota de co-adopción de la tarjeta.",
        f"Pairs of countermeasures for which a source read says how they interact: {pairs}. "
        "The source's sentence goes in the co-adoption note of the card.",
    )


def overview() -> dict[str, Any]:
    """Para la biblioteca: las interacciones leídas (hoy ninguna), la nota y las cuentas."""
    items = loaded().effects.values()
    return {
        "note": i18n.loc(NOTE),
        "co_adoption_basis": i18n.loc(CO_ADOPTION_BASIS),
        "declared": sum(1 for item in items if item.declared),
        "not_declared": sum(1 for item in items if not item.declared),
        "interactions": [item.to_dict() for item in interactions()],
        "interactions_note": _interactions_note(len(interactions())),
    }
