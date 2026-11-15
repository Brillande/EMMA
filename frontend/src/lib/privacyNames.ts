/**
 * Los nombres que el modo privacidad tapa dentro de las frases que se dejan a la vista (§5.40).
 *
 * Por qué existe: la privacidad deja a la vista el estado general, las alertas y «Qué hacer», y
 * esas frases las redacta el backend con el nombre del tripulante dentro («Cambio individual en
 * crew-02», «Reconocida por Ana»). La interfaz no reescribe texto clínico, así que no puede quitar
 * el nombre de la frase; lo que sí puede es no **pintarlo**: cada aparición exacta de un nombre
 * conocido se marca con un `Highlight` de CSS (`::highlight(emma-private-name)` en `styles.css`),
 * que la pinta como una barra gris sin letra. El texto del DOM, el que llega del backend, no se
 * toca, y fuera del modo privacidad no hay nada que quitar.
 *
 * Qué es un nombre conocido: los tripulantes del selector, el que se mira, quien está en la
 * consola (`emma.operator`) y quien firmó algo en el estado recibido (las claves `*_by` de
 * personas). Una aparición cuenta si es la palabra entera: «Ana» no tapa media «Mañana».
 *
 * Sin la API de resaltado (navegadores viejos) no se puede tapar solo el nombre, y entonces la
 * privacidad tapa también las secciones de estado general (`ConsoleTabs.tsx`): mejor de más que
 * dejar un nombre a la vista con un aviso que dice lo contrario.
 */

/** El nombre del resaltado, el mismo que `::highlight(...)` en `styles.css`. */
export const PRIVATE_NAME_HIGHLIGHT = "emma-private-name";

/**
 * Las claves del estado cuyo valor es quien firmó: personas. Fuera quedan las `*_by` que no lo son
 * (`shelter_ready_by` es una hora; `cited_by` y `used_by`, referencias).
 */
const SIGNER_KEYS: ReadonlySet<string> = new Set([
  "acknowledged_by",
  "adopted_by",
  "closed_by",
  "confirmed_by",
  "decided_by",
  "declared_by",
  "measured_by",
  "note_by",
  "recorded_by",
  "reported_by",
  "requested_by",
  "signed_by",
  "silenced_by",
  "since_declared_by",
]);

/** Quien firmó algo en un estado (o en cualquier respuesta), buscado en todo el árbol. */
export function signersIn(value: unknown, found: Set<string> = new Set()): Set<string> {
  if (Array.isArray(value)) {
    for (const item of value) signersIn(item, found);
  } else if (typeof value === "object" && value !== null) {
    for (const [key, item] of Object.entries(value)) {
      if (SIGNER_KEYS.has(key)) {
        const names = Array.isArray(item) ? item : [item];
        for (const name of names) if (typeof name === "string") found.add(name);
      } else {
        signersIn(item, found);
      }
    }
  }
  return found;
}

/**
 * Los nombres a tapar, sin vacíos ni repetidos y del más largo al más corto: así «crew-01» no se
 * queda a medias porque antes se encontrara «crew».
 */
export function privateNames(sources: readonly (string | null | undefined)[], statuses: readonly unknown[] = []): string[] {
  const names = new Set<string>();
  for (const name of sources) if (typeof name === "string") names.add(name.trim());
  for (const status of statuses) for (const name of signersIn(status)) names.add(name.trim());
  names.delete("");
  return [...names].sort((a, b) => b.length - a.length || a.localeCompare(b));
}

const WORD = /[\p{L}\p{N}_]/u;

/**
 * Dónde está cada nombre en un texto: pares `[inicio, fin)` sin solaparse, en orden. Solo
 * apariciones exactas de palabra entera (lo de antes y lo de después no es letra, cifra ni `_`).
 */
export function nameRanges(text: string, names: readonly string[]): [number, number][] {
  const taken: [number, number][] = [];
  for (const name of names) {
    if (name.length === 0) continue;
    let from = 0;
    for (;;) {
      const start = text.indexOf(name, from);
      if (start < 0) break;
      const end = start + name.length;
      from = start + 1;
      const before = text[start - 1] ?? "";
      const after = text[end] ?? "";
      if ((before !== "" && WORD.test(before)) || (after !== "" && WORD.test(after))) continue;
      if (taken.some(([a, b]) => start < b && a < end)) continue;
      taken.push([start, end]);
    }
  }
  return taken.sort((x, y) => x[0] - y[0]);
}

/** Si este navegador sabe pintar resaltados de CSS (`CSS.highlights` y `Highlight`). */
export function namesMaskable(): boolean {
  return (
    typeof CSS !== "undefined" &&
    "highlights" in CSS &&
    typeof (globalThis as { Highlight?: unknown }).Highlight === "function"
  );
}

/** Los tramos de texto de `root` donde aparece un nombre, para el resaltado. */
export function nameRangesIn(root: Node, names: readonly string[]): Range[] {
  const ranges: Range[] = [];
  if (names.length === 0) return ranges;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    for (const [start, end] of nameRanges(node.nodeValue ?? "", names)) {
      const range = document.createRange();
      range.setStart(node, start);
      range.setEnd(node, end);
      ranges.push(range);
    }
  }
  return ranges;
}
