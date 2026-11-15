"""El habitat como parte del sistema sanitario: atmosfera de cabina y sus limites.

La especificacion del equipo (`docs/contexto/`, §3 HabitatState, §7) y la base de conocimiento
(§6, "Habitat Twin") parten de una observacion simple: el estado de la nave cambia el estado de
la persona. Un pulso que sube y un PVT que empeora en tres tripulantes a la vez no son tres
anomalias individuales si el CO2 del modulo que comparten ha subido. Hasta el 2026-09-26 EMMA no
tenia ni un solo dato de cabina: la unica variable de contexto era la radiacion.

Los limites son los de NASA-STD-3001 Vol 2, leidos en el resumen tecnico de la OCHMO
"Environmental Control and Life Support System" (OCHMO-TB-002 Rev B, 14-11-2023; ficha
`ochmo-tb-002` del registro de evidencia, `LIMITS_SOURCE`):

- [V2 6004] ppCO2 media de una hora en el volumen habitable <= 3 mmHg.
- [V2 6003] PIO2 segun la tabla 6.2-1. Ver "LO QUE LA NORMA ESCRIBE DE VERDAD" abajo.
- [V2 6006] presion total 34,5 kPa < p <= 103 kPa para exposicion indefinida.
- [V2 6012] figura 6.2-2: temperatura y humedad JUNTAS. Ver abajo.
- [V2 6013] zona de rendimiento: 20-25 degC y 30-60 % de humedad relativa.
- [V2 6077] ruido: menos de 85 dBA en cualquier duracion, leido en el resumen tecnico de
  acustica (OCHMO-TB-035 Rev C, 06-10-2023, pagina 2: "the A-weighted sound level (excluding
  impulse noise and alarm signals) shall be less than 85 dBA, regardless of time duration";
  ficha `ochmo-tb-035`, `NOISE_SOURCE`, leida el 2026-10-31). Es el unico limite evaluado que
  no sale de OCHMO-TB-002, y su parametro cita su propia ficha. Ver abajo.
- SMAC de monoxido de carbono, amoniaco y formaldehido: JSC 20584 Rev C (2024-06-13), leidos en
  sus tablas (paginas 9, 11 y 15).

LO QUE LA NORMA ESCRIBE DE VERDAD (NASA-STD-3001 Vol 2 Rev F, releida el 2026-10-14)
-----------------------------------------------------------------------------------
Hasta el 2026-10-14 tres limites decian mas, o otra cosa, que la norma:

- **O2.** 145-155 mmHg es el "Normoxia Target Range" de la tabla 6.2-1: un rango OBJETIVO de
  diseno, no un limite de salud. Pasa a la clase `target` (fuera = aviso, como la zona de
  rendimiento; no es excursion normativa ni entra en ninguna hipotesis). Los limites de
  exposicion de esa misma fila son otros: "Indefinite Hyperoxia Upper Limit 356" y "Mild
  Hypoxia Lower Limit 127****", cuya nota dice "1-hour time-weighted average with an absolute
  lower limit for the minimum hypoxia range of 122 mmHg". Esos tres son los de salud. El de
  hiperoxia de corta duracion (791, 6-9 h, para la prerrespiracion de una EVA) no se evalua: es
  para un traje, no para la cabina.
- **Temperatura y humedad.** [V2 6012] pide mantenerlas "within the boundaries of the Operating
  Limits as shown in Figure 6.2-2": un cuadrilatero, no dos rangos. Sus cuatro vertices van
  rotulados en la figura: (18C, 75%), (25.7C, 75%), (27C, 25%) y (19.1C, 25%). Los lados de
  arriba y abajo son los de 75 % y 25 % de humedad: la humedad se juzga sola, lectura a lectura.
  Los lados izquierdo y derecho estan inclinados: el limite de temperatura DEPENDE de la humedad
  del mismo instante. Con una lectura de humedad simultanea (`PAIR_TOLERANCE`) se juzga contra
  esos lados; sin ella, una temperatura fuera de 18-27 degC esta fuera con cualquier humedad y
  se juzga, y una dentro de esa franja pero cerca de un lado inclinado NO es evaluable con una
  lectura sola, y no se juzga. Aproximacion declarada: la figura dibuja los lados rectos sobre
  la razon de humedad (g/kg); EMMA los traza rectos entre los mismos vertices sobre la humedad
  relativa, porque la figura no declara la presion a la que esta dibujada. Calculado a
  101,325 kPa (supuesto de ese calculo, no de la figura): los lados inclinados difieren menos de
  0,02 degC; el de arriba llega en la figura hasta ~76,9 % a media altura (EMMA corta en 75, mas
  estricto) y el de abajo hasta ~25,6 % (EMMA admite desde 25, hasta 0,6 puntos mas laxo).
- **Ruido.** [V2 6077] escribe su requisito "For off-nominal operations, broadcast
  communications, pressurization valve noise, and maintenance activities", y su justificacion
  dice que no es para las emisiones nominales, que limitan [V2 6078] y [V2 6080]. Sigue siendo
  limite de salud —la misma justificacion lo llama "the hazardous noise limit during all phases
  except launch, entry, and abort", y la tabla 6.6-2 lo pone como "Hazardous Noise <85 dBA" en
  orbita—, pero su rotulo (`Limit.label`) dice para que lo escribe la norma, y que EMMA no sabe
  si la lectura usa la ponderacion temporal rapida que el requisito pide.

POR QUE NO SON CODIGOS LOINC
---------------------------
LOINC codifica observaciones clinicas y de laboratorio sobre una persona. La atmosfera de un
modulo no es un sujeto clinico: es telemetria del vehiculo. Van en el sistema propio
`https://emma.mission/codes` y cada uno lo declara (invariante 1), con prueba.

LO QUE SOLO SE MUESTRA
----------------------
La especificacion (§3, HabitatState) pide tambien "noise/light". El ruido tiene limite leido. La
luz tiene REQUISITOS leidos, pero ninguno es un limite de toda la cabina a toda hora
(NASA-STD-3001 Vol 2 Rev F, leida el 2026-10-13 en su PDF oficial):

- [V2 8051] pide niveles de iluminancia "to support the range of expected crew tasks, at
  minimum, per Table 8.7-1": un valor por TAREA (traslado, ambiente general, tareas medicas o de
  mantenimiento) y un maximo para el SUENO, cada uno medido en un plano y con una orientacion
  de sensor concretos. Su justificacion lo dice: "A single type of lighting at a single
  illumination level is insufficient to support all tasks", y que alguna operacion pide
  oscurecer la cabina. [V2 8057] exige ademas que las luces sean regulables.
- [V2 8055] (tabla 8.7-2) da la luz para el ritmo circadiano en OTRA magnitud (iluminancia
  melanopica equivalente, EDI, en la cornea) y por PERIODO (vigilia y pre-sueno).

EMMA recibe una iluminancia de cabina sin saber que tarea se hace, si es periodo de sueno ni
hacia donde mira el sensor. Con eso no se puede decir que una lectura incumple nada, y no se
fuerza un limite que la norma no da. Asi que la luz sigue en una lista aparte, `DISPLAY_ONLY`:
se firma y se ensena como cualquier lectura, dice "sin limite general" y **no se evalua nunca**
—no da excursion, no entra en ninguna hipotesis ni en la huella de reglas como limite—. Junto a
la lectura se ensenan los requisitos leidos (`reference_requirements`), cada uno con su
condicion y rotulados "requisito por tarea; EMMA no conoce la tarea". Una lista aparte, y no un
parametro mas con `limits=()`, para que la prueba que exige un limite a todo parametro evaluado
siga valiendo para todos los demas.

AGUA Y MICROBIOLOGIA: SE ENSENAN CON SU LIMITE Y NO SE EVALUAN (2026-10-22)
---------------------------------------------------------------------------
La especificacion (§3) pone el agua entre lo que el habitat cambia en la persona, y el sistema
«Agua» ya estaba declarado (`data/habitat_systems.json`) sin un solo parametro. Decision del
usuario del 2026-10-22: las lecturas de agua y de microbiologia se ensenan junto al limite que
se haya leido y **no se evaluan**, como la luz; el veredicto no cambia. Van en `DISPLAY_ONLY`,
cada una en su grupo (`GROUPS`) para que la interfaz no las pinte bajo «Atmosfera de cabina».

Lo leido el 2026-10-22, cada documento en su PDF oficial:

- **JSC 63414 Rev A** (SWEG, noviembre de 2023; ficha `jsc-63414-rev-a`). Valores guia por
  compuesto y por tiempo de consumo (1, 10, 100 y 1000 dias), en mg/L. EMMA declara dos: el
  carbono organico total (pagina 14: solo 100 y 1000 dias, 5 mg/L; su observacion dice que
  supone que todo el carbono medido es formaldehido) y la plata (pagina 13: 5, 5, 0,6 y
  0,4 mg/L). La eleccion de esos dos es de diseno de EMMA. El documento dice que los de 1 y
  10 dias son para contingencias, «not necessarily fully protective of crew health» y no
  criterio de diseno, y que superar uno «does not mean that health impairment is certain».
  EMMA no sabe cuanto tiempo se ha bebido esa agua: se ensenan los cuatro tiempos y no se
  compara la lectura con ninguno. El yodo no tiene SWEG en esa tabla: no se declara.
- **NASA-STD-3001 Vol 2 Rev F**: [V2 6026] (6.3.1.1, agua potable), [V2 6059] (6.2.8.5, aire)
  y [V2 7081] (7.11.3, superficies) piden agua, aire y superficies «microbiologically safe» y
  **no dan cifra**: remiten a la guia del laboratorio de microbiologia del JSC y a los
  requisitos de cada programa, que EMMA no ha leido. Las tres lecturas microbianas se ensenan
  con ese requisito, sin limite. Sin fuente, sin limite.

Ninguno de estos parametros entra en `rules_version` (solo entra `PARAMETERS`) ni en
`excursions`: la huella y el veredicto son los de antes, con prueba. [V2 6046] pide al vehiculo
avisar cuando la calidad del agua se acerque a sus limites; EMMA no es ese sistema y, por la
decision de arriba, no avisa.

RADIACION: SE ENSENA EN EL HABITAT Y NO SE EVALUA AQUI (2026-10-26)
------------------------------------------------------------------
La especificacion (§3, HabitatState) pide «radiation» en el estado del habitat, y la base de
conocimiento (§10, Habitat Twin) pone la radiacion entre lo que el habitat cambia en la persona.
Hasta el 2026-10-26 la tasa de dosis solo existia como lectura de cada tripulante
(`absorbed-dose-rate`, `ingest/codes.py`) y el evento solar solo en el estado de cada uno
(DONKI, `environment/donki.py`). Decision del usuario del 2026-10-26: el habitat ensena la ultima
tasa de dosis de cada dosimetro y el evento solar vigente, diciendo de donde sale cada cifra, con
dos limites declarados:

- **Modulo sin declarar.** La lectura llega atribuida a un tripulante, no a un modulo: EMMA no
  sabe donde esta el dosimetro (un dosimetro personal va con la persona; uno de area, en su
  sitio), y no lo deduce de la ubicacion declarada del tripulante.
- **Sin factores de blindaje.** El refugio por modulo esta rechazado (`docs/contexto/README.md`,
  «No se adopta»: serian factores de blindaje inventados; EMMA no modela una nave concreta). La
  cifra es la del dosimetro tal cual: ni se corrige ni se reparte por modulo.

Es descriptivo (`radiation_state`): no da excursion de habitat, no entra en ninguna hipotesis ni
en `rules_version`, y no cambia ningun nivel. La tasa de dosis ya la evalua el estado de cada
tripulante como lectura suya, y el evento solar ya da su escala aguda; aqui solo se repiten, con
las mismas reglas de seleccion (el evento es el que elige el motor de riesgo).

Que NO hace este modulo: no correlaciona ni decide nada sobre la salud; solo dice si un
parametro esta dentro de su limite normativo. La hipotesis de causa compartida es de
`analysis/context.py` y va rotulada como correlacion.
"""

