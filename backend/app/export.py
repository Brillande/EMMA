# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exportar a PDF lo que EMMA ya muestra, con `md_to_pdf_pro` de Polaris tal cual.

Por qué existe: un informe para Tierra, para el médico de vuelo o para el expediente se lee fuera
de la consola, y el estado de la consola cambia con cada lectura. Un PDF fecha la foto. Polaris ya
convierte Markdown en PDF con reportlab (títulos, listas y tablas); aquí EMMA escribe el Markdown
**solo con texto del backend** (resumen, detalle de cada alerta, recomendaciones, dosier,
crónica, anotaciones de dolor) y lo pasa por esa función.

`md_to_pdf_pro.main()` lee `sys.argv` y pone a todo PDF el título del caso de su autora. Las dos
cosas se sustituyen durante la llamada y bajo cerrojo (patrón de `reports/identity.py`): la copia
no se toca. Los colores de sus encabezados son los de Polaris: un PDF no es la interfaz y la
tabla F.5-1 no le aplica.

Licencia y origen (AGPL §5a): usa `polaris/tools/md_to_pdf_pro.py` de la copia literal de Polaris,
sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: el Markdown que se le pasa y la
sustitución temporal de `sys.argv` y del título.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import sys
import tempfile
import threading
from functools import cache
from pathlib import Path
from typing import Any

from app import polaris
from app.core.mission import mission_day
from app.pain.catalog import CHARACTERS, MAX_INTENSITY, ZONES
from app.polaris import console

# Protege `sys.argv` y el título sustituido. Se toma ANTES que el de consola
# (`app/polaris/console.py`), nunca al revés.
_LOCK = threading.Lock()
KINDS = ("estado", "dosier", "cronica", "dolor")


@cache
def _tool() -> Any:
    return polaris.load("md_to_pdf_pro")


def _cell(text: object) -> str:
    """Una celda de tabla Markdown: sin barras ni saltos que rompan la fila."""
    return str(text).replace("|", "/").replace("\n", " ").strip() or "—"


def status_markdown(status: dict[str, Any], now: dt.datetime) -> str:
    """El estado de salud tal cual lo da `/api/status`: resumen, alertas con detalle, consejo."""
    lines = [
        f"# EMMA — estado de salud de {status.get('subject', '—')}",
        "",
        f"Generado el {now:%Y-%m-%d %H:%M} UTC. Apoyo a la decisión, no prescripción.",
        "",
        "## Resumen",
        "",
        str(status.get("summary") or "—"),
        "",
        "## Alertas",
        "",
    ]
    alerts = status.get("alerts") or []
    if not alerts:
        lines.append("Sin alertas activas.")
    for alert in alerts:
        detail = alert.get("detail") or {}
        lines += [f"### {alert.get('domain')} · {alert.get('level')}", ""]
        for item in [*(detail.get("changed") or []), *(detail.get("trends") or [])]:
            lines.append(f"- {item.get('description')}")
        if detail.get("onset_basis"):
            lines.append(f"- Desde cuándo: {detail['onset_basis']}")
        if detail.get("ridge_display"):
            lines.append(f"- Peligro RIDGE de NASA: {detail['ridge_display']}")
        state = (alert.get("resolution") or {}).get("state")
        if alert.get("acknowledged"):
            lines.append(f"- Reconocida por {alert.get('acknowledged_by')}; estado: {state}")
        dismissal = alert.get("dismissal")
        if dismissal:
            # Lo último que se dijo de ella: va aparte del estado declarado (§5.37.6).
            lines.append(
                f"- Descartada por {dismissal.get('declared_by')}; motivo: "
                f"{dismissal.get('reason_display')}"
            )
        lines.append("")
    lines += ["## Qué comprobar", ""]
    recommendations = status.get("recommendations") or []
    if not recommendations:
        lines.append("Sin recomendaciones.")
    else:
        lines += ["| Dominio | Acción | Urgencia |", "|---|---|---|"]
        lines += [
            f"| {_cell(item.get('domain'))} | {_cell(item.get('action'))} "
            f"| {_cell(item.get('urgency'))} |"
            for item in recommendations
        ]
    return "\n".join(lines) + "\n"


