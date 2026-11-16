"""Dictar la nota de un informe de dolor: `transcribe_audios.py` de Polaris con Whisper local.

La suite simula el subproceso (sin Whisper ni red); la prueba `live` usa el instalado.
"""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import memguard, voice
from tests.test_pain import LUMBAR, _report


def _page(granule: int, payload: bytes) -> bytes:
    """Una página Ogg: lo que `voice.ogg_seconds` lee (magia y gránulo), sin CRC."""
    return (b"OggS" + b"\x00\x00" + struct.pack("<q", granule) + b"\x00" * 12
            + bytes([1, len(payload)]) + payload)


def ogg_opus(seconds: float) -> bytes:
    """Un Ogg/Opus mínimo que declara `seconds` de audio (Opus cuenta a 48 kHz)."""
    head = _page(0, b"OpusHead" + b"\x01\x01" + b"\x00" * 9)
    return head + _page(int(seconds * 48_000), b"\x00" * 8)


OGG = ogg_opus(4.0)
AUDIO = {"Content-Type": "audio/ogg"}


def _fake_whisper(text: str) -> Any:
    def run(command: list[str], ceiling_gb: float, env: dict[str, str], **kwargs: Any) -> Any:
        assert ceiling_gb == voice.CEILING_GB  # con el techo de memoria de Polaris
        # Envuelto en el lanzador con plazo; dentro, el script de la copia, tal cual.
        assert command[1:3] == ["-c", voice._WITH_DEADLINE]
        assert float(command[3]) == voice.deadline_s(4.0)
        assert command[5].endswith("transcribe_audios.py")
        assert (Path(env["BTP_AUDIO_SRC"]) / "dictado" / "dictado.opus").read_bytes() == OGG
        out = Path(env["BTP_AUDIO_OUT"])
        out.mkdir(parents=True)
        (out / "dictado.md").write_text(
            f"# Audios transcritos — dictado\n\n**[dictado.opus]** `dictado.opus`\n{text}\n\n",
            encoding="utf-8",
        )
        return memguard.Outcome(0, 1.4)

    return run


def test_without_whisper_it_is_declared_absent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "ready", lambda: False)

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("sin la instalación comprobada no se lanza nada")

    monkeypatch.setattr(voice.memguard, "run", never)
    assert client.get("/api/pain/voice").json()["available"] is False
    assert client.post("/api/pain/voice", content=OGG, headers=AUDIO).status_code == 503


def test_only_ogg_audio_is_accepted(client: TestClient) -> None:
    assert client.post("/api/pain/voice", content=b"RIFF....WAVE", headers=AUDIO).status_code == 422


def test_the_transcription_comes_back_as_a_draft_and_is_not_stored(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "ready", lambda: True)
    monkeypatch.setattr(voice.memguard, "run", _fake_whisper("me duele la espalda al agacharme"))
    before = client.get("/api/audit").json()["total_entries"]
    body = client.post("/api/pain/voice", content=OGG, headers=AUDIO).json()
    assert body["draft"] == "me duele la espalda al agacharme"
    assert body["origin"] == "dictada-revisada"
    assert client.get("/api/audit").json()["total_entries"] == before  # nada firmado


def test_a_whisper_error_is_not_a_transcription(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "ready", lambda: True)
    monkeypatch.setattr(voice.memguard, "run", _fake_whisper("[ERROR: formato no soportado]"))
    assert client.post("/api/pain/voice", content=OGG, headers=AUDIO).status_code == 503


def test_without_an_audio_type_it_is_refused_before_reading(client: TestClient) -> None:
    """Una petición simple de otra página lleva `text/plain` (auditoría run-2,
    `emma:voice:ogg-transcription-unbounded`)."""
    for headers in ({}, {"Content-Type": "text/plain"}):
        assert client.post("/api/pain/voice", content=OGG, headers=headers).status_code == 415


