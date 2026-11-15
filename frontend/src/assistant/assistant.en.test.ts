/**
 * El asistente con la interfaz en inglés (`lib/i18n.ts`): las pestañas y los paneles se encuentran
 * por los nombres ingleses del inventario, se confirma y se cancela con palabras inglesas, y lo que
 * la consola dice y pinta por su cuenta está en inglés.
 *
 * El inventario lo servirá el backend ya en el idioma de la petición (`GET /api/assistant`); aquí
 * se compone igual que lo hará él: la estructura de `assistant_ui.json` con el rótulo y los alias
 * de `assistant_ui.en.json`, emparejados por id. La interfaz no lee el `.en.json`: solo esta prueba.
 */
import "../test/english";

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { DEFAULT_MODES } from "../components/displayModes";
import type { AssistantInfo, AssistantTurn, UiInventory } from "../lib/api";
import { ASSISTANT_TITLE, AssistantView, type AssistantViewProps, TALK_UNAVAILABLE_TEXT, TOGGLE_TEXT } from "./Assistant";
import {
  CONFIRMATION_WORDS,
  type IntentEffects,
  confirmationWord,
  executeIntent,
  normalize,
  placeFor,
  proposalFields,
  proposalSpeech,
  resolveTab,
  signedRequest,
} from "./intents";

const json = (name: string) =>
  JSON.parse(readFileSync(fileURLToPath(new URL(`../../../backend/app/data/${name}`, import.meta.url)), "utf8"));

interface Named {
  label?: string;
  aliases?: string[];
  about?: string;
}

/** El inventario en inglés, como lo compondrá el backend: estructura castellana, nombres ingleses. */
function englishInventory(): UiInventory {
  const es = json("assistant_ui.json") as UiInventory;
  const en = json("assistant_ui.en.json") as {
    consoles: Record<string, Named>;
    sections: { crew: Record<string, Named>; ground: Record<string, Named>; environments: Named };
    modes: Record<string, Named>;
    panels: Record<string, Named>;
  };
  return {
    consoles: es.consoles.map((item) => ({ ...item, ...en.consoles[item.id] })),
    sections: {
      crew: es.sections.crew.map((item) => ({ ...item, ...en.sections.crew[item.key] })),
      ground: es.sections.ground.map((item) => ({ ...item, ...en.sections.ground[item.key] })),
      environments: { ...es.sections.environments, ...en.sections.environments },
    },
    modes: es.modes.map((item) => ({ ...item, ...en.modes[item.id] })),
    panels: es.panels.map((item) => ({ ...item, ...en.panels[item.id] })),
  };
}

const UI = englishInventory();

/** Las pestañas a la vista en esta versión, con el rótulo inglés de `ConsoleTabs`. */
const CREW_TABS = [
  { key: "home", label: "Home" },
  { key: "radiation", label: "Radiation" },
  { key: "isolation", label: "Isolation" },
  { key: "gravity", label: "Gravity" },
  { key: "environment", label: "Environment" },
  { key: "nodes", label: "Distance and nodes" },
  { key: "hazards", label: "Hazards and alerts" },
];
const GROUND_TABS = [
  { key: "received", label: "Received status" },
  { key: "history", label: "History" },
  { key: "trends", label: "Trends" },
  { key: "habitat", label: "Habitat" },
  { key: "framework", label: "Framework and sources" },
  { key: "ledger", label: "Ledger and documents" },
  { key: "library", label: "Library" },
];

function turn(intent: string, extra: Partial<AssistantTurn> = {}): AssistantTurn {
  return {
    intent,
    args: {},
    reply: "Backend text.",
    reply_source: "backend",
    needs_confirmation: false,
    proposal: null,
    checks: { text_guard: true, numbers: true, no_prescription: true, schema: true },
    label: null,
    ...extra,
  };
}

function effects(overrides: Partial<IntentEffects> = {}) {
  const calls: string[] = [];
  const base: IntentEffects = {
    console: "crew",
    tabs: () => CREW_TABS,
    openTab: (key) => calls.push(`tab:${key}`),
    switchConsole: (to) => calls.push(`console:${to}`),
    revealPanel: (id, place) => calls.push(`panel:${id}@${place.console}:${place.section}`),
    readPanel: () => false,
    stepPanel: () => false,
    scroll: () => undefined,
    ui: UI,
    modes: { ...DEFAULT_MODES },
    updateModes: () => undefined,
    readStatus: () => false,
    readAlerts: () => false,
    stopVoice: () => undefined,
    repeatVoice: () => undefined,
    ...overrides,
  };
  return { base, calls };
}

