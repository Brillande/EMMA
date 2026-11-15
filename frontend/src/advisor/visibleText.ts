/**
 * Que se lee de un HTML estatico SIN abrir ningun desplegable.
 *
 * Por que existe: la tarjeta de recomendacion pliega parte de lo que ensena, y «plegado» solo es
 * aceptable si lo que hay que leer antes de decidir sigue a la vista. Eso no se comprueba mirando
 * el JSX: se pinta la tarjeta y se le quita lo que un `<details>` cerrado esconde. Solo lo usan
 * las pruebas; no entra en lo que se sirve.
 */

const INNERMOST = /<details(?:\s[^>]*)?>((?:(?!<details[\s>])[\s\S])*?)<\/details>/;
const SUMMARY = /<summary(?:\s[^>]*)?>[\s\S]*?<\/summary>/;
const INLINE = /<\/?(?:span|strong|em|b|i|a|code)(?:\s[^>]*)?>/g;

/** El HTML que queda a la vista: de cada `<details>` cerrado, solo su `<summary>`. */
export function withoutFolded(html: string): string {
  let rest = html;
  for (;;) {
    const found = INNERMOST.exec(rest);
    if (found === null) return rest;
    if (/^<details[^>]*\sopen/.test(found[0])) {
      throw new Error("un <details open> no esta plegado: esta medida no lo contempla");
    }
    const summary = SUMMARY.exec(found[1] ?? "")?.[0] ?? "";
    rest = rest.slice(0, found.index) + summary + rest.slice(found.index + found[0].length);
  }
}

/**
 * Fuera los comentarios y los pictogramas (`<svg>…</svg>`, `icons/Pictogram.tsx`): un pictograma
 * no es texto, va oculto al lector de pantalla y sus trazos no deben partir la linea de la
 * palabra a la que acompana.
 */
const clean = (html: string): string =>
  html.replace(/<!--[\s\S]*?-->/g, "").replace(/<svg[\s>][\s\S]*?<\/svg>/g, "");

/** Los nodos de texto de un HTML, sin los vacios. */
export function textNodes(html: string): string[] {
  return clean(html)
    .split(/<[^>]+>/)
    .map((piece) => piece.trim())
    .filter((piece) => piece !== "");
}

/**
 * Las lineas de texto: lo que separa un bloque o un `<br>`. Las etiquetas en linea (un `<span>`
 * de color o de glifo) no parten la linea.
 */
export function textLines(html: string): string[] {
  return clean(html)
    .replace(INLINE, "")
    .split(/<[^>]+>/)
    .map((piece) => piece.replace(/\s+/g, " ").trim())
    .filter((piece) => piece !== "");
}

/** El texto a la vista, en una sola cadena. */
export function visibleText(html: string): string {
  return textLines(withoutFolded(html)).join("\n");
}

const escapeRegExp = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * El `<svg>` de un pictograma con ese nombre, entero, como trozo de expresion regular: para
 * componer una prueba que fije donde cae el dibujo dentro de un HTML mayor.
 */
export function pictogramSvg(name: string): string {
  return `<svg\\b[^>]*data-pictogram="${name}"[^>]*>(?:(?!</svg>)[\\s\\S])*</svg>`;
}

/**
 * Un `span` con esas clases exactas, dentro el pictograma y, tras el, la palabra (literal: se
 * escapa). Para lo que lleva pictograma sin ser una marca (`.label` de la franja) o cuando la
 * prueba quiere la clase entera.
 */
export function spanWithPictogram(classes: string, pictogram: string, word: string): RegExp {
  return new RegExp(`<span class="${classes}"(?: title="[^"]*")?>${pictogramSvg(pictogram)}${escapeRegExp(word)}`);
}

/**
 * Una marca pintada (`<Mark>`): un `span` de clase `mark[ clases][ c-color]`, dentro el `svg` con
 * su `data-pictogram` y, tras el, la palabra. Es el unico sitio que sabe como se escribe, para que
 * un cambio en `Mark` se corrija en una linea y no en cada prueba. `word` se toma literal (se
 * escapa); `className` va entre `mark` y el color, como lo emite el componente.
 */
export function markedHtml(
  pictogram: string,
  word: string,
  color: string | null = null,
  className: string | null = null,
): RegExp {
  const classes = ["mark", className, color === null ? null : `c-${color}`]
    .filter((item) => item !== null)
    .join(" ");
  return spanWithPictogram(classes, pictogram, word);
}

/**
 * Una pieza con el pictograma directo dentro (`PanelTitle`, `Fold`, `Command`, `Th`,
 * `FieldLabel`): la etiqueta `tag` con sus atributos exactos (`attrs`, literal, con su espacio
 * delante: ` class="command"`), dentro el `svg` con su `data-pictogram` y, tras el, la palabra
 * (literal). Para las pruebas del mobiliario, como `markedHtml` para las marcas.
 */
export function taggedPictogram(tag: string, pictogram: string, word: string, attrs = ""): RegExp {
  return new RegExp(`<${escapeRegExp(tag)}${escapeRegExp(attrs)}>${pictogramSvg(pictogram)}${escapeRegExp(word)}`);
}

/**
 * Una cabecera pintada por `<Th>`: como `taggedPictogram("th", …)`, pero con el `span.th-sign`
 * que une el dibujo a la palabra (`components/Th.tsx` dice por qué). `word` se toma literal; para
 * fijar el final de la cabecera, `</span></th>` detrás de la palabra.
 */
export function thSign(pictogram: string, word: string, attrs = ""): RegExp {
  return new RegExp(
    `<th${escapeRegExp(attrs)}><span class="th-sign">${pictogramSvg(pictogram)}${escapeRegExp(word)}`,
  );
}
