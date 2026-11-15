import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { HaltNoticeText, MissionMeasure, MissionModeState } from "../lib/api";
import { formatUtc } from "../lib/format";
import { LookContext } from "./BoardOnly";
import { MeasureList, MissionMode, isNewer } from "./MissionMode";

/*
 * El nivel de misión: el texto lo redacta el backend (`core/mission_modes.py`) y la consola lo
 * pinta tal cual. Aquí cada texto del backend lleva un marcador en mayúsculas para ver que llega
 * sin tocar, y la fuente del componente se mira para ver que no escribe nada del nivel.
 */
const measure = (key: string, why: string): MissionMeasure => ({
  key,
  name: `NOMBRE-${key}`,
  mode: "continuous-passive",
  mode_display: "MODO",
  consumables: "none",
  consumables_display: "CONSUMIBLES",
  crew_time_minutes: null,
  crew_time_basis: "sin fuente",
  inputs: [],
  why,
});

const notice: HaltNoticeText = {
  title: "TITULO-DEL-NIVEL",
  headline: "TITULAR-DEL-NIVEL",
  summary: "LO-QUE-SIGUE-DEL-BACKEND",
  since: "2026-11-02T10:00:00+00:00",
  since_label: "ETIQUETA-DE-FECHA",
  details_label: "ETIQUETA-DEL-DETALLE",
  details: ["DETALLE-1", "DETALLE-2"],
};

const base: MissionModeState = {
  level: "nominal",
  level_display: "NIVEL-ALTO",
  reason: null,
  declared_by: null,
  since: null,
  ledger_index: null,
  cited_system: null,
  cited_state: null,
  cited_system_display: null,
  cited_state_display: null,
  version: 0,
  store_epoch: 1,
  label: "ROTULO-DE-DISENO",
  basis: "BASE-DEL-VOCABULARIO",
  rule: "REGLA-DE-QUIEN-SUBE",
  not_power: "SIN-POTENCIA",
  unchanged: ["SIGUE-1"],
  citable_systems: [
    { key: "power", display: "SISTEMA-ENERGIA" },
    { key: "communications", display: "SISTEMA-COMUNICACIONES" },
  ],
  citable_basis: "BASE-DE-LA-CITA",
  levels: [
    { key: "nominal", display: "NIVEL-ALTO", description: "D1", rank: 0, expected: 128 },
    { key: "reduced", display: "NIVEL-MEDIO", description: "D2", rank: 1, expected: 60 },
    { key: "minimal", display: "NIVEL-BAJO", description: "D3", rank: 2, expected: 15 },
  ],
  current: {
    key: "nominal",
    display: "NIVEL-ALTO",
    description: "DESCRIPCION-DEL-NIVEL",
    rank: 0,
    expected: [measure("heart-rate", "PORQUE-SE-ESPERA")],
    suspended: [],
  },
  notice: null,
};

const lowered: MissionModeState = {
  ...base,
  level: "minimal",
  level_display: "NIVEL-BAJO",
  reason: "MOTIVO-FIRMADO",
  declared_by: "QUIEN-FIRMO",
  since: notice.since,
  ledger_index: 3,
  cited_system: "power",
  cited_state: "degraded",
  cited_system_display: "SISTEMA-ENERGIA",
  cited_state_display: "ESTADO-CITADO",
  version: 1,
  current: {
    ...base.current,
    key: "minimal",
    suspended: [measure("cortisol-salivary", "PORQUE-SE-SUSPENDE")],
  },
  notice,
};

const render = (state: MissionModeState, controls = false) =>
  renderToStaticMarkup(createElement(MissionMode, { state, controls, apply: () => Promise.resolve() }));

