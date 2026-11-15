"""Los perfiles lado a lado y el octavo aspecto, la capacidad o autonomía médica.

Lo que vigilan estas pruebas: que la matriz sirva todos los perfiles con los mismos aspectos y en
el mismo orden, que la columna del perfil declarado sea la única señalada, que una casilla sin
frase diga «EMMA no tiene fuente» y no se rellene, que la capacidad médica se construya SOLO con
frases que EMMA ya había leído para otra cosa (misma ficha, misma frase, mismo día) y diga para
qué se leyeron, y que ese aspecto no lo lea nada que decida: cambiarlo no mueve ningún nivel,
puntuación, alerta ni el factor de aislamiento (invariante 5). Ninguna toca la red.
"""

from __future__ import annotations

import copy
import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import text_guard
from app.api import routes
from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.environment.ephemeris import CommsWindow
from app.evidence import mission_profiles, nasa_framework
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]
PROFILES = ("leo", "cislunar", "lunar-surface", "mars-transit", "mars-surface")
# La configuración por defecto, sin `.env`: `EMMA_TARGET_BODY` 499, que ya no manda.
_SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]
MEDICAL = "medical_capability"


def _raw() -> dict[str, Any]:
    return copy.deepcopy(mission_profiles.catalog())


def _aspect(raw: dict[str, Any], profile: str, name: str) -> dict[str, Any]:
    [found] = [item for item in raw["profiles"] if item["id"] == profile]
    aspect: dict[str, Any] = found["aspects"][name]
    return aspect


