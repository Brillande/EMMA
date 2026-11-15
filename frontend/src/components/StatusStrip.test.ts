import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { spanWithPictogram, textNodes } from "../advisor/visibleText";
import type { AlertCounts } from "../lib/alerts";
import type { CrewStatus } from "../lib/api";
import { formatMinutes } from "../lib/format";
import { LEVELS } from "../lib/levels";
import { uiPictogram } from "../lib/uiMarks";
import { StatusStrip } from "./StatusStrip";

/**
 * La franja común (F.4.2) tras pasar a pictogramas (§5.32.11): cada celda lleva en el rótulo el
 * dibujo de lo que mide y en el valor el de su estado, siempre junto a la palabra, y el color de
 * la tabla F.5-1 nunca va solo. Se pinta con `renderToStaticMarkup`, sin red: `SafeMode` no ha
 * leído aún su estado y no pinta nada, así que lo que se mira aquí es el resto de la franja.
 */

/** Lo que la franja lee de un estado; el resto no entra en lo que pinta. */
function status(over: {
  mode?: CrewStatus["mission"]["mode"];
  level?: "full" | "reduced";
  causes?: ("missing" | "manual")[];
  comms?: CrewStatus["comms"];
  freshness?: "fresh" | "stale" | "missing";
  integrity?: boolean;
  link?: Partial<CrewStatus["declared_link"]>;
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
    freshness: { comms: { state: over.freshness ?? "fresh" }, solar: { state: "fresh" }, basis: "" },
    comms: over.comms === undefined ? { one_way_minutes: 4, round_trip_minutes: 8 } : over.comms,
    comms_data_age: "2026-03-01",
    declared_link: { state: "undeclared", attention: false, headline: null, sentence: "S", ...over.link },
  };
  return partial as unknown as CrewStatus;
}

const none: AlertCounts = { warning: 0, caution: 0, advisory: 0, unacknowledged: 0, suppressed: 0, inhibited: 0 };

function render(props: Partial<Parameters<typeof StatusStrip>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(StatusStrip, {
      status: status(),
      loading: false,
      counts: none,
      consoleTitle: "TITULO · crew-01",
      ...props,
    }),
  );
}

describe("título y estados de carga", () => {
  it("el título lleva el dibujo de la consola junto a su nombre, y EMMA sin dibujo: no es un logotipo", () => {
    const html = render({ consolePictogram: "helmet" });
    expect(html).toMatch(/<h1 class="title">EMMA · <span class="mark"><svg [^>]*data-pictogram="helmet"/);
    expect(html).toContain("</svg>TITULO · crew-01</span></h1>");
  });

  it("sin dibujo de consola, el título es solo texto", () => {
    expect(render()).toContain('<h1 class="title">EMMA · TITULO · crew-01</h1>');
  });

  it("cargando: la flecha circular; sin datos: el anillo punteado en cian", () => {
    expect(render({ loading: true })).toMatch(spanWithPictogram("mark secondary", "refresh", "Cargando…"));
    expect(render({ status: null })).toMatch(spanWithPictogram("mark c-cyan", "ring-dotted", "Sin datos del tripulante"));
  });
});

