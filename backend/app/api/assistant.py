"""Rutas del asistente de voz: qué puede hacer, un turno por texto y un turno por audio.

Por qué es un módulo aparte: el asistente no tiene almacén propio ni escribe en el de nadie
(`app/assistant/`, Clase C segregada). Estas rutas solo leen el estado y devuelven intención,
respuesta y, para una escritura, la propuesta que la interfaz firmará después por la ruta del
formulario de siempre. Sin modelo responden igual, con lo determinista: nunca un 500 por falta de
Ollama.

Por qué no hay `until` en la petición: el corte de Tierra lo calcula el backend con la misma regla
que la consola (`app/assistant/context.py`), para que nadie pueda pedirle a Tierra lo que aún no le
ha llegado.
"""

from __future__ import annotations

import base64
import binascii
import json
import threading
from typing import Annotated, Any, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from app import voice
from app.api.console_header import console_post
from app.api.routes import SettingsDep, StoreDep, _read_capped
from app.assistant import audio, catalog, controls, turn
from app.core.config import Settings
from app.core.i18n import tr
from app.core.storage import ObservationStore
from app.interpret.llm import LlmUnavailable, LocalLlm

assistant_router = APIRouter(prefix="/assistant")

# Lo que espera la consola a que el modelo conteste un turno. Medido el 2026-11-03: 0,70 s de
# mediana y 1,23 s de máximo con el modelo ya cargado; la primera carga en la GPU tarda más.
TURN_TIMEOUT_S = 60.0
# El contexto del modelo del asistente. Con el mapa de la aplicación (pestañas con lo que hay
# dentro, ejemplos y los paneles más parecidos) el prompt de la consola de a bordo ronda los 7000
# tokens (medido el 2026-11-04 con qwen3.5:9b), y con ocho turnos de historial no cabía en 8192.
# Con 12288 qwen3.5:9b sigue entero en la GPU de 8 GB (`ollama ps`: 5,5 GB, 100 % GPU); con 16384
# ya no (21 % en CPU).
CONTEXT_TOKENS = 12288
Console = Literal["crew", "ground"]
Subject = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class HistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class ControlIn(BaseModel):
    """Un botón que la consola tiene a la vista (`app/assistant/controls.py`)."""

    model_config = ConfigDict(extra="forbid")

    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                            max_length=controls.MAX_LABEL)]
    # Si pulsarlo guarda algo: entonces no se pulsa sin «confirmo». En la duda, la consola dice sí.
    writes: bool = True


class TurnIn(BaseModel):
    """Un turno. El historial lo guarda la consola, no el backend: aquí solo viaja."""

    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    console: Console
    subject: Subject
    history: list[HistoryItem] = Field(default_factory=list, max_length=turn.MAX_HISTORY)
    # Quien firmará si se confirma una propuesta: solo para decirlo en la respuesta. No firma aquí.
    operator: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None = None
    # Los modos de pantalla que la consola tiene puestos ahora (`DisplayModes`, los de sí o no):
    # solo para entender «ya se han ido» con la privacidad puesta. No se guardan ni cambian nada.
    modes: dict[str, bool] | None = None
    # Los botones a la vista, para pulsar uno por voz. Sin ellos, el asistente no pulsa ninguno.
    controls: list[ControlIn] = Field(default_factory=list, max_length=controls.MAX_CONTROLS)

    @field_validator("modes")
    @classmethod
    def _known_modes(cls, value: dict[str, bool] | None) -> dict[str, bool] | None:
        if value is not None and not set(value) <= set(catalog.catalog().toggle_modes()):
            raise ValueError("modos de pantalla fuera del inventario")
        return value


def llm_for(settings: Settings) -> LocalLlm | None:
    """El cliente del modelo del asistente, o None si la dirección no es de loopback."""
    try:
        return LocalLlm(settings.llm_url, settings.assistant_model, timeout=TURN_TIMEOUT_S,
                        context_tokens=CONTEXT_TOKENS)
    except ValueError:
        return None


def _unavailable_reason(settings: Settings, llm: LocalLlm | None) -> str | None:
    if llm is None:
        return tr(f"el modelo tiene que ser local (loopback); {settings.llm_url} no lo es",
                  f"the model has to be local (loopback); {settings.llm_url} is not")
    if not llm.available():
        return tr(
            f"el modelo local {settings.assistant_model} no responde en {settings.llm_url} "
            "(servidor apagado o sin ese modelo): el asistente sigue con palabras clave y el "
            "texto del backend",
            f"the local model {settings.assistant_model} does not answer at {settings.llm_url} "
            "(server off or without that model): the assistant carries on with keywords and "
            "the backend text",
        )
    return None


_warmed: set[tuple[str, str]] = set()
_warm_lock = threading.Lock()


