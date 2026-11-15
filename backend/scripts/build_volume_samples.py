"""Prepara los TAC de ejemplo del visor 3D a partir de sujetos ya segmentados.

    .venv/Scripts/python.exe scripts/build_volume_samples.py higado:s0048 ojos:s0289

Requiere haber bajado los sujetos (`fetch_ct_samples.py`) y haberlos segmentado con TotalSegmentator
en `data/ct-sources/<sujeto>/seg-<preset>/<tarea>/` (lo hace `app/volumes/segment.run`). Guarda en
`app/data/volume_samples/<clave>/` el TAC recortado a la región a 2 mm y los ficheros del visor,
con un manifiesto que da el dataset, la licencia y la huella SHA-256 de cada fichero.

La posición de cada argumento da el número de la clave (`esqueleto:s1152` en cuarto lugar es
`esqueleto-4`), así que se pasan siempre todos, en el orden del manifiesto. Para rehacer una sola
muestra sin mover la huella de las demás:

    .venv/Scripts/python.exe scripts/build_volume_samples.py higado:s0816 higado:s0048 \
        ojos:s0289 esqueleto:s1152 --only esqueleto-4 [--sources <otra carpeta ct-sources>]

Por qué existe `--only`: una huella publicada no se cambia sin motivo. Al regenerar `esqueleto-4`
el 2026-10-08 (sus nombres de hueso eran anteriores a la concordancia de género), las otras tres
salían con otros bytes en `ct.nii.gz` y `etiquetas.nii.gz` sin que nadie lo hubiera pedido; con
`--only` sus entradas del manifiesto se conservan tal cual y sus ficheros no se tocan.
`--sources` es para una copia de trabajo sin `data/` (un worktree): los TAC están fuera de git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.volumes import assets  # noqa: E402

SOURCES = ROOT / "data" / "ct-sources"
OUT = ROOT / "backend" / "app" / "data" / "volume_samples"
DATASET = {
    "name": "TotalSegmentator dataset v2.0.1 (1228 TAC con 117 estructuras segmentadas)",
    "citation": "Wasserthal J. et al. TotalSegmentator: Robust Segmentation of 104 Anatomic "
                "Structures in CT Images. Radiol Artif Intell 2023;5(5):e230024. "
                "Datos: Zenodo, doi:10.5281/zenodo.10047292",
    "doi": "10.5281/zenodo.10047292",
    "license": "CC BY 4.0",
    "url": "https://doi.org/10.5281/zenodo.10047292",
}
NAMES = {
    "higado": "Abdomen: hígado",
    "ojos": "Cabeza: órbitas",
    "esqueleto": "Cuerpo entero: esqueleto",
}


def main(specs: list[str], only: list[str] | None = None, sources: Path | None = None) -> None:
    import nibabel as nib

    sources = SOURCES if sources is None else sources
    OUT.mkdir(parents=True, exist_ok=True)
    keys = [f"{spec.split(':')[0]}-{number}" for number, spec in enumerate(specs, start=1)]
    kept: dict[str, dict[str, object]] = {}
    if only:
        unknown = sorted(set(only) - set(keys))
        if unknown:
            raise SystemExit(f"--only pide {unknown}, que no sale de los argumentos: {keys}")
        published = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))["samples"]
        kept = {entry["key"]: entry for entry in published}
        # Cada entrada que se conserva tiene que ser la misma muestra, y se mira ANTES de rehacer
        # nada: comprobándolo sobre la marcha, una orden mal ordenada abortaba con la muestra
        # pedida ya reescrita en disco y el manifiesto todavía con su huella antigua.
        for key, spec in zip(keys, specs, strict=True):
            subject = spec.split(":")[1]
            if key not in only and kept.get(key, {}).get("sujeto_dataset") != subject:
                raise SystemExit(
                    f"{key} ({subject}) no está así en el manifiesto: sin ella no "
                    "se puede conservar; revisa el orden de los argumentos"
                )
    samples: list[dict[str, object]] = []
    for number, spec in enumerate(specs, start=1):
        preset_key, subject = spec.split(":")
        preset = assets.PRESETS[preset_key]
        if only and keys[number - 1] not in only:
            # Se conserva la entrada publicada, sin rehacer nada.
            samples.append(kept[keys[number - 1]])
            print(f"{keys[number - 1]}: {subject} · se conserva")
            continue
        source = sources / subject
        seg_dir = source / f"seg-{preset.key}"
        masks = {p.name.removesuffix(".nii.gz"): p for p in seg_dir.rglob("*.nii.gz")}
        reference = assets.resample(nib.load(source / "ct.nii.gz"), preset.voxel_mm)
        files, summary = assets.build(reference, assets.mask_loader(reference, masks), preset)
        summary["segmentador"] = "TotalSegmentator (precalculado)"
        key = f"{preset.key}-{number}"
        target = OUT / key
        target.mkdir(exist_ok=True)
        ct = files["ct.nii.gz"]
        archive = assets.zip_files(files, json.dumps(summary, ensure_ascii=False).encode("utf-8"))
        (target / "ct.nii.gz").write_bytes(ct)
        (target / "visor.zip").write_bytes(archive)
        meta = json.loads((source / "manifest.json").read_text(encoding="utf-8"))["meta"]
        same_preset = sum(item["preset"] == preset.key for item in samples) + 1
        samples.append({
            "key": key,
            "nombre": f"{NAMES.get(preset.key, preset.display)} {same_preset}",
            "preset": preset.key,
            "modalidad": "CT",
            "sujeto_dataset": subject,
            "estudio_dataset": meta.get("study_type"),
            "dataset": DATASET,
            "sha256": {
                "ct.nii.gz": hashlib.sha256(ct).hexdigest(),
                "visor.zip": hashlib.sha256(archive).hexdigest(),
            },
            "lesiones": len(summary["lesiones"]),
        })
        print(f"{key}: {subject} · {len(files)} ficheros · {len(summary['lesiones'])} lesiones "
              f"· {(len(ct) + len(archive)) / 1e6:.1f} MB")
    (OUT / "manifest.json").write_text(
        json.dumps({"samples": samples}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("specs", nargs="+", metavar="preset:sujeto")
    parser.add_argument("--only", action="append", metavar="clave",
                        help="rehacer solo esta muestra y conservar las demás (repetible)")
    parser.add_argument("--sources", type=Path, metavar="carpeta",
                        help=f"carpeta con los sujetos segmentados (por defecto, {SOURCES})")
    arguments = parser.parse_args()
    main(arguments.specs, arguments.only, arguments.sources)
