/**
 * El gesto de emergencia de la voz: encenderla y oír el estado sin ver la pantalla.
 *
 * Por qué existe: el usuario pidió (2026-11) «un atajo para activarlo que sea fácil de activar en
 * caso de emergencia, en caso de que te hayas quedado ciego». La voz propia (`lib/speech.ts`) ya
 * leía el estado con un botón y con Alt + Mayús + L, pero quien de repente no ve (una lesión
 * ocular, el edema de SANS, un deslumbramiento, humo en la cabina) no encuentra un botón, y un
 * acorde de tres teclas con una letra en medio del teclado se busca a ciegas peor que una tecla
 * de esquina. Así que hay dos gestos que no necesitan mirar:
 *
 * - **Escape tres veces seguidas**, en menos de `EMERGENCY_WINDOW_MS`. Escape está en la esquina
 *   de arriba a la izquierda de casi todos los teclados y se encuentra al tacto; no escribe nada,
 *   así que vale también con el foco en un campo de texto; y pulsarlo tres veces seguidas no es
 *   algo que se haga sin querer (cerrar un desplegable es una).
 * - **Tres dedos sobre la pantalla** quietos `HOLD_MS` y levantarlos, para la tableta. Uno y dos
 *   dedos son del desplazamiento y del zoom; tres quietos no los usa la consola. Se dispara al
 *   levantar, no al cumplirse el segundo, porque Chromium solo deja hablar tras un gesto de la
 *   persona y de los toques solo cuenta como tal el `touchend` (HTML, «activation triggering
 *   input event»).
 *
 * Qué hace el gesto (`emergencyPlan`): con voz local, enciende el modo voz si estaba apagado y lee
 * en el acto una frase fija de navegación (`EMERGENCY_INTRO`) y después lo mismo que «Leer en voz
 * alta». Repetirlo con la voz encendida vuelve a leer: **en emergencia el gesto nunca calla**;
 * apagar sigue siendo el mando o Alt + Mayús + L. Sin voz local no puede hablar: deja en la región
 * viva asertiva, para el lector de pantalla del sistema, que no hay voz y cómo se enciende el
 * Narrador de Windows.
 *
 * Los tiempos y la tolerancia de movimiento son **parámetros de diseño de EMMA, sin fuente**: no se
 * han medido con personas, y menos con una persona que acaba de perder la vista.
 *
 * Aquí va lo que se prueba sin navegador (vitest en node): los dos detectores, como funciones que
 * reciben el estado y lo que pasó y devuelven el estado nuevo y si el gesto se ha completado, y lo
 * que el gesto hace según haya voz o no. Lo que escucha al navegador va en
 * `components/EmergencyVoice.tsx`.
 */

import { tr } from "./i18n";
import type { VoiceAvailability } from "./speech";

/** Pulsaciones de Escape que hacen el gesto. */
export const EMERGENCY_PRESSES = 3;
/** Tiempo máximo entre la primera y la última pulsación (diseño de EMMA, sin fuente). */
export const EMERGENCY_WINDOW_MS = 1500;
/** Dedos sobre la pantalla que hacen el gesto táctil. */
export const HOLD_FINGERS = 3;
/** Lo que hay que mantenerlos quietos (diseño de EMMA, sin fuente). */
export const HOLD_MS = 1000;
/** Lo que un dedo se puede mover sin que deje de ser «quieto», en píxeles CSS (diseño, sin fuente). */
export const HOLD_SLOP_PX = 40;

/**
 * El suceso que se manda desde la aplicación de escritorio con su atajo del sistema
 * (`desktop/main.cjs`, Ctrl + Alt + V). El mismo nombre está escrito allí; una prueba lo vigila.
 */
export const EMERGENCY_EVENT = "emma:emergency-voice";

/** Ese atajo, escrito como se ve en el teclado español, para el texto junto al mando. */
export const DESKTOP_SHORTCUT_TEXT = "Ctrl+Alt+V";

/** Lo mínimo de un `KeyboardEvent` que mira el detector. */
export interface EscapeKey {
  readonly key: string;
  readonly repeat: boolean;
  readonly altKey: boolean;
  readonly ctrlKey: boolean;
  readonly metaKey: boolean;
  readonly shiftKey: boolean;
}

/** Las pulsaciones de Escape que llevan la serie, en milisegundos. */
export interface EscapeSeries {
  readonly times: readonly number[];
}

export const NO_SERIES: EscapeSeries = { times: [] };

