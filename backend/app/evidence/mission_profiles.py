"""El perfil de misión: qué se sabe del sitio adonde se va, por fuente leída. Solo descriptivo.

La base de conocimiento del equipo (`docs/contexto/knowledge-base-v1.md` §3) compara estación,
Luna y Marte en una matriz, y la especificación (§3, MissionContext) pide `location`,
`gravity_regime` y `comm_delay`. EMMA tenía de eso dos cosas sueltas: un texto libre
(`EMMA_GRAVITY_REGIME`) y un código de efemérides (`EMMA_TARGET_BODY`). Nadie decía a qué clase
de misión correspondían ni qué se sabe de ella, y una matriz así, escrita de memoria, es justo
la clase de tabla que acaba con una cifra inventada en una casilla.

Aquí cada perfil lleva, de cada aspecto, **solo lo que un documento oficial dice**, con la frase
literal, su URL, su apartado y el día en que se leyó. Lo que no se encontró escrito queda «sin
verificar» y dice qué se buscó: la carga rechaza un aspecto leído sin cita y uno sin verificar
que no diga dónde se miró. Cuando dos páginas discrepan, van las dos.

EL ENTORNO DE RADIACIÓN (2026-10-21)
------------------------------------
La base de conocimiento (§2.1, RIDGE) pone la radiación la primera de los cinco peligros, y su
escalera de §3 separa la estación de la Luna y Marte, que salen de la magnetosfera. Cada perfil
lleva ese aspecto con su frase leída, y el ciclo solar con la suya. Lo que el perfil no puede
decir es qué parte de la dosis que EMMA enseña viene de cada componente: la tasa medida los mezcla
y EMMA no los separa. Esa nota es de EMMA, no de una fuente, y se sirve aparte (`emma_note`) para
que no se confunda con lo leído.

DESCRIPTIVO: NO ESCALA EL RIESGO (decisión del usuario, 2026-10-13)
-------------------------------------------------------------------
El riesgo se escala con el tiempo de luz REAL de las efemérides (`analysis/risk.py`), no con lo
que diga un perfil: «hasta 20 minutos» es una frase de una página, no una medida de hoy. Este
módulo no lo importa nadie de `app/analysis` ni de `app/advisor`, y una prueba lo fija
(`tests/test_mission_profile.py`). Por eso tampoco entra en `rules_version`: no es una regla.

EL PERFIL DECIDE HACIA DÓNDE SE MIDE (decisión del usuario, 2026-11-11)
-----------------------------------------------------------------------
Lo único del perfil que actúa es su `ephemeris_target`: hacia qué cuerpo se calcula ese tiempo de
luz real. Antes eran dos ajustes sueltos (`EMMA_MISSION_PROFILE` y `EMMA_TARGET_BODY`), y con
órbita baja declarada el riesgo se escalaba con el tiempo de luz de Marte mientras la consola
decía «no casan». Ahora `ephemeris_target` es el único punto que da el objetivo, y todo lo que
consulta efemérides (el estado, `/api/comms`, la cobertura, la precarga) pasa por él; ningún otro
módulo lee `EMMA_TARGET_BODY` (`tests/test_mission_profile.py` lo fija), que ya no manda y, si
difiere, se dice que se ignora. Un perfil sin objetivo (órbita baja, cislunar, superficie lunar:
la Luna no está anotada en EMMA) no consulta Horizons ni su caché: el retardo no se calcula, el
riesgo no se escala con ningún tiempo de luz (factor de aislamiento 1) y la conjunción solar no
aplica, y se dice así, no como «sin efemérides». Cambiar de perfil mueve, por tanto, el factor de
aislamiento cuando cambia el objetivo, y nada más: los niveles se calculan igual que con el
tiempo de luz de ese cuerpo. La validación externa (`app/validation`) llama al motor sin tiempo
de luz, así que sus dos métricas no cambian (invariante 5).

El perfil de partida es el de la configuración (`EMMA_MISSION_PROFILE`). Desde el 2026-11-04 se
puede cambiar en marcha: cada cambio es un asiento firmado `mission-profile`
(`core/mission_profile_changes.py`, `POST /api/mission/profile`), y vale el último. Describe el
despliegue, no es una observación ni una decisión clínica. Desde el 2026-11-11 el perfil vigente
decide además el cuerpo de las efemérides (ver abajo), así que ya no pueden no casar.

LOS PERFILES LADO A LADO (2026-10-23)
-------------------------------------
La base de conocimiento (§15, P1) pide la matriz «ISS vs Artemis vs Mars» de requisitos y
autonomía, y hasta aquí solo se servía el perfil declarado. `compare()` los sirve todos con los
mismos aspectos, para la consola de Tierra. Lleva un octavo aspecto, la capacidad o autonomía
médica, que tiene una regla más que los demás: se construye SOLO con frases que EMMA ya había
leído para otra cosa (otro aspecto del mismo perfil o el marco de NASA leído), y la carga rechaza
una frase que no esté en ninguno de los dos. Así la casilla no es una lectura nueva hecha a
medias, y cada cita dice para qué se leyó primero (`reused_from`, también en el perfil declarado
de `/api/status`). Los niveles de asistencia
médica IV y V no se asignan a ningún perfil como cualidad suya: lo único leído que los pone junto a
un destino concreto es una diapositiva de 2017, y se cita como tal (`MEDICAL_NOTE`).
Lo que ningún perfil dice queda «EMMA no tiene fuente». Igual de descriptivo que lo demás: nada
que decida lee este aspecto (`tests/test_mission_profile_matrix.py`).

LA SUPERFICIE DE MARTE (2026-11-01)
-----------------------------------
La conversación de ideación del equipo distingue el trayecto de la estancia, y hasta aquí lo
dicho de la superficie cabía solo como aclaración del tránsito. Es un cuarto perfil con las
mismas reglas: cada aspecto con su frase, la discrepancia «un tercio» frente a «tres octavos» con
las dos fuentes y sin elegir, y descriptivo como los demás. Comparte con el tránsito el cuerpo de
efemérides: el riesgo sigue saliendo del tiempo de luz real, no de este perfil.

EL ESPACIO CISLUNAR (2026-11-03)
--------------------------------
La interfaz que describió el equipo separa las vistas por entorno —dentro de la magnetosfera,
espacio cislunar, Luna y Marte—, y el enunciado del reto nombra la nave además de la estación y la
base. Entre la órbita baja y la superficie lunar faltaba el tramo en que la tripulación vive en
Orion: el tránsito y el vuelo alrededor de la Luna de Artemis II, el único vuelo tripulado de esa
clase que ya ha ocurrido. Mismas reglas que los demás: cada aspecto con su frase, la capacidad
médica solo con frases ya leídas, y sin cuerpo de efemérides (la Luna no está anotada en EMMA,
como en el perfil lunar). Gateway no se da por parte de las misiones de hoy: la frase que lo
nombra es un plan de 2021, y su página avisa de que se está actualizando tras la reorganización
de Artemis de 2026.

EL POLVO Y EL CICLO DE DÍA Y NOCHE (2026-11-03)
-----------------------------------------------
La consola va a tener una pestaña por entorno, y lo que distingue una superficie de una nave no
cabía en los ocho aspectos: el polvo (el regolito lunar, el polvo de Marte con percloratos) y la
luz (16 amaneceres al día en la estación, dos semanas de luz y dos de noche en el ecuador lunar,
el sol de Marte). Son dos aspectos más con las mismas reglas. Donde ninguna frase leída habla de
ellos —el polvo a bordo de una nave, la luz durante un tránsito— quedan sin verificar con lo que
se buscó: que en una nave no haya polvo de superficie sería una deducción de EMMA, no una lectura.
Descriptivos como los demás: el límite de exposición al polvo lunar que cita la casilla no lo lee
ninguna regla.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core import display, i18n
from app.evidence import nasa_framework, registry

if TYPE_CHECKING:
    from app.core.config import Settings

PROFILES_PATH = Path(__file__).resolve().parents[1] / "data" / "mission_profiles.json"

# Los perfiles, en el orden de la escalera Tierra → estación → espacio cislunar → Luna → Marte.
EXPECTED_IDS = ("leo", "cislunar", "lunar-surface", "mars-transit", "mars-surface")

# Qué se dice de cada perfil, con el rótulo que ve la tripulación. Todo perfil lleva todos.
ASPECTS: dict[str, str] = {
    "comm_delay": "retardo de comunicaciones",
    "gravity_regime": "régimen de gravedad",
    "return_or_evacuation": "regreso o evacuación",
    "resupply": "reabastecimiento",
    "typical_duration": "duración",
    "distance": "distancia",
    "radiation_environment": "entorno de radiación",
    "surface_dust": "polvo de superficie",
    "day_night_cycle": "ciclo de día y noche",
    "medical_capability": "capacidad o autonomía médica",
}
i18n.en_many({
    ASPECTS["comm_delay"]: "communication delay",
    ASPECTS["gravity_regime"]: "gravity regime",
    ASPECTS["return_or_evacuation"]: "return or evacuation",
    ASPECTS["resupply"]: "resupply",
    ASPECTS["typical_duration"]: "duration",
    ASPECTS["distance"]: "distance",
    ASPECTS["radiation_environment"]: "radiation environment",
    ASPECTS["surface_dust"]: "surface dust",
    ASPECTS["day_night_cycle"]: "day and night cycle",
    ASPECTS["medical_capability"]: "medical capability or autonomy",
})

# Los aspectos que se construyen solo con frases ya leídas para otra cosa (ver cabecera): cada cita
# suya repite, con la misma ficha, la misma frase y el mismo día, una de otro aspecto del catálogo
# o una del marco de NASA leído. Una lectura nueva va a su aspecto propio, no aquí.
REUSED_ONLY = frozenset({"medical_capability"})

# Lo que se enseña en la matriz donde un perfil no tiene frase leída de un aspecto.
NO_SOURCE = "EMMA no tiene fuente"
i18n.en(NO_SOURCE, "EMMA has no source")

# Lo que EMMA dice de la capacidad médica al lado de la matriz. No sale de ninguna fuente.
MEDICAL_NOTE = (
    "Nota de EMMA: los niveles de asistencia médica IV y V del marco de NASA leído no se asignan "
    "aquí a ningún perfil como cualidad suya. Las definiciones que cita el memorando "
    "NASA/TM-2017-219290 los describen por capacidades y por riesgo. Lo único leído que los pone "
    "junto a un destino concreto es una diapositiva de 2017 que rotula la Revisión A de la norma "
    "(«Lunar > 30 day», «Mars Expedition»), y las casillas la citan como tal; la norma vigente ya "
    "no los define: decir que un perfil tiene tal nivel sería una deducción de EMMA, no una frase "
    "leída."
)
i18n.en(
    MEDICAL_NOTE,
    "EMMA's note: levels of care IV and V of the NASA framework as read are not assigned here to "
    "any profile as a quality of its own. The definitions quoted by memorandum "
    "NASA/TM-2017-219290 describe them by capabilities and by risk. The only thing read that "
    "places them next to a specific destination is a 2017 slide labeling Revision A of the "
    "standard («Lunar > 30 day», «Mars Expedition»), and the cells cite it as such; the current "
    "standard no longer defines them: saying that a profile has a given level would be a "
    "deduction by EMMA, not a sentence it read.",
)
REUSED_NOTE = (
    "La capacidad o autonomía médica se construye solo con frases que EMMA ya había leído para "
    "otra cosa; cada casilla dice para qué se leyó primero."
)
i18n.en(
    REUSED_NOTE,
    "Medical capability or autonomy is built only from sentences EMMA had already read for "
    "something else; each cell says what it was first read for.",
)

# Lo que EMMA dice de sí mismo junto a un aspecto: no sale de ninguna fuente y no lleva cita.
EMMA_NOTES: dict[str, str] = {
    "radiation_environment": (
        "Nota de EMMA: la tasa de dosis medida mezcla los componentes de la radiación; EMMA no "
        "los separa, y por eso no dice qué parte viene de dentro o de fuera de la magnetosfera ni "
        "cuánto pesa el ciclo solar."
    ),
}
i18n.en(
    EMMA_NOTES["radiation_environment"],
    "EMMA's note: the measured dose rate mixes the components of the radiation; EMMA does not "
    "separate them, so it does not say which part comes from inside or outside the "
    "magnetosphere or how much the solar cycle weighs.",
)

READ = "read"
UNVERIFIED = "unverified"
STATUSES = {
    READ: "leído en la fuente",
    UNVERIFIED: "sin verificar",
}
i18n.en_many({STATUSES[READ]: "read in the source", STATUSES[UNVERIFIED]: "unverified"})

DESCRIPTIVE = (
    "descriptivo: lo que dice de cada aspecto no cambia el riesgo; el perfil solo decide hacia "
    "qué cuerpo se calcula el tiempo de luz real, que es lo que lo escala"
)
i18n.en(
    DESCRIPTIVE,
    "descriptive: what it says about each aspect does not change the risk; the profile only "
    "decides toward which body the real light time is calculated, which is what scales it",
)
DECLARED_NOTE = (
    "El entorno de partida es el de la configuración (EMMA_MISSION_PROFILE); cada cambio es un "
    "asiento firmado del registro (`mission-profile`), con quién lo declara. Describe el "
    "despliegue: no es una observación ni una decisión clínica. Lo único que cambia del análisis "
    "es hacia qué cuerpo se calcula el tiempo de luz con que se escala el riesgo."
)
i18n.en(
    DECLARED_NOTE,
    "The starting environment is the one in the configuration (EMMA_MISSION_PROFILE); each "
    "change is a signed entry of the record (`mission-profile`), with who declares it. It "
    "describes the deployment: it is not an observation or a clinical decision. The only thing "
    "it changes in the analysis is toward which body the light time that scales the risk is "
    "calculated.",
)

# Los cuerpos de efemérides que EMMA tiene anotados con su nombre (`.env.example`). De otro
# código no se dice a qué cuerpo corresponde: no se rellena de memoria.
KNOWN_TARGETS = {"499": "Marte"}
i18n.en(KNOWN_TARGETS["499"], "Mars")

# El estado de las efemérides del perfil. Desde el 2026-11-11 el perfil decide el objetivo, así
# que «no casan» ya no puede darse: o el perfil tiene objetivo y se calcula hacia él, o no lo
# tiene y no se calcula.
CONSISTENT = "consistent"
NO_TARGET = "no_target"

_CITATION_KEYS = {"ref", "section", "quote", "read_on"}
_ASPECT_KEYS = {"status", "statement", "citations", "discrepancy", "searched"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_citation(where: str, cite: dict[str, Any]) -> None:
    if set(cite) != _CITATION_KEYS:
        raise ValueError(f"{where}: una cita lleva exactamente {sorted(_CITATION_KEYS)}")
    for key in ("section", "quote"):
        if not _text(cite[key]):
            raise ValueError(f"{where}: cita sin `{key}`: sin frase y apartado no hay cita")
    # El título y la URL del documento viven en su ficha del registro de evidencia: aquí se
    # cita por identificador y no se escribe otra copia. Citar una ficha que no existe falla.
    registry.get(cite["ref"])
    dt.date.fromisoformat(cite["read_on"])


def _validate_aspect(where: str, aspect: dict[str, Any]) -> None:
    if set(aspect) != _ASPECT_KEYS:
        raise ValueError(f"{where}: un aspecto lleva exactamente {sorted(_ASPECT_KEYS)}")
    if aspect["status"] not in STATUSES:
        raise ValueError(f"{where}: estado desconocido {aspect['status']!r}")
    for cite in aspect["citations"]:
        _validate_citation(where, cite)
    if aspect["status"] == READ:
        if not _text(aspect["statement"]) or not aspect["citations"]:
            raise ValueError(f"{where}: un dato leído lleva lo que dice la fuente y su cita")
    else:
        if aspect["statement"] is not None or aspect["citations"]:
            raise ValueError(f"{where}: lo que está sin verificar no afirma nada ni cita nada")
        if not _text(aspect["searched"]):
            raise ValueError(f"{where}: sin verificar tiene que decir qué se buscó y dónde")
    discrepancy = aspect["discrepancy"]
    if discrepancy is not None:
        if not _text(discrepancy.get("text")) or not discrepancy.get("citations"):
            raise ValueError(f"{where}: una discrepancia lleva su texto y la cita que discrepa")
        for cite in discrepancy["citations"]:
            _validate_citation(where, cite)


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza un catálogo que afirme algo sin su frase, o que calle lo que no encontró."""
    dt.date.fromisoformat(raw["source"]["read_on"])
    # Una nota de EMMA pegada a un aspecto que no existe se perdería sin que nadie lo viera.
    if not set(EMMA_NOTES) <= set(ASPECTS):
        orphan = sorted(set(EMMA_NOTES) - set(ASPECTS))
        raise ValueError(f"nota de EMMA de un aspecto desconocido: {orphan}")
    found = tuple(profile["id"] for profile in raw["profiles"])
    if found != EXPECTED_IDS:
        raise ValueError(f"se esperaban los perfiles {EXPECTED_IDS} en ese orden, y hay {found}")
    for profile in raw["profiles"]:
        key = profile["id"]
        if not _text(profile["display"]):
            raise ValueError(f"{key}: falta el nombre que se enseña")
        target = profile["ephemeris_target"]
        if target is not None and target not in KNOWN_TARGETS:
            raise ValueError(f"{key}: el código de efemérides {target!r} no está anotado en EMMA")
        if tuple(profile["aspects"]) != tuple(ASPECTS):
            raise ValueError(f"{key}: los aspectos son {tuple(ASPECTS)}, en ese orden")
        for name, aspect in profile["aspects"].items():
            _validate_aspect(f"{key}.{name}", aspect)
    # La lista de páginas citadas es la de las citas, ni una más ni una menos: una página
    # «citada» de la que no se copió ninguna frase daría respaldo de oídas.
    if set(raw["source"]["pages_cited"]) != _refs(raw):
        raise ValueError("`pages_cited` no coincide con las fichas que citan los perfiles")
    _validate_reused(raw)
    for page in raw["source"]["pages_read_without_citation"]:
        if not _text(page.get("title")) or not str(page.get("url", "")).startswith("https://"):
            raise ValueError("una página leída lleva su título y su URL")
        # Sin cita no hay otro sitio donde conste cuándo se leyó: lo lleva la página.
        if not page.get("read_on"):
            raise ValueError("una página leída sin cita lleva los días en que se leyó")
        for day in page["read_on"]:
            dt.date.fromisoformat(day)
    return raw


