"""Mapa anatomico: de que region del cuerpo habla cada dominio (especificacion §10).

La especificacion pide un modo anatomico CUERPO → ORGANO → estado → variables → evidencia →
tendencia → contramedida, y que el visor sea un **cliente del mismo modelo de estado**, no una
fuente propia. Por eso el mapa vive aqui, en el backend, y la interfaz solo lo recorre: el
nivel de cada region es el del dominio (o dominios) que la cubren, calculado por el motor.

El mapa es de presentacion. No afirma nada que el motor no diga: una region "en vigilancia"
significa que un dominio que la cubre lo esta. Donde un dominio no tiene organo propio (la
radiacion afecta a todo el cuerpo; el sistema inmune no es un organo), se dice asi.

La cadena entera de cada región (`state`) también se compone aquí y no en la interfaz, por la
misma razón: el nivel, las variables que lo mueven, la evidencia y las contramedidas son las
que el análisis y el advisor ya dieron a `/status`. Y una región sin lecturas se dice sin
lecturas: "nominal" sin nada que mirar no es un estado.

RIESGO, HÁBITAT Y TIEMPO (decimocuarta ronda, 2026-10-21)
--------------------------------------------------------
La base de conocimiento (§11.1) pide la cadena BODY → ORGAN → HEALTH STATE → DATA → EVIDENCE →
TREND → RISK → COUNTERMEASURE, y la conversación de ideación dos cosas más: ver junto a la
alteración del astronauta los factores externos («ASTRONAUT TWIN ↔ HABITAT TWIN») y desplazarse
en el tiempo («Pre-flight → Day 30 → … → Recovery»). Faltaban las tres: el RIDGE de la región
solo salía si había una recomendación con contramedida, el contexto externo solo lo tenía el
detalle de una alerta, y `/anatomy/state` aceptaba `until` sin que nadie supiera qué instantes
pedir. Las tres se leen de donde ya viven, sin regla nueva:

- el riesgo de cada dominio es el de `risk_entity.summary` (los mismos campos que `/risks`);
- el contexto externo es el de una alerta (`analysis/alert_context.py`, con el mismo constructor
  que `/status`): anclado al inicio de la alerta si la región la tiene y al instante del estado
  si no, diciéndolo;
- los momentos (`moments`) son los cambios de fase del calendario, el regreso y los días
  posvuelo con lecturas (el R+ de la recuperación) agrupados en hitos, y el estado en uno de
  ellos es un recálculo con las reglas de hoy que no se firma, con el rótulo de la historia de
  alertas. La crónica enlaza sus hechos con estos momentos (`chronicle_moment`).

HITOS CON FUENTE Y PULMONES (decimosexta ronda, 2026-10-23)
----------------------------------------------------------
Los hitos R+90, R+180 y R+365 se decían «de diseño, sin fuente» mientras la banda ósea inferida ya
citaba la densitometría posvuelo de NASA a los 6 meses y al año. Ahora cada hito dice de qué ficha
sale y qué cubre esa ficha: los de Standard Measures son el calendario de ese estudio y los de la
densitometría, solo del hueso; ninguno es un calendario de todos los indicadores. Lo que ninguna
fuente leída da (R+90) sigue siendo de diseño. El prevuelo gana sus hitos L- con la misma regla.
Y el pulmón, que la conversación de ideación cuenta entre los órganos del gemelo, entra como el
hígado: una región sin nivel propio, con los indicadores que una ficha leída dice del pulmón.

MEDIDO, Y APARTE LO QUE SOLO SE HA VISTO EN ANIMALES (decimoséptima ronda, 2026-10-26)
-------------------------------------------------------------------------------------
La conversación de ideación, al pensar el hígado del gemelo, pide distinguir tres niveles: lo
medido en ese astronauta, lo inferido por el modelo y la «evidencia de investigación», un
mecanismo observado en estudios con animales o células «que no podemos afirmar que esté
ocurriendo» en él. El hígado solo tenía sus analitos; el estudio que motivó esa frase estaba en
el registro y solo lo citaba un docstring. Ahora una región puede llevar una capa aparte de
evidencia de investigación (`research_refs`), solo con fichas cuya población incluye animales,
con una frase fija que dice que no está medida en el tripulante. Sale solo en la cadena de la
región: no entra en el nivel, ni en la evidencia del dominio, ni en ninguna alerta, ni en la
matriz de riesgos. Y los hitos R+730 y R+1095, las densitometrías de
dos y tres años que la misma ficha de los de R+180 y R+365 ya daba, entran en «Momento».

LA CAPA DE INVESTIGACIÓN EN OTROS ÓRGANOS (decimonovena ronda, U16, 2026-10-31)
-------------------------------------------------------------------------------
La conversación de ideación nombra los órganos del gemelo con esa capa: «Cerebro → cognición,
sueño, aislamiento, radiación/CNS», «Músculos → pérdida/adaptación y efecto del ejercicio»,
«Sistema inmune/bazo → biomarcadores e información OSDR». Solo el hígado la tenía, y solo admitía
fichas con animales porque su frase fija decía «con animales». Ahora cada ficha de la capa es un
`ResearchItem`: la cita de siempre más un rótulo de población a la vista («modelo animal: ratón;
12 ratones…», «humanos: 24 mujeres…») que tiene que empezar por la clase de población que la
ficha declara en el registro. Una ficha sin población leída no entra; un rótulo que diga otra
clase que la ficha, tampoco. La frase fija dice lo que vale para todas: es de otras personas o de
animales, no está medido en este tripulante, cada ficha dice su población, y no cuenta. El
cerebro lleva además dónde se hace esa investigación (el NSRL, `research_facility`), como
instalación aparte de los estudios: no es un estudio y su ficha no tiene población. El bazo no
tiene región propia —EMMA no mide nada de él— y su evidencia de investigación (OSD-288, bazo de
ratón) cuelga de la región del sistema inmune, donde la conversación lo pone («Sistema
inmune/bazo»). La capa sigue sin entrar en el nivel, en la evidencia del dominio, en las alertas
ni en la matriz de riesgos; `rules_version` no la ve (`core/versioning.py` solo mira el análisis).

PARA QUÉ SIRVE CADA ÓRGANO (vigésima ronda, unidad 2, 2026-11-02)
----------------------------------------------------------------
El enunciado del reto pide una figura en la que cada parte del cuerpo, al pulsarla, «displays
information about its function and health status». El estado ya lo daba la cadena; la función no
la decía nadie, y la frase de cada región (`note`) habla de lo que EMMA mide, no del órgano. Ahora
cada región lleva `function`: una o dos frases de para qué sirve ese órgano o sistema en el cuerpo,
cada una con la ficha leída de la que sale (`function_refs`: el módulo de anatomía y fisiología
SEER del NCI y, para el ojo, la página del NEI). Es texto de divulgación: no entra en el nivel, ni
en la evidencia del dominio, ni en ninguna alerta. Donde no hay órgano que describir (la radiación,
«todo el cuerpo») no se inventa una función: `function` es `None` y `function_note` lo dice.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from app.advisor.recommendations import Recommendation
from app.analysis import alert_history, alert_support
from app.analysis.baseline import Deviation
from app.analysis.explain import changed
from app.analysis.explain import onset as alert_onset
from app.analysis.recovery import days_after_landing, flight
from app.analysis.risk import CrewHealthStatus, RiskLevel, representative_deviation
from app.analysis.trend import Trend
from app.core import display as number_display
from app.core import i18n
from app.core.mission import ADAPTATION_DAYS, RETURN_DAYS, phase_at
from app.evidence import registry
from app.evidence.links import amcl_alignment, evidence_for
from app.evidence.registry import Citation
from app.ingest.codes import CATALOG, DESCRIPTIVE_ONLY, Domain
from app.ingest.fhir import VitalObservation
from app.pain_on_skeleton import OWN_CT, REFERENCE
from app.volumes import assets as volume_assets
from app.volumes import skeleton_view

if TYPE_CHECKING:
    from app.core.storage import ObservationStore


# EL RÓTULO DE POBLACIÓN DE CADA FICHA DE LA CAPA DE INVESTIGACIÓN (decimonovena ronda, U16).
# Empieza por la clase que la ficha declara en el registro (`registry.POPULATIONS`), con estas
# palabras y dos puntos, y sigue con lo concreto que la ficha ya dice: especie, cuántos, dónde.
# Así un rótulo no puede empezar por «humanos» en un estudio en ratón: la clase de partida la pone
# el registro, no quien cita. Lo que sigue a los dos puntos es texto libre y solo lo vigila la
# revisión, frase a frase, en `test_each_new_research_relevance_says_no_more_than_its_card`.
RESEARCH_POPULATION_LABELS: dict[str, str] = {
    "animal": "modelo animal",
    "human": "humanos",
    "human_and_animal": "humanos y modelo animal",
}


# EL INGLÉS SE PONE AL SALIR (2026-11-15, dos idiomas con selector). Lo que este módulo compone se
# sigue componiendo en castellano, con las mismas líneas que fijan las pruebas y las campañas de
# mutantes; quien lo sirve (`to_dict`, `function_dict`, `research_dict`) lo pasa al idioma de la
# petición campo a campo. En castellano no se toca nada: sale lo compuesto, tal cual. El inglés
# de cada frase está al final del módulo (`ENGLISH`).
def _loc(text: str | None) -> str | None:
    return i18n.loc(text) if text is not None else None


def _cited(item: dict[str, Any]) -> dict[str, Any]:
    """Una cita ya servida, con su relevancia en el idioma de la petición: la relevancia la
    escribe quien cita (este módulo); el título y la nota de la ficha son del registro."""
    return {**item, "relevance": _loc(item.get("relevance"))}


@dataclass(frozen=True, slots=True)
class ResearchItem:
    """Una ficha de la capa de investigación con su rótulo de población a la vista.

    `population` es el rótulo que ve la tripulación junto a la ficha. Tiene que empezar por la
    clase de población que la ficha declara en el registro, con las palabras de
    `RESEARCH_POPULATION_LABELS` seguidas de dos puntos; lo que sigue es lo concreto leído en la
    ficha. Una ficha sin población en el registro —sin leer, o «no aplica», como la página de una
    instalación— no entra: el rótulo no tendría respaldo, y lo que no es un estudio va en
    `Region.research_facility`. El registro no tiene población «in vitro»: un estudio solo con
    células no entraría, y la frase fija de la capa no lo promete.
    """

    citation: Citation
    population: str

    def __post_init__(self) -> None:
        ref = self.citation.ref
        if ref.population is None:
            raise ValueError(
                f"{ref.id}: sin población en el registro (sin leer, no aplica o fuera del "
                "enumerado): no entra como estudio en la capa de investigación"
            )
        expected = f"{RESEARCH_POPULATION_LABELS[ref.population]}:"
        if not self.population.startswith(expected):
            raise ValueError(
                f"{ref.id}: el rótulo de población tiene que empezar por «{expected}», la clase "
                f"que declara su ficha ({registry.POPULATIONS[ref.population]})"
            )
        if not self.population.removeprefix(expected).strip():
            raise ValueError(f"{ref.id}: el rótulo de población no dice nada tras la clase")

    @property
    def id(self) -> str:
        return self.citation.id

    def to_dict(self) -> dict[str, Any]:
        return {**self.citation.to_dict(), "population_label": self.population}


@dataclass(frozen=True, slots=True)
class Region:
    """Una región del cuerpo: los dominios que la cubren o, si no tiene nivel propio, sus analitos.

    `analytes`, `level_of` y `analytes_source` van juntos (los tres o ninguno) y solo en una
    región sin dominios: una vista de unos indicadores del catálogo que ya cuentan en el nivel de
    otro dominio, con la ficha de la que sale la lista. No crea dominio ni nivel; su nivel lo dice
    `level_note`, con las palabras del backend.

    `note_refs` son las fichas en que se apoya la propia frase de la región (`note`) cuando nombra
    algo que el riesgo de sus dominios no cubre: la de la vejiga habla del riesgo de cálculos, y el
    riesgo de su dominio es la retención urinaria (decimosexta ronda, E9). No cambia nivel ni
    evidencia del dominio.

    `research_refs` es la capa aparte de «evidencia de investigación» (decimoséptima ronda; en
    otros órganos y con rótulo de población desde la decimonovena): lo observado en estudios con
    otras personas o con animales, que no está medido en el tripulante. Cada ficha es un
    `ResearchItem` y lleva su rótulo de población, que empieza por la clase que la ficha declara
    en el registro; la salvedad de alcance de la ficha, que el registro exige a toda ficha con
    animales, viaja con ella y dice qué parte es de personas. `research_facility` es, si lo hay,
    dónde se hace esa investigación (el NSRL en el cerebro): una instalación, no un estudio, y por
    eso su ficha no tiene población («no aplica») y va aparte de los estudios; sin estudios no hay
    instalación que citar. Nada de esto cambia nivel, evidencia del dominio ni alerta; no sale en
    `to_dict` (lo leen `/api/anatomy` y la matriz de riesgos, que enseñan la frase de la región),
    solo en la cadena (`research_dict`).

    `function` es para qué sirve el órgano o sistema en el cuerpo, no lo que EMMA mide de él, y
    `function_refs` las fichas leídas de las que sale (vigésima ronda): una función sin ficha no
    arranca, y unas fichas sin función tampoco. `None` donde no hay órgano que describir, y entonces
    `function_note` dice por qué (una de las dos, siempre). Va en `function_dict`, no en `to_dict`
    (que viaja con cada riesgo). No cambia nivel, evidencia del dominio ni alerta.
    """

    key: str
    display: str
    domains: tuple[Domain, ...]
    note: str
    analytes: tuple[str, ...] = ()
    level_of: Domain | None = None
    analytes_source: Citation | None = None
    note_refs: tuple[Citation, ...] = ()
    research_refs: tuple[ResearchItem, ...] = ()
    research_facility: Citation | None = None
    function: str | None = None
    function_refs: tuple[Citation, ...] = ()
    function_note: str | None = None

    def __post_init__(self) -> None:
        listed = (bool(self.analytes), self.level_of is not None, self.analytes_source is not None)
        if len(set(listed)) != 1 or (self.analytes and self.domains):
            raise ValueError(
                f"{self.key}: `analytes`, `level_of` y su fuente van juntos y sin dominios"
            )
        if self.research_facility is not None:
            if not self.research_refs:
                raise ValueError(
                    f"{self.key}: una instalación sin estudios no es capa de investigación"
                )
            if "population" not in self.research_facility.ref.not_applicable:
                raise ValueError(
                    f"{self.key}: {self.research_facility.id} tiene población o está sin leer: "
                    "es un estudio, no una instalación"
                )
        for key in self.analytes:
            code = CATALOG[key]
            # La región enseña lo que el dominio de su nivel ya evalúa: ni otro dominio, ni un
            # descriptivo (el estado no lo lee, y diría que cuenta).
            if code.domain is not self.level_of or key in DESCRIPTIVE_ONLY:
                raise ValueError(f"{self.key}: {key} no es un indicador evaluado de su nivel")
        self._check_function()

    def _check_function(self) -> None:
        """La función va con sus fichas, y sin ella la región dice por qué (una de las dos)."""
        if self.function is not None and not self.function.strip():
            raise ValueError(f"{self.key}: una función vacía no es una función; `None` y se dice")
        if (self.function is None) != (not self.function_refs):
            raise ValueError(
                f"{self.key}: la función y sus fichas van juntas: ni una frase sin fuente leída "
                "ni fichas sin frase"
            )
        explained = self.function_note is not None and bool(self.function_note.strip())
        if (self.function is None) != explained:
            raise ValueError(
                f"{self.key}: o la función o la frase que dice por qué no la hay, una de las dos"
            )

    @property
    def level_note(self) -> str | None:
        """De qué dominio es el nivel de una región sin nivel propio; `None` si lo tiene."""
        if self.level_of is None:
            return None
        return LEVEL_OF_NOTE.format(domain=self.level_of.display)

    @property
    def engine_domains(self) -> tuple[Domain, ...]:
        """Los dominios del motor de los que habla la región: los suyos o el de su nivel."""
        return self.domains if self.level_of is None else (self.level_of,)

    def shows(self, key: str) -> bool:
        """Si la región enseña ese indicador del catálogo (los descriptivos no los evalúa)."""
        if key in DESCRIPTIVE_ONLY:
            return False
        return key in self.analytes if self.level_of is not None else (
            CATALOG[key].domain in self.domains
        )

    def to_dict(self) -> dict[str, Any]:
        """Los campos de la región en el idioma de la petición: los de `_fields`, con el nombre,
        la frase, la nota del nivel y la relevancia de sus citas en inglés si se pide. Las claves,
        los dominios y los analitos son identificadores y no cambian."""
        found = self._fields()
        if i18n.current() != "en" or self.level_of is None:
            level_note = found["level_note"]
        else:
            level_note = i18n.loc(LEVEL_OF_NOTE).format(domain=i18n.loc(self.level_of.display))
        source = found["analytes_source"]
        return {
            **found,
            "display": i18n.loc(found["display"]),
            "note": i18n.loc(found["note"]),
            "level_note": level_note,
            "note_refs": [_cited(item) for item in found["note_refs"]],
            "analytes_source": _cited(source) if source is not None else None,
        }

    def _fields(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display": self.display,
            "domains": [str(item) for item in self.domains],
            "note": self.note,
            "analytes": list(self.analytes),
            "level_of": str(self.level_of) if self.level_of is not None else None,
            "level_note": self.level_note,
            "note_refs": [item.to_dict() for item in self.note_refs],
            # La ficha que nombra la frase de una región sin nivel propio («según MedlinePlus»):
            # también es de su frase, y la matriz de riesgos la enseña junto a `note_refs`.
            "analytes_source": (
                self.analytes_source.to_dict() if self.analytes_source is not None else None
            ),
        }

    def function_dict(self) -> dict[str, Any]:
        """Para qué sirve el órgano (vigésima ronda): la frase, sus fichas y, si no la hay, la
        frase de la región que lo dice. La sirven el mapa (`describe`) y la cadena (`state`); no
        va en `to_dict`, que también viaja con cada riesgo de `/api/risks`: no es de la frase de
        la región ni del riesgo. La interfaz la enseña tal cual."""
        found = self._function_fields()
        return {
            "function": _loc(found["function"]),
            "function_refs": [_cited(item) for item in found["function_refs"]],
            "function_note": _loc(found["function_note"]),
        }

    def _function_fields(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "function_refs": [item.to_dict() for item in self.function_refs],
            "function_note": self.function_note,
        }

    def research_dict(self) -> dict[str, Any] | None:
        """La capa aparte de investigación, con la frase que dice que no está medida en el
        tripulante, cada ficha con su rótulo de población y, si la hay, la instalación donde se
        hace; `None` en las regiones que no la tienen. Solo la sirve la cadena (`state`)."""
        found = self._research_fields()
        if found is None:
            return None
        facility = found["facility"]
        return {
            "note": i18n.loc(found["note"]),
            "items": [
                {**_cited(item), "population_label": i18n.loc(item["population_label"])}
                for item in found["items"]
            ],
            "facility": (
                {"note": i18n.loc(facility["note"]), "item": _cited(facility["item"])}
                if facility is not None
                else None
            ),
        }

    def _research_fields(self) -> dict[str, Any] | None:
        if not self.research_refs:
            return None
        return {
            "note": RESEARCH_NOTE,
            "items": [item.to_dict() for item in self.research_refs],
            "facility": (
                {"note": RESEARCH_FACILITY_NOTE, "item": self.research_facility.to_dict()}
                if self.research_facility is not None
                else None
            ),
        }


# EL HÍGADO, COMO REGIÓN SIN NIVEL PROPIO (decimoquinta ronda, decisión del usuario 2026-10-22).
#
# Los analitos hepáticos que EMMA lee de una analítica escaneada (`ingest/codes.py`) se agrupan en
# el dominio de nutrición, que es donde cuentan, y en la silueta caían dentro del aparato digestivo
# sin que nada dijera «hígado». EMMA no tiene un dominio hepático y esta región no lo crea: es una
# vista de esos analitos, sin nivel ni color de nivel, que dice de quién es el nivel. Cuáles son no
# lo decide EMMA: los que MedlinePlus (NLM) cuenta entre las pruebas de función hepática más
# comunes y que el catálogo tiene (el tiempo de protrombina, que también nombra, no está). La
# glucosa, la tiroides y el resto de la nutrición se quedan solo en el aparato digestivo.
LEVEL_OF_NOTE = "El nivel es del dominio {domain}."
LIVER_SOURCE = registry.cite(
    "medlineplus-liver-function-tests",
    "qué analitos son pruebas de función hepática: albúmina, proteínas totales, fosfatasa "
    "alcalina, ALT, AST, GGT, bilirrubina y LDH (y el tiempo de protrombina, que EMMA no tiene)",
)
LIVER_ANALYTES = (
    "albumin", "total-protein", "alkaline-phosphatase", "alt", "ast", "ggt",
    "bilirubin-total", "bilirubin-direct", "ldh",
)
# LA CAPA DE INVESTIGACIÓN DEL HÍGADO (decimoséptima ronda, 2026-10-26). La conversación de
# ideación separa lo MEDIDO en el astronauta, lo INFERIDO por el modelo y la RESEARCH EVIDENCE:
# «mecanismo observado en estudios animales/celulares, pero que no podemos afirmar que esté
# ocurriendo directamente en ese astronauta». El estudio que la motivó es la ficha `hayslip-2026`,
# leído primero su resumen y, el 2026-10-26 (decimoctava ronda, U15), su texto completo, de acceso
# abierto, que no cambia nada de esta frase: el experimento es en hígado de ratón (microgravedad
# simulada y análogos de radiación de espacio profundo, en Tierra) y lo humano es una comparación
# con transcriptómica de sangre del Twins Study y de Inspiration4 (sus autores: «Our goal was
# therefore not to equate mouse liver and human blood responses»). Aquí se dice eso y nada más:
# ni que le pase al tripulante, ni qué cambio concreto se vio, ni nada del tratamiento que probó.
# (Sin «Evidencia de investigación:» delante: es el título de la sección que la enseña.)
#
# Desde la decimonovena ronda (U16, 2026-10-31) la frase vale para todas las fichas de la capa, en
# personas o en animales: la clase de cada una la dice su rótulo de población, al lado. Por eso ya
# no dice «con animales»: diría de un reposo en cama de 24 mujeres que es de ratón.
RESEARCH_NOTE = (
    "Lo observado en estudios con otras personas o con animales, no medido en este tripulante; "
    "cada ficha dice su población. No afirma que le esté ocurriendo y no cuenta en el nivel ni en "
    "las alertas."
)
# La instalación donde se hace la investigación de una región, aparte de los estudios: la página
# de un laboratorio no mide a nadie y su ficha no tiene población.
RESEARCH_FACILITY_NOTE = (
    "Dónde se hace parte de esa investigación: la ficha es de una instalación, no de un estudio, "
    "y no tiene población."
)
LIVER_RESEARCH = ResearchItem(
    registry.cite(
        "hayslip-2026",
        "un mecanismo en hígado de ratón, no medido en este tripulante: redes de miARN y TGF-β "
        "asociadas a senescencia y fibrosis, con microgravedad simulada y análogos de radiación "
        "de espacio profundo en Tierra; lo humano del estudio es una comparación con "
        "transcriptómica de sangre del Twins Study y de Inspiration4",
    ),
    population=(
        "humanos y modelo animal: el experimento es en hígado de ratón, en Tierra; lo humano es "
        "una comparación con transcriptómica de sangre del Twins Study y de Inspiration4"
    ),
)

# LA CAPA DE INVESTIGACIÓN DEL CEREBRO, EL MÚSCULO Y EL SISTEMA INMUNE (decimonovena ronda, U16,
# 2026-10-31). Cada relevancia dice lo que dicen el título y la nota de su ficha y nada más; cada
# rótulo de población, la clase que declara la ficha y lo concreto que ya está leído en ella.
#
# El cerebro: la conversación de ideación le pone «radiación/CNS». EMMA no mide nada de eso; lo
# que hay es el informe de evidencia del HRP sobre el SNC y la radiación, que descansa sobre todo
# en roedores irradiados en aceleradores y dice que en personas lo visto es de radioterapia y que
# falta epidemiología humana. Dónde se hace esa investigación —el NSRL, en Brookhaven— va como
# instalación, aparte: la página del laboratorio no es un estudio.
CNS_RESEARCH = ResearchItem(
    registry.cite(
        "hrp-cns-radiation-evidence-report",
        "qué se sabe de la radiación espacial y el sistema nervioso central: déficits "
        "neurocognitivos en ratones y ratas con exposiciones bajas a núcleos HZE (10-50 cGy) en "
        "haces que simulan la radiación espacial; en personas, lo visto es de pacientes de "
        "radioterapia con exposiciones mucho mayores, y el informe dice que falta epidemiología "
        "humana con que estimar el riesgo y que ver efectos en astronautas de misiones pasadas es "
        "muy improbable",
    ),
    population=(
        "humanos y modelo animal: lo humano es sobre todo de pacientes de radioterapia y expuestos "
        "en Tierra, y de astronautas, los destellos de luz del Apolo; lo animal, sobre todo "
        "ratones y ratas irradiados en aceleradores"
    ),
)
NSRL_FACILITY = registry.cite(
    "bnl-nsrl",
    "dónde se irradia con haces de iones pesados que simulan los rayos cósmicos: el informe del "
    "SNC lo nombra como ejemplo de acelerador, y la página del laboratorio se describe como «the "
    "only place designed and built to study a space radiation environment right here on Earth's "
    "surface»",
)
# El músculo: «pérdida/adaptación y efecto del ejercicio». Tres poblaciones distintas, cada una
# con su rótulo: el informe del HRP (vuelo, análogos y animales; lo leído es de la ISS y del
# STS-78), el reposo en cama de WISE 2005 (personas, sin vuelo, con ejercicio como contramedida)
# y el músculo de ratón
# de Rodent Research-9 (lo humano de esa ficha se analiza en la publicación, no está en los
# ficheros). El dominio musculoesquelético de EMMA es el dolor autoinformado: nada de esto lo mide.
MUSCLE_RESEARCH_REPORT = ResearchItem(
    registry.cite(
        "hrp-muscle-evidence-report",
        "qué se sabe de la pérdida de masa, fuerza y resistencia muscular en vuelo: en la ISS la "
        "fuerza se mide antes y después de la misión, y el informe, de 2015, anunciaba que en "
        "vuelo se seguiría por primera vez la masa muscular con ecografía (estudio SPRINT); la "
        "única prueba de fuerza en vuelo que describe es un experimento, el dinamómetro de "
        "pantorrilla del STS-78",
    ),
    population=(
        "humanos y modelo animal: el informe junta vuelo (de Mercury a la ISS), análogos en "
        "Tierra y estudios con animales; lo que EMMA leyó es de tripulaciones de la ISS y del "
        "STS-78, en el transbordador"
    ),
)
MUSCLE_RESEARCH_BEDREST = ResearchItem(
    registry.cite(
        "osd-51",
        "qué hace al músculo la descarga sin vuelo y qué cambia una contramedida: transcriptoma "
        "de músculo esquelético en 60 días de reposo en cama, con un grupo solo en reposo y dos "
        "con contramedida, ejercicio o nutrición; no es vuelo ni constantes vitales",
    ),
    population=(
        "humanos: 24 mujeres jóvenes sanas en el reposo en cama WISE 2005, 60 días en Tierra"
    ),
)
MUSCLE_RESEARCH_MOUSE = ResearchItem(
    registry.cite(
        "osd-343",
        "un estudio multi-ómico cuyo título nombra el estrés mitocondrial como eje de la respuesta "
        "al vuelo; lo abierto en OSDR es la metabolómica del gastrocnemio de Rodent Research-9, "
        "en ratón; respalda un mecanismo, no un umbral ni una medida sobre este tripulante",
    ),
    population=(
        "humanos y modelo animal: los ficheros abiertos son de músculo de ratón (gastrocnemio, "
        "Rodent Research-9); lo humano, métricas de 59 astronautas y datos del Twins Study que la "
        "publicación analiza y los ficheros no publican"
    ),
)
# El sistema inmune y el bazo: «biomarcadores e información OSDR». El bazo no tiene región propia
# (EMMA no mide nada de él) y su evidencia cuelga de aquí. OSD-288 ya es evidencia del dominio
# inmune (`evidence/links.py`, con su relevancia de dominio) y se queda allí: moverla cambiaría
# `/status`. Aquí se vuelve a citar con otra relevancia y con su rótulo, porque lo que la
# conversación pide de esta capa es que diga a la vista de quién es: de ratón, no del tripulante.
# La «firma inmune del tripulante desde OSD-288» está rechazada (`docs/contexto/README.md`): esto
# es evidencia junto al órgano, nunca un estado.
IMMUNE_RESEARCH_REPORT = ResearchItem(
    registry.cite(
        "hrp-immune-evidence-report",
        "qué se sabe en personas y en animales: en pruebas posvuelo, función de células T muy "
        "deprimida tras 6 meses de vuelo; en vuelo, reactivación de herpesvirus latentes en "
        "misiones cortas y largas, y síntomas clínicos en la ISS (herpes labial, erupciones, "
        "alergias atípicas e infecciones), por lo general sin poder confirmarlos; en animales, "
        "función de células T y NK del bazo "
        "reducida en ratas del SLS-2 y masa del bazo reducida en ratones tras 13 días del STS-135",
    ),
    population=(
        "humanos y modelo animal: tripulantes del transbordador y de la ISS, en vuelo y posvuelo, "
        "y análogos en Tierra; ratas y ratones en vuelo y en Tierra, y cultivos celulares; lo "
        "leído no da un número total de tripulantes y dice que los estudios en vuelo han sido de "
        "pocos sujetos o de vuelos cortos"
    ),
)
IMMUNE_RESEARCH_SPLEEN = ResearchItem(
    registry.cite(
        "osd-288",
        "el bazo en ratón tras 35 días en la ISS: transcriptoma por "
        "secuenciación («transcriptome analysis by next-generation sequencing technology is "
        "performed about spleen»); respalda que el vuelo altera la función inmune en un "
        "mamífero, no una firma inmune de este tripulante",
    ),
    population=(
        "modelo animal: ratón; 12 ratones volaron 35 días en la ISS y el conjunto publica 9 "
        "muestras de bazo: 3 de control en Tierra, 3 de vuelo con gravedad por centrifugación y "
        "3 de vuelo en microgravedad"
    ),
)
# EL RIESGO DE CÁLCULOS QUE NOMBRA LA FRASE DE LA VEJIGA (decimosexta ronda, E9, 2026-10-23). La
# frase lo nombraba sin ficha; ahora lleva el informe de evidencia del HRP en que se apoya. El
# dominio lo cita además como riesgo adicional (`evidence/links.py`, `ADDITIONAL_HRP_RISKS`).
RENAL_STONE_SOURCE = registry.cite(
    "hrp-renal-stone-evidence-report",
    "por qué la ingesta de líquidos y la orina importan frente a los cálculos: el informe pone la "
    "deshidratación relativa y el volumen de orina entre los factores del riesgo, y da beber más "
    "para aumentar la orina como primera medida de prevención para todo tipo de cálculo",
)

# LOS PULMONES, COMO REGIÓN SIN NIVEL PROPIO (decimosexta ronda, 2026-10-23), con el patrón del
# hígado. La frecuencia respiratoria y la saturación de oxígeno cuentan en el dominio
# cardiovascular, y en la silueta caían en el corazón sin que nada dijera «pulmón». EMMA no tiene
# un dominio respiratorio y esta región no lo crea. Cuáles son no lo decide EMMA: los que el NHLBI
# nombra entre lo que se mira cuando los pulmones no llevan bastante oxígeno a la sangre (la
# respiración rápida y el oxígeno en sangre). La temperatura, el pulso y la presión se quedan solo
# en el corazón.
LUNG_SOURCE = registry.cite(
    "nhlbi-respiratory-failure",
    "qué indicadores son del pulmón: la respiración rápida y el oxígeno en sangre, que el NHLBI "
    "nombra entre lo que se mira cuando los pulmones no llevan bastante oxígeno a la sangre",
)
LUNG_ANALYTES = ("respiratory-rate", "oxygen-saturation")
# Sin contramedidas propias: las que proponga el advisor son del dominio de su nivel y salen en la
# región de ese dominio, no repetidas aquí.
LEVEL_ELSEWHERE_RECOMMENDATIONS_NOTE = (
    "Sin contramedidas propias: las del dominio {domain} salen en la región «{region}»."
)

# PARA QUÉ SIRVE CADA ÓRGANO (vigésima ronda, unidad 2, 2026-11-02). Cada frase dice lo que dicen
# las frases citadas en la nota de su ficha y nada más; la relevancia dice qué parte respalda. Las
# fichas son el módulo SEER de anatomía y fisiología del NCI (sin fecha en la página) y, para el
# ojo, la del NEI. Son de anatomía humana general, no de vuelo: ninguna dice qué le pasa al órgano
# en el espacio, y la frase tampoco.
NO_FUNCTION_NOTE = (
    "No es un órgano ni un sistema del cuerpo: la región reúne la radiación, que llega a todo el "
    "cuerpo. No hay una función que describir."
)
BRAIN_FUNCTION = (
    "El sistema nervioso, con el cerebro, es el principal sistema de control, regulación y "
    "comunicación del cuerpo y el centro de la actividad mental: el pensamiento, el aprendizaje y "
    "la memoria."
)
BRAIN_FUNCTION_SOURCE = registry.cite(
    "seer-nervous-system",
    "para qué sirve el sistema nervioso: control, regulación y comunicación del cuerpo, y la "
    "actividad mental (pensamiento, aprendizaje y memoria)",
)
EYES_FUNCTION = (
    "Los ojos permiten ver: en la retina, unas células llamadas fotorreceptores convierten la luz "
    "en señales eléctricas, que viajan por el nervio óptico hasta el cerebro, y el cerebro las "
    "convierte en las imágenes que se ven."
)
EYES_FUNCTION_SOURCE = registry.cite(
    "nei-how-the-eyes-work",
    "para qué sirven los ojos y el nervio óptico: la retina convierte la luz en señales eléctricas "
    "y el nervio óptico las lleva al cerebro",
)
HEART_FUNCTION = (
    "El corazón es una bomba muscular que impulsa la sangre por un circuito cerrado de vasos "
    "(arterias, venas y capilares); en los capilares la sangre cumple su función de transporte."
)
HEART_FUNCTION_SOURCE = registry.cite(
    "seer-cardiovascular-system",
    "para qué sirven el corazón y la circulación: una bomba muscular y un circuito cerrado de "
    "vasos, y en los capilares la función de transporte de la sangre",
)
LUNGS_FUNCTION = (
    "El aparato respiratorio, junto con el circulatorio, lleva a las células el oxígeno que "
    "necesitan y retira productos de desecho del metabolismo; en los pulmones se intercambian "
    "gases con la sangre. También ayuda a regular el pH de la sangre."
)
LUNGS_FUNCTION_SOURCE = registry.cite(
    "seer-respiratory-system",
    "para qué sirven los pulmones: el aporte de oxígeno y la retirada de desechos del metabolismo, "
    "el intercambio de gases con la sangre y la ayuda a regular su pH",
)
BONES_FUNCTION = (
    "Los huesos forman el esqueleto, un armazón rígido que sostiene el cuerpo frente a la gravedad "
    "y protege los órganos blandos; con los músculos hacen de palancas para el movimiento, y la "
    "formación de las células de la sangre ocurre sobre todo en su médula roja."
)
BONES_FUNCTION_SOURCE = registry.cite(
    "seer-skeletal-system",
    "para qué sirven los huesos: sostén frente a la gravedad, protección, palancas del movimiento "
    "con los músculos y formación de las células de la sangre en la médula roja",
)
MUSCLES_FUNCTION = (
    "Los músculos, unidos a los huesos, a órganos internos y a vasos sanguíneos, producen el "
    "movimiento al contraerse; su contracción mantiene la postura, como al estar sentado o de pie, "
    "y su metabolismo produce calor que ayuda a mantener la temperatura del cuerpo."
)
MUSCLES_FUNCTION_SOURCE = registry.cite(
    "seer-muscular-system",
    "para qué sirven los músculos: movimiento por contracción, postura y calor para la temperatura "
    "del cuerpo",
)
URINARY_FUNCTION = (
    "El aparato urinario mantiene el volumen y la composición de los líquidos del cuerpo dentro de "
    "lo normal: regula cuánta agua se elimina con la orina y libra al cuerpo de productos de "
    "desecho del metabolismo de las células."
)
URINARY_FUNCTION_SOURCE = registry.cite(
    "seer-urinary-system",
    "para qué sirve el aparato urinario: mantener el volumen y la composición de los líquidos del "
    "cuerpo, regular el agua que sale con la orina y eliminar desechos del metabolismo",
)
DIGESTIVE_FUNCTION = (
    "El aparato digestivo convierte los alimentos en moléculas que las células pueden absorber y "
    "usar: los toma por la boca, los descompone de forma mecánica y química, los hace avanzar por "
    "el tubo digestivo, absorbe los nutrientes y elimina lo que no se puede digerir ni absorber."
)
DIGESTIVE_FUNCTION_SOURCE = registry.cite(
    "seer-digestive-system",
    "para qué sirve el aparato digestivo: convertir los alimentos en moléculas que las células "
    "absorben y usan, en las seis actividades que nombra la página",
)
LIVER_FUNCTION = (
    "El hígado tiene muchas funciones, muchas de ellas vitales; entre ellas, fabrica sales "
    "biliares y proteínas del plasma, almacena, desintoxica, interviene en el metabolismo de los "
    "hidratos de carbono, las grasas y las proteínas, y unas células suyas, las de Kupffer, "
    "limpian la sangre."
)
LIVER_FUNCTION_SOURCE = registry.cite(
    "seer-digestive-accessory-organs",
    "para qué sirve el hígado: la lista de funciones de la página (sales biliares, proteínas del "
    "plasma, almacenamiento, desintoxicación, metabolismo) y la limpieza de la sangre por las "
    "células de Kupffer",
)
IMMUNE_FUNCTION = (
    "Defiende al cuerpo de los microorganismos invasores y de la enfermedad: los órganos "
    "linfáticos filtran la linfa para retirar microorganismos y otras partículas extrañas, y "
    "contienen linfocitos que destruyen los organismos invasores."
)
IMMUNE_FUNCTION_SOURCE = registry.cite(
    "seer-lymphatic-system",
    "para qué sirve la defensa del cuerpo: la del sistema linfático frente a microorganismos "
    "invasores, con el filtrado de la linfa y los linfocitos",
)


REGIONS: tuple[Region, ...] = (
    Region(
        "brain", "Cerebro: sueño, vigilancia, estado de ánimo", (Domain.BEHAVIORAL,),
        "El dominio conductual: sueño, ritmo circadiano, PVT y autoinforme de ánimo.",
        research_refs=(CNS_RESEARCH,), research_facility=NSRL_FACILITY,
        function=BRAIN_FUNCTION, function_refs=(BRAIN_FUNCTION_SOURCE,),
    ),
    Region(
        "eyes", "Ojos y nervio óptico", (Domain.NEURO_OCULAR,),
        "Síndrome neuro-ocular asociado al vuelo (SANS), por ecografía de la vaina.",
        function=EYES_FUNCTION, function_refs=(EYES_FUNCTION_SOURCE,),
    ),
    Region(
        "heart", "Corazón y circulación", (Domain.CARDIOVASCULAR,),
        "Pulso, variabilidad, presión y ortostatismo.",
        function=HEART_FUNCTION, function_refs=(HEART_FUNCTION_SOURCE,),
    ),
    Region(
        "lungs", "Pulmones", (),
        "No es un dominio de EMMA: la frecuencia respiratoria y la saturación de oxígeno cuentan "
        "en el dominio cardiovascular. Son las del pulmón según el NHLBI: la respiración rápida y "
        "el oxígeno en sangre.",
        analytes=LUNG_ANALYTES, level_of=Domain.CARDIOVASCULAR, analytes_source=LUNG_SOURCE,
        function=LUNGS_FUNCTION, function_refs=(LUNGS_FUNCTION_SOURCE,),
    ),
    Region(
        "bones", "Huesos de carga", (Domain.BONE,),
        "Marcadores de resorción, carga de impacto y ejercicio; la densidad solo se infiere.",
        function=BONES_FUNCTION, function_refs=(BONES_FUNCTION_SOURCE,),
    ),
    Region(
        "muscles", "Espalda y músculo-esquelético", (Domain.MUSCULOSKELETAL,),
        "Dolor autoinformado en el mapa corporal.",
        research_refs=(MUSCLE_RESEARCH_REPORT, MUSCLE_RESEARCH_BEDREST, MUSCLE_RESEARCH_MOUSE),
        function=MUSCLES_FUNCTION, function_refs=(MUSCLES_FUNCTION_SOURCE,),
    ),
    Region(
        "bladder", "Riñones, vejiga y vías urinarias", (Domain.GENITOURINARY,),
        "Retención urinaria por ecografía; ingesta de líquidos y orina frente al riesgo de "
        "cálculos.",
        note_refs=(RENAL_STONE_SOURCE,),
        function=URINARY_FUNCTION, function_refs=(URINARY_FUNCTION_SOURCE,),
    ),
    Region(
        "digestive", "Aparato digestivo: nutrición", (Domain.NUTRITION,),
        "Ingesta real y aceptabilidad de la comida.",
        function=DIGESTIVE_FUNCTION, function_refs=(DIGESTIVE_FUNCTION_SOURCE,),
    ),
    Region(
        "liver", "Hígado", (),
        "No es un dominio de EMMA: sus analitos cuentan en el dominio nutrición. Son los de las "
        "pruebas de función hepática más comunes según MedlinePlus.",
        analytes=LIVER_ANALYTES, level_of=Domain.NUTRITION, analytes_source=LIVER_SOURCE,
        research_refs=(LIVER_RESEARCH,),
        function=LIVER_FUNCTION, function_refs=(LIVER_FUNCTION_SOURCE,),
    ),
    Region(
        "immune", "Sistema inmune (todo el cuerpo)", (Domain.IMMUNE,),
        "No es un órgano: recuento, reactivación viral y síntomas.",
        research_refs=(IMMUNE_RESEARCH_REPORT, IMMUNE_RESEARCH_SPLEEN),
        function=IMMUNE_FUNCTION, function_refs=(IMMUNE_FUNCTION_SOURCE,),
    ),
    Region(
        "whole-body", "Todo el cuerpo: radiación", (Domain.RADIATION,),
        "La radiación no tiene órgano propio en EMMA: dosis acumulada y eventos solares.",
        function_note=NO_FUNCTION_NOTE,
    ),
)


def _home_regions(regions: Sequence[Region]) -> dict[str, Region]:
    """La región del dominio del nivel de cada región sin nivel propio, comprobada al importar.

    Sin ella, la nota de contramedidas diría «salen en la región «»»: mejor no arrancar.
    """
    homes: dict[str, Region] = {}
    for region in regions:
        if region.level_of is None:
            continue
        found = [item for item in regions if region.level_of in item.domains]
        if len(found) != 1:
            raise ValueError(f"{region.key}: el dominio de su nivel no tiene una región propia")
        homes[region.key] = found[0]
    return homes


HOME_REGIONS = _home_regions(REGIONS)


def describe() -> list[dict[str, Any]]:
    return [{**item.to_dict(), **item.function_dict()} for item in REGIONS]


# --------------------------------------------------------------------------- #
# La cadena entera de una región (especificación §10)
# --------------------------------------------------------------------------- #
#
# El panel enseñaba el nivel de cada región calculándolo en el cliente (el peor de sus
# dominios, con "nominal" por defecto) y, al abrir una, remitía a otros paneles para la
# evidencia y la tendencia. Dos fallos: la interfaz decidía un nivel (§4: el visor es cliente,
# no fuente), y una región sin una sola lectura salía "nominal" como si se hubiera valorado.
#
# Aquí se compone la cadena con lo que el análisis YA calculó para `/status`: nada de esto
# puntúa, ni toca umbrales, ni mueve un nivel (invariante 5). Si algo de aquí discrepara de
# `/status`, el fallo estaría aquí.

_LEVEL_ORDER: tuple[RiskLevel, ...] = (
    RiskLevel.NOMINAL, RiskLevel.WATCH, RiskLevel.CONCERN, RiskLevel.CRITICAL,
)

# El indicador del que `/status` toma la dosis acumulada cuando nadie la da por parámetro.
CUMULATIVE_DOSE = "cumulative-dose"

NO_DATA_NOTE = "Sin lecturas de esta región: no hay estado que valorar. No equivale a nominal."
# Tres motivos distintos para no proponer nada, y cada uno se dice con el suyo. Sin lecturas no
# vale "el análisis no encontró nada": no miró nada, y decirlo así sería pintarla de verde.
NOTHING_TO_ASSESS_NOTE = "Sin contramedidas propuestas: no hay lecturas de esta región que valorar."
NO_FINDINGS_NOTE = (
    "Sin contramedidas propuestas: el análisis no encontró nada fuera de lo esperado en esta "
    "región."
)
# Hoy no ocurre (la biblioteca cubre todos los dominios); si dejara de cubrir uno, que la región
# no diga que no hay hallazgos cuando lo que falta es la contramedida.
NO_LIBRARY_ENTRY_NOTE = (
    "Sin contramedidas en la biblioteca para lo que el análisis encontró en esta región."
)


def _trend(trend: Trend) -> dict[str, Any]:
    return {
        "direction": str(trend.direction),
        "significant": trend.significant,
        "concerning": trend.is_concerning,
        "slope_per_week": round(trend.slope_per_week, 4),
        "span_days": round(trend.span_days, 1),
        "points": trend.points,
        "description": trend.describe(),
    }


def _variable(
    reading: VitalObservation,
    counted: Deviation | None,
    trend: Trend | None,
    counted_as_dose: bool = False,
    counted_type: str | None = None,
) -> dict[str, Any]:
    code = reading.code
    return {
        "key": code.key,
        "display": code.display,
        "display_es": code.display_es,
        "unit": code.unit,
        "decimals": number_display.DECIMALS[code.key],
        "domain": str(code.domain),
        # El último valor, con su instante: una lectura antigua se tiene que poder ver como tal.
        "value": reading.value,
        "effective": reading.effective.isoformat(),
        # De dónde sale el dato: medido / inferido / predicho, y en qué entorno (§2).
        "observation_type": str(reading.observation_type),
        "evidence_context": str(reading.evidence),
        # Lleva al dominio a su nivel: el motor la cuenta como hallazgo (abajo, por qué).
        "contributes": (
            counted is not None or (trend is not None and trend.is_concerning) or counted_as_dose
        ),
        # La desviación que el motor cuenta para el indicador; su texto es el de `drivers`.
        # Con el tipo de su lectura, como en el detalle de `/status` (§5.37.1).
        "deviation": changed(counted, counted_type) if counted is not None else None,
        "trend": _trend(trend) if trend is not None else None,
    }


class ContextAround(Protocol):
    """El contexto externo alrededor de un inicio: el constructor del de las alertas (`routes`).

    `alert=False` lo pide quien no tiene alerta: se ancla en el instante del estado y lo dice.
    Uno solo para `/status` y el modo anatómico, para que las dos vistas no discrepen.
    """

    def __call__(self, onset: dt.datetime | None, alert: bool = True) -> dict[str, Any]: ...


def _context_anchor(
    domains: Iterable[Domain], status: CrewHealthStatus, current: Sequence[Deviation]
) -> tuple[dt.datetime | None, bool]:
    """El inicio de la alerta de la región, el mismo que da su detalle, y si la tiene.

    Hay alerta donde `/status` la da: un dominio por encima de nominal. El inicio es el de
    `explain.onset`, el que usa el detalle de la alerta, con las mismas desviaciones: el contexto
    de la región y el de su alerta se anclan en el mismo instante. Hoy cada región tiene un solo
    dominio (lo vigila `BodySilhouette.test.ts`); con varios con alerta, el primer inicio.
    """
    alerted = [
        domain for domain in domains
        if (risk := status.domains.get(domain)) is not None
        and risk.level is not RiskLevel.NOMINAL
    ]
    onsets = [found for domain in alerted if (found := alert_onset(domain, current)) is not None]
    return min(onsets, default=None), bool(alerted)


def state(
    status: CrewHealthStatus,
    observations: Sequence[VitalObservation],
    current: Sequence[Deviation],
    trends: Mapping[str, Trend],
    recommendations: Sequence[Recommendation],
    dose_from_reading: bool = False,
    context_around: ContextAround | None = None,
) -> list[dict[str, Any]]:
    """Por región: estado → variables → evidencia → tendencia → riesgo → contramedida, y el
    contexto externo.

    Todo llega calculado y es lo mismo que recibió el motor: `status` es su veredicto, `current`
    las desviaciones de la ventana actual, `trends` las derivas y `recommendations` lo que el
    advisor ya propone. Un dominio sin lecturas y sin hallazgo sale con `level: None`, y la
    región que solo tiene dominios así, también. `dose_from_reading`: la dosis acumulada que
    valoró el motor salió de la última lectura registrada, no de un parámetro.
    `context_around`: el constructor del contexto de las alertas; sin él, `context` es `None`.
    """
    # `risk_entity` importa este módulo (las regiones de cada riesgo): se lee aquí, al llamar,
    # para no cerrar el ciclo al importar.
    from app import risk_entity

    # Las regiones sin alerta comparten el mismo contexto (anclado en el instante del estado): se
    # compone una vez por ancla, no una por región.
    contexts: dict[tuple[dt.datetime | None, bool], dict[str, Any]] = {}

    def context_of(region: Region) -> dict[str, Any] | None:
        if context_around is None:
            return None
        # Una región sin nivel propio se ancla en la alerta del dominio de su nivel, si la hay.
        anchor = _context_anchor(region.engine_domains, status, current)
        if anchor not in contexts:
            contexts[anchor] = context_around(*anchor)
        return copy.deepcopy(contexts[anchor])

    # A igualdad de instante se queda la primera, como al elegir la dosis registrada en
    # `routes._assess` (`max` por instante): el valor que se enseña es el que se valoró.
    latest: dict[str, VitalObservation] = {}
    for reading in observations:
        held = latest.get(reading.key)
        if held is None or reading.effective > held.effective:
            latest[reading.key] = reading

    # QUÉ VARIABLE «CONTRIBUYE» LO DECIDE EL MOTOR, NO UNA LECTURA SUELTA.
    #
    # El motor no cuenta cualquier lectura fuera de lo esperado: cuenta la desviación
    # representativa de cada indicador, que exige persistencia o una ráfaga grave
    # (`risk.representative_deviation`; un cruce aislado es antes un artefacto que un evento).
    # Marcar aquí como contribuyente toda lectura preocupante de la ventana señalaría variables
    # que el motor descartó como ruido. Se usa su misma función sobre su misma entrada, y la
    # prueba de coherencia compara el texto resultante con los `drivers` de `/status`.
    by_key: dict[str, list[Deviation]] = {}
    for deviation in current:
        by_key.setdefault(deviation.key, []).append(deviation)
    counted = {
        key: found
        for key, series in by_key.items()
        if (found := representative_deviation(series)) is not None
    }
    # La dosis acumulada es el único indicador que cuenta sin desviación ni deriva: el motor no
    # la juzga contra una base, la mide contra el límite de carrera, y la suma en cuanto no es
    # cero (`RiskEngine.assess`). Si salió de una lectura, esa lectura es la variable que mueve
    # la radiación; si salió de un parámetro, ninguna variable del tripulante la explica.
    dose_counted = dose_from_reading and status.dose_fraction > 0
    # El tipo de la lectura de cada desviacion contada, leido del registro como en `/status`.
    counted_types = {
        key: (None if kind == alert_support.NOT_LOCATED else kind)
        for key, kind in zip(
            counted, alert_support.observation_types(counted.values(), observations), strict=True
        )
    }

    regions: list[dict[str, Any]] = []
    for region in REGIONS:
        # Sin los descriptivos (`codes.DESCRIPTIVE_ONLY`): el estado no los lee, y la región
        # no los evalúa. En el orden del catálogo, como siempre.
        # (Una región sin nivel propio enseña solo sus analitos, también en el orden del catálogo.)
        codes = [code for code in CATALOG.values() if region.shows(code.key)]
        measured = [code for code in codes if code.key in latest]
        entries: list[dict[str, Any]] = []
        valued: list[RiskLevel] = []
        for domain in region.domains:
            risk = status.domains.get(domain)
            has_data = any(code.domain is domain for code in measured)
            # Sin lecturas, "nominal" solo significa que no hay nada que mirar: no se afirma.
            # Si el motor sí encontró algo sin ellas (un evento solar sobre la radiación), su
            # nivel se respeta.
            level = (
                risk.level
                if risk is not None and (has_data or risk.level is not RiskLevel.NOMINAL)
                else None
            )
            if level is not None:
                valued.append(level)
            entries.append({
                "domain": str(domain),
                "level": str(level) if level is not None else None,
                "has_data": has_data,
                "drivers": list(risk.drivers) if risk is not None else [],
                # El paso RIESGO (KB §11.1): RIDGE y riesgo del HRP del dominio, los de `/risks`.
                "risk": risk_entity.summary(domain),
            })
        worst = max(valued, key=_LEVEL_ORDER.index, default=None)
        proposed = [item for item in recommendations if item.domain in region.domains]
        variables = [
            _variable(
                latest[code.key], counted.get(code.key), trends.get(code.key),
                counted_as_dose=dose_counted and code.key == CUMULATIVE_DOSE,
                counted_type=counted_types.get(code.key),
            )
            for code in measured
        ]
        home = HOME_REGIONS.get(region.key)
        regions.append({
            **region.to_dict(),
            **region.function_dict(),
            "level": str(worst) if worst is not None else None,
            "has_data": bool(measured),
            "data_note": None if measured else i18n.loc(NO_DATA_NOTE),
            "state": entries,
            # Las que mueven el nivel, primero; dentro de cada grupo, el orden del catálogo.
            "variables": sorted(variables, key=lambda item: not item["contributes"]),
            "unmeasured": [
                {
                    "key": code.key, "display": code.display,
                    "display_es": code.display_es, "domain": str(code.domain),
                }
                for code in codes if code.key not in latest
            ],
            # Cada referencia con su nivel de evidencia y su alcance tal como los declara
            # `evidence/links.py`: un estudio en ratón sigue diciendo que es de ratón.
            "evidence": [
                {
                    "domain": str(domain),
                    "amcl_alignment": amcl_alignment(domain),
                    "items": [item.to_dict() for item in evidence_for(domain)],
                }
                for domain in region.domains
            ],
            # Las recomendaciones del advisor para estos dominios, cada una con su contramedida.
            "recommendations": [item.to_dict() for item in proposed],
            "recommendations_note": (
                i18n.loc(LEVEL_ELSEWHERE_RECOMMENDATIONS_NOTE).format(
                    domain=i18n.loc(region.level_of.display), region=i18n.loc(home.display)
                )
                if region.level_of is not None and home is not None
                else None if proposed
                else i18n.loc(NOTHING_TO_ASSESS_NOTE) if not valued
                else i18n.loc(NO_FINDINGS_NOTE)
                if all(level is RiskLevel.NOMINAL for level in valued)
                else i18n.loc(NO_LIBRARY_ENTRY_NOTE)
            ),
            # Lo de fuera del cuerpo que solapa en el tiempo (hábitat, eventos, sistemas,
            # ejercicio): el contexto de una alerta, rotulado «correlación temporal, no causa».
            "context": context_of(region),
            # (De dónde sale la lista de analitos de una región sin nivel propio, `analytes_source`,
            # llega con `region.to_dict()`, arriba.)
            # La capa aparte de evidencia de investigación (hígado, cerebro, músculo y sistema
            # inmune); `None` en las demás. Va en su clave, fuera de `evidence`: no es evidencia
            # del dominio ni mueve nada.
            "research": region.research_dict(),
            # El paso RIESGO de una región sin nivel propio: el del dominio de su nivel, que es
            # donde cuentan sus analitos (los mismos campos que `/risks`); `None` en las demás.
            "level_risk": (
                risk_entity.summary(region.level_of) if region.level_of is not None else None
            ),
        })
    return regions


# --------------------------------------------------------------------------- #
# Momentos de la misión (conversación de ideación: «Pre-flight → … → Recovery»)
# --------------------------------------------------------------------------- #
#
# Qué instantes ofrecer al recorrer la cadena en el tiempo. No se inventa ninguno: los cambios de
# fase son los límites del calendario de misión (diseño EMMA, `core/mission.py`), el regreso es
# el de la recuperación (`recovery.flight`, el mismo que usa la crónica) y los días posvuelo con
# lecturas, con el R+ que les da la recuperación, se agrupan en hitos. El estado en cada uno se
# recalcula ahora con las reglas de hoy: no es lo que el sistema enseñó entonces, y no se firma.
#
# HITOS POSVUELO (decimoquinta ronda, 2026-10-22). Hasta entonces cada día posvuelo con lecturas
# era su propio momento, sin tope: con una recuperación larga y diaria el selector crecía un botón
# por día. El usuario decidió agruparlos en hitos. Los cuatro primeros son los de una fuente leída,
# Spaceflight Standard Measures de la NASA (Hardy et al. 2025): «After flight, data is collected
# on the day of return at the landing site, and then one day, one week, and one month later»; EMMA
# lee «una semana» y «un mes» como R+7 y R+30. Los tres siguientes los propone la conversación de
# ideación (R+90, R+180, R+365) y son de diseño de EMMA, sin fuente. Cada hito junta los días
# desde el anterior (R+7: de R+2 a R+7) y su instante es la última lectura de ese tramo anterior a
# la de ahora; lo posterior a R+365 va junto en un último tramo, sin hito propio.
#
# HITOS CON SU FICHA (decimosexta ronda, 2026-10-23). R+180 y R+365 tienen fuente: el resumen
# técnico de NASA sobre la pérdida ósea (OCHMO-MTB-013, página 20) hace la densitometría (DXA)
# posvuelo «at 6 months, one year, two years, and 3 years post-flight»; EMMA lee «6 months» y «one
# year» como R+180 y R+365. Esa fuente es solo del hueso, y cada hito lo dice. Las tablas
# suplementarias de Standard Measures, leídas, dan sus tomas posvuelo hasta R+30 con su margen y
# ninguna después: R+90 no lo da ninguna fuente leída y sigue siendo de diseño. El prevuelo gana
# tres hitos L-: L-180 y L-90, las tomas prevuelo de Standard Measures («6 months and 3 months
# before flight»; sus tablas, L-180±45 y L-90±30), y L-30, la densitometría prevuelo del calendario
# de ejemplo de OCHMO-MTB-013 («L- 180/30 d (as close to launch as feasible)»), también solo del
# hueso. Esa cadena no dice si son dos tomas o una ventana: leerla como una toma en L-30, la más
# cercana al lanzamiento, es de EMMA, y la base lo dice.
#
# DOS Y TRES AÑOS (decimoséptima ronda, 2026-10-26). La misma frase de OCHMO-MTB-013 sigue: «two
# years, and 3 years post-flight». Se dejaron fuera porque la conversación de ideación acababa la
# cadena en R+365; un hito con fuente leída que el selector no ofrece deja sin momento propio dos
# densitometrías que la fuente da. Entran R+730 y R+1095 (leer «two years» y «3 years» así es de
# EMMA), solo del hueso como los otros dos, con la misma regla de tramos: lo posterior a R+1095 va
# junto. La frase sigue con «or until recovered within least significant change of pre-flight»:
# que se hagan todas depende de la recuperación de cada uno, y la base lo dice.


@dataclass(frozen=True, slots=True)
class MilestoneSource:
    """Unos hitos y la ficha leída de la que salen, con lo que esa ficha cubre (`scope`).

    `scope` existe para que nadie lea el calendario de un estudio o de una prueba como el de todos
    los indicadores: lo dice la propia respuesta, junto a la ficha.
    """

    days: tuple[int, ...]
    citation: Citation
    scope: str

    def to_dict(self) -> dict[str, Any]:
        """Los hitos con su ficha y su alcance, en el idioma de la petición."""
        found = self._fields()
        return {
            **found,
            "source": _cited(found["source"]),
            "scope": i18n.loc(found["scope"]),
        }

    def _fields(self) -> dict[str, Any]:
        # La ficha por su identificador, título y enlace: la nota entera, con su bitácora de
        # lectura, la sirve el registro, y repetirla en cada momento pedido no añade nada.
        source = {
            "id": self.citation.id, "title": self.citation.title, "url": self.citation.url,
            "relevance": self.citation.relevance,
        }
        return {"days": list(self.days), "source": source, "scope": self.scope}


def _join_milestones(
    read: Sequence[int], design: Sequence[int], *, reverse: bool = False
) -> tuple[int, ...]:
    """Los hitos de un lado, los leídos y los de diseño juntos, sin repetir y en orden.

    Un día puede salir de dos fuentes leídas, cada una con su alcance (el reacondicionamiento de
    OCHMO-MTB-013 también prueba en R+7 y R+30, por ejemplo), y sale una vez. Un día leído y de
    diseño a la vez se rechaza al importar: la respuesta diría de él que tiene fuente y que no la
    tiene.
    """
    both = set(read) & set(design)
    if both:
        raise ValueError(f"hitos leídos y de diseño a la vez: {sorted(both)}")
    return tuple(sorted({*read, *design}, reverse=reverse))


STANDARD_MEASURES_SOURCE = registry.cite(
    "hardy-2025-spaceflight-standard-measures",
    "cuándo toma NASA las medidas de Spaceflight Standard Measures antes y después del vuelo",
)
BONE_DXA_SOURCE = registry.cite(
    "ochmo-mtb-013", "cuándo hace NASA la densitometría ósea (DXA) antes y después del vuelo"
)
STANDARD_MEASURES_SCOPE = (
    "El calendario de Spaceflight Standard Measures, no el de todos los indicadores: cada medida "
    "tiene sus sesiones y sus márgenes."
)
BONE_DXA_SCOPE = (
    "Solo del hueso: son tomas de densitometría (DXA), no un calendario de todos los indicadores."
)

# Un segundo antes del límite: el estado al acabar una fase, sin las lecturas de la siguiente.
_BEFORE = dt.timedelta(seconds=1)

MOMENTS_BASIS = (
    "Cambios de fase del calendario de misión (sus límites son diseño de EMMA, sin fuente), el "
    "regreso y los días prevuelo y posvuelo con lecturas, agrupados en hitos L- y R+ (el R+ de la "
    "recuperación posvuelo). En cada momento el estado se recalcula con las lecturas registradas "
    "hasta ese instante."
)
# Los hitos posvuelo, en días tras el regreso, y de dónde sale cada uno.
POSTFLIGHT_SOURCES: tuple[MilestoneSource, ...] = (
    MilestoneSource((0, 1, 7, 30), STANDARD_MEASURES_SOURCE, STANDARD_MEASURES_SCOPE),
    MilestoneSource((180, 365, 730, 1095), BONE_DXA_SOURCE, BONE_DXA_SCOPE),
)
READ_MILESTONES: tuple[int, ...] = tuple(
    sorted({day for item in POSTFLIGHT_SOURCES for day in item.days})
)
DESIGN_MILESTONES: tuple[int, ...] = (90,)
POSTFLIGHT_MILESTONES: tuple[int, ...] = _join_milestones(READ_MILESTONES, DESIGN_MILESTONES)
MILESTONES_BASIS = (
    "Hitos posvuelo: R+0, R+1, R+7 y R+30 son las tomas posvuelo de Spaceflight Standard Measures "
    "de la NASA (el día del regreso y uno, siete y treinta días después; la fuente dice «una "
    "semana» y «un mes»), que es el calendario de ese estudio y no el de todos los indicadores. "
    "R+180, R+365, R+730 y R+1095 son las densitometrías posvuelo del resumen técnico de NASA "
    "sobre la pérdida ósea, a los 6 meses y a uno, dos y tres años del regreso, o hasta que el "
    "hueso se recupera: esa fuente es solo del hueso. R+90 es de diseño de EMMA, sin fuente. Cada "
    "hito junta los días desde el anterior y se pide en la última lectura de ese tramo; lo "
    "posterior a R+1095 va junto."
)
# Los hitos prevuelo, en días antes del lanzamiento (de más lejos a más cerca), y de dónde salen.
PREFLIGHT_SOURCES: tuple[MilestoneSource, ...] = (
    MilestoneSource((180, 90), STANDARD_MEASURES_SOURCE, STANDARD_MEASURES_SCOPE),
    MilestoneSource((30,), BONE_DXA_SOURCE, BONE_DXA_SCOPE),
)
PREFLIGHT_READ_MILESTONES: tuple[int, ...] = tuple(
    sorted({day for item in PREFLIGHT_SOURCES for day in item.days}, reverse=True)
)
# Hoy ninguno: si uno sin fuente entrara, se declara aquí y no entre los leídos.
PREFLIGHT_DESIGN_MILESTONES: tuple[int, ...] = ()
PREFLIGHT_MILESTONES: tuple[int, ...] = _join_milestones(
    PREFLIGHT_READ_MILESTONES, PREFLIGHT_DESIGN_MILESTONES, reverse=True
)
PREFLIGHT_MILESTONES_BASIS = (
    "Hitos prevuelo: L-180 y L-90 son las tomas prevuelo de Spaceflight Standard Measures de la "
    "NASA (6 y 3 meses antes del vuelo), que es el calendario de ese estudio y no el de todos los "
    "indicadores. L-30 es la densitometría prevuelo del calendario de ejemplo del resumen técnico "
    "de NASA sobre la pérdida ósea, para una misión de 180 días en la ISS; la fuente escribe "
    "«L- 180/30 d», tan cerca del lanzamiento como se pueda, y leerlo como una toma en L-30 es de "
    "EMMA. Esa fuente es solo del hueso. Cada hito junta los días desde el anterior y se pide en "
    "la última lectura de ese tramo; lo posterior a L-30 es el momento del lanzamiento."
)
# Los hechos de la crónica que son tomas posvuelo (`timeline._recovery_events`).
POSTFLIGHT_FACTS = frozenset({"postflight-sample", "postflight-day"})
# Los momentos que acaban un segundo antes de un cambio de fase: ni un hito prevuelo ni uno
# posvuelo, que caen en una lectura y podrían coincidir por azar con un cambio de fase.
PHASE_KINDS = frozenset({"phase_change", "landing"})
CURRENT_MOMENT = "Ahora: última lectura registrada"
# El rótulo de un estado pedido en un momento pasado: el de la historia de alertas, y que no
# queda asiento de él.
MOMENT_LABEL = f"{alert_history.LABEL}, sin asiento"
# Lo que el corte `until` no alcanza: las lecturas y la dosis registrada se cortan en ese instante,
# pero los eventos solares y el tiempo de luz son los que el estado tiene hoy (los mismos que usa
# `/status` con `until`). Se dice, como lo dice la historia de alertas de lo suyo.
MOMENT_EXTERNAL_BASIS = (
    "El contexto externo no es el de entonces: las lecturas, también la radiación acumulada "
    "registrada, llegan hasta ese instante, pero los eventos solares y el tiempo de luz con que "
    "se evalúa son los que el sistema tiene hoy."
)


def _day(value: float) -> str:
    return number_display.number(value, 0)


def postflight_milestone(day: int) -> int | None:
    """El hito de un día posvuelo: el primero que no queda antes de él (R+3 → R+7); `None`
    después del último, en el tramo que va junto."""
    return next((milestone for milestone in POSTFLIGHT_MILESTONES if day <= milestone), None)


def _milestone_display(milestone: int | None, day: int) -> str:
    """Qué es el momento de un hito: el día de su lectura, y el tramo si no es el del hito."""
    if milestone is None:
        return i18n.tr(
            f"Después de R+{POSTFLIGHT_MILESTONES[-1]}: última lectura, en R+{day}",
            f"After R+{POSTFLIGHT_MILESTONES[-1]}: last reading, at R+{day}",
        )
    if day == milestone:
        return i18n.tr(
            f"R+{milestone}: última lectura de ese día", f"R+{milestone}: last reading of that day"
        )
    earlier = [item for item in POSTFLIGHT_MILESTONES if item < milestone]
    return i18n.tr(
        f"Tramo de R+{earlier[-1] + 1} a R+{milestone}: última lectura, en R+{day}",
        f"Span from R+{earlier[-1] + 1} to R+{milestone}: last reading, at R+{day}",
    )


def days_before_launch(moment: dt.datetime, launch: dt.datetime) -> int:
    """El L- de un instante prevuelo: días hasta el lanzamiento, con la regla del R+
    (`recovery.days_after_landing`) al revés; con dos reglas, el espejo dejaría de serlo."""
    return days_after_landing(launch, moment)


def _segments(
    days: Mapping[int, dt.datetime], milestone_of: Callable[[int], int | None],
    cutoff: dt.datetime,
) -> dict[int | None, tuple[int, dt.datetime]]:
    """Cada tramo de hitos, en el último de sus días con lecturas anterior a `cutoff`.

    Una sola regla para el prevuelo y el posvuelo. `days` es la última lectura de cada día y
    `cutoff` el instante cuyo estado ya se ofrece de otro modo: en posvuelo, la última lectura (el
    estado de ahora); en prevuelo, la última lectura prevuelo (el estado del lanzamiento). El tramo
    de ese instante se pide en el día de antes que tenga lecturas. La clave del momento es la de
    ese día (R+2 en el tramo de R+7), no la del hito: mientras el tramo está abierto su día cambia
    al llegar lecturas, y un momento elegido con la clave del hito saltaría solo a otro instante;
    con la del día, deja de ofrecerse y se vuelve a ahora.
    """
    segments: dict[int | None, tuple[int, dt.datetime]] = {}
    for day, instant in days.items():
        milestone = milestone_of(day)
        held = segments.get(milestone)
        if instant < cutoff and (held is None or instant > held[1]):
            segments[milestone] = (day, instant)
    return segments


def preflight_milestone(day: int) -> int | None:
    """El hito de un día prevuelo (días antes del lanzamiento): el primero que no queda antes de
    él (L-120 → L-90); `None` después del último, L-30, en el tramo que llega al lanzamiento."""
    return next((milestone for milestone in PREFLIGHT_MILESTONES if day >= milestone), None)


def _preflight_display(milestone: int, day: int) -> str:
    """Qué es el momento de un hito prevuelo: el día de su lectura, y su tramo si no es el del
    hito."""
    if day == milestone:
        return i18n.tr(
            f"L-{milestone}: última lectura de ese día", f"L-{milestone}: last reading of that day"
        )
    earlier = [item for item in PREFLIGHT_MILESTONES if item > milestone]
    if not earlier:
        return i18n.tr(
            f"Hasta L-{milestone}: última lectura, en L-{day}",
            f"Up to L-{milestone}: last reading, at L-{day}",
        )
    return i18n.tr(
        f"Tramo de L-{earlier[-1] - 1} a L-{milestone}: última lectura, en L-{day}",
        f"Span from L-{earlier[-1] - 1} to L-{milestone}: last reading, at L-{day}",
    )


def _preflight_moments(
    observations: Sequence[VitalObservation], launch: dt.datetime
) -> list[tuple[str, str, str, dt.datetime, int | None, int | None]]:
    """Un momento por tramo prevuelo, con la regla de los tramos posvuelo (`_segments`).

    Lo posterior a L-30 es el momento del lanzamiento («Fin del prevuelo»), que ya se ofrece. La
    última lectura prevuelo tampoco se ofrece como hito: su estado es el de ese mismo momento (o
    el de ahora, si no hay nada después), y serían dos botones para lo mismo; su tramo se pide en
    el día de antes con lecturas, como el tramo abierto del posvuelo.
    """
    preflight: dict[int, dt.datetime] = {}
    for item in observations:
        if item.effective < launch:
            day = days_before_launch(item.effective, launch)
            preflight[day] = max(preflight.get(day, item.effective), item.effective)
    if not preflight:
        return []
    segments = _segments(preflight, preflight_milestone, max(preflight.values()))
    return [
        (f"L-{day}", "preflight_milestone", _preflight_display(milestone, day), instant, None, day)
        for milestone, (day, instant) in segments.items()
        if milestone is not None
    ]


def moments(
    observations: Sequence[VitalObservation], mission_start: dt.date, mission_days: int
) -> dict[str, Any]:
    """Los momentos anteriores a la última lectura en que se puede pedir el estado (`until`).

    Solo los que tienen alguna lectura antes y alguna después: sin lecturas antes no hay estado
    (404), y sin lecturas después el estado es el de ahora. Un hito posvuelo lleva además el R+
    de su lectura (`days_after_landing`), y un hito prevuelo el L- (`days_before_launch`); la
    clave de los dos es la de ese día.
    """
    items: list[dict[str, Any]] = []
    if observations:
        first = min(item.effective for item in observations)
        last = max(item.effective for item in observations)
        launch, landing, real = flight(observations, mission_start, mission_days)
        found: list[tuple[str, str, str, dt.datetime, int | None, int | None]] = [
            *_preflight_moments(observations, launch),
            (
                "preflight", "phase_change",
                i18n.tr("Fin del prevuelo: lanzamiento", "End of preflight: launch"),
                launch - _BEFORE, None, None,
            ),
        ]
        for day in sorted({ADAPTATION_DAYS, mission_days - RETURN_DAYS}):
            boundary = launch + dt.timedelta(days=day)
            before = phase_at(boundary - _BEFORE, mission_start, mission_days)
            after = phase_at(boundary, mission_start, mission_days)
            # Con una misión muy corta dos límites caen en la misma fase; con un vuelo real
            # reproducido, el calendario configurado puede quedar después de su regreso.
            if before is not after and boundary < landing:
                found.append((
                    f"phase-{after}", "phase_change",
                    i18n.tr(
                        f"Cambio de fase: de {before.display} a {after.display} (día {_day(day)})",
                        f"Phase change: from {i18n.loc(before.display)} to "
                        f"{i18n.loc(after.display)} (day {_day(day)})",
                    ),
                    boundary - _BEFORE, None, None,
                ))
        flown = (landing - launch) / dt.timedelta(days=1)
        found.append((
            "landing", "landing",
            i18n.tr("Regreso del vuelo reproducido", "Return of the replayed flight") if real
            else i18n.tr(f"Regreso (día {_day(flown)})", f"Return (day {_day(flown)})"),
            landing - _BEFORE, None, None,
        ))
        # La última lectura de cada día posvuelo, con su R+.
        postflight: dict[int, dt.datetime] = {}
        for item in observations:
            if item.effective >= landing:
                day = days_after_landing(item.effective, landing)
                postflight[day] = max(postflight.get(day, item.effective), item.effective)
        # Cada tramo, en el último de sus días anterior al de ahora: el día de la última lectura
        # es el estado de ahora, y su tramo se pide en el día de antes que tenga lecturas.
        segments = _segments(postflight, postflight_milestone, last)
        found.extend(
            (
                f"R+{day}", "postflight_milestone", _milestone_display(milestone, day), instant,
                day, None,
            )
            for milestone, (day, instant) in segments.items()
        )
        items = [
            {
                "key": key, "kind": kind, "display": text, "until": instant.isoformat(),
                "days_after_landing": after, "days_before_launch": before,
            }
            for key, kind, text, instant, after, before in sorted(found, key=lambda entry: entry[3])
            if first <= instant < last
        ]
    return {
        "current_display": i18n.loc(CURRENT_MOMENT),
        "items": items,
        "basis": i18n.loc(MOMENTS_BASIS),
        "postflight_milestones": {
            "read": list(READ_MILESTONES),
            "design": list(DESIGN_MILESTONES),
            "sources": [item.to_dict() for item in POSTFLIGHT_SOURCES],
            "basis": i18n.loc(MILESTONES_BASIS),
        },
        "preflight_milestones": {
            "read": list(PREFLIGHT_READ_MILESTONES),
            "design": list(PREFLIGHT_DESIGN_MILESTONES),
            "sources": [item.to_dict() for item in PREFLIGHT_SOURCES],
            "basis": i18n.loc(PREFLIGHT_MILESTONES_BASIS),
        },
    }


def chronicle_moment(
    event: Mapping[str, Any], moments: Mapping[str, Any] | None
) -> dict[str, str] | None:
    """El momento de `moments` que es un hecho de la crónica, o `None` si no lo es.

    Pulsar un hito de la crónica elige ese momento en «Cuerpo»; qué hecho es qué momento se
    decide aquí, junto a los momentos, y no en la interfaz. Por instantes, no por días ni por
    claves: la crónica cuenta el posvuelo con todas las lecturas y los momentos con las que
    analiza el estado, y un R+ o un regreso calculados por separado podrían no coincidir.

    - Un cambio de fase es el momento que acaba un segundo antes de él: el estado al cerrar la
      fase de antes (con el calendario, el regreso es el cambio a posvuelo). Con un vuelo
      reproducido, el cambio a posvuelo del calendario no es su regreso y no enlaza: por eso se
      compara el instante y no el nombre de la fase.
    - Un hecho posvuelo es el primer hito que ya lo cuenta: el de instante más temprano que no
      queda antes de él. Si ninguno lo cuenta (es de hoy), no enlaza.
    """
    if moments is None:
        return None
    at = dt.datetime.fromisoformat(event["at"])
    items: list[dict[str, Any]] = moments["items"]
    found: dict[str, Any] | None = None
    if event.get("fact") == "phase-change":
        found = next(
            (item for item in items
             if item["kind"] in PHASE_KINDS
             and dt.datetime.fromisoformat(item["until"]) + _BEFORE == at),
            None,
        )
    elif event.get("fact") in POSTFLIGHT_FACTS:
        found = min(
            (item for item in items
             if item["kind"] == "postflight_milestone"
             and dt.datetime.fromisoformat(item["until"]) >= at),
            key=lambda item: dt.datetime.fromisoformat(item["until"]),
            default=None,
        )
    return None if found is None else {"key": found["key"], "display": found["display"]}


def moment(until: dt.datetime | None) -> dict[str, Any] | None:
    """Qué es el estado pedido en un momento pasado; `None` si es el de ahora."""
    if until is None:
        return None
    found: dict[str, Any] = {
        "until": until.isoformat(),
        "label": MOMENT_LABEL,
        "basis": [
            alert_history.RECOMPUTED_BASIS, MOMENT_EXTERNAL_BASIS, alert_history.NOT_STORED,
        ],
    }
    # Las dos frases de la historia de alertas salen en inglés cuando su módulo lo registre.
    return {
        **found,
        "label": i18n.loc(found["label"]),
        "basis": [i18n.loc(item) for item in found["basis"]],
    }


# Esqueleto de referencia para la región "bones": render anterior y centroide de cada hueso, de
# BodyParts3D (CC BY 4.0, DBCLS) con `esqueleto_referencia.py` de Polaris (data/anatomy/
# ATRIBUCION.txt). Es una figura de referencia, no el cuerpo del tripulante: los puntos dicen
# dónde está cada hueso, no qué le pasa.
SKELETON_DIR = Path(__file__).resolve().parent / "data" / "anatomy"
SKELETON_ATTRIBUTION = (
    "BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 "
    "International"
)



# QUÉ ESQUELETO SE ESTÁ VIENDO LO DICE LA RESPUESTA, CON SUS PALABRAS.
#
# Desde el 2026-10-07 la figura puede salir del TAC que el tripulante tiene en su registro
# (`volumes/skeleton_view.py`). Las dos figuras tienen el mismo contrato y se parecen: si la
# interfaz tuviera que adivinar cuál pinta, o redactar ella el rótulo, un cuerpo ajeno pasaría
# por el propio (o al revés). `source` lo dice, y `label`, `alt`, `caption` y las notas son el
# texto que se enseña, tal cual.
# (`REFERENCE` y `OWN_CT` son los de `pain_on_skeleton`, que es quien los compara: una sola copia.)
# Por qué se ve la de referencia cuando se pidió la de un tripulante: no tiene esqueleto propio
# (dato ausente) o lo tiene y no se puede usar (no disponible). La interfaz les pone el color de
# la tabla F.5-1 de NASA-STD-3001; el texto es `fallback_reason`.
NO_OWN = "no-segmentation"
OWN_UNUSABLE = "not-usable"
REFERENCE_LABEL = "Esqueleto de referencia (BodyParts3D): no es el cuerpo del tripulante."
REFERENCE_ALT = (
    "Esqueleto humano de referencia, vista anterior: la izquierda del sujeto queda a la derecha "
    "de la imagen"
)
REFERENCE_CAPTION = "Figura de referencia, no del tripulante. {attribution}."
NO_SEGMENTATION = (
    "Este tripulante no tiene una segmentación del esqueleto vigente: se enseña el esqueleto de "
    "referencia."
)
NOT_USABLE = (
    "La segmentación del esqueleto de este tripulante (asiento {index} del ledger) no se usa: "
    "{reason}. Se enseña el esqueleto de referencia."
)
UNREADABLE_RECORD = (
    "No se pudo leer el registro de volúmenes de este tripulante ({reason}). Se enseña el "
    "esqueleto de referencia."
)
SkeletonUnavailable = skeleton_view.Unavailable
OWN_LABEL = (
    "Esqueleto del TAC de este tripulante: estudio registrado el {study_date} (asiento "
    "{study_index} del ledger), segmentación del {date} (asiento {index})."
)
# Los TAC de ejemplo son pacientes de un dataset abierto, firmados como simulados
# (`api/volumes.create_sample`): están en el registro del tripulante, pero no son su cuerpo.
SAMPLE_LABEL = (
    "Esqueleto del TAC de ejemplo registrado a este tripulante el {study_date} (asiento "
    "{study_index} del ledger; segmentación del {date}, asiento {index}): es un paciente de un "
    "dataset abierto, firmado como dato simulado, no el cuerpo del tripulante."
)
OWN_ALT = (
    "Esqueleto segmentado de un TAC, vista anterior: la izquierda del sujeto queda a la derecha "
    "de la imagen"
)
OWN_CAPTION = (
    "{status}. Imagen de referencia previa al vuelo o de Tierra: dice dónde está cada hueso "
    "segmentado, no qué le pasa, y no es un diagnóstico a bordo."
)
ABSENT_NOTE = (
    "Huesos sin vóxeles en esta segmentación: no se dibujan. Puede ser que el estudio no los "
    "cubra o que el modelo no los encontrara."
)
TRUNCATED_NOTE = (
    "Huesos que llegan al borde del estudio: el punto marca el centro del trozo que entra en el "
    "TAC, no el del hueso."
)
TRUNCATION_UNKNOWN_NOTE = (
    "No se pudo medir qué huesos corta el borde del estudio: algún punto puede marcar el centro "
    "de un trozo y no el del hueso."
)


# Con el idioma en la clave: el nombre de cada hueso lo da `volumes/assets.py`, que es de otro
# módulo; si un día lo dice en el idioma de la petición, aquí no se queda el del primero que pasó.
@i18n.lang_cache
def _reference() -> dict[str, Any]:
    data = json.loads((SKELETON_DIR / "esqueleto.json").read_text(encoding="utf-8"))
    width, height = data["tamano"]
    return {
        "region": "bones",
        "width": int(width),
        "height": int(height),
        "bones": {
            name: {
                "u": float(point["u"]), "v": float(point["v"]),
                "display": volume_assets.bone_display(name), "truncated": False,
            }
            for name, point in sorted(data["huesos"].items())
        },
        "attribution": SKELETON_ATTRIBUTION,
        "source": REFERENCE,
        "label": REFERENCE_LABEL,
        "alt": REFERENCE_ALT,
        "caption": REFERENCE_CAPTION.format(attribution=SKELETON_ATTRIBUTION),
        "simulated": False,
        "ledger": None,
        "extent_mm": None,
        "absent_bones": [],
        "truncated_bones": [],
        "notes": [],
        "spine": None,
        "fallback_reason": None,
        "fallback_kind": None,
    }


def skeleton() -> dict[str, Any]:
    """El esqueleto de REFERENCIA: tamaño de la imagen y {hueso: {u, v}} (fracciones de ancho y
    alto; izquierda del sujeto a la derecha de la imagen, vista anterior)."""
    found = copy.deepcopy(_reference())
    for field in ("label", "alt", "caption"):
        found[field] = i18n.loc(found[field])
    return found


def skeleton_png() -> bytes:
    return (SKELETON_DIR / "esqueleto-anterior.png").read_bytes()


def _named(names: Sequence[str]) -> list[dict[str, str]]:
    return [{"name": name, "display": volume_assets.bone_display(name)} for name in names]


def subject_skeleton(store: ObservationStore, subject: str) -> dict[str, Any]:
    """El esqueleto que se enseña de un tripulante: el de su TAC si tiene una segmentación del
    esqueleto vigente y vale; si no, el de referencia, diciendo por qué. Mismo contrato."""
    try:
        found = skeleton_view.current(store, subject)
    except SkeletonUnavailable as failed:
        index = failed.segmentation_index
        return {
            **skeleton(),
            # El motivo lo redacta `volumes/skeleton_view.py`: sale en inglés cuando lo registre.
            "fallback_reason": (
                i18n.loc(UNREADABLE_RECORD).format(reason=i18n.loc(failed.reason))
                if index is None
                else i18n.loc(NOT_USABLE).format(index=index, reason=i18n.loc(failed.reason))
            ),
            "fallback_kind": OWN_UNUSABLE,
        }
    if found is None:
        return {
            **skeleton(), "fallback_reason": i18n.loc(NO_SEGMENTATION), "fallback_kind": NO_OWN,
        }
    view, segmentation, study = found.view, found.segmentation, found.study
    simulated = str(study.get("source", "")).startswith("simulator")
    dataset = study.get("dataset") if isinstance(study.get("dataset"), dict) else None
    ledger: dict[str, Any] = {
        "segmentation_index": int(segmentation["ledger_index"]),
        "segmentation_recorded": str(segmentation["recorded"]),
        "study_index": int(study["ledger_index"]),
        "study_recorded": str(study["recorded"]),
    }
    notes = []
    if view.absent:
        notes.append(i18n.loc(ABSENT_NOTE))
    if view.truncated:
        notes.append(i18n.loc(TRUNCATED_NOTE))
    if not view.truncation_checked:
        notes.append(i18n.loc(TRUNCATION_UNKNOWN_NOTE))
    # El estado es el que firmó la segmentación (castellano): en inglés, si su módulo lo registra.
    status = i18n.loc(str(segmentation.get("estado") or volume_assets.UNVALIDATED))
    return {
        "region": "bones",
        "width": view.width,
        "height": view.height,
        "bones": {
            name: {
                **point, "display": volume_assets.bone_display(name),
                "truncated": name in view.truncated,
            }
            for name, point in view.bones.items()
        },
        # CC BY: la figura derivada de un TAC de un dataset lleva su cita al lado.
        "attribution": (
            f"{dataset.get('citation', dataset.get('name', ''))} ({dataset.get('license', '')})"
            if dataset else None
        ),
        "source": OWN_CT,
        "label": i18n.loc(SAMPLE_LABEL if simulated else OWN_LABEL).format(
            study_date=ledger["study_recorded"][:10], study_index=ledger["study_index"],
            date=ledger["segmentation_recorded"][:10], index=ledger["segmentation_index"],
        ),
        "alt": i18n.loc(OWN_ALT),
        "caption": i18n.loc(OWN_CAPTION).format(status=status[:1].upper() + status[1:]),
        "simulated": simulated,
        "ledger": ledger,
        "extent_mm": view.extent_mm,
        "absent_bones": _named(view.absent),
        "truncated_bones": _named(view.truncated),
        "notes": notes,
        # El control de la cadena vertebral de `volumes/spine.py`, con su aviso ya redactado.
        # Un bloque firmado por una versión anterior puede no traer listas: nunca viaja un nulo.
        "spine": {
            "nivel": view.spine.get("nivel"),
            "aviso": view.spine.get("aviso"),
            "listas": view.spine.get("listas") or [],
        },
        "fallback_reason": None,
        "fallback_kind": None,
    }


def subject_skeleton_png(store: ObservationStore, ledger_index: int) -> bytes:
    """La imagen de la figura de una segmentación; `skeleton_view.Unavailable` si no la hay."""
    return skeleton_view.view_of(store, ledger_index).png


# --------------------------------------------------------------------------- #
# El inglés de lo que este módulo sirve (2026-11-15, dos idiomas con selector)
# --------------------------------------------------------------------------- #
#
# Cada frase castellana de arriba se queda donde está, con sus bytes: las fijan las pruebas y las
# campañas de mutantes. Su inglés va aquí, emparejado por la constante y no por una copia del
# texto, y se registra una vez; quien sirve la frase la pide con `i18n.loc`. Dice lo mismo que el
# castellano y nada más: las mismas salvedades, las mismas poblaciones, las mismas fuentes. Las
# citas literales de una fuente («…») se quedan en el idioma de la fuente.


def _relevance(citation: Citation) -> str:
    if citation.relevance is None:
        raise ValueError(f"{citation.id}: una cita sin relevancia no tiene inglés que registrar")
    return citation.relevance


# Nombre y frase de cada región, por su clave: una región nueva sin inglés no arranca.
REGIONS_ENGLISH: dict[str, tuple[str, str]] = {
    "brain": (
        "Brain: sleep, vigilance, mood",
        "The behavioral domain: sleep, circadian rhythm, PVT and self-reported mood.",
    ),
    "eyes": (
        "Eyes and optic nerve",
        "Spaceflight-associated neuro-ocular syndrome (SANS), by ultrasound of the optic nerve "
        "sheath.",
    ),
    "heart": (
        "Heart and circulation",
        "Pulse, variability, blood pressure and orthostatic response.",
    ),
    "lungs": (
        "Lungs",
        "Not an EMMA domain: respiratory rate and oxygen saturation count in the cardiovascular "
        "domain. They are the lung indicators according to the NHLBI: rapid breathing and blood "
        "oxygen.",
    ),
    "bones": (
        "Weight-bearing bones",
        "Resorption markers, impact loading and exercise; density is only inferred.",
    ),
    "muscles": (
        "Back and musculoskeletal",
        "Self-reported pain on the body map.",
    ),
    "bladder": (
        "Kidneys, bladder and urinary tract",
        "Urinary retention by ultrasound; fluid intake and urine against the risk of stones.",
    ),
    "digestive": (
        "Digestive system: nutrition",
        "Actual intake and food acceptability.",
    ),
    "liver": (
        "Liver",
        "Not an EMMA domain: its analytes count in the nutrition domain. They are those of the "
        "most common liver function tests according to MedlinePlus.",
    ),
    "immune": (
        "Immune system (whole body)",
        "Not an organ: cell count, viral reactivation and symptoms.",
    ),
    "whole-body": (
        "Whole body: radiation",
        "Radiation has no organ of its own in EMMA: cumulative dose and solar events.",
    ),
}

ENGLISH: dict[str, str] = {
    **{region.display: REGIONS_ENGLISH[region.key][0] for region in REGIONS},
    **{region.note: REGIONS_ENGLISH[region.key][1] for region in REGIONS},
    LEVEL_OF_NOTE: "The level is that of the {domain} domain.",
    _relevance(LIVER_SOURCE): (
        "which analytes are liver function tests: albumin, total protein, alkaline phosphatase, "
        "ALT, AST, GGT, bilirubin and LDH (and prothrombin time, which EMMA does not have)"
    ),
    RESEARCH_NOTE: (
        "What has been observed in studies with other people or with animals, not measured in "
        "this crew member; each card states its population. It does not claim that this is "
        "happening to them and it does not count toward the level or the alerts."
    ),
    RESEARCH_FACILITY_NOTE: (
        "Where part of that research is done: the card is for a facility, not a study, and it "
        "has no population."
    ),
    _relevance(LIVER_RESEARCH.citation): (
        "a mechanism in mouse liver, not measured in this crew member: miRNA and TGF-β networks "
        "associated with senescence and fibrosis, with simulated microgravity and deep-space "
        "radiation analogs on Earth; the human part of the study is a comparison with blood "
        "transcriptomics from the Twins Study and Inspiration4"
    ),
    LIVER_RESEARCH.population: (
        "humans and animal model: the experiment is in mouse liver, on Earth; the human part is "
        "a comparison with blood transcriptomics from the Twins Study and Inspiration4"
    ),
    _relevance(CNS_RESEARCH.citation): (
        "what is known about space radiation and the central nervous system: neurocognitive "
        "deficits in mice and rats with low exposures to HZE nuclei (10-50 cGy) in beams that "
        "simulate space radiation; in people, what has been seen comes from radiotherapy "
        "patients with much higher exposures, and the report says that the human epidemiology "
        "needed to estimate the risk is lacking and that seeing effects in astronauts of past "
        "missions is very unlikely"
    ),
    CNS_RESEARCH.population: (
        "humans and animal model: the human part is mostly from radiotherapy patients and people "
        "exposed on Earth, and from astronauts, the Apollo light flashes; the animal part, "
        "mostly mice and rats irradiated at accelerators"
    ),
    _relevance(NSRL_FACILITY): (
        "where irradiation is done with heavy-ion beams that simulate cosmic rays: the CNS report "
        "names it as an example of an accelerator, and the laboratory's page describes itself as "
        "«the only place designed and built to study a space radiation environment right here on "
        "Earth's surface»"
    ),
    _relevance(MUSCLE_RESEARCH_REPORT.citation): (
        "what is known about the loss of muscle mass, strength and endurance in flight: on the "
        "ISS strength is measured before and after the mission, and the report, from 2015, "
        "announced that muscle mass would be followed in flight for the first time with "
        "ultrasound (SPRINT study); the only in-flight strength test it describes is an "
        "experiment, the calf dynamometer of STS-78"
    ),
    MUSCLE_RESEARCH_REPORT.population: (
        "humans and animal model: the report brings together flight (from Mercury to the ISS), "
        "analogs on Earth and animal studies; what EMMA read is from ISS crews and from STS-78, "
        "on the Space Shuttle"
    ),
    _relevance(MUSCLE_RESEARCH_BEDREST.citation): (
        "what unloading without flight does to muscle and what a countermeasure changes: "
        "skeletal muscle transcriptome over 60 days of bed rest, with one group on bed rest "
        "only and two with a countermeasure, exercise or nutrition; it is neither flight nor "
        "vital signs"
    ),
    MUSCLE_RESEARCH_BEDREST.population: (
        "humans: 24 healthy young women in the WISE 2005 bed rest study, 60 days on Earth"
    ),
    _relevance(MUSCLE_RESEARCH_MOUSE.citation): (
        "a multi-omics study whose title names mitochondrial stress as a hub of the response to "
        "flight; what is open in OSDR is the gastrocnemius metabolomics of Rodent Research-9, in "
        "mouse; it supports a mechanism, not a threshold nor a measurement on this crew member"
    ),
    MUSCLE_RESEARCH_MOUSE.population: (
        "humans and animal model: the open files are from mouse muscle (gastrocnemius, Rodent "
        "Research-9); the human part, metrics from 59 astronauts and Twins Study data that the "
        "publication analyzes and the files do not publish"
    ),
    _relevance(IMMUNE_RESEARCH_REPORT.citation): (
        "what is known in people and in animals: in postflight tests, markedly depressed T-cell "
        "function after 6 months of flight; in flight, reactivation of latent herpesviruses on "
        "short and long missions, and clinical symptoms on the ISS (cold sores, rashes, atypical "
        "allergies and infections), generally without it being possible to confirm them; in "
        "animals, reduced spleen T-cell and NK-cell function in SLS-2 rats and reduced spleen "
        "mass in mice after 13 days on STS-135"
    ),
    IMMUNE_RESEARCH_REPORT.population: (
        "humans and animal model: Space Shuttle and ISS crew members, in flight and postflight, "
        "and analogs on Earth; rats and mice in flight and on Earth, and cell cultures; what was "
        "read gives no total number of crew members and says that in-flight studies have had few "
        "subjects or short flights"
    ),
    _relevance(IMMUNE_RESEARCH_SPLEEN.citation): (
        "the spleen in mouse after 35 days on the ISS: transcriptome by sequencing "
        "(«transcriptome analysis by next-generation sequencing technology is performed about "
        "spleen»); it supports that flight alters immune function in a mammal, not an immune "
        "signature of this crew member"
    ),
    IMMUNE_RESEARCH_SPLEEN.population: (
        "animal model: mouse; 12 mice flew 35 days on the ISS and the dataset publishes 9 spleen "
        "samples: 3 ground controls, 3 flight with gravity by centrifugation and 3 flight in "
        "microgravity"
    ),
    _relevance(RENAL_STONE_SOURCE): (
        "why fluid intake and urine matter against stones: the report lists relative dehydration "
        "and urine volume among the risk factors, and gives drinking more to increase urine "
        "output as the first prevention measure for every type of stone"
    ),
    _relevance(LUNG_SOURCE): (
        "which indicators are of the lung: rapid breathing and blood oxygen, which the NHLBI "
        "names among what is looked at when the lungs do not carry enough oxygen to the blood"
    ),
    LEVEL_ELSEWHERE_RECOMMENDATIONS_NOTE: (
        "No countermeasures of its own: those of the {domain} domain appear in the region "
        "«{region}»."
    ),
    NO_FUNCTION_NOTE: (
        "It is not an organ or a body system: the region gathers radiation, which reaches the "
        "whole body. There is no function to describe."
    ),
    BRAIN_FUNCTION: (
        "The nervous system, with the brain, is the major controlling, regulatory and "
        "communicating system of the body and the center of mental activity: thought, learning "
        "and memory."
    ),
    _relevance(BRAIN_FUNCTION_SOURCE): (
        "what the nervous system is for: control, regulation and communication of the body, and "
        "mental activity (thought, learning and memory)"
    ),
    EYES_FUNCTION: (
        "The eyes make sight possible: in the retina, cells called photoreceptors turn light "
        "into electrical signals, which travel along the optic nerve to the brain, and the brain "
        "turns them into the images that are seen."
    ),
    _relevance(EYES_FUNCTION_SOURCE): (
        "what the eyes and the optic nerve are for: the retina turns light into electrical "
        "signals and the optic nerve carries them to the brain"
    ),
    HEART_FUNCTION: (
        "The heart is a muscular pump that drives blood through a closed circuit of vessels "
        "(arteries, veins and capillaries); in the capillaries the blood performs its transport "
        "function."
    ),
    _relevance(HEART_FUNCTION_SOURCE): (
        "what the heart and the circulation are for: a muscular pump and a closed circuit of "
        "vessels, and in the capillaries the transport function of the blood"
    ),
    LUNGS_FUNCTION: (
        "The respiratory system, together with the circulatory system, brings the cells the "
        "oxygen they need and removes waste products of metabolism; in the lungs gases are "
        "exchanged with the blood. It also helps regulate the pH of the blood."
    ),
    _relevance(LUNGS_FUNCTION_SOURCE): (
        "what the lungs are for: the supply of oxygen and the removal of metabolic waste, gas "
        "exchange with the blood and the help in regulating its pH"
    ),
    BONES_FUNCTION: (
        "Bones form the skeleton, a rigid framework that supports the body against gravity and "
        "protects the soft organs; with the muscles they act as levers for movement, and blood "
        "cell formation takes place mostly in their red marrow."
    ),
    _relevance(BONES_FUNCTION_SOURCE): (
        "what bones are for: support against gravity, protection, levers of movement with the "
        "muscles and blood cell formation in the red marrow"
    ),
    MUSCLES_FUNCTION: (
        "Muscles, attached to bones, to internal organs and to blood vessels, produce movement "
        "when they contract; their contraction maintains posture, as when sitting or standing, "
        "and their metabolism produces heat that helps maintain body temperature."
    ),
    _relevance(MUSCLES_FUNCTION_SOURCE): (
        "what muscles are for: movement by contraction, posture and heat for body temperature"
    ),
    URINARY_FUNCTION: (
        "The urinary system keeps the volume and composition of body fluids within normal "
        "limits: it regulates how much water is eliminated in urine and rids the body of waste "
        "products of cell metabolism."
    ),
    _relevance(URINARY_FUNCTION_SOURCE): (
        "what the urinary system is for: keeping the volume and composition of body fluids, "
        "regulating the water that leaves in urine and eliminating metabolic waste"
    ),
    DIGESTIVE_FUNCTION: (
        "The digestive system turns food into molecules that the cells can absorb and use: it "
        "takes food in through the mouth, breaks it down mechanically and chemically, moves it "
        "along the digestive tract, absorbs the nutrients and eliminates what cannot be digested "
        "or absorbed."
    ),
    _relevance(DIGESTIVE_FUNCTION_SOURCE): (
        "what the digestive system is for: turning food into molecules that the cells absorb and "
        "use, in the six activities the page names"
    ),
    LIVER_FUNCTION: (
        "The liver has many functions, many of them vital; among them, it makes bile salts and "
        "plasma proteins, stores, detoxifies, takes part in the metabolism of carbohydrates, "
        "fats and proteins, and some of its cells, the Kupffer cells, clean the blood."
    ),
    _relevance(LIVER_FUNCTION_SOURCE): (
        "what the liver is for: the page's list of functions (bile salts, plasma proteins, "
        "storage, detoxification, metabolism) and the cleaning of the blood by the Kupffer cells"
    ),
    IMMUNE_FUNCTION: (
        "It defends the body against invading microorganisms and disease: the lymphatic organs "
        "filter the lymph to remove microorganisms and other foreign particles, and contain "
        "lymphocytes that destroy invading organisms."
    ),
    _relevance(IMMUNE_FUNCTION_SOURCE): (
        "what the body's defense is for: that of the lymphatic system against invading "
        "microorganisms, with the filtering of lymph and the lymphocytes"
    ),
    NO_DATA_NOTE: (
        "No readings for this region: there is no state to assess. This is not the same as "
        "nominal."
    ),
    NOTHING_TO_ASSESS_NOTE: (
        "No countermeasures proposed: there are no readings for this region to assess."
    ),
    NO_FINDINGS_NOTE: (
        "No countermeasures proposed: the analysis found nothing outside the expected range in "
        "this region."
    ),
    NO_LIBRARY_ENTRY_NOTE: (
        "No countermeasures in the library for what the analysis found in this region."
    ),
    _relevance(STANDARD_MEASURES_SOURCE): (
        "when NASA takes the Spaceflight Standard Measures measurements before and after flight"
    ),
    _relevance(BONE_DXA_SOURCE): (
        "when NASA performs bone densitometry (DXA) before and after flight"
    ),
    STANDARD_MEASURES_SCOPE: (
        "The Spaceflight Standard Measures schedule, not that of every indicator: each measure "
        "has its own sessions and margins."
    ),
    BONE_DXA_SCOPE: (
        "Bone only: these are densitometry (DXA) sessions, not a schedule for every indicator."
    ),
    MOMENTS_BASIS: (
        "Phase changes of the mission calendar (their boundaries are EMMA design, with no "
        "source), the return, and the preflight and postflight days with readings, grouped into "
        "L- and R+ milestones (the R+ of postflight recovery). At each moment the state is "
        "recomputed with the readings recorded up to that instant."
    ),
    MILESTONES_BASIS: (
        "Postflight milestones: R+0, R+1, R+7 and R+30 are the postflight sessions of NASA's "
        "Spaceflight Standard Measures (the day of return and one, seven and thirty days later; "
        "the source says «one week» and «one month»), which is the schedule of that study and "
        "not that of every indicator. R+180, R+365, R+730 and R+1095 are the postflight "
        "densitometry sessions of NASA's technical brief on bone loss, at 6 months and at one, "
        "two and three years after return, or until the bone recovers: that source is about bone "
        "only. R+90 is EMMA design, with no source. Each milestone gathers the days since the "
        "previous one and is requested at the last reading of that span; whatever comes after "
        "R+1095 goes together."
    ),
    PREFLIGHT_MILESTONES_BASIS: (
        "Preflight milestones: L-180 and L-90 are the preflight sessions of NASA's Spaceflight "
        "Standard Measures (6 and 3 months before flight), which is the schedule of that study "
        "and not that of every indicator. L-30 is the preflight densitometry of the example "
        "schedule in NASA's technical brief on bone loss, for a 180-day mission on the ISS; the "
        "source writes «L- 180/30 d», as close to launch as feasible, and reading it as one "
        "session at L-30 is EMMA's. That source is about bone only. Each milestone gathers the "
        "days since the previous one and is requested at the last reading of that span; whatever "
        "comes after L-30 is the launch moment."
    ),
    CURRENT_MOMENT: "Now: last recorded reading",
    MOMENT_LABEL: "Recomputed with today's rules, with no ledger entry",
    MOMENT_EXTERNAL_BASIS: (
        "The external context is not the one of that time: the readings, including the recorded "
        "cumulative radiation, go up to that instant, but the solar events and the light time "
        "used in the assessment are the ones the system has today."
    ),
    REFERENCE_LABEL: "Reference skeleton (BodyParts3D): it is not the crew member's body.",
    REFERENCE_ALT: (
        "Human reference skeleton, anterior view: the subject's left is on the right of the image"
    ),
    REFERENCE_CAPTION.format(attribution=SKELETON_ATTRIBUTION): (
        f"Reference figure, not the crew member's. {SKELETON_ATTRIBUTION}."
    ),
    NO_SEGMENTATION: (
        "This crew member has no current skeleton segmentation: the reference skeleton is shown."
    ),
    NOT_USABLE: (
        "The skeleton segmentation of this crew member (ledger entry {index}) is not used: "
        "{reason}. The reference skeleton is shown."
    ),
    UNREADABLE_RECORD: (
        "The volume record of this crew member could not be read ({reason}). The reference "
        "skeleton is shown."
    ),
    OWN_LABEL: (
        "Skeleton from this crew member's CT: study recorded on {study_date} (ledger entry "
        "{study_index}), segmentation of {date} (entry {index})."
    ),
    SAMPLE_LABEL: (
        "Skeleton from the sample CT recorded for this crew member on {study_date} (ledger entry "
        "{study_index}; segmentation of {date}, entry {index}): it is a patient from an open "
        "dataset, signed as simulated data, not the crew member's body."
    ),
    OWN_ALT: (
        "Skeleton segmented from a CT, anterior view: the subject's left is on the right of the "
        "image"
    ),
    OWN_CAPTION: (
        "{status}. Reference image from before the flight or from Earth: it says where each "
        "segmented bone is, not what is happening to it, and it is not a clinical reading made "
        "on board."
    ),
    ABSENT_NOTE: (
        "Bones with no voxels in this segmentation: they are not drawn. The study may not cover "
        "them, or the model may not have found them."
    ),
    TRUNCATED_NOTE: (
        "Bones that reach the edge of the study: the point marks the center of the piece that "
        "falls inside the CT, not that of the bone."
    ),
    TRUNCATION_UNKNOWN_NOTE: (
        "It could not be measured which bones the edge of the study cuts: some point may mark "
        "the center of a piece and not that of the bone."
    ),
}
i18n.en_many(ENGLISH)

