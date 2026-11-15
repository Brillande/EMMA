import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, textNodes } from "../advisor/visibleText";
import type { ContrastPhaseView, VolumeStudy } from "../lib/api";
import { MISSING_MARK, UNKNOWN_MARK } from "../lib/marks";
import { ContrastPhasePanel } from "./ContrastPhasePanel";
import { LesionComparison } from "./LesionComparison";
import { PolarisViewer } from "./PolarisViewer";
import { VolumesPanel } from "./VolumesPanel";
import {
  ATTENTION_MARK,
  CLEANED_MARK,
  KNOWN_PHASES,
  PHASE_TONE_MARK,
  UNAVAILABLE_MARK,
  modalityMark,
  phaseMark,
  spineNoticeMark,
} from "./marks";

/**
 * Las marcas de los volumenes (§5.32.9): cada fase conocida del vocabulario cerrado tiene su
 * dibujo (la paridad con `PHASES` del backend la vigila
 * `backend/tests/test_pain_volume_pictograms.py`, que lee la tabla); la modalidad, el suyo; y
 * los tres significados de F.5-1 que ya tenian color (atencion, dato ausente, no disponible)
 * llevan ahora su forma.
 */

describe("la fase de contraste (phaseMark)", () => {
  it("las cinco fases del vocabulario, cada una con un dibujo propio y distinto, sin color", () => {
    expect(KNOWN_PHASES).toHaveLength(5);
    expect(KNOWN_PHASES).toContain("non-contrast");
    const drawn = KNOWN_PHASES.map((code) => phaseMark(code).pictogram);
    expect(new Set(drawn).size).toBe(drawn.length);
    for (const code of KNOWN_PHASES) {
      expect(phaseMark(code).pictogram, code).not.toBe(UNKNOWN_MARK.pictogram);
      expect(phaseMark(code).color).toBeNull();
    }
    expect(phaseMark("unknown").pictogram).toBe("question");
  });

  it("un codigo que la interfaz no conoce lleva la marca de desconocido", () => {
    expect(phaseMark("inventada")).toEqual(UNKNOWN_MARK);
  });

  it("lo que el backend dice de dos fases: igual sin color, atencion en amarillo, no aplica en gris", () => {
    expect(PHASE_TONE_MARK.igual).toEqual({ pictogram: "equals", color: null, className: undefined });
    expect(PHASE_TONE_MARK.atencion).toBe(ATTENTION_MARK);
    expect(PHASE_TONE_MARK["no-aplica"]).toBe(UNAVAILABLE_MARK);
  });
});

describe("la modalidad y los significados de F.5-1", () => {
  it("gantry para CT, iman para MR, desconocido para lo demas, siempre sin color", () => {
    expect(modalityMark("CT")).toEqual({ pictogram: "gantry", color: null, className: undefined });
    expect(modalityMark("MR")).toEqual({ pictogram: "magnet", color: null, className: undefined });
    expect(modalityMark("PET")).toEqual(UNKNOWN_MARK);
  });

  it("atencion: triangulo amarillo; dato ausente: anillo punteado cian; no disponible: circulo tachado gris", () => {
    expect(ATTENTION_MARK).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
    expect(MISSING_MARK).toEqual({ pictogram: "ring-dotted", color: "cyan", className: "c-cyan" });
    expect(UNAVAILABLE_MARK).toEqual({ pictogram: "slash-circle", color: "gray", className: "c-gray" });
    expect(CLEANED_MARK).toEqual({ pictogram: "eraser", color: null, className: undefined });
  });

  it("el control de la cadena vertebral: un nivel desconocido se pinta como atencion, no como dato ausente", () => {
    expect(spineNoticeMark("atencion")).toBe(ATTENTION_MARK);
    expect(spineNoticeMark("dato_ausente")).toBe(MISSING_MARK);
    expect(spineNoticeMark("otro")).toBe(ATTENTION_MARK);
  });
});

