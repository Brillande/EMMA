import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, thSign } from "../advisor/visibleText";
import type {
  BaselineIndicator,
  BaselinePersonalData,
  BaselineProfile,
  BaselineState,
  FlightDirection,
  FlightDirectionIndicator,
} from "../lib/api";
import { LookContext } from "../components/BoardOnly";
import { FAILURE_MARK, type RequestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { BaselineProfileView } from "./BaselineProfilePanel";
import { addressesIn } from "../lib/urlWrapMarkup";

/**
 * El perfil de línea base (especificación §3, §10): se pinta lo que da el backend. Los textos de
 * prueba son marcadores, no frases de verdad: si la interfaz redactara algo propio en su sitio,
 * el marcador no saldría.
 */
const state = (overrides: Partial<BaselineState> = {}): BaselineState => ({
  context: "rest",
  context_display: "ESTADO-REPOSO",
  latest: false,
  reading_effective: "2026-11-14T08:00:00+00:00",
  window: { start: "2026-10-30T20:00:00+00:00", end: "2026-11-13T20:00:00+00:00" },
  drawn_from: "state",
  drawn_from_display: "DE-SU-ESTADO",
  established: true,
  status_display: "PALABRA-ESTABLECIDA",
  samples: 1234,
  min_samples: 100,
  median: 64.1,
  spread: 2.63,
  decimals: 0,
  danger_limit: { low: 40, high: 110, text: "LIMITE-DEL-BACKEND" },
  judged_against: "CONTRA-PERCENTILES",
  composition: { samples: 1234, evidence_context: { simulated: 1200, iss: 34 }, observation_type: { measured: 1234 } },
  composition_display: "MEZCLA-DEL-BACKEND",
  cuts: [
    { severity: "mild", display: "leve", quantile: 0.99, min_samples: 100, applies: true, high: 88.4, low: 52.1, text: "CORTE-LEVE" },
    { severity: "severe", display: "grave", quantile: 0.999, min_samples: 1000, applies: true, high: 95.2, low: 48.3, text: "CORTE-GRAVE" },
  ],
  cuts_note: null,
  ...overrides,
});

const learning = state({
  context: "sleep",
  context_display: "ESTADO-SUENO",
  latest: true,
  drawn_from: "family",
  drawn_from_display: "DE-SU-FAMILIA",
  established: false,
  status_display: "PALABRA-APRENDIZAJE",
  samples: 84,
  median: null,
  spread: null,
  judged_against: "MIENTRAS-APRENDE",
  composition: null,
  composition_display: "NO-SE-SABE-DE-QUE",
  cuts: [],
});

const indicator = (states: BaselineState[]): BaselineIndicator => ({
  key: "heart-rate",
  display: "Heart rate",
  display_es: "NOMBRE-FC",
  domain: "cardiovascular",
  unit: "/min",
  established: false,
  reference: { low: 50, high: 100, basis: "observed", text: "RANGO-DEL-CATALOGO" },
  states,
  unattributed_readings: 0,
  unattributed_display: null,
});

const flightRow = (overrides: Partial<FlightDirectionIndicator> = {}): FlightDirectionIndicator => ({
  key: "heart-rate",
  display_es: "NOMBRE-FC",
  direction: "unchanged",
  direction_display: "PALABRA-SENTIDO",
  text: "TEXTO-SENTIDO",
  scope: "ALCANCE-SENTIDO",
  searched: null,
  searched_display: null,
  searched_sources: [],
  searched_read_on: [],
  searched_extent_text: [],
  statements: [
    {
      id: "s1",
      direction: "unchanged",
      direction_display: "PALABRA-FRASE",
      quote: "QUOTE",
      quote_display: "FRASE-LEIDA",
      literal: "QUOTE",
      compared_with: "x",
      compared_with_display: "FRENTE-A",
      population: "POBLACION",
      where: "DONDE",
      ref: "ficha",
      source: "CITA-FUENTE",
      url: null,
      read_on: "2026-10-22",
      extent: "partial",
      extent_text: "ALCANCE-LECTURA",
    },
  ],
  ...overrides,
});

const PERSONAL: BaselinePersonalData = {
  no_field: ["edad"],
  statement: "SEXO-APARTE-EDAD-SIN-CAMPO",
  cycle: "SOLO-DECIDE-EL-CICLO",
  radiation: "LIMITE-IGUAL-PARA-TODOS",
  elsewhere: "DONDE-LA-NORMA-SI",
  privacy: "PRIVACIDAD-12",
  source: { id: "nasa-std-3001-vol1-rev-c", title: "TITULO-NORMA", url: "https://example.org/norma.pdf", relevance: "V1-4030" },
};

const NO_FLIGHT: FlightDirection = { note: "NOTA-VUELOS", statement: "CUENTA-VUELOS", read_on: "2026-10-22", indicators: [] };

const body = (
  indicators: BaselineIndicator[],
  descriptive: BaselineProfile["descriptive"] = [],
  flight: FlightDirection = NO_FLIGHT,
): BaselineProfile => ({
  subject: "crew-01",
  reference_time: "2026-11-14T08:00:00+00:00",
  until: null,
  kind: "rolling",
  method: "METODO-DEL-BACKEND",
  cuts_method: "CORTES-DEL-BACKEND",
  fixed_note: "NOTA-BASE-FIJA",
  window_days: 14,
  lag_hours: 12,
  min_samples: 100,
  statement: "RECUENTO-DEL-BACKEND",
  indicators,
  descriptive,
  flight_direction: flight,
  personal_data: PERSONAL,
});

const FAILED: RequestOutcome = { mark: FAILURE_MARK, text: "MOTIVO" };
const render = (data: BaselineProfile | null, unavailable: RequestOutcome | null = null) =>
  renderToStaticMarkup(createElement(BaselineProfileView, { data, unavailable }));

describe("perfil de línea base", () => {
  const html = render(
    body([indicator([learning, state()])], [{ key: "nasa-tlx-workload", display_es: "NOMBRE-TLX", reason: "SIN-BASE-PORQUE" }]),
  );

  it("pinta las frases del backend tal cual", () => {
    for (const text of [
      "RECUENTO-DEL-BACKEND",
      "METODO-DEL-BACKEND",
      "NOTA-BASE-FIJA",
      "ESTADO-REPOSO",
      "ESTADO-SUENO",
      "PALABRA-ESTABLECIDA",
      "PALABRA-APRENDIZAJE",
      "DE-SU-FAMILIA",
      "LIMITE-DEL-BACKEND",
      "CONTRA-PERCENTILES",
      "MIENTRAS-APRENDE",
      "RANGO-DEL-CATALOGO",
      "SIN-BASE-PORQUE",
    ]) {
      expect(html).toContain(text);
    }
    // La procedencia solo se dice cuando la base es prestada de la familia.
    expect(html).not.toContain("DE-SU-ESTADO");
  });

  // Lote «muestra» (2026-11-08): en el tablero, el método y los plegables van detrás de «Ver
  // detalle»; el recuento y los indicadores sin base («no disponible») nunca se pliegan.
  it("en el tablero, a la vista el recuento y lo no disponible; el método, en el detalle", () => {
    const toggle = html.indexOf("Ver detalle: método y tablas de la base");
    expect(toggle).toBeGreaterThan(0);
    expect(html.indexOf("RECUENTO-DEL-BACKEND")).toBeLessThan(toggle);
    expect(html.indexOf("NOMBRE-TLX")).toBeLessThan(toggle);
    expect(html.indexOf("METODO-DEL-BACKEND")).toBeGreaterThan(toggle);
    expect(html.indexOf("SEXO-APARTE-EDAD-SIN-CAMPO")).toBeGreaterThan(toggle);
    const classic = renderToStaticMarkup(
      createElement(
        LookContext.Provider,
        { value: "classic" },
        createElement(BaselineProfileView, { data: body([indicator([state()])]), unavailable: null }),
      ),
    );
    expect(classic).not.toContain("Ver detalle");
    expect(classic).toContain("METODO-DEL-BACKEND");
  });

  it("las cifras pasan por format, con su unidad", () => {
    expect(html).toContain('<span class="num">64</span> /min');
    expect(html).toContain('dispersión <span class="num">2,6</span> /min');
    expect(html).toContain('<span class="num">1234 de 100</span> lecturas');
  });

  it("en aprendizaje no hay mediana: en su sitio, contra qué se juzga", () => {
    expect(html).toContain('<td class="secondary">MIENTRAS-APRENDE</td>');
    // Y el respaldo de una base en aprendizaje no repite la frase.
    expect(html.match(/MIENTRAS-APRENDE/g)).toHaveLength(1);
  });

  it("sin color: una base en aprendizaje no es un aviso; los descriptivos, «no disponible»", () => {
    const colors = html.match(/c-[a-z]+/g) ?? [];
    expect(colors).toEqual(["c-gray"]);
    expect(html).toMatch(markedHtml("slash-circle", "NOMBRE-TLX", "gray"));
  });

  it("título, plegables y cabeceras con el signo de su concepto", () => {
    expect(html).toMatch(taggedPictogram("h2", uiPictogram("baseline"), "Línea base personal</h2>"));
    expect(html).toMatch(taggedPictogram("summary", uiPictogram("byIndicator"), "Por indicador y estado"));
    expect(html).toMatch(taggedPictogram("summary", uiPictogram("range"), "Rango del catálogo, por indicador</summary>"));
    const headers: [Parameters<typeof uiPictogram>[0], string][] = [
      ["indicator", "Indicador"],
      ["state", "Estado"],
      ["baseline", "Base"],
      ["value", "Mediana y dispersión"],
      ["limits", "Respaldo"],
    ];
    for (const [concept, word] of headers) {
      expect(html).toMatch(thSign(uiPictogram(concept), `${word}</span></th>`, ' scope="col"'));
    }
    expect(html).not.toMatch(/<th scope="col">[^<]/);
  });

  it("el indicador va una vez, sobre todos sus estados, y el de la última lectura primero", () => {
    expect(html.match(/NOMBRE-FC/g)).toHaveLength(2); // la tabla y la lista de rangos
    // `renderToStaticMarkup` deja el atributo como lo escribe React.
    expect(html).toContain('<td rowSpan="2">');
    expect(html.indexOf("ESTADO-SUENO")).toBeLessThan(html.indexOf("ESTADO-REPOSO"));
  });

  it("un indicador sin estado atribuible sale con el motivo del backend", () => {
    const lost = render(body([{ ...indicator([]), unattributed_readings: 2, unattributed_display: "SIN-ATRIBUIR" }]));
    expect(lost).toContain("NOMBRE-FC");
    expect(lost).toContain('<td colSpan="4" class="secondary">SIN-ATRIBUIR</td>');
    const some = render(body([{ ...indicator([state()]), unattributed_readings: 1, unattributed_display: "SIN-ATRIBUIR" }]));
    expect(some).toContain('<div class="secondary">SIN-ATRIBUIR</div>');
  });

  it("sin datos dice por qué; cargando, la flecha que gira", () => {
    expect(render(null, FAILED)).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
    expect(render(null)).toMatch(markedHtml("refresh", "Cargando…"));
  });

  it("si la última lectura falló, las cifras de antes van en cursiva", () => {
    expect(html).not.toContain("stale");
    const old = render(body([indicator([state()])]), FAILED);
    expect(old).toContain('<p class="stale">RECUENTO-DEL-BACKEND</p>');
    expect(old).toContain('<span class="num stale">64</span>');
    expect(old).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
  });
});

describe("de qué está hecha la base y dónde corta (§5.37.2)", () => {
  const html = render(body([indicator([learning, state()])]));

  it("los cortes y su nota son frases del backend, y una base en aprendizaje no tiene", () => {
    expect(html).toContain('<div data-baseline-cut="mild">CORTE-LEVE</div>');
    expect(html).toContain('<div data-baseline-cut="severe">CORTE-GRAVE</div>');
    expect(html.match(/data-baseline-cut=/g)).toHaveLength(2);
    const oneSided = render(body([indicator([state({ cuts_note: "SOLO-POR-ABAJO" })])]));
    expect(oneSided).toContain("<div>SOLO-POR-ABAJO</div>");
    // Los cortes van antes del límite de peligro, que se mira haya o no base.
    expect(html.indexOf("CORTE-GRAVE")).toBeLessThan(html.lastIndexOf("LIMITE-DEL-BACKEND"));
  });

  it("la composición, con las palabras de lib/provenance y las cuentas por format", () => {
    expect(html).toContain("simulado");
    expect(html).toContain("ISS");
    expect(html).toContain("MEDIDO");
    expect(html).toContain('<span class="num">1200</span>');
    expect(html).toContain('<span class="num">34</span>');
    // En el orden del backend: el entorno más frecuente primero.
    expect(html.indexOf("simulado")).toBeLessThan(html.indexOf(">ISS<"));
    expect(html).toContain("<div>MEZCLA-DEL-BACKEND</div>");
  });

  it("si no se sabe de qué está hecha, solo la frase del backend", () => {
    expect(html).toContain('<div class="secondary"><div>NO-SE-SABE-DE-QUE</div></div>');
    expect(html.match(/data-baseline-composition/g)).toHaveLength(1);
  });

  it("sin frase cuando no hay nada que decir, y sin color: el entorno describe, no avisa", () => {
    const plain = render(body([indicator([state({ composition_display: null })])]));
    expect(plain).not.toContain("MEZCLA-DEL-BACKEND");
    expect(plain).toContain("data-baseline-composition");
    expect(plain.match(/c-[a-z]+/g) ?? []).toEqual([]);
  });

  it("cómo corta una base es frase del backend, junto al método", () => {
    expect(html).toContain('<p class="secondary">CORTES-DEL-BACKEND</p>');
    expect(html.indexOf("METODO-DEL-BACKEND")).toBeLessThan(html.indexOf("CORTES-DEL-BACKEND"));
  });

  it("si la última lectura falló, cortes, cuentas, rótulos y frases de antes van en cursiva", () => {
    const old = render(body([indicator([state({ cuts_note: "SOLO-POR-ABAJO" })])]), FAILED);
    expect(old).toContain('<div class="stale" data-baseline-cut="mild">CORTE-LEVE</div>');
    expect(old).toContain('<span class="num stale">1200</span>');
    expect(old).toContain('<div class="stale">MEZCLA-DEL-BACKEND</div>');
    expect(old).toContain('<div class="stale">SOLO-POR-ABAJO</div>');
    expect(old).toMatch(/<span class="mark stale"><svg[^>]*>[\s\S]*?<\/svg>simulado<\/span>/);
  });
});

describe("sexo y edad: qué se guarda y para qué (§5.36.19, revisado 2026-11-14)", () => {
  const html = render(body([indicator([state()])]));

  it("pinta las frases y la ficha del backend tal cual, plegadas con el signo de la identidad", () => {
    expect(html).toMatch(taggedPictogram("summary", uiPictogram("identity"), "Sexo y edad</summary>"));
    for (const text of [
      "SEXO-APARTE-EDAD-SIN-CAMPO",
      "SOLO-DECIDE-EL-CICLO",
      "LIMITE-IGUAL-PARA-TODOS",
      "DONDE-LA-NORMA-SI",
      "PRIVACIDAD-12",
      "TITULO-NORMA",
      "https://example.org/norma.pdf",
    ]) {
      expect(html).toContain(text);
    }
  });

  it("también sin indicadores analizados, y sin color: no es una lectura ni un aviso", () => {
    const empty = render(body([]));
    expect(empty).toContain("SEXO-APARTE-EDAD-SIN-CAMPO");
    expect(empty).toContain("SOLO-DECIDE-EL-CICLO");
    const fold = /<details[^>]*data-personal-data[^>]*>[\s\S]*?<\/details>/.exec(html);
    expect(fold).not.toBeNull();
    expect(fold?.[0].match(/c-[a-z]+/g) ?? []).toEqual([]);
  });
});

describe("lo que se observó en otros vuelos, junto a la base", () => {
  const flight: FlightDirection = {
    note: "NOTA-VUELOS",
    statement: "CUENTA-VUELOS",
    read_on: "2026-10-22",
    indicators: [
      flightRow(),
      flightRow({
        key: "cortisol-salivary",
        display_es: "NOMBRE-CORTISOL",
        direction: "no_source",
        direction_display: "PALABRA-SIN-FUENTE",
        text: "TEXTO-SIN-FUENTE",
        scope: null,
        searched: "x",
        searched_display: "BUSCADO-Y-NO",
        searched_sources: ["CITA-DE-LO-BUSCADO"],
        searched_read_on: ["2026-10-23"],
        searched_extent_text: ["CUANTO-SE-LEYO"],
        statements: [],
      }),
    ],
  };
  const html = render(body([indicator([state()])], [], flight));

  it("pinta las palabras, las frases y la fuente del backend tal cual", () => {
    for (const text of [
      "NOTA-VUELOS",
      "CUENTA-VUELOS",
      "PALABRA-SENTIDO",
      "TEXTO-SENTIDO",
      "ALCANCE-SENTIDO",
      "PALABRA-FRASE: FRASE-LEIDA",
      "FRENTE-A POBLACION.",
      'DONDE. CITA-FUENTE (ALCANCE-LECTURA, <span class="num">2026-10-22</span>)',
      "PALABRA-SIN-FUENTE",
      "TEXTO-SIN-FUENTE",
      "BUSCADO-Y-NO",
      // Lo buscado también se leyó un día, y en parte o entero, y lo lleva.
      'CITA-DE-LO-BUSCADO (CUANTO-SE-LEYO, <span class="num">2026-10-23</span>)',
    ]) {
      expect(html).toContain(text);
    }
  });

  it("plegado y con el signo de lo leído en la fuente; sin frases, sin plegable de frases", () => {
    expect(html).toMatch(taggedPictogram("summary", uiPictogram("source"), "En otros vuelos, por indicador</summary>"));
    expect(html).toMatch(taggedPictogram("summary", uiPictogram("sourceText"), "Frases leídas"));
    expect(html).toContain('Frases leídas (<span class="num">1</span>)');
    expect(html.match(/Frases leídas/g)).toHaveLength(1);
  });

  it("sin color: un sentido no es un aviso y «sin fuente» no es «no disponible»", () => {
    expect(html.match(/c-[a-z]+/g) ?? []).toEqual([]);
  });

  it("sin indicadores analizados no hay plegable", () => {
    expect(render(body([indicator([state()])]))).not.toContain("En otros vuelos");
  });
});

// Lo pintado, no el código: toda dirección en monoespaciada lleva `url` y se parte (§5.38.12).
describe("línea base: las direcciones pintadas se parten", () => {
  it("ningún `.num` sin `url` encierra una dirección", () => {
    const { inNum, unwrapped } = addressesIn(render(body([indicator([state()])])));
    expect(inNum).toBeGreaterThan(0);
    expect(unwrapped).toEqual([]);
  });
});
