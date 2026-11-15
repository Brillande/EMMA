import { describe, expect, it } from "vitest";

import type { SafeModeState } from "../lib/api";
import { networkSync } from "./SafeMode";

/*
 * Qué respuesta gana entre relecturas y cambios del modo seguro. Cada petición devuelve una promesa
 * que la prueba resuelve cuando quiere: así se fuerza el orden de llegada que en la consola depende
 * de la red. La carrera de §5.35.12: una relectura que sale después de activar y vuelve antes que la
 * respuesta de la activación ganaba y enseñaba el estado viejo. Desde §5.38.13 el estado lleva su
 * versión y la época de su almacén, y gana lo más nuevo; abajo, además de los casos sueltos, todas
 * las órdenes de aplicación y de llegada de varias tandas de cambios y relecturas.
 */

const closed: SafeModeState = {
  active: false,
  reason: null,
  declared_by: null,
  since: null,
  version: 0,
  store_epoch: 100,
  halt: { active: false, file: "estado/.HALT", since: null, notice: null },
};
const safe: SafeModeState = { ...closed, active: true, reason: "motivo", declared_by: "quien", version: 1 };
const lifted: SafeModeState = { ...closed, declared_by: "quien", version: 2 };
const braked: SafeModeState = { ...safe, halt: { ...safe.halt, active: true } };

interface Pending {
  resolve: (state: SafeModeState) => void;
  reject: (reason: unknown) => void;
}

/** La sincronía con peticiones que la prueba contesta; `stale` es lo que pintaría la franja. */
function harness() {
  const reads: Pending[] = [];
  const writes: Pending[] = [];
  const shown: SafeModeState[] = [];
  const view = { stale: false, marked: 0 };
  const sync = networkSync(
    () => new Promise((resolve, reject) => reads.push({ resolve, reject })),
    () => new Promise((resolve, reject) => writes.push({ resolve, reject })),
    (state) => {
      shown.push(state);
      view.stale = false;
    },
    () => {
      view.stale = true;
      view.marked += 1;
    },
    () => {
      view.stale = false;
    },
  );
  return { sync, reads, writes, shown, view };
}

/** Deja correr todo lo pendiente: `setImmediate` va detrás de toda la cola de microtareas. */
const settle = () => new Promise((resolve) => setImmediate(resolve));

const body = { active: true, reason: "motivo", declared_by: "quien" };