from __future__ import annotations

import bisect
import datetime as dt
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import display, i18n
from app.environment.donki import SolarEvent
from app.evidence import registry
from app.ingest.fhir import EvidenceContext, VitalObservation, evidence_context_for

EMMA_SYSTEM = "https://emma.mission/codes"
# El documento del catalogo de limites. Su URL vive en su ficha del registro de evidencia
# (`LIMITS_SOURCE`, mas abajo) y no se vuelve a escribir aqui.
SOURCE_TITLE = (
    "NASA-STD-3001 Technical Brief OCHMO-TB-002 Rev B, Environmental Control and "
    "Life Support System (2023-11-14)"
)
NOT_LOINC = (
    "telemetría de cabina, no una observación sobre una persona: LOINC codifica observaciones "
    "clínicas y de laboratorio de un paciente"
)

i18n.en(
    NOT_LOINC,
    "cabin telemetry, not an observation about a person: LOINC codes clinical and laboratory "
    "observations of a patient",
)

MODULES_PATH = Path(__file__).resolve().parents[1] / "data" / "habitat_modules.json"


def _served(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Un diccionario que ya va a la interfaz, con los textos de `keys` en el idioma de la
    peticion (`i18n.loc`: su ingles esta registrado junto a cada constante).

    Existe para traducir a la salida y no en la definicion: los literales castellanos alimentan
    la huella de reglas (`Limit.requirement`) y las pruebas, y no se tocan. Las claves, los
    identificadores y las unidades no pasan por aqui.
    """
    return {
        key: i18n.loc(value) if key in keys and isinstance(value, str) else value
        for key, value in payload.items()
    }


@dataclass(frozen=True, slots=True)
class HabitatModule:
    key: str
    display: str
    description: str

    def to_dict(self) -> dict[str, str]:
        # El ingles de la lista de modulos va en su hermano `habitat_modules.en.json`.
        return {
            "key": self.key,
            "display": i18n.localized(self.display, MODULES_PATH),
            "description": i18n.localized(self.description, MODULES_PATH),
        }


def load_modules(path: Path = MODULES_PATH) -> tuple[dict[str, HabitatModule], str, str]:
    """La lista declarada de modulos, su base y el modulo por defecto.

    Es un fichero de datos y no una constante porque es un parametro de diseno: EMMA no modela
    una nave concreta, y la lista se cambia por la del vehiculo sin tocar codigo. Una lista
    vacia, repetida o sin el modulo por defecto no se carga: una lectura sin modulo declarado
    no tendria donde caer.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    modules = {
        item["key"]: HabitatModule(item["key"], item["display"], item["description"])
        for item in raw["modules"]
    }
    if not modules or len(modules) != len(raw["modules"]):
        raise ValueError("lista de módulos vacía o con claves repetidas")
    if any(not key.strip() or not item.display.strip() for key, item in modules.items()):
        raise ValueError("un módulo sin clave o sin nombre no se puede declarar")
    if raw["default"] not in modules:
        raise ValueError("el módulo por defecto no está en la lista declarada")
    if not str(raw["basis"]).strip():
        raise ValueError("la lista de módulos tiene que declarar su base")
    return modules, str(raw["basis"]), str(raw["default"])


# Lista pequena y declarada (especificacion §3, HabitatState "module/location"). Parametro de
# diseno sin respaldo bibliografico, y `MODULES_BASIS` lo dice en la API. Una lectura que no
# declara modulo cae en el de por defecto; un tripulante que no declara donde esta se supone
# que comparte el habitat, y toda hipotesis que se apoye en ello lo dice.
MODULES, MODULES_BASIS, DEFAULT_MODULE = load_modules()


def module_display(key: str) -> str:
    """El nombre de un modulo, en el idioma de la peticion; el de uno que ya no esta en la lista
    es su clave."""
    return i18n.localized(MODULES[key].display, MODULES_PATH) if key in MODULES else key


def modules_basis() -> str:
    """La base declarada de la lista de modulos (`MODULES_BASIS`), en el idioma de la peticion."""
    return i18n.localized(MODULES_BASIS, MODULES_PATH)


# Donde se ensena cada parametro. La atmosfera de cabina (con la luz) va en su tabla; el agua
# potable y la microbiologia del aire y las superficies, cada una en su bloque. Solo agrupa lo
# que se ensena: no decide nada, y los nombres van tal cual a la interfaz.
CABIN, WATER, MICROBIOLOGY = "cabin", "water", "microbiology"
GROUPS: dict[str, str] = {
    CABIN: "Atmósfera de cabina",
    WATER: "Agua potable",
    MICROBIOLOGY: "Microbiología del aire y las superficies",
}
i18n.en_many({
    GROUPS[CABIN]: "Cabin atmosphere",
    GROUPS[WATER]: "Drinking water",
    GROUPS[MICROBIOLOGY]: "Microbiology of air and surfaces",
})
# Toda lectura de habitat es una medida de un sensor o de una muestra analizada: no hay
# lecturas de cabina inferidas ni predichas. Se publica para que cada lectura diga su tipo.
OBSERVATION_TYPE = "measured"

HEALTH, PERFORMANCE, TARGET = "health", "performance", "target"
# Las clases de limite. Solo `health` cuenta como excursion normativa (alerta de habitat,
# hipotesis de causa compartida); las otras dos son aviso.
LIMIT_KINDS: dict[str, str] = {
    HEALTH: "límite normativo",
    PERFORMANCE: "zona de confort",
    TARGET: "rango objetivo",
}
i18n.en_many({
    LIMIT_KINDS[HEALTH]: "normative limit",
    LIMIT_KINDS[PERFORMANCE]: "comfort zone",
    LIMIT_KINDS[TARGET]: "target range",
})

# Una lectura de humedad cuenta como simultanea a una de temperatura si esta a esta distancia o
# menos, en el mismo modulo. Diseno EMMA sin fuente: la figura no habla de tiempos; el simulador
# emite las dos en el mismo instante.
PAIR_TOLERANCE = dt.timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class FigureBoundary:
    """Los lados inclinados de una figura conjunta: el limite de un parametro segun otro.

    Existe por [V2 6012] (figura 6.2-2): el limite de temperatura es un lado inclinado del
    cuadrilatero, y su valor depende de la humedad del mismo instante. `low_edge` y `high_edge`
    son los dos vertices de cada lado, como (valor, valor del par), tal y como van rotulados en
    la figura. Entre ellos, recta (aproximacion declarada en la cabecera del modulo).
    """

    figure: str
    pair: str
    low_edge: tuple[tuple[float, float], tuple[float, float]]
    high_edge: tuple[tuple[float, float], tuple[float, float]]

    @property
    def pair_range(self) -> tuple[float, float]:
        values = [p for _, p in (*self.low_edge, *self.high_edge)]
        return min(values), max(values)

    @property
    def envelope(self) -> tuple[float, float]:
        """Fuera de esto se esta fuera de la figura con cualquier valor del par."""
        return min(v for v, _ in self.low_edge), max(v for v, _ in self.high_edge)

    @staticmethod
    def _at(edge: tuple[tuple[float, float], tuple[float, float]], pair: float) -> float:
        (v0, p0), (v1, p1) = edge
        return v0 + (v1 - v0) * (pair - p0) / (p1 - p0)

    def bounds(self, pair: float | None) -> tuple[float, float] | None:
        """El intervalo valido con ese valor del par; None si no es evaluable con una lectura.

        Sin par, o con el par fuera de la figura (eso ya lo juzga el limite del par), solo la
        envolvente es segura.
        """
        low_pair, high_pair = self.pair_range
        if pair is None or not low_pair <= pair <= high_pair:
            return None
        return self._at(self.low_edge, pair), self._at(self.high_edge, pair)

    def vertices(self) -> list[list[float]]:
        """Los cuatro vertices rotulados en la figura, en orden de recorrido."""
        return [list(point) for point in (*self.low_edge, *reversed(self.high_edge))]


@dataclass(frozen=True, slots=True)
class Limit:
    low: float | None
    high: float | None
    requirement: str
    # Una de `LIMIT_KINDS`. "health": limite normativo (fuera = alerta de habitat).
    # "performance": zona de confort; "target": rango objetivo de diseno (fuera = aviso).
    kind: str
    # Ventana de la media con que se juzga ESTE limite (los SMAC tienen un valor por tiempo
    # de exposicion: 1 h, 24 h, 7 d, 30 d...). None: lectura a lectura.
    averaging: dt.timedelta | None = None
    # Rotulo del backend que la interfaz ensena tal cual: para que escribe la norma el limite.
    label: str | None = None
    # Solo en un limite de figura conjunta: `low`/`high` son entonces su envolvente.
    figure: FigureBoundary | None = None

    def __post_init__(self) -> None:
        if self.kind not in LIMIT_KINDS:
            raise ValueError(f"clase de límite desconocida: {self.kind}")

    def contains(self, value: float) -> bool:
        return (self.low is None or value >= self.low) and (
            self.high is None or value <= self.high
        )

    def to_dict(self) -> dict[str, Any]:
        # `requirement` entra tal cual en la huella de reglas: su ingles se pone solo aqui, al
        # servirlo, y el campo no cambia.
        return _served({
            "low": self.low, "high": self.high, "requirement": self.requirement,
            "kind": self.kind, "kind_display": LIMIT_KINDS[self.kind],
            "averaging_minutes": (
                self.averaging.total_seconds() / 60 if self.averaging else None
            ),
            "label": self.label,
            "figure": (
                None if self.figure is None
                else {"name": i18n.loc(self.figure.figure), "pair": self.figure.pair,
                      "vertices": self.figure.vertices()}
            ),
        }, "requirement", "kind_display", "label")


@dataclass(frozen=True, slots=True)
class ReferenceSource:
    """El documento de donde salen los requisitos que se ensenan junto a una lectura.

    Solo el identificador de su ficha, el titulo y el dia de la lectura: la URL vive en el
    registro de evidencia y no se vuelve a escribir aqui.
    """

    id: str
    title: str
    read_on: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "title": i18n.loc(self.title), "read_on": self.read_on}

    def with_url(self) -> dict[str, str]:
        """La ficha citada mas la URL de su documento, tomada del registro: es lo que la
        interfaz enlaza. La ficha existe y tiene URL, o el modulo no arranca (`_check_sources`)."""
        url = registry.get(self.id).url
        assert url is not None
        return {**self.to_dict(), "url": url}


