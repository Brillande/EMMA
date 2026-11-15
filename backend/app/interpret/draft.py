# SPDX-License-Identifier: AGPL-3.0-or-later
"""Del registro a un borrador revisable, con cinco barreras automáticas antes de la humana.

Licencia y origen (AGPL §5a): usa `polaris/tools/local.py` de la copia literal de Polaris, sin
modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»; se carga con `app.polaris.load`): su guarda contra inyección `_ANTI`, que
aquí es `DATA_GUARD`. De Polaris es también el patrón, no el código, del comité de verificadores
de casas distintas. De EMMA: los hechos del registro, los prompts, `fenced()` (que envuelve por
separado hechos y borrador), el encadenado de las barreras y el formato del borrador.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app import polaris
from app.core import display
from app.core.ledger import canonical_bytes
from app.core.storage import ObservationStore
from app.imaging.measure import ALERTING_NOTE, METHOD
from app.imaging.protocols import PROTOCOLS, Protocol
from app.ingest.codes import get
from app.interpret.cotejo import annotated_from_facts, unannotated_claims
from app.interpret.llm import LocalLlm
from app.pain.catalog import CHARACTERS, ZONES
from app.text_guard import advisories, check, normalize

# Mediciones previas del mismo indicador que ve el modelo. Más no aporta a un borrador corto.
HISTORY_LIMIT = 10
# Informes de dolor más recientes del tripulante que ve el modelo. Mismo motivo.
PAIN_HISTORY_LIMIT = 5

DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "resumen": {"type": "string"},
        "evolucion": {"type": "string"},
        "limitaciones": {"type": "array", "items": {"type": "string"}},
        "preguntas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["resumen", "evolucion", "limitaciones", "preguntas"],
}

VERIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "problemas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cita": {"type": "string"},
                    "motivo": {"type": "string"},
                    "es_fallo": {"type": "boolean"},
                },
                "required": ["cita", "motivo", "es_fallo"],
            },
        },
    },
    "required": ["problemas"],
}

WRITER_PROMPT = """Redactas un BORRADOR para el médico de a bordo de una misión espacial. No eres
el médico y no decides nada.

Reglas sin excepción:
- Usa solo los HECHOS que se te dan. No añadas datos, valores, fechas ni causas.
- Toda cifra que escribas tiene que aparecer en los HECHOS.
- No diagnostiques, no confirmes ni descartes enfermedades.
- No propongas fármacos, dosis, procedimientos ni tratamientos.
- No uses certezas ("sin duda", "seguro", "definitivamente") ni absolutos ("nunca",
  "siempre").
- No recomiendes: nada de "conviene", "debería" o "es razonable". Si algo merece
  comprobarse, escríbelo como pregunta para el médico.
- Escribe en español, frases cortas.

Los signos anotados por el operador son observaciones, no diagnósticos: descríbelos tal cual,
sin decir qué enfermedad sugieren. Si un signo no está anotado o está como "No valorable", no
digas que no está: di que no está anotado o que no fue valorable.

El dolor referido es lo que el tripulante dice sentir, con sus palabras de una lista cerrada: no
lo relaciones con la imagen ni digas qué lo causa.

Rellena: "resumen" (qué se midió o se anotó y con qué resultado), "evolucion" (comparación con
las mediciones previas, o que no las hay), "limitaciones" (lo que los datos no permiten afirmar)
y "preguntas" (qué podría querer comprobar el médico)."""

VERIFIER_PROMPT = """Eres un verificador. Recibes unos HECHOS y un BORRADOR escrito a partir de
ellos. Busca solo estos cuatro fallos en lo que el BORRADOR dice:
1. Una afirmación que no se desprende de los HECHOS.
2. Un diagnóstico, o el nombre de una enfermedad como explicación.
3. Una propuesta de fármaco, dosis, procedimiento o tratamiento.
4. Una certeza que los datos no sostienen.

NO son fallos: omitir un hecho, comparar dos valores de los HECHOS ("mayor", "menor"), describir
un signo tal como está anotado, ni formular preguntas para el médico.

