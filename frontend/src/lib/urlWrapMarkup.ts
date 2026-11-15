/**
 * La guarda de `urlWrap.test.ts` mirando lo pintado y no el código (§5.38.12).
 *
 * Por qué existe: la guarda del código lee cada línea de cada componente y busca un `num` sin `url`
 * que encierre algo llamado «url». No ve una dirección que llega con otro nombre (`listed_in`,
 * `where`, `sites`), ni una clase montada con una plantilla, ni el texto que hereda el `.num` de un
 * elemento de más arriba. Esto mira el HTML que React pinta: todo texto con una dirección cuyo
 * `.num` más cercano no lleva `url` (ni `wrap`) es una dirección que no se parte (`white-space: pre`).
 *
 * Solo para pruebas (no lo importa ningún componente: no entra en lo que se sirve): lo llaman las
 * de los paneles que pintan direcciones, con sus datos de ejemplo, y sus casos están en
 * `urlWrap.test.ts`. No sustituye a la guarda del código, que mira todas las líneas aunque ningún ejemplo
 * las pinte; la completa, que ve lo pintado aunque el código no diga «url».
 */

// Lo que se lee como una dirección web en pantalla, entera: hasta el primer espacio.
const ADDRESS = /(?:[a-z][a-z0-9+.-]*:\/\/|www\.)\S+/gi;
// Elementos en línea: no cortan la tira de texto, que en pantalla sigue siendo una
// (`https://<b>loinc.org</b>`). Cualquier otra etiqueta, `<br>` incluido, sí.
const INLINE = new Set([
  "a", "abbr", "b", "bdi", "bdo", "cite", "code", "data", "dfn", "em", "i", "kbd", "mark", "q", "s",
  "samp", "small", "span", "strong", "sub", "sup", "time", "u", "var",
]);
// Etiquetas sin cierre en HTML; React las pinta con `/>`, pero un `<br>` suelto tampoco abre nada.
const VOID = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"]);
const TOKEN = /<!--[\s\S]*?-->|<(\/?)([a-zA-Z][\w:-]*)((?:"[^"]*"|'[^']*'|[^'">])*)>|([^<]+)/g;
const CLASS = /\sclass=(?:"([^"]*)"|'([^']*)')/;

interface Open {
  tag: string;
  /** El `.num` más cercano, este o uno de fuera: `null` si no hay; si lo hay, si se parte. */
  num: { wraps: boolean } | null;
}

export interface AddressesInMarkup {
  /** Cuántos textos en monoespaciada (`.num`) llevan una dirección: que la prueba no mire nada. */
  inNum: number;
  /** Las direcciones que no se parten: su `.num` más cercano no lleva `url` (ni `wrap`). Tal como salen pintadas. */
  unwrapped: string[];
}

export function addressesIn(markup: string): AddressesInMarkup {
  const stack: Open[] = [];
  const result: AddressesInMarkup = { inNum: 0, unwrapped: [] };
  // La tira de texto que en pantalla va seguida: los trozos que React separa con `<!-- -->`
  // (`{scheme}://{host}`) y los de elementos en línea. Cada trozo recuerda su `.num` más cercano;
  // una dirección cuenta si alguno de los trozos que ocupa está en `.num`, y no se parte si alguno
  // de ellos está en un `.num` que no se parte.
  let pieces: Array<{ text: string; num: Open["num"] }> = [];
  const flush = () => {
    const text = pieces.map((piece) => piece.text).join("");
    for (const found of text.matchAll(ADDRESS)) {
      const from = found.index;
      const to = from + found[0].length;
      let offset = 0;
      const covered: Array<Open["num"]> = [];
      for (const piece of pieces) {
        const end = offset + piece.text.length;
        if (end > from && offset < to) covered.push(piece.num);
        offset = end;
      }
      const nums = covered.filter((num) => num !== null);
      if (nums.length === 0) continue;
      result.inNum += 1;
      if (nums.some((num) => !num.wraps)) result.unwrapped.push(found[0]);
    }
    pieces = [];
  };
  for (const [token, closing, tag, attributes = "", piece] of markup.matchAll(TOKEN)) {
    if (piece !== undefined) {
      pieces.push({ text: piece, num: stack.at(-1)?.num ?? null });
      continue;
    }
    if (tag === undefined) continue; // comentario: no corta el texto
    const name = tag.toLowerCase();
    if (!INLINE.has(name)) flush();
    if (closing === "/") {
      // Se cierra la última abierta con ese nombre (y lo que quedara abierto dentro).
      const at = stack.map((open) => open.tag).lastIndexOf(name);
      if (at >= 0) stack.length = at;
      continue;
    }
    if (VOID.has(name) || token.endsWith("/>")) continue;
    const match = CLASS.exec(attributes);
    const names = (match?.[1] ?? match?.[2] ?? "").split(/\s+/);
    // `.num.url` (`white-space: normal`) y `.num.wrap` (`pre-wrap`) se parten en cualquier punto.
    const own = names.includes("num") ? { wraps: names.includes("url") || names.includes("wrap") } : null;
    stack.push({ tag: name, num: own ?? stack.at(-1)?.num ?? null });
  }
  flush();
  return result;
}
