"""Estados inferidos: lo que no se mide en vuelo, estimado y rotulado como tal.

La especificacion del equipo (§9, escenario musculoesqueletico) pide "mostrar la trayectoria
inferida —no medida— y su incertidumbre". La densidad mineral osea no se mide a bordo: se mide
antes y despues del vuelo (DEXA, tomografia). Durante el vuelo solo cabe estimarla, y la base de
conocimiento (§4, "variables inferibles") lo plantea como hipotesis, no como capacidad.

Lo que se sabe y con que respaldo:
- Perdida de 1-1,5 % al mes en huesos de carga sin contramedidas: magnitud documentada por NASA
  ("The Human Body in Space"; `simulator.LITERATURE["bmd_loss_pct_per_month"]`).
- El ejercicio resistivo la reduce: sentido documentado, magnitud no citable. Por eso la banda
  NO se estrecha con la adherencia al ejercicio: se dice, no se calcula.

Es una banda de poblacion aplicada al dia de mision, no un modelo de esta persona. Se rotula
INFERIDO con su modelo, y nunca se escribe en el ledger como si fuera una medida.

EN POSVUELO LA BANDA SE DETIENE EN EL DIA DE REGRESO
----------------------------------------------------
La banda contaba con `mission_day`, que sigue sumando despues del aterrizaje: con datos de
posvuelo decia que el hueso seguia perdiendo 1-1,5 % al mes en Tierra y seguia proyectando esa
tasa a los horizontes que quedaban (el dia 365 de una mision de 180, ya aterrizada). La tasa es de
vuelo; en Tierra no aplica. Decision del usuario (2026-10-21): en posvuelo la banda se congela
en el dia de regreso y lo dice. La fase y el dia de regreso son los de `core/mission.py`
(`phase_at` declara posvuelo desde `duration_days`, y ese es el dia de regreso): aqui no se abre
otro calendario.

Lo que pasa despues no se estima. Solo se da lo que dice una fuente leida sobre la recuperacion
(`ochmo-mtb-013`, paginas 2 y 20, leidas el 2026-10-21): el hueso cortical se recupera bien y el
trabecular puede no recuperarse, y NASA la sigue en Tierra con densitometria. La ficha no trae
una tasa de recuperacion, asi que la banda no baja: se queda donde estaba al regresar. Fuera del
posvuelo nada cambia, y la banda sigue sin puntuar ni alertar.

Queda sin decidir, y se dice: en vuelo la trayectoria todavia puede mostrar horizontes
posteriores al dia de regreso (el 365 de una mision de 180, «si nada cambia»). La decision del
usuario cubre el posvuelo y aqui no se amplia.
"""

from __future__ import annotations

from typing import Any

from app.core import i18n
from app.core.mission import MissionPhase
from app.evidence import registry
from app.ingest.simulator import LITERATURE

BMD_MODEL = "bmd-banda-nasa-1-1,5pct-mes@1"
# De donde sale la banda: su ficha en el registro unico de evidencia (`evidence/registry.py`).
BMD_SOURCE = registry.cite("nasa-human-body-in-space")
_LOW_PCT_PER_MONTH = 1.0
_HIGH_PCT_PER_MONTH = 1.5
_DAYS_PER_MONTH = 30.44
# Horizontes que se muestran: el dia actual y lo que vendria si nada cambia.
_HORIZON_DAYS = (30, 90, 180, 365)

# El corte en el regreso (ver cabecera). Las palabras las da el backend; la cifra del dia es
# `now.mission_day`, que ya es la del regreso, y la pinta la interfaz con su formato.
RETURN_CUT_LABEL = "hasta el día de regreso"
RETURN_CUT_BASIS = (
    "La banda es de pérdida en vuelo: en posvuelo se detiene en el día de regreso y no sigue "
    "contando en Tierra"
)
# Lo que dice una fuente leida de la recuperacion: solo eso, con su ficha.
RECOVERY_SOURCE = registry.cite(
    "ochmo-mtb-013", "lo que dice NASA de la recuperación ósea tras el vuelo (páginas 2 y 20)"
)
RECOVERY_STATEMENT = (
    "Según el resumen técnico de NASA sobre la pérdida ósea, tras el vuelo el hueso cortical "
    "se recupera bien y el trabecular puede no recuperarse; la recuperación se sigue en Tierra "
    "con densitometría (DXA) a los 6 meses y a 1, 2 y 3 años del regreso, o hasta volver al "
    "valor previo. EMMA no estima la recuperación: la ficha no da una tasa, y la banda se queda "
    "en el día de regreso."
)


def english_relevance(citation: registry.Citation, english: str) -> None:
    """Registra el inglés del «para qué» de una cita (`core/i18n.py`); lo sirve `cited`.

    El «para qué» lo escribe quien cita, no el registro de evidencia: por eso su inglés se pone
    aquí, junto a la cita, y no en la ficha. También lo usan `densitometry` y `baseline_profile`.
    """
    if citation.relevance is not None:
        i18n.en(citation.relevance, english)


def cited(citation: registry.Citation) -> dict[str, Any]:
    """La ficha como se sirve, con el «para qué» de esta cita en el idioma de la petición."""
    relevance = citation.relevance
    return {
        **citation.to_dict(),
        "relevance": i18n.loc(relevance) if relevance is not None else None,
    }


