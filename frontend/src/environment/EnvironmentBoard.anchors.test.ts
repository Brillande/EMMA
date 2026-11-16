import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { type ReactElement, type ReactNode, createElement, isValidElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EnvHeader, type EnvironmentData } from "./EnvironmentBoard";

/**
 * Los bloques de la cabecera de «Entorno» (Aire, Temperatura, Luz, Ruido, Agua, Microbios) eran
 * cajas con borde que parecían botones y no hacían nada (lote «que si pulso el botón pasen
 * cosas», 2026-11-15). Ahora son botones que llevan a su panel de la pestaña, como las anclas de
 * «Radiación». Sin DOM en la suite: se despliega el árbol de elementos y se pulsa cada botón con
 * un `document` falso que apunta qué panel se pidió. La pestaña va por páginas de dos filas
 * (2026-11-16): el botón abre antes la página del panel (`showRowOf`, que sube con `closest`) y
 * desplaza en el siguiente fotograma, así que se simula `requestAnimationFrame` y se ejecuta al momento.
 */

type Props = Record<string, unknown> & { children?: ReactNode };
type Found = { label: string; click: () => void; type: unknown };

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
      found.push({ label: text(props.children), click: props.onClick as () => void, type: props.type });
    }
    walk(props.children);
  };
  walk(node);
  return found;
}

const env = {
  home: {
    reference: Date.parse("2026-11-08T12:00:00Z"),
    catalog: new Map(),
    status: { subject: "crew-01", mission: { profile: null, mission_day: 12 }, domains: {}, data: { reference_time: "2026-11-08T12:00:00Z" } },
  },
  habitat: { state: "ready", value: { latest: [], readings: [], active: [], excursions: [] } },
  parameters: { state: "ready", value: { parameters: [], display_only: [] } },
  systems: { state: "loading" },
  sleep: { state: "loading" },
  correlations: { state: "loading" },
} as unknown as EnvironmentData;

const TARGETS: Record<string, string> = {
  Aire: "env-air",
  Temperatura: "env-thermal",
  Luz: "env-light",
  Ruido: "env-noise",
  Agua: "env-water",
  Microbios: "env-microbiology",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("los bloques de la cabecera de «Entorno» llevan a su panel", () => {
  it("cada bloque es un botón (de teclado) que desplaza hasta su panel", () => {
    const scrolled: string[] = [];
    vi.stubGlobal("requestAnimationFrame", (run: () => void) => run());
    vi.stubGlobal("document", {
      querySelector: (selector: string) => ({
        // Fuera de una sección por filas: `showRowOf` no encuentra página que abrir y no cambia nada.
        closest: () => null,
        scrollIntoView: () => scrolled.push(selector),
      }),
    });
    const found = buttons(createElement(EnvHeader, { env }));
    // El nombre del botón empieza por el bloque; detrás va su estado («sin lectura» aquí).
    expect(found).toHaveLength(6);
    found.forEach((button, index) => expect(button.label.startsWith(Object.keys(TARGETS)[index] ?? "?")).toBe(true));
    for (const button of found) {
      expect(button.type).toBe("button");
      button.click();
    }
    expect(scrolled).toEqual(Object.values(TARGETS).map((target) => `[data-ui="${target}"]`));
  });

  it("los bloques se pintan como <button> dentro de su <li>", () => {
    const html = renderToStaticMarkup(createElement(EnvHeader, { env }));
    expect(html.match(/<li data-chip="[a-z]+"><button type="button"/g)).toHaveLength(6);
  });

  it("cada panel de destino existe en el tablero con ese `data-ui`", () => {
    const source = readFileSync(fileURLToPath(new URL("./EnvironmentBoard.tsx", import.meta.url)), "utf8");
    for (const target of Object.values(TARGETS)) expect(source).toMatch(new RegExp(`data-ui="${target}"`));
  });

  it("si el panel no está montado, pulsar no rompe nada", () => {
    vi.stubGlobal("requestAnimationFrame", (run: () => void) => run());
    vi.stubGlobal("document", { querySelector: () => null });
    for (const button of buttons(createElement(EnvHeader, { env }))) expect(() => button.click()).not.toThrow();
  });
});
