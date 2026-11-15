"""El contrato común de lo leído (`evidence/read_contract.py`) y su validación al arrancar.

Tres cosas, cada una con su prueba:

- los seis cargadores rechazan las mismas formas rotas de `sources`, cada uno con su error y su
  motivo (antes, cinco de ellos rompían con un `AttributeError` o un `TypeError` sin explicación);
- la negación no cuenta como reclamo, con una sola regla para los dos paneles del marco;
- los seis ficheros se validan al importar la aplicación (`app/main.py`), y uno roto no deja
  arrancar y dice cuál y por qué.
"""

from __future__ import annotations

import ast
import copy
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app import main
from app.evidence import (
    credibility,
    cycle_physiology,
    flight_direction,
    instruments_read,
    light_exposure,
    menopause_physiology,
    nasa_framework,
    read_contract,
    registry,
    research_countermeasures,
)

APP = Path(read_contract.__file__).parents[1]

# Cada cargador, con su error y el fichero que lee.
LOADERS: dict[str, tuple[ModuleType, type[ValueError], Path]] = {
    "credibility": (credibility, credibility.CredibilityError, credibility.READ_PATH),
    "cycle_physiology": (
        cycle_physiology, cycle_physiology.CyclePhysiologyError, cycle_physiology.READ_PATH
    ),
    "flight_direction": (
        flight_direction, flight_direction.FlightDirectionError, flight_direction.READ_PATH
    ),
    "instruments_read": (
        instruments_read, instruments_read.InstrumentsError, instruments_read.READ_PATH
    ),
    "light_exposure": (light_exposure, light_exposure.LightExposureError, light_exposure.READ_PATH),
    "menopause_physiology": (
        menopause_physiology,
        menopause_physiology.MenopausePhysiologyError,
        menopause_physiology.READ_PATH,
    ),
    "nasa_framework": (nasa_framework, nasa_framework.FrameworkError, nasa_framework.READ_PATH),
    "research_countermeasures": (
        research_countermeasures,
        research_countermeasures.ResearchError,
        research_countermeasures.RESEARCH_PATH,
    ),
}


def _raw(path: Path) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return raw


def _first_source(raw: dict[str, Any]) -> str:
    return next(iter(raw["sources"]))


BROKEN_SOURCES: dict[str, tuple[Callable[[dict[str, Any]], None], str]] = {
    "sources que no son un objeto": (
        lambda raw: raw.__setitem__("sources", list(raw["sources"])), "`sources` tiene que decir"
    ),
    "sin sources": (lambda raw: raw.pop("sources"), "`sources` tiene que decir"),
    "una ficha que no es un objeto": (
        lambda raw: raw["sources"].__setitem__(_first_source(raw), "leído"), "cuánto se leyó"
    ),
    "un extent que no es texto": (
        lambda raw: raw["sources"][_first_source(raw)].__setitem__("extent", ["full"]),
        "cuánto se leyó",
    ),
    "un extent que no es de la tabla": (
        lambda raw: raw["sources"][_first_source(raw)].__setitem__("extent", "por encima"),
        "cuánto se leyó",
    ),
    "sin decir qué se leyó": (
        lambda raw: raw["sources"][_first_source(raw)].__setitem__("what", " "), "cuánto se leyó"
    ),
    "una ficha que no está en el registro": (
        lambda raw: raw["sources"].__setitem__("no-existe", {"extent": "full", "what": "x"}),
        "no-existe: .*no está en el registro",
    ),
}