const SPANISH = /[áéíóúñ¿¡«»]/i;

describe("el inventario inglés que se usa aquí", () => {
  it("trae nombre inglés para cada pestaña a la vista y conserva la estructura", () => {
    for (const tab of CREW_TABS) {
      expect(UI.sections.crew.find((item) => item.key === tab.key)?.label, tab.key).toBe(tab.label);
    }
    for (const tab of GROUND_TABS) {
      expect(UI.sections.ground.find((item) => item.key === tab.key)?.label, tab.key).toBe(tab.label);
    }
    expect(UI.panels.every((panel) => Array.isArray(panel.places))).toBe(true);
  });
});

describe("normalizar lo dicho", () => {
  it("al inglés no le quita nada: minúsculas, sin signos, el apóstrofo como espacio", () => {
    expect(normalize("Open the Hazards & Alerts tab, please!")).toBe("open the hazards alerts tab please");
    expect(normalize("  DON'T   stop ")).toBe("don t stop");
    expect(normalize("Distance and nodes")).toBe("distance and nodes");
  });
});

describe("la pestaña que se pide, en inglés", () => {
  it("por su clave, por su rótulo inglés entero o como comienzo, sin mayúsculas", () => {
    expect(resolveTab("crew", "radiation", CREW_TABS, UI)).toBe("radiation");
    expect(resolveTab("crew", "Hazards and alerts", CREW_TABS, UI)).toBe("hazards");
    expect(resolveTab("crew", "DISTANCE", CREW_TABS, UI)).toBe("nodes");
    expect(resolveTab("ground", "Framework and sources", GROUND_TABS, UI)).toBe("framework");
    // Sin inventario (aún no llegó), el rótulo de la pestaña basta.
    expect(resolveTab("ground", "ledger and documents", GROUND_TABS, null)).toBe("ledger");
  });

  it("por uno de sus otros nombres ingleses del inventario", () => {
    expect(resolveTab("crew", "dashboard", CREW_TABS, UI)).toBe("home");
    expect(resolveTab("crew", "main screen", CREW_TABS, UI)).toBe("home");
    expect(resolveTab("crew", "spectrum", CREW_TABS, UI)).toBe("radiation");
    expect(resolveTab("crew", "on board reserves", CREW_TABS, UI)).toBe("nodes");
    expect(resolveTab("ground", "charts", GROUND_TABS, UI)).toBe("trends");
    expect(resolveTab("ground", "glossary", GROUND_TABS, UI)).toBe("library");
  });

  it("todo alias inglés de una pestaña a la vista la encuentra, tal como está escrito", () => {
    for (const [consoleId, tabs] of [["crew", CREW_TABS], ["ground", GROUND_TABS]] as const) {
      const first = new Map<string, string>();
      for (const section of UI.sections[consoleId]) {
        for (const alias of section.aliases) if (!first.has(alias)) first.set(alias, section.key);
      }
      for (const tab of tabs) {
        const section = UI.sections[consoleId].find((item) => item.key === tab.key);
        for (const alias of section?.aliases ?? []) {
          // Un alias que la normalización cambiara no casaría nunca con lo dicho.
          expect(normalize(alias), alias).toBe(alias);
          if (first.get(alias) === tab.key) expect(resolveTab(consoleId, alias, tabs, UI), alias).toBe(tab.key);
        }
      }
    }
  });

  it("un nombre castellano ya no es de ninguna pestaña: no abre otra por error", () => {
    expect(resolveTab("crew", "peligros", CREW_TABS, UI)).toBeNull();
    expect(resolveTab("crew", "", CREW_TABS, UI)).toBeNull();
  });
});

