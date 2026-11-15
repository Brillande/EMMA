/**
 * Los perfiles lado a lado en inglés (`lib/i18n.ts`): los rótulos de la tabla salen en inglés; cada
 * frase, rótulo de aspecto, nota y cita es del backend y se pinta tal cual.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LookContext } from "../components/BoardOnly";
import type { ProfileMatrix, ProfileMatrixCell } from "../lib/api";
import { language } from "../lib/i18n";
import { MissionProfilesView } from "./MissionProfilesPanel";

const cell = (over: Partial<ProfileMatrixCell> = {}): ProfileMatrixCell => ({
  key: "comm_delay",
  label: "rotulo",
  status: "read",
  status_text: "ESTADO-DEL-BACKEND",
  statement: "frase",
  citations: [
    {
      ref: "ficha",
      title: "TITULO-DE-LA-PAGINA",
      url: null,
      section: "APARTADO",
      quote: "A literal sentence read on the page.",
      read_on: "2026-10-13",
    },
  ],
  discrepancy: null,
  searched: null,
  emma_note: null,
  text: "FRASE-DEL-BACKEND",
  reused_from: ["OTRO-PERFIL"],
  ...over,
});

const matrix: ProfileMatrix = {
  note: "NOTA-MATRIZ",
  declared_id: "perfil-a",
  declared_note: "NOTA-DECLARADO",
  declared_text: null,
  no_source: "sin fuente segun el backend",
  aspects: [{ key: "comm_delay", label: "ASPECTO-A", reused_only: false }],
  profiles: [{ id: "perfil-a", display: "PERFIL-A", declared: true, cells: [cell()] }],
  reused_note: "NOTA-REUTILIZADA",
  medical_note: "NOTA-MEDICA",
  pages_read: [{ title: "Pagina", url: null, read_on: ["2026-10-13"] }],
};

describe("los perfiles lado a lado en inglés", () => {
  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
  });

  it("la tabla: rótulos propios en inglés, frases y citas del backend tal cual", () => {
    for (const look of ["classic", "reference"] as const) {
      const html = renderToStaticMarkup(
        createElement(LookContext.Provider, { value: look }, createElement(MissionProfilesView, { matrix })),
      );
      expect(html).toContain('aria-label="Mission profiles side by side"');
      expect(html).toContain('aria-label="Profile by aspect"');
      expect(html).toContain("Aspect");
      expect(html).toContain("Declared profile");
      expect(html).toContain("Read earlier for: OTRO-PERFIL");
      expect(html).toContain("Statements read (");
      expect(html).toContain("APARTADO; read on ");
      expect(html).toContain("Pages read:");
      for (const backend of ["NOTA-MATRIZ", "PERFIL-A", "ASPECTO-A", "FRASE-DEL-BACKEND", "TITULO-DE-LA-PAGINA", "A literal sentence read on the page."]) {
        expect(html).toContain(backend);
      }
      expect(html).not.toMatch(/Perfiles de misión|Perfil declarado|Leída antes|Frases leídas|leído el|Páginas leídas/);
    }
  });

  it("en el tablero, el recuento por estado lleva su rótulo en inglés", () => {
    const html = renderToStaticMarkup(createElement(MissionProfilesView, { matrix }));
    expect(html).toContain('aria-label="Profiles and cells by state"');
    expect(html).toContain("ESTADO-DEL-BACKEND");
  });
});
