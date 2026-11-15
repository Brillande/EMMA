"""Mapa de conjuntos de datos humanos: qué mide cada uno, cuándo, a quién y con qué acceso.

La base de conocimiento del equipo (§8) pide «construir un mapa, no un único dataset», y su
backlog (§15) pone como P0 la «tabla de variables, timepoints, acceso y utilidad» de Twins Study,
OSD-343 y los demás conjuntos humanos. La conversación de ideación propone la misma matriz —quién,
qué variable, L-, en vuelo, R+— y una escalera de hitos de seguimiento (L-180 → … → R+365). Las
piezas ya estaban, pero sueltas: las fichas de OSD-288, OSD-569, OSD-343, el Twins Study y MMASH en
el registro, el acceso de los repositorios en `docs/contexto/repositorios-humanos.md`. Ninguna
pantalla decía de qué días hay tomas en cada conjunto, ni que los ficheros abiertos de OSD-343 son
de ratón aunque el estudio hable de 59 astronautas, ni que de CIPHER no se publica ningún día.

Por eso este mapa se sostiene en frases leídas (`data/human_datasets_read.json`) y su defensa está
en `validate`: rechaza una frase sin ficha o de un sitio que no es la fuente; una población que no
sea la de la ficha (así OSD-288 no sale humano); unos ficheros abiertos de una población que el
estudio no tiene, o distinta de la suya sin decir por qué (así OSD-343 no sale «59 astronautas»);
un día de toma que no esté escrito en una frase de su fase, o que no sea de esa fase (L- antes, FD
en vuelo, R+ después); tomas en vuelo en un conjunto de Tierra; una fase sin decir de dónde sale lo
que dice (la frase, el motivo o dónde se buscó); un acceso sin fuente, sin el fichero que EMMA
tiene o sin motivo, o que de tener un fichero deduzca que todo el conjunto es abierto; un uso en
EMMA sin el fichero y la ficha que cita, que reclame de más o que copie una cifra de la
validación; y una lista de estudios de CIPHER que no cuadre con la que da su página. Que el
fichero exista y nombre esa ficha lo comprueba la prueba: en el paquete de escritorio el código no
viaja como ficheros.

La decimosexta ronda añadió tres cosas que el contexto pedía y el mapa no tenía. Los controles de
cada conjunto (la conversación, a propósito de Biolab: «Flight sample / In-flight control / Ground
control / Pre-flight / Post-flight»), cada uno con su frase; se rechaza un control que la frase no
nombra o que niega («did not have … controls»), de otra población (los controles de OSD-288 son
ratones, como sus muestras), un control a 1 g en vuelo o el propio antes del vuelo en un conjunto
que no es de vuelo, un control en Tierra en uno que ya está en ella, o un grupo de control de
análogo fuera de un análogo. El reposo en cama como conjunto longitudinal (base de conocimiento
§3.2): un análogo no tiene antes, durante ni después de un vuelo —el «R+» de AGBRESA es la
recuperación tras el reposo, no el regreso, y pasaría por día escrito si no se rechazara—, así que
sus tomas van en su propio calendario, por etapas de la pauta PRE → EXPOSURE → COUNTERMEASURE →
POST → RECOVERY. Y los catálogos de §8 (ISS Research Explorer, data.nasa.gov), que no miden a
nadie: van aparte, sin población ni tomas. Las diez áreas del Twins Study van enteras, contadas
contra la frase de su página.

La decimonovena ronda (U5) añadió lo que la conversación pide de cada fuente y el mapa no decía:
su papel en la estrategia de datos de la base de conocimiento (§8: INPUT, KNOWLEDGE o CONTEXT) y
para qué sirve al modelo («si sirven para entrenar, validar o simplemente contextualizar»).
Ninguna fuente dice para qué le sirve a EMMA, así que las dos son deducción de EMMA sobre lo
leído, se rotulan así y cada una lleva su motivo. La defensa cierra el enumerado por los dos
lados: un estudio con población no es una señal recibida en misión (INPUT) ni el entorno
(CONTEXT), y EMMA no entrena ningún modelo (compara con la línea base de la persona o con un
rango de referencia, y los parámetros del simulador salen de la bibliografía), así que `train`
se rechaza con su motivo; «validar» solo lo puede decir un conjunto que EMMA usa y cuyos ficheros
abiertos miden personas. Que todos salgan KNOWLEDGE es la respuesta del mapa, no una omisión. La
misma ronda leyó el acceso de cada conjunto de OSDR en su API de ficheros (la bandera «restricted»
de cada fichero) en vez de deducirlo de que los ficheros tengan enlace, y los días que el
artículo del Twins Study escribe en resultados concretos, con el guion largo con que los escribe
PMC.

Es un inventario: no entra en el análisis, en el riesgo ni en ninguna alerta, y no sale a la red.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core import i18n
from app.evidence import registry
from app.evidence.testbeds import CLAIM, COPIED_FIGURE, FIGURES_HOME
from app.ingest.fhir import EvidenceContext

DATASETS_PATH = Path(__file__).resolve().parents[1] / "data" / "human_datasets_read.json"
# El fichero que EMMA dice tener o usar se nombra desde la raíz del repositorio. Que exista lo
# comprueba la prueba, no el cargador: en el paquete de escritorio el código no viaja como ficheros.
_REPO_PATH = re.compile(r"backend/app/[\w./-]+\.(?:py|json|csv)")

# Los sitios de las fuentes: la ficha del estudio en OSDR, la página de NASA, el artículo en PMC,
# el conjunto en PhysioNet y el servidor de informes técnicos de NASA (NTRS: los pósteres y
# manuscritos de los propios investigadores de un estudio, no un resumen de terceros). Una frase
# de un resumen de terceros no es la fuente.
SOURCE_HOSTS = frozenset({
    "osdr.nasa.gov", "www.nasa.gov", "pmc.ncbi.nlm.nih.gov", "physionet.org", "ntrs.nasa.gov",
})
# Un catálogo es la fuente de lo que él mismo es, no de un conjunto: data.nasa.gov «describes NASA
# datasets rather than hosting the data itself». Su sitio vale solo en las frases de un catálogo.
CATALOG_HOSTS = SOURCE_HOSTS | {"data.nasa.gov"}

PHASES = {
    "pre": "antes del vuelo",
    "inflight": "en vuelo",
    "post": "después del vuelo",
}
# El inglés de cada tabla de rótulos va en una tabla hermana con las mismas claves (y no en el
# registro común de `i18n.en`): son palabras sueltas —«abierto», «validar», «no procede»— que en
# otro módulo pueden querer otro inglés. Lo que se sirve lo elige `_label`.
PHASES_EN = {
    "pre": "before flight",
    "inflight": "in flight",
    "post": "after flight",
}
# Lo que se sabe de las tomas de una fase, con la palabra que se enseña.
PHASE_STATUS = {
    "labels": "tomas con día",
    "stated": "la fuente dice que hay tomas, sin día",
    "none": "sin tomas en esta fase",
    "not_applicable": "no procede",
    "not_found": "buscado y no encontrado",
}
PHASE_STATUS_EN = {
    "labels": "samples with a day",
    "stated": "the source says there are samples, without a day",
    "none": "no samples in this phase",
    "not_applicable": "not applicable",
    "not_found": "searched and not found",
}
ACCESS_LEVELS = {
    "open": "abierto",
    # Lo único que se sabe es que el fichero que EMMA descargó lo era: no se extiende al resto.
    "file_open": "abierto el fichero que EMMA tiene; del resto, la fuente no lo dice",
    "mixed": "abierto en parte; lo sensible, de acceso controlado",
    "controlled": "de acceso controlado",
    "request": "por solicitud aprobada",
    # Lo que dice un artículo («made available by the authors»): ni repositorio ni solicitud formal.
    "authors": "a petición a sus autores",
    "not_found": "buscado y no encontrado",
}
ACCESS_LEVELS_EN = {
    "open": "open",
    "file_open": "the file that EMMA has is open; of the rest, the source does not say",
    "mixed": "open in part; what is sensitive, under controlled access",
    "controlled": "under controlled access",
    "request": "by approved request",
    "authors": "on request to its authors",
    "not_found": "searched and not found",
}
ACCESS_BASIS = {
    "source": "lo dice la fuente",
    "emma": "EMMA tiene el fichero",
    "deduced": "lo deduce EMMA; la fuente no lo dice",
    "not_found": "buscado y no encontrado",
}
ACCESS_BASIS_EN = {
    "source": "stated by the source",
    "emma": "EMMA has the file",
    "deduced": "deduced by EMMA; the source does not say",
    "not_found": "searched and not found",
}
EMMA_USE = {True: "en uso", False: "sin uso"}
EMMA_USE_EN = {True: "in use", False: "not in use"}
# Una fase con días, pero ninguno en este tramo de la escalera.
EMPTY_SEGMENT = "sin toma en este tramo"
EMPTY_SEGMENT_EN = "no sample in this segment"

# El papel de cada fuente en la estrategia de datos (base de conocimiento §8) y para qué sirve al
# modelo (conversación de ideación: «si sirven para entrenar, validar o simplemente
# contextualizar»). Ninguna fuente dice para qué le sirve a EMMA: las dos son deducción de EMMA
# sobre lo leído, y así se rotulan en la respuesta.
ROLE_LEVELS = {
    "INPUT": "señal recibida durante la misión",
    "KNOWLEDGE": "evidencia histórica o mecanística",
    "CONTEXT": "entorno y misión",
}
ROLE_LEVELS_EN = {
    "INPUT": "signal received during the mission",
    "KNOWLEDGE": "historical or mechanistic evidence",
    "CONTEXT": "environment and mission",
}
# En este mapa solo cabe KNOWLEDGE: un estudio con población es evidencia histórica. Los INPUT de
# EMMA son los wearables y el simulador, y el CONTEXT las efemérides y DONKI, y ninguno es un
# conjunto de datos humanos. Que los otros dos valores existan y se rechacen con su motivo es
# deliberado: la conversación pide clasificar cada fuente, y esta es la respuesta del mapa.
ROLE_REJECTED = {
    "INPUT": (
        "una señal recibida en misión no es un estudio: los INPUT de EMMA (wearables, simulador) "
        "no están en este mapa"
    ),
    "CONTEXT": (
        "el CONTEXT es el entorno y la misión (efemérides, DONKI), que no miden a nadie: un "
        "estudio con población es KNOWLEDGE"
    ),
}
FITNESS = {
    "train": "entrenar",
    "validate": "validar",
    "contextualize": "solo contextualizar",
}
# «validate» es el nombre de la casilla de la conversación («entrenar, validar o simplemente
# contextualizar»), no algo que EMMA diga de sí: el motivo de cada conjunto dice qué se mide.
FITNESS_EN = {
    "train": "train",
    "validate": "validate",
    "contextualize": "contextualize only",
}
# EMMA no entrena ningún modelo: compara con la línea base de la persona o con un rango de
# referencia, y los parámetros del simulador salen de la bibliografía. Un conjunto que dijera
# «entrenar» reclamaría algo que no existe.
FITNESS_REJECTED = {
    "train": (
        "EMMA no entrena ningún modelo: compara con la línea base de la persona o con un rango "
        "de referencia, y los parámetros del simulador salen de la bibliografía"
    ),
}
ROLE_BASIS = "deducción de EMMA sobre lo leído"
i18n.en(ROLE_BASIS, "EMMA's deduction from what was read")
ROLE_FIELDS = frozenset({"level", "level_why", "fitness", "fitness_why"})

# Un día de toma por fase: L-n antes del lanzamiento, FDn día de vuelo, R+n tras el regreso.
_LABEL = {
    "pre": re.compile(r"L-(\d+)"),
    "inflight": re.compile(r"FD(\d+)"),
    "post": re.compile(r"R\+(\d+)"),
}
_RANK = {"pre": 0, "inflight": 1, "post": 2}
# Los conjuntos sin vuelo —en Tierra o en un análogo— no tienen antes, durante ni después de un
# vuelo: sus tres fases no proceden. Un análogo lleva además su propio calendario.
_ANALOG = frozenset({EvidenceContext.ANALOG_BEDREST, EvidenceContext.ANALOG_ISOLATION})
_NO_FLIGHT = frozenset({EvidenceContext.GROUND}) | _ANALOG
# Solo un conjunto de un vuelo puede tener un control a 1 g en vuelo o el suyo antes del vuelo.
_FLIGHT = frozenset({EvidenceContext.ISS, EvidenceContext.SPACEFLIGHT})
# Un conjunto simulado no es un conjunto de datos humanos: el mapa no lo admite. Cada entorno del
# enumerado cae en uno de los tres grupos, para que uno nuevo no quede sin reglas sin que se note.
# Sin entorno (`None`) solo queda un estudio que lo tiene fuera del enumerado, como OSD-343 (ISS y
# Tierra a la vez): no se le restringe por entorno.
_REJECTED = frozenset({EvidenceContext.SIMULATED})
if set(EvidenceContext) != _FLIGHT | _NO_FLIGHT | _REJECTED:
    raise RuntimeError("un entorno del enumerado sin clasificar en el mapa de datos humanos")

# Los controles de un conjunto (la conversación, a propósito de Biolab), con la palabra que se
# enseña. Un gemelo es un control en Tierra, pero se dice aparte: es la misma genética.
CONTROL_KINDS = {
    "ground": "control en Tierra",
    "inflight_1g": "control en vuelo a 1 g, por centrifugación",
    "twin": "gemelo en Tierra",
    "own_baseline": "cada sujeto, su propio control antes del vuelo",
    "analog_control": "grupo del análogo sin la contramedida",
}
CONTROL_KINDS_EN = {
    "ground": "ground control",
    "inflight_1g": "in-flight control at 1 g, by centrifugation",
    "twin": "twin on Earth",
    "own_baseline": "each subject, their own control before flight",
    "analog_control": "group of the analog without the countermeasure",
}
# Lo que la frase tiene que nombrar para sostener ese control: sin la palabra, no se sostiene.
CONTROL_WORDS = {
    "ground": re.compile(r"\b(?:ground|earth)\b", re.IGNORECASE),
    "inflight_1g": re.compile(r"\b1\s?g\b|centrifug", re.IGNORECASE),
    "twin": re.compile(r"\btwin\b", re.IGNORECASE),
    "own_baseline": re.compile(r"\bown controls?\b|\bbaseline\b|\bpre-?flight\b", re.IGNORECASE),
    # «BR only (BRC)»: el grupo que solo hace reposo; un «only» cualquiera no nombra un grupo. Y un
    # «control» suelto tampoco: «Ground Control» o «vivarium controls» no son el grupo del análogo
    # sin la contramedida; «a passive control (Ctrl) group», sí.
    "analog_control": re.compile(
        r"\bcontrol\s+(?:\([^)]*\)\s+)?groups?\b|\b(?:BR|bed rest) only\b", re.IGNORECASE
    ),
}
# Tener la palabra no basta: una frase que niega el control («did not have … controls on Earth»,
# «no controls», «controls were not flown») o que nombra un periodo («a 20 day ambulatory control
# period») no sostiene ningún grupo. La negación ha de regir el control: un grupo descrito por lo
# que no recibe («a no-exercise control group», «subjects without countermeasure served as the
# control group») sí es un control.
_NOT_A_CONTROL = re.compile(
    r"\b(?:did|does|do|was|were|is|are|has|have|had)\s+(?:not|never)\b[^.;]{0,60}\bcontrols?\b"
    r"|\b(?:no|without)\s+(?:[\w-]+\s+){0,3}?controls?\b"
    r"|\bcontrols?\s+(?:groups?\s+)?(?:were|was|are|is)\s+(?:not|never)\b"
    r"|\bcontrols?\s+(?:period|phase)s?\b",
    re.IGNORECASE,
)
# Lo que la frase de un paso del calendario tiene que nombrar para cada etapa de la pauta de §3.2:
# sin la palabra, la etapa es una suposición. Así el «R+0 … R+13» de AGBRESA no pasa por un POST
# ni una centrifugación por la exposición.
STAGE_WORDS = {
    "PRE": re.compile(r"\bbaseline\b|\bBDC\b|\bbefore\b|\bpre-", re.IGNORECASE),
    "EXPOSURE": re.compile(r"\bbed rest\b|\bBR\b|\bHDT\d*\b|\bhead-down\b", re.IGNORECASE),
    "COUNTERMEASURE": re.compile(
        r"countermeasure|centrifug|\b[ci]?AG\b|\bexercise\b|\bnutrition\b", re.IGNORECASE
    ),
    "POST": re.compile(r"\bpost\b|\bpost-|\bafter\b", re.IGNORECASE),
    "RECOVERY": re.compile(r"\brecovery\b|\bR\+", re.IGNORECASE),
}
CONTROL_STATUS = {
    "listed": "con controles",
    "none": "sin controles",
    "not_applicable": "no procede",
    "not_found": "buscado y no encontrado",
}
CONTROL_STATUS_EN = {
    "listed": "with controls",
    "none": "no controls",
    "not_applicable": "not applicable",
    "not_found": "searched and not found",
}
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Los apartados de la base de conocimiento de donde sale una fila: la tabla de repositorios (§8) y
# la de análogos (§3.1). Que la fila esté literal en su apartado lo comprueba la prueba.
KB_SECTIONS = frozenset({"§8", "§3.1"})

DATASET_FIELDS = frozenset({
    "id", "name", "ref", "population", "open_population", "open_population_note", "kb_row",
    "kb_where", "subjects", "variables", "areas", "phases", "analog_schedule", "controls",
    "access", "emma_use", "role", "caveat",
})
CONTROL_FIELDS = frozenset({"status", "items", "absent", "why", "searched"})
# Las piezas con frase: su frase, su ficha y su sitio, y su `read_on` si se leyó otro día.
_QUOTE_KEYS = frozenset({"quote", "ref", "where"})
CONTROL_ITEM_FIELDS = _QUOTE_KEYS | {"kind", "population"}
SCHEDULE_FIELDS = _QUOTE_KEYS | {"stages"}
AREA_FIELDS = _QUOTE_KEYS | {"name", "what"}
AREAS_FIELDS = frozenset({"count", "cited", "items"})
CATALOG_FIELDS = frozenset({
    "id", "name", "ref", "kb_row", "kb_where", "what", "access", "emma_use", "caveat",
})
PHASE_FIELDS = frozenset({"status", "labels", "cited", "why", "searched"})
ACCESS_FIELDS = frozenset({"level", "basis", "cited", "path", "why", "searched"})
EMMA_FIELDS = frozenset({"used", "text", "where", "cites"})
CIPHER_FIELDS = frozenset({
    "name", "full_name", "what", "study_count", "studies", "studies_where", "cohort", "ladder",
    "phases", "access", "emma_study", "emma_use", "role",
})

NOTE = (
    "Qué conjuntos de datos humanos hay, a quién miden, en qué días hay tomas, con qué controles "
    "y cómo se accede a ellos; y los catálogos que los describen sin medir a nadie. Un reposo en "
    "cama no es un vuelo: sus días van en su propio calendario. Cada día y cada control están "
    "escritos en una frase de la fuente; lo que la fuente no dice se declara "
    "buscado y no encontrado. El papel de cada conjunto en la estrategia de datos (INPUT, "
    "KNOWLEDGE, CONTEXT) y para qué sirve al modelo (entrenar, validar o solo contextualizar) "
    "son deducción de EMMA sobre lo leído, y van rotulados así. No existe una API pública de "
    "constantes de astronautas: lo que hay son conjuntos de estudios. Inventario: no interviene "
    "en el estado de la tripulación ni en ninguna alerta."
)
i18n.en(
    NOTE,
    "Which human datasets exist, whom they measure, on which days there are samples, with "
    "which controls and how they are accessed; and the catalogues that describe them without "
    "measuring anyone. A bed rest is not a flight: its days go in its own schedule. Each day "
    "and each control is written in a sentence of the source; what the source does not say is "
    "declared searched and not found. The role of each dataset in the data strategy (INPUT, "
    "KNOWLEDGE, CONTEXT) and what it is good for in the model (train, validate or contextualize "
    "only) are EMMA's deduction from what was read, and are labelled as such. There is no "
    "public API of astronaut vital signs: what exists are datasets from studies. Inventory: it "
    "plays no part in the crew status or in any alert.",
)


class DatasetMapError(ValueError):
    """El mapa de conjuntos de datos no cumple su contrato: no se sirve."""


def _label(table: dict[str, str], english: dict[str, str], key: str) -> str:
    """El rótulo de una tabla en el idioma de la petición; la clave no se traduce nunca."""
    return i18n.tr(table[key], english[key])


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _fields(key: str, item: dict[str, Any], expected: frozenset[str]) -> None:
    """Ni campos de menos (lo que no se sabe es null) ni de más (uno mal escrito no se sirve)."""
    if missing := sorted(expected - item.keys()):
        raise DatasetMapError(f"{key}: faltan campos {missing}: lo que no se sabe va como null")
    if extra := sorted(item.keys() - expected):
        raise DatasetMapError(f"{key}: campos desconocidos {extra}")


def _piece(
    key: str,
    item: dict[str, Any],
    expected: frozenset[str],
    hosts: frozenset[str] = SOURCE_HOSTS,
) -> None:
    """Una pieza con frase: sus campos, ni de menos ni de más; `read_on`, solo si se releyó."""
    _fields(key, {name: value for name, value in item.items() if name != "read_on"}, expected)
    _quoted(key, item, hosts)


def _counted(count: Any, names: list[str], quote: str) -> bool:
    """Una lista cuadra con el número que da su fuente: tantos como dice, sin repetir ninguno, y
    ese número escrito en la frase. Lo comparten los estudios de CIPHER y las áreas del Twins."""
    return (
        not isinstance(count, bool)
        and isinstance(count, int)
        and len(names) == count
        and len(set(names)) == count
        and re.search(rf"\b{count}\b", quote) is not None
    )


def _quoted(key: str, item: dict[str, Any], hosts: frozenset[str]) -> None:
    """Una frase de fuente: literal, con su sitio y una ficha del registro de un sitio fuente."""
    for field in ("quote", "ref", "where"):
        if not _text(item, field):
            raise DatasetMapError(f"{key}: falta `{field}`: sin frase, sitio y ficha no es un dato")
    url = registry.get(item["ref"]).url  # una ficha que no está en el registro falla aquí
    if urlsplit(url or "").hostname not in hosts:
        raise DatasetMapError(f"{key}: {url!r} no es la página de la fuente")
    # Una frase leída otro día que el del fichero lleva su fecha; si no, es la del fichero.
    read_on = item.get("read_on")
    if read_on is not None and not (isinstance(read_on, str) and _DATE.fullmatch(read_on)):
        raise DatasetMapError(f"{key}: `read_on` {read_on!r} no es una fecha AAAA-MM-DD")


def _repo_path(value: Any) -> bool:
    return isinstance(value, str) and _REPO_PATH.fullmatch(value) is not None and ".." not in value


def named_files() -> list[str]:
    """Los ficheros del repositorio que el mapa nombra: los que EMMA tiene o en los que lo usa."""
    raw = read()
    rows = [*raw["datasets"], *raw["catalogs"]]
    files = [item["access"]["path"] for item in rows if item["access"]["path"]]
    files += [item["emma_use"]["where"] for item in rows if item["emma_use"]["where"]]
    files.append(raw["cipher"]["emma_use"]["where"])
    return files


def emma_citations() -> list[tuple[str, str]]:
    """Cada uso en EMMA como (fichero, ficha que cita): la prueba mira que el fichero la nombre."""
    raw = read()
    rows = [*raw["datasets"], *raw["catalogs"]]
    uses = [item["emma_use"] for item in rows] + [raw["cipher"]["emma_use"]]
    return [(use["where"], use["cites"]) for use in uses if use["used"]]


def _compact(text: str) -> str:
    """El guion de siempre y sin espacios a su lado: «L − 92» y «R + 1» se escriben así en PMC.

    Solo se quitan los espacios junto al signo: quitar todos pegaría «and L−3» en «andL-3».
    """
    # El signo menos (U+2212, Inspiration4) y el guion largo (U+2013, «L–162» en el Twins
    # Study) son el mismo guion.
    dashes = text.replace("\u2212", "-").replace("\u2013", "-")
    return re.sub(r"\s*([-+])\s*", r"\1", dashes)


def written_in(label: str, quotes: list[str]) -> bool:
    """El día está escrito en una de las frases, entero: «R+1» no es el principio de «R+194», ni
    «L-1» el de «L-1d» (la carga de los ratones de OSD-288, que no es una toma)."""
    pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(_compact(label)) + r"(?![A-Za-z0-9])")
    return any(pattern.search(_compact(quote)) for quote in quotes)


def label_key(phase: str, label: str) -> tuple[int, int] | None:
    """El orden de un día en la línea del vuelo; `None` si no es un día de esa fase."""
    found = _LABEL[phase].fullmatch(label)
    if found is None:
        return None
    day = int(found.group(1))
    return (_RANK[phase], -day if phase == "pre" else day)


def _point_key(point: str) -> tuple[int, int]:
    """Un hito de la escalera de la conversación: un día L-/R+, o «Flight»."""
    if point == "Flight":
        return (_RANK["inflight"], 0)
    for phase in ("pre", "post"):
        if (key := label_key(phase, point)) is not None:
            return key
    raise DatasetMapError(f"hito {point!r}: ni L-n, ni R+n, ni «Flight»")


def _status_reasons(key: str, nothing: str, item: dict[str, Any], said: bool) -> None:
    """Lo que no hay se sostiene igual en las tomas que en los controles: «sin nada», con la frase
    de la fuente o un motivo; «no procede», con su motivo; «no encontrado», con dónde se buscó."""
    status = item["status"]
    if status == "none" and not (said or _text(item, "why")):
        raise DatasetMapError(f"{key}: {nothing}, sin frase ni motivo")
    if status == "not_applicable" and not _text(item, "why"):
        raise DatasetMapError(f"{key}: no procede, sin decir por qué")
    if status == "not_found" and not _text(item, "searched"):
        raise DatasetMapError(f"{key}: buscado y no encontrado, sin decir dónde se buscó")


def _validate_phase(
    key: str, phase: str, item: dict[str, Any], context: EvidenceContext | None
) -> None:
    _fields(key, item, PHASE_FIELDS)
    status = item["status"]
    if status not in PHASE_STATUS:
        raise DatasetMapError(f"{key}: estado {status!r} desconocido")
    labels, cited = item["labels"], item["cited"]
    for index, quote in enumerate(cited):
        _piece(f"{key}/cited/{index}", quote, _QUOTE_KEYS)
    if status == "labels":
        if not labels:
            raise DatasetMapError(f"{key}: tomas con día, pero sin ningún día")
        quotes = [quote["quote"] for quote in cited]
        for label in labels:
            if label_key(phase, label) is None:
                raise DatasetMapError(f"{key}: {label!r} no es un día de {PHASES[phase]}")
            if not written_in(label, quotes):
                raise DatasetMapError(f"{key}: {label!r} no está escrito en ninguna frase")
    elif labels:
        raise DatasetMapError(f"{key}: días sin el estado de tomas con día")
    if status in {"labels", "stated"} and not cited:
        raise DatasetMapError(f"{key}: lo que dice de sus tomas sin una frase de la fuente")
    _status_reasons(key, "sin tomas", item, bool(cited))
    if context in _NO_FLIGHT and status != "not_applicable":
        # El arreglo que se propone es uno que el cargador admite: calendario, solo en un análogo.
        fix = (
            "sus tomas van en el calendario del análogo" if context in _ANALOG
            else "en Tierra sus tres fases no proceden"
        )
        raise DatasetMapError(
            f"{key}: un conjunto sin vuelo no tiene antes, durante ni después de un vuelo; {fix}"
        )


def _validate_access(
    key: str, item: dict[str, Any], hosts: frozenset[str] = SOURCE_HOSTS
) -> None:
    _fields(key, item, ACCESS_FIELDS)
    if item["level"] not in ACCESS_LEVELS:
        raise DatasetMapError(f"{key}: acceso {item['level']!r} desconocido")
    basis = item["basis"]
    if basis not in ACCESS_BASIS:
        raise DatasetMapError(f"{key}: `basis` {basis!r}: se dice de dónde sale el acceso")
    for index, quote in enumerate(item["cited"]):
        _piece(f"{key}/cited/{index}", quote, _QUOTE_KEYS, hosts)
    if basis == "source" and not item["cited"]:
        raise DatasetMapError(f"{key}: el acceso lo dice la fuente, pero sin su frase")
    if (basis == "emma") != (item["level"] == "file_open"):
        raise DatasetMapError(f"{key}: tener un fichero solo dice que ese fichero es abierto")
    if basis == "emma" and not (_repo_path(item["path"]) and _text(item, "why")):
        raise DatasetMapError(f"{key}: EMMA tiene el fichero, pero no lo nombra o no dice de dónde")
    if item["path"] is not None and not _repo_path(item["path"]):
        raise DatasetMapError(f"{key}: `path` no es un fichero del repositorio")
    if basis == "deduced" and not _text(item, "why"):
        raise DatasetMapError(f"{key}: una deducción sin su motivo")
    if (basis == "not_found") != (item["level"] == "not_found"):
        raise DatasetMapError(f"{key}: un acceso no encontrado lo es en el nivel y en su origen")
    if basis == "not_found" and not _text(item, "searched"):
        raise DatasetMapError(f"{key}: buscado y no encontrado, sin decir dónde se buscó")


def _validate_emma_use(key: str, item: dict[str, Any]) -> None:
    _fields(key, item, EMMA_FIELDS)
    if not isinstance(item["used"], bool) or not _text(item, "text"):
        raise DatasetMapError(f"{key}: el uso en EMMA sin decir si lo hay y cuál")
    if item["used"]:
        if not _repo_path(item["where"]):
            raise DatasetMapError(f"{key}: un uso en EMMA que no nombra un fichero del repositorio")
        # La ficha que ese fichero cita: que la cite de verdad lo comprueba la prueba.
        if not _text(item, "cites"):
            raise DatasetMapError(f"{key}: un uso en EMMA sin la ficha que cita")
        registry.get(item["cites"])  # una ficha que no está en el registro falla aquí
    elif item["where"] is not None or item["cites"] is not None:
        raise DatasetMapError(f"{key}: sin uso en EMMA, pero con fichero o ficha")
    if claimed := [found.group(0) for found in CLAIM.finditer(item["text"])]:
        raise DatasetMapError(f"{key}: el uso en EMMA reclama de más ({claimed})")
    if COPIED_FIGURE.search(item["text"]):
        raise DatasetMapError(f"{key}: el uso en EMMA copia una cifra; se remite a {FIGURES_HOME}")


def _validate_role(key: str, role: Any, used: bool, opened: str | None) -> None:
    """El papel y la aptitud de un conjunto: valores cerrados, cada uno con su motivo, y sin
    reclamar de más. `used` y `opened` son el uso en EMMA y la población de los ficheros
    abiertos, ya validados: «validar» solo lo dice un conjunto que EMMA usa y cuyos ficheros
    miden personas."""
    if not isinstance(role, dict):
        raise DatasetMapError(f"{key}: el papel es un bloque con su motivo")
    _fields(key, role, ROLE_FIELDS)
    level, fitness = role["level"], role["fitness"]
    if not isinstance(level, str) or level not in ROLE_LEVELS:
        raise DatasetMapError(f"{key}: papel {level!r} desconocido; uno de {sorted(ROLE_LEVELS)}")
    if level in ROLE_REJECTED:
        raise DatasetMapError(f"{key}: {ROLE_REJECTED[level]}")
    if not isinstance(fitness, str) or fitness not in FITNESS:
        raise DatasetMapError(f"{key}: aptitud {fitness!r} desconocida; una de {sorted(FITNESS)}")
    if fitness in FITNESS_REJECTED:
        raise DatasetMapError(f"{key}: {FITNESS_REJECTED[fitness]}")
    for field in ("level_why", "fitness_why"):
        if not _text(role, field):
            raise DatasetMapError(f"{key}: `{field}`: una deducción sin su motivo")
        if overclaimed := [found.group(0) for found in CLAIM.finditer(role[field])]:
            raise DatasetMapError(f"{key}: `{field}` reclama de más ({overclaimed})")
        if COPIED_FIGURE.search(role[field]):
            raise DatasetMapError(f"{key}: `{field}` copia una cifra; se remite a {FIGURES_HOME}")
    if fitness == "validate" and not used:
        raise DatasetMapError(f"{key}: un conjunto que EMMA no usa no sirve para validar nada")
    if fitness == "validate" and opened != "human":
        raise DatasetMapError(
            f"{key}: el motor se contrasta con personas, y los ficheros abiertos no las miden"
        )


def _validate_dataset(item: dict[str, Any], pattern: list[str]) -> None:
    key = str(item.get("id", "?"))
    _fields(key, item, DATASET_FIELDS)
    for field in ("id", "name", "ref", "caveat"):
        if not _text(item, field):
            raise DatasetMapError(f"{key}: falta `{field}`")
    ref = registry.get(item["ref"])
    if ref.population is None or item["population"] != ref.population:
        raise DatasetMapError(
            f"{key}: población {item['population']!r}; la ficha dice {ref.population!r}"
        )
    opened = item["open_population"]
    if opened is not None:
        if opened not in registry.POPULATIONS:
            raise DatasetMapError(f"{key}: población de los ficheros {opened!r} desconocida")
        if opened not in _covered(item["population"]):
            raise DatasetMapError(
                f"{key}: los ficheros abiertos miden {opened!r}, que el estudio no tiene"
            )
        if opened != item["population"] and not _text(item, "open_population_note"):
            raise DatasetMapError(
                f"{key}: los ficheros abiertos no miden lo mismo que el estudio y no se dice"
            )
    _validate_kb_row(key, item)
    for block, expected in (("subjects", _QUOTE_KEYS), ("variables", _QUOTE_KEYS | {"what"})):
        if not item[block]:
            raise DatasetMapError(f"{key}: sin ninguna frase leída en `{block}`")
        for index, quote in enumerate(item[block]):
            _piece(f"{key}/{block}/{index}", quote, expected)
    for index, variable in enumerate(item["variables"]):
        if not _text(variable, "what"):
            raise DatasetMapError(f"{key}/variables/{index}: falta `what`")
    context = ref.evidence_context
    if context in _REJECTED:
        raise DatasetMapError(f"{key}: un conjunto simulado no es un conjunto de datos humanos")
    _validate_areas(f"{key}/areas", item["areas"])
    _validate_phases(key, item["phases"], context)
    _validate_schedule(f"{key}/analog_schedule", item["analog_schedule"], context, pattern)
    _validate_controls(f"{key}/controls", item["controls"], item["population"], context)
    _validate_access(f"{key}/access", item["access"])
    _validate_emma_use(f"{key}/emma_use", item["emma_use"])
    _validate_role(f"{key}/role", item["role"], item["emma_use"]["used"], opened)


def _validate_kb_row(key: str, item: dict[str, Any]) -> None:
    """La fila de la base de conocimiento, con el apartado de donde sale; sin fila, sin apartado."""
    if item["kb_row"] is None:
        if item["kb_where"] is not None:
            raise DatasetMapError(f"{key}: `kb_where` sin la fila que sitúa")
        return
    if not _text(item, "kb_row") or not _text(item, "kb_where"):
        raise DatasetMapError(f"{key}: `kb_row` vacía o sin su apartado: lo que no hay es null")
    if item["kb_where"] not in KB_SECTIONS:
        raise DatasetMapError(
            f"{key}: apartado {item['kb_where']!r}; las filas salen de {sorted(KB_SECTIONS)}"
        )


def _validate_areas(key: str, areas: dict[str, Any] | None) -> None:
    """Las áreas de un estudio, enteras: tantas como dice la frase que las cuenta, sin repetir."""
    if areas is None:
        return
    _fields(key, areas, AREAS_FIELDS)
    _piece(f"{key}/cited", areas["cited"], _QUOTE_KEYS)
    items = areas["items"]
    for index, area in enumerate(items):
        _piece(f"{key}/items/{index}", area, AREA_FIELDS)
        if not (_text(area, "name") and _text(area, "what")):
            raise DatasetMapError(f"{key}/items/{index}: falta `name` o `what`")
    names = [area["name"] for area in items]
    if not _counted(areas["count"], names, areas["cited"]["quote"]):
        raise DatasetMapError(f"{key}: las áreas no cuadran con las que cuenta su fuente")


def _validate_schedule(
    key: str,
    schedule: list[dict[str, Any]] | None,
    context: EvidenceContext | None,
    pattern: list[str],
) -> None:
    """El calendario de un análogo: cada etapa con su frase, en el orden de la pauta de §3.2.

    Un análogo lo tiene siempre (sus tres fases de vuelo no proceden); un conjunto que no es de
    análogo no lo tiene: su calendario son sus fases.

    Los pasos se ordenan por la etapa en que empiezan, no por la última que nombran: una frase
    puede resumir todo el estudio y la siguiente detallar una sola etapa. Es lo que dice OSD-51
    («a 20 day ambulatory control period before BR and a 20 day recovery period after BR»,
    PRE, EXPOSURE y RECOVERY; después los grupos, COUNTERMEASURE).
    """
    if context not in _ANALOG:
        if schedule is not None:
            raise DatasetMapError(f"{key}: un calendario de análogo en un conjunto que no lo es")
        return
    if not schedule:
        raise DatasetMapError(f"{key}: un análogo sin su calendario")
    starts = []
    for index, step in enumerate(schedule):
        _piece(f"{key}/{index}", step, SCHEDULE_FIELDS)
        stages = step["stages"]
        if not stages or any(stage not in pattern for stage in stages):
            raise DatasetMapError(f"{key}/{index}: etapas {stages!r} fuera de la pauta {pattern}")
        for stage in stages:
            words = STAGE_WORDS.get(stage)
            if words is None or not words.search(step["quote"]):
                raise DatasetMapError(f"{key}/{index}: la frase no nombra la etapa {stage}")
        ranks = [pattern.index(stage) for stage in stages]
        if ranks != sorted(set(ranks)):
            raise DatasetMapError(f"{key}/{index}: etapas fuera del orden de la pauta")
        starts.append(ranks[0])
    # Y los pasos entre sí: cada uno empieza donde empezó el anterior o más adelante en la pauta.
    if starts != sorted(starts):
        raise DatasetMapError(f"{key}: pasos fuera del orden de la pauta")


def _validate_controls(
    key: str, item: dict[str, Any], population: str, context: EvidenceContext | None
) -> None:
    """Los controles de un conjunto: cada uno nombrado en su frase, de su población y su entorno."""
    _fields(key, item, CONTROL_FIELDS)
    status, items = item["status"], item["items"]
    if status not in CONTROL_STATUS:
        raise DatasetMapError(f"{key}: estado {status!r} desconocido")
    if (status == "listed") != bool(items):
        raise DatasetMapError(f"{key}: controles listados sin ninguno, o ninguno con lista")
    for index, quote in enumerate(item["absent"]):
        _piece(f"{key}/absent/{index}", quote, _QUOTE_KEYS)
    if item["absent"] and status not in {"listed", "none"}:
        raise DatasetMapError(
            f"{key}: la fuente dice qué controles no hay, y el estado es {status!r}"
        )
    kinds: set[str] = set()
    for index, control in enumerate(items):
        where = f"{key}/items/{index}"
        kind = control.get("kind")
        if kind not in CONTROL_KINDS:
            raise DatasetMapError(f"{where}: control {kind!r} desconocido")
        if kind in kinds:
            raise DatasetMapError(f"{where}: control {kind!r} repetido")
        kinds.add(kind)
        _piece(where, control, CONTROL_ITEM_FIELDS)
        if not CONTROL_WORDS[kind].search(control["quote"]):
            raise DatasetMapError(f"{where}: la frase no nombra un {CONTROL_KINDS[kind]}")
        if _NOT_A_CONTROL.search(control["quote"]):
            raise DatasetMapError(f"{where}: la frase niega el control o nombra un periodo")
        if control.get("population") not in _covered(population):
            raise DatasetMapError(
                f"{where}: control de población {control.get('population')!r}; el conjunto mide "
                f"{population!r}"
            )
        if kind == "inflight_1g" and context not in _FLIGHT:
            raise DatasetMapError(f"{where}: un control a 1 g en vuelo en un conjunto sin vuelo")
        # «Su propio control antes del vuelo» pide un vuelo: la fase basal de un reposo en cama
        # («baseline data collection») no lo es.
        if kind == "own_baseline" and context not in _FLIGHT:
            raise DatasetMapError(f"{where}: un control antes del vuelo en un conjunto sin vuelo")
        # En Tierra o en un análogo, todos están en Tierra: su grupo de control es otro. El gemelo
        # también es un control en Tierra («gemelo en Tierra»), y por lo mismo.
        if kind in {"ground", "twin"} and context in _NO_FLIGHT:
            raise DatasetMapError(f"{where}: un control en Tierra en un conjunto que ya está allí")
        if kind == "analog_control" and context not in _ANALOG:
            raise DatasetMapError(f"{where}: un grupo de control de análogo fuera de un análogo")
        if kind == "twin" and control["population"] != "human":
            raise DatasetMapError(f"{where}: un gemelo de control que no es una persona")
    _status_reasons(key, "sin controles", item, bool(item["absent"]))


def _validate_catalog(item: dict[str, Any]) -> None:
    """Un catálogo (§8): dice qué hay y dónde, no mide a nadie; por eso no tiene población."""
    key = str(item.get("id", "?"))
    _fields(key, item, CATALOG_FIELDS)
    for field in ("id", "name", "ref", "caveat"):
        if not _text(item, field):
            raise DatasetMapError(f"{key}: falta `{field}`")
    ref = registry.get(item["ref"])
    if ref.population is not None:
        raise DatasetMapError(f"{key}: un catálogo con población {ref.population!r} en su ficha")
    _validate_kb_row(key, item)
    if not item["what"]:
        raise DatasetMapError(f"{key}: sin ninguna frase leída de lo que es")
    for index, quote in enumerate(item["what"]):
        _piece(f"{key}/what/{index}", quote, _QUOTE_KEYS, CATALOG_HOSTS)
    _validate_access(f"{key}/access", item["access"], CATALOG_HOSTS)
    _validate_emma_use(f"{key}/emma_use", item["emma_use"])


def _validate_phases(
    key: str, phases: dict[str, Any], context: EvidenceContext | None
) -> None:
    if sorted(phases) != sorted(PHASES):
        raise DatasetMapError(f"{key}: hacen falta las tres fases, una vez cada una")
    for phase in PHASES:
        _validate_phase(f"{key}/{phase}", phase, phases[phase], context)


def _covered(population: str) -> set[str]:
    """Las poblaciones que caben en la de un estudio: el mixto tiene las dos."""
    return {"human", "animal", population} if population == "human_and_animal" else {population}


def _validate_cipher(raw: dict[str, Any]) -> None:
    _fields("cipher", raw, CIPHER_FIELDS)
    for field in ("name", "full_name", "studies_where"):
        if not _text(raw, field):
            raise DatasetMapError(f"cipher: falta `{field}`")
    for field in ("what", "cohort"):
        _piece(f"cipher/{field}", raw[field], _QUOTE_KEYS)
    if not _counted(raw["study_count"], raw["studies"], raw["what"]["quote"]):
        raise DatasetMapError("cipher: la lista de estudios no cuadra con la que da su página")
    if not raw["ladder"]:
        raise DatasetMapError("cipher: sin la escalera de duraciones")
    for index, rung in enumerate(raw["ladder"]):
        if not _text(rung, "id"):
            raise DatasetMapError(f"cipher/ladder/{index}: falta `id`")
        _piece(f"cipher/ladder/{index}", rung, _QUOTE_KEYS | {"id"})
    if raw["emma_study"] not in raw["studies"]:
        raise DatasetMapError(f"cipher: {raw['emma_study']!r} no es uno de sus estudios")
    _validate_phases("cipher", raw["phases"], None)
    _validate_access("cipher/access", raw["access"])
    _validate_emma_use("cipher/emma_use", raw["emma_use"])
    # CIPHER no deposita ficheros: no hay población de ficheros abiertos con la que validar.
    _validate_role("cipher/role", raw["role"], raw["emma_use"]["used"], None)


def _header(raw: dict[str, Any], block: str, fields: tuple[str, ...]) -> dict[str, Any]:
    """Un bloque de cabecera, con sus textos: uno que falte o no sea un bloque es un rechazo
    del contrato, no un error cualquiera que acabe en un 500 sin explicación."""
    value = raw.get(block)
    if not isinstance(value, dict) or not all(_text(value, field) for field in fields):
        raise DatasetMapError(f"`{block}` sin su texto y de dónde sale")
    return value


def _points(block: str, value: dict[str, Any]) -> list[str]:
    """Los puntos de un bloque de cabecera: una lista de textos, ninguno vacío."""
    points = value.get("points")
    if not isinstance(points, list) or not points or not all(
        isinstance(point, str) and point.strip() for point in points
    ):
        raise DatasetMapError(f"`{block}` sin sus puntos")
    # Repetido, un punto rompería el orden de la pauta, que se mide por su posición.
    if len(set(points)) != len(points):
        raise DatasetMapError(f"`{block}` con un punto repetido")
    return points


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza lo que no se pueda sostener con la fuente delante, o que diga de más sobre EMMA."""
    if not (_text(raw, "read_on") and _DATE.fullmatch(raw["read_on"])):
        raise DatasetMapError("falta `read_on` AAAA-MM-DD: una lectura sin fecha no se contrasta")
    # La tarea (§15), la regla de los tres niveles (§8) y la de la aptitud (la conversación): texto
    # literal del equipo, y la prueba lo contrasta con los documentos.
    for block in ("task", "rule", "fitness_rule"):
        _header(raw, block, ("text", "where"))
    milestones = _header(raw, "milestones", ("text", "where"))
    points = _points("milestones", milestones)
    if " → ".join(points) != milestones["text"]:
        raise DatasetMapError("los hitos no son los del texto de la conversación")
    keys = [_point_key(point) for point in points]
    if keys != sorted(set(keys)):
        raise DatasetMapError("los hitos no van en el orden del vuelo")
    pattern = _header(raw, "analog_pattern", ("text", "where"))
    if " → ".join(_points("analog_pattern", pattern)) != pattern["text"]:
        raise DatasetMapError("la pauta del análogo no es la del texto de la base de conocimiento")
    _points("controls_rule", _header(raw, "controls_rule", ("where",)))
    for block in ("datasets", "catalogs", "not_found"):
        if not isinstance(raw.get(block), list):
            raise DatasetMapError(f"`{block}` falta o no es una lista")
    if not isinstance(raw.get("cipher"), dict):
        raise DatasetMapError("`cipher` falta o no es un bloque")
    seen: set[str] = set()
    for item in raw["datasets"]:
        _validate_dataset(item, pattern["points"])
        if item["id"] in seen:
            raise DatasetMapError(f"{item['id']}: conjunto repetido")
        seen.add(item["id"])
    for item in raw["catalogs"]:
        _validate_catalog(item)
        if item["id"] in seen:
            raise DatasetMapError(f"{item['id']}: conjunto repetido")
        seen.add(item["id"])
    _validate_cipher(raw["cipher"])
    for quote in all_quotes(raw):
        # Una relectura es posterior a la lectura del fichero: antes no se había leído nada.
        if quote.get("read_on") is not None and quote["read_on"] < raw["read_on"]:
            raise DatasetMapError(
                f"{quote['ref']}: leída el {quote['read_on']}, antes que el fichero "
                f"({raw['read_on']})"
            )
    if not all(isinstance(line, str) and line.strip() for line in raw["not_found"]):
        raise DatasetMapError("una línea vacía en `not_found`")
    return raw


