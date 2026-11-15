import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { UNKNOWN_MARK } from "../lib/marks";
import { DOMAIN_LABELS } from "../lib/levels";
import { DomainName } from "./DomainName";
import { IndicatorName } from "./IndicatorName";

/** El nombre de un dominio y el de un indicador, con su pictograma y sin color: nombran, no avisan. */

describe("<DomainName>", () => {
  it("cada dominio con su pictograma y su nombre en espanol", () => {
    for (const [domain, label] of Object.entries(DOMAIN_LABELS)) {
      const html = renderToStaticMarkup(createElement(DomainName, { domain }));
      expect(html).toContain(`data-pictogram="domain-${domain}"`);
      expect(html).toMatch(/^<span class="mark">/);
      expect(textNodes(html)).toEqual([label]);
    }
  });

  it("la palabra del backend, si se da, manda sobre la tabla de la interfaz", () => {
    const html = renderToStaticMarkup(createElement(DomainName, { domain: "bone", label: "PALABRA" }));
    expect(textNodes(html)).toEqual(["PALABRA"]);
  });

  it("un dominio desconocido se ensena con su clave y el dibujo de desconocido, sin color ni dibujo supuesto", () => {
    const html = renderToStaticMarkup(createElement(DomainName, { domain: "otro" }));
    expect(html).toContain(`data-pictogram="${UNKNOWN_MARK.pictogram}"`);
    expect(html).toMatch(/^<span class="mark">/);
    expect(textNodes(html)).toEqual(["otro"]);
  });
});

describe("<IndicatorName>", () => {
  it("el pictograma de la familia y display_es tal cual", () => {
    const html = renderToStaticMarkup(
      createElement(IndicatorName, { indicatorKey: "onsd-left", displayEs: "NOMBRE-DEL-BACKEND" }),
    );
    expect(html).toContain('data-pictogram="eye-nerve"');
    expect(html).toMatch(/^<span class="mark">/);
    expect(textNodes(html)).toEqual(["NOMBRE-DEL-BACKEND"]);
  });

  it("una clave sin familia se ensena con su nombre y el dibujo de desconocido: la consola no se cae", () => {
    const html = renderToStaticMarkup(
      createElement(IndicatorName, { indicatorKey: "inventado", displayEs: "NOMBRE-NUEVO" }),
    );
    expect(html).toContain(`data-pictogram="${UNKNOWN_MARK.pictogram}"`);
    expect(html).toMatch(/^<span class="mark">/);
    expect(textNodes(html)).toEqual(["NOMBRE-NUEVO"]);
  });
});
