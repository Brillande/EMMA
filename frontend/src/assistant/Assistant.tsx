import { type FormEvent, type ReactNode, useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState } from "react";

import { Command } from "../components/Command";
import { Mark, MarkOf } from "../components/Mark";
import type { Speaker } from "../components/ReadAloud";
import { type AssistantInfo, type AssistantTurn, assistantApi } from "../lib/api";
import { tr } from "../lib/i18n";
import { LOADING_MARK, type RequestOutcome, UNAVAILABLE_MARK, mark, requestOutcome } from "../lib/marks";
import { storedOperator } from "../lib/operator";
import { uiPictogram } from "../lib/uiMarks";
import { type AssistantEvent, listen } from "./bus";
import { pressControl, visibleControls } from "./controls";
import {
  type IntentEffects,
  type PendingWrite,
  type ProposalField,
  NO_BUTTON,
  confirmationWord,
  executeIntent,
  proposalFields,
  proposalSpeech,
  sendSigned,
  signedRequest,
  toggledModes,
} from "./intents";
import { type ThreadItem, historyOf, memoryScope, remember } from "./memory";
import {
  HOLD_LIMIT_MS,
  IDLE,
  LISTEN_LIMIT_MS,
  TALK_SHORTCUT,
  micOpen,
  talkKey,
  talkStep,
} from "./pushToTalk";
import { type Recording, browserCanRecord, startRecording } from "./recorder";

/**
 * El asistente «EMMA» en la consola: el hilo de la conversación, pulsar y hablar, el campo de
 * texto y la confirmación de lo que se firma (`compliance/hmi-state-of-the-art.md`, subsección del
 * asistente).
 *
 * Por qué así: el usuario pidió (2026-11-03) una EMMA «tipo Jarvis» para toda la interfaz con el
 * modelo local. Lo que contesta lo decide el backend (`POST /api/assistant/turn`), con sus barreras
 * (lenguaje, cifras, no recetar, catálogo); aquí no se redacta texto clínico: se enseña y se dice
 * la `reply` tal cual, con el rótulo del backend cuando la redactó el modelo. Lo que hace la
 * consola con la intención está en `intents.ts`, con lista cerrada. Nada se firma sin «confirmo».
 *
 * El aviso «Micrófono abierto» va en la cabecera del asistente, que está siempre a la vista, en el
 * azul de «aviso» de la tabla F.5-1, como «Cámara encendida».
 *
 * Dónde va (2026-11-04, «poco tablet»): flotaba abajo a la derecha y tapaba el panel que se
 * estaba leyendo. Ahora **reserva su sitio**: abierto, columna acoplada a la derecha en
 * horizontal y hoja de abajo de alto fijo en vertical; cerrado, una barra con el título y «Hablar
 * con EMMA». Lo decide la hoja de estilos por `data-open`; aquí solo se marca el estado.
 */

/** El micrófono abierto: azul, «aviso» de F.5-1, como la cámara encendida (`DisplayControls`). */
export const MIC_ON_MARK = mark(uiPictogram("microphone"), "blue");

export const ASSISTANT_TITLE = tr("EMMA (asistente)", "EMMA (assistant)");

/** Por qué no se puede hablar, en la palabra gris de «no disponible». */
export type TalkUnavailable = "no-voice" | "no-format" | null;

export const TALK_UNAVAILABLE_TEXT: Record<Exclude<TalkUnavailable, null>, string> = {
  "no-voice": tr(
    "Hablar no disponible: el reconocimiento de voz local no está instalado. Escriba la pregunta.",
    "Talking unavailable: local speech recognition is not installed. The question can be typed.",
  ),
  "no-format": tr(
    "Hablar no disponible: este navegador no deja grabar el micrófono (falta AudioWorklet). Escriba la pregunta.",
    "Talking unavailable: this browser cannot record the microphone (AudioWorklet is missing). The question can be typed.",
  ),
};

/** Las intenciones que ya hablan solas: su respuesta no se dice encima. */
export const SPEAKS_ITSELF: ReadonlySet<string> = new Set(["read_status", "read_alerts", "read_panel", "repeat_voice"]);

