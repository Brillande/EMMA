import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { spanWithPictogram, taggedPictogram, textLines } from "../advisor/visibleText";
import type { AlertHistory, ChronicleEvent, ChronicleView, DependsView, RoutineState, WaitingView } from "../lib/api";
import { adoptLevelLabels } from "../lib/levels";
import { AsOf, ChronicleBody, DependsList, RoutineList, WaitingBody } from "./TimelinePieces";

/*
 * Las piezas de la cronica, pintadas con un ejemplo: cada palabra del backend con su pictograma
 * al lado (F.5.10 e), el color solo donde la tabla F.5-1 lo da, y el texto visible igual que
 * antes de los pictogramas: la interfaz no añade palabras.
 */

const met = (iso: string) => `MET(${iso.slice(5, 10)})`;

function event(over: Partial<ChronicleEvent>): ChronicleEvent {
  return {
    fecha: "2026-11-13",
    tipo: "alerta",
    que: "frase del backend",
    quien: "EMMA",
    fuente: "estado",
    clave: `k:${JSON.stringify(over)}`,
    at: "2026-11-13T04:00:00+00:00",
    time_basis: "data",
    recorded: null,
    mission_day: 12,
    stage: "mission-day",
    fact: "x",
    level: null,
    severity: null,
    recomputed: false,
    ...over,
  };
}

const history: AlertHistory = {
  subject: "crew-1",
  until: null,
  label: "historia recalculada",
  resting_level_display: "palabra",
  rules_version: "reglas v1",
  basis: ["es un recalculo"],
  window_hours: 6,
  steps_examined: 3,
  max_steps: 120,
  max_steps_basis: "tope de diseño",
  examined_from: "2026-11-01T00:00:00+00:00",
  examined_until: "2026-11-13T00:00:00+00:00",
  first_reading: "2026-11-01T00:00:00+00:00",
  complete: true,
  coverage: "hasta aqui",
  none_display: null,
  episodes: [
    {
      id: "e1",
      domain: "behavioral",
      domain_display: "conductual",
      peak_level: "watch",
      peak_level_display: "palabra de nivel",
      first_step_start: "2026-11-10T00:00:00+00:00",
      last_step_end: "2026-11-11T00:00:00+00:00",
      steps: 4,
      open: false,
      state_display: "cerrado",
      start_unknown: false,
      start_note: null,
      levels: [],
      signed: [],
    },
  ],
};

const view: ChronicleView = {
  as_of: "2026-11-13T10:00:00+00:00",
  as_of_source: "data",
  as_of_basis: "instante de referencia del estado",
  stages: [
    { key: "mission-day", display: "día de misión", count: 4 },
    { key: "unplaced", display: "sin instante de datos", count: 1 },
    { key: "preflight", display: "vacía", count: 0 },
  ],
  events: [
    event({ tipo: "habitat", que: "CO2 fuera de su límite", severity: "health", fuente: "cabina" }),
    event({ tipo: "habitat", que: "temperatura fuera de confort", severity: "target" }),
    event({ tipo: "alerta", que: "alerta conductual", level: "watch", quien: "CDR" }),
    event({ tipo: "alerta", que: "recalculado hoy: episodio", recomputed: true, level: "critical" }),
    event({ tipo: "sistema", que: "modo seguro activado", stage: "unplaced", time_basis: "recorded" }),
  ],
  lines: [],
  recomputed: history,
};

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);
const pictogram = (name: string) => new RegExp(`<svg [^>]*data-pictogram="${name}">`);

afterEach(() => adoptLevelLabels(null));

