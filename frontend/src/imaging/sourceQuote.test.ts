import { describe, expect, it } from "vitest";

import type { SecondSignatureRule, SourceQuote } from "../lib/api";
import { palette } from "../lib/palette";
import {
  citesReport,
  collationLine,
  isCurrent,
  provenance,
  quoteStyle,
  secondSignatureOffer,
  seenOf,
  viewKey,
} from "./sourceQuote";

const located: SourceQuote = {
  estado: "localizada",
  frase: "higado de tamano normal,\nsin lesiones",
  detalle: "frase literal de informe:3",
  puntero: "informe:3",
  informe: 3,
  asiento: 3,
  inicio: 21,
  fin: 58,
  sha256: "a".repeat(64),
  desidentificado: true,
};
const missing: SourceQuote = { ...located, estado: "no_localizada", frase: "", inicio: null, fin: null };

describe("la frase literal de la fuente, antes de la segunda firma", () => {
  it("«no localizada» lleva pictograma, palabra y el color de «hay que mirarlo»", () => {
    const style = quoteStyle(missing);
    expect(style).toEqual({ pictogram: "shape-triangle", word: "no localizada", color: "yellow" });
    expect(style.color !== null && style.color in palette).toBe(true);
  });

  it("«localizada» no es un visto bueno: sin color, con las comillas y la palabra", () => {
    const style = quoteStyle(located);
    expect(style.color).toBeNull();
    expect(style.pictogram).toBe("guillemets");
    expect(style.word).toBe("localizada");
  });

  it("una fuente que no es un informe es «no disponible» (gris, circulo tachado), no «dato ausente» (cian)", () => {
    expect(quoteStyle({ estado: "no_aplica" })).toEqual({
      pictogram: "slash-circle",
      word: "no disponible",
      color: "gray",
    });
  });

  it("cada estado tiene su propio pictograma: ninguno se disfraza de otro", () => {
    const names = (["localizada", "no_localizada", "no_aplica"] as const).map(
      (estado) => quoteStyle({ estado }).pictogram,
    );
    expect(new Set(names).size).toBe(3);
  });

  it("la procedencia nombra el informe, su asiento y que el texto esta des-identificado", () => {
    expect(provenance(located)).toBe("informe:3 · asiento 3 del registro · texto des-identificado");
    expect(provenance({ estado: "no_aplica", frase: "", detalle: "" })).toBe("");
  });

  it("se devuelve lo que se vio, tal cual, y nada si no habia informe", () => {
    expect(seenOf(located)).toEqual({ estado: "localizada", frase: located.frase, sha256: located.sha256 });
    expect(seenOf(missing)).toEqual({ estado: "no_localizada", frase: "", sha256: located.sha256 });
    expect(seenOf({ estado: "no_localizada", frase: "", detalle: "no existe" })?.sha256).toBeNull();
    expect(seenOf({ estado: "no_aplica", frase: "", detalle: "" })).toBeUndefined();
    expect(seenOf(null)).toBeUndefined();
  });

  it("lo visto deja de valer si cambia la cita, el fragmento o quien firma", () => {
    const view = { key: viewKey("informe:3", "higado de tamano normal", "Ingeniera") };
    expect(isCurrent(view, viewKey(" INFORME:3 ", "higado de tamano normal ", "Ingeniera"))).toBe(true);
    expect(isCurrent(view, viewKey("informe:4", "higado de tamano normal", "Ingeniera"))).toBe(false);
    expect(isCurrent(view, viewKey("informe:3", "higado de tamano", "Ingeniera"))).toBe(false);
    expect(isCurrent(view, viewKey("informe:3", "higado de tamano normal", "CMO"))).toBe(false);
    expect(isCurrent(null, view.key)).toBe(false);
  });
});

// Textos de pega: en la consola llegan del backend (`second_signature_rule`); aqui solo se
// comprueba que el panel pinta ESOS y no otros.
const rule: SecondSignatureRule = {
  since: "2026-10-15",
  must_cite: "texto-del-backend: hay que citar un informe guardado",
  must_look: "texto-del-backend: pedir la frase",
  declaration: "texto-del-backend: la he leido",
  must_declare: "texto-del-backend: falta declararlo",
  not_collatable: "texto-del-backend: no es un informe, no vale",
};
const allowed = { collatable: true, allowed: true, reason: null };
const refused = { collatable: true, allowed: false, reason: "texto-del-backend: el 422" };

