import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { PRIVATE_NAME_HIGHLIGHT, nameRanges, namesMaskable, privateNames, signersIn } from "./privacyNames";

/**
 * La privacidad tapa los nombres dentro de las frases que quedan a la vista (§5.40) sin tocar el
 * texto del backend: aquí, qué nombres y dónde; la hoja de estilos, cómo se pintan.
 */

const pick = (text: string, ranges: [number, number][]) => ranges.map(([a, b]) => text.slice(a, b));

describe("dónde está un nombre en una frase", () => {
  it("cada aparición exacta, como palabra entera", () => {
    const text = "Cambio individual en crew-02. Reconocida por Ana; crew-02 sigue en vigilancia.";
    expect(pick(text, nameRanges(text, ["crew-02", "Ana"]))).toEqual(["crew-02", "Ana", "crew-02"]);
  });

  it("no tapa media palabra: «Ana» no está en «Mañana» ni «crew-0» en «crew-01»", () => {
    expect(nameRanges("Mañana, Anabel", ["Ana"])).toEqual([]);
    expect(nameRanges("de crew-01", ["crew-0"])).toEqual([]);
  });

  it("el nombre largo gana al corto que lleva dentro, sin solaparse", () => {
    const text = "Ana María firmó; Ana no.";
    const names = privateNames(["Ana", "Ana María"]);
    expect(names).toEqual(["Ana María", "Ana"]);
    expect(pick(text, nameRanges(text, names))).toEqual(["Ana María", "Ana"]);
  });

  it("sin nombres o sin apariciones, nada", () => {
    expect(nameRanges("Ningún dominio fuera de lo nominal.", [])).toEqual([]);
    expect(nameRanges("Ningún dominio fuera de lo nominal.", ["crew-01"])).toEqual([]);
  });
});

describe("qué nombres se conocen", () => {
  it("quien firmó algo en el estado, a cualquier profundidad", () => {
    const status = {
      alerts: [{ acknowledged_by: "Ana", silenced_by: null, resolution: { declared_by: "Luis" } }],
      followups: [{ adopted_by: "Eva", closed_by: null }],
      notes: { declared_by: ["Iker", 3] },
    };
    expect([...signersIn(status)].sort()).toEqual(["Ana", "Eva", "Iker", "Luis"]);
  });

  it("las claves `*_by` que no son personas no cuentan", () => {
    const status = { shelter: { shelter_ready_by: "2026-11-03T10:00:00Z" }, cited_by: ["HRP"], used_by: ["crew-01"] };
    expect(signersIn(status).size).toBe(0);
  });

  it("tripulantes, el que se mira y quien está en la consola, sin vacíos ni repetidos", () => {
    expect(privateNames(["crew-01", "crew-02", "crew-01", "", "  ", null, undefined], [{ decided_by: "crew-02" }])).toEqual([
      "crew-01",
      "crew-02",
    ]);
  });
});

describe("cómo se pinta", () => {
  it("fuera del navegador no hay API de resaltado: se dice que no, y la consola tapa de más", () => {
    expect(namesMaskable()).toBe(false);
  });

  it("una barra gris sin letra, con el color de «no disponible» de la paleta", () => {
    const css = readFileSync(fileURLToPath(new URL("../styles.css", import.meta.url)), "utf8");
    const rule = css.match(new RegExp(`::highlight\\(${PRIVATE_NAME_HIGHLIGHT}\\)\\s*\\{([^}]*)\\}`));
    expect(rule?.[1]).toMatch(/color:\s*transparent/);
    expect(rule?.[1]).toMatch(/background-color:\s*var\(--c-gray\)/);
  });
});
