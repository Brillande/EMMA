"""Modelo canonico de datos: FHIR R4B `Observation`.

Todo lo que entra al sistema —simulador, wearable, dosimetro, test PVT— se
normaliza aqui. Es lo que permite que fuentes heterogeneas alimenten exactamente
el mismo motor de analisis sin ramas especiales por origen.

Nota de version: se usa **R4B**, la release de mantenimiento de R4 y la que expone
`fhir.resources` 8.x. Es compatible con R4 para el perfil Vital Signs.

`VitalObservation` es una representacion interna ligera: instanciar objetos FHIR
completos para cada muestra de una serie de 10 s seria caro sin aportar nada. La
conversion a FHIR real ocurre en los limites del sistema (API, exportacion,
auditoria), y `to_fhir()` produce un recurso que valida contra el esquema.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.ingest.codes import (
    CATALOG,
    LAB_REPORT_ONLY,
    ULTRASOUND_MEASURES,
    CodeSystem,
    Domain,
    NoCategory,
    ObservationCategory,
    VitalCode,
    current_system,
    get,
)
from app.ingest.food_item import KEYS as FOOD_ITEM_KEYS

UCUM_SYSTEM = "http://unitsofmeasure.org"
# La especificación de UCUM leída (ficha en `data/evidence_refs.json`): de ella sale que el código
# distingue mayúsculas y que el litro tiene dos grafías, lo que `require_catalog_unit` no iguala.
UCUM_REF = "ucum-2-2"
CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"
# La definición de `Observation.focus` en FHIR R4B, leída (ficha en `data/evidence_refs.json`):
# el foco puede ser «the subject's diet», y ahí va el alimento de una valoración de la comida.
FOCUS_REF = "hl7-fhir-r4b-observation"

# Como se nombra cada categoria en el sistema de codigos oficial (su `display`).
CATEGORY_DISPLAY: dict[ObservationCategory, str] = {
    ObservationCategory.SOCIAL_HISTORY: "Social History",
    ObservationCategory.VITAL_SIGNS: "Vital Signs",
    ObservationCategory.IMAGING: "Imaging",
    ObservationCategory.LABORATORY: "Laboratory",
    ObservationCategory.PROCEDURE: "Procedure",
    ObservationCategory.SURVEY: "Survey",
    ObservationCategory.EXAM: "Exam",
    ObservationCategory.THERAPY: "Therapy",
    ObservationCategory.ACTIVITY: "Activity",
}

# Categoria FHIR por dominio clinico, para el indicador que no declara la suya
# (`VitalCode.category`). Solo los signos vitales clasicos son "vital-signs"; el resto son
# "survey" (autoinforme, PVT) o "exam"/"laboratory". Lo que no es lo tipico de su dominio la
# declara en el catalogo, junto al indicador y con su motivo (decimoctava ronda, §5.38.9): antes
# era una tabla aparte por clave, y el peso, la orina de 24 h y la carga de sintomas se quedaron
# fuera de ella con la categoria de su dominio.
_CATEGORY_BY_DOMAIN: dict[Domain, ObservationCategory] = {
    Domain.CARDIOVASCULAR: ObservationCategory.VITAL_SIGNS,
    Domain.BEHAVIORAL: ObservationCategory.SURVEY,
    Domain.RADIATION: ObservationCategory.EXAM,
    Domain.BONE: ObservationCategory.ACTIVITY,
    Domain.IMMUNE: ObservationCategory.LABORATORY,
    Domain.NEURO_OCULAR: ObservationCategory.IMAGING,
    Domain.GENITOURINARY: ObservationCategory.IMAGING,
    # Autoinforme de la tripulacion, como el estado de animo.
    Domain.MUSCULOSKELETAL: ObservationCategory.SURVEY,
    Domain.NUTRITION: ObservationCategory.SURVEY,
}


def category_of(code: VitalCode) -> ObservationCategory | None:
    """La categoría FHIR de un indicador: lo que es la medida, no el dominio en que se agrupa.

    `None` si ninguna de las nueve lo describe (`NoCategory.NONE_FITS`): el recurso va sin
    categoría. En orden: la declarada en el catálogo; imagen para una medida ecográfica (con
    "vital-signs" quedaría sujeta al perfil de signos vitales, que no la admite, aunque su
    dominio sea cardiovascular); laboratorio para un analito de analítica (`LAB_REPORT_ONLY`: el
    calcio del óseo salía «activity», el sodio del genitourinario «imaging» y la glucosa de
    nutrición «survey»); y si no, la de su dominio. La categoría solo vive en el recurso FHIR
    que se sirve: no se firma en el asiento ni entra en la huella de las reglas.
    """
    if isinstance(code.category, NoCategory):
        return None
    if code.category is not None:
        return code.category
    if code.key in ULTRASOUND_MEASURES:
        return ObservationCategory.IMAGING
    if code.key in LAB_REPORT_ONLY:
        return ObservationCategory.LABORATORY
    return _CATEGORY_BY_DOMAIN[code.domain]


def fhir_category(code: VitalCode) -> tuple[str, str] | None:
    """El código y el `display` oficiales de su categoría, o `None` si no lleva."""
    category = category_of(code)
    return None if category is None else (category.value, CATEGORY_DISPLAY[category])


class CatalogUnit(Protocol):
    """Lo que necesita la comparación de unidad: la clave y la unidad UCUM de un catálogo.

    La cumplen un indicador (`VitalCode`) y un parámetro de cabina
    (`environment.habitat.HabitatParameter`): las dos ingestas manuales comparan igual.
    """

    @property
    def key(self) -> str: ...

    @property
    def unit(self) -> str: ...


class Context(StrEnum):
    """Estado fisiologico en que se tomo la medida.

    Existe porque la validacion externa contra MMASH demostro que **la linea base
    es ciega al estado**. En 24 h de un sujeto sano el pulso recorrio 59-128 lpm
    —68 lpm de amplitud circadiana— mientras la dispersion de su linea base era de
    11 lpm. Comparar una lectura despierto contra una referencia construida
    mientras dormia la deja a seis sigmas por pura fisiologia normal.

    Con el contexto declarado, la base se estratifica y compara estados
    comparables. Ver `compliance/external-validation.md`.

    GRANULARIDAD: POR QUE NO BASTA reposo/actividad
    -----------------------------------------------
    La primera version tenia tres estados y `rest` seguia siendo el que mas
    alarmaba (8,1 %, frente al 1,1 % de `active`). Medido en MMASH, dentro de
    "reposo" la mediana de pulso iba de **58 a 80 lpm segun la subactividad**
    —pantalla 71, laboral 76, comer 80—, es decir 22 lpm de dispersion entre
    subestados cuando la dispersion de la propia linea base era de 11 lpm.
    Agrupar estados que difieren mas que el ruido garantiza falsas alarmas al
    cambiar de tarea.

    Los estados se eligen para que una **agenda de mision** los cubra: dormir,
    descanso, trabajo, comida y ejercicio son bloques de horario reales, no
    categorias inventadas para este dataset.
    """

    UNKNOWN = "unknown"
    SLEEP = "sleep"
    REST = "rest"
    # Tarea concentrada: demanda cognitiva sin esfuerzo fisico apreciable.
    WORK = "work"
    # Postprandial: la subida de pulso tras comer es un fenomeno real, no ruido.
    MEAL = "meal"
    ACTIVE = "active"

    @property
    def family(self) -> Context:
        """Agrupacion gruesa, para cuando el estado fino no tiene datos.

        Estratificar fino mejora la comparacion pero **fragmenta la muestra**: un
        evento agudo puede caer en un grupo sin base establecida y volverse
        invisible. Ocurrio: al pasar de tres estados a cinco, la deteccion del
        episodio agudo cayo del 90 % al 20 %.

        La familia da el escalon intermedio: si el estado exacto no tiene
        suficientes lecturas, se compara contra el grupo al que pertenece antes
        de caer al rango poblacional.
        """
        if self in {Context.REST, Context.WORK, Context.MEAL}:
            return Context.REST
        return self


# Confianza por defecto: la medida se acepta tal cual mientras nadie diga lo
# contrario. El adaptador de wearable la baja cuando el sensor declara mal
# contacto, y el analisis exige mas evidencia para marcar una lectura dudosa.
FULL_CONFIDENCE = 1.0

# Por debajo de esto una lectura no basta por si sola para generar un hallazgo.
# El error del PPG es ~30 % mayor durante actividad y varia 3x entre
# dispositivos; una lectura sin contacto de sensor no puede pesar igual que una
# tomada en reposo con buen contacto.
LOW_CONFIDENCE_THRESHOLD = 0.5

EXTENSION_CONTEXT = "https://emma.mission/fhir/context"
EXTENSION_CONFIDENCE = "https://emma.mission/fhir/confidence"
EXTENSION_OBSERVATION_TYPE = "https://emma.mission/fhir/observation-type"
EXTENSION_EVIDENCE_CONTEXT = "https://emma.mission/fhir/evidence-context"
EXTENSION_MODEL_VERSION = "https://emma.mission/fhir/model-version"

# Hasta 2026-11-02 las extensiones vivian bajo `https://halo.mission/fhir/`, y asi van en lo
# firmado antes. Se leen como las de hoy (`_current_extension`); se escriben siempre las de hoy.
FORMER_EXTENSION_PREFIX = "https://halo.mission/fhir/"
EXTENSION_PREFIX = "https://emma.mission/fhir/"


def _current_extension(url: str) -> str:
    """La URL de hoy para una extension leida de un registro, que puede llevar la de antes."""
    if url.startswith(FORMER_EXTENSION_PREFIX):
        return EXTENSION_PREFIX + url.removeprefix(FORMER_EXTENSION_PREFIX)
    return url


class ObservationType(StrEnum):
    """Que clase de afirmacion es el valor: medido, inferido o predicho.

    La especificacion del equipo (`docs/contexto/`, §2 y §14) lo exige en todo dato:
    "incertidumbre primero". Una dosis efectiva calculada o una deriva extrapolada
    presentadas con el mismo aspecto que una lectura de sensor afirman mas de lo que
    se sabe. Sin esta etiqueta la interfaz no tenia forma de distinguirlas.
    """

    # Salida directa de un sensor, de un test o de un autoinforme.
    MEASURED = "measured"
    # Estimada por un modelo a partir de otras medidas (p. ej. dosis efectiva con Q).
    INFERRED = "inferred"
    # Proyectada hacia el futuro (p. ej. la deriva de una tendencia).
    PREDICTED = "predicted"


class EvidenceContext(StrEnum):
    """En que entorno se obtuvo el dato (el del estudio o despliegue que lo produjo).

    La base de conocimiento (§3.1, "misiones analogas: considerar variables") prohibe
    mezclar sin etiqueta un dato de la ISS, de un reposo en cama o de un voluntario en
    Tierra: cada entorno reproduce unas condiciones y deja fuera otras.
    """

    ISS = "iss"
    # Estudio de un vuelo real fuera de la ISS (Inspiration4, orbita libre de 3 dias).
    # Es el entorno del ESTUDIO: sus tomas L-/R+ se hicieron en Tierra antes y despues
    # del vuelo, y eso lo dice la fase de la toma, no esta etiqueta.
    SPACEFLIGHT = "spaceflight"
    ANALOG_BEDREST = "analog_bedrest"
    ANALOG_ISOLATION = "analog_isolation"
    # Persona en Tierra fuera de un analogo: MMASH, o un wearable real hoy.
    GROUND = "ground"
    SIMULATED = "simulated"


def evidence_context_for(source: str) -> EvidenceContext:
    """Contexto que corresponde a una fuente cuando nadie lo declaro.

    Solo para asientos anteriores a que el payload llevara el campo: cada via de
    ingesta nueva lo declara. Inspiration4 se firma con la identidad del simulador
    (`simulator:inspiration4`) pero sus valores son analiticas reales de vuelo.
    """
    if source == "simulator:inspiration4":
        return EvidenceContext.SPACEFLIGHT
    if source.startswith("simulator:"):
        return EvidenceContext.SIMULATED
    return EvidenceContext.GROUND


def require_catalog_unit(code: CatalogUnit, unit: object) -> None:
    """Rechaza una cifra que llega declarada en una unidad distinta de la del catálogo.

    La comparten todas las vías que reciben una cifra con su unidad: el recurso FHIR
    (`valueQuantity.code`, en `VitalObservation.from_fhir`), el alta manual
    (`POST /api/observations` y su enmienda, campo `unit`), el adaptador del contrato de §5
    (`POST /api/import/observations`, `api/spec5.py`, que traduce al alta manual y pasa por
    sus mismas comprobaciones), la confirmación de una analítica
    escaneada (`reports/labs.confirmed_value`, que añade al motivo lo que puede hacer la persona
    con el papel delante) y la lectura de cabina manual (`POST /api/habitat`, contra la unidad
    del parámetro). Antes el alta manual no tenía campo de unidad, y una cifra en nmol/L entraba
    como si estuviera en ng/mL; la analítica y la cabina tenían cada una su comparación o
    ninguna.

    No convierte, a propósito (invariante 2): LOINC separa masa y sustancia por volumen con
    códigos distintos, así que una vitamina D en ng/mL y otra en nmol/L no son el mismo dato en
    otra escala, sino dos indicadores. Convertir en silencio guardaría la cifra bajo un código
    cuya propiedad no es la de la medida. La comparación es literal sobre el código UCUM, que
    distingue mayúsculas: aquí «ml» no es «mL», aunque UCUM acepte las dos grafías del litro
    (`UCUM_REF`, §31). Ni se convierte ni se normaliza la grafía.
    """
    if unit == code.unit:
        return
    # Vacía no es lo mismo que ausente: quien la omite deja que se asuma la del catálogo y se le
    # dice; quien la manda vacía no ha dicho ninguna, y repetir «llega ''» no le explica nada.
    if unit == "":
        raise ValueError(
            f"unidad vacía para {code.key}: el catálogo define {code.unit!r}; si no se conoce, "
            "no se declara"
        )
    # La unidad recibida se repite recortada, sea texto o no (un recurso FHIR puede traer una
    # lista): una de 500 KB no vuelve entera en el error. El corte se marca con «…», para que
    # quien lee no tome por recibida una unidad a la que le falta el final.
    shown = repr(unit)
    if len(shown) > 40:
        shown = shown[:40] + "…"
    raise ValueError(
        f"unidad incompatible para {code.key}: llega {shown}, el catálogo define "
        f"{code.unit!r}. EMMA no convierte unidades: una cifra en otra unidad no se registra"
    )


@dataclass(frozen=True, slots=True)
class VitalObservation:
    """Una medicion puntual de un indicador, ya normalizada."""

    code: VitalCode
    value: float
    effective: datetime
    subject: str
    source: str
    context: Context = Context.UNKNOWN
    confidence: float = FULL_CONFIDENCE
    observation_type: ObservationType = ObservationType.MEASURED
    # None solo al construir: se resuelve desde `source` en `__post_init__`.
    evidence_context: EvidenceContext | None = None
    # Que modelo produjo el valor. Obligatorio si no es una medida: un valor inferido
    # o predicho sin decir con que se calculo no se puede reproducir ni auditar.
    model_version: str | None = None
    # EL IDENTIFICADOR DEL DISPOSITIVO, SI QUIEN ENVIA LO PUSO (decision del usuario,
    # 2026-10-13).
    #
    # Sin el, el aviso de «sensor vinculado a otro tripulante» (`ingest/bindings.py`) solo
    # existia en la respuesta de la ingesta: nadie podia reconstruirlo despues, y la consola
    # ensenaba esas lecturas como las demas. Es OPCIONAL y solo se serializa cuando existe: una
    # lectura sin dispositivo se firma byte a byte como antes de este campo. No entra en el
    # analisis: ningun modulo de `analysis/` que decide lo lee (invariante 5). Puede ser un dato
    # personal (una direccion MAC): se firma en el registro y no se escribe en el log.
    device: str | None = None
    # QUIEN TECLEO EL VALOR, SI LO ANOTO UNA PERSONA EN LA CONSOLA (decision del usuario,
    # 2026-10-13).
    #
    # `subject` dice de que tripulante es el dato; no dice quien lo escribio. En el registro
    # diario y en la PVT hecha en pantalla lo teclea el operador de la consola, que puede no
    # ser el tripulante. Es OPCIONAL y solo se serializa cuando existe, como `device`: una
    # lectura sin el se firma byte a byte como antes. Es un nombre DECLARADO, no una identidad
    # autenticada. No entra en el analisis (invariante 5) y, como dato personal, se firma en
    # el registro y no se escribe en el log.
    recorded_by: str | None = None
    # DE QUÉ ALIMENTO ES LA VALORACIÓN (decisión del usuario, 2026-10-26).
    #
    # Solo la aceptabilidad de la comida y, desde el 2026-10-31, la fracción que se deja sin
    # comer lo llevan (`food_item.KEYS`): sin él no se podía decir cuántas veces se valoró un
    # plato ni cómo fue su valoración en el tiempo. Es OPCIONAL y
    # solo se serializa cuando existe, como `device` y `recorded_by`: una lectura sin alimento
    # se firma byte a byte como antes. Texto libre con la regla de `ingest/food_item.py`, que
    # aplica la ruta que firma; aquí solo se exige lo estructural, para que un cambio de la
    # regla no deje sin leer lo ya firmado. No entra en el análisis (invariante 5).
    food: str | None = None

    def __post_init__(self) -> None:
        if self.food is not None:
            if not isinstance(self.food, str) or not self.food or self.food != self.food.strip():
                raise ValueError(
                    f"{self.code.key}: el alimento, si se da, es un texto no vacío y sin "
                    "espacios en los bordes; una lectura sin alimento no lleva el campo"
                )
            if self.code.key not in FOOD_ITEM_KEYS:
                raise ValueError(
                    f"{self.code.key}: solo la aceptabilidad de la comida y la fracción "
                    "rechazada llevan alimento"
                )
        if self.recorded_by is not None and (
            not isinstance(self.recorded_by, str) or not self.recorded_by.strip()
        ):
            raise ValueError(
                f"{self.code.key}: quien anota, si se da, es un nombre no vacío; una lectura "
                "que no anotó una persona no lleva el campo"
            )
        if self.device is not None and (not isinstance(self.device, str) or not self.device):
            raise ValueError(
                f"{self.code.key}: el identificador de dispositivo, si se da, es un texto "
                "no vacío; una lectura sin dispositivo no lleva el campo"
            )
        if self.evidence_context is None:
            object.__setattr__(self, "evidence_context", evidence_context_for(self.source))
        if self.observation_type is not ObservationType.MEASURED and not self.model_version:
            raise ValueError(
                f"{self.code.key}: un valor {self.observation_type} tiene que declarar "
                f"el modelo que lo produjo (`model_version`)"
            )

        if self.effective.tzinfo is None:
            raise ValueError(
                "`effective` debe llevar zona horaria: una marca de tiempo ambigua "
                "rompe la trazabilidad exigida por 21 CFR 11.10(e)"
            )

        # La confianza es una fraccion de 0 a 1. La API la acotaba y el modelo no: por
        # `from_fhir` o por codigo entraba un NaN, y como `NaN < 0,5` es falso la lectura
        # pasaba por de confianza plena (`is_low_confidence`).
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError(
                f"{self.code.key}: confianza {self.confidence!r} fuera de 0..1"
            )

        # NaN ATRAVESABA EL SISTEMA EN SILENCIO.
        #
        # Toda comparacion con NaN es falsa, asi que ni los cuantiles ni los
        # limites de peligro lo veian: la lectura desaparecia sin dejar rastro ni
        # alerta. En monitorizacion clinica, un dato que se esfuma sin avisar es
        # peor que uno que da error.
        if not math.isfinite(self.value):
            raise ValueError(
                f"{self.code.key}: valor no finito ({self.value}). Un dato así "
                f"atraviesa las comparaciones sin disparar nada"
            )

        # Un valor fisicamente imposible es un sensor roto, no una urgencia.
        if not self.code.is_physically_possible(self.value):
            raise ValueError(
                f"{self.code.key}: {self.value} {self.code.unit} está fuera de lo "
                f"físicamente posible ({self.code.physical_min}.."
                f"{self.code.physical_max}). Es un fallo de medida, no un hallazgo"
            )

    # ----------------------------------------------------------------- #

    @property
    def key(self) -> str:
        return self.code.key

    @property
    def domain(self) -> Domain:
        return self.code.domain

    @property
    def evidence(self) -> EvidenceContext:
        """El contexto ya resuelto (nunca None tras construir)."""
        assert self.evidence_context is not None
        return self.evidence_context

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < LOW_CONFIDENCE_THRESHOLD

    def to_fhir(self) -> dict[str, Any]:
        """Recurso FHIR R4B Observation como dict serializable."""
        category = fhir_category(self.code)
        return {
            "resourceType": "Observation",
            "status": "final",
            # `Observation.category` es 0..*: el indicador que ninguna categoria describe va sin
            # la clave, en vez de con una que no es la suya.
            **(
                {
                    "category": [
                        {
                            "coding": [
                                {
                                    "system": CATEGORY_SYSTEM,
                                    "code": category[0],
                                    "display": category[1],
                                }
                            ]
                        }
                    ]
                }
                if category is not None else {}
            ),
            "code": {
                "coding": [
                    {
                        "system": str(self.code.system),
                        "code": self.code.code,
                        "display": self.code.display,
                    }
                ],
                "text": self.code.display,
            },
            "subject": {"reference": f"Patient/{self.subject}"},
            "effectiveDateTime": self.effective.astimezone(UTC).isoformat(),
            "valueQuantity": {
                "value": self.value,
                "unit": self.code.unit,
                "system": UCUM_SYSTEM,
                "code": self.code.unit,
            },
            # `Observation.device` es una referencia (`Reference(Device)`), y una referencia
            # FHIR admite un identificador logico (`Reference.identifier`) cuando no hay un
            # recurso `Device` al que apuntar: es el caso. El identificador va sin `system`:
            # EMMA no sabe que clase de identificador puso quien envia (una MAC, una etiqueta),
            # y declarar un sistema seria inventarlo. Sin dispositivo, el campo queda como antes.
            "device": {
                "display": self.source,
                **({"identifier": {"value": self.device}} if self.device is not None else {}),
            },
            # `Observation.performer` («quien responde de la observacion») es una lista de
            # referencias, y una referencia FHIR puede llevar solo `display` cuando no hay un
            # recurso al que apuntar: EMMA no tiene recursos `Practitioner` ni un sistema de
            # identificadores de operadores, y el nombre es lo declarado. Sin `reference` ni
            # `identifier`: ponerlos seria inventarlos. Sin anotador, la clave no existe.
            **(
                {"performer": [{"display": self.recorded_by}]}
                if self.recorded_by is not None else {}
            ),
            # `Observation.focus` («what the observation is about, when it is not about the
            # subject of record»): FHIR R4B pone «the subject's diet» entre sus ejemplos
            # (`FOCUS_REF`). Es una lista de referencias de cualquier recurso, y EMMA no tiene un
            # recurso del alimento al que apuntar: solo `display`, el nombre firmado, sin
            # `reference` ni `identifier` (serían inventados). Sin alimento, la clave no existe.
            **({"focus": [{"display": self.food}]} if self.food is not None else {}),
            # FHIR permite extensiones propias con URL propia. Es la via
            # correcta para metadatos que el estandar no contempla; inventar un
            # campo en la raiz del recurso lo invalidaria.
            "extension": [
                {"url": EXTENSION_CONTEXT, "valueCode": str(self.context)},
                {"url": EXTENSION_CONFIDENCE, "valueDecimal": self.confidence},
                {"url": EXTENSION_OBSERVATION_TYPE, "valueCode": str(self.observation_type)},
                {"url": EXTENSION_EVIDENCE_CONTEXT, "valueCode": str(self.evidence)},
                *(
                    [{"url": EXTENSION_MODEL_VERSION, "valueString": self.model_version}]
                    if self.model_version
                    else []
                ),
            ],
        }

    @classmethod
    def from_fhir(cls, resource: dict[str, Any]) -> VitalObservation:
        """Reconstruye una observacion interna desde un recurso FHIR."""
        if resource.get("resourceType") != "Observation":
            raise ValueError(f"se esperaba Observation, llegó {resource.get('resourceType')!r}")

        coding = resource["code"]["coding"][0]
        code = _lookup_by_coding(coding["system"], coding["code"])
        quantity = resource["valueQuantity"]

        require_catalog_unit(code, quantity.get("code"))

        subject_ref = resource["subject"]["reference"]
        extensions = {
            _current_extension(item["url"]): item
            for item in resource.get("extension", []) if "url" in item
        }
        raw_context = extensions.get(EXTENSION_CONTEXT, {}).get("valueCode")
        raw_confidence = extensions.get(EXTENSION_CONFIDENCE, {}).get("valueDecimal")
        raw_type = extensions.get(EXTENSION_OBSERVATION_TYPE, {}).get("valueCode")
        raw_evidence = extensions.get(EXTENSION_EVIDENCE_CONTEXT, {}).get("valueCode")

        return cls(
            code=code,
            value=float(quantity["value"]),
            effective=datetime.fromisoformat(resource["effectiveDateTime"]),
            subject=subject_ref.removeprefix("Patient/"),
            source=resource.get("device", {}).get("display", "unknown"),
            context=Context(raw_context) if raw_context else Context.UNKNOWN,
            confidence=float(raw_confidence) if raw_confidence is not None else FULL_CONFIDENCE,
            observation_type=(
                ObservationType(raw_type) if raw_type else ObservationType.MEASURED
            ),
            evidence_context=EvidenceContext(raw_evidence) if raw_evidence else None,
            model_version=extensions.get(EXTENSION_MODEL_VERSION, {}).get("valueString"),
            device=resource.get("device", {}).get("identifier", {}).get("value"),
            recorded_by=(resource.get("performer") or [{}])[0].get("display"),
            food=(resource.get("focus") or [{}])[0].get("display"),
        )

    def validates(self) -> bool:
        """Comprueba el recurso contra el esquema FHIR R4B real.

        Es una operacion cara (construye el modelo Pydantic completo), asi que se
        usa en pruebas y en los limites del sistema, no por muestra.
        """
        from fhir.resources.R4B.observation import Observation as FhirObservation

        FhirObservation.model_validate(self.to_fhir())
        return True


def deployed(
    observations: list[VitalObservation], where: EvidenceContext
) -> list[VitalObservation]:
    """Declara el entorno de lecturas reales con el del despliegue.

    Un pulsometro no sabe si va en la ISS o en un laboratorio: lo sabe quien despliega
    el sistema (`Settings.deployment_context`). Lo simulado se queda como esta.
    """
    return [
        obs if obs.evidence is EvidenceContext.SIMULATED or obs.source.startswith("simulator:")
        else replace(obs, evidence_context=where)
        for obs in observations
    ]


def from_device(
    observations: list[VitalObservation], device: str | None
) -> list[VitalObservation]:
    """Las mismas lecturas con el identificador del dispositivo que las envio, si lo hay.

    Lo usan las tres rutas de ingesta de wearables, justo antes de firmar. Sin identificador
    devuelve las lecturas tal cual: no se escribe un campo vacio (lo firmado no cambia).
    """
    if device is None:
        return observations
    return [replace(obs, device=device) for obs in observations]


def annotated_by(
    observations: list[VitalObservation], operator: str
) -> list[VitalObservation]:
    """Las mismas lecturas con el nombre de quien las tecleo en la consola.

    Lo usa la PVT hecha en pantalla, justo antes de firmar: la puntuacion construye las
    lecturas sin saber quien paso la prueba.
    """
    return [replace(obs, recorded_by=operator) for obs in observations]


def _lookup_by_coding(system: str, code: str) -> VitalCode:
    for candidate in CATALOG.values():
        if str(candidate.system) == current_system(system) and candidate.code == code:
            return candidate
    raise KeyError(f"código no reconocido: {system}|{code}")


def observation(
    key: str,
    value: float,
    effective: datetime,
    subject: str,
    source: str,
    context: Context = Context.UNKNOWN,
    confidence: float = FULL_CONFIDENCE,
    observation_type: ObservationType = ObservationType.MEASURED,
    evidence_context: EvidenceContext | None = None,
    model_version: str | None = None,
    device: str | None = None,
    recorded_by: str | None = None,
    food: str | None = None,
) -> VitalObservation:
    """Atajo de construccion desde la clave del catalogo."""
    return VitalObservation(
        code=get(key), value=value, effective=effective, subject=subject,
        source=source, context=context, confidence=confidence,
        observation_type=observation_type, evidence_context=evidence_context,
        model_version=model_version, device=device,
        recorded_by=recorded_by,
        food=food,
    )


__all__ = [
    "CodeSystem",
    "Context",
    "EvidenceContext",
    "ObservationType",
    "VitalObservation",
    "annotated_by",
    "deployed",
    "evidence_context_for",
    "from_device",
    "observation",
    "require_catalog_unit",
]