describe("la cronica pintada", () => {
  const html = render(createElement(ChronicleBody, { view, met }));

  it("cada etapa lleva su pictograma junto a la palabra del backend, y las vacias no se pintan", () => {
    // Título de etapa con `PanelTitle` (§5.33.1): el dibujo directo en el `<h3>`, sin `<span>`.
    expect(html).toMatch(taggedPictogram("h3", "calendar-day", "día de misión · "));
    expect(html).toMatch(taggedPictogram("h3", "clock", "sin instante de datos · "));
    expect(html).not.toContain("vacía");
    expect(html).not.toContain('data-pictogram="clipboard"');
  });

  it("cada hecho lleva el pictograma de su tipo delante de la frase, sin title: la clave no es texto", () => {
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="house">/);
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="gear">.*?<\/svg>modo seguro activado<\/span>/);
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="bell">/);
    expect(html).not.toContain("title=");
  });

  it("una excursion de cabina: su clase de limite pegada a la frase, el color solo en el pictograma", () => {
    expect(html).toMatch(
      /<span class="mark c-yellow"><svg [^>]*data-pictogram="shape-triangle">.*?<\/svg><span class="c-text">CO2 fuera de su límite<\/span><\/span>/,
    );
    expect(html).toMatch(
      /<span class="mark c-blue"><svg [^>]*data-pictogram="shape-diamond">.*?<\/svg><span class="c-text">temperatura fuera de confort<\/span><\/span>/,
    );
  });

  it("una alerta lleva su insignia de nivel delante, y la frase sin color", () => {
    adoptLevelLabels({ watch: "P-1" });
    const labelled = render(createElement(ChronicleBody, { view, met }));
    expect(labelled).toMatch(
      /<span class="mark level c-blue"><svg [^>]*data-pictogram="shape-diamond">.*?<\/svg>P-1<\/span> <span class="mark"><svg [^>]*data-pictogram="bell">.*?<\/svg>alerta conductual<\/span>/,
    );
  });

  it("lo recalculado va entero en secundario, con su pictograma, y nunca con la insignia de un nivel", () => {
    expect(html).toMatch(
      /<span class="mark secondary"><svg [^>]*data-pictogram="bell">.*?<\/svg><span class="mark"><svg [^>]*data-pictogram="refresh">.*?<\/svg>recalculado hoy: episodio<\/span><\/span>/,
    );
    expect(html).not.toMatch(/c-red/);
    expect(html).not.toMatch(pictogram("shape-square"));
  });

  it("la historia recalculada: su rotulo y cada episodio con el recalculo en secundario y el dominio en texto normal", () => {
    expect(html).toMatch(taggedPictogram("h3", "refresh", "historia recalculada · "));
    expect(html).toMatch(
      /<span class="mark secondary"><svg [^>]*data-pictogram="refresh">.*?<\/svg><span class="c-text"><span class="mark"><svg [^>]*data-pictogram="domain-behavioral">.*?<\/svg>conductual<\/span><\/span><\/span>: palabra de nivel · /,
    );
  });

  it("el texto visible es el de antes: ninguna palabra nueva", () => {
    expect(textLines(html)).toEqual([
      "A fecha de MET(11-13) · instante de referencia del estado",
      "día de misión · 4",
      "MET(11-13) recalculado hoy: episodio (EMMA · estado)",
      "MET(11-13) watch alerta conductual (CDR · estado)",
      "MET(11-13) temperatura fuera de confort (EMMA · estado)",
      "MET(11-13) CO2 fuera de su límite (EMMA · cabina)",
      "sin instante de datos · 1",
      "2026-11-13 04:00 UTC modo seguro activado (EMMA · estado)",
      "historia recalculada · 1 episodios cerrados",
      "hasta aqui",
      "es un recalculo",
      "Tope: 120 pasos de 6 h (tope de diseño) · reglas v1",
      "conductual: palabra de nivel · MET(11-10) a MET(11-11) · 4 pasos · cerrado",
    ]);
  });
});

