import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { EvidenceItem, Glossary, MeasurementGuides } from "../lib/api";
import { GlossaryBody, GuidesBody, GuidesCounts } from "./GuidesPanel";
import { LookContext } from "../components/BoardOnly";
import { GUIDES_LABELS, basisCaption, guidePictogram, guideStepsWord, guideSummary, indicatorsLine } from "./guides";

/**
 * El panel de guías y glosario: los pasos, lo leído de vuelo, lo no encontrado, las definiciones y
 * su origen son del backend y salen tal cual; cada paso lleva su frase literal en inglés con su
 * ficha; nada lleva color (nada es un aviso), y las cifras pasan por `lib/format.ts`.
 */

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf-8");

const citation = (id: string): EvidenceItem => ({
  id,
  title: `Título ${id}`,
  source: `Fuente ${id}`,
  url: null,
  doi: null,
  pmid: null,
  organization: null,
  date: null,
  evidence_type: null,
  evidence_type_display: "página de agencia",
  evidence_context: null,
  population: "human",
  population_display: "humano",
  notes: null,
  not_applicable: [],
  outside_enum: [],
  outside_enum_display: [],
  unverified: [],
  unverified_display: [],
  relevance: null,
  scope_caveat: null,
  scope_in_view: null,
  grade: {
    source: `Fuente ${id}`,
    pmid: null,
    basis: "none",
    tier: "desconocido",
    label: "desconocido",
    preclinical: false,
    reason: "",
    signals: {},
    missing: [],
  } as unknown as EvidenceItem["grade"],
});

const guides: MeasurementGuides = {
  scope: "Alcance del backend.",
  guides: [
    {
      id: "g1",
      title: "Guía del backend",
      indicators: [
        { key: "systolic-bp", display_es: "Nombre uno", equipment: "equipo uno", mode_display: "modo" },
        { key: "diastolic-bp", display_es: "Nombre dos", equipment: null, mode_display: null },
      ],
      steps: [
        {
          text: "Paso uno del backend.",
          basis: [{ quote: "Literal one.", where: "Sección A", read_on: "2026-11-03", citation: citation("r1") }],
        },
        {
          text: "Paso dos del backend.",
          basis: [
            { quote: "Literal two.", where: "Sección B", read_on: "2026-11-03", citation: citation("r1") },
            { quote: "Literal three.", where: "Sección C", read_on: "2026-11-03", citation: citation("r1") },
          ],
        },
      ],
      in_flight: [],
      not_found: ["Lo no encontrado, del backend."],
    },
    {
      id: "g2",
      title: "Solo de vuelo",
      indicators: [{ key: "body-weight", display_es: "Masa", equipment: null, mode_display: null }],
      steps: [],
      in_flight: [
        {
          text: "Lo leído de vuelo, del backend.",
          basis: [{ quote: "Flight literal.", where: "Resumen", read_on: "2026-11-03", citation: citation("r2") }],
        },
      ],
      not_found: ["Sin procedimiento leído."],
    },
  ],
  elsewhere: [{ id: "e1", text: "Lo de otro panel.", route: "/api/imaging/protocols", module: "m.py" }],
};

const glossary: Glossary = {
  scope: "Alcance del glosario.",
  terms: [
    {
      id: "t1",
      term: "Término de EMMA",
      definition: "Definición del backend.",
      origin: "emma",
      origin_display: "definición de EMMA",
      document: "backend/app/x.py",
      basis: [],
    },
    {
      id: "t2",
      term: "Término de fuente",
      definition: "Otra definición.",
      origin: "source",
      origin_display: "definición tomada de la fuente",
      document: null,
      basis: [{ quote: "Source literal.", where: "Sección", read_on: "2026-11-03", citation: citation("r3") }],
    },
  ],
};

