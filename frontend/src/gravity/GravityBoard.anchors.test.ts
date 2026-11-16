import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { type ReactElement, type ReactNode, createElement, isValidElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { HomeData } from "../dashboard/HomeBoard";
import { GRAVITY_KEYS, GravMusculo, GravTests, type GravityData } from "./GravityBoard";

/**
 * Los mandos de «Gravedad» que no hacían nada (lote «que si pulso el botón pasen cosas»,
 * 2026-11-15): «Ver pruebas / resultados» y «Plan de contramedidas» no salían porque abrían
 * pestañas apartadas de esta versión; ahora llevan a los paneles de la pestaña y salen siempre.
 * Y la casilla «Densidad ósea (DXA)» se apaga, diciendo por qué, cuando no hay densitometría que
 * marcar. Sin DOM en la suite: árbol de elementos y `document` falso para pulsar; el marcado
 * estático para la casilla. La pestaña va por páginas de dos filas (2026-11-16): el botón abre antes
 * la página del panel (`showRowOf`, que sube con `closest`) y desplaza en el siguiente fotograma, así
 * que se simula `requestAnimationFrame` y se ejecuta al momento.
 */

type Props = Record<string, unknown> & { children?: ReactNode };
type Found = { label: string; click: () => void };

const HOOK_OUTSIDE_RENDER = /reading 'use|Invalid hook call/;

function buttons(node: ReactNode): Found[] {
  const found: Found[] = [];
  const text = (child: ReactNode): string => {
    if (typeof child === "string" || typeof child === "number") return String(child);
    if (Array.isArray(child)) return child.map(text).join("");
    if (isValidElement(child)) return text((child.props as Props).children);
    return "";
  };
  const walk = (child: ReactNode): void => {
    if (Array.isArray(child)) {
      child.forEach(walk);
      return;
    }
    if (!isValidElement(child)) return;
    const element = child as ReactElement<Props>;
    const { props } = element;
    if (typeof element.type === "function") {
      let out: ReactNode;
      try {
        out = (element.type as (p: Props) => ReactNode)(props);
      } catch (error) {
        if (error instanceof Error && HOOK_OUTSIDE_RENDER.test(error.message)) return;
        throw error;
      }
      walk(out);
      return;
    }
    if (element.type === "button" && typeof props.onClick === "function") {
      found.push({ label: text(props.children), click: props.onClick as () => void });
    }
    walk(props.children);
  };
  walk(node);
  return found;
}

const REFERENCE = "2026-12-10T23:00:00+00:00";

function data(extra: Partial<Record<(typeof GRAVITY_KEYS)[number], { at: number; value: number }[]>> = {}): GravityData {
  const home = {
    status: {
      subject: "crew-01",
      domains: {},
      alerts: [],
      predictions: [],
      recommendations: [],
      data: { reference_time: REFERENCE },
      mission: { gravity_now: "microgravedad", phase: "stable", phase_display: "F", phase_basis: "B", phases: [], mission_day: 40, duration_days: 180 },
    },
    reference: Date.parse(REFERENCE),
    catalog: new Map(),
  } as unknown as HomeData;
  return {
    home,
    series: { state: "ready", value: { ...Object.fromEntries(GRAVITY_KEYS.map((key) => [key, []])), ...extra } as never },
    risks: { state: "ready", value: [] },
    links: undefined,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("«Ver pruebas» y «Plan de contramedidas» llevan a su panel de la pestaña", () => {
  it("salen siempre, sin accesos de la consola, y desplazan hasta las pruebas y los ejercicios", () => {
    const scrolled: string[] = [];
    vi.stubGlobal("requestAnimationFrame", (run: () => void) => run());
    vi.stubGlobal("document", {
      // Fuera de una sección por filas: `showRowOf` no encuentra página que abrir y no cambia nada.
      querySelector: (selector: string) => ({ closest: () => null, scrollIntoView: () => scrolled.push(selector) }),
    });
    const found = buttons(createElement(GravTests, { grav: data() }));
    expect(found.map((button) => button.label.trim())).toEqual(["Ver pruebas / resultados", "Plan de contramedidas"]);
    for (const button of found) button.click();
    expect(scrolled).toEqual(['[data-ui="grav-tests"]', '[data-ui="grav-exercises"]']);
  });

  it("los dos paneles de destino existen en el tablero", () => {
    const source = readFileSync(fileURLToPath(new URL("./GravityBoard.tsx", import.meta.url)), "utf8");
    expect(source).toContain('data-ui="grav-tests"');
    expect(source).toContain('data-ui="grav-exercises"');
  });
});

describe("la casilla «Densidad ósea (DXA)»", () => {
  const sites = (html: string) => {
    const label = /<label[^>]*>(?:(?!<\/label>).)*Densidad ósea \(DXA\)(?:(?!<\/label>).)*<\/label>/s.exec(html);
    expect(label).not.toBeNull();
    return label?.[0] ?? "";
  };

  it("sin densitometría de columna ni de cadera se apaga y dice por qué", () => {
    const html = renderToStaticMarkup(createElement(GravMusculo, { grav: data() }));
    const label = sites(html);
    expect(label).toMatch(/<input[^>]*disabled=""/);
    expect(label).not.toMatch(/checked=""/);
    expect(label).toMatch(/aria-describedby="[^"]+"/);
    expect(html).toContain("Sin densitometría de columna lumbar ni de cadera: no hay zonas que marcar.");
    // Las otras dos capas siguen activas.
    expect(html.match(/<input[^>]*disabled=""/g)).toHaveLength(1);
  });

  it("con una medida de columna lumbar queda activa y sin aviso", () => {
    const html = renderToStaticMarkup(
      createElement(GravMusculo, { grav: data({ "bmd-dxa-lumbar-spine": [{ at: Date.parse(REFERENCE) - 86_400_000, value: 1.1 }] }) }),
    );
    const label = sites(html);
    expect(label).not.toMatch(/disabled=""/);
    expect(label).toMatch(/checked=""/);
    expect(html).not.toContain("Sin densitometría de columna lumbar");
  });
});
