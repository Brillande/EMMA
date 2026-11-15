"""Credibilidad de cada capa que predice o infiere (decimosexta ronda, E10).

La ficha de credibilidad solo vale si cubre todas las cifras que EMMA rotula INFERIDAS o PREDICHAS
y ninguna más, y si lo que dice de cada factor no se convierte en un nivel que nadie evaluó. Estas
pruebas leen el código para lo primero: una función nueva que rotule una cifra sin ficha, o una
ficha que nombre una función que ya no rotula, hacen fallar la suite. Y rompen el fichero de datos
a propósito para lo segundo.
"""

from __future__ import annotations

import ast
import copy
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analysis import inferred, radiation, trend
from app.evidence import credibility
from app.evidence.credibility import FACTOR_IDS, GROUPS, CredibilityError
from app.main import app
from app.text_guard import check

APP = Path(credibility.__file__).resolve().parents[1]
BACKEND = APP.parent
MARKS = {"inferred", "predicted"}
# Donde se define el vocabulario de tipos: nombrarlo no es rotular una cifra.
VOCABULARY = {("ingest/fhir.py", "ObservationType")}
STATUS = "/api/status → "


def _raw() -> dict[str, Any]:
    return copy.deepcopy(credibility.read())


def _labels() -> Counter[tuple[str, str]]:
    """Cuántas veces escribe cada función de `app/` un tipo INFERIDO o PREDICHO, por tipo.

    Cuenta la cadena suelta ("inferred") y el miembro del enumerado (ObservationType.INFERRED),
    en cualquier sitio salvo como clave de un diccionario (la lista `inferred` de `/status` es un
    nombre de campo, no un rótulo) o dentro de una comparación (`tipo == "inferred"` lee el
    rótulo, no lo pone). Lo que se escribe fuera de toda función sale como `módulo.py:(módulo)`.
    """
    found: Counter[tuple[str, str]] = Counter()
    for path in sorted(APP.rglob("*.py")):
        found += _labels_in(path.relative_to(APP).as_posix(), path.read_text(encoding="utf-8"))
    return found


