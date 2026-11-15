import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
// Sin los `data-ui` del asistente: estas pruebas miran el marcado del panel.
import { renderToStaticMarkup } from "../assistant/staticMarkup";
import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import { ApiError, type ResearchCountermeasures } from "../lib/api";
import { FAILURE_MARK, REFUSED_MARK, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { FAMILY_PICTOGRAMS, RESEARCH_PICTOGRAM } from "./library";
import { ResearchSection } from "./LibraryPanel";
import { markedHtml, taggedPictogram, thSign } from "./visibleText";

/**
 * Las contramedidas en investigación (§5.36.15): una sección aparte de la biblioteca, plegada, con
 * el matraz y rotulada como en investigación; las palabras y las frases literales son del backend,
 * no hay mando de adoptar ni familia, nada lleva color, y un fallo se pinta con la marca de la
 * decisión del usuario (4xx amarillo con triángulo, caída roja con cruz).
 */

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf-8");

const researchOf = (over: Partial<ResearchCountermeasures> = {}): ResearchCountermeasures => ({
  entries: [
    {
      id: "research-x",
      name: "Nombre del backend",
      ridge: "gravity",
      ridge_display: "campos gravitatorios",
      targets: "Qué ataca, del backend.",
      status: "Estado del backend.",
      flight_note: "Lo que la fuente dice del vuelo.",
      quotes: [
        { ref: "r1", title: "Título 1", source: "Fuente 1", url: null, where: "p. 9", quote: "Literal one." },
        { ref: "r2", title: "Título 2", source: "Fuente 2", url: null, where: "p. 85", quote: "Literal two." },
      ],
      offered: false,
    },
  ],
  note: "nota de lo que está en investigación",
  offered: false,
  read_on: "2026-10-23",
  sources: {
    r1: {
      title: "Título 1",
      source: "Fuente 1",
      url: null,
      extent: "partial",
      extent_text: "leído en parte",
      what: "qué se leyó 1",
      read_on: "2026-10-23",
    },
  },
  not_found: ["lo buscado y no encontrado"],
  read_not_included: ["lo leído y no incluido"],
  ...over,
});

describe("contramedidas en investigación", () => {
  const html = renderToStaticMarkup(createElement(ResearchSection, { research: researchOf(), failure: null }));

  it("va en su plegable, con el matraz y rotulada como en investigación, con cuántas hay", () => {
    expect(isPictogramName(RESEARCH_PICTOGRAM)).toBe(true);
    expect(RESEARCH_PICTOGRAM).not.toBe(uiPictogram("countermeasureLibrary"));
    expect(Object.values(FAMILY_PICTOGRAMS)).not.toContain(RESEARCH_PICTOGRAM);
    expect(html).toMatch(
      taggedPictogram("summary", RESEARCH_PICTOGRAM, "En investigación: no se ofrecen ("),
    );
    expect(html).toMatch(/no se ofrecen \(<span class="num">1<\/span>\)/);
    // Plegada: no se abre sola.
    expect(html.startsWith('<details class="library-research"><summary>')).toBe(true);
    expect(html).toMatch(thSign(RESEARCH_PICTOGRAM, "Contramedida en investigación</span></th>", ' scope="col"'));
  });

  it("pinta las palabras del backend y la frase literal en su idioma, con su ficha y su página", () => {
    for (const text of [
      "nota de lo que está en investigación",
      "Nombre del backend",
      "Qué ataca, del backend.",
      "Estado del backend.",
      "Lo que la fuente dice del vuelo.",
      "lo buscado y no encontrado",
      "lo leído y no incluido",
      "qué se leyó 1",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).toContain('<blockquote lang="en">Literal one.</blockquote>');
    expect(html).toContain('<blockquote lang="en">Literal two.</blockquote>');
    expect(html).toContain("Fuente 1, p. 9");
    expect(html).toContain("Fuente 2, p. 85");
    expect(html).toMatch(markedHtml("ridge-gravity", "campos gravitatorios</span>"));
    expect(html).toMatch(taggedPictogram("summary", uiPictogram("searchedNotFound"), "Buscado y no encontrado"));
  });

  it("lo leído lleva la dirección de su ficha cuando la tiene", () => {
    expect(html).not.toContain('class="num url"');
    const withUrl = renderToStaticMarkup(
      createElement(ResearchSection, {
        research: researchOf({
          sources: {
            r1: {
              title: "Título 1",
              source: "Fuente 1",
              url: "https://example.org/r1.pdf",
              extent: "partial",
              extent_text: "leído en parte",
              what: "qué se leyó 1",
              read_on: "2026-10-23",
            },
          },
        }),
        failure: null,
      }),
    );
    expect(withUrl).toContain('<div class="num url">https://example.org/r1.pdf</div>');
  });

  it("una fuente leída otro día que el del rótulo lleva su día; la del mismo día, no", () => {
    expect(html).not.toMatch(/leído en parte(<!-- -->)? el /);
    const later = renderToStaticMarkup(
      createElement(ResearchSection, {
        research: researchOf({
          sources: {
            r1: {
              title: "Título 1",
              source: "Fuente 1",
              url: null,
              extent: "full",
              extent_text: "leído entero",
              what: "qué se leyó 1",
              read_on: "2026-10-26",
            },
          },
        }),
        failure: null,
      }),
    );
    expect(later.replace(/<!-- -->/g, "")).toContain("Fuente 1: leído entero el 2026-10-26. qué se leyó 1");
    // El rótulo sigue con el día del fichero.
    expect(later).toMatch(/Qué se leyó \((<!-- -->)?2026-10-23(<!-- -->)?\)/);
  });

  it("una fecha de lectura que no se entiende se dice, sin tumbar el panel", () => {
    expect(html).toMatch(/Qué se leyó \((<!-- -->)?2026-10-23(<!-- -->)?\)/);
    // `formatSourceDate` lanza ante esta forma; sin recogerlo, el panel entero (biblioteca
    // incluida) dejaría de pintarse.
    const odd = renderToStaticMarkup(
      createElement(ResearchSection, { research: researchOf({ read_on: "2026-W43-5" }), failure: null }),
    );
    expect(odd).toMatch(/Qué se leyó \((<!-- -->)?fecha de lectura no legible(<!-- -->)?\)/);
    expect(odd).not.toContain("2026-W43-5");
  });

  it("no se ofrece: ni mando de adoptar ni familia, y nada lleva color", () => {
    expect(html).not.toMatch(/<button/);
    expect(html).not.toContain("Familia");
    expect(html).not.toMatch(/c-(red|yellow|blue|cyan|gray|magenta|green)/);
  });

  it("mientras llega dice que llega; un fallo se dice con la marca de la decisión", () => {
    // Dice qué llega: el de la biblioteca, justo encima, también dice «Cargando…».
    expect(renderToStaticMarkup(createElement(ResearchSection, { research: null, failure: null }))).toContain(
      "Cargando las contramedidas en investigación…",
    );
    const refused = renderToStaticMarkup(
      createElement(ResearchSection, { research: null, failure: requestOutcome(new ApiError(404, "no está")) }),
    );
    expect(refused).toMatch(markedHtml(REFUSED_MARK.pictogram ?? "", "No se pudieron leer", "yellow"));
    const failed = renderToStaticMarkup(
      createElement(ResearchSection, {
        research: null,
        failure: requestOutcome(new TypeError("Failed to fetch")),
      }),
    );
    expect(failed).toMatch(markedHtml(FAILURE_MARK.pictogram ?? "", "No se pudieron leer", "red"));
  });

  it("el fichero del backend no comparte ningún id con la biblioteca", () => {
    const research = JSON.parse(read("../../../backend/app/data/countermeasures_research.json")) as {
      entries: { id: string }[];
    };
    const library = JSON.parse(read("../../../backend/app/data/countermeasures.json")) as {
      countermeasures: { id: string }[];
    };
    const ids = new Set(library.countermeasures.map((entry) => entry.id));
    expect(research.entries.length).toBeGreaterThan(0);
    for (const entry of research.entries) expect(ids.has(entry.id), entry.id).toBe(false);
  });
});
