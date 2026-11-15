"""Spike: NASA DONKI — eventos de particulas energeticas solares (SPE).

Objetivo: confirmar formato de los eventos que disparan la alerta de refugio
por radiacion. Usa DEMO_KEY; en produccion, api_key propia de api.nasa.gov.

Ejecutar:  python backend/spikes/spike_donki.py
"""

import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.nasa.gov/DONKI"
API_KEY = "DEMO_KEY"  # spike: sustituir por clave propia en produccion
TIMEOUT = 60


def get(endpoint: str, params: dict) -> tuple[int, str]:
    params = {**params, "api_key": API_KEY}
    url = f"{BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "EMMA-spike/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:500]


def probe(endpoint: str, start: dt.date, end: dt.date) -> None:
    print(f"\n[{endpoint}] {start} -> {end}")
    status, body = get(
        endpoint, {"startDate": start.isoformat(), "endDate": end.isoformat()}
    )
    print(f"    status={status}  bytes={len(body)}")
    if status != 200:
        print(f"    cuerpo: {body[:300]}")
        return
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"    no-JSON: {body[:300]}")
        return
    print(f"    n eventos: {len(data) if isinstance(data, list) else 'n/a'}")
    if isinstance(data, list) and data:
        print(f"    claves: {list(data[0].keys())}")
        print(f"    muestra: {json.dumps(data[0])[:500]}")


def main() -> None:
    print("=" * 70)
    print("SPIKE 3: NASA DONKI (space weather)")
    print("=" * 70)

    today = dt.date.today()
    # Ventana amplia: los SPE son raros, 30 dias puede no traer ninguno.
    probe("SEP", today - dt.timedelta(days=365), today)
    probe("FLR", today - dt.timedelta(days=60), today)
    probe("CME", today - dt.timedelta(days=30), today)


if __name__ == "__main__":
    main()
