import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { spanWithPictogram, textNodes } from "../advisor/visibleText";
import type { Indicator } from "../lib/api";
import { RouteFigure, VitalValue, letterOf } from "./HomeBoard";
import { routeFigures } from "./missionProfile";

/**
 * Contradicciones de «Inicio» con el resto de la consola (lote «lógica», unidad 6): una letra RIDGE
 * que «Peligros» no da, un vital redondeado y sin unidad mientras falta el catálogo, y la distancia
 * y el retardo de «Rutas espaciales» limpios con el perfil y las efemérides que no casan o con las
 * efemérides caducadas.
 */

describe("la letra RIDGE de «Inicio» es la de «Peligros»", () => {
  it("los cinco de la sigla, su letra; un peligro desconocido, ninguna", () => {
    expect(["radiation", "isolation", "distance", "gravity", "environment"].map(letterOf)).toEqual([
      "R",
      "I",
      "D",
      "G",
      "E",
    ]);
    // Antes «toxicity» salía con una «T» que no es de la sigla.
    expect(letterOf("toxicity")).toBe("");
  });
});

describe("la cifra de un vital lleva los decimales y la unidad de su ficha", () => {
  const temperature = { key: "body-temperature", decimals: 1, unit: "Cel" } as unknown as Indicator;
  const render = (indicator: Indicator | undefined, state: "loading" | "ready" | "failed") =>
    renderToStaticMarkup(
      createElement(VitalValue, {
        value: 36.7,
        indicator,
        catalog:
          state === "ready"
            ? { state, value: [] }
            : state === "failed"
              ? { state, outcome: { mark: { pictogram: null, color: null }, text: "x" } as never }
              : { state },
      }),
    );

  it("con la ficha, 36,7 con su unidad", () => {
    const text = textNodes(render(temperature, "ready")).join(" ");
    expect(text).toContain("36,7");
    expect(text).not.toContain("37 ");
  });

  it("sin la ficha no se enseña una cifra redondeada y sin unidad (antes «37»)", () => {
    const loading = render(undefined, "loading");
    expect(loading).not.toContain("37");
    expect(textNodes(loading).join(" ")).toContain("Cargando");
    for (const state of ["failed", "ready"] as const) {
      const html = render(undefined, state);
      expect(html).not.toContain("37");
      expect(html).toMatch(spanWithPictogram("mark c-gray", "slash-circle", "sin ficha del catálogo"));
    }
  });
});

describe("las cifras de las efemérides en «Rutas espaciales»", () => {
  it("perfil y efemérides que no casan: la precaución, no la distancia de otro cuerpo", () => {
    const figures = routeFigures(true, true, "fresh", "mismatch");
    expect(figures).toMatchObject({ kind: "absent", word: "perfil y efemérides no casan" });
    const html = renderToStaticMarkup(createElement(RouteFigure, { figures }, "225 km"));
    expect(html).not.toContain("225 km");
    expect(html).toMatch(spanWithPictogram("mark c-yellow", "shape-triangle", "perfil y efemérides no casan"));
  });

  it("caducadas: la cifra se conserva en cian con el anillo punteado, como en la franja", () => {
    for (const freshness of ["stale", "missing"] as const) {
      const figures = routeFigures(true, true, freshness, "consistent");
      expect(figures).toEqual({ kind: "shown", stale: true });
      const html = renderToStaticMarkup(createElement(RouteFigure, { figures }, "12,5 min"));
      expect(html).toMatch(spanWithPictogram("mark num c-cyan", "ring-dotted", "12,5 min"));
    }
  });

  it("al día y con el perfil que casa, limpia; sin declarar o sin efemérides, lo que falta", () => {
    const fresh = renderToStaticMarkup(
      createElement(RouteFigure, { figures: routeFigures(true, true, "fresh", "consistent") }, "12,5 min"),
    );
    expect(fresh).toBe('<span class="num">12,5 min</span>');
    expect(routeFigures(false, true, "fresh", "mismatch")).toMatchObject({ word: "solo del perfil declarado" });
    expect(routeFigures(true, false, "missing", "mismatch")).toMatchObject({ word: "sin efemérides" });
  });

  it("un perfil sin objetivo de efemérides (2026-11-11): «no disponible», no «sin efemérides»", () => {
    const figures = routeFigures(true, false, "missing", "no_target");
    expect(figures).toMatchObject({ kind: "absent", word: "sin objetivo de efemérides" });
    const html = renderToStaticMarkup(createElement(RouteFigure, { figures }, "0,1 min"));
    expect(html).not.toContain("0,1 min");
    expect(html).toMatch(spanWithPictogram("mark c-gray", "slash-circle", "sin objetivo de efemérides"));
  });
});
