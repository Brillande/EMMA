"""Petición de ayuda urgente: la saben, por este orden, los de al lado y Tierra.

POR QUÉ EXISTE
--------------
Decisión del usuario (2026-11-14): el botón rojo de «Inicio» deja de ser solo «modo esencial» y
pasa a ser de emergencia, «por si necesitas ayuda urgente». Y matizó: «Tierra está muy lejos;
tiene que alertar a quien tengas más cerca y, obviamente, a Tierra». Con minutos de luz de por
medio, quien puede ayudar ya es la tripulación de a bordo; Tierra llega después.

LO QUE ES
---------
Un asiento firmado por la consola de a bordo con el tripulante que pide ayuda, el nombre de quien
la pide si se sabe (declarado, sin autenticar, como toda acción de consola), un motivo opcional y
el instante de la misión. A bordo se ve **en cuanto se firma**, en las dos consolas de la nave; a
Tierra le llega un tiempo de luz después, con el mismo corte con que Tierra lee todo lo que baja.
La lista ordena al resto de la tripulación por cercanía: primero quien está en el mismo módulo,
después quien está en otro módulo conocido y, al final, de quien no se sabe dónde está. La
ubicación es la del estado (`analysis/location`: declarada por la consola o estimada por las anclas
de módulo). La petición sigue abierta hasta que alguien de a bordo la da por atendida con otro
asiento: no se borra ni se edita. Pedirla es un solo toque, sin nombre obligatorio ni confirmación:
en una emergencia, cada paso de más es tiempo que se resta a quien puede ayudar. Darla por atendida
sí lleva nombre: cerrar una emergencia por error es peligroso, y ese paso no se lo resta a nadie.

LO QUE NO ES
------------
**No es una alerta del motor ni una observación.** No entra en el análisis, no cambia ningún
nivel, ninguna alerta ni `rules_version`: lo que se decide sobre las lecturas sigue igual. Tampoco
es un diagnóstico ni una pauta (invariante 7): EMMA no dice qué le pasa a nadie ni qué hacer; dice
quién pide ayuda, dónde está y a quién tiene más cerca.

EL MOTIVO NO PASA EL FILTRO DE LENGUAJE, A PROPÓSITO. Son las palabras de una persona en apuros,
no un texto de EMMA, y se enseñan entre comillas y firmadas. Rechazar «dolor en el pecho» por
sonar a diagnóstico dejaría a alguien sin poder pedir ayuda. Solo se acota la longitud.

LÍMITE, dicho para no dar falsa confianza: EMMA no tiene megafonía ni intercomunicador. «Avisar a
quien está más cerca» es que su consola lo enseñe y lo lea en voz alta; si nadie mira una consola,
nadie se entera. La petición no sustituye al procedimiento de emergencia de la nave.
"""

from __future__ import annotations

from app.core import i18n

# Un motivo corto: se lee de un vistazo en una banda, no es un informe.
MAX_REASON = 280
MAX_NAME = 64

# Cercanía de cada tripulante a quien pide ayuda, de más a menos cerca (contrato con la interfaz).
SAME_MODULE = "same_module"
OTHER_MODULE = "other_module"
UNKNOWN_PLACE = "unknown"
PROXIMITY_ORDER = (SAME_MODULE, OTHER_MODULE, UNKNOWN_PLACE)
PROXIMITY_DISPLAY = {
    SAME_MODULE: "en el mismo módulo",
    OTHER_MODULE: "en otro módulo",
    UNKNOWN_PLACE: "ubicación desconocida",
}

HEADLINE = "Ayuda urgente"
BASIS = (
    "Petición de ayuda firmada a bordo. La tripulación la ve al momento, empezando por quien está "
    "más cerca; a Tierra le llega un tiempo de luz después. No es una alerta del análisis ni un "
    "diagnóstico: dice quién pide ayuda y dónde está. Sigue abierta hasta que alguien de a bordo "
    "la da por atendida."
)
NO_CREWMATES = (
    "No hay más tripulantes con lecturas en EMMA: avise a la tripulación por el procedimiento de "
    "emergencia de la nave."
)
NO_LOCATION = "ubicación desconocida"
# El inglés de lo que se enseña, registrado para que quien lo sirve (`api/help_requests.py`)
# lo pase por `i18n.loc` al leer. El asiento firmado no lleva ninguna de estas palabras.
i18n.en_many({
    PROXIMITY_DISPLAY[SAME_MODULE]: "in the same module",
    PROXIMITY_DISPLAY[OTHER_MODULE]: "in another module",
    PROXIMITY_DISPLAY[UNKNOWN_PLACE]: "location unknown",
    NO_LOCATION: "location unknown",
    HEADLINE: "Urgent help",
    BASIS: (
        "Help request signed on board. The crew sees it at once, starting with whoever is "
        "closest; it reaches Earth one light time later. It is not an alert from the analysis "
        "nor a medical assessment: it says who is asking for help and where they are. It stays "
        "open until someone on board marks it as attended."
    ),
    NO_CREWMATES: (
        "There are no other crew members with readings in EMMA: alert the crew through the "
        "spacecraft's emergency procedure."
    ),
})


def problem(signed_by: str, reason: str) -> str | None:
    """Por qué no se puede anotar una petición de ayuda; `None` si se puede.

    Casi nada se exige, a propósito (decisión del usuario, 2026-11-14: «solo haces que sea más
    probable que se muera si le restas tiempo de acción por parte de los demás»): ni nombre ni
    motivo. Quién pide la ayuda ya lo dice el tripulante de la consola; el nombre, si lo hay, es el
    recordado en el equipo. El asiento se firma igual, con la clave de la consola, sin que nadie
    haga nada. Solo se acota la longitud de lo que viene.
    """
    if len(signed_by.strip()) > MAX_NAME:
        return f"el nombre tiene como mucho {MAX_NAME} caracteres"
    if len(reason.strip()) > MAX_REASON:
        return f"el motivo tiene como mucho {MAX_REASON} caracteres"
    return None


def close_problem(signed_by: str) -> str | None:
    """Por qué no se puede dar por atendida una petición; `None` si se puede."""
    if not any(char.isalpha() for char in signed_by):
        return "una petición de ayuda la da por atendida una persona con nombre"
    return None
