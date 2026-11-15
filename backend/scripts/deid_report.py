# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recall de la des-identificación de informes por tipo de entidad, con el banco de Polaris.

    .venv/Scripts/python.exe scripts/deid_report.py            # tabla por consola
    .venv/Scripts/python.exe scripts/deid_report.py --write    # y en el expediente de riesgos

Por qué existe: la única cifra que había ("se escapa 1 de 23") sale de `deid_eval.fugas`, que
busca el texto ENTERO de cada identificador en la salida. Un nombre tapado a medias ("su padre,
Tomás [REDACTADO]") no cuenta ahí como fuga, y tampoco se sabía qué tipo de dato falla. El banco
de Polaris trae otra medida, `puntuar`: por tipo de entidad, cuántas quedan tapadas enteras.
Necesita los tramos tapados, que da `app.reports.deid.masked_spans`.

Qué usa de la copia de Polaris (`polaris/tools/deid_eval.py`; el commit, en
`polaris/ADOPTADO.txt`; AGPL-3.0-or-later; se carga con `app.polaris.load`): `cargar_brat`,
`offsets_cuadran`, `puntuar` y `fugas`, tal cual. No se usa su `main` ni su `evaluar`: miden
`deid.detectar` de Polaris, sin las reglas de EMMA.

Qué NO mide: el corpus (`tests/data/deid_corpus/`) son informes inventados para esta prueba, y
las reglas de etiquetas y de parentesco de EMMA se añadieron tras medir con él. Dice si las
reglas tapan lo que se pensó que debían tapar; no valida la des-identificación con historias
clínicas reales.

La tabla del expediente (`compliance/risk-management-file.md`, H17) la escribe este guion entre
dos marcas; `tests/test_deid_corpus.py` falla si deja de coincidir con lo que se mide.
Herramienta de desarrollo: sin red, y no viaja en el producto.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app import polaris  # noqa: E402
from app.reports import deid  # noqa: E402

CORPUS = BACKEND / "tests" / "data" / "deid_corpus"
RISK_FILE = BACKEND.parent / "compliance" / "risk-management-file.md"
BEGIN = "<!-- deid-report:inicio (lo escribe backend/scripts/deid_report.py --write) -->"
END = "<!-- deid-report:fin -->"


def measure() -> dict[str, Any]:
    """Las cifras del banco de Polaris sobre el corpus, con y sin las reglas de EMMA."""
    bench = polaris.load("deid_eval")
    docs = bench.cargar_brat(str(CORPUS))
    if not docs:
        raise SystemExit(f"sin documentos anotados en {CORPUS}")
    mismatched = bench.offsets_cuadran(docs)
    if mismatched:
        raise SystemExit(f"{mismatched} anotaciones no cuadran con su texto: no se mide")

    emma = [list(deid.masked_spans(text)) for _id, text, _gold in docs]
    only_polaris = [list(deid.masked_spans(text, emma_rules=False)) for _id, text, _gold in docs]
    # Un informe retenido cuenta como tapado entero: se da aparte para que no infle el recall.
    withheld = [
        doc[0] for doc, spans in zip(docs, emma, strict=True)
        if any(span.layer == deid.LAYER_WITHHELD for span in spans)
    ]
    outputs = [deid.deidentify(text).text for _id, text, _gold in docs]
    return {
        "documents": len(docs),
        "withheld": withheld,
        "emma": bench.puntuar(docs, emma),
        "polaris": bench.puntuar(docs, only_polaris),
        "leaks": bench.fugas(docs, outputs),
    }


def _ratio(covered: int, total: int) -> str:
    return f"{covered} de {total} ({100 * covered / total:.0f} %)"


def render(measured: dict[str, Any]) -> list[str]:
    """La tabla en Markdown, sin fecha: es lo que la prueba compara con el expediente."""
    emma, only_polaris, leaks = measured["emma"], measured["polaris"], measured["leaks"]
    lines = [
        "| Tipo de entidad (etiqueta del corpus) | Anotadas | Tapadas enteras, EMMA "
        "| Tocadas, EMMA | Tapadas enteras, solo Polaris |",
        "|---|---|---|---|---|",
    ]
    for label, row in emma["por_etiqueta"].items():
        alone = only_polaris["por_etiqueta"][label]
        lines.append(
            f"| `{label}` | {row['n']} | {_ratio(row['cubiertas'], row['n'])} "
            f"| {row['parciales']} | {_ratio(alone['cubiertas'], alone['n'])} |"
        )
    total = emma["entidades"]
    covered = sum(row["cubiertas"] for row in emma["por_etiqueta"].values())
    touched = sum(row["parciales"] for row in emma["por_etiqueta"].values())
    alone_covered = sum(row["cubiertas"] for row in only_polaris["por_etiqueta"].values())
    lines += [
        f"| **Total** | {total} | **{_ratio(covered, total)}** | {touched} "
        f"| {_ratio(alone_covered, only_polaris['entidades'])} |",
        "",
        f"Precisión por carácter (cuánto de lo tapado era un identificador anotado): "
        f"{emma['precision_caracter']:.3f} con EMMA, {only_polaris['precision_caracter']:.3f} "
        "solo Polaris.",
        f"Fugas literales en la salida real (`deid_eval.fugas`): {leaks['fugas']} de "
        f"{leaks['entidades']}.",
        f"Informes: {measured['documents']}; retenidos enteros por no verificar: "
        f"{len(measured['withheld'])}.",
    ]
    return lines


def write(lines: list[str], today: date) -> None:
    """Cambia en el expediente lo que hay entre las dos marcas; si faltan, no escribe."""
    document = RISK_FILE.read_bytes().decode("utf-8")
    if document.count(BEGIN) != 1 or document.count(END) != 1:
        raise SystemExit(f"{RISK_FILE.name} no tiene las marcas de la tabla (una vez cada una)")
    # El fichero conserva sus saltos de línea: cambiarlos reescribiría el expediente entero.
    newline = "\r\n" if "\r\n" in document else "\n"
    head, rest = document.split(BEGIN)
    _old, tail = rest.split(END)
    block = newline.join(["", f"Medido el {today.isoformat()}.", "", *lines, ""])
    RISK_FILE.write_bytes((head + BEGIN + block + END + tail).encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="actualiza la tabla del riesgo H17")
    args = parser.parse_args()
    # Las etiquetas y los acentos caben en cp1252, pero una consola con otra página de códigos
    # no debe tumbar la medida.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    measured = measure()
    lines = render(measured)
    print("\n".join(lines))
    if measured["withheld"]:
        print("RETENIDOS (cuentan como tapados enteros): " + ", ".join(measured["withheld"]))
    if args.write:
        write(lines, date.today())
        print(f"escrito en {RISK_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
