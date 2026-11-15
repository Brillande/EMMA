import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { VoiceAvailabilityContext } from "../components/ReadAloud";
import { DEFAULT_MODES, parseModes } from "../components/displayModes";
import type { Alert } from "../lib/alerts";
import type { RoutineState, RoutinesView } from "../lib/api";
import { announcementText } from "../lib/announce";
import { type AssistantEvent, emit, listen } from "./bus";
import { ProactiveControls } from "./ProactiveControls";
import {
  DEFAULT_SILENCE_MS,
  GREETING,
  INITIAL_ALERT_MEMORY,
  INITIAL_PACER,
  NOTICE_GAP_MS,
  type Notice,
  PRIORITY_ORDER,
  QUEUE_LIMIT,
  QUEUE_TTL_MS,
  drain,
  enqueue,
  entrySpeech,
  routineNotices,
  silenceFor,
  silencedUntil,
  statusNotices,
  subscribeSilence,
} from "./proactive";

/**
 * La iniciativa propia (`proactive.ts`): diferencias entre sondeos, tope, cola, prioridad, silencio
 * y privacidad. Sin navegador ni red: funciones puras y el marcado con `renderToStaticMarkup`.
 */

const SCOPE = "crew|crew-01";
const T = 1_000_000;

const critical: Alert = { id: "cardiovascular:critical", domain: "cardiovascular", level: "critical", drivers: ["FC 140 lpm"] };
const watch: Alert = { id: "sleep:watch", domain: "sleep", level: "watch", drivers: ["Sueño 5 h"] };

function statusInput(alerts: Alert[], extra: Partial<Parameters<typeof statusNotices>[1]> = {}) {
  return {
    scope: SCOPE,
    console: "Consola de tripulación",
    subject: "crew-01",
    summary: "Estado nominal. Sin hallazgos que requieran acción.",
    alerts,
    annunciation: new Map<string, string>(),
    acknowledged: new Set<string>(),
    privacy: false,
    now: T,
    ...extra,
  };
}

function routine(key: string, state: RoutineState["state"], extra: Partial<RoutineState> = {}): RoutineState {
  return {
    key,
    display: key,
    display_es: `medida ${key}`,
    period_hours: 6,
    basis: "diseño",
    state,
    last_run: null,
    last_success: null,
    ...extra,
  };
}

function view(routines: RoutineState[], extra: Partial<RoutinesView> = {}): RoutinesView {
  return {
    now: "2026-11-03T00:00:00+00:00",
    counts: {},
    routines,
    active_event: null,
    event_note: null,
    event_over_note: "Sin evento solar en curso: las medidas se esperan con su periodo de diseño",
    mission_level: "nominal",
    mission_level_display: "nominal",
    suspended_note: null,
    ...extra,
  };
}

function notice(priority: Notice["priority"], key: string, at = T, scope = SCOPE): Notice {
  return { key, scope, priority, chunks: [key], at };
}

afterEach(() => silenceFor(0));

describe("al abrir: saludo y resumen del backend", () => {
  it("saluda una vez, con la consola, el tripulante y el resumen tal cual", () => {
    const first = statusNotices(INITIAL_ALERT_MEMORY, statusInput([]));
    expect(first.notices).toHaveLength(1);
    const [entry] = first.notices;
    expect(entry?.priority).toBe("entry");
    expect(entry?.chunks[0]).toBe(
      `${GREETING} Consola de tripulación, tripulante crew-01. Estado: Estado nominal. Sin hallazgos que requieran acción.`,
    );
    // El sondeo siguiente, sin cambios, no dice nada.
    const second = statusNotices(first.memory, statusInput([]));
    expect(second.notices).toEqual([]);
    // Cambiar de ámbito dice el estado del nuevo, sin volver a saludar.
    const other = statusNotices(second.memory, statusInput([], { scope: "ground|crew-01", console: "Consola de Tierra" }));
    expect(other.notices[0]?.chunks[0]?.startsWith("Consola de Tierra")).toBe(true);
    expect(other.notices[0]?.chunks.join(" ")).not.toContain(GREETING);
  });

  it("al entrar dice las alertas que hay con la frase de announce.ts, dentro del aviso de entrada", () => {
    const { notices } = statusNotices(INITIAL_ALERT_MEMORY, statusInput([critical, watch]));
    expect(notices).toHaveLength(1);
    expect(notices[0]?.chunks.slice(1)).toEqual([`${announcementText(critical)}.`, `${announcementText(watch)}.`]);
  });

  it("con la privacidad no dice el nombre ni los motivos", () => {
    const { notices } = statusNotices(INITIAL_ALERT_MEMORY, statusInput([critical], { privacy: true }));
    const text = notices.flatMap((item) => item.chunks).join(" ");
    expect(text).not.toContain("crew-01");
    expect(text).not.toContain("140");
    expect(text.startsWith(`${GREETING} Consola de tripulación.`)).toBe(true);
    expect(entrySpeech({ greet: true, console: "C", subject: "Ana", summary: "S", alerts: [], privacy: true }).join(" ")).not.toContain("Ana");
  });
});

