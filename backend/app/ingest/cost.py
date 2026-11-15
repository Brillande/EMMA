"""Coste de medir cada indicador (base de conocimiento §9, "coste de medicion").

Un biomarcador excelente que exige sangre, centrifuga y un laboratorio vale para entrenar y
validar modelos, no para vigilar a diario en Marte. Cada indicador dice que hace falta para
obtenerlo y cuanto tiempo de tripulacion cuesta. La clase es una clasificacion descriptiva de
EMMA; el tiempo solo lleva cifra si tiene fuente (`app/data/measurement_cost.json`).

LAS DIMENSIONES DEL COSTE: DÓNDE SE PROCESA, CUÁNDO LLEGA Y SI GASTA CONSUMIBLES
--------------------------------------------------------------------------------
La base de conocimiento y la conversación de ideación piden de cada medida algo más que el
equipo y el tiempo: dónde se procesa, si depende de Tierra, si el resultado es inmediato y si
gasta consumibles. Son tres clases descriptivas de vocabulario cerrado (`DIMENSIONS`).

NO SE CLASIFICA A OJO. Un «a bordo» puesto por intuición es una cifra inventada con otro
nombre. Cada valor sale de una REGLA escrita en `measurement_cost.json` (`dimension_rules`),
que dice a qué indicadores aplica —por su `mode`, su `equipment` o su clave— y en qué texto del
repositorio se apoya (`basis`). Lo que ninguna regla alcanza queda «sin clasificar», y el total
se publica: es la lista de lo que alguien tiene que decidir con una fuente delante. Por eso
«a bordo, con analizador» existe en el vocabulario y hoy no lo lleva ningún indicador: lo leído
de analizadores en la ISS son demostraciones tecnológicas y una sesión de estudio, no el
procedimiento de uso ordinario, y se enseñan como discrepancias de la regla de sangre.

DESDE LA UNDÉCIMA RONDA, LO LEÍDO
---------------------------------
Una regla puede apoyarse, además de en su `basis`, en frases leídas en una fuente oficial
(`sources`): la frase exacta, el sitio del documento, la ficha del registro de evidencia
(`data/evidence_refs.json`) y el día de lectura. Y lo leído que la matiza o la contradice no se
calla: va en `discrepancies`, con una nota que dice en qué. Es el caso de la sangre: hoy se
devuelve a Tierra para analizarla, y a la vez hubo demostraciones de analizadores a bordo. La
regla clasifica lo que dice la práctica leída y enseña la demostración al lado; elegir sin
decirlo sería redondear una discrepancia. El cargador rechaza una frase vacía, una ficha que no
está en el registro, una fecha que no es fecha y una discrepancia sin nota.

En la decimotercera ronda se leyó qué material gasta cada muestra (tubos, bolsas con trazador,
papel de filtro, algodón) y dónde se mide el volumen de la orina de 24 h tomada en vuelo: en
Tierra, por el litio de cada bolsa. Lo que no se encontró —la densidad de la orina, el material de
las medidas sin muestra— sigue sin clasificar: una frase que no existe no se suple con intuición.

DESDE LA DECIMOCUARTA RONDA: «HOY LO SABEMOS DESPUÉS»
----------------------------------------------------
La conversación de ideación (~643 y ~754) pide de cada equipo qué parte depende hoy de Tierra, y
señala como el sitio donde buscar lo que «hoy lo sabemos después; en Marte necesitaríamos saberlo
ahora». `ground_dependence` cruza las medidas que hoy requieren retorno de la muestra o análisis en
Tierra con lo que la fuente de cada perfil de misión (`evidence/mission_profiles.py`) dice del
reabastecimiento y del regreso. NO deduce logística: si la fuente del perfil no dice nada, el
cruce dice «EMMA no tiene fuente», no «imposible» ni «habrá que medirlo a bordo». Las frases de
las reglas son de la estación espacial; las del perfil, de su página. Se ponen al lado.

Los tres calculados dicen de qué se calculan (`inputs`). Si heredan (`inherits`), toman de sus
entradas dónde se procesan y cuándo llegan, y solo cuando todas las entradas coinciden: el
cociente neutrófilos/linfocitos y el BUN/creatinina salen del mismo informe que sus analitos. La
dosis acumulada no hereda: en EMMA llega registrada, no se calcula de la tasa de dosis, y su
`inputs_basis` dice por qué (`environment/dosimetry.py`). Lo que se buscó sin encontrarlo se
declara en `searched_not_found`, con dónde se buscó, y solo sobre pares que siguen sin clasificar:
una búsqueda fallida al lado de una clase asignada sería un aviso viejo.

DESDE LA DECIMOQUINTA RONDA: EL MATERIAL DE LAS MEDIDAS SIN MUESTRA
-----------------------------------------------------------------
Que una ficha de equipo no nombre consumibles no dice que no los gaste. Por eso «no gasta
consumibles» solo lo asigna una regla que lo diga de la propia medida —un cálculo, una anotación,
una prueba de reacción en pantalla— y nunca la falta de una frase: de los sensores que se
llevan puestos, el tensiómetro, la masa, la prueba de esfuerzo y el dinamómetro se dice lo que se
buscó (`searched_not_found`), no «no gasta»; lo que no se buscó (el dosímetro de la nave, el
registro del equipo de ejercicio) queda sin clasificar y sin aviso. Lo que sí se leyó gastar
—el gel de la ecografía, el tubo EDTA de la serie roja— lleva su regla con la frase. Y lo leído
que matiza una regla que se apoya en el repositorio también se enseña: la camiseta con sensores
de la estación baja sus datos a Tierra para analizarlos, aunque el wearable de EMMA dé el valor
en el propio dispositivo.

DESDE LA DECIMOSEXTA RONDA: LAS DIMENSIONES QUE NOMBRA LA BASE DE CONOCIMIENTO §9
--------------------------------------------------------------------------------
La base de conocimiento §9 da la lista literal: tiempo de tripulación, invasividad, hardware,
masa, volumen, potencia, consumibles, calibración, entrenamiento, procesamiento, dependencia de
Tierra y latencia hasta el resultado. EMMA tenía siete de las doce en otros nombres (el tiempo, la
clase de medida, el equipo y las tres dimensiones de arriba); `KB_TERMS` dice dónde está cada
una, y una prueba lee la frase de la base de conocimiento para que ninguna se quede sin sitio.
Las cinco que faltaban entran como dimensiones: masa, volumen y potencia del equipo, calibración,
y formación y guía del operador.

Masa, volumen y potencia son CIFRAS, y una cifra solo se escribe con la frase de la fuente que la
da: la regla pone `{"figure": "10.32", "unit": "lbs"}` y el cargador exige que esa cifra, con esa
unidad, esté escrita tal cual en una de sus frases leídas (`sources`). Un tope (lo más que puede
gastar cualquier carga de un rack) no es el gasto de un aparato, y una cifra del fabricante para
otro modelo tampoco: lo que se encontró así va en lo buscado y no encontrado. Casi todo queda sin
clasificar, y es el resultado: masa y potencia de los equipos de la estación no las publica lo
leído para ninguno de los aparatos de EMMA.

DESDE LA DECIMOCTAVA RONDA: CALIBRACIÓN Y FORMACIÓN DE LO QUE SE LLEVA PUESTO, DEL DOSÍMETRO Y
DEL LABORATORIO
-------------------------------------------------------------------------------------------
La decimosexta ronda dejó sin buscar la calibración y la formación de los sensores que se llevan
puestos, del dosímetro y de las analíticas. Buscadas, se dice lo que la frase dice y de qué equipo:
el dosímetro de la nave (los DOSTEL de Columbus y los REM de NASA) y los analizadores del hemograma
de la serie roja se calibran, y el actígrafo de la estación es un comercial cuyo fabricante vende su
recalibración; la tripulación se instruyó en la extracción antes de la misión en el estudio de los
leucocitos, y la de un análogo en Tierra se formó en la camiseta con sensores antes de la suya.
Por eso la formación tiene dos palabras nuevas, una por sitio: la estación y el análogo. Una
formación leída de un análogo no es una de vuelo, y donde no se enseña la regla (el detalle de
alerta, los recuentos) la palabra tiene que decirlo sola.
Lo que no se encontró —la calibración de los sensores puestos, del resto de la sangre, de la orina
y de la saliva; la formación del dosímetro y de las demás muestras— queda sin clasificar con dónde
se buscó.

DESDE LA DECIMONOVENA RONDA: LAS DIMENSIONES QUE NOMBRA LA CONVERSACIÓN DE IDEACIÓN
---------------------------------------------------------------------------------
La conversación de ideación (~673) pide de cada medida once cosas, y tres no estaban en la lista
de la base de conocimiento §9: almacenamiento, frecuencia posible y capacidad de automatización.
`CONVERSATION_TERMS` dice dónde tiene EMMA cada una, como `KB_TERMS`, y una prueba lee la frase de
la conversación para que ninguna se quede sin sitio. «Valor clínico» NO entra, y la lista lo dice
con su motivo: es un juicio clínico, como ordenar las comprobaciones de una alerta por su coste
(decisión abierta C6), y EMMA no lo puntúa.

El almacenamiento es el destino de la muestra a bordo (congelada, o a temperatura ambiente hasta
el regreso), «nada que guardar a bordo» cuando la medida se hace en Tierra, o el volumen de datos
de un sensor como cifra —con la misma regla que la masa: solo copiada de una frase leída—. La
frecuencia posible es el calendario que da el protocolo leído: continua mientras se lleva el
equipo, continua por periodos, en las sesiones de vuelo del protocolo, o solo en Tierra. Ninguna
de las dos se deduce de la clase de medida: lo que ninguna frase da queda sin clasificar.

La capacidad de automatización sí es una DEDUCCIÓN DE EMMA, de la clase de medida (`mode`), y se
rotula así en la propia palabra («lo deduce EMMA de la clase de medida»), porque el detalle de
alerta y los recuentos enseñan la palabra sin la regla. El cargador exige la marca en cada palabra
de una dimensión deducida y en el `basis` de toda regla que la asigne: una deducción que se lee
como una lectura es una cifra inventada con otro nombre. Dice qué intervención pide la clase
(pasiva, con operador, con muestra y análisis, calculada), no cuánto está automatizado hoy en la
estación. Donde la clase no decide (la densitometría DXA, de «laboratorio» sin muestra; la dosis
acumulada, «calculada» que EMMA no calcula) la deducción no alcanza: sin clasificar.

Nada de esto entra en el análisis: es inventario (invariante 5), también las cifras de masa,
volumen y potencia, que ningún módulo de `analysis/` lee. `measurement_cost.json` no entra en
`rules_version` (`core/versioning.py`): no decide nada.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any, TypeVar, cast

from app.core import display, i18n
from app.evidence import mission_profiles, registry

COST_PATH = Path(__file__).resolve().parents[1] / "data" / "measurement_cost.json"

T = TypeVar("T")

MODES = {
    "continuous-passive": "continuo y pasivo",
    "periodic-noninvasive": "periódico, no invasivo",
    "periodic-invasive": "periódico, con muestra",
    "laboratory": "laboratorio",
    "derived": "calculado a partir de otras medidas",
}

UNCLASSIFIED = "unclassified"
UNCLASSIFIED_DISPLAY = "sin clasificar"
UNCLASSIFIED_NOTE = (
    "«Sin clasificar» es que no se deduce de lo que el repositorio dice del indicador. No "
    "quiere decir ni «a bordo» ni «en Tierra», ni que gaste o no consumibles, ni que el equipo "
    "no pese, no abulte o no gaste energía, ni que no haya que calibrarlo o formarse para usarlo, "
    "ni que la muestra o el dato no ocupen sitio, ni que la medida se pueda tomar cuando se "
    "quiera: está por decidir con una fuente delante."
)
# Decimonovena ronda: una dimensión deducida por EMMA lleva la marca en cada palabra y en el
# `basis` de toda regla que la asigne (`_checked`): la palabra viaja sola al detalle de alerta.
DEDUCED = "deduced"
DEDUCED_MARK = "lo deduce EMMA"
DEDUCED_DISPLAY = "deducción de EMMA, no una lectura"
DEDUCED_NOTE = (
    "Esta dimensión no sale de una frase leída: EMMA la deduce de la clase de medida (`mode`) de "
    "cada indicador, y cada palabra lo dice. Describe qué intervención pide la clase, no cuánto "
    "está automatizado hoy en la estación. Donde la clase no decide, queda sin clasificar."
)
# Vocabulario cerrado de cada dimensión, con las palabras que se enseñan (la interfaz no las
# redacta). «Inmediato» y «diferido» se definen por la espera a un análisis, no por un tiempo:
# no hay cifra de plazo que citar.
DIMENSIONS: dict[str, dict[str, Any]] = {
    "processing": {
        "display": "Dónde se procesa",
        "values": {
            "on-device": "a bordo, en el propio dispositivo",
            "onboard-analyzer": "a bordo, con analizador",
            "ground-or-return": "requiere retorno de la muestra o análisis en Tierra",
        },
    },
    "result": {
        "display": "Cuándo llega el resultado",
        "values": {
            "immediate": "inmediato: disponible al medir, sin espera a un análisis",
            "deferred": "diferido: espera a un análisis",
        },
    },
    "consumables": {
        "display": "Consumibles",
        "values": {
            "none": "no gasta consumibles",
            "consumes": "gasta consumibles",
        },
    },
    # Decimosexta ronda (KB §9). Masa, volumen y potencia son cifras: «stated» solo lo pone una
    # regla con `figure` y `unit` copiados de su frase leída (`_check_figure`).
    "mass": {
        "display": "Masa del equipo",
        "values": {
            "stated": "cifra leída en la fuente",
            "no-own-equipment": "no añade equipo propio: se calcula de otras medidas",
        },
        "units": ("kg", "g", "lbs", "lb"),
    },
    "volume": {
        "display": "Volumen del equipo",
        "values": {
            "stated": "cifra leída en la fuente",
            "no-own-equipment": "no añade equipo propio: se calcula de otras medidas",
        },
        "units": ("L", "mL", "m³", "cm³"),
    },
    "power": {
        "display": "Potencia eléctrica",
        "values": {
            "stated": "cifra leída en la fuente",
            "no-own-equipment": "no añade equipo propio: se calcula de otras medidas",
        },
        "units": ("W",),
    },
    "calibration": {
        "display": "Calibración",
        "values": {
            "required": "lo leído nombra su calibración",
            "no-own-equipment": "no añade instrumento propio que calibrar: se calcula",
        },
    },
    "training": {
        "display": "Formación y guía del operador",
        "values": {
            # Lo leído es de la estación (Marshall-Goebel et al. 2019), no de la consola de EMMA.
            "ground-guided": "en la estación, la toma se guió en tiempo real desde Tierra",
            # Decimoctava ronda: quién se formó y cuándo, y dónde se leyó. La estación y el
            # análogo en Tierra son dos palabras, no una: lo leído de un análogo no se cuenta
            # ni se enseña como de vuelo, tampoco donde la regla no sale (el detalle de alerta).
            "station-trained": "en la estación, quien lo toma se formó antes de la misión",
            "analog-trained": "en un análogo en Tierra, quien lo usó se formó antes de la misión",
            "no-own-equipment": "no añade operador: se calcula de otras medidas",
        },
    },
    # Decimonovena ronda (conversación de ideación ~673). El almacenamiento es el destino de la
    # muestra a bordo o el volumen de datos de un sensor (cifra: solo con `figure` y `unit`
    # copiados de su frase leída, como la masa); la frecuencia posible, el calendario que da el
    # protocolo leído. Ninguna de las dos se deduce de la clase de medida.
    "storage": {
        "display": "Almacenamiento",
        "values": {
            "sample-frozen-aboard": "muestra: se congela a bordo y espera así al regreso",
            "sample-ambient-aboard": (
                "muestra: espera a temperatura ambiente hasta llegar a Tierra"
            ),
            "nothing-aboard": "nada que guardar a bordo: la medida se hace en Tierra",
            "stated": "cifra leída en la fuente: volumen de datos",
            "no-own-storage": "no añade almacenamiento propio: se calcula de otras medidas",
        },
        "units": ("kB", "KB", "MB", "GB", "TB"),
    },
    "frequency": {
        "display": "Frecuencia posible",
        "values": {
            # Cada cuánto se lleva el equipo (días por misión), si lo leído lo da, lo dice la regla.
            "continuous": (
                "continua: lo leído dice que el equipo mide de forma continua mientras se lleva"
            ),
            # La palabra viaja sola al detalle de alerta: un registro por periodos no se lee como
            # uno continuo, y las pausas no pueden quedarse en la regla.
            "continuous-in-periods": (
                "continua por periodos: registra de forma continua dentro de cada periodo que fija "
                "el protocolo leído, y entre periodos no (la regla dice cuáles)"
            ),
            "mission-timepoints": (
                "por protocolo, en vuelo: en las sesiones de la misión que fija el protocolo "
                "leído (la regla dice cuáles)"
            ),
            "ground-only": (
                "por protocolo, solo en Tierra: antes y después del vuelo o en una revisión "
                "periódica; sin toma en vuelo"
            ),
            "no-own-schedule": "no añade calendario propio: se calcula de otras medidas",
        },
    },
    # Deducción de EMMA (`DEDUCED`): cada palabra lleva la marca `DEDUCED_MARK`, porque el detalle
    # de alerta y los recuentos la enseñan sin la regla, y el cargador lo exige.
    "automation": {
        "display": "Capacidad de automatización",
        DEDUCED: True,
        "values": {
            "passive": (
                "pasiva (lo deduce EMMA de la clase de medida): el sensor registra sin que nadie "
                "haga la medida"
            ),
            "operator": (
                "con operador (lo deduce EMMA de la clase de medida): alguien, el tripulante u "
                "otra persona, hace la medida o la anota"
            ),
            "sample-and-analysis": (
                "con muestra y análisis (lo deduce EMMA de la clase de medida): alguien toma la "
                "muestra y esta se analiza aparte"
            ),
            "computed": (
                "calculada (lo deduce EMMA de la clase de medida): sale de otras medidas; se "
                "automatiza lo que se automaticen sus entradas"
            ),
        },
    },
}
# El valor de una cifra leída, y las dimensiones que solo lo admiten con su cifra.
STATED = "stated"
QUANTITIES = tuple(name for name, spec in DIMENSIONS.items() if "units" in spec)
_FIGURE_KEYS = frozenset({"figure", "unit"})
# Solo punto decimal: las fuentes leídas están en inglés, donde la coma separa miles («2,000 W»).
# Una cifra con coma se rechaza en vez de leerse mil veces más pequeña; el precio es que hoy no se
# puede escribir una cifra de cuatro cifras o más con su coma de miles. Ninguna fuente leída la da
# para un equipo de EMMA: si aparece, se amplía esto con su prueba, no se quita la coma a mano.
_FIGURE = re.compile(r"\d+(?:\.\d+)?")
# La lista de la base de conocimiento §9, en su orden, y dónde la tiene EMMA: un campo de cada
# indicador (`mode`, `equipment`, el tiempo) o una dimensión de `DIMENSIONS`. La dependencia de
# Tierra es un valor de «dónde se procesa» y el cruce de «hoy se sabe después».
KB_TERMS: tuple[tuple[str, str], ...] = (
    ("crew time", "crew_time_minutes"),
    ("invasividad", "mode"),
    ("hardware", "equipment"),
    ("masa", "mass"),
    ("volumen", "volume"),
    ("potencia", "power"),
    ("consumibles", "consumables"),
    ("calibración", "calibration"),
    ("entrenamiento", "training"),
    ("procesamiento", "processing"),
    ("dependencia de Tierra", "processing"),
    ("latencia hasta resultado", "result"),
)
KB_FIELDS = {
    "crew_time_minutes": "Tiempo de tripulación para medirlo",
    "mode": "Clase de medida (con muestra o sin ella)",
    "equipment": "Equipo",
}
KB_DISPLAY = "Lo que pide la base de conocimiento §9 y dónde lo tiene EMMA"
KB_ORIGIN = (
    "Base de conocimiento §9: «Cada variable debe acompañarse de su “coste de medición”: crew "
    "time, invasividad, hardware, masa, volumen, potencia, consumibles, calibración, "
    "entrenamiento, procesamiento, dependencia de Tierra y latencia hasta resultado»."
)
KB_NOTES = {
    "dependencia de Tierra": (
        "Es el valor «requiere retorno de la muestra o análisis en Tierra» de esta dimensión, "
        "y el cruce «Hoy se sabe después». Lo que en la estación se guió desde Tierra al tomarlo "
        "está en «Formación y guía del operador», y ese cruce no lo cuenta: es una dependencia al "
        "medir, no al analizar."
    ),
    # Decimoctava ronda: lo que las dos palabras dicen y lo que dejan a cada regla.
    "calibración": (
        "La palabra «lo leído nombra su calibración» dice que el instrumento se calibra, no cada "
        "cuánto, ni dónde, ni quién: eso lo dice la regla de cada medida (antes del "
        "lanzamiento, en el servicio del fabricante o en el laboratorio de Tierra adonde vuelve "
        "la muestra)."
    ),
    "entrenamiento": (
        "Es «Formación y guía del operador»: la guía desde Tierra al tomarlo y la formación de "
        "quien lo usa antes de la misión, con el sitio donde se leyó en la palabra (la estación "
        "o un análogo en Tierra). Ni cuánto duró ni quién la dio: lo leído no lo dice."
    ),
}
# Decimonovena ronda: la lista de la conversación de ideación (~673), en su orden, y dónde la
# tiene EMMA. `None` es un término que NO entra, y su nota dice por qué: la lista no lo calla.
EXCLUDED = None
CONVERSATION_TERMS: tuple[tuple[str, str | None], ...] = (
    ("valor clínico", EXCLUDED),
    ("tiempo de astronauta", "crew_time_minutes"),
    ("invasividad", "mode"),
    ("hardware", "equipment"),
    ("consumibles", "consumables"),
    ("energía", "power"),
    ("masa", "mass"),
    ("almacenamiento", "storage"),
    ("dependencia de Tierra", "processing"),
    ("frecuencia posible", "frequency"),
    ("capacidad de automatización", "automation"),
)
EXCLUDED_KIND = "excluded"
EXCLUDED_DISPLAY = "No entra en EMMA"
CONVERSATION_DISPLAY = "Lo que pide la conversación de ideación y dónde lo tiene EMMA"
CONVERSATION_ORIGIN = (
    "Conversación de ideación del equipo: «Cada medición debería evaluarse por: valor clínico / "
    "tiempo de astronauta / invasividad / hardware / consumibles / energía / masa / "
    "almacenamiento / dependencia de Tierra / frecuencia posible / capacidad de automatización.»"
)
CONVERSATION_NOTES = {
    "valor clínico": (
        "No entra: cuánto vale clínicamente una medida es un juicio clínico, como ordenar las "
        "comprobaciones de una alerta por su coste de medir (decisión abierta C6). EMMA describe "
        "lo que cuesta medir; no puntúa lo que vale medir."
    ),
    "dependencia de Tierra": KB_NOTES["dependencia de Tierra"],
    "almacenamiento": (
        "Es el destino de la muestra a bordo (congelada, o a temperatura ambiente hasta el "
        "regreso), «nada que guardar a bordo» cuando la medida se hace en Tierra, o el volumen de "
        "datos de un sensor como cifra copiada de una frase leída. Lo que ninguna frase da queda "
        "sin clasificar: ni cuánto ocupa un dato ni cuánto una muestra."
    ),
    "frecuencia posible": (
        "Es el calendario que da el protocolo leído: continua mientras se lleva el equipo, "
        "continua por periodos, en las sesiones de vuelo que fija el protocolo, o solo en "
        "Tierra. No se deduce de la clase "
        "de medida: una medida sin calendario leído queda sin clasificar."
    ),
    "capacidad de automatización": (
        "Es una deducción de EMMA de la clase de medida, y cada palabra lo dice: pasiva, con "
        "operador, con muestra y análisis, o calculada. Dice qué intervención pide la clase, no "
        "cuánto está automatizado hoy en la estación. Donde la clase no decide queda sin "
        "clasificar."
    ),
}
# Lo leído que sostiene una regla y lo leído que la matiza: los dos se enseñan con estas palabras.
READING_DISPLAY = {
    "sources": "Lo leído que la sostiene",
    "discrepancies": "Lo leído que la matiza o la contradice",
}
_READING_KEYS = {
    "sources": frozenset({"ref", "quote", "where", "read_on"}),
    "discrepancies": frozenset({"ref", "quote", "where", "read_on", "note"}),
}
_ISO_DAY = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
# Lo que un calculado declara de sus entradas, y las dimensiones que puede heredar de ellas. Los
# consumibles no se heredan: el cálculo no gasta lo que gastó la muestra de sus entradas.
_INPUT_FIELDS = ("inputs", "inherits", "inputs_basis")
INHERITED_DIMENSIONS = ("processing", "result")
# «Hoy se sabe después»: el valor que dice que una medida depende de Tierra, y lo que se lee de
# cada perfil de misión para ponerlo al lado.
GROUND_VALUE = "ground-or-return"
GROUND_ASPECTS = ("resupply", "return_or_evacuation")
NO_SOURCE = "EMMA no tiene fuente"
GROUND_DISPLAY = "Hoy se sabe después"
GROUND_NOTE = (
    "Las medidas que hoy requieren retorno de la muestra o análisis en Tierra, según las reglas "
    "de arriba (frases leídas de la estación espacial), y al lado lo que la fuente de cada perfil "
    "de misión dice del reabastecimiento y del regreso. EMMA no deduce de aquí la logística de "
    "ningún perfil ni cuándo llegaría el resultado en él. Donde la fuente del perfil no dice "
    "nada: «EMMA no tiene fuente»."
)
GROUND_ORIGIN = (
    "Conversación de ideación del equipo: «hoy lo sabemos después; en Marte necesitaríamos "
    "saberlo ahora»."
)
SEARCHED_DISPLAY = "Buscado y no encontrado"
_SEARCHED_KEYS = frozenset({"keys", "dimensions", "searched", "searched_on"})
# Por qué campo puede una regla elegir indicadores. `keys` los nombra uno a uno.
_MATCH_FIELDS = ("mode", "equipment")
_MATCH_KEYS = frozenset({*_MATCH_FIELDS, "keys", "except_keys"})


# EL INGLÉS (2026-11-15, `core/i18n.py`). Las constantes de arriba no se tocan: sus pruebas, las
# campañas de mutantes y el cargador (la marca `DEDUCED_MARK` se busca en la palabra castellana)
# leen el castellano. El inglés va aquí, al lado, y se aplica al SERVIR (`_served`): lo que se
# valida y lo que se guarda en caché sigue en castellano. El inglés de `measurement_cost.json`
# está en su hermano `measurement_cost.en.json`. Las clases siguen siendo relativas y sin medir:
# el inglés dice lo mismo que el castellano, con sus mismas reservas.
_NO_OWN_EQUIPMENT_EN = "adds no equipment of its own: it is calculated from other measurements"
_VALUES_EN: dict[str, tuple[str, dict[str, str]]] = {
    "processing": ("Where it is processed", {
        "on-device": "on board, on the device itself",
        "onboard-analyzer": "on board, with an analyzer",
        "ground-or-return": "requires sample return or analysis on Earth",
    }),
    "result": ("When the result arrives", {
        "immediate": "immediate: available on measuring, with no wait for an analysis",
        "deferred": "deferred: waits for an analysis",
    }),
    "consumables": ("Consumables", {
        "none": "uses no consumables",
        "consumes": "uses consumables",
    }),
    "mass": ("Equipment mass", {
        "stated": "figure read in the source",
        "no-own-equipment": _NO_OWN_EQUIPMENT_EN,
    }),
    "volume": ("Equipment volume", {
        "stated": "figure read in the source",
        "no-own-equipment": _NO_OWN_EQUIPMENT_EN,
    }),
    "power": ("Electrical power", {
        "stated": "figure read in the source",
        "no-own-equipment": _NO_OWN_EQUIPMENT_EN,
    }),
    "calibration": ("Calibration", {
        "required": "what was read names its calibration",
        "no-own-equipment": "adds no instrument of its own to calibrate: it is calculated",
    }),
    "training": ("Operator training and guidance", {
        "ground-guided": "on the station, the acquisition was guided in real time from Earth",
        "station-trained": "on the station, whoever takes it was trained before the mission",
        "analog-trained": "in an analog on Earth, whoever used it was trained before the mission",
        "no-own-equipment": "adds no operator: it is calculated from other measurements",
    }),
    "storage": ("Storage", {
        "sample-frozen-aboard": "sample: frozen on board, and it waits that way for the return",
        "sample-ambient-aboard": "sample: waits at ambient temperature until it reaches Earth",
        "nothing-aboard": "nothing to store on board: the measurement is made on Earth",
        "stated": "figure read in the source: data volume",
        "no-own-storage": "adds no storage of its own: it is calculated from other measurements",
    }),
    "frequency": ("Possible frequency", {
        "continuous": (
            "continuous: what was read says the equipment measures continuously while it is worn"
        ),
        "continuous-in-periods": (
            "continuous in periods: it records continuously within each period set by the "
            "protocol that was read, and not between periods (the rule says which)"
        ),
        "mission-timepoints": (
            "by protocol, in flight: in the mission sessions set by the protocol that was read "
            "(the rule says which)"
        ),
        "ground-only": (
            "by protocol, on Earth only: before and after the flight or at a periodic check-up; "
            "not taken in flight"
        ),
        "no-own-schedule": "adds no schedule of its own: it is calculated from other measurements",
    }),
    # La marca de la deducción viaja también en inglés, en cada palabra.
    "automation": ("Automation capability", {
        "passive": (
            "passive (EMMA deduces it from the measurement class): the sensor records without "
            "anyone making the measurement"
        ),
        "operator": (
            "with an operator (EMMA deduces it from the measurement class): someone, the crew "
            "member or another person, makes the measurement or notes it down"
        ),
        "sample-and-analysis": (
            "with sample and analysis (EMMA deduces it from the measurement class): someone "
            "takes the sample and it is analyzed separately"
        ),
        "computed": (
            "calculated (EMMA deduces it from the measurement class): it comes from other "
            "measurements; it is automated to the extent that its inputs are"
        ),
    }),
}
# Las frases del equipo se citan como están escritas, en castellano: solo cambia quién las presenta.
_QUOTED_IN_SPANISH = " (in Spanish): "
_EN: dict[str, str] = {
    MODES["continuous-passive"]: "continuous and passive",
    MODES["periodic-noninvasive"]: "periodic, non-invasive",
    MODES["periodic-invasive"]: "periodic, with a sample",
    MODES["laboratory"]: "laboratory",
    MODES["derived"]: "calculated from other measurements",
    UNCLASSIFIED_DISPLAY: "unclassified",
    UNCLASSIFIED_NOTE: (
        "“Unclassified” means that it cannot be deduced from what the repository says about the "
        "indicator. It does not mean “on board” or “on Earth”, nor that it does or does not use "
        "consumables, nor that the equipment has no weight, takes no room or draws no power, nor "
        "that it needs no calibration or no training to use it, nor that the sample or the data "
        "take no room, nor that the measurement can be taken whenever wanted: it is still to be "
        "decided with a source in hand."
    ),
    DEDUCED_DISPLAY: "EMMA's deduction, not a reading",
    DEDUCED_NOTE: (
        "This dimension does not come from a sentence read: EMMA deduces it from the measurement "
        "class (`mode`) of each indicator, and each wording says so. It describes what "
        "intervention the class asks for, not how automated it is on the station today. Where the "
        "class does not decide, it remains unclassified."
    ),
    KB_FIELDS["crew_time_minutes"]: "Crew time to measure it",
    KB_FIELDS["mode"]: "Measurement class (with or without a sample)",
    KB_FIELDS["equipment"]: "Equipment",
    KB_DISPLAY: "What the knowledge base §9 asks for and where EMMA has it",
    KB_ORIGIN: "Knowledge base §9" + _QUOTED_IN_SPANISH + KB_ORIGIN.partition(": ")[2],
    KB_NOTES["dependencia de Tierra"]: (
        "It is the value “requires sample return or analysis on Earth” of this dimension, and the "
        "cross-reference “Today it is known afterwards”. What on the station was guided from "
        "Earth when taking it is under “Operator training and guidance”, and that cross-reference "
        "does not count it: it is a dependence when measuring, not when analyzing."
    ),
    KB_NOTES["calibración"]: (
        "The wording “what was read names its calibration” says that the instrument is "
        "calibrated, not how often, or where, or by whom: that is said by the rule of each "
        "measurement (before launch, at the manufacturer's service or in the Earth laboratory "
        "the sample returns to)."
    ),
    KB_NOTES["entrenamiento"]: (
        "It is “Operator training and guidance”: the guidance from Earth when taking it and the "
        "training of its user before the mission, with the place where it was read in the wording "
        "(the station or an analog on Earth). Neither how long it lasted nor who gave it: what "
        "was read does not say."
    ),
    EXCLUDED_DISPLAY: "Not included in EMMA",
    CONVERSATION_DISPLAY: "What the ideation conversation asks for and where EMMA has it",
    CONVERSATION_ORIGIN: (
        "Team ideation conversation" + _QUOTED_IN_SPANISH + CONVERSATION_ORIGIN.partition(": ")[2]
    ),
    CONVERSATION_NOTES["valor clínico"]: (
        "Not included: how much a measurement is worth clinically is a clinical judgment, like "
        "ordering the checks of an alert by their measurement cost (open decision C6). EMMA "
        "describes what it costs to measure; it does not score what measuring is worth."
    ),
    CONVERSATION_NOTES["almacenamiento"]: (
        "It is the destination of the sample on board (frozen, or at ambient temperature until "
        "the return), “nothing to store on board” when the measurement is made on Earth, or the "
        "data volume of a sensor as a figure copied from a sentence read. What no sentence gives "
        "remains unclassified: neither how much room a datum takes nor how much a sample does."
    ),
    CONVERSATION_NOTES["frecuencia posible"]: (
        "It is the calendar given by the protocol that was read: continuous while the equipment "
        "is worn, continuous in periods, in the flight sessions set by the protocol, or on Earth "
        "only. It is not deduced from the measurement class: a measurement with no calendar read "
        "remains unclassified."
    ),
    CONVERSATION_NOTES["capacidad de automatización"]: (
        "It is EMMA's deduction from the measurement class, and each wording says so: passive, "
        "with an operator, with sample and analysis, or calculated. It says what intervention "
        "the class asks for, not how automated it is on the station today. Where the class does "
        "not decide it remains unclassified."
    ),
    READING_DISPLAY["sources"]: "What was read that supports it",
    READING_DISPLAY["discrepancies"]: "What was read that qualifies or contradicts it",
    NO_SOURCE: "EMMA has no source",
    GROUND_DISPLAY: "Today it is known afterwards",
    GROUND_NOTE: (
        "The measurements that today require sample return or analysis on Earth, according to "
        "the rules above (sentences read about the space station), and beside them what the "
        "source of each mission profile says about resupply and return. EMMA does not deduce "
        "from this the logistics of any profile or when the result would arrive in it. Where the "
        "profile's source says nothing: “EMMA has no source”."
    ),
    GROUND_ORIGIN: (
        "Team ideation conversation" + _QUOTED_IN_SPANISH + GROUND_ORIGIN.partition(": ")[2]
    ),
    SEARCHED_DISPLAY: "Searched and not found",
}
for _dimension, (_shown, _words) in _VALUES_EN.items():
    _EN[DIMENSIONS[_dimension]["display"]] = _shown
    for _value, _word in _words.items():
        _EN[DIMENSIONS[_dimension]["values"][_value]] = _word
# Quien enseña una de estas constantes desde otro módulo la resuelve con `i18n.loc`. «Equipo»
# no se registra para todos: en castellano es también la tripulación, y otro módulo podría darle
# otro inglés; aquí dentro lo resuelve `_served`, que solo mira este diccionario.
i18n.en_many({es: en for es, en in _EN.items() if es != KB_FIELDS["equipment"]})
# Lo que se copia de un documento se queda como está escrito: la frase leída y el término de la
# lista del equipo.
_VERBATIM = frozenset({"quote", "term"})


def _english(value: Any) -> Any:
    if isinstance(value, str):
        shown = _EN.get(value, value)
        return i18n.overlay(COST_PATH).get(shown, shown)
    if isinstance(value, dict):
        return {
            key: item if key in _VERBATIM else _english(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_english(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_english(item) for item in value)
    return value


def _served(value: T) -> T:
    """Lo que sale de este módulo, en el idioma de la petición.

    En castellano, tal cual. En inglés, una copia con cada cadena entera sustituida por su inglés
    (el de arriba o el de `measurement_cost.en.json`); las claves, los identificadores y lo
    copiado de una fuente (`_VERBATIM`) no cambian. Lo guardado en caché no se toca.
    """
    if i18n.current() != "en":
        return value
    return cast(T, _english(value))


def _document() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(COST_PATH.read_text(encoding="utf-8"))
    return document


@cache
def costs() -> dict[str, dict[str, Any]]:
    raw: dict[str, dict[str, Any]] = _document()["indicators"]
    return validate(raw)


def validate(raw: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Rechaza una entrada con clase desconocida o con cifra de tiempo sin fuente."""
    for key, item in raw.items():
        if item["mode"] not in MODES:
            raise ValueError(f"{key}: clase de medida desconocida {item['mode']!r}")
        if item["crew_time_minutes"] is not None and item["crew_time_basis"] == "sin fuente":
            raise ValueError(f"{key}: un tiempo con cifra no puede ser 'sin fuente'")
        _check_inputs(key, item, raw)
    return raw


