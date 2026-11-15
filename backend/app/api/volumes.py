"""Rutas del visor 3D: subir un volumen, segmentarlo en local y servir lo que abre el visor.

Por qué es un módulo aparte: un volumen TAC/RM no es una ecografía ni una lectura. No se mide con
calibres ni entra en el análisis; se ve en tres planos y en 3D, y su segmentación automática es
una ayuda sin validar. Comparte con la imagen el almacén de binarios firmados, la lectura por
trozos con tope y el cupo de importaciones, que se reutilizan de `routes.py`.

La segmentación tarda minutos: se lanza en segundo plano y se consulta su estado.
"""

from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import logging
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.api.mission import latest_identity
from app.api.routes import (
    CONSOLE_IDENTITY,
    SettingsDep,
    StoreDep,
    _import_slots,
    _read_capped,
    _recorded_or_422,
    identity_for,
)
from app.core.ledger import sha256_hex
from app.core.storage import ObservationStore, TamperedRecordError
from app.volumes import (
    assets,
    contrast_phase,
    geometry,
    polaris_web,
    privacy,
    segment,
    spine,
)
from app.volumes.samples import SAMPLE_SOURCE, SampleFileChanged, catalog, load_sample

volumes_router = APIRouter(prefix="/volumes")
log = logging.getLogger(__name__)

MAX_VOLUME_BYTES = 256 * 1024 * 1024
SEGMENTER_SIGNER = "segmentation-local"
UNAVAILABLE_NOTE = (
    "Segmentación automática no disponible: no hay TotalSegmentator instalado en esta máquina. "
    "Los volúmenes se guardan y se ven igual."
)
Modality = Literal["CT", "MR"]

# Trabajos de segmentación en curso, en memoria: un reinicio los pierde, y se repiten.
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


@volumes_router.get("/segmenter")
def segmenter_status(settings: SettingsDep) -> dict[str, Any]:
    """Si hay segmentador local y en qué estado. Sin él, la función se declara ausente."""
    executable = segment.find(settings.totalseg_cmd)
    if executable is None:
        return {"available": False, "note": UNAVAILABLE_NOTE, "presets": _presets()}
    if not segment.telemetry_off(executable):
        return {
            "available": False,
            "note": "TotalSegmentator tiene la telemetría encendida: se apaga antes de segmentar.",
            "presets": _presets(),
        }
    return {"available": True, "note": None, "presets": _presets()}


def _presets() -> list[dict[str, Any]]:
    return [
        {"key": p.key, "nombre": p.display, "estructuras": [s.display for s in p.structures],
         "lesiones": p.lesion_mask is not None}
        for p in assets.PRESETS.values()
    ]


class _Refused(Exception):
    """La puerta no deja entrar el volumen. `body` es el 422: el motivo y si se ofrece limpiar."""

    def __init__(self, detail: str, *, cleanable: bool) -> None:
        super().__init__(detail)
        self.body = {
            "detail": detail,
            "cleanable": cleanable,
            "clean_offer": privacy.CLEAN_OFFER if cleanable else None,
            "clean_label": privacy.CLEAN_LABEL if cleanable else None,
        }


# `response_model=None`: el rechazo sale como respuesta propia, con más campos que `detail`.
@volumes_router.post("", status_code=201, response_model=None)
async def upload_volume(
    request: Request,
    store: StoreDep,
    recorded_by: Annotated[str, Query(min_length=1, max_length=64)],
    modality: Modality = "CT",
    subject: Annotated[str, Query(min_length=1)] = "crew-01",
    clean: bool = False,
) -> dict[str, Any] | JSONResponse:
    """Sube un volumen NIfTI (.nii o .nii.gz). Se firma entero en el ledger.

    Antes de guardar se mira la cabecera (`volumes/privacy.py`): con texto, extensiones o la
    identidad declarada del tripulante dentro, no entra y se dice qué campo. El rechazo dice
    además si limpiar la cabecera aquí lo dejaría entrar (`cleanable`). Con `clean=true` —que
    solo manda el operador, reenviando el mismo fichero— se guarda y se firma el volumen limpio,
    y el asiento declara que se limpió, qué campos y las dos huellas. Sin `clean`, nada cambia.
    """
    raw = await _read_capped(request, MAX_VOLUME_BYTES)
    async with _import_slots:
        try:
            return await run_in_threadpool(
                _upload, store, raw, modality, subject, recorded_by, clean
            )
        except _Refused as refused:
            return JSONResponse(status_code=422, content=refused.body)


