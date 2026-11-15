/**
 * El planificador de a bordo visto desde Tierra, en inglés (`lib/i18n.ts`): el panel, el aviso del
 * corte, la pieza de carga que comparte con los paneles del planificador y el nombre de los
 * bloques de la hoja diaria. El resto de la pestaña «Planificador» está apartado y sigue en
 * castellano.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { requestOutcome } from "../lib/marks";
import { blockLabel } from "./BriefingPanel";
import { GroundPlannerPanel } from "./GroundPlannerPanel";
import { State } from "./PlannerPanels";

describe("el planificador de a bordo en inglés", () => {
  it("el panel con corte: título, hasta cuándo y la espera", () => {
    const html = renderToStaticMarkup(createElement(GroundPlannerPanel, { oneWayMinutes: 10 }));
    expect(html).toContain('aria-label="On-board planner"');
    expect(html).toContain("What was noted on board up to");
    expect(html).toContain("; anything later is on its way.");
    expect(html).toContain("Rebuilding the planner up to the cut…");
    expect(html).not.toMatch(/Planificador|Lo anotado|Reconstruyendo/);
  });

  it("sin efemérides no hay corte y lo dice", () => {
    const html = renderToStaticMarkup(createElement(GroundPlannerPanel, { oneWayMinutes: null }));
    expect(html).toContain("No delay cut: everything noted on board is shown.");
    expect(html).not.toContain("Sin corte");
  });

  it("la pieza de carga: no se pudo leer y no se pudo actualizar, con el motivo tal cual", () => {
    const failed = requestOutcome(new Error("MOTIVO"));
    const reload = () => undefined;
    const unread = renderToStaticMarkup(createElement(State, { loaded: { data: null, failed, reload }, reading: "X" }));
    expect(unread).toContain("Could not read the planner:");
    const stale = renderToStaticMarkup(createElement(State, { loaded: { data: {}, failed, reload }, reading: "X" }));
    expect(stale).toContain("Could not refresh:");
    expect(unread + stale).not.toMatch(/No se pudo/);
  });

  it("los bloques de la hoja diaria llevan nombre inglés; uno desconocido, su clave", () => {
    expect(blockLabel("wordSearch")).toBe("Word search");
    expect(blockLabel("riddle")).toBe("Riddle");
    expect(blockLabel("otro")).toBe("otro");
  });
});
