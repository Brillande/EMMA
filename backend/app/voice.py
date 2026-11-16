# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dictar en vez de escribir: un audio pasa a texto con `transcribe_audios.py` de Polaris y Whisper.

Por qué existe: con guantes, con una mano ocupada o con dolor, escribir una nota cuesta; hablar,
no. Polaris transcribe notas de voz en local con Whisper (sin red, sin nube). Aquí se usa su
script tal cual en un entorno aparte (`backend/.venv-voice`, `scripts/install_voice.py`), con un
cambio decidido a la copia: `SRC` y `OUT` por variable de entorno, para que lea el audio de una
carpeta temporal y escriba fuera de `polaris/` (`polaris/CAMBIOS.json`).

Lo que devuelve es un **borrador**: no se firma ni entra en nada por sí mismo. La interfaz lo pone
en la nota de un informe de dolor, la persona lo lee y lo corrige, y solo al enviar el informe se
firma, marcado `dictada-revisada` (invariante 7: un modelo no escribe en el registro).

Solo Ogg/Opus, que es lo que su script busca (`*.opus`) y lo que `soundfile` lee sin ffmpeg.

Licencia y origen (AGPL §5a): ejecuta `polaris/tools/transcribe_audios.py` de la copia de Polaris
(commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the
Protocol») como programa aparte, sin importarlo. El único cambio a ese fichero es el declarado en
`polaris/CAMBIOS.json`. De EMMA: la carpeta temporal, el entorno aparte y el techo de memoria.

