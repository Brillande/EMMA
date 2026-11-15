"""Tiempo de luz y elongación solar calculados en local con SPICE (NAIF, JPL), sin red.

Por qué existe: sin red, el modo nominal de misión, el retardo con Tierra de un día sale de la
efeméride de JPL Horizons de ese día en caché, o sale «sin dato». La caché se llena con red, día
a día o con la precarga, y una misión de seis meses con solo unos días en caché enseñaba «Sin
efemérides» el resto: el riesgo dejaba de escalarse con el tiempo de luz justo cuando la nave
está lejos y sin enlace. Las efemérides planetarias de JPL (las series DE; Horizons usa DE441, y
aquí va DE432) se distribuyen como ficheros de NAIF (los «núcleos» SPK, y el de segundos
intercalares, LSK), y con ellos el cálculo se hace en el equipo, sin salir a internet. Este módulo
es ese cálculo; no sustituye a Horizons, lo deja de contraste y de respaldo:

- **Precedencia** (decisión del usuario, 2026-11-11, `EphemerisClient.comms_window`): **SPICE
  primero**. Sin red es el modo nominal de misión, y SPICE calcula la misión entera en local con
  el mismo resultado que Horizons (peor diferencia medida en el spike: 0,003 ms de tiempo de luz
  en 181 días, `spikes/HALLAZGOS.md` §10). Si SPICE puede calcular el día (instalado, núcleos
  verificados, día dentro del núcleo, objetivo y observador soportados), la ventana sale de aquí
  sin salir a la red. Horizons queda de **contraste** (`contrast`: su efeméride de ese día en
  caché, si la hay; no se pide nada en vivo para contrastar) y de **respaldo** (si SPICE no puede:
  la caché de Horizons, Horizons en vivo con red y, si nada, «sin dato»). Si el contraste
  discrepa por encima del error declarado, se dice y ese día se usa Horizons, la referencia. Lo
  que se calcula aquí NO se escribe en la caché de Horizons: cada ventana dice de dónde sale
  (`CommsWindow.source`) y las dos fuentes no se mezclan sin decirlo.
- **Qué calcula**: la distancia aparente (corregida por tiempo de luz, como el `delta` de
  Horizons), el tiempo de luz de ida (el `lighttime` de Horizons), la elongación solar
  Sol-observador-objetivo (cantidad 23 de Horizons) y su marca `/T` o `/L`, a las 00:00 UTC de
  cada día, igual que la efeméride diaria. Coincidencia con Horizons medida en el spike
  (`spikes/spike_spice.py`, `spikes/HALLAZGOS.md`) con un error máximo declarado
  (`DECLARED_MAX_ERROR`).
- **Qué no calcula**: solo el objetivo que tiene núcleo genérico mínimo (`TARGETS`, hoy Marte) y
  solo desde el geocentro (`OBSERVERS`). Marte se calcula por su baricentro (`4`), porque el SPK
  planetario pequeño no trae el centro del planeta (`499`); la diferencia (Fobos y Deimos apartan
  el centro de Marte del baricentro unas decenas de centímetros, por su masa) es despreciable
  frente al error declarado. Otro objetivo u otro observador: «SPICE no calcula este objetivo»,
  no un número.

Dependencias, opcionales las dos y dichas si faltan (como el resto de lo opcional de EMMA):

- `spiceypy` (extra `[spice]` de `pyproject.toml`; MIT, incluye CSPICE de NAIF): sin ella,
  «SPICE no instalado», y todo sigue como antes (Horizons y su caché).
- Los núcleos (`KERNELS`) en `data/spice/` (junto a `data/cache`, fuera de git), que descarga
  `scripts/fetch_spice_kernels.py` por la puerta de salida. Sin ellos, o con uno que no pasa la
  comprobación de integridad (tamaño y huella fijados aquí), «núcleos SPICE ausentes», igual.

La aplicación de escritorio lleva las dos cosas dentro (decisión del usuario, 2026-11-11): el
retardo con Tierra tiene que salir sin red desde el primer arranque, y su caché nace vacía en el
perfil del usuario. `packaging/freeze.py` congela `spiceypy` con su CSPICE y mete los núcleos,
comprobados con `check_kernel` antes de empaquetarlos, en la carpeta `spice` del paquete
(`BUNDLED_SUBDIR`). Dónde se buscan (`kernel_sources`): primero la carpeta configurada (junto a la
caché: lo que se baje o ponga a mano allí manda), después los empaquetados; se usan los de la
primera carpeta en la que pasan la comprobación los dos, y `/api/spice` dice cuál
(`kernel_origin`). Los empaquetados se comprueban igual que los otros: un paquete manipulado no
calcula.

Licencia de los núcleos (leída el 2026-11-11 en https://naif.jpl.nasa.gov/naif/rules.html,
«Kernels Distribution» y «Kernels Redistribution»): «SPICE kernels placed on the NAIF server may be
downloaded and used by anyone» y «Redistribution of SPICE kernels distributed by NAIF is permitted
as long as they have not been modified». Esa página no dice «dominio público». El instalador los
redistribuye sin modificar (la huella lo garantiza), que es lo permitido; el `NOTICE` lo declara.

Lo que NO hace: no entra en el riesgo por su cuenta. Da una `CommsWindow` como la de Horizons, y lo
que hace el retardo con el factor de aislamiento es lo de siempre (`analysis/risk.py`). El efecto
SÍ es nuevo: un día sin caché con perfil de Marte tenía factor 1 (sin retardo) y ahora tiene el
del tiempo de luz calculado. Lo dice `compliance/risk-management-file.md`. Poner SPICE primero no
cambia ninguna cifra del riesgo: el tiempo de luz es el mismo dentro del error declarado, que
queda muy por debajo de lo que mueve el factor de aislamiento; y la validación externa (MMASH y
deterioros inyectados) no usa retardo, así que la invariante 5 no se mueve.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib
import logging
import math
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from app.core import i18n
from app.core.cache import OfflineDataUnavailable
from app.core.config import Settings
from app.environment.ephemeris import (
    LIGHT_SECONDS_PER_AU,
    CommsWindow,
    Contrast,
    checked_elongation,
    servable,
)

_log = logging.getLogger(__name__)

PRECEDENCE = (
    "SPICE primero: si el cálculo local puede calcular el día, el retardo sale de él, sin red. "
    "JPL Horizons queda de contraste (su efeméride de ese día en caché, si la hay; no se pide "
    "nada en vivo para contrastar) y de respaldo (si SPICE no calcula el día: la caché de "
    "Horizons, después Horizons en vivo con red, y si no, sin dato). Si el contraste discrepa por "
    "encima del error declarado, se dice y ese día se usa Horizons, la referencia. Cada ventana "
    "dice de cuál sale, y lo calculado con SPICE no se guarda en la caché de Horizons."
)
# Qué se hace con el contraste, dicho igual en `/api/spice` y en la cobertura.
CONTRAST_POLICY = (
    "El cálculo local se contrasta con la efeméride de JPL Horizons del mismo día cuando está en "
    "caché (la precarga la llena). Si la diferencia supera el error declarado en el tiempo de "
    "luz o en la elongación, la ventana lo dice (contrast.agrees = false) y ese día se usa "
    "Horizons. Sin esa entrada en caché no hay contraste (contrast = null): no se pide a "
    "Horizons en vivo solo para contrastar."
)
i18n.en_many({
    PRECEDENCE: (
        "SPICE first: if the local computation can compute the day, the delay comes from it, "
        "offline. JPL Horizons remains as a cross-check (its ephemeris for that day in the "
        "cache, if there is one; nothing is requested live to cross-check) and as a fallback "
        "(if SPICE does not compute the day: the Horizons cache, then Horizons live with "
        "network access, and otherwise no data). If the cross-check disagrees above the "
        "declared error, it is stated and on that day Horizons, the reference, is used. Each "
        "window says which one it comes from, and what is computed with SPICE is not stored in "
        "the Horizons cache."
    ),
    CONTRAST_POLICY: (
        "The local computation is cross-checked against the JPL Horizons ephemeris of the same "
        "day when it is in the cache (the preload fills it). If the difference exceeds the "
        "declared error in light time or in elongation, the window says so (contrast.agrees = "
        "false) and on that day Horizons is used. Without that cache entry there is no "
        "cross-check (contrast = null): Horizons is not queried live only to cross-check."
    ),
})

# Propósito de la puerta de salida para descargar los núcleos (`core/egress.py`). Solo lo usa el
# guion de descarga: la aplicación calcula sin red.
PURPOSE = "spice-kernels"
NAIF_HOST = "naif.jpl.nasa.gov"
RULES_URL = "https://naif.jpl.nasa.gov/naif/rules.html"
RULES_READ_ON = "2026-11-11"
RULES_QUOTES = (
    "SPICE kernels placed on the NAIF server may be downloaded and used by anyone",
    "Redistribution of SPICE kernels distributed by NAIF is permitted as long as they have not "
    "been modified.",
)

# Unidad astronómica en km (IAU 2012), la misma que usa Horizons: con ella y
# `LIGHT_SECONDS_PER_AU`, la distancia en UA y el tiempo de luz son los de la tabla de Horizons.
AU_KM = 149_597_870.7

# El error máximo que se declara frente a Horizons, medido en el spike con margen (la diferencia
# medida está en `spikes/HALLAZGOS.md`): tiempo de luz de ida en segundos y elongación en grados.
DECLARED_MAX_ERROR = {"one_way_seconds": 0.1, "elongation_deg": 0.01}


@dataclass(frozen=True, slots=True)
class Kernel:
    """Un núcleo genérico de NAIF: de dónde se baja y cómo se comprueba que es ese.

    `md5` es la huella que publica NAIF (`aa_checksums.txt` de su carpeta), si la publica; `sha256`
    y `size` los fijó EMMA al descargarlo el 2026-11-11 (`fetch_spice_kernels.py`). Un fichero con
    otro tamaño u otra huella no se carga: no es el núcleo que se validó contra Horizons.
    """

    name: str
    url: str
    kind: str
    size: int
    sha256: str
    md5: str | None
    integrity_source: str
    covers: str


# Los dos núcleos mínimos, elegidos en el spike (`spikes/HALLAZGOS.md`):
# - LSK `naif0012.tls`: los segundos intercalares, para pasar de UTC a la escala de tiempo de las
#   efemérides (TDB). NAIF no publica huella de los LSK: se fija la del día de la descarga.
# - SPK `de432s.bsp`: el más pequeño de los planetarios genéricos de NAIF (10,4 MB) que cubre la
#   misión (1950-2050). `de440s`/`de442s` cubren 1849-2150 pero pesan 31 MB. La diferencia con
#   Horizons (que usa DE441) se midió en el spike: ≤ 3 µs de tiempo de luz en toda la misión.
KERNELS: tuple[Kernel, ...] = (
    Kernel(
        name="naif0012.tls",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls",
        kind="LSK",
        size=5257,
        sha256="678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b",
        md5=None,
        integrity_source=(
            "NAIF no publica huella de los LSK: tamaño y SHA-256 fijados por EMMA al descargarlo "
            "el 2026-11-11"
        ),
        covers="segundos intercalares hasta el de 2017-01-01 (el último anunciado)",
    ),
    Kernel(
        name="de432s.bsp",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de432s.bsp",
        kind="SPK",
        size=10_895_360,
        sha256="363f32e14f5255359ac32c4d38080cf28ab55564a5e16696a75f63394b666e9b",
        md5="d66c2153188958472fec67016b4b4e7a",
        integrity_source=(
            "MD5 publicado por NAIF en spk/planets/aa_checksums.txt; tamaño y SHA-256 fijados por "
            "EMMA al descargarlo el 2026-11-11"
        ),
        covers="1950-2050: baricentros planetarios, Sol, Tierra y Luna",
    ),
)


def spk_name() -> str:
    """El nombre del SPK planetario de `KERNELS` (el que firma lo calculado)."""
    return next(kernel.name for kernel in KERNELS if kernel.kind == "SPK")


i18n.en_many({
    KERNELS[0].integrity_source: (
        "NAIF does not publish a checksum for the LSKs: size and SHA-256 pinned by EMMA when "
        "downloading it on 2026-11-11"
    ),
    KERNELS[0].covers: "leap seconds up to that of 2017-01-01 (the last one announced)",
    KERNELS[1].integrity_source: (
        "MD5 published by NAIF in spk/planets/aa_checksums.txt; size and SHA-256 pinned by "
        "EMMA when downloading it on 2026-11-11"
    ),
    KERNELS[1].covers: "1950-2050: planetary barycentres, Sun, Earth and Moon",
})

# Objetivo de Horizons -> cuerpo de SPICE que se calcula, y lo que se aproxima al hacerlo.
TARGETS: dict[str, tuple[str, str]] = {
    "499": (
        "4",
        "Marte por su baricentro (el SPK planetario pequeño no trae el centro del planeta, 499): "
        "la diferencia es de decenas de centímetros, despreciable frente al error declarado",
    ),
}
# Observador de Horizons -> observador de SPICE. Solo el geocentro: uno topocéntrico pediría la
# orientación de la Tierra y la estación, que estos núcleos no traen.
OBSERVERS: dict[str, str] = {"500@399": "399"}
FRAME = "J2000"

# CSPICE tiene un único almacén de núcleos por proceso y no es seguro con varios hilos; las dos
# consolas piden `/api/status` a la vez. Todo lo que toca SPICE va con este cerrojo.
_LOCK = threading.Lock()
# Qué núcleos hay cargados, con su versión de fichero (fecha y tamaño), y si cada fichero pasó la
# comprobación de integridad en esa versión: comprobar la huella de 10 MB una vez, no por día.
_loaded: tuple[tuple[str, int, int], ...] | None = None
_verified: dict[str, tuple[tuple[int, int], bool]] = {}
_VERIFY_LOCK = threading.Lock()
# El tramo que cubre el SPK cargado, por objetivo y observador: leerlo una vez por versión.
_spans: dict[tuple[Any, ...], tuple[dt.date, dt.date] | None] = {}
# La carpeta de los núcleos si se fija a mano (las pruebas); `None`: junto a la caché.
KERNEL_DIR: Path | None = None
# La carpeta de los núcleos dentro del paquete congelado (`packaging/freeze.py` la llena).
BUNDLED_SUBDIR = "spice"
# De dónde salen los núcleos, dicho en `/api/spice` (`kernel_origin` y su texto).
ORIGINS: dict[str, str] = {
    "configured": "carpeta configurada (data/spice, junto a la caché)",
    "bundled": "núcleos empaquetados con la aplicación de escritorio",
}
i18n.en_many({
    TARGETS["499"][1]: (
        "Mars by its barycentre (the small planetary SPK does not carry the centre of the "
        "planet, 499): the difference is tens of centimetres, negligible against the declared "
        "error"
    ),
    ORIGINS["configured"]: "configured folder (data/spice, next to the cache)",
    ORIGINS["bundled"]: "kernels bundled with the desktop application",
})


class SpiceUnavailable(OfflineDataUnavailable):
    """SPICE no puede calcular este día: sin `spiceypy`, sin núcleos, u objetivo no soportado.

    Hereda de `OfflineDataUnavailable` para que el estado y `/api/comms` lo traten como la falta
    de efemérides de siempre: «sin dato», no un error del servidor.
    """


def kernel_dir(settings: Settings) -> Path:
    """Dónde están los núcleos: `data/spice`, junto a la caché (`data/cache`), fuera de git.

    No hay variable de configuración propia (`core/config.py` no se toca en este lote): sigue a
    `EMMA_CACHE_DIR`, de modo que una caché en otra carpeta tiene sus núcleos al lado.
    `KERNEL_DIR`, si no es `None`, manda: lo fija la suite de pruebas (`tests/conftest.py`) para
    que ninguna prueba dependa de los núcleos que haya bajado quien la corre.
    """
    if KERNEL_DIR is not None:
        return KERNEL_DIR
    return Path(settings.cache_dir).parent / "spice"


def bundled_kernel_dir() -> Path | None:
    """La carpeta de los núcleos empaquetados, solo en el ejecutable congelado; si no, `None`.

    PyInstaller deja los datos del paquete en `sys._MEIPASS` (`_internal/` del modo carpeta).
    Fuera del congelado no hay paquete: en el repositorio, los núcleos son los de `data/spice`.
    """
    if not getattr(sys, "frozen", False):
        return None
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(sys.executable).resolve().parent
    return root / BUNDLED_SUBDIR


def kernel_sources(settings: Settings) -> list[tuple[str, Path]]:
    """Dónde se buscan los núcleos, en orden: la carpeta configurada y, congelado, el paquete."""
    sources = [("configured", kernel_dir(settings))]
    bundled = bundled_kernel_dir()
    if bundled is not None:
        sources.append(("bundled", bundled))
    return sources


def _folder_problems(folder: Path) -> list[str]:
    """Lo que falla en los núcleos fijados de una carpeta (vacío si pasan los dos)."""
    return [
        problem for kernel in KERNELS
        if (problem := _verified_ok(kernel, folder / kernel.name)) is not None
    ]


def active_kernels(settings: Settings) -> tuple[str | None, Path, dict[str, list[str]]]:
    """La primera carpeta de `kernel_sources` con los núcleos fijados, y lo que falla en cada una.

    Devuelve el origen (`None` si ninguna vale), la carpeta (si ninguna vale, la configurada,
    que es donde se bajan) y los problemas de cada origen mirado.
    """
    problems: dict[str, list[str]] = {}
    sources = kernel_sources(settings)
    for origin, folder in sources:
        found = _folder_problems(folder)
        if not found:
            return origin, folder, problems
        problems[origin] = found
    return None, sources[0][1], problems


def source_label() -> str:
    """Cómo se firma una ventana calculada aquí: el núcleo planetario con que se calculó."""
    return f"SPICE local, núcleo {spk_name()}"


# La firma de la ventana es la misma pida quien pida (va en `CommsWindow.source` y en el asiento
# de la discrepancia); donde solo se enseña, `i18n.loc` la dice en inglés.
i18n.en(source_label(), f"local SPICE, kernel {spk_name()}")


def _spiceypy() -> ModuleType | None:
    """`spiceypy` si está instalado (extra `[spice]`), o `None`."""
    try:
        return importlib.import_module("spiceypy")
    except ImportError:
        return None


def file_digest(path: Path, algorithm: str) -> str:
    """La huella de un fichero, leída por bloques."""
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_kernel(kernel: Kernel, path: Path) -> str | None:
    """`None` si el fichero es el núcleo fijado; si no, por qué no (texto para decirlo)."""
    try:
        size = path.stat().st_size
    except OSError:
        return i18n.tr(f"falta {kernel.name}", f"{kernel.name} is missing")
    if size != kernel.size:
        return i18n.tr(
            f"{kernel.name} mide {size} bytes y el fijado {kernel.size}",
            f"{kernel.name} is {size} bytes and the pinned one {kernel.size}",
        )
    if file_digest(path, "sha256") != kernel.sha256:
        return i18n.tr(
            f"la huella SHA-256 de {kernel.name} no es la fijada",
            f"the SHA-256 checksum of {kernel.name} is not the pinned one",
        )
    if kernel.md5 is not None and file_digest(path, "md5") != kernel.md5:
        return i18n.tr(
            f"la huella MD5 de {kernel.name} no es la publicada por NAIF",
            f"the MD5 checksum of {kernel.name} is not the one published by NAIF",
        )
    return None


def _verified_ok(kernel: Kernel, path: Path) -> str | None:
    """`check_kernel`, recordado por versión de fichero: la huella se calcula una vez."""
    try:
        stat = path.stat()
    except OSError:
        _verified.pop(str(path), None)
        return i18n.tr(f"falta {kernel.name}", f"{kernel.name} is missing")
    version = (stat.st_mtime_ns, stat.st_size)
    with _VERIFY_LOCK:
        known = _verified.get(str(path))
        if known is not None and known[0] == version and known[1]:
            return None
        problem = check_kernel(kernel, path)
        _verified[str(path)] = (version, problem is None)
    return problem


@dataclass(frozen=True, slots=True)
class Availability:
    """Si SPICE puede calcular, y si no, por qué (texto para la consola)."""

    available: bool
    reason: str | None
    version: str | None
    kernels: tuple[dict[str, Any], ...]
    # De dónde salen los núcleos (`ORIGINS`), `None` si ninguna carpeta los tiene válidos, y la
    # carpeta: la de los núcleos que se usan, o la configurada si no hay ninguna válida.
    origin: str | None = None
    folder: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "spiceypy_version": self.version,
            "kernels": list(self.kernels),
            "kernel_origin": self.origin,
            "kernel_origin_label": (
                None if self.origin is None else i18n.loc(ORIGINS[self.origin])
            ),
            # Sin la ruta de la carpeta: lleva el nombre de usuario del equipo (decisión de
            # Ellande, 2026-11-11). El origen ya dice cuál es.
        }


def availability(settings: Settings) -> Availability:
    """Si hay `spiceypy` y los núcleos fijados están en una de sus carpetas. Sin red."""
    origin, folder, problems = active_kernels(settings)
    module = _spiceypy()
    rows: list[dict[str, Any]] = []
    for kernel in KERNELS:
        problem = _verified_ok(kernel, folder / kernel.name)
        rows.append({
            "name": kernel.name,
            "kind": kernel.kind,
            "covers": i18n.loc(kernel.covers),
            "url": kernel.url,
            "present": (folder / kernel.name).exists(),
            "verified": problem is None,
            "integrity": i18n.loc(kernel.integrity_source),
        })
    if module is None:
        return Availability(
            False,
            i18n.tr(
                "SPICE no instalado: falta la biblioteca spiceypy (extra [spice] del backend); el "
                "retardo sale de JPL Horizons y su caché, como antes.",
                "SPICE not installed: the spiceypy library is missing (backend extra [spice]); "
                "the delay comes from JPL Horizons and its cache, as before.",
            ),
            None, tuple(rows), origin, folder,
        )
    version = str(getattr(module, "__version__", "?"))
    if origin is None:
        configured = "; ".join(problems.get("configured", []))
        bundled = problems.get("bundled")
        packaged = (
            "" if bundled is None
            else f"; los empaquetados con la aplicación tampoco valen ({'; '.join(bundled)})"
        )
        packaged_en = (
            "" if bundled is None
            else f"; those bundled with the application are not valid either ({'; '.join(bundled)})"
        )
        return Availability(
            False,
            i18n.tr(
                "Núcleos SPICE ausentes o no válidos en la carpeta configurada "
                f"({configured}){packaged}: se descargan con "
                "backend/scripts/fetch_spice_kernels.py. "
                "El retardo sale de JPL Horizons y su caché, como antes.",
                "SPICE kernels missing or not valid in the configured folder "
                f"({configured}){packaged_en}: they are downloaded with "
                "backend/scripts/fetch_spice_kernels.py. "
                "The delay comes from JPL Horizons and its cache, as before.",
            ),
            version, tuple(rows), None, folder,
        )
    return Availability(True, None, version, tuple(rows), origin, folder)


def _ensure_loaded(sp: Any, folder: Path) -> None:
    """Carga los núcleos fijados (una vez por versión de fichero). Con el cerrojo tomado."""
    global _loaded
    wanted: list[tuple[str, int, int]] = []
    for kernel in KERNELS:
        stat = (folder / kernel.name).stat()
        wanted.append((str(folder / kernel.name), stat.st_mtime_ns, stat.st_size))
    current = tuple(wanted)
    if _loaded == current:
        return
    sp.kclear()
    _loaded = None
    for path, _, _ in current:
        sp.furnsh(path)
    _loaded = current


def _unload() -> None:
    """Descarga lo cargado (para las pruebas, que cambian de carpeta de núcleos)."""
    global _loaded
    with _LOCK:
        clear = getattr(_spiceypy(), "kclear", None)
        if callable(clear):
            clear()
        _loaded = None
        _spans.clear()
    with _VERIFY_LOCK:
        _verified.clear()


def _spice_body(settings: Settings, target: str) -> tuple[str, str]:
    """El objetivo y el observador de SPICE para los de Horizons, o `SpiceUnavailable`."""
    body = TARGETS.get(target)
    if body is None:
        raise SpiceUnavailable(
            f"SPICE no calcula el objetivo {target!r}: sus núcleos mínimos solo traen "
            f"{', '.join(sorted(TARGETS))}"
        )
    observer = OBSERVERS.get(settings.observer_body)
    if observer is None:
        raise SpiceUnavailable(
            f"SPICE no calcula desde el observador {settings.observer_body!r}: solo desde el "
            "geocentro (500@399)"
        )
    return body[0], observer


def _elongation_flag(sp: Any, et: float, target: str, observer: str) -> str:
    """`/T` si el objetivo va detrás del Sol (al este, cielo de tarde), `/L` si va delante.

    La misma marca que Horizons: se compara la ascensión recta aparente del objetivo con la del
    Sol, vistas desde el observador (al este, sale y se pone después del Sol). HALLAZGO del spike:
    con la longitud eclíptica la marca salía cambiada el 2027-02-20, cerca de la oposición
    (elongación 175,5°); con la ascensión recta en J2000 coincide con Horizons los 181 días.
    """
    sun, _ = sp.spkpos("10", et, FRAME, "LT+S", observer)
    body, _ = sp.spkpos(target, et, FRAME, "LT+S", observer)
    east = (math.atan2(body[1], body[0]) - math.atan2(sun[1], sun[0])) % (2 * math.pi)
    return "/T" if 0 < east < math.pi else "/L"


def _spice_error(exc: Exception) -> str:
    """El motivo de un error de SPICE en una línea (su `short` y su `long`, sin el recuadro)."""
    short = getattr(exc, "short", None)
    long = " ".join(str(getattr(exc, "long", "") or "").split())
    if short:
        return f"{short} {long}".strip()
    return f"{type(exc).__name__}: {' '.join(str(exc).split())}"


def compute(sp: Any, epoch: dt.date, target: str, observer: str) -> tuple[float, float, float, str]:
    """Distancia (UA), tiempo de luz de ida (min), elongación (°) y su marca a las 00:00 UTC.

    Con los núcleos ya cargados. La distancia es la aparente (corregida por tiempo de luz, `LT`),
    la del `delta` de Horizons; la elongación, entre las direcciones aparentes del Sol y del
    objetivo (`LT+S`), la de su cantidad 23.
    """
    et = sp.str2et(f"{epoch.isoformat()} 00:00:00 UTC")
    position, light_seconds = sp.spkpos(target, et, FRAME, "LT", observer)
    distance_km = math.sqrt(sum(float(value) ** 2 for value in position))
    sun, _ = sp.spkpos("10", et, FRAME, "LT+S", observer)
    apparent, _ = sp.spkpos(target, et, FRAME, "LT+S", observer)
    elongation = math.degrees(float(sp.vsep(sun, apparent)))
    return (
        distance_km / AU_KM,
        float(light_seconds) / 60.0,
        elongation,
        _elongation_flag(sp, et, target, observer),
    )


def window(settings: Settings, epoch: dt.date, target: str) -> CommsWindow:
    """La ventana de comunicación de un día calculada con SPICE, o `SpiceUnavailable`.

    Verificación cruzada, como con Horizons: el tiempo de luz que da SPICE (`spkpos`) se contrasta
    con el que sale de la distancia con la constante de EMMA; si divergen, algo no es lo que se
    validó y no se sirve. Lo que no sea una ventana servible (un número no finito) tampoco.
    """
    state = availability(settings)
    if not state.available:
        raise SpiceUnavailable(state.reason or "SPICE no disponible")
    body, observer = _spice_body(settings, target)
    sp = _spiceypy()
    assert sp is not None and state.folder is not None  # `availability` ya lo comprobó
    try:
        with _LOCK:
            _ensure_loaded(sp, state.folder)
            distance_au, minutes, elongation, flag = compute(sp, epoch, body, observer)
    except Exception as exc:  # noqa: BLE001 - SPICE lanza sus propios errores (SpiceyError…)
        # Una fecha fuera de la cobertura del núcleo, un núcleo que no carga: SPICE lo dice con
        # su excepción; aquí se dice «no calculable» con el motivo, no un error del servidor.
        raise SpiceUnavailable(f"SPICE no pudo calcular el {epoch}: {_spice_error(exc)}") from exc
    expected = distance_au * LIGHT_SECONDS_PER_AU / 60.0
    if abs(expected - minutes) * 60.0 > DECLARED_MAX_ERROR["one_way_seconds"]:
        raise SpiceUnavailable(
            f"discrepancia en el tiempo de luz de SPICE para {epoch}: {minutes:.6f} min frente "
            f"a {expected:.6f} min desde la distancia"
        )
    checked_deg, checked_flag = checked_elongation(elongation, flag)
    result = CommsWindow(
        epoch=epoch,
        distance_au=distance_au,
        one_way_minutes=minutes,
        target=target,
        solar_elongation_deg=checked_deg,
        solar_elongation_flag=checked_flag,
        source=source_label(),
    )
    if not servable(result):
        raise SpiceUnavailable(f"SPICE dio para {epoch} una distancia o un retardo no finitos")
    return result


def contrast(local: CommsWindow, reference: CommsWindow, fetched_at: dt.datetime) -> Contrast:
    """El cálculo local de un día frente a la efeméride de Horizons de ese día, con el veredicto.

    Coinciden si la diferencia del tiempo de luz de ida (en segundos) y la de la elongación (en
    grados) no superan el error declarado (`DECLARED_MAX_ERROR`). Una elongación ausente en una de
    las dos (una entrada de caché anterior a leerla) no se compara: el veredicto sale del tiempo
    de luz, que es lo que decide. Si no coinciden se usa Horizons, la referencia.
    """
    seconds = abs(local.one_way_minutes - reference.one_way_minutes) * 60.0
    elongation = (
        None if local.solar_elongation_deg is None or reference.solar_elongation_deg is None
        else abs(local.solar_elongation_deg - reference.solar_elongation_deg)
    )
    seconds_limit = DECLARED_MAX_ERROR["one_way_seconds"]
    elongation_limit = DECLARED_MAX_ERROR["elongation_deg"]
    agrees = seconds <= seconds_limit and (elongation is None or elongation <= elongation_limit)
    return Contrast(
        local=local.source,
        reference=reference.source,
        reference_fetched_at=fetched_at,
        one_way_seconds_difference=seconds,
        elongation_deg_difference=elongation,
        one_way_seconds_tolerance=seconds_limit,
        elongation_deg_tolerance=elongation_limit,
        agrees=agrees,
        used=local.source if agrees else reference.source,
    )


def coverage_span(settings: Settings, target: str) -> tuple[dt.date, dt.date] | None:
    """Del primer al último día (00:00 UTC) que el SPK cubre para el objetivo, el observador y
    el Sol; `None` si SPICE no está o no calcula ese objetivo. No sale nada a la red."""
    state = availability(settings)
    if not state.available or state.folder is None:
        return None
    try:
        body, observer = _spice_body(settings, target)
    except SpiceUnavailable:
        return None
    sp = _spiceypy()
    assert sp is not None
    spk = str(state.folder / spk_name())
    try:
        with _LOCK:
            _ensure_loaded(sp, state.folder)
            key = (_loaded, body, observer)
            if key not in _spans:
                _spans[key] = _read_span(sp, spk, (body, observer, "10"))
            return _spans[key]
    except Exception as exc:  # noqa: BLE001 - errores propios de SPICE
        _log.warning("cobertura SPICE no legible: %s", type(exc).__name__)
        return None


def _read_span(sp: Any, spk: str, codes: tuple[str, ...]) -> tuple[dt.date, dt.date] | None:
    """El tramo de días que el SPK cubre para todos los cuerpos, o `None` si falta alguno."""
    spans = []
    for code in codes:
        cover = sp.spkcov(spk, int(code))
        count = sp.wncard(cover)
        if count == 0:
            return None
        first, _ = sp.wnfetd(cover, 0)
        _, last = sp.wnfetd(cover, count - 1)
        spans.append((first, last))
    start_et = max(first for first, _ in spans)
    stop_et = min(last for _, last in spans)
    if stop_et <= start_et:
        return None
    start = dt.date.fromisoformat(sp.et2utc(start_et, "ISOC", 0)[:10])
    stop = dt.date.fromisoformat(sp.et2utc(stop_et, "ISOC", 0)[:10])
    # Un día cuenta si sus 00:00 UTC caen dentro: el primero, si el tramo no empieza justo a
    # medianoche, no (se descarta siempre, por prudencia); el último sí (sus 00:00 son anteriores
    # al fin). La corrección por tiempo de luz mira minutos atrás, dentro del tramo.
    first_day = start + dt.timedelta(days=1)
    return (first_day, stop) if first_day <= stop else None


def covered_days(
    settings: Settings, days: list[dt.date], target: str
) -> tuple[list[bool], Availability, tuple[dt.date, dt.date] | None]:
    """Qué días de la lista puede calcular SPICE, con su disponibilidad y su tramo."""
    state = availability(settings)
    span = coverage_span(settings, target) if state.available else None
    if span is None:
        return [False] * len(days), state, None
    return [span[0] <= day <= span[1] for day in days], state, span
