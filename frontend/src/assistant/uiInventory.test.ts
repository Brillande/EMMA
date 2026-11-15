import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { DEFAULT_MODES } from "../components/displayModes";
import type { AssistantTurn, UiInventory } from "../lib/api";
import { type IntentEffects, TOGGLE_MODES, executeIntent, placeFor } from "./intents";
import { ENV_SECTION, type Place, TRACKED_TAGS, openingTag, scan, withoutComments } from "./uiScan";
import { MAX_READ_LINES, MORE_ON_SCREEN, NAME_COVERED, type UiNode, readableLines, revealable } from "./uiTargets";

/**
 * Que la IA llegue a toda la interfaz, y solo para mirar: el inventario
 * (`backend/app/data/assistant_ui.json`) contra lo que de verdad montan las consolas, leído de sus
 * `.tsx` (`uiScan.ts`), como `dashboard/timelineMarks.test.ts` lee `timeline.py`. Un panel,
 * apartado o pliegue nuevo sin `data-ui` o sin entrada, una entrada de uno que ya no existe, un
 * panel que se muda de pestaña o un modo de pantalla nuevo hacen fallar estas pruebas: así ninguna
 * parte nueva de la interfaz se queda sin entrada para el asistente, y ninguna orden apunta en
 * silencio a algo que ya no está.
 */

const SRC = fileURLToPath(new URL("..", import.meta.url));
const UI = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../backend/app/data/assistant_ui.json", import.meta.url)), "utf8"),
) as UiInventory;
const found = scan();
const key = (place: Place) => `${place.console}:${place.section ?? "·"}`;

function tsxFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return tsxFiles(path);
    return name.endsWith(".tsx") ? [relative(SRC, path).replace(/\\/g, "/")] : [];
  });
}

