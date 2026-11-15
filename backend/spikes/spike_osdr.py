"""Spike: OSDR Biodata API — confirmar formato de metadatos de estudio.

Objetivo: verificar que podemos recuperar OSD-288 (evidencia inmune) y buscar
estudios por factor de vuelo espacial, sin autenticacion.

Ejecutar:  python backend/spikes/spike_osdr.py
"""

import json
import urllib.parse
import urllib.request

BASE = "https://visualization.osdr.nasa.gov/biodata/api/v2"
TIMEOUT = 30


def get(path: str, params: dict | None = None) -> tuple[int, str]:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "EMMA-spike/0.1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def main() -> None:
    print("=" * 70)
    print("SPIKE 1: OSDR Biodata API")
    print("=" * 70)

    # 1. Metadatos del estudio OSD-288 (bazo murino, evidencia inmune)
    print("\n[1] GET /dataset/OSD-288/")
    status, body = get("/dataset/OSD-288/", {"format": "json.records"})
    print(f"    status={status}  bytes={len(body)}")
    try:
        data = json.loads(body)
        print(f"    tipo raiz: {type(data).__name__}")
        # Mostrar la forma sin volcar todo el contenido
        if isinstance(data, dict):
            print(f"    claves nivel 1: {list(data.keys())[:10]}")
            inner = data.get("OSD-288")
            if isinstance(inner, dict):
                print(f"    claves OSD-288: {list(inner.keys())[:15]}")
    except json.JSONDecodeError as exc:
        print(f"    !! no es JSON: {exc}")
        print(f"    primeros 300: {body[:300]}")

    # 2. Ensayos del estudio
    print("\n[2] GET /dataset/OSD-288/assays/")
    status, body = get("/dataset/OSD-288/assays/", {"format": "json.records"})
    print(f"    status={status}  bytes={len(body)}")
    print(f"    primeros 400: {body[:400]}")

    # 3. Query: estudios con muestras en vuelo (para la capa de evidencia)
    print("\n[3] GET /query/datasets/ (factor spaceflight=in-flight)")
    status, body = get(
        "/query/datasets/",
        {
            "study.factor value.spaceflight": "in-flight",
            "format": "csv",
        },
    )
    print(f"    status={status}  bytes={len(body)}")
    lines = body.splitlines()
    print(f"    filas: {len(lines)}")
    for line in lines[:5]:
        print(f"    | {line[:160]}")


if __name__ == "__main__":
    main()
