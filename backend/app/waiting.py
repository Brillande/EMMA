# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lo que espera por una persona: `atascos.esperan_por_titular` de Polaris, con lo de EMMA.

Por qué existe: EMMA no actúa solo (invariante 7) y por eso deja cosas a la espera de alguien:
una alerta sin reconocer, una cifra de analítica sin confirmar, un borrador sin firmar. Cada una
se ve en su panel, pero nadie mira cuánto lleva cada una esperando. Polaris lo vio en su caso: «si
el cuello de botella eres tú, cambia el proceso»; sin un resumen, lo que espera se olvida.

Se usa su `esperan_por_titular()` tal cual: cuenta los días desde `esperando_desde`, se queda con
lo que lleva 3 días o más (su `ESPERA_DIAS`) y lo ordena del más viejo al más nuevo. Lo que espera
por una persona lo decide su `seguimiento._manos` por la marca `gate`, nunca por el texto. Lo que
EMMA le da son hilos con esa forma.

Dos relojes, que no se mezclan: lo que nace de los datos (alertas, medidas) cuenta con la hora de
los datos; lo que nace de una acción en el ledger (informes, borradores, "en arreglo"), con la
hora en que se registró. Con el simulador, los datos van por delante del reloj.

Para Tierra (`until`), lo que Tierra puede saber en su corte, con la regla del resto de su consola
(`/api/status`, la crónica): solo cuenta lo firmado hasta el corte —un informe, una confirmación,
un borrador, una firma, un «en arreglo»—, y una firma o una confirmación posterior al corte no ha
llegado, así que lo suyo sigue esperando. El reloj del registro se para en el corte, sin pasar del
reloj real: un asiento no puede ser de después de hoy.

El estado de una alerta («en arreglo», «resuelto») es el último que firmó la consola, con la regla
de `action_counts` que usa el estado: un asiento de ese tipo firmado por otra identidad no cuenta
para el estado y tampoco aquí (antes se tomaba el último fuera quien fuera, §5.37.13).

Los títulos nombran el dominio como lo nombra el resto de la interfaz (`codes.domain_name`), no por
su clave de la API: el panel decía «Alerta immune sin reconocer».

No se usan su `propuestas_de_proceso` ni su `bloque`: proponen pasar trabajo a su asistente
("Vega") y le hablan a su autora. Las incongruencias se enseñan siempre, sin esperar 3 días, como
hace su `bloque`.

Licencia y origen (AGPL §5a): usa `polaris/tools/atascos.py` de la copia literal de Polaris, sin
modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: los hilos que se le dan y sus dos
relojes.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from functools import cache
from typing import Any

from app import polaris
from app.core.identities import action_counts
from app.ingest.codes import domain_name


@cache
def _tool() -> Any:
    return polaris.load("atascos")


def _thread(title: str, kind: str, since: str) -> dict[str, Any]:
    """Un hilo con la forma del Tablero de Polaris: abierto y con el paso en manos de alguien."""
    return {"titulo": title, "etiqueta": kind, "estado": "esperando", "gate": kind,
            "esperando_desde": since[:10]}


def unacknowledged_title(domain: str) -> str:
    """El título del hilo de una alerta sin reconocer (las cinco preguntas lo buscan por él)."""
    return f"Alerta {domain_name(domain)} sin reconocer"


def _instant(text: str) -> dt.datetime:
    moment = dt.datetime.fromisoformat(text)
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.UTC)


def _known(item: dict[str, Any] | None, until: dt.datetime | None) -> bool:
    """Un asiento existe para Tierra si se firmó en su corte o antes (el corte de tiempo de
    `identities.action_counts`). Quién lo firmó se mira solo en el estado de una alerta:
    un informe, una confirmación o un borrador esperan aunque no los firme la consola."""
    if item is None:
        return False
    return until is None or _instant(str(item["recorded"])) <= until