# Los documentos de donde se leyo cada limite evaluado, citados por su ficha. El del catalogo es
# OCHMO-TB-002 (leido entero el 2026-10-21, segun su ficha); el del ruido, OCHMO-TB-035, el
# resumen tecnico de acustica (leido el 2026-10-31): [V2 6077] no esta en el del ECLSS.
LIMITS_SOURCE = ReferenceSource("ochmo-tb-002", SOURCE_TITLE, "2026-10-21")
NOISE_SOURCE = ReferenceSource(
    "ochmo-tb-035",
    "NASA-STD-3001 Technical Brief OCHMO-TB-035 Rev C, Acoustics (2023-10-06)",
    "2026-10-31",
)


@dataclass(frozen=True, slots=True)
class ReferenceRequirement:
    """Un requisito leido en la norma que se ENSENA junto a una lectura y NO se evalua.

    No es un `Limit`: el requisito vale para una tarea, un periodo o un plano de medida que
    EMMA no conoce, y `condition` lo dice. `source_row` es la fila de la tabla tal como se lee
    en la norma (sus celdas separadas por " | "). `stated` es para el valor que la tabla da
    sin comparador: no se le pone un ">=" que la fuente no escribe.
    """

    requirement: str
    table: str
    label: str
    unit: str
    condition: str
    source_row: str
    low: float | None = None
    high: float | None = None
    stated: float | None = None
    # False: la magnitud del requisito no es la que EMMA lee (EDI melanopica frente a lux).
    same_quantity: bool = True

    def to_dict(self) -> dict[str, Any]:
        # `source_row` es la fila tal como la escribe la fuente: no se traduce.
        return _served({
            "requirement": self.requirement, "table": self.table, "label": self.label,
            "low": self.low, "high": self.high, "stated": self.stated, "unit": self.unit,
            "condition": self.condition, "same_quantity": self.same_quantity,
            "source_row": self.source_row, "evaluated": False,
        }, "requirement", "table", "label", "condition")


@dataclass(frozen=True, slots=True)
class HabitatParameter:
    key: str
    display: str
    unit: str
    physical_min: float
    physical_max: float
    limits: tuple[Limit, ...]
    # Ventana de la media que exige el requisito (el CO2 se juzga en media de una hora).
    averaging: dt.timedelta | None = None
    not_loinc_reason: str = NOT_LOINC
    # Solo en los de `DISPLAY_ONLY`: por que la lectura se muestra y no se evalua.
    limit_note: str | None = None
    # Solo en los de `DISPLAY_ONLY`: requisitos leidos que se ensenan al lado, sin evaluar, con
    # su rotulo (que dice por que no se evaluan) y el documento de donde salen.
    reference_requirements: tuple[ReferenceRequirement, ...] = ()
    reference_label: str | None = None
    reference_source: ReferenceSource | None = None
    # Solo en un evaluado cuyos limites no se leyeron en el documento del catalogo
    # (`LIMITS_SOURCE`): la ficha de donde si se leyeron. No entra en la huella de reglas.
    limit_source: ReferenceSource | None = None
    # Donde se ensena (`GROUPS`). No decide nada.
    group: str = CABIN

    def __post_init__(self) -> None:
        if self.group not in GROUPS:
            raise ValueError(f"{self.key}: grupo desconocido ({self.group})")
        if self.reference_requirements and (
            self.reference_label is None or self.reference_source is None
        ):
            # Un requisito sin el rotulo de por que no se evalua se leeria como un limite.
            raise ValueError(f"{self.key}: requisitos de referencia sin rótulo o sin documento")

    @property
    def system(self) -> str:
        return EMMA_SYSTEM

    @property
    def source(self) -> ReferenceSource:
        """La ficha del documento de donde se leyeron los limites de este parametro."""
        return self.limit_source or LIMITS_SOURCE

    def to_dict(self) -> dict[str, Any]:
        return _served({
            "key": self.key,
            "display": self.display,
            "unit": self.unit,
            "system": self.system,
            "group": self.group,
            "group_display": GROUPS[self.group],
            "observation_type": OBSERVATION_TYPE,
            "not_loinc_reason": self.not_loinc_reason,
            "averaging_minutes": (
                self.averaging.total_seconds() / 60 if self.averaging else None
            ),
            "limits": [item.to_dict() for item in self.limits],
            # Lo que solo se muestra no tiene norma leida que citar, y lo dice `limit_note`.
            "limit_note": self.limit_note,
            # La ficha del documento de los limites, con su URL del registro.
            "source": None if self.limit_note is not None else self.source.with_url(),
            # Requisitos leidos que NO se evaluan (la luz, el agua, la microbiologia): se ensenan
            # junto a la lectura con su condicion y su rotulo. `source` sigue en None: no hay
            # limite evaluado que citar.
            "reference_requirements": [item.to_dict() for item in self.reference_requirements],
            "reference_label": self.reference_label if self.reference_requirements else None,
            "reference_source": (
                self.reference_source.to_dict()
                if self.reference_requirements and self.reference_source is not None else None
            ),
        }, "display", "group_display", "not_loinc_reason", "limit_note", "reference_label")


# Rotulos de los limites que dicen algo mas que su cifra (ver la cabecera). Van tal cual a la
# interfaz, que no los redacta.
O2_TARGET_LABEL = (
    "rango objetivo de normoxia de la tabla 6.2-1, no un límite de salud: salir de él es un "
    "aviso"
)
O2_MILD_HYPOXIA_LABEL = (
    "límite inferior de hipoxia leve de la tabla 6.2-1, en media de 1 h; la norma lo admite de "
    "duración indefinida con vigilancia"
)
O2_ABSOLUTE_LABEL = "mínimo absoluto de la hipoxia leve (nota **** de la tabla 6.2-1)"
O2_HYPEROXIA_LABEL = "límite superior de hiperoxia de duración indefinida (tabla 6.2-1)"
THERMAL_TEMPERATURE_LABEL = (
    "figura 6.2-2, conjunta con la humedad: el límite exacto depende de la humedad del mismo "
    "instante; sin ella solo se juzga fuera de la envolvente"
)
THERMAL_HUMIDITY_LABEL = "lados superior e inferior de la figura 6.2-2"
NOISE_LABEL = (
    "límite de ruido peligroso que la norma escribe para operaciones fuera de lo nominal, "
    "comunicaciones, válvulas de presurización y mantenimiento; el ruido nominal lo limitan "
    "otros requisitos que EMMA no comprueba, y EMMA no sabe si la lectura usa la ponderación "
    "temporal rápida que pide"
)
# Figura 6.2-2 de NASA-STD-3001 Vol 2 Rev F, vertices tal como van rotulados: (19.1C, 25%) y
# (18C, 75%) a la izquierda, (27C, 25%) y (25.7C, 75%) a la derecha. Leida el 2026-10-14.
THERMAL_FIGURE = FigureBoundary(
    figure="Figura 6.2-2",
    pair="cabin-humidity",
    low_edge=((19.1, 25.0), (18.0, 75.0)),
    high_edge=((27.0, 25.0), (25.7, 75.0)),
)


