"""El historial misión a misión de un tripulante, tal y como lo declara una persona.

POR QUÉ EXISTE
--------------
La especificación del equipo pone `mission_history` en el astronauta (§3), y su conversación de
ideación pide la escala de carrera como «historial de misiones + exposición acumulada» («Career
baseline → Mission 1 → Recovery → Mission 2 → …»). EMMA tenía dos cifras sueltas en el perfil
(`crew-profile`): cuántas misiones previas y la dosis de carrera previa. De qué misiones, cuándo,
cuánto duró cada una y cuánta dosis dejó cada una no constaba en ningún sitio, y la dosis de
carrera previa no se podía cotejar con nada.

LO QUE ES Y LO QUE NO ES
------------------------
Una declaración hecha en la consola y firmada en el registro (decisión del usuario, 2026-10-22):
nombre, fecha de inicio, fecha de fin y, si se conoce, dosis de cada misión previa. **EMMA no la
comprueba contra ningún registro de vuelos ni de dosimetría**: es lo que alguien dijo.

* **No sustituye la dosis previa del perfil.** La escala de carrera y su proyección
  (`analysis/radiation.py`) siguen leyendo solo `prior_career_dose_msv` del perfil. Si la suma de
  las dosis del historial no casa con ella, se dice (`describe`); no se corrige ninguna de las dos
  ni se elige una: elegir sería decidir qué declaración es la buena, y eso lo hace una persona.
* **Sin dosis no es cero.** Una misión sin dosis declarada deja la suma incompleta, y una suma
  incompleta no se coteja: se dice cuántas faltan.
* **Los días se calculan, no se declaran.** Salen de las dos fechas (`días entre fechas`). Un
  campo «días» al lado de las fechas sería una segunda declaración del mismo hecho que podría
  contradecirlas; con precisión de día, además, la cuenta puede diferir en uno de la duración
  oficial en horas, y por eso se rotula como lo que es.

QUÉ DECLARACIÓN VALE
--------------------
La última firmada por la consola (y, para Tierra, la que ya existía en su corte), como el perfil.
Se declara la lista entera y se corrige declarándola de nuevo; no hay borrado ni edición. Una lista
vacía es una declaración: «ninguna misión previa», distinta de «sin declarar».
"""

from __future__ import annotations

import datetime as dt
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core import display, i18n

# El mismo tope que `prior_missions` en la API del perfil.
MAX_PRIOR_MISSIONS = 20
MAX_NAME_LENGTH = 80
_KEYS = ("dose_msv", "end", "name", "start")

# Dos dosis «casan» si difieren en menos de esto: la suma de decimales en coma flotante no es
# exacta (0,1 + 0,2 no es 0,3) y la consola declara como mucho centésimas. No es un umbral clínico:
# no decide nada, solo si se escribe «casa» o «no casa».
DOSE_MATCH_TOLERANCE_MSV = 0.005

SCOPE = (
    "Declarado por una persona; EMMA no lo comprueba contra ningún registro. No entra en ningún "
    "cálculo: la dosis de carrera sigue usando solo la dosis previa declarada en el perfil."
)
DAYS_BASIS = (
    "días entre la fecha de inicio y la de fin declaradas; con precisión de día puede diferir en "
    "uno de la duración oficial"
)
# De dónde sale cada misión previa en la crónica (`timeline.py`, etapa «carrera»): lo que dijo
# una persona, sin comprobar. Va en la fuente de cada hecho, después del número de asiento.
CHRONICLE_SOURCE = (
    "historial misión a misión declarado; EMMA no lo comprueba contra ningún registro"
)
i18n.en(
    SCOPE,
    "Declared by a person; EMMA does not check it against any record. It does not enter any "
    "calculation: the career dose still uses only the prior dose declared in the profile.",
)
i18n.en(
    DAYS_BASIS,
    "days between the declared start and end dates; at day precision it may differ by one "
    "from the official duration",
)
i18n.en(
    CHRONICLE_SOURCE,
    "declared mission-by-mission history; EMMA does not check it against any record",
)


@dataclass(frozen=True)
class PriorMission:
    """Una misión previa. `dose_msv` None: no se conoce (no es cero)."""

    name: str
    start: dt.date
    end: dt.date
    dose_msv: float | None = None

    @property
    def days(self) -> int:
        return (self.end - self.start).days


def overlaps_current(mission: PriorMission, current_start: dt.date) -> bool:
    """¿Se solapa una misión previa con la que está en curso? Si termina después del día en que
    empieza; acabar ese mismo día no es solape, como dos previas seguidas. Una sola regla para
    rechazar al firmar (`check`) y avisar al leer (`describe`)."""
    return mission.end > current_start


