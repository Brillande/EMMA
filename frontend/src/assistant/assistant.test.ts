import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_MODES, type DisplayModes } from "../components/displayModes";
import type { AssistantInfo, AssistantTurn, UiInventory } from "../lib/api";
import { UNAVAILABLE_MARK } from "../lib/marks";
import { assistantAudioRequest } from "../lib/api";
import {
  ASSISTANT_TITLE,
  AssistantView,
  type AssistantViewProps,
  MIC_ON_MARK,
  TOGGLE_TEXT,
  generalNotice,
  routeBusEvent,
  spokenReply,
  talkUnavailable,
} from "./Assistant";
import { emit, listen } from "./bus";
import {
  type IntentEffects,
  PANEL_IDS,
  WRITE_ROUTES,
  type WriteIntent,
  confirmationWord,
  executeIntent,
  proposalFields,
  proposalSpeech,
  resolveTab,
  TOGGLE_MODES,
  sendSigned,
  signedRequest,
  toggledModes,
} from "./intents";
import { MEMORY_LIMIT, type ThreadItem, historyOf, memoryScope, remember } from "./memory";
import { IDLE, type TalkState, micOpen, talkKey, talkStep } from "./pushToTalk";
import { joinChunks } from "./recorder";

/**
 * El asistente en la consola (`assistant/`): pulsar y hablar, el ejecutor de intenciones con su
 * confirmación, la memoria de la sesión y lo que se pinta. El backend es de mentira: aquí se
 * prueba lo que hace la consola con lo que contesta.
 */

function turn(intent: string, extra: Partial<AssistantTurn> = {}): AssistantTurn {
  return {
    intent,
    args: {},
    reply: "Texto del backend.",
    reply_source: "backend",
    needs_confirmation: false,
    proposal: null,
    checks: { text_guard: true, numbers: true, no_prescription: true, schema: true },
    label: null,
    ...extra,
  };
}

/** El inventario de verdad, el que sirve `GET /api/assistant` (sin su nota). */
const UI = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../backend/app/data/assistant_ui.json", import.meta.url)), "utf8"),
) as UiInventory;

const CREW_TABS = [
  { key: "radiation", label: "Radiación" },
  { key: "hazards", label: "Peligros y alertas" },
  { key: "routines", label: "Rutinas y notas" },
  { key: "mission", label: "Misión y hábitat" },
  { key: "log", label: "Diario y pruebas" },
  { key: "library", label: "Biblioteca" },
];

function effects(overrides: Partial<IntentEffects> = {}, modes: Partial<DisplayModes> = {}) {
  const calls: string[] = [];
  const patches: Partial<DisplayModes>[] = [];
  const base: IntentEffects = {
    console: "crew",
    tabs: () => CREW_TABS,
    openTab: (key) => calls.push(`tab:${key}`),
    switchConsole: (to) => calls.push(`console:${to}`),
    revealPanel: (id, place) => calls.push(`panel:${id}@${place.console}:${place.section}`),
    readPanel: (id, place) => {
      calls.push(`read:${id}@${place.console}:${place.section}`);
      return true;
    },
    stepPanel: (delta) => {
      calls.push(`step:${delta}`);
      return true;
    },
    scroll: (direction) => calls.push(`scroll:${direction}`),
    ui: UI,
    modes: { ...DEFAULT_MODES, ...modes },
    updateModes: (patch) => patches.push(patch),
    readStatus: () => {
      calls.push("read:status");
      return true;
    },
    readAlerts: () => {
      calls.push("read:alerts");
      return true;
    },
    stopVoice: () => calls.push("voice:stop"),
    repeatVoice: () => calls.push("voice:repeat"),
    ...overrides,
  };
  return { base, calls, patches };
}

