import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SectionArt } from "./HomeArt";

/**
 * Los dibujos de sección (lote «muestra», 2026-11-08) son adorno puro: cada clave conocida pinta un
 * `svg` oculto al lector de pantalla y sin texto; «Inicio» y una clave desconocida no pintan nada.
 */

const art = (section: string, console: string) => renderToStaticMarkup(createElement(SectionArt, { section, console }));

const CREW = ["hazards", "routines", "body", "mission", "data", "log", "imaging", "library", "env-leo", "env-mars-transit"];
const GROUND = ["received", "history", "trends", "habitat", "framework", "ledger", "library", "env-lunar-surface"];

describe("SectionArt", () => {
  it.each([...CREW.map((key) => ["crew", key]), ...GROUND.map((key) => ["ground", key])])(
    "%s/%s pinta un dibujo oculto, sin texto",
    (console, section) => {
      const out = art(section, console);
      expect(out).toMatch(/<svg[^>]*aria-hidden="true"/);
      // El envoltorio, si lo hay, también queda oculto.
      expect(out.startsWith("<svg") || /^<span[^>]*aria-hidden="true"/.test(out)).toBe(true);
      // Sin texto: quitadas las etiquetas no queda nada, y no hay <text> ni <title>.
      expect(out.replace(/<[^>]*>/g, "").trim()).toBe("");
      expect(out).not.toMatch(/<(text|title|desc)\b/);
      expect(out).not.toMatch(/aria-label|role=/);
    },
  );

  it("las secciones de Tierra tienen su dibujo, no el de tripulación con la misma clave", () => {
    expect(art("received", "ground")).not.toBe("");
    expect(art("received", "crew")).toBe("");
    expect(art("hazards", "ground")).toBe("");
  });

  it("el entorno lleva el planeta de su perfil", () => {
    expect(art("env-mars-transit", "crew")).toContain("url(#ref-g-mars)");
    expect(art("env-lunar-surface", "crew")).toContain("url(#ref-g-moon)");
  });

  it.each([
    ["crew", "home"],
    ["ground", "home"],
    ["crew", "env"],
    ["crew", "env-"],
    ["crew", "desconocida"],
    ["crew", "toString"],
    ["ground", "constructor"],
  ])("%s/%s no pinta nada", (console, section) => {
    expect(art(section, console)).toBe("");
  });
});
