"""Respaldo de cifras en las citas (portado de Polaris `soporte_cita.py`). Sin red.

Los resúmenes de estos casos son fragmentos literales de los registros de PubMed citados.
"""

from __future__ import annotations

from app.evidence.claims import CLAIMS
from app.evidence.support import (
    DOUBTFUL,
    NOT_ASSESSABLE,
    NOT_SUPPORTED,
    SUPPORTS,
    check,
    numbers,
)

KERSTMAN = (
    "The incidence of space adaptation back pain among astronauts was determined to be 52% "
    "(382/728). Most of the affected astronauts reported mild pain (86%)."
)
SERLIN = "ratings of 1-4 correspond to mild pain, 5-6 to moderate pain, and 7-10 to severe pain."


def test_a_fraction_in_the_abstract_backs_both_figures() -> None:
    """Sin esto, "728" salía como no respaldado contra un resumen que dice "382/728"."""
    claim = "El dolor de espalda lo refirió el 52 % de 728 astronautas."
    assert check(claim, KERSTMAN)[0] == SUPPORTS


def test_a_range_in_the_abstract_backs_both_ends() -> None:
    assert check("De 7 a 10 es dolor intenso.", SERLIN)[0] == SUPPORTS


def test_a_figure_the_paper_does_not_say_is_caught() -> None:
    state, detail = check("El 61 % de 728 astronautas refirió dolor.", KERSTMAN)
    assert state == NOT_SUPPORTED and detail["missing_numbers"] == ["61"]


def test_an_acronym_the_abstract_does_not_name_is_doubtful() -> None:
    assert check("El 52 % con SANS.", KERSTMAN)[0] == DOUBTFUL


def test_nothing_to_check_is_said_so() -> None:
    assert check("Una frase sin cifras.", KERSTMAN)[0] == NOT_ASSESSABLE
    assert check("El 52 %.", "")[0] == NOT_ASSESSABLE


def test_polaris_noise_rules_hold() -> None:
    # Miles en español, años y la propia cita no son cifras de la frase.
    assert numbers("En 2012, 1.234 casos (PMID 22272509)") == ["1234"]
    # "CDK4/6" no es una fracción: la barra pegada a letras no aporta cifras.
    assert numbers("CDK4/6 inhibitors", "en") == []


def test_every_claim_cites_a_pmid_and_says_where_it_is_used() -> None:
    for claim in CLAIMS:
        assert claim.citation.startswith("PMID ") and claim.used_in
