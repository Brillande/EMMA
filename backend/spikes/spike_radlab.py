"""Spike: OSDR RadLab API — dosimetria real de radiacion.

HALLAZGO CRITICO (spike 2026-09-20): una consulta sin filtro de tiempo NI
seleccion de campos devuelve ~435 MB. El cliente de produccion DEBE acotar
siempre por rango de timestamp y pedir solo los campos necesarios.

Parametros confirmados: spacecraft, instrument, timestamp (con operadores
>=, <=), fields+= para anadir columnas, format=json|csv|tsv|html.
Formato JSON devuelto: {"columns": [...], "index": [...], "data": [[...]]}
(estilo pandas "split"), NO una lista de objetos.

Ejecutar:  python backend/spikes/spike_radlab.py
"""

import json
import urllib.error
import urllib.request

BASE = "https://visualization.osdr.nasa.gov/radlab/api"
TIMEOUT = 120
MAX_BYTES = 8 * 1024 * 1024  # corta-circuitos: no tragar respuestas gigantes


def get(query: str) -> tuple[int, str, bool]:
    """Devuelve (status, cuerpo, truncado)."""
    url = f"{BASE}/?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "EMMA-spike/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read(MAX_BYTES + 1)
            truncated = len(raw) > MAX_BYTES
            return resp.status, raw[:MAX_BYTES].decode("utf-8", errors="replace"), truncated
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:500], False


def describe(label: str, query: str) -> None:
    print(f"\n[{label}]")
    print(f"    query: {query}")
    status, body, truncated = get(query)
    print(f"    status={status}  bytes={len(body)}{'  (TRUNCADO)' if truncated else ''}")
    if status != 200:
        print(f"    cuerpo: {body[:300]}")
        return
    if truncated:
        print("    !! respuesta excede el limite: la consulta necesita mas filtros")
        return
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"    no-JSON: {body[:300]}")
        return
    if isinstance(data, dict) and "columns" in data:
        cols = data["columns"]
        rows = data.get("data", [])
        print(f"    columnas: {cols}")
        print(f"    n filas: {len(rows)}")
        for row in rows[:3]:
            print(f"    | {row}")
    else:
        print(f"    forma inesperada: {str(data)[:300]}")


def main() -> None:
    print("=" * 70)
    print("SPIKE 2: OSDR RadLab API (con filtros)")
    print("=" * 70)

    # Forma booleana: obligatoria si se usa fields+=. La API rechaza mezclar
    # el estilo clave-valor con seleccion de campos.
    describe(
        "ISS / DosTel / 1 dia / campos de dosis",
        "query=(spacecraft=ISS)AND(instrument=DosTel)"
        "AND(timestamp>=2022-04-01)AND(timestamp<=2022-04-02)"
        "&fields+=absorbed_dose_rate&fields+=dose_equivalent_rate"
        "&format=json",
    )

    # Sin fields+=, el estilo clave-valor si funciona (devuelve todas las columnas).
    describe(
        "ISS / DosTel / 1 dia / clave-valor",
        "spacecraft=ISS&instrument=DosTel"
        "&timestamp>=2022-04-01&timestamp<=2022-04-02"
        "&format=json",
    )


if __name__ == "__main__":
    main()