describe("relecturas y cambios del modo seguro: gana lo más nuevo", () => {
  it("una relectura que sale tras activar y vuelve antes que la activación no la pisa", async () => {
    const { sync, reads, writes, shown } = harness();
    const applied = sync.apply(body);
    sync.load();
    reads[0]!.resolve(closed); // el servidor la contestó antes de firmar el cambio: era el estado
    await settle();
    writes[0]!.resolve(safe);
    await applied;
    expect(shown).toEqual([closed, safe]);
  });

  it("una relectura vieja que vuelve después de la activación no la pisa", async () => {
    const { sync, reads, writes, shown } = harness();
    sync.load();
    const applied = sync.apply(body);
    writes[0]!.resolve(safe);
    await applied;
    reads[0]!.resolve(closed);
    await settle();
    expect(shown).toEqual([safe]);
  });

  it("una relectura con la misma versión, pedida la última, sí se enseña (un freno puesto luego)", async () => {
    const { sync, reads, writes, shown } = harness();
    const applied = sync.apply(body);
    writes[0]!.resolve(safe);
    await applied;
    sync.load();
    reads[0]!.resolve(braked);
    await settle();
    expect(shown).toEqual([safe, braked]);
  });

  it("dos cambios cruzados: gana el que el servidor firmó después, y no se relee", async () => {
    const { sync, reads, writes, shown } = harness();
    const first = sync.apply(body);
    const second = sync.apply({ ...body, active: false });
    // El servidor firmó el segundo primero (versión 1) y el primero después (versión 2): la
    // respuesta del segundo llega antes, la del primero después, y es la del primero la que vale.
    const second1 = { ...closed, version: 1 };
    const first2 = { ...safe, version: 2 };
    writes[1]!.resolve(second1);
    await second;
    writes[0]!.resolve(first2);
    await first;
    expect(shown).toEqual([second1, first2]);
    expect(reads).toHaveLength(0);
  });

  it("dos cambios cruzados al revés: la respuesta vieja que llega tarde no pisa la nueva", async () => {
    const { sync, reads, writes, shown } = harness();
    const first = sync.apply(body);
    const second = sync.apply({ ...body, active: false });
    writes[1]!.resolve(lifted);
    await second;
    writes[0]!.resolve(safe);
    await first;
    expect(shown).toEqual([lifted]);
    expect(reads).toHaveLength(0);
  });

  it("un solo cambio que sale bien no relee: su respuesta es el estado", async () => {
    const { sync, reads, writes, shown } = harness();
    const applied = sync.apply(body);
    writes[0]!.resolve(safe);
    await applied;
    expect(shown).toEqual([safe]);
    expect(reads).toHaveLength(0);
  });

  it("si el último cambio falla con otro aún en vuelo, se relee al acabar ese otro", async () => {
    const { sync, reads, writes, shown } = harness();
    const first = sync.apply(body);
    const second = sync.apply(body);
    writes[1]!.reject(new Error("rechazado"));
    await expect(second).rejects.toThrow("rechazado");
    expect(reads).toHaveLength(0); // aún va el primero: releer ahora no diría su versión
    writes[0]!.resolve(safe);
    await first;
    expect(shown).toEqual([safe]); // su versión es la más alta vista: se enseña…
    expect(reads).toHaveLength(1); // …y, como uno falló (pudo firmarse), se relee
    reads[0]!.resolve(braked);
    await settle();
    expect(shown).toEqual([safe, braked]); // la misma versión, de la última relectura: refresca el freno
  });

  it("el fallo de un cambio que otro pedido después dejó viejo no se lanza", async () => {
    const { sync, reads, writes, shown } = harness();
    const first = sync.apply(body);
    const second = sync.apply({ ...body, active: false });
    writes[1]!.resolve(lifted);
    await second;
    writes[0]!.reject(new Error("tarde"));
    await expect(first).resolves.toBeUndefined();
    expect(reads).toHaveLength(1);
    reads[0]!.resolve(lifted);
    await settle();
    expect(shown).toEqual([lifted, lifted]);
  });

  it("un cambio cuya respuesta se pierde pero se firmó: la relectura trae su versión", async () => {
    const { sync, reads, writes, shown } = harness();
    sync.load();
    reads[0]!.resolve(closed);
    await settle();
    const applied = sync.apply(body);
    writes[0]!.reject(new Error("caído")); // el servidor lo firmó; la respuesta no llegó
    await expect(applied).rejects.toThrow("caído");
    expect(reads).toHaveLength(2);
    reads[1]!.resolve(safe);
    await settle();
    expect(shown).toEqual([closed, safe]);
  });

  it("entre relecturas con la misma versión manda la última pedida; con más versión, cualquiera", async () => {
    const { sync, reads, shown, view } = harness();
    sync.load();
    sync.load();
    reads[1]!.resolve(braked);
    reads[0]!.resolve(safe); // la misma versión, pedida antes: no quita el freno que se ve
    await settle();
    expect(shown).toEqual([braked]);
    sync.load();
    sync.load();
    reads[2]!.resolve(lifted); // pedida antes, pero trae una versión más nueva: se enseña
    reads[3]!.resolve(braked); // la última pedida, pero más vieja: no
    await settle();
    expect(shown).toEqual([braked, lifted]);
    expect(view.marked).toBe(0);
  });

  it("otro almacén (escenario nuevo, backend reiniciado): su versión 0 no es vieja", async () => {
    const { sync, reads, writes, shown } = harness();
    sync.load();
    reads[0]!.resolve({ ...lifted, version: 3 });
    await settle();
    const fresh = { ...closed, store_epoch: 200 }; // otro almacén: vuelve a 0
    sync.load();
    reads[1]!.resolve(fresh);
    await settle();
    expect(shown.at(-1)).toEqual(fresh);
    // Lo que se active en él se enseña, aunque su versión (1) sea menor que la 3 de antes.
    const applied = sync.apply(body);
    const activated = { ...safe, store_epoch: 200 };
    writes[0]!.resolve(activated);
    await applied;
    expect(shown.at(-1)).toEqual(activated);
    // Una respuesta tardía del almacén de antes no lo pisa, aunque traiga más versión.
    sync.load();
    sync.load();
    reads[3]!.resolve(activated);
    reads[2]!.resolve({ ...safe, version: 9 }); // salió antes que la última: no manda
    await settle();
    expect(shown.at(-1)).toEqual(activated);
  });

  it("si la última relectura, sin nada en medio, dice un almacén de época menor, es el de hoy", async () => {
    // Un backend reiniciado con el reloj atrasado abre un almacén de época menor: no se queda
    // la franja atascada en el de antes.
    const { sync, reads, shown } = harness();
    sync.load();
    reads[0]!.resolve({ ...safe, version: 4 });
    await settle();
    const restarted = { ...closed, store_epoch: 50 };
    sync.load();
    reads[1]!.resolve(restarted);
    await settle();
    expect(shown.at(-1)).toEqual(restarted);
  });

  it("«sin actualizar»: solo la última relectura, sin cambio en vuelo ni nada llegado desde que salió", async () => {
    const { sync, reads, writes, shown, view } = harness();
    sync.load();
    sync.load();
    reads[1]!.resolve(safe);
    reads[0]!.reject(new Error("tarde")); // vieja: no marca
    await settle();
    expect(view.marked).toBe(0);
    sync.load();
    const applied = sync.apply({ ...body, active: false });
    reads[2]!.reject(new Error("sin red")); // va un cambio: su respuesta lo dirá
    await settle();
    expect(view.marked).toBe(0);
    writes[0]!.resolve(lifted);
    await applied;
    sync.load();
    reads[3]!.reject(new Error("sin red"));
    await settle();
    expect(view).toEqual({ stale: true, marked: 1 });
    expect(shown).toEqual([safe, lifted]);
  });

  it("una respuesta al día con la misma versión quita «sin actualizar» aunque no se enseñe", async () => {
    const { sync, reads, shown, view } = harness();
    sync.load();
    reads[0]!.resolve(safe);
    await settle();
    sync.load();
    sync.load();
    reads[2]!.reject(new Error("sin red")); // la última: marca
    await settle();
    expect(view.stale).toBe(true);
    reads[1]!.resolve(safe); // la de antes vuelve bien, con la misma versión: está al día
    await settle();
    expect(view.stale).toBe(false);
    expect(shown).toEqual([safe]);
  });
});