def _check_inputs(key: str, item: Mapping[str, Any], raw: Mapping[str, Mapping[str, Any]]) -> None:
    """Un calculado dice de qué se calcula, si hereda de ello y por qué; nadie más lo dice."""
    declared = [name for name in _INPUT_FIELDS if name in item]
    if item["mode"] != "derived":
        if declared:
            raise ValueError(f"{key}: solo un calculado declara entradas ({declared})")
        return
    if len(declared) != len(_INPUT_FIELDS):
        raise ValueError(f"{key}: un calculado dice de qué se calcula: {list(_INPUT_FIELDS)}")
    inputs = item["inputs"]
    if (
        not isinstance(inputs, list) or not inputs
        or not all(isinstance(name, str) for name in inputs) or len(set(inputs)) != len(inputs)
    ):
        raise ValueError(f"{key}: `inputs` es la lista de indicadores de los que se calcula")
    if missing := sorted(set(inputs) - raw.keys()):
        raise ValueError(f"{key}: entradas que no están en el coste de medir: {missing}")
    # Herencia de un paso: una entrada calculada (o él mismo) haría depender el resultado del
    # orden en que se recorren, y un ciclo no tendría de dónde heredar.
    if chained := sorted(name for name in inputs if raw[name]["mode"] == "derived"):
        raise ValueError(f"{key}: entradas que también son calculadas: {chained}")
    if not isinstance(item["inherits"], bool):
        raise ValueError(f"{key}: `inherits` es sí o no")
    if not isinstance(item["inputs_basis"], str) or not item["inputs_basis"].strip():
        raise ValueError(f"{key}: sin `inputs_basis`: de dónde sale el enlace, o no se escribe")


