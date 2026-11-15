"""El registro de evidencia, completo: lo que se leyó el 2026-10-13 queda escrito y fijado.

La especificación (§3, EvidenceRef) pide `date` y `url/doi` en cada ficha. Hasta la décima ronda
casi todas las fichas antiguas los llevaban a `null`, porque el registro se compiló sin red.
Ese día se leyó la página oficial de cada una y se escribió lo que la página da. Una prueba no
puede comprobar que alguien leyó una fuente; sí puede comprobar el rastro que deja haberla
leído: la fecha de lectura y la frase están en la ficha, la fecha y el DOI de la ficha son los
de su cita, lo que no procede está declarado y no callado, y el número de huecos solo encoge.

Ninguna prueba de aquí sale a la red (invariante 3): lo leído vive en el repositorio.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.advisor import countermeasures
from app.advisor.countermeasures import NO_SOURCE
from app.evidence import registry

READ_ON = "2026-10-13"
LIBRARY = json.loads(
    (Path(countermeasures.__file__).resolve().parents[1] / "data" / "countermeasures.json")
    .read_text(encoding="utf-8")
)["countermeasures"]

# Fichas completadas ese día, con lo que su página declara. Si alguien cambia una fecha o un DOI,
# tiene que hacerlo aquí también: con la fuente delante.
COMPLETED: dict[str, tuple[str, str | None]] = {
    "osd-288": ("2019-06-18", None),
    "osd-569": ("2024-05-14", None),
    "osd-343": ("2020-12-02", "10.26030/h968-2m75"),
    "nasa-twins-study": ("2025-07-10", None),
    "hrp-risk-cardiovascular": ("2025-05-13", None),
    "hrp-risk-behavioral": ("2025-05-13", None),
    "hrp-risk-radiation": ("2026-08-17", None),
    "hrp-risk-bone": ("2025-05-13", None),
    "hrp-risk-immune": ("2025-05-13", None),
    "hrp-sans-evidence-report": ("2017-11-30", None),
    "hrr-urinary-retention": ("2014-08-13", None),
    "kerstman-2012": ("2012-01", "10.3357/asem.2876.2012"),
    "law-2014": ("2014-05", "10.1097/JOM.0000000000000158"),
    "scully-2019": ("2019-06-19", "10.1038/s41526-019-0071-6"),
    "csa-physical-activity": ("2006-08-18", None),
    "hrr-task-1651-pvt": ("2025-05-13", None),
    "nasa-orion-radiation-protection": ("2016-09-22", None),
    "nasa-human-body-in-space": ("2021-02-02", None),
    "mmash": ("2020-06-19", "10.13026/cerq-fc86"),
    "hayslip-2026": ("2026-06-23", "10.1007/s11357-026-02365-x"),
    # Releídas el 2026-10-14 (unidad F1): la fecha estaba en la página y aquella lectura no la vio.
    "nasa-hrp-hazards": ("2023-10-26", None),
    "nasa-hrp-hazard-distance": ("2023-10-26", None),
    "nasa-imm-overview": ("2026-09-16", None),
}
# Fichas cuya página se leyó y no declara fecha: siguen sin ella. El 2026-10-14 se buscó otra vez.
NO_DATE_ON_THE_PAGE = {"hrr-gaps"}
# Las páginas de dos bancos de prueba (decimocuarta ronda, C9), leídas el 2026-10-21: tampoco
# declaran fecha de publicación. Son fichas nuevas, fuera de la pasada de arriba y de su recuento.
NO_DATE_ON_THE_PAGE_R14 = {"bnl-nsrl", "nasa-mmea-program"}
# Páginas leídas en la decimoquinta ronda (2026-10-22) que no declaran fecha de publicación: las dos
# de instalación de ESA y los informes del Research Explorer de NASA (D3), y la de trajes espaciales
# de Johnson (ARGOS) y la de vuelos parabólicos (D5), que solo dicen cuándo se actualizaron, y la
# página de referencia de CIPHER (D2).
NO_DATE_ON_THE_PAGE_R15 = {
    "esa-epm", "esa-biolab", "nasa-iss-research-explorer",
    "nasa-jsc-space-suits-argos", "nasa-parabolic-flight",
    "nasa-cipher",
}
# La portada de data.nasa.gov (decimosexta ronda, E11), leída el 2026-10-23: no muestra fecha.
# El listado de riesgos del Roadmap (decimosexta ronda, E9), leído el 2026-10-23: no declara fecha
# ni versión; cada página de riesgo lleva la suya («Last Published»).
NO_DATE_ON_THE_PAGE_R16 = {"nasa-open-data-portal", "hrr-risks"}
# Bancos de prueba de la decimosexta ronda (E12), leídos el 2026-10-23: el catálogo de análogos,
# las fichas de misión de HERA, la Antártida, el NSRL y las cámaras de altitud, la página «About»
# del NSRL, la del hábitat de CHAPEA y la del NBL. Solo dicen cuándo se actualizaron, o nada.
NO_DATE_ON_THE_PAGE_E12 = {
    "nasa-analog-missions", "nasa-hera-mission", "nasa-antarctic-stations-mission",
    "nasa-nsrl-mission", "bnl-nsrl-about", "nasa-chapea-habitat", "nasa-jsc-nbl",
    "nasa-altitude-chambers",
}
# Las fuentes del contexto sin ficha (decimoséptima ronda, U8), leídas o buscadas el 2026-10-26:
# las portadas de «Living in Space» y de OSDR, que solo dicen cuándo se actualizaron; las dos
# páginas de Columbus, que no muestran fecha; y las preguntas frecuentes, que muestran una sin
# decir de qué es. El enunciado del reto, que ese día el sitio aún no servía, estuvo aquí hasta la
# decimonovena ronda (U2, 2026-10-31), cuando se leyó con su fecha de publicación.
NO_DATE_ON_THE_PAGE_U8 = {
    "nasa-living-in-space", "nasa-osdr-portal",
    "esa-kids-columbus-10-years", "estacionespacial-columbus", "space-apps-2026-participant-faqs",
}
# Las seis direcciones de §17 que quedaban sin ficha (decimoctava ronda, U19), leídas el
# 2026-10-26: las dos páginas de nasa.gov y la del Apéndice E solo dicen cuándo se actualizaron, la
# documentación de astroquery cuándo se compiló, y el repositorio de Polaris y el boletín de
# ZeroKeyUSB no muestran ninguna.
NO_DATE_ON_THE_PAGE_U19 = {
    "nasa-hrp-roi", "nasa-iss-astronaut-record-holders", "astroquery-docs",
    "nasa-std-3001-appendix-e", "beyondtheprotocol-polaris", "bonilista-zerokeyusb",
}
# El libro de nutrición que el Roadmap pone bajo el riesgo de alimentación (decimoctava ronda, U5),
# leído en su portada el 2026-10-26: no lleva fecha; la del nombre del fichero no se adopta. El
# 2026-11-05 (rama «Evidencia») la página de NASA del libro da el año de la segunda edición, y sale
# de esta lista: lo comprueba `test_the_nutrition_book_takes_the_year_nasa_gives_its_edition`.
NO_DATE_ON_THE_COVER_U5: set[str] = set()
NUTRITION_BOOK = "hrp-nutrition-human-adaptation-2020"
NUTRITION_BOOK_DATE_READ_ON = "2026-11-05"
# La página del ciclo solar de NOAA (decimoctava ronda, U14), releída con sus gráficas el
# 2026-10-26: no muestra fecha, y sus datos se actualizan cada mes.
NO_DATE_ON_THE_PAGE_U14 = {"noaa-swpc-solar-cycle-progression"}
# Las páginas de bancos de prueba y proveedores (decimonovena ronda, U4), leídas el 2026-10-31:
# no muestran fecha de publicación; su ficha dice lo que muestran.
NO_DATE_ON_THE_PAGE_R19_U4 = {
    "nasa-envihab-mission", "nasa-antarctic-stations-nsf", "nasa-space-radiation-element",
    "nasa-tissue-sharing-forum", "nasa-chapea-program", "nasa-argos-patent",
    "nasa-iss-facts-figures",
}
# Las páginas del módulo SEER de anatomía y fisiología del NCI (vigésima ronda, unidad 2: la
# función de cada órgano), leídas el 2026-11-02: no muestran fecha de publicación ni de
# actualización; la única del pie es la de la cita sugerida, que es la de quien la lee.
NO_DATE_ON_THE_PAGE_R20_U2 = {
    "seer-nervous-system", "seer-cardiovascular-system", "seer-respiratory-system",
    "seer-skeletal-system", "seer-muscular-system", "seer-urinary-system",
    "seer-digestive-system", "seer-digestive-accessory-organs", "seer-lymphatic-system",
}
# La documentación de las API de HealthKit y Health Connect (lote «ciclo», unidad A3), leída el
# 2026-11-14: las páginas de referencia no publican fecha (Health Connect solo dice en qué versión
# de la biblioteca se añadió cada clase).
NO_DATE_ON_THE_PAGE_CYCLE_A3 = {
    "apple-hk-menstrual-flow-type", "apple-hk-menstrual-flow-values",
    "apple-hk-vaginal-bleeding-values", "apple-hk-menstrual-cycle-start",
    "apple-hk-intermenstrual-bleeding", "apple-hk-ovulation-test-values",
    "apple-hk-ovulation-positive", "apple-hk-contraceptive-values", "apple-hk-contraceptive-type",
    "apple-hk-basal-body-temperature", "android-hc-menstruation-flow",
    "android-hc-ovulation-test", "android-hc-basal-body-temperature",
    "android-hc-records-package",
}
# Las páginas de HealthKit del estado menopáusico y los síntomas vasomotores (lote «ciclo», unidad
# C2), leídas el 2026-11-15: tampoco publican fecha.
NO_DATE_ON_THE_PAGE_CYCLE_C2 = {
    "apple-hk-menopausal-state-type", "apple-hk-menopausal-state-menopause",
    "apple-hk-menopausal-state-perimenopause", "apple-hk-menopausal-state-none",
    "apple-hk-hot-flashes", "apple-hk-night-sweats", "apple-hk-severity-values",
}
# El día en que se leyó cada una de esas páginas sin fecha.
NO_DATE_READ_ON = {
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_CYCLE_C2, "2026-11-15"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_CYCLE_A3, "2026-11-14"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_R20_U2, "2026-11-02"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_R19_U4, "2026-10-31"),
    **dict.fromkeys(NO_DATE_ON_THE_COVER_U5, "2026-10-26"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_U8, "2026-10-26"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_U19, "2026-10-26"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_U14, "2026-10-26"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE, "2026-10-13"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_R14, "2026-10-21"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_R15, "2026-10-22"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_R16, "2026-10-23"),
    **dict.fromkeys(NO_DATE_ON_THE_PAGE_E12, "2026-10-23"),
}
# Lo que queda sin verificar tras la pasada, ficha a ficha. Solo puede encoger: el 2026-10-13
# quedaban 17 campos; el 2026-10-14 se leyeron 16 en su fuente (unidad F1).
STILL_UNVERIFIED: dict[str, set[str]] = {
    **{ref_id: {"date"} for ref_id in NO_DATE_ON_THE_PAGE},
}
_DOI = re.compile(r"10\.\d{4,9}/\S+")


@pytest.mark.parametrize("ref_id", sorted(COMPLETED))
def test_a_completed_card_carries_what_its_page_declares(ref_id: str) -> None:
    ref = registry.get(ref_id)
    date, doi = COMPLETED[ref_id]
    assert ref.date == date
    assert ref.doi == doi
    # El año se lee en la cita, y la ficha dice cuándo se leyó la fuente.
    assert date[:4] in ref.source
    assert ref.notes is not None and READ_ON in ref.notes
    if doi is None:
        # Sin DOI por su naturaleza (página, informe, conjunto sin DOI propio): declarado.
        assert "doi" in ref.not_applicable and "doi" not in ref.unverified
    else:
        assert _DOI.fullmatch(doi) and f"doi:{doi}" in ref.source
        # Un DOI se copió de la fuente y se comprobó que resuelve a ese título: queda dicho.
        assert "doi.org" in ref.notes and "resuelve" in ref.notes


def test_no_date_and_no_doi_is_left_silently_empty() -> None:
    """Tras la pasada, una fecha ausente solo puede ser la de una página que no la declara."""
    for ref in registry.registry().values():
        if ref.date is None:
            assert ref.id in NO_DATE_READ_ON, f"{ref.id}: sin fecha y sin motivo"
            read_on = NO_DATE_READ_ON[ref.id]
            assert ref.notes is not None and read_on in ref.notes, ref.id
            assert "date" in ref.unverified, ref.id
        # El DOI ya no queda pendiente en ninguna ficha: o lo tiene, o no procede.
        assert "doi" not in ref.unverified, ref.id
        # O la tiene, o se leyó y ninguna clase del registro la cubre (un vídeo, una publicación
        # en una red social, una página no oficial: decimoséptima ronda, U8), y se dice.
        assert ref.evidence_type is not None or "evidence_type" in ref.outside_enum, (
            f"{ref.id}: sin clase de documento"
        )


def test_the_nutrition_book_takes_the_year_nasa_gives_its_edition() -> None:
    """Solo el año: la página de NASA da «2021» a la segunda edición, sin mes ni día, y su propia
    fecha (la del artículo web, 2024) no es la del libro."""
    ref = registry.get(NUTRITION_BOOK)
    assert ref.date == "2021"
    assert "date" not in ref.unverified
    assert ref.notes is not None and NUTRITION_BOOK_DATE_READ_ON in ref.notes
    assert "«Download Second Edition PDF – 2021»" in ref.notes
    assert "human-adaptation-to-spaceflight-the-role-of-food-and-nutrition" in ref.notes
    # El número de publicación sigue sin adoptarse como fecha por sí solo, y la del web, tampoco.
    assert "NP-2021-03-003-JSC" in ref.notes and "no se adopta" in ref.notes


def test_what_is_still_unverified_is_listed_and_can_only_shrink() -> None:
    cards = registry.registry().values()
    pending = {ref.id: set(ref.unverified) for ref in cards if ref.unverified}
    for ref_id, fields in pending.items():
        # Una ficha añadida después (otra unidad) no es asunto de esta lista.
        if ref_id in STILL_UNVERIFIED or ref_id in COMPLETED:
            assert fields <= STILL_UNVERIFIED.get(ref_id, set()), ref_id
    total = sum(len(pending.get(ref_id, ())) for ref_id in STILL_UNVERIFIED)
    assert total <= sum(len(fields) for fields in STILL_UNVERIFIED.values()) == 1


def test_the_two_standards_of_the_cabin_are_typed_as_standards() -> None:
    for ref_id in ("nasa-std-3001-vol2-rev-f", "jsc-20584-rev-c"):
        ref = registry.get(ref_id)
        assert ref.evidence_type == "technical_standard"
        assert ref.unverified == ()
        assert ref.notes is not None and "sin clasificar" not in ref.notes


def test_titles_that_were_emma_paraphrases_are_now_the_ones_the_source_gives() -> None:
    """Siete fichas llevaban por título una descripción en español escrita por EMMA."""
    for ref_id in (
        "hrp-risk-cardiovascular", "hrp-risk-behavioral", "hrp-risk-radiation", "hrp-risk-bone",
        "hrp-risk-immune",
    ):
        ref = registry.get(ref_id)
        assert ref.title.startswith("Risk of ")
        assert ref.url is not None and "/Risks/risk.aspx?i=" in ref.url
        # La dirección antigua (el listado) se conserva en la ficha, y el título anterior.
        assert ref.notes is not None
        assert "https://humanresearchroadmap.nasa.gov/risks/" in ref.notes
        assert "Título anterior" in ref.notes
        assert "Last Published" in ref.source
    kerstman = registry.get("kerstman-2012")
    assert kerstman.title == "Space adaptation back pain: a retrospective study"
    assert registry.get("hrp-sans-evidence-report").title.startswith("Evidence Report: Risk of")
    assert registry.get("hrr-urinary-retention").title == "Urinary Retention (Space Adaptation)"
    assert "ISS-12" in registry.get("hrr-task-1651-pvt").title


def test_osd_288_keeps_its_caveat_and_says_what_the_metadata_did_not_confirm() -> None:
    ref = registry.get("osd-288")
    assert ref.notes is not None
    assert "NO mide signos vitales humanos" in ref.notes
    # La discrepancia se resolvió leyendo OSDR (2026-10-14) y queda escrita, con la frase de la
    # fuente: 12 ratones lanzados, 9 muestras en el conjunto. El «n = 12» antiguo se explica.
    assert "9 muestras de bazo" in ref.notes
    assert "12 mice at 8 weeks of age were loaded into the TCU" in ref.notes
    assert "contaba los ratones lanzados, no los datos" in ref.notes


# --------------------------------------------------------------------------- #
# La pasada del 2026-10-14 (unidad F1): los 16 campos leídos dejan su rastro
# --------------------------------------------------------------------------- #

READ_ON_F1 = "2026-10-14"
# Lo que dio cada fuente, y la frase de la ficha que lo respalda.
ORGANIZATIONS: dict[str, tuple[str, str]] = {
    "kerstman-2012": ("The University of Texas Medical Branch",
                      "«The University of Texas Medical Branch, Galveston, TX, USA.»"),
    "law-2014": ("NASA Johnson Space Center", "«From the NASA Johnson Space Center (Dr Law"),
    "scully-2019": ("KBRwyle / NASA Johnson Space Center",
                    "NASA Lyndon B. Johnson Space Center, Houston, TX 77058 USA.»"),
    "hayslip-2026": ("University of Central Florida", "University of Central Florida, Orlando"),
}
# Entorno leído y sin valor del enumerado que lo cubra: estudios que juntan entornos.
OUTSIDE_THE_ENUM = {
    "osd-343", "kerstman-2012", "hayslip-2026", "hrp-sans-evidence-report",
    "hrp-food-system-evidence-report",
}
# Entorno que no procede: no son estudios.
CONTEXT_NOT_APPLICABLE = {"hrr-urinary-retention", "nasa-human-body-in-space"}


@pytest.mark.parametrize("ref_id", sorted(ORGANIZATIONS))
def test_an_organization_is_the_affiliation_the_record_gives(ref_id: str) -> None:
    ref = registry.get(ref_id)
    organization, quote = ORGANIZATIONS[ref_id]
    assert ref.organization == organization
    assert ref.notes is not None and quote in ref.notes and READ_ON_F1 in ref.notes


def test_a_context_no_value_covers_is_declared_not_forced() -> None:
    for ref_id in OUTSIDE_THE_ENUM:
        ref = registry.get(ref_id)
        assert ref.outside_enum == ("evidence_context",), ref_id
        assert ref.evidence_context is None and ref.unverified == (), ref_id
        assert ref.notes is not None and "se declara fuera del enumerado" in ref.notes, ref_id
        assert ref.to_dict()["outside_enum_display"] == ["entorno del estudio"]
    for ref_id in CONTEXT_NOT_APPLICABLE:
        ref = registry.get(ref_id)
        assert "evidence_context" in ref.not_applicable and ref.unverified == (), ref_id
        assert ref.notes is not None and "no aplica" in ref.notes, ref_id
    # Ninguna ficha dice ya «sin clasificar» de su entorno: o lo tiene, o se dice por qué no.
    for ref in registry.registry().values():
        assert "el entorno queda sin clasificar" not in (ref.notes or "").lower(), ref.id


def test_the_two_evidence_reports_say_on_whom_they_measured() -> None:
    sans = registry.get("hrp-sans-evidence-report")
    # El informe de SANS cita un mono en vuelo y ratas: no es solo de personas.
    assert sans.population == "human_and_animal"
    assert sans.notes is not None and "Macaque Monkey During Spaceflight" in sans.notes
    food = registry.get("hrp-food-system-evidence-report")
    assert food.population == "human"
    assert food.notes is not None and "no cita estudios en animales" in food.notes
    for ref in (sans, food):
        assert READ_ON_F1 in (ref.notes or "") and "no se releyó entero" in (ref.notes or "")


# --------------------------------------------------------------------------- #
# El estudio de GeroScience: ficha leída, preclínica, y el docstring dice lo que dice el resumen
# --------------------------------------------------------------------------- #


def test_the_geroscience_study_is_a_card_and_it_is_preclinical() -> None:
    ref = registry.get("hayslip-2026")
    assert ref.evidence_type == "journal_article"
    assert ref.population in registry.NON_HUMAN
    assert ref.notes is not None
    for said in ("preclínico", "ratón", "No dice nada de un tripulante", "influenced"):
        assert said in ref.notes
    resolved = ref.to_dict()
    assert resolved["population_display"] != registry.POPULATIONS["human"]


def test_the_library_docstring_cites_the_card_and_does_not_overstate_it() -> None:
    doc = countermeasures.__doc__ or ""
    assert "`hayslip-2026`" in doc
    # La frase del resumen, literal, y la misma que guarda la ficha.
    quote = (
        "while antagomir treatment influenced genes associated with senescence and "
        "inflammatory responses, it increased the expression of fibrosis-associated transcripts"
    )
    assert quote in " ".join(doc.split())
    assert quote in (registry.get("hayslip-2026").notes or "")
    assert "raton" in doc and "preclinico" in doc
    # Lo que el resumen no dice: que el tratamiento mejorase nada.
    assert "mejoro senales" not in doc
    # Ninguna otra mención de la revista sin ficha en el código de la aplicación.
    app = Path(countermeasures.__file__).resolve().parents[1]
    for path in app.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "GeroScience" in text:
            assert "hayslip-2026" in text, path.name


# --------------------------------------------------------------------------- #
# Tiempo de tripulación: solo el que su fuente publica, con su frase
# --------------------------------------------------------------------------- #

# Las cifras que hay y la frase literal que las sostiene (leída el 2026-10-13).
CREW_TIME: dict[str, tuple[int, str]] = {
    "cv-exercise-session": (120, "astronauts must exercise approximately two hours per day"),
    "bh-repeat-pvt": (3, "we developed a modified brief 3-min version of the PVT (PVT-B)"),
    "rad-storm-shelter": (60, "the crew would create the shelter within an hour"),
}
# Las que se leyeron el 2026-10-14 (undécima ronda, F4), en las notas técnicas de OCHMO.
CREW_TIME_READ_ON = "2026-10-14"
CREW_TIME_LATER: dict[str, tuple[int, str]] = {
    "bone-resistive-load": (60, "Resistive/Strength: 30-60 minutes load-bearing training"),
    "bh-protect-sleep": (60, "1-2 hrs before bedtime: avoid use of electronic devices"),
}
# Decimotercera ronda (H10), leída el 2026-10-20: de las 32 «sin fuente», la única que gana
# frase. Las demás siguen sin cifra; lo buscado está en el informe de la unidad.
CREW_TIME_H10_READ_ON = "2026-10-20"
CREW_TIME_H10: dict[str, tuple[int, str]] = {
    "imm-viral-sample": (
        3,
        "the subject placed the cotton roll in their mouth until it became saturated with "
        "saliva (2–3 min)",
    ),
}
# La única cifra sin fuente externa: la fija el propio procedimiento, y lo dice.
EMMA_DESIGN = {"cv-repeat-rest": 10}


def test_every_crew_time_figure_has_its_literal_sentence_or_is_emma_design() -> None:
    with_figure = {item["id"]: item for item in LIBRARY if item["crew_time_minutes"] is not None}
    assert set(with_figure) == (
        set(CREW_TIME) | set(CREW_TIME_LATER) | set(CREW_TIME_H10) | set(EMMA_DESIGN)
    )
    for key, (minutes, sentence) in CREW_TIME.items():
        item = with_figure[key]
        assert item["crew_time_minutes"] == minutes
        assert sentence in item["crew_time_basis"] and "«" in item["crew_time_basis"], key
        assert READ_ON in item["crew_time_basis"], key
    for key, (minutes, sentence) in CREW_TIME_LATER.items():
        item = with_figure[key]
        assert item["crew_time_minutes"] == minutes
        assert sentence in item["crew_time_basis"] and "«" in item["crew_time_basis"], key
        assert CREW_TIME_READ_ON in item["crew_time_basis"], key
        # La frase es la que guarda la ficha que la entrada cita como protocolo.
        ref = registry.get(item["protocol_ref"]["ref"])
        assert sentence in (ref.notes or ""), key
    for key, (minutes, sentence) in CREW_TIME_H10.items():
        item = with_figure[key]
        assert item["crew_time_minutes"] == minutes
        assert sentence in item["crew_time_basis"] and "«" in item["crew_time_basis"], key
        assert CREW_TIME_H10_READ_ON in item["crew_time_basis"], key
        ref = registry.get(item["protocol_ref"]["ref"])
        assert sentence in (ref.notes or ""), key
    for key, minutes in EMMA_DESIGN.items():
        assert with_figure[key]["crew_time_minutes"] == minutes
        assert "diseño EMMA" in with_figure[key]["crew_time_basis"]


def test_a_protocol_that_publishes_no_duration_gives_none() -> None:
    """No se convierte «dos horas de ejercicio al día» en la duración de otra contramedida."""
    for item in LIBRARY:
        if item["id"] in {*CREW_TIME, *CREW_TIME_LATER, *CREW_TIME_H10, *EMMA_DESIGN}:
            continue
        assert item["crew_time_minutes"] is None, item["id"]
        if item.get("protocol_ref") is None:
            assert item["crew_time_basis"] == NO_SOURCE, item["id"]
    # Una ventana de cuándo (la luz antes de dormir y al despertar) no es una duración.
    lighting = next(item for item in LIBRARY if item["id"] == "bh-circadian-lighting")
    assert lighting["crew_time_minutes"] is None and "sin fuente" in lighting["crew_time_basis"]


def test_a_range_is_given_by_its_top_and_says_so() -> None:
    """De un rango publicado se toma un extremo y se dice cuál; nunca una cifra a medio camino."""
    by_id = {item["id"]: item for item in LIBRARY}
    assert "tope del rango" in by_id["bone-resistive-load"]["crew_time_basis"]
    assert "extremo inferior" in by_id["bh-protect-sleep"]["crew_time_basis"]
    # Una tarea se agenda por su tope: de «2–3 min» con el rollo en la boca, 3.
    assert "tope del rango" in by_id["imm-viral-sample"]["crew_time_basis"]
    # Un estudio citado solo por su tiempo no convierte la acción en respaldada por protocolo.
    assert by_id["imm-viral-sample"]["basis"] == "demo"
    # La discrepancia entre la CSA (dos horas) y OCHMO-TB-031 (de 60 a 90 minutos) se dice.
    exercise = by_id["cv-exercise-session"]["crew_time_basis"]
    assert "OCHMO-TB-031" in exercise and "Discrepa" in exercise


def test_contraindications_stay_pending_until_a_medical_review_writes_them() -> None:
    """Lo leído el 2026-10-14 no trae contraindicaciones de estas acciones.

    Lo más parecido —«Within 2 hours of sleep, avoid: Vigorous exercise», de OCHMO-MTB-009— es
    una práctica de higiene del sueño. Escribirla en `contraindications_note` haría que la
    tarjeta dejase de decir «pendiente de revisión médica»: la ficha la guarda y así se queda.
    """
    assert all(item["contraindications_note"] is None for item in LIBRARY)
    assert "Within 2 hours of sleep, avoid: Vigorous exercise" in (
        registry.get("ochmo-mtb-009").notes or ""
    )


def test_the_quoted_sentences_are_the_ones_kept_in_the_registry() -> None:
    """La frase del tiempo y la ficha de su protocolo no pueden decir cosas distintas."""
    by_id = {item["id"]: item for item in LIBRARY}
    for key in ("cv-exercise-session", "rad-storm-shelter"):
        ref = registry.get(by_id[key]["protocol_ref"]["ref"])
        assert CREW_TIME[key][1] in (ref.notes or ""), key
    # La tarea del Roadmap no publica la duración del PVT: la cifra sale del artículo, y se dice.
    assert "no publica la duración" in (registry.get("hrr-task-1651-pvt").notes or "")
    assert "PMID 22025811" in by_id["bh-repeat-pvt"]["crew_time_basis"]


# --------------------------------------------------------------------------- #
# Invariante 5: nada de esto entra en el veredicto
# --------------------------------------------------------------------------- #


def test_no_analysis_module_reads_the_crew_time_or_the_registry_dates() -> None:
    analysis = Path(countermeasures.__file__).resolve().parents[1] / "analysis"
    for path in analysis.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "crew_time" not in text, path.name
        # Ni la fecha ni el DOI de una ficha: el análisis cita fichas, no decide con ellas.
        assert "ref.date" not in text and ".doi" not in text, path.name


def _verdict(status: dict[str, Any]) -> dict[str, Any]:
    """Lo que decide el motor: niveles, alertas y qué se recomienda, sin las fichas citadas."""
    return {
        "overall": status["overall_level"],
        "domains": {key: value["level"] for key, value in status["domains"].items()},
        "alerts": [(a["id"], a["domain"], a["level"]) for a in status["alerts"]],
        "recommendations": [
            (
                r["domain"], r["action"], r["urgency"],
                (r["countermeasure"] or {}).get("id"),
                (r["countermeasure"] or {}).get("crew_time_minutes"),
            )
            for r in status["recommendations"]
        ],
        "rules_version": status["rules_version"],
    }


def test_the_verdict_and_the_recommended_actions_do_not_depend_on_the_cards(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El mismo escenario con las fichas de hoy y con fecha, DOI y título borrados: mismo veredicto.

    Las citas ya construidas al importar (`links`, `context`) conservan su ficha; lo que esta
    prueba cubre es todo lo que resuelve una ficha al atender la petición, que es por donde un
    campo del registro podría colarse en una decisión. El contraste entero, con el registro de
    antes y el de después en dos servidores, es el humo de la unidad.
    """
    sent = client.post("/api/simulate", params={"scenario": "spe-event", "days": 40})
    assert sent.status_code in (200, 201), sent.text
    now = client.get("/api/status").json()
    assert now["alerts"], "el escenario tiene que disparar al menos una alerta"

    raw = json.loads(registry.REGISTRY_PATH.read_text(encoding="utf-8"))
    for item in raw["references"]:
        if item["url"] is not None:
            item["doi"] = None
        item["date"] = None
        item["title"] = "x"
        item["not_applicable"] = [n for n in item.get("not_applicable", []) if n != "doi"]
    blank = registry.parse(raw)
    monkeypatch.setattr(registry, "registry", lambda: blank)
    before = client.get("/api/status").json()

    assert _verdict(now) == _verdict(before)


def test_the_api_counts_fewer_pending_fields_than_before_the_pass(client: TestClient) -> None:
    body = client.get("/api/dossier/references").json()
    # Antes de la pasada: 67 campos sin verificar en 37 fichas (medido el 2026-10-13).
    mine = [r for r in body["references"] if r["id"] in STILL_UNVERIFIED or r["id"] in COMPLETED]
    # Tras la pasada del 2026-10-13 quedaban 17; tras la del 2026-10-14, uno.
    assert sum(len(r["unverified"]) for r in mine) == 1
    assert body["unverified_fields"] == sum(len(r["unverified"]) for r in body["references"])
