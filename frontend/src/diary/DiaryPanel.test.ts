import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, pictogramSvg, taggedPictogram, thSign, textLines } from "../advisor/visibleText";
import type { DiaryCatalog, DiaryEntry } from "../lib/api";
import { uiPictogram } from "../lib/uiMarks";
import { DiaryView, clampable, distinctTail } from "./DiaryPanel";
import type { Draft, Outcome } from "./entry";
import { ApiError } from "../lib/api";
import { type RequestOutcome, requestOutcome } from "../lib/marks";

/** Una lectura que cayó (5xx): la marca de fallo con el motivo tal cual (§5.34.14). */
const down = (text: string): RequestOutcome => requestOutcome(new ApiError(503, text));

/**
 * El panel pinta lo que da el backend: nombres, rango, nota de escala, procedencia y lo que
 * quedó en el registro. No rotula una escala ni interpreta un valor. Cada forma es un
 * pictograma SVG junto a la palabra (§5.32): aquí se fija por su `data-pictogram`.
 */

/** «Registrar» sin poder enviarse; con la segunda pasada es un `Command` (`class="command"`). */
const SUBMIT_DISABLED = /<button class="command" type="submit"[^>]*disabled=""/;
/** «Registrar» activo: sin `disabled`, con la pluma de «registrar» delante de la palabra. */
const SUBMIT_ENABLED = taggedPictogram("button", uiPictogram("register"), "Registrar", ' class="command" type="submit"');

/** Un bloque sin la cabecera de su plegable: para contar los dibujos de lo que guarda. */
const withoutSummary = (block: string): string => block.replace(/<summary>[\s\S]*?<\/summary>/g, "");

const catalog: DiaryCatalog = {
  indicators: [
    {
      key: "mood-valence",
      display: "Self-reported mood valence",
      display_es: "Valencia del ánimo autoinformada",
      unit: "{score}",
      unit_display: "puntos",
      domain: "behavioral",
      decimals: 1,
      physical_min: 0,
      physical_max: 10,
      range_text: "de 0,0 a 10,0",
      equipment: "autoinforme",
      mode_display: "periódico, no invasivo",
      scale: {
        described_as: "escala breve de autoinforme propia de la misión",
        labels: null,
        labels_note: "escala sin rótulos verificados",
        concerning: "low",
        concerning_note: "El catálogo vigila el extremo bajo.",
      },
    },
    {
      key: "fluid-intake-24h",
      display: "Fluid intake total 24 hour",
      display_es: "Ingesta total de líquidos en 24 horas",
      unit: "mL/(24.h)",
      unit_display: "mL/24 h",
      domain: "genitourinary",
      decimals: 0,
      physical_min: 0,
      physical_max: 20000,
      range_text: "de 0 a 20 000",
      equipment: "registro de ingesta",
      mode_display: "periódico, no invasivo",
      scale: null,
    },
  ],
  provenance: {
    source: "crew-diary",
    source_display: "registro diario",
    observation_type: "measured",
    evidence_context: "ground",
  },
  recorded_by: {
    required: true,
    label: "ROTULO-DE-QUIEN-ANOTA",
    note: "NOTA-DE-QUIEN-ANOTA",
    missing_display: "NO-CONSTA-DEL-BACKEND",
    legacy_note: "NOTA-DE-LO-ANTIGUO",
  },
  submit_to: "/api/diary/entries",
  notes: ["NOTA-DEL-BACKEND"],
};

const entry: DiaryEntry = {
  key: "mood-valence",
  display: "Self-reported mood valence",
  display_es: "Valencia del ánimo autoinformada",
  value: 6.5,
  value_text: "6,5 puntos",
  effective: "2026-12-01T10:30:00+00:00",
  source: "crew-diary",
  source_display: "registro diario",
  recorded_by: "Ane Zubiri",
  recorded_by_display: "Ane Zubiri",
  observation_type: "measured",
  evidence_context: "ground",
  position: "current",
  position_note: "NOTA-DE-POSICION",
};

