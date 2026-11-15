/**
 * El ejecutor de las intenciones del asistente: qué hace la consola con lo que contesta el backend.
 *
 * Por qué una lista cerrada aquí también: el backend ya valida la intención contra su catálogo
 * (`backend/app/data/assistant_intents.json`), pero lo que la consola hace con ella es código de
 * la consola, y una intención que no está en esta tabla no hace nada —y lo dice—, aunque el
 * backend la mande. Así un catálogo nuevo en el backend no abre por sí solo una vía nueva en la
 * pantalla.
 *
 * Dos clases, como en el backend:
 * - **Lectura** (`read`): se hacen al momento con lo que la consola ya tiene: las pestañas del
 *   carril (`ConsoleTabs`), los modos de pantalla (`DisplayModesContext`), la voz propia
 *   (`lib/speech.ts`) y los paneles y pliegues del inventario de la interfaz
 *   (`backend/app/data/assistant_ui.json`, que llega con `GET /api/assistant`): abrir uno, leer lo
 *   que pone, ir al siguiente. Se llega a cada panel por su `data-ui` (`uiTargets.ts`), nunca por
 *   su texto visible. Nada de esto firma. Además, `press` pulsa un botón a la vista por su
 *   rótulo (`controls.ts`): si solo cambia la vista, al momento; si guarda algo, tras «confirmo»,
 *   y lo guarda el propio botón por su ruta de siempre.
 * - **Escritura** (`write`): nunca se hacen aquí. Se devuelve la propuesta del backend para
 *   enseñarla campo a campo y decirla; solo `signedRequest` + `sendSigned`, tras «confirmo» o el
 *   botón Confirmar, la mandan por la MISMA ruta del formulario de siempre, con quien firma de la
 *   consola. Sin operador, no se firma.
 *
 * Los rótulos que pone la consola (`note`) son de navegación («esa sección no está a la vista»),
 * nunca texto clínico: lo clínico es la `reply` del backend, que la consola dice tal cual, y lo
 * que pone un panel en pantalla, que se lee tal cual.
 */

import { DEFAULT_MODES, ROTATIONS, type DisplayModes, type Rotation } from "../components/displayModes";
import { type AssistantTurn, type UiInventory, type UiPanel, type UiPlace, api, diaryApi, missionProfileApi } from "../lib/api";
import { formatNumber } from "../lib/format";
import { type Language, language, tr } from "../lib/i18n";
import { controlWrites, findControl, pressControl } from "./controls";

/** Las de lectura que la consola sabe hacer. */
export const READ_INTENTS = [
  "open_tab",
  "open_panel",
  "read_panel",
  "next_panel",
  "previous_panel",
  "scroll",
  "switch_console",
  "toggle_mode",
  "read_status",
  "read_alerts",
  "read_routines",
  "rotate",
  "privacy",
  "low_vision",
  "essential",
  "stop_voice",
  "repeat_voice",
  "open_guide",
  "open_glossary",
  "start_pvt",
  "start_cognition",
  "silence",
  "stop_listening",
  "press",
  "none",
] as const;

export type ReadIntent = (typeof READ_INTENTS)[number];

/**
 * Las de escritura, con la ruta del formulario que ya existe y el campo de quien firma. El cuerpo
 * es la `proposal` del backend tal cual, más quien firma (lo pone la consola, nunca la propuesta)
 * y el tripulante que se está viendo en las rutas que lo llevan.
 */
export const WRITE_ROUTES = {
  diary_entry: { signer: "recorded_by", subject: true, path: "/diary/entries" },
  pain_report: { signer: "reported_by", subject: true, path: "/pain/reports" },
  acknowledge_alert: { signer: "acknowledged_by", subject: true, path: "/alerts/acknowledge" },
  mission_level: { signer: "declared_by", subject: false, path: "/mission-mode" },
  mission_profile: { signer: "declared_by", subject: false, path: "/mission/profile" },
  safe_mode: { signer: "declared_by", subject: false, path: "/safe-mode" },
} as const;

export type WriteIntent = keyof typeof WRITE_ROUTES;

export function isReadIntent(id: string): id is ReadIntent {
  return (READ_INTENTS as readonly string[]).includes(id);
}

export function isWriteIntent(id: string): id is WriteIntent {
  return Object.prototype.hasOwnProperty.call(WRITE_ROUTES, id);
}

