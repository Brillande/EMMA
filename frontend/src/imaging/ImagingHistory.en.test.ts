/**
 * «Ecografías recibidas» (consola de Tierra) en inglés (`lib/i18n.ts`): el título, el aviso de lo
 * que va en tránsito y las fichas del tablero.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { formatMinutes } from "../lib/format";
import { ArrivedBoard, ImagingHistory } from "./ImagingHistory";

describe("las ecografías recibidas en inglés", () => {
  it("el título y el aviso del tránsito", () => {
    const html = renderToStaticMarkup(createElement(ImagingHistory, { subject: "crew-01", oneWayMinutes: 12 }));
    expect(html).toContain('aria-label="Ultrasounds received"');
    expect(html).toContain("What was recorded on board in the last");
    expect(html).toContain(`<span class="num">${formatMinutes(12)}</span> is in transit.`);
    expect(html).not.toMatch(/Ecografías|Lo registrado|tránsito/);
  });

  it("las fichas del tablero", () => {
    const html = renderToStaticMarkup(createElement(ArrivedBoard, { rows: [], stale: false }));
    expect(html).toContain('aria-label="Ultrasounds arrived on Earth"');
    expect(html).toContain("Studies arrived");
    expect(html).toContain("Measurements arrived");
    expect(html).not.toMatch(/llegad/);
  });
});