def check(
    missions: Sequence[PriorMission],
    today: dt.date | None = None,
    current_start: dt.date | None = None,
) -> list[PriorMission]:
    """Las misiones en orden de inicio, o ValueError si alguna no puede ser.

    Se rechaza: un nombre sin letras ni cifras o demasiado largo, una misión que termina antes de
    empezar o después de hoy (es una misión PREVIA), una dosis negativa o no finita, dos misiones
    que se solapan o empiezan el mismo día y más de las que admite el perfil. Nada de esto es una
    regla clínica: es lo que no puede ser verdad de una persona. Se impone al escribir; al leer
    solo se exige la forma (`decode`), para que una regla más estricta mañana no deje ilegible un
    asiento firmado hoy.

    `current_start` es el inicio de la misión en curso (`Settings.mission_start`). Con él, una
    misión previa tampoco puede terminar después de ese día: con la misión ya empezada, «antes de
    hoy» dejaba declarar una previa que se solapa con la actual (§5.36.4). Puede terminar el mismo
    día en que empieza la actual, como dos previas seguidas. Sin él (una llamada que no lo
    conoce), la regla es la de antes.
    """
    limit = dt.datetime.now(dt.UTC).date() if today is None else today
    if len(missions) > MAX_PRIOR_MISSIONS:
        raise ValueError(f"como mucho {MAX_PRIOR_MISSIONS} misiones previas")
    cleaned: list[PriorMission] = []
    for mission in missions:
        name = mission.name.strip()
        if not any(char.isalnum() for char in name):
            raise ValueError("cada misión previa necesita un nombre")
        if len(name) > MAX_NAME_LENGTH:
            raise ValueError(
                f"el nombre de una misión tiene como mucho {MAX_NAME_LENGTH} caracteres"
            )
        if mission.end < mission.start:
            raise ValueError(f"la misión «{name}» termina antes de empezar")
        if mission.end > limit:
            raise ValueError(f"la misión «{name}» termina después de hoy: no es una misión previa")
        if current_start is not None and overlaps_current(mission, current_start):
            raise ValueError(
                f"la misión «{name}» termina después del inicio de la misión en curso "
                f"({current_start.isoformat()}): se solapa con ella"
            )
        dose = mission.dose_msv
        if dose is not None and (not math.isfinite(dose) or dose < 0):
            raise ValueError(f"la dosis de la misión «{name}» no puede ser negativa")
        cleaned.append(PriorMission(name, mission.start, mission.end, dose))
    ordered = sorted(cleaned, key=lambda item: (item.start, item.end))
    for before, after in zip(ordered, ordered[1:], strict=False):
        # Una puede empezar el día que acaba la anterior; dos que empiezan el mismo día, no.
        if after.start < before.end or after.start == before.start:
            raise ValueError(f"las misiones «{before.name}» y «{after.name}» se solapan")
    return ordered


