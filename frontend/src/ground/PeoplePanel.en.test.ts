/**
 * «Personas y organizaciones» y «Fuentes del contexto» en inglés (`lib/i18n.ts`): los rótulos, los
 * recuentos con su singular y lo que falta («sin leer», «sin dirección en la ficha»). Las palabras
 * de estado y los papeles son del backend y pasan tal cual (relleno en mayúsculas).
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LookContext } from "../components/BoardOnly";
import type { ContextSources, People } from "../lib/api";
import { ContextSourcesPanel, ContextSourcesView } from "./ContextSourcesPanel";
import { PeoplePanel, PeopleView } from "./PeoplePanel";

const look = (value: "reference" | "classic", element: Parameters<typeof renderToStaticMarkup>[0]) =>
  renderToStaticMarkup(createElement(LookContext.Provider, { value }, element));

const reference = {
  id: "ref-1",
  title: "TITULO",
  source: "ORIGEN",
  url: null,
  date: "2011-12-01",
  year: "2011",
  evidence_type_display: "CLASE",
  organization: "ORG",
  authors: ["Basner M"],
  et_al: false,
  named_people: [],
  affiliations: [],
  named_organizations: [],
};

const people = {
  note: "n",
  affiliation_rule: "a",
  named_organization_rule: "r",
  same_person_rule: "s",
  no_year: "SIN-FECHA",
  no_organization: "SIN-ORGANIZACION",
  references: 1,
  organizations: [
    {
      name: "ORG",
      references: [reference],
      named_by: [
        { ref: "ref-2", role: "x", role_text: "PAPEL", title: "T2", year: null },
        { ref: "ref-3", role: "x", role_text: "PAPEL", title: "T3", year: "2020" },
      ],
    },
  ],
  without_organization: [],
  people: [
    {
      name: "Basner M",
      citations: [{ ref: "ref-1", role: "author", role_text: "PAPEL", title: "TITULO", year: "2011", organization: "ORG", affiliation_text: null }],
    },
  ],
} as unknown as People;

describe("personas y organizaciones en inglés", () => {
  it("sin respuesta todavía, el título y la espera", () => {
    const html = renderToStaticMarkup(createElement(PeoplePanel));
    expect(html).toContain('aria-label="People and organizations"');
    expect(html).toContain("Loading people and organizations…");
    expect(html).not.toMatch(/Personas|Consultando/);
  });

  it("en la consola clásica, los recuentos con su singular", () => {
    const html = look("classic", createElement(PeopleView, { people }));
    expect(html).toContain("1 organization · 1 person · 1 registry record");
    expect(html).toContain("· 1 record");
    expect(html).toContain("named by 2 records");
    expect(html).not.toMatch(/organización|persona|ficha|la nombra/);
  });

  it("los apartados y las líneas de cada ficha", () => {
    const html = look("reference", createElement(PeopleView, { people }));
    for (const label of [
      ">Organizations<",
      ">People<",
      "Registry records",
      'aria-label="Organization ORG"',
      'aria-label="People in the records"',
      "Signed by: ",
      "organization of the record: ORG",
      "Show detail: how they are counted",
      "Show detail: when it is the same person",
    ]) {
      expect(html).toContain(label);
    }
    // La palabra de la fecha que falta es del backend.
    expect(html).toContain("SIN-FECHA");
    expect(html).not.toMatch(/Organizaciones|Personas|Fichas del registro|Firman|organización de la ficha|cómo se cuentan/);
  });
});

const card = {
  id: "ficha",
  title: "TITULO-DE-LA-FICHA",
  source: "ORIGEN",
  url: null,
  doi: null,
  pmid: null,
  organization: null,
  date: "2026-10",
  evidence_type: null,
  evidence_type_display: "CLASE",
  evidence_context: null,
  population: null,
  population_display: "POBLACION",
  notes: null,
  not_applicable: [],
  outside_enum: [],
  outside_enum_display: [],
  unverified: [],
  unverified_display: [],
  grade: { source: "", pmid: null, basis: "none", tier: "desconocido", label: "", preclinical: false, reason: "" },
};

const sources = {
  note: "n",
  read_on: "2026-10-26",
  lists: [{ id: "spec-17", document: "especificacion.md", section: "§17", title: "Fuentes" }],
  sources: [
    {
      ref: "uno",
      lists: ["spec-17"],
      listed_as: "ROTULO",
      why_added: "MOTIVO",
      status: "not_read",
      status_text: "PALABRA-SIN-LEER",
      not_read: "POR-QUE-NO",
      emma_use: "USO",
      card,
    },
  ],
} as unknown as ContextSources;

describe("las fuentes del contexto en inglés", () => {
  it("sin respuesta todavía, el título y la espera", () => {
    const html = renderToStaticMarkup(createElement(ContextSourcesPanel));
    expect(html).toContain('aria-label="Context sources"');
    expect(html).toContain("Loading the sources…");
    expect(html).not.toMatch(/Fuentes del contexto|Consultando/);
  });

  it("lo no leído se dice, con el motivo del backend, y la ficha sin dirección también", () => {
    const html = look("reference", createElement(ContextSourcesView, { body: sources }));
    expect(html).toContain(">Not read<");
    expect(html).toContain("POR-QUE-NO");
    expect(html).toContain("PALABRA-SIN-LEER");
    expect(html).toContain("no address in the record");
    expect(html).not.toMatch(/Sin leer|sin dirección/);
  });

  it("los rótulos y el recuento de fuentes", () => {
    const html = look("reference", createElement(ContextSourcesView, { body: sources }));
    for (const label of [
      "Reading of ",
      'aria-label="Sources by status"',
      "</span> source<",
      'aria-label="Source TITULO-DE-LA-FICHA"',
      "Team list",
      "Why it was added",
      "What for in EMMA",
      "Show detail: 1 source, one per row",
      "Show detail: where they come from",
    ]) {
      expect(html).toContain(label);
    }
    expect(html).not.toMatch(/Lectura del|Fuentes por estado|fuente|Lista del equipo|Por qué se añadió|Para qué en EMMA|de dónde salen/);
  });
});
