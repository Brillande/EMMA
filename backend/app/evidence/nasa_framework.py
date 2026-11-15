"""El marco de NASA, leído: lo que dicen las fuentes, con su frase, y aparte lo que hace EMMA.

La especificación del equipo (§16) ancla el diseño en la arquitectura CDSS de ExMC, en el IMM y
en el informe de alimentación; su base de conocimiento (§2.2, §2.3 y §5) y la conversación de
ideación añaden las limitaciones del IMM, los huecos Food-01…04 y la progresión del nivel de
asistencia IV al V. Hasta la décima ronda EMMA citaba esos anclajes sin haberlos leído: tres
referencias de NTRS figuraban «sin leer» y la propia base de conocimiento pedía comprobar los
huecos de alimentación «antes de afirmar que siguen abiertos». Un anclaje citado de oídas acaba
diciendo lo que conviene.

El 2026-10-13 se leyeron las fuentes oficiales y lo leído vive en `data/nasa_framework_read.json`
(lo leído después lleva su propia fecha en la fuente: MEDPRAT e IMPACT, el ATCS y OCHMO-TB-002, el
2026-10-21; el memorando de 2025 sobre MEDPRAT y el IMM, dos presentaciones de 2020, un resumen
de 2025 y la relectura de la página del IMM, el 2026-10-22):
la frase o la fila exacta, su sección, su dirección y la ficha del registro de evidencia. La
lectura corrigió dos cosas que el proyecto daba por buenas —el Roadmap publica Med07 como
cerrado y Food-01…04 como divididos en otros huecos; la norma vigente ya no define niveles de
asistencia—, y por eso lo que se lee va como dato fechado, no como prosa.

Este cargador es la defensa: rechaza una frase sin fuente, una dirección que no sea de un sitio
oficial de NASA, una ficha que no esté en el registro, un documento del que no se diga cuánto se
leyó, un texto sobre EMMA que reclame conformidad y un estado de hueco que no sea uno de los que
publica el Roadmap, leído en la página del propio hueco. Ese estado (`gap_status`) es el que
acompaña al nombre de un hueco en `/api/framework`: corregir la lectura no bastó, porque la ruta
siguió presentando Med07 y Med10 como huecos que EMMA aborda, uno cerrado y otro fusionado, hasta
la undécima ronda. **Citar un documento no es implementarlo**
(`CLAUDE.md`, invariante 6): de cada bloque se dice qué pide la fuente y, aparte, qué hace EMMA.

Decimoquinta ronda: un bloque puede llevar una pregunta que lo leído contesta (`question`). El de
MEDPRAT decía que IMPACT «will soon replace» al IMM con un resumen de 2024 como última palabra, y
el memorando técnico de febrero de 2025 —que no se había leído— sigue llamando al IMM «the
currently accepted standard». Una respuesta que se apoya en lo de hace dos años mientras el bloque
guarda algo más nuevo dice lo que ya no es. Por eso la respuesta nombra las frases en que se
apoya y el cargador exige que entre ellas esté la del documento más reciente del bloque: quien
añada una fuente más nueva tiene que volver a mirar la respuesta. Y lo que la respuesta pone entre
comillas angulares tiene que estar, letra por letra, en alguna de esas frases: la respuesta no
puede cambiar «is anticipated to produce» por «has produced» sin que se note.

Decimoséptima ronda: un bloque puede llevar una tabla de cobertura (`coverage`). El del CDSS citaba
cuatro restricciones y un supuesto de dieciséis, y nada decía qué hace EMMA con cada cosa que pide
el documento: citado así, parece que lo atiende todo. Cada fila nombra lo que pide una frase,
letra por letra de ella, si EMMA lo cubre, lo hace en parte o no, el motivo y el fichero de EMMA
que lo hace; el cargador rechaza una petición que la frase no escriba, un «cubre» sin fichero y un
texto que reclame conformidad.

Es un inventario: no entra en el análisis, en el riesgo ni en ninguna alerta (invariante 5), y
no sale a la red: la lectura se hizo una vez, en Tierra, y aquí solo quedan sus frases.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import re
from functools import cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from app.core import i18n
from app.evidence import registry
from app.evidence.read_contract import check_sources, claims

READ_PATH = Path(__file__).resolve().parents[1] / "data" / "nasa_framework_read.json"

# Solo la página o el PDF oficial: un buscador, un blog o una enciclopedia no son una fuente.
OFFICIAL_HOSTS = frozenset({
    "ntrs.nasa.gov",
    "www.nasa.gov",
    "humanresearchroadmap.nasa.gov",
    "standards.nasa.gov",
})

# La fecha de una ficha con la precisión que dé la fuente (como en `registry`), y lo que una
# respuesta cita entre comillas angulares.
_CARD_DATE = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?")
_QUOTED = re.compile(r"«([^«»]+)»")

# Cuánto se leyó de cada documento. No hay valor por defecto: quien cita lo declara.
EXTENTS = {
    "full": "leído entero",
    "partial": "leído en parte",
    "record": "leído: resumen de NTRS; el documento completo, no",
}
i18n.en_many({
    EXTENTS["full"]: "read in full",
    EXTENTS["partial"]: "read in part",
    EXTENTS["record"]: "read: NTRS abstract; the full document, not",
})

# El estado de un hueco tal como lo publica su página del Human Research Roadmap. Lo que no
# figura abierto no se presenta como hueco que EMMA aborde: de aquí sale la frase que lo dice
# junto a su nombre en `/api/framework` (undécima ronda: la lectura del 2026-10-13 encontró Med07
# cerrado, Med10 fusionado y el hueco de fatiga de menú archivado, y los textos seguían
# presentándolos como huecos que EMMA aborda).
GAP_STATUSES = {
    "open": "abierto",
    "closed": "cerrado",
    "merged": "fusionado en otro hueco",
    "archived": "archivado y retirado del plan de investigación actual",
    "split": "dividido en otros huecos",
}
i18n.en_many({
    GAP_STATUSES["open"]: "open",
    GAP_STATUSES["closed"]: "closed",
    GAP_STATUSES["merged"]: "merged into another gap",
    GAP_STATUSES["archived"]: "archived and withdrawn from the current research plan",
    GAP_STATUSES["split"]: "split into other gaps",
})

# Lo que EMMA no puede decir de sí mismo por haber citado un documento (invariante 6).
CLAIM_WORDS = (
    "implementa", "alinead", "conforme", "cumple", "certific", "satisface", "compatible con",
)

# Qué hace EMMA con lo que pide una frase (decimoséptima ronda, tabla de cobertura del CDSS).
# «Cubre» es que EMMA tiene una pieza que lo hace, con su fichero; no que se haya evaluado frente
# al documento ni probado en vuelo.
COVERAGES = {
    "covered": "cubre",
    "partial": "en parte",
    "outside": "no",
}
# «covers», como en castellano, es tener una pieza que lo hace: no una evaluación frente al
# documento. El «no» se dice igual en los dos idiomas y no se registra.
i18n.en_many({COVERAGES["covered"]: "covers", COVERAGES["partial"]: "partly"})

NOTE = (
    "Lo que dicen las fuentes oficiales de NASA, con su frase exacta y la fecha en que se leyó, "
    "y aparte lo que hace EMMA. Citar un documento no es implementarlo: EMMA no reclama "
    "conformidad con ninguno. Inventario: no interviene en el estado de la tripulación."
)
i18n.en(
    NOTE,
    "What NASA's official sources say, with the exact sentence and the date it was read, and "
    "separately what EMMA does. Citing a document is not implementing it: EMMA claims "
    "conformity with none. Inventory: it plays no part in the crew's status.",
)


class FrameworkError(ValueError):
    """Lo leído no cumple su contrato: no se sirve."""


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _url(item: dict[str, Any]) -> str | None:
    """La dirección leída: la propia de la frase o, si no lleva, la de su ficha del registro."""
    own = item.get("url")
    if own is not None:
        return str(own)
    return registry.get(item["ref"]).url


def _validate_statement(block: str, item: dict[str, Any], sources: dict[str, Any]) -> None:
    key = f"{block}/{item.get('id', '?')}"
    for field in ("id", "label", "quote", "ref", "where"):
        if not _text(item, field):
            raise FrameworkError(
                f"{key}: falta `{field}`: sin frase, sección y fuente no es un dato"
            )
    if item["ref"] not in sources:
        raise FrameworkError(f"{key}: de {item['ref']!r} no se declara cuánto se leyó")
    url = _url(item)
    parts = urlsplit(url or "")
    if parts.scheme != "https" or parts.hostname not in OFFICIAL_HOSTS:
        raise FrameworkError(f"{key}: {url!r} no es una fuente oficial de NASA")
    note = item.get("note")
    if note is not None and not _text(item, "note"):
        raise FrameworkError(f"{key}: `note` vacía: lo que no hay es null")
    gap = item.get("gap")
    if gap is not None:
        if not isinstance(gap, dict) or not _text(gap, "id"):
            raise FrameworkError(f"{key}: `gap` sin el nombre del hueco")
        if gap.get("status") not in GAP_STATUSES:
            raise FrameworkError(
                f"{key}: estado de hueco {gap.get('status')!r} desconocido: se dice el que "
                "publica el Roadmap, no uno aproximado"
            )
        if urlsplit(url or "").hostname != "humanresearchroadmap.nasa.gov":
            raise FrameworkError(
                f"{key}: el estado de un hueco se lee en su página del Human Research Roadmap"
            )


def _bounds(date: str) -> tuple[dt.date, dt.date]:
    """El primer y el último día que cabe en una fecha de ficha (AAAA, AAAA-MM o AAAA-MM-DD).

    Una ficha fechada solo por el mes («2025-02», la portada de un memorando) puede ser de
    cualquier día de ese mes: para decidir si un documento es más nuevo que otro no se le supone
    el día que conviene. Una fecha con otra forma falla aquí, no se compara como texto.
    """
    wrong = f"{date!r} no es una fecha de ficha (AAAA, AAAA-MM o AAAA-MM-DD)"
    if _CARD_DATE.fullmatch(date) is None:
        raise FrameworkError(wrong)
    try:
        if len(date) == 4:
            year = int(date)
            return dt.date(year, 1, 1), dt.date(year, 12, 31)
        if len(date) == 7:
            first = dt.date.fromisoformat(f"{date}-01")
            last = calendar.monthrange(first.year, first.month)[1]
            return first, first.replace(day=last)
        day = dt.date.fromisoformat(date)
    except ValueError:
        raise FrameworkError(wrong) from None
    return day, day


def _validate_question(block: dict[str, Any]) -> None:
    """La pregunta de un bloque se apoya en frases suyas, y entre ellas en la más reciente."""
    key = block["id"]
    question = block.get("question")
    if question is None:
        return
    if not isinstance(question, dict) or not all(
        _text(question, field) for field in ("text", "answer")
    ):
        raise FrameworkError(f"{key}: una pregunta sin `text` o sin `answer`")
    rests_on = question.get("rests_on")
    if (
        not isinstance(rests_on, list) or not rests_on
        or not all(isinstance(item, str) for item in rests_on)
    ):
        raise FrameworkError(f"{key}: una respuesta sin las frases en que se apoya (`rests_on`)")
    statements = {item["id"]: item for item in block["statements"]}
    if len(set(rests_on)) != len(rests_on):
        raise FrameworkError(f"{key}: una frase repetida en `rests_on`")
    if missing := [item for item in rests_on if item not in statements]:
        raise FrameworkError(
            f"{key}: la respuesta se apoya en frases que no son del bloque ({missing})"
        )
    # Se compara por documento: otra frase del mismo documento que una usada ya está mirada.
    dates: dict[str, str] = {}
    for item in statements.values():
        date = registry.get(item["ref"]).date
        if date is None:
            raise FrameworkError(
                f"{key}/{item['id']}: su ficha no tiene fecha: no se sabe si es más reciente "
                "que lo que responde la pregunta"
            )
        dates[item["ref"]] = date
    used = {statements[item]["ref"] for item in rests_on}
    # Lo más nuevo en que se apoya, tomado por lo bajo; lo que no usa, por lo alto.
    newest = max(_bounds(dates[ref])[0] for ref in used)
    if newer := sorted(
        ref for ref in dates if ref not in used and _bounds(dates[ref])[1] > newest
    ):
        raise FrameworkError(
            f"{key}: la respuesta no mira la fuente más reciente del bloque ({newer}): una "
            "respuesta que se apoya en lo antiguo dice lo que quizá ya no es"
        )
    # Lo citado en la respuesta, letra por letra en alguna de las frases en que se apoya.
    quotes = [statements[item]["quote"] for item in rests_on]
    if invented := [
        cited for cited in _QUOTED.findall(question["answer"])
        if not any(cited in quote for quote in quotes)
    ]:
        raise FrameworkError(
            f"{key}: la respuesta cita lo que no dicen las frases en que se apoya ({invented})"
        )


def _claims(text: str) -> list[str]:
    # La misma regla que el bloque: lo negado no reclama (`read_contract.claims`).
    return claims(text, CLAIM_WORDS)


def _repo_path(path: object) -> bool:
    """Un fichero del repositorio, con ruta relativa y barras: lo que se puede buscar en él.

    Ni absoluta, ni con unidad de Windows («C:/…», que `PurePosixPath` toma por relativa), ni
    que suba de nivel, ni una carpeta («.», «backend/»).
    """
    if not isinstance(path, str) or not path.strip() or "\\" in path or ":" in path:
        return False
    if path.endswith("/"):
        return False
    parts = PurePosixPath(path).parts
    return bool(parts) and not PurePosixPath(path).is_absolute() and ".." not in parts


def _validate_coverage(block: dict[str, Any]) -> None:
    """La tabla de lo que pide cada frase y lo que hace EMMA, sin decir más de lo que hay.

    Lo que pide una fila está, letra por letra, en su frase: no se le hace pedir a NASA lo que
    no escribió. Un «cubre» o un «en parte» nombra el fichero de EMMA que lo hace; el texto
    sobre EMMA no reclama conformidad, como el de cada bloque.
    """
    key = block["id"]
    table = block.get("coverage")
    if table is None:
        return
    if not isinstance(table, dict) or not _text(table, "about"):
        raise FrameworkError(f"{key}: una tabla de cobertura sin `about`, que dice qué es «cubre»")
    # El `about` define «cubre» ante quien lee: tampoco puede reclamar conformidad.
    if said := _claims(table["about"]):
        raise FrameworkError(f"{key}: el `about` de la tabla reclama conformidad ({said})")
    rows = table.get("rows")
    if not isinstance(rows, list) or not rows:
        raise FrameworkError(f"{key}: una tabla de cobertura sin filas")
    quotes = {item["id"]: item["quote"] for item in block["statements"]}
    asked: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict) or not all(
            _text(row, name) for name in ("statement", "asks", "emma")
        ):
            raise FrameworkError(f"{key}: una fila sin su frase, lo que pide o qué hace EMMA")
        where = f"{key}/{row['statement']}"
        if row["statement"] not in quotes:
            raise FrameworkError(f"{where}: la fila no es de una frase del bloque")
        if row["asks"] not in quotes[row["statement"]]:
            raise FrameworkError(
                f"{where}: «{row['asks']}» no está, letra por letra, en la frase que lo pide"
            )
        if (row["statement"], row["asks"]) in asked:
            raise FrameworkError(f"{where}: «{row['asks']}» tiene dos filas")
        asked.add((row["statement"], row["asks"]))
        # `isinstance` antes del `in`: una lista no se busca en un dict (TypeError, no un rechazo).
        if not isinstance(row.get("coverage"), str) or row["coverage"] not in COVERAGES:
            raise FrameworkError(f"{where}: cobertura {row.get('coverage')!r} desconocida")
        files = row.get("files")
        if not isinstance(files, list) or not all(_repo_path(path) for path in files):
            raise FrameworkError(f"{where}: `files` son rutas del repositorio, relativas")
        if row["coverage"] != "outside" and not files:
            raise FrameworkError(
                f"{where}: «{COVERAGES[row['coverage']]}» sin el fichero de EMMA que lo hace"
            )
        if said := _claims(row["emma"]):
            raise FrameworkError(f"{where}: el texto sobre EMMA reclama conformidad ({said})")


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Rechaza lo que no se pueda sostener con la fuente delante, o que afirme de más sobre EMMA."""
    try:
        first = dt.date.fromisoformat(raw["read_on"])
    except (KeyError, TypeError, ValueError):
        raise FrameworkError(
            "falta `read_on`: una lectura sin fecha no se puede contrastar"
        ) from None

    def own_read_on(value: Any, ref_id: str) -> None:
        """La fecha propia de una fuente: una fecha, y no anterior a `first`, la de arriba."""
        try:
            own = dt.date.fromisoformat(value)
        except (TypeError, ValueError):
            raise FrameworkError(
                f"{ref_id}: `read_on` no es una fecha: una lectura sin fecha no se puede "
                "contrastar"
            ) from None
        # La fecha general es la de la primera lectura: una fuente no se leyó antes.
        if own < first:
            raise FrameworkError(
                f"{ref_id}: `read_on` anterior a la primera lectura ({raw['read_on']}): "
                "una errata de fecha no se sirve"
            )

    # El contrato común de las fuentes; la fecha propia de una fuente, con la regla de aquí.
    sources = check_sources(raw, FrameworkError, EXTENTS, own_read_on=own_read_on)
    seen: set[str] = set()
    gaps_seen: set[str] = set()
    for block in raw["blocks"]:
        if not all(_text(block, field) for field in ("id", "title", "about")):
            raise FrameworkError("un bloque sin `id`, `title` o `about`")
        key = block["id"]
        if not block["statements"]:
            raise FrameworkError(f"{key}: un bloque sin ninguna frase leída no se sirve")
        for item in block["statements"]:
            _validate_statement(key, item, sources)
            if item["id"] in seen:
                raise FrameworkError(f"{key}/{item['id']}: identificador repetido")
            seen.add(item["id"])
            if (gap := item.get("gap")) is not None:
                if gap["id"] in gaps_seen:
                    raise FrameworkError(
                        f"{key}/{item['id']}: dos estados para el hueco {gap['id']}"
                    )
                gaps_seen.add(gap["id"])
        _validate_question(block)
        _validate_coverage(block)
        if not _text(block, "emma"):
            raise FrameworkError(f"{key}: falta qué hace EMMA, aparte de lo que pide la fuente")
        # Lo negado no reclama («EMMA no es conforme a…»): la misma regla que en las fichas de
        # credibilidad (`read_contract.claims`).
        if claimed := claims(block["emma"], CLAIM_WORDS):
            raise FrameworkError(f"{key}: el texto sobre EMMA reclama conformidad ({claimed})")
        if not all(isinstance(line, str) and line.strip() for line in block["not_read"]):
            raise FrameworkError(f"{key}: una línea vacía en `not_read`")
    return raw


