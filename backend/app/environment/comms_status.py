"""El estado del retardo con Tierra en una sola frase, y la discrepancia SPICE-Horizons firmada.

Por qué existe (decisión del usuario, 2026-11-11): la interfaz deducía «Sin efemérides» por su
cuenta, en cada componente, de `comms === null` o del estado de la caché de Horizons
(`ephemeris_coverage.state`). Con SPICE primero (`environment/spice.py`) eso mentía de dos formas:
un día que SPICE calcula en local salía «sin efemérides» si Horizons no lo tenía en caché, y un
perfil sin objetivo de efemérides (órbita baja, cislunar, superficie lunar) salía en cian como un
dato que falta, cuando el retardo no se calcula por diseño. Aquí el backend dice UNA vez qué pasa
con el retardo del día (`describe`), y cada vista lo lee de `/api/status` → `comms_status`:

- `available`: hay retardo; `source` dice de dónde (`spice` o `horizons`) y `source_text` cómo se
  dice («calculado en local (SPICE)» o «JPL Horizons»).
- `not_applicable`: el perfil vigente no tiene objetivo de efemérides; no se calcula y no falta
  nada (gris «no disponible» en F.5-1, no el cian).
- `missing`: ni SPICE, ni la caché de Horizons, ni la red: «Sin efemérides» (cian, F.5-1).

Y si el cálculo local discrepa de la efeméride de Horizons en caché por encima del error declarado
(`ephemeris.Contrast`), `discrepancy` lo dice con la frase del contraste. Esa discrepancia queda
además firmada en el ledger (`record-integrity.md` §3.30), un asiento por día de efeméride: el
payload lo arma `discrepancy_payload`. No es una observación clínica: nada de `analysis/`, del
riesgo ni de las alertas lo lee, y el día discrepante ya se sirve con Horizons, la referencia.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.core import i18n
from app.core.storage import EPHEMERIS_DISCREPANCY_SUBJECT
from app.environment.ephemeris import SOURCE, CommsWindow, Contrast

AVAILABLE = "available"
NOT_APPLICABLE = "not_applicable"
MISSING = "missing"
STATES = (AVAILABLE, NOT_APPLICABLE, MISSING)

SPICE = "spice"
HORIZONS = "horizons"

SOURCE_TEXT = {SPICE: "calculado en local (SPICE)", HORIZONS: "JPL Horizons"}

# El sujeto del asiento: no es de un tripulante, como el enlace simulado (§3.29).
DISCREPANCY_SUBJECT = EPHEMERIS_DISCREPANCY_SUBJECT
DISCREPANCY_WORD = "SPICE y JPL Horizons discrepan"
i18n.en_many({
    SOURCE_TEXT[SPICE]: "computed locally (SPICE)",
    DISCREPANCY_WORD: "SPICE and JPL Horizons disagree",
})
# Cómo sigue la frase en inglés tras «Delay»: «Retardo JPL Horizons» necesita allí su «from».
_SOURCE_PHRASE_EN = {SPICE: "computed locally (SPICE)", HORIZONS: "from JPL Horizons"}


def source_of(window: CommsWindow) -> str:
    """De qué fuente sale una ventana: la caché y la consulta a Horizons firman `SOURCE`."""
    return HORIZONS if window.source == SOURCE else SPICE


def describe(
    window: CommsWindow | None,
    target: str | None,
    epoch: dt.date,
    *,
    profile_id: str,
    signed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """El estado del retardo del día `epoch`, para todas las vistas.

    `signed` es el asiento de la discrepancia de ese día, si lo hay hasta el corte de quien pide
    (`/api/status` con `until`): Tierra no ve un asiento firmado después de su corte.
    """
    if target is None:
        return {
            "state": NOT_APPLICABLE,
            "source": None,
            "source_text": None,
            "word": i18n.tr("No aplica", "Not applicable"),
            "text": i18n.tr(
                f"El perfil de misión vigente ({profile_id}) no tiene objetivo de efemérides: el "
                "retardo con Tierra no se calcula y no falta ningún dato.",
                f"The mission profile in force ({profile_id}) has no ephemeris target: the "
                "delay with Earth is not computed and no data is missing.",
            ),
            "discrepancy": None,
        }
    if window is None:
        return {
            "state": MISSING,
            "source": None,
            "source_text": None,
            "word": i18n.tr("Sin efemérides", "No ephemeris"),
            "text": i18n.tr(
                f"Sin efemérides del {epoch.isoformat()}: el cálculo local (SPICE) no cubre ese "
                "día, JPL Horizons no lo tiene en caché y no se pudo consultar. El retardo no se "
                "inventa.",
                f"No ephemeris for {epoch.isoformat()}: the local computation (SPICE) does not "
                "cover that day, JPL Horizons does not have it cached and it could not be "
                "queried. The delay is not made up.",
            ),
            "discrepancy": None,
        }
    source = source_of(window)
    contrast = window.contrast
    return {
        "state": AVAILABLE,
        "source": source,
        "source_text": i18n.loc(SOURCE_TEXT[source]),
        "word": i18n.tr(
            f"Retardo {SOURCE_TEXT[source]}", f"Delay {_SOURCE_PHRASE_EN[source]}"
        ),
        "text": i18n.tr(
            f"Retardo del {window.epoch.isoformat()} {SOURCE_TEXT[source]} ({window.source}).",
            f"Delay for {window.epoch.isoformat()} {_SOURCE_PHRASE_EN[source]} "
            f"({i18n.loc(window.source)}).",
        ),
        "discrepancy": (
            None if contrast is None or contrast.agrees
            else {
                "word": i18n.loc(DISCREPANCY_WORD),
                "text": contrast.describe(),
                "epoch": window.epoch.isoformat(),
                "used": contrast.used,
                "signed": signed,
            }
        ),
    }


def discrepancy_payload(window: CommsWindow, observer: str) -> dict[str, str] | None:
    """El asiento `ephemeris-discrepancy` de una ventana, o `None` si no discrepa.

    Todo texto, como cualquier acción del registro (`storage._actions`): las cifras con `repr`,
    como las instantáneas de proyección, para que se lean igual que se firmaron. Una elongación no
    comparada va vacía, no a cero.
    """
    contrast: Contrast | None = window.contrast
    if contrast is None or contrast.agrees:
        return None
    # Lo que se firma se escribe en el idioma del registro, pida quien pida (§3.34).
    with i18n.record_language():
        text = contrast.describe()
    return {
        "subject": DISCREPANCY_SUBJECT,
        "epoch": window.epoch.isoformat(),
        "target": window.target,
        "observer": observer,
        "local": contrast.local,
        "reference": contrast.reference,
        "reference_fetched_at": contrast.reference_fetched_at.isoformat(),
        "one_way_seconds_difference": repr(contrast.one_way_seconds_difference),
        "elongation_deg_difference": (
            "" if contrast.elongation_deg_difference is None
            else repr(contrast.elongation_deg_difference)
        ),
        "one_way_seconds_tolerance": repr(contrast.one_way_seconds_tolerance),
        "elongation_deg_tolerance": repr(contrast.elongation_deg_tolerance),
        "used": contrast.used,
        "text": text,
    }


def signed_view(entry: dict[str, Any]) -> dict[str, Any]:
    """Lo que la interfaz enseña de un asiento firmado: dónde está y cuándo se firmó."""
    return {"ledger_index": entry["ledger_index"], "recorded": entry["recorded"]}
