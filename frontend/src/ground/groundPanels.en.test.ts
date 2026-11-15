/**
 * La consola de Tierra en inglés (`lib/i18n.ts`): lo que escribe la interfaz en la cabecera del
 * retardo, el registro, las proyecciones, la documentación, las notas, el historial, la
 * recuperación, las tendencias y la copia de Polaris. Lo que redacta el backend (aquí, marcadores)
 * se pinta tal cual. Marcas, colores y cifras los fijan las pruebas en castellano de cada pieza.
 */
import "../test/english";

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LookContext } from "../components/BoardOnly";
import type { AuditReport, CrewStatus, GroundNotes, Indicator, LinkSync } from "../lib/api";
import { formatMinutes } from "../lib/format";
import { language } from "../lib/i18n";
import { AuditPanel } from "./AuditPanel";
import { DocsPanel } from "./DocsPanel";
import { ForecastCheckPanel, checkKind } from "./ForecastCheckPanel";
import { DelayBanner } from "./GroundConsole";
import { GroundNotesComposer, GroundNotesSent, NotesTally, transitMark } from "./GroundNotesComposer";
import { MissionHistoryGround } from "./MissionHistoryPanel";
import { PolarisPanel } from "./PolarisPanel";
import { RecoveryPanel, ReturnTally } from "./RecoveryPanel";
import { TrendChart } from "./TrendChart";
import { POLARIS_FILTERS, useStyle } from "./polarisInventory";

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);
const onBoard = (element: Parameters<typeof renderToStaticMarkup>[0]) =>
  render(createElement(LookContext.Provider, { value: "reference" }, element));

const QUEUE = { count: 0, readings: 0, other: 0, first: null, last: null, first_index: null };
const SYNC = {
  state: "up",
  held: false,
  held_since: null,
  to_send: QUEUE,
  to_arrive: QUEUE,
  ground_sentence: "FRASE-DE-TIERRA-DEL-BACKEND",
  known_only_here: "SOLO-AQUI",
} as unknown as LinkSync;

