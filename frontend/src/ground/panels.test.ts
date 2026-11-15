import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, thSign, textNodes } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import { indicatorFamily } from "../lib/indicatorFamily";
import type { AuditReport, CrewStatus } from "../lib/api";
import { UNKNOWN_MARK } from "../lib/marks";
import { type UiConcept, uiPictogram } from "../lib/uiMarks";
import { AuditPanel } from "./AuditPanel";
import { DocsPanel } from "./DocsPanel";
import { ForecastCheckPanel, KIND, checkKind } from "./ForecastCheckPanel";
import { FrameworkPanel } from "./FrameworkPanel";
import { PolarisPanel } from "./PolarisPanel";
import { RisksPanel } from "./RisksPanel";

/**
 * Los paneles de Tierra que se pintan sin red, pintados: el pictograma va junto a la palabra que
 * ya existía, con `data-pictogram` para poder fijarlo. Que ningún panel escriba ya un glifo de
 * texto lo vigila `lib/glyphs.test.ts` para toda la interfaz (§5.32 del estado del arte).
 */

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

const checks: CrewStatus["forecast_checks"] = {
  checked: 2,
  within_margin: 1,
  basis: "base del backend",
  checks: [
    {
      key: "heart-rate",
      display: "Heart rate",
      display_es: "Frecuencia cardíaca",
      unit: "/min",
      kind: "hindcast",
      projected_change: 2,
      projected_change_low: 1,
      projected_change_high: 3,
      actual_change: 2.5,
      error: 0.5,
      within_margin: true,
    },
    {
      key: "sleep-duration",
      display: "Sleep duration",
      display_es: "Duración del sueño",
      unit: "h",
      kind: "snapshot",
      projected_change: -0.5,
      projected_change_low: -0.8,
      projected_change_high: -0.2,
      actual_change: -1.4,
      error: 0.9,
      within_margin: false,
    },
  ],
};

describe("<ForecastCheckPanel>", () => {
  const html = render(createElement(ForecastCheckPanel, { checks }));

  it("cada indicador lleva el pictograma de su familia junto a su nombre", () => {
    expect(html).toContain(`data-pictogram="${indicatorFamily("heart-rate")}"`);
    expect(html).toContain(`data-pictogram="${indicatorFamily("sleep-duration")}"`);
    expect(textNodes(html)).toContain("Frecuencia cardíaca");
  });

  it("dentro del margen, el anillo sin color; fuera, el rombo en azul", () => {
    expect(html).toMatch(/<span class="mark secondary"><svg[^>]*data-pictogram="shape-circle"[^>]*>.*?<\/svg>dentro<\/span>/);
    expect(html).toMatch(/<span class="mark c-blue"><svg[^>]*data-pictogram="shape-diamond"[^>]*>.*?<\/svg>fuera<\/span>/);
  });

  it("cada clase de comprobación lleva su pictograma junto a su rótulo", () => {
    for (const { label, pictogram } of Object.values(KIND)) {
      expect(html).toMatch(new RegExp(`data-pictogram="${pictogram}"[^>]*>.*?</svg>${label}</span>`));
    }
    expect(KIND["hindcast"]?.pictogram).not.toBe(KIND["snapshot"]?.pictogram);
  });

  it("una clase que la interfaz no conoce sale con su clave y la marca de desconocido, sin tumbar la tabla", () => {
    expect(checkKind("replay")).toEqual({ label: "replay", pictogram: UNKNOWN_MARK.pictogram });
    const first = checks.checks[0];
    if (first === undefined) throw new Error("sin comprobaciones de prueba");
    const odd = { ...checks, checks: [{ ...first, kind: "replay" as (typeof first)["kind"] }] };
    const html = render(createElement(ForecastCheckPanel, { checks: odd }));
    expect(html).toMatch(/data-pictogram="dot-small"[^>]*>.*?<\/svg>replay<\/span>/);
  });

  it("sin comprobaciones no pinta nada", () => {
    expect(render(createElement(ForecastCheckPanel, { checks: { ...checks, checked: 0 } }))).toBe("");
  });

  it("tablero: el anillo de cuántas cayeron dentro, con su cifra y su nombre accesible", () => {
    expect(html).toContain('role="img" aria-label="1 de 2 comprobadas dentro de su margen"');
    expect(html).toContain('<span class="num ref-ring-value">1</span>');
    // La frase de siempre sigue: es la leyenda del anillo y lo que lee la clásica.
    expect(textNodes(html).join(" ")).toContain("dentro de su margen");
  });

  it("tablero: cada fila, su margen como tramo con lo medido como marca, en su escala simétrica", () => {
    expect(html).toContain('aria-label="margen de 1,00 a 3,00 /min; medido 2,50 /min"');
    expect(html).toContain('aria-label="margen de -0,80 a -0,20 h; medido -1,40 h"');
    // Escala de la propia fila: ±3 en la primera (el tramo de 1 a 3 va de 66,7 % a 100 %).
    expect(html).toContain('style="left:66.7%;width:33.3%"');
    expect(html).toContain('class="board-range-marker" style="left:91.7%"');
    // En la segunda, ±1,4: lo medido, fuera del margen, cae en el extremo y fuera del tramo.
    expect(html).toContain('class="board-range-marker" style="left:0.0%"');
  });

  it("tablero: con todo a cero no se dibuja el tramo, y la clásica no lleva ninguna pieza", () => {
    const first = checks.checks[0];
    if (first === undefined) throw new Error("sin comprobaciones de prueba");
    const flat = { ...first, projected_change: 0, projected_change_low: 0, projected_change_high: 0, actual_change: 0 };
    expect(render(createElement(ForecastCheckPanel, { checks: { ...checks, checks: [flat] } }))).not.toContain("board-range");
    const classic = render(createElement(LookContext.Provider, { value: "classic" }, createElement(ForecastCheckPanel, { checks })));
    expect(classic).not.toContain("ref-ring");
    expect(classic).not.toContain("board-range");
  });

  it("tablero: una fila por indicador junto al anillo; la tabla y la base, detrás de «Ver detalle»", () => {
    expect(html).toContain('aria-label="Margen proyectado y lo medido, por indicador"');
    expect(html).toContain("Ver detalle: cifras y base");
    expect(html).toMatch(/<div id="[^"]+" class="board-detail-body" hidden="">.*Proyectado frente a medido/);
    // La frase del recuento sigue a la vista, fuera del pliegue.
    expect(html.indexOf("dentro de su margen</p>")).toBeLessThan(html.indexOf("board-detail"));
    const classic = render(createElement(LookContext.Provider, { value: "classic" }, createElement(ForecastCheckPanel, { checks })));
    expect(classic).not.toContain("Ver detalle");
    expect(classic).toContain("Proyectado frente a medido");
  });
});

