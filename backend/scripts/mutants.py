# SPDX-License-Identifier: AGPL-3.0-or-later
"""Comprueba que cada defensa tiene una prueba que se pone roja al quitarla.

    .venv/Scripts/python.exe scripts/mutants.py tests/mutants/*.json [-v]

Por qué existe: una prueba que sigue verde cuando le quitas el candado es peor que no tener
prueba, porque da la cobertura por hecha. Leyendo una prueba no se ve; se ve rompiendo a
propósito lo que dice proteger. Las defensas de lenguaje, cotejo, comité y firma del borrador son
Clase C (`compliance/software-safety-classification.md`): merecen esa comprobación.

Adaptador sobre Polaris copiado tal cual (`polaris/tools/mutantes.py`; el commit, en
`polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris, «Beyond the Protocol»;
se carga con `app.polaris.load`). La campaña la corre la clase `Campana` del original, con sus
tres reglas, cada una nacida de un fallo real: la prueba tiene que estar verde sin mutar; el
trozo a mutar tiene que aparecer exactamente una vez; y el mutante tiene que cargarse de verdad
en lugar del original. Lo que pone EMMA alrededor (pegamento, no cambios al original):
  * Las campañas de EMMA están en inglés (`target`, `test`, `mutations`, `label`, `old`, `new`)
    y se traducen a las de Polaris (`objetivo`, `test`, `mutaciones`, `etiqueta`, `viejo`,
    `nuevo`). Una mutación puede llevar su propio `target` (otro módulo, las mismas pruebas): se
    corre una `Campana` por objetivo.
  * Polaris escribe el mutante junto al original y la prueba lo carga por una variable de entorno.
    Las pruebas de EMMA importan `app` directamente, y este repositorio lo editan varias sesiones
    a la vez: mutar en su sitio podría pisar un cambio ajeno. Aquí se copia `app/`, `tests/`,
    `scripts/` y `polaris/` a una carpeta temporal con la misma forma que el repositorio, y la
    "prueba" que corre `Campana` es un lanzador que pone el mutante en el sitio del objetivo
    dentro de esa copia, corre pytest y deja el original. El repositorio no se toca.
  * Como el backend está instalado en modo editable, `import app` podría resolver al original y
    no a la copia. Antes de empezar se comprueba desde qué ruta se importa; si no es la copia, la
    campaña no corre (todos los mutantes "sobrevivirían" sin haberse probado).
Herramienta de desarrollo: no viaja en el producto ni toca la red.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app import polaris  # noqa: E402

ENV = "EMMA_MUTANT"  # la ruta del código que la prueba tiene que cargar (convención de Polaris)
RUNNER = "_emma_mutant_runner.py"
# El lanzador que `Campana` usa como "prueba": el mutante de Polaris se escribe al lado del
# objetivo con otro nombre; aquí se copia encima del objetivo, se corre pytest y se restaura.
RUNNER_SOURCE = f'''import os, shutil, subprocess, sys
target, tests = sys.argv[1], sys.argv[2:]
code = os.environ["{ENV}"]
backup = target + ".original"
shutil.copyfile(target, backup)
try:
    if os.path.abspath(code) != os.path.abspath(target):
        shutil.copyfile(code, target)
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    sys.exit(subprocess.run([sys.executable, "-m", "pytest", "-q", "-x",
                             "-p", "no:cacheprovider", *tests], env=env).returncode)
finally:
    shutil.copyfile(backup, target)
    os.unlink(backup)
'''


def _sandbox() -> Path:
    """Copia con la forma del repositorio (`backend/app`, `backend/tests`, `polaris/`), para que
    el adaptador de Polaris encuentre la copia de al lado y no otra."""
    root = Path(tempfile.mkdtemp(prefix="emma_mutants_"))
    backend = root / "backend"
    # `scripts/` también: `tests/test_polaris_tests_runner.py` carga un guion por su ruta, y una
    # campaña puede tener un guion por objetivo.
    for name in ("app", "tests", "scripts"):
        shutil.copytree(
            BACKEND / name, backend / name, ignore=shutil.ignore_patterns("__pycache__")
        )
    shutil.copy(BACKEND / "pyproject.toml", backend / "pyproject.toml")
    shutil.copytree(
        BACKEND.parent / "polaris", root / "polaris",
        ignore=shutil.ignore_patterns("node_modules", "__pycache__"),
    )
    # La documentación del proyecto, que el buscador (`app/kb.py`) indexa: sin ella, sus pruebas
    # no tienen qué buscar y la campaña no corre.
    for name in ("compliance", "docs"):
        shutil.copytree(BACKEND.parent / name, root / name)
    shutil.copy(BACKEND.parent / "README.md", root / "README.md")
    # Las fuentes de la interfaz, sin dependencias: la tabla del reto
    # (`compliance/challenge-coverage.md`) nombra ficheros de `frontend/src` y
    # `tests/test_context_sources.py` comprueba que cada uno existe.
    shutil.copytree(
        BACKEND.parent / "frontend" / "src", root / "frontend" / "src",
        ignore=shutil.ignore_patterns("node_modules"),
    )
    # Lo que decide qué viaja en el instalador (`tests/mutants/packaging.json`): las opciones del
    # congelado, el guion de la copia que su prueba carga por ruta (`scripts/`, ya copiado arriba:
    # copiarlo otra vez aquí hacía fallar `copytree` y ninguna campaña arrancaba), y la lista del
    # instalador.
    for name in ("packaging",):
        shutil.copytree(
            BACKEND / name, backend / name, ignore=shutil.ignore_patterns("__pycache__")
        )
    (root / "desktop").mkdir()
    shutil.copy(BACKEND.parent / "desktop" / "package.json", root / "desktop" / "package.json")
    (backend / RUNNER).write_text(RUNNER_SOURCE, encoding="utf-8")
    return backend


def _imports_from(backend: Path) -> str:
    result = subprocess.run(
        [sys.executable, "-c", "import app; print(app.__file__)"], cwd=backend,
        capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(backend)},
        check=False,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[-1] if result.returncode == 0 and lines else ""


def campaign(spec_path: Path, verbose: bool) -> bool:
    spec: dict[str, Any] = json.loads(spec_path.read_text(encoding="utf-8"))
    target_rel, tests, mutations = spec["target"], list(spec["test"]), spec["mutations"]
    print(f"campaña {spec_path.name}: {target_rel} ({len(mutations)} mutaciones)")
    # Una mutación puede llevar su propio `target`: la defensa que vigilan las pruebas de la
    # campaña puede vivir en otro módulo (el borde del estudio que corta un hueso está en
    # `volumes/skeleton_view.py` y lo vigila el dolor sobre el esqueleto). `Campana` muta un solo
    # objetivo: se corre una por objetivo, todas sobre la misma copia.
    groups: dict[str, list[dict[str, Any]]] = {}
    for mutation in mutations:
        groups.setdefault(str(mutation.get("target", target_rel)), []).append(mutation)
    backend = _sandbox()
    try:
        where = _imports_from(backend)
        if not where or not Path(where).resolve().is_relative_to(backend.resolve()):
            print(f"  NO CORRE: `import app` resuelve a {where!r}, no a la copia")
            return False
        passed = True
        for target, group in groups.items():
            if len(groups) > 1 or target != target_rel:
                print(f"  objetivo {target} ({len(group)} mutaciones)")
            original = polaris.load("mutantes").Campana(
                {
                    "objetivo": target,
                    "test": [sys.executable, RUNNER, target, *tests],
                    "env": ENV,
                    "mutaciones": [
                        {"etiqueta": m["label"], "viejo": m["old"], "nuevo": m.get("new", "")}
                        for m in group
                    ],
                },
                base=str(backend),
            )
            survivors, problems, runs = original.corre(verboso=verbose)
            if survivors is None:
                print(f"  NO CORRE: {problems[0]}")
                return False
            for problem in problems:
                print(f"  MAL ESCRITA  {problem}")
            if survivors:
                print(f"  {len(survivors)} sobreviven: esa defensa no tiene prueba que la vigile")
            elif not problems:
                print(f"  {runs}/{len(group)} cazados")
            passed = passed and not survivors and not problems
        return passed
    finally:
        shutil.rmtree(backend.parent, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    # `Campana` escribe marcas (✅/🔴) que la consola de Windows en cp1252 no sabe imprimir.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("campaigns", nargs="+", type=Path)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    results = [campaign(path, args.verbose) for path in args.campaigns]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
