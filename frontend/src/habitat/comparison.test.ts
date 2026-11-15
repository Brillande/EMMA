import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { CrewCompare, CrewCompareSeries, CrewOverview, HabitatExcursion } from "../lib/api";
import { FAILURE_MARK, MISSING_MARK, UNAVAILABLE_MARK } from "../lib/marks";
import {
  findingCounts,
  prepareComparison,
  suggestedIndicator,
  suggestedParameter,
} from "./comparison";
import { limitMark } from "./flow";

const START = "2026-11-01";
const DAY = 86_400;

/** Un instante de la mision: dia y hora desde su origen. */
function at(day: number, hour = 0): string {
  return new Date(Date.UTC(2026, 10, 1 + day, hour)).toISOString();
}

/** Lecturas horarias desde el dia 10: `[lectura, base]`; base `null` = sin linea base personal. */
function series(
  subject: string,
  readings: [value: number, baseline: number | null][],
  extra: Partial<CrewCompareSeries> = {},
): CrewCompareSeries {
  return {
    subject,
    state: "within",
    state_text: "dentro de lo esperado",
    baseline_text: null,
    deviating: false,
    onset: null,
    drivers: [],
    latest: at(10, readings.length - 1),
    origins: [{ type: "measured", context: "simulated" }],
    points: readings.map(([value, baseline], hour) => ({
      effective: at(10, hour),
      value,
      baseline,
      delta: baseline === null ? null : value - baseline,
      concerning: false,
    })),
    ...extra,
  };
}

function compare(crew: CrewCompareSeries[], extra: Partial<CrewCompare> = {}): CrewCompare {
  return {
    key: "heart-rate",
    display: "Heart rate",
    display_es: "Frecuencia cardiaca",
    unit: "/min",
    reference_time: at(10, 3),
    since: at(0),
    baseline_basis: "cada lectura menos la mediana de la línea base personal…",
    series: crew,
    habitat: null,
    summary: {
      label: "coincidencia temporal, no causa",
      text: "Frecuencia cardiaca: ningún tripulante…",
      deviating: [],
      with_data: crew.length,
      first_onset: null,
      simultaneous_since: null,
      onset_basis: "primera lectura fuera de lo esperado dentro de la ventana comparada",
      undated_note: null,
      habitat_excursions: [],
      assumption: "EMMA no registra en qué módulo está cada tripulante…",
      window_hours: 48,
      window_basis: "las 48 h anteriores…",
    },
    ...extra,
  };
}

function excursion(
  parameter: string,
  kind: HabitatExcursion["kind"],
  from: string,
  to: string,
): HabitatExcursion {
  return {
    module: "habitat-principal",
    parameter,
    display: parameter,
    unit: "mm[Hg]",
    kind,
    requirement: kind === "health" ? "[V2 6004]" : "[V2 6013]",
    start: from,
    end: to,
    worst: 5.3,
  };
}