def _aspect_citations(aspect: dict[str, Any]) -> list[dict[str, Any]]:
    extra = aspect["discrepancy"]["citations"] if aspect["discrepancy"] else []
    return [*aspect["citations"], *extra]


Key = tuple[str, str, str, str]


def _catalog_place(name: str, display_name: str) -> str:
    """El sitio de una frase leída para un aspecto propio, como se enseña en `reused_from`.

    Se redacta en el idioma de la petición. La carga (`catalog`, cacheada) también pasa por aquí al
    validar, pero solo mira si cada cita tiene algún sitio y no guarda el texto: nada queda
    congelado en el idioma del primero que pasó.
    """
    return i18n.tr(
        f"«{ASPECTS[name]}» de «{display_name}»",
        f"«{i18n.loc(ASPECTS[name])}» of «{i18n.localized(display_name, PROFILES_PATH)}»",
    )


def _framework_place(title: str) -> str:
    """El sitio de una frase del marco de NASA leído. El título del bloque es de
    `nasa_framework`: su inglés, si lo tiene, es el de su fichero hermano."""
    return i18n.tr(
        f"marco de NASA leído: «{title}»",
        f"NASA framework as read: «{i18n.localized(title, nasa_framework.READ_PATH)}»",
    )


def _key(cite: dict[str, Any]) -> Key:
    """Qué hace de dos citas la misma lectura: ficha, apartado, frase y día."""
    return (cite["ref"], cite["section"], cite["quote"], cite["read_on"])


