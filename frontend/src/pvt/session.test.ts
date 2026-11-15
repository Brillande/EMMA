import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { PvtProtocol, PvtSessionSpec } from "../lib/api";
import {
  type Clock,
  type Snapshot,
  createSession,
  foreperiod,
  operatorName,
  resultRows,
  running,
  submission,
  usable,
} from "./session";

/**
 * Reloj falso: el tiempo solo avanza cuando la prueba lo dice, y los temporizadores vencen
 * en orden. Así se comprueba al milisegundo qué tiempo se anota y qué se envía.
 */
class FakeClock implements Clock {
  time = 1000;
  private next = 1;
  private timers = new Map<number, { at: number; run: () => void }>();

  now = () => this.time;
  setTimer = (run: () => void, afterMs: number) => {
    const handle = this.next++;
    this.timers.set(handle, { at: this.time + afterMs, run });
    return handle;
  };
  clearTimer = (handle: unknown) => {
    this.timers.delete(handle as number);
  };

  get pending(): number {
    return this.timers.size;
  }

  advance(ms: number): void {
    const target = this.time + ms;
    for (;;) {
      const due = [...this.timers.entries()]
        .filter(([, timer]) => timer.at <= target)
        .sort((a, b) => a[1].at - b[1].at)[0];
      if (due === undefined) break;
      this.timers.delete(due[0]);
      this.time = due[1].at;
      due[1].run();
    }
    this.time = target;
  }
}

const spec: PvtSessionSpec = {
  trials: 3,
  foreperiod_min_ms: 2000,
  foreperiod_max_ms: 10000,
  premature_response_ms: 0,
  abandon_after_ms: 10000,
};

function begin(over: Partial<PvtSessionSpec> = {}, random: () => number = () => 0) {
  const clock = new FakeClock();
  const seen: Snapshot[] = [];
  const session = createSession({ ...spec, ...over }, clock, random, (s) => seen.push(s));
  return { clock, seen, session };
}

describe("espera antes del estímulo", () => {
  it("cae entre los dos extremos que da el backend", () => {
    expect(foreperiod(spec, () => 0)).toBe(2000);
    expect(foreperiod(spec, () => 0.5)).toBe(6000);
    expect(foreperiod(spec, () => 1)).toBe(10000);
  });

  it("un sorteo fuera de 0-1 no saca la espera de los extremos", () => {
    expect(foreperiod(spec, () => -3)).toBe(2000);
    expect(foreperiod(spec, () => 7)).toBe(10000);
  });

  it("la marca no aparece antes de la espera sorteada", () => {
    const { clock, session } = begin({}, () => 0.5);
    session.start();
    expect(session.snapshot().phase).toBe("waiting");
    clock.advance(5999);
    expect(session.snapshot().phase).toBe("waiting");
    clock.advance(1);
    expect(session.snapshot().phase).toBe("stimulus");
  });
});

describe("qué tiempo se anota", () => {
  it("el que pasa entre la marca y la respuesta, con el reloj inyectado", () => {
    const { clock, session } = begin();
    session.start();
    clock.advance(2000);
    clock.advance(312.5);
    session.respond();
    expect(session.snapshot().times).toEqual([312.5]);
    expect(session.snapshot().done).toBe(1);
    expect(session.snapshot().phase).toBe("waiting");
  });

  it("no se puntúa aquí: una respuesta lenta o muy rápida se anota tal cual", () => {
    const { clock, session } = begin();
    session.start();
    clock.advance(2000);
    clock.advance(40);
    session.respond();
    clock.advance(2000);
    clock.advance(4321);
    session.respond();
    expect(session.snapshot().times).toEqual([40, 4321]);
  });

  it("una respuesta antes de la marca se anota como dice el backend y cierra ese estímulo", () => {
    const { clock, session } = begin({ premature_response_ms: 0 });
    session.start();
    clock.advance(500);
    session.respond();
    const after = session.snapshot();
    expect(after.times).toEqual([0]);
    expect(after.premature).toBe(true);
    expect(after.phase).toBe("waiting");
    // La marca que estaba programada ya no aparece: se sortea una espera nueva entera.
    clock.advance(1999);
    expect(session.snapshot().phase).toBe("waiting");
    clock.advance(1);
    expect(session.snapshot().phase).toBe("stimulus");
    expect(session.snapshot().premature).toBe(false);
  });

  it("el valor de una respuesta prematura no lo decide este fichero", () => {
    const { clock, session } = begin({ premature_response_ms: 7 });
    session.start();
    clock.advance(10);
    session.respond();
    expect(session.snapshot().times).toEqual([7]);
  });

  it("una segunda pulsación tras responder cuenta para el estímulo siguiente, no para el mismo", () => {
    const { clock, session } = begin();
    session.start();
    clock.advance(2000);
    clock.advance(300);
    session.respond();
    session.respond();
    expect(session.snapshot().times).toEqual([300, 0]);
  });
});

