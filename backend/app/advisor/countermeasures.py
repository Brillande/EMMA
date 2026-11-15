"""Contramedidas como datos, no como frases.

La especificacion del equipo (`docs/contexto/`, §8) lo dice sin rodeos: "las contramedidas son
datos estructurados, no texto libre". Hasta el 2026-09-26 eran tres frases por dominio en un
diccionario, con la evidencia del dominio pegada a todas por igual. Una tripulacion que tiene
que decidir que hace con dos horas libres no puede elegir entre "ejercicio" y "revisar la sal"
sin saber que cuesta cada una, en que se apoya, cuando se sabra si ha servido y que mirar.

Cada entrada (`app/data/countermeasures.json`) dice: accion, indicacion, recursos, tiempo de
tripulacion, protocolo o fuente, que indicador se repite y cuando, efectos adversos conocidos,
y si la respalda un protocolo concreto (`evidence-backed`) o solo el riesgo del dominio
(`demo`). **Una cifra sin fuente no se escribe:** el tiempo de tripulacion va a `null` con
"sin fuente", y la ventana de seguimiento dice si es "diseño EMMA". La carga valida todo eso y
falla si falta: una contramedida sin base no llega a la tripulacion.

Desde el 2026-10-09 `resources` es obligatorio (especificacion §3 y §8: «recursos necesarios»):
una lista, vacia solo si la entrada declara por que en `resources_note`. Y la contraindicacion
(§3, «contraindication placeholder») ya no se calla: ninguna entrada la tiene escrita, porque
escribirla es trabajo de la revision medica, asi que se entrega «pendiente de revision medica»
(`contraindications_display`) en vez de un hueco que se leeria como «no tiene».

El 2026-10-14 se leyeron las notas tecnicas de OCHMO del ejercicio (`ochmo-tb-031`), del ritmo
circadiano (`ochmo-mtb-009`) y del hueso (`ochmo-mtb-013`) buscando tiempos y
contraindicaciones. Dieron tiempos con su frase y riesgos del nutriente, pero ninguna
contraindicacion de estas acciones: lo mas parecido («Within 2 hours of sleep, avoid: Vigorous
exercise») es higiene del sueño, y escribirlo como contraindicacion borraria el «pendiente de
revision medica» de la tarjeta. Sigue pendiente.

Desde el 2026-10-10 cada recurso apunta a una clave del vocabulario cerrado de recursos
(`app/data/resources.json`, `core/resources.py`) y conserva al lado el texto con que la entrada
lo nombraba. El vocabulario sale de esos textos y de nada mas: un recurso fuera de el, o una
clave que ninguna contramedida nombre, hace fallar la carga. Asi una persona puede declarar que
un recurso no esta a bordo y la tarjeta decirlo junto a la contramedida, sin retirarla.

El campo de efectos adversos existe por una leccion concreta de la base de conocimiento, que
esta en el registro de evidencia como `hayslip-2026` (GeroScience, 23 de junio de 2026; resumen
leido en PubMed el 2026-10-13). Es un estudio preclinico, en higado de raton, y su resumen dice:
«while antagomir treatment influenced genes associated with senescence and inflammatory
responses, it increased the expression of fibrosis-associated transcripts». Dice que el
tratamiento influyo en unos genes, no que los mejorase, y no dice nada de una persona: lo que
EMMA toma de ahi es solo la forma del problema. Una intervencion puede mover una variable en un
sentido y otra en el contrario; el modelo de datos tiene que poder decirlo.

LA FAMILIA DE CADA CONTRAMEDIDA (2026-10-21)
--------------------------------------------
La biblioteca existia entera en `GET /api/countermeasures` y nadie la leia: la tripulacion solo
veia las recomendadas. La base de conocimiento (§15, P1: «Contramedidas por RIDGE: biblioteca
evidence-linked de acciones y recursos») y la conversacion de ideacion piden ademas saber de que
clase es cada accion. La ideacion lo dice dos veces, pensando en la radiacion: «blindaje
estructural, uso de masa ya disponible —agua, alimentos, suministros—, refugios temporales,
dosimetria y sensores, procedimientos operacionales y, finalmente, contramedidas
medicas/biologicas y vigilancia longitudinal», y despues «Contramedidas fisicas → materiales,
agua, polietileno, distribucion de masa, refugios. Contramedidas operacionales → alerta,
desplazamiento, reduccion del tiempo de exposicion. Contramedidas biologicas/farmacologicas →
proteccion/reparacion celular. Vigilancia medica → detectar consecuencias tempranas y
longitudinales». La base de conocimiento (§7) repite la lista para la radiacion.

El usuario decidio el 2026-10-21 un vocabulario cerrado de tres familias, mas la farmacologica
declarada fuera del alcance de EMMA (`FAMILIES`). Cada entrada lleva `family` y la carga falla si
falta, si no es del vocabulario o si es la farmacologica: la especificacion (§8) dice «No generar
dosis ni tratamientos», y una entrada asi no se adopta, se dice. Hoy ninguna lo es.

La familia se asigna por lo que la accion ES, no por lo que «deberia» ser, y el criterio de cada
una va escrito en `FAMILIES` (lo sirve la API). Dos casos que no estaban en la lista de la
ideacion se declaran: el ejercicio entra en «fisica o de masa» por ser carga mecanica sobre el
cuerpo con un equipo (la lista de la ideacion es de radiacion y no lo nombra), y trasladarse al
modulo con mas blindaje es «operacional» (desplazamiento, como lo clasifica la ideacion), mientras
que el refugio, que coloca agua y viveres como blindaje, es «fisica o de masa». La familia no la
lee el analisis ni el asesor: no cambia que se recomienda ni ningun nivel. Si cambia la huella de
reglas (`core/versioning.py` resume este fichero de datos entero), y se declaro asi.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from app.core import i18n
from app.core.resources import vocabulary as resource_vocabulary
from app.environment.habitat import PARAMETERS
from app.evidence.links import EvidenceItem
from app.evidence.registry import RegistryError, cite
from app.ingest.codes import CATALOG, Domain, Ridge
from app.ingest.codes import get as get_code

LIBRARY_PATH = Path(__file__).resolve().parents[1] / "data" / "countermeasures.json"

BASES = ("evidence-backed", "demo")
NO_SOURCE = "sin fuente"
# Lo que se dice de una entrada sin contraindicaciones escritas. Escribirlas es trabajo de la
# revision medica, no de este modulo: callar haria creer que no las hay.
CONTRAINDICATIONS_PENDING = "sin contraindicaciones escritas: pendiente de revisión médica"
i18n.en(CONTRAINDICATIONS_PENDING, "no contraindications written: pending medical review")
# La accion de refugio solo la dispara un evento solar activo, no el nivel del dominio.
SHELTER_ID = "rad-storm-shelter"


class LibraryError(ValueError):
    """La biblioteca no cumple su propio contrato: no se carga."""


SCOPES = ("crew", "habitat")


@dataclass(frozen=True, slots=True)
class Family:
    """Una familia del vocabulario cerrado: su palabra y el criterio con que se asigna."""

    key: str
    display: str
    criterion: str
    # La farmacologica esta en el vocabulario para poder decir que queda fuera, no para usarla.
    in_scope: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display": i18n.loc(self.display),
            "criterion": i18n.loc(self.criterion),
            "in_scope": self.in_scope,
        }


PHARMACOLOGICAL = "pharmacological"

FAMILIES: dict[str, Family] = {
    item.key: item
    for item in (
        Family(
            "physical-mass",
            "física o de masa",
            "La acción actúa por medios físicos: coloca masa entre la persona y el peligro "
            "(zona blindada, agua y víveres como blindaje) o carga el cuerpo con un equipo "
            "(cinta, cicloergómetro, ARED). La lista de la ideación es de radiación y no nombra "
            "el ejercicio; que entre aquí por ser carga física es criterio de EMMA.",
        ),
        Family(
            "operational",
            "operacional",
            "La acción cambia qué hace la tripulación, cuándo o dónde: el horario antes del "
            "sueño, la iluminación, el contacto, el traslado a otro módulo, suspender una "
            "actividad extravehicular, la higiene, el reparto de la ingesta o el menú. No coloca "
            "masa ni mide nada: reorganiza la actividad.",
        ),
        Family(
            "check-surveillance",
            "comprobación o vigilancia",
            "La acción mide, repite una medida, registra o revisa con alguien: no cambia nada "
            "de la persona ni del entorno; dice si lo visto es real y cómo evoluciona. Incluye "
            "la dosimetría y el contraste de los sensores de cabina.",
        ),
        Family(
            PHARMACOLOGICAL,
            "farmacológica: fuera del alcance de EMMA",
            "La acción es una sustancia que se toma para proteger o reparar el cuerpo (la "
            "ideación habla de «protección/reparación celular»). La especificación (§8) la deja "
            "fuera: una entrada de esta familia no se carga. Ninguna de la biblioteca lo es.",
            in_scope=False,
        ),
    )
}
IN_SCOPE_FAMILIES = tuple(key for key, item in FAMILIES.items() if item.in_scope)
FAMILY_BASIS = (
    "Vocabulario cerrado decidido el 2026-10-21 sobre la conversación de ideación del equipo "
    "(contramedidas físicas, operacionales, biológicas o farmacológicas y vigilancia médica) y la "
    "base de conocimiento §7 (blindaje, masa existente, refugio, procedimiento operacional y "
    "seguimiento médico). La familia se asigna por lo que la acción es y no cambia ninguna "
    "recomendación ni ningún nivel."
)
# El inglés del vocabulario de familias (`core/i18n.py`): las palabras y los criterios de arriba
# se quedan como están; `Family.to_dict` y `overview` los resuelven al servir.
i18n.en_many({
    FAMILIES["physical-mass"].display: "physical or mass",
    FAMILIES["physical-mass"].criterion: (
        "The action works by physical means: it places mass between the person and the hazard "
        "(shielded area, water and food supplies as shielding) or loads the body with a piece "
        "of equipment (treadmill, cycle ergometer, ARED). The list from the ideation is about "
        "radiation and does not name exercise; placing it here as physical loading is EMMA's "
        "criterion."
    ),
    FAMILIES["operational"].display: "operational",
    FAMILIES["operational"].criterion: (
        "The action changes what the crew does, when or where: the schedule before sleep, the "
        "lighting, contact, the move to another module, suspending an extravehicular activity, "
        "hygiene, the spread of intake or the menu. It places no mass and measures nothing: it "
        "reorganizes activity."
    ),
    FAMILIES["check-surveillance"].display: "check or surveillance",
    FAMILIES["check-surveillance"].criterion: (
        "The action measures, repeats a measurement, records or reviews with someone: it "
        "changes nothing in the person or the environment; it says whether what was seen is "
        "real and how it evolves. It includes dosimetry and the cross-check of the cabin "
        "sensors."
    ),
    FAMILIES[PHARMACOLOGICAL].display: "pharmacological: outside EMMA's scope",
    FAMILIES[PHARMACOLOGICAL].criterion: (
        "The action is a substance taken to protect or repair the body (the ideation speaks of "
        "«protección/reparación celular», cell protection and repair). The specification (§8) "
        "leaves it out: an entry of this family is not loaded. None in the library is one."
    ),
    FAMILY_BASIS: (
        "Closed vocabulary decided on 2026-10-21 from the team's ideation conversation "
        "(physical, operational, biological or pharmacological countermeasures and medical "
        "surveillance) and the knowledge base §7 (shielding, existing mass, shelter, "
        "operational procedure and medical follow-up). The family is assigned by what the "
        "action is and changes no recommendation and no level."
    ),
})


@dataclass(frozen=True, slots=True)
class Countermeasure:
    id: str
    # None en las de habitat: actuan sobre la cabina, no sobre un dominio clinico.
    domain: Domain | None
    action: str
    indication: str
    resources: tuple[str, ...]
    crew_time_minutes: int | None
    crew_time_basis: str
    protocol_ref: EvidenceItem | None
    followup_checks: tuple[str, ...]
    followup_window_hours: float
    followup_basis: str
    contraindications_note: str | None
    adverse_effects_note: str | None
    basis: str
    # Clave de `FAMILIES`, siempre de una familia en el alcance (la carga lo comprueba).
    family: str
    # "crew": sobre una persona, se ofrece por dominio y se adopta. "habitat": comprobacion
    # ambiental de la especificacion (§8), se ofrece con la hipotesis de causa compartida.
    scope: str = "crew"
    # Solo cuando `resources` esta vacia: la entrada dice expresamente por que (p. ej. "no
    # requiere recursos"). Una lista vacia sin esto no carga: no se distinguiria de un olvido.
    resources_note: str | None = None
    # La clave del vocabulario cerrado de cada recurso, en el mismo orden que `resources`
    # (que sigue siendo el texto con que la entrada lo nombra).
    resource_keys: tuple[str, ...] = ()

    @property
    def contraindications_display(self) -> str:
        """Lo escrito por la revision medica o, si no hay nada, que esta pendiente."""
        return self.contraindications_note or CONTRAINDICATIONS_PENDING

    @property
    def ridge(self) -> Ridge:
        return self.domain.ridge if self.domain is not None else Ridge.ENVIRONMENT

    def to_dict(self) -> dict[str, Any]:
        return _served({
            "id": self.id,
            "scope": self.scope,
            "domain": str(self.domain) if self.domain is not None else None,
            "ridge": str(self.ridge),
            "ridge_display": self.ridge.display,
            "family": self.family,
            "family_display": FAMILIES[self.family].display,
            "action": self.action,
            "indication": self.indication,
            "resources": list(self.resources),
            "resource_keys": list(self.resource_keys),
            "resources_note": self.resources_note,
            "crew_time_minutes": self.crew_time_minutes,
            "crew_time_basis": self.crew_time_basis,
            "protocol_ref": self.protocol_ref.to_dict() if self.protocol_ref else None,
            "followup_checks": list(self.followup_checks),
            "followup_checks_display": [_display(key) for key in self.followup_checks],
            "followup_window_hours": self.followup_window_hours,
            "followup_basis": self.followup_basis,
            "contraindications_note": self.contraindications_note,
            "contraindications_display": self.contraindications_display,
            "adverse_effects_note": self.adverse_effects_note,
            "basis": self.basis,
        })


def _served(body: dict[str, Any]) -> dict[str, Any]:
    """Una entrada en el idioma de la petición; en castellano, la misma que se le da.

    El texto de la biblioteca (acción, indicación, recursos, bases, notas y para qué sirve su
    fuente) sale de su hermano inglés, `countermeasures.en.json`: `countermeasures.json` no se
    toca, porque sus bytes entran en la huella de reglas. La familia y la contraindicación
    pendiente son constantes de este módulo. Los ids, las claves y las cifras no cambian. Se
    traduce aquí, al servir, y no en `library()`, que está cacheada.
    """
    if i18n.current() != "en":
        return body
    served = i18n.localized(body, LIBRARY_PATH)
    served["family_display"] = i18n.loc(served["family_display"])
    served["contraindications_display"] = i18n.loc(served["contraindications_display"])
    return served


def _entry(raw: dict[str, Any], vocabulary: Mapping[str, object]) -> Countermeasure:
    ident = str(raw.get("id", "?"))

    def fail(reason: str) -> LibraryError:
        return LibraryError(f"contramedida {ident}: {reason}")

    scope = raw.get("scope", "crew")
    if scope not in SCOPES:
        raise fail(f"alcance desconocido; uno de {SCOPES}")
    domain: Domain | None = None
    if scope == "crew":
        try:
            domain = Domain(raw["domain"])
        except (KeyError, ValueError) as exc:
            raise fail("dominio desconocido") from exc
    elif raw.get("domain") is not None:
        raise fail("una contramedida de hábitat no lleva dominio clínico")
    if raw.get("basis") not in BASES:
        raise fail(f"`basis` tiene que ser uno de {BASES}")
    family = raw.get("family")
    if family == PHARMACOLOGICAL:
        raise fail(
            "familia farmacológica: fuera del alcance de EMMA (especificación §8: no se generan "
            "dosis ni tratamientos); no se adopta"
        )
    if family not in IN_SCOPE_FAMILIES:
        raise fail(f"familia desconocida o ausente; una de {IN_SCOPE_FAMILIES}")
    minutes = raw.get("crew_time_minutes")
    time_basis = str(raw.get("crew_time_basis") or "").strip()
    if not time_basis:
        raise fail("sin `crew_time_basis`: diga la fuente del tiempo o 'sin fuente'")
    if minutes is not None and time_basis == NO_SOURCE:
        raise fail("un tiempo de tripulacion con cifra no puede ser 'sin fuente'")
    reference = raw.get("protocol_ref")
    if raw["basis"] == "evidence-backed" and not reference:
        raise fail("respaldada por evidencia sin protocolo ni fuente que la respalde")
    protocol_ref: EvidenceItem | None = None
    if reference:
        # La fuente se cita por su identificador del registro unico de evidencia; aqui solo
        # se dice para que sirve en esta accion. Una ficha escrita en linea no se acepta.
        if not isinstance(reference, dict) or set(reference) != {"ref", "relevance"}:
            raise fail("`protocol_ref` es {ref, relevance}: la ficha vive en evidence_refs.json")
        relevance = reference["relevance"]
        if not isinstance(relevance, str) or not relevance.strip():
            raise fail("`protocol_ref` sin `relevance`: diga qué respalda de esta acción")
        try:
            protocol_ref = cite(str(reference["ref"]), relevance)
        except RegistryError as exc:
            raise fail(str(exc)) from exc
    checks = tuple(raw.get("followup_checks") or ())
    known = CATALOG if scope == "crew" else PARAMETERS
    unknown = [key for key in checks if key not in known]
    if unknown:
        raise fail(f"indicadores de seguimiento fuera del catálogo: {unknown}")
    window = raw.get("followup_window_hours")
    if not isinstance(window, (int, float)) or window <= 0:
        raise fail("ventana de seguimiento no positiva")
    if not str(raw.get("followup_basis") or "").strip():
        raise fail("ventana de seguimiento sin base")
    # La especificacion (§3, §8) pide los recursos de cada entrada. El campo es obligatorio y
    # es una lista; vacia solo si la entrada lo declara expresamente en `resources_note`.
    if "resources" not in raw:
        raise fail("sin `resources`: liste los recursos o declare que no requiere ninguno")
    listed = raw["resources"]
    # Cada recurso es una clave del vocabulario cerrado (`core/resources.py`) y el texto con
    # que ESTA entrada lo nombra, que se conserva tal cual: no se reescribe contenido clinico.
    if not isinstance(listed, list) or any(
        not isinstance(item, dict) or set(item) != {"key", "description"} for item in listed
    ):
        raise fail("`resources` tiene que ser una lista de {key, description}")
    resources = [item["description"] for item in listed]
    resource_keys = [item["key"] for item in listed]
    if any(not isinstance(name, str) or not name.strip() for name in resources):
        raise fail("un recurso sin `description`: conserve el texto con que se nombra")
    outside = [key for key in resource_keys if not isinstance(key, str) or key not in vocabulary]
    if outside:
        raise fail(f"recursos fuera del vocabulario: {outside}")
    if len(set(resource_keys)) != len(resource_keys):
        raise fail("un mismo recurso del vocabulario aparece dos veces")
    resources_note = raw.get("resources_note")
    if resources_note is not None and (
        not isinstance(resources_note, str) or not resources_note.strip()
    ):
        raise fail("`resources_note` vacía: diga por qué no requiere recursos, o quítela")
    if not resources and resources_note is None:
        raise fail(
            "`resources` vacía sin `resources_note`: declare expresamente que no requiere "
            "recursos"
        )
    if resources and resources_note is not None:
        raise fail("`resources_note` solo acompaña a una lista de recursos vacía")
    contraindications = raw.get("contraindications_note")
    if contraindications is not None and (
        not isinstance(contraindications, str) or not contraindications.strip()
    ):
        raise fail("`contraindications_note` vacía: escríbala la revisión médica o déjela en null")
    return Countermeasure(
        id=ident,
        domain=domain,
        action=str(raw["action"]),
        indication=str(raw["indication"]),
        resources=tuple(resources),
        crew_time_minutes=minutes,
        crew_time_basis=time_basis,
        protocol_ref=protocol_ref,
        followup_checks=checks,
        followup_window_hours=float(window),
        followup_basis=str(raw["followup_basis"]),
        contraindications_note=contraindications,
        adverse_effects_note=raw.get("adverse_effects_note"),
        basis=str(raw["basis"]),
        family=str(family),
        scope=scope,
        resources_note=resources_note,
        resource_keys=tuple(resource_keys),
    )


def load(
    path: Path = LIBRARY_PATH, vocabulary: Mapping[str, object] | None = None
) -> dict[str, Countermeasure]:
    known = resource_vocabulary() if vocabulary is None else vocabulary
    raw = json.loads(path.read_text(encoding="utf-8"))["countermeasures"]
    library: dict[str, Countermeasure] = {}
    for item in raw:
        entry = _entry(item, known)
        if entry.id in library:
            raise LibraryError(f"contramedida {entry.id}: id repetido")
        library[entry.id] = entry
    return library


def unused_resources(
    library: Mapping[str, Countermeasure], vocabulary: Mapping[str, object]
) -> list[str]:
    """Claves del vocabulario que ninguna contramedida nombra."""
    used = {key for item in library.values() for key in item.resource_keys}
    return [key for key in vocabulary if key not in used]


def load_closed(
    path: Path = LIBRARY_PATH, vocabulary: Mapping[str, object] | None = None
) -> dict[str, Countermeasure]:
    """La biblioteca, y ademas que el vocabulario de recursos no tenga nada de mas.

    El vocabulario sale de lo que las contramedidas nombran: una clave que ninguna use seria
    un recurso inventado (el principio de un inventario que EMMA no lleva), y la carga falla.
    """
    known = resource_vocabulary() if vocabulary is None else vocabulary
    loaded = load(path, known)
    unused = unused_resources(loaded, known)
    if unused:
        raise LibraryError(
            f"recursos del vocabulario que ninguna contramedida nombra: {unused}"
        )
    return loaded


@cache
def library() -> dict[str, Countermeasure]:
    return load_closed()


def resource_users() -> dict[str, list[str]]:
    """Que contramedidas nombran cada recurso, en el orden de la biblioteca."""
    users: dict[str, list[str]] = {}
    for item in library().values():
        for key in item.resource_keys:
            users.setdefault(key, []).append(item.id)
    return users


def _display(key: str) -> str:
    return PARAMETERS[key].display if key in PARAMETERS else get_code(key).display_es


def for_habitat(parameter: str) -> list[Countermeasure]:
    """Comprobaciones ambientales cuyo seguimiento es ese parametro de cabina."""
    return [
        item for item in library().values()
        if item.scope == "habitat" and parameter in item.followup_checks
    ]


def for_domain(domain: Domain) -> list[Countermeasure]:
    """Las del dominio en el orden de la biblioteca, sin la de refugio (va por evento)."""
    return [
        item for item in library().values()
        if item.domain is domain and item.id != SHELTER_ID
    ]


def get(countermeasure_id: str) -> Countermeasure:
    try:
        return library()[countermeasure_id]
    except KeyError as exc:
        raise KeyError(f"contramedida desconocida: {countermeasure_id}") from exc


LIBRARY_NOTE = (
    "La biblioteca entera, agrupada por peligro RIDGE: qué se puede hacer, qué cuesta y en qué "
    "se apoya. Consultarla no adopta nada ni cambia ningún nivel; lo que el estado de ahora "
    "recomienda va aparte, con las recomendaciones."
)
RIDGE_BASIS = (
    "El peligro RIDGE de cada contramedida es el de su dominio clínico; las comprobaciones de "
    "cabina, sin dominio, van a «entorno hostil y cerrado». Vocabulario RIDGE: NASA, «The Human "
    "Body in Space»."
)
i18n.en_many({
    LIBRARY_NOTE: (
        "The whole library, grouped by RIDGE hazard: what can be done, what it costs and what "
        "it rests on. Consulting it adopts nothing and changes no level; what the current "
        "status recommends goes separately, with the recommendations."
    ),
    RIDGE_BASIS: (
        "The RIDGE hazard of each countermeasure is that of its clinical domain; the cabin "
        "checks, which have no domain, go under «hostile and closed environment». RIDGE "
        "vocabulary: NASA, «The Human Body in Space»."
    ),
})


def overview() -> dict[str, Any]:
    """La biblioteca para leerla entera: por peligro RIDGE y con el vocabulario de familias.

    Los grupos siguen el orden de `Ridge` y cada uno nombra sus entradas por id, en el orden de la
    biblioteca; un peligro sin entradas sale con cero, no desaparece. Las familias salen todas,
    tambien la que esta fuera del alcance, con cuantas entradas tiene cada una.
    """
    items = list(library().values())
    by_ridge = []
    for ridge in Ridge:
        ids = [item.id for item in items if item.ridge is ridge]
        by_ridge.append(
            {
                "ridge": str(ridge),
                "ridge_display": ridge.display,
                "count": len(ids),
                "countermeasures": ids,
            }
        )
    return {
        "countermeasures": [item.to_dict() for item in items],
        "by_ridge": by_ridge,
        "families": [
            {**family.to_dict(), "count": sum(1 for item in items if item.family == key)}
            for key, family in FAMILIES.items()
        ],
        "note": i18n.loc(LIBRARY_NOTE),
        "family_basis": i18n.loc(FAMILY_BASIS),
        "ridge_basis": i18n.loc(RIDGE_BASIS),
    }