describe("pulsar y mantener para hablar", () => {
  type Step = "press" | "release" | "opened" | "denied" | "done" | "quiet" | "listen" | "listen-speaking";
  const run = (events: Step[], from: TalkState = IDLE) =>
    events.reduce(
      (state, step) =>
        talkStep(
          state,
          step === "listen" || step === "listen-speaking"
            ? { type: "listen", speaking: step === "listen-speaking" }
            : { type: step },
        ),
      from,
    );

  it("pulsar abre, el micrófono llega y graba, soltar manda y al terminar vuelve a reposo", () => {
    expect(run(["press"])).toEqual({ phase: "opening", mode: "hold", released: false });
    expect(run(["press", "opened"])).toEqual({ phase: "recording", mode: "hold" });
    expect(run(["press", "opened", "release"])).toEqual({ phase: "sending" });
    expect(run(["press", "opened", "release", "done"])).toEqual(IDLE);
  });

  it("soltar antes de tener micrófono no manda nada", () => {
    expect(run(["press", "release"])).toEqual({ phase: "opening", mode: "hold", released: true });
    expect(run(["press", "release", "opened"])).toEqual(IDLE);
  });

  it("sin permiso de micrófono vuelve a reposo", () => {
    expect(run(["press", "denied"])).toEqual(IDLE);
  });

  it("pulsar con algo en curso no apila otra grabación", () => {
    expect(run(["press", "opened", "press"])).toEqual({ phase: "recording", mode: "hold" });
    expect(run(["press", "opened", "release", "press"])).toEqual({ phase: "sending" });
  });

  it("el turno abierto por el gesto no se corta al soltar, sí al volver a pulsar", () => {
    expect(run(["listen", "opened", "release"])).toEqual({ phase: "recording", mode: "listen" });
    expect(run(["listen", "opened", "press"])).toEqual({ phase: "sending" });
  });

  it("mientras EMMA habla, el turno del gesto espera a que calle y no graba su voz", () => {
    expect(run(["listen-speaking"])).toEqual({ phase: "waiting", mode: "listen" });
    expect(micOpen(run(["listen-speaking"]))).toBe(false);
    // Que llegue un «abierto» o un «soltar» no abre nada mientras espera.
    expect(run(["listen-speaking", "opened", "release"])).toEqual({ phase: "waiting", mode: "listen" });
    expect(run(["listen-speaking", "quiet"])).toEqual({ phase: "opening", mode: "listen", released: false });
    expect(run(["listen"])).toEqual({ phase: "opening", mode: "listen", released: false });
  });

  it("pulsar mientras espera corta la espera y abre al momento (la voz la corta quien pulsa)", () => {
    expect(run(["listen-speaking", "press"])).toEqual({ phase: "opening", mode: "hold", released: false });
  });

  it("el aviso de micrófono abierto va mientras se abre y mientras graba, no al mandar", () => {
    expect(micOpen(IDLE)).toBe(false);
    expect(micOpen(run(["press"]))).toBe(true);
    expect(micOpen(run(["press", "opened"]))).toBe(true);
    expect(micOpen(run(["press", "opened", "release"]))).toBe(false);
  });

  it("los trozos del worklet se unen en orden", () => {
    expect([...joinChunks([new Float32Array([1, 2]), new Float32Array([]), new Float32Array([3])])]).toEqual([1, 2, 3]);
  });

  it("Ctrl+Espacio mantenido: bajar pulsa, sin la repetición del teclado; soltar suelta", () => {
    const key = { code: "Space", key: " ", ctrlKey: true, altKey: false, metaKey: false, repeat: false };
    expect(talkKey(key, "down")).toBe("press");
    expect(talkKey({ ...key, repeat: true }, "down")).toBeNull();
    expect(talkKey({ ...key, ctrlKey: false }, "down")).toBeNull();
    expect(talkKey({ ...key, altKey: true }, "down")).toBeNull();
    expect(talkKey({ ...key, ctrlKey: false }, "up")).toBe("release");
    expect(talkKey({ ...key, code: "ControlLeft", key: "Control" }, "up")).toBe("release");
    expect(talkKey({ ...key, code: "KeyA", key: "a" }, "up")).toBeNull();
  });
});

