import { type ReactElement, type ReactNode, createElement, isValidElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { textNodes } from "../advisor/visibleText";
import type { CrewStatus, ProfileMatrix } from "../lib/api";
import type { HomeData, HomeLinks } from "../dashboard/HomeBoard";
import { RadCrew, RadRoute, type RadiationData, hazardLink } from "./RadiationBoard";

/**
 * Los mandos de «Radiación» que parecían botones y no hacían nada (lote «botones», 2026-11-15): las
 * letras RIDGE de «Tripulante» abren la pestaña de su peligro, y «Ruta: …» elige la ruta enseñada,
 * la misma de «Inicio». Con otra ruta que la declarada, la tabla no cambia y se dice con palabras.
 *
 * Sin DOM en la suite (como `HomeBoard.links.test.ts`): se despliega el árbol de elementos llamando a
 * cada componente; el que usa ganchos no se puede llamar fuera de React y se salta.
 */

const HOOK_OUTSIDE_RENDER = /reading 'use|Invalid hook call/;

type Props = Record<string, unknown> & { children?: ReactNode };

/** Los elementos nativos `type` del árbol, con sus props. */
function find(node: ReactNode, type: string): Props[] {
  const found: Props[] = [];
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
    if (element.type === type) found.push(props);
    walk(props.children);
  };
  walk(node);
  return found;
}

const REFERENCE = "2026-12-10T23:00:00+00:00";

const status = {
  subject: "crew-01",
  domains: { radiation: { level: "nominal" }, cardiovascular: { level: "watch" } },
  alerts: [],
  recommendations: [],
  provenance: { observation_type: { measured: 1 }, evidence_context: {} },
  data: { reference_time: REFERENCE },
  mission: {
    phase_display: "fase estable",
    mission_day: 40,
    duration_days: 180,
    phase: "stable",
    phases: [{ key: "stable", display: "fase estable" }],
    profile: { id: "mars-transit", display: "tránsito a Marte" },
  },
  radiation: {
    acute: { active_event: null, time_to_action: null },
    mission: null,
    career: { value_msv: null, basis: "b", limit_msv: 600, limit_source: "s" },
    projection: null,
  },
} as unknown as CrewStatus;

function cell(text: string) {
  return {
    key: "radiation_environment",
    label: "entorno de radiación",
    text,
    status: "documented",
    status_text: "",
    statement: text,
    citations: [],
    discrepancy: null,
    searched: null,
    emma_note: null,
    reused_from: [],
  };
}

const MATRIX = {
  declared_id: "mars-transit",
  profiles: [
    { id: "leo", display: "órbita baja terrestre", declared: false, cells: [cell("Frase de órbita baja (backend).")] },
    { id: "mars-transit", display: "tránsito a Marte", declared: true, cells: [cell("Frase de Marte (backend).")] },
  ],
} as unknown as ProfileMatrix;

const GROUPS = ["radiation", "isolation", "distance", "gravity", "environment"].map((hazard) => ({
  hazard,
  display: hazard,
  domains: [] as string[],
}));

function data(shownRoute: string | null, setRoute: (id: string) => void = () => {}): RadiationData {
  const home = {
    status,
    reference: Date.parse(REFERENCE),
    groups: GROUPS,
    matrix: MATRIX,
    matrixFailure: null,
    shownRoute,
    setRoute,
    // El estado por regiones, aún sin llegar: la silueta enseña «Cargando…» y ningún botón.
    anatomy: { state: null, error: null, stale: false },
    region: null,
    setRegion: () => {},
  } as unknown as HomeData;
  return {
    home,
    weather: { state: "loading" },
    crew: { state: "loading" },
    history: { state: "loading" },
    risk: { state: "loading" },
    doseRate: { state: "ready", value: [] },
    imm: { state: "loading" },
    latest: { state: "loading" },
  };
}

function links(visible: readonly string[]) {
  const openSection = vi.fn<(key: string) => void>();
  const value: HomeLinks = {
    openSection,
    sectionName: (key) => (visible.includes(key) ? `«${key}»` : null),
  };
  return { openSection, value };
}

const ALL = ["radiation", "isolation", "nodes", "gravity", "environment", "hazards"];

describe("Radiación: letras RIDGE", () => {
  it("cada letra abre la pestaña de su peligro; la distancia, «Nodos»", () => {
    const { openSection, value } = links(ALL);
    const buttons = find(createElement(RadCrew, { rad: data("mars-transit"), links: value }), "button");
    expect(buttons).toHaveLength(5);
    buttons.forEach((props) => (props.onClick as () => void)());
    expect(openSection.mock.calls.map(([key]) => key)).toEqual(["radiation", "isolation", "nodes", "gravity", "environment"]);
    expect(buttons[2]?.["aria-label"]).toBe("Abrir «nodes»: Distance");
  });

  it("si la pestaña no está a la vista, cae a «Peligros»; sin consola, no hay botones", () => {
    const { openSection, value } = links(["radiation", "hazards"]);
    hazardLink(value, "gravity")?.open();
    hazardLink(value, "radiation")?.open();
    expect(openSection.mock.calls.map(([key]) => key)).toEqual(["hazards", "radiation"]);
    expect(find(createElement(RadCrew, { rad: data("mars-transit") }), "button")).toHaveLength(0);
  });
});

describe("Radiación: elegir la ruta", () => {
  it("el desplegable lleva los perfiles de la matriz y elegir uno cambia la ruta compartida", () => {
    const setRoute = vi.fn<(id: string) => void>();
    const [select] = find(createElement(RadRoute, { rad: data("mars-transit", setRoute) }), "select");
    expect(select?.value).toBe("mars-transit");
    (select?.onChange as (event: { target: { value: string } }) => void)({ target: { value: "leo" } });
    expect(setRoute).toHaveBeenCalledWith("leo");
    const html = renderToStaticMarkup(createElement(RadRoute, { rad: data("mars-transit") }));
    expect(html).toContain("Tránsito a Marte (declarado)");
    expect(html).toContain("Órbita baja");
  });

  it("con la ruta declarada no hay nota; con otra, se dice que la dosis es la del perfil declarado", () => {
    const declared = textNodes(renderToStaticMarkup(createElement(RadRoute, { rad: data("mars-transit") }))).join(" ");
    expect(declared).not.toContain("EMMA no proyecta dosis");
    expect(declared).toContain("Frase de Marte (backend).");

    const other = textNodes(renderToStaticMarkup(createElement(RadRoute, { rad: data("leo") }))).join(" ");
    expect(other).toContain("La dosis de la tabla es la del perfil declarado (Tránsito a Marte); EMMA no proyecta dosis para Órbita baja.");
    // De la ruta elegida, solo lo que la matriz ya trae de ella.
    expect(other).toContain("Frase de órbita baja (backend).");
    expect(other).not.toContain("Frase de Marte (backend).");
  });
});