PARAMETERS: dict[str, HabitatParameter] = {
    item.key: item
    for item in (
        HabitatParameter(
            key="cabin-ppco2", display="CO2 de cabina (presión parcial)", unit="mm[Hg]",
            physical_min=0.0, physical_max=100.0,
            limits=(Limit(None, 3.0, "[V2 6004]", "health", dt.timedelta(hours=1)),),
            averaging=dt.timedelta(hours=1),
        ),
        HabitatParameter(
            key="cabin-ppo2", display="O2 de cabina (presión parcial)", unit="mm[Hg]",
            physical_min=0.0, physical_max=800.0,
            # Tabla 6.2-1, fila PIO2 (mmHg). La lectura es la presion parcial de la cabina, no
            # la inspirada: `analysis/context.py` lo dice junto a la justificacion.
            limits=(
                Limit(145.0, 155.0, "[V2 6003] rango objetivo", TARGET, label=O2_TARGET_LABEL),
                Limit(127.0, None, "[V2 6003] hipoxia leve, media 1 h", HEALTH,
                      dt.timedelta(hours=1), label=O2_MILD_HYPOXIA_LABEL),
                Limit(122.0, None, "[V2 6003] mínimo absoluto", HEALTH,
                      label=O2_ABSOLUTE_LABEL),
                Limit(None, 356.0, "[V2 6003] hiperoxia indefinida", HEALTH,
                      label=O2_HYPEROXIA_LABEL),
            ),
        ),
        HabitatParameter(
            key="cabin-pressure", display="Presión total de cabina", unit="kPa",
            physical_min=0.0, physical_max=200.0,
            # 34,5 < p: el limite inferior es estricto en el requisito; se trata como >=
            # porque un sensor no distingue 34,5 de 34,50001.
            limits=(Limit(34.5, 103.0, "[V2 6006]", "health"),),
        ),
        HabitatParameter(
            key="cabin-temperature", display="Temperatura de cabina", unit="Cel",
            physical_min=-50.0, physical_max=80.0,
            # [V2 6012]: 18-27 es solo la envolvente; el limite exacto lo dan los lados
            # inclinados de la figura con la humedad del mismo instante (`FigureBoundary`).
            limits=(
                Limit(18.0, 27.0, "[V2 6012]", HEALTH, label=THERMAL_TEMPERATURE_LABEL,
                      figure=THERMAL_FIGURE),
                Limit(20.0, 25.0, "[V2 6013]", PERFORMANCE),
            ),
        ),
        # Ruido: [V2 6077], menos de 85 dBA sin importar la duracion, leido en el resumen de
        # acustica (ficha `ochmo-tb-035`, `NOISE_SOURCE`), no en el del ECLSS. El limite de ruido
        # continuo de trabajo, [V2 6078], es la curva NC-50 por bandas de octava: con una sola
        # lectura en dBA no se puede comprobar, y no se finge que se comprueba.
        HabitatParameter(
            key="cabin-noise", display="Ruido de cabina (nivel ponderado A)", unit="dB(A)",
            physical_min=0.0, physical_max=160.0,
            limits=(Limit(None, 85.0, "[V2 6077]", HEALTH, label=NOISE_LABEL),),
            limit_source=NOISE_SOURCE,
        ),
        # Contaminantes: SMAC de NASA, JSC 20584 Rev C (2024-06-13), en ppm. Cada limite con
        # la media de su tiempo de exposicion; para una mision de meses rige tambien el de 30 d.
        HabitatParameter(
            key="cabin-co", display="Monóxido de carbono de cabina", unit="[ppm]",
            physical_min=0.0, physical_max=10000.0,
            limits=(
                Limit(None, 425.0, "SMAC 1 h", "health", dt.timedelta(hours=1)),
                Limit(None, 100.0, "SMAC 24 h", "health", dt.timedelta(hours=24)),
                Limit(None, 55.0, "SMAC 7 d", "health", dt.timedelta(days=7)),
                Limit(None, 15.0, "SMAC 30 d", "health", dt.timedelta(days=30)),
            ),
        ),
        HabitatParameter(
            key="cabin-ammonia", display="Amoníaco de cabina", unit="[ppm]",
            physical_min=0.0, physical_max=10000.0,
            limits=(
                Limit(None, 30.0, "SMAC 1 h", "health", dt.timedelta(hours=1)),
                Limit(None, 20.0, "SMAC 24 h", "health", dt.timedelta(hours=24)),
                Limit(None, 3.0, "SMAC 7 d", "health", dt.timedelta(days=7)),
                # Fila «Ammonia» de la pagina 9: "30 d 3 (2) | 180 d 3 (2) | 1000 d 3 (2)".
                # Tienen el mismo valor que el de 7 d: una media de 30 dias o mas por encima de
                # 3 ppm casi siempre trae una semana por encima, y el de 7 d ya avisa. Se evaluan
                # igual, para que la cabina diga todos los que la tabla da y no solo uno.
                Limit(None, 3.0, "SMAC 30 d", "health", dt.timedelta(days=30)),
                Limit(None, 3.0, "SMAC 180 d", "health", dt.timedelta(days=180)),
                Limit(None, 3.0, "SMAC 1000 d", "health", dt.timedelta(days=1000)),
            ),
        ),
        # Formaldehido: los SMAC son valores techo (no medias); para misiones de mas de 7 dias
        # el techo es 0,1 ppm. Se juzga lectura a lectura.
        HabitatParameter(
            key="cabin-formaldehyde", display="Formaldehído de cabina", unit="[ppm]",
            physical_min=0.0, physical_max=100.0,
            limits=(Limit(None, 0.1, "SMAC techo (> 7 d)", "health"),),
        ),
        HabitatParameter(
            key="cabin-humidity", display="Humedad relativa de cabina", unit="%",
            physical_min=0.0, physical_max=100.0,
            limits=(
                Limit(25.0, 75.0, "[V2 6012]", HEALTH, label=THERMAL_HUMIDITY_LABEL),
                Limit(30.0, 60.0, "[V2 6013]", PERFORMANCE),
            ),
        ),
    )
}


NO_VERIFIED_LIMIT = (
    "Sin límite verificado: EMMA no ha leído ninguna fuente que fije un límite para este "
    "parámetro. La lectura se muestra y no se evalúa."
)


# La norma leida para la luz y para la justificacion de cada limite (`analysis/context.py`).
# Su ficha, con la URL, esta en el registro de evidencia con este identificador: aqui no se
# vuelve a escribir (el registro es el unico sitio donde vive la URL de una fuente).
STANDARD_REF = "nasa-std-3001-vol2-rev-f"
STANDARD_TITLE = "NASA-STD-3001, Volume 2, Revision F (aprobada 2026-07-14)"
STANDARD_READ_ON = "2026-10-13"
LIGHT_SOURCE = ReferenceSource(STANDARD_REF, STANDARD_TITLE, STANDARD_READ_ON)

REFERENCE_LABEL = "requisito por tarea; EMMA no conoce la tarea"
LIGHT_NO_GENERAL_LIMIT = (
    "Sin límite general: NASA-STD-3001 Vol 2 Rev F fija niveles de iluminación por tarea "
    "([V2 8051], tabla 8.7-1) y por periodo ([V2 8055], tabla 8.7-2), no un límite para toda "
    "la cabina a toda hora. EMMA no conoce la tarea, el periodo ni hacia dónde mira el sensor: "
    "la lectura se muestra y no se evalúa."
)
_AREA_AVERAGE = (
    "media de los puntos del área, con una uniformidad (media/mínimo) de 3:1 como mucho "
    "(nota 5)"
)
_AT_CORNEA = (
    "iluminancia melanópica equivalente (EDI) medida en la córnea, en el plano vertical "
    "(nota 1): no es la iluminancia que lee EMMA"
)
# Tablas 8.7-1 y 8.7-2 de NASA-STD-3001 Vol 2 Rev F, fila a fila, leidas el 2026-10-13
# (secciones 8.7.1 y 8.7.8). De la 8.7-2 no se copian las columnas "Melanopic DER" ni "Peak
# Wavelength": EMMA no mide espectro.
LIGHT_REQUIREMENTS: tuple[ReferenceRequirement, ...] = (
    ReferenceRequirement(
        "[V2 8051]", "Tabla 8.7-1", "Traslado y estiba", "lx",
        f"para tareas de traslado y estiba; {_AREA_AVERAGE}",
        "Translation & Stowage | >= 108 | 5", low=108.0,
    ),
    ReferenceRequirement(
        "[V2 8051]", "Tabla 8.7-1", "Ambiente general, plano horizontal", "lx",
        "en el plano horizontal donde quedan las manos de la tripulación, con el sensor hacia "
        f"el techo (nota 1); {_AREA_AVERAGE}",
        "General Horizontal Ambient Lighting | >= 350 | 1, 5", low=350.0,
    ),
    ReferenceRequirement(
        "[V2 8051]", "Tabla 8.7-1", "Ambiente general, plano vertical", "lx",
        "en el plano vertical de las manos o de los mandos al alcance, con el sensor "
        f"perpendicular a ese plano (nota 2); {_AREA_AVERAGE}",
        "General Vertical Ambient Lighting | >= 200 | 2, 5", low=200.0,
    ),
    ReferenceRequirement(
        "[V2 8051]", "Tabla 8.7-1",
        "Tareas médicas, técnicas, de mantenimiento, reparación y foto o TV", "lx",
        f"en la superficie designada para esas tareas (nota 3); {_AREA_AVERAGE}",
        "Medical/Technical/Maintenance/Repair/PhotoTV Lighting | >= 750 | 3, 5", low=750.0,
    ),
    ReferenceRequirement(
        "[V2 8051]", "Tabla 8.7-1", "Sueño de la tripulación", "lx",
        "en el punto medio de los ojos de quien duerme, con el sensor mirando hacia fuera "
        f"(nota 4); {_AREA_AVERAGE}",
        "Crew Sleep | <=0.02 | 4,5", high=0.02,
    ),
    ReferenceRequirement(
        "[V2 8055]", "Tabla 8.7-2", "Ambiente general en vigilia (ritmo circadiano)", "lx",
        f"durante las horas de vigilia (nota 2); {_AT_CORNEA}",
        "General Ambient Lighting | Melanopic EDI Lux: 250", stated=250.0,
        same_quantity=False,
    ),
    ReferenceRequirement(
        "[V2 8055]", "Tabla 8.7-2", "Antes del sueño (ritmo circadiano)", "lx",
        f"durante el pre-sueño programado (nota 3); {_AT_CORNEA}",
        "Crew Pre-Sleep | Melanopic EDI Lux: 8 +/- 2", low=6.0, high=10.0,
        same_quantity=False,
    ),
)


