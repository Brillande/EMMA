# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cada cifra que EMMA atribuye a un artículo está en su resumen. Con red: marcada `live`.

    .venv/Scripts/python.exe -m pytest -m live tests/test_citation_support_live.py

Las afirmaciones están declaradas en `app/evidence/claims.py`. Método de Polaris
(`tools/soporte_cita.py`): se baja el resumen de PubMed y se cotejan cifras y siglas.

Licencia y origen (AGPL §5a): de Polaris aquí solo es el método; este fichero no contiene código
suyo. Ejerce `app/evidence/support.py`, que declara en su cabecera qué llama de la copia
(`polaris/tools/soporte_cita.py`) y qué sigue adaptado a mano.
"""

from __future__ import annotations

import re
import time

import httpx
import pytest

from app.evidence.claims import CLAIMS
from app.evidence.support import NOT_SUPPORTED, check, clean_source

EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def abstract(client: httpx.Client, pmid: str) -> str:
    xml = client.get(EFETCH, params={"db": "pubmed", "retmode": "xml", "id": pmid}).text
    parts = re.findall(r"<ArticleTitle[^>]*>(.*?)</ArticleTitle>", xml, re.S)
    parts += re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", xml, re.S)
    return clean_source(re.sub(r"<[^>]+>", " ", " ".join(parts)))


@pytest.mark.live
def test_every_figure_emma_attributes_to_a_paper_is_in_its_abstract() -> None:
    unsupported = []
    with httpx.Client(timeout=30) as client:
        for claim in CLAIMS:
            pmid = claim.citation.split()[-1]
            state, detail = check(claim.text, abstract(client, pmid))
            if state == NOT_SUPPORTED:
                unsupported.append(f"{claim.citation} ({claim.used_in}): {detail}")
            time.sleep(0.5)  # NCBI: no más de 3 peticiones por segundo sin clave
    assert not unsupported, "\n".join(unsupported)
