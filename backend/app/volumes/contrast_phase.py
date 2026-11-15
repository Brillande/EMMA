"""La fase de contraste de un TAC, tal y como la declara una persona.

POR QUÉ EXISTE
--------------
La densidad (HU) de una lesión candidata cambia con la fase de contraste en que se adquirió el
estudio, y un NIfTI no la lleva. Hasta aquí EMMA lo decía y nada más: junto a cada cifra, «el
estudio no declara la fase», y en la comparación de dos estudios, las dos densidades una junto a
otra con el aviso de que la fase podía no ser la misma. No había forma de decir cuál era
(`docs/contexto/README.md`, «Pendiente»; decisión del usuario, 2026-10-13: sí).

LO QUE ES Y LO QUE NO ES
------------------------
**Una etiqueta declarada, no una medida.** La pone una persona con nombre en la consola y se
firma en el registro. No lleva código LOINC ni uno inventado (invariante 1), no es una
observación del catálogo y no entra en `observations`.

**EMMA no propone la fase ni la comprueba.** Polaris tiene `fase()` en `visor3d`, que la propone
con la mediana de aorta, porta e hígado; EMMA no la llama ni la reimplementa
(`docs/polaris-divergencias.md` §7.5). Nada de este módulo mira la imagen: si una persona declara
«arterial» en un estudio sin contraste, eso es lo que consta, con su nombre.

**No clasifica.** La fase declarada no convierte una densidad en el nombre de una lesión ni en
un «realce»: sigue siendo la densidad dentro de una máscara automática, descriptiva.

CINCO VALORES Y UN SEXTO QUE NO SE FIRMA
----------------------------------------
Vocabulario cerrado, de diseño de EMMA y sin fuente leída: sin contraste, arterial, portal
(venosa portal), tardía y «no se sabe». No hay subfases: cada valor más es una distinción que
quien declara tendría que saber hacer, y aquí solo sirve para decir si dos cifras se adquirieron
en la misma. «No se sabe» SÍ se firma: una persona miró y no lo sabe. «Sin declarar» no: es que
nadie ha dicho nada, y se enseña como dato ausente.

NO DECIDE NADA
--------------
En la comparación de dos estudios dice si las dos fases constan y coinciden. No bloquea la
comparación, no añade una columna de cambio de densidad y no toca el estado de la evolución, que
lo decide Polaris solo con el diámetro. No entra en el análisis ni en una alerta, y no es una
regla de `rules_version`.

QUÉ DECLARACIÓN VALE
--------------------
La última firmada por la consola para cada estudio. Se corrige declarando de nuevo; no hay
borrado y las anteriores se conservan y se pueden leer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

NON_CONTRAST = "non-contrast"
ARTERIAL = "arterial"
PORTAL_VENOUS = "portal-venous"
DELAYED = "delayed"
UNKNOWN = "unknown"
# Lo que una persona puede firmar, en el orden en que se ofrece.
PHASES: dict[str, str] = {
    NON_CONTRAST: "sin contraste",
    ARTERIAL: "arterial",
    PORTAL_VENOUS: "portal (venosa portal)",
    DELAYED: "tardía",
    UNKNOWN: "no se sabe",
}
UNDECLARED_DISPLAY = "sin declarar"
# La única modalidad con unidades Hounsfield (`geometry.HU_MODALITY`), y por eso la única en la
# que la fase dice algo de una densidad.
MODALITY = "CT"

DECLARED_LABEL = "declarada por una persona; EMMA no la propone ni la comprueba"
DECLARED_NOTE = (
    "Fase de contraste declarada por {declared_by}: {display}. Es lo que una persona declaró en "
    "la consola, firmado en el registro; EMMA no la propone ni la comprueba con la imagen. La "
    "densidad cambia con la fase: las cifras de dos estudios solo se pueden poner una junto a "
    "otra si se adquirieron en la misma."
)
UNKNOWN_NOTE = (
    "{declared_by} declaró que no se sabe en qué fase de contraste se adquirió el estudio. La "
    "densidad cambia con la fase: sin saberla, estas cifras no se pueden poner junto a las de "
    "otro estudio como iguales."
)
VOCABULARY_BASIS = (
    "El vocabulario es cerrado y de diseño de EMMA, sin fuente leída: sirve para decir si dos "
    "estudios se adquirieron en la misma fase, no para describir el protocolo de adquisición."
)
RULE = (
    "Vale la última declaración firmada por la consola para cada estudio; las anteriores se "
    "conservan. No hay borrado: se corrige declarando de nuevo."
)
SCOPE = (
    "La fase declarada se enseña junto a la densidad. No clasifica ninguna lesión, no cambia el "
    "estado de la evolución —que sale solo del diámetro— y no entra en el análisis ni en una "
    "alerta."
)
NOT_CT = (
    "La fase de contraste solo se declara en un TAC: es lo que cambia sus unidades Hounsfield, "
    "y este estudio es de modalidad {modality}."
)
NO_NAME = "la fase de contraste la declara una persona con nombre"

SAME = "same"
DIFFERENT = "different"
MISSING = "missing"
NOT_APPLICABLE = "not-applicable"
SAME_TEXT = (
    "Los dos estudios constan declarados en la misma fase de contraste ({display}). Es lo que "
    "declaró una persona, no una medida: las dos densidades se enseñan una junto a otra, sin "
    "columna de cambio y sin veredicto."
)
DIFFERENT_TEXT = (
    "Los dos estudios constan declarados en fases de contraste distintas ({before} y {after}): "
    "las cifras de densidad de uno y de otro no se pueden poner una junto a otra como iguales."
)
MISSING_TEXT = (
    "No consta la fase de contraste de los dos estudios (anterior: {before}; posterior: "
    "{after}): las cifras de densidad de uno y de otro no se pueden poner una junto a otra como "
    "iguales."
)
NOT_APPLICABLE_TEXT = (
    "La fase de contraste solo se declara en un TAC, y alguno de estos estudios no lo es."
)


def check(phase: str) -> None:
    """Lo que se puede firmar. Lo usan la ruta y el almacén: nadie más escribe una declaración."""
    if phase not in PHASES:
        raise ValueError(
            f"fase de contraste fuera del vocabulario: {phase}; una de {', '.join(PHASES)}"
        )


def check_modality(modality: Any) -> None:
    if modality != MODALITY:
        raise ValueError(NOT_CT.format(modality=modality))


def well_formed(item: dict[str, Any]) -> bool:
    """Un asiento que la ruta no habría firmado no se respeta, lo firme quien lo firme."""
    return item.get("phase") in PHASES and any(
        char.isalpha() for char in str(item.get("declared_by", ""))
    )


def _view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": item["phase"],
        "display": PHASES[item["phase"]],
        "declared_by": item["declared_by"],
        "at": item["at"],
        "note": item["note"] or None,
        "ledger_index": item["ledger_index"],
        "recorded": item["recorded"],
    }


def history(
    declarations: Sequence[dict[str, Any]], study: dict[str, Any], signer: str
) -> list[dict[str, Any]]:
    """Las declaraciones que cuentan de un estudio, de la más antigua a la más reciente.

    Solo las firmadas por la consola, bien formadas y que citan la huella del volumen firmado en
    ese asiento: una que nombrara otro volumen no habla de este estudio.
    """
    return [
        _view(item) for item in declarations
        if item.get("signer") == signer
        and item.get("study_index") == study.get("ledger_index")
        and item.get("study_sha256") == study.get("sha256")
        and well_formed(item)
    ]


def sentence(item: dict[str, Any], study_index: int, previous: dict[str, Any] | None) -> str:
    """Una declaración de `history` en una frase para la crónica, con su rótulo.

    Solo la fase y el asiento del estudio. Ni la nota, que es texto libre sobre el estudio y
    puede llevar datos personales, ni nada del volumen: la crónica se escribe en más sitios que
    la respuesta a quien lo pregunta (el PDF, la bitácora de Polaris). Quién declaró va en su
    campo, como en las demás declaraciones.
    """
    before = (
        f"antes constaba «{previous['display']}»" if previous is not None
        else f"antes constaba «{UNDECLARED_DISPLAY}»"
    )
    return (
        f"fase de contraste del TAC del asiento {study_index}: «{item['display']}» "
        f"({before}; {DECLARED_LABEL})"
    )


def describe(
    declarations: Sequence[dict[str, Any]], study: dict[str, Any], signer: str
) -> dict[str, Any]:
    """Lo que consta de la fase de un estudio: la vigente (o ninguna) y la historia."""
    applicable = study.get("modality") == MODALITY
    told = history(declarations, study, signer) if applicable else []
    return {
        "applicable": applicable,
        "not_applicable_reason": (
            None if applicable else NOT_CT.format(modality=study.get("modality"))
        ),
        "current": told[-1] if told else None,
        "undeclared_display": UNDECLARED_DISPLAY,
        "label": DECLARED_LABEL,
        "history": told,
    }


def annotate(
    segmentation: dict[str, Any], current: dict[str, Any] | None, density_key: str,
    undeclared_note: str,
) -> dict[str, Any]:
    """La segmentación con la fase declarada de su estudio junto a la densidad. Devuelve una
    copia: lo firmado (que lleva `fase_contraste` vacía y la nota de «no declara») no se toca.

    Sin densidad disponible, o sin declaración, no cambia nada: la nota sigue diciendo que el
    estudio no declara la fase.
    """
    block = segmentation.get(density_key)
    if current is None or not isinstance(block, dict) or not block.get("disponible"):
        return segmentation
    told = (UNKNOWN_NOTE if current["code"] == UNKNOWN else DECLARED_NOTE).format(
        declared_by=current["declared_by"], display=current["display"]
    )
    notes = [note for note in block.get("notas", []) if note != undeclared_note]
    return {
        **segmentation,
        density_key: {**block, "fase_contraste": current, "notas": [*notes, told]},
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Lo que consta de las fases de dos estudios (`describe` de cada uno), sin veredicto.

    «No se sabe» cuenta como no constar: dos estudios de los que no se sabe la fase no están en
    la misma.
    """
    first, second = before["current"], after["current"]
    shown = {
        "antes": first, "despues": second, "sin_declarar": UNDECLARED_DISPLAY,
        "etiqueta": DECLARED_LABEL,
    }
    if not (before["applicable"] and after["applicable"]):
        return {**shown, "estado": NOT_APPLICABLE, "texto": NOT_APPLICABLE_TEXT}
    names = [UNDECLARED_DISPLAY if item is None else item["display"] for item in (first, second)]
    if first is None or second is None or UNKNOWN in (first["code"], second["code"]):
        return {
            **shown, "estado": MISSING,
            "texto": MISSING_TEXT.format(before=names[0], after=names[1]),
        }
    if first["code"] != second["code"]:
        return {
            **shown, "estado": DIFFERENT,
            "texto": DIFFERENT_TEXT.format(before=names[0], after=names[1]),
        }
    return {**shown, "estado": SAME, "texto": SAME_TEXT.format(display=names[0])}


def vocabulary() -> dict[str, Any]:
    """Lo que la consola ofrece para declarar, con los textos que enseña al lado."""
    return {
        "phases": [{"code": code, "display": display} for code, display in PHASES.items()],
        "undeclared_display": UNDECLARED_DISPLAY,
        "modality": MODALITY,
        "label": DECLARED_LABEL,
        "basis": VOCABULARY_BASIS,
        "rule": RULE,
        "scope": SCOPE,
    }
