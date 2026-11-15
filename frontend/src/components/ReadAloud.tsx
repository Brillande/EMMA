import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState } from "react";

import { tr } from "../lib/i18n";
import { UNAVAILABLE_MARK } from "../lib/marks";
import {
  READ_SHORTCUT,
  REPEAT_SHORTCUT,
  UNAVAILABLE_TEXT,
  type VoiceAvailability,
  pickVoice,
  voiceAvailability,
  voiceShortcut,
} from "../lib/speech";
import { Command } from "./Command";
import { VoiceShortcuts } from "./VoiceShortcuts";
import { MarkOf } from "./Mark";

/**
 * La voz propia en el navegador (§5.40): la parte de `lib/speech.ts` que toca `speechSynthesis`.
 * Qué voz, qué texto y qué alertas son nuevas se deciden allí, en funciones puras con prueba; aquí
 * solo se habla, se para y se repite, y se pinta el mando de la cabecera.
 *
 * Solo se habla con la voz que da `pickVoice`, que es siempre local: una voz «en línea» mandaría
 * el texto a un servidor sin pasar por `egress.py` (lo explica `lib/speech.ts`). Es una voz del
 * idioma de la interfaz si el equipo la tiene, y cada enunciado lleva el `lang` de esa voz.
 */

/** La síntesis de voz del navegador, o nada si no la tiene (o no hay navegador: las pruebas). */
export function browserSynth(): SpeechSynthesis | null {
  try {
    return typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;
  } catch {
    return null;
  }
}

/**
 * Las voces del sistema, o `null` sin API. Chromium las da tarde: la primera lista puede venir
 * vacía y llega entera con `voiceschanged`, así que se vuelve a leer con ese evento.
 */
export function useVoices(): readonly SpeechSynthesisVoice[] | null {
  const [voices, setVoices] = useState<readonly SpeechSynthesisVoice[] | null>(
    () => browserSynth()?.getVoices() ?? null,
  );
  useEffect(() => {
    const synth = browserSynth();
    if (synth === null) return;
    const update = () => setVoices(synth.getVoices());
    update();
    synth.addEventListener("voiceschanged", update);
    return () => synth.removeEventListener("voiceschanged", update);
  }, []);
  return voices;
}

/**
 * Si hay voz, de una sola fuente: la que mira `useSpeaker` en `App.tsx`. Los mandos de pantalla la
 * leen de aquí, para que el modo voz y el mando de la franja no discrepen mientras Chromium carga
 * las voces. Sin proveedor (las pruebas), sin API.
 */
export const VoiceAvailabilityContext = createContext<VoiceAvailability>("no-api");

export function useVoiceAvailability(): VoiceAvailability {
  return useContext(VoiceAvailabilityContext);
}

export interface Speaker {
  availability: VoiceAvailability;
  speaking: boolean;
  /** Hay algo leído que repetir. */
  canRepeat: boolean;
  /**
   * Lee los trozos, cada uno como un enunciado. `interrupt` corta lo que se esté diciendo (leer
   * el estado a petición); sin él, se pone a la cola (el aviso de una alerta nueva no corta a
   * nadie a media frase). `onBlocked` se llama una vez si el navegador no deja hablar
   * (`not-allowed`: Chromium pide antes un gesto de la persona, y Escape no lo es), para que el
   * gesto de emergencia (`EmergencyVoice.tsx`) lo diga y lo reintente.
   */
  say: (chunks: readonly string[], interrupt: boolean, onBlocked?: () => void) => void;
  stop: () => void;
  repeat: () => void;
}

