/**
 * El signo de cada cosa de la interfaz: qué dibujo acompaña a un título de panel, a un plegable,
 * a un mando o a una cabecera de tabla.
 *
 * Por qué existe: la segunda pasada pictográfica (2026-10-21, «la interfaz vistosa») decidió que
 * el pictograma acompaña a cada título, plegable, mando y cabecera, no solo a las palabras de
 * estado (`compliance/hmi-state-of-the-art.md` §5.32 c y §5.33). Once unidades de área iban a
 * ponerlos a la vez; si cada una eligiera su dibujo para «historial» o «exportar», la interfaz
 * acabaría con dos dibujos para un concepto, que es justo lo que §5.32 c prohíbe. Esta tabla es
 * el vocabulario cerrado: un concepto, un dibujo, el mismo en todo el sistema.
 *
 * Solo nombra dibujos de los conjuntos del núcleo (`shapes`, `common`, `provenance`, `domains`,
 * `indicators`, `ui`): la usa cualquier área, y `pictograms.test.ts` cuenta como uso todo nombre
 * entrecomillado, así que un dibujo de área aquí sería un dibujo de área usado desde `lib/`.
 *
 * Dos conceptos pueden compartir dibujo cuando son el mismo objeto visto desde dos sitios
 * («historial» y «lo anterior», «exportar» y «recibido»), y entonces se declaran juntos en
 * `UI_SYNONYMS`: la prueba exige que todo dibujo compartido esté declarado ahí y que nada
 * declarado ahí deje de serlo. Lo que nunca pasa es lo contrario, un concepto con dos dibujos:
 * la clave del objeto es única.
 *
 * `inferred` y `predictions` usan a propósito los dibujos de procedencia (`lib/provenance.ts`:
 * medio punto de lo inferido, triángulo de reproducir de lo predicho): el panel de inferencias y
 * el de predicciones hablan de esa procedencia, y otro dibujo para lo mismo sería el segundo
 * dibujo de un concepto.
 *
 * El concepto es el nombre en el código (inglés, camelCase); la palabra que se lee la sigue
 * escribiendo el panel o la da el backend, y el pictograma nunca va sin ella (§5.32 a).
 */

import type { PictogramName } from "../icons/registry";