describe("guías de medida", () => {
  const html = renderToStaticMarkup(createElement(GuidesBody, { guides }));

  it("enseña los pasos, lo de vuelo y lo no encontrado tal cual del backend", () => {
    for (const text of [
      "Alcance del backend.",
      "Paso uno del backend.",
      "Paso dos del backend.",
      "Lo leído de vuelo, del backend.",
      "Lo no encontrado, del backend.",
      "Lo de otro panel.",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).toContain(GUIDES_LABELS.inFlight);
    expect(html).toContain(GUIDES_LABELS.notFound);
  });

  it("cada paso lleva su frase literal en inglés, dónde y cuándo se leyó, y su ficha una vez", () => {
    expect(html).toContain('<blockquote lang="en">Literal one.</blockquote>');
    expect(html).toContain("Fuente r1, Sección B · leído el 2026-11-03");
    // El paso dos cita la misma ficha dos veces: la ficha sale una vez dentro de ese paso.
    const stepTwo = html.slice(html.indexOf("Paso dos del backend."), html.indexOf("Solo de vuelo"));
    expect(stepTwo.split("Título r1").length - 1).toBe(1);
  });

  it("los pasos van numerados y lo de vuelo no", () => {
    expect(html).toContain("<ol>");
    const flight = html.slice(html.indexOf("Solo de vuelo"));
    expect(flight).toContain("<ul>");
  });

  it("el rótulo plegado cuenta los pasos con formatNumber y dice cuándo no hay ninguno", () => {
    expect(guideSummary(guides.guides[0]!)).toBe("Guía del backend · 2 pasos");
    expect(guideSummary(guides.guides[1]!)).toBe("Solo de vuelo · sin pasos con fuente");
    expect(indicatorsLine(guides.guides[0]!)).toBe("Nombre uno (equipo uno) · Nombre dos");
  });

  it("bajo la concha nueva, cada guía es una fila con el dibujo de su indicador y sus pasos aparte; el alcance, a la vista", () => {
    expect(guideStepsWord(guides.guides[0]!)).toBe("2 pasos");
    expect(guidePictogram(guides.guides[0]!)).toBe("gauge");
    expect(guidePictogram({ ...guides.guides[0]!, indicators: [] })).toBeNull();
    expect(html).toMatch(/data-pictogram="gauge"[^>]*>.*?<\/svg><span class="guide-title" title="Guía del backend">Guía del backend<\/span> <span class="guide-steps">2 pasos<\/span>/);
    // El alcance dice que las guías no dicen qué hacer con el resultado (invariante 7): no se pliega.
    expect(html).not.toContain("board-detail");
    expect(html.indexOf("Alcance del backend.")).toBeLessThan(html.indexOf("Guía del backend"));
    const classic = renderToStaticMarkup(createElement(LookContext.Provider, { value: "classic" }, createElement(GuidesBody, { guides })));
    expect(classic).toContain("Guía del backend · 2 pasos");
    expect(classic).not.toContain("guide-steps");
    expect(classic).not.toContain("board-detail");
    expect(classic.indexOf("Alcance del backend.")).toBeLessThan(classic.indexOf("Guía del backend"));
  });

  it("un día de lectura mal formado falla en vez de mostrarse", () => {
    const basis = { ...guides.guides[0]!.steps[0]!.basis[0]!, read_on: "03/11/2026" };
    expect(() => basisCaption(basis)).toThrow(RangeError);
  });
});

describe("glosario", () => {
  const html = renderToStaticMarkup(createElement(GlossaryBody, { glossary }));

  it("cada término lleva su definición y el rótulo de su origen, del backend", () => {
    for (const text of [
      "Término de EMMA",
      "Definición del backend.",
      "definición de EMMA",
      "<code>backend/app/x.py</code>",
      "definición tomada de la fuente",
      '<blockquote lang="en">Source literal.</blockquote>',
    ]) {
      expect(html).toContain(text);
    }
  });
});

describe("las fichas del tablero", () => {
  it("cuentan las guías y los términos que sirvió el backend, con formatNumber", () => {
    const html = renderToStaticMarkup(createElement(GuidesCounts, { guides: 10, terms: 14 }));
    expect(html).toContain('role="group" aria-label="Guías y glosario"');
    expect(html).toMatch(/Guías<\/span><span class="stat-value"><span class="num">10<\/span>/);
    expect(html).toMatch(/Glosario<\/span><span class="stat-value"><span class="num">14<\/span> <span class="stat-unit">términos/);
  });

  it("lo que carga o falló no se pinta como cero: su marca y su palabra", () => {
    const html = renderToStaticMarkup(createElement(GuidesCounts, { guides: "loading", terms: "failed" }));
    expect(html).not.toContain('class="num"');
    expect(html).toContain("cargando");
    expect(html).toMatch(/c-gray"><svg[^>]*data-pictogram="slash-circle"[^>]*>.*?<\/svg>no disponible/);
  });
});

describe("el panel no redacta ni colorea", () => {
  const source = read("./GuidesPanel.tsx") + read("./guides.ts");

  it("no escribe colores ni clases de color: nada aquí es un aviso", () => {
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgb\(|\bc-(?:red|yellow|amber|green|cyan|gray|grey)\b/);
  });

  it("no lleva ninguna cifra clínica escrita en la interfaz", () => {
    expect(source).not.toMatch(/mm ?Hg|°C|\d+ ?%/);
  });
});
