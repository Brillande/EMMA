import { createElement } from "react";
import { describe, expect, it } from "vitest";

import { renderToStaticMarkup } from "../assistant/staticMarkup";
import { RegionChain } from "../anatomy/RegionChain";
import type { AnatomyView } from "../anatomy/useAnatomyState";
import { zoneOf } from "../icons/Silhouette";
import type { AnatomyRegionState, AnatomyState, CrewStatus } from "../lib/api";
import { adoptLevelLabels } from "../lib/levels";
import { RegionFigure, RegionPopover, closesPopover, followingOf, popoverSide } from "./RegionPopover";

/**
 * La ficha de una región junto a la silueta de «Inicio» y «Radiación» (2026-11-15). Sin navegador en
 * la suite (no hay jsdom ni Testing Library): la ficha se pinta a HTML estático con la región ya
 * elegida, y las decisiones del clic, de Esc, de pulsar fuera y del lado se prueban en sus funciones.
 */

adoptLevelLabels({ nominal: "Nominal", watch: "Vigilancia", concern: "Precaución", critical: "Crítico" });

// Frases como las del backend: la interfaz las enseña tal cual, sin redactar nada.
const NOTE = "Pulso, variabilidad, presión y ortostatismo.";
const DRIVER = "Frecuencia cardiaca 35 /min por debajo del límite de peligro.";
const NO_DATA = "Sin lecturas ni hallazgos en esta región.";
const ACTION = "Repetir la medida en reposo dentro de 24 h.";

const RISK = {
  ridge: { category: "gravity", display: "Campos de gravedad alterados", source: { title: "NASA HRP" } },
  hrp_risk: null,
  uncertainty_statement: "Incertidumbre declarada por el backend.",
};

const base = {
  note_refs: [],
  function: null,
  function_note: null,
  function_refs: [],
  level_of: null,
  level_note: null,
  variables: [],
  unmeasured: [],
  evidence: [],
  analytes_source: null,
  research: null,
  recommendations: [],
  recommendations_note: null,
  level_risk: null,
  context: null,
};

const heart = {
  ...base,
  key: "heart",
  display: "Corazón y circulación",
  domains: ["cardiovascular"],
  note: NOTE,
  level: "concern",
  has_data: true,
  data_note: null,
  state: [{ domain: "cardiovascular", level: "concern", has_data: true, drivers: [DRIVER], risk: RISK }],
  recommendations: [
    {
      domain: "cardiovascular",
      action: ACTION,
      rationale: "Motivo redactado por el backend.",
      urgency: "soon",
      notify_ground: false,
      evidence: [],
      countermeasure: {
        id: "cv-repeat-rest",
        scope: "crew",
        domain: "cardiovascular",
        ridge: "gravity",
        ridge_display: "Campos de gravedad",
        action: ACTION,
        indication: "Hallazgo cardiovascular",
        resources: ["Wearable"],
        crew_time_minutes: null,
        crew_time_basis: "sin fuente",
        protocol_ref: null,
        followup_checks: ["heart-rate"],
        followup_checks_display: ["Frecuencia cardiaca"],
        followup_window_hours: 24,
        followup_basis: "ventana de demo",
        contraindications_note: null,
        adverse_effects_note: null,
        basis: "demo",
      },
    },
  ],
} as unknown as AnatomyRegionState;

const immune = {
  ...base,
  key: "immune",
  display: "Sistema inmune (todo el cuerpo)",
  domains: ["immune"],
  note: "No es un órgano.",
  level: null,
  has_data: false,
  data_note: NO_DATA,
  state: [],
} as unknown as AnatomyRegionState;

const status = {
  subject: "crew-01",
  mission: { start: "2026-11-01" },
  data: { reference_time: "2026-12-11T00:00:00+00:00", trend_window_days: 21 },
  inferred: [],
  followups: [
    { state: "open", countermeasure: { id: "cm-open" } },
    { state: "closed", countermeasure: { id: "cm-closed" } },
  ],
} as unknown as CrewStatus;

const view: AnatomyView = {
  state: { subject: "crew-01", regions: [heart, immune] } as unknown as AnatomyState,
  error: null,
  stale: false,
};

const render = (region: string | null, shown: AnatomyView = view) =>
  renderToStaticMarkup(createElement(RegionPopover, { view: shown, region, status, onClose: () => undefined }));