def _nifti(raw: bytes) -> Any:
    import nibabel as nib

    data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
    try:
        return nib.Nifti1Image.from_bytes(data)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo es un volumen ilegible
        raise HTTPException(status_code=422, detail=f"no es un NIfTI legible: {exc}") from exc


def _upload(
    store: ObservationStore, raw: bytes, modality: str, subject: str, recorded_by: str,
    clean: bool = False,
) -> dict[str, Any]:
    image = _nifti(raw)
    if len(image.shape) != 3:
        raise HTTPException(status_code=422, detail="el volumen tiene que ser 3D")
    cleaned = _refuse_personal_data(store, raw, subject, clean)
    if cleaned is None:
        payload = _study_payload(image, raw, modality, subject, CONSOLE_IDENTITY, recorded_by)
        entry = store.record_volume_study(payload, raw, identity_for(CONSOLE_IDENTITY))
        return {"ledger_index": entry.index, "shape": payload["shape"]}
    # Se guarda y se firma el limpio; del recibido queda su huella, no sus bytes.
    kept = cleaned.data
    payload = _study_payload(_nifti(kept), kept, modality, subject, CONSOLE_IDENTITY, recorded_by)
    payload["cleaned"] = {
        "fields": list(cleaned.fields),
        "received_sha256": sha256_hex(raw),
        "received_size_bytes": len(raw),
        "note": privacy.CLEANED_NOTE,
    }
    entry = store.record_volume_study(payload, kept, identity_for(CONSOLE_IDENTITY))
    return {
        "ledger_index": entry.index, "shape": payload["shape"], "sha256": payload["sha256"],
        "cleaned": payload["cleaned"],
    }


def _refuse_personal_data(
    store: ObservationStore, raw: bytes, subject: str, clean: bool
) -> privacy.Cleaned | None:
    """Fallo cerrado: con datos personales en la cabecera, o sin poder comprobarlo, no se guarda.

    El motivo nombra el campo y nunca el dato. Devuelve `None` si el volumen entra tal como
    llegó. Si la puerta lo rechaza y el operador NO pidió limpiar, se rechaza como siempre y se
    dice si limpiar serviría (se prueba en seco: nada se guarda). Solo si lo pidió se devuelve el
    volumen limpio, que `privacy.clean` ya ha vuelto a pasar por la misma puerta.
    """
    declared = latest_identity(store, subject)
    try:
        try:
            privacy.ensure_clean(raw, declared)
        except privacy.PersonalDataFound as found:
            if clean:
                return _cleaned(raw, declared)
            raise _Refused(
                f"El volumen puede llevar datos personales: {found}. {privacy.HOW_TO_CLEAN}",
                cleanable=_would_enter_clean(raw, declared),
            ) from None
    except privacy.CheckUnavailable as failed:
        raise HTTPException(
            status_code=503, detail=f"El volumen no se ha guardado: {failed}."
        ) from None
    return None


def _cleaned(raw: bytes, declared: Any) -> privacy.Cleaned:
    try:
        return privacy.clean(raw, declared)
    except privacy.PersonalDataFound as still:
        raise _Refused(
            f"{privacy.STILL_FOUND}: {still}. {privacy.HOW_TO_CLEAN}", cleanable=False
        ) from None


def _would_enter_clean(raw: bytes, declared: Any) -> bool:
    """Si limpiar aquí lo dejaría entrar. Es la limpieza de verdad, tirada: no se guarda nada."""
    try:
        privacy.clean(raw, declared)
    except (privacy.PersonalDataFound, privacy.CheckUnavailable):
        return False
    return True


def _study_payload(
    image: Any, raw: bytes, modality: str, subject: str, source: str, recorded_by: str
) -> dict[str, Any]:
    affine = image.affine
    return {
        "subject": subject,
        "modality": modality,
        "media_type": "application/x-nifti",
        "sha256": sha256_hex(raw),
        "size_bytes": len(raw),
        "shape": [int(n) for n in image.shape],
        "voxel_mm": [round(float(v), 3) for v in geometry.spacing(affine)],
        "source": source,
        "recorded_by": recorded_by,
    }