export function useSpeaker(): Speaker {
  const voices = useVoices();
  const availability = voiceAvailability(voices);
  const voice = useMemo(() => (voices === null ? null : pickVoice(voices)), [voices]);
  const [speaking, setSpeaking] = useState(false);
  const [canRepeat, setCanRepeat] = useState(false);
  const pending = useRef(0);
  // Cada «parar» abre una generación nueva: los avisos de fin de los enunciados cancelados, que
  // Chromium da tarde o no da, no tocan la cuenta de los de ahora.
  const generation = useRef(0);
  const last = useRef<readonly string[]>([]);

  const halt = useCallback(() => {
    browserSynth()?.cancel();
    generation.current += 1;
    pending.current = 0;
    setSpeaking(false);
  }, []);

  const say = useCallback(
    (chunks: readonly string[], interrupt: boolean, onBlocked?: () => void) => {
      const synth = browserSynth();
      const texts = chunks.filter((chunk) => chunk.trim() !== "");
      if (synth === null || voice === null || texts.length === 0) return;
      if (interrupt) halt();
      const current = generation.current;
      // «Repetir» vuelve a decir lo último que se pidió leer (el estado entero): un aviso a la cola
      // no lo pisa. Si aún no se pidió nada, repite el último aviso.
      const previous = last.current;
      if (interrupt || last.current.length === 0) last.current = texts;
      setCanRepeat(true);
      let blocked = false;
      for (const text of texts) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.voice = voice;
        utterance.lang = voice.lang;
        const done = () => {
          if (current !== generation.current) return;
          pending.current = Math.max(0, pending.current - 1);
          if (pending.current === 0) setSpeaking(false);
        };
        utterance.onend = done;
        utterance.onerror = (event) => {
          done();
          if (event.error === "not-allowed" && !blocked) {
            blocked = true;
            // Lo que no se dijo no es «lo último leído»: «Repetir» sigue con lo de antes.
            if (last.current === texts) last.current = previous;
            onBlocked?.();
          }
        };
        pending.current += 1;
        synth.speak(utterance);
      }
      setSpeaking(true);
    },
    [voice, halt],
  );

  const repeat = useCallback(() => say(last.current, true), [say]);

  // Chromium a veces no da el fin de un enunciado (sobre todo tras `cancel()`): sin esto, la
  // consola se quedaría en «Parar la voz» para siempre. Mientras dice que habla, se mira si la
  // síntesis sigue con algo; si no, ya no habla.
  useEffect(() => {
    if (!speaking) return;
    const timer = setInterval(() => {
      const synth = browserSynth();
      if (synth === null || (!synth.speaking && !synth.pending)) {
        pending.current = 0;
        setSpeaking(false);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [speaking]);

  // Al desmontar la consola, la voz no sigue hablando sola.
  useEffect(() => halt, [halt]);

  return { availability, speaking, canRepeat, say, stop: halt, repeat };
}

/**
 * Las teclas de la voz en toda la ventana (`voiceShortcut`): leer o parar, repetir y Escape para
 * parar. `read` es lo que se lee ahora; sin nada que leer, la tecla no hace nada.
 */
export function useVoiceShortcut(speaker: Speaker, read: readonly string[]): void {
  const latest = useRef({ speaker, read });
  latest.current = { speaker, read };
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onKey = (event: KeyboardEvent) => {
      const { speaker: now, read: text } = latest.current;
      // Mantener la tecla pulsada no alterna leer y parar con cada repetición del teclado.
      if (now.availability !== "ready" || event.repeat) return;
      const command = voiceShortcut(event, now.speaking, isEditable(event.target));
      if (command === null) return;
      if (command === "stop") now.stop();
      else if (command === "repeat") now.repeat();
      else if (text.length > 0) now.say(text, true);
      // Escape sigue siendo de quien lo tenga (un desplegable que se cierra): solo se lee.
      if (event.key !== "Escape") event.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

/** Un campo donde se escribe: ahí Alt + Mayús + una letra puede ser un carácter (macOS). */
function isEditable(target: EventTarget | null): boolean {
  if (typeof HTMLElement === "undefined" || !(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/** La palabra gris de «no disponible» (tabla F.5-1), con el motivo. */
export function VoiceUnavailable({ availability }: { availability: Exclude<VoiceAvailability, "ready"> }) {
  return <MarkOf mark={UNAVAILABLE_MARK}>{UNAVAILABLE_TEXT[availability]}</MarkOf>;
}

/**
 * El mando de la cabecera: «Leer en voz alta» (o «Parar» mientras habla) y «Repetir». Los rótulos
 * son de navegación; lo que se lee lo da `statusSpeech` con las frases del backend. Sin voz, la
 * marca gris de «no disponible» con el motivo, en el mismo sitio.
 *
 * Junto al mando va escrito el gesto de emergencia (`lib/emergencyVoice.ts`), y el grupo de la voz
 * lo lleva por `aria-describedby` (una vez para sus tres botones): `aria-keyshortcuts` nombra teclas o acordes, no una serie de tres
 * pulsaciones, así que «Escape» a secas ahí diría algo falso (un Escape solo no lee).
 *
 * Desde la franja compacta (§5.40, 2026-11-04) ese texto va dentro del plegable «Atajos»
 * (`VoiceShortcuts.tsx`), junto a los dos mandos: era una línea larga que ocupaba su propio
 * renglón en la franja fija.
 */
export function ReadAloud({ speaker, read }: { speaker: Speaker; read: readonly string[] }) {
  const help = useId();
  if (speaker.availability !== "ready") {
    return (
      <div className="cell read-aloud">
        <VoiceUnavailable availability={speaker.availability} />
      </div>
    );
  }
  return (
    <div className="cell read-aloud" role="group" aria-label={tr("Voz", "Voice")} aria-describedby={help}>
      {speaker.speaking ? (
        <Command type="button" concept="stopVoice" aria-keyshortcuts={`${READ_SHORTCUT} Escape`} onClick={speaker.stop}>
          {tr("Parar la voz", "Stop the voice")}
        </Command>
      ) : (
        <Command
          type="button"
          concept="voice"
          aria-keyshortcuts={READ_SHORTCUT}
          disabled={read.length === 0}
          onClick={() => speaker.say(read, true)}
        >
          {tr("Leer en voz alta", "Read aloud")}
        </Command>
      )}
      <Command
        type="button"
        concept="repeatVoice"
        aria-keyshortcuts={REPEAT_SHORTCUT}
        disabled={!speaker.canRepeat}
        onClick={speaker.repeat}
      >
        {tr("Repetir", "Repeat")}
      </Command>
      <VoiceShortcuts id={help} />
    </div>
  );
}