def _listed(value: Any) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


def _matches(rule: Mapping[str, Any], key: str, item: Mapping[str, Any]) -> bool:
    """Una regla alcanza a un indicador si cumple TODO lo que la regla nombra."""
    match = rule["match"]
    if "keys" in match and key not in match["keys"]:
        return False
    # Una medida de la clase a la que lo leído le quita lo que la regla diría de ella.
    if key in match.get("except_keys", ()):
        return False
    return all(item[name] in _listed(match[name]) for name in _MATCH_FIELDS if name in match)


def _checked(rule: Mapping[str, Any], raw: Mapping[str, Mapping[str, Any]]) -> str:
    """Valida una regla contra el vocabulario y devuelve su identificador."""
    ident = str(rule.get("id") or "")

    def fail(reason: str) -> ValueError:
        return ValueError(f"regla de coste {ident or '?'}: {reason}")

    if not ident:
        raise fail("sin `id`")
    basis = rule.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        raise fail("sin `basis`: una clasificación dice de dónde sale o no se escribe")
    match, assigned = rule.get("match"), rule.get("set")
    if not isinstance(match, dict) or not match:
        raise fail("sin `match`: una regla que alcanza a todo no es una regla")
    if extra := sorted(match.keys() - _MATCH_KEYS):
        raise fail(f"`match` por campos desconocidos {extra}")
    if unknown := sorted(set(_listed(match.get("mode", []))) - MODES.keys()):
        raise fail(f"clase de medida desconocida {unknown}")
    named = {*match.get("keys", []), *match.get("except_keys", [])}
    if missing := sorted(named - raw.keys()):
        raise fail(f"nombra indicadores que no están en el coste de medir: {missing}")
    if not isinstance(assigned, dict) or not assigned:
        raise fail("sin `set`: no clasifica nada")
    for kind, keys in _READING_KEYS.items():
        _check_reading(rule.get(kind, []), kind, keys, fail)
    for dimension, value in assigned.items():
        if dimension not in DIMENSIONS:
            raise fail(f"dimensión desconocida {dimension!r}")
        # Una dimensión deducida se rotula como deducción en la regla y en la palabra: leída sin
        # la marca pasaría por una lectura.
        if DIMENSIONS[dimension].get(DEDUCED) and DEDUCED_MARK not in basis:
            raise fail(f"`{dimension}` es una deducción de EMMA y el `basis` no lo dice")
        # Y no finge fuente: una lectura al lado de una deducción la haría pasar por leída.
        if DIMENSIONS[dimension].get(DEDUCED) and any(rule.get(kind) for kind in _READING_KEYS):
            raise fail(f"`{dimension}` es una deducción de EMMA y la regla cita lecturas")
        if isinstance(value, dict):
            _check_figure(dimension, value, rule.get("sources", []), fail)
            continue
        if not isinstance(value, str):
            raise fail(f"`{dimension}`: {value!r} no es ni una palabra del vocabulario ni cifra")
        if value == STATED:
            raise fail(f"`{dimension}`: una cifra se escribe con `figure` y `unit`, no a secas")
        if value not in DIMENSIONS[dimension]["values"]:
            # «Sin clasificar» no se asigna: es lo que queda cuando ninguna regla alcanza.
            raise fail(f"valor {value!r} fuera del vocabulario de `{dimension}`")
        if DIMENSIONS[dimension].get(DEDUCED) and DEDUCED_MARK not in (
            DIMENSIONS[dimension]["values"][value]
        ):
            raise fail(f"la palabra {value!r} de `{dimension}` no dice que la deduce EMMA")
    return ident


