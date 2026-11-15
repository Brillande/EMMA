import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
// Sin los `data-ui` del asistente: estas pruebas miran el marcado del panel.
import { renderToStaticMarkup } from "../assistant/staticMarkup";
import { describe, expect, it } from "vitest";

import { markedHtml, pictogramSvg, taggedPictogram, visibleText } from "../advisor/visibleText";
import type { EvidenceItem } from "../lib/api";
import { EvidenceEntry, READING_NOTE_SUMMARY, SCOPE_AND_READING_SUMMARY } from "./EvidenceEntry";

/**
 * La ficha de una fuente con su nota plegada: que se lee SIN abrir nada y que no se ha perdido.
 *
 * Por que existe: junto a una hipotesis de cabina, el «Alcance» repetia la nota de lectura entera
 * (organizacion releida en PubMed incluida), larga para la consola de tripulacion (undecima
 * ronda). Ahora va a la vista lo que el backend corta (`scope_in_view`) y la nota entera,
 * plegada. Se pinta a HTML estatico y se le quita lo que un `<details>` cerrado esconde.
 */

const render = (item: EvidenceItem) => renderToStaticMarkup(createElement(EvidenceEntry, { item }));
// Lo que React escapa al pintar texto: también < y > (una nota puede decir «>90%»).
const escaped = (text: string) =>
  text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

const LEAD = "Modelo murino: 12 ratones en la ISS. NO mide signos vitales humanos.";
const LOG = "Metadatos del estudio leídos el 2026-10-13 en osdr.nasa.gov (editor: «NASA GeneLab»).";

const card = (notes: string | null, inView: string | null): EvidenceItem => ({
  id: "ficha",
  title: "Una fuente",
  source: "NASA OSDR",
  url: "https://osdr.nasa.gov/",
  doi: null,
  pmid: null,
  organization: null,
  date: null,
  evidence_type: "dataset",
  evidence_type_display: "conjunto de datos",
  evidence_context: "iss",
  population: "animal",
  population_display: "animal",
  notes,
  not_applicable: [],
  outside_enum: [],
  outside_enum_display: [],
  unverified: [],
  unverified_display: [],
  relevance: null,
  scope_caveat: notes,
  scope_in_view: inView,
  grade: {
    source: "",
    pmid: null,
    basis: "none",
    tier: "desconocido",
    label: "desconocido",
    preclinical: false,
    reason: "",
  },
});

describe("una nota con alcance delante y bitacora detras", () => {
  const note = `${LEAD} ${LOG}`;
  const html = render(card(note, LEAD));
  const view = visibleText(html);

  it("ensena a la vista el alcance que corta el backend, en amarillo y con el triangulo", () => {
    expect(html).toMatch(markedHtml("shape-triangle", `Alcance: ${escaped(LEAD)}</span></p>`, "yellow"));
    // El amarillo nunca va sin forma (§5.33.5).
    expect(html).not.toMatch(/<p class="c-yellow">/);
    expect(view).toContain(`Alcance: ${LEAD}`);
  });

  it("pliega la bitacora: a la vista solo queda el rotulo del plegable", () => {
    expect(view).not.toContain("leídos el 2026-10-13");
    expect(view).toContain(READING_NOTE_SUMMARY);
    // El plegable lleva el libro abierto de «lo leido en la fuente» (`sourceText`).
    expect(html).toMatch(taggedPictogram("summary", "book-open", READING_NOTE_SUMMARY));
  });

  it("no pierde texto: la nota entera, sin recortar, esta dentro del plegable", () => {
    expect(html).toMatch(markedHtml("shape-triangle", `${escaped(note)}</span></p>`, "yellow"));
    expect(html).toMatch(
      new RegExp(`<details><summary>${pictogramSvg("book-open")}[^<]+</summary><p><span class="mark c-yellow">`),
    );
  });

  it("la poblacion animal sigue a la vista, en amarillo y con la huella junto a la palabra", () => {
    expect(html).toMatch(markedHtml("paw", "población: animal</span>", "yellow"));
    expect(view).toContain("población: animal");
  });
});

describe("una nota que empieza por la lectura", () => {
  const html = render(card(LOG, null));
  const view = visibleText(html);

  it("no ensena «Alcance» a la vista y el rotulo dice que el alcance va dentro", () => {
    expect(view).not.toContain("Alcance:");
    expect(view).toContain(SCOPE_AND_READING_SUMMARY);
    expect(html).toMatch(taggedPictogram("summary", "book-open", SCOPE_AND_READING_SUMMARY));
    expect(view).not.toContain(LOG);
  });

  it("la nota entera sigue en la ficha", () => {
    expect(html).toContain(escaped(LOG));
  });
});

describe("una nota que va entera a la vista", () => {
  it("no lleva plegable si no hay nada que plegar", () => {
    const html = render(card(LEAD, LEAD));
    expect(html).not.toContain("<details");
    expect(visibleText(html)).toContain(`Alcance: ${LEAD}`);
  });

  it("una ficha sin nota no pinta ni alcance ni plegable", () => {
    const html = render(card(null, null));
    expect(html).not.toContain("<details");
    expect(html).not.toContain("Alcance");
  });
});

describe("las fichas reales de la hipotesis de cabina (salida del backend)", () => {
  // El fichero de referencia de `tests/test_habitat.py`: la salida de `correlate` con un CO2
  // alto y varios tripulantes afectados. Sus fichas son las que se ven en el pliegue
  // «Evidencia» de la hipotesis, en la consola de tripulacion y en la de Tierra.
  const golden = JSON.parse(
    readFileSync(
      fileURLToPath(
        new URL("../../../backend/tests/data/context/correlate_sin_ubicacion.json", import.meta.url),
      ),
      "utf-8",
    ),
  ) as { varios_con_co2: { hypotheses: { evidence: EvidenceItem[] }[] } };
  const evidence = golden.varios_con_co2.hypotheses[0]?.evidence ?? [];

  it("cada nota entera sigue en la ficha y la bitacora no queda a la vista", () => {
    const withNotes = evidence.filter((item) => item.scope_caveat !== null);
    expect(withNotes.length).toBeGreaterThan(0);
    for (const item of withNotes) {
      const html = render(item);
      expect(html).toContain(escaped(item.scope_caveat ?? ""));
      // La organizacion releida en PubMed era lo que alargaba la ficha.
      expect(visibleText(html)).not.toContain("organización");
    }
  });

  it("la medida: lo que se lee sin abrir nada, antes y ahora", () => {
    // «Antes» es la misma ficha con la nota entera a la vista, que es como se pintaba.
    const before = evidence.map((item) => visibleText(render({ ...item, scope_in_view: item.scope_caveat })));
    const after = evidence.map((item) => visibleText(render(item)));
    const chars = (texts: string[]) => texts.reduce((sum, text) => sum + text.length, 0);
    // La relacion, no las cifras: corregir una errata en una nota no tiene que romper esta prueba.
    // Medido el 2026-10-20: de 2397 a 1019 caracteres (`compliance/hmi-state-of-the-art.md` §5.29).
    expect(chars(after)).toBeLessThan(chars(before) / 2);
  });
});
