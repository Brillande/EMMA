import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, pictogramSvg, taggedPictogram, thSign } from "../advisor/visibleText";
import { diaryInstrument } from "../diary/labels";
import type {
  DescriptiveIndicator,
  DescriptiveIndicators,
  DescriptiveMeasure,
  DiaryIndicator,
  InstrumentStatement,
} from "../lib/api";
import { uiPictogram } from "../lib/uiMarks";
import { DescriptiveView } from "./DescriptivePanel";
import { type DescriptiveCard, descriptiveView, instrumentView } from "./descriptive";
import { ApiError } from "../lib/api";
import { type RequestOutcome, requestOutcome } from "../lib/marks";

/** Una lectura que cayó (5xx): la marca de fallo con el motivo tal cual (§5.34.14). */
const down = (text: string): RequestOutcome => requestOutcome(new ApiError(503, text));

/**
 * Los indicadores descriptivos: se firman y se enseñan, pero el estado no los lee. Los textos
 * de prueba son marcadores, no frases de verdad: aquí no se redacta nada, se pinta lo que da el
 * backend, sin color de nivel y con las frases en el idioma de su fuente.
 */
const statement = (id: string): InstrumentStatement => ({
  id,
  label: `ROTULO-${id}`,
  quote: `FRASE-${id}`,
  ref: "hrp-sans-evidence-report",
  source: "CITA-DE-LA-FUENTE",
  title: "TITULO",
  url: "https://humanresearchroadmap.nasa.gov/informe.pdf",
  where: "V.A.5 · página 27",
  read_on: "2026-10-16",
  extent: "partial",
  extent_text: "leído en parte",
});

const measure = (over: Partial<DescriptiveMeasure> = {}): DescriptiveMeasure => ({
  instrument: "INSTRUMENTO",
  language: "en",
  scope: "ALCANCE-DEL-BACKEND",
  statements: [statement("pregunta"), statement("categorias")],
  categories: [
    { value: 1, literal: "CATEGORIA-LEVE", statement: "categorias" },
    { value: 2, literal: "CATEGORIA-MODERADA", statement: "categorias" },
  ],
  numbering: "NUMERACION-DE-EMMA",
  sources: [
    {
      ref: "hrp-sans-evidence-report",
      title: "TITULO",
      source: "CITA-DE-LA-FUENTE",
      url: "https://humanresearchroadmap.nasa.gov/informe.pdf",
      extent: "partial",
      extent_text: "leído en parte",
      what: "LO-LEIDO",
    },
  ],
  not_found: ["NO-ENCONTRADO"],
  ...over,
});

const indicator = (over: Partial<DescriptiveIndicator> = {}): DescriptiveIndicator => ({
  key: "vision-change",
  display: "LOINC-NAME-IN-ENGLISH",
  display_es: "TITULO-DEL-INDICADOR",
  domain: "neuro-ocular",
  domain_display: "neuro-ocular",
  unit: "{score}",
  unit_display: "puntos",
  decimals: 0,
  range_text: "RANGO-DEL-BACKEND",
  system: "https://emma.mission/codes",
  system_display: "código propio de EMMA",
  code: "vision-change",
  code_basis: { kind: "own", text: "PORQUE-DEL-CODIGO", loinc: null, searched: "LO-BUSCADO" },
  equipment: "autoinforme",
  how_recorded: { route: "/api/diary/entries", text: "COMO-SE-REGISTRA" },
  instrument: measure(),
  count: 0,
  shown: 0,
  readings: [],
  ...over,
});

const vo2 = (): DescriptiveIndicator =>
  indicator({
    key: "vo2-peak",
    display: "VO2-PEAK",
    display_es: "VO2-PICO",
    system: "http://loinc.org",
    system_display: "LOINC",
    code: "94122-9",
    code_basis: {
      kind: "loinc",
      text: "FICHA-LOINC-LEIDA",
      loinc: {
        component: "Oxygen consumption/Body weight^peak during exercise",
        property: "VRatCnt",
        system: "^Patient",
        scale: "Qn",
        method: null,
        example_ucum: "mL/min/kg{body_wt}",
        status: "ACTIVE",
        version: "2.82",
        read_on: "2026-10-16",
        url: "https://tx.fhir.org/consulta",
      },
      searched: null,
    },
    how_recorded: { route: "/api/observations", text: "POR-LA-INGESTA" },
    instrument: measure({ categories: [], numbering: null }),
    count: 3,
    shown: 2,
    readings: [
      {
        effective: "2026-12-02T07:00:00+00:00",
        value: 35.25,
        value_text: "CIFRA-DEL-BACKEND",
        source: "manual",
        source_display: "PROCEDENCIA",
        recorded_by: null,
        recorded_by_display: "NO-CONSTA",
        observation_type: "measured",
        evidence_context: "ground",
      },
      {
        effective: "2026-12-01T07:00:00+00:00",
        value: 36,
        value_text: "OTRA-CIFRA",
        source: "manual",
        source_display: "PROCEDENCIA",
        recorded_by: null,
        recorded_by_display: "NO-CONSTA",
        observation_type: "measured",
        evidence_context: "ground",
      },
    ],
  });

