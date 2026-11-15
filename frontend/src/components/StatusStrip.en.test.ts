/**
 * La franja común (F.4.2) en inglés (`lib/i18n.ts`): los rótulos de las celdas y sus palabras de
 * estado. Marcas, colores y cifras son los de `StatusStrip.test.ts`; aquí solo el idioma.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import type { AlertCounts } from "../lib/alerts";
import type { CrewStatus } from "../lib/api";
import { formatMinutes } from "../lib/format";
import { AlertBell, StatusStrip } from "./StatusStrip";

function status(over: {
  mode?: CrewStatus["mission"]["mode"];
  level?: "full" | "reduced";
  causes?: ("missing" | "manual")[];
  comms?: CrewStatus["comms"];
  integrity?: boolean;
} = {}): CrewStatus {
  const partial = {
    data: { reference_time: "2026-03-02T00:00:00Z", integrity_ok: over.integrity ?? true },
    mission: { start: "2026-03-01", mode: over.mode ?? "simulation" },
    monitoring: {
      level: over.level ?? "full",
      capabilities: (over.causes ?? []).map((cause, index) => ({
        key: `c${index}`,
        label: `C${index}`,
        available: false,
        cause,
        consequence: "X",
      })),
    },
    freshness: { comms: { state: "fresh" }, solar: { state: "fresh" }, basis: "" },
    comms: over.comms === undefined ? { one_way_minutes: 4, round_trip_minutes: 8 } : over.comms,
    comms_data_age: "2026-03-01",
    declared_link: { state: "undeclared", attention: false, headline: null, sentence: "S" },
  };
  return partial as unknown as CrewStatus;
}

const none: AlertCounts = { warning: 0, caution: 0, advisory: 0, unacknowledged: 0, suppressed: 0, inhibited: 0 };

function render(props: Partial<Parameters<typeof StatusStrip>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(StatusStrip, { status: status(), loading: false, counts: none, consoleTitle: "TITLE", ...props }),
  );
}

describe("la franja en inglés", () => {
  it("los rótulos de las celdas", () => {
    const text = textNodes(render());
    for (const label of ["Last reading analyzed", "Mode", "Monitoring", "Active alerts", "Signed ledger"]) {
      expect(text).toContain(label);
    }
    for (const label of ["Última lectura analizada", "Modo", "Vigilancia", "Alertas activas", "Registro firmado"]) {
      expect(text).not.toContain(label);
    }
  });

  it("las palabras de estado: modo, vigilancia e integridad", () => {
    const html = render();
    expect(html).toContain("Simulation");
    expect(html).toMatch(/<\/svg>Full<\/span>/);
    expect(html).toMatch(/<\/svg>Intact<\/span>/);
    expect(html).not.toMatch(/Simulación|Completa|Íntegro/);
    expect(render({ status: status({ mode: "mixed" }) })).toContain("Mixed: simulated and real");
    expect(render({ status: status({ integrity: false }) })).toContain("Integrity compromised");
  });

  it("la vigilancia reducida cuenta cada causa en inglés", () => {
    const html = render({ status: status({ level: "reduced", causes: ["missing", "manual", "manual"] }) });
    expect(html).toMatch(/<\/svg>Reduced<\/span>/);
    expect(html).toContain('<span class="num">1</span> without data');
    expect(html).toContain('<span class="num">2</span> by manual decision');
    expect(html).not.toMatch(/Reducida|sin datos|por decisión manual/);
  });

  it("el retardo: ida, ida y vuelta y la edad de las efemérides", () => {
    const html = render();
    expect(html).toContain(`one way ${formatMinutes(4)} · round trip ${formatMinutes(8)}`);
    expect(html).toContain("Delay to Earth · ephemeris 2026-03-01");
    expect(html).not.toMatch(/ida y vuelta|Retardo|efemérides/);
  });

  it("sin efemérides y sin estado del backend, la palabra de reserva es inglesa", () => {
    const html = render({ status: status({ comms: null }) });
    expect(html).toContain("Delay to Earth");
    expect(html).toContain("No ephemeris");
    expect(html).not.toContain("Sin efemérides");
  });

  it("las alertas: lo no reconocido y lo silenciado", () => {
    const html = render({ counts: { ...none, advisory: 1, unacknowledged: 1, suppressed: 2, inhibited: 3 } });
    expect(html).toContain("unacknowledged 1");
    expect(html).toContain("suppressed 2");
    expect(html).toContain("inhibited 3");
    expect(html).not.toMatch(/sin reconocer|suprimidas|inhibidas/);
  });

  it("cargando y sin datos", () => {
    expect(render({ loading: true })).toContain("Loading…");
    expect(render({ status: null })).toContain("No data for this crew member");
  });

  it("la campana dice la cuenta y adónde lleva", () => {
    const html = renderToStaticMarkup(
      createElement(AlertBell, { counts: { ...none, caution: 2 }, onOpen: () => undefined }),
    );
    expect(html).toContain('aria-label="Alerts: 2 active, view"');
    expect(html).toMatch(/<\/svg>Alerts<\/span>/);
    expect(html).not.toContain("Alertas");
  });
});
