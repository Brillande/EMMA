import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { BODY_OUTLINE, SITED_REGIONS, Silhouette, siteAnchor } from "./Silhouette";

/**
 * La silueta recalcada (§5.33.3): un solo contorno cerrado de cúbicas con una decimal, dentro de su
 * lienzo y simétrico; los órganos dentro del tronco, con las primitivas de los pictogramas y sin
 * color ni estilo propios. Se pinta a HTML estático y se lee lo que sale, no el código.
 */

const NUMBER = String.raw`-?\d+(?:\.\d)?`;
const PAIR = `${NUMBER} ${NUMBER}`;

describe("el contorno", () => {
  it("es un trayecto cerrado: un M y solo cúbicas absolutas, con una decimal como mucho", () => {
    const grammar = new RegExp(`^M${PAIR}(?:C${PAIR} ${PAIR} ${PAIR})+Z$`);
    expect(BODY_OUTLINE).toMatch(grammar);
  });

  it("tiene cuarenta nodos como mucho", () => {
    const curves = BODY_OUTLINE.match(/C/g)?.length ?? 0;
    // El nodo de llegada de la última cúbica es el de salida: cerrado, no se cuenta dos veces.
    expect(curves).toBeLessThanOrEqual(40);
    expect(curves % 2).toBe(0);
  });

  it("todo punto cae en el lienzo de 200×480, con los pies abajo y la coronilla arriba", () => {
    const values = (BODY_OUTLINE.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
    const xs = values.filter((_, index) => index % 2 === 0);
    const ys = values.filter((_, index) => index % 2 === 1);
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...xs)).toBeLessThanOrEqual(200);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...ys)).toBeLessThanOrEqual(480);
    expect(Math.max(...ys)).toBeGreaterThan(465);
    expect(Math.min(...ys)).toBeLessThan(60);
  });

  it("la mitad derecha es el espejo de la izquierda (x → 200 − x)", () => {
    const points = (BODY_OUTLINE.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
    const pairs: [number, number][] = [];
    for (let index = 0; index < points.length; index += 2) {
      pairs.push([points[index] ?? Number.NaN, points[index + 1] ?? Number.NaN]);
    }
    const key = ([x, y]: [number, number]) => `${Math.round(x * 10)}:${Math.round(y * 10)}`;
    const all = new Set(pairs.map(key));
    for (const [x, y] of pairs) expect(all.has(key([200 - x, y])), `${x} ${y}`).toBe(true);
  });
});

