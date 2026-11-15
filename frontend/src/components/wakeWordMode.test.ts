import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { WakeState } from "../assistant/wake/machine";
import { UNAVAILABLE_MARK } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { DisplayControls, DisplayModesContext, MICROPHONE_ON_MARK, ScreenTop } from "./DisplayControls";
import { DEFAULT_MODES, type DisplayModes, parseModes } from "./displayModes";

/** El modo «Escuchar "EMMA"» de los mandos de pantalla (manos libres): lo guardado y lo que se ve. */

describe("lo guardado", () => {
  it("apagado de partida; un valor de antes de existir el modo se lee con él apagado", () => {
    expect(DEFAULT_MODES.wakeWord).toBe(false);
    const old = '{"lowVision": true, "privacy": false, "rotation": 90, "followFace": false}';
    expect(parseModes(old)).toEqual({ ...DEFAULT_MODES, lowVision: true, rotation: 90 });
    expect(parseModes('{"wakeWord": true}').wakeWord).toBe(true);
    expect(parseModes('{"wakeWord": "sí"}').wakeWord).toBe(false);
  });

  it("con la privacidad puesta no se escucha, aunque lo guardado lo pida", () => {
    expect(parseModes('{"wakeWord": true, "privacy": true}')).toEqual({ ...DEFAULT_MODES, privacy: true });
  });
});

const render = (element: Parameters<typeof createElement>[0], modes: Partial<DisplayModes>, wake?: WakeState) =>
  renderToStaticMarkup(
    createElement(
      DisplayModesContext.Provider,
      {
        value: {
          modes: { ...DEFAULT_MODES, ...modes },
          update: () => undefined,
          ...(wake === undefined ? {} : { wake }),
        },
      },
      createElement(element),
    ),
  );

describe("el mando", () => {
  const controls = (modes: Partial<DisplayModes>, wake?: WakeState) => render(DisplayControls, modes, wake);

  it("es un mando con su estado, su dibujo y su palabra; apagado no dice nada más", () => {
    const off = controls({});
    expect(off).toMatch(
      new RegExp(`aria-pressed="false"[^>]*>.*?data-pictogram="${uiPictogram("wakeWord")}"[^>]*>.*?</svg>Escuchar «EMMA»`),
    );
    expect(off).not.toContain("Sin probar con personas");
    const on = controls({ wakeWord: true }, { kind: "listening", armed: true });
    expect(on).toMatch(/aria-pressed="true"[^>]*>(?:(?!<button).)*Escuchar «EMMA»/);
    expect(on).toContain("«EMMA, deja de escuchar» lo apaga");
    expect(on).toContain("Solo se graba lo que se dice después de «EMMA»");
  });

  it("al oír la palabra dice «Te escucho» en una región de estado", () => {
    expect(controls({ wakeWord: true }, { kind: "recording", settled: false })).toMatch(
      /role="status"[^>]*>(?:(?!<\/span><\/span>).)*Te escucho/,
    );
  });

  it("sin escucha lo dice en gris con el círculo tachado y el motivo", () => {
    for (const reason of ["sin micrófono", "sin permiso", "sin modelo", "sin audio del navegador"] as const) {
      expect(controls({ wakeWord: true }, { kind: "unavailable", reason })).toMatch(
        new RegExp(
          `role="status"[^>]*><span class="mark ${UNAVAILABLE_MARK.className}"><svg[^>]*data-pictogram="slash-circle"[^>]*>.*?</svg>Escucha no disponible: ${reason}`,
        ),
      );
    }
  });

  it("con la privacidad puesta no se puede pulsar, y lo dice", () => {
    const html = controls({ privacy: true });
    expect(html).toMatch(/aria-pressed="false" disabled=""[^>]*>(?:(?!<button).)*Escuchar «EMMA»/);
    expect(html).toContain("Con la privacidad puesta, el micrófono no se abre");
  });
});

describe("el aviso de micrófono escuchando", () => {
  const top = (wake?: WakeState) => render(ScreenTop, {}, wake);

  it("va en el borde de arriba, en azul de aviso con su dibujo, mientras el micrófono está abierto", () => {
    expect(MICROPHONE_ON_MARK.color).toBe("blue");
    const open: WakeState[] = [
      { kind: "listening", armed: true },
      { kind: "recording", settled: false },
      { kind: "sending", settled: true },
    ];
    for (const wake of open) {
      expect(top(wake)).toMatch(
        new RegExp(
          `class="mark microphone-on ${MICROPHONE_ON_MARK.className}"><svg[^>]*data-pictogram="${uiPictogram("microphone")}"[^>]*>.*?</svg>Micrófono escuchando`,
        ),
      );
    }
    expect(top({ kind: "recording", settled: false })).toContain("Micrófono escuchando · te escucho");
  });

  it("no sale apagado, cargando ni sin micrófono", () => {
    for (const wake of [undefined, { kind: "off" }, { kind: "loading" }, { kind: "unavailable", reason: "sin permiso" }] as const) {
      expect(top(wake)).not.toContain("Micrófono escuchando");
    }
  });
});
