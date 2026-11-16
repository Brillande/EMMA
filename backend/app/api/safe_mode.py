"""Modo seguro: un interruptor firmado que corta toda salida de EMMA a internet.

Por qué existe: Polaris tiene su "código rojo" (`polaris/tools/codigo_rojo.py`): si algo pone en
peligro el objetivo, para todo. No se puede usar tal cual (escribe en la carpeta personal, avisa
por Telegram, apaga demonios de macOS), pero su regla sí: **lo activa cualquiera con un motivo,
y solo una persona lo levanta**. En EMMA, por decisión del usuario (2026-10-01), lo que corta es
**la red**: la IA es local (modelos locales que se verifican entre sí) y sigue, igual que las
constantes, el análisis y las alertas. Ninguna consulta a NASA ni a los registros de citas sale
mientras esté activo (`core/egress.py`).

Aquí se enseña también el freno por fichero de Polaris (`halt`), que no es este interruptor pero
corta lo mismo, y su aviso (`halt_notice`): el texto lo compone el backend y la consola lo pinta
en la franja común en cuanto aparece el fichero, sin que nadie lo pida.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api import routes
from app.api.routes import CONSOLE_IDENTITY, SettingsDep, StoreDep, identity_for
from app.core import egress, i18n
from app.core.config import Settings
from app.core.storage import SafeModeConflict

safe_mode_router = APIRouter(prefix="/safe-mode")


class SafeModeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool
    reason: str = Field(default="", max_length=300)
    declared_by: str = Field(min_length=1, max_length=64)


# Cada propósito de salida de `core/egress.py` (su `ALLOWLIST`), con el nombre con que se lee.
# El aviso se compone recorriendo `ALLOWLIST`, no esta tabla: un propósito nuevo sale aunque sea
# por su clave, y `tests/test_halt_notice.py` exige que las dos tengan las mismas claves.
EXIT_NAMES: dict[str, str] = {
    "space-weather": "clima espacial (NASA DONKI)",
    "space-weather-series": "series de protones y viento solar (NASA CCMC iSWA)",
    "radiation": "radiación (OSDR RadLab)",
    "osdr-data": "fichas de estudios (OSDR)",
    "ephemeris": "efemérides para el retardo con Tierra (JPL Horizons)",
    "spice-kernels": "la descarga de los núcleos SPICE (NAIF, JPL)",
    "orbit": "la posición de la ISS (NASA SSCweb)",
    "citations": "la comprobación de citas en sus registros",
    "datasets": "la descarga de conjuntos de validación (Zenodo)",
    "planner-quotes": "la cita del día del planificador (ZenQuotes)",
    "planner-onthisday": "las efemérides del planificador (Wikipedia)",
    "models-pack": "la descarga del paquete de modelos (GitHub)",
    "app-update": "la búsqueda y descarga de versiones nuevas de EMMA (GitHub)",
}
i18n.en_many(
    {
        EXIT_NAMES["space-weather"]: "space weather (NASA DONKI)",
        EXIT_NAMES["space-weather-series"]: "proton and solar wind series (NASA CCMC iSWA)",
        EXIT_NAMES["radiation"]: "radiation (OSDR RadLab)",
        EXIT_NAMES["osdr-data"]: "study records (OSDR)",
        EXIT_NAMES["ephemeris"]: "ephemeris for the delay to Earth (JPL Horizons)",
        EXIT_NAMES["spice-kernels"]: "the download of the SPICE kernels (NAIF, JPL)",
        EXIT_NAMES["orbit"]: "the position of the ISS (NASA SSCweb)",
        EXIT_NAMES["citations"]: "the checking of citations in their registries",
        EXIT_NAMES["datasets"]: "the download of validation datasets (Zenodo)",
        EXIT_NAMES["planner-quotes"]: "the planner's quote of the day (ZenQuotes)",
        EXIT_NAMES["planner-onthisday"]: "the planner's on-this-day entries (Wikipedia)",
        EXIT_NAMES["models-pack"]: "the download of the model pack (GitHub)",
        EXIT_NAMES["app-update"]: "the search for and download of new EMMA versions (GitHub)",
    }
)


def _exits() -> str:
    names = [EXIT_NAMES.get(purpose, purpose) for purpose in egress.ALLOWLIST]
    names = [i18n.loc(name) for name in names]
    last = i18n.tr("y", "and")
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} {last} {names[-1]}"


def halt_notice(halt: dict[str, Any], offline: bool) -> dict[str, Any] | None:
    """El aviso del freno HALT para la consola, o None si el freno no está puesto.

    Por qué existe: un freno olvidado no se nota (en Polaris paró una rutina semanas) y hasta
    ahora solo lo sabía quien leyera `GET /api/safe-mode`. La interfaz no redacta, así que el
    texto sale de aquí, y dice lo que el freno es en EMMA, ni más ni menos:

    * corta la salida a internet, lo mismo que el modo seguro, pero no es el modo seguro: no se
      firma ni deja asiento, EMMA no lo crea y levantar el modo seguro no lo quita;
    * no toca las constantes, el análisis, las alertas ni el modelo local, que no pasan por la
      puerta de salida (`polaris.halt_file`). De lo que EMMA llama de Polaris, solo la puerta lo
      mira (leído el 2026-10-20): `soporte_cita` lo consulta en `soporte` y `cotejar_fragmento`,
      que EMMA no llama; `seguimiento`, en `frescura`, que tampoco (de él solo se usa
      `recopilar`, sustituido por `timeline.py`); `salida`, `cost_guard` y `codigo_rojo` no se
      llaman;
    * `since` es la fecha del fichero, no la de un asiento firmado (`egress.halt_state`);
    * en modo sin red, el nominal de misión, ya no salía nada: el freno no cambia nada hasta que
      vuelva la red, y el aviso lo dice en vez de presentarse como la causa del corte.
    """
    if not halt["active"]:
        return None
    details = [
        i18n.tr(
        "Es el freno por fichero de Polaris, no el modo seguro: no se firma ni deja asiento en "
        "el registro, EMMA no lo pone nunca y levantar el modo seguro no lo quita. Lo pone una "
        "persona a mano o una herramienta de Polaris (cost_guard, codigo_rojo). Dentro de "
        "Polaris, las herramientas que lo consultan se paran; de lo que EMMA usa de Polaris, "
        "solo lo nota la puerta de salida.",
        "It is Polaris's file brake, not safe mode: it is not signed and leaves no entry in "
        "the record, EMMA never sets it and lifting safe mode does not remove it. It is set by "
        "a person by hand or by a Polaris tool (cost_guard, codigo_rojo). Inside Polaris, the "
        "tools that check it stop; of what EMMA uses from Polaris, only the egress gate "
        "notices it.",
        ),
        i18n.tr(
        "Mientras el fichero exista, la puerta de salida niega toda consulta a internet: "
        f"{_exits()}. Lo que viene de esas fuentes se sirve de lo ya guardado, con su edad, o se "
        "declara ausente.",
        "While the file exists, the egress gate refuses every query to the internet: "
        f"{_exits()}. What comes from those sources is served from what is already stored, "
        "with its age, or is declared absent.",
        ),
        i18n.tr(
        "No para las constantes, el análisis, las alertas ni el modelo local: no salen a "
        "internet.",
        "It does not stop the vital signs, the analysis, the alerts or the local model: they "
        "do not go out to the internet.",
        ),
        i18n.tr(
        "La fecha es la de modificación del fichero, sin firma: dice cuánto lleva ahí, no quién "
        "lo puso.",
        "The date is the file's modification date, unsigned: it says how long it has been "
        "there, not who set it.",
        ),
        i18n.tr(
        f"Se quita borrando el fichero {halt['file']}; la consola no tiene un mando para ello.",
        f"It is removed by deleting the file {halt['file']}; the console has no control for it.",
        ),
    ]
    if offline:
        details.insert(
            1,
            i18n.tr(
            "EMMA está además en modo sin red: hoy no sale nada a internet, con freno o sin él. "
            "El freno cortará la salida cuando vuelva la red, si sigue puesto.",
            "EMMA is also in offline mode: today nothing goes out to the internet, with or "
            "without the brake. The brake will cut the egress when the network returns, if it "
            "is still set.",
            ),
        )
    notice: dict[str, Any] = {
        "title": i18n.tr("Freno HALT de Polaris", "Polaris HALT brake"),
        "headline": i18n.tr("puesto · sin salida a internet", "set · no internet egress"),
        "summary": "Siguen las constantes, el análisis, las alertas y el modelo local.",
        "since": halt["since"],
        "since_label": i18n.tr(
            "desde (fecha del fichero, sin firma)", "since (file date, unsigned)"
        ),
        "details_label": i18n.tr("Qué es y cómo se quita", "What it is and how to remove it"),
        "details": details,
    }
    # Aparte, para que la línea castellana de arriba siga tal cual (la fija una campaña de
    # mutantes).
    notice["summary"] = i18n.tr(
        notice["summary"],
        "The vital signs, the analysis, the alerts and the local model keep running.",
    )
    return notice


def _state(settings: Settings, safe_mode: dict[str, Any]) -> dict[str, Any]:
    """El modo seguro y, aparte, el freno por fichero de Polaris (`halt`), con su aviso.

    `halt` no es el modo seguro ni pasa por el ledger (`polaris.halt_file` dice qué es), pero
    también corta la salida: si está puesto tiene que verse aquí, que es donde se mira por qué no
    sale nada. Levantar el modo seguro no lo quita.

    Los dos llevan un `since` y no valen lo mismo: el del modo seguro es la hora de su asiento
    firmado en el ledger; `halt.since` es la fecha de modificación del fichero, sin firma
    (`egress.halt_state`). `halt.notice` es el texto que la consola pinta (`halt_notice`).

    `version` (§5.38.13) cuenta los cambios del modo seguro y viaja en la lectura y en la
    respuesta de cada cambio, con `store_epoch` (de qué almacén es): la consola se queda con la
    más nueva sin releer. La de un cambio es la del asiento que firmó (`change_safe_mode`).
    Versiona el modo seguro, no el freno: `halt` se lee al componer cada respuesta, y dos
    respuestas con la misma versión pueden traerlo de momentos distintos.
    """
    halt = egress.halt_state()
    halt["notice"] = halt_notice(halt, settings.offline)
    return {**safe_mode, "halt": halt}


@safe_mode_router.get("")
def read_safe_mode(store: StoreDep, settings: SettingsDep) -> dict[str, Any]:
    return _state(settings, store.safe_mode())


@safe_mode_router.post("", status_code=201)
def set_safe_mode(
    store: StoreDep, settings: SettingsDep, payload: SafeModeIn
) -> dict[str, Any]:
    try:
        # El estado tal como lo dejó este asiento, con su versión: si otro cambio se firma
        # mientras se compone la respuesta, esta no se presenta como la suya (§5.38.13).
        changed = store.change_safe_mode(
            payload.active, payload.reason, payload.declared_by, identity_for(CONSOLE_IDENTITY)
        )
    except SafeModeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        # Activar sin motivo, levantar sin nombre o un texto que el ledger no firma: el fallo
        # es del dato (422), no un conflicto con el estado (409), como en `/mission-mode`.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _state(settings, changed)


def active_reason() -> str | None:
    """Para la puerta de salida: el motivo si el modo seguro está activo, o None.

    Sin almacén abierto todavía no hay modo seguro que consultar.
    """
    store = routes._store
    if store is None:
        return None
    state = store.safe_mode()
    return str(state["reason"] or "sin motivo") if state["active"] else None


egress.set_safe_mode_provider(active_reason)
