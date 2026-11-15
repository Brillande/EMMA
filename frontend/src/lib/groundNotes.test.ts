import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, textLines } from "../advisor/visibleText";
import { LookContext } from "../components/BoardOnly";
import { GroundNotesOnBoard } from "../dashboard/GroundNotesPanel";
import { GroundNotesSent, NotesTally, transitMark } from "../ground/GroundNotesComposer";
import { ApiError, type GroundNotes } from "./api";
import { arrivalCut } from "./crew";
import { noteKindMark, noteTransit } from "./groundNotes";
import { requestOutcome } from "./marks";
import { uiPictogram } from "./uiMarks";

/**
 * Las notas de Tierra a bordo (§5.38.1). Qué se puede firmar y que a bordo solo llega lo firmado
 * antes del corte lo prueba el backend (`tests/test_ground_notes.py`); aquí, que las dos consolas
 * cuentan el tránsito con el mismo corte, que la de tripulación pide con él y que el texto y las
 * palabras se pintan como las da el backend.
 */

const SIGNED = "2026-10-27T10:00:00Z";
const minutes = (count: number) => count * 60_000;

const notes: GroundNotes = {
  subject: "crew-01",
  until: null,
  notes: [
    {
      ledger_index: 7,
      kind: "question",
      kind_display: "PALABRA-PREGUNTA",
      text: "TEXTO-TAL-CUAL ¿Puede repetir la medida?",
      signed_by: "Dra. Ruiz",
      signed_at: "2026-10-27T10:00:00+00:00",
      addressed_to: "crew-01",
      addressed_to_display: "crew-01",
    },
    {
      ledger_index: 9,
      kind: "information",
      kind_display: "PALABRA-INFORMACION",
      text: "SEGUNDA-NOTA",
      signed_by: "CAPCOM",
      signed_at: "2026-10-27T10:30:00+00:00",
      addressed_to: "tripulacion",
      addressed_to_display: "toda la tripulación",
    },
  ],
  withheld: 0,
  withheld_note: null,
  basis: "BASE-DEL-BACKEND",
};

describe("dónde está una nota firmada", () => {
  it("a bordo si se firmó antes del corte de ahora; llega un tiempo de luz después de firmarse", () => {
    const now = Date.parse(SIGNED) + minutes(20);
    expect(noteTransit(SIGNED, 20, now)).toEqual({ state: "on-board", at: new Date(now) });
    const early = Date.parse(SIGNED) + minutes(19);
    expect(noteTransit(SIGNED, 20, early)).toEqual({ state: "in-transit", at: new Date(Date.parse(SIGNED) + minutes(20)) });
  });

  it("con el mismo corte que pide la consola de tripulación (`recorded <= until`)", () => {
    for (const offset of [-1, 0, 1]) {
      const now = Date.parse(SIGNED) + minutes(12.5) + offset;
      const cut = arrivalCut(12.5, now);
      const onBoard = cut !== undefined && Date.parse(SIGNED) <= cut.getTime();
      expect(noteTransit(SIGNED, 12.5, now).state).toBe(onBoard ? "on-board" : "in-transit");
    }
  });

  it("sin efemérides no se sabe; una hora ilegible no se pinta como otra", () => {
    expect(noteTransit(SIGNED, null, Date.parse(SIGNED))).toEqual({ state: "unknown" });
    expect(() => noteTransit("ayer", 20, Date.now())).toThrow(RangeError);
    expect(transitMark({ state: "unknown" }).mark.color).toBe("cyan");
  });

  it("la clase lleva su signo sin color: una nota no es una alerta", () => {
    expect(noteKindMark("question")).toMatchObject({ pictogram: "question", color: null });
    expect(noteKindMark("information")).toMatchObject({ pictogram: "circle-i", color: null });
    expect(noteKindMark("orden").pictogram).toBe("dot-small");
  });
});

