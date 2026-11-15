import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { markedHtml, taggedPictogram, textNodes } from "../advisor/visibleText";
import type {
  ImagingStudy,
  DraftSignoff,
  Indicator,
  InterpretationDraft,
  ProtocolCatalog,
  RecordedFindings,
  SourceQuote,
  UltrasoundProtocol,
} from "../lib/api";
import { ApiError } from "../lib/api";
import { Attention, ReasonLine } from "./Attention";
import { CitedSource, Collation, Decision, DraftCard, DraftPanel, QuotedPhrase } from "./DraftPanel";
import { FindingsPanel } from "./FindingsPanel";
import { ArrivedBoard, ImagingHistory, SignSummary } from "./ImagingHistory";
import { SignValue } from "./SignValue";
import { EvolutionCells, StudyBoard, UltrasoundPanel } from "./UltrasoundPanel";
import { NOT_ASSESSABLE } from "./findings";

/**
 * Lo que pintan los paneles de ecografia: el pictograma junto a la palabra del backend, y la palabra
 * como unico texto. Se prueban las piezas sin red (sin efectos que llamen a la API).
 */

const render = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

const LUNG: UltrasoundProtocol = {
  key: "lung",
  display: "Pulmón",
  rationale: "",
  checklist: [],
  sources: [],
  source_grades: [],
  measures: [],
  views: [
    {
      key: "derecha-anterior",
      display: "Derecha, anterior",
      signs: [
        {
          key: "deslizamiento-pleural",
          display: "Deslizamiento pleural",
          values: { presente: "Presente", ausente: "Ausente", [NOT_ASSESSABLE]: "No valorable" },
        },
        {
          key: "lineas-b",
          display: "Líneas B",
          values: { ninguna: "Ninguna", multiples: "Múltiples", [NOT_ASSESSABLE]: "No valorable" },
        },
      ],
    },
  ],
};

const CATALOG: ProtocolCatalog = { protocols: [LUNG], method: {}, alerting: { active: false, note: "nota" } };

const record = (findings: RecordedFindings["findings"]): RecordedFindings => ({
  ledger_index: 3,
  recorded: "2026-11-14T08:00:00+00:00",
  protocol: "lung",
  checklist: [],
  recorded_by: "CMO",
  findings,
});

describe("<SignValue>", () => {
  it("presente, ausente y no valorable: tres dibujos, la palabra del protocolo como texto", () => {
    const present = render(createElement(SignValue, { code: "presente", children: "Presente" }));
    expect(present).toContain('data-pictogram="fan-dot"');
    expect(present).toMatch(/^<span class="mark">/);
    expect(textNodes(present)).toEqual(["Presente"]);

    const absent = render(createElement(SignValue, { code: "ausente", children: "Ausente" }));
    expect(absent).toContain('data-pictogram="fan-dash"');
    expect(textNodes(absent)).toEqual(["Ausente"]);

    const skipped = render(createElement(SignValue, { code: NOT_ASSESSABLE, children: "No valorable" }));
    expect(skipped).toContain('data-pictogram="slash-circle"');
    expect(skipped).toMatch(/^<span class="mark c-gray">/);
    expect(textNodes(skipped)).toEqual(["No valorable"]);
  });

  it("un valor que compara va con su palabra sola", () => {
    const html = render(createElement(SignValue, { code: "mayor", children: "Mayor" }));
    expect(html).toBe('<span class="mark">Mayor</span>');
  });
});

describe("<SignSummary> (Tierra)", () => {
  it("cada signo valorable con su marca; los no valorables se cuentan con «no disponible»", () => {
    const html = render(
      createElement(SignSummary, {
        catalog: CATALOG,
        record: record({ "derecha-anterior": { "deslizamiento-pleural": "ausente", "lineas-b": NOT_ASSESSABLE } }),
      }),
    );
    expect(html).toContain('data-pictogram="fan-dash"');
    expect(html).toContain('<div class="c-gray"><span class="mark"><svg');
    expect(html).toContain('data-pictogram="slash-circle"');
    expect(textNodes(html)).toEqual([
      "Deslizamiento pleural (Derecha, anterior):",
      "Ausente",
      "1",
      "signos no valorables",
    ]);
  });

  it("sin el protocolo en el catalogo no pinta nada: no inventa nombres", () => {
    expect(render(createElement(SignSummary, { catalog: null, record: record({}) }))).toBe("");
  });
});

