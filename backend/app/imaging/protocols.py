"""Registro de protocolos ecográficos.

Por qué existe: la tripulación no va a hacer un solo tipo de ecografía, y añadir un examen no
debería exigir código nuevo en la ingesta ni en la interfaz. Cada protocolo se declara aquí una
vez; lo que cambia de uno a otro —ventanas, signos que se anotan, lista de calidad— cuelga de
esta misma entrada. Las medidas en milímetros viven en `measure.py`.

Dos maneras de registrar lo que se ve:

  * **Medida** (nervio óptico, yugular, vejiga): un número, que entra en el catálogo y en la
    línea base.
  * **Signos anotados** (pulmón, FAST, hígado): lo que el operador ve en cada ventana, de una
    lista cerrada de valores. Un signo es una observación, no un diagnóstico: "deslizamiento
    pleural: ausente" se anota; "neumotórax" no. No entran en el análisis.

Cada signo exige respuesta, con "no valorable" como opción explícita: un signo sin marcar no
puede leerse como "ausente".

Las ventanas y los signos salen de la literatura citada en `sources`. La **lista de calidad** la
fija el proyecto (no es un protocolo validado): recuerda al operador lo que invalida una
adquisición, y queda registrada con el estudio.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core import i18n

NOT_ASSESSABLE = "no-valorable"


@dataclass(frozen=True)
class Sign:
    key: str
    display: str
    # Valor -> cómo se lee. Siempre incluye NOT_ASSESSABLE.
    values: dict[str, str]


@dataclass(frozen=True)
class View:
    key: str
    display: str
    signs: tuple[Sign, ...]


@dataclass(frozen=True)
class Protocol:
    key: str
    display: str
    # Por qué se hace en vuelo. Es lo que justifica que el protocolo esté en el registro.
    rationale: str
    views: tuple[View, ...] = ()
    checklist: tuple[str, ...] = ()
    sources: tuple[str, ...] = field(default=())


def _sign(key: str, display: str, **values: str) -> Sign:
    return Sign(key, display, {**values, NOT_ASSESSABLE: "No valorable"})


_PRESENT_ABSENT = {"presente": "Presente", "ausente": "Ausente"}

_LUNG_SLIDING = _sign("deslizamiento-pleural", "Deslizamiento pleural", **_PRESENT_ABSENT)
_B_LINES = _sign(
    "lineas-b", "Líneas B",
    ninguna="Ninguna", aisladas="Aisladas", multiples="Múltiples",
)
_LUNG_POINT = _sign("punto-pulmon", "Punto pulmón", visto="Visto", **{"no-visto": "No visto"})
_PLEURAL_FLUID = _sign("liquido-pleural", "Líquido pleural", **_PRESENT_ABSENT)
_FREE_FLUID = _sign("liquido-libre", "Líquido libre", **_PRESENT_ABSENT)

_ANTERIOR = (_LUNG_SLIDING, _B_LINES, _LUNG_POINT)
_POSTEROLATERAL = (_B_LINES, _PLEURAL_FLUID)

PROTOCOLS: dict[str, Protocol] = {
    p.key: p
    for p in (
        Protocol(
            "optic-nerve",
            "Vaina del nervio óptico",
            "Marcador del síndrome neuro-ocular asociado al vuelo espacial (SANS).",
            checklist=(
                "Corte axial con el nervio óptico en su eje, sin inclinación.",
                "Párpado cerrado y sin presión de la sonda sobre el globo.",
                "Ganancia que no satura los bordes de la vaina.",
            ),
            sources=("NASA HRP, Evidence Report: Risk of SANS (2017)",),
        ),
        Protocol(
            "jugular-vein",
            "Vena yugular interna",
            "Estasis y flujo invertido por el desplazamiento cefálico de fluidos; trombosis "
            "documentada en un tripulante de la ISS.",
            checklist=(
                "Corte transversal, perpendicular a la vena.",
                "Sin comprimir la vena con la sonda.",
            ),
            sources=("Marshall-Goebel et al., JAMA Netw Open 2019 (PMID 31722025)",),
        ),
        Protocol(
            "bladder",
            "Vejiga",
            "Retención urinaria, conocida en vuelo.",
            checklist=(
                "Corte transversal y corte sagital en fotogramas distintos.",
                "Pared vesical completa visible en los dos cortes.",
            ),
            sources=("NASA HumanResearchWiki: Urinary Retention (Space Adaptation)",),
        ),
        Protocol(
            "lung",
            "Pulmón",
            "Neumotórax y líquido intersticial en emergencias.",
            views=(
                View("derecha-anterior", "Derecha, anterior", _ANTERIOR),
                View("izquierda-anterior", "Izquierda, anterior", _ANTERIOR),
                View("derecha-posterolateral", "Derecha, posterolateral", _POSTEROLATERAL),
                View("izquierda-posterolateral", "Izquierda, posterolateral", _POSTEROLATERAL),
            ),
            checklist=(
                "Sonda perpendicular a las costillas.",
                "Línea pleural visible entre dos costillas.",
            ),
            sources=(
                "Lichtenstein DA, Mezière GA. Chest 2008 (PMID 18403664): protocolo BLUE",
                "Hamilton DR et al. Aviat Space Environ Med 2004 (PMID 15018297): "
                "deslizamiento pleural en microgravedad",
            ),
        ),
        Protocol(
            "fast",
            "FAST abdominal",
            "Líquido libre tras un traumatismo.",
            views=(
                View(
                    "hepatorrenal", "Hepatorrenal (cuadrante superior derecho)", (_FREE_FLUID,)
                ),
                View(
                    "esplenorrenal", "Esplenorrenal (cuadrante superior izquierdo)", (_FREE_FLUID,)
                ),
                View("pelvica", "Pélvica (suprapúbica)", (_FREE_FLUID,)),
                View("pericardica", "Pericárdica (subxifoidea)", (_FREE_FLUID,)),
            ),
            checklist=(
                "Las cuatro ventanas adquiridas.",
                "Profundidad que incluye el espacio que se valora.",
            ),
            sources=(
                "Sargsyan AE et al. J Trauma 2005 (PMID 15674147): FAST de cuatro ventanas en "
                "la ISS",
            ),
        ),
        Protocol(
            "liver",
            "Hígado",
            # Sin respaldo de vuelo localizado: se declara así en vez de inventar uno.
            "Pedido por el equipo. Sin evidencia de vuelo específica localizada todavía.",
            views=(
                View(
                    "hepatorrenal", "Lóbulo derecho con corteza renal en el mismo corte",
                    (
                        _sign(
                            "ecogenicidad-frente-a-rinon", "Ecogenicidad frente a la corteza renal",
                            mayor="Mayor", igual="Igual", menor="Menor",
                        ),
                    ),
                ),
            ),
            checklist=(
                "Hígado y corteza renal a la misma profundidad.",
                "Ganancia uniforme en todo el campo.",
            ),
            sources=(
                "Daum N et al. Z Gastroenterol 2026 (PMID 42161258): índice hepatorrenal",
            ),
        ),
    )
}

# EL INGLÉS DE LOS PROTOCOLOS (2026-11-15, dos idiomas con selector). El registro de arriba no se
# toca: las claves de protocolo, ventana, signo y valor son identificadores (van al ledger con los
# signos anotados) y no se traducen. Aquí va el inglés de lo que se enseña, y quien lo sirve
# (`api/imaging.py`) lo pide con `i18n.loc`.
#
# Ojo con la lista de calidad: su texto castellano hace además de clave. El formulario devuelve
# cada punto por su texto y así queda firmado con el estudio (`record_findings`), de modo que el
# inglés de un punto es solo para enseñarlo: lo que se envía y lo que se firma sigue siendo el
# castellano. De las fuentes se traduce la coletilla de EMMA; la cita queda como está.
ENGLISH: dict[str, str] = {
    # Nombres de protocolo y por qué se hace cada uno en vuelo.
    "Vaina del nervio óptico": "Optic nerve sheath",
    "Marcador del síndrome neuro-ocular asociado al vuelo espacial (SANS).": (
        "Marker of spaceflight-associated neuro-ocular syndrome (SANS)."
    ),
    "Vena yugular interna": "Internal jugular vein",
    "Estasis y flujo invertido por el desplazamiento cefálico de fluidos; trombosis "
    "documentada en un tripulante de la ISS.": (
        "Stasis and reversed flow from the headward fluid shift; thrombosis documented in one "
        "ISS crew member."
    ),
    "Vejiga": "Bladder",
    "Retención urinaria, conocida en vuelo.": "Urinary retention, known in flight.",
    "Pulmón": "Lung",
    "Neumotórax y líquido intersticial en emergencias.": (
        "Pneumothorax and interstitial fluid in emergencies."
    ),
    "FAST abdominal": "Abdominal FAST",
    "Líquido libre tras un traumatismo.": "Free fluid after trauma.",
    "Hígado": "Liver",
    "Pedido por el equipo. Sin evidencia de vuelo específica localizada todavía.": (
        "Requested by the team. No specific flight evidence located yet."
    ),
    # Ventanas.
    "Derecha, anterior": "Right, anterior",
    "Izquierda, anterior": "Left, anterior",
    "Derecha, posterolateral": "Right, posterolateral",
    "Izquierda, posterolateral": "Left, posterolateral",
    "Hepatorrenal (cuadrante superior derecho)": "Hepatorenal (right upper quadrant)",
    "Esplenorrenal (cuadrante superior izquierdo)": "Splenorenal (left upper quadrant)",
    "Pélvica (suprapúbica)": "Pelvic (suprapubic)",
    "Pericárdica (subxifoidea)": "Pericardial (subxiphoid)",
    "Lóbulo derecho con corteza renal en el mismo corte": (
        "Right lobe with renal cortex in the same slice"
    ),
    # Signos y cómo se lee cada valor.
    "Deslizamiento pleural": "Lung sliding",
    "Líneas B": "B-lines",
    "Punto pulmón": "Lung point",
    "Líquido pleural": "Pleural fluid",
    "Líquido libre": "Free fluid",
    "Ecogenicidad frente a la corteza renal": "Echogenicity compared with the renal cortex",
    "No valorable": "Not assessable",
    "Presente": "Present",
    "Ausente": "Absent",
    "Ninguna": "None",
    "Aisladas": "Isolated",
    "Múltiples": "Multiple",
    "Visto": "Seen",
    "No visto": "Not seen",
    "Mayor": "Higher",
    "Igual": "Equal",
    "Menor": "Lower",
    # Lista de calidad (solo para enseñarla: arriba, por qué).
    "Corte axial con el nervio óptico en su eje, sin inclinación.": (
        "Axial slice with the optic nerve along its axis, without tilt."
    ),
    "Párpado cerrado y sin presión de la sonda sobre el globo.": (
        "Eyelid closed and no probe pressure on the globe."
    ),
    "Ganancia que no satura los bordes de la vaina.": (
        "Gain that does not saturate the edges of the sheath."
    ),
    "Corte transversal, perpendicular a la vena.": "Transverse slice, perpendicular to the vein.",
    "Sin comprimir la vena con la sonda.": "Without compressing the vein with the probe.",
    "Corte transversal y corte sagital en fotogramas distintos.": (
        "Transverse slice and sagittal slice in separate frames."
    ),
    "Pared vesical completa visible en los dos cortes.": (
        "Whole bladder wall visible in both slices."
    ),
    "Sonda perpendicular a las costillas.": "Probe perpendicular to the ribs.",
    "Línea pleural visible entre dos costillas.": "Pleural line visible between two ribs.",
    "Las cuatro ventanas adquiridas.": "All four windows acquired.",
    "Profundidad que incluye el espacio que se valora.": (
        "Depth that includes the space being assessed."
    ),
    "Hígado y corteza renal a la misma profundidad.": (
        "Liver and renal cortex at the same depth."
    ),
    "Ganancia uniforme en todo el campo.": "Uniform gain across the whole field.",
    # Fuentes: la cita, igual; la coletilla de EMMA, en inglés.
    "Lichtenstein DA, Mezière GA. Chest 2008 (PMID 18403664): protocolo BLUE": (
        "Lichtenstein DA, Mezière GA. Chest 2008 (PMID 18403664): BLUE protocol"
    ),
    "Hamilton DR et al. Aviat Space Environ Med 2004 (PMID 15018297): "
    "deslizamiento pleural en microgravedad": (
        "Hamilton DR et al. Aviat Space Environ Med 2004 (PMID 15018297): lung sliding in "
        "microgravity"
    ),
    "Sargsyan AE et al. J Trauma 2005 (PMID 15674147): FAST de cuatro ventanas en "
    "la ISS": (
        "Sargsyan AE et al. J Trauma 2005 (PMID 15674147): four-window FAST on the ISS"
    ),
    "Daum N et al. Z Gastroenterol 2026 (PMID 42161258): índice hepatorrenal": (
        "Daum N et al. Z Gastroenterol 2026 (PMID 42161258): hepatorenal index"
    ),
}
i18n.en_many(ENGLISH)


def get_protocol(key: str) -> Protocol:
    try:
        return PROTOCOLS[key]
    except KeyError:
        raise KeyError(f"protocolo ecográfico desconocido: {key!r}") from None


def validate_findings(
    protocol: Protocol, findings: dict[str, dict[str, str]]
) -> list[str]:
    """Problemas de un formulario de signos. Lista vacía = completo y válido.

    Tiene que responder a todas las ventanas y a todos los signos del protocolo, cada uno con
    un valor de su lista. Nada de más, nada de menos: un signo que falta no es un "ausente".
    """
    problems: list[str] = []
    expected = {view.key: view for view in protocol.views}
    for view_key in findings:
        if view_key not in expected:
            problems.append(f"ventana desconocida: {view_key!r}")
    for view in protocol.views:
        answered = findings.get(view.key)
        if answered is None:
            problems.append(f"falta la ventana '{view.display}'")
            continue
        signs = {sign.key: sign for sign in view.signs}
        for sign_key in answered:
            if sign_key not in signs:
                problems.append(f"'{view.display}': signo desconocido {sign_key!r}")
        for sign in view.signs:
            value = answered.get(sign.key)
            if value is None:
                problems.append(f"'{view.display}': falta '{sign.display}' (o 'no valorable')")
            elif value not in sign.values:
                problems.append(f"'{view.display}': valor no admitido para '{sign.display}'")
    return problems
