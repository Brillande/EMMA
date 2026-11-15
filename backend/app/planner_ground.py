"""El resumen del planificador para Tierra, reconstruido con lo que había hasta el corte.

Por qué existe: decisión del usuario (2026-11-12): en Tierra no se ve el planificador de a bordo
(Marplanner) entero, sino lo que puede servir para apoyar la salud mental de la tripulación:
cuánto ocio hay en su calendario, sus tareas y rachas, los pasatiempos de su hoja diaria y
cuántos mensajes y recordatorios tiene cada uno. Son cifras descriptivas por persona y día. No
hay umbral, ni veredicto, ni alerta, ni entra en el análisis (invariantes 5 y 7).

Tierra solo puede saber lo que ya habría llegado: se toman los registros del ledger anotados
hasta el corte del retardo y con ellos se reconstruye la base de Marplanner, de solo lectura,
con sus propias funciones (`planner-bridge/ground-summary.mjs`, Node). Es un proceso aparte en
esta máquina, sin red: no pasa por `core/egress.py` porque no sale nada.

Qué cuenta como ocio: una lista de palabras declarada (`data/planner_leisure.json`), decisión del
usuario; se dice con esas palabras en la respuesta, para que nadie lo tome por una medida.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core import i18n

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "planner-bridge"
MARPLANNER = REPO / "marplanner"
LEISURE_PATH = Path(__file__).resolve().parent / "data" / "planner_leisure.json"
TIMEOUT_S = 120
MAX_DAYS = 31
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class SummaryUnavailable(RuntimeError):
    """No se pudo calcular el resumen: sin Node, sin la copia de Marplanner o el cálculo falló."""


def leisure_words() -> list[str]:
    data = json.loads(LEISURE_PATH.read_text(encoding="utf-8"))
    words = data.get("words")
    if not isinstance(words, list) or not all(isinstance(w, str) and w.strip() for w in words):
        raise SummaryUnavailable("planner_leisure.json: `words` tiene que ser una lista")
    return [w.strip() for w in words]


def _node() -> str:
    found = os.environ.get("EMMA_NODE") or shutil.which("node")
    if not found:
        raise SummaryUnavailable("no hay Node en esta máquina: el planificador no puede resumirse")
    return found


def _command() -> tuple[list[str], Path, dict[str, str]]:
    """Cómo se ejecuta el resumen: en el instalador, el Node de Electron con el paquete compilado
    (lo dicen `EMMA_PLANNER_BRIDGE_DIR` y `EMMA_PLANNER_RUNTIME_DIR`, que pone `desktop/main.cjs`);
    en el repositorio, el Node del sistema con tsx sobre la copia de Marplanner."""
    env = dict(os.environ)
    runtime = os.environ.get("EMMA_PLANNER_RUNTIME_DIR")
    if runtime:
        bridge = Path(os.environ.get("EMMA_PLANNER_BRIDGE_DIR", str(BRIDGE)))
        bundle = Path(runtime) / "summary-modules.js"
        if not bundle.is_file():
            raise SummaryUnavailable("falta el planificador compilado del instalador")
        env["EMMA_PLANNER_SUMMARY_BUNDLE"] = str(bundle)
        script = bridge / "ground-summary.mjs"
        command = [_node(), "--import", (bridge / "register.mjs").as_uri(), str(script)]
        return command, Path(runtime), env
    if not (MARPLANNER / "node_modules").is_dir():
        raise SummaryUnavailable("la copia de Marplanner no tiene sus dependencias instaladas")
    register = (BRIDGE / "register.mjs").as_uri()
    script = BRIDGE / "ground-summary.mjs"
    return [_node(), "--import", register, "--import", "tsx", str(script)], MARPLANNER, env


def _from_service(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """El resumen pedido al servicio local del escritorio (`planner-bridge/summary-server.mjs`).

    En el instalador `EMMA.exe` no puede hacer de Node (fusible `runAsNode` apagado a propósito):
    el resumen corre en un `utilityProcess` de Electron que escucha en loopback. Solo loopback,
    como el planificador (`planner_link.py`); no es una salida a internet.
    """
    host = urlsplit(url).hostname or ""
    if host not in LOOPBACK_HOSTS:
        raise SummaryUnavailable(f"el servicio del resumen tiene que ser local, no {host!r}")
    try:
        response = httpx.post(url, json=payload, timeout=TIMEOUT_S)
    except httpx.HTTPError as exc:
        raise SummaryUnavailable(f"el servicio del resumen no responde: {exc}") from exc
    if response.status_code != 200:
        is_json = response.headers.get("content-type", "").startswith("application/json")
        said = response.json().get("error", "") if is_json else ""
        raise SummaryUnavailable(f"el resumen del planificador falló: {str(said)[:300]}")
    result: dict[str, Any] = response.json()
    return result


def run_node(payload: dict[str, Any]) -> dict[str, Any]:
    """Ejecuta el resumen con la entrada dada. Punto de sustitución para las pruebas."""
    service = os.environ.get("EMMA_PLANNER_SUMMARY_URL")
    if service:
        return _from_service(service, payload)
    command, cwd, env = _command()
    try:
        done = subprocess.run(
            command, cwd=cwd, env=env, input=json.dumps(payload).encode("utf-8"),
            capture_output=True, timeout=TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SummaryUnavailable("el resumen del planificador tardó demasiado") from exc
    if done.returncode != 0:
        # La línea del error, no la última de la pila ni el aviso de almacenamiento de Marplanner.
        lines = done.stderr.decode("utf-8", "replace").splitlines()
        said = next(
            (ln.strip() for ln in lines if "Error" in ln and not ln.strip().startswith("at ")), ""
        )
        raise SummaryUnavailable(f"el resumen del planificador falló: {said[:300]}")
    result: dict[str, Any] = json.loads(done.stdout.decode("utf-8"))
    return result


_cache: dict[str, dict[str, Any]] = {}
_cache_lock = threading.Lock()


def summarize(
    changesets: list[dict[str, Any]], until: dt.datetime, days: int,
) -> dict[str, Any]:
    """El resumen con los changesets anotados hasta `until` (incluido). Se guarda por corte:
    los mismos registros y el mismo día dan el mismo resumen."""
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days tiene que estar entre 1 y {MAX_DAYS}")
    cut = [c for c in changesets if dt.datetime.fromisoformat(c["recorded"]) <= until]
    words = leisure_words()
    until_day = until.astimezone().date().isoformat()
    key = hashlib.sha256(
        json.dumps([[c["sha256"] for c in cut], until_day, days, words]).encode("utf-8")
    ).hexdigest()
    with _cache_lock:
        if key in _cache:
            return _served(_cache[key])
    result = run_node({
        "records": [c["changeset"] for c in cut], "until_day": until_day, "days": days,
        "leisure_words": words,
    })
    result["cut"] = until.isoformat()
    result["leisure_rule"] = (
        "Ocio: eventos del calendario cuyo título contiene alguna palabra de una lista declarada "
        "(data/planner_leisure.json); no es una medida."
    )
    with _cache_lock:
        _cache[key] = result
    return _served(result)


def _served(result: dict[str, Any]) -> dict[str, Any]:
    """El resumen en el idioma de la petición: solo cambia la frase de EMMA sobre el ocio.

    El resumen se guarda por corte y lo piden los dos idiomas: lo guardado se queda en
    castellano y el inglés se pone al entregarlo, en una copia. Lo que viene del planificador
    (títulos, tareas, pasatiempos) se sirve como está guardado.
    """
    if i18n.current() != "en":
        return result
    return {
        **result,
        "leisure_rule": (
            "Leisure: calendar events whose title contains a word from a declared list "
            "(data/planner_leisure.json); it is not a measurement."
        ),
    }
