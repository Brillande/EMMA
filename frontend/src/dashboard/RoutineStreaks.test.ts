import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textLines } from "../advisor/visibleText";
import type { RoutineStreaks } from "../lib/api";
import { RoutineStreakList } from "./TimelinePieces";

/*
 * Las rachas de las medidas periodicas (gamificacion del reto, decision del usuario 2026-11-02):
 * una cifra con la fila de puntos, sin color, sin porcentaje y con todo el texto del backend. Las
 * palabras de abajo en mayusculas son marcadores: si la interfaz escribiera algo suyo, el texto
 * visible no cuadraria.
 */

const view: RoutineStreaks = {
  label: "ROTULO",
  note: "NOTA",
  longest_label: "MAS-LARGA",
  routines: [
    { key: "heart-rate", display_es: "Pulso", period_hours: 6, basis: "BASE", current: 1234, longest: 1234, unit: "UNIDAD" },
    { key: "body-weight", display_es: "Peso", period_hours: 168, basis: "BASE", current: 0, longest: 2, unit: "UNIDADES" },
    { key: "cortisol-salivary", display_es: "Cortisol", period_hours: 720, basis: "BASE", current: 0, longest: 0, unit: "UNIDADES" },
  ],
};

const render = (value: RoutineStreaks) => renderToStaticMarkup(createElement(RoutineStreakList, { view: value }));

describe("rachas de las medidas periodicas", () => {
  it("la cifra va con formatNumber y la fila de puntos, sin color; el texto es el del backend", () => {
    const html = render(view);
    expect(html).toMatch(/<details[^>]*><summary[^>]*><svg [^>]*data-pictogram="dots-row"/);
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="dots-row">.*?<\/svg><span class="num">1234<\/span> UNIDAD<\/span>/);
    // Sin color: ningún token de la paleta en las rachas, y ningún porcentaje a la vista (la barra
    // del tablero lleva el suyo en su anchura, oculta al lector y sin escribirlo).
    expect(html).not.toMatch(/c-(green|yellow|red|blue|cyan|gray|magenta)/);
    expect(textLines(html).join(" ")).not.toContain("%");
    expect(textLines(html)).toEqual([
      "ROTULO",
      "NOTA",
      "Pulso: 1234 UNIDAD · MAS-LARGA 1234 · cada 6 h (BASE)",
      "Peso: 0 UNIDADES · MAS-LARGA 2 · cada 168 h (BASE)",
    ]);
  });

  it("tablero (2026-11-07): junto a la cifra, la barra de la racha actual sobre la más larga, adorno y sin tono", () => {
    const html = render(view);
    const bars = html.match(/<span class="board-bar" aria-hidden="true"><span style="width:[0-9.]+%"><\/span><\/span>/g) ?? [];
    expect(bars).toHaveLength(2);
    expect(bars[0]).toContain("width:100.0%");
    expect(bars[1]).toContain("width:0.0%");
    expect(html).not.toContain("data-tone");
  });

  it("lo que nunca tuvo racha no se lista, y sin ninguna no se pinta nada", () => {
    expect(render(view)).not.toContain("Cortisol");
    expect(render({ ...view, routines: [view.routines[2]!] })).toBe("");
  });
});
