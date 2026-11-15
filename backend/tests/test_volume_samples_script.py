# SPDX-License-Identifier: AGPL-3.0-or-later
"""`build_volume_samples.py --only` no mueve la huella de las muestras que no se le piden.

Por qué existe: las huellas SHA-256 de `app/data/volume_samples/manifest.json` están publicadas, y
un almacén que ya registró una muestra la reconoce por ellas. Al regenerar `esqueleto-4` el
2026-10-08, rehacer las otras tres les cambiaba los bytes sin que nadie lo hubiera pedido; `--only`
nació para conservarlas, y se quedó sin prueba (auditoría del 2026-10-09). Lo que aquí se ata: con
`--only` las demás entradas salen idénticas y sus ficheros no se tocan, y una orden equivocada
(clave que no existe, argumentos en otro orden) aborta ANTES de escribir nada, en vez de conservar
la entrada de otra muestra o dejar una carpeta rehecha con un manifiesto que ya no la describe.

Sin TAC ni TotalSegmentator: se sustituye lo que el guion lee y construye (`nibabel.load`,
`assets.resample`, `assets.mask_loader`, `assets.build`) y `OUT` va a `tmp_path`. Lo que NO se
prueba aquí es que `assets.build` dé los mismos bytes dos veces, ni el contenido real de las
muestras (eso es de `tests/test_volumes.py`), ni el análisis de la línea de órdenes (`argparse`).

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

BACKEND = Path(__file__).resolve().parents[1]

# El orden del manifiesto publicado: la posición da el número de la clave.
SPECS = ["higado:s0816", "higado:s0048", "ojos:s0289", "esqueleto:s1152"]
KEYS = ["higado-1", "higado-2", "ojos-3", "esqueleto-4"]


def _load() -> ModuleType:
    """`scripts/` no es un paquete: el guion se carga por su ruta."""
    spec = importlib.util.spec_from_file_location(
        "emma_build_volume_samples_under_test", BACKEND / "scripts" / "build_volume_samples.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load()


class Builds:
    """Lo que el guion mandó construir, y unos bytes distintos en cada construcción: así una
    muestra rehecha sin pedirlo se nota en su fichero y en su huella."""

    def __init__(self) -> None:
        self.subjects: list[str] = []

    def load(self, path: Path) -> Path:
        self.subjects.append(Path(path).parent.name)
        return Path(path)

    def build(self, reference: Any, loader: Any, preset: Any) -> tuple[dict[str, bytes], Any]:
        stamp = f"{reference.parent.name}/{preset.key}/construcción {len(self.subjects)}".encode()
        return {"ct.nii.gz": b"ct " + stamp, "malla.bin": b"malla " + stamp}, {"lesiones": [1, 2]}


@pytest.fixture
def builds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Builds:
    import nibabel

    record = Builds()
    monkeypatch.setattr(script, "OUT", tmp_path / "volume_samples")
    monkeypatch.setattr(nibabel, "load", record.load)
    monkeypatch.setattr(script.assets, "resample", lambda image, voxel_mm: image)
    monkeypatch.setattr(script.assets, "mask_loader", lambda reference, masks: masks)
    monkeypatch.setattr(script.assets, "build", record.build)
    for spec in SPECS:
        subject = spec.split(":")[1]
        folder = tmp_path / "ct-sources" / subject
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(
            json.dumps({"meta": {"study_type": f"ct de {subject}"}}), encoding="utf-8"
        )
    return record


def _run(tmp_path: Path, specs: list[str], only: list[str] | None = None) -> None:
    script.main(specs, only, tmp_path / "ct-sources")


def _published(tmp_path: Path) -> dict[str, Any]:
    """Un manifiesto de pega ya publicado, con sus ficheros: lo que `--only` tiene que respetar.

    Las entradas llevan un campo que el guion no escribe: una entrada conservada es la que había,
    no una reconstruida que casualmente se le parece.
    """
    out = tmp_path / "volume_samples"
    samples = []
    for key, spec in zip(KEYS, SPECS, strict=True):
        preset, subject = spec.split(":")
        (out / key).mkdir(parents=True)
        (out / key / "ct.nii.gz").write_bytes(f"ct publicado de {key}".encode())
        (out / key / "visor.zip").write_bytes(f"visor publicado de {key}".encode())
        samples.append({
            "key": key, "nombre": f"publicada {key}", "preset": preset,
            "sujeto_dataset": subject, "sha256": {"ct.nii.gz": "c" * 64, "visor.zip": "f" * 64},
            "nota_publicada": f"solo está en la entrada de {key}",
        })
    (out / "manifest.json").write_text(
        json.dumps({"samples": samples}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {entry["key"]: entry for entry in samples}


def _manifest(tmp_path: Path) -> dict[str, Any]:
    raw = json.loads((tmp_path / "volume_samples" / "manifest.json").read_text(encoding="utf-8"))
    assert [entry["key"] for entry in raw["samples"]] == KEYS  # mismo orden que los argumentos
    return {entry["key"]: entry for entry in raw["samples"]}


def _files(tmp_path: Path) -> dict[str, tuple[bytes, int]]:
    """Cada fichero de la carpeta de muestras con sus bytes y su hora de escritura."""
    out = tmp_path / "volume_samples"
    return {
        path.relative_to(out).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(out.rglob("*")) if path.is_file()
    }


def _of(files: dict[str, tuple[bytes, int]], key: str) -> dict[str, tuple[bytes, int]]:
    return {name: value for name, value in files.items() if name.startswith(f"{key}/")}


# --- sin --only -----------------------------------------------------------------------------------


def test_without_only_every_sample_is_rebuilt(tmp_path: Path, builds: Builds) -> None:
    before = _published(tmp_path)

    _run(tmp_path, SPECS)

    assert builds.subjects == ["s0816", "s0048", "s0289", "s1152"]
    after = _manifest(tmp_path)
    out = tmp_path / "volume_samples"
    for key in KEYS:
        assert after[key] != before[key]
        assert "nota_publicada" not in after[key]
        # La huella del manifiesto es la de lo que hay en disco.
        for name in ("ct.nii.gz", "visor.zip"):
            digest = hashlib.sha256((out / key / name).read_bytes()).hexdigest()
            assert after[key]["sha256"][name] == digest
    assert [after[key]["nombre"] for key in KEYS] == [
        "Abdomen: hígado 1", "Abdomen: hígado 2", "Cabeza: órbitas 1",
        "Cuerpo entero: esqueleto 1",
    ]
    assert after["esqueleto-4"]["sujeto_dataset"] == "s1152"
    assert after["esqueleto-4"]["estudio_dataset"] == "ct de s1152"
    assert after["esqueleto-4"]["lesiones"] == 2


def test_without_only_no_published_manifest_is_needed(tmp_path: Path, builds: Builds) -> None:
    _run(tmp_path, SPECS)

    assert set(_manifest(tmp_path)) == set(KEYS)


# --- con --only -----------------------------------------------------------------------------------


@pytest.mark.parametrize("wanted", KEYS)
def test_only_keeps_the_other_entries_identical_and_their_files_untouched(
    tmp_path: Path, builds: Builds, wanted: str
) -> None:
    before = _published(tmp_path)
    files_before = _files(tmp_path)

    _run(tmp_path, SPECS, [wanted])

    assert builds.subjects == [before[wanted]["sujeto_dataset"]]  # no se lee ningún otro TAC
    after = _manifest(tmp_path)
    files_after = _files(tmp_path)
    for key in KEYS:
        if key == wanted:
            continue
        assert after[key] == before[key], key
        assert _of(files_after, key) == _of(files_before, key), key
    # La pedida sí se rehace: entrada nueva, ficheros nuevos y su huella.
    assert "nota_publicada" not in after[wanted]
    assert after[wanted]["sha256"]["ct.nii.gz"] == hashlib.sha256(
        files_after[f"{wanted}/ct.nii.gz"][0]
    ).hexdigest()
    assert files_after[f"{wanted}/ct.nii.gz"][0] != files_before[f"{wanted}/ct.nii.gz"][0]
    assert files_after[f"{wanted}/visor.zip"][0] != files_before[f"{wanted}/visor.zip"][0]


def test_only_numbers_the_rebuilt_name_counting_the_kept_ones(
    tmp_path: Path, builds: Builds
) -> None:
    _published(tmp_path)

    _run(tmp_path, SPECS, ["higado-2"])

    assert _manifest(tmp_path)["higado-2"]["nombre"] == "Abdomen: hígado 2"


def test_only_can_be_repeated(tmp_path: Path, builds: Builds) -> None:
    before = _published(tmp_path)

    _run(tmp_path, SPECS, ["higado-1", "esqueleto-4"])

    assert builds.subjects == ["s0816", "s1152"]
    after = _manifest(tmp_path)
    assert after["higado-2"] == before["higado-2"]
    assert after["ojos-3"] == before["ojos-3"]


# --- las órdenes equivocadas abortan sin escribir nada --------------------------------------------


def _assert_aborts_untouched(
    tmp_path: Path, builds: Builds, specs: list[str], only: list[str], match: str
) -> None:
    files_before = _files(tmp_path)

    with pytest.raises(SystemExit, match=match):
        _run(tmp_path, specs, only)

    assert builds.subjects == []  # no llegó a construir nada
    assert _files(tmp_path) == files_before  # ni el manifiesto ni ninguna muestra


def test_only_with_a_key_that_the_arguments_do_not_give_aborts(
    tmp_path: Path, builds: Builds
) -> None:
    _published(tmp_path)

    _assert_aborts_untouched(tmp_path, builds, SPECS, ["esqueleto-3"], "esqueleto-3")


def test_only_with_one_good_key_and_one_unknown_aborts(tmp_path: Path, builds: Builds) -> None:
    _published(tmp_path)

    _assert_aborts_untouched(tmp_path, builds, SPECS, ["higado-1", "ojos-9"], "ojos-9")


def test_only_aborts_when_the_order_does_not_match_the_manifest(
    tmp_path: Path, builds: Builds
) -> None:
    _published(tmp_path)
    # Los dos hígados cambiados de sitio: `higado-2` sería s0816, que en el manifiesto es
    # `higado-1`. Conservar «higado-2» dejaría la entrada de s0048 bajo un argumento que pide s0816.
    swapped = ["higado:s0048", "higado:s0816", "ojos:s0289", "esqueleto:s1152"]

    _assert_aborts_untouched(tmp_path, builds, swapped, ["esqueleto-4"], "higado-1")


def test_a_wrong_order_aborts_before_rebuilding_the_sample_asked_for(
    tmp_path: Path, builds: Builds
) -> None:
    _published(tmp_path)
    # La pedida va la primera y la que no casa después: si se rehiciera `higado-1` antes de
    # mirar las demás, quedaría en disco con otros bytes y el manifiesto con la huella antigua.
    wrong = ["higado:s0816", "higado:s0048", "ojos:s1152", "esqueleto:s0289"]

    _assert_aborts_untouched(tmp_path, builds, wrong, ["higado-1"], "ojos-3")


def test_only_aborts_when_a_kept_sample_is_not_in_the_manifest(
    tmp_path: Path, builds: Builds
) -> None:
    _published(tmp_path)
    # Un argumento de más: `ojos-5` no está publicada y no se pide rehacerla.
    _assert_aborts_untouched(
        tmp_path, builds, [*SPECS, "ojos:s0289"], ["esqueleto-4"], "ojos-5"
    )
