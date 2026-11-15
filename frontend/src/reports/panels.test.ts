import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LookContext } from "../components/BoardOnly";
import { markedHtml, taggedPictogram, thSign, textLines, textNodes } from "../advisor/visibleText";
import type { Indicator, LabIncongruences, LabReading, ScannedReport } from "../lib/api";
import { LabReadings } from "./LabReadings";
import { Incongruences, ReportBoard, ReportView, ReportsPanel } from "./ReportsPanel";

/**
 * Lo que pintan los paneles de informes: el pictograma junto a la palabra del backend, y la
 * palabra como unico texto. Se prueban las piezas sin red (sin efectos que llamen a la API).
 * Los nombres de los informes de prueba son inventados.
 */

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);
const noop = () => undefined;

const report = (extra: Partial<ScannedReport> = {}): ScannedReport => ({
  ledger_index: 11,
  recorded: "2026-11-14T10:00:00+00:00",
  kind: "analitica",
  media_type: "application/pdf",
  pages: 1,
  recorded_by: "CMO",
  ocr: { available: true, pages: [{ page: 1, text: "Hemoglobina 13,9 g/dL", confidence: null, words: 3, low_confidence: false }] },
  ...extra,
});

describe("<ReportView>", () => {
  // Segunda pasada (§5.33.10): el informe es un plegable (`Fold`) y la hoja de su clase es su signo,
  // directo en el `<summary>` como el de todo plegable; la palabra de la clase va justo detras.
  it("la clase del informe es el signo del plegable, junto a su palabra", () => {
    const html = render(createElement(ReportView, { report: report(), operator: "CMO", onChanged: noop }));
    expect(html).toMatch(/<summary><svg[^>]*data-pictogram="page-grid"[^>]*>.*?<\/svg>Analítica · /);
    const other = render(createElement(ReportView, { report: report({ kind: "alta" }), operator: "CMO", onChanged: noop }));
    expect(other).toContain('data-pictogram="page-arrow-right"');
    expect(textNodes(other).join(" ")).toContain("Informe de alta");
  });

  it("un informe de otra persona: triangulo amarillo en «no se usa» y en la explicacion, sin texto ni pagina", () => {
    const html = render(
      createElement(ReportView, {
        report: report({ identity: { verdict: "otro_paciente", explanation: "EXPLICACION", usable: false } }),
        operator: "CMO",
        onChanged: noop,
      }),
    );
    expect(html).toContain('<span class="mark c-yellow"><svg');
    expect((html.match(/data-pictogram="shape-triangle"/g) ?? []).length).toBe(2);
    expect(html).not.toContain("<img");
    expect(textNodes(html).join(" ")).toContain("Este informe no es de este tripulante: EXPLICACION.");
  });

  it("la identidad: ambiguo con triangulo amarillo; parcial con medio circulo y sin color; coincide no se dice", () => {
    const ambiguous = render(
      createElement(ReportView, {
        report: report({ identity: { verdict: "ambiguo", explanation: "EXPLICACION", usable: true } }),
        operator: "CMO",
        onChanged: noop,
      }),
    );
    expect(ambiguous).toMatch(/<p class="c-yellow"><span class="mark"><svg[^>]*data-pictogram="shape-triangle"[^>]*>.*?<\/svg>Identidad: EXPLICACION\./);
    const partial = render(
      createElement(ReportView, {
        report: report({ identity: { verdict: "parcial", explanation: "EXPLICACION", usable: true } }),
        operator: "CMO",
        onChanged: noop,
      }),
    );
    expect(partial).toMatch(/<p class="secondary"><span class="mark"><svg[^>]*data-pictogram="circle-half-dashed"/);
    const matching = render(
      createElement(ReportView, {
        report: report({ identity: { verdict: "coincide", explanation: "EXPLICACION", usable: true } }),
        operator: "CMO",
        onChanged: noop,
      }),
    );
    expect(matching).not.toContain("Identidad:");
  });

  it("sin OCR, no disponible con el circulo tachado; lectura poco fiable y texto retenido, con triangulo", () => {
    const html = render(
      createElement(ReportView, {
        report: report({
          ocr: {
            available: false,
            note: "NOTA-OCR",
            pages: [
              {
                page: 1,
                text: "",
                confidence: 40,
                words: 10,
                low_confidence: true,
                deidentification: { redactions: 2, verified: false, remaining: ["un nombre"] },
              },
            ],
          },
        }),
        operator: "CMO",
        onChanged: noop,
      }),
    );
    expect(html).toMatch(/<p class="c-gray"><span class="mark"><svg[^>]*data-pictogram="slash-circle"[^>]*>.*?<\/svg>NOTA-OCR</);
    expect((html.match(/data-pictogram="shape-triangle"/g) ?? []).length).toBe(2);
    const words = textNodes(html).join(" ");
    expect(words).toContain("Lectura poco fiable");
    expect(words).toContain("Texto retenido");
  });
});