describe("el ejecutor: paneles, modos y consola (inventario de la interfaz)", () => {
  it("abrir un panel va a su pestaña por su id; el de la otra consola, a la otra consola", () => {
    const { base, calls } = effects();
    expect(executeIntent(turn("open_panel", { args: { panel: "dose" } }), base).kind).toBe("done");
    expect(executeIntent(turn("open_panel", { args: { panel: "trends" } }), base).kind).toBe("done");
    expect(calls).toEqual(["panel:dose@crew:mission", "panel:trends@ground:trends"]);
  });

  it("un panel que vive en las dos consolas se abre en la de ahora", () => {
    const { base, calls } = effects();
    executeIntent(turn("open_panel", { args: { panel: "habitat" } }), base);
    expect(calls).toEqual(["panel:habitat@crew:mission"]);
  });

  it("un panel de una pestaña oculta (modo esencial) no se abre y se dice", () => {
    const { base, calls } = effects({ tabs: () => CREW_TABS.slice(0, 1) });
    expect(executeIntent(turn("open_panel", { args: { panel: "dose" } }), base).kind).toBe("unavailable");
    expect(calls).toEqual([]);
  });

  it("un panel que no está en el inventario, o sin inventario todavía, no hace nada", () => {
    const { base, calls } = effects();
    expect(executeIntent(turn("open_panel", { args: { panel: "launch-button" } }), base).kind).toBe("unknown");
    const early = effects({ ui: null });
    expect(executeIntent(turn("read_panel", { args: { panel: "dose" } }), early.base).kind).toBe("unavailable");
    expect([...calls, ...early.calls]).toEqual([]);
  });

  it("leer un panel lo lee tal cual; sin voz, se dice", () => {
    const { base, calls } = effects();
    expect(executeIntent(turn("read_panel", { args: { panel: "dose" } }), base).kind).toBe("done");
    expect(calls).toEqual(["read:dose@crew:mission"]);
    const mute = effects({ readPanel: () => false }).base;
    expect(executeIntent(turn("read_panel", { args: { panel: "dose" } }), mute).kind).toBe("unavailable");
  });

  it("siguiente, anterior, desplazar y cambiar de consola", () => {
    const { base, calls } = effects();
    executeIntent(turn("next_panel"), base);
    executeIntent(turn("previous_panel"), base);
    executeIntent(turn("scroll", { args: { direction: "top" } }), base);
    executeIntent(turn("scroll", { args: { direction: "sideways" } }), base);
    executeIntent(turn("switch_console", { args: { console: "ground" } }), base);
    executeIntent(turn("switch_console"), base);
    expect(calls).toEqual(["step:1", "step:-1", "scroll:top", "scroll:down", "console:ground", "console:ground"]);
    const last = effects({ stepPanel: () => false }).base;
    expect(executeIntent(turn("next_panel"), last).kind).toBe("unavailable");
  });

  it("cualquier modo de pantalla, encendido, apagado o cambiado", () => {
    const { base, patches } = effects({}, { followSensor: true });
    executeIntent(turn("toggle_mode", { args: { mode: "followFace", on: true } }), base);
    executeIntent(turn("toggle_mode", { args: { mode: "wakeWord", on: false } }), base);
    executeIntent(turn("toggle_mode", { args: { mode: "followSensor" } }), base);
    executeIntent(turn("toggle_mode", { args: { mode: "proactive", on: true } }), base);
    expect(patches).toEqual([{ followFace: true }, { wakeWord: false }, { followSensor: false }, { proactive: true }]);
  });

  it("con la privacidad, ni la cámara ni el micrófono se encienden; un modo que no existe, nada", () => {
    const { base, patches } = effects({}, { privacy: true });
    expect(executeIntent(turn("toggle_mode", { args: { mode: "followFace", on: true } }), base).kind).toBe("unavailable");
    expect(executeIntent(turn("toggle_mode", { args: { mode: "wakeWord", on: true } }), base).kind).toBe("unavailable");
    expect(executeIntent(turn("toggle_mode", { args: { mode: "rotation", on: true } }), base).kind).toBe("unknown");
    expect(patches).toEqual([]);
  });

  it("encender «Seguir el sensor» pide el permiso del giroscopio", () => {
    const requestOrientation = vi.fn();
    const { base } = effects({ requestOrientation });
    executeIntent(turn("toggle_mode", { args: { mode: "followSensor", on: true } }), base);
    expect(requestOrientation).toHaveBeenCalledTimes(1);
  });
});