def encode(missions: Sequence[PriorMission]) -> str:
    """La lista como texto JSON, con cada valor como texto (vacío: dosis no conocida)."""
    return json.dumps(
        [
            {
                "name": item.name,
                "start": item.start.isoformat(),
                "end": item.end.isoformat(),
                "dose_msv": "" if item.dose_msv is None else repr(item.dose_msv),
            }
            for item in missions
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def decode(text: str) -> list[PriorMission]:
    """Lo contrario de `encode`; ValueError si no tiene su forma.

    Solo la forma: una lista de misiones con sus cuatro campos de texto, fechas ISO y dosis vacía
    o numérica y finita. Las reglas de `check` se impusieron al firmar; volver a pasarlas aquí
    haría que una regla más estricta mañana dejara ilegible un asiento firmado bien hoy.
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("el historial no es JSON") from exc
    if not isinstance(raw, list):
        raise ValueError("el historial no es una lista")
    missions: list[PriorMission] = []
    for item in raw:
        if not isinstance(item, dict) or tuple(sorted(item)) != _KEYS:
            raise ValueError("misión previa con otros campos")
        if any(not isinstance(item[key], str) for key in _KEYS):
            raise ValueError("misión previa con un campo que no es texto")
        dose = None if item["dose_msv"] == "" else float(item["dose_msv"])
        if dose is not None and not math.isfinite(dose):
            raise ValueError("misión previa con una dosis que no es una cifra")
        missions.append(
            PriorMission(
                name=item["name"],
                start=dt.date.fromisoformat(item["start"]),
                end=dt.date.fromisoformat(item["end"]),
                dose_msv=dose,
            )
        )
    return missions


def _msv(value: float) -> str:
    return f"{display.number(value, 2)} mSv"


def _count(number: int) -> str:
    return i18n.tr(
        f"{number} misión" if number == 1 else f"{number} misiones",
        f"{number} mission" if number == 1 else f"{number} missions",
    )


def _days(number: int) -> str:
    return i18n.tr(
        f"{number} día" if number == 1 else f"{number} días",
        f"{number} day" if number == 1 else f"{number} days",
    )


def chronicle_sentence(mission: PriorMission) -> str:
    """Una misión previa como hecho de la crónica: lo declarado y nada más, sin veredicto.

    Las fechas, tal y como se declararon (con día); los días, con su base («entre fechas»); la
    dosis, la declarada, o que no se declaró (no es cero). No se coteja aquí con el perfil: eso
    lo dice `describe`, y la crónica cuenta hechos, no cotejos. La palabra es «exposición a
    radiación» y no «dosis»: el filtro de lenguaje (`text_guard`) aparta «dosis» por ser de
    fármacos, y en mSv no hay ambigüedad. Esa comprobación es de prueba, sobre las frases que
    escribe EMMA (`test_no_career_text_sounds_like_an_order_or_a_verdict`); el nombre de la
    misión lo escribió una persona y entra tal cual, sin filtro en tiempo de ejecución.
    """
    dose = (
        f"exposición a radiación declarada {_msv(mission.dose_msv)}"
        if mission.dose_msv is not None
        else "sin exposición a radiación declarada (no es cero)"
    )
    dose_en = (
        f"declared radiation exposure {_msv(mission.dose_msv)}"
        if mission.dose_msv is not None
        else "no declared radiation exposure (this is not zero)"
    )
    return i18n.tr(
        f"misión previa «{mission.name}», del {mission.start.isoformat()} al "
        f"{mission.end.isoformat()} ({_days(mission.days)} entre fechas); {dose}",
        f"prior mission «{mission.name}», from {mission.start.isoformat()} to "
        f"{mission.end.isoformat()} ({_days(mission.days)} between dates); {dose_en}",
    )


def _missions_check(missions: Sequence[PriorMission], prior_missions: int | None) -> dict[str, Any]:
    told = _count(len(missions))
    if prior_missions is None:
        return {
            "key": "missions",
            "matches": None,
            "text": i18n.tr(
                f"El historial declara {told}; el perfil no declara cuántas misiones previas hay, "
                "y no hay con qué cotejarlo.",
                f"The history declares {told}; the profile does not declare how many prior "
                "missions there are, and there is nothing to compare it with.",
            ),
        }
    if prior_missions == len(missions):
        return {
            "key": "missions",
            "matches": True,
            "text": i18n.tr(
                f"El historial declara {told}, las mismas que el perfil.",
                f"The history declares {told}, the same number as the profile.",
            ),
        }
    return {
        "key": "missions",
        "matches": False,
        "text": i18n.tr(
            f"El historial declara {told} y el perfil, {_count(prior_missions)}. No se corrige "
            "ninguno de los dos: lo puede revisar quien los declaró.",
            f"The history declares {told} and the profile, {_count(prior_missions)}. Neither is "
            "corrected: whoever declared them can review it.",
        ),
    }


def _dose_check(total: float, missing: int, prior_dose: float | None) -> dict[str, Any]:
    """`total`, la suma de las dosis conocidas; `missing`, cuántas misiones no la tienen."""
    if missing:
        return {
            "key": "dose",
            "matches": None,
            "text": i18n.tr(
                f"{_count(missing).capitalize()} del historial sin dosis declarada: la suma de las "
                f"demás ({_msv(total)}) está incompleta y no se coteja con la dosis previa del "
                "perfil. Sin dosis no es cero.",
                f"{_count(missing).capitalize()} in the history with no declared dose: the sum "
                f"of the others ({_msv(total)}) is incomplete and is not compared with the prior "
                "dose of the profile. No dose is not zero.",
            ),
        }
    if prior_dose is None:
        return {
            "key": "dose",
            "matches": None,
            "text": i18n.tr(
                f"La suma de las dosis del historial es {_msv(total)}; el perfil no declara dosis "
                "de carrera previa, y la suma no la sustituye: la escala de carrera sigue sin "
                "ella.",
                f"The sum of the doses in the history is {_msv(total)}; the profile does not "
                "declare a prior career dose, and the sum does not replace it: the career scale "
                "carries on without it.",
            ),
        }
    if abs(total - prior_dose) < DOSE_MATCH_TOLERANCE_MSV:
        return {
            "key": "dose",
            "matches": True,
            "text": i18n.tr(
                f"La suma de las dosis del historial ({_msv(total)}) casa con la dosis de carrera "
                f"previa del perfil ({_msv(prior_dose)}).",
                f"The sum of the doses in the history ({_msv(total)}) matches the prior career "
                f"dose of the profile ({_msv(prior_dose)}).",
            ),
        }
    return {
        "key": "dose",
        "matches": False,
        "text": i18n.tr(
            f"La suma de las dosis del historial ({_msv(total)}) no casa con la dosis de carrera "
            f"previa del perfil ({_msv(prior_dose)}). La escala de carrera sigue usando la del "
            "perfil; no se corrige ninguna de las dos: lo puede revisar quien las declaró.",
            f"The sum of the doses in the history ({_msv(total)}) does not match the prior "
            f"career dose of the profile ({_msv(prior_dose)}). The career scale still uses the "
            "one in the profile; neither is corrected: whoever declared them can review it.",
        ),
    }


def _overlap_check(
    missions: Sequence[PriorMission], current_start: dt.date | None
) -> list[dict[str, Any]]:
    """El aviso de una misión previa que se solapa con la actual, o nada.

    `check` lo rechaza al firmar, con el inicio de misión de la configuración de ese momento. Un
    historial firmado antes de esa regla, o con otro inicio (si después se adelanta
    `EMMA_MISSION_START`), puede quedar solapado. Al leer no se rechaza —un asiento firmado bien
    entonces no se vuelve ilegible (`decode`)—, pero se dice (§5.37.11, «Queda»; §5.38.10). Sin
    solape no se añade nada: no es un cotejo con el perfil, es un aviso.
    """
    if current_start is None:
        return []
    late = [item for item in missions if overlaps_current(item, current_start)]
    if not late:
        return []
    names = ", ".join(
        i18n.tr(
            f"«{item.name}» (termina el {item.end.isoformat()})",
            f"«{item.name}» (ends on {item.end.isoformat()})",
        )
        for item in late
    )
    one = len(late) == 1
    return [{
        "key": "overlap",
        "matches": False,
        "text": i18n.tr(
            f"{'La misión' if one else 'Las misiones'} {names} "
            f"{'termina' if one else 'terminan'} después del inicio de la misión en curso "
            f"({current_start.isoformat()}): {'se solapa' if one else 'se solapan'} con ella. Al "
            "declarar un historial eso se rechaza; este se firmó antes de esa regla o con otro "
            "inicio de misión, y se lee igual. No se corrige: lo puede revisar quien lo declaró.",
            f"{'Mission' if one else 'Missions'} {names} {'ends' if one else 'end'} after the "
            f"start of the current mission ({current_start.isoformat()}): "
            f"{'it overlaps' if one else 'they overlap'} with it. When a history is declared "
            "that is rejected; this one was signed before that rule or with another mission "
            "start, and it is read all the same. It is not corrected: whoever declared it can "
            "review it.",
        ),
    }]


def describe(
    history: dict[str, Any] | None, profile: dict[str, Any], *, current_start: dt.date | None
) -> dict[str, Any]:
    """Lo declarado vigente y su cotejo con el perfil, con las frases ya escritas.

    `history` es el asiento vigente (`api/mission.latest_mission_history`, con `missions` ya
    leído) o None; `profile`, lo que da `api/mission.latest_profile`. No lee ni cambia nada más.
    `limits` son los topes de `check`, para que el formulario no los copie.

    `current_start` es el inicio de la misión en curso (`Settings.mission_start`), obligatorio
    por nombre como en `record_mission_history`: con él, una misión previa que se solapa con la
    actual se avisa en `checks` (`_overlap_check`). `None` solo si quien llama no lo conoce.
    """
    limits = {"missions": MAX_PRIOR_MISSIONS, "name_length": MAX_NAME_LENGTH}
    if history is None:
        return {
            "declared": False,
            "scope": i18n.loc(SCOPE),
            "limits": limits,
            "missions": [],
            "text": i18n.tr(
                "Sin historial misión a misión declarado.",
                "No mission-by-mission history declared.",
            ),
            "checks": [],
        }
    missions: list[PriorMission] = history["missions"]
    known = [item.dose_msv for item in missions if item.dose_msv is not None]
    total = math.fsum(known)
    missing = len(missions) - len(known)
    return {
        "declared": True,
        "scope": i18n.loc(SCOPE),
        "limits": limits,
        "days_basis": i18n.loc(DAYS_BASIS),
        "missions": [
            {
                "name": item.name,
                "start": item.start.isoformat(),
                "end": item.end.isoformat(),
                "days": item.days,
                "dose_msv": item.dose_msv,
            }
            for item in missions
        ],
        "text": (
            i18n.tr("Declarado: ninguna misión previa.", "Declared: no prior missions.")
            if not missions
            else i18n.tr(
                f"Declaradas {_count(len(missions))} previas.",
                f"Declared: {len(missions)} prior mission{'' if len(missions) == 1 else 's'}.",
            )
        ),
        "dose_sum_msv": total if known else None,
        "missions_without_dose": missing,
        "declared_by": history["declared_by"],
        "recorded": history["recorded"],
        "ledger_index": history["ledger_index"],
        "checks": [
            _missions_check(missions, profile["prior_missions"]),
            _dose_check(total, missing, profile["prior_career_dose_msv"]),
            *_overlap_check(missions, current_start),
        ],
    }
