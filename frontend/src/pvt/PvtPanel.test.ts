import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
// Sin los `data-ui` del asistente: estas pruebas miran el marcado del panel.
import { renderToStaticMarkup } from "../assistant/staticMarkup";
import { describe, expect, it } from "vitest";

import { markedHtml, pictogramSvg, taggedPictogram, thSign, textNodes } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import type { PvtProtocol, PvtRecordedSession, PvtSubmitted } from "../lib/api";
import { palette } from "../lib/palette";
import { PvtView } from "./PvtPanel";
import { IDLE, type Snapshot } from "./session";
import { ApiError } from "../lib/api";
import { type RequestOutcome, requestOutcome } from "../lib/marks";

/** Una lectura que cayó (5xx): la marca de fallo con el motivo tal cual (§5.34.14). */
const down = (text: string): RequestOutcome => requestOutcome(new ApiError(503, text));

/**
 * El panel pinta lo que da el backend: instrucciones, límites, parámetros con su respaldo,
 * la puntuación y lo que quedó en el registro. No puntúa, no interpreta, y la marca no se
 * parece a una alarma. Toda forma es un pictograma (`data-pictogram`) pegado a su palabra
 * (§5.32): aquí se fija cuál acompaña a cada estado y que ningún carácter de forma queda escrito.
 * Desde la segunda pasada (§5.33.8) los títulos, plegables, mandos, cabeceras y el rótulo de quién
 * está en la consola llevan el signo del vocabulario común (`lib/uiMarks.ts`): se fija con
 * `taggedPictogram`, la etiqueta exacta con el dibujo dentro y la palabra detrás.
 */

/** Un mando del panel: `<button class="command" …>` con su dibujo y su palabra. */
const command = (pictogram: string, word: string, attrs = ' type="button"') =>
  taggedPictogram("button", pictogram, word, ` class="command"${attrs}`);

