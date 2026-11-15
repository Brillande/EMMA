"""Hook de PyInstaller para astropy, sustituye al de pyinstaller-hooks-contrib.

El original importa **todos** los submodulos de astropy para descubrir los ocultos.
Con pytest instalado en el entorno, `astropy.visualization.wcsaxes` llama a
`pytest.importorskip("matplotlib")` al importarse, y la excepcion de pytest tumba el
empaquetado. EMMA usa astropy solo a traves de `astroquery.jplhorizons` (tiempo de
luz): la visualizacion y las suites de pruebas de astropy sobran en el ejecutable.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

_SKIP = ("astropy.visualization", "astropy.tests", ".tests", "conftest")


def _wanted(name: str) -> bool:
    return not any(part in name for part in _SKIP)


datas = collect_data_files("astropy", excludes=["**/tests/**"])
datas += [
    (path, target)
    for path, target in collect_data_files("astropy", include_py_files=True)
    if path.endswith(("_parsetab.py", "_lextab.py"))
]
datas += copy_metadata("astropy") + copy_metadata("numpy")

hiddenimports = collect_submodules("astropy", filter=_wanted) + ["numpy.lib.recfunctions"]
excludedimports = ["matplotlib", "pytest", "IPython"]