describe("<ContrastPhasePanel>: lo que consta, pintado", () => {
  const view = (changes: Partial<ContrastPhaseView>): ContrastPhaseView => ({
    applicable: true,
    not_applicable_reason: null,
    current: null,
    undeclared_display: "SIN-DECLARAR",
    label: "ROTULO",
    history: [],
    ...changes,
  });
  const study = (contrast_phase: ContrastPhaseView): VolumeStudy =>
    ({ ledger_index: 3, modality: "CT", contrast_phase }) as unknown as VolumeStudy;
  const render = (contrast_phase: ContrastPhaseView) =>
    renderToStaticMarkup(
      createElement(ContrastPhasePanel, {
        study: study(contrast_phase),
        operator: "CMO",
        onOperator: () => undefined,
        onDeclared: () => undefined,
      }),
    );

  it("sin declarar: anillo punteado en cian junto a la palabra del backend", () => {
    const html = render(view({}));
    expect(html).toContain('<span class="mark c-cyan"><svg class="pictogram"');
    expect(html).toMatch(/data-pictogram="ring-dotted"[^]*?<\/svg>SIN-DECLARAR<\/span>/);
    expect(textNodes(html)).toContain("SIN-DECLARAR");
  });

  it("declarada: el dibujo de esa fase junto a su nombre, sin color, y el rotulo del backend", () => {
    const declared = {
      code: "portal-venous",
      display: "PORTAL-VENOSA",
      declared_by: "CMO",
      at: "2026-12-01T08:00:00+00:00",
      note: null,
      ledger_index: 9,
      recorded: "2026-12-01T08:05:30+00:00",
    };
    const html = render(view({ current: declared, history: [declared] }));
    expect(html).toMatch(/<span class="mark"><svg class="pictogram"[^]*?data-pictogram="branches"[^]*?<\/svg>PORTAL-VENOSA<\/span>/);
    expect(html).not.toContain("c-cyan");
    expect(textNodes(html)).toContain("(ROTULO)");
  });

  it("no aplica: circulo tachado en gris junto al motivo del backend", () => {
    const html = render(view({ applicable: false, not_applicable_reason: "MOTIVO" }));
    expect(html).toContain('<span class="mark c-gray"><svg class="pictogram"');
    expect(html).toMatch(/data-pictogram="slash-circle"[^]*?<\/svg>MOTIVO<\/span>/);
  });
});

describe("el signo de cada cosa de los volumenes (segunda pasada, §5.33.9)", () => {
  it("el panel: el gantry en el titulo, cada rotulo y el mando con su concepto, y la lista vacia con el anillo punteado sin color", () => {
    const html = renderToStaticMarkup(createElement(VolumesPanel, { subject: "crew-01" }));
    expect(html).toMatch(taggedPictogram("h2", "gantry", "Volúmenes 3D (TAC/RM)"));
    expect(html).toMatch(taggedPictogram("label", "arrow-up-tray", "Volumen NIfTI"));
    expect(html).toMatch(taggedPictogram("label", "tag", "Modalidad"));
    expect(html).toMatch(taggedPictogram("label", "person", "Registrado por", ' class="operator"'));
    expect(html).toMatch(taggedPictogram("button", "arrow-up-tray", "Registrar volumen", ' class="command" disabled=""'));
    expect(html).toMatch(markedHtml("ring-dotted", "Sin volúmenes registrados."));
    expect(html).not.toContain("c-cyan");
  });

  it("comparar con el estudio anterior lleva las dos barras de comparar", () => {
    const html = renderToStaticMarkup(createElement(LesionComparison, { before: 1, after: 2 }));
    expect(html).toMatch(taggedPictogram("button", "bars-two", "Comparar con el estudio anterior", ' class="command"'));
  });

  it("visor y render de Polaris: mandos con su dibujo y el pulsado por aria-pressed", () => {
    const segmentation = { ledger_index: 7 } as unknown as Parameters<typeof PolarisViewer>[0]["segmentation"];
    const html = renderToStaticMarkup(createElement(PolarisViewer, { segmentation }));
    expect(html).toMatch(
      taggedPictogram("button", "frame-crosshair", "Visor de Polaris", ' class="command" type="button" aria-pressed="true"'),
    );
    expect(html).toMatch(
      taggedPictogram("button", "sphere-shaded", "Render de Polaris", ' class="command" type="button" aria-pressed="false"'),
    );
  });
});