describe("cada tripulante, contra su propia linea base", () => {
  it("dos personas con bases distintas y la misma desviacion se dibujan iguales", () => {
    // 65 /min sobre una base de 60 y 75 sobre una de 70: en valor absoluto no se parecen.
    const prepared = prepareComparison(
      compare([series("crew-01", [[65, 60]]), series("crew-02", [[75, 70]])]),
      START,
    );
    expect(prepared.crew.map((member) => member.points)).toEqual([
      [{ met: 10 * DAY, value: 5 }],
      [{ met: 10 * DAY, value: 5 }],
    ]);
  });

  it("el tiempo va en segundos de mision, el mismo para todos", () => {
    const prepared = prepareComparison(
      compare([
        series("crew-01", [
          [61, 60],
          [62, 60],
        ]),
      ]),
      START,
    );
    expect(prepared.crew[0]?.points.map((point) => point.met)).toEqual([10 * DAY, 10 * DAY + 3_600]);
    expect(prepared.referenceMet).toBe(10 * DAY + 3 * 3_600);
  });

  it("una lectura sin linea base personal no se dibuja: no hay diferencia que inventar", () => {
    const prepared = prepareComparison(
      compare([
        series("crew-01", [
          [61, null],
          [64, 60],
        ]),
      ]),
      START,
    );
    expect(prepared.crew[0]?.points).toEqual([{ met: 10 * DAY + 3_600, value: 4 }]);
  });

  it("quien no tiene base ni lecturas se queda sin serie, con lo que dice el backend", () => {
    const lone = series("crew-09", [[61, null]], {
      baseline_text: "sin línea base personal establecida en este tramo",
    });
    const absent = series("crew-08", [], {
      state: "no_data",
      state_text: "sin dato",
      latest: null,
      origins: [],
    });
    const prepared = prepareComparison(compare([lone, absent]), START);
    expect(prepared.crew.map((member) => member.points)).toEqual([[], []]);
    expect(prepared.crew[0]?.baselineText).toBe("sin línea base personal establecida en este tramo");
    expect(prepared.crew[1]?.stateText).toBe("sin dato");
    expect(prepared.crew[1]?.state).toBe("no_data");
    // Nadie tiene nada que dibujar: no hay escala.
    expect(prepared.range).toBeNull();
  });

  it("el estado, los motivos y el origen pasan tal cual: aqui no se redacta nada", () => {
    const drifting = series("crew-02", [[3, 0.5]], {
      state: "deviating",
      state_text: "deriva sostenida",
      deviating: true,
      drivers: ["Self-reported symptom burden: subiendo 0,61 puntos/semana a lo largo de 21 días"],
      origins: [{ type: "measured", context: "ground" }],
    });
    const [member] = prepareComparison(compare([drifting]), START).crew;
    expect(member?.stateText).toBe("deriva sostenida");
    expect(member?.drivers).toEqual(drifting.drivers);
    expect(member?.origins).toEqual([{ type: "measured", context: "ground" }]);
    // Una deriva no tiene instante de inicio.
    expect(member?.onsetMet).toBeNull();
  });

  it("la primera lectura fuera de lo esperado va en tiempo de mision", () => {
    const out = series("crew-01", [[90, 60]], { onset: at(9, 6) });
    expect(prepareComparison(compare([out]), START).crew[0]?.onsetMet).toBe(9 * DAY + 6 * 3_600);
  });
});

describe("una sola escala vertical para toda la tripulacion", () => {
  it("abarca a todos y deja margen", () => {
    const prepared = prepareComparison(
      compare([
        series("crew-01", [
          [62, 60],
          [64, 60],
        ]),
        series("crew-02", [
          [69, 70],
          [90, 70],
        ]),
      ]),
      START,
    );
    // De -1 a 20: amplitud 21, margen del 8 %.
    expect(prepared.range?.[0]).toBeCloseTo(-1 - 21 * 0.08, 9);
    expect(prepared.range?.[1]).toBeCloseTo(20 + 21 * 0.08, 9);
  });

  it("incluye siempre el cero, que es la linea base de cada uno", () => {
    const above = prepareComparison(compare([series("crew-01", [[65, 60]])]), START);
    expect(above.range?.[0]).toBeLessThan(0);
    const below = prepareComparison(compare([series("crew-01", [[55, 60]])]), START);
    expect(below.range?.[1]).toBeGreaterThan(0);
  });

  it("no degenera cuando todos estan justo en su base", () => {
    const prepared = prepareComparison(compare([series("crew-01", [[60, 60]])]), START);
    expect(prepared.range?.[0]).toBeLessThan(0);
    expect(prepared.range?.[1]).toBeGreaterThan(0);
  });

  it("sin lecturas del indicador en nadie no hay eje ni escala", () => {
    const empty = compare([series("crew-01", [], { state: "no_data", state_text: "sin dato" })], {
      reference_time: null,
      since: null,
    });
    const prepared = prepareComparison(empty, START);
    expect(prepared.referenceMet).toBeNull();
    expect(prepared.range).toBeNull();
    expect(prepared.cabin).toBeNull();
  });
});

