"""Una banda de pulso real, trama a trama, hasta las graficas del tripulante.

Una banda como la COOSPO HW9 manda ~1 trama por segundo con uno o dos intervalos R-R.
Antes la HRV exigia tres en la misma trama y con una banda de verdad no salia nunca; el
pulso se registraba, pero la variabilidad no llegaba a ninguna grafica. Estas pruebas
mandan la secuencia que manda una banda, por la API y sin red, y miran lo que queda.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi.testclient import TestClient

from app.ingest.wearable import HRV_MAX_GAP, NO_CONTACT_CONFIDENCE

SUBJECT = "real-01"
START = dt.datetime.now(dt.UTC).replace(microsecond=0) - dt.timedelta(minutes=5)


def rr_bytes(*intervals_ms: float) -> bytes:
    return b"".join(int(ms / 1000 * 1024).to_bytes(2, "little") for ms in intervals_ms)


def send(
    client: TestClient, at: dt.datetime, heart_rate: int = 62,
    rr: tuple[float, ...] = (960.0, 980.0), flags: int = 0b0001_0110, extra: bytes = b"",
) -> Any:
    frame = bytes([flags, heart_rate]) + extra + rr_bytes(*rr)
    response = client.post("/api/wearable/ble", json={
        "frame_hex": frame.hex(), "subject": SUBJECT, "effective": at.isoformat(),
        "device": "coospo-hw9",
    })
    assert response.status_code == 201, response.text
    return response.json()


def stream(client: TestClient, start: dt.datetime, seconds: int) -> list[Any]:
    return [
        send(client, start + dt.timedelta(seconds=second),
             rr=(960.0 + 15 * (second % 3), 990.0 - 10 * (second % 2)))
        for second in range(seconds)
    ]


def test_a_band_sequence_records_hrv_and_the_crew_member_follows_it(client: TestClient) -> None:
    replies = stream(client, START, 20)

    with_hrv = [reply for reply in replies if reply["hrv"] is not None]
    # 2 latidos por trama: la ventana llega a 30 en la trama 15, y no vuelve a emitir
    # hasta pasado un minuto.
    assert [replies.index(reply) for reply in with_hrv] == [14]
    hrv = with_hrv[0]["hrv"]
    assert set(hrv) == {"rmssd_ms", "sdnn_ms"}
    assert hrv["rmssd_ms"] > 0 and hrv["sdnn_ms"] > 0
    assert set(with_hrv[0]["indicators"]) == {"heart-rate", "hrv-rmssd", "hrv-sdnn"}
    assert all(reply["indicators"] == ["heart-rate"] for reply in replies if reply["hrv"] is None)
    # Cada observacion, al ledger: 20 pulsos y 2 de HRV.
    assert client.get("/api/audit").json()["total_entries"] == 22

    heart = client.get(
        "/api/observations", params={"key": "heart-rate", "subject": SUBJECT}
    ).json()
    assert heart["count"] == 20
    rmssd = client.get(
        "/api/observations", params={"key": "hrv-rmssd", "subject": SUBJECT}
    ).json()
    assert rmssd["count"] == 1
    observed = rmssd["observations"][0]
    assert observed["valueQuantity"]["value"] == hrv["rmssd_ms"]
    assert dt.datetime.fromisoformat(observed["effectiveDateTime"]) == START + dt.timedelta(
        seconds=14
    )

    status = client.get("/api/status", params={"subject": SUBJECT})
    assert status.status_code == 200
    reference = dt.datetime.fromisoformat(status.json()["data"]["reference_time"])
    assert abs(reference - (START + dt.timedelta(seconds=19))) <= dt.timedelta(seconds=1)


def test_the_response_carries_the_decoded_frame(client: TestClient) -> None:
    # Pulso uint16, contacto soportado y detectado, energia y dos R-R.
    frame = (
        bytes([0b0001_1111]) + (148).to_bytes(2, "little") + (350).to_bytes(2, "little")
        + rr_bytes(400.0, 410.0)
    )
    reply = client.post("/api/wearable/ble", json={
        "frame_hex": frame.hex(), "subject": SUBJECT, "effective": START.isoformat(),
    }).json()
    assert reply["frame"] == {
        "heart_rate": 148, "rr_ms": [399.4, 409.2], "sensor_contact": "detected",
        "energy_kj": 350,
    }
    assert reply["hrv"] is None
    # La energia no se registra: no hay codigo verificado para ella.
    assert reply["indicators"] == ["heart-rate"]

    bare = send(client, START + dt.timedelta(seconds=1), flags=0b0000_0000, rr=())
    assert bare["frame"] == {
        "heart_rate": 62, "rr_ms": [], "sensor_contact": "unsupported", "energy_kj": None,
    }


def test_a_gap_empties_the_window(client: TestClient) -> None:
    assert all(reply["hrv"] is None for reply in stream(client, START, 14))
    # Una trama mas tras el silencio no completa la ventana anterior: empieza otra.
    after = START + dt.timedelta(seconds=13) + HRV_MAX_GAP + dt.timedelta(seconds=1)
    replies = stream(client, after, 15)
    assert [reply["hrv"] is not None for reply in replies] == [False] * 14 + [True]


def test_without_skin_contact_the_pulse_loses_confidence_and_no_hrv_is_built(
    client: TestClient,
) -> None:
    stream(client, START, 14)
    # Contacto soportado y NO detectado.
    reply = send(client, START + dt.timedelta(seconds=14), flags=0b0001_0100)
    assert reply["frame"]["sensor_contact"] == "not_detected"
    assert reply["hrv"] is None

    stored = client.get(
        "/api/observations", params={"key": "heart-rate", "subject": SUBJECT, "limit": 1}
    ).json()["observations"][0]
    confidence = [
        item for item in stored.get("extension", []) if "confidence" in item.get("url", "")
    ]
    assert confidence and confidence[0]["valueDecimal"] == NO_CONTACT_CONFIDENCE

    # La ventana se vacio: hacen falta otros 15 tramas con contacto para la HRV.
    replies = stream(client, START + dt.timedelta(seconds=15), 15)
    assert [reply["hrv"] is not None for reply in replies] == [False] * 14 + [True]
