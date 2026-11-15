import { type ReactElement, type ReactNode, createElement, isValidElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { type CrewStatus, type ProfileMatrix, api } from "../lib/api";
import { type HomeData, type HomeLinks, HomePlaces, MODULE_DECLARE_HOURS, type ModuleDeclare, declareModule } from "./HomeBoard";
import type { DeclareEvent } from "./MissionTimeline";

/**
 * La «Ubicación de la tripulación» y la «Sububicación» que encabezan cada pestaña (lote «botones»,
 * 2026-11-15: «que si pulso el botón pasen cosas»). Elegir un perfil fuera de «Inicio» y «Distancia y
 * nodos» solo cambiaba el anillo; ahora la tarjeta dice el aspecto de esa pestaña en el perfil
 * elegido (frase del backend) y lleva a «Distancia y nodos». La sububicación era un `<p>` con aire de
 * desplegable; ahora es un `<select>` que declara el módulo en el ledger (`POST /mission/events`).
 *
 * Sin DOM en la suite: el clic se hace llamando al `onClick` del botón del árbol de elementos (como
 * `HomeBoard.links.test.ts`), y lo visible se lee pintando a HTML estático.
 */

type Props = Record<string, unknown> & { children?: ReactNode };
type Found = { label: string; click: () => void };

/** Los `<button>` con `onClick` del árbol; las piezas con ganchos se saltan (el desplegable). */
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
      try {
        walk((element.type as (p: Props) => ReactNode)(props));
      } catch (error) {
        if (!(error instanceof Error && /reading 'use|Invalid hook call/.test(error.message))) throw error;
      }
      return;
    }
    if (element.type === "button" && typeof props.onClick === "function") {
      const label = typeof props["aria-label"] === "string" ? props["aria-label"] : text(props.children);
      found.push({ label, click: props.onClick as () => void });
    }
    walk(props.children);
  };
  walk(node);
  return found;
}

const cell = (key: string, label: string, text: string, status: "read" | "unverified" = "read") => ({
  key,
  label,
  status,
  status_text: status === "read" ? "leído" : "SIN-VERIFICAR (backend)",
  statement: null,
  citations: [],
  discrepancy: null,
  searched: null,
  emma_note: null,
  reused_from: [],
  text,
});

const matrix = {
  note: "",
  declared_id: "leo",
  declared_note: "",
  declared_text: null,
  no_source: "EMMA NO TIENE FUENTE (backend)",
  aspects: [
    { key: "gravity_regime", label: "régimen de gravedad", reused_only: false },
    { key: "comm_delay", label: "retardo de comunicaciones", reused_only: false },
  ],
  profiles: [
    { id: "leo", display: "órbita baja terrestre", declared: true, cells: [cell("gravity_regime", "régimen de gravedad", "MICROGRAVEDAD-LEO")] },
    { id: "mars-surface", display: "superficie de Marte", declared: false, cells: [cell("gravity_regime", "régimen de gravedad", "TRES-OCTAVOS-MARTE", "unverified")] },
  ],
  reused_note: "",
  medical_note: "",
  pages_read: [],
} as unknown as ProfileMatrix;

const status = {
  subject: "CM-1",
  data: { reference_time: "2026-11-09T06:00:00Z" },
  mission: {
    start: "2026-11-01",
    location: null,
    location_state: "missing",
    location_missing_text: "SIN UBICACIÓN (backend)",
    location_basis: "",
  },
} as unknown as CrewStatus;

function homeWith(shownRoute: string | null, setRoute: (id: string) => void = () => undefined): HomeData {
  return { status, matrix, matrixFailure: null, shownRoute, setRoute, declaredShort: null } as unknown as HomeData;
}

const links: HomeLinks & { opened: string[] } = {
  opened: [],
  openSection(key) {
    links.opened.push(key);
  },
  sectionName: (key) => (key === "nodes" ? "Distancia y nodos" : null),
};

const text = (node: ReactElement) => textNodes(renderToStaticMarkup(node)).join(" ");
const places = (home: HomeData, aspect?: string, declare?: ModuleDeclare) =>
  createElement(HomePlaces, { home, links, aspect, declare });