describe("<EvolutionCells>", () => {
  const indicators: Record<string, Indicator> = {
    "onsd-right": { key: "onsd-right", display_es: "ONSD derecho", unit: "mm", decimals: 1 } as Indicator,
  };
  const cells = (value: number, previous: { value: number; effective: string } | null) =>
    render(
      createElement(
        "table",
        null,
        createElement(
          "tbody",
          null,
          createElement("tr", null, createElement(EvolutionCells, { record: "onsd-right", value, previous, indicators })),
        ),
      ),
    );

  it("sube y baja llevan su flecha, sin color: estas medidas aun no alertan", () => {
    const up = cells(6.1, { value: 5.5, effective: "2026-10-01T00:00:00+00:00" });
    expect(up).toContain('data-pictogram="arrow-up"');
    expect(up).not.toMatch(/c-(red|yellow)/);
    expect(textNodes(up)).toContain("sube 0,6 mm");
    const down = cells(5.0, { value: 5.5, effective: "2026-10-01T00:00:00+00:00" });
    expect(down).toContain('data-pictogram="arrow-down"');
    expect(textNodes(down)).toContain("baja 0,5 mm");
  });

  it("sin cambio y primera medida no llevan flecha", () => {
    expect(cells(5.5, { value: 5.5, effective: "2026-10-01T00:00:00+00:00" })).not.toContain("data-pictogram");
    const first = cells(5.5, null);
    expect(first).not.toContain("data-pictogram");
    expect(textNodes(first)).toEqual(["primera medida", "—"]);
  });
});

const located: SourceQuote = {
  estado: "localizada",
  frase: "frase del informe",
  detalle: "frase literal de informe:3",
  puntero: "informe:3",
  asiento: 3,
  desidentificado: true,
};

describe("<QuotedPhrase>", () => {
  it("localizada: las comillas junto a la palabra, la frase tal cual, sin color", () => {
    const html = render(createElement(QuotedPhrase, { quote: located }));
    expect(html).toContain('data-pictogram="guillemets"');
    expect(html).toContain("«frase del informe»");
    expect(html).not.toMatch(/c-(yellow|gray)/);
    expect(textNodes(html)).toContain("Frase localizada");
  });

  it("no localizada: triangulo y amarillo, con el detalle del backend", () => {
    const html = render(
      createElement(QuotedPhrase, { quote: { ...located, estado: "no_localizada", frase: "", detalle: "no existe" } }),
    );
    expect(html).toMatch(/^<p class="c-yellow"><span class="mark"><svg[^>]*data-pictogram="shape-triangle"/);
    expect(textNodes(html)).toEqual(["Frase no localizada", "· no existe"]);
  });

  it("no aplica: no disponible, circulo tachado y gris", () => {
    const html = render(createElement(QuotedPhrase, { quote: { estado: "no_aplica", frase: "", detalle: "" } }));
    expect(html).toMatch(/^<p class="c-gray">/);
    expect(html).toContain('data-pictogram="slash-circle"');
  });
});

describe("<Collation>", () => {
  it("una segunda firma no cotejada se dice con el circulo tachado y el texto del backend", () => {
    const html = render(
      createElement(Collation, {
        draft: { countersign_collation: { collated: false, label: "no cotejada", why: "x", text: "TEXTO-BACKEND" } },
      }),
    );
    expect(html).toContain('<p class="c-gray"><span class="mark"><svg');
    expect(html).toContain('data-pictogram="slash-circle"');
    expect(textNodes(html)).toEqual(["TEXTO-BACKEND"]);
  });

  it("una cotejada no lleva linea", () => {
    const html = render(
      createElement(Collation, {
        draft: { countersign_collation: { collated: true, label: "cotejada", why: null, text: "x" } },
      }),
    );
    expect(html).toBe("");
  });
});

const signoff = (extra: Partial<DraftSignoff> = {}): DraftSignoff => ({
  decision: "accepted",
  signed_by: "CMO",
  comment: "",
  recorded: "2026-11-14T09:00:00+00:00",
  ...extra,
});