def threads(status: dict[str, Any], store: Any, routines: dict[str, Any],
            subject: str, until: dt.datetime | None = None,
            reports: Sequence[dict[str, Any]] | None = None,
            ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(hilos con la hora de los datos, hilos con la hora del registro).

    Con `until`, el estado y las rutinas ya vienen cortados; lo del registro se corta aquí.
    `reports` son los informes ya cortados (`reports_known`) si quien llama los tiene: así se
    cortan una vez por petición; sin ellos se cortan aquí.
    """
    data_clock: list[dict[str, Any]] = []
    record_clock: list[dict[str, Any]] = []
    for alert in status.get("alerts") or []:
        if not alert.get("acknowledged"):
            since = (alert.get("detail") or {}).get("onset") or status["data"]["reference_time"]
            data_clock.append(_thread(unacknowledged_title(alert["domain"]), "reconocer",
                                      str(since)))
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    # Un «en arreglo» o un «resuelto», con la regla del estado: la misma función, no una copia.
    for item in store.alert_resolutions(subject):
        if action_counts(item, until):
            latest[(item["domain"], item["level"])] = item
    # Una alerta descartada después de declararla «en arreglo» ya no espera a nadie: vale lo
    # último que se dijo de ella (§5.37.6, `record-integrity.md` §3.20 bis).
    for item in store.alert_dismissals(subject):
        key = (item["domain"], item["level"])
        if _known(item, until) and key in latest and (
            item["ledger_index"] > latest[key]["ledger_index"]
        ):
            del latest[key]
    for (domain, _level), item in latest.items():
        if item["state"] == "en_arreglo":
            record_clock.append(_thread(f"Alerta {domain_name(domain)} en arreglo", "resolver",
                                        str(item["recorded"])))
    for routine in routines.get("routines") or []:
        # Una suspendida por el nivel de misión no la debe nadie (`routines.with_mission_level`).
        if routine.get("suspended"):
            continue
        if routine["state"] == "rota" and routine.get("last_success"):
            data_clock.append(_thread(f"{routine['display_es']}: sin lectura buena", "medir",
                                      str(routine["last_success"])))
    if reports is None:
        reports = reports_known(store, subject, until)
    for report in reports:
        readings = (report.get("lab_readings") or {}).get("readings") or []
        done = {
            item["reading_index"] for item in store.lab_confirmations(report["ledger_index"])
            if _known(item, until)
        }
        pending = len(readings) - len(done)
        if pending > 0:
            record_clock.append(_thread(
                f"{pending} {'cifra' if pending == 1 else 'cifras'} sin confirmar en el informe "
                f"{report['ledger_index']}",
                "confirmar", str(report["recorded"])))
    for study in store.imaging_studies(subject):
        if not _known(study, until):
            continue
        for draft in store.drafts(study["ledger_index"]):
            if not _known(draft, until):
                continue
            if draft.get("status") == "unvalidated" and not _known(draft.get("signoff"), until):
                record_clock.append(_thread(f"Borrador {draft['ledger_index']} sin firmar",
                                            "firmar", str(draft["recorded"])))
    return data_clock, record_clock


def reports_known(store: Any, subject: str, until: dt.datetime | None) -> list[dict[str, Any]]:
    """Los informes escaneados que Tierra tiene en su corte (todos, sin `until`)."""
    return [report for report in store.scanned_reports(subject) if _known(report, until)]


def waiting(status: dict[str, Any], store: Any, routines: dict[str, Any], subject: str,
            incongruences: list[dict[str, Any]], today: dt.date | None = None,
            until: dt.datetime | None = None,
            reports: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Lo que lleva días esperando a alguien, del más viejo al más nuevo, y lo que no cuadra.

    Con `until`, lo que Tierra sabe en su corte: quien llama da el estado, las rutinas y las
    incongruencias ya cortados (`reports_known` da los informes con que buscarlas; si los pasa
    en `reports`, no se vuelven a cortar).
    """
    data_clock, record_clock = threads(status, store, routines, subject, until, reports)
    data_today = dt.date.fromisoformat(str(status["data"]["reference_time"])[:10])
    # En UTC, como los asientos y el corte: con la fecha local, cerca de medianoche, un hilo
    # ganaba o perdía un día según la zona horaria del ordenador.
    record_today = today or dt.datetime.now(dt.UTC).date()
    if until is not None:
        record_today = min(record_today, until.astimezone(dt.UTC).date())
    tool = _tool()
    found = [
        *tool.esperan_por_titular(data_clock, data_today),
        *tool.esperan_por_titular(record_clock, record_today),
    ]
    found.sort(key=lambda pair: -pair[1])
    return {
        "threshold_days": tool.ESPERA_DIAS,
        "waiting": [{"title": item["titulo"], "kind": item["etiqueta"], "days": days,
                     "since": item["esperando_desde"]} for item, days in found],
        "incongruences": incongruences,
    }
