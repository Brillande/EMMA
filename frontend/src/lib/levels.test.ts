import { afterEach, describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import { LEVELS, LEVEL_ORDER, adoptLevelLabels, levelStyle } from "./levels";

afterEach(() => adoptLevelLabels(null));

describe("tabla F.5-1 y F.6.4: color por nivel", () => {
  it("critical en rojo y como aviso (W)", () => {
    expect(LEVELS.critical.color).toBe("red");
    expect(LEVELS.critical.alertClass).toBe("W");
  });

  it("concern en amarillo y como caution (C)", () => {
    expect(LEVELS.concern.color).toBe("yellow");
    expect(LEVELS.concern.alertClass).toBe("C");
  });

  it("watch en azul y como advertencia (A)", () => {
    expect(LEVELS.watch.color).toBe("blue");
    expect(LEVELS.watch.alertClass).toBe("A");
  });

  it("nominal sin color de alerta, y nunca en gris ni cian", () => {
    expect(LEVELS.nominal.color).toBe("text");
    expect(LEVELS.nominal.alertClass).toBeNull();
  });
});

describe("F.5.10 e: el nivel nunca depende solo del color", () => {
  it("cada nivel tiene una palabra y un pictograma propios, y el pictograma existe", () => {
    const labels = LEVEL_ORDER.map((level) => LEVELS[level].label);
    const pictograms = LEVEL_ORDER.map((level) => LEVELS[level].pictogram);
    expect(new Set(labels).size).toBe(LEVEL_ORDER.length);
    expect(new Set(pictograms).size).toBe(LEVEL_ORDER.length);
    for (const name of pictograms) expect(isPictogramName(name), name).toBe(true);
  });
});

describe("la palabra de cada nivel es la del backend", () => {
  const GIVEN = { nominal: "palabra-a", watch: "palabra-b", concern: "palabra-c", critical: "palabra-d" };

  it("se pinta la que trae el estado, tal cual", () => {
    adoptLevelLabels(GIVEN);
    for (const level of LEVEL_ORDER) expect(levelStyle(level).label).toBe(GIVEN[level]);
  });

  it("antes de que llegue ningun estado se nombra con la clave de la API, no con una palabra propia", () => {
    for (const level of LEVEL_ORDER) expect(LEVELS[level].label).toBe(level);
  });

  it("un estado nuevo sustituye las palabras: no se conserva la que el backend ya no da", () => {
    adoptLevelLabels(GIVEN);
    adoptLevelLabels({ concern: "otra" });
    expect(LEVELS.concern.label).toBe("otra");
    expect(LEVELS.watch.label).toBe("watch");
  });

  it("una palabra vacia no deja el pictograma solo: queda la clave", () => {
    adoptLevelLabels({ concern: "  " });
    expect(LEVELS.concern.label).toBe("concern");
  });

  it("el color y el pictograma no cambian con la palabra: siguen siendo de la interfaz", () => {
    const before = LEVEL_ORDER.map((level) => [LEVELS[level].color, LEVELS[level].pictogram]);
    adoptLevelLabels(GIVEN);
    expect(LEVEL_ORDER.map((level) => [LEVELS[level].color, LEVELS[level].pictogram])).toEqual(before);
  });
});

describe("parpadeo: solo el nivel mas grave (desviacion declarada §2.2)", () => {
  it("parpadea critical y nada mas", () => {
    expect(LEVEL_ORDER.filter((level) => LEVELS[level].flashes)).toEqual(["critical"]);
  });
});

describe("un nivel desconocido", () => {
  it("no se pinta como nominal: falla", () => {
    expect(() => levelStyle("unknown")).toThrow(RangeError);
  });
});