describe("<Decision> y <CitedSource>", () => {
  // Segunda pasada (§5.33.10): «rechazado» lleva el dibujo del mando «rechazar» (`reject`, el
  // circulo tachado), no la cruz, que es «cancelar» y la del fallo de una peticion.
  it("aceptado lleva el hecho; rechazado, el circulo tachado de «rechazar»; la palabra es el hijo", () => {
    const accepted = render(createElement(Decision, { decision: "accepted", children: "Aceptado" }));
    expect(accepted).toContain('data-pictogram="check"');
    expect(textNodes(accepted)).toEqual(["Aceptado"]);
    const rejected = render(createElement(Decision, { decision: "rejected", children: "rechazado" }));
    expect(rejected).toContain('data-pictogram="slash-circle"');
    expect(rejected).not.toContain('data-pictogram="cross"');
    expect(textNodes(rejected)).toEqual(["rechazado"]);
  });

  it("una cita que el registro desmiente lleva triangulo y amarillo; una confirmada, ninguno", () => {
    const fabricated = render(
      createElement(CitedSource, {
        signature: signoff({ source: "PMID 1", source_check: { estado: "FABRICADA", detalle: "no existe" } }),
      }),
    );
    expect(fabricated).toMatch(/^<p class="c-yellow"><span class="mark"><svg[^>]*data-pictogram="shape-triangle"/);
    expect(textNodes(fabricated).join("")).toBe("Fuente de CMO: PMID 1 · no existe");
    const fine = render(
      createElement(CitedSource, {
        signature: signoff({ source: "PMID 1", source_check: { estado: "confirmada", detalle: "ok" } }),
      }),
    );
    expect(fine).toBe('<p class="secondary"><span class="mark">Fuente de CMO: PMID 1 · ok</span></p>');
  });
});

const draft = (extra: Partial<InterpretationDraft> = {}): InterpretationDraft => ({
  ledger_index: 7,
  recorded: "2026-11-14T09:00:00+00:00",
  study_index: 3,
  model: "modelo-local",
  status: "unvalidated",
  text: "TEXTO DEL BORRADOR",
  text_sha256: "a".repeat(64),
  verifier_problems: [],
  signoff: null,
  countersign: null,
  record: { second_signature_required: false, complete: false, disagreement: false },
  ...extra,
});

describe("<DraftCard>: el borrador se ve como borrador (Clase C)", () => {
  it("sin firmar: triangulo amarillo en SIN VALIDAR y la hoja a trazos junto al texto del modelo", () => {
    const html = render(createElement(DraftCard, { draft: draft(), onSigned: () => undefined }));
    expect(html).toMatch(/<p class="c-yellow"><span class="mark"><svg[^>]*data-pictogram="shape-triangle"/);
    expect(html).toMatch(/<p class="draft-text"><span class="mark"><svg[^>]*data-pictogram="page-dashed"/);
    expect(textNodes(html)).toContain("TEXTO DEL BORRADOR");
    expect(textNodes(html).join(" ")).toContain("BORRADOR SIN VALIDAR");
  });

  it("firmado: la decision con su marca, y el texto sigue siendo un borrador (hoja a trazos)", () => {
    const html = render(createElement(DraftCard, { draft: draft({ signoff: signoff() }), onSigned: () => undefined }));
    expect(html).toContain('data-pictogram="check"');
    expect(html).toContain('data-pictogram="page-dashed"');
    expect(textNodes(html).join(" ")).toContain("Aceptado por CMO");
  });

  it("bloqueado: triangulo amarillo y los motivos del backend, sin texto del modelo", () => {
    const blocked = draft({ status: "blocked", reasons: ["MOTIVO"] });
    delete blocked.text;
    const html = render(createElement(DraftCard, { draft: blocked, onSigned: () => undefined }));
    expect(html).toContain('data-pictogram="shape-triangle"');
    expect(html).not.toContain('data-pictogram="page-dashed"');
    expect(textNodes(html)).toEqual(["Borrador bloqueado antes de mostrarse:", "MOTIVO"]);
  });

  it("las dos firmas discrepan: triangulo, y cada decision con la suya", () => {
    const html = render(
      createElement(DraftCard, {
        draft: draft({
          signoff: signoff(),
          countersign: signoff({ decision: "rejected", signed_by: "Ingeniera" }),
          record: { second_signature_required: true, complete: true, disagreement: true },
        }),
        onSigned: () => undefined,
      }),
    );
    expect(html).toContain('data-pictogram="check"');
    expect(html).toContain('data-pictogram="slash-circle"');
    expect(textNodes(html).join(" ")).toContain("Las dos firmas discrepan.");
  });
});

/*
 * Segunda pasada (2026-10-21, §5.33.10): cada titulo, plegable, rotulo, cabecera y mando del area
 * lleva el signo de lo que es, y todo aviso que era solo color lleva su forma. Se pintan sin red:
 * `renderToStaticMarkup` no corre los efectos que llaman a la API.
 */