def warm_up(settings: Settings, llm: LocalLlm | None) -> threading.Thread | None:
    """Carga el modelo en memoria con una petición mínima, en segundo plano y una sola vez.

    Por qué: en frío, el primer turno esperaba a que Ollama cargara el modelo (4-5 s medidos el
    2026-11-03). La consola pide `GET /api/assistant` al abrirse; para cuando alguien habla, el
    modelo ya está. No bloquea la respuesta y sin Ollama no pasa nada: se intentará la próxima vez.
    """
    if not settings.assistant_warmup or llm is None:
        return None
    key = (llm.base_url, llm.model)
    with _warm_lock:
        if key in _warmed:
            return None
        _warmed.add(key)

    def run() -> None:
        # Cualquier fallo, no solo `LlmUnavailable`, deja que la próxima petición lo intente otra
        # vez: un hilo muerto no puede dejar el modelo marcado como caliente para siempre.
        try:
            llm.structured("Responde con {}.", "hola", {"type": "object"})
        except Exception:  # noqa: BLE001 — precalentar no puede romper nada
            with _warm_lock:
                _warmed.discard(key)

    thread = threading.Thread(target=run, name="emma-assistant-warmup", daemon=True)
    thread.start()
    return thread


@assistant_router.get("")
def assistant_status(settings: SettingsDep) -> dict[str, Any]:
    """Si hay modelo y voz, el catálogo entero de intenciones con sus esquemas y el inventario de
    la interfaz (`data/assistant_ui.json`): la consola lo lee de aquí para saber en qué pestaña
    está cada panel que se le pide, sin copiarlo."""
    llm = llm_for(settings)
    reason = _unavailable_reason(settings, llm)
    if reason is None:
        warm_up(settings, llm)
    voice_by = ("model" if reason is None and hearer(settings) is not None
                else "whisper" if voice.ready() else None)
    return {
        "available": reason is None,
        "model": settings.assistant_model,
        "reason": reason,
        # Hay voz si el propio modelo oye (`assistant_hearing`) o si hay Whisper.
        "voice_available": voice_by is not None,
        "voice_by": voice_by,
        "intents": catalog.describe(),
        "ui": catalog.ui_inventory(),
    }


def _turn(settings: Settings, store: ObservationStore, payload: TurnIn) -> dict[str, Any]:
    result = turn.run(
        settings, store, llm_for(settings),
        text=payload.text, console=payload.console, subject=payload.subject,
        history=[item.model_dump() for item in payload.history],
        operator=payload.operator or None, modes=payload.modes,
        controls=[controls.Control(item.label, item.writes) for item in payload.controls],
    )
    return result.to_dict()


@assistant_router.post("/turn")
def assistant_turn(store: StoreDep, settings: SettingsDep, payload: TurnIn) -> dict[str, Any]:
    """Intención, respuesta y, si es una escritura, la propuesta sin firmar. No escribe nada."""
    return _turn(settings, store, payload)


HISTORY_HEADER = "X-EMMA-History"
OPERATOR_HEADER = "X-EMMA-Operator"
MODES_HEADER = "X-EMMA-Modes"
CONTROLS_HEADER = "X-EMMA-Controls"


def _modes(header: str | None) -> dict[str, bool] | None:
    """Los modos de la cabecera: los ids puestos, separados por comas (`privacy,lowVision`)."""
    if header is None:
        return None
    known = catalog.catalog().toggle_modes()
    on = {item.strip() for item in header.split(",") if item.strip()}
    if not on <= set(known):
        raise HTTPException(status_code=422, detail=f"{MODES_HEADER}: modos fuera del inventario")
    return {mode: mode in on for mode in known}


def _controls(encoded: str | None) -> list[ControlIn]:
    """Los botones de la cabecera: JSON en base64 (UTF-8), con las reglas del cuerpo de `/turn`."""
    if not encoded:
        return []
    try:
        items = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
        found = TypeAdapter(list[ControlIn]).validate_python(items)
    except (ValueError, binascii.Error, ValidationError) as exc:
        raise HTTPException(
            status_code=422, detail=f"{CONTROLS_HEADER}: JSON en base64 ilegible ({exc})"
        ) from exc
    if len(found) > controls.MAX_CONTROLS:
        raise HTTPException(
            status_code=422, detail=f"{CONTROLS_HEADER}: como mucho {controls.MAX_CONTROLS}"
        )
    return found


def _history(encoded: str | None) -> list[HistoryItem]:
    """El historial de la cabecera: JSON en base64 (UTF-8), con las reglas del cuerpo de `/turn`."""
    if not encoded:
        return []
    try:
        items = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
        history = TypeAdapter(list[HistoryItem]).validate_python(items)
    except (ValueError, binascii.Error, ValidationError) as exc:
        raise HTTPException(
            status_code=422, detail=f"{HISTORY_HEADER}: JSON en base64 ilegible ({exc})"
        ) from exc
    if len(history) > turn.MAX_HISTORY:
        raise HTTPException(
            status_code=422, detail=f"{HISTORY_HEADER}: como mucho {turn.MAX_HISTORY} turnos"
        )
    return history