describe("alertas nuevas, con el criterio de announce.ts", () => {
  const opened = statusNotices(INITIAL_ALERT_MEMORY, statusInput([])).memory;

  it("una crítica nueva es crítica; una de vigilancia, no; no se repiten", () => {
    const next = statusNotices(opened, statusInput([critical, watch]));
    expect(next.notices.map((item) => item.priority)).toEqual(["critical", "alert"]);
    expect(next.notices[0]?.chunks[0]).toBe(`Alerta nueva: ${announcementText(critical)}.`);
    expect(statusNotices(next.memory, statusInput([critical, watch])).notices).toEqual([]);
  });

  it("lo suprimido o inhibido no se dice (F.6.4)", () => {
    const silenced = new Map([[critical.id, "suppressed"], [watch.id, "inhibited"]]);
    expect(statusNotices(opened, statusInput([critical, watch], { annunciation: silenced })).notices).toEqual([]);
  });

  it("una crítica ya reconocida no corta: va como alerta", () => {
    const next = statusNotices(opened, statusInput([critical], { acknowledged: new Set([critical.id]) }));
    expect(next.notices[0]?.priority).toBe("alert");
  });
});

describe("medidas, nivel de misión y evento solar entre sondeos", () => {
  it("la primera lectura es la línea de partida: no avisa", () => {
    const { notices } = routineNotices(null, view([routine("hr", "rota")]), SCOPE, T);
    expect(notices).toEqual([]);
  });

  it("avisa de la que pasa a atrasada o a sin lectura buena, con su nombre del backend", () => {
    const base = routineNotices(null, view([routine("hr", "al-dia"), routine("bp", "atrasada"), routine("t", "al-dia")]), SCOPE, T);
    const next = routineNotices(base.memory, view([routine("hr", "atrasada"), routine("bp", "rota"), routine("t", "al-dia")]), SCOPE, T);
    expect(next.notices.map((item) => item.chunks.join(" "))).toEqual([
      "Medida periódica: medida hr, atrasada.",
      "Medida periódica: medida bp, sin lectura buena.",
    ]);
    expect(next.notices.every((item) => item.priority === "routine")).toBe(true);
    // Sin cambios, nada; la que vuelve a su ritmo tampoco se dice.
    expect(routineNotices(next.memory, view([routine("hr", "atrasada"), routine("bp", "rota"), routine("t", "al-dia")]), SCOPE, T).notices).toEqual([]);
    expect(routineNotices(next.memory, view([routine("hr", "al-dia"), routine("bp", "rota"), routine("t", "al-dia")]), SCOPE, T).notices).toEqual([]);
  });

  it("lo que el nivel de misión suspende no se debe: no avisa", () => {
    const base = routineNotices(null, view([routine("hr", "al-dia")]), SCOPE, T);
    const next = routineNotices(base.memory, view([routine("hr", "rota", { suspended: true })]), SCOPE, T);
    expect(next.notices).toEqual([]);
  });

  it("el nivel de misión que cambia, con el nombre y la frase del backend", () => {
    const base = routineNotices(null, view([]), SCOPE, T);
    const next = routineNotices(
      base.memory,
      view([], { mission_level: "minimal", mission_level_display: "mínimo", suspended_note: "Nivel de misión «mínimo»: 2 de estas medidas no se esperan" }),
      SCOPE,
      T,
    );
    expect(next.notices).toHaveLength(1);
    expect(next.notices[0]?.priority).toBe("mission");
    expect(next.notices[0]?.chunks).toEqual(["Nivel de misión: mínimo.", "Nivel de misión «mínimo»: 2 de estas medidas no se esperan."]);
  });

  it("el evento solar que empieza y el que acaba, con la frase del backend; sin frase, nada", () => {
    const base = routineNotices(null, view([]), SCOPE, T);
    const started = routineNotices(
      base.memory,
      view([], { active_event: { event_id: "SEP-1" }, event_note: "Evento solar SEP-1 en curso", event_over_note: null }),
      SCOPE,
      T,
    );
    expect(started.notices.map((item) => [item.priority, item.chunks[0]])).toEqual([["solar", "Evento solar SEP-1 en curso."]]);
    const over = routineNotices(started.memory, view([]), SCOPE, T);
    expect(over.notices[0]?.chunks[0]).toBe("Sin evento solar en curso: las medidas se esperan con su periodo de diseño.");
    const mute = routineNotices(base.memory, view([], { active_event: { event_id: "SEP-2" }, event_note: null }), SCOPE, T);
    expect(mute.notices).toEqual([]);
    // Si no se dijo que empezaba, tampoco se dice que acaba.
    expect(routineNotices(mute.memory, view([]), SCOPE, T).notices).toEqual([]);
  });

  it("un nivel de misión sin su nombre del backend no se dice", () => {
    const base = routineNotices(null, view([]), SCOPE, T);
    const { mission_level_display: _, ...bare } = view([], { mission_level: "minimal" });
    expect(routineNotices(base.memory, bare, SCOPE, T).notices).toEqual([]);
  });

  it("no dice nombres de personas: solo los textos del backend sobre medidas y misión", () => {
    const base = routineNotices(null, view([routine("hr", "al-dia")]), SCOPE, T);
    const next = routineNotices(base.memory, view([routine("hr", "rota")], { mission_level: "reduced", mission_level_display: "reducido" }), SCOPE, T);
    expect(next.notices.flatMap((item) => item.chunks).join(" ")).not.toMatch(/crew-01|tripulante/);
  });
});