def _labels_in(module: str, source: str) -> Counter[tuple[str, str]]:
    """Los rótulos de un módulo (ver `_labels`)."""
    found: Counter[tuple[str, str]] = Counter()
    tree = ast.parse(source)
    # Lo que se lee y no se escribe: claves de diccionario y operandos de una comparación, también
    # los elementos de una colección comparada (`tipo in ("inferred", "predicted")`).
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            skipped |= {id(key) for key in node.keys if key is not None}
        elif isinstance(node, ast.Compare):
            for item in (node.left, *node.comparators):
                skipped.add(id(item))
                if isinstance(item, (ast.Tuple, ast.List, ast.Set)):
                    skipped |= {id(element) for element in item.elts}

    def visit(node: ast.AST, scope: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            inner = scope
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = [*scope, child.name]
            mark: str | None = None
            if id(child) in skipped:
                pass
            elif isinstance(child, ast.Constant) and child.value in MARKS:
                mark = str(child.value)
            elif isinstance(child, ast.Attribute) and child.attr in {"INFERRED", "PREDICTED"}:
                # El miembro del enumerado por cualquier camino: `ObservationType.INFERRED`,
                # `fhir.ObservationType.INFERRED` o un alias.
                mark = child.attr.lower()
            if mark is not None and (module, ".".join(scope[:1])) not in VOCABULARY:
                found[(f"{module}:{'.'.join(scope) or '(módulo)'}", mark)] += 1
            visit(child, inner)

    visit(tree, [])
    return found


# Cuántos rótulos pone hoy cada función con ficha. Una cifra nueva dentro de una función que ya
# tiene ficha no cambia el conjunto de funciones, pero sí esta cuenta: quien la añada tiene que
# mirar si la ficha la cubre (y entonces subir la cuenta) o si necesita la suya.
LABELS = {
    ("analysis/trend.py:projection", "predicted"): 1,
    ("analysis/radiation.py:mission_dose", "inferred"): 1,
    ("analysis/radiation.py:scales", "inferred"): 1,
    # La proyección y la carrera proyectada (PREDICHAS) y la horquilla por tipo (INFERIDA).
    ("analysis/radiation.py:mission_projection", "predicted"): 2,
    ("analysis/radiation.py:mission_projection", "inferred"): 1,
    ("analysis/inferred.py:bone_density_band", "inferred"): 1,
    ("api/routes.py:crew_status", "inferred"): 1,
    ("environment/dosimetry.py:DoseEstimate.to_dict", "inferred"): 1,
}


def _marked_paths(node: Any, path: str = "") -> Iterator[str]:
    """La ruta de cada objeto rotulado INFERIDO o PREDICHO en una respuesta (`[]`: elemento)."""
    if isinstance(node, dict):
        # El recuento de `provenance` también se llama así, y es un diccionario: no es un rótulo.
        if isinstance(node.get("observation_type"), str) and node["observation_type"] in MARKS:
            yield path
        for key, value in node.items():
            yield from _marked_paths(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for value in node:
            yield from _marked_paths(value, f"{path}[]")


# --------------------------------------------------------------------------- #
# Lo leído y la cobertura
# --------------------------------------------------------------------------- #


def test_the_eleven_factors_of_the_standard_are_all_there_in_their_group() -> None:
    raw = credibility.read()
    assert [group["id"] for group in raw["groups"]] == list(GROUPS)
    assert [item["id"] for item in raw["factors"]] == list(FACTOR_IDS)
    assert len(GROUPS["capability"]) == 5 and len(GROUPS["results"]) == 6
    # Cada pregunta empieza por el nombre del factor en la norma: es la fila de las tablas 5 y 12.
    for item in raw["factors"]:
        assert item["question"].split(":")[0].startswith(item["name"].split("/")[0])


def test_every_function_that_labels_a_figure_has_its_card_and_back() -> None:
    labelled = set(_labels())
    assert labelled, "la búsqueda no encuentra ningún rótulo: la prueba no comprueba nada"
    carded = set(credibility.marked_sites())
    assert labelled - carded == set(), "rotulan una cifra sin ficha de credibilidad"
    assert carded - labelled == set(), "fichas de funciones que ya no rotulan nada"


def test_a_new_label_inside_a_carded_function_does_not_pass_unseen() -> None:
    assert dict(_labels()) == LABELS


def test_reading_a_label_is_not_labelling() -> None:
    """Una comparación lee el tipo; una clave de diccionario lo nombra: ninguna rotula."""
    reads = (
        'def f(o):\n    if o.observation_type == "inferred":\n        return {"inferred": 1}\n'
        '    if o.observation_type in ("inferred", "predicted"):\n        return None\n'
    )
    assert _labels_in("x.py", reads) == Counter()
    writes = (
        'TYPE = "predicted"\n'
        "class C:\n    def g(self):\n"
        "        return {'observation_type': ObservationType.INFERRED}\n"
        "def h():\n    return fhir.ObservationType.PREDICTED, OT.INFERRED\n"
    )
    assert _labels_in("x.py", writes) == Counter({
        ("x.py:(módulo)", "predicted"): 1,
        ("x.py:C.g", "inferred"): 1,
        ("x.py:h", "predicted"): 1,
        ("x.py:h", "inferred"): 1,
    })


def test_every_model_version_is_the_one_the_code_writes() -> None:
    by_layer = {
        layer["id"]: layer["model_version"] for layer in credibility.read()["layers"]
    }
    assert by_layer["trend-projection"] == trend.PROJECTION_MODEL
    assert by_layer["mission-dose"] == radiation.MISSION_DOSE_MODEL
    assert by_layer["mission-dose-projection"] == radiation.PROJECTION_MODEL
    assert by_layer["bone-density-band"] == inferred.BMD_MODEL
    # Las demás no llevan modelo y dicen por qué.
    named = {"trend-projection", "mission-dose", "mission-dose-projection", "bone-density-band"}
    assert {key for key, model in by_layer.items() if model is not None} == named


# Lo que no corre, o no cuenta, en la suite por defecto: fuera de ella (`live`, `external`), saltado
# (`skip`, y `skipif` por si se cumple) o con el fallo esperado (`xfail`).
OUT_OF_SUITE = {"live", "external", "skip", "skipif", "xfail"}


def _is_pytestmark(node: ast.stmt) -> ast.expr | None:
    """El valor de `pytestmark = ...` o `pytestmark: ... = ...` en el módulo, si lo es."""
    if isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
    ):
        return node.value
    if (
        isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        and node.target.id == "pytestmark"
    ):
        return node.value
    return None


def _marks(node: ast.AST) -> set[str]:
    """Las marcas `pytest.mark.<x>` que lleva una función o, con `pytestmark`, un módulo."""
    return {
        sub.attr for sub in ast.walk(node)
        if isinstance(sub, ast.Attribute)
        and isinstance(sub.value, ast.Attribute) and sub.value.attr == "mark"
    }


def test_every_test_a_card_names_exists_and_runs_in_the_default_suite() -> None:
    """Una prueba `live` o `external` no corre en la suite: nombrarla exageraría lo verificado."""
    for layer in credibility.read()["layers"]:
        for item in layer["tests"]:
            file, name = item.split("::")
            path = BACKEND / file
            assert path.is_file(), f"{layer['id']}: {file} no existe"
            tree = ast.parse(path.read_text(encoding="utf-8"))
            defs = [
                node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == name
            ]
            assert defs, (layer["id"], item)
            assert not _test_marks(tree, defs[0]) & OUT_OF_SUITE, (
                f"{layer['id']}: {item} no corre en la suite por defecto"
            )


def _test_marks(tree: ast.Module, function: ast.FunctionDef) -> set[str]:
    """Las marcas de una prueba: las suyas y las de `pytestmark` en su módulo."""
    values = [value for node in tree.body if (value := _is_pytestmark(node)) is not None]
    module_marks: set[str] = set().union(*(_marks(value) for value in values))
    return module_marks | set().union(*(_marks(d) for d in function.decorator_list))


@pytest.mark.parametrize(("source", "mark"), [
    ("@pytest.mark.live\ndef test_x():\n    pass\n", "live"),
    ("@pytest.mark.skip(reason='x')\ndef test_x():\n    pass\n", "skip"),
    ("@pytest.mark.skipif(True, reason='x')\ndef test_x():\n    pass\n", "skipif"),
    ("@pytest.mark.xfail\ndef test_x():\n    pass\n", "xfail"),
    ("pytestmark = pytest.mark.external\ndef test_x():\n    pass\n", "external"),
    ("pytestmark: list[Any] = [pytest.mark.live]\ndef test_x():\n    pass\n", "live"),
])
def test_the_marks_of_a_test_are_read(source: str, mark: str) -> None:
    """La comprobación de arriba ve la marca, venga de donde venga: si no, aceptaría cualquiera."""
    tree = ast.parse("import pytest\n" + source)
    function = tree.body[-1]
    assert isinstance(function, ast.FunctionDef)
    assert mark in _test_marks(tree, function) & OUT_OF_SUITE


def test_every_route_a_card_names_exists() -> None:
    """`served_in` empieza por la ruta: una ruta renombrada deja la ficha señalando a nada."""
    # Del esquema OpenAPI: los routers incluidos no se despliegan en `app.routes`.
    paths = set(app.openapi()["paths"])
    for layer in credibility.read()["layers"]:
        for place in layer["served_in"]:
            route = place.split(" ")[0]
            assert route in paths, f"{layer['id']}: {route} no es una ruta de la aplicación"


def test_what_status_serves_as_inferred_or_predicted_has_a_card(client: TestClient) -> None:
    assert client.post(
        "/api/simulate", params={"scenario": "cardiovascular-deconditioning", "days": 40}
    ).status_code == 201
    # Con dosis previa declarada la carrera y su proyección también llevan rótulo.
    assert client.post("/api/crew/profile", json={
        "prior_missions": 1, "prior_career_dose_msv": 120.0, "declared_by": "CDR",
    }).status_code == 201
    status = client.get("/api/status").json()
    served = set(_marked_paths(status))
    declared = {
        place.removeprefix(STATUS)
        for layer in credibility.read()["layers"]
        for place in layer["served_in"]
        if place.startswith(STATUS)
    }
    assert served - declared == set(), "la ruta sirve cifras rotuladas sin ficha"
    # Y el escenario las ejercita todas: si una deja de servirse, la ficha sobra o el nombre cambió.
    assert declared - served == set()


def test_the_framework_route_serves_every_card_without_a_level(client: TestClient) -> None:
    body = client.get("/api/framework").json()["credibility"]
    assert [layer["id"] for layer in body["layers"]] == [
        layer["id"] for layer in credibility.read()["layers"]
    ]
    for layer in body["layers"]:
        assert [item["id"] for item in layer["factors"]] == list(FACTOR_IDS)
        assert all(set(item) == {"group", "id", "name_es", "state"} for item in layer["factors"])
        assert layer["observation_type_text"] in {"INFERIDO", "PREDICHO"}
    assert {source["ref"] for source in body["sources"]} == {"nasa-std-7009b", "nasa-hdbk-7009a"}
    assert "Sin nivel ni puntuación" in body["note"]


def _strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def test_what_the_cards_say_passes_the_language_guard() -> None:
    payload = credibility.payload()
    # Las frases de la norma van en inglés y tal cual: el filtro es para lo que redacta EMMA.
    block = payload["criticality"]
    quoted = {item["quote"] for item in payload["statements"]} | {
        group["quote"] for group in payload["groups"]
    } | {factor["question"] for group in payload["groups"] for factor in group["factors"]} | {
        item["quote"] for item in block["statements"]
    } | {axis["quote"] for axis in block["axes"]}
    texts = [text for text in _strings(payload) if text not in quoted]
    # «dosis» a secas es la de radiación (como en `test_radiation_projection.py`).
    found = [
        (text, finding) for text in texts for finding in check(text)
        if (finding.category, finding.match.lower()) != ("dosing", "dosis")
    ]
    assert found == []


# --------------------------------------------------------------------------- #
# El cargador rechaza lo que no se puede sostener
# --------------------------------------------------------------------------- #


def _layer(raw: dict[str, Any]) -> dict[str, Any]:
    layer: dict[str, Any] = raw["layers"][0]
    return layer


def _breaks(change: Any) -> dict[str, Any]:
    raw = _raw()
    change(raw)
    return raw


BROKEN = {
    "un campo de nivel": lambda raw: _layer(raw).__setitem__("level", 2),
    "un nivel dentro del texto": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Validación de nivel 3 con datos de vuelo."
    ),
    "una puntuación sobre cuatro": lambda raw: _layer(raw)["factors"].__setitem__(
        "verification", "Verificación 2/4."
    ),
    "un factor callado": lambda raw: _layer(raw)["factors"].pop("robustness"),
    "un factor vacío": lambda raw: _layer(raw)["factors"].__setitem__("uncertainty", " "),
    "un factor de más en la ficha": lambda raw: _layer(raw)["factors"].__setitem__(
        "use-history", "Ninguno."
    ),
    "un campo de puntuación con tilde y mayúscula": lambda raw: _layer(raw).__setitem__(
        "Puntuación", 2
    ),
    "un nivel con dos puntos": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Nivel: 3."
    ),
    "un nivel en romanos": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Nivel III."
    ),
    "niveles en plural": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Entre los niveles 2 y 3."
    ),
    "un nivel en palabra": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Nivel tres."
    ),
    "el rótulo más alto de la norma": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Evidencia gold-standard."
    ),
    "una ruta servida que puntúa": lambda raw: _layer(raw)["served_in"].append(
        "/api/risks (nivel 3)"
    ),
    "una ruta servida que reclama conformidad": lambda raw: _layer(raw)["served_in"].append(
        "/api/risks (conforme a la norma)"
    ),
    "un factor de la norma omitido": lambda raw: raw["factors"].pop(),
    "un grupo de la norma omitido": lambda raw: raw["groups"].pop(),
    "un grupo repetido": lambda raw: raw["groups"].insert(0, copy.deepcopy(raw["groups"][0])),
    "sin la clave del modelo": lambda raw: _layer(raw).pop("model_note"),
    "lo que se lee primero reclama conformidad": lambda raw: raw.__setitem__(
        "about", "EMMA cumple NASA-STD-7009B."
    ),
    "una línea de fuera de alcance que puntúa": lambda raw: raw["out_of_scope"].append(
        "El simulador tiene nivel 4."
    ),
    "una fuente que no está en el registro": lambda raw: raw["sources"].__setitem__(
        "no-existe", {"extent": "full", "what": "x"}
    ),
    "sin fichas de capa": lambda raw: raw.pop("layers"),
    "un factor en el grupo que no es": lambda raw: raw["factors"][0].__setitem__(
        "group", "results"
    ),
    "un texto que reclama conformidad": lambda raw: _layer(raw)["factors"].__setitem__(
        "use-management", "Cumple la norma."
    ),
    "lo de EMMA reclama conformidad": lambda raw: raw.__setitem__(
        "emma", "EMMA es conforme a NASA-STD-7009B."
    ),
    "una cifra medida con ficha": lambda raw: _layer(raw).__setitem__(
        "observation_type", "measured"
    ),
    "sin modelo y sin decir por qué": lambda raw: _layer(raw).update(
        {"model_version": None, "model_note": None}
    ),
    "con modelo y con nota": lambda raw: _layer(raw).__setitem__("model_note", "otra"),
    "una función mal escrita": lambda raw: _layer(raw).__setitem__("sites", ["trend.projection"]),
    "sin pruebas": lambda raw: _layer(raw).__setitem__("tests", []),
    "sin ruta que la sirva": lambda raw: _layer(raw).__setitem__("served_in", ["predicciones"]),
    "dos fichas con el mismo nombre": lambda raw: raw["layers"].append(
        copy.deepcopy(raw["layers"][0])
    ),
    "una frase sin sitio": lambda raw: raw["statements"][0].__setitem__("where", ""),
    "una frase de un documento sin lectura declarada": lambda raw: raw["statements"][0]
    .__setitem__("ref", "nasa-imm"),
    "un documento sin cuánto se leyó": lambda raw: raw["sources"]["nasa-std-7009b"].__setitem__(
        "extent", "skimmed"
    ),
    "un documento de fuera de NASA": lambda raw: raw["sources"].__setitem__(
        "mmash", {"extent": "full", "what": "x"}
    ),
    "sin fecha de lectura": lambda raw: raw.pop("read_on"),
    "sin decir que no se evaluó": lambda raw: raw.__setitem__("not_assessed", ""),
    "una línea vacía en lo no leído": lambda raw: raw["not_read"].append(" "),
    # De la revisión de código: formas de escribir un nivel que la primera guarda no veía.
    "un nivel con guion": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Validación nivel-3."
    ),
    "un nivel con letra": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Level 2b."
    ),
    "un nivel con «de»": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Un nivel de 3."
    ),
    "un nivel en ordinal": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Alcanza el tercer nivel."
    ),
    "una nota de tres sobre cuatro": lambda raw: _layer(raw)["factors"].__setitem__(
        "verification", "Verificación: 3 de 4."
    ),
    "una capa dada por validada": lambda raw: _layer(raw)["factors"].__setitem__(
        "validation", "Validada frente a datos de vuelo."
    ),
    "una negación que no alcanza al reclamo": lambda raw: _layer(raw)["factors"].__setitem__(
        # La negación queda a dos palabras, pero en otra frase: no alcanza.
        "validation", "Ninguna duda: validada frente a datos de vuelo."
    ),
    "el sitio de una frase que puntúa": lambda raw: raw["statements"][0].__setitem__(
        "where", "Tabla 7, nivel 3"
    ),
    "el sitio de un factor que reclama": lambda raw: raw["factors"][0].__setitem__(
        "where", "§E.3.1, conforme a la Tabla 5"
    ),
    "el requisito de un grupo que puntúa": lambda raw: raw["groups"][0].__setitem__(
        "requirement", "[M&S 48], nivel 2"
    ),
    # Decimoctava ronda (U14): el Apéndice D se lee, y su matriz no se aplica.
    "una consecuencia clasificada": lambda raw: _axis(
        raw, "decision", "Consecuencia catastrófica."
    ),
    "una influencia clasificada en inglés": lambda raw: _axis(raw, "influence", "Controlling."),
    "una categoría negada también clasifica": lambda raw: _axis(
        raw, "decision", "No es catastrófica."
    ),
    "una consecuencia traducida": lambda raw: _axis(raw, "decision", "Una decisión moderada."),
    "el color de una casilla": lambda raw: _axis(raw, "decision", "Cae en la casilla roja."),
    "la letra de una casilla": lambda raw: _axis(raw, "influence", "Casilla (Y)."),
    "un romano de la tabla de consecuencias": lambda raw: _axis(raw, "decision", "IV: grave."),
    "un nivel en un eje": lambda raw: _axis(raw, "influence", "Influencia de nivel 4."),
    "un eje que reclama conformidad": lambda raw: _axis(raw, "decision", "Cumple el Apéndice D."),
    "un eje callado": lambda raw: _layer(raw)["criticality"].pop("influence"),
    "un eje vacío": lambda raw: _axis(raw, "decision", " "),
    "un eje de más en la ficha": lambda raw: _layer(raw)["criticality"].__setitem__(
        "likelihood", "Ninguna."
    ),
    "los ejes de la ficha en otro orden": lambda raw: _layer(raw).__setitem__(
        "criticality", dict(reversed(list(_layer(raw)["criticality"].items())))
    ),
    "una ficha sin ejes": lambda raw: _layer(raw).pop("criticality"),
    "sin lo leído del apéndice": lambda raw: raw.pop("criticality"),
    "el apéndice sin fecha de lectura": lambda raw: raw["criticality"].__setitem__(
        "read_on", "ayer"
    ),
    "el apéndice leído antes que la norma": lambda raw: raw["criticality"].__setitem__(
        "read_on", "2026-10-01"
    ),
    "sin decir que la matriz no se aplicó": lambda raw: raw["criticality"].__setitem__(
        "not_applied", ""
    ),
    "lo de EMMA sobre la criticidad la clasifica": lambda raw: raw["criticality"].__setitem__(
        "not_applied", "La proyección de derivas es significativa."
    ),
    "lo de EMMA sobre la criticidad reclama conformidad": lambda raw: raw["criticality"]
    .__setitem__("about", "EMMA cumple el Apéndice D."),
    "un eje de la matriz omitido": lambda raw: raw["criticality"]["axes"].pop(),
    "los ejes de la matriz en otro orden": lambda raw: raw["criticality"]["axes"].reverse(),
    "una frase del apéndice sin lectura declarada": lambda raw: raw["criticality"]["statements"][0]
    .__setitem__("ref", "nasa-imm"),
    "una frase del apéndice sin sitio": lambda raw: raw["criticality"]["statements"][0]
    .__setitem__("where", ""),
    "una frase del apéndice con el nombre de otra": lambda raw: raw["criticality"]["statements"][0]
    .__setitem__("id", "purpose"),
    "el rótulo de una frase del apéndice que clasifica": lambda raw: raw["criticality"][
        "statements"
    ][0].__setitem__("label", "Influencia determinante"),
    "el nombre de un eje que clasifica": lambda raw: raw["criticality"]["axes"][0].__setitem__(
        "name_es", "Consecuencia (significant)"
    ),
    # De la revisión de código: la categoría tampoco cabe fuera de los ejes, y la última lectura
    # de una fuente es una fecha que no precede a la primera.
    "un factor que clasifica la consecuencia": lambda raw: _layer(raw)["factors"].__setitem__(
        "robustness", "Consecuencia catastrófica si falla."
    ),
    "lo de EMMA que clasifica la influencia": lambda raw: raw.__setitem__(
        "emma", "La influencia de cada capa es determinante."
    ),
    "el color de una casilla en un factor": lambda raw: _layer(raw)["factors"].__setitem__(
        "use-assessment", "Cae en la casilla de color rojo."
    ),
    "la última lectura de la norma antes de la primera": lambda raw: raw["sources"][
        "nasa-std-7009b"
    ].__setitem__("read_on", "2026-10-01"),
    "la última lectura de la norma sin fecha": lambda raw: raw["sources"][
        "nasa-std-7009b"
    ].__setitem__("read_on", "hace poco"),
    # Segunda revisión de código (U14): los atajos que quedaban.
    "el apéndice fechado en forma compacta": lambda raw: raw["criticality"].__setitem__(
        "read_on", "20261026"
    ),
    "la última lectura de la norma en semana ISO": lambda raw: raw["sources"][
        "nasa-std-7009b"
    ].__setitem__("read_on", "2026-W43-1"),
    "la última lectura de la norma sin rastro en su ficha": lambda raw: raw["sources"][
        "nasa-std-7009b"
    ].__setitem__("read_on", "2026-10-28"),
    "el apéndice fechado otro día que su fuente": lambda raw: raw["criticality"].__setitem__(
        "read_on", "2026-11-30"
    ),
    "el nivel 5 del apéndice": lambda raw: _axis(raw, "decision", "Consecuencia de nivel 5."),
    "una fila de la matriz": lambda raw: _axis(raw, "decision", "Cae en la fila 4."),
    "una categoría en romano sin dos puntos": lambda raw: _axis(
        raw, "influence", "Categoría III."
    ),
    "una consecuencia en inglés como adjetivo": lambda raw: _axis(
        raw, "decision", "Consecuencia: Critical."
    ),
    "el color lejos de la casilla": lambda raw: _axis(
        raw, "decision", "Casilla de la matriz roja."
    ),
    "la letra de una casilla en minúscula": lambda raw: _axis(raw, "influence", "Casilla (r)."),
    "una categoría con la tilde suelta": lambda raw: _axis(
        raw, "decision", "No es catastrófica."
    ),
    "el nombre en inglés de un eje que clasifica": lambda raw: raw["criticality"]["axes"][0]
    .__setitem__("name", "Decision Consequence: Catastrophic"),
    "un modelo con nombre de categoría": lambda raw: _layer(raw).update(
        model_version="catastrophic-v1", model_note=None
    ),
}


