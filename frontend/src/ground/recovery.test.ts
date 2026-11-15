import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml } from "../advisor/visibleText";

import { MISSING_MARK, UNKNOWN_MARK } from "../lib/marks";
import { INSIDE_MARK, OUTSIDE_MARK, RETURN_MARKS, returnMark } from "./recovery";
import { ReturnTally } from "./RecoveryPanel";

const RECOVERY_PATH = fileURLToPath(
  new URL("../../../backend/app/analysis/recovery.py", import.meta.url),
);

/**
 * Los estados que escribe `recovery.py`: los literales de cada línea con `"state":` que no son
 * a su vez una clave (los que no van seguidos de dos puntos).
 */
function backendStates(): string[] {
  const source = readFileSync(RECOVERY_PATH, "utf8");
  const found = new Set<string>();
  for (const line of source.split(/\r?\n/)) {
    if (!line.includes('"state":')) continue;
    for (const match of line.matchAll(/"([a-z-]+)"(?!\s*:)/g)) found.add(match[1] as string);
  }
  return [...found].sort();
}

describe("vuelta al rango tras el vuelo", () => {
  it("cada estado del backend tiene su marca, y ninguna marca nombra un estado que no existe", () => {
    const states = backendStates();
    expect(states).toEqual(["back-again", "no-preflight-range", "not-back", "within"]);
    expect(Object.keys(RETURN_MARKS).sort()).toEqual(states);
  });

  it("usa las marcas de cada toma: dentro, fuera y, sin rango, la del dato ausente", () => {
    expect(returnMark("within")).toBe(INSIDE_MARK);
    expect(returnMark("back-again")).toBe(INSIDE_MARK);
    expect(returnMark("not-back")).toBe(OUTSIDE_MARK);
    expect(OUTSIDE_MARK.color).toBe("blue");
    expect(returnMark("no-preflight-range")).toBe(MISSING_MARK);
  });

  it("un estado desconocido no se disfraza de otro", () => {
    expect(returnMark("recovered")).toBe(UNKNOWN_MARK);
    expect(returnMark("toString")).toBe(UNKNOWN_MARK);
  });
});

describe("<ReturnTally> (tablero)", () => {
  const html = renderToStaticMarkup(
    createElement(ReturnTally, { states: ["not-back", "within", "back-again", "within", "no-preflight-range", "recovered"] }),
  );

  it("una píldora por estado, con la marca de su fila y cuántos indicadores", () => {
    expect(html).toMatch(/<\/svg>dentro<\/span> <span class="num">2<\/span>/);
    expect(html).toMatch(markedHtml("shape-circle", "dentro de nuevo"));
    expect(html).toMatch(markedHtml("shape-diamond", "sin volver", "blue"));
    expect(html).toMatch(markedHtml("ring-dotted", "sin rango previo", "cyan"));
  });

  it("en el orden de la tabla de palabras; lo desconocido, al final, con su clave y su marca", () => {
    const order = ["dentro", "dentro de nuevo", "sin volver", "sin rango previo", "recovered"].map((word) =>
      html.indexOf(`</svg>${word}</span>`),
    );
    expect(order.every((at) => at >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(html).toMatch(markedHtml(UNKNOWN_MARK.pictogram ?? "", "recovered", UNKNOWN_MARK.color));
  });

  it("sin estados no hay píldoras", () => {
    expect(renderToStaticMarkup(createElement(ReturnTally, { states: [] }))).not.toContain("<li");
  });
});
