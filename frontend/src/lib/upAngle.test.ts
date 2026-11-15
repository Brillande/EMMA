import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { DisplayModesContext, ScreenTop } from "../components/DisplayControls";
import { DEFAULT_MODES, type DisplayModes } from "../components/displayModes";
import { setUpAngle, upAngle, upArrowDegrees } from "./upAngle";

/** La flecha de «arriba» del borde de la pantalla (§5.40): señala el arriba real grado a grado. */

afterEach(() => {
  setUpAngle("face", null);
  setUpAngle("sensor", null);
});

describe("hacia dónde apunta la flecha", () => {
  it("sin medida, al borde de arriba de la vista", () => {
    expect(upArrowDegrees(null, 0)).toBe(0);
    expect(upArrowDegrees(null, 90)).toBe(0);
  });

  it("con la vista en su cuadrante, lo que le falta para llegar al arriba real", () => {
    // Tableta girada 50°: la vista sigue en 0 (histéresis) y la flecha se gira los 50.
    expect(upArrowDegrees(50, 0)).toBe(50);
    // Ya en 90, con el arriba real a 70: la flecha se gira 20 hacia el otro lado.
    expect(upArrowDegrees(70, 90)).toBe(-20);
    // Por el camino corto al dar la vuelta.
    expect(upArrowDegrees(350, 0)).toBe(-10);
    expect(upArrowDegrees(10, 270)).toBe(100);
  });
});

describe("de dónde sale el ángulo", () => {
  it("la cara manda sobre el giroscopio mientras se ve, y al perderla sigue él", () => {
    setUpAngle("sensor", 40);
    expect(upAngle()).toBe(40);
    setUpAngle("face", 95.4);
    expect(upAngle()).toBe(95);
    setUpAngle("face", null);
    expect(upAngle()).toBe(40);
    setUpAngle("sensor", null);
    expect(upAngle()).toBeNull();
  });

  it("un ángulo roto no cuenta, y se guarda en [0, 360)", () => {
    setUpAngle("sensor", Number.NaN);
    expect(upAngle()).toBeNull();
    setUpAngle("sensor", -30);
    expect(upAngle()).toBe(330);
  });
});

const top = (modes: Partial<DisplayModes>) =>
  renderToStaticMarkup(
    createElement(
      DisplayModesContext.Provider,
      { value: { modes: { ...DEFAULT_MODES, ...modes }, update: () => undefined } },
      createElement(ScreenTop),
    ),
  );

describe("en el borde de arriba", () => {
  it("sin medida dice «Arriba», con la flecha sin girar", () => {
    const html = top({});
    expect(html).toContain("Arriba");
    expect(html).not.toContain("Arriba real");
    expect(html).not.toContain("rotate(");
  });
});