function render(over: {
  catalog?: DiaryCatalog | null;
  entries?: DiaryEntry[] | null;
  draft?: Draft;
  outcome?: Outcome | null;
  unavailable?: RequestOutcome | null;
  operator?: string;
  busy?: boolean;
}): string {
  return renderToStaticMarkup(
    createElement(DiaryView, {
      catalog,
      entries: [],
      draft: {},
      outcome: null,
      unavailable: null,
      busy: false,
      operator: "CDR",
      onOperator: () => undefined,
      onChange: () => undefined,
      onSubmit: () => undefined,
      ...over,
    }),
  );
}

describe("panel del registro diario", () => {
  it("en el tablero, la última cifra de cada campo va junto a su entrada, y la tabla en «Ver detalle»", () => {
    const html = render({ entries: [entry, { ...entry, value: 5, value_text: "5,0 puntos", effective: "2026-11-30T10:30:00+00:00" }] });
    const field = html.split('<label for="diary-mood-valence">')[1]!.split('<label for="diary-fluid-intake-24h">')[0]!;
    expect(field).toContain('<div class="diary-last" role="group" aria-label="Última anotación: Valencia del ánimo autoinformada">');
    expect(field).toContain('<span class="num">6,5 puntos</span>');
    expect(field).toContain('class="ref-spark"');
    // Un indicador del catálogo no repite su ficha aparte.
    expect(html).not.toContain("diary-board");
    expect(html.indexOf("Ver detalle: tabla de anotaciones")).toBeLessThan(html.indexOf('<table class="ledger">'));
  });

  it("cada campo tiene su etiqueta, su rango y la nota de escala del backend", () => {
    const html = render({});
    // El nombre del backend con el dibujo de su familia (cara: autoinforme; vejiga: líquidos).
    expect(html).toMatch(
      new RegExp(
        `<label for="diary-mood-valence"><span class="diary-field-name" data-clamp="" title="Valencia del ánimo autoinformada"><span class="mark">${pictogramSvg("face-neutral")}Valencia del ánimo autoinformada</span></span> <span class="secondary diary-field-unit">\\(puntos\\)</span></label>`,
      ),
    );
    expect(html).toMatch(
      new RegExp(`<label for="diary-fluid-intake-24h"><span class="diary-field-name" data-clamp="" title="Ingesta total de líquidos en 24 horas"><span class="mark">${pictogramSvg("bladder")}Ingesta total de líquidos en 24 horas</span>`),
    );
    expect(html).toContain('id="diary-mood-valence"');
    // El rango, a la vista; la regla de la escala, en el detalle común del tablero (`-notes`).
    expect(html).toContain('aria-describedby="diary-mood-valence-hint diary-mood-valence-notes"');
    expect(html).toMatch(/<p class="secondary" id="diary-mood-valence-hint">Rango: <span class="num">de 0,0 a 10,0<\/span><\/p>/);
    expect(html).toContain('id="diary-mood-valence-notes"');
    expect(html).toContain("de 0,0 a 10,0");
    expect(html).toContain("escala sin rótulos verificados");
    expect(html).toContain("El catálogo vigila el extremo bajo.");
    expect(html).toContain("NOTA-DEL-BACKEND");
    // Una magnitud física no lleva nota de escala.
    expect(html.split("escala sin rótulos verificados")).toHaveLength(2);
  });

  it("en el tablero, si el alimento es obligatorio u opcional va junto a su entrada, entero en `title` y en su descripción", () => {
    const fluid = catalog.indicators[1]!;
    const withFood: DiaryCatalog = {
      ...catalog,
      indicators: [
        catalog.indicators[0]!,
        {
          ...fluid,
          food_item: {
            label: "ROTULO-DEL-PLATO",
            required: false,
            requirement_note: "OPCIONAL-SEGUN-EL-BACKEND",
            max_length: 10,
            status: "design",
            status_display: "DECISION-DE-EMMA",
            decided_on: "2026-10-26",
            rule: "REGLA-DEL-ALIMENTO",
            why_free_text: "POR-QUE-TEXTO-LIBRE",
            grouping: "COMO-SE-AGRUPA",
            basis: [],
          },
        },
      ],
    };
    const html = render({ catalog: withFood });
    // La hoja la recorta a dos líneas (`.diary-food-rule`); el texto no se pierde: entero en el
    // DOM y en `title`, descrito por la entrada, y repetido en el detalle común (sin ratón).
    // (Sin DOM en estas pruebas: se mira la etiqueta del párrafo y su texto por separado.)
    const ruleTag = html.match(/<p [^>]*id="diary-fluid-intake-24h-food-rule"[^>]*>/)![0];
    expect(ruleTag).toMatch(/class="[^"]*\bdiary-food-rule\b/);
    expect(ruleTag).toContain('title="OPCIONAL-SEGUN-EL-BACKEND"');
    expect(html.split(ruleTag)[1]!.split("</p>")[0]).toContain("OPCIONAL-SEGUN-EL-BACKEND");
    const inputTag = html.match(/<input [^>]*id="diary-fluid-intake-24h-food"[^>]*>/)![0];
    expect(inputTag).toMatch(/aria-describedby="[^"]*\bdiary-fluid-intake-24h-food-rule\b/);
    const notes = html.split('id="diary-fluid-intake-24h-food-rule-notes"')[1]!.split("</div>")[0]!;
    expect(notes).toContain("OPCIONAL-SEGUN-EL-BACKEND");
    // El mando y el detalle común van juntos en el pie, una sola pieza de la rejilla.
    const foot = html.split('<div class="diary-foot">')[1]!;
    expect(foot.indexOf('type="submit"')).toBeGreaterThanOrEqual(0);
    expect(foot.indexOf('type="submit"')).toBeLessThan(foot.indexOf("Ver detalle: escalas, anclas y fuentes de cada campo"));
  });

  it("ningún campo llega relleno y sin nada tecleado no se puede enviar", () => {
    const html = render({});
    expect(html.match(/<input id="diary-[^>]*value=""/g)).toHaveLength(2);
    expect(html).toMatch(SUBMIT_DISABLED);
  });

  it("dice con qué procedencia se firma: medido, entorno del despliegue y fuente", () => {
    const html = render({});
    expect(html).toContain("MEDIDO");
    expect(html).toContain("Tierra");
    expect(html).toContain("fuente: registro diario");
  });

  it("pide quién anota con el rótulo y la nota del backend, y sin nombre no deja enviar", () => {
    const named = render({ draft: { "mood-valence": "6,5" } });
    // El rótulo con el dibujo de «persona» delante (`FieldLabel`), el mismo de su cabecera.
    expect(named).toMatch(
      new RegExp(`<label class="operator">${pictogramSvg("person")}ROTULO-DE-QUIEN-ANOTA <input[^>]*value="CDR"`),
    );
    expect(named).toContain('id="diary-operator-note">NOTA-DE-QUIEN-ANOTA');
    expect(named).toMatch(SUBMIT_ENABLED);
    expect(named).not.toContain("Falta el nombre");

    for (const nobody of ["", "  ", "—"]) {
      const html = render({ draft: { "mood-valence": "6,5" }, operator: nobody });
      expect(html).toMatch(SUBMIT_DISABLED);
      expect(html).toContain("Falta el nombre de quien anota");
      expect(html).toMatch(
        new RegExp(`<label class="operator">${pictogramSvg("person")}[^<]*<input[^>]*aria-invalid="true"`),
      );
    }
  });

  it("de cada anotación enseña la fuente con que entró y quién la anotó", () => {
    const html = render({ entries: [entry] });
    expect(html).toContain("· registro diario");
    // La cabecera es el rótulo del backend, con el dibujo de «persona» delante.
    expect(html).toMatch(thSign("person", "ROTULO-DE-QUIEN-ANOTA</span></th>", ' scope="col"'));
    // El nombre, tal cual: quien consta no lleva marca ninguna.
    expect(html).toContain('<td data-recorded-by="named"><span class="mark">Ane Zubiri</span></td>');
    // El indicador de la fila, con el dibujo de su familia.
    expect(html).toMatch(
      new RegExp(`<th scope="row"><span class="mark">${pictogramSvg("face-neutral")}Valencia del ánimo autoinformada</span></th>`),
    );
    // Todas llevan nombre: la nota sobre lo antiguo no hace falta.
    expect(html).not.toContain("NOTA-DE-LO-ANTIGUO");
  });

  it("una anotación antigua dice su fuente y que no consta quién la anotó, sin rellenarlo", () => {
    const old: DiaryEntry = {
      ...entry,
      source: "manual",
      source_display: "alta manual",
      recorded_by: null,
      recorded_by_display: "NO-CONSTA-DEL-BACKEND",
    };
    const html = render({ entries: [entry, { ...old, effective: "2026-11-30T10:30:00+00:00" }] });
    expect(html).toContain("· alta manual");
    // Gris con el círculo tachado («no disponible», `UNAVAILABLE_MARK`) y las palabras del
    // backend, no un hueco. Hasta la segunda pasada era el anillo punteado en gris: el dibujo de
    // «dato ausente» con el color de «no disponible».
    expect(html).toMatch(
      new RegExp(
        `<td data-recorded-by="missing"><span class="mark c-gray">${pictogramSvg("slash-circle")}NO-CONSTA-DEL-BACKEND</span></td>`,
      ),
    );
    expect(html).toContain("NOTA-DE-LO-ANTIGUO");
    // Ni el operador de ahora ni el tripulante ocupan el sitio de quien no consta.
    expect(html.split('data-recorded-by="missing"')[1]!.split("</td>")[0]).not.toContain("CDR");
  });

  it("un valor fuera de rango se avisa junto al campo y bloquea el envío", () => {
    const html = render({ draft: { "mood-valence": "11", "fluid-intake-24h": "2000" } });
    expect(html).toContain('aria-invalid="true"');
    expect(html).toContain('aria-describedby="diary-mood-valence-hint diary-mood-valence-notes diary-mood-valence-error"');
    // Amarillo con el triángulo y la frase de `entry.ts`, no solo el color.
    expect(html).toMatch(
      new RegExp(
        `<p id="diary-mood-valence-error" role="alert"><span class="mark c-yellow">${pictogramSvg("shape-triangle")}Fuera del rango: de 0,0 a 10,0\\.</span></p>`,
      ),
    );
    expect(html).toMatch(SUBMIT_DISABLED);
  });

  it("con un valor válido el botón queda activo", () => {
    const html = render({ draft: { "mood-valence": "6,5" } });
    expect(html).toMatch(SUBMIT_ENABLED);
  });

  it("tras guardar enseña lo que devuelve el registro: valor, hora UTC y procedencia", () => {
    const html = render({
      entries: [entry],
      outcome: { saved: ["mood-valence"], failed: null },
    });
    // La marca de «hecho» junto a la palabra, y el indicador con el dibujo de su familia; el
    // texto que se lee es el mismo de antes.
    expect(html).toMatch(new RegExp(`<span class="mark">${pictogramSvg("check")}Registrado:</span> `));
    expect(textLines(html)).toContain(
      "Registrado: Valencia del ánimo autoinformada. Abajo, tal como quedó en el registro.",
    );
    expect(html).toContain("6,5 puntos");
    expect(html).toContain("2026-12-01 10:30 UTC");
    // Dentro de la ventana del estado: solo la palabra del backend, sin marca.
    expect(html).toContain('<td data-position="current"><span class="mark">NOTA-DE-POSICION</span></td>');
  });

  it("el rechazo del backend se enseña tal cual, en amarillo con el triángulo (§5.34.14)", () => {
    const refused = requestOutcome(new ApiError(422, "DETALLE-DEL-BACKEND"));
    const html = render({
      outcome: { saved: [], failed: { key: "mood-valence", outcome: refused } },
    });
    expect(textLines(html)).toContain(
      "No se registró Valencia del ánimo autoinformada: DETALLE-DEL-BACKEND",
    );
    expect(html).toMatch(
      new RegExp(`<p role="alert"><span class="mark c-yellow">${pictogramSvg("shape-triangle")}No se registró `),
    );
    // Una anotación que no llegó (5xx, sin red) es un fallo: la cruz en rojo, no el triángulo.
    const broken = render({ outcome: { saved: [], failed: { key: "mood-valence", outcome: down("CAIDA") } } });
    expect(broken).toMatch(new RegExp(`<p role="alert"><span class="mark c-red">${pictogramSvg("cross")}No se registró `));
    expect(html).not.toContain('data-pictogram="check"');
  });

  it("una anotación apartada del análisis se marca con pictograma y palabra, no solo con color", () => {
    const html = render({
      entries: [{ ...entry, position: "after-reference", position_note: "APARTADA" }],
    });
    expect(html).toMatch(
      new RegExp(
        `<td data-position="after-reference"><span class="mark c-yellow">${pictogramSvg("shape-triangle")}APARTADA</span></td>`,
      ),
    );
  });

  it("una anotación descriptiva lleva el guion de «no aplica», sin color: no avisa de nada", () => {
    const html = render({
      entries: [
        { ...entry, position: "descriptive", position_note: "NO-LA-LEE" },
        { ...entry, effective: "2026-11-30T10:30:00+00:00", position: "earlier", position_note: "ANTERIOR" },
      ],
    });
    expect(html).toMatch(
      new RegExp(`<td data-position="descriptive"><span class="mark">${pictogramSvg("dash")}NO-LA-LEE</span></td>`),
    );
    expect(html).toContain('<td data-position="earlier"><span class="mark">ANTERIOR</span></td>');
    expect(html).not.toMatch(/c-(red|yellow|blue|magenta|green)/);
  });

  it("una anotación que el estado no lee por su tipo lleva «no disponible»: gris con el círculo tachado (§5.39.11)", () => {
    const html = render({
      entries: [
        { ...entry, observation_type: "inferred", position: "not-analysed-by-type", position_note: "NO-POR-SU-TIPO" },
      ],
    });
    expect(html).toMatch(
      new RegExp(
        `<td data-position="not-analysed-by-type"><span class="mark c-gray">${pictogramSvg("slash-circle")}NO-POR-SU-TIPO</span></td>`,
      ),
    );
    // Ni cian (el dato existe y no ha caducado) ni amarillo (no hay nada que mirar en la persona).
    expect(html).not.toMatch(/c-(red|yellow|blue|magenta|green|cyan)/);
  });

  it("sin catálogo dice que no hay dato, en cian, y no pinta formulario", () => {
    const html = render({ catalog: null, unavailable: down("MOTIVO") });
    expect(html).toMatch(
      new RegExp(`<p><span class="mark c-red">${pictogramSvg("cross")}Sin datos: MOTIVO</span></p>`),
    );
    expect(html).not.toContain("<form");
  });

  it("cada título, cabecera y mando lleva el signo de su concepto delante de la palabra (§5.33.7)", () => {
    const html = render({ entries: [entry] });
    expect(html).toMatch(taggedPictogram("h2", uiPictogram("diary"), "Registro diario</h2>"));
    expect(html).toMatch(taggedPictogram("h3", uiPictogram("notes"), "Últimas anotaciones</h3>"));
    const headers: [Parameters<typeof uiPictogram>[0], string][] = [
      ["indicator", "Indicador"],
      ["value", "Valor"],
      ["time", "Hora"],
      ["provenance", "Procedencia"],
      ["state", "En el estado"],
    ];
    for (const [concept, word] of headers) {
      expect(html).toMatch(thSign(uiPictogram(concept), `${word}</span></th>`, ' scope="col"'));
    }
    // Ninguna cabecera de columna se queda sin signo.
    expect(html).not.toMatch(/<th scope="col">[^<]/);
  });

  it("cargando dice «Cargando…» con su marca; mientras envía, el mando lleva la misma", () => {
    const loading = render({ catalog: null, unavailable: null });
    expect(loading).toMatch(markedHtml("refresh", "Cargando…"));
    expect(loading).not.toContain("Sin datos");
    const busy = render({ draft: { "mood-valence": "6,5" }, busy: true });
    expect(busy).toMatch(
      taggedPictogram("button", "refresh", "Registrando…", ' class="command" type="submit" disabled=""'),
    );
    expect(busy).not.toContain(">Registrar<");
  });

  it("el instrumento leído de un descriptivo lleva el libro abierto en sus categorías y su plegable", () => {
    const quote = {
      id: "categorias",
      label: "ROTULO",
      quote: "FRASE",
      ref: "ficha",
      source: "CITA",
      title: "TITULO",
      url: null,
      where: "SECCION",
      read_on: "2026-10-16",
      extent: "partial",
      extent_text: "leído en parte",
    };
    const described: DiaryCatalog["indicators"][number] = {
      ...catalog.indicators[0]!,
      key: "vision-change",
      scale: {
        described_as: null,
        labels: null,
        labels_status: "instrument",
        labels_note: "NOTA",
        instrument: {
          instrument: "INSTRUMENTO",
          language: "en",
          scope: "ALCANCE",
          statements: [quote],
          categories: [{ value: 1, literal: "CATEGORIA", statement: "categorias" }],
          numbering: null,
          sources: [],
          not_found: [],
        },
        concerning: "high",
        concerning_note: null,
      },
      descriptive_only: true,
    };
    const html = render({ catalog: { ...catalog, indicators: [described] } });
    const block = html.split('data-diary-instrument="vision-change"')[1]!.split("</details>")[0]!;
    const book = uiPictogram("sourceText");
    expect(block).toMatch(markedHtml(book, "Categorías de la fuente:"));
    expect(block).toMatch(taggedPictogram("summary", book, "Fuente del instrumento: INSTRUMENTO</summary>"));
  });

  it("si la última lectura falló, las cifras de antes van en cursiva: caducadas", () => {
    expect(render({ entries: [entry] })).not.toContain("stale");
    const html = render({ entries: [entry], unavailable: down("MOTIVO") });
    expect(html).toContain('<td class="num stale">6,5 puntos</td>');
    expect(html).toContain('<td class="num stale">2026-12-01 10:30 UTC</td>');
    expect(html).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
  });

  it("mientras no llegan las anotaciones de este tripulante, «Cargando…», no un registro vacío", () => {
    const html = render({ entries: null });
    const notes = html.split("Últimas anotaciones</h3>")[1]!;
    expect(notes).toMatch(markedHtml("refresh", "Cargando…"));
    expect(notes).not.toContain("Ninguna anotación");
    expect(notes).not.toContain("<table");
    // Si su lectura falló, ya lo dice «Sin datos» arriba: ni carga ni registro vacío.
    const failed = render({ entries: null, unavailable: down("MOTIVO") }).split("Últimas anotaciones</h3>")[1]!;
    expect(failed).toBe("</section>");
  });

  it("sin anotaciones lo dice con la marca de registro vacío, sin color (§5.33.12)", () => {
    const html = render({ entries: [] });
    expect(html).toMatch(
      markedHtml("ring-dotted", "Ninguna anotación a mano de este tripulante en el registro.</span>"),
    );
    expect(html).not.toContain("<table");
  });

  it("una escala con rótulos leídos los enseña en su idioma, con su frase y su origen", () => {
    const statement = {
      id: "anclas",
      label: "ROTULO-DE-LA-FRASE",
      quote: "FRASE-DE-LA-FUENTE",
      ref: "ficha",
      source: "CITA-DE-LA-FUENTE",
      title: "TITULO",
      url: "URL-DE-LA-FUENTE",
      where: "SECCION",
      read_on: "2026-10-13",
      extent: "partial",
      extent_text: "leído en parte",
    };
    const hedonic: DiaryCatalog["indicators"][number] = {
      ...catalog.indicators[0]!,
      key: "food-acceptability",
      scale: {
        described_as: "DESCRIPCION",
        labels: [
          { value: 1, label: "ROTULO-BAJO", statement },
          { value: 9, label: "ROTULO-ALTO", statement },
        ],
        labels_status: "read",
        labels_language: "en",
        labels_note: "NOTA-DE-ROTULOS-LEIDOS",
        labels_sources: [],
        labels_see_also: [],
        labels_not_found: ["NO-ENCONTRADO"],
        concerning: "low",
        concerning_note: null,
      },
    };
    const html = render({ catalog: { ...catalog, indicators: [catalog.indicators[0]!, hedonic] } });
    const block = html.split('data-diary-labels="food-acceptability"')[1]!.split("</details>")[0]!;
    expect(block).toMatch(
      /<span class="num">1<\/span> = <span lang="en">ROTULO-BAJO<\/span><\/span><span> · <span class="num">9<\/span> = <span lang="en">ROTULO-ALTO/,
    );
    expect(block.split('<q lang="en">FRASE-DE-LA-FUENTE</q>')).toHaveLength(2);
    expect(block).toContain("SECCION · CITA-DE-LA-FUENTE · leído en parte · leído el 2026-10-13");
    expect(block).toContain("Buscado y no encontrado: NO-ENCONTRADO");
    expect(html).toContain("NOTA-DE-ROTULOS-LEIDOS");
    // La escalera junto al rótulo, y un solo dibujo: cada rótulo leído va con su cifra y su
    // palabra, sin dibujo propio (ni caras ni otra cosa que no se haya leído).
    expect(block).toMatch(new RegExp(`^><span class="mark">${pictogramSvg("stairs")}Rótulos leídos en la fuente:</span> `));
    // Se cuenta sin la cabecera del plegable, que lleva el signo de «lo leído en la fuente» (el
    // libro abierto, segunda pasada §5.33.7) y no es un dibujo de la escala.
    expect(block).toMatch(
      taggedPictogram("summary", uiPictogram("sourceText"), "Fuente de los rótulos</summary>"),
    );
    expect(withoutSummary(block).match(/data-pictogram=/g)).toHaveLength(1);
    // La escala propia de la misión, al lado, sigue sin rótulos ni escalera.
    expect(html).not.toContain('data-diary-labels="mood-valence"');
    expect(html.match(/data-pictogram="stairs"/g)).toHaveLength(1);
  });

  it("una escala propia enseña sus anclas con la marca y el porqué del backend, sin cita", () => {
    const own: DiaryCatalog["indicators"][number] = {
      ...catalog.indicators[0]!,
      scale: {
        ...catalog.indicators[0]!.scale!,
        labels_status: "own",
        labels_language: null,
        labels_sources: [],
        labels_see_also: [],
        labels_not_found: [],
        design_anchors: {
          status: "design",
          status_display: "MARCA-DEL-BACKEND",
          decided_on: "2026-10-15",
          why: "POR-QUE-DEL-BACKEND",
          anchors: [
            { value: 0, label: "ANCLA-BAJA" },
            { value: 10, label: "ANCLA-ALTA" },
          ],
          between: "ENTRE-DEL-BACKEND",
          reference: "REFERENCIA-DEL-BACKEND",
        },
      },
    };
    const html = render({ catalog: { ...catalog, indicators: [own, catalog.indicators[1]!] } });
    const block = html.split('data-diary-anchors="mood-valence"')[1]!.split("</details>")[0]!;
    // La marca va delante de las anclas, no escondida en el desplegable. Cada extremo lleva un
    // cursor en su lado de la pista: la posición en el rango, sin caras ni otro dibujo.
    expect(block).toMatch(
      new RegExp(
        `^>Anclas \\(MARCA-DEL-BACKEND\\): <span><span class="mark">${pictogramSvg("slider-left")}<span class="num">0</span> = ANCLA-BAJA</span></span><span> · <span class="mark">${pictogramSvg("slider-right")}<span class="num">10</span> = ANCLA-ALTA</span></span>\\. ENTRE-DEL-BACKEND`,
      ),
    );
    // Sin la cabecera del plegable (el lápiz de «Por qué son de EMMA», §5.33.7), solo los dos
    // cursores: las anclas no llevan otro dibujo.
    expect(block).toMatch(taggedPictogram("summary", uiPictogram("whyEmma"), "Por qué son de EMMA</summary>"));
    expect(withoutSummary(block).match(/data-pictogram=/g)).toHaveLength(2);
    expect(block).not.toMatch(/face|stairs|c-(red|yellow|blue|gray|cyan|magenta|green)/);
    expect(block).toContain("<p>POR-QUE-DEL-BACKEND</p>");
    expect(block).toContain("<p>REFERENCIA-DEL-BACKEND</p>");
    // No son rótulos leídos: ni su bloque, ni frase, ni enlace, ni idioma de una fuente.
    expect(html).not.toContain('data-diary-labels="mood-valence"');
    expect(html).not.toContain("Rótulos leídos en la fuente");
    expect(block).not.toContain("<q");
    expect(block).not.toContain("lang=");
    // Una magnitud física no lleva anclas.
    expect(html.split("data-diary-anchors=")).toHaveLength(2);
  });

  it("el panel no interpreta lo anotado ni rotula la escala", () => {
    const source = readFileSync(fileURLToPath(new URL("./DiaryPanel.tsx", import.meta.url)), "utf8")
      + readFileSync(fileURLToPath(new URL("./entry.ts", import.meta.url)), "utf8")
      + readFileSync(fileURLToPath(new URL("./labels.ts", import.meta.url)), "utf8")
      + readFileSync(fileURLToPath(new URL("./position.ts", import.meta.url)), "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    // Tampoco los rótulos de la escala hedónica, ni traducidos: los da el backend con su frase.
    for (const word of ["Dislike", "Extremely", "gusta", "disgusta"]) {
      expect(code).not.toContain(word);
    }
    // Ni las palabras para quien no consta, ni el nombre de una fuente: son del backend.
    for (const word of ["no consta", "alta manual", "registro diario", "crew-diary"]) {
      expect(code).not.toContain(word);
    }
    for (const word of ["nominal", "normal", "preocupante", "muy mal", "muy bien", "c-red"]) {
      expect(code).not.toContain(word);
    }
    // Las anclas de las escalas propias y su marca son del backend: aquí no se escriben, y
    // nada las llama validadas.
    for (const word of ["negativo", "positivo", "síntoma", "apetito", "sin validar", "validad"]) {
      expect(code).not.toContain(word);
    }
    expect(code).not.toMatch(/validated/i);
  });
});

describe("el nombre recortado a dos líneas en el tablero (segunda ronda, 2026-11-08)", () => {
  const cohesion = (end: string) => `Cohesión del equipo, cuestionario de fin de día: acuerdo de 1 a 7 con «${end}»`;
  const names = [
    "Ingesta total de líquidos en 24 horas",
    "Ingesta energética diaria",
    cohesion("Our team members cared about each other"),
    cohesion("Our team was unified in its task focus"),
  ];

  it("se recorta si lo que lo distingue de los demás cae en lo que se ve", () => {
    expect(clampable(names[0]!, names)).toBe(true);
    expect(clampable(names[1]!, names)).toBe(true);
  });

  it("va entero si recortado se confundiría con otro: los de cohesión solo difieren al final", () => {
    expect(clampable(names[2]!, names)).toBe(false);
    expect(clampable(names[3]!, names)).toBe(false);
  });

  it("de los que no se recortan se ve solo su frase, cortada del nombre del backend sin palabras nuevas (quinta ronda)", () => {
    expect(distinctTail(names[0]!, names)).toBeNull();
    expect(distinctTail(names[2]!, names)).toBe("«Our team members cared about each other»");
    expect(distinctTail(names[3]!, names)).toBe("«Our team was unified in its task focus»");
    for (const name of names) {
      const tail = distinctTail(name, names);
      if (tail !== null) expect(name.endsWith(tail)).toBe(true);
    }
  });

  it("en el tablero, la frase a la vista y el nombre entero para el lector de pantalla y en `title`", () => {
    const base = catalog.indicators[0]!;
    const html = render({
      catalog: {
        ...catalog,
        indicators: names.map((name, index) => ({ ...base, key: `${base.key}-${index}`, display_es: name })),
      },
    });
    expect(html).toContain(`title="${names[2]!}"`);
    expect(html).toContain(`<span class="sr-only">${names[2]!}</span>`);
    expect(html).toContain("…«Our team members cared about each other»");
  });
});