/**
 * Un paso del detector del triple Escape.
 *
 * - Cuenta Escape a secas; con un modificador (Mayús + Escape abre el administrador de tareas de
 *   Chrome) no cuenta y rompe la serie, como cualquier otra tecla en medio.
 * - La repetición de la tecla mantenida (`repeat`) ni cuenta ni rompe: mantener Escape no es
 *   pulsarlo tres veces, y quien lo mantiene un instante de más no pierde lo que llevaba.
 * - Solo valen las pulsaciones de los últimos `EMERGENCY_WINDOW_MS`; un reloj que va hacia atrás
 *   (un `timeStamp` de otra base) tampoco deja contar pulsaciones del futuro.
 * - Al completarse, la serie empieza de cero: un cuarto Escape no repite el gesto, hacen falta
 *   otros tres.
 */
export function escapeStep(
  series: EscapeSeries,
  event: EscapeKey,
  now: number,
): { series: EscapeSeries; fire: boolean } {
  if (event.key !== "Escape" || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
    return { series: NO_SERIES, fire: false };
  }
  if (event.repeat) return { series, fire: false };
  const times = [...series.times.filter((time) => time <= now && now - time <= EMERGENCY_WINDOW_MS), now];
  if (times.length >= EMERGENCY_PRESSES) return { series: NO_SERIES, fire: true };
  return { series: { times }, fire: false };
}

/** Un dedo sobre la pantalla: su identificador y dónde está, en píxeles CSS. */
export interface TouchPoint {
  readonly id: number;
  readonly x: number;
  readonly y: number;
}

/**
 * Cómo va el gesto táctil: sin dedos (`idle`), con uno o dos quietos esperando al tercero
 * (`gathering`), con tres quietos desde `since` (`holding`),
 * con el segundo cumplido esperando a que se levanten (`armed`), o deshecho, esperando a que no
 * quede ningún dedo para volver a empezar (`spent`).
 */
export type HoldState =
  | { readonly phase: "idle" }
  | { readonly phase: "gathering"; readonly origin: readonly TouchPoint[] }
  | { readonly phase: "holding"; readonly since: number; readonly origin: readonly TouchPoint[] }
  | { readonly phase: "armed"; readonly origin: readonly TouchPoint[] }
  | { readonly phase: "spent" };

export const HOLD_IDLE: HoldState = { phase: "idle" };

/** Lo que pasa: los dedos que hay ahora (de `touchstart`, `touchmove`, `touchend`…) o el reloj. */
export type HoldInput =
  | { readonly type: "touches"; readonly touches: readonly TouchPoint[]; readonly now: number }
  | { readonly type: "tick"; readonly now: number };

/** Siguen los mismos dedos, y ninguno se ha ido más allá de la tolerancia. */
function stillHolding(origin: readonly TouchPoint[], touches: readonly TouchPoint[]): boolean {
  if (touches.length !== origin.length) return false;
  return origin.every((start) => {
    const now = touches.find((touch) => touch.id === start.id);
    return now !== undefined && Math.hypot(now.x - start.x, now.y - start.y) <= HOLD_SLOP_PX;
  });
}

/**
 * Un paso del detector de tres dedos.
 *
 * - Solo cuenta un toque que empieza limpio: los dedos van llegando (casi nunca a la vez) y ninguno
 *   se mueve más de `HOLD_SLOP_PX` ni se levanta antes de que estén los tres. Un dedo que ya
 *   desplazaba o dos que ampliaban no se convierten en gesto al posar el tercero.
 * - Empieza cuando hay justo tres dedos; un cuarto, mover uno más de `HOLD_SLOP_PX` (eso es
 *   desplazar) o levantar uno antes de `HOLD_MS` lo deshace, y no se vuelve a contar hasta que no
 *   quede ningún dedo: así un deslizamiento con tres dedos que se para no se convierte en gesto.
 * - Cumplido el tiempo (con el reloj o con cualquier suceso posterior) queda armado, y se dispara
 *   cuando se levanta el primer dedo: ese `touchend` es el gesto que Chromium acepta para hablar.
 *   Mover los dedos estando armado también lo deshace.
 * - La vista girada no cambia nada: la distancia es la misma se gire como se gire.
 */
