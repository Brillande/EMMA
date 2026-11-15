import { describe, expect, it } from "vitest";

import type { HelpRequest } from "./api";
import { LOCATING, freshRequests, groundArrival, groundHelpCut, spokenRequest, withProvisional } from "./help";

/**
 * La banda de ayuda urgente (2026-11-14): cuándo le llega a Tierra, con qué corte la pide Tierra,
 * cuáles son nuevas y qué se dice en voz alta (con las palabras del backend).
 */

const request = (index: number, nearby: HelpRequest["nearby"] = []): HelpRequest => ({
  ledger_index: index,
  subject: "crew-01",
  signed_by: "Comandante",
  reason: null,
  at: "2026-12-10T23:00:00+00:00",
  signed_at: "2026-11-14T10:00:00+00:00",
  location_display: "Laboratorio (backend)",
  nearby,
  nearby_note: nearby.length === 0 ? "texto del backend" : null,
});

describe("groundArrival", () => {
  it("la firma más un tiempo de luz; sin efemérides, no se sabe", () => {
    expect(groundArrival("2026-11-14T10:00:00+00:00", 11)?.toISOString()).toBe("2026-11-14T10:11:00.000Z");
    expect(groundArrival("2026-11-14T10:00:00+00:00", null)).toBeNull();
    expect(groundArrival("no es una fecha", 11)).toBeNull();
  });
});

describe("groundHelpCut", () => {
  it("el reloj menos un tiempo de luz; sin efemérides ni enlace, todo", () => {
    const now = Date.parse("2026-11-14T10:20:00Z");
    expect(groundHelpCut(11, null, now)?.toISOString()).toBe("2026-11-14T10:09:00.000Z");
    expect(groundHelpCut(null, null, now)).toBeUndefined();
  });
});

describe("freshRequests y spokenRequest", () => {
  it("solo las que no estaban, y se dice quién, dónde y quién está más cerca", () => {
    expect(freshRequests(new Set([1]), [request(1), request(2)]).map((item) => item.ledger_index)).toEqual([2]);
    const near = request(3, [
      { subject: "crew-04", proximity: "same_module", proximity_display: "en el mismo módulo", location_display: "Laboratorio" },
    ]);
    expect(spokenRequest("Ayuda urgente", near)).toBe(
      "Ayuda urgente: crew-01. Laboratorio (backend). crew-04, en el mismo módulo",
    );
    expect(spokenRequest("Ayuda urgente", request(4))).toBe("Ayuda urgente: crew-01. Laboratorio (backend)");
  });
});

describe("withProvisional", () => {
  it("la recién pedida va delante al momento, localizando; si ya estaba, no se duplica", () => {
    const detail = { ledger_index: 9, subject: "crew-01", signed_by: "", at: "2026-12-10T23:00:00+00:00", signed_at: "2026-11-14T10:00:00+00:00" };
    const first = withProvisional(null, detail, "Ayuda urgente");
    expect(first.open).toHaveLength(1);
    expect(first.open[0]?.location_display).toBe(LOCATING);
    expect(first.open[0]?.signed_by).toBeNull();
    expect(withProvisional(first, detail, "Ayuda urgente").open).toHaveLength(1);
    const withOld = withProvisional({ until: null, headline: "Ayuda urgente", basis: "b", open: [request(1)] }, detail, "x");
    expect(withOld.open.map((item) => item.ledger_index)).toEqual([9, 1]);
  });
});