/** Los modos de pantalla que se encienden y apagan: los de `DisplayModes` que son sí o no. */
export type ToggleMode = { [K in keyof DisplayModes]: DisplayModes[K] extends boolean ? K : never }[keyof DisplayModes];

export const TOGGLE_MODES = (Object.keys(DEFAULT_MODES) as (keyof DisplayModes)[]).filter(
  (key): key is ToggleMode => typeof DEFAULT_MODES[key] === "boolean",
);

/**
 * Los modos de sí o no tal como están, para el turno: con ellos el backend entiende «ya se han ido»
 * con la privacidad puesta. Solo presentación; el backend no los guarda.
 */
export function toggledModes(modes: DisplayModes): Record<ToggleMode, boolean> {
  return Object.fromEntries(TOGGLE_MODES.map((key) => [key, modes[key]])) as Record<ToggleMode, boolean>;
}

/** Los que miran o escuchan: con la privacidad puesta no se encienden (`displayModes.ts`). */
const SENSES: readonly ToggleMode[] = ["followFace", "wakeWord"];

/** Una pestaña del carril tal como está ahora en pantalla. */
export interface TabRef {
  key: string;
  label: string;
}

export type ScrollDirection = "up" | "down" | "top" | "bottom";

/** Lo que el ejecutor puede tocar: todo inyectado, para probarlo sin navegador. */
export interface IntentEffects {
  console: "crew" | "ground";
  /** Las pestañas a la vista ahora (el modo esencial oculta algunas). */
  tabs: () => readonly TabRef[];
  openTab: (key: string) => void;
  switchConsole: (to: "crew" | "ground") => void;
  /**
   * Abre la pestaña de `place` (cambiando de consola si hace falta), despliega el panel o pliegue
   * con ese `data-ui` y lo lleva a la vista.
   */
  revealPanel: (id: string, place: UiPlace) => void;
  /** Como `revealPanel`, y después lee lo que pone; `false` si no hay voz. */
  readPanel: (id: string, place: UiPlace) => boolean;
  /** Lleva a la vista el panel siguiente (1) o el anterior (-1) de la pestaña; `false` si no hay. */
  stepPanel: (delta: 1 | -1) => boolean;
  scroll: (direction: ScrollDirection) => void;
  modes: DisplayModes;
  updateModes: (patch: Partial<DisplayModes>) => void;
  /** Lee el estado o las alertas con la voz; `false` si no hay nada que leer o no hay voz. */
  readStatus: () => boolean;
  readAlerts: () => boolean;
  stopVoice: () => void;
  repeatVoice: () => void;
  /** Callar la iniciativa propia un rato (`assistant/proactive.ts`), si está montada. */
  silence?: (ms: number) => void;
  /** Dejar de escuchar la palabra «EMMA» (`assistant/wake/`), si está montada. */
  stopListening?: () => void;
  /** El permiso del giroscopio (iOS), al encender «Seguir el sensor». */
  requestOrientation?: () => void;
  /** El inventario de la interfaz, si ya llegó del backend. */
  ui?: UiInventory | null;
}

/** Una escritura propuesta, pendiente de «confirmo». */
export interface PendingWrite {
  intent: WriteIntent;
  proposal: Record<string, unknown>;
}

export type IntentOutcome =
  | { kind: "done"; note: string | null }
  | { kind: "unknown"; note: string }
  | { kind: "unavailable"; note: string }
  | { kind: "proposal"; pending: PendingWrite }
  /** Un botón que guarda algo: no se pulsa hasta «confirmo» (`assistant/controls.ts`). */
  | { kind: "press"; label: string };

/** Los ids del inventario de los paneles a los que llevan las intenciones de siempre. */
export const PANEL_IDS = {
  pvt: "pvt",
  cognition: "cognition",
  guides: "guides",
  glossary: "glossary",
} as const;

/**
 * Sin tildes, en minúsculas, sin signos: para comparar palabras dichas o escritas. Vale igual en
 * los dos idiomas de la interfaz: al inglés no le quita nada (el apóstrofo pasa a espacio).
 */
export function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9ñ ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * La pestaña que se pide, entre las que están a la vista: por su clave, por uno de sus otros
 * nombres del inventario («radiación» está en «Misión y hábitat») o por su rótulo (sin tildes,
 * entero o como comienzo). `null` si no está a la vista.
 */
