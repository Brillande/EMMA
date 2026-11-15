import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram } from "../advisor/visibleText";
import { isPictogramName } from "../icons/registry";
import type { Facilities, FacilityQuote } from "../lib/api";
import { MISSING_MARK, UNKNOWN_MARK, UNKNOWN_PICTOGRAM, mark } from "../lib/marks";
import { signPictogram } from "../lib/uiMarks";
import { FacilitiesPanel, FacilitiesView } from "./FacilitiesPanel";
import { addressesIn } from "../lib/urlWrapMarkup";
import { FACILITIES_PICTOGRAM, STATUS_MARKS, STEP_SIGNS, statusMark, stepSign } from "./facilities";

// Las claves que declara el backend (`app/evidence/facilities.py`): un eslabón o un estado nuevo
// sin signo saldría con la marca de «desconocido», y esta prueba lo dice antes.
const BACKEND = readFileSync(fileURLToPath(new URL("../../../backend/app/evidence/facilities.py", import.meta.url)), "utf-8");

function backendKeys(block: string): string[] {
  const body = new RegExp(`${block}: dict\\[str, str\\] = \\{([^}]*)\\}`).exec(BACKEND)?.[1] ?? "";
  return [...body.matchAll(/"([a-z_]+)":/g)].map((match) => match[1]!);
}

function quote(over: Partial<FacilityQuote>): FacilityQuote {
  return {
    quote: "European Physiology Modules are an International Standard Payload Rack",
    where: "cuerpo de la página",
    ref: "esa-epm",
    source: "ESA · Columbus · European Physiology Modules",
    url: "https://www.esa.int/",
    organization: "ESA",
    date: null,
    population: null,
    population_display: "no aplica",
    evidence_type: "agency_page",
    evidence_type_display: "página de agencia",
    unverified_display: ["fecha"],
    ...over,
  };
}

// Como lo escribe el backend: la consola no lo redacta.
const FACILITIES: Facilities = {
  note: "Dos instalaciones europeas de la estación. Inventario: no interviene en ninguna alerta.",
  read_on: "2026-10-22",
  chain: { text: "Columbus/EPM y Biolab deben analizarse como cadenas facility → … → application.", where: "knowledge-base-v1.md §9" },
  facilities: [
    {
      id: "biolab",
      name: "Biolab",
      full_name: "Biological Experiment Laboratory",
      experiment: "TripleLux-A",
      kb_role: { text: "Biolab es principalmente mecanístico", where: "knowledge-base-v1.md §9" },
      scope_caveat: "Células de rata en cultivo, no personas.",
      links: [
        {
          step: "facility",
          label: "instalación",
          status: "read",
          status_text: "leído en la fuente",
          quotes: [quote({ quote: "Biolab supports biological experiments on micro-organisms" })],
          missing: null,
        },
        {
          step: "parameter",
          label: "parámetro",
          status: "read",
          status_text: "leído en la fuente",
          quotes: [
            quote({
              quote: "We measured the oxidative burst reaction in mammalian macrophages",
              ref: "thiel-2017",
              source: "Thiel CS et al. Sci Rep. 2017",
              population: "animal",
              population_display: "animal",
              unverified_display: [],
            }),
          ],
          missing: null,
        },
        {
          step: "provider",
          label: "proveedor",
          status: "partial",
          status_text: "leído, con un hueco",
          quotes: [quote({ quote: "EADS Astrium, Toulouse, France" })],
          missing: { what: "Quién fabricó el contenedor.", searched: ["columna Developer(s): vacía"] },
        },
        {
          step: "dataset",
          label: "conjunto de datos",
          status: "not_found",
          status_text: "sin verificar: buscado y no encontrado",
          quotes: [],
          missing: { what: "Un conjunto de datos de TripleLux-A.", searched: ["OSDR: sin resultado"] },
        },
      ],
      unsourced: ["conjunto de datos"],
    },
  ],
  not_found: ["La página de Biolab no dice «crew time»."],
};

