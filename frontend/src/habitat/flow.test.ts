import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { displayUnit, formatNumber } from "../lib/format";
import { UNKNOWN_MARK } from "../lib/marks";
import { TEXT_TOKENS } from "../lib/palette";
import {
  decimalsFor,
  healthRange,
  limitLabels,
  limitMark,
  meterScale,
  referenceFigure,
  stepMark,
} from "./flow";

const STATES = ["done", "awaiting_human", "in_progress", "not_applicable"];

describe("la marca de un paso del flujo", () => {
  it("cada estado lleva pictograma ademas de color, y un token de texto de la paleta", () => {
    for (const state of STATES) {
      const mark = stepMark(state);
      expect(mark.pictogram).not.toBeNull();
      expect(TEXT_TOKENS).toContain(mark.color);
      expect(mark.className).toBe(`c-${mark.color}`);
    }
  });

  it("los pictogramas distinguen los estados sin el color, con el dibujo del glifo que habia", () => {
    const pictograms = STATES.map((state) => stepMark(state).pictogram);
    expect(new Set(pictograms).size).toBe(STATES.length);
    // ✓ ☐ ↻ – : hecho, a la espera de una persona, en curso, no aplica.
    expect(pictograms).toEqual(["check", "box-empty", "refresh", "dash"]);
  });

  it("no usa los colores de alerta ni el de dato ausente", () => {
    // Un paso pendiente no es una precaucion (amarillo), ni un fallo (rojo), ni un dato
    // ausente o caducado (cian): tabla F.5-1.
    for (const state of STATES) {
      expect(["red", "yellow", "cyan"]).not.toContain(stepMark(state).color);
    }
  });

  it("lo que espera a una persona es aviso; lo que no aplica, no disponible", () => {
    expect(stepMark("awaiting_human").color).toBe("blue");
    expect(stepMark("not_applicable").color).toBe("gray");
    expect(stepMark("done").color).toBe("text");
  });

  it("un estado que esta version no conoce se pinta sin significado, no como otro", () => {
    const mark = stepMark("estado-nuevo");
    expect(mark).toEqual(UNKNOWN_MARK);
    expect(mark.color).toBe("text");
    expect(STATES.map((state) => stepMark(state).pictogram)).not.toContain(mark.pictogram);
  });
});

describe("la marca de la clase de un limite", () => {
  it("normativo: triangulo amarillo (precaucion); confort y rango objetivo: rombo azul (aviso)", () => {
    expect(limitMark("health")).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
    expect(limitMark("performance")).toEqual({ pictogram: "shape-diamond", color: "blue", className: "c-blue" });
    expect(limitMark("target")).toEqual(limitMark("performance"));
  });

  it("una clase que esta version no conoce se pinta sin significado", () => {
    expect(limitMark("otra")).toEqual(UNKNOWN_MARK);
  });
});