def _reused_citations(raw: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Cada cita de un aspecto de `REUSED_ONLY`, con su perfil y su aspecto."""
    return [
        (profile["id"], name, cite)
        for profile in raw["profiles"]
        for name in REUSED_ONLY
        for cite in _aspect_citations(profile["aspects"][name])
    ]


def _catalog_places(raw: dict[str, Any]) -> dict[Key, list[tuple[str, str]]]:
    """Cada frase leída para un aspecto propio del catálogo: (ficha, apartado, frase, día) →
    (perfil, sitio). Los aspectos de `REUSED_ONLY` no cuentan: una frase no se respalda a sí misma.
    """
    found: dict[Key, list[tuple[str, str]]] = {}
    for profile in raw["profiles"]:
        for name, aspect in profile["aspects"].items():
            if name in REUSED_ONLY:
                continue
            for cite in _aspect_citations(aspect):
                where = _catalog_place(name, profile["display"])
                found.setdefault(_key(cite), []).append((profile["id"], where))
    return found


def _framework_places() -> dict[Key, list[str]]:
    """Cada frase del marco de NASA leído, con su bloque. El marco no es de ningún destino."""
    framework = nasa_framework.read()
    found: dict[Key, list[str]] = {}
    for block in framework["blocks"]:
        for item in block["statements"]:
            # El apartado de una frase del marco es su `where`, tal como se anotó al leerla.
            key = (item["ref"], item["where"], item["quote"],
                   nasa_framework.read_on(framework, item["ref"]))
            found.setdefault(key, []).append(_framework_place(block["title"]))
    return found


def _first_read(raw: dict[str, Any]) -> dict[tuple[str, Key], list[str]]:
    """Para qué se leyó primero cada cita de `REUSED_ONLY`: (perfil, cita) → sitios.

    Vale lo leído para otro aspecto del MISMO perfil: una frase leída de otro destino no respalda
    la casilla de este (que lo dicho de Marte valga para la Luna sería una deducción de EMMA). Si
    el perfil no la tiene, vale una frase del marco de NASA leído, que no es de ningún destino. Una
    cita sin sitio queda con la lista vacía, y la carga la rechaza.

    El marco solo se lee si alguna cita no está en su perfil. Desde que las casillas citan las filas
    de los niveles y EIMO (decimonovena ronda) se necesita siempre: un error en ese fichero tumba
    el perfil, y no solo el marco. Lo para `main.check_read_files`, que no deja arrancar con él
    roto, y el fichero no cambia con la aplicación en marcha. Y como cada cita mira primero
    su perfil, lo que dice una casilla no cambia por lo que lleve otra.
    """
    places = _catalog_places(raw)
    index: dict[tuple[str, Key], list[str]] = {}
    for profile_id, _, cite in _reused_citations(raw):
        key = _key(cite)
        index[(profile_id, key)] = [
            where for owner, where in places.get(key, []) if owner == profile_id
        ]
    missing = [item for item, found in index.items() if not found]
    if missing:
        framework = _framework_places()
        for item in missing:
            index[item] = framework.get(item[1], [])
    return index


def _validate_reused(raw: dict[str, Any]) -> None:
    """Un aspecto de `REUSED_ONLY` no cita nada que EMMA no hubiera leído ya para otra cosa."""
    index = _first_read(raw)
    for profile_id, name, cite in _reused_citations(raw):
        if not index[(profile_id, _key(cite))]:
            raise ValueError(
                f"{profile_id}.{name}: se construye solo con frases ya leídas, y esta no lo está "
                "(misma ficha, mismo apartado, misma frase y mismo día, en otro aspecto del mismo "
                f"perfil o en el marco de NASA leído): {cite['quote'][:60]!r}"
            )


def _reused_from(
    index: dict[tuple[str, Key], list[str]], profile_id: str, name: str, aspect: dict[str, Any]
) -> list[str]:
    """Para qué se leyó primero cada frase de la casilla, sin repetir sitio. Vacío fuera de
    `REUSED_ONLY`: los demás aspectos son lecturas propias."""
    reused: list[str] = []
    if name in REUSED_ONLY:
        for cite in _aspect_citations(aspect):
            # `.get`: si el índice dejara fuera una cita, la casilla no dice de dónde viene, pero
            # `/api/status` no cae por un `KeyError` (la carga ya rechaza la cita sin sitio).
            for where in index.get((profile_id, _key(cite)), []):
                if where not in reused:
                    reused.append(where)
    return reused


def _citations(raw: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for profile in raw["profiles"]:
        for aspect in profile["aspects"].values():
            found.extend(_aspect_citations(aspect))
    return found


def _refs(raw: dict[str, Any]) -> set[str]:
    return {cite["ref"] for cite in _citations(raw)}


def _read_dates(raw: dict[str, Any], ref_id: str) -> list[str]:
    """Los días en que se leyó algo citado de una ficha, del primero al último."""
    return sorted({cite["read_on"] for cite in _citations(raw) if cite["ref"] == ref_id})


def _pages_read(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Dónde se leyó y dónde se buscó, cada página con sus días de lectura.

    Por qué cada una lleva los suyos: con una sola fecha al pie (o con todas juntas) cada página
    parecería leída todos esos días. Las citadas sacan sus días de sus citas; las que se leyeron
    sin sacar ninguna frase, del catálogo.
    """
    cited = [
        {"title": ref.title, "url": ref.url, "read_on": _read_dates(raw, ref.id)}
        for ref in map(registry.get, raw["source"]["pages_cited"])
    ]
    uncited = [
        {"title": page["title"], "url": page["url"], "read_on": sorted(page["read_on"])}
        for page in raw["source"]["pages_read_without_citation"]
    ]
    return [*cited, *uncited]


@cache
def catalog() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def cited_refs() -> set[str]:
    """Las fichas del registro de evidencia que citan los perfiles."""
    return _refs(catalog())


def _registered(value: Any) -> Any:
    """`value` con cada cadena que es, entera, una constante registrada, en inglés."""
    if isinstance(value, str):
        return i18n.loc(value)
    if isinstance(value, dict):
        return {key: _registered(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_registered(item) for item in value]
    return value


def _served(payload: dict[str, Any]) -> dict[str, Any]:
    """Lo que se sirve, en el idioma de la petición; en castellano, tal cual.

    El perfil se compone entero en castellano, con las mismas líneas de siempre, y se pasa al
    inglés de una vez al salir: lo que viene del catálogo, con su fichero hermano
    (`mission_profiles.en.json`), y los rótulos y notas de este módulo, con su inglés registrado.
    Solo cambian valores que son, enteros, una de esas cadenas: los identificadores, las fechas,
    los títulos de las fuentes y las frases citadas (`quote`), que van en el idioma de la fuente,
    no están en ninguno de los dos y salen como están.
    """
    if i18n.current() != "en":
        return payload
    served: dict[str, Any] = _registered(i18n.localized(payload, PROFILES_PATH))
    return served


def _citation(cite: dict[str, Any]) -> dict[str, Any]:
    ref = registry.get(cite["ref"])
    return {**cite, "title": ref.title, "url": ref.url}


def _aspect(name: str, aspect: dict[str, Any], reused_from: list[str]) -> dict[str, Any]:
    discrepancy = aspect["discrepancy"]
    return {
        "key": name,
        "label": ASPECTS[name],
        "status": aspect["status"],
        "status_text": STATUSES[aspect["status"]],
        "statement": aspect["statement"],
        "citations": [_citation(cite) for cite in aspect["citations"]],
        "discrepancy": None if discrepancy is None else {
            "text": discrepancy["text"],
            "citations": [_citation(cite) for cite in discrepancy["citations"]],
        },
        "searched": aspect["searched"],
        "emma_note": EMMA_NOTES.get(name),
        # Para qué se leyó primero cada frase de un aspecto de `REUSED_ONLY`; vacío en los demás.
        "reused_from": reused_from,
    }


def _light_time_effect(round_trip_minutes: float | None, isolation_factor: float) -> str:
    """Lo que hizo el tiempo de luz con el riesgo del estado al que acompaña, con su cifra.

    LÓGICA 1 (2026-11-11): el texto del desajuste decía siempre «el riesgo sigue saliendo de ese
    tiempo de luz», también los días sin efeméride en caché, en que no hay tiempo de luz y el
    factor de aislamiento es 1. Ahora dice lo que pasó en el estado al que acompaña (que puede
    ser el de un `epoch` pedido, no el de hoy: por eso no dice «hoy»).
    """
    if round_trip_minutes is None:
        return i18n.tr(
            "En este estado no hay efeméride de su día, así que el riesgo no se escala con ningún "
            "tiempo de luz; el día que la haya, se escalará con ese.",
            "In this state there is no ephemeris for its day, so the risk is not scaled with any "
            "light time; the day there is one, it will be scaled with that.",
        )
    # Por debajo del minuto (la Luna, ~2,6 s), en segundos: «0 min» diría que no hay retardo.
    trip = (
        f"{display.number(round_trip_minutes, 0)} min"
        if round_trip_minutes >= 1.0
        else f"{display.number(round_trip_minutes * 60.0, 1)} s"
    )
    if isolation_factor > 1.0:
        return i18n.tr(
            f"En este estado son {trip} de ida y vuelta, y el riesgo se escala con ellos (factor "
            f"de aislamiento {display.number(isolation_factor, 2)}).",
            f"In this state the round trip is {trip}, and the risk is scaled with it (isolation "
            f"factor {display.number(isolation_factor, 2)}).",
        )
    return i18n.tr(
        f"En este estado son {trip} de ida y vuelta, por debajo del umbral de autonomía: no "
        "escalan el riesgo.",
        f"In this state the round trip is {trip}, below the autonomy threshold: it does not "
        "scale the risk.",
    )


@dataclass(frozen=True)
class EphemerisTarget:
    """Hacia qué cuerpo se calculan las efemérides con un perfil, y lo que trae la configuración.

    `target` es el que manda (`None`: el perfil no tiene objetivo, o no se reconoce, y no se
    consulta nada). `configured` es `EMMA_TARGET_BODY`, que ya no manda: se guarda solo para
    decir que se ignora cuando alguien lo puso (`explicit`) y difiere. El valor por defecto de la
    configuración no lo escribió nadie: avisar de que se ignora sería avisar de nada.
    """

    profile_id: str
    target: str | None
    configured: str
    explicit: bool = False

    @property
    def configured_ignored(self) -> bool:
        return self.explicit and self.configured != self.target


def ephemeris_target(profile_id: str, settings: Settings) -> EphemerisTarget:
    """EL ÚNICO PUNTO que da el objetivo de efemérides: el del perfil (decisión del 2026-11-11).

    Lo consultan el estado, `/api/comms`, la cobertura y la precarga, con el perfil vigente (el
    último firmado hasta el corte, o el de la configuración). Un perfil fuera del catálogo no
    tiene objetivo: no se adivina uno. Aquí, y solo aquí, se lee `EMMA_TARGET_BODY` de la
    configuración, para decir que ya no manda (`tests/test_mission_profile.py` lo fija).
    """
    profile = next((item for item in catalog()["profiles"] if item["id"] == profile_id), None)
    target = None if profile is None else profile["ephemeris_target"]
    return EphemerisTarget(
        profile_id, target, settings.target_body,
        explicit="target_body" in settings.model_fields_set,
    )


# Lo que se dice cuando el perfil no tiene objetivo de efemérides: no es un fallo ni un dato que
# falte, es que con este perfil no se calcula. Sin cifra: ni un retardo ni un factor inventados.
NO_TARGET_TEXT = (
    "Este perfil no tiene objetivo de efemérides en EMMA: el retardo con Tierra no se calcula, no "
    "se consulta JPL Horizons ni su caché, el riesgo no se escala con ningún tiempo de luz (factor "
    "de aislamiento 1) y la conjunción solar no aplica."
)
i18n.en(
    NO_TARGET_TEXT,
    "This profile has no ephemeris target in EMMA: the delay with Earth is not calculated, "
    "neither JPL Horizons nor its cache is queried, the risk is not scaled with any light time "
    "(isolation factor 1) and solar conjunction does not apply.",
)


def _ephemeris(
    chosen: EphemerisTarget,
    round_trip_minutes: float | None,
    isolation_factor: float,
) -> dict[str, Any]:
    """Hacia qué cuerpo se calcula el tiempo de luz con este perfil, y qué hizo con el riesgo."""
    target = chosen.target
    if target is None:
        state, text = NO_TARGET, NO_TARGET_TEXT
    else:
        effect = _light_time_effect(round_trip_minutes, isolation_factor)
        state, text = CONSISTENT, i18n.tr(
            f"El tiempo de luz se calcula hacia {KNOWN_TARGETS[target]} (código {target} de JPL "
            "Horizons), el objetivo de efemérides de este perfil. "
            f"{effect}",
            f"Light time is calculated toward {i18n.loc(KNOWN_TARGETS[target])} (JPL Horizons "
            f"code {target}), the ephemeris target of this profile. {effect}",
        )
    # `NO_TARGET_TEXT` es una constante: su inglés está registrado y se resuelve aquí, al servir.
    text = i18n.loc(text)
    if chosen.configured_ignored:
        text += i18n.tr(
            f" La configuración trae EMMA_TARGET_BODY={chosen.configured}: no se usa, porque el "
            "objetivo lo decide el perfil.",
            f" The configuration carries EMMA_TARGET_BODY={chosen.configured}: it is not used, "
            "because the target is decided by the profile.",
        )
    return {
        "state": state,
        # El objetivo que manda (el del perfil), o `None` si este perfil no tiene.
        "target_body": target,
        # `EMMA_TARGET_BODY`, que ya no manda, y si se está ignorando porque difiere.
        "configured_target_body": chosen.configured,
        "configured_ignored": chosen.configured_ignored,
        # Si el tiempo de luz de las efemérides escaló el riesgo del estado (factor > 1). Sin
        # objetivo no se consulta nada: `round_trip_minutes` llega `None`.
        "risk_scaled": round_trip_minutes is not None and isolation_factor > 1.0,
        "text": text,
    }


def describe(
    profile_id: str,
    settings: Settings,
    *,
    round_trip_minutes: float | None = None,
    isolation_factor: float = 1.0,
) -> dict[str, Any]:
    """El perfil declarado, como se sirve dentro del contexto de misión. No decide nada.

    `round_trip_minutes` e `isolation_factor` son los del estado al que acompaña (`None` y 1 sin
    efeméride ese día): solo sirven para decir qué hizo hoy el tiempo de luz; no se recalcula nada.
    """
    raw = catalog()
    base = {
        "id": profile_id,
        "note": DESCRIPTIVE,
        "declared": DECLARED_NOTE,
        # Dónde se leyó y dónde se buscó lo que quedó sin verificar: las páginas citadas (de su
        # ficha del registro) y las que se leyeron sin sacar de ellas ninguna frase.
        "pages_read": _pages_read(raw),
    }
    profile = next((item for item in raw["profiles"] if item["id"] == profile_id), None)
    if profile is None:
        return _served({
            **base,
            "known": False,
            "display": i18n.tr("perfil no reconocido", "unrecognized profile"),
            "unknown_text": i18n.tr(
                f"El perfil declarado ({profile_id!r}) no está en el catálogo de EMMA, que tiene "
                f"{', '.join(EXPECTED_IDS)}. No se enseña nada de él, y sin perfil reconocido no "
                "hay objetivo de efemérides: el retardo no se calcula y el riesgo no se escala "
                "con ningún tiempo de luz.",
                f"The declared profile ({profile_id!r}) is not in EMMA's catalog, which has "
                f"{', '.join(EXPECTED_IDS)}. Nothing is shown about it, and without a recognized "
                "profile there is no ephemeris target: the delay is not calculated and the risk "
                "is not scaled with any light time.",
            ),
            "ephemeris": None,
            "aspects": [],
        })
    index = _first_read(raw)
    return _served({
        **base,
        "known": True,
        "display": profile["display"],
        "unknown_text": None,
        "ephemeris": _ephemeris(
            ephemeris_target(profile_id, settings), round_trip_minutes, isolation_factor
        ),
        "aspects": [
            _aspect(name, aspect, _reused_from(index, profile["id"], name, aspect))
            for name, aspect in profile["aspects"].items()
        ],
    })


def _cell(
    index: dict[tuple[str, Key], list[str]], profile_id: str, name: str, aspect: dict[str, Any]
) -> dict[str, Any]:
    """Una casilla de la matriz: el aspecto como se sirve, con lo que se enseña si no hay frase."""
    return {
        **_aspect(name, aspect, _reused_from(index, profile_id, name, aspect)),
        "text": aspect["statement"] if aspect["status"] == READ else NO_SOURCE,
    }


def compare(declared_id: str) -> dict[str, Any]:
    """Los perfiles lado a lado, aspecto por aspecto. Descriptivo: no decide nada."""
    raw = catalog()
    index = _first_read(raw)
    return _served({
        "note": DESCRIPTIVE,
        "declared_id": declared_id,
        # De dónde sale el entorno declarado: la configuración de partida y los asientos firmados.
        "declared_note": DECLARED_NOTE,
        "declared_text": None if declared_id in EXPECTED_IDS else (
            i18n.tr(
                f"El perfil declarado ({declared_id!r}) no está en el catálogo de EMMA: ninguna "
                "columna es la suya.",
                f"The declared profile ({declared_id!r}) is not in EMMA's catalog: no column "
                "is its own.",
            )
        ),
        "no_source": NO_SOURCE,
        "aspects": [
            {"key": key, "label": label, "reused_only": key in REUSED_ONLY}
            for key, label in ASPECTS.items()
        ],
        "profiles": [
            {
                "id": profile["id"],
                "display": profile["display"],
                "declared": profile["id"] == declared_id,
                "cells": [
                    _cell(index, profile["id"], name, aspect)
                    for name, aspect in profile["aspects"].items()
                ],
            }
            for profile in raw["profiles"]
        ],
        "reused_note": REUSED_NOTE,
        "medical_note": MEDICAL_NOTE,
        "pages_read": _pages_read(raw),
    })
