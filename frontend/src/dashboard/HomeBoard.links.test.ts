import { type ReactElement, type ReactNode, isValidElement } from "react";
import { describe, expect, it, vi } from "vitest";

import type { CrewStatus } from "../lib/api";
import {
  type HomeData,
  HomeCrewColumn,
  HomeGlobal,
  type HomeLinks,
  HomeQuickHazards,
  HomeRiskColumn,
  sectionLink,
} from "./HomeBoard";

/**
 * Los accesos de «Inicio» (lote de arreglos, 2026-11-09: «Inicio no enlaza con accesos directos a
 * las partes del programa»). Cada tarjeta o fila con acceso abre su sección por la clave; sin los
 * accesos de la consola no hay botones; y en modo esencial, lo que lleva a una sección fuera de la
 * vista no se enseña (antes devolvía a «Inicio» sin decir nada).
 *
 * Sin DOM en la suite: se despliega el árbol de elementos llamando a cada componente sin estado; el
 * que usa ganchos no se puede llamar fuera de React y se salta (ninguno de ellos lleva accesos).
 * Solo se salta ese fallo: cualquier otro error de una pieza hace fallar la prueba, para que un
 * subárbol roto no se lleve sus botones en silencio.
 */

/** El fallo de llamar a un gancho fuera de un render de React (sin despachador). */
const HOOK_OUTSIDE_RENDER = /reading 'use|Invalid hook call/;

type Props = Record<string, unknown> & { children?: ReactNode };

type Found = { label: string; click: () => void; tabbable: boolean };

/** Los `<button>` con `onClick` del árbol, con su nombre accesible (o su texto). */
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
      const label = typeof props["aria-label"] === "string" ? props["aria-label"] : text(props.children);
      found.push({ label, click: props.onClick as () => void, tabbable: props.tabIndex !== -1 });
    }
    walk(props.children);
  };
  walk(node);
  return found;
}

const status = {
  subject: "CM-1",
  summary: "Resumen del backend.",
  overall_level: "watch",
  comms: null,
  domains: { radiation: { level: "nominal" }, cardiovascular: { level: "watch" } },
  followups: [
    {
      adoption_index: 3,
      countermeasure: { id: "cm-a", action: "Ejercicio de resistencia" },
      domain: "cardiovascular",
      window_ends: "2026-11-12",
      state: "in_window",
    },
  ],
  recommendations: [{ domain: "radiation", action: "Revisar el blindaje del refugio" }],
  predictions: [],
  data: { reference_time: "2026-11-09T00:00:00Z" },
  mission: { start: "2026-11-01T00:00:00Z", phase_display: "en vuelo", profile: null },
} as unknown as CrewStatus;

const home = {
  status,
  reference: Date.parse("2026-11-09T00:00:00Z"),
  ridge: { state: "ready", value: {} },
  groups: [
    { hazard: "radiation", display: "radiación", domains: ["radiation"] },
    { hazard: "gravity", display: "campos de gravedad", domains: ["cardiovascular"] },
  ],
  indicators: { state: "ready", value: [] },
  catalog: new Map(),
  seriesOf: () => ({ state: "ready", value: [] }),
  readingsFor: () => [],
  diary: { state: "ready", value: [] },
  matrix: null,
  matrixFailure: null,
  shownRoute: null,
  setRoute: () => undefined,
  declaredShort: null,
  anatomy: { state: null, error: null, stale: false },
  region: null,
  setRegion: () => undefined,
  lowest: "nominal",
  atLowest: 1,
  domainCount: 2,
  overall: "watch",
  overallStyle: null,
  elapsed: 0,
} as unknown as HomeData;

const NAMES: Record<string, string> = {
  hazards: "Peligros y alertas",
  routines: "Rutinas y notas",
  body: "Cuerpo",
  mission: "Misión y hábitat",
  data: "Calidad y sensores",
  log: "Diario y pruebas",
};
const ESSENTIAL = new Set(["home", "hazards"]);

