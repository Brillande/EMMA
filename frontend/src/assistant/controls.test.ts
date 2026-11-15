/**
 * Los botones que se le dicen al asistente y cómo se pulsan (`controls.ts`), sin navegador: un
 * DOM mínimo de mentira con lo que esas funciones miran de cada botón.
 */

import { afterEach, describe, expect, it } from "vitest";

import type { AssistantTurn } from "../lib/api";
import { controlLabel, findControl, pressControl, sameLabel, visibleControls } from "./controls";
import { type IntentEffects, executeIntent } from "./intents";

interface FakeButton {
  text: string;
  disabled?: boolean;
  view?: boolean;
  hidden?: boolean;
  tab?: boolean;
  clicks: number;
}

function button(text: string, extra: Partial<FakeButton> = {}): FakeButton {
  return { text, clicks: 0, ...extra };
}

function root(buttons: FakeButton[]): ParentNode {
  const elements = buttons.map((item) => ({
    disabled: item.disabled ?? false,
    textContent: item.text,
    getAttribute: (name: string) => (name === "role" && item.tab ? "tab" : null),
    closest: (selector: string) => {
      if (selector === "[data-ui-view]") return item.view ? {} : null;
      if (selector.includes("[hidden]")) return item.hidden ? {} : null;
      return null;
    },
    getClientRects: () => (item.hidden ? [] : [{}]),
    scrollIntoView: () => undefined,
    focus: () => undefined,
    click: () => {
      item.clicks += 1;
    },
  }));
  return { querySelectorAll: () => elements } as unknown as ParentNode;
}

const turn = (label: string, needs = false): AssistantTurn => ({
  intent: "press",
  args: { control: label },
  reply: "",
  reply_source: "fixed",
  needs_confirmation: needs,
  proposal: null,
  checks: { text_guard: true, numbers: true, no_prescription: true, schema: true },
  label: null,
});

afterEach(() => {
  delete (globalThis as { document?: unknown }).document;
});

describe("los botones a la vista", () => {
  it("se mandan con su rótulo y si guardan, sin desactivados, ocultos, pestañas ni repetidos", () => {
    const shown = root([
      button("  Abdomen:\n hígado 1 "),
      button("Visor de Polaris", { view: true }),
      button("Segmentar", { disabled: true }),
      button("Oculto", { hidden: true }),
      button("Cuerpo", { tab: true }),
      button("Abdomen: hígado 1"),
    ]);
    expect(visibleControls(shown)).toEqual([
      { label: "Abdomen: hígado 1", writes: true },
      { label: "Visor de Polaris", writes: false },
    ]);
  });

  it("se encuentran por su rótulo sin mayúsculas, tildes ni puntuación", () => {
    expect(sameLabel("Abdomen: hígado 1", "abdomen higado 1")).toBe(true);
    expect(sameLabel("Abdomen: hígado 1", "Abdomen: hígado 2")).toBe(false);
    const shown = root([button("Render de Polaris")]);
    expect(findControl("render de polaris", shown)).not.toBeNull();
    expect(findControl("Visor", shown)).toBeNull();
    expect(controlLabel({ getAttribute: () => "Cerrar", textContent: "×" } as unknown as HTMLElement)).toBe("Cerrar");
  });

  it("se pulsan una vez, y si ya no están no se pulsa nada", () => {
    const render = button("Render de Polaris");
    const shown = root([render]);
    expect(pressControl("Render de Polaris", shown)).toBe(true);
    expect(render.clicks).toBe(1);
    expect(pressControl("Visor de Polaris", shown)).toBe(false);
  });
});

describe("la intención de pulsar", () => {
  const effects = {} as IntentEffects;

  it("pulsa al momento lo que solo cambia la vista", () => {
    const visor = button("Visor de Polaris", { view: true });
    (globalThis as { document?: unknown }).document = root([visor]);
    expect(executeIntent(turn("Visor de Polaris"), effects)).toEqual({ kind: "done", note: null });
    expect(visor.clicks).toBe(1);
  });

  it("no pulsa lo que guarda: espera a «confirmo», lo diga el backend o el propio botón", () => {
    const sample = button("Abdomen: hígado 1");
    const visor = button("Visor de Polaris", { view: true });
    (globalThis as { document?: unknown }).document = root([sample, visor]);
    expect(executeIntent(turn("Abdomen: hígado 1"), effects)).toEqual({ kind: "press", label: "Abdomen: hígado 1" });
    expect(executeIntent(turn("Visor de Polaris", true), effects)).toEqual({ kind: "press", label: "Visor de Polaris" });
    expect(sample.clicks + visor.clicks).toBe(0);
  });

  it("un botón que ya no está no se pulsa y lo dice", () => {
    (globalThis as { document?: unknown }).document = root([]);
    expect(executeIntent(turn("Abdomen: hígado 1"), effects).kind).toBe("unavailable");
  });
});
