"""El inventario de la interfaz en inglés (`data/assistant_ui.en.json`) frente al castellano.

Por qué existe: el fichero inglés es solo datos y se empareja por id con `assistant_ui.json`. Si
un panel nuevo se queda sin su entrada, o un alias inglés se repite entre dos paneles, el
asistente en inglés abriría otra cosa o nada sin que ninguna prueba lo dijera. Aquí se coteja la
cobertura exacta de lo que no está apartado, la forma de cada entrada y los rótulos de pestaña
que la interfaz traduce por su lado y tienen que coincidir.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.assistant import catalog

DATA = Path(__file__).resolve().parents[1] / "app" / "data"

# Rótulos fijados entre unidades: la interfaz traduce las mismas pestañas y modos.
CONSOLE_LABELS = {"crew": "Crew console", "ground": "Earth console"}
SECTION_LABELS = {
    "crew": {
        "home": "Home", "radiation": "Radiation", "isolation": "Isolation", "gravity": "Gravity",
        "environment": "Environment", "nodes": "Distance and nodes",
        "hazards": "Hazards and alerts",
    },
    "ground": {
        "received": "Received status", "history": "History", "trends": "Trends",
        "habitat": "Habitat", "framework": "Framework and sources",
        "ledger": "Ledger and documents", "library": "Library",
    },
}
MODE_LABELS = {
    "lowVision": "Low vision", "essential": "Essential mode", "privacy": "Privacy",
    "highContrast": "High contrast", "rotation": "Rotate", "followSensor": "Follow the sensor",
    "followFace": "Follow the face (demo)", "voice": "Voice: read each new alert",
    "proactive": "EMMA takes the initiative", "wakeWord": "Listen for «EMMA»",
    "autoPrivacy": "Automatic privacy with another face",
}

_SPANISH_ONLY = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
_QUOTED_NAME = re.compile(r"«[^»]*»")
# Comprobación por muestreo: nada que suene a certificación, a diagnóstico o a orden médica.
_FORBIDDEN_IN_ABOUT = ("certified", "validated", "diagnos", "must take", "administer")


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((DATA / name).read_text(encoding="utf-8"))
    return loaded


def _spanish() -> dict[str, Any]:
    return _load("assistant_ui.json")


def _english() -> dict[str, Any]:
    return _load("assistant_ui.en.json")


def _kept_panels() -> set[str]:
    """Los paneles que quedan con las pestañas apartadas, como los calcula el catálogo."""
    catalog.use_set_aside(True)
    try:
        return set(catalog.catalog().panels)
    finally:
        catalog.use_set_aside(False)


def _kept_sections(console: str) -> set[str]:
    return {item["key"] for item in _spanish()["sections"][console]
            if item.get("set_aside") is not True}


def _entries(english: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any], bool]]:
    """Cada entrada con su dueño y si lleva rótulo (las pestañas de entorno no lo llevan)."""
    for key, item in english["consoles"].items():
        yield f"consoles.{key}", item, True
    for console in ("crew", "ground"):
        for key, item in english["sections"][console].items():
            yield f"sections.{console}.{key}", item, True
    yield "sections.environments", english["sections"]["environments"], False
    for key, item in english["modes"].items():
        yield f"modes.{key}", item, True
    for key, item in english["panels"].items():
        yield f"panels.{key}", item, True


def test_ids_are_exactly_the_ones_not_set_aside() -> None:
    spanish, english = _spanish(), _english()
    assert set(english) == {"_nota", "consoles", "sections", "modes", "panels"}
    assert isinstance(english["_nota"], str) and english["_nota"].strip()
    assert set(english["consoles"]) == {item["id"] for item in spanish["consoles"]}
    assert set(english["sections"]) == {"crew", "ground", "environments"}
    for console in ("crew", "ground"):
        assert set(english["sections"][console]) == _kept_sections(console), console
    assert set(english["modes"]) == {item["id"] for item in spanish["modes"]}
    kept = _kept_panels()
    assert kept, "el catálogo no dejó ningún panel"
    assert set(english["panels"]) == kept


def test_set_aside_is_restored_after_reading_the_kept_panels() -> None:
    _kept_panels()
    assert catalog.set_aside_active() is False


def test_every_entry_has_label_about_and_aliases() -> None:
    for owner, item, has_label in _entries(_english()):
        expected = {"label", "aliases", "about"} if has_label else {"aliases", "about"}
        assert set(item) == expected, owner
        if has_label:
            assert isinstance(item["label"], str) and item["label"].strip(), owner
        about = item["about"]
        assert isinstance(about, str) and about.strip(), owner
        assert len(about) <= catalog.ABOUT_MAX, f"{owner}: {len(about)} caracteres"
        assert "\n" not in about and "\r" not in about, owner
        aliases = item["aliases"]
        assert isinstance(aliases, list) and aliases, owner
        assert len(set(aliases)) == len(aliases), f"{owner}: alias repetido"


def test_aliases_are_already_in_plain_form() -> None:
    for owner, item, has_label in _entries(_english()):
        for alias in item["aliases"]:
            assert isinstance(alias, str) and alias, owner
            assert alias == catalog.plain(alias).strip(), f"{owner}: {alias!r}"
            assert alias.isascii(), f"{owner}: {alias!r}"
        if has_label:
            assert item["aliases"][0] == catalog.plain(item["label"]).strip(), owner


def test_no_two_panels_share_an_alias() -> None:
    owner_of: dict[str, str] = {}
    for key, item in _english()["panels"].items():
        for alias in item["aliases"]:
            assert alias not in owner_of, f"«{alias}»: {owner_of[alias]} y {key}"
            owner_of[alias] = key


def test_sections_of_one_console_do_not_share_an_alias() -> None:
    english = _english()
    for console in ("crew", "ground"):
        owner_of: dict[str, str] = {}
        for key, item in english["sections"][console].items():
            for alias in item["aliases"]:
                assert alias not in owner_of, f"{console} «{alias}»: {owner_of[alias]} y {key}"
                owner_of[alias] = key


def test_fixed_labels_agree_with_the_interface() -> None:
    english = _english()
    assert {key: item["label"] for key, item in english["consoles"].items()} == CONSOLE_LABELS
    for console, labels in SECTION_LABELS.items():
        found = {key: item["label"] for key, item in english["sections"][console].items()}
        assert found == labels, console
    assert {key: item["label"] for key, item in english["modes"].items()} == MODE_LABELS


def test_english_values_carry_no_spanish_only_characters() -> None:
    for owner, item, has_label in _entries(_english()):
        values = [item["about"], *item["aliases"]]
        if has_label:
            values.append(item["label"])
        for value in values:
            outside_names = _QUOTED_NAME.sub("", value)
            assert not _SPANISH_ONLY.search(outside_names), f"{owner}: {value!r}"


def test_about_texts_do_not_overclaim_or_order() -> None:
    for owner, item, _ in _entries(_english()):
        about = item["about"].lower()
        for word in _FORBIDDEN_IN_ABOUT:
            assert word not in about, f"{owner}: «{word}»"
