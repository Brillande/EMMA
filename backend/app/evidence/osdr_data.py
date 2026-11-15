"""La ficha de un estudio de OSDR, leída en la API de OSDR y comparada con lo que EMMA dice de él.

Por qué existe: EMMA cita diez estudios de OSDR (OSD-288, OSD-569, OSD-343, los reposos en cama…)
y todo lo que afirma de ellos —título, fecha, si son personas o ratones, cuántas muestras— está
copiado a mano en su ficha (`data/evidence_refs.json`), con la fecha en que alguien lo leyó. Una
ficha copiada no avisa cuando la fuente cambia ni cuando se copió mal: el «n = 12» de OSD-288
estuvo meses en la ficha contando ratones lanzados en vez de muestras, y solo se vio releyendo la
página. Aquí la API de datos de OSDR (Biological Data API v2, pública y sin clave) dice lo suyo
—título, organismo, misión, tipo de ensayo, muestras y fecha de publicación— y se compara campo a
campo con la ficha. Si discrepan, se declara la discrepancia con los dos valores; **no se corrige
la ficha**: quién tiene razón lo decide una persona con la fuente delante.

Qué compara y qué no:
  * **Título** y **fecha de publicación** (la ficha guarda la de OSDR, «study public release
    date», en segundos desde 1970 en la API).
  * **Población**: el organismo de la API (`Mus musculus`, `Homo sapiens`) contra la población de
    la ficha. El organismo es el de las muestras depositadas; una ficha «humano y animal» (OSD-343:
    el estudio analiza astronautas, pero los ficheros abiertos son de ratón) es *compatible* con un
    organismo animal, no una discrepancia. Un organismo que EMMA no sabe clasificar no se compara.
  * **Muestras**: solo donde EMMA afirma una cifra (`CLAIMED_SAMPLES`). La API cuenta muestras,
    no sujetos: OSD-51 tiene 340 muestras de 24 mujeres, y comparar 340 con «24» sería falso.
  * La misión y el tipo de ensayo se enseñan tal cual los da la API, sin comparar: la ficha no
    los guarda como campo. Las fechas de misión van como texto, porque la API mezcla formatos
    («7/18/16», «14-Aug-2017») y convertirlas sería adivinar el orden del día y el mes. Una fecha
    de misión revisada en fuente primaria lleva su nota (`MISSION_NOTES`): la de fin de OSD-288
    («9/26/16») no es el regreso de los ratones, que amerizaron el 26 de agosto de 2016.

La mina de siempre: OSD-288 es RNA-Seq de bazo de 12 ratones, no datos de astronautas. La API lo
dice con su organismo, y la salida lo escribe con esas palabras (`scope`).

Es evidencia, no medida: nada de aquí entra en el ledger, en el análisis, en el riesgo ni en una
alerta. Sale a la red solo por `core/egress.py` (propósito `osdr-data`); sin red sirve la última
lectura con su edad, y sin ella dice «no disponible».
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import httpx

from app.core import egress, i18n
from app.core.cache import CachedPayload, FileCache, OfflineDataUnavailable
from app.core.config import Settings, get_settings
from app.evidence import registry
from app.evidence.registry import EvidenceRef

PURPOSE = "osdr-data"
BASE_URL = "https://visualization.osdr.nasa.gov/biodata/api/v2"
SOURCE = "NASA OSDR · Biological Data API v2"
# Vigencia de una lectura (parámetro de diseño, no de la fuente): la ficha de un estudio publicado
# casi no cambia, y releerla en cada visita no aporta nada. Con red, pasada una semana se relee.
FRESH_FOR = dt.timedelta(days=7)
# Peticiones a la vez al leer todas las fichas: diez estudios son veinte peticiones.
MAX_WORKERS = 4

# La ficha de un estudio de OSDR en el registro: su página en el repositorio.
_STUDY_URL = re.compile(r"^https://osdr\.nasa\.gov/bio/repo/data/studies/(OSD-\d+)$")

# Organismo de la API -> población del registro. Solo los que aparecen en los estudios que EMMA
# cita; otro organismo no se clasifica (y su población no se compara), no se adivina.
ORGANISMS: dict[str, str] = {
    "Homo sapiens": "human",
    "Mus musculus": "animal",
}

# Las cifras de muestras que EMMA afirma, y dónde las afirma. La API cuenta muestras, no sujetos:
# solo se compara donde EMMA dice «muestras». La prueba comprueba que la frase sigue en la ficha.
CLAIMED_SAMPLES: dict[str, tuple[int, str]] = {
    "osd-288": (9, "publica 9 muestras de bazo"),
}

# Veredictos de cada comparación, con la palabra que se enseña (la interfaz no la redacta).
VERDICTS: dict[str, str] = {
    "match": "coincide",
    "compatible": "compatible",
    "mismatch": "discrepa",
    "not_comparable": "no comparable",
}
# El inglés, en tablas hermanas con las mismas claves: las claves no se traducen nunca.
VERDICTS_EN: dict[str, str] = {
    "match": "matches",
    "compatible": "compatible",
    "mismatch": "differs",
    "not_comparable": "not comparable",
}
STATUS: dict[str, str] = {
    "agrees": "la ficha de EMMA coincide con OSDR",
    "disagrees": "la ficha de EMMA discrepa de OSDR: se declara, no se corrige",
    "unavailable": "OSDR no disponible: no se ha podido comprobar la ficha",
}
STATUS_EN: dict[str, str] = {
    "agrees": "EMMA's reference card matches OSDR",
    "disagrees": "EMMA's reference card differs from OSDR: it is declared, not corrected",
    "unavailable": "OSDR not available: the reference card could not be checked",
}
UNAVAILABLE = "no disponible"

# Fechas de misión de la API que se revisaron en fuente primaria y no dicen lo que parecen. La nota
# sale junto a la misión solo mientras la API dé el mismo valor que al revisarla: si OSDR lo cambia,
# la fecha se enseña sin nota, porque la explicación ya no es de ese valor.
MISSION_NOTES: dict[str, dict[str, str]] = {
    "OSD-288": {
        "field": "end date",
        "osdr": "9/26/16",
        "checked_on": "2026-11-11",
        "note": (
            "No es el regreso de los ratones. El protocolo del propio estudio, en esta misma API "
            "(«study protocol description»), dice «The capsule splashed down in the Pacific Ocean "
            "offshore from California on 26 August 2016 (GMT)», y NASA lo confirma (nota de prensa "
            "RELEASE16-090, 26 de agosto de 2016: amerizaje a las 11:47 EDT del viernes 26 de "
            "agosto, al final de la novena misión de carga de SpaceX). «9/26/16» es la fecha de "
            "fin del registro de misión «SpaceX-9» de OSDR (endDate «09/26/2016» en "
            "osdr.nasa.gov/geode-py/ws/api/mission/SpaceX-9), común a ocho estudios; OSDR no dice "
            "qué marca y ninguna fuente leída da un hito de la misión ese día. La ficha de EMMA "
            "usa el amerizaje del protocolo."
        ),
    },
}
# Las citas («…») son de las fuentes y van igual en los dos idiomas.
i18n.en(
    MISSION_NOTES["OSD-288"]["note"],
    "It is not the return of the mice. The study's own protocol, in this same API («study "
    "protocol description»), says «The capsule splashed down in the Pacific Ocean offshore from "
    "California on 26 August 2016 (GMT)», and NASA confirms it (press release RELEASE16-090, 26 "
    "August 2016: splashdown at 11:47 EDT on Friday 26 August, at the end of SpaceX's ninth "
    "cargo mission). «9/26/16» is the end date of OSDR's mission record «SpaceX-9» (endDate "
    "«09/26/2016» in osdr.nasa.gov/geode-py/ws/api/mission/SpaceX-9), shared by eight studies; "
    "OSDR does not say what it marks and no source that was read gives a mission milestone on "
    "that day. EMMA's reference card uses the splashdown of the protocol.",
)


class OsdrDataError(ValueError):
    """Una ficha del registro que no es un estudio de OSDR."""


@dataclass(frozen=True, slots=True)
class StudyRecord:
    """Lo que la API de OSDR dice de un estudio. `None` o vacío: la API no lo da."""

    accession: str
    title: str | None
    organisms: tuple[str, ...]
    mission: dict[str, str] | None
    measurement_types: tuple[str, ...]
    technology_types: tuple[str, ...]
    project_type: str | None
    release_date: str | None
    assay_count: int
    sample_count: int
    source_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "accession": self.accession,
            "title": self.title,
            "organisms": list(self.organisms),
            "mission": dict(self.mission) if self.mission is not None else None,
            "measurement_types": list(self.measurement_types),
            "technology_types": list(self.technology_types),
            "project_type": self.project_type,
            "release_date": self.release_date,
            "assay_count": self.assay_count,
            "sample_count": self.sample_count,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StudyRecord:
        return cls(
            accession=raw["accession"],
            title=raw["title"],
            organisms=tuple(raw["organisms"]),
            mission=raw["mission"],
            measurement_types=tuple(raw["measurement_types"]),
            technology_types=tuple(raw["technology_types"]),
            project_type=raw["project_type"],
            release_date=raw["release_date"],
            assay_count=raw["assay_count"],
            sample_count=raw["sample_count"],
            source_url=raw["source_url"],
        )

    @property
    def population(self) -> str | None:
        """La población del registro que corresponde a sus organismos, o None si no se sabe."""
        found = {ORGANISMS.get(name) for name in self.organisms}
        if not found or None in found:
            return None
        if found == {"human", "animal"}:
            return "human_and_animal"
        return found.pop() if len(found) == 1 else None

    @property
    def scope(self) -> str:
        """Sobre quién son las muestras, con palabras que no se pueden leer de más."""
        names = ", ".join(self.organisms) or i18n.tr(
            "sin organismo en la API", "no organism in the API"
        )
        population = self.population
        if population == "animal":
            return i18n.tr(
                (f"Modelo animal ({names}): las muestras no son de astronautas ni de "
                 "ninguna persona."),
                f"Animal model ({names}): the samples are not from astronauts or from any person.",
            )
        if population == "human":
            return i18n.tr(
                f"Personas ({names}): muestras humanas.", f"People ({names}): human samples."
            )
        if population == "human_and_animal":
            return i18n.tr(
                f"Personas y modelo animal ({names}): cada muestra es de su organismo.",
                f"People and animal model ({names}): each sample is from its own organism.",
            )
        return i18n.tr(
            f"Organismo sin clasificar en EMMA ({names}): no se dice sobre quién son.",
            f"Organism not classified in EMMA ({names}): it is not said whom they are from.",
        )


def _strings(value: Any) -> tuple[str, ...]:
    """Un campo que la API da como texto o como lista (un estudio con varios ensayos)."""
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip() and item.strip() not in out:
            out.append(item.strip())
    return tuple(out)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _release_date(value: Any) -> str | None:
    """«study public release date» viene en segundos desde 1970 (UTC). Otra cosa no se adivina."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return dt.datetime.fromtimestamp(value, dt.UTC).date().isoformat()


