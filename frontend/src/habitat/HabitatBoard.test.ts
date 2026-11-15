import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewOverview, HabitatExcursion, HabitatReading } from "../lib/api";
import { HabitatBoard } from "./HabitatPanel";

/*
 * Lo que el hábitat enseña de un vistazo en el tablero: las píldoras de hipótesis, excursiones fuera
 * del límite normativo y tripulantes por nivel (solo cifras, nunca quién), y las últimas lecturas de
 * cabina como baldosas con la unidad de su ficha. Nada que no dé ya el panel, y nada si no hay nada.
 */
const reading = (parameter: string, value: number, module = "hab"): HabitatReading => ({
  module,
  parameter,
  value,
  unit: "UNIDAD-DE-LECTURA",
  effective: "2026-11-08T00:00:00+00:00",
  source: "simulado",
  evidence_context: "",
});

const excursion: HabitatExcursion = {
  module: "hab",
  parameter: "co2",
  display: "CO2",
  unit: "mmHg",
  kind: "health",
  requirement: "REQUISITO-X",
  start: "2026-11-07T00:00:00+00:00",
  end: "2026-11-08T00:00:00+00:00",
  worst: 6,
};

const member = (subject: string, level: string) =>
  ({ subject, overall_level: level }) as unknown as CrewOverview["crew"][number];

const crew = {
  crew: [
    member("crew-01", "watch"),
    member("crew-02", "watch"),
    member("crew-03", "nominal"),
  ],
  correlation: { hypotheses: [{}, {}] },
} as unknown as CrewOverview;

const render = (props: Partial<Parameters<typeof HabitatBoard>[0]> = {}) =>
  renderToStaticMarkup(
    createElement(HabitatBoard, {
      habitat: { active: [], excursions: [] },
      crew: null,
      specs: [{ key: "co2", display: "NOMBRE-CO2", unit: "mm[Hg]" }],
      cabinLatest: [],
      measured: [],
      moduleName: (key: string) => `MODULO-${key}`,
      ...props,
    }),
  );

describe("<HabitatBoard>", () => {
  it("sin nada que contar no pinta nada", () => {
    expect(render()).toBe("");
  });

  it("las píldoras cuentan hipótesis, excursiones y tripulantes por nivel, sin nombrar a nadie", () => {
    const closed = { ...excursion, kind: "performance" as const };
    const html = render({ crew, habitat: { active: [], excursions: [excursion, closed] } });
    expect(html).toContain('Hipótesis del sistema</span> <span class="num">2</span>');
    // Solo las del límite normativo, vigentes o cerradas: las de confort no cuentan aquí.
    expect(html).toContain('salidas del límite en la ventana</span> <span class="num">1</span>');
    // Una píldora por nivel presente, con su cifra.
    expect(html.match(/class="ref-pill board-pill" style=/g)).toHaveLength(2);
    expect(html).not.toContain("crew-01");
  });

  it("una baldosa por lectura con ficha; la que no tiene ficha no se inventa", () => {
    const html = render({ cabinLatest: [reading("co2", 4.8), reading("desconocido", 1)], measured: ["hab"] });
    expect(html).toContain("NOMBRE-CO2");
    expect(html.match(/class="stat-tile"/g)).toHaveLength(1);
    expect(html).not.toContain("UNIDAD-DE-LECTURA");
  });

  it("un parámetro con ficha sin lectura en un módulo medido lleva su baldosa «sin dato» en cian, como su fila", () => {
    const specs = [
      { key: "co2", display: "PRIMERO", unit: "mm[Hg]" },
      { key: "o2", display: "SEGUNDO", unit: "mm[Hg]" },
    ];
    const html = render({ specs, cabinLatest: [reading("co2", 4)], measured: ["hab"] });
    expect(html.match(/class="stat-tile"/g)).toHaveLength(2);
    expect(html).toMatch(/SEGUNDO[^]*?<span class="mark c-cyan"[^>]*>[^]*?sin dato<\/span>/);
    // Sin módulos medidos no hay huecos que contar: la tabla dice «Sin telemetría de cabina».
    expect(render({ specs })).toBe("");
  });

  it("una excursión vigente lleva su marca y su requisito en la baldosa; con varios módulos, el módulo", () => {
    const html = render({
      habitat: { active: [excursion], excursions: [excursion] },
      cabinLatest: [reading("co2", 6), reading("co2", 3, "otro")],
      measured: ["hab", "otro"],
    });
    expect(html).toContain("fuera de REQUISITO-X");
    expect(html.match(/fuera de REQUISITO-X/g)).toHaveLength(1);
    expect(html).toContain("MODULO-otro");
  });

  it("el aviso de confort que acaba en la lectura lleva su rombo y su palabra, como su fila", () => {
    const comfort = { ...excursion, kind: "performance" as const, end: "2026-11-08T00:00:00+00:00" };
    const html = render({ habitat: { active: [], excursions: [comfort] }, cabinLatest: [reading("co2", 6)], measured: ["hab"] });
    expect(html).toMatch(/<span class="mark c-blue"[^>]*>[^]*?fuera de la zona de confort REQUISITO-X<\/span>/);
  });

  it("las baldosas van en el orden de la tabla: módulo a módulo y el catálogo dentro", () => {
    const specs = [
      { key: "co2", display: "PRIMERO", unit: "mm[Hg]" },
      { key: "o2", display: "SEGUNDO", unit: "mm[Hg]" },
    ];
    const html = render({ specs, cabinLatest: [reading("o2", 150), reading("co2", 4)], measured: ["hab"] });
    expect(html.indexOf("PRIMERO")).toBeLessThan(html.indexOf("SEGUNDO"));
  });
});