/** Los atributos numéricos de un elemento como mapa. */
function attributes(tag: string): Record<string, string> {
  return Object.fromEntries([...tag.matchAll(/([a-zA-Z0-9-]+)="([^"]*)"/g)].map((match) => [match[1], match[2]]));
}

/**
 * Los puntos de un `d` con órdenes absolutas M, L, C, A y Z. De un arco, su llegada y las cuatro
 * esquinas de la caja de lado 4r centrada en ella: todo punto de un arco de radio r está a menos
 * de 2r de sus extremos, así que la panza no se escapa de la cuenta.
 */
function pathPoints(d: string): [number, number][] {
  const tokens = d.match(/[MLCAZ]|-?\d+(?:\.\d+)?/g) ?? [];
  expect(tokens.join(""), d).toBe(d.replace(/[\s,]/g, ""));
  const points: [number, number][] = [];
  let command = "";
  let index = 0;
  const next = () => Number(tokens[index++]);
  while (index < tokens.length) {
    const token = tokens[index] ?? "";
    if (/[MLCAZ]/.test(token)) {
      command = token;
      index += 1;
      if (command === "Z") continue;
    }
    if (command === "A") {
      const r = Math.max(next(), next());
      index += 3;
      const [x, y] = [next(), next()];
      points.push([x, y], [x - 2 * r, y - 2 * r], [x + 2 * r, y + 2 * r]);
    } else if (command === "M" || command === "L" || command === "C") {
      points.push([next(), next()]);
    } else {
      throw new Error(`orden no prevista en ${d}`);
    }
  }
  return points;
}

describe("los órganos", () => {
  const html = renderToStaticMarkup(createElement(Silhouette, {}));
  const zones = new Map(
    [...html.matchAll(/<g class="zone[^"]*" data-region="([a-z-]+)"[^>]*>(.*?)<\/g>/g)].map((match) => [
      match[1] ?? "",
      match[2] ?? "",
    ]),
  );

  it("cada zona con dibujo, solo con las primitivas de los pictogramas", () => {
    expect([...zones.keys()]).toEqual([...SITED_REGIONS]);
    const tags = [...html.matchAll(/<([a-z]+)\b/g)].map((match) => match[1]);
    for (const tag of tags) expect(["svg", "g", "path", "circle", "rect", "line"], tag).toContain(tag);
    for (const [region, shape] of zones) expect(shape, region).not.toBe("");
  });

  it("en el centro de la figura: x entre 60 y 140, y en el lienzo", () => {
    for (const [region, shape] of zones) {
      const points: [number, number][] = [];
      for (const [tag] of shape.matchAll(/<(?:path|circle|rect|line)\b[^>]*>/g)) {
        const attrs = attributes(tag);
        if (tag.startsWith("<path")) points.push(...pathPoints(attrs.d ?? ""));
        if (tag.startsWith("<circle")) {
          const [cx, cy, r] = [Number(attrs.cx), Number(attrs.cy), Number(attrs.r)];
          points.push([cx - r, cy], [cx + r, cy]);
        }
        if (tag.startsWith("<rect")) {
          const [x, y] = [Number(attrs.x), Number(attrs.y)];
          points.push([x, y], [x + Number(attrs.width), y + Number(attrs.height)]);
        }
        if (tag.startsWith("<line")) {
          points.push([Number(attrs.x1), Number(attrs.y1)], [Number(attrs.x2), Number(attrs.y2)]);
        }
      }
      expect(points.length, region).toBeGreaterThan(0);
      for (const [x, y] of points) {
        expect(Number.isFinite(x) && Number.isFinite(y), region).toBe(true);
        expect(x, region).toBeGreaterThanOrEqual(60);
        expect(x, region).toBeLessThanOrEqual(140);
        expect(y, region).toBeGreaterThanOrEqual(0);
        expect(y, region).toBeLessThanOrEqual(480);
      }
    }
  });

  it("el rotulo de cada zona empieza pasado el contorno en la franja que ocupa (±24 de su altura)", () => {
    // El contorno muestreado: cada cúbica en cuarenta pasos.
    const values = (BODY_OUTLINE.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
    const samples: [number, number][] = [];
    let [px, py] = [values[0] ?? 0, values[1] ?? 0];
    for (let index = 2; index + 5 < values.length; index += 6) {
      const [x1, y1, x2, y2, x, y] = values.slice(index, index + 6) as [number, number, number, number, number, number];
      for (let step = 0; step <= 40; step += 1) {
        const t = step / 40;
        const a = (1 - t) ** 3;
        const b = 3 * (1 - t) ** 2 * t;
        const c = 3 * (1 - t) * t ** 2;
        const d = t ** 3;
        samples.push([a * px + b * x1 + c * x2 + d * x, a * py + b * y1 + c * y2 + d * y]);
      }
      [px, py] = [x, y];
    }
    expect(samples.length).toBeGreaterThan(100);
    for (const region of SITED_REGIONS) {
      const { y, reach } = siteAnchor(region);
      const centre = y * 480;
      const band = samples.filter(([, sy]) => Math.abs(sy - centre) <= 24);
      const widest = Math.max(...band.map(([sx]) => Math.abs(sx - 100)));
      expect(reach, region).toBeGreaterThanOrEqual(widest);
      // Y no mucho más: el rótulo va junto a su sitio, no al borde del panel.
      expect(reach - widest, region).toBeLessThan(3);
    }
  });

  it("sin color ni estilo propios: todo en currentColor", () => {
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|style=/);
    expect(html).not.toMatch(/\b(?:fill|stroke)="(?!none|currentColor)/);
  });
});