describe("como se escribe un limite", () => {
  const limit = (low: number | null, high: number | null, requirement: string, kind = "health") => ({
    low,
    high,
    requirement,
    kind,
    averaging_minutes: null,
  });

  it("un rango, un techo y un suelo, cada uno con su requisito", () => {
    expect(healthRange({ unit: "mm[Hg]", limits: [limit(145, 155, "[V2 6003]")] })).toBe(
      "145,0–155,0 mmHg ([V2 6003])",
    );
    expect(healthRange({ unit: "mm[Hg]", limits: [limit(null, 3, "[V2 6004]")] })).toBe(
      "≤ 3,0 mmHg ([V2 6004])",
    );
    expect(healthRange({ unit: "kPa", limits: [limit(34.5, null, "[V2 6006]")] })).toBe(
      "≥ 34,5 kPa ([V2 6006])",
    );
  });

  it("solo cuenta los limites de salud, y junta los de cada tiempo de exposicion", () => {
    expect(
      healthRange({
        unit: "[ppm]",
        limits: [
          limit(null, 425, "SMAC 1 h"),
          limit(null, 0.1, "SMAC techo"),
          limit(20, 25, "[V2 6013]", "performance"),
        ],
      }),
    ).toBe("≤ 425,0 ppm (SMAC 1 h) · ≤ 0,10 ppm (SMAC techo)");
  });

  it("el rango objetivo no es limite de salud: no sale en el rango, si en los rotulos", () => {
    const oxygen = {
      unit: "mm[Hg]",
      limits: [
        { ...limit(145, 155, "[V2 6003] rango objetivo", "target"), label: "rango objetivo" },
        { ...limit(122, null, "[V2 6003] mínimo absoluto"), label: "mínimo absoluto" },
        { ...limit(20, 25, "[V2 6013]", "performance"), label: "confort" },
      ],
    };
    expect(healthRange(oxygen)).toBe("≥ 122,0 mmHg ([V2 6003] mínimo absoluto)");
    // El rotulo va tal cual lo da el backend; los de confort no se repiten aqui.
    expect(limitLabels(oxygen)).toEqual([
      "[V2 6003] rango objetivo: rango objetivo",
      "[V2 6003] mínimo absoluto: mínimo absoluto",
    ]);
  });

  it("una figura conjunta dice que depende de la humedad y da sus vertices", () => {
    const temperature = {
      unit: "Cel",
      limits: [
        {
          ...limit(18, 27, "[V2 6012]"),
          figure: {
            name: "Figura 6.2-2",
            pair: "cabin-humidity",
            vertices: [
              [19.1, 25],
              [18, 75],
              [25.7, 75],
              [27, 25],
            ],
          },
        },
      ],
    };
    const c = displayUnit("Cel");
    expect(healthRange(temperature)).toBe(
      `18,0–27,0 ${c} según la humedad simultánea ([V2 6012], Figura 6.2-2: ` +
        `19,1 ${c} 25 %, 18,0 ${c} 75 %, 25,7 ${c} 75 %, 27,0 ${c} 25 %)`,
    );
  });

  it("sin limites no inventa ninguno: la luz no recibe un rango", () => {
    expect(healthRange({ unit: "lx", limits: [] })).toBe("");
    expect(displayUnit("lx")).toBe("lx");
  });

  it("las cifras pequeñas llevan mas decimales", () => {
    expect(decimalsFor(0.02)).toBe(2);
    expect(decimalsFor(300)).toBe(1);
  });
});

describe("el panel no redacta el flujo ni la nota de la luz", () => {
  const source = readFileSync(
    fileURLToPath(new URL("./HabitatPanel.tsx", import.meta.url)),
    "utf-8",
  );

  // Desde §5.34.6 la lista de pasos es una pieza compartida con los pasos de una alerta.
  const steps = readFileSync(
    fileURLToPath(new URL("../components/FlowSteps.tsx", import.meta.url)),
    "utf-8",
  );

  it("nombre, estado y frase de cada paso salen del backend", () => {
    expect(source).toMatch(/<FlowSteps steps=\{item\.flow \?\? \[\]\} \/>/);
    for (const field of ["step.name", "step.state_display", "step.detail"]) {
      expect(steps).toContain(field);
    }
    for (const written of ["pendiente de una persona", "no aplica", "en seguimiento"]) {
      expect(source).not.toContain(written);
      expect(steps).not.toContain(written);
    }
  });

  it("el estado de cada paso se pinta con la marca, pictograma y color, junto a la palabra", () => {
    expect(steps).toMatch(/<MarkOf mark=\{stepMark\(step\.state\)\}>\s*\{step\.state_display\}\s*<\/MarkOf>/);
  });

  it("que la luz no tiene limite lo dice el backend", () => {
    expect(source).toContain("spec.limit_note");
    expect(source.toLowerCase()).not.toContain("sin límite verificado");
    expect(source).toContain("item.knowledge_note");
  });

  it("los requisitos de la luz, su rotulo y su condicion salen del backend", () => {
    for (const field of ["spec.reference_label", "item.condition", "item.requirement"]) {
      expect(source).toContain(field);
    }
    for (const written of ["requisito por tarea", "sin límite general", "no conoce la tarea"]) {
      expect(source.toLowerCase()).not.toContain(written);
    }
  });

  it("lo que la norma escribe se pinta con su base y su frase literal, sin redactarlas", () => {
    for (const field of ["item.what_is_known_basis", "source.quote", "source.locator"]) {
      expect(source).toContain(field);
    }
    expect(source.toLowerCase()).not.toContain("la norma lo justifica");
  });
});

