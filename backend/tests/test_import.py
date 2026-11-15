"""Importacion de exports de Apple Health y Google Fit por la API.

Los dos adaptadores existian, con pruebas, pero ningun endpoint los usaba: la via de
entrada de datos de salud reales del propio tripulante era inalcanzable. Ahora pasan
por el ledger como cualquier otra lectura, y lo que no se puede importar se dice.
"""

import time
import tracemalloc
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.api.routes import new_store, reset_store
from app.core.config import Settings, get_settings
from app.ingest.wearable import WearableAdapter
from app.main import app

XML = {"content-type": "application/xml"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    reset_store(new_store())
    app.dependency_overrides[get_settings] = lambda: Settings(cache_dir=tmp_path, offline=True)
    yield TestClient(app)
    app.dependency_overrides.clear()
    reset_store(None)


def _export(*records: str) -> bytes:
    # Un export real trae una DTD interna con declaraciones ATTLIST: se reproduce.
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE HealthData [\n<!ATTLIST Record type CDATA #REQUIRED>\n]>\n"
        '<HealthData locale="es_ES">' + "".join(records) + "</HealthData>"
    ).encode()


_UNITS = {
    "HeartRate": "count/min",
    "OxygenSaturation": "%",
    "StepCount": "count",
    "BodyMass": "kg",
    "BodyTemperature": "degC",
}


def _record(
    kind: str, value: str, date: str = "2026-09-01 08:00:00 +0000", unit: str | None = None
) -> str:
    unit = _UNITS.get(kind, "") if unit is None else unit
    unit_attr = f' unit="{unit}"' if unit else ""
    return (
        f'<Record type="HKQuantityTypeIdentifier{kind}"{unit_attr} value="{value}" '
        f'startDate="{date}"/>'
    )


def test_an_apple_health_export_is_imported_and_audited(client: TestClient) -> None:
    export = _export(
        _record("HeartRate", "62"),
        _record("OxygenSaturation", "0.97", "2026-09-01 08:01:00 +0000"),
        _record("StepCount", "120"),  # tipo que no se importa: no es un descarte
    )

    response = client.post("/api/import/apple-health", content=export, headers=XML)

    assert response.status_code == 201
    body = response.json()
    assert body["imported"] == 2
    assert body["by_indicator"] == {"heart-rate": 1, "oxygen-saturation": 1}
    assert body["rejected"] == 0
    observations = client.get("/api/observations").json()["observations"]
    values = sorted(item["valueQuantity"]["value"] for item in observations)
    assert values == [62.0, 97.0]  # la SpO2 llega como fraccion y se guarda en %
    audit = client.get("/api/audit").json()
    assert audit["total_entries"] == 2
    assert audit["integrity_ok"] is True


def test_rejected_readings_are_reported_not_dropped(client: TestClient) -> None:
    """Una constante vital descartada tiene que quedar dicha, no perderse en silencio."""
    export = _export(
        _record("HeartRate", "62"),
        _record("HeartRate", "abc"),
        _record("HeartRate", "5000"),
        _record("HeartRate", "70", "14/11/2026"),
    )

    body = client.post("/api/import/apple-health", content=export, headers=XML).json()

    assert body["imported"] == 1
    assert body["rejected"] == 3
    reasons = " ".join(body["rejections"])
    assert "no numérico" in reasons
    assert "registro 3" in reasons and "registro 4" in reasons


def test_malformed_xml_is_a_422(client: TestClient) -> None:
    response = client.post("/api/import/apple-health", content=b"<HealthData><Rec", headers=XML)
    assert response.status_code == 422


def test_billion_laughs_is_refused_quickly(client: TestClient) -> None:
    """Expansion exponencial de entidades: 422 y rapido, sin agotar memoria.

    QUE CAPA LO CORTA, EXACTAMENTE. Esta peticion **no llega a expat**: `_xml_text`
    rechaza cualquier export que contenga `<!ENTITY` antes de intentar el parseo. El
    limite de amplificacion de expat sigue ahi, detras, y tiene su propia prueba
    —`test_expat_still_cuts_the_amplification_behind_the_filter`—, porque una defensa
    que ninguna prueba ejerce es una defensa que nadie sabe si sigue viva.
    """
    entities = '<!ENTITY a "aaaaaaaaaa">' + "".join(
        f'<!ENTITY {chr(98 + i)} "{("&" + chr(97 + i) + ";") * 10}">' for i in range(9)
    )
    bomb = (
        f'<?xml version="1.0"?><!DOCTYPE l [{entities}]><HealthData>'
        '<Record type="HKQuantityTypeIdentifierHeartRate" value="&j;" '
        'startDate="2026-11-14 08:00:00 +0000"/></HealthData>'
    ).encode()

    started = time.perf_counter()
    response = client.post("/api/import/apple-health", content=bomb, headers=XML)

    assert response.status_code == 422
    assert time.perf_counter() - started < 2.0


def test_external_entities_are_not_resolved(client: TestClient, tmp_path: Path) -> None:
    """Un fichero local no sale por la respuesta ni entra en el almacen.

    La entidad va en `value`, que es lo que el importador lee: la version anterior de
    esta prueba la ponia en el texto del registro, que nadie lee, y no podia fallar.
    Aqui tambien corta `_xml_text` por la declaracion `<!ENTITY`, antes del parseo; lo
    que la prueba afirma es el resultado —nada se filtra—, no que lo impida expat.
    """
    secret = tmp_path / "secreto.txt"
    secret.write_text("CONTENIDO-SECRETO-XYZ", encoding="utf-8")
    xxe = (
        f'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "{secret.as_uri()}">]>'
        '<HealthData><Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" '
        'value="&x;" startDate="2026-09-01 08:00:00 +0000"/></HealthData>'
    ).encode()

    response = client.post("/api/import/apple-health", content=xxe, headers=XML)

    assert response.status_code == 422
    assert "CONTENIDO-SECRETO-XYZ" not in response.text
    assert client.get("/api/audit").json()["total_entries"] == 0


def test_an_oversized_export_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "MAX_IMPORT_BYTES", 100)
    export = _export(_record("HeartRate", "62"), _record("HeartRate", "63"))

    assert client.post("/api/import/apple-health", content=export, headers=XML).status_code == 413
    assert client.get("/api/audit").json()["total_entries"] == 0