describe("la consola de Tierra en inglés", () => {
  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
  });

  it("las pestañas llevan el vocabulario acordado junto a su castellano", () => {
    const source = readFileSync(fileURLToPath(new URL("./GroundConsole.tsx", import.meta.url)), "utf8");
    for (const pair of [
      'label: tr("Estado recibido", "Received status")',
      'label: tr("Historial", "History")',
      'label: tr("Tendencias", "Trends")',
      'label: tr("Hábitat", "Habitat")',
      'label: tr("Marco y fuentes", "Framework and sources")',
      'label: tr("Registro y documentos", "Ledger and documents")',
      'label: tr("Biblioteca", "Library")',
    ]) {
      expect(source, pair).toContain(pair);
    }
  });

  it("la cabecera del retardo: fichas y frase en inglés; las frases del backend, tal cual", () => {
    const html = render(
      createElement(DelayBanner, {
        oneWay: 14,
        earthMet: "MET 10/04:00",
        onboardMet: "MET 10/04:14",
        link: null,
        linkError: null,
        sync: SYNC,
      }),
    );
    expect(html).toContain('aria-label="Delay applied"');
    expect(html).toContain("Earth has data up to");
    expect(html).toContain("On board they are already at");
    expect(html).toContain(`One-way delay <span class="num">${formatMinutes(14)}</span>. Any instruction sent now`);
    expect(html).toContain(": the crew decides on its own.");
    expect(html).toContain("FRASE-DE-TIERRA-DEL-BACKEND");
    expect(html).not.toMatch(/Retardo|Tierra tiene|A bordo ya|tripulación/);
  });

  it("sin efemérides lo dice en inglés", () => {
    const html = render(
      createElement(DelayBanner, {
        oneWay: null,
        earthMet: "MET 10/04:00",
        onboardMet: "MET 10/04:14",
        link: null,
        linkError: null,
        sync: SYNC,
      }),
    );
    expect(html).toContain("No ephemeris: the delay cannot be applied. Everything on board is shown.");
    expect(html).not.toContain("Sin efemérides");
  });

  it("el registro firmado: título, veredicto, cabeceras y cuenta de asientos", () => {
    const audit = (ok: boolean): AuditReport => ({
      entries: [
        { index: 0, entry_type: "vital-observation", signer: "emma", recorded: "2026-10-20T10:00:00Z", content_hash: "a".repeat(64) },
      ],
      total_entries: 1,
      merkle_root: ok ? "d".repeat(64) : null,
      integrity_ok: ok,
      failed_index: ok ? null : 0,
      failure_reason: ok ? null : "MOTIVO-DEL-BACKEND",
    });
    // La vista clásica lleva también el rótulo de integridad en la lista; el tablero, en la ficha.
    const good = render(
      createElement(LookContext.Provider, { value: "classic" }, createElement(AuditPanel, { audit: audit(true) })),
    );
    expect(good).toContain('aria-label="Signed ledger"');
    expect(good).toContain("Signed ledger on board");
    expect(good).toContain("The chain verifies");
    expect(good).toContain("The anchor would be sent to Earth: entry count and Merkle root.");
    for (const head of ["Entry", "Type", "Signer", "Recorded (UTC)", "Merkle root", "Integrity"]) {
      expect(good, head).toContain(head);
    }
    // El tipo de asiento es la clave del registro: no se traduce.
    expect(good).toContain("vital-observation");
    expect(good).not.toMatch(/Registro firmado|La cadena verifica|Asiento|Firmante|Raíz/);

    const bad = render(createElement(AuditPanel, { audit: audit(false) }));
    expect(bad).toContain("Fails at entry 0: MOTIVO-DEL-BACKEND");
    expect(bad).toContain("no anchor: the chain does not verify");
    expect(onBoard(createElement(AuditPanel, { audit: audit(true) }))).toContain("entry shown");
  });

  it("las proyecciones comprobadas: título, cabeceras, dentro y fuera, y la clase de comprobación", () => {
    const checks = {
      checked: 2,
      within_margin: 1,
      basis: "BASE-DEL-BACKEND",
      checks: [
        { key: "heart-rate", display: "Heart rate", display_es: "NOMBRE-A", unit: "/min", kind: "hindcast", projected_change: 2, projected_change_low: 1, projected_change_high: 3, actual_change: 2.5, error: 0.5, within_margin: true },
        { key: "sleep-duration", display: "Sleep duration", display_es: "NOMBRE-B", unit: "h", kind: "snapshot", projected_change: -0.5, projected_change_low: -0.8, projected_change_high: -0.2, actual_change: -1.4, error: 0.9, within_margin: false },
      ],
    } as unknown as CrewStatus["forecast_checks"];
    const html = render(createElement(ForecastCheckPanel, { checks }));
    expect(html).toContain('aria-label="Projection check"');
    expect(html).toContain("Did the projections hold?");
    expect(html).toContain("within their margin");
    for (const word of ["Indicator", "Projected (margin)", "Measured", "within", "outside", "hindcast", "signed snapshot"]) {
      expect(html, word).toContain(word);
    }
    expect(html).toContain("BASE-DEL-BACKEND");
    expect(html).not.toMatch(/proyecciones|Proyectado|Medido|dentro|fuera|retrospectiva|instantánea/);
    // Una clase que la interfaz no conoce sale con su clave, en cualquier idioma.
    expect(checkKind("otra").label).toBe("otra");
  });

  it("exportar y documentación: los mandos y la búsqueda", () => {
    const html = render(createElement(DocsPanel, { subject: "crew-01", until: null }));
    expect(html).toContain("Export and documentation");
    for (const word of ["Received status (PDF)", "Chronicle (PDF)", "Pain entries received (PDF)", "Evidence dossier (PDF)", "Search"]) {
      expect(html, word).toContain(word);
    }
    expect(html).toContain('aria-label="Search the documentation"');
    expect(html).not.toMatch(/Exportar|Crónica|Dosier|Buscar/);
  });

  it("las notas a bordo: título, lista vacía, dónde está cada nota y el aviso del tiempo de luz", () => {
    const composer = render(createElement(GroundNotesComposer, { subject: "crew-01", oneWayMinutes: 10 }));
    expect(composer).toContain("Notes to the crew");
    expect(composer).toContain("Reading the rules for a note…");
    expect(composer).not.toMatch(/Notas a bordo|Leyendo/);

    const empty = { subject: "crew-01", until: null, notes: [], withheld: 0, withheld_note: null, basis: "" } as unknown as GroundNotes;
    const sent = render(createElement(GroundNotesSent, { data: empty, unavailable: null, oneWayMinutes: 10, now: 0 }));
    expect(sent).toContain("No signed note for this crew member.");
    expect(sent).toContain("A note reaches the crew one light time after it is signed.");
    expect(sent).not.toMatch(/Ninguna nota|tripulante/);

    expect(render(createElement(NotesTally, { notes: [], oneWayMinutes: 10, now: 0 }))).toContain("Signed");
    expect(transitMark({ state: "on-board", at: new Date(0) }).word).toBe("on board since");
    expect(transitMark({ state: "in-transit", at: new Date(0) }).word).toBe("on its way: arrives around");
    expect(transitMark({ state: "unknown" }).word).toContain("without ephemeris");
  });

  it("el historial misión a misión: título y aviso de lo que va en tránsito", () => {
    const html = render(createElement(MissionHistoryGround, { data: null, unavailable: null, oneWayMinutes: 20 }));
    expect(html).toContain('aria-label="Mission-by-mission history"');
    expect(html).toContain("What was declared on board less than");
    expect(html).toContain("ago is in transit and not yet visible here.");
    expect(html).not.toMatch(/Historial|Lo declarado/);
  });

  it("la recuperación: las píldoras de vuelta al rango; sin informe no pinta nada", () => {
    const html = render(createElement(ReturnTally, { states: ["within", "back-again", "not-back", "no-preflight-range", "otra"] }));
    expect(html).toContain('aria-label="Indicators by return to range"');
    for (const word of ["within", "within again", "not back", "no preflight range", "otra"]) {
      expect(html, word).toContain(word);
    }
    expect(html).not.toMatch(/dentro|sin volver|sin rango/);
    expect(render(createElement(RecoveryPanel, { subject: "crew-01", refreshKey: "k" }))).toBe("");
  });

  it("una gráfica de tendencia: leyenda y cifras de la ventana", () => {
    const indicator = {
      key: "heart-rate",
      display: "Heart rate",
      display_es: "NOMBRE-DEL-BACKEND",
      unit: "/min",
      reference_low: 50,
      reference_high: 90,
      critical_low: 30,
      critical_high: null,
      decimals: 1,
    } as unknown as Indicator;
    const html = onBoard(
      createElement(TrendChart, {
        indicator,
        points: [{ met: 120, value: 61, confidence: 1 }],
        receivedUntil: 400,
        onboardUntil: 1000,
        windowSeconds: 900,
      }),
    );
    for (const word of ["— received on Earth", "- - reference range", "— danger limit", "in transit: on board, not yet received", "Last received", "Readings", "Minimum", "Maximum"]) {
      expect(html, word).toContain(word);
    }
    expect(html).toContain('aria-label="Window figures"');
    expect(html).toContain("NOMBRE-DEL-BACKEND");
    expect(html).not.toMatch(/recibido en Tierra|rango de referencia|límite de peligro|Mínimo|Máximo|Lecturas/);
  });

  it("la copia de Polaris: título, espera y filtros", () => {
    const html = render(createElement(PolarisPanel));
    expect(html).toContain('aria-label="Polaris copy"');
    expect(html).toContain("Third-party code: Polaris copy");
    expect(html).toContain("Querying the copy…");
    expect(html).not.toMatch(/Código de terceros|Consultando/);
    expect(POLARIS_FILTERS.map((item) => item.label)).toEqual([
      "All",
      "Load",
      "Do not load",
      "Not imported",
      "In use by EMMA",
      "Copied, unused",
    ]);
    // La clave del filtro es la de siempre.
    expect(POLARIS_FILTERS.map((item) => item.id)).toEqual(["all", "loads", "fails", "skipped", "used", "unused"]);
    expect(useStyle({ en_uso: true } as Parameters<typeof useStyle>[0]).word).toBe("in use by EMMA");
  });
});
