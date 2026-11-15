/**
 * La frase literal del informe citado, antes de la segunda firma: que se rotula, que se devuelve
 * al firmar y cuando lo que se vio deja de valer.
 *
 * Por que existe aparte del panel: aqui lo que se puede equivocar es logica, no pintura. Una
 * frase vista para "informe:3" que se firma con "informe:4", o un "no localizada" sin color ni
 * pictograma, harian pasar por leido lo que nadie leyo. Esta en un `.ts` para que lo pruebe
 * `sourceQuote.test.ts`.
 *
 * Nada de aqui redacta: la frase y el motivo son los de `POST /api/imaging/drafts/{i}/source-quote`
 * (el texto des-identificado del informe, tal cual). Lo unico propio son rotulos de estado.
 */

import type {
  SecondSignatureCollation,
  SecondSignatureGate,
  SecondSignatureRule,
  SeenQuote,
  SourceQuote,
} from "../lib/api";
import type { PictogramName } from "../icons/registry";
import { formatNumber } from "../lib/format";
import type { Token } from "../lib/palette";

export interface QuoteStyle {
  pictogram: PictogramName;
  word: string;
  /** `null`: sin color de la tabla F.5-1, texto normal. */
  color: Token | null;
}

/**
 * "No localizada" hay que mirarla antes de firmar: amarillo con triangulo (F.5-1, *attention
 * required*), como las demas citas que no se sostienen. "Localizada" no es un visto bueno clinico
 * —acredita que la frase esta en el informe, no que sostenga la decision—: sin color, con las
 * comillas de la cita. Una fuente que no es un informe no tiene frase: gris, *unavailable*.
 * Siempre pictograma y palabra (F.5.10 e).
 */
export function quoteStyle(quote: Pick<SourceQuote, "estado">): QuoteStyle {
  if (quote.estado === "localizada") return { pictogram: "guillemets", word: "localizada", color: null };
  if (quote.estado === "no_localizada") {
    return { pictogram: "shape-triangle", word: "no localizada", color: "yellow" };
  }
  return { pictogram: "slash-circle", word: "no disponible", color: "gray" };
}

/** De donde sale la frase: el informe, su asiento en el registro y que es texto des-identificado. */
export function provenance(quote: SourceQuote): string {
  const parts: string[] = [];
  if (quote.puntero) parts.push(quote.puntero);
  if (typeof quote.asiento === "number") parts.push(`asiento ${formatNumber(quote.asiento)} del registro`);
  if (quote.desidentificado) parts.push("texto des-identificado");
  return parts.join(" · ");
}

/** Lo que la segunda firma devuelve para que se firme lo que se vio; nada si no habia informe. */
export function seenOf(quote: SourceQuote | null): SeenQuote | undefined {
  if (quote === null || quote.estado === "no_aplica") return undefined;
  return { estado: quote.estado, frase: quote.frase, sha256: quote.sha256 ?? null };
}

/** Lo que identifica una vista: cambia la cita o quien firma, y lo visto ya no vale. */
export function viewKey(source: string, fragment: string, operator: string): string {
  return JSON.stringify([source.trim().toLowerCase(), fragment.trim(), operator.trim()]);
}

/** Si la frase que hay en pantalla es la de la cita que se va a firmar. */
export function isCurrent(view: { key: string } | null, key: string): boolean {
  return view !== null && view.key === key;
}

/** Si la fuente tecleada es un informe guardado (`informe:<n>`): la unica que se puede cotejar. */
export function citesReport(source: string): boolean {
  return /^\s*informe:\d+\s*$/i.test(source);
}

/** Lo que se tiene delante tras pedir la frase: la frase y lo que el backend dice de la firma. */
export interface Looked {
  quote: SourceQuote;
  /** Ausente si el backend es anterior a la regla del 2026-10-13. */
  gate?: SecondSignatureGate | undefined;
}

export interface SecondSignatureOffer {
  /** Si los botones de la segunda firma se ofrecen. */
  offered: boolean;
  /** Que falta para ofrecerlos: texto del backend, tal cual. `null` si se ofrecen. */
  why: string | null;
  /** Si toca pedir la declaracion de haber leido la frase (ya esta delante y es cotejable). */
  askDeclaration: boolean;
}

/**
 * Si la segunda firma se ofrece con esta cita, y si no, que falta. La regla la impone el backend
 * (422 y ningun asiento); esto solo evita ofrecer un boton que se sabe que va a rechazar, y dice
 * antes de firmar que hace falta, paso a paso, con sus mismos textos (`second_signature_rule` y
 * `second_signature.reason`): aqui no se redacta ninguno. Desde el 2026-10-15 la segunda firma
 * tiene que citar un informe guardado: sin fuente, o con otra que no lo es, no se ofrece.
 */
export function secondSignatureOffer(input: {
  rule: SecondSignatureRule | undefined;
  source: string;
  looked: Looked | null;
  declared: boolean;
}): SecondSignatureOffer {
  const { rule, source, looked, declared } = input;
  // Sin los textos de la regla (un backend anterior a ella) no se puede decir que falta: se
  // ofrece y decide el backend, en vez de dejar un boton cerrado sin poder decir por que.
  if (!citesReport(source)) {
    if (rule === undefined) return { offered: true, why: null, askDeclaration: false };
    const why = source.trim() === "" ? rule.must_cite : rule.not_collatable;
    return { offered: false, why, askDeclaration: false };
  }
  if (looked === null) {
    return { offered: false, why: rule?.must_look ?? null, askDeclaration: false };
  }
  const located = looked.quote.estado === "localizada";
  if (!located || looked.gate?.allowed === false) {
    const why = looked.gate?.reason ?? looked.quote.detalle ?? null;
    return { offered: false, why, askDeclaration: false };
  }
  if (rule === undefined) return { offered: true, why: null, askDeclaration: false };
  if (!declared) {
    return { offered: false, why: rule.must_declare, askDeclaration: true };
  }
  return { offered: true, why: null, askDeclaration: true };
}

export interface CollationLine {
  pictogram: PictogramName;
  color: Token;
  /** Texto del backend (`countersign_collation.text`), tal cual. */
  text: string;
}

/**
 * Lo que se pinta de una segunda firma que no se cotejo con la frase de un informe. Hoy no se
 * escribe ninguna (desde el 2026-10-15 la segunda firma cita un informe), pero las admitidas antes
 * siguen en el registro y no se callan: sin esto, en el panel se verian igual que una cotejada.
 * Gris con el circulo tachado, *unavailable* de la tabla F.5-1: el cotejo no esta disponible, no
 * es un fallo. Una cotejada no lleva linea: ya se ve su frase.
 */
export function collationLine(
  collation: SecondSignatureCollation | null | undefined,
): CollationLine | null {
  if (collation === null || collation === undefined || collation.collated) return null;
  return { pictogram: "slash-circle", color: "gray", text: collation.text };
}
