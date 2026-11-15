import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ARRIVAL_CHECK_MS, arrivalCheckKey, createArrivalClock, onceRequest } from "./arrival";

/**
 * Lo que viaja al firmarse en la consola de Tierra (§5.37.17, §5.38.12): un solo temporizador y un
 * solo corte para las ecografías, el dolor y el historial, y ninguno vuelve a pedir porque el
 * tiempo de luz cambie unas centésimas. El efecto no se ejecuta en estas pruebas (no hay DOM): se
 * prueba el reloj con temporizadores falsos, la clave que dispara el efecto y que los tres paneles
 * la usan.
 */

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

const PANELS = {
  ecografías: "../imaging/ImagingHistory.tsx",
  dolor: "../pain/PainHistory.tsx",
  historial: "../ground/MissionHistoryPanel.tsx",
};

describe("cuándo se vuelve a mirar si ha llegado algo", () => {
  it("cada 30 s", () => {
    expect(ARRIVAL_CHECK_MS).toBe(30_000);
  });

  it("no cambia con unas centésimas del tiempo de luz", () => {
    expect(arrivalCheckKey(12.48, 3)).toBe(arrivalCheckKey(12.49, 3));
    expect(arrivalCheckKey(0, 3)).toBe(arrivalCheckKey(22.4, 3));
  });

  it("cambia con cada vuelta del temporizador y al llegar o perderse las efemérides", () => {
    expect(arrivalCheckKey(12.48, 3)).not.toBe(arrivalCheckKey(12.48, 4));
    expect(arrivalCheckKey(12.48, 3)).not.toBe(arrivalCheckKey(null, 3));
  });
});

describe("un solo reloj para los tres paneles (§5.38.12)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-26T12:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("un temporizador para todos los que escuchan, y ninguno sin nadie", () => {
    const clock = createArrivalClock();
    expect(vi.getTimerCount()).toBe(0);
    const stops = [clock.subscribe(() => {}), clock.subscribe(() => {}), clock.subscribe(() => {})];
    expect(vi.getTimerCount()).toBe(1);
    stops[0]?.();
    stops[1]?.();
    expect(vi.getTimerCount()).toBe(1);
    stops[2]?.();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cada vuelta avisa a todos con la misma cuenta", () => {
    const clock = createArrivalClock();
    const seen: number[] = [];
    // Dos paneles: dos oyentes distintos.
    const stopA = clock.subscribe(() => seen.push(clock.turns()));
    const stopB = clock.subscribe(() => seen.push(clock.turns()));
    vi.advanceTimersByTime(ARRIVAL_CHECK_MS - 1);
    expect(seen).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(seen).toEqual([1, 1]);
    vi.advanceTimersByTime(ARRIVAL_CHECK_MS);
    expect(seen).toEqual([1, 1, 2, 2]);
    stopA();
    stopB();
  });

  it("lo que se pide en la misma tanda corta en el mismo instante, y la siguiente con el de ahora", async () => {
    const clock = createArrivalClock();
    const first = clock.instant();
    expect(first).toBe(Date.parse("2026-10-26T12:00:00Z"));
    // Los efectos de un pintado van seguidos: aunque el reloj avance entre uno y otro, el mismo.
    vi.setSystemTime(new Date("2026-10-26T12:00:00.250Z"));
    expect(clock.instant()).toBe(first);
    // Otra tanda (otra vuelta, otro tripulante entre vueltas): el instante de ahora, no uno viejo.
    await Promise.resolve();
    vi.setSystemTime(new Date("2026-10-26T12:00:29Z"));
    expect(clock.instant()).toBe(Date.parse("2026-10-26T12:00:29Z"));
  });

  it("parado y vuelto a arrancar, no cambia la cuenta: quien ya pintó no vuelve a pedir", () => {
    const clock = createArrivalClock();
    const stop = clock.subscribe(() => {});
    vi.advanceTimersByTime(ARRIVAL_CHECK_MS);
    stop();
    vi.advanceTimersByTime(5 * 60_000);
    const turns = clock.turns();
    const again = clock.subscribe(() => {});
    expect(clock.turns()).toBe(turns);
    vi.advanceTimersByTime(ARRIVAL_CHECK_MS);
    expect(clock.turns()).toBe(turns + 1);
    again();
  });
});