@pytest.mark.parametrize("loader", list(LOADERS))
@pytest.mark.parametrize("case", list(BROKEN_SOURCES))
def test_every_loader_refuses_the_same_broken_sources_with_its_own_error(
    loader: str, case: str
) -> None:
    module, error, path = LOADERS[loader]
    raw = _raw(path)
    change, reason = BROKEN_SOURCES[case]
    change(raw)
    with pytest.raises(error, match=reason):
        module.validate(raw)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _uses_check_sources(tree: ast.Module) -> bool:
    """Si el módulo trae `check_sources` del contrato (con otro nombre también) o lo llama."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "app.evidence.read_contract"
            and any(alias.name == "check_sources" for alias in node.names)
        ):
            return True
        if isinstance(node, ast.Attribute) and node.attr == "check_sources":
            return True
    return False


def test_every_loader_with_sources_uses_the_one_contract() -> None:
    """Ningún cargador vuelve a llevar su copia: los seis usan el contrato, y ninguno compara
    por su cuenta con su tabla de alcances (`EXTENTS`), se escriba como se escriba."""
    for name, (module, _, _) in LOADERS.items():
        tree = _tree(Path(str(module.__file__)))
        assert _uses_check_sources(tree), name
        compared = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Compare)
            and any(isinstance(item, ast.Name) and item.id == "EXTENTS"
                    for item in (node.left, *node.comparators))
        ]
        assert not compared, name


def test_the_contract_returns_the_sources_and_checks_only_what_it_is_asked() -> None:
    raw = _raw(light_exposure.READ_PATH)
    assert read_contract.check_sources(raw, ValueError, instruments_read.EXTENTS) is raw["sources"]
    seen: list[tuple[str, str]] = []
    dates: list[tuple[Any, str]] = []
    ref_id = _first_source(raw)
    raw["sources"][ref_id]["read_on"] = "2026-10-23"
    read_contract.check_sources(
        raw,
        ValueError,
        instruments_read.EXTENTS,
        own_read_on=lambda value, ref: dates.append((value, ref)),
        authored=lambda ref, what: seen.append((ref, what)),
    )
    # La fecha propia, solo de la fuente que la lleva; el linter, sobre lo que se leyó de cada una.
    assert dates == [("2026-10-23", ref_id)]
    assert seen == [(ref, source["what"]) for ref, source in raw["sources"].items()]


def test_the_contract_checks_the_official_site_of_each_card_when_asked() -> None:
    raw = _raw(light_exposure.READ_PATH)
    with pytest.raises(ValueError, match="no es una fuente oficial de NASA"):
        read_contract.check_sources(
            raw, ValueError, instruments_read.EXTENTS, official_hosts=frozenset({"example.org"})
        )


def test_an_unregistered_card_keeps_the_registry_reason_as_its_cause() -> None:
    raw = _raw(nasa_framework.READ_PATH)
    raw["sources"]["no-existe"] = {"extent": "full", "what": "x"}
    with pytest.raises(nasa_framework.FrameworkError) as caught:
        nasa_framework.validate(raw)
    assert isinstance(caught.value.__cause__, registry.RegistryError)


@pytest.mark.parametrize(("text", "claimed"), [
    ("EMMA implementa la arquitectura CDSS.", ["implementa"]),
    ("EMMA no implementa la arquitectura CDSS.", []),
    ("Ninguna implementación de referencia.", []),
    ("No está validada frente a un dosímetro.", []),
    # La negación en otra frase, o a más de tres palabras, no alcanza.
    ("Ninguna duda: validada frente a datos de vuelo.", ["validad"]),
    ("No usa el IMM y por eso es conforme.", ["conforme"]),
    # Una palabra negada una vez y dicha otra, reclama.
    ("No es conforme hoy; mañana será conforme.", ["conforme"]),
    # Lo que lleva una palabra de negación y refuerza no niega (de la revisión de código).
    ("EMMA es sin duda conforme a la norma.", ["conforme"]),
    ("EMMA no solo implementa la arquitectura CDSS.", ["implementa"]),
    ("EMMA no sólo cumple la norma.", ["cumple"]),
    ("Not only validated against flight data.", ["validated"]),
    ("Sin lugar a dudas validada.", ["validad"]),
    # Y la negación de verdad, junto a uno de esos giros, sigue negando.
    ("Sin duda, EMMA no es conforme.", []),
])
def test_a_negation_close_to_the_word_is_not_a_claim(text: str, claimed: list[str]) -> None:
    words = (*nasa_framework.CLAIM_WORDS, *credibility.VALIDATION_WORDS)
    assert read_contract.claims(text, words) == claimed


def test_the_negation_rule_lives_in_one_place() -> None:
    """Ni las credenciales ni el panel de NASA llevan su copia de la regla de la negación."""
    for module in (credibility, nasa_framework):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        assert "_NEGATIONS" not in source and "def _negated" not in source
        assert "claims(" in source


# --------------------------------------------------------------------------- #
# Al arrancar
# --------------------------------------------------------------------------- #


def test_the_six_read_files_are_validated_when_the_app_is_imported() -> None:
    assert {path for path, _ in main.READ_FILES} == {path for _, _, path in LOADERS.values()}
    # Una llamada suelta, a nivel de módulo: al importar `app.main`, no en la primera petición.
    tree = ast.parse(Path(str(main.__file__)).read_text(encoding="utf-8"))
    calls = [
        node.value.func.id
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    ]
    assert "check_read_files" in calls


def test_every_loader_that_uses_the_contract_is_checked_at_startup() -> None:
    """Un cargador nuevo con el contrato de lo leído entra también en el arranque."""
    users = {
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if path.name != "read_contract.py" and _uses_check_sources(_tree(path))
    }
    assert users == {f"evidence/{name}.py" for name in LOADERS}


def test_the_app_entry_only_validates_the_read_files() -> None:
    """`main.py` importa los seis cargadores solo para validar su fichero: de cada uno toma la ruta
    y `read`, nada más. Lo que sirven sigue saliendo solo por sus rutas (y las pruebas de
    aislamiento de cada uno, que admiten `main.py`, se apoyan en esto)."""
    tree = _tree(Path(str(main.__file__)))
    used = {
        (node.value.id, node.attr)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in LOADERS
    }
    assert {attr for _, attr in used} <= {"READ_PATH", "RESEARCH_PATH", "read"}
    # Y no se pasan enteros a ningún sitio: cada nombre aparece solo delante de un atributo.
    bare = [
        node.id for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in LOADERS
    ]
    assert len(bare) == len([
        node for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in LOADERS
    ])


@pytest.mark.parametrize("loader", list(LOADERS))
def test_a_broken_read_file_stops_the_start_and_says_which_and_why(
    loader: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, path = LOADERS[loader]
    raw = _raw(path)
    raw["sources"]["no-existe"] = {"extent": "full", "what": "x"}
    broken = tmp_path / path.name
    broken.write_text(json.dumps(raw), encoding="utf-8")
    name = "RESEARCH_PATH" if loader == "research_countermeasures" else "READ_PATH"
    monkeypatch.setattr(module, name, broken)
    module.read.cache_clear()
    try:
        with pytest.raises(main.ReadFileError) as caught:
            main.check_read_files()
        message = str(caught.value)
        assert message.startswith(f"{path.name} no pasa su contrato: no-existe: ")
        assert "no está en el registro" in message
    finally:
        monkeypatch.undo()
        module.read.cache_clear()


def test_a_file_that_is_not_json_also_stops_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = tmp_path / light_exposure.READ_PATH.name
    broken.write_text("{ roto", encoding="utf-8")
    monkeypatch.setattr(light_exposure, "READ_PATH", broken)
    light_exposure.read.cache_clear()
    try:
        with pytest.raises(main.ReadFileError, match="light_exposure_read.json no pasa su"):
            main.check_read_files()
    finally:
        monkeypatch.undo()
        light_exposure.read.cache_clear()


def test_a_file_with_another_shape_says_the_class_of_its_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un `KeyError` solo dice la clave: el arranque dice también la clase."""
    raw = _raw(light_exposure.READ_PATH)
    del raw["statements"]
    broken = tmp_path / light_exposure.READ_PATH.name
    broken.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(light_exposure, "READ_PATH", broken)
    light_exposure.read.cache_clear()
    try:
        with pytest.raises(main.ReadFileError, match="contrato: KeyError\\('statements'\\)"):
            main.check_read_files()
    finally:
        monkeypatch.undo()
        light_exposure.read.cache_clear()


def test_the_real_files_pass_at_startup() -> None:
    main.check_read_files()
    for module, _, _ in LOADERS.values():
        assert copy.deepcopy(module.read())
