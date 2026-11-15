import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, textNodes, thSign } from "../advisor/visibleText";
import {
  ApiError,
  type CrewStatus,
  type EvidenceItem,
  type RadiationReading,
  type RadiationScales as Scales,
} from "../lib/api";
import { requestOutcome } from "../lib/marks";
import { RadiationScales } from "./RadiationScales";

/**
 * Radiación en tres escalas (§5.11): cada una con su forma junto a su nombre, tres dibujos
 * distintos; lo que falta en cian con su anillo; el refugio con su casa cuando hay evento. Los
 * textos, las bases y las cifras son del backend; aquí solo se comprueba qué forma va con qué
 * palabra y que ningún color es decorativo.
 */

const status = (over: Partial<Scales> = {}): CrewStatus =>
  ({
    mission: { start: "2026-01-01" },
    radiation: {
      acute: { active_event: null, time_to_action: null },
      mission: null,
      career: { value_msv: null, basis: "BASE-SIN-DOSIS-PREVIA", limit_msv: 600, limit_source: "FUENTE-LIMITE" },
      ...over,
    },
  }) as unknown as CrewStatus;

const render = (crew: CrewStatus, operator = "CDR") =>
  renderToStaticMarkup(
    createElement(RadiationScales, { status: crew, operator, onDeclareProfile: () => Promise.resolve() }),
  );

const event: NonNullable<Scales["acute"]["time_to_action"]> = {
  detected_at: "2026-01-02T01:00:00Z",
  shelter_ready_by: "2026-01-02T02:00:00Z",
  max_stay_until: "2026-01-03T01:00:00Z",
  elapsed_minutes: 30,
  elapsed_note: null,
  basis: "BASE-DEL-PROCEDIMIENTO",
  source: { title: "TITULO", source: "FUENTE-ORION", url: "https://example.invalid/orion" },
};