describe("un hito de la crónica elige su momento en «Cuerpo» (§5.35.8)", () => {
  const linked: ChronicleView = {
    ...view,
    events: [
      event({
        tipo: "fase",
        que: "cambio de fase de misión: adaptación → fase estable",
        fact: "phase-change",
        moment: { key: "phase-stable", display: "Cambio de fase: de adaptación a fase estable (día 14)" },
      }),
      event({ tipo: "alerta", que: "alerta conductual", level: "watch" }),
    ],
    recomputed: null,
  };

  it("con `onMoment`, el hecho que es un momento lleva el mando, con el dibujo del cuerpo y el rótulo del backend", () => {
    const html = render(createElement(ChronicleBody, { view: linked, met, onMoment: () => undefined }));
    expect(html).toMatch(
      taggedPictogram(
        "button",
        "figure-dot",
        "Ver en «Cuerpo»",
        ' class="command" title="Cambio de fase: de adaptación a fase estable (día 14)"',
      ),
    );
    // Solo el que es un momento: la alerta no lo lleva.
    expect(html.split("Ver en «Cuerpo»").length - 1).toBe(1);
  });

  it("sin `onMoment` (Tierra) no hay mando, y la crónica dice lo de siempre", () => {
    const html = render(createElement(ChronicleBody, { view: linked, met }));
    expect(html).not.toContain("Ver en «Cuerpo»");
    expect(html).not.toContain("<button");
  });

  it("la consola pasa el mando a la crónica y el momento elegido a «Cuerpo»: uno solo para los dos", async () => {
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const code = readFileSync(fileURLToPath(new URL("./CrewConsole.tsx", import.meta.url)), "utf-8");
    expect(code).toContain("onMoment={chooseMomentFromChronicle}");
    expect(code).toContain("momentKey={moment}");
    expect(code).toContain("onMoment={setMoment}");
  });
});

describe("la carrera: misiones previas declaradas (§5.36.4)", () => {
  const career: ChronicleView = {
    ...view,
    stages: [
      { key: "career", display: "carrera: misiones previas declaradas", count: 1 },
      { key: "mission-day", display: "día de misión", count: 1 },
    ],
    events: [
      event({
        tipo: "carrera",
        que: "misión previa «Expedición 1», del 2021-04-01 al 2021-10-01",
        quien: "CDR",
        fuente: "asiento 7: historial declarado",
        fecha: "2021-04-01",
        at: "2021-04-01T00:00:00+00:00",
        time_basis: "declared",
        recorded: "2026-10-22T10:00:00+00:00",
        mission_day: null,
        stage: "career",
      }),
      event({ que: "alerta conductual" }),
    ],
    recomputed: null,
  };
  const html = render(createElement(ChronicleBody, { view: career, met }));

  it("la etapa va con su dibujo y la palabra del backend; el hecho, con el cohete y su frase", () => {
    expect(html).toMatch(taggedPictogram("h3", "clock-rewind","carrera: misiones previas declaradas · "));
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="rocket">.*?<\/svg>misión previa «Expedición 1»/);
  });

  it("su fecha es el día declarado, sin hora ni tiempo de misión; los demás siguen en tiempo de misión", () => {
    // Cada hecho es una línea: su instante delante de la frase.
    const lines = textLines(html);
    expect(lines.some((line) => line.startsWith("2021-04-01 misión previa «Expedición 1»"))).toBe(true);
    expect(lines.some((line) => line.endsWith("(CDR · asiento 7: historial declarado)"))).toBe(true);
    expect(html).not.toContain("MET(04-01)");
    expect(html).not.toContain("2021-04-01 00:00");
    expect(lines.some((line) => line.startsWith("MET(11-13)"))).toBe(true);
  });

  it("una fecha declarada con otra forma falla en vez de pintarse (`lib/format.ts`)", () => {
    const bad = { ...career, events: [{ ...career.events[0]!, fecha: "01/04/2021" }] };
    expect(() => render(createElement(ChronicleBody, { view: bad, met }))).toThrow(RangeError);
  });
});

