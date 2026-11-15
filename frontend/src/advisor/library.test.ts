import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
// Sin los `data-ui` del asistente: estas pruebas miran el marcado del panel.
import { renderToStaticMarkup } from "../assistant/staticMarkup";
import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import type { CountermeasureLibrary } from "../lib/api";
import { EMPTY_MARK, OK_MARK, UNKNOWN_PICTOGRAM } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { TEXTS, measureOf } from "./cardFixture";
import {
  ADVERSE_EFFECTS_PICTOGRAM,
  CONTRAINDICATIONS_PICTOGRAM,
  FAMILY_PICTOGRAMS,
  familyOptions,
  familyPictogram,
  libraryGroups,
  TIME_BASIS_VISIBLE_CHARS,
  timeBasisFolds,
} from "./library";
import { LibraryBody } from "./LibraryPanel";
import { CountermeasureFacts } from "./RecommendationCard";
import { markedHtml, pictogramSvg, taggedPictogram, thSign } from "./visibleText";

/**
 * La biblioteca de contramedidas (§5.34.1): cada familia del vocabulario cerrado del backend
 * tiene su dibujo, los grupos RIDGE son los del backend sin inventar ni perder entradas, el fallo
 * de la lectura se pinta con la marca de la decisión del usuario, y todo lo escrito es del backend.
 */

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf-8");

