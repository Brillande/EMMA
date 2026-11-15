/**
 * Paleta de EMMA: la unica fuente de verdad del color.
 *
 * Por que existe como codigo y no como un CSS a mano: NASA-STD-3001 Vol 2, F.5.10,
 * exige un contraste de al menos 6:1 entre texto y fondo, y asigna significados
 * fijos a cada color (tabla F.5-1). Si los colores vivieran solo en una hoja de
 * estilos, nada impediria que un retoque bajara el contraste de 6:1 o que alguien
 * usara el cian para decorar. Aqui los tokens se aplican al CSS desde este mismo
 * objeto, y `palette.test.ts` comprueba cada pareja texto/fondo que se usa.
 *
 * Significados obligatorios (tabla F.5-1, literal):
 *   rojo     "Highest alert level, emergency, warning, failed"
 *   amarillo "Second highest level, caution, off-nominal, [...] attention required"
 *   azul     "Advisory"
 *   gris     "Unavailable, unselectable"
 *   cian     "Missing or stale data"
 * Recomendados (tabla F.5-2):
 *   magenta      "Electronic Procedures and system directed" -> recomendaciones
 *   verde oscuro "Commandable element background"            -> fondo de botones
 *   verde vivo   "Navigation and Cursor Outlines"            -> foco
 */

export const palette = {
  // Fondos. Oscuros: en cabina se trabaja con poca luz.
  bg: "#0A0D12",
  surface: "#121821",
  raised: "#1A2230",
  command: "#0F3A24",

  // Texto sin significado de alerta. El secundario NO es el gris de la tabla
  // F.5-1: el gris esta reservado para "no disponible".
  text: "#EEF2F6",
  textSecondary: "#B9C4D0",

  // Significados de la tabla F.5-1.
  red: "#FF8A8A",
  yellow: "#FFD447",
  blue: "#8DBDFF",
  gray: "#A3ACB5",
  cyan: "#3EE6E6",

  // Significados de la tabla F.5-2.
  magenta: "#F59CF5",
  green: "#6BF09A",

  // Bordes y separadores: no son texto, no entran en la regla de 6:1.
  line: "#2A3446",
} as const;

export type Token = keyof typeof palette;

/** Una paleta completa: un valor para cada token, ni uno más ni uno menos. */
export type PaletteValues = { readonly [K in Token]: string };

/**
 * Variante de alto contraste, para el deslumbramiento y la luz intensa (modo «Alto contraste»,
 * `components/displayModes.ts`; §5.40 de `compliance/hmi-state-of-the-art.md`).
 *
 * Por qué existe: con luz fuerte sobre la pantalla, el reflejo suma la misma luminancia al fondo y
 * a la letra, y la razón de contraste cae (con un reflejo del 5 % de la luminancia del blanco, el
 * 17:1 del texto normal baja a unos 9:1, y el amarillo sobre `raised` de 11:1 a menos de 7:1). La
 * única palanca de la interfaz es partir de más: fondo negro, texto blanco y los colores de las
 * tablas F.5-1 y F.5-2 más claros (salvo el gris), cada uno con su mismo tono (lo vigila `palette.test.ts`: el mismo significado, el
 * mismo matiz). Todo texto queda en 7:1 o más (WCAG 1.4.6, «contraste mejorado»), el principal en
 * 12:1 o más, y los bordes pasan de 3:1 (WCAG 1.4.11, componentes no textuales), cosa que la
 * paleta normal no pide a `line`.
 *
 * Por qué oscura y no clara: en fondo claro, el amarillo y el cian no llegan a 7:1 sin dejar de
 * parecer amarillo y cian (un amarillo de 7:1 sobre blanco es un ocre, `#6B5300`; un cian `#006B6B`
 * se queda en 6,3:1), y la tabla F.5-1 dejaría de leerse por el color. El motivo completo, y lo que
 * se deja (la ventaja de la polaridad positiva con mucha luminancia), en el documento.
 */
export const highContrast = {
  bg: "#000000",
  surface: "#080A0E",
  raised: "#10141B",
  command: "#003A1C",

  text: "#FFFFFF",
  textSecondary: "#E3E9EF",

  red: "#FF8A94",
  yellow: "#FFE15C",
  blue: "#9CC4FF",
  // El gris de siempre: «no disponible» no tiene por qué destacar, sobre el negro ya pasa de 7:1, y
  // uno más claro se confundiría con el hueso y el cristalino de los lienzos (`anatomy`).
  gray: "#A3ACB5",
  cyan: "#5CF5F5",

  magenta: "#FFB3FF",
  green: "#7CFFA8",

  // Aquí sí cuenta: un borde de alto contraste se tiene que ver (WCAG 1.4.11, 3:1).
  line: "#7D8BA0",
} as const satisfies PaletteValues;

/** Las paletas que se pueden aplicar: la de siempre y la de alto contraste. */
export const PALETTES = { base: palette, highContrast } as const satisfies Record<string, PaletteValues>;

export type PaletteVariant = keyof typeof PALETTES;

/** WCAG 1.4.6 (AAA): 7:1 para el texto. Es el mínimo de la variante de alto contraste. */
export const HIGH_CONTRAST_MIN = 7;