describe("con qué reglas se firmó lo que va junto a un episodio recalculado (§5.39.9)", () => {
  const phrase = "decidido con reglas@old; distinta de la de hoy: reglas@abc hoy";
  const entry = {
    ledger_index: 12,
    kind: "acknowledgement",
    kind_display: "alerta reconocida",
    domain: "behavioral",
    by: "CDR",
    reference_time: "2026-11-10T02:00:00+00:00",
  };
  const withSigned = (signed: AlertHistory["episodes"][number]["signed"]) =>
    render(
      createElement(ChronicleBody, {
        view: { ...view, recomputed: { ...history, episodes: [{ ...history.episodes[0]!, signed }] } },
        met,
      }),
    );

  it("la frase del backend va al final de la línea, tal cual y sin color", () => {
    const html = withSigned([
      { ...entry, rules: { rules_version: "reglas@old", same_as_today: false, text: phrase } },
    ]);
    expect(textLines(html).join(" ")).toContain(`12 · ${phrase}`);
    expect(html).not.toMatch(/c-(red|yellow|cyan)[^>]*>[^<]*decidido con/);
  });

  it("un anuncio (`null`) o un backend anterior no dicen nada", () => {
    expect(withSigned([{ ...entry, rules: null }, { ...entry, ledger_index: 13 }])).not.toContain("decidido con");
  });
});

describe("la cronica vacia", () => {
  it("sin hechos: la frase de siempre con la marca de visto, no un hueco", () => {
    const html = render(createElement(ChronicleBody, { view: { ...view, events: [], recomputed: null }, met }));
    expect(html).toMatch(spanWithPictogram("mark", "check", "sin hechos que contar todavía"));
  });
});

