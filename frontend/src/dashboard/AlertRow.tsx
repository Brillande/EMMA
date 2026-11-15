import { useState, useEffect } from "react";
import { AlertDetailView } from "./AlertDetailView";

import { Command } from "../components/Command";
import { DomainName } from "../components/DomainName";
import { FieldLabel } from "../components/FieldLabel";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import {
  type Alert,
  acknowledgementMark,
  annunciationMark,
  earthArrival,
  resolutionMark,
} from "../lib/alerts";
import {
  type AlertDismissal,
  type AlertState,
  type CrewStatus,
  type DismissalReasons,
  type LinkSync,
  api,
} from "../lib/api";
import { formatMet, missionElapsedSeconds } from "../lib/format";
import { tr } from "../lib/i18n";
import { domainLabel } from "../lib/levels";
import { commsMark, commsStatusOf } from "../lib/commsStatus";
import { MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";

/** Lo que la consola puede hacer con una alerta. Todo acaba en el ledger. */
export interface AlertActions {
  /** "En arreglo" o "resuelto" (estados de Polaris `salud.py`); no cambia el calculo. */
  resolve: (alert: Alert, by: string, state: "en_arreglo" | "resuelto", note: string) => Promise<void>;
  /** Descartar esta alerta, con un motivo del vocabulario del backend; no cambia el calculo. */
  dismiss: (alert: Alert, by: string, reason: string, note: string) => Promise<void>;
  acknowledge: (alert: Alert, by: string) => Promise<void>;
  suppress: (alert: Alert, by: string, reason: string, minutes: number) => Promise<void>;
  inhibit: (alert: Alert, by: string, reason: string, hours: number) => Promise<void>;
  enable: (alert: Alert, by: string, reason: string) => Promise<void>;
}

// Duraciones que se ofrecen. Los topes los impone el backend: suprimir, 12 h como
// mucho y 1 h si es critica; inhibir, 7 dias y nunca en critico.
const SUPPRESS_MINUTES = [15, 30, 60, 120, 240, 720];
const CRITICAL_SUPPRESS_MINUTES = [15, 30, 60];
const INHIBIT_HOURS = [1, 4, 12, 24, 72, 168];

type Pending = "suppress" | "inhibit" | "enable" | null;

/**
 * Una alerta con lo que el retardo significa para ella y lo que se puede hacer.
 *
 * Silenciar una alarma clinica es un mando peligroso (NASA-STD-3001 Vol 2,
 * F.4.3.2): exige dos acciones independientes —abrir el formulario y confirmar—,
 * motivo obligatorio, y el boton de confirmacion lleva cinta de peligro. Una alerta
 * silenciada **sigue en la lista**, con su estado de anuncio (F.6.4): deja de
 * reclamar atencion, no de existir.
 */
const RESOLUTION_LABEL = {
  detectado: tr("Detectada", "Detected"),
  en_arreglo: tr("En arreglo", "Being fixed"),
  resuelto: tr("Resuelta", "Resolved"),
};

/**
 * Lo que pasa despues de reconocer: quien se ocupa y cuando lo da por resuelto. Una alerta
 * "resuelta" cuyos datos siguen fuera de rango sigue en la lista: el estado es de la persona, el
 * calculo no cambia. Sin color propio: es informacion, no una señal nueva; el pictograma de cada
 * estado (`lib/alerts.ts`) va junto a su palabra.
 */
function Resolution({
  alert,
  state,
  by,
  actions,
  onError,
}: {
  alert: Alert;
  state: AlertState | undefined;
  by: string;
  actions: AlertActions;
  onError: (outcome: RequestOutcome) => void;
}) {
  const [note, setNote] = useState("");
  // Descartada, lo último que se dijo es el descarte (lo dice su propia línea): el estado declarado
  // antes no se enseña como vigente, y lo que se ofrece es volver a ocuparse de ella.
  const dismissed = state?.dismissal != null;
  const current = dismissed ? "detectado" : (state?.resolution?.state ?? "detectado");
  const next = current === "detectado" ? "en_arreglo" : current === "en_arreglo" ? "resuelto" : null;
  const send = (target: "en_arreglo" | "resuelto") => {
    actions
      .resolve(alert, by, target, note.trim())
      .then(() => setNote(""))
      .catch((cause: unknown) => onError(requestOutcome(cause)));
  };
  return (
    <span className="resolution">
      {!dismissed && (
        <span className="secondary">
          {" · "}
          <Mark pictogram={resolutionMark(current).pictogram}>{RESOLUTION_LABEL[current]}</Mark>
          {state?.resolution?.declared_by ? ` (${state.resolution.declared_by})` : ""}
          {state?.resolution?.note ? `: ${state.resolution.note}` : ""}
          {/* Con qué reglas se firmó el estado declarado (§5.39.9): la frase del backend, sin color. */}
          {state?.resolution?.rules ? ` · ${state.resolution.rules.text}` : ""}
        </span>
      )}
      {next !== null && (
        <>
          <input
            aria-label={tr("Nota", "Note")}
            placeholder={tr("nota", "note")}
            value={note}
            maxLength={300}
            onChange={(event) => setNote(event.target.value)}
          />
          <Command
            concept={next === "en_arreglo" ? "inRepair" : "resolved"}
            disabled={by.length === 0}
            onClick={() => send(next)}
          >
            {next === "en_arreglo" ? tr("En arreglo", "Being fixed") : tr("Resuelta", "Resolved")}
          </Command>
        </>
      )}
    </span>
  );
}

/**
 * La alerta descartada sigue en la lista: esto lo dice junto a ella, con quién y por qué, tal
 * cual lo devuelve el backend (§5.37.6), y con qué reglas se firmó (§5.39.9). Sin color propio,
 * como los demás estados: el de la fila sigue siendo el del nivel, que el descarte no cambia.
 */
function DismissedNote({ dismissal }: { dismissal: AlertDismissal }) {
  return (
    <p className="dismissal secondary">
      <Mark pictogram={uiPictogram("dismiss")}>{tr("Descartada", "Dismissed")}</Mark>{tr(" por ", " by ")}{dismissal.declared_by}:{" "}
      {dismissal.reason_display}
      {dismissal.note ? ` (${dismissal.note})` : ""}
      {dismissal.rules ? ` · ${dismissal.rules.text}` : ""}
    </p>
  );
}

/**
 * Descartar (la «HUMAN DECISION / Dismiss» de la conversación de ideación): dos pasos —abrir y
 * confirmar—, un motivo de la lista del backend y nota cuando el motivo la exige. Los motivos y la
 * frase que explica lo que el descarte es se piden al abrir, no se redactan aquí.
 */
function DismissForm({
  alert,
  by,
  actions,
  onClose,
  onError,
}: {
  alert: Alert;
  by: string;
  actions: AlertActions;
  onClose: () => void;
  onError: (outcome: RequestOutcome) => void;
}) {
  const [reasons, setReasons] = useState<DismissalReasons | null>(null);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  useEffect(() => {
    let live = true;
    api
      .dismissalReasons()
      .then((loaded) => {
        if (!live) return;
        // Sin motivo elegido de antemano: el que se firma lo elige la persona.
        setReasons(loaded);
      })
      .catch((cause: unknown) => {
        if (live) onError(requestOutcome(cause));
      });
    return () => {
      live = false;
    };
  }, [onError]);
  if (reasons === null) {
    // Mientras llegan los motivos, o si no llegaron (el error se dice debajo), se puede cerrar.
    return (
      <div className="silence-form">
        <Command concept="cancel" onClick={onClose}>
          {tr("Cancelar", "Cancel")}
        </Command>
      </div>
    );
  }
  const chosen = reasons.reasons.find((item) => item.code === reason);
  const missingNote = chosen?.note_required === true && note.trim().length === 0;
  // Un clic, un asiento: mientras la firma va y vuelve, el botón no firma otra vez.
  const confirm = () => {
    setSending(true);
    actions
      .dismiss(alert, by, reason, note.trim())
      .then(onClose)
      .catch((cause: unknown) => {
        setSending(false);
        onError(requestOutcome(cause));
      });
  };
  return (
    <div className="silence-form">
      <FieldLabel concept="reason">
        {tr("Motivo", "Reason")}{" "}
        <select value={reason} onChange={(event) => setReason(event.target.value)}>
          <option value="" disabled>
            {tr("elige un motivo", "choose a reason")}
          </option>
          {reasons.reasons.map((item) => (
            <option key={item.code} value={item.code}>
              {item.display}
            </option>
          ))}
        </select>
      </FieldLabel>
      <FieldLabel concept="note">
        {tr("Nota", "Note")}{" "}
        <input
          value={note}
          maxLength={300}
          onChange={(event) => setNote(event.target.value)}
          placeholder={chosen?.note_required === true ? tr("obligatoria con este motivo", "required with this reason") : tr("opcional", "optional")}
        />
      </FieldLabel>
      <p className="secondary">{reasons.basis}</p>
      <div className="summary">
        <Command
          concept="confirm"
          disabled={sending || by.length === 0 || reason.length === 0 || missingNote}
          onClick={confirm}
        >
          {tr("Confirmar descarte", "Confirm dismissal")}
        </Command>
        <Command concept="cancel" onClick={onClose}>
          {tr("Cancelar", "Cancel")}
        </Command>
      </div>
    </div>
  );
}

export function AlertRow({
  alert,
  state,
  status,
  operator,
  actions,
  sync = null,
}: {
  alert: Alert;
  state: AlertState | undefined;
  status: CrewStatus;
  operator: string;
  actions: AlertActions;
  /** El enlace con Tierra simulado: caído, no se sabe cuándo verá Tierra la alerta (`earthArrival`). */
  sync?: Pick<LinkSync, "state"> | null;
}) {
  const [pending, setPending] = useState<Pending>(null);
  const [reason, setReason] = useState("");
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const [dismissing, setDismissing] = useState(false);
  const dismissal = state?.dismissal ?? null;

  const at = new Date(status.data.reference_time);
  const arrival = earthArrival(at, status.comms, sync);
  const comms = commsStatusOf(status);
  const met = (date: Date) => formatMet(missionElapsedSeconds(status.mission.start, date));

  const annunciation = state?.annunciation ?? "normal";
  const acknowledged = state?.acknowledged ?? false;
  const silenced = annunciation !== "normal";
  const by = operator.trim();
  const critical = alert.level === "critical";

  const run = (work: Promise<void>) => {
    setError(null);
    work
      .then(() => {
        setPending(null);
        setReason("");
      })
      .catch((cause: unknown) => setError(requestOutcome(cause)));
  };

  const open = (next: Pending) => {
    setDismissing(false);
    setPending(next);
    setReason("");
    setError(null);
    setDuration(next === "inhibit" ? INHIBIT_HOURS[3] ?? 24 : 60);
  };

  const confirm = () => {
    if (pending === "suppress") run(actions.suppress(alert, by, reason.trim(), duration));
    else if (pending === "inhibit") run(actions.inhibit(alert, by, reason.trim(), duration));
    else if (pending === "enable") run(actions.enable(alert, by, reason.trim()));
  };

  const durations =
    pending === "inhibit" ? INHIBIT_HOURS : critical ? CRITICAL_SUPPRESS_MINUTES : SUPPRESS_MINUTES;
  const unit = pending === "inhibit" ? "h" : "min";

  return (
    <div className={`alert-row${silenced ? " silenced" : ""}`}>
      <div>
        {/* Encabezado de nivel 3 bajo «Alertas activas» (h2): con el lector de pantalla se salta de
            alerta en alerta con la tecla de encabezados, y cada una se nombra por su nivel y su
            dominio. Con `role` y no con `<h3>`, para no tocar la maqueta de la fila (§5.41). */}
        <span role="heading" aria-level={3}>
          <LevelBadge level={alert.level} flashing={!acknowledged && !silenced} />{" "}
          <strong>
            <DomainName domain={alert.domain} />
          </strong>
        </span>
        {silenced && state !== undefined && (
          <p className="annunciation">
            <Mark pictogram={annunciationMark(annunciation).pictogram}>
              {annunciation === "suppressed" ? tr("Suprimida", "Suppressed") : tr("Inhibida", "Inhibited")}
            </Mark>{" "}
            {tr("hasta", "until")}{" "}
            <span className="num">
              {state.silenced_until !== null ? met(new Date(state.silenced_until)) : "—"}
            </span>{" "}
            {tr("por ", "by ")}{state.silenced_by}: {state.silenced_reason}
          </p>
        )}
        {dismissal !== null && <DismissedNote dismissal={dismissal} />}
        <ul className="drivers">
          {alert.drivers.map((driver) => (
            <li key={driver}>{driver}</li>
          ))}
        </ul>
        {state?.detail !== undefined && (
          <AlertDetailView
            detail={state.detail}
            level={alert.level}
            status={status}
            alertTime={state.time_to_action}
          />
        )}
        {/* El retardo con Tierra lleva el signo del tiempo de luz, el de la franja; sin
            efemérides, la marca de dato ausente en su lugar (tabla F.5-1). */}
        {arrival.kind === "link-down" ? (
          <p className="earth">
            {/* Con el enlace simulado caído, tampoco: sale cuando se declare restablecido (lógica 6). */}
            <MarkOf mark={MISSING_MARK}>
              {tr("Enlace con Tierra caído: no se sabe cuándo lo verá Tierra.", "Link to Earth down: it is not known when Earth will see it.")}
            </MarkOf>
          </p>
        ) : arrival.kind === "no-ephemeris" ? (
          <p className="earth">
            {/* Sin retardo, lo que diga el backend (`comms_status`, 2026-11-11): con un perfil sin
                objetivo de efemérides no falta nada (gris, su frase); si de verdad falta, cian. */}
            {comms.state === "not_applicable" ? (
              <MarkOf mark={commsMark(comms.state)}>{comms.text}</MarkOf>
            ) : (
              <MarkOf mark={commsMark(comms.state)}>{comms.word}{tr(": no se sabe cuándo lo verá Tierra.", ": it is not known when Earth will see it.")}</MarkOf>
            )}
          </p>
        ) : (
          <p className="earth secondary">
            <Mark pictogram={uiPictogram("lightTime")}>
              {tr("Tierra lo sabrá a ", "Earth will know at ")}<span className="num">{met(arrival.timeline.earthKnowsAt)}</span>
              {tr(" · su respuesta no puede llegar antes de", " · its reply cannot arrive before")}{" "}
              <span className="num">{met(arrival.timeline.earliestReplyAt)}</span>
            </Mark>
          </p>
        )}

        {pending !== null && (
          <div className="silence-form">
            <FieldLabel concept="reason">
              {tr("Motivo", "Reason")}{" "}
              <input
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
                placeholder={
                  pending === "enable" ? tr("p. ej. sensor recolocado", "e.g. sensor repositioned") : tr("p. ej. sensor con mal contacto", "e.g. sensor with poor contact")
                }
              />
            </FieldLabel>
            {pending !== "enable" && (
              <FieldLabel concept="during">
                {tr("Durante", "For")}{" "}
                <select value={duration} onChange={(event) => setDuration(Number(event.target.value))}>
                  {durations.map((value) => (
                    <option key={value} value={value}>
                      {value} {unit}
                    </option>
                  ))}
                </select>
              </FieldLabel>
            )}
            {pending === "inhibit" && (
              <p className="secondary">
                {tr("Inhibir deja de anunciar las alertas de ", "Inhibiting stops announcing the alerts of ")}{domainLabel(alert.domain)}
                {tr(
                  " hasta este nivel, también las que aparezcan después. Una escalada se anuncia siempre.",
                  " up to this level, including those that appear later. An escalation is always announced.",
                )}
              </p>
            )}
            <div className="summary">
              <Command
                concept="confirm"
                hazard={pending !== "enable"}
                disabled={reason.trim().length === 0 || by.length === 0}
                onClick={confirm}
              >
                {pending === "suppress"
                  ? tr("Confirmar supresión", "Confirm suppression")
                  : pending === "inhibit"
                    ? tr("Confirmar inhibición", "Confirm inhibition")
                    : tr("Confirmar: volver a anunciar", "Confirm: announce again")}
              </Command>
              <Command concept="cancel" onClick={() => setPending(null)}>
                {tr("Cancelar", "Cancel")}
              </Command>
            </div>
          </div>
        )}
        {dismissing && (
          <DismissForm
            alert={alert}
            by={by}
            actions={actions}
            onClose={() => setDismissing(false)}
            onError={setError}
          />
        )}
        {error !== null && (
          <p>
            <MarkOf mark={error.mark}>{tr("No se pudo completar: ", "Could not complete: ")}{error.text}</MarkOf>
          </p>
        )}
      </div>

      <div className="alert-actions">
        {silenced ? (
          <Command concept="enable" disabled={by.length === 0} onClick={() => open("enable")}>
            {tr("Habilitar…", "Enable…")}
          </Command>
        ) : (
          <>
            {acknowledged ? (
              <>
                <span className="secondary">
                  <Mark pictogram={acknowledgementMark(true).pictogram}>
                    {tr("Reconocida por ", "Acknowledged by ")}{state?.acknowledged_by}
                  </Mark>
                  {/* Con qué reglas se firmó el reconocimiento, frente a las de hoy (§5.39.9):
                      la frase del backend tal cual, sin color. Es información, no una señal. */}
                  {state?.acknowledgement_rules ? ` · ${state.acknowledgement_rules.text}` : ""}
                </span>
                <Resolution alert={alert} state={state} by={by} actions={actions} onError={setError} />
                {/* Descartar es una decisión sobre una alerta ya vista: va con los estados de
                    después de reconocer. Una ya descartada no lo vuelve a ofrecer; declarar
                    «en arreglo» o «resuelta» deja el descarte atrás. */}
                {dismissal === null && !dismissing && (
                  <Command
                    concept="dismiss"
                    disabled={by.length === 0}
                    onClick={() => {
                      setError(null);
                      setPending(null);
                      setDismissing(true);
                    }}
                  >
                    {tr("Descartar…", "Dismiss…")}
                  </Command>
                )}
              </>
            ) : (
              <Command
                concept="acknowledge"
                disabled={by.length === 0}
                onClick={() => run(actions.acknowledge(alert, by))}
              >
                {tr("Reconocer", "Acknowledge")}
              </Command>
            )}
            <Command concept="suppress" disabled={by.length === 0} onClick={() => open("suppress")}>
              {tr("Suprimir…", "Suppress…")}
            </Command>
            {/* Un dominio en critico no se puede inhibir: el backend lo rechaza, y la
                interfaz ni lo ofrece. */}
            {!critical && (
              <Command concept="inhibit" disabled={by.length === 0} onClick={() => open("inhibit")}>
                {tr("Inhibir…", "Inhibit…")}
              </Command>
            )}
          </>
        )}
      </div>
    </div>
  );
}