/**
 * El aviso de lo que el modelo contesta con lo que sabe por su cuenta (`reply_source="general"`):
 * el mismo literal del backend (`label`) que se ve en el hilo, con mayúscula y dos puntos, dicho
 * antes de la respuesta. Así lo que se oye y lo que se ve no se separan (decisión del usuario,
 * 2026-11-03).
 */
export function generalNotice(label: string): string {
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}:`;
}

/** Lo que se dice de una respuesta: tal cual, o con su aviso delante si es conocimiento del modelo. */
export function spokenReply(turn: Pick<AssistantTurn, "reply" | "reply_source" | "label">): string {
  if (turn.reply_source !== "general" || turn.label === null || turn.label === "") return turn.reply;
  return `${generalNotice(turn.label)} ${turn.reply}`;
}

/** Por qué no hay asistente: el motivo del backend, o el de la petición que falló. */
export type AssistantLoad =
  | { state: "loading" }
  | { state: "ready"; info: AssistantInfo }
  | { state: "failed"; outcome: RequestOutcome };

export function talkUnavailable(info: AssistantInfo, recordable: boolean): TalkUnavailable {
  if (!info.voice_available) return "no-voice";
  return recordable ? null : "no-format";
}

/** Lo que pinta el asistente: sin estado propio, para probarlo con `renderToStaticMarkup`. */
export interface AssistantViewProps {
  load: AssistantLoad;
  open: boolean;
  onToggle: () => void;
  thread: readonly ThreadItem[];
  /** El hilo tapado por la privacidad (sigue funcionando; no se lee lo de antes). */
  privacy: boolean;
  mic: boolean;
  busy: boolean;
  talk: TalkUnavailable;
  onTalk: (event: "press" | "release") => void;
  draft: string;
  onDraft: (text: string) => void;
  onSend: () => void;
  pending: { fields: readonly ProposalField[]; signer: string } | null;
  /** Un botón que guarda algo, esperando «confirmo» (`controls.ts`). */
  pendingPress?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
  failure: RequestOutcome | null;
}

function speaker(item: ThreadItem): ReactNode {
  if (item.role === "user") return <Mark pictogram={uiPictogram("person")}>{tr("Tú", "You")}</Mark>;
  return <Mark pictogram={uiPictogram("assistant")}>EMMA</Mark>;
}

const UNSIGNED_PROPOSAL = tr("Propuesta sin firmar", "Unsigned proposal");
const ASSISTANT_UNAVAILABLE = tr("Asistente no disponible: ", "Assistant unavailable: ");

/** Lo que dice el botón del título además del título: qué hace pulsarlo (no solo el estado). */
export const TOGGLE_TEXT = { open: tr("Ocultar", "Hide"), closed: tr("Mostrar", "Show") } as const;

export function AssistantView(props: AssistantViewProps) {
  const { load, open, thread, mic, busy, talk, pending, failure } = props;
  const ready = load.state === "ready" && load.info.available;
  // El hilo tiene alto fijo y se desplaza dentro: lo último dicho queda a la vista, de golpe (nada
  // se anima). Solo al llegar algo nuevo (el hilo se recorta a ocho turnos: cuenta el objeto, no
  // la longitud), no a cada pulsación del campo de texto; y no si la persona ha subido a releer.
  const scroller = useRef<HTMLDivElement | null>(null);
  const atEnd = useRef(true);
  useLayoutEffect(() => {
    const element = scroller.current;
    if (element !== null && atEnd.current) element.scrollTop = element.scrollHeight;
  }, [thread, pending, failure, talk, open]);
  return (
    <aside className="assistant" aria-label={ASSISTANT_TITLE} data-open={open ? "true" : "false"}>
      <div className="assistant-head">
        <button
          type="button"
          className="assistant-toggle"
          aria-expanded={open}
          onClick={() => {
            // Al abrir, el hilo empieza por lo último.
            atEnd.current = true;
            props.onToggle();
          }}
        >
          <Mark pictogram={uiPictogram("assistant")}>{ASSISTANT_TITLE}</Mark>
          <span className="assistant-toggle-state secondary">{open ? TOGGLE_TEXT.open : TOGGLE_TEXT.closed}</span>
        </button>
        {mic && (
          <MarkOf mark={MIC_ON_MARK} className="mic-on">
            {tr("Micrófono abierto", "Microphone open")}
          </MarkOf>
        )}
        {ready && talk === null && (
          <Command
            type="button"
            concept="microphone"
            aria-keyshortcuts={TALK_SHORTCUT}
            aria-pressed={mic}
            disabled={busy && !mic}
            // El puntero queda capturado por el botón mientras se mantiene: si la cabecera se mueve
            // (aparece «Micrófono abierto») o el dedo resbala, no se suelta solo. Se suelta al
            // levantarlo, o si el sistema cancela el gesto o se pierde la captura.
            onPointerDown={(event) => {
              event.preventDefault();
              event.currentTarget.setPointerCapture?.(event.pointerId);
              props.onTalk("press");
            }}
            onPointerUp={() => props.onTalk("release")}
            onPointerCancel={() => props.onTalk("release")}
            onLostPointerCapture={() => props.onTalk("release")}
            onKeyDown={(event) => {
              if ((event.key === " " || event.key === "Enter") && !event.repeat) {
                event.preventDefault();
                props.onTalk("press");
              }
            }}
            onKeyUp={(event) => {
              if (event.key === " " || event.key === "Enter") props.onTalk("release");
            }}
          >
            {tr("Hablar con EMMA", "Talk to EMMA")}
          </Command>
        )}
      </div>
      {open && (
        <div className="assistant-body">
          <div
            className="assistant-scroll"
            ref={scroller}
            onScroll={(event) => {
              const element = event.currentTarget;
              atEnd.current = element.scrollHeight - element.scrollTop - element.clientHeight < 24;
            }}
          >
            {load.state === "loading" && (
              <p className="secondary">
                <MarkOf mark={LOADING_MARK}>{tr("Consultando el asistente…", "Checking the assistant…")}</MarkOf>
              </p>
            )}
            {load.state === "failed" && (
              <p>
                <MarkOf mark={UNAVAILABLE_MARK}>
                  {ASSISTANT_UNAVAILABLE}
                  {load.outcome.text}
                </MarkOf>
              </p>
            )}
            {load.state === "ready" && !load.info.available && (
              <p>
                <MarkOf mark={UNAVAILABLE_MARK}>
                  {ASSISTANT_UNAVAILABLE}
                  {load.info.reason ?? tr("el backend no da el motivo", "the backend gives no reason")}
                </MarkOf>
              </p>
            )}
            {ready && (
              <>
                <ol className={props.privacy ? "assistant-thread privacy-blur" : "assistant-thread"} aria-live="polite">
                  {thread.map((item, index) => (
                    <li key={item.id ?? index} className={`assistant-turn assistant-${item.role}`}>
                      <span className="assistant-who">{speaker(item)}</span>{" "}
                      {/* Lo que el modelo sabe por su cuenta va con su aviso delante, no detrás: se lee
                          antes que la respuesta, igual que se dice. */}
                      {item.source === "general" && item.label != null && item.label !== "" && (
                        <span className="assistant-label assistant-general">{generalNotice(item.label)} </span>
                      )}
                      {item.source === "console" ? <span className="secondary">{item.text}</span> : item.text}
                      {item.source === "model" && item.label != null && item.label !== "" && (
                        <span className="assistant-label secondary"> · {item.label}</span>
                      )}
                    </li>
                  ))}
                </ol>
                {pending !== null && (
                  <section className="assistant-proposal" aria-label={UNSIGNED_PROPOSAL}>
                    <p>
                      <Mark pictogram={uiPictogram("register")}>{UNSIGNED_PROPOSAL}</Mark>
                    </p>
                    <dl className={props.privacy ? "privacy-blur" : undefined}>
                      {pending.fields.map((field) => (
                        <div key={field.name}>
                          <dt>{field.name}</dt>
                          <dd>{field.value}</dd>
                        </div>
                      ))}
                      <div>
                        <dt>{tr("Firma", "Signature")}</dt>
                        <dd>
                          {pending.signer === ""
                            ? tr("sin tripulante en consola", "no crew member at the console")
                            : pending.signer}
                        </dd>
                      </div>
                    </dl>
                    <Command type="button" concept="confirm" disabled={busy} onClick={props.onConfirm}>
                      {tr("Confirmar", "Confirm")}
                    </Command>{" "}
                    <Command type="button" concept="cancel" disabled={busy} onClick={props.onCancel}>
                      {tr("Cancelar", "Cancel")}
                    </Command>
                  </section>
                )}
                {props.pendingPress != null && (
                  <section className="assistant-proposal" aria-label={tr("Botón por pulsar", "Button to press")}>
                    <p>
                      <Mark pictogram={uiPictogram("register")}>
                        {tr("Botón por pulsar, que guarda en el registro", "Button to press, which saves to the ledger")}
                      </Mark>
                    </p>
                    <p>
                      {tr("«", "“")}
                      {props.pendingPress}
                      {tr("»", "”")}
                    </p>
                    <Command type="button" concept="confirm" disabled={busy} onClick={props.onConfirm}>
                      {tr("Confirmar", "Confirm")}
                    </Command>{" "}
                    <Command type="button" concept="cancel" disabled={busy} onClick={props.onCancel}>
                      {tr("Cancelar", "Cancel")}
                    </Command>
                  </section>
                )}
                {failure !== null && (
                  <p>
                    <MarkOf mark={failure.mark}>{failure.text}</MarkOf>
                  </p>
                )}
                {talk !== null && (
                  <p>
                    <MarkOf mark={UNAVAILABLE_MARK}>{TALK_UNAVAILABLE_TEXT[talk]}</MarkOf>
                  </p>
                )}
              </>
            )}
          </div>
          {ready && (
            <>
              <form
                className="assistant-form"
                onSubmit={(event: FormEvent) => {
                  event.preventDefault();
                  // Quien escribe quiere ver su turno y la respuesta, aunque hubiera subido a releer.
                  atEnd.current = true;
                  props.onSend();
                }}
              >
                <label className="assistant-field">
                  <span className="secondary">{tr("Escribir a EMMA", "Write to EMMA")}</span>{" "}
                  <input
                    type="text"
                    className="assistant-input"
                    value={props.draft}
                    autoComplete="off"
                    onChange={(event) => props.onDraft(event.target.value)}
                  />
                </label>{" "}
                <Command type="submit" concept="assistant" disabled={busy || props.draft.trim() === ""}>
                  {tr("Enviar", "Send")}
                </Command>
              </form>
              {talk === null && (
                <p className="secondary shortcut assistant-shortcut">
                  <kbd>{tr("Ctrl+Espacio", "Ctrl+Space")}</kbd>
                  {tr(" mantener para hablar", " hold to talk")}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </aside>
  );
}

/** Qué hace el asistente con cada evento del bus. */
export interface BusHandlers {
  audio: (audio: Blob) => void;
  listen: () => void;
  /** Un turno de EMMA para el hilo. */
  said: (item: ThreadItem) => void;
}

/**
 * Reparte un evento del bus. `say` lo emite la iniciativa propia (`proactive.ts`) cuando **ya lo ha
 * dicho** en voz alta: aquí solo entra en el hilo, como frase fija y sin rótulo de modelo; volver a
 * decirlo sería oírlo dos veces.
 */
export function routeBusEvent(event: AssistantEvent, handlers: BusHandlers): void {
  if (event.kind === "utterance") handlers.audio(event.audio);
  else if (event.kind === "listen") handlers.listen();
  else handlers.said({ role: "assistant", text: event.text, source: "fixed", label: null });
}

/** Lo que el asistente necesita de la consola. */
export interface AssistantProps {
  console: "crew" | "ground";
  /** El tripulante que se está viendo: el de cada turno y el de cada firma. */
  subject: string;
  privacy: boolean;
  speaker: Speaker;
  /** Lo que hace cada intención de lectura con lo que ya hay en la consola (`intents.ts`). */
  effects: IntentEffects;
  /** Tras firmar, volver a pedir el estado: lo que se ve es lo firmado. */
  onSigned: () => void;
}

/** Lo que dice la consola por su cuenta: rótulos de navegación, nunca texto clínico. */
const SAY_CONFIRM_OR_CANCEL = tr(
  "Hay una propuesta sin firmar. Diga «confirmo» o «cancela».",
  "There is an unsigned proposal. Say “confirm” or “cancel”.",
);
const SIGNED = tr("Firmado en el registro.", "Signed in the ledger.");
const CANCELLED = tr("Propuesta descartada; no se firmó nada.", "Proposal discarded; nothing was signed.");
const PROPOSAL_SHOWN = tr("Hay una propuesta sin firmar en pantalla.", "There is an unsigned proposal on screen.");
const SAY_PRESS_OR_CANCEL = tr(
  "Hay un botón por pulsar. Diga «confirmo» o «cancela».",
  "There is a button to press. Say “confirm” or “cancel”.",
);
const PRESSED = tr("Pulsado.", "Pressed.");
const PRESS_CANCELLED = tr("No pulso nada.", "I am pressing nothing.");

export function Assistant({ console: consoleKey, subject, privacy, speaker: voice, effects, onSigned }: AssistantProps) {
  const [load, setLoad] = useState<AssistantLoad>({ state: "loading" });
  const [open, setOpen] = useState(false);
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [pending, setPending] = useState<PendingWrite | null>(null);
  const [pendingPress, setPendingPress] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  // Firmando: mientras tanto no se vuelve a firmar ni se cancela (una segunda «confirmo» dicha o un
  // doble clic firmarían dos veces la misma propuesta).
  const [signing, setSigning] = useState(false);
  const signingRef = useRef(false);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);
  const [talk, dispatch] = useReducer(talkStep, IDLE);
  const [recordable] = useState(() => browserCanRecord());
  const recording = useRef<Recording | null>(null);

  useEffect(() => {
    let cancelled = false;
    assistantApi
      .info()
      .then((info) => {
        if (!cancelled) setLoad({ state: "ready", info });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setLoad({ state: "failed", outcome: requestOutcome(reason) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // La memoria es de esta consola, este tripulante y esta privacidad: si cambia, se borra, y con
  // ella la propuesta pendiente (sería de otra persona o de antes de poner la privacidad).
  const scope = memoryScope(consoleKey, subject, privacy);
  const [shownScope, setShownScope] = useState(scope);
  if (shownScope !== scope) {
    setShownScope(scope);
    setThread([]);
    setPending(null);
    setPendingPress(null);
    setFailure(null);
  }
  const scopeRef = useRef(scope);
  scopeRef.current = scope;

  const latest = useRef({ effects, voice, thread, pending, pendingPress, subject, consoleKey, privacy, onSigned, load });
  latest.current = { effects, voice, thread, pending, pendingPress, subject, consoleKey, privacy, onSigned, load };

  const say = useCallback((texts: readonly string[]) => latest.current.voice.say(texts, true), []);
  const note = useCallback((text: string) => {
    setThread((current) => remember(current, { role: "assistant", text, source: "console" }));
    say([text]);
  }, [say]);

  /** Lo que se hace con la respuesta del backend: hilo, intención y voz. */
  const answer = useCallback(
    (turn: AssistantTurn) => {
      setOpen(true);
      setThread((current) =>
        remember(current, { role: "assistant", text: turn.reply, source: turn.reply_source, label: turn.label }),
      );
      const ui = latest.current.load.state === "ready" ? latest.current.load.info.ui : null;
      const outcome = executeIntent(turn, { ...latest.current.effects, ui });
      // Leer el estado, las alertas o un panel ya lo dice la voz con su texto tal cual, y repetir
      // repite lo último dicho: la frase de la respuesta no lo pisa.
      const readsAloud = outcome.kind === "done" && SPEAKS_ITSELF.has(turn.intent);
      const spoken: string[] = readsAloud || turn.reply.trim() === "" ? [] : [spokenReply(turn)];
      if (outcome.kind === "press") {
        // La pregunta («¿Pulso…? diga «confirmo»») ya va en la respuesta del backend.
        setPendingPress(outcome.label);
      } else if (outcome.kind === "proposal") {
        setPending(outcome.pending);
        const speech = proposalSpeech(proposalFields(outcome.pending));
        // Con la privacidad, los campos (lo que se va a firmar) no se dicen en voz alta: se ven
        // difuminados, y para firmar basta «confirmo».
        spoken.push(...(latest.current.privacy ? [PROPOSAL_SHOWN, ...speech.slice(1)] : speech));
      } else if (outcome.kind !== "done") {
        setThread((current) => remember(current, { role: "assistant", text: outcome.note, source: "console" }));
        spoken.push(outcome.note);
      }
      if (spoken.length > 0) say(spoken);
    },
    [say],
  );

  const confirm = useCallback(async () => {
    const press = latest.current.pendingPress;
    if (press !== null) {
      // Lo pulsa la consola como una persona; lo que guarde lo guarda el propio botón.
      setPendingPress(null);
      note(pressControl(press) ? PRESSED : NO_BUTTON);
      return;
    }
    const now = latest.current.pending;
    if (now === null || signingRef.current) return;
    const request = signedRequest(now, storedOperator(), latest.current.subject);
    if (!request.ok) {
      note(request.reason);
      return;
    }
    const asked = scopeRef.current;
    signingRef.current = true;
    setSigning(true);
    setFailure(null);
    try {
      await sendSigned(request);
      // Firmado aunque entretanto se cambiara de tripulante o de consola: se dice igual, y se
      // vuelve a pedir el estado, para que nadie lo pida otra vez creyendo que no se firmó.
      if (scopeRef.current === asked) setPending(null);
      note(SIGNED);
      latest.current.onSigned();
    } catch (reason) {
      if (scopeRef.current === asked) setFailure(requestOutcome(reason));
    } finally {
      signingRef.current = false;
      setSigning(false);
    }
  }, [note]);

  const cancel = useCallback(() => {
    if (latest.current.pendingPress !== null) {
      setPendingPress(null);
      note(PRESS_CANCELLED);
      return;
    }
    if (latest.current.pending === null || signingRef.current) return;
    setPending(null);
    note(CANCELLED);
  }, [note]);

  /** Ante una propuesta, lo dicho o escrito solo confirma o cancela; otra cosa lo recuerda. */
  const decide = useCallback(
    (text: string): boolean => {
      if (latest.current.pending === null && latest.current.pendingPress === null) return false;
      const word = confirmationWord(text);
      if (word === "confirm") void confirm();
      else if (word === "cancel") cancel();
      else note(latest.current.pendingPress !== null ? SAY_PRESS_OR_CANCEL : SAY_CONFIRM_OR_CANCEL);
      return true;
    },
    [confirm, cancel, note],
  );

  const sendText = useCallback(
    async (text: string) => {
      const said = text.trim();
      if (said === "") return;
      const before = latest.current.thread;
      setThread((current) => remember(current, { role: "user", text: said }));
      if (decide(said)) return;
      const asked = scopeRef.current;
      setBusy(true);
      setFailure(null);
      try {
        const turn = await assistantApi.turn({
          text: said,
          console: latest.current.consoleKey,
          subject: latest.current.subject,
          history: historyOf(before),
          operator: storedOperator(),
          modes: toggledModes(latest.current.effects.modes),
          controls: visibleControls(),
        });
        if (scopeRef.current === asked) answer(turn);
      } catch (reason) {
        if (scopeRef.current === asked) setFailure(requestOutcome(reason));
      } finally {
        setBusy(false);
      }
    },
    [answer, decide],
  );

  const sendAudio = useCallback(
    async (audio: Blob) => {
      const asked = scopeRef.current;
      setOpen(true);
      setBusy(true);
      setFailure(null);
      try {
        const result = await assistantApi.audio(audio, {
          console: latest.current.consoleKey,
          subject: latest.current.subject,
          history: historyOf(latest.current.thread),
          operator: storedOperator(),
          modes: toggledModes(latest.current.effects.modes),
          controls: visibleControls(),
        });
        if (scopeRef.current !== asked) return;
        setThread((current) => remember(current, { role: "user", text: result.transcript }));
        // Con una propuesta delante, la voz solo confirma o cancela: el turno del backend se ignora.
        if (decide(result.transcript)) return;
        answer(result.turn);
      } catch (reason) {
        if (scopeRef.current === asked) setFailure(requestOutcome(reason));
      } finally {
        setBusy(false);
      }
    },
    [answer, decide],
  );

  // La última `sendAudio`, para que el efecto de enviar no se repita cada vez que cambia.
  const sendAudioRef = useRef(sendAudio);
  sendAudioRef.current = sendAudio;

  // La grabación sigue a la máquina de estados: abrir al pasar a «opening», cerrar y mandar al
  // pasar a «sending», y tirar lo abierto si se soltó antes de tener micrófono.
  const ready = load.state === "ready" && load.info.available;
  const talkBlocked = load.state === "ready" ? talkUnavailable(load.info, recordable) : "no-voice";
  const phase = talk.phase;
  useEffect(() => {
    if (phase !== "opening" || !recordable) {
      if (phase === "opening") dispatch({ type: "denied" });
      return;
    }
    let cancelled = false;
    startRecording()
      .then((started) => {
        if (cancelled) {
          started.cancel();
          return;
        }
        recording.current = started;
        dispatch({ type: "opened" });
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setFailure(requestOutcome(reason));
        dispatch({ type: "denied" });
      });
    return () => {
      cancelled = true;
    };
  }, [phase, recordable]);

  useEffect(() => {
    if (phase === "idle" && recording.current !== null) {
      // Soltado antes de abrir: lo que llegara a grabarse se tira.
      recording.current.cancel();
      recording.current = null;
    }
    if (phase !== "sending") return;
    const current = recording.current;
    recording.current = null;
    if (current === null) {
      dispatch({ type: "done" });
      return;
    }
    void current
      .stop()
      .then((audio) => (audio.size > 0 ? sendAudioRef.current(audio) : undefined))
      .finally(() => dispatch({ type: "done" }));
  }, [phase]);

  // Tope de tiempo: un turno mantenido no graba sin fin, y uno abierto por `listen` se cierra solo.
  const mode = talk.phase === "recording" ? talk.mode : null;
  useEffect(() => {
    if (mode === null) return;
    const timer = setTimeout(() => dispatch({ type: mode === "hold" ? "release" : "press" }), mode === "hold" ? HOLD_LIMIT_MS : LISTEN_LIMIT_MS);
    return () => clearTimeout(timer);
  }, [mode]);

  const canTalk = ready && talkBlocked === null;
  const onTalk = useCallback(
    (type: "press" | "release") => {
      if (type === "release") {
        dispatch({ type });
        return;
      }
      if (!canTalk) return;
      // Quien pulsa para hablar corta la voz: si no, el micrófono grabaría a EMMA.
      if (latest.current.voice.speaking) latest.current.voice.stop();
      dispatch({ type });
    },
    [canTalk],
  );

  // Un turno pedido mientras EMMA hablaba se abre cuando calla (`talkStep`, «waiting»).
  const speaking = voice.speaking;
  useEffect(() => {
    if (phase === "waiting" && !speaking) dispatch({ type: "quiet" });
  }, [phase, speaking]);

  // Ctrl+Espacio mantenido, en toda la ventana; y si la ventana se oculta o pierde el foco, se suelta.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const down = (event: KeyboardEvent) => {
      // Sin poder hablar, Ctrl+Espacio sigue siendo de quien lo tenga (cambiar de método de entrada).
      if (canTalk && talkKey(event, "down") === "press") {
        event.preventDefault();
        onTalk("press");
      }
    };
    const up = (event: KeyboardEvent) => {
      if (talkKey(event, "up") === "release") onTalk("release");
    };
    const blur = () => onTalk("release");
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
    };
  }, [onTalk, canTalk]);

  // El bus (`routeBusEvent`): el trozo grabado por la palabra «EMMA», el gesto que abre un turno y
  // lo que la iniciativa propia ya ha dicho.
  useEffect(
    () =>
      listen((event) =>
        routeBusEvent(event, {
          audio: (audio) => {
            if (ready && talkBlocked !== "no-voice") void sendAudio(audio);
          },
          listen: () => {
            setOpen(true);
            if (canTalk) dispatch({ type: "listen", speaking: latest.current.voice.speaking });
          },
          said: (item) => setThread((current) => remember(current, item)),
        }),
      ),
    [ready, talkBlocked, canTalk, sendAudio],
  );

  return (
    <AssistantView
      load={load}
      open={open}
      onToggle={() => setOpen((value) => !value)}
      thread={thread}
      privacy={privacy}
      mic={micOpen(talk)}
      busy={busy || signing || talk.phase === "sending"}
      talk={load.state === "ready" ? talkBlocked : null}
      onTalk={onTalk}
      draft={draft}
      onDraft={setDraft}
      onSend={() => {
        const text = draft;
        setDraft("");
        void sendText(text);
      }}
      pending={
        pending === null
          ? null
          : { fields: proposalFields(pending), signer: privacy ? tr("tripulante en consola (tapado)", "crew member at the console (hidden)") : storedOperator() }
      }
      pendingPress={pendingPress}
      onConfirm={() => void confirm()}
      onCancel={cancel}
      failure={failure}
    />
  );
}
