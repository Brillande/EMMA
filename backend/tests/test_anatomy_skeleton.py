"""Esqueleto de referencia del modo anatómico (BodyParts3D, CC BY 4.0, vía Polaris).

Los ficheros viajan con la app: su atribución tiene que ir al lado y los puntos tienen que ser
coherentes con la imagen (dentro de ella, y la izquierda del sujeto a la derecha de la imagen).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import anatomy

PNG = b"\x89PNG\r\n\x1a\n"


def test_the_skeleton_travels_with_its_cc_by_attribution() -> None:
    attribution = (anatomy.SKELETON_DIR / "ATRIBUCION.txt").read_text(encoding="utf-8")
    assert "CC Attribution 4.0" in attribution and "lic.html" in attribution
    assert anatomy.skeleton()["attribution"].startswith("BodyParts3D")


def test_every_bone_point_lies_inside_the_image_on_its_own_side() -> None:
    bones = anatomy.skeleton()["bones"]
    assert len(bones) >= 50 and "femur_left" in bones and "vertebrae_L5" in bones
    assert all(0 <= p["u"] <= 1 and 0 <= p["v"] <= 1 for p in bones.values())
    # Vista anterior: la izquierda del sujeto cae a la derecha de la imagen.
    assert bones["femur_left"]["u"] > 0.5 > bones["femur_right"]["u"]
    assert bones["vertebrae_C1"]["v"] < bones["vertebrae_L5"]["v"]


def test_the_api_serves_the_points_and_the_image(client: TestClient) -> None:
    body = client.get("/api/anatomy/skeleton").json()
    assert body["region"] == "bones" and body["width"] > 0 and body["bones"]
    image = client.get("/api/anatomy/skeleton.png")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert image.content.startswith(PNG)
