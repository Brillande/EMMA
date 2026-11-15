"""Los avisos de licencia de los paquetes Python que viajan en el backend congelado.

`packaging/third_party.py` existe porque el instalador llevaba los avisos de EMMA, Polaris y
Marplanner y no los de FastAPI, numpy, cryptography... (revisión de fuentes del 2026-11-14,
`docs/fuentes-y-procedencia.md`, «Resumen de huecos»). Aquí se comprueba con el entorno de pruebas,
que tiene las mismas dependencias de ejecución que el de empaquetado.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

BACKEND = Path(__file__).resolve().parents[1]


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"emma_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


third_party = _load(BACKEND / "packaging" / "third_party.py")


def test_runtime_packages_are_listed_with_their_license_text() -> None:
    text = third_party.notices()
    for name in ("fastapi", "numpy", "cryptography", "pydicom", "httpx", "sqlalchemy"):
        assert f"\n{name} " in text.lower(), name
    # FastAPI trae su LICENSE: va el texto MIT, no solo el nombre de la licencia.
    assert "Permission is hereby granted, free of charge" in text


def test_build_tools_and_freeze_exclusions_are_left_out() -> None:
    text = third_party.notices(excluded=("pandas",)).lower()
    for name in ("pip", "pyinstaller", "pandas"):
        assert f"\n{name} " not in text, name


def test_freeze_writes_the_notices_next_to_the_executable() -> None:
    # Que `freeze.main` llame a `third_party.write` sobre la carpeta que copia el instalador
    # (`desktop/package.json`, extraResources «backend»), con las exclusiones de `freeze.py`.
    source = (BACKEND / "packaging" / "freeze.py").read_text(encoding="utf-8")
    main = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    body = ast.unparse(main)
    assert "third_party.write(OUT / 'dist' / 'emma-backend', excluded=EXCLUDED)" in body