describe("segunda pasada: el signo de cada cosa del area de ecografia", () => {
  it("el borrador: la hoja a trazos en el titulo y en «Pedir borrador»", () => {
    const html = render(createElement(DraftPanel, { study: 3, measured: true }));
    expect(html).toMatch(taggedPictogram("h3", "page-dashed", "Borrador de interpretación"));
    expect(html).toMatch(taggedPictogram("button", "page-dashed", "Pedir borrador", ' class="command" disabled=""'));
  });

  it("la firma: quien revisa, su comentario y su fuente con su signo; aceptar y rechazar con el de su mando", () => {
    const html = render(createElement(DraftCard, { draft: draft(), onSigned: () => undefined }));
    expect(html).toMatch(taggedPictogram("label", "person", "Revisado por", ' class="operator"'));
    expect(html).toMatch(taggedPictogram("label", "bubble-lines", "Comentario"));
    expect(html).toMatch(taggedPictogram("label", "book-open", "Fuente (opcional)"));
    expect(html).toMatch(taggedPictogram("button", "check", "Aceptar borrador", ' class="command" disabled=""'));
    expect(html).toMatch(taggedPictogram("button", "slash-circle", "Rechazar borrador", ' class="command" disabled=""'));
  });

  it("las objeciones del comite son un plegable con el bocadillo y la cuenta", () => {
    const html = render(
      createElement(DraftCard, {
        draft: draft({
          dossier: {
            committee: ["revisor"],
            head: [{ title: "OBJECION", impact: "alta", quote: null, source: "PMID 1" }],
            deferred: [],
            warnings: [],
            untraceable: false,
          },
        }),
        onSigned: () => undefined,
      }),
    );
    expect(html).toMatch(taggedPictogram("summary", "bubble-lines", "Objeciones del comité (", ' class="secondary"'));
    expect(textNodes(html)).toContain("1");
  });

  it("calidad y signos: la lista en el titulo, la chincheta en cada ventana, quien anota y «Registrar»", () => {
    const html = render(createElement(FindingsPanel, { study: 3, protocol: LUNG, onRecorded: () => undefined }));
    expect(html).toMatch(taggedPictogram("h3", "list-check", "Calidad y signos anotados"));
    expect(html).toMatch(taggedPictogram("legend", "pin", "Derecha, anterior"));
    expect(html).toMatch(taggedPictogram("label", "person", "Anotado por", ' class="operator"'));
    expect(html).toMatch(taggedPictogram("button", "pen", "Registrar", ' class="command" disabled=""'));
  });

  it("Tierra: la sonda en el titulo, el retardo junto a lo que esta en transito", () => {
    const html = render(createElement(ImagingHistory, { subject: "crew-01", oneWayMinutes: 12 }));
    expect(html).toMatch(taggedPictogram("h2", "probe-fan", "Ecografías recibidas"));
    expect(html).toMatch(markedHtml("signal-arcs", "Lo registrado a bordo en los últimos"));
  });

  it("antes de la primera respuesta se dice que carga, no que no ha llegado nada", () => {
    const ground = render(createElement(ImagingHistory, { subject: "crew-01", oneWayMinutes: null }));
    expect(ground).toMatch(markedHtml("refresh", "Cargando…"));
    expect(ground).not.toContain("Todavía no ha llegado");
    const onboard = render(createElement(UltrasoundPanel, { subject: "crew-01" }));
    expect(onboard).toMatch(taggedPictogram("h2", "probe-fan", "Ecografía"));
    expect(onboard).toMatch(markedHtml("refresh", "Cargando…"));
    expect(onboard).not.toContain("Sin estudios registrados.");
  });

  it("un aviso del backend que pide mirarlo lleva el triangulo en amarillo, no solo el color", () => {
    const html = render(createElement(Attention, { children: "MOTIVO" }));
    expect(html).toMatch(/^<p class="c-yellow">/);
    expect(html).toMatch(markedHtml("shape-triangle", "MOTIVO"));
  });

  it("lo que sale mal se marca por lo que es, no por el sitio: rechazo con triangulo, fallo con cruz roja", () => {
    // Con la marca de toda la interfaz (`requestOutcome`, §5.34.14), no el parrafo amarillo a mano.
    const refused = render(createElement(ReasonLine, { reason: new ApiError(422, "MOTIVO") }));
    expect(refused).toMatch(/^<p><span class="mark c-yellow">/);
    expect(refused).toMatch(markedHtml("shape-triangle", "MOTIVO", "yellow"));
    const broken = render(createElement(ReasonLine, { reason: new ApiError(500, "ROTO") }));
    expect(broken).toMatch(markedHtml("cross", "ROTO", "red"));
    const unreachable = render(createElement(ReasonLine, { reason: new TypeError("Failed to fetch") }));
    expect(unreachable).toMatch(markedHtml("cross", "TypeError: Failed to fetch", "red"));
    expect(unreachable).not.toContain("c-yellow");
    // El 409 del registro roto (un asiento manipulado, la calibracion firmada ilegible) no es un
    // «no» que se corrige: cruz en rojo con el motivo del backend tal cual (§5.35.12).
    const tampered = render(createElement(ReasonLine, { reason: new ApiError(409, "calibración del estudio ilegible") }));
    expect(tampered).toMatch(markedHtml("cross", "calibración del estudio ilegible", "red"));
    const record = render(createElement(ReasonLine, { reason: new ApiError(409, "integridad comprometida: asiento 4: X", true) }));
    expect(record).toMatch(markedHtml("cross", "integridad comprometida: asiento 4: X", "red"));
    expect(tampered + record).not.toContain("c-yellow");
  });
});