export function resolveTab(
  console: "crew" | "ground",
  requested: string,
  tabs: readonly TabRef[],
  ui: UiInventory | null = null,
): string | null {
  const wanted = normalize(requested);
  if (wanted === "") return null;
  const keys = tabs.map((tab) => tab.key);
  if (keys.includes(requested)) return requested;
  const named = ui?.sections[console].find((section) => section.aliases.includes(wanted));
  if (named !== undefined && keys.includes(named.key)) return named.key;
  const byLabel = tabs.find((tab) => {
    const label = normalize(tab.label);
    return label === wanted || label.startsWith(wanted) || normalize(tab.key) === wanted;
  });
  return byLabel?.key ?? null;
}

/**
 * Dónde abrir un panel desde esta consola: un sitio suyo en esta consola si lo tiene y está a la
 * vista (el modo esencial oculta pestañas), y si no, uno de la otra consola. `null` si en esta
 * consola solo está en pestañas ocultas.
 */
export function placeFor(panel: UiPanel, console: "crew" | "ground", tabs: readonly TabRef[]): UiPlace | null {
  const keys = tabs.map((tab) => tab.key);
  const here = panel.places.filter((place) => place.console === console);
  if (here.length === 0) return panel.places[0] ?? null;
  return (
    here.find(
      (place) =>
        place.section === null ||
        (place.section === "env-*" ? keys.some((key) => key.startsWith("env-")) : keys.includes(place.section)),
    ) ?? null
  );
}

const MINUTE_MS = 60_000;
/** «EMMA, silencio» sin decir cuánto: un cuarto de hora. */
export const DEFAULT_SILENCE_MINUTES = 15;

function flag(args: Record<string, unknown>, name: string): boolean | null {
  const value = args[name];
  return typeof value === "boolean" ? value : null;
}

function nextRotation(current: Rotation, args: Record<string, unknown>): Rotation {
  const degrees = args.degrees;
  const absolute = ROTATIONS.find((item) => item === degrees);
  if (absolute !== undefined) return absolute;
  const index = ROTATIONS.indexOf(current);
  return ROTATIONS[(index + 1) % ROTATIONS.length] ?? 0;
}

const NOT_SHOWN = tr("Esa sección no está a la vista en esta consola.", "That section is not in view on this console.");
const NOTHING_TO_READ = tr(
  "No hay nada que leer o la voz no está disponible.",
  "There is nothing to read or the voice is not available.",
);
const NO_INVENTORY = tr(
  "Todavía no sé dónde está cada panel; vuelve a pedirlo en un momento.",
  "I do not know yet where each panel is; ask again in a moment.",
);
const NO_PANEL = tr("No conozco ese panel; no hago nada.", "I do not know that panel; I am doing nothing.");
const NO_MORE_PANELS = tr("No hay más paneles en esta pestaña.", "There are no more panels in this tab.");
export const NO_BUTTON = tr(
  "Ese botón ya no está a la vista; no pulso nada.",
  "That button is no longer in view; I am pressing nothing.",
);
const SENSES_PRIVATE = tr(
  "Con la privacidad puesta no se encienden ni la cámara ni el micrófono.",
  "With privacy on, neither the camera nor the microphone is turned on.",
);
const SCROLLS: readonly ScrollDirection[] = ["up", "down", "top", "bottom"];

/**
 * Hace una intención de lectura con lo que ya hay, o devuelve la propuesta de una de escritura sin
 * firmar nada. Una intención fuera de la lista no hace nada y lo dice.
 */