def read_on(raw: dict[str, Any], ref_id: str) -> str:
    """El día en que se leyó una fuente: el suyo si lo declara, si no el de toda la lectura.

    Las fuentes no se leyeron todas el mismo día (la lectura de MEDPRAT, del ATCS y de
    OCHMO-TB-002 es de la decimocuarta ronda; la del memorando de 2025, de la decimoquinta):
    poner a una frase la fecha de otra lectura sería decir que se contrastó cuando aún no se había
    leído.
    """
    return str(raw["sources"][ref_id].get("read_on", raw["read_on"]))


@cache
def read() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(READ_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def cited_refs() -> frozenset[str]:
    """Las fichas del registro que sostienen alguna frase leída."""
    return frozenset(
        item["ref"] for block in read()["blocks"] for item in block["statements"]
    )


def gap_status(gap_id: str) -> dict[str, Any]:
    """El estado leído de un hueco del Roadmap, con su frase, su dirección y la fecha de lectura.

    Quien nombra un hueco ante el usuario lo toma de aquí: un hueco sin estado leído falla en
    vez de servirse como si siguiera abierto.
    """
    raw = read()
    for block in raw["blocks"]:
        for item in block["statements"]:
            gap = item.get("gap")
            if gap is not None and gap["id"] == gap_id:
                found = {
                    "id": gap_id,
                    "status": gap["status"],
                    "status_text": GAP_STATUSES[gap["status"]],
                    "statement": item["id"],
                    "quote": item["quote"],
                    "where": item["where"],
                    "url": _url(item),
                    "source": "Human Research Roadmap",
                    "read_on": read_on(raw, item["ref"]),
                }
                # En inglés cambian la palabra del estado y la sección leída, que son de EMMA;
                # la frase y el nombre de la fuente son de NASA y salen como están.
                found["status_text"] = i18n.loc(found["status_text"])
                found["where"] = i18n.localized(found["where"], READ_PATH)
                return found
    raise FrameworkError(f"{gap_id}: no hay estado leído de este hueco")


def gap_statuses() -> dict[str, str]:
    """Cada hueco con estado leído y ese estado."""
    return {
        item["gap"]["id"]: item["gap"]["status"]
        for block in read()["blocks"]
        for item in block["statements"]
        if item.get("gap") is not None
    }


def payload() -> dict[str, Any]:
    """Lo leído como se sirve: la cita y el alcance de cada lectura se resuelven aquí."""
    raw = read()
    sources = raw["sources"]

    def statement(item: dict[str, Any]) -> dict[str, Any]:
        ref = registry.get(item["ref"])
        source = sources[item["ref"]]
        return {
            "id": item["id"],
            "label": item["label"],
            "quote": item["quote"],
            "ref": ref.id,
            "source": ref.source,
            "title": ref.title,
            "url": _url(item),
            "where": item["where"],
            "read_on": read_on(raw, item["ref"]),
            "extent": source["extent"],
            "extent_text": i18n.loc(EXTENTS[source["extent"]]),
            "note": item.get("note"),
            "gap": None if item.get("gap") is None else {
                "id": item["gap"]["id"],
                "status": item["gap"]["status"],
                "status_text": i18n.loc(GAP_STATUSES[item["gap"]["status"]]),
            },
        }

    def question(block: dict[str, Any]) -> dict[str, Any] | None:
        asked = block.get("question")
        if asked is None:
            return None
        rests_on = set(asked["rests_on"])
        return {
            "text": asked["text"],
            "answer": asked["answer"],
            # En el orden del bloque, con la fecha de su documento: se ve qué es lo más nuevo.
            "rests_on": [
                {
                    "id": item["id"],
                    "label": item["label"],
                    "date": registry.get(item["ref"]).date,
                }
                for item in block["statements"]
                if item["id"] in rests_on
            ],
        }

    def coverage(block: dict[str, Any]) -> dict[str, Any] | None:
        table = block.get("coverage")
        if table is None:
            return None
        labels = {item["id"]: item["label"] for item in block["statements"]}
        counts = dict.fromkeys(COVERAGES, 0)
        for row in table["rows"]:
            counts[row["coverage"]] += 1
        return {
            "about": table["about"],
            "counts": counts,
            "rows": [
                {
                    "statement": row["statement"],
                    "label": labels[row["statement"]],
                    "asks": row["asks"],
                    "coverage": row["coverage"],
                    "coverage_text": i18n.loc(COVERAGES[row["coverage"]]),
                    "emma": row["emma"],
                    "files": list(row["files"]),
                }
                for row in table["rows"]
            ],
        }

    served = {
        "note": i18n.loc(NOTE),
        "read_on": raw["read_on"],
        "extents": [{"id": key, "text": i18n.loc(text)} for key, text in EXTENTS.items()],
        "gap_statuses": [
            {"id": key, "text": i18n.loc(text)} for key, text in GAP_STATUSES.items()
        ],
        "coverages": [{"id": key, "text": i18n.loc(text)} for key, text in COVERAGES.items()],
        "sources": [
            {
                "ref": ref_id,
                "title": registry.get(ref_id).title,
                "url": registry.get(ref_id).url,
                "read_on": read_on(raw, ref_id),
                "extent": source["extent"],
                "extent_text": i18n.loc(EXTENTS[source["extent"]]),
                "what": source["what"],
            }
            for ref_id, source in sources.items()
        ],
        "blocks": [
            {
                "id": block["id"],
                "title": block["title"],
                "about": block["about"],
                "statements": [statement(item) for item in block["statements"]],
                "question": question(block),
                "coverage": coverage(block),
                "emma": block["emma"],
                "not_read": list(block["not_read"]),
            }
            for block in raw["blocks"]
        ],
    }
    # Lo que redacta EMMA en el fichero (rótulos, notas, lo que hace, lo no leído), por su hermano
    # inglés, al salir y sobre una copia: `read()` y su validación siguen viendo el castellano.
    # La frase de la fuente, lo que pide y los títulos de las fichas no están en el hermano.
    return i18n.localized(served, READ_PATH)
