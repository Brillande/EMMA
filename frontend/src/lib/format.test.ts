import { describe, expect, it } from "vitest";

import {
  displayUnit,
  formatAge,
  formatDay,
  formatHouseholdTime,
  formatField,
  formatMet,
  formatMinutes,
  formatNumber,
  formatSourceDate,
  formatUtc,
  missionElapsedSeconds,
} from "./format";

const NNBSP = " ";

describe("F.5.6: numeros", () => {
  it("f. cero inicial si el valor absoluto es menor que 1", () => {
    expect(formatNumber(0.25, 2)).toBe("0,25");
    expect(formatNumber(-0.5, 1)).toBe("-0,5");
  });

  it("g. sin ceros a la izquierda", () => {
    expect(formatNumber(3.14, 2)).toBe("3,14");
    expect(formatNumber(7)).toBe("7");
  });

  it("h. nunca un '+'", () => {
    expect(formatNumber(12, 0)).not.toContain("+");
  });

  it("i. el menos siempre en los negativos", () => {
    expect(formatNumber(-3, 0)).toBe("-3");
    expect(formatNumber(-1.25, 2)).toBe("-1,25");
  });

  it("un negativo que redondea a cero no lleva signo", () => {
    expect(formatNumber(-0.004, 2)).toBe("0,00");
  });

  it("j. separador de millares desde cinco digitos, y no antes", () => {
    expect(formatNumber(1234)).toBe("1234");
    expect(formatNumber(12345)).toBe(`12${NNBSP}345`);
    expect(formatNumber(1234567.5, 1)).toBe(`1${NNBSP}234${NNBSP}567,5`);
  });

  it("desviacion declarada: coma decimal, no punto", () => {
    expect(formatNumber(36.6, 1)).toBe("36,6");
  });

  it("rechaza lo que no es una cifra", () => {
    expect(() => formatNumber(Number.NaN)).toThrow(RangeError);
    expect(() => formatNumber(Number.POSITIVE_INFINITY)).toThrow(RangeError);
  });
});

describe("F.4.3.1: campos de ancho fijo", () => {
  it("f. un valor que cabe se alinea a la derecha dentro del campo", () => {
    expect(formatField(72, 0, 3)).toEqual({ text: " 72", overflow: false });
  });

  it("h. el desbordamiento se sustituye por asteriscos, y se marca", () => {
    const field = formatField(1500, 0, 3);
    expect(field).toEqual({ text: "***", overflow: true });
  });

  it("h. salvo el signo y la coma decimal", () => {
    expect(formatField(-123.4, 1, 5)).toEqual({ text: "-**,*", overflow: true });
    expect(formatField(9999.9, 1, 5)).toEqual({ text: "***,*", overflow: true });
  });

  it("nunca recorta la cifra: 150 no puede leerse como 15", () => {
    expect(formatField(150, 0, 2).text).not.toContain("15");
  });
});

describe("F.6.1: tiempo de mision", () => {
  it("formato dddd/hh:mm:ss con el dia sin ceros a la izquierda", () => {
    expect(formatMet(57 * 86_400 + 14 * 3_600 + 8 * 60 + 33)).toBe("MET 57/14:08:33");
    expect(formatMet(1089 * 86_400 + 13 * 3_600 + 3 * 60 + 1)).toBe("MET 1089/13:03:01");
  });

  it("siempre con la etiqueta del sistema de tiempo", () => {
    expect(formatMet(0)).toBe("MET 0/00:00:00");
    expect(formatMet(60, "PET")).toBe("PET 0/00:01:00");
  });

  it("negativo antes del origen", () => {
    expect(formatMet(-90)).toBe("MET -0/00:01:30");
  });

  it("se calcula desde el origen de mision en UTC", () => {
    const at = new Date("2026-11-14T08:00:00Z");
    expect(formatMet(missionElapsedSeconds("2026-11-01", at))).toBe("MET 13/08:00:00");
  });

  it("lo que no es tiempo de mision va en UTC y lo dice, venga con el desfase que venga", () => {
    expect(formatUtc(new Date("2026-10-07T09:14:33+00:00"))).toBe("2026-10-07 09:14 UTC");
    expect(formatUtc(new Date("2026-10-07T01:30:00+02:00"))).toBe("2026-10-06 23:30 UTC");
    expect(() => formatUtc(new Date("no es una fecha"))).toThrow(RangeError);
  });
});