describe("el ejecutor: intenciones de lectura", () => {
  it("abrir una pestaña por su clave, por un nombre conocido o por su rótulo", () => {
    expect(resolveTab("crew", "mission", CREW_TABS)).toBe("mission");
    expect(resolveTab("crew", "radiación", CREW_TABS, UI)).toBe("radiation");
    expect(resolveTab("crew", "Biblioteca", CREW_TABS)).toBe("library");
    expect(resolveTab("crew", "rutinas", CREW_TABS)).toBe("routines");
    expect(resolveTab("crew", "cuerpo", CREW_TABS)).toBeNull();
    const { base, calls } = effects();
    expect(executeIntent(turn("open_tab", { args: { section: "radiacion" } }), base)).toEqual({ kind: "done", note: null });
    expect(calls).toEqual(["tab:radiation"]);
  });

  it("una pestaña que no está a la vista no se abre y se dice", () => {
    const { base, calls } = effects({ tabs: () => CREW_TABS.slice(0, 1) });
    const outcome = executeIntent(turn("open_tab", { args: { section: "library" } }), base);
    expect(outcome.kind).toBe("unavailable");
    expect(calls).toEqual([]);
  });

  it("abrir la otra consola", () => {
    const { base, calls } = effects();
    executeIntent(turn("open_tab", { args: { section: "ground" } }), base);
    expect(calls).toEqual(["console:ground"]);
  });

  it("leer el estado y las alertas con la voz; sin nada que leer, se dice", () => {
    const { base, calls } = effects();
    expect(executeIntent(turn("read_status"), base).kind).toBe("done");
    expect(executeIntent(turn("read_alerts"), base).kind).toBe("done");
    expect(calls).toEqual(["read:status", "read:alerts"]);
    const mute = effects({ readStatus: () => false }).base;
    expect(executeIntent(turn("read_status"), mute).kind).toBe("unavailable");
  });

  it("leer las rutinas abre su pestaña (el texto lo dice la respuesta del backend)", () => {
    const { base, calls } = effects();
    expect(executeIntent(turn("read_routines"), base).kind).toBe("done");
    expect(calls).toEqual(["tab:routines"]);
  });

  it("girar: a los grados pedidos, o el siguiente cuarto de vuelta", () => {
    const { base, patches } = effects({}, { rotation: 90 });
    executeIntent(turn("rotate", { args: { degrees: 270 } }), base);
    executeIntent(turn("rotate"), base);
    executeIntent(turn("rotate", { args: { degrees: 45 } }), base);
    expect(patches).toEqual([{ rotation: 270 }, { rotation: 180 }, { rotation: 180 }]);
  });

  it("privacidad, baja visión y esencial: lo pedido, o cambiar", () => {
    const { base, patches } = effects({}, { privacy: false, lowVision: true, essential: false });
    executeIntent(turn("privacy", { args: { on: true } }), base);
    executeIntent(turn("privacy"), base);
    executeIntent(turn("low_vision"), base);
    executeIntent(turn("essential", { args: { on: true } }), base);
    expect(patches).toEqual([{ privacy: true }, { privacy: true }, { lowVision: false }, { essential: true }]);
  });

  it("parar y repetir la voz", () => {
    const { base, calls } = effects();
    executeIntent(turn("stop_voice"), base);
    executeIntent(turn("repeat_voice"), base);
    expect(calls).toEqual(["voice:stop", "voice:repeat"]);
  });

  it("la guía y el glosario abren la biblioteca y llevan a su panel", () => {
    const { base, calls } = effects();
    executeIntent(turn("open_guide"), base);
    executeIntent(turn("open_glossary"), base);
    expect(calls).toEqual([`panel:${PANEL_IDS.guides}@crew:library`, `panel:${PANEL_IDS.glossary}@crew:library`]);
  });

  it("PVT y Cognition abren su panel en a bordo; en Tierra no", () => {
    const { base, calls } = effects();
    executeIntent(turn("start_pvt"), base);
    executeIntent(turn("start_cognition"), base);
    expect(calls).toEqual([`panel:${PANEL_IDS.pvt}@crew:log`, `panel:${PANEL_IDS.cognition}@crew:log`]);
    const ground = effects({ console: "ground" });
    expect(executeIntent(turn("start_pvt"), ground.base).kind).toBe("unavailable");
    expect(ground.calls).toEqual([]);
  });

  it("silencio y dejar de escuchar llaman a lo inyectado; sin ello, no disponible", () => {
    const silence = vi.fn();
    const stopListening = vi.fn();
    const { base } = effects({ silence, stopListening });
    executeIntent(turn("silence", { args: { minutes: 5 } }), base);
    executeIntent(turn("silence"), base);
    executeIntent(turn("stop_listening"), base);
    expect(silence.mock.calls).toEqual([[5 * 60_000], [15 * 60_000]]);
    expect(stopListening).toHaveBeenCalledTimes(1);
    const bare = effects().base;
    expect(executeIntent(turn("silence"), bare).kind).toBe("unavailable");
    expect(executeIntent(turn("stop_listening"), bare).kind).toBe("unavailable");
  });

  it("«none» no hace nada; una intención desconocida tampoco, y lo dice", () => {
    const { base, calls, patches } = effects();
    expect(executeIntent(turn("none"), base)).toEqual({ kind: "done", note: null });
    const unknown = executeIntent(turn("format_disk"), base);
    expect(unknown.kind).toBe("unknown");
    expect(unknown.kind === "unknown" && unknown.note).toMatch(/no hago nada/);
    expect(calls).toEqual([]);
    expect(patches).toEqual([]);
  });
});

