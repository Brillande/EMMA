"""Spike: CCMC iSWA por HAPI — series de flujo de protones (GOES) y viento solar.

Objetivo: confirmar que el servidor HAPI público de iSWA (NASA Goddard, Community Coordinated
Modeling Center) sirve, sin clave, una serie continua de flujo de protones ≥10 MeV y del viento
solar, con qué unidades, qué valor de relleno, qué cadencia y qué errores. DONKI da eventos
sueltos; esto daría la serie entre evento y evento.

Ejecutar:  python backend/spikes/spike_iswa.py
"""

import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://iswa.gsfc.nasa.gov/IswaSystemWebApp/hapi"
TIMEOUT = 60
# User-Agent genérico: nada del proyecto ni de nadie en lo que sale.
HEADERS = {"User-Agent": "hapi-client"}


def get(endpoint: str, params: dict[str, str]) -> tuple[int, str]:
    url = f"{BASE}/{endpoint}?{urllib.parse.urlencode(params)}" if params else f"{BASE}/{endpoint}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:500]


def show(title: str, endpoint: str, params: dict[str, str], limit: int = 600) -> str:
    status, body = get(endpoint, params)
    print(f"\n[{title}] {endpoint} {params}")
    print(f"    status={status}  bytes={len(body)}")
    print(f"    {body[:limit]}")
    return body


def main() -> None:
    print("=" * 70)
    print("SPIKE: CCMC iSWA HAPI")
    print("=" * 70)
    show("capacidades", "capabilities", {})

    status, body = get("catalog", {})
    catalog = json.loads(body)["catalog"]
    print(f"\n[catálogo] status={status} conjuntos={len(catalog)}")
    for entry in catalog:
        text = f"{entry['id']} {entry.get('title', '')}".lower()
        if any(word in text for word in ("goes", "proton", "plasma", "solar wind")):
            print(f"    {entry['id']}: {entry.get('title')}")

    for dataset in ("goesp_part_flux_P5M", "swpc_rtsw_plasma_P1M"):
        info = json.loads(get("info", {"id": dataset})[1])
        print(f"\n[info {dataset}] {info['startDate']} -> {info['stopDate']}")
        for parameter in info["parameters"]:
            print(f"    {parameter['name']}: {parameter.get('units')} fill={parameter.get('fill')}")

    now = dt.datetime.now(dt.UTC).replace(microsecond=0, second=0)
    window = {
        "time.min": (now - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "time.max": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    show("protones ≥10 MeV, JSON", "data",
         {"id": "goesp_part_flux_P5M", "parameters": "P10,satelliteProton", "format": "json",
          **window})
    show("protones ≥10 MeV, CSV (por defecto)", "data",
         {"id": "goesp_part_flux_P5M", "parameters": "P10", **window}, limit=200)
    show("viento solar, JSON", "data",
         {"id": "swpc_rtsw_plasma_P1M", "format": "json", **window})

    # Un evento conocido (SPE de mayo de 2024, el de las auroras): ¿pasa de 10 pfu?
    body = show("SPE 2024-05-11", "data",
                {"id": "goesp_part_flux_P5M", "parameters": "P10", "format": "json",
                 "time.min": "2024-05-11T00:00:00Z", "time.max": "2024-05-12T00:00:00Z"},
                limit=200)
    values = [row[1] for row in json.loads(body).get("data", []) if row[1] is not None]
    print(f"    máximo P10 del día: {max(values) if values else 'sin datos'}")

    # Errores
    show("id desconocido", "data", {"id": "no_existe", **window})
    show("parámetro desconocido", "data",
         {"id": "goesp_part_flux_P5M", "parameters": "P999", **window})
    show("fecha mal formada", "data",
         {"id": "goesp_part_flux_P5M", "time.min": "ayer", "time.max": window["time.max"]})
    show("ventana vacía (min > max)", "data",
         {"id": "goesp_part_flux_P5M", "time.min": window["time.max"],
          "time.max": window["time.min"]})
    show("ventana posterior al stopDate", "data",
         {"id": "goesp_part_flux_P5M", "parameters": "P10", "format": "json",
          "time.min": "2030-01-01T00:00:00Z", "time.max": "2030-01-02T00:00:00Z"})


if __name__ == "__main__":
    main()