export const UI_PICTOGRAMS = {
  // --- Títulos de panel ------------------------------------------------------------------------
  alerts: "bell",
  recommendations: "signpost",
  domains: "grid-four",
  monitoring: "lighthouse",
  basis: "pillars",
  baseline: "pillars",
  nextDays: "calendar",
  routines: "arrows-cycle",
  waiting: "hourglass",
  inferred: "dot-half",
  predictions: "play",
  // Lo medido frente a lo proyectado o al rango previo (columnas de Tierra): el disco lleno de
  // «medido» de la procedencia, como `inferred` y `predictions` (§5.33.12). Hasta entonces esas
  // columnas llevaban la regla de `measure`, la misma de «Indicador» en la columna de al lado.
  measured: "dot-filled",
  dataQuality: "list-check",
  acquisitionQuality: "list-check",
  devices: "sensor-arcs",
  body: "figure-dot",
  habitat: "house",
  systems: "gear",
  comparison: "bars-two",
  compare: "bars-two",
  followUp: "magnifier",
  resources: "cube",
  evidence: "sheet-lines",
  received: "tray-arrow-down",
  export: "tray-arrow-down",
  // «Modelos de IA» (`components/ModelsPack.tsx`): el paquete de modelos que se baja a este equipo.
  modelsPack: "tray-arrow-down",
  trends: "chart-line",
  change: "chart-line",
  signedLedger: "lock",
  docs: "book-open",
  sourceText: "book-open",
  source: "book-open",
  forecastCheck: "clock-rewind",
  history: "clock-rewind",
  previous: "clock-rewind",
  nasaFramework: "sheet-circle",
  measurementCost: "coins",
  recovery: "sunrise",
  risks: "list-lines",
  diary: "notebook",
  notes: "pen",
  descriptive: "ruler",
  indicator: "ruler",
  measure: "ruler",
  limits: "bar-capped",
  range: "bar-capped",
  pvt: "stopwatch",
  // El panel de radiación habla de dosis (la cifra acumulada, el dosímetro): lleva el trébol de la
  // familia de dosis, el mismo de `DoseMeter`. El dominio de riesgo de radiación es otro concepto
  // y conserva su dibujo (`domain-radiation`, el trébol en círculo, vía `<DomainName>`).
  radiation: "trefoil",
  pain: "bolt",
  about: "circle-i",
  howToRead: "circle-i",
  identity: "id-card",
  // La biblioteca entera de contramedidas (`advisor/LibraryPanel.tsx`, §5.34.1): la tirita, la
  // misma que el plegable de las ambientales y el hecho «contramedida» de la crónica.
  countermeasureLibrary: "bandage",
  // Las cinco preguntas de los gemelos (`dashboard/TwinQuestions.tsx`, §5.35.1): las capas de la
  // tabla de la base de conocimiento §10, apiladas.
  twinQuestions: "layers-stack",

  // --- Plegables -------------------------------------------------------------------------------
  detail: "text-lines",
  declare: "pen",
  searchedNotFound: "magnifier",
  divergences: "not-equal",
  ratings: "stairs",
  whyEmma: "pencil",
  objections: "bubble-lines",
  reason: "bubble-lines",
  // Las notas de Tierra a bordo (§5.38.1): lo que alguien en Tierra dice a la tripulación.
  groundNotes: "bubble-lines",
  markedBones: "domain-bone",
  withoutReading: "ring-dotted",
  environmentalCountermeasures: "bandage",
  byIndicator: "table-grid",
  // Los pasos de un flujo: los de una hipótesis (hábitat) y los de una alerta (§5.34.6).
  flowSteps: "squares-arrow",

  // --- Mandos ----------------------------------------------------------------------------------
  acknowledge: "pen",
  register: "pen",
  note: "pen",
  suppress: "bell-slash",
  inhibit: "bell-box",
  inRepair: "wrench",
  resolved: "check",
  confirm: "check",
  adopt: "check",
  closeFollowUp: "check",
  accept: "check",
  confirmChange: "check",
  cancel: "cross",
  abandon: "cross",
  decline: "slash-circle",
  reject: "slash-circle",
  noPain: "slash-circle",
  // Descartar una alerta (§5.37.6): un «no» firmado, como no adoptar una contramedida.
  dismiss: "slash-circle",
  enable: "bell",
  bind: "chain-links",
  unbind: "chain-broken",
  add: "plus",
  removeZone: "eraser",
  // Quitar una fila de una lista que aún no se ha firmado (una misión del historial, §5.35.19).
  removeRow: "eraser",
  startTest: "stopwatch",
  cine: "film-strip",
  undo: "arrow-u-turn",
  segment: "chip",
  search: "magnifier",
  reread: "refresh",
  upload: "arrow-up-tray",
  changeScenario: "wave-zigzag",
  // Alternar entre dos vistas de lo mismo (cortes y superficies, silueta y esqueleto).
  switchView: "arrows-swap",
  // La opción elegida de un selector, y la fase en curso (`components/Chosen.tsx`): el anillo con
  // punto de §5.32.3, que hasta la limpieza (§5.33.12) se escribía a mano en ocho sitios.
  chosen: "ring-dot",

  // --- Cabeceras de tabla y rótulos ------------------------------------------------------------
  value: "hash",
  time: "clock",
  date: "calendar",
  provenance: "stamp",
  person: "person",
  state: "toggle",
  type: "tag",
  confidence: "percent",
  during: "stopwatch",
  document: "sheet-lines",
  zone: "pin",
  protocol: "clipboard",
  analyte: "vial",
  // El retardo con Tierra (tiempo de luz) y el día de misión: rótulos de la franja y del perfil,
  // con los dibujos que ya tenían en la misión y la crónica.
  lightTime: "signal-arcs",
  missionDay: "calendar-day",

  // --- Carril de secciones y modos de pantalla (§5.40) -----------------------------------------
  // Los cinco peligros RIDGE: la pestaña inicial y sus tarjetas.
  hazards: "dots-pentagon",
  // Modo baja visión, modo esencial, girar la pantalla, el borde de arriba y la privacidad.
  lowVision: "letters-two-sizes",
  // Alto contraste (deslumbramiento): un cuadrado partido en diagonal, una mitad llena y otra vacía.
  highContrast: "square-split-diagonal",
  essential: "lines-narrowing",
  orientation: "screen-rotate",
  screenTop: "chevron-bar-up",
  privacy: "eye-slash",
  // El plegable «Pantalla» del pie del carril, que guarda los mandos de los modos: el interruptor.
  displayModes: "toggle",
  // Girar siguiendo el giroscopio de la tableta: el sensor del equipo, el dibujo de los equipos.
  followSensor: "sensor-arcs",
  // La voz propia (`lib/speech.ts`): el modo voz y «Leer en voz alta» son el mismo objeto, el
  // altavoz con ondas; tachado para parar, con la flecha que vuelve para repetir (`common`).
  voice: "speaker-waves",
  stopVoice: "speaker-slash",
  repeatVoice: "speaker-repeat",
  // Girar siguiendo la cara de quien mira (demostración, `lib/faceOrientation.ts`), y el aviso
  // permanente de que la cámara está encendida mientras lo hace.
  followFace: "head-eye-line",
  cameraOn: "webcam",
  // El asistente (`assistant/`): el micrófono es el mismo objeto en «Hablar con EMMA» y en los
  // avisos permanentes de «Micrófono abierto» y «Micrófono escuchando»; la conversación, el
  // bocadillo de lo que alguien dice.
  microphone: "microphone",
  assistant: "bubble-lines",
  // Escuchar la palabra «EMMA» (`assistant/wake/`): el micrófono con ondas a los lados, que oye
  // sin que nadie pulse.
  wakeWord: "microphone-arcs",
} as const satisfies Readonly<Record<string, PictogramName>>;

