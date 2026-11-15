"""Descarga los núcleos SPICE mínimos (NAIF, JPL) para calcular el retardo sin red.

    .venv/Scripts/python.exe scripts/fetch_spice_kernels.py            # baja lo que falte
    .venv/Scripts/python.exe scripts/fetch_spice_kernels.py --check    # solo comprueba lo que hay

Por qué existe: `app/environment/spice.py` calcula en local el tiempo de luz y la elongación solar
de los días sin efeméride de JPL Horizons en caché, y para eso necesita dos ficheros públicos de
NAIF (`spice.KERNELS`: el de segundos intercalares y un SPK planetario). Este guion los deja en
`data/spice/` (junto a `data/cache`, fuera de git) y comprueba que son los fijados: tamaño, SHA-256
fijado por EMMA y, si NAIF la publica, su MD5. Un fichero que no pasa la comprobación no se
guarda: queda el que hubiera.

Sale por la puerta de salida (`app/core/egress.py`, propósito `spice-kernels`, host
`naif.jpl.nasa.gov`): lista blanca, modo sin red, freno HALT y el control de borde de Polaris
sobre lo que sale. La petición es la URL pública del fichero y nada más: ni la tripulación, ni
la misión, ni quién la pide (User-Agent genérico de httpx). Con `EMMA_OFFLINE=true` se niega y lo
dice.

Licencia (https://naif.jpl.nasa.gov/naif/rules.html, leída el 2026-11-11): los núcleos del
servidor de NAIF «may be downloaded and used by anyone», y redistribuirlos sin modificar está
permitido. El instalador de escritorio los lleva (decisión del usuario, 2026-11-11): si faltan,
`packaging/freeze.py` llama a este guion antes de congelar, y solo empaqueta lo que verifica.

Códigos de salida: 0 hecho (o nada que hacer); 2 no se puede salir (sin red, freno HALT, red
caída); 3 con `--check`, falta alguno o no es el fijado; 4 lo descargado no es el fijado (tamaño
o huella), y no se guarda; 6 no se pudo escribir en la carpeta.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core import egress  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.environment import spice  # noqa: E402


class IntegrityError(RuntimeError):
    """Lo descargado no es el núcleo fijado."""


def download(settings: Settings, kernel: spice.Kernel, folder: Path) -> Path:
    """Baja un núcleo a `folder`, lo comprueba y solo entonces lo pone en su sitio."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / kernel.name
    handle, temporary = tempfile.mkstemp(prefix=f".{kernel.name}.", dir=folder)
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()  # noqa: S324 - la huella que publica NAIF, solo para comparar
    size = 0
    try:
        with (
            os.fdopen(handle, "wb") as out,
            egress.client(settings, spice.PURPOSE) as client,
            client.stream("GET", kernel.url) as response,
        ):
            response.raise_for_status()
            for block in response.iter_bytes(1 << 20):
                out.write(block)
                sha256.update(block)
                md5.update(block)
                size += len(block)
        if size != kernel.size:
            raise IntegrityError(f"{kernel.name}: {size} bytes, se esperaban {kernel.size}")
        if kernel.md5 is not None and md5.hexdigest() != kernel.md5:
            raise IntegrityError(f"{kernel.name}: el MD5 no es el que publica NAIF")
        if sha256.hexdigest() != kernel.sha256:
            raise IntegrityError(
                f"{kernel.name}: SHA-256 {sha256.hexdigest()}, se esperaba {kernel.sha256}"
            )
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--check", action="store_true", help="solo comprueba lo que hay: no sale nada a la red"
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    folder = spice.kernel_dir(settings)

    missing = [
        kernel for kernel in spice.KERNELS
        if spice.check_kernel(kernel, folder / kernel.name) is not None
    ]
    for kernel in spice.KERNELS:
        state = "falta o no es el fijado" if kernel in missing else "comprobado"
        print(f"{kernel.name} ({kernel.kind}): {state}")
    if not missing:
        print(f"Núcleos SPICE completos en {folder}.")
        return 0
    if args.check:
        return 3

    for kernel in missing:
        print(f"Descargando {kernel.url} ...")
        try:
            download(settings, kernel, folder)
        except egress.EgressBlocked as exc:
            print(f"No sale: {exc.reason}", file=sys.stderr)
            return 2
        except IntegrityError as exc:
            print(f"Descargado pero no es el núcleo fijado, no se guarda: {exc}", file=sys.stderr)
            return 4
        except httpx.HTTPError as exc:
            print(f"NAIF inaccesible: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        except OSError as exc:
            print(f"No se pudo escribir en {folder}: {exc}", file=sys.stderr)
            return 6
        print(f"  {kernel.name}: guardado y comprobado ({kernel.integrity_source}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