@assistant_router.post(
    "/audio",
    **console_post(
        requestBody={
            "required": True,
            "content": {
                media: {"schema": {"type": "string", "format": "binary"}}
                for media in ("audio/wav", "audio/ogg")
            },
        }
    ),
)
async def assistant_audio(
    request: Request,
    store: StoreDep,
    settings: SettingsDep,
    console: Annotated[Console, Query()],
    subject: Annotated[str, Query(min_length=1, max_length=64)],
    x_emma_history: Annotated[str | None, Header()] = None,
    x_emma_operator: Annotated[str | None, Header(max_length=200)] = None,
    x_emma_modes: Annotated[str | None, Header(max_length=200)] = None,
    x_emma_controls: Annotated[str | None, Header(max_length=65536)] = None,
) -> dict[str, Any]:
    """Un audio hablado: se pasa a texto en local y sigue como un turno.

    Lo oye el propio modelo del asistente si oye y el audio es WAV (`assistant_hearing`, p. ej.
    gemma4:e4b); si no, Whisper (`app/voice.py`). `heard_by` dice cuál fue.

    Cuerpo binario, tal cual: Ogg/Opus, o WAV PCM de 16 bits mono (lo que graba la consola con
    un AudioWorklet), que para Whisper se convierte en local a Ogg/Opus
    (`app/assistant/audio.py`). Lo que en
    `/turn` va en el JSON viaja aquí en la consulta y en cabeceras, porque el cuerpo es el audio:

      * `?console=crew|ground&subject=crew-01`;
      * `X-EMMA-History`: el historial (la misma lista de `/turn`, máximo 8) como JSON en UTF-8
        codificado en base64;
      * `X-EMMA-Operator`: quien firmaría, codificado por ciento en UTF-8 (`Jos%C3%A9`);
      * `X-EMMA-Modes`: los modos de pantalla puestos, sus ids separados por comas
        (`privacy,lowVision`; vacía, ninguno). Sin ella, la consola no los ha dicho.
      * `X-EMMA-Controls`: los botones a la vista (la misma lista `controls` de `/turn`) como
        JSON en UTF-8 codificado en base64.

    Ejemplo: `curl -X POST "http://127.0.0.1:8000/api/assistant/audio?console=crew&subject=crew-01"
    -H "X-EMMA-Console: 1" -H "Content-Type: audio/wav" -H "X-EMMA-Operator: CMO"
    -H "X-EMMA-History: $(printf '[{"role":"user","text":"hola"}]' | base64 -w0)"
    --data-binary @orden.wav`.

    El audio no se guarda: va a una carpeta temporal y se borra con ella. Lleva la cabecera de la
    consola porque lee el cuerpo tal cual, sin `requestBody` declarado.
    """
    history = _history(x_emma_history)
    modes = _modes(x_emma_modes)
    shown = _controls(x_emma_controls)
    operator = unquote(x_emma_operator).strip()[:64] if x_emma_operator else None
    raw = await _read_capped(request, voice.MAX_BYTES)
    try:
        text, heard_by = await run_in_threadpool(_hear, settings, raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except voice.VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="no se ha entendido nada en el audio")
    payload = TurnIn(text=text[:1000], console=console, subject=subject, history=history,
                     operator=operator or None, modes=modes, controls=shown)
    body = await run_in_threadpool(_turn, settings, store, payload)
    return {"transcript": text, "heard_by": heard_by, "turn": body}


def hearer(settings: Settings) -> LocalLlm | None:
    """El modelo del asistente si oye y se le deja oír (`assistant_hearing`); si no, None."""
    if settings.assistant_hearing != "auto":
        return None
    llm = llm_for(settings)
    return llm if llm is not None and llm.hears() else None


def _hear(settings: Settings, raw: bytes) -> tuple[str, str]:
    """Lo dicho, en texto, y quién lo oyó: `model` o `whisper`.

    El modelo solo recibe WAV (lo que graba la consola), comprobado con los mismos topes que para
    Whisper. Si el modelo falla y Whisper está instalado, lo intenta Whisper: el turno por voz no
    se pierde por un modelo caído.
    """
    if audio.is_wav(raw):
        llm = hearer(settings)
        if llm is not None:
            audio.check_wav(raw)
            try:
                return llm.transcribe(raw), "model"
            except LlmUnavailable as exc:
                if not voice.ready():
                    raise voice.VoiceUnavailable(str(exc)) from exc
    return voice.transcribe(audio.to_ogg(raw)), "whisper"