# El inglés de lo de arriba; se resuelve al servir, en `bone_density_band`.
i18n.en(RETURN_CUT_LABEL, "up to the return day")
i18n.en(
    RETURN_CUT_BASIS,
    "The band is of in-flight loss: postflight it stops at the return day and does not keep "
    "counting on Earth",
)
english_relevance(
    RECOVERY_SOURCE, "what NASA says about bone recovery after flight (pages 2 and 20)"
)
i18n.en(
    RECOVERY_STATEMENT,
    "According to NASA's technical brief on bone loss, after flight cortical bone recovers well "
    "and trabecular bone may not recover; recovery is followed on Earth with densitometry (DXA) "
    "at 6 months and at 1, 2 and 3 years after return, or until the previous value is reached. "
    "EMMA does not estimate recovery: the brief gives no rate, and the band stays at the return "
    "day.",
)


def loss_band(days: float) -> dict[str, float]:
    """La banda de perdida a un dia de mision, redondeada como se sirve.

    La usa tambien la comparacion con la densitometria (`analysis/densitometry.py`), que tiene
    que comparar con la misma cifra que se ensena, no con otra calculada aparte.
    """
    months = days / _DAYS_PER_MONTH
    return {
        "mission_day": round(days, 1),
        "loss_pct_low": round(_LOW_PCT_PER_MONTH * months, 2),
        "loss_pct_high": round(_HIGH_PCT_PER_MONTH * months, 2),
    }


def bone_density_band(
    mission_day: float,
    exercise_logged: bool,
    exercise: dict[str, Any] | None = None,
    *,
    phase: MissionPhase | None = None,
    return_day: float | None = None,
    densitometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Banda de perdida de densidad mineral osea estimada, hoy y a varios horizontes.

    `exercise` es lo MEDIDO que la acompana (`exercise_summary.measured`): va al lado, rotulado
    como medido, y no entra en la banda. `now` y `trajectory` solo dependen del dia de mision,
    salvo en posvuelo: con `phase` posvuelo la banda se detiene en `return_day` (el
    `duration_days` de la mision), no proyecta y lleva `cut` con lo que dice la fuente.
    `densitometry` es la densitometria MEDIDA puesta junto a la banda
    (`densitometry.against_band`): va al lado, tal cual, y tampoco la mueve.
    """
    day = max(0.0, mission_day)
    returned = phase is MissionPhase.POSTFLIGHT
    if returned:
        if return_day is None:
            raise ValueError("en posvuelo la banda necesita el día de regreso")
        day = min(day, max(0.0, return_day))

    # La banda a un dia, la misma que lee la comparacion con la densitometria.
    band = loss_band

    source = LITERATURE["bmd_loss_pct_per_month"]
    state: dict[str, Any] = {
        "key": "bone-mineral-density-loss",
        "display": i18n.tr(
            "Pérdida de densidad mineral ósea en huesos de carga",
            "Bone mineral density loss in weight-bearing bones",
        ),
        "unit": "%",
        "observation_type": "inferred",
        "model_version": BMD_MODEL,
        "now": band(day),
        # En posvuelo no se proyecta: la tasa de vuelo no aplica en Tierra.
        "trajectory": (
            [] if returned else [band(float(item)) for item in _HORIZON_DAYS if item > day]
        ),
        "basis": i18n.tr(
            "banda de población sin contramedidas (1-1,5 % al mes, NASA) aplicada al día de "
            "misión; no es una medida de esta persona: la densidad ósea se mide antes y "
            "después del vuelo",
            "population band without countermeasures (1-1.5 % per month, NASA) applied to the "
            "mission day; it is not a measurement of this person: bone density is measured "
            "before and after the flight",
        ),
        "source": cited(BMD_SOURCE),
        "evidence_class": source.evidence,
        "exercise_note": (
            i18n.tr(
                "Hay registro de ejercicio: el ejercicio resistivo reduce la pérdida, pero su "
                "efecto no tiene magnitud citable y la banda no se ajusta.",
                "There is an exercise record: resistive exercise reduces the loss, but its "
                "effect has no citable magnitude and the band is not adjusted.",
            )
            if exercise_logged
            else i18n.tr(
                "Sin registro de ejercicio en los datos: la banda es la de sin contramedidas.",
                "No exercise record in the data: the band is the one without countermeasures.",
            )
        ),
    }
    if exercise is not None:
        # Con lo medido delante, la nota dice la verdad en tres casos (hay registro, no lo hay,
        # lo hay y es 0) en vez de dar por registro una lectura de 0 minutos. Solo es texto.
        state["exercise_note"] = exercise["record"]["note"]
        state["exercise"] = exercise
    if returned:
        # Solo en posvuelo: fuera de el la banda sale como antes, campo a campo.
        state["cut"] = {
            "phase": str(MissionPhase.POSTFLIGHT),
            "label": i18n.loc(RETURN_CUT_LABEL),
            "basis": i18n.loc(RETURN_CUT_BASIS),
            "recovery": i18n.loc(RECOVERY_STATEMENT),
            "recovery_source": cited(RECOVERY_SOURCE),
        }
    if densitometry is not None:
        # Solo si hay alguna densitometria del tripulante: sin ella la banda sale como antes.
        state["densitometry"] = densitometry
    return state
