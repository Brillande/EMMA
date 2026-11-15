/**
 * La voz propia de la consola: leer en voz alta el estado y avisar de cada alerta nueva.
 *
 * Por qué existe: el usuario pidió (2026-11) un lector de pantalla «también en caso de ceguera».
 * El lector del sistema (NVDA, Narrador) lee la consola gracias a su ARIA, pero puede no estar
 * instalado en el equipo de a bordo, y quien tiene las manos ocupadas o la vista en otra cosa
 * quiere oír el estado sin mirarlo. Esta voz no sustituye al lector del sistema: lee dos cosas y
 * nada más, el resumen del estado y las alertas activas, con las frases tal cual las redacta el
 * backend (`advisor.summarize`, los motivos de cada dominio). La interfaz no redacta texto
 * clínico (`CLAUDE.md`); aquí solo pone rótulos de navegación («Alertas activas:», «Alerta
 * nueva:») y las palabras que ya están en pantalla (la del nivel, que también es del backend, y el
 * nombre del dominio).
 *
 * **Solo voces locales.** `window.speechSynthesis` puede ofrecer voces «en línea»
 * (`localService === false`): en Chromium, las voces de Google sintetizan en un servidor, así
 * que el texto que se lee —el estado de salud de un tripulante— saldría de la nave sin pasar por
 * `backend/app/core/egress.py`, que es por donde pasa toda salida a internet (invariante 3 bis).
 * Por eso `pickVoice` descarta toda voz que no sea local, aunque sea la única en español; sin voz
 * local, la voz se declara no disponible. En la aplicación de escritorio (Electron) las voces son
 * las del sistema operativo, todas locales.
 *
 * La síntesis no pide permiso al navegador: el gestor de permisos de `desktop/main.cjs`, que los
 * deniega todos, no la apaga; y la CSP de `vite.config.ts` no la afecta, porque no carga nada.
 *
 * Aquí va lo que se prueba sin navegador (vitest en node, sin jsdom): qué voz se elige, qué texto
 * se lee, qué alertas son nuevas y a qué tecla responde. Lo que toca el navegador
 * (`speechSynthesis`, `SpeechSynthesisUtterance`) va en `components/ReadAloud.tsx`.
 */

import type { Alert } from "./alerts";
import { formatNumber } from "./format";
import { type Language, language, tr } from "./i18n";

/** Lo que se usa de una `SpeechSynthesisVoice`: así las pruebas pasan voces de mentira. */
export interface VoiceLike {
  readonly name: string;
  readonly lang: string;
  readonly localService: boolean;
  readonly default: boolean;
}

/** Por qué no hay voz: sin la API en este navegador, o con la API pero sin ninguna voz local. */
export type VoiceAvailability = "ready" | "no-api" | "no-local-voice";

/**
 * Las voces de cada idioma de la interfaz (`lib/i18n.ts`). BCP 47 dice `es-ES` o `en-US`; algunos
 * sistemas (Android) dan `es_ES`. Y `es` o `en` a secas.
 */
const VOICE_LANGUAGE: Record<Language, RegExp> = {
  es: /^es(?:[-_]|$)/i,
  en: /^en(?:[-_]|$)/i,
};

/**
 * La voz con que se lee: solo de las locales; de ellas, una en el idioma de la interfaz (lo que se
 * lee está en ese idioma: una voz española leyendo inglés no se entiende), la que el sistema marca
 * por defecto si la hay; si no hay ninguna en ese idioma, la local por defecto o la primera (el
 * texto se entiende peor con otra voz, pero se oye); y sin voces locales, ninguna. El enunciado
 * lleva el `lang` de la voz elegida (`components/ReadAloud.tsx`).
 */
export function pickVoice<V extends VoiceLike>(voices: readonly V[]): V | null {
  const local = voices.filter((voice) => voice.localService === true);
  const own = local.filter((voice) => VOICE_LANGUAGE[language()].test(voice.lang));
  const pool = own.length > 0 ? own : local;
  return pool.find((voice) => voice.default) ?? pool[0] ?? null;
}

