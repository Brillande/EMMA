import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LookContext } from "../components/BoardOnly";
import type { Sharing, SharingItem } from "../lib/api";
import { OK_MARK, UNKNOWN_MARK } from "../lib/marks";
import { SharingView } from "./SharingPanel";
import { enforcementMark, itemsByDestination } from "./sharing";

/**
 * «Qué se comparte y qué no» (`GET /api/sharing`): los destinos en el orden del backend, la marca de
 * cada grado y que el texto se pinta tal cual. Las frases son marcadores.
 */

// Los destinos y los grados del backend: uno nuevo sin sitio aquí saldría sin agrupar.
const BACKEND = readFileSync(fileURLToPath(new URL("../../../backend/app/sharing.py", import.meta.url)), "utf-8");
const tuple = (name: string) =>
  [...(new RegExp(`${name} = \\(([^)]*)\\)`).exec(BACKEND)?.[1] ?? "").matchAll(/"([a-z]+)"/g)].map((m) => m[1]);

function row(id: string, destination: SharingItem["destination"], enforcement: SharingItem["enforcement"]): SharingItem {
  return {
    id,
    title: `TITULO-${id}`,
    destination,
    destination_text: `DESTINO-${destination}`,
    text: `TEXTO-${id}`,
    enforcement,
    enforcement_text: `GRADO-${enforcement}`,
    limit: enforcement === "code" ? null : `LIMITE-${id}`,
    enforced_by: enforcement === "none" ? [] : [`app.modulo.${id}`],
  };
}

const body: Sharing = {
  note: "NOTA-DE-LA-TABLA",
  destinations: [
    { id: "internet", label: "SALE-A-INTERNET" },
    { id: "ground", label: "LO-VE-TIERRA" },
    { id: "board", label: "A-BORDO" },
    { id: "device", label: "EN-LA-CONSOLA" },
    { id: "nowhere", label: "NO-SE-GUARDA" },
  ],
  items: [
    row("internet-queries", "internet", "code"),
    row("readings", "ground", "partial"),
    row("personal-notes", "ground", "none"),
    row("drafts", "board", "partial"),
  ],
  internet: {
    offline: true,
    offline_text: "AHORA-SIN-RED",
    purposes: [{ purpose: "space-weather", what: "QUE-DONKI", carries: "LLEVA-FECHAS", hosts: ["api.nasa.gov"] }],
  },
  ground_cut: {
    note: "NOTA-DEL-CORTE",
    routes: [{ path: "/api/status", direction: "down", direction_text: "BAJA" }],
  },
};

describe("qué se comparte y qué no", () => {
  it("los destinos y los grados son los del backend", () => {
    expect(tuple("DESTINATIONS")).toEqual(body.destinations.map((d) => d.id));
    expect(tuple("ENFORCEMENT")).toEqual(["code", "partial", "none"]);
  });

  it("lo que impone el código lleva la de visto; lo demás, la palabra del backend sin color propio", () => {
    expect(enforcementMark("code")).toBe(OK_MARK);
    expect(enforcementMark("partial")).toBe(UNKNOWN_MARK);
    expect(enforcementMark("none")).toBe(UNKNOWN_MARK);
  });

  it("agrupa por destino en el orden del backend y calla los destinos vacíos", () => {
    expect(itemsByDestination(body).map((group) => [group.id, group.items.map((item) => item.id)])).toEqual([
      ["internet", ["internet-queries"]],
      ["ground", ["readings", "personal-notes"]],
      ["board", ["drafts"]],
    ]);
  });

  it("pinta el texto del backend tal cual, con lo que queda fuera y dónde se impone", () => {
    const html = renderToStaticMarkup(createElement(SharingView, { body }));
    for (const text of [
      "NOTA-DE-LA-TABLA",
      "AHORA-SIN-RED",
      "SALE-A-INTERNET",
      "TEXTO-readings",
      "GRADO-none",
      "LIMITE-personal-notes",
      "app.modulo.drafts",
      "QUE-DONKI",
      "api.nasa.gov",
      "NOTA-DEL-CORTE",
      "/api/status",
      "BAJA",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toContain("NO-SE-GUARDA");
    expect(html).toContain('data-ui="sharing"');
    expect(html).toContain('data-ui="sharing-item"');
    expect(html).toContain('data-ui="sharing-purposes"');
    expect(html).toContain('data-ui="sharing-cut"');
  });

  // Lote «muestra» (2026-11-08): en el tablero, lo que SALE del equipo no se pliega nunca; lo que se
  // queda, los propósitos, las rutas y la nota, detrás de «Ver detalle». En la clásica, sin mando.
  it("en el tablero, lo que sale del equipo queda a la vista y lo que se queda, en el detalle", () => {
    const html = renderToStaticMarkup(createElement(SharingView, { body }));
    const at = (text: string) => {
      const index = html.indexOf(text);
      expect(index, text).toBeGreaterThanOrEqual(0);
      return index;
    };
    expect(at("AHORA-SIN-RED")).toBeLessThan(at("Ver detalle: por qué esta tabla"));
    expect(at("NOTA-DE-LA-TABLA")).toBeGreaterThan(at("Ver detalle: por qué esta tabla"));
    expect(at("TITULO-internet-queries")).toBeLessThan(at("Ver detalle: SALE-A-INTERNET"));
    expect(at("QUE-DONKI")).toBeGreaterThan(at("Ver detalle: SALE-A-INTERNET"));
    expect(at("TITULO-personal-notes")).toBeLessThan(at("Ver detalle: LO-VE-TIERRA"));
    expect(at("TITULO-drafts")).toBeGreaterThan(at("Ver detalle: A-BORDO"));
    const classic = renderToStaticMarkup(
      createElement(LookContext.Provider, { value: "classic" }, createElement(SharingView, { body })),
    );
    expect(classic).not.toContain("Ver detalle");
    expect(classic.indexOf("NOTA-DE-LA-TABLA")).toBeLessThan(classic.indexOf("AHORA-SIN-RED"));
  });
});