describe("el ejecutor: escrituras con confirmación", () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ledger_index: 7 }), { status: 200 }));
  afterEach(() => {
    fetchMock.mockClear();
    vi.unstubAllGlobals();
  });

  const diary = turn("diary_entry", {
    needs_confirmation: true,
    proposal: { key: "sleep-quality", value: 2, subject: "crew-01" },
  });

  it("una escritura sin confirmar no firma: solo devuelve la propuesta", () => {
    vi.stubGlobal("fetch", fetchMock);
    const { base, calls } = effects();
    const outcome = executeIntent(diary, base);
    expect(outcome).toEqual({ kind: "proposal", pending: { intent: "diary_entry", proposal: diary.proposal } });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(calls).toEqual([]);
  });

  it("sin propuesta no hay nada que firmar", () => {
    const { base } = effects();
    expect(executeIntent(turn("pain_report", { proposal: null }), base).kind).toBe("unavailable");
  });

  it("la propuesta se enseña campo a campo y se dice, sin el campo de quien firma", () => {
    const fields = proposalFields({
      intent: "pain_report",
      proposal: { zones: [{ zone: "knee-left", intensity: 4, characters: ["dull", "burning"] }], reported_by: "otro" },
    });
    expect(fields).toEqual([
      { name: "zones 1 · zone", value: "knee-left" },
      { name: "zones 1 · intensity", value: "4" },
      { name: "zones 1 · characters", value: "dull, burning" },
    ]);
    expect(proposalSpeech(fields).join(" ")).toMatch(/confirmo.*cancela/);
  });

  it("las cifras de la propuesta se leen como se firman", () => {
    const fields = proposalFields({ intent: "diary_entry", proposal: { value: 0.25, tiny: 1.5e-7, big: 12000 } });
    expect(fields).toEqual([
      { name: "value", value: "0,25" },
      { name: "tiny", value: "0,00000015" },
      { name: "big", value: expect.stringMatching(/^12.?000$/) as unknown as string },
    ]);
  });

  it("«confirmo» y «cancela», dichos o escritos; lo demás no decide", () => {
    expect(confirmationWord("Confirmo.")).toBe("confirm");
    expect(confirmationWord("EMMA, confirmo")).toBe("confirm");
    expect(confirmationWord("sí, confirmo")).toBe("confirm");
    expect(confirmationWord("Cancela")).toBe("cancel");
    expect(confirmationWord("no")).toBe("cancel");
    expect(confirmationWord("no confirmo")).toBeNull();
    expect(confirmationWord("apunta otra cosa")).toBeNull();
  });

  it("sin tripulante en consola no se firma", () => {
    const request = signedRequest({ intent: "diary_entry", proposal: diary.proposal ?? {} }, "  ", "crew-01");
    expect(request.ok).toBe(false);
  });

  it("una propuesta de otro tripulante no se firma", () => {
    const request = signedRequest({ intent: "diary_entry", proposal: { key: "x", value: 1, subject: "crew-02" } }, "Ana", "crew-01");
    expect(request).toEqual({ ok: false, reason: "La propuesta es de otro tripulante; no se firma." });
  });

  it("quien firma lo pone la consola, aunque la propuesta traiga otro", () => {
    const request = signedRequest({ intent: "safe_mode", proposal: { active: true, reason: "r", declared_by: "otro" } }, "Ana", "crew-01");
    expect(request).toEqual({
      ok: true,
      intent: "safe_mode",
      path: "/safe-mode",
      body: { active: true, reason: "r", declared_by: "Ana" },
    });
  });

  const cases: { intent: WriteIntent; proposal: Record<string, unknown>; body: Record<string, unknown> }[] = [
    {
      intent: "diary_entry",
      proposal: { key: "sleep-quality", value: 2 },
      body: { key: "sleep-quality", value: 2, subject: "crew-01", recorded_by: "Ana" },
    },
    {
      intent: "pain_report",
      proposal: { zones: [{ zone: "knee-left", intensity: 4, characters: [] }] },
      body: { zones: [{ zone: "knee-left", intensity: 4, characters: [] }], subject: "crew-01", reported_by: "Ana" },
    },
    {
      intent: "acknowledge_alert",
      proposal: { domain: "sleep", level: "watch", reference_time: "2026-11-03T10:00:00Z" },
      body: {
        domain: "sleep",
        level: "watch",
        reference_time: "2026-11-03T10:00:00Z",
        subject: "crew-01",
        acknowledged_by: "Ana",
      },
    },
    {
      intent: "mission_level",
      proposal: { level: "reduced", reason: "energía", cited_system: null },
      body: { level: "reduced", reason: "energía", cited_system: null, declared_by: "Ana" },
    },
    {
      intent: "mission_profile",
      proposal: { profile: "leo", reason: "" },
      body: { profile: "leo", reason: "", declared_by: "Ana" },
    },
    {
      intent: "safe_mode",
      proposal: { active: true, reason: "prueba" },
      body: { active: true, reason: "prueba", declared_by: "Ana" },
    },
  ];

  for (const item of cases) {
    it(`al confirmar, ${item.intent} va por la ruta del formulario (${WRITE_ROUTES[item.intent].path}) con el cuerpo exacto`, async () => {
      vi.stubGlobal("fetch", fetchMock);
      const request = signedRequest({ intent: item.intent, proposal: item.proposal }, "Ana", "crew-01");
      if (!request.ok) throw new Error(request.reason);
      await sendSigned(request);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
      expect(url).toBe(`/api${WRITE_ROUTES[item.intent].path}`);
      expect(init.method).toBe("POST");
      expect(JSON.parse(String(init.body))).toEqual(item.body);
    });
  }
});

