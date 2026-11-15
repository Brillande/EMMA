"""De lo que graba la consola (WAV) a lo que lee el transcriptor (Ogg/Opus), en local.

Por qué existe: `MediaRecorder` de Chromium y de Electron no graba `audio/ogg;codecs=opus`
(lo halló la unidad de la interfaz el 2026-11-03), y el script de Polaris que usa `app/voice.py`
solo busca `*.opus`. La consola graba entonces WAV PCM de 16 bits mono con un AudioWorklet, y aquí
se pasa a Ogg/Opus antes de transcribir.

Dónde se convierte: en el entorno de la voz (`backend/.venv-voice`), con su `soundfile`, cuya
libsndfile escribe OGG/OPUS (comprobado el 2026-11-03: soundfile 0.14.0, libsndfile 1.2.2). El
entorno de EMMA no lleva `soundfile` y no se le añade una dependencia para esto: sin la voz
instalada no hay a quién darle el audio, así que la conversión vive donde vive Whisper. Corre
como programa aparte, sin red, sobre una carpeta temporal que se borra al terminar; el audio no
se guarda.

Opus solo admite 8, 12, 16, 24 y 48 kHz: otra frecuencia es un 422 con su motivo, sin remuestrear
aquí. Topes: los bytes de `voice.MAX_BYTES` y `MAX_SECONDS` de duración, que para una orden
hablada sobra.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import wave
from pathlib import Path

from app import voice

MAX_SECONDS = 60.0
OPUS_RATES = frozenset({8000, 12000, 16000, 24000, 48000})
CONVERT_TIMEOUT_S = 60.0
_RIFF = b"RIFF"
_WAVE = b"WAVE"
# Lo que corre en el entorno de la voz. Sin importar nada de EMMA.
_CONVERT = (
    "import sys, soundfile as sf; "
    "data, rate = sf.read(sys.argv[1], dtype='int16'); "
    "sf.write(sys.argv[2], data, rate, format='OGG', subtype='OPUS')"
)


def is_wav(audio: bytes) -> bool:
    return audio[:4] == _RIFF and audio[8:12] == _WAVE


def check_wav(audio: bytes) -> None:
    """PCM de 16 bits, mono, a una frecuencia de Opus y dentro de los topes; si no, `ValueError`."""
    if len(audio) > voice.MAX_BYTES:
        raise ValueError(f"audio de más de {voice.MAX_BYTES // 2**20} MB")
    try:
        with wave.open(io.BytesIO(audio)) as reader:
            channels, width = reader.getnchannels(), reader.getsampwidth()
            rate, frames = reader.getframerate(), reader.getnframes()
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"WAV ilegible: {exc}") from exc
    if channels != 1 or width != 2:
        raise ValueError("solo WAV PCM de 16 bits y mono")
    if rate not in OPUS_RATES:
        raise ValueError(
            f"frecuencia de {rate} Hz: Opus admite {', '.join(map(str, sorted(OPUS_RATES)))}"
        )
    if frames == 0:
        raise ValueError("el audio está vacío")
    if frames / rate > MAX_SECONDS:
        raise ValueError(f"audio de más de {MAX_SECONDS:.0f} s")


def wav_to_ogg(audio: bytes) -> bytes:
    """El WAV, comprobado y pasado a Ogg/Opus por el entorno de la voz."""
    check_wav(audio)
    if not voice.ready():
        raise voice.VoiceUnavailable(
            "transcripción no instalada en esta máquina (scripts/install_voice.py)"
        )
    with tempfile.TemporaryDirectory() as folder:
        source, target = Path(folder) / "turno.wav", Path(folder) / "turno.opus"
        source.write_bytes(audio)
        try:
            done = subprocess.run(
                [str(voice._python()), "-I", "-c", _CONVERT, str(source), str(target)],
                capture_output=True, timeout=CONVERT_TIMEOUT_S, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise voice.VoiceUnavailable(f"no se pudo convertir el audio: {exc}") from exc
        if done.returncode != 0 or not target.is_file():
            raise voice.VoiceUnavailable(
                f"no se pudo convertir el audio (código {done.returncode})"
            )
        return target.read_bytes()


def to_ogg(audio: bytes) -> bytes:
    """Ogg/Opus tal cual; WAV, convertido. Lo demás, `ValueError`."""
    if is_wav(audio):
        return wav_to_ogg(audio)
    return audio