@volumes_router.get("")
def list_volumes(
    store: StoreDep, subject: Annotated[str, Query(min_length=1)] = "crew-01"
) -> list[dict[str, Any]]:
    """Estudios volumétricos vigentes, cada uno con sus segmentaciones y con la fase de contraste
    que una persona haya declarado de él (`volumes/contrast_phase.py`)."""
    studies = store.volume_studies(subject)
    declared = store.contrast_phase_declarations(subject)
    for study in studies:
        phase = contrast_phase.describe(declared, study, CONSOLE_IDENTITY)
        study["contrast_phase"] = phase
        study["segmentations"] = [
            _with_phase(_with_density(store, _with_spine_review(store, segmentation)), phase)
            for segmentation in store.volume_segmentations(int(study["ledger_index"]))
        ]
    return studies


def _with_phase(segmentation: dict[str, Any], phase: dict[str, Any]) -> dict[str, Any]:
    """La fase declarada del estudio, junto a la densidad. Se pone al servir: la densidad
    firmada al segmentar lleva la fase vacía, y eso no se reescribe."""
    return contrast_phase.annotate(
        segmentation, phase["current"], geometry.DENSITY_KEY, geometry.PHASE_UNDECLARED
    )


def _study_phase(
    store: ObservationStore, study: dict[str, Any], study_index: int
) -> dict[str, Any]:
    """Lo que consta de la fase de un estudio leído con `volume_blob`, que no trae su índice."""
    return contrast_phase.describe(
        store.contrast_phase_declarations(str(study.get("subject"))),
        {**study, "ledger_index": study_index}, CONSOLE_IDENTITY,
    )


Operator = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ContrastPhaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str
    # Cuándo lo declara quien lo declara; sin él, el instante en que llega.
    at: dt.datetime | None = None
    note: Note = ""
    declared_by: Operator

    @field_validator("phase")
    @classmethod
    def _in_the_vocabulary(cls, value: str) -> str:
        contrast_phase.check(value)
        return value

    @field_validator("at")
    @classmethod
    def _aware(cls, value: dt.datetime | None) -> dt.datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("el instante debe llevar zona horaria")
        return value


@volumes_router.get("/contrast-phases")
def contrast_phases() -> dict[str, Any]:
    """El vocabulario cerrado de fases de contraste y los textos que lo acompañan."""
    return contrast_phase.vocabulary()


@volumes_router.post("/{ledger_index}/contrast-phase", status_code=201)
def declare_contrast_phase(
    store: StoreDep, ledger_index: int, payload: ContrastPhaseIn
) -> dict[str, Any]:
    """Firma la fase de contraste que una persona declara de un TAC. Un asiento por declaración;
    el del estudio no se toca. 404 si el estudio no existe; 422 si no es un TAC, si la fase no
    es del vocabulario o si falta quién lo declara.

    EMMA no propone la fase ni la comprueba con la imagen, y declararla no cambia ninguna
    cifra, ningún estado de evolución, ningún nivel ni ninguna alerta.
    """
    try:
        entry = _recorded_or_422(
            lambda: store.record_contrast_phase(
                ledger_index, payload.phase, payload.at or dt.datetime.now(dt.UTC),
                payload.note, payload.declared_by, identity_for(CONSOLE_IDENTITY),
            )
        )[0]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    return {"ledger_index": entry.index}


# Control de la cadena vertebral de las segmentaciones guardadas SIN él, por las huellas firmadas
# de su zip y de su estudio: el control solo depende de esos bytes. En memoria; un reinicio lo
# pierde y se vuelve a calcular.
_spine_reviews: dict[tuple[str, str], dict[str, Any]] = {}


