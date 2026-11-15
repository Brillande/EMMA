"""Lo que lee la tripulacion esta en su idioma, sin nombres internos.

El resumen decia "Atencion en behavioral (watch)": media frase en castellano y
la otra media con las claves del codigo. El valor de los enums es la clave de la
API y se queda en ingles; el texto de pantalla, no.

Los nombres de los indicadores tambien: la frase dice el nombre en español del indicador
(`ingest/names_es.py`, rotulado como de EMMA o de Polaris, nunca de LOINC). El nombre
oficial de LOINC ("Heart rate") se queda en el codigo, en FHIR y en la API, donde la
correspondencia con el codigo que se declara lo exige.
"""

import datetime as dt

from app.advisor.recommendations import Advisor
from app.analysis.risk import CrewHealthStatus, DomainRisk, RiskEngine, RiskLevel
from app.ingest.codes import Domain
from app.ingest.fhir import observation
from tests.test_analysis import _deviation

NOW = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.UTC)


def _concerning_status(count: int = 12):
    return RiskEngine().assess("crew-01", [_deviation(4.5) for _ in range(count)])


def test_every_domain_and_level_has_a_crew_facing_name() -> None:
    for domain in Domain:
        assert domain.display and domain.display != "" and " " not in domain.display
    for level in RiskLevel:
        assert level.display


def test_the_summary_has_no_internal_names() -> None:
    status = _concerning_status()
    summary = Advisor().summarize(status)

    assert "cardiovascular" in summary
    assert "behavioral" not in summary
    for level in RiskLevel:
        assert f"({level.value})" not in summary, f"nivel interno {level.value} en pantalla"


def test_the_rationale_has_no_internal_names() -> None:
    status = _concerning_status()
    rationale = Advisor().recommend(status)[0].rationale

    for level in RiskLevel:
        assert f"({level.value})" not in rationale
    # El nombre del indicador, en español; el de LOINC no entra en la frase.
    assert "Frecuencia cardiaca" in rationale
    assert "Heart rate" not in rationale


def test_the_api_keys_stay_in_english() -> None:
    """El cambio es de pantalla, no de contrato: los clientes no se enteran."""
    status = _concerning_status()
    payload = Advisor().recommend(status)[0].to_dict()

    assert payload["domain"] == "cardiovascular"
    assert str(Domain.BEHAVIORAL) == "behavioral"
    assert str(RiskLevel.WATCH) == "watch"
    assert observation("heart-rate", 60.0, NOW, "crew-01", "t").code.display == "Heart rate"


def test_the_summary_does_not_name_a_lower_level_for_the_other_domains() -> None:
    """Lógica 2: «y 1 dominio(s) más bajo vigilancia» con el segundo dominio en crítico.

    «Vigilancia» es el nombre del nivel WATCH: la frase rebajaba de nivel, con su nombre, a un
    dominio que estaba en crítico.
    """
    domains = {
        domain: DomainRisk(domain=domain, score=0.0, level=RiskLevel.NOMINAL, drivers=())
        for domain in Domain
    }
    for domain in (Domain.CARDIOVASCULAR, Domain.BEHAVIORAL):
        domains[domain] = DomainRisk(
            domain=domain, score=80.0, level=RiskLevel.CRITICAL, drivers=("motivo",)
        )
    status = CrewHealthStatus(
        subject="crew-01", domains=domains, comms=None, isolation_factor=1.0,
        cumulative_dose_msv=0.0, dose_limit_msv=600.0,
    )
    summary = Advisor().summarize(status)

    assert RiskLevel.WATCH.display not in summary, summary
    assert "1 dominio(s) más fuera de nominal" in summary
