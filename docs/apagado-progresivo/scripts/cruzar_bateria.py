"""Cruza el CSV de `bateria.ps1` con las fases de una tanda: consumo del equipo entero por fase.

Por qué existe: la descarga de la batería se muestrea en un proceso aparte (`bateria.ps1`), y cada
plan de `medir.py` / `medir-ui.mjs` guarda sus fases con su inicio y su fin (`inicio`/`fin` o
`t0`/`t1`, en segundos Unix). Aquí se hace la media de la descarga dentro de cada fase. Las muestras
con el portátil enchufado se descartan: entonces la batería no mide nada.

Uso: python cruzar_bateria.py <bateria.csv> <tanda1.json> [<tanda2.json> ...]
Escribe al lado de cada tanda `<tanda>-bateria.json`.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def main(battery_csv: str, runs: list[str]) -> None:
    with open(battery_csv, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["enchufado"] == "0"]
    samples = [(float(r["t"]), float(r["descarga_w"])) for r in rows]
    for run in runs:
        data = json.loads(Path(run).read_text(encoding="utf-8"))
        out = []
        for phase in data["fases"]:
            t0 = phase.get("inicio", phase.get("t0"))
            t1 = phase.get("fin", phase.get("t1"))
            if t0 is None or t1 is None:
                continue
            inside = [w for t, w in samples if t0 <= t <= t1]
            out.append({"fase": phase["fase"], "duracion_s": round(t1 - t0, 2), "muestras": len(inside),
                        "equipo_w_media": round(sum(inside) / len(inside), 2) if inside else None,
                        "equipo_julios": round(sum(inside) / len(inside) * (t1 - t0), 1) if inside else None})
        target = Path(run).with_name(Path(run).stem + "-bateria.json")
        target.write_text(json.dumps({"fuente": Path(battery_csv).name, "fases": out}, ensure_ascii=False,
                                     indent=1), encoding="utf-8")
        print(target.name)
        for o in out:
            print("  ", o)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
