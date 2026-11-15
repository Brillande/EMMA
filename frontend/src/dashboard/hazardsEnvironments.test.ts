import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import { resetFoldsForTests, setFoldOpen } from "../components/SecondaryFold";
import type { AlertCounts } from "../lib/alerts";
import type { CrewStatus, Framework, ProfileMatrix, ProfileMatrixCell } from "../lib/api";
import { formatMinutes } from "../lib/format";
import { adoptLevelLabels } from "../lib/levels";
import { ENVIRONMENTS_GROUP, ENV_FOLD, EnvironmentView, aspectTally, environmentSections } from "./Environments";
import { MissionProfilesView } from "../ground/MissionProfilesPanel";
import { AlertTally, CountPill, DomainLevelTally, HazardCardsView, hazardGroups, hazardLetter } from "./HazardCards";
import { aspectDisplay, aspectStyle } from "./missionProfile";

/**
 * Las tarjetas de los cinco peligros y las pestañas por entorno (§5.40): todo lo que dicen es del
 * backend; la interfaz agrupa, ordena y pinta, sin agregar un nivel ni redactar un entorno.
 */

const RIDGE: Framework["ridge"] = {
  cardiovascular: { hazard: "gravity", display: "campos gravitatorios" },
  behavioral: { hazard: "isolation", display: "aislamiento y confinamiento" },
  radiation: { hazard: "radiation", display: "radiación" },
  bone: { hazard: "gravity", display: "campos gravitatorios" },
  immune: { hazard: "environment", display: "entorno hostil y cerrado" },
  nutrition: { hazard: "distance", display: "distancia de la Tierra" },
};

const status = (oneWay: number | null): CrewStatus =>
  ({
    comms: oneWay === null ? null : { one_way_minutes: oneWay },
    domains: {
      cardiovascular: { level: "concern", score: 2, drivers: [] },
      behavioral: { level: "nominal", score: 0, drivers: [] },
      radiation: { level: "watch", score: 1, drivers: [] },
      bone: { level: "nominal", score: 0, drivers: [] },
      immune: { level: "critical", score: 3, drivers: [] },
      nutrition: { level: "nominal", score: 0, drivers: [] },
    },
  }) as unknown as CrewStatus;