describe("<Incongruences>", () => {
  it("dos analiticas que no coinciden llevan triangulo amarillo; las sin fecha, circulo tachado gris", () => {
    const crossed: LabIncongruences = {
      incongruences: [
        {
          key: "hemoglobin",
          sample: "2026-09-12",
          readings: [
            { value: 13.9, date: "2026-09-12", report: "informe:3" },
            { value: 12.1, date: "2026-09-12", report: "informe:4" },
          ],
        },
      ],
      undated_reports: 1,
      tolerance: 0.1,
    };
    const indicators = { hemoglobin: { key: "hemoglobin", display_es: "Hemoglobina" } as Indicator };
    const html = render(createElement(Incongruences, { crossed, indicators }));
    expect(html).toMatch(/<p class="c-yellow"><span class="mark"><svg[^>]*data-pictogram="shape-triangle"/);
    expect(html).toMatch(/<p class="c-gray"><span class="mark"><svg[^>]*data-pictogram="slash-circle"/);
    // El analito con su nombre del catalogo y el pictograma de su familia, no con su clave.
    expect(html).toContain('data-pictogram="cells"');
    expect(textLines(html)).toEqual([
      "Hemoglobina, 2026-09-12: no coinciden 13,90 (informe:3) / 12,10 (informe:4)",
      "1 analíticas sin fecha legible: no se cruzan con las demás",
    ]);
    // Sin catalogo todavia, la clave: nunca un nombre inventado.
    expect(textLines(render(createElement(Incongruences, { crossed, indicators: {} })))[0]).toContain("hemoglobin, ");
  });

  it("sin incongruencias ni informes sin fecha no pinta nada", () => {
    const crossed: LabIncongruences = { incongruences: [], undated_reports: 0, tolerance: 0.1 };
    expect(render(createElement(Incongruences, { crossed, indicators: {} }))).toBe("");
  });
});

const reading = (extra: Partial<LabReading> = {}): LabReading => ({
  key: "hemoglobin",
  name: "Hemoglobina",
  value: 13.9,
  unit: "g/dL",
  report_unit: "g/dL",
  ref_low: 12,
  ref_high: 16,
  out_of_range: false,
  confidence: "alta",
  comparator: null,
  requires_correction: false,
  status: "por_confirmar",
  ...extra,
});

describe("<LabReadings>", () => {
  const table = (items: LabReading[]) =>
    render(createElement(LabReadings, { report: 11, readings: items, reportDate: "2026-09-12", operator: "CMO", onConfirmed: noop }));

  it("el analito lleva el pictograma de la familia de su indicador, con el nombre del backend", () => {
    const html = table([reading()]);
    expect(html).toMatch(/<td><span class="mark"><svg[^>]*data-pictogram="cells"[^>]*>.*?<\/svg>Hemoglobina<\/span>/);
    expect(table([reading({ key: "creatinine", name: "Creatinina" })])).toContain('data-pictogram="kidneys"');
  });

  it("por confirmar: la casilla por marcar junto a «Confirmar»; confirmada: el hecho junto a quien confirmo", () => {
    const pending = table([reading()]);
    expect(pending).toMatch(/<button class="command"><span class="mark"><svg[^>]*data-pictogram="box-empty"[^>]*>.*?<\/svg>Confirmar<\/span><\/button>/);
    expect(pending).not.toContain('data-pictogram="check"');
    const confirmed = table([
      reading({ status: "confirmada", confirmation: { confirmed_by: "CMO", value: 13.9, observation_index: 40 } }),
    ]);
    expect(confirmed).toMatch(/<span class="mark secondary"><svg[^>]*data-pictogram="check"[^>]*>.*?<\/svg>Confirmada por CMO<\/span>/);
    expect(confirmed).not.toContain('data-pictogram="box-empty"');
  });

  it("la que exige correccion lleva triangulo amarillo; «fuera de rango» se dice y no se dibuja", () => {
    const html = table([reading({ requires_correction: true, out_of_range: true })]);
    expect(html).toMatch(/<span class="c-yellow"><span class="mark"><svg[^>]*data-pictogram="shape-triangle"[^>]*>.*?<\/svg>indica el valor del papel en g\/dL<\/span>/);
    expect(html).toContain('<span class="secondary"> · fuera de rango</span>');
  });

  it("el titulo lleva la hoja cuadriculada", () => {
    expect(table([])).toMatch(/<h3><svg[^>]*data-pictogram="page-grid"[^>]*>.*?<\/svg>Cifras leídas<\/h3>/);
  });

  // Segunda pasada (§5.33.10): cabeceras y rotulo con el signo de su concepto (`lib/uiMarks.ts`).
  it("cada cabecera y la fecha de extraccion llevan el signo de su concepto", () => {
    const html = table([reading()]);
    expect(html).toMatch(thSign("vial", "Analito", ' scope="col"'));
    expect(html).toMatch(thSign("hash", "Valor", ' scope="col"'));
    expect(html).toMatch(thSign("bar-capped", "Rango del informe", ' scope="col"'));
    expect(html).toMatch(thSign("toggle", "Estado", ' scope="col"'));
    expect(html).toMatch(taggedPictogram("label", "calendar", "Fecha de extracción"));
  });
});