describe("el parametro de cabina, en el mismo tiempo", () => {
  const habitat: NonNullable<CrewCompare["habitat"]> = {
    parameter: {
      key: "cabin-temperature",
      display: "Temperatura de cabina",
      unit: "Cel",
      limits: [
        { low: 18, high: 27, requirement: "[V2 6012]", kind: "health", averaging_minutes: null },
        { low: 20, high: 25, requirement: "[V2 6013]", kind: "performance", averaging_minutes: null },
      ],
      averaging_minutes: null,
      source: { id: "ochmo-tb-002", title: "OCHMO-TB-002", url: "https://www.nasa.gov/", read_on: "2026-10-21" },
    },
    state: "ok",
    state_text: null,
    evidence_contexts: ["simulated"],
    points: [
      { effective: at(10, 0), value: 26, module: "habitat-principal" },
      { effective: at(10, 1), value: 28, module: "habitat-principal" },
    ],
    excursions: [
      excursion("cabin-temperature", "health", at(10, 1), at(10, 2)),
      excursion("cabin-temperature", "performance", at(9), at(10, 2)),
    ],
  };

  it("solo los limites normativos se trazan, en el amarillo de precaucion", () => {
    const cabin = prepareComparison(compare([], { habitat }), START).cabin;
    expect(cabin?.limits).toEqual([
      { value: 18, tone: "yellow", dashed: false },
      { value: 27, tone: "yellow", dashed: false },
    ]);
    expect(cabin?.limitRequirements).toEqual(["[V2 6012]"]);
  });

  it("solo las excursiones de limite normativo se sombrean, con su requisito", () => {
    const cabin = prepareComparison(compare([], { habitat }), START).cabin;
    expect(cabin?.excursions).toEqual([{ from: 10 * DAY + 3_600, to: 10 * DAY + 2 * 3_600 }]);
    expect(cabin?.excursionRequirements).toEqual(["[V2 6004]"]);
  });

  it("sus lecturas van en tiempo de mision y declaran su entorno", () => {
    const cabin = prepareComparison(compare([], { habitat }), START).cabin;
    expect(cabin?.points).toEqual([
      { met: 10 * DAY, value: 26 },
      { met: 10 * DAY + 3_600, value: 28 },
    ]);
    expect(cabin?.evidenceContexts).toEqual(["simulated"]);
  });

  it("sin lecturas de cabina se dice lo que dice el backend", () => {
    const missing = { ...habitat, state: "no_data" as const, state_text: "sin dato", points: [] };
    const cabin = prepareComparison(compare([], { habitat: missing }), START).cabin;
    expect(cabin?.points).toEqual([]);
    expect(cabin?.stateText).toBe("sin dato");
  });
});

describe("que comparar primero", () => {
  const member = (subject: string, indicators: string[]): CrewOverview["crew"][number] => ({
    subject,
    overall_level: "watch",
    summary: "",
    reference_time: at(10),
    domains: {},
    location: null,
    indicators,
  });
  const catalog = ["heart-rate", "sleep-efficiency", "symptom-burden", "pvt-mean-rt"];

  it("el indicador con hallazgo en mas tripulantes", () => {
    const crew = [
      member("crew-01", ["symptom-burden", "pvt-mean-rt"]),
      member("crew-02", ["symptom-burden"]),
      member("crew-03", []),
    ];
    expect(findingCounts(crew)).toEqual(
      new Map([
        ["symptom-burden", 2],
        ["pvt-mean-rt", 1],
      ]),
    );
    expect(suggestedIndicator(crew, catalog)).toBe("symptom-burden");
  });

  it("a igualdad, el que va antes en el catalogo", () => {
    const crew = [member("crew-01", ["pvt-mean-rt", "sleep-efficiency"])];
    expect(suggestedIndicator(crew, catalog)).toBe("sleep-efficiency");
  });

  it("sin hallazgos, el primero del catalogo; sin catalogo, ninguno", () => {
    expect(suggestedIndicator([member("crew-01", [])], catalog)).toBe("heart-rate");
    expect(suggestedIndicator([member("crew-01", ["symptom-burden"])], [])).toBeNull();
  });

  it("un indicador que no esta en el catalogo no se propone", () => {
    expect(suggestedIndicator([member("crew-01", ["desconocido"])], catalog)).toBe("heart-rate");
  });

  it("el parametro de cabina con una excursion vigente; sin ella, ninguno", () => {
    const known = ["cabin-ppco2", "cabin-temperature"];
    const out = [excursion("cabin-ppco2", "health", at(9), at(10))];
    expect(suggestedParameter(out, known)).toBe("cabin-ppco2");
    expect(suggestedParameter([], known)).toBeNull();
    expect(suggestedParameter([excursion("cabin-otro", "health", at(9), at(10))], known)).toBeNull();
  });
});

