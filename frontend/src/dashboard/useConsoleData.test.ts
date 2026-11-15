import { describe, expect, it } from "vitest";

import { ApiError, type CrewStatus, type LinkSync } from "../lib/api";
import { FAILURE_MARK, REFUSED_MARK } from "../lib/marks";
import {
  LIVE_REFRESH_MS,
  LIVE_WINDOW_MS,
  type Load,
  REFRESH_MS,
  cutOf,
  dataKeyOf,
  isLive,
  lightCutOf,
  loadOfFailure,
  receivedStatus,
  refreshPeriod,
} from "./useConsoleData";

/** Un estado de a bordo con lo que leen las funciones puras: referencia, retardo, fuentes y recuento. */
function onboard(over: { oneWay?: number | null; sources?: string[]; observations?: number } = {}): CrewStatus {
  return {
    subject: "crew-02",
    comms: over.oneWay === undefined || over.oneWay === null ? null : { one_way_minutes: over.oneWay },
    data: { reference_time: "2026-11-07T12:00:00+00:00", observations: over.observations ?? 480 },
    mission: { sources: over.sources ?? ["simulator:nominal"] },
  } as unknown as CrewStatus;
}

describe("el corte de Tierra", () => {
  it("sin efemérides no hay corte: Tierra ve lo mismo que a bordo", () => {
    expect(lightCutOf(onboard())).toBeNull();
  });

  it("es la última lectura menos el tiempo de luz", () => {
    expect(lightCutOf(onboard({ oneWay: 12.5 }))?.toISOString()).toBe("2026-11-07T11:47:30.000Z");
  });

  it("un enlace caído lo retiene en la caída, nunca más tarde", () => {
    const sync = { cut: "2026-11-07T10:00:00+00:00", held: true, held_since: "2026-11-07T10:00:00+00:00" } as unknown as LinkSync;
    expect(cutOf(onboard({ oneWay: 12.5 }), sync)?.toISOString()).toBe("2026-11-07T10:00:00.000Z");
  });
});

describe("la clave de lo que hay en el almacén", () => {
  it("cambia con la referencia, el escenario y el número de lecturas", () => {
    const base = dataKeyOf(onboard());
    expect(dataKeyOf(onboard())).toBe(base);
    expect(dataKeyOf(onboard({ sources: ["simulator:spe-event"] }))).not.toBe(base);
    expect(dataKeyOf(onboard({ observations: 481 }))).not.toBe(base);
  });
});

describe("cuando el estado no llega", () => {
  it("un 404 es el almacén vacío, no un fallo", () => {
    expect(loadOfFailure(new ApiError(404, "sin lecturas"))).toEqual({ state: "empty" });
  });

  it("un 422 es una petición rechazada: triángulo amarillo con el motivo del backend", () => {
    const load = loadOfFailure(new ApiError(422, "hasta sin zona horaria"));
    expect(load.state).toBe("error");
    if (load.state !== "error") return;
    expect(load.outcome.mark).toBe(REFUSED_MARK);
    expect(load.outcome.text).toContain("hasta sin zona horaria");
  });

  it("un 500 o la red caída es un fallo: cruz roja", () => {
    const load = loadOfFailure(new ApiError(500, "se cayó"));
    expect(load.state === "error" && load.outcome.mark).toBe(FAILURE_MARK);
    const network = loadOfFailure(new TypeError("Failed to fetch"));
    expect(network.state === "error" && network.outcome.mark).toBe(FAILURE_MARK);
  });
});

describe("el estado que Tierra ya tiene", () => {
  const status = onboard({ oneWay: 20 });

  it("sin corte es el de a bordo, sin pedir nada", async () => {
    let asked = 0;
    const fetchStatus = async () => {
      asked += 1;
      return status;
    };
    expect(await receivedStatus(fetchStatus, status, null)).toBe(status);
    expect(asked).toBe(0);
  });

  it("con corte se pide el del mismo tripulante hasta ese instante", async () => {
    const calls: [Date, string][] = [];
    const received = onboard({ oneWay: 20, observations: 300 });
    const fetchStatus = async (until: Date, subject: string) => {
      calls.push([until, subject]);
      return received;
    };
    const until = new Date("2026-11-07T11:40:00Z");
    expect(await receivedStatus(fetchStatus, status, until)).toBe(received);
    expect(calls).toEqual([[until, "crew-02"]]);
  });

  it("un 404 es «todavía no ha llegado nada», no un fallo", async () => {
    const fetchStatus = async () => {
      throw new ApiError(404, "sin lecturas llegadas");
    };
    expect(await receivedStatus(fetchStatus, status, new Date())).toBeNull();
  });

  it("cualquier otro fallo sube tal cual", async () => {
    const fetchStatus = async () => {
      throw new ApiError(500, "se cayó");
    };
    await expect(receivedStatus(fetchStatus, status, new Date())).rejects.toBeInstanceOf(ApiError);
  });
});

describe("cuándo se lee en vivo", () => {
  // `onboard()` tiene la última lectura el 2026-11-07 a las 12:00 UTC.
  const latest = Date.parse("2026-11-07T12:00:00Z");
  const band = onboard({ sources: ["wearable-ble"] });

  it("una banda de pulso con lectura de hace segundos está en vivo", () => {
    expect(isLive(band, latest + 3_000)).toBe(true);
    expect(isLive(band, latest + LIVE_WINDOW_MS)).toBe(true);
  });

  it("una banda quieta más de la ventana ya no lo está", () => {
    expect(isLive(band, latest + LIVE_WINDOW_MS + 1)).toBe(false);
  });

  it("una fuente por lotes no lo está aunque su última lectura sea de ahora", () => {
    expect(isLive(onboard({ sources: ["simulator:nominal"] }), latest + 1_000)).toBe(false);
    expect(isLive(onboard({ sources: ["apple-health"] }), latest + 1_000)).toBe(false);
  });

  it("con varias fuentes basta con que una sea de tiempo real", () => {
    expect(isLive(onboard({ sources: ["apple-health", "wearable-ble"] }), latest + 1_000)).toBe(true);
  });

  it("una referencia muy en el futuro no es vivo; unos segundos de desfase del reloj sí", () => {
    expect(isLive(band, latest - 10_000)).toBe(true);
    expect(isLive(band, latest - 10 * 60_000)).toBe(false);
  });

  it("el periodo de relectura: 5 s en vivo, 30 s en lo demás", () => {
    const ready = (status: CrewStatus): Load => ({
      state: "ready",
      onboard: status,
      received: status,
      sync: {} as LinkSync,
    });
    expect(refreshPeriod(ready(band), latest + 1_000)).toBe(LIVE_REFRESH_MS);
    expect(refreshPeriod(ready(band), latest + 60 * 60_000)).toBe(REFRESH_MS);
    expect(refreshPeriod({ state: "loading" }, latest)).toBe(REFRESH_MS);
    expect(LIVE_REFRESH_MS).toBeLessThan(REFRESH_MS);
  });
});

describe("la clave de las series en vivo", () => {
  it("cambia con una lectura nueva aunque la referencia sea la misma", () => {
    expect(dataKeyOf(onboard({ observations: 10 }))).not.toBe(dataKeyOf(onboard({ observations: 11 })));
  });
});
