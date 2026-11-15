"""Las afirmaciones con cifras que EMMA apoya en un artículo, tal como las escribe.

Por qué existe: para comprobar que una cita respalda una cifra (`support.py`), hay que saber qué
cifra se le atribuye. Recortar frases de la documentación a ciegas da trozos sin cifras o mezcla
cifras propias con las del artículo. Aquí se declara cada afirmación una vez, con dónde se usa, y
`tests/test_citation_support_live.py` la coteja con el resumen del registro.

Si añades a EMMA una cifra que atribuyes a un artículo, añádela aquí.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    text: str
    citation: str
    used_in: str


CLAIMS: tuple[Claim, ...] = (
    Claim(
        "El dolor de espalda de adaptación al vuelo lo refirió el 52 % de 728 astronautas.",
        "PMID 22272509",
        "compliance/clinical-decision-rationale.md; app/pain/__init__.py",
    ),
    Claim(
        "En la escala de 0 a 10, de 7 a 10 es dolor intenso.",
        "PMID 7659438",
        "app/pain/alarm.py (SEVERE_FROM)",
    ),
    Claim(
        "El flujo y la morfología de la yugular interna se midieron en vuelo en 11 tripulantes "
        "de la ISS.",
        "PMID 31722025",
        "app/imaging/phantom.py; app/imaging/protocols.py",
    ),
    Claim(
        "El diámetro de la vaina del nervio óptico se mide a 3 mm por detrás de la papila.",
        "PMID 8805599",
        "app/imaging/measure.py (onsd_depth_mm)",
    ),
)