describe("el ahora de una pieza", () => {
  it("si sale de los datos, texto secundario sin señal", () => {
    const html = render(createElement(AsOf, { view, met }));
    expect(html).toBe(
      '<p class="secondary"><span class="mark">A fecha de <span class="num">MET(11-13)</span> · instante de referencia del estado</span></p>',
    );
  });

  it("si no, dato ausente: anillo punteado en cian junto a la frase", () => {
    for (const source of ["cut", "clock"] as const) {
      const html = render(createElement(AsOf, { view: { ...view, as_of_source: source }, met }));
      expect(html).toMatch(/^<p><span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted">.*?<\/svg>A fecha de /);
    }
  });
});

describe("medidas periodicas", () => {
  const routine = (over: Partial<RoutineState>): RoutineState => ({
    key: "k",
    display: "K",
    display_es: "Medida",
    period_hours: 24,
    basis: "base",
    state: "al-dia",
    last_run: null,
    last_success: null,
    ...over,
  });

  it("rota en amarillo con triangulo, atrasada con reloj de arena y sin color, nunca en gris con anillo", () => {
    const html = render(
      createElement(RoutineList, {
        items: [
          routine({ key: "a", display_es: "Peso", state: "rota" }),
          routine({ key: "b", display_es: "Orina", state: "atrasada", last_run: "2026-11-12T00:00:00+00:00" }),
          routine({ key: "c", state: "nunca-corrio" }),
          routine({ key: "d", state: "al-dia" }),
        ],
        met,
      }),
    );
    // El nombre con el dibujo de su familia (sin color) y el estado con su marca junto a su palabra.
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="[a-z0-9-]+">.*?<\/svg>Peso<\/span>: <span class="mark c-yellow"><svg [^>]*data-pictogram="shape-triangle">.*?<\/svg>sin lectura buena<\/span>/);
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="[a-z0-9-]+">.*?<\/svg>Orina<\/span>: <span class="mark"><svg [^>]*data-pictogram="hourglass">.*?<\/svg>atrasada<\/span>/);
    // Lo que nunca corrió: «no disponible» de toda la interfaz, el círculo tachado en gris.
    expect(html).toMatch(/<p><span class="mark c-gray"><svg [^>]*data-pictogram="slash-circle">.*?<\/svg><span class="num">1<\/span> medidas sin ninguna lectura<\/span><\/p>/);
    expect(html).not.toMatch(pictogram("ring-dotted"));
    // Tablero (2026-11-08, la muestra): delante, el anillo de las que van al día sobre las que se
    // deben, un mosaico por estado (los cuatro, lo roto primero) con las mismas marcas y palabras,
    // y cada medida como ficha con la marca de su estado (la palabra, para el lector de pantalla);
    // las filas, igual que antes.
    expect(textLines(html)).toEqual([
      "1/ 4",
      "al día",
      "1 sin lectura buena",
      "1 atrasada",
      "1 sin ninguna lectura",
      "1 al día",
      "Peso: sin lectura buena",
      "Orina: atrasada",
      "Medida: sin ninguna lectura",
      "Medida: al día",
      "Peso: sin lectura buena · última — · cada 24 h (base)",
      "Orina: atrasada · última MET(11-12) · cada 24 h (base)",
      "1 medidas sin ninguna lectura",
    ]);
  });

  it("tablero: el anillo dice cuántas de cuántas, y cada mosaico y cada ficha llevan la marca de su estado y su color en el filete", () => {
    const html = render(
      createElement(RoutineList, {
        items: [
          routine({ key: "a", state: "rota" }),
          routine({ key: "b", state: "nunca-corrio" }),
          routine({ key: "c", state: "al-dia" }),
          // Lo suspendido por el nivel de misión no se debe: ni en el anillo ni en las píldoras.
          routine({ key: "d", state: "atrasada", suspended: true }),
        ],
        met,
      }),
    );
    expect(html).toContain('class="ref-ring" role="img" aria-label="1 de 3 medidas al día"');
    expect(html).toMatch(
      /<li class="routine-tile" data-count="1" style="--lvl:var\(--c-yellow\)"><span class="num routine-tile-num">1<\/span> <span class="mark c-yellow"><svg [^>]*data-pictogram="shape-triangle">.*?<\/svg>sin lectura buena<\/span><\/li>/,
    );
    expect(html).toMatch(
      /<li class="routine-tile" data-count="1" style="--lvl:var\(--c-gray\)"><span class="num routine-tile-num">1<\/span> <span class="mark c-gray"><svg [^>]*data-pictogram="slash-circle">.*?<\/svg>sin ninguna lectura<\/span><\/li>/,
    );
    // La suspendida no cuenta: el mosaico de «atrasada» dice 0, y no hay ficha para ella.
    expect(html).toMatch(/<li class="routine-tile" data-count="0"><span class="num routine-tile-num">0<\/span> <span class="mark"><svg [^>]*data-pictogram="hourglass">.*?<\/svg>atrasada<\/span><\/li>/);
    expect(html).not.toContain(": atrasada\"");
    // Cada ficha, con la marca y el color de su estado; la de «al día», con la de visto y sin color.
    expect(html).toMatch(
      /<li class="routine-chip" style="--lvl:var\(--c-yellow\)" title="Medida: sin lectura buena"><span class="mark c-yellow"><svg [^>]*data-pictogram="shape-triangle">.*?<\/svg>Medida<\/span><span class="sr-only">: sin lectura buena<\/span><\/li>/,
    );
    expect(html).toMatch(/<li class="routine-chip" title="Medida: al día"><span class="mark"><svg [^>]*data-pictogram="check">/);
    // La atrasada no lleva color: su mosaico queda en el tono neutro de la hoja (sin `--lvl`).
    const late = render(createElement(RoutineList, { items: [routine({ state: "atrasada" })], met }));
    expect(late).toMatch(/<li class="routine-tile" data-count="1"><span class="num routine-tile-num">1<\/span> <span class="mark"><svg [^>]*data-pictogram="hourglass">.*?<\/svg>atrasada<\/span><\/li>/);
    // Sin nada que se deba, ni anillo ni mosaicos: solo la frase de siempre.
    const nothing = render(createElement(RoutineList, { items: [routine({ state: "atrasada", suspended: true })], met }));
    expect(nothing).not.toContain("ref-ring");
    expect(textLines(nothing)).toEqual(["Todas las que llegan, a su ritmo."]);
  });

  it("durante un evento solar: el periodo acortado y su motivo, tal cual del backend y en su orden", () => {
    const html = render(
      createElement(RoutineList, {
        items: [
          routine({
            key: "dose", display_es: "Dosis", state: "rota", period_hours: 1, basis: "base de evento",
            period_source: "event", design_period_hours: 6, event_id: "SEP-1", priority: 1,
            period_note: "frase del backend de la dosis",
          }),
          routine({ key: "b", display_es: "Orina", state: "atrasada" }),
        ],
        met,
        note: "frase del backend del panel",
      }),
    );
    expect(html).toMatch(/^<p class="secondary">frase del backend del panel<\/p>/);
    // Sin color nuevo: el estado lleva su marca de siempre, y la frase va como texto secundario.
    expect(html).not.toMatch(/c-cyan|c-red/);
    expect(textLines(html)).toEqual([
      "frase del backend del panel",
      "0/ 2",
      "al día",
      "1 sin lectura buena",
      "1 atrasada",
      "0 sin ninguna lectura",
      "0 al día",
      "Dosis: sin lectura buena",
      "Orina: atrasada",
      "Dosis: sin lectura buena · última — · cada 1 h (base de evento) · frase del backend de la dosis",
      "Orina: atrasada · última — · cada 24 h (base)",
    ]);
  });

  it("todas a su ritmo: la frase de siempre, con la marca de visto; el anillo, lleno, y los otros mosaicos a 0", () => {
    const html = render(createElement(RoutineList, { items: [routine({})], met }));
    expect(html).toContain('aria-label="1 de 1 medidas al día"');
    expect(html).not.toContain("board-tally");
    expect(html).toMatch(/<p class="secondary"><span class="mark"><svg [^>]*data-pictogram="check">/);
    expect(html).toMatch(spanWithPictogram("mark", "check", "Todas las que llegan, a su ritmo."));
    expect(textLines(html)).toEqual([
      "1/ 1",
      "al día",
      "0 sin lectura buena",
      "0 atrasada",
      "0 sin ninguna lectura",
      "1 al día",
      "Medida: al día",
      "Todas las que llegan, a su ritmo.",
    ]);
  });
});

