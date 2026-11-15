import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import { DOMAIN_LABELS, LEVELS, LEVEL_ORDER } from "../lib/levels";
import { UNKNOWN_MARK } from "../lib/marks";
import { TEXT_TOKENS } from "../lib/palette";
import { NO_STATE, domainPictogram, metOf, seriesPoints, seriesWindowSeconds, stateStyle } from "./chain";

const START = "2026-11-01";
const DAY = 86_400;
const at = (day: number) => new Date(Date.parse(`${START}T00:00:00Z`) + day * DAY * 1000).toISOString();

describe("especificacion §4: el visor es cliente, no decide el nivel", () => {
  it("el nivel que llega se pinta tal cual", () => {
    for (const level of LEVEL_ORDER) expect(stateStyle(level)).toBe(LEVELS[level]);
  });

  it("sin nivel no es nominal: es 'sin datos'", () => {
    expect(stateStyle(null)).toBe(NO_STATE);
    expect(stateStyle(null).label).not.toBe(LEVELS.nominal.label);
    expect(stateStyle(null).color).not.toBe(LEVELS.nominal.color);
  });

  it("un nivel desconocido falla en vez de pintarse", () => {
    expect(() => stateStyle("unknown")).toThrow(RangeError);
    expect(() => stateStyle("")).toThrow(RangeError);
  });
});

describe("tabla F.5-1 y F.5.10 e: como se ve 'sin datos'", () => {
  it("en cian (dato ausente), no en gris (no disponible) ni en un color de alerta", () => {
    expect(NO_STATE.color).toBe("cyan");
    expect(TEXT_TOKENS).toContain(NO_STATE.color);
    expect(LEVEL_ORDER.map((level) => LEVELS[level].color)).not.toContain(NO_STATE.color);
  });

  it("con palabra y pictograma que no son los de ningun nivel", () => {
    expect(LEVEL_ORDER.map((level) => LEVELS[level].pictogram)).not.toContain(NO_STATE.pictogram);
    expect(LEVEL_ORDER.map((level) => LEVELS[level].label)).not.toContain(NO_STATE.label);
  });
});

describe("el pictograma del dominio de una region", () => {
  it("es el del conjunto de dominios para cada dominio que la interfaz conoce", () => {
    for (const domain of Object.keys(DOMAIN_LABELS)) {
      expect(domainPictogram(domain)).toBe(`domain-${domain}`);
      expect(isPictogramName(domainPictogram(domain))).toBe(true);
    }
  });

  it("un dominio desconocido lleva el dibujo de «desconocido», no uno supuesto", () => {
    expect(domainPictogram("inventado")).toBe(UNKNOWN_MARK.pictogram);
    expect(domainPictogram("")).toBe(UNKNOWN_MARK.pictogram);
  });
});

describe("la serie de una variable", () => {
  it("abarca la ventana sobre la que el motor ajusto la tendencia", () => {
    const variable = { effective: at(40), trend: null };
    expect(seriesWindowSeconds(variable, 21, START, 40 * DAY)).toBe(21 * DAY);
  });

  it("se alarga si el ajuste uso mas dias (indicadores que se miden poco)", () => {
    const variable = { effective: at(40), trend: { span_days: 33.5 } };
    expect(seriesWindowSeconds(variable, 21, START, 40 * DAY)).toBe(33.5 * DAY);
  });

  it("se alarga hasta la ultima lectura si es anterior a la ventana", () => {
    const variable = { effective: at(10), trend: null };
    expect(seriesWindowSeconds(variable, 21, START, 40 * DAY)).toBe(31 * DAY);
  });

  it("no empieza antes del origen de la mision", () => {
    const variable = { effective: at(5), trend: null };
    expect(seriesWindowSeconds(variable, 21, START, 6 * DAY)).toBe(6 * DAY);
  });

  it("ordena las lecturas en el tiempo y no toca los valores", () => {
    const reading = (day: number, value: number) => ({
      effectiveDateTime: at(day),
      valueQuantity: { value, unit: "/min" },
    });
    expect(seriesPoints([reading(2, 61), reading(1, 35.5), reading(3, 62)], START)).toEqual([
      { met: DAY, value: 35.5 },
      { met: 2 * DAY, value: 61 },
      { met: 3 * DAY, value: 62 },
    ]);
    expect(metOf(START, at(1))).toBe(DAY);
  });
});
