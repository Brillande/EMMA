"""Dos trampas del idioma por petición, vigiladas leyendo el código (`app/core/i18n.py`).

`tr` y `loc` leen el idioma de la petición en curso. Llamadas a nivel de módulo o de clase se
evalúan una vez, al importar; dentro de una función con `functools.cache`, una vez por argumentos.
En los dos casos el texto quedaría en el idioma del primero que pasó. Solo se ven las llamadas
directas: una función cacheada que llama a otra que traduce no se detecta aquí.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.core import i18n

APP = Path(__file__).resolve().parents[1] / "app"
TRANSLATORS = {"tr", "loc"}
CACHES = {"cache", "lru_cache", "cached_property"}


def _name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        return _name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _is_translator(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr in TRANSLATORS and _name(func.value) == "i18n"
    return isinstance(func, ast.Name) and func.id in TRANSLATORS


class _Finder(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.depth = 0
        self.cached = 0
        self.found: list[str] = []

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> None:
        decorators: list[ast.expr] = getattr(node, "decorator_list", [])
        is_cached = any(_name(item) in CACHES for item in decorators)
        for item in decorators:
            self.visit(item)
        self.depth += 1
        self.cached += is_cached
        body = node.body if isinstance(node.body, list) else [node.body]
        for statement in body:
            self.visit(statement)
        self.cached -= is_cached
        self.depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._function(node)

    def visit_Call(self, node: ast.Call) -> None:
        where = f"{self.path.relative_to(APP).as_posix()}:{node.lineno}"
        if _is_translator(node):
            if self.depth == 0:
                self.found.append(f"{where}: fuera de una función")
            elif self.cached:
                self.found.append(f"{where}: dentro de una función cacheada (usa `lang_cache`)")
            if _name(node.func) == "tr":
                english = node.args[1] if len(node.args) > 1 else None
                if isinstance(english, ast.Constant) and not str(english.value).strip():
                    self.found.append(f"{where}: `tr` sin inglés")
        self.generic_visit(node)


def _findings(source: str, path: Path) -> list[str]:
    finder = _Finder(path)
    finder.visit(ast.parse(source))
    return finder.found


def test_the_guard_sees_each_trap() -> None:
    path = APP / "ejemplo.py"
    assert _findings('LABEL = tr("a", "b")\n', path) == ["ejemplo.py:1: fuera de una función"]
    in_class = "class A:\n    x = i18n.loc(B)\n"
    assert _findings(in_class, path) == ["ejemplo.py:2: fuera de una función"]
    cached = '@cache\ndef f():\n    return i18n.tr("a", "b")\n'
    assert _findings(cached, path) == [
        "ejemplo.py:3: dentro de una función cacheada (usa `lang_cache`)"
    ]
    empty = 'def f():\n    return tr("a", "")\n'
    assert _findings(empty, path) == ["ejemplo.py:2: `tr` sin inglés"]
    fine = '@lang_cache\ndef f():\n    return tr("a", "b")\n\ni18n.en(A, "a")\n'
    assert _findings(fine, path) == []


def test_no_module_translates_at_import_or_inside_a_cache() -> None:
    found: list[str] = []
    files = sorted(APP.rglob("*.py"))
    assert len(files) > 200
    for path in files:
        if path == APP / "core" / "i18n.py":
            continue
        found.extend(_findings(path.read_text(encoding="utf-8"), path))
    assert found == []


def test_no_spanish_constant_has_two_englishes() -> None:
    import app.main  # noqa: F401  (carga todos los módulos que registran su inglés)

    assert i18n.conflicts() == []
