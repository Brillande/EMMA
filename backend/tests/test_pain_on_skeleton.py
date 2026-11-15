"""Dolor referido sobre el esqueleto real (`visor3d_superpone_focos.alinea` de Polaris). Sin red."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import pain_on_skeleton, polaris
from app.pain.catalog import ZONES
from tests.test_pain import KNEE, LUMBAR, _report

BODY_MODEL = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pain" / "bodyModel.ts"


@pytest.fixture(autouse=True)
def fresh_fit(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.volumes import skeleton_view

    # Ni el ajuste de referencia ni una figura del TAC calculada por otra prueba.
    monkeypatch.setattr(skeleton_view, "_views", {})
    pain_on_skeleton.alignment.cache_clear()
    yield
    pain_on_skeleton.alignment.cache_clear()


def _body_model() -> dict[str, tuple[float, float]]:
    """Las posiciones de `bodyModel.ts`: centrales tal cual, pares a la izquierda (+x) y espejo."""
    text = BODY_MODEL.read_text(encoding="utf-8")
    central, left = text.split("const LEFT")[0], text.split("const LEFT")[1].split("export")[0]
    found: dict[str, tuple[float, float]] = {}
    pattern = re.compile(r'zone: "([\w-]+)".*?position: \[([-\d.]+), ([-\d.]+)', re.S)
    for zone, x, y in pattern.findall(central):
        found[zone] = (float(x), float(y))
    for zone, x, y in pattern.findall(left):
        found[f"{zone}-left"] = (float(x), float(y))
        found[f"{zone}-right"] = (-float(x), float(y))
    return found


@pytest.mark.skipif(not BODY_MODEL.is_file(), reason="sin el frontend al lado")
def test_the_points_are_the_pain_body_model() -> None:
    zones = pain_on_skeleton.points()["zones"]
    assert {key: (item["x"], item["y"]) for key, item in zones.items()} == _body_model()


def test_every_pain_zone_is_placed_and_the_fit_holds() -> None:
    fit = pain_on_skeleton.alignment()
    assert set(fit["zones"]) == set(ZONES)
    assert fit["superposable"] is True
    assert fit["error_px"]["mean"] < fit["error_px"]["threshold"]
    # La izquierda del tripulante cae a la derecha de la imagen, como el esqueleto de referencia.
    assert fit["zones"]["knee-left"]["u"] > 0.5 > fit["zones"]["knee-right"]["u"]
    # De arriba abajo: cabeza, lumbar, rodilla, pie.
    order = [fit["zones"][key]["v"] for key in ("head", "lower-back", "knee-left", "foot-left")]
    assert order == sorted(order)


def _anchored() -> dict[str, str]:
    """Zona -> hueso de anclaje, del mapa de dolor."""
    zones = pain_on_skeleton.points()["zones"]
    return {key: str(item["bone"]) for key, item in zones.items() if "bone" in item}


def test_each_anchored_zone_sits_on_its_own_bone_on_the_reference() -> None:
    """Modo DIRECTO de Polaris: la zona anclada va al centroide de su hueso, no a donde la deja el
    ajuste (en la figura de referencia, hasta 101 px de él). Las demás, con el ajuste."""
    fit = pain_on_skeleton.alignment()
    bones = pain_on_skeleton.skeleton()["huesos"]
    for zone, bone in _anchored().items():
        placed = fit["zones"][zone]
        assert placed["placed_on"] == pain_on_skeleton.ON_BONE, zone
        centroid = bones[bone]
        assert (placed["u"], placed["v"]) == (round(centroid["u"], 4), round(centroid["v"], 4))
    free = set(ZONES) - set(_anchored())
    assert {fit["zones"][zone]["placed_on"] for zone in free} == {pain_on_skeleton.BY_FIT}
    # El ajuste se sigue midiendo igual: es el que coloca las zonas sin hueso y el que decide.
    assert fit["error_px"]["mean"] < fit["error_px"]["threshold"]


def test_wrong_anchors_are_refused_instead_of_painted(monkeypatch: pytest.MonkeyPatch) -> None:
    bad: dict[str, Any] = {**pain_on_skeleton.points()}
    bad["zones"] = {
        key: ({**item, "bone": "femur_left"} if key in ("neck", "chest") else
              {**item, "bone": "vertebrae_C1"} if key in ("thigh-left", "thigh-right") else item)
        for key, item in bad["zones"].items()
    }
    monkeypatch.setattr(pain_on_skeleton, "points", lambda: bad)
    fit = pain_on_skeleton.alignment()
    assert fit["superposable"] is False
    assert pain_on_skeleton.overlay([_stored(LUMBAR, 0)])["marks"] == []


def test_a_fit_with_too_much_error_is_refused_instead_of_painted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Brazos y muslos anclados al hueso del otro: el cuerpo sigue derecho (la columna manda),
    pero las anclas quedan lejos de su zona. El error lo dice, y entonces no se pinta."""
    swap = {"upper-arm": "femur", "thigh": "humerus"}
    bad: dict[str, Any] = {**pain_on_skeleton.points()}
    bad["zones"] = {
        key: ({**item, "bone": f"{swap[key.rsplit('-', 1)[0]]}_{key.rsplit('-', 1)[1]}"}
              if key.rsplit("-", 1)[0] in swap else item)
        for key, item in bad["zones"].items()
    }
    monkeypatch.setattr(pain_on_skeleton, "points", lambda: bad)
    fit = pain_on_skeleton.alignment()
    assert fit["error_px"]["mean"] > fit["error_px"]["threshold"]
    assert fit["superposable"] is False and fit["reason"] == pain_on_skeleton.BAD_FIT
    body = pain_on_skeleton.overlay([_stored(LUMBAR, 0)])
    assert body["marks"] == [] and body["reason"] == pain_on_skeleton.BAD_FIT


