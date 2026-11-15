import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, textNodes } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import type { ContextSource, ContextSources, EvidenceCard } from "../lib/api";
import { MISSING_MARK, UNAVAILABLE_MARK } from "../lib/marks";
import { ContextSourcesPanel, ContextSourcesView } from "./ContextSourcesPanel";
import { STATUS_MARKS, namedLists, sortedSources, statusCounts, statusMark } from "./contextSources";

/**
 * «Fuentes del contexto» en la consola de Tierra (§5.39.20): la marca y el orden de cada estado, y
 * lo que se pinta. Las frases son marcadores: la interfaz las enseña tal cual.
 */

// El enumerado del backend: un estado nuevo sin marca saldría como «no disponible», y esto lo dice antes.
const BACKEND = readFileSync(
  fileURLToPath(new URL("../../../backend/app/evidence/context_sources.py", import.meta.url)),
  "utf-8",
);
const STATUSES = /STATUSES: dict\[str, str\] = \{([^}]*)\}/.exec(BACKEND)?.[1] ?? "";

const card: EvidenceCard = {
  id: "ficha",
  title: "TITULO-DE-LA-FICHA",
  source: "ORIGEN",
  url: "https://example.org/ficha",
  doi: null,
  pmid: null,
  organization: null,
  date: "2026-10",
  evidence_type: null,
  evidence_type_display: "CLASE",
  evidence_context: null,
  population: null,
  population_display: "POBLACION",
  notes: "NOTA-DE-LA-FICHA",
  not_applicable: [],
  outside_enum: [],
  outside_enum_display: [],
  unverified: [],
  unverified_display: [],
  grade: { source: "", pmid: null, basis: "none", tier: "desconocido", label: "", preclinical: false, reason: "" },
};

function source(over: Partial<ContextSource>): ContextSource {
  return {
    ref: "uno",
    lists: ["spec-17"],
    listed_as: "ROTULO-DE-LA-LISTA",
    why_added: null,
    status: "read",
    status_text: "PALABRA-LEIDA",
    not_read: null,
    emma_use: "USO-EN-EMMA",
    card,
    ...over,
  };
}

const body = (sources: ContextSource[]): ContextSources => ({
  note: "NOTA-DEL-INVENTARIO",
  read_on: "2026-10-26",
  lists: [{ id: "spec-17", document: "especificacion.md", section: "§17", title: "Fuentes" }],
  sources,
});

const render = (sources: ContextSource[]) =>
  renderToStaticMarkup(createElement(ContextSourcesView, { body: body(sources) }));

describe("la marca de cada estado", () => {
  it("cada estado del backend tiene marca, y ninguna de más", () => {
    const keys = [...STATUSES.matchAll(/"([a-z_]+)":/g)].map((match) => match[1]!);
    expect(keys.length).toBeGreaterThan(0);
    expect(Object.keys(STATUS_MARKS).sort()).toEqual([...keys].sort());
  });

  it("lo no leído es el dato ausente: cian con su anillo, sin color de alerta", () => {
    expect(statusMark("not_read")).toBe(MISSING_MARK);
    for (const known of Object.values(STATUS_MARKS)) {
      expect(known.color === "red" || known.color === "yellow").toBe(false);
      expect(known.pictogram).not.toBeNull();
    }
  });

  it("lo leído, entero o en parte, no lleva color", () => {
    expect(statusMark("read").color).toBeNull();
    expect(statusMark("partial").color).toBeNull();
    expect(statusMark("read").pictogram).not.toBe(statusMark("partial").pictogram);
  });

  it("un estado desconocido cae en «no disponible», también uno que el objeto hereda", () => {
    expect(statusMark("sin_servir")).toBe(UNAVAILABLE_MARK);
    expect(statusMark("constructor")).toBe(UNAVAILABLE_MARK);
  });
});

