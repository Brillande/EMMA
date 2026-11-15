import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import type { DataQuality, IndicatorQuality } from "../lib/api";
import { UNKNOWN_MARK } from "../lib/marks";
import { QualityPanel } from "./QualityPanel";
import { readingSourcePictogram } from "./readingSources";

/*
 * La fuente que firmo una lectura lleva su pictograma junto al nombre que pone el backend
 * (`analysis/data_quality.py`). Se comprueba que cada fuente y cada prefijo que el backend
 * conoce tienen dibujo, que ninguno se repite, y que el panel de calidad los pinta junto a la
 * palabra, con el indicador con el de su familia, sin color.
 */

const PYTHON = readFileSync(
  fileURLToPath(new URL("../../../backend/app/analysis/data_quality.py", import.meta.url)),
  "utf-8",
);

/** Las claves de un diccionario literal de Python, por su nombre. */
function pythonKeys(name: string): string[] {
  const block = new RegExp(`${name}: dict\\[str, str\\] = \\{([\\s\\S]*?)\\n\\}`).exec(PYTHON)?.[1];
  expect(block, `${name} en data_quality.py`).toBeDefined();
  return [...(block ?? "").matchAll(/^\s*"([^"]+)":/gm)].map((match) => match[1] ?? "");
}

describe("pictograma de la fuente de una lectura", () => {
  it("cada fuente que el backend nombra tiene su dibujo, y ninguno se repite", () => {
    const sources = pythonKeys("_SOURCE_LABELS");
    expect(sources.length).toBeGreaterThan(5);
    const drawn = new Set<string>();
    for (const source of sources) {
      const pictogram = readingSourcePictogram(source);
      expect(pictogram, source).not.toBe(UNKNOWN_MARK.pictogram);
      drawn.add(String(pictogram));
    }
    expect(drawn.size).toBe(sources.length);
  });

  it("cada prefijo del backend tiene su dibujo, y solo cuenta con algo detras, como alli", () => {
    const prefixes = pythonKeys("_SOURCE_PREFIXES");
    expect(prefixes).toContain("simulator:");
    for (const prefix of prefixes) {
      expect(readingSourcePictogram(`${prefix}algo`), prefix).not.toBe(UNKNOWN_MARK.pictogram);
      expect(readingSourcePictogram(prefix), prefix).toBe(UNKNOWN_MARK.pictogram);
    }
    // El simulador es el mismo origen que el entorno «simulado»: el mismo dibujo.
    expect(readingSourcePictogram("simulator:nominal")).toBe("wave-zigzag");
  });

  it("una fuente que la interfaz no conoce va con el dibujo de desconocido, no con el de otra", () => {
    expect(readingSourcePictogram("otra-cosa")).toBe(UNKNOWN_MARK.pictogram);
    expect(readingSourcePictogram("")).toBe(UNKNOWN_MARK.pictogram);
  });
});

const row = (over: Partial<IndicatorQuality> = {}): IndicatorQuality => ({
  key: "heart-rate",
  display: "Heart rate",
  display_es: "NOMBRE-DEL-INDICADOR",
  domain: "cardiovascular",
  unit: "/min",
  decimals: 0,
  latest: {
    value: 62,
    effective: "2026-12-10T23:00:00+00:00",
    source: "wearable-ble",
    source_label: "FUENTE-DEL-BACKEND",
    observation_type: "measured",
    evidence_context: "simulated",
    confidence: 0.4,
    state: "low",
    label: "baja confianza",
  },
  recent: {
    readings: 10,
    low_confidence: 2,
    undeclared: 0,
    sources: [{ source: "apple-health", label: "OTRA-FUENTE", readings: 4, low_confidence: 2 }],
  },
  baseline: { excluded_readings: 2, capped_findings: 0, discounted: true, text: "FRASE-BASE" },
  ...over,
});

const quality = (over: Partial<DataQuality> = {}): DataQuality => ({
  low_confidence_threshold: 0.5,
  window_days: 7,
  recent_label: "últimos 2 días",
  labels: { low: "baja confianza", declared: "confianza declarada", undeclared: "no declarada" },
  summary: "RESUMEN",
  undeclared_note: null,
  recent: { readings: 10, low_confidence: 2, undeclared: 0 },
  indicators: [row()],
  device_bindings: {
    kind: "none",
    label: "declarado por una persona",
    readings: 0,
    with_device: 0,
    mismatched: 0,
    groups: [],
    indicators: [],
    since: null,
    text: null,
    analysis_note: null,
    device_note: null,
  },
  ...over,
});

describe("calidad del dato: la fila", () => {
  it("el indicador con el dibujo de su familia y la fuente con el de su canal, junto a las palabras del backend", () => {
    const html = renderToStaticMarkup(createElement(QualityPanel, { quality: quality() }));
    expect(html).toMatch(
      /<td><span class="mark"><svg [^>]*data-pictogram="heart-pulse"[^>]*>.*?<\/svg>NOMBRE-DEL-INDICADOR<\/span><\/td>/,
    );
    expect(html).toMatch(
      /<td><span class="mark"><svg [^>]*data-pictogram="wristwatch"[^>]*>.*?<\/svg>FUENTE-DEL-BACKEND<\/span><\/td>/,
    );
    // La fuente de las lecturas dudosas, en secundario, tambien con su dibujo.
    expect(html).toMatch(/<svg [^>]*data-pictogram="phone-heart"[^>]*>.*?<\/svg>OTRA-FUENTE<\/span>/);
    // El entorno del ultimo dato con su onda, dentro del rotulo de tipo.
    expect(html).toMatch(/<svg [^>]*data-pictogram="wave-zigzag"[^>]*>.*?<\/svg>simulado<\/span>/);
    // Las palabras siguen siendo las del backend, y nada mas se añade en esas celdas.
    expect(textNodes(html)).toContain("NOMBRE-DEL-INDICADOR");
    expect(textNodes(html)).toContain("FUENTE-DEL-BACKEND");
  });
});
