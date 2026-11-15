"""El perfil de misión: descriptivo, con cada dato atado a su frase leída, y fuera del riesgo.

Lo que vigilan estas pruebas: que ningún dato de un perfil figure sin su cita literal (o, si no
se encontró, sin decir qué se buscó), que el perfil se sirva en el contexto de misión con la
frase que lo declara descriptivo, que el perfil sea el que decide el objetivo de efemérides
(decisión del usuario del 2026-11-11: un perfil sin objetivo no consulta Horizons y no escala el
riesgo, y nadie más lee `EMMA_TARGET_BODY`), y —lo decidido el 2026-10-13— que, fuera de ese
tiempo de luz, cambiar de perfil no mueva ningún nivel, puntuación ni alerta (invariante 5).
Ninguna toca la red.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.api.routes import new_store, reset_store
from app.core import versioning
from app.core.cache import CachedPayload, OfflineDataUnavailable
from app.core.config import Settings, get_settings
from app.environment.ephemeris import CommsWindow, EphemerisClient
from app.evidence import mission_profiles, registry
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]
PROFILES = ("leo", "cislunar", "lunar-surface", "mars-transit", "mars-surface")
# La configuración por defecto, sin `.env`: `EMMA_TARGET_BODY` 499, que ya no manda.
_SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]


def _raw() -> dict[str, Any]:
    return copy.deepcopy(mission_profiles.catalog())


def _aspect(raw: dict[str, Any], profile: str, name: str) -> dict[str, Any]:
    [found] = [item for item in raw["profiles"] if item["id"] == profile]
    aspect: dict[str, Any] = found["aspects"][name]
    return aspect


def _as_gap(aspect: dict[str, Any]) -> dict[str, Any]:
    """Convierte un aspecto leído en un hueco declarado, como quedaría si no se hubiera encontrado.

    Desde el 2026-10-21 el catálogo no tiene ningún aspecto sin verificar: los seis que lo estaban
    se leyeron en su fuente. Las defensas sobre los huecos se prueban con uno fabricado aquí.
    """
    aspect.update(
        status=mission_profiles.UNVERIFIED, statement=None, citations=[], discrepancy=None,
        searched="En las páginas leídas se buscó «delay» y no se encontró.",
    )
    return aspect


# --- El catálogo: nada sin su frase, y lo que falta dice qué se buscó ----------------------


def test_the_catalog_has_every_profile_with_every_aspect() -> None:
    raw = mission_profiles.catalog()
    assert tuple(item["id"] for item in raw["profiles"]) == PROFILES
    for profile in raw["profiles"]:
        assert tuple(profile["aspects"]) == tuple(mission_profiles.ASPECTS)


def test_every_read_fact_carries_its_literal_quote_and_every_gap_says_what_was_searched() -> None:
    raw = mission_profiles.catalog()
    read = 0
    for profile in raw["profiles"]:
        for aspect in profile["aspects"].values():
            if aspect["status"] == mission_profiles.READ:
                read += 1
                assert aspect["statement"] and aspect["citations"]
            else:
                assert aspect["status"] == mission_profiles.UNVERIFIED
                assert aspect["statement"] is None and aspect["citations"] == []
                assert "se buscó" in aspect["searched"]
    # Desde el 2026-10-21 los seis huecos que había están leídos. Eso no hace del hueco un error:
    # lo que no se encuentre se declara así, y un hueco bien declarado se acepta (si una prueba
    # exigiera cero huecos, empujaría a rellenar de memoria). Las defensas sobre los huecos se
    # prueban con uno fabricado (`_as_gap`).
    assert read > 0
    raw = _raw()
    _as_gap(_aspect(raw, "lunar-surface", "comm_delay"))
    assert mission_profiles.validate(raw) is raw


def _is_nasa(url: str | None) -> bool:
    host = urlparse(url or "").hostname or ""
    return (url or "").startswith("https://") and (host == "nasa.gov" or host.endswith(".nasa.gov"))


def test_every_citation_points_at_a_registry_entry_with_the_same_url() -> None:
    raw = mission_profiles.catalog()
    cited = 0
    for profile in raw["profiles"]:
        for aspect in profile["aspects"].values():
            extra = aspect["discrepancy"]["citations"] if aspect["discrepancy"] else []
            for cite in [*aspect["citations"], *extra]:
                cited += 1
                # Por identificador: el título y la URL son los de la ficha, sin otra copia.
                assert set(cite) == {"ref", "section", "quote", "read_on"}
                ref = registry.get(cite["ref"])
                # Documentos de la NASA: nasa.gov, science.nasa.gov o ntrs.nasa.gov.
                assert _is_nasa(ref.url), ref.url
                assert cite["quote"].strip() and cite["section"].strip()
                # La primera lectura (2026-10-13), la de los huecos y la radiación (2026-10-21),
                # la de la decimonovena ronda (U8) y la del espacio cislunar, el polvo y el ciclo
                # de día y noche (2026-11-03).
                assert dt.date.fromisoformat(cite["read_on"]) in {
                    dt.date(2026, 10, 13), dt.date(2026, 10, 21),
                    dt.date(2026, 10, 31), dt.date(2026, 11, 1), dt.date(2026, 11, 3),
                }
    assert cited > 0
    assert not _is_nasa("https://nasa.gov.example.org/") and not _is_nasa("http://www.nasa.gov/")


def test_each_profile_says_whether_it_is_inside_the_magnetosphere_with_its_quote() -> None:
    raw = mission_profiles.catalog()
    expected = {
        "leo": "the planet’s magnetic field provides them with significant protection",
        # El espacio cislunar: atraviesa los cinturones de Van Allen y sale del campo magnético.
        "cislunar": "As Orion travels beyond the protection of Earth’s magnetic field",
        "lunar-surface": "The Moon is beyond Earth’s protective magnetosphere",
        "mars-transit": "Outside Earth’s protective magnetic field and atmosphere",
    }
    for profile, phrase in expected.items():
        aspect = _aspect(raw, profile, "radiation_environment")
        assert aspect["status"] == mission_profiles.READ
        quotes = [cite["quote"] for cite in aspect["citations"]]
        assert phrase in quotes[0]
        # El ciclo solar, con su frase, en los tres; sin decir en qué fase se está.
        assert any(quote.startswith("Solar cycle") for quote in quotes)
        assert "no dice en qué fase" in aspect["statement"]


def test_the_note_on_mixed_components_is_emma_s_own_and_only_on_radiation() -> None:
    served = mission_profiles.describe("leo", _SETTINGS)
    notes = {item["key"]: item["emma_note"] for item in served["aspects"]}
    assert notes.pop("radiation_environment") == mission_profiles.EMMA_NOTES[
        "radiation_environment"
    ]
    assert set(notes.values()) == {None}
    note = mission_profiles.EMMA_NOTES["radiation_environment"]
    assert note.startswith("Nota de EMMA:") and "EMMA no los separa" in note
    assert "mezcla los componentes" in note


def test_the_lunar_light_time_is_not_passed_off_as_the_communication_delay() -> None:
    delay = _aspect(_raw(), "lunar-surface", "comm_delay")
    assert "1.3 seconds" in delay["citations"][0]["quote"]
    assert "3 to 14 seconds" in delay["citations"][1]["quote"]
    assert "tiempo de luz, no el retardo" in delay["statement"]
    assert "5-14 second" in delay["discrepancy"]["citations"][0]["quote"]
    # El perfil lunar sigue sin cuerpo de efemérides: activarlo pide red y otra decisión.
    [lunar] = [item for item in _raw()["profiles"] if item["id"] == "lunar-surface"]
    assert lunar["ephemeris_target"] is None


def test_the_cislunar_profile_is_orion_with_what_artemis_ii_observed() -> None:
    raw = _raw()
    [cislunar] = [item for item in raw["profiles"] if item["id"] == "cislunar"]
    # Como el lunar, sin cuerpo de efemérides: la Luna no está anotada en EMMA.
    assert cislunar["ephemeris_target"] is None
    delay = cislunar["aspects"]["comm_delay"]
    # El tiempo de luz no pasa por retardo, y el corte tras la Luna no pasa por retardo tampoco.
    assert "tiempo de luz, no el retardo" in delay["statement"]
    assert "es un corte previsto, no un retardo" in delay["statement"]
    assert "about 40 minutes" in delay["citations"][2]["quote"]
    duration = cislunar["aspects"]["typical_duration"]
    assert duration["citations"][0]["quote"].endswith("MISSION DURATION 9 Days, 1 Hour, 32 Minutes")
    assert "Crewed Lunar Flyby" in duration["citations"][0]["quote"]
    assert "first crewed Orion flight" in duration["citations"][1]["quote"]
    assert "duración observada de un vuelo, no una duración típica" in duration["statement"]
    assert "252,756 miles" in cislunar["aspects"]["distance"]["citations"][1]["quote"]
    evacuation = cislunar["aspects"]["return_or_evacuation"]
    assert "multi-day return from the Moon" in evacuation["citations"][0]["quote"]
    assert "no da un plazo de evacuación médica" in evacuation["statement"]
    # Gateway sale solo como plan de 2021: ninguna cifra ni aspecto lo da por volando hoy.
    gravity = cislunar["aspects"]["gravity_regime"]
    assert "que entonces se planeaba" in gravity["statement"]
    assert "es un plan" in gravity["statement"]
    radiation = cislunar["aspects"]["radiation_environment"]
    # La frase de 2022 es una previsión anterior al vuelo, y la casilla lo dice.
    assert "Es una previsión, no una medida del vuelo." in radiation["statement"]


def test_dust_and_daylight_are_read_where_a_source_says_them_and_gaps_elsewhere() -> None:
    raw = _raw()
    read = {
        ("lunar-surface", "surface_dust"): "irritated the eyes and throats of Apollo crews",
        ("mars-surface", "surface_dust"): "perchlorates that can disrupt thyroid function",
        ("leo", "day_night_cycle"): "16 sunrises and sunsets",
        ("lunar-surface", "day_night_cycle"): "~14.5 Earth days of light",
        ("mars-surface", "day_night_cycle"): "one rotation every 24.6 hours",
    }
    for (profile, name), phrase in read.items():
        aspect = _aspect(raw, profile, name)
        assert aspect["status"] == mission_profiles.READ, (profile, name)
        assert any(phrase in cite["quote"] for cite in aspect["citations"]), (profile, name)
    # Donde nada leído lo dice, no se deduce que no haya polvo o que no haya noche: hueco.
    for profile in PROFILES:
        for name in ("surface_dust", "day_night_cycle"):
            if (profile, name) not in read:
                aspect = _aspect(raw, profile, name)
                assert aspect["status"] == mission_profiles.UNVERIFIED, (profile, name)
                assert "se buscó" in aspect["searched"]
    # El sol de Marte va con la cifra de la página (24,6 h), no con una de memoria.
    assert "24,6 horas" in _aspect(raw, "mars-surface", "day_night_cycle")["statement"]


def test_mars_surface_keeps_both_gravity_figures_and_chooses_neither() -> None:
    surface = _aspect(_raw(), "mars-surface", "gravity_regime")
    assert "un tercio" in surface["statement"]
    assert any("one-third" in cite["quote"] for cite in surface["citations"])
    assert any("1/3 g on Mars" in cite["quote"] for cite in surface["citations"])
    assert "three-eighths" in surface["discrepancy"]["citations"][0]["quote"]
    assert "no elige" in surface["discrepancy"]["text"]


def test_transit_evacuation_says_the_reading_is_about_aborts_and_gives_no_medical_term() -> None:
    aspect = _aspect(_raw(), "mars-transit", "return_or_evacuation")
    assert "ninguna fuente leída da un plazo de evacuación médica" in aspect["statement"]
    assert {"nasa-m2m-mars-abort", "ntrs-20250003885"} <= {
        cite["ref"] for cite in aspect["citations"]
    }


def test_a_discrepancy_between_two_pages_is_kept_with_both_quotes() -> None:
    surface = _aspect(_raw(), "mars-transit", "gravity_regime")
    assert "one-third" in surface["citations"][0]["quote"]
    assert "three-eighths" in surface["discrepancy"]["citations"][0]["quote"]
    assert "tres octavos" in surface["discrepancy"]["text"]


@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        (lambda a: a.update(citations=[]), "un dato leído lleva"),
        (lambda a: a.update(statement=" "), "un dato leído lleva"),
        (lambda a: a.update(status="proven"), "estado desconocido"),
        (lambda a: a["citations"][0].update(quote=""), "sin frase y apartado"),
        (lambda a: a["citations"][0].update(section=" "), "sin frase y apartado"),
        (lambda a: a["citations"][0].update(url="https://example.org/"),
         "una cita lleva exactamente"),
        (lambda a: a["citations"][0].pop("read_on"), "una cita lleva exactamente"),
        (lambda a: a.pop("searched"), "un aspecto lleva exactamente"),
        (lambda a: a.update(discrepancy={"text": "otra dice otra cosa", "citations": []}),
         "una discrepancia lleva"),
    ],
)
def test_a_read_fact_without_its_evidence_is_rejected(break_it: Any, message: str) -> None:
    raw = _raw()
    break_it(_aspect(raw, "mars-transit", "comm_delay"))
    with pytest.raises(ValueError, match=message):
        mission_profiles.validate(raw)


def test_a_citation_of_a_document_that_is_not_in_the_registry_is_rejected() -> None:
    raw = _raw()
    _aspect(raw, "mars-transit", "comm_delay")["citations"][0]["ref"] = "de-memoria"
    with pytest.raises(registry.RegistryError):
        mission_profiles.validate(raw)


@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        (lambda a: a.update(statement="unos segundos"), "no afirma nada"),
        (lambda a: a.update(searched=None), "qué se buscó"),
        (lambda a: a.update(searched="  "), "qué se buscó"),
    ],
)
def test_a_gap_cannot_assert_anything_nor_hide_the_search(break_it: Any, message: str) -> None:
    raw = _raw()
    gap = _as_gap(_aspect(raw, "lunar-surface", "comm_delay"))
    break_it(gap)
    with pytest.raises(ValueError, match=message):
        mission_profiles.validate(raw)


def test_a_catalog_with_a_missing_profile_or_aspect_is_rejected() -> None:
    raw = _raw()
    raw["profiles"].pop()
    with pytest.raises(ValueError, match="se esperaban los perfiles"):
        mission_profiles.validate(raw)
    raw = _raw()
    raw["profiles"][0]["aspects"].pop("distance")
    with pytest.raises(ValueError, match="los aspectos son"):
        mission_profiles.validate(raw)
    raw = _raw()
    raw["profiles"][1]["ephemeris_target"] = "301"
    with pytest.raises(ValueError, match="no está anotado"):
        mission_profiles.validate(raw)


def test_the_list_of_cited_pages_is_exactly_what_the_profiles_cite() -> None:
    assert mission_profiles.cited_refs() == set(mission_profiles.catalog()["source"]["pages_cited"])
    raw = _raw()
    raw["source"]["pages_cited"].append("mmash")
    with pytest.raises(ValueError, match="no coincide"):
        mission_profiles.validate(raw)
    raw = _raw()
    raw["source"]["pages_read_without_citation"][0]["url"] = "de memoria"
    with pytest.raises(ValueError, match="su título y su URL"):
        mission_profiles.validate(raw)


# --- Lo que se sirve ---------------------------------------------------------------------


def test_the_served_profile_says_it_is_descriptive_and_not_a_ledger_entry() -> None:
    served = mission_profiles.describe("mars-transit", _SETTINGS)
    assert served["known"] is True
    assert served["note"] == (
        "descriptivo: lo que dice de cada aspecto no cambia el riesgo; el perfil solo decide "
        "hacia qué cuerpo se calcula el tiempo de luz real, que es lo que lo escala"
    )
    assert "asiento firmado del registro" in served["declared"]
    assert [item["key"] for item in served["aspects"]] == list(mission_profiles.ASPECTS)
    delay = served["aspects"][0]
    assert delay["label"] == "retardo de comunicaciones"
    assert delay["status_text"] == "leído en la fuente"
    assert delay["citations"][0]["title"] == "The Human Body in Space"
    assert delay["citations"][0]["url"] == registry.get("nasa-human-body-in-space").url
    assert len(served["pages_read"]) == 39
    assert all(_is_nasa(page["url"]) for page in served["pages_read"])
    assert "read_on" not in served and "read_dates" not in served
    # Cada página con sus días: ni una fecha común al pie ni todas las fechas para todas.
    pages = {page["title"]: page["read_on"] for page in served["pages_read"]}
    assert pages["The Human Body in Space"] == ["2026-10-13"]
    assert pages["Voyager 1: What Is a Light-Day"] == ["2026-10-21"]
    assert pages["Step 3, Artemis: Moon Missions as an Astronaut Testbed for Mars"] == [
        "2026-10-13", "2026-10-21", "2026-10-31", "2026-11-03",
    ]
    assert pages["Hazard: Gravity Fields"] == ["2026-10-13"]
    assert pages["Artemis III"] == ["2026-10-21"]
    assert "up to 20 minutes one-way" in delay["citations"][0]["quote"]
    assert "22 minutos" in delay["discrepancy"]["text"]
    # El tiempo de luz no se hace pasar por retardo de comunicaciones, tampoco con Marte.
    assert "es tiempo de luz, no el retardo" in delay["discrepancy"]["text"]
    evacuation = {item["key"]: item for item in served["aspects"]}["return_or_evacuation"]
    assert evacuation["status_text"] == "leído en la fuente"
    assert "espacio profundo en general" in evacuation["statement"]
    # Un hueco se sirve como tal, con lo que se buscó.
    gap = mission_profiles._aspect("resupply", _as_gap(_aspect(_raw(), "leo", "resupply")), [])
    assert gap["status_text"] == "sin verificar"
    assert gap["statement"] is None and gap["searched"] and gap["emma_note"] is None


def test_the_reading_dates_come_from_the_citations_and_each_uncited_page_carries_its_own() -> None:
    raw = _raw()
    _aspect(raw, "leo", "comm_delay")["citations"][0]["read_on"] = "2026-10-01"
    pages = {page["title"]: page["read_on"] for page in mission_profiles._pages_read(raw)}
    assert pages["Step 3, Artemis: Moon Missions as an Astronaut Testbed for Mars"] == [
        "2026-10-01", "2026-10-13", "2026-10-21", "2026-10-31", "2026-11-03",
    ]
    for broken in ([], None, ["ayer"]):
        raw = _raw()
        raw["source"]["pages_read_without_citation"][0]["read_on"] = broken
        with pytest.raises(ValueError):
            mission_profiles.validate(raw)


def test_a_emma_note_on_an_aspect_that_does_not_exist_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(mission_profiles.EMMA_NOTES, "radiation", "nota huérfana")
    with pytest.raises(ValueError, match="aspecto desconocido"):
        mission_profiles.validate(_raw())


def test_the_default_profile_matches_the_default_ephemeris_target() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    served = mission_profiles.describe(settings.mission_profile, settings)
    assert settings.mission_profile == "mars-transit"
    assert served["ephemeris"]["state"] == mission_profiles.CONSISTENT
    assert served["ephemeris"]["target_body"] == "499"
    assert served["ephemeris"]["configured_ignored"] is False


# --- El perfil decide el objetivo de efemérides (decisión del usuario, 2026-11-11) ----------


@pytest.mark.parametrize("profile", ["leo", "cislunar", "lunar-surface", "jupiter"])
def test_a_profile_without_ephemeris_target_has_no_target_whatever_the_configuration_says(
    profile: str,
) -> None:
    """Antes, con órbita baja declarada, el tiempo de luz se calculaba hacia Marte («no casan»)."""
    chosen = mission_profiles.ephemeris_target(profile, _SETTINGS)
    assert chosen.target is None
    # El 499 por defecto no lo escribió nadie: no se avisa de que se ignora.
    assert chosen.configured == "499" and chosen.configured_ignored is False
    written = Settings(_env_file=None, target_body="499")  # type: ignore[call-arg]
    chosen = mission_profiles.ephemeris_target(profile, written)
    assert chosen.target is None and chosen.configured_ignored is True


@pytest.mark.parametrize("profile", ["mars-transit", "mars-surface"])
def test_a_mars_profile_targets_mars_even_if_the_configuration_says_otherwise(
    profile: str,
) -> None:
    other = Settings(_env_file=None, target_body="301")  # type: ignore[call-arg]
    chosen = mission_profiles.ephemeris_target(profile, other)
    assert chosen.target == "499"
    assert chosen.configured_ignored is True
    ephemeris = mission_profiles.describe(profile, other)["ephemeris"]
    assert ephemeris["state"] == mission_profiles.CONSISTENT
    assert ephemeris["target_body"] == "499" and ephemeris["configured_target_body"] == "301"
    assert "EMMA_TARGET_BODY=301: no se usa" in ephemeris["text"]


@pytest.mark.parametrize("profile", ["leo", "cislunar", "lunar-surface"])
def test_a_profile_without_target_says_so_without_a_figure_nor_a_failure(profile: str) -> None:
    ephemeris = mission_profiles.describe(profile, _SETTINGS)["ephemeris"]
    assert ephemeris["state"] == mission_profiles.NO_TARGET
    assert ephemeris["target_body"] is None and ephemeris["risk_scaled"] is False
    assert ephemeris["text"].startswith(mission_profiles.NO_TARGET_TEXT)
    assert "no tiene objetivo de efemérides" in ephemeris["text"]
    assert "factor de aislamiento 1" in ephemeris["text"]
    # Ni el «no casan» de antes ni el «sin efemérides» de un fallo, ni una cifra de retardo.
    assert "No casan" not in ephemeris["text"] and "Sin efemérides" not in ephemeris["text"]
    assert "min de ida y vuelta" not in ephemeris["text"]
    # El valor por defecto de EMMA_TARGET_BODY no se menciona; uno escrito que no manda, sí.
    assert "EMMA_TARGET_BODY" not in ephemeris["text"]
    written = Settings(_env_file=None, target_body="499")  # type: ignore[call-arg]
    said = mission_profiles.describe(profile, written)["ephemeris"]
    assert "EMMA_TARGET_BODY=499: no se usa" in said["text"] and said["configured_ignored"]


def test_the_mismatch_state_no_longer_exists() -> None:
    assert not hasattr(mission_profiles, "MISMATCH")
    states = {
        mission_profiles.describe(profile, _SETTINGS)["ephemeris"]["state"] for profile in PROFILES
    }
    assert states == {mission_profiles.CONSISTENT, mission_profiles.NO_TARGET}


def test_a_target_profile_says_the_figure_that_scaled_the_risk() -> None:
    ephemeris = mission_profiles.describe(
        "mars-transit", _SETTINGS, round_trip_minutes=22.0, isolation_factor=1.33
    )["ephemeris"]
    assert ephemeris["risk_scaled"] is True
    assert "hacia Marte (código 499" in ephemeris["text"]
    assert "22 min de ida y vuelta" in ephemeris["text"]
    assert "factor de aislamiento 1,33" in ephemeris["text"]
    below = mission_profiles.describe(
        "mars-transit", _SETTINGS, round_trip_minutes=8.0, isolation_factor=1.0
    )["ephemeris"]
    assert below["risk_scaled"] is False
    assert "no escalan el riesgo" in below["text"]
    # Un retardo de segundos no sale como «0 min», que diría que no hay retardo.
    seconds = mission_profiles.describe(
        "mars-transit", _SETTINGS, round_trip_minutes=0.043, isolation_factor=1.0
    )["ephemeris"]
    assert "2,6 s de ida y vuelta" in seconds["text"]
    assert "0 min" not in seconds["text"]
    # Sin efeméride ese día (lógica 1): el factor es 1 y el texto no dice lo contrario.
    missing = mission_profiles.describe("mars-transit", _SETTINGS)["ephemeris"]
    assert missing["risk_scaled"] is False
    assert "no hay efeméride" in missing["text"]


def test_an_unknown_profile_is_declared_unknown_and_shows_nothing() -> None:
    served = mission_profiles.describe("jupiter", _SETTINGS)
    assert served["known"] is False
    assert served["aspects"] == [] and served["ephemeris"] is None
    assert "no está en el catálogo" in served["unknown_text"]
    assert "no hay objetivo de efemérides" in served["unknown_text"]
    assert served["note"] == mission_profiles.DESCRIPTIVE


def test_only_the_single_point_reads_the_configured_target_body() -> None:
    """Ningún módulo de `app/` ni guion lee `EMMA_TARGET_BODY` salvo `ephemeris_target`."""
    readers = [
        path.relative_to(BACKEND).as_posix()
        for path in [*sorted((BACKEND / "app").rglob("*.py")),
                     *sorted((BACKEND / "scripts").glob("*.py"))]
        if ".target_body" in path.read_text(encoding="utf-8")
    ]
    assert readers == ["app/evidence/mission_profiles.py"]
    source = (BACKEND / "app" / "evidence" / "mission_profiles.py").read_text(encoding="utf-8")
    assert source.count(".target_body") == 1


# --- Invariante 5: el perfil solo actúa por el tiempo de luz de su objetivo -----------------


MARS_WINDOW = CommsWindow(dt.date(2026, 11, 14), 1.324, 11.01, "499")


class _Horizons:
    """Lo que se pide a las efemérides (sin red): el tiempo de luz de Marte fijo, o ninguno."""

    def __init__(self) -> None:
        self.asked: list[str] = []
        self.available = True

    def comms_window(self, client: Any, epoch: dt.date, target: str) -> CachedPayload:
        self.asked.append(target)
        if not self.available:
            raise OfflineDataUnavailable("sin efemérides en la prueba")
        assert target == "499", f"se pidió el objetivo {target!r}"
        return CachedPayload(
            data=MARS_WINDOW, fetched_at=dt.datetime.now(dt.UTC), source="prueba",
            from_cache=True,
        )


@pytest.fixture
def horizons(monkeypatch: pytest.MonkeyPatch) -> _Horizons:
    fake = _Horizons()
    monkeypatch.setattr(
        EphemerisClient, "comms_window",
        lambda self, epoch, target: fake.comms_window(self, epoch, target),
    )
    return fake


@pytest.fixture
def api(tmp_path: Path, horizons: _Horizons) -> Iterator[TestClient]:
    """Un almacén con un escenario y un tiempo de luz de Marte fijo (sin red).

    El tiempo de luz se fija para que el factor de aislamiento NO sea 1 hacia Marte: con él en 1
    la prueba no distinguiría un perfil que lo tocara de uno que no.
    """
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    client = TestClient(app)
    client.post("/api/simulate", params={"scenario": "progressive-insomnia", "days": 40})
    yield client
    app.dependency_overrides.clear()
    reset_store(None)


def _status_with(client: TestClient, tmp_path: Path, profile: str | None) -> dict[str, Any]:
    extra = {} if profile is None else {"mission_profile": profile}
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, **extra
    )
    response = client.get("/api/status")
    assert response.status_code == 200, response.text
    status: dict[str, Any] = response.json()
    return status


def _without_profile(status: dict[str, Any]) -> dict[str, Any]:
    rest = copy.deepcopy(status)
    rest["mission"].pop("profile")
    rest["mission"].pop("ephemeris_coverage")
    # Sin objetivo, «retardo con Tierra» no es una capacidad perdida (sin efemérides, sí): lo
    # fija `test_low_orbit_declared_does_not_scale_the_risk_with_the_light_time_of_mars`.
    rest.pop("monitoring")
    # Y lo que dice del retardo (`comms_status`, 2026-11-11): «no aplica» sin objetivo, «sin
    # efemérides» con él y sin dato. Solo lo describe; los niveles se comparan igual.
    rest.pop("comms_status")
    return rest


def test_the_profile_acts_only_through_the_light_time_of_its_target(
    api: TestClient, tmp_path: Path, horizons: _Horizons
) -> None:
    """El perfil cambia hacia dónde se mide; todo lo demás sale igual que con ese tiempo de luz.

    Con un perfil de Marte el estado es el de siempre con el tiempo de luz de Marte; con uno sin
    objetivo, exactamente el que daría ese mismo perfil de Marte sin efemérides (factor 1), y sin
    preguntar a Horizons. Ningún otro aspecto del perfil mueve un nivel, una puntuación o una
    alerta (invariante 5).
    """
    reference = _status_with(api, tmp_path, None)
    assert reference["isolation_factor"] > 1.0
    assert reference["alerts"], "el escenario tiene que disparar al menos una alerta"
    assert reference["mission"]["profile"]["id"] == "mars-transit"
    horizons.available = False
    unscaled = _status_with(api, tmp_path, None)
    assert unscaled["isolation_factor"] == 1.0
    horizons.available = True
    seen = {reference["mission"]["profile"]["display"]}
    for profile in (*PROFILES, "jupiter"):
        horizons.asked.clear()
        other = _status_with(api, tmp_path, profile)
        served = other["mission"]["profile"]
        assert served["id"] == profile
        seen.add(served["display"])
        if profile in ("mars-transit", "mars-surface"):
            assert horizons.asked and set(horizons.asked) == {"499"}
            assert _without_profile(other) == _without_profile(reference)
        else:
            assert horizons.asked == [], f"{profile}: se consultó Horizons sin objetivo"
            assert other["isolation_factor"] == 1.0
            assert other["mission"]["ephemeris_coverage"] is None
            assert served["solar_conjunction"] is None
            assert _without_profile(other) == _without_profile(unscaled)
    # Y el bloque sí cambia: la prueba no pasa porque el perfil se ignore al servirlo.
    assert len(seen) == 6


def test_the_status_serves_the_profile_inside_the_mission_context(
    api: TestClient, tmp_path: Path
) -> None:
    mission = _status_with(api, tmp_path, "mars-transit")["mission"]
    profile = mission["profile"]
    assert profile["note"] == mission_profiles.DESCRIPTIVE
    assert profile["ephemeris"]["state"] == mission_profiles.CONSISTENT
    # El tiempo de luz fijado del `api` escala el riesgo, y el bloque lo dice con el mismo factor.
    assert profile["ephemeris"]["risk_scaled"] is True
    assert mission["ephemeris_coverage"]["target"] == "499"
    assert profile["solar_conjunction"]["target_body"] == "499"
    # El texto libre de la configuración se queda: el perfil lo acompaña, no lo sustituye.
    assert mission["gravity_regime"] == "microgravedad"


def test_low_orbit_declared_does_not_scale_the_risk_with_the_light_time_of_mars(
    api: TestClient, tmp_path: Path, horizons: _Horizons
) -> None:
    """Lógica (2026-11-11): el caso que vio Ellande, órbita baja declarada y retardo de Marte."""
    horizons.asked.clear()
    status = _status_with(api, tmp_path, "leo")
    ephemeris = status["mission"]["profile"]["ephemeris"]
    assert horizons.asked == []
    assert status["isolation_factor"] == 1.0 and status["comms"] is None
    assert ephemeris["state"] == mission_profiles.NO_TARGET
    assert ephemeris["risk_scaled"] is False
    # Y la vigilancia no anuncia «sin efemérides» como capacidad perdida: no falta nada.
    [light] = [c for c in status["monitoring"]["capabilities"] if c["key"] == "light-time"]
    assert light["available"] is True


def test_the_signed_profile_decides_the_target_not_the_configured_one(
    api: TestClient, tmp_path: Path, horizons: _Horizons
) -> None:
    """Un cambio firmado a órbita baja deja de consultar Marte, aunque lo diga la configuración."""
    before = _status_with(api, tmp_path, None)
    assert before["isolation_factor"] > 1.0
    response = api.post(
        "/api/mission/profile", json={"profile": "leo", "declared_by": "Ana"},
        headers={"X-EMMA-Console": "1"},
    )
    assert response.status_code in (200, 201), response.text
    horizons.asked.clear()
    after = _status_with(api, tmp_path, None)
    assert after["mission"]["profile"]["id"] == "leo"
    assert horizons.asked == [] and after["isolation_factor"] == 1.0


def test_comms_and_preload_follow_the_profile(
    api: TestClient, tmp_path: Path, horizons: _Horizons
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, mission_profile="leo"
    )
    horizons.asked.clear()
    comms = api.get("/api/comms")
    assert comms.status_code == 404
    assert "no tiene objetivo de efemérides" in comms.json()["detail"]
    preload = api.post("/api/comms/preload", headers={"X-EMMA-Console": "1"})
    assert preload.status_code == 409
    assert "no hay nada que precargar" in preload.json()["detail"]
    assert horizons.asked == []
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    body = api.get("/api/comms").json()
    assert horizons.asked == ["499"]
    assert body["solar_conjunction"]["target_body"] == "499"


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_the_risk_engine_does_not_import_the_profiles() -> None:
    risk = BACKEND / "app" / "analysis" / "risk.py"
    assert "app.analysis.baseline" in _imports(risk)  # la guardia lee imports de verdad
    deciders = [risk, *sorted((BACKEND / "app" / "analysis").glob("*.py")),
                *sorted((BACKEND / "app" / "advisor").glob("*.py"))]
    for module in deciders:
        offending = {name for name in _imports(module) if "mission_profile" in name}
        assert not offending, f"{module.name} importa el perfil de misión: {offending}"
        assert "mission_profile" not in module.read_text(encoding="utf-8"), module.name


def test_the_profile_is_not_a_rule_and_stays_out_of_the_rules_fingerprint() -> None:
    assert not any("mission_profile" in module for module in versioning.FINGERPRINTED)