def test_the_copy_is_restored_after_aligning() -> None:
    tool = polaris.load("visor3d_superpone_focos")
    before = (tool.FOCOS, tool.ANCLAS, tool.VB)
    pain_on_skeleton.alignment()
    after = (tool.FOCOS, tool.ANCLAS, tool.VB)
    assert all(now is then for now, then in zip(after, before, strict=True))


def _stored(zone: dict[str, object], days_ago: int) -> dict[str, Any]:
    when = dt.datetime(2026, 11, 20, tzinfo=dt.UTC) - dt.timedelta(days=days_ago)
    return {"effective": when.isoformat(), "zones": [zone]}


def test_only_recent_pain_is_marked_with_its_last_intensity() -> None:
    reports = [_stored(LUMBAR, 20), _stored({**LUMBAR, "intensity": 2}, 1), _stored(KNEE, 0)]
    marks = {item["zone"]: item for item in pain_on_skeleton.overlay(reports)["marks"]}
    assert set(marks) == {"lower-back", "knee-left"}
    assert marks["lower-back"]["reports"] == 1 and marks["lower-back"]["intensity"] == 2
    assert marks["lower-back"]["bone"] == "vertebrae_L3"


def test_the_endpoint_marks_a_recorded_report(client: TestClient) -> None:
    assert client.post("/api/pain/reports", json=_report(LUMBAR, KNEE)).status_code == 201
    body = client.get("/api/anatomy/pain-on-skeleton").json()
    assert body["superposable"] is True
    assert {item["zone"] for item in body["marks"]} == {"lower-back", "knee-left"}
    assert body["source"] == "reference" and body["outside_study"] == []


# --------------------------------------------------------------------------- #
# Sobre el esqueleto del propio TAC (`volumes/skeleton_view.py`)
# --------------------------------------------------------------------------- #