const body = (indicators: DescriptiveIndicator[]): DescriptiveIndicators => ({
  subject: "crew-01",
  decided_on: "2026-10-15",
  scope: "ALCANCE-GENERAL",
  statement: "RECUENTO-DEL-BACKEND",
  indicators,
});

/** Las dos tarjetas de la prueba: la del código propio y la del LOINC. */
function twoCards(): [DescriptiveCard, DescriptiveCard] {
  const [own, loinc] = descriptiveView(body([indicator(), vo2()])).cards;
  if (own === undefined || loinc === undefined) throw new Error("faltan tarjetas");
  return [own, loinc];
}

describe("indicadores descriptivos, preparados", () => {
  it("dice el código y por qué es ese, como lo escribe el backend", () => {
    const view = descriptiveView(body([indicator(), vo2()]));
    expect(view.statement).toBe("RECUENTO-DEL-BACKEND");
    expect(view.scope).toBe("ALCANCE-GENERAL");
    const [own, loinc] = twoCards();
    expect(own.domainKey).toBe("neuro-ocular");
    expect(own.domain).toBe("neuro-ocular");
    expect(own.code).toBe("código propio de EMMA · vision-change");
    expect(own.codeBasis).toBe("PORQUE-DEL-CODIGO");
    expect(own.searched).toBe("LO-BUSCADO");
    expect(own.loincUrl).toBeNull();
    expect(loinc.code).toBe("LOINC 94122-9");
    expect(loinc.codeBasis).toBe("FICHA-LOINC-LEIDA");
    expect(loinc.loincUrl).toBe("https://tx.fhir.org/consulta");
    expect(loinc.searched).toBeNull();
    expect(loinc.how).toBe("POR-LA-INGESTA");
  });

  it("titula cada indicador con el nombre en español del backend, no con el de LOINC", () => {
    const [own, loinc] = twoCards();
    expect(own.title).toBe("TITULO-DEL-INDICADOR");
    expect(loinc.title).toBe("VO2-PICO");
  });

  it("cuenta lo que consta y dice cuándo la lista no lo trae todo", () => {
    const [own, loinc] = twoCards();
    expect(own.count).toBe("Sin lecturas");
    expect(own.rows).toEqual([]);
    expect(loinc.count).toBe("3 lecturas");
    expect(loinc.shown).toBe("Las 2 últimas de 3.");
    expect(loinc.rows.map((row) => row.value)).toEqual(["CIFRA-DEL-BACKEND", "OTRA-CIFRA"]);
    expect(loinc.rows.map((row) => row.recordedBy)).toEqual(["NO-CONSTA", "NO-CONSTA"]);
  });

  it("copia cada categoría tal cual, con el número de EMMA y la nota que lo dice", () => {
    const view = instrumentView(measure(), "vision-change");
    expect(view.categories).toEqual([
      { key: "vision-change-1", point: "1", literal: "CATEGORIA-LEVE" },
      { key: "vision-change-2", point: "2", literal: "CATEGORIA-MODERADA" },
    ]);
    expect(view.numbering).toBe("NUMERACION-DE-EMMA");
    expect(view.quotes.map((item) => item.quote)).toEqual(["FRASE-pregunta", "FRASE-categorias"]);
    expect(view.notFound).toEqual(["NO-ENCONTRADO"]);
  });
});

