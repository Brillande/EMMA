"""Congela el backend en `build/desktop/dist/emma-backend/` para la aplicacion de escritorio.

Se ejecuta con el Python de un entorno **limpio** (`build/venv-desktop`), creado solo
con las dependencias de ejecucion y PyInstaller. No con el `.venv` de desarrollo:
el ejecutable que se entrega no debe llevar pytest ni el resto de herramientas de
prueba, y con pytest presente el hook de astropy ni siquiera llega a empaquetar
(`packaging/hooks/hook-astropy.py`). Lo orquesta `desktop/scripts/build-backend.mjs`.

Cada opcion de abajo responde a un fallo real encontrado al probar el ejecutable.
"""

from __future__ import annotations

import ast
import os
import shutil
from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "build" / "desktop"
# Declaradas en pyproject pero no importadas por el codigo de EMMA
# (compliance/software-safety-classification.md). `scipy` estuvo aqui hasta el 2026-10-04: el
# visor 3D lo usa (nibabel al remuestrear, `volumes/assets.py`, `volumes/geometry.py`) y sin el
# toda segmentacion fallaba en la app instalada. Lo vigila tests/test_packaging.py.
EXCLUDED = ("pandas", "matplotlib")
POLARIS = BACKEND.parent / "polaris"
POLARIS_TOOLS = POLARIS / "tools"
# Datos de la copia de Polaris que leen sus herramientas en ejecución (polaris/ADOPTADO.txt).
# `orquestadores.json` entró con la octava ronda (2026-10-08): `cost_guard` y `enruta_comite` lo
# citan como el fichero que decide qué binario arranca; hoy ninguna herramienta copiada lo abre,
# y viaja para que quien las despierte no lo eche en falta solo en la aplicación instalada.
POLARIS_DATA = (
    "peripheries.json",
    "normas.json",
    "polaris_estado.checklist.json",
    "orquestadores.json",
)
# Carpetas de `polaris/tools/` que viajan enteras, con su mismo nombre.
POLARIS_DIRS = ("fichas",)
# Lo que hay en el primer nivel de `polaris/tools/`, no es código y NO viaja, con su motivo. Todo
# lo que no sea `.py` tiene que estar en una de las tres listas: los `.py` viajan por comodín, pero
# un dato nuevo de la copia se quedaba fuera del ejecutable sin que nada lo dijera, porque en el
# repositorio está siempre. Lo vigila tests/test_packaging.py.
POLARIS_NOT_SHIPPED = {
    "visor3d_web": (
        "fuentes del visor web: viaja compilado en `app/data/polaris_web` "
        "(frontend/scripts/build-polaris.mjs), no como fuente con su `package.json`"
    ),
    "fonts": (
        "solo trae el `LEEME.md` de las tipografías de la web de su autora: ninguna herramienta "
        "copiada abre esa carpeta"
    ),
    "colab": (
        "cuaderno para segmentar en Google Colab: se abre en la nube, y la aplicación instalada "
        "no sale a la nube ni ofrece ese camino"
    ),
}
# Los sustitutos de `app/polaris/compat/` que EMMA importa como módulos (ver `polaris_files`).
COMPAT_MODULES = ("winlock", "memguard")
# Los avisos de Polaris: su licencia, el aviso y la cita de su autora, de qué commit se copió y qué
# se cambió (AGPL §4 y §5a). El `NOTICE` de EMMA remite a ellos, y hasta el 2026-10-06 el
# ejecutable llevaba el código de Polaris sin ninguno. Lo vigila tests/test_packaging.py.
#
# Desde el 2026-10-07 viajan además los cuatro que faltaban para que esos avisos se puedan seguir
# sin el repositorio delante: el `README.md` y el `CHANGELOG.md` de Polaris (el `NOTICE` de EMMA
# los cuenta entre lo copiado), `MANIFEST.sha256` (la lista de la copia, con la que quien reciba
# el ejecutable comprueba que `polaris/tools/` es la que se dice) y `ADOPTADO.txt` (al que remite
# la cabecera de cada fichero de EMMA que llama a la copia).
POLARIS_NOTICES = (
    "LICENSE",
    "NOTICE",
    "CITATION.cff",
    "ORIGEN.md",
    "CAMBIOS.json",
    "README.md",
    "CHANGELOG.md",
    "MANIFEST.sha256",
    "ADOPTADO.txt",
)


