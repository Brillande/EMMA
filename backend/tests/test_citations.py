"""Verificador de citas (portado de Polaris `verifica_citas.py`). Sin red: registros simulados.

Los casos de clasificación son los de Polaris (`tests/test_verifica_citas.py` y
`test_verifica_citas_datacite.py`): de ellos salen el DOI dentro de una cita larga, la dosis que
no es un DOI y los paréntesis legítimos de un DOI de Elsevier.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.evidence.citations import (
    EXISTS,
    NOT_FOUND,
    UNRESOLVABLE,
    classify,
    find_identifiers,
    verify,
)

ZENODO = "10.5281/zenodo.20005708"


@pytest.mark.parametrize(
    ("raw", "kind", "identifier"),
    [
        ("Pérez J, et al. Lancet Oncol. 2025;26(4):e123. doi:10.1016/j.annonc.2025.01.001",
         "doi", "10.1016/j.annonc.2025.01.001"),
        ("Smith A. Nature. 2024. https://doi.org/10.1038/s41586-024-07123-4",
         "doi", "10.1038/s41586-024-07123-4"),
        ("Estudio CONTACTO-1 (NCT07222267), fase II", "nct", "NCT07222267"),
        ("PMID: 38472196", "pmid", "38472196"),
        ("38472196", "pmid", "38472196"),
        ("el preprint (`10.5281/zenodo.20005708`)", "doi", ZENODO),
        ("**10.5281/zenodo.20005708**", "doi", ZENODO),
        ("doi:10.5281/zenodo.20005708.", "doi", ZENODO),
        ("[preprint](https://doi.org/10.5281/zenodo.20005708)", "doi", ZENODO),
        ("Lancet Oncol. doi:10.1016/S1470-2045(25)00001-9.", "doi",
         "10.1016/S1470-2045(25)00001-9"),
        # Un DOI que termina en un paréntesis emparejado lo conserva; uno suelto se quita.
        ("doi:10.1234/abcd(12)", "doi", "10.1234/abcd(12)"),
        ("(ver 10.5281/zenodo.20005708),", "doi", ZENODO),
    ],
)
def test_classify_as_polaris_does(raw: str, kind: str, identifier: str) -> None:
    assert classify(raw) == (kind, identifier)


@pytest.mark.parametrize("raw", ["Dosis de 10.5/mg cada 12h", "Ratio 10.25/kg en el protocolo"])
def test_a_dose_is_not_a_doi(raw: str) -> None:
    assert classify(raw)[0] != "doi"


def test_identifiers_are_found_in_a_long_text() -> None:
    text = (
        "Byra (2018), doi:10.5281/zenodo.1009146. Kerstman 2012 · PMID 22272509; "
        "a 5,5 mm, 12345 muestras."
    )
    assert find_identifiers(text) == {("doi", "10.5281/zenodo.1009146"), ("pmid", "22272509")}


def _registry(routes: dict[str, tuple[int, object]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, (status, body) in routes.items():
            if str(request.url).startswith(prefix):
                return httpx.Response(status, text=json.dumps(body))
        return httpx.Response(404, text="{}")
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_zenodo_doi_missing_from_crossref_is_not_fabricated() -> None:
    """El incidente de Polaris del 24-sep-2026: tres DOI reales de Zenodo acusados."""
    client = _registry({
        "https://api.datacite.org/dois/": (
            200, {"data": {"attributes": {"titles": [{"title": "x"}]}}}
        ),
    })
    [verdict] = verify(client, {("doi", ZENODO)})
    assert verdict.status == EXISTS and verdict.registry == "DataCite"


def test_only_three_noes_make_a_doi_fabricated() -> None:
    client = _registry({"https://doi.org/api/handles/": (404, {"responseCode": 100})})
    [verdict] = verify(client, {("doi", "10.9999/nope")})
    assert verdict.status == NOT_FOUND


def test_a_silent_registry_accuses_nobody() -> None:
    client = _registry({"https://api.crossref.org/works/": (503, {})})
    [verdict] = verify(client, {("doi", ZENODO)})
    assert verdict.status == UNRESOLVABLE


def test_a_pmid_with_an_error_record_does_not_exist() -> None:
    client = _registry({
        "https://eutils.ncbi.nlm.nih.gov/": (
            200, {"result": {"99999999": {"error": "cannot get document summary"}}}
        ),
    })
    [verdict] = verify(client, {("pmid", "99999999")})
    assert verdict.status == NOT_FOUND
