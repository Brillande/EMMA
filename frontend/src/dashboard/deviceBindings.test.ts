import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { DeviceBindingsNotice } from "../lib/api";
import { qualityStyle } from "../lib/provenance";
import { deviceBindingsView } from "./deviceBindings";

const notice = (over: Partial<DeviceBindingsNotice>): DeviceBindingsNotice => ({
  kind: "none",
  label: "declarado por una persona",
  readings: 0,
  with_device: 0,
  mismatched: 0,
  groups: [],
  indicators: [],
  since: null,
  text: null,
  analysis_note: null,
  device_note: null,
  ...over,
});

const SAID =
  "2 de 4 lecturas de wearable de los últimos 2 días llegaron para crew-02 desde un " +
  "dispositivo que en su instante constaba vinculado a otro tripulante. EMMA las analiza " +
  "igual; decidir si son de este tripulante es de una persona.";

describe("el aviso de sensor vinculado a otro tripulante, en la calidad del dato", () => {
  it("sin vínculos declarados no pinta nada: es el caso normal", () => {
    expect(deviceBindingsView(notice({}))).toBeNull();
  });

  it("con vínculos y ninguna lectura señalada, la frase del backend va sin señal", () => {
    const view = deviceBindingsView(notice({ text: "Ninguna lectura…" }));
    expect(view).toEqual({ text: "Ninguna lectura…", note: null, style: null });
  });

  it("una lectura señalada lleva la señal de baja confianza, no la de una alerta", () => {
    const view = deviceBindingsView(
      notice({ kind: "bound-to-other-crew", mismatched: 2, text: SAID, device_note: "abreviado" }),
    );
    expect(view).toEqual({ text: SAID, note: "abreviado", style: qualityStyle("low") });
    // Es un aviso sobre el dato: la señal de «baja confianza», nunca la de una alerta grave.
    expect(view?.style?.color).not.toBe("red");
  });

  it("no haber podido comparar también se dice, con la misma señal", () => {
    const view = deviceBindingsView(
      notice({ kind: "not-checked", mismatched: null, text: "No se ha podido comparar…" }),
    );
    expect(view?.style).toEqual(qualityStyle("low"));
    expect(view?.text).toBe("No se ha podido comparar…");
  });

  it("un tipo de aviso desconocido falla en vez de callar", () => {
    const odd = notice({ text: "?" });
    (odd as { kind: string }).kind = "inventado";
    expect(() => deviceBindingsView(odd)).toThrow(/desconocido/);
  });

  it("no redacta: la frase es la del backend y el módulo no lleva texto clínico", () => {
    const path = fileURLToPath(new URL("./deviceBindings.ts", import.meta.url));
    const source = readFileSync(path, "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    for (const word of ["vinculado", "tripulante", "lectura", "analiza"]) {
      expect(code).not.toContain(word);
    }
  });
});