describe("<RadiationScales>, las tres escalas", () => {
  it("cada escala lleva su forma junto a su nombre, y son tres dibujos distintos", () => {
    const html = render(status());
    expect(html).toMatch(markedHtml("burst", "Aguda"));
    expect(html).toMatch(markedHtml("trefoil", "Esta misión"));
    expect(html).toMatch(markedHtml("bar-capped", "Carrera"));
    const names = [...html.matchAll(/<dt><span class="mark"><svg [^>]*data-pictogram="([a-z-]+)"/g)].map((m) => m[1]);
    expect(names).toEqual(["burst", "trefoil", "bar-capped"]);
  });

  it("sin evento solar activo lo dice en secundario, sin refugio ni cian", () => {
    const html = render(status());
    expect(html).toContain('<span class="secondary">sin evento solar activo</span>');
    expect(html).not.toContain('data-pictogram="house-door"');
    // Tampoco con lo leído (E8), que el backend manda siempre: el fin del refugio va con el libro.
    expect(render(status(readings()))).not.toContain('data-pictogram="house-door"');
  });

  it("con evento: detección, refugio con su casa y permanencia, en tiempo de misión, con la base y la fuente", () => {
    const html = render(status({ acute: { active_event: { event_type: "SEP" }, time_to_action: event } }));
    expect(html).toContain('evento detectado en <span class="num">MET 1/01:00:00</span>');
    expect(html).toMatch(markedHtml("house-door", "refugio"));
    expect(html).toMatch(/refugio<\/span> montado antes de <span class="num">MET 1\/02:00:00<\/span>/);
    expect(html).toContain('permanencia hasta <span class="num">MET 2/01:00:00</span>');
    expect(html).toContain("BASE-DEL-PROCEDIMIENTO.");
    expect(html).toMatch(/<a href="https:\/\/example\.invalid\/orion" target="_blank" rel="noreferrer">FUENTE-ORION<\/a>/);
    // El tipo del evento no se enseña: tampoco se le pone forma.
    expect(html).not.toContain("SEP");
  });

  it("sin tasa de dosis de misión: cian con el anillo; con ella, la cifra rotulada INFERIDO", () => {
    expect(render(status())).toMatch(markedHtml("ring-dotted", "sin tasa de dosis registrada", "cyan"));
    const html = render(
      status({
        mission: {
          value_msv: 12.5,
          absorbed_mgy: 5,
          quality_factor: 2.5,
          hours_covered: 240,
          observation_type: "inferred",
          model_version: "m1",
          basis: "BASE-DE-MISION",
        },
      }),
    );
    expect(html).toContain('<span class="num">12,50</span> mSv');
    expect(html).toContain('data-pictogram="dot-half"');
    expect(html).toContain('<p class="secondary">BASE-DE-MISION</p>');
    expect(html).not.toContain("sin tasa de dosis registrada");
  });

  it("carrera sin dosis previa: cian con la base del backend; con ella, la cifra sobre el límite", () => {
    expect(render(status())).toMatch(markedHtml("ring-dotted", "BASE-SIN-DOSIS-PREVIA", "cyan"));
    const html = render(
      status({
        career: { value_msv: 123.45, prior_msv: 100, fraction: 0.2, basis: "BASE-DE-CARRERA", limit_msv: 600, limit_source: "FUENTE-LIMITE" },
      }),
    );
    expect(html).toContain('<span class="num">123,5</span> de <span class="num">600</span> mSv');
    expect(html).toContain('<span class="secondary">(FUENTE-LIMITE)</span>');
    expect(html).toContain('<p class="secondary">BASE-DE-CARRERA</p>');
    expect(html).not.toContain("BASE-SIN-DOSIS-PREVIA");
    // Con la cifra, la fila de carrera ya no está en cian: solo lo sigue la de misión, que falta.
    expect(html.match(/c-cyan/g)).toHaveLength(1);
  });

  it("ningún color decorativo: solo el cian de lo que falta", () => {
    const html = render(status());
    expect(html).not.toMatch(/c-(red|yellow|blue|gray|magenta|green)/);
    expect(html.match(/c-cyan/g)).toHaveLength(2);
  });

  it("la palabra es el único texto de cada nombre de escala", () => {
    const html = render(status());
    const terms = [...html.matchAll(/<dt>([\s\S]*?)<\/dt>/g)].map((m) => textNodes(m[1]!));
    expect(terms).toEqual([["Aguda"], ["Esta misión"], ["Carrera"]]);
  });

  it("declarar el historial pide quién está en la consola", () => {
    expect(render(status())).toMatch(taggedPictogram("button", "pen", "Declarar</button>", ' class="command" type="submit"'));
    expect(render(status(), "")).toMatch(
      taggedPictogram("button", "pen", "Declarar</button>", ' class="command" type="submit" disabled=""'),
    );
  });

  it("el título, el plegable y sus rótulos llevan el signo del vocabulario común (§5.33)", () => {
    const html = render(status());
    expect(html).toMatch(taggedPictogram("h2", "trefoil", "Radiación: aguda, misión y carrera</h2>"));
    expect(html).toMatch(taggedPictogram("summary", "pen", "Declarar historial del tripulante</summary>"));
    expect(html).toMatch(taggedPictogram("label", "clock-rewind", "Misiones previas <input"));
    expect(html).toMatch(taggedPictogram("label", "trefoil", "Dosis de carrera previa (mSv, vacío si no se conoce) <input"));
  });

  it("la dosis de carrera va en el medidor neutro hasta el límite del backend, sin banda ni color", () => {
    const career = { prior_msv: 100, fraction: 0.2, basis: "BASE-DE-CARRERA", limit_msv: 600, limit_source: "FUENTE-LIMITE" };
    const html = render(status({ career: { ...career, value_msv: 150 } }));
    expect(html).toContain('<div class="meter" role="meter" aria-label="Carrera: dosis sobre el límite de carrera" aria-valuemin="0" aria-valuemax="600" aria-valuenow="150">');
    expect(html).toContain('<div class="meter-fill" style="width:25%"></div>');
    expect(html).not.toContain("meter-band");
    // Sin cifra de carrera no hay medidor: la fila dice que falta.
    expect(render(status())).not.toContain('role="meter"');
    // Por encima del límite: barra vacía y la flecha con la cifra, sin color; la cifra va una sola
    // vez, junto a la flecha, y no también delante (§5.33.12).
    const over = render(status({ career: { ...career, value_msv: 700 } }));
    expect(over).toContain('class="meter meter-oor"');
    expect(over).not.toContain("meter-fill");
    expect(over).toMatch(markedHtml("arrow-up", "700,0 de 600 mSv"));
    expect(over).not.toContain('<span class="num">700,0</span>');
    expect(over.match(/>[^<]*700,0/g)).toHaveLength(1);
    expect(html).toContain('<span class="num">150,0</span> de <span class="num">600</span> mSv');
    expect(over).not.toMatch(/c-(red|yellow|blue|gray|magenta|green|text)/);
  });

  it("el rechazo del backend se enseñaría a secas: el detalle, no «Error: HTTP…»", () => {
    // `ApiError.detail` es lo que el panel pinta; `String(error)` llevaría el prefijo técnico.
    const rejected = new ApiError(422, "DETALLE-DEL-BACKEND");
    expect(rejected.detail).toBe("DETALLE-DEL-BACKEND");
    expect(String(rejected)).not.toBe("DETALLE-DEL-BACKEND");
    const source = readFileSync(fileURLToPath(new URL("./RadiationScales.tsx", import.meta.url)), "utf8");
    // `requestOutcome` (§5.34.14) da el detalle a secas y la marca de lo que fue.
    expect(source).toContain("setError(requestOutcome(cause))");
    expect(source).toContain("<MarkOf mark={error.mark}>{error.text}</MarkOf>");
    expect(requestOutcome(rejected).text).toBe("DETALLE-DEL-BACKEND");
  });

  it("ningún carácter de forma ni trazo queda escrito: toda forma es un pictograma junto a su palabra", () => {
    const source = readFileSync(fileURLToPath(new URL("./RadiationScales.tsx", import.meta.url)), "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(code).not.toMatch(/[○◇△■□●◐▷◌⊘✕✓≠≈]/);
    expect(code).not.toMatch(/<svg|<path|aria-hidden/);
  });
});

/**
 * Decimocuarta ronda (C7, §5.34.7): la proyección al fin de misión (PREDICHA), la horquilla por
 * tipo de radiación (INFERIDA) y la Tabla 4.8-1 en su unidad. Cifras, bases, unidades y fuentes
 * son del backend; aquí, qué marca va con qué y que nada lleva color salvo el gris de la casilla
 * sin cifra.
 */
/** Una ficha del registro como la resuelve el backend (`Citation.to_dict`). */
const evidence = (
  id: string,
  title: string,
  url: string,
  relevance: string | null,
  inView: string | null,
): EvidenceItem => ({
  id,
  title,
  source: `CITA-${id}`,
  url,
  doi: null,
  pmid: null,
  organization: null,
  date: null,
  evidence_type: null,
  evidence_type_display: "sin clasificar",
  evidence_context: null,
  population: null,
  population_display: "no aplica",
  notes: inView,
  not_applicable: [],
  outside_enum: [],
  outside_enum_display: [],
  unverified: [],
  unverified_display: [],
  relevance,
  scope_caveat: inView,
  scope_in_view: inView,
  grade: { source: "", pmid: null, basis: "none", tier: "desconocido", label: "desconocido", preclinical: false, reason: "" },
});

const mission: NonNullable<Scales["mission"]> = {
  value_msv: 12.5,
  absorbed_mgy: 5,
  quality_factor: 2.38,
  hours_covered: 240,
  observation_type: "inferred",
  model_version: "m1",
  basis: "BASE-DE-MISION",
};

const projection: NonNullable<Scales["projection"]> = {
  observation_type: "predicted",
  model_version: "p1",
  mission_end: "2026-04-30",
  end_day: 120,
  scope: "ALCANCE-DE-PROYECCION",
  value_msv: 80.25,
  basis: "BASE-DE-PROYECCION",
  by_type: {
    low_msv: 61.7,
    high_msv: 92.4,
    low_quality_factor: 1.83,
    high_quality_factor: 2.74,
    observation_type: "inferred",
    basis: "BASE-POR-TIPO",
    source: evidence("badhwar-1992-sls1-tepc", "TITULO-TEPC", "https://example.invalid/tepc", null, "ALCANCE-TEPC"),
  },
  career: { value_msv: null, basis: "CARRERA-SIN-PREVIA", limit_msv: 600, limit_source: "FUENTE-LIMITE" },
};

const limits: NonNullable<Scales["short_term_limits"]> = {
  rows: [
    {
      organ: "Lens",
      organ_display: "ORGANO-A",
      unit: "mGy-Eq",
      thirty_day: { value: 1000, unit: "mGy-Eq", absent: null, literal: null },
      one_year: { value: 2000, unit: "mGy-Eq", absent: null, literal: null },
      career: { value: 4000, unit: "mGy-Eq", absent: null, literal: null },
      note: "NOTA-A",
    },
    {
      organ: "CNS",
      organ_display: "ORGANO-B",
      unit: "mGy",
      thirty_day: { value: null, unit: null, absent: "SIN-CIFRA", literal: "-" },
      one_year: { value: 100, unit: "mGy", absent: null, literal: null },
      career: { value: 250, unit: "mGy", absent: null, literal: null },
      note: null,
    },
  ],
  units: "UNIDADES-DE-LA-NORMA",
  scope: "ALCANCE-DE-LIMITES",
  source: evidence("nasa-std-3001-vol1-rev-c", "TITULO-VOL1", "https://example.invalid/vol1", "TABLA-4.8-1", null),
};

describe("<RadiationScales>, proyección, tipos y límites a corto plazo", () => {
  it("la proyección va en su fila, con el dibujo del día de misión, rotulada PREDICHA, con su base y su alcance", () => {
    const html = render(status({ mission, projection }));
    expect(html).toMatch(markedHtml("calendar-day", "Al fin de misión"));
    const names = [...html.matchAll(/<dt><span class="mark"><svg [^>]*data-pictogram="([a-z-]+)"/g)].map((m) => m[1]);
    expect(names).toEqual(["burst", "trefoil", "calendar-day", "bar-capped"]);
    expect(html).toContain('<span class="num">80,25</span> mSv');
    expect(html).toContain('data-pictogram="play"');
    expect(html).toContain('<p class="secondary">BASE-DE-PROYECCION; ALCANCE-DE-PROYECCION.</p>');
  });

  it("la horquilla por tipo de radiación es INFERIDA y enlaza la ficha de sus Q", () => {
    const html = render(status({ mission, projection }));
    expect(html).toContain(
      'Por tipo de radiación: <span class="num">61,70</span> a <span class="num">92,40</span> mSv',
    );
    expect(html).toContain('<p class="secondary">BASE-POR-TIPO.</p>');
    // La ficha entera (`EvidenceEntry`), con su salvedad, plegada bajo el libro de la fuente.
    expect(html).toMatch(taggedPictogram("summary", "book-open", "Fuente de los factores de calidad</summary>"));
    expect(html).toMatch(/<a href="https:\/\/example\.invalid\/tepc" target="_blank" rel="noreferrer">TITULO-TEPC<\/a>/);
    expect(html).toMatch(markedHtml("shape-triangle", "Alcance: ALCANCE-TEPC", "yellow"));
  });

  it("sin dosis previa la carrera proyectada dice por qué, sin medidor y sin otro cian", () => {
    const html = render(status({ mission, projection }));
    expect(html).toContain('<p class="secondary">CARRERA-SIN-PREVIA</p>');
    expect(html).not.toContain("Carrera proyectada al fin de misión");
    // Solo el cian de la fila «Carrera», que es la que tiene el dato ausente.
    expect(html.match(/c-cyan/g)).toHaveLength(1);
  });

  it("con dosis previa, la carrera proyectada va en el medidor neutro hasta el límite", () => {
    const career = { value_msv: 200.5, prior_msv: 120, fraction: 0.334, basis: "BASE-CARRERA-PROY", limit_msv: 600, limit_source: "FUENTE-LIMITE" };
    const html = render(status({ mission, projection: { ...projection, career } }));
    expect(html).toContain('Carrera proyectada: <span class="num">200,5</span> de <span class="num">600</span> mSv');
    expect(html).toContain('aria-label="Carrera proyectada al fin de misión sobre el límite de carrera"');
    expect(html).toContain('<p class="secondary">BASE-CARRERA-PROY</p>');
    const over = render(status({ mission, projection: { ...projection, career: { ...career, value_msv: 900 } } }));
    expect(over).toMatch(markedHtml("arrow-up", "900,0 de 600 mSv"));
    expect(over).toContain("Carrera proyectada: ");
    expect(over).not.toContain('<span class="num">900,0</span>');
  });

  it("con la misión terminada no hay cifra: la base del backend, en secundario y sin cian", () => {
    // Como lo da el backend con la misión terminada: sin horquilla ni carrera.
    const { by_type: _byType, career: _career, ...rest } = projection;
    const ended = { ...rest, value_msv: null, basis: "MISION-TERMINADA" };
    const html = render(status({ mission, projection: ended }));
    expect(html).toContain('<span class="secondary">MISION-TERMINADA</span>');
    expect(html).not.toContain('data-pictogram="play"');
    expect(html.match(/c-cyan/g)).toHaveLength(1);
  });

  it("sin proyección no hay fila: la de misión ya dice que falta la tasa", () => {
    const html = render(status());
    expect(html).not.toContain("Al fin de misión");
  });

  it("los límites a corto plazo van plegados, en la unidad del backend, sin convertir ni colorear", () => {
    const html = render(status({ short_term_limits: limits }));
    expect(html).toMatch(taggedPictogram("summary", "bar-capped", "Límites a corto plazo por órgano</summary>"));
    expect(html).toMatch(thSign("figure-dot", "Órgano (unidad)</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("bar-capped", "30 días</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("bar-capped", "1 año</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("bar-capped", "Carrera</span></th>", ' scope="col"'));
    expect(html).toContain('<td>ORGANO-A (mGy-Eq)<span class="secondary"> · NOTA-A</span></td>');
    expect(html).toContain('<td>ORGANO-B (mGy)</td>');
    expect(html).toContain('<td><span class="num">1000</span></td>');
    expect(html).toContain('<div class="limits-table"><table class="ledger">');
    // Ninguna fila ni casilla en mSv: la unidad de la norma, sin convertir.
    expect(html).not.toMatch(/\(mSv\)|mSv<\/td>/);
    // La casilla sin cifra: gris con su círculo tachado y el texto que da el backend.
    expect(html).toMatch(markedHtml("slash-circle", "SIN-CIFRA", "gray"));
    expect(html).toContain("UNIDADES-DE-LA-NORMA; ALCANCE-DE-LIMITES.");
    expect(html).toMatch(/<a href="https:\/\/example\.invalid\/vol1" target="_blank" rel="noreferrer">TITULO-VOL1<\/a>/);
    expect(html).toContain('<p class="secondary">TABLA-4.8-1</p>');
    expect(html).not.toMatch(/c-(red|yellow|blue|magenta|green)/);
  });
});

/**
 * Decimosexta ronda (E8, §5.36.8): lo leído junto a la radiación. Que en Orion avisa HERA y EMMA
 * no lo lee se ve sin abrir nada; el fin del refugio va plegado con la casa del refugio; el ciclo
 * solar, plegado y con la fecha de su nota en el rótulo. Textos y fichas, del backend; ninguna
 * marca de estado ni color propio.
 */
const reading = (label: string, over: Partial<RadiationReading> = {}): RadiationReading => {
  const a = evidence(`ficha-a-${label}`, `TITULO-A-${label}`, "https://example.invalid/a", null, null);
  const b = evidence(`ficha-b-${label}`, `TITULO-B-${label}`, "https://example.invalid/b", null, null);
  return {
    label,
    text: `TEXTO-${label}`,
    scope: `ALCANCE-${label}`,
    not_found: `NO-ENCONTRADO-${label}`,
    read_on: "2026-10-23",
    quotes: [
      { quote: `FRASE-1-${label}`, where: "SITIO-1", ref: a.id },
      { quote: `FRASE-3-${label}`, where: "SITIO-3", ref: b.id },
      { quote: `FRASE-2-${label}`, where: "SITIO-2", ref: a.id },
    ],
    sources: [a, b],
    ...over,
  };
};

const readings = (): Partial<Scales> => ({
  acute: {
    active_event: null,
    time_to_action: null,
    onboard_warning: reading("AVISO", { emma_reads_it: false }),
    shelter_exit: reading("FIN"),
  },
  solar_cycle: reading("CICLO", { as_of: "2024-10-15" }),
});

describe("<RadiationScales>, lo leído: HERA, ciclo solar y fin del refugio", () => {
  it("el aviso a bordo se lee sin abrir nada, también sin evento; sus fuentes, plegadas", () => {
    const html = render(status(readings()));
    expect(html).toContain('<span class="secondary">sin evento solar activo</span>');
    expect(html).toContain('<p class="secondary"><strong>AVISO:</strong> TEXTO-AVISO</p>');
    const before = html.slice(0, html.indexOf("TEXTO-AVISO"));
    // Ningún plegable abierto alrededor: el texto no está dentro de un <details>.
    expect(before.split("<details").length).toBe(before.split("</details>").length);
    expect(html).toMatch(taggedPictogram("summary", "book-open", "Fuentes del aviso a bordo</summary>"));
    // Su alcance (que EMMA no recibe ese aviso ni cambia el riesgo) va con sus fuentes.
    expect(html).toContain('<p class="secondary">ALCANCE-AVISO.</p>');
  });

  it("el fin del refugio va plegado con el libro de fuente, con su texto, su alcance y sus fuentes", () => {
    const html = render(status(readings()));
    // No la casa: esa es el refugio montado durante un evento, y aquí no hay evento.
    expect(html).toMatch(taggedPictogram("summary", "book-open", "FIN</summary>"));
    expect(html).toContain('<p class="secondary">TEXTO-FIN</p>');
    expect(html).toContain('<p class="secondary">ALCANCE-FIN.</p>');
    expect(html).toContain('<q lang="en">FRASE-1-FIN</q> (SITIO-1)');
  });

  it("el ciclo solar va plegado con la fecha de su nota en el rótulo", () => {
    const html = render(status(readings()));
    expect(html).toMatch(
      taggedPictogram("summary", "book-open", 'CICLO (nota del <span class="num">2024-10-15</span>)</summary>'),
    );
    expect(html).toContain('<p class="secondary">TEXTO-CICLO</p>');
    expect(html).toContain('<p class="secondary">ALCANCE-CICLO.</p>');
  });

  it("cada ficha una vez, con sus frases debajo; el día de lectura y lo buscado sin encontrar", () => {
    const html = render(status(readings()));
    for (const label of ["AVISO", "FIN", "CICLO"]) {
      expect(html.match(new RegExp(`>TITULO-A-${label}</a>`, "g"))).toHaveLength(1);
      expect(html.match(new RegExp(`>TITULO-B-${label}</a>`, "g"))).toHaveLength(1);
      for (const n of [1, 2, 3]) expect(html).toContain(`<q lang="en">FRASE-${n}-${label}</q>`);
      // Las dos frases de la ficha A van juntas bajo ella, aunque el backend las dé separadas.
      expect(html).toContain(
        `FRASE-1-${label}</q> (SITIO-1)</p><p><q lang="en">FRASE-2-${label}</q> (SITIO-2)</p></div>`,
      );
      expect(html).toContain(`NO-ENCONTRADO-${label}`);
    }
    expect(html).toContain('Leído el <span class="num">2026-10-23</span>.');
    expect(html).toMatch(markedHtml("magnifier", "Buscado y no encontrado:"));
    // Una frase del mismo día que la entrada no repite la fecha.
    expect(html).not.toContain("; leída el");
  });

  it("una frase leída otro día que la entrada lleva su día junto a su sitio", () => {
    const later = reading("CICLO", { as_of: "2024-10-15" });
    later.quotes = [...later.quotes, { quote: "CIFRA-NOAA", where: "SITIO-NOAA", ref: "ficha-b-CICLO", read_on: "2026-10-26" }];
    const html = render(status({ ...readings(), solar_cycle: later }));
    expect(html).toContain('<q lang="en">CIFRA-NOAA</q> (SITIO-NOAA; leída el <span class="num">2026-10-26</span>)');
    // El pie dice los dos días, el de la primera lectura delante (revisión de código).
    expect(html).toContain(
      'Leído el <span class="num">2026-10-23</span> y el <span class="num">2026-10-26</span>.',
    );
  });

  it("nada de lo leído lleva color propio: el cian sigue siendo solo el de lo que falta", () => {
    const html = render(status(readings()));
    expect(html).not.toMatch(/c-(red|yellow|blue|magenta|green)/);
    expect(html.match(/c-cyan/g)).toHaveLength(2);
    // El gris que queda es el de la ficha (`EvidenceEntry`: campos sin clasificar del fixture), no
    // del texto: los párrafos de lo leído van sin marca.
    for (const label of ["FIN", "CICLO"]) {
      expect(html).toContain(`<p class="secondary">TEXTO-${label}</p>`);
    }
    expect(html).toContain('<p class="secondary"><strong>AVISO:</strong> TEXTO-AVISO</p>');
  });

  it("sin lo leído (un backend anterior) no se pinta nada de ello", () => {
    const html = render(status());
    expect(html).not.toContain("Fuentes del aviso a bordo");
    expect(html).not.toContain("Leído el");
    expect(html).not.toContain("nota del");
  });
});
