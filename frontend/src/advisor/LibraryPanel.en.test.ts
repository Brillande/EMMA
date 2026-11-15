/**
 * La biblioteca de contramedidas en inglés (`lib/i18n.ts`): el título, las esperas y los fallos
 * del panel y de las contramedidas en investigación. Las fichas (acción, respaldo, efectos) las
 * redacta el backend.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ResearchCountermeasures } from "../lib/api";
import { requestOutcome } from "../lib/marks";
import { LibraryPanel, ResearchSection, readOnLabel } from "./LibraryPanel";

describe("la biblioteca en inglés", () => {
  it("el panel mientras carga", () => {
    const html = renderToStaticMarkup(createElement(LibraryPanel));
    expect(html).toContain('aria-label="Countermeasure library"');
    expect(html).toContain("Loading the countermeasures under research…");
    expect(html).not.toMatch(/Biblioteca|Cargando las contramedidas/);
  });

  it("las contramedidas en investigación: el fallo y el plegable con sus cabeceras", () => {
    const failed = renderToStaticMarkup(
      createElement(ResearchSection, { research: null, failure: requestOutcome(new Error("MOTIVO")) }),
    );
    expect(failed).toContain("Could not read the countermeasures under research:");
    expect(failed).not.toContain("No se pudieron");

    const research = {
      note: "NOTA-DEL-BACKEND",
      read_on: "2026-10-01",
      entries: [],
      not_found: [],
      read_not_included: [],
      sources: {},
    } as unknown as ResearchCountermeasures;
    const html = renderToStaticMarkup(createElement(ResearchSection, { research, failure: null }));
    for (const word of [
      "Under research: not offered (",
      "Countermeasure under research",
      "RIDGE hazard",
      "What the source says",
      "Searched and not found",
      "Read and not included",
      "What was read (",
      "NOTA-DEL-BACKEND",
    ]) {
      expect(html, word).toContain(word);
    }
    expect(html).not.toMatch(/En investigación|Peligro RIDGE|Lo que dice|Buscado|Leído|Qué se leyó/);
  });

  it("una fecha de lectura ilegible lo dice en inglés", () => {
    expect(readOnLabel("no-es-fecha")).toBe("reading date not readable");
  });
});