def _with_spine_review(store: ObservationStore, segmentation: dict[str, Any]) -> dict[str, Any]:
    """La segmentación del esqueleto, con su control de la cadena vertebral (`volumes/spine.py`).

    Las nuevas lo llevan firmado en su resumen (`assets.build`), y también el ejemplo
    `esqueleto-4` desde que se regeneró el 2026-10-08. Las guardadas antes no: se calcula al
    servir, desde su mapa de etiquetas firmado (el binario se comprueba contra su huella al
    leerlo), y viaja solo en la respuesta. No se reescribe nada en el ledger: añadirlo allí
    cambiaría bytes firmados o exigiría otro asiento para decir lo mismo.

    Es descriptivo y no bloquea: si el binario no se puede leer (o ya no es el firmado), el
    listado sigue y el bloque dice que el control no se pudo hacer y por qué. El visor sigue
    negándose a servir ese binario, como siempre.
    """
    if segmentation.get("preset") != spine.PRESET or spine.KEY in segmentation:
        return segmentation
    preset = assets.PRESETS[spine.PRESET]
    key = (str(segmentation["sha256"]), str(segmentation["study_sha256"]))
    review = _spine_reviews.get(key)
    if review is None:
        try:
            _, archive = store.segmentation_blob(int(segmentation["ledger_index"]))
        except (KeyError, TamperedRecordError) as exc:
            return {**segmentation, spine.KEY: spine.unreviewed(preset, str(exc.args[0]))}
        try:
            _, volume = store.volume_blob(int(segmentation["study_index"]))
        except (KeyError, TamperedRecordError):
            volume = None  # sin el volumen del estudio no se miden los extremos; lo demás sí
        review = spine.review_stored(archive, volume, preset)
        if review["revisada"]:
            _spine_reviews[key] = review
    return {**segmentation, spine.KEY: review}


def _with_density(store: ObservationStore, segmentation: dict[str, Any]) -> dict[str, Any]:
    """La segmentación con la densidad (HU) de sus lesiones candidatas; las guardadas sin ella,
    calculada al servir desde su zip firmado (`assets.with_density`). Descriptiva: no bloquea."""
    return assets.with_density(
        segmentation, lambda: store.segmentation_blob(int(segmentation["ledger_index"]))[1]
    )


@volumes_router.post("/{ledger_index}/segment", status_code=202)
def request_segmentation(
    store: StoreDep, settings: SettingsDep, ledger_index: int, preset: str = "higado"
) -> dict[str, Any]:
    """Lanza la segmentación en segundo plano. Devuelve el trabajo para consultar su estado."""
    if preset not in assets.PRESETS:
        raise HTTPException(status_code=422, detail=f"preset desconocido: {preset!r}")
    executable = segment.find(settings.totalseg_cmd)
    if executable is None:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_NOTE)
    try:
        store.volume_blob(ledger_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    job = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job] = {"state": "running", "study_index": ledger_index, "preset": preset}
    threading.Thread(
        target=_segment_job,
        args=(store, executable, ledger_index, assets.PRESETS[preset], job),
        daemon=True,
    ).start()
    return {"job": job, "state": "running"}


@volumes_router.get("/jobs/{job}")
def job_status(job: str) -> dict[str, Any]:
    with _jobs_lock:
        if job not in _jobs:
            raise HTTPException(status_code=404, detail="trabajo desconocido")
        return dict(_jobs[job])


def _segment_job(
    store: ObservationStore, executable: str, study_index: int, preset: assets.Preset, job: str
) -> None:
    try:
        study, raw = store.volume_blob(study_index)
        with tempfile.TemporaryDirectory(prefix="emma_seg_") as folder:
            ct_path = Path(folder) / "ct.nii.gz"
            ct_path.write_bytes(raw if raw[:2] == b"\x1f\x8b" else gzip.compress(raw))
            masks = segment.run(executable, ct_path, Path(folder) / "seg", preset)
            index = _record_segmentation(
                store, study, study_index, _nifti(raw), masks, preset, "TotalSegmentator"
            )
        result: dict[str, Any] = {"state": "done", "ledger_index": index}
    except (segment.SegmenterUnavailable, ValueError, KeyError) as exc:
        result = {"state": "failed", "error": str(exc)}
    except Exception as exc:
        # Cualquier otro fallo también cierra el trabajo. Si no, el hilo muere, el trabajo se
        # queda "running" para siempre y la interfaz espera sin fin (pasó en la app instalada:
        # el congelado había dejado fuera scipy y nadie se enteraba).
        log.exception("segmentación %s fallida", job)
        result = {"state": "failed", "error": f"Fallo inesperado al segmentar: {exc}"}
    with _jobs_lock:
        _jobs[job].update(result)


def _record_segmentation(
    store: ObservationStore, study: dict[str, Any], study_index: int, image: Any,
    masks: dict[str, Any], preset: assets.Preset, segmenter: str,
) -> int:
    reference = assets.resample(image, preset.voxel_mm)
    files, summary = assets.build(
        reference, assets.mask_loader(reference, masks), preset, str(study["modality"])
    )
    summary["segmentador"] = segmenter
    archive = assets.zip_files(files, json.dumps(summary, ensure_ascii=False).encode("utf-8"))
    payload = {
        **summary,
        "study_index": study_index,
        "study_sha256": study["sha256"],
        "sha256": sha256_hex(archive),
        "size_bytes": len(archive),
        "files": sorted(files),
    }
    entry = store.record_volume_segmentation(payload, archive, identity_for(SEGMENTER_SIGNER))
    return entry.index