describe("<GroundNotesOnBoard> (consola de tripulación)", () => {
  const render = (
    data: GroundNotes | null,
    oneWayMinutes: number | null = 20,
    unavailable: ReturnType<typeof requestOutcome> | null = null,
  ) => renderToStaticMarkup(createElement(GroundNotesOnBoard, { data, unavailable, oneWayMinutes }));

  it("pide con el corte del reloj, cada 30 s, y lo pintado es del tripulante que se mira", () => {
    const source = readFileSync(fileURLToPath(new URL("../dashboard/GroundNotesPanel.tsx", import.meta.url)), "utf8");
    expect(source).toContain("const { checkKey, cutNow } = useArrivalCheck(oneWayMinutes);");
    expect(source).toContain(".list(subject, cutNow())");
    expect(source).toContain("}, [subject, checkKey, cutNow]);");
    expect(source).toContain("loaded?.subject === subject ? loaded.body : null");
    const crew = readFileSync(fileURLToPath(new URL("../dashboard/CrewConsole.tsx", import.meta.url)), "utf8");
    expect(crew).toContain(
      "<GroundNotesPanel subject={status.subject} oneWayMinutes={status.comms?.one_way_minutes ?? null} comms={commsStatusOf(status)} />",
    );
  });

  it("pinta el texto y las palabras del backend tal cual, la última arriba, sin mandos", () => {
    const html = render(notes);
    expect(html).toMatch(taggedPictogram("h2", uiPictogram("groundNotes"), "Notas de Tierra</h2>"));
    const lines = textLines(html);
    expect(lines).toContain("TEXTO-TAL-CUAL ¿Puede repetir la medida?");
    expect(lines).toContain("BASE-DEL-BACKEND");
    expect(html.indexOf("SEGUNDA-NOTA")).toBeLessThan(html.indexOf("TEXTO-TAL-CUAL"));
    expect(html).toMatch(markedHtml("question", "PALABRA-PREGUNTA"));
    expect(html).toMatch(markedHtml("circle-i", "PALABRA-INFORMACION"));
    expect(lines.join(" ")).toContain("para toda la tripulación");
    // Tablero (2026-11-08): la hora de firma, en su columna a la izquierda de la nota.
    expect(lines.join(" ")).toContain("2026-10-27 10:00 UTC PALABRA-PREGUNTA · para crew-01");
    expect(lines.join(" ")).toContain("Firmada en Tierra por Dra. Ruiz");
    expect(html).toContain('<span class="num">2026-10-27 10:00 UTC</span>');
    expect(html).not.toContain("<form");
    // El único mando es el «Ver detalle» del tablero (la base); ninguno sobre las notas.
    expect(html.match(/<button/g) ?? []).toHaveLength(1);
    expect(html).toContain('class="command board-detail-toggle"');
  });

  it("en la clásica cada nota sigue como antes: firma y hora en la misma línea, y la base a la vista", () => {
    const html = renderToStaticMarkup(
      createElement(
        LookContext.Provider,
        { value: "classic" },
        createElement(GroundNotesOnBoard, { data: notes, unavailable: null, oneWayMinutes: 20 }),
      ),
    );
    const lines = textLines(html);
    expect(lines.join(" ")).toContain("Firmada en Tierra por Dra. Ruiz, 2026-10-27 10:00 UTC");
    expect(lines).toContain("BASE-DEL-BACKEND");
    expect(html).not.toContain("ground-notes-board");
    expect(html).not.toContain("<button");
  });

  it("tablero (2026-11-08): la base de lo que llega, detrás de «Ver detalle»; el retardo, a la vista", () => {
    const html = render(notes);
    expect(html).toMatch(/<div id="[^"]+" class="board-detail-body" hidden="">\s*<p class="secondary">BASE-DEL-BACKEND<\/p><\/div>/);
    expect(html.indexOf("Llega lo firmado en Tierra hace más de")).toBeLessThan(html.indexOf("board-detail"));
    expect(html).not.toMatch(/hidden=""[^]*Llega lo firmado/);
  });

  it("tablero (2026-11-07): píldoras con las llegadas, cada clase con su signo y su palabra, y las no enseñadas en gris", () => {
    const tallyOf = (html: string) => /<ul class="board-tally" aria-label="Notas por clase">([\s\S]*?)<\/ul>/.exec(html)?.[1] ?? null;
    const plain = tallyOf(render(notes));
    expect(plain).not.toBeNull();
    expect(textLines(plain ?? "")).toEqual(["llegadas 2", "PALABRA-PREGUNTA 1", "PALABRA-INFORMACION 1"]);
    expect(plain).toMatch(markedHtml(uiPictogram("groundNotes"), "llegadas</span>"));
    expect(plain).toMatch(markedHtml("question", "PALABRA-PREGUNTA</span>"));
    expect(plain).toMatch(markedHtml("circle-i", "PALABRA-INFORMACION</span>"));
    expect(plain).not.toMatch(/c-(gray|yellow|red|cyan)/);
    const withheld = tallyOf(render({ ...notes, withheld: 3, withheld_note: "RETENIDAS" })) ?? "";
    expect(withheld).toMatch(
      /<li class="ref-pill board-pill" style="--lvl:var\(--c-gray\)"><span class="mark c-gray"><svg [^>]*data-pictogram="slash-circle">.*?<\/svg>no enseñadas<\/span> <span class="num">3<\/span><\/li>$/,
    );
    // Sin notas ni retenidas no hay píldoras; retenidas sin notas, solo la suya.
    expect(tallyOf(render({ ...notes, notes: [] }))).toBeNull();
    expect(textLines(tallyOf(render({ ...notes, notes: [], withheld: 1, withheld_note: "RETENIDAS" })) ?? "")).toEqual(["no enseñadas 1"]);
    // Las píldoras solo cuentan: quién firma y a quién va siguen en cada nota, no en ellas.
    expect(plain).not.toContain("Dra. Ruiz");
  });

  it("dice el retardo; sin efemérides, que no se aplica, con la marca de dato ausente", () => {
    expect(textLines(render(notes, 20)).join(" ")).toContain("lo posterior está en camino.");
    expect(render(notes, null)).toMatch(markedHtml("ring-dotted", "Sin efemérides: no se puede aplicar el retardo.", "cyan"));
  });

  it("vacío, cargando, con notas retenidas o sin respuesta: cada uno con su marca", () => {
    expect(render({ ...notes, notes: [] })).toMatch(markedHtml("ring-dotted", "Ninguna nota de Tierra ha llegado."));
    expect(render(null)).toMatch(markedHtml("refresh", "Leyendo las notas…"));
    const withheld = render({ ...notes, withheld: 1, withheld_note: "RETENIDAS" });
    expect(withheld).toMatch(markedHtml("slash-circle", "RETENIDAS", "gray"));
    const failed = render(null, 20, requestOutcome(new ApiError(409, "ROTO")));
    expect(failed).toMatch(markedHtml("shape-triangle", "No se pudieron leer las notas: ROTO", "yellow"));
    const stale = render(notes, 20, requestOutcome(new ApiError(409, "OCUPADO")));
    expect(stale).toMatch(markedHtml("shape-triangle", "No se pudo actualizar: OCUPADO", "yellow"));
    expect(textLines(stale)).toContain("SEGUNDA-NOTA");
  });
});