/** Un concepto de la interfaz con signo propio: la clave de `UI_PICTOGRAMS`. */
export type UiConcept = keyof typeof UI_PICTOGRAMS;

/**
 * Los conceptos que comparten dibujo, cada grupo con su motivo: son el mismo objeto visto desde
 * dos sitios. Un dibujo compartido sin declarar aquí es un error (`uiMarks.test.ts`).
 */
export const UI_SYNONYMS: readonly { readonly concepts: readonly UiConcept[]; readonly why: string }[] = [
  { concepts: ["devices", "followSensor"], why: "un sensor del equipo" },
  { concepts: ["state", "displayModes"], why: "un interruptor: el estado de algo y los mandos que lo cambian" },
  { concepts: ["alerts", "enable"], why: "habilitar devuelve la alerta: la campana" },
  { concepts: ["basis", "baseline"], why: "la base de un cálculo es la línea base personal" },
  { concepts: ["nextDays", "date"], why: "un día del calendario" },
  { concepts: ["dataQuality", "acquisitionQuality"], why: "la calidad comprobada punto por punto" },
  { concepts: ["comparison", "compare"], why: "comparar y su resultado" },
  { concepts: ["followUp", "searchedNotFound", "search"], why: "buscar con la lupa" },
  { concepts: ["evidence", "document"], why: "una hoja escrita" },
  {
    concepts: ["received", "export", "modelsPack"],
    why: "lo que llega a la bandeja: recibido, exportado a un fichero y los modelos descargados",
  },
  { concepts: ["trends", "change"], why: "la línea de una serie en el tiempo" },
  { concepts: ["docs", "sourceText", "source"], why: "lo leído en la fuente" },
  { concepts: ["forecastCheck", "history", "previous"], why: "mirar atrás" },
  { concepts: ["notes", "declare", "acknowledge", "register", "note"], why: "escribir de puño y letra" },
  { concepts: ["descriptive", "indicator", "measure"], why: "una medida" },
  { concepts: ["limits", "range"], why: "lo acumulado frente a su tope" },
  { concepts: ["pvt", "startTest", "during"], why: "el cronómetro de la prueba" },
  { concepts: ["about", "howToRead"], why: "información sobre lo que se tiene delante" },
  { concepts: ["objections", "reason", "groundNotes", "assistant"], why: "lo que alguien dice" },
  {
    concepts: ["resolved", "confirm", "adopt", "closeFollowUp", "accept", "confirmChange"],
    why: "dar algo por bueno",
  },
  { concepts: ["cancel", "abandon"], why: "no seguir" },
  { concepts: ["removeZone", "removeRow"], why: "borrar algo de lo que se está componiendo, antes de firmarlo" },
  { concepts: ["decline", "reject", "noPain", "dismiss"], why: "no, o no hay" },
  {
    concepts: ["countermeasureLibrary", "environmentalCountermeasures"],
    why: "las contramedidas: la biblioteca entera y las ambientales, que son parte de ella",
  },
];

/** El dibujo de un concepto. */
export function uiPictogram(concept: UiConcept): PictogramName {
  return UI_PICTOGRAMS[concept];
}

/**
 * El signo de una pieza de la interfaz (`PanelTitle`, `Fold`, `Command`, `Th`, `FieldLabel`,
 * `StatTile`): un concepto de la tabla, o un pictograma directo para lo que ya tiene dibujo propio
 * (un dominio, un indicador, una procedencia). Uno de los dos, nunca ambos.
 */
export type Sign =
  | { readonly concept: UiConcept; readonly pictogram?: never }
  | { readonly pictogram: PictogramName; readonly concept?: never };

/** El dibujo de un signo. */
export function signPictogram(sign: Sign): PictogramName {
  return sign.concept !== undefined ? uiPictogram(sign.concept) : sign.pictogram;
}

/** `Omit` que reparte sobre una unión: quita las claves de cada rama. */
export type WithoutSign<T> = T extends unknown ? Omit<T, "concept" | "pictogram"> : never;

/** Las props de una pieza sin su signo: lo que queda se pasa tal cual al elemento. */
export function withoutSign<T extends Sign>(props: T): WithoutSign<T> {
  const { concept: _concept, pictogram: _pictogram, ...rest } = props;
  return rest as WithoutSign<T>;
}