def test_an_export_with_nothing_importable_is_a_422(client: TestClient) -> None:
    export = _export(_record("StepCount", "120"), _record("HeartRate", "abc"))

    response = client.post("/api/import/apple-health", content=export, headers=XML)

    assert response.status_code == 422
    assert client.get("/api/audit").json()["total_entries"] == 0


def _point(kind: str, value: float | None, nanos: int | None) -> dict[str, object]:
    point: dict[str, object] = {"dataTypeName": kind, "value": [{"fpVal": value}]}
    if nanos is not None:
        point["startTimeNanos"] = str(nanos)
    return point


def test_a_google_fit_dataset_is_imported(client: TestClient) -> None:
    nanos = 1_788_249_600_000_000_000  # 2026-09-01 08:00 UTC
    dataset = {
        "point": [
            _point("com.google.heart_rate.bpm", 70.0, nanos),
            _point("com.google.step_count.delta", 500.0, nanos),
            _point("com.google.heart_rate.bpm", 71.0, None),  # sin instante: se dice
        ]
    }

    response = client.post("/api/import/google-fit", json=dataset)

    assert response.status_code == 201
    body = response.json()
    assert body["imported"] == 1
    assert body["rejected"] == 1
    assert "startTimeNanos" in body["rejections"][0]


def test_a_google_fit_body_without_points_is_a_422(client: TestClient) -> None:
    assert client.post("/api/import/google-fit", json={"otra": 1}).status_code == 422
    assert client.post("/api/import/google-fit", json={"point": "no"}).status_code == 422


# --------------------------------------------------------------------------- #
# Quinta revision (2026-09-22)
# --------------------------------------------------------------------------- #


def test_units_are_converted_and_unknown_ones_reported(client: TestClient) -> None:
    export = _export(
        _record("BodyMass", "170", unit="lb"),
        _record("BodyTemperature", "98.6", unit="degF"),
        _record("BodyMass", "11", unit="st"),
        _record("HeartRate", "64", unit=""),
    )

    body = client.post("/api/import/apple-health", content=export, headers=XML).json()

    assert body["imported"] == 2
    assert body["rejected"] == 2
    values = sorted(
        round(item["valueQuantity"]["value"], 2)
        for item in client.get("/api/observations").json()["observations"]
    )
    assert values == [37.0, 77.11]


