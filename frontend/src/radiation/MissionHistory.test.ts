import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, thSign } from "../advisor/visibleText";
import { ApiError, type MissionHistory } from "../lib/api";
import { requestOutcome } from "../lib/marks";
import { MissionHistoryView, checkMark, isHistoryNotice, parseDose } from "./MissionHistory";

/**
 * El historial misión a misión (§5.35.19): las frases son del backend y se pintan tal cual; aquí
 * se comprueba qué marca va con cada cotejo (casa: visto sin color; no casa: triángulo amarillo;
 * no se puede cotejar: cian con su anillo), que las cifras pasan por `lib/format.ts`, que los días
 * no se piden en el formulario y que ningún color es decorativo.
 */

const render = (data: MissionHistory | null, operator = "CDR", unavailable: ReturnType<typeof requestOutcome> | null = null) =>
  renderToStaticMarkup(
    createElement(MissionHistoryView, { data, unavailable, operator, onDeclare: () => Promise.resolve() }),
  );

const limits = { missions: 20, name_length: 80 };

const undeclared: MissionHistory = {
  subject: "crew-01",
  declared: false,
  scope: "ALCANCE-DEL-BACKEND",
  limits,
  text: "SIN-HISTORIAL",
  missions: [],
  checks: [],
};

const declared = (checks: MissionHistory["checks"], dose: number | null = 80.25): MissionHistory => ({
  subject: "crew-01",
  declared: true,
  scope: "ALCANCE-DEL-BACKEND",
  limits,
  days_basis: "BASE-DE-LOS-DIAS",
  text: "DECLARADAS-DOS",
  missions: [
    { name: "Expedición 1", start: "2021-04-01", end: "2021-10-01", days: 183, dose_msv: dose },
    { name: "Artemis II", start: "2024-03-01", end: "2024-03-11", days: 10, dose_msv: 40.25 },
  ],
  dose_sum_msv: 120.5,
  missions_without_dose: dose === null ? 1 : 0,
  declared_by: "CDR",
  recorded: "2026-10-22T10:00:00+00:00",
  ledger_index: 7,
  checks,
});

