"""Radiación: el aviso de HERA, la fase del ciclo solar y el fin del refugio, como fuente (E8).

Decimosexta ronda: a bordo de Orion el aviso operacional lo da HERA (Hybrid Electronic Radiation
Assessor), con ficha propia, y EMMA no lo lee; la fase del ciclo solar 25 va como nota fechada de
NASA y NOAA, solo descriptiva, y la proyección de dosis sigue con tasa constante; y lo que una
fuente dice del fin del refugio se enseña como fuente, sin umbral de EMMA. Nada de esto entra en
`rules_version` ni en ningún nivel. `evidence/radiation_read.py`, `data/radiation_read.json`.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import radiation
from app.analysis.radiation import mission_projection
from app.api import routes
from app.core import versioning
from app.evidence import radiation_read, registry, testbeds
from app.evidence.radiation_read import RadiationReadError
from app.ingest.fhir import observation
from app.text_guard import check

RAW = json.loads(radiation_read.READ_PATH.read_text(encoding="utf-8"))
READ_ON = "2026-10-23"
# Las fuentes leídas otro día que la primera lectura (decimoctava ronda, U14: las gráficas de NOAA).
# Decimonovena ronda, U8: las diapositivas de 2019 y el informe de evidencia de 2016.
LATER_READING = {
    "noaa-swpc-solar-cycle-progression": "2026-10-26",
    "lee-2019-srag-ops": "2026-10-31",
    "ntrs-20160003870": "2026-11-01",
}
START = dt.date(2026, 11, 1)
T0 = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)


def _texts(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [text for value in node.values() for text in _texts(value)]
    if isinstance(node, list):
        return [text for value in node for text in _texts(value)]
    return []


# --------------------------------------------------------------------------- #
# Lo leído, y de dónde sale
# --------------------------------------------------------------------------- #


def test_the_three_readings_cite_registry_cards_read_that_day() -> None:
    described = radiation_read.describe()
    assert set(described) == {"onboard_warning", "solar_cycle", "shelter_exit"}
    cited = set()
    for entry in described.values():
        assert entry["read_on"] == READ_ON
        assert entry["quotes"]
        # Cada ficha una vez, entera, la del registro; en el orden de su primera frase.
        order = list(dict.fromkeys(item["ref"] for item in entry["quotes"]))
        assert entry["sources"] == [registry.cite(ref_id).to_dict() for ref_id in order]
        for item in entry["quotes"]:
            ref = registry.get(item["ref"])
            # La frase escrita en la nota de su ficha al leerla, el día en que se leyó.
            assert item["quote"] in (ref.notes or "") and item["read_on"] in (ref.notes or "")
            assert item["read_on"] == LATER_READING.get(ref.id, READ_ON)
            assert item["where"].strip()
            cited.add(ref.id)
    assert cited == radiation_read.cited_refs() == radiation.READINGS_REFS == {
        "nasa-orion-radiation-protection", "nasa-artemis1-radiation-research",
        "nasa-artemis2-eyes-on-sun", "nasa-noaa-solar-maximum-2024",
        "lowe-2025-sep-nowcasting-mars", "noaa-swpc-solar-cycle-progression",
        "lee-2019-srag-ops", "ntrs-20160003870",
    }


def test_hera_is_the_orion_instrument_not_the_ground_analog_and_emma_does_not_read_it() -> None:
    warning = radiation_read.describe()["onboard_warning"]
    assert warning["emma_reads_it"] is False
    assert "EMMA no lee HERA" in warning["text"]
    assert "no sustituye ese aviso" in warning["text"]
    refs = {item["ref"] for item in warning["quotes"]}
    # Ninguna es de las fichas del análogo terrestre que comparte siglas.
    assert not refs & testbeds.cited_refs()
    for ref_id in refs:
        assert "Hybrid Electronic Radiation Assessor" in (registry.get(ref_id).notes or "")
    # El aviso, en palabras de NASA: parte del sistema de precaución y aviso de la nave.
    assert any("Caution and Warning System" in item["quote"] for item in warning["quotes"])


def test_what_was_read_says_there_is_a_threshold_and_not_which_nor_when_to_leave() -> None:
    described = radiation_read.describe()
    warning = described["onboard_warning"]
    assert any("Radiation Console" in item["quote"] for item in warning["quotes"])
    assert "las diapositivas dicen que hay un umbral, no cuál" in warning["not_found"]
    assert "Sigue sin criterio de NASA" in described["shelter_exit"]["not_found"]


def test_the_module_cites_hera_with_its_cards_and_not_the_analog() -> None:
    doc = radiation.__doc__ or ""
    assert "Hybrid Electronic Radiation Assessor" in doc
    assert "Human Exploration Research Analog" in doc
    for ref_id in ("nasa-orion-radiation-protection", "nasa-artemis1-radiation-research",
                   "nasa-artemis2-eyes-on-sun"):
        assert f"`{ref_id}`" in doc
        registry.get(ref_id)


def test_the_solar_cycle_note_is_dated_and_says_it_is_a_2024_forecast() -> None:
    cycle = radiation_read.describe()["solar_cycle"]
    assert cycle["as_of"] == "2024-10-15" == registry.get("nasa-noaa-solar-maximum-2024").date
    assert "previsión de 2024, no una medida de hoy" in cycle["text"]
    assert "tasa constante" in cycle["scope"] and "no lee esta nota" in cycle["scope"]
    # Lo buscado y no encontrado se dice.
    assert "no se encontró" in cycle["not_found"]


def test_the_noaa_graphs_give_one_copied_figure_with_its_month_and_no_phase() -> None:
    """Decimoctava ronda (U14): de las gráficas del ciclo de NOAA entra una cifra copiada de los
    datos que pintan, con su mes y su día de lectura; la fase no la dicen, y EMMA no la deduce."""
    cycle = radiation_read.describe()["solar_cycle"]
    noaa = [item for item in cycle["quotes"] if item["ref"] == "noaa-swpc-solar-cycle-progression"]
    # Las frases citadas no traen más cifras que la copiada: ni el mes ni el «-1» de la página
    # amplían las que EMMA puede escribir en la entrada (revisión de código).
    assert [item["quote"] for item in noaa] == [
        '"smoothed_ssn": 94.4', "Data not yet available or not calculable",
    ]
    assert '{"time-tag": "2026-03", "smoothed_ssn": 94.4}' in (
        registry.get("noaa-swpc-solar-cycle-progression").notes or ""
    )
    assert "2026-03" in noaa[0]["where"]
    assert all(item["read_on"] == "2026-10-26" for item in noaa)
    # La cifra, con su mes, y que EMMA no deduce la fase.
    assert "marzo de 2026, con 94,4" in cycle["text"]
    assert "EMMA no deduce de esa cifra en qué fase está el ciclo" in cycle["text"]
    # La nota sigue siendo la de 2024: la cifra no la sustituye ni cambia su fecha.
    assert cycle["as_of"] == "2024-10-15"
    # La ficha es de NOAA, sin fecha propia (la página no la lleva) y declarada pendiente.
    card = registry.get("noaa-swpc-solar-cycle-progression")
    assert card.url == "https://www.swpc.noaa.gov/products/solar-cycle-progression"
    assert card.date is None and "date" in card.unverified
    assert "Releída el 2026-10-26" in (card.notes or "")


def test_the_shelter_exit_is_shown_as_a_source_with_no_threshold_of_emma() -> None:
    exit_ = radiation_read.describe()["shelter_exit"]
    # Solo texto y frases: no hay ningún campo con cifra que EMMA pudiera usar como umbral.
    assert set(exit_) == {"label", "text", "quotes", "sources", "not_found", "scope", "read_on"}
    assert "no tiene criterio propio de fin del refugio" in exit_["scope"]
    preprint = registry.get("lowe-2025-sep-nowcasting-mars")
    assert preprint.evidence_type == "preprint"
    assert "sin revisión por pares" in exit_["text"] and "no de Orion" in exit_["text"]
    assert "Ninguna fuente de NASA leída" in exit_["text"]
    # La permanencia que ya se enseñaba no cambia.
    assert dt.timedelta(hours=1) == radiation.SHELTER_BUILD
    assert dt.timedelta(hours=24) == radiation.SHELTER_MAX_STAY


def test_what_the_readings_write_passes_the_language_guard() -> None:
    texts = _texts({
        name: {field: value for field, value in entry.items() if field not in ("quotes", "sources")}
        for name, entry in radiation_read.describe().items()
    })
    # «dosis» a secas es la de radiación (la misma excepción que el resto del bloque).
    found = [
        (text, finding) for text in texts for finding in check(text)
        if (finding.category, finding.match.lower()) != ("dosing", "dosis")
    ]
    assert found == []


# --------------------------------------------------------------------------- #
# Las defensas del cargador
# --------------------------------------------------------------------------- #


def _break(path: str, value: Any) -> dict[str, Any]:
    raw = copy.deepcopy(RAW)
    *parents, last = path.split("/")
    node: Any = raw
    for key in parents:
        node = node[int(key)] if isinstance(node, list) else node[key]
    if value is _DROP:
        del node[last]
    else:
        node[int(last) if isinstance(node, list) else last] = value
    return raw


_DROP = object()


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        ("read_on", "ayer", "no es una fecha"),
        ("extra", 1, "campos desconocidos"),
        ("shelter_exit/threshold", 1.25, "campos desconocidos"),
        ("solar_cycle/as_of", _DROP, "faltan campos"),
        ("shelter_exit/not_found", " ", "falta `not_found`"),
        ("shelter_exit/quotes", [], "sin ninguna frase"),
        ("onboard_warning/quotes/0/ref", "no-existe", "no está en el registro"),
        ("onboard_warning/quotes/0/where", "", "falta `where`"),
        # Una ficha que no es de NASA ni del servidor de preprints (OSDR) no se cita aquí.
        ("onboard_warning/quotes/0/ref", "osd-288", "no es NASA"),
        # Una ficha de NASA que no dice que se leyera ese día.
        ("onboard_warning/quotes/0/ref", "nasa-why-space-radiation-matters", "sin rastro"),
        ("shelter_exit/scope", "  ", "falta `scope`"),
        ("onboard_warning/quotes/1/quote", "HERA will sound a warning.", "no está en la nota"),
        ("onboard_warning/emma_reads_it", True, "no la lee"),
        ("solar_cycle/as_of", "2025-01-01", "no es la fecha de ninguna"),
        ("solar_cycle/as_of", "2026-12-01", "posterior a su lectura"),
        ("solar_cycle/as_of", "15/10/2024", "no es una fecha"),
        # `fromisoformat` las acepta, y la interfaz rompe al pintarlas.
        ("read_on", "20261023", "no es una fecha"),
        ("solar_cycle/as_of", "20241015", "no es una fecha"),
        # El punto lo pone la interfaz: con el suyo saldrían dos.
        ("shelter_exit/scope", "se muestra como fuente.", "termina en puntuación"),
        # La fecha propia de una frase (decimoctava ronda, U14): una fecha, no anterior a la
        # primera lectura, y la que dice la nota de su ficha.
        ("solar_cycle/quotes/4/read_on", "2026-10-20", "anterior a la primera lectura"),
        ("solar_cycle/quotes/4/read_on", "26/10/2026", "no es una fecha"),
        ("solar_cycle/quotes/4/read_on", "2026-10-25", "sin rastro"),
        # La nota de 2024 no se releyó ese día: no se puede fechar como si se hubiera releído.
        ("solar_cycle/quotes/0/read_on", "2026-10-26", "sin rastro"),
        ("solar_cycle/quotes/4/quote", '"smoothed_ssn": 95.0', "no está en la nota"),
    ],
)
def test_the_loader_rejects_what_breaks_its_contract(path: str, value: Any, reason: str) -> None:
    with pytest.raises(RadiationReadError, match=reason):
        radiation_read.validate(_break(path, value))


@pytest.mark.parametrize(
    ("entry", "field", "addition"),
    [
        # Un umbral de salida propio: la cifra no está en ninguna frase.
        ("shelter_exit", "text", " Se considera terminado a las 12 h."),
        # El día de la fecha de una ficha (Orion, 2016-09-22) no es una cifra citada.
        ("shelter_exit", "text", " Se sale del refugio a las 22 h."),
        # Una permanencia de otra fuente sin ficha, en lo buscado.
        ("shelter_exit", "not_found", " RadWorks los dimensiona para 36 horas."),
        # Un umbral escondido en el alcance o en el rótulo.
        ("shelter_exit", "scope", ", salvo por debajo del 50 % del fondo"),
        ("shelter_exit", "label", " (12 h)"),
        ("solar_cycle", "text", " El ciclo 26 empieza en 2030."),
        # De las gráficas de NOAA solo entra la cifra copiada: ni el máximo, ni otro mes.
        ("solar_cycle", "text", " El máximo suavizado fue de 160,9."),
        ("solar_cycle", "text", " En septiembre de 2026 hubo 60,3 manchas."),
        # Ni el mes de la cifra ni el «-1» de la página abren paso a otras cifras.
        ("solar_cycle", "text", " Dura 3 meses."),
        ("solar_cycle", "text", " Pasó a 1."),
        ("onboard_warning", "text", " HERA tiene 7 sensores."),
        # Una cifra de la frase de otra entrada no vale en esta: 24 es del refugio.
        ("solar_cycle", "text", " Dura 24 h."),
        # Lo que el cotejo de `support.py` deja pasar por diseño, y aquí no: la cifra pegada a su
        # unidad, el decimal, un valor de entre 1950 y 2049 con unidad, un número largo y el que
        # va tras «nivel».
        ("shelter_exit", "text", " Se sale a las 12h."),
        ("shelter_exit", "text", " Se sale por debajo de 1,25x el fondo."),
        ("shelter_exit", "text", " El umbral es de 2000 µSv/h."),
        ("shelter_exit", "not_found", " Unas 1000000 partículas."),
        ("onboard_warning", "text", " Avisa en el nivel 3."),
        # Un número que parece un año no se aparta si no es el de una ficha o el de la lectura
        # (lo vio la revisión de código), y un decimal con punto no pierde su parte entera.
        ("shelter_exit", "text", " Se sale tras 1999 minutos."),
        ("onboard_warning", "text", " HERA tiene 2000 sensores."),
        ("shelter_exit", "text", " Se sale por debajo de 0.125 del umbral."),
        # El año de una ficha citada (Orion, 2016) con una unidad detrás es una cifra.
        ("shelter_exit", "text", " El umbral es de 2016 µSv/h."),
    ],
)
def test_no_figure_written_by_emma_that_no_quote_of_its_entry_gives(
    entry: str, field: str, addition: str
) -> None:
    raw = copy.deepcopy(RAW)
    raw[entry][field] += addition
    with pytest.raises(RadiationReadError, match=f"{entry}/{field}: cifras que no están"):
        radiation_read.validate(raw)


@pytest.mark.parametrize(
    "addition",
    [
        " Se sale a las doce horas.", " Unas treinta y seis horas.", " Medio día.",
        # Sin unidad de tiempo detrás también es una cifra.
        " HERA tiene siete sensores.",
        # Centenas compuestas, millones y el cuarto de hora (lo vio la revisión de código).
        " El refugio dura quinientas horas.", " Unos doscientos minutos.",
        " Un millón de partículas.", " Un cuarto de hora.",
    ],
)
def test_a_quantity_in_words_cannot_be_checked_and_is_rejected(addition: str) -> None:
    raw = copy.deepcopy(RAW)
    raw["shelter_exit"]["text"] += addition
    with pytest.raises(RadiationReadError, match="va con letras"):
        radiation_read.validate(raw)


def test_a_decimal_with_a_point_keeps_its_whole_part_and_thousands_lose_the_point() -> None:
    # «0.125» se cotejaba como 125 (el punto de los millares se quitaba también de un decimal).
    assert radiation_read._written_figures("0.125") == ["0.125"]
    assert radiation_read._written_figures("1,25 y 1.000 y 12.500") == ["1.25", "1000", "12500"]
    # Un año solo se aparta si es uno de los dados, y nunca con unidad detrás.
    years = frozenset({"2016"})
    assert radiation_read._written_figures("de 2016 y de 1999", years) == ["1999"]
    assert radiation_read._written_figures("2016 µSv", years) == ["2016"]


def test_the_figures_emma_writes_are_the_quoted_ones() -> None:
    # Las que sí están: 24 h (Orion 2016), 25 % y las duraciones (el preprint); el ciclo 25. Una
    # fecha («15 de octubre de 2024») y un año no son cifras que cotejar.
    assert radiation_read.validate(copy.deepcopy(RAW)) == RAW
    for figure in ("24 h", "25 %", "5 h 30 min", "3 días y 7 h"):
        assert figure in RAW["shelter_exit"]["text"]
    assert "15 de octubre de 2024" in RAW["solar_cycle"]["text"]
    assert "ciclo 25" in RAW["solar_cycle"]["text"]


def test_a_date_in_the_note_is_not_a_reading_unless_it_says_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = registry.get

    def searched_only(ref_id: str) -> registry.EvidenceRef:
        ref = real(ref_id)
        notes = re.sub(r"(?:Re)?[Ll]e[ií]d[oa]s? el ", "Buscada el ", ref.notes or "")
        return dataclasses.replace(ref, notes=notes)

    monkeypatch.setattr(registry, "get", searched_only)
    with pytest.raises(RadiationReadError, match="sin rastro de la lectura"):
        radiation_read.validate(copy.deepcopy(RAW))


def test_a_card_on_plain_http_is_not_cited(monkeypatch: pytest.MonkeyPatch) -> None:
    real = registry.get

    def downgraded(ref_id: str) -> registry.EvidenceRef:
        ref = real(ref_id)
        url = (ref.url or "").replace("https://", "http://")
        return dataclasses.replace(ref, url=url)

    monkeypatch.setattr(registry, "get", downgraded)
    with pytest.raises(RadiationReadError, match="no es NASA"):
        radiation_read.validate(copy.deepcopy(RAW))


# --------------------------------------------------------------------------- #
# No decide nada: ni la proyección, ni las reglas, ni ningún nivel
# --------------------------------------------------------------------------- #


def _rates() -> list[Any]:
    return [
        observation("absorbed-dose-rate", 10.0, T0 + dt.timedelta(hours=h), "crew-01", "d")
        for h in range(25)
    ]


def test_the_projection_does_not_read_the_solar_cycle_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs: dict[str, Any] = {
        "mission_start": START, "mission_days": 10, "prior_career_msv": 100.0, "limit_msv": 600.0,
    }
    before = mission_projection(_rates(), **kwargs)
    assert before is not None and "supone tasa constante" in before["basis"]
    # Otra fase del ciclo en el fichero: la proyección no se mueve.
    raw = copy.deepcopy(RAW)
    raw["solar_cycle"]["text"] = "Nota descriptiva: mínimo solar."
    path = tmp_path / "radiation_read.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(radiation_read, "READ_PATH", path)
    radiation_read._read.cache_clear()
    radiation_read._describe.cache_clear()
    try:
        assert radiation_read.describe()["solar_cycle"]["text"] == "Nota descriptiva: mínimo solar."
        assert mission_projection(_rates(), **kwargs) == before
    finally:
        radiation_read._read.cache_clear()
        radiation_read._describe.cache_clear()


def test_the_readings_do_not_enter_the_rules_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = versioning.rules()
    raw = copy.deepcopy(RAW)
    raw["shelter_exit"]["text"] = "Otro texto, sin cifras."
    path = tmp_path / "radiation_read.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(radiation_read, "READ_PATH", path)
    radiation_read._read.cache_clear()
    radiation_read._describe.cache_clear()
    try:
        # Lo leído cambió de verdad, y la huella de las reglas no.
        assert radiation_read.describe()["shelter_exit"]["text"] == "Otro texto, sin cifras."
        assert versioning.rules() == before
    finally:
        radiation_read._read.cache_clear()
        radiation_read._describe.cache_clear()
    assert "radiation_read" not in json.dumps(before)


def test_status_serves_the_three_readings_without_moving_any_level(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/simulate", params={"scenario": "spe-event", "days": 10})
    before = client.get("/api/status").json()
    block = before["radiation"]
    # Sin red no hay evento de DONKI: el aviso y el fin del refugio se sirven igual, con o sin él.
    assert block["acute"]["onboard_warning"]["emma_reads_it"] is False
    assert block["acute"]["shelter_exit"]["label"] == "Fin del refugio"
    assert block["solar_cycle"]["as_of"] == "2024-10-15"
    for entry in (block["acute"]["onboard_warning"], block["acute"]["shelter_exit"],
                  block["solar_cycle"]):
        assert {item["ref"] for item in entry["quotes"]} == {
            source["id"] for source in entry["sources"]
        } <= set(registry.registry())
    # Cambiar lo leído no mueve nada de lo que decide.
    real = radiation_read.describe

    def other() -> dict[str, dict[str, Any]]:
        result = real()
        result["solar_cycle"]["text"] = "Nota descriptiva: mínimo solar."
        result["shelter_exit"]["text"] = "Otro texto."
        return result

    monkeypatch.setattr(radiation_read, "describe", other)
    after = client.get("/api/status").json()
    assert after["radiation"]["solar_cycle"]["text"] == "Nota descriptiva: mínimo solar."
    for key in ("dose", "domains", "overall_level", "rules_version"):
        assert after[key] == before[key], key
    assert [alert["level"] for alert in after["alerts"]] == [
        alert["level"] for alert in before["alerts"]
    ]
    for key in ("mission", "career", "projection"):
        assert after["radiation"][key] == block[key], key
    assert after["radiation"]["acute"]["time_to_action"] == block["acute"]["time_to_action"]


def test_without_an_event_the_onboard_warning_is_still_served(client: TestClient) -> None:
    client.post("/api/simulate", params={"days": 3})
    acute = client.get("/api/status").json()["radiation"]["acute"]
    assert acute["time_to_action"] is None
    assert acute["onboard_warning"]["label"] == "Aviso a bordo"


def test_routes_build_the_block_with_the_scales_function() -> None:
    # La ruta usa `radiation.scales`, que es quien añade lo leído: no hay otra vía.
    assert routes.radiation_scales is radiation.scales