describe("<GroundNotesSent> (consola de Tierra)", () => {
  const render = (oneWayMinutes: number | null, now: number) =>
    renderToStaticMarkup(createElement(GroundNotesSent, { data: notes, unavailable: null, oneWayMinutes, now }));

  it("cada nota firmada dice si ya está a bordo o cuándo llega", () => {
    const html = render(20, Date.parse("2026-10-27T10:40:00Z"));
    expect(html).toMatch(markedHtml("check", "a bordo desde"));
    expect(html).toContain('<span class="num">2026-10-27 10:20 UTC</span>');
    expect(html).toMatch(markedHtml(uiPictogram("lightTime"), "en camino: llega hacia"));
    expect(html).toContain('<span class="num">2026-10-27 10:50 UTC</span>');
  });

  it("sin efemérides, que no se sabe cuándo llega", () => {
    expect(render(null, Date.now())).toMatch(markedHtml("ring-dotted", "sin efemérides no se sabe cuándo llega", "cyan"));
  });

  it("la consola de Tierra lleva el panel, con el tiempo de luz del estado", () => {
    const ground = readFileSync(fileURLToPath(new URL("../ground/GroundConsole.tsx", import.meta.url)), "utf8");
    expect(ground).toContain("<GroundNotesComposer subject={status.subject} oneWayMinutes={oneWay} />");
    const composer = readFileSync(fileURLToPath(new URL("../ground/GroundNotesComposer.tsx", import.meta.url)), "utf8");
    // Las reglas y su frase son del backend; la interfaz no decide qué texto vale.
    expect(composer).toContain("groundNotesApi\n      .rules()");
    expect(composer).toContain("<p className=\"secondary\">{rules.refused}</p>");
    // Un borrador para un tripulante no se firma para el siguiente al cambiar de tripulante.
    expect(composer).toContain("<NoteForm key={subject} subject={subject}");
  });
});

describe("<NotesTally> (tablero de Tierra)", () => {
  const tally = (oneWayMinutes: number | null, now: number) =>
    renderToStaticMarkup(createElement(NotesTally, { notes: notes.notes, oneWayMinutes, now }));

  it("cuántas firmadas y cuántas a bordo o en camino, con la marca del tránsito de su fila", () => {
    const html = tally(20, Date.parse("2026-10-27T10:40:00Z"));
    expect(html).toMatch(/Firmadas<\/span> <span class="num">2<\/span>/);
    expect(html).toMatch(markedHtml("check", "a bordo"));
    expect(html).toMatch(markedHtml(uiPictogram("lightTime"), "en camino"));
    expect(html).not.toContain("sin saber");
    // Las retenidas cuentan como firmadas, sin sitio; y un refresco fallido las pone en cursiva.
    const withheld = renderToStaticMarkup(
      createElement(NotesTally, { notes: notes.notes, withheld: 1, oneWayMinutes: 20, now: Date.now(), stale: true }),
    );
    expect(withheld).toMatch(/Firmadas<\/span> <span class="num">3<\/span>/);
    expect(withheld).toContain(' stale');
  });

  it("sin efemérides, el cian del dato ausente; y nunca un nombre", () => {
    const html = tally(null, Date.now());
    expect(html).toMatch(markedHtml("ring-dotted", "sin saber cuándo llega", "cyan"));
    for (const name of ["Dra. Ruiz", "CAPCOM", "crew-01", "toda la tripulación"]) expect(html).not.toContain(name);
  });
});