/** Las claves de `FAMILIES`, leídas del propio `countermeasures.py`. */
function backendFamilies(): string[] {
  const source = read("../../../backend/app/advisor/countermeasures.py");
  const constant = /^PHARMACOLOGICAL = "([a-z-]+)"/m.exec(source)?.[1];
  const keys = [...source.matchAll(/^\s+Family\(\s*\n\s+("([a-z-]+)"|PHARMACOLOGICAL),/gm)].map(
    (match) => match[2] ?? constant ?? "",
  );
  if (keys.length === 0) throw new Error("no se encuentran las familias en countermeasures.py");
  return keys;
}

const libraryJson = (): { countermeasures: { id: string; family: string }[] } =>
  JSON.parse(read("../../../backend/app/data/countermeasures.json"));

const FAMILY_WORDS = {
  "physical-mass": "física o de masa",
  operational: "operacional",
  "check-surveillance": "comprobación o vigilancia",
  pharmacological: "farmacológica: fuera del alcance de EMMA",
} as const;

const libraryOf = (over: Partial<CountermeasureLibrary> = {}): CountermeasureLibrary => ({
  countermeasures: [
    measureOf({
      id: "a",
      action: "Acción A del backend.",
      family: "physical-mass",
      family_display: FAMILY_WORDS["physical-mass"],
      crew_time_minutes: 120,
      crew_time_basis: "frase de la fuente del tiempo",
    }),
    measureOf({
      id: "b",
      action: "Acción B del backend.",
      ridge: "radiation",
      family: "check-surveillance",
      family_display: FAMILY_WORDS["check-surveillance"],
      adverse_effects_note: null,
    }),
  ],
  by_ridge: [
    { ridge: "radiation", ridge_display: "radiación", count: 1, countermeasures: ["b"] },
    { ridge: "gravity", ridge_display: "campos gravitatorios", count: 1, countermeasures: ["a"] },
    { ridge: "distance", ridge_display: "distancia de la Tierra", count: 0, countermeasures: [] },
  ],
  families: (Object.keys(FAMILY_WORDS) as (keyof typeof FAMILY_WORDS)[]).map((key) => ({
    key,
    display: FAMILY_WORDS[key],
    criterion: `criterio de ${key}`,
    in_scope: key !== "pharmacological",
    count: key === "physical-mass" || key === "check-surveillance" ? 1 : 0,
  })),
  note: "nota de la biblioteca",
  family_basis: "base del vocabulario",
  ridge_basis: "base de RIDGE",
  ...over,
});

describe("familias", () => {
  it("cada familia del backend tiene su dibujo, distinto de las demás, y ninguno de más", () => {
    expect(Object.keys(FAMILY_PICTOGRAMS).sort()).toEqual(backendFamilies().sort());
    const drawings = Object.values(FAMILY_PICTOGRAMS);
    expect(new Set(drawings).size).toBe(drawings.length);
    for (const name of drawings) expect(isPictogramName(name), name).toBe(true);
  });

  it("toda entrada de la biblioteca lleva una familia del vocabulario, ninguna la farmacológica", () => {
    const entries = libraryJson().countermeasures;
    expect(entries.length).toBeGreaterThan(30);
    for (const entry of entries) {
      expect(Object.keys(FAMILY_PICTOGRAMS), entry.id).toContain(entry.family);
      expect(entry.family, entry.id).not.toBe("pharmacological");
    }
  });

  it("una familia que esta versión no conoce sale con el dibujo de «desconocido»", () => {
    expect(familyPictogram("inventada")).toBe(UNKNOWN_PICTOGRAM);
  });
});

describe("grupos RIDGE", () => {
  it("son los del backend, en su orden, con sus entradas resueltas", () => {
    const { groups, ungrouped } = libraryGroups(libraryOf());
    expect(groups.map((group) => group.ridge)).toEqual(["radiation", "gravity", "distance"]);
    expect(groups.map((group) => group.items.map((item) => item.id))).toEqual([["b"], ["a"], []]);
    expect(groups.map((group) => group.pictogram)).toEqual(["ridge-radiation", "ridge-gravity", "ridge-distance"]);
    expect(ungrouped).toEqual([]);
  });

  it("no inventan una entrada que la lista no trae ni pierden una que ningún grupo nombra", () => {
    const { groups, ungrouped } = libraryGroups(
      libraryOf({
        by_ridge: [{ ridge: "otro-eje", ridge_display: "otro", count: 2, countermeasures: ["a", "zz"] }],
      }),
    );
    expect(groups[0]?.items.map((item) => item.id)).toEqual(["a"]);
    expect(groups[0]?.missing).toEqual(["zz"]);
    expect(groups[0]?.pictogram).toBe(UNKNOWN_PICTOGRAM);
    expect(ungrouped.map((item) => item.id)).toEqual(["b"]);
  });
});

describe("el panel", () => {
  const html = renderToStaticMarkup(createElement(LibraryBody, { library: libraryOf() }));

  it("pinta las palabras del backend: nota, familias con su dibujo, criterios y RIDGE", () => {
    expect(html).toContain("nota de la biblioteca");
    expect(html).toContain("base del vocabulario");
    expect(html).toContain("base de RIDGE");
    for (const [key, word] of Object.entries(FAMILY_WORDS)) {
      expect(html).toMatch(markedHtml(FAMILY_PICTOGRAMS[key as keyof typeof FAMILY_WORDS], `${word}</span>`));
      expect(html).toContain(`criterio de ${key}`);
    }
    expect(html).toMatch(taggedPictogram("summary", "ridge-radiation", "RIDGE: radiación ("));
    expect(html).toMatch(taggedPictogram("summary", "ridge-distance", "RIDGE: distancia de la Tierra ("));
    expect(html).toContain("Acción A del backend.");
    expect(html).toContain("Acción B del backend.");
  });

  it("una cifra de tiempo lleva su fuente al lado, en un plegable; sin cifra, la base sola", () => {
    expect(html).toMatch(/<span class="num">120<\/span> min<details><summary>.*?fuente<\/summary>/);
    expect(html).toContain("frase de la fuente del tiempo");
  });

  it("nada lleva color: la biblioteca no avisa de nada", () => {
    expect(html).not.toMatch(/c-(red|yellow|blue|cyan|gray|magenta|green)/);
  });
});

describe("la tarjeta del asesor", () => {
  it("dice la familia junto al RIDGE, con su dibujo y la palabra del backend", () => {
    const html = renderToStaticMarkup(
      createElement(CountermeasureFacts, {
        measure: measureOf({ family: "operational", family_display: FAMILY_WORDS.operational }),
      }),
    );
    expect(html).toMatch(markedHtml("route-arrow", "familia: operacional</span>"));
  });

  it("sin la palabra del backend no pinta familia", () => {
    const html = renderToStaticMarkup(createElement(CountermeasureFacts, { measure: measureOf() }));
    expect(html).not.toContain("familia");
  });
});

describe("el filtro por familia (§5.35.7)", () => {
  it("ofrece las familias del backend en su orden, con la cifra de la lista; sin entradas, sin mando", () => {
    const options = familyOptions(libraryOf());
    expect(options.map((option) => option.key)).toEqual(Object.keys(FAMILY_WORDS));
    expect(options.map((option) => option.display)).toEqual(Object.values(FAMILY_WORDS));
    expect(options.map((option) => option.count)).toEqual([1, 0, 1, 0]);
    expect(options.map((option) => option.selectable)).toEqual([true, false, true, false]);
    expect(options.find((option) => option.key === "pharmacological")?.inScope).toBe(false);
  });

  it("una familia que la lista trae y el vocabulario no sale detrás, con «desconocido», y no se pierde", () => {
    const base = libraryOf();
    const extra = measureOf({ id: "c", family: "nueva", family_display: "palabra nueva" });
    const options = familyOptions({ ...base, countermeasures: [...base.countermeasures, extra] });
    expect(options.at(-1)).toMatchObject({
      key: "nueva",
      display: "palabra nueva",
      pictogram: UNKNOWN_PICTOGRAM,
      count: 1,
      selectable: true,
    });
  });

  it("filtra dentro de cada grupo sin tocar los grupos, y lo nombrado sin ficha sale siempre", () => {
    const { groups } = libraryGroups(libraryOf(), "physical-mass");
    expect(groups.map((group) => group.ridge)).toEqual(["radiation", "gravity", "distance"]);
    expect(groups.map((group) => group.items.map((item) => item.id))).toEqual([[], ["a"], []]);
    const odd = libraryGroups(
      libraryOf({ by_ridge: [{ ridge: "radiation", ridge_display: "r", count: 2, countermeasures: ["b", "zz"] }] }),
      "physical-mass",
    );
    expect(odd.groups[0]?.items).toEqual([]);
    expect(odd.groups[0]?.missing).toEqual(["zz"]);
    expect(odd.ungrouped.map((item) => item.id)).toEqual(["a"]);
  });

  it("sin familia elegida, todas: el reparto de antes", () => {
    expect(libraryGroups(libraryOf(), null)).toEqual(libraryGroups(libraryOf()));
  });

  it("en el panel: «todas» elegida con el anillo, cada familia con entradas es un mando y la vacía no", () => {
    const html = renderToStaticMarkup(createElement(LibraryBody, { library: libraryOf() }));
    expect(html).toMatch(
      new RegExp(
        `<button type="button" class="command" aria-pressed="true"><span class="mark">${pictogramSvg(uiPictogram("chosen"))}todas `,
      ),
    );
    expect(html).toMatch(
      new RegExp(`aria-pressed="false"><span class="mark"><span class="mark">${pictogramSvg("weight-trapezoid")}`),
    );
    const buttons = [...html.matchAll(/<button[\s\S]*?<\/button>/g)].map((match) => match[0]);
    expect(buttons).toHaveLength(3);
    expect(buttons.some((button) => button.includes(FAMILY_WORDS.pharmacological))).toBe(false);
    expect(buttons.some((button) => button.includes(FAMILY_WORDS.operational))).toBe(false);
  });

  it("con una familia elegida, cada grupo dice cuántas de las suyas enseña y el vacío lo dice", () => {
    const html = renderToStaticMarkup(
      createElement(LibraryBody, { library: libraryOf(), initialFamily: "physical-mass" }),
    );
    expect(html).toContain("Acción A del backend.");
    expect(html).not.toContain("Acción B del backend.");
    expect(html).toMatch(/RIDGE: radiación \(<span class="num">0<\/span> de <span class="num">1<\/span>\)/);
    expect(html).toMatch(/RIDGE: campos gravitatorios \(<span class="num">1<\/span> de <span class="num">1<\/span>\)/);
    expect(html).toMatch(markedHtml(OK_MARK.pictogram ?? "", "Ninguna de esta familia en este peligro."));
    expect(html).not.toMatch(/c-(red|yellow|blue|cyan|gray|magenta|green)/);
  });

  it("una familia que no se puede elegir (sin entradas, o que no existe) deja ver todas", () => {
    for (const initialFamily of ["pharmacological", "inventada"]) {
      const html = renderToStaticMarkup(createElement(LibraryBody, { library: libraryOf(), initialFamily }));
      expect(html, initialFamily).toContain("Acción A del backend.");
      expect(html, initialFamily).toContain("Acción B del backend.");
      expect(html, initialFamily).toMatch(/RIDGE: radiación \(<span class="num">1<\/span>\)/);
    }
  });
});

describe("contraindicaciones y efectos en la tabla (§5.35.7)", () => {
  const html = renderToStaticMarkup(createElement(LibraryBody, { library: libraryOf() }));

  it("dos columnas con su dibujo, distinto de los demás y que no es el triángulo de «mirarlo»", () => {
    expect(html).toMatch(thSign(CONTRAINDICATIONS_PICTOGRAM, "Contraindicaciones</span></th>", " scope=\"col\""));
    expect(html).toMatch(
      thSign(ADVERSE_EFFECTS_PICTOGRAM, "Efectos a tener en cuenta</span></th>", ' scope="col" class="library-head-whole"'),
    );
    const drawings = [CONTRAINDICATIONS_PICTOGRAM, ADVERSE_EFFECTS_PICTOGRAM, ...Object.values(FAMILY_PICTOGRAMS)];
    expect(new Set(drawings).size).toBe(drawings.length);
    for (const name of [CONTRAINDICATIONS_PICTOGRAM, ADVERSE_EFFECTS_PICTOGRAM]) {
      expect(isPictogramName(name), name).toBe(true);
      expect(name).not.toBe("shape-triangle");
    }
  });

  it("la tarjeta lleva los mismos dos dibujos en sus claves (§5.36.19)", () => {
    const card = renderToStaticMarkup(
      createElement(CountermeasureFacts, { measure: measureOf({ adverse_effects_note: "efecto del backend" }) }),
    );
    expect(card).toMatch(taggedPictogram("dt", CONTRAINDICATIONS_PICTOGRAM, "Contraindicaciones</dt>"));
    expect(card).toMatch(taggedPictogram("dt", ADVERSE_EFFECTS_PICTOGRAM, "Efectos a tener en cuenta</dt>"));
  });

  it("la cabecera de los efectos no se parte: su clase y la regla que la deja en una línea", () => {
    expect(html).toMatch(
      thSign(ADVERSE_EFFECTS_PICTOGRAM, "Efectos a tener en cuenta</span></th>", ' scope="col" class="library-head-whole"'),
    );
    const css = readFileSync(fileURLToPath(new URL("../styles.css", import.meta.url)), "utf-8");
    expect(css).toMatch(/table\.library-table th\.library-head-whole \{\s*white-space: nowrap;\s*\}/);
  });

  it("van tras el respaldo, como en la tarjeta: lo que hay que saber antes de adoptar", () => {
    const heads = [...html.matchAll(/<th scope="col"[^>]*>[\s\S]*?<\/th>/g)].map((match) =>
      match[0].replace(/<svg[\s\S]*?<\/svg>/g, "").replace(/<[^>]+>/g, ""),
    );
    expect(heads.slice(0, 8)).toEqual([
      "Contramedida",
      "Familia",
      "Respaldo",
      "Contraindicaciones",
      "Efectos a tener en cuenta",
      "Tiempo de tripulación",
      "Seguimiento",
      "Recursos",
    ]);
  });

  it("la contraindicación pendiente, tal cual del backend, en secundario y sin color", () => {
    expect(html).toContain(`<div class="library-note"><span class="secondary">${TEXTS.contraindications}</span></div>`);
  });

  it("una contraindicación escrita por la revisión médica va en el peso normal", () => {
    const base = libraryOf();
    const written = measureOf({
      id: "a",
      contraindications_note: "nota de la revisión",
      contraindications_display: "nota de la revisión",
    });
    const body = renderToStaticMarkup(
      createElement(LibraryBody, { library: { ...base, countermeasures: [written, base.countermeasures[1]!] } }),
    );
    expect(body).toContain(`<div class="library-note">nota de la revisión</div>`);
  });

  it("el efecto escrito, tal cual; sin nada escrito, la marca del registro vacío", () => {
    expect(html).toContain(`<div class="library-note">${TEXTS.adverse}</div>`);
    expect(html).toMatch(markedHtml(EMPTY_MARK.pictogram ?? "", "nada escrito</span>"));
  });

  it("un efecto ausente (backend anterior) o en blanco tampoco deja la celda vacía", () => {
    const base = libraryOf();
    const absent = measureOf({ id: "a" });
    delete (absent as Partial<typeof absent>).adverse_effects_note;
    const blank = measureOf({ id: "b", ridge: "radiation", adverse_effects_note: "  " });
    const body = renderToStaticMarkup(
      createElement(LibraryBody, { library: { ...base, countermeasures: [absent, blank] } }),
    );
    expect(body.match(/nada escrito/g)).toHaveLength(2);
  });

  it("sin el texto del backend la contraindicación no se inventa: nada escrito", () => {
    const base = libraryOf();
    const bare = measureOf({ id: "a", contraindications_display: "", adverse_effects_note: "x" });
    const body = renderToStaticMarkup(
      createElement(LibraryBody, { library: { ...base, countermeasures: [bare, base.countermeasures[1]!] } }),
    );
    expect(body.match(/nada escrito/g)).toHaveLength(2);
  });

  it("la base del tiempo se parte en su columna, con cifra o sin ella", () => {
    expect(html).toMatch(/<div class="library-note"><span class="num">120<\/span> min<details>/);
    expect(html).toContain(`<div class="library-note"><span class="secondary">${TEXTS.crewTimeBasis}</span></div>`);
  });

  it("sin cifra, la base larga se pliega con su texto entero dentro; la corta sigue a la vista", () => {
    const long = "x".repeat(TIME_BASIS_VISIBLE_CHARS + 1);
    expect(timeBasisFolds(measureOf({ crew_time_basis: long }))).toBe(true);
    expect(timeBasisFolds(measureOf({ crew_time_basis: "x".repeat(TIME_BASIS_VISIBLE_CHARS) }))).toBe(false);
    expect(timeBasisFolds(measureOf({ crew_time_minutes: 5, crew_time_basis: long }))).toBe(false);
    const base = libraryOf();
    const body = renderToStaticMarkup(
      createElement(LibraryBody, {
        library: { ...base, countermeasures: [measureOf({ id: "a", crew_time_basis: long }), base.countermeasures[1]!] },
      }),
    );
    expect(body).toMatch(
      new RegExp(`<div class="library-note"><details><summary>${pictogramSvg(uiPictogram("source"))}sin cifra</summary><p class="secondary">${long}</p></details></div>`),
    );
  });

  it("en la biblioteca de verdad solo se pliega la base que cita su fuente literal", () => {
    const entries = (
      JSON.parse(read("../../../backend/app/data/countermeasures.json")) as {
        countermeasures: { id: string; crew_time_minutes: number | null; crew_time_basis: string }[];
      }
    ).countermeasures;
    const folded = entries.filter((entry) => timeBasisFolds(measureOf(entry))).map((entry) => entry.id);
    expect(folded.length).toBeGreaterThan(0);
    expect(folded.length).toBeLessThanOrEqual(3);
  });
});