Por cada fallo, copia en "cita" la frase EXACTA del BORRADOR donde está, explica el "motivo" y
pon "es_fallo": true. Si al revisarla ves que no es uno de los cuatro fallos, no la incluyas. Si
no puedes citar una frase exacta del BORRADOR, no es un fallo. Si no hay fallos, devuelve
"problemas" vacío."""

# GUARDA CONTRA INYECCIÓN: el `_ANTI` de Polaris (`tools/local.py`), leído de la copia literal
# (`polaris/`, vía `app.polaris`), no reescrito aquí. Lo que añade EMMA, y no está en Polaris
# (allí se envuelve un único texto de entrada): `fenced()` envuelve por separado los HECHOS y el
# BORRADOR y neutraliza los delimitadores que aparezcan dentro de los datos, para que un dato no
# pueda cerrar el bloque y hablar fuera de él. Los hechos llevan texto que escriben personas
# (quien mide, firma o informa): es la vía por la que una instrucción podría colarse en el prompt.
DATA_GUARD = str(polaris.load("local")._ANTI)


def fenced(label: str, data: str) -> str:
    """Un bloque de datos delimitado, con los delimitadores de dentro neutralizados."""
    safe = data.replace("<<<", "< < <").replace(">>>", "> > >")
    return f"{label}:\n<<<\n{safe}\n>>>"


# Una cita más corta que esto casa con cualquier texto: no identifica una frase.
MIN_QUOTE = 12

_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?")


@dataclass
class DraftOutcome:
    facts_sha256: str
    sections: dict[str, Any]
    text: str
    blocked_reasons: list[str] = field(default_factory=list)
    verifier_problems: list[str] = field(default_factory=list)
    # Objeciones del verificador que no citaban nada del borrador: no bloquean, se registran.
    discarded_objections: list[str] = field(default_factory=list)
    # Modelos del comité que revisaron el borrador, en orden.
    committee: list[str] = field(default_factory=list)
    # Cada objeción del comité, estructurada (modelo, cita, motivo, si cuenta), para consolidarlas
    # en un dosier (`app/committee_dossier.py`, Polaris `paso_consolidacion`).
    objections: list[dict[str, Any]] = field(default_factory=list)
    # Frases que las listas completas de Polaris marcarían y EMMA no bloquea: se enseñan a
    # quien firma (`text_guard.advisories`).
    language_notes: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_reasons)


def facts_for(store: ObservationStore, study_index: int) -> dict[str, Any]:
    """Los hechos firmados de un estudio: lo único que el modelo puede usar.

    Las cifras van ya escritas como las lee la tripulación (coma decimal, unidad legible): así
    el modelo las copia en ese formato y la comprobación de cifras compara lo mismo.
    """
    study, _ = store.imaging_blob(study_index)  # vigente y con el binario comprobado
    records = store.measurements(study_index)
    annotated = store.findings(study_index)
    if not records and not annotated:
        raise ValueError("el estudio no tiene medidas ni hallazgos anotados que describir")

    measured: list[dict[str, Any]] = []
    for record in records:
        code = get(str(record["key"]))
        decimals = display.DECIMALS[code.key]
        history = [
            {
                "fecha": reading.effective.date().isoformat(),
                "valor": _shown(reading.value, decimals, code.unit),
            }
            for reading in store.query(str(study["subject"]), key=code.key)
            if reading.effective.isoformat() != study["acquired"]
        ][-HISTORY_LIMIT:]
        measured.append(
            {
                # En español, como el borrador: con el de LOINC el modelo mezclaría idiomas o
                # traduciría a su manera. El cotejo compara cifras y hallazgos, no este nombre.
                "indicador": code.display_es,
                "lado": record.get("laterality"),
                "valor": _shown(float(record["value"]), decimals, code.unit),
                "detalles": {
                    name: display.number(float(value), 1)
                    for name, value in dict(record.get("details") or {}).items()
                },
                "mediciones_previas": history,
            }
        )
    protocol = PROTOCOLS.get(str(study["protocol"]))
    return {
        "hallazgos_anotados_por_el_operador": [_readable(protocol, item) for item in annotated],
        "protocolo": protocol.display if protocol else study["protocol"],
        "fecha_adquisicion": str(study["acquired"])[:10],
        "origen_de_la_imagen": _origin(study),
        "calibracion": (
            "calibrada: se puede medir en milímetros"
            if study.get("calibration")
            else "sin calibrar: se puede ver, no medir en milímetros"
        ),
        "medidas": measured,
        "metodo": {
            name: {"valor": display.number(param.value, 2), "respaldo": param.evidence}
            for name, param in METHOD.items()
        },
        "alertas": ALERTING_NOTE,
        "dolor_referido_por_el_tripulante": pain_history(store, str(study["subject"])),
    }


def _origin(study: dict[str, Any]) -> str:
    """De dónde sale la imagen, en palabras.

    Antes iban dos booleanos (`fantoma_simulado`, `calibrado`), y el modelo los traducía tal
    cual: "la calibración es falsa", "el fantoma no fue simulado" —de una ecografía real—. Lo
    cazó el linter con el modelo real el 2026-09-25. Un hecho que el modelo tiene que describir
    se le da ya escrito como se lee.
    """
    if study.get("synthetic"):
        return "fantoma simulado: imagen dibujada, no de un tripulante"
    dataset = study.get("dataset")
    if isinstance(dataset, dict):
        return "ecografía real de ejemplo de un dataset público, no de este tripulante"
    return "ecografía adquirida a bordo"


def pain_history(store: ObservationStore, subject: str) -> list[dict[str, Any]]:
    """Los informes de dolor más recientes, legibles, como hechos de ENTRADA del borrador.

    Solo entran: nada de lo que el borrador escriba vuelve al análisis ni a una alerta
    (`compliance/software-safety-classification.md` §2.1). La intensidad va escrita como la
    lee la tripulación, para que la comprobación de cifras compare lo mismo.
    """
    readable: list[dict[str, Any]] = []
    for report in store.pain_reports(subject)[-PAIN_HISTORY_LIMIT:]:
        zones = [
            {
                "zona": ZONES[str(z["zone"])].display if z["zone"] in ZONES else z["zone"],
                "intensidad": _shown(float(z["intensity"]), 0, "{score}"),
                "tipo": [
                    CHARACTERS[c].display if c in CHARACTERS else c
                    for c in z.get("characters") or []
                ],
            }
            for z in report.get("zones") or []
        ]
        readable.append(
            {"fecha": str(report.get("effective", ""))[:10], "zonas": zones or "sin dolor"}
        )
    return readable


def _readable(protocol: Protocol | None, item: dict[str, Any]) -> dict[str, Any]:
    """Los signos anotados, con los nombres que lee una persona en vez de las claves."""
    views = {view.key: view for view in protocol.views} if protocol else {}
    readable: dict[str, dict[str, str]] = {}
    for view_key, signs in dict(item.get("findings") or {}).items():
        view = views.get(view_key)
        by_key = {sign.key: sign for sign in view.signs} if view else {}
        readable[view.display if view else view_key] = {
            (by_key[k].display if k in by_key else k): (
                by_key[k].values.get(v, v) if k in by_key else v
            )
            for k, v in dict(signs).items()
        }
    checklist = [str(point["item"]) for point in item.get("checklist") or [] if not point["done"]]
    return {"signos": readable, "calidad_no_cumplida": checklist}


def _shown(value: float, decimals: int, unit: str) -> str:
    return f"{display.number(value, decimals)} {display.unit(unit)}"


def generate(
    llm: LocalLlm, facts: dict[str, Any], verifiers: Sequence[LocalLlm] | None = None
) -> DraftOutcome:
    """Redactor, comité de verificadores y las barreras deterministas. Un fallo bloquea.

    COMITÉ DE VERIFICADORES, de Polaris: una sola opinión no basta, porque un modelo se equivoca
    con la misma seguridad con que acierta; Polaris convoca voces de casas distintas y
    contrasta. Aquí, todos locales: cada verificador revisa el borrador por su cuenta y basta la
    objeción citada de uno para bloquearlo. Sin `verifiers`, verifica el propio redactor.
    Cuando uno bloquea, los siguientes no se consultan: el borrador ya no se va a mostrar.
    """
    facts_json = json.dumps(facts, ensure_ascii=False, indent=1)
    sections = llm.structured(
        WRITER_PROMPT, f"{DATA_GUARD}\n\n{fenced('HECHOS', facts_json)}", DRAFT_SCHEMA
    )
    text = _assemble(sections)
    outcome = DraftOutcome(
        facts_sha256=hashlib.sha256(canonical_bytes(facts)).hexdigest(),
        sections=sections,
        text=text,
    )
    if not _well_formed(sections):
        outcome.blocked_reasons.append("el modelo no rellenó las secciones pedidas")
        return outcome

    for finding in check(text):
        outcome.blocked_reasons.append(
            f"lenguaje no permitido ({finding.category}): «{finding.match}»"
        )
    outcome.language_notes.extend(
        f"frase que Polaris marcaría ({finding.category}): «{finding.match}»"
        for finding in advisories(text)
    )
    for number in unsupported_numbers(text, facts_json):
        outcome.blocked_reasons.append(f"cifra que no está en los hechos: {number}")
    protocol = next((p for p in PROTOCOLS.values() if p.display == facts.get("protocolo")), None)
    annotated = annotated_from_facts(
        protocol, facts.get("hallazgos_anotados_por_el_operador") or []
    )
    outcome.blocked_reasons.extend(unannotated_claims(text, protocol, annotated))

    for verifier in verifiers or [llm]:
        if outcome.blocked:
            break
        outcome.committee.append(verifier.model)
        _verify(verifier, facts_json, text, outcome)
    return outcome


def _verify(verifier: LocalLlm, facts_json: str, text: str, outcome: DraftOutcome) -> None:
    verdict = verifier.structured(
        VERIFIER_PROMPT,
        f"{DATA_GUARD}\n\n{fenced('HECHOS', facts_json)}\n\n{fenced('BORRADOR', text)}",
        VERIFIER_SCHEMA,
    )
    problems = verdict.get("problemas")
    if not isinstance(problems, list):
        outcome.blocked_reasons.append(
            f"el verificador {verifier.model} no devolvió una lista de problemas"
        )
        return
    # EL VERIFICADOR TAMBIEN TIENE QUE CITAR.
    #
    # Probado con qwen3.5:9b el 2026-09-24: bloqueaba borradores correctos con objeciones
    # inventadas —que "omitía" un hecho que el texto decía literalmente—. Una objeción cuenta
    # solo si cita una frase que está en el borrador; si no, se registra como descartada.
    # Así el verificador puede señalar un fallo, pero no bloquear algo que no está escrito.
    plain = normalize(text)
    for problem in problems:
        item = problem if isinstance(problem, dict) else {}
        quote = str(item.get("cita", "")).strip()
        reason = str(item.get("motivo", "")) if item else str(problem)
        # qwen3.5:9b listaba frases correctas y en el motivo escribía "no es un fallo": la
        # objeción solo cuenta si el propio verificador la marca como fallo y cita el texto.
        counted = (item.get("es_fallo") is True and len(quote) >= MIN_QUOTE
                   and normalize(quote) in plain)
        outcome.objections.append(
            {"model": verifier.model, "quote": quote if counted else "", "reason": reason,
             "counted": counted}
        )
        if counted:
            outcome.verifier_problems.append(f"{verifier.model} · «{quote}»: {reason}")
            outcome.blocked_reasons.append(f"el verificador {verifier.model} objeta «{quote}»")
        else:
            outcome.discarded_objections.append(f"{verifier.model} · {reason}")


def _well_formed(sections: dict[str, Any]) -> bool:
    return (
        isinstance(sections.get("resumen"), str) and bool(sections["resumen"].strip())
        and isinstance(sections.get("evolucion"), str)
        and all(isinstance(sections.get(k), list) for k in ("limitaciones", "preguntas"))
    )


def _assemble(sections: dict[str, Any]) -> str:
    parts = [str(sections.get("resumen", "")), str(sections.get("evolucion", ""))]
    for title, key in (("Limitaciones", "limitaciones"), ("Preguntas", "preguntas")):
        items = [str(item) for item in sections.get(key) or []]
        if items:
            parts.append(f"{title}: " + " ".join(items))
    return "\n\n".join(part for part in parts if part.strip())


def unsupported_numbers(text: str, facts_text: str) -> list[str]:
    """Cifras del borrador que no salen de los hechos.

    Es la barrera que no depende de ningún modelo: un valor inventado, o mal copiado, no pasa.
    Una cifra vale si coincide con alguna de los hechos redondeada a los decimales con que se
    escribió ("5,5" vale si los hechos dicen "5,485").
    """
    known = [_as_float(match) for match in _NUMBER.findall(facts_text)]
    missing: list[str] = []
    for token in _NUMBER.findall(text):
        value = _as_float(token)
        decimals = len(re.split(r"[.,]", token)[1]) if re.search(r"[.,]", token) else 0
        if not any(round(fact, decimals) == value for fact in known):
            missing.append(token)
    return missing


def _as_float(token: str) -> float:
    return float(token.replace(",", "."))
