import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, thSign, textLines, textNodes } from "../advisor/visibleText";
import type { PainCatalog, PainReport } from "../lib/api";
import { UNKNOWN_MARK } from "../lib/marks";
import { KNOWN_CHARACTERS, characterMark } from "./characters";
import type { Change } from "./evolution";
import { CHANGES, PainEvolution, PainHistory, ReceivedPainBoard } from "./PainHistory";
import { PainPanel } from "./PainPanel";
import { ORIGIN_PICTOGRAM, PainNote } from "./PainNote";

/**
 * Los pictogramas del dolor (§5.32.9): cada caracter conocido tiene un dibujo propio y distinto
 * (la paridad con `CHARACTERS` del backend la vigila `backend/tests/test_pain_volume_pictograms.py`,
 * que lee esta tabla); el cambio de cada zona lleva su forma junto a su palabra; y nada del
 * dolor va en rojo ni amarillo (§5.2).
 */

const CATALOG: PainCatalog = {
  system: "https://emma.mission/pain",
  scale: { min: 1, max: 10, unit: "{score}" },
  zones: [
    { key: "lower-back", display: "ZONA-LUMBAR", side: null },
    { key: "knee-left", display: "RODILLA-IZQUIERDA", side: "left" },
  ],
  characters: [
    { key: "dull", display: "PALABRA-SORDO" },
    { key: "sharp", display: "PALABRA-PUNZANTE" },
    { key: "inventado", display: "PALABRA-NUEVA" },
  ],
};

function report(effective: string, zones: [string, number, string[]][]): PainReport {
  return {
    subject: "crew-01",
    effective,
    reported_by: "cmdr",
    zones: zones.map(([zone, intensity, characters]) => ({ zone, intensity, characters })),
    intensity: Math.max(0, ...zones.map(([, value]) => value)),
    ledger_index: 0,
    recorded: effective,
    discuss: { reasons: [], note: null },
  };
}

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

describe("los caracteres del dolor (characters.ts)", () => {
  it("los siete caracteres del catalogo, cada uno con un dibujo propio y distinto", () => {
    expect(KNOWN_CHARACTERS).toHaveLength(7);
    const drawn = KNOWN_CHARACTERS.map((key) => characterMark(key).pictogram);
    expect(new Set(drawn).size).toBe(drawn.length);
    for (const key of KNOWN_CHARACTERS) {
      expect(characterMark(key).pictogram, key).not.toBe(UNKNOWN_MARK.pictogram);
    }
  });

  it("ninguno con color: el dolor no es una alerta", () => {
    for (const key of KNOWN_CHARACTERS) expect(characterMark(key).color).toBeNull();
  });

  it("un caracter que la interfaz no conoce lleva la marca de desconocido, no un dibujo supuesto", () => {
    expect(characterMark("inventado")).toEqual(UNKNOWN_MARK);
  });
});

describe("el cambio de cada zona (CHANGES)", () => {
  it("una forma distinta por cambio, sin color: ▲ ▼ = con su dibujo, y «primera vez» con el anillo de elegido, no el disco de medido", () => {
    expect(CHANGES.sube.mark.pictogram).toBe("triangle-up-filled");
    expect(CHANGES.baja.mark.pictogram).toBe("triangle-down-filled");
    expect(CHANGES.igual.mark.pictogram).toBe("equals");
    expect(CHANGES.nueva.mark.pictogram).toBe("ring-dot");
    for (const change of Object.keys(CHANGES) as Change[]) {
      expect(CHANGES[change].mark.color).toBeNull();
      expect(CHANGES[change].word).not.toBe("");
    }
  });
});

describe("<PainEvolution>", () => {
  const html = render(
    createElement(PainEvolution, {
      catalog: CATALOG,
      reports: [
        report("2026-09-20T08:00:00Z", [["lower-back", 4, ["dull"]]]),
        report("2026-09-21T08:00:00Z", [
          ["lower-back", 6, ["dull", "sharp", "inventado"]],
          ["knee-left", 3, []],
        ]),
      ],
    }),
  );

  it("el cambio lleva su pictograma junto a su palabra", () => {
    expect(html).toContain('<span class="mark"><svg class="pictogram"');
    expect(html).toMatch(/data-pictogram="triangle-up-filled"[^]*?<\/svg>sube<\/span>/);
    expect(html).toMatch(/data-pictogram="ring-dot"[^]*?<\/svg>primera vez<\/span>/);
  });

  it("cada caracter lleva su dibujo junto a la palabra del backend, y el desconocido el punto", () => {
    expect(html).toMatch(/data-pictogram="oval"[^]*?<\/svg>PALABRA-SORDO<\/span>/);
    expect(html).toMatch(/data-pictogram="star-four"[^]*?<\/svg>PALABRA-PUNZANTE<\/span>/);
    expect(html).toMatch(new RegExp(`data-pictogram="${UNKNOWN_MARK.pictogram}"[^]*?</svg>PALABRA-NUEVA</span>`));
    // Los pictogramas no parten la linea: la celda se lee como la lista de palabras.
    expect(textLines(html)).toContain("PALABRA-SORDO, PALABRA-PUNZANTE, PALABRA-NUEVA");
  });

  it("nada del dolor va en rojo ni amarillo (§5.2), y la zona sin caracteres lleva la raya", () => {
    expect(html).not.toMatch(/c-red|c-yellow|flash/);
    expect(textNodes(html)).toContain("—");
  });
});

