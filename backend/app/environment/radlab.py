"""OSDR RadLab: dosimetria real de radiacion medida en vuelo.

HALLAZGOS CRITICOS del spike (ver `spikes/HALLAZGOS.md`):

  1. Una consulta sin filtro temporal devolvio **435 MB**. El rango de tiempo es
     obligatorio, no una optimizacion. Este cliente lo exige en la firma y
     ademas limita la ventana.
  2. `fields+=` exige la sintaxis booleana `query=(a=b)AND(c>=d)`. Mezclarla con
     el estilo clave-valor da error 500.
  3. **Sin `fields+=` no llega ninguna columna de dosis**, solo identificadores.
     Es decir: pedir campos no es opcional si se quieren datos utiles.
  4. El JSON viene como `{"columns": [...], "index": [...], "data": [[...]]}`
     (estilo pandas *split*), no como lista de objetos.
  5. El nombre del parametro es `fields` **con un espacio final**, no `fields+`.
     En una query string el `+` es la codificacion del espacio, y de ahi viene el
     `fields+=` de la documentacion. Enviar un `+` literal (`%2B`) da
     `500: Invalid key: fields+`. Ver DOSE_FIELD_PARAM.
  6. La API **ignora en silencio** los campos que no puede servir. Por eso
     `parse_split_table` falla con un mensaje explicito en vez de devolver una
     serie vacia.
  7. Pedir varios `fields` a la vez es impredecible: con `absorbed_dose_rate` y
     `dose_equivalent_rate` juntos devuelve solo uno, y no siempre el primero.
     Por eso el cliente pide **un campo por peticion** y comprueba que la
     columna llego.
  8. `dose_equivalent_rate` existe en el esquema pero **nunca esta poblado** en
     los datos de la ISS: 98 688 filas revisadas en cuatro ventanas entre 2011 y
     2022, con diez instrumentos distintos (DosTel1/2, Lidal, REM-Lid,
     Liulin-5-D1/D3, SPACEDOS02A-F y varios REM/RAD de Columbus), todas nulas.
     El modelo lo contempla de todos modos: el dia que se publique sera
     preferible a estimarlo, y `dosimetry.effective_dose` ya lo prefiere.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import httpx

from app.core import egress
from app.core.cache import CachedPayload, FileCache, OfflineDataUnavailable
from app.core.config import Settings, get_settings

BASE_URL = "https://visualization.osdr.nasa.gov/radlab/api/"
# Vigencia de una consulta (parámetro de diseño): RadLab es una serie histórica de dosis que se
# publica con días de retraso; volver a pedirla en cada estado no aporta nada.
FRESH_FOR = dt.timedelta(hours=6)

# Tope de ventana. Un dia de DosTel son ~2400 filas; 30 dias ya son ~72 000.
# Mas alla de eso la respuesta deja de ser manejable en la nave.
MAX_WINDOW_DAYS = 30

DEFAULT_FIELDS = ("absorbed_dose_rate",)

# El espacio final es deliberado y necesario: la API espera la clave `fields `,
# que en la URL se codifica como `fields+`. No quitarlo.
DOSE_FIELD_PARAM = "fields "


@dataclass(frozen=True, slots=True)
class DoseSample:
    """Una medida de dosimetria.

    `dose_equivalent_rate` es opcional porque en la practica RadLab no lo publica
    para ningun instrumento de la ISS (hallazgo 8). Se modela igualmente para que
    el dia que aparezca se use sin tocar nada mas.
    """

    timestamp: dt.datetime
    instrument: str
    spacecraft: str
    absorbed_dose_rate: float  # uGy/h
    dose_equivalent_rate: float | None = None  # uSv/h

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "instrument": self.instrument,
            "spacecraft": self.spacecraft,
            "absorbed_dose_rate": self.absorbed_dose_rate,
            "dose_equivalent_rate": self.dose_equivalent_rate,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DoseSample:
        return cls(
            timestamp=dt.datetime.fromisoformat(raw["timestamp"]),
            instrument=raw["instrument"],
            spacecraft=raw["spacecraft"],
            absorbed_dose_rate=raw["absorbed_dose_rate"],
            dose_equivalent_rate=raw.get("dose_equivalent_rate"),
        )


def build_query(
    spacecraft: str, instrument: str | None, start: dt.date, end: dt.date
) -> str:
    """Construye la expresion booleana que exige la API cuando se piden campos."""
    clauses = [f"(spacecraft={spacecraft})"]
    if instrument:
        clauses.append(f"(instrument={instrument})")
    clauses.append(f"(timestamp>={start.isoformat()})")
    clauses.append(f"(timestamp<={end.isoformat()})")
    return "AND".join(clauses)


def parse_split_table(payload: dict[str, Any]) -> list[DoseSample]:
    """Convierte el formato pandas *split* de RadLab en muestras tipadas.

    Las columnas de dosis solo aparecen si se pidieron con `fields+=`; si falta
    la columna, se avisa en lugar de devolver una serie vacia en silencio.
    """
    columns: list[str] = payload["columns"]
    if "absorbed_dose_rate" not in columns:
        raise ValueError(
            "la respuesta de RadLab no trae `absorbed_dose_rate`. Casi siempre "
            "significa que faltó `fields+=absorbed_dose_rate` en la consulta."
        )

    index_of = {name: position for position, name in enumerate(columns)}
    equivalent_at = index_of.get("dose_equivalent_rate")
    samples: list[DoseSample] = []

    for row in payload["data"]:
        rate = row[index_of["absorbed_dose_rate"]]
        if rate is None:
            continue  # huecos de instrumento: se omiten, no se interpolan
        equivalent = row[equivalent_at] if equivalent_at is not None else None
        samples.append(
            DoseSample(
                dose_equivalent_rate=float(equivalent) if equivalent is not None else None,
                timestamp=dt.datetime.fromisoformat(row[index_of["timestamp"]]),
                instrument=row[index_of["instrument"]],
                spacecraft=row[index_of["spacecraft"]],
                absorbed_dose_rate=float(rate),
            )
        )
    return samples


def integrate_dose_msv(samples: list[DoseSample]) -> float:
    """Dosis acumulada en mSv a partir de una serie de dosimetria.

    Delega en `dosimetry.effective_dose`, que aplica un factor de calidad medido
    en vuelo. La version anterior usaba Q = 1 y **subestimaba la dosis unas dos
    veces y media**; ver el encabezado de `app/environment/dosimetry.py`.

    Devuelve solo el numero, por comodidad de calculo. Para **presentar** la
    dosis a una persona usar `dosimetry.effective_dose`, que la acompana de su
    procedencia: una cifra de dosis sin decir si es medida o estimada, y con que
    factor, no es interpretable.
    """
    from app.environment.dosimetry import effective_dose

    return effective_dose(samples).value_msv


class RadLabClient:
    """Cliente de RadLab que impone ventana temporal y seleccion de campos."""

    def __init__(self, settings: Settings | None = None, cache: FileCache | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or FileCache(self.settings.cache_dir / "radlab")

    def dose_series(
        self,
        start: dt.date,
        end: dt.date,
        spacecraft: str = "ISS",
        instrument: str | None = "DosTel",
    ) -> CachedPayload:
        if end < start:
            raise ValueError(f"ventana invertida: {start} > {end}")
        if (end - start).days > MAX_WINDOW_DAYS:
            raise ValueError(
                f"ventana de {(end - start).days} días excede el máximo de "
                f"{MAX_WINDOW_DAYS}. Sin este límite la API llega a devolver "
                f"cientos de MB."
            )

        key = f"radlab:{spacecraft}:{instrument}:{start.isoformat()}:{end.isoformat()}"

        cached = self.cache.get(key)
        if cached is not None and (self.settings.offline or not cached.is_stale(FRESH_FOR)):
            # Con red, una caché reciente se usa sin salir: antes cada estado de salud llamaba a
            # RadLab sin necesidad. Su edad se declara igual.
            return self._rehydrate(cached)

        if self.settings.offline:
            raise OfflineDataUnavailable(
                f"serie de dosis {start}..{end} no cacheada y el sistema está offline"
            )

        try:
            payload = self._fetch(spacecraft, instrument, start, end)
        except httpx.HTTPError as exc:
            if cached is not None:
                return self._rehydrate(cached)
            raise OfflineDataUnavailable(f"RadLab inaccesible y sin cache: {exc}") from exc

        samples = parse_split_table(payload)
        stored = self.cache.put(
            key, [sample.to_dict() for sample in samples], source="OSDR RadLab"
        )
        return CachedPayload(
            data=samples, fetched_at=stored.fetched_at, source=stored.source, from_cache=False
        )

    def _rehydrate(self, cached: CachedPayload) -> CachedPayload:
        return CachedPayload(
            data=[DoseSample.from_dict(item) for item in cached.data],
            fetched_at=cached.fetched_at,
            source=cached.source,
            from_cache=True,
        )

    def _fetch(
        self, spacecraft: str, instrument: str | None, start: dt.date, end: dt.date
    ) -> dict[str, Any]:
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("query", build_query(spacecraft, instrument, start, end)),
            ("format", "json"),
        ]
        params.extend((DOSE_FIELD_PARAM, field) for field in DEFAULT_FIELDS)

        response = egress.get(self.settings, "radiation", BASE_URL, params=params)
        response.raise_for_status()
        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            # Un 200 sin JSON es una consulta fallida (caché vieja con su edad, o «no
            # disponible»), no una ventana mal pedida: antes la ruta lo daba como un 400.
            raise httpx.DecodingError(f"RadLab respondió sin JSON utilizable: {exc}") from exc
        if not (
            isinstance(payload, dict)
            and isinstance(payload.get("columns"), list)
            and isinstance(payload.get("data"), list)
        ):
            # Un JSON sin la forma *split* (un objeto de error) tampoco es una serie: antes era un
            # `KeyError` y un 500 en `/api/radiation/dose`.
            raise httpx.DecodingError("RadLab respondió sin JSON utilizable: no es una tabla split")
        return payload
