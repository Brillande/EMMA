"""La historia recalculada de las alertas, de solo lectura (`app/analysis/alert_history.py`).

Por qué está aparte de `/api/status`: el estado firma instantáneas de predicción al consultarlo
y verifica la cadena entera. Recalcular el pasado no puede hacer ninguna de las dos cosas: aquí
se llama a `_assess` (lecturas → línea base → tendencia → riesgo, sin escribir) una sola vez, y
cada paso anterior se evalúa con el mismo `RiskEngine` sobre las desviaciones que ese cálculo ya
dejó hechas. Es lo que hace `routes._previous_levels` para una ventana atrás, repetido.

En qué se aparta de `_previous_levels`, y por qué: aquél mira dos días atrás y usa el contexto
externo de hoy. Cuarenta días atrás eso sería atribuir al pasado un evento solar de hoy o la
dosis acumulada de hoy, y daría un episodio de radiación tan largo como la historia. Los pasos
anteriores se evalúan sin eventos solares (el estado solo guarda los vigentes) y con la dosis
acumulada registrada hasta ese paso; el tiempo de luz sí es el de hoy. La respuesta lo dice.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter

from app.analysis import alert_history
from app.analysis.risk import RiskEngine, RiskLevel
from app.api import routes
from app.api.routes import SettingsDep, StoreDep
from app.core import i18n
from app.core.config import Settings
from app.core.storage import DISMISSAL_REASONS, RULES_VERSION_FIELD, ObservationStore
from app.core.versioning import decided_with, rules_version
from app.ingest.codes import Domain

alert_history_router = APIRouter(prefix="/alerts")

EXTERNAL_BASIS = (
    "El contexto externo de los pasos anteriores no es el de entonces: se evalúan sin eventos "
    "solares (el sistema solo guarda los vigentes), con el tiempo de luz de hoy y con la "
    "radiación acumulada registrada hasta cada paso. El paso actual es el del estado, tal cual."
)

i18n.en(
    EXTERNAL_BASIS,
    "The external context of the earlier steps is not that of the time: they are assessed "
    "without solar events (the system only keeps the current ones), with today's light time "
    "and with the cumulative radiation recorded up to each step. The current step is that of "
    "the state, as is.",
)

_RESOLUTION_DISPLAY = {"en_arreglo": "en arreglo", "resuelto": "resuelta"}
_RESOLUTION_DISPLAY_EN = {"en_arreglo": "being fixed", "resuelto": "resolved"}
_ANNUNCIATION_DISPLAY = {
    "suppress": "anuncio suprimido", "inhibit": "anuncio inhibido",
    "enable": "anuncio rehabilitado",
}
_ANNUNCIATION_DISPLAY_EN = {
    "suppress": "announcement suppressed", "inhibit": "announcement inhibited",
    "enable": "announcement re-enabled",
}


def _level_at(settings: Settings, assessed: routes._Assessment) -> alert_history.LevelAt:
    """El nivel de cada dominio en un paso, con el motor del estado y sin escribir nada."""
    engine = RiskEngine(dose_limit_msv=settings.career_dose_limit_msv)
    # Las mismas que valoro el estado (`routes.DOSE_TYPES`: medidas o inferidas), ya ordenadas.
    doses = assessed.doses

    def level_at(start: dt.datetime, end: dt.datetime) -> dict[Domain, RiskLevel]:
        if end >= assessed.latest:
            # El paso actual no se recalcula: es, literalmente, lo que dice el estado.
            return {domain: risk.level for domain, risk in assessed.status.domains.items()}
        recorded = [obs.value for obs in doses if obs.effective < end]
        status = engine.assess(
            subject=assessed.status.subject,
            deviations=[dev for dev in assessed.deviations if start <= dev.effective < end],
            # Las de lo anterior al paso, una vez por evaluacion: el paso anterior al actual
            # es la ventana de `_previous_levels`, y en la cronica las dos piden lo mismo.
            trends=assessed.trends_before(end),
            comms=assessed.comms_window,
            solar_events=None,
            cumulative_dose_msv=recorded[-1] if recorded else 0.0,
        )
        return {domain: risk.level for domain, risk in status.domains.items()}

    return level_at


def _signed(
    store: ObservationStore, subject: str, until: dt.datetime | None
) -> list[dict[str, Any]]:
    """Lo firmado sobre una alerta, con la misma regla de qué cuenta que `/api/status`."""
    found: list[dict[str, Any]] = []

    def add(
        item: dict[str, Any], kind: str, display: str, by: str, *, decided: bool = True
    ) -> None:
        found.append({
            "ledger_index": item["ledger_index"], "kind": kind, "kind_display": display,
            "domain": item["domain"], "by": by, "reference_time": item["reference_time"],
            # Lo que este episodio recalculado hoy no puede decir por si mismo: con que reglas se
            # firmo cada decision (`record-integrity.md` §3.26). Se lee del asiento y se dice; el
            # episodio no se recalcula con ellas. Los anuncios no llevan el campo: `None`.
            "rules": decided_with(item.get(RULES_VERSION_FIELD)) if decided else None,
        })

    for item in store.acknowledgements(subject):
        if routes._counts(item, until):
            add(item, "acknowledgement",
                i18n.tr("alerta reconocida", "alert acknowledged"), item["acknowledged_by"])
    for item in store.alert_resolutions(subject):
        if routes._counts(item, until):
            add(item, "resolution",
                i18n.tr(
                    f"alerta declarada {_RESOLUTION_DISPLAY.get(item['state'], item['state'])}",
                    f"alert declared {_RESOLUTION_DISPLAY_EN.get(item['state'], item['state'])}",
                ),
                item["declared_by"])
    for item in store.alert_dismissals(subject):
        if routes._counts(item, until) and routes._acceptable_dismissal(item):
            add(item, "dismissal",
                i18n.tr(
                    f"alerta descartada: {DISMISSAL_REASONS[item['reason']]}",
                    f"alert dismissed: {i18n.loc(DISMISSAL_REASONS[item['reason']])}",
                ),
                item["declared_by"])
    for item in store.annunciation_changes(subject):
        if routes._counts(item, until) and routes._within_limits(item):
            action = item["action"]
            add(item, "annunciation",
                i18n.tr(
                    _ANNUNCIATION_DISPLAY.get(action, action),
                    _ANNUNCIATION_DISPLAY_EN.get(action, action),
                ),
                item["requested_by"],
                decided=False)
    return found


def history_view(
    settings: Settings,
    store: ObservationStore,
    subject: str,
    until: dt.datetime | None = None,
    assessed: routes._Assessment | None = None,
) -> dict[str, Any]:
    """Los episodios recalculados de un tripulante. Con `until`, con lo que Tierra tiene.

    `assessed` es la evaluacion ya hecha con estos mismos parametros (`_assess` sin epoca ni
    dosis, con este `until`), si quien llama la tiene: la cronica la comparte con su estado en
    vez de evaluar dos veces lo mismo. Sin ella se evalua aqui.
    """
    if assessed is None:
        assessed = routes._assess(settings, store, subject, None, None, until)
    earliest = min(obs.effective for obs in assessed.observations)
    steps = alert_history.walk(
        assessed.latest, earliest, routes.CURRENT_WINDOW, _level_at(settings, assessed)
    )
    payload = alert_history.describe(
        steps, earliest, routes.CURRENT_WINDOW, rules_version(), external_basis=EXTERNAL_BASIS
    )
    alert_history.attach_signed(payload["episodes"], _signed(store, subject, until))
    return {"subject": subject, "until": until.isoformat() if until else None, **payload}


@alert_history_router.get("/history")
def read_alert_history(
    store: StoreDep,
    settings: SettingsDep,
    subject: str = "crew-01",
    # Lo que Tierra puede tener: hasta el corte del retardo, como `/api/status`.
    until: dt.datetime | None = None,
) -> dict[str, Any]:
    """Episodios pasados por dominio, recalculados hoy con las reglas de hoy. No escribe nada."""
    return history_view(settings, store, subject, until)