const audit = (ok: boolean): AuditReport => ({
  entries: [
    { index: 0, entry_type: "vital-observation", signer: "emma", recorded: "2026-10-20T10:00:00Z", content_hash: "a".repeat(64) },
    { index: 1, entry_type: "alert-acknowledgement", signer: "crew-01", recorded: "2026-10-20T10:01:00Z", content_hash: "b".repeat(64) },
    { index: 2, entry_type: "asiento-nuevo", signer: "emma", recorded: "2026-10-20T10:02:00Z", content_hash: "c".repeat(64) },
  ],
  total_entries: 3,
  merkle_root: ok ? "d".repeat(64) : null,
  integrity_ok: ok,
  failed_index: ok ? null : 2,
  failure_reason: ok ? null : "firma inválida",
});

describe("<AuditPanel>", () => {
  it("la cadena que verifica lleva la marca de hecho, sin color", () => {
    const html = render(createElement(AuditPanel, { audit: audit(true) }));
    expect(html).toMatch(/<span class="mark"><svg[^>]*data-pictogram="check"[^>]*>.*?<\/svg>La cadena verifica<\/span>/);
    expect(html).not.toContain("c-red");
  });

  it("la cadena que falla lleva el aspa en rojo, con el asiento y el motivo del backend", () => {
    const html = render(createElement(AuditPanel, { audit: audit(false) }));
    expect(html).toMatch(/<span class="mark c-red"><svg[^>]*data-pictogram="cross"/);
    expect(textNodes(html).join(" ")).toContain("Falla en el asiento 2: firma inválida");
  });

  it("en el tablero, el número de asientos es una ficha grande con el veredicto debajo, y la lista solo lleva la raíz", () => {
    const ok = render(createElement(AuditPanel, { audit: audit(true) }));
    expect(ok).toMatch(/<div class="stat-tile">[\s\S]*?Asientos<\/span><span class="stat-value"><span class="num">3<\/span><\/span><span class="mark"><svg[^>]*data-pictogram="check"/);
    expect(ok).not.toMatch(taggedPictogram("dt", uiPictogram("signedLedger"), "Integridad"));
    expect(ok).toMatch(taggedPictogram("dt", uiPictogram("value"), "Raíz de Merkle"));
    expect(ok).toContain("d".repeat(64));
    const failed = render(createElement(AuditPanel, { audit: audit(false) }));
    expect(failed).toMatch(/<div class="stat-tile">[\s\S]*?<span class="mark c-red"><svg[^>]*data-pictogram="cross"/);
  });

  it("en el tablero, píldoras con cuántos de los asientos mostrados son de cada tipo", () => {
    const html = render(createElement(AuditPanel, { audit: audit(true) }));
    const tally = html.match(/<ul class="board-tally" aria-label="Asientos mostrados, por tipo">[\s\S]*?<\/ul>/)?.[0] ?? "";
    expect(textNodes(tally)).toEqual(["3", "asientos mostrados", "vital-observation", "1", "alert-acknowledgement", "1", "asiento-nuevo", "1"]);
  });

  it("cada asiento lleva el pictograma de su clase junto a su tipo, escrito tal cual; uno desconocido, el punto", () => {
    const html = render(createElement(AuditPanel, { audit: audit(true) }));
    expect(html).toMatch(/data-pictogram="dot-filled"[^>]*>.*?<\/svg>vital-observation<\/span>/);
    expect(html).toMatch(/data-pictogram="bell"[^>]*>.*?<\/svg>alert-acknowledgement<\/span>/);
    expect(html).toMatch(/<span class="mark c-text"><svg[^>]*data-pictogram="dot-small"[^>]*>.*?<\/svg>asiento-nuevo<\/span>/);
  });
});

