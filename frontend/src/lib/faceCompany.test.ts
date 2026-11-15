import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DisplayControls, DisplayModesContext, PresenceStrip, ScreenTop, activeModes } from "../components/DisplayControls";
import { DEFAULT_MODES, type DisplayModes, parseModes } from "../components/displayModes";
import {
  COMPANY_ARRIVE_MS,
  COMPANY_GAP_MS,
  COMPANY_LEAVE_MS,
  type CompanyEvent,
  type CompanyState,
  NO_COMPANY,
  PROPOSAL_TEXT,
  PROTECTED_TEXT,
  type PresenceNotice,
  companyStep,
  presenceNotice,
  presenceText,
} from "./faceCompany";
import { DETECTION_INTERVAL_MS, type FaceReading } from "./faceOrientation";

/**
 * Otra persona delante (§5.40, demostración): la histéresis que separa a una persona de un
 * parpadeo del detector, el aviso que queda y lo que se ve en la franja y en los mandos.
 */

const ONE: FaceReading = { kind: "one", angle: 0 };
const NONE: FaceReading = { kind: "none" };
const TWO: FaceReading = { kind: "several", count: 2 };

/** Una búsqueda cada `DETECTION_INTERVAL_MS`, como la cámara; devuelve los sucesos con su hora. */
function run(readings: readonly FaceReading[], start = 0, from: CompanyState = NO_COMPANY) {
  let state = from;
  const events: { at: number; event: Exclude<CompanyEvent, null> }[] = [];
  readings.forEach((reading, index) => {
    const at = start + index * DETECTION_INTERVAL_MS;
    const step = companyStep(state, reading, at);
    state = step.state;
    if (step.event !== null) events.push({ at, event: step.event });
  });
  return { state, events };
}

const times = (reading: FaceReading, count: number) => Array.from({ length: count }, () => reading);

describe("la histéresis", () => {
  it("los parámetros: la llegada pide una racha, la ida pide más tiempo que la llegada", () => {
    expect(COMPANY_ARRIVE_MS).toBeGreaterThan(DETECTION_INTERVAL_MS * 2);
    expect(COMPANY_GAP_MS).toBeGreaterThan(DETECTION_INTERVAL_MS);
    expect(COMPANY_GAP_MS).toBeLessThan(COMPANY_ARRIVE_MS);
    expect(COMPANY_LEAVE_MS).toBeGreaterThan(COMPANY_ARRIVE_MS);
  });

  it("una sola cara, o ninguna, nunca es otra persona", () => {
    expect(run([...times(ONE, 40), ...times(NONE, 40)]).events).toEqual([]);
  });

  it("varias caras seguidas durante la racha: llega otra persona, una vez", () => {
    const { state, events } = run(times(TWO, 30));
    expect(events).toEqual([{ at: COMPANY_ARRIVE_MS, event: "arrived" }]);
    expect(state.present).toBe(true);
  });

  it("varias caras un instante no bastan", () => {
    const blink = Math.floor(COMPANY_ARRIVE_MS / DETECTION_INTERVAL_MS);
    expect(run([...times(TWO, blink), ...times(ONE, 20)]).events).toEqual([]);
  });

  it("un hueco corto sin la segunda cara no rompe la racha; uno largo, sí", () => {
    // Una búsqueda suelta sin ella, en medio: llega igual, a la misma hora.
    const short = run([...times(TWO, 3), ONE, ...times(TWO, 10)]);
    expect(short.events).toEqual([{ at: COMPANY_ARRIVE_MS, event: "arrived" }]);
    // Un hueco de COMPANY_GAP_MS o más: la racha vuelve a empezar después.
    const gap = Math.ceil(COMPANY_GAP_MS / DETECTION_INTERVAL_MS) + 1;
    const long = run([...times(TWO, 3), ...times(ONE, gap), ...times(TWO, 10)]);
    const restart = (3 + gap) * DETECTION_INTERVAL_MS;
    expect(long.events).toEqual([{ at: restart + COMPANY_ARRIVE_MS, event: "arrived" }]);
  });

  it("con otra persona delante, se va solo cuando deja de verse un rato largo", () => {
    const arrived = run(times(TWO, 10)).state;
    const start = 10 * DETECTION_INTERVAL_MS;
    const lastSeen = start - DETECTION_INTERVAL_MS;
    // Parpadeos de la segunda cara con huecos cortos: sigue delante, sin sucesos.
    expect(run([...times(ONE, 4), TWO, ...times(ONE, 4), TWO], start, arrived).events).toEqual([]);
    // Sin ella mucho rato: se va una vez, a COMPANY_LEAVE_MS de la última vez que se vio.
    const gone = run(times(NONE, 30), start, arrived);
    expect(gone.events).toEqual([{ at: lastSeen + COMPANY_LEAVE_MS, event: "left" }]);
    expect(gone.state).toEqual(NO_COMPANY);
  });

  it("si vuelve después de irse, llega otra vez", () => {
    const readings = [...times(TWO, 10), ...times(ONE, 20), ...times(TWO, 10)];
    expect(run(readings).events.map((item) => item.event)).toEqual(["arrived", "left", "arrived"]);
  });

  it("un reloj que va hacia atrás vuelve a empezar sin suceso", () => {
    const arrived = run(times(TWO, 10)).state;
    expect(companyStep(arrived, NONE, 0)).toEqual({ state: NO_COMPANY, event: null });
    expect(companyStep(arrived, TWO, 0)).toEqual({ state: { present: false, since: 0, lastSeveral: 0 }, event: null });
  });
});