function links(essential = false): { links: HomeLinks; opened: string[] } {
  const opened: string[] = [];
  return {
    opened,
    links: {
      openSection: vi.fn((key: string) => opened.push(key)),
      sectionName: (key) => (essential && !ESSENTIAL.has(key) ? null : (NAMES[key] ?? null)),
    },
  };
}

const pieces = (with_: HomeLinks | undefined) => [
  HomeGlobal({ home, links: with_ }),
  HomeCrewColumn({ home, links: with_ }),
  HomeRiskColumn({ home, links: with_ }),
  HomeQuickHazards({ home, links: with_ }),
];

/** Pulsa cada acceso y devuelve «rótulo → sección abierta». */
function clickAll(essential = false): Map<string, string> {
  const { links: given, opened } = links(essential);
  const result = new Map<string, string>();
  for (const button of buttons(pieces(given))) {
    const before = opened.length;
    button.click();
    expect(opened.length, button.label).toBe(before + 1);
    result.set(button.label, opened[opened.length - 1] ?? "");
  }
  return result;
}

describe("accesos de «Inicio»", () => {
  it("cada tarjeta o fila abre su sección por la clave, y su rótulo dice adónde", () => {
    const opened = clickAll();
    expect(Object.fromEntries(opened)).toEqual({
      "Abrir Misión y hábitat: estado de la misión": "mission",
      "Abrir Peligros y alertas: Radiación": "hazards",
      "Abrir Peligros y alertas: Campos de gravedad": "hazards",
      "Abrir Cuerpo: signos vitales": "body",
      "Abrir Cuerpo: tendencia de 24 horas": "body",
      "Abrir Peligros y alertas: estado de riesgo": "hazards",
      "Abrir Rutinas y notas: Ejercicio de resistencia": "routines",
      "Abrir Peligros y alertas: Revisar el blindaje del refugio": "hazards",
      "Escribir en el diario": "log",
      "Ver indicadores en detalle": "body",
      "Datos brutos / fuente": "data",
    });
  });

  it("los peligros se abren desde las barras globales, las letras y el acceso rápido", () => {
    const { links: given } = links();
    const count = (piece: ReactNode) =>
      buttons(piece).filter((button) => button.label === "Abrir Peligros y alertas: Radiación").length;
    expect(count(HomeGlobal({ home, links: given }))).toBe(1);
    expect(count(HomeCrewColumn({ home, links: given }))).toBe(1);
    expect(count(HomeQuickHazards({ home, links: given }))).toBe(1);
  });

  it("con el teclado, cada peligro se abre una vez: desde el acceso rápido", () => {
    const { links: given } = links();
    const tabbable = buttons(pieces(given))
      .filter((button) => button.tabbable)
      .map((button) => button.label);
    expect(tabbable.filter((label) => label === "Abrir Peligros y alertas: Radiación")).toHaveLength(1);
    const quick = buttons(HomeQuickHazards({ home, links: given })).find((button) => button.label.endsWith("Radiación"));
    expect(quick?.tabbable).toBe(true);
  });

  it("sin los accesos de la consola no hay ningún botón", () => {
    expect(buttons(pieces(undefined))).toEqual([]);
    expect(buttons(pieces({ openSection: () => undefined }))).toEqual([]);
  });

  it("en modo esencial solo quedan los que llevan a una sección esencial", () => {
    const opened = clickAll(true);
    expect(new Set(opened.values())).toEqual(new Set(["hazards"]));
    expect([...opened.keys()]).not.toContain("Ver indicadores en detalle");
    expect([...opened.keys()]).not.toContain("Escribir en el diario");
  });

  it("`sectionLink` necesita las dos cosas: cómo abrir y el nombre de la sección", () => {
    expect(sectionLink(undefined, "body")).toBeNull();
    expect(sectionLink({ sectionName: () => "Cuerpo" }, "body")).toBeNull();
    expect(sectionLink({ openSection: () => undefined, sectionName: () => null }, "body")).toBeNull();
    expect(sectionLink({ openSection: () => undefined, sectionName: () => "Cuerpo" }, "body")?.name).toBe("Cuerpo");
  });
});
