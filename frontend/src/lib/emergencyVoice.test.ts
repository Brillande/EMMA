import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EmergencyNotice } from "../components/EmergencyVoice";
import { ReadAloud, type Speaker } from "../components/ReadAloud";
import {
  EMERGENCY_EVENT,
  EMERGENCY_INTRO,
  EMERGENCY_WINDOW_MS,
  type EscapeKey,
  type EscapeSeries,
  HOLD_IDLE,
  HOLD_MS,
  HOLD_SLOP_PX,
  type HoldInput,
  type HoldState,
  NOTHING_TO_READ,
  NO_SERIES,
  NO_VOICE_NOTICE,
  type TouchPoint,
  emergencyPlan,
  escapeStep,
  holdStep,
} from "./emergencyVoice";
import { statusSpeech } from "./speech";

/**
 * El gesto de emergencia de la voz (§5.40) sin navegador: el triple Escape, los tres dedos, qué
 * hace según haya voz o no, el aviso para el lector del sistema y el atajo del escritorio.
 */

const key = (name: string, extra: Partial<EscapeKey> = {}): EscapeKey => ({
  key: name,
  repeat: false,
  altKey: false,
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  ...extra,
});

/** Pasa las teclas por el detector; devuelve en qué pulsaciones se disparó. */
function press(sequence: readonly [EscapeKey, number][]): number[] {
  let series: EscapeSeries = NO_SERIES;
  const fired: number[] = [];
  sequence.forEach(([event, now], index) => {
    const step = escapeStep(series, event, now);
    series = step.series;
    if (step.fire) fired.push(index);
  });
  return fired;
}

const esc = key("Escape");

describe("el triple Escape", () => {
  it("tres seguidos disparan en el tercero", () => {
    expect(press([[esc, 0], [esc, 300], [esc, 600]])).toEqual([2]);
  });

  it("dos no disparan", () => {
    expect(press([[esc, 0], [esc, 300]])).toEqual([]);
  });

  it("vale justo en el límite y no pasado él", () => {
    expect(press([[esc, 0], [esc, 700], [esc, EMERGENCY_WINDOW_MS]])).toEqual([2]);
    expect(press([[esc, 0], [esc, 700], [esc, EMERGENCY_WINDOW_MS + 1]])).toEqual([]);
  });

  it("una serie lenta sigue contando las pulsaciones recientes", () => {
    // La primera caduca, pero las tres últimas caben en la ventana.
    expect(press([[esc, 0], [esc, 1400], [esc, 1800], [esc, 2200]])).toEqual([3]);
  });

  it("otra tecla en medio rompe la serie", () => {
    expect(press([[esc, 0], [key("a"), 100], [esc, 200], [esc, 300]])).toEqual([]);
    expect(press([[esc, 0], [key("Shift"), 100], [esc, 200], [esc, 300]])).toEqual([]);
  });

  it("Escape con un modificador no cuenta y rompe", () => {
    for (const modifier of ["altKey", "ctrlKey", "metaKey", "shiftKey"] as const) {
      expect(press([[esc, 0], [key("Escape", { [modifier]: true }), 100], [esc, 200], [esc, 300]])).toEqual([]);
    }
  });

  it("mantener Escape pulsado no cuenta, ni rompe lo que se llevaba", () => {
    const held = key("Escape", { repeat: true });
    expect(press([[esc, 0], [held, 50], [held, 100], [held, 150]])).toEqual([]);
    expect(press([[esc, 0], [held, 50], [esc, 200], [held, 250], [esc, 400]])).toEqual([4]);
  });

  it("al disparar empieza de cero: un cuarto Escape no repite el gesto", () => {
    expect(press([[esc, 0], [esc, 100], [esc, 200], [esc, 300]])).toEqual([2]);
    expect(press([[esc, 0], [esc, 100], [esc, 200], [esc, 300], [esc, 400], [esc, 500]])).toEqual([2, 5]);
  });

  it("un reloj que va hacia atrás no cuenta pulsaciones del futuro", () => {
    expect(press([[esc, 5000], [esc, 5100], [esc, 100]])).toEqual([]);
  });
});

const finger = (id: number, x: number, y: number): TouchPoint => ({ id, x, y });
const [f1, f2, f3] = [finger(1, 100, 100), finger(2, 200, 100), finger(3, 300, 100)];
const three = [f1, f2, f3];

/** Pasa sucesos por el detector; devuelve el estado final y en qué pasos se disparó. */
function touch(inputs: readonly HoldInput[]): { state: HoldState; fired: number[] } {
  let state: HoldState = HOLD_IDLE;
  const fired: number[] = [];
  inputs.forEach((input, index) => {
    const step = holdStep(state, input);
    state = step.state;
    if (step.fire) fired.push(index);
  });
  return { state, fired };
}

const at = (touches: readonly TouchPoint[], now: number): HoldInput => ({ type: "touches", touches, now });
const tick = (now: number): HoldInput => ({ type: "tick", now });