describe("la cifra de un requisito que se ensena y no se evalua", () => {
  const row = { low: null, high: null, stated: null, unit: "lx" };

  it("lleva el comparador que da el backend: minimo, maximo o intervalo", () => {
    expect(referenceFigure({ ...row, low: 350 })).toBe(`≥ ${formatNumber(350, 1)} lx`);
    expect(referenceFigure({ ...row, high: 0.02 })).toBe(`≤ ${formatNumber(0.02, 2)} lx`);
    expect(referenceFigure({ ...row, low: 6, high: 10 })).toBe(
      `${formatNumber(6, 1)}–${formatNumber(10, 1)} lx`,
    );
  });

  it("un valor que la tabla da sin comparador no gana uno aqui", () => {
    const written = referenceFigure({ ...row, stated: 250 });
    expect(written).toBe(`${formatNumber(250, 1)} lx`);
    expect(written).not.toMatch(/[≥≤–]/);
  });

  it("sin cifra no escribe ninguna", () => {
    expect(referenceFigure(row)).toBe("");
  });

  it("una unidad sin forma de lectura declarada falla en vez de pintarse", () => {
    expect(() => referenceFigure({ ...row, low: 1, unit: "lx-melanopico" })).toThrow(RangeError);
  });
});

describe("la escala del medidor de un parametro de cabina (§5.33.4)", () => {
  type Limit = Parameters<typeof meterScale>[0]["limits"][number];
  const limit = (low: number | null, high: number | null, kind = "health", extra: Partial<Limit> = {}): Limit => ({
    low,
    high,
    requirement: "[V2 0000]",
    kind,
    averaging_minutes: null,
    ...extra,
  });

  it("un techo en unidad de razon: escala [0, 2 × techo] y la banda de lo permitido", () => {
    // CO2 de cabina y formaldehido, con sus limites de `environment/habitat.py`.
    expect(meterScale({ unit: "mm[Hg]", limits: [limit(null, 3)] })).toEqual({ min: 0, max: 6, band: { low: 0, high: 3 } });
    expect(meterScale({ unit: "[ppm]", limits: [limit(null, 0.1)] })).toEqual({ min: 0, max: 0.2, band: { low: 0, high: 0.1 } });
  });

  it("con suelo y techo, la banda va del uno al otro; la humedad no pasa del 100 %", () => {
    expect(meterScale({ unit: "kPa", limits: [limit(34.5, 103)] })).toEqual({ min: 0, max: 206, band: { low: 34.5, high: 103 } });
    expect(meterScale({ unit: "%", limits: [limit(25, 75), limit(30, 60, "performance")] })).toEqual({
      min: 0,
      max: 100,
      band: { low: 25, high: 75 },
    });
  });

  it("sin escala cuando habria que inventarla", () => {
    // Varios limites normativos (SMAC del CO, los cuatro del O2): la banda tendria que elegir uno.
    expect(meterScale({ unit: "[ppm]", limits: [limit(null, 425), limit(null, 100)] })).toBeNull();
    // Figura conjunta (temperatura con la humedad simultanea).
    const figure = { name: "Figura 6.2-2", pair: "cabin-humidity", vertices: [[18, 25]] };
    expect(meterScale({ unit: "%", limits: [limit(18, 27, "health", { figure })] })).toBeNull();
    // Unidades sin cero fisico: el doble de 85 dB(A) o de 27 °C no es el doble de nada.
    expect(meterScale({ unit: "dB(A)", limits: [limit(null, 85)] })).toBeNull();
    expect(meterScale({ unit: "Cel", limits: [limit(18, 27)] })).toBeNull();
    // Solo suelo, o ningun limite normativo.
    expect(meterScale({ unit: "kPa", limits: [limit(34.5, null)] })).toBeNull();
    expect(meterScale({ unit: "kPa", limits: [limit(20, 25, "performance")] })).toBeNull();
    expect(meterScale({ unit: "kPa", limits: [] })).toBeNull();
  });
});
