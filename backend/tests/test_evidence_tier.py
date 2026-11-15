"""Nivel de evidencia de las fuentes (portado de Polaris `tier_evidencia.py`).

Las pruebas de la jerarquía son las de Polaris (`tests/test_tier_evidencia.py`): preclínico manda,
un RCT no compite con "Clinical Trial", y sin señales no se inventa un nivel. Sin red: el
registro de PubMed está guardado en `app/data/evidence_tiers.json` (invariante 3).

Una fuente sin PMID se lee con el léxico de Polaris (`senales_desde_texto`), que solo degrada. Lo
que se comprueba aquí es que sigue siendo así pasado por EMMA: del texto nunca sale un nivel por
encima de un caso, nunca se mezcla con un registro, y lo que sale lleva dicho de dónde viene.
"""

from __future__ import annotations

import re

import pytest

from app.advisor import countermeasures
from app.evidence import links, registry, tier
from app.evidence.tier import (
    TEXT_LABEL,
    TEXT_TIERS,
    _records,
    grade,
    signals_from_record,
    signals_from_text,
    weave,
)
from app.imaging.protocols import PROTOCOLS
from app.ingest.codes import Domain


def test_a_bench_study_is_preclinical_even_if_it_cites_a_trial() -> None:
    graded = weave({"animal": True, "rct": True})
    assert graded["tier"] == "modelo_animal" and graded["preclinical"]


def test_humans_and_animals_is_not_preclinical() -> None:
    assert weave({"animal": True, "humanos": True, "rct": True})["tier"] == "rct"


def test_no_design_signal_is_unknown_not_invented() -> None:
    assert weave({"humanos": True})["tier"] == "desconocido"


def test_a_trial_label_does_not_compete_with_rct() -> None:
    signals = signals_from_record(
        ["Randomized Controlled Trial", "Clinical Trial"], ["Humans"]
    )
    assert "ensayo" not in signals and weave(signals)["tier"] == "rct"


def test_review_is_dropped_when_the_method_is_systematic() -> None:
    signals = signals_from_record(["Meta-Analysis", "Review"], ["Humans"])
    assert weave(signals)["tier"] == "metaanalisis"


def test_a_source_without_pmid_is_unknown() -> None:
    graded = grade("NASA HRP, Evidence Report: Risk of SANS (2017)")
    assert graded["tier"] == "desconocido" and graded["pmid"] is None


def test_a_human_source_without_pmid_and_without_signals_stays_unknown() -> None:
    """Sin registro y sin señales en el texto no se inventa un nivel, y `basis` dice que no hay."""
    graded = grade(
        "NASA Human Research Program",
        "Riesgo de desregulación inmune. El vuelo espacial altera la función inmune de la "
        "tripulación y favorece la reactivación de herpesvirus latentes.",
    )
    assert graded["tier"] == "desconocido" and graded["basis"] == "none"
    assert TEXT_LABEL not in graded["label"]


def test_a_mouse_dataset_without_pmid_is_degraded_from_its_text_and_says_so() -> None:
    """La mina de CLAUDE.md: OSD-288 es bazo de ratón. Sin PMID salía "desconocido"."""
    graded = links.OSD_288.to_dict()["grade"]
    assert graded["pmid"] is None
    assert graded["tier"] == "modelo_animal" and graded["preclinical"]
    assert graded["basis"] == "text"
    assert graded["label"].endswith(TEXT_LABEL) and "no del registro" in graded["reason"]
    # Con el mismo texto suelto, sin pasar por la ficha.
    loose = grade("NASA OSDR · OSD-000", "Transcriptome analysis of murine spleen in space")
    assert (loose["tier"], loose["basis"]) == ("modelo_animal", "text")