def test_incredible_dates_are_reported_not_imported(client: TestClient) -> None:
    export = _export(
        _record("HeartRate", "60", "2099-01-01 08:00:00 +0000"),
        _record("HeartRate", "61", "0001-01-01 00:00:00 +2359"),
        _record("HeartRate", "62", "9999-12-31 23:59:59 -2359"),
        _record("HeartRate", "63"),
    )

    response = client.post("/api/import/apple-health", content=export, headers=XML)

    assert response.status_code == 201
    assert response.json()["imported"] == 1
    assert response.json()["rejected"] == 3


def test_entity_declarations_are_refused(client: TestClient) -> None:
    """Amplificacion lineal: expat permite hasta 100x, y 24 MB de XML llevaban el proceso
    a 2,9 GB. Un export de Apple no declara entidades, asi que no se admite ninguna."""
    expansion = "&e;" * 1000
    export = (
        '<?xml version="1.0"?><!DOCTYPE HealthData [<!ENTITY e "xxxxxxxxxx">]><HealthData>'
        f'<Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" value="62" '
        f'startDate="2026-09-01 08:00:00 +0000">{expansion}</Record></HealthData>'
    ).encode()

    response = client.post("/api/import/apple-health", content=export, headers=XML)

    assert response.status_code == 422
    assert "entidad" in response.json()["detail"]


@pytest.mark.parametrize(
    "export",
    [
        _export(_record("HeartRate", "62")).decode().encode("utf-16"),
        b'<?xml version="1.0" encoding="bogus-enc"?><HealthData></HealthData>',
        b'<?xml version="1.0" encoding="utf-7"?><HealthData></HealthData>',
    ],
    ids=["utf-16", "codificacion-inventada", "utf-7"],
)
def test_odd_encodings_are_a_422_not_a_crash(client: TestClient, export: bytes) -> None:
    assert client.post("/api/import/apple-health", content=export, headers=XML).status_code == 422


def test_too_many_readings_are_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "MAX_IMPORT_RECORDS", 2)
    export = _export(*(_record("HeartRate", str(60 + i)) for i in range(3)))

    assert client.post("/api/import/apple-health", content=export, headers=XML).status_code == 413
    assert client.get("/api/audit").json()["total_entries"] == 0


def test_a_google_fit_body_that_is_not_json_is_a_422(client: TestClient) -> None:
    headers = {"content-type": "application/json"}
    for body in (b'{"point": [Infinity]}', b"{no es json", b"[1, 2]"):
        response = client.post("/api/import/google-fit", content=body, headers=headers)
        assert response.status_code == 422


def test_an_oversized_google_fit_body_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "MAX_IMPORT_BYTES", 50)
    dataset = {"point": [_point("com.google.heart_rate.bpm", 70.0, 1_788_249_600_000_000_000)]}

    assert client.post("/api/import/google-fit", json=dataset).status_code == 413


# --------------------------------------------------------------------------- #
# Sexta revision (2026-09-22)
# --------------------------------------------------------------------------- #


def test_expat_still_cuts_the_amplification_behind_the_filter() -> None:
    """La segunda linea, ejercida sin el filtro textual que hoy la tapa.

    `_xml_text` rechaza `<!ENTITY` antes del parseo, asi que ninguna prueba que pase
    por el endpoint toca el limite de amplificacion de expat. Esta llama al adaptador
    directamente: si alguien relaja el filtro, o cambia la version de expat, aqui se
    entera.
    """
    entities = '<!ENTITY a "aaaaaaaaaa">' + "".join(
        f'<!ENTITY {chr(98 + i)} "{("&" + chr(97 + i) + ";") * 10}">' for i in range(9)
    )
    bomb = (
        f'<?xml version="1.0"?><!DOCTYPE l [{entities}]><HealthData>'
        '<Record type="HKQuantityTypeIdentifierHeartRate" value="&j;" '
        'startDate="2026-11-14 08:00:00 +0000"/></HealthData>'
    )

    started = time.perf_counter()
    with pytest.raises(ET.ParseError, match="amplification"):
        list(WearableAdapter(subject="crew-01").from_apple_health_export(bomb))

    assert time.perf_counter() - started < 2.0


