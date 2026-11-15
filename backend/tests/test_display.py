"""Cifras dentro del texto que lee la tripulacion: NASA-STD-3001 Vol 2, F.5.6.

Las mismas reglas que `frontend/src/lib/format.test.ts`: una cifra no puede leerse
de una forma en la franja de la interfaz y de otra en el motivo de una alerta.
"""

import math
import re
from pathlib import Path

import pytest

from app.core.display import (
    DECIMALS,
    UNITS,
    number,
    percent,
    quantity,
    rate_per_week,
    unit,
)
from app.ingest.codes import CATALOG

# Escrito de otra forma que en el codigo: una errata en uno no la repite el otro.
NNBSP = chr(0x202F)


def test_leading_zero_below_one() -> None:
    assert number(0.25, 2) == "0,25"
    assert number(-0.5, 1) == "-0,5"


def test_no_leading_zeros_and_no_plus() -> None:
    assert number(3.14, 2) == "3,14"
    assert number(12, 0) == "12"


def test_minus_always_but_never_on_zero() -> None:
    assert number(-3, 0) == "-3"
    assert number(-0.004, 2) == "0,00"


def test_thousands_from_five_digits_only() -> None:
    assert number(1234, 0) == "1234"
    assert number(12345, 0) == f"12{NNBSP}345"
    assert number(1234567.5, 1) == f"1{NNBSP}234{NNBSP}567,5"


def test_decimal_comma() -> None:
    assert number(36.6, 1) == "36,6"


def test_not_a_number_is_refused() -> None:
    with pytest.raises(ValueError):
        number(math.nan, 1)


def test_every_indicator_declares_its_decimals() -> None:
    """F.5.6 c: los decimales son una decision por indicador, no un valor por defecto."""
    missing = sorted(set(CATALOG) - set(DECIMALS))
    assert not missing, f"indicadores sin decimales declarados: {missing}"
    assert not sorted(set(DECIMALS) - set(CATALOG)), "decimales de indicadores que no existen"


def test_every_catalog_unit_has_a_reading() -> None:
    """F.5.6 b: ninguna cifra sin unidad, ni una unidad UCUM en crudo."""
    missing = sorted({code.unit for code in CATALOG.values()} - set(UNITS))
    assert not missing, f"unidades sin forma de lectura: {missing}"


def test_units_change_the_writing_not_the_magnitude() -> None:
    assert unit("Cel") == "°C"
    assert unit("ug/dL") == "µg/dL"
    assert unit("{score}") == "puntos"
    with pytest.raises(ValueError):
        unit("mg")


def test_a_reading_uses_the_indicator_decimals() -> None:
    assert quantity("heart-rate", 35.4, "/min") == "35 /min"
    assert quantity("sleep-duration", 1.978, "h") == "2,0 h"
    assert quantity("cortisol-salivary", 0.4567, "ug/dL") == "0,46 µg/dL"


def test_a_dimensionless_reading_has_no_unit_and_no_trailing_space() -> None:
    """UCUM «1» se lee como nada: la proporción de la batería Cognition y la densidad relativa de
    la orina se escriben sin el espacio que separaría una unidad que no hay."""
    assert quantity("cognition-bart-risk", 0.853, "1") == "0,85"
    assert quantity("urine-specific-gravity", 1.0204, "1") == "1,020"
    assert quantity("urine-caox-supersaturation-24h", 2.5, "1") == "2,50"


def test_a_weekly_slope_is_finer_than_the_reading() -> None:
    """Una deriva de 0,4 lpm/semana no puede leerse como "0"."""
    assert rate_per_week("heart-rate", 0.4, "/min") == "0,4 /min/semana"
    assert rate_per_week("mood-valence", -0.39, "{score}") == "-0,39 puntos/semana"


def test_percent() -> None:
    assert percent(0.125) == "12,5 %"
    assert percent(1.0, 0) == "100 %"


def test_the_interface_reads_units_the_same_way() -> None:
    """Una unidad no puede leerse de una forma en la franja y de otra en el motivo.

    Hay dos tablas —esta y la de `frontend/src/lib/format.ts`— porque cada lado
    formatea lo suyo. Si divergen, este test lo dice.
    """
    source = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "format.ts"
    ).read_text(encoding="utf-8")
    block = re.search(r"const UNIT_DISPLAY[^{]*\{(.*?)\n\};", source, re.S)
    assert block is not None, "no se encuentra UNIT_DISPLAY en format.ts"
    entries = re.findall(r'^\s*(?:"([^"]+)"|(\w+)):\s*"([^"]*)",', block.group(1), re.M)
    frontend = {quoted or bare: shown for quoted, bare, shown in entries}

    assert frontend == UNITS
