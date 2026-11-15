"""Contramedidas en investigación: a la vista, con su fuente, y sin ofrecerse (§5.36.15).

La base de conocimiento (§4, §3.2) y la conversación de ideación nombran contramedidas que hoy
se estudian y no se adoptan a bordo: la realidad virtual para el aislamiento, la presión negativa
en la parte inferior del cuerpo, los brazaletes de muslo y la gravedad artificial. EMMA las
enseña en un fichero aparte (`data/countermeasures_research.json`). Estas pruebas fijan las dos
mitades del trato:

- **A la vista y con fuente.** Cada entrada tiene su frase literal, su página y su ficha del
  registro; un peligro RIDGE inventado, una entrada sin frase, una fuente sin lectura declarada o
  un texto con tono de orden no se cargan.
- **Sin ofrecerse jamás.** Ningún módulo salvo la ruta importa el cargador; la huella de reglas
  sigue resumiendo solo la biblioteca (`rules_version` idéntico); ningún id coincide con la
  biblioteca; ninguna recomendación —del asesor, dominio por dominio y nivel por nivel, ni de la
  cabina, ni del estado servido— nombra una; y adoptar o declinar una se rechaza.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.advisor.recommendations import Advisor
from app.analysis.risk import CrewHealthStatus, DomainRisk, RiskLevel
from app.core import versioning
from app.environment.habitat import PARAMETERS
from app.evidence import registry
from app.evidence import research_countermeasures as research
from app.evidence.research_countermeasures import ResearchError, validate
from app.ingest.codes import Domain, Ridge
from app.text_guard import check

APP = Path(research.__file__).resolve().parents[1]
RAW: dict[str, Any] = json.loads(research.RESEARCH_PATH.read_text(encoding="utf-8"))
# Los únicos sitios que pueden leer este módulo: la ruta que lo sirve y el propio módulo.
# La ruta que lo sirve, y el arranque, que solo valida el fichero (`main.check_read_files`): ni el
# motor ni el asesor.
ALLOWED_IMPORTERS = {"api/countermeasures.py", "main.py"}


def _raw(**override: Any) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    raw.update(override)
    return raw


def _with_entry(**override: Any) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    raw["entries"][0].update(override)
    return raw


# --------------------------------------------------------------------------- #
# Lo leído: con fuente o no se sirve
# --------------------------------------------------------------------------- #


def test_the_research_file_loads_the_four_the_context_names_and_two_more() -> None:
    ids = research.ids()
    # Las cuatro que nombran la base de conocimiento y la ideación, y las dos que el informe del
    # SANS pone en la misma frase que los brazaletes y la presión negativa.
    assert ids == {
        "research-vr-relaxing-environments", "research-thigh-cuffs", "research-lbnp",
        "research-centrifuge-artificial-gravity", "research-kaatsu-modified",
        "research-impedance-threshold-device",
    }
    ridges = {item["id"]: item["ridge"] for item in RAW["entries"]}
    assert ridges["research-vr-relaxing-environments"] == "isolation"
    assert {ridges[ident] for ident in ids - {"research-vr-relaxing-environments"}} == {"gravity"}


def test_every_quote_points_to_a_registry_card_whose_reading_is_declared() -> None:
    for item in RAW["entries"]:
        assert item["quotes"], item["id"]
        for quote in item["quotes"]:
            assert quote["ref"] in RAW["sources"], item["id"]
            registry.get(quote["ref"])
            assert quote["where"].strip() and quote["quote"].strip()
    assert research.cited_refs() == {
        "nasa-body-in-space-2022", "hrp-sans-evidence-report", "nasa-bed-rest-agbresa",
        # El artículo de resultados de AGBRESA (decimoctava ronda, U15, 2026-10-26).
        "kramer-2021-agbresa",
    }


def test_the_status_says_research_and_never_flight_equipment_without_a_source() -> None:
    for item in RAW["entries"]:
        status = item["status"].lower()
        assert "investigación" in status or "estudi" in status, item["id"]
        # Lo que la fuente no dice del vuelo se dice, no se calla.
        assert item["flight_note"].strip(), item["id"]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (_raw(read_on="hacia octubre"), "read_on"),
        # Fechas que `fromisoformat` admite y la interfaz no pinta (`formatSourceDate`).
        (_raw(read_on="20261023"), "read_on"),
        (_raw(read_on="2026-W43-5"), "read_on"),
        (_raw(read_on="2026-13-40"), "read_on"),
        (_with_entry(ridge="fluids"), "RIDGE"),
        (_with_entry(quotes=[]), "sin frase"),
        (_with_entry(quotes=[{"ref": "nasa-body-in-space-2022", "where": "", "quote": "x"}]),
         "sin `ref`, `where` o `quote`"),
        (_with_entry(quotes=[{"ref": "osd-288", "where": "p. 1", "quote": "x"}]),
         "no se declara cuánto se leyó"),
        (_with_entry(status=" "), "falta `status`"),
        (_with_entry(flight_note=None), "falta `flight_note`"),
        (_with_entry(name="Administre la realidad virtual a diario"), "pauta u orden"),
        (_with_entry(status="Se recomienda usarla a bordo."), "pauta u orden"),
        (_raw(not_found=["Es la contramedida recomendada sin duda."]), "pauta u orden"),
        # La página bajo la frase y lo leído de cada fuente también los escribe EMMA.
        (_with_entry(quotes=[{"ref": "nasa-body-in-space-2022",
                              "where": "Se recomienda usarla a bordo.", "quote": "x"}]),
         "pauta u orden"),
        (_raw(sources={**RAW["sources"], "nasa-body-in-space-2022": {
            "extent": "partial", "what": "Se recomienda usarla a bordo."}}), "pauta u orden"),
        (_raw(read_not_included="una frase"), "lista de frases"),
        (_raw(entries=[]), "sin entradas"),
        (_raw(entries=[RAW["entries"][0], RAW["entries"][0]]), "repetido"),
        (_raw(sources={**RAW["sources"], "no-existe": {"extent": "full", "what": "x"}}),
         "no está en el registro"),
        (_raw(sources={**RAW["sources"], "osd-288": {"extent": "algo", "what": "x"}}),
         "cuánto se leyó"),
        # Una ficha declarada leída que ninguna frase cita no respalda nada.
        (_raw(sources={**RAW["sources"], "osd-288": {"extent": "full", "what": "x"}}),
         "ninguna frase cita"),
        # Formas rotas: se rechazan con su motivo, no con un 500 sin explicación.
        (_raw(sources=list(RAW["sources"])), "`sources`"),
        (_raw(sources={**RAW["sources"], "osd-288": "leído"}), "cuánto se leyó"),
        (_raw(entries=["research-x"]), "no es un objeto"),
        (_with_entry(quotes=["una frase suelta"]), "sin `ref`, `where` o `quote`"),
        # Un `extent` que no es texto no se puede buscar en la tabla (TypeError sin motivo).
        (_raw(sources={**RAW["sources"], "nasa-body-in-space-2022": {
            "extent": ["partial"], "what": "x"}}), "cuánto se leyó"),
        # El día propio de una fuente leída después: una fecha entera, y no antes que el fichero.
        (_raw(sources={**RAW["sources"], "kramer-2021-agbresa": {
            **RAW["sources"]["kramer-2021-agbresa"], "read_on": "20261026"}}), "AAAA-MM-DD"),
        (_raw(sources={**RAW["sources"], "kramer-2021-agbresa": {
            **RAW["sources"]["kramer-2021-agbresa"], "read_on": "2026-13-40"}}),
         "no es una fecha"),
        (_raw(sources={**RAW["sources"], "kramer-2021-agbresa": {
            **RAW["sources"]["kramer-2021-agbresa"], "read_on": "2026-10-22"}}), "anterior"),
    ],
)
def test_what_cannot_be_held_with_the_source_in_front_is_refused(
    raw: dict[str, Any], reason: str
) -> None:
    with pytest.raises(ResearchError, match=reason):
        validate(raw)


def test_a_file_that_is_not_an_object_is_refused_with_its_reason() -> None:
    # Y no como «falta `read_on`», que mandaría a buscar el fallo donde no está.
    with pytest.raises(ResearchError, match="tiene que ser un objeto"):
        validate([RAW])  # type: ignore[arg-type]


def test_an_id_that_clashes_with_the_library_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library_id = next(iter(countermeasures.library()))
    with pytest.raises(ResearchError, match="también están en la biblioteca"):
        validate(_with_entry(id=library_id), countermeasures.library())
    # Y la carga de verdad lo comprueba contra la biblioteca, sin que nadie se la pase.
    path = tmp_path / "research.json"
    path.write_text(json.dumps(_with_entry(id=library_id)), encoding="utf-8")
    monkeypatch.setattr(research, "RESEARCH_PATH", path)
    with pytest.raises(ResearchError, match="también están en la biblioteca"):
        research.read.__wrapped__()


def test_the_texts_emma_writes_do_not_read_as_medical_orders() -> None:
    texts = [research.NOTE, *RAW["not_found"], *RAW["read_not_included"]]
    texts += [item[field] for item in RAW["entries"] for field in research.AUTHORED]
    assert [(text, check(text)) for text in texts if check(text)] == []


# --------------------------------------------------------------------------- #
# Sin ofrecerse jamás
# --------------------------------------------------------------------------- #


def test_no_module_of_the_engine_imports_the_research_file() -> None:
    importers = set()
    for path in APP.rglob("*.py"):
        if path == Path(research.__file__):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or "", *(alias.name for alias in node.names)]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            if any("research_countermeasures" in name for name in names):
                importers.add(path.relative_to(APP).as_posix())
        # Tampoco por la ruta del fichero de datos.
        if "countermeasures_research.json" in path.read_text(encoding="utf-8"):
            importers.add(path.relative_to(APP).as_posix())
    assert importers == ALLOWED_IMPORTERS


def test_the_rules_fingerprint_still_summarises_only_the_library() -> None:
    rules = versioning.rules()
    # Los periodos de las rutinas entran en la huella desde la monitorización intensificada
    # (`routines`); los efectos y las contramedidas en investigación siguen fuera.
    assert set(rules) == {"parameters", "catalog", "habitat", "countermeasures_sha256", "routines"}
    assert rules["countermeasures_sha256"] == hashlib.sha256(
        countermeasures.LIBRARY_PATH.read_bytes()
    ).hexdigest()
    assert research.RESEARCH_PATH != countermeasures.LIBRARY_PATH
    text = json.dumps(rules, ensure_ascii=False)
    assert not any(ident in text for ident in research.ids())
    # Y la versión que declaran el estado y las alertas es la de esas reglas.
    assert versioning.rules_version() == f"reglas@{versioning.fingerprint(rules)}"


def test_no_research_id_is_in_the_library_or_can_be_fetched_from_it() -> None:
    assert not research.ids() & set(countermeasures.library())
    for ident in research.ids():
        with pytest.raises(KeyError):
            countermeasures.get(ident)


def _status(domain: Domain, level: RiskLevel) -> CrewHealthStatus:
    return CrewHealthStatus(
        subject="crew-01",
        domains={domain: DomainRisk(domain, 50.0, level, ("x",))},
        comms=None, isolation_factor=1.0, cumulative_dose_msv=0.0, dose_limit_msv=600.0,
        active_solar_event=None,
    )


def test_the_advisor_never_offers_one_in_any_domain_at_any_level() -> None:
    offered = {
        item.countermeasure.id
        for domain in Domain
        for level in RiskLevel
        for item in Advisor().recommend(_status(domain, level))
        if item.countermeasure is not None
    }
    assert offered, "el asesor tiene que ofrecer algo para que la prueba diga algo"
    assert not offered & research.ids()
    # Las dos puertas por las que la biblioteca da candidatas: por dominio y por parámetro de
    # cabina (la hipótesis de causa compartida).
    by_domain = {item.id for domain in Domain for item in countermeasures.for_domain(domain)}
    by_habitat = {item.id for key in PARAMETERS for item in countermeasures.for_habitat(key)}
    assert by_domain and by_habitat
    assert not (by_domain | by_habitat) & research.ids()


def test_the_state_names_none_and_adopting_or_declining_one_is_refused(
    client: TestClient,
) -> None:
    # co2-fatigue: el escenario que recomienda a la vez por dominio y por cabina. El asesor ya se
    # recorre entero arriba, dominio a dominio y nivel a nivel; aquí se mira el estado servido.
    client.post("/api/simulate", params={"scenario": "co2-fatigue", "days": 40, "crew_size": 1})
    body = client.get("/api/status").json()
    assert body["recommendations"], "el escenario tiene que recomendar algo"
    text = json.dumps(body, ensure_ascii=False)
    assert not [ident for ident in research.ids() if ident in text]
    for item in body["recommendations"]:
        ident = (item.get("countermeasure") or {}).get("id")
        assert ident is None or ident in countermeasures.library()
    reference = body["data"]["reference_time"]
    # Adoptar exige que estuviera recomendada en ese estado: 409. Basta una; cada intento
    # recalcula el estado.
    adopted = client.post(
        "/api/countermeasures/adopt",
        json={"subject": "crew-01", "countermeasure_id": "research-lbnp",
              "reference_time": reference, "adopted_by": "prueba"},
    )
    assert adopted.status_code == 409, adopted.text
    for ident in research.ids():
        declined = client.post(
            "/api/countermeasures/decline",
            json={"subject": "crew-01", "countermeasure_id": ident, "reference_time": reference,
                  "reason": "en investigación", "declined_by": "prueba"},
        )
        assert declined.status_code == 422
        assert "desconocida" in declined.json()["detail"]


# --------------------------------------------------------------------------- #
# La API
# --------------------------------------------------------------------------- #


def test_the_api_serves_them_apart_with_their_sources(client: TestClient) -> None:
    body = client.get("/api/countermeasures/research").json()
    assert body["offered"] is False
    assert body["note"] == research.NOTE
    assert [item["id"] for item in body["entries"]] == [item["id"] for item in RAW["entries"]]
    for item, raw in zip(body["entries"], RAW["entries"], strict=True):
        assert item["offered"] is False
        assert item["ridge_display"] == Ridge(item["ridge"]).display
        assert "family" not in item and "domain" not in item
        # Todas las frases, literales y en su orden: ninguna se pierde ni se reescribe.
        assert [(q["ref"], q["where"], q["quote"]) for q in item["quotes"]] == [
            (q["ref"], q["where"], q["quote"]) for q in raw["quotes"]
        ]
        assert {key: item[key] for key in research.AUTHORED} == {
            key: raw[key] for key in research.AUTHORED
        }
        for quote in item["quotes"]:
            ref = registry.get(quote["ref"])
            served = (quote["title"], quote["source"], quote["url"])
            assert served == (ref.title, ref.source, ref.url)
    assert set(body["sources"]) == research.cited_refs()
    assert body["not_found"] == RAW["not_found"]
    assert body["read_not_included"] == RAW["read_not_included"]
    assert body["read_on"] == RAW["read_on"]
    # Cada fuente, con el día de su lectura: el suyo si se leyó después (el artículo de resultados
    # de AGBRESA), el del fichero si no. Sin él, sus frases saldrían con un día que no es el suyo.
    assert {ref: source["read_on"] for ref, source in body["sources"].items()} == {
        ref: source.get("read_on", RAW["read_on"]) for ref, source in RAW["sources"].items()
    }
    assert body["sources"]["kramer-2021-agbresa"]["read_on"] == "2026-10-26"
    assert body["sources"]["nasa-bed-rest-agbresa"]["read_on"] == RAW["read_on"]
    # La biblioteca no las lleva, ni en la lista ni en sus grupos.
    library = client.get("/api/countermeasures").json()
    listed = {item["id"] for item in library["countermeasures"]}
    grouped = {ident for group in library["by_ridge"] for ident in group["countermeasures"]}
    assert not (listed | grouped) & research.ids()