def test_a_percentage_saturation_is_rejected_not_inverted(client: TestClient) -> None:
    """La peor inversion posible: una hipoxia del 1 % se guardaba como un 100 % perfecto.

    `physical_min` de la saturacion es 0, asi que "1" es un valor que el sistema acepta
    —1 % de saturacion, muy por debajo del limite critico de 88—. El heuristico "si es
    <= 1, multiplica por 100" lo dejaba nominal, firmado y sin una linea de aviso. Ahora
    la escala la decide el formato: en un export de Apple la saturacion es una fraccion,
    y lo que no cabe en 0-1 se rechaza diciendolo.
    """
    export = _export(_record("OxygenSaturation", "97"))

    response = client.post("/api/import/apple-health", content=export, headers=XML)

    assert response.status_code == 422, "no queda ninguna lectura importable"
    assert client.get("/api/audit").json()["total_entries"] == 0, "y no se registro nada"


def test_a_low_saturation_arrives_as_the_critical_reading_it_is(client: TestClient) -> None:
    """Y la hipoxia de verdad —fraccion 0,01— entra como 1 %, no se pierde ni se invierte."""
    export = _export(_record("OxygenSaturation", "0.01"))

    response = client.post("/api/import/apple-health", content=export, headers=XML)

    assert response.status_code == 201
    observations = client.get("/api/observations").json()["observations"]
    assert [item["valueQuantity"]["value"] for item in observations] == [1.0]


def test_a_real_apple_saturation_still_becomes_a_percentage(client: TestClient) -> None:
    """El dato real de Apple —fraccion 0-1 con la unidad en '%'— sigue entrando bien."""
    export = _export(_record("OxygenSaturation", "0.97"))

    response = client.post("/api/import/apple-health", content=export, headers=XML)

    assert response.status_code == 201
    assert response.json()["imported"] == 1
    observations = client.get("/api/observations").json()["observations"]
    assert [item["valueQuantity"]["value"] for item in observations] == [97.0]


def test_a_giant_unit_does_not_come_back_in_the_response(client: TestClient) -> None:
    """El motivo del rechazo reflejaba el atributo entero: 20 unidades de 500 KB
    devolvian al cliente un JSON del tamano de su propia peticion."""
    export = _export(
        *(
            f'<Record type="HKQuantityTypeIdentifierHeartRate" unit="{"u" * 100_000}" '
            f'value="60" startDate="2026-09-01 08:0{index}:00 +0000"/>'
            for index in range(5)
        )
    )

    response = client.post("/api/import/apple-health", content=export, headers=XML)

    assert response.status_code == 422, "ningún registro era importable"
    assert len(response.content) < 10_000, "la respuesta no arrastra los atributos"


def test_the_parser_does_not_keep_every_record_in_memory() -> None:
    """`element.clear()` vaciaba el registro pero lo dejaba colgado de la raiz.

    Lo que se mide aqui es que el coste **no crece con el numero de registros**: dos
    exports del mismo tamano, uno con 20 000 registros pequenos y otro con 200 grandes,
    tienen que costar lo mismo. Antes el de muchos registros costaba 1,7 MB mas. El
    multiplicador que queda —unas 4 veces el tamano del fichero— es del parser y del
    texto en memoria, y lo acota `MAX_IMPORT_BYTES` junto con `MAX_CONCURRENT_IMPORTS`.
    """

    def peak_for(count: int, padding: int) -> int:
        record = (
            '<Record type="HKQuantityTypeIdentifierStepCount" unit="count" value="1" '
            f'note="{"x" * padding}" startDate="2026-09-01 08:00:00 +0000"/>'
        )
        export = f'<?xml version="1.0"?><HealthData>{record * count}</HealthData>'
        tracemalloc.start()
        try:
            assert list(WearableAdapter(subject="crew-01").from_apple_health_export(export)) == []
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        return peak

    many_small = peak_for(20_000, 0)
    few_large = peak_for(200, 11_000)  # mismo tamano total, ~2,3 MB

    assert many_small < few_large * 1.15, (
        f"el número de registros sigue pesando: {many_small / 1e6:.1f} MB con muchos "
        f"pequenos frente a {few_large / 1e6:.1f} MB con pocos grandes"
    )