describe("Ubicación: elegir un perfil se ve en las pestañas que no lo leen", () => {
  it("pulsar un planeta en «Gravedad» cambia lo que dice la tarjeta", () => {
    let route: string | null = "leo";
    const setRoute = (id: string) => {
      route = id;
    };
    const before = text(places(homeWith(route, setRoute), "gravity_regime"));
    expect(before).toContain("MICROGRAVEDAD-LEO");
    expect(before).not.toContain("TRES-OCTAVOS-MARTE");

    const mars = buttons(HomePlaces({ home: homeWith(route, setRoute), links, aspect: "gravity_regime" })).find(
      (button) => button.label === "Superficie de Marte",
    );
    expect(mars).toBeDefined();
    mars?.click();
    expect(route).toBe("mars-surface");

    const after = text(places(homeWith(route, setRoute), "gravity_regime"));
    expect(after).toContain("TRES-OCTAVOS-MARTE");
    expect(after).not.toContain("MICROGRAVEDAD-LEO");
    // Sin verificar, con la palabra del backend: no se lee como zanjado.
    expect(after).toContain("SIN-VERIFICAR (backend)");
    expect(renderToStaticMarkup(places(homeWith(route), "gravity_regime"))).toContain('aria-pressed="true"');
  });

  it("un aspecto sin casilla dice la frase del backend para lo que no tiene fuente; sin cifra propia", () => {
    expect(text(places(homeWith("mars-surface"), "comm_delay"))).toContain("EMMA NO TIENE FUENTE (backend)");
  });

  it("«Ver rutas» abre «Distancia y nodos»", () => {
    links.opened.length = 0;
    const more = buttons(HomePlaces({ home: homeWith("leo"), links, aspect: "gravity_regime" })).find((button) =>
      button.label.startsWith("Abrir Distancia y nodos"),
    );
    expect(more).toBeDefined();
    more?.click();
    expect(links.opened).toEqual(["nodes"]);
  });

  it("sin aspecto (Inicio con las rutas abiertas, Distancia y nodos) no se añade nada", () => {
    const html = renderToStaticMarkup(places(homeWith("leo")));
    expect(html).not.toContain("ref-place-aspect");
  });
});

describe("Sububicación: un desplegable de verdad que declara el módulo", () => {
  afterEach(() => vi.unstubAllGlobals());

  const declare = (onDeclare: DeclareEvent, operator = "CM-2"): ModuleDeclare => ({
    onDeclare,
    operator,
    setOperator: () => undefined,
    privacy: false,
  });

  it("es un `<select>` con su rótulo, no un párrafo con aire de desplegable", () => {
    const html = renderToStaticMarkup(places(homeWith("leo"), undefined, declare(async () => undefined)));
    expect(html).toMatch(/<select[^>]*class="ref-select-like"[^>]*aria-label="Declarar el módulo del tripulante"/);
    expect(html).not.toMatch(/<p[^>]*class="ref-select-like"/);
    // Fuera de la consola (sin declaración) el módulo se lee y no se ofrece mando.
    expect(renderToStaticMarkup(places(homeWith("leo")))).not.toContain("<select");
  });

  it("declara una ubicación firmada de este tripulante desde el instante de referencia (POST /mission/events)", async () => {
    const fetched = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => new Response(JSON.stringify({ ledger_index: 9 }), { status: 201, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetched);
    // La misma declaración que la consola (`useConsoleData`): el módulo va en `where`.
    const viaApi: DeclareEvent = async (kind, start, end, label, by, where) => {
      await api.declareMissionEvent({
        subject: status.subject,
        kind,
        start,
        end,
        declared_by: by,
        ...(label === "" ? {} : { label }),
        ...where,
      });
    };
    // Con los datos al día (ahora = referencia), la ventana va de la referencia a dos horas después.
    await declareModule(declare(viaApi, "  CM-2 "), status, "laboratorio", 2, Date.parse("2026-11-09T06:00:00Z"));
    const [url, init] = fetched.mock.calls[0] ?? [];
    expect(url).toBe("/api/mission/events");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      subject: "CM-1",
      kind: "location",
      start: "2026-11-09T06:00:00.000Z",
      end: "2026-11-09T08:00:00.000Z",
      declared_by: "CM-2",
      module: "laboratorio",
    });
  });

  it("con los datos atrasados, las horas cuentan desde ahora: la ventana no nace cerrada", async () => {
    const onDeclare = vi.fn<DeclareEvent>(async () => undefined);
    await declareModule(declare(onDeclare), status, "laboratorio", 1, Date.parse("2026-11-09T09:30:00Z"));
    const [, start, end] = onDeclare.mock.calls[0] ?? [];
    expect(start).toBe("2026-11-09T06:00:00.000Z");
    expect(end).toBe("2026-11-09T10:30:00.000Z");
  });

  it("sin módulo, sin firma o sin horas no se declara nada", () => {
    const onDeclare = vi.fn<DeclareEvent>(async () => undefined);
    expect(declareModule(declare(onDeclare), status, "", 2)).toBeNull();
    expect(declareModule(declare(onDeclare, "  "), status, "laboratorio", 2)).toBeNull();
    expect(declareModule(declare(onDeclare), status, "laboratorio", Number(""))).toBeNull();
    expect(onDeclare).not.toHaveBeenCalled();
    expect(MODULE_DECLARE_HOURS.length).toBeGreaterThan(0);
  });
});
