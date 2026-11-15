import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { spanWithPictogram, taggedPictogram, textNodes } from "./advisor/visibleText";
import { About } from "./About";
import { App, EmptyStore, SCENARIO_LABELS, SCENARIO_PICTOGRAMS, ScenarioSwitcher } from "./App";
import { isPictogramName } from "./icons";
import { uiPictogram } from "./lib/uiMarks";

/**
 * La carcasa tras pasar a pictogramas (§5.32.11): pestañas, selector, escenarios, almacén vacío
 * y «acerca de». Se pinta sin red con `renderToStaticMarkup`: los efectos no corren, así que la
 * aplicación queda en su primer estado (cargando) y el almacén vacío sin la lista de escenarios;
 * lo que se mira es que cada palabra de la carcasa lleva su dibujo al lado y ninguno va solo.
 */

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

describe("pestañas y franja", () => {
  const html = render(createElement(App));

  it("cada consola con su dibujo junto al nombre: casco a bordo, globo en Tierra", () => {
    expect(html).toMatch(
      /<button role="tab" aria-selected="true" tabindex="0" data-console="crew"><span class="mark"><svg [^>]*data-pictogram="helmet"[^>]*>.*?<\/svg>Consola de tripulación<\/span><\/button>/,
    );
    expect(html).toMatch(
      /<button role="tab" aria-selected="false" tabindex="-1" data-console="ground"><span class="mark"><svg [^>]*data-pictogram="globe"[^>]*>.*?<\/svg>Consola de Tierra<\/span><\/button>/,
    );
  });

  it("el conmutador de consola es el único tablist de la barra: tripulante y escenario quedan fuera (§5.40.2)", () => {
    expect(html).toMatch(/<nav class="tabs" aria-label="[^"]+"><div class="console-switch" role="tablist" aria-label="Consolas">/);
    const tablist = /<div class="console-switch" role="tablist"[^>]*>([\s\S]*?)<\/div>/.exec(html)?.[1] ?? "";
    expect(tablist.match(/<button role="tab"/g)).toHaveLength(2);
    expect(tablist).not.toContain("<select");
  });

  it("la consola elegida, con barra, negrita y fondo elevado, no solo color; 48 px al tacto", () => {
    const css = readFileSync(fileURLToPath(new URL("./styles.css", import.meta.url)), "utf8");
    const selected = /\.console-switch > button\[role="tab"\]\[aria-selected="true"\] \{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(selected).toContain("font-weight: 600");
    expect(selected).toContain("background: var(--c-raised)");
    expect(selected).toContain("border-bottom-color: var(--c-text)");
    expect(css).toMatch(/@media \(pointer: coarse\) \{\s*nav\.tabs \.console-switch > button\[role="tab"\],[^{]*\{\s*min-height: 48px/);
  });

  it("el título de la franja lleva el mismo dibujo que la pestaña activa", () => {
    expect(html).toMatch(/<h1 class="title">EMMA · <span class="mark"><svg [^>]*data-pictogram="helmet"[^>]*>.*?<\/svg>Consola de tripulación · crew-01<\/span><\/h1>/);
  });

  it("mientras carga, la flecha circular junto a la palabra", () => {
    expect(html).toMatch(spanWithPictogram("mark", "refresh", "Cargando estado…"));
  });

  it("ningún dibujo va sin palabra: los textos visibles son los de siempre", () => {
    expect(textNodes(html)).toContain("Consola de tripulación");
    expect(textNodes(html)).toContain("Consola de Tierra");
    expect(textNodes(html)).toContain("Cargando estado…");
  });
});

describe("lector de pantalla (§5.41)", () => {
  const html = render(createElement(App));

  it("lo primero de la página es «Saltar al contenido», y su destino recibe el foco", () => {
    expect(html).toMatch(/^<div class="app"><a class="skip-link" href="#contenido">Saltar al contenido<\/a>/);
    expect(html).toContain('<main id="contenido" tabindex="-1">');
  });

  it("las regiones vivas de las alertas están desde el primer render, antes de la franja", () => {
    expect(html).toMatch(
      /<\/a><div class="sr-only"><div role="alert" aria-atomic="false"><\/div><div role="status" aria-atomic="false"><\/div><\/div><header class="strip"/,
    );
  });

  it("un solo h1, el título de la franja", () => {
    expect(html.match(/<h1[ >]/g)).toHaveLength(1);
  });

  it("con la privacidad, el selector de tripulante fuera del lector, y el anuncio sin motivos", () => {
    // El selector solo se pinta con dos tripulantes o más, que llegan por la red: se mira el código.
    const source = readFileSync(fileURLToPath(new URL("./App.tsx", import.meta.url)), "utf8");
    expect(source).toMatch(/<select value=\{subject\} inert=\{modes\.privacy\}/);
    expect(source).toMatch(/<AlertAnnouncer[\s\S]*?privacy=\{modes\.privacy\}[\s\S]*?\/>/);
  });
});

describe("escenarios del simulador", () => {
  it("cada escenario con nombre tiene su dibujo, y cada dibujo existe", () => {
    expect(Object.keys(SCENARIO_PICTOGRAMS).sort()).toEqual(Object.keys(SCENARIO_LABELS).sort());
    for (const name of Object.values(SCENARIO_PICTOGRAMS)) expect(isPictogramName(name), name).toBe(true);
  });

  it("dos escenarios no comparten dibujo: el dibujo distingue, la palabra nombra", () => {
    const names = Object.values(SCENARIO_PICTOGRAMS);
    expect(new Set(names).size).toBe(names.length);
  });
});

describe("cambio de escenario (§5.33.11)", () => {
  // Sin red: la lista de escenarios no llega, pero el rótulo, el selector y el mando se pintan.
  const html = render(createElement(ScenarioSwitcher, { current: "co2-fatigue", onSwitched: () => undefined }));

  it("«Escenario:» con la onda de cambiar de escenario; no nombra el selector, que elige el siguiente", () => {
    expect(uiPictogram("changeScenario")).toBe("wave-zigzag");
    expect(html).toMatch(taggedPictogram("label", "wave-zigzag", "Escenario:"));
    expect(html).not.toContain(" for=");
  });

  it("el selector del siguiente lleva su propio nombre accesible (axe select-name, §5.41)", () => {
    expect(html).toMatch(/<select aria-label="Escenario al que cambiar">/);
  });

  it("el escenario en curso con su dibujo, y «Cambiar…» con el signo de cambiar, desactivado sin elección", () => {
    expect(html).toMatch(spanWithPictogram("mark", "ridge-environment", "CO2 de cabina (toda la tripulación)"));
    expect(html).toMatch(taggedPictogram("button", "wave-zigzag", "Cambiar…", ' class="command" disabled=""'));
  });

  it("al confirmar: «Confirmar cambio» con la marca de dar por bueno y la cinta, «Cancelar» con la cruz", () => {
    // El paso de confirmar necesita un clic: se mira la fuente.
    const source = readFileSync(fileURLToPath(new URL("./App.tsx", import.meta.url)), "utf8");
    expect(source).toMatch(/<Command concept="confirmChange" hazard onClick=\{\(\) => void change\(\)\}>\s*\{tr\("Confirmar cambio", "Confirm change"\)\}\s*<\/Command>/);
    expect(source).toMatch(/<Command concept="cancel" onClick=\{\(\) => setConfirming\(false\)\}>\s*\{tr\("Cancelar", "Cancel"\)\}\s*<\/Command>/);
  });
});

describe("errores y carga", () => {
  const source = readFileSync(fileURLToPath(new URL("./App.tsx", import.meta.url)), "utf8");

  it("todo fallo va con la marca de lo que fue (rechazo o caída): nada en rojo sin forma (§5.34.14)", () => {
    expect(source).not.toContain("c-red");
    expect(source).not.toMatch(/<Mark pictogram="cross"/);
    // Ni una marca de petición fija: la decide `requestOutcome` con el código de estado.
    expect(source).not.toMatch(/FAILURE_MARK|REFUSED_MARK/);
    // El estado, el cambio de escenario, el almacén vacío y los datos reales.
    expect(source.match(/<MarkOf mark=\{[a-z.]+\.mark\}>/g)).toHaveLength(4);
  });

  it("toda carga con la marca de cargando, no con un dibujo escrito a mano", () => {
    expect(source).not.toMatch(/<Mark pictogram="refresh"/);
  });
});

describe("almacén vacío", () => {
  const html = render(createElement(EmptyStore, { subject: "crew-01", onLoaded: () => undefined }));

  it("lo que falta, en cian con el anillo punteado junto al título", () => {
    expect(html).toMatch(/<h2 class="c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>No hay lecturas del tripulante<\/h2>/);
  });

  it("los datos reales con el cohete del vuelo real, en un mando corriente, sin color de alerta", () => {
    expect(html).toMatch(
      /<button class="command"><span class="mark"><svg [^>]*data-pictogram="rocket"[^>]*>.*?<\/svg>Analíticas reales de Inspiration4 \(NASA OSDR\)<\/span><\/button>/,
    );
    expect(html).not.toContain("hazard");
  });
});

describe("acerca de", () => {
  it("el círculo con la i junto al resumen", () => {
    const html = render(createElement(About));
    expect(html).toMatch(/<summary><svg [^>]*data-pictogram="circle-i"[^>]*>.*?<\/svg>Acerca de EMMA<\/summary>/);
  });
});

describe("la fuente", () => {
  it("App.tsx no escribe un carácter de forma: todos pasaron a pictogramas", () => {
    const source = readFileSync(fileURLToPath(new URL("./App.tsx", import.meta.url)), "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(code).not.toMatch(/[△◌✓✕○◇■●◐▷⊘☐]/);
  });
});
