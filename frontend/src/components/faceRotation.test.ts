import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { FaceUnavailable } from "../lib/faceCamera";
import type { FaceStatus } from "../lib/faceOrientation";
import { UNAVAILABLE_MARK } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { CAMERA_ON_MARK, DisplayControls, DisplayModesContext, ScreenTop } from "./DisplayControls";
import { DEFAULT_MODES, type DisplayModes, parseModes } from "./displayModes";

/** El modo «seguir la cara» de los mandos de pantalla (§5.40, demostración): lo guardado y lo que se ve. */

describe("lo guardado", () => {
  it("un valor de antes de existir el modo se sigue leyendo, con el modo apagado", () => {
    const old = '{"lowVision": false, "essential": true, "privacy": false, "rotation": 90, "followSensor": true}';
    expect(parseModes(old)).toEqual({ ...DEFAULT_MODES, essential: true, rotation: 90, followSensor: true });
    expect(DEFAULT_MODES.followFace).toBe(false);
  });

  it("el modo se lee si está, y lo que no es sí o no queda apagado", () => {
    expect(parseModes('{"followFace": true}').followFace).toBe(true);
    expect(parseModes('{"followFace": 1}').followFace).toBe(false);
  });

  it("con la privacidad puesta la cámara no se enciende, aunque lo guardado lo pida", () => {
    expect(parseModes('{"followFace": true, "privacy": true}')).toEqual({ ...DEFAULT_MODES, privacy: true });
  });
});

const render = (
  element: Parameters<typeof createElement>[0],
  modes: Partial<DisplayModes>,
  face?: FaceStatus,
  faceProblem?: FaceUnavailable,
) =>
  renderToStaticMarkup(
    createElement(
      DisplayModesContext.Provider,
      {
        value: {
          modes: { ...DEFAULT_MODES, ...modes },
          update: () => undefined,
          ...(face === undefined ? {} : { face }),
          ...(faceProblem === undefined ? {} : { faceProblem }),
        },
      },
      createElement(element),
    ),
  );

describe("los mandos", () => {
  const controls = (modes: Partial<DisplayModes>, face?: FaceStatus, problem?: FaceUnavailable) =>
    render(DisplayControls, modes, face, problem);

  it("seguir la cara es un mando con su estado, su dibujo y su palabra, y dice que es una demostración", () => {
    const off = controls({});
    expect(off).toMatch(
      new RegExp(`aria-pressed="false"[^>]*>.*?data-pictogram="${uiPictogram("followFace")}"[^>]*>.*?</svg>Seguir la cara \\(demo\\)`),
    );
    expect(off).not.toContain("Demostración, sin validar");
    const on = controls({ followFace: true }, "starting");
    expect(on).toMatch(/aria-pressed="true"[^>]*>(?:(?!<button).)*Seguir la cara/);
    expect(on).toContain("Preparando la cámara");
    expect(on).toContain("Demostración, sin validar. Solo se usa el giro de la cara");
  });

  it("sin cámara lo dice en gris con el círculo tachado y el motivo, y el giro manual sigue ahí", () => {
    const html = controls({ followFace: true, rotation: 180 }, "unavailable", "sin permiso");
    expect(html).toMatch(
      new RegExp(
        `role="status"[^>]*><span class="mark ${UNAVAILABLE_MARK.className}"><svg[^>]*data-pictogram="slash-circle"[^>]*>.*?</svg>Cámara no disponible: sin permiso`,
      ),
    );
    for (const rotation of [0, 90, 180, 270]) expect(html).toContain(`<span class="num">${rotation}</span> °`);
  });

  it("con dos caras no gira y lo dice; sin cara dice qué hace la vista", () => {
    expect(controls({ followFace: true }, "several")).toContain("Hay más de una cara: la vista no gira");
    expect(controls({ followFace: true }, "noFace")).toContain("No se ve ninguna cara: la vista se queda como está");
    expect(controls({ followFace: true, followSensor: true }, "noFace")).toContain(
      "No se ve ninguna cara: sigue el sensor de giro",
    );
    expect(controls({ followFace: true }, "face")).toContain("Siguiendo la cara");
  });

  it("con la privacidad puesta el mando no se puede pulsar, y lo dice", () => {
    const html = controls({ privacy: true }, "off");
    expect(html).toMatch(/aria-pressed="false" disabled=""[^>]*>(?:(?!<button).)*Seguir la cara/);
    expect(html).toContain("Con la privacidad puesta, la cámara no se enciende");
  });
});

describe("el aviso de cámara encendida", () => {
  const top = (face?: FaceStatus) => render(ScreenTop, {}, face);

  it("va en el borde de arriba, en azul de aviso con su dibujo, mientras la cámara está encendida", () => {
    expect(CAMERA_ON_MARK.color).toBe("blue");
    for (const face of ["noFace", "face", "several"] as const) {
      expect(top(face)).toMatch(
        new RegExp(
          `class="mark camera-on ${CAMERA_ON_MARK.className}"><svg[^>]*data-pictogram="${uiPictogram("cameraOn")}"[^>]*>.*?</svg>Cámara encendida`,
        ),
      );
    }
  });

  it("no sale con la cámara apagada, preparándose o no disponible", () => {
    for (const face of [undefined, "off", "starting", "unavailable"] as const) {
      expect(top(face)).not.toContain("Cámara encendida");
    }
  });
});