describe("fin de la prueba", () => {
  it("acaba al cerrar el último estímulo y no quedan temporizadores", () => {
    const { clock, session, seen } = begin();
    session.start();
    for (const rt of [250, 260, 270]) {
      clock.advance(2000);
      clock.advance(rt);
      session.respond();
    }
    const end = session.snapshot();
    expect(end.phase).toBe("finished");
    expect(end.times).toEqual([250, 260, 270]);
    expect(clock.pending).toBe(0);
    expect(seen.at(-1)?.phase).toBe("finished");
    // Lo que venga después no añade nada.
    session.respond();
    clock.advance(60_000);
    expect(session.snapshot().times).toEqual([250, 260, 270]);
    expect(session.snapshot().phase).toBe("finished");
  });

  it("se envía un tiempo por estímulo, el tripulante, quién teclea y ninguna hora", () => {
    const { clock, session } = begin();
    session.start();
    for (const rt of [250, 620, 270]) {
      clock.advance(2000);
      clock.advance(rt);
      session.respond();
    }
    const body = submission(session.snapshot(), "crew-02", "  CDR ");
    expect(body).toEqual({
      reaction_times_ms: [250, 620, 270],
      subject: "crew-02",
      recorded_by: "CDR",
    });
    expect(Object.keys(body ?? {})).toEqual(["reaction_times_ms", "subject", "recorded_by"]);
  });

  it("sin tripulante no hay cuerpo que enviar", () => {
    const done: Snapshot = {
      phase: "finished", total: 2, done: 2, premature: false, abandoned: null, times: [1, 2],
    };
    expect(submission(done, "", "CDR")).toBeNull();
    expect(submission({ ...done, times: [1] }, "crew-01", "CDR")).toBeNull();
  });

  it("sin el nombre de quien está en la consola no hay cuerpo que enviar", () => {
    const done: Snapshot = {
      phase: "finished", total: 2, done: 2, premature: false, abandoned: null, times: [1, 2],
    };
    for (const nobody of ["", "   ", "—", "..."]) {
      expect(submission(done, "crew-01", nobody)).toBeNull();
      expect(operatorName(nobody)).toBeNull();
    }
    expect(submission(done, "crew-01", "CDR")?.recorded_by).toBe("CDR");
  });
});

