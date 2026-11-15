"""Las categorías FHIR que se quedan como están sin casar bien con ninguna de las nueve.

POR QUÉ EXISTE
--------------
`Observation.category` es la clasificación gruesa del recurso FHIR, y `ingest/fhir.py` decide la de
cada indicador. §5.38.9 corrigió las que se podían defender contra la definición oficial y dejó
seis que salen de su dominio sin que ninguna de las nueve las describa bien. Cambiarlas no se ha
decidido (decimonovena ronda, §5.39.19): se **exponen y se declaran**. `/api/indicators` lleva la
categoría de cada indicador y esta lista, con la frase del motivo, para que quien lea el recurso
sepa cuáles son una aproximación en vez de creer que EMMA las da por buenas.

Va aparte del catálogo a propósito: es una nota sobre el recurso que se sirve, no una regla. No
entra en `VitalCode` ni en la huella de las reglas, y no cambia ninguna categoría: la que se
enseña es siempre la de `fhir_category`, y una prueba fija que cada motivo habla de esa.
"""

from __future__ import annotations

from app.core import i18n
from app.ingest.codes import CATALOG, VitalCode
from app.ingest.fhir import fhir_category

_NOT_IN_PROFILE = (
    "Sale «vital-signs» por su dominio, pero {what} no está en el conjunto de códigos del perfil "
    "de signos vitales de FHIR R4 (observation-vitalsignresult); ninguna de las nueve categorías "
    "lo describe mejor."
)
_SHIP_DOSIMETRY = (
    "Sale «exam» por su dominio, pero es dosimetría de la nave, no una exploración de la persona; "
    "ninguna de las nueve categorías la describe."
)

# Clave del indicador → por qué su categoría no casa.
_MISFITS: dict[str, str] = {
    "hrv-sdnn": _NOT_IN_PROFILE.format(what="su código LOINC de variabilidad (SDNN)"),
    "hrv-rmssd": _NOT_IN_PROFILE.format(what="su código propio de variabilidad (RMSSD)"),
    "orthostatic-drop": _NOT_IN_PROFILE.format(what="su código propio de caída ortostática"),
    "absorbed-dose-rate": _SHIP_DOSIMETRY,
    "cumulative-dose": _SHIP_DOSIMETRY,
    "circadian-shift": (
        "Sale «survey» por su dominio, pero es un cálculo respecto al horario de misión, no un "
        "cuestionario; ninguna de las nueve categorías lo describe."
    ),
}

# El inglés de cada motivo, por la clave del indicador (`core/i18n.py`). El código de la categoría
# («vital-signs», «exam», «survey») es el de FHIR y va igual en los dos idiomas.
_NOT_IN_PROFILE_EN = (
    "It comes out as «vital-signs» because of its domain, but {what} is not in the code set of "
    "the FHIR R4 vital signs profile (observation-vitalsignresult); none of the nine categories "
    "describes it better."
)
_SHIP_DOSIMETRY_EN = (
    "It comes out as «exam» because of its domain, but it is ship dosimetry, not an examination "
    "of the person; none of the nine categories describes it."
)
_MISFITS_EN: dict[str, str] = {
    "hrv-sdnn": _NOT_IN_PROFILE_EN.format(what="its LOINC variability code (SDNN)"),
    "hrv-rmssd": _NOT_IN_PROFILE_EN.format(what="its own variability code (RMSSD)"),
    "orthostatic-drop": _NOT_IN_PROFILE_EN.format(what="its own orthostatic drop code"),
    "absorbed-dose-rate": _SHIP_DOSIMETRY_EN,
    "cumulative-dose": _SHIP_DOSIMETRY_EN,
    "circadian-shift": (
        "It comes out as «survey» because of its domain, but it is a calculation relative to the "
        "mission schedule, not a questionnaire; none of the nine categories describes it."
    ),
}
i18n.en_many({_MISFITS[key]: english for key, english in _MISFITS_EN.items()})


def fields(code: VitalCode) -> dict[str, str | None]:
    """La categoría de un indicador para `/api/indicators`, tal cual sale en su recurso FHIR.

    `None` en las dos si el recurso va sin categoría (`NoCategory.NONE_FITS`).
    """
    category = fhir_category(code)
    return {
        "category": None if category is None else category[0],
        "category_display": None if category is None else category[1],
    }


def misfits() -> list[dict[str, str | None]]:
    """Las que no casan bien: clave, la categoría que llevan de verdad y el motivo, este en el
    idioma de la petición."""
    reasons = {key: i18n.loc(reason) for key, reason in _MISFITS.items()}
    return [
        {"key": key, "category": fields(CATALOG[key])["category"], "reason": reason}
        for key, reason in reasons.items()
    ]