/**
 * Segunda pasada (§5.33.6): título, rótulos, cabeceras y estados de cada panel de Tierra con su
 * signo, el de su concepto en `lib/uiMarks.ts` o el dibujo propio de Tierra. Los paneles que piden
 * datos se pintan aquí antes de la respuesta (sin efectos en `renderToStaticMarkup`): es el estado
 * de «consultando», con la flecha que gira.
 */
describe("el mobiliario de Tierra lleva su signo", () => {
  it("el registro firmado: candado en el título y el rótulo de integridad, y cada cabecera con el suyo", () => {
    // Las filas de integridad y de asientos son de la clásica: en el tablero van en la ficha.
    const html = render(
      createElement(LookContext.Provider, { value: "classic" }, createElement(AuditPanel, { audit: audit(true) })),
    );
    expect(html).toMatch(taggedPictogram("h2", uiPictogram("signedLedger"), "Registro firmado a bordo"));
    expect(html).toMatch(taggedPictogram("dt", uiPictogram("signedLedger"), "Integridad"));
    expect(html).toMatch(taggedPictogram("dt", uiPictogram("value"), "Asientos"));
    expect(html).toMatch(taggedPictogram("dt", uiPictogram("value"), "Raíz de Merkle"));
    const headers: [UiConcept, string][] = [
      ["value", "Asiento"],
      ["type", "Tipo"],
      ["person", "Firmante"],
      ["time", "Registrado (UTC)"],
      ["signedLedger", "Hash"],
    ];
    for (const [concept, word] of headers) {
      expect(html).toMatch(thSign(uiPictogram(concept), word, ' scope="col"'));
    }
  });

  it("las proyecciones: el reloj que mira atrás en el título y cada cabecera con su concepto", () => {
    const html = render(createElement(ForecastCheckPanel, { checks }));
    expect(html).toMatch(taggedPictogram("h2", uiPictogram("forecastCheck"), "¿Acertaron las proyecciones?"));
    const headers: [UiConcept, string][] = [
      ["indicator", "Indicador"],
      ["range", "Proyectado (margen)"],
      ["measured", "Medido"],
      ["type", "Tipo"],
    ];
    for (const [concept, word] of headers) {
      expect(html).toMatch(thSign(uiPictogram(concept), word, ' scope="col"'));
    }
  });

  it("exportar y documentación: el libro abierto en el título y la lupa en el mando de buscar", () => {
    const html = render(createElement(DocsPanel, { subject: "crew-01", until: null }));
    expect(html).toMatch(taggedPictogram("h2", uiPictogram("docs"), "Exportar y documentación"));
    expect(html).toMatch(
      taggedPictogram("button", uiPictogram("search"), "Buscar", ' class="command" type="submit" disabled=""'),
    );
  });

  it("el marco, los riesgos y la copia de Polaris: su título y, mientras consultan, la marca de cargando", () => {
    const framework = render(createElement(FrameworkPanel));
    expect(framework).toMatch(
      taggedPictogram("h2", uiPictogram("nasaFramework"), "Marco de NASA e hipótesis de diseño"),
    );
    expect(framework).toMatch(markedHtml("refresh", "Consultando el marco…"));

    const risks = render(createElement(RisksPanel));
    expect(risks).toMatch(taggedPictogram("h3", uiPictogram("risks"), "Riesgos", ' class="section-gap"'));
    expect(risks).toMatch(markedHtml("refresh", "Consultando los riesgos…"));

    const polaris = render(createElement(PolarisPanel));
    expect(polaris).toMatch(taggedPictogram("h2", "plug", "Código de terceros: copia de Polaris"));
    expect(polaris).toMatch(markedHtml("refresh", "Consultando la copia…"));
  });
});

// El barrido de glifos de texto que nacio aqui para `ground/` cubre ahora toda la interfaz:
// `lib/glyphs.test.ts`.