describe("F.5.6 b: unidades", () => {
  it("cambia la escritura, no la magnitud", () => {
    expect(displayUnit("Cel")).toBe("°C");
    expect(displayUnit("mm[Hg]")).toBe("mmHg");
    expect(displayUnit("ug/dL")).toBe("µg/dL");
  });

  it("las anotaciones UCUM se nombran: ningun numero sin unidad", () => {
    expect(displayUnit("{count}")).toBe("recuento");
    expect(displayUnit("{score}")).toBe("puntos");
  });

  it("una unidad sin revisar falla en vez de mostrarse", () => {
    expect(() => displayUnit("mg")).toThrow(RangeError);
  });

  it("cubre todas las unidades del catalogo del backend", () => {
    // Copia de las unidades de /api/indicators a 2026-09-23. Si el catalogo gana
    // una unidad nueva, la interfaz tiene que aprender a escribirla.
    const catalogUnits = [
      "/min", "Cel", "%", "mm[Hg]", "kg", "ms", "{count}", "h", "{score}",
      "uGy/h", "mSv", "min", "nmol/L", "ug/dL",
    ];
    for (const unit of catalogUnits) {
      expect(() => displayUnit(unit)).not.toThrow();
    }
  });
});

describe("duraciones", () => {
  it("minutos con un decimal por debajo de diez, enteros por encima", () => {
    expect(formatMinutes(14.294)).toBe("14 min");
    expect(formatMinutes(4.25)).toBe("4,3 min");
  });
});

describe("fecha de una fuente citada", () => {
  it("se muestra con la precision que da el registro, sin completarla", () => {
    expect(formatSourceDate("2017")).toBe("2017");
    expect(formatSourceDate("2017-06")).toBe("2017-06");
    expect(formatSourceDate("2023-11-14")).toBe("2023-11-14");
  });

  it("una fecha con otra forma falla en vez de mostrarse", () => {
    for (const bad of ["14/11/2023", "2023-13", "2023-11-32", "hacia 2017", ""]) {
      expect(() => formatSourceDate(bad), bad).toThrow(RangeError);
    }
  });
});

describe("un día declarado (inicio o fin de una misión previa)", () => {
  it("en ISO 8601 y con el día obligatorio; otra forma falla", () => {
    expect(formatDay("2021-04-01")).toBe("2021-04-01");
    for (const bad of ["2021", "2021-04", "01/04/2021", "2021-04-32", "2021-04-01T00:00", ""]) {
      expect(() => formatDay(bad), bad).toThrow(RangeError);
    }
  });
});

describe("formatAge", () => {
  it("minutos enteros, horas con un decimal hasta dos días, y días; nunca negativa", () => {
    expect(formatAge(7.4)).toBe("7 min");
    expect(formatAge(150)).toBe("2,5 h");
    expect(formatAge(3 * 24 * 60)).toBe("3,0 d");
    expect(formatAge(-5)).toBe("0 min");
  });

  it("el escalón se decide con la cifra redondeada: una edad no se escribe de dos formas (lógica 6)", () => {
    // Antes 59,7 min daba «60 min» y 60 min «1,0 h»; y 47,98 h daba «48,0 h» frente a «2,0 d».
    expect(formatAge(59.7)).toBe(formatAge(60));
    expect(formatAge(59.7)).toBe("1,0 h");
    expect(formatAge(48 * 60 - 1)).toBe(formatAge(48 * 60));
    expect(formatAge(48 * 60 - 1)).toBe("2,0 d");
    expect(formatAge(59.4)).toBe("59 min");
  });
});

describe("formatHouseholdTime", () => {
  it("da la hora del hogar a 24 horas, no la UTC", () => {
    expect(formatHouseholdTime("2026-11-12T17:00:00.000Z", "Europe/Madrid")).toBe("18:00");
    expect(formatHouseholdTime("2026-07-12T17:00:00.000Z", "Europe/Madrid")).toBe("19:00");
    expect(formatHouseholdTime("2026-11-12T05:05:00Z", "UTC")).toBe("05:05");
  });
  it("falla con un instante o una zona que no se pueden leer", () => {
    expect(() => formatHouseholdTime("ayer", "UTC")).toThrow(RangeError);
    expect(() => formatHouseholdTime("2026-11-12T05:05:00Z", "Marte/Olympus")).toThrow(RangeError);
  });
});