describe("cola, tope y prioridad", () => {
  it("el orden de prioridad declarado", () => {
    expect(PRIORITY_ORDER).toEqual(["critical", "entry", "alert", "mission", "solar", "routine"]);
  });

  it("un aviso no crítico cada NOTICE_GAP_MS; el resto espera en cola, por prioridad", () => {
    let pacer = enqueue(INITIAL_PACER, [notice("routine", "r"), notice("mission", "m"), notice("alert", "a")], T, 0);
    let out = drain(pacer, T, 0);
    expect(out.speak.map((item) => item.key)).toEqual(["a"]);
    pacer = out.pacer;
    out = drain(pacer, T + NOTICE_GAP_MS - 1, 0);
    expect(out.speak).toEqual([]);
    out = drain(out.pacer, T + NOTICE_GAP_MS, 0);
    expect(out.speak.map((item) => item.key)).toEqual(["m"]);
    out = drain(out.pacer, T + 2 * NOTICE_GAP_MS, 0);
    expect(out.speak.map((item) => item.key)).toEqual(["r"]);
  });

  it("lo crítico pasa siempre, sin esperar turno, y corta lo que se esté diciendo", () => {
    const busy = { queue: [], lastAt: T };
    const out = drain(enqueue(busy, [notice("critical", "c"), notice("alert", "a")], T + 1, 0), T + 1, 0);
    expect(out.speak.map((item) => item.key)).toEqual(["c"]);
    expect(out.interrupt).toBe(true);
    expect(out.pacer.queue.map((item) => item.key)).toEqual(["a"]);
  });

  it("la entrada no espera turno y se lleva lo que esperaba de otro ámbito", () => {
    const waiting = enqueue({ queue: [], lastAt: T }, [notice("routine", "old", T, "crew|crew-02")], T, 0);
    const out = drain(enqueue(waiting, [notice("entry", "e")], T + 1, 0), T + 1, 0);
    expect(out.speak.map((item) => item.key)).toEqual(["e"]);
    expect(out.interrupt).toBe(false);
    expect(out.pacer.queue).toEqual([]);
  });

  it("lo crítico y las alertas no se caen por tope ni por edad", () => {
    const criticals = Array.from({ length: QUEUE_LIMIT + 2 }, (_, i) => notice("critical", `c${i}`));
    const out = drain(enqueue(INITIAL_PACER, criticals, T, 0), T, 0);
    expect(out.speak).toHaveLength(QUEUE_LIMIT + 2);
    const alerts = Array.from({ length: QUEUE_LIMIT + 2 }, (_, i) => notice("alert", `a${i}`, T + i));
    const queued = enqueue({ queue: [], lastAt: T }, [...alerts, notice("routine", "r")], T, 0);
    expect(queued.queue.filter((item) => item.priority === "alert")).toHaveLength(QUEUE_LIMIT + 2);
    const late = drain(queued, T + QUEUE_TTL_MS + NOTICE_GAP_MS, 0);
    expect(late.speak.map((item) => item.key)).toEqual(["a0"]);
    expect(late.pacer.queue.map((item) => item.key)).not.toContain("r");
    expect(late.pacer.queue).toHaveLength(QUEUE_LIMIT + 1);
  });

  it("ni la entrada ni lo crítico retrasan el aviso siguiente", () => {
    const after = drain(enqueue(INITIAL_PACER, [notice("entry", "e"), notice("critical", "c")], T, 0), T, 0);
    expect(after.pacer.lastAt).toBeNull();
    const next = drain(enqueue(after.pacer, [notice("routine", "r")], T + 1, 0), T + 1, 0);
    expect(next.speak.map((item) => item.key)).toEqual(["r"]);
  });

  it("la misma clave ocupa un sitio; la cola tiene tope y lo viejo caduca", () => {
    const twice = enqueue(INITIAL_PACER, [notice("routine", "r"), notice("routine", "r")], T, 0);
    expect(twice.queue).toHaveLength(1);
    const many = Array.from({ length: QUEUE_LIMIT + 3 }, (_, i) => notice("routine", `r${i}`, T + i));
    const full = enqueue(INITIAL_PACER, [...many, notice("mission", "m")], T, 0);
    expect(full.queue).toHaveLength(QUEUE_LIMIT);
    expect(full.queue[0]?.key).toBe("m");
    const stale = drain(enqueue(INITIAL_PACER, [notice("routine", "r")], T, 0), T + QUEUE_TTL_MS + 1, 0);
    expect(stale.speak).toEqual([]);
    expect(stale.pacer.queue).toEqual([]);
  });
});