/** Si hay voz, y si no, por qué. `null` es que el navegador no tiene `speechSynthesis`. */
export function voiceAvailability(voices: readonly VoiceLike[] | null): VoiceAvailability {
  if (voices === null) return "no-api";
  return pickVoice(voices) === null ? "no-local-voice" : "ready";
}

/** La palabra de cada «no disponible», para la marca gris junto al mando. */
export const UNAVAILABLE_TEXT: Record<Exclude<VoiceAvailability, "ready">, string> = {
  "no-api": tr(
    "Voz no disponible: este navegador no tiene síntesis de voz",
    "Voice unavailable: this browser has no speech synthesis",
  ),
  "no-local-voice": tr(
    "Voz no disponible: no hay ninguna voz instalada en el equipo",
    "Voice unavailable: no voice is installed on this device",
  ),
};

/** Una frase terminada en su punto: sin él, la voz encadena el rótulo con lo siguiente. */
export function sentence(text: string): string {
  const trimmed = text.trim();
  if (trimmed === "") return "";
  return /[.!?…:;]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}

/** Lo que se lee de una alerta: las palabras de su fila, sin nada que no esté en pantalla. */
export interface SpokenAlert {
  readonly id: string;
  /** La palabra del nivel, la del backend (`level_labels`), la misma de la insignia. */
  readonly level: string;
  /** El nombre del dominio, el mismo de la fila. */
  readonly domain: string;
  /** Los motivos, tal cual del backend. */
  readonly drivers: readonly string[];
  /** «Suprimida» o «Inhibida», la palabra de la fila; `null` si se anuncia. */
  readonly silenced: string | null;
}

/** La alerta a leer, con las palabras de su fila. */
export function spokenAlert(
  alert: Alert,
  levelLabel: (level: string) => string,
  domainLabel: (domain: string) => string,
  annunciation: string | undefined,
): SpokenAlert {
  return {
    id: alert.id,
    level: levelLabel(alert.level),
    domain: domainLabel(alert.domain),
    drivers: alert.drivers,
    silenced:
      annunciation === "suppressed"
        ? tr("Suprimida", "Suppressed")
        : annunciation === "inhibited"
          ? tr("Inhibida", "Inhibited")
          : null,
  };
}

function alertLines(alert: SpokenAlert): string {
  const head = sentence(`${alert.level}, ${alert.domain}`);
  const parts = [head, alert.silenced === null ? "" : sentence(alert.silenced), ...alert.drivers.map(sentence)];
  return parts.filter((part) => part !== "").join(" ");
}

/**
 * Lo que se lee con «Leer en voz alta», en trozos (uno por alerta): la consola y de quién es, el
 * resumen del backend y cada alerta activa. Va en trozos porque cada uno es un enunciado aparte
 * de la síntesis, y así «Parar» corta enseguida y un texto largo no se queda a medias.
 *
 * Con la privacidad puesta no se dice de quién es: ni el nombre del tripulante (la franja tampoco
 * lo enseña) ni ningún otro nombre, porque la voz llega a quien está en la sala aunque no mire la
 * pantalla. Lo demás se lee igual que se ve: la privacidad deja a la vista el estado general y las
 * alertas con sus motivos (§5.40), porque una preferencia de presentación no puede callar una
 * alerta; tampoco la voz.
 */
export function statusSpeech({
  console: consoleName,
  subject,
  summary,
  alerts,
  privacy,
}: {
  console: string;
  subject: string;
  summary: string;
  alerts: readonly SpokenAlert[];
  privacy: boolean;
}): string[] {
  const who = privacy
    ? sentence(consoleName)
    : sentence(tr(`${consoleName}, tripulante ${subject}`, `${consoleName}, crew member ${subject}`));
  const chunks = [`${who} ${sentence(tr(`Estado: ${summary}`, `Status: ${summary}`))}`];
  chunks.push(
    sentence(tr(`Alertas activas: ${formatNumber(alerts.length)}`, `Active alerts: ${formatNumber(alerts.length)}`)),
  );
  for (const alert of alerts) chunks.push(alertLines(alert));
  return chunks;
}

