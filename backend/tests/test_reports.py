"""Informes escaneados con OCR local (portado de Polaris `ocr_informes.py`). Sin red.

Los casos de maquetación son los de Polaris (`tests/test_ocr_layout.py`): trabajan sobre el TSV
de tesseract, así que corren sin tesseract instalado. Las pruebas de la API simulan tesseract.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.api.routes import get_store
from app.core.storage import ImagingBlobRow
from app.reports import deid, ocr

HEADER = "\t".join([
    "level", "page_num", "block_num", "par_num", "line_num", "word_num",
    "left", "top", "width", "height", "conf", "text",
])


def word(block: int, line: int, left: int, top: int, width: int, conf: float, text: str) -> str:
    return f"5\t1\t{block}\t1\t{line}\t1\t{left}\t{top}\t{width}\t20\t{conf}\t{text}"


def tsv(*rows: str) -> str:
    return "\n".join([HEADER, *rows])


def test_table_cells_stay_apart() -> None:
    text, confidence, words = ocr.tsv_to_text(tsv(
        word(1, 1, 100, 100, 200, 95, "Linfocitos"),
        word(1, 1, 900, 100, 60, 95, "0.8"),
        word(1, 1, 1600, 100, 220, 95, "1.0-4.5"),
    ))
    assert text == "Linfocitos  ·  0.8  ·  1.0-4.5"
    assert (confidence, words) == (95.0, 3)


def test_a_sentence_stays_a_sentence() -> None:
    text, _, _ = ocr.tsv_to_text(tsv(
        word(1, 1, 100, 100, 120, 90, "el"),
        word(1, 1, 240, 100, 150, 90, "zorro"),
        word(1, 1, 410, 100, 130, 90, "veloz"),
    ))
    assert text == "el zorro veloz"


def test_a_guessed_page_is_below_the_threshold() -> None:
    _, confidence, _ = ocr.tsv_to_text(tsv(
        word(1, 1, 100, 100, 200, 20, "iIegibIe"), word(1, 1, 400, 100, 200, 30, "rnaI"),
    ))
    page = ocr.PageText(1, "x", confidence, 2)
    assert page.low_confidence


def test_non_words_do_not_count() -> None:
    _, confidence, words = ocr.tsv_to_text(tsv(
        word(1, 1, 100, 100, 200, -1, "x"), word(1, 1, 400, 100, 200, 90, "bueno"),
    ))
    assert (confidence, words) == (90.0, 1)


def test_blocks_keep_a_blank_line() -> None:
    text, _, _ = ocr.tsv_to_text(tsv(
        word(1, 1, 100, 100, 200, 90, "primero"), word(2, 1, 100, 400, 200, 90, "segundo"),
    ))
    assert text == "primero\n\nsegundo"


def test_a_scanned_pdf_is_rendered_page_by_page() -> None:
    buffer = io.BytesIO()
    pages = [Image.new("RGB", (200, 280), "white"), Image.new("RGB", (200, 280), "white")]
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:])
    data = buffer.getvalue()
    assert ocr.text_layer(data) is None  # sin capa de texto: escaneado
    assert len(ocr.page_images(data, "application/pdf")) == 2


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (300, 400), 255).save(buffer, format="PNG")
    return buffer.getvalue()


def upload(client: TestClient, data: bytes, media_type: str = "image/png") -> dict[str, object]:
    response = client.post(
        "/api/reports",
        params={"kind": "analitica", "recorded_by": "CMO"},
        content=data,
        headers={"Content-Type": media_type},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def _pdf_page(width_pt: float, height_pt: float, pages: int = 1) -> bytes:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(width_pt, height_pt)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_a_pdf_page_too_big_to_paint_is_refused_before_painting(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una `MediaBox` de 200 pulgadas son 60 000 × 60 000 píxeles a 300 ppp (auditoría run-2,
    `emma:reports:pdf-render-unbounded-page-size`): 422 sin pintar nada."""
    painted: list[int] = []
    import pypdfium2 as pdfium

    original = pdfium.PdfPage.render
    monkeypatch.setattr(
        pdfium.PdfPage, "render", lambda self, **kw: painted.append(1) or original(self, **kw)
    )
    response = client.post(
        "/api/reports", params={"kind": "analitica", "recorded_by": "CMO"},
        content=_pdf_page(14_400, 14_400), headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 422
    assert "tope" in response.json()["detail"]
    assert painted == []
    assert len(get_store().ledger) == 0


def test_a4_pages_still_paint_and_the_sum_has_its_own_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    assert len(ocr.page_images(_pdf_page(595, 842, pages=2), "application/pdf")) == 2
    monkeypatch.setattr(ocr, "MAX_TOTAL_PIXELS", 10_000_000)
    with pytest.raises(ocr.PageTooLarge, match="juntas"):
        ocr.page_images(_pdf_page(595, 842, pages=2), "application/pdf")


def _tiff(frames: int, size: tuple[int, int] = (10, 10)) -> bytes:
    images = [Image.new("1", size) for _ in range(frames)]
    buffer = io.BytesIO()
    images[0].save(buffer, format="TIFF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def test_a_tiff_converts_only_the_pages_it_keeps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Antes se convertían todos los fotogramas y luego se cortaba a `MAX_PAGES` (auditoría run-2,
    `emma:reports:tiff-frames-before-max-pages`)."""
    converted: list[int] = []
    original = Image.Image.convert
    monkeypatch.setattr(
        Image.Image, "convert", lambda self, *a, **k: converted.append(1) or original(self, *a, **k)
    )
    pages = ocr.page_images(_tiff(ocr.MAX_PAGES + 20), "image/tiff")
    assert len(pages) == ocr.MAX_PAGES
    assert len(converted) == ocr.MAX_PAGES


def test_a_tiff_frame_beyond_the_cap_is_refused() -> None:
    with pytest.raises(ocr.PageTooLarge, match="tope"):
        ocr.page_images(_tiff(1, size=(5000, 5000)), "image/tiff")


def test_without_tesseract_the_report_is_kept_but_has_no_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "find_tesseract", lambda configured=None: None)
    assert client.get("/api/reports/ocr").json()["available"] is False
    index = upload(client, png())["ledger_index"]
    [report] = client.get("/api/reports").json()
    assert report["ocr"]["available"] is False and "no disponible" in report["ocr"]["note"]
    page = client.get(f"/api/reports/{index}/pages/1")
    assert page.status_code == 200 and page.headers["content-type"] == "image/png"


def test_ocr_text_and_its_confidence_are_signed_with_the_original(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "tesseract.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(ocr, "find_tesseract", lambda configured=None: str(fake))
    monkeypatch.setattr(ocr, "version", lambda executable: "tesseract 5.5.0")
    monkeypatch.setattr(ocr, "ocr_image", lambda executable, image: ("Hemoglobina 13,9", 42.0, 2))
    body = upload(client, png())
    assert body["low_confidence_pages"] == [1]
    [report] = client.get("/api/reports").json()
    [page] = report["ocr"]["pages"]
    assert page == {
        "page": 1, "text": "Hemoglobina 13,9", "confidence": 42.0, "words": 2,
        "low_confidence": True,
        "deidentification": {"redactions": 0, "verified": True, "remaining": []},
    }
    assert report["ocr"]["engine"] == "tesseract 5.5.0"


def test_a_report_is_not_a_reading(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """El texto de un informe no entra en el análisis: no hay lectura que analizar."""
    monkeypatch.setattr(ocr, "find_tesseract", lambda configured=None: None)
    upload(client, png())
    assert get_store().query("crew-01") == []
    # Pero es un registro real: un cambio de escenario simulado no lo puede tirar.
    replace = client.post(
        "/api/simulate", params={"scenario": "nominal", "days": 1, "replace": "true"}
    )
    assert replace.status_code == 409


def test_a_changed_original_is_refused_and_caught_by_verification(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "find_tesseract", lambda configured=None: None)
    index = int(str(upload(client, png())["ledger_index"]))
    store = get_store()
    with Session(store.engine) as session:
        row = session.get(ImagingBlobRow, index)
        assert row is not None
        row.data = png()[:-1] + b"\x00"
        session.commit()
    assert client.get(f"/api/reports/{index}/pages/1").status_code == 409
    assert not store.verify_integrity().ok


def test_unsupported_media_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/reports", params={"kind": "otro", "recorded_by": "CMO"},
        content=b"hola", headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 415


def text_pdf(line: str, repeat: int = 6) -> bytes:
    """Un PDF mínimo con capa de texto real (Helvetica), escrito a mano: sin dependencias."""
    stream = "BT /F1 10 Tf 40 780 Td 14 TL " + " ".join(
        f"({line}) Tj T*" for _ in range(repeat)
    ) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode("latin-1")
    return out


def test_a_pdf_with_text_is_read_not_ocred(monkeypatch: pytest.MonkeyPatch) -> None:
    """Polaris: un PDF que ya trae texto no se OCR-iza. Sin tesseract, se lee igual."""
    def no_ocr(executable: str, image: Image.Image) -> tuple[str, float, int]:
        raise AssertionError("no se debía OCR-izar")

    monkeypatch.setattr(ocr, "ocr_image", no_ocr)
    data = text_pdf("Hemoglobina 13,9 g/dL  Leucocitos 6,2 x10^3/uL")
    [page] = ocr.read(data, "application/pdf", None)
    assert "Hemoglobina 13,9" in page.text
    assert page.confidence is None and not page.low_confidence


# --------------------------------------------------------------------------- #
# Des-identificación (portada de Polaris `deid.py` y `borde.py`)
# --------------------------------------------------------------------------- #

REPORT = """Paciente: María José Pérez Gómez   NHC: 00123456
DNI 12345678Z  Tel. 612345678  correo maria.perez@ejemplo.es
Fecha de nacimiento: 03/04/1985
Domicilio: C/ Mayor 12, 3ºB, Madrid
Fecha de extracción: 12/09/2026
Hemoglobina 13,9 g/dL   Leucocitos 6,2 x10^3/µL
Firmado por: Dra. Ana López"""


def test_identifiers_go_and_clinical_content_stays() -> None:
    result = deid.deidentify(REPORT)
    assert result.verified
    for secret in ("María", "Pérez", "00123456", "12345678Z", "612345678", "ejemplo.es",
                   "1985", "Mayor", "Ana", "López"):
        assert secret not in result.text, secret
    # Lo clínico y las etiquetas se quedan. La fecha de la analítica, no: el original de Polaris
    # (commit e3b588d, adoptado el 2026-10-01) enmascara todas las fechas.
    for kept in ("Paciente: [REDACTADO]", "Hemoglobina 13,9 g/dL", "Firmado por: [REDACTADO]"):
        assert kept in result.text, kept
    assert result.text.count("\n") == REPORT.count("\n")  # no se funden líneas


def test_a_title_is_part_of_the_name() -> None:
    """Si la etiqueta se comía el "Dra.", el nombre quedaba a la vista y sin etiqueta."""
    assert "López" not in deid.deidentify("Firmado por: Dra. Ana López").text
    assert "López" not in deid.deidentify("Revisado por la Dra. Ana López.").text


def test_an_evasion_with_invisible_characters_never_shows_the_identifier() -> None:
    """Un carácter de anchura cero dentro del DNI: el original normaliza antes y lo enmascara.
    Si no lo reconociera, la revalidación retendría el texto; en ningún caso sale el DNI."""
    result = deid.deidentify("DNI 1234​5678Z")
    assert "5678Z" not in result.text
    assert (result.verified and "[REDACTADO]" in result.text) or result.text == ""


def test_the_signed_text_is_the_deidentified_one(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "tesseract.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(ocr, "find_tesseract", lambda configured=None: str(fake))
    monkeypatch.setattr(ocr, "version", lambda executable: "tesseract 5.5.0")
    monkeypatch.setattr(ocr, "ocr_image", lambda executable, image: (REPORT, 91.0, 40))
    upload(client, png())
    [report] = client.get("/api/reports").json()
    [page] = report["ocr"]["pages"]
    assert "12345678Z" not in page["text"] and "Hemoglobina 13,9" in page["text"]
    assert page["deidentification"] == {"redactions": 9, "verified": True, "remaining": []}
    audit = client.get("/api/audit", params={"limit": 5})
    assert audit.status_code == 200
    assert "12345678Z" not in audit.text  # tampoco en el registro que se audita


def test_two_masked_lines_hide_both_identifiers() -> None:
    """El original funde dos líneas enmascaradas seguidas; lo que importa es que no quede nada."""
    text = deid.deidentify("maria@ejemplo.es\n612345678").text
    assert "ejemplo" not in text and "612345678" not in text and "[REDACTADO]" in text


def test_a_name_with_a_title_mid_sentence_is_masked_on_top_of_polaris() -> None:
    """Regla de EMMA encima del original, que deja "la Dra. Ana Lopez" a la vista."""
    result = deid.deidentify("Revisado por la Dra. Ana López.")
    assert "Ana" not in result.text and result.verified


# Familiar nombrado (regla de EMMA, 2026-10-07): se tapa el nombre y se queda el parentesco.
# Las salidas van sin tildes: el original las quita antes de que la regla mire el texto.


@pytest.mark.parametrize(
    ("text", "kept", "secrets"),
    [
        ("Acude acompañado de su hermana Lucía Fernández.", "su hermana [REDACTADO].",
         ("Luc", "Fern")),
        ("Persona de aviso: su padre, Tomás Pérez", "su padre, [REDACTADO]", ("Tom", "rez")),
        ("Su madre Carmen refiere fiebre.", "Su madre [REDACTADO] refiere fiebre.", ("Carmen",)),
        ("Vive con sus hijos Ana y Luis Ortega en Houston.", "sus hijos [REDACTADO] en Houston.",
         ("Ana", "Luis", "Ortega")),
        ("Avisar a la tía Paloma.", "la tia [REDACTADO].", ("Paloma",)),
        ("Su cuñado Íñigo de la Torre le acompaña.", "Su cunado [REDACTADO] le", ("igo", "Torre")),
        ("Con su abuela materna, Rosa M. Gil-Soto.", "abuela materna, [REDACTADO].",
         ("Rosa", "Gil", "Soto")),
        ("Vive con su esposo (Javier Molina).", "su esposo ([REDACTADO]).", ("Javier", "Molina")),
        # Sin determinante hace falta nombre y apellido.
        ("Hermano: Andrés Molina Prieto, donante compatible.",
         "Hermano: [REDACTADO], donante compatible.", ("Andr", "Molina", "Prieto")),
        ("Vive con su mujer Ana y dos hijos.", "su mujer [REDACTADO] y dos hijos.", ("Ana",)),
        # La etiqueta del campo siguiente no es un apellido.
        ("Avisar a su madre Carmen Servicio: Urgencias", "su madre [REDACTADO] Servicio: Urgencias",
         ("Carmen",)),
        ("Su mamá Carmen le acompaña.", "Su mama [REDACTADO] le", ("Carmen",)),
        # Un apellido con sufijo de término médico ("-oma") no corta el nombre.
        ("Acude con su hermana Lucía Coloma.", "su hermana [REDACTADO].", ("Luc", "Coloma")),
        ("Madre: Carmen Poma", "Madre: [REDACTADO]", ("Carmen", "Poma")),
        # Un apellido que también es un estado ("Mayor") no corta el nombre.
        ("La madre Nuria Colón Mayor.", "La madre [REDACTADO].", ("Nuria", "Colon", "Mayor")),
    ],
)
def test_a_named_relative_is_masked_and_the_kinship_stays(
    text: str, kept: str, secrets: tuple[str, ...]
) -> None:
    result = deid.deidentify(text)
    assert result.verified and result.redactions >= 1
    assert kept in result.text, result.text
    for secret in secrets:
        assert secret not in result.text, secret


@pytest.mark.parametrize(
    "text",
    [
        "Madre con Diabetes Mellitus tipo 2. Padre fallecido de Infarto.",
        "Madre: Diabetes. Padre: Infarto Agudo. Hermano: Vitiligo.",
        "Su abuelo Parkinson, su tia Glaucoma y su prima Paracetamol.",
        "El padre Fallecido. La madre Viva.",
        "Enfermedad de Parkinson en la madre. Tratamiento: Levodopa.",
        "Acude con su madre.\nParacetamol 1 g",
        "Ingresa en el Hospital Madre Teresa de Calcuta, en la Calle Hermanos Pinzon Soto.",
        "Ecografia de la Mama Derecha Sin Hallazgos.",
        "Sus padres Fallecidos. Hermanos: Dos Sanos.",
        "Paciente mujer Remitida Desde Urgencias.",
    ],
)
def test_what_follows_a_kinship_term_and_is_not_a_name_stays(text: str) -> None:
    """Antecedentes, epónimos, fármacos, otra frase y centros: nada de eso se tapa de más."""
    result = deid.deidentify(text)
    assert result.verified
    assert (result.text, result.redactions) == (text, 0)


def test_a_clinical_word_ends_the_name_of_the_relative() -> None:
    result = deid.deidentify("Su abuelo materno Tomás Diabetes tipo 2.")
    assert result.text == "Su abuelo materno [REDACTADO] Diabetes tipo 2."


def test_a_hyphenated_surname_half_masked_by_polaris_goes_entirely() -> None:
    """Polaris tapa "Pérez" en "Pérez-Gómez"; el guion une la marca con el resto del apellido."""
    result = deid.deidentify("Acude con su madre María José Pérez-Gómez hoy.")
    assert result.text == "Acude con su madre [REDACTADO] hoy."


# El nombre DELANTE del parentesco (regla de EMMA, 2026-10-20): "con Rosa Beltrán, su cuñada".


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Acude a la consulta con Rosa Beltrán, su cuñada.",
         "Acude a la consulta con [REDACTADO], su cunada."),
        ("Viene con Pedro, mi hermano.", "Viene con [REDACTADO], mi hermano."),
        ("Rosa Beltrán (su madre) acude.", "[REDACTADO] (su madre) acude."),
        ("Viene con Rosa Beltrán, cuñada del paciente.",
         "Viene con [REDACTADO], cunada del paciente."),
        ("Rosa Beltrán, la cuñada de la paciente, firma.",
         "[REDACTADO], la cunada de la paciente, firma."),
        ("María José Pérez-Gómez, su madre, refiere dolor.",
         "[REDACTADO], su madre, refiere dolor."),
        ("Juan de la Cruz Ortega, su padre.", "[REDACTADO], su padre."),
        ("Ana y Luis Ortega, sus hijos, la visitan.", "[REDACTADO], sus hijos, la visitan."),
        ("Avisar a Íñigo Sáez, su suegro materno.", "Avisar a [REDACTADO], su suegro materno."),
        # Lo que abre la frase no es parte del nombre y se queda.
        ("Hoy Rosa Beltrán, su cuñada, refiere.", "Hoy [REDACTADO], su cunada, refiere."),
        # Un nombre de pila suelto, en mitad de la frase y tras "con", "a", "de" de "acompañada"…
        ("Acompañada de Lucía, su hermana.", "Acompanada de [REDACTADO], su hermana."),
        ("Acude con Inés, su nuera, y de Tomás, su hijo.",
         "Acude con [REDACTADO], su nuera, y de [REDACTADO], su hijo."),
        # Ya sin tildes (el original las quita antes que la regla) y con las dos marcas.
        ("Con Rosa Beltran, su cunada.", "Con [REDACTADO], su cunada."),
        # Meses y días que también son nombres de pila no se quitan como inicio de frase.
        ("Julio Pérez, su padre, acude.", "[REDACTADO], su padre, acude."),
        ("Acude con Abril, su hija.", "Acude con [REDACTADO], su hija."),
        # Lo que dejó Polaris tras tapar la primera parte del apellido.
        ("Viene con María Pérez-Gómez, su madre.", "Viene con [REDACTADO], su madre."),
        ("Acude con Pérez-Gómez, su madre.", "Acude con [REDACTADO], su madre."),
        ("Acude con Pérez Gómez, su madre.", "Acude con [REDACTADO], su madre."),
        ("Acompañados de Lucía, su hermana.", "Acompanados de [REDACTADO], su hermana."),
        ("Revisión Rosa Beltrán, su cuñada, acude.", "Revision [REDACTADO], su cunada, acude."),
    ],
)
def test_a_name_before_its_kinship_is_masked_and_the_kinship_stays(
    text: str, expected: str
) -> None:
    result = deid.deidentify(text)
    assert result.verified and result.redactions >= 1
    assert result.text == expected


@pytest.mark.parametrize(
    "text",
    [
        "Ademas, su madre tiene asma.",
        "Diabetes Mellitus, su madre tambien.",
        "Hipertension Arterial, su padre tambien.",
        "Fractura de Colles, su madre tambien.",
        "Enfermedad de Crohn, su padre.",
        "Antecedentes Familiares, su madre tiene asma.",
        "Antecedentes: Asma, su madre.",
        "Hospital Clinico, su centro de referencia.",
        "Hospital Clinico, su madre ingreso alli.",
        "Centro de Salud Las Rozas, su madre trabaja alli.",
        "Vive en la plaza San Juan, su madre tambien.",
        "Vive en Madrid, su madre en Sevilla.",
        "Acude a Urgencias, su madre le trae.",
        "Remitida por Medicina Interna, la madre lo pide.",
    ],
)
def test_what_precedes_a_kinship_and_is_not_a_name_stays(text: str) -> None:
    """Lo clínico, lo que abre la frase, centros, calles y lugares delante de ", su madre"."""
    result = deid.deidentify(text)
    assert result.verified
    assert (result.text, result.redactions) == (text, 0)


@pytest.mark.parametrize(
    "text",
    [
        # Un nombre de pila suelto al principio de la frase: la mayúscula puede ser "Además".
        "Lucia, su hermana, la acompana.",
        # Sin posesivo ni "del paciente", la aposición no se ancla a la persona.
        "Rosa Beltran, cunada.",
        # Mayúsculas sostenidas: ahí van también HTA, IAM, EPOC.
        "ROSA BELTRAN, SU CUNADA",
        # Una profesión no es un parentesco: el personal sanitario se tapa con su tratamiento.
        "Ana Lopez, su medica.",
        # Una palabra de la lista clínica descarta el tramo entero: un apellido epónimo, o un
        # nombre enumerado tras una enfermedad.
        "Ana Graves, su madre, acude.",
        "Visita de Parkinson y Rosa Beltran, su cunada.",
    ],
)
def test_a_name_before_its_kinship_that_needs_ner_is_a_declared_limit(text: str) -> None:
    """Límites declarados (`_mask_relatives`): sin la capa NER, esto sale tal cual."""
    result = deid.deidentify(text)
    assert result.verified and result.text == text


def test_a_professional_before_the_relation_is_masked_by_the_title_rule() -> None:
    """Con tratamiento, el nombre del profesional ya lo tapa la regla del tratamiento."""
    assert deid.deidentify("Dr. Ramírez, su médico.").text == "[REDACTADO], su medico."


def test_a_place_after_a_is_masked_too_and_that_is_declared() -> None:
    """De más, declarado: un lugar tras "a" delante de ", su hermano" se toma por un nombre."""
    assert deid.deidentify("Trasladado a Bilbao, su hermano vive alli.").text == (
        "Trasladado a [REDACTADO], su hermano vive alli."
    )


def test_if_a_named_relative_is_still_seen_the_text_is_withheld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falla cerrado: si la primera pasada no tapa y la revalidación lo ve, el texto no sale."""
    real = deid._mask_relatives
    calls = 0

    def forgetful(text: str) -> tuple[str, int]:
        nonlocal calls
        calls += 1
        return (text, 0) if calls == 1 else real(text)

    monkeypatch.setattr(deid, "_mask_relatives", forgetful)
    result = deid.deidentify("Acude con su hermana Lucía Fernández.")
    assert result.text == "" and not result.verified
    assert result.remaining == ("queda un familiar nombrado",)


def test_a_text_that_does_not_verify_is_withheld(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si el original dice que no verifica, el adaptador no enseña nada (falla cerrado)."""
    original = deid._original()
    monkeypatch.setattr(
        original, "de_identificar_verificado",
        lambda text, **_: (None, 1, False, "quedan identificadores"),
    )
    result = deid.deidentify("DNI 12345678Z")
    assert result.text == "" and not result.verified
    assert result.remaining == ("quedan identificadores",)


def test_polaris_revalidation_catches_what_its_mask_missed(monkeypatch: pytest.MonkeyPatch) -> None:
    """La revalidación de la copia: si el enmascarado dejara un DNI, el texto no sale."""
    original = deid._original()
    monkeypatch.setattr(original, "de_identificar", lambda text, **_: (text, 0))
    masked, _count, verified, _reason = original.de_identificar_verificado("DNI 12345678Z")
    assert masked is None and not verified


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("Cuenta: IBAN ES9121000418450200051332", "2100"),
        ("Pagado con tarjeta 4111 1111 1111 1111", "1111 1111"),
        ("Pasaporte nº: PAA123456", "PAA123456"),
        ("Extracción 2024-03-03T10:00:00Z", "2024-03-03"),
    ],
)
def test_emma_masks_what_polaris_lets_through(text: str, secret: str) -> None:
    """IBAN, tarjeta, pasaporte con etiqueta y fecha ISO con hora (reglas de EMMA, 2026-10-01)."""
    result = deid.deidentify(text)
    assert result.verified and secret not in result.text and "[REDACTADO]" in result.text
    assert result.redactions >= 1


def test_a_long_number_that_fails_its_checksum_is_left_alone() -> None:
    """Sin dígito de control, una cifra larga no es un IBAN ni una tarjeta: no se tapa."""
    text = "Lote 1234567890123 · referencia ES0000000000000000000000"
    assert deid.deidentify(text).text.endswith("ES0000000000000000000000")
    assert "1234567890123" in deid.deidentify(text).text


def test_without_the_ner_marker_the_layer_is_not_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Un entorno sin pesos comprobados no activa la capa: si no, se retendría cada informe."""
    monkeypatch.setenv("BTP_VENV_DEID", str(tmp_path))
    assert not deid.ner_ready()
    assert deid.deidentify("Hemoglobina 13,9 g/dL").verified


def test_with_the_ner_layer_its_spans_are_masked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """La capa NER simulada: lo que marca el modelo se tapa, encima de los patrones."""
    (tmp_path / "ner-ok.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BTP_VENV_DEID", str(tmp_path))
    # Al principio de la frase: lo que las reglas no tapan (límite declarado) y la capa sí.
    text = "Lucía, su hermana, le acompaña. Hemoglobina 13,9 g/dL"
    start = text.index("Lucía")
    monkeypatch.setattr(
        deid._original(), "_spans_ner", lambda texto: [(start, start + 5, "FAMILIAR", 0.9)]
    )
    result = deid.deidentify(text)
    assert result.verified and "Luc" not in result.text and "Hemoglobina 13,9" in result.text


def test_if_the_ner_layer_fails_the_text_is_withheld(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Pedida y caída, la capa no se salta en silencio: el texto no sale."""
    (tmp_path / "ner-ok.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BTP_VENV_DEID", str(tmp_path))
    original = deid._original()

    def down(texto: str) -> list[tuple[int, int, str, float]]:
        raise original.NERNoDisponible("modelo ausente")

    monkeypatch.setattr(original, "_spans_ner", down)
    result = deid.deidentify("Hemoglobina 13,9 g/dL")
    assert not result.verified and result.text == ""


@pytest.mark.live
def test_the_installed_ner_model_masks_a_relative() -> None:
    """Con el modelo del BSC instalado (`scripts/install_deid_ner.py`)."""
    if not deid.ner_ready():
        pytest.skip("capa NER sin instalar (el modelo no es público: hace falta HF_TOKEN)")
    result = deid.deidentify("Acude acompañado de su hermana Lucía Fernández Ortega.")
    assert result.verified and "Fernández" not in result.text