def test_only_the_expected_emma_sources_are_graded_from_text() -> None:
    """Quien añada una fuente sin PMID ve aquí si el léxico la ha degradado, y lo decide."""
    items = [item for domain in Domain for item in links.evidence_for(domain)]
    items += [c.protocol_ref for c in countermeasures.library().values() if c.protocol_ref]
    grades = [item.to_dict()["grade"] for item in items]
    grades += [grade(source) for protocol in PROTOCOLS.values() for source in protocol.sources]
    assert {g["source"] for g in grades if g["basis"] == "text"} == {
        "NASA OSDR · OSD-288 (publicado el 18 de junio de 2019)"
    }
    assert all(g["basis"] == "record" for g in grades if g.get("retrieved"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Transcriptome analysis of murine spleen in space", "modelo_animal"),
        ("Respuesta de una línea celular de osteoblastos a la microgravedad", "in_vitro"),
        # De una frase el original saca un caso; del texto, EMMA no acepta un nivel clínico.
        ("We report a case of venous thrombosis during spaceflight", "desconocido"),
        ("No es un caso clínico publicado", "desconocido"),
        # Banco y personas a la vez: el original no afirma preclínico, y sin diseño no hay nivel.
        ("Mouse model findings compared with a cohort of 12 participants", "desconocido"),
    ],
)
def test_what_the_text_of_a_source_without_pmid_can_say(text: str, expected: str) -> None:
    """Del texto, EMMA solo acepta la marca de preclínico; lo demás sigue en desconocido."""
    graded = grade("Fuente sin identificador", text)
    assert graded["tier"] == expected
    assert graded["basis"] == ("none" if expected == "desconocido" else "text")


# Las únicas señales que emite el léxico del original. Ninguna es de un diseño que suba el nivel.
_TEXT_SIGNALS = ("in_vitro", "animal", "humanos", "caso")
# El resumen de la prueba de Polaris (ANTI-ASCENSO): un estudio en ratones que cita un ensayo.
_MOUSE_ABSTRACT = (
    "In this study we treated mice bearing xenograft tumors. Unlike the randomized controlled "
    "trial reported by Smith et al., our murine model showed complete regression."
)
# Textos que, leídos por alguien con prisa, "suben" el nivel. El léxico no los detecta a propósito.
_ASCENDING = (
    "A randomized controlled trial in 120 patients",
    "randomized controlled trial in 340 patients, phase III",
    "Clinical practice guideline and consensus statement",
    "Systematic review and meta-analysis of prospective cohort studies",
    "Ensayo aleatorizado, doble ciego, en pacientes reclutados",
    "Randomized, placebo-controlled study in a murine xenograft model",
    "We report a case: randomized treatment of a 54-year-old patient",
    "Retrospective cohort of 300 participants; in vitro confirmation in a cell line",
    "Guía de práctica clínica: serie de casos, preprint y revisión narrativa",
    _MOUSE_ABSTRACT,
    "",
)


def test_a_mouse_abstract_does_not_ascend_for_saying_randomized() -> None:
    """La prueba de Polaris, por la vía de EMMA: sigue en preclínico, y dice de dónde sale."""
    graded = grade("Póster sin identificador", _MOUSE_ABSTRACT)
    assert graded["tier"] == "modelo_animal" and graded["preclinical"]
    assert graded["basis"] == "text"


@pytest.mark.parametrize("text", _ASCENDING)
def test_the_lexicon_emits_no_signal_that_ascends(text: str) -> None:
    """De Polaris: el léxico ni siquiera emite "rct"; solo banco, personas y caso."""
    assert set(signals_from_text(text)) <= set(_TEXT_SIGNALS)


def test_emma_accepts_from_text_less_than_the_lexicon_reaches() -> None:
    """Diferencia declarada con el `--texto` de Polaris: su léxico alcanza también "caso clínico"
    y EMMA, del texto, solo acepta lo preclínico. Si una copia nueva alcanza más, se ve aquí."""
    reachable = {
        weave({key: True for bit, key in enumerate(_TEXT_SIGNALS) if mask >> bit & 1})["tier"]
        for mask in range(2 ** len(_TEXT_SIGNALS))
    }
    assert reachable == TEXT_TIERS | {"caso_clinico", "desconocido"}
    assert set(tier._original().PRECLINICOS) == TEXT_TIERS


@pytest.mark.parametrize("text", [*_ASCENDING, "No es un caso clínico; no hay pacientes"])
def test_text_never_grades_above_what_it_would_get_without_it(text: str) -> None:
    """La propiedad clave. Sin leer el texto, una fuente sin PMID es "desconocido": no afirma
    ningún respaldo clínico. Leyéndolo solo puede seguir ahí o quedar marcada preclínica, que
    afirma menos todavía; nunca recibe un nivel clínico (de caso a guía): ese solo lo da el
    registro."""
    assert grade("Fuente sin identificador")["tier"] == "desconocido"
    graded = grade("Fuente sin identificador", text)
    assert graded["tier"] == "desconocido" or graded["preclinical"]
    assert (graded["basis"] == "text") == graded["preclinical"] == (graded["tier"] in TEXT_TIERS)
    assert (TEXT_LABEL in graded["label"]) == (graded["basis"] == "text")