describe("el ejecutor, en inglés", () => {
  it("abre la pestaña dicha por su otro nombre y un panel por su id", () => {
    const { base, calls } = effects();
    expect(executeIntent(turn("open_tab", { args: { section: "dashboard" } }), base)).toEqual({ kind: "done", note: null });
    const panel = UI.panels.find((item) => placeFor(item, "crew", CREW_TABS)?.console === "crew");
    expect(panel).toBeDefined();
    expect(executeIntent(turn("open_panel", { args: { panel: panel?.id } }), base).kind).toBe("done");
    expect(calls[0]).toBe("tab:home");
    expect(calls[1]?.startsWith(`panel:${panel?.id}@crew:`)).toBe(true);
  });

  it("lo que dice cuando no puede, en inglés y sin sonar a orden", () => {
    const { base } = effects();
    const notes = [
      executeIntent(turn("open_tab", { args: { section: "nowhere" } }), base),
      executeIntent(turn("open_panel", { args: { panel: "no-such-panel" } }), base),
      executeIntent(turn("open_panel", { args: { panel: "x" } }), { ...base, ui: null }),
      executeIntent(turn("read_status"), base),
      executeIntent(turn("next_panel"), base),
      executeIntent(turn("toggle_mode", { args: { mode: "nope" } }), base),
      executeIntent(turn("toggle_mode", { args: { mode: "wakeWord", on: true } }), {
        ...base,
        modes: { ...DEFAULT_MODES, privacy: true },
      }),
      executeIntent(turn("start_pvt"), { ...base, console: "ground", tabs: () => GROUND_TABS }),
      executeIntent(turn("silence"), base),
      executeIntent(turn("stop_listening"), base),
      executeIntent(turn("diary_entry"), base),
      executeIntent(turn("made_up"), base),
    ].map((outcome) => ("note" in outcome ? outcome.note : null));
    expect(notes).toEqual([
      "That section is not in view on this console.",
      "I do not know that panel; I am doing nothing.",
      "I do not know yet where each panel is; ask again in a moment.",
      "There is nothing to read or the voice is not available.",
      "There are no more panels in this tab.",
      "I do not know that display mode; I am doing nothing.",
      "With privacy on, neither the camera nor the microphone is turned on.",
      "That test is taken from the crew console.",
      "Notices on EMMA's own initiative are not available.",
      "Listening for the word “EMMA” is not available.",
      "No proposal to sign arrived; nothing is signed.",
      "I do not know that request; I am doing nothing.",
    ]);
  });
});

describe("confirmar y cancelar, en inglés", () => {
  it("«confirm» firma y «cancel» descarta; un «yes» a secas no firma", () => {
    for (const said of ["Confirm.", "EMMA, confirm", "yes, confirm", "OK, I confirm", "Confirmed", "confirm it"]) {
      expect(confirmationWord(said), said).toBe("confirm");
    }
    for (const said of ["Cancel", "cancel it", "No", "discard it", "EMMA, cancel."]) {
      expect(confirmationWord(said), said).toBe("cancel");
    }
    for (const said of ["yes", "do not confirm", "don't confirm", "confirm the alert", "note something else", ""]) {
      expect(confirmationWord(said), said).toBeNull();
    }
  });

  it("con la interfaz en inglés valen también las castellanas: el reconocimiento puede devolverlas", () => {
    expect(confirmationWord("Confirmo.")).toBe("confirm");
    expect(confirmationWord("cancela")).toBe("cancel");
    expect(confirmationWord("no confirmo")).toBeNull();
    // Cada tabla, solo lo suyo.
    expect(CONFIRMATION_WORDS.es.confirm.test("confirmo")).toBe(true);
    expect(CONFIRMATION_WORDS.es.confirm.test("confirm")).toBe(false);
    expect(CONFIRMATION_WORDS.en.confirm.test("confirmo")).toBe(false);
    expect(CONFIRMATION_WORDS.en.cancel.test("cancela")).toBe(false);
  });

  it("la propuesta se dice con sus campos tal cual y cómo seguir, con las mismas palabras que se aceptan", () => {
    const pending = { intent: "diary_entry" as const, proposal: { code: "mood-valence", value: 3, private: true } };
    const fields = proposalFields(pending);
    expect(fields).toContainEqual({ name: "private", value: "yes" });
    const speech = proposalSpeech(fields);
    expect(speech[0]).toBe("Unsigned proposal. code: mood-valence. value: 3. private: yes.");
    expect(speech[1]).toBe("Say “confirm” to sign it or “cancel” to discard it.");
    const quoted = [...(speech[1] ?? "").matchAll(/“([^”]+)”/g)].map((match) => match[1] ?? "");
    expect(quoted.map((word) => confirmationWord(word))).toEqual(["confirm", "cancel"]);
  });

  it("lo firmado no lleva nada traducido: el cuerpo es la propuesta y quien firma", () => {
    const pending = { intent: "diary_entry" as const, proposal: { code: "mood-valence", value: 3, private: true } };
    const request = signedRequest(pending, "ana", "crew-01");
    expect(request).toEqual({
      ok: true,
      intent: "diary_entry",
      path: "/diary/entries",
      body: { code: "mood-valence", value: 3, private: true, subject: "crew-01", recorded_by: "ana" },
    });
    const refused = signedRequest(pending, " ", "crew-01");
    expect(refused.ok === false && refused.reason).toBe(
      "Nothing is signed without a crew member at the console. Enter who is at the console and ask again.",
    );
    const other = signedRequest({ ...pending, proposal: { subject: "crew-02" } }, "ana", "crew-01");
    expect(other.ok === false && other.reason).toBe("The proposal is for another crew member; it is not signed.");
  });
});