def dossier_markdown(state: dict[str, Any], now: dt.datetime) -> str:
    lines = [
        "# EMMA — dosier de evidencia",
        "",
        f"Generado el {now:%Y-%m-%d %H:%M} UTC.",
        "",
        f"- Piezas: {state.get('pieces')}",
        f"- Entregable: {'sí' if state.get('deliverable') else 'no'}",
        f"- Vigencia de una revisión: {state.get('ttl_days')} días",
        "",
        "| Estado | Piezas |",
        "|---|---|",
        *[f"| {_cell(key)} | {value} |" for key, value in (state.get("by_state") or {}).items()],
        "",
    ]
    blocked = state.get("blocked") or []
    if blocked:
        lines += ["## Lo que impide entregarlo", "", *[f"- {item}" for item in blocked]]
    return "\n".join(lines) + "\n"


def _utc(iso: str) -> str:
    return f"{dt.datetime.fromisoformat(iso).astimezone(dt.UTC):%Y-%m-%d %H:%M}"


def chronicle_markdown(chronicle: dict[str, Any], subject: str, now: dt.datetime) -> str:
    """La crónica de `/api/timeline/chronicle`: hasta cuándo cuenta y los hechos por etapa.

    `now` fecha el documento (cuándo se generó). Hasta dónde llegan los hechos lo dice el `as_of`
    de la crónica, que va en el tiempo de los datos y declara de dónde sale: con una misión
    simulada las dos fechas pueden distar meses, y confundirlas falsearía el documento.
    """
    lines = [
        f"# EMMA — crónica de {subject}",
        "",
        f"Generada el {now:%Y-%m-%d %H:%M} UTC, desde el ledger firmado y el estado calculado.",
        "",
    ]
    if chronicle.get("as_of"):
        lines += [
            f"Hechos hasta el {_utc(chronicle['as_of'])} UTC ({chronicle.get('as_of_basis')}).",
            "",
        ]
    events = chronicle.get("events") or []
    if not events:
        lines.append("Sin hechos que contar todavía.")
    for stage in chronicle.get("stages") or []:
        found = [item for item in events if item["stage"] == stage["key"]]
        if not found:
            continue
        # La carrera no tiene instante: tiene el día que declaró una persona.
        clock = "Día declarado" if stage["key"] == "career" else "Instante (UTC)"
        lines += [
            f"## {stage['display']}",
            "",
            f"| {clock} | Día de misión | Qué | Quién | Fuente |",
            "|---|---|---|---|---|",
        ]
        for item in found:
            day = "" if item["mission_day"] is None else item["mission_day"]
            # Una fecha declarada (la carrera) va con su día y sin hora: la hora sería una
            # precisión que nadie declaró.
            at = item["fecha"] if item.get("time_basis") == "declared" else _utc(item["at"])
            lines.append(
                f"| {at} | {_cell(day)} | {_cell(item['que'])} "
                f"| {_cell(item['quien'])} | {_cell(item['fuente'])} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _note_heading(origin: object) -> str:
    """Qué es la nota de un informe de dolor, según el origen que se firmó con ella.

    Una nota dictada la transcribió un modelo (`app/voice.py`) y la revisó quien informa; nadie
    más. Presentarla como texto comprobado sería atribuirle a EMMA una verificación que no hace.
    """
    if origin == "escrita":
        return "Nota escrita por quien informa, tal como la firmó:"
    if origin == "dictada-revisada":
        return (
            "Nota dictada: la transcribió un modelo local de voz a texto y quien informa la "
            "revisó antes de firmarla. EMMA no la ha corregido ni verificado:"
        )
    if origin == "asistente-confirmada":
        return (
            "Nota de un informe preparado por el asistente de voz: son las palabras de quien "
            "informa, tal como las entendió la transcripción, y quien informa confirmó el informe "
            "antes de firmarlo. EMMA no la ha corregido ni verificado:"
        )
    return f"Nota de origen declarado «{origin}», sin verificar:"


def pain_markdown(
    reports: list[dict[str, Any]],
    subject: str,
    now: dt.datetime,
    as_of: dict[str, str],
    mission_start: dt.date,
    until: dt.datetime | None = None,
) -> str:
    """Las anotaciones de dolor de `/api/pain/reports`, una por apartado, con su procedencia.

    Describe lo firmado y nada más: zona, tipo e intensidad con los nombres del catálogo, la marca
    «comentar con el médico de a bordo» que ya calcula `app/pain/alarm.py` y la nota. No resume,
    no compara informes y no deduce nada de que falten: sin informes dice que el ledger no tiene
    ninguno, que no es lo mismo que «sin dolor».
    """
    lines = [
        f"# EMMA — anotaciones de dolor de {subject}",
        "",
        f"Generado el {now:%Y-%m-%d %H:%M} UTC, desde el ledger firmado. Descriptivo: apoyo a la "
        "decisión, no prescripción ni diagnóstico.",
        "",
        f"Estado de los datos: hasta el {_utc(as_of['as_of'])} UTC ({as_of['as_of_basis']}).",
        "",
    ]
    if until is not None:
        lines += [
            f"Solo lo recibido hasta el corte del {until.astimezone(dt.UTC):%Y-%m-%d %H:%M} UTC, "
            "por la hora de firma de cada asiento.",
            "",
        ]
    if not reports:
        lines.append("Sin anotaciones de dolor en el ledger.")
    for report in reports:
        day = math.floor(mission_day(dt.datetime.fromisoformat(report["effective"]), mission_start))
        # Un informe anterior al despegue no tiene día de misión: se dice, no se numera en negativo.
        met = f"día de misión {day}" if day >= 0 else "antes del inicio de la misión"
        peak = report.get("intensity")
        lines += [
            f"## {_utc(report['effective'])} UTC · {met}",
            "",
            f"- Informa: {_cell(report.get('reported_by'))}",
            # La lectura es un número del catálogo (float); la escala verbal es de enteros.
            f"- Intensidad máxima: {_cell(f'{peak:g}' if isinstance(peak, float) else peak)} "
            f"de {MAX_INTENSITY}",
            f"- Procedencia: asiento {report.get('ledger_index')} del ledger, firmado el "
            f"{_utc(report['recorded'])} UTC",
        ]
        discuss = report.get("discuss") or {}
        if discuss.get("reasons"):
            # Las frases y la nota son las de `app/pain/alarm.py`; aquí solo se dice qué son.
            lines.append(
                f"- Marca informativa, no una alerta: {'; '.join(discuss['reasons'])}. "
                f"{discuss.get('note') or ''}".rstrip()
            )
        lines.append("")
        zones = report.get("zones") or []
        if not zones:
            lines += ["Informe sin zonas marcadas.", ""]
        else:
            lines += [f"| Zona | Tipo | Intensidad (0-{MAX_INTENSITY}) |", "|---|---|---|"]
            for zone in zones:
                key = str(zone.get("zone"))
                kinds = [
                    CHARACTERS[kind].display if kind in CHARACTERS else str(kind)
                    for kind in zone.get("characters") or []
                ]
                lines.append(
                    f"| {_cell(ZONES[key].display if key in ZONES else key)} "
                    f"| {_cell(', '.join(kinds))} | {_cell(zone.get('intensity'))} |"
                )
            lines.append("")
        if report.get("note"):
            # Cita en una sola línea: un salto o una almohadilla dentro de la nota no deben
            # abrir un título ni una tabla en el documento.
            text = re.sub(r"\s+", " ", str(report["note"])).strip()
            lines += [_note_heading(report.get("note_origin")), "", f"> {text}", ""]
    return "\n".join(lines) + "\n"


def to_pdf(markdown: str, title: str) -> bytes:
    """El Markdown en PDF con la función de Polaris; el título del documento es el de EMMA."""
    tool = _tool()
    original = tool.SimpleDocTemplate

    def titled(*args: Any, **kwargs: Any) -> Any:
        kwargs["title"] = title
        return original(*args, **kwargs)

    with tempfile.TemporaryDirectory() as folder, _LOCK:
        source, target = Path(folder) / "entrada.md", Path(folder) / "salida.pdf"
        source.write_text(markdown, encoding="utf-8")
        saved_argv = sys.argv
        tool.SimpleDocTemplate = titled
        sys.argv = ["md_to_pdf_pro", str(source), str(target)]
        try:
            # Imprime la ruta del PDF: a la consola no le sirve, y en Windows puede no codificarse.
            # La consola es de todo el proceso: se captura bajo el cerrojo común.
            with console.captured():
                tool.main()
        finally:
            sys.argv = saved_argv
            tool.SimpleDocTemplate = original
        return target.read_bytes()