def _check_reading(
    items: Any, kind: str, keys: frozenset[str], fail: Callable[[str], ValueError]
) -> None:
    """Una frase leída lleva su ficha del registro, su sitio, su día y, si matiza, en qué."""
    if not isinstance(items, list):
        raise fail(f"`{kind}` es una lista")
    for item in items:
        if not isinstance(item, dict) or item.keys() != keys:
            raise fail(f"`{kind}` lleva exactamente {sorted(keys)}")
        for name in keys - {"read_on"}:
            if not isinstance(item[name], str) or not item[name].strip():
                raise fail(f"`{kind}` con `{name}` vacío: lo leído se copia o no se escribe")
        if not isinstance(item["read_on"], str) or not _ISO_DAY.fullmatch(item["read_on"]):
            raise fail(f"`{kind}`: `read_on` es el día de lectura, AAAA-MM-DD")
        # Citar una ficha que no está en el registro falla aquí: no se inventa una en blanco.
        registry.get(item["ref"])


def _check_figure(
    dimension: str, value: Mapping[str, Any], sources: Any, fail: Callable[[str], ValueError]
) -> None:
    """Una cifra de masa, volumen, potencia o datos: copiada, con su unidad, de una frase leída.

    No basta con que la regla cite algo: la cifra y la unidad tienen que estar escritas juntas,
    tal cual, en una de sus frases (`sources`). Lo que matiza (`discrepancies`) no sostiene una
    cifra, y una cifra en otra unidad o redondeada es otra cifra. Una tasa tampoco es una
    cantidad: «1 MB/s» o «1 MB per day» no sostienen «1 MB», y las tasas son la forma habitual de
    dar el volumen de datos de un sensor.
    """
    units = DIMENSIONS[dimension].get("units")
    if units is None:
        raise fail(f"`{dimension}` no es una cifra: se clasifica con su vocabulario")
    if value.keys() != _FIGURE_KEYS:
        raise fail(f"una cifra de `{dimension}` lleva exactamente {sorted(_FIGURE_KEYS)}")
    figure, unit = value["figure"], value["unit"]
    if not isinstance(figure, str) or not _FIGURE.fullmatch(figure) or float(figure) <= 0:
        raise fail(f"`figure` de `{dimension}` es la cifra tal cual se lee, positiva")
    if unit not in units:
        raise fail(f"unidad {unit!r} fuera de las de `{dimension}`: {list(units)}")
    written = re.compile(
        rf"(?<![\d.,]){re.escape(figure)}\s?{re.escape(unit)}(?![^\W\d_]|\s?/|\s?per\b)"
    )
    quotes = [item.get("quote", "") for item in sources if isinstance(item, dict)]
    if not any(isinstance(quote, str) and written.search(quote) for quote in quotes):
        raise fail(f"la cifra {figure} {unit} de `{dimension}` no está en ninguna frase leída")