def test_a_dictation_longer_than_its_cap_is_refused_before_whisper(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """20 MB de Opus son horas de Whisper en CPU: se mira la duración que declara el Ogg."""
    called: list[int] = []
    monkeypatch.setattr(voice, "ready", lambda: True)
    monkeypatch.setattr(voice.memguard, "run", lambda *a, **k: called.append(1))
    long = ogg_opus(voice.MAX_SECONDS + 1)
    response = client.post("/api/pain/voice", content=long, headers=AUDIO)
    assert response.status_code == 422 and "s:" in response.json()["detail"]
    assert called == []


def test_the_declared_duration_is_read_from_the_last_page() -> None:
    assert voice.ogg_seconds(ogg_opus(12.5)) == 12.5
    vorbis_head = b"\x01vorbis" + b"\x00\x00\x00\x00" + b"\x01" + struct.pack("<I", 16_000)
    vorbis = _page(0, vorbis_head + b"\x00" * 8) + _page(32_000, b"\x00")
    assert voice.ogg_seconds(vorbis) == 2.0
    with pytest.raises(ValueError, match="Opus o Vorbis"):
        voice.ogg_seconds(b"OggS" + b"\x00" * 64)


def test_a_second_transcription_waits_for_nobody(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una a la vez: mientras una corre, la siguiente recibe 429 y no hace cola.

    El semáforo se sustituye por uno «ocupado» que falla si alguien intenta esperarlo: así, si la
    ruta dejara de mirar `locked()`, la prueba fallaría en vez de quedarse esperando para siempre.
    """
    from app.api import pain

    class Busy:
        def locked(self) -> bool:
            return True

        async def __aenter__(self) -> None:
            raise AssertionError("esperó al semáforo en vez de responder 429")

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(pain, "_voice_slot", Busy())
    response = client.post("/api/pain/voice", content=OGG, headers=AUDIO)
    assert response.status_code == 429


def test_the_deadline_launcher_kills_what_runs_too_long() -> None:
    """El lanzador de verdad, con el Python de las pruebas: un proceso que dura más que su plazo
    muere y el lanzador sale con `DEADLINE_CODE` (auditoría run-2,
    `emma:voice:ogg-transcription-unbounded`: la guarda de Polaris no tiene plazo de reloj)."""
    import sys
    import time

    slow = [sys.executable, "-c", "import time; time.sleep(60)"]
    started = time.monotonic()
    done = subprocess.run(
        [sys.executable, "-c", voice._WITH_DEADLINE, "1", *slow], timeout=30, check=False
    )
    assert done.returncode == voice.DEADLINE_CODE
    assert time.monotonic() - started < 20


def test_the_deadline_launcher_passes_the_exit_code_through() -> None:
    import sys

    quick = [sys.executable, "-c", "import sys; sys.exit(3)"]
    done = subprocess.run(
        [sys.executable, "-c", voice._WITH_DEADLINE, "30", *quick], timeout=30, check=False
    )
    assert done.returncode == 3


def test_a_transcription_past_its_deadline_says_so(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "ready", lambda: True)
    monkeypatch.setattr(voice.memguard, "run", lambda command, ceiling_gb, **kw:
                        memguard.Outcome(voice.DEADLINE_CODE, 1.0))
    response = client.post("/api/pain/voice", content=OGG, headers=AUDIO)
    assert response.status_code == 503 and "plazo" in response.json()["detail"]


def test_the_deadline_grows_with_the_audio_and_is_bounded() -> None:
    assert voice.deadline_s(10) < voice.deadline_s(100)
    assert voice.deadline_s(voice.MAX_SECONDS) <= 16 * 60


def test_the_reviewed_note_is_signed_with_its_origin(client: TestClient) -> None:
    body = _report(LUMBAR, note="me duele al agacharme", note_origin="dictada-revisada")
    assert client.post("/api/pain/reports", json=body).status_code == 201
    [report] = client.get("/api/pain/reports").json()
    assert report["note"] == "me duele al agacharme"
    assert report["note_origin"] == "dictada-revisada"
    assert client.post("/api/pain/reports", json=_report(note="x" * 1001)).status_code == 422


def test_a_typed_note_is_marked_typed(client: TestClient) -> None:
    typed = _report(LUMBAR, note="punzante")
    assert client.post("/api/pain/reports", json=typed).status_code == 201
    [report] = client.get("/api/pain/reports").json()
    assert report["note_origin"] == "escrita"


@pytest.mark.live
@pytest.mark.skipif(not voice.ready(), reason="Whisper no instalado (scripts/install_voice.py)")
def test_the_installed_whisper_transcribes_an_ogg(tmp_path: Path) -> None:
    # El audio se genera en el entorno de voz, que es el que tiene soundfile.
    sound = tmp_path / "tono.ogg"
    make = (
        "import numpy as np, soundfile as sf, sys; "
        "sf.write(sys.argv[1], (0.1 * np.sin(np.linspace(0, 2764, 16000))).astype('float32'), "
        "16000, format='OGG', subtype='OPUS')"
    )
    subprocess.run([str(voice._python()), "-c", make, str(sound)], check=True)
    assert isinstance(voice.transcribe(sound.read_bytes()), str)


def test_a_transcription_cut_for_memory_says_so(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "ready", lambda: True)
    monkeypatch.setattr(voice.memguard, "run",
                        lambda command, ceiling_gb, **kw: memguard.Outcome(99, 4.2))
    response = client.post("/api/pain/voice", content=OGG, headers=AUDIO)
    assert response.status_code == 503 and "se cortó" in response.json()["detail"]



@pytest.mark.skipif(voice.os.name != "nt", reason="la copia de Python del paquete es de Windows")
def test_a_python_copy_from_the_models_pack_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El paquete de modelos trae una copia de Python (`python.exe` en la raíz), no un venv."""
    monkeypatch.setenv("BTP_VENV_VOICE", str(tmp_path))
    (tmp_path / "python.exe").write_bytes(b"")
    (tmp_path / "voice-ok.json").write_text("{}", encoding="utf-8")
    assert voice._python() == tmp_path / "python.exe"
    assert voice.ready()
    # Con un venv, manda el venv.
    (tmp_path / "Scripts").mkdir()
    (tmp_path / "Scripts" / "python.exe").write_bytes(b"")
    assert voice._python() == tmp_path / "Scripts" / "python.exe"