export function executeIntent(turn: AssistantTurn, effects: IntentEffects): IntentOutcome {
  const { intent } = turn;
  const args = turn.args ?? {};
  if (isWriteIntent(intent)) {
    if (turn.proposal === null || typeof turn.proposal !== "object") {
      return {
        kind: "unavailable",
        note: tr(
          "No llegó ninguna propuesta que firmar; no se firma nada.",
          "No proposal to sign arrived; nothing is signed.",
        ),
      };
    }
    return { kind: "proposal", pending: { intent, proposal: turn.proposal } };
  }
  if (!isReadIntent(intent)) {
    return {
      kind: "unknown",
      note: tr("No conozco esa orden; no hago nada.", "I do not know that request; I am doing nothing."),
    };
  }
  const ui = effects.ui ?? null;
  const open = (requested: string): IntentOutcome => {
    if (requested === "crew" || requested === "ground") {
      effects.switchConsole(requested);
      return { kind: "done", note: null };
    }
    const key = resolveTab(effects.console, requested, effects.tabs(), ui);
    if (key === null) return { kind: "unavailable", note: NOT_SHOWN };
    effects.openTab(key);
    return { kind: "done", note: null };
  };
  /** Lleva a la vista un panel del inventario (y lo lee, con `read`). */
  const toPanel = (id: string, read = false): IntentOutcome => {
    if (ui === null) return { kind: "unavailable", note: NO_INVENTORY };
    const panel = ui.panels.find((item) => item.id === id);
    if (panel === undefined) return { kind: "unknown", note: NO_PANEL };
    const place = placeFor(panel, effects.console, effects.tabs());
    if (place === null) return { kind: "unavailable", note: NOT_SHOWN };
    if (read) {
      return effects.readPanel(panel.id, place)
        ? { kind: "done", note: null }
        : { kind: "unavailable", note: NOTHING_TO_READ };
    }
    effects.revealPanel(panel.id, place);
    return { kind: "done", note: null };
  };
  switch (intent) {
    case "none":
      return { kind: "done", note: null };
    case "press": {
      // Se busca otra vez por su rótulo: el botón pudo irse entre que se dijo y se contestó.
      const label = typeof args.control === "string" ? args.control : "";
      const button = label === "" ? null : findControl(label);
      if (button === null) return { kind: "unavailable", note: NO_BUTTON };
      // Lo que guarda espera a «confirmo», lo diga el backend o lo diga el propio botón.
      if (turn.needs_confirmation || controlWrites(button)) return { kind: "press", label };
      pressControl(label);
      return { kind: "done", note: null };
    }
    case "open_tab": {
      const section = typeof args.section === "string" ? args.section : "";
      return open(section);
    }
    case "open_panel":
    case "read_panel":
      return toPanel(typeof args.panel === "string" ? args.panel : "", intent === "read_panel");
    case "next_panel":
    case "previous_panel":
      return effects.stepPanel(intent === "next_panel" ? 1 : -1)
        ? { kind: "done", note: null }
        : { kind: "unavailable", note: NO_MORE_PANELS };
    case "scroll": {
      const direction = SCROLLS.find((item) => item === args.direction) ?? "down";
      effects.scroll(direction);
      return { kind: "done", note: null };
    }
    case "switch_console": {
      const to = args.console === "crew" || args.console === "ground" ? args.console : null;
      effects.switchConsole(to ?? (effects.console === "crew" ? "ground" : "crew"));
      return { kind: "done", note: null };
    }
    case "toggle_mode": {
      const mode = TOGGLE_MODES.find((item) => item === args.mode);
      if (mode === undefined) {
        return {
          kind: "unknown",
          note: tr(
            "No conozco ese modo de pantalla; no hago nada.",
            "I do not know that display mode; I am doing nothing.",
          ),
        };
      }
      const on = flag(args, "on") ?? !effects.modes[mode];
      if (on && effects.modes.privacy && SENSES.includes(mode)) return { kind: "unavailable", note: SENSES_PRIVATE };
      if (on && mode === "followSensor") effects.requestOrientation?.();
      effects.updateModes({ [mode]: on });
      return { kind: "done", note: null };
    }
    case "read_status":
      return effects.readStatus() ? { kind: "done", note: null } : { kind: "unavailable", note: NOTHING_TO_READ };
    case "read_alerts":
      return effects.readAlerts() ? { kind: "done", note: null } : { kind: "unavailable", note: NOTHING_TO_READ };
    case "read_routines": {
      // Las rutinas las lee la `reply` del backend; aquí solo se abre su pestaña, si la hay.
      if (effects.console === "crew") open("routines");
      return { kind: "done", note: null };
    }
    case "rotate":
      effects.updateModes({ rotation: nextRotation(effects.modes.rotation, args) });
      return { kind: "done", note: null };
    case "privacy":
      effects.updateModes({ privacy: flag(args, "on") ?? !effects.modes.privacy });
      return { kind: "done", note: null };
    case "low_vision":
      effects.updateModes({ lowVision: flag(args, "on") ?? !effects.modes.lowVision });
      return { kind: "done", note: null };
    case "essential":
      effects.updateModes({ essential: flag(args, "on") ?? !effects.modes.essential });
      return { kind: "done", note: null };
    case "stop_voice":
      effects.stopVoice();
      return { kind: "done", note: null };
    case "repeat_voice":
      effects.repeatVoice();
      return { kind: "done", note: null };
    case "open_guide":
      return toPanel(PANEL_IDS.guides);
    case "open_glossary":
      return toPanel(PANEL_IDS.glossary);
    case "start_pvt":
    case "start_cognition":
      if (effects.console !== "crew") {
        return {
          kind: "unavailable",
          note: tr("Esa prueba se hace desde la consola de tripulación.", "That test is taken from the crew console."),
        };
      }
      return toPanel(intent === "start_pvt" ? PANEL_IDS.pvt : PANEL_IDS.cognition);
    case "silence": {
      if (effects.silence === undefined) {
        return {
          kind: "unavailable",
          note: tr(
            "Los avisos por iniciativa propia no están disponibles.",
            "Notices on EMMA's own initiative are not available.",
          ),
        };
      }
      const minutes = typeof args.minutes === "number" && args.minutes > 0 ? args.minutes : DEFAULT_SILENCE_MINUTES;
      effects.silence(minutes * MINUTE_MS);
      return { kind: "done", note: null };
    }
    case "stop_listening":
      if (effects.stopListening === undefined) {
        return {
          kind: "unavailable",
          note: tr(
            "La escucha de la palabra «EMMA» no está disponible.",
            "Listening for the word “EMMA” is not available.",
          ),
        };
      }
      effects.stopListening();
      return { kind: "done", note: null };
  }
}