/*
 * Todas las órdenes. Un servidor de juguete con las reglas del de verdad (`record_safe_mode`:
 * activar con el modo puesto, o levantarlo sin él, es un 409; cada cambio aceptado sube la versión
 * en uno; cambiar de almacén sube la época y vuelve la versión a 0) aplica cada petición en un
 * momento y su respuesta llega en otro, siempre después. La prueba recorre todas las
 * intercalaciones de esos dos momentos para cada petición: el orden en que el servidor las aplica y
 * el orden en que llegan, cruzados de todas las formas posibles. Por tandas: la segunda se pide
 * cuando ha llegado todo lo de la primera, y se cruza con las relecturas que esta dejó pedidas.
 */

type Op =
  | { kind: "read"; lost?: boolean }
  | { kind: "write"; active: boolean | "toggle"; lost?: boolean }
  | { kind: "swap" }; // el servidor cambia de almacén (un escenario nuevo); el cliente no pide nada

/** Cada intercalación: cada petición sale dos veces, la primera se aplica y la segunda llega. */
function* schedules(count: number, done: number[] = [], prefix: number[] = []): Generator<number[]> {
  if (prefix.length === count * 2) {
    yield prefix;
    return;
  }
  for (let op = 0; op < count; op += 1) {
    const seen = done[op] ?? 0;
    if (seen < 2) {
      done[op] = seen + 1;
      yield* schedules(count, done, [...prefix, op]);
      done[op] = seen;
    }
  }
}

