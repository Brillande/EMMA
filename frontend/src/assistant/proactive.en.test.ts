/**
 * La iniciativa propia en inglés (`proactive.ts`, `lib/i18n.ts`): los rótulos de navegación que
 * EMMA dice sin que se lo pidan, el mando del silencio y lo que se dice al leer un panel. El texto
 * del backend (resumen, frases de alerta, nombre de cada medida) pasa tal cual: aquí es de mentira.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { VoiceAvailabilityContext } from "../components/ReadAloud";
import type { RoutineState, RoutinesView } from "../lib/api";
import { ProactiveControls } from "./ProactiveControls";
import {
  GREETING,
  INITIAL_ALERT_MEMORY,
  MISSION_LABEL,
  NEW_ALERT,
  ROUTINE_LABEL,
  routineNotices,
  silenceFor,
  statusNotices,
} from "./proactive";
import { MORE_ON_SCREEN, NAME_COVERED, PANEL_COVERED, PANEL_NOT_FOUND, readableLines } from "./uiTargets";

const SCOPE = "crew|crew-01";
const T = 1_000_000;

function routine(key: string, state: RoutineState["state"]): RoutineState {
  return {
    key,
    display: key,
    display_es: `measurement ${key}`,
    period_hours: 6,
    basis: "design",
    state,
    last_run: null,
    last_success: null,
  };
}

function view(routines: RoutineState[], extra: Partial<RoutinesView> = {}): RoutinesView {
  return {
    now: "2026-11-03T00:00:00+00:00",
    counts: {},
    routines,
    active_event: null,
    event_note: null,
    event_over_note: null,
    mission_level: "nominal",
    mission_level_display: "nominal",
    suspended_note: null,
    ...extra,
  };
}

afterEach(() => silenceFor(0));

describe("lo que EMMA dice por su cuenta", () => {
  it("los rótulos fijos", () => {
    expect([GREETING, NEW_ALERT, ROUTINE_LABEL, MISSION_LABEL]).toEqual([
      "Hello, I am EMMA.",
      "New alert:",
      "Periodic measurement:",
      "Mission level:",
    ]);
  });

  it("al entrar: el saludo, la consola, de quién es y el resumen del backend tal cual", () => {
    const { notices } = statusNotices(INITIAL_ALERT_MEMORY, {
      scope: SCOPE,
      console: "Crew console",
      subject: "crew-01",
      summary: "Backend summary",
      alerts: [],
      annunciation: new Map<string, string>(),
      acknowledged: new Set<string>(),
      privacy: false,
      now: T,
    });
    expect(notices[0]?.chunks).toEqual(["Hello, I am EMMA. Crew console, crew member crew-01. Status: Backend summary."]);
  });

  it("una medida que pasa a deberse: su nombre del backend y la palabra inglesa de su estado", () => {
    const before = routineNotices(null, view([routine("bp", "al-dia"), routine("spo2", "al-dia")]), SCOPE, T);
    const after = routineNotices(
      before.memory,
      view([routine("bp", "atrasada"), routine("spo2", "rota")], { mission_level: "reduced", mission_level_display: "reduced" }),
      SCOPE,
      T + 1,
    );
    expect(after.notices.map((notice) => notice.chunks)).toEqual([
      ["Mission level: reduced."],
      ["Periodic measurement: measurement bp, overdue."],
      ["Periodic measurement: measurement spo2, no good reading."],
    ]);
  });
});

describe("el mando", () => {
  const render = (silenced: number) =>
    renderToStaticMarkup(
      createElement(
        VoiceAvailabilityContext.Provider,
        { value: "ready" },
        createElement(ProactiveControls, { on: true, onChange: () => undefined, silenced }),
      ),
    );

  it("el modo y el silencio, con su aviso de que lo que interrumpe se sigue diciendo", () => {
    const on = render(0);
    expect(textNodes(on)).toContain("EMMA takes the initiative");
    expect(textNodes(on)).toContain("Silence 15 min");
    const quiet = textNodes(render(Date.UTC(2026, 10, 3, 12, 30))).join(" | ");
    expect(quiet).toMatch(/Silent until [^|]+; alerts that interrupt are still spoken/);
    expect(quiet).toContain("End the silence");
    expect(on + quiet).not.toMatch(/Silencio|iniciativa|Quitar/);
  });
});

describe("leer un panel", () => {
  it("el nombre tapado y el corte de un panel largo se dicen en inglés", () => {
    expect([MORE_ON_SCREEN, PANEL_COVERED, PANEL_NOT_FOUND, NAME_COVERED]).toEqual([
      "There is more on screen.",
      "That panel is covered by privacy: I am not reading it.",
      "I cannot find that panel on screen: I am not reading it.",
      "crew member hidden",
    ]);
    expect(readableLines("Status of Ana\n\nAna slept 7 h", ["Ana"])).toEqual([
      "Status of crew member hidden",
      "crew member hidden slept 7 h",
    ]);
    const long = Array.from({ length: 60 }, (_, index) => `line ${index}`).join("\n");
    expect(readableLines(long, []).at(-1)).toBe("There is more on screen.");
  });
});
