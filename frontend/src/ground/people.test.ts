import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
// Sin los `data-ui` del asistente: estas pruebas miran el marcado del panel.
import { renderToStaticMarkup } from "../assistant/staticMarkup";
import { describe, expect, it } from "vitest";

import { textNodes, withoutFolded } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import type { People, PeopleReference } from "../lib/api";
import { MISSING_MARK, NO_MARK } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { PeoplePanel, PeopleView } from "./PeoplePanel";
import { ORGANIZATION_CONCEPT, PEOPLE_CONCEPT, authorsLine, countOf, yearCell } from "./people";

// Las claves que sirve el backend (`app/evidence/people.py`): si cambia una, esta prueba lo dice
// antes de que el panel enseñe un hueco.
const BACKEND = readFileSync(
  fileURLToPath(new URL("../../../backend/app/evidence/people.py", import.meta.url)),
  "utf-8",
);

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

const card = (over: Partial<PeopleReference> = {}): PeopleReference => ({
  id: "basner-2011-pvt-b",
  title: "Validity and Sensitivity of a Brief Psychomotor Vigilance Test (PVT-B)",
  source: "Basner M, Mollicone D, Dinges DF. Acta Astronaut. 2011",
  url: "https://pubmed.ncbi.nlm.nih.gov/22025811/",
  date: "2011-12-01",
  year: "2011",
  evidence_type_display: "artículo de revista",
  organization: "University of Pennsylvania School of Medicine",
  authors: ["Basner M", "Mollicone D", "Dinges DF"],
  et_al: false,
  named_people: [],
  affiliations: [],
  named_organizations: [],
  ...over,
});

const orion = card({
  id: "nasa-orion-radiation-protection",
  title: "Scientists and Engineers Evaluate Orion Radiation Protection Plan",
  source: "NASA (22 de septiembre de 2016)",
  date: "2016-09-22",
  year: "2016",
  evidence_type_display: "página de agencia",
  organization: "NASA",
  authors: ["Mark A. Garcia"],
  named_people: [
    {
      name: "Kerry Lee",
      role: "radiation system manager for Orion",
      role_text: "la fuente la nombra como «radiation system manager for Orion» (en la fecha de la fuente, 2016)",
    },
  ],
});

const undated = card({
  id: "esa-epm",
  title: "European Physiology Modules",
  source: "ESA · Science & Exploration",
  date: null,
  year: null,
  evidence_type_display: "página de agencia",
  organization: null,
  authors: [],
});

const people: People = {
  note: "Derivado del registro en cada consulta.",
  affiliation_rule: "La organización de una ficha no es la afiliación de cada firmante.",
  same_person_rule: "Un nombre escrito de dos formas sale dos veces.",
  named_organization_rule: "Una organización que una fuente nombra no es la de esa ficha.",
  no_organization: "sin organización en la ficha",
  no_year: "sin fecha en la ficha",
  organizations: [
    { name: "NASA", references: [orion], named_by: [] },
    {
      name: "Teledyne Brown Engineering Inc.",
      references: [],
      named_by: [
        {
          ref: "nasa-mossi-ii-teledyne-2022",
          title: "MOSSI II contract",
          year: "2022",
          organization: "NASA",
          role: "payload operations",
          role_text: "la fuente la nombra como «payload operations» (en la fecha de la fuente, 2022)",
        },
      ],
    },
    { name: "University of Pennsylvania School of Medicine", references: [card()], named_by: [] },
  ],
  people: [
    {
      name: "Kerry Lee",
      citations: [
        {
          ref: orion.id,
          title: orion.title,
          year: "2016",
          organization: "NASA",
          role: "named",
          role_text: "la fuente la nombra como «radiation system manager for Orion» (en la fecha de la fuente, 2016)",
          affiliation: null,
          affiliation_text: null,
        },
      ],
    },
    {
      name: "Hart SG",
      citations: [
        {
          ref: "nasa-tlx-1986",
          title: "NASA-TLX",
          year: null,
          organization: null,
          role: "author",
          role_text: "firma (única firma en la ficha)",
          affiliation: "KBR Inc",
          affiliation_text: "el documento la sitúa en «KBR Inc» (en la fecha de la fuente, 2020)",
        },
      ],
    },
  ],
  without_organization: [undated],
  references: 127,
};

describe("lo que decide el panel de personas", () => {
  it("un año que la ficha no da es un dato ausente, con la frase del backend; uno que da, sin marca", () => {
    expect(yearCell(null, "sin fecha en la ficha")).toEqual({ text: "sin fecha en la ficha", mark: MISSING_MARK });
    expect(yearCell("2016", "x")).toEqual({ text: "2016", mark: NO_MARK });
    expect(() => yearCell("16/09", "x")).toThrow(RangeError);
  });

  it("una cita abreviada lo dice; una ficha sin firmantes no dice «nadie»", () => {
    expect(authorsLine({ authors: ["Thiel CS", "Ullrich O"], et_al: true })).toBe("Thiel CS, Ullrich O, et al.");
    expect(authorsLine({ authors: ["Hart SG"], et_al: false })).toBe("Hart SG");
    expect(authorsLine({ authors: [], et_al: false })).toBeNull();
  });

  it("las cuentas pasan por formatNumber y concuerdan en número", () => {
    expect(countOf(1, "ficha", "fichas")).toBe("1 ficha");
    expect(countOf(1250, "ficha", "fichas")).toMatch(/^1.?250 fichas$/);
  });

  it("las claves que lee el panel son las que escribe el backend", () => {
    for (const key of [
      "note", "affiliation_rule", "same_person_rule", "named_organization_rule", "no_organization", "no_year",
      "organizations", "people", "without_organization", "references", "role_text", "et_al",
      "named_people", "evidence_type_display", "citations", "affiliations", "named_organizations", "named_by",
      "affiliation_text",
    ]) {
      expect(BACKEND).toContain(`"${key}"`);
    }
  });
});

