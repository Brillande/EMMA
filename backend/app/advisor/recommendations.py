"""Motor de recomendaciones: de "algo va mal" a "haz esto".

El reto pide que el astronauta pueda **actuar** sobre su estado, no solo verlo.
Un panel que muestra un numero rojo y no dice que hacer traslada el problema
entero a una persona cansada, sola y sin cirujano de vuelo al otro lado.

LIMITES DECLARADOS
------------------
Este modulo produce **apoyo a la decision**, no prescripcion. No indica
farmacos ni dosis, no diagnostica, y toda accion irreversible o invasiva queda
fuera. Es la frontera que sostiene la clasificacion IEC 62304 Clase B del
sistema (ver `compliance/software-safety-classification.md`): si el software
fallara, el dano posible no es grave porque no ejecuta terapia.

Cada recomendacion lleva su evidencia: el tripulante ve en que se apoya y puede
discrepar con criterio.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.advisor import countermeasures
from app.advisor.countermeasures import Countermeasure
from app.analysis.risk import CrewHealthStatus, RiskLevel
from app.core import i18n
from app.evidence.links import EvidenceItem, countermeasure_evidence
from app.ingest.codes import Domain


class Urgency(StrEnum):
    ROUTINE = "routine"
    SOON = "soon"
    IMMEDIATE = "immediate"


_URGENCY_BY_LEVEL: dict[RiskLevel, Urgency] = {
    RiskLevel.NOMINAL: Urgency.ROUTINE,
    RiskLevel.WATCH: Urgency.ROUTINE,
    RiskLevel.CONCERN: Urgency.SOON,
    RiskLevel.CRITICAL: Urgency.IMMEDIATE,
}


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Una accion concreta que el tripulante puede ejecutar por si mismo."""

    domain: Domain
    action: str
    rationale: str
    urgency: Urgency
    evidence: tuple[EvidenceItem, ...]
    # Si la situacion justifica avisar a Tierra pese al retardo.
    notify_ground: bool = False
    # La contramedida de la biblioteca de la que sale la accion (recursos, tiempo,
    # protocolo, seguimiento). La accion y la evidencia de arriba salen de ella.
    countermeasure: Countermeasure | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "domain": str(self.domain),
            # La acción es texto de la biblioteca: su inglés, del hermano de `countermeasures.json`
            # (`Countermeasure.to_dict` hace lo mismo con la entrada entera).
            "action": i18n.localized(self.action, countermeasures.LIBRARY_PATH),
            "rationale": self.rationale,
            "urgency": str(self.urgency),
            "notify_ground": self.notify_ground,
            "evidence": [item.to_dict() for item in self.evidence],
            "countermeasure": (
                self.countermeasure.to_dict() if self.countermeasure is not None else None
            ),
        }


# Las contramedidas viven como datos en `app/data/countermeasures.json`, con recursos,
# tiempo, protocolo y seguimiento (`advisor/countermeasures.py`). Todas ejecutables por la
# tripulacion a bordo y reversibles: nada invasivo, nada farmacologico.


def _evidence(item: Countermeasure) -> tuple[EvidenceItem, ...]:
    """El protocolo propio de la contramedida primero; despues, el riesgo del dominio."""
    own: tuple[EvidenceItem, ...] = (
        (item.protocol_ref,) if item.protocol_ref is not None else ()
    )
    domain = tuple(countermeasure_evidence(item.domain)) if item.domain is not None else ()
    return own + domain


class Advisor:
    """Convierte un estado de salud en acciones concretas y justificadas."""

    def recommend(
        self,
        status: CrewHealthStatus,
        driver_keys: dict[Domain, set[str]] | None = None,
    ) -> list[Recommendation]:
        """Acciones por dominio, las que siguen a las variables del hallazgo primero.

        `driver_keys` son los indicadores que llevan cada dominio a su nivel. Sin ellos, el
        orden de la biblioteca: con la hidratacion y la retencion en el mismo dominio, una
        orina de 24 h a la baja recibia antes "intentar la miccion" que "repartir el agua".
        """
        recommendations: list[Recommendation] = []
        keys_by_domain = driver_keys or {}

        # El evento solar activo va primero: es lo unico con ventana de minutos.
        if status.active_solar_event is not None:
            shelter = countermeasures.get(countermeasures.SHELTER_ID)
            recommendations.append(
                Recommendation(
                    domain=Domain.RADIATION,
                    action=shelter.action,
                    rationale=i18n.tr(
                        f"Evento solar activo ({status.active_solar_event.event_type} "
                        f"{status.active_solar_event.event_id}) detectado por NASA DONKI.",
                        f"Active solar event ({status.active_solar_event.event_type} "
                        f"{status.active_solar_event.event_id}) detected by NASA DONKI.",
                    ),
                    urgency=Urgency.IMMEDIATE,
                    evidence=_evidence(shelter),
                    notify_ground=True,
                    countermeasure=shelter,
                )
            )

        for risk in status.domains_needing_attention():
            urgency = _URGENCY_BY_LEVEL[risk.level]
            drivers = keys_by_domain.get(risk.domain, set())
            actions = sorted(
                countermeasures.for_domain(risk.domain),
                # Estable: dentro de cada grupo se conserva el orden de la biblioteca.
                key=lambda item: not (set(item.followup_checks) & drivers),
            )
            # Cuantas acciones se ofrecen segun la urgencia: ante una situacion
            # critica, una lista larga es ruido.
            count = 1 if urgency is Urgency.IMMEDIATE else (2 if urgency is Urgency.SOON else 3)

            for item in actions[:count]:
                recommendations.append(
                    Recommendation(
                        domain=risk.domain,
                        action=item.action,
                        rationale=risk.describe(),
                        urgency=urgency,
                        evidence=_evidence(item),
                        notify_ground=risk.level is RiskLevel.CRITICAL,
                        countermeasure=item,
                    )
                )

        return recommendations

    def summarize(self, status: CrewHealthStatus) -> str:
        """Una frase para encabezar la pantalla: lo primero que se lee."""
        if status.overall_level is RiskLevel.NOMINAL:
            return i18n.tr(
                "Estado nominal. Sin hallazgos que requieran acción.",
                "Nominal status. No findings requiring action.",
            )

        attention = status.domains_needing_attention()
        worst = attention[0]
        others = len(attention) - 1
        # «Bajo vigilancia» no: «vigilancia» es el nombre del nivel WATCH (`risk._LEVEL_DISPLAY`),
        # y los otros dominios pueden estar en precaución o en crítico. Con dos dominios críticos
        # la frase decía que el segundo estaba «bajo vigilancia», un nivel por debajo del suyo.
        tail = i18n.tr(
            f" y {others} dominio(s) más fuera de nominal",
            f" and {others} more domain(s) outside nominal",
        ) if others else ""

        prefix = ""
        if status.comms is not None and status.comms.autonomy_required:
            prefix = i18n.tr(
                f"Sin consulta en vivo con Tierra "
                f"({status.comms.round_trip_minutes:.0f} min ida y vuelta). ",
                f"No live consultation with Earth "
                f"({status.comms.round_trip_minutes:.0f} min round trip). ",
            )

        return i18n.tr(
            f"{prefix}Atención en el dominio {worst.domain.display} "
            f"({worst.level.display}){tail}.",
            f"{prefix}Attention in the {worst.domain.display} domain "
            f"({worst.level.display}){tail}.",
        )
