"""Cuanto se puede confiar en cada lectura, dicho a quien mira la pantalla.

POR QUE EXISTE
--------------
La especificacion del equipo (§2 y §10) pide *"mostrar confidence/quality"*. El
backend ya tenia la confianza de cada lectura y la usaba: una lectura por debajo
de `LOW_CONFIDENCE_THRESHOLD` no entra en la referencia de la linea base y no
sostiene mas que un hallazgo leve (`analysis/baseline.py`). Pero eso no salia de
aqui: la tripulacion veia "nominal" sin saber que el pulsometro llevaba una hora
sin contacto y que el analisis estaba descontando esas lecturas. Una decision que
el sistema toma por la calidad del dato y no ensena es una decision que nadie
puede revisar.

QUE NO HACE
-----------
No decide nada. Lee las lecturas y las desviaciones que el motor ya calculo y las
cuenta. No toca umbrales, linea base ni riesgo (invariante 5): el umbral es el de
`ingest/fhir.py` y la regla de "baja confianza" es la propiedad
`VitalObservation.is_low_confidence`, la misma que usa la linea base.

"NO DECLARADA" NO ES UN NUMERO
------------------------------
El ledger guarda siempre una confianza, y vale `FULL_CONFIDENCE` cuando nadie dice
otra cosa. Ese 1,0 no distingue "la fuente comprobo la medida y es buena" de "la
fuente no mide su calidad" —el simulador, una importacion de Apple Health o un
alta manual no declaran nada—. Presentarlo como "confianza 1,0" seria inventar
una cifra. Asi que un valor por defecto se informa como **no declarada**, sin
numero; solo una confianza distinta de la de por defecto se da por declarada.
El coste, que se asume: una fuente que declare 1,0 a proposito (un pulsometro BLE
con buen contacto) se lee igual que una que calla. Distinguirlas exigiria firmar
un campo nuevo en el ledger.

LA TENDENCIA NO MIRA LA CONFIANZA
---------------------------------
La linea base aparta las lecturas dudosas de su referencia; el ajuste de
tendencia (`analysis/trend.py`) no: usa todas. Aqui no se cambia —seria tocar el
analisis—, pero se dice. Un bloque que contara "el analisis las descuenta", sin
mas, afirmaria mas de lo que hace el codigo.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from app.analysis.baseline import Deviation, SeverityBasis
from app.core import display, i18n
from app.ingest import bindings
from app.ingest.codes import get
from app.ingest.fhir import FULL_CONFIDENCE, LOW_CONFIDENCE_THRESHOLD, VitalObservation


class QualityState(StrEnum):
    """Lo que se puede afirmar de la confianza de una lectura."""

    LOW = "low"
    DECLARED = "declared"
    UNDECLARED = "undeclared"


# Las palabras las pone el backend: la interfaz no redacta (invariante 7).
LABELS: dict[QualityState, str] = {
    QualityState.LOW: "baja confianza",
    QualityState.DECLARED: "confianza declarada",
    QualityState.UNDECLARED: "no declarada",
}
# Quien las sirva las resuelve con `i18n.loc` (aquí, `describe`; fuera, `alert_support`).
i18n.en_many({
    "baja confianza": "low confidence",
    "confianza declarada": "declared confidence",
    "no declarada": "not declared",
})

# Lo que el analisis NO hace con la confianza. `tests/test_data_quality.py` comprueba
# que sigue siendo verdad: si la tendencia empieza a descontarlas, esta frase sobra.
TREND_NOTE = (
    "La tendencia no distingue la confianza de la medida: su ajuste usa también las "
    "lecturas de baja confianza."
)
i18n.en(
    TREND_NOTE,
    "The trend does not distinguish measurement confidence: its fit also uses the "
    "low-confidence readings.",
)

# Como se nombra cada fuente que firma lecturas. Una que no este aqui se muestra con
# el nombre con que firmo: no se le inventa otro.
_SOURCE_LABELS: dict[str, str] = {
    "wearable-ble": "wearable BLE",
    "apple-health": "Apple Health",
    "google-fit": "Google Fit",
    "manual": "alta manual",
    "pvt-test": "test PVT",
    # Lo que una persona teclea en la consola, con su nombre firmado al lado (2026-10-13).
    "crew-diary": "registro diario",
    "console-pvt": "test PVT en la consola",
    # Las puntuaciones de la batería Cognition copiadas en la consola (2026-11-03).
    "console-cognition": "batería Cognition en la consola",
    "ultrasound": "ecografía",
    "pain-report": "informe de dolor",
}
_SOURCE_PREFIXES: dict[str, str] = {
    "simulator:": "simulador ({})",
    "analitica:": "analítica del informe {}",
}
# Los mismos nombres en inglés (`core/i18n.py`), por la misma clave. Tablas aparte y no el
# registro de `i18n.en`: son palabras cortas («ecografía») que otro módulo puede rotular distinto.
# Una fuente sin entrada aquí se nombra igual en los dos idiomas.
_SOURCE_LABELS_EN: dict[str, str] = {
    "manual": "manual entry",
    "pvt-test": "PVT test",
    "crew-diary": "daily log",
    "console-pvt": "PVT test on the console",
    "console-cognition": "Cognition battery on the console",
    "ultrasound": "ultrasound",
    "pain-report": "pain report",
}
_SOURCE_PREFIXES_EN: dict[str, str] = {
    "simulator:": "simulator ({})",
    "analitica:": "lab results of report {}",
}


def state_of(observation: VitalObservation) -> QualityState:
    """El estado de calidad de una lectura, con la misma regla que la linea base."""
    if observation.is_low_confidence:
        return QualityState.LOW
    if observation.confidence == FULL_CONFIDENCE:
        return QualityState.UNDECLARED
    return QualityState.DECLARED


def source_label(source: str) -> str:
    """El nombre legible de la fuente que firmo, o el que firmo si no se conoce."""
    for prefix, template in _SOURCE_PREFIXES.items():
        if source.startswith(prefix) and len(source) > len(prefix):
            template = i18n.tr(template, _SOURCE_PREFIXES_EN.get(prefix, template))
            return template.format(source[len(prefix):])
    name = _SOURCE_LABELS.get(source, source)
    return i18n.tr(name, _SOURCE_LABELS_EN.get(source, name))


def _readings(count: int) -> str:
    return i18n.tr(
        f"{display.number(count, 0)} {'lectura' if count == 1 else 'lecturas'}",
        f"{display.number(count, 0)} {'reading' if count == 1 else 'readings'}",
    )


def _span(window: dt.timedelta) -> tuple[str, str]:
    """La ventana de lo reciente, con su articulo: ("los", "últimos 2 días")."""
    hours = window / dt.timedelta(hours=1)
    if hours >= 48 and hours % 24 == 0:
        days = display.number(hours / 24, 0)
        return i18n.tr("los", "the"), i18n.tr(f"últimos {days} días", f"last {days} days")
    return i18n.tr("las", "the"), i18n.tr(
        f"últimas {display.number(hours, 0)} h", f"last {display.number(hours, 0)} h"
    )


def _summary_en(total: int, low: int, indicators: int, window: dt.timedelta) -> str:
    """`_summary` en inglés: la misma afirmación, con el orden de la frase inglesa."""
    span = " ".join(_span(window))
    if not low:
        return f"{_readings(total)} in {span}: none with low measurement confidence."
    one = low == 1
    return (
        f"{display.number(low, 0)} of {_readings(total)} from {span} with low measurement "
        f"confidence ({display.number(indicators, 0)} "
        f"{'indicator' if indicators == 1 else 'indicators'}): "
        f"{'it does' if one else 'they do'} not count as baseline reference and cannot on "
        f"{'its' if one else 'their'} own support more than a mild finding. "
        f"{i18n.loc(TREND_NOTE)}"
    )


def _summary(total: int, low: int, indicators: int, window: dt.timedelta) -> str:
    if i18n.current() == "en":
        return _summary_en(total, low, indicators, window)
    span = " ".join(_span(window))
    if not low:
        return f"{_readings(total)} en {span}: ninguna con baja confianza de medida."
    one = low == 1
    return (
        f"{display.number(low, 0)} de {_readings(total)} de {span} con baja confianza de medida "
        f"({display.number(indicators, 0)} {'indicador' if indicators == 1 else 'indicadores'}): "
        f"{'no cuenta' if one else 'no cuentan'} como referencia de la línea base y "
        f"{'no sostiene por sí sola' if one else 'no sostienen por sí solas'} más que un "
        f"hallazgo leve. {TREND_NOTE}"
    )


def _undeclared_note(total: int, undeclared: int) -> str | None:
    if not undeclared:
        return None
    one = undeclared == 1
    if i18n.current() == "en":
        return (
            f"{display.number(undeclared, 0)} of {display.number(total, 0)} recent "
            f"{'reading' if total == 1 else 'readings'} {'does' if one else 'do'} not declare "
            f"confidence: the record keeps the default one, which does not tell a checked "
            f"measurement from an unchecked one. "
            f"{'It is' if one else 'They are'} analysed as full confidence."
        )
    return (
        f"{display.number(undeclared, 0)} de {_readings(total)} recientes "
        f"{'no declara' if one else 'no declaran'} confianza: el registro guarda la de por "
        f"defecto, que no distingue una medida comprobada de una sin comprobar. "
        f"{'Se analiza como plena' if one else 'Se analizan como plenas'}."
    )


def _baseline_text(excluded: int, capped: int) -> str:
    if i18n.current() == "en":
        return _baseline_text_en(excluded, capped)
    if not excluded:
        return "sin lecturas apartadas por baja confianza"
    text = (
        f"{_readings(excluded)} de baja confianza entre las analizadas: "
        f"{'queda' if excluded == 1 else 'quedan'} fuera de la referencia de la línea base"
    )
    if capped:
        text += (
            f"; {display.number(capped, 0)} "
            f"{'hallazgo reciente limitado' if capped == 1 else 'hallazgos recientes limitados'}"
            f" a leve"
        )
    return text


def _baseline_text_en(excluded: int, capped: int) -> str:
    """`_baseline_text` en inglés."""
    if not excluded:
        return "no readings set aside for low confidence"
    text = (
        f"{_readings(excluded)} of low confidence among those analysed: "
        f"{'it is' if excluded == 1 else 'they are'} left out of the baseline reference"
    )
    if capped:
        text += (
            f"; {display.number(capped, 0)} recent "
            f"{'finding' if capped == 1 else 'findings'} capped at mild"
        )
    return text


def describe(
    observations: Sequence[VitalObservation],
    deviations: Sequence[Deviation],
    latest: dt.datetime,
    window: dt.timedelta,
    sensor_bindings: Sequence[dict[str, Any]] | None = (),
) -> dict[str, Any]:
    """La calidad del dato por indicador, sobre las lecturas que el analisis ya uso.

    `window` es la ventana de "lo reciente" del estado (`CURRENT_WINDOW`): la misma
    con la que se seleccionan las desviaciones que cuentan para el nivel.

    `sensor_bindings` son los vinculos sensor-tripulante declarados (`ingest/bindings.py`);
    `None`, que no se pudieron leer con garantias. Solo anaden el bloque `device_bindings`:
    nada de lo demas los lee, y las lecturas senaladas se cuentan aqui como todas.
    """
    cutoff = latest - window
    by_key: dict[str, list[VitalObservation]] = {}
    for obs in observations:
        by_key.setdefault(obs.key, []).append(obs)

    # Hallazgos recientes que el motor limito a leve por la confianza de la medida.
    capped: Counter[str] = Counter(
        dev.key
        for dev in deviations
        if dev.effective >= cutoff and dev.basis is SeverityBasis.LOW_CONFIDENCE
    )

    indicators: list[dict[str, Any]] = []
    totals: Counter[QualityState] = Counter()
    for key, series in by_key.items():
        code = get(key)
        last = max(series, key=lambda obs: obs.effective)
        state = state_of(last)
        recent = [obs for obs in series if obs.effective >= cutoff]
        states = Counter(state_of(obs) for obs in recent)
        totals.update(states)
        sources = Counter(obs.source for obs in recent)
        doubtful_sources = Counter(obs.source for obs in recent if obs.is_low_confidence)
        # La linea base aparta toda lectura de baja confianza de su referencia
        # (`evaluate_rolling`): son estas, sobre todo lo analizado del indicador.
        excluded = sum(1 for obs in series if obs.is_low_confidence)
        indicators.append({
            "key": key,
            "display": code.display,
            "display_es": code.display_es,
            "domain": str(code.domain),
            "unit": code.unit,
            "decimals": display.decimals_for(key),
            "latest": {
                "value": last.value,
                "effective": last.effective.isoformat(),
                "source": last.source,
                "source_label": source_label(last.source),
                "observation_type": str(last.observation_type),
                "evidence_context": str(last.evidence),
                # Sin numero si la fuente no declaro nada: 1,0 por defecto no es un dato.
                "confidence": None if state is QualityState.UNDECLARED else last.confidence,
                "state": str(state),
                "label": i18n.loc(LABELS[state]),
            },
            "recent": {
                "readings": len(recent),
                "low_confidence": states[QualityState.LOW],
                "undeclared": states[QualityState.UNDECLARED],
                "sources": [
                    {
                        "source": source,
                        "label": source_label(source),
                        "readings": count,
                        "low_confidence": doubtful_sources[source],
                    }
                    for source, count in sorted(sources.items())
                ],
            },
            "baseline": {
                "excluded_readings": excluded,
                "capped_findings": capped[key],
                "discounted": excluded > 0,
                "text": _baseline_text(excluded, capped[key]),
            },
        })

    # Primero lo que tiene lecturas dudosas ahora; despues, orden estable por clave.
    indicators.sort(
        key=lambda item: (
            -item["recent"]["low_confidence"],
            item["latest"]["state"] != str(QualityState.LOW),
            item["key"],
        )
    )
    total = sum(totals.values())
    low = totals[QualityState.LOW]
    affected = sum(1 for item in indicators if item["recent"]["low_confidence"])
    return {
        "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
        "window_days": window.days,
        "recent_label": _span(window)[1],
        "labels": {str(state): i18n.loc(label) for state, label in LABELS.items()},
        "summary": _summary(total, low, affected, window),
        "undeclared_note": _undeclared_note(total, totals[QualityState.UNDECLARED]),
        "recent": {
            "readings": total,
            "low_confidence": low,
            "undeclared": totals[QualityState.UNDECLARED],
        },
        "indicators": indicators,
        # LECTURAS DE UN DISPOSITIVO QUE CONSTABA VINCULADO A OTRO TRIPULANTE.
        #
        # Es un aviso sobre el dato, no un nivel: lo declarado por una persona frente a lo
        # que llego. Se compone al final y aparte para que no pueda cambiar nada de arriba.
        "device_bindings": bindings.in_readings(
            sensor_bindings,
            [obs for obs in observations if obs.effective >= cutoff],
            observations[0].subject if observations else "",
            " ".join(_span(window)),
        ),
    }
