/**
 * Lo que la persona elige de la pantalla y la sección que tenía abierta, guardado en el equipo.
 *
 * Por qué existe: las notas de voz del equipo (2026-11) piden una consola tipo tableta para un
 * habitáculo en microgravedad, donde no hay arriba ni abajo, puede haber daño visual (SANS,
 * deslumbramiento) o cansancio, y a veces hay otra persona delante. Cinco modos de pantalla
 * responden a eso: baja visión, alto contraste, esencial, orientación y privacidad (§5.40 de
 * `compliance/hmi-state-of-the-art.md`), y la voz propia se guarda con ellos (`lib/speech.ts`,
 * para quien no ve la pantalla o no la está mirando). Son preferencias de presentación de este equipo, no
 * decisiones clínicas: no pasan por el registro firmado, no cambian nada del backend y se guardan
 * en `localStorage`. Si el almacén no existe o falla (modo privado del navegador, pruebas), la
 * consola funciona igual con los valores de partida.
 *
 * Aquí solo va lo que se puede probar sin navegador: leer y escribir con tolerancia, resolver qué
 * sección se abre y a dónde lleva cada tecla del carril.
 */

/** Giro de toda la vista, en grados en el sentido de las agujas del reloj. */
export type Rotation = 0 | 90 | 180 | 270;

export const ROTATIONS: readonly Rotation[] = [0, 90, 180, 270];

export interface DisplayModes {
  /** Texto, mandos y trazos más grandes; el texto secundario pasa al color del texto. */
  lowVision: boolean;
  /**
   * Alto contraste, para el deslumbramiento o la luz intensa: la variante `highContrast` de
   * `lib/palette.ts` (7:1 o más en todo texto, los mismos significados de la tabla F.5-1), bordes y
   * foco más gruesos. Se suma a la baja visión. Lo guardado antes de que existiera no lo trae: apagado.
   */
  highContrast: boolean;
  /** Solo las secciones imprescindibles para actuar. */
  essential: boolean;
  /** Tapa nombres, cifras personales y notas; deja a la vista alertas y estado general. */
  privacy: boolean;
  /**
   * Voz propia (`lib/speech.ts`): con ella, cada alerta nueva se lee una vez en voz alta. «Leer en
   * voz alta» funciona con ella o sin ella. Lo guardado antes de que existiera no la trae: apagada.
   */
  voice: boolean;
  /**
   * EMMA toma la iniciativa (`assistant/proactive.ts`): saluda al abrir, lee el estado y avisa sin
   * que se lo pidan de alertas nuevas, medidas que se atrasan, el nivel de misión y el evento solar.
   * Con él, las alertas nuevas las dice este modo y no el de voz (para no decirlas dos veces). Lo
   * guardado antes de que existiera no lo trae: apagado.
   */
  proactive: boolean;
  rotation: Rotation;
  /**
   * La vista gira sola con el giroscopio, desde el «esto es arriba» de la persona
   * (`lib/orientation.ts`). `rotation` sigue guardando el último giro: sin sensor, o al quitar
   * este modo, la vista se queda donde estaba y los botones de giro manual son el respaldo.
   */
  followSensor: boolean;
  /**
   * La vista gira sola siguiendo la cara de quien mira, con la cámara frontal (demostración,
   * `lib/faceOrientation.ts`). Con `followSensor` también encendido, manda la cara mientras la ve
   * (`faceHoldsView`). Nunca a la vez que `privacy`: poner la privacidad lo apaga.
   */
  followFace: boolean;
  /**
   * Manos libres: la consola oye la palabra «EMMA» y graba la frase que sigue para el asistente
   * (`assistant/wake/`). Nunca a la vez que `privacy`, y cada sesión empieza con él apagado.
   */
  wakeWord: boolean;
  /**
   * Con `followFace`, si la cámara ve otra cara un momento seguido, EMMA pone la privacidad sola y
   * lo dice; sin este modo, solo la propone (`lib/faceCompany.ts`, demostración). Solo cuenta
   * caras. No enciende la cámara: sin `followFace` no hace nada. Cada sesión empieza con él
   * apagado, como la cámara. Lo guardado antes de que existiera no lo trae: apagado.
   */
  autoPrivacy: boolean;
}