interface Server {
  active: boolean;
  version: number;
  store_epoch: number;
}

/** Corre las tandas con un orden cada una; `null` si las relecturas arrastradas no cuadran. */
async function run(phases: Op[][], orders: number[][]) {
  let server: Server = { active: false, version: 0, store_epoch: 100 };
  const snapshot = (): SafeModeState => ({
    ...(server.active ? safe : closed),
    version: server.version,
    store_epoch: server.store_epoch,
  });
  const { sync, reads, writes, shown, view } = harness();
  const thrown: boolean[] = [];
  const expectedThrow: boolean[] = [];
  let failures = 0;
  let lastProcessed: SafeModeState | null = null; // la respuesta buena que el servidor dio la última
  let carried: number[] = []; // relecturas pedidas por la sincronía y sin contestar
  let requestedReads = 0;
  const answered = new Set<number>();
  const readAt = (at: number) => () => {
    answered.add(at);
    return reads[at]!;
  };

  for (const [phase, ops] of phases.entries()) {
    const order = orders[phase]!;
    if (order.length !== (carried.length + ops.length) * 2) return null;
    type Call = { op: Op; pending: () => Pending | null; write?: number };
    const calls: Call[] = carried.map((at) => ({ op: { kind: "read" }, pending: readAt(at) }));
    const phaseWrites: number[] = [];
    for (const op of ops) {
      if (op.kind === "read") {
        const at = reads.length;
        requestedReads += 1;
        sync.load();
        calls.push({ op, pending: readAt(at) });
      } else if (op.kind === "write") {
        const at = writes.length;
        const slot = thrown.length;
        thrown.push(false);
        expectedThrow.push(false);
        phaseWrites.push(slot);
        const active = op.active === "toggle" ? !server.active : op.active;
        sync.apply({ active, reason: "motivo", declared_by: "quien" }).catch(() => {
          thrown[slot] = true;
        });
        calls.push({ op: { ...op, active }, pending: () => writes[at]!, write: slot });
      } else {
        calls.push({ op, pending: () => null });
      }
    }
    const answers: ((pending: Pending | null) => void)[] = [];
    for (const index of order) {
      const call = calls[index]!;
      const answer = answers[index];
      if (answer !== undefined) {
        answer(call.pending());
        await settle();
        continue;
      }
      // El servidor la aplica ahora; la respuesta queda guardada hasta que llegue.
      const op = call.op;
      if (op.kind === "swap") {
        server = { active: false, version: 0, store_epoch: server.store_epoch + 1 };
        answers[index] = () => {};
      } else if (op.kind === "read") {
        const state = snapshot();
        if (op.lost) answers[index] = (pending) => pending!.reject(new Error("sin red"));
        else {
          lastProcessed = state;
          answers[index] = (pending) => pending!.resolve(state);
        }
      } else if (server.active === op.active) {
        failures += 1;
        expectedThrow[call.write!] = call.write === phaseWrites.at(-1);
        answers[index] = (pending) => pending!.reject(new Error("409"));
      } else {
        server = { ...server, active: op.active as boolean, version: server.version + 1 };
        const state = snapshot();
        if (op.lost) {
          failures += 1;
          expectedThrow[call.write!] = call.write === phaseWrites.at(-1);
          answers[index] = (pending) => pending!.reject(new Error("caída"));
        } else {
          lastProcessed = state;
          answers[index] = (pending) => pending!.resolve(state);
        }
      }
    }
    // Las relecturas que pidió la sincronía en esta tanda y siguen sin contestar.
    carried = reads.map((_, at) => at).filter((at) => !answered.has(at));
  }
  // Al final, con el servidor ya quieto, las que queden.
  for (const at of carried) {
    const state = snapshot();
    lastProcessed = state;
    reads[at]!.resolve(state);
    await settle();
  }
  return {
    server,
    shown,
    view,
    thrown,
    expectedThrow,
    failures,
    rereads: reads.length - requestedReads,
    lastProcessed: lastProcessed as SafeModeState | null,
  };
}