describe("los tres paneles de lo que llega a Tierra", () => {
  for (const [name, path] of Object.entries(PANELS)) {
    it(`${name}: el corte de \`useArrivalCheck\`, sin pedir por el tiempo de luz`, () => {
      const source = read(path);
      expect(source).toContain("const { checkKey, cutNow } = useArrivalCheck(oneWayMinutes);");
      expect(source).toMatch(/\}, \[subject, checkKey, cutNow(?:, \w+)?\]\);/);
      // Ni su propio temporizador ni su propia cuenta del corte, ni su propio reloj (§5.38.12).
      expect(source).not.toMatch(/setInterval|setTimeout|ARRIVAL_CHECK_MS|createArrivalClock|Date\.now|\* 60_000/);
      // Lo pintado es del tripulante que se mira: lo cargado y lo fallido llevan su tripulante.
      expect(source).toMatch(/loaded\?\.subject === subject \?/);
      expect(source).toMatch(/failed\?\.subject === subject \? failed\.outcome : null/);
    });
  }
});

describe("lo fijo se pide una vez, no en cada vuelta (§5.38.12)", () => {
  it("una petición que sale bien se reutiliza; una que falla se reintenta", async () => {
    let calls = 0;
    const ok = onceRequest(() => {
      calls += 1;
      return Promise.resolve({ protocols: [] });
    });
    const first = await ok();
    expect(await ok()).toBe(first);
    expect(calls).toBe(1);

    let attempts = 0;
    const flaky = onceRequest(() => {
      attempts += 1;
      return attempts === 1 ? Promise.reject(new Error("sin red")) : Promise.resolve("catálogo");
    });
    await expect(flaky()).rejects.toThrow("sin red");
    expect(await flaky()).toBe("catálogo");
    expect(await flaky()).toBe("catálogo");
    expect(attempts).toBe(2);

    // Una que no vuelve no se queda: la vuelta siguiente pide otra, y la que sale bien se guarda.
    let tries = 0;
    const hung = onceRequest(() => {
      tries += 1;
      return tries === 1 ? new Promise<string>(() => {}) : Promise.resolve("catálogo");
    });
    void hung();
    expect(await hung()).toBe("catálogo");
    expect(await hung()).toBe("catálogo");
    expect(tries).toBe(2);
  });

  it("ecografías: los protocolos y los indicadores, fuera del efecto que corta", () => {
    const source = read(PANELS.ecografías);
    expect(source).toContain("const catalogs = useFixedRequest(loadCatalogs);");
    expect(source).toContain("Promise.all([catalogs(), api.imaging.studies(subject, cutoff)])");
    expect(source.match(/api\.imaging\.protocols\(\)|api\.indicators\(\)/g)).toHaveLength(2);
    expect(source).toMatch(/const loadCatalogs = \(\) =>\s+Promise\.all\(\[api\.imaging\.protocols\(\), api\.indicators\(\)\]\)/);
  });

  it("dolor: el catálogo de zonas", () => {
    const source = read(PANELS.dolor);
    expect(source).toContain("useFixedRequest(api.pain.catalog)");
    expect(source).not.toContain("api.pain.catalog()");
  });
});

describe("la consola de Tierra calcula su corte una sola vez", () => {
  it("con `groundCut`, sin rehacerlo en segundos de misión", () => {
    const source = read("../ground/GroundConsole.tsx");
    expect(source.match(/groundCut\(/g)).toHaveLength(1);
    expect(source).not.toContain("Date.parse(status.mission.start)");
    expect(source).not.toMatch(/onboardUntil - oneWay/);
  });
});
