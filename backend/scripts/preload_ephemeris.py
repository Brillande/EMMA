"""Precarga las efemérides de JPL Horizons de toda la misión, para operar sin red.

    .venv/Scripts/python.exe scripts/preload_ephemeris.py            # precarga lo que falte
    .venv/Scripts/python.exe scripts/preload_ephemeris.py --check    # solo dice qué falta

Por qué existe: sin red (`EMMA_OFFLINE=true`, el modo nominal de misión) el retardo con Tierra y
la conjunción solar de un día salen de la efeméride de ese día en caché, y la consulta diaria
pedía a Horizons un día cada vez, el día que hacía falta. Un día sin red y sin caché era un día
con el retardo «sin dato». Este guion pide a Horizons, con paso de un día y una consulta por cada
tramo seguido que falte, los días del lanzamiento (`EMMA_MISSION_START`) al fin configurado
(`EMMA_MISSION_DAYS` después) que aún no estén en caché, y los escribe en la misma caché
(`data/cache/ephemeris`) con la misma clave y el mismo formato que la consulta diaria, que los
aprovecha sin cambios (`EphemerisClient.preload`).

Sale por la puerta de salida (`app/core/egress.py`): lista blanca por propósito (`ephemeris`),
modo sin red y freno HALT. Con `EMMA_OFFLINE=true` se niega y lo dice. El modo seguro es un
asiento firmado en el ledger del proceso que sirve la consola, que vive en memoria: este guion,
en su propio proceso, no lo ve. Con la consola en marcha, la misma precarga se pide con
`POST /api/comms/preload` (con la cabecera `X-EMMA-Console: 1`, `app/api/console_header.py`),
que sí lo respeta. Este guion no llama a la API: precarga con `EphemerisClient` en su proceso.

Con SPICE primero (decisión del usuario, 2026-11-11, `app/environment/spice.py`): si el cálculo
local cubre todos los días de la misión, esta precarga ya no hace falta para el retardo sin red, y
el guion lo dice (`preload_role` de la cobertura). No se quita: lo precargado es el contraste de
SPICE en cada consulta (la consulta diaria no pide nada en vivo para contrastar) y el respaldo si
SPICE faltara.

Meter la caché precargada en el instalador no se hace aquí: es decisión del usuario.

Códigos de salida: 0 hecho (o nada que hacer); 1 Horizons respondió algo inservible; 2 no se
puede salir (sin red, freno HALT o red caída); 3 con `--check`, faltan días; 4 Horizons no
devolvió todos los días que faltaban (los que llegaron quedan escritos); 5 la configuración no
deja ningún día de misión (`EMMA_MISSION_DAYS` negativo); 6 no se pudo escribir en la caché
(disco lleno, sin permiso; lo escrito antes del fallo queda, entero).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.cache import OfflineDataUnavailable  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.environment import ephemeris_coverage  # noqa: E402
from app.environment.ephemeris import EphemerisCacheWriteError, EphemerisClient  # noqa: E402
from app.evidence import mission_profiles  # noqa: E402


def _report(coverage: dict[str, Any]) -> None:
    print(coverage["text"])
    if coverage.get("preload_role"):
        print(coverage["preload_role"])
    for gap in coverage["missing"]:
        print(f"  falta: {gap['start']} a {gap['end']} ({gap['days']} d)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--check", action="store_true", help="solo mira la caché: no sale nada a la red"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    # El objetivo lo decide el perfil (2026-11-11). Este proceso no ve los cambios de perfil
    # firmados en la consola (su ledger vive en memoria en el proceso que la sirve): usa el de la
    # configuración, y lo dice. Con la consola en marcha, `POST /api/comms/preload` usa el vigente.
    chosen = mission_profiles.ephemeris_target(settings.mission_profile, settings)
    if chosen.configured_ignored:
        print(
            f"EMMA_TARGET_BODY={chosen.configured} no se usa: el objetivo lo decide el perfil.",
            file=sys.stderr,
        )
    target = chosen.target
    if target is None:
        print(
            f"El perfil configurado ({settings.mission_profile!r}) no tiene objetivo de "
            "efemérides: el retardo no se calcula y no hay nada que precargar. Si a bordo se "
            "firmó otro perfil, precarga desde la consola (POST /api/comms/preload)."
        )
        return 0
    start, end = ephemeris_coverage.mission_span(settings)
    client = EphemerisClient(settings=settings)
    print(
        f"misión: {start} a {end} · perfil {settings.mission_profile} (de la configuración) · "
        f"objetivo {target} · observador {settings.observer_body} · caché {client.cache.root}"
    )
    if end < start:
        print(
            f"La configuración no deja ningún día de misión (EMMA_MISSION_DAYS="
            f"{settings.mission_days}): no se pide nada a JPL Horizons.",
            file=sys.stderr,
        )
        return 5
    if args.check:
        coverage = ephemeris_coverage.coverage(settings, client, target=target)
        _report(coverage)
        return 0 if coverage["state"] == ephemeris_coverage.COMPLETE else 3

    try:
        result = client.preload(start, end, target)
    except EphemerisCacheWriteError as exc:
        # Antes de «no se puede salir»: no es la red, es el disco, y lo escrito antes se queda.
        print(f"No se pudo guardar en la caché: {exc}", file=sys.stderr)
        _report(ephemeris_coverage.coverage(settings, client, target=target))
        return 6
    except OfflineDataUnavailable as exc:
        print(f"No se precarga: {exc}", file=sys.stderr)
        if settings.offline:
            print(
                "EMMA_OFFLINE=true: el guion no sale a la red. Quítalo solo para precargar, "
                "con red, y vuelve a ponerlo.",
                file=sys.stderr,
            )
        _report(ephemeris_coverage.coverage(settings, client, target=target))
        return 2
    except ValueError as exc:
        print(f"Horizons respondió algo inservible; la caché queda como estaba: {exc}",
              file=sys.stderr)
        return 1

    if result.requested is None:
        print("Nada que pedir: todos los días ya estaban en caché.")
    else:
        asked = "; ".join(f"{first} a {last}" for first, last in result.queries)
        how = "en una consulta" if len(result.queries) == 1 else (
            f"en {len(result.queries)} consultas, una por tramo que faltaba"
        )
        print(
            f"Pedido a Horizons {how}: {asked}; "
            f"{result.rows_received} filas recibidas, {len(result.written)} días escritos, "
            f"{result.already_cached} ya estaban."
        )
        if result.rows_unusable:
            print(
                f"{result.rows_unusable} filas sin fecha o fuera de las 00:00 UT: no se guardan "
                "bajo ningún día.",
                file=sys.stderr,
            )
    _report(ephemeris_coverage.coverage(settings, client, target=target))
    if result.not_received:
        print(
            f"Horizons no devolvió {len(result.not_received)} de los días que faltaban "
            f"({result.not_received[0]} a {result.not_received[-1]}): siguen sin efeméride.",
            file=sys.stderr,
        )
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