describe("<MissionHistoryView>", () => {
  it("plegado bajo el reloj de «lo anterior», con el recuento si hay historial", () => {
    expect(render(undeclared)).toMatch(taggedPictogram("summary", "clock-rewind", "Historial misión a misión</summary>"));
    expect(render(declared([]))).toMatch(taggedPictogram("summary", "clock-rewind", "Historial misión a misión (2)</summary>"));
  });

  it("sin declarar: la frase del backend con el anillo sin color, que no es un dato ausente", () => {
    const html = render(undeclared);
    expect(html).toMatch(markedHtml("ring-dotted", "SIN-HISTORIAL"));
    expect(html).toContain('<p class="secondary">ALCANCE-DEL-BACKEND</p>');
    expect(html).not.toContain("c-cyan");
    expect(html).not.toContain("<table");
  });

  it("la tabla: nombre, fechas, días calculados y dosis con su cifra; sin dosis, cian con su anillo", () => {
    const html = render(declared([], null));
    expect(html).toMatch(thSign("clock-rewind", "Misión</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("calendar", "Inicio</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("calendar", "Fin</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("calendar-day", "Días</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("trefoil", "Dosis (mSv)</span></th>", ' scope="col"'));
    expect(html).toContain("<td>Expedición 1</td><td>2021-04-01</td><td>2021-10-01</td>");
    expect(html).toContain('<td><span class="num">183</span></td>');
    expect(html).toContain('<td><span class="num">40,25</span></td>');
    expect(html).toMatch(markedHtml("ring-dotted", "sin dosis declarada", "cyan"));
    expect(html).toContain('<p class="secondary">Días: BASE-DE-LOS-DIAS.</p>');
    expect(html).toContain("<p>DECLARADAS-DOS</p>");
  });

  it("cada cotejo con su marca: casa, no casa o no hay con qué cotejar", () => {
    const html = render(
      declared([
        { key: "missions", matches: true, text: "CASA-MISIONES" },
        { key: "dose", matches: false, text: "NO-CASA-DOSIS" },
      ]),
    );
    expect(html).toMatch(markedHtml("check", "CASA-MISIONES"));
    expect(html).toMatch(markedHtml("shape-triangle", "NO-CASA-DOSIS", "yellow"));
    const unknown = render(declared([{ key: "dose", matches: null, text: "SIN-COTEJO" }]));
    expect(unknown).toMatch(markedHtml("ring-dotted", "SIN-COTEJO", "cyan"));
    expect(checkMark({ key: "dose", matches: true, text: "" }).color).toBeNull();
  });

  it("el solape es un aviso, no un cotejo: lo dice su clave, con el triángulo en amarillo", () => {
    const overlap = { key: "overlap", matches: false, text: "" } as const;
    expect(isHistoryNotice(overlap)).toBe(true);
    expect(isHistoryNotice({ key: "dose", matches: false, text: "" })).toBe(false);
    expect(isHistoryNotice({ key: "missions", matches: false, text: "" })).toBe(false);
    const shown = checkMark(overlap);
    expect([shown.pictogram, shown.color]).toEqual(["shape-triangle", "yellow"]);
  });

  it("las claves que da el backend son las que la interfaz separa: una nueva no cae entre los cotejos", () => {
    const backend = readFileSync(
      fileURLToPath(new URL("../../../backend/app/core/mission_history.py", import.meta.url)),
      "utf-8",
    );
    const keys = new Set([...backend.matchAll(/"key": "([a-z_]+)"/g)].map((match) => match[1]));
    expect([...keys].sort()).toEqual(["dose", "missions", "overlap"]);
  });

  it("con aviso, el rótulo cerrado lleva el triángulo en amarillo; sin él, el signo de siempre", () => {
    const withNotice = render(declared([{ key: "overlap", matches: false, text: "SE-SOLAPA" }]));
    expect(withNotice).toMatch(/<summary[^>]*><svg[^>]*c-yellow/);
    const without = render(declared([{ key: "dose", matches: false, text: "NO-CASA" }]));
    expect(without).not.toMatch(/<summary[^>]*><svg[^>]*c-yellow/);
  });

  it("el aviso va en su bloque, tal cual y antes de la tabla; los cotejos, debajo y sin él", () => {
    const html = render(
      declared([
        { key: "dose", matches: false, text: "NO-CASA-DOSIS" },
        { key: "overlap", matches: false, text: "SE-SOLAPA" },
      ]),
    );
    expect(html).toMatch(markedHtml("shape-triangle", "SE-SOLAPA", "yellow"));
    expect(html.match(/history-notice/g)).toHaveLength(1);
    expect(html.indexOf("history-notice")).toBeLessThan(html.indexOf("SE-SOLAPA"));
    expect(html.indexOf("SE-SOLAPA")).toBeLessThan(html.indexOf("<table"));
    expect(html.indexOf("</table>")).toBeLessThan(html.indexOf("NO-CASA-DOSIS"));
    expect(html.match(/SE-SOLAPA/g)).toHaveLength(1);
  });

  it("ningún color decorativo: solo el amarillo de lo que no casa y el cian de lo que falta", () => {
    const html = render(declared([{ key: "missions", matches: true, text: "CASA" }]));
    expect(html).not.toMatch(/c-(red|yellow|blue|gray|magenta|green|cyan)/);
  });

  it("el formulario arranca con la lista vigente y no pide los días", () => {
    const html = render(declared([]));
    expect(html).toContain('value="Expedición 1"');
    expect(html).toContain('value="2024-03-11"');
    expect(html).toContain('value="80.25"');
    expect(html).not.toMatch(/Días <input/);
    expect(html).toMatch(taggedPictogram("label", "clock-rewind", "Misión <input"));
    expect(html).toMatch(taggedPictogram("label", "calendar", "Inicio <input"));
    expect(html).toMatch(taggedPictogram("label", "trefoil", "Dosis (mSv, vacío si no se conoce) <input"));
    expect(html).toMatch(taggedPictogram("button", "eraser", "Quitar</button>", ' class="command" type="button"'));
    expect(html).toMatch(taggedPictogram("button", "plus", "Añadir misión</button>", ' class="command" type="button"'));
    expect(html).toMatch(taggedPictogram("button", "pen", "Declarar historial</button>", ' class="command" type="submit"'));
  });

  it("declarar pide quién está en la consola; sin filas, el mando dice que firma «ninguna»", () => {
    expect(render(declared([]), "")).toMatch(
      taggedPictogram("button", "pen", "Declarar historial</button>", ' class="command" type="submit" disabled=""'),
    );
    // Una lista vacía es una declaración: el único mando activo dice cuál, no «Declarar historial».
    const empty = render(undeclared);
    expect(empty).toMatch(
      taggedPictogram("button", "pen", "Declarar: ninguna misión previa</button>", ' class="command" type="submit"'),
    );
    expect(empty).not.toContain("Declarar historial</button>");
  });

  it("los topes del formulario son los del backend, no una copia", () => {
    const html = render({ ...declared([]), limits: { missions: 2, name_length: 12 } } as MissionHistory);
    expect(html).toContain('maxLength="12"');
    // Con tantas filas como el tope, añadir otra queda apagado.
    expect(html).toMatch(taggedPictogram("button", "plus", "Añadir misión</button>", ' class="command" type="button" disabled=""'));
    const source = readFileSync(fileURLToPath(new URL("./MissionHistory.tsx", import.meta.url)), "utf8");
    expect(source).not.toMatch(/maxLength=\{\d+\}|length >= \d+/);
  });

  it("una dosis que no es una cifra no se manda como «no se conoce»", () => {
    expect(parseDose("")).toBeNull();
    expect(parseDose(" 12,5 ")).toBe(12.5);
    expect(parseDose("1,2,3")).toBeUndefined();
    expect(parseDose("12 mSv")).toBeUndefined();
    expect(parseDose("1e3")).toBeUndefined();
  });

  it("las fechas pasan por `lib/format.ts`: una con otra forma falla en vez de pintarse", () => {
    const bad = declared([]);
    if (!bad.declared) throw new Error("fixture");
    bad.missions[0] = { ...bad.missions[0]!, start: "01/04/2021" };
    expect(() => render(bad)).toThrow(RangeError);
  });

  it("cargando, la flecha sin color; sin respuesta, la marca de lo que fue", () => {
    expect(render(null)).toMatch(markedHtml("refresh", "Cargando…"));
    const refused = render(null, "CDR", requestOutcome(new ApiError(409, "DETALLE")));
    expect(refused).toMatch(markedHtml("shape-triangle", "Sin datos: DETALLE", "yellow"));
    const down = render(null, "CDR", requestOutcome(new TypeError("caida")));
    expect(down).toMatch(/c-red/);
  });

  it("el rechazo del backend se guarda con su marca, no como texto", () => {
    const source = readFileSync(fileURLToPath(new URL("./MissionHistory.tsx", import.meta.url)), "utf8");
    expect(source).toContain("setError(requestOutcome(cause))");
    expect(source).toContain("<MarkOf mark={error.mark}>{error.text}</MarkOf>");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(code).not.toMatch(/<svg|<path|aria-hidden/);
    expect(code).not.toMatch(/[○◇△■□●◐▷◌⊘✕✓≠≈]/);
  });
});
