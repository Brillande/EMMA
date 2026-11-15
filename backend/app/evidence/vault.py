# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cotejar la cita de una firma contra el informe que cita (`fuente_clinica.cotejar` de Polaris).

Por qué existe: una firma puede apoyarse en un informe escaneado ("informe:12" y un fragmento).
Hasta ahora nadie abría el informe: valía con que la referencia tuviera buena forma. Polaris vio
el mismo agujero (auditoría externa, 24-sep): un veredicto se sellaba como "verificado" contra un
fichero que no existía. Su `cotejar` hace lo único que no se puede fingir: abre el fichero y busca
dentro el fragmento citado.

La bóveda de EMMA es el texto **des-identificado** de cada informe vigente, sacado del asiento
firmado (`store.report_blob`, que comprueba su hash), escrito como `informe-<índice>.md` en el
estado de EMMA. Los ganchos que Polaris deja para esto se rellenan con lo de EMMA:

* `_IDENTIDAD`: el veredicto de filiación ya firmado en el informe (`identidad_paciente`), y
  "otro_paciente" si el informe es de otro tripulante que el borrador. "Sin identidad declarada"
  de EMMA es su "no_consta", que su política da por servible.
* `_LOG`: cada cotejo deja una línea (quién, resultado, informe) en `vault/accesos.jsonl`.
* `bovedas()`: se sustituye durante la llamada, bajo cerrojo, por la de EMMA. No se usa su variable
  de entorno, que su código reserva a pruebas.

El cerrojo (`_LOCK`) cubre el cotejo entero, no solo los ganchos: poner la copia del informe en la
bóveda, que `cotejar` la lea y, en `locate`, volver a leerla para sacar la frase. Un cotejo a la
vez dentro del proceso; dos procesos de EMMA sobre el mismo estado no están cubiertos.

Lo que dice su propio módulo, y vale aquí: acredita PROCEDENCIA (el fragmento está en ese informe),
no FIDELIDAD (que sostenga lo que se firma). Eso sigue siendo juicio clínico humano.