export const DEFAULT_MODES: DisplayModes = {
  lowVision: false,
  essential: false,
  privacy: false,
  voice: false,
  proactive: false,
  rotation: 0,
  followSensor: false,
  followFace: false,
  wakeWord: false,
  highContrast: false,
  autoPrivacy: false,
};

export const DISPLAY_KEY = "emma.display";

/** Lo mínimo de `Storage` que se usa: así las pruebas pasan uno de mentira. */
export interface PreferenceStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** El `localStorage` del navegador, o nada si no existe o no deja leerse. */
export function browserStore(): PreferenceStore | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** Lee lo guardado; lo que falte o no se entienda queda con su valor de partida. */
export function parseModes(raw: string | null): DisplayModes {
  if (raw === null) return DEFAULT_MODES;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return DEFAULT_MODES;
  }
  if (typeof value !== "object" || value === null) return DEFAULT_MODES;
  const given = value as Record<string, unknown>;
  const flag = (key: keyof Omit<DisplayModes, "rotation">) =>
    typeof given[key] === "boolean" ? (given[key] as boolean) : DEFAULT_MODES[key];
  const rotation = ROTATIONS.find((item) => item === given.rotation) ?? DEFAULT_MODES.rotation;
  // Un valor guardado antes de existir `followSensor` o `followFace` no lo trae: queda apagado.
  const privacy = flag("privacy");
  return {
    lowVision: flag("lowVision"),
    essential: flag("essential"),
    privacy,
    voice: flag("voice"),
    proactive: flag("proactive"),
    rotation,
    followSensor: flag("followSensor"),
    // Con la privacidad puesta la cámara no se enciende, aunque lo guardado diga otra cosa.
    followFace: flag("followFace") && !privacy,
    // Lo mismo con el micrófono. Un valor de antes de existir el modo no lo trae: apagado.
    wakeWord: flag("wakeWord") && !privacy,
    highContrast: flag("highContrast"),
    autoPrivacy: flag("autoPrivacy"),
  };
}

export function readModes(store: PreferenceStore | null): DisplayModes {
  try {
    return parseModes(store?.getItem(DISPLAY_KEY) ?? null);
  } catch {
    return DEFAULT_MODES;
  }
}

export function writeModes(store: PreferenceStore | null, modes: DisplayModes): void {
  try {
    store?.setItem(DISPLAY_KEY, JSON.stringify(modes));
  } catch {
    // Sin almacén la preferencia dura lo que la sesión: no es un fallo de la consola.
  }
}

/**
 * Si el plegable «Pantalla» del pie del carril está abierto. Va en su propia clave, no en
 * `emma.display`: es dónde está un mando, no un modo, y así un valor viejo de los modos se sigue
 * leyendo igual. Lo de partida, cerrado: el carril es de las pestañas.
 */
export const DISPLAY_OPEN_KEY = "emma.display.open";

export function readDisplayOpen(store: PreferenceStore | null): boolean {
  try {
    return store?.getItem(DISPLAY_OPEN_KEY) === "true";
  } catch {
    return false;
  }
}

export function writeDisplayOpen(store: PreferenceStore | null, open: boolean): void {
  try {
    store?.setItem(DISPLAY_OPEN_KEY, open ? "true" : "false");
  } catch {
    // Como los modos: sin almacén dura lo que la sesión.
  }
}

/**
 * Si «Inicio» enseña lo secundario, lo que va por debajo de «Peligros RIDGE: acceso rápido» (rutas
 * espaciales y el pie). Decisión del usuario (2026-11-14): un botón separa lo principal, de RIDGE
 * para arriba, de lo secundario, de RIDGE para abajo. Lo de partida, plegado (decisión del usuario,
 * 2026-11-14: «que aparezca oculto»); el modo esencial no se pliega: queda
 * abajo y a lo ancho (`HomeEssential`).
 */
export const HOME_SECONDARY_KEY = "emma.home.secondary";

export function readHomeSecondary(store: PreferenceStore | null): boolean {
  try {
    return store?.getItem(HOME_SECONDARY_KEY) === "true";
  } catch {
    return false;
  }
}

