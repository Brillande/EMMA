import { describe, expect, it } from "vitest";

import { SILHOUETTE_HEIGHT, SITED_REGIONS, siteAnchor } from "../icons/Silhouette";
import { MAX_SHIFT, SITE_GAP, type SiteBox, placeSites } from "./siteLayout";

/**
 * Los rótulos de la silueta colocados por su alto medido (§5.35.11): ninguno pisa a otro de su
 * lado, cada uno queda lo más cerca posible de su zona y, si para no pisarse tendría que alejarse
 * de ella, van todos a la lista de debajo. Unidades del lienzo (480 de alto).
 */

const box = (key: string, side: "left" | "right", anchor: number, height = 40): SiteBox => ({
  key,
  side,
  anchor,
  height,
});

/** Que en cada lado ningún rótulo pise al siguiente, con su hueco. */
function expectNoOverlap(boxes: readonly SiteBox[], centres: Readonly<Record<string, number>>) {
  for (const side of ["left", "right"] as const) {
    const placed = boxes
      .filter((item) => item.side === side)
      .map((item) => ({ ...item, centre: centres[item.key] ?? Number.NaN }))
      .sort((a, b) => a.centre - b.centre);
    for (let index = 0; index + 1 < placed.length; index += 1) {
      const upper = placed[index] as (typeof placed)[number];
      const lower = placed[index + 1] as (typeof placed)[number];
      expect(upper.centre + upper.height / 2 + SITE_GAP, `${upper.key} / ${lower.key}`).toBeLessThanOrEqual(
        lower.centre - lower.height / 2 + 1e-9,
      );
    }
    for (const item of placed) {
      expect(item.centre - item.height / 2, item.key).toBeGreaterThanOrEqual(-1e-9);
      expect(item.centre + item.height / 2, item.key).toBeLessThanOrEqual(SILHOUETTE_HEIGHT + 1e-9);
    }
  }
}

/** Los rótulos de la figura de verdad, con un mismo alto, y los de las regiones sin nivel propio
 * (el hígado y los pulmones, con la frase de su nivel debajo) más altos (tres líneas). */
const TALLER = new Set<string>(["liver", "lungs"]);
function realBoxes(height: number): SiteBox[] {
  return SITED_REGIONS.map((key) => {
    const anchor = siteAnchor(key);
    return box(key, anchor.side, anchor.y * SILHOUETTE_HEIGHT, TALLER.has(key) ? height * 1.5 : height);
  });
}

describe("colocar los rótulos por su alto", () => {
  it("los que no se pisan se quedan en la altura de su zona", () => {
    const boxes = [box("a", "left", 60), box("b", "left", 200), box("c", "right", 60)];
    const placed = placeSites(boxes, SILHOUETTE_HEIGHT);
    expect(placed.listed).toBe(false);
    expect(placed.centres).toEqual({ a: 60, b: 200, c: 60 });
  });

  it("dos que se pisan se apartan lo justo, repartidos alrededor de sus zonas", () => {
    const boxes = [box("a", "left", 170), box("b", "left", 180)];
    const placed = placeSites(boxes, SILHOUETTE_HEIGHT);
    expect(placed.listed).toBe(false);
    expectNoOverlap(boxes, placed.centres);
    // El bloque queda centrado en la media de sus zonas: cada uno se aleja lo mismo.
    expect((placed.centres.a ?? 0) + (placed.centres.b ?? 0)).toBeCloseTo(350);
    expect((placed.centres.b ?? 0) - (placed.centres.a ?? 0)).toBeCloseTo(40 + SITE_GAP);
  });

  it("un lado no aparta al otro", () => {
    const boxes = [box("a", "left", 170), box("b", "right", 175)];
    expect(placeSites(boxes, SILHOUETTE_HEIGHT).centres).toEqual({ a: 170, b: 175 });
  });

  it("al juntarse, un bloque puede alcanzar al de arriba y se juntan los tres", () => {
    const boxes = [box("a", "right", 100), box("b", "right", 150), box("c", "right", 160)];
    const placed = placeSites(boxes, SILHOUETTE_HEIGHT);
    expectNoOverlap(boxes, placed.centres);
    expect(placed.listed).toBe(false);
  });

  it("no se salen de la figura: el de arriba del todo se queda dentro", () => {
    const boxes = [box("a", "right", 5), box("b", "right", 470)];
    const placed = placeSites(boxes, SILHOUETTE_HEIGHT);
    expect(placed.centres).toEqual({ a: 20, b: 460 });
  });

  it("si alguno tendría que alejarse de su zona más de lo que se lee junto a ella, todos a la lista", () => {
    const crowded = [box("a", "left", 200, 60), box("b", "left", 205, 60), box("c", "left", 210, 60)];
    const placed = placeSites(crowded, SILHOUETTE_HEIGHT);
    // El del medio se queda; los otros dos se alejan 64 unidades, más que MAX_SHIFT.
    expect(60 + SITE_GAP).toBeGreaterThan(MAX_SHIFT);
    expect(placed).toEqual({ listed: true, centres: {} });
  });

  it("si no caben en el alto de la figura, también a la lista", () => {
    const tall = [box("a", "left", 100, 300), box("b", "left", 380, 300)];
    expect(placeSites(tall, SILHOUETTE_HEIGHT).listed).toBe(true);
  });
});

describe("con los rótulos de la silueta", () => {
  it("a tamaño normal caben junto a sus zonas sin pisarse, el hígado y los pulmones incluidos", () => {
    // Un rótulo de dos líneas a 0,85 rem con la figura a 500 px: unas 49 unidades.
    const boxes = realBoxes(49);
    const placed = placeSites(boxes, SILHOUETTE_HEIGHT);
    expect(placed.listed).toBe(false);
    expectNoOverlap(boxes, placed.centres);
  });

  it("al 125 % del texto todavía caben, con los pulmones por la derecha (§5.36.13)", () => {
    const boxes = realBoxes(49 * 1.25);
    const placed = placeSites(boxes, SILHOUETTE_HEIGHT);
    expect(placed.listed).toBe(false);
    expectNoOverlap(boxes, placed.centres);
    // Por la izquierda, con el hígado y la espalda, no cabrían ni a tamaño normal.
    const left = realBoxes(49).map((item) => (item.key === "lungs" ? { ...item, side: "left" as const } : item));
    expect(placeSites(left, SILHOUETTE_HEIGHT).listed).toBe(true);
  });

  it("al 200 % del texto no caben junto a sus zonas: van a la lista", () => {
    expect(placeSites(realBoxes(98), SILHOUETTE_HEIGHT).listed).toBe(true);
  });
});