describe("la ficha de la región elegida", () => {
  it("sin región elegida no se pinta nada", () => {
    expect(render(null)).toBe("");
  });

  it("con la región elegida, una ficha con nombre y la cadena del backend", () => {
    const html = render("heart");
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-label="Corazón y circulación"');
    expect(html).toContain('tabindex="-1"');
    // Las frases del backend, tal cual.
    expect(html).toContain(NOTE);
    expect(html).toContain(DRIVER);
    // Y su mando de cerrar, con palabra.
    expect(html).toMatch(/<button[^>]*type="button"[^>]*>.*Cerrar<\/button>/);
  });

  it("de solo lectura: enseña la contramedida pero no ofrece adoptarla", () => {
    const html = render("heart");
    expect(html).toContain(ACTION);
    expect(html).not.toContain("Adoptar y seguir");
    // La misma cadena con el mando de adoptar sí lo enseña: la prueba de arriba puede fallar.
    const adoptable = renderToStaticMarkup(
      createElement(RegionChain, { region: heart, status, operator: "", following: new Set<string>(), onAdopt: async () => {} }),
    );
    expect(adoptable).toContain("Adoptar y seguir");
  });

  it("si el estado por regiones es anterior al de la consola, se dice", () => {
    expect(render("heart", { ...view, stale: true })).toContain("anterior al que muestra la consola");
    expect(render("heart")).not.toContain("anterior al que muestra la consola");
  });

  it("si el estado por regiones es de otro tripulante, no se abre", () => {
    const other = { state: { subject: "crew-02", regions: [heart, immune] } as unknown as AnatomyState, error: null, stale: true };
    expect(render("heart", other)).toBe("");
  });

  it("una región sin datos: su nombre y la frase del backend en gris, sin la cadena", () => {
    const html = render("immune");
    expect(html).toContain("Sistema inmune (todo el cuerpo)");
    expect(html).toContain(`<p class="secondary">${NO_DATA}</p>`);
    expect(html).not.toContain("Variables");
    expect(html).not.toMatch(/c-(red|yellow|blue|cyan)/);
  });

  it("una región que no está en la respuesta (o sin respuesta aún) no abre nada", () => {
    expect(render("lungs")).toBe("");
    expect(render("heart", { state: null, error: null, stale: false })).toBe("");
  });
});

describe("la figura de «Inicio» y «Radiación»", () => {
  it("una región elegida en otra pestaña no abre aquí la ficha: solo un clic en esta figura", () => {
    const html = renderToStaticMarkup(
      createElement(RegionFigure, { view, region: "heart", setRegion: () => undefined, status }),
    );
    expect(html).toContain('data-region="heart"');
    expect(html).not.toContain('role="dialog"');
  });
});

describe("lo que la cierra y hacia dónde se abre", () => {
  it("Esc la cierra; otras teclas no", () => {
    const key = (name: string) => ({ kind: "key", key: name, handled: false, focusNear: true }) as const;
    expect(closesPopover(key("Escape"))).toBe(true);
    expect(closesPopover(key("Enter"))).toBe(false);
    expect(closesPopover(key("Tab"))).toBe(false);
  });

  it("Esc no se quita a otro diálogo: ni ya atendido ni con el foco lejos de la ficha", () => {
    expect(closesPopover({ kind: "key", key: "Escape", handled: true, focusNear: true })).toBe(false);
    expect(closesPopover({ kind: "key", key: "Escape", handled: false, focusNear: false })).toBe(false);
  });

  it("pulsar fuera la cierra; dentro o sobre otra región, no (esa la cambia)", () => {
    expect(closesPopover({ kind: "pointer", inside: false, onRegion: false })).toBe(true);
    expect(closesPopover({ kind: "pointer", inside: true, onRegion: false })).toBe(false);
    expect(closesPopover({ kind: "pointer", inside: false, onRegion: true })).toBe(false);
  });

  it("a la derecha del cuerpo si cabe, si no a la izquierda, si no debajo", () => {
    expect(popoverSide({ left: 100, right: 300 }, 400, 1200)).toBe("right");
    expect(popoverSide({ left: 700, right: 1000 }, 400, 1200)).toBe("left");
    expect(popoverSide({ left: 100, right: 300 }, 400, 500)).toBe("below");
  });

  it("las contramedidas con seguimiento abierto, como en la consola", () => {
    expect([...followingOf(status)]).toEqual(["cm-open"]);
  });
});

describe("pulsar una zona de la silueta", () => {
  const target = (region: string | null) => ({
    closest: (selector: string) =>
      selector === "g.zone[data-region]" && region !== null ? { getAttribute: () => region } : null,
  });

  it("da la región de la zona pulsada", () => {
    expect(zoneOf(target("heart") as unknown as EventTarget)).toBe("heart");
  });

  it("fuera de toda zona, o con una región que la figura no conoce, nada", () => {
    expect(zoneOf(target(null) as unknown as EventTarget)).toBeNull();
    expect(zoneOf(target("immune") as unknown as EventTarget)).toBeNull();
    expect(zoneOf(null)).toBeNull();
  });
});