describe("<PeopleView>", () => {
  const html = render(createElement(PeopleView, { people }));

  it("una organización por plegable, cerrado, con el sello de la procedencia y su cuenta de fichas", () => {
    expect(html.match(/<details aria-label="Organización /g)?.length).toBe(3);
    expect(html).toContain(`data-pictogram="${uiPictogram(ORGANIZATION_CONCEPT)}"`);
    const visible = textNodes(withoutFolded(html));
    expect(visible).toContain("NASA");
    expect(visible).toContain("· 1 ficha");
    // Plegado: lo que firma una ficha no está a la vista sin abrirla.
    expect(visible.join(" ")).not.toContain("Mollicone D");
  });

  it("dentro, cada ficha con su año, quién la firma y a quién nombra con su cargo literal", () => {
    expect(html).toContain("Basner M, Mollicone D, Dinges DF");
    // El papel de quien la fuente nombra lo compone el backend, el mismo en las dos vistas.
    expect(html).toContain(`<strong>Kerry Lee</strong>: ${orion.named_people[0]!.role_text}`);
    expect(html).toContain(">2016<");
  });

  it("una ficha sin organización va aparte, con el anillo cian y la frase del backend", () => {
    expect(html).toMatch(/<details aria-label="sin organización en la ficha">/);
    expect(html).toMatch(/c-cyan[^>]*>(?:<svg[^>]*data-pictogram="ring-dotted"[\s\S]*?<\/svg>)?<span>sin fecha en la ficha/);
    // Una frase no va en la letra de las cifras; un año, sí.
    expect(html).toContain('<span class="num">2016</span>');
  });

  it("la organización junto a una persona se dice como de la ficha, nunca como suya", () => {
    expect(html).toContain("organización de la ficha: NASA");
    expect(html).not.toMatch(/Kerry Lee<\/strong>[^<]*organización/);
    expect(html).toContain(people.affiliation_rule);
  });

  it("cada persona con el papel que compone el backend, tal cual", () => {
    expect(html).toContain(people.people[0]!.citations[0]!.role_text);
    expect(html).toContain("firma (única firma en la ficha)");
    expect(html).toMatch(/<details aria-label="Personas de las fichas">/);
    expect(html).toContain(`data-pictogram="${uiPictogram(PEOPLE_CONCEPT)}"`);
  });

  it("en el tablero, las tres cuentas son fichas con cifra, sin ningún nombre, y sin la frase", () => {
    const tiles = html.match(/<div class="board-stats"[\s\S]*?<\/div><\/div>/)?.[0] ?? "";
    expect(textNodes(tiles)).toEqual(["Organizaciones", "3", "Personas", String(people.people.length), "Fichas del registro", "127"]);
    expect(html).not.toContain("3 organizaciones");
  });

  it("en la clásica, las cuentas del título pasan por formatNumber", () => {
    const classic = render(createElement(LookContext.Provider, { value: "classic" }, createElement(PeopleView, { people })));
    expect(classic).toContain("3 organizaciones");
    expect(classic).toContain("127 fichas del registro");
    expect(classic).not.toContain("board-stats");
  });
});

describe("<PeopleView> con lo que nombran las fuentes", () => {
  const html = renderToStaticMarkup(createElement(PeopleView, { people }));

  it("una organización solo nombrada dice qué ficha la nombra y con qué papel, y no pinta lista vacía", () => {
    expect(html).toContain("Teledyne Brown Engineering Inc.");
    expect(html).toContain("0 fichas");
    expect(html).toContain("la nombra 1 ficha");
    expect(html).toContain("la fuente la nombra como «payload operations»");
    expect(html).toContain("nasa-mossi-ii-teledyne-2022");
  });

  it("la regla se lee y la afiliación solo sale si el documento la escribe", () => {
    expect(html).toContain(people.named_organization_rule);
    expect(html).toContain("el documento la sitúa en «KBR Inc»");
    expect(html.match(/el documento la sitúa en/g)).toHaveLength(1);
  });
});

describe("<PeoplePanel>", () => {
  it("mientras consulta: la persona en el título y la marca de cargando", () => {
    const html = render(createElement(PeoplePanel));
    expect(html).toContain(`data-pictogram="${uiPictogram(PEOPLE_CONCEPT)}"`);
    expect(html).toContain("Consultando personas y organizaciones");
  });
});
