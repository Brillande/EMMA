# SPDX-License-Identifier: AGPL-3.0-or-later
"""Guarda el registro de PubMed de cada fuente que cita EMMA, para graduar su evidencia sin red.

    .venv/Scripts/python.exe scripts/grade_sources.py

Lee los PMID citados en los protocolos de ecografía, en la evidencia (`app/evidence/links.py`) y
en el registro único de fichas, pide su registro a NCBI (efetch) y guarda solo lo que usa
`app/evidence/tier.py`: los tipos de publicación y los descriptores MeSH, con la fecha de consulta.
Es lo único que toca la red; la aplicación y la suite leen el fichero guardado.

Sale por la puerta de salida (`app/core/egress.py`, propósito `citations`): lista blanca, modo sin
red y freno HALT. Con `EMMA_OFFLINE=true` se niega y lo dice.

Un PMID cuya respuesta no trae su artículo (NCBI caído, un 429, un PMID retirado) no se guarda
como registro vacío: un registro vacío gradúa «desconocido» con fecha, que parece leído y no lo
está. Se dice cuál, se conserva el registro que ya hubiera y el guion termina con código 1.

Derivado de Polaris `tools/tier_evidencia.py::_fetch_pubmed` (@ 7bf47257, AGPL-3.0-or-later,
© 2026 la autora de Polaris). Cambios: la puerta de salida de EMMA (httpx) en vez de `curl`, un
fichero en vez de una caché de estado (que guarda los tipos y los MeSH leídos con las mismas
expresiones que `senales_desde_registro()`), y una respuesta sin el artículo pedido no se guarda.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import egress  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.evidence import links, registry  # noqa: E402
from app.evidence.tier import _PMID, TIERS_FILE  # noqa: E402
from app.imaging.protocols import PROTOCOLS  # noqa: E402

EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def cited_pmids() -> list[str]:
    texts = [source for protocol in PROTOCOLS.values() for source in protocol.sources]
    texts += [str(value) for value in vars(links).values() if isinstance(value, str)]
    texts += [repr(value) for value in vars(links).values() if not isinstance(value, str)]
    # Las fichas del registro unico llevan el PMID en su campo, no siempre en el texto de la cita.
    texts += [f"PMID {ref.pmid}" for ref in registry.registry().values() if ref.pmid]
    return sorted({match.group(1) for text in texts for match in _PMID.finditer(text)})


def parse(pmid: str, xml: str) -> dict[str, object] | None:
    """Lo que gradúa `tier.py`, o `None` si la respuesta no es el artículo de ese PMID."""
    if "<PubmedArticle>" not in xml or not re.search(rf"<PMID[^>]*>{pmid}</PMID>", xml):
        return None
    return {
        "title": (re.findall(r"<ArticleTitle>(.*?)</ArticleTitle>", xml, re.S) or [""])[0],
        # Con la etiqueta de cierre, como `senales_desde_registro()` del original. Sin ella,
        # `<PublicationTypeList>` casaba como un tipo vacío y se comía el `<` del primer tipo de
        # verdad: el primero de cada registro se perdía (hasta la decimoctava ronda, §5.38.20).
        "publication_types": re.findall(
            r"<PublicationType[^>]*>([^<]*)</PublicationType>", xml
        ),
        "mesh": re.findall(r"<DescriptorName[^>]*>([^<]*)</DescriptorName>", xml),
        "retrieved": dt.date.today().isoformat(),
    }


def main() -> int:
    settings = get_settings()
    previous: dict[str, dict[str, object]] = {}
    if TIERS_FILE.exists():
        previous = json.loads(TIERS_FILE.read_text(encoding="utf-8"))["records"]
    records: dict[str, dict[str, object]] = {}
    failed: list[str] = []
    for pmid in cited_pmids():
        try:
            response = egress.get(
                settings, "citations", EFETCH,
                params={"db": "pubmed", "retmode": "xml", "id": pmid},
            )
            response.raise_for_status()
            record = parse(pmid, response.text)
        except egress.EgressBlocked as exc:
            # Sin red, modo seguro o freno HALT: no se escribe nada, ni a medias.
            print(f"No sale: {exc}", file=sys.stderr)
            return 2
        except httpx.HTTPError:
            record = None
        if record is None:
            failed.append(pmid)
            if pmid in previous:
                records[pmid] = previous[pmid]
        else:
            records[pmid] = record
        time.sleep(0.4)  # NCBI pide no pasar de 3 peticiones por segundo sin clave
    TIERS_FILE.write_text(
        json.dumps({"source": EFETCH, "records": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(records)} registros en {TIERS_FILE}")
    if failed:
        print(f"Sin el artículo en la respuesta (no se guardan): {', '.join(failed)}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