# --- Agua potable: SWEG de JSC 63414 Rev A, leido el 2026-10-22 (ver la cabecera) -----------
SWEG_REF = "jsc-63414-rev-a"
SWEG_TITLE = "JSC 63414 Rev A, Spacecraft Water Exposure Guidelines (noviembre de 2023)"
WATER_READ_ON = "2026-10-22"
SWEG_SOURCE = ReferenceSource(SWEG_REF, SWEG_TITLE, WATER_READ_ON)
SWEG_LABEL = (
    "valor guía por tiempo de consumo (SWEG); EMMA no sabe cuánto tiempo se ha bebido esa agua "
    "y no compara la lectura con ninguno"
)
WATER_NOT_EVALUATED = (
    "Se muestra y no se evalúa: junto a la lectura van los valores guía de la NASA para el agua "
    "potable (SWEG, JSC 63414 Rev A), uno por tiempo de consumo. EMMA no sabe cuánto tiempo se "
    "ha bebido esa agua y no la compara con ninguno: no da excursión, hipótesis, alerta ni nivel."
)
# Seccion 1.0 del documento, leida el 2026-10-22: lo que dice de cada grupo de tiempos.
_SWEG_ACUTE = (
    "valor guía para contingencias: el documento dice que no protege del todo la salud de la "
    "tripulación y que no es un criterio de diseño (sección 1.0)"
)
_SWEG_PROLONGED = (
    "valor guía para un consumo prolongado, sin riesgo apreciable según el documento; superarlo "
    "no implica un daño cierto, aunque indica que la tripulación puede estar expuesta a riesgos "
    "mayores (sección 1.0)"
)
_TOC_ASSUMPTION = (
    "; supone el peor caso razonable, que todo el carbono medido sea formaldehído "
    "(observación de la fila)"
)


def _sweg(
    chemical: str, page: int, period: str, value: float, effect: str, condition: str,
) -> ReferenceRequirement:
    """Una casilla de la tabla de SWEG: el compuesto, el tiempo de consumo, su valor y el efecto
    que lo fija, tal como van en la fila (`source_row`)."""
    days = {"1 day": "1 día", "10 days": "10 días", "100 days": "100 días",
            "1000 days": "1000 días"}[period]
    return ReferenceRequirement(
        f"SWEG {days}", f"JSC 63414 Rev A, p. {page}", f"Consumo de {days}", "mg/L",
        condition, f"{chemical} | {period} | {value:g} mg/L | {effect}", high=value,
    )


# Pagina 14: el TOC solo tiene valor de 100 y de 1000 dias; las columnas de 1 y 10 van vacias.
TOC_REQUIREMENTS: tuple[ReferenceRequirement, ...] = (
    _sweg("Total Organic Carbon", 14, "100 days", 5.0, "G.I. Gastric upset",
          _SWEG_PROLONGED + _TOC_ASSUMPTION),
    _sweg("Total Organic Carbon", 14, "1000 days", 5.0, "G.I. Gastric upset",
          _SWEG_PROLONGED + _TOC_ASSUMPTION),
)
# Pagina 13. La columna de observaciones de esa pagina va desalineada en el PDF (la nota sobre
# la argiria cae junto al propilenglicol): no se copia ninguna observacion para la plata.
SILVER_REQUIREMENTS: tuple[ReferenceRequirement, ...] = (
    _sweg("Silver", 13, "1 day", 5.0, "Nose RWC", _SWEG_ACUTE),
    _sweg("Silver", 13, "10 days", 5.0, "Nose RWC", _SWEG_ACUTE),
    _sweg("Silver", 13, "100 days", 0.6, "CNS Hypoactivity", _SWEG_PROLONGED),
    _sweg("Silver", 13, "1000 days", 0.4, "Skin Argyria", _SWEG_PROLONGED),
)

# --- Microbiologia: NASA-STD-3001 Vol 2 Rev F, releida el 2026-10-22 ---------------------------
MICROBIAL_SOURCE = ReferenceSource(STANDARD_REF, STANDARD_TITLE, WATER_READ_ON)
MICROBIAL_LABEL = "requisito sin cifra: la norma no da un nivel admisible"
MICROBIAL_NO_LIMIT = (
    "Sin límite leído: NASA-STD-3001 Vol 2 Rev F pide seguridad microbiológica y no da "
    "cifra; dice que los niveles admisibles los fijan la guía del laboratorio de microbiología "
    "del JSC y los requisitos de cada programa, que EMMA no ha leído. La lectura se muestra y no "
    "se evalúa."
)
_MICROBIAL_CONDITION = (
    "la norma no da cifra: remite a la guía del laboratorio de microbiología del JSC y a los "
    "requisitos de cada programa, según la arquitectura del vehículo y la duración de la misión"
)
# `source_row` es la frase del requisito tal como la escribe la norma.
WATER_MICROBIAL_REQUIREMENTS: tuple[ReferenceRequirement, ...] = (
    ReferenceRequirement(
        "[V2 6026]", "sección 6.3.1.1", "Agua potable química y microbiológicamente segura",
        "{CFU}/mL", _MICROBIAL_CONDITION,
        "At the point of crew consumption or contact, the system shall provide aesthetically "
        "acceptable potable water that is chemically and microbiologically safe for human use, "
        "including drinking, food rehydration, personal hygiene, and medical needs.",
    ),
)
AIR_MICROBIAL_REQUIREMENTS: tuple[ReferenceRequirement, ...] = (
    ReferenceRequirement(
        "[V2 6059]", "sección 6.2.8.5", "Aire de la atmósfera habitable microbiológicamente "
        "seguro", "{CFU}/m3", _MICROBIAL_CONDITION,
        "The system shall provide air in the habitable atmosphere that is microbiologically "
        "safe for human health and performance.",
    ),
)
SURFACE_MICROBIAL_REQUIREMENTS: tuple[ReferenceRequirement, ...] = (
    ReferenceRequirement(
        "[V2 7081]", "sección 7.11.3", "Superficies microbiológicamente seguras al contacto",
        "{CFU}/(100.cm2)", _MICROBIAL_CONDITION,
        "The system shall provide surfaces that are microbiologically safe for human contact.",
    ),
)


def _display_only(
    key: str, display: str, unit: str, physical_min: float, physical_max: float,
    limit_note: str = NO_VERIFIED_LIMIT,
    reference_requirements: tuple[ReferenceRequirement, ...] = (),
    reference_label: str | None = None,
    reference_source: ReferenceSource | None = None,
    group: str = CABIN,
) -> HabitatParameter:
    """Un parametro que solo se muestra: aqui no hay por donde darle un limite."""
    return HabitatParameter(
        key=key, display=display, unit=unit, physical_min=physical_min,
        physical_max=physical_max, limits=(), limit_note=limit_note,
        reference_requirements=reference_requirements, reference_label=reference_label,
        reference_source=reference_source, group=group,
    )


# Lecturas del habitat que se firman y se ensenan pero NO se evaluan (ver la cabecera). Las
# cotas fisicas no son limites: solo rechazan un fallo de sensor, y todas son de diseno de EMMA,
# sin fuente —una iluminancia, una concentracion o un recuento no son negativos; los topes son
# holgados a proposito—. La luz va la primera: es la de la cabina.
DISPLAY_ONLY: dict[str, HabitatParameter] = {
    item.key: item
    for item in (
        _display_only(
            "cabin-light", "Iluminación de cabina (iluminancia)", "lx", 0.0, 1_000_000.0,
            limit_note=LIGHT_NO_GENERAL_LIMIT, reference_requirements=LIGHT_REQUIREMENTS,
            reference_label=REFERENCE_LABEL, reference_source=LIGHT_SOURCE,
        ),
        _display_only(
            "water-toc", "Carbono orgánico total del agua potable", "mg/L", 0.0, 10_000.0,
            limit_note=WATER_NOT_EVALUATED, reference_requirements=TOC_REQUIREMENTS,
            reference_label=SWEG_LABEL, reference_source=SWEG_SOURCE, group=WATER,
        ),
        _display_only(
            "water-silver", "Plata del agua potable", "mg/L", 0.0, 10_000.0,
            limit_note=WATER_NOT_EVALUATED, reference_requirements=SILVER_REQUIREMENTS,
            reference_label=SWEG_LABEL, reference_source=SWEG_SOURCE, group=WATER,
        ),
        _display_only(
            "water-microbial", "Bacterias cultivables del agua potable", "{CFU}/mL",
            0.0, 1e9, limit_note=MICROBIAL_NO_LIMIT,
            reference_requirements=WATER_MICROBIAL_REQUIREMENTS,
            reference_label=MICROBIAL_LABEL, reference_source=MICROBIAL_SOURCE, group=WATER,
        ),
        _display_only(
            "air-microbial", "Bacterias cultivables del aire de cabina", "{CFU}/m3",
            0.0, 1e9, limit_note=MICROBIAL_NO_LIMIT,
            reference_requirements=AIR_MICROBIAL_REQUIREMENTS,
            reference_label=MICROBIAL_LABEL, reference_source=MICROBIAL_SOURCE,
            group=MICROBIOLOGY,
        ),
        _display_only(
            "surface-microbial", "Bacterias cultivables de las superficies", "{CFU}/(100.cm2)",
            0.0, 1e9, limit_note=MICROBIAL_NO_LIMIT,
            reference_requirements=SURFACE_MICROBIAL_REQUIREMENTS,
            reference_label=MICROBIAL_LABEL, reference_source=MICROBIAL_SOURCE,
            group=MICROBIOLOGY,
        ),
    )
}
if set(DISPLAY_ONLY) & set(PARAMETERS):
    raise ValueError("un parámetro no puede evaluarse y a la vez ser de solo mostrar")
if any(item.reference_requirements for item in PARAMETERS.values()):
    # Un requisito "de referencia" junto a un limite evaluado se leeria como un segundo limite:
    # lo que se evalua lleva `limits`, y nada mas.
    raise ValueError("un parámetro evaluado no lleva requisitos de solo mostrar")
if any(item.group != CABIN for item in PARAMETERS.values()):
    # Agua y microbiologia se muestran y no se evaluan (decision del 2026-10-22): un parametro
    # de esos grupos en `PARAMETERS` entraria en la huella de reglas y en las excursiones.
    raise ValueError("solo la atmósfera de cabina se evalúa")

