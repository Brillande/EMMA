"""Version de las reglas con que se decide (especificacion del equipo §12).

"Todo modelo o regla debe estar versionado y disponer de trazabilidad." El ledger dice que datos
se usaron; faltaba decir con que reglas. Si alguien cambia un umbral de nivel, una ventana, un
rango de referencia, un limite de habitat o una contramedida, una alerta calculada antes y otra
despues no son comparables sin saberlo.

La huella se calcula sobre los **valores** de las reglas, no sobre el codigo fuente: la
aplicacion de escritorio no lleva los `.py`, y un comentario cambiado no cambia ninguna decision.
Cada estado y cada alerta la declaran; una prueba comprueba que cambiar un umbral la cambia.

LA HUELLA DEJABA FUERA REGLAS QUE CAMBIAN ALERTAS
-------------------------------------------------
La primera version recogia los umbrales de nivel, `MIN_SAMPLES` y la relevancia de la tendencia,
elegidos a mano. Se quedaban fuera la persistencia, los puntos por gravedad y por tendencia, el
factor de aislamiento, la rafaga, los cuantiles, la ventana y el retardo de la linea base, el
umbral de confianza y la ventana de "lo actual": cambiar la persistencia del 30 % al 10 % cambiaba
alertas y la version seguia siendo la misma. Justo lo que este modulo existe para impedir.

Una lista hecha a mano se vuelve a quedar corta con la siguiente constante. Por eso ahora es al
reves: `FINGERPRINTED` nombra, modulo a modulo, que constantes entran, la huella se calcula
**recorriendo esa lista** (lo que esta nombrado esta dentro, sin segunda copia que mantener), y
una prueba lee con `ast` los modulos de `GUARDED` y falla si aparece una constante numerica a
nivel de modulo que no este aqui ni en `NOT_IN_VERDICT` con su motivo.

LO QUE LA GUARDIA NO VE, Y SE DICE
----------------------------------
Solo mira constantes **a nivel de modulo**. Un numero escrito dentro de una funcion —el `40.0`
de minutos al que satura `risk.isolation_factor`, por ejemplo— no entra en la huella ni hace
fallar la prueba. Tampoco vigila modulos fuera de `GUARDED`: de `ingest.fhir` y de `api.routes`
entra lo que se nombra a mano.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from enum import Enum
from functools import cache
from types import ModuleType
from typing import Any

from app import routines
from app.advisor.countermeasures import LIBRARY_PATH
from app.analysis import baseline, cycle_phase, risk, staleness, trend
from app.core import i18n
from app.environment.habitat import PARAMETERS
from app.ingest import fhir
from app.ingest.codes import CATALOG, DESCRIPTIVE_ONLY

# Constantes que entran en la huella, por modulo. Lo que esta aqui se lee con `getattr` al
# calcularla: no hay forma de nombrar una y que no cuente.
FINGERPRINTED: dict[str, tuple[str, ...]] = {
    "app.analysis.risk": (
        "_SEVERITY_POINTS",
        "_TREND_POINTS",
        "_MAX_ISOLATION_FACTOR",
        "_DOSE_LIMIT_POINTS",
        "_ADDITIONAL_FINDING_DECAY",
        "_FINDING_PERCENTILE",
        "_PERSISTENCE_FRACTION",
        "_ALWAYS_REPORT_SEVERITY",
        "_HEALTHY_SEVERE_RATE",
        "_BURST_SURPRISE",
        "_MIN_BURST",
        "_LEVEL_THRESHOLDS",
    ),
    "app.analysis.baseline": (
        "MAD_TO_SD",
        "MIN_SAMPLES",
        "MIN_SD_FRACTION",
        "DEFAULT_ROLLING_WINDOW",
        "DEFAULT_ROLLING_LAG",
        "_QUANTILE_THRESHOLDS",
        "_SAMPLES_FOR_SEVERITY",
        "_Z_THRESHOLDS",
    ),
    "app.analysis.trend": (
        "MIN_POINTS",
        "MIN_SPAN_DAYS",
        "T_SIGNIFICANCE",
        "RELEVANCE_HORIZON_WEEKS",
        "RELEVANCE_FRACTION_OF_RANGE",
        "RELEVANCE_FRACTION_OF_LEVEL",
        "TREND_WINDOW",
    ),
    # La fase del ciclo como desplazamiento de la base y de la tendencia (lote «ciclo», B3): donde
    # está la fase lútea, cuántos inicios hacen falta, cuánto se descuenta y entre qué límites.
    # Solo actúa con la puerta abierta (`api/cycle_phase.py`), pero cuando actúa cambia alertas.
    "app.analysis.cycle_phase": (
        "LUTEAL_DAYS",
        "MIN_STARTS",
        "RECENT_CYCLES",
        "START_MARK",
        "LUTEAL_CORE_DAYS",
        "LUTEAL_MAX_DAYS",
        "AFTER_DAYS",
        "MIN_PHASE_READINGS",
        "LUTEAL_OFFSETS",
        "LUTEAL_RANGES",
    ),
    # Por debajo de esta confianza una lectura no entra en la linea base ni sostiene mas que
    # un hallazgo leve.
    "app.ingest.fhir": ("LOW_CONFIDENCE_THRESHOLD",),
    # A partir de cuanto un dato externo se ensena como caducado. No mueve niveles ni alertas,
    # pero decide lo que la tripulacion ve como vigente: una regla, y antes vivia en la interfaz.
    "app.analysis.staleness": ("STALE_AFTER",),
    # Que lecturas son "lo actual" y cual es el "ahora" del estado; y de que tipo (medida,
    # inferida, predicha) tienen que ser para decidir: desde el 2026-10-26, solo las medidas.
    # La dosis acumulada, medida o inferida, es la excepcion declarada para el limite de carrera.
    "app.api.routes": (
        "CURRENT_WINDOW", "_REFERENCE_SUPPORT", "_GAP_FACTOR", "ANALYSED_TYPES", "DOSE_TYPES",
    ),
}

# Modulos donde TODA constante numerica a nivel de modulo tiene que estar en `FINGERPRINTED` o
# en `NOT_IN_VERDICT`. Son los que deciden; `tests/test_versioning.py` lo comprueba.
GUARDED: tuple[str, ...] = (
    "app.analysis.risk", "app.analysis.baseline", "app.analysis.trend", "app.analysis.cycle_phase",
)

# Constantes numericas de un modulo vigilado que NO cambian el veredicto, cada una con su
# motivo. Hoy no hay ninguna: todas las que existen deciden algo. Quien añada una que de
# verdad no decida la declara aqui; quien añada una que decide, arriba.
NOT_IN_VERDICT: dict[str, dict[str, str]] = {}


def canonical(value: Any) -> Any:
    """Un valor de regla en una forma que `json` serializa siempre igual.

    Un tipo que no se sabe canonizar es un error y no un `str(valor)`: una regla que entrara
    en la huella por su `repr` podria cambiar de version sin cambiar, o al reves.
    """
    if isinstance(value, Enum):
        return str(value.value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    if isinstance(value, dict):
        return sorted([canonical(key), canonical(item)] for key, item in value.items())
    if isinstance(value, (tuple, list)):
        return [canonical(item) for item in value]
    raise TypeError(f"regla de tipo {type(value).__name__}: no se sabe canonizar")


def _module(name: str) -> ModuleType:
    """El modulo ya cargado; `api.routes` se importa aqui y no arriba.

    `routes` importa este modulo para declarar la version: importarlo arriba seria un ciclo.
    Cuando se pide la huella ya esta cargado.
    """
    if name == "app.api.routes":
        from app.api import routes

        return routes
    return {
        "app.analysis.risk": risk,
        "app.analysis.baseline": baseline,
        "app.analysis.trend": trend,
        "app.analysis.cycle_phase": cycle_phase,
        "app.ingest.fhir": fhir,
        "app.analysis.staleness": staleness,
    }[name]


def rules() -> dict[str, Any]:
    """Los valores que deciden, en forma canonica."""
    return {
        "parameters": {
            module: {name: canonical(getattr(_module(module), name)) for name in names}
            for module, names in sorted(FINGERPRINTED.items())
        },
        "catalog": {
            key: [
                code.code, code.unit, code.reference_low, code.reference_high,
                code.critical_low, code.critical_high,
                # Sin rango no hay base: `null` (el catalogo no le da rango), no el texto "None".
                canonical(code.reference_basis),
                code.concerning,
            ]
            for key, code in sorted(CATALOG.items())
            # Un indicador descriptivo no decide nada (el estado no lo lee): no cambia las
            # reglas. Si dejara de serlo, entraria aqui y la version cambiaria.
            if key not in DESCRIPTIVE_ONLY
        },
        "habitat": {
            # Una figura conjunta decide con sus vertices, no con `low`/`high`: entran tambien.
            key: [
                [item.low, item.high, item.requirement, item.kind,
                 *([item.figure.vertices()] if item.figure is not None else [])]
                for item in spec.limits
            ]
            for key, spec in sorted(PARAMETERS.items())
        },
        "countermeasures_sha256": hashlib.sha256(LIBRARY_PATH.read_bytes()).hexdigest(),
        # Cada cuánto se espera cada medida periódica, la de siempre y la de un evento solar
        # (`app/routines.py`, 2026-11-02). Como `STALE_AFTER`: no mueve niveles ni alertas, pero
        # decide lo que la tripulación ve como al día, atrasado o roto, y en qué orden.
        "routines": _routine_periods(),
    }


def _routine_periods() -> dict[str, Any]:
    """Los periodos y prioridades de `routines.json`: los valores, no los textos que los citan."""
    data = routines.load()
    during = data.get("during_event", {}).get("routines", {})
    return {
        "design": {key: item["period_hours"] for key, item in sorted(data["routines"].items())},
        "during_event": {
            key: [item["period_hours"], item["priority"]] for key, item in sorted(during.items())
        },
        # Qué acorta esos periodos (2026-11-04): el evento de DONKI y, sin él, la dosis de a bordo
        # por encima de su límite de peligro. Cambiar los disparadores cambia lo que se ve al día.
        "during_event_triggers": [routines.SOLAR_TRIGGER, routines.DOSE_TRIGGER],
    }


def fingerprint(values: dict[str, Any]) -> str:
    canonical_text = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()[:16]


@cache
def rules_version() -> str:
    return f"reglas@{fingerprint(rules())}"


# LA VERSION CON QUE SE FIRMO CADA DECISION (2026-10-31; `record-integrity.md` §3.26)
# ----------------------------------------------------------------------------------
# La huella iba en el estado y en las instantaneas de proyeccion, pero no en los asientos de las
# decisiones humanas (reconocer, declarar un estado, descartar, adoptar, cerrar, no adoptar). Como
# la historia de alertas se recalcula con las reglas de hoy, no se podia saber con que reglas
# salio la alerta que alguien firmo. Ahora cada ruta que firma una decision guarda la huella
# vigente en el asiento, como campo opcional, y al leerlo se dice con cual se firmo y si es la de
# hoy. Una sola redaccion para el detalle de alerta, el seguimiento y la cronica; la interfaz la
# enseña tal cual, sin color (es informacion, no una señal). No se recalcula nada ni cambia
# ningun veredicto: una alerta firmada con otras reglas sigue siendo la alerta que se firmo.
NO_VERSION_RECORDED = "sin versión registrada: el asiento no la lleva"
SAME_AS_TODAY = "misma versión que hoy"
i18n.en(NO_VERSION_RECORDED, "no version recorded: the entry does not carry it")
i18n.en(SAME_AS_TODAY, "same version as today")


def decided_with(signed: str | None) -> dict[str, Any]:
    """Con qué reglas se firmó una decisión, frente a las de hoy, dicho; sin recalcular nada.

    `signed` es el `rules_version` del asiento, o `None` si no lo lleva (firmado antes del campo
    o por fuera de las rutas). `same_as_today` es `None` cuando no hay con qué comparar.
    """
    today = rules_version()
    if signed is None:
        return {
            "rules_version": None, "same_as_today": None, "text": i18n.loc(NO_VERSION_RECORDED),
        }
    same = signed == today
    comparison = SAME_AS_TODAY if same else f"distinta de la de hoy: {today} hoy"
    return {
        "rules_version": signed,
        "same_as_today": same,
        "text": i18n.tr(
            f"decidido con {signed}; {comparison}",
            f"decided with {signed}; "
            + (i18n.loc(SAME_AS_TODAY) if same else f"different from today's: {today} today"),
        ),
    }
