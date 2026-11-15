import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { CrewStatus } from "./api";
import {
  DEFAULT_SUBJECT,
  arrivalCut,
  baselineRefreshKey,
  crewOptions,
  fallbackSubject,
  groundCut,
  twinsRefreshKey,
} from "./crew";
import { missionElapsedSeconds } from "./format";

const CREW = ["crew-01", "crew-02", "crew-03", "crew-04"];

describe("opciones del selector de tripulante", () => {
  it("son la tripulacion conocida, en su orden", () => {
    expect(crewOptions(CREW, "crew-02")).toEqual(CREW);
  });

  it("conservan al elegido aunque Tierra aun no tenga lecturas suyas", () => {
    // En Tierra la lista trae solo a quien ya tiene lecturas llegadas.
    expect(crewOptions(["crew-01", "crew-03"], "crew-02")).toEqual([
      "crew-01",
      "crew-02",
      "crew-03",
    ]);
  });

  it("con el almacen vacio queda el tripulante por defecto, no un control en blanco", () => {
    expect(crewOptions([], DEFAULT_SUBJECT)).toEqual([DEFAULT_SUBJECT]);
  });

  it("no tocan la lista recibida", () => {
    const members = ["crew-03", "crew-01"];
    crewOptions(members, "crew-02");
    expect(members).toEqual(["crew-03", "crew-01"]);
  });
});

describe("cuando el elegido no tiene lecturas", () => {
  it("se pasa al primero que si las tiene", () => {
    // Se cargo un escenario de un solo tripulante mientras se miraba a crew-03.
    expect(fallbackSubject(["crew-01"], "crew-03", true)).toBe("crew-01");
  });

  it("no se cambia de persona si el elegido tiene datos", () => {
    expect(fallbackSubject(CREW, "crew-03", false)).toBeNull();
    // Ni aunque no figure en la lista: en Tierra puede no haber llegado nada suyo todavia.
    expect(fallbackSubject(["crew-01"], "crew-03", false)).toBeNull();
  });

  it("no se cambia si la lista dice que tiene lecturas: la lista puede ir por detras", () => {
    expect(fallbackSubject(CREW, "crew-03", true)).toBeNull();
  });

  it("una lista pedida antes de elegir no confirma que el elegido este vacio", () => {
    // La banda escribe en real-01 y la consola pasa a el; la lista vieja aun no lo trae.
    expect(fallbackSubject(CREW, "real-01", true, false)).toBeNull();
    // La pedida despues de elegir si lo confirma.
    expect(fallbackSubject(CREW, "real-01", true, true)).toBe("crew-01");
  });

  it("con el almacen vacio no hay a quien pasar", () => {
    expect(fallbackSubject([], DEFAULT_SUBJECT, true)).toBeNull();
  });
});

describe("el corte de Tierra", () => {
  it("es la ultima lectura de a bordo menos el tiempo de luz de ida", () => {
    const cut = groundCut("2026-12-10T23:00:00+00:00", 11.5);
    expect(cut?.toISOString()).toBe("2026-12-10T22:48:30.000Z");
  });

  it("no existe sin efemerides: no hay retardo que aplicar", () => {
    expect(groundCut("2026-12-10T23:00:00+00:00", null)).toBeNull();
  });

  it("nunca es posterior a lo que hay a bordo", () => {
    const reference = "2026-12-10T23:00:00+00:00";
    for (const minutes of [0, 3.1, 22.4]) {
      expect(groundCut(reference, minutes)!.getTime()).toBeLessThanOrEqual(Date.parse(reference));
    }
  });

  it("un instante ilegible falla en vez de dar un corte inventado", () => {
    expect(() => groundCut("ayer", 11)).toThrow(RangeError);
    expect(() => groundCut(Number.NaN, 11)).toThrow(RangeError);
  });

  it("es el mismo que la consola de Tierra calculaba en segundos de misión (§5.37.17)", () => {
    // Lo que hacían a mano el hábitat, la línea base y los documentos de Tierra:
    // `mission.start + (MET de la última lectura - tiempo de luz)`.
    const start = "2026-11-01";
    for (const [reference, minutes] of [
      ["2026-12-10T23:00:00+00:00", 11.5],
      ["2026-12-10T23:00:00+00:00", 12.483],
      ["2026-11-01T05:00:00+00:00", 0],
      ["2027-03-02T14:00:00+00:00", 22.4],
    ] as const) {
      const onboardUntil = missionElapsedSeconds(start, new Date(reference));
      const byHand = new Date(Date.parse(start) + (onboardUntil - minutes * 60) * 1000);
      expect(groundCut(reference, minutes)?.toISOString()).toBe(byHand.toISOString());
    }
  });

  it("acepta el reloj en milisegundos: es el corte de lo que viaja al firmarse", () => {
    const now = Date.parse("2026-10-23T12:00:00Z");
    expect(groundCut(now, 20)?.toISOString()).toBe("2026-10-23T11:40:00.000Z");
    expect(arrivalCut(20, now)?.toISOString()).toBe("2026-10-23T11:40:00.000Z");
    // Sin efemérides las rutas no llevan `until`: `undefined`, no `null`.
    expect(arrivalCut(null, now)).toBeUndefined();
  });
});