describe("la segunda firma no se ofrece sin un informe citado, su frase localizada, delante y leida", () => {
  const offer = (source: string, looked: Parameters<typeof secondSignatureOffer>[0]["looked"], declared = false) =>
    secondSignatureOffer({ rule, source, looked, declared });

  it("solo `informe:<n>` es una cita que se puede cotejar", () => {
    expect(citesReport(" Informe:12 ")).toBe(true);
    expect(citesReport("informe:")).toBe(false);
    expect(citesReport("PMID 12345678")).toBe(false);
    expect(citesReport("")).toBe(false);
  });

  it("sin fuente no se ofrece: antes de nada se dice que hay que citar un informe", () => {
    expect(offer("  ", null)).toEqual({ offered: false, why: rule.must_cite, askDeclaration: false });
  });

  it("una fuente que no es un informe no se ofrece, con el porque del backend", () => {
    for (const source of ["PMID 12345678", "DOI 10.1/x", "informe:", "contramedida: ejercicio"]) {
      expect(offer(source, null)).toEqual({ offered: false, why: rule.not_collatable, askDeclaration: false });
    }
  });

  it("cita un informe y no se ha pedido la frase: no se ofrece, y lo explica el backend", () => {
    expect(offer("informe:3", null)).toEqual({
      offered: false,
      why: rule.must_look,
      askDeclaration: false,
    });
  });

  it("la cita no se localiza: no se ofrece ni se pide declarar, con el motivo del rechazo", () => {
    const result = offer("informe:3", { quote: missing, gate: refused }, true);
    expect(result).toEqual({ offered: false, why: refused.reason, askDeclaration: false });
  });

  it("no localizada con un backend que no dice por que: no se ofrece, con el detalle de la cita", () => {
    const result = offer("informe:3", { quote: { ...missing, detalle: "no existe" } }, true);
    expect(result.offered).toBe(false);
    expect(result.why).toBe("no existe");
  });

  it("el backend dice que no aunque la frase este localizada: manda el backend", () => {
    expect(offer("informe:3", { quote: located, gate: refused }, true).offered).toBe(false);
  });

  it("localizada y sin declarar: no se ofrece, y se pide la declaracion", () => {
    expect(offer("informe:3", { quote: located, gate: allowed })).toEqual({
      offered: false,
      why: rule.must_declare,
      askDeclaration: true,
    });
  });

  it("localizada, delante y declarada: se ofrece", () => {
    expect(offer("informe:3", { quote: located, gate: allowed }, true)).toEqual({
      offered: true,
      why: null,
      askDeclaration: true,
    });
  });

  it("sin los textos de la regla no deja un boton cerrado sin explicacion: decide el backend", () => {
    for (const [source, looked] of [
      ["informe:3", { quote: located, gate: allowed }],
      ["PMID 12345678", null],
      ["", null],
    ] as const) {
      const result = secondSignatureOffer({ rule: undefined, source, looked, declared: false });
      expect(result).toEqual({ offered: true, why: null, askDeclaration: false });
    }
  });

  it("no redacta: todo texto que devuelve es uno de los que dio el backend", () => {
    const given = new Set<string | null>([null, ...Object.values(rule), refused.reason, missing.detalle]);
    const cases = [
      offer("informe:3", null),
      offer("informe:3", { quote: missing, gate: refused }),
      offer("informe:3", { quote: missing }),
      offer("informe:3", { quote: located, gate: allowed }),
      offer("informe:3", { quote: located, gate: allowed }, true),
      offer("DOI 10.1/x", null),
      offer("", null),
    ];
    for (const result of cases) {
      expect(given.has(result.why)).toBe(true);
    }
  });

  it("antes de firmar, cada paso dice que falta, y solo el ultimo ofrece los botones", () => {
    const steps = [
      offer("", null),
      offer("informe:3", null),
      offer("informe:3", { quote: located, gate: allowed }),
      offer("informe:3", { quote: located, gate: allowed }, true),
    ];
    expect(steps.map((step) => step.why)).toEqual([rule.must_cite, rule.must_look, rule.must_declare, null]);
    expect(steps.map((step) => step.offered)).toEqual([false, false, false, true]);
  });
});

describe("segunda firma no cotejada", () => {
  const notCollated = {
    collated: false,
    label: "no cotejada",
    why: "texto-del-backend: el porque",
    text: "texto-del-backend: Segunda firma no cotejada",
  };

  it("se dice a la vista, con pictograma, color de no disponible y el texto del backend tal cual", () => {
    const line = collationLine(notCollated);
    expect(line).toEqual({ pictogram: "slash-circle", color: "gray", text: notCollated.text });
    expect(line !== null && line.color in palette).toBe(true);
  });

  it("una cotejada no lleva linea (su frase ya se ve), y sin dato del backend tampoco", () => {
    expect(collationLine({ ...notCollated, collated: true, why: null })).toBeNull();
    expect(collationLine(null)).toBeNull();
    expect(collationLine(undefined)).toBeNull();
  });
});