export function holdStep(state: HoldState, input: HoldInput): { state: HoldState; fire: boolean } {
  if (input.type === "tick") {
    if (state.phase === "holding" && input.now - state.since >= HOLD_MS) {
      return { state: { phase: "armed", origin: state.origin }, fire: false };
    }
    return { state, fire: false };
  }
  const { touches, now } = input;
  if (touches.length === 0) return { state: HOLD_IDLE, fire: state.phase === "armed" };
  switch (state.phase) {
    case "spent":
      return { state, fire: false };
    case "idle":
    case "gathering": {
      const before = state.phase === "gathering" ? state.origin : [];
      // Ninguno de los que ya estaban se ha levantado ni movido.
      const kept = before.every((start) => {
        const current = touches.find((touch) => touch.id === start.id);
        return current !== undefined && Math.hypot(current.x - start.x, current.y - start.y) <= HOLD_SLOP_PX;
      });
      if (!kept || touches.length > HOLD_FINGERS) return { state: { phase: "spent" }, fire: false };
      if (touches.length === HOLD_FINGERS) {
        return { state: { phase: "holding", since: now, origin: touches }, fire: false };
      }
      const added = touches.filter((touch) => !before.some((start) => start.id === touch.id));
      return { state: { phase: "gathering", origin: [...before, ...added] }, fire: false };
    }
    case "holding": {
      if (!stillHolding(state.origin, touches)) return { state: { phase: "spent" }, fire: false };
      if (now - state.since >= HOLD_MS) return { state: { phase: "armed", origin: state.origin }, fire: false };
      return { state, fire: false };
    }
    case "armed": {
      const lifted =
        touches.length < state.origin.length && touches.every((touch) => state.origin.some((o) => o.id === touch.id));
      if (lifted) return { state: { phase: "spent" }, fire: true };
      if (!stillHolding(state.origin, touches)) return { state: { phase: "spent" }, fire: false };
      return { state, fire: false };
    }
  }
}

/**
 * La frase fija que se dice antes de la lectura: de navegación, no clínica. Dice que la voz está
 * encendida, cómo volver a oír y cómo callarla. Las teclas, con su nombre en español.
 */
export const EMERGENCY_INTRO = tr(
  "Voz activada. Escape tres veces, o tres dedos un segundo, vuelve a leer. Alt Mayús L para parar.",
  "Voice on. Escape three times, or three fingers for one second, reads again. Alt Shift L to stop.",
);

/** Lo que se dice tras la frase si aún no hay estado que leer (cargando o sin backend). */
export const NOTHING_TO_READ = tr("Todavía no hay estado que leer.", "There is no status to read yet.");

/**
 * Para el lector de pantalla del sistema cuando no hay voz propia. El atajo del Narrador es el que
 * da Microsoft en su guía (`compliance/hmi-state-of-the-art.md`, «Gesto de emergencia»); no se
 * dice ningún otro sistema porque no se ha comprobado.
 */
export const NO_VOICE_NOTICE = tr(
  "Voz no disponible en este equipo. El Narrador de Windows se enciende con Control, tecla Windows e Intro.",
  "Voice is not available on this device. Windows Narrator turns on with Control, Windows key and Enter.",
);

/** Cuando el navegador no deja hablar porque aún no ha habido un gesto que lo permita. */
export const BLOCKED_NOTICE = tr(
  "El navegador todavía no deja hablar: la voz empieza al tocar la pantalla o pulsar otra tecla. " +
    "El Narrador de Windows se enciende con Control, tecla Windows e Intro.",
  "The browser does not allow speech yet: the voice starts when the screen is touched or another key is pressed. " +
    "Windows Narrator turns on with Control, Windows key and Enter.",
);

/** Lo que hace el gesto: hablar (encendiendo antes el modo voz si hace falta) o dejar el aviso. */
export type EmergencyPlan =
  | { readonly kind: "speak"; readonly enableVoice: boolean; readonly chunks: readonly string[] }
  | { readonly kind: "notice"; readonly text: string };

/**
 * Qué hace el gesto según el estado de la voz.
 *
 * - Con voz y el modo apagado: lo enciende y lee. Con el modo encendido: vuelve a leer, desde el
 *   principio, cortando lo que se esté diciendo. Nunca lo apaga.
 * - Sin voz (sin `speechSynthesis` o sin voz local): el aviso para el lector del sistema. El modo
 *   voz no se toca: encenderlo no haría hablar a nada.
 * - La lectura es la que da `statusSpeech`, que ya respeta la privacidad (sin nombres).
 */
export function emergencyPlan(
  availability: VoiceAvailability,
  voiceOn: boolean,
  readout: readonly string[],
): EmergencyPlan {
  if (availability !== "ready") return { kind: "notice", text: NO_VOICE_NOTICE };
  const body = readout.length > 0 ? readout : [NOTHING_TO_READ];
  return { kind: "speak", enableVoice: !voiceOn, chunks: [EMERGENCY_INTRO, ...body] };
}