@volumes_router.get("/segmentations/{ledger_index}/files/{name}")
def segmentation_file(store: StoreDep, ledger_index: int, name: str) -> Response:
    """Un fichero del visor, sacado del binario firmado recién comprobado."""
    try:
        payload, archive = store.segmentation_blob(ledger_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    if name not in payload.get("files", []):
        raise HTTPException(status_code=404, detail=f"no hay {name!r} en esta segmentación")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        content = bundle.read(name)
    media = "application/octet-stream"
    return Response(content=content, media_type=media, headers={"Cache-Control": "no-store"})


@volumes_router.get("/segmentations/{ledger_index}/polaris/{path:path}")
def polaris_viewer(store: StoreDep, ledger_index: int, path: str) -> Response:
    """El visor web de Polaris (copiado tal cual) y, en sus rutas relativas, esta segmentación.

    Todo sale del binario firmado recién comprobado, como en `segmentation_file`.
    """
    try:
        payload, archive = store.segmentation_blob(ledger_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    headers = {"Cache-Control": "no-store"}
    page = path or "index.html"
    if page in polaris_web.STATIC:
        source = polaris_web.WEB_DIR / page
        if not source.is_file():
            raise HTTPException(status_code=503, detail="falta compilar el visor de Polaris")
        return Response(source.read_bytes(), media_type=polaris_web.STATIC[page], headers=headers)
    if page == "indice.json":
        body: Any = polaris_web.index()
    elif page == f"{polaris_web.FOLDER}/estudio.json":
        body = polaris_web.study(payload, ledger_index)
    elif page.startswith(f"{polaris_web.FOLDER}/"):
        name = page.removeprefix(f"{polaris_web.FOLDER}/")
        if name not in payload.get("files", []):
            raise HTTPException(status_code=404, detail=f"no hay {name!r} en esta segmentación")
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            content = bundle.read(name)
        return Response(content, media_type="application/octet-stream", headers=headers)
    else:
        # comparacion.json, referencia.json, pet.json, marcas.json: EMMA no los tiene y el visor
        # de Polaris ya trata su ausencia.
        raise HTTPException(status_code=404, detail=f"{page!r} no existe")
    return Response(
        json.dumps(body, ensure_ascii=False), media_type="application/json", headers=headers
    )


DIFFERENT_PEOPLE_NOTE = (
    "Los dos estudios son TAC de ejemplo de pacientes distintos de un dataset público: este "
    "emparejado enseña cómo funciona la comparación, no la evolución de una persona."
)


@volumes_router.get("/compare")
def compare(store: StoreDep, before: int, after: int) -> dict[str, Any]:
    """Lesiones de dos segmentaciones del mismo preset: emparejadas (Polaris `empareja`) y con el
    estado de cada una entre los dos estudios (Polaris `evolucion`).

    Sigue siendo segmentación automática sin validar: no es una lectura, no entra en el análisis
    ni en una alerta, y el emparejado bueno sale del informe radiológico.
    """
    try:
        a, archive_a = store.segmentation_blob(before)
        b, archive_b = store.segmentation_blob(after)
        study_a, _ = store.volume_blob(int(a["study_index"]))
        study_b = study_a if a["study_index"] == b["study_index"] else (
            store.volume_blob(int(b["study_index"]))[0]
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    if a.get("preset") != b.get("preset") or a.get("segmentador") != b.get("segmentador"):
        # Polaris aborta si no salen del mismo modelo y receta: la "evolución" mediría el cambio
        # de modelo.
        raise HTTPException(
            status_code=409, detail="las dos segmentaciones no salen del mismo preset y segmentador"
        )
    if study_a.get("subject") != study_b.get("subject"):
        # Emparejar las lesiones de dos tripulantes no mide la evolución de ninguno.
        raise HTTPException(
            status_code=409, detail="las dos segmentaciones no son del mismo tripulante"
        )
    pairs = geometry.pair(a, b)
    # Las dos densidades, una junto a otra y sin veredicto: la fase de contraste puede no ser la
    # misma, y el estado lo decide Polaris solo con el diámetro (por eso van después de emparejar).
    a = assets.with_density(a, lambda: archive_a)
    b = assets.with_density(b, lambda: archive_b)
    # La fase declarada de cada estudio, al lado y después de todo lo anterior: no bloquea la
    # comparación, no resta las densidades y no la lee quien decide el estado.
    phase_a = _study_phase(store, study_a, int(a["study_index"]))
    phase_b = _study_phase(store, study_b, int(b["study_index"]))
    a, b = _with_phase(a, phase_a), _with_phase(b, phase_b)
    lesions_after: list[dict[str, Any]] = list(b.get("lesiones", []))
    states = geometry.evolution(pairs, lesions_after)
    previous = {int(item["id"]): item for item in a.get("lesiones", [])}
    rows = []
    for lesion in lesions_after:
        state = states[int(lesion["id"])]
        prior = previous.get(state["id_previo"]) if state["id_previo"] is not None else None
        rows.append({
            "id": lesion["id"],
            "estado": lesion.get("estado"),
            "region": lesion.get("region"),
            "pequena": lesion.get("pequena"),
            "diametro_mm": lesion["diametro_mm"],
            "volumen_ml": lesion["volumen_ml"],
            "densidad": lesion.get("densidad"),
            "previa": None if prior is None else {
                "id": prior["id"], "diametro_mm": prior["diametro_mm"],
                "volumen_ml": prior["volumen_ml"], "densidad": prior.get("densidad"),
            },
            "evolucion": state,
        })
    # Como en la ficha de Polaris: las del estudio previo que no se reencuentran se listan con su
    # medida y sin estado. Polaris no les pone texto y EMMA no lo inventa.
    not_found_again = [
        {"id_previo": pair["antes"], "region": previous[pair["antes"]].get("region"),
         "diametro_mm": previous[pair["antes"]]["diametro_mm"],
         "volumen_ml": previous[pair["antes"]]["volumen_ml"],
         "densidad": previous[pair["antes"]].get("densidad")}
        for pair in pairs if pair.get("despues") is None
    ]
    samples = {study_a.get("sample"), study_b.get("sample")}
    return {
        "antes": before,
        "despues": after,
        "estado": assets.UNVALIDATED,
        "segmentador": b.get("segmentador"),
        "criterio": geometry.EVOLUTION_CRITERION,
        "aviso": DIFFERENT_PEOPLE_NOTE if len(samples) == 2 and None not in samples else None,
        "densidad": {"antes": a.get("densidad"), "despues": b.get("densidad")},
        "fase_contraste": contrast_phase.compare(phase_a, phase_b),
        "pares": pairs,
        "lesiones": rows,
        "no_reencontradas": not_found_again,
    }


@volumes_router.get("/samples")
def list_samples() -> list[dict[str, Any]]:
    """TAC reales de ejemplo, del dataset abierto de TotalSegmentator, ya segmentados."""
    return [sample.as_public() for sample in catalog()]


@volumes_router.post("/samples/{key}", status_code=201)
def create_sample(
    store: StoreDep, key: str, subject: Annotated[str, Query(min_length=1)] = "crew-01"
) -> dict[str, Any]:
    """Registra un TAC de ejemplo con su segmentación precalculada. Firmado como simulado: es un
    paciente de un dataset, no un tripulante."""
    try:
        sample, ct_raw, archive = load_sample(key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except SampleFileChanged as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    image = _nifti(ct_raw)
    study_payload = {
        **_study_payload(image, ct_raw, sample.modality, subject, SAMPLE_SOURCE, "demo"),
        "dataset": sample.dataset,
        "sample": sample.key,
    }
    study = store.record_volume_study(study_payload, ct_raw, identity_for("simulator"))
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        summary = json.loads(bundle.read("estudio.json"))
        files = sorted(name for name in bundle.namelist() if name != "estudio.json")
    payload = {
        **summary,
        "study_index": study.index,
        "study_sha256": study_payload["sha256"],
        "sha256": sha256_hex(archive),
        "size_bytes": len(archive),
        "files": files,
    }
    segmentation = store.record_volume_segmentation(
        payload, archive, identity_for(SEGMENTER_SIGNER)
    )
    return {"ledger_index": study.index, "segmentation": segmentation.index}