def _figure_entry(figure: Mapping[str, str]) -> tuple[str, dict[str, Any]]:
    """El valor y lo que se enseña de una cifra leída: el número en español y su unidad."""
    text = figure["figure"]
    decimals = len(text.partition(".")[2])
    amount = float(text)
    return (
        f"{display.number(amount, decimals)} {figure['unit']}",
        {"amount": amount, "decimals": decimals, "unit": figure["unit"], "figure": text},
    )


def _resolved_reading(item: Mapping[str, Any]) -> dict[str, Any]:
    ref = registry.get(item["ref"])
    return {**item, "title": ref.title, "source": ref.source, "url": ref.url}


def cited_refs() -> set[str]:
    """Las fichas del registro que cita el coste de medir (para la prueba de huérfanas)."""
    return {
        item["ref"] for rule in _rules() for kind in _READING_KEYS for item in rule.get(kind, [])
    }


def classify(
    raw: Mapping[str, Mapping[str, Any]], rules: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, dict[str, Any]]]:
    """Las dimensiones de cada indicador, cada una con la regla y el texto que la sostienen.

    Falla al cargar —no en silencio— si una regla sale del vocabulario, no dice en qué se apoya,
    no alcanza a ningún indicador (regla muerta: lo que nombraba ya no existe) o contradice a
    otra sobre el mismo indicador. Una cifra (`{"figure", "unit"}`) es el valor «stated» con su
    cifra al lado: falla si no está escrita en una frase leída de la regla, o si dos reglas dan
    dos cifras distintas. Lo que ninguna regla alcanza queda sin clasificar.
    """
    out: dict[str, dict[str, dict[str, Any]]] = {
        key: {
            dimension: {
                "value": UNCLASSIFIED, "display": UNCLASSIFIED_DISPLAY, "basis": None,
                "rule": None, "inherited_from": None, "figure": None,
            }
            for dimension in DIMENSIONS
        }
        for key in raw
    }
    seen: set[str] = set()
    for rule in rules:
        ident = _checked(rule, raw)
        if ident in seen:
            raise ValueError(f"regla de coste {ident}: identificador duplicado")
        seen.add(ident)
        reached = [key for key, item in raw.items() if _matches(rule, key, item)]
        if not reached:
            raise ValueError(f"regla de coste {ident}: no alcanza a ningún indicador")
        for key in reached:
            for dimension, assigned in rule["set"].items():
                # Una cifra leída es el valor «stated» con su cifra al lado; lo demás, vocabulario.
                if isinstance(assigned, dict):
                    value = STATED
                    shown, figure = _figure_entry(assigned)
                else:
                    value, figure = assigned, None
                    shown = DIMENSIONS[dimension]["values"][value]
                held = out[key][dimension]
                if held["rule"] is not None and held["value"] != value:
                    raise ValueError(
                        f"{key}: las reglas {held['rule']} y {ident} dan dos valores de "
                        f"`{dimension}`"
                    )
                if held["rule"] is not None and held["figure"] != figure:
                    raise ValueError(
                        f"{key}: las reglas {held['rule']} y {ident} dan dos cifras de "
                        f"`{dimension}`"
                    )
                if held["rule"] is None:
                    out[key][dimension] = {
                        "value": value,
                        "display": shown,
                        "basis": rule["basis"],
                        "rule": ident,
                        "inherited_from": None,
                        "figure": figure,
                    }
    _inherit(raw, out)
    return out