describe("el orden y la cuenta", () => {
  const list = [
    source({ ref: "a", status: "read" }),
    source({ ref: "b", status: "partial", status_text: "EN-PARTE" }),
    source({ ref: "c", status: "read" }),
    source({ ref: "d", status: "not_read", status_text: "SIN-LEER" }),
    source({ ref: "e", status: "sin_servir", status_text: "SIN-SERVIR" }),
  ];

  it("lo desconocido y lo menos leído primero; a igual estado, el orden del backend", () => {
    expect(sortedSources(list).map((item) => item.ref)).toEqual(["e", "d", "b", "a", "c"]);
    expect(list[0]?.ref).toBe("a");
  });

  it("la cuenta va en ese orden y con la palabra del backend", () => {
    expect(statusCounts(list)).toEqual([
      { status: "sin_servir", text: "SIN-SERVIR", count: 1 },
      { status: "not_read", text: "SIN-LEER", count: 1 },
      { status: "partial", text: "EN-PARTE", count: 1 },
      { status: "read", text: "PALABRA-LEIDA", count: 2 },
    ]);
  });

  it("una lista que no se conoce se enseña por su identificador", () => {
    const lists = body([]).lists;
    expect(namedLists(["spec-17", "otra"], lists)).toEqual([lists[0], "otra"]);
  });
});

describe("el panel", () => {
  it("consulta al montarse y dice que consulta", () => {
    expect(renderToStaticMarkup(createElement(ContextSourcesPanel))).toContain("Consultando las fuentes…");
  });

  it("pinta lo del backend tal cual, con la fecha de lectura y el enlace a la ficha", () => {
    const html = render([source({})]);
    expect(html).toContain("NOTA-DEL-INVENTARIO");
    expect(html).toContain('<span class="num">2026-10-26</span>');
    expect(html).toContain("ROTULO-DE-LA-LISTA");
    expect(html).toContain("Fuentes · especificacion.md §17");
    expect(html).toContain("USO-EN-EMMA");
    expect(html).toContain('href="https://example.org/ficha"');
    expect(html).toContain("NOTA-DE-LA-FICHA");
    expect(html).toContain("ORIGEN");
    expect(html).toMatch(markedHtml("book-open", "PALABRA-LEIDA"));
    expect(html).not.toContain("c-cyan");
  });

  it("lo no leído, con su motivo en cian y sin color de alerta", () => {
    const html = render([source({ status: "not_read", status_text: "SIN-LEER", not_read: "MOTIVO" })]);
    expect(html).toContain('<span class="c-cyan">SIN-LEER</span>');
    expect(html).toMatch(markedHtml("ring-dotted", "SIN-LEER", "cyan"));
    // Cerrada, su rótulo no abre con el libro de lo leído.
    expect(/<summary[^>]*>(.*?)<\/summary>/.exec(html)?.[1]).not.toMatch(/data-pictogram="book-open"/);
    expect(html).toMatch(markedHtml("ring-dotted", "MOTIVO", "cyan"));
    expect(html).not.toContain("c-red");
    expect(html).not.toContain("c-yellow");
  });

  it("una fuente de fuera de las listas dice por qué se añadió", () => {
    const html = render([source({ lists: [], listed_as: null, why_added: "POR-QUE" })]);
    expect(html).toContain("POR-QUE");
    expect(html).not.toContain("Lista del equipo");
  });

  it("en el tablero, la cuenta por estado son píldoras con su marca; en la clásica, la frase", () => {
    const list = [
      source({ ref: "a" }),
      source({ ref: "b" }),
      source({ ref: "d", status: "not_read", status_text: "SIN-LEER", not_read: "MOTIVO" }),
    ];
    const html = render(list);
    const tally = html.match(/<ul class="board-tally" aria-label="Fuentes por estado">[\s\S]*?<\/ul>/)?.[0] ?? "";
    expect(textNodes(tally)).toEqual(["3", "fuentes", "SIN-LEER", "1", "PALABRA-LEIDA", "2"]);
    expect(tally).toMatch(markedHtml("ring-dotted", "SIN-LEER", "cyan"));
    const classic = renderToStaticMarkup(
      createElement(LookContext.Provider, { value: "classic" }, createElement(ContextSourcesView, { body: body(list) })),
    );
    expect(classic).not.toContain("board-tally");
    expect(classic).toMatch(/PALABRA-LEIDA<\/span>:\s*<span class="num">2<\/span>/);
  });

  it("una ficha sin dirección lo dice, sin enlace vacío", () => {
    const html = render([source({ card: { ...card, url: null } })]);
    expect(html).toMatch(markedHtml("ring-dotted", "sin dirección en la ficha", "cyan"));
    expect(html).not.toContain("<a ");
  });
});