/** El texto principal de la variante de alto contraste, por encima del 10:1 preferido de F.5.10. */
export const HIGH_CONTRAST_TEXT_MIN = 12;

/** WCAG 1.4.11: 3:1 para bordes y componentes no textuales. Solo se exige en alto contraste. */
export const MIN_NON_TEXT_CONTRAST = 3;

export const BACKGROUNDS = ["bg", "surface", "raised"] as const satisfies readonly Token[];

/** Colores que pueden ir como texto sobre cualquiera de los fondos generales. */
export const TEXT_TOKENS = [
  "text",
  "textSecondary",
  "red",
  "yellow",
  "blue",
  "gray",
  "cyan",
  "magenta",
  "green",
] as const satisfies readonly Token[];

/** Lo unico que se escribe sobre el fondo verde de un elemento de mando. */
export const COMMAND_TEXT_TOKENS = ["text", "yellow", "green"] as const satisfies readonly Token[];

// F.5.10: "Contrast between characters and background must be 6:1 or greater".
export const MIN_CONTRAST = 6;

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const n = Number.parseInt(hex.slice(1), 16);
  return 0.2126 * channel(n >> 16) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}

/** Razon de contraste de WCAG 2.x, la que cita la nota de F.5.10 (webaim.org). */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/** Nombre de la variable CSS de un token: `textSecondary` -> `--c-text-secondary`. */
export function cssVar(token: Token): string {
  return `--c-${token.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;
}

/**
 * Vuelca una paleta como variables CSS: `--c-red`, `--c-bg`... Sin variante, la de siempre. Cambiar
 * de variante es volver a llamarla: los mismos nombres, otros valores, y la hoja de estilos no cambia.
 */
export function applyPalette(root: HTMLElement, variant: PaletteVariant = "base"): void {
  for (const [name, value] of Object.entries(PALETTES[variant])) {
    root.style.setProperty(cssVar(name as Token), value);
  }
}

/**
 * Colores de ANATOMIA, solo para el contenido de los lienzos 3D (visor de volumenes, atlas,
 * mapa de dolor). No son señales de interfaz: son la imagen médica, como el gris de un TAC.
 *
 * Por que existen: el visor portado de Polaris pintaba hígado, porta, vasos y cava en los grises
 * de la paleta de interfaz, y la escena quedó gris sobre gris, sin forma. Polaris los pinta con
 * tonos anatómicos (hígado crema translúcido, porta azul, vasos azul grisáceo). Aquí se recuperan,
 * con una condición que vigila `palette.test.ts`: ninguno puede parecerse a un color con
 * significado de la tabla F.5-1 o F.5-2, para que un vaso nunca se lea como una alerta. Las
 * lesiones candidatas y la seleccionada siguen con amarillo y verde de la paleta: esas sí son
 * señales.
 */
export const anatomy = {
  // Fondo de los lienzos 3D: el berenjena oscuro de Polaris, que deja ver los translúcidos.
  canvas: "#1C1126",
  organ: "#E6DCCD", // hígado, globos oculares, silueta: crema, translúcido
  portal: "#6E96C8", // porta y esplénica
  vessels: "#6A7FA8", // vasos hepáticos
  cava: "#4A5C94", // vena cava inferior
  gallbladder: "#6F9A3A", // vesícula
  lens: "#D2DCE6", // cristalino
  nerve: "#E0C08A", // nervio óptico
  bone: "#D8CFBE", // esqueleto
  muscle: "#B8645A", // corazón, músculo
  lung: "#B98272", // pulmones
  kidney: "#9A5040", // riñones, bazo
  brain: "#E8C4AA", // encéfalo
  // El render de «ilustración médica» de Polaris (`tools/visor3d_web/render.js`), el del hígado de la
  // maqueta de la ISS: la vista previa de `volumes/SegmentationPreview.tsx` (2026-11-14).
  liverRender: "#9A3F2C", // hígado: rojo hepático, translúcido por Fresnel
  // El brillo del hígado: en Polaris, #E39A86; se parecía al rojo de alarma (distancia 32) y aquí
  // se oscurece hasta separarse (AGPL §5a, anotado en la vista previa).
  liverSheen: "#C77A68",
  portalRender: "#5236B0", // vena porta
  vesselsRender: "#2D63D6", // vasos hepáticos
  cavaRender: "#1F45A8", // vena cava inferior
} as const;

export type AnatomyToken = keyof typeof anatomy;

/** Distancia euclídea en RGB entre dos colores `#rrggbb`. */
export function rgbDistance(a: string, b: string): number {
  const pa = Number.parseInt(a.slice(1), 16);
  const pb = Number.parseInt(b.slice(1), 16);
  const d = [16, 8, 0].map((shift) => ((pa >> shift) & 255) - ((pb >> shift) & 255));
  return Math.hypot(...d);
}

/** Colores con significado que ningún color anatómico puede imitar. */
export const SIGNAL_TOKENS = [
  "red", "yellow", "blue", "gray", "cyan", "magenta", "green",
] as const satisfies readonly Token[];

/** Umbral de parecido: por debajo, un color anatómico se confundiría con una señal. */
export const MIN_SIGNAL_DISTANCE = 60;