describe("los cinco peligros", () => {
  it("se agrupan por peligro en el orden de la sigla, cada uno con sus dominios", () => {
    const groups = hazardGroups(RIDGE, Object.keys(status(null).domains));
    expect(groups.map((group) => group.hazard)).toEqual(["radiation", "isolation", "distance", "gravity", "environment"]);
    expect(groups.find((group) => group.hazard === "gravity")?.domains).toEqual(["cardiovascular", "bone"]);
  });

  it("un peligro que la interfaz no conoce sale al final, con su nombre del backend", () => {
    const groups = hazardGroups({ ...RIDGE, otro: { hazard: "nuevo", display: "peligro nuevo" } }, ["otro"]);
    expect(groups.at(-1)).toEqual({ hazard: "nuevo", display: "peligro nuevo", domains: ["otro"] });
  });

  it("cinco tarjetas con la insignia de cada dominio tal como la dio el backend, sin nivel agregado", () => {
    adoptLevelLabels({ nominal: "PALABRA-N", watch: "PALABRA-W", concern: "PALABRA-C", critical: "PALABRA-X" });
    const html = renderToStaticMarkup(createElement(HazardCardsView, { ridge: RIDGE, status: status(4.2) }));
    expect(html.match(/<article class="hazard"/g)).toHaveLength(5);
    for (const hazard of ["radiation", "isolation", "distance", "gravity", "environment"]) {
      expect(html).toContain(`data-pictogram="ridge-${hazard}"`);
    }
    const words = textNodes(html);
    expect(words).toContain("Campos gravitatorios");
    // Una insignia por dominio, ni una más: la tarjeta no inventa el nivel del peligro.
    expect(html.match(/class="mark level/g)).toHaveLength(6);
    expect(words.filter((word) => word.startsWith("PALABRA-"))).toEqual([
      "PALABRA-W",
      "PALABRA-N",
      "PALABRA-N",
      "PALABRA-C",
      "PALABRA-N",
      "PALABRA-X",
    ]);
    expect(html).toContain(formatMinutes(4.2));
    adoptLevelLabels(null);
  });

  it("sin efemérides, la distancia lo dice con la marca de dato ausente", () => {
    const html = renderToStaticMarkup(createElement(HazardCardsView, { ridge: RIDGE, status: status(null) }));
    expect(html).toMatch(/c-cyan"><svg[^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>Retardo con Tierra: sin efemérides/);
  });

  it("bajo la concha nueva cada tarjeta lleva su letra (adorno), un segmento por dominio en el color real de su nivel y la cuenta", () => {
    const html = renderToStaticMarkup(createElement(HazardCardsView, { ridge: RIDGE, status: status(4.2) }));
    expect(["radiation", "isolation", "distance", "gravity", "environment"].map(hazardLetter)).toEqual(["R", "I", "D", "G", "E"]);
    expect(html.match(/<span class="hazard-letter" aria-hidden="true">[RIDGE]<\/span>/g)).toHaveLength(5);
    // Un peligro que no es de la sigla no recibe una letra que no es de la sigla: sale sin ficha.
    expect(hazardLetter("nuevo")).toBeNull();
    const odd = renderToStaticMarkup(
      createElement(HazardCardsView, { ridge: { ...RIDGE, otro: { hazard: "nuevo", display: "peligro nuevo" } }, status: status(4.2) }),
    );
    expect(odd.match(/class="hazard-letter"/g)).toHaveLength(5);
    // Campos gravitatorios: cardiovascular en precaución (amarillo) y óseo nominal (el tono del texto); dos dominios.
    const gravity = html.slice(html.indexOf('aria-label="Campos gravitatorios"'), html.indexOf('aria-label="Entorno hostil y cerrado"'));
    expect(gravity).toContain('<span class="ref-segments" aria-hidden="true"><span data-tone="yellow" title="Cardiovascular"></span><span data-tone="text" title="Óseo"></span></span>');
    expect(gravity).toContain('<span class="num">2</span> dominios');
    // Inmune en crítico (rojo); un solo dominio, en singular.
    const environment = html.slice(html.indexOf('aria-label="Entorno hostil y cerrado"'));
    expect(environment).toContain('<span data-tone="red" title="Inmune"></span>');
    expect(environment).toContain('<span class="num">1</span> dominio<');
    // Sigue sin nivel agregado: las insignias son las mismas seis de antes.
    expect(html.match(/class="mark level/g)).toHaveLength(6);
  });

  it("en la concha clásica las tarjetas son las de antes: ni letra, ni segmentos, ni cuenta", () => {
    const html = renderToStaticMarkup(
      createElement(LookContext.Provider, { value: "classic" }, createElement(HazardCardsView, { ridge: RIDGE, status: status(4.2) })),
    );
    expect(html).not.toContain("hazard-letter");
    expect(html).not.toContain("ref-segments");
    expect(html).not.toContain("dominios");
    expect(html.match(/class="mark level/g)).toHaveLength(6);
  });
});

describe("los recuentos del tablero de «Peligros y alertas»", () => {
  it("el resumen cuenta los dominios por nivel: con alguno, el color real; a cero, sin color; lo desconocido, «sin nivel»", () => {
    adoptLevelLabels({ nominal: "PALABRA-N", watch: "PALABRA-W", concern: "PALABRA-C", critical: "PALABRA-X" });
    const html = renderToStaticMarkup(createElement(DomainLevelTally, { domains: { ...status(null).domains, raro: { level: "elevated", score: 1, drivers: [] } } as never }));
    expect(html).toContain('role="group" aria-label="Dominios por nivel"');
    // Tres nominales (texto), un vigilancia (azul), un precaución (amarillo), un crítico (rojo): la píldora teñida.
    expect(html).toMatch(/style="--lvl:var\(--c-text\)"><span class="mark level c-text"><svg[^>]*data-pictogram="shape-circle"[^>]*>.*?<\/svg>PALABRA-N<\/span><span class="num">3<\/span>/);
    expect(html).toMatch(/style="--lvl:var\(--c-blue\)"><span class="mark level c-blue">.*?PALABRA-W<\/span><span class="num">1<\/span>/);
    expect(html).toMatch(/style="--lvl:var\(--c-red\)"><span class="mark level c-red">.*?PALABRA-X<\/span><span class="num">1<\/span>/);
    // El desconocido no entra en ninguna píldora de nivel y tiene la suya; los segmentos lo llevan en gris.
    expect(html).toMatch(/<span class="ref-pill board-pill secondary"><span class="mark"><svg[^>]*data-pictogram="dot-small"[^>]*>.*?<\/svg>sin nivel <span class="num">1<\/span><\/span><\/span>/);
    expect(html).toContain('<span data-tone="gray" title="raro"></span>');
    expect(html).toContain('<span class="num">7</span> dominios');
    // A cero (sin precaución en esta muestra): la forma y la palabra en secundario, sin clase de color.
    const none = renderToStaticMarkup(createElement(DomainLevelTally, { domains: { bone: { level: "nominal", score: 0, drivers: [] } } as never }));
    expect(none).toMatch(/<span class="ref-pill board-pill secondary"><span class="mark level"><svg[^>]*data-pictogram="shape-square"[^>]*>.*?<\/svg>PALABRA-X<\/span><span class="num">0<\/span><\/span>/);
    expect(none).not.toMatch(/c-(red|yellow|blue)/);
    expect(none).not.toContain("sin nivel");
    adoptLevelLabels(null);
  });

  it("las alertas: las tres clases de F.6.4 de más a menos grave, lo sin reconocer y lo silenciado solo si lo hay", () => {
    adoptLevelLabels({ nominal: "PALABRA-N", watch: "PALABRA-W", concern: "PALABRA-C", critical: "PALABRA-X" });
    const counts: AlertCounts = { warning: 0, caution: 2, advisory: 1, unacknowledged: 1, suppressed: 0, inhibited: 1 };
    const html = renderToStaticMarkup(createElement(AlertTally, { counts }));
    const words = textNodes(html).filter((word) => word.startsWith("PALABRA-"));
    expect(words).toEqual(["PALABRA-X", "PALABRA-C", "PALABRA-W"]);
    expect(html).not.toContain("PALABRA-N");
    expect(html).toMatch(/board-pill secondary"><span class="mark level"><svg[^>]*data-pictogram="shape-square".*?PALABRA-X<\/span><span class="num">0<\/span>/);
    expect(html).toMatch(/style="--lvl:var\(--c-yellow\)"><span class="mark level c-yellow">.*?PALABRA-C<\/span><span class="num">2<\/span>/);
    expect(html).toMatch(/data-pictogram="box-empty"[^>]*>.*?<\/svg>sin reconocer <span class="num">1<\/span>/);
    expect(html).toMatch(/data-pictogram="bell-box"[^>]*>.*?<\/svg>inhibidas <span class="num">1<\/span>/);
    expect(html).not.toContain("suprimidas");
    adoptLevelLabels(null);
  });

  it("la píldora neutra de recuento concuerda la palabra con la cifra", () => {
    expect(renderToStaticMarkup(createElement(CountPill, { pictogram: "signpost", count: 1, one: "recomendación", many: "recomendaciones" }))).toContain(
      '<span class="num">1</span> recomendación</span>',
    );
    expect(renderToStaticMarkup(createElement(CountPill, { pictogram: "signpost", count: 0, one: "recomendación", many: "recomendaciones" }))).toContain(
      '<span class="num">0</span> recomendaciones</span>',
    );
  });
});

const cell = (over: Partial<ProfileMatrixCell> = {}): ProfileMatrixCell => ({
  key: "comm_delay",
  label: "rotulo",
  status: "read",
  status_text: "leido",
  statement: "frase del backend",
  citations: [],
  discrepancy: null,
  searched: null,
  emma_note: null,
  text: "frase del backend",
  reused_from: [],
  ...over,
});

const matrix: ProfileMatrix = {
  note: "NOTA-MATRIZ",
  declared_id: "mars-transit",
  declared_note: "NOTA-DECLARADO",
  declared_text: null,
  no_source: "sin fuente segun el backend",
  aspects: [
    { key: "comm_delay", label: "RETARDO", reused_only: false },
    { key: "medical_capability", label: "CAPACIDAD", reused_only: true },
  ],
  profiles: [
    {
      id: "leo",
      display: "ORBITA-BAJA",
      declared: false,
      cells: [cell({ text: "RETARDO-LEO" }), cell({ key: "medical_capability", text: "CAPACIDAD-LEO" })],
    },
    // Un perfil que la interfaz no conoce: llega solo por venir del backend.
    {
      id: "rover-base",
      display: "CISLUNAR",
      declared: false,
      cells: [
        cell({ text: "RETARDO-CISLUNAR" }),
        cell({
          key: "medical_capability",
          status: "unverified",
          statement: null,
          status_text: "sin fuente",
          text: "sin fuente segun el backend",
        }),
      ],
    },
    {
      id: "mars-transit",
      display: "MARTE",
      declared: true,
      cells: [cell({ text: "RETARDO-MARTE" })],
    },
  ],
  reused_note: "NOTA-REUTILIZADA",
  medical_note: "NOTA-MEDICA",
  pages_read: [{ title: "Pagina", url: null, read_on: ["2026-10-13"] }],
};

describe("una pestaña por entorno", () => {
  it("las pestañas salen de los perfiles del backend, en su orden, en el grupo «Entornos»", () => {
    const sections = environmentSections({ matrix, failure: null });
    expect(sections.map((section) => section.key)).toEqual(["env-leo", "env-rover-base", "env-mars-transit"]);
    expect(sections.map((section) => section.label)).toEqual(["ORBITA-BAJA", "CISLUNAR", "MARTE"]);
    expect(sections.every((section) => section.group === ENVIRONMENTS_GROUP)).toBe(true);
    // El que la interfaz no conoce lleva el dibujo de «desconocido», no uno supuesto.
    expect(sections[1]?.pictogram).toBe("dot-small");
  });

  it("el entorno declarado se marca en su pestaña con el anillo de elegido", () => {
    const sections = environmentSections({ matrix, failure: null });
    const note = (index: number) => {
      const value = sections[index]?.note;
      return value === undefined ? "" : renderToStaticMarkup(createElement("span", null, value));
    };
    expect(note(2)).toMatch(/data-pictogram="ring-dot"[^>]*>.*?<\/svg>Perfil declarado/);
    expect(note(0)).toBe("");
  });

  it("cada pestaña enseña su columna, aspecto a aspecto, y lo sin fuente tal cual en cian", () => {
    // Las notas de la matriz van bajo la raya de lo secundario: aquí, desplegada.
    setFoldOpen(ENV_FOLD, true);
    const html = renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId: "rover-base" }));
    resetFoldsForTests();
    const words = textNodes(html);
    for (const word of ["CISLUNAR", "RETARDO", "CAPACIDAD", "RETARDO-CISLUNAR", "NOTA-MATRIZ", "NOTA-DECLARADO", "NOTA-MEDICA"]) {
      expect(words).toContain(word);
    }
    expect(html).not.toContain("RETARDO-LEO");
    expect(html).toMatch(/c-cyan"><svg[^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>sin fuente segun el backend/);
  });

  it("un estado de aspecto desconocido no tumba la pestaña: «no disponible» en gris, con el estado tal cual", () => {
    const odd: ProfileMatrix = {
      ...matrix,
      profiles: [
        {
          id: "leo",
          display: "ORBITA-BAJA",
          declared: false,
          cells: [
            cell({ status: "proven" as never, statement: null, text: "FRASE-RARA" }),
            cell({ key: "medical_capability", text: "CAPACIDAD-LEO" }),
          ],
        },
      ],
    };
    // El contrato de `aspectStyle` no cambia: sigue fallando ante un estado que no conoce.
    expect(() => aspectStyle("proven")).toThrow(RangeError);
    for (const view of [
      createElement(EnvironmentView, { matrix: odd, profileId: "leo" }),
      createElement(MissionProfilesView, { matrix: odd }),
    ]) {
      const html = renderToStaticMarkup(view);
      expect(html).toMatch(/c-gray"><svg[^>]*data-pictogram="slash-circle"[^>]*>.*?<\/svg>FRASE-RARA/);
      expect(textNodes(html).join(" ")).toContain("«proven»");
      // El resto de la columna sigue ahí.
      expect(textNodes(html)).toContain("CAPACIDAD-LEO");
    }
    // Ni un estado que coincide con una propiedad heredada de los objetos pasa por conocido.
    expect(aspectDisplay("toString").known).toBe(false);
    expect(aspectDisplay("unverified")).toEqual({ mark: aspectStyle("unverified"), known: true });
  });

  it("bajo la concha nueva, el anillo de aspectos leídos, una píldora por estado con su palabra y las páginas leídas", () => {
    const html = renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId: "rover-base" }));
    expect(html).toContain('aria-label="1 de 2 aspectos leídos en una fuente"');
    expect(html).toMatch(/c-cyan"><svg[^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>sin fuente<\/span> <span class="num">1<\/span>/);
    expect(html).toMatch(/Páginas leídas<\/span><span class="stat-value"><span class="num">1<\/span>/);
    // Un aspecto sin casilla no cuenta como leído; el total es el de la matriz.
    expect(aspectTally(matrix, "mars-transit")).toMatchObject({ read: 1, total: 2 });
    // En la clásica, nada de esto.
    const classic = renderToStaticMarkup(
      createElement(LookContext.Provider, { value: "classic" }, createElement(EnvironmentView, { matrix, profileId: "rover-base" })),
    );
    expect(classic).not.toContain("ref-ring");
    expect(classic).not.toContain("environment-board");
  });

  it("bajo la concha nueva, cada aspecto es un mosaico: su estado con su marca a la vista y lo leído detrás de «Ver detalle»", () => {
    const html = renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId: "rover-base" }));
    // El estado de cada aspecto, fuera de toda región cerrada: el cian de «sin fuente» no se pliega.
    // Cada región cerrada acaba con su aspecto (`</dd>`) o con el panel (`</section>`).
    const visible = html.replace(/class="board-detail-body" hidden="">[\s\S]*?(?=<\/dd>|<\/section>)/g, "");
    expect(visible).toMatch(/environment-aspect-state"><span class="mark c-cyan"><svg[^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>sin fuente<\/span>/);
    expect(visible).toContain('environment-aspect-state"><span class="mark">leido</span>');
    expect(visible).not.toContain("RETARDO-CISLUNAR");
    expect(visible).not.toContain("NOTA-DECLARADO");
    // La nota de alcance de la matriz («descriptivo…») sigue a la vista.
    expect(visible).toContain("NOTA-MATRIZ");
    // Plegado, pero en el DOM, con su mando por aspecto.
    expect(html).toContain("RETARDO-CISLUNAR");
    expect(html).toContain("Ver detalle: RETARDO");
    // Un aspecto sin casilla dice «no disponible» en gris; una discrepancia se anuncia en el mosaico.
    expect(renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId: "mars-transit" }))).toMatch(
      /environment-aspect-state"><span class="mark c-gray"><svg[^>]*data-pictogram="slash-circle"[^>]*>.*?<\/svg>no disponible/,
    );
    const contested: ProfileMatrix = {
      ...matrix,
      profiles: [{ id: "leo", display: "ORBITA-BAJA", declared: false, cells: [cell({ discrepancy: { text: "OTRA-CIFRA", citations: [] } })] }],
    };
    const contestedHtml = renderToStaticMarkup(createElement(EnvironmentView, { matrix: contested, profileId: "leo" }));
    expect(contestedHtml).toContain("otra fuente discrepa");
    expect(contestedHtml).toContain("OTRA-CIFRA");
    // «Perfil declarado» sigue fuera de todo pliegue.
    const declared = renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId: "mars-transit" }));
    expect(declared.indexOf("Perfil declarado")).toBeLessThan(declared.indexOf("board-detail"));
    // En la clásica, la columna como antes: sin mosaico ni mandos, la nota arriba.
    const classic = renderToStaticMarkup(
      createElement(LookContext.Provider, { value: "classic" }, createElement(EnvironmentView, { matrix, profileId: "rover-base" })),
    );
    expect(classic).not.toContain("board-detail");
    expect(classic).not.toContain("environment-aspect-state");
    expect(classic.indexOf("NOTA-MATRIZ")).toBeLessThan(classic.indexOf("environment-aspects"));
  });

  it("las notas de la matriz y las páginas leídas, bajo la raya de lo secundario, plegada de partida", () => {
    resetFoldsForTests();
    for (const look of ["reference", "classic"] as const) {
      const folded = renderToStaticMarkup(
        createElement(LookContext.Provider, { value: look }, createElement(EnvironmentView, { matrix, profileId: "mars-transit" })),
      );
      expect(folded).toContain('class="ref-divider" data-open="false"');
      expect(folded).toContain("Notas de la matriz y páginas leídas");
      for (const word of ["NOTA-DECLARADO", "NOTA-REUTILIZADA", "NOTA-MEDICA", "Pagina"]) expect(folded).not.toContain(word);
      // Lo de arriba no se pliega: la nota de alcance, «Perfil declarado» y el estado de los aspectos.
      expect(folded).toContain("NOTA-MATRIZ");
      expect(folded).toContain("Perfil declarado");
      expect(folded.indexOf("environment-aspects")).toBeLessThan(folded.indexOf("ref-divider"));
    }
    // Una sola raya para todos los entornos: desplegarla en uno la despliega en los demás.
    setFoldOpen(ENV_FOLD, true);
    for (const profileId of ["leo", "rover-base", "mars-transit"]) {
      const open = renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId }));
      expect(open).toContain('data-open="true"');
      for (const word of ["NOTA-DECLARADO", "NOTA-REUTILIZADA", "NOTA-MEDICA", "Pagina"]) expect(open).toContain(word);
    }
    resetFoldsForTests();
  });

  it("a bordo, un entorno que no es el declarado ofrece declararlo; el declarado y Tierra, no", () => {
    const declare = async () => {};
    const offered = renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId: "leo", declare }));
    expect(offered).toContain('data-ui="environment-declare"');
    expect(offered).toMatch(/data-pictogram="pen"[^>]*>.*?<\/svg>Declarar como entorno de la misión/);
    const current = renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId: "mars-transit", declare }));
    expect(current).not.toContain("environment-declare");
    const ground = renderToStaticMarkup(createElement(EnvironmentView, { matrix, profileId: "leo" }));
    expect(ground).not.toContain("environment-declare");
    // Por las pestañas: con el mando, solo en las de los no declarados.
    const panels = environmentSections({ matrix, failure: null }, declare).map((section) =>
      renderToStaticMarkup(createElement("div", null, ...(section.panels as never[]))),
    );
    expect(panels.map((html) => html.includes("environment-declare"))).toEqual([true, true, false]);
  });

  it("mientras llega la matriz, una sola pestaña que lo dice; si falla, el motivo", () => {
    const loading = environmentSections({ matrix: null, failure: null });
    expect(loading.map((section) => section.key)).toEqual(["env"]);
    const failed = environmentSections({
      matrix: null,
      failure: { mark: { pictogram: "cross", color: "red", className: "c-red" }, text: "MOTIVO" } as never,
    });
    const html = renderToStaticMarkup(createElement("div", null, ...(failed[0]?.panels ?? []) as never[]));
    expect(html).toContain("Perfiles de misión no disponibles: MOTIVO");
  });

  it("ningún entorno se escribe en la interfaz: ni nombres de perfil ni sus peculiaridades", () => {
    const source = readFileSync(fileURLToPath(new URL("./Environments.tsx", import.meta.url)), "utf8").replace(
      /\/\*[\s\S]*?\*\/|\/\/.*$/gm,
      "",
    );
    expect(source).not.toMatch(/magnetosfera|cislunar|Marte|Luna|órbita baja/i);
  });
});
