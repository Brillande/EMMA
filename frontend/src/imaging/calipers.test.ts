import { describe, expect, it } from "vitest";

import type { MeasureSpec } from "../lib/api";
import {
  addPoint,
  closeContour,
  currentStep,
  isComplete,
  startCalipers,
  stepsFor,
  toImagePoint,
  toRequest,
  undo,
} from "./calipers";

const ONSD: MeasureSpec = {
  name: "onsd",
  display: "Vaina",
  lateral: true,
  annotations: { globe: 1, sheath: 2 },
  instructions: { globe: "globo", sheath: "vaina" },
};

const IJV: MeasureSpec = {
  name: "ijv-csa",
  display: "Yugular",
  lateral: true,
  annotations: { contour: 0 },
  instructions: { contour: "contorno" },
};

describe("marcas guiadas", () => {
  it("siguen el orden del backend y avanzan al completar cada una", () => {
    let state = startCalipers(stepsFor(ONSD, 6));
    expect(currentStep(state)?.label).toBe("globe");
    expect(currentStep(state)?.instruction).toBe("globo");
    state = addPoint(state, [10, 10], 0);
    expect(currentStep(state)?.label).toBe("sheath");
    state = addPoint(state, [5, 13], 0);
    expect(isComplete(state)).toBe(false);
    state = addPoint(state, [15, 13], 0);
    expect(isComplete(state)).toBe(true);
    expect(toRequest(state, "onsd", "right", "CMO")).toEqual({
      measure: "onsd",
      laterality: "right",
      measured_by: "CMO",
      annotations: {
        globe: { frame: 0, points: [[10, 10]] },
        sheath: { frame: 0, points: [[5, 13], [15, 13]] },
      },
    });
  });

  it("no se envia una medida a medias", () => {
    const state = addPoint(startCalipers(stepsFor(ONSD, 6)), [1, 1], 0);
    expect(() => toRequest(state, "onsd", "right", "CMO")).toThrow();
  });

  it("una marca no mezcla puntos de dos fotogramas", () => {
    let state = startCalipers(stepsFor(ONSD, 6));
    state = addPoint(state, [10, 10], 0);
    state = addPoint(state, [5, 13], 0);
    state = addPoint(state, [7, 7], 3); // cambia de fotograma a mitad de la vaina
    expect(state.marks.sheath).toEqual({ frame: 3, points: [[7, 7]] });
    expect(isComplete(state)).toBe(false);
  });

  it("un contorno se cierra solo con los puntos minimos", () => {
    let state = startCalipers(stepsFor(IJV, 6));
    for (let i = 0; i < 5; i += 1) state = addPoint(state, [i, i * 2], 0);
    expect(isComplete(closeContour(state))).toBe(false);
    state = addPoint(state, [9, 1], 0);
    expect(isComplete(state)).toBe(false); // un contorno no se cierra solo
    expect(isComplete(closeContour(state))).toBe(true);
  });

  it("deshacer quita el ultimo punto y vuelve a la marca anterior", () => {
    let state = startCalipers(stepsFor(ONSD, 6));
    state = addPoint(state, [10, 10], 0);
    state = undo(state); // la vaina esta vacia: vuelve al globo y lo quita
    expect(currentStep(state)?.label).toBe("globe");
    expect(state.marks.globe).toBeUndefined();
    expect(undo(state)).toEqual(state);
  });

  it("deshacer tras completar reabre la ultima marca", () => {
    let state = startCalipers(stepsFor(ONSD, 6));
    for (const point of [[10, 10], [5, 13], [15, 13]] as [number, number][]) {
      state = addPoint(state, point, 0);
    }
    state = undo(state);
    expect(currentStep(state)?.label).toBe("sheath");
    expect(state.marks.sheath?.points).toEqual([[5, 13]]);
  });
});

describe("de pantalla a pixeles de imagen", () => {
  const box = { left: 100, top: 50, width: 400, height: 300 };

  it("deshace el escalado de la imagen mostrada", () => {
    // Imagen de 800 x 600 mostrada a la mitad: un clic en el centro es (400, 300).
    expect(toImagePoint(300, 200, box, 800, 600)).toEqual([400, 300]);
  });

  it("no sale de la imagen", () => {
    expect(toImagePoint(0, 0, box, 800, 600)).toEqual([0, 0]);
    expect(toImagePoint(10_000, 10_000, box, 800, 600)).toEqual([800, 600]);
  });
});