describe("el panel", () => {
  const html = renderToStaticMarkup(
    createElement(DescriptiveView, { data: body([indicator(), vo2()]), unavailable: null }),
  );

  it("no lleva color ni pictograma de nivel: no avisa de nada", () => {
    for (const level of ["c-red", "c-yellow", "c-blue", "c-green", "c-magenta"]) {
      expect(html).not.toContain(level);
    }
    expect(html).not.toContain('data-pictogram="shape-circle"');
    expect(html).not.toContain('data-pictogram="shape-triangle"');
  });

  it("cada nombre con el dibujo de su familia y cada dominio con el suyo, sin color", () => {
    // El cuestionario de visión: ojo con su nervio. El VO2 pico: mancuerna (forma física).
    expect(html).toMatch(new RegExp(`<h3><span class="mark">${pictogramSvg("eye-nerve")}TITULO-DEL-INDICADOR</span></h3>`));
    expect(html).toMatch(new RegExp(`<h3><span class="mark">${pictogramSvg("dumbbell")}VO2-PICO</span></h3>`));
    // El dominio, con la palabra del backend (`domain_display`) al lado del dibujo.
    expect(html).toMatch(new RegExp(` · <span class="mark">${pictogramSvg("domain-neuro-ocular")}neuro-ocular</span> · RANGO-DEL-BACKEND`));
    // Dos en las fichas del detalle y uno en el recuento por dominio del tablero.
    expect(html.match(/data-pictogram="domain-neuro-ocular"/g)).toHaveLength(3);
  });

  it("pinta las frases y las categorías en el idioma de su fuente", () => {
    expect(html).toContain('<q lang="en">FRASE-categorias</q>');
    expect(html).toContain('<span lang="en">CATEGORIA-LEVE</span>');
    expect(html).toContain("NUMERACION-DE-EMMA");
    expect(html).toContain("Buscado y no encontrado: NO-ENCONTRADO");
  });

  it("enseña lo que consta, con quién lo anotó o que no consta", () => {
    expect(html).toContain("CIFRA-DEL-BACKEND");
    expect(html).toContain("NO-CONSTA");
    expect(html).toContain("Las 2 últimas de 3.");
    expect(html).toContain("RECUENTO-DEL-BACKEND");
  });

  it("sin datos dice por qué, en cian", () => {
    const empty = renderToStaticMarkup(
      createElement(DescriptiveView, { data: null, unavailable: down("MOTIVO"), onReread: () => undefined }),
    );
    expect(empty).toMatch(
      new RegExp(`<p><span class="mark c-red">${pictogramSvg("cross")}Sin datos: MOTIVO</span></p>`),
    );
    // El mando de volver a leer sigue ahí, también sin datos: desde la segunda pasada es un
    // `Command` (`button.command`) con la flecha que gira de «volver a leer» (§5.33.7).
    expect(empty).toMatch(
      taggedPictogram("button", uiPictogram("reread"), "Volver a leer</button>", ' class="command" type="button"'),
    );
  });

  it("título, plegable, cabeceras y carga con el signo de su concepto (§5.33.7)", () => {
    expect(html).toMatch(taggedPictogram("h2", uiPictogram("descriptive"), "Indicadores descriptivos</h2>"));
    expect(html).toMatch(
      taggedPictogram("summary", uiPictogram("sourceText"), "Lo leído de su medida: INSTRUMENTO</summary>"),
    );
    const headers: [Parameters<typeof uiPictogram>[0], string][] = [
      ["time", "Hora"],
      ["value", "Valor"],
      ["provenance", "Procedencia"],
      ["person", "Quién anota"],
    ];
    for (const [concept, word] of headers) {
      expect(html).toMatch(thSign(uiPictogram(concept), `${word}</span></th>`, ' scope="col"'));
    }
    expect(html).not.toMatch(/<th scope="col">[^<]/);
    const loading = renderToStaticMarkup(createElement(DescriptiveView, { data: null, unavailable: null }));
    expect(loading).toMatch(markedHtml("refresh", "Cargando…"));
    expect(loading).not.toContain("Sin datos");
  });

  it("lo que falta lleva la marca de la tabla F.5-1, que no es de nivel", () => {
    // Sin lecturas: dato ausente, cian con el anillo punteado.
    expect(html).toMatch(new RegExp(`<p>${markedHtml("ring-dotted", "Sin lecturas", "cyan").source}</span></p>`));
    // Una lectura sin quién la anotó: «no disponible», la misma marca que en el diario.
    expect(html).toMatch(markedHtml("slash-circle", "NO-CONSTA", "gray"));
    // Con lecturas, el recuento va tal cual, sin marca (el `<p>` exacto lo fija).
    expect(html).toContain("<p>3 lecturas</p>");
    // El recuento general: con alguna lectura, tal cual; sin ninguna, con la marca de registro
    // vacío, sin color (§5.34.14): el cian queda para la tarjeta de un indicador sin lecturas.
    expect(html).toContain("<p>RECUENTO-DEL-BACKEND</p>");
    const none = renderToStaticMarkup(
      createElement(DescriptiveView, { data: body([indicator()]), unavailable: null }),
    );
    expect(none).toMatch(new RegExp(`<p>${markedHtml("ring-dotted", "RECUENTO-DEL-BACKEND").source}</span></p>`));
  });

  it("si la última lectura falló, las cifras de antes van en cursiva: caducadas", () => {
    expect(html).not.toContain("stale");
    const old = renderToStaticMarkup(
      createElement(DescriptiveView, { data: body([indicator(), vo2()]), unavailable: down("MOTIVO") }),
    );
    expect(old).toContain('<td class="num stale">CIFRA-DEL-BACKEND</td>');
    // Y el recuento y la nota de cuántas trae, que también son cifras de antes.
    expect(old).toContain('<p class="stale">3 lecturas</p>');
    expect(old).toContain('<p class="secondary stale">Las 2 últimas de 3.</p>');
    expect(old).toMatch(markedHtml("ring-dotted", "Sin lecturas", "cyan", "stale"));
    expect(old).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
  });
});