def test_the_ceiling_holds_even_if_the_lexicon_learns_to_ascend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El techo es de EMMA: no depende de que la copia de Polaris siga sin detectar ensayos."""
    monkeypatch.setattr(
        tier._original(), "senales_desde_texto", lambda _text: {"rct": True, "humanos": True}
    )
    graded = grade("Fuente sin identificador", "randomized")
    assert graded["tier"] == "desconocido" and graded["basis"] == "none"


@pytest.mark.parametrize("text", [*_ASCENDING, "enrolled patients; we report a case"])
def test_text_is_not_read_when_there_is_a_record(text: str) -> None:
    """La otra mitad de la propiedad: con registro, el texto no cuenta y sale lo mismo. Mezclado,
    "patients" quitaría lo preclínico al estudio en cerdos de Hamilton 2004: eso sí subiría."""
    assert grade("Hamilton 2004 (PMID 15018297)")["tier"] == "modelo_animal"
    for pmid in _records():
        plain = grade(f"cita (PMID {pmid})")
        assert plain["basis"] == "record"
        assert grade(f"cita (PMID {pmid})", text) == plain


def test_what_emma_writes_about_a_source_is_not_read() -> None:
    """La relevancia y el alcance son palabras de EMMA, casi siempre negaciones, y el léxico es
    literal: leídas, estas marcarían preclínico un informe en personas."""
    # Desde el registro único (`evidence/registry.py`): la salvedad de alcance es `notes` de la
    # ficha y la relevancia la pone quien cita. Ninguna de las dos llega al léxico.
    ref = registry.EvidenceRef(
        id="informe-de-prueba",
        title="Informe de evidencia de un riesgo",
        source="Informe sin identificador",
        url="https://example.invalid/",
        doi=None,
        pmid=None,
        organization=None,
        date=None,
        evidence_type=None,
        evidence_context=None,
        population=None,
        notes="No hay datos in vitro ni es un modelo animal.",
    )
    item = registry.Citation(
        ref=ref, relevance="Datos de tripulaciones; no se apoya en estudios en ratones."
    )
    graded = item.to_dict()["grade"]
    assert graded["tier"] == "desconocido" and graded["basis"] == "none"


@pytest.mark.parametrize(
    "source", ["doi:10.1/x pmid 15018297", "https://pubmed.ncbi.nlm.nih.gov/15018297/"]
)
def test_a_pmid_written_another_way_does_not_open_the_text_path(source: str) -> None:
    """Esa cita tiene registro: no es una fuente sin PMID. Sigue en desconocido, como antes."""
    graded = grade(source, "Transcriptome analysis of murine spleen in space")
    assert graded["tier"] == "desconocido" and graded["basis"] == "none"
    assert "PubMed" in graded["reason"]


def test_every_cited_pmid_has_a_stored_record() -> None:
    """Si alguien cita un PMID nuevo, la suite le pide correr scripts/grade_sources.py."""
    texts = [s for p in PROTOCOLS.values() for s in p.sources]
    texts += [repr(v) for v in vars(links).values()]
    cited = {m for t in texts for m in re.findall(r"\bPMID:?\s*(\d{5,9})\b", t)}
    assert cited and cited <= set(_records())


@pytest.mark.parametrize(
    ("pmid", "tier"),
    [
        # Hamilton 2004: neumotórax en microgravedad, en cerdos. La app lo citaba sin decirlo.
        ("15018297", "modelo_animal"),
        ("18403664", "cohorte_prospectiva"),
        ("42161258", "revision_narrativa"),
    ],
)
def test_the_stored_records_grade_as_their_registry_says(pmid: str, tier: str) -> None:
    assert grade(f"cita (PMID {pmid})")["tier"] == tier


def test_labels_are_emma_wording_over_polaris_logic() -> None:
    """El nivel lo decide `teje()` de Polaris; la etiqueta, en la redacción de EMMA (2026-09-29)."""
    assert tier.weave({"animal": True})["label"] == "modelo animal (preclínico)"
    assert "mírala a mano" not in tier._unknown("sin registro")["label"]
