"""Descarga una instantánea fechada de NASA DONKI (SEP) para la demo sin red.

    .venv/Scripts/python.exe scripts/fetch_donki_snapshot.py            # descarga y escribe
    .venv/Scripts/python.exe scripts/fetch_donki_snapshot.py --check    # solo dice qué hay

Por qué existe: el instalador de escritorio arranca con la caché vacía y, con `EMMA_OFFLINE=true`
(el modo nominal de misión), sin caché no hay meteorología espacial: la consola decía «sin datos
de NASA DONKI» y el evento solar no se veía en ninguna demo sin red. Este guion pide a DONKI los
eventos de partículas solares (SEP) del último año —la misma ventana que piden el estado y
`/api/space-weather`— y escribe la respuesta **tal cual llegó**, con la URL de la consulta (sin la
clave), la fecha de descarga y la licencia, en `backend/app/data/donki_snapshot.json`, que viaja en
el paquete. `DonkiClient` la usa solo sin red y sin caché, y la declara como instantánea con su
fecha: nunca como dato en vivo (`app/environment/donki.py`).

Sale por la puerta de salida (`app/core/egress.py`, propósito `space-weather`, el mismo que la
aplicación), con la clave de `EMMA_NASA_API_KEY`: la `DEMO_KEY` se agota pronto (10 peticiones y
horas de espera), así que conviene una clave propia. Con `EMMA_OFFLINE=true` se niega y lo dice.
Las pruebas no lo ejecutan: leen el fichero ya escrito.

Códigos de salida: 0 hecho; 1 DONKI respondió algo inservible; 2 no se puede salir (sin red,
freno HALT o red caída); 3 con `--check`, no hay instantánea.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import egress  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.environment import donki  # noqa: E402

LOOKBACK_DAYS = 365


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--check", action="store_true", help="solo lee la instantánea: no sale nada a la red"
    )
    args = parser.parse_args(argv)

    if args.check:
        snapshot = donki.load_snapshot(donki.SNAPSHOT)
        if snapshot is None:
            print(f"sin instantánea en {donki.SNAPSHOT}")
            return 3
        print(f"{snapshot.label}: {len(snapshot.raw)} SEP de {snapshot.start} a {snapshot.end}")
        return 0

    settings = get_settings()
    end = dt.date.today()
    start = end - dt.timedelta(days=LOOKBACK_DAYS)
    url = f"{donki.BASE_URL}/{donki.EventType.SEP}"
    params = {"startDate": start.isoformat(), "endDate": end.isoformat()}
    try:
        # Por tramos de 60 días, que es lo que DONKI acepta (`donki.fetch_raw`). La clave va en
        # cada petición y nunca al fichero.
        payload = donki.fetch_raw(settings, donki.EventType.SEP, start, end)
    except egress.EgressBlocked as exc:
        print(f"no se puede salir: {exc}", file=sys.stderr)
        return 2
    except httpx.DecodingError as exc:
        print(f"DONKI no devolvió una lista de eventos: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        # Sin la URL: lleva la clave.
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        print(f"DONKI inaccesible: {type(exc).__name__} {status or ''}".rstrip(), file=sys.stderr)
        return 2
    # Antes de escribir: que cada evento se pueda normalizar como lo hará el cliente.
    try:
        for item in payload:
            donki.normalize(donki.EventType.SEP, item)
    except (KeyError, TypeError, ValueError) as exc:
        print(f"DONKI devolvió un evento inservible: {exc!r}", file=sys.stderr)
        return 1

    body = {
        "event_type": str(donki.EventType.SEP),
        # La consulta sin la clave: con ella se puede repetir y comparar.
        "source_url": f"{url}?startDate={params['startDate']}&endDate={params['endDate']}",
        "retrieved_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "window": params,
        "licence": donki.SNAPSHOT_LICENCE,
        "raw": payload,
    }
    donki.SNAPSHOT.write_text(
        json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"{len(payload)} SEP de {start} a {end} escritos en {donki.SNAPSHOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