describe("celdas", () => {
  it("cada rótulo lleva el dibujo de su concepto (§5.33.11), el mismo que en cualquier panel", () => {
    const html = render();
    expect(html).toMatch(spanWithPictogram("label", uiPictogram("time"), "Última lectura analizada"));
    expect(html).toMatch(spanWithPictogram("label", uiPictogram("alerts"), "Alertas activas"));
    expect(html).toMatch(spanWithPictogram("label", uiPictogram("signedLedger"), "Registro firmado"));
    expect(html).toMatch(spanWithPictogram("label", uiPictogram("monitoring"), "Vigilancia"));
    // «Modo» no es un concepto de ningún panel: el mando giratorio de un selector, del conjunto
    // de la carcasa, y nunca el dibujo de uno de los modos (ese va en el valor, al lado).
    expect(html).toMatch(spanWithPictogram("label", "knob-ticks", "Modo"));
  });

  it("el retardo con Tierra lleva los arcos de la señal, no el globo: el globo es Tierra, no el retardo", () => {
    const html = render();
    expect(uiPictogram("lightTime")).toBe("signal-arcs");
    expect(html).toMatch(spanWithPictogram("label", "signal-arcs", "Retardo con Tierra · efemérides 2026-03-01"));
    expect(render({ status: status({ comms: null }) })).toMatch(spanWithPictogram("label", "signal-arcs", "Retardo con Tierra"));
    expect(html).not.toContain('data-pictogram="globe"');
  });

  it("el modo con su dibujo: onda (simulado), onda y punto (mezcla), cohete (misión)", () => {
    expect(render({ status: status({ mode: "simulation" }) })).toMatch(spanWithPictogram("mark mode-tag", "wave-zigzag", "Simulación"));
    expect(render({ status: status({ mode: "mixed" }) })).toMatch(spanWithPictogram("mark mode-tag", "wave-dot", "Mezcla: simulado y real"));
    // En misión no hay marco a rayas: es el modo nominal, no el que hay que distinguir (F.4.2).
    expect(render({ status: status({ mode: "mission" }) })).toMatch(spanWithPictogram("mark", "rocket", "Misión"));
  });

  it("vigilancia completa con la marca de hecho; reducida, con el anillo en cian por dato ausente y el triángulo en amarillo por decisión manual", () => {
    expect(render()).toMatch(spanWithPictogram("mark", "check", "Completa"));
    const reduced = render({ status: status({ level: "reduced", causes: ["missing", "missing", "manual"] }) });
    // «Reducida» con la marca de su causa: si falta algún dato, la del dato ausente.
    expect(reduced).toMatch(spanWithPictogram("mark c-cyan", "ring-dotted", "Reducida"));
    expect(reduced).toMatch(spanWithPictogram("mark c-cyan", "ring-dotted", '<span class="num">2</span> sin datos'));
    expect(reduced).toMatch(spanWithPictogram("mark c-yellow", "shape-triangle", '<span class="num">1</span> por decisión manual'));
    expect(reduced).not.toMatch(spanWithPictogram("mark", "check", "Completa"));
  });

  it("reducida solo por decisión manual: el triángulo en amarillo; por una causa que no se conoce, la marca de desconocido", () => {
    const manual = render({ status: status({ level: "reduced", causes: ["manual"] }) });
    expect(manual).toMatch(spanWithPictogram("mark c-yellow", "shape-triangle", "Reducida"));
    expect(manual).not.toContain("ring-dotted");
    const unknown = render({ status: status({ level: "reduced", causes: [] }) });
    expect(unknown).toMatch(spanWithPictogram("mark c-text", "dot-small", "Reducida"));
  });

  it("cada clase de alerta con la forma de su nivel: en su color si hay alguna, en secundario a cero", () => {
    const html = render({ counts: { ...none, warning: 2, caution: 0, advisory: 1, unacknowledged: 3 } });
    expect(html).toMatch(spanWithPictogram("mark c-red", LEVELS.critical.pictogram, "W 2"));
    expect(html).toMatch(spanWithPictogram("mark secondary", LEVELS.concern.pictogram, "C 0"));
    expect(html).toMatch(spanWithPictogram("mark c-blue", LEVELS.watch.pictogram, "A 1"));
    expect(html).toMatch(spanWithPictogram("mark secondary", "box-empty", "sin reconocer 3"));
    // Los contadores no parpadean: eso es de la fila de la alerta crítica.
    expect(html).not.toContain("flash");
    expect(html).not.toContain("bell-slash");
  });

  it("lo silenciado se ve siempre, con la marca de su anuncio: tachada la suprimida, enmarcada la inhibida", () => {
    const html = render({ counts: { ...none, suppressed: 1, inhibited: 2 } });
    expect(html).toMatch(spanWithPictogram("mark", "bell-slash", "suprimidas 1"));
    // La misma que en la fila de la alerta y que el mando de inhibir: un concepto, un dibujo.
    expect(uiPictogram("inhibit")).toBe("bell-box");
    expect(html).toMatch(spanWithPictogram("mark", "bell-box", "inhibidas 2"));
  });

  it("retardo al día: la cifra sin marca; caducado o sin veredicto: anillo punteado en cian; sin efemérides: lo mismo con la palabra", () => {
    const delay = `ida ${formatMinutes(4)} · ida y vuelta ${formatMinutes(8)}`;
    expect(render()).toContain(`<span class="num">${delay}</span>`);
    expect(render()).not.toContain("ring-dotted");
    expect(render({ status: status({ freshness: "stale" }) })).toMatch(spanWithPictogram("mark num c-cyan", "ring-dotted", delay));
    expect(render({ status: status({ freshness: "missing" }) })).toMatch(spanWithPictogram("mark num c-cyan", "ring-dotted", delay));
    expect(render({ status: status({ comms: null }) })).toMatch(spanWithPictogram("mark c-cyan", "ring-dotted", "Sin efemérides"));
  });

  it("el enlace declarado caído o degradado va debajo del retardo, con la frase del backend y la marca del panel de sistemas; sin nada que señalar, no hay línea", () => {
    expect(render()).not.toContain("link-declared");
    // Declarado sin problema: el backend no da frase corta y la franja no crece.
    expect(render({ status: status({ link: { state: "nominal", attention: false } }) })).not.toContain("link-declared");
    const down = "Enlace declarado «fuera de servicio» desde 2026-03-02 00:00 UTC por CDR (declarado por una persona, no telemetría)";
    const html = render({ status: status({ link: { state: "out-of-service", attention: true, headline: down } }) });
    expect(html).toMatch(spanWithPictogram("mark link-declared c-yellow", "slash-circle", down));
    // La cifra del retardo sigue siendo la de las efemérides, sin marca.
    expect(html).toContain(`<span class="num">ida ${formatMinutes(4)} · ida y vuelta ${formatMinutes(8)}</span>`);
    const degraded = render({ status: status({ link: { state: "degraded", attention: true, headline: "D" } }) });
    expect(degraded).toMatch(spanWithPictogram("mark link-declared c-yellow", "shape-triangle", "D"));
    // Sin efemérides también se dice: la declaración no depende de ellas.
    const blind = render({ status: status({ comms: null, link: { state: "out-of-service", attention: true, headline: down } }) });
    expect(blind).toMatch(spanWithPictogram("mark c-cyan", "ring-dotted", "Sin efemérides"));
    expect(blind).toMatch(spanWithPictogram("mark link-declared c-yellow", "slash-circle", down));
  });

  it("registro íntegro con la marca de hecho; comprometido, la cruz en rojo", () => {
    expect(render()).toMatch(spanWithPictogram("mark", "check", "Íntegro"));
    expect(render()).not.toContain("c-red");
    expect(render({ status: status({ integrity: false }) })).toMatch(spanWithPictogram("mark c-red", "cross", "Integridad comprometida"));
  });

  it("ningún carácter de forma queda en el texto: todos pasaron a pictogramas", () => {
    const html = render({
      status: status({ level: "reduced", causes: ["missing", "manual"], freshness: "stale", integrity: false }),
      counts: { ...none, warning: 1, suppressed: 1 },
    });
    expect(textNodes(html).join(" ")).not.toMatch(/[△◌✓✕○◇■●◐▷⊘☐]/);
  });
});