def _own_figure(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    """La figura que da la API para un maniquí con cada hueso donde lo ancla el mapa de dolor."""
    from tests.test_skeleton_view import phantom, record_skeleton

    record_skeleton(client, *phantom(**kwargs))
    figure: dict[str, Any] = client.get("/api/anatomy/skeleton/own").json()
    assert figure["source"] == "own-ct"
    return figure


def test_pain_is_aligned_on_the_own_ct_with_a_physical_threshold(client: TestClient) -> None:
    figure = _own_figure(client)
    fit = pain_on_skeleton.alignment_on(figure)
    assert fit["superposable"] is True and fit["anchors"] == 11
    # El maniquí no tiene cráneo ni pies: esas zonas caen fuera de la imagen. Las ancladas, no.
    anchored = {key for key, item in pain_on_skeleton.points()["zones"].items() if "bone" in item}
    assert not anchored & set(fit["outside"]) and {"head", "foot-left"} <= set(fit["outside"])
    # La imagen abarca 1085 mm de alto: la mitad de la zona anclada más pequeña en px. Con las
    # once anclas es el cuello (160 mm); antes del cuerpo de 2026-11-09, pelvis y cadera (140 mm).
    smallest = min(float(item["height_m"]) for item in pain_on_skeleton.points()["zones"].values()
                   if "bone" in item)
    assert smallest == pytest.approx(0.16)
    assert fit["error_px"]["threshold"] == pytest.approx(0.08 * figure["height"] / 1.085, abs=0.1)
    assert fit["error_px"]["mean"] < 10, "el maniquí tiene los huesos donde el mapa los ancla"
    # Cada zona anclada cae sobre su hueso, del lado que es.
    bones = figure["bones"]
    for zone, bone in (("lower-back", "vertebrae_L3"), ("upper-arm-left", "humerus_left"),
                       ("hip-right", "hip_right"), ("thigh-left", "femur_left")):
        assert fit["zones"][zone]["u"] == pytest.approx(bones[bone]["u"], abs=0.02)
        assert fit["zones"][zone]["v"] == pytest.approx(bones[bone]["v"], abs=0.02)
    assert fit["zones"]["knee-left"]["u"] > 0.5 > fit["zones"]["knee-right"]["u"]


def test_on_a_partial_ct_pain_outside_the_study_is_declared_not_moved(
    client: TestClient,
) -> None:
    """Un TAC que acaba a media pierna y sin el húmero derecho: el fémur cortado no ancla, la
    rodilla queda fuera de la imagen y la zona del hueso ausente no se pinta en otro sitio."""
    figure = _own_figure(client, floor_mm=700.0, missing=("humerus_right",))
    fit = pain_on_skeleton.alignment_on(figure)
    assert fit["superposable"] is True and fit["anchors"] == 8  # 11 − 2 fémures − 1 húmero
    assert fit["outside"]["upper-arm-right"] == pain_on_skeleton.BONE_NOT_IN_STUDY
    assert fit["outside"]["knee-left"] == pain_on_skeleton.OFF_THE_IMAGE
    # El fémur está, pero el centro del muslo queda por debajo de donde acaba el estudio.
    assert fit["outside"]["thigh-left"] == pain_on_skeleton.OFF_THE_IMAGE
    assert "lower-back" not in fit["outside"] and "hip-left" not in fit["outside"]
    # El centroide del fémur cortado es el de su trozo: el muslo no va ahí, sigue con el ajuste.
    assert fit["zones"]["thigh-left"]["placed_on"] == pain_on_skeleton.BY_FIT
    assert fit["zones"]["lower-back"]["placed_on"] == pain_on_skeleton.ON_BONE

    arm = {"zone": "upper-arm-right", "intensity": 4, "characters": ["dull"]}
    reports = [_stored(LUMBAR, 0), _stored(KNEE, 1), _stored(arm, 2)]
    body = pain_on_skeleton.overlay(reports, figure=figure)
    assert body["source"] == "own-ct"
    assert body["segmentation_index"] == figure["ledger"]["segmentation_index"]
    assert [item["zone"] for item in body["marks"]] == ["lower-back"]
    outside = {item["zone"]: item for item in body["outside_study"]}
    assert set(outside) == {"knee-left", "upper-arm-right"}
    assert outside["upper-arm-right"]["reason"].startswith("Fuera del estudio")
    assert outside["upper-arm-right"]["intensity"] == 4 and outside["knee-left"]["reports"] == 1


def test_a_cut_bone_is_not_an_anchor(client: TestClient) -> None:
    """El centroide del trozo de fémur que entra en el TAC queda 140 mm por encima del de la
    zona del muslo: usado de ancla, tira del ajuste; declarado cortado, no cuenta."""
    figure = _own_figure(client, floor_mm=700.0)
    honest = pain_on_skeleton.alignment_on(figure)
    naive = {**figure, "bones": {
        name: {**point, "truncated": False} for name, point in figure["bones"].items()
    }}
    fooled = pain_on_skeleton.alignment_on(naive)
    assert honest["anchors"] == 9 and fooled["anchors"] == 11
    assert honest["error_px"]["mean"] < 10 < fooled["error_px"]["mean"]


def test_an_arm_cut_by_the_side_of_the_study_is_not_an_anchor_nor_where_its_zone_goes(
    client: TestClient,
) -> None:
    """El campo del TAC acaba por el lado derecho del sujeto, a media anchura del húmero: el
    centroide que queda es el de su trozo. El brazo derecho sigue con el ajuste, no sobre él."""
    from tests.test_skeleton_view import cut_study, phantom, record_skeleton

    record_skeleton(client, *cut_study(*phantom(), axis=0, stop=111))
    figure = client.get("/api/anatomy/skeleton/own").json()
    assert figure["source"] == "own-ct"
    assert [item["name"] for item in figure["truncated_bones"]] == ["humerus_right"]
    fit = pain_on_skeleton.alignment_on(figure)
    assert fit["superposable"] is True and fit["anchors"] == 10  # 11 − el húmero cortado
    arm, piece = fit["zones"]["upper-arm-right"], figure["bones"]["humerus_right"]
    assert arm["placed_on"] == pain_on_skeleton.BY_FIT
    assert (arm["u"], arm["v"]) != (round(piece["u"], 4), round(piece["v"], 4))
    assert "upper-arm-right" not in fit["outside"]
    left = fit["zones"]["upper-arm-left"]
    assert left["placed_on"] == pain_on_skeleton.ON_BONE


def test_without_enough_anchors_pain_is_not_aligned_and_it_says_so(client: TestClient) -> None:
    """Solo la columna y el esternón: todas las anclas en la línea media. A lo alto el ajuste
    saldría perfecto y a lo ancho no hay con qué comprobarlo."""
    lateral = tuple(
        name for name in pain_on_skeleton.skeleton()["huesos"] if "left" in name or "right" in name
    )
    figure = _own_figure(client, missing=lateral)
    fit = pain_on_skeleton.alignment_on(figure)
    assert fit["superposable"] is False and fit["anchors"] == 5
    assert fit["reason"] == pain_on_skeleton.TOO_FEW_ANCHORS and fit["error_px"] is None
    body = pain_on_skeleton.overlay([_stored(LUMBAR, 0)], figure=figure)
    assert body["marks"] == [] and body["outside_study"] == []
    assert "anclaje suficientes" in body["reason"]


def test_a_fit_that_mirrors_the_body_places_nothing(client: TestClient) -> None:
    """Una figura en espejo encaja igual de bien con escala negativa: el error no la delata."""
    figure = _own_figure(client)
    mirrored = {**figure, "bones": {
        name: {**point, "u": 1 - point["u"]} for name, point in figure["bones"].items()
    }}
    fit = pain_on_skeleton.alignment_on(mirrored)
    assert fit["error_px"]["mean"] < fit["error_px"]["threshold"], "el error solo no basta"
    assert fit["superposable"] is False and fit["reason"] == pain_on_skeleton.FLIPPED
    assert pain_on_skeleton.overlay([_stored(LUMBAR, 0)], figure=mirrored)["marks"] == []


def test_polaris_refusing_the_fit_is_said_not_raised(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    figure = _own_figure(client)

    def abort(*_args: Any) -> Any:
        raise SystemExit("ABORTA: las anclas están alineadas, no definen escala")

    tool = polaris.load("visor3d_superpone_focos")
    monkeypatch.setattr(tool, "alinea", abort)
    before = (tool.FOCOS, tool.ANCLAS, tool.VB)
    fit = pain_on_skeleton.alignment_on(figure)
    assert fit["superposable"] is False and "no definen escala" in fit["reason"]
    after = (tool.FOCOS, tool.ANCLAS, tool.VB)
    assert after == before, "la copia vuelve a su estado también cuando aborta"


def test_the_endpoint_places_pain_on_the_real_sample_ct(client: TestClient) -> None:
    """`esqueleto-4` acaba en la pelvis: el lumbar se marca y la rodilla queda fuera del estudio."""
    index = client.post("/api/volumes/samples/esqueleto-4").json()["segmentation"]
    assert client.post("/api/pain/reports", json=_report(LUMBAR, KNEE)).status_code == 201
    body = client.get("/api/anatomy/pain-on-skeleton").json()
    assert body["source"] == "own-ct" and body["segmentation_index"] == index
    assert body["superposable"] is True and body["anchors"] == 6
    assert body["error_px"]["mean"] < body["error_px"]["threshold"]
    [mark] = body["marks"]
    assert mark["zone"] == "lower-back" and 0.4 < mark["u"] < 0.6 and 0.45 < mark["v"] < 0.75
    assert [item["zone"] for item in body["outside_study"]] == ["knee-left"]
    other = client.get("/api/anatomy/pain-on-skeleton", params={"subject": "crew-02"}).json()
    assert other["source"] == "reference" and other["marks"] == []


def test_on_the_real_sample_ct_the_worst_anchor_stays_under_the_threshold(
    client: TestClient,
) -> None:
    """`esqueleto-4`, el único TAC real: no basta con que la media pase. Medido el 2026-10-20 con
    6 anclas: error medio 44,4 mm y peor 75,1 mm (L3), umbral 80,0 mm. **Margen del peor: 4,9 mm**
    (el de la media, 35,6). Si el ajuste o la muestra cambian, esta prueba lo dice antes de que el
    peor pase del umbral sin que nadie lo mire. Re-medido el 2026-11-09 con el cuerpo nuevo del
    mapa de dolor: las mismas cifras. Las alturas no mueven el ajuste, solo el umbral, y la zona
    más baja de esas 6 anclas sigue siendo el cuello (0,16 m)."""
    client.post("/api/volumes/samples/esqueleto-4")
    figure = client.get("/api/anatomy/skeleton/own").json()
    top, bottom = figure["extent_mm"]["z"]
    mm = abs(top - bottom) / figure["height"]
    fit = pain_on_skeleton.alignment_on(figure)
    error = {key: value * mm for key, value in fit["error_px"].items()}
    assert fit["superposable"] is True and fit["anchors"] == 6
    assert error["worst"] < error["threshold"]
    assert error["mean"] == pytest.approx(44.4, abs=0.5)
    assert error["worst"] == pytest.approx(75.1, abs=0.5)
    assert error["threshold"] == pytest.approx(80.0, abs=0.5)
    # Con el modo DIRECTO el peor (L3) ya no es la posición de la zona lumbar: va sobre su hueso.
    lumbar, l3 = fit["zones"]["lower-back"], figure["bones"]["vertebrae_L3"]
    assert lumbar["placed_on"] == pain_on_skeleton.ON_BONE
    assert (lumbar["u"], lumbar["v"]) == (round(l3["u"], 4), round(l3["v"], 4))
    # La pelvis y las caderas acaban en el borde del estudio: sus huesos llegan cortados, no son
    # anclas y sus zonas siguen con el ajuste, no sobre el centroide de un trozo.
    assert {figure["bones"][b]["truncated"] for b in ("sacrum", "hip_left", "hip_right")} == {True}
    assert {fit["zones"][z]["placed_on"] for z in ("pelvis", "hip-left", "hip-right")} == {
        pain_on_skeleton.BY_FIT
    }
