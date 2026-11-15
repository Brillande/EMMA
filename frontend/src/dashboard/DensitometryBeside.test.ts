import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { DensitometryCheck, DensitometryRegion, InferredState } from "../lib/api";
import { DensitometryBeside } from "./DensitometryBeside";
import { InferredPanel } from "./InferredPanel";

/*
 * La densitometría (DXA) MEDIDA junto a la banda INFERIDA (`analysis/densitometry.py`). Cada
 * frase es del backend; aquí se comprueba que se pinta tal cual, con las cifras por `format.ts`,
 * sin color, y que la fuente del componente no calcula ni decide nada.
 */

const region = (over: Partial<DensitometryRegion> = {}): DensitometryRegion => ({
  key: "bmd-dxa-hip",
  region: "Cadera",
  display_es: "Densidad ósea de la cadera por densitometría (DXA)",
  unit: "g/cm2",
  decimals: 3,
  state: "compared",
  preflight: {
    label: "ROTULO-PREVIO",
    value: 1,
    effective: "2026-10-02T00:00:00+00:00",
    mission_day: -30,
    days_after_return: null,
    when_display: "CUANDO-PREVIO",
  },
  postflight: {
    label: "ROTULO-POSVUELO",
    value: 0.988,
    effective: "2026-12-06T00:00:00+00:00",
    mission_day: 35,
    days_after_return: 5,
    when_display: "CUANDO-POSVUELO",
  },
  later_postflight: 0,
  in_flight: 0,
  measured_loss_pct: 1.2,
  position: "within",
  statement: "FRASE-POSICION",
  ...over,
});

const check = (regions: DensitometryRegion[] = [region()]): DensitometryCheck => ({
  observation_type: "measured",
  relation: "FRASE-RELACION",
  band_day: 30,
  band: { loss_pct_low: 0.99, loss_pct_high: 1.48 },
  postflight_window_days: 30,
  preflight_window_days: 180,
  loss_label: "ROTULO-PERDIDA",
  band_label: "ROTULO-BANDA",
  precision_note: "FRASE-PRECISION",
  source: { title: "Bone Loss", source: "NASA OCHMO", url: "https://www.nasa.gov/x.pdf" },
  regions,
});

const render = (value: DensitometryCheck) =>
  renderToStaticMarkup(createElement(DensitometryBeside, { check: value }));

describe("DensitometryBeside", () => {
  it("pinta las frases del backend tal cual y las cifras con su formato", () => {
    const html = render(check());
    for (const text of [
      "FRASE-RELACION",
      "FRASE-POSICION",
      "FRASE-PRECISION",
      "Cadera",
      "ROTULO-PREVIO",
      "ROTULO-POSVUELO",
      "CUANDO-PREVIO",
      "CUANDO-POSVUELO",
      "ROTULO-PERDIDA",
      "ROTULO-BANDA",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).toContain("1,000</span> g/cm²");
    expect(html).toContain("0,988</span> g/cm²");
    expect(html).toContain("1,20</span> %");
    expect(html).toContain("0,99</span>–");
    expect(html).toContain("1,48</span> %");
    expect(html).toContain("https://www.nasa.gov/x.pdf");
  });

  it("una región que no se compara enseña su porqué y ninguna pérdida", () => {
    const html = render(
      check([
        region({
          state: "no_postflight",
          postflight: null,
          measured_loss_pct: null,
          position: null,
          statement: "FRASE-SIN-POSVUELO",
        }),
      ]),
    );
    expect(html).toContain("FRASE-SIN-POSVUELO");
    expect(html).not.toContain("ROTULO-PERDIDA");
    expect(html).not.toContain("1,48");
  });

  it("no lleva color ni calcula: la posición la decide el backend", () => {
    const source = readFileSync(
      fileURLToPath(new URL("./DensitometryBeside.tsx", import.meta.url)),
      "utf8",
    );
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,6}\b|palette|color=/);
    expect(source).not.toMatch(/\.position\s*===|loss_pct_(low|high)\s*[-+*/<>]/);
    expect(source).not.toMatch(/toFixed|Math\./);
  });

  it("el panel de estados inferidos la enseña solo si llega", () => {
    const band: InferredState = {
      key: "bone-mineral-density-loss",
      display: "Pérdida de densidad mineral ósea en huesos de carga",
      unit: "%",
      observation_type: "inferred",
      model_version: "bmd@1",
      now: { mission_day: 30, loss_pct_low: 0.99, loss_pct_high: 1.48 },
      trajectory: [],
      basis: "FRASE-BASE",
      source: { title: "t", source: "s", url: "https://www.nasa.gov/" },
      evidence_class: "established",
      exercise_note: "FRASE-EJERCICIO",
    };
    const without = renderToStaticMarkup(createElement(InferredPanel, { inferred: [band] }));
    expect(without).not.toContain("FRASE-RELACION");
    const withIt = renderToStaticMarkup(
      createElement(InferredPanel, { inferred: [{ ...band, densitometry: check() }] }),
    );
    expect(withIt).toContain("FRASE-RELACION");
    expect(withIt).toContain("FRASE-POSICION");
  });
});
