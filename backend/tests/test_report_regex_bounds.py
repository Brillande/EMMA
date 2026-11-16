"""Las regex de los informes no se vuelven cuadráticas con un texto preparado (auditoría run-2,
`emma:reports:deid-regex-superlinear` y `emma:reports:labs-regex-superlinear`).

Los patrones lentos son de Polaris (`borde._RE_EMAIL`, `biomarcadores._RE_CON_UNIDAD`), copia
literal que aquí no se edita: EMMA no les pasa lo que ningún informe real trae. El suyo propio,
`_PASSPORT`, se arregló con cuantificadores posesivos. Las cotas de tiempo son holgadas: medido
antes, cada caso tardaba segundos o decenas de segundos.
"""

from __future__ import annotations

import time

from app.reports import deid, labs


def _seconds(call: object) -> float:
    started = time.perf_counter()
    call()  # type: ignore[operator]
    return time.perf_counter() - started


def test_a_huge_word_is_withheld_without_reaching_polaris() -> None:
    result = deid.deidentify("informe " + "a" * 20_000)
    assert not result.verified and result.text == ""
    assert "palabra" in result.remaining[0]
    assert _seconds(lambda: deid.deidentify("a" * 20_000)) < 0.5


def test_a_huge_text_is_withheld() -> None:
    result = deid.deidentify("palabra " * (deid.MAX_DEID_CHARS // 8 + 1))
    assert not result.verified and "caracteres" in result.remaining[0]


def test_ordinary_long_words_still_go_through() -> None:
    url = "https://www.ejemplo.org/" + "ruta/" * 40
    assert len(url) < deid.MAX_DEID_TOKEN
    assert deid.deidentify(f"Ver {url} para más detalle.").verified


def test_the_passport_rule_does_not_backtrack_over_a_long_gap() -> None:
    gap = "pasaporte" + " " * 20_000 + "!"
    assert _seconds(lambda: deid._PASSPORT.subn("x", gap)) < 0.1
    masked, count = deid._PASSPORT.subn(lambda m: m.group(1) + deid.MARK, "pasaporte nº: AB123456")
    assert count == 1 and "AB123456" not in masked
    _, spaced = deid._PASSPORT.subn("x", "Passport   #  123456789")
    assert spaced == 1


def test_a_long_digit_run_is_not_a_lab_line() -> None:
    assert _seconds(lambda: labs.extract("Glucosa " + "1" * 50_000)) < 0.5
    assert labs.extract("Glucosa " + "1" * 50_000)["readings"] == []
    [reading] = labs.extract("Glucosa 95 mg/dL 70 - 110")["readings"]
    assert reading["key"] == "glucose"