/** Un campo de la propuesta a la vista: su nombre y su valor ya escrito. */
export interface ProposalField {
  name: string;
  value: string;
}

function valueText(value: unknown): string {
  if (typeof value === "number") {
    // Las cifras, por `lib/format.ts`, con los decimales que hacen falta para que lo que se lee
    // sea lo que se firma; si ni con diez lo es (1e-12), la cifra tal cual.
    if (!Number.isFinite(value)) return String(value);
    for (let decimals = 0; decimals <= 10; decimals += 1) {
      if (Number(value.toFixed(decimals)) === value) return formatNumber(value, decimals);
    }
    return String(value);
  }
  if (typeof value === "boolean") return value ? tr("sí", "yes") : "no";
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

/**
 * La propuesta campo a campo, como llegará a la ruta (sin el de quien firma, que pone la consola).
 * Lo anidado (las zonas de un dolor) va con su camino: «zones 1 · intensity».
 */
export function proposalFields(pending: PendingWrite): ProposalField[] {
  const signer = WRITE_ROUTES[pending.intent].signer;
  const out: ProposalField[] = [];
  const walk = (prefix: string, value: unknown) => {
    if (Array.isArray(value)) {
      if (value.every((item) => typeof item !== "object" || item === null)) {
        out.push({ name: prefix, value: value.map(valueText).join(", ") });
        return;
      }
      value.forEach((item, index) => walk(`${prefix} ${formatNumber(index + 1)}`, item));
      return;
    }
    if (typeof value === "object" && value !== null) {
      for (const [name, inner] of Object.entries(value as Record<string, unknown>)) {
        walk(prefix === "" ? name : `${prefix} · ${name}`, inner);
      }
      return;
    }
    out.push({ name: prefix, value: valueText(value) });
  };
  for (const [name, value] of Object.entries(pending.proposal)) {
    if (name === signer) continue;
    walk(name, value);
  }
  return out;
}

/** Lo que se dice al llegar una propuesta: cada campo y cómo seguir. */
export function proposalSpeech(fields: readonly ProposalField[]): string[] {
  const list = fields.map((field) => `${field.name}: ${field.value}`).join(". ");
  return [
    tr(`Propuesta sin firmar. ${list}.`, `Unsigned proposal. ${list}.`),
    tr(
      "Diga «confirmo» para firmarla o «cancela» para descartarla.",
      "Say “confirm” to sign it or “cancel” to discard it.",
    ),
  ];
}

/**
 * Las palabras con que se confirma o se cancela en cada idioma, ya normalizadas (`normalize`). Son
 * las que dicen los rótulos de la consola («Diga «confirmo»…», “Say “confirm”…”). Un «sí» o un
 * «yes» a secas no firma: confirmar es decir la palabra.
 */
export const CONFIRMATION_WORDS: Record<Language, { confirm: RegExp; cancel: RegExp }> = {
  es: {
    confirm: /^(si |vale )?(confirmo|confirmar|confirma|confirmado)$/,
    cancel: /^(cancela|cancelar|cancelo|cancelado|no|descarta|descartar)$/,
  },
  en: {
    confirm: /^(yes |ok |okay )?(i )?(confirm|confirm it|confirmed)$/,
    cancel: /^(cancel|cancel it|cancelled|canceled|no|discard|discard it)$/,
  },
};

/**
 * Los idiomas cuyas palabras valen con cada idioma de la interfaz. En castellano, solo las
 * castellanas, como siempre. En inglés valen además las castellanas: mientras el backend no
 * transcriba ni conteste en inglés (su reconocimiento de voz puede devolver «confirmo» a quien
 * dijo “confirm”, y su pregunta puede pedir «confirmo»), rechazarlas dejaría una propuesta sin
 * poder firmarse ni descartarse de palabra. Ninguna castellana es una palabra inglesa con otro
 * sentido.
 */
const ACCEPTED_WORDS: Record<Language, readonly Language[]> = { es: ["es"], en: ["en", "es"] };

/** Lo que dice la persona ante una propuesta: confirmar, cancelar, u otra cosa (`null`). */
export function confirmationWord(text: string): "confirm" | "cancel" | null {
  const words = normalize(text).replace(/^emma /, "");
  const accepted = ACCEPTED_WORDS[language()].map((lang) => CONFIRMATION_WORDS[lang]);
  if (accepted.some(({ confirm }) => confirm.test(words))) return "confirm";
  if (accepted.some(({ cancel }) => cancel.test(words))) return "cancel";
  return null;
}

/** El cuerpo firmado, o por qué no se firma. */
export type SignedRequest =
  | { ok: true; intent: WriteIntent; path: string; body: Record<string, unknown> }
  | { ok: false; reason: string };

/**
 * El cuerpo que va a la ruta del formulario: la propuesta, con quien firma de la consola y, en las
 * rutas que lo llevan, el tripulante que se está viendo. Sin operador no se firma. Una propuesta
 * de otro tripulante tampoco: la consola no firma en nombre de quien no se ve.
 */
export function signedRequest(pending: PendingWrite, operator: string, subject: string): SignedRequest {
  const route = WRITE_ROUTES[pending.intent];
  const who = operator.trim();
  if (who === "") {
    return {
      ok: false,
      reason: tr(
        "Sin tripulante en consola no se firma. Escriba quién está en la consola y vuelva a pedirlo.",
        "Nothing is signed without a crew member at the console. Enter who is at the console and ask again.",
      ),
    };
  }
  const body: Record<string, unknown> = { ...pending.proposal };
  if (route.subject) {
    if (body.subject !== undefined && body.subject !== subject) {
      return {
        ok: false,
        reason: tr(
          "La propuesta es de otro tripulante; no se firma.",
          "The proposal is for another crew member; it is not signed.",
        ),
      };
    }
    body.subject = subject;
  }
  body[route.signer] = who;
  return { ok: true, intent: pending.intent, path: route.path, body };
}

/**
 * Manda un cuerpo ya firmado por la función de `lib/api.ts` del formulario de siempre: la misma
 * ruta, la misma validación del backend y el mismo ledger (invariante 4).
 */
export async function sendSigned(request: Extract<SignedRequest, { ok: true }>): Promise<void> {
  const body = request.body as never;
  switch (request.intent) {
    case "diary_entry":
      await diaryApi.record(body);
      return;
    case "pain_report":
      await api.pain.record(body);
      return;
    case "acknowledge_alert":
      await api.acknowledge(body);
      return;
    case "mission_level":
      await api.setMissionMode(body);
      return;
    case "mission_profile":
      await missionProfileApi.set(body);
      return;
    case "safe_mode":
      await api.setSafeMode(body);
      return;
  }
}