describe("el inventario de la interfaz contra los .tsx de las consolas", () => {
  it("el recorrido encuentra las dos consolas enteras", () => {
    expect(found.files).toContain("dashboard/CrewConsole.tsx");
    expect(found.files).toContain("ground/GroundConsole.tsx");
    expect(found.files).toContain("components/ConsoleTabs.tsx");
    expect(found.elements.length).toBeGreaterThan(100);
  });

  it("cada panel, apartado y pliegue lleva un `data-ui` literal", () => {
    const missing = found.elements.filter((element) => element.uiId === null).map((e) => `${e.file}:${e.line} <${e.tag}>`);
    expect(missing).toEqual([]);
  });

  it("cada uno se sabe en qué consola y pestaña se monta", () => {
    const nowhere = found.elements.filter((element) => element.places.length === 0).map((e) => `${e.file}:${e.line}`);
    expect(nowhere).toEqual([]);
  });

  it("cada `data-ui` está en el inventario, y cada entrada del inventario sigue en el código", () => {
    const inCode = new Set(found.elements.map((element) => element.uiId ?? ""));
    const listed = new Set(UI.panels.map((panel) => panel.id));
    expect([...inCode].filter((id) => !listed.has(id)).sort()).toEqual([]);
    expect([...listed].filter((id) => !inCode.has(id)).sort()).toEqual([]);
    expect(listed.size).toBe(UI.panels.length);
  });

  it("el inventario dice dónde se monta cada uno, el mismo sitio que el código", () => {
    const wrong: string[] = [];
    for (const panel of UI.panels) {
      const code = new Set(found.elements.filter((e) => e.uiId === panel.id).flatMap((e) => e.places.map(key)));
      const listed = new Set(panel.places.map(key));
      const same = code.size === listed.size && [...code].every((place) => listed.has(place));
      if (!same) wrong.push(`${panel.id}: código ${[...code].sort().join(",")} · inventario ${[...listed].sort().join(",")}`);
    }
    expect(wrong).toEqual([]);
  });

  it("un pliegue es un pliegue y un apartado es un apartado", () => {
    const tags = new Map<string, Set<string>>();
    for (const element of found.elements) {
      const set = tags.get(element.uiId ?? "") ?? new Set();
      set.add(element.tag);
      tags.set(element.uiId ?? "", set);
    }
    for (const panel of UI.panels) {
      const seen = [...(tags.get(panel.id) ?? [])];
      if (panel.kind === "fold") expect(seen.every((tag) => tag === "Fold" || tag === "details"), panel.id).toBe(true);
      if (panel.kind === "part") expect(seen, panel.id).toEqual(["section"]);
    }
  });

  it("las pestañas del inventario son las de las tablas de las consolas, en su orden", () => {
    expect(UI.sections.crew.map((section) => section.key)).toEqual(found.sections.crew);
    expect(UI.sections.ground.map((section) => section.key)).toEqual(found.sections.ground);
    const sitios = UI.panels.flatMap((panel) => panel.places);
    for (const place of sitios) {
      if (place.section === null || place.section === ENV_SECTION) continue;
      expect(found.sections[place.console]).toContain(place.section);
    }
  });

  it("las pestañas apartadas de esta versión son las mismas en la consola y en el inventario", () => {
    const marked = (list: UiInventory["sections"]["crew"]) =>
      list.filter((section) => section.set_aside === true).map((section) => section.key);
    expect(marked(UI.sections.crew)).toEqual(found.setAside.crew);
    expect(marked(UI.sections.ground)).toEqual(found.setAside.ground);
    expect(found.setAside.crew).toEqual(["routines", "body", "mission", "data", "log", "imaging", "planner", "library"]);
    expect(found.setAside.ground).toEqual([]);
    // Lo que se queda: las alertas se reconocen en «Peligros y alertas», que no se aparta.
    expect(found.setAside.crew).not.toContain("hazards");
    expect(found.setAside.crew).not.toContain("home");
  });

  it("cada modo de pantalla tiene entrada, y cada entrada es un modo", () => {
    expect(UI.modes.map((mode) => mode.id).sort()).toEqual(Object.keys(DEFAULT_MODES).sort());
    expect(UI.modes.filter((mode) => mode.kind === "toggle").map((mode) => mode.id).sort()).toEqual(
      [...TOGGLE_MODES].sort(),
    );
    // Cada mando de la pantalla cambia un modo del inventario (y solo eso: `update` de los modos).
    const controls = ["components/DisplayControls.tsx", "components/ConsoleTabs.tsx"].map((file) =>
      withoutComments(readFileSync(join(SRC, file), "utf8")),
    );
    const changed = new Set(controls.flatMap((text) => [...text.matchAll(/update\(\{\s*(\w+)/g)].map((m) => m[1])));
    expect([...changed].filter((mode) => !UI.modes.some((item) => item.id === mode))).toEqual([]);
    expect(changed.size).toBeGreaterThanOrEqual(UI.modes.length - 1); // «proactive» va por ProactiveControls
  });
});

describe("la navegación no firma nada", () => {
  it("`data-ui` solo va en paneles y pliegues: nunca en un mando, un formulario o un botón de firmar", () => {
    const wrong: string[] = [];
    for (const file of tsxFiles(SRC)) {
      const text = withoutComments(readFileSync(join(SRC, file), "utf8"));
      for (const match of text.matchAll(/<([A-Za-z]\w*)\b/g)) {
        const opening = openingTag(text, match.index ?? 0);
        if (!/\bdata-ui=/.test(opening)) continue;
        if (!(TRACKED_TAGS as readonly string[]).includes(match[1] ?? "")) wrong.push(`${file}: <${match[1]}>`);
      }
    }
    expect(wrong).toEqual([]);
  });

  it("solo es destino un panel o un pliegue con `data-ui`, que no sea un mando ni esté dentro de uno", () => {
    const node = (tagName: string, attrs: Record<string, string>, inside: string[] = []): UiNode => ({
      tagName,
      getAttribute: (name) => attrs[name] ?? null,
      closest: (selector) =>
        [tagName.toLowerCase(), ...inside].some((tag) => selector.split(",").some((part) => part.trim().startsWith(tag)))
          ? {}
          : null,
    });
    expect(revealable(node("SECTION", { "data-ui": "dose" }))).toBe(true);
    expect(revealable(node("DETAILS", { "data-ui": "glossary" }, ["form"]))).toBe(true);
    expect(revealable(node("SECTION", {}))).toBe(false);
    expect(revealable(node("BUTTON", { "data-ui": "sign" }))).toBe(false);
    expect(revealable(node("FORM", { "data-ui": "diary" }))).toBe(false);
    expect(revealable(node("INPUT", { "data-ui": "x" }))).toBe(false);
    expect(revealable(node("DETAILS", { "data-ui": "x" }, ["button"]))).toBe(false);
  });

  it("lo único que pulsa el asistente es una pestaña", () => {
    const targets = withoutComments(readFileSync(join(SRC, "assistant/uiTargets.ts"), "utf8"));
    expect(targets.match(/\.click\(\)/g)).toHaveLength(1);
    expect(targets).toMatch(/getAttribute\("role"\) !== "tab"\) return false;\s*\n\s*if \(element\.getAttribute\("aria-selected"\) !== "true"\) element\.click\(\);/);
    for (const file of ["assistant/uiTargets.ts", "assistant/intents.ts", "App.tsx"]) {
      const text = withoutComments(readFileSync(join(SRC, file), "utf8"));
      expect(text, file).not.toMatch(/\.(?:requestSubmit|submit|dispatchEvent)\(/);
      if (file !== "assistant/uiTargets.ts") expect(text, file).not.toMatch(/\.click\(\)/);
    }
  });

  const turn = (intent: string, args: Record<string, unknown> = {}): AssistantTurn => ({
    intent,
    args,
    reply: "",
    reply_source: "fixed",
    needs_confirmation: false,
    proposal: { subject: "crew-01", note: "no se firma" },
    checks: { text_guard: false, numbers: false, no_prescription: false, schema: false },
    label: null,
  });

  it("abrir, leer, moverse y los modos nunca dan una propuesta, aunque llegue una", () => {
    const patches: Record<string, unknown>[] = [];
    const effects: IntentEffects = {
      console: "crew",
      tabs: () => UI.sections.crew.map((section) => ({ key: section.key, label: section.label })),
      openTab: () => undefined,
      switchConsole: () => undefined,
      revealPanel: () => undefined,
      readPanel: () => true,
      stepPanel: () => true,
      scroll: () => undefined,
      modes: DEFAULT_MODES,
      updateModes: (patch) => patches.push(patch),
      readStatus: () => true,
      readAlerts: () => true,
      stopVoice: () => undefined,
      repeatVoice: () => undefined,
      ui: UI,
    };
    const asked = [
      ...UI.panels.flatMap((panel) => [turn("open_panel", { panel: panel.id }), turn("read_panel", { panel: panel.id })]),
      ...TOGGLE_MODES.flatMap((mode) => [turn("toggle_mode", { mode, on: true }), turn("toggle_mode", { mode, on: false })]),
      turn("toggle_mode", { mode: "safe_mode", on: true }),
      turn("switch_console", { console: "ground" }),
      turn("scroll", { direction: "down" }),
      turn("next_panel"),
      turn("previous_panel"),
    ];
    for (const item of asked) expect(executeIntent(item, effects).kind, item.intent).not.toBe("proposal");
    // Los modos solo cambian modos de pantalla: nada del registro (el modo seguro no es uno).
    for (const patch of patches) for (const name of Object.keys(patch)) expect(Object.keys(DEFAULT_MODES)).toContain(name);
    expect(patches.some((patch) => "safe_mode" in patch)).toBe(false);
  });

  it("cada panel se puede abrir desde alguna consola", () => {
    const all = (console: "crew" | "ground") =>
      [...UI.sections[console].map((section) => ({ key: section.key, label: section.label })), { key: "env-mars-transit", label: "" }];
    for (const panel of UI.panels) {
      const reachable = placeFor(panel, "crew", all("crew")) ?? placeFor(panel, "ground", all("ground"));
      expect(reachable, panel.id).not.toBeNull();
    }
  });
});

describe("leer un panel", () => {
  it("línea a línea, sin repetir, con los nombres tapados y hasta un máximo", () => {
    expect(readableLines("Radiación\n\n  Dosis  hoy  0,6 mSv\nAna Pérez firmó\n", ["Ana Pérez"])).toEqual([
      "Radiación",
      "Dosis hoy 0,6 mSv",
      `${NAME_COVERED} firmó`,
    ]);
    const long = Array.from({ length: MAX_READ_LINES + 5 }, (_, index) => `línea ${index}`).join("\n");
    const lines = readableLines(long, []);
    expect(lines).toHaveLength(MAX_READ_LINES + 1);
    expect(lines.at(-1)).toBe(MORE_ON_SCREEN);
  });
});
