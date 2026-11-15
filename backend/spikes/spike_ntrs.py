"""Spike: NASA Technical Reports Server (NTRS), `https://ntrs.nasa.gov/api`.

Pregunta: ¿se puede comprobar contra NTRS que un informe técnico que cita EMMA existe, con su
título, autores, año y número de documento, como se hace con un DOI contra Crossref?

Mira: la ficha de un informe por su número de NTRS, qué devuelve un número inexistente, uno mal
formado, dónde están los autores, las fechas y los números de informe, la búsqueda y si hay
límites de uso visibles. User-Agent genérico; no se manda nada del proyecto.

Ejecutar:  python backend/spikes/spike_ntrs.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "https://ntrs.nasa.gov/api"
UA = {"User-Agent": "citation-check/0.1", "Accept": "application/json"}


def get(path: str) -> tuple[int, dict[str, str], str, float]:
    request = urllib.request.Request(f"{BASE}{path}", headers=UA)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, dict(response.headers), body, time.monotonic() - start
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, dict(exc.headers), body, time.monotonic() - start


def show_record(ntrs_id: str) -> None:
    status, headers, body, took = get(f"/citations/{ntrs_id}")
    print(f"\n[{ntrs_id}] status={status} {took:.2f}s bytes={len(body)}")
    limits = {k: v for k, v in headers.items() if "rate" in k.lower() or "retry" in k.lower()}
    if limits:
        print("    cabeceras de límite:", limits)
    if status != 200:
        print("    cuerpo:", body[:300])
        return
    data = json.loads(body)
    print("    claves:", sorted(data))
    print("    title:", data.get("title"))
    print("    stiType:", data.get("stiType"), "| onlyAbstract:", data.get("onlyAbstract"))
    print("    autores:", [a["meta"]["author"]["name"] for a in data.get("authorAffiliations", [])])
    print("    reportNumbers:", data.get("reportNumbers"))
    print("    otherReportNumbers:", data.get("otherReportNumbers"))
    print("    publications:", [
        {k: p.get(k) for k in ("publicationDate", "publicationName", "doi")}
        for p in data.get("publications") or []
    ])
    print("    meetings:", [
        {k: m.get(k) for k in ("name", "startDate", "endDate")} for m in data.get("meetings") or []
    ])
    print("    distributionDate:", data.get("distributionDate"), "| created:", data.get("created"))


def main() -> None:
    # Presentación de congreso, memorando técnico con número NASA/TM, norma JSC, informe de
    # evidencia HRP y uno de 1982 (NASA-CR).
    for ntrs_id in (
        "20200000567", "20170004345", "20240007713", "20160004368", "19820015234",
        "20220017869",
    ):
        show_record(ntrs_id)
    # Un número con forma válida que no existe, y uno mal formado.
    for bad in ("20999999999", "abc"):
        status, _, body, _ = get(f"/citations/{bad}")
        print(f"\n[{bad}] status={status} cuerpo={body[:200]!r}")
    # La búsqueda por texto (por si una cita trae el título y no el número).
    status, _, body, took = get("/citations/search?q=%22Medical%20Data%20Architecture%22")
    data = json.loads(body) if status == 200 else {}
    print(f"\n[búsqueda] status={status} {took:.2f}s stats={data.get('stats')}")
    # Ráfaga corta: ¿aparece un 429?
    codes = [get("/citations/20200000567")[0] for _ in range(10)]
    print("\n[ráfaga de 10]", codes)


if __name__ == "__main__":
    main()