describe("lo que se pinta, en inglés", () => {
  const info: AssistantInfo = { available: true, model: "m", reason: null, voice_available: true, intents: [], ui: UI };
  const props = (overrides: Partial<AssistantViewProps> = {}): AssistantViewProps => ({
    load: { state: "ready", info },
    open: true,
    onToggle: () => undefined,
    thread: [],
    privacy: false,
    mic: false,
    busy: false,
    talk: null,
    onTalk: () => undefined,
    draft: "",
    onDraft: () => undefined,
    onSend: () => undefined,
    pending: null,
    onConfirm: () => undefined,
    onCancel: () => undefined,
    failure: null,
    ...overrides,
  });
  const render = (overrides: Partial<AssistantViewProps> = {}) =>
    renderToStaticMarkup(createElement(AssistantView, props(overrides)));

  it("el título, los mandos y el atajo", () => {
    const html = render({ mic: true, thread: [{ role: "user", text: "how am I?" }] });
    const text = textNodes(html);
    expect(ASSISTANT_TITLE).toBe("EMMA (assistant)");
    expect(html).toContain('aria-label="EMMA (assistant)"');
    for (const label of ["Hide", "Microphone open", "Talk to EMMA", "You", "Write to EMMA", "Send", "hold to talk"]) {
      expect(text, label).toContain(label);
    }
    expect(html).toContain("<kbd>Ctrl+Space</kbd> hold to talk");
    expect(TOGGLE_TEXT).toEqual({ open: "Hide", closed: "Show" });
    expect(html).not.toMatch(SPANISH);
    expect(html).not.toMatch(/Hablar|Escribir|Enviar|Ocultar|Espacio/);
  });

  it("la propuesta y el botón por pulsar", () => {
    const proposal = render({ pending: { fields: [{ name: "value", value: "3" }], signer: "" } });
    expect(proposal).toContain('aria-label="Unsigned proposal"');
    for (const label of ["Unsigned proposal", "Signature", "no crew member at the console", "Confirm", "Cancel"]) {
      expect(textNodes(proposal), label).toContain(label);
    }
    const press = render({ pendingPress: "Save reading" });
    expect(press).toContain('aria-label="Button to press"');
    expect(textNodes(press)).toContain("Button to press, which saves to the ledger");
    expect(textNodes(press)).toContain("“Save reading”");
    expect(proposal + press).not.toMatch(SPANISH);
  });

  it("sin asistente o sin poder hablar, el motivo; el del backend, tal cual", () => {
    const off = render({ load: { state: "ready", info: { ...info, available: false, reason: "Ollama is not answering" } } });
    expect(textNodes(off)).toContain("Assistant unavailable: Ollama is not answering");
    const silent = render({ load: { state: "ready", info: { ...info, available: false, reason: null } } });
    expect(textNodes(silent)).toContain("Assistant unavailable: the backend gives no reason");
    expect(textNodes(render({ load: { state: "loading" } }))).toContain("Checking the assistant…");
    expect(textNodes(render({ talk: "no-voice" }))).toContain(TALK_UNAVAILABLE_TEXT["no-voice"]);
    for (const reason of Object.values(TALK_UNAVAILABLE_TEXT)) {
      expect(reason.startsWith("Talking unavailable: ")).toBe(true);
      expect(reason).not.toMatch(SPANISH);
    }
  });
});