describe("silencio", () => {
  it("calla y descarta lo no crítico; lo crítico se sigue diciendo", () => {
    const until = T + DEFAULT_SILENCE_MS;
    const queued = enqueue(INITIAL_PACER, [notice("alert", "a"), notice("entry", "e"), notice("critical", "c")], T, until);
    expect(queued.queue.map((item) => item.key)).toEqual(["c"]);
    // Lo que ya esperaba cuando empieza el silencio se cae sin decirse.
    const before = enqueue(INITIAL_PACER, [notice("routine", "r")], T, 0);
    const out = drain(before, T + 1, until);
    expect(out.speak).toEqual([]);
    expect(out.pacer.queue).toEqual([]);
    expect(drain(queued, T, until).speak.map((item) => item.key)).toEqual(["c"]);
  });

  it("silenceFor fija y quita el silencio, y avisa a quien escucha", () => {
    let calls = 0;
    const stop = subscribeSilence(() => {
      calls += 1;
    });
    silenceFor(60_000, T);
    expect(silencedUntil()).toBe(T + 60_000);
    silenceFor(0);
    expect(silencedUntil()).toBe(0);
    stop();
    silenceFor(1, T);
    expect(calls).toBe(2);
  });
});

describe("modo de pantalla y mandos", () => {
  it("apagado por defecto; lo guardado antes de existir no lo trae", () => {
    expect(DEFAULT_MODES.proactive).toBe(false);
    expect(parseModes(JSON.stringify({ voice: true })).proactive).toBe(false);
    expect(parseModes(JSON.stringify({ proactive: true })).proactive).toBe(true);
  });

  const render = (on: boolean, silenced: number, availability: "ready" | "no-api" = "ready") =>
    renderToStaticMarkup(
      createElement(
        VoiceAvailabilityContext.Provider,
        { value: availability },
        createElement(ProactiveControls, { on, onChange: () => undefined, silenced }),
      ),
    );

  it("el mando dice su estado y, encendido, ofrece el silencio", () => {
    expect(render(false, 0)).toContain('aria-pressed="false"');
    expect(render(false, 0)).not.toContain("Silencio");
    const on = render(true, 0);
    expect(on).toContain('aria-pressed="true"');
    expect(on).toContain("Silencio 15 min");
    const quiet = render(true, Date.UTC(2026, 10, 3, 12, 30));
    expect(quiet).toContain("las alertas que interrumpen se siguen diciendo");
    expect(quiet).toContain("Quitar el silencio");
  });

  it("sin voz local no hay mando (el modo voz ya dice por qué)", () => {
    expect(render(true, 0, "no-api")).toBe("");
  });
});

describe("canal del asistente", () => {
  it("un say llega a quien escucha el canal", () => {
    const seen: AssistantEvent[] = [];
    const stop = listen((event) => seen.push(event));
    emit({ kind: "say", text: "hola" });
    stop();
    emit({ kind: "say", text: "otra" });
    expect(seen).toEqual([{ kind: "say", text: "hola" }]);
  });

  it("useProactive emite al canal lo que dice con la voz, y no escucha el canal", () => {
    const code = readFileSync(fileURLToPath(new URL("./useProactive.ts", import.meta.url)), "utf8");
    expect(code).toContain('emit({ kind: "say"');
    expect(code).not.toMatch(/\blisten\(/);
  });
});