describe("la clave de refresco de las cinco preguntas", () => {
  const status = (over: Partial<Record<string, unknown>> = {}) =>
    ({
      data: { reference_time: "2026-12-10T23:00:00+00:00", observations: 120 },
      alerts: [{ acknowledged: true }, { acknowledged: false }],
      followups: [{}],
      recommendations: [{ decision: { kind: "accepted" } }, { decision: null }, {}],
      mission: { sources: ["simulation:nominal"] },
      ...over,
    }) as unknown as CrewStatus;

  it("en tripulación, sin corte; en Tierra, con el día (UTC) del corte delante", () => {
    expect(twinsRefreshKey(status())).toBe("|2026-12-10T23:00:00+00:00|120|1|1|1|simulation:nominal");
    const cut = new Date("2026-12-10T22:48:30Z");
    expect(twinsRefreshKey(status(), cut)).toBe("2026-12-10|2026-12-10T23:00:00+00:00|120|1|1|1|simulation:nominal");
  });

  it("no cambia con un corte del mismo día, y sí al pasar la medianoche UTC", () => {
    const early = new Date("2026-12-10T22:48:30Z");
    const later = new Date("2026-12-10T22:48:31.234Z");
    expect(twinsRefreshKey(status(), later)).toBe(twinsRefreshKey(status(), early));
    expect(twinsRefreshKey(status(), new Date("2026-12-11T00:00:01Z"))).not.toBe(twinsRefreshKey(status(), early));
  });

  it("cambia con cada cosa que cambia las respuestas, también con las fuentes", () => {
    const base = twinsRefreshKey(status());
    expect(twinsRefreshKey(status({ data: { reference_time: "2026-12-11T00:00:00+00:00", observations: 120 } }))).not.toBe(base);
    expect(twinsRefreshKey(status({ data: { reference_time: "2026-12-10T23:00:00+00:00", observations: 121 } }))).not.toBe(base);
    expect(twinsRefreshKey(status({ alerts: [{ acknowledged: true }, { acknowledged: true }] }))).not.toBe(base);
    expect(twinsRefreshKey(status({ followups: [] }))).not.toBe(base);
    expect(twinsRefreshKey(status({ recommendations: [] }))).not.toBe(base);
    expect(twinsRefreshKey(status({ mission: { sources: ["simulation:co2-fatigue"] } }))).not.toBe(base);
  });
});

describe("la clave de refresco de la línea base (§5.38.12)", () => {
  const status = (over: Partial<Record<string, unknown>> = {}) =>
    ({
      data: { reference_time: "2026-12-10T23:00:00+00:00", observations: 120 },
      alerts: [{ acknowledged: true }],
      followups: [{}],
      recommendations: [{ decision: null }],
      mission: { sources: ["simulation:nominal", "wearable:ble"] },
      ...over,
    }) as unknown as CrewStatus;
  const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

  it("es la que cada consola escribía a mano: última lectura, número de lecturas y fuentes", () => {
    expect(baselineRefreshKey(status())).toBe("2026-12-10T23:00:00+00:00|120|simulation:nominal,wearable:ble");
  });

  it("cambia con las lecturas y las fuentes, no con reconocimientos, seguimientos ni decisiones", () => {
    const base = baselineRefreshKey(status());
    expect(baselineRefreshKey(status({ data: { reference_time: "2026-12-11T00:00:00+00:00", observations: 120 } }))).not.toBe(base);
    expect(baselineRefreshKey(status({ data: { reference_time: "2026-12-10T23:00:00+00:00", observations: 121 } }))).not.toBe(base);
    expect(baselineRefreshKey(status({ mission: { sources: ["simulation:co2-fatigue"] } }))).not.toBe(base);
    expect(baselineRefreshKey(status({ alerts: [], followups: [], recommendations: [] }))).toBe(base);
  });

  it("las dos consolas la usan, sin escribirla a mano", () => {
    const ground = read("../ground/GroundConsole.tsx");
    const crew = read("../dashboard/CrewConsole.tsx");
    expect(ground).toContain("refreshKey={baselineRefreshKey(received)}");
    expect(crew).toContain("refreshKey={baselineRefreshKey(status)}");
    for (const source of [ground, crew]) {
      expect(source).not.toMatch(/<BaselineProfilePanel[^>]*refreshKey=\{`/);
    }
  });
});