/**
 * Los bloques plegables de la pestaña «Distancia y nodos» (lote «reservas», 2026-11-14): distancia y
 * reservas (el diagnóstico no se pliega). Por equipo, como lo secundario de «Inicio». Abiertos por defecto;
 * las reservas se pueden plegar («el que se despliega»), pero vienen abiertas como en la maqueta.
 */
export type HomeBlock = "distance" | "reserves";

// Las reservas vienen desplegadas, como en la maqueta de la ISS (decisión del usuario, 2026-11-15).
const HOME_BLOCK_DEFAULT: Record<HomeBlock, boolean> = { distance: true, reserves: true };

export function readHomeBlock(store: PreferenceStore | null, block: HomeBlock): boolean {
  try {
    const stored = store?.getItem(`emma.home.${block}`);
    return stored === "true" ? true : stored === "false" ? false : HOME_BLOCK_DEFAULT[block];
  } catch {
    return HOME_BLOCK_DEFAULT[block];
  }
}

export function writeHomeBlock(store: PreferenceStore | null, block: HomeBlock, open: boolean): void {
  try {
    store?.setItem(`emma.home.${block}`, open ? "true" : "false");
  } catch {
    // Sin almacén dura lo que la sesión.
  }
}

export function writeHomeSecondary(store: PreferenceStore | null, open: boolean): void {
  try {
    store?.setItem(HOME_SECONDARY_KEY, open ? "true" : "false");
  } catch {
    // Como los modos: sin almacén dura lo que la sesión.
  }
}

/** Dónde va el carril: al lado del contenido o encima, como una barra. */
export type RailPlacement = "side" | "top";

/** La ampliación de baja visión (`styles.css`, `zoom: 1.25`): la maqueta ve la ventana así de menor. */
export const LOW_VISION_ZOOM = 1.25;

/**
 * Dónde va el carril con esta ventana. Una tableta en vertical (768 × 1024) o una pantalla
 * estrecha no dejan sitio para una columna de pestañas al lado: el carril pasa arriba, con las
 * pestañas en filas, todas a la vista y sin desplazar nada de lado. Cuenta la vista como la ve
 * quien mira: girada 90 o 270°, el ancho de la vista es el alto de la ventana; con baja visión, todo
 * se mide ampliado.
 */
export function railPlacement(width: number, height: number, rotation: Rotation, lowVision: boolean): RailPlacement {
  const sideways = rotation === 90 || rotation === 270;
  const zoom = lowVision ? LOW_VISION_ZOOM : 1;
  const viewWidth = (sideways ? height : width) / zoom;
  const viewHeight = (sideways ? width : height) / zoom;
  return viewWidth <= 760 || (viewWidth <= 1024 && viewWidth < viewHeight) ? "top" : "side";
}

/** Clave de la sección abierta de una consola. */
export function sectionKey(consoleId: string): string {
  return `emma.section.${consoleId}`;
}

export function readSection(store: PreferenceStore | null, consoleId: string): string | null {
  try {
    return store?.getItem(sectionKey(consoleId)) ?? null;
  } catch {
    return null;
  }
}

export function writeSection(store: PreferenceStore | null, consoleId: string, key: string): void {
  try {
    store?.setItem(sectionKey(consoleId), key);
  } catch {
    // Como arriba.
  }
}

/**
 * La sección que se abre: la guardada si sigue a la vista, y si no la primera. Una sección que ya
 * no existe (otro backend sin ese perfil) o que el modo esencial oculta no deja la consola vacía.
 */
export function resolveSection(visible: readonly string[], stored: string | null): string | null {
  if (stored !== null && visible.includes(stored)) return stored;
  return visible[0] ?? null;
}

/**
 * A qué pestaña lleva una tecla en el carril vertical (patrón de pestañas de WAI-ARIA): abajo y
 * derecha, la siguiente; arriba e izquierda, la anterior, dando la vuelta; Inicio y Fin, la primera
 * y la última. Cualquier otra tecla no mueve nada (`null`). La vista girada no invierte las
 * teclas: quien la mira girada tiene su abajo donde el documento tiene el suyo.
 */
export function nextTabIndex(count: number, current: number, key: string): number | null {
  if (count <= 0) return null;
  switch (key) {
    case "ArrowDown":
    case "ArrowRight":
      return (current + 1) % count;
    case "ArrowUp":
    case "ArrowLeft":
      return (current - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}
