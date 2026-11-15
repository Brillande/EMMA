"""El catálogo cerrado de intenciones del asistente, leído de `data/assistant_intents.json`, y el
inventario de la interfaz a la que llega, leído de `data/assistant_ui.json`.

Por qué existe: «toda la interfaz por voz» no puede querer decir «lo que el modelo crea que la
interfaz hace». Si el modelo pudiera nombrar cualquier acción, una alucinación sería un botón
pulsado. Aquí está la lista entera, con el esquema de los argumentos de cada intención; lo que el
modelo devuelve se valida contra ella y lo que no encaja se descarta (barrera «schema»).

Las listas de valores no se copian en el JSON de intenciones: las pestañas, los paneles, los
pliegues, las consolas y los modos de pantalla salen del inventario de la interfaz (el mismo que
lee la consola por `GET /api/assistant` y que `frontend/src/assistant/uiInventory.test.ts` coteja
con los `.tsx`); las secciones de entorno, de los perfiles de misión; las guías, de
`measurement_guides.json`; los términos, del glosario; las zonas y tipos de dolor, de
`app/pain/`; los dominios, del catálogo; los niveles de misión, de su vocabulario, y los
indicadores del diario, de su ruta. Así una lista no puede quedarse atrás de su fuente.

LA NAVEGACIÓN NO ESCRIBE. Las intenciones de navegación y lectura de pantalla (`open_panel`,
`read_panel`, `toggle_mode`, `switch_console`, `scroll`, `next_panel`, `previous_panel`) son de
clase `read`, como las demás de pantalla, y el catálogo no carga si una de ellas declara una ruta.
Sus valores son ids del inventario, que solo nombra paneles, pliegues y modos de presentación:
ningún mando que firme, envíe, reconozca o redacte. Eso solo lo proponen las seis de escritura.

Sin modelo, `keyword_intent` empareja por palabras clave (las del JSON y los alias del
inventario) sobre texto normalizado: es lo determinista con que el asistente sigue sirviendo
cuando Ollama no está. Las marcadas `keywords_first` mandan aunque el modelo esté: son mandos de
voz y de pantalla donde una palabra clara no admite otra lectura.

UN CATÁLOGO POR IDIOMA, UNA SOLA ESTRUCTURA (decisión del usuario, 2026-11-15: el asistente
también en inglés). Las intenciones, sus clases, sus argumentos, sus rutas y los ids del inventario
salen siempre de los dos ficheros de arriba; el inglés solo trae PALABRAS, por id:
`assistant_intents.en.json` (rótulos, palabras clave, verbos, sinónimos y frases de enrutado) y
`assistant_ui.en.json` (rótulo, alias y `about` de cada consola, pestaña, modo y panel). Se funden
antes de validar (`english_intents`, `english_ui`), así que el catálogo inglés pasa las mismas
comprobaciones que el castellano, y una entrada sin inglés se queda con su castellano. Lo que del
emparejamiento sin modelo es gramática y no dato (apagar, desplazar, girar, preguntar) vive en un
`_Lexicon` por idioma, al final de este módulo.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import guides
from app.core import i18n, mission_modes
from app.evidence import mission_profiles
from app.ingest.codes import Domain
from app.pain.catalog import CHARACTERS, MAX_INTENSITY, ZONES
from app.text_guard import normalize

DATA = Path(__file__).resolve().parents[1] / "data"
INTENTS_PATH = DATA / "assistant_intents.json"
UI_PATH = DATA / "assistant_ui.json"
# Las palabras inglesas de los dos ficheros de arriba, por id (ver «UN CATÁLOGO POR IDIOMA»).
INTENTS_EN_PATH = DATA / "assistant_intents.en.json"
UI_EN_PATH = DATA / "assistant_ui.en.json"
CONSOLES = ("crew", "ground")
KINDS = frozenset({"read", "write"})
PANEL_KINDS = frozenset({"panel", "part", "fold"})
MODE_KINDS = frozenset({"toggle", "choice"})
ENV_SECTION = "env-*"
# Las intenciones que acuerda el contrato con la interfaz (unidad B). Una que falte o sobre en el
# JSON es un error al cargar, no una sorpresa en la consola.
CONTRACT_IDS = frozenset({
    "open_tab", "read_status", "read_alerts", "read_routines", "rotate", "privacy", "low_vision",
    "essential", "stop_voice", "repeat_voice", "silence", "stop_listening", "open_guide",
    "open_glossary", "start_pvt", "start_cognition", "none",
    "open_panel", "read_panel", "toggle_mode", "switch_console", "scroll", "next_panel",
    "previous_panel", "press",
    "diary_entry", "pain_report", "acknowledge_alert", "mission_level", "mission_profile",
    "safe_mode",
})
# Las únicas que escriben (proponen). Ninguna intención nueva entra aquí sin cambiar el contrato.
WRITE_IDS = frozenset({"diary_entry", "pain_report", "acknowledge_alert", "mission_level",
                       "mission_profile", "safe_mode"})
ROTATIONS = (0, 90, 180, 270)


class CatalogError(ValueError):
    """El catálogo no cumple sus propias reglas: no se carga."""


@dataclass(frozen=True)
class Intent:
    id: str
    kind: str
    label: str
    args: dict[str, Any]
    keywords: tuple[str, ...]
    route: str | None
    signer_field: str | None
    origin_field: str | None
    keywords_first: bool = False


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    keywords: tuple[str, ...]
    # Qué se ve y qué se puede hacer en la pestaña, en una o dos frases (el mapa de la aplicación).
    about: str = ""


@dataclass(frozen=True)
class Place:
    console: str
    section: str | None


@dataclass(frozen=True)
class Panel:
    """Un panel, apartado o pliegue de la interfaz: lo que lleva `data-ui="<id>"` en el DOM."""

    id: str
    kind: str
    label: str
    aliases: tuple[str, ...]
    places: tuple[Place, ...]
    # Qué enseña y qué deja hacer, escrito desde el propio componente: con esto el modelo sabe qué
    # hay DENTRO de cada panel, no solo cómo se llama (el aire de la nave está en «Hábitat»).
    about: str = ""

    def in_console(self, console: str) -> bool:
        return any(place.console == console for place in self.places)


@dataclass(frozen=True)
class Mode:
    id: str
    kind: str
    intent: str
    label: str
    aliases: tuple[str, ...]
    about: str = ""


@dataclass(frozen=True)
class ConsoleRef:
    id: str
    label: str
    aliases: tuple[str, ...]
    about: str = ""


@dataclass(frozen=True)
class Catalog:
    intents: dict[str, Intent]
    sections: dict[str, tuple[Section, ...]]
    open_verbs: tuple[str, ...]
    read_verbs: tuple[str, ...]
    question_words: tuple[str, ...]
    panel_words: tuple[str, ...]
    guide_keywords: dict[str, tuple[str, ...]]
    model_label: str
    panels: dict[str, Panel]
    modes: dict[str, Mode]
    consoles: dict[str, ConsoleRef]
    # El rótulo de lo que contesta el modelo con lo que sabe por su cuenta: el mismo literal para la
    # pantalla y para la voz, que lo dice antes de la respuesta (decisión del usuario, 2026-11-03).
    general_label: str
    # Las palabras con que se nombra cada entorno de misión al declararlo («órbita baja»): el
    # nombre del catálogo es largo («órbita baja terrestre (estación espacial)») y nadie lo dice
    # entero. Una por perfil del catálogo, ni una más (lo comprueba `validate`).
    profile_keywords: dict[str, tuple[str, ...]]
    # Grupos de palabras que dicen lo mismo en la calle y en la pantalla («dormir» y «sueño»,
    # «corazón» y «cardiovascular», «aire» y «CO2»): los usa la búsqueda del mapa de la aplicación
    # (`retrieval.py`) para llegar a un panel por lo que hay dentro, no por su rótulo.
    synonyms: tuple[tuple[str, ...], ...] = ()
    # Frases de enrutado sin modelo (`routing` del JSON): levantar la privacidad cuando está puesta,
    # declarar un entorno con «estamos en…», el dominio de una alerta por sus palabras y el nivel de
    # misión por las suyas.
    privacy_off: tuple[str, ...] = ()
    profile_triggers: tuple[str, ...] = ()
    domain_keywords: dict[str, tuple[str, ...]] = field(default_factory=dict)
    level_keywords: dict[str, tuple[str, ...]] = field(default_factory=dict)
    diary_keywords: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Cómo se dice cada zona del dolor y cada término del glosario además de por su nombre
    # (`routing.zone_keywords`, `routing.glossary_keywords`). El castellano no las necesita: casa
    # por el nombre de su fuente. El inglés sí, porque esos nombres los traduce otra unidad y el
    # asistente no puede depender de en qué idioma lleguen.
    zone_keywords: dict[str, tuple[str, ...]] = field(default_factory=dict)
    glossary_keywords: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def section_keys(self, console: str) -> list[str]:
        return [section.key for section in self.sections[console]]

    def section(self, console: str, key: str) -> Section | None:
        return next((item for item in self.sections[console] if item.key == key), None)

    def toggle_modes(self) -> list[str]:
        return [mode.id for mode in self.modes.values() if mode.kind == "toggle"]


def _diary_keys() -> list[str]:
    # Import tardío: `app.api.diary` arrastra las rutas, y el catálogo se carga al importar.
    from app.api.diary import diary_keys

    return diary_keys()


def enum_source(name: str) -> list[str]:
    """Los valores admitidos de un argumento, leídos de su fuente."""
    if name == "diary_keys":
        return _diary_keys()
    if name == "pain_zones":
        return list(ZONES)
    if name == "pain_characters":
        return list(CHARACTERS)
    if name == "domains":
        return [str(domain) for domain in Domain]
    if name == "mission_levels":
        return list(mission_modes.LEVELS)
    if name == "mission_profiles":
        return list(mission_profiles.EXPECTED_IDS)
    if name == "guides":
        return [str(item["id"]) for item in guides.guides()["guides"]]
    if name == "glossary":
        return [str(item["id"]) for item in guides.glossary()["terms"]]
    if name == "panels":
        return list(catalog().panels)
    if name == "modes":
        return catalog().toggle_modes()
    if name == "consoles":
        return list(CONSOLES)
    raise CatalogError(f"lista de valores desconocida: {name}")


# Las que salen del propio catálogo: se comprueban al validarlo, no con `enum_source`.
_OWN_LISTS = frozenset({"sections", "panels", "modes", "consoles"})


def _environment_sections(raw: dict[str, Any]) -> list[Section]:
    prefix = str(raw["prefix"])
    keywords = tuple(str(word) for word in raw["aliases"])
    about = _about("entornos", raw)
    return [
        Section(f"{prefix}{profile['id']}", str(profile["display"]),
                (*keywords, normalize(str(profile["display"]))), about)
        for profile in mission_profiles.catalog()["profiles"]
    ]


# Lo que cabe en el `about` de una entrada: una o dos frases. Un párrafo no cabe en el prompt
# (van una docena por turno) ni ayuda a elegir.
ABOUT_MAX = 200


def _about(owner: str, item: dict[str, Any]) -> str:
    """El «qué hay aquí» de una entrada del inventario: obligatorio, corto y en una línea."""
    about = item.get("about")
    if not isinstance(about, str) or not about.strip():
        raise CatalogError(f"{owner}: sin `about` (qué enseña y qué deja hacer)")
    if len(about) > ABOUT_MAX or "\n" in about:
        raise CatalogError(f"{owner}: el `about` pasa de {ABOUT_MAX} caracteres o de una línea")
    return about.strip()


def _words(owner: str, words: Any) -> tuple[str, ...]:
    out = tuple(str(word) for word in words)
    if any(word != plain(word).strip() or not word for word in out):
        raise CatalogError(f"{owner}: palabras y alias sin tildes, en minúsculas y sin signos")
    return out


# Pestañas apartadas de una versión (`"set_aside": true` en el inventario; decisión del usuario,
# 2026-11-15): la consola no las monta (`ConsoleSection.setAside`), así que el asistente no debe
# ofrecerlas ni llevar a un panel que solo vive en ellas. El inventario las sigue nombrando —el
# código se queda— y esta marca decide si el catálogo las cuenta. La aplicación la enciende al
# arrancar (`app/main.py`); la suite la deja apagada, porque sus pruebas del asistente recorren
# todas las pestañas, y prueba el apartado pidiéndolo (`tests/test_set_aside.py`).
_set_aside_active = False


def use_set_aside(active: bool) -> None:
    """Enciende o apaga el apartado de pestañas y olvida lo calculado con el valor anterior."""
    global _set_aside_active
    _set_aside_active = active
    # `lang_cache` deja su `cache_clear` en la función, y borra lo de los dos idiomas.
    catalog.cache_clear()  # type: ignore[attr-defined]
    examples.cache_clear()  # type: ignore[attr-defined]
    ui_inventory.cache_clear()  # type: ignore[attr-defined]


def set_aside_active() -> bool:
    return _set_aside_active


def _validate_ui(ui: dict[str, Any]) -> tuple[dict[str, tuple[Section, ...]], dict[str, Panel],
                                              dict[str, Mode], dict[str, ConsoleRef]]:
    """El inventario de la interfaz, comprobado: ids únicos, sitios que existen, alias limpios."""
    consoles = {str(item["id"]): ConsoleRef(str(item["id"]), str(item["label"]),
                                            _words(str(item["id"]), item["aliases"]),
                                            _about(str(item["id"]), item))
                for item in ui["consoles"]}
    if tuple(consoles) != CONSOLES:
        raise CatalogError("el inventario nombra otras consolas que las dos de EMMA")
    environments = _environment_sections(ui["sections"]["environments"])
    sections: dict[str, tuple[Section, ...]] = {}
    all_keys: dict[str, set[str]] = {}
    aside: dict[str, set[str]] = {}
    for console in CONSOLES:
        own = [Section(str(item["key"]), str(item["label"]),
                       _words(f"{console}.{item['key']}", item["aliases"]),
                       _about(f"{console}.{item['key']}", item))
               for item in ui["sections"][console]]
        keys = [section.key for section in own]
        if len(keys) != len(set(keys)):
            raise CatalogError(f"{console}: sección repetida")
        all_keys[console] = set(keys)
        for item in ui["sections"][console]:
            if not isinstance(item.get("set_aside", False), bool):
                raise CatalogError(f"{console}.{item['key']}: `set_aside` es verdadero o falso")
        aside[console] = ({str(item["key"]) for item in ui["sections"][console]
                           if item.get("set_aside") is True} if _set_aside_active else set())
        sections[console] = (*(s for s in own if s.key not in aside[console]), *environments)
    panels: dict[str, Panel] = {}
    for item in ui["panels"]:
        panel_id = str(item["id"])
        if panel_id in panels:
            raise CatalogError(f"panel repetido: {panel_id}")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", panel_id):
            raise CatalogError(f"{panel_id}: un id de panel es en minúsculas y con guiones")
        if item["kind"] not in PANEL_KINDS:
            raise CatalogError(f"{panel_id}: clase {item['kind']!r}, no panel/part/fold")
        places = []
        for place in item["places"]:
            console, section = str(place["console"]), place["section"]
            if console not in CONSOLES:
                raise CatalogError(f"{panel_id}: consola {console!r}")
            if (section is not None and section != ENV_SECTION
                    and section not in all_keys[console]):
                raise CatalogError(f"{panel_id}: {console} no tiene la pestaña {section}")
            places.append(Place(console, None if section is None else str(section)))
        if not places:
            raise CatalogError(f"{panel_id}: sin sitio en ninguna consola")
        # Un panel que solo vive en pestañas apartadas no existe en esta versión; uno que vive
        # también en otra se queda con los sitios que siguen a la vista.
        places = [place for place in places if place.section not in aside[place.console]]
        if not places:
            continue
        aliases = _words(panel_id, item["aliases"])
        if not aliases:
            raise CatalogError(f"{panel_id}: sin ningún nombre con que pedirlo")
        taken = next((other.id for other in panels.values()
                      if set(other.aliases) & set(aliases)), None)
        if taken is not None:
            # Un nombre de dos paneles abriría siempre el primero, sin decirlo.
            raise CatalogError(f"{panel_id}: comparte un alias con {taken}")
        panels[panel_id] = Panel(panel_id, str(item["kind"]), str(item["label"]), aliases,
                                 tuple(places), _about(panel_id, item))
    modes: dict[str, Mode] = {}
    for item in ui["modes"]:
        mode_id = str(item["id"])
        if mode_id in modes or item["kind"] not in MODE_KINDS:
            raise CatalogError(f"modo repetido o de clase desconocida: {mode_id}")
        modes[mode_id] = Mode(mode_id, str(item["kind"]), str(item["intent"]), str(item["label"]),
                              _words(mode_id, item["aliases"]), _about(mode_id, item))
    return sections, panels, modes, consoles


def validate(raw: dict[str, Any], ui: dict[str, Any] | None = None) -> Catalog:
    """El catálogo, comprobado: ids del contrato, clases, rutas de escritura y palabras clave."""
    if ui is None:
        ui = json.loads(UI_PATH.read_text(encoding="utf-8"))
    sections, panels, modes, consoles = _validate_ui(ui)
    intents: dict[str, Intent] = {}
    for item in raw["intents"]:
        intent_id = str(item["id"])
        if intent_id in intents:
            raise CatalogError(f"intención repetida: {intent_id}")
        kind = str(item["kind"])
        if kind not in KINDS:
            raise CatalogError(f"{intent_id}: clase {kind!r}, no read/write")
        if kind == "write" and not (item.get("route") and item.get("signer_field")):
            raise CatalogError(f"{intent_id}: una escritura dice su ruta y su campo de firma")
        if kind == "read" and item.get("route"):
            raise CatalogError(f"{intent_id}: una lectura no escribe por ninguna ruta")
        if (kind == "write") != (intent_id in WRITE_IDS):
            raise CatalogError(f"{intent_id}: solo escriben las seis del contrato")
        keywords = _words(intent_id, item.get("keywords", []))
        from_mode = item.get("keywords_from_mode")
        if from_mode is not None:
            mode = modes.get(str(from_mode))
            if mode is None or mode.intent != intent_id:
                raise CatalogError(f"{intent_id}: el modo {from_mode!r} no es suyo")
            keywords = (*keywords, *mode.aliases)
        for spec in dict(item["args"]).values():
            for key in ("enum_from", "items_enum_from"):
                if key in spec and spec[key] not in _OWN_LISTS:
                    enum_source(str(spec[key]))  # una lista que no existe falla aquí, al cargar
        intents[intent_id] = Intent(
            intent_id, kind, str(item["label"]), dict(item["args"]), keywords,
            item.get("route"), item.get("signer_field"), item.get("origin_field"),
            bool(item.get("keywords_first", False)),
        )
    if set(intents) != CONTRACT_IDS:
        raise CatalogError(
            f"el catálogo no es el del contrato: sobran {sorted(set(intents) - CONTRACT_IDS)}, "
            f"faltan {sorted(CONTRACT_IDS - set(intents))}"
        )
    if any(intents[mode.intent].kind != "read" for mode in modes.values()
           if mode.intent in intents):
        raise CatalogError("un modo de pantalla no escribe en el registro")
    if any(mode.intent not in intents for mode in modes.values()):
        raise CatalogError("cada modo de pantalla dice qué intención lo cambia")
    known_guides = set(enum_source("guides"))
    guide_keywords = {str(key): tuple(words) for key, words in raw["guide_keywords"].items()}
    if set(guide_keywords) != known_guides:
        raise CatalogError("cada guía de medida lleva sus palabras clave, y solo las guías")
    profile_keywords = {str(key): _words(f"entorno {key}", words)
                        for key, words in raw["profile_keywords"].items()}
    if tuple(profile_keywords) != mission_profiles.EXPECTED_IDS or not all(
        profile_keywords.values()
    ):
        raise CatalogError("cada entorno de misión lleva sus palabras clave, y solo los entornos")
    synonyms = tuple(_words("sinónimos", group) for group in raw.get("synonyms", []))
    if any(len(group) < 2 for group in synonyms):
        raise CatalogError("un grupo de sinónimos tiene al menos dos palabras")
    routing = dict(raw.get("routing", {}))
    domain_keywords = {str(key): _words(f"dominio {key}", words)
                       for key, words in dict(routing.get("domain_keywords", {})).items()}
    if not set(domain_keywords) <= {str(domain) for domain in Domain}:
        raise CatalogError("las palabras de dominio son de dominios del catálogo")
    level_keywords = {str(key): _words(f"nivel {key}", words)
                      for key, words in dict(routing.get("level_keywords", {})).items()}
    if not set(level_keywords) <= set(mission_modes.LEVELS):
        raise CatalogError("las palabras de nivel son de niveles de misión")
    diary_keywords = {str(key): _words(f"diario {key}", words)
                      for key, words in dict(routing.get("diary_keywords", {})).items()}
    if not set(diary_keywords) <= set(enum_source("diary_keys")):
        raise CatalogError("las palabras del diario son de indicadores del diario")
    zone_keywords = {str(key): _words(f"zona {key}", words)
                     for key, words in dict(routing.get("zone_keywords", {})).items()}
    if not set(zone_keywords) <= set(ZONES):
        raise CatalogError("las palabras de zona son de zonas del mapa de dolor")
    glossary_keywords = {str(key): _words(f"término {key}", words)
                         for key, words in dict(routing.get("glossary_keywords", {})).items()}
    if not set(glossary_keywords) <= set(enum_source("glossary")):
        raise CatalogError("las palabras de glosario son de términos del glosario")
    return Catalog(
        intents, sections, tuple(str(verb) for verb in raw["open_verbs"]),
        tuple(str(verb) for verb in raw["read_verbs"]),
        tuple(str(word) for word in raw["question_words"]),
        tuple(str(word) for word in raw["panel_words"]),
        guide_keywords, str(raw["model_label"]), panels, modes, consoles,
        str(raw["general_label"]), profile_keywords, synonyms,
        _words("privacy_off", routing.get("privacy_off", [])),
        _words("profile_triggers", routing.get("profile_triggers", [])),
        domain_keywords, level_keywords, diary_keywords, zone_keywords, glossary_keywords,
    )


# Lo que de `assistant_intents.json` es idioma y no estructura: lo único que trae el fichero
# inglés, además del rótulo y las palabras clave de cada intención.
LANGUAGE_KEYS = ("model_label", "general_label", "open_verbs", "read_verbs", "question_words",
                 "panel_words", "guide_keywords", "profile_keywords", "synonyms", "routing")
_INTENT_WORDS = frozenset({"label", "keywords"})
_ENTRY_WORDS = ("label", "aliases", "about")


def _own(data: dict[str, Any]) -> set[str]:
    """Las claves de un JSON de datos sin sus notas (`_nota`, `_routing`…)."""
    return {key for key in data if not key.startswith("_")}


def english_intents(raw: dict[str, Any], english: dict[str, Any]) -> dict[str, Any]:
    """`assistant_intents.json` con las palabras de su hermano inglés.

    El inglés no puede bifurcar el catálogo: trae exactamente las listas de `LANGUAGE_KEYS` y, por
    cada intención del castellano (ni una más, ni una menos), su rótulo y sus palabras clave. La
    clase, los argumentos, la ruta, el campo de firma, `keywords_first` y `keywords_from_mode`
    son los del castellano.
    """
    if _own(english) != {*LANGUAGE_KEYS, "intents"}:
        raise CatalogError("el inglés del catálogo trae las listas de idioma e `intents`, nada más")
    words = dict(english["intents"])
    if set(words) != {str(item["id"]) for item in raw["intents"]}:
        raise CatalogError("el inglés del catálogo nombra otras intenciones que el castellano")
    if any(set(item) != _INTENT_WORDS for item in words.values()):
        raise CatalogError("el inglés de una intención es su rótulo y sus palabras clave")
    return {
        **raw,
        **{key: english[key] for key in LANGUAGE_KEYS},
        "intents": [{**item, **words[str(item["id"])]} for item in raw["intents"]],
    }


def _in_english(owner: str, items: list[dict[str, Any]], key: str,
                english: dict[str, Any]) -> list[dict[str, Any]]:
    """Cada entrada con su rótulo, sus alias y su `about` ingleses, si los tiene."""
    known = {str(item[key]) for item in items}
    stray = sorted(set(english) - known)
    if stray:
        # Un id inglés sin entrada castellana es una errata o un panel que ya no existe: sus
        # palabras no llegarían a nada, y callarlo escondería que falta traducir el de verdad.
        raise CatalogError(f"{owner}: el inglés nombra lo que el inventario no tiene: {stray}")
    out = []
    for item in items:
        entry = english.get(str(item[key]))
        out.append(item if entry is None else
                   {**item, **{name: entry[name] for name in _ENTRY_WORDS if name in entry}})
    return out


def english_ui(ui: dict[str, Any], english: dict[str, Any]) -> dict[str, Any]:
    """`assistant_ui.json` con el rótulo, los alias y el `about` de `assistant_ui.en.json`, por id.

    Solo cambian esas tres cosas: los ids, las clases, los sitios y `set_aside` son los del
    castellano. Una entrada sin inglés (hoy, las de las pestañas apartadas) se queda en castellano.
    """
    sections = dict(ui["sections"])
    for console in CONSOLES:
        sections[console] = _in_english(f"sections.{console}", ui["sections"][console], "key",
                                        dict(english["sections"].get(console, {})))
    environments = dict(english["sections"].get("environments", {}))
    sections["environments"] = {**ui["sections"]["environments"],
                                **{name: environments[name] for name in ("aliases", "about")
                                   if name in environments}}
    return {
        **ui,
        "consoles": _in_english("consoles", ui["consoles"], "id", dict(english["consoles"])),
        "sections": sections,
        "modes": _in_english("modes", ui["modes"], "id", dict(english["modes"])),
        "panels": _in_english("panels", ui["panels"], "id", dict(english["panels"])),
    }


def _read(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _ui() -> dict[str, Any]:
    """El inventario de la interfaz en el idioma de la petición."""
    ui = _read(UI_PATH)
    return english_ui(ui, _read(UI_EN_PATH)) if i18n.current() == "en" else ui


@i18n.lang_cache
def catalog() -> Catalog:
    if i18n.current() == "en":
        return validate(english_intents(_read(INTENTS_PATH), _read(INTENTS_EN_PATH)), _ui())
    return validate(json.loads(INTENTS_PATH.read_text(encoding="utf-8")))


@i18n.lang_cache
def ui_inventory() -> dict[str, Any]:
    """El inventario tal cual, sin la nota: lo que la consola lee por `GET /api/assistant`."""
    shown = catalog()  # que no se sirva un inventario que no se deja cargar
    raw = _ui()
    served = {key: value for key, value in raw.items() if not key.startswith("_")}
    if not _set_aside_active:
        return served
    # Con pestañas apartadas, la consola recibe el inventario de lo que monta: sin ellas, sin los
    # paneles que solo vivían en ellas y sin esos sitios en los que viven también en otra.
    aside = {console: {str(item["key"]) for item in raw["sections"][console]
                       if item.get("set_aside") is True} for console in CONSOLES}
    served["sections"] = {
        **raw["sections"],
        **{console: [item for item in raw["sections"][console]
                     if str(item["key"]) not in aside[console]] for console in CONSOLES},
    }
    served["panels"] = [
        {**item, "places": [place for place in item["places"]
                            if place["section"] not in aside[str(place["console"])]]}
        for item in raw["panels"] if str(item["id"]) in shown.panels
    ]
    return served


def args_schema(intent: Intent) -> dict[str, Any]:
    """El esquema de los argumentos de una intención, con sus listas ya resueltas."""
    schema: dict[str, Any] = {}
    for name, spec in intent.args.items():
        resolved = {key: value for key, value in spec.items()
                    if key not in ("enum_from", "items_enum_from")}
        if spec.get("enum_from") == "sections":
            resolved["enum"] = sorted({key for console in CONSOLES
                                       for key in catalog().section_keys(console)})
            resolved["by_console"] = {console: catalog().section_keys(console)
                                      for console in CONSOLES}
        elif "enum_from" in spec:
            resolved["enum"] = enum_source(str(spec["enum_from"]))
        if "items_enum_from" in spec:
            resolved["items"] = {"type": "string",
                                 "enum": enum_source(str(spec["items_enum_from"]))}
        schema[name] = resolved
    return schema


def describe() -> list[dict[str, Any]]:
    """Lo que publica `GET /api/assistant`: cada intención con su clase y su esquema."""
    return [
        {"id": intent.id, "kind": intent.kind, "label": intent.label, "args": args_schema(intent)}
        for intent in catalog().intents.values()
    ]


# --------------------------------------------------------------------------- #
# Validación de lo que propone el modelo (barrera «schema»)
# --------------------------------------------------------------------------- #


class InvalidArgs(ValueError):
    """Los argumentos no cumplen el esquema de la intención."""


def _check_value(name: str, spec: dict[str, Any], value: Any, console: str) -> Any:
    kind = spec.get("type")
    if kind == "boolean":
        if not isinstance(value, bool):
            raise InvalidArgs(f"{name}: tiene que ser sí o no")
        return value
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
            raise InvalidArgs(f"{name}: tiene que ser un entero")
        value = int(value)
    elif kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidArgs(f"{name}: tiene que ser un número")
        value = float(value)
    elif kind == "string":
        if not isinstance(value, str) or not value.strip():
            raise InvalidArgs(f"{name}: tiene que ser un texto")
        value = value.strip()
    elif kind == "array":
        if not isinstance(value, list):
            raise InvalidArgs(f"{name}: tiene que ser una lista")
        allowed = enum_source(str(spec["items_enum_from"]))
        if any(item not in allowed for item in value) or len(set(value)) != len(value):
            raise InvalidArgs(f"{name}: valores fuera de la lista o repetidos")
        return list(value)
    if "minimum" in spec and value < spec["minimum"]:
        raise InvalidArgs(f"{name}: por debajo de {spec['minimum']}")
    if "maximum" in spec and value > spec["maximum"]:
        raise InvalidArgs(f"{name}: por encima de {spec['maximum']}")
    if "enum" in spec and value not in spec["enum"]:
        raise InvalidArgs(f"{name}: fuera de la lista")
    if spec.get("enum_from") == "sections":
        if value not in catalog().section_keys(console):
            raise InvalidArgs(f"{name}: la consola no tiene esa sección")
    elif "enum_from" in spec and value not in enum_source(str(spec["enum_from"])):
        raise InvalidArgs(f"{name}: fuera de la lista")
    return value


def validate_args(intent_id: str, args: Any, console: str) -> dict[str, Any]:
    """Los argumentos limpios de una intención del catálogo, o `InvalidArgs` con el motivo.

    Ni un argumento de más: lo que el esquema no declara no se pasa a la interfaz.
    """
    intent = catalog().intents.get(intent_id)
    if intent is None:
        raise InvalidArgs(f"intención fuera del catálogo: {intent_id}")
    if not isinstance(args, dict):
        raise InvalidArgs("los argumentos tienen que ser un objeto")
    extra = set(args) - set(intent.args)
    if extra:
        raise InvalidArgs(f"argumentos que la intención no tiene: {sorted(extra)}")
    clean: dict[str, Any] = {}
    for name, spec in intent.args.items():
        value = args.get(name)
        if value is None:
            if spec.get("optional"):
                continue
            raise InvalidArgs(f"falta {name}")
        clean[name] = _check_value(name, spec, value, console)
    return clean


EXAMPLES_PATH = DATA / "assistant_examples.json"
# Los ejemplos en inglés no son la traducción de los castellanos: son frases de la calle en inglés,
# con las mismas intenciones y los mismos ids, comprobadas contra el catálogo como las otras.
EXAMPLES_EN_PATH = DATA / "assistant_examples.en.json"


@dataclass(frozen=True)
class Example:
    """Una frase de la calle y su intención, para el prompt (`data/assistant_examples.json`)."""

    say: str
    consoles: tuple[str, ...]
    intent: str
    args: dict[str, Any]


def check_examples(raw: dict[str, Any]) -> tuple[Example, ...]:
    """Los ejemplos, comprobados contra el catálogo: un ejemplo que enseña algo que no existe
    enseñaría al modelo a pedirlo."""
    out: list[Example] = []
    for item in raw["examples"]:
        say, intent_id = str(item["say"]), str(item["intent"])
        where = str(item["console"])
        consoles = CONSOLES if where == "any" else (where,)
        if where not in (*CONSOLES, "any"):
            raise CatalogError(f"ejemplo «{say}»: consola {where!r}")
        intent = catalog().intents.get(intent_id)
        if intent is None:
            raise CatalogError(f"ejemplo «{say}»: intención fuera del catálogo")
        args = dict(item["args"])
        for console in consoles:
            if intent.kind == "write" and console != "crew":
                raise CatalogError(f"ejemplo «{say}»: Tierra no prepara escrituras")
            try:
                clean = (valid_subset(intent_id, args, console) if intent.kind == "write"
                         else validate_args(intent_id, args, console))
            except InvalidArgs as exc:
                raise CatalogError(f"ejemplo «{say}»: {exc}") from exc
            if clean != args:
                raise CatalogError(f"ejemplo «{say}»: argumentos fuera del esquema")
            panel = args.get("panel")
            if panel is not None and not catalog().panels[str(panel)].in_console(console):
                raise CatalogError(f"ejemplo «{say}»: el panel no está en la consola {console}")
        out.append(Example(say, consoles, intent_id, args))
    if len({plain(example.say) for example in out}) != len(out):
        raise CatalogError("ejemplo repetido")
    return tuple(out)


@i18n.lang_cache
def examples() -> tuple[Example, ...]:
    raw = _read(EXAMPLES_EN_PATH if i18n.current() == "en" else EXAMPLES_PATH)
    if not _set_aside_active:
        return check_examples(raw)
    # Con pestañas apartadas, un ejemplo que abre una de ellas (o un panel suyo) no se enseña al
    # modelo. Que cada ejemplo sea válido con todas las pestañas lo comprueba la suite, que corre
    # sin apartar; aquí solo se quitan los que el apartado deja sin destino.
    kept: list[Example] = []
    for item in raw["examples"]:
        try:
            kept.extend(check_examples({"examples": [item]}))
        except (CatalogError, KeyError):
            continue
    return tuple(kept)


def is_question(text: str) -> bool:
    """¿Es una pregunta (y no un mando con su verbo)?"""
    return _is_question(text, plain(text))


def valid_subset(intent_id: str, args: Any, console: str) -> dict[str, Any]:
    """Los argumentos que cumplen su esquema, uno a uno; los demás se dejan fuera.

    Para una escritura con argumentos a medias: la propuesta pregunta por lo que falte, y lo que
    no cumple el esquema no llega nunca a ella.
    """
    intent = catalog().intents[intent_id]
    if not isinstance(args, dict):
        return {}
    clean: dict[str, Any] = {}
    for name, value in args.items():
        spec = intent.args.get(name)
        if spec is None or value is None:
            continue
        try:
            clean[name] = _check_value(name, spec, value, console)
        except InvalidArgs:
            continue
    return clean


# --------------------------------------------------------------------------- #
# Sin modelo: palabras clave
# --------------------------------------------------------------------------- #

_NUMBER_WORDS = {
    "cero": 0, "uno": 1, "una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}
_DIGITS = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?")
# Solo verbos de apagar: un «no» o un «sin» sueltos («pon la letra grande, que no veo bien») no
# apagan nada (revisión de código, 2026-11-03).
_OFF = re.compile(r"\b(?:quita\w*|desactiva\w*|apaga\w*|deja de|fuera|no hace falta|"
                  r"normal)\b")
# Levantar el modo seguro. «Sal» solo como verbo seguido de «del»/«de»: «salud» no lo levanta.
_LIFT = re.compile(r"\b(?:levant\w*|quit\w*|desactiv\w*|apag\w*)|\bsal(?:ir)? del?\b")
# «Un», «una» y «uno» son casi siempre artículos («me duele un poco»): no cuentan como el 1.
_ARTICLES = frozenset({"un", "una", "uno"})
# `normalize` no quita la puntuación: se separa para que «estado?» case con «estado».
_PUNCTUATION = re.compile(r"[^\w\s]")
# «Pon la pantalla derecha»: derecha es sin girar (visto con los dos modelos, 2026-11-03: giraban
# a 90). «Boca abajo», media vuelta.
_UPRIGHT = re.compile(r"\b(?:derech\w*|endereza\w*|normal)\b")
_UPSIDE_DOWN = re.compile(r"\b(?:boca abajo|del reves)\b")
# El desplazamiento: hacia dónde, por las palabras.
_SCROLL = (
    ("top", re.compile(r"\b(?:al principio|arriba del todo|al inicio)\b")),
    ("bottom", re.compile(r"\b(?:al final|abajo del todo)\b")),
    ("up", re.compile(r"\b(?:sube\w*|arriba)\b")),
    ("down", re.compile(r"\b(?:baja\w*|abajo|desplaza\w*)\b")),
)
# «EMMA, baja» o «sube» a secas: desplazar. Con más palabras («¿me sube la tensión?») no.
_BARE_SCROLL = frozenset({"baja", "sube", "bajar", "subir", "baja mas", "sube mas"})
# «Siguiente» o «anterior» a secas: el panel de al lado (medido el 2026-11-04: «siguiente» solo
# no casaba con nada y el modelo contestaba «entendido»).
_BARE_STEP = {
    "siguiente": "next_panel", "el siguiente": "next_panel", "la siguiente": "next_panel",
    "otro panel": "next_panel", "adelante": "next_panel",
    "anterior": "previous_panel", "el anterior": "previous_panel",
    "la anterior": "previous_panel", "atras": "previous_panel",
}
# Callar con un plazo es silenciar la iniciativa, no cortar la frase de ahora: «calla un rato que
# estoy concentrado» (medido el 2026-11-04: paraba la voz y nada más).
_FOR_A_WHILE = re.compile(r"\b(?:un rato|un ratito|un tiempo|minutos?|media hora|una hora|"
                          r"un cuarto de hora|hasta luego|hasta nuevo aviso)\b")
_SPOKEN_SPANS = (("media hora", 30), ("un cuarto de hora", 15), ("una hora", 60))
# «¿Dónde se apunta…?» pregunta por el sitio: no es una anotación.
_WHERE_TO_WRITE = re.compile(r"\bdonde (?:se )?(?:apunt|anot)\w*")
# Cómo empieza una pregunta por un término del glosario cuando no dice «qué significa».
_GLOSSARY_OPENERS = ("que es la", "que es el", "que es una", "que es un", "explicame",
                     "que es eso del", "que es lo de")
# Un entorno nombrado tras un «no» no es el que se declara: «estamos en la estación, no yendo a
# Marte» es la estación.
_NEGATED = re.compile(r"\bno(?:\s+\w+){0,2}\s*$")


def plain(text: str) -> str:
    """Texto para emparejar: normalizado, sin puntuación y con un espacio entre palabras."""
    return " " + " ".join(_PUNCTUATION.sub(" ", normalize(text)).split()) + " "


def spoken_numbers(text: str) -> list[float]:
    """Las cifras que dice un texto, en dígitos o en palabra (de cero a cien: «veinte minutos»,
    «noventa grados»; la misma lectura que la barrera de cifras, `guards.spelled_numbers`)."""
    # Import tardío: las barreras no dependen del catálogo, pero se cargan con el modelo.
    from app.assistant.guards import spelled_numbers

    found = [_figure(token) for token in _DIGITS.findall(text)]
    spelled, _ = spelled_numbers(text)
    return found + spelled


# En inglés la coma separa los miles («1,200») y el decimal es el punto; «7,5» se sigue leyendo
# como siete y medio, que es como lo escribe quien teclea con un teclado español.
_THOUSANDS = re.compile(r"\d{1,3},\d{3}")


def _figure(token: str) -> float:
    if i18n.current() == "en" and _THOUSANDS.fullmatch(token):
        return float(token.replace(",", ""))
    return float(token.replace(",", "."))


def _has(words: str, keyword: str) -> bool:
    if i18n.current() == "en":
        # En inglés, palabra entera (con su plural o su tercera persona: «alert» casa con
        # «alerts», «hurt» con «hurts»). Por comienzo, como en castellano, «read» casaría con
        # «reading», «press» con «pressure» y «show» con «shower».
        return f" {keyword} " in words or f" {keyword}s " in words
    return f" {keyword}" in words


def _has_word(words: str, keyword: str) -> bool:
    """Palabra entera: «basta» no está en «bastante», ni «esencial» en «esenciales»."""
    return f" {keyword} " in words


# Las preguntas no mueven la pantalla ni encienden nada: «¿cuál es el siguiente paso?», «¿qué pasó
# al final de la misión Apolo 13?» o «¿la cámara está grabando?» no son mandos (revisión de código
# del 2026-11-03). Salvo que digan el verbo de hacerlo («¿puedes encender…?»).
_QUESTION = re.compile(r"^\s*(?:emma\s+)?(?:que|cual\w*|como|cuando|cuant\w*|donde|quien\w*|"
                       r"por que|hay|es|esta|son|se)\b")
_ACTION = re.compile(r"\b(?:enciend\w*|encender|activ\w*|pon|ponla|ponme|poner|apag\w*|quit\w*|"
                     r"desactiv\w*|deja de|usa|cambia\w*|pasa\w*|ve|vete|lleva\w*|baja\w*|sube\w*|"
                     r"gira\w*|vuelve)\b")
# Los mandos que una pregunta sin verbo de hacer no dispara.
_NOT_FROM_QUESTIONS = frozenset({"next_panel", "previous_panel", "scroll", "switch_console",
                                 "toggle_mode", "privacy", "low_vision", "essential"})


@dataclass(frozen=True)
class _Lexicon:
    """Lo que el emparejamiento sin modelo sabe de un idioma y no es dato del catálogo: cómo se
    apaga, se levanta, se gira y se desplaza, cómo empieza una pregunta y qué verbo la convierte
    en un mando. El castellano es el de las constantes de arriba, sin tocar; el inglés va al lado.
    """

    off: re.Pattern[str]
    lift: re.Pattern[str]
    upright: re.Pattern[str]
    upside_down: re.Pattern[str]
    # De lado, un cuarto de vuelta. En castellano lo resuelve el modelo («de lado»): None.
    sideways: re.Pattern[str] | None
    scroll: tuple[tuple[str, re.Pattern[str]], ...]
    bare_scroll: frozenset[str]
    bare_step: Mapping[str, str]
    for_a_while: re.Pattern[str]
    spoken_spans: tuple[tuple[str, int], ...]
    where_to_write: re.Pattern[str]
    glossary_openers: tuple[str, ...]
    # «What does X mean?»: el término va en medio y no cabe en una palabra clave. None si el
    # idioma lo dice con una frase que empieza («qué significa»).
    glossary_ask: re.Pattern[str] | None
    negated: re.Pattern[str]
    question: re.Pattern[str]
    action: re.Pattern[str]
    fillers: tuple[str, ...]
    guide_word: str
    note_verbs: tuple[str, ...]
    # Las consolas: los alias que no bastan solos para elegir una, y las palabras sueltas que sí.
    console_bare: tuple[str, ...]
    ground_words: tuple[str, ...]
    crew_words: tuple[str, ...]


_SPANISH = _Lexicon(
    off=_OFF, lift=_LIFT, upright=_UPRIGHT, upside_down=_UPSIDE_DOWN, sideways=None,
    scroll=_SCROLL, bare_scroll=_BARE_SCROLL, bare_step=_BARE_STEP, for_a_while=_FOR_A_WHILE,
    spoken_spans=_SPOKEN_SPANS, where_to_write=_WHERE_TO_WRITE,
    glossary_openers=_GLOSSARY_OPENERS, glossary_ask=None, negated=_NEGATED, question=_QUESTION,
    action=_ACTION, fillers=("vale ", "venga ", "pues ", "ahora "), guide_word="guia",
    note_verbs=("apunta", "anota"), console_bare=("tierra", "a bordo"),
    ground_words=("tierra",), crew_words=("a bordo", "tripulacion"),
)

# El inglés. Sobre texto de `plain`: en minúsculas y sin puntuación, así que «don't» llega como
# «don t» y «what's» como «what s».
_ENGLISH = _Lexicon(
    # Solo verbos y partículas de apagar: un «no» suelto («make the text bigger, I can not see»)
    # no apaga nada. «Normal» apaga, como en castellano («normal text»).
    off=re.compile(r"\b(?:off|disable\w*|deactivate\w*|remove|stop|no need|exit|leave|quit|"
                   r"normal)\b"),
    # Levantar el modo seguro. «Off» solo pegado al verbo o al modo: el motivo de activarlo puede
    # decir que algo está «off» («turn on safe mode, the pulse sensor is off»).
    lift=re.compile(r"\b(?:lift\w*|(?:turn|switch) (?:it |safe mode )?off|safe mode off|"
                    r"disable\w*|deactivate\w*|exit|leave|stand down|end safe mode|"
                    r"clear safe mode|out of safe mode)\b"),
    upright=re.compile(r"\b(?:upright|straight|straighten\w*|normal|right way up|"
                       r"right side up)\b"),
    upside_down=re.compile(r"\b(?:upside down|flip\w*|inverted?)\b"),
    sideways=re.compile(r"\b(?:sideways|on its side)\b"),
    scroll=(
        ("top", re.compile(r"\b(?:to the top|the very top|top of the (?:page|screen)|"
                           r"to the beginning|to the start)\b")),
        ("bottom", re.compile(r"\b(?:to the bottom|the very bottom|bottom of the (?:page|screen)|"
                              r"to the end)\b")),
        ("up", re.compile(r"\b(?:up|higher)\b")),
        ("down", re.compile(r"\b(?:down|lower|scroll\w*)\b")),
    ),
    # «EMMA, down» o «up» a secas. Con más palabras («is my blood pressure up?») no.
    bare_scroll=frozenset({"down", "up", "scroll", "scroll down", "scroll up", "go down", "go up",
                           "further down", "further up", "down more", "up more"}),
    bare_step={
        "next": "next_panel", "the next": "next_panel", "next one": "next_panel",
        "the next one": "next_panel", "another panel": "next_panel", "forward": "next_panel",
        "previous": "previous_panel", "the previous": "previous_panel",
        "previous one": "previous_panel", "the previous one": "previous_panel",
        "back": "previous_panel", "go back": "previous_panel",
    },
    for_a_while=re.compile(r"\b(?:a while|a bit|a moment|minutes?|half an hour|half hour|"
                           r"an hour|one hour|a quarter of an hour|until later|"
                           r"until further notice|for now)\b"),
    spoken_spans=(("half an hour", 30), ("half hour", 30), ("a quarter of an hour", 15),
                  ("quarter of an hour", 15), ("an hour", 60), ("one hour", 60)),
    where_to_write=re.compile(r"\bwhere (?:do|can|should|would|does|did) (?:i|we|you|one) "
                              r"(?:\w+ )?(?:log|note|record|write|enter|jot)\w*|"
                              r"\bwhere to (?:log|note|record|write|enter|jot)\w*"),
    glossary_openers=("what is", "what s", "what are", "explain", "tell me about"),
    glossary_ask=re.compile(r"\bwhat (?:does|do|did) .+ (?:mean|means|stand for)\b"),
    negated=re.compile(r"\b(?:not|no|never|isn t|aren t|don t|doesn t|won t)(?:\s+\w+){0,2}\s*$"),
    # «Can you…» y «could you…» son peticiones, no preguntas: no van. Tampoco «do» («do the PVT»).
    question=re.compile(r"^\s*(?:emma\s+)?(?:what|which|how|when|where|who|whose|why|is|are|was|"
                        r"were|does|did|has|have|am)\b"),
    action=re.compile(r"\b(?:turn|switch|activate\w*|enable\w*|disable\w*|deactivate\w*|put|set|"
                      r"use|change\w*|go|take me|bring|scroll\w*|rotate\w*|flip\w*|hide|"
                      r"make)\b"),
    fillers=("ok ", "okay ", "right ", "well ", "so ", "now ", "please ", "hey "),
    guide_word="guide",
    # «Log» a secas no: es también el nombre de una pestaña («open the log»).
    note_verbs=("note down", "write down", "jot down", "make a note", "note that", "log that",
                "log my", "log it", "log a", "record that", "record my", "record it"),
    console_bare=("crew", "ground", "on board"),
    ground_words=("ground", "earth"),
    crew_words=("on board", "onboard", "crew"),
)


def _lex() -> _Lexicon:
    """La gramática del emparejamiento en el idioma de la petición."""
    return _ENGLISH if i18n.current() == "en" else _SPANISH


def _is_question(text: str, words: str) -> bool:
    lex = _lex()
    return ("?" in text or bool(lex.question.search(words))) and not lex.action.search(words)


def _section_for(words: str, console: str) -> str | None:
    found = _section_match(words, console)
    return found[0] if found is not None else None


def _section_match(words: str, console: str) -> tuple[str, int] | None:
    """La primera pestaña que nombra el texto y lo largo de la palabra con que la nombra."""
    if i18n.current() == "en":
        return _longest_section(words, console)
    for section in catalog().sections[console]:
        matched = [len(keyword) for keyword in section.keywords if _has(words, keyword)]
        if matched:
            return section.key, max(matched)
    return None


def _longest_section(words: str, console: str) -> tuple[str, int] | None:
    """En inglés, la pestaña del nombre más largo; a igualdad, la primera.

    La pestaña «Environment» de a bordo se llama «environment» y las de entorno de misión,
    «mission environment»: la primera que casa abriría siempre la de la nave, también cuando se
    pide el entorno de la misión. El castellano no tiene ese choque y se queda como estaba.
    """
    best: tuple[str, int] | None = None
    for section in catalog().sections[console]:
        matched = [len(keyword) for keyword in section.keywords if _has(words, keyword)]
        if matched and (best is None or max(matched) > best[1]):
            best = (section.key, max(matched))
    return best


def profile_for(words: str) -> str | None:
    """El entorno que nombra el texto: el de la palabra clave más larga («superficie de marte»
    gana a «marte»)."""
    best: tuple[int, str] | None = None
    for key, keywords in catalog().profile_keywords.items():
        for keyword in keywords:
            if not _has(words, keyword) or _negated(words, keyword):
                continue
            if best is None or len(keyword) > best[0]:
                best = (len(keyword), key)
    return best[1] if best is not None else None


def _negated(words: str, keyword: str) -> bool:
    """¿Va la palabra clave detrás de un «no» (a dos palabras como mucho) cada vez que sale?"""
    starts = [match.start() for match in re.finditer(re.escape(f" {keyword}"), words)]
    negated = _lex().negated
    return bool(starts) and all(negated.search(words[:start]) for start in starts)


def _diary_args(text: str, words: str) -> dict[str, Any]:
    """El indicador del diario que nombran las palabras («ánimo», «agobiado») y el valor dicho."""
    best: tuple[int, str] | None = None
    for key, keywords in catalog().diary_keywords.items():
        for keyword in keywords:
            if _has(words, keyword) and (best is None or len(keyword) > best[0]):
                best = (len(keyword), key)
    args: dict[str, Any] = {}
    if best is not None:
        args["key"] = best[1]
        values = spoken_numbers(text)
        if values:
            args["value"] = values[0]
    return args


def domain_for(words: str) -> str | None:
    """El dominio que nombra el texto, por su nombre o por sus palabras de la calle."""
    best: tuple[int, str] | None = None
    for key, keywords in catalog().domain_keywords.items():
        for keyword in (plain(Domain(key).display).strip(), *keywords):
            if _has(words, keyword) and (best is None or len(keyword) > best[0]):
                best = (len(keyword), key)
    return best[1] if best is not None else None


def level_for(words: str) -> str | None:
    """El nivel de misión que piden las palabras («hay que recortar» es reducido), o None."""
    for level, keywords in catalog().level_keywords.items():
        if any(_has(words, keyword) for keyword in keywords):
            return level
    return None


def silence_minutes(text: str) -> int | None:
    """Los minutos de un «calla media hora» o «silencio diez minutos», si los dice."""
    words = plain(text)
    for phrase, minutes in _lex().spoken_spans:
        if f" {phrase} " in words:
            return minutes
    found = [int(n) for n in spoken_numbers(text) if 1 <= n <= 120 and n == int(n)]
    return found[0] if found else None


def _guide_for(words: str) -> str | None:
    for key, keywords in catalog().guide_keywords.items():
        if any(_has(words, keyword) for keyword in keywords):
            return key
    return None


def _toggle(words: str) -> bool:
    return not _lex().off.search(words)


def panel_for(words: str, console: str, *, only_here: bool = False) -> str | None:
    """El panel que nombra el texto: el del alias más largo; a igualdad, el de esta consola.

    `only_here`: solo los que se montan en esta consola (una pregunta no cambia de consola).
    """
    found = _panel_match(words, console, only_here=only_here)
    return found[0] if found is not None else None


def _panel_match(words: str, console: str, *, only_here: bool = False) -> tuple[str, int] | None:
    """Como `panel_for`, con lo largo del alias que casó."""
    best: tuple[int, int, str] | None = None
    for panel in catalog().panels.values():
        here = panel.in_console(console)
        if only_here and not here:
            continue
        for alias in panel.aliases:
            if f" {alias} " in words:
                score = (len(alias), 1 if here else 0, panel.id)
                if best is None or score[:2] > best[:2]:
                    best = score
    return (best[2], best[0]) if best is not None else None


def _mode_for(words: str) -> str | None:
    """El modo de pantalla que nombra el texto, por el alias más largo."""
    best: tuple[int, str] | None = None
    for mode in catalog().modes.values():
        for alias in mode.aliases:
            if _has_word(words, alias) and (best is None or len(alias) > best[0]):
                best = (len(alias), mode.id)
    return best[1] if best is not None else None


def _console_for(words: str, console: str) -> str:
    """La consola que nombra el texto, o la otra si no nombra ninguna («cambia de consola»)."""
    lex = _lex()
    for ref in catalog().consoles.values():
        if any(_has(words, alias) for alias in ref.aliases if alias not in lex.console_bare):
            return ref.id
    if any(_has(words, word) for word in lex.ground_words):
        return "ground"
    if any(_has(words, word) for word in lex.crew_words):
        return "crew"
    return "ground" if console == "crew" else "crew"


def glossary_term_for(words: str) -> str | None:
    """El término del glosario que nombra el texto: por su nombre, sus siglas entre paréntesis o
    su nombre sin la última palabra («línea base» es «Línea base personal»)."""
    best: tuple[int, str] | None = None
    spoken = catalog().glossary_keywords
    for term in guides.glossary()["terms"]:
        name = str(term["term"])
        base = plain(re.sub(r"\([^)]*\)", " ", name)).strip()
        names = {base, *(plain(inner).strip() for inner in re.findall(r"\(([^)]*)\)", name))}
        parts = base.split()
        if len(parts) >= 3 and len(parts[-2]) > 3:
            names.add(" ".join(parts[:-1]))
        names.update(spoken.get(str(term["id"]), ()))
        for alias in names:
            if alias and f" {alias} " in words and (best is None or len(alias) > best[0]):
                best = (len(alias), str(term["id"]))
    return best[1] if best is not None else None


def _scroll_direction(words: str) -> str:
    for direction, pattern in _lex().scroll:
        if pattern.search(words):
            return direction
    return "down"


def _mode_intent(mode_id: str, words: str) -> tuple[str, dict[str, Any]]:
    mode = catalog().modes[mode_id]
    if mode.intent == "rotate":
        return "rotate", {}  # lo resuelve la rama de `rotate`, con los grados
    if mode.intent == "toggle_mode":
        return "toggle_mode", {"mode": mode.id, "on": _toggle(words)}
    return mode.intent, {"on": _toggle(words)}


def keyword_intent(
    text: str, console: str, modes: Mapping[str, bool] | None = None
) -> tuple[str, dict[str, Any]]:
    """La intención por palabras clave y los argumentos que se pueden sacar sin modelo.

    Una escritura sale sin argumentos completos: la propuesta dirá qué falta. Lo que no casa con
    nada es «none». `modes`: los modos de pantalla que la consola dice tener puestos ahora; con
    ellos, «ya se han ido» levanta la privacidad (sin ellos no se adivina).
    """
    words = plain(text)
    cat = catalog()
    lex = _lex()
    bare = words.replace(" emma ", " ").strip()
    for filler in lex.fillers:
        bare = bare.removeprefix(filler)
    if bare in lex.bare_scroll:
        return "scroll", {"direction": _scroll_direction(words)}
    if bare in lex.bare_step:
        return lex.bare_step[bare], {}
    if modes and modes.get("privacy") and any(_has(words, phrase) for phrase in cat.privacy_off):
        return "privacy", {"on": False}
    names_panel = any(_has(words, word) for word in cat.panel_words)
    # Leer un panel: «lee el panel de radiación». Sin la palabra «panel», «léeme las alertas» es
    # leer las alertas, no el panel.
    if names_panel and any(_has(words, verb) for verb in cat.read_verbs):
        panel = panel_for(words, console)
        if panel is not None:
            return "read_panel", {"panel": panel}
    # Una pregunta por un panel de esta consola: «¿qué tal la radiación hoy?» lee el de la dosis.
    if any(_has(words, word) for word in cat.question_words):
        panel = panel_for(words, console, only_here=True)
        if panel is not None and cat.panels[panel].kind == "panel":
            return "read_panel", {"panel": panel}
    if any(_has(words, verb) for verb in cat.open_verbs):
        guide = _guide_for(words) if _has(words, lex.guide_word) else None
        if guide is not None:
            return "open_guide", {"topic": guide}
        writes = (any(_has(words, verb) for verb in lex.note_verbs)
                  and not lex.where_to_write.search(words))
        section_found = _section_match(words, console)
        panel_found = _panel_match(words, console)
        section = section_found[0] if section_found else None
        panel = panel_found[0] if panel_found else None
        # El panel gana si se pide con la palabra «panel» o si su nombre es más largo que el de la
        # pestaña: «abre los informes escaneados» es el panel, «abre los informes» la pestaña.
        specific = bool(panel_found and section_found and panel_found[1] > section_found[1])
        if not writes and panel is not None and (names_panel or section is None or specific):
            return "open_panel", {"panel": panel}
        if section is not None and not writes:
            return "open_tab", {"section": section}
    question = _is_question(text, words)
    for intent in cat.intents.values():
        if question and intent.id in _NOT_FROM_QUESTIONS:
            continue
        if intent.id == "toggle_mode":
            mode = _mode_for(words)
            if mode is not None:
                found, mode_args = _mode_intent(mode, words)
                if found != "rotate":
                    return found, mode_args
                return _rotation(text, words)
            continue
        # Los mandos que mandan sin modelo casan por palabra entera; los demás, por comienzo
        # («atrasad» casa con «atrasadas»).
        matches = _has_word if intent.keywords_first else _has
        said = any(matches(words, keyword) for keyword in intent.keywords)
        if not said and intent.id == "mission_profile" and not question:
            # «En realidad estamos en la estación espacial»: un entorno nombrado tras «estamos en».
            said = (any(_has(words, trigger) for trigger in cat.profile_triggers)
                    and profile_for(words) is not None)
        if intent.id == "diary_entry" and lex.where_to_write.search(words):
            said = False  # «¿dónde se apunta lo que como?» pregunta dónde, no pide anotar
        if not said and intent.id == "open_glossary":
            # «¿Qué es la tasa de falsa alarma?»: un «qué es» suelto solo si nombra un término.
            said = (any(_has(words, opener) for opener in lex.glossary_openers)
                    and glossary_term_for(words) is not None)
            if not said and lex.glossary_ask is not None:
                said = bool(lex.glossary_ask.search(words))
        if not said:
            continue
        if intent.id == "diary_entry":
            return "diary_entry", _diary_args(text, words)
        if intent.id == "stop_voice" and lex.for_a_while.search(words):
            minutes = silence_minutes(text)
            return "silence", ({"minutes": minutes} if minutes else {})
        if intent.id == "acknowledge_alert":
            domain = domain_for(words)
            return "acknowledge_alert", ({"domain": domain} if domain else {})
        if intent.id == "mission_level":
            level = level_for(words)
            return "mission_level", ({"level": level} if level else {})
        if intent.id == "rotate":
            return _rotation(text, words)
        if intent.id in ("privacy", "low_vision", "essential"):
            return intent.id, {"on": _toggle(words)}
        if intent.id == "silence":
            minutes = silence_minutes(text)
            return "silence", ({"minutes": minutes} if minutes else {})
        if intent.id == "open_guide":
            guide = _guide_for(words)
            return "open_guide", ({"topic": guide} if guide else {})
        if intent.id == "open_glossary":
            term = glossary_term_for(words)
            return "open_glossary", ({"term": term} if term else {})
        if intent.id == "switch_console":
            return "switch_console", {"console": _console_for(words, console)}
        if intent.id == "scroll":
            return "scroll", {"direction": _scroll_direction(words)}
        if intent.id == "safe_mode":
            return "safe_mode", {"active": not lex.lift.search(words)}
        if intent.id == "mission_profile":
            profile = profile_for(words)
            return "mission_profile", ({"profile": profile} if profile else {})
        if intent.id == "pain_report":
            zone = zone_for(words)
            intensities = [int(n) for n in spoken_numbers(text)
                           if 0 <= n <= MAX_INTENSITY and n == int(n)]
            args: dict[str, Any] = {}
            if zone is not None:
                args["zone"] = zone
            if intensities:
                args["intensity"] = intensities[0]
            return "pain_report", args
        return intent.id, {}
    return "none", {}


def _rotation(text: str, words: str) -> tuple[str, dict[str, Any]]:
    degrees = [int(n) for n in spoken_numbers(text) if n in ROTATIONS]
    if degrees:
        return "rotate", {"degrees": degrees[0]}
    lex = _lex()
    if lex.upside_down.search(words):
        return "rotate", {"degrees": 180}
    if lex.sideways is not None and lex.sideways.search(words):
        return "rotate", {"degrees": 90}
    if lex.upright.search(words):
        return "rotate", {"degrees": 0}
    return "none", {}


def zone_said(zone: str, words: str) -> str | None:
    """Las palabras con que el texto nombra ESTA zona del dolor (`routing.zone_keywords`), o None.

    Para la propuesta de dolor: la zona tiene que estar en lo que dijo la persona, y en inglés
    «my left knee» la nombra aunque el nombre de la zona llegue en otro idioma.
    """
    said = [keyword for keyword in catalog().zone_keywords.get(zone, ()) if _has(words, keyword)]
    return max(said, key=len) if said else None


def zone_for(words: str) -> str | None:
    """La zona del dolor que nombra el texto: por sus palabras del catálogo (la más larga: «left
    knee» gana a «knee») o, si no las hay o no casan, por el nombre de la zona."""
    best: tuple[int, str] | None = None
    for key, keywords in catalog().zone_keywords.items():
        for keyword in keywords:
            if _has(words, keyword) and (best is None or len(keyword) > best[0]):
                best = (len(keyword), key)
    if best is not None:
        return best[1]
    return next((key for key, item in ZONES.items()
                 if _has(words, normalize(item.display))), None)
