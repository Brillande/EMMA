"""Spike: ¿hay ecografías públicas con las que validar la ecografía a bordo?

Por qué existe: la idea era validar con datos de la NASA. Antes de diseñar el motor de medida
hay que saber si esos datos existen y bajo qué licencia, porque Space Apps exige que todo
material de terceros esté libre o bajo licencia OSI y que se cite. Este script deja la búsqueda
reproducible en lugar de confiar en lo que alguien recuerde haber buscado.

Consulta dos fuentes:
  1. NASA OSDR (incluye ALSDA, el archivo de datos de astronautas): búsqueda de texto libre.
  2. Zenodo: los registros candidatos, con su licencia declarada y sus ficheros.

Ejecutar:  python backend/spikes/spike_ultrasound_data.py
"""

import json
import urllib.parse
import urllib.request

OSDR_SEARCH = "https://osdr.nasa.gov/osdr/data/search"
OSDR_FILES = "https://osdr.nasa.gov/osdr/data/osd/files"
ZENODO = "https://zenodo.org/api/records"
TIMEOUT = 40

OSDR_INDEXES = ("cgene", "alsda")
TERMS = ("ultrasound", "echography", "sonography", "optic nerve sheath")

# Registros de Zenodo que aparecieron como candidatos en la búsqueda del 2026-09-24.
ZENODO_CANDIDATES = (
    "1327317",  # HC18: perímetro cefálico fetal, con mm/píxel por imagen
    "1009146",  # hígado graso en modo B
)


def get_json(url: str, params: dict[str, str] | None = None) -> object:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "EMMA-spike/0.1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def search_osdr() -> None:
    print("\n[1] NASA OSDR / ALSDA — búsqueda de texto libre")
    # Un solo índice por petición: con varios separados por comas la API no devuelve `total`.
    for index in OSDR_INDEXES:
        for term in TERMS:
            data = get_json(
                OSDR_SEARCH, {"term": term, "from": "0", "size": "20", "type": index}
            )
            hits = data.get("hits", {}) if isinstance(data, dict) else {}
            print(f"    {index:6} {term!r:22} total={hits.get('total')}")
            for hit in hits.get("hits", []):
                src = hit["_source"]
                title = str(src.get("Study Title", ""))[:100]
                print(f"        {src.get('Accession')} | {title}")


def osdr_files(accession_number: str) -> None:
    print(f"\n[2] Ficheros de OSD-{accession_number}")
    data = get_json(f"{OSDR_FILES}/{accession_number}")
    studies = data.get("studies", {}) if isinstance(data, dict) else {}
    for accession, study in studies.items():
        for f in study.get("study_files", []):
            print(f"    {accession} | {f.get('file_name')} | {f.get('category')}")


def zenodo_records() -> None:
    print("\n[3] Zenodo — licencia y ficheros de los candidatos")
    for record_id in ZENODO_CANDIDATES:
        rec = get_json(f"{ZENODO}/{record_id}")
        assert isinstance(rec, dict)
        meta = rec["metadata"]
        print(f"    {record_id} | {meta['title'][:80]}")
        print(f"        licencia={meta.get('license', {}).get('id')}  doi={rec.get('doi')}")
        for f in rec.get("files", []):
            print(f"        {f['key']}  ({f['size']} B)")


def main() -> None:
    print("=" * 70)
    print("SPIKE: datos ecográficos públicos")
    print("=" * 70)
    search_osdr()
    osdr_files("435")
    zenodo_records()


if __name__ == "__main__":
    main()