describe("el nivel de misión, tal cual lo da el backend", () => {
  it("en el nivel de más medidas: el nombre del backend, sin color ni aviso", () => {
    const html = render(base);
    expect(html).toContain("NIVEL-ALTO");
    expect(html).not.toContain("c-yellow");
    expect(html).not.toContain('role="status"');
    expect(html).not.toContain("TITULO-DEL-NIVEL");
  });

  it("fuera de él: el aviso en amarillo con el triángulo, nunca el color solo (F.5-1)", () => {
    const html = render(lowered);
    expect(html).toMatch(/<span role="status">[^]*data-pictogram="shape-triangle"[^]*TITULO-DEL-NIVEL · TITULAR-DEL-NIVEL/);
    expect(html).toContain("c-yellow");
    expect(html).toContain("LO-QUE-SIGUE-DEL-BACKEND");
    expect(html).toContain(formatUtc(new Date(notice.since ?? "")));
  });

  it("quién, el motivo y lo citado, y cada detalle del aviso, sin redactar nada", () => {
    const html = render(lowered);
    expect(html).toContain("QUIEN-FIRMO · MOTIVO-FIRMADO · SISTEMA-ENERGIA · ESTADO-CITADO");
    for (const text of ["ETIQUETA-DEL-DETALLE", "DETALLE-1", "DETALLE-2", "ROTULO-DE-DISENO", "BASE-DEL-VOCABULARIO"]) {
      expect(html).toContain(text);
    }
  });

  it("lo que se espera y lo que no, cada medida con el porqué del backend", () => {
    const html = render(lowered);
    expect(html).toContain("NOMBRE-heart-rate");
    expect(html).toContain("PORQUE-SE-ESPERA");
    expect(html).toContain("NOMBRE-cortisol-salivary");
    expect(html).toContain("PORQUE-SE-SUSPENDE");
  });

  it("la lista dice cuántas son con `formatNumber`, y vacía no pinta la lista", () => {
    const empty = renderToStaticMarkup(createElement(MeasureList, { title: "T", measures: [] }));
    expect(empty).toContain('<span class="num">0</span>');
    expect(empty).not.toContain("<ul>");
  });

  it("el mando solo a bordo: Tierra ve el nivel y no lo cambia", () => {
    expect(render(lowered, false)).not.toContain("<select");
    const html = render(lowered, true);
    expect(html).toContain("<select");
    for (const text of ["NIVEL-ALTO", "NIVEL-MEDIO", "NIVEL-BAJO", "SISTEMA-ENERGIA", "SISTEMA-COMUNICACIONES", "REGLA-DE-QUIEN-SUBE"]) {
      expect(html).toContain(text);
    }
  });
});

describe("el tablero (la concha de la maqueta)", () => {
  it("el anillo cuenta las medidas que se esperan sobre las que reparte el nivel, con su texto", () => {
    const html = render(lowered);
    expect(html).toContain('role="img" aria-label="1 de 2 medidas esperadas"');
    expect(html).toMatch(/<span class="ref-pill board-pill"><span class="mark c-yellow"[^>]*>[^]*NIVEL-BAJO<\/span><\/span>/);
  });

  it("en el nivel de más medidas la píldora no lleva color, y la clásica no monta nada", () => {
    expect(render(base)).toContain('aria-label="1 de 1 medidas esperadas"');
    const classic = renderToStaticMarkup(
      createElement(
        LookContext.Provider,
        { value: "classic" },
        createElement(MissionMode, { state: lowered, controls: false, apply: () => Promise.resolve() }),
      ),
    );
    expect(classic).not.toContain("ref-ring");
    expect(classic).not.toContain("board-pill");
  });
});

describe("qué respuesta gana (§5.38.13, como el modo seguro)", () => {
  it("la de un almacén posterior, o la del mismo con versión igual o mayor; nunca una más vieja", () => {
    expect(isNewer(base, null)).toBe(true);
    expect(isNewer(lowered, base)).toBe(true);
    expect(isNewer(base, lowered)).toBe(false);
    expect(isNewer(lowered, lowered)).toBe(true);
    expect(isNewer({ ...base, store_epoch: 2 }, lowered)).toBe(true);
    expect(isNewer({ ...lowered, store_epoch: 0, version: 9 }, lowered)).toBe(false);
  });
});

describe("la fuente del componente", () => {
  const source = readFileSync(fileURLToPath(new URL("./MissionMode.tsx", import.meta.url)), "utf8");
  const code = source.replace(/\/\*\*[^]*?\*\/|\/\/.*$/gm, "");

  it("no redacta el nivel ni su significado: ninguna palabra del aviso escrita aquí", () => {
    expect(code).not.toMatch(/reducido|mínimo|suspendid|análisis|alertas|vatio/i);
  });

  it("el color sale de la paleta por `Mark`, nunca escrito a mano", () => {
    expect(code).not.toMatch(/#[0-9a-fA-F]{3,6}\b|c-yellow|style=\{/);
  });

  it("los rótulos llevan el signo de su concepto, por `FieldLabel`, y el rechazo su marca", () => {
    expect(code).toMatch(/<FieldLabel concept="person">\s*\{tr\("Quién", "Who"\)\}\{" "\}/);
    expect(code).toMatch(/<FieldLabel concept="reason">\s*\{tr\("Motivo", "Reason"\)\} <input/);
    expect(code).toContain("setError(requestOutcome(failure))");
    expect(code).not.toMatch(/<label>|<details|<summary/);
  });
});
