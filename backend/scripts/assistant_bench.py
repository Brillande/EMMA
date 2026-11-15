"""Mide cuánto entiende el asistente con frases naturales, contra un backend vivo.

    .venv/Scripts/python.exe scripts/assistant_bench.py [--url http://127.0.0.1:8231]
        [--file tests/data/assistant_nl_eval.json] [--tag eval] [--load] [--json salida.json]

Por qué existe: «la IA no entiende la aplicación» (el usuario, 2026-11-04) no se arregla a ojo.
Esta batería dice, frase a frase, qué intención y qué argumentos salieron, de dónde salió la
respuesta y cuánto tardó, y al final el acierto y la mediana de latencia: así se compara un
cambio de prompt, de modelo o de enrutado con el anterior, sobre las mismas frases.

Un caso acierta si la intención es la esperada y lleva al menos los argumentos esperados con ese
valor (o casa con una de las alternativas de `accept`), y, si dice `reply_has`, la respuesta
contiene alguna de esas cadenas. `strict` cuenta solo la intención esperada, sin alternativas ni
argumentos: es lo que medía la batería de 32 frases de antes del cambio.

Con `--load` primero carga el escenario de la batería (`POST /api/simulate?replace=true`), que
REEMPLAZA el almacén de ese backend: úsese solo contra uno propio, nunca contra el que esté usando
alguien. El asistente no escribe nada: la batería no deja asientos (las propuestas no se firman).

Herramienta de desarrollo: toca la red solo hacia el backend que se le diga (loopback) y no viaja
en el producto.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_FILE = BACKEND / "tests" / "data" / "assistant_nl_eval.json"
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def _post(url: str, body: dict[str, Any] | None, timeout: float = 600.0) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else b""
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json", "X-EMMA-Console": "1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — loopback
        return json.load(response)


def _matches(out: dict[str, Any], want: dict[str, Any]) -> bool:
    if out.get("intent") != want.get("intent"):
        return False
    got = out.get("args") or {}
    if any(got.get(key) != value for key, value in (want.get("args") or {}).items()):
        return False
    needles = want.get("reply_has")
    return not needles or any(needle in str(out.get("reply", "")) for needle in needles)


def judge(case: dict[str, Any], out: dict[str, Any]) -> tuple[bool, bool]:
    """(acierto completo, acierto estricto de la intención)."""
    main = {"intent": case["intent"], "args": case.get("args"), "reply_has": case.get("reply_has")}
    full = _matches(out, main) or any(
        _matches(out, {"reply_has": case.get("reply_has"), **alt})
        for alt in case.get("accept", [])
    )
    return full, out.get("intent") == case["intent"]


def run(url: str, cases: list[dict[str, Any]], subject: str) -> list[dict[str, Any]]:
    results = []
    for case in cases:
        body = {
            "text": case["say"], "console": case.get("console", "crew"), "subject": subject,
            "history": case.get("history", []), "operator": "CMO",
        }
        if "modes" in case:
            body["modes"] = case["modes"]
        start = time.perf_counter()
        try:
            out = _post(f"{url}/api/assistant/turn", body)
        except urllib.error.HTTPError as exc:
            # Un backend de antes de los modos (2026-11-04) no los admite: se pregunta sin ellos,
            # que es lo que habría recibido de su consola.
            if exc.code != 422 or "modes" not in body:
                raise
            body.pop("modes")
            start = time.perf_counter()
            out = _post(f"{url}/api/assistant/turn", body)
        seconds = time.perf_counter() - start
        full, strict = judge(case, out)
        results.append({"case": case, "out": out, "seconds": seconds, "ok": full,
                        "strict": strict})
        args = json.dumps(out.get("args"), ensure_ascii=False)
        print(f"{'OK' if full else 'XX'} {seconds:5.1f}s [{case.get('tag', '')}] "
              f"«{case['say']}» -> {out.get('intent')} {args} [{out.get('reply_source')}] "
              f"{str(out.get('reply'))[:90]}", flush=True)
    return results


def report(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    tags = sorted({str(item["case"].get("tag", "")) for item in results})
    for tag in [*tags, "all"]:
        part = [item for item in results if tag == "all" or item["case"].get("tag") == tag]
        if not part:
            continue
        seconds = [item["seconds"] for item in part]
        summary[tag] = {
            "cases": len(part),
            "ok": sum(item["ok"] for item in part),
            "strict": sum(item["strict"] for item in part),
            "median_s": round(statistics.median(seconds), 2),
            "p90_s": round(sorted(seconds)[int(0.9 * (len(seconds) - 1))], 2),
            "model_turns": sum(1 for item in part if item["out"].get("checks", {}).get("schema")),
        }
        row = summary[tag]
        print(f"== {tag}: {row['ok']}/{row['cases']} ({100 * row['ok'] / row['cases']:.0f} %), "
              f"estricto {row['strict']}/{row['cases']}, mediana {row['median_s']} s, "
              f"p90 {row['p90_s']} s, con modelo {row['model_turns']}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default="http://127.0.0.1:8231")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--tag", action="append", help="solo los casos con esta etiqueta")
    parser.add_argument("--load", action="store_true",
                        help="carga antes el escenario (REEMPLAZA el almacén de ese backend)")
    parser.add_argument("--json", type=Path, help="guarda aquí los resultados")
    args = parser.parse_args(argv)
    if urlparse(args.url).hostname not in LOOPBACK:
        parser.error("la batería solo se corre contra un backend local (loopback)")
    battery = json.loads(args.file.read_text(encoding="utf-8"))
    cases = [case for case in battery["cases"] if not args.tag or case.get("tag") in args.tag]
    if args.load:
        _post(f"{args.url}/api/simulate?scenario={battery['scenario']}&replace=true", None)
    results = run(args.url, cases, battery["subject"])
    summary = report(results)
    if args.json:
        args.json.write_text(json.dumps({"summary": summary, "results": results},
                                        ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
