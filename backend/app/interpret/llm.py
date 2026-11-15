"""Cliente de un modelo de lenguaje local con la API de chat de Ollama (licencia MIT).

Formato verificado en la documentación de Ollama (`docs/api.md`, "Generate a chat completion"):
`POST /api/chat` con `stream: false`, `format` como esquema JSON para salida estructurada y
`options.temperature`; la respuesta trae el texto en `message.content`.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core import i18n

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Contexto que se pide al modelo. Los hechos de un estudio con su historial caben de sobra;
# el valor por defecto de Ollama (4096) se quedaba corto con el verificador, que recibe
# hechos y borrador a la vez.
CONTEXT_TOKENS = 8192
# Cuánto se queda el modelo en la GPU tras la última petición (formato de Ollama).
KEEP_ALIVE = "30m"


class LlmUnavailable(RuntimeError):
    """No hay modelo local que responda, o respondió algo inservible. El motivo va en el mensaje."""


class LocalLlm:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0,
                 context_tokens: int = CONTEXT_TOKENS) -> None:
        host = urlparse(base_url).hostname
        if host not in LOOPBACK_HOSTS:
            # Los datos clínicos no salen de la nave. Una URL remota sería exactamente eso.
            raise ValueError(f"el modelo tiene que ser local (loopback), no {host!r}")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.context_tokens = context_tokens

    def available(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
        except httpx.HTTPError:
            return False
        if response.status_code != 200:
            return False
        try:
            names = {item.get("name") for item in response.json().get("models", [])}
        except (ValueError, AttributeError):
            return False
        return self.model in names

    def structured(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Una respuesta que cumple `schema`, ya parseada. Determinista: temperatura 0."""
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "format": schema,
                    "stream": False,
                    # SIN RAZONAMIENTO PREVIO.
                    #
                    # Probado con qwen3.5:9b el 2026-09-24: con el razonamiento activo el
                    # modelo pensaba cientos de tokens, agotaba el contexto por defecto
                    # (4096) y devolvia `content` vacio. La tarea es redactar a partir de
                    # hechos dados, no deducir: el razonamiento solo cuesta tiempo.
                    "think": False,
                    "options": {"temperature": 0, "num_ctx": self.context_tokens},
                    # EL MODELO SE QUEDA CARGADO. Ollama lo descarga a los 5 min sin uso y
                    # recargarlo cuesta ~4 s (medido el 2026-11-03 con qwen3.5:9b: 4,6 s en frio,
                    # 0,3 s ya cargado). El asistente de voz no puede esperar eso en cada pausa.
                    "keep_alive": KEEP_ALIVE,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
            if body.get("done_reason") == "length":
                raise LlmUnavailable(
                    "el modelo local agotó el contexto antes de terminar la respuesta"
                )
            content = body["message"]["content"]
            parsed = json.loads(content)
        except httpx.HTTPError as exc:
            raise LlmUnavailable(f"el modelo local no responde: {exc}") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise LlmUnavailable(f"el modelo local devolvió algo inservible: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LlmUnavailable("el modelo local no devolvió un objeto JSON")
        return parsed

    def hears(self) -> bool:
        """¿Declara el modelo que entiende audio? (`capabilities` de `POST /api/show`).

        Lo que se sabe se recuerda por servidor y modelo; un fallo de red no se recuerda, para
        volver a preguntar la próxima vez.
        """
        key = (self.base_url, self.model)
        if key in _HEARS:
            return _HEARS[key]
        try:
            response = httpx.post(f"{self.base_url}/api/show", json={"model": self.model},
                                  timeout=3.0)
        except httpx.HTTPError:
            return False
        if response.status_code != 200:
            return False
        try:
            capabilities = response.json().get("capabilities") or []
        except (ValueError, AttributeError):
            return False
        _HEARS[key] = "audio" in capabilities
        return _HEARS[key]

    def transcribe(self, wav: bytes) -> str:
        """Lo dicho en un WAV, en texto, por el propio modelo. Vacío si no se entiende nada.

        Formato verificado contra Ollama 0.40.14 el 2026-11-06: el audio WAV va en `images` del
        mensaje, en base64, igual que una imagen. Temperatura 0 y salida con esquema, para que
        devuelva lo dicho y no una respuesta a lo dicho.
        """
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        # El idioma en que se transcribe es el de la consola: el modelo escribe
                        # lo que oye en el idioma que se le dice (ver `HEARING_PROMPT_EN`).
                        {"role": "system", "content": hearing_prompt()},
                        {"role": "user",
                         "content": i18n.tr("Transcribe este audio.", "Transcribe this audio."),
                         "images": [base64.b64encode(wav).decode("ascii")]},
                    ],
                    "format": _TRANSCRIPT_SCHEMA,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0, "num_ctx": self.context_tokens},
                    "keep_alive": KEEP_ALIVE,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            text = json.loads(response.json()["message"]["content"])["text"]
        except httpx.HTTPError as exc:
            raise LlmUnavailable(f"el modelo local no responde: {exc}") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise LlmUnavailable(f"el modelo local devolvió algo inservible: {exc}") from exc
        if not isinstance(text, str):
            raise LlmUnavailable("el modelo local no devolvió texto")
        return text.strip()


# Qué modelos oyen, por (servidor, modelo). Ver `LocalLlm.hears`.
_HEARS: dict[tuple[str, str], bool] = {}

# Probado el 2026-11-06 con gemma4:e4b y cuatro frases dichas por las voces es-ES de Windows:
# las cuatro bien y «EMMA» escrito como tal (sin nombrarla en el prompt salía «M»); un silencio
# da texto vacío.
HEARING_PROMPT = (
    "Eres el oído de EMMA, el asistente de salud de una misión espacial. Transcribe "
    "literalmente, en español, lo que dice la persona en el audio: puede llamar al asistente "
    "«EMMA». Solo lo dicho, sin responder ni comentar. Si no se entiende nada, deja el texto "
    "vacío."
)
# El mismo encargo con la consola en inglés (2026-11-15): que escriba en inglés lo que oye. Sin
# medir con voces inglesas: el castellano se midió con gemma4:e4b y este es su calco.
HEARING_PROMPT_EN = (
    "You are the ear of EMMA, the health assistant of a space mission. Transcribe literally, in "
    "English, what the person says in the audio: they may call the assistant «EMMA». Only what "
    "is said, without answering or commenting. If nothing can be understood, leave the text "
    "empty."
)


def hearing_prompt() -> str:
    """El encargo de transcribir, en el idioma de la petición."""
    return HEARING_PROMPT_EN if i18n.current() == "en" else HEARING_PROMPT


_TRANSCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}