# --- El ingles de lo que este catalogo ensena -------------------------------------------------
# Va aparte y no en cada definicion: los literales castellanos de arriba no se mueven (el
# requisito de cada `Limit` entra en la huella de reglas, y las pruebas y las campanas de
# mutantes fijan el resto). Se resuelve al servir (`_served`, `i18n.loc`). Las filas citadas
# (`source_row`) y los titulos que ya estan en ingles no llevan pareja. Las mismas afirmaciones
# que el castellano, con sus mismas reservas.
_EN_AREA_AVERAGE = (
    "average of the points in the area, with a uniformity (average/minimum) of 3:1 at most "
    "(note 5)"
)
_EN_AT_CORNEA = (
    "melanopic equivalent daylight illuminance (EDI) measured at the cornea, in the vertical "
    "plane (note 1): it is not the illuminance that EMMA reads"
)
_EN_SWEG_ACUTE = (
    "guideline value for contingencies: the document says it is not fully protective of crew "
    "health and that it is not a design criterion (section 1.0)"
)
_EN_SWEG_PROLONGED = (
    "guideline value for prolonged consumption, with no appreciable risk according to the "
    "document; exceeding it does not mean that harm is certain, although it indicates that "
    "the crew may be exposed to greater risks (section 1.0)"
)
i18n.en_many({
    # Requisitos de `Limit` con palabras (los demas son solo su codigo, igual en los dos idiomas).
    # La clave se toma del propio limite: si su castellano cambia, la pareja cambia con el.
    PARAMETERS["cabin-ppo2"].limits[0].requirement: "[V2 6003] target range",
    PARAMETERS["cabin-ppo2"].limits[1].requirement: "[V2 6003] mild hypoxia, 1 h average",
    PARAMETERS["cabin-ppo2"].limits[2].requirement: "[V2 6003] absolute minimum",
    PARAMETERS["cabin-ppo2"].limits[3].requirement: "[V2 6003] indefinite hyperoxia",
    PARAMETERS["cabin-formaldehyde"].limits[0].requirement: "SMAC ceiling (> 7 d)",
    O2_TARGET_LABEL: (
        "normoxia target range of table 6.2-1, not a health limit: leaving it is an advisory"
    ),
    O2_MILD_HYPOXIA_LABEL: (
        "mild hypoxia lower limit of table 6.2-1, as a 1 h average; the standard allows it for "
        "an indefinite duration with monitoring"
    ),
    O2_ABSOLUTE_LABEL: "absolute minimum of mild hypoxia (note **** of table 6.2-1)",
    O2_HYPEROXIA_LABEL: "indefinite-duration hyperoxia upper limit (table 6.2-1)",
    THERMAL_TEMPERATURE_LABEL: (
        "figure 6.2-2, joint with humidity: the exact limit depends on the humidity at the same "
        "instant; without it, only readings outside the envelope are judged"
    ),
    THERMAL_HUMIDITY_LABEL: "upper and lower sides of figure 6.2-2",
    NOISE_LABEL: (
        "hazardous noise limit that the standard writes for off-nominal operations, "
        "communications, pressurization valves and maintenance; nominal noise is limited by "
        "other requirements that EMMA does not check, and EMMA does not know whether the "
        "reading uses the fast time weighting it asks for"
    ),
    THERMAL_FIGURE.figure: "Figure 6.2-2",
    # Nombres de los parametros.
    PARAMETERS["cabin-ppco2"].display: "Cabin CO2 (partial pressure)",
    PARAMETERS["cabin-ppo2"].display: "Cabin O2 (partial pressure)",
    PARAMETERS["cabin-pressure"].display: "Cabin total pressure",
    PARAMETERS["cabin-temperature"].display: "Cabin temperature",
    PARAMETERS["cabin-noise"].display: "Cabin noise (A-weighted level)",
    PARAMETERS["cabin-co"].display: "Cabin carbon monoxide",
    PARAMETERS["cabin-ammonia"].display: "Cabin ammonia",
    PARAMETERS["cabin-formaldehyde"].display: "Cabin formaldehyde",
    PARAMETERS["cabin-humidity"].display: "Cabin relative humidity",
    DISPLAY_ONLY["cabin-light"].display: "Cabin lighting (illuminance)",
    DISPLAY_ONLY["water-toc"].display: "Total organic carbon in potable water",
    DISPLAY_ONLY["water-silver"].display: "Silver in potable water",
    DISPLAY_ONLY["water-microbial"].display: "Culturable bacteria in potable water",
    DISPLAY_ONLY["air-microbial"].display: "Culturable bacteria in cabin air",
    DISPLAY_ONLY["surface-microbial"].display: "Culturable bacteria on surfaces",
    # Lo que solo se muestra: por que no se evalua, y los requisitos que van al lado.
    NO_VERIFIED_LIMIT: (
        "No verified limit: EMMA has not read any source that sets a limit for this parameter. "
        "The reading is shown and not evaluated."
    ),
    STANDARD_TITLE: "NASA-STD-3001, Volume 2, Revision F (approved 2026-07-14)",
    REFERENCE_LABEL: "requirement per task; EMMA does not know the task",
    LIGHT_NO_GENERAL_LIMIT: (
        "No general limit: NASA-STD-3001 Vol 2 Rev F sets lighting levels per task ([V2 8051], "
        "table 8.7-1) and per period ([V2 8055], table 8.7-2), not a limit for the whole cabin "
        "at all hours. EMMA does not know the task, the period or which way the sensor faces: "
        "the reading is shown and not evaluated."
    ),
    "Tabla 8.7-1": "Table 8.7-1",
    "Tabla 8.7-2": "Table 8.7-2",
    LIGHT_REQUIREMENTS[0].label: "Translation and stowage",
    LIGHT_REQUIREMENTS[0].condition: f"for translation and stowage tasks; {_EN_AREA_AVERAGE}",
    LIGHT_REQUIREMENTS[1].label: "General ambient, horizontal plane",
    LIGHT_REQUIREMENTS[1].condition: (
        "in the horizontal plane where the crew's hands are, with the sensor facing the "
        f"ceiling (note 1); {_EN_AREA_AVERAGE}"
    ),
    LIGHT_REQUIREMENTS[2].label: "General ambient, vertical plane",
    LIGHT_REQUIREMENTS[2].condition: (
        "in the vertical plane of the hands or of the controls within reach, with the sensor "
        f"perpendicular to that plane (note 2); {_EN_AREA_AVERAGE}"
    ),
    LIGHT_REQUIREMENTS[3].label: (
        "Medical, technical, maintenance, repair and photo or TV tasks"
    ),
    LIGHT_REQUIREMENTS[3].condition: (
        f"on the surface designated for those tasks (note 3); {_EN_AREA_AVERAGE}"
    ),
    LIGHT_REQUIREMENTS[4].label: "Crew sleep",
    LIGHT_REQUIREMENTS[4].condition: (
        "at the midpoint between the eyes of the person sleeping, with the sensor facing "
        f"outwards (note 4); {_EN_AREA_AVERAGE}"
    ),
    LIGHT_REQUIREMENTS[5].label: "General ambient during waking hours (circadian rhythm)",
    LIGHT_REQUIREMENTS[5].condition: f"during waking hours (note 2); {_EN_AT_CORNEA}",
    LIGHT_REQUIREMENTS[6].label: "Before sleep (circadian rhythm)",
    LIGHT_REQUIREMENTS[6].condition: f"during scheduled pre-sleep (note 3); {_EN_AT_CORNEA}",
    SWEG_TITLE: "JSC 63414 Rev A, Spacecraft Water Exposure Guidelines (November 2023)",
    SWEG_LABEL: (
        "guideline value per consumption time (SWEG); EMMA does not know how long that water "
        "has been drunk and does not compare the reading with any of them"
    ),
    WATER_NOT_EVALUATED: (
        "Shown and not evaluated: next to the reading are NASA's guideline values for potable "
        "water (SWEG, JSC 63414 Rev A), one per consumption time. EMMA does not know how long "
        "that water has been drunk and does not compare it with any of them: it gives no "
        "excursion, hypothesis, alert or level."
    ),
    _SWEG_ACUTE: _EN_SWEG_ACUTE,
    _SWEG_PROLONGED: _EN_SWEG_PROLONGED,
    _SWEG_PROLONGED + _TOC_ASSUMPTION: (
        f"{_EN_SWEG_PROLONGED}; it assumes the reasonable worst case, that all the measured "
        "carbon is formaldehyde (remark in the row)"
    ),
    "SWEG 1 día": "SWEG 1 day",
    "SWEG 10 días": "SWEG 10 days",
    "SWEG 100 días": "SWEG 100 days",
    "SWEG 1000 días": "SWEG 1000 days",
    "Consumo de 1 día": "Consumption over 1 day",
    "Consumo de 10 días": "Consumption over 10 days",
    "Consumo de 100 días": "Consumption over 100 days",
    "Consumo de 1000 días": "Consumption over 1000 days",
    MICROBIAL_LABEL: "requirement without a figure: the standard gives no admissible level",
    MICROBIAL_NO_LIMIT: (
        "No limit read: NASA-STD-3001 Vol 2 Rev F asks for microbiological safety and gives no "
        "figure; it says that the admissible levels are set by the JSC microbiology laboratory "
        "guidance and by each program's requirements, which EMMA has not read. The reading is "
        "shown and not evaluated."
    ),
    _MICROBIAL_CONDITION: (
        "the standard gives no figure: it refers to the JSC microbiology laboratory guidance "
        "and to each program's requirements, depending on the vehicle architecture and the "
        "mission duration"
    ),
    WATER_MICROBIAL_REQUIREMENTS[0].table: "section 6.3.1.1",
    WATER_MICROBIAL_REQUIREMENTS[0].label: "Chemically and microbiologically safe potable water",
    AIR_MICROBIAL_REQUIREMENTS[0].table: "section 6.2.8.5",
    AIR_MICROBIAL_REQUIREMENTS[0].label: "Microbiologically safe air in the habitable atmosphere",
    SURFACE_MICROBIAL_REQUIREMENTS[0].table: "section 7.11.3",
    SURFACE_MICROBIAL_REQUIREMENTS[0].label: "Surfaces microbiologically safe for contact",
})


def cited_refs() -> set[str]:
    """Las fichas del registro que cita este modulo: los documentos de donde salen los limites
    evaluados y los de los requisitos que se ensenan sin evaluar."""
    return {spec.source.id for spec in PARAMETERS.values()} | {
        item.reference_source.id for item in DISPLAY_ONLY.values()
        if item.reference_source is not None
    }


def _check_sources(parameters: Mapping[str, HabitatParameter]) -> None:
    """Cada documento citado por un limite evaluado tiene ficha en el registro, con URL, o el
    modulo no arranca: una ficha que no existe seria una fuente inventada (`registry.get` lo
    rechaza), y una sin URL dejaria a la interfaz sin documento que enlazar."""
    for spec in parameters.values():
        if registry.get(spec.source.id).url is None:
            raise ValueError(f"{spec.key}: la ficha {spec.source.id} no tiene URL")


