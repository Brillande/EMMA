import { useCallback, useEffect, useRef, useState } from "react";

import { emit } from "../assistant/bus";
import { type LiveMessage, appendMessages } from "../lib/announce";
import {
  BLOCKED_NOTICE,
  EMERGENCY_EVENT,
  type EscapeSeries,
  HOLD_IDLE,
  HOLD_MS,
  type HoldInput,
  type HoldState,
  NO_SERIES,
  type TouchPoint,
  emergencyPlan,
  escapeStep,
  holdStep,
} from "../lib/emergencyVoice";
import type { Speaker } from "./ReadAloud";

/**
 * El gesto de emergencia de la voz en el navegador (§5.40, `lib/emergencyVoice.ts`): escucha el
 * triple Escape, los tres dedos y el aviso de la aplicación de escritorio, y hace lo que diga
 * `emergencyPlan`. Qué cuenta como gesto y qué hace se decide allí, con prueba; aquí solo se
 * escucha y se pinta la región viva del aviso.
 *
 * - **Teclado en captura, en la ventana.** Así llega antes que nadie y con el foco donde esté
 *   (un campo de texto, un desplegable, cualquier pestaña): Escape no escribe nada. El tercer
 *   Escape no sigue hasta su destino: es del gesto, y así el «Escape para la voz» de
 *   `useVoiceShortcut` no corta la lectura que se acaba de pedir. El primero sí sigue: si la voz
 *   hablaba, la calla, y el tercero vuelve a leer desde el principio. El triple siempre gana.
 * - **Toques pasivos.** Se miran sin `preventDefault`: el desplazamiento con uno o dos dedos y el
 *   zoom siguen siendo del navegador.
 * - **Si el navegador no deja hablar** (Chromium pide antes un gesto de la persona y Escape, por la
 *   norma HTML, no lo es), se dice en la región viva y la lectura se reintenta con el siguiente
 *   suceso que sí lo es: una tecla que no sea Escape, un clic o un toque que se levanta.
 */

/** Lo que dura pendiente una lectura que el navegador no dejó decir (diseño de EMMA, sin fuente). */
const RETRY_MS = 30_000;

/** Teclas que solas no son una pulsación de la persona para reintentar (son parte de un acorde). */
const MODIFIER_KEYS = new Set(["Alt", "AltGraph", "Control", "Meta", "Shift", "OS"]);

/** Los dedos de un `TouchEvent`, en el formato del detector. */
function points(list: TouchList): TouchPoint[] {
  return Array.from(list, (touch) => ({ id: touch.identifier, x: touch.clientX, y: touch.clientY }));
}

/** La región viva asertiva del aviso: siempre montada y vacía, para que el lector anuncie lo nuevo. */
export function EmergencyNotice({ messages }: { messages: readonly LiveMessage[] }) {
  return (
    <div className="sr-only">
      <div role="alert" aria-atomic="false">
        {messages.map((message) => (
          <p key={message.id}>{message.text}</p>
        ))}
      </div>
    </div>
  );
}