describe("la fuente", () => {
  const source = readFileSync(fileURLToPath(new URL("./StatusStrip.tsx", import.meta.url)), "utf8");

  it("no escribe un carácter de forma, y el rótulo «Vigilancia» sigue carácter a carácter (wording.test.ts)", () => {
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(code).not.toMatch(/[△◌✓✕○◇■●◐▷⊘☐]/);
    // Desde los dos idiomas (2026-11-15) el rótulo va en un `tr`; `wording.test.ts` declara ese fragmento.
    expect(source).toContain(
      '<FieldLabel as="span" className="label" concept="monitoring">{tr("Vigilancia", "Monitoring")}</FieldLabel>',
    );
  });

  it("ningún rótulo de celda se escribe a mano: todos son `FieldLabel` en un `span.label`", () => {
    expect(source).not.toMatch(/<span className="label">/);
    expect(source).not.toMatch(/<Pictogram\b/);
    const labels = source.match(/<FieldLabel\b[^>]*>/g) ?? [];
    expect(labels).toHaveLength(7);
    for (const label of labels) expect(label).toMatch(/^<FieldLabel as="span" className="label" /);
  });
});

describe("franja compacta (§5.40, 2026-11-04)", () => {
  const css = readFileSync(fileURLToPath(new URL("../styles.css", import.meta.url)), "utf8").replace(
    /\/\*[\s\S]*?\*\//g,
    "",
  );

  it("los mandos van juntos al final, detrás de las celdas; sin mandos, no hay grupo vacío", () => {
    const html = render({ voice: createElement("div", { className: "cell read-aloud" }, "VOZ") });
    const header = html.slice(0, html.indexOf("</header>") + "</header>".length);
    expect(header).toMatch(/<div class="strip-controls"><div class="cell read-aloud">VOZ<\/div><\/div><\/header>$/);
    expect(header.indexOf("Registro firmado")).toBeLessThan(header.indexOf("strip-controls"));
    expect(render()).not.toContain("strip-controls");
    // A bordo, sin voz y con el estado de la red sin leer aún, el modo seguro no tiene mando todavía.
    expect(render({ controls: true })).not.toContain("strip-controls");
  });

  it("una sola corriente que se parte en filas, de 44 px y de 48 px al tacto", () => {
    expect(css).toMatch(/\.strip \{[^}]*display: flex;[^}]*flex-wrap: wrap;/);
    // `--touch`: 44 px con ratón, 48 al tacto (`pointer: coarse`), el mismo token que todo mando.
    expect(css).toMatch(/@media \(pointer: coarse\) \{\s*:root \{[^}]*--touch: 48px;/);
    for (const selector of [
      ".strip .cell",
      ".strip details.strip-pop > summary",
      ".strip .read-aloud button.command",
      ".strip .halt-notice > button.command",
      ".strip .silence-form input",
    ]) {
      const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      expect(css, selector).toMatch(new RegExp(`(^|\\})\\s*${escaped} \\{[^}]*min-height: var\\(--touch\\);`));
    }
    expect(css).not.toMatch(/\.strip[^{]*\{[^}]*min-height: 4[0-7]px/);
  });

  it("lo que se abre desde un mando de la franja cuelga encima de la página, sin hacerla crecer", () => {
    expect(css).toMatch(/\.strip details\.strip-pop > :not\(summary\) \{[^}]*position: absolute;/);
  });

  it("«Atajos» cerrado se oculta con display: none, y en una pantalla solo táctil solo se ve abierto", () => {
    expect(css).toMatch(/\.strip details\.shortcuts::details-content \{\s*content-visibility: visible;\s*\}/);
    expect(css).toMatch(/\.strip details\.shortcuts:not\(\[open\]\) > \.shortcut \{\s*display: none;\s*\}/);
    // Pasar por encima o llegar con el tabulador solo lo enseña donde hay ratón o teclado.
    expect(css).toMatch(
      /@media not all and \(pointer: coarse\) and \(hover: none\) \{\s*\.strip details\.shortcuts:is\(:hover, :has\(> summary:focus-visible\)\) > \.shortcut \{\s*display: block;/,
    );
  });

  it("ningún texto de la franja baja de 0,875rem", () => {
    for (const [, selector, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (!/\.strip|\.halt-details/.test(selector ?? "")) continue;
      for (const [, size] of (body ?? "").matchAll(/font-size: ([\d.]+)rem/g)) {
        expect(Number(size), selector).toBeGreaterThanOrEqual(0.875);
      }
    }
  });
});