def _check_figures() -> None:
    """Una figura conjunta casa con sus dos parametros, o el modulo no arranca.

    Su envolvente es el `low`/`high` del limite que la lleva, y el rango del par es el limite
    del par con el mismo requisito: si no, los dos limites dirian figuras distintas.
    """
    for spec in PARAMETERS.values():
        for limit in spec.limits:
            if limit.figure is None:
                continue
            if (limit.low, limit.high) != limit.figure.envelope:
                raise ValueError(f"{spec.key}: la envolvente no casa con la figura")
            partner = PARAMETERS[limit.figure.pair]
            if not any(
                item.requirement == limit.requirement
                and (item.low, item.high) == limit.figure.pair_range
                for item in partner.limits
            ):
                raise ValueError(f"{spec.key}: {partner.key} no lleva el lado de la figura")


_check_figures()
_check_sources(PARAMETERS)


def parameter(key: str) -> HabitatParameter:
    """Un parametro de cabina, se evalue o solo se muestre."""
    found = PARAMETERS.get(key) or DISPLAY_ONLY.get(key)
    if found is None:
        raise KeyError(f"parámetro de hábitat desconocido: {key}")
    return found


@dataclass(frozen=True, slots=True)
class HabitatReading:
    module: str
    parameter: str
    value: float
    effective: dt.datetime
    source: str
    evidence_context: EvidenceContext | None = None

    def __post_init__(self) -> None:
        if self.effective.tzinfo is None:
            raise ValueError("`effective` debe llevar zona horaria")
        spec = parameter(self.parameter)
        if not math.isfinite(self.value):
            raise ValueError(f"{self.parameter}: valor no finito ({self.value})")
        if not spec.physical_min <= self.value <= spec.physical_max:
            raise ValueError(
                f"{self.parameter}: {self.value} {spec.unit} está fuera de lo físicamente "
                f"posible ({spec.physical_min}..{spec.physical_max}). Es un fallo de sensor"
            )
        if not self.module.strip():
            raise ValueError("un módulo sin nombre no se puede correlacionar con nadie")
        if self.evidence_context is None:
            object.__setattr__(self, "evidence_context", evidence_context_for(self.source))

    @property
    def evidence(self) -> EvidenceContext:
        assert self.evidence_context is not None
        return self.evidence_context

    def to_payload(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "parameter": self.parameter,
            "value": self.value,
            "unit": parameter(self.parameter).unit,
            "effective": self.effective.isoformat(),
            "source": self.source,
            "evidence_context": self.evidence.value,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> HabitatReading:
        if payload.get("unit") != parameter(payload["parameter"]).unit:
            raise ValueError("unidad del asiento distinta de la del catálogo de hábitat")
        return cls(
            module=payload["module"],
            parameter=payload["parameter"],
            value=float(payload["value"]),
            effective=dt.datetime.fromisoformat(payload["effective"]),
            source=payload["source"],
            evidence_context=EvidenceContext(payload["evidence_context"]),
        )


@dataclass(frozen=True, slots=True)
class Excursion:
    """Un parametro fuera de un limite, en un modulo, durante un intervalo."""

    module: str
    parameter: str
    kind: str
    requirement: str
    start: dt.datetime
    end: dt.datetime
    worst: float

    def to_dict(self) -> dict[str, Any]:
        spec = parameter(self.parameter)
        return _served({
            "module": self.module,
            "parameter": self.parameter,
            "display": spec.display,
            "unit": spec.unit,
            "kind": self.kind,
            "requirement": self.requirement,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "worst": round(self.worst, 3),
        }, "display", "requirement")


def _judged(
    series: Sequence[HabitatReading], averaging: dt.timedelta | None
) -> list[tuple[dt.datetime, float]]:
    """Valores tal y como los juzga el limite: la media movil si pide media."""
    if averaging is None:
        return [(item.effective, item.value) for item in series]
    judged: list[tuple[dt.datetime, float]] = []
    window: list[HabitatReading] = []
    total = 0.0
    for item in series:
        window.append(item)
        total += item.value
        while window and window[0].effective <= item.effective - averaging:
            total -= window.pop(0).value
        judged.append((item.effective, total / len(window)))
    return judged


def _simultaneous(
    moment: dt.datetime, pair: Sequence[HabitatReading]
) -> float | None:
    """La lectura del par mas cercana a `moment`, si esta dentro de `PAIR_TOLERANCE`.

    `pair` viene ordenada por instante: se busca por biseccion, no recorriendola entera.
    """
    index = bisect.bisect_left(pair, moment, key=lambda item: item.effective)
    near = [item for item in pair[max(index - 1, 0): index + 1]
            if abs(item.effective - moment) <= PAIR_TOLERANCE]
    if not near:
        return None
    return min(near, key=lambda item: abs(item.effective - moment)).value


def _bounded(
    limit: Limit, judged: Sequence[tuple[dt.datetime, float]],
    pair: Sequence[HabitatReading],
) -> list[tuple[dt.datetime, float, float | None, float | None]]:
    """Cada valor juzgado con los extremos que le tocan.

    Un limite normal tiene los mismos en todo momento. Uno de figura conjunta los toma de los
    lados inclinados con la lectura simultanea del par; sin ella, de la envolvente, pero solo
    para lo que cae fuera de ella: lo de dentro no es evaluable con una lectura sola, y se le
    dan extremos abiertos (no se juzga).
    """
    figure = limit.figure
    if figure is None:
        return [(moment, value, limit.low, limit.high) for moment, value in judged]
    low_env, high_env = figure.envelope
    out: list[tuple[dt.datetime, float, float | None, float | None]] = []
    for moment, value in judged:
        bounds = figure.bounds(_simultaneous(moment, pair))
        if bounds is not None:
            out.append((moment, value, *bounds))
        elif not low_env <= value <= high_env:
            out.append((moment, value, low_env, high_env))
        else:
            out.append((moment, value, None, None))
    return out


def excursions(readings: Iterable[HabitatReading]) -> list[Excursion]:
    """Intervalos fuera de limite, por modulo, parametro y tipo de limite."""
    grouped: dict[tuple[str, str], list[HabitatReading]] = {}
    for item in readings:
        grouped.setdefault((item.module, item.parameter), []).append(item)
    for series in grouped.values():
        series.sort(key=lambda item: item.effective)
    found: list[Excursion] = []
    for (module, key), series in sorted(grouped.items()):
        # Lo que solo se muestra no se juzga, lleve lo que lleve su ficha: sin limite leido no
        # hay excursion posible, con ningun valor.
        if key in DISPLAY_ONLY:
            continue
        spec = parameter(key)
        for limit in spec.limits:
            pair = grouped.get((module, limit.figure.pair), []) if limit.figure else []
            bounded = _bounded(limit, _judged(series, limit.averaging), pair)
            current: list[tuple[dt.datetime, float, float]] = []
            for moment, value, low, high in [*bounded, (None, None, None, None)]:
                excess = (
                    -math.inf if value is None else max(
                        (low - value) if low is not None else -math.inf,
                        (value - high) if high is not None else -math.inf,
                    )
                )
                if excess > 0:
                    assert moment is not None and value is not None
                    current.append((moment, value, excess))
                    continue
                if current:
                    # El peor es el que mas se aleja de SU extremo (en una figura, el extremo
                    # cambia de una lectura a otra).
                    worst = max(current, key=lambda item: item[2])[1]
                    found.append(Excursion(
                        module, key, limit.kind, limit.requirement,
                        current[0][0], current[-1][0], worst,
                    ))
                    current = []
    return found


def cabin_readings(readings: Iterable[HabitatReading]) -> list[HabitatReading]:
    """Las lecturas de la atmosfera de cabina (lo evaluado y la luz), sin agua ni microbiologia.

    Existe porque una muestra de agua o un recuento microbiano se declaran de vez en cuando y
    a destiempo: si contaran para el «ahora» de la cabina, una muestra firmada despues de la
    ultima lectura de cabina daria por cerrada una excursion vigente; si contaran como «hay
    lecturas de habitat», un contexto de alerta diria que la cabina se vigilo en parte cuando
    ningun parametro de cabina tenia lectura. Todo lo que pregunte por la cabina pasa por aqui.
    """
    return [item for item in readings if parameter(item.parameter).group == CABIN]


def latest_by_parameter(
    readings: Iterable[HabitatReading],
) -> dict[tuple[str, str], HabitatReading]:
    latest: dict[tuple[str, str], HabitatReading] = {}
    for item in readings:
        key = (item.module, item.parameter)
        if key not in latest or item.effective > latest[key].effective:
            latest[key] = item
    return latest


# --- Radiacion: se ensena en el habitat y no se evalua aqui (2026-10-26, ver la cabecera) -----
DOSE_RATE_KEY = "absorbed-dose-rate"
RADIATION_DISPLAY = "Radiación"
RADIATION_MODULE_TEXT = (
    "módulo sin declarar: la tasa de dosis llega como lectura de un tripulante, no de un módulo, "
    "y EMMA no sabe dónde está cada dosímetro"
)
RADIATION_NO_SHIELDING = (
    "Sin factores de blindaje: EMMA no modela una nave concreta ni el refugio de cada módulo, y "
    "cada cifra es la del dosímetro tal cual, sin corregir ni repartir por módulo."
)
RADIATION_NOT_EVALUATED = (
    "Se muestra y no se evalúa aquí: no da excursión de hábitat, hipótesis ni nivel. La tasa de "
    "dosis ya la evalúa el estado de cada tripulante como lectura suya, y el evento solar ya da "
    "su escala aguda."
)
DOSE_RATE_DISPLAY = "Tasa de dosis absorbida"
DOSE_RATE_BASIS = "la última lectura de cada tripulante, tal como está firmada en el registro"
DOSE_RATE_MISSING = "Ninguna lectura de tasa de dosis registrada."
# Lo que cada tripulante tiene de tasa de dosis y el estado aparta por su tipo (§5.39.11): quien
# solo la tiene inferida desaparecia de la lista de arriba sin una nota, y el resumen (que la
# capa del habitat de `/api/twins` repite como nota) callaba lo mismo.
DOSE_RATE_SET_ASIDE_DISPLAY = "Apartadas por su tipo"
SOLAR_DISPLAY = "Evento solar vigente"
SOLAR_SOURCE = "NASA DONKI, eventos de partículas solares (SEP)"
SOLAR_UNAVAILABLE = (
    "Sin datos de NASA DONKI: no se sabe si hay un evento de partículas solares vigente."
)
# Los estados del evento solar. La interfaz elige con ellos la marca, no la frase.
SOLAR_ACTIVE, SOLAR_NONE, SOLAR_UNKNOWN = "active", "none", "unavailable"
i18n.en_many({
    RADIATION_DISPLAY: "Radiation",
    RADIATION_MODULE_TEXT: (
        "module not declared: the dose rate arrives as a reading of a crew member, not of a "
        "module, and EMMA does not know where each dosimeter is"
    ),
    RADIATION_NO_SHIELDING: (
        "No shielding factors: EMMA does not model a specific spacecraft or the shelter of each "
        "module, and each figure is the dosimeter's as it is, neither corrected nor split by "
        "module."
    ),
    RADIATION_NOT_EVALUATED: (
        "Shown and not evaluated here: it gives no habitat excursion, hypothesis or level. The "
        "dose rate is already evaluated by each crew member's status as a reading of their "
        "own, and the solar event already gives its acute scale."
    ),
    DOSE_RATE_DISPLAY: "Absorbed dose rate",
    DOSE_RATE_BASIS: "the latest reading of each crew member, as it is signed in the ledger",
    DOSE_RATE_MISSING: "No dose rate reading recorded.",
    DOSE_RATE_SET_ASIDE_DISPLAY: "Set aside because of their type",
    SOLAR_DISPLAY: "Solar event in effect",
    SOLAR_SOURCE: "NASA DONKI, solar energetic particle (SEP) events",
    SOLAR_UNAVAILABLE: (
        "No data from NASA DONKI: it is not known whether a solar particle event is in effect."
    ),
})


def _dose_reading(item: VitalObservation) -> dict[str, Any]:
    """Una lectura de tasa de dosis con de donde sale: de quien es el dosimetro y que la envio."""
    return {
        "subject": item.subject,
        "value": item.value,
        # Los decimales declarados del indicador: la interfaz escribe la cifra como la frase.
        "decimals": display.decimals_for(item.key),
        "unit": item.code.unit,
        "effective": item.effective.isoformat(),
        "source": item.source,
        "device": item.device,
        "evidence_context": item.evidence_context.value if item.evidence_context else None,
        "observation_type": str(item.observation_type),
        "origin_text": i18n.tr(
            f"lectura del dosímetro de {item.subject} (fuente «{item.source}»)",
            f"reading from the dosimeter of {item.subject} (source “{item.source}”)",
        ),
        # Sin modulo (ver la cabecera): no se deduce de la ubicacion declarada del tripulante.
        "module": None,
    }


def _days(span: dt.timedelta) -> str:
    return display.number(span.total_seconds() / 86400, 0)


def _solar_text(
    event: SolarEvent | None,
    known: bool,
    relevance: dt.timedelta,
    stale_age: str | None = None,
) -> str:
    if not known:
        return i18n.loc(SOLAR_UNAVAILABLE)
    if event is None and stale_age is not None:
        # Datos caducados (una cache vieja o la instantanea del paquete, 2026-11-04): que no
        # registren un evento no dice que no lo haya en los ultimos dias, que no cubren.
        return i18n.tr(
            f"Los datos de NASA DONKI que hay están caducados ({stale_age}): no cubren los "
            f"últimos {_days(relevance)} días y no se sabe si hay un evento de partículas "
            "solares vigente.",
            f"The NASA DONKI data at hand are stale ({stale_age}): they do not cover the last "
            f"{_days(relevance)} days and it is not known whether a solar particle event is in "
            "effect.",
        )
    if event is None:
        return i18n.tr(
            "Ningún evento de partículas solares de severidad alta o grave en NASA DONKI en los "
            f"últimos {_days(relevance)} días.",
            "No solar particle event of high or severe severity in NASA DONKI in the last "
            f"{_days(relevance)} days.",
        )
    return i18n.tr(
        f"{event.event_type} {event.event_id}, del "
        f"{event.time.astimezone(dt.UTC):%Y-%m-%d %H:%M} UTC, según NASA DONKI.",
        f"{event.event_type} {event.event_id}, of "
        f"{event.time.astimezone(dt.UTC):%Y-%m-%d %H:%M} UTC, according to NASA DONKI.",
    )


def _latest_text(event: SolarEvent) -> str:
    return i18n.tr(
        f"Último evento de partículas solares en esos datos de NASA DONKI: {event.event_type} "
        f"{event.event_id}, del {event.time.astimezone(dt.UTC):%Y-%m-%d %H:%M} UTC; no está "
        "vigente.",
        f"Latest solar particle event in those NASA DONKI data: {event.event_type} "
        f"{event.event_id}, of {event.time.astimezone(dt.UTC):%Y-%m-%d %H:%M} UTC; it is not "
        "in effect.",
    )


def radiation_state(
    latest_dose: Sequence[VitalObservation],
    active_event: SolarEvent | None,
    solar_known: bool,
    solar_age: tuple[str, float] | None,
    solar_freshness: dict[str, Any],
    relevance: dt.timedelta,
    set_aside: Sequence[dict[str, Any]] = (),
    set_aside_rule: str | None = None,
    latest_recorded: SolarEvent | None = None,
) -> dict[str, Any]:
    """La radiacion del estado del habitat: la ultima tasa de dosis de cada dosimetro y el
    evento solar vigente, cada cifra con de donde sale.

    Solo compone: `latest_dose` es la ultima lectura de cada tripulante y `active_event` el que
    ya eligio el motor de riesgo para el estado (`solar_known` en falso si DONKI no respondio ni
    habia cache). `set_aside` es lo que cada tripulante tiene de tasa de dosis y el estado no
    lee por su tipo, ya contado y redactado por quien conoce la regla (`api/habitat.py`, con
    `subject` y `text`): aqui solo se lista y entra en el resumen, para que quien hereda el
    resumen (`/api/twins`) diga lo mismo. Nada de aqui vuelve al motor: no hay limite,
    excursion ni nivel.

    `latest_recorded` es el SEP mas reciente de esos datos de DONKI aunque no este vigente
    (2026-11-04): sin red, el de la instantanea del paquete, con su fecha real. Solo se ensena
    sin evento vigente, y dice que no lo esta; no entra en nada mas.
    """
    readings = [_dose_reading(item) for item in sorted(latest_dose, key=lambda o: o.subject)]
    stale_age = (
        solar_age[0] if solar_age is not None and not solar_freshness.get("is_current", True)
        else None
    )
    if not solar_known or (active_event is None and stale_age is not None):
        state = SOLAR_UNKNOWN
    else:
        state = SOLAR_ACTIVE if active_event is not None else SOLAR_NONE
    solar_text = _solar_text(active_event, solar_known, relevance, stale_age)
    shown_latest = latest_recorded if active_event is None and solar_known else None
    if readings:
        listed = "; ".join(
            f"{item['subject']} {display.quantity(DOSE_RATE_KEY, item['value'], item['unit'])}"
            for item in readings
        )
        dose_summary = i18n.tr(
            f"{DOSE_RATE_DISPLAY}, última lectura de cada dosímetro ({RADIATION_MODULE_TEXT}; "
            f"sin factores de blindaje): {listed}.",
            f"{i18n.loc(DOSE_RATE_DISPLAY)}, latest reading of each dosimeter "
            f"({i18n.loc(RADIATION_MODULE_TEXT)}; no shielding factors): {listed}.",
        )
    else:
        dose_summary = i18n.tr(
            f"{DOSE_RATE_DISPLAY}: ninguna lectura registrada.",
            f"{i18n.loc(DOSE_RATE_DISPLAY)}: no reading recorded.",
        )
    # La regla la redacta quien la conoce (`analysis/alert_support.py`): aqui solo se sirve.
    if set_aside_rule is not None:
        set_aside_rule = i18n.loc(set_aside_rule)
    aside = sorted(set_aside, key=lambda item: str(item["subject"]))
    if aside:
        # En el resumen va cada tripulante con su frase: la nota del gemelo no tiene otra via.
        dose_summary += " " + " ".join(f"{item['subject']}: {item['text']}." for item in aside)
    return {
        "display": i18n.loc(RADIATION_DISPLAY),
        "module": None,
        "module_text": i18n.loc(RADIATION_MODULE_TEXT),
        "shielding": i18n.loc(RADIATION_NO_SHIELDING),
        "evaluated": False,
        "note": i18n.loc(RADIATION_NOT_EVALUATED),
        "dose_rate": {
            "key": DOSE_RATE_KEY,
            "display": i18n.loc(DOSE_RATE_DISPLAY),
            "basis": i18n.loc(DOSE_RATE_BASIS),
            "readings": readings,
            "missing_text": None if readings else i18n.loc(DOSE_RATE_MISSING),
            # Quien tiene tasa de dosis que el estado no lee por su tipo, cuantas y de que tipo,
            # con la frase de quien la aparta; y la regla, en palabras, cuando hay algo apartado.
            "set_aside_display": i18n.loc(DOSE_RATE_SET_ASIDE_DISPLAY),
            "set_aside": aside,
            "set_aside_rule": set_aside_rule if aside else None,
        },
        "solar_event": {
            "display": i18n.loc(SOLAR_DISPLAY),
            "state": state,
            "text": solar_text,
            "event": active_event.to_dict() if active_event is not None else None,
            "source": i18n.loc(SOLAR_SOURCE),
            "data_age": solar_age[0] if solar_age else None,
            "data_age_seconds": solar_age[1] if solar_age else None,
            "freshness": solar_freshness,
            "latest_recorded": (
                {**shown_latest.to_dict(), "text": _latest_text(shown_latest)}
                if shown_latest is not None else None
            ),
            "basis": i18n.tr(
                "el evento de partículas solares de severidad alta o grave más reciente de los "
                f"últimos {_days(relevance)} días, el mismo que da la escala aguda del estado de "
                "cada tripulante",
                "the most recent solar particle event of high or severe severity in the last "
                f"{_days(relevance)} days, the same one that gives the acute scale of each crew "
                "member's status",
            ),
        },
        "summary": f"{dose_summary} {i18n.loc(SOLAR_DISPLAY)}: {solar_text}",
    }