describe("la memoria de la conversación", () => {
  const item = (index: number): ThreadItem => ({ role: index % 2 === 0 ? "user" : "assistant", text: `t${index}` });

  it("se queda con los últimos ocho y los manda como historia, sin rótulos", () => {
    let thread: ThreadItem[] = [];
    for (let index = 0; index < 12; index += 1) thread = remember(thread, item(index));
    expect(thread).toHaveLength(MEMORY_LIMIT);
    expect(thread[0]?.text).toBe("t4");
    const labelled = remember(thread, { role: "assistant", text: "r", source: "model", label: "sin validar" });
    expect(historyOf(labelled).at(-1)).toEqual({ role: "assistant", text: "r" });
    expect(historyOf(labelled)).toHaveLength(8);
  });

  it("un texto vacío no ocupa sitio", () => {
    expect(remember([], { role: "user", text: "  " })).toEqual([]);
  });

  it("se borra al cambiar de consola, de tripulante o de privacidad", () => {
    const base = memoryScope("crew", "crew-01", false);
    expect(memoryScope("crew", "crew-01", false)).toBe(base);
    expect(memoryScope("ground", "crew-01", false)).not.toBe(base);
    expect(memoryScope("crew", "crew-02", false)).not.toBe(base);
    expect(memoryScope("crew", "crew-01", true)).not.toBe(base);
  });

  it("no se guarda en el equipo: ni `localStorage` ni `sessionStorage` en el asistente", async () => {
    const { readFileSync, readdirSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const dir = fileURLToPath(new URL(".", import.meta.url));
    for (const name of readdirSync(dir).filter((file) => /\.tsx?$/.test(file) && !file.endsWith(".test.ts"))) {
      expect(readFileSync(`${dir}${name}`, "utf8"), name).not.toMatch(/\b(localStorage|sessionStorage|indexedDB)\s*\./);
    }
  });
});

describe("el canal común", () => {
  it("«say» ya se dijo: entra en el hilo como frase fija y no se vuelve a decir", () => {
    const said: ThreadItem[] = [];
    const other = vi.fn();
    routeBusEvent({ kind: "say", text: "Buenos días." }, { audio: other, listen: other, said: (item) => said.push(item) });
    expect(said).toEqual([{ role: "assistant", text: "Buenos días.", source: "fixed", label: null }]);
    expect(other).not.toHaveBeenCalled();
  });

  it("«utterance» manda el audio y «listen» abre un turno", () => {
    const audio = vi.fn();
    const open = vi.fn();
    const blob = new Blob(["x"]);
    routeBusEvent({ kind: "utterance", audio: blob }, { audio, listen: open, said: vi.fn() });
    routeBusEvent({ kind: "listen" }, { audio, listen: open, said: vi.fn() });
    expect(audio).toHaveBeenCalledWith(blob);
    expect(open).toHaveBeenCalledTimes(1);
  });

  it("el trozo de voz va como WAV binario, con consola y tripulante en la consulta e historia y firmante en cabeceras", async () => {
    const wav = new Blob(["RIFF"], { type: "audio/wav" });
    const { path, init } = assistantAudioRequest(wav, {
      console: "crew",
      subject: "crew-01",
      history: [{ role: "user", text: "¿qué tal?" }],
      operator: "Ána",
    });
    expect(path).toBe("/assistant/audio?console=crew&subject=crew-01");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(wav);
    const headers = init.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("audio/wav");
    const history = new TextDecoder().decode(Uint8Array.from(atob(headers["X-EMMA-History"] ?? ""), (c) => c.charCodeAt(0)));
    expect(JSON.parse(history)).toEqual([{ role: "user", text: "¿qué tal?" }]);
    expect(decodeURIComponent(headers["X-EMMA-Operator"] ?? "")).toBe("Ána");
    expect(headers["X-EMMA-Modes"]).toBeUndefined();
  });

  it("los modos puestos viajan con el turno: por sus ids en la cabecera del audio", () => {
    const modes = toggledModes({ ...DEFAULT_MODES, privacy: true, lowVision: true });
    expect(modes.privacy).toBe(true);
    expect(modes.voice).toBe(false);
    expect(Object.keys(modes).sort()).toEqual([...TOGGLE_MODES].sort());
    const { init } = assistantAudioRequest(new Blob(["RIFF"], { type: "audio/wav" }), {
      console: "crew",
      subject: "crew-01",
      history: [],
      operator: "",
      modes,
    });
    const headers = init.headers as Record<string, string>;
    expect(headers["X-EMMA-Modes"]?.split(",").sort()).toEqual(["lowVision", "privacy"]);
  });

  it("lo emitido llega a quien escucha, y deja de llegar al soltarlo", () => {
    const seen: string[] = [];
    const stop = listen((event) => seen.push(event.kind));
    emit({ kind: "listen" });
    emit({ kind: "say", text: "hola" });
    stop();
    emit({ kind: "listen" });
    expect(seen).toEqual(["listen", "say"]);
  });
});

describe("lo que se pinta", () => {
  const info: AssistantInfo = { available: true, model: "gemma4:12b-it-qat", reason: null, voice_available: true, intents: [], ui: UI };
  const props = (overrides: Partial<AssistantViewProps> = {}): AssistantViewProps => ({
    load: { state: "ready", info },
    open: true,
    onToggle: () => undefined,
    thread: [],
    privacy: false,
    mic: false,
    busy: false,
    talk: null,
    onTalk: () => undefined,
    draft: "",
    onDraft: () => undefined,
    onSend: () => undefined,
    pending: null,
    onConfirm: () => undefined,
    onCancel: () => undefined,
    failure: null,
    ...overrides,
  });
  const render = (overrides: Partial<AssistantViewProps> = {}) =>
    renderToStaticMarkup(createElement(AssistantView, props(overrides)));

  it("el título, «Hablar con EMMA» y el campo de texto", () => {
    const html = render();
    expect(html).toContain(ASSISTANT_TITLE);
    expect(html).toContain("Hablar con EMMA");
    expect(html).toContain('aria-keyshortcuts="Control+Space"');
    expect(html).toContain("Escribir a EMMA");
    expect(html).not.toContain("Micrófono abierto");
  });

  it("reserva su sitio: el estado en `data-open`, el título dice qué hace y el campo queda fuera del hilo", () => {
    const open = render({ thread: [{ role: "user", text: "x" }] });
    expect(open).toMatch(/<aside class="assistant" aria-label="EMMA \(asistente\)" data-open="true">/);
    expect(open).toContain(`aria-expanded="true"`);
    expect(open).toContain(`assistant-toggle-state secondary">${TOGGLE_TEXT.open}</span>`);
    // El hilo se desplaza dentro de su caja; el campo, Enviar y el atajo van después, siempre a mano.
    const scroll = open.indexOf('class="assistant-scroll"');
    const form = open.indexOf('<form class="assistant-form"');
    expect(scroll).toBeGreaterThan(-1);
    expect(form).toBeGreaterThan(open.indexOf("</ol>"));
    expect(open.slice(scroll, form)).toMatch(/<\/ol><\/div>$/);
    expect(open).toContain('class="assistant-input"');
    expect(open).toContain('class="secondary shortcut assistant-shortcut"');
    const closed = render({ open: false });
    expect(closed).toContain('data-open="false"');
    expect(closed).toContain(`>${TOGGLE_TEXT.closed}</span>`);
    expect(closed).toContain("Hablar con EMMA");
    expect(closed).not.toContain("Escribir a EMMA");
  });

  it("micrófono abierto, en el azul de aviso, también con el panel cerrado", () => {
    const html = render({ mic: true, open: false });
    expect(MIC_ON_MARK.color).toBe("blue");
    expect(html).toMatch(/class="[^"]*c-blue[^"]*"[^>]*>.*Micrófono abierto/);
  });

  it("el hilo: lo dicho y la respuesta; el rótulo del backend solo si la redactó el modelo", () => {
    const html = render({
      thread: [
        { role: "user", text: "¿cómo estoy?" },
        { role: "assistant", text: "Respuesta A", source: "model", label: "respuesta del modelo local, sin validar" },
        { role: "assistant", text: "Respuesta B", source: "backend", label: "no se enseña" },
      ],
    });
    expect(html).toContain("¿cómo estoy?");
    expect(html).toContain("Respuesta A");
    expect(html).toContain("respuesta del modelo local, sin validar");
    expect(html).toContain("Respuesta B");
    expect(html).not.toContain("no se enseña");
  });

  it("sin asistente, «no disponible» en gris con el motivo del backend, y sin mandos", () => {
    const html = render({ load: { state: "ready", info: { ...info, available: false, reason: "Ollama no responde" } } });
    expect(UNAVAILABLE_MARK.color).toBe("gray");
    expect(html).toMatch(/c-gray[^>]*>.*Asistente no disponible: Ollama no responde/);
    expect(html).not.toContain("Hablar con EMMA");
    expect(html).not.toContain("Escribir a EMMA");
  });

  it("sin voz o sin poder grabar, «hablar no disponible» en gris y queda el campo de texto", () => {
    expect(talkUnavailable({ ...info, voice_available: false }, true)).toBe("no-voice");
    expect(talkUnavailable(info, false)).toBe("no-format");
    expect(talkUnavailable(info, true)).toBeNull();
    const html = render({ talk: "no-format" });
    expect(html).toMatch(/c-gray[^>]*>.*Hablar no disponible/);
    expect(html).not.toContain("Hablar con EMMA");
    expect(html).toContain("Escribir a EMMA");
  });

  it("conocimiento del modelo: el mismo literal del backend en el hilo y en la voz, delante", () => {
    const intents = JSON.parse(
      readFileSync(fileURLToPath(new URL("../../../backend/app/data/assistant_intents.json", import.meta.url)), "utf8"),
    ) as { general_label: string; model_label: string };
    const label = intents.general_label;
    expect(label).toBe("conocimiento del modelo, sin fuente");
    expect(label).not.toBe(intents.model_label);
    const said = spokenReply({ reply: "Unos ocho minutos.", reply_source: "general", label });
    expect(said).toBe(`${generalNotice(label)} Unos ocho minutos.`);
    expect(said.startsWith("Conocimiento del modelo, sin fuente:")).toBe(true);
    expect(spokenReply({ reply: "Vas bien.", reply_source: "model", label: intents.model_label })).toBe("Vas bien.");
    const html = render({ thread: [{ role: "assistant", text: "Unos ocho minutos.", source: "general", label }] });
    expect(html).toMatch(/assistant-general">Conocimiento del modelo, sin fuente: <\/span>Unos ocho minutos\./);
    expect(html).not.toContain(intents.model_label);
  });

  it("la propuesta campo a campo, con quien firma, Confirmar y Cancelar", () => {
    const html = render({ pending: { fields: [{ name: "value", value: "2" }], signer: "Ana" } });
    expect(html).toContain("Propuesta sin firmar");
    expect(html).toMatch(/<dt>value<\/dt><dd>2<\/dd>/);
    expect(html).toMatch(/<dt>Firma<\/dt><dd>Ana<\/dd>/);
    expect(html).toContain("Confirmar");
    expect(html).toContain("Cancelar");
  });

  it("con la privacidad, el hilo va tapado", () => {
    expect(render({ privacy: true, thread: [{ role: "user", text: "x" }] })).toContain("assistant-thread privacy-blur");
    const proposal = render({ privacy: true, pending: { fields: [{ name: "value", value: "2" }], signer: "x" } });
    expect(proposal).toContain('<dl class="privacy-blur">');
  });
});
