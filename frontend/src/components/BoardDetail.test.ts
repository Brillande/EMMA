import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { BoardDetail } from "./BoardDetail";
import { LookContext } from "./BoardOnly";

/** «Ver detalle» del tablero: cerrado en la concha nueva, tal cual en la clásica, sin quitar texto. */

const render = (look: "reference" | "classic", label?: string) =>
  renderToStaticMarkup(
    createElement(
      LookContext.Provider,
      { value: look },
      createElement(BoardDetail, {
        ...(label === undefined ? {} : { label }),
        children: createElement("p", null, "Regla de la fuente."),
      }),
    ),
  );

describe("<BoardDetail>", () => {
  it("en la concha nueva: mando cerrado y el texto dentro, oculto pero presente", () => {
    const html = render("reference", "reglas");
    expect(html).toMatch(/<button class="command board-detail-toggle" type="button" aria-expanded="false" aria-controls="([^"]+)">/);
    expect(html).toContain("Ver detalle: reglas</button>");
    const controls = /aria-controls="([^"]+)"/.exec(html)?.[1];
    expect(html).toContain(`<div id="${controls}" class="board-detail-body" hidden=""><p>Regla de la fuente.</p></div>`);
  });

  it("sin rótulo, «Ver detalle» a secas", () => {
    expect(render("reference")).toContain("Ver detalle</button>");
  });

  it("en la clásica, los hijos tal cual: ni mando ni envoltorio", () => {
    expect(render("classic", "reglas")).toBe("<p>Regla de la fuente.</p>");
  });

  it("no es un pliegue del inventario: ni details, ni section, ni data-ui", () => {
    const html = render("reference", "reglas");
    expect(html).not.toMatch(/<details|<section|data-ui=/);
  });
  it("en la hoja: enlace fino con chevrón, alto táctil intacto y cerrados en fila", () => {
    const css = readFileSync(fileURLToPath(new URL("../shell/board.css", import.meta.url)), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "");
    const rules = [...css.matchAll(/([^{}]*\.board-detail[^{}]*)\{([^}]*)\}/g)].map(([, selector, body]) => ({
      selector: (selector ?? "").trim(),
      body: body ?? "",
    }));
    const toggle = rules.find((rule) => rule.selector.endsWith("button.command.board-detail-toggle[aria-expanded]"));
    expect(toggle?.body).toMatch(/border-color: transparent;/);
    expect(toggle?.body).toMatch(/background: none;/);
    // Ni ancho completo ni un alto propio: el de `button.command` (`--touch`) se queda; y el foco, el de siempre.
    for (const rule of rules) {
      expect(rule.body, rule.selector).not.toMatch(/(?:^|[;\s])(?:width: 100%|min-height:|height:)/);
      expect(rule.body, rule.selector).not.toMatch(/outline/);
    }
    // El chevrón cerrado, en línea (sin `display`): pegado a la última palabra, sin corte entre ambos.
    const chevron = rules.find((rule) => rule.selector.endsWith("[aria-expanded]::after"));
    expect(chevron?.body).toMatch(/content: "›" \/ "";/);
    expect(chevron?.body).not.toMatch(/display:/);
    const closed = rules.find((rule) => rule.selector.includes(".board-detail:has(> .board-detail-body[hidden])"));
    expect(closed?.body).toMatch(/display: inline-block;/);
  });
});
