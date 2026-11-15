import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { taggedPictogram, thSign, textNodes } from "../advisor/visibleText";
import { MISSING_MARK, mark } from "../lib/marks";
import { Chosen } from "./Chosen";
import { Command } from "./Command";
import { FieldLabel } from "./FieldLabel";
import { Fold } from "./Fold";
import { PanelTitle } from "./PanelTitle";
import { Th } from "./Th";
import { Loading } from "./Unavailable";

/**
 * El mobiliario de la interfaz (§5.32 c, §5.33): título, plegable, mando, cabecera y rótulo de
 * campo, cada uno con su signo directo dentro y la palabra detrás. Lo que se promete a las once
 * unidades que los van a usar: el dibujo sale del concepto, no hay `<span>` intermedio, la palabra
 * es el único texto, y el elemento recibe lo demás tal cual.
 */

const render = renderToStaticMarkup;

describe("<PanelTitle>", () => {
  it("un h2 con el dibujo del concepto y la palabra", () => {
    const html = render(createElement(PanelTitle, { concept: "alerts", children: "Alertas activas" }));
    expect(html).toMatch(taggedPictogram("h2", "bell", "Alertas activas"));
    expect(html).toMatch(/<\/svg>Alertas activas<\/h2>$/);
    expect(textNodes(html)).toEqual(["Alertas activas"]);
  });

  it("otro nivel, una clase de color y un pictograma directo", () => {
    const html = render(
      createElement(PanelTitle, { pictogram: "ring-dotted", as: "h3", className: "c-cyan", children: "Sin datos" }),
    );
    expect(html).toMatch(taggedPictogram("h3", "ring-dotted", "Sin datos", ' class="c-cyan"'));
  });
});

describe("<Fold>", () => {
  it("details con el dibujo dentro del summary y el contenido detrás", () => {
    const html = render(createElement(Fold, { concept: "detail", label: "Detalle", children: "CONTENIDO" }));
    expect(html).toMatch(/^<details>/);
    expect(html).toMatch(taggedPictogram("summary", "text-lines", "Detalle"));
    expect(html).toContain("</summary>CONTENIDO</details>");
  });

  it("las props del details van al details y la clase del summary al summary; el signo no se filtra", () => {
    const html = render(
      createElement(Fold, {
        concept: "history",
        label: "La otra vez",
        summaryClassName: "lead",
        className: "past",
        open: true,
        children: "x",
      }),
    );
    expect(html).toMatch(/^<details class="past" open="">/);
    expect(html).toMatch(taggedPictogram("summary", "clock-rewind", "La otra vez", ' class="lead"'));
    expect(html).not.toContain("concept");
  });
});

describe("<Fold mark>", () => {
  it("con la marca de un estado como signo: su color solo en el dibujo, el rótulo sin color", () => {
    const html = render(createElement(Fold, { mark: MISSING_MARK, label: "Sin lectura", children: "x" }));
    expect(html).toMatch(/^<details><summary><svg class="pictogram c-cyan"[^>]*data-pictogram="ring-dotted"/);
    expect(html).toMatch(taggedPictogram("summary", "ring-dotted", "Sin lectura</summary>"));
    expect(html).not.toContain('class="mark');
    expect(textNodes(html)).toEqual(["Sin lectura", "x"]);
  });

  it("una marca sin dibujo no es signo: lanza en vez de dejar el plegable sin él", () => {
    expect(() => render(createElement(Fold, { mark: mark(null, null), label: "x", children: "y" }))).toThrow(RangeError);
  });
});