# --------------------------------------------------------------------------- #
# El ciclo y la anticoncepción (lote «ciclo», unidad B1, 2026-11-15)
# --------------------------------------------------------------------------- #


def _category(kind: str, value: str, start: str | None = None, minute: int = 0) -> str:
    meta = f'<MetadataEntry key="HKMenstrualCycleStart" value="{start}"/>' if start else ""
    date = f"2026-09-01 08:{minute:02d}:00 +0000"
    return (
        f'<Record type="HKCategoryTypeIdentifier{kind}" sourceName="Salud" value="{value}" '
        f'startDate="{date}" endDate="{date}">{meta}</Record>'
    )


def test_a_cycle_export_is_imported_signed_and_its_rejections_said(client: TestClient) -> None:
    """Todo lo del ciclo entra por `_imported`: firmado en el ledger, nada en silencio."""
    export = _export(
        _category("MenstrualFlow", "HKCategoryValueMenstrualFlowMedium", start="1"),
        _category("MenstrualFlow", "HKCategoryValueVaginalBleedingLight", start="0", minute=1),
        _category("MenstrualFlow", "HKCategoryValueMenstrualFlowUnspecified", start="0", minute=2),
        _category("IntermenstrualBleeding", "HKCategoryValueNotApplicable", minute=3),
        _category("OvulationTestResult", "HKCategoryValueOvulationTestResultPositive", minute=4),
        _category(
            "OvulationTestResult", "HKCategoryValueOvulationTestResultIndeterminate", minute=5
        ),
        _category("Contraceptive", "HKCategoryValueContraceptiveOral", minute=6),
        _record("BasalBodyTemperature", "97.7", "2026-09-01 08:07:00 +0000", unit="degF"),
    )

    response = client.post("/api/import/apple-health", content=export, headers=XML)

    assert response.status_code == 201
    body = response.json()
    assert body["by_indicator"] == {
        "menstrual-flow": 2, "menstruation-start": 3, "intermenstrual-bleeding": 1,
        "ovulation-test": 1, "contraceptive-in-use": 1, "basal-body-temperature": 1,
    }
    assert body["rejected"] == 2
    assert all("no tiene número" in reason for reason in body["rejections"])
    stored = {
        (item["code"]["coding"][0]["code"], item["effectiveDateTime"][11:16]):
            item["valueQuantity"]["value"]
        for item in client.get("/api/observations").json()["observations"]
    }
    assert stored[("menstrual-flow", "08:00")] == 2.0
    assert stored[("menstruation-start", "08:00")] == 1.0
    assert stored[("menstruation-start", "08:02")] == 0.0  # el inicio sobrevive a la cantidad
    assert stored[("ovulation-test", "08:04")] == 2.0
    assert stored[("contraceptive-in-use", "08:06")] == 6.0
    assert stored[("basal-body-temperature", "08:07")] == pytest.approx(36.5)
    audit = client.get("/api/audit").json()
    assert audit["total_entries"] == body["imported"] == 9
    assert audit["integrity_ok"] is True


def test_reading_the_cycle_metadata_keeps_memory_bounded() -> None:
    """Leer los `<MetadataEntry>` antes del `clear()` no puede devolver el coste por registro."""

    def peak_for(count: int, padding: int) -> int:
        record = (
            '<Record type="HKCategoryTypeIdentifierMenstrualFlow" '
            'value="HKCategoryValueMenstrualFlowLight" '
            f'note="{"x" * padding}" startDate="2026-09-01 08:00:00 +0000">'
            '<MetadataEntry key="HKMenstrualCycleStart" value="1"/></Record>'
        )
        export = f'<?xml version="1.0"?><HealthData>{record * count}</HealthData>'
        tracemalloc.start()
        try:
            readings = WearableAdapter(subject="crew-01").from_apple_health_export(export)
            seen = sum(1 for _ in readings)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert seen == 2 * count
        return peak

    many_small = peak_for(10_000, 0)
    few_large = peak_for(100, 20_800)  # mismo tamano total, ~2,1 MB

    assert many_small < few_large * 1.15, (
        f"el número de registros pesa: {many_small / 1e6:.1f} MB con muchos pequenos "
        f"frente a {few_large / 1e6:.1f} MB con pocos grandes"
    )