describe("las marcas de las cadenas de instalación", () => {
  it("cada eslabón que declara el backend tiene su signo, y existe", () => {
    expect(Object.keys(STEP_SIGNS)).toEqual(backendKeys("STEPS"));
    for (const sign of Object.values(STEP_SIGNS)) expect(isPictogramName(signPictogram(sign))).toBe(true);
    expect(isPictogramName(FACILITIES_PICTOGRAM)).toBe(true);
    // Un eslabón que la interfaz no conoce, ni una clave heredada, se pintan como otro.
    expect(stepSign("sponsor")).toEqual({ pictogram: UNKNOWN_PICTOGRAM });
    expect(stepSign("constructor")).toEqual({ pictogram: UNKNOWN_PICTOGRAM });
  });

  it("los nueve eslabones llevan nueve dibujos distintos: uno por concepto", () => {
    const drawn = Object.values(STEP_SIGNS).map(signPictogram);
    expect(new Set(drawn).size).toBe(drawn.length);
  });

  it("cada estado del backend tiene su marca; lo no encontrado, el cian del dato ausente", () => {
    expect(Object.keys(STATUS_MARKS).sort()).toEqual(backendKeys("STATUSES").sort());
    expect(statusMark("not_found")).toEqual(MISSING_MARK);
    expect(statusMark("partial")).toEqual(mark("circle-half-right", null));
    // Lo leído no es la marca de «hecho» ni lleva color, y uno desconocido no se pinta como leído.
    expect(statusMark("read").pictogram).not.toBe("check");
    expect(statusMark("read").color).toBeNull();
    expect(statusMark("verified")).toEqual(UNKNOWN_MARK);
    expect(statusMark("toString")).toEqual(UNKNOWN_MARK);
  });
});

describe("<FacilitiesPanel>", () => {
  it("mientras consulta: el matraz en el título y la marca de cargando", () => {
    const html = renderToStaticMarkup(createElement(FacilitiesPanel));
    expect(html).toMatch(taggedPictogram("h2", "flask", "Instalaciones de Columbus: EPM y Biolab"));
    expect(html).toMatch(markedHtml("refresh", "Consultando las instalaciones…"));
  });

  it("pinta cada eslabón con su signo y su estado, con las palabras del backend", () => {
    const html = renderToStaticMarkup(createElement(FacilitiesView, { facilities: FACILITIES }));
    expect(html).toMatch(taggedPictogram("dt", "flask", "instalación"));
    expect(html).toMatch(taggedPictogram("dt", "table-grid", "conjunto de datos"));
    expect(html).toMatch(markedHtml("book-open", "leído en la fuente"));
    expect(html).toMatch(markedHtml("circle-half-right", "leído, con un hueco"));
    expect(html).toMatch(markedHtml("ring-dotted", "sin verificar: buscado y no encontrado", "cyan"));
    // El hueco dice qué falta, en cian, y dónde se buscó.
    expect(html).toMatch(markedHtml("ring-dotted", "Un conjunto de datos de TripleLux-A.", "cyan"));
    expect(html).toContain("<li>OSDR: sin resultado</li>");
    expect(html).toMatch(markedHtml("ring-dotted", "conjunto de datos", "cyan"));
  });

  it("la cadena de células de rata lleva su salvedad y la frase de un animal, en amarillo", () => {
    const html = renderToStaticMarkup(createElement(FacilitiesView, { facilities: FACILITIES }));
    expect(html).toMatch(markedHtml("shape-triangle", "Células de rata en cultivo, no personas.", "yellow"));
    expect(html).toMatch(markedHtml("paw", "animal", "yellow"));
    // Las frases de la fuente, en su idioma, y lo que la ficha no tiene verificado, en cian.
    expect(html).toContain('<q lang="en">We measured the oxidative burst reaction in mammalian macrophages</q>');
    expect(html).toMatch(markedHtml("ring-dotted", "sin verificar: fecha", "cyan"));
    expect(html).toContain("<li>La página de Biolab no dice «crew time».</li>");
  });
});

// Lo pintado, no el código: toda dirección en monoespaciada lleva `url` y se parte (§5.38.12).
describe("instalaciones: las direcciones pintadas se parten", () => {
  it("ningún `.num` sin `url` encierra una dirección", () => {
    const { inNum, unwrapped } = addressesIn(renderToStaticMarkup(createElement(FacilitiesView, { facilities: FACILITIES })));
    expect(inNum).toBeGreaterThan(0);
    expect(unwrapped).toEqual([]);
  });
});
