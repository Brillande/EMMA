"""Toda regla que cambia una alerta está en la versión de reglas (especificación §12).

La huella se hizo a mano y se quedó corta: cambiar la persistencia cambiaba alertas sin cambiar
`rules_version`. Estas pruebas vigilan las dos mitades del arreglo: que lo nombrado en
`FINGERPRINTED` cuenta de verdad, y que no puede aparecer una constante numérica nueva en los
módulos que deciden sin que alguien diga si decide o no.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import importlib
from pathlib import Path
from typing import Any

import pytest

from app.core import versioning
from app.core.versioning import (
    FINGERPRINTED,
    GUARDED,
    NOT_IN_VERDICT,
    canonical,
    fingerprint,
    rules,
)


def _changed(value: Any) -> Any:
    """Otro valor del mismo tipo: el cambio más pequeño que una persona haría a mano."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, dt.timedelta):
        return value + dt.timedelta(hours=1)
    if isinstance(value, dict):
        key = next(iter(value))
        return {**value, key: _changed(value[key])}
    if isinstance(value, tuple):
        return (_changed(value[0]), *value[1:])
    if isinstance(value, str):  # incluye los StrEnum: otro miembro del mismo enumerado
        others = [member for member in type(value) if member != value]  # type: ignore[attr-defined]
        return others[0]
    raise AssertionError(f"no sé cambiar un {type(value).__name__}")


_NAMED = [(module, name) for module, names in sorted(FINGERPRINTED.items()) for name in names]