describe("los tres dedos", () => {
  it("quietos un segundo y levantados disparan al levantar el primero", () => {
    const { fired } = touch([at(three, 0), tick(HOLD_MS), at(three.slice(1), HOLD_MS + 200), at([], HOLD_MS + 250)]);
    expect(fired).toEqual([2]);
  });

  it("levantarlos todos a la vez también dispara", () => {
    expect(touch([at(three, 0), tick(HOLD_MS), at([], HOLD_MS + 100)]).fired).toEqual([2]);
  });

  it("cualquier suceso después del segundo arma, sin esperar al reloj", () => {
    expect(touch([at(three, 0), at(three, HOLD_MS + 10), at(three.slice(0, 2), HOLD_MS + 20)]).fired).toEqual([2]);
  });

  it("levantar antes del segundo no dispara, ni luego al volver a poner el dedo", () => {
    const { fired, state } = touch([
      at(three, 0),
      at(three.slice(0, 2), 500),
      at(three, 600),
      tick(2000),
      at([], 2100),
    ]);
    expect(fired).toEqual([]);
    expect(state).toEqual(HOLD_IDLE);
  });

  it("antes del segundo, el reloj no arma", () => {
    expect(touch([at(three, 0), tick(HOLD_MS - 1), at([], HOLD_MS)]).fired).toEqual([]);
  });

  it("mover un dedo más de la tolerancia cancela (eso es desplazar)", () => {
    const moved = [finger(1, 100, 100 + HOLD_SLOP_PX + 1), f2, f3];
    expect(touch([at(three, 0), at(moved, 300), tick(HOLD_MS), at([], HOLD_MS + 100)]).fired).toEqual([]);
    // Estando ya armado, también.
    expect(touch([at(three, 0), tick(HOLD_MS), at(moved, HOLD_MS + 50), at([], HOLD_MS + 100)]).fired).toEqual([]);
  });

  it("un temblor dentro de la tolerancia no cancela", () => {
    const shaky = [finger(1, 100 + HOLD_SLOP_PX / 2, 100), f2, f3];
    expect(touch([at(three, 0), at(shaky, 300), tick(HOLD_MS), at([], HOLD_MS + 100)]).fired).toEqual([3]);
  });

  it("uno o dos dedos (desplazar, ampliar) nunca empiezan el gesto", () => {
    const two = three.slice(0, 2);
    expect(touch([at(two, 0), tick(HOLD_MS * 3), at([], HOLD_MS * 3)]).fired).toEqual([]);
    expect(touch([at(three.slice(0, 1), 0), tick(HOLD_MS * 3), at([], HOLD_MS * 3)]).fired).toEqual([]);
  });

  it("un cuarto dedo lo deshace", () => {
    const four = [...three, finger(4, 400, 100)];
    expect(touch([at(three, 0), at(four, 200), tick(HOLD_MS), at([], HOLD_MS + 100)]).fired).toEqual([]);
  });

  it("un dedo que ya desplazaba, o dos que ampliaban, no se convierten en gesto", () => {
    const panned = finger(1, 100, 100 + HOLD_SLOP_PX + 1);
    expect(
      touch([at([f1], 0), at([panned], 100), at([panned, f2], 200), at([panned, f2, f3], 300), tick(2000), at([], 2100)])
        .fired,
    ).toEqual([]);
    const pinched = finger(2, 200 + HOLD_SLOP_PX + 1, 100);
    expect(
      touch([at([f1, f2], 0), at([f1, pinched], 100), at([f1, pinched, f3], 200), tick(2000), at([], 2100)]).fired,
    ).toEqual([]);
  });

  it("levantar uno de los primeros antes del tercero lo deshace", () => {
    expect(touch([at([f1, f2], 0), at([f2], 100), at([f2, f1, f3], 200), tick(2000), at([], 2100)]).fired).toEqual([]);
  });

  it("dedos que llegan de uno en uno cuentan desde que son tres", () => {
    const { fired } = touch([
      at(three.slice(0, 1), 0),
      at(three.slice(0, 2), 100),
      at(three, 200),
      tick(200 + HOLD_MS - 1),
      at(three, 200 + HOLD_MS),
      at([], 200 + HOLD_MS + 50),
    ]);
    expect(fired).toEqual([5]);
  });
});

