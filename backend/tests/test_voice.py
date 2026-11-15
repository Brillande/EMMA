"""Dictar la nota de un informe de dolor: `transcribe_audios.py` de Polaris con Whisper local.

La suite simula el subproceso (sin Whisper ni red); la prueba `live` usa el instalado.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import memguard, voice
from tests.test_pain import LUMBAR, _report

OGG = b"OggS" + b"\x00" * 64


def _fake_whisper(text: str) -> Any:
    def run(command: list[str], ceiling_gb: float, env: dict[str, str], **kwargs: Any) -> Any:
        assert ceiling_gb == voice.CEILING_GB  # con el techo de memoria de Polaris
        assert command[1].endswith("transcribe_audios.py")  # el script de la copia, tal cual
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
    assert client.post("/api/pain/voice", content=OGG).status_code == 503


def test_only_ogg_audio_is_accepted(client: TestClient) -> None:
    assert client.post("/api/pain/voice", content=b"RIFF....WAVE").status_code == 422


def test_the_transcription_comes_back_as_a_draft_and_is_not_stored(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "ready", lambda: True)
    monkeypatch.setattr(voice.memguard, "run", _fake_whisper("me duele la espalda al agacharme"))
    before = client.get("/api/audit").json()["total_entries"]
    body = client.post("/api/pain/voice", content=OGG).json()
    assert body["draft"] == "me duele la espalda al agacharme"
    assert body["origin"] == "dictada-revisada"
    assert client.get("/api/audit").json()["total_entries"] == before  # nada firmado


def test_a_whisper_error_is_not_a_transcription(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "ready", lambda: True)
    monkeypatch.setattr(voice.memguard, "run", _fake_whisper("[ERROR: formato no soportado]"))
    assert client.post("/api/pain/voice", content=OGG).status_code == 503


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
    response = client.post("/api/pain/voice", content=OGG)
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