/** El rótulo de una alerta nueva; lo dice también la iniciativa propia (`assistant/proactive.ts`). */
export const NEW_ALERT_LABEL = tr("Alerta nueva:", "New alert:");

/** Lo que se lee al aparecer una alerta nueva: el rótulo y la alerta, con sus palabras. */
export function newAlertSpeech(alert: SpokenAlert): string {
  return `${NEW_ALERT_LABEL} ${alertLines(alert)}`;
}

/**
 * Qué alertas hay que anunciar, y qué queda anunciado después.
 *
 * - `seen === null` es la primera vez que se miran (la consola acaba de cargar, se cambió de
 *   tripulante o de consola, o se acaba de encender la voz): no se anuncia nada y lo de ahora queda
 *   como visto. Anunciar todo cada vez que se recarga la página sería ruido; para oírlo todo está
 *   «Leer en voz alta».
 * - Una alerta silenciada (suprimida o inhibida) no se anuncia, porque silenciarla es justo dejar
 *   de anunciarla (F.6.4), y tampoco queda como vista: si se vuelve a habilitar, se anuncia.
 * - Lo que ya no está activo sale de lo visto: si vuelve, es un episodio nuevo y se anuncia otra
 *   vez. La clave de una alerta es dominio y nivel (`lib/alerts.ts`): si sube de nivel es otra.
 */
export function newAlerts(
  seen: ReadonlySet<string> | null,
  current: readonly SpokenAlert[],
): { announce: SpokenAlert[]; seen: Set<string> } {
  const audible = current.filter((alert) => alert.silenced === null);
  const next = new Set(audible.map((alert) => alert.id));
  if (seen === null) return { announce: [], seen: next };
  return { announce: audible.filter((alert) => !seen.has(alert.id)), seen: next };
}

/** Lo que piden las teclas de la voz. */
export type VoiceCommand = "read" | "stop" | "repeat";

/** Lo mínimo de un `KeyboardEvent` que se mira. */
export interface KeyLike {
  readonly code: string;
  readonly key: string;
  readonly altKey: boolean;
  readonly shiftKey: boolean;
  readonly ctrlKey: boolean;
  readonly metaKey: boolean;
}

/**
 * El atajo de teclado: Alt + Mayús + L lee el estado (o lo para, si ya está hablando), Alt + Mayús
 * + R repite lo último leído, y Escape para la voz. Se mira `code` (la tecla física), no `key`: con
 * Alt y Mayús, `key` depende de la distribución del teclado. Alt + Mayús no lo usa la consola, ni
 * NVDA ni Narrador como modificador (usan Insertar o Bloq Mayús), y en el escritorio empaquetado
 * no hay barra de menús que se lleve el Alt. Escape solo cuenta si se está hablando: si no, es
 * de quien lo tenga (cerrar un desplegable). Dentro de un campo de texto (`editable`) las letras
 * no cuentan: en algunas distribuciones (Opción + Mayús en macOS) Alt + Mayús + L escribe un
 * carácter, y la nota no debe perderlo; Escape sí para la voz.
 */
export function voiceShortcut(event: KeyLike, speaking: boolean, editable = false): VoiceCommand | null {
  if (event.key === "Escape" && !event.altKey && !event.ctrlKey && !event.metaKey) {
    return speaking ? "stop" : null;
  }
  if (editable || !event.altKey || !event.shiftKey || event.ctrlKey || event.metaKey) return null;
  if (event.code === "KeyL") return speaking ? "stop" : "read";
  if (event.code === "KeyR") return "repeat";
  return null;
}

/** El atajo escrito, para el rótulo y el `aria-keyshortcuts` del mando. */
export const READ_SHORTCUT = "Alt+Shift+L";
export const REPEAT_SHORTCUT = "Alt+Shift+R";