describe("que depende de un dato", () => {
  const views: DependsView[] = [
    {
      key: "hr-rest",
      affected: [
        { id: "1", mode: "auto", title: "riesgo cardiovascular" },
        { id: "2", mode: "humano", title: "plan de ejercicio" },
      ],
      map_errors: [],
    },
  ];

  it("chip junto a lo que se recalcula solo, persona junto a lo que revisa una persona", () => {
    const html = render(createElement(DependsList, { views }));
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="chip">.*?<\/svg>se recalcula riesgo cardiovascular<\/span>/);
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="person">.*?<\/svg>a revisar por una persona: plan de ejercicio<\/span>/);
    expect(textLines(html)).toEqual(["hr-rest: se recalcula riesgo cardiovascular · a revisar por una persona: plan de ejercicio"]);
  });

  it("el dato se nombra con su nombre y el dibujo de su familia; sin nombre, su clave tal cual", () => {
    const named = render(createElement(DependsList, { views, names: { "hr-rest": "FC en reposo" } }));
    expect(named).toMatch(/<li><span class="mark"><svg [^>]*data-pictogram="[a-z0-9-]+">.*?<\/svg>FC en reposo<\/span>: /);
    expect(textLines(named)[0]).toMatch(/^FC en reposo: se recalcula/);
  });

  it("sin nada que dependa, la raya", () => {
    expect(render(createElement(DependsList, { views: [] }))).toBe('<span class="secondary">—</span>');
  });
});

describe("espera por una persona", () => {
  it("lo que no cuadra entre dos informes va en amarillo con triangulo; lo que espera, sin color", () => {
    const waiting: WaitingView = {
      threshold_days: 3,
      waiting: [{ title: "reconocer la alerta ósea", kind: "ack", days: 4, since: "2026-11-09" }],
      incongruences: [{ key: "hemoglobina", sample: "S-2", values: [], note: "" }] as unknown as WaitingView["incongruences"],
    };
    const html = render(createElement(WaitingBody, { view: waiting }));
    expect(html).toMatch(/<p><span class="mark c-yellow"><svg [^>]*data-pictogram="shape-triangle">.*?<\/svg>hemoglobina, S-2: dos informes no coinciden<\/span><\/p>/);
    expect(textLines(html)).toEqual([
      "hemoglobina, S-2: dos informes no coinciden",
      "reconocer la alerta ósea · 4 días",
      "Solo lo que lleva 3 días o más.",
    ]);
  });
});
