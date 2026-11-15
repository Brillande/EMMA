import { describe, expect, it } from "vitest";

import { ApiError, type DiaryCatalog, type DiaryIndicator, type DiaryObservationBody } from "../lib/api";
import { REFUSED_MARK } from "../lib/marks";
import {
  afterSubmit,
  canSubmit,
  check,
  itemProblem,
  operatorName,
  parseValue,
  prepare,
  submitAll,
} from "./entry";

const indicator = (over: Partial<DiaryIndicator>): DiaryIndicator => ({
  key: "mood-valence",
  display: "Self-reported mood valence",
  display_es: "Valencia del ánimo autoinformada",
  unit: "{score}",
  unit_display: "puntos",
  domain: "behavioral",
  decimals: 1,
  physical_min: 0,
  physical_max: 10,
  range_text: "de 0,0 a 10,0",
  equipment: "autoinforme",
  mode_display: "periódico, no invasivo",
  scale: {
    described_as: "escala breve de autoinforme propia de la misión",
    labels: null,
    labels_note: "escala sin rótulos verificados",
    concerning: "low",
    concerning_note: "El catálogo vigila el extremo bajo.",
  },
  ...over,
});

const mood = indicator({});
const acceptability = indicator({
  key: "food-acceptability",
  physical_min: 1,
  physical_max: 9,
  range_text: "de 1,0 a 9,0",
});
const fluid = indicator({
  key: "fluid-intake-24h",
  unit: "mL/(24.h)",
  unit_display: "mL/24 h",
  decimals: 0,
  physical_max: 20000,
  range_text: "de 0 a 20 000",
  scale: null,
});

const catalog: DiaryCatalog = {
  indicators: [mood, acceptability, fluid],
  provenance: {
    source: "crew-diary",
    source_display: "registro diario",
    observation_type: "measured",
    evidence_context: "ground",
  },
  recorded_by: {
    required: true,
    label: "ROTULO-DE-QUIEN-ANOTA",
    note: "NOTA-DE-QUIEN-ANOTA",
    missing_display: "NO-CONSTA-DEL-BACKEND",
    legacy_note: "NOTA-DE-LO-ANTIGUO",
  },
  submit_to: "/api/diary/entries",
  notes: [],
};

describe("cifra tecleada", () => {
  it("acepta coma o punto decimal", () => {
    expect(parseValue("6,5")).toBe(6.5);
    expect(parseValue(" 6.5 ")).toBe(6.5);
    expect(parseValue("7")).toBe(7);
  });

  it("lo que no es una cifra escrita con cifras no es una anotación", () => {
    for (const text of ["", "siete", "7 puntos", "1e3", "0x10", "6,5,1", "Infinity", "NaN", ","]) {
      expect(parseValue(text)).toBeNull();
    }
  });
});

describe("campo contra el rango del catálogo", () => {
  it("un campo vacío no se anota y no es un error", () => {
    expect(check(mood, "  ")).toEqual({ state: "empty" });
  });

  it("los extremos del rango entran", () => {
    expect(check(mood, "0")).toEqual({ state: "ok", value: 0 });
    expect(check(mood, "10")).toEqual({ state: "ok", value: 10 });
    expect(check(acceptability, "1")).toEqual({ state: "ok", value: 1 });
  });

  it("fuera del rango no se envía, y el motivo cita el rango que dio el backend", () => {
    expect(check(mood, "10,1")).toEqual({
      state: "invalid",
      reason: "Fuera del rango: de 0,0 a 10,0.",
    });
    expect(check(mood, "-1").state).toBe("invalid");
    // La escala hedónica empieza en 1: un 0 no existe en ella.
    expect(check(acceptability, "0").state).toBe("invalid");
  });

  it("sin límite declarado por un lado, ese lado no se comprueba aquí", () => {
    const open = indicator({ physical_max: null });
    expect(check(open, "5000")).toEqual({ state: "ok", value: 5000 });
    expect(check(open, "-1").state).toBe("invalid");
  });

  it("un texto que no es cifra se dice, no se convierte en cero", () => {
    expect(check(mood, "bien")).toEqual({ state: "invalid", reason: "No es una cifra." });
  });
});

