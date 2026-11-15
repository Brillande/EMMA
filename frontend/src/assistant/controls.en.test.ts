/**
 * Los botones por voz con la interfaz en inglés (`controls.ts`): el rótulo que se manda al backend
 * es el que el botón tiene en pantalla (ya en inglés), y se vuelve a encontrar con ese mismo
 * rótulo, lo devuelva el backend tal cual o como lo deja su `plain` (minúsculas, sin signos). Nada
 * de `controls.ts` sabe de idiomas: esta prueba fija que siga así.
 */
import "../test/english";

import { afterEach, describe, expect, it } from "vitest";

import type { AssistantTurn } from "../lib/api";
import { controlLabel, findControl, pressControl, sameLabel, visibleControls } from "./controls";
import { type IntentEffects, confirmationWord, executeIntent } from "./intents";

interface FakeButton {
  text: string;
  aria?: string;
  view?: boolean;
  clicks: number;
}

const button = (text: string, extra: Partial<FakeButton> = {}): FakeButton => ({ text, clicks: 0, ...extra });

function root(buttons: FakeButton[]): ParentNode {
  const elements = buttons.map((item) => ({
    disabled: false,
    textContent: item.text,
    getAttribute: (name: string) => (name === "aria-label" ? (item.aria ?? null) : null),
    closest: (selector: string) => (selector === "[data-ui-view]" && item.view ? {} : null),
    getClientRects: () => [{}],
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

describe("ida y vuelta de un rótulo inglés", () => {
  const buttons = () => [
    button("  Abdomen:\n liver 1 "),
    button("Polaris viewer", { view: true }),
    button("×", { aria: "Close the crew member's panel" }),
    button("Don't show again", { view: true }),
  ];

  it("lo que se manda es lo que se lee, en una línea, con si guarda", () => {
    expect(visibleControls(root(buttons()))).toEqual([
      { label: "Abdomen: liver 1", writes: true },
      { label: "Polaris viewer", writes: false },
      { label: "Close the crew member's panel", writes: true },
      { label: "Don't show again", writes: false },
    ]);
  });

  it("cada rótulo mandado se vuelve a encontrar: tal cual, en minúsculas y sin signos", () => {
    const shown = root(buttons());
    for (const { label } of visibleControls(shown)) {
      const found = findControl(label, shown);
      expect(found, label).not.toBeNull();
      expect(controlLabel(found as HTMLElement)).toBe(label);
      expect(findControl(label.toLowerCase(), shown), label).toBe(found);
      expect(findControl(label.replace(/[^A-Za-z0-9]+/g, " ").trim().toLowerCase(), shown), label).toBe(found);
    }
    expect(sameLabel("Don't show again", "dont show again")).toBe(false);
    expect(sameLabel("Abdomen: liver 1", "Abdomen: liver 2")).toBe(false);
  });

  it("lo que solo cambia la vista se pulsa al momento; lo que guarda espera a «confirm»", () => {
    const list = buttons();
    (globalThis as { document?: unknown }).document = root(list);
    const effects = {} as IntentEffects;
    expect(executeIntent(turn("polaris viewer"), effects)).toEqual({ kind: "done", note: null });
    expect(list[1]?.clicks).toBe(1);
    expect(executeIntent(turn("Abdomen: liver 1"), effects)).toEqual({ kind: "press", label: "Abdomen: liver 1" });
    expect(list[0]?.clicks).toBe(0);
    // La palabra que lo confirma es la inglesa; la pulsación la hace el mismo rótulo.
    expect(confirmationWord("confirm")).toBe("confirm");
    expect(pressControl("Abdomen: liver 1")).toBe(true);
    expect(list[0]?.clicks).toBe(1);
    const gone = executeIntent(turn("Save reading"), effects);
    expect(gone).toEqual({ kind: "unavailable", note: "That button is no longer in view; I am pressing nothing." });
  });
});
