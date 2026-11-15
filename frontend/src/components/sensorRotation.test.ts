import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { UNAVAILABLE_MARK } from "../lib/marks";
import { formatUtc } from "../lib/format";
import type { SensorSource, SensorStatus } from "../lib/orientation";
import { uiPictogram } from "../lib/uiMarks";
import { DisplayControls, DisplayModesContext } from "./DisplayControls";
import { DEFAULT_MODES, type DisplayModes, parseModes } from "./displayModes";

/** El modo «seguir el sensor» de los mandos de pantalla (§5.40): lo guardado y lo que se ve. */

describe("lo guardado", () => {
  it("un valor de antes de existir el modo se sigue leyendo, con el modo apagado", () => {
    const old = '{"lowVision": true, "essential": false, "privacy": false, "rotation": 270}';
    expect(parseModes(old)).toEqual({ ...DEFAULT_MODES, lowVision: true, rotation: 270, followSensor: false });
  });

  it("el modo se lee si está, y lo que no es sí o no queda apagado", () => {
    expect(parseModes('{"followSensor": true}').followSensor).toBe(true);
    expect(parseModes('{"followSensor": "si"}').followSensor).toBe(false);
  });
});

describe("los mandos", () => {
  const controls = (
    modes: Partial<DisplayModes>,
    sensor?: SensorStatus,
    extra: { sensorSource?: SensorSource; upSince?: Date } = {},
  ) =>
    renderToStaticMarkup(
      createElement(
        DisplayModesContext.Provider,
        {
          value: {
            modes: { ...DEFAULT_MODES, ...modes },
            update: () => undefined,
            ...(sensor === undefined ? {} : { sensor }),
            ...extra,
          },
        },
        createElement(DisplayControls),
      ),
    );

  it("seguir el sensor es un mando con su estado, su dibujo y su palabra", () => {
    const off = controls({});
    expect(off).toMatch(new RegExp(`aria-pressed="false"[^>]*>.*?data-pictogram="${uiPictogram("followSensor")}"[^>]*>.*?</svg>Seguir el sensor`));
    expect(off).not.toContain("sensor-state");
    const on = controls({ followSensor: true }, "waiting");
    expect(on).toMatch(/aria-pressed="true"[^>]*>(?:(?!<button).)*Seguir el sensor/);
  });

  it("sin sensor lo dice en gris con el círculo tachado, y el giro manual sigue ahí", () => {
    const html = controls({ followSensor: true, rotation: 90 }, "unavailable");
    expect(html).toContain('role="status"');
    expect(html).toMatch(
      new RegExp(`class="mark ${UNAVAILABLE_MARK.className}"><svg[^>]*data-pictogram="slash-circle"[^>]*>.*?</svg>Sensor de giro no disponible`),
    );
    for (const rotation of [0, 90, 180, 270]) expect(html).toContain(`<span class="num">${rotation}</span> °`);
    expect(html).not.toContain("Esto es arriba");
  });

  it("mientras espera lo dice, y leyendo ofrece fijar «esto es arriba»", () => {
    expect(controls({ followSensor: true }, "waiting")).toContain("Esperando al sensor de giro");
    const reading = controls({ followSensor: true }, "reading");
    expect(reading).toMatch(
      new RegExp(`<button type="button" class="command"><span class="mark"><svg[^>]*data-pictogram="${uiPictogram("screenTop")}"[^>]*>.*?</svg>Esto es arriba`),
    );
    expect(reading).not.toContain("Sensor de giro no disponible");
    expect(reading).not.toContain("Esperando");
  });

  it("leyendo dice desde cuándo vale el «arriba», y si la fuente solo vale en Tierra", () => {
    const since = new Date("2026-11-03T10:20:00Z");
    const gyro = controls({ followSensor: true }, "reading", { sensorSource: "gyroscope", upSince: since });
    expect(gyro).toContain(`Arriba fijado: ${formatUtc(since)}`);
    expect(gyro).not.toContain("solo vale en Tierra");
    const earth = controls({ followSensor: true }, "reading", { sensorSource: "earth", upSince: since });
    expect(earth).toContain("Orientación del navegador: solo vale en Tierra");
  });
});
