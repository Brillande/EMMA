"""Capa de entorno: efemerides, meteorologia espacial y dosimetria.

Las pruebas por defecto no tocan la red (respx intercepta httpx). Las marcadas
`live` golpean las APIs reales y quedan excluidas de CI; se ejecutan con
`pytest -m live` antes del evento para confirmar que las APIs no han cambiado.
"""

import datetime as dt
import urllib.error
from pathlib import Path

import httpx
import pytest
import requests
import respx
from astroquery.exceptions import TimeoutError as HorizonsTimeout

from app.core.cache import CachedPayload, FileCache, OfflineDataUnavailable
from app.core.config import Settings
from app.environment import donki
from app.environment.donki import (
    BASE_URL as DONKI_URL,
)
from app.environment.donki import (
    DonkiClient,
    EventType,
    Severity,
    severity_from_flare_class,
)
from app.environment.ephemeris import (
    AUTONOMY_THRESHOLD_MINUTES,
    CommsWindow,
    light_minutes_from_au,
)
from app.environment.radlab import (
    BASE_URL as RADLAB_URL,
)
from app.environment.radlab import (
    DOSE_FIELD_PARAM,
    DoseSample,
    RadLabClient,
    build_query,
    integrate_dose_msv,
    parse_split_table,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(cache_dir=tmp_path, nasa_api_key="TEST_KEY")


# --------------------------------------------------------------------------- #
# Efemerides / tiempo de luz
# --------------------------------------------------------------------------- #


def test_light_time_matches_known_values() -> None:
    """Contrastado con los valores medidos en el spike contra JPL Horizons."""
    assert light_minutes_from_au(1.324362) == pytest.approx(11.01, abs=0.01)
    assert light_minutes_from_au(0.678033) == pytest.approx(5.64, abs=0.01)
    assert light_minutes_from_au(2.348087) == pytest.approx(19.53, abs=0.01)


def test_hackathon_day_requires_autonomy() -> None:
    """El 14-nov-2026 Marte esta a 1,324 UA: 22 min ida y vuelta, sin consulta viva."""
    window = CommsWindow(
        epoch=dt.date(2026, 11, 14), distance_au=1.324362,
        one_way_minutes=11.01, target="499",
    )
    assert window.round_trip_minutes == pytest.approx(22.02, abs=0.01)
    assert window.autonomy_required
    assert "Sin consulta en vivo" in window.describe()


def test_near_earth_does_not_require_autonomy() -> None:
    window = CommsWindow(
        epoch=dt.date(2026, 11, 14), distance_au=0.01, one_way_minutes=0.08, target="301"
    )
    assert not window.autonomy_required
    assert "disponible" in window.describe()


def test_autonomy_threshold_is_crossed_where_expected() -> None:
    below = CommsWindow(dt.date(2026, 1, 1), 0.1, AUTONOMY_THRESHOLD_MINUTES / 2 - 0.1, "499")
    above = CommsWindow(dt.date(2026, 1, 1), 0.1, AUTONOMY_THRESHOLD_MINUTES / 2 + 0.1, "499")
    assert not below.autonomy_required
    assert above.autonomy_required


def test_comms_window_roundtrip() -> None:
    original = CommsWindow(dt.date(2026, 11, 14), 1.324362, 11.01, "499")
    assert CommsWindow.from_dict(original.to_dict()) == original


# --------------------------------------------------------------------------- #
# DONKI
# --------------------------------------------------------------------------- #

SEP_PAYLOAD = [
    {
        "sepID": "2025-10-22T00:09:00-SEP-001",
        "eventTime": "2025-10-22T00:09Z",
        "instruments": [{"displayName": "STEREO A: IMPACT 13-100 MeV"}],
        "linkedEvents": [{"activityID": "2025-10-21T20:24:00-CME-001"}],
        "link": "https://example.invalid/sep/1",
    }
]

FLR_PAYLOAD = [
    {
        "flrID": "2026-07-22T06:27:00-FLR-001",
        "beginTime": "2026-07-22T06:27Z",
        "classType": "M3.6",
        "instruments": [{"displayName": "GOES-S: EXIS 1.0-8.0"}],
        "linkedEvents": None,
        "link": "https://example.invalid/flr/1",
    }
]


@pytest.mark.parametrize(
    ("flare_class", "expected"),
    [
        ("A1.0", Severity.NOMINAL), ("B5.2", Severity.NOMINAL),
        ("C4.1", Severity.ELEVATED), ("M3.6", Severity.HIGH),
        ("X9.3", Severity.SEVERE), (None, Severity.NOMINAL), ("", Severity.NOMINAL),
    ],
)
def test_flare_class_maps_to_severity(flare_class: str | None, expected: Severity) -> None:
    assert severity_from_flare_class(flare_class) is expected


@respx.mock
def test_sep_events_are_normalized(settings: Settings) -> None:
    respx.get(f"{DONKI_URL}/SEP").mock(return_value=httpx.Response(200, json=SEP_PAYLOAD))
    client = DonkiClient(settings=settings)

    result = client.events(EventType.SEP, dt.date(2025, 10, 1), dt.date(2025, 11, 1))
    event = result.data[0]

    assert not result.from_cache
    assert event.event_type is EventType.SEP
    assert event.severity is Severity.HIGH
    # `linkedEvents` reconstruye la cascada CME -> SPE.
    assert event.linked_event_ids == ("2025-10-21T20:24:00-CME-001",)
    assert event.time == dt.datetime(2025, 10, 22, 0, 9, tzinfo=dt.UTC)


def test_a_year_is_asked_in_ranges_donki_accepts() -> None:
    """DONKI responde 400 a más de 60 días (2026-11-13): un año va en tramos contiguos."""
    start, end = dt.date(2025, 11, 13), dt.date(2026, 11, 13)
    ranges = donki.query_ranges(start, end)
    assert ranges[0][0] == start and ranges[-1][1] == end
    for (_first, last), (following, _) in zip(ranges, ranges[1:], strict=False):
        assert following == last + dt.timedelta(days=1)
    assert all((last - first).days + 1 <= donki.MAX_RANGE_DAYS for first, last in ranges)
    assert donki.query_ranges(end, end) == [(end, end)]


@respx.mock
def test_a_long_window_joins_every_range(settings: Settings) -> None:
    """Cada tramo se pide y sus eventos se juntan; uno repetido entre tramos sale una vez."""
    later = {**SEP_PAYLOAD[0], "sepID": "2026-09-01T00:00:00-SEP-001",
             "eventTime": "2026-09-01T00:00Z"}

    def answer(request: httpx.Request) -> httpx.Response:
        first = dt.date.fromisoformat(request.url.params["startDate"])
        last = dt.date.fromisoformat(request.url.params["endDate"])
        assert (last - first).days + 1 <= donki.MAX_RANGE_DAYS
        found = [e for e in [*SEP_PAYLOAD, later] if first <= dt.date.fromisoformat(
            e["eventTime"][:10]) <= last]
        return httpx.Response(200, json=found + found)

    route = respx.get(f"{DONKI_URL}/SEP").mock(side_effect=answer)
    result = DonkiClient(settings=settings).events(
        EventType.SEP, dt.date(2025, 10, 1), dt.date(2026, 10, 1)
    )
    assert route.call_count == len(donki.query_ranges(dt.date(2025, 10, 1), dt.date(2026, 10, 1)))
    assert [e.event_id for e in result.data] == [
        "2025-10-22T00:09:00-SEP-001", "2026-09-01T00:00:00-SEP-001"
    ]


@respx.mock
def test_flare_events_carry_class(settings: Settings) -> None:
    respx.get(f"{DONKI_URL}/FLR").mock(return_value=httpx.Response(200, json=FLR_PAYLOAD))
    client = DonkiClient(settings=settings)

    event = client.events(EventType.FLR, dt.date(2026, 7, 1), dt.date(2026, 8, 1)).data[0]

    assert event.flare_class == "M3.6"
    assert event.severity is Severity.HIGH
    assert event.linked_event_ids == ()


@respx.mock
def test_network_failure_falls_back_to_cache(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un dato viejo con su edad declarada es mejor que ningun dato."""
    # Caché caducada al instante: si no, la segunda llamada ni intenta salir.
    monkeypatch.setattr(donki, "FRESH_FOR", dt.timedelta(0))
    route = respx.get(f"{DONKI_URL}/SEP")
    route.mock(return_value=httpx.Response(200, json=SEP_PAYLOAD))
    client = DonkiClient(settings=settings)
    window = (dt.date(2025, 10, 1), dt.date(2025, 11, 1))
    client.events(EventType.SEP, *window)  # llena la cache

    route.mock(side_effect=httpx.ConnectError("sin enlace con la Tierra"))
    result = client.events(EventType.SEP, *window)

    assert result.from_cache
    assert result.data[0].event_id == "2025-10-22T00:09:00-SEP-001"


@respx.mock
def test_an_event_time_without_zone_falls_back_and_is_never_cached(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una hora sin zona de DONKI no se guarda: antes quedaba en caché y cada `/api/status`
    lanzaba `TypeError`, también sin red (auditoría run-2,
    `emma:environment:naive-external-timestamp-cache-poison`). Se trata como una consulta fallida:
    la caché anterior, con su edad."""
    monkeypatch.setattr(donki, "FRESH_FOR", dt.timedelta(0))
    route = respx.get(f"{DONKI_URL}/SEP")
    route.mock(return_value=httpx.Response(200, json=SEP_PAYLOAD))
    client = DonkiClient(settings=settings)
    window = (dt.date(2025, 10, 1), dt.date(2025, 11, 1))
    client.events(EventType.SEP, *window)

    naive = [{**SEP_PAYLOAD[0], "eventTime": "2025-10-22T00:09"}]
    route.mock(return_value=httpx.Response(200, json=naive))
    result = client.events(EventType.SEP, *window)
    assert result.from_cache
    assert result.data[0].time.tzinfo is not None
    # Lo guardado sigue siendo lo bueno: la respuesta ilegible no lo pisó.
    cached = client.cache.get(f"donki:{EventType.SEP}:{window[0]}:{window[1]}")
    assert cached is not None and cached.data[0]["time"].endswith("+00:00")


def test_a_cache_written_before_the_rule_is_read_as_utc() -> None:
    event = donki.SolarEvent.from_dict({
        "event_id": "x", "event_type": "SEP", "time": "2025-10-22T00:09:00",
        "severity": "high", "instruments": [], "linked_event_ids": [], "flare_class": None,
        "link": "",
    })
    assert event.time == dt.datetime(2025, 10, 22, 0, 9, tzinfo=dt.UTC)


@respx.mock
def test_a_recent_cache_is_used_without_going_out(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con red, una consulta reciente no se repite (antes cada estado llamaba a DONKI y con la
    cuota agotada la consola esperaba); una caducada sí se vuelve a pedir."""
    route = respx.get(f"{DONKI_URL}/SEP").mock(
        return_value=httpx.Response(200, json=SEP_PAYLOAD)
    )
    client = DonkiClient(settings=settings)
    window = (dt.date(2025, 10, 1), dt.date(2025, 11, 1))
    client.events(EventType.SEP, *window)
    again = client.events(EventType.SEP, *window)
    assert again.from_cache and route.call_count == 1
    monkeypatch.setattr(donki, "FRESH_FOR", dt.timedelta(0))
    assert not client.events(EventType.SEP, *window).from_cache
    assert route.call_count == 2


@respx.mock
def test_a_recent_radlab_series_is_not_requested_again(settings: Settings) -> None:
    route = respx.get(RADLAB_URL).mock(return_value=httpx.Response(200, json=RADLAB_PAYLOAD))
    client = RadLabClient(settings=settings)
    client.dose_series(dt.date(2022, 4, 1), dt.date(2022, 4, 2))
    assert client.dose_series(dt.date(2022, 4, 1), dt.date(2022, 4, 2)).from_cache
    assert route.call_count == 1


@respx.mock
def test_network_failure_without_cache_raises(settings: Settings) -> None:
    respx.get(f"{DONKI_URL}/SEP").mock(side_effect=httpx.ConnectError("sin enlace"))
    client = DonkiClient(settings=settings)

    with pytest.raises(OfflineDataUnavailable, match="sin cache"):
        client.events(EventType.SEP, dt.date(2025, 10, 1), dt.date(2025, 11, 1))


@respx.mock
def test_offline_mode_never_touches_the_network(settings: Settings, tmp_path: Path) -> None:
    route = respx.get(f"{DONKI_URL}/SEP")
    route.mock(return_value=httpx.Response(200, json=SEP_PAYLOAD))
    window = (dt.date(2025, 10, 1), dt.date(2025, 11, 1))
    DonkiClient(settings=settings).events(EventType.SEP, *window)
    calls_before = route.call_count

    offline = Settings(cache_dir=tmp_path, offline=True)
    result = DonkiClient(settings=offline).events(EventType.SEP, *window)

    assert result.from_cache
    assert route.call_count == calls_before, "el modo offline no debe emitir peticiones"


def test_offline_without_cache_is_an_explicit_failure(tmp_path: Path) -> None:
    offline = Settings(cache_dir=tmp_path, offline=True)
    with pytest.raises(OfflineDataUnavailable, match="offline"):
        DonkiClient(settings=offline).events(
            EventType.SEP, dt.date(2025, 10, 1), dt.date(2025, 11, 1)
        )


@respx.mock
def test_offline_the_next_day_uses_yesterdays_query_with_its_age(
    settings: Settings, tmp_path: Path
) -> None:
    """Lógica 1 (2026-11-11): la ventana corre con el día y la clave llevaba sus fechas.

    Sin red, la consulta de ayer no casaba con la clave de hoy: «sin datos de DONKI» (o la
    instantánea del paquete, más vieja) con una caché de un día en el disco.
    """
    respx.get(f"{DONKI_URL}/SEP").mock(return_value=httpx.Response(200, json=SEP_PAYLOAD))
    yesterday = (dt.date(2024, 11, 1), dt.date(2025, 11, 1))
    stored = DonkiClient(settings=settings).events(EventType.SEP, *yesterday)

    offline = Settings(cache_dir=tmp_path, offline=True)
    today = (dt.date(2024, 11, 2), dt.date(2025, 11, 2))
    result = DonkiClient(settings=offline).events(EventType.SEP, *today)

    assert result.from_cache
    assert result.fetched_at == stored.fetched_at, "con la edad de la consulta de ayer"
    assert [event.event_id for event in result.data] == ["2025-10-22T00:09:00-SEP-001"]


@respx.mock
def test_an_earlier_query_does_not_vouch_for_days_it_never_asked(
    settings: Settings, tmp_path: Path
) -> None:
    """Una ventana más estrecha, o que empieza después, no dice nada del tramo que no pidió."""
    respx.get(f"{DONKI_URL}/SEP").mock(return_value=httpx.Response(200, json=SEP_PAYLOAD))
    DonkiClient(settings=settings).events(EventType.SEP, dt.date(2025, 10, 1), dt.date(2025, 11, 1))
    offline = DonkiClient(settings=Settings(cache_dir=tmp_path, offline=True))
    with pytest.raises(OfflineDataUnavailable):
        offline.events(EventType.SEP, dt.date(2024, 11, 2), dt.date(2025, 11, 2))
    with pytest.raises(OfflineDataUnavailable):
        offline.events(EventType.SEP, dt.date(2025, 9, 30), dt.date(2025, 10, 31))


@respx.mock
def test_a_radlab_body_that_is_not_json_is_unavailable_not_a_bad_window(
    settings: Settings,
) -> None:
    respx.get(RADLAB_URL).mock(return_value=httpx.Response(200, content=b"<html>"))
    with pytest.raises(OfflineDataUnavailable, match="sin JSON"):
        RadLabClient(settings=settings).dose_series(dt.date(2022, 4, 1), dt.date(2022, 4, 2))


@respx.mock
def test_a_radlab_json_error_object_is_unavailable_not_a_crash(settings: Settings) -> None:
    """Lógica 1: un 200 con un objeto de error caía con `KeyError` (500 en la ruta de dosis)."""
    respx.get(RADLAB_URL).mock(return_value=httpx.Response(200, json={"error": "cuota"}))
    with pytest.raises(OfflineDataUnavailable, match="sin JSON"):
        RadLabClient(settings=settings).dose_series(dt.date(2022, 4, 1), dt.date(2022, 4, 2))


@respx.mock
def test_a_body_that_is_not_json_is_a_failed_query_not_a_crash(settings: Settings) -> None:
    """Lógica 1: un 200 sin JSON salía como `JSONDecodeError` (500 en `/api/space-weather`)."""
    respx.get(f"{DONKI_URL}/SEP").mock(return_value=httpx.Response(200, content=b""))
    with pytest.raises(OfflineDataUnavailable, match="sin JSON"):
        DonkiClient(settings=settings).events(
            EventType.SEP, dt.date(2025, 10, 1), dt.date(2025, 11, 1)
        )


# --------------------------------------------------------------------------- #
# RadLab
# --------------------------------------------------------------------------- #

RADLAB_PAYLOAD = {
    "columns": ["timestamp", "instrument_id", "absorbed_dose_rate", "instrument", "spacecraft"],
    "index": [0, 1, 2],
    "data": [
        ["2022-04-01T00:00:00", "DosTel1", 2.0, "DosTel1", "ISS"],
        ["2022-04-01T01:00:00", "DosTel1", 4.0, "DosTel1", "ISS"],
        ["2022-04-01T02:00:00", "DosTel1", 6.0, "DosTel1", "ISS"],
    ],
}


def test_build_query_uses_boolean_syntax() -> None:
    query = build_query("ISS", "DosTel", dt.date(2022, 4, 1), dt.date(2022, 4, 2))
    assert query == (
        "(spacecraft=ISS)AND(instrument=DosTel)"
        "AND(timestamp>=2022-04-01)AND(timestamp<=2022-04-02)"
    )


def test_dose_field_param_keeps_its_trailing_space() -> None:
    """Regresion: sin el espacio final la API responde `Invalid key: fields+`."""
    assert DOSE_FIELD_PARAM == "fields "
    assert DOSE_FIELD_PARAM.endswith(" ")


def test_parse_split_table() -> None:
    samples = parse_split_table(RADLAB_PAYLOAD)
    assert len(samples) == 3
    assert samples[0].absorbed_dose_rate == 2.0
    assert samples[0].spacecraft == "ISS"


def test_missing_dose_column_gives_an_actionable_error() -> None:
    """RadLab ignora en silencio los campos que no puede servir."""
    payload = {
        "columns": ["timestamp", "instrument", "spacecraft"],
        "index": [0],
        "data": [["2022-04-01T00:00:00", "DosTel1", "ISS"]],
    }
    with pytest.raises(ValueError, match="fields"):
        parse_split_table(payload)


def test_null_dose_values_are_skipped_not_interpolated() -> None:
    payload = {
        "columns": ["timestamp", "instrument_id", "absorbed_dose_rate", "instrument", "spacecraft"],
        "index": [0, 1],
        "data": [
            ["2022-04-01T00:00:00", "DosTel1", None, "DosTel1", "ISS"],
            ["2022-04-01T01:00:00", "DosTel1", 3.0, "DosTel1", "ISS"],
        ],
    }
    samples = parse_split_table(payload)
    assert len(samples) == 1


def test_integrate_dose_trapezoidal() -> None:
    """2->4 uGy/h en 1 h = 3 uGy; 4->6 en 1 h = 5 uGy. Total 8 uGy = 0,008 mGy.

    La dosis **equivalente** aplica ademas el factor de calidad medio de mision.
    La version anterior devolvia 0,008 mSv usando Q = 1, y eso subestimaba la
    dosis unas dos veces y media; ver `app/environment/dosimetry.py`.
    """
    samples = parse_split_table(RADLAB_PAYLOAD)
    assert integrate_dose_msv(samples) == pytest.approx(0.008 * 2.38)


def test_integrate_dose_handles_gaps() -> None:
    """Los huecos de instrumento no deben asumir cadencia fija."""
    samples = [
        DoseSample(dt.datetime(2022, 4, 1, 0, 0), "DosTel1", "ISS", 2.0),
        DoseSample(dt.datetime(2022, 4, 1, 10, 0), "DosTel1", "ISS", 2.0),  # hueco de 10 h
    ]
    assert integrate_dose_msv(samples) == pytest.approx(0.020 * 2.38)


@pytest.mark.parametrize("sample_count", [0, 1])
def test_integrate_dose_needs_two_points(sample_count: int) -> None:
    samples = [DoseSample(dt.datetime(2022, 4, 1), "DosTel1", "ISS", 2.0)] * sample_count
    assert integrate_dose_msv(samples) == 0.0


def test_window_larger_than_limit_is_rejected(settings: Settings) -> None:
    """Sin este limite la API llega a devolver cientos de MB."""
    client = RadLabClient(settings=settings)
    with pytest.raises(ValueError, match="excede el máximo"):
        client.dose_series(dt.date(2022, 1, 1), dt.date(2022, 6, 1))


def test_inverted_window_is_rejected(settings: Settings) -> None:
    client = RadLabClient(settings=settings)
    with pytest.raises(ValueError, match="invertida"):
        client.dose_series(dt.date(2022, 4, 2), dt.date(2022, 4, 1))


@respx.mock
def test_dose_series_end_to_end(settings: Settings) -> None:
    respx.get(RADLAB_URL).mock(return_value=httpx.Response(200, json=RADLAB_PAYLOAD))
    client = RadLabClient(settings=settings)

    result = client.dose_series(dt.date(2022, 4, 1), dt.date(2022, 4, 2))

    assert len(result.data) == 3
    assert not result.from_cache
    assert result.source == "OSDR RadLab"


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #


def test_cache_reports_age(tmp_path: Path) -> None:
    cache = FileCache(tmp_path)
    stored = cache.put("k", {"v": 1}, source="test")
    assert not stored.from_cache
    assert stored.describe_age() == "ahora mismo"

    retrieved = cache.get("k")
    assert retrieved is not None
    assert retrieved.from_cache
    assert retrieved.data == {"v": 1}


def test_corrupt_cache_is_treated_as_absent(tmp_path: Path) -> None:
    cache = FileCache(tmp_path)
    cache.put("k", {"v": 1}, source="test")
    next(tmp_path.glob("*.json")).write_text("{ esto no es json", encoding="utf-8")
    assert cache.get("k") is None


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    assert FileCache(tmp_path).get("nunca-guardado") is None


# --------------------------------------------------------------------------- #
# Pruebas contra las APIs reales (excluidas de CI)
# --------------------------------------------------------------------------- #


@pytest.mark.live
def test_live_radlab_contract(tmp_path: Path) -> None:
    """Confirma que RadLab sigue aceptando `fields ` y devolviendo la dosis."""
    client = RadLabClient(settings=Settings(cache_dir=tmp_path))
    result = client.dose_series(dt.date(2022, 4, 1), dt.date(2022, 4, 2))
    assert result.data, "RadLab devolvio una serie vacía"
    assert all(sample.absorbed_dose_rate > 0 for sample in result.data)


@pytest.mark.live
def test_live_donki_contract(tmp_path: Path) -> None:
    client = DonkiClient(settings=Settings(cache_dir=tmp_path))
    end = dt.date.today()
    result = client.events(EventType.FLR, end - dt.timedelta(days=60), end)
    assert isinstance(result.data, list)


@pytest.mark.live
def test_live_ephemeris_contract(tmp_path: Path) -> None:
    """Valida el tiempo de luz del dia del hackathon contra JPL Horizons."""
    from app.environment.ephemeris import EphemerisClient

    client = EphemerisClient(settings=Settings(cache_dir=tmp_path))
    window = client.comms_window(dt.date(2026, 11, 14), "499").data
    assert window.distance_au == pytest.approx(1.3244, abs=0.001)
    assert window.round_trip_minutes == pytest.approx(22.03, abs=0.05)
    assert window.autonomy_required


def test_cache_age_in_seconds_agrees_with_its_text() -> None:
    """La interfaz decide con el numero y muestra el texto: no pueden discrepar."""
    fetched = dt.datetime.now(dt.UTC) - dt.timedelta(hours=7, minutes=5)
    payload = CachedPayload(data=None, fetched_at=fetched, source="test", from_cache=True)

    assert 7 * 3600 + 5 * 60 <= payload.age_seconds < 7 * 3600 + 6 * 60
    assert payload.describe_age() == "hace 7 h"


# --------------------------------------------------------------------------- #
# Efemerides: fallos de la fuente
# --------------------------------------------------------------------------- #


def _failing_fetch(exc: BaseException):
    def fetch(self: object, epoch: dt.date, target: str) -> CommsWindow:
        raise exc

    return fetch


@pytest.mark.parametrize(
    "exc",
    [
        requests.ConnectionError("red caida"),
        urllib.error.URLError("sin ruta"),
        HorizonsTimeout("lento"),
    ],
)
def test_a_network_failure_is_offline_not_a_crash(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, exc: BaseException
) -> None:
    """Un corte de red durante la consulta salia como error del servidor."""
    from app.environment.ephemeris import EphemerisClient

    monkeypatch.setattr(EphemerisClient, "_fetch", _failing_fetch(exc))
    with pytest.raises(OfflineDataUnavailable):
        EphemerisClient(settings=settings).comms_window(dt.date(2026, 11, 14), "499")


def test_a_broken_answer_is_not_disguised_as_no_network(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from astroquery.exceptions import RemoteServiceError

    from app.environment.ephemeris import EphemerisClient, HorizonsResponseError

    monkeypatch.setattr(
        EphemerisClient, "_fetch", _failing_fetch(RemoteServiceError("Ambiguous target"))
    )
    with pytest.raises(HorizonsResponseError):
        EphemerisClient(settings=settings).comms_window(dt.date(2026, 11, 14), "499")


def test_a_network_failure_still_uses_the_cache(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con la efemeride de ese dia en cache, un corte de red no se nota."""
    from app.environment.ephemeris import EphemerisClient

    epoch = dt.date(2026, 11, 14)
    good = CommsWindow(epoch=epoch, distance_au=1.3244, one_way_minutes=11.01, target="499")
    monkeypatch.setattr(EphemerisClient, "_fetch", lambda self, e, t: good)
    EphemerisClient(settings=settings).comms_window(epoch, "499")

    monkeypatch.setattr(
        EphemerisClient, "_fetch", _failing_fetch(requests.ConnectionError())
    )
    payload = EphemerisClient(settings=settings).comms_window(epoch, "499")
    assert payload.from_cache
    assert payload.data.one_way_minutes == pytest.approx(11.01)