describe("<StudyBoard> (tablero)", () => {
  const study = (extra: Partial<ImagingStudy>): ImagingStudy => ({
    ledger_index: 1,
    recorded: "2026-11-07T10:00:00+00:00",
    subject: "crew-01",
    protocol: "lung",
    acquired: "2026-11-07T10:00:00+00:00",
    source: "dicom",
    sha256: "x",
    size_bytes: 1,
    frames: 1,
    rows: 10,
    columns: 10,
    calibration: [{ x0: 0, y0: 0, x1: 10, y1: 10, mm_per_px_x: 0.1, mm_per_px_y: 0.1 }],
    burned_in_annotation: "NO",
    ...extra,
  });
  const name = (key: string) => (key === "lung" ? "Pulmón" : key);

  it("la cifra de estudios y una píldora por protocolo, con el dibujo y el nombre del catálogo", () => {
    const html = render(
      createElement(StudyBoard, {
        studies: [study({ protocol: "bladder" }), study({ ledger_index: 2 }), study({ ledger_index: 3 })],
        order: ["optic-nerve", "lung", "bladder"],
        protocolName: name,
      }),
    );
    // En el orden del catálogo, no en el de llegada; un protocolo sin estudios no se pinta.
    expect(textNodes(html)).toEqual(["Estudios", "3", "Pulmón", "2", "bladder", "1"]);
    expect(html).not.toContain("stale");
    expect(html).toMatch(markedHtml("lungs", "Pulmón"));
    expect(html).toMatch(markedHtml("bladder", "bladder"));
    // Sin fantomas, ejemplos ni estudios sin calibrar no hay píldora de procedencia ni cian.
    expect(html).not.toContain("c-cyan");
  });

  it("fantomas, ejemplos reales y estudios sin calibrar, con las palabras de la lista y el cian de lo ausente", () => {
    const dataset = { name: "D", citation: "C", doi: "d", license: "CC BY 4.0", url: "u" };
    const html = render(
      createElement(StudyBoard, {
        studies: [study({ synthetic: true }), study({ ledger_index: 2, dataset, calibration: [] })],
        order: [],
        protocolName: name,
        stale: true,
      }),
    );
    const text = textNodes(html).join(" ");
    expect(text).toContain("Fantoma simulado 1");
    expect(text).toContain("Ejemplo real 1");
    expect(html).toMatch(markedHtml("ring-dotted", "sin calibración", "cyan"));
    // Tras una lectura fallida la cifra que queda es la anterior: en cursiva.
    expect(html).toContain('class="stat-tile stale"');
  });
});

describe("<ArrivedBoard> (tablero de Tierra)", () => {
  const study = { ledger_index: 1, calibration: [] } as unknown as ImagingStudy;
  const measurement = { key: "onsd-right", value: 5.1, ledger_index: 2 } as unknown as Parameters<
    typeof ArrivedBoard
  >[0]["rows"][number]["measurements"][number];

  it("los estudios y las medidas llegadas, contados de las filas de la tabla", () => {
    const rows = [
      { study, measurements: [measurement, measurement], findings: [] },
      { study: { ...study, ledger_index: 3 }, measurements: [], findings: [] },
    ];
    const html = render(createElement(ArrivedBoard, { rows, stale: false }));
    expect(html).toMatch(/Estudios llegados<\/span><span class="stat-value"><span class="num">2<\/span>/);
    expect(html).toMatch(/Medidas llegadas<\/span><span class="stat-value"><span class="num">2<\/span>/);
    expect(render(createElement(ArrivedBoard, { rows, stale: true }))).toContain('class="stat-tile stale"');
  });
});
