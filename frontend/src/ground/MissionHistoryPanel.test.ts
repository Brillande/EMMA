import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, textLines } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import { ApiError, type MissionHistory } from "../lib/api";
import { arrivalCut } from "../lib/crew";
import { requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { MissionHistoryGround } from "./MissionHistoryPanel";

/**
 * El historial misión a misión en la consola de Tierra (§5.36.4): de solo lectura, con el corte
 * del retardo. Que lo firmado después del corte no llega lo prueba el backend
 * (`tests/test_mission_history.py`); aquí, que el panel pide con ese corte, que no ofrece
 * ningún mando de declarar y que pinta lo del backend tal cual.
 */

const declared: MissionHistory = {
  subject: "crew-01",
  declared: true,
  scope: "ALCANCE-DEL-BACKEND",
  limits: { missions: 20, name_length: 80 },
  days_basis: "BASE-DE-LOS-DIAS",
  text: "DECLARADAS-DOS",
  missions: [
    { name: "Expedición 1", start: "2021-04-01", end: "2021-10-01", days: 183, dose_msv: 80.25 },
    { name: "Artemis II", start: "2024-03-01", end: "2024-03-11", days: 10, dose_msv: null },
  ],
  dose_sum_msv: 80.25,
  missions_without_dose: 1,
  declared_by: "CDR",
  recorded: "2026-10-22T10:00:00+00:00",
  ledger_index: 7,
  checks: [
    { key: "missions", matches: false, text: "COTEJO-NO-CASA" },
    { key: "dose", matches: null, text: "COTEJO-SIN-CON-QUE" },
  ],
};

const render = (
  data: MissionHistory | null,
  oneWayMinutes: number | null = 20,
  unavailable: ReturnType<typeof requestOutcome> | null = null,
) => renderToStaticMarkup(createElement(MissionHistoryGround, { data, unavailable, oneWayMinutes }));

describe("el corte de Tierra para lo declarado a bordo", () => {
  it("es el reloj menos un tiempo de luz; sin efemérides, ninguno", () => {
    // La cuenta vive en `lib/crew.ts` (`arrivalCut`, §5.37.17), la misma de las ecografías y el dolor.
    const now = Date.parse("2026-10-23T12:00:00Z");
    expect(arrivalCut(20, now)?.toISOString()).toBe("2026-10-23T11:40:00.000Z");
    expect(arrivalCut(0, now)?.toISOString()).toBe("2026-10-23T12:00:00.000Z");
    expect(arrivalCut(null, now)).toBeUndefined();
  });

  it("el panel pide el historial con ese corte, no sin él", () => {
    const source = readFileSync(fileURLToPath(new URL("./MissionHistoryPanel.tsx", import.meta.url)), "utf8");
    // Con el último tiempo de luz, pero sin volver a pedir cada vez que cambia un poco
    // (`useArrivalCheck`: cada 30 s y al llegar o perderse las efemérides).
    expect(source).toContain("const { checkKey, cutNow } = useArrivalCheck(oneWayMinutes);");
    expect(source).toContain(".missionHistory(subject, cutNow())");
    expect(source).toContain("}, [subject, checkKey, cutNow]);");
    // Lo pintado es del tripulante que se mira, no del anterior.
    expect(source).toContain("loaded?.subject === subject ? loaded.body : null");
    const ground = readFileSync(fileURLToPath(new URL("./GroundConsole.tsx", import.meta.url)), "utf8");
    expect(ground).toContain("<MissionHistoryPanel subject={status.subject} oneWayMinutes={oneWay} />");
  });
});

describe("<MissionHistoryGround>", () => {
  it("es de solo lectura: ni formulario ni mando de declarar", () => {
    const html = render(declared);
    expect(html).not.toContain("<form");
    expect(html).not.toContain("<input");
    expect(html).not.toContain("<button");
    expect(html).not.toContain("Declarar");
  });

  it("pinta lo del backend tal cual: alcance, tabla, cotejos con su marca y quién lo declaró", () => {
    const html = render(declared);
    expect(html).toMatch(taggedPictogram("h2", uiPictogram("previous"), "Historial misión a misión</h2>"));
    const lines = textLines(html);
    for (const text of ["ALCANCE-DEL-BACKEND", "DECLARADAS-DOS", "Expedición 1", "2021-04-01", "183", "80,25"]) {
      expect(lines).toContain(text);
    }
    expect(html).toMatch(markedHtml("shape-triangle", "COTEJO-NO-CASA", "yellow"));
    expect(html).toMatch(markedHtml("ring-dotted", "COTEJO-SIN-CON-QUE", "cyan"));
    expect(html).toMatch(markedHtml("ring-dotted", "sin dosis declarada", "cyan"));
    expect(lines).toContain("Declarado por CDR.");
  });

  it("dice que lo firmado hace menos de un tiempo de luz no ha llegado; sin retardo, no lo dice", () => {
    const html = render(declared, 20);
    expect(html).toContain(`data-pictogram="${uiPictogram("lightTime")}"`);
    expect(textLines(html).join(" ")).toContain("está en tránsito y todavía no se ve aquí.");
    expect(render(declared, null)).not.toContain("tránsito");
  });

  it("sin declarar, lo dice el backend; cargando o sin respuesta, la marca de lo que fue", () => {
    const empty: MissionHistory = {
      subject: "crew-01",
      declared: false,
      scope: "ALCANCE-DEL-BACKEND",
      limits: { missions: 20, name_length: 80 },
      text: "SIN-HISTORIAL",
      missions: [],
      checks: [],
    };
    expect(textLines(render(empty))).toContain("SIN-HISTORIAL");
    expect(render(null)).toMatch(markedHtml("refresh", "Cargando…"));
    const refused = render(null, 20, requestOutcome(new ApiError(409, "DETALLE")));
    expect(refused).toMatch(markedHtml("shape-triangle", "Sin datos: DETALLE", "yellow"));
  });

  it("un refresco que falla no borra lo que ya se veía: lo deja, con la marca del fallo", () => {
    const html = render(declared, 20, requestOutcome(new ApiError(409, "OCUPADO")));
    expect(html).toMatch(markedHtml("shape-triangle", "No se pudo actualizar: OCUPADO", "yellow"));
    expect(textLines(html)).toContain("Expedición 1");
    expect(textLines(html)).toContain("Declarado por CDR.");
    expect(html).not.toContain("Sin datos: OCUPADO");
  });
});

describe("<MissionHistoryGround>: las fichas del tablero", () => {
  it("cuántas misiones, la dosis sumada y cuántas van sin dosis, con la suma parcial dicha", () => {
    const html = render(declared);
    expect(html).toContain('aria-label="Historial declarado, en cifras"');
    expect(html).toMatch(/Misiones previas<\/span><span class="stat-value"><span class="num">2<\/span>/);
    expect(html).toMatch(/Dosis sumada<\/span><span class="stat-value"><span class="num">80,25<\/span> <span class="stat-unit">mSv<\/span>/);
    expect(html).toMatch(markedHtml("ring-dotted", "parcial: faltan dosis", "cyan"));
    expect(html).toMatch(/Misiones sin dosis<\/span><span class="stat-value"><span class="num">1<\/span>/);
  });

  it("sin ninguna dosis conocida, la ficha lo dice con el cian del dato ausente, no con un cero", () => {
    const html = render({ ...declared, dose_sum_msv: null, missions_without_dose: 2 });
    expect(html).toMatch(markedHtml("ring-dotted", "sin dosis declarada", "cyan"));
    expect(html).not.toMatch(/Dosis sumada<\/span><span class="stat-value">/);
  });

  it("con todas las dosis, la suma no se dice parcial", () => {
    expect(render({ ...declared, missions_without_dose: 0 })).not.toContain("parcial");
  });

  it("en cursiva si el refresco falló; sin misiones o en la clásica, sin fichas", () => {
    expect(render(declared, 20, requestOutcome(new ApiError(503, "CAIDO")))).toContain('class="stat-tile stale"');
    expect(render({ ...declared, missions: [] })).not.toContain("history-board");
    const classic = renderToStaticMarkup(
      createElement(
        LookContext.Provider,
        { value: "classic" },
        createElement(MissionHistoryGround, { data: declared, unavailable: null, oneWayMinutes: 20 }),
      ),
    );
    expect(classic).not.toContain("history-board");
  });
});