describe("lo que hace el gesto", () => {
  const readout = ["Consola de tripulación, tripulante crew-01. Estado: algo.", "Alertas activas: 0."];

  it("con voz y el modo apagado: lo enciende y lee con la frase delante", () => {
    expect(emergencyPlan("ready", false, readout)).toEqual({
      kind: "speak",
      enableVoice: true,
      chunks: [EMERGENCY_INTRO, ...readout],
    });
  });

  it("con el modo encendido: vuelve a leer y no lo apaga", () => {
    const plan = emergencyPlan("ready", true, readout);
    expect(plan).toEqual({ kind: "speak", enableVoice: false, chunks: [EMERGENCY_INTRO, ...readout] });
  });

  it("sin estado todavía, la frase y que no hay nada que leer", () => {
    expect(emergencyPlan("ready", false, [])).toEqual({
      kind: "speak",
      enableVoice: true,
      chunks: [EMERGENCY_INTRO, NOTHING_TO_READ],
    });
  });

  it("sin voz: el aviso del Narrador, y el modo voz no se toca", () => {
    for (const availability of ["no-api", "no-local-voice"] as const) {
      expect(emergencyPlan(availability, false, readout)).toEqual({ kind: "notice", text: NO_VOICE_NOTICE });
    }
    expect(NO_VOICE_NOTICE).toContain("Control, tecla Windows e Intro");
  });

  it("con la privacidad, lee lo mismo que «Leer en voz alta»: sin el nombre del tripulante", () => {
    const privateReadout = statusSpeech({
      console: "Consola de tripulación",
      subject: "crew-01",
      summary: "algo",
      alerts: [],
      privacy: true,
    });
    const plan = emergencyPlan("ready", false, privateReadout);
    expect(plan.kind).toBe("speak");
    if (plan.kind === "speak") expect(plan.chunks.join(" ")).not.toContain("crew-01");
  });

  it("las frases fijas son de navegación: sin cifras escritas a mano", () => {
    for (const text of [EMERGENCY_INTRO, NOTHING_TO_READ, NO_VOICE_NOTICE]) expect(text).not.toMatch(/\d/);
    expect(EMERGENCY_INTRO).toContain("Escape tres veces");
    expect(EMERGENCY_INTRO).toContain("Alt Mayús L para parar");
  });
});

const speaker = (overrides: Partial<Speaker> = {}): Speaker => ({
  availability: "ready",
  speaking: false,
  canRepeat: false,
  say: () => undefined,
  stop: () => undefined,
  repeat: () => undefined,
  ...overrides,
});

describe("en pantalla y para el lector", () => {
  it("la región del aviso está siempre, vacía y asertiva", () => {
    const markup = renderToStaticMarkup(createElement(EmergencyNotice, { messages: [] }));
    expect(markup).toBe('<div class="sr-only"><div role="alert" aria-atomic="false"></div></div>');
  });

  it("cada aviso es un nodo nuevo", () => {
    const markup = renderToStaticMarkup(
      createElement(EmergencyNotice, { messages: [{ id: 1, text: NO_VOICE_NOTICE }] }),
    );
    expect(markup).toContain(`<p>${NO_VOICE_NOTICE}</p>`);
  });

  it("el gesto está escrito junto al mando y los botones lo llevan descrito", () => {
    const markup = renderToStaticMarkup(createElement(ReadAloud, { speaker: speaker(), read: ["x"] }));
    expect(markup).toContain("<kbd>Esc</kbd> tres veces o tres dedos un segundo");
    expect(markup).toContain("<kbd>Ctrl+Alt+V</kbd>");
    const id = /<span class="secondary shortcut" id="([^"]+)"/.exec(markup)?.[1];
    expect(id).toBeDefined();
    expect(markup).toContain(`role="group" aria-label="Voz" aria-describedby="${id}"`);
    // Dentro del plegable «Atajos» de la franja (§5.40), que sigue dentro del grupo de la voz.
    expect(markup).toMatch(
      /<details class="shortcuts strip-pop"><summary><svg [^>]*data-pictogram="circle-i"[^>]*>.*?<\/svg>Atajos<\/summary><span class="secondary shortcut" id=/,
    );
    expect(markup.indexOf("<details")).toBeGreaterThan(markup.indexOf('role="group"'));
    const speaking = renderToStaticMarkup(
      createElement(ReadAloud, { speaker: speaker({ speaking: true }), read: ["x"] }),
    );
    expect(speaking).toMatch(/Parar la voz/);
    expect(speaking).toContain("aria-describedby=");
  });
});

describe("el atajo de la aplicación de escritorio", () => {
  const main = readFileSync(fileURLToPath(new URL("../../../desktop/main.cjs", import.meta.url)), "utf8");

  it("manda el mismo suceso que escucha la página", () => {
    expect(main).toContain(`const EMERGENCY_EVENT = "${EMERGENCY_EVENT}";`);
  });

  it("registra el atajo, lo hace como gesto de la persona y lo suelta al salir", () => {
    expect(main).toContain('const EMERGENCY_SHORTCUT = "Control+Alt+V";');
    expect(main).toContain("globalShortcut.register(EMERGENCY_SHORTCUT");
    expect(main).toContain("executeJavaScript(code, true)");
    expect(main).toContain("globalShortcut.unregisterAll()");
  });

  it("se registra con la página cargada y mantenerlo pulsado no repite la lectura", () => {
    expect(main).toContain('once("did-finish-load", () => registerEmergencyShortcut(window))');
    expect(main).toMatch(/const EMERGENCY_REPEAT_MS = \d/);
    expect(main).toContain("if (!quiet) return;");
  });

  it("sigue sin preload ni IPC", () => {
    expect(main).not.toMatch(/preload\s*:/);
    expect(main).not.toMatch(/ipcMain|ipcRenderer/);
  });
});