describe("<Loading>, <Chosen> y la cabecera que une su dibujo a la palabra (§5.33.12)", () => {
  it("cargando: la flecha que gira, sin color, en texto secundario", () => {
    expect(render(createElement(Loading))).toMatch(
      /^<p class="secondary"><span class="mark"><svg[^>]*data-pictogram="refresh"[^]*?<\/svg>Cargando…<\/span><\/p>$/,
    );
  });

  it("ningún panel escribe su copia del párrafo de carga: usa la pieza", () => {
    const sources = Object.entries(
      import.meta.glob("/src/**/*.tsx", { query: "?raw", import: "default", eager: true }),
    ).filter(([path]) => !/\.test\.tsx?$/.test(path) && path !== "/src/components/Unavailable.tsx");
    for (const [path, source] of sources) {
      expect(String(source), path).not.toMatch(/<p className="secondary">\s*<MarkOf mark=\{LOADING_MARK\}>Cargando…/);
    }
  });

  it("el anillo punteado no va en gris en ningún sitio: «no disponible» es el círculo tachado", () => {
    const sources = Object.entries(
      import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }),
    ).filter(([path]) => !/\.test\.tsx?$/.test(path));
    for (const [path, source] of sources) {
      expect(String(source), path).not.toMatch(/mark\("ring-dotted", "gray"\)|pictogram="ring-dotted" color="gray"/);
    }
  });

  it("la opción elegida lleva el anillo con punto; las demás, solo la palabra", () => {
    expect(render(createElement(Chosen, { chosen: true, children: "7 d" }))).toMatch(
      /^<span class="mark"><svg[^>]*data-pictogram="ring-dot"[^]*?<\/svg>7 d<\/span>$/,
    );
    expect(render(createElement(Chosen, { chosen: false, children: "48 h" }))).toBe('<span class="mark">48 h</span>');
  });

  it("la cabecera envuelve dibujo y palabra en un `span.th-sign`, y la palabra no se toca", () => {
    const html = render(createElement(Th, { concept: "person", children: "Quién anota" }));
    expect(html).toMatch(/^<th scope="col"><span class="th-sign"><svg[^>]*data-pictogram="person"[^]*?<\/svg>Quién anota<\/span><\/th>$/);
    expect(textNodes(html)).toEqual(["Quién anota"]);
  });
});

describe("<Command>", () => {
  it("botón de clase command con el dibujo y la palabra, sin type forzado", () => {
    const html = render(createElement(Command, { concept: "add", children: "Añadir" }));
    expect(html).toMatch(taggedPictogram("button", "plus", "Añadir", ' class="command"'));
    expect(html).not.toContain("type=");
  });

  it("hazard añade la cinta, la clase extra va detrás y el resto de props llega al botón", () => {
    const html = render(
      createElement(Command, {
        concept: "suppress",
        hazard: true,
        className: "wide",
        type: "submit",
        disabled: true,
        children: "Suprimir",
      }),
    );
    expect(html).toMatch(/^<button class="command hazard wide" type="submit" disabled="">/);
    expect(html).toMatch(taggedPictogram("button", "bell-slash", "Suprimir", ' class="command hazard wide" type="submit" disabled=""'));
  });
});

describe("<Th>", () => {
  it("cabecera de columna por defecto, con su dibujo", () => {
    const html = render(createElement(Th, { concept: "value", children: "Valor" }));
    expect(html).toMatch(thSign("hash", "Valor", ' scope="col"'));
  });

  it("la de fila lo dice, y las demás props pasan", () => {
    const html = render(createElement(Th, { concept: "time", scope: "row", colSpan: 2, children: "Hora" }));
    expect(html).toMatch(thSign("clock", "Hora", ' scope="row" colSpan="2"'));
  });
});

describe("<FieldLabel>", () => {
  it("un label por defecto, con htmlFor", () => {
    const html = render(createElement(FieldLabel, { concept: "note", htmlFor: "nota", children: "Nota" }));
    expect(html).toMatch(taggedPictogram("label", "pen", "Nota", ' for="nota"'));
  });

  it("como dt o legend, sin for", () => {
    expect(render(createElement(FieldLabel, { concept: "provenance", as: "dt", children: "Procedencia" }))).toMatch(
      taggedPictogram("dt", "stamp", "Procedencia"),
    );
    const legend = render(createElement(FieldLabel, { concept: "zone", as: "legend", htmlFor: "x", children: "Zona" }));
    expect(legend).toMatch(taggedPictogram("legend", "pin", "Zona"));
    expect(legend).not.toContain("for=");
  });

  it("como span, para rotular una lectura que no es campo de formulario (la franja)", () => {
    const html = render(
      createElement(FieldLabel, { concept: "time", as: "span", className: "label", htmlFor: "x", children: "Hora" }),
    );
    expect(html).toMatch(taggedPictogram("span", "clock", "Hora", ' class="label"'));
    expect(html).not.toContain("for=");
  });
});
