import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import { ApiError, type CognitionProtocol, type CognitionRecordedSession, type CognitionSubmitted } from "../lib/api";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { CognitionView } from "./CognitionPanel";
import type { Draft } from "./draft";
import { protocol } from "./fixture";

/*
 * El panel pinta lo que da el backend: qué mide cada prueba con su frase, las puntuaciones a
 * copiar con su rango, quién teclea y lo que quedó firmado. No puntúa, no compara y no pinta
 * color según el valor. La PVT solo remite a su panel.
 */

const PANEL_CODE = readFileSync(fileURLToPath(new URL("./CognitionPanel.tsx", import.meta.url)), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

function render(over: {
  protocol?: CognitionProtocol | null;
  sessions?: CognitionRecordedSession[] | null;
  draft?: Draft;
  operator?: string;
  sending?: boolean;
  submitted?: CognitionSubmitted | null;
  failure?: RequestOutcome | null;
  unavailable?: RequestOutcome | null;
}): string {
  return renderToStaticMarkup(
    createElement(CognitionView, {
      protocol,
      sessions: [],
      draft: {},
      onDraft: () => undefined,
      subject: "crew-01",
      operator: "CDR",
      onOperator: () => undefined,
      sending: false,
      submitted: null,
      failure: null,
      unavailable: null,
      onSubmit: () => undefined,
      ...over,
    }),
  );
}

const session: CognitionRecordedSession = {
  effective: "2026-11-03T09:00:00+00:00",
  source: "console-cognition",
  source_display: "batería Cognition en la consola",
  recorded_by: null,
  recorded_by_display: "no consta",
  observation_type: "measured",
  evidence_context: "ground",
  position: "descriptive",
  position_note: "NOTA-DE-POSICION",
  values: [
    {
      key: "cognition-mpt-speed",
      sigla: "MPT",
      measure_display: "velocidad",
      display: "DISPLAY",
      display_es: "NOMBRE-MPT",
      value: 812,
      value_text: "812 ms",
    },
  ],
};

describe("panel de la batería Cognition", () => {
  it("sin protocolo dice que carga, o por qué no está", () => {
    expect(render({ protocol: null })).toContain("Cargando");
    const down = render({ protocol: null, unavailable: requestOutcome(new ApiError(503, "CAIDO")) });
    expect(down).toContain("CAIDO");
  });

  it("enseña el título, lo que hace EMMA, el alcance y los límites con el texto del backend", () => {
    const html = render({});
    expect(html).toMatch(taggedPictogram("h2", "clipboard", "TITULO-DEL-BACKEND</h2>"));
    expect(html).toContain("IDENTIDAD-DEL-BACKEND");
    expect(html).toContain("ALCANCE-DEL-BACKEND");
    expect(html).toContain("<li>LIMITE-1</li>");
    expect(html).toContain("<li>NO-ENCONTRADO-1</li>");
  });

  it("cada prueba en su orden, con qué mide en el idioma de su fuente, y la PVT remite a su panel", () => {
    const html = render({});
    const order = ["mpt", "volt", "pvt"].map((abbrev) => html.indexOf(`data-cognition-test="${abbrev}"`));
    expect(order.every((at) => at > 0)).toBe(true);
    expect(order).toEqual([...order].sort((a, b) => a - b));
    expect(html).toContain('<q lang="en">QUOTE-cog-test-mpt</q>');
    expect(html).toContain("SIN-FRASE-LEIDA");
    expect(html).toContain("NOTA-DE-LA-PVT");
    // La PVT no tiene campos aquí.
    const pvt = html.split('data-cognition-test="pvt"')[1]!.split("</article>")[0]!;
    expect(pvt).not.toContain("<input");
  });

  it("un campo por puntuación, con su rótulo del backend, su rango y ningún valor por defecto", () => {
    const html = render({});
    for (const key of ["cognition-mpt-speed", "cognition-volt-speed", "cognition-volt-accuracy"]) {
      expect(html).toMatch(new RegExp(`<input id="cognition-${key}"[^>]*value=""`));
    }
    expect(html).toContain("NOMBRE-cognition-volt-accuracy");
    expect(html).toContain('Rango: <span class="num">RANGO-MS</span>');
    // Qué es cada cifra va plegado, con su frase; en la MPT, también que no tiene precisión.
    expect(html).toContain("QUOTE-frase-cognition-volt-accuracy");
    expect(html).toContain("QUOTE-cog-mpt-no-accuracy");
  });

  it("lo que está fuera de rango se dice con la marca de un rechazo, y no se puede registrar", () => {
    const html = render({ draft: { "cognition-mpt-speed": "0" } });
    expect(html).toMatch(markedHtml("shape-triangle", "Fuera del rango: RANGO-MS.", "yellow"));
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
  });

  it("una prueba a medias se nombra, y no se registra", () => {
    const html = render({ draft: { "cognition-volt-speed": "900" } });
    expect(html).toContain("Pruebas a medias: VOLT.");
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
  });

  it("con una prueba entera y un nombre, se puede registrar; sin nombre, no", () => {
    const ok = render({ draft: { "cognition-mpt-speed": "700" } });
    expect(ok).not.toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
    expect(ok).toMatch(taggedPictogram("label", "person", "ROTULO-DE-QUIEN-ANOTA <input", ' class="operator"'));
    expect(ok).toContain("fuente: batería Cognition en la consola");
    const unnamed = render({ draft: { "cognition-mpt-speed": "700" }, operator: "  " });
    expect(unnamed).toContain("Falta el nombre de quien está en la consola");
    expect(unnamed).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
  });

  it("tras registrar, los asientos; y el rechazo del backend, tal cual", () => {
    const done = render({
      submitted: {
        recorded: [4, 5],
        keys: ["cognition-volt-speed", "cognition-volt-accuracy"],
        source: "console-cognition",
        source_display: "batería Cognition en la consola",
        recorded_by: "CDR",
      },
    });
    expect(done).toContain("Registrado:");
    expect(done).toContain('<span class="num">4, 5</span>');
    const refused = render({ failure: requestOutcome(new ApiError(422, "MOTIVO-DEL-BACKEND")) });
    expect(refused).toContain("MOTIVO-DEL-BACKEND");
    expect(refused).toContain('role="alert"');
  });

  it("las sesiones del registro, con su procedencia, quién tecleó o que no consta, y la posición descriptiva", () => {
    const html = render({ sessions: [session] });
    expect(html).toContain('<span class="num">812 ms</span>');
    expect(html).toContain("· batería Cognition en la consola");
    expect(html).toMatch(markedHtml("slash-circle", "no consta", "gray"));
    expect(html).toMatch(markedHtml("dash", "NOTA-DE-POSICION"));
    const empty = render({ sessions: [] });
    expect(empty).toContain("Ninguna sesión de este tripulante en el registro.");
    // Sin leer el registro no se dice que esté vacío.
    expect(render({ sessions: null })).not.toContain("Ninguna sesión");
  });

  it("no pinta color según el valor ni escribe un texto clínico o una comparación", () => {
    const table = render({ sessions: [session] }).split("<table")[1]!.split("</table>")[0]!;
    const values = table.split("<td>")[1]!;
    expect(values).not.toMatch(/c-(red|yellow|blue|gray|cyan|magenta|green)/);
    expect(PANEL_CODE).not.toMatch(/\b(normal|bajo|alto|deterioro|percentil)\b/i);
  });
});

describe("batería Cognition en el tablero (concha de la maqueta, 2026-11-07)", () => {
  /** La tira de cifras de la última sesión, tal como queda en el HTML. */
  const strip = (html: string) => html.match(/<dl class="ref-stats cognition-board[^"]*"[\s\S]*?<\/dl>/)?.[0] ?? null;

  it("la última sesión va en la tira de cifras: sigla, medida y `value_text` del backend, sin color", () => {
    const html = strip(render({ sessions: [session] }));
    expect(html).not.toBeNull();
    expect(html).toContain('aria-label="Última sesión en el registro"');
    expect(html).toContain('<span class="cognition-sigla">MPT</span> velocidad');
    expect(html).toContain('<dd class="num">812 ms</dd>');
    expect(html).not.toMatch(/c-(red|yellow|green|cyan)/);
  });

  it("con la relectura caída la tira conserva lo de antes, en cursiva", () => {
    const html = render({ sessions: [session], unavailable: requestOutcome(new ApiError(503, "CAIDO")) });
    expect(html).toContain('class="ref-stats cognition-board stale"');
  });

  it("en la concha clásica no hay tira", () => {
    const html = renderToStaticMarkup(
      createElement(LookContext.Provider, { value: "classic" }, createElement(CognitionView, {
        protocol,
        sessions: [session],
        draft: {},
        onDraft: () => undefined,
        subject: "crew-01",
        operator: "CDR",
        onOperator: () => undefined,
        sending: false,
        submitted: null,
        failure: null,
        unavailable: null,
        onSubmit: () => undefined,
      })),
    );
    expect(strip(html)).toBeNull();
    expect(html).toContain("812 ms");
  });

  it("el formulario de una sesión va entero en su «Ver detalle» (quinta ronda); lo registrado, fuera y antes", () => {
    const html = render({ sessions: [session] });
    const toggle = html.indexOf("Ver detalle: anotar una sesión");
    expect(toggle).toBeGreaterThan(html.indexOf("Últimas sesiones en el registro"));
    const body = html.slice(toggle).match(/<div id="[^"]+" class="board-detail-body" hidden="">([\s\S]*)/)?.[1] ?? "";
    expect(body.startsWith('<form class="cognition-form"')).toBe(true);
    expect(body).toContain("Registrar la sesión");
    expect(body).toContain("data-cognition-test=");
  });
});