def imported_names(source: str) -> set[str]:
    """Cada módulo que un fuente importa, y cada `paquete.nombre` de sus `from paquete import`.

    Se lee el árbol sintáctico y no el texto: la expresión regular que había antes pegaba el alias
    al nombre (`from scipy import ndimage as _nd` daba `scipy.ndimageas_nd`, que luego se
    descartaba por no existir) y no veía `import a, b`, los `from` partidos en varias líneas ni
    todos los nombres de una lista. `ast.walk` entra también en las funciones: Polaris importa ahí
    lo pesado.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            # `from PIL import ImageDraw`: ImageDraw es un submódulo que PyInstaller no ve
            # (en el primer congelado, visor3d_superpone_focos no cargaba por esto).
            names.update(f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*")
    return names


def polaris_files() -> list[str]:
    """Lo que viaja de `polaris/`, con su misma ruta: `app/polaris` lo busca junto a `app/`."""
    return [
        f"--add-data={POLARIS_TOOLS / '*.py'}{os.pathsep}polaris/tools",
        *[f"--add-data={POLARIS_TOOLS / name}{os.pathsep}polaris/tools" for name in POLARIS_DATA],
        # La ficha de cada herramienta (`fichas/<nombre>.py.json`): qué hace y qué necesita, tal
        # como lo escribió su autora. `/api/polaris/estado` la lee, y sin la carpeta la aplicación
        # instalada enseñaría las herramientas sin su ficha. La carpeta entera, como en la copia.
        *[
            f"--add-data={POLARIS_TOOLS / name}{os.pathsep}polaris/tools/{name}"
            for name in POLARIS_DIRS
        ],
        *[f"--add-data={POLARIS / name}{os.pathsep}polaris" for name in POLARIS_NOTICES],
        # El sustituto de fcntl se importa desde su carpeta, como fichero suelto (compat/fcntl.py).
        f"--add-data={BACKEND / 'app' / 'polaris' / 'compat' / 'fcntl.py'}"
        f"{os.pathsep}app/polaris/compat",
        # Los otros dos sustitutos que usa EMMA (`winlock`, que importa el arranque en
        # `app/polaris`, y `memguard`, en `app/memguard.py`) no son ficheros sueltos: viajan como
        # módulos dentro del ejecutable. `compat/` no tiene `__init__.py`, y que PyInstaller los
        # siga depende de que esos dos `import` sigan siendo estáticos; declarados aquí no. Los
        # dos que quedan (`resource.py`, `sitecustomize.py`) son para las pruebas de la copia.
        *[f"--hidden-import=app.polaris.compat.{name}" for name in COMPAT_MODULES],
    ]


def polaris_options() -> list[str]:
    """La copia de Polaris viaja como ficheros `.py` que el adaptador importa en ejecución.

    PyInstaller no los analiza (no los importa ningún módulo de `app/`), así que tampoco vería lo
    que ellos importan: se declara aquí, sacado de la propia copia, cada módulo de la biblioteca
    estándar o instalado que nombran. Lo que no esté instalado lo dirá `inventory()`.
    """
    local = {path.stem for path in POLARIS_TOOLS.glob("*.py")}
    excluded = {"fcntl", *EXCLUDED}
    imported: set[str] = set()
    for path in POLARIS_TOOLS.glob("*.py"):
        imported |= imported_names(path.read_text(encoding="utf-8"))

    def available(name: str) -> bool:
        top = name.split(".")[0]
        if top in local or top in excluded:
            return False
        try:
            return find_spec(name) is not None
        except (ImportError, ValueError):
            return False  # `paquete.nombre` donde `nombre` no es un submódulo, sino una función

    hidden = sorted(name for name in imported if available(name))
    return [
        *polaris_files(),
        *[f"--hidden-import={name}" for name in hidden],
        # `from reportlab.lib import colors` importa submódulos que la lectura de arriba no ve.
        "--collect-submodules=reportlab",
    ]


def options() -> list[str]:
    """Una función y no una constante: así el módulo se importa sin PyInstaller y sin buscar
    medio centenar de paquetes, y las pruebas pueden mirar qué se empaqueta."""
    return [
        str(BACKEND / "desktop_entry.py"),
        "--name=emma-backend",
        # Carpeta y no un solo .exe: el modo de un fichero lanza un segundo proceso que
        # se descomprime en temporales, y matar al primero puede dejar vivo al segundo.
        "--onedir",
        "--noconfirm",
        "--clean",
        f"--distpath={OUT / 'dist'}",
        f"--workpath={OUT / 'work'}",
        f"--specpath={OUT}",
        f"--additional-hooks-dir={BACKEND / 'packaging' / 'hooks'}",
        # uvicorn elige bucle y protocolo en tiempo de ejecucion: el analisis estatico
        # no los ve.
        "--collect-submodules=uvicorn",
        "--collect-submodules=fhir.resources",
        # pydicom carga por nombre sus diccionarios y codificadores al escribir un DICOM.
        "--collect-submodules=pydicom",
        # pypdfium2 carga la biblioteca PDFium de sus datos: sin --collect-all no viaja.
        "--collect-all=pypdfium2",
        # nibabel y scikit-image cargan submódulos por nombre (remuestreo, marching cubes).
        "--collect-submodules=nibabel",
        "--collect-submodules=skimage.measure",
        "--collect-data=astroquery",
        # Datos reales que viajan con el ejecutable: sin red, la reproduccion tiene que funcionar.
        f"--add-data={BACKEND / 'app' / 'data'}{os.pathsep}app/data",
        # La documentación, para buscar en ella sin red (`app/kb.py`): riesgos, integridad,
        # interfaz, especificación del equipo y decisiones sobre Polaris.
        f"--add-data={BACKEND.parent / 'compliance'}{os.pathsep}emma-docs/compliance",
        f"--add-data={BACKEND.parent / 'docs'}{os.pathsep}emma-docs/docs",
        f"--add-data={BACKEND.parent / 'README.md'}{os.pathsep}emma-docs",
        # Sin los datos de pyvo, astropy intenta DESCARGARLOS de internet al importar
        # astroquery. Sin red, las efemerides fallarian aunque estuvieran en cache.
        "--collect-data=pyvo",
        *[f"--exclude-module={name}" for name in EXCLUDED],
        "--log-level=WARN",
        *polaris_options(),
        *spice_options(),
    ]


# --- SPICE dentro del paquete (decisión del usuario, 2026-11-11) ---------------------------------
# El retardo con Tierra tiene que salir sin red desde el primer arranque: la caché de la
# aplicación instalada nace vacía. Viajan `spiceypy` (MIT, con la biblioteca CSPICE de NAIF) y los
# núcleos fijados en `app/environment/spice.py`, comprobados aquí antes de empaquetarlos.
# `spice.bundled_kernel_dir()` los busca en el paquete, detrás de la carpeta configurada.
SPICE_STAGE = OUT / "spice"
SPICE_FETCH = BACKEND / "scripts" / "fetch_spice_kernels.py"
# El origen de los núcleos, junto a ellos en el paquete: quien abra la carpeta sabe qué son, de
# dónde salen, con qué huella y con qué condiciones se redistribuyen.
SPICE_README = "ORIGEN-NUCLEOS-SPICE.txt"


class SpiceKernelsRefused(RuntimeError):
    """Los núcleos que habría que empaquetar no son los fijados: no se congela."""


def spice_options() -> list[str]:
    """Lo que el congelador necesita para SPICE: la biblioteca, su licencia y los núcleos.

    `spice.py` importa `spiceypy` por nombre en ejecución (`importlib`), así que PyInstaller no lo
    ve: se declara. Con él declarado entra el hook de `pyinstaller-hooks-contrib`
    (`hook-spiceypy.py`), que recoge `cspice.dll`. `--copy-metadata` lleva su `dist-info` con la
    licencia MIT (`licenses/LICENSE`). Los núcleos salen de `SPICE_STAGE`, que solo llena
    `stage_spice_kernels` con ficheros comprobados.
    """
    from app.environment import spice

    return [
        "--hidden-import=spiceypy",
        "--copy-metadata=spiceypy",
        *[
            f"--add-data={SPICE_STAGE / name}{os.pathsep}{spice.BUNDLED_SUBDIR}"
            for name in (*(kernel.name for kernel in spice.KERNELS), SPICE_README)
        ],
    ]


def _problems(folder: Path) -> list[str]:
    from app.environment import spice

    return [
        problem for kernel in spice.KERNELS
        if (problem := spice.check_kernel(kernel, folder / kernel.name)) is not None
    ]


def run_fetch_script() -> int:
    """Baja los núcleos que falten con su guion (por la puerta de salida, comprobados)."""
    import subprocess
    import sys

    return subprocess.run([sys.executable, str(SPICE_FETCH)], cwd=BACKEND, check=False).returncode


def _readme() -> str:
    from app.environment import spice

    lines = [
        "Núcleos SPICE de NAIF (JPL, NASA) empaquetados con EMMA",
        "",
        "Se redistribuyen SIN MODIFICAR, tal como los publica NAIF en su servidor. Antes de",
        "empaquetarlos se comprobó el tamaño y la huella de cada uno",
        "(backend/packaging/freeze.py), y la aplicación los vuelve a comprobar antes de",
        "cargarlos (app/environment/spice.py).",
        "",
    ]
    for kernel in spice.KERNELS:
        lines += [
            f"{kernel.name} ({kernel.kind}): {kernel.covers}",
            f"  Origen: {kernel.url}",
            f"  Tamaño: {kernel.size} bytes",
            f"  SHA-256: {kernel.sha256}",
            f"  MD5: {kernel.md5 or '(NAIF no publica huella de este núcleo)'}",
            f"  Integridad: {kernel.integrity_source}",
            "",
        ]
    lines += [
        f"Condiciones de NAIF ({spice.RULES_URL}, leídas el {spice.RULES_READ_ON}):",
        *[f"  «{quote}»" for quote in spice.RULES_QUOTES],
        "NAIF anima a reconocer el uso de SPICE y de los equipos que hicieron los núcleos:",
        "  https://naif.jpl.nasa.gov/naif/credit.html",
        "",
    ]
    return "\n".join(lines)


def stage_spice_kernels(
    source: Path,
    stage: Path = SPICE_STAGE,
    fetch: Callable[[], int] | None = run_fetch_script,
) -> list[Path]:
    """Deja en `stage` los núcleos fijados, comprobados, y su `SPICE_README`; o se niega.

    Si en `source` (la carpeta configurada, `data/spice`) falta alguno o no es el fijado, se baja
    con `fetch` (el guion de descarga, que solo guarda lo que verifica) y se vuelve a comprobar.
    Lo que no pase la comprobación no se empaqueta: `SpiceKernelsRefused`, con el motivo. La copia
    se comprueba otra vez en `stage`: lo que se empaqueta es lo comprobado, no lo que había antes.
    """
    from app.environment import spice

    # Lo de una preparación anterior no se queda: si esta se niega, no hay nada que empaquetar.
    if stage.exists():
        shutil.rmtree(stage)
    problems = _problems(source)
    if problems and fetch is not None:
        print(f"Núcleos SPICE incompletos en {source} ({'; '.join(problems)}): se descargan.")
        fetch()
        problems = _problems(source)
    if problems:
        raise SpiceKernelsRefused(
            f"No se empaquetan núcleos SPICE sin verificar: {'; '.join(problems)} (en {source}). "
            "Bájalos con `python scripts/fetch_spice_kernels.py` (necesita red; con "
            "EMMA_OFFLINE=true se niega) o copia ahí los ficheros fijados en "
            "app/environment/spice.py."
        )
    stage.mkdir(parents=True)
    staged = [
        Path(shutil.copy2(source / kernel.name, stage / kernel.name)) for kernel in spice.KERNELS
    ]
    problems = _problems(stage)
    if problems:
        shutil.rmtree(stage)
        raise SpiceKernelsRefused(f"La copia de los núcleos no verifica: {'; '.join(problems)}")
    readme = stage / SPICE_README
    readme.write_text(_readme(), encoding="utf-8")
    return [*staged, readme]


def main() -> int:
    import sys

    # El `app` de esta carpeta, el que se congela, y no otro instalado.
    sys.path.insert(0, str(BACKEND))
    if find_spec("spiceypy") is None:
        print(
            "Falta spiceypy en el entorno de empaquetado: instala el backend con los extras "
            "[desktop,spice] (desktop/scripts/build-backend.mjs lo hace).",
            file=sys.stderr,
        )
        return 2
    from app.core.config import get_settings
    from app.environment import spice

    try:
        stage_spice_kernels(spice.kernel_dir(get_settings()))
    except SpiceKernelsRefused as exc:
        print(str(exc), file=sys.stderr)
        return 3

    # Aquí y no arriba: PyInstaller solo está en el entorno de empaquetado, y el módulo tiene que
    # poder importarse desde el de desarrollo para probarlo.
    import PyInstaller.__main__

    PyInstaller.__main__.run(options())

    # Los avisos de licencia de lo congelado viajan junto al ejecutable (`third_party.py`).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import third_party

    written = third_party.write(OUT / "dist" / "emma-backend", excluded=EXCLUDED)
    print(f"Avisos de terceros: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
