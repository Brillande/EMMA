"""Spike: SSCweb (Satellite Situation Center, NASA Goddard) — posición de la ISS.

Objetivo: confirmar que el servicio REST es público y sin clave, la forma real de la respuesta de
`/locations` para la ISS en coordenadas geográficas (latitud, longitud, altura), sus límites y sus
errores. Con eso se decide si la nave está sobre la Anomalía del Atlántico Sur.

Ejecutar:  python backend/spikes/spike_sscweb.py
"""

import datetime as dt
import json
import urllib.error
import urllib.request

BASE = "https://sscweb.gsfc.nasa.gov/WS/sscr/2"
TIMEOUT = 60
HEADERS = {"Accept": "application/json", "User-Agent": "spike-client/0.1"}


def get(path: str) -> tuple[int, str, dict[str, str]]:
    req = urllib.request.Request(f"{BASE}{path}", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:800], dict(exc.headers)


def show(title: str, path: str, limit: int = 1500) -> str:
    print(f"\n[{title}] GET {path}")
    status, body, headers = get(path)
    print(f"    status={status} bytes={len(body)} content-type={headers.get('Content-Type')}")
    print(f"    {body[:limit]}")
    return body


def main() -> None:
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    start = (now - dt.timedelta(minutes=10)).strftime("%Y%m%dT%H%M%SZ")
    end = now.strftime("%Y%m%dT%H%M%SZ")

    body = show("observatorios", "/observatories", limit=300)
    try:
        obs = json.loads(body)
        for item in obs.get("Observatory", [None, []])[1]:
            if item.get("Id") == "iss":
                print(f"    ISS: {json.dumps(item)}")
    except (ValueError, AttributeError, IndexError, TypeError) as exc:
        print(f"    no se pudo leer la lista: {exc}")

    show("ISS geo, 10 min", f"/locations/iss/{start},{end}/geo/", limit=4000)
    show("observatorio inexistente", f"/locations/nosuchsat/{start},{end}/geo/", limit=600)
    show("tiempo mal formado", "/locations/iss/ayer,hoy/geo/", limit=600)
    future = (now + dt.timedelta(days=60)).strftime("%Y%m%dT%H%M%SZ")
    future_end = (now + dt.timedelta(days=60, minutes=5)).strftime("%Y%m%dT%H%M%SZ")
    show("ISS dentro de 60 días", f"/locations/iss/{future},{future_end}/geo/", limit=1200)


if __name__ == "__main__":
    main()
