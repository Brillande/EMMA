# SPDX-License-Identifier: AGPL-3.0-or-later
"""La ficha de SOUP de Polaris dice lo que el código hace hoy, o esta prueba falla.

Por qué existe: `compliance/software-safety-classification.md` §4.2 clasifica la copia literal de
Polaris como SOUP y le da una fila por herramienta en uso: qué se espera de ella, qué módulo la
llama, qué pasa si falla y qué la vigila. Una tabla así se queda atrás sin hacer ruido, y en ese
mismo documento ya pasó dos veces: `scipy` figuró como «ninguno» mientras el visor 3D lo usaba, y
el párrafo que decía que Polaris no era SOUP siguió citando el commit que se copió primero cuando
la copia ya iba por otro. Aquí la ficha se lee como dato y se contrasta con lo que hay:

  * el inventario: `EMMA_USES` (que `tests/test_polaris_bridge.py` ata a los `load("…")` de
    `backend/app`), los `load("…")` de `backend/scripts` y las cargas indirectas de `INDIRECT`;
  * quién llama a cada herramienta, con el extractor `ast` de esa misma prueba;
  * qué nombres le pide el código a cada una, con el lector `ast` de
    `tests/test_polaris_texts.py` (el que ata la tabla de `NOTICE`): la fila de `visor3d` calló
    `_caja_de` hasta el 2026-10-08, y un nombre privado que no está escrito no se revisa al
    sincronizar;
  * las pruebas y las campañas de EMMA que cita, en `backend/tests/`;
  * el resultado de las pruebas de Polaris, en `polaris/PRUEBAS.md`, y la que cada herramienta
    declara como suya en `polaris/tools/fichas/`; toda roja o saltada sobre una herramienta en
    uso tiene que estar en la tabla de anomalías;
  * las bibliotecas que cada herramienta con fila importa, leídas de la copia con `ast`: o
    tienen ficha en la lista de SOUP del §4, o están en `NOT_REQUIRED` con su motivo;
  * los peligros, en `compliance/risk-management-file.md`;
  * el commit, en `polaris/ADOPTADO.txt`, y las versiones de los entornos aparte, en sus guiones;
  * lo que Polaris publica de sus propios fallos (`polaris/docs/lo-que-falta.md` y su
    `CHANGELOG.md`): la ficha dice que se leyó y qué alcanza a EMMA, y eso solo vale para el
    texto que se leyó. Aquí se guarda su huella (`REVIEWED`); si la copia trae otro, falla hasta
    que alguien lo vuelva a leer;
  * qué hace cada herramienta de la copia **al importarse**, medido: `GET /api/polaris/estado`
    importa las que nadie llama, y «dormida» no es lo mismo que «inerte». La primera medida
    (2026-10-08) encontró una que lanza `git`, y desde el 2026-10-09 el inventario no la importa
    (`polaris.NOT_IMPORTED`). Ahora se miden dos cosas, en un intérprete aparte con un gancho de
    auditoría: que pedir el inventario no hace nada, y que lo que la ficha declara de una
    herramienta excluida es lo que hace cuando se la importa a propósito;
  * que los cerebros de nube, de los que la ficha dijo que no se copiaban, están en la copia y
    fuera del registro que EMMA le da a `ia`.

Qué NO comprueba: que «qué usa EMMA de ella» y «qué pasa si falla» describan bien el código, ni
que la clase de cada fila sea la correcta; ni que la evaluación de cada fallo publicado sea la
buena. Eso lo lee una persona.

No lee `NOTICE` ni importa `tests/test_polaris_headers.py` (que lo lee al importarse): el banco de
mutantes no copia ese fichero, y esta prueba tiene campañas: sobre el propio documento
(`tests/mutants/soup_polaris.json`), sobre el código que el documento describe
(`soup_polaris_callers.json`, `soup_polaris_indirect.json`) y sobre la copia
(`soup_polaris_published.json`, `soup_polaris_dormant.json`).

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Lee los ficheros de la
copia literal `polaris/` (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de
Polaris, «Beyond the Protocol») sin modificarla.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from app import polaris
from app.api import polaris as polaris_api
from tests.test_polaris_bridge import _loads_by_module
from tests.test_polaris_texts import emma_takes

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
COPY = REPO / "polaris"
DOC = REPO / "compliance" / "software-safety-classification.md"
RISKS = REPO / "compliance" / "risk-management-file.md"

# Las dos tablas de la ficha van entre estas marcas (como la tabla que escribe `deid_report.py`).
START, OTHER, END = (
    "<!-- soup-polaris:inicio", "<!-- soup-polaris:otro-camino -->", "<!-- soup-polaris:fin -->",
)
ANOMALIES = ("<!-- soup-polaris:anomalias -->", "<!-- soup-polaris:anomalias-fin -->")
PUBLISHED = ("<!-- soup-polaris:publicadas -->", "<!-- soup-polaris:publicadas-fin -->")
ON_IMPORT = ("<!-- soup-polaris:al-importar -->", "<!-- soup-polaris:al-importar-fin -->")

# Lo que Polaris publica de sus propios fallos, con la huella del texto que se leyó y se cruzó
# con la ficha (2026-10-08). No es la versión de la copia (esa es `ADOPTADO.txt`): es la marca de
# hasta dónde llega la lectura. Si cambia, se lee otra vez y se pone aquí la huella nueva.
REVIEWED = {
    "docs/lo-que-falta.md": "954fde78c0c0982a071e4d5443da00c57c2c0b6589592b228c33ac67dc881a3b",
    "CHANGELOG.md": "953e651d8fff144224ea69d22b97e9f4382740db8dfe0fc568f0eaeeac7cebb3",
}
# Lo que decía la ficha hasta esa fecha.
UNREVIEWED = "no se han revisado una a una"
CLOUD_LEFT_OUT = "ni se registran ni se copian"

# Lo que llega a la copia sin un `load("…")` literal. El extractor no lo ve, así que se declara
# aquí, con el fichero de EMMA que lo nombra. Una carga indirecta nueva se añade aquí y a la ficha.
INDIRECT = {
    "transcribe_audios": "app/voice.py",  # lo ejecuta como programa aparte, sin importarlo
    "esqueleto_referencia": "app/anatomy.py",  # sirve los datos que se generaron con él
    "kb_embed": "app/kb.py",  # lo trae `kb`; aquí se le apuntan las rutas del modelo
    "deid_ner": "app/reports/deid.py",  # `deid` la pide si está instalada
    "visor3d_web/": "app/volumes/polaris_web.py",  # el visor web: se compila y se sirve
}

# Cómo se llama en la lista de SOUP lo que el código importa con otro nombre.
DISTRIBUTIONS = {"PIL": "pillow", "skimage": "scikit-image", "whisper": "openai-whisper"}
# Lo que una herramienta con fila importa dentro de funciones que EMMA no llama: no es un
# requisito de EMMA. Cada una con su motivo; todo lo demás tiene que tener ficha en el §4.
NOT_REQUIRED = {
    "SimpleITK": "visor3d: leer y registrar una serie DICOM; EMMA le da el NIfTI ya cargado",
    "matplotlib": "visor3d: sus figuras de cortes; el congelado de EMMA lo excluye",
    "nnunetv2": "visor3d: `tumor_modelo`, su segundo modelo de lesiones",
    "totalsegmentator": "visor3d: segmentar con la API de Python; EMMA lanza el programa externo",
}

TOOL = re.compile(r"`(\w+/?)`")
# Un nombre de la copia tal como lo escribe una fila: `nombre` o `nombre()`.
NAME = re.compile(r"`(\w+)(?:\(\))?`")
MODULE = re.compile(r"`((?:app|scripts)/[\w/]+\.py)`")
EMMA_TEST = re.compile(r"`(tests/test_\w+\.py)`")
CAMPAIGN = re.compile(r"`(\w+\.json)`")
POLARIS_TEST = re.compile(r"`(test_\w+\.py)`(?: (verde|roja|saltada))?")
# Cómo lo dice la ficha (de «prueba») y cómo lo escribe `polaris/PRUEBAS.md`.
RESULTS = {"verde": "verde", "roja": "rojo", "saltada": "saltada"}
SAFETY_CLASS = re.compile(r"[ABC]†?|—")
HAZARD = re.compile(r"\bH(\d+)\b")
# Un sha tal como se escribe en prosa: siete o más cifras hexadecimales, con letra y con número.
SHA = re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b")
# Lo que decía el apartado hasta el 2026-10-07, cuando Polaris no se trataba como SOUP.
STALE = ("no SOUP: Polaris", "No se trata como SOUP")
DENIAL = re.compile(
    r"(?:Polaris|copia)[^.|]*?\bno (?:es|se trata como|se considera) SOUP", re.IGNORECASE
)


class Row(NamedTuple):
    tool: str
    uses: str
    modules: str
    safety_class: str
    failure: str
    watched_by: str
    polaris_tests: str


def document() -> str:
    return DOC.read_text(encoding="utf-8")


def _rows(table: str) -> dict[str, Row]:
    rows: dict[str, Row] = {}
    for line in table.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == len(Row._fields), f"fila con {len(cells)} celdas: {line[:70]}…"
        name = TOOL.match(cells[0])
        assert name, f"la primera celda no nombra una herramienta: {cells[0]}"
        assert name.group(1) not in rows, f"`{name.group(1)}` tiene dos filas"
        rows[name.group(1)] = Row(name.group(1), *cells[1:])
    return rows


def tables() -> tuple[dict[str, Row], dict[str, Row]]:
    """Las filas de la ficha: lo que `backend/app` carga por su nombre y lo que llega aparte."""
    text = document()
    marks = [text.find(mark) for mark in (START, OTHER, END)]
    assert -1 not in marks and marks == sorted(marks), "faltan las marcas de la ficha, o su orden"
    loaded, other = _rows(text[marks[0]:marks[1]]), _rows(text[marks[1]:marks[2]])
    twice = sorted(set(loaded) & set(other))
    assert not twice, f"con fila en las dos tablas: {twice}"
    return loaded, other


def rows() -> list[Row]:
    loaded, other = tables()
    return [*loaded.values(), *other.values()]


def callers() -> dict[str, set[str]]:
    """Qué ficheros de EMMA piden cada herramienta: los `load("…")` y las cargas indirectas."""
    found: dict[str, set[str]] = {}
    for folder in ("app", "scripts"):
        for name, modules in _loads_by_module(folder).items():
            found.setdefault(name, set()).update(modules)
    for name, module in INDIRECT.items():
        found.setdefault(name, set()).add(module)
    return found


def in_the_copy(tool: str) -> bool:
    """¿Está en `polaris/tools`? Un nombre acabado en `/` es una carpeta (el visor web)."""
    tools = COPY / "tools"
    return (tools / tool).is_dir() if tool.endswith("/") else (tools / f"{tool}.py").is_file()


def polaris_results() -> dict[str, str]:
    """El resultado de cada prueba de Polaris en esta máquina, según `polaris/PRUEBAS.md`."""
    found: dict[str, str] = {}
    for line in (COPY / "PRUEBAS.md").read_text(encoding="utf-8").splitlines():
        match = re.match(r"\| `(test_\w+\.py)` \| (\w+) \|", line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def declared_test(tool: str) -> str | None:
    """La prueba que la ficha de Polaris (la de su autora) da como la de la herramienta.

    Solo si viajó en la copia: `polaris_sync` no copia las pruebas que usan algo no copiado.
    """
    try:
        card = json.loads((COPY / "tools" / "fichas" / f"{tool}.py.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    declared = card.get("test") if isinstance(card, dict) else None
    name = Path(declared).name if isinstance(declared, str) and declared else None
    return name if name and (COPY / "tests" / name).is_file() else None


def adapted_origins() -> set[str]:
    """Los commits de Polaris que el código adaptado a mano cita en sus cabeceras («@ <sha>»)."""
    cited = re.compile(r"@\s*((?=[0-9a-f]*\d)[0-9a-f]{7,40})\b")
    found: set[str] = set()
    for folder in ("app", "scripts"):
        for path in (BACKEND / folder).rglob("*.py"):
            found.update(sha[:7] for sha in cited.findall(path.read_text(encoding="utf-8-sig")))
    return found


def blocks(text: str) -> list[str]:
    """Párrafos y elementos de lista: la unidad en la que una frase habla de una sola cosa."""
    return [block for block in re.split(r"\n\s*\n|\n(?=- )", text) if block.strip()]


def third_party_imports(tool: str) -> set[str]:
    """Lo que una herramienta de la copia importa y no es ni de Python ni otra herramienta suya.

    También lo que importa dentro de una función: un `import` tardío es un requisito igual, solo
    que falla más tarde.
    """
    tools = COPY / "tools"
    found: set[str] = set()
    for node in ast.walk(ast.parse((tools / f"{tool}.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return {
        name for name in found
        if name not in sys.stdlib_module_names and not (tools / f"{name}.py").is_file()
    }


def test_every_tool_emma_uses_has_a_row_and_no_row_is_made_up() -> None:
    loaded, other = tables()
    used = set(polaris_api.EMMA_USES)
    apart = set(callers()) - used
    checks = (
        (used - set(loaded), "`backend/app` la carga y no tiene fila"),
        (set(loaded) - used, "tiene fila entre las que `backend/app` carga, y no la carga"),
        (apart - set(other), "EMMA la usa por otro camino y no tiene fila"),
        (set(other) - apart, "tiene fila entre lo que llega por otro camino, y nada la usa"),
        ({name for name in (*loaded, *other) if not in_the_copy(name)}, "no está en polaris/tools"),
    )
    problems = [f"`{name}`: {why}" for names, why in checks for name in sorted(names)]
    assert not problems, "\n".join(problems)


def test_each_indirect_use_is_still_what_it_was() -> None:
    """Una carga indirecta no se ve con `ast`: al menos, su módulo la sigue nombrando."""
    by_name = {*_loads_by_module("app"), *_loads_by_module("scripts")}
    assert by_name, "el extractor ya no encuentra ningún `load`: esta prueba no miraría nada"
    for name, module in INDIRECT.items():
        assert name not in by_name, f"`{name}` ya se carga por su nombre: quítala de INDIRECT"
        source = (BACKEND / module).read_text(encoding="utf-8-sig")
        word = re.escape(name.rstrip("/"))
        assert re.search(rf"\b{word}\b", source), f"{module} ya no nombra a `{name}`"


def test_each_row_names_exactly_the_modules_that_call_the_tool() -> None:
    real = callers()
    problems = []
    for row in rows():
        cited, actual = set(MODULE.findall(row.modules)), real.get(row.tool, set())
        for module in sorted(cited - actual):
            why = "no la llama" if (BACKEND / module).is_file() else "no existe"
            problems.append(f"`{row.tool}`: la ficha cita {module}, que {why}")
        for module in sorted(actual - cited):
            problems.append(
                f"`{row.tool}`: la llama también {module}; añádelo a su fila, con lo que usa"
            )
    assert not problems, "\n".join(problems)


def test_each_row_writes_every_name_emma_asks_of_the_tool() -> None:
    """Llamado, leído o sustituido: lo que EMMA le pide a la copia está en su fila, tal cual.

    Solo en ese sentido. Una fila nombra además otras cosas (funciones de EMMA, otra
    herramienta), así que lo que sobra no se mira.
    """
    takes = emma_takes()
    assert "_caja_de" in takes["visor3d"]["app/volumes/geometry.py"], "el lector ya no lee nada"
    problems = []
    for row in rows():
        asked: set[str] = set().union(*takes.get(row.tool, {}).values())
        unwritten = sorted(asked - set(NAME.findall(row.uses)))
        if unwritten:
            problems.append(f"`{row.tool}`: EMMA le pide {unwritten} y su fila no lo escribe")
    assert not problems, "\n".join(problems)


def test_every_row_is_complete_and_keeps_the_draft_in_class_c() -> None:
    problems = []
    for row in rows():
        if not SAFETY_CLASS.fullmatch(row.safety_class):
            problems.append(f"`{row.tool}`: clase «{row.safety_class}» (A, B, C o —; † opcional)")
        # Invariante 6: el borrador de interpretación es Clase C por elemento.
        if "`app/interpret/" in row.modules and not row.safety_class.startswith("C"):
            problems.append(f"`{row.tool}`: corre en `app/interpret/` y la fila no dice Clase C")
        for label, cell in (("qué usa EMMA de ella", row.uses), ("qué pasa si falla", row.failure)):
            if len(cell) < 20:
                problems.append(f"`{row.tool}`: «{label}» está sin escribir")
    assert not problems, "\n".join(problems)


def section(heading: str) -> str:
    """Un apartado de primer nivel del documento, de su título al siguiente."""
    text = document()
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start:] if end == -1 else text[start:end]


def classified_elements() -> set[str]:
    """Los ficheros y carpetas con clase propia: la tabla de elementos del §3 y el §7."""
    declared = section("## 3. Elementos") + section("## 7. ")
    return set(re.findall(r"`((?:app/)?[\w/]+(?:\.py|/))`", declared))


def has_own_class(module: str, elements: set[str]) -> bool:
    short = module.removeprefix("app/")
    names = {element.removeprefix("app/") for element in elements}
    return short in names or any(name.endswith("/") and short.startswith(name) for name in names)


def test_the_dagger_marks_exactly_the_rows_whose_modules_have_no_class_of_their_own() -> None:
    """La † dice «este módulo no está en la tabla de elementos»: tiene que seguir siendo verdad."""
    text = document()
    elements = classified_elements()
    assert has_own_class("app/interpret/draft.py", elements), "no se lee la tabla del §3"
    note = next((block for block in blocks(text) if block.startswith("† ")), "")
    problems = []
    for row in rows():
        if row.safety_class == "—":
            continue  # no viaja en el producto: no es un elemento
        orphans = [m for m in MODULE.findall(row.modules) if not has_own_class(m, elements)]
        if orphans and not row.safety_class.endswith("†"):
            problems.append(f"`{row.tool}`: {orphans} no tienen fila en el §3 y falta la †")
        if not orphans and row.safety_class.endswith("†"):
            problems.append(f"`{row.tool}`: lleva † y todos sus módulos tienen fila en el §3")
        problems += [
            f"`{row.tool}`: la nota de la † no nombra {module}"
            for module in orphans
            if f"`{module}`" not in note
        ]
    assert not problems, "\n".join(problems)


def test_each_row_cites_emma_tests_and_campaigns_that_exist() -> None:
    problems = []
    for row in rows():
        tests, campaigns = EMMA_TEST.findall(row.watched_by), CAMPAIGN.findall(row.watched_by)
        if not tests and "Ninguna prueba de EMMA" not in row.watched_by:
            problems.append(f"`{row.tool}`: ni cita una prueba de EMMA ni dice que no la tiene")
        problems += [
            f"`{row.tool}`: cita {test}, que no existe"
            for test in tests
            if not (BACKEND / test).is_file()
        ]
        for campaign in campaigns:
            path = BACKEND / "tests" / "mutants" / campaign
            if not path.is_file():
                problems.append(f"`{row.tool}`: cita la campaña {campaign}, que no existe")
                continue
            # Una campaña cuenta para la fila si corre alguna de las pruebas que la fila cita.
            run = {str(test).split("::")[0] for test in json.loads(path.read_text("utf-8"))["test"]}
            if not run & set(tests):
                problems.append(f"`{row.tool}`: {campaign} no corre ninguna prueba de su fila")
    assert not problems, "\n".join(problems)


def test_what_the_fiche_says_of_polaris_own_tests_is_what_was_measured() -> None:
    results = polaris_results()
    assert results, "no se lee ningún resultado en polaris/PRUEBAS.md"
    problems = []
    for row in rows():
        cited = POLARIS_TEST.findall(row.polaris_tests)
        for name, result in cited:
            if not (COPY / "tests" / name).is_file():
                problems.append(f"`{row.tool}`: cita {name}, que no está en polaris/tests")
            elif not result:
                problems.append(f"`{row.tool}`: no dice si {name} está verde, roja o saltada")
            elif results.get(name) != RESULTS[result]:
                measured = results.get(name, "nada")
                problems.append(
                    f"`{row.tool}`: {name} figura como {result} y PRUEBAS.md dice {measured}"
                )
        names = {name for name, _ in cited}
        own = declared_test(row.tool)
        if own and own not in names:
            # Sin esto se podría citar solo la verde y callar la roja de la prueba principal.
            problems.append(f"`{row.tool}`: su ficha de Polaris declara {own} y no se cita")
        if not names:
            pattern = f"test_{row.tool.rstrip('/')}*.py"
            alike = sorted(path.name for path in (COPY / "tests").glob(pattern))
            if alike:
                problems.append(f"`{row.tool}`: dice no tener prueba en la copia y están {alike}")
    assert not problems, "\n".join(problems)


def test_every_red_or_skipped_polaris_test_on_a_used_tool_is_explained() -> None:
    """IEC 62304 pide evaluar las anomalías conocidas del SOUP: aquí, que ninguna se calle."""
    text = document()
    begin, finish = (text.find(mark) for mark in ANOMALIES)
    assert -1 < begin < finish, "faltan las marcas de la tabla de anomalías"
    explained = {
        name.group(1): line
        for line in text[begin:finish].splitlines()
        if line.startswith("| `") and (name := TOOL.match(line[2:]))
    }
    results = polaris_results()
    problems = []
    for row in rows():
        failing = [
            name
            for name, result in POLARIS_TEST.findall(row.polaris_tests)
            if result in ("roja", "saltada")
        ]
        line = explained.pop(row.tool, None)
        if line is None:
            if failing:
                problems.append(f"`{row.tool}`: {failing} no pasan aquí y nadie lo explica")
            continue
        if not failing:
            problems.append(f"`{row.tool}`: está entre las anomalías y su fila no cita ninguna")
        said = dict(POLARIS_TEST.findall(line))
        for name in failing:
            if name not in said:
                problems.append(f"`{row.tool}`: la tabla de anomalías no nombra {name}")
            elif results.get(name) != RESULTS.get(said[name]):
                problems.append(f"`{row.tool}`: {name} no figura allí con su resultado")
    problems += [f"`{name}`: está entre las anomalías y no tiene fila" for name in explained]
    assert not problems, "\n".join(problems)


def test_every_library_a_used_tool_imports_has_its_own_soup_entry() -> None:
    """Una tabla de dependencias se escribe leyendo los `import`: `reportlab` viajó sin ficha."""
    text = document()
    listed = set(re.findall(r"`([\w.-]+)`", text[text.index("## 4. SOUP"):text.index("### 4.1")]))
    imported: dict[str, set[str]] = {}
    for row in rows():
        if not row.tool.endswith("/"):
            for module in third_party_imports(row.tool):
                imported.setdefault(module, set()).add(row.tool)
    assert imported, "no se lee ningún `import` de terceros en la copia: no se miraría nada"
    missing = {
        module: sorted(tools)
        for module, tools in imported.items()
        if module not in NOT_REQUIRED and DISTRIBUTIONS.get(module, module) not in listed
    }
    assert not missing, f"la copia las importa y no están en la lista de SOUP del §4: {missing}"
    idle = sorted(set(NOT_REQUIRED) - set(imported))
    assert not idle, f"excepciones de NOT_REQUIRED que ya no hacen falta: {idle}"


def test_the_versions_given_for_the_separate_environments_are_the_pinned_ones() -> None:
    text = document()
    pins: list[tuple[str, str]] = []
    for script in ("install_voice.py", "install_deid_ner.py"):
        source = (BACKEND / "scripts" / script).read_text(encoding="utf-8")
        pins += re.findall(r'"([\w-]+)==([\w.]+)', source)
    assert pins, "los guiones de instalación ya no fijan ninguna versión"
    stale = [f"{name} {version}" for name, version in pins if f"`{name}` {version}" not in text]
    assert not stale, f"el documento no da la versión que instala el guion: {stale}"


def known_hazards() -> set[str]:
    known = set(re.findall(r"^### H(\d+) —", RISKS.read_text(encoding="utf-8"), flags=re.M))
    assert known, "no se lee ningún peligro en el expediente de riesgos"
    return known


def test_every_hazard_the_fiche_cites_is_in_the_risk_file() -> None:
    known = known_hazards()
    made_up = sorted(
        f"`{row.tool}`: H{number}"
        for row in rows()
        for number in HAZARD.findall(" ".join(row))
        if number not in known
    )
    assert not made_up, f"peligros que no están en risk-management-file.md: {made_up}"


def test_the_document_pins_no_polaris_commit_but_the_origin_of_the_adapted_code() -> None:
    """La versión de la copia es la de `ADOPTADO.txt`: un sha escrito aquí caduca en silencio."""
    adopted = polaris_api._adopted_commit(COPY)
    assert adopted and len(adopted) == 40
    origins = adapted_origins()
    assert origins, "ninguna cabecera cita ya el commit del que se adaptó su código"
    stale = []
    for block in blocks(document()):
        for sha in SHA.findall(block):
            is_origin = sha[:7] in origins and "adaptad" in block.lower()
            if not adopted.startswith(sha) and not is_origin:
                stale.append(f"{sha}, en «{' '.join(block.split())[:80]}…»")
    assert not stale, f"commits que no son el adoptado ({adopted[:7]}): {stale}"


def test_the_detector_reads_a_commit_and_not_a_date_or_a_version() -> None:
    whole = "0123456789abcdef0123456789abcdef01234567"
    assert SHA.findall(f"commit `7bf47257`, luego e3b588d y {whole}") == [
        "7bf47257", "e3b588d", whole,
    ]
    assert not SHA.findall("2026-10-07, Chromium 152.0.7977.130, PMID 7659438, e5-small, acceded")


def test_the_document_says_the_literal_copy_is_soup() -> None:
    flat = " ".join(document().split())
    assert re.search(r"copia literal \(`polaris/`\) es SOUP", flat), "ya no dice que es SOUP"
    denial = DENIAL.search(flat)
    assert not denial, f"vuelve a decir que Polaris no es SOUP: «…{denial.group(0)[-70:]}»"
    assert not [phrase for phrase in STALE if phrase in flat], "queda texto del apartado anterior"


def marked_table(marks: tuple[str, str]) -> dict[str, list[str]]:
    """Las filas de una tabla entre dos marcas: `{herramienta: [celdas]}`."""
    text = document()
    begin, finish = (text.find(mark) for mark in marks)
    assert -1 < begin < finish, f"faltan las marcas {marks[0]} … {marks[1]}, o su orden"
    table: dict[str, list[str]] = {}
    for line in text[begin:finish].splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        name = TOOL.match(cells[0])
        assert name, f"la primera celda no nombra una herramienta: {cells[0]}"
        assert name.group(1) not in table, f"`{name.group(1)}` tiene dos filas en {marks[0]}"
        table[name.group(1)] = cells
    return table


def test_what_polaris_publishes_was_read_as_the_copy_carries_it_today() -> None:
    """IEC 62304 pide evaluar lo que el SOUP publica de sus fallos: leído, y en esta versión."""
    changed = [
        name
        for name, digest in REVIEWED.items()
        if hashlib.sha256((COPY / name).read_bytes()).hexdigest() != digest
    ]
    assert not changed, (
        f"Polaris cambió {changed}: léelo entero, crúzalo con la tabla de lo que publica "
        "(compliance/software-safety-classification.md §4.2) y pon su huella nueva en REVIEWED"
    )
    flat = " ".join(document().split())
    assert UNREVIEWED not in flat, "el documento vuelve a decir que lo publicado está sin revisar"

    published = marked_table(PUBLISHED)
    assert published, "la tabla de lo que publica Polaris está vacía"
    with_row = {row.tool for row in rows()}
    results, hazards = polaris_results(), known_hazards()
    problems = []
    for tool, cells in published.items():
        if tool not in with_row:
            # Lo que no toca a una herramienta con fila se cuenta en una frase; no se lista.
            problems.append(f"`{tool}`: está entre lo publicado y no tiene fila en la ficha")
        if len(cells) != 3 or any(len(cell) < 20 for cell in cells[1:]):
            problems.append(f"`{tool}`: le falta decir qué se publica o qué alcanza a EMMA")
            continue
        said, verdict = cells[1], cells[2]
        if not verdict.startswith("**"):
            problems.append(f"`{tool}`: la evaluación no empieza por su veredicto, en negrita")
        watchers = EMMA_TEST.findall(verdict)
        if not watchers:
            problems.append(f"`{tool}`: la evaluación no dice qué prueba de EMMA lo vigila")
        problems += [
            f"`{tool}`: cita {test}, que no existe"
            for test in watchers
            if not (BACKEND / test).is_file()
        ]
        problems += [
            f"`{tool}`: cita la campaña {campaign}, que no existe"
            for campaign in CAMPAIGN.findall(verdict)
            if not (BACKEND / "tests" / "mutants" / campaign).is_file()
        ]
        for name, result in POLARIS_TEST.findall(f"{said} {verdict}"):
            if not (COPY / "tests" / name).is_file():
                problems.append(f"`{tool}`: cita {name}, que no está en polaris/tests")
            elif result and results.get(name) != RESULTS[result]:
                problems.append(f"`{tool}`: {name} figura como {result} y PRUEBAS.md no dice eso")
        problems += [
            f"`{tool}`: H{number} no está en risk-management-file.md"
            for number in HAZARD.findall(verdict)
            if number not in hazards
        ]
    assert not problems, "\n".join(problems)


def test_the_cloud_brains_are_in_the_copy_and_only_out_of_the_registry() -> None:
    """La ficha decía «ni se registran ni se copian», y lo segundo era falso: están copiados."""
    flat = " ".join(document().split())
    assert CLOUD_LEFT_OUT not in flat, "vuelve a decir que los cerebros de nube no se copian"
    assert "Los cerebros de nube sí están en la copia" in flat, "ya no dice que están copiados"
    attended = re.search(r"los atienden \(([^)]*)\)", flat)
    named = TOOL.findall(attended.group(1)) if attended else []
    assert named, "la ficha no nombra ningún módulo de los que atienden a los cerebros de nube"
    missing = [name for name in named if not in_the_copy(name)]
    assert not missing, f"la ficha dice que viajan y no están en polaris/tools: {missing}"

    original = json.loads((COPY / "tools" / "peripheries.json").read_text(encoding="utf-8"))
    cloud = [b["name"] for b in original["cerebros"] if b["name"] != polaris.LOCAL_BRAIN]
    assert cloud, "el registro de la copia ya no trae cerebros de nube: la frase sobra"
    given = polaris.registry()["cerebros"]
    assert isinstance(given, list) and [b["name"] for b in given] == [polaris.LOCAL_BRAIN]


# Lo que el inventario no importa y esta prueba tampoco importa a propósito, con su motivo. Todo
# lo demás de `polaris.NOT_IMPORTED` tiene que tener fila en la tabla `al-importar` y medirse.
NOT_MEASURED = {
    "transcribe_audios": "es un guion entero: importarlo donde estén sus dependencias cargaría "
    "un modelo de Whisper. Que no tiene función de entrada lo lee `tests/test_polaris_bridge.py`",
}

# Lo que corre en el intérprete aparte, con el estado en una carpeta vacía. Dos medidas, las dos
# por los eventos de auditoría de Python (PEP 578):
#
#   1. Pide el inventario (`app.polaris.inventory`, lo mismo que hace `GET /api/polaris/estado`) y
#      apunta lo que pasa mientras tanto. Cada cosa se anota a nombre del fichero de
#      `polaris/tools` que la hace (el marco más cercano en la pila); si no la hace ninguno, a
#      nombre de `<inventario>`.
#   2. Importa a propósito, con `app.polaris.load`, las herramientas que se le pasan (las que la
#      ficha declara que hacen algo al importarse) y apunta aparte lo que hace cada una.
#
# Antes de empezar se prueba a sí misma (`<control>`): escribe un fichero y lanza un proceso de
# verdad, y emite a mano el evento de una conexión (sin abrirla: los tests no tocan la red). Si
# el gancho no los viera, la medida saldría limpia sin haber mirado nada.
PROBE = '''
import json, os, subprocess, sys
from pathlib import Path

backend, state = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, backend)
import app
from app import polaris

polaris.state_dir = lambda: state / "polaris"
polaris.configure()
TOOLS = str(polaris.tools_dir().resolve())
WRITE = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
KINDS = {
    "proceso": ("subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn",
                "os.startfile", "os.fork"),
    "disco": ("os.mkdir", "os.rename", "os.remove", "os.rmdir", "os.chmod", "os.truncate",
              "os.link", "os.symlink", "os.utime", "shutil.copyfile", "shutil.copytree",
              "shutil.move", "shutil.rmtree", "tempfile.mkstemp", "tempfile.mkdtemp",
              "sqlite3.connect"),
    "red": ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname",
            "urllib.Request", "http.client.connect"),
}
KIND = {event: kind for kind, events in KINDS.items() for event in events}
loading, seen, on_purpose = [None], {}, {}
book = [seen]


def writes(args):
    path, mode, flags = (tuple(args) + (None, None, None))[:3]
    if str(path).endswith(".pyc"):
        return False  # lo escribe el intérprete, no la herramienta
    if isinstance(mode, str):
        return any(letter in mode for letter in "wax+")
    return isinstance(flags, int) and bool(flags & WRITE)


def hook(event, args):
    if loading[0] is None:
        return
    try:
        kind = KIND.get(event) or ("disco" if event == "open" and writes(args) else None)
        if kind is None:
            return
        who, frame = loading[0], sys._getframe(1)
        while frame is not None and who != "<control>":
            name = frame.f_code.co_filename
            if os.path.dirname(os.path.abspath(name)) == TOOLS:
                who = os.path.splitext(os.path.basename(name))[0]
                break
            frame = frame.f_back
        book[0].setdefault(who, {}).setdefault(kind, (event + " " + repr(args))[:300])
    except Exception as exc:  # un gancho que lanza rompería la importación que está mirando
        seen.setdefault("<sonda>", {})["rota"] = repr(exc)


sys.addaudithook(hook)
loading[0] = "<control>"
(state / "control.txt").write_text("x", encoding="utf-8")
subprocess.run([sys.executable, "-c", ""], check=False)
sys.audit("socket.connect", None, ("127.0.0.1", 9))
loading[0] = "<inventario>"
statuses = polaris.inventory()
loading[0] = None
skipped = sorted(status.name for status in statuses if not status.imported)
early = sorted(name for name in skipped if name in sys.modules)
loaded = {}
book[0] = on_purpose
for name in sys.argv[3:]:
    loading[0] = name
    try:
        polaris.load(name)
        loaded[name] = True
    except polaris.PolarisUnavailable:
        loaded[name] = False  # lo que hiciera antes de fallar ya está apuntado
loading[0] = None
report = {
    "app": app.__file__, "tools": sorted(status.name for status in statuses), "seen": seen,
    "skipped": skipped, "early": early, "on_purpose": on_purpose, "loaded": loaded,
}
(state / "seen.json").write_text(json.dumps(report), encoding="utf-8")
'''


def test_what_each_copied_tool_does_when_imported_is_what_the_fiche_declares(
    tmp_path: Path,
) -> None:
    """Pedir el inventario no hace nada, y lo excluido hace lo que la ficha dice si se importa.

    Va la última: es la única que lanza un intérprete, y las campañas paran en el primer rojo.
    """
    declared = {
        tool: {kind.lower() for kind in re.findall(r"\*\*(Proceso|Disco|Red)\b", cells[1])}
        for tool, cells in marked_table(ON_IMPORT).items()
    }
    excluded = set(polaris.NOT_IMPORTED)
    # Una herramienta que hace algo al importarse no puede seguir en el inventario; y una que el
    # inventario excluye, o se mide aquí o se dice por qué no.
    problems = [
        f"`{tool}`: la ficha declara que hace algo al importarse y el inventario la importa "
        "(añádela a `NOT_IMPORTED`, en app/polaris/__init__.py)"
        for tool in sorted(set(declared) - excluded)
    ]
    problems += [
        f"`{tool}`: el inventario no la importa y la ficha no dice qué hace al importarse "
        "(una fila en la tabla `al-importar`, o su motivo en NOT_MEASURED)"
        for tool in sorted(excluded - set(declared) - set(NOT_MEASURED))
    ]
    problems += [
        f"`{tool}`: está en NOT_MEASURED y el inventario ya la importa"
        for tool in sorted(set(NOT_MEASURED) - excluded)
    ]
    problems += [
        f"`{tool}`: está en NOT_MEASURED y tiene fila en la tabla: se mide"
        for tool in sorted(set(NOT_MEASURED) & set(declared))
    ]
    assert not problems, "\n".join(problems)

    result = subprocess.run(
        [
            sys.executable, "-B", "-X", "utf8", "-c", PROBE, str(BACKEND), str(tmp_path),
            *sorted(declared),
        ],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600, check=False,
        env={**os.environ, "EMMA_OFFLINE": "true", "EMMA_CACHE_DIR": str(tmp_path)},
    )
    assert result.returncode == 0, f"la sonda no terminó:\n{result.stderr[-2000:]}"
    report = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    # Con el backend instalado en modo editable, `import app` podría resolver a otra copia.
    assert Path(report["app"]).resolve().is_relative_to(BACKEND.resolve()), report["app"]
    copied = sorted(path.stem for path in (COPY / "tools").glob("*.py"))
    assert report["tools"] == copied, "la sonda no hizo el inventario de esta copia"
    assert report["skipped"] == sorted(excluded), "el inventario no excluye lo que declara"
    assert not report["early"], f"el inventario importó lo que dice no importar: {report['early']}"

    seen: dict[str, dict[str, str]] = report["seen"]
    assert "<sonda>" not in seen, f"el gancho de auditoría falló: {seen.get('<sonda>')}"
    control = seen.pop("<control>", {})
    assert set(control) == {"disco", "proceso", "red"}, f"la sonda no ve lo que hace: {control}"

    # 1. El inventario: ni un proceso, ni una escritura, ni una conexión, de nadie.
    problems = [
        f"`{tool}`: al hacer el inventario pasa algo ({kind}): {detail}. Si lo hace al importarse, "
        "va a `NOT_IMPORTED` y a la tabla `al-importar`"
        for tool, kinds in sorted(seen.items())
        for kind, detail in sorted(kinds.items())
    ]
    # 2. Lo excluido, importado a propósito: lo que la ficha declara, ni más ni menos. Es lo que
    # justifica la exclusión; si deja de hacerlo, la lista se puede revisar.
    measured: dict[str, dict[str, str]] = report["on_purpose"]
    problems += [
        f"`{tool}`: importada a propósito hace algo que la ficha no declara ({kind}): {detail}"
        for tool, kinds in sorted(measured.items())
        for kind, detail in sorted(kinds.items())
        if kind not in declared.get(tool, set())
    ]
    problems += [
        f"`{tool}`: la ficha declara que al importarse hace algo ({kind}) y no se ha medido"
        for tool, kinds in sorted(declared.items())
        for kind in sorted(kinds - set(measured.get(tool, {})))
    ]
    # La lista solo afecta al inventario: por su nombre se siguen cargando.
    problems += [
        f"`{tool}`: pedida por su nombre con `load` ya no carga"
        for tool, loaded in sorted(report["loaded"].items())
        if not loaded
    ]
    problems += [
        f"`{tool}`: está en la tabla y no dice qué hace (**Proceso**, **Disco** o **Red**)"
        for tool, kinds in sorted(declared.items())
        if not kinds
    ]
    assert not problems, "\n".join(problems)

    # Lo que el gancho no vería (una biblioteca nativa que escribe por su cuenta), al menos en
    # el estado: tras las dos medidas, ahí solo está lo que pusieron el adaptador y la sonda.
    left = sorted(
        path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()
    )
    assert left == ["control.txt", "polaris/peripheries.json", "seen.json"], left
