"""Detalle de una alerta: las siete preguntas de la especificacion del equipo (§10).

"Que ha cambiado, desde cuando, respecto a que baseline, que contexto ha cambiado, por que
puede ser relevante, que deberia comprobarse, que evidencia lo respalda." El estado ya tenia
las respuestas repartidas en frases (`drivers`); aqui se dan estructuradas, con las cifras y
la base de cada una, para que la interfaz las ponga en su sitio sin redactar nada clinico.

Quien responde a cada una:

  1. que ha cambiado ........... `changed` y `trends`, aqui
  2. desde cuando .............. `onset` y `onset_basis`, aqui
  3. respecto a que baseline ... `changed[].compared_with`, mediana y muestras, aqui
  4. que contexto ha cambiado .. `context`: lo anade `api/routes.py` (`_with_detail`) con
                                 `analysis/alert_context.py`, porque necesita el almacen
  5. por que puede importar .... `relevance` (peligro RIDGE) y `relevance_evidence` (la ficha
                                 que lo redacta, de `analysis/alert_support.py`)
  6. que comprobar ............. `checks`, de `analysis/alert_support.py`
  7. que evidencia lo respalda . `evidence`, de `analysis/alert_support.py`

Y tres cosas de §6 y §3 que no son preguntas de §10: `concordance` (entre senales),
`persistence` (cuantas lecturas de la ventana estan fuera de lo esperado, con la regla del
motor) y `confidence` (recuentos de calidad de las lecturas fuera de lo esperado del dominio;
**sin cifra unica**, que seria inventada).

Desde la decimoseptima ronda (2026-10-26), cada cambio dice el tipo de su lectura y el corte de su
propia base que cruzo (percentil y valor, en su unidad), y `readings` cuenta de que tipo son las
lecturas que causaron la alerta y cuantas inferidas o predichas del dominio habia en la ventana sin
decidir: la linea base, la tendencia y el riesgo solo leen lo medido (`api/routes.py`).

Desde la decimocuarta ronda, cada cambio lleva `relative_change` (cuanto frente a la mediana
personal, en %, solo en escala de razon) y cada comprobacion su coste (`alert_support`); y la ruta
anade `flow`, los pasos SENSE → … → FOLLOW-UP de la base de conocimiento §10 con el estado de
cada uno (`analysis/alert_flow.py`), que necesita el reconocimiento, la adopcion y el seguimiento.

Las dos ultimas preguntas se componen con las recomendaciones que el estado ya calculo. Si no
se le pasan —quien llama solo quiere las cinco primeras—, `checks` y `evidence` lo dicen con
palabras ("sin comprobacion estructurada para este dominio"); no se deja el hueco.

Nada de esto decide: lee las desviaciones y tendencias que el motor ya calculo.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from app.analysis import alert_support
from app.analysis.alert_context import concordance
from app.analysis.baseline import Deviation
from app.analysis.trend import Trend
from app.core import i18n
from app.ingest.codes import Domain, get
from app.ingest.fhir import VitalObservation

if TYPE_CHECKING:
    from app.advisor.recommendations import Recommendation


def changed(deviation: Deviation, observation_type: str | None = None) -> dict[str, Any]:
    """Una lectura fuera de lo esperado, con su base, su tipo y el corte personal que cruzo.

    `observation_type` es el de su lectura en el registro (`alert_support.observation_types`);
    `None` si quien llama no lo busco.
    """
    code = get(deviation.key)
    baseline = deviation.baseline
    median = baseline.quantile(0.5) if baseline is not None else None
    return {
        "key": deviation.key,
        "display": code.display,
        "display_es": code.display_es,
        "unit": code.unit,
        "value": deviation.value,
        "effective": deviation.effective.isoformat(),
        "severity": str(deviation.severity),
        # Hacia donde se desvia, estructurado: la interfaz pinta la flecha de F.4.3.1 d con esto,
        # no leyendo "por encima"/"por debajo" en la frase.
        "direction": deviation.direction,
        "basis": str(deviation.basis) if deviation.basis is not None else None,
        # Frente a que se compara: la mediana de su propia base, o el rango poblacional.
        "baseline_median": round(median, 4) if median is not None else None,
        "baseline_samples": baseline.samples if baseline is not None else 0,
        # El valor lo compara la interfaz (`AlertDetailView.tsx`): no se traduce. Lo que se lee
        # va en su gemelo `compared_with_display`, en el idioma de la petición.
        "compared_with": (
            "rango poblacional" if deviation.used_population_range else "línea base personal"
        ),
        "compared_with_display": (
            i18n.tr("rango poblacional", "population range")
            if deviation.used_population_range
            else i18n.tr("línea base personal", "personal baseline")
        ),
        "danger_limit": deviation.danger_limit,
        "description": deviation.describe(),
        # Cuanto cambio frente a esa mediana, en %, solo en escala de razon (o por que no).
        # Descriptivo: la lectura ya esta juzgada.
        "relative_change": alert_support.relative_change(deviation),
        # De que tipo es la lectura: desde el 2026-10-26 solo lo medido decide, y se dice.
        "observation_type": observation_type,
        # Que corte de su propia base cruzo (percentil y valor, en su unidad), o por que no hay.
        "personal_cut": alert_support.personal_cut(deviation),
    }


def _concerning(domain: Domain, current: Iterable[Deviation]) -> list[Deviation]:
    """Las lecturas fuera de lo esperado del dominio en la ventana actual, por instante."""
    return sorted(
        (item for item in current if item.is_concerning and get(item.key).domain is domain),
        key=lambda item: item.effective,
    )


def onset(domain: Domain, current: Iterable[Deviation]) -> dt.datetime | None:
    """El inicio de la alerta de un dominio: la primera lectura fuera de lo esperado.

    El mismo que da `detail`; el modo anatómico lo lee para anclar el contexto de una región en
    el mismo instante que el de su alerta, sin componer el detalle entero.
    """
    found = _concerning(domain, current)
    return found[0].effective if found else None


def detail(
    domain: Domain,
    current: Sequence[Deviation],
    trends: Iterable[Trend],
    recommendations: Iterable[Recommendation] = (),
    observations: Iterable[VitalObservation] = (),
    set_aside: Iterable[VitalObservation] = (),
) -> dict[str, Any]:
    """Las respuestas de §10 que no necesitan el almacen, con la base de cada cifra.

    `current` son las desviaciones de la ventana actual; `recommendations`, las del estado
    (aqui se toman las del dominio); `observations`, las lecturas del registro, de las que solo
    se leen la confianza y el tipo de las que estan fuera de lo esperado; `set_aside`, las de la
    ventana que el analisis aparto por su tipo (inferidas o predichas), que solo se cuentan.
    """
    observations = list(observations)
    concerning = _concerning(domain, current)
    trends = list(trends)
    drifting = [
        item for item in trends if get(item.key).domain is domain and item.is_concerning
    ]
    # Una lectura por indicador: la mas reciente, que es la que el estado muestra.
    latest: dict[str, Deviation] = {}
    for item in concerning:
        latest[item.key] = item
    onset: dt.datetime | None = concerning[0].effective if concerning else None
    # Lo medido del dominio en la ventana (todas las lecturas, no solo las fuera de lo esperado):
    # el primer paso del flujo de la alerta (`analysis/alert_flow.py`) lo lee de aqui.
    sensed = [item for item in current if get(item.key).domain is domain]
    return {
        "domain": str(domain),
        "ridge": str(domain.ridge),
        # El inglés del nombre del peligro es de quien lo define (`ingest/codes.py`): si lo
        # registra con `i18n.en`, aquí, donde se sirve, sale; si no, queda como está.
        "ridge_display": i18n.loc(domain.ridge.display),
        # Por que puede importar: el peligro del que procede el riesgo. Lo dice el backend
        # para que la interfaz no redacte.
        "relevance": i18n.tr(
            f"Peligro RIDGE de NASA: {domain.ridge.display}.",
            f"NASA RIDGE hazard: {i18n.loc(domain.ridge.display)}.",
        ),
        "onset": onset.isoformat() if onset is not None else None,
        "onset_basis": (
            i18n.tr(
                "primera lectura fuera de lo esperado dentro de la ventana actual",
                "first reading outside what is expected within the current window",
            )
            if onset is not None
            else i18n.tr(
                "sin lectura fuera de lo esperado: la alerta viene de una tendencia o de un "
                "evento externo",
                "no reading outside what is expected: the alert comes from a trend or from an "
                "external event",
            )
        ),
        "sensed": {"readings": len(sensed), "indicators": len({item.key for item in sensed})},
        "changed": [
            # Una lectura que no se localiza en el registro no tiene tipo que decir: `None`.
            changed(item, None if kind == alert_support.NOT_LOCATED else kind)
            for item, kind in zip(
                latest.values(),
                alert_support.observation_types(latest.values(), observations),
                strict=True,
            )
        ],
        # De que tipo son las lecturas que la causaron, y lo que no decidio (§2, §14).
        "readings": alert_support.reading_types(domain, current, observations, set_aside),
        "trends": [
            {
                "key": item.key,
                "display": get(item.key).display,
                "display_es": get(item.key).display_es,
                "description": item.describe(),
                "span_days": round(item.span_days, 1),
                # El sentido de la deriva, estructurado, para la flecha de F.4.3.1 d.
                "direction": str(item.direction),
            }
            for item in drifting
        ],
        # Concordancia entre senales del dominio (§6). Descriptiva: no vuelve al motor.
        "concordance": concordance(domain, current, trends),
        # Que comprobar y que evidencia lo respalda (§10), mas la ficha del "por que".
        **alert_support.support(domain, recommendations),
        # Persistencia (§6) y confianza (§3), descriptivas: no vuelven al motor.
        "persistence": alert_support.persistence(domain, current, trends),
        "confidence": alert_support.confidence(domain, current, observations, trends),
    }
