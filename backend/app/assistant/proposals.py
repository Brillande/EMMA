"""Lo que el asistente propone escribir: el cuerpo exacto de la ruta del formulario, sin firmar.

Por qué existe: «EMMA, apunta que me duele la rodilla» no puede firmar nada. El asistente prepara
el cuerpo que aceptaría la ruta de siempre de ese formulario, lo comprueba con las MISMAS reglas que
ella antes de devolverlo y lo lee en voz alta; la firma la hace la interfaz por esa misma ruta,
cuando la persona dice «confirmo» o pulsa Confirmar, con el nombre del operador de la consola. El
modelo nunca escribe en el registro (invariantes 4 y 7).

La propuesta va SIN el campo de quien firma (lo pone la interfaz):

  * `diary_entry` → `POST /api/diary/entries`, firma `recorded_by`. Sin campo de origen.
  * `pain_report` → `POST /api/pain/reports`, firma `reported_by`. Lleva `note_origin`
    «asistente-confirmada» y, como nota, las palabras de la persona tal cual las dijo.
  * `acknowledge_alert` → `POST /api/alerts/acknowledge`, firma `acknowledged_by`. Sin origen.
  * `mission_level` → `POST /api/mission-mode`, firma `declared_by`. Sin origen.
  * `mission_profile` → `POST /api/mission/profile`, firma `declared_by`. Sin origen. El entorno
    sale de lo que dijo la persona (`catalog.profile_for`) o del modelo, y se comprueba contra el
    vigente con las reglas del almacén.
  * `safe_mode` → `POST /api/safe-mode`, firma `declared_by`. Sin origen.

Donde la ruta no tiene campo de origen no se inventa uno: lo firmado no distingue si llegó por
voz o por teclado, y se dice así en `compliance/software-safety-classification.md` §2.2.

NADA QUE LA PERSONA NO HAYA DICHO. Un valor del diario, una intensidad, un tipo de dolor, un
alimento o el motivo de un cambio de nivel tienen que estar en lo que dijo la persona: si el
modelo los pone y no están, la propuesta no sale y se pregunta por ellos. El nivel y el instante
de la alerta que se reconoce salen del estado que ve la consola, no del modelo.

EL IDIOMA (2026-11-15). Lo que se LEE de la propuesta va en el idioma de la petición. Lo que se
FIRMARÍA no cambia con él: el cuerpo lleva ids y cifras, la nota de un informe de dolor son las
palabras de la persona tal cual las dijo, en el idioma en que las dijo, y `ORIGIN` es un
identificador que se guarda, no un texto que se traduce (`compliance/record-integrity.md`,
«Idioma del registro»).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from app.api.diary import DIARY_SOURCE, diary_keys
from app.assistant.catalog import plain, spoken_numbers, zone_said
from app.assistant.context import AssistantContext
from app.core import display, i18n, mission_modes, mission_profile_changes
from app.core.config import Settings
from app.core.i18n import tr
from app.core.storage import ObservationStore
from app.ingest import food_item
from app.ingest.codes import Domain, get
from app.ingest.fhir import ObservationType, observation
from app.pain.catalog import CHARACTERS, ZONES, validate_zones
from app.text_guard import normalize

ORIGIN = "asistente-confirmada"
NOTE_MAX = 1000
# El tope del motivo en `MissionModeIn` y `SafeModeIn`.
REASON_MAX = 300
# Un nombre de relleno con que se pasan las comprobaciones que exigen «una persona con nombre»: la
# propuesta no lleva firmante, y el de verdad lo pone la interfaz.
_PLACEHOLDER_SIGNER = "propuesta"
NOT_SIGNED = "No se ha firmado nada: di «confirmo» o pulsa Confirmar para firmarlo"
GROUND_REFUSAL = (
    "Desde la consola de Tierra no preparo escrituras por voz: el diario, el dolor, los "
    "reconocimientos, el nivel de misión, el entorno de la misión y el modo seguro se firman a "
    "bordo."
)
i18n.en(NOT_SIGNED, "Nothing has been signed: say «confirm» or press Confirm to sign it")
i18n.en(GROUND_REFUSAL, (
    "From the Ground console I do not prepare entries by voice: the diary, pain, "
    "acknowledgements, the mission level, the mission environment and safe mode are signed on "
    "board."
))


@dataclass
class Proposal:
    body: dict[str, Any] | None
    reply: str


def _said(word: str, words: str) -> bool:
    """¿Dijo la persona esta palabra? Por su raíz (cinco letras), para que valga el género."""
    stem = normalize(word)[:5]
    return bool(stem) and f" {stem}" in words


def _from_user(reason: str | None, words: str) -> str:
    """El motivo solo si son palabras de la persona: el asistente no redacta asientos."""
    if not reason or len(reason) > REASON_MAX:
        return ""
    tokens = [token for token in plain(reason).split() if len(token) >= 3]
    return reason.strip() if tokens and all(f" {token}" in words for token in tokens) else ""


def _closing(operator: str | None) -> str:
    who = (tr(f" Firmará {operator}.", f" {operator} will sign.") if operator else
           tr(" Falta quién firma: el operador de la consola.",
              " The signer is missing: the console operator."))
    return f"{i18n.loc(NOT_SIGNED)}.{who}"


def _diary(args: dict[str, Any], text: str, subject: str, settings: Settings,
           operator: str | None) -> Proposal:
    key = str(args["key"])
    if key not in diary_keys():
        return Proposal(None, tr(f"«{key}» no es un indicador del registro diario.",
                                 f"«{key}» is not a daily log indicator."))
    code = get(key)
    value = float(args["value"])
    if value not in spoken_numbers(text):
        return Proposal(None, tr(f"Para anotar {code.display_es} necesito el valor: dímelo y lo "
                                 "preparo.",
                                 f"To log {code.display_es} I need the value: tell me and I will "
                                 "prepare it."))
    words = plain(text)
    food_said = args.get("food")
    food = str(food_said) if food_said and normalize(str(food_said)) in words else None
    try:
        food = food_item.accept(key, food, require=True)
        observation(
            key, value, dt.datetime.now(dt.UTC), subject, DIARY_SOURCE,
            observation_type=ObservationType.MEASURED,
            evidence_context=settings.deployment_context,
            recorded_by=_PLACEHOLDER_SIGNER, food=food,
        )
    except ValueError as exc:
        return Proposal(None, tr(f"No puedo preparar esa anotación: {exc}.",
                                 f"I cannot prepare that entry: {exc}."))
    body: dict[str, Any] = {"key": key, "value": value, "subject": subject}
    if food is not None:
        body["food"] = food
    shown = f"{display.number(value, display.decimals_for(key))} {display.unit(code.unit)}"
    food_text = tr(f", alimento «{food}»", f", food «{food}»") if food else ""
    return Proposal(body, tr(f"Propuesta para el diario: {code.display_es}, {shown.strip()}"
                             f"{food_text}. {_closing(operator)}",
                             f"Proposal for the diary: {code.display_es}, {shown.strip()}"
                             f"{food_text}. {_closing(operator)}"))


def _pain(args: dict[str, Any], text: str, subject: str, operator: str | None) -> Proposal:
    zone = str(args["zone"])
    intensity = int(args["intensity"])
    words = plain(text)
    item = ZONES[zone]
    named = [token for token in plain(item.display).split() if len(token) >= 3]
    spoken_as = zone_said(zone, words)
    if spoken_as is not None:
        # La persona nombró la zona con sus palabras del catálogo («my left knee»): cuentan esas,
        # llegue el nombre de la zona en el idioma que llegue.
        named = spoken_as.split()
    if not named or not all(_said(token, words) for token in named):
        return Proposal(None, tr("¿Dónde te duele exactamente? Dime la zona y el lado.",
                                 "Where exactly does it hurt? Tell me the area and the side."))
    if float(intensity) not in spoken_numbers(text):
        return Proposal(None, tr(f"¿Cuánto te duele en {item.display.lower()}, de 1 a 10?",
                                 f"How much does it hurt in {item.display.lower()}, from 1 to "
                                 "10?"))
    characters = [str(key) for key in args.get("characters") or []
                  if _said(CHARACTERS[str(key)].display, words)]
    problems = validate_zones([(zone, intensity, characters)])
    if problems:
        return Proposal(None, tr("No puedo preparar ese informe: ",
                                 "I cannot prepare that report: ") + "; ".join(problems) + ".")
    body = {
        "zones": [{"zone": zone, "intensity": intensity, "characters": characters}],
        "subject": subject,
        "note": text.strip()[:NOTE_MAX],
        "note_origin": ORIGIN,
    }
    kinds = ", ".join(CHARACTERS[key].display.lower() for key in characters)
    kinds_text = f", {kinds}" if kinds else ""
    return Proposal(body, tr(f"Propuesta de informe de dolor: {item.display.lower()}, "
                             f"{intensity} de 10{kinds_text}. {_closing(operator)}",
                             f"Proposed pain report: {item.display.lower()}, "
                             f"{intensity} out of 10{kinds_text}. {_closing(operator)}"))


def _acknowledge(args: dict[str, Any], context: AssistantContext, subject: str,
                 operator: str | None) -> Proposal:
    domain = str(args["domain"])
    name = Domain(domain).display
    alert = next((item for item in context.alerts
                  if item["domain"] == domain and not item.get("acknowledged")), None)
    if alert is None or context.reference_time is None:
        return Proposal(None, tr(f"No hay ninguna alerta de {name} sin reconocer.",
                                 f"There is no unacknowledged {name} alert."))
    body = {
        "subject": subject,
        "domain": domain,
        "level": str(alert["level"]),
        "reference_time": context.reference_time.isoformat(),
    }
    return Proposal(body, tr(f"Propuesta: reconocer la alerta de {name}. Reconocerla detiene su "
                             f"parpadeo; no la oculta ni la resuelve. {_closing(operator)}",
                             f"Proposal: acknowledge the {name} alert. Acknowledging it stops "
                             f"its blinking; it does not hide or resolve it. "
                             f"{_closing(operator)}"))


def _mission_level(args: dict[str, Any], text: str, store: ObservationStore,
                   operator: str | None) -> Proposal:
    level = str(args["level"])
    reason = _from_user(args.get("reason"), plain(text))
    current = str(store.mission_mode(None)["level"])
    try:
        mission_modes.check_change(current, level, reason, _PLACEHOLDER_SIGNER)
    except ValueError as exc:  # también `MissionModeConflict`
        return Proposal(None, _no_change(exc))
    shown = mission_modes.vocabulary().levels[level].display
    reason_text = _reason_text(reason)
    return Proposal({"level": level, "reason": reason},
                    tr(f"Propuesta: nivel de misión {shown}{reason_text}. {_closing(operator)}",
                       f"Proposal: mission level {shown}{reason_text}. {_closing(operator)}"))


def _no_change(exc: ValueError) -> str:
    return tr(f"No puedo preparar ese cambio: {exc}.", f"I cannot prepare that change: {exc}.")


def _reason_text(reason: str) -> str:
    """El motivo, con las palabras de la persona tal cual: no se traduce."""
    return tr(f", motivo «{reason}»", f", reason «{reason}»") if reason else ""


def _mission_profile(args: dict[str, Any], text: str, store: ObservationStore,
                     settings: Settings, operator: str | None) -> Proposal:
    profile = str(args["profile"])
    reason = _from_user(args.get("reason"), plain(text))
    current = str(store.mission_profile(None, settings.mission_profile)["id"])
    try:
        mission_profile_changes.check_change(current, profile, _PLACEHOLDER_SIGNER)
    except ValueError as exc:  # también `MissionProfileConflict`
        return Proposal(None, _no_change(exc))
    shown = mission_profile_changes.display(profile)
    reason_text = _reason_text(reason)
    return Proposal({"profile": profile, "reason": reason},
                    tr(f"Propuesta: entorno de la misión {shown}{reason_text}. Es descriptivo: no "
                       f"cambia niveles, alertas ni riesgo. {_closing(operator)}",
                       f"Proposal: mission environment {shown}{reason_text}. It is descriptive: "
                       f"it changes no levels, alerts or risk. {_closing(operator)}"))


def _safe_mode(args: dict[str, Any], text: str, store: ObservationStore,
               operator: str | None) -> Proposal:
    active = bool(args["active"])
    reason = _from_user(args.get("reason"), plain(text))
    if bool(store.safe_mode()["active"]) == active:
        return Proposal(None, tr("El modo seguro ya está ", "Safe mode is already ") + (
            tr("activo.", "active.") if active else tr("levantado.", "lifted.")))
    if active and not any(char.isalnum() for char in reason):
        return Proposal(None, tr("Activar el modo seguro exige un motivo: dímelo con tus palabras.",
                                 "Activating safe mode requires a reason: tell me in your own "
                                 "words."))
    action = tr("activar", "activate") if active else tr("levantar", "lift")
    reason_text = _reason_text(reason)
    return Proposal({"active": active, "reason": reason},
                    tr(f"Propuesta: {action} el modo seguro{reason_text}. {_closing(operator)}",
                       f"Proposal: {action} safe mode{reason_text}. {_closing(operator)}"))


def propose(
    intent: str,
    args: dict[str, Any],
    *,
    text: str,
    context: AssistantContext,
    store: ObservationStore,
    settings: Settings,
    operator: str | None,
) -> Proposal:
    """El cuerpo para la ruta de `intent`, ya comprobado, o por qué no sale y qué falta."""
    made = _checked(intent, args, text=text, context=context, store=store, settings=settings,
                    operator=operator)
    # Una frase fija (constante de módulo) sale aquí en el idioma de la petición; las que se
    # componen con datos ya lo traen. El cuerpo no se toca.
    return Proposal(made.body, i18n.loc(made.reply))


def _checked(
    intent: str,
    args: dict[str, Any],
    *,
    text: str,
    context: AssistantContext,
    store: ObservationStore,
    settings: Settings,
    operator: str | None,
) -> Proposal:
    if context.console != "crew":
        return Proposal(None, GROUND_REFUSAL)
    subject = context.subject
    missing = {
        "diary_entry": ("key", "value"), "pain_report": ("zone", "intensity"),
        "acknowledge_alert": ("domain",), "mission_level": ("level",),
        "mission_profile": ("profile",), "safe_mode": ("active",),
    }[intent]
    if any(name not in args for name in missing):
        return Proposal(None, {
            "diary_entry": tr(
                "El diario anota indicadores con un valor, como el ánimo, los síntomas o el "
                "apetito: ¿cuál quieres anotar y con qué valor?",
                "The diary logs indicators with a value, such as mood, symptoms or appetite: "
                "which one do you want to log, and with what value?"
            ),
            "pain_report": tr("¿Dónde te duele y cuánto, de 1 a 10?",
                              "Where does it hurt and how much, from 1 to 10?"),
            "acknowledge_alert": tr("¿Qué alerta quieres reconocer?",
                                    "Which alert do you want to acknowledge?"),
            "mission_level": tr("¿A qué nivel de misión: ", "To which mission level: ") + ", ".join(
                level.display for level in mission_modes.vocabulary().levels.values()
            ) + "?",
            "mission_profile": tr("¿Qué entorno de la misión declaro: ",
                                  "Which mission environment do I declare: ") + ", ".join(
                item["display"] for item in mission_profile_changes.view(
                    store.mission_profile(None, settings.mission_profile)
                )["profiles"]
            ) + "?",
            "safe_mode": tr("¿Activo o levanto el modo seguro?",
                            "Do I activate or lift safe mode?"),
        }[intent])
    if intent == "diary_entry":
        return _diary(args, text, subject, settings, operator)
    if intent == "pain_report":
        return _pain(args, text, subject, operator)
    if intent == "acknowledge_alert":
        return _acknowledge(args, context, subject, operator)
    if intent == "mission_level":
        return _mission_level(args, text, store, operator)
    if intent == "mission_profile":
        return _mission_profile(args, text, store, settings, operator)
    return _safe_mode(args, text, store, operator)
