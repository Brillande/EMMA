import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/*
 * Misión, calidad y vigilancia (§5.33.2): todo título, plegable, mando, cabecera y rótulo de estos
 * paneles va por las piezas del núcleo, que ponen el signo del concepto delante de la palabra. Se
 * lee la fuente: un `<h2>`, un `<details>`, un `button.command`, un `<th>` o un `<dt>` escritos a
 * mano serían un título o un mando sin su dibujo.
 */

const read = (file: string) =>
  readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf-8").replace(/\r\n/g, "\n");

/** Los dos paneles de vigilancia y base, en su fichero desde el tablero por secciones (2026-11-07). */
const crewPanels = () => {
  const source = read("./MonitoringBasis.tsx");
  return source.slice(source.indexOf("function MonitoringPanel("));
};

const FILES: Record<string, () => string> = {
  "MonitoringBasis.tsx (vigilancia y base)": crewPanels,
  "MissionTimeline.tsx": () => read("./MissionTimeline.tsx"),
  "MissionProfileView.tsx": () => read("./MissionProfileView.tsx"),
  "Predictions.tsx": () => read("./Predictions.tsx"),
  "InferredPanel.tsx": () => read("./InferredPanel.tsx"),
  "QualityPanel.tsx": () => read("./QualityPanel.tsx"),
  "SensorBindingsPanel.tsx": () => read("./SensorBindingsPanel.tsx"),
  "BaselineProfilePanel.tsx": () => read("./BaselineProfilePanel.tsx"),
};

describe("mobiliario de misión, calidad y vigilancia", () => {
  it("ningún título, plegable, mando ni rótulo escrito a mano", () => {
    for (const [name, source] of Object.entries(FILES)) {
      const code = source();
      expect(code, name).not.toMatch(/<h[234][ >]/);
      expect(code, name).not.toMatch(/<details[ >]|<summary[ >]/);
      expect(code, name).not.toContain('className="command"');
      expect(code, name).not.toMatch(/<dt[ >]|<label[ >]/);
    }
  });

  it("en la calidad del dato, la única cabecera sin dibujo es la de baja confianza", () => {
    const code = read("./QualityPanel.tsx");
    // Esa columna es la confianza otra vez: su dibujo ya va en «Confianza», y sin pictograma
    // delante `::first-letter` sigue poniendo la mayúscula a la etiqueta del backend.
    expect(code.match(/<th[ >]/g)).toEqual(["<th "]);
    expect(code).toMatch(/<th scope="col">\s*\{quality\.labels\.low\}/);
    for (const concept of ["indicator", "time", "confidence", "source", "baseline"]) {
      expect(code).toContain(`<Th concept="${concept}">`);
    }
  });

  it("los títulos llevan el concepto de su panel", () => {
    expect(read("./DomainsPanel.tsx")).toContain('<PanelTitle concept="domains">Dominios</PanelTitle>');
    expect(crewPanels()).toContain('<PanelTitle concept="monitoring">');
    expect(crewPanels()).toContain('<PanelTitle concept="basis">En qué se apoya</PanelTitle>');
    expect(read("./QualityPanel.tsx")).toContain('<PanelTitle concept="dataQuality">');
    expect(read("./InferredPanel.tsx")).toContain('<PanelTitle concept="inferred">');
    expect(read("./Predictions.tsx")).toContain('<PanelTitle concept="predictions">');
    expect(read("./SensorBindingsPanel.tsx")).toContain('<PanelTitle concept="devices">');
  });
});
