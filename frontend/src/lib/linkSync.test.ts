import { describe, expect, it } from "vitest";

import { linkedCut } from "./crew";
import { LINK_DOWN_MARK, backlogMark, groundLinkMark, linkChange, linkInstant } from "./linkSync";
import { MISSING_MARK } from "./marks";

/*
 * El enlace con Tierra simulado en la interfaz (§5.47): el corte que se pide a las rutas de Tierra
 * nunca queda por delante del tiempo de luz ni de la caída; el instante se declara hacia atrás desde
 * la última lectura; y las marcas son las de la tabla F.5-1 (cian lo que Tierra aún no tiene,
 * amarillo con el círculo tachado el enlace caído, como el sistema Comunicaciones fuera de servicio).
 */

const LIGHT = new Date("2026-11-10T12:00:00Z");
const DROP = "2026-11-10T06:00:00+00:00";

describe("el corte de Tierra con el enlace simulado", () => {
  it("sin respuesta del enlace, el del tiempo de luz", () => {
    expect(linkedCut(LIGHT, null)).toEqual(LIGHT);
    expect(linkedCut(null, null)).toBeNull();
  });

  it("con el enlace reteniéndolo, la caída", () => {
    expect(linkedCut(LIGHT, { cut: DROP, held: true, held_since: DROP })).toEqual(new Date(DROP));
  });

  it("sin efemérides y con el enlace caído, la caída; arriba, todo", () => {
    expect(linkedCut(null, { cut: DROP, held: true, held_since: DROP })).toEqual(new Date(DROP));
    expect(linkedCut(null, { cut: null, held: false, held_since: null })).toBeNull();
  });

  it("nunca por delante del tiempo de luz ni de la caída, diga lo que diga la respuesta", () => {
    const ahead = "2026-11-10T13:00:00+00:00";
    expect(linkedCut(LIGHT, { cut: ahead, held: false, held_since: null })).toEqual(LIGHT);
    expect(linkedCut(LIGHT, { cut: ahead, held: true, held_since: DROP })).toEqual(new Date(DROP));
    for (const minutes of [0, 5, 60, 600]) {
      const light = new Date(LIGHT.getTime() + minutes * 60_000);
      const cut = linkedCut(light, { cut: DROP, held: true, held_since: DROP });
      expect(cut!.getTime()).toBeLessThanOrEqual(Math.min(light.getTime(), Date.parse(DROP)));
    }
  });
});

describe("el mando del enlace simulado", () => {
  it("el instante va hacia atrás desde la última lectura de a bordo", () => {
    expect(linkInstant("2026-11-10T12:00:00+00:00", 0, new Date(0))).toBe("2026-11-10T12:00:00.000Z");
    expect(linkInstant("2026-11-10T12:00:00+00:00", 6, new Date(0))).toBe("2026-11-10T06:00:00.000Z");
    expect(linkInstant(null, 1, new Date("2026-11-05T10:00:00Z"))).toBe("2026-11-05T09:00:00.000Z");
    expect(() => linkInstant("2026-11-10T12:00:00+00:00", -1, new Date(0))).toThrow(RangeError);
    expect(() => linkInstant("ayer", 1, new Date(0))).toThrow(RangeError);
  });

  it("ofrece el cambio contrario al vigente, con quien firma y la nota recortados", () => {
    expect(linkChange({ state: "up" }, DROP, " CMO ", " antena ")).toEqual({
      state: "down", at: DROP, note: "antena", declared_by: "CMO",
    });
    expect(linkChange({ state: "down" }, DROP, "CMO", "").state).toBe("up");
  });
});

describe("las marcas del enlace simulado", () => {
  it("cian lo que Tierra aún no tiene; nada si no falta nada", () => {
    expect(backlogMark(3)).toBe(MISSING_MARK);
    expect(backlogMark(0)).toBeNull();
    expect(groundLinkMark({ held: true })).toBe(MISSING_MARK);
    expect(groundLinkMark({ held: false })).toBeNull();
  });

  it("el enlace caído, en amarillo con el círculo tachado: no es rojo, no es una alerta", () => {
    expect(LINK_DOWN_MARK.pictogram).toBe("slash-circle");
    expect(LINK_DOWN_MARK.className).toContain("yellow");
  });
});