describe("el aviso", () => {
  const states: PresenceNotice[] = [null, "proposed", "protected"];

  it("al llegar otra persona: propuesta sin el modo automático, privacidad puesta con él", () => {
    for (const current of states) {
      expect(presenceNotice(current, { kind: "arrived", auto: false })).toBe("proposed");
      expect(presenceNotice(current, { kind: "arrived", auto: true })).toBe("protected");
    }
  });

  it("la propuesta se va si la persona se va, si se contesta o si la cámara se apaga", () => {
    for (const kind of ["left", "accepted", "dismissed", "cameraOff"] as const) {
      expect(presenceNotice("proposed", { kind })).toBeNull();
    }
    expect(presenceNotice("proposed", { kind: "privacyOff" })).toBe("proposed");
  });

  it("la privacidad puesta sola se queda hasta que se quita: apagar la cámara no la quita", () => {
    for (const kind of ["left", "accepted", "dismissed", "cameraOff"] as const) {
      expect(presenceNotice("protected", { kind })).toBe("protected");
    }
    expect(presenceNotice("protected", { kind: "privacyOff" })).toBeNull();
  });

  it("las frases dicen lo que pasa, sin nada clínico, y la de ponerla sola dice que la cámara se apaga", () => {
    expect(presenceText("proposed")).toBe(PROPOSAL_TEXT);
    expect(PROPOSAL_TEXT).toBe("Hay otra persona delante: ¿activo la privacidad?");
    expect(presenceText("protected")).toBe(PROTECTED_TEXT);
    expect(PROTECTED_TEXT).toContain("La cámara se ha apagado");
    expect(PROTECTED_TEXT).toContain("hasta que la quites");
  });
});

describe("el modo guardado", () => {
  it("apagado de partida; un valor de antes de existir se lee con él apagado", () => {
    expect(DEFAULT_MODES.autoPrivacy).toBe(false);
    expect(parseModes('{"lowVision": true, "followFace": true}').autoPrivacy).toBe(false);
    expect(parseModes('{"autoPrivacy": true}').autoPrivacy).toBe(true);
    expect(parseModes('{"autoPrivacy": "sí"}').autoPrivacy).toBe(false);
  });

  it("el rótulo plegado lo dice solo con la cámara mirando", () => {
    expect(activeModes({ ...DEFAULT_MODES, autoPrivacy: true }, true)).not.toContain("privacidad automática");
    expect(activeModes({ ...DEFAULT_MODES, autoPrivacy: true, followFace: true }, true)).toContain("privacidad automática");
  });
});

const withModes = (modes: Partial<DisplayModes>, extra: object, element: Parameters<typeof createElement>[0]) =>
  renderToStaticMarkup(
    createElement(
      DisplayModesContext.Provider,
      { value: { modes: { ...DEFAULT_MODES, ...modes }, update: () => undefined, ...extra } },
      createElement(element),
    ),
  );

describe("en la pantalla", () => {
  it("el mando dice su estado, que es una demostración y que solo cuenta caras", () => {
    const off = withModes({}, {}, DisplayControls);
    expect(off).toMatch(/aria-pressed="false"[^>]*>.*?Privacidad automática con otra cara/);
    expect(off).toContain("Funciona con «Seguir la cara (demo)» encendido.");
    expect(off).toContain("Es una demostración sin validar, y solo cuenta caras.");
    expect(withModes({ followFace: true }, {}, DisplayControls)).toContain("EMMA propone la privacidad");
    expect(withModes({ followFace: true, autoPrivacy: true }, {}, DisplayControls)).toContain(
      "EMMA pone la privacidad sola y lo dice",
    );
  });

  it("la propuesta va en la franja con sus dos mandos; sin aviso no hay nada", () => {
    const html = renderToStaticMarkup(createElement(PresenceStrip, { notice: "proposed", privacy: false, answer: undefined }));
    expect(html).toContain(PROPOSAL_TEXT);
    expect(html).toContain(">Activar la privacidad</button>");
    expect(html).toContain(">No, seguir así</button>");
    expect(html).toContain("Demostración, sin validar");
    expect(renderToStaticMarkup(createElement(PresenceStrip, { notice: null, privacy: false, answer: undefined }))).toBe("");
    // Con la privacidad ya puesta no se pregunta.
    expect(renderToStaticMarkup(createElement(PresenceStrip, { notice: "proposed", privacy: true, answer: undefined }))).toBe("");
  });

  it("puesta sola, dice por qué mientras la privacidad sigue", () => {
    const html = renderToStaticMarkup(createElement(PresenceStrip, { notice: "protected", privacy: true, answer: undefined }));
    expect(html).toContain("Privacidad puesta sola: había otra persona delante");
    expect(html).toContain("La cámara está apagada");
    expect(renderToStaticMarkup(createElement(PresenceStrip, { notice: "protected", privacy: false, answer: undefined }))).toBe("");
  });

  it("la región viva del lector está siempre, vacía hasta que hay algo que decir, y fuera de ella los mandos", () => {
    expect(withModes({}, {}, ScreenTop)).toContain('<span class="sr-only" role="status" aria-atomic="false"></span>');
    const html = withModes(
      { followFace: true },
      { presence: "proposed", presenceMessages: [{ id: 0, text: PROPOSAL_TEXT }] },
      ScreenTop,
    );
    expect(html).toMatch(new RegExp(`role="status" aria-atomic="false"><span>${PROPOSAL_TEXT.replace("?", "\\?")}</span></span>`));
    const region = /<span class="sr-only" role="status" aria-atomic="false">(.*?)<\/span><\/span>/.exec(html)?.[1] ?? "";
    expect(region).not.toContain("<button");
    expect(html).toContain(">Activar la privacidad</button>");
  });
});
