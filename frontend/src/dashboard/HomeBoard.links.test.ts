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
import { tabForHazard } from "./HazardCards";

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
    { hazard: "isolation", display: "aislamiento", domains: [] },
    { hazard: "distance", display: "distancia", domains: [] },
    { hazard: "gravity", display: "campos de gravedad", domains: ["cardiovascular"] },
    { hazard: "environment", display: "entorno hostil", domains: [] },
    // Un peligro que la interfaz no conoce no tiene pestaña propia: va a «Peligros y alertas».
    { hazard: "unknown", display: "otro peligro", domains: [] },
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

// Las secciones a la vista en esta versión: «Rutinas y notas», «Cuerpo», «Misión y hábitat»,
// «Calidad y sensores» y «Diario y pruebas» están apartadas (`setAside`, 2026-11-15) y
// `visibleSections` no las da, así que su nombre es `null` como en la consola.
const NAMES: Record<string, string> = {
  hazards: "Peligros y alertas",
  radiation: "Radiación",
  isolation: "Aislamiento",
  nodes: "Distancia y nodos",
  gravity: "Gravedad",
  environment: "Entorno",
};
const ESSENTIAL = new Set(["home", "hazards"]);

function links(
  essential = false,
  hidden: ReadonlySet<string> = new Set(),
  names: Record<string, string> = NAMES,
): { links: HomeLinks; opened: string[] } {
  const opened: string[] = [];
  return {
    opened,
    links: {
      openSection: vi.fn((key: string) => opened.push(key)),
      sectionName: (key) =>
        (essential && !ESSENTIAL.has(key)) || hidden.has(key) ? null : (names[key] ?? null),
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
  it("cada tarjeta o fila abre una sección a la vista, y su rótulo dice adónde", () => {
    // Con las secciones de antes apartadas, cada acceso lleva a una visible (2026-11-15): el estado
    // de la misión a «Peligros y alertas»; los vitales y los indicadores a «Gravedad»; los datos
    // brutos a «Distancia y nodos». El seguimiento y el «+» de la bitácora escriben en su sitio
    // (`HomeBoard.write.test.ts`): sus piezas tienen estado y este recorrido las salta.
    const opened = clickAll();
    expect(Object.fromEntries(opened)).toEqual({
      "Abrir Peligros y alertas: estado de la misión": "hazards",
      "Abrir Radiación: Radiación": "radiation",
      "Abrir Aislamiento: Aislamiento": "isolation",
      "Abrir Distancia y nodos: Distancia": "nodes",
      "Abrir Gravedad: Campos de gravedad": "gravity",
      "Abrir Entorno: Entorno hostil": "environment",
      "Abrir Peligros y alertas: Otro peligro": "hazards",
      "Abrir Gravedad: signos vitales": "gravity",
      "Abrir Gravedad: tendencia de 24 horas": "gravity",
      "Abrir Peligros y alertas: estado de riesgo": "hazards",
      "Abrir Peligros y alertas: Revisar el blindaje del refugio": "hazards",
      "Ver indicadores en detalle": "gravity",
      "Datos brutos / fuente": "nodes",
    });
  });

  it("cada peligro abre su pestaña desde las barras globales, las letras y el acceso rápido", () => {
    for (const [piece, render] of [
      ["barras globales", HomeGlobal],
      ["letras", HomeCrewColumn],
      ["acceso rápido", HomeQuickHazards],
    ] as const) {
      const { links: given, opened } = links();
      const clicked = new Map<string, string>();
      for (const button of buttons(render({ home, links: given }))) {
        button.click();
        clicked.set(button.label, opened[opened.length - 1] ?? "");
      }
      expect(clicked.get("Abrir Radiación: Radiación"), piece).toBe("radiation");
      expect(clicked.get("Abrir Aislamiento: Aislamiento"), piece).toBe("isolation");
      expect(clicked.get("Abrir Distancia y nodos: Distancia"), piece).toBe("nodes");
      expect(clicked.get("Abrir Gravedad: Campos de gravedad"), piece).toBe("gravity");
      expect(clicked.get("Abrir Entorno: Entorno hostil"), piece).toBe("environment");
      expect(clicked.get("Abrir Peligros y alertas: Otro peligro"), piece).toBe("hazards");
    }
  });

  it("si la pestaña del peligro no está a la vista, el peligro abre «Peligros y alertas»", () => {
    const { links: given, opened } = links(false, new Set(["gravity", "nodes"]));
    const clicked = new Map<string, string>();
    for (const button of buttons(pieces(given))) {
      button.click();
      clicked.set(button.label, opened[opened.length - 1] ?? "");
    }
    expect(clicked.get("Abrir Peligros y alertas: Campos de gravedad")).toBe("hazards");
    expect(clicked.get("Abrir Peligros y alertas: Distancia")).toBe("hazards");
    expect(clicked.get("Abrir Radiación: Radiación")).toBe("radiation");
    expect(clicked.has("Abrir Gravedad: Campos de gravedad")).toBe(false);
  });

  it("`tabForHazard` da la pestaña de cada peligro RIDGE y nada a uno desconocido", () => {
    expect(["radiation", "isolation", "distance", "gravity", "environment"].map(tabForHazard)).toEqual([
      "radiation",
      "isolation",
      "nodes",
      "gravity",
      "environment",
    ]);
    expect(tabForHazard("unknown")).toBeNull();
    expect(tabForHazard("toString")).toBeNull();
  });

  it("si una sección apartada vuelve, su acceso vuelve a ella", () => {
    const { links: given, opened } = links(false, new Set(), { ...NAMES, body: "Cuerpo", mission: "Misión y hábitat", data: "Calidad y sensores" });
    const found = new Map(buttons(pieces(given)).map((button) => [button.label, button.click]));
    found.get("Abrir Cuerpo: signos vitales")?.();
    found.get("Abrir Misión y hábitat: estado de la misión")?.();
    found.get("Datos brutos / fuente")?.();
    expect(opened).toEqual(["body", "mission", "data"]);
  });

  it("con el teclado, cada peligro se abre una vez: desde el acceso rápido", () => {
    const { links: given } = links();
    const tabbable = buttons(pieces(given))
      .filter((button) => button.tabbable)
      .map((button) => button.label);
    expect(tabbable.filter((label) => label === "Abrir Radiación: Radiación")).toHaveLength(1);
    const quick = buttons(HomeQuickHazards({ home, links: given })).find((button) => button.label.endsWith("Radiación"));
    expect(quick?.tabbable).toBe(true);
  });

  it("sin los accesos de la consola no hay ningún botón", () => {
    expect(buttons(pieces(undefined))).toEqual([]);
    expect(buttons(pieces({ openSection: () => undefined }))).toEqual([]);
  });

  it("en modo esencial solo quedan los que llevan a una sección esencial", () => {
    // Los vitales y los datos brutos no tienen sección esencial que los enseñe: no se ofrecen, en
    // vez de llevar a «Peligros y alertas» con un rótulo que promete otra cosa.
    const opened = clickAll(true);
    expect(new Set(opened.values())).toEqual(new Set(["hazards"]));
    expect(opened.get("Abrir Peligros y alertas: estado de la misión")).toBe("hazards");
    expect([...opened.keys()]).not.toContain("Ver indicadores en detalle");
    expect([...opened.keys()]).not.toContain("Datos brutos / fuente");
    expect([...opened.keys()].some((label) => label.endsWith("signos vitales"))).toBe(false);
  });

  it("`sectionLink` necesita las dos cosas: cómo abrir y el nombre de la sección", () => {
    expect(sectionLink(undefined, "body")).toBeNull();
    expect(sectionLink({ sectionName: () => "Cuerpo" }, "body")).toBeNull();
    expect(sectionLink({ openSection: () => undefined, sectionName: () => null }, "body")).toBeNull();
    expect(sectionLink({ openSection: () => undefined, sectionName: () => "Cuerpo" }, "body")?.name).toBe("Cuerpo");
  });

  it("`sectionLink` toma la primera de la lista que esté a la vista", () => {
    const opened: string[] = [];
    const given: HomeLinks = {
      openSection: (key) => opened.push(key),
      sectionName: (key) => (key === "hazards" ? "Peligros y alertas" : null),
    };
    const link = sectionLink(given, "body", "gravity", "hazards");
    expect(link?.name).toBe("Peligros y alertas");
    link?.open();
    expect(opened).toEqual(["hazards"]);
    expect(sectionLink(given, "body", "gravity")).toBeNull();
  });
});
