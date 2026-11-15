import { describe, expect, it } from "vitest";

import { cabinDecimals, changeArrow, concordanceStyle, costText, groupCostFacts, sourceStyle } from "./alertContext";
import type { AlertCostFact } from "./api";

describe("el coste de una comprobación: lo que falta, junto por su palabra", () => {
  const fact = (key: string, display: string, missing: boolean, basis: string | null = null): AlertCostFact => ({
    key,
    label: `rótulo ${key}`,
    display,
    missing,
    basis,
  });

  it("lo que hay va suelto y en su orden; lo que falta, junto por la palabra del backend", () => {
    const groups = groupCostFacts([
      fact("mode", "periódico, no invasivo", false),
      fact("crew_time", "sin cifra con fuente", true),
      fact("processing", "a bordo", false),
      fact("mass", "sin clasificar", true),
      fact("power", "sin clasificar", true),
    ]);
    expect(groups.shown.map((item) => item.key)).toEqual(["mode", "processing"]);
    expect(groups.missing).toEqual([
      { display: "sin cifra con fuente", labels: ["rótulo crew_time"] },
      { display: "sin clasificar", labels: ["rótulo mass", "rótulo power"] },
    ]);
  });

  it("qué falta lo dice `missing`, no la palabra; y un ausente con base escrita no pierde su base", () => {
    const groups = groupCostFacts([
      fact("a", "sin clasificar", false),
      fact("crew_time", "sin cifra con fuente", true, "la recogida dura 24 h"),
    ]);
    expect(groups.shown.map((item) => item.key)).toEqual(["a", "crew_time"]);
    expect(groups.missing).toEqual([]);
  });
});

describe("el coste de medir: una cifra leída se formatea en la interfaz", () => {
  it("con los decimales con que se leyó y su unidad tal cual; sin cifra, la palabra del backend", () => {
    const figure = { amount: 10.32, decimals: 2, unit: "lbs", figure: "10.32" };
    expect(costText({ display: "lo que diga el backend", figure })).toBe("10,32 lbs");
    expect(costText({ display: "x", figure: { ...figure, amount: 1.5, decimals: 1, unit: "kg" } })).toBe("1,5 kg");
    expect(costText({ display: "a bordo", figure: null })).toBe("a bordo");
    expect(costText({ display: "a bordo" })).toBe("a bordo");
  });
});

describe("tabla F.5-1: lo que falta en el contexto de una alerta va en cian, y nunca solo", () => {
  it("una fuente sin dato o con dato parcial lleva cian y el anillo punteado", () => {
    for (const status of ["no_data", "partial"]) {
      expect(sourceStyle(status)).toEqual({ pictogram: "ring-dotted", color: "cyan", className: "c-cyan" });
    }
  });

  it("una fuente con dato no lleva señal ni color: no hay nada que señalar", () => {
    expect(sourceStyle("with_data")).toEqual({ pictogram: null, color: null, className: undefined });
  });

  it("un estado de fuente desconocido falla en vez de pasar por «con dato»", () => {
    expect(() => sourceStyle("unknown")).toThrow(RangeError);
    // Las propiedades heredadas de Object no son estados.
    expect(() => sourceStyle("toString")).toThrow(RangeError);
  });
});

describe("la concordancia describe: no usa colores de nivel", () => {
  it("solo «sin dato» lleva señal, y es el anillo punteado en cian", () => {
    expect(concordanceStyle("no_data")).toEqual({ pictogram: "ring-dotted", color: "cyan", className: "c-cyan" });
    for (const state of ["concordant", "against", "unchanged"]) {
      expect(concordanceStyle(state).color).toBeNull();
      expect(concordanceStyle(state).pictogram).toBeNull();
    }
  });

  it("un estado desconocido falla", () => {
    expect(() => concordanceStyle("worse")).toThrow(RangeError);
  });
});

describe("la flecha de F.4.3.1 d sale del campo estructurado del backend, no de la frase", () => {
  it("por encima o subiendo, flecha arriba; por debajo o bajando, flecha abajo", () => {
    expect(changeArrow("high")).toBe("arrow-up");
    expect(changeArrow("rising")).toBe("arrow-up");
    expect(changeArrow("low")).toBe("arrow-down");
    expect(changeArrow("falling")).toBe("arrow-down");
  });

  it("sin sentido conocido no hay flecha: ni estable, ni ausente, ni un valor nuevo", () => {
    expect(changeArrow("stable")).toBeNull();
    expect(changeArrow(undefined)).toBeNull();
    expect(changeArrow(null)).toBeNull();
    expect(changeArrow("por encima")).toBeNull();
    expect(changeArrow("toString")).toBeNull();
  });
});

describe("cifras de cabina", () => {
  it("las menores que uno llevan dos decimales para no leerse cero", () => {
    expect(cabinDecimals(0.02)).toBe(2);
    expect(cabinDecimals(5.314)).toBe(1);
    expect(cabinDecimals(-0.5)).toBe(2);
  });
});