describe("segunda pasada: los mandos y plegables de los informes", () => {
  it("los botones de pagina no llevan signo de concepto; la que se ve, el anillo con punto", () => {
    const html = render(createElement(ReportView, { report: report({ pages: 2 }), operator: "CMO", onChanged: noop }));
    expect(html).toMatch(
      new RegExp(`<button class="command" aria-pressed="true">${markedHtml("ring-dot", "1").source}</span></button>`),
    );
    // La que no se ve, sin dibujo: su `.mark` reserva el hueco del anillo (`Chosen`, §5.33.12).
    expect(html).toContain('<button class="command" aria-pressed="false"><span class="mark">2</span></button>');
  });

  it("un informe de otra persona tambien es un plegable con la hoja de su clase", () => {
    const html = render(
      createElement(ReportView, {
        report: report({ kind: "otro", identity: { verdict: "otro_paciente", explanation: "E", usable: false } }),
        operator: "CMO",
        onChanged: noop,
      }),
    );
    expect(html).toMatch(taggedPictogram("summary", "page-blank", "Otro · "));
  });

  it("el panel: titulo, identidad plegada, rotulos y mandos con su signo; cargando antes de la respuesta", () => {
    const html = render(createElement(ReportsPanel, { subject: "crew-01" }));
    expect(html).toMatch(taggedPictogram("h2", "pages-stack", "Informes escaneados"));
    expect(html).toMatch(taggedPictogram("summary", "id-card", "Identidad para cotejar informes:"));
    expect(html).toMatch(taggedPictogram("label", "person", "Nombre de pila"));
    expect(html).toMatch(taggedPictogram("label", "calendar", "Fecha de nacimiento"));
    expect(html).toMatch(taggedPictogram("button", "id-card", "Declarar identidad", ' class="command" disabled=""'));
    expect(html).toMatch(taggedPictogram("label", "sheet-lines", "Documento (PDF, PNG, JPEG o TIFF)"));
    expect(html).toMatch(taggedPictogram("label", "tag", "Tipo"));
    expect(html).toMatch(taggedPictogram("button", "arrow-up-tray", "Registrar informe", ' class="command" disabled=""'));
    expect(html).toMatch(markedHtml("refresh", "Cargando…"));
    expect(html).not.toContain("Sin informes registrados.");
  });

  it("tablero: el formulario de subir va tras «Ver detalle» (sigue en el DOM); la identidad, a la vista", () => {
    const html = render(createElement(ReportsPanel, { subject: "crew-01" }));
    expect(html).toContain("Ver detalle: Subir informe escaneado");
    const hidden = html.slice(html.indexOf('class="board-detail-body" hidden=""'));
    expect(hidden).toContain("Registrar informe");
    expect(hidden).not.toContain("Identidad para cotejar informes");
    // En la concha clásica no hay mando: el formulario se pinta como siempre.
    const classic = render(createElement(LookContext.Provider, { value: "classic" }, createElement(ReportsPanel, { subject: "crew-01" })));
    expect(classic).not.toContain("Ver detalle");
    expect(classic).toContain("Registrar informe");
  });
});

describe("<ReportBoard> (tablero)", () => {
  it("las cifras de informes y de páginas, y una píldora por clase con la hoja y la palabra del plegable", () => {
    const html = render(
      createElement(ReportBoard, {
        reports: [report({ pages: 3 }), report({ ledger_index: 12, kind: "alta", pages: 2 }), report({ ledger_index: 13 })],
      }),
    );
    expect(textNodes(html)).toEqual(["Informes", "3", "Páginas", "6", "Analítica", "2", "Informe de alta", "1"]);
    expect(html).toMatch(markedHtml("page-grid", "Analítica"));
    expect(html).toMatch(markedHtml("page-arrow-right", "Informe de alta"));
    expect(html).not.toContain("Otro");
    expect(html).not.toContain("no se usa");
  });

  it("los que no son de este tripulante: el triángulo amarillo y «no se usa», como en su plegable", () => {
    const foreign = { verdict: "otro_paciente", explanation: "E", usable: false };
    const html = render(createElement(ReportBoard, { reports: [report(), report({ ledger_index: 12, identity: foreign })], stale: true }));
    expect(html).toMatch(markedHtml("shape-triangle", "no se usa", "yellow"));
    expect(textNodes(html).join(" ")).toContain("no se usa 1");
    expect(html).toContain('class="stat-tile stale"');
  });
});
