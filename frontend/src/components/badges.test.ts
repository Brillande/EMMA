import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { LEVELS, LEVEL_ORDER, adoptLevelLabels } from "../lib/levels";
import { OBSERVATION_TYPES } from "../lib/provenance";
import { LevelBadge } from "./LevelBadge";
import { ObservationTypeBadge } from "./ObservationTypeBadge";
import { QualityBadge } from "./QualityBadge";

/**
 * Las tres insignias comunes, pintadas: nivel, confianza y tipo de observacion. Lo que cada una
 * promete tras pasar a pictogramas: la palabra del backend sigue siendo el unico texto, el
 * pictograma es el del nivel o del tipo, el color va en la clase, y solo lo critico parpadea.
 */

afterEach(() => adoptLevelLabels(null));

describe("<LevelBadge>", () => {
  it("cada nivel con su pictograma, su color y su palabra", () => {
    adoptLevelLabels({ nominal: "P-0", watch: "P-1", concern: "P-2", critical: "P-3" });
    for (const level of LEVEL_ORDER) {
      const html = renderToStaticMarkup(createElement(LevelBadge, { level }));
      const style = LEVELS[level];
      expect(html).toContain(`<span class="mark level c-${style.color}">`);
      expect(html).toContain(`data-pictogram="${style.pictogram}"`);
      expect(textNodes(html)).toEqual([style.label]);
    }
  });

  it("parpadea solo el pictograma, solo en critico y solo si se pide", () => {
    const critical = renderToStaticMarkup(createElement(LevelBadge, { level: "critical", flashing: true }));
    expect(critical).toContain('<span class="mark level c-red"><svg class="pictogram flash"');
    expect(renderToStaticMarkup(createElement(LevelBadge, { level: "critical" }))).not.toContain("flash");
    for (const level of ["nominal", "watch", "concern"]) {
      expect(renderToStaticMarkup(createElement(LevelBadge, { level, flashing: true }))).not.toContain("flash");
    }
  });

  it("un nivel desconocido falla en vez de pintarse", () => {
    expect(() => renderToStaticMarkup(createElement(LevelBadge, { level: "otro" }))).toThrow(RangeError);
  });
});

describe("<QualityBadge>", () => {
  it("confianza declarada: solo la palabra del backend, sin pictograma ni color", () => {
    const html = renderToStaticMarkup(createElement(QualityBadge, { state: "declared", label: "PALABRA" }));
    expect(html).toBe('<span class="mark obs-type">PALABRA</span>');
    expect(html).not.toContain("<svg");
  });

  it("baja confianza: triangulo y amarillo, con la cifra si la hay", () => {
    const html = renderToStaticMarkup(
      createElement(QualityBadge, { state: "low", label: "BAJA", confidence: 0.3 }),
    );
    expect(html).toContain('<span class="mark obs-type c-yellow">');
    expect(html).toContain('data-pictogram="shape-triangle"');
    expect(textNodes(html)).toEqual(["BAJA", "0,30"]);
  });

  it("sin confianza no se pinta ningun numero", () => {
    const html = renderToStaticMarkup(createElement(QualityBadge, { state: "low", label: "BAJA" }));
    expect(textNodes(html)).toEqual(["BAJA"]);
  });
});

describe("<ObservationTypeBadge>", () => {
  it("cada tipo con su pictograma, su palabra y el significado en el title del span", () => {
    for (const [type, style] of Object.entries(OBSERVATION_TYPES)) {
      const html = renderToStaticMarkup(createElement(ObservationTypeBadge, { type }));
      expect(html).toContain(`<span class="mark obs-type" title="${style.meaning}">`);
      expect(html).toContain(`data-pictogram="${style.pictogram}"`);
      expect(textNodes(html)).toEqual([style.word]);
    }
  });

  it("el entorno va detras, en secundario, con su pictograma junto a su palabra", () => {
    const html = renderToStaticMarkup(createElement(ObservationTypeBadge, { type: "measured", context: "iss" }));
    expect(html).toMatch(
      /<span class="secondary"> · <span class="mark"><svg [^>]*data-pictogram="station"[^>]*>.*?<\/svg>ISS<\/span><\/span>/,
    );
    expect(textNodes(html)).toEqual(["MEDIDO", "·", "ISS"]);
  });

  it("sin color propio: el cian diria caducado", () => {
    const html = renderToStaticMarkup(createElement(ObservationTypeBadge, { type: "predicted" }));
    expect(html).not.toMatch(/c-(red|yellow|blue|gray|cyan|magenta|green)/);
  });
});
