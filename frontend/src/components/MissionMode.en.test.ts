/**
 * El nivel de misión y la red en inglés (`lib/i18n.ts`). El nombre del nivel, su aviso y los
 * porqués son del backend y llegan tal cual (marcadores en mayúsculas); aquí solo se mira que los
 * rótulos de la interfaz salen en inglés.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { MissionModeState, SafeModeState } from "../lib/api";
import { LookContext } from "./BoardOnly";
import { MissionMode } from "./MissionMode";
import { NetworkStatus } from "./SafeMode";

const state = {
  level: "nominal",
  level_display: "LEVEL-FROM-BACKEND",
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
  label: "LABEL",
  basis: "BASIS",
  rule: "RULE",
  not_power: "NOT-POWER",
  unchanged: [],
  citable_systems: [{ key: "power", display: "SYSTEM-POWER" }],
  citable_basis: "CITABLE",
  levels: [
    { key: "nominal", display: "LEVEL-FROM-BACKEND", description: "D1", rank: 0, expected: 128 },
    { key: "reduced", display: "LEVEL-MID", description: "D2", rank: 1, expected: 60 },
  ],
  current: {
    key: "nominal",
    display: "LEVEL-FROM-BACKEND",
    description: "DESCRIPTION",
    rank: 0,
    expected: [{ key: "heart-rate", name: "NAME", why: "WHY" }],
    suspended: [],
  },
  notice: null,
} as unknown as MissionModeState;

const render = (controls: boolean, look: "classic" | "reference" = "classic") =>
  renderToStaticMarkup(
    createElement(
      LookContext.Provider,
      { value: look },
      createElement(MissionMode, { state, controls, apply: () => Promise.resolve() }),
    ),
  );

describe("el nivel de misión en inglés", () => {
  it("el rótulo y las dos listas; el nombre del nivel sigue siendo el del backend", () => {
    const html = render(false);
    expect(html).toContain("Mission level");
    expect(html).toContain("LEVEL-FROM-BACKEND");
    expect(html).toContain('Expected <span class="num">1</span>');
    expect(html).toContain('Not expected <span class="num">0</span>');
    expect(html).not.toMatch(/Nivel de misión|Se esperan|No se esperan/);
  });

  it("el formulario de a bordo: quién, nivel, motivo, cita y la firma", () => {
    const html = render(true);
    for (const label of ["Change the level", "Who", "Level", "Reason", "Cites", "Sign the level"]) {
      expect(html).toContain(label);
    }
    expect(html).toContain("LEVEL-MID · 60 measures");
    expect(html).not.toMatch(/Cambiar el nivel|Quién|Motivo|Firmar el nivel|medidas/);
  });

  it("en el tablero, el anillo dice qué cuenta", () => {
    const html = render(false, "reference");
    expect(html).toContain("measures expected");
    expect(html).toMatch(/<p class="secondary ref-ring-caption">expected<\/p>/);
    expect(html).not.toMatch(/medidas esperadas|se esperan/);
  });
});

describe("la red en inglés", () => {
  const open: SafeModeState = {
    active: false,
    reason: null,
    declared_by: null,
    since: null,
    version: 0,
    store_epoch: 1,
    halt: { active: false, file: "estado/.HALT", since: null, notice: null },
  };

  it("abierta, y con el modo seguro puesto", () => {
    const up = renderToStaticMarkup(createElement(NetworkStatus, { state: open }));
    expect(up).toMatch(/<\/svg>open<\/span>/);
    expect(up).not.toContain("abierta");
    const safe = renderToStaticMarkup(createElement(NetworkStatus, { state: { ...open, active: true } }));
    expect(safe).toContain("Safe mode · no internet access");
    expect(safe).not.toMatch(/Modo seguro|sin salida/);
  });
});
