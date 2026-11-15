import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { LinkSync } from "../lib/api";
import { LookContext } from "./BoardOnly";
import { LinkSyncPanel } from "./LinkSync";

/*
 * Las piezas del tablero del enlace simulado: lo pendiente de enviar como cifra grande (un 0 es un
 * recuento real y no lleva marca; con cola, el cian de lo que Tierra aún no tiene) y el estado en su
 * píldora con la palabra del backend (caído, con su marca amarilla). La clásica no las monta.
 */
const backlog = (count: number) => ({ count, readings: count, other: 0, first: null, last: null, first_index: null });

const sync = (state: "up" | "down", count: number) =>
  ({
    label: "ROTULO",
    state,
    state_display: `PALABRA-${state}`,
    to_send: backlog(count),
    to_arrive: backlog(0),
    crew_sentence: "FRASE-A-BORDO",
    rule: "REGLA",
    instant_basis: "BASE",
    not_read_by: "NO-LO-LEE",
    not_measured: "NO-SE-MIDE",
    history: [],
  }) as unknown as LinkSync;

const render = (value: LinkSync, look: "classic" | "reference" = "reference") =>
  renderToStaticMarkup(
    createElement(
      LookContext.Provider,
      { value: look },
      createElement(LinkSyncPanel, { sync: value, referenceTime: null, onDeclared: () => Promise.resolve() }),
    ),
  );

describe("<LinkSyncPanel> en el tablero", () => {
  it("arriba y sin cola: la cifra 0 sin marca y la píldora sin color", () => {
    const html = render(sync("up", 0));
    expect(html).toMatch(/<span class="stat-value"><span class="num">0<\/span> <span class="stat-unit">asientos<\/span><\/span><\/div>/);
    expect(html).not.toContain("c-cyan");
    expect(html).toMatch(/<span class="ref-pill board-pill"><span class="mark">[^]*?PALABRA-up<\/span><\/span>/);
  });

  it("con cola: la cifra lleva el cian de lo que Tierra aún no tiene", () => {
    const html = render(sync("up", 7));
    expect(html).toContain('<span class="num">7</span>');
    expect(html).toMatch(/<span class="mark c-cyan"[^>]*>[^]*?Tierra aún no los tiene<\/span>/);
  });

  it("caído: la píldora lleva la marca amarilla del enlace caído y la palabra del backend", () => {
    const html = render(sync("down", 0));
    expect(html).toMatch(/<span class="ref-pill board-pill"><span class="mark c-yellow"[^>]*>[^]*?PALABRA-down<\/span><\/span>/);
  });

  it("la clásica no monta las piezas", () => {
    const html = render(sync("down", 3), "classic");
    expect(html).not.toContain("stat-tile");
    expect(html).not.toContain("board-pill");
    expect(html).toContain("FRASE-A-BORDO");
  });
});
