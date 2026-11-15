"""Cuánto se le escapa a la des-identificación de EMMA, medido con el banco de Polaris.

`deid_eval.fugas` busca, en la salida real, el texto normalizado de cada identificador largo
anotado a mano. El corpus (`tests/data/deid_corpus/`, brat) es inventado: doce informes con todos
los identificadores que se esperan en uno escaneado. La cifra queda en `risk-management-file.md`
(H17); si sube, esta prueba falla.

`deid_eval.puntuar` mide otra cosa: por tipo de entidad, cuántas quedan tapadas enteras. Necesita
los tramos tapados (`masked_spans`), que aquí se comprueban contra la salida real.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from app import polaris
from app.reports import deid as deid_module
from app.reports.deid import (
    LAYER_EMMA_BEFORE,
    LAYER_EMMA_KIN,
    LAYER_EMMA_TITLE,
    LAYER_POLARIS,
    LAYER_WITHHELD,
    MARK,
    Span,
    SpanAlignmentError,
    deidentify,
    masked_spans,
)

CORPUS = Path(__file__).parent / "data" / "deid_corpus"
# Lo único que se escapa hoy, y es un límite declarado: un nombre de pila suelto delante del
# parentesco al principio de la frase ("Marta, su sobrina, llamó", informe12). Una mayúscula sola
# ahí puede ser "Además, su madre…"; sin la capa NER no se tapa. Hasta la regla de parentesco
# (2026-10-07) se escapaba "su hermana Lucía Fernández" (informe03), y hasta su segunda pasada
# (2026-10-20), el nombre delante del parentesco ("con Rosa Beltrán, su cuñada", informe11).
KNOWN_LEAKS = {"FAMILIARES_SUJETO_ASISTENCIA": 1}


def test_the_corpus_is_coherent() -> None:
    bench = polaris.load("deid_eval")
    docs = bench.cargar_brat(str(CORPUS))
    assert len(docs) == 12
    assert not bench.offsets_cuadran(docs), "las anotaciones no cuadran con los textos"


def test_only_the_known_leaks_escape() -> None:
    bench = polaris.load("deid_eval")
    docs = bench.cargar_brat(str(CORPUS))
    outputs = []
    for _id, text, _gold in docs:
        result = deidentify(text)
        assert result.verified, f"{_id}: retenido ({result.remaining})"
        outputs.append(result.text)
    leaks = {
        label: row["fugas"]
        for label, row in bench.fugas(docs, outputs)["por_etiqueta"].items()
        if row["fugas"]
    }
    assert leaks == KNOWN_LEAKS


def test_the_family_history_keeps_its_clinical_content() -> None:
    """informe11: se tapan los nombres de los familiares y nada de lo clínico."""
    text = (CORPUS / "informe11.txt").read_text(encoding="utf-8")
    spans = masked_spans(text)
    assert [(text[span.start : span.end], span.layer) for span in spans] == [
        ("Elena Castro Rubio", LAYER_EMMA_KIN),
        ("Marcos y Julia", LAYER_EMMA_KIN),
        ("Andrés Molina Prieto", LAYER_EMMA_KIN),
        ("Rosa Beltrán", LAYER_EMMA_KIN),
    ]
    output = deidentify(text).text
    for kept in (
        "Madre con Diabetes Mellitus tipo 2. Padre fallecido de Infarto.",
        "Abuelo materno: enfermedad de Parkinson, en tratamiento con Levodopa.",
        "su esposa [REDACTADO] y sus hijos [REDACTADO].",
        "Hermano: [REDACTADO], donante compatible.",
        "Acude a la consulta con [REDACTADO], su cunada.",
        "Creatinina 0,9 mg/dL   Glucosa 92 mg/dL",
    ):
        assert kept in output, kept


def test_names_before_the_kinship_go_and_clinical_appositions_stay() -> None:
    """informe12: el nombre delante del parentesco se tapa; lo clínico en aposición, no."""
    text = (CORPUS / "informe12.txt").read_text(encoding="utf-8")
    spans = masked_spans(text)
    kin = [text[span.start : span.end] for span in spans if span.layer == LAYER_EMMA_KIN]
    assert kin == ["Inés Montero Gil", "Tomás", "Clara Varela"]
    output = deidentify(text).text
    for kept in (
        "Acude acompanado de [REDACTADO], su esposa, y de [REDACTADO], su hijo menor.",
        "avisar a [REDACTADO] (su hermana).",
        # Delante de ", su madre" y compañía: lo que abre la frase, lo clínico y un centro.
        "Ademas, su madre refiere que la Diabetes Mellitus esta controlada.",
        "Hipertension Arterial, su padre tambien. Enfermedad de Crohn, su tio materno.",
        "Ingreso en el Hospital Clinico, su madre tambien.",
        # Límite declarado: nombre de pila suelto al principio de la frase (`KNOWN_LEAKS`).
        "Marta, su sobrina, llamo por la tarde.",
    ):
        assert kept in output, kept


def test_a_relative_half_masked_by_polaris_is_one_span_of_the_kinship_rule() -> None:
    """Polaris tapa el apellido de "su padre, Tomás Pérez"; la regla, el nombre entero."""
    text = "Persona de aviso: su padre, Tomás Pérez"
    spans = masked_spans(text)
    assert ("Tomás Pérez", LAYER_EMMA_KIN) in [
        (text[span.start : span.end], span.layer) for span in spans
    ]
    assert deidentify(text).text == "Persona de aviso: su padre, [REDACTADO]"


def test_holder_and_health_card_are_masked_but_labels_stay() -> None:
    result = deidentify("Tarjeta sanitaria: BBBB123456789012\nTSI: AB12345678\nHb 14 g/dL")
    assert "BBBB123456789012" not in result.text and "AB12345678" not in result.text
    assert "Tarjeta sanitaria:" in result.text and "Hb 14 g/dL" in result.text
    holder = deidentify("Titular: Pedro Alonso Ruiz\nPCR 2,1 mg/L")
    assert "Pedro" not in holder.text and "PCR 2,1 mg/L" in holder.text


# --- Recall por tipo de entidad (`deid_eval.puntuar`) -------------------------------------------
#
# Suelos medidos el 2026-10-07 (`scripts/deid_report.py`): entidades tapadas ENTERAS de cada tipo,
# y cuántas hay. Pueden subir; si una baja, la prueba falla. `FAMILIARES_SUJETO_ASISTENCIA` estaba
# en 0 de 2 hasta la regla de parentesco; con ella y con informe11 (cinco familiares más) queda en
# 6 de 7. El séptimo era el nombre delante del parentesco: desde el 2026-10-20 lo tapa la segunda
# pasada de la regla (7 de 7), y con informe12 (cuatro familiares más) queda en 10 de 11. El que
# falta es el límite declarado de `KNOWN_LEAKS`.
COVERED_FLOOR = {
    "NOMBRE_SUJETO_ASISTENCIA": (7, 7),
    "FECHAS": (6, 6),
    "ID_SUJETO_ASISTENCIA": (6, 6),
    "OTRO_NUMERO_IDENTIF": (5, 5),
    "NOMBRE_PERSONAL_SANITARIO": (3, 3),
    "NUMERO_TELEFONO": (2, 2),
    "CORREO_ELECTRONICO": (2, 2),
    "CALLE": (2, 2),
    "FAMILIARES_SUJETO_ASISTENCIA": (10, 11),
    "ID_ASEGURAMIENTO": (1, 1),
}
# Solo los patrones de Polaris, sin las reglas de EMMA: lo que las reglas añaden es la diferencia.
POLARIS_ALONE_COVERED = 24


def _report() -> Any:
    path = Path(__file__).parents[1] / "scripts" / "deid_report.py"
    spec = importlib.util.spec_from_file_location("deid_report", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply(text: str, spans: tuple[Span, ...]) -> str:
    """El texto con cada tramo cambiado por la marca (los que se solapan, por una sola)."""
    merged: list[list[int]] = []
    for start, end, _layer in sorted(spans):
        if merged and start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    for start, end in reversed(merged):
        text = text[:start] + MARK + text[end:]
    return text


def test_the_spans_explain_the_real_output() -> None:
    """Los tramos se deducen del texto tapado: aplicados al original tienen que dar ese texto."""
    bench = polaris.load("deid_eval")
    normalise = polaris.load("borde")._normalizar
    for _id, text, _gold in bench.cargar_brat(str(CORPUS)):
        spans = masked_spans(text)
        assert spans and all(0 <= span.start < span.end <= len(text) for span in spans), _id
        assert normalise(_apply(text, spans))[0] == deidentify(text).text, _id


def test_a_span_is_the_identifier_and_names_its_layer() -> None:
    text = "Glucosa 92 mg/dL\nIBAN ES9121000418450200051332\nRevisado por la Dra. Ana López."
    spans = masked_spans(text)
    assert [(text[span.start : span.end], span.layer) for span in spans] == [
        ("ES9121000418450200051332", LAYER_EMMA_BEFORE),
        ("Dra. Ana López", LAYER_EMMA_TITLE),
    ]
    assert masked_spans(text, emma_rules=False) == ()
    assert masked_spans("Hemoglobina 13,9 g/dL") == ()
    # Los tramos van sobre el original aunque Polaris quite las tildes antes de tapar.
    accented = "Teléfono de la clínica: 612345678"
    (phone,) = masked_spans(accented)
    assert (accented[phone.start : phone.end], phone.layer) == ("612345678", LAYER_POLARIS)


def test_a_withheld_text_is_one_span_that_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        deid_module._original(),
        "de_identificar_verificado",
        lambda texto, ner=False: (None, 1, False, "resto"),
    )
    assert masked_spans("DNI 12345678Z") == ((0, 13, LAYER_WITHHELD),)


def test_a_text_that_is_not_the_input_with_marks_is_refused() -> None:
    """Si una capa hiciera algo más que tapar, no se inventan tramos."""
    assert deid_module._gaps("DNI 12345678Z fin", "DNI [REDACTADO] fin") == [(4, 13)]
    for changed in ("dni [REDACTADO] fin", "DNI [REDACTADO] FIN", "DNI [REDACTADO] x fin", "DNI"):
        with pytest.raises(SpanAlignmentError):
            deid_module._gaps("DNI 12345678Z fin", changed)


def test_recall_per_entity_does_not_drop() -> None:
    bench = polaris.load("deid_eval")
    docs = bench.cargar_brat(str(CORPUS))
    spans = [list(masked_spans(text)) for _id, text, _gold in docs]
    assert not any(span.layer == LAYER_WITHHELD for found in spans for span in found), (
        "un informe retenido cuenta como tapado entero"
    )
    scored = bench.puntuar(docs, spans)
    rows = scored["por_etiqueta"]
    assert {label: row["n"] for label, row in rows.items()} == {
        label: total for label, (_covered, total) in COVERED_FLOOR.items()
    }
    for label, (floor, _total) in COVERED_FLOOR.items():
        assert rows[label]["cubiertas"] >= floor, label
    # Lo publicado: 45 anotadas (34 hasta informe11, 39 hasta informe12) y 1 fuga literal de 34.
    assert scored["entidades"] == 45
    leaks = bench.fugas(docs, [deidentify(text).text for _id, text, _gold in docs])
    assert (leaks["fugas"], leaks["entidades"]) == (1, 34)
    alone = bench.puntuar(
        docs, [list(masked_spans(text, emma_rules=False)) for _id, text, _gold in docs]
    )
    covered = sum(row["cubiertas"] for row in alone["por_etiqueta"].values())
    assert covered == POLARIS_ALONE_COVERED


def test_the_published_table_is_the_measured_one() -> None:
    """`compliance/` lleva una copia de la tabla: si se mide otra cosa, hay que regenerarla."""
    if not (Path(__file__).parents[1] / "scripts").is_dir():
        pytest.skip("copia de `scripts/mutants.py`: no lleva los guiones")
    report = _report()
    published = report.RISK_FILE.read_text(encoding="utf-8")
    block = published.split(report.BEGIN)[1].split(report.END)[0]
    expected = "\n".join(report.render(report.measure()))
    assert expected in block, "corre scripts/deid_report.py --write"
