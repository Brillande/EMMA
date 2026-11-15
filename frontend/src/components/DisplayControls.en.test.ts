/**
 * Los mandos de «Pantalla» en inglés (`lib/i18n.ts`): modos, giro, privacidad, voz, el borde de
 * arriba y el aviso de otra persona delante. El selector de idioma no se traduce: cada idioma se
 * llama como en el suyo.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PROPOSAL_TEXT } from "../lib/faceCompany";
import { BoardDetail } from "./BoardDetail";
import { LookContext } from "./BoardOnly";
import { DisplayControls, DisplayModesContext, type DisplayModesValue, PresenceStrip, ScreenTop, activeModes } from "./DisplayControls";
import { DEFAULT_MODES, type DisplayModes } from "./displayModes";
import { OperatorInput } from "./OperatorInput";
import { Loading, Unavailable } from "./Unavailable";
import { FAILURE_MARK } from "../lib/marks";

const render = (
  element: Parameters<typeof createElement>[0],
  modes: Partial<DisplayModes> = {},
  extra: Partial<DisplayModesValue> = {},
) =>
  renderToStaticMarkup(
    createElement(
      DisplayModesContext.Provider,
      { value: { modes: { ...DEFAULT_MODES, ...modes }, update: () => undefined, ...extra } },
      createElement(element),
    ),
  );

describe("los mandos de pantalla en inglés", () => {
  it("el grupo y cada modo", () => {
    const html = render(DisplayControls);
    expect(html).toContain('role="group" aria-label="Display"');
    for (const label of [
      "Low vision",
      "High contrast",
      "Essential mode",
      "Rotate",
      "Follow the sensor",
      "Follow the face (demo)",
      "Privacy",
      "Automatic privacy with another face",
      "Listen for “EMMA”",
    ]) {
      expect(html).toContain(label);
    }
    expect(html).toContain('aria-label="Rotate the screen"');
    expect(html).not.toMatch(/Baja visión|Alto contraste|Modo esencial|Girar|Seguir|Privacidad|Escuchar/);
  });

  it("el selector de idioma nombra cada uno en el suyo y marca el inglés", () => {
    const html = render(DisplayControls);
    expect(html).toContain('role="group" aria-label="Language"');
    expect(html).toMatch(/lang="en" aria-pressed="true"/);
    expect(html).toMatch(/lang="es" aria-pressed="false"/);
    expect(html).toContain("Español");
    expect(html).toContain("English");
  });

  it("con la privacidad puesta: el mando la quita, y cámara y micrófono dicen por qué no se abren", () => {
    const html = render(DisplayControls, { privacy: true });
    expect(html).toContain("Turn privacy off");
    expect(html).toContain("With privacy on, the camera does not turn on");
    expect(html).toContain("With privacy on, the microphone does not open");
  });

  it("el seguimiento de la cara se declara sin probar, con las mismas palabras en todo el panel", () => {
    const html = render(DisplayControls, { followFace: true }, { face: "unavailable", faceProblem: "sin permiso" });
    expect(html).toContain("Camera not available: no permission");
    expect(html).toContain("Demonstration, unproven.");
    expect(html).toContain("This is an unproven demonstration, and it only counts faces.");
    expect(html).not.toMatch(/validated|certified/i);
    expect(html).not.toMatch(/sin permiso|Demostración/);
  });

  it("el resumen del plegable nombra los modos puestos", () => {
    const modes = { ...DEFAULT_MODES, lowVision: true, highContrast: true, essential: true, privacy: true, voice: true };
    expect(activeModes(modes, true).filter((item) => typeof item === "string")).toEqual([
      "low vision",
      "high contrast",
      "essential",
      "privacy",
      "voice",
    ]);
  });
});

describe("el borde de arriba en inglés", () => {
  it("la referencia de arriba y la vista girada", () => {
    expect(render(ScreenTop)).toMatch(/<\/span>Up<\/span>/);
    const turned = render(ScreenTop, { rotation: 90 });
    expect(turned).toContain("· view rotated");
    expect(turned).not.toMatch(/Arriba|vista girada/);
  });

  it("la cámara encendida se dice en inglés", () => {
    const html = render(ScreenTop, { followFace: true }, { face: "face" });
    expect(html).toContain("Camera on");
    expect(html).not.toContain("Cámara encendida");
  });

  it("la propuesta de privacidad con sus dos mandos", () => {
    const html = renderToStaticMarkup(
      createElement(PresenceStrip, { notice: "proposed", privacy: false, answer: () => undefined }),
    );
    expect(PROPOSAL_TEXT).toBe("Someone else is in front of the screen: shall I turn privacy on?");
    expect(html).toContain(PROPOSAL_TEXT);
    expect(html).toContain("Turn privacy on");
    expect(html).toContain("No, carry on like this");
    expect(html).toContain("Demonstration, unproven: only faces are counted.");
  });

  it("la privacidad puesta sola dice por qué", () => {
    const html = renderToStaticMarkup(createElement(PresenceStrip, { notice: "protected", privacy: true, answer: undefined }));
    expect(html).toContain("Privacy turned on by itself: someone else was in front of the screen");
    expect(html).toContain("The camera is off.");
  });
});

describe("piezas comunes en inglés", () => {
  it("«Ver detalle» con y sin nombre", () => {
    const detail = (label?: string) =>
      renderToStaticMarkup(
        createElement(LookContext.Provider, { value: "reference" }, createElement(BoardDetail, label === undefined ? { children: "X" } : { label, children: "X" })),
      );
    expect(detail()).toContain("Show detail</button>");
    expect(detail("Sleep")).toContain("Show detail: Sleep</button>");
    expect(detail()).not.toContain("Ver detalle");
  });

  it("el campo de quien firma, cargando y sin datos", () => {
    expect(
      renderToStaticMarkup(createElement(OperatorInput, { value: "", onChange: () => undefined, privacy: false })),
    ).toContain('placeholder="name or call sign"');
    expect(renderToStaticMarkup(createElement(Loading))).toContain("Loading…");
    expect(
      renderToStaticMarkup(createElement(Unavailable, { outcome: { mark: FAILURE_MARK, text: "REASON" } })),
    ).toContain("No data: REASON");
  });
});
