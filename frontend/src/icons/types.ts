/**
 * Pictogramas de EMMA: la forma que acompaña a cada palabra.
 *
 * Por qué existen como SVG propio y no como caracteres: F.5.10 e de NASA-STD-3001 Vol 2 exige
 * una señal además del color para la información crítica, y la interfaz la daba con glifos de
 * texto (○ ◇ △ ■, ● ◐ ▷, ◌, ⊘ ✕). IBM Plex (@fontsource, subconjunto latino) no cubre los
 * bloques U+22xx, U+25xx ni U+27xx, así que cada sistema operativo dibujaba esos caracteres con
 * otra fuente de reserva: distinto peso, distinta línea base y, en algún caso, distinto dibujo.
 * La señal que no debía depender del color dependía del sistema operativo.
 *
 * Aquí cada pictograma es geometría: trazo de 2 unidades sobre una rejilla de 24×24, en
 * `currentColor`, pensado para leerse a 12 px. Solo seis primitivas, para que un pictograma se
 * pueda comprobar por prueba (`pictograms.test.ts`): números finitos, rutas con la gramática
 * mínima de `d`, sin colores propios, sin estilos. El color sigue siendo de la paleta y lo pone
 * la clase `c-<token>` del elemento que lo contiene; el pictograma nunca lo elige.
 *
 * El nombre describe el dibujo («shape-triangle»), nunca el significado («precaución»): el
 * significado lo da la palabra que va al lado y la tabla de `compliance/hmi-state-of-the-art.md`
 * §5.32. Un pictograma solo, sin palabra, no existe en EMMA.
 */

export type PictogramElement =
  | { readonly kind: "path"; readonly d: string; readonly fill?: true; readonly dashed?: true }
  | {
      readonly kind: "circle";
      readonly cx: number;
      readonly cy: number;
      readonly r: number;
      readonly fill?: true;
      readonly dashed?: true;
    }
  | {
      readonly kind: "rect";
      readonly x: number;
      readonly y: number;
      readonly width: number;
      readonly height: number;
      readonly fill?: true;
    }
  | {
      readonly kind: "line";
      readonly x1: number;
      readonly y1: number;
      readonly x2: number;
      readonly y2: number;
    }
  | { readonly kind: "polygon"; readonly points: string; readonly fill?: true }
  | { readonly kind: "polyline"; readonly points: string };

export interface PictogramDef {
  readonly elements: readonly PictogramElement[];
  /** Grosor del trazo si no es el de 2 unidades por defecto. */
  readonly strokeWidth?: number;
}

/** Un conjunto de pictogramas de un área: nombre en kebab-case → dibujo. */
export type PictogramSet = Readonly<Record<string, PictogramDef>>;