/** El fuente del panel sin comentarios: lo que no debe llevar escrito se busca aquí. */
const PANEL_CODE = readFileSync(fileURLToPath(new URL("./PvtPanel.tsx", import.meta.url)), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

const protocol: PvtProtocol = {
  title: "TITULO-DEL-BACKEND",
  instructions: ["INSTRUCCION-1", "INSTRUCCION-2"],
  limits: ["LIMITE-LATENCIA", "LIMITE-LINEA-BASE"],
  notices: { premature: "AVISO-PREMATURA", abandoned: "AVISO-ABANDONO", no_response: "AVISO-SIN-RESPUESTA" },
  parameters: [
    {
      key: "lapse_threshold_ms",
      display: "PARAM-LAPSO",
      value: 500,
      value_text: "500 ms",
      basis: "repository",
      basis_display: "FUENTE-ESCRITA",
      note: "NOTA-LAPSO",
    },
    {
      key: "trials",
      display: "PARAM-ESTIMULOS",
      value: 20,
      value_text: "20",
      basis: "design",
      basis_display: "diseño de EMMA, sin fuente leída",
      note: "NOTA-ESTIMULOS",
    },
  ],
  session: {
    trials: 20,
    foreperiod_min_ms: 2000,
    foreperiod_max_ms: 10000,
    premature_response_ms: 0,
    abandon_after_ms: 10000,
  },
  result_fields: [
    { key: "mean_rt_ms", display: "CAMPO-MEDIA", unit_display: "ms", decimals: 0, recorded_as: "pvt-mean-rt" },
    { key: "false_starts", display: "CAMPO-FALSAS", unit_display: "", decimals: 0, recorded_as: null },
  ],
  records: [{ key: "pvt-mean-rt", display: "INDICATOR-MEAN", display_es: "INDICADOR-MEDIA" }],
  provenance: {
    source: "console-pvt",
    source_display: "test PVT en la consola",
    observation_type: "measured",
    evidence_context: "ground",
    effective_note: "NOTA-DE-HORA",
  },
  recorded_by: {
    required: true,
    label: "ROTULO-DE-QUIEN-ANOTA",
    note: "NOTA-DE-QUIEN-ANOTA",
    missing_display: "NO-CONSTA-DEL-BACKEND",
    legacy_note: "NOTA-DE-LO-ANTIGUO",
  },
  submit_to: "/api/pvt/console",
  notes: ["NOTA-DEL-BACKEND"],
};

const recorded: PvtRecordedSession = {
  effective: "2026-12-01T10:30:00+00:00",
  source: "console-pvt",
  source_display: "test PVT en la consola",
  recorded_by: "Ane Zubiri",
  recorded_by_display: "Ane Zubiri",
  observation_type: "measured",
  evidence_context: "ground",
  position: "current",
  position_note: "NOTA-DE-POSICION",
  values: [
    {
      key: "pvt-mean-rt",
      display: "INDICATOR-MEAN",
      display_es: "INDICADOR-MEDIA",
      value: 291,
      value_text: "291 ms",
    },
  ],
};

const at = (phase: Snapshot["phase"], over: Partial<Snapshot> = {}): Snapshot => ({
  ...IDLE,
  total: 20,
  phase,
  ...over,
});

function render(over: {
  protocol?: PvtProtocol | null;
  sessions?: PvtRecordedSession[] | null;
  snapshot?: Snapshot;
  sending?: boolean;
  submitted?: PvtSubmitted | null;
  failure?: RequestOutcome | null;
  unavailable?: RequestOutcome | null;
  operator?: string;
}): string {
  return renderToStaticMarkup(
    createElement(PvtView, {
      protocol,
      sessions: [],
      snapshot: IDLE,
      sending: false,
      submitted: null,
      failure: null,
      unavailable: null,
      operator: "CDR",
      onOperator: () => undefined,
      onStart: () => undefined,
      onRespond: () => undefined,
      onAbandon: () => undefined,
      ...over,
    }),
  );
}

/** El botón de respuesta, tal como queda en el HTML. */
function target(html: string): string {
  const match = html.match(/<button[^>]*data-pvt-target[\s\S]*?<\/button>/);
  if (match === null) throw new Error("no hay recuadro de respuesta");
  return match[0];
}

describe("panel de la prueba PVT, antes de empezar", () => {
  it("enseña las instrucciones y los límites con el texto del backend", () => {
    const html = render({});
    expect(html).toMatch(taggedPictogram("h2", "stopwatch", "TITULO-DEL-BACKEND</h2>"));
    expect(html).toMatch(taggedPictogram("h3", "bar-capped", "Límites de esta prueba</h3>"));
    expect(html).toContain("<li>INSTRUCCION-1</li>");
    expect(html).toContain("<li>LIMITE-LATENCIA</li>");
    expect(html).toContain("<li>LIMITE-LINEA-BASE</li>");
    expect(html).toContain("NOTA-DEL-BACKEND");
    expect(html).toContain("NOTA-DE-HORA");
  });

  it("cada parámetro va con su respaldo: lo que es diseño se dice con esas palabras", () => {
    const html = render({});
    expect(html).toMatch(/PARAM-LAPSO<\/th><td class="num">500 ms<\/td><td><span class="mark">/);
    expect(html).toMatch(/PARAM-ESTIMULOS<\/th><td class="num">20<\/td><td><span class="mark">/);
    expect(html).toContain("FUENTE-ESCRITA</span>");
    expect(html).toContain("diseño de EMMA, sin fuente leída</span>");
  });

  it("el respaldo lleva su forma junto a la palabra del backend: hoja escrita, lápiz o libro leído", () => {
    const read = { ...protocol.parameters[1]!, key: "min", basis: "read" as const, basis_display: "COINCIDE-CON-LO-LEIDO" };
    const html = render({ protocol: { ...protocol, parameters: [...protocol.parameters, read] } });
    expect(html).toMatch(markedHtml("sheet-lines", "FUENTE-ESCRITA"));
    expect(html).toMatch(markedHtml("pencil", "diseño de EMMA, sin fuente leída"));
    expect(html).toMatch(markedHtml("book-open", "COINCIDE-CON-LO-LEIDO"));
    // Sin color: de dónde sale un parámetro no es una alerta.
    const table = html.split("<table")[1]!.split("</table>")[0]!;
    expect(table).not.toMatch(/c-(red|yellow|blue|gray|cyan|magenta|green)/);
  });

  it("un respaldo que esta versión no conoce se enseña con su palabra y la forma de «desconocido»", () => {
    const odd = { ...protocol.parameters[0]!, basis: "otro" as never, basis_display: "RESPALDO-NUEVO" };
    const html = render({ protocol: { ...protocol, parameters: [odd] } });
    expect(html).toMatch(markedHtml("dot-small", "RESPALDO-NUEVO", "text"));
  });

  it("dice con qué procedencia se firma y qué queda en el registro, cada indicador con su familia", () => {
    const html = render({});
    expect(html).toContain("MEDIDO");
    expect(html).toContain("Tierra");
    expect(html).toContain("fuente: test PVT en la consola");
    expect(html).toMatch(markedHtml("stopwatch", "INDICADOR-MEDIA"));
  });

  it("dos indicadores en el registro van separados por punto y coma, cada uno con su forma", () => {
    const two = {
      ...protocol,
      records: [
        ...protocol.records,
        { key: "pvt-lapses", display: "INDICATOR-LAPSES", display_es: "INDICADOR-LAPSOS" },
      ],
    };
    const html = render({ protocol: two });
    expect(html).toMatch(/INDICADOR-MEDIA<\/span>; <span class="mark"><svg [^>]*data-pictogram="stopwatch"/);
    expect(html).toMatch(markedHtml("stopwatch", "INDICADOR-LAPSOS"));
  });

  it("pide quién está en la consola con el rótulo y la nota del backend", () => {
    const html = render({});
    expect(html).toMatch(taggedPictogram("label", "person", "ROTULO-DE-QUIEN-ANOTA <input", ' class="operator"'));
    expect(html).toMatch(/ROTULO-DE-QUIEN-ANOTA <input[^>]*value="CDR"/);
    expect(html).toContain('id="pvt-operator-note">NOTA-DE-QUIEN-ANOTA');
    expect(html).not.toContain("Falta el nombre");
  });

  it("sin nombre la prueba no se empieza: acabada, no se podría firmar", () => {
    for (const nobody of ["", "  ", "—"]) {
      const html = render({ operator: nobody });
      expect(html).toMatch(command("stopwatch", "Empezar", ' type="button" disabled=""'));
      expect(html).toContain("Falta el nombre de quien está en la consola");
      expect(html).toMatch(new RegExp(`<label class="operator">${pictogramSvg("person")}[^<]*<input[^>]*aria-invalid="true"`));
    }
  });

  it("se empieza con un botón, y no hay recuadro de respuesta hasta entonces", () => {
    const html = render({});
    expect(html).toMatch(command("stopwatch", "Empezar la prueba</button>"));
    expect(html).not.toContain("data-pvt-target");
  });

  it("con cifras del backend que no sirven no se puede empezar", () => {
    const html = render({ protocol: { ...protocol, session: { ...protocol.session, trials: 0 } } });
    expect(html).toMatch(command("stopwatch", "Empezar", ' type="button" disabled=""'));
  });

  it("mientras se envía no se puede empezar otra", () => {
    // El mando cambia de estado: mientras se envía lleva el dibujo de «cargando», no el cronómetro.
    expect(render({ sending: true })).toMatch(command("refresh", "Enviando…", ' type="button" disabled=""'));
  });

  it("sin protocolo dice que no hay dato, en cian con su anillo, y no ofrece la prueba", () => {
    const html = render({ protocol: null, unavailable: down("MOTIVO") });
    expect(html).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
    expect(html).not.toContain("<button");
  });

  it("antes de la primera respuesta dice que carga, con la flecha que gira, y no ofrece la prueba", () => {
    const html = render({ protocol: null, unavailable: null });
    expect(html).toMatch(markedHtml("refresh", "Cargando…</span>"));
    expect(html).not.toContain("<button");
  });
});

describe("panel de la prueba PVT, en curso", () => {
  it("la espera y la marca se distinguen por forma y por palabra, no solo por tono", () => {
    const waiting = target(render({ snapshot: at("waiting") }));
    const shown = target(render({ snapshot: at("stimulus") }));
    expect(waiting).toMatch(markedHtml("square-outline", "Espere", null, "pvt-target"));
    expect(shown).toMatch(markedHtml("shape-square", "Responda", null, "pvt-target"));
    expect(waiting).not.toContain('data-pictogram="shape-square"');
    expect(shown).not.toContain('data-pictogram="square-outline"');
    // La forma va grande sobre la palabra (`.pvt-target`), y la palabra es el único texto.
    expect(waiting).toContain('<span class="mark pvt-target">');
    expect(textNodes(waiting)).toEqual(["Espere"]);
    expect(textNodes(shown)).toEqual(["Responda"]);
  });

  it("la marca usa tonos neutros de la paleta: ni rojo ni amarillo ni otro color de señal", () => {
    for (const phase of ["waiting", "stimulus"] as const) {
      const html = target(render({ snapshot: at(phase) }));
      expect(html).toContain(phase === "stimulus" ? "color:var(--c-text)" : "color:var(--c-text-secondary)");
      expect(html).toContain("background:var(--c-raised)");
      for (const signal of ["red", "yellow", "blue", "gray", "cyan", "magenta", "green"]) {
        expect(html).not.toContain(`--c-${signal}`);
        expect(html).not.toContain(`c-${signal}`);
      }
      // Y ningún color escrito a mano.
      expect(html).not.toMatch(/#[0-9a-fA-F]{3,6}\b/);
      for (const hex of Object.values(palette)) expect(html).not.toContain(hex);
    }
  });

  it("no parpadea ni se anima", () => {
    for (const word of ["animation", "transition", "blink", "keyframes", "setInterval"]) {
      expect(PANEL_CODE).not.toContain(word);
    }
  });

  it("el recuadro es un botón enfocable y el abandono está al alcance del teclado", () => {
    const html = render({ snapshot: at("stimulus", { done: 4 }) });
    expect(target(html)).toMatch(/^<button type="button"/);
    expect(target(html)).toContain('aria-label="Marca en pantalla: responda"');
    expect(target(render({ snapshot: at("waiting") }))).toContain('aria-label="Espere a la marca"');
    expect(html).toMatch(command("cross", "Abandonar (Esc)</button>"));
    expect(html).not.toContain("tabindex=\"-1\"");
  });

  it("dice por qué estímulo va", () => {
    const html = render({ snapshot: at("waiting", { done: 4 }) });
    expect(html).toMatch(/Estímulo <span class="num">5<\/span> de <span class="num">20<\/span>/);
  });

  it("una respuesta antes de la marca se avisa con el texto del backend", () => {
    expect(render({ snapshot: at("waiting", { premature: true }) })).toContain("AVISO-PREMATURA");
    expect(render({ snapshot: at("waiting") })).not.toContain("AVISO-PREMATURA");
  });

  it("en curso no se enseña nada que distraiga: ni tabla ni botón de empezar", () => {
    const html = render({ snapshot: at("waiting"), sessions: [recorded] });
    expect(html).not.toContain("<table");
    expect(html).not.toContain("Empezar la prueba");
  });
});

describe("panel de la prueba PVT, al acabar", () => {
  it("abandonada: dice que no se envió nada, con el texto del backend", () => {
    const user = render({ snapshot: at("abandoned", { abandoned: "user" }) });
    expect(user).toContain("AVISO-ABANDONO");
    expect(user).not.toContain("AVISO-SIN-RESPUESTA");
    const silent = render({ snapshot: at("abandoned", { abandoned: "no-response" }) });
    expect(silent).toContain("AVISO-SIN-RESPUESTA");
    expect(user).not.toContain("Resultado");
    // Y se puede empezar otra.
    expect(user).toContain("Empezar la prueba");
  });

  it("enviada: enseña la puntuación del backend con sus nombres y los asientos", () => {
    const html = render({
      snapshot: at("finished", { done: 20 }),
      submitted: { result: { mean_rt_ms: 291, false_starts: 1, lapses: 2 }, recorded: [7, 8] },
      sessions: [recorded],
    });
    expect(html).toMatch(markedHtml("check", "Resultado, puntuado por el backend"));
    // Lo que queda en el registro es un indicador: su nombre lleva el dibujo de su familia.
    expect(html).toMatch(markedHtml("stopwatch", "CAMPO-MEDIA"));
    expect(html).toMatch(/CAMPO-MEDIA<\/span><\/th><td class="num">291 ms<\/td><td class="secondary"><span class="mark">/);
    expect(html).toMatch(markedHtml("check", "queda en el registro"));
    expect(html).toMatch(/CAMPO-FALSAS<\/th><td class="num">1<\/td><td class="secondary"><\/td>/);
    expect(html).toMatch(/Asientos del registro: <span class="num">7, 8<\/span>/);
    // Lo que no nombra el backend no se pinta.
    expect(html).not.toContain("lapses");
  });

  it("lo que quedó en el registro se enseña con su hora UTC y su procedencia", () => {
    const html = render({ sessions: [recorded] });
    expect(html).toContain("2026-12-01 10:30 UTC");
    // El indicador con la forma de su familia, y la cifra detrás.
    expect(html).toMatch(markedHtml("stopwatch", "INDICADOR-MEDIA"));
    expect(html).toContain("INDICADOR-MEDIA</span>: <span class=\"num\">291 ms</span>");
    expect(html).toContain("NOTA-DE-POSICION");
    expect(html).toContain("· test PVT en la consola");
    // Con qué fuente entró y quién tecleó, tal como quedó firmado.
    expect(html).toMatch(thSign("person", "ROTULO-DE-QUIEN-ANOTA</span></th>", ' scope="col"'));
    // Cada cabecera con su signo: hora, lecturas (valor), procedencia y en el estado.
    expect(html).toMatch(thSign("clock", "Hora</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("hash", "Lecturas</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("stamp", "Procedencia</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("toggle", "En el estado</span></th>", ' scope="col"'));
    expect(html).toMatch(taggedPictogram("h3", "clock-rewind", "Últimas pruebas en el registro</h3>"));
    expect(html).toContain('<td data-recorded-by="named"><span class="mark">Ane Zubiri</span></td>');
    expect(html).not.toContain("NOTA-DE-LO-ANTIGUO");
  });

  it("una prueba que llegó por la ruta de siempre dice su fuente y que no consta quién tecleó", () => {
    const old: PvtRecordedSession = {
      ...recorded,
      source: "pvt-test",
      source_display: "FUENTE-ANTIGUA",
      recorded_by: null,
      recorded_by_display: "NO-CONSTA-DEL-BACKEND",
    };
    // Mismo instante que la de la consola: son dos pruebas, y se pintan las dos.
    const html = render({ sessions: [recorded, old] });
    expect(html.match(/data-recorded-by=/g)).toHaveLength(2);
    expect(html).toContain("· FUENTE-ANTIGUA");
    // Gris («no disponible») con forma y con las palabras del backend, no un hueco: el círculo
    // tachado de toda la interfaz, la misma marca que el diario (`recordedByMark`, §5.33.12).
    const missing = html.split('<td data-recorded-by="missing">')[1]!.split("</td>")[0]!;
    expect(missing).toMatch(markedHtml("slash-circle", "NO-CONSTA-DEL-BACKEND", "gray"));
    expect(textNodes(missing)).toEqual(["NO-CONSTA-DEL-BACKEND"]);
    expect(html).toContain("NOTA-DE-LO-ANTIGUO");
    expect(missing).not.toContain("CDR");
    // Quien consta va sin forma: no hay nada que señalar.
    expect(html).toContain('<td data-recorded-by="named"><span class="mark">Ane Zubiri</span></td>');
  });

  it("una prueba que el estado aparta se marca con forma y palabra, no solo con color", () => {
    const html = render({
      sessions: [{ ...recorded, position: "after-reference", position_note: "APARTADA" }],
    });
    expect(html).toMatch(markedHtml("shape-triangle", "APARTADA", "yellow"));
    expect(html).toContain('<td data-position="after-reference">');
    // Y la que está en el estado, sin forma ni color.
    expect(render({ sessions: [recorded] })).toContain(
      '<td data-position="current"><span class="mark">NOTA-DE-POSICION</span></td>',
    );
  });

  it("una prueba que el estado no lee por su tipo lleva «no disponible», la misma marca que el diario (§5.39.11)", () => {
    const html = render({
      sessions: [
        { ...recorded, observation_type: "inferred", position: "not-analysed-by-type", position_note: "NO-POR-SU-TIPO" },
      ],
    });
    const cell = html.split('<td data-position="not-analysed-by-type">')[1]!.split("</td>")[0]!;
    expect(cell).toMatch(markedHtml("slash-circle", "NO-POR-SU-TIPO", "gray"));
    expect(html).not.toMatch(/c-(red|yellow|blue|magenta|green|cyan)/);
  });

  it("abandonada: el aviso lleva el círculo, sin color", () => {
    const html = render({ snapshot: at("abandoned", { abandoned: "user" }) });
    expect(html).toMatch(markedHtml("shape-circle", "AVISO-ABANDONO"));
  });

  it("el rechazo del backend se enseña tal cual, en amarillo con triángulo; la caída, con la cruz en rojo", () => {
    const refused = requestOutcome(new ApiError(422, "DETALLE-DEL-BACKEND"));
    const html = render({ snapshot: at("finished"), failure: refused });
    const alert = html.split('<p role="alert">')[1]!.split("</p>")[0]!;
    expect(alert).toMatch(markedHtml("shape-triangle", "El backend no confirmó la prueba: DETALLE-DEL-BACKEND", "yellow"));
    expect(html).not.toContain("Resultado");
    const broken = render({ snapshot: at("finished"), failure: down("CAIDA") });
    expect(broken).toMatch(markedHtml("cross", "El backend no confirmó la prueba: CAIDA", "red"));
  });

  it("sin pruebas lo dice, con la marca de registro vacío, sin color: la misma que el diario (§5.33.12)", () => {
    expect(render({})).toMatch(markedHtml("ring-dotted", "Ninguna prueba de este tripulante en el registro.</span>"));
  });

  it("con el registro sin leer (cargando o con fallo) no dice que esté vacío", () => {
    expect(render({ sessions: null })).not.toContain("Ninguna prueba");
    const failed = render({ sessions: null, unavailable: down("MOTIVO") });
    expect(failed).not.toContain("Ninguna prueba");
    expect(failed).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
  });

  it("las cabeceras de los parámetros llevan su signo: parámetro, valor y respaldo", () => {
    const html = render({});
    expect(html).toMatch(thSign("ruler", "Parámetro</span></th>", ' scope="col"'));
    expect(html).toMatch(thSign("hash", "Valor</span></th>", ' scope="col"'));
    // «Respaldo» es en qué se apoya el valor (`basis`), no «leído en la fuente»: el libro abierto
    // es solo uno de los respaldos posibles, y en la cabecera contradiría al lápiz de «sin fuente leída».
    expect(html).toMatch(thSign("pillars", "Respaldo</span></th>", ' scope="col"'));
  });

  it("sin protocolo, el título también lleva el cronómetro", () => {
    expect(render({ protocol: null, unavailable: down("MOTIVO") })).toMatch(taggedPictogram("h2", "stopwatch", "Prueba PVT</h2>"));
  });
});

describe("panel de la prueba PVT, lo publicado", () => {
  const quoted = (id: string, quote: string) => ({
    id,
    label: `ROTULO-${id}`,
    quote,
    ref: "ficha",
    source: "CITA-DE-LA-FUENTE",
    title: "TITULO",
    url: "URL-DE-LA-FUENTE",
    where: "SECCION",
    read_on: "2026-10-13",
    extent: "partial",
    extent_text: "leído en parte",
  });
  const read: PvtProtocol = {
    ...protocol,
    identity: "IDENTIDAD-DEL-BACKEND",
    parameters: [
      {
        ...protocol.parameters[0]!,
        scores: true,
        published: {
          status: "same_value",
          status_display: "ESTADO-DEL-BACKEND",
          values: [
            {
              variant: "larga",
              variant_display: "VERSION-LARGA",
              literal: "LITERAL-LARGO",
              value_ms: 1,
              same: true,
              marker_display: "MARCA-ES-EL-VALOR",
              statement: quoted("larga", "FRASE-LARGA"),
            },
            {
              variant: "corta",
              variant_display: "VERSION-CORTA",
              literal: "LITERAL-CORTO",
              value_ms: 2,
              same: false,
              marker_display: "MARCA-NO-ES-EL-VALOR",
              statement: quoted("corta", "FRASE-CORTA"),
            },
            {
              variant: "operador",
              variant_display: "VERSION-OPERADOR",
              literal: "LITERAL-OPERADOR",
              value_ms: 1,
              same: false,
              same_figure: true,
              match: "same_figure_different_operator",
              marker_display: "MARCA-MISMA-CIFRA-OTRO-OPERADOR",
              statement: quoted("operador", "FRASE-OPERADOR"),
            },
          ],
          see_also: [quoted("limite", "FRASE-LIMITE")],
          difference: "DIFERENCIA-DEL-BACKEND",
        },
      },
      {
        ...protocol.parameters[1]!,
        scores: false,
        published: {
          status: "not_comparable",
          status_display: "NO-COMPARABLE",
          values: [
            {
              variant: "larga",
              variant_display: "VERSION-LARGA",
              literal: "LITERAL-DURACION",
              value_ms: 3,
              same: false,
              marker_display: null,
              statement: quoted("duracion", "FRASE-DURACION"),
            },
          ],
          see_also: [],
          difference: "DIFERENCIA-ESTIMULOS",
        },
      },
    ],
    published: {
      note: "NOTA-DE-LO-LEIDO",
      read_on: "2026-10-13",
      sources: [
        {
          ref: "ficha",
          title: "TITULO",
          source: "CITA",
          url: "URL-DE-LA-FUENTE",
          extent: "partial",
          extent_text: "leído en parte",
          what: "QUE-SE-LEYO",
        },
      ],
      context: [quoted("poblacion", "FRASE-POBLACION")],
      outcomes_note: "NOTA-DE-MEDIDAS",
      not_found: ["NO-ENCONTRADO"],
    },
  };

  it("dice qué prueba es con el texto del backend", () => {
    expect(render({ protocol: read })).toContain("<p>IDENTIDAD-DEL-BACKEND</p>");
  });

  it("cada valor publicado va con su versión, su frase en su idioma y su origen", () => {
    const html = render({ protocol: read });
    expect(html).toMatch(/<strong>VERSION-LARGA<\/strong>: <span class="num" lang="en">LITERAL-LARGO/);
    expect(html).toContain('<q lang="en">FRASE-LARGA</q>');
    expect(html).toContain('<q lang="en">FRASE-CORTA</q>');
    expect(html).toContain("SECCION · CITA-DE-LA-FUENTE · leído en parte · leído el 2026-10-13");
    expect(html).toContain("URL-DE-LA-FUENTE");
    expect(html).toContain("ROTULO-limite");
    expect(html).toContain('<q lang="en">FRASE-LIMITE</q>');
  });

  it("cuál es el valor de EMMA lo dice la marca del backend, tal cual, y la diferencia también", () => {
    const html = render({ protocol: read });
    const lapse = html.split('data-pvt-published="lapse_threshold_ms"')[1]!.split("</article>")[0]!;
    expect(lapse).toContain("entra en la puntuación");
    // El estado del backend, con la forma de «igual» y sin color.
    expect(lapse).toContain('<div data-status-mark=""><span class="mark"><svg');
    expect(lapse).toMatch(markedHtml("equals", "ESTADO-DEL-BACKEND"));
    expect(lapse).toMatch(/LITERAL-LARGO<\/span> <span class="secondary">MARCA-ES-EL-VALOR/);
    expect(lapse).toMatch(/LITERAL-CORTO<\/span> <span class="secondary">MARCA-NO-ES-EL-VALOR/);
    // Misma cifra con otro operador (el lapso, 2026-10-20): la marca es la del backend, no «=».
    expect(lapse).toMatch(
      /LITERAL-OPERADOR<\/span> <span class="secondary">MARCA-MISMA-CIFRA-OTRO-OPERADOR/,
    );
    // La interfaz no redacta la marca: ni «=» ni «≠» salen de aquí.
    expect(lapse).not.toContain("es el valor de EMMA");
    expect(lapse).toContain("DIFERENCIA-DEL-BACKEND");
    expect(lapse).not.toMatch(/c-(red|yellow|green|cyan)/);
  });

  it("lo que no es comparable no lleva marca, y lo que no puntúa no dice que puntúa", () => {
    const html = render({ protocol: read });
    const trials = html.split('data-pvt-published="trials"')[1]!.split("</article>")[0]!;
    expect(trials).toMatch(markedHtml("dash", "NO-COMPARABLE"));
    expect(trials).not.toContain("es el valor de EMMA");
    expect(trials).not.toMatch(/LITERAL-DURACION<\/span> <span class="secondary">/);
    expect(trials).not.toContain("entra en la puntuación");
  });

  it("enseña con quién se estudió, las fuentes y lo que no se encontró", () => {
    const html = render({ protocol: read });
    expect(html).toContain("NOTA-DE-LO-LEIDO");
    expect(html).toContain('<q lang="en">FRASE-POBLACION</q>');
    expect(html).toContain("NOTA-DE-MEDIDAS");
    expect(html).toContain("CITA · leído en parte: QUE-SE-LEYO");
    expect(html).toContain("<li>NO-ENCONTRADO</li>");
    // El plegable, cada parámetro y los dos apartados finales, con su signo.
    expect(html).toMatch(taggedPictogram("summary", "bars-two", "Lo publicado y lo que hace EMMA</summary>"));
    expect(html).toMatch(taggedPictogram("h4", "ruler", "PARAM-LAPSO: "));
    expect(html).toMatch(taggedPictogram("h4", "book-open", "Fuentes leídas</h4>"));
    expect(html).toMatch(taggedPictogram("h4", "magnifier", "Buscado y no encontrado, o no leído</h4>"));
  });

  it("si el backend no da lo leído, el panel no inventa el apartado", () => {
    expect(render({})).not.toContain("Lo publicado");
  });

  it("durante la prueba no se enseña", () => {
    expect(render({ protocol: read, snapshot: at("waiting") })).not.toContain("Lo publicado");
  });
});

describe("panel de la prueba PVT, las divergencias con lo publicado", () => {
  const quoted = (id: string, quote: string) => ({
    id,
    label: `ROTULO-${id}`,
    quote,
    ref: "ficha",
    source: "CITA-DE-LA-FUENTE",
    title: "TITULO",
    url: "URL-DE-LA-FUENTE",
    where: "SECCION",
    read_on: "2026-10-13",
    extent: "partial",
    extent_text: "leído en parte",
  });
  const declared: PvtProtocol = {
    ...protocol,
    divergences: {
      note: "NOTA-DE-DIVERGENCIAS",
      items: [
        {
          key: "lapse_operator",
          display: "NOMBRE-OPERADOR",
          emma: "EMMA-CUENTA-ASI",
          published: "LA-FUENTE-CUENTA-ASI",
          status: "differs",
          status_display: "DIFIERE-DEL-BACKEND",
          consequence: "CONSECUENCIA-DEL-BACKEND",
          scores: true,
          kept: "SIN-CAMBIAR-DEL-BACKEND",
          sources: [quoted("lapso", "FRASE-LAPSO"), quoted("tabla", "FRASE-TABLA")],
          not_found: [],
        },
        {
          key: "no_response",
          display: "NOMBRE-SIN-RESPUESTA",
          emma: "EMMA-ABANDONA",
          published: "LA-FUENTE-ESPERA",
          status: "differs",
          status_display: "DIFIERE-DEL-BACKEND",
          consequence: "OTRA-CONSECUENCIA",
          scores: false,
          kept: "SIN-CAMBIAR-DEL-BACKEND",
          sources: [quoted("espera", "FRASE-ESPERA")],
          not_found: [],
        },
        {
          key: "min_trials",
          display: "NOMBRE-MINIMO",
          emma: "EMMA-RECHAZA",
          published: "SIN-VALOR-PUBLICADO",
          status: "not_published",
          status_display: "SIN-PUBLICAR-DEL-BACKEND",
          consequence: "ES-DISENO",
          scores: true,
          kept: "SIN-CAMBIAR-DEL-BACKEND",
          sources: [],
          not_found: ["BUSCADO-Y-NO-ENCONTRADO"],
        },
      ],
    },
  };
  const block = (html: string) =>
    html.split("<details data-pvt-divergences")[1]!.split("</details>")[0]!;
  const one = (html: string, key: string) =>
    html.split(`data-pvt-divergence="${key}"`)[1]!.split("</article>")[0]!;

  it("van plegadas bajo el protocolo, con cuántas son y la nota del backend", () => {
    const html = render({ protocol: declared });
    expect(html).toMatch(
      taggedPictogram(
        "summary",
        "not-equal",
        'Divergencias con lo publicado: <span class="num">3</span></summary>',
      ),
    );
    expect(html).toContain('<details data-pvt-divergences=""><summary>');
    expect(block(html)).toContain("NOTA-DE-DIVERGENCIAS");
    // Debajo de los parámetros. En el tablero, el protocolo entero va en «Ver detalle», después de
    // quién está en la consola y del mando de empezar (2026-11-08, una pantalla por sección).
    expect(html.indexOf("PARAM-LAPSO")).toBeLessThan(html.indexOf("data-pvt-divergences"));
    expect(html.indexOf("ROTULO-DE-QUIEN-ANOTA")).toBeLessThan(html.indexOf("Ver detalle: protocolo, instrucciones y fuentes"));
    expect(html.indexOf("Ver detalle: protocolo, instrucciones y fuentes")).toBeLessThan(html.indexOf("data-pvt-divergences"));
  });

  it("en la concha clásica siguen debajo de los parámetros y antes de quién está en la consola", () => {
    const html = renderToStaticMarkup(
      createElement(LookContext.Provider, { value: "classic" }, createElement(PvtView, {
        protocol: declared,
        sessions: [],
        snapshot: IDLE,
        sending: false,
        submitted: null,
        failure: null,
        unavailable: null,
        operator: "CDR",
        onOperator: () => undefined,
        onStart: () => undefined,
        onRespond: () => undefined,
        onAbandon: () => undefined,
      })),
    );
    expect(html).not.toContain("Ver detalle");
    expect(html.indexOf("PARAM-LAPSO")).toBeLessThan(html.indexOf("data-pvt-divergences"));
    expect(html.indexOf("data-pvt-divergences")).toBeLessThan(html.indexOf("ROTULO-DE-QUIEN-ANOTA"));
  });

  it("cada una dice lo que hace EMMA, lo publicado y la consecuencia, con el texto del backend", () => {
    const html = one(render({ protocol: declared }), "lapse_operator");
    expect(html).toMatch(taggedPictogram("h4", "ruler", 'NOMBRE-OPERADOR<span class="secondary"> · entra en la puntuación'));
    // Cada clave con su signo (§5.33.12): engranaje, libro abierto, bocadillo; ninguno repetido.
    expect(html).toMatch(taggedPictogram("dt", "gear", "EMMA</dt><dd>EMMA-CUENTA-ASI</dd>"));
    expect(html).toMatch(taggedPictogram("dt", "book-open", "Lo publicado</dt><dd>LA-FUENTE-CUENTA-ASI</dd>"));
    expect(html).toMatch(taggedPictogram("dt", "bubble-lines", "Consecuencia</dt><dd>CONSECUENCIA-DEL-BACKEND</dd>"));
    expect(html).toMatch(markedHtml("not-equal", "DIFIERE-DEL-BACKEND"));
  });

  it("con la frase de la fuente en su idioma y su ubicación", () => {
    const html = one(render({ protocol: declared }), "lapse_operator");
    expect(html).toContain("ROTULO-lapso");
    expect(html).toContain('<q lang="en">FRASE-LAPSO</q>');
    expect(html).toContain('<q lang="en">FRASE-TABLA</q>');
    expect(html).toContain("SECCION · CITA-DE-LA-FUENTE · leído en parte · leído el 2026-10-13");
    expect(html).toContain("URL-DE-LA-FUENTE");
  });

  it("lo que no puntúa no dice que puntúa", () => {
    expect(one(render({ protocol: declared }), "no_response")).not.toContain("entra en la puntuación");
  });

  it("sin valor publicado: en gris, sin frase inventada, y lo que se buscó", () => {
    const html = one(render({ protocol: declared }), "min_trials");
    expect(html).toContain('<div data-status-mark=""><span class="mark c-gray"><svg');
    expect(html).toMatch(markedHtml("slash-circle", "SIN-PUBLICAR-DEL-BACKEND", "gray"));
    expect(html).not.toContain("<q");
    expect(html).toContain("<li>BUSCADO-Y-NO-ENCONTRADO</li>");
    expect(html).toMatch(markedHtml("magnifier", "Buscado y no encontrado en lo leído:"));
  });

  it("ninguna es una alerta: ni rojo, ni amarillo, ni cian, ni color escrito a mano", () => {
    const html = block(render({ protocol: declared }));
    for (const signal of ["red", "yellow", "blue", "cyan", "magenta", "green"]) {
      expect(html).not.toContain(`c-${signal}`);
    }
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,6}\b/);
    for (const hex of Object.values(palette)) expect(html).not.toContain(hex);
    // Lo que difiere va sin clase de color: forma y palabra.
    expect(one(html, "lapse_operator")).toContain('<div data-status-mark=""><span class="mark"><svg');
  });

  it("lo que no se cambió se dice una vez, no en cada una", () => {
    const html = block(render({ protocol: declared }));
    expect(html.split("SIN-CAMBIAR-DEL-BACKEND")).toHaveLength(2);
  });

  it("si el backend no las da, el panel no inventa el apartado", () => {
    expect(render({})).not.toContain("Divergencias");
  });

  it("durante la prueba no se enseñan", () => {
    expect(render({ protocol: declared, snapshot: at("waiting") })).not.toContain("Divergencias");
  });
});

describe("el panel no puntúa ni interpreta", () => {
  const code = PANEL_CODE;

  it("no califica el resultado ni usa el rojo", () => {
    // Las dos últimas se componen para que tampoco este fichero las lleve escritas: la
    // palabra que daría la prueba por comprobada y el nombre de una variante publicada.
    const claimed = ["valid" + "ad", "PVT" + "-B"];
    for (const word of ["normal", "preocupante", "fatiga", "lento", "c-red", ...claimed]) {
      expect(code).not.toContain(word);
    }
  });

  it("no nombra ninguna fuente ni rellena a quien no consta: son palabras del backend", () => {
    for (const word of ["no consta", "pvt-test", "console-pvt", "test PVT"]) {
      expect(code).not.toContain(word);
    }
  });

  it("no trae umbrales ni duraciones: las cifras de la prueba son del backend", () => {
    // «100%» es el ancho del recuadro, no un tiempo.
    expect(code).not.toMatch(/\b(500|100|2000|10000|20)\b(?!%)/);
  });

  it("mide con performance.now() y no pone la hora de la lectura", () => {
    expect(code).toContain("performance.now()");
    expect(code).not.toMatch(/Date\.now|new Date\(\)|effective:/);
  });

  it("ningún carácter de forma ni trazo queda escrito: toda forma es un pictograma junto a su palabra", () => {
    expect(code).not.toMatch(/[○◇△■□●◐▷◌⊘✕✓≠≈]/);
    expect(code).not.toMatch(/<svg|<path|aria-hidden/);
  });
});

describe("PVT en el tablero (concha de la maqueta, 2026-11-07)", () => {
  /** Las fichas de la última prueba, tal como quedan en el HTML. */
  const tiles = (html: string) => html.match(/<div class="board-stats pvt-board"[\s\S]*?(?=<div class="quality-table")/)?.[0] ?? null;

  it("las lecturas de la última prueba van como fichas con el `value_text` del backend y su familia", () => {
    const html = tiles(render({ sessions: [recorded] }));
    expect(html).not.toBeNull();
    expect(html).toContain('aria-label="Última prueba en el registro"');
    expect(html).toContain("INDICADOR-MEDIA");
    expect(html).toContain('<span class="num">291 ms</span>');
    expect(html).toMatch(new RegExp(pictogramSvg("stopwatch")));
  });

  it("con la relectura caída las fichas conservan lo de antes, en cursiva", () => {
    const html = render({ sessions: [recorded], unavailable: down("CAIDO") });
    expect(html).toContain('<div class="stat-tile stale">');
  });

  it("sin pruebas no hay fichas, y en la concha clásica tampoco", () => {
    expect(render({ sessions: [] })).not.toContain("pvt-board");
    const classic = renderToStaticMarkup(
      createElement(LookContext.Provider, { value: "classic" }, createElement(PvtView, {
        protocol,
        sessions: [recorded],
        snapshot: IDLE,
        sending: false,
        submitted: null,
        failure: null,
        unavailable: null,
        operator: "CDR",
        onOperator: () => undefined,
        onStart: () => undefined,
        onRespond: () => undefined,
        onAbandon: () => undefined,
      })),
    );
    expect(classic).not.toContain("pvt-board");
    expect(classic).toContain("291 ms");
  });
});