def _inherit(
    raw: Mapping[str, Mapping[str, Any]], out: dict[str, dict[str, dict[str, Any]]]
) -> None:
    """Un calculado que hereda toma de sus entradas dónde se procesa y cuándo llega.

    Solo si TODAS sus entradas tienen el mismo valor: si una está sin clasificar o discrepan, no
    se elige una, y el calculado sigue sin clasificar. Si una regla ya lo clasificó, la herencia
    tiene que coincidir con ella o la carga falla.
    """
    for key, item in raw.items():
        if not item.get("inherits"):
            continue
        for dimension in INHERITED_DIMENSIONS:
            held = [out[name][dimension] for name in item["inputs"]]
            values = {entry["value"] for entry in held}
            if len(values) != 1 or UNCLASSIFIED in values:
                continue
            (value,) = values
            current = out[key][dimension]
            if current["rule"] is not None:
                if current["value"] != value:
                    raise ValueError(
                        f"{key}: la regla {current['rule']} y sus entradas dan dos valores de "
                        f"`{dimension}`"
                    )
                continue
            rules = sorted({str(entry["rule"]) for entry in held})
            display = DIMENSIONS[dimension]["values"][value]
            out[key][dimension] = {
                "value": value,
                "display": display,
                "basis": i18n.tr(
                    f"Calculado a partir de {', '.join(item['inputs'])}, que dan «{display}» "
                    f"(regla {', '.join(rules)}). {item['inputs_basis']}",
                    f"Calculated from {', '.join(item['inputs'])}, which give "
                    f"“{_english(display)}” (rule {', '.join(rules)}). "
                    f"{_english(item['inputs_basis'])}",
                ),
                # La regla de sus entradas si es una sola; si son varias, ninguna en particular.
                "rule": rules[0] if len(rules) == 1 else None,
                "inherited_from": list(item["inputs"]),
                "figure": None,
            }