@pytest.mark.parametrize(("module", "name"), _NAMED)
def test_changing_any_named_rule_changes_the_version(
    module: str, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cada constante nombrada, cambiada ella sola, cambia la huella."""
    target = importlib.import_module(module)
    before = fingerprint(rules())
    monkeypatch.setattr(target, name, _changed(getattr(target, name)))
    assert fingerprint(rules()) != before, f"{module}.{name} no entra en la huella"


def test_the_parameters_the_first_fingerprint_left_out_are_in() -> None:
    """Los que la auditoría del 2026-10-09 encontró fuera, por su nombre."""
    assert {
        "_PERSISTENCE_FRACTION", "_SEVERITY_POINTS", "_TREND_POINTS", "_MAX_ISOLATION_FACTOR",
        "_DOSE_LIMIT_POINTS", "_HEALTHY_SEVERE_RATE", "_BURST_SURPRISE", "_MIN_BURST",
    } <= set(FINGERPRINTED["app.analysis.risk"])
    assert {"DEFAULT_ROLLING_WINDOW", "DEFAULT_ROLLING_LAG"} <= set(
        FINGERPRINTED["app.analysis.baseline"]
    )
    assert "LOW_CONFIDENCE_THRESHOLD" in FINGERPRINTED["app.ingest.fhir"]
    assert "CURRENT_WINDOW" in FINGERPRINTED["app.api.routes"]


@pytest.mark.parametrize("block", ["design", "during_event"])
def test_changing_a_routine_period_changes_the_version(
    block: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Los periodos de las rutinas, los de siempre y los de evento, deciden lo que se ve al día."""
    from app import routines

    data = copy.deepcopy(routines.load())
    before = fingerprint(rules())
    table = data["routines"] if block == "design" else data["during_event"]["routines"]
    key = next(iter(table))
    table[key]["period_hours"] = table[key]["period_hours"] / 2
    monkeypatch.setattr(routines, "load", lambda: data)
    assert fingerprint(rules()) != before, f"el periodo de {block} no entra en la huella"


def _has_number(node: ast.AST) -> bool:
    return any(
        isinstance(item, ast.Constant)
        and isinstance(item.value, (int, float))
        and not isinstance(item.value, bool)
        for item in ast.walk(node)
    )


def numeric_module_constants(source: str) -> set[str]:
    """Nombres asignados a nivel de módulo cuyo valor lleva algún número escrito."""
    found: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if _has_number(value):
            found.update(target.id for target in targets if isinstance(target, ast.Name))
    return found


def test_the_guard_reads_what_it_says_it_reads() -> None:
    source = (
        "A = 3\n"
        "B: float = 0.5\n"
        "C = dt.timedelta(days=14)\n"
        "D = {Severity.MILD: 10.0}\n"
        "E = ((0.99, Severity.MILD),)\n"
        "F = Severity.SEVERE\n"
        "G = 'texto'\n"
        "H = True\n"
        "def f():\n    I = 40.0\n"
    )
    assert numeric_module_constants(source) == {"A", "B", "C", "D", "E"}


@pytest.mark.parametrize("module", GUARDED)
def test_no_numeric_constant_decides_outside_the_version(module: str) -> None:
    """Una constante numérica nueva en un módulo que decide tiene que declararse.

    O entra en la huella (`FINGERPRINTED`) o se dice por qué no cambia el veredicto
    (`NOT_IN_VERDICT`). Lo que no vale es que exista sin que nadie lo haya decidido.
    """
    path = Path(importlib.import_module(module).__file__ or "")
    declared = set(FINGERPRINTED.get(module, ())) | set(NOT_IN_VERDICT.get(module, {}))
    missing = numeric_module_constants(path.read_text(encoding="utf-8")) - declared
    assert not missing, (
        f"{module}: {sorted(missing)} no está en la huella de reglas ni declarada como ajena "
        "al veredicto (app/core/versioning.py)"
    )


def test_the_declarations_are_consistent() -> None:
    assert set(GUARDED) <= set(FINGERPRINTED)
    for module, names in FINGERPRINTED.items():
        target = importlib.import_module(module)
        assert len(set(names)) == len(names), f"{module}: nombre repetido"
        for name in names:
            assert hasattr(target, name), f"{module}.{name} ya no existe"
    for module, reasons in NOT_IN_VERDICT.items():
        assert module in GUARDED, f"{module} no es un módulo vigilado"
        target = importlib.import_module(module)
        for name, reason in reasons.items():
            assert hasattr(target, name), f"{module}.{name} ya no existe"
            assert reason.strip(), f"{module}.{name} no dice por qué no decide"
            assert name not in FINGERPRINTED[module], f"{module}.{name} está en los dos sitios"


def test_an_exempt_constant_needs_its_reason_and_then_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La lista de «no afecta al veredicto» funciona: sin ella falla, con ella no."""
    module = "app.analysis.risk"
    monkeypatch.setitem(
        versioning.FINGERPRINTED, module,
        tuple(name for name in FINGERPRINTED[module] if name != "_MIN_BURST"),
    )
    with pytest.raises(AssertionError, match="_MIN_BURST"):
        test_no_numeric_constant_decides_outside_the_version(module)
    monkeypatch.setitem(versioning.NOT_IN_VERDICT, module, {"_MIN_BURST": "motivo de prueba"})
    test_no_numeric_constant_decides_outside_the_version(module)


def test_canonical_form_is_stable_and_refuses_what_it_does_not_know() -> None:
    assert canonical(dt.timedelta(days=2)) == 172800.0
    assert canonical({"b": 1, "a": (2.0, None)}) == [["a", [2.0, None]], ["b", 1]]
    with pytest.raises(TypeError):
        canonical(object())


def test_the_version_is_the_fingerprint_of_the_rules() -> None:
    versioning.rules_version.cache_clear()
    assert versioning.rules_version() == f"reglas@{fingerprint(rules())}"


def test_the_guard_watches_every_module_that_decides() -> None:
    """La guardia recorre `GUARDED`: si un módulo sale de la lista, deja de vigilarlo sin fallar.

    Por eso la lista se fija aquí. Quitar de ella un módulo que decide tiene que ser una decisión
    escrita en esta prueba, no un descuido que pase en verde.
    """
    # La fase del ciclo entra en 2026-11-15 (lote «ciclo», B3): desplaza la base y la tendencia.
    assert set(GUARDED) == {
        "app.analysis.risk", "app.analysis.baseline", "app.analysis.trend",
        "app.analysis.cycle_phase",
    }
