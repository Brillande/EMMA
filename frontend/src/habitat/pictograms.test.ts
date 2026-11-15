import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textLines, textNodes } from "../advisor/visibleText";
import { isPictogramName } from "../icons/registry";
import type { HabitatDisplayOnly, HabitatExcursion, HabitatParameter, HabitatSystems } from "../lib/api";
import { MISSING_MARK, REFUSED_MARK, UNKNOWN_MARK } from "../lib/marks";
import { DisplayOnlyRow, HabitatRow, HypothesisPlaceLine } from "./HabitatPanel";
import { HypothesisReview } from "./HypothesisReview";
import { SystemEntry } from "./SystemsStatus";
import {
  CABIN_AIR_PICTOGRAM,
  FLOW_STEPS_PICTOGRAM,
  GROUP_PICTOGRAMS,
  MODULE_PICTOGRAMS,
  PARAMETER_PICTOGRAMS,
  SYSTEM_PICTOGRAMS,
  hypothesisKindMark,
  hypothesisMark,
  modulePictogram,
  parameterPictogram,
  groupPictogram,
  presenceMark,
  systemPictogram,
} from "./pictograms";
import { systemRows } from "./systems";

/**
 * Los pictogramas del habitat (`compliance/hmi-state-of-the-art.md` §5.32.4), como prueba.
 *
 * Paridad con el backend: cada parametro de cabina de `environment/habitat.py`, cada modulo de
 * `habitat_modules.json` y cada sistema de `habitat_systems.json` tienen dibujo, y ninguno
 * repite el de otro de su misma lista (salvo la luz, que es el mismo significado para el
 * parametro y para el sistema). Y pintado a HTML estatico: el pictograma va junto a la palabra
 * del backend, con el color solo donde ya iba, y sin que el texto visible cambie.
 */

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf-8");
const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

const BACKEND = "../../../backend/app/";

/**
 * Las claves de cabina que el backend evalua o ensena (`PARAMETERS`, con `key="…"`, y
 * `DISPLAY_ONLY`, cuya clave es el primer argumento de `_display_only(`). Es una lectura del
 * fuente: la paridad de verdad, con los objetos de Python, la hace el backend en
 * `tests/test_habitat_pictograms.py`; aqui solo se comprueba que esta tabla no la contradice.
 */
