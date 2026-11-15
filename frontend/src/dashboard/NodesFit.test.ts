import { describe, expect, it } from "vitest";

import { FIT_MIN, NODES_FIT_KEY, nextZoom, readNodesFit, writeNodesFit } from "./NodesFit";

function memory(initial: Record<string, string> = {}) {
  const items = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
    removeItem: (key: string) => void items.delete(key),
  };
}

describe("«Ajustar a pantalla» de «Distancia y nodos»", () => {
  it("encoge lo justo para caber: el alto libre entre el alto natural", () => {
    // 1000 px a zoom 1 en 950 libres: 0,95.
    expect(nextZoom(950, 1000, 1)).toBeCloseTo(0.95, 5);
    // Medido ya con zoom 0,96 (960 px), el natural sigue siendo 1000.
    expect(nextZoom(950, 960, 0.96)).toBeCloseTo(0.95, 5);
  });

  it("nunca agranda ni baja de su mínimo, que deja la letra legible (unos 12,6 px de 14)", () => {
    expect(FIT_MIN * 14).toBeGreaterThanOrEqual(12.5);
    expect(nextZoom(2000, 1000, 1)).toBe(1);
    expect(nextZoom(100, 5000, 1)).toBe(FIT_MIN);
  });

  it("sin medida (pestaña escondida) no encoge", () => {
    expect(nextZoom(900, 0, 1)).toBe(1);
    expect(nextZoom(0, 1800, 1)).toBe(1);
  });

  it("viene puesto, y la elección de quitarlo se guarda en el equipo", () => {
    const store = memory();
    expect(readNodesFit(store)).toBe(true);
    writeNodesFit(store, false);
    expect(store.getItem(NODES_FIT_KEY)).toBe("false");
    expect(readNodesFit(store)).toBe(false);
    expect(readNodesFit(null)).toBe(true);
  });
});