describe("lo que se envía", () => {
  it("nada tecleado: nada que enviar", () => {
    const prepared = prepare(catalog, "crew-01", {}, "CDR");
    expect(prepared).toEqual({ bodies: [], problems: [], unnamed: false });
    expect(canSubmit(prepared)).toBe(false);
  });

  it("solo los campos rellenos, con el sujeto en pantalla y quién anota", () => {
    const prepared = prepare(catalog, "crew-03", {
      "fluid-intake-24h": "2400",
      "mood-valence": "6,5",
    }, "CDR");
    expect(prepared.problems).toEqual([]);
    expect(prepared.bodies).toEqual([
      { key: "mood-valence", value: 6.5, subject: "crew-03", recorded_by: "CDR" },
      { key: "fluid-intake-24h", value: 2400, subject: "crew-03", recorded_by: "CDR" },
    ]);
    expect(canSubmit(prepared)).toBe(true);
  });

  it("no envía ni fuente, ni tipo, ni entorno, ni hora: los pone el backend", () => {
    const [body] = prepare(catalog, "crew-01", { "mood-valence": "7" }, "CDR").bodies;
    expect(Object.keys(body ?? {}).sort()).toEqual(["key", "recorded_by", "subject", "value"]);
  });

  it("sin el nombre de quien anota no se envía nada, por válido que sea lo tecleado", () => {
    for (const nobody of ["", "   ", "—", "..."]) {
      const prepared = prepare(catalog, "crew-01", { "mood-valence": "7" }, nobody);
      expect(prepared).toEqual({ bodies: [], problems: [], unnamed: true });
      expect(canSubmit(prepared)).toBe(false);
    }
  });

  it("el nombre se envía recortado, y no es el tripulante del dato", () => {
    const [body] = prepare(catalog, "crew-02", { "mood-valence": "7" }, "  Ane Z. ").bodies;
    expect(body).toEqual({
      key: "mood-valence",
      value: 7,
      subject: "crew-02",
      recorded_by: "Ane Z.",
    });
    expect(operatorName(" 7 ")).toBe("7");
    expect(operatorName("Ñ")).toBe("Ñ");
    expect(operatorName("  ")).toBeNull();
  });

  it("un campo inválido se sigue diciendo aunque falte el nombre", () => {
    const prepared = prepare(catalog, "crew-01", { "food-acceptability": "12" }, "");
    expect(prepared.problems).toHaveLength(1);
    expect(prepared.unnamed).toBe(true);
  });

  it("con un campo inválido no se envía ninguno", () => {
    const prepared = prepare(catalog, "crew-01", {
      "mood-valence": "7",
      "food-acceptability": "12",
    }, "CDR");
    expect(prepared.problems).toEqual([
      { key: "food-acceptability", reason: "Fuera del rango: de 1,0 a 9,0." },
    ]);
    expect(canSubmit(prepared)).toBe(false);
  });

  it("una clave que el backend no ofrece no se envía aunque esté en el borrador", () => {
    expect(prepare(catalog, "crew-01", { "heart-rate": "60" }, "CDR").bodies).toEqual([]);
  });
});

describe("envío", () => {
  const bodies = prepare(catalog, "crew-01", {
    "mood-valence": "7",
    "food-acceptability": "8",
    "fluid-intake-24h": "2000",
  }, "CDR").bodies;

  it("todo guardado", async () => {
    const sent: DiaryObservationBody[] = [];
    const outcome = await submitAll(
      bodies,
      async (body) => {
        sent.push(body);
      },
    );
    expect(outcome).toEqual({
      saved: ["mood-valence", "food-acceptability", "fluid-intake-24h"],
      failed: null,
    });
    expect(sent).toEqual(bodies);
  });

  it("se detiene en el primer rechazo y da el motivo del backend tal cual", async () => {
    const sent: string[] = [];
    const outcome = await submitAll(
      bodies,
      async (body) => {
        sent.push(body.key);
        if (body.key === "food-acceptability") {
          throw new ApiError(422, "food-acceptability: 8 {score} está fuera de lo físicamente posible");
        }
      },
    );
    expect(outcome).toEqual({
      saved: ["mood-valence"],
      failed: {
        key: "food-acceptability",
        outcome: {
          mark: REFUSED_MARK,
          text: "food-acceptability: 8 {score} está fuera de lo físicamente posible",
        },
      },
    });
    // El tercero no se intenta.
    expect(sent).toEqual(["mood-valence", "food-acceptability"]);
  });

  it("tras el envío se vacía lo guardado y se conserva lo que no entró", () => {
    const draft = { "mood-valence": "7", "food-acceptability": "8", "fluid-intake-24h": "2000" };
    expect(
      afterSubmit(draft, {
        saved: ["mood-valence"],
        failed: { key: "food-acceptability", outcome: { mark: REFUSED_MARK, text: "x" } },
      }),
    ).toEqual({ "food-acceptability": "8", "fluid-intake-24h": "2000" });
  });
});

