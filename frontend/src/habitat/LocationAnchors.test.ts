import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { markedHtml, textLines } from "../advisor/visibleText";
import { CONSOLE_HEADER, CONSOLE_HEADER_VALUE, type HabitatModules, type LocationAnchors, api } from "../lib/api";
import {
  EMPTY_ANCHOR_FORM,
  LocationAnchorsView,
  anchorBody,
  canDeclareAnchor,
} from "./LocationAnchors";
import { modulePictogram } from "./pictograms";

/**
 * Las anclas de módulo del hábitat (2026-11-10): la lista de lo declarado con el texto del backend y,
 * a bordo, el formulario «ancla → módulo», que firma el operador de la consola y va con la cabecera
 * de la consola a `POST /api/location/anchors`, con el cuerpo que fija el contrato.
 */

const MODULES: HabitatModules = {
  modules: [
    { key: "laboratorio", display: "Laboratorio", description: "" },
    { key: "nodo", display: "Nodo", description: "" },
  ],
  default: "laboratorio",
  basis: "lista declarada: texto del backend",
};

const ANCHORS: LocationAnchors = {
  anchors: [
    {
      anchor_id: "f7826da6-4fa2-4e98-8024-bc5b71e0893e:1:7",
      module: "laboratorio",
      display: "Laboratorio (backend)",
      since: "2026-11-01T00:00:00+00:00",
      ledger_index: 1234,
    },
  ],
  basis: "anclas de la nave, sin respaldo en un módulo metálico: texto del backend",
};

const met = (iso: string) => `MET ${iso.slice(11, 16)}`;

function render(anchors: LocationAnchors, operator: string | undefined, form = EMPTY_ANCHOR_FORM) {
  return renderToStaticMarkup(
    createElement(LocationAnchorsView, {
      anchors,
      modules: MODULES,
      met,
      operator,
      form,
      onForm: () => undefined,
      since: "2026-11-01T10:00:00+00:00",
      onDeclare: () => undefined,
      error: null,
    }),
  );
}

describe("anclas de módulo", () => {
  it("lista cada ancla con su módulo (dibujo y nombre del backend), desde cuándo y su asiento", () => {
    const html = render(ANCHORS, undefined);
    expect(html).toMatch(markedHtml(modulePictogram("laboratorio"), "Laboratorio (backend)"));
    const text = textLines(html).join(" ");
    expect(text).toContain("f7826da6-4fa2-4e98-8024-bc5b71e0893e:1:7");
    expect(text).toContain("MET 00:00");
    expect(text).toContain("asiento 1234");
    expect(text).toContain("anclas de la nave, sin respaldo en un módulo metálico: texto del backend");
  });

  it("en Tierra (sin operador) es de solo lectura: ni campos ni mando", () => {
    const html = render(ANCHORS, undefined);
    expect(html).not.toContain("<input");
    expect(html).not.toContain("<select");
    expect(html).not.toContain("Declarar ancla");
  });

  it("sin ninguna declarada: «aún no se ha registrado nada», sin el cian de dato ausente", () => {
    const html = render({ anchors: [], basis: "base" }, "CMO");
    expect(html).toMatch(markedHtml("ring-dotted", "Ninguna ancla declarada"));
    expect(html).not.toContain("c-cyan");
  });

  it("a bordo: identificador, los módulos de la lista declarada y el mando, inactivo hasta tenerlo todo", () => {
    const html = render(ANCHORS, "CMO");
    expect(html).toContain('aria-label="Identificador del ancla"');
    for (const item of MODULES.modules) expect(html).toContain(`<option value="${item.key}">${item.display}</option>`);
    expect(html).toMatch(/<button class="command" disabled="">[\s\S]*?Declarar ancla<\/button>/);
    expect(textLines(html).join(" ")).toContain("firma CMO");

    const ready = render(ANCHORS, "CMO", { anchorId: "ancla-1", module: "nodo" });
    expect(ready).not.toContain('disabled=""');
  });

  it("con una declaración en curso el mando se apaga: un doble clic no firma dos asientos", () => {
    const html = renderToStaticMarkup(
      createElement(LocationAnchorsView, {
        anchors: ANCHORS, modules: MODULES, met, operator: "CMO", form: { anchorId: "ancla-1", module: "nodo" },
        onForm: () => undefined, since: "2026-11-01T10:00:00+00:00", onDeclare: () => undefined, pending: true, error: null,
      }),
    );
    expect(html).toMatch(/<button class="command" disabled="">[\s\S]*?Declarar ancla<\/button>/);
  });

  it("se declara solo con identificador, módulo y quien firma", () => {
    expect(canDeclareAnchor({ anchorId: "a", module: "nodo" }, "CMO")).toBe(true);
    expect(canDeclareAnchor({ anchorId: "  ", module: "nodo" }, "CMO")).toBe(false);
    expect(canDeclareAnchor({ anchorId: "a", module: "" }, "CMO")).toBe(false);
    expect(canDeclareAnchor({ anchorId: "a", module: "nodo" }, " ")).toBe(false);
    expect(canDeclareAnchor({ anchorId: "a", module: "nodo" }, undefined)).toBe(false);
  });

  it("el cuerpo es el del contrato, recortado, con el instante de los datos", () => {
    expect(anchorBody({ anchorId: " ancla-1 ", module: "nodo" }, " CMO ", "2026-11-01T10:00:00+00:00")).toEqual({
      anchor_id: "ancla-1",
      module: "nodo",
      since: "2026-11-01T10:00:00+00:00",
      declared_by: "CMO",
    });
  });

  it("la interfaz no redacta la base: la pinta tal cual del backend", () => {
    const source = readFileSync(fileURLToPath(new URL("./LocationAnchors.tsx", import.meta.url)), "utf-8");
    expect(source).toContain("{anchors.basis}");
  });
});

describe("api de anclas", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubFetch(body: unknown) {
    const fetched = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetched);
    return fetched;
  }

  it("declarar un ancla es un POST con la cabecera de la consola y el cuerpo tal cual", async () => {
    const fetched = stubFetch({ ledger_index: 5 });
    const body = { anchor_id: "ancla-1", module: "nodo", since: "2026-11-01T10:00:00+00:00", declared_by: "CMO" };
    await expect(api.declareAnchor(body)).resolves.toEqual({ ledger_index: 5 });
    const [url, init] = fetched.mock.calls[0] ?? [];
    expect(url).toBe("/api/location/anchors");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get(CONSOLE_HEADER)).toBe(CONSOLE_HEADER_VALUE);
    expect(JSON.parse(String(init?.body))).toEqual(body);
  });

  it("leerlas es un GET sin cabecera de la consola", async () => {
    const fetched = stubFetch(ANCHORS);
    await expect(api.locationAnchors()).resolves.toEqual(ANCHORS);
    const [url, init] = fetched.mock.calls[0] ?? [];
    expect(url).toBe("/api/location/anchors");
    expect(new Headers(init?.headers).get(CONSOLE_HEADER)).toBeNull();
  });
});
