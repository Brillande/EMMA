"""Lo leído junto a la radiación: el aviso de HERA, la fase del ciclo solar y el fin del refugio.

La base de conocimiento (§7) pone «HERA/Orion y dosimetría: detección de hazard y alertas
operacionales» y la conversación de ideación lo resume en que HERA avisa y el sistema ayuda a
entender qué significa esa exposición. EMMA citaba esa frase sin ficha, y todas las fichas
«HERA» del registro eran del análogo terrestre Human Exploration Research Analog, que comparte
siglas con el instrumento de Orion (Hybrid Electronic Radiation Assessor). La conversación
también dice que los rayos cósmicos galácticos suben en el mínimo solar, y ninguna fuente leída
daba en qué fase está el ciclo. Y la contramedida del refugio decía «hasta 24 h» sin decir qué
lo termina. Tres huecos de la misma clase: lo que una fuente dice, enseñado como fuente.

Lo leído vive en `data/radiation_read.json`, aparte de `countermeasures.json` a propósito: la
biblioteca de contramedidas entra en `rules_version` y esto no decide nada. Este cargador es la
defensa:

- cada frase tiene su sitio en la fuente y su ficha en el registro, la ficha es de NASA, del Space
  Weather Prediction Center de NOAA o del servidor de preprints (por https), dice en su nota
  «Leída el …» (o «Leído», «Releída») con ese día y lleva la frase tal cual: lo que se enseña es lo
  que quedó escrito al leer, no un recuerdo. Una frase leída otro día que el resto lleva su propio
  `read_on`, que no puede ser anterior a la primera lectura, y es ese día el que tiene que estar en
  la nota de su ficha;
- **ninguna cifra que escribe EMMA es suya**: cada cifra del rótulo, del texto, del alcance y de
  lo buscado tiene que estar en una de las frases citadas de esa misma entrada. El cotejo es
  propio y más estricto que el de `evidence/support.py` a propósito: aquel está hecho para
  comparar una afirmación con un resumen y deja pasar, por diseño, una cifra pegada a su unidad
  («12h»), un número tras «nivel» o «fase» y cualquier valor entre 1950 y 2049; aquí cuenta toda
  secuencia de dígitos. Solo se aparta una fecha (ISO o «15 de octubre de 2024»), el número de un
  catálogo (NTRS, arXiv) y un año suelto sin unidad detrás que sea el de una ficha citada o el de
  la lectura (no cualquier valor que parezca un año: «tras 1999 minutos» cuenta). Un número
  escrito con letras («doce horas», «siete sensores», «quinientas horas») no se puede cotejar con
  una frase inglesa y tampoco se admite. Un «hasta 24 h» o un «25 %» que no sale de una cita no
  se sirve, y un umbral propio de salida del refugio no tiene donde escribirse. Tampoco carga
  Polaris al importar (aquel cotejo sí), y este módulo se valida al arrancar;
- el aviso de HERA declara que EMMA no lo lee (`emma_reads_it` es falso): EMMA no tiene
  conexión con HERA, y decir lo contrario sería falso;
- la nota del ciclo solar lleva la fecha de la nota (`as_of`), que tiene que ser la de su ficha y
  no posterior a la lectura: es una nota fechada, no el estado de hoy. Las gráficas del ciclo de
  NOAA (decimoctava ronda, U14) entran solo como cifra copiada de los datos que pintan, con su mes;
  la fase no la dicen, y EMMA no la deduce: no hay campo donde escribirla.

Se valida al importar `analysis/radiation.py`, como las fichas que ese módulo cita: un fichero
roto se ve al arrancar (y en la suite), no como un fallo de `/status` a media misión.

No entra en el análisis, en el riesgo, en la proyección de dosis (que sigue suponiendo tasa
constante) ni en ninguna alerta (invariante 5), y no sale a la red: la lectura se hizo una vez,
en Tierra.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core import i18n
from app.evidence import registry

READ_PATH = Path(__file__).resolve().parents[1] / "data" / "radiation_read.json"

# Las páginas de NASA, la del Space Weather Prediction Center de NOAA (la agencia que, con NASA,
# publica el ciclo solar) y el servidor de preprints. Un buscador o un periódico no son la fuente.
OFFICIAL_HOSTS = frozenset({
    "www.nasa.gov", "science.nasa.gov", "ntrs.nasa.gov", "ccmc.gsfc.nasa.gov",
    "www.swpc.noaa.gov", "arxiv.org",
})

TOP_FIELDS = frozenset({"_nota", "read_on", "onboard_warning", "solar_cycle", "shelter_exit"})
ENTRY_FIELDS = frozenset({"label", "text", "quotes", "not_found", "scope"})
# Lo que EMMA escribe en cada entrada y se enseña: ninguna cifra suya en ninguno.
WRITTEN_FIELDS = ("label", "text", "scope", "not_found")
# Lo propio de cada entrada, además de lo común. Nada más: un `threshold` no cabe.
EXTRA_FIELDS: dict[str, frozenset[str]] = {
    "onboard_warning": frozenset({"emma_reads_it"}),
    "solar_cycle": frozenset({"as_of"}),
    "shelter_exit": frozenset(),
}
QUOTE_FIELDS = frozenset({"quote", "ref", "where"})
# Opcional en una frase: el día en que se leyó, si no es el de la primera lectura.
QUOTE_READ_ON = "read_on"

# Un número escrito con letras: no se puede cotejar con una frase inglesa. Un cardinal de dos en
# adelante, vaya o no con unidad («siete sensores»); «medio» y «media» solo junto a una unidad,
# porque sueltas tienen otros sentidos. «Un» y «una» son además artículos y no se miran.
_SPELLED = re.compile(
    r"\b(?:(?:dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|"
    r"dieci\w+|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|"
    r"cien|ciento|cientos|(?:dos|tres|cuatro|seis|sete|ocho|nove)cient[oa]s|quinient[oa]s|"
    r"mil|mill[oó]n|millones|millar(?:es)?|centenar(?:es)?|docenas?|decenas?)\b"
    r"|\bcuarto\s+de\s+hora\b"
    r"|(?:medio|media)\s+(?:horas?|d[ií]as?|minutos?|semanas?|mes|años?|por\s+ciento)\b)",
    re.IGNORECASE,
)
# Lo que no es una cifra que cotejar en lo que escribe EMMA: una fecha ISO, una fecha con el mes
# escrito («15 de octubre de 2024», «febrero de 2025») y el número de un catálogo.
_MONTHS = (
    "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|"
    "diciembre"
)
_NOT_A_FIGURE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"
    rf"|\b(?:\d{{1,2}}\s+de\s+)?(?:{_MONTHS})(?:\s+de\s+\d{{4}})?\b"
    r"|\b(?:NTRS|arXiv)\s*:?\s*[\d.]+(?:v\d+)?",
    re.IGNORECASE,
)
# Toda secuencia de dígitos cuenta, pegada a letras o no («12h», «1,25x»); con su parte decimal,
# escrita con coma o, por descuido, con punto: «0.125» es 0,125 y no 125.
_DIGITS_ES = re.compile(r"\d+(?:[.,]\d+)?")
_DIGITS_EN = re.compile(r"\d+(?:\.\d+)?")
# El punto de los millares en español («1.000», «12.500»): grupos de tres tras una cabeza de una a
# tres cifras que no empieza por cero. «0.125» o «1.25» no lo son.
_THOUSANDS_ES = re.compile(r"(?<![\d.,])[1-9]\d{0,2}(?:\.\d{3})+(?![.,]?\d)")
# Un año suelto no es una cifra que cotejar si es el de una de las fichas citadas o el de la
# lectura, y no lleva detrás una unidad («2024 µSv» sí cuenta). Cualquier valor entre 1950 y
# 2049 dejaba pasar «tras 1999 minutos» o «2000 sensores».
_UNIT_AFTER = re.compile(
    r"\s*(?:%|[µu]?[mµ]?(?:sv|gy)\b|h\b|min\b|s\b|horas?\b|d[ií]as?\b|veces\b|x\b)", re.IGNORECASE
)
# La nota de la ficha dice que se leyó ese día: «Leída el 2026-10-23», «Leído…», «Releída…».
_READ_MARK = "(?:Re)?[Ll]e[ií]d[oa]s? el {day}"


class RadiationReadError(ValueError):
    """Lo leído sobre la radiación no cumple su contrato: no se sirve."""


def _text(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    return isinstance(value, str) and bool(value.strip())


def _fields(key: str, item: Any, expected: frozenset[str]) -> None:
    if not isinstance(item, dict):
        raise RadiationReadError(f"{key}: se esperaba un objeto con {sorted(expected)}")
    if missing := sorted(expected - item.keys()):
        raise RadiationReadError(f"{key}: faltan campos {missing}")
    if extra := sorted(item.keys() - expected):
        raise RadiationReadError(f"{key}: campos desconocidos {extra}")


def _date(key: str, value: Any) -> dt.date:
    # Solo AAAA-MM-DD: `fromisoformat` acepta también «20261023» o «2026-W43-5», y la interfaz
    # (`formatSourceDate`) rompe con ellas al pintar.
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise RadiationReadError(f"{key}: {value!r} no es una fecha AAAA-MM-DD")
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise RadiationReadError(f"{key}: {value!r} no es una fecha AAAA-MM-DD") from None


def _canonical(token: str) -> str:
    """«1,25» y «1.25» → «1.25»; «24» → «24»: la misma cifra se escribe igual en los dos idiomas."""
    return format(Decimal(token.replace(",", ".")).normalize(), "f")


def _quoted_figures(quote: str) -> set[str]:
    """Las cifras de una frase inglesa: todas, sin apartar nada; «1,000» es mil."""
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", quote)
    return {_canonical(match.group(0)) for match in _DIGITS_EN.finditer(text)}


def _written_figures(text: str, years: frozenset[str] = frozenset()) -> list[str]:
    """Las cifras de lo que escribe EMMA: todos los dígitos menos fechas, catálogos y los años
    de `years` (los de las fichas citadas y el de la lectura)."""
    text = _NOT_A_FIGURE.sub(" ", text)
    text = _THOUSANDS_ES.sub(lambda match: match.group(0).replace(".", ""), text)
    found: list[str] = []
    for match in _DIGITS_ES.finditer(text):
        token = match.group(0)
        if token in years and not _UNIT_AFTER.match(text, match.end()):
            continue
        figure = _canonical(token)
        if figure not in found:
            found.append(figure)
    return found


def _quote_read_on(item: dict[str, Any], read_on: str) -> str:
    """El día en que se leyó la frase: el suyo si lo declara, si no el de la primera lectura."""
    return str(item.get(QUOTE_READ_ON, read_on))


def _quote(key: str, item: Any, read_on: str) -> registry.EvidenceRef:
    """Una frase literal, con su sitio, de una ficha oficial que dice que se leyó ese día."""
    own = isinstance(item, dict) and QUOTE_READ_ON in item
    _fields(key, item, QUOTE_FIELDS | ({QUOTE_READ_ON} if own else set()))
    for field in sorted(QUOTE_FIELDS):
        if not _text(item, field):
            raise RadiationReadError(
                f"{key}: falta `{field}`: sin frase, sitio y ficha no es un dato"
            )
    day = _quote_read_on(item, read_on)
    if own and _date(f"{key}: `read_on`", item[QUOTE_READ_ON]) < _date("read_on", read_on):
        # La primera lectura es la de arriba: una frase no se leyó antes.
        raise RadiationReadError(
            f"{key}: `read_on` anterior a la primera lectura ({read_on}): errata de fecha"
        )
    try:
        ref = registry.get(item["ref"])
    except registry.RegistryError as error:  # una ficha que no está en el registro no se cita
        raise RadiationReadError(f"{key}: {error}") from None
    parts = urlsplit(ref.url or "")
    if parts.scheme != "https" or parts.hostname not in OFFICIAL_HOSTS:
        raise RadiationReadError(
            f"{key}: {ref.url!r} no es NASA, el centro de NOAA ni el servidor de preprints"
        )
    notes = ref.notes or ""
    if not re.search(_READ_MARK.format(day=re.escape(day)), notes):
        raise RadiationReadError(
            f"{key}: la ficha {ref.id} no dice que se leyera el {day}: sin rastro de la lectura"
        )
    if item["quote"] not in notes:
        raise RadiationReadError(
            f"{key}: la frase no está en la nota de {ref.id}: lo que se enseña es lo que se anotó"
        )
    return ref


def _no_figure_of_its_own(name: str, entry: dict[str, Any], years: frozenset[str]) -> None:
    """Cada cifra que escribe EMMA está en una frase citada de la misma entrada."""
    quoted = {figure for item in entry["quotes"] for figure in _quoted_figures(item["quote"])}
    for field in WRITTEN_FIELDS:
        if spelled := _SPELLED.search(entry[field]):
            raise RadiationReadError(
                f"{name}/{field}: «{spelled.group(0)}» va con letras y no se puede cotejar con "
                "su frase: se escribe en cifras"
            )
        if invented := [f for f in _written_figures(entry[field], years) if f not in quoted]:
            raise RadiationReadError(
                f"{name}/{field}: cifras que no están en ninguna frase citada: {invented}"
            )


def _validate_entry(name: str, entry: Any, read_on: str) -> list[registry.EvidenceRef]:
    _fields(name, entry, ENTRY_FIELDS | EXTRA_FIELDS[name])
    for field in WRITTEN_FIELDS:
        if not _text(entry, field):
            raise RadiationReadError(f"{name}: falta `{field}`")
    # El alcance se pinta como una frase a la que la interfaz pone el punto: sin el suyo.
    if entry["scope"].rstrip().endswith((".", ";", ":")):
        raise RadiationReadError(
            f"{name}: `scope` termina en puntuación; el punto lo pone la interfaz"
        )
    quotes = entry["quotes"]
    if not isinstance(quotes, list) or not quotes:
        raise RadiationReadError(f"{name}: sin ninguna frase de su fuente")
    refs = [_quote(f"{name}/{index}", item, read_on) for index, item in enumerate(quotes)]
    if name == "solar_cycle":
        as_of = _date(f"{name}: `as_of`", entry["as_of"])
        if as_of > _date("read_on", read_on):
            raise RadiationReadError(f"{name}: la nota es posterior a su lectura")
        if entry["as_of"] not in {ref.date for ref in refs}:
            raise RadiationReadError(f"{name}: `as_of` no es la fecha de ninguna de sus fichas")
    if name == "onboard_warning" and entry["emma_reads_it"] is not False:
        raise RadiationReadError(f"{name}: EMMA no tiene conexión con HERA; no la lee")
    return refs


def validate(raw: Any) -> dict[str, Any]:
    _fields("radiation_read", raw, TOP_FIELDS)
    read_on = raw["read_on"]
    _date("read_on", read_on)
    cited = [ref for name in EXTRA_FIELDS for ref in _validate_entry(name, raw[name], read_on)]
    # Los años que el texto puede nombrar sin cotejarlos: los de las fichas que cita y el de la
    # lectura («un artículo de 2016», «una nota de 2025 o 2026»).
    years = frozenset({read_on[:4]} | {ref.date[:4] for ref in cited if ref.date})
    for name in EXTRA_FIELDS:
        _no_figure_of_its_own(name, raw[name], years)
    return raw  # type: ignore[no-any-return]


@cache
def _read() -> dict[str, Any]:
    return validate(json.loads(READ_PATH.read_text(encoding="utf-8")))


def cited_refs() -> set[str]:
    """Las fichas que cita lo leído: el registro comprueba que ninguna quede huérfana."""
    raw = _read()
    return {item["ref"] for name in EXTRA_FIELDS for item in raw[name]["quotes"]}


@cache
def _describe() -> dict[str, dict[str, Any]]:
    raw = _read()
    described: dict[str, dict[str, Any]] = {}
    for name in EXTRA_FIELDS:
        entry = raw[name]
        # Cada ficha una vez, en el orden en que la cita la primera frase; cada frase, con el
        # identificador de la suya. Repetir la ficha entera por frase la mandaba hasta cuatro veces
        # en cada `/status`.
        sources = list(dict.fromkeys(item["ref"] for item in entry["quotes"]))
        described[name] = {
            **{field: entry[field] for field in sorted(entry) if field != "quotes"},
            "read_on": raw["read_on"],
            # Cada frase con el día en que se leyó: no todas las fuentes se leyeron el mismo, y
            # poner a una la fecha de otra lectura sería decir que se leyó cuando aún no.
            "quotes": [
                {
                    "quote": item["quote"],
                    "where": item["where"],
                    "ref": item["ref"],
                    "read_on": _quote_read_on(item, raw["read_on"]),
                }
                for item in entry["quotes"]
            ],
            "sources": [registry.cite(ref_id).to_dict() for ref_id in sources],
        }
    return described


def describe() -> dict[str, dict[str, Any]]:
    """Las tres entradas para enseñar, con cada ficha resuelta. Cada respuesta lleva su copia.

    El idioma se pone aquí, al servir, con el hermano `radiation_read.en.json`: lo validado y lo
    cacheado es el castellano, y las frases de la fuente (`quote`) van en el suyo.
    """
    return i18n.localized(copy.deepcopy(_describe()), READ_PATH)