export function EmergencyVoice({
  speaker,
  readout,
  voiceOn,
  enableVoice,
}: {
  speaker: Speaker;
  readout: readonly string[];
  voiceOn: boolean;
  enableVoice: () => void;
}) {
  const latest = useRef({ speaker, readout, voiceOn, enableVoice });
  latest.current = { speaker, readout, voiceOn, enableVoice };
  const [messages, setMessages] = useState<LiveMessage[]>([]);
  const nextId = useRef(0);
  // Un gesto que el navegador no dejó decir: cuándo fue y de qué intento es. El reintento lee lo
  // de ahora (no lo de entonces) y caduca: una lectura de hace minutos ya no se pidió.
  const retry = useRef<{ at: number; attempt: number } | null>(null);
  const attempt = useRef(0);

  const post = useCallback((text: string) => {
    const id = nextId.current;
    nextId.current += 1;
    setMessages((current) => appendMessages(current, [text], id));
  }, []);

  const trigger = useCallback(() => {
    const { speaker: now, readout: text, voiceOn: on, enableVoice: enable } = latest.current;
    const plan = emergencyPlan(now.availability, on, text);
    // Si el asistente está montado, abre un turno de escucha (`assistant/bus.ts`); si no, nadie
    // escucha el suceso y no pasa nada.
    emit({ kind: "listen" });
    if (plan.kind === "notice") {
      post(plan.text);
      return;
    }
    if (plan.enableVoice) enable();
    attempt.current += 1;
    const mine = attempt.current;
    retry.current = null;
    now.say(plan.chunks, true, () => {
      // Un aviso de bloqueo que llega tarde, de un intento ya sustituido, no cuenta.
      if (mine !== attempt.current) return;
      retry.current = { at: performance.now(), attempt: mine };
      post(BLOCKED_NOTICE);
    });
  }, [post]);

  // Reintento tras un bloqueo: solo con sucesos que el navegador cuenta como gesto de la persona.
  const retryNow = useCallback(() => {
    const pending = retry.current;
    if (pending === null) return;
    retry.current = null;
    if (pending.attempt !== attempt.current || performance.now() - pending.at > RETRY_MS) return;
    const { speaker: now, readout: text } = latest.current;
    const plan = emergencyPlan(now.availability, true, text);
    if (plan.kind !== "speak") return;
    // Si vuelve a fallar se queda pendiente otra vez, sin repetir el aviso.
    now.say(plan.chunks, true, () => {
      if (pending.attempt === attempt.current) retry.current = pending;
    });
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    let series: EscapeSeries = NO_SERIES;
    let hold: HoldState = HOLD_IDLE;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const onKey = (event: KeyboardEvent) => {
      // Una tecla suelta reintenta; un modificador o un acorde no (Alt + Mayús + L es del atajo de
      // la voz, y reintentar en su Alt haría que la L parase lo que se acaba de empezar).
      if (
        event.key !== "Escape" &&
        !event.repeat &&
        !MODIFIER_KEYS.has(event.key) &&
        !event.altKey &&
        !event.ctrlKey &&
        !event.metaKey
      ) {
        retryNow();
      }
      const step = escapeStep(series, event, event.timeStamp);
      series = step.series;
      if (!step.fire) return;
      event.stopPropagation();
      trigger();
    };

    const feed = (input: HoldInput) => {
      const step = holdStep(hold, input);
      const started = hold.phase !== "holding" && step.state.phase === "holding";
      hold = step.state;
      if (started) {
        if (timer !== null) clearTimeout(timer);
        timer = setTimeout(() => {
          timer = null;
          hold = holdStep(hold, { type: "tick", now: performance.now() }).state;
        }, HOLD_MS + 50);
      }
      if (step.fire) trigger();
    };
    const onTouch = (event: TouchEvent) => feed({ type: "touches", touches: points(event.touches), now: event.timeStamp });
    const onTouchEnd = (event: TouchEvent) => {
      retryNow();
      onTouch(event);
    };
    // El sistema se queda los toques (un gesto suyo): lo que se llevaba no vale.
    const onTouchCancel = (event: TouchEvent) => {
      hold = event.touches.length === 0 ? HOLD_IDLE : { phase: "spent" };
    };
    const onMouseDown = () => retryNow();
    const onPointerUp = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") retryNow();
    };

    window.addEventListener("keydown", onKey, true);
    window.addEventListener("touchstart", onTouch, { passive: true, capture: true });
    window.addEventListener("touchmove", onTouch, { passive: true, capture: true });
    window.addEventListener("touchend", onTouchEnd, { passive: true, capture: true });
    window.addEventListener("touchcancel", onTouchCancel, { passive: true, capture: true });
    window.addEventListener("mousedown", onMouseDown, true);
    window.addEventListener("pointerup", onPointerUp, true);
    window.addEventListener(EMERGENCY_EVENT, trigger);
    return () => {
      if (timer !== null) clearTimeout(timer);
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("touchstart", onTouch, true);
      window.removeEventListener("touchmove", onTouch, true);
      window.removeEventListener("touchend", onTouchEnd, true);
      window.removeEventListener("touchcancel", onTouchCancel, true);
      window.removeEventListener("mousedown", onMouseDown, true);
      window.removeEventListener("pointerup", onPointerUp, true);
      window.removeEventListener(EMERGENCY_EVENT, trigger);
    };
  }, [trigger, retryNow]);

  return <EmergencyNotice messages={messages} />;
}