@cache
def _rules() -> tuple[dict[str, Any], ...]:
    return tuple(_document().get("dimension_rules", ()))


def check_searched(
    notes: Any, classified: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    """Lo buscado y no encontrado: sobre qué pares, dónde se buscó y cuándo.

    Solo vale sobre pares que siguen sin clasificar: si una regla los clasifica después, el
    aviso de «no encontrado» se quita en el mismo cambio o la carga falla.
    """
    if not isinstance(notes, list):
        raise ValueError("`searched_not_found` es una lista")
    for item in notes:
        if not isinstance(item, dict) or item.keys() != _SEARCHED_KEYS:
            raise ValueError(f"lo buscado lleva exactamente {sorted(_SEARCHED_KEYS)}")
        if not isinstance(item["searched"], str) or not item["searched"].strip():
            raise ValueError("lo buscado dice qué se buscó y dónde")
        if not isinstance(item["searched_on"], str) or not _ISO_DAY.fullmatch(item["searched_on"]):
            raise ValueError("`searched_on` es el día de la búsqueda, AAAA-MM-DD")
        if not all(
            isinstance(item[name], list) and item[name]
            and all(isinstance(entry, str) for entry in item[name])
            for name in ("keys", "dimensions")
        ):
            raise ValueError("lo buscado nombra al menos un indicador y una dimensión")
        if missing := sorted(set(item["keys"]) - classified.keys()):
            raise ValueError(f"lo buscado nombra indicadores que no están: {missing}")
        if unknown := sorted(set(item["dimensions"]) - DIMENSIONS.keys()):
            raise ValueError(f"lo buscado nombra dimensiones desconocidas: {unknown}")
        if found := sorted(
            f"{key}.{dimension}"
            for key in item["keys"] for dimension in item["dimensions"]
            if classified[key][dimension]["value"] != UNCLASSIFIED
        ):
            raise ValueError(f"«no encontrado» sobre pares ya clasificados: {found}")
    return list(notes)


@cache
def searched() -> tuple[dict[str, Any], ...]:
    return tuple(check_searched(_document().get("searched_not_found", []), dimensions()))


def _profile_citation(cite: Mapping[str, Any]) -> dict[str, Any]:
    ref = registry.get(cite["ref"])
    return {**cite, "title": ref.title, "url": ref.url}


def _ground_aspect(name: str, aspect: Mapping[str, Any]) -> dict[str, Any]:
    """Lo que la fuente del perfil dice de un aspecto, o que EMMA no tiene fuente."""
    read = aspect["status"] == mission_profiles.READ
    discrepancy = aspect["discrepancy"]
    return {
        "key": name,
        "label": i18n.loc(mission_profiles.ASPECTS[name]),
        "status": aspect["status"],
        "text": aspect["statement"] if read else NO_SOURCE,
        "citations": [_profile_citation(cite) for cite in aspect["citations"]],
        "discrepancy": None if discrepancy is None else {
            "text": discrepancy["text"],
            "citations": [_profile_citation(cite) for cite in discrepancy["citations"]],
        },
        "searched": None if read else aspect["searched"],
    }


@i18n.lang_cache
def ground_dependence() -> dict[str, Any]:
    """«Hoy lo sabemos después»: qué depende hoy de Tierra y qué dice cada perfil al lado.

    Una entrada de caché por idioma. Lo de cada perfil es de `evidence/mission_profiles.py`: se
    enseña con el inglés que tenga su fichero (`PROFILES_PATH`), y en castellano mientras no.
    """
    classified = dimensions()
    return _served({
        "display": GROUND_DISPLAY,
        "note": GROUND_NOTE,
        "origin": GROUND_ORIGIN,
        "value": GROUND_VALUE,
        "value_display": DIMENSIONS["processing"]["values"][GROUND_VALUE],
        "no_source": NO_SOURCE,
        "rules": [
            rule["id"] for rule in _rules() if rule["set"].get("processing") == GROUND_VALUE
        ],
        "indicators": [
            {
                "key": key,
                "rule": item["processing"]["rule"],
                "inherited_from": item["processing"]["inherited_from"],
                "result": item["result"]["display"],
            }
            for key, item in classified.items()
            if item["processing"]["value"] == GROUND_VALUE
        ],
        "profiles": [
            {
                "id": profile["id"],
                "display": profile["display"],
                "aspects": [
                    _ground_aspect(name, profile["aspects"][name]) for name in GROUND_ASPECTS
                ],
            }
            for profile in i18n.localized(
                mission_profiles.catalog()["profiles"], mission_profiles.PROFILES_PATH
            )
        ],
    })


@i18n.lang_cache
def dimensions() -> dict[str, dict[str, dict[str, Any]]]:
    # Una entrada por idioma: la cifra leída se escribe con la coma o el punto de quien la pide
    # (`_figure_entry`) y lo heredado redacta su frase (`_inherit`). Lo demás sale en castellano
    # en las dos y lo pasa a inglés `_served`, al servir.
    # Las listas de la base de conocimiento §9 y de la conversación se comprueban al cargar las
    # dimensiones, no en la primera petición del resumen: un término sin sitio falla con todo lo
    # demás.
    kb_coverage()
    conversation_coverage()
    return classify(costs(), _rules())


def cost(key: str) -> dict[str, Any] | None:
    item = costs().get(key)
    if item is None:
        return None
    return _served(
        {**item, "mode_display": MODES[item["mode"]], "dimensions": dimensions()[key]}
    )


def _coverage(
    origin_name: str,
    terms: Sequence[tuple[str, str | None]],
    notes: Mapping[str, str],
    display: str,
    origin: str,
) -> dict[str, Any]:
    """Cada término de una lista del equipo, con dónde lo tiene EMMA o que no entra.

    Un término que apunte a un campo que no existe hace fallar la carga de las dimensiones
    (`dimensions` la llama): la lista no se publica con un hueco tapado. Un campo se busca en
    las entradas de verdad, no solo en `KB_FIELDS`: si una entrada lo pierde, falla igual. Un
    término que no entra (`EXCLUDED`) lleva su nota, o la carga falla: lo que se deja fuera se
    dice con su motivo.
    """
    shown_terms: list[dict[str, Any]] = []
    entries = costs()
    for term, field in terms:
        if field is EXCLUDED:
            if not notes.get(term, "").strip():
                raise ValueError(f"{origin_name}: «{term}» no entra y la lista no dice por qué")
            shown, kind = EXCLUDED_DISPLAY, EXCLUDED_KIND
        elif field in DIMENSIONS:
            shown, kind = DIMENSIONS[field]["display"], "dimension"
        elif field in KB_FIELDS and all(field in item for item in entries.values()):
            shown, kind = KB_FIELDS[field], "field"
        else:
            raise ValueError(f"{origin_name}: «{term}» apunta a {field!r}, que EMMA no tiene")
        shown_terms.append({
            "term": term, "field": field, "kind": kind, "display": shown,
            "note": notes.get(term),
        })
    return _served({"display": display, "origin": origin, "terms": shown_terms})


def kb_coverage() -> dict[str, Any]:
    """Cada término de la lista de la base de conocimiento §9, con dónde lo tiene EMMA."""
    return _coverage("KB §9", KB_TERMS, KB_NOTES, KB_DISPLAY, KB_ORIGIN)


def conversation_coverage() -> dict[str, Any]:
    """Cada término de la conversación de ideación (~673): dónde lo tiene EMMA, o que no entra."""
    return _coverage(
        "Conversación de ideación", CONVERSATION_TERMS, CONVERSATION_NOTES,
        CONVERSATION_DISPLAY, CONVERSATION_ORIGIN,
    )


def summary() -> dict[str, Any]:
    """Cuántos indicadores hay en cada clase de cada dimensión, y cuántos sin clasificar."""
    classified = dimensions()
    rows: list[dict[str, Any]] = []
    for dimension, spec in DIMENSIONS.items():
        held = [item[dimension]["value"] for item in classified.values()]
        rows.append({
            "key": dimension,
            "display": spec["display"],
            # Decimonovena ronda: una dimensión deducida por EMMA lo dice también en su fila.
            "deduced": bool(spec.get(DEDUCED, False)),
            "values": [
                {"value": value, "display": display, "count": held.count(value)}
                for value, display in spec["values"].items()
            ],
            "unclassified": held.count(UNCLASSIFIED),
        })
    # Se compone en castellano y sale por `_served`.
    return _served({
        "indicators": len(classified),
        "kb_coverage": kb_coverage(),
        "conversation_coverage": conversation_coverage(),
        "deduced_display": DEDUCED_DISPLAY,
        "deduced_note": DEDUCED_NOTE,
        "dimensions": rows,
        # Pares indicador-dimensión por decidir, y cuántos indicadores tienen todas decididas.
        "unclassified": sum(row["unclassified"] for row in rows),
        "fully_classified": sum(
            1 for item in classified.values()
            if all(entry["value"] != UNCLASSIFIED for entry in item.values())
        ),
        "unclassified_value": UNCLASSIFIED,
        "unclassified_display": UNCLASSIFIED_DISPLAY,
        "unclassified_note": UNCLASSIFIED_NOTE,
        "reading_display": READING_DISPLAY,
        "searched_display": SEARCHED_DISPLAY,
        "searched": [
            {
                **item,
                "dimensions_display": [
                    DIMENSIONS[dimension]["display"] for dimension in item["dimensions"]
                ],
            }
            for item in searched()
        ],
        "ground_dependence": ground_dependence(),
        "rules": [
            {
                "id": rule["id"],
                "basis": rule["basis"],
                "indicators": sum(
                    1 for item in classified.values()
                    # Lo heredado lleva la regla de sus entradas, pero la regla no lo alcanza:
                    # no cuenta como indicador suyo.
                    if any(
                        entry["rule"] == rule["id"] and entry["inherited_from"] is None
                        for entry in item.values()
                    )
                ),
                **{
                    kind: [_resolved_reading(item) for item in rule.get(kind, [])]
                    for kind in _READING_KEYS
                },
            }
            for rule in _rules()
        ],
    })