/** Los órdenes de cada tanda; desde la segunda, con 0 o 1 relecturas arrastradas de la anterior. */
function* plans(phases: Op[][], at = 0, prefix: number[][] = []): Generator<number[][]> {
  if (at === phases.length) {
    yield prefix;
    return;
  }
  for (const carried of at === 0 ? [0] : [0, 1]) {
    for (const order of schedules(phases[at]!.length + carried)) {
      yield* plans(phases, at + 1, [...prefix, [...order]]);
    }
  }
}

const ON: Op = { kind: "write", active: true };
const OFF: Op = { kind: "write", active: false };
const TOGGLE: Op = { kind: "write", active: "toggle" };
const READ: Op = { kind: "read" };
const SWAP: Op = { kind: "swap" };

const batches: [string, Op[][]][] = [
  ["activar con dos relecturas", [[ON, READ, READ]]],
  ["activar y levantar cruzados con dos relecturas", [[ON, OFF, READ, READ]]],
  ["dos activaciones cruzadas (una es un 409); luego, un cambio que se cruza con la relectura", [[ON, ON, READ], [TOGGLE]]],
  ["activar con la respuesta perdida; luego, un cambio y una relectura cruzados con la de recuperación", [[{ ...ON, lost: true }, READ], [TOGGLE, READ]]],
  ["activar y levantar, la respuesta de levantar perdida", [[ON, { ...OFF, lost: true }, READ]]],
  ["una relectura; luego, otra y la última que falla", [[READ], [READ, { kind: "read", lost: true }]]],
  ["activar mientras el backend cambia de almacén, con dos relecturas", [[ON, SWAP, READ, READ]]],
  ["activar con una relectura; luego, cambio de almacén cruzado con un cambio y una relectura", [[ON, READ], [SWAP, TOGGLE, READ]]],
];

describe("todas las órdenes de aplicación y de llegada", () => {
  for (const [name, phases] of batches) {
    it(name, async () => {
      let runs = 0;
      const swaps = phases.flat().some((op) => op.kind === "swap");
      for (const orders of plans(phases)) {
        const result = await run(phases, orders);
        if (result === null) continue;
        runs += 1;
        const where = `${name}, orden ${orders.map((order) => order.join("")).join(" | ")}`;
        // Nunca se vuelve a algo más viejo que lo que ya se enseñó: ni de almacén ni de versión.
        result.shown.forEach((state, index) => {
          const before = result.shown[index - 1];
          if (before === undefined) return;
          expect(state.store_epoch >= before.store_epoch, where).toBe(true);
          if (state.store_epoch === before.store_epoch) expect(state.version >= before.version, where).toBe(true);
        });
        // Lo último que se ve es la última respuesta buena que dio el servidor…
        const last = result.shown.at(-1);
        const pick = (state: SafeModeState | null | undefined) =>
          state && { active: state.active, version: state.version, store_epoch: state.store_epoch };
        expect(pick(last), where).toEqual(pick(result.lastProcessed));
        // …y, sin cambio de almacén por medio, su estado al acabar.
        if (!swaps) expect(pick(last), where).toEqual(result.server);
        // Sin ningún cambio fallido no hace falta releer: las versiones bastan.
        if (result.failures === 0) expect(result.rereads, where).toBe(0);
        else expect(result.rereads, where).toBeGreaterThan(0);
        // Solo se lanza el fallo del último cambio pedido, y solo si falló.
        expect(result.thrown, where).toEqual(result.expectedThrow);
        // Y lo que se ve al acabar no está marcado «sin actualizar»: algo al día llegó después.
        expect(result.view.stale, where).toBe(false);
      }
      expect(runs).toBeGreaterThan(0);
    });
  }
});