def _axis(raw: dict[str, Any], axis: str, text: str) -> None:
    _layer(raw)["criticality"][axis] = text

# Y lo que no es un nivel ni un reclamo pasa: una ficha honrada dice justo esto.
ACCEPTED = {
    "una cuenta de pruebas": "Pasan 3 de 4 pruebas de la suite.",
    "un número que no es de nivel": "Hay dos niveles: uno de ellos es el diario.",
    "una magnitud": "Por debajo de un nivel de 0,3 mSv al día.",
    "una implementación negada": "Ninguna implementación de referencia con que compararla.",
    "un cumplimiento negado": "EMMA no cumple ni reclama la norma.",
    "una validación negada": "No está validada frente a un dosímetro.",
}


@pytest.mark.parametrize("case", list(BROKEN))
def test_the_loader_refuses_what_cannot_be_sustained(case: str) -> None:
    with pytest.raises(CredibilityError):
        credibility.validate(_breaks(BROKEN[case]))


# Defensas que se solapan: con otra que también rechaza el caso, quitar una no se notaría. Estas
# exigen que el rechazo venga de la suya, por su mensaje (segunda revisión de código, U14).
BY_ITS_OWN_DEFENSE = {
    "sin fecha de lectura": r"^falta `read_on`",
    "niveles en plural": r"es un nivel",
    "el apéndice leído antes que la norma": r"anterior a la primera lectura de la norma",
    "la última lectura de la norma antes de la primera": r"anterior a la primera lectura \(",
    "la última lectura de la norma en semana ISO": r"no es una fecha",
    "la última lectura de la norma sin rastro en su ficha": r"no anota la lectura",
    "el apéndice fechado en forma compacta": r"`criticality`: falta `read_on`",
    "el apéndice fechado otro día que su fuente": r"no casan",
}