describe("el tablero de los descriptivos (segunda ronda, 2026-11-08)", () => {
  // Del mismo dominio, uno sin lecturas (el cuestionario) y uno con tres (el VO2 pico); y otro de
  // otro dominio, sin lecturas.
  const html = renderToStaticMarkup(
    createElement(DescriptiveView, {
      data: body([
        indicator(),
        vo2(),
        indicator({ key: "grip-right", display_es: "PRENSION", domain: "musculoskeletal", domain_display: "musculoesquelético" }),
      ]),
      unavailable: null,
    }),
  );
  const summary = html.split('<ul class="descriptive-groups"')[1]!.split("</ul>")[0]!;

  it("arriba, cada dominio con cuántos tiene, cuántos con lecturas y los sin lecturas con su marca", () => {
    const groups = summary.split("<li ").slice(1);
    expect(groups).toHaveLength(2);
    expect(groups[0]).toContain('data-descriptive-group="neuro-ocular"');
    expect(groups[0]).toContain('<span class="num secondary">(2)</span>');
    expect(groups[0]).toContain('con lecturas <span class="num">1</span>');
    expect(groups[0]).toMatch(markedHtml("ring-dotted", 'sin lecturas <span class="num">1</span>', "cyan"));
    expect(groups[1]).toContain('data-descriptive-group="musculoskeletal"');
    expect(groups[1]).toContain('con lecturas <span class="num">0</span>');
  });

  it("los mosaicos de uno en uno, con su marca de sin lecturas, en su «Ver detalle»", () => {
    const at = html.indexOf("Ver detalle: recuento de cada indicador");
    expect(at).toBeGreaterThan(-1);
    expect(html.indexOf('data-descriptive="vision-change"')).toBeGreaterThan(at);
    const detail = html.slice(at);
    expect(detail).toMatch(/class="board-detail-body" hidden="">\s*<div class="descriptive-tiles">/);
    expect(detail).toMatch(markedHtml("ring-dotted", "Sin lecturas", "cyan"));
  });
});

describe("el diario", () => {
  const diaryIndicator = (scale: Partial<NonNullable<DiaryIndicator["scale"]>>): DiaryIndicator => ({
    key: "vision-change",
    display: "TITULO",
    display_es: "TITULO",
    unit: "{score}",
    unit_display: "puntos",
    domain: "neuro-ocular",
    decimals: 0,
    physical_min: 0,
    physical_max: 3,
    range_text: "de 0 a 3",
    equipment: "autoinforme",
    mode_display: null,
    scale: {
      described_as: null,
      labels: null,
      labels_status: "instrument",
      labels_note: "NOTA",
      instrument: measure(),
      concerning: "high",
      concerning_note: "DESCRIPTIVO",
      ...scale,
    },
    descriptive_only: true,
  });

  it("enseña el instrumento leído de un descriptivo, con sus categorías", () => {
    const view = diaryInstrument(diaryIndicator({}));
    expect(view?.categories.map((item) => item.literal)).toEqual([
      "CATEGORIA-LEVE",
      "CATEGORIA-MODERADA",
    ]);
  });

  it("no lo enseña en una escala leída o propia, ni sin frases", () => {
    expect(diaryInstrument(diaryIndicator({ labels_status: "read" }))).toBeNull();
    expect(diaryInstrument(diaryIndicator({ labels_status: "own" }))).toBeNull();
    expect(diaryInstrument(diaryIndicator({ instrument: null }))).toBeNull();
    expect(diaryInstrument(diaryIndicator({ instrument: measure({ statements: [] }) }))).toBeNull();
  });
});