EL IDIOMA DEL DICTADO (2026-11-15, el asistente también en inglés). Su script le dice a Whisper
`language="es"` en la propia llamada, y la copia no se edita. Con la consola en castellano se
lanza como siempre, sin nada en medio. Con la consola en otro idioma se lanza el mismo fichero,
sin tocar, desde un lanzador de EMMA (`_IN_LANGUAGE`) que antes de ejecutarlo envuelve
`whisper.load_model` para que el modelo transcriba en el idioma pedido. Es pegamento de EMMA
alrededor de la copia, no un cambio a ella; si se prefiere un cambio declarado al script (el
idioma por variable de entorno, como `SRC` y `OUT`), es decisión del usuario y va en
`polaris/CAMBIOS.json`.
"""

from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path

from app import memguard, polaris
from app.core import i18n

MAX_BYTES = 20 * 1024 * 1024
# Techo de memoria del árbol de Whisper (`app/memguard.py`, Polaris `guarda_memoria`). Medido el
# 2026-10-04: modelo `base`, 20 s de audio, pico de 1,47 GB (procesa en ventanas de 30 s, no crece
# con la duración). 4 GB es ~2,7 veces lo medido.
CEILING_GB = 4.0
IDLE_S = 300.0
MODEL = "base"
_OGG = b"OggS"
# El idioma que el script de Polaris lleva escrito en su llamada a Whisper.
SCRIPT_LANGUAGE = "es"
LANGUAGE_ENV = "EMMA_VOICE_LANGUAGE"
# El lanzador para otro idioma: corre en el entorno de la voz, sin importar nada de EMMA. Envuelve
# `whisper.load_model` para que el modelo que carga el script transcriba en `LANGUAGE_ENV`, y
# ejecuta el script de la copia tal cual, como programa principal y con sus mismos argumentos.
_IN_LANGUAGE = (
    "import os, runpy, sys, whisper\n"
    f"language = os.environ[{LANGUAGE_ENV!r}]\n"
    "load = whisper.load_model\n"
    "def load_model(*args, **kwargs):\n"
    "    model = load(*args, **kwargs)\n"
    "    transcribe = model.transcribe\n"
    "    def in_language(*heard, **options):\n"
    "        options['language'] = language\n"
    "        return transcribe(*heard, **options)\n"
    "    model.transcribe = in_language\n"
    "    return model\n"
    "whisper.load_model = load_model\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)


# Lo más largo que se transcribe: una nota de dolor dictada. Los 20 MB de `MAX_BYTES` de Opus a
# 6 kbit/s son más de siete horas de Whisper en CPU, sin plazo (auditoría run-2,
# `emma:voice:ogg-transcription-unbounded`).
MAX_SECONDS = 300.0


def ogg_seconds(audio: bytes) -> float:
    """La duración que declara un Ogg, leída de sus páginas sin descodificar nada.

    La posición de gránulo de la última página es la muestra final: en Opus siempre a 48 kHz
    (RFC 7845), en Vorbis a la frecuencia de su cabecera de identificación. Otro códec o un Ogg
    sin páginas legibles: `ValueError`.
    """
    if b"OpusHead" in audio[:512]:
        rate = 48_000
    elif (at := audio.find(b"\x01vorbis", 0, 512)) >= 0 and len(audio) >= at + 16:
        rate = struct.unpack_from("<I", audio, at + 12)[0]
    else:
        raise ValueError("solo audio Ogg con Opus o Vorbis")
    if rate <= 0:
        raise ValueError("frecuencia de muestreo no válida")
    last = -1
    at = audio.find(_OGG)
    while at >= 0 and at + 14 <= len(audio):
        (granule,) = struct.unpack_from("<q", audio, at + 6)
        last = max(last, granule)
        at = audio.find(_OGG, at + 4)
    if last < 0:
        raise ValueError("el Ogg no declara su duración")
    return last / rate


# PLAZO DE RELOJ. La guarda de memoria (`memguard.run`, `guarda_memoria.corre` de Polaris) corta
# por memoria y por CPU parada, no por tiempo: una transcripción que trabaja sin parar no acababa
# nunca (auditoría run-2, `emma:voice:ogg-transcription-unbounded`). Polaris no se edita aquí, así
# que el plazo lo pone EMMA envolviendo el comando: este lanzador corre con el mismo Python de voz,
# arranca el comando de siempre y, pasado el plazo, mata su árbol entero y sale con
# `DEADLINE_CODE`. La guarda sigue mirando la memoria del árbol, que ahora cuelga del lanzador.
DEADLINE_CODE = 97
_WITH_DEADLINE = (
    "import subprocess, sys\n"
    "limit = float(sys.argv[1])\n"
    "proc = subprocess.Popen(sys.argv[2:])\n"
    "try:\n"
    "    sys.exit(proc.wait(timeout=limit))\n"
    "except subprocess.TimeoutExpired:\n"
    "    if sys.platform == 'win32':\n"
    "        subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True)\n"
    "    else:\n"
    "        proc.kill()\n"
    "    proc.wait()\n"
    f"    sys.exit({DEADLINE_CODE})\n"
)


def deadline_s(audio_seconds: float) -> float:
    """El plazo de una transcripción: un minuto de arranque y carga del modelo más tres veces la
    duración del audio (Whisper `base` en CPU va bastante más rápido que el tiempo real; medido en
    el portátil, 4-6 s por nota corta). Con `MAX_SECONDS` = 300, como mucho 16 minutos."""
    return 60.0 + 3.0 * audio_seconds


def _with_deadline(command: list[str], seconds: float) -> list[str]:
    """`command`, lanzado desde el envoltorio que lo mata al pasar `seconds`."""
    return [str(_python()), "-c", _WITH_DEADLINE, f"{seconds:.0f}", *command]


class VoiceUnavailable(RuntimeError):
    """La transcripción no está instalada o no respondió; el mensaje dice por qué."""


def venv() -> Path:
    configured = os.environ.get("BTP_VENV_VOICE")
    return Path(configured) if configured else Path(__file__).resolve().parents[1] / ".venv-voice"


def _python() -> Path:
    """El intérprete del entorno: el de un venv o, si no lo hay, el de una copia de Python.

    El paquete de modelos (`backend/packaging/models_pack.py`) no lleva un venv —apunta al Python
    de la máquina que lo creó y no funciona en otra—, sino una copia entera de Python con
    `python.exe` en su raíz.
    """
    if os.name != "nt":
        return venv() / "bin/python"
    in_venv = venv() / "Scripts/python.exe"
    return in_venv if in_venv.is_file() else venv() / "python.exe"


def ready() -> bool:
    """¿Instalada con su modelo comprobado? (marca de `scripts/install_voice.py`)."""
    return (venv() / "voice-ok.json").is_file() and _python().is_file()


def _parse(markdown: str, name: str) -> str:
    """La transcripción que su script escribe bajo la línea del fichero (`**[fecha]** `nombre``)."""
    lines = markdown.splitlines()
    for number, line in enumerate(lines):
        if f"`{name}`" in line and number + 1 < len(lines):
            text = lines[number + 1].strip()
            if text.startswith("[ERROR:"):
                raise VoiceUnavailable(f"Whisper no pudo leer el audio: {text}")
            return text
    raise VoiceUnavailable("Whisper no devolvió transcripción")


def _command(script: Path, language: str) -> list[str]:
    """Cómo se lanza su script: tal cual en su idioma; en otro, desde el lanzador de EMMA."""
    if language == SCRIPT_LANGUAGE:
        return [str(_python()), str(script), MODEL]
    return [str(_python()), "-c", _IN_LANGUAGE, str(script), MODEL]


def transcribe(audio: bytes) -> str:
    """El texto del audio, en el idioma de la petición. Borrador: quien lo pide lo revisa."""
    if not audio.startswith(_OGG):
        raise ValueError("solo audio Ogg/Opus (.opus, .ogg)")
    if len(audio) > MAX_BYTES:
        raise ValueError(f"audio de más de {MAX_BYTES // 2**20} MB")
    seconds = ogg_seconds(audio)
    if seconds > MAX_SECONDS:
        raise ValueError(f"audio de más de {MAX_SECONDS:.0f} s: se dicta una nota, no una sesión")
    if not ready():
        raise VoiceUnavailable(
            "transcripción no instalada en esta máquina (scripts/install_voice.py)"
        )
    script = polaris.tools_dir() / "transcribe_audios.py"
    with tempfile.TemporaryDirectory() as folder:
        source, out = Path(folder) / "src", Path(folder) / "out"
        (source / "dictado").mkdir(parents=True)
        name = "dictado.opus"
        (source / "dictado" / name).write_bytes(audio)
        env = {
            **os.environ,
            "BTP_AUDIO_SRC": str(source),
            "BTP_AUDIO_OUT": str(out),
            # El modelo, en el entorno instalado; nunca se descarga aquí.
            "XDG_CACHE_HOME": str(venv() / "cache"),
            "PYTHONIOENCODING": "utf-8",
        }
        language = str(i18n.current())
        if language != SCRIPT_LANGUAGE:
            env[LANGUAGE_ENV] = language
        try:
            limit = deadline_s(seconds)
            done = memguard.run(_with_deadline(_command(script, language), limit), CEILING_GB,
                                env=env, idle_s=IDLE_S)
        except OSError as exc:
            raise VoiceUnavailable(f"Whisper no respondió: {exc}") from exc
        if done.code == DEADLINE_CODE:
            raise VoiceUnavailable(f"la transcripción se cortó: pasó de su plazo de {limit:.0f} s")
        if done.killed_for_memory:
            raise VoiceUnavailable(
                f"la transcripción se cortó: pasó de {CEILING_GB:.0f} GB de memoria"
            )
        # Una carpeta, un fichero de salida. Se busca por extensión y no por nombre: en Windows su
        # `chatdir.rstrip("/")` deja la barra invertida y el fichero sale como `.md`, sin nombre.
        results = list(out.glob("*.md")) if out.is_dir() else []
        if done.code != 0 or len(results) != 1:
            raise VoiceUnavailable(
                f"la transcripción falló (código {done.code}); el detalle está en el registro"
            )
        return _parse(results[0].read_text(encoding="utf-8"), name)
