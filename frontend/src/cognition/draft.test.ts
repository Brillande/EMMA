import { describe, expect, it } from "vitest";

import { check, incomplete, prepare } from "./draft";
import { field, protocol } from "./fixture";

/*
 * Lo tecleado se comprueba contra el rango del backend y con su misma regla —cada prueba con
 * todas sus puntuaciones—, y sin nombre de quien teclea no se envía nada. La PVT no se anota aquí.
 */

const speed = field("cognition-mpt-speed", "speed");
const accuracy = field("cognition-volt-accuracy", "accuracy");

describe("un campo", () => {
  it("vacío no se anota; una cifra con coma o punto, sí", () => {
    expect(check(speed, "  ")).toEqual({ state: "empty" });
    expect(check(speed, "812")).toEqual({ state: "ok", value: 812 });
    expect(check(accuracy, "0,85")).toEqual({ state: "ok", value: 0.85 });
    expect(check(accuracy, "0.85")).toEqual({ state: "ok", value: 0.85 });
  });

  it("lo que no es cifra, o cae fuera del rango del backend, no se envía y dice por qué", () => {
    expect(check(speed, "rápido")).toEqual({ state: "invalid", reason: "No es una cifra." });
    expect(check(speed, "1e3").state).toBe("invalid");
    expect(check(speed, "0")).toEqual({ state: "invalid", reason: "Fuera del rango: RANGO-MS." });
    expect(check(speed, "60001").state).toBe("invalid");
    expect(check(accuracy, "1,2")).toEqual({
      state: "invalid",
      reason: "Fuera del rango: RANGO-PROPORCION.",
    });
    // Los extremos son del rango.
    expect(check(speed, "1").state).toBe("ok");
    expect(check(accuracy, "1").state).toBe("ok");
  });
});

describe("la sesión que se enviaría", () => {
  const volt = protocol.tests[1]!;

  it("una prueba a medias se dice, y no se envía", () => {
    expect(incomplete(volt, { "cognition-volt-speed": "900" })).toBe(true);
    expect(incomplete(volt, { "cognition-volt-speed": "900", "cognition-volt-accuracy": "0,8" })).toBe(false);
    expect(incomplete(volt, {})).toBe(false);
    const prepared = prepare(protocol, { "cognition-volt-speed": "900" }, "crew-01", "CDR");
    expect(prepared.partial).toEqual(["VOLT"]);
    expect(prepared.body).toBeNull();
  });

  it("solo las pruebas escritas, con las cifras leídas, el tripulante y quien teclea recortado", () => {
    const prepared = prepare(
      protocol,
      { "cognition-volt-speed": "900", "cognition-volt-accuracy": "0,8" },
      "crew-02",
      "  CDR ",
    );
    expect(prepared.body).toEqual({
      scores: { "cognition-volt-speed": 900, "cognition-volt-accuracy": 0.8 },
      subject: "crew-02",
      recorded_by: "CDR",
    });
    expect(prepared.invalid).toBe(0);
    expect(prepared.partial).toEqual([]);
  });

  it("nada escrito, un campo inválido o sin nombre: no se envía, y se sabe por qué", () => {
    expect(prepare(protocol, {}, "crew-01", "CDR")).toMatchObject({ body: null, empty: true });
    expect(prepare(protocol, { "cognition-mpt-speed": "0" }, "crew-01", "CDR")).toMatchObject({
      body: null,
      invalid: 1,
      empty: false,
    });
    expect(prepare(protocol, { "cognition-mpt-speed": "700" }, "crew-01", " ... ")).toMatchObject({
      body: null,
      unnamed: true,
    });
  });

  it("la PVT no se anota aquí: aunque llegue una clave suya, no se envía", () => {
    const prepared = prepare(protocol, { "cognition-mpt-speed": "700", "pvt-mean-rt": "250" }, "crew-01", "CDR");
    expect(prepared.body?.scores).toEqual({ "cognition-mpt-speed": 700 });
  });
});