def _cells(served: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    return {
        profile["id"]: next(cell for cell in profile["cells"] if cell["key"] == key)
        for profile in served["profiles"]
    }


# --- El octavo aspecto: solo frases ya leídas ----------------------------------------------


def test_the_last_aspect_is_the_medical_capability_and_every_profile_carries_it() -> None:
    assert list(mission_profiles.ASPECTS)[-1] == MEDICAL
    # Diez desde el 2026-11-03: el polvo de superficie y el ciclo de día y noche, antes de este.
    assert len(mission_profiles.ASPECTS) == 10
    assert mission_profiles.ASPECTS[MEDICAL] == "capacidad o autonomía médica"
    assert sorted(mission_profiles.REUSED_ONLY) == [MEDICAL]
    raw = mission_profiles.catalog()
    expected = {
        "leo": ["real-time guidance from Mission Control when using medical technologies"],
        "cislunar": [
            "spacesuits capable of keeping the astronauts alive for six days",
            "prohibiting real-time operational and medical support",
        ],
        "lunar-surface": [
            "IV Lunar > 30 day",
            "the CMO to stabilize and maintain an critically ill crewmember",
        ],
        "mars-transit": [
            "V Mars Expedition",
            "Mars-class missions",
            "the possibility of equipment failures or medical emergencies",
            "prohibiting real-time operational and medical support",
        ],
        "mars-surface": [
            "the possibility of equipment failures or medical emergencies",
            "prohibiting real-time operational and medical support",
            "V Mars Expedition",
            "Mars-class missions",
        ],
    }
    for profile, phrases in expected.items():
        aspect = _aspect(raw, profile, MEDICAL)
        assert aspect["status"] == mission_profiles.READ
        quotes = [cite["quote"] for cite in aspect["citations"]]
        assert len(quotes) == len(phrases)
        for quote, phrase in zip(quotes, phrases, strict=True):
            assert phrase in quote


def test_each_medical_quote_was_already_read_for_something_else() -> None:
    raw = mission_profiles.catalog()
    index = mission_profiles._first_read(raw)
    for profile in raw["profiles"]:
        for cite in profile["aspects"][MEDICAL]["citations"]:
            places = index[(profile["id"], mission_profiles._key(cite))]
            # Leída para otro aspecto del mismo perfil, nunca para la propia capacidad médica.
            assert places and not any("capacidad o autonomía médica" in place for place in places)
            assert all(
                place.endswith(f"de «{profile['display']}»")
                or place.startswith("marco de NASA leído:")
                for place in places
            )


def test_a_quote_read_for_another_destination_does_not_back_this_one() -> None:
    """Lo leído de Marte no respalda la casilla de la Luna: sería una deducción de EMMA."""
    raw = _raw()
    mars_delay = _aspect(raw, "mars-transit", "comm_delay")["citations"][0]
    _aspect(raw, "lunar-surface", MEDICAL)["citations"] = [copy.deepcopy(mars_delay)]
    with pytest.raises(ValueError, match="lunar-surface.medical_capability: se construye solo"):
        mission_profiles.validate(raw)


def _new_quote(aspect: dict[str, Any]) -> None:
    aspect["citations"][0]["quote"] = "A sentence nobody in EMMA has read before."


@pytest.mark.parametrize(
    "break_it",
    [
        pytest.param(_new_quote, id="frase nueva"),
        pytest.param(lambda a: a["citations"][0].update(read_on="2026-10-22"), id="otro día"),
        pytest.param(
            lambda a: a["citations"][0].update(section="Conclusions (página 9)"), id="otro apartado"
        ),
        pytest.param(
            lambda a: a["citations"][0].update(ref="nasa-human-body-in-space"), id="otra ficha"
        ),
        pytest.param(
            lambda a: a.update(discrepancy={
                "text": "otra página dice otra cosa",
                "citations": [{**a["citations"][0], "quote": "Unread discrepancy."}],
            }),
            id="discrepancia sin leer",
        ),
    ],
)
def test_a_medical_quote_not_already_read_is_rejected(break_it: Any) -> None:
    raw = _raw()
    break_it(_aspect(raw, "leo", MEDICAL))
    with pytest.raises(ValueError, match="solo con frases ya leídas"):
        mission_profiles.validate(raw)


def test_a_medical_quote_cannot_back_itself_from_another_profile() -> None:
    raw = _raw()
    # La misma frase nueva en la capacidad médica de dos perfiles: ninguna respalda a la otra.
    for profile in ("leo", "mars-transit"):
        _new_quote(_aspect(raw, profile, MEDICAL))
    with pytest.raises(ValueError, match="solo con frases ya leídas"):
        mission_profiles.validate(raw)


def test_the_rule_applies_only_to_the_reused_aspect() -> None:
    raw = _raw()
    # La misma frase nueva en un aspecto propio es una lectura nueva: no la caza esta regla.
    _new_quote(_aspect(raw, "leo", "gravity_regime"))
    assert mission_profiles.validate(raw) is raw
    # Pero quitar la frase de donde se leyó primero deja sin respaldo a la capacidad médica.
    raw = _raw()
    _new_quote(_aspect(raw, "leo", "comm_delay"))
    with pytest.raises(ValueError, match="solo con frases ya leídas"):
        mission_profiles.validate(raw)


def test_a_quote_from_the_nasa_framework_read_counts_as_already_read() -> None:
    framework = nasa_framework.read()
    [item] = [
        statement for block in framework["blocks"] for statement in block["statements"]
        if statement["id"] == "loc-v-definition"
    ]
    raw = _raw()
    _aspect(raw, "mars-transit", MEDICAL)["citations"].append({
        "ref": item["ref"], "section": item["where"], "quote": item["quote"],
        "read_on": nasa_framework.read_on(framework, item["ref"]),
    })
    raw["source"]["pages_cited"].append(item["ref"])
    assert mission_profiles.validate(raw) is raw
    read_on = nasa_framework.read_on(framework, item["ref"])
    key = (item["ref"], item["where"], item["quote"], read_on)
    places = mission_profiles._first_read(raw)[("mars-transit", key)]
    assert places == ["marco de NASA leído: «Niveles de asistencia médica (Level of Care) IV y V»"]


def test_the_framework_is_read_only_when_a_quote_needs_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un catálogo que no cita el marco de NASA no lo lee. El real lo cita: `main` lo valida."""

    def broken() -> dict[str, Any]:
        raise nasa_framework.FrameworkError("marco roto")

    monkeypatch.setattr(nasa_framework, "read", broken)
    raw = _raw()
    # Las filas de los niveles y EIMO (decimonovena ronda) sí lo necesitan: sin ellas, nada lo lee.
    for profile in raw["profiles"]:
        aspect = profile["aspects"][MEDICAL]
        aspect["citations"] = [
            cite for cite in aspect["citations"]
            if cite["ref"] not in {"ntrs-20180008706", "ntrs-20240001402"}
        ]
    raw["source"]["pages_cited"] = sorted(mission_profiles._refs(raw))
    assert mission_profiles.validate(raw) is raw
    _new_quote(_aspect(raw, "leo", MEDICAL))
    with pytest.raises(nasa_framework.FrameworkError):
        mission_profiles.validate(raw)


def test_a_medical_gap_is_declared_like_any_other() -> None:
    raw = _raw()
    _aspect(raw, "leo", MEDICAL).update(
        status=mission_profiles.UNVERIFIED, statement=None, citations=[],
        searched="Se buscó entre las frases ya leídas y ninguna habla de la estación.",
    )
    assert mission_profiles.validate(raw) is raw


# --- La matriz que se sirve ----------------------------------------------------------------


def test_the_matrix_serves_every_profile_with_the_same_aspects_in_order() -> None:
    served = mission_profiles.compare("mars-transit")
    assert served["note"] == mission_profiles.DESCRIPTIVE
    assert [item["key"] for item in served["aspects"]] == list(mission_profiles.ASPECTS)
    assert [item["label"] for item in served["aspects"]] == list(mission_profiles.ASPECTS.values())
    assert [item["key"] for item in served["aspects"] if item["reused_only"]] == [MEDICAL]
    assert tuple(profile["id"] for profile in served["profiles"]) == PROFILES
    for profile in served["profiles"]:
        assert [cell["key"] for cell in profile["cells"]] == list(mission_profiles.ASPECTS)
        for cell in profile["cells"]:
            # Desde el polvo y el ciclo de día y noche (2026-11-03) hay casillas sin frase leída.
            if cell["status"] == mission_profiles.READ:
                assert cell["text"] == cell["statement"]
            else:
                assert cell["text"] == mission_profiles.NO_SOURCE and cell["statement"] is None
            # Para qué se leyó primero: solo en la capacidad médica, y siempre en ella.
            assert bool(cell["reused_from"]) == (cell["key"] == MEDICAL)
    assert [page["title"] for page in served["pages_read"]] == [
        page["title"]
        for page in mission_profiles.describe("mars-transit", _SETTINGS)["pages_read"]
    ]


def test_each_medical_cell_says_where_its_quote_was_first_read() -> None:
    cells = _cells(mission_profiles.compare("leo"), MEDICAL)
    assert cells["leo"]["reused_from"] == [
        "«retardo de comunicaciones» de «órbita baja terrestre (estación espacial)»"
    ]
    # La frase lunar también se leyó para la estación: esa columna no se nombra en la de la Luna.
    levels = "marco de NASA leído: «Niveles de asistencia médica (Level of Care) IV y V»"
    eimo = "marco de NASA leído: «Operaciones médicas independientes de la Tierra (EIMO)»"
    assert cells["cislunar"]["reused_from"] == [
        "«regreso o evacuación» de «espacio cislunar (Orion, entre la Tierra y la Luna)»",
    ]
    assert cells["lunar-surface"]["reused_from"] == [
        levels, "«regreso o evacuación» de «superficie lunar»",
    ]
    assert cells["mars-transit"]["reused_from"] == [
        levels, eimo, "«retardo de comunicaciones» de «tránsito a Marte»",
        "«regreso o evacuación» de «tránsito a Marte»",
    ]
    assert cells["mars-surface"]["reused_from"] == [
        "«retardo de comunicaciones» de «superficie de Marte»",
        "«regreso o evacuación» de «superficie de Marte»", levels, eimo,
    ]
    # El perfil declarado de `/api/status` dice lo mismo que su columna de la matriz.
    for profile, cell in cells.items():
        served = mission_profiles.describe(profile, _SETTINGS)
        medical = next(item for item in served["aspects"] if item["key"] == MEDICAL)
        assert medical["reused_from"] == cell["reused_from"]
        assert all(
            item["reused_from"] == [] for item in served["aspects"] if item["key"] != MEDICAL
        )


def test_two_quotes_read_in_the_same_place_name_it_once(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _raw()
    # Las dos frases del retardo de Marte, las dos en su capacidad médica: un solo sitio.
    medical = _aspect(raw, "mars-transit", MEDICAL)
    medical["citations"] = copy.deepcopy(_aspect(raw, "mars-transit", "comm_delay")["citations"])
    monkeypatch.setattr(mission_profiles, "catalog", lambda: mission_profiles.validate(raw))
    cell = _cells(mission_profiles.compare("mars-transit"), MEDICAL)["mars-transit"]
    assert cell["reused_from"] == ["«retardo de comunicaciones» de «tránsito a Marte»"]


def test_only_the_declared_profile_column_is_marked() -> None:
    for declared in PROFILES:
        served = mission_profiles.compare(declared)
        assert [p["id"] for p in served["profiles"] if p["declared"]] == [declared]
        assert served["declared_id"] == declared and served["declared_text"] is None
        assert served["declared_note"] == mission_profiles.DECLARED_NOTE
    served = mission_profiles.compare("jupiter")
    assert not any(profile["declared"] for profile in served["profiles"])
    assert "no está en el catálogo" in served["declared_text"]


def test_a_cell_without_a_quote_says_emma_has_no_source(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _raw()
    _aspect(raw, "lunar-surface", MEDICAL).update(
        status=mission_profiles.UNVERIFIED, statement=None, citations=[],
        searched="Se buscó entre las frases ya leídas y ninguna lo dice.",
    )
    monkeypatch.setattr(mission_profiles, "catalog", lambda: mission_profiles.validate(raw))
    served = mission_profiles.compare("mars-transit")
    assert served["no_source"] == "EMMA no tiene fuente"
    cell = _cells(served, MEDICAL)["lunar-surface"]
    assert cell["text"] == "EMMA no tiene fuente"
    assert cell["statement"] is None and cell["citations"] == [] and cell["reused_from"] == []
    assert cell["searched"] == "Se buscó entre las frases ya leídas y ninguna lo dice."
    assert cell["status_text"] == "sin verificar"


def test_the_matrix_says_the_levels_of_care_are_not_assigned_to_any_profile() -> None:
    served = mission_profiles.compare("mars-transit")
    note = served["medical_note"]
    assert note.startswith("Nota de EMMA:")
    assert "IV y V" in note and "no se asignan" in note and "no una frase leída" in note
    assert "solo con frases que EMMA ya había leído" in served["reused_note"]


def test_emma_s_own_text_in_the_matrix_passes_the_language_filter() -> None:
    """Lo que añade la matriz: sus notas, sus rótulos y las casillas de la capacidad médica."""
    served = mission_profiles.compare("jupiter")
    medical = _cells(served, MEDICAL).values()
    texts = [
        served["note"], served["declared_text"], served["no_source"], served["reused_note"],
        served["medical_note"],
        *(item["label"] for item in served["aspects"]),
        *(profile["display"] for profile in served["profiles"]),
        *(cell["text"] for cell in medical),
        *(where for cell in medical for where in cell["reused_from"]),
    ]
    for text in texts:
        assert text_guard.check(text) == [], text


# --- La ruta y la invariante 5 --------------------------------------------------------------


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Un almacén con un escenario y un tiempo de luz de Marte fijo (sin red).

    El tiempo de luz se fija para que el factor de aislamiento NO sea 1: con él en 1 la prueba
    no distinguiría un aspecto que lo tocara de uno que no.
    """
    window = CommsWindow(dt.date(2026, 11, 14), 1.324, 11.01, "499")
    monkeypatch.setattr(routes, "_fetch_comms", lambda settings, epoch, target: (window, None))
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    client = TestClient(app)
    client.post("/api/simulate", params={"scenario": "progressive-insomnia", "days": 40})
    yield client
    app.dependency_overrides.clear()
    reset_store(None)


def test_the_route_serves_the_matrix_with_the_declared_column(
    api: TestClient, tmp_path: Path
) -> None:
    response = api.get("/api/mission/profiles")
    assert response.status_code == 200, response.text
    assert response.json() == mission_profiles.compare("mars-transit")
    app.dependency_overrides[get_settings] = lambda: Settings(
        cache_dir=tmp_path, offline=True, mission_profile="leo"
    )
    body = api.get("/api/mission/profiles").json()
    assert [p["id"] for p in body["profiles"] if p["declared"]] == ["leo"]


def test_changing_the_medical_aspect_changes_no_level_score_alert_nor_isolation(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = api.get("/api/status").json()
    assert reference["isolation_factor"] > 1.0
    assert reference["alerts"], "el escenario tiene que disparar al menos una alerta"
    raw = _raw()
    for profile in PROFILES:
        _aspect(raw, profile, MEDICAL).update(
            status=mission_profiles.UNVERIFIED, statement=None, citations=[],
            searched="Se buscó entre las frases ya leídas.",
        )
    monkeypatch.setattr(mission_profiles, "catalog", lambda: raw)
    other = api.get("/api/status").json()
    served = other["mission"].pop("profile")
    medical = next(item for item in served["aspects"] if item["key"] == MEDICAL)
    # El bloque del perfil sí cambia: la prueba no pasa porque el aspecto se ignore.
    assert medical["status"] == mission_profiles.UNVERIFIED
    expected = copy.deepcopy(reference)
    expected["mission"].pop("profile")
    assert other == expected


def test_nothing_that_decides_names_the_medical_aspect() -> None:
    """Solo el catálogo de perfiles nombra el aspecto; ninguna regla, umbral ni ruta lo lee."""
    app_dir = BACKEND / "app"
    naming = sorted(
        str(path.relative_to(app_dir)).replace("\\", "/")
        for path in app_dir.rglob("*.py")
        if MEDICAL in path.read_text(encoding="utf-8")
    )
    assert naming == ["evidence/mission_profiles.py"]
    # Y los que deciden no leen la comparación ni la lista de aspectos reutilizados.
    for folder in ("analysis", "advisor"):
        for module in sorted((app_dir / folder).glob("*.py")):
            source = module.read_text(encoding="utf-8")
            for name in ("REUSED_ONLY", "compare(", "MEDICAL_NOTE"):
                assert name not in source, f"{module.name} lee {name}"