La frase literal (`locate`, decisión del usuario, 2026-10-07). `cotejar` contesta sí o no y dos
huellas: por diseño no entrega texto ("quien necesite el texto va por la ventanilla y deja su
propia línea"). Pero quien pone la segunda firma tiene que LEER lo que el informe dice, no fiarse
de un "confirmada" sobre lo que se tecleó. `locate` hace esa lectura aparte: solo si `cotejar`
confirmó, abre la misma copia de la bóveda, comprueba que su huella es la que `cotejar` acaba de
dar, y devuelve el tramo del texto cuya forma normalizada (con el `normaliza` de Polaris, no uno
propio) es el fragmento citado. Tal cual está en la bóveda: ni lo que se tecleó, ni una
paráfrasis. Si no se localiza, lo dice; no rellena. Y deja su propia línea en `accesos.jsonl`.

Licencia y origen (AGPL §5a): usa `polaris/tools/fuente_clinica.py` de la copia literal de Polaris,
sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: la bóveda de informes
des-identificados y lo que rellena sus ganchos (`_IDENTIDAD`, `_LOG`, `bovedas()`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import threading
import unicodedata
from functools import cache
from pathlib import Path
from typing import Any

from app import polaris

_LOCK = threading.Lock()
SOURCE = re.compile(r"^\s*informe:(\d+)\s*$", re.I)
# Veredictos de EMMA (`app/reports/identity.py`) en el vocabulario de la política de Polaris.
_VERDICTS = {"coincide": "coincide", "ambiguo": "ambiguo", "otro_paciente": "otro_paciente",
             "sin_identidad": "no_consta"}


@cache
def _tool() -> Any:
    return polaris.load("fuente_clinica")


def report_index(source: str) -> int | None:
    """El índice del informe si la fuente es `informe:<n>`; None si cita otra cosa."""
    match = SOURCE.match(source or "")
    return int(match.group(1)) if match else None


def _vault() -> Path:
    return polaris.configure() / "vault" / "_PRIVADO_CLINICO"


def _log_line(folder: Path) -> Any:
    def log(agent: str, result: str, path: str) -> None:
        line = {"ts": dt.datetime.now(dt.UTC).isoformat(), "quien": agent, "resultado": result,
                "informe": Path(path).name}
        with (folder.parent / "accesos.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    return log


def _sync(store: Any, index: int, target: Path, subject: str) -> str:
    """Deja en `target` la copia vigente del informe y dice de quién es. Solo con `_LOCK` tomado.

    Por qué va dentro del cerrojo: se escribía antes de tomarlo, y dos cotejos del mismo informe
    a la vez (firma y contrafirma, o dos consolas) se pisaban. Uno truncaba el fichero mientras
    `cotejar` lo leía en el otro, que salía con «vacía», «fragmento ausente» o una huella que no
    era la del informe; en la contrafirma, un 409 o un `no_localizada` sin causa en el asiento.
    Y se escribe a un lado y se cambia de golpe (`os.replace`): si el proceso muere a media
    escritura, lo que queda es la copia anterior entera, no medio informe.
    """
    try:
        report, _ = store.report_blob(index)  # vigente y sin manipular
    except KeyError:
        target.unlink(missing_ok=True)  # redactado o inexistente: que no quede una copia vieja
        return "otro_paciente"
    pages = (report.get("ocr") or {}).get("pages") or []
    # `newline="\n"`: sin él, Windows escribe cada salto como CRLF y el `sha256` que `cotejar`
    # saca del fichero —la huella de la fuente que queda en la firma— dejaba de ser la del
    # texto del informe y cambiaba según la máquina que firmara. Lo enseñó la prueba de
    # Polaris `test_fuente_clinica`, que en Windows falla justo en esa huella.
    fresh = target.with_name(target.name + ".tmp")
    fresh.write_text("\n\n".join(str(page.get("text") or "") for page in pages),
                     encoding="utf-8", newline="\n")
    os.replace(fresh, target)
    found = str((report.get("identity") or {}).get("verdict") or "sin_identidad")
    return _VERDICTS.get(found, "ambiguo") if report.get("subject") == subject else (
        "otro_paciente")


def _check(store: Any, index: int, fragment: str, subject: str, who: str) -> dict[str, Any]:
    """El cotejo entero, con `_LOCK` ya tomado: poner la copia, sustituir los ganchos y leer."""
    folder = _vault()
    folder.mkdir(parents=True, exist_ok=True)
    name = f"informe-{index}.md"
    verdict = _sync(store, index, folder / name, subject)
    tool = _tool()
    saved = (tool.bovedas, tool._IDENTIDAD, tool._LOG)
    tool.bovedas = lambda: [str(folder)]
    tool._IDENTIDAD = lambda text, path: (verdict, "veredicto firmado en el informe")
    tool._LOG = _log_line(folder)
    try:
        result: dict[str, Any] = tool.cotejar(
            f"_PRIVADO_CLINICO/{name}", fragment.strip() or None, quien=who
        )
    finally:
        tool.bovedas, tool._IDENTIDAD, tool._LOG = saved
    return {
        "estado": result["estado"],
        "detalle": result["motivo"].replace(f"_PRIVADO_CLINICO/{name}", f"informe:{index}"),
        "sha256": result.get("sha256"),
        "sha256_fragmento": result.get("sha256_fragmento"),
        "identidad": result.get("identidad"),
    }


def check(store: Any, index: int, fragment: str, subject: str, who: str) -> dict[str, Any]:
    """`cotejar` de Polaris sobre el informe `index`, como estado de la fuente de una firma."""
    with _LOCK:
        return _check(store, index, fragment, subject, who)


LOCATED, NOT_LOCATED = "localizada", "no_localizada"
_KEPT = frozenset("abcdefghijklmnopqrstuvwxyz0123456789%")


def _normalised(text: str) -> tuple[str, list[int]]:
    """La forma normalizada de `cotejar` y, de cada carácter suyo, de qué posición de `text` sale.

    Mismos pasos que `fuente_clinica.normaliza`, carácter a carácter para no perder el origen.
    No se da por buena sin más: `_span` la compara con la de Polaris antes de usarla.
    """
    chars: list[str] = []
    origin: list[int] = []
    for position, char in enumerate(text):
        plain = "".join(c for c in unicodedata.normalize("NFKD", char)
                        if not unicodedata.combining(c))
        for c in plain.lower().replace("%", " % "):
            keep = c if c in _KEPT else " "
            if keep == " " and (not chars or chars[-1] == " "):
                continue
            chars.append(keep)
            origin.append(position)
    if chars and chars[-1] == " ":
        chars.pop()
        origin.pop()
    return "".join(chars), origin


def _span(tool: Any, text: str, fragment: str) -> tuple[int, int] | None:
    """Dónde está en `text` el tramo que `cotejar` casó con `fragment`; None si no se sabe."""
    wanted = str(tool.normaliza(fragment))
    normal, origin = _normalised(text)
    if not wanted or normal != tool.normaliza(text):
        return None  # si la normalización de Polaris cambia, no se adivina dónde cae
    at = normal.find(wanted)
    if at < 0:
        return None
    start, end = origin[at], origin[at + len(wanted) - 1] + 1
    while end < len(text) and unicodedata.combining(text[end]):
        end += 1  # la tilde suelta (texto en NFD) va con su letra
    # La frase que se enseña tiene que ser, para Polaris, exactamente lo citado.
    return (start, end) if tool.normaliza(text[start:end]) == wanted else None


def locate(
    store: Any, index: int, fragment: str, subject: str, who: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """El cotejo de `check` y, aparte, la frase literal que localiza en la bóveda.

    Las dos cosas bajo el mismo cerrojo: si entre el cotejo y la lectura otro cotejo rehiciera la
    copia, en Windows su `os.replace` chocaría con el fichero abierto aquí, y en cualquier máquina
    la lectura podría caer sobre una copia que no es la que se acaba de cotejar.
    """
    with _LOCK:
        return _locate(store, index, fragment, subject, who)


def _locate(
    store: Any, index: int, fragment: str, subject: str, who: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """`locate`, con `_LOCK` ya tomado: el cotejo y la frase.

    La frase es lo que ve quien va a poner la segunda firma y lo que queda en su asiento: la
    frase tal cual está en el texto des-identificado del informe, dónde (el informe, que es su
    asiento, y la posición en el texto) y la huella de ese texto. Si no hay frase,
    `no_localizada` con el motivo del cotejo: nunca el fragmento que se tecleó.
    """
    status = _check(store, index, fragment, subject, who)
    quote: dict[str, Any] = {
        "estado": NOT_LOCATED, "frase": "", "puntero": f"informe:{index}", "informe": index,
        "asiento": index, "inicio": None, "fin": None, "sha256": status.get("sha256"),
        "desidentificado": True, "detalle": status["detalle"],
    }
    folder = _vault()
    name = f"informe-{index}.md"
    if status["estado"] == "confirmada":
        try:
            raw = (folder / name).read_bytes()
        except OSError:
            raw = b""
        # La copia que se lee es la que `cotejar` acaba de cotejar, o no se enseña nada de ella.
        if hashlib.sha256(raw).hexdigest() != status.get("sha256"):
            quote["detalle"] = f"informe:{index} cambió entre el cotejo y la lectura"
        else:
            text = raw.decode("utf-8", errors="replace")
            span = _span(_tool(), text, fragment)
            if span is None:
                quote["detalle"] = (f"el cotejo confirma el fragmento en informe:{index}, pero "
                                    "no se pudo delimitar la frase literal")
            else:
                quote.update(estado=LOCATED, frase=text[span[0]:span[1]], inicio=span[0],
                             fin=span[1], detalle=f"frase literal de informe:{index}")
    elif status["estado"] == "existe":
        quote["detalle"] = f"la firma no cita ningún fragmento de informe:{index}"
    # El texto sale de la bóveda: su propia línea, como pide el muro de `fuente_clinica`.
    _log_line(folder)(f"emma:{who}", f"FRASE-{quote['estado']}", name)
    return status, quote