describe("el alimento valorado (decisión del usuario, 2026-10-26)", () => {
  // La aceptabilidad tal como la da el backend desde ese día: con su campo de alimento. La regla
  // y sus textos son del backend; aquí son marcadores.
  const rated = indicator({
    key: "food-acceptability",
    physical_min: 1,
    physical_max: 9,
    range_text: "de 1,0 a 9,0",
    food_item: {
      label: "ROTULO-DEL-ALIMENTO",
      required: true,
      max_length: 10,
      status: "design",
      status_display: "DECISION-DE-EMMA",
      decided_on: "2026-10-26",
      rule: "REGLA-DEL-ALIMENTO",
      why_free_text: "POR-QUE-TEXTO-LIBRE",
      grouping: "COMO-SE-AGRUPA",
      basis: [],
    },
  });
  const withFood: DiaryCatalog = { ...catalog, indicators: [mood, rated, fluid] };

  it("la valoración va con su alimento, tal como se tecleó; los demás indicadores no lo llevan", () => {
    const prepared = prepare(
      withFood, "crew-01", { "food-acceptability": "5", "mood-valence": "7" }, "CDR",
      { "food-acceptability": " lentejas ", "mood-valence": "no se envía" },
    );
    expect(prepared.problems).toEqual([]);
    expect(prepared.bodies).toEqual([
      { key: "mood-valence", value: 7, subject: "crew-01", recorded_by: "CDR" },
      { key: "food-acceptability", value: 5, subject: "crew-01", recorded_by: "CDR", food: " lentejas " },
    ]);
  });

  it("sin alimento no se envía la valoración, y un alimento sin valoración tampoco se pierde", () => {
    const missing = prepare(withFood, "crew-01", { "food-acceptability": "5" }, "CDR", {});
    expect(missing.problems).toEqual([
      { key: "food-acceptability", reason: "Falta: ROTULO-DEL-ALIMENTO." },
    ]);
    expect(canSubmit(missing)).toBe(false);
    const alone = prepare(withFood, "crew-01", {}, "CDR", { "food-acceptability": "arroz" });
    expect(alone.problems).toEqual([
      { key: "food-acceptability", reason: "ROTULO-DEL-ALIMENTO: falta la cifra." },
    ]);
    // Vacío o solo espacios, y sin valoración: no hay nada que enviar ni que señalar.
    expect(prepare(withFood, "crew-01", {}, "CDR", { "food-acceptability": "  " }).problems).toEqual([]);
  });

  it("el tope de longitud del backend se adelanta; lo demás de la regla lo dice el backend", () => {
    expect(itemProblem(rated, { state: "ok", value: 5 }, "x".repeat(10))).toBeNull();
    // Los espacios de más no cuentan: el backend los quita antes de medir.
    expect(itemProblem(rated, { state: "ok", value: 5 }, " x    xxxxxxxx ")).toBeNull();
    // Nunca más estricto que el backend, que cuenta en NFC: diez «é» escritas descompuestas
    // (letra + tilde combinada) son diez caracteres, no veinte.
    expect(itemProblem(rated, { state: "ok", value: 5 }, "e\u0301".repeat(10))).toBeNull();
    expect(itemProblem(rated, { state: "ok", value: 5 }, "x".repeat(11))).toBe(
      "ROTULO-DEL-ALIMENTO: pasa del tope de caracteres.",
    );
    // Un indicador sin el campo no tiene nada que comprobar.
    expect(itemProblem(mood, { state: "ok", value: 5 }, "")).toBeNull();
  });

  it("una cifra inválida se dice antes que el alimento que falta", () => {
    const prepared = prepare(withFood, "crew-01", { "food-acceptability": "12" }, "CDR", {});
    expect(prepared.problems).toEqual([
      { key: "food-acceptability", reason: "Fuera del rango: de 1,0 a 9,0." },
    ]);
  });

  it("tras el envío se vacía el alimento de lo guardado", () => {
    expect(
      afterSubmit({ "food-acceptability": "lentejas" }, { saved: ["food-acceptability"], failed: null }),
    ).toEqual({});
  });
});

