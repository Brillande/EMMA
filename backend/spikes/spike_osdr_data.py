"""Spike: API de datos de OSDR — leer por API la ficha de los estudios que EMMA cita.

Continúa `spike_osdr.py` (que solo confirmó la forma de `/dataset/OSD-288/`). Aquí se mira, para
cada estudio de OSDR del registro de evidencia (`app/data/evidence_refs.json`), lo que la API dice
de él: título, organismo, misión, tipo de ensayo, número de muestras y fecha de publicación; y
qué pasa con un estudio que no existe y con una ruta mal formada.

Ejecutar:  .venv/Scripts/python.exe spikes/spike_osdr_data.py
Sale a la red: no es una prueba y no corre en la suite.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request

BASE = "https://visualization.osdr.nasa.gov/biodata/api/v2"
TIMEOUT = 30
# User-Agent genérico: nada del proyecto ni de nadie en la petición.
HEADERS = {"User-Agent": "python-httpx"}
STUDIES = ("OSD-288", "OSD-569", "OSD-343", "OSD-51", "OSD-195", "OSD-198", "OSD-353",
           "OSD-370", "OSD-942", "OSD-946")


def get(path: str) -> tuple[int, bytes, float]:
    url = f"{BASE}{path}"
    request = urllib.request.Request(url, headers=HEADERS)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read(), time.monotonic() - start
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), time.monotonic() - start


def main() -> None:
    for accession in STUDIES:
        status, body, took = get(f"/dataset/{accession}/?format=json")
        meta = json.loads(body)[accession]["metadata"]
        s_status, s_body, s_took = get(f"/dataset/{accession}/samples/?format=json")
        assays = json.loads(s_body)[accession]["assays"]
        names = {name for assay in assays.values() for name in assay.get("samples", {})}
        released = meta.get("study public release date")
        print(f"\n{accession}  ({status} {len(body)} B {took:.1f}s; muestras {s_status} "
              f"{len(s_body)} B {s_took:.1f}s)")
        print(f"  título     : {meta.get('study title')!r}")
        print(f"  organismo  : {meta.get('organism')!r}")
        print(f"  misión     : {meta.get('mission')!r}")
        print(f"  programa   : {meta.get('flight program')!r} / {meta.get('project type')!r}")
        print(f"  ensayo     : {meta.get('study assay measurement type')!r} · "
              f"{meta.get('study assay technology type')!r}")
        print(f"  publicado  : {released!r} -> "
              f"{dt.datetime.fromtimestamp(released, dt.UTC).date() if released else None}")
        print(f"  ensayos    : {len(assays)}  muestras únicas: {len(names)}  "
              f"por ensayo: {[len(a.get('samples', {})) for a in assays.values()]}")

    print("\n[errores]")
    for path in ("/dataset/OSD-999999/?format=json", "/dataset/OSD-288/nada/?format=json"):
        status, body, _ = get(path)
        print(f"  {path} -> {status} {body[:200]!r}")


if __name__ == "__main__":
    main()
