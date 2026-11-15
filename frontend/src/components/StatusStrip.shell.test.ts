import { type ReactElement, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { spanWithPictogram, textNodes } from "../advisor/visibleText";
import type { AlertCounts } from "../lib/alerts";
import type { CrewStatus, LinkSync } from "../lib/api";
import { AlertBell, StatusStrip } from "./StatusStrip";

/**
 * Lo que la concha de la maqueta añade a la franja (2026-11-07, decisión del usuario de hacerla
 * consola): el tripulante y el escenario con los mandos (`tools`), el enlace simulado con Tierra
 * junto al retardo (`sync`) y el logotipo de la maqueta delante de «EMMA» (`brand`). Sin esas
 * props la franja es la de siempre, que mira `StatusStrip.test.ts`.
 */

function status(): CrewStatus {
  return {
    data: { reference_time: "2026-03-02T00:00:00Z", integrity_ok: true },
    mission: { start: "2026-03-01", mode: "simulation" },
    monitoring: { level: "full", capabilities: [] },
    freshness: { comms: { state: "fresh" }, solar: { state: "fresh" }, basis: "" },
    comms: { one_way_minutes: 4, round_trip_minutes: 8 },
    comms_data_age: "2026-03-01",
    declared_link: { state: "undeclared", attention: false, headline: null, sentence: "S" },
  } as unknown as CrewStatus;
}

function sync(over: Partial<LinkSync> = {}): LinkSync {
  return { state: "up", state_display: "Enlace activo", held: false, ...over } as unknown as LinkSync;
}

const none: AlertCounts = { warning: 0, caution: 0, advisory: 0, unacknowledged: 0, suppressed: 0, inhibited: 0 };

function render(props: Partial<Parameters<typeof StatusStrip>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(StatusStrip, { status: status(), loading: false, counts: none, consoleTitle: "TITULO · crew-01", ...props }),
  );
}

describe("la franja con la concha de la maqueta", () => {
  it("los mandos de `tools` van en el grupo de mandos, delante de la voz; solos, también abren el grupo", () => {
    const html = render({
      tools: createElement("label", { className: "crew-selector" }, "TRIP"),
      voice: createElement("div", { className: "cell read-aloud" }, "VOZ"),
    });
    expect(html).toMatch(/<div class="strip-controls"><label class="crew-selector">TRIP<\/label><div class="cell read-aloud">VOZ<\/div><\/div><\/header>/);
    expect(render({ tools: createElement("span", null, "T") })).toContain("strip-controls");
  });

  it("el enlace simulado caído va bajo el retardo con la marca de fuera de servicio y la palabra del backend; retenido, con la del dato que falta; arriba, nada", () => {
    expect(render({ sync: sync({ state: "down", state_display: "Enlace caído" }) })).toMatch(
      spanWithPictogram("mark link-declared c-yellow", "slash-circle", "Enlace caído"),
    );
    expect(render({ sync: sync({ held: true, state_display: "Enlace restablecido" }) })).toMatch(
      spanWithPictogram("mark link-declared c-cyan", "ring-dotted", "Enlace restablecido"),
    );
    expect(render({ sync: sync() })).not.toContain("link-declared");
    expect(render()).not.toContain("link-declared");
  });

  it("el logotipo de la maqueta va delante de «EMMA», con su nombre largo, solo si se pasa; sin él, el título es el de siempre", () => {
    const html = render({ brand: createElement("span", { className: "ref-logo" }, "L") });
    expect(html).toContain(
      '<div class="masthead-brand"><span class="ref-logo">L</span><span class="masthead-name"><span class="masthead-emma">EMMA</span><span class="masthead-long">Environment and Medical Monitoring Assistant</span></span></div>',
    );
    // El `h1` es el de siempre para el lector de pantalla: «EMMA · » se ve en la marca, encima.
    expect(html).toContain('<h1 class="title"><span class="sr-only">EMMA · </span>TITULO · crew-01</h1>');
    expect(render()).toContain('<h1 class="title">EMMA · TITULO · crew-01</h1>');
    expect(render()).not.toContain("masthead");
  });
});

/**
 * La cabecera de la muestra (lote «muestra», 2026-11-08). R4-1: dos franjas, arriba la línea de
 * lectura con «Arriba» y las celdas de F.4.2 (rótulo corto a la vista, el entero para el lector) y
 * debajo la fila de la muestra con la marca, el título, el lema, los mandos y los iconos (de 90 px a
 * 64 a 1672 de ancho, `shell/header.css`). Lo que mira esta prueba es que nada de lo que decía la
 * franja se pierde por el camino.
 */