describe("<PainNote>: el origen de la nota", () => {
  const note = (origin: "escrita" | "dictada-revisada", text: string) =>
    render(createElement(PainNote, { note: text, origin, onChange: () => undefined }));

  it("pluma junto al rotulo mientras se escribe; microfono cuando viene de un audio", () => {
    expect(ORIGIN_PICTOGRAM).toEqual({ escrita: "pen", "dictada-revisada": "microphone" });
    expect(note("escrita", "")).toMatch(/data-pictogram="pen"[^]*?<\/svg>Nota \(opcional\)<\/span>/);
    expect(note("dictada-revisada", "x")).toMatch(/data-pictogram="microphone"[^]*?<\/svg>Nota \(opcional\)<\/span>/);
  });

  it("el borrador dictado se avisa en amarillo con su triangulo; escrito, no hay aviso", () => {
    const dictated = note("dictada-revisada", "lo que dijo");
    expect(dictated).toContain('<span class="mark c-yellow"><svg class="pictogram"');
    expect(dictated).toMatch(/data-pictogram="shape-triangle"[^]*?<\/svg>Borrador transcrito/);
    expect(note("escrita", "lo que escribio")).not.toContain("c-yellow");
  });
});

describe("el signo de cada cosa del dolor (segunda pasada, §5.33.9)", () => {
  const evolution = (reports: PainReport[]) => render(createElement(PainEvolution, { catalog: CATALOG, reports }));

  it("cada cabecera de la evolucion lleva el dibujo de su concepto delante de su palabra", () => {
    const html = evolution([report("2026-09-21T08:00:00Z", [["lower-back", 6, ["dull"]]])]);
    const col = ' scope="col"';
    expect(html).toMatch(thSign("pin", "Zona", col));
    expect(html).toMatch(thSign("clock", "Ahora", col));
    expect(html).toMatch(thSign("clock-rewind", "Anterior", col));
    expect(html).toMatch(thSign("chart-line", "Cambio", col));
    expect(html).toMatch(thSign("tag", "Tipo (último)", col));
  });

  it("sin informes: el anillo punteado sin color (nada aqui), no el cian del dato ausente", () => {
    const html = evolution([]);
    expect(html).toMatch(markedHtml("ring-dotted", "Sin informes de dolor registrados."));
    expect(html).not.toMatch(/c-cyan|c-red|c-yellow/);
  });

  it("antes de la primera respuesta el panel dice que carga, sin color (§5.33.11)", () => {
    const html = render(createElement(PainPanel, { subject: "crew-01" }));
    expect(html).toMatch(/<p class="secondary"><span class="mark"><svg[^>]*data-pictogram="refresh"[^]*?<\/svg>Cargando…<\/span><\/p>/);
    expect(html).not.toMatch(/c-cyan|c-red|c-yellow/);
  });

  it("los titulos de los dos paneles llevan el rayo del dolor", () => {
    expect(render(createElement(PainPanel, { subject: "crew-01" }))).toMatch(taggedPictogram("h2", "bolt", "Dolor"));
    expect(render(createElement(PainHistory, { subject: "crew-01", oneWayMinutes: null }))).toMatch(
      taggedPictogram("h2", "bolt", "Dolor referido"),
    );
  });
});

describe("<ReceivedPainBoard> (tablero de Tierra)", () => {
  const reports = [
    report("2026-10-20T08:00:00Z", [["lower-back", 3, []]]),
    report("2026-10-22T08:00:00Z", [["lower-back", 6, []], ["knee-left", 2, []]]),
  ];

  it("la intensidad máxima del último llegado sobre la escala del catálogo, con su curva, las zonas y los informes", () => {
    const html = render(createElement(ReceivedPainBoard, { reports, catalog: CATALOG, stale: false }));
    expect(html).toContain('aria-label="Último informe de dolor llegado"');
    expect(html).toMatch(/<span class="num">6<\/span> <span class="stat-unit">de 10<\/span>/);
    expect(html).toContain('class="ref-spark"');
    expect(html).toMatch(/Zonas<\/span><span class="stat-value"><span class="num">2<\/span>/);
    expect(html).toMatch(/Informes<\/span><span class="stat-value"><span class="num">2<\/span>/);
  });

  it("un último informe sin zonas dice «sin dolor», sin cifra; con uno solo no hay curva; sin informes, nada", () => {
    const calm = render(createElement(ReceivedPainBoard, { reports: [report("2026-10-22T08:00:00Z", [])], catalog: CATALOG, stale: true }));
    expect(calm).toMatch(markedHtml("check", "sin dolor"));
    expect(calm).not.toContain("ref-spark");
    expect(calm).toContain('class="stat-tile stale"');
    expect(render(createElement(ReceivedPainBoard, { reports: [], catalog: CATALOG, stale: false }))).toBe("");
  });
});