const CABIN_KEYS = [
  ...new Set(
    [
      ...read(`${BACKEND}environment/habitat.py`).matchAll(
        /(?:\bkey\s*=\s*|_display_only\(\s*)"((?:cabin|water|air|surface)-[a-z0-9-]+)"/g,
      ),
    ].flatMap((m) => (m[1] === undefined ? [] : [m[1]])),
  ),
];
const MODULES = (JSON.parse(read(`${BACKEND}data/habitat_modules.json`)) as { modules: { key: string }[] }).modules;
const SYSTEMS = (JSON.parse(read(`${BACKEND}data/habitat_systems.json`)) as { systems: { key: string }[] }).systems;

describe("paridad con el backend", () => {
  it("cada parametro de cabina tiene su dibujo, y todos distintos", () => {
    expect(CABIN_KEYS.length).toBeGreaterThanOrEqual(10);
    for (const key of CABIN_KEYS) {
      expect(PARAMETER_PICTOGRAMS[key], key).toBeDefined();
      expect(parameterPictogram(key), key).not.toBe(UNKNOWN_MARK.pictogram);
    }
    expect(Object.keys(PARAMETER_PICTOGRAMS).sort()).toEqual([...CABIN_KEYS].sort());
    expect(new Set(Object.values(PARAMETER_PICTOGRAMS)).size).toBe(CABIN_KEYS.length);
  });

  it("cada modulo declarado tiene su dibujo, y todos distintos", () => {
    expect(Object.keys(MODULE_PICTOGRAMS).sort()).toEqual(MODULES.map((item) => item.key).sort());
    expect(new Set(Object.values(MODULE_PICTOGRAMS)).size).toBe(MODULES.length);
  });

  it("cada sistema del vocabulario tiene su dibujo; solo la luz comparte el de su parametro", () => {
    expect(Object.keys(SYSTEM_PICTOGRAMS).sort()).toEqual(SYSTEMS.map((item) => item.key).sort());
    expect(new Set(Object.values(SYSTEM_PICTOGRAMS)).size).toBe(SYSTEMS.length);
    expect(systemPictogram("lighting")).toBe(parameterPictogram("cabin-light"));
    const shared = Object.values(SYSTEM_PICTOGRAMS).filter((name) =>
      Object.values(PARAMETER_PICTOGRAMS).includes(name),
    );
    expect(shared).toEqual(["bulb"]);
  });

  it("cada bloque de lecturas del hábitat tiene su dibujo: el agua, el grifo de su sistema", () => {
    // Los grupos de `environment/habitat.py` (`CABIN, WATER, MICROBIOLOGY = "cabin", ...`).
    const groups = read(`${BACKEND}environment/habitat.py`).match(
      /^CABIN, WATER, MICROBIOLOGY = "([a-z]+)", "([a-z]+)", "([a-z]+)"$/m,
    );
    expect(groups).not.toBeNull();
    expect(Object.keys(GROUP_PICTOGRAMS).sort()).toEqual([...(groups ?? []).slice(1)].sort());
    expect(groupPictogram("cabin")).toBe(CABIN_AIR_PICTOGRAM);
    expect(groupPictogram("water")).toBe(systemPictogram("water"));
    expect(groupPictogram("microbiology")).toBe("petri-dish");
    expect(groupPictogram("kitchen")).toBe(UNKNOWN_MARK.pictogram);
    // Ningún bloque se dibuja como uno de sus parámetros.
    for (const name of Object.values(GROUP_PICTOGRAMS)) {
      expect(Object.values(PARAMETER_PICTOGRAMS)).not.toContain(name);
    }
  });

  it("todo dibujo nombrado existe en el registro", () => {
    for (const name of [
      ...Object.values(PARAMETER_PICTOGRAMS),
      ...Object.values(MODULE_PICTOGRAMS),
      ...Object.values(SYSTEM_PICTOGRAMS),
      ...Object.values(GROUP_PICTOGRAMS),
    ]) {
      expect(isPictogramName(name), name).toBe(true);
    }
  });

  it("una clave que la interfaz no conoce se enseña con el punto, sin fallar ni disfrazarse", () => {
    expect(parameterPictogram("cabin-radon")).toBe(UNKNOWN_MARK.pictogram);
    expect(modulePictogram("invernadero")).toBe(UNKNOWN_MARK.pictogram);
    expect(systemPictogram("propulsion")).toBe(UNKNOWN_MARK.pictogram);
    expect(hypothesisKindMark("otra")).toEqual(UNKNOWN_MARK);
  });
});

describe("clase de hipotesis y ubicacion de cada tripulante", () => {
  it("las tres clases del backend llevan figura distinta y ningun color: una hipotesis no es una alerta", () => {
    const kinds = ["individual", "shared_unknown", "shared_environment"];
    const marks = kinds.map(hypothesisKindMark);
    expect(marks.map((mark) => mark.pictogram)).toEqual(["stick-figure", "stick-figures-two", "stick-figures-roof"]);
    for (const mark of marks) expect(mark.color).toBeNull();
  });

  it("sin ubicacion declarada es un dato ausente (cian, anillo punteado); las otras dos, sin color", () => {
    expect(MISSING_MARK).toEqual({ pictogram: "ring-dotted", color: "cyan", className: "c-cyan" });
    expect(presenceMark("undeclared")).toBe(MISSING_MARK);
    expect(presenceMark("present")).toEqual({ pictogram: "pin", color: null, className: undefined });
    expect(presenceMark("elsewhere")).toEqual({ pictogram: "pin-arrow", color: null, className: undefined });
  });
});

const ppco2: HabitatParameter = {
  key: "cabin-ppco2",
  display: "CO2 de cabina (presión parcial)",
  unit: "mm[Hg]",
  limits: [{ low: null, high: 3, requirement: "[V2 6004]", kind: "health", averaging_minutes: 60 }],
  averaging_minutes: 60,
  source: { id: "ochmo-tb-002", title: "OCHMO-TB-002", url: "https://www.nasa.gov/", read_on: "2026-10-21" },
};

const excursion = (kind: HabitatExcursion["kind"], requirement: string): HabitatExcursion => ({
  module: "habitat-principal",
  parameter: "cabin-ppco2",
  display: ppco2.display,
  unit: ppco2.unit,
  kind,
  requirement,
  start: "2026-11-10T00:00:00+00:00",
  end: "2026-11-10T02:00:00+00:00",
  worst: 5.3,
});

const row = (value: number | null, active: HabitatExcursion | null = null, comfort: HabitatExcursion | null = null) =>
  render(createElement("dl", null, createElement(HabitatRow, { spec: ppco2, value, active, comfort })));

describe("la tabla de atmosfera, pintada", () => {
  it("el parametro lleva su pictograma junto a su nombre, sin color", () => {
    const html = row(2.1);
    expect(html).toMatch(/<dt><span class="mark"><svg[^>]*data-pictogram="atoms-three"[^>]*>.*?<\/svg>CO2 de cabina \(presión parcial\)<\/span><\/dt>/);
  });

  it("sin lectura: anillo punteado en cian y la palabra «sin dato»", () => {
    const html = row(null);
    expect(html).toMatch(/<span class="mark c-cyan"><svg[^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>sin dato<\/span>/);
    expect(html).not.toContain("◌");
  });

  it("fuera del limite normativo: triangulo amarillo con el requisito; fuera del confort u objetivo: rombo azul", () => {
    const health = row(5.3, excursion("health", "[V2 6004]"));
    expect(health).toMatch(/<span class="mark c-yellow"><svg[^>]*data-pictogram="shape-triangle"[^>]*>.*?<\/svg>fuera de \[V2 6004\]<\/span>/);
    expect(health).not.toContain("△");
    const target = row(2.1, null, excursion("target", "[V2 6003] rango objetivo"));
    expect(target).toMatch(/<span class="mark c-blue"><svg[^>]*data-pictogram="shape-diamond"[^>]*>.*?<\/svg>fuera de \[V2 6003\] rango objetivo<\/span>/);
    const comfort = row(2.1, null, excursion("performance", "[V2 6013]"));
    expect(comfort).toContain("fuera de la zona de confort [V2 6013]");
    expect(comfort).toContain('data-pictogram="shape-diamond"');
    expect(comfort).not.toContain("◇");
  });

  it("el texto visible es el de antes: el pictograma no añade ni quita palabras", () => {
    expect(textNodes(row(5.3, excursion("health", "[V2 6004]")))).toEqual([
      "CO2 de cabina (presión parcial)",
      "5,3",
      "mmHg",
      "fuera de [V2 6004]",
    ]);
    expect(textLines(row(5.3, excursion("health", "[V2 6004]")))).toEqual([
      "CO2 de cabina (presión parcial)",
      "5,3 mmHg fuera de [V2 6004]",
    ]);
  });

  it("la luz: bombilla junto al nombre y ningun color ni forma de aviso (sin semaforo)", () => {
    const light: HabitatDisplayOnly = {
      key: "cabin-light",
      display: "Iluminación de cabina (iluminancia)",
      unit: "lx",
      limits: [],
      averaging_minutes: null,
      source: null,
      limit_note: "Sin límite general: la norma fija niveles por tarea.",
    };
    const html = render(createElement("dl", null, createElement(DisplayOnlyRow, { spec: light, value: 300 })));
    expect(html).toContain('data-pictogram="bulb"');
    expect(html).toContain("Iluminación de cabina (iluminancia)");
    expect(html).not.toMatch(/c-(yellow|blue|red)|shape-triangle|shape-diamond/);
    const missing = render(createElement("dl", null, createElement(DisplayOnlyRow, { spec: light, value: null })));
    expect(missing).toMatch(/<span class="mark c-cyan"><svg[^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>sin dato<\/span>/);
  });
});

describe("el agua y la microbiologia, pintadas", () => {
  it("un requisito sin cifra se lista sin cifra, y ninguno lleva color ni forma de aviso", () => {
    const microbial: HabitatDisplayOnly = {
      key: "air-microbial",
      display: "Bacterias cultivables del aire de cabina",
      unit: "{CFU}/m3",
      group: "microbiology",
      limits: [],
      averaging_minutes: null,
      source: null,
      limit_note: "Sin límite leído: la norma no da cifra. La lectura se muestra y no se evalúa.",
      reference_label: "requisito sin cifra: la norma no da un nivel admisible",
      reference_source: { id: "nasa-std-3001-vol2-rev-f", title: "NASA-STD-3001 Vol 2 Rev F", read_on: "2026-10-22" },
      reference_requirements: [
        {
          requirement: "[V2 6059]",
          table: "sección 6.2.8.5",
          label: "Aire microbiológicamente seguro",
          low: null,
          high: null,
          stated: null,
          unit: "{CFU}/m3",
          condition: "la norma no da cifra",
          same_quantity: true,
          source_row: "The system shall provide air ...",
          evaluated: false,
        },
      ],
    };
    const html = render(createElement("dl", null, createElement(DisplayOnlyRow, { spec: microbial, value: 120 })));
    expect(html).toContain('data-pictogram="wind-dots"');
    expect(html).toContain('<span class="num">120</span> UFC/m³');
    expect(html).toContain("Aire microbiológicamente seguro: ([V2 6059], sección 6.2.8.5)");
    expect(html).not.toContain('<span class="num"></span>');
    expect(html).not.toMatch(/c-(yellow|blue|red)|shape-triangle|shape-diamond/);
  });
});

describe("la revision de una hipotesis, pintada", () => {
  const hypothesis = (decision: "confirmed" | "discarded") => ({
    kind: "shared_environment" as const,
    label: "correlación, no causa",
    title: "Contexto ambiental compartido",
    affected: ["crew-01", "crew-02"],
    excursion: excursion("health", "[V2 6004]"),
    what_is_known: null,
    checks: [],
    evidence: [],
    steps: [],
    review: { decision, reason: "segundo sensor de acuerdo", decided_by: "CDR", ledger_index: 12 },
  });

  // Descartada llevaba el aspa; desde §5.33.4 lleva el circulo tachado de «Descartar»
  // (`reject`), como «Confirmada» lleva el visto de «Confirmar»: un concepto, un dibujo.
  it("confirmada con el visto de confirmar, descartada con el circulo tachado de descartar; sin color, y sin glifo de texto", () => {
    const confirmed = render(createElement(HypothesisReview, { hypothesis: hypothesis("confirmed"), operator: undefined, onReviewed: () => {} }));
    expect(confirmed).toMatch(/<span class="mark"><svg[^>]*data-pictogram="check"[^>]*>.*?<\/svg>Confirmada<\/span>/);
    expect(confirmed).not.toMatch(/c-(yellow|blue|red|cyan|gray)/);
    expect(confirmed).not.toContain("✓");
    const discarded = render(createElement(HypothesisReview, { hypothesis: hypothesis("discarded"), operator: undefined, onReviewed: () => {} }));
    expect(discarded).toMatch(/<span class="mark"><svg[^>]*data-pictogram="slash-circle"[^>]*>.*?<\/svg>Descartada<\/span>/);
    expect(discarded).not.toMatch(/c-(yellow|blue|red|cyan|gray)/);
    expect(discarded).not.toContain("✗");
    expect(textNodes(confirmed).join(" ")).toBe("Confirmada por CDR: segundo sensor de acuerdo");
  });

  // §5.34.4: un sistema de soporte vital declarado degradado entra como coincidencia en el
  // tiempo. No se confirma ni se descarta: se ensena lo que una persona ya firmo, tal cual.
  const statement =
    "Declarado «degradado» desde 10,0 h antes del instante comparado, y es lo último declarado; " +
    "lo declaró CDR (asiento 7): declarado por una persona, no telemetría.";
  const declared = (note: string | null) => ({
    kind: "declared_system" as const,
    label: "coincidencia temporal, no causa",
    title: "Sistema Revitalización de aire declarado «degradado» dentro de la ventana comparada",
    affected: ["crew-01", "crew-02"],
    excursion: null,
    what_is_known: null,
    checks: [],
    evidence: [],
    steps: [],
    review: null,
    system: {
      key: "air-revitalization",
      display: "Revitalización de aire",
      state: "degraded",
      state_display: "degradado",
      module: null,
      module_display: "sistema entero",
      start: "2026-11-30T14:00:00+00:00",
      end: null,
      declared_by: ["CDR"],
      ledger_index: 7,
      last_ledger_index: 7,
      note,
      note_by: note === null ? null : "CDR",
      label: "declarado por una persona, no telemetría",
      statement,
    },
  });

  it("el titulo de un sistema declarado lleva el dibujo de ese sistema, sin color", () => {
    expect(hypothesisMark(declared(null))).toEqual({ pictogram: "wind", color: null, className: undefined });
    expect(hypothesisMark({ kind: "declared_system", system: { key: "propulsion" } }).pictogram).toBe(
      UNKNOWN_MARK.pictogram,
    );
    // Las demas clases, como antes.
    expect(hypothesisMark({ kind: "shared_unknown" })).toBe(hypothesisKindMark("shared_unknown"));
  });

  it("un sistema declarado ensena la frase del backend con el dibujo de declarar, y ningun mando", () => {
    const html = render(createElement(HypothesisReview, { hypothesis: declared("el lecho 2 no regenera"), operator: "CDR", onReviewed: () => {} }));
    expect(html).toMatch(/<span class="mark"><svg[^>]*data-pictogram="pen"[^>]*>.*?<\/svg>Declarado «degradado»/);
    expect(html).not.toMatch(/c-(yellow|blue|red|cyan|gray)/);
    expect(html).not.toContain("Confirmar");
    expect(html).not.toContain("<input");
    expect(textNodes(html)).toEqual([statement, "Nota de CDR:", "el lecho 2 no regenera"]);
    const bare = render(createElement(HypothesisReview, { hypothesis: declared(null), operator: undefined, onReviewed: () => {} }));
    expect(textNodes(bare)).toEqual([statement]);
  });

  it("un sistema declarado en un modulo dice donde y quien estaba alli, como una excursion; el sistema entero, nada", () => {
    const base = declared(null);
    const inModule = {
      ...base,
      system: { ...base.system, module: "laboratorio", module_display: "Laboratorio" },
      location: {
        module: "laboratorio",
        module_display: "Laboratorio",
        present: ["crew-01"],
        elsewhere: ["crew-02"],
        undeclared: [],
      },
    };
    const name = (key: string) => (key === "laboratorio" ? "Laboratorio" : key);
    const html = render(createElement(HypothesisPlaceLine, { item: inModule, moduleName: name }));
    expect(html).toMatch(/Declarado en: <span class="mark"><svg[^>]*data-pictogram="flask"[^>]*>.*?<\/svg>Laboratorio<\/span>/);
    expect(textNodes(html).join("")).toContain("estaban allí: crew-01");
    expect(textNodes(html).join("")).toContain("en otro módulo: crew-02");
    expect(render(createElement(HypothesisPlaceLine, { item: base, moduleName: name }))).toBe("");
  });

  // §5.37.5: la radiación registrada en la ventana entra como coincidencia en el tiempo. Lleva
  // el dibujo de la escala aguda del panel de radiación y la frase del backend, tal cual.
  const radiationStatement =
    "Tasa de dosis absorbida por encima de su límite de peligro (100,0 µGy/h) en 35 lecturas del " +
    "dosímetro de crew-01, la primera 34,0 h antes del instante comparado, con un máximo de 1529,2 " +
    "µGy/h; origen de las lecturas: simulator:spe-event. Sin datos de NASA DONKI que cubran la " +
    "ventana: la tasa de dosis sola no dice si fue un evento solar.";
  const solar = {
    kind: "solar_event" as const,
    label: "coincidencia temporal, no causa",
    title: "Tasa de dosis por encima de su límite de peligro dentro de la ventana comparada",
    affected: ["crew-01"],
    excursion: null,
    what_is_known: null,
    checks: [],
    evidence: [],
    steps: [],
    review: null,
    radiation: {
      dose: null,
      donki: { status: "no_data" as const, events: [] },
      statement: radiationStatement,
    },
  };

  it("la radiacion registrada lleva el dibujo de la escala aguda, sin color, y la frase del backend sin ningun mando", () => {
    expect(hypothesisMark(solar)).toEqual({ pictogram: "burst", color: null, className: undefined });
    expect(hypothesisKindMark("solar_event")).toEqual(hypothesisMark(solar));
    const html = render(createElement(HypothesisReview, { hypothesis: solar, operator: "CDR", onReviewed: () => {} }));
    expect(textNodes(html)).toEqual([radiationStatement]);
    expect(html).not.toMatch(/c-(yellow|blue|red|cyan|gray)/);
    expect(html).not.toContain("Confirmar");
    expect(html).not.toContain("<input");
  });
});

describe("un sistema del habitat, pintado", () => {
  const status = (over: Partial<HabitatSystems["systems"][number]["statuses"][number]>) => ({
    module: null,
    module_display: "sistema entero",
    state: "undeclared",
    state_display: "sin declarar",
    declared: false,
    since: null,
    last_declared_at: null,
    declarations: 0,
    note: null,
    declared_by: null,
    ledger_index: null,
    recorded: null,
    ...over,
  });
  const air: HabitatSystems["systems"][number] = {
    key: "air-revitalization",
    display: "Revitalización de aire",
    description: "Retira el CO2 del aire de cabina y repone el oxígeno.",
    parameters: [
      { key: "cabin-ppco2", display: "CO2 de cabina (presión parcial)" },
      { key: "cabin-ppo2", display: "O2 de cabina (presión parcial)" },
    ],
    statuses: [
      status({}),
      status({
        module: "laboratorio",
        module_display: "Laboratorio",
        state: "degraded",
        state_display: "degradado",
        declared: true,
        declared_by: "CDR",
      }),
    ],
  };
  const html = render(
    createElement("dl", null, createElement(SystemEntry, { system: air, rows: systemRows({ systems: [air] }), met: () => "" })),
  );

  it("el nombre del sistema con su pictograma, sin color", () => {
    expect(html).toMatch(/<dt[^>]*><span class="mark"><svg[^>]*data-pictogram="wind"[^>]*>.*?<\/svg>Revitalización de aire<\/span><\/dt>/);
  });

  it("cada estado con la marca de systems.ts: sin declarar en cian con anillo; degradado en amarillo con triangulo", () => {
    expect(html).toMatch(/<span class="mark c-cyan"><svg[^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>sin declarar<\/span>/);
    expect(html).toMatch(/<span class="mark c-yellow"><svg[^>]*data-pictogram="shape-triangle"[^>]*>.*?<\/svg>degradado<\/span>/);
  });

  it("el modulo de una declaracion y los parametros relacionados llevan su pictograma junto al nombre", () => {
    expect(html).toMatch(/<span class="mark"><svg[^>]*data-pictogram="flask"[^>]*>.*?<\/svg>Laboratorio<\/span>/);
    expect(html).toMatch(/<span class="mark"><svg[^>]*data-pictogram="atoms-three"[^>]*>.*?<\/svg>CO2 de cabina \(presión parcial\)<\/span>/);
    expect(html).toMatch(/<span class="mark"><svg[^>]*data-pictogram="atoms-two"[^>]*>.*?<\/svg>O2 de cabina \(presión parcial\)<\/span>/);
    // La coma entre parametros sigue en el texto, sin partir la linea.
    expect(textLines(html)).toContain(
      "Parámetros de cabina relacionados por definición: CO2 de cabina (presión parcial), O2 de cabina (presión parcial)",
    );
  });
});

describe("en las fuentes del panel", () => {
  const strip = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

  it("ningun glifo de texto queda como señal: todos pasaron a pictograma", () => {
    for (const path of [
      "./HabitatPanel.tsx",
      "./CrewComparison.tsx",
      "./SystemsStatus.tsx",
      "./HypothesisReview.tsx",
      "./flow.ts",
      "./systems.ts",
    ]) {
      expect(strip(read(path)), path).not.toMatch(/[◌△◇■●◐▷⊘✕✗✓↻☐▌]/);
    }
  });

  it("modulo, parametro, clase de hipotesis, ubicacion, dato ausente y clase de limite se pintan por las tablas, no a mano", () => {
    const panel = read("./HabitatPanel.tsx");
    for (const call of [
      "modulePictogram(",
      "parameterPictogram(",
      "<MarkOf mark={hypothesisMark(",
      '<MarkOf mark={presenceMark("present")}>',
      '<MarkOf mark={presenceMark("elsewhere")}>',
      '<MarkOf mark={presenceMark("undeclared")}>',
      "<MarkOf mark={MISSING_MARK}>",
      "<MarkOf mark={limitMark(",
    ]) {
      expect(panel).toContain(call);
    }
    // Ninguna vista escribe a mano la marca de dato ausente ni la de la clase de un limite.
    for (const path of ["./HabitatPanel.tsx", "./CrewComparison.tsx", "./SystemsStatus.tsx"]) {
      expect(read(path), path).not.toMatch(/pictogram="(ring-dotted|shape-triangle|shape-diamond)"/);
    }
    expect(read("./SystemsStatus.tsx")).toContain("systemPictogram(");
    expect(read("./CrewComparison.tsx")).toContain("parameterPictogram(");
  });

  it("titulos, plegables y mandos van por las piezas del nucleo, con su signo (§5.33.4)", () => {
    const views = ["./HabitatPanel.tsx", "./CrewComparison.tsx", "./SystemsStatus.tsx", "./HypothesisReview.tsx"];
    for (const path of views) {
      const source = strip(read(path));
      expect(source, path).not.toMatch(/<details\b|<summary\b|<h2\b|className="command"/);
    }
    // El unico `<h3>` a mano es el de una grafica sin dibujar, cuyo titulo ya lleva sus marcas.
    expect(strip(read("./CrewComparison.tsx")).match(/<h3\b/g)).toHaveLength(1);
    for (const path of ["./HabitatPanel.tsx", "./SystemsStatus.tsx"]) {
      expect(strip(read(path)), path).not.toMatch(/<h3\b/);
    }
    // Lo que sale mal en una peticion, con la marca de lo que fue (`requestOutcome`, §5.34.14):
    // la cruz roja si cayo, el triangulo si el backend dijo que no; esperar, la flecha.
    for (const path of ["./HabitatPanel.tsx", "./CrewComparison.tsx", "./SystemsStatus.tsx", "./HypothesisReview.tsx"]) {
      expect(read(path), path).toContain("<MarkOf mark={error.mark}>");
      expect(read(path), path).toContain("setError(requestOutcome(");
      expect(read(path), path).not.toMatch(/FAILURE_MARK|REFUSED_MARK/);
    }
    expect(read("./CrewComparison.tsx")).toContain("<MarkOf mark={LOADING_MARK}>");
    for (const path of views) expect(read(path), path).not.toMatch(/<span className="c-yellow">/);
  });

  it("el aire de cabina es el dibujo del sistema que lo trata, y el flujo tiene el suyo", () => {
    expect(CABIN_AIR_PICTOGRAM).toBe(systemPictogram("air-revitalization"));
    expect(isPictogramName(FLOW_STEPS_PICTOGRAM)).toBe(true);
    expect(REFUSED_MARK).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
  });
});

describe("el medidor de un parametro de cabina, pintado (§5.33.4)", () => {
  it("dentro de escala: barra neutra con la banda del limite, sin texto nuevo", () => {
    const html = row(2.1);
    expect(html).toMatch(/role="meter"[^>]*aria-label="CO2 de cabina \(presión parcial\)"/);
    expect(html).toContain('aria-valuemax="6"');
    expect(html).toContain('class="meter-band"');
    expect(textNodes(html)).toEqual(["CO2 de cabina (presión parcial)", "2,1", "mmHg", "límite ≤ 3,0 mmHg ([V2 6004])"]);
  });

  it("fuera de escala con la excursion vigente: barra vacia y la marca de la fila con su palabra", () => {
    const html = row(7.5, excursion("health", "[V2 6004]"));
    expect(html).toContain("meter meter-oor");
    expect(html).not.toContain("meter-fill");
    expect(html.match(/data-pictogram="shape-triangle"/g)).toHaveLength(2);
    expect(textNodes(html).filter((text) => text === "fuera de [V2 6004]")).toHaveLength(2);
  });

  it("fuera de escala sin excursion que lo diga: sin medidor, en vez de una palabra inventada", () => {
    const html = row(7.5);
    expect(html).not.toContain('role="meter"');
  });

  it("sin escala que dar (varios limites normativos): sin medidor", () => {
    const co: HabitatParameter = {
      ...ppco2,
      key: "cabin-co",
      unit: "[ppm]",
      limits: [
        { low: null, high: 425, requirement: "SMAC 1 h", kind: "health", averaging_minutes: 60 },
        { low: null, high: 15, requirement: "SMAC 30 d", kind: "health", averaging_minutes: 43200 },
      ],
    };
    const html = render(createElement("dl", null, createElement(HabitatRow, { spec: co, value: 3, active: null, comfort: null })));
    expect(html).not.toContain('role="meter"');
  });
});