describe("regla de interfaz: los tripulantes no se distinguen por color", () => {
  const read = (name: string) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");
  const view = read("./CrewComparison.tsx");

  it("la vista no toca la paleta ni escribe colores a mano", () => {
    // Sin paleta, sin colores literales y sin estilos en linea no hay forma de dar un color a
    // cada persona.
    expect(view).not.toMatch(/lib\/palette|\bpalette\.|\banatomy\./);
    expect(view).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|\bstyle=/);
  });

  /** Las marcas de tabla que la vista pinta con `<MarkOf mark={marca}>`: su color cuenta como escrito. */
  const TABLE_MARKS = {
    MISSING_MARK,
    'limitMark("health")': limitMark("health"),
    UNAVAILABLE_MARK,
  };

  it("solo usa colores con significado, y cada uno con el suyo", () => {
    // Un color entra por la clase `c-<token>`, por el `color` de una marca escrita a mano
    // (`<Mark color="…">`, que emite la misma clase) o por una marca de tabla extendida: se
    // cuentan los tres caminos, con el token desnudo.
    const tokens = "red|yellow|blue|gray|cyan|magenta|green";
    const written = [...view.matchAll(new RegExp(`\\bc-(${tokens})\\b|\\bcolor="(${tokens})"`, "g"))].map(
      (match) => match[1] ?? match[2],
    );
    const fromTables = Object.entries(TABLE_MARKS).flatMap(([name, mark]) => {
      expect(view, name).toContain(`<MarkOf mark={${name}}>`);
      return mark.color === null ? [] : [mark.color];
    });
    const used = [...new Set([...written, ...fromTables])].sort();
    // Cian: dato ausente o en transito. Gris: no disponible. Magenta: texto del sistema.
    // Amarillo: parametro de cabina fuera de su limite normativo. Que la comparacion no se pudo
    // cargar lleva la marca de la peticion (`requestOutcome`, §5.34.14: la cruz roja si cayo, el
    // triangulo si el backend dijo que no), que es de la peticion y no de ningun tripulante.
    expect(used).toEqual(["cyan", "gray", "magenta", "yellow"]);
    expect(view).toContain("<MarkOf mark={error.mark}>{tr(`No se pudo cargar la comparación: ${error.text}`, `Could not load the comparison: ${error.text}`)}</MarkOf>");
  });

  it("cada color va con su pictograma y su palabra, nunca solo", () => {
    // Dato ausente: anillo punteado (la marca de tabla). No disponible: circulo tachado. Fuera de
    // limite: el triangulo de `limitMark`. La barra llena es la muestra del sombreado de la
    // grafica: amarilla junto al parametro que se salio, cian junto a «en transito».
    expect(MISSING_MARK).toEqual({ pictogram: "ring-dotted", color: "cyan", className: "c-cyan" });
    expect(limitMark("health")).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
    expect(UNAVAILABLE_MARK).toEqual({ pictogram: "slash-circle", color: "gray", className: "c-gray" });
    expect(FAILURE_MARK).toEqual({ pictogram: "cross", color: "red", className: "c-red" });
    expect(view).toMatch(/<Mark pictogram="bar-filled" color="yellow">/);
    expect(view).toMatch(/<Mark pictogram="bar-filled" color="cyan">/);
    // Ningun glifo de texto queda como señal.
    expect(view.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "")).not.toMatch(/[◌△◇▌✓✗⊘]/);
  });

  it("la grafica comun traza toda serie en el color del texto: no admite uno por serie", () => {
    const chart = read("../ground/TrendChart.tsx");
    expect(chart).toMatch(/label: seriesLabel,\s+stroke: palette\.text,/);
  });
});