describe("abandonar", () => {
  it("a medias: se tiran los tiempos, se paran los temporizadores y no hay nada que enviar", () => {
    const { clock, session } = begin();
    session.start();
    clock.advance(2000);
    clock.advance(300);
    session.respond();
    expect(submission(session.snapshot(), "crew-01", "CDR")).toBeNull();
    session.abandon();
    const after = session.snapshot();
    expect(after.phase).toBe("abandoned");
    expect(after.abandoned).toBe("user");
    expect(after.times).toEqual([]);
    expect(clock.pending).toBe(0);
    expect(submission(after, "crew-01", "CDR")).toBeNull();
    // Y no revive: ni con el tiempo ni con una pulsación.
    clock.advance(60_000);
    session.respond();
    expect(session.snapshot().phase).toBe("abandoned");
    expect(session.snapshot().times).toEqual([]);
  });

  it("con la marca en pantalla también", () => {
    const { clock, session } = begin();
    session.start();
    clock.advance(2000);
    expect(session.snapshot().phase).toBe("stimulus");
    session.abandon();
    expect(session.snapshot().phase).toBe("abandoned");
    expect(clock.pending).toBe(0);
  });

  it("sin respuesta en el tiempo máximo se abandona sola: no se inventa un tiempo", () => {
    const { clock, session } = begin();
    session.start();
    clock.advance(2000);
    clock.advance(300);
    session.respond();
    clock.advance(2000);
    clock.advance(9999);
    expect(session.snapshot().phase).toBe("stimulus");
    clock.advance(1);
    const after = session.snapshot();
    expect(after.phase).toBe("abandoned");
    expect(after.abandoned).toBe("no-response");
    expect(after.times).toEqual([]);
    expect(submission(after, "crew-01", "CDR")).toBeNull();
    expect(clock.pending).toBe(0);
  });

  it("una pulsación que llega pasado el tiempo máximo no se anota aunque el temporizador se retrase", () => {
    const { clock, session } = begin();
    session.start();
    clock.advance(2000);
    // El temporizador del navegador vence tarde: el reloj ya pasó el tope y aún no saltó.
    clock.time += 10_000;
    session.respond();
    const after = session.snapshot();
    expect(after.phase).toBe("abandoned");
    expect(after.abandoned).toBe("no-response");
    expect(after.times).toEqual([]);
    expect(clock.pending).toBe(0);
  });

  it("una prueba acabada no se puede abandonar: ya es lo que se envía", () => {
    const { clock, session } = begin({ trials: 1 });
    session.start();
    clock.advance(2000);
    clock.advance(280);
    session.respond();
    session.abandon();
    expect(session.snapshot().phase).toBe("finished");
    expect(submission(session.snapshot(), "crew-01", "CDR")?.reaction_times_ms).toEqual([280]);
  });

  it("empezar de nuevo tras abandonar parte de cero", () => {
    const { clock, session } = begin();
    session.start();
    clock.advance(100);
    session.respond();
    session.abandon();
    session.start();
    const again = session.snapshot();
    expect(again.phase).toBe("waiting");
    expect(again.abandoned).toBeNull();
    expect(again.times).toEqual([]);
    expect(again.premature).toBe(false);
    expect(clock.pending).toBe(1);
  });

  it("desmontar para los temporizadores", () => {
    const { clock, session } = begin();
    session.start();
    session.dispose();
    expect(clock.pending).toBe(0);
  });
});

describe("antes de empezar", () => {
  it("una pulsación o un abandono sin prueba en curso no hacen nada", () => {
    const { session, seen } = begin();
    session.respond();
    session.abandon();
    expect(session.snapshot().phase).toBe("idle");
    expect(seen).toEqual([]);
    expect(running(session.snapshot())).toBe(false);
  });

  it("con cifras que no sirven no se empieza", () => {
    expect(usable(spec)).toBe(true);
    for (const bad of [
      { trials: 0 },
      { trials: 2.5 },
      { foreperiod_min_ms: 0 },
      { foreperiod_max_ms: 1000 },
      { abandon_after_ms: 0 },
      { premature_response_ms: Number.NaN },
    ]) {
      expect(usable({ ...spec, ...bad }), JSON.stringify(bad)).toBe(false);
      expect(() => createSession({ ...spec, ...bad }, new FakeClock(), () => 0, () => undefined))
        .toThrow(RangeError);
    }
  });
});

describe("resultado", () => {
  const protocol = {
    result_fields: [
      { key: "mean_rt_ms", display: "MEDIA", unit_display: "ms", decimals: 0, recorded_as: "pvt-mean-rt" },
      { key: "lapses", display: "LAPSOS", unit_display: "", decimals: 0, recorded_as: "pvt-lapses" },
      { key: "ausente", display: "AUSENTE", unit_display: "", decimals: 0, recorded_as: null },
    ],
  } as unknown as PvtProtocol;

  it("pinta lo que devolvió el backend, con sus nombres y sin calcular nada", () => {
    const rows = resultRows(protocol, {
      result: { mean_rt_ms: 12345.6, lapses: 2, lapse_rate: 0.1 },
      recorded: [4, 5],
    });
    expect(rows).toEqual([
      { key: "mean_rt_ms", display: "MEDIA", text: "12 346 ms", recordedAs: "pvt-mean-rt" },
      { key: "lapses", display: "LAPSOS", text: "2", recordedAs: "pvt-lapses" },
    ]);
  });
});

describe("este fichero no puntúa ni trae cifras propias", () => {
  const source = readFileSync(fileURLToPath(new URL("./session.ts", import.meta.url)), "utf8");
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  it("no conoce el umbral de lapso ni el de salida en falso", () => {
    expect(code).not.toMatch(/\b(500|100|10000|2000|20)\b/);
    for (const word of ["lapse", "false_start", "mean", "median"]) {
      expect(code).not.toContain(word);
    }
  });

  it("no usa el reloj del sistema: solo el que se le pasa", () => {
    expect(code).not.toMatch(/performance\.|Date\.now|setTimeout|Math\.random/);
  });
});
