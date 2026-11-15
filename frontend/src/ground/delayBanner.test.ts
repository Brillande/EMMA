import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { declaredLinkNotice } from "../habitat/systems";
import { ApiError, type LinkSync } from "../lib/api";
import { requestOutcome } from "../lib/marks";
import { DelayBanner } from "./GroundConsole";

/**
 * La cabecera de la consola de Tierra con el enlace declarado (§5.35.9): la ficha «Tierra tiene
 * datos hasta» lleva la frase corta del backend y el párrafo de debajo la entera, tal cual, con
 * la marca del estado; y antes de que llegue ninguna lectura el enlace se lee de
 * `/api/habitat/systems` con el corte, porque no hay estado recibido del que leerlo.
 */

const HEADLINE = "CORTA-DEL-BACKEND";
const SENTENCE = "ENTERA-DEL-BACKEND con la nota";
const LINK = declaredLinkNotice({
  state: "out-of-service",
  attention: true,
  headline: HEADLINE,
  sentence: SENTENCE,
});

const QUEUE = { count: 0, readings: 0, other: 0, first: null, last: null, first_index: null };
/** El enlace simulado arriba, sin nada que señalar (§5.47); `GROUND` es su frase para Tierra. */
const GROUND = "FRASE-DE-TIERRA-DEL-BACKEND";
const UP: LinkSync = {
  label: "Enlace con Tierra simulado (declarado por una persona)",
  state: "up",
  state_display: "arriba",
  declared: false,
  since: null,
  declared_by: null,
  note: null,
  ledger_index: null,
  light_cut: "2026-11-10T03:46:00+00:00",
  cut: "2026-11-10T03:46:00+00:00",
  held: false,
  held_since: null,
  to_send: QUEUE,
  to_arrive: QUEUE,
  crew_sentence: "a bordo",
  ground_sentence: GROUND,
  rule: "regla",
  not_measured: "no se mide",
  not_read_by: "no lo lee",
  known_only_here: "SOLO-AQUI",
  instant_basis: "instantes",
  history: [],
  version: 0,
  store_epoch: 1,
};
const HELD: LinkSync = {
  ...UP,
  state: "down",
  held: true,
  held_since: "2026-11-09T22:00:00+00:00",
  cut: "2026-11-09T22:00:00+00:00",
};

const banner = (over: Partial<Parameters<typeof DelayBanner>[0]> = {}) =>
  renderToStaticMarkup(
    createElement(DelayBanner, {
      oneWay: 14,
      earthMet: "MET 10/04:00",
      onboardMet: "MET 10/04:14",
      link: LINK,
      linkError: null,
      sync: UP,
      ...over,
    }),
  );

/** El HTML de la ficha de Tierra: del rótulo a la ficha siguiente. */
const earthTile = (html: string) =>
  html.slice(html.indexOf("Tierra tiene datos hasta"), html.indexOf("A bordo ya van por"));

describe("la cabecera de Tierra con el enlace declarado", () => {
  it("la ficha lleva la frase corta y el párrafo de debajo la entera, cada una con el círculo tachado", () => {
    const html = banner();
    expect(earthTile(html)).toContain(HEADLINE);
    expect(earthTile(html)).not.toContain(SENTENCE);
    const below = html.slice(html.indexOf("</div></div>"));
    expect(below).toMatch(
      new RegExp(`<p class="delay-link"><span class="mark c-yellow"><svg [^>]*data-pictogram="slash-circle"[^>]*>.*?</svg>${SENTENCE}</span></p>`),
    );
    expect(html.match(/data-pictogram="slash-circle"/g)).toHaveLength(2);
  });

  it("sin efemérides la ficha lleva su motivo y el enlace va solo en el párrafo, entero", () => {
    const html = banner({ oneWay: null });
    expect(earthTile(html)).not.toContain(HEADLINE);
    expect(earthTile(html)).toContain("Sin efemérides");
    expect(html).toContain(`<p class="delay-link">`);
    expect(html).toContain(SENTENCE);
    expect(html).not.toContain(HEADLINE);
  });

  it("sin nada que señalar no hay frase ni párrafo del enlace", () => {
    const html = banner({ link: null });
    expect(html).not.toContain(HEADLINE);
    expect(html).not.toContain(SENTENCE);
    expect(html).not.toContain("slash-circle");
  });

  it("si no se pudo leer, se dice con la marca que decide `requestOutcome`", () => {
    const failed = banner({ link: null, linkError: requestOutcome(new ApiError(503, "HTTP 503")) });
    const refused = banner({ link: null, linkError: requestOutcome(new ApiError(422, "until")) });
    expect(failed).toMatch(/<span class="mark c-red"><svg [^>]*data-pictogram="cross"[^>]*>.*?<\/svg>No se pudo leer el enlace declarado: HTTP 503<\/span>/);
    expect(refused).toMatch(/<span class="mark c-yellow"><svg [^>]*data-pictogram="[^"]+"[^>]*>.*?<\/svg>No se pudo leer el enlace declarado: until<\/span>/);
  });
});

describe("antes de que llegue ninguna lectura", () => {
  const source = readFileSync(fileURLToPath(new URL("./GroundConsole.tsx", import.meta.url)), "utf8");

  it("el enlace se lee de `/api/habitat/systems` con el corte de Tierra, y el error por `requestOutcome`", () => {
    expect(source).toMatch(/\.habitatSystems\(new Date\(cutKey\)\)/);
    expect(source).toContain("link: overview.declared_link");
    expect(source).toContain("error: requestOutcome(reason)");
    // Lo recibido manda; lo leído antes solo vale para su corte.
    expect(source).toContain("received?.declared_link ?? early?.link");
    expect(source).toMatch(/waiting && beforeAny\?\.cut === cutKey/);
  });

  it("sin efemérides pero con el enlace simulado reteniendo el corte, la ficha da el corte", () => {
    const html = banner({ oneWay: null, sync: HELD });
    expect(earthTile(html)).toContain("MET 10/04:00");
    expect(earthTile(html)).not.toContain("Sin efemérides");
  });
});

describe("la cabecera de Tierra con el enlace simulado (§5.47)", () => {
  it("con el enlace arriba, la frase del backend tal cual y sin marca", () => {
    const html = banner({ link: null });
    expect(html).toContain(`<p class="delay-link">${GROUND} <span class="secondary">SOLO-AQUI</span></p>`);
    expect(html).not.toContain("ring-dotted");
  });

  it("con el corte retenido por el enlace caído, en cian con el anillo punteado (dato caducado)", () => {
    const html = banner({ link: null, sync: HELD });
    expect(html).toMatch(
      new RegExp(`<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?</svg>${GROUND}</span>`),
    );
  });
});