describe("la cabecera de la muestra", () => {
  const brand = createElement("span", { className: "ref-logo" }, "L");
  const crew = createElement("label", { className: "crew-selector" }, "TRIP");
  const voice = createElement("div", { className: "cell read-aloud" }, "VOZ");

  // R5-1: una franja. A la izquierda la marca; a la derecha, arriba la línea de lectura y debajo el
  // título, el lema, los mandos y los iconos. El orden del documento es el de lectura.
  it("la marca; después, arriba «Arriba» y las celdas y debajo el título, el lema, los mandos y, al final, los iconos", () => {
    const html = render({ brand, crew, voice, edge: createElement("span", null, "ARRIBA") });
    expect(html).toMatch(
      /^<header class="strip strip-masthead" role="banner"><div class="masthead-brand">.*<\/div><div class="masthead-main"><div class="masthead-status"><div class="strip-edge"><span>ARRIBA<\/span><\/div><div class="masthead-cells"><div class="cell"/,
    );
    expect(html).toMatch(
      /<\/div><\/div><div class="masthead-bar"><h1 class="title"><span class="sr-only">EMMA · <\/span>TITULO · crew-01<\/h1><p class="masthead-motto">Monitorización · Prevención · Rendimiento · Salud de la Tripulación<\/p><div class="masthead-tools"><div class="strip-controls">/,
    );
    // Los mandos siguen juntos detrás de las celdas; el tripulante ya no va con ellos, sino en su
    // ficha, la última de los iconos.
    expect(html.indexOf("Registro firmado")).toBeLessThan(html.indexOf("strip-controls"));
    expect(html).toMatch(
      /<div class="strip-controls"><div class="cell read-aloud">VOZ<\/div><\/div><div class="masthead-icons">.*<div class="masthead-crew"><label class="crew-selector">TRIP<\/label><\/div><\/div><\/div><\/div><\/div><\/header>$/,
    );
  });

  it("cada celda dice a la vista un rótulo corto o solo su dibujo, con el entero en un `title`, y al lector de pantalla solo el entero", () => {
    const html = render({ brand });
    expect(html).toContain(
      '<span class="label-short" aria-hidden="true" title="Retardo con Tierra · efemérides 2026-03-01">efemérides 2026-03-01</span><span class="sr-only">Retardo con Tierra · efemérides 2026-03-01</span></span>',
    );
    // R5-1: lectura, modo, vigilancia, alertas y registro, solo con su dibujo delante del valor; el rótulo
    // entero, para el lector de pantalla y en el `title` de la celda.
    for (const full of ["Última lectura analizada", "Modo", "Alertas activas", "Registro firmado"]) {
      expect(html, full).toContain(`<div class="cell" title="${full}">`);
      expect(html, full).toMatch(new RegExp(`</svg><span class="sr-only">${full}</span></span>`));
    }
    // «Vigilancia», escrita tal cual en su celda (la recorta la hoja, `shell/header.css`).
    expect(html).toContain('<div class="cell cell-monitoring">');
    expect(html).toMatch(spanWithPictogram("label", "lighthouse", "Vigilancia"));
    // Sin la cabecera de la muestra, los rótulos enteros a la vista y sin `title`.
    expect(render()).not.toContain("label-short");
    expect(render()).not.toContain(" title=");
  });

  it("sin la cabecera, el tripulante es el primero de los mandos, como antes", () => {
    expect(render({ crew, voice })).toMatch(
      /<div class="strip-controls"><label class="crew-selector">TRIP<\/label><div class="cell read-aloud">VOZ<\/div><\/div><\/header>$/,
    );
  });

  it("todo lo que dice la franja clásica lo dice la cabecera, con las mismas palabras", () => {
    const counts: AlertCounts = { ...none, warning: 1, advisory: 2, unacknowledged: 1, suppressed: 1 };
    const classic = textNodes(render({ counts, crew, voice }));
    const masthead = textNodes(render({ counts, crew, voice, brand }));
    // «EMMA · » delante del título: en la cabecera va en la marca y, para el lector, en el `h1`.
    expect(classic[0]).toBe("EMMA · TITULO · crew-01");
    expect(masthead).toContain("EMMA");
    for (const text of ["TITULO · crew-01", ...classic.slice(1)]) expect(masthead, text).toContain(text);
  });

  it("la campana suma las alertas activas; el globo, solo si hay, con la forma y el color de la clase más grave", () => {
    const quiet = render({ brand });
    expect(quiet).toMatch(spanWithPictogram("mark", "bell", "Alertas"));
    expect(quiet).not.toContain("bell-badge");
    const busy = render({ brand, counts: { ...none, caution: 1, advisory: 2 } });
    expect(busy).toMatch(spanWithPictogram("mark bell-badge num c-yellow", "shape-triangle", "3"));
    // Mientras carga no hay cuenta que dar, y no se pinta una campana a cero.
    expect(render({ brand, loading: true })).not.toContain("masthead-bell");
  });

  it("con `onAlerts` la campana es un mando que lleva a las alertas y dice su cuenta; sin él, la marca de siempre", () => {
    const counts: AlertCounts = { ...none, caution: 1, advisory: 2 };
    const html = render({ brand, counts, onAlerts: () => undefined });
    expect(html).toContain(
      '<button type="button" class="masthead-icon masthead-bell" aria-label="Alertas: 3 activas, ver" title="Alertas: 3 activas, ver">',
    );
    // Lo de dentro no cambia: el dibujo, la palabra y el globo, como en la marca.
    expect(html).toMatch(spanWithPictogram("mark bell-badge num c-yellow", "shape-triangle", "3"));
    expect(render({ brand, counts: { ...none, warning: 1 }, onAlerts: () => undefined })).toContain('aria-label="Alertas: 1 activa, ver"');
    expect(render({ brand, counts })).toContain('<span class="masthead-icon masthead-bell">');
    expect(render({ brand, counts })).not.toMatch(/<button[^>]*masthead-bell/);
    // Mientras carga tampoco hay mando: no hay cuenta que dar.
    expect(render({ brand, loading: true, onAlerts: () => undefined })).not.toContain("masthead-bell");
  });

  it("pulsar la campana llama a `onAlerts`", () => {
    let calls = 0;
    const bell = AlertBell({ counts: none, onOpen: () => (calls += 1) }) as ReactElement<{ type?: string; onClick?: () => void }>;
    expect(bell.type).toBe("button");
    expect(bell.props.type).toBe("button");
    bell.props.onClick?.();
    expect(calls).toBe(1);
    expect((AlertBell({ counts: none }) as ReactElement).type).toBe("span");
  });
});
