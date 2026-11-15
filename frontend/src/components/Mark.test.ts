import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import {
  FAILURE_MARK,
  LOADING_MARK,
  OK_MARK,
  UNAVAILABLE_MARK,
  UNKNOWN_MARK,
  mark,
} from "../lib/marks";
import { Mark, MarkOf } from "./Mark";

/**
 * La marca: pictograma junto a la palabra, con el color del significado (F.5.10 e). Lo que se
 * promete a las unidades que la usan: la clase exacta, el hueco en CSS y no en el texto, la
 * palabra como unico texto, y el parpadeo solo sobre el dibujo.
 */

const render = (props: Omit<Parameters<typeof Mark>[0], "children">, word: string) =>
  renderToStaticMarkup(createElement(Mark, { ...props, children: word }));

describe("<Mark>", () => {
  it("pictograma y palabra, sin color: class=\"mark\"", () => {
    const html = render({ pictogram: "shape-circle" }, "PALABRA");
    expect(html).toMatch(/^<span class="mark"><svg class="pictogram" .*<\/svg>PALABRA<\/span>$/);
    expect(html).toContain('data-pictogram="shape-circle"');
    expect(textNodes(html)).toEqual(["PALABRA"]);
  });

  it("con color: la clase del token detras, y una clase propia en medio", () => {
    expect(render({ pictogram: "shape-triangle", color: "yellow" }, "P")).toContain(
      '<span class="mark c-yellow">',
    );
    expect(render({ pictogram: "shape-square", color: "red", className: "level" }, "P")).toContain(
      '<span class="mark level c-red">',
    );
    expect(render({ pictogram: "shape-circle", className: "obs-type" }, "P")).toContain(
      '<span class="mark obs-type">',
    );
  });

  it("sin pictograma, solo la palabra", () => {
    const html = render({ pictogram: null, color: null }, "PALABRA");
    expect(html).toBe('<span class="mark">PALABRA</span>');
  });

  it("el hueco con la palabra no es un espacio en el texto", () => {
    const html = render({ pictogram: "shape-circle" }, "PALABRA");
    expect(html).toContain("</svg>PALABRA");
  });

  it("el parpadeo va solo sobre el dibujo, y solo si se pide", () => {
    const flashing = render({ pictogram: "shape-square", color: "red", flashing: true }, "P");
    expect(flashing).toContain('<svg class="pictogram flash"');
    expect(flashing).toMatch(/^<span class="mark c-red">/);
    expect(render({ pictogram: "shape-square", color: "red" }, "P")).not.toContain("flash");
  });

  it("el `title` va en el span, no en el svg", () => {
    const html = render({ pictogram: "dot-filled", title: "significado" }, "MEDIDO");
    expect(html).toContain('<span class="mark" title="significado">');
    expect(html).not.toMatch(/<svg[^>]*title=/);
  });

  it("caducado: la clase stale entre la propia y el color, y solo si se pide", () => {
    expect(render({ pictogram: "ring-dotted", color: "cyan", stale: true, className: "x" }, "P")).toContain(
      '<span class="mark x stale c-cyan">',
    );
    expect(render({ pictogram: "ring-dotted", color: "cyan" }, "P")).not.toContain("stale");
  });
});

describe("<MarkOf>", () => {
  it("pasa stale a la marca", () => {
    const html = renderToStaticMarkup(createElement(MarkOf, { mark: UNAVAILABLE_MARK, stale: true, children: "P" }));
    expect(html).toMatch(/^<span class="mark stale c-gray"><svg [^>]*data-pictogram="slash-circle"/);
  });
});

describe("mark() y UNKNOWN_MARK (lib/marks.ts)", () => {
  it("la clase sale del token; sin token no hay clase", () => {
    expect(mark("ring-dotted", "cyan")).toEqual({ pictogram: "ring-dotted", color: "cyan", className: "c-cyan" });
    expect(mark("check", null)).toEqual({ pictogram: "check", color: null, className: undefined });
    expect(mark(null, null)).toEqual({ pictogram: null, color: null, className: undefined });
  });

  it("un estado desconocido lleva un punto y texto normal: ningun significado", () => {
    expect(UNKNOWN_MARK).toEqual({ pictogram: "dot-small", color: "text", className: "c-text" });
  });
});

describe("las marcas de los estados de un panel (segunda pasada, §5.33)", () => {
  it("no disponible en gris con el círculo tachado; fallo en rojo con la cruz", () => {
    expect(UNAVAILABLE_MARK).toEqual(mark("slash-circle", "gray"));
    expect(FAILURE_MARK).toEqual(mark("cross", "red"));
  });

  it("cargando y hecho, sin color: no son alertas", () => {
    expect(LOADING_MARK).toEqual(mark("refresh", null));
    expect(OK_MARK).toEqual(mark("check", null));
  });
});