@cache
def read() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(DATASETS_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def _quotes_of(item: dict[str, Any]) -> list[dict[str, Any]]:
    quotes = [*item["subjects"], *item["variables"], *item["access"]["cited"]]
    for phase in item["phases"].values():
        quotes += phase["cited"]
    if item["areas"] is not None:
        quotes += [item["areas"]["cited"], *item["areas"]["items"]]
    quotes += item["analog_schedule"] or []
    quotes += [*item["controls"]["items"], *item["controls"]["absent"]]
    return quotes


def all_quotes(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Cada frase de fuente del mapa, esté donde esté."""
    quotes = [quote for item in raw["datasets"] for quote in _quotes_of(item)]
    for item in raw["catalogs"]:
        quotes += [*item["what"], *item["access"]["cited"]]
    cipher = raw["cipher"]
    quotes += [cipher["what"], cipher["cohort"], *cipher["ladder"], *cipher["access"]["cited"]]
    quotes += [quote for phase in cipher["phases"].values() for quote in phase["cited"]]
    return quotes


def cited_refs() -> frozenset[str]:
    """Las fichas del registro que sostienen alguna frase del mapa."""
    raw = read()
    refs = {quote["ref"] for quote in all_quotes(raw)}
    refs |= {item["ref"] for item in [*raw["datasets"], *raw["catalogs"]]}
    return frozenset(refs)


def _cited(item: dict[str, Any], read_on: str) -> dict[str, Any]:
    """Una frase resuelta en su ficha, con el día en que se leyó (el suyo, o el del fichero)."""
    ref = registry.get(item["ref"])
    return {
        "quote": item["quote"],
        "where": item["where"],
        "read_on": item.get("read_on") or read_on,
        "ref": ref.id,
        "source": ref.source,
        "url": ref.url,
        "unverified_display": [
            i18n.loc(registry.OPTIONAL_FIELDS[name]) for name in ref.unverified
        ],
    }


def segments(points: list[str]) -> list[dict[str, Any]]:
    """Los tramos entre hitos, con la fase a la que pertenece cada uno.

    Un tramo va de un hito al siguiente sin incluirlo; antes del primero y desde el último hay un
    tramo abierto. «Flight» abre el tramo en vuelo, que acaba en el primer hito R+.
    """
    keys = [_point_key(point) for point in points]
    out: list[dict[str, Any]] = [
        {
            "label": i18n.tr(f"antes de {points[0]}", f"before {points[0]}"),
            "low": None, "high": keys[0], "phase": "pre",
        }
    ]
    for index, point in enumerate(points):
        high = keys[index + 1] if index + 1 < len(points) else None
        label = (
            f"{point} → {points[index + 1]}" if high is not None
            else i18n.tr(f"desde {point}", f"from {point}")
        )
        phase = next(name for name, rank in _RANK.items() if rank == keys[index][0])
        out.append({"label": label, "low": keys[index], "high": high, "phase": phase})
    return out


def _ladder(item: dict[str, Any], tramos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada tramo de la escalera con los días leídos que caen en él, o el estado de su fase."""
    cells = []
    for tramo in tramos:
        phase = item["phases"][tramo["phase"]]
        labels = [
            label
            for label in phase["labels"]
            if (key := label_key(tramo["phase"], label)) is not None
            and (tramo["low"] is None or key >= tramo["low"])
            and (tramo["high"] is None or key < tramo["high"])
        ]
        cells.append({
            "segment": tramo["label"],
            "phase": tramo["phase"],
            "labels": labels,
            "status": phase["status"],
            # Sin días en el tramo, la palabra: de su fase, o que la fase tiene días, pero no aquí.
            "text": None if labels else (
                i18n.tr(EMPTY_SEGMENT, EMPTY_SEGMENT_EN) if phase["status"] == "labels"
                else _label(PHASE_STATUS, PHASE_STATUS_EN, phase["status"])
            ),
        })
    return cells


def _phase(item: dict[str, Any], read_on: str) -> dict[str, Any]:
    return {
        "status": item["status"],
        "status_text": _label(PHASE_STATUS, PHASE_STATUS_EN, item["status"]),
        "labels": list(item["labels"]),
        "cited": [_cited(quote, read_on) for quote in item["cited"]],
        "why": item["why"],
        "searched": item["searched"],
    }


def _emma_use(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "used_text": i18n.tr(EMMA_USE[item["used"]], EMMA_USE_EN[item["used"]])}


def _role(role: dict[str, Any]) -> dict[str, Any]:
    """El papel y la aptitud con sus palabras y el rótulo de deducción: la interfaz no redacta."""
    return {
        "level": role["level"],
        "level_text": _label(ROLE_LEVELS, ROLE_LEVELS_EN, role["level"]),
        "level_why": role["level_why"],
        "fitness": role["fitness"],
        "fitness_text": _label(FITNESS, FITNESS_EN, role["fitness"]),
        "fitness_why": role["fitness_why"],
        "basis_text": i18n.loc(ROLE_BASIS),
    }


def _access(access: dict[str, Any], read_on: str) -> dict[str, Any]:
    return {
        "level": access["level"],
        "level_text": _label(ACCESS_LEVELS, ACCESS_LEVELS_EN, access["level"]),
        "basis": access["basis"],
        "basis_text": _label(ACCESS_BASIS, ACCESS_BASIS_EN, access["basis"]),
        "cited": [_cited(quote, read_on) for quote in access["cited"]],
        "path": access["path"],
        "why": access["why"],
        "searched": access["searched"],
    }


def _controls(item: dict[str, Any], read_on: str) -> dict[str, Any]:
    return {
        "status": item["status"],
        "status_text": _label(CONTROL_STATUS, CONTROL_STATUS_EN, item["status"]),
        "items": [
            {
                "kind": control["kind"],
                "kind_text": _label(CONTROL_KINDS, CONTROL_KINDS_EN, control["kind"]),
                "population": control["population"],
                "population_display": i18n.loc(registry.POPULATIONS[control["population"]]),
                **_cited(control, read_on),
            }
            for control in item["items"]
        ],
        "absent": [_cited(quote, read_on) for quote in item["absent"]],
        "why": item["why"],
        "searched": item["searched"],
    }


def _areas(areas: dict[str, Any] | None, read_on: str) -> dict[str, Any] | None:
    if areas is None:
        return None
    return {
        "count": areas["count"],
        "cited": _cited(areas["cited"], read_on),
        "items": [
            {"name": area["name"], "what": area["what"], **_cited(area, read_on)}
            for area in areas["items"]
        ],
    }


def _schedule(schedule: list[dict[str, Any]] | None, read_on: str) -> list[dict[str, Any]] | None:
    if schedule is None:
        return None
    return [{"stages": list(step["stages"]), **_cited(step, read_on)} for step in schedule]


def _dataset(item: dict[str, Any], tramos: list[dict[str, Any]], read_on: str) -> dict[str, Any]:
    ref = registry.get(item["ref"])
    opened = item["open_population"]
    return {
        "id": item["id"],
        "name": item["name"],
        "ref": ref.id,
        "title": ref.title,
        "source": ref.source,
        "url": ref.url,
        "population": item["population"],
        "population_display": i18n.loc(registry.POPULATIONS[item["population"]]),
        "evidence_context": str(ref.evidence_context) if ref.evidence_context else None,
        "outside_enum_text": (
            i18n.loc(registry.OUTSIDE_ENUM) if "evidence_context" in ref.outside_enum else None
        ),
        "open_population": opened,
        "open_population_display": (
            i18n.loc(registry.POPULATIONS[opened]) if opened else None
        ),
        "open_population_note": item["open_population_note"],
        "kb_row": item["kb_row"],
        "kb_where": item["kb_where"],
        "subjects": [_cited(quote, read_on) for quote in item["subjects"]],
        "variables": [
            {"what": quote["what"], **_cited(quote, read_on)} for quote in item["variables"]
        ],
        "areas": _areas(item["areas"], read_on),
        "phases": {phase: _phase(item["phases"][phase], read_on) for phase in PHASES},
        "ladder": _ladder(item, tramos),
        "analog_schedule": _schedule(item["analog_schedule"], read_on),
        "controls": _controls(item["controls"], read_on),
        "access": _access(item["access"], read_on),
        "emma_use": _emma_use(item["emma_use"]),
        "role": _role(item["role"]),
        "caveat": item["caveat"],
    }


def _catalog(item: dict[str, Any], read_on: str) -> dict[str, Any]:
    ref = registry.get(item["ref"])
    return {
        "id": item["id"],
        "name": item["name"],
        "ref": ref.id,
        "title": ref.title,
        "source": ref.source,
        "url": ref.url,
        "kb_row": item["kb_row"],
        "kb_where": item["kb_where"],
        "what": [_cited(quote, read_on) for quote in item["what"]],
        "access": _access(item["access"], read_on),
        "emma_use": _emma_use(item["emma_use"]),
        "caveat": item["caveat"],
    }


def payload() -> dict[str, Any]:
    """El mapa como se sirve: cada cita resuelta en su ficha y cada día en su tramo."""
    # Una copia en el idioma de la petición, después de validar: la caché guarda el castellano.
    raw = i18n.localized(read(), DATASETS_PATH)
    read_on = raw["read_on"]
    tramos = segments(raw["milestones"]["points"])
    cipher = raw["cipher"]
    return {
        "note": i18n.loc(NOTE),
        "read_on": read_on,
        "task": dict(raw["task"]),
        "rule": dict(raw["rule"]),
        "fitness_rule": dict(raw["fitness_rule"]),
        "phases": {phase: _label(PHASES, PHASES_EN, phase) for phase in PHASES},
        "milestones": {
            "text": raw["milestones"]["text"],
            "where": raw["milestones"]["where"],
            "segments": [{"label": tramo["label"], "phase": tramo["phase"]} for tramo in tramos],
        },
        "analog_pattern": {
            "text": raw["analog_pattern"]["text"],
            "where": raw["analog_pattern"]["where"],
            "points": list(raw["analog_pattern"]["points"]),
        },
        "controls_rule": {
            "points": list(raw["controls_rule"]["points"]),
            "where": raw["controls_rule"]["where"],
        },
        "datasets": [_dataset(item, tramos, read_on) for item in raw["datasets"]],
        "catalogs": [_catalog(item, read_on) for item in raw["catalogs"]],
        "cipher": {
            "name": cipher["name"],
            "full_name": cipher["full_name"],
            "what": _cited(cipher["what"], read_on),
            "studies": list(cipher["studies"]),
            "studies_where": cipher["studies_where"],
            "cohort": _cited(cipher["cohort"], read_on),
            "ladder": [{"id": rung["id"], **_cited(rung, read_on)} for rung in cipher["ladder"]],
            "phases": {phase: _phase(cipher["phases"][phase], read_on) for phase in PHASES},
            "ladder_cells": _ladder(cipher, tramos),
            "access": _access(cipher["access"], read_on),
            "emma_study": cipher["emma_study"],
            "emma_use": _emma_use(cipher["emma_use"]),
            "role": _role(cipher["role"]),
        },
        "not_found": list(raw["not_found"]),
    }