def _mission(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    mission = {key: text for key in ("name", "start date", "end date")
               if (text := _text(value.get(key))) is not None}
    return mission or None


def _entry(accession: str, body: Any, key: str) -> dict[str, Any]:
    """`{accession: {key: {...}}}`: el accession es la clave del objeto raíz (spike de OSDR)."""
    entry = body.get(accession) if isinstance(body, dict) else None
    inner = entry.get(key) if isinstance(entry, dict) else None
    if not isinstance(inner, dict):
        raise httpx.DecodingError(f"OSDR respondió sin `{accession}.{key}` utilizable")
    return inner


def parse(accession: str, metadata_body: Any, samples_body: Any) -> StudyRecord:
    """Los dos cuerpos de la API en un registro. Una forma que no es la esperada es un fallo de
    lectura (`httpx.DecodingError`: caché vieja o «no disponible»), no un estudio vacío."""
    metadata = _entry(accession, metadata_body, "metadata")
    assays = _entry(accession, samples_body, "assays")
    names: set[str] = set()
    for assay in assays.values():
        samples = assay.get("samples") if isinstance(assay, dict) else None
        if not isinstance(samples, dict):
            raise httpx.DecodingError(f"OSDR respondió un ensayo de {accession} sin muestras")
        names.update(samples)
    return StudyRecord(
        accession=accession,
        title=_text(metadata.get("study title")),
        organisms=_strings(metadata.get("organism")),
        mission=_mission(metadata.get("mission")),
        measurement_types=_strings(metadata.get("study assay measurement type")),
        technology_types=_strings(metadata.get("study assay technology type")),
        project_type=_text(metadata.get("project type")),
        release_date=_release_date(metadata.get("study public release date")),
        assay_count=len(assays),
        sample_count=len(names),
        source_url=f"{BASE_URL}/dataset/{accession}/",
    )


def accession_of(ref: EvidenceRef) -> str | None:
    """El accession de una ficha que es un estudio de OSDR (por su URL), o None."""
    found = _STUDY_URL.match(ref.url or "")
    return found.group(1) if found else None


def osdr_refs() -> list[EvidenceRef]:
    """Las fichas del registro que son estudios de OSDR, en su orden."""
    return [ref for ref in registry.registry().values() if accession_of(ref) is not None]


class OsdrDataClient:
    """Lee la ficha de un estudio en la API de OSDR, con caché y edad declarada."""

    def __init__(self, settings: Settings | None = None, cache: FileCache | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or FileCache(self.settings.cache_dir / "osdr-data")

    def study(self, accession: str) -> CachedPayload:
        """El `StudyRecord` de un accession con su edad, o `OfflineDataUnavailable`."""
        key = f"osdr-data:{accession}"
        cached = self.cache.get(key)
        if cached is not None and (self.settings.offline or not cached.is_stale(FRESH_FOR)):
            return self._rehydrate(cached)
        if self.settings.offline:
            raise OfflineDataUnavailable(
                # Es el motivo que se sirve en el modo nominal (sin red): va en los dos idiomas.
                i18n.tr(
                    f"ficha de {accession} en OSDR no leída aún y el sistema está sin red",
                    f"the record of {accession} in OSDR has not been read yet and the system "
                    "is offline",
                )
            )
        try:
            record = self._fetch(accession)
        except httpx.HTTPError as exc:
            if cached is not None:
                return self._rehydrate(cached)
            raise OfflineDataUnavailable(f"OSDR inaccesible y sin caché: {exc}") from exc
        stored = self.cache.put(key, record.to_dict(), source=SOURCE)
        return CachedPayload(
            data=record, fetched_at=stored.fetched_at, source=stored.source, from_cache=False
        )

    def _rehydrate(self, cached: CachedPayload) -> CachedPayload:
        try:
            record = StudyRecord.from_dict(cached.data)
        except (KeyError, TypeError) as exc:
            raise OfflineDataUnavailable(f"caché de OSDR ilegible: {exc}") from exc
        return CachedPayload(
            data=record, fetched_at=cached.fetched_at, source=cached.source, from_cache=True
        )

    def _get_json(self, url: str) -> Any:
        response = egress.get(self.settings, PURPOSE, url, params={"format": "json"})
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise httpx.DecodingError(f"OSDR respondió sin JSON utilizable: {exc}") from exc

    def _fetch(self, accession: str) -> StudyRecord:
        metadata = self._get_json(f"{BASE_URL}/dataset/{accession}/")
        samples = self._get_json(f"{BASE_URL}/dataset/{accession}/samples/")
        return parse(accession, metadata, samples)


def _check(field: str, label: str, emma: Any, osdr: Any, verdict: str, note: str | None = None,
           ) -> dict[str, Any]:
    return {
        "field": field,
        "label": label,
        "emma": emma,
        "osdr": osdr,
        "verdict": verdict,
        "verdict_display": i18n.tr(VERDICTS[verdict], VERDICTS_EN[verdict]),
        "note": note,
    }


def _equal(field: str, label: str, emma: Any, osdr: Any) -> dict[str, Any]:
    if emma is None or osdr is None:
        note = (
            i18n.tr("la ficha no lo da", "the reference card does not give it") if emma is None
            else i18n.tr("OSDR no lo da", "OSDR does not give it")
        )
        return _check(field, label, emma, osdr, "not_comparable", note)
    return _check(field, label, emma, osdr, "match" if emma == osdr else "mismatch")


def compare(ref: EvidenceRef, record: StudyRecord) -> list[dict[str, Any]]:
    """La ficha de EMMA contra lo que dice OSDR, campo a campo."""
    checks = [
        _equal("title", i18n.tr("título", "title"), ref.title, record.title),
        _equal(
            "date", i18n.tr("fecha de publicación", "publication date"),
            ref.date, record.release_date,
        ),
    ]
    population = record.population
    population_label = i18n.tr("población", "population")
    if population is None or ref.population is None:
        checks.append(_check(
            "population", population_label, ref.population, list(record.organisms),
            "not_comparable",
            i18n.tr("organismo sin clasificar en EMMA", "organism not classified in EMMA")
            if population is None
            else i18n.tr("la ficha no la da", "the reference card does not give it"),
        ))
    elif population == ref.population:
        checks.append(_check("population", population_label, ref.population, population, "match"))
    elif ref.population == "human_and_animal":
        checks.append(_check(
            "population", population_label, ref.population, population, "compatible",
            i18n.tr(
                "OSDR da el organismo de las muestras depositadas; la ficha dice que el estudio "
                "analiza también otra población, cuyos datos no están entre esas muestras",
                "OSDR gives the organism of the deposited samples; the reference card says that "
                "the study also analyses another population, whose data are not among those "
                "samples",
            ),
        ))
    else:
        checks.append(
            _check("population", population_label, ref.population, population, "mismatch")
        )
    claimed = CLAIMED_SAMPLES.get(ref.id)
    if claimed is not None:
        checks.append(_check(
            "sample_count", i18n.tr("muestras", "samples"), claimed[0], record.sample_count,
            "match" if claimed[0] == record.sample_count else "mismatch",
            i18n.tr(
                "muestras distintas en los ensayos del conjunto, no sujetos",
                "distinct samples in the assays of the dataset, not subjects",
            ),
        ))
    return checks


def mission_notes(record: StudyRecord) -> list[dict[str, str]]:
    """Las notas revisadas de la misión de un estudio que siguen valiendo para lo que da la API."""
    known = MISSION_NOTES.get(record.accession)
    if known is None or record.mission is None:
        return []
    if record.mission.get(known["field"]) != known["osdr"]:
        return []
    return [dict(known) | {"note": i18n.loc(known["note"])}]


def _study_view(ref: EvidenceRef, client: OsdrDataClient) -> dict[str, Any]:
    accession = accession_of(ref)
    if accession is None:
        raise OsdrDataError(f"{ref.id}: no es un estudio de OSDR")
    view: dict[str, Any] = {
        "id": ref.id,
        "accession": accession,
        "emma": {
            "title": ref.title,
            "date": ref.date,
            "population": ref.population,
            "url": ref.url,
            "scope_in_view": ref.scope_in_view,
        },
    }
    try:
        payload = client.study(accession)
    except OfflineDataUnavailable as exc:
        return view | {
            "available": False,
            "osdr": None,
            "mission_notes": [],
            "checks": [],
            "status": "unavailable",
            "status_display": i18n.tr(STATUS["unavailable"], STATUS_EN["unavailable"]),
            "reason": str(exc),
            "age": None,
        }
    record: StudyRecord = payload.data
    checks = compare(ref, record)
    disagrees = any(check["verdict"] == "mismatch" for check in checks)
    status = "disagrees" if disagrees else "agrees"
    return view | {
        "available": True,
        "osdr": record.to_dict() | {"scope": record.scope, "population": record.population},
        "mission_notes": mission_notes(record),
        "checks": checks,
        "status": status,
        "status_display": i18n.tr(STATUS[status], STATUS_EN[status]),
        "reason": None,
        "age": {
            "fetched_at": payload.fetched_at.isoformat(),
            "age_seconds": payload.age_seconds,
            "describe": payload.describe_age(),
            "from_cache": payload.from_cache,
            "source": payload.source,
        },
    }


def study(ref_id: str, client: OsdrDataClient | None = None) -> dict[str, Any]:
    """La comprobación de una ficha. `RegistryError` si no existe, `OsdrDataError` si no es de
    OSDR."""
    return _study_view(registry.get(ref_id), client or OsdrDataClient())


def studies(client: OsdrDataClient | None = None,
            refs: Iterable[EvidenceRef] | None = None) -> dict[str, Any]:
    """Todas las fichas de OSDR comprobadas. Una que no se pueda leer no tumba a las demás."""
    reader = client or OsdrDataClient()
    chosen = list(refs) if refs is not None else osdr_refs()
    # El idioma de la petición es un `ContextVar` y no pasa solo a los hilos del grupo: se lleva.
    lang = i18n.current()

    def view(ref: EvidenceRef) -> dict[str, Any]:
        with i18n.use(lang):
            return _study_view(ref, reader)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        views = list(pool.map(view, chosen))
    return {
        "source": SOURCE,
        "base_url": BASE_URL,
        "note": i18n.tr(
            "Lo que EMMA dice de cada estudio de OSDR, comparado con lo que dice la API de OSDR. "
            "Una discrepancia se declara con los dos valores y no se corrige sola. Es evidencia, "
            "no medida de ningún tripulante: no entra en el análisis ni en ninguna alerta.",
            "What EMMA says about each OSDR study, compared with what the OSDR API says. A "
            "discrepancy is declared with both values and is not corrected on its own. It is "
            "evidence, not a measurement of any crew member: it does not enter the analysis or "
            "any alert.",
        ),
        "fresh_for_seconds": int(FRESH_FOR.total_seconds()),
        "counts": {
            status: sum(1 for view in views if view["status"] == status) for status in STATUS
        },
        "studies": views,
    }