@pytest.mark.parametrize("case", list(BY_ITS_OWN_DEFENSE))
def test_each_overlapping_defense_refuses_by_itself(case: str) -> None:
    with pytest.raises(CredibilityError, match=BY_ITS_OWN_DEFENSE[case]):
        credibility.validate(_breaks(BROKEN[case]))


@pytest.mark.parametrize("case", list(ACCEPTED))
def test_the_loader_lets_through_what_is_neither_a_level_nor_a_claim(case: str) -> None:
    raw = _raw()
    _layer(raw)["factors"]["robustness"] = ACCEPTED[case]
    assert credibility.validate(raw)["layers"]


def test_a_broken_address_is_said_as_a_broken_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """`urlsplit` lanza `ValueError` con «https://[host»: sale como lo que es, fichero roto."""
    real = credibility.registry.get

    def broken(ref_id: str) -> Any:
        ref = real(ref_id)
        return type("Ref", (), {"id": ref.id, "url": "https://[standards.nasa.gov"})()

    monkeypatch.setattr(credibility.registry, "get", broken)
    with pytest.raises(CredibilityError, match="mal formado"):
        credibility.validate(_raw())


def test_a_broken_card_file_does_not_take_the_framework_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una ficha rota no se sirve, pero EIMO, el IMM y lo leído de NASA siguen en su sitio."""

    def refuse() -> dict[str, Any]:
        raise CredibilityError("rota a propósito")

    monkeypatch.setattr(credibility, "payload", refuse)
    response = client.get("/api/framework")
    assert response.status_code == 200
    body = response.json()
    assert body["credibility"] is None
    assert body["read_sources"] and body["imm"]


def test_a_card_without_the_model_keys_says_so_by_name() -> None:
    """Sin la clave, lo que se sirve fallaría al leerla: el cargador lo dice antes y por qué."""
    raw = _raw()
    _layer(raw).pop("model_note")
    with pytest.raises(CredibilityError, match="van siempre"):
        credibility.validate(raw)


def test_the_file_as_it_is_validates() -> None:
    assert credibility.validate(_raw())["layers"]


# --------------------------------------------------------------------------- #
# La criticidad del uso: el Apéndice D, leído y sin aplicar (decimoctava ronda, U14)
# --------------------------------------------------------------------------- #


def test_appendix_d_is_read_on_its_own_day_and_no_longer_said_unread() -> None:
    raw = credibility.read()
    block = raw["criticality"]
    assert block["read_on"] == "2026-10-26" > raw["read_on"]
    # Lo que se leyó de la norma lo dice, con el día; y el Apéndice D ya no figura como no leído.
    assert "2026-10-26" in raw["sources"]["nasa-std-7009b"]["what"]
    assert "Apéndice D entero" in raw["sources"]["nasa-std-7009b"]["what"]
    assert not any("Apéndice D" in line and "no se ha leído" in line for line in raw["not_read"])
    notes = credibility.registry.get("nasa-std-7009b").notes or ""
    assert "Leído en parte el 2026-10-23" in notes and "El 2026-10-26" in notes
    # Cada frase del apéndice está en el texto de la norma tal como se citó, con su página.
    for item in block["statements"]:
        assert item["ref"] == "nasa-std-7009b"
        assert item["where"].endswith(tuple(f"p. {page}" for page in (20, 56, 57, 59)))
    # Quién determina la criticidad, en palabras de la norma: la razón de no aplicar la matriz.
    who = {item["id"]: item["quote"] for item in block["statements"]}["criticality-who"]
    assert who.startswith("Program and project management, in collaboration with the delegated")
    assert "nadie con esa autoridad la ha hecho" in block["not_applied"]


def test_every_card_says_what_there_is_on_both_axes_and_no_cell() -> None:
    assert credibility.AXES == ("decision", "influence")
    for layer in credibility.read()["layers"]:
        assert list(layer["criticality"]) == list(credibility.AXES)
    # La única cifra que entra en el riesgo lo dice en su eje de la decisión.
    supplied = next(
        layer for layer in credibility.read()["layers"] if layer["id"] == "supplied-cumulative-dose"
    )
    assert "única de estas cifras que entra en el riesgo" in supplied["criticality"]["decision"]


def test_the_framework_route_serves_the_axes_of_every_card(client: TestClient) -> None:
    body = client.get("/api/framework").json()["credibility"]
    block = body["criticality"]
    assert block["read_on"] == "2026-10-26"
    # La norma se sirve con su última lectura, la del apéndice; la guía, con la primera.
    read = {source["ref"]: source["read_on"] for source in body["sources"]}
    assert read == {"nasa-std-7009b": "2026-10-26", "nasa-hdbk-7009a": "2026-10-23"}
    assert [axis["id"] for axis in block["axes"]] == list(credibility.AXES)
    assert all(item["source"] for item in block["statements"])
    names = {axis["id"]: axis["name_es"] for axis in block["axes"]}
    for layer in body["layers"]:
        assert [item["axis"] for item in layer["criticality"]] == list(credibility.AXES)
        for item in layer["criticality"]:
            assert set(item) == {"axis", "name_es", "state"}
            assert item["name_es"] == names[item["axis"]] and item["state"].strip()


@pytest.mark.parametrize(
    "text",
    [
        # Nombrar la criticidad o la significación estadística no es clasificar.
        "La criticidad no se ha determinado.",
        "Sin análisis de la significación del cambio.",
        # Una palabra que contiene una categoría no es la categoría.
        "Los verdaderos datos de vuelo no llegan a EMMA.",
        # Palabras corrientes que no son una categoría de la matriz (revisión de código).
        "EMMA funciona sin red, y en menor medida con ella.",
        "La pantalla verde de la consola no cambia.",
    ],
)
def test_an_axis_that_names_no_category_passes(text: str) -> None:
    raw = _raw()
    _axis(raw, "influence", text)
    assert credibility.validate(raw)["layers"]
