"""Lo que al detalle de una alerta le faltaba decir por si mismo.

POR QUE EXISTE
--------------
La especificacion del equipo (§10) pide que el detalle de una alerta responda a siete preguntas.
El backend respondia a cinco. Las dos ultimas —que deberia comprobarse a continuacion y que
evidencia lo respalda— las componia la interfaz: filtraba las recomendaciones del estado por
dominio, quitaba las citas repetidas y elegia de cual sacar el «por que». Eso es logica clinica
de presentacion en el sitio equivocado: la interfaz no redacta ni elige, pinta (§4: el visor es
cliente del modelo). Aqui se compone lo mismo, con la misma informacion, y la vista solo lo pone
en su sitio.

Dos cosas mas que el motor ya calculaba y no ensenaba:

  * **Persistencia** (§6). Un indicador cuenta como hallazgo solo si sus lecturas fuera de lo
    esperado persisten o forman una rafaga de lecturas graves. La regla vive en
    `analysis/risk.py` y aqui NO se define otra: se llama a `representative_deviation` y a
    `min_severe_readings`, y la fraccion se lee de alli. Si la regla cambia, esto cambia con ella.
  * **Confianza** (§3, `Alert.confidence`). DESCRIPTIVA: cuantas de las lecturas fuera de lo
    esperado de los indicadores de la alerta son de baja confianza, cuantas no la declaran, y
    si cada una se juzgo contra la linea base personal o contra el rango poblacional.

DESDE LA DECIMOCUARTA RONDA (2026-10-21): QUE CUESTA COMPROBAR Y CUANTO CAMBIO
------------------------------------------------------------------------------
Dos huecos que la base de conocimiento y la conversacion de ideacion dejaban al descubierto:

  * **Que cuesta cada comprobacion** (base de conocimiento §9: cada variable con su «coste de
    medicion», para usar lo pasivo y continuo antes que lo invasivo). Las comprobaciones salian
    sin coste aunque `ingest/cost.py` ya lo tenia por indicador. Ahora cada una lleva el tiempo
    de tripulacion de la accion (el de la biblioteca de contramedidas) y, por cada indicador que
    repite, su clase de medida, el tiempo de medirlo, donde se procesa, cuando llega el resultado
    y si gasta consumibles: lo de `ingest/cost.py`, leido tal cual. Lo junta
    `advisor/check_cost.py`, porque ningun modulo del analisis lee el tiempo de tripulacion. Lo
    que alli esta «sin clasificar» aqui sigue «sin clasificar»; no se rellena. Y NO SE
    REORDENAN: salen en el orden del recomendador. Ordenar por coste seria una decision
    clinica (lo barato antes que lo indicado) que nadie ha tomado.
  * **Cuanto cambio** (conversacion de ideacion: «HRV: −14 % respecto al baseline personal»).
    `relative_change` da `(valor − mediana) / mediana` en %, frente a la mediana de la linea base
    personal, SOLO donde la cuenta tiene sentido: magnitudes de escala de razon (cero absoluto,
    distancias proporcionales). No en puntuaciones ordinales, ni en la temperatura en °C (escala
    de intervalo), ni en diferencias con signo, ni con mediana 0; ahi se dice por que no. La
    escala se declara por unidad en una tabla cerrada: una unidad nueva sin declarar no se
    calcula, y una prueba obliga a decidirla.

Las dos cosas son descriptivas: ni puntuan ni cambian ninguna alerta.

SIN CIFRA UNICA DE CONFIANZA
----------------------------
No se da un «0,8» de confianza de la alerta. No hay en el repositorio una fuente ni un metodo
validado con el que combinar calidad de medida, base de comparacion y persistencia en un numero;
cualquier formula seria diseno propio presentado como medida. Se dan los recuentos y se dice.

QUE NO HACE
-----------
No decide nada (invariante 5). Lee las desviaciones, las tendencias, las lecturas y las
recomendaciones que el estado ya calculo. El motor de riesgo no importa este modulo.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from app.advisor import check_cost
from app.analysis import risk
from app.analysis.baseline import Deviation, SeverityBasis, crossed_personal_cut
from app.analysis.data_quality import LABELS, TREND_NOTE, QualityState, state_of
from app.analysis.trend import Trend
from app.core import display, i18n
from app.ingest.codes import Domain, get
from app.ingest.fhir import LOW_CONFIDENCE_THRESHOLD, VitalObservation

if TYPE_CHECKING:
    from app.advisor.recommendations import Recommendation

NO_CHECKS = "sin comprobación estructurada para este dominio"
NO_EVIDENCE = "sin evidencia enlazada para este dominio"

# Como se dice la base de una contramedida de la biblioteca (`advisor/countermeasures.py`:
# `evidence-backed` si la respalda un protocolo concreto, `demo` si solo el riesgo del dominio).
BASIS_DISPLAY: dict[str, str] = {
    "evidence-backed": "la respalda un protocolo concreto",
    "demo": "demo: la respalda solo el riesgo del dominio, no un protocolo concreto",
}
DEMO = "demo"

ROLE_DISPLAY: dict[str, str] = {
    "protocol": "protocolo de la comprobación",
    "domain_risk": "riesgo del dominio",
}
DEMO_EVIDENCE = "citada aquí solo por comprobaciones demo"

PERSISTENCE_BASIS = (
    "Misma regla con la que el motor de riesgo de EMMA decide si un indicador cuenta como "
    "hallazgo. Descriptivo: no cambia el nivel de la alerta."
)
NO_SINGLE_FIGURE = (
    "Sin cifra única de confianza: EMMA no tiene una fuente ni un método validado para "
    "calcularla y no la inventa. Se dan los recuentos."
)
CONFIDENCE_BASIS = "Descriptivo: no cambia el nivel de la alerta."
NO_READINGS = (
    "Sin lecturas fuera de lo esperado en la ventana actual: la alerta viene de una tendencia "
    "o de un evento externo."
)
PERSONAL = "línea base personal"
POPULATION = "rango poblacional"
i18n.en_many({
    NO_CHECKS: "no structured check for this domain",
    NO_EVIDENCE: "no linked evidence for this domain",
    BASIS_DISPLAY["evidence-backed"]: "backed by a specific protocol",
    BASIS_DISPLAY["demo"]: "demo: backed only by the domain risk, not by a specific protocol",
    ROLE_DISPLAY["protocol"]: "protocol of the check",
    ROLE_DISPLAY["domain_risk"]: "domain risk",
    DEMO_EVIDENCE: "cited here only by demo checks",
    PERSISTENCE_BASIS: (
        "The same rule with which EMMA's risk engine decides whether an indicator counts as a "
        "finding. Descriptive: it does not change the level of the alert."
    ),
    NO_SINGLE_FIGURE: (
        "No single confidence figure: EMMA has neither a source nor a validated method to "
        "compute one and does not invent it. The counts are given."
    ),
    CONFIDENCE_BASIS: "Descriptive: it does not change the level of the alert.",
    NO_READINGS: (
        "No readings outside the expected range in the current window: the alert comes from a "
        "trend or from an external event."
    ),
    PERSONAL: "personal baseline",
    POPULATION: "population range",
})


def _count(value: int) -> str:
    return display.number(value, 0)


def _readings(value: int) -> str:
    return i18n.tr(
        f"{_count(value)} {'lectura' if value == 1 else 'lecturas'}",
        f"{_count(value)} {'reading' if value == 1 else 'readings'}",
    )


# --------------------------------------------------------------------------- #
# De que tipo son las lecturas que la causaron (especificacion §2, §10 y §14)
# --------------------------------------------------------------------------- #
#
# Desde el 2026-10-26 (decision del usuario) la linea base, la tendencia y el riesgo solo leen
# lecturas medidas (`api/routes.py`, `ANALYSED_TYPES`). El detalle lo dice con cifras: de que tipo
# son las lecturas fuera de lo esperado que causaron la alerta y cuantas inferidas o predichas
# del dominio habia en la ventana sin decidir nada. Lo que no se encuentra en el registro se
# cuenta aparte; no se le supone tipo.

TYPE_WORDS: dict[str, tuple[str, str]] = {
    "measured": ("medida", "medidas"),
    "inferred": ("inferida", "inferidas"),
    "predicted": ("predicha", "predichas"),
}
# El adjetivo inglés no cambia con el número y va delante del nombre («3 measured readings»).
# Tabla aparte, y no el registro común de `i18n`: «medida» es también un sustantivo en otras
# unidades y ahí tendría otro inglés.
TYPE_WORDS_EN: dict[str, str] = {
    "measured": "measured",
    "inferred": "inferred",
    "predicted": "predicted",
}
NOT_LOCATED = "not_found"
ANALYSED_RULE = (
    "La línea base, la tendencia y el riesgo solo leen lecturas medidas; las inferidas y las "
    "predichas se firman en el registro y se enseñan rotuladas, sin decidir."
)
i18n.en(
    ANALYSED_RULE,
    "The baseline, the trend and the risk read measured readings only; inferred and predicted "
    "ones are signed into the record and shown labelled, without deciding.",
)


def typed_readings(counts: dict[str, int]) -> str:
    """«3 lecturas medidas y 1 inferida»: los recuentos por tipo, en el orden de `TYPE_WORDS`."""
    if i18n.current() == "en":
        return _typed_readings_en(counts)
    # El sustantivo va solo en la primera cifra: «3 lecturas medidas y 1 inferida».
    words = [*TYPE_WORDS.items(), (NOT_LOCATED, ("sin localizar en el registro",) * 2)]
    parts: list[str] = []
    for kind, (one, many) in words:
        count = counts.get(kind, 0)
        if count:
            amount = _count(count) if parts else _readings(count)
            parts.append(f"{amount} {one if count == 1 else many}")
    if not parts:
        return _readings(0)
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " y " + parts[-1]


def _typed_readings_en(counts: dict[str, int]) -> str:
    """Lo mismo en inglés: «3 measured readings and 1 inferred». El nombre, solo en la primera."""
    parts: list[str] = []
    for kind, word in TYPE_WORDS_EN.items():
        count = counts.get(kind, 0)
        if count:
            noun = "" if parts else f" {'reading' if count == 1 else 'readings'}"
            parts.append(f"{_count(count)} {word}{noun}")
    lost = counts.get(NOT_LOCATED, 0)
    if lost:
        amount = _count(lost) if parts else _readings(lost)
        parts.append(f"{amount} not located in the record")
    if not parts:
        return _readings(0)
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _located(
    recorded: dict[tuple[str, Any], list[VitalObservation]], deviation: Deviation
) -> VitalObservation | None:
    """La lectura del registro detras de una desviacion: misma clave, instante y valor.

    Una sola regla para el tipo (`observation_types`) y la confianza (`confidence`): si cada uno
    buscara a su manera, podrian hablar de lecturas distintas.
    """
    candidates = recorded.get((deviation.key, deviation.effective), [])
    return next((obs for obs in candidates if obs.value == deviation.value), None)


def _recorded(
    observations: Iterable[VitalObservation],
) -> dict[tuple[str, Any], list[VitalObservation]]:
    recorded: dict[tuple[str, Any], list[VitalObservation]] = {}
    for obs in observations:
        recorded.setdefault((obs.key, obs.effective), []).append(obs)
    return recorded


def observation_types(
    deviations: Iterable[Deviation], observations: Iterable[VitalObservation]
) -> list[str]:
    """El tipo de cada desviacion, en su orden: el de su lectura en el registro."""
    recorded = _recorded(observations)
    return [
        str(found.observation_type) if (found := _located(recorded, item)) is not None
        else NOT_LOCATED
        for item in deviations
    ]


def reading_types(
    domain: Domain,
    current: Sequence[Deviation],
    observations: Iterable[VitalObservation],
    set_aside: Iterable[VitalObservation] = (),
) -> dict[str, Any]:
    """De que tipo son las lecturas que causaron la alerta y cuantas del dominio no decidieron.

    `current` y `observations` son las de la ventana actual que el motor leyo; `set_aside`, las
    del registro en esa ventana que el analisis aparto por su tipo. Descriptivo: no puntua.
    """
    concerning = [
        item for item in current if item.is_concerning and get(item.key).domain is domain
    ]
    causes: dict[str, int] = {}
    for kind in observation_types(concerning, observations):
        causes[kind] = causes.get(kind, 0) + 1
    aside: dict[str, int] = {}
    for obs in set_aside:
        if get(obs.key).domain is domain:
            kind = str(obs.observation_type)
            aside[kind] = aside.get(kind, 0) + 1
    if concerning:
        statement = i18n.tr(
            f"Lecturas fuera de lo esperado que la causaron: {typed_readings(causes)}.",
            f"Readings outside the expected range that caused it: {typed_readings(causes)}.",
        )
    else:
        statement = i18n.loc(NO_READINGS)
    if aside:
        statement += i18n.tr(
            f" En la ventana hay además {typed_readings(aside)} de este dominio que no deciden: "
            f"están en el registro y no entran en esta alerta.",
            f" The window also holds {typed_readings(aside)} of this domain that do not decide: "
            f"they are in the record and do not enter this alert.",
        )
    return {
        "causes": causes,
        "set_aside": aside,
        "statement": statement,
        "rule": i18n.loc(ANALYSED_RULE),
    }


# --------------------------------------------------------------------------- #
# Que corte de la propia base cruzo cada lectura
# --------------------------------------------------------------------------- #

CUT_BASIS = (
    "Corte de la propia línea base con el que el motor gradúa la lectura (percentiles 99, 99,5 y "
    "99,9 por el lado que preocupa, cada uno con las muestras que exige). Descriptivo."
)
i18n.en(
    CUT_BASIS,
    "Cut of the personal baseline with which the engine grades the reading (percentiles 99, 99.5 "
    "and 99.9 on the concerning side, each with the samples it requires). Descriptive.",
)


def _percentile_text(quantile: float) -> tuple[float, str]:
    shown = round(quantile * 100, 1)
    decimals = 0 if shown == round(shown) else 1
    return shown, display.number(shown, decimals)


def personal_cut(deviation: Deviation) -> dict[str, Any]:
    """El corte personal que cruza la lectura (percentil y valor, en su unidad), o por que no hay.

    Sale de `baseline.crossed_personal_cut`, la misma funcion con la que el motor gradua: el corte
    que se ensena es el que decidio, no uno recalculado aparte.
    """
    code = get(deviation.key)
    empty: dict[str, Any] = {
        "applies": False, "percentile": None, "value": None, "unit": code.unit,
        "samples": deviation.baseline.samples if deviation.baseline is not None else 0,
        "basis": i18n.loc(CUT_BASIS),
    }
    if deviation.used_population_range or deviation.baseline is None:
        return {
            **empty,
            "statement": i18n.tr(
                "Juzgada contra el rango poblacional: no hay corte de línea base personal.",
                "Judged against the population range: there is no personal baseline cut.",
            ),
        }
    cut = crossed_personal_cut(deviation.value, deviation.baseline, code)
    danger = deviation.danger_limit is not None
    if cut is None:
        return {
            **empty,
            "statement": i18n.tr(
                "No cruza ningún corte de su línea base personal"
                + (": la marca el límite de peligro." if danger else "."),
                "It does not cross any cut of its personal baseline"
                + (": it is flagged by the danger limit." if danger else "."),
            ),
        }
    percentile, shown = _percentile_text(cut.quantile)
    sense = "Por encima" if cut.quantile > 0.5 else "Por debajo"
    sense_en = "Above" if cut.quantile > 0.5 else "Below"
    statement = i18n.tr(
        f"{sense} del percentil {shown} de su línea base personal "
        f"({display.quantity(deviation.key, cut.value, code.unit)}, sobre "
        f"{_readings(deviation.baseline.samples)}).",
        f"{sense_en} percentile {shown} of its personal baseline "
        f"({display.quantity(deviation.key, cut.value, code.unit)}, over "
        f"{_readings(deviation.baseline.samples)}).",
    )
    if deviation.basis is SeverityBasis.DANGER_LIMIT:
        statement += i18n.tr(
            " La gravedad la decide el límite de peligro, no este corte.",
            " Severity is decided by the danger limit, not by this cut.",
        )
    elif deviation.basis is SeverityBasis.LOW_CONFIDENCE:
        statement += i18n.tr(
            " La baja confianza de la medida limita la gravedad a leve: este corte no la decide.",
            " The low confidence of the measurement caps severity at mild: this cut does not "
            "decide it.",
        )
    return {
        **empty,
        "applies": True,
        "percentile": percentile,
        "value": round(cut.value, 4),
        "statement": statement,
    }


# --------------------------------------------------------------------------- #
# Que cuesta cada comprobacion (base de conocimiento §9)
# --------------------------------------------------------------------------- #

COST_ORDER_NOTE = (
    "En el orden en que las da el recomendador: el coste se anota al lado, no las reordena."
)
i18n.en(
    COST_ORDER_NOTE,
    "In the order the recommender gives them: the cost is noted alongside and does not reorder "
    "them.",
)


# --------------------------------------------------------------------------- #
# Que comprobar a continuacion y que evidencia lo respalda
# --------------------------------------------------------------------------- #

def support(domain: Domain, recommendations: Iterable[Recommendation]) -> dict[str, Any]:
    """Las comprobaciones del dominio y sus fichas, una vez cada una.

    Es lo que juntaba la vista: las recomendaciones del dominio de la alerta y sus citas. Las
    fichas se deduplican por identificador del registro (la vista lo hacia por titulo). El «por
    que puede importar» citado es el de la primera ficha que lo trae redactado.
    """
    checks: list[dict[str, Any]] = []
    evidence: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for item in recommendations:
        if item.domain is not domain:
            continue
        measure = item.countermeasure
        ident = measure.id if measure is not None else item.action
        if ident in seen:
            continue
        seen.add(ident)
        basis = measure.basis if measure is not None else None
        protocol = (
            measure.protocol_ref.id
            if measure is not None and measure.protocol_ref is not None
            else None
        )
        checks.append({
            "id": measure.id if measure is not None else None,
            "title": item.action,
            "indication": measure.indication if measure is not None else None,
            "urgency": str(item.urgency),
            "basis": basis,
            "basis_display": (
                i18n.loc(BASIS_DISPLAY.get(basis, basis)) if basis is not None else None
            ),
            "demo": basis == DEMO,
            # Una contramedida puede citar la misma ficha como protocolo y como riesgo.
            "evidence_ids": list(dict.fromkeys(cited.id for cited in item.evidence)),
            # Que cuesta (KB §9). Se anota; el orden de la lista sigue siendo el del recomendador.
            "cost": check_cost.of(measure),
        })
        for cited in item.evidence:
            entry = evidence.setdefault(
                cited.id,
                {**cited.to_dict(), "cited_by": [], "role": "domain_risk", "demo": True},
            )
            if ident not in entry["cited_by"]:
                entry["cited_by"].append(ident)
            if cited.id == protocol:
                entry["role"] = "protocol"
            if basis != DEMO:
                entry["demo"] = False
            if entry["relevance"] is None and cited.relevance is not None:
                entry["relevance"] = cited.relevance
    fiches = list(evidence.values())
    for entry in fiches:
        entry["role_display"] = i18n.loc(ROLE_DISPLAY[entry["role"]])
        entry["demo_display"] = i18n.loc(DEMO_EVIDENCE) if entry["demo"] else None
    why = next((entry for entry in fiches if entry["relevance"] is not None), None)
    return {
        "checks": {
            "items": checks,
            "statement": i18n.tr(
                f"Comprobaciones estructuradas para este dominio: {_count(len(checks))}."
                if checks
                else NO_CHECKS,
                f"Structured checks for this domain: {_count(len(checks))}."
                if checks
                else i18n.loc(NO_CHECKS),
            ),
            "order_note": i18n.loc(COST_ORDER_NOTE) if checks else None,
            # Que quiere decir «sin clasificar», dicho una vez si alguna comprobacion lo lleva.
            "unclassified_note": (
                i18n.loc(check_cost.UNCLASSIFIED_NOTE)
                if check_cost.has_unclassified(item["cost"] for item in checks)
                else None
            ),
        },
        "evidence": {
            "items": fiches,
            "statement": i18n.tr(
                f"Fichas de evidencia enlazadas: {_count(len(fiches))}." if fiches else NO_EVIDENCE,
                f"Linked evidence records: {_count(len(fiches))}."
                if fiches else i18n.loc(NO_EVIDENCE),
            ),
        },
        "relevance_evidence": (
            {"id": why["id"], "title": why["title"], "text": why["relevance"]}
            if why is not None
            else None
        ),
    }


# --------------------------------------------------------------------------- #
# Persistencia
# --------------------------------------------------------------------------- #

def _by_key(domain: Domain, current: Sequence[Deviation]) -> dict[str, list[Deviation]]:
    series: dict[str, list[Deviation]] = {}
    for item in current:
        if get(item.key).domain is domain:
            series.setdefault(item.key, []).append(item)
    return series


def _persistence_statement(
    name: str, total: int, out: int, severe: int, needed: int, rule: str | None, drifting: bool
) -> str:
    fraction = display.percent(risk._PERSISTENCE_FRACTION, 0)
    if i18n.current() == "en":
        return _persistence_statement_en(name, total, out, severe, needed, rule, drifting, fraction)
    text = (
        f"{name}: {_count(out)} de {_readings(total)} de la ventana actual fuera de lo esperado"
        + (f" ({display.percent(out / total, 0)})." if total else ".")
    )
    if rule == "persistence":
        text += f" Cuenta como hallazgo: alcanza la fracción mínima de persistencia ({fraction})."
    elif rule == "burst":
        text += (
            f" Cuenta como hallazgo por ráfaga: {_readings(severe)} "
            f"{'grave' if severe == 1 else 'graves'}, y con {_count(needed)} o más cuenta aunque "
            f"no alcance la fracción mínima de persistencia ({fraction})."
        )
    elif out:
        text += (
            f" Por sus lecturas no cuenta como hallazgo: no alcanza la fracción mínima de "
            f"persistencia ({fraction}) ni forma una ráfaga de lecturas graves "
            f"({_count(severe)}; harían falta {_count(needed)})."
        )
    if drifting:
        text += " Su tendencia sostenida cuenta aparte, por su propia vía."
    return text


def _persistence_statement_en(
    name: str, total: int, out: int, severe: int, needed: int, rule: str | None, drifting: bool,
    fraction: str,
) -> str:
    """La frase de `_persistence_statement` en inglés: mismas ramas, mismas cifras."""
    text = (
        f"{name}: {_count(out)} of {_readings(total)} in the current window outside the "
        "expected range" + (f" ({display.percent(out / total, 0)})." if total else ".")
    )
    if rule == "persistence":
        text += (
            f" It counts as a finding: it reaches the minimum persistence fraction ({fraction})."
        )
    elif rule == "burst":
        text += (
            f" It counts as a finding by burst: {_count(severe)} severe "
            f"{'reading' if severe == 1 else 'readings'}, and with {_count(needed)} or more it "
            f"counts even if it does not reach the minimum persistence fraction ({fraction})."
        )
    elif out:
        text += (
            f" By its readings it does not count as a finding: it does not reach the minimum "
            f"persistence fraction ({fraction}) and does not form a burst of severe readings "
            f"({_count(severe)}; {_count(needed)} would be needed)."
        )
    if drifting:
        text += " Its sustained trend counts separately, by its own route."
    return text


def persistence(
    domain: Domain, current: Sequence[Deviation], trends: Iterable[Trend]
) -> dict[str, Any]:
    """Por indicador: cuantas lecturas de la ventana estan fuera de lo esperado, y si cuenta.

    `current` son las desviaciones de la ventana actual, las mismas que recibe el motor. Si un
    indicador cuenta lo decide `risk.representative_deviation`, llamada tal cual.
    """
    drifting = {
        item.key for item in trends if item.is_concerning and get(item.key).domain is domain
    }
    indicators: list[dict[str, Any]] = []
    for key, series in _by_key(domain, current).items():
        out = sum(1 for item in series if item.is_concerning)
        if not out and key not in drifting:
            continue
        severe = sum(1 for item in series if item.severity is risk._ALWAYS_REPORT_SEVERITY)
        needed = risk.min_severe_readings(len(series))
        sustained = risk.representative_deviation(series) is not None
        rule = None if not sustained else ("burst" if severe >= needed else "persistence")
        name = get(key).display_es
        indicators.append({
            "key": key,
            "display": get(key).display,
            "display_es": name,
            "readings": len(series),
            "out_of_expected": out,
            "fraction": round(out / len(series), 4),
            "severe": severe,
            "required_fraction": risk._PERSISTENCE_FRACTION,
            "required_severe": needed,
            "sustained": sustained,
            "rule": rule,
            "trend": key in drifting,
            "statement": _persistence_statement(
                name, len(series), out, severe, needed, rule, key in drifting
            ),
        })
    # Tendencias de indicadores sin ninguna lectura en la ventana actual: se dicen igual.
    for key in sorted(drifting - {item["key"] for item in indicators}):
        name = get(key).display_es
        indicators.append({
            "key": key, "display": get(key).display, "display_es": name, "readings": 0,
            "out_of_expected": 0, "fraction": None,
            "severe": 0, "required_fraction": risk._PERSISTENCE_FRACTION,
            "required_severe": risk.min_severe_readings(0), "sustained": False, "rule": None,
            "trend": True,
            "statement": _persistence_statement(name, 0, 0, 0, 0, None, True),
        })
    indicators.sort(key=lambda item: (not item["sustained"], item["key"]))
    sustained_count = sum(1 for item in indicators if item["sustained"])
    return {
        "indicators": indicators,
        "sustained": sustained_count,
        "statement": i18n.tr(
            f"Indicadores que cuentan como hallazgo por sus lecturas: {_count(sustained_count)} "
            f"de {_count(len(indicators))}."
            if indicators
            else NO_READINGS,
            f"Indicators that count as a finding by their readings: {_count(sustained_count)} "
            f"of {_count(len(indicators))}."
            if indicators
            else i18n.loc(NO_READINGS),
        ),
        "basis": i18n.loc(PERSISTENCE_BASIS),
    }


# --------------------------------------------------------------------------- #
# Confianza, descriptiva
# --------------------------------------------------------------------------- #

def confidence(
    domain: Domain,
    current: Sequence[Deviation],
    observations: Iterable[VitalObservation],
    trends: Iterable[Trend] = (),
) -> dict[str, Any]:
    """Recuentos sobre las lecturas detras de la alerta. Sin cifra unica: seria inventada.

    Se cuentan las lecturas fuera de lo esperado de la ventana actual, en los indicadores del
    dominio. Si cada indicador llega a contar como hallazgo lo dice `persistence`, no esto: una
    alerta puede venir de una tendencia y sus lecturas sueltas no sostenerla. La confianza de
    cada una es la de su lectura en el registro, con la regla de `analysis/data_quality.py` (la
    misma que usa la linea base). Una lectura cuya observacion no se encuentra se cuenta como
    «sin lectura localizada», no se le supone nada.
    """
    recorded = _recorded(observations)

    indicators: list[dict[str, Any]] = []
    for key, series in _by_key(domain, current).items():
        out = [item for item in series if item.is_concerning]
        if not out:
            continue
        states: dict[QualityState | None, int] = {}
        for item in out:
            found = _located(recorded, item)
            state = state_of(found) if found is not None else None
            states[state] = states.get(state, 0) + 1
        population = sum(1 for item in out if item.used_population_range)
        personal = len(out) - population
        compared = [
            i18n.loc(label)
            for label, count in ((PERSONAL, personal), (POPULATION, population)) if count
        ]
        low = states.get(QualityState.LOW, 0)
        undeclared = states.get(QualityState.UNDECLARED, 0)
        indicators.append({
            "key": key,
            "display": get(key).display,
            "display_es": get(key).display_es,
            "readings": len(out),
            "low_confidence": low,
            "declared": states.get(QualityState.DECLARED, 0),
            "undeclared": undeclared,
            "not_found": states.get(None, 0),
            # Hallazgos que el motor ya limito a leve por la confianza de la medida.
            "capped": sum(1 for item in out if item.basis is SeverityBasis.LOW_CONFIDENCE),
            "personal_baseline": personal,
            "population_range": population,
            "compared_with": compared,
            "statement": i18n.tr(
                f"{get(key).display_es}: {_readings(len(out))} fuera de lo esperado; de baja "
                f"confianza de medida, {_count(low)}; sin confianza declarada, "
                f"{_count(undeclared)}; frente a {' y '.join(compared)}.",
                f"{get(key).display_es}: {_readings(len(out))} outside the expected range; with "
                f"low measurement confidence, {_count(low)}; with no declared confidence, "
                f"{_count(undeclared)}; compared with {' and '.join(compared)}.",
            ),
        })
    indicators.sort(key=lambda item: (-item["low_confidence"], item["key"]))

    def total(field: str) -> int:
        return sum(int(item[field]) for item in indicators)

    readings = total("readings")
    drifting = any(
        item.is_concerning and get(item.key).domain is domain for item in trends
    )
    if readings:
        statement = i18n.tr(
            f"Lecturas fuera de lo esperado de este dominio en la ventana actual: "
            f"{_count(readings)}. "
            f"De baja confianza de medida: {_count(total('low_confidence'))}. "
            f"Sin confianza declarada: {_count(total('undeclared'))}. "
            f"Juzgadas contra la línea base personal: {_count(total('personal_baseline'))}; "
            f"contra el rango poblacional: {_count(total('population_range'))}.",
            f"Readings outside the expected range in this domain in the current window: "
            f"{_count(readings)}. "
            f"With low measurement confidence: {_count(total('low_confidence'))}. "
            f"With no declared confidence: {_count(total('undeclared'))}. "
            f"Judged against the personal baseline: {_count(total('personal_baseline'))}; "
            f"against the population range: {_count(total('population_range'))}.",
        )
    else:
        statement = i18n.loc(NO_READINGS)
    return {
        "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
        "labels": {str(state): i18n.loc(label) for state, label in LABELS.items()},
        "readings": readings,
        "low_confidence": total("low_confidence"),
        "declared": total("declared"),
        "undeclared": total("undeclared"),
        "not_found": total("not_found"),
        "capped": total("capped"),
        "personal_baseline": total("personal_baseline"),
        "population_range": total("population_range"),
        "indicators": indicators,
        "statement": statement,
        # La tendencia no mira la confianza (`analysis/data_quality.py`): se dice si hay una.
        "trend_note": i18n.loc(TREND_NOTE) if drifting else None,
        "note": i18n.loc(NO_SINGLE_FIGURE),
        "basis": i18n.loc(CONFIDENCE_BASIS),
    }


# --------------------------------------------------------------------------- #
# Cuanto cambio frente a la mediana personal (conversacion de ideacion)
# --------------------------------------------------------------------------- #
#
# `(valor - mediana) / mediana` solo tiene sentido en escala de razon: con un cero que es
# ausencia de lo medido, «un 14 % menos» es una proporcion. En una escala de intervalo (°C) el
# cero es una convencion y el porcentaje cambia con ella; en una puntuacion ordinal las distancias
# no son proporciones; en una diferencia con signo la mediana puede ser 0 o negativa. La escala
# se declara por unidad, en una tabla cerrada, y por clave cuando la unidad no basta.

RATIO_UNITS = frozenset({
    "/min", "%", "mm[Hg]", "kg", "ms", "{count}", "h", "uGy/h", "mSv", "min", "nmol/L", "ug/dL",
    "mm", "mm2", "cm3", "10*3/uL", "1", "mg/dL", "10*6/uL", "g/dL", "fL", "pg", "mmol/L",
    "pg/mL", "m[IU]/mL", "U/L", "u[IU]/mL", "ng/dL", "[arb'U]/mL", "ng/mL", "mg/L", "ug/L",
    "mL/(24.h)", "mL", "kcal/d", "mL/min/kg{body_wt}", "kgf",
    # La densidad ósea areal de la DXA: su cero es «sin mineral», una razón.
    "g/cm2",
    # La orina de 24 h: masa o sustancia excretada por día y osmolalidad; su cero es «nada».
    "mg/(24.h)", "mmol/(24.h)", "mosm/kg",
    # Tiempo y fuerza de las pruebas funcionales, y lo ingerido al día: su cero es «nada».
    "s", "N", "mg/d", "ug/d", "g/(24.h)",
})
NOT_RATIO_UNITS: dict[str, str] = {
    "{score}": "es una puntuación ordinal o de valoración: sus distancias no son proporciones",
    "Cel": (
        "la temperatura en grados Celsius es una escala de intervalo: su cero es una convención, "
        "no la ausencia de temperatura"
    ),
    "[pH]": (
        "el pH es el logaritmo de una concentración: una unidad de pH multiplica por diez la "
        "acidez, y un porcentaje de la cifra no es una proporción de lo medido"
    ),
}
# Indicadores con unidad de razon cuyo valor no lo es.
NOT_RATIO_KEYS: dict[str, str] = {
    "circadian-shift": (
        "es un desfase con signo respecto al horario de misión: su cero es «sin desfase» y la "
        "mediana puede ser 0 o negativa"
    ),
    "orthostatic-drop": (
        "es la diferencia entre dos medidas de presión: puede ser negativa y su mediana, 0"
    ),
    "urine-specific-gravity": (
        "es una densidad relativa al agua, que vale 1: el cero de la escala no es «sin solutos»"
    ),
    "cumulative-dose": (
        "es un total acumulado, que solo crece con el tiempo: frente a su mediana pasada "
        "sale por encima sin que nada haya cambiado"
    ),
}
UNDECLARED_SCALE = "su unidad no tiene escala declarada en EMMA"
RELATIVE_BASIS = (
    "Cambio relativo = (valor − mediana) / mediana de la línea base personal, solo en magnitudes "
    "de escala de razón. Descriptivo: no puntúa ni cambia el nivel de la alerta."
)
PERCENT_NOTE = " Es un cambio relativo, no una diferencia en puntos porcentuales."
i18n.en_many({
    NOT_RATIO_UNITS["{score}"]: (
        "it is an ordinal or rating score: its distances are not proportions"
    ),
    NOT_RATIO_UNITS["Cel"]: (
        "temperature in degrees Celsius is an interval scale: its zero is a convention, not the "
        "absence of temperature"
    ),
    NOT_RATIO_UNITS["[pH]"]: (
        "pH is the logarithm of a concentration: one pH unit multiplies acidity by ten, and a "
        "percentage of the figure is not a proportion of what is measured"
    ),
    NOT_RATIO_KEYS["circadian-shift"]: (
        "it is a signed offset from the mission schedule: its zero is «no offset» and the "
        "median can be 0 or negative"
    ),
    NOT_RATIO_KEYS["orthostatic-drop"]: (
        "it is the difference between two pressure measurements: it can be negative and its "
        "median can be 0"
    ),
    NOT_RATIO_KEYS["urine-specific-gravity"]: (
        "it is a density relative to water, which is 1: the zero of the scale is not «no "
        "solutes»"
    ),
    NOT_RATIO_KEYS["cumulative-dose"]: (
        "it is a cumulative total, which only grows with time: against its past median it "
        "comes out above without anything having changed"
    ),
    UNDECLARED_SCALE: "its unit has no declared scale in EMMA",
    RELATIVE_BASIS: (
        "Relative change = (value − median) / median of the personal baseline, only for "
        "ratio-scale quantities. Descriptive: it neither scores nor changes the level of the "
        "alert."
    ),
    PERCENT_NOTE: " It is a relative change, not a difference in percentage points.",
})


def scale_reason(key: str) -> str | None:
    """Por que el cambio relativo no tiene sentido en este indicador, o `None` si lo tiene."""
    if key in NOT_RATIO_KEYS:
        return NOT_RATIO_KEYS[key]
    unit = get(key).unit
    if unit in NOT_RATIO_UNITS:
        return NOT_RATIO_UNITS[unit]
    if unit not in RATIO_UNITS:
        return UNDECLARED_SCALE
    return None


def _not_computed(reason: str) -> dict[str, Any]:
    return {
        "applies": False, "percent": None, "median": None, "statement": reason,
        "basis": i18n.loc(RELATIVE_BASIS),
    }


def relative_change(deviation: Deviation) -> dict[str, Any]:
    """El cambio de la lectura frente a la mediana de su linea base personal, o por que no se da.

    Se calcula con la misma mediana que `explain.changed` ensena (`quantile(0.5)`). No lee ni
    escribe nada del motor: la lectura ya esta juzgada cuando llega aqui.
    """
    code = get(deviation.key)
    if deviation.used_population_range:
        return _not_computed(i18n.tr(
            "Juzgada contra el rango poblacional: no hay mediana personal con la que dar un "
            "cambio relativo.",
            "Judged against the population range: there is no personal median with which to "
            "give a relative change.",
        ))
    reason = scale_reason(deviation.key)
    if reason is not None:
        return _not_computed(i18n.tr(
            f"Sin cambio relativo: {reason}.", f"No relative change: {i18n.loc(reason)}."
        ))
    median = deviation.baseline.quantile(0.5) if deviation.baseline is not None else None
    if median is None:
        return _not_computed(i18n.tr(
            "Sin cambio relativo: no hay mediana de línea base personal.",
            "No relative change: there is no personal baseline median.",
        ))
    if median <= 0:
        return _not_computed(i18n.tr(
            "Sin cambio relativo: la mediana personal es "
            f"{display.quantity(deviation.key, median, code.unit)}, y frente a una mediana que no "
            "es positiva el porcentaje no se define.",
            "No relative change: the personal median is "
            f"{display.quantity(deviation.key, median, code.unit)}, and against a median that "
            "is not positive the percentage is not defined.",
        ))
    percent = (deviation.value - median) / median * 100
    # Se decide con la cifra ya redondeada: un 9,96 % se lee «10 %», como un 10,2 %.
    decimals = 0 if round(abs(percent), 1) >= 10 else 1
    shown = display.number(abs(percent), decimals)
    # La mediana no se repite en la frase: la vista ya la ensena al lado con sus decimales, y
    # dos redondeos de la misma cifra («7,8» y «8 recuento») se leerian como dos medianas.
    if round(abs(percent), decimals) == 0:
        statement = i18n.tr(
            "Sin cambio apreciable frente a su mediana personal.",
            "No appreciable change from its personal median.",
        )
    else:
        sense = "por encima" if percent > 0 else "por debajo"
        sense_en = "above" if percent > 0 else "below"
        statement = i18n.tr(
            f"Un {shown} % {sense} de su mediana personal.",
            f"{shown} % {sense_en} its personal median.",
        )
    if code.unit == "%":
        statement += i18n.loc(PERCENT_NOTE)
    return {
        "applies": True,
        "percent": round(percent, 1),
        "median": round(median, 4),
        "statement": statement,
        "basis": i18n.loc(RELATIVE_BASIS),
    }