describe("el plato en la fracción rechazada, opcional (decimonovena ronda, 2026-10-31)", () => {
  // La fracción rechazada tal como la da el backend desde ese día: con el campo del alimento y
  // `required` en falso. Los textos son del backend; aquí son marcadores.
  const rejected = indicator({
    key: "food-rejected-fraction",
    unit: "%",
    unit_display: "%",
    decimals: 0,
    physical_min: 0,
    physical_max: 100,
    range_text: "de 0 a 100",
    scale: null,
    food_item: {
      label: "ROTULO-DEL-PLATO",
      required: false,
      requirement_note: "OPCIONAL-SEGUN-EL-BACKEND",
      max_length: 10,
      status: "design",
      status_display: "DECISION-DE-EMMA",
      decided_on: "2026-10-26",
      rule: "REGLA-DEL-ALIMENTO",
      why_free_text: "POR-QUE-TEXTO-LIBRE",
      grouping: "COMO-SE-AGRUPA",
      basis: [],
    },
  });
  const withRejected: DiaryCatalog = { ...catalog, indicators: [mood, rejected] };
  const fraction = { "food-rejected-fraction": "30" };

  it("sin plato se envía igual y sin el campo; con plato, va tal como se tecleó", () => {
    const without = prepare(withRejected, "crew-01", fraction, "CDR", {});
    expect(without.problems).toEqual([]);
    expect(without.bodies).toEqual([
      { key: "food-rejected-fraction", value: 30, subject: "crew-01", recorded_by: "CDR" },
    ]);
    // Solo espacios es no decir el plato: tampoco va.
    const blank = prepare(withRejected, "crew-01", fraction, "CDR", { "food-rejected-fraction": "   " });
    expect(blank.problems).toEqual([]);
    expect(blank.bodies[0]).not.toHaveProperty("food");
    const named = prepare(withRejected, "crew-01", fraction, "CDR", { "food-rejected-fraction": " lentejas " });
    expect(named.bodies).toEqual([
      { key: "food-rejected-fraction", value: 30, subject: "crew-01", recorded_by: "CDR", food: " lentejas " },
    ]);
    expect(canSubmit(named)).toBe(true);
  });

  it("un plato sin su fracción no se pierde en silencio, y el tope de longitud se adelanta igual", () => {
    const alone = prepare(withRejected, "crew-01", {}, "CDR", { "food-rejected-fraction": "arroz" });
    expect(alone.problems).toEqual([
      { key: "food-rejected-fraction", reason: "ROTULO-DEL-PLATO: falta la cifra." },
    ]);
    expect(itemProblem(rejected, { state: "ok", value: 30 }, "")).toBeNull();
    expect(itemProblem(rejected, { state: "ok", value: 30 }, "x".repeat(10))).toBeNull();
    expect(itemProblem(rejected, { state: "ok", value: 30 }, "x".repeat(11))).toBe(
      "ROTULO-DEL-PLATO: pasa del tope de caracteres.",
    );
  });

  it("si el backend lo marcara obligatorio, la consola lo exigiría: manda `required`, no la clave", () => {
    const demanded = indicator({ ...rejected, food_item: { ...rejected.food_item!, required: true } });
    expect(itemProblem(demanded, { state: "ok", value: 30 }, "")).toBe("Falta: ROTULO-DEL-PLATO.");
  });
});
