/**
 * Los dos mandos del render pequeño en inglés (`lib/i18n.ts`). Sin navegador no hay WebGL ni
 * efectos: se pinta el marco con `renderToStaticMarkup`, y el nombre accesible es el que le pasan.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { VolumeSegmentation } from "../lib/api";
import { SegmentationPreview } from "./SegmentationPreview";

const segmentation = {
  ledger_index: 20,
  preset: "higado",
  estructuras: [{ key: "higado", nombre: "liver", etiqueta: 1, malla: "higado.ply", volumen_ml: 1500 }],
} as unknown as VolumeSegmentation;

describe("la vista previa de la segmentación en inglés", () => {
  it("los mandos de abrir el visor y de parar el giro", () => {
    const html = renderToStaticMarkup(
      createElement(SegmentationPreview, {
        segmentation,
        label: "LABEL FROM THE CARD",
        open: { label: "OPEN LABEL", onClick: () => undefined },
      }),
    );
    expect(html).toContain('aria-label="LABEL FROM THE CARD"');
    expect(html).toContain('aria-label="OPEN LABEL"');
    expect(html).toContain("Open viewer");
    expect(html).toContain("Stop rotation");
    expect(html).not.toMatch(/Abrir visor|Parar giro|Girar/);
  });
});
