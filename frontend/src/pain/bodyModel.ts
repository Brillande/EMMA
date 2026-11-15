/**
 * Cuerpo del mapa de dolor: una superficie lisa y continua, cortada en una pieza por zona.
 *
 * Por que no un modelo anatomico descargado: Z-Anatomy publica el codigo con licencia MIT pero
 * la malla con CC BY-SA, que obliga a compartir con la misma licencia lo que se derive.
 * BodyParts3D es CC BY 4.0 (verificado el 2026-10-01 en
 * https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html; lo usa el esqueleto de referencia
 * del modo anatomico), pero sigue siendo una malla que habria que cortar por zonas y servir como
 * fichero. Este cuerpo lo escribe el proyecto, no lleva fichero de modelo y no necesita cambiar
 * la CSP (nada de `blob:`, WebAssembly ni decodificadores).
 *
 * Por que no las formas sueltas de antes (2026-11-09): eran 28 esferas, capsulas y cajas, una por
 * zona, y el usuario lo vio feo al lado del cuerpo de «Inicio». Ahora el cuerpo son tramos
 * lisos —tronco con cuello y cabeza, brazo, pierna, pie y, sueltos, dedos y orejas— barridos a lo
 * largo de un eje con una seccion eliptica que cambia con suavidad, y cada zona es un trozo de
 * uno o varios tramos (un intervalo del eje y, en el tronco, un sector del contorno). Dos zonas
 * vecinas del mismo tramo comparten el borde punto a punto: no hay costura ni rendija, y un clic
 * en la junta no cae en dos sitios. Las proporciones salen de la silueta de «Inicio»
 * (`dashboard/referenceBody.generated.ts`, 152 x 310 px, 1,73 m de talla). Desde el lote «Inicio
 * 3D» (2026-11-10) el contorno de frente se ajusta por altura a esa silueta (hombros de 0,52 m con
 * los deltoides, cintura de 0,29, caderas de 0,34, brazos abiertos unos 20 grados, la mano a 0,35
 * m del centro y los pies separados) y el relieve vuelve a ser el de su varon atletico.
 *
 * Por que el relieve (2026-11-09, «todavia el cuerpo puede ser mas chulo»): con solo elipses el
 * cuerpo parecia un maniqui de tubos al lado del de «Inicio», que es un cuerpo atletico con la
 * musculatura a la vista. Cada tramo lleva una lista de bultos (`Bump`): campanas de Gauss en el
 * eje y en el angulo del contorno que empujan la superficie hacia fuera (musculo, hueso) o hacia
 * dentro (surco, cuenca del ojo). Como el bulto es una funcion del punto del tramo, el borde que
 * comparten dos zonas sigue siendo el mismo punto a punto. En el tronco cada bulto se aplica
 * tambien en su angulo espejo, asi que la simetria izquierda-derecha no depende de escribirlo dos
 * veces. Es un relieve orientativo para que el cuerpo se lea como cuerpo, no un atlas anatomico.
 *
 * `position` de cada zona es su centro de referencia, el que usa el backend para llevar el dolor
 * al esqueleto (`backend/app/data/anatomy/pain_points.json`, que su prueba compara con este
 * fichero). La superficie se ha dibujado alrededor de esos centros; los movio la postura en
 * reposo del brazo (Humano 2, 2026-11-09: antebrazo y mano) y la de «Inicio» (Inicio 3D,
 * 2026-11-10: brazo, codo, antebrazo, mano, pierna y pie). De las anclas del ajuste solo se movio
 * el brazo, al centro de su malla nueva; el umbral no cambia (lo fija el cuello, 0,16 m).
 *
 * Datos y geometria puros, sin three.js: asi se prueban sin navegador (`bodyModel.test.ts`).
 *
 * EJES: y hacia arriba, pies en y = 0. El cuerpo mira hacia +z, que es donde esta la camara
 * en la vista de frente. **El lado izquierdo del tripulante esta en +x**: visto de frente,
 * su izquierda cae a la derecha de la pantalla, como un paciente sentado delante. Las zonas
 * con `side` del backend son del tripulante, y la prueba comprueba que caen en su lado.
 */

export type Vec3 = readonly [number, number, number];

/** Seccion del tramo en el punto `at` de su eje: semiejes de la elipse, en metros. */
export interface Section {
  at: number;
  /** Semieje a lo ancho (x en el tronco; perpendicular al eje y de lado en brazo y pierna). */
  rx: number;
  /** Semieje de delante a atras (o, en el pie, de alto). */
  rz: number;
}

/**
 * Bulto del relieve: empuja la superficie `d` metros (negativo, hacia dentro) en el punto `at`
 * del eje y al angulo `deg` del contorno, y se apaga como una campana de Gauss de anchura `sAt`
 * (en unidades del eje; dos valores = antes y despues de `at` a lo largo del eje, que en el
 * tronco sube y en brazo, pierna y dedos baja) y `sDeg` (en grados).
 *
 * Angulos: en el tronco 0 es +x (izquierda del tripulante), 90 delante, 270 detras. En brazo y
 * pierna izquierdos 0 es el lado de dentro (hacia el cuerpo), 90 delante, 180 fuera y 270 detras.
 * En el pie 0 es dentro, 90 arriba, 180 fuera y 270 la planta.
 *
 * Por que `tilt` y `edge` (2026-11-09, «se puede modelar todavia mejor»): con solo `at`, `deg`,
 * `sAt` y `sDeg` cada bulto es una elipse alineada con el eje, redonda y sin borde, y un musculo
 * que va en diagonal (el pectoral hacia el hombro, el oblicuo, el sartorio) no se puede escribir.
 * Los dos campos son opcionales; sin ellos el bulto es exactamente el de antes, bit a bit (lo
 * vigila la prueba).
 */
export interface Bump {
  at: number;
  deg: number;
  d: number;
  sAt: number | readonly [number, number];
  sDeg: number;
  /**
   * Giro del bulto, en grados, en el plano (eje, contorno). Se mide en metros: lo recorrido a lo
   * largo del eje (`travelled`, no `at`) y el arco del contorno (angulo por el radio de la
   * seccion) se pasan a metros antes de girar, asi que 45 es una diagonal de verdad tambien donde
   * `at` no son metros (brazo, pierna) o el tramo es fino. Positivo gira el eje largo del bulto
   * desde "eje adelante" hacia "angulo creciente". Con giro, `sAt` de dos valores sigue siendo
   * antes y despues, pero a lo largo del eje girado. En el tronco el bulto espejo lleva el giro
   * opuesto, y uno de la linea media con giro tambien se duplica con medio empuje cada copia
   * (sale en X, simetrico, y en su centro sube `d`). El arco del contorno se mide con la derivada
   * de la elipse al angulo del bulto, en la seccion de cada fila.
   */
  tilt?: number;
  /**
   * Dureza del borde, >= 1 (por defecto 1, la campana de Gauss). El perfil es
   * exp(-0.5 * r^(2 * edge)): con 2 o 3 el vientre del musculo sale plano y el borde, marcado,
   * que es lo que separa un musculo de un bulto blando.
   */
  edge?: number;
}

export interface Sweep {
  /** Puntos del eje y su parametro. En el tronco el parametro es la altura y. */
  axis: readonly { at: number; p: Vec3 }[];
  sections: readonly Section[];
  /** Largo en metros del remate redondeado al principio y al final del tramo. */
  caps: readonly [number, number];
  /**
   * "level": secciones horizontales (tronco, cuello, cabeza); angulo 0 hacia +x, 90 hacia +z.
   * "limb": perpendiculares al eje, con delante (+z) de referencia. "foot": con arriba (+y).
   */
  frame: "level" | "limb" | "foot";
  /** Paso de muestreo del parametro: comun a todo el tramo, para que las zonas casen. */
  step: number;
  /**
   * Intervalo del eje con la rejilla tres veces mas fina, la de los remates. Lo usa la cara: con
   * filas de 6 mm un labio o un parpado (de 1 cm o menos) caia entre dos filas y salia como una
   * raya. Es una funcion de `at` como la de los remates, asi que dos zonas vecinas del tramo siguen
   * casando fila a fila.
   */
  fine?: readonly [number, number];
  /** Paso del contorno en grados; si falta, `ARC_STEP`. Un dedo no necesita el del tronco. */
  arcStep?: number;
  /** Relieve: musculos, huesos y surcos sobre la elipse. */
  relief?: readonly Bump[];
  /** Altura minima de la superficie: la planta del pie es plana y apoya en y = 0. */
  floor?: number;
  /**
   * Giro de la seccion alrededor del eje, en grados, por tramos de `at` (entre dos nudos pasa con
   * una curva suave, sin rebasar ninguno de los dos; antes del primero y despues del ultimo se
   * queda en el suyo). Positivo lleva el angulo 0 hacia el 90. Lo pide la mano (Humano 2,
   * 2026-11-09): en reposo el antebrazo prona un poco y la palma mira al muslo algo hacia atras;
   * sin giro, la mano se veia de canto desde delante, como una hoja. El relieve gira con la
   * seccion, como los musculos del antebrazo con el radio. En el tramo derecho el giro va con el
   * signo opuesto, para que siga siendo el espejo del izquierdo. Sin `twist` el tramo es el de
   * antes, bit a bit.
   */
  twist?: readonly { at: number; deg: number }[];
}

export type SweepName =
  | "column"
  | "arm"
  | "leg"
  | "foot"
  | "thumb"
  | "index"
  | "middle"
  | "ring"
  | "little"
  | "ear";

/** Trozo de un tramo: intervalo del eje y, solo en el tronco, sector del contorno en grados. */
export interface Patch {
  on: SweepName;
  from: number;
  to: number;
  arc?: readonly [number, number];
  /** Solo en una zona central y fuera del tronco: usar la copia derecha del tramo (la otra oreja). */
  mirror?: boolean;
}

export interface ZoneShape {
  zone: string;
  /** Centro de referencia de la zona (el del backend). */
  position: Vec3;
  patches: readonly Patch[];
  /** Lado del tripulante en las zonas pares; los tramos de brazo y pierna se reflejan. */
  side?: "left" | "right";
}

/** Altura del cuerpo, para encuadrar la camara. */
export const BODY_HEIGHT = 1.73;

// ---- Mano izquierda en reposo ----
//
// Humano 2 (2026-11-09, «las manos son garras diminutas»): la mano de antes median 0,17 m con
// dedos de 12 lados separados por rendijas, recta y de canto, y se leia como una pinza. Esta es
// una mano de adulto de 1,73 m: 0,19 m de la muneca a la punta del corazon (0,105 de palma y
// 0,085 de dedo), 0,085 de ancho de palma, dedos gruesos que se tocan, con nudillos y falanges, y
// recogidos como en una mano que cuelga sin esfuerzo (cada dedo algo mas que el anterior, del
// indice al menique). El pulgar sale de la eminencia tenar, cerca de la muneca, y descansa por
// delante del indice, del lado de la palma.
//
// Los dedos son tramos sueltos y se colocan en el marco de la palma: `HAND_DOWN` (de la muneca a
// los nudillos), `HAND_PALM` (hacia donde mira la palma) y `HAND_THUMBWARD` (hacia el pulgar). El
// marco sale de los mismos puntos que el eje del brazo (`at` 5 y 6) y del mismo giro, asi que si
// se retoca la mano los dedos la siguen.

/**
 * Eje del brazo en `at` 5 (arranque de la palma, bajo la muneca) y en `at` 6 (nudillos).
 *
 * Inicio 3D (2026-11-10, «convertir el modelo de inicio a 3D»): la mano cuelga donde la del
 * cuerpo de «Inicio», abierta y separada del muslo (la muneca a 0,34 m del centro y 0,85 de alto,
 * los nudillos a 0,35 y 0,76). Antes colgaba a 0,27, casi pegada a la cadera.
 */
const PALM_START: Vec3 = [0.342, 0.845, 0.038];
const KNUCKLES: Vec3 = [0.354, 0.76, 0.06];
/**
 * Giro de la mano en reposo. Humano 2 la pronaba 25 grados (la palma al muslo y algo hacia atras).
 * Inicio 3D (2026-11-10): en «Inicio» la mano cuelga abierta con la palma hacia el muslo y algo
 * hacia delante, y de frente se ve ancha, no de canto; con 15 grados hacia delante el pulgar queda
 * delante de la palma, sin abrirse hacia fuera como un gancho (eso pasaba con 25).
 */
const HAND_TWIST = 15;

/** Vector unitario. Funcion declarada (no `const`): la usan los dedos antes de las de abajo. */
function normalized(v: readonly number[]): Vec3 {
  const length = Math.hypot(v[0]!, v[1]!, v[2]!);
  return [v[0]! / length, v[1]! / length, v[2]! / length];
}

/** `p` + `k` * `d`. */
function along(p: Vec3, d: Vec3, k: number): Vec3 {
  return [p[0] + d[0] * k, p[1] + d[1] * k, p[2] + d[2] * k];
}

/**
 * Marco de la palma, con la misma cuenta que `Tube.frame` al final del brazo: delante (+z) sin la
 * componente del eje, a lo ancho el eje por delante, y los dos girados `HAND_TWIST`.
 */
function handBasis(): { down: Vec3; palm: Vec3; thumbward: Vec3 } {
  const down = normalized([KNUCKLES[0] - PALM_START[0], KNUCKLES[1] - PALM_START[1], KNUCKLES[2] - PALM_START[2]]);
  const depth = normalized([-down[0] * down[2], -down[1] * down[2], 1 - down[2] * down[2]]);
  const across: Vec3 = [
    down[1] * depth[2] - down[2] * depth[1],
    down[2] * depth[0] - down[0] * depth[2],
    down[0] * depth[1] - down[1] * depth[0],
  ];
  const turn = (HAND_TWIST * Math.PI) / 180;
  const [c, s] = [Math.cos(turn), Math.sin(turn)];
  return {
    down,
    palm: [across[0] * c + depth[0] * s, across[1] * c + depth[1] * s, across[2] * c + depth[2] * s],
    thumbward: [depth[0] * c - across[0] * s, depth[1] * c - across[1] * s, depth[2] * c - across[2] * s],
  };
}

const HAND = handBasis();

/** Direccion en el marco de la mano: `down`, `palm` y `thumbward` en proporcion. */
function inHand(down: number, palm: number, thumbward: number): Vec3 {
  return normalized([0, 1, 2].map((k) => HAND.down[k]! * down + HAND.palm[k]! * palm + HAND.thumbward[k]! * thumbward));
}

/**
 * Un dedo de la mano izquierda. Nace dentro de la palma, sale por su nudillo (`across` metros
 * hacia el pulgar desde el centro de los nudillos y `lift` por encima de la linea del corazon) y
 * baja `length` metros en tres falanges (43, 31 y 26 %), cada una doblada `curl` grados mas hacia
 * la palma que la anterior; `spread` lo abre hacia el pulgar (negativo, hacia el menique).
 * `radius` es el semiancho en el nudillo; de canto es algo mas fino, como un dedo de verdad, y se
 * afina hacia la yema con un abultamiento suave en cada articulacion.
 */
function finger(
  across: number,
  lift: number,
  length: number,
  radius: number,
  curl: readonly [number, number, number],
  spread: number,
): Sweep {
  const knuckle = along(along(KNUCKLES, HAND.thumbward, across), HAND.down, -lift);
  const points: Vec3[] = [along(knuckle, HAND.down, -0.016), knuckle];
  const opening = Math.sin((spread * Math.PI) / 180);
  let bend = 0;
  [0.43, 0.31, 0.26].forEach((share, k) => {
    bend += curl[k]!;
    const angle = (bend * Math.PI) / 180;
    const direction = inHand(Math.cos(angle), Math.sin(angle), opening);
    points.push(along(points[points.length - 1]!, direction, share * length));
  });
  // [at, ancho, grueso]: nudillo, falange, articulacion, falange... hasta la yema.
  const profile: readonly [number, number, number][] = [
    [0, 1.02, 1],
    [1, 1.04, 0.95],
    [1.5, 0.95, 0.85],
    [2, 0.97, 0.86],
    [2.5, 0.88, 0.77],
    [3, 0.88, 0.76],
    [3.5, 0.84, 0.72],
    [4, 0.8, 0.7],
  ];
  return {
    frame: "limb",
    step: 0.25,
    arcStep: 22.5,
    caps: [0.006, 0.0075],
    twist: [{ at: 0, deg: HAND_TWIST }],
    axis: points.map((p, at) => ({ at, p })),
    sections: profile.map(([at, wide, thick]) => ({ at, rx: radius * thick, rz: radius * wide })),
  };
}

/**
 * El pulgar izquierdo: del carpo, en el borde de la palma del lado del pulgar y bajo la muneca, a
 * la yema, que descansa por delante del indice y del lado de la palma. El metacarpiano queda
 * dentro de la eminencia tenar (relieve del brazo); asoman las dos falanges.
 */
function thumb(): Sweep {
  const base = along(PALM_START, HAND.thumbward, 0.02);
  // Metacarpiano abierto hacia delante; las falanges vuelven hacia el indice. Sin apartarse hacia
  // la palma: con la mano pronada eso lo llevaba hacia el muslo y, de frente, el pulgar se veia
  // como un gancho suelto al lado de la mano.
  const segments: readonly [number, Vec3][] = [
    [0.048, inHand(0.88, -0.08, 0.44)],
    [0.034, inHand(0.95, -0.04, 0)],
    [0.028, inHand(0.93, 0.06, -0.3)],
  ];
  const points: Vec3[] = [base];
  for (const [length, direction] of segments) points.push(along(points[points.length - 1]!, direction, length));
  return {
    frame: "limb",
    step: 0.25,
    arcStep: 22.5,
    caps: [0.01, 0.008],
    twist: [{ at: 0, deg: HAND_TWIST + 70 }],
    axis: points.map((p, at) => ({ at, p })),
    sections: [
      { at: 0, rx: 0.013, rz: 0.015 },
      { at: 1, rx: 0.0105, rz: 0.0118 },
      { at: 1.5, rx: 0.0098, rz: 0.011 },
      { at: 2, rx: 0.0094, rz: 0.0108 },
      { at: 2.5, rx: 0.0088, rz: 0.0102 },
      { at: 3, rx: 0.0082, rz: 0.0094 },
    ],
  };
}

// Tramos del lado izquierdo (+x). El derecho es su espejo en x.
export const SWEEPS: Readonly<Record<SweepName, Sweep>> = {
  // Tronco, cuello y cabeza en una pieza: de la entrepierna (0,78 m) a la coronilla (1,73).
  column: {
    frame: "level",
    step: 0.006,
    // La cara, de bajo la barbilla a las cejas, con filas de 2 mm (ver `Sweep.fine`).
    fine: [1.494, 1.648],
    caps: [0.06, 0.07],
    axis: [
      { at: 0.78, p: [0, 0.78, 0] },
      { at: 0.86, p: [0, 0.86, -0.005] },
      { at: 0.95, p: [0, 0.95, -0.005] },
      { at: 1.05, p: [0, 1.05, 0] },
      { at: 1.15, p: [0, 1.15, 0.008] },
      { at: 1.25, p: [0, 1.25, 0.012] },
      { at: 1.33, p: [0, 1.33, 0.005] },
      { at: 1.38, p: [0, 1.38, -0.005] },
      { at: 1.41, p: [0, 1.41, -0.01] },
      { at: 1.44, p: [0, 1.44, -0.012] },
      { at: 1.47, p: [0, 1.47, -0.0135] },
      { at: 1.49, p: [0, 1.49, -0.0105] },
      // Cabeza humano 1 (2026-11-09): de la barbilla (1,50) a la coronilla, 0,23 m, la de un
      // adulto (ANSUR II, p50 0,23-0,24). Con 0,19 la cabeza era pequena y el cuerpo no se leia
      // como persona. El centro de cada seccion va entre la cara y la nuca: abajo adelantado por
      // la mandibula, que sale por delante del cuello, y arriba hacia atras, para que la frente
      // se curve hacia la coronilla y la nuca abulte detras.
      { at: 1.51, p: [0, 1.51, -0.005] },
      { at: 1.53, p: [0, 1.53, 0] },
      { at: 1.55, p: [0, 1.55, 0.0025] },
      { at: 1.57, p: [0, 1.57, 0.0015] },
      { at: 1.59, p: [0, 1.59, -0.0005] },
      { at: 1.62, p: [0, 1.62, -0.002] },
      { at: 1.65, p: [0, 1.65, -0.003] },
      { at: 1.68, p: [0, 1.68, -0.006] },
      { at: 1.705, p: [0, 1.705, -0.01] },
      { at: 1.73, p: [0, 1.73, -0.014] },
    ],
    sections: [
      // La entrepierna, estrecha: queda dentro de los muslos y no asoma como un panal entre ellos.
      { at: 0.78, rx: 0.1, rz: 0.085 },
      // Humano 5 (2026-11-09), proporciones. Se compara con un varon adulto del percentil 50
      // (ANSUR II, 1,75 m, escalado a 1,73): anchura del torax 0,32-0,33 m (0,36 con los
      // dorsales), fondo del torax 0,25; cintura de 0,30 x 0,23; cadera 0,35-0,36 y fondo de
      // gluteos 0,24. Para un adulto atletico la cintura se estrecha (0,28) y el torax gana fondo:
      // con la cintura casi tan ancha como la pelvis y el pecho poco hondo, el tronco se leia como
      // una columna. Medido en la malla (con el relieve): torax 0,37 x 0,26 a 1,26 m, cintura
      // 0,28 x 0,21 y pelvis 0,32 x 0,23.
      //
      // Neutro 4 (2026-11-10, «le has puesto culo»): el cuerpo es un maniqui holografico,
      // androgino. La pelvis era mas estrecha que el arranque de los muslos, y la cupula de cada
      // pierna asomaba por fuera y por delante: de frente quedaba dibujada la silueta de un
      // calzoncillo y, encima, dos hombros en la cadera. Ahora la pelvis envuelve el arranque de
      // las piernas (que dentro del tronco no se ve) y se funde con el muslo en una sola pieza lisa,
      // con la cadera intermedia: ni la de un varon estrecho ni la de una mujer.
      //
      // Inicio 3D (2026-11-10, «convertir el modelo de inicio a 3D»): la referencia vuelve a ser
      // el cuerpo de «Inicio», un varon atletico, y su silueta de frente (`silueta.json`, por fila)
      // manda en el ancho: cadera de 0,33-0,34 m a 0,90, cintura de 0,29 a 1,05 y caja de 0,33 bajo
      // la axila. La pelvis sigue envolviendo el arranque de los muslos (Neutro 4), con 1 cm menos
      // de ancho que la del maniqui, que en «Inicio» sobraba.
      { at: 0.86, rx: 0.162, rz: 0.104 },
      { at: 0.9, rx: 0.168, rz: 0.108 },
      { at: 0.95, rx: 0.155, rz: 0.106 },
      // La cintura, estrecha, y la caja que se abre hacia la axila: la V del tronco atletico. El
      // relieve (oblicuos, dorsales, pectorales) pone encima el volumen de cada musculo.
      { at: 1.05, rx: 0.137, rz: 0.099 },
      { at: 1.15, rx: 0.154, rz: 0.107 },
      { at: 1.25, rx: 0.178, rz: 0.116 },
      { at: 1.33, rx: 0.182, rz: 0.11 },
      // Del hombro al cuello, la cuesta de los trapecios (en «Inicio», 0,19 m a cada lado a 1,40
      // y 0,09 a 1,44): sin ella el brazo asomaba por encima del tronco como una bola.
      // Neutro 2 (2026-11-10, «el brazo nace de una bola, como una hombrera de muneco»): la cuesta
      // llega hasta donde empieza el brazo (0,184 m a cada lado a 1,38, antes 0,176) y lo entrega a
      // su altura: 1,394 m a 0,18 en el tronco y 1,385 a 0,19 en el brazo. Asi el trapecio baja en
      // continuo hasta la punta del hombro y de ahi cae el brazo. Con 0,19 el tronco acababa en una
      // esquina propia por encima del brazo, otra hombrera.
      // Inicio 3D: en «Inicio» los trapecios son altos y llenos (0,20 m a cada lado a 1,41 y 0,10
      // a 1,445), la cuesta de un hombre que entrena. Sigue entregando el hombro al brazo.
      // Hombro A (2026-11-10): la esquina del tronco a 1,38-1,41, 7-8 mm mas adentro. Caia a
      // plomo justo donde salia el brazo, y el brazo asomaba por un costado vertical: ahora la
      // esquina queda dentro del deltoides y el brazo sale de la cuesta del trapecio, casi tangente.
      { at: 1.38, rx: 0.188, rz: 0.098 },
      { at: 1.41, rx: 0.182, rz: 0.088 },
      { at: 1.44, rx: 0.112, rz: 0.069 },
      // Cuello de varon atletico, como el de «Inicio» (0,13 m de ancho de 1,46 a 1,52): el de 0,118
      // de Neutro 1 era el de un maniqui sin sexo. Los esternocleidomastoideos van en el relieve.
      { at: 1.47, rx: 0.064, rz: 0.059 },
      { at: 1.49, rx: 0.064, rz: 0.061 },
      // Craneo: 0,155 m de ancho y 0,195 de fondo en lo mas grande (ANSUR II p50), mas fondo que
      // ancho; abajo se estrecha en la mandibula. La cara (nariz, labios, menton) va en el relieve.
      // Inicio 3D: la cabeza del render es algo mas ancha (0,166 m de sien a sien) y la mandibula,
      // de varon, cuadrada y llena hasta el angulo (0,14 m a 1,53), sin la V de Facciones 1.
      { at: 1.51, rx: 0.064, rz: 0.066 },
      { at: 1.53, rx: 0.067, rz: 0.073 },
      { at: 1.55, rx: 0.072, rz: 0.081 },
      { at: 1.57, rx: 0.0735, rz: 0.089 },
      { at: 1.59, rx: 0.077, rz: 0.095 },
      { at: 1.62, rx: 0.0795, rz: 0.098 },
      { at: 1.65, rx: 0.0805, rz: 0.098 },
      { at: 1.68, rx: 0.0795, rz: 0.096 },
      { at: 1.705, rx: 0.0765, rz: 0.093 },
      { at: 1.73, rx: 0.07, rz: 0.088 },
    ],
    relief: [
      // --- tronco delantero ---
      // Modelado 3 (2026-11-09): del pubis a las claviculas, con `tilt` y `edge`. Con `tilt` el
      // eje largo del bulto gira desde "hacia arriba" hacia "angulo creciente", que en el lado
      // izquierdo (0-90) es hacia la linea media: un giro negativo sube hacia fuera. El espejo
      // derecho sale solo, con el giro opuesto.
      //
      //
      // Humano 3 (2026-11-09, «que no se que parece»): con bordes netos (`edge` 2-2,5) y surcos de
      // 4-5 mm, mas finos que la rejilla de 6 mm, cada musculo salia como un cable recortado y el
      // tronco parecia despellejado. Una persona tiene piel y grasa encima: el musculo se adivina
      // por su volumen, no por su contorno. Asi que los vientres siguen ahi, con su sitio y su
      // direccion, pero con el borde casi de campana (`edge` 1,2-1,4) y los surcos mas someros y
      // del doble de anchos, para que la luz resbale de un musculo al siguiente en vez de cortarse.
      //
      // Claviculas: una barra casi horizontal que sube un poco hacia el hombro, apenas asomada
      // bajo la piel; debajo, la fosita blanda que la separa del pectoral.
      { at: 1.396, deg: 50, d: 0.005, sAt: 0.045, sDeg: 3.6, tilt: 98, edge: 1.2 },
      { at: 1.381, deg: 46, d: -0.002, sAt: 0.03, sDeg: 5, tilt: 98 },
      // Neutro 2: la carne de delante del hombro, bajo el extremo de la clavicula, rellena el angulo
      // entre el tronco y el brazo; sin ella, de frente, el brazo se leia pegado al tronco con una
      // raya oscura en la juntura, como la pieza de un muneco.
      // Hombro A (2026-11-10, «los hombros con el tronco siguen viendose de quita y pon»): el brazo
      // salia del tronco casi a escuadra (60-100 grados entre las dos superficies delante y detras,
      // medido en la linea donde se cortan), y en tres cuartos se leia un cilindro pegado al costado.
      // En una persona el pectoral mayor sale del pecho y entra en el brazo por delante (pliegue
      // axilar anterior), y el dorsal y el redondo mayor hacen lo mismo por detras: el tronco se
      // adelanta hasta abrazar la cara interna del brazo y el brazo sale de el, no de al lado. Asi
      // que la carne de delante del hombro es mas honda y llega mas abajo, bajo la clavicula sigue
      // hacia el deltoides (el surco deltopectoral, blando) y, mas abajo, el pliegue axilar: un
      // volumen que sube hacia fuera hasta la cara interna del brazo.
      { at: 1.34, deg: 29, d: 0.027, sAt: [0.065, 0.045], sDeg: 13, edge: 1.2 },
      { at: 1.378, deg: 36, d: 0.012, sAt: [0.035, 0.025], sDeg: 11, edge: 1.2 },
      { at: 1.3, deg: 20, d: 0.03, sAt: [0.05, 0.05], sDeg: 14, tilt: -20, edge: 1.2 },
      // Inicio 3D (2026-11-10, «convertir el modelo de inicio a 3D»): vuelve el tronco de un varon
      // atletico, el de «Inicio», con la musculatura a la vista pero bajo la piel (lo que aprendio
      // Humano 3: bordes casi de campana y surcos someros y anchos, nada de cables). Se parte del
      // relieve del lote «facciones» (commit 163e36b), anterior al maniqui androgino.
      //
      // Pectoral mayor: un volumen ancho que se funde hacia la clavicula sin escalon. Lo que se ve
      // es su borde de abajo, en diagonal del esternon a la axila, como una sombra redondeada y no
      // como un corte. Sin estrias de fibra: bajo la piel no se ven.
      { at: 1.33, deg: 62, d: 0.016, sAt: [0.05, 0.05], sDeg: 22 },
      { at: 1.295, deg: 58, d: 0.02, sAt: [0.08, 0.07], sDeg: 24, tilt: -62, edge: 2 },
      { at: 1.25, deg: 62, d: -0.0045, sAt: 0.065, sDeg: 3.8, tilt: -62 },
      // Surco del esternon entre los dos pectorales: un valle suave, no una raja.
      { at: 1.29, deg: 90, d: -0.0045, sAt: [0.06, 0.07], sDeg: 5 },
      // Caja toracica: un abombado ancho y blando en la esquina entre el pecho y el costado. La
      // seccion eliptica deja esa esquina plana y el tronco se leia como una caja; con esto la
      // piel da la vuelta de delante al costado como un barril, de la axila a la cintura.
      { at: 1.19, deg: 32, d: 0.005, sAt: [0.07, 0.08], sDeg: 22 },
      // Serrato anterior: dientes bajo el brazo en diagonal, como en la costilla donde nace. Se
      // adivinan como ondas en el costado.
      { at: 1.24, deg: 19, d: 0.0035, sAt: 0.016, sDeg: 4.6, tilt: -55, edge: 1.2 },
      { at: 1.208, deg: 21, d: 0.0035, sAt: 0.016, sDeg: 4.6, tilt: -55, edge: 1.2 },
      { at: 1.176, deg: 23, d: 0.0035, sAt: 0.016, sDeg: 4.6, tilt: -55, edge: 1.2 },
      { at: 1.146, deg: 25, d: 0.003, sAt: 0.015, sDeg: 4.4, tilt: -55, edge: 1.2 },
      // Oblicuo externo: el flanco entre las costillas y la cresta de la cadera, con las fibras
      // bajando hacia dentro ("manos en los bolsillos"). Es el que hace la cintura: un volumen
      // redondo que une la caja toracica con la cadera, y su borde de abajo, el rodete blando que
      // asoma sobre la cadera.
      { at: 1.04, deg: 30, d: 0.012, sAt: [0.06, 0.07], sDeg: 12, tilt: -40, edge: 1.3 },
      { at: 0.985, deg: 24, d: 0.006, sAt: 0.03, sDeg: 12, tilt: -40 },
      // Linea semilunar: el valle ancho que separa el oblicuo del recto, en curva.
      { at: 1.07, deg: 59, d: -0.0025, sAt: 0.075, sDeg: 4.5, tilt: 8 },
      // Recto del abdomen: una columna a cada lado de la linea alba, del pubis a las costillas,
      // mas ancha arriba. Las intersecciones tendinosas son ondulaciones someras que suben un poco
      // hacia fuera: se leen los cuadros de un abdomen en forma, redondeados por la piel, no las
      // esquinas de una tableta tallada. Los tres cortes (1,118, 1,062 y 1,006) son los de «Inicio».
      { at: 1.06, deg: 74.5, d: 0.011, sAt: [0.115, 0.12], sDeg: 11, edge: 1.4 },
      { at: 1.118, deg: 75, d: -0.0042, sAt: 0.026, sDeg: 5.5, tilt: 96 },
      { at: 1.062, deg: 76, d: -0.0042, sAt: 0.027, sDeg: 5.5, tilt: 95 },
      { at: 1.006, deg: 77, d: -0.0028, sAt: 0.026, sDeg: 5.5, tilt: 94 },
      // Linea alba: el valle recto entre las dos columnas.
      { at: 1.07, deg: 90, d: -0.0025, sAt: [0.1, 0.09], sDeg: 4.5 },
      // Ombligo: una fosita en la linea media, a la altura del ultimo corte.
      { at: 1.0, deg: 90, d: -0.004, sAt: 0.01, sDeg: 3.5 },
      // La «V» de la ingle: valle en diagonal de la cresta de la cadera al pubis, por debajo del
      // oblicuo; en «Inicio» es la linea clara que baja hacia el pubis. Somero: mas hondo, junto a
      // la cupula de los muslos, dibujaba un calzoncillo (Neutro 4).
      { at: 0.945, deg: 50, d: -0.0035, sAt: [0.035, 0.07], sDeg: 5, tilt: -45 },
      // La pelvis se llena por delante de cada muslo con un plano ancho en la diagonal de la ingle
      // (Neutro 4): la cupula de la pierna queda dentro y el muslo sale de la pelvis por esa
      // diagonal, de la cadera a la entrepierna, sin escalon horizontal.
      { at: 0.885, deg: 48, d: 0.02, sAt: [0.045, 0.055], sDeg: 22, tilt: -50, edge: 1.3 },
      // --- espalda ---
      // Se escribe el lado izquierdo (270 la columna, 360 el costado) y el derecho sale en espejo.
      // Aqui un giro positivo lleva el eje largo del bulto hacia arriba y hacia fuera.
      // Trapecio, en rombo: las fibras de arriba bajan en diagonal del cuello al hombro y hacen la
      // cuesta; las del medio van en horizontal de la columna a la espina de la escapula; las de
      // abajo suben en V desde la mitad de la espalda. Humano 3 (2026-11-09): como delante, bajo
      // la piel; una lamina que se adivina por el volumen y se funde en sus vecinos.
      //
      // Volumen 5 (2026-11-10): la espalda lleva su dibujo (`backAnatomy/torso.ts`, en metros de
      // x y altura), y la luz tiene que acompanarlo: cada bulto y cada surco de aqui cae sobre el
      // musculo o la linea que dibuja la textura, no un par de centimetros al lado. Con la luz por
      // un sitio y el dibujo por otro, el brillo de un surco cruzaba un vientre pintado y la
      // espalda se leia sucia. Por eso los centros de abajo se han medido proyectando el bulto de
      // espaldas (x del punto de la superficie a ese angulo y altura) contra las cotas del dibujo.
      { at: 1.418, deg: 312, d: 0.02, sAt: [0.05, 0.04], sDeg: 11, tilt: -60, edge: 1.3 },
      // Neutro 2: lo mismo detras, sobre la escapula, donde el hombro se junta con la espalda.
      // Volumen 5: el de dentro (romboides y trapecio medio) se aparta del borde medial de la
      // escapula, que en el dibujo es un surco (x 0,08): caia encima y lo borraba.
      // Hombro A (2026-11-10): como delante, el pliegue axilar posterior (dorsal ancho y redondo
      // mayor) tiende el puente del omoplato a la cara de detras del brazo, y encima, la carne que
      // envuelve la raiz del brazo por detras. Algo mas alto que el de delante, como en el cuerpo.
      { at: 1.355, deg: 328, d: 0.02, sAt: [0.07, 0.045], sDeg: 13, edge: 1.2 },
      { at: 1.382, deg: 324, d: 0.012, sAt: [0.035, 0.025], sDeg: 11, edge: 1.2 },
      { at: 1.31, deg: 343, d: 0.026, sAt: [0.05, 0.05], sDeg: 14, tilt: 20, edge: 1.2 },
      { at: 1.35, deg: 286, d: 0.007, sAt: 0.035, sDeg: 10, edge: 1.3 },
      { at: 1.245, deg: 284, d: 0.005, sAt: [0.06, 0.05], sDeg: 8, tilt: 22, edge: 1.3 },
      // Espina de la escapula: una cresta que sube hacia el acromion, donde la dibuja la textura
      // (de x 0,08 a 1,366 m a x 0,19 a 1,402: unos 18 grados sobre la horizontal, giro 72); bajo
      // ella, el infraespinoso en el centro de su fosa dibujada (0,118, 1,322) y el redondo mayor
      // entre los dos trazos que lo limitan hacia la axila, subiendo unos 36 grados (giro 54). El
      // borde medial de la escapula, a plomo en x 0,08 de 1,24 a 1,40 m, queda como un valle.
      { at: 1.384, deg: 312, d: 0.0035, sAt: 0.045, sDeg: 4.5, tilt: 72 },
      { at: 1.318, deg: 309, d: 0.008, sAt: [0.042, 0.036], sDeg: 8, tilt: 45, edge: 1.2 },
      { at: 1.262, deg: 326, d: 0.006, sAt: 0.035, sDeg: 6, tilt: 54, edge: 1.2 },
      { at: 1.315, deg: 296, d: -0.0025, sAt: 0.065, sDeg: 4.5 },
      // Dorsal ancho: la V de la espalda, en diagonal de la cintura a la axila; abajo es lamina
      // y la carne se junta bajo el brazo, que es lo que ensancha la espalda arriba. Con borde
      // blando el costado sigue redondo de la axila a la cintura. Volumen 5: el vientre carnoso,
      // por fuera de la linea donde acaba la aponeurosis (dibujada de la axila a la lumbar), unos
      // 15 grados de la vertical; por dentro de esa linea la lamina es plana.
      { at: 1.16, deg: 334, d: 0.01, sAt: [0.08, 0.07], sDeg: 15, tilt: 6, edge: 1.3 },
      { at: 1.24, deg: 338, d: 0.01, sAt: 0.04, sDeg: 12, tilt: 20, edge: 1.3 },
      // Erectores espinales: dos columnas a los lados de la columna, gruesas en la lumbar y finas
      // en la espalda alta, con el valle de la columna entre ellas. Volumen 5: el valle sube con
      // la linea de las apofisis que dibuja la textura, hasta la altura de las escapulas.
      { at: 1.06, deg: 281.5, d: 0.008, sAt: [0.08, 0.12], sDeg: 6, edge: 1.3 },
      { at: 1.25, deg: 280, d: 0.003, sAt: 0.06, sDeg: 4.5 },
      { at: 1.12, deg: 270, d: -0.0055, sAt: [0.13, 0.2], sDeg: 5 },
      // Gluteos: los del maniqui de Neutro 4 (2026-11-10, «le has puesto culo»), un abombado ancho
      // y bajo con la hendidura insinuada, algo mas lleno para un cuerpo atletico. «Inicio» no
      // ensena la espalda, asi que no hay referencia que pida los globos de antes.
      // Espalda 5 (2026-11-10, «falta darle detalle [a la espalda] como en frente»): la espalda ya
      // lleva su textura dibujada, y la luz tiene que dibujar tambien el gluteo, no un plano. El
      // mayor algo mas lleno y con forma: su vientre cae en diagonal del sacro hacia fuera y abajo
      // (giro negativo: subiendo por el eje, hacia la linea media) y con borde algo mas neto. Encima
      // y por fuera, bajo la cresta, el gluteo medio, un abombado pequeno. Discreto, el de un
      // atleta: 1 cm de empuje, no los globos de antes.
      // Volumen 5 (2026-11-10): los dos, en el centro de los que dibuja `backAnatomy/legs.ts`: el
      // mayor entre su borde de arriba (del sacro al trocanter) y el pliegue, hacia x 0,08 a
      // 0,865 m; el medio bajo la cresta, hacia x 0,125 a 0,95 m.
      { at: 0.865, deg: 298, d: 0.01, sAt: [0.045, 0.055], sDeg: 21, tilt: -25, edge: 1.3 },
      { at: 0.95, deg: 326, d: 0.004, sAt: [0.03, 0.035], sDeg: 13, edge: 1.2 },
      { at: 0.84, deg: 270, d: -0.02, sAt: [0.05, 0.03], sDeg: 45 },
      { at: 0.85, deg: 270, d: -0.0035, sAt: [0.045, 0.05], sDeg: 7 },
      // --- cabeza y cuello ---
      // Humano 1 (2026-11-09, «que no se que parece»): la cara de antes era una mascara, con
      // cuencas y boca como bandas hundidas. Ahora es una cara estilizada, sin rasgos de nadie,
      // con las proporciones de un adulto: barbilla 1,50, base de la nariz 1,565, cejas 1,635 y
      // nacimiento del pelo 1,70 (los tres tercios de la cara, iguales); los ojos a media cabeza
      // (1,618). Los ojos no son agujeros: la cuenca es una sombra ancha y somera y dentro abomba
      // el globo con su parpado.
      //
      // Cuello. Inicio 3D: en «Inicio» los esternocleidomastoideos dibujan la V del cuello, de
      // detras de la oreja a la punta del esternon. Cordones blandos y anchos (borde 1,4, no los 2
      // de 163e36b, que con la sombra de cavidades salian como cables); entre los dos, la garganta
      // apenas hundida, una nuez discreta y, abajo, la fosa yugular.
      { at: 1.475, deg: 30, d: 0.0045, sAt: 0.045, sDeg: 12, tilt: -32, edge: 1.4 },
      { at: 1.435, deg: 90, d: -0.004, sAt: [0.012, 0.014], sDeg: 12 },
      { at: 1.476, deg: 90, d: 0.003, sAt: [0.008, 0.01], sDeg: 9 },
      // Detras, la cuesta del trapecio sube blanda de la espalda a la nuca, sin el surco de la
      // nuca entre las dos: con el, la nuca se leia como una costura.
      { at: 1.475, deg: 238, d: 0.006, sAt: [0.025, 0.035], sDeg: 20, tilt: 30 },
      // Nuca: el hueco bajo el craneo y, encima, el occipital, que abomba la cabeza por detras.
      { at: 1.535, deg: 270, d: -0.004, sAt: 0.02, sDeg: 28 },
      { at: 1.6, deg: 270, d: 0.004, sAt: 0.03, sDeg: 40 },
      // --- cara ---
      // Inicio 3D: la cara de «Inicio» es la de un varon sereno, con la frente y las cejas firmes,
      // la nariz recta y algo ancha, la mandibula cuadrada y el menton marcado. Se parte de la de
      // Neutro 1 (rasgos que se adivinan por el volumen, sin surcos que la sombra de cavidades
      // vuelva arrugas) y se le da hueso: arco de las cejas, pomulo, angulo de la mandibula y
      // menton. Sin arco de Cupido ni amago de sonrisa: la boca, cerrada y recta.
      //
      // Mandibula: un borde limpio de la barbilla al angulo de bajo la oreja, y bajo el, el hueco
      // somero donde la cara se separa del cuello.
      { at: 1.528, deg: 42, d: 0.0035, sAt: 0.035, sDeg: 7, tilt: -57 },
      { at: 1.518, deg: 36, d: -0.0012, sAt: 0.035, sDeg: 8, tilt: -57 },
      // El angulo de la mandibula, bajo la oreja: lo que la hace cuadrada.
      { at: 1.53, deg: 22, d: 0.003, sAt: 0.014, sDeg: 10 },
      // Menton: ancho y algo cuadrado, casi a plomo con el labio de abajo.
      { at: 1.513, deg: 90, d: 0.021, sAt: [0.008, 0.016], sDeg: 14.5 },
      // La boca, apenas adelantada sobre el arco de los dientes.
      { at: 1.548, deg: 90, d: 0.006, sAt: [0.02, 0.014], sDeg: 15 },
      // Labios firmes: el de abajo, con algo mas de vientre que el de arriba.
      { at: 1.536, deg: 90, d: 0.0035, sAt: [0.0045, 0.004], sDeg: 10 },
      { at: 1.548, deg: 90, d: 0.0025, sAt: [0.0035, 0.005], sDeg: 11 },
      // La linea de la boca: fina, cerrada y recta, en reposo.
      { at: 1.5425, deg: 90, d: -0.0009, sAt: 0.0016, sDeg: 10 },
      // Nariz recta: la punta, lo que mas sale; el dorso, recto hasta el entrecejo; las aletas,
      // algo anchas, como la de «Inicio». No mas estrecha que esto: con la columna cada 2,5 grados
      // (3 mm), un dorso mas fino sale como una arista viva (lo vigila la prueba de aristas).
      { at: 1.574, deg: 90, d: 0.0135, sAt: [0.0075, 0.012], sDeg: 6 },
      { at: 1.59, deg: 90, d: 0.008, sAt: 0.014, sDeg: 5.2 },
      { at: 1.608, deg: 90, d: 0.0055, sAt: 0.01, sDeg: 4.6 },
      { at: 1.5715, deg: 83, d: 0.0025, sAt: 0.005, sDeg: 3 },
      // Ojos: horizontales y tranquilos, algo hundidos bajo la ceja (la cuenca, una sombra somera)
      // y el globo, una cupula baja con el parpado de arriba algo mas lleno. Sin pupila ni pliegue.
      { at: 1.622, deg: 66, d: -0.002, sAt: 0.013, sDeg: 12 },
      { at: 1.6195, deg: 66, d: 0.0035, sAt: [0.0075, 0.0065], sDeg: 7, edge: 1.2 },
      // Cejas: el arco del hueso, firme y recto, que hace sombra sobre el ojo; el entrecejo, liso.
      { at: 1.637, deg: 68, d: 0.0028, sAt: 0.007, sDeg: 15 },
      { at: 1.634, deg: 90, d: 0.002, sAt: 0.008, sDeg: 7 },
      // Pomulos: un hueso que corre hacia la oreja, algo mas marcado que el del maniqui; bajo el
      // ojo, la mejilla llena, que borra la ojera.
      { at: 1.6, deg: 50, d: 0.0065, sAt: 0.015, sDeg: 13, tilt: 8 },
      { at: 1.585, deg: 64, d: 0.003, sAt: 0.013, sDeg: 10 },
      // Las mejillas bajas, planas hacia la mandibula.
      { at: 1.545, deg: 52, d: 0.002, sAt: 0.02, sDeg: 14 },
      // Frente: ancha, lisa y apenas abombada; las sienes, casi planas.
      { at: 1.665, deg: 90, d: 0.0025, sAt: 0.022, sDeg: 30 },
      { at: 1.645, deg: 25, d: -0.001, sAt: 0.02, sDeg: 12 },
    ],
  },
  // Del hombro a los nudillos, en reposo, con la postura de «Inicio» (Inicio 3D, 2026-11-10): el
  // brazo cae algo abierto y el antebrazo se separa mas, unos 20 grados del tronco, con el codo a
  // 0,27 m del centro y 1,07 de alto y la mano colgando a 0,34-0,35 m, lejos del muslo. La de antes
  // (unos 11 grados, la mano a 0,27) se leia mas cerrada que la figura de «Inicio». El codo, un poco
  // por detras del costado y el antebrazo, adelantado; la palma, hacia el muslo, girada con `twist`.
  arm: {
    frame: "limb",
    step: 0.05,
    arcStep: 6,
    // Hombro A (2026-11-10): el remate de arriba, corto. Con 0,045 m de remate la raiz se cerraba
    // en cupula justo donde sale del tronco, y esa cupula era la «tapa redonda» del hombro; ahora
    // la raiz acaba dentro del tronco y lo que asoma ya es la seccion entera.
    caps: [0.012, 0.012],
    // Arranca dentro del tronco, bajo la cuesta de los trapecios: el deltoides no sobresale por
    // encima del hombro. El hombro, algo mas alto y mas adentro que el del maniqui: en «Inicio» el
    // deltoides llena la cuesta del trapecio hasta 1,41 m y por fuera no pasa de 0,26-0,27.
    axis: [
      { at: 0, p: [0.15, 1.365, -0.01] },
      { at: 1, p: [0.197, 1.34, 0] },
      { at: 2, p: [0.228, 1.205, -0.008] },
      { at: 3, p: [0.27, 1.07, -0.02] },
      { at: 4, p: [0.31, 0.955, 0.008] },
      { at: 5, p: PALM_START },
      { at: 6, p: KNUCKLES },
    ],
    // El antebrazo prona del codo a la muneca y la mano queda girada (ver `HAND_TWIST`).
    twist: [
      { at: 3, deg: 0 },
      { at: 4.7, deg: HAND_TWIST },
    ],
    // Humano 5 (2026-11-09): brazo del percentil 50 (ANSUR II), con el relieve incluido. Brazo
    // relajado de 0,31-0,33 m de perimetro (unos 0,10 de diametro), codo de 0,08, antebrazo de
    // 0,09 arriba que se afina a una muneca de 0,058 x 0,04.
    // Neutro 2 (2026-11-10): el arranque es mas bajo que hondo (`rx` 0,04-0,048, que aqui, con el
    // eje casi horizontal, es el alto). Con 0,058 el brazo subia por encima de la cuesta del
    // trapecio y se leia como una hombrera.
    sections: [
      // Hombro A (2026-11-10): la raiz se ensancha de delante a atras (`rz`) hacia dentro del
      // tronco, como el cono que forman el deltoides y los pliegues axilares: asi la superficie del
      // brazo se acerca a la del tronco de soslayo y no a 90 grados. El alto (`rx`) no cambia: con
      // mas, el brazo volveria a subir por encima del trapecio (Neutro 2).
      { at: 0, rx: 0.04, rz: 0.062 },
      { at: 0.6, rx: 0.045, rz: 0.068 },
      { at: 1, rx: 0.047, rz: 0.058 },
      { at: 1.6, rx: 0.046, rz: 0.046 },
      { at: 2, rx: 0.044, rz: 0.044 },
      { at: 2.6, rx: 0.041, rz: 0.041 },
      { at: 3, rx: 0.036, rz: 0.038 },
      // Facciones 2 (2026-11-10, «los antebrazos de las personas no son asi»): el antebrazo lo
      // dibuja la seccion, no el relieve. Lleno en su tercio de arriba, junto al codo, y afinandose
      // en una curva continua hasta la muneca. Con la mano en posicion neutra (pulgar delante) el
      // ancho de la muneca, de radio a cubito, va de delante a atras (`rz`) y de frente se ve su
      // grueso, de palma a dorso (`rx`): por eso de frente el antebrazo se afina mucho mas que de
      // lado, como en una persona. Inicio 3D: el de «Inicio» es de varon que entrena, 0,105 m de
      // frente bajo el codo, y se afina a 0,055 en la muneca.
      { at: 3.3, rx: 0.042, rz: 0.041 },
      { at: 3.6, rx: 0.038, rz: 0.039 },
      { at: 4, rx: 0.031, rz: 0.034 },
      { at: 4.3, rx: 0.025, rz: 0.031 },
      // Muneca algo mas fina que el arranque de la palma: sin ese estrechamiento el antebrazo
      // entraba en la mano como un tubo. Es mas ancha (de pulgar a menique, `rz`) que gruesa.
      { at: 4.5, rx: 0.0215, rz: 0.03 },
      { at: 4.8, rx: 0.021, rz: 0.03 },
      // La palma: 0,085 de ancho en los nudillos y unos 0,03 de grueso, mas gruesa en el talon
      // de la mano (las eminencias las pone el relieve).
      { at: 5.1, rx: 0.018, rz: 0.036 },
      { at: 5.5, rx: 0.017, rz: 0.042 },
      { at: 5.85, rx: 0.016, rz: 0.044 },
      { at: 6, rx: 0.0135, rz: 0.043 },
    ],
    relief: [
      // --- brazo y mano ---
      // Humano 4 (2026-11-09, «que se vea mas humano»): cada musculo con piel y grasa encima, que
      // lo redondean y rellenan el hueco entre dos vecinos. Bordes casi de campana (`edge` 1-1,5),
      // bultos anchos de contorno que se solapan y se funden, y ningun surco hacia dentro salvo el
      // pliegue del codo, ancho y somero. Todo va en `at` y en angulo del contorno: vale aunque se
      // doble algo el codo. Angulos del brazo: 0 dentro (la palma, en esta postura con el pulgar
      // delante), 90 delante, 180 fuera y 270 detras.
      //
      // Inicio 3D (2026-11-10): vuelven los musculos de un brazo atletico, los de «Inicio» y los
      // del lote «facciones» (163e36b): deltoides de tres cabezas, biceps en huso, braquial,
      // triceps en herradura y las dos masas del antebrazo.
      //
      // Deltoides: una masa redonda que cubre el hombro, con la cabeza de delante y la de detras
      // como hombros de esa masa, no como tiras. Neutro 2 (2026-11-10): la masa de fuera va mas
      // abajo (1,15), donde 180 ya mira hacia fuera: ensancha el hombro en vez de levantarlo, y su
      // cola de arriba se queda corta (0,2) para no subirlo por encima del trapecio. Las dos de
      // dentro (85 y 278) llevan el deltoides hacia el pectoral y la escapula y tapan la juntura.
      { at: 1.15, deg: 180, d: 0.004, sAt: [0.4, 0.2], sDeg: 40, edge: 1.2 },
      { at: 1.0, deg: 85, d: 0.01, sAt: [0.35, 0.4], sDeg: 30, edge: 1.2 },
      { at: 1.0, deg: 278, d: 0.01, sAt: [0.35, 0.4], sDeg: 30, edge: 1.2 },
      { at: 1.0, deg: 115, d: 0.011, sAt: [0.32, 0.4], sDeg: 26, tilt: 24, edge: 1.4 },
      { at: 1.0, deg: 250, d: 0.011, sAt: [0.32, 0.4], sDeg: 26, tilt: -24, edge: 1.4 },
      // Hombro A (2026-11-10): la raiz del brazo sale tangente al tronco. Por dentro, delante y
      // detras, la insercion del pectoral y del dorsal llena la cara interna del brazo hacia el
      // tronco; arriba y delante, el deltoides continua la cuesta del trapecio en vez de asomar
      // como una tapa.
      { at: 1.35, deg: 55, d: 0.011, sAt: [0.3, 0.3], sDeg: 25 },
      { at: 0.55, deg: 180, d: 0.006, sAt: [0.3, 0.3], sDeg: 50 },
      { at: 0.55, deg: 120, d: 0.006, sAt: [0.3, 0.3], sDeg: 30 },
      { at: 1.35, deg: 310, d: 0.008, sAt: [0.3, 0.3], sDeg: 25 },
      // La punta de la V, por fuera hasta media altura del brazo. Cae en el borde hombro/brazo y
      // su empuje fija la caja de «upper-arm» (alto anclado en `pain_points.json`): si se toca,
      // comprobar esa altura.
      { at: 1.5, deg: 180, d: 0.005, sAt: [0.22, 0.3], sDeg: 20, edge: 1.5 },
      // Biceps: un huso lleno delante que se funde con el resto del brazo por los lados.
      { at: 2.0, deg: 92, d: 0.018, sAt: [0.55, 0.4], sDeg: 34, edge: 1.5 },
      // Por fuera, la masa del brazo bajo la piel entre biceps y triceps: asienta los musculos sobre
      // un volumen.
      { at: 1.95, deg: 180, d: 0.005, sAt: 0.6, sDeg: 75 },
      // Braquial: asoma por fuera del biceps en la mitad de abajo, ensanchando el brazo hacia el
      // codo; por dentro, la carne blanda del brazo hacia la axila.
      { at: 2.3, deg: 148, d: 0.007, sAt: [0.32, 0.24], sDeg: 16, tilt: -10, edge: 1.3 },
      { at: 2.3, deg: 38, d: 0.005, sAt: [0.32, 0.24], sDeg: 16, tilt: 10, edge: 1.3 },
      // Triceps: la espalda del brazo llena. Las dos cabezas, anchas y solapadas, se cierran hacia
      // abajo, sin raya entre ellas; el tendon es solo donde la masa acaba.
      { at: 1.75, deg: 228, d: 0.013, sAt: [0.45, 0.38], sDeg: 28, tilt: 14, edge: 1.5 },
      { at: 1.85, deg: 300, d: 0.013, sAt: [0.5, 0.34], sDeg: 28, tilt: -14, edge: 1.5 },
      { at: 1.9, deg: 266, d: 0.007, sAt: [0.55, 0.42], sDeg: 45 },
      // Codo: el olecranon detras, el epicondilo de dentro y el pliegue delante, ancho y somero.
      { at: 3.0, deg: 270, d: 0.005, sAt: 0.12, sDeg: 28 },
      { at: 2.9, deg: 8, d: 0.003, sAt: 0.1, sDeg: 18 },
      { at: 2.95, deg: 90, d: -0.004, sAt: 0.12, sDeg: 30 },
      // Antebrazo (Facciones 2, 2026-11-10): dos masas anchas bajo la piel, sin surco entre ellas:
      // por fuera y arriba el braquiorradial con los extensores radiales, que nace ya sobre el
      // codo y da el punto mas alto del perfil de fuera; por dentro la de los flexores, con su
      // punto mas alto algo mas abajo (la regla clasica del dibujo de figura).
      { at: 3.2, deg: 160, d: 0.011, sAt: [0.3, 0.5], sDeg: 50 },
      { at: 3.38, deg: 15, d: 0.01, sAt: [0.3, 0.5], sDeg: 55 },
      // Detras, los extensores redondean el dorso sin raya; el borde del cubito queda liso.
      { at: 3.4, deg: 235, d: 0.004, sAt: [0.3, 0.5], sDeg: 45 },
      // Ultimo tercio: los tendones apenas se insinuan bajo la piel de la cara palmar (aqui, hacia
      // dentro), y en la muneca asoman la cabeza del cubito por el dorso y la apofisis del radio
      // del lado del pulgar. Relieves de milimetros: se ven con la luz rasante, no como cordones.
      { at: 4.3, deg: 10, d: 0.0012, sAt: 0.22, sDeg: 14 },
      { at: 4.6, deg: 230, d: 0.0025, sAt: 0.1, sDeg: 20 },
      { at: 4.55, deg: 110, d: 0.0018, sAt: 0.1, sDeg: 22 },
      // Mano. Eminencia tenar en la base del pulgar (palma, hacia delante), la hipotenar al otro
      // lado y el hueco de la palma entre las dos.
      { at: 5.25, deg: 42, d: 0.009, sAt: [0.2, 0.25], sDeg: 28, edge: 1.5 },
      { at: 5.4, deg: 330, d: 0.005, sAt: 0.3, sDeg: 24, edge: 1.5 },
      { at: 5.45, deg: 0, d: -0.003, sAt: 0.2, sDeg: 18 },
      // Nudillos en el dorso, uno por dedo, a la altura de donde sale cada uno. Suaves: mas
      // marcados, con los dedos debajo, se leian como una fila de cuentas.
      { at: 5.88, deg: 143, d: 0.002, sAt: 0.08, sDeg: 8 },
      { at: 5.88, deg: 169, d: 0.0022, sAt: 0.08, sDeg: 8 },
      { at: 5.88, deg: 193, d: 0.002, sAt: 0.08, sDeg: 8 },
      { at: 5.88, deg: 218, d: 0.0018, sAt: 0.08, sDeg: 8 },
    ],
  },
  // De la cadera (dentro del tronco) al tobillo.
  leg: {
    frame: "limb",
    step: 0.05,
    arcStep: 6,
    caps: [0.06, 0.015],
    // Inicio 3D (2026-11-10): de pie como la figura de «Inicio», con los muslos juntos arriba y la
    // pierna abriendose algo de la rodilla abajo, hasta el tobillo a 0,124 m del centro (antes, a
    // 0,106, casi a plomo). Los pies quedan separados, como en la imagen.
    axis: [
      { at: 0, p: [0.09, 0.95, 0] },
      { at: 1, p: [0.1, 0.8, 0.005] },
      { at: 2, p: [0.103, 0.65, 0.01] },
      { at: 3, p: [0.111, 0.47, 0.012] },
      { at: 4, p: [0.129, 0.27, -0.008] },
      { at: 5, p: [0.124, 0.058, -0.016] },
    ],
    // Humano 5 (2026-11-09): pierna del percentil 50 (ANSUR II), con el relieve incluido. Muslo
    // de 0,17-0,18 m arriba, algo mas hondo que ancho por el gluteo y los isquiotibiales, y de
    // 0,16 a media altura; rodilla de 0,11; pantorrilla de 0,12 x 0,14 con el gemelo; tobillo de
    // 0,07 entre maleolos. Inicio 3D: la silueta de «Inicio» pide la rodilla algo mas fina por
    // delante (0,11) y el tobillo mas fino (0,068).
    sections: [
      { at: 0, rx: 0.078, rz: 0.09 },
      { at: 1, rx: 0.078, rz: 0.092 },
      { at: 1.6, rx: 0.073, rz: 0.084 },
      { at: 2, rx: 0.068, rz: 0.076 },
      { at: 2.7, rx: 0.058, rz: 0.059 },
      { at: 3, rx: 0.054, rz: 0.055 },
      { at: 3.3, rx: 0.05, rz: 0.053 },
      // Facciones 3 (2026-11-10, «los gemelos de las personas no son así»): el grueso de la
      // pantorrilla esta en el tercio de arriba, justo bajo la rodilla, y desde ahi la pierna se
      // afina en una curva larga y sin escalones hasta el tobillo.
      { at: 3.55, rx: 0.054, rz: 0.056 },
      { at: 3.85, rx: 0.05, rz: 0.052 },
      { at: 4.2, rx: 0.037, rz: 0.043 },
      { at: 4.5, rx: 0.031, rz: 0.037 },
      { at: 4.8, rx: 0.029, rz: 0.037 },
      { at: 5, rx: 0.035, rz: 0.045 },
    ],
    relief: [
      // --- pierna ---
      // Angulos de la pierna izquierda: 0 dentro, 90 delante, 180 fuera, 270 detras.
      // Humano 4 (2026-11-09): una pierna atletica con piel se lee por el volumen: cuadriceps lleno
      // que cae hacia la rodilla, rotula y gemelos presentes pero redondeados. Bordes casi de
      // campana, bultos anchos que se solapan y surcos someros y anchos.
      // Inicio 3D (2026-11-10): vuelve la pierna atletica del lote «facciones» (163e36b), la de
      // «Inicio»: cuadriceps con la lagrima del vasto medial sobre la rodilla, la rotula, los
      // gemelos con la cabeza de dentro mas baja y la espinilla con el tibial anterior.
      // Recto femoral y vasto lateral: la masa de delante y de fuera del muslo.
      { at: 1.65, deg: 96, d: 0.017, sAt: [0.6, 0.55], sDeg: 28, edge: 1.5 },
      { at: 1.85, deg: 148, d: 0.018, sAt: [0.65, 0.5], sDeg: 32, edge: 1.5, tilt: -8 },
      // Vasto medial: la lagrima sobre la rodilla por dentro, redonda.
      { at: 2.55, deg: 40, d: 0.022, sAt: [0.36, 0.28], sDeg: 30, edge: 1.5, tilt: 12 },
      // Entre recto y vasto lateral, solo una sombra ancha; la cintilla iliotibial, un plano leve
      // por fuera. Sin el sartorio: su cinta en diagonal era el cable mas visible del muslo.
      { at: 2.0, deg: 122, d: -0.0025, sAt: [0.55, 0.4], sDeg: 8, tilt: -6 },
      { at: 1.9, deg: 192, d: -0.0025, sAt: [0.7, 0.55], sDeg: 14 },
      // Aductores: la masa de arriba por dentro, que se afila hacia la rodilla.
      { at: 1.1, deg: 12, d: 0.009, sAt: [0.45, 0.6], sDeg: 38, edge: 1.1 },
      // Isquiotibiales: la parte de atras del muslo llena, dos vientres que se funden arriba.
      // Espalda 5 (2026-11-10): de espaldas tienen que leerse los dos, el biceps femoral por fuera
      // y el semitendinoso por dentro, para que la luz los dibuje como el cuadriceps de delante.
      // Algo mas estrechos de contorno, con el surco entre ellos mas marcado hacia la rodilla, y
      // abriendose al bajar (cada uno hacia su lado: el de fuera va a la cabeza del perone y el de
      // dentro a la tibia), que es lo que abre el rombo de detras de la rodilla.
      // Volumen 5 (2026-11-10): cada vientre en el centro del que dibuja `backAnatomy/legs.ts` (el
      // biceps hacia x 0,12 y el semitendinoso hacia 0,065, a 0,68 m) y el surco sobre la linea
      // dibujada entre ellos, que baja abriendose hacia fuera (de x 0,072 a 0,77 m a 0,11 a 0,56:
      // giro de -10 grados). El biceps estaba en 230, sobre el vasto externo, y la luz dibujaba
      // un musculo donde la textura pinta otro.
      { at: 1.65, deg: 252, d: 0.014, sAt: [0.6, 0.5], sDeg: 22, tilt: -8, edge: 1.4 },
      { at: 1.7, deg: 298, d: 0.014, sAt: [0.6, 0.5], sDeg: 22, tilt: 6, edge: 1.4 },
      { at: 1.9, deg: 278, d: -0.0035, sAt: [0.6, 0.55], sDeg: 8, tilt: -10 },
      // Rotula: un relieve redondo; debajo, su tendon, apenas, y a los lados dos hoyos someros.
      { at: 3.0, deg: 90, d: 0.007, sAt: [0.12, 0.1], sDeg: 28, edge: 1.4 },
      { at: 3.28, deg: 90, d: 0.0035, sAt: 0.14, sDeg: 12 },
      { at: 3.25, deg: 62, d: -0.0025, sAt: 0.1, sDeg: 14 },
      { at: 3.25, deg: 118, d: -0.0025, sAt: 0.1, sDeg: 14 },
      // Detras de la rodilla, de pie y con la pierna recta, apenas un plano: un hueco hondo rodeado
      // por isquiotibiales y gemelos recogia la luz en su borde y salia como un anillo.
      // Volumen 5: en el centro del rombo dibujado (0,506 m).
      { at: 2.82, deg: 270, d: -0.0015, sAt: 0.14, sDeg: 36 },
      // Gemelos (Facciones 3): anchos y altos, que se apagan despacio hacia abajo (`sAt` de despues
      // mayor que el de antes): suben pronto bajo el hueco de la rodilla y bajan en una curva
      // larga. La cabeza de dentro es mas gruesa y baja mas que la de fuera, y llega al borde de
      // dentro: de frente la silueta es asimetrica, con la curva de dentro mas baja, como en
      // «Inicio».
      // Volumen 5 (2026-11-10): las dos cabezas, algo hacia el centro de las que dibuja
      // `backAnatomy/legs.ts` (la de dentro hacia x 0,09 y la de fuera hacia 0,15); no del todo,
      // porque su anchura es la que da la silueta de frente.
      { at: 3.58, deg: 306, d: 0.015, sAt: [0.28, 0.5], sDeg: 38, edge: 1.1, tilt: -6 },
      { at: 3.4, deg: 236, d: 0.014, sAt: [0.22, 0.36], sDeg: 34, edge: 1.1, tilt: 6 },
      // Entre las dos cabezas, una masa que cierra el valle: la espalda de la pantorrilla, redonda.
      // Espalda 5 (2026-11-10): algo menos llena, para que de espaldas se insinue la linea entre
      // las dos cabezas en la mitad de arriba, como en una pantorrilla de verdad, sin volver al tajo.
      // Volumen 5: esa linea es ya un surco del dibujo (x 0,113-0,12, de 0,45 a 0,31 m), y aqui un
      // valle somero y ancho sobre ella, para que la luz lo acompane; la masa, algo mas baja.
      { at: 3.5, deg: 270, d: 0.008, sAt: [0.24, 0.42], sDeg: 30 },
      { at: 3.4, deg: 272, d: -0.0025, sAt: [0.16, 0.2], sDeg: 7, tilt: -4 },
      // Soleo: debajo y a los lados del gemelo, mas por dentro; con la masa de detras hace la
      // curva continua hasta el Aquiles, sin bultos sueltos.
      { at: 3.95, deg: 340, d: 0.006, sAt: [0.35, 0.45], sDeg: 34 },
      { at: 3.85, deg: 205, d: 0.005, sAt: [0.35, 0.45], sDeg: 30 },
      { at: 4.0, deg: 270, d: 0.005, sAt: [0.35, 0.4], sDeg: 40 },
      // Tibial anterior lleno arriba, por fuera de la tibia; la cresta de la tibia, una curva
      // suave hacia delante en la mitad de arriba; y la cara de dentro de la tibia, algo plana.
      { at: 3.65, deg: 118, d: 0.01, sAt: [0.3, 0.6], sDeg: 26 },
      { at: 3.7, deg: 92, d: 0.005, sAt: [0.35, 0.6], sDeg: 26 },
      { at: 3.9, deg: 50, d: -0.002, sAt: 0.45, sDeg: 22 },
      // Peroneos: una franja leve por fuera.
      { at: 3.85, deg: 178, d: 0.003, sAt: [0.38, 0.42], sDeg: 22 },
      // Tendon de Aquiles: un cordon blando detras del tobillo, sin huecos a los lados (de espalda
      // se leian como dos tajos).
      { at: 4.6, deg: 270, d: 0.003, sAt: 0.22, sDeg: 16 },
      // Tobillos: el maleolo de dentro, mas alto que el de fuera. Redondos y estrechos de contorno:
      // mas anchos se juntaban delante y el tobillo salia con un brazalete.
      { at: 4.72, deg: 0, d: 0.006, sAt: 0.1, sDeg: 17, edge: 1.2 },
      { at: 4.8, deg: 180, d: 0.006, sAt: 0.1, sDeg: 17, edge: 1.2 },
    ],
  },
  // Del talon a los dedos, hacia delante; la planta, plana, en y = 0.
  foot: {
    frame: "foot",
    step: 0.05,
    arcStep: 7.5,
    caps: [0.03, 0.028],
    floor: 0,
    // Humano 5 (2026-11-09): el pie media 0,22 m, y un varon del percentil 50 calza 0,26-0,27
    // (ANSUR II); tan corto, el cuerpo parecia de puntillas sobre unos munones. Ahora mide
    // 0,26: el talon sobresale unos 0,06 m por detras del tobillo (casi una cuarta parte del
    // largo, como en el pie real) y la puntera llega mas lejos. Ancho de 0,10 en los metatarsos.
    // Inicio 3D (2026-11-10): bajo el tobillo nuevo y con la puntera algo abierta hacia fuera,
    // unos 9 grados, como los pies de «Inicio», que de frente se ven separados (0,09-0,20 m).
    axis: [
      { at: 0, p: [0.127, 0.036, -0.074] },
      { at: 1, p: [0.134, 0.032, 0.016] },
      { at: 2, p: [0.15, 0.022, 0.11] },
      { at: 3, p: [0.165, 0.016, 0.19] },
    ],
    sections: [
      { at: 0, rx: 0.037, rz: 0.045 },
      { at: 1, rx: 0.04, rz: 0.042 },
      { at: 2, rx: 0.05, rz: 0.028 },
      { at: 3, rx: 0.045, rz: 0.018 },
    ],
    relief: [
      // --- pie ---
      // Angulos del pie: 0 dentro, 90 arriba, 180 fuera, 270 la planta.
      // Empeine: alto, cae hacia los dedos y hacia fuera; con borde de campana (Humano 4), que el
      // pie es piel sobre hueso, no un musculo marcado.
      { at: 1.1, deg: 82, d: 0.011, sAt: [0.5, 0.65], sDeg: 42 },
      // Arco por dentro de la planta, y el borde de dentro del pie algo lleno sobre el.
      { at: 1.3, deg: 315, d: -0.012, sAt: 0.5, sDeg: 25 },
      { at: 1.5, deg: 8, d: 0.003, sAt: 0.55, sDeg: 22 },
      // Talon: el calcaneo asoma detras, por debajo del Aquiles.
      { at: 0.2, deg: 250, d: 0.006, sAt: 0.25, sDeg: 40, edge: 1.2 },
      // El dedo gordo, algo mas alto.
      { at: 2.7, deg: 50, d: 0.004, sAt: 0.25, sDeg: 25 },
    ],
  },
  // Dedos de la mano izquierda: salen del interior de la palma. Pulgar delante, menique detras.
  // Juntos, como en una mano relajada: los vecinos se tocan y el pliegue entre ellos lo marca la
  // sombra. Los nudillos van en arco (el del corazon, el mas bajo) y cada dedo se recoge algo mas
  // que el anterior hacia el menique.
  thumb: thumb(),
  index: finger(0.025, 0.003, 0.074, 0.0103, [5, 14, 8], -1),
  middle: finger(0.0085, 0, 0.085, 0.0107, [7, 17, 10], 0),
  ring: finger(-0.008, 0.004, 0.079, 0.0101, [9, 20, 11], 1),
  little: finger(-0.0235, 0.013, 0.062, 0.0089, [12, 23, 12], 2.5),
  // Oreja izquierda: un ovalo plano pegado al lado de la cabeza.
  ear: {
    frame: "limb",
    step: 0.25,
    arcStep: 15,
    caps: [0.012, 0.014],
    axis: [
      // Entre la ceja (1,635) y la base de la nariz (1,565), algo echada hacia atras y pegada al
      // craneo; detras del angulo de la mandibula.
      { at: 0, p: [0.074, 1.57, -0.004] },
      { at: 1, p: [0.084, 1.594, -0.011] },
      { at: 2, p: [0.082, 1.628, -0.02] },
    ],
    sections: [
      { at: 0, rx: 0.0055, rz: 0.0085 },
      { at: 1, rx: 0.0072, rz: 0.0168 },
      { at: 2, rx: 0.0065, rz: 0.013 },
    ],
    // --- cabeza y cuello (oreja) ---
    // Un ovalo liso se leia como un boton pegado a la cabeza. El borde de atras y de arriba (el
    // helix) se levanta hacia fuera y por delante queda una concavidad (la concha): con eso la
    // oreja se lee como pabellon, y el centro, que es por donde la toca un rayo de lado, no se
    // hunde.
    relief: [
      { at: 1.3, deg: 215, d: 0.0035, sAt: 0.5, sDeg: 35, edge: 1.5 },
      // Sin la concavidad de la concha (2026-11-10, cuerpo neutro): con el sombreado de cavidades
      // salia como un agujero oscuro en tres cuartos. Basta el borde levantado.
    ],
  },
};

// Zonas de la linea media, todas en el tronco. Delante y detras son zonas distintas (torax y
// espalda alta, abdomen y lumbar): la mitad de delante del contorno (0 a 180 grados) y la de
// detras, asi que se tocan de frente y de espalda. La pelvis es el centro de su franja, delante
// y detras; los lados de esa franja son las caderas (abajo, en las zonas pares).
const CENTRAL: readonly ZoneShape[] = [
  {
    zone: "head",
    position: [0, 1.62, 0],
    patches: [
      { on: "column", from: 1.54, to: 1.685, arc: [135, 405] },
      { on: "column", from: 1.685, to: 1.73 },
      // Las orejas son de la cabeza: la izquierda y su espejo.
      { on: "ear", from: 0, to: 2 },
      { on: "ear", from: 0, to: 2, mirror: true },
    ],
  },
  // El frente de la cabeza, de la barbilla a la frente.
  { zone: "face", position: [0, 1.6, 0.1], patches: [{ on: "column", from: 1.5, to: 1.685, arc: [45, 135] }] },
  // El cuello baja hasta el arranque de los trapecios y sube hasta la barbilla. Con la cabeza de
  // 0,23 m (Humano 1) la barbilla baja a 1,50: por delante el cuello acaba ahi y por los lados y
  // detras sigue hasta 1,54, bajo la mandibula y hasta la nuca, que es cuello tambien en la
  // anatomia. Asi su caja sigue midiendo 0,16 m. El umbral del ajuste al esqueleto
  // (`backend/app/pain_on_skeleton.py`) es la mitad de la zona anclada mas baja, con las alturas
  // que copia `pain_points.json` de este cuerpo (hoy el cuello). Si una zona anclada cambia de
  // alto, ese JSON tambien: lo vigila la prueba, para que el umbral no salga de un cuerpo que ya
  // no existe. Se probo un cuello de 0,14 (todo el borde a 1,52): el umbral bajaba a 70 mm y el
  // peor ancla del TAC real (75 mm) quedaba fuera, asi que la caja se mantiene en 0,16 llevando
  // el borde de detras a la nuca, donde el craneo ya se ha recogido.
  {
    zone: "neck",
    position: [0, 1.47, 0],
    patches: [
      { on: "column", from: 1.38, to: 1.5 },
      { on: "column", from: 1.5, to: 1.54, arc: [135, 405] },
    ],
  },
  { zone: "chest", position: [0, 1.28, 0.055], patches: [{ on: "column", from: 1.16, to: 1.38, arc: [0, 180] }] },
  {
    zone: "upper-back",
    position: [0, 1.28, -0.055],
    patches: [{ on: "column", from: 1.16, to: 1.38, arc: [180, 360] }],
  },
  { zone: "abdomen", position: [0, 1.06, 0.05], patches: [{ on: "column", from: 0.97, to: 1.16, arc: [0, 180] }] },
  {
    zone: "lower-back",
    position: [0, 1.06, -0.05],
    patches: [{ on: "column", from: 0.97, to: 1.16, arc: [180, 360] }],
  },
  {
    zone: "pelvis",
    position: [0, 0.9, 0],
    patches: [
      { on: "column", from: 0.78, to: 0.97, arc: [60, 120] },
      { on: "column", from: 0.78, to: 0.97, arc: [240, 300] },
    ],
  },
];

// Zonas pares, en el lado izquierdo del tripulante (+x). El derecho es su espejo.
const LEFT: readonly ZoneShape[] = [
  { zone: "shoulder", position: [0.22, 1.38, 0], patches: [{ on: "arm", from: 0, to: 1.5 }] },
  // Humano 2 (2026-11-09): con la postura en reposo el codo queda algo detras y el antebrazo y la
  // mano, delante (z), y la mano, mas larga, baja su centro; el antebrazo y la mano se han
  // recolocado en el centro de su malla (x, y tambien en `pain_points.json`). El brazo, que es
  // ancla del ajuste al esqueleto, no ha cambiado de x ni de y. Inicio 3D (2026-11-10): con el
  // brazo de «Inicio», algo mas abierto abajo y mas recogido en el hombro, el brazo pasa a x =
  // 0,235 (el centro de su malla) y el codo, el antebrazo y la mano, a los suyos.
  { zone: "upper-arm", position: [0.235, 1.2, -0.01], patches: [{ on: "arm", from: 1.5, to: 2.65 }] },
  { zone: "elbow", position: [0.272, 1.07, -0.02], patches: [{ on: "arm", from: 2.65, to: 3.3 }] },
  { zone: "forearm", position: [0.3, 0.95, 0.005], patches: [{ on: "arm", from: 3.3, to: 4.85 }] },
  {
    zone: "hand",
    position: [0.35, 0.775, 0.06],
    // La palma es el final del brazo; los dedos, tramos aparte metidos en ella.
    patches: [
      { on: "arm", from: 4.85, to: 6 },
      { on: "thumb", from: 0, to: 3 },
      { on: "index", from: 0, to: 4 },
      { on: "middle", from: 0, to: 4 },
      { on: "ring", from: 0, to: 4 },
      { on: "little", from: 0, to: 4 },
    ],
  },
  // El lado de la franja de la pelvis y el arranque de la pierna.
  {
    zone: "hip",
    position: [0.125, 0.9, 0],
    patches: [
      { on: "column", from: 0.78, to: 0.97, arc: [-60, 60] },
      { on: "leg", from: 0, to: 0.9 },
    ],
  },
  { zone: "thigh", position: [0.11, 0.66, 0], patches: [{ on: "leg", from: 0.9, to: 2.65 }] },
  { zone: "knee", position: [0.11, 0.47, 0], patches: [{ on: "leg", from: 2.65, to: 3.35 }] },
  { zone: "lower-leg", position: [0.125, 0.27, 0], patches: [{ on: "leg", from: 3.35, to: 4.8 }] },
  {
    zone: "foot",
    position: [0.14, 0.025, 0.04],
    patches: [
      { on: "leg", from: 4.8, to: 5 },
      { on: "foot", from: 0, to: 3 },
    ],
  },
];

/** El sector de un trozo del tronco visto en espejo: el angulo a se vuelve 180 - a. */
function mirrorPatch(patch: Patch): Patch {
  if (patch.on !== "column" || patch.arc === undefined) return patch;
  return { ...patch, arc: [180 - patch.arc[1], 180 - patch.arc[0]] };
}

export const BODY: readonly ZoneShape[] = [
  ...CENTRAL,
  ...LEFT.map((item) => ({ ...item, zone: `${item.zone}-left`, side: "left" as const })),
  ...LEFT.map((item) => ({
    ...item,
    zone: `${item.zone}-right`,
    side: "right" as const,
    position: [-item.position[0], item.position[1], item.position[2]] as const,
    patches: item.patches.map(mirrorPatch),
  })),
];

// ---- Geometria ----

/** Superficie de una zona, lista para un `BufferGeometry`: posiciones, normales e indices. */
export interface Surface {
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
}

/**
 * Paso del contorno del tronco en grados. Sus sectores empiezan y acaban en multiplos de el.
 *
 * Rejilla afinada (2026-11-09, con `tilt` y `edge`): con 5 grados en el tronco y 0,1 de paso en
 * brazo y pierna, un surco de 5 a 8 grados (esternon, cuadros del abdomen) o un borde marcado caia
 * entre dos columnas y se veia romo. Ahora 2,5 grados en el tronco, y paso 0,05 con 6 grados en
 * brazo y pierna (el pie, 0,05 y 7,5). El total de triangulos lo vigila la prueba de ligereza
 * (`bodyModel.test.ts`), que es donde vive el tope.
 */
export const ARC_STEP = 2.5;

type V = [number, number, number];

/** Interpolacion de Hermite con tangentes de diferencias finitas (Catmull-Rom no uniforme). */
function hermite(knots: readonly number[], values: readonly (readonly number[])[], t: number): number[] {
  const n = knots.length;
  const first = knots[0]!;
  const last = knots[n - 1]!;
  const x = Math.min(Math.max(t, first), last);
  let i = 0;
  while (i < n - 2 && x > knots[i + 1]!) i += 1;
  const tangent = (k: number): number[] => {
    const lo = Math.max(k - 1, 0);
    const hi = Math.min(k + 1, n - 1);
    const span = knots[hi]! - knots[lo]!;
    return values[hi]!.map((v, axis) => (v - values[lo]![axis]!) / span);
  };
  const h = knots[i + 1]! - knots[i]!;
  const s = (x - knots[i]!) / h;
  const h00 = 2 * s ** 3 - 3 * s ** 2 + 1;
  const h10 = s ** 3 - 2 * s ** 2 + s;
  const h01 = -2 * s ** 3 + 3 * s ** 2;
  const h11 = s ** 3 - s ** 2;
  const m0 = tangent(i);
  const m1 = tangent(i + 1);
  return values[i]!.map(
    (v, axis) => h00 * v + h10 * h * m0[axis]! + h01 * values[i + 1]![axis]! + h11 * h * m1[axis]!,
  );
}

const sub = (a: V, b: V): V => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a: V, b: V): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: V, b: V): V => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
const scale = (a: V, k: number): V => [a[0] * k, a[1] * k, a[2] * k];
const unit = (a: V): V => scale(a, 1 / (Math.hypot(...a) || 1));

/** Diferencia entre dos angulos en grados, en [-180, 180). */
function angleGap(a: number, b: number): number {
  return ((((a - b) % 360) + 540) % 360) - 180;
}

/** Lo que solo depende de `at`: centro, ejes, semiejes y los bultos que llegan a esa altura. */
interface Ring {
  c: V;
  across: V;
  depth: V;
  /** Semiejes ya redondeados en los remates. */
  rx: number;
  rz: number;
  /** Semiejes sin redondear: el bulto se mide contra ellos y el remate lo encoge con todo. */
  baseRx: number;
  baseRz: number;
  /** Bultos con efecto en esta altura: angulo, empuje ya pesado por el eje, anchura en grados. */
  bumps: { deg: number; d: number; sDeg: number }[];
  /**
   * Bultos con giro o borde que llegan a esta altura. No se pueden pesar por el eje de antemano
   * (con giro el peso depende del eje y del angulo a la vez): se guarda lo que solo depende de la
   * fila —recorrido hasta el centro del bulto y anchuras en metros— y `point` termina la cuenta.
   */
  shaped: ShapedRow[];
}

/** Lo que una fila sabe de un bulto con forma (ver `Bump.tilt` y `Bump.edge`). */
interface ShapedRow {
  deg: number;
  d: number;
  /** Metros recorridos por el eje desde el centro del bulto hasta esta fila (con signo). */
  u: number;
  /** Metros de contorno por radian en esta fila, al angulo del bulto: pasa grados a metros. */
  metresPerRad: number;
  /** Anchuras en metros: a lo largo del eje girado (antes, despues) y a lo ancho. */
  below: number;
  above: number;
  across: number;
  cos: number;
  sin: number;
  edge: number;
}

/** Un bulto con forma, con lo que no cambia de fila a fila ya calculado. */
interface ShapedBump {
  deg: number;
  d: number;
  sDeg: number;
  /** Recorrido en metros hasta el centro del bulto. */
  centre: number;
  /** `sAt` pasado a metros: lo recorrido por el eje entre el centro y `at` -/+ `sAt`. */
  below: number;
  above: number;
  cos: number;
  sin: number;
  edge: number;
}

/** Sin giro ni borde, el bulto va por la cuenta de siempre (separable, pesada por fila). */
function isShaped(bump: Bump): boolean {
  return (bump.tilt ?? 0) !== 0 || (bump.edge ?? 1) !== 1;
}

/** Un tramo listo para muestrear: eje, secciones y largo recorrido hasta cada punto. */
class Tube {
  private readonly knots: number[];
  private readonly points: number[][];
  private readonly sectionKnots: number[];
  private readonly sectionValues: number[][];
  private readonly arcAt: number[] = [];
  private readonly arcLength: number[] = [];
  private readonly relief: Bump[];
  private readonly shapedRelief: ShapedBump[];
  readonly start: number;
  readonly end: number;
  readonly length: number;

  constructor(
    readonly sweep: Sweep,
    private readonly mirrored: boolean,
  ) {
    this.knots = sweep.axis.map((point) => point.at);
    this.points = sweep.axis.map(({ p }) => [mirrored ? -p[0] : p[0], p[1], p[2]]);
    this.sectionKnots = sweep.sections.map((section) => section.at);
    this.sectionValues = sweep.sections.map((section) => [section.rx, section.rz]);
    // En el tronco cada bulto fuera de la linea media va tambien a su angulo espejo (180 - a):
    // asi el relieve es simetrico por construccion. El espejo invierte el sentido del contorno,
    // asi que un bulto girado va al espejo con el giro opuesto; y uno girado de la linea media
    // tambien se duplica, porque solo no seria simetrico; entonces cada copia lleva la mitad del
    // empuje, para que en el centro suba `d` y no el doble.
    const all = (sweep.relief ?? []).flatMap((bump): Bump[] => {
      if (sweep.frame !== "level") return [bump];
      const midline = Math.abs(angleGap(bump.deg, 180 - bump.deg)) <= 1e-9;
      const tilt = bump.tilt ?? 0;
      if (midline && tilt === 0) return [bump];
      if (!midline) return [bump, { ...bump, deg: 180 - bump.deg, ...(tilt !== 0 ? { tilt: -tilt } : {}) }];
      const half = { ...bump, d: bump.d / 2 };
      return [half, { ...half, tilt: -tilt }];
    });
    this.relief = all.filter((bump) => !isShaped(bump));
    const shaped = all.filter(isShaped);
    this.start = this.knots[0]!;
    this.end = this.knots[this.knots.length - 1]!;
    // Largo de arco a lo largo del eje, para los remates redondeados (en metros, no en `at`).
    const samples = 512;
    let total = 0;
    let previous = this.centre(this.start);
    for (let k = 0; k <= samples; k += 1) {
      const at = this.start + ((this.end - this.start) * k) / samples;
      const here = this.centre(at);
      total += Math.hypot(...sub(here, previous));
      previous = here;
      this.arcAt.push(at);
      this.arcLength.push(total);
    }
    this.length = total;
    this.shapedRelief = shaped.map((bump) => this.shape(bump));
  }

  /**
   * Prepara un bulto con forma. Se comprueba aqui lo que, mal escrito, haria desaparecer el bulto
   * o toda la zona sin aviso (un `NaN` en el giro vuelve `NaN` cada punto del tramo).
   */
  private shape(bump: Bump): ShapedBump {
    const where = `bulto en ${bump.at}/${bump.deg}`;
    const edge = bump.edge ?? 1;
    const tilt = bump.tilt ?? 0;
    const [below, above] = typeof bump.sAt === "number" ? [bump.sAt, bump.sAt] : bump.sAt;
    if (!(Number.isFinite(edge) && edge >= 1)) throw new Error(`${where}: edge debe ser >= 1`);
    if (!Number.isFinite(tilt)) throw new Error(`${where}: tilt no es un numero`);
    if (!(bump.at >= this.start && bump.at <= this.end)) throw new Error(`${where}: fuera del tramo`);
    if (!(below > 0 && above > 0 && bump.sDeg > 0)) throw new Error(`${where}: anchura no positiva`);
    // `sAt` a metros con el recorrido real a cada lado del centro, para que el bulto acabe donde
    // acabaria sin forma aunque el eje no avance igual en todo el tramo. Si la anchura se sale del
    // tramo, con la escala local del centro.
    const centre = this.travelled(bump.at);
    const h = (this.end - this.start) * 1e-3;
    const a = Math.max(bump.at - h, this.start);
    const b = Math.min(bump.at + h, this.end);
    const perAt = (this.travelled(b) - this.travelled(a)) / (b - a);
    const metres = (sigma: number, sign: number): number => {
      const to = bump.at + sign * sigma;
      return to >= this.start && to <= this.end ? sign * (this.travelled(to) - centre) : sigma * perAt;
    };
    const radians = (tilt * Math.PI) / 180;
    return {
      deg: bump.deg,
      d: bump.d,
      sDeg: bump.sDeg,
      centre,
      below: metres(below, -1),
      above: metres(above, 1),
      cos: Math.cos(radians),
      sin: Math.sin(radians),
      edge,
    };
  }

  centre(at: number): V {
    return hermite(this.knots, this.points, at) as V;
  }

  /** Recorrido en metros desde el principio del tramo hasta `at`. */
  travelled(at: number): number {
    const span = this.end - this.start;
    const k = Math.min(Math.max(((at - this.start) / span) * (this.arcAt.length - 1), 0), this.arcAt.length - 1);
    const lo = Math.floor(k);
    const hi = Math.min(lo + 1, this.arcAt.length - 1);
    return this.arcLength[lo]! + (this.arcLength[hi]! - this.arcLength[lo]!) * (k - lo);
  }

  /** Direccion del eje en `at`. */
  tangent(at: number): V {
    const e = (this.end - this.start) * 1e-4;
    const a = Math.max(at - e, this.start);
    const b = Math.min(at + e, this.end);
    return unit(sub(this.centre(b), this.centre(a)));
  }

  /** Ejes de la seccion: `across` lleva rx y `depth` lleva rz. */
  private frame(at: number): { across: V; depth: V } {
    if (this.sweep.frame === "level") return { across: [1, 0, 0], depth: [0, 0, 1] };
    const reference: V = this.sweep.frame === "foot" ? [0, 1, 0] : [0, 0, 1];
    const t = this.tangent(at);
    const depth = unit(sub(reference, scale(t, dot(reference, t))));
    const across = cross(t, depth);
    const turn = this.twist(at);
    if (turn === 0) return { across, depth };
    // Girar el marco `turn` grados lleva el angulo 0 hacia el 90 (ver `Sweep.twist`).
    const [c, s] = [Math.cos((turn * Math.PI) / 180), Math.sin((turn * Math.PI) / 180)];
    return {
      across: [across[0] * c + depth[0] * s, across[1] * c + depth[1] * s, across[2] * c + depth[2] * s],
      depth: [depth[0] * c - across[0] * s, depth[1] * c - across[1] * s, depth[2] * c - across[2] * s],
    };
  }

  /** Giro del marco en `at`, en grados; en el tramo derecho, el opuesto (espejo). */
  private twist(at: number): number {
    const knots = this.sweep.twist;
    if (knots === undefined || knots.length === 0) return 0;
    let deg = knots[knots.length - 1]!.deg;
    if (at <= knots[0]!.at) deg = knots[0]!.deg;
    else {
      for (let k = 0; k < knots.length - 1; k += 1) {
        const [a, b] = [knots[k]!, knots[k + 1]!];
        if (at > b.at) continue;
        // Paso suave (smoothstep): sin pendiente en los nudos y sin pasarse de ninguno.
        const s = (at - a.at) / (b.at - a.at);
        deg = a.deg + (b.deg - a.deg) * s * s * (3 - 2 * s);
        break;
      }
    }
    return this.mirrored ? -deg : deg;
  }

  /** Factor de los remates: 0 en la punta, 1 donde acaba el redondeo. */
  private rounding(at: number): number {
    const s = this.travelled(at);
    const [head, tail] = this.sweep.caps;
    let factor = 1;
    if (head > 0 && s < head) factor = Math.sqrt(Math.max(0, 1 - ((head - s) / head) ** 2));
    const left = this.length - s;
    if (tail > 0 && left < tail) factor *= Math.sqrt(Math.max(0, 1 - ((tail - left) / tail) ** 2));
    return factor;
  }

  /**
   * Se guarda por `at` porque cada fila tiene decenas de puntos y sus normales piden otros cinco
   * cada uno; asi los bultos se filtran y se pesan por el eje una vez por fila.
   */
  private readonly rings = new Map<number, Ring>();

  private ring(at: number): Ring {
    let ring = this.rings.get(at);
    if (ring === undefined) {
      const [rx, rz] = hermite(this.sectionKnots, this.sectionValues, at) as [number, number];
      const k = this.rounding(at);
      const bumps: Ring["bumps"] = [];
      for (const bump of this.relief) {
        const [below, above] = typeof bump.sAt === "number" ? [bump.sAt, bump.sAt] : bump.sAt;
        const sigma = at < bump.at ? below : above;
        const u = (at - bump.at) / sigma;
        if (Math.abs(u) > 4) continue;
        bumps.push({ deg: bump.deg, d: bump.d * Math.exp(-0.5 * u * u), sDeg: bump.sDeg });
      }
      const shaped: ShapedRow[] = [];
      if (this.shapedRelief.length > 0) {
        const s = this.travelled(at);
        for (const bump of this.shapedRelief) {
          // Metros de contorno por radian al angulo del bulto, en la seccion sin redondear: la
          // derivada de la elipse (rx cos, rz sin). En una seccion aplanada (la palma) cambia mucho
          // alrededor del contorno, y con el radio medio el giro dejaria de ser el pedido.
          const phi = (bump.deg * Math.PI) / 180;
          const metresPerRad = Math.hypot(rx * Math.sin(phi), rz * Math.cos(phi));
          const row: ShapedRow = {
            deg: bump.deg,
            d: bump.d,
            u: s - bump.centre,
            metresPerRad,
            below: bump.below,
            above: bump.above,
            across: ((bump.sDeg * Math.PI) / 180) * metresPerRad,
            cos: bump.cos,
            sin: bump.sin,
            edge: bump.edge,
          };
          // Hasta donde llega por el eje la elipse de radio 4 (en anchuras) del bulto girado:
          // fuera de ella el bulto no empuja nada en esta fila.
          const reach = 4 * Math.hypot(Math.max(row.below, row.above) * row.cos, row.across * row.sin);
          if (Math.abs(row.u) <= reach) shaped.push(row);
        }
      }
      ring = {
        c: this.centre(at),
        ...this.frame(at),
        rx: rx * k,
        rz: rz * k,
        baseRx: rx,
        baseRz: rz,
        bumps,
        shaped,
      };
      this.rings.set(at, ring);
    }
    return ring;
  }

  /** Punto de la superficie en `at` y al angulo `degrees` del contorno. */
  point(at: number, degrees: number): V {
    const { c, across, depth, rx, rz, baseRx, baseRz, bumps, shaped } = this.ring(at);
    const angle = (((degrees % 360) + 360) % 360) * (Math.PI / 180);
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    // El tramo derecho es el izquierdo visto en espejo: su angulo a es el 180 - a del izquierdo.
    const relief = this.mirrored ? 180 - degrees : degrees;
    let push = 0;
    for (const bump of bumps) {
      const gap = angleGap(relief, bump.deg) / bump.sDeg;
      if (Math.abs(gap) < 4) push += bump.d * Math.exp(-0.5 * gap * gap);
    }
    for (const bump of shaped) {
      // Las dos distancias en metros, giradas al marco del bulto, y la distancia normalizada.
      const v = ((angleGap(relief, bump.deg) * Math.PI) / 180) * bump.metresPerRad;
      const along = bump.u * bump.cos + v * bump.sin;
      const side = -bump.u * bump.sin + v * bump.cos;
      const sigma = along < 0 ? bump.below : bump.above;
      const r2 = (along / sigma) ** 2 + (side / bump.across) ** 2;
      if (r2 < 16) push += bump.d * Math.exp(-0.5 * (bump.edge === 1 ? r2 : r2 ** bump.edge));
    }
    // El empuje va en la direccion del radio de la elipse y se mide en metros sobre la seccion
    // sin redondear, asi que en la punta de un remate se apaga con ella.
    const radius = Math.hypot(baseRx * cos, baseRz * sin);
    const grow = radius > 1e-9 ? Math.max(0.2, 1 + push / radius) : 1;
    const a = rx * cos * grow;
    const b = rz * sin * grow;
    const y = c[1] + across[1] * a + depth[1] * b;
    const floor = this.sweep.floor;
    return [
      c[0] + across[0] * a + depth[0] * b,
      floor !== undefined && y < floor ? floor : y,
      c[2] + across[2] * a + depth[2] * b,
    ];
  }

  /** Normal hacia fuera, por diferencias: identica en el borde que comparten dos zonas. */
  normal(at: number, degrees: number): V {
    const e = (this.end - this.start) * 1e-4;
    const a = Math.max(at - e, this.start);
    const b = Math.min(at + e, this.end);
    const along = sub(this.point(b, degrees), this.point(a, degrees));
    const around = sub(this.point(at, degrees + 0.05), this.point(at, degrees - 0.05));
    const n = cross(around, along);
    const p = this.point(at, degrees);
    const radial = sub(p, this.centre(at));
    if (Math.hypot(...n) < 1e-12 || Math.hypot(...radial) < 1e-6) {
      // En la punta de un remate el contorno es un punto: la normal es la del eje.
      const t = this.tangent(at);
      return at - this.start < this.end - at ? scale(t, -1) : t;
    }
    return unit(dot(n, radial) < 0 ? scale(n, -1) : n);
  }

  /**
   * Suelta las filas guardadas. Con la malla ya hecha no las vuelve a pedir nadie, y con la
   * rejilla fina son muchas (cada fila y las de sus normales, a `at` +/- e).
   */
  forget(): void {
    this.rings.clear();
  }

  /** Valores de `at` donde se muestrea entre `from` y `to`: la rejilla comun del tramo. */
  samples(from: number, to: number): number[] {
    const out = [from];
    // En los remates la curvatura es mayor: la rejilla se hace tres veces mas fina.
    const fine = this.sweep.step / 3;
    // `at` = principio + k pasos finos, por producto y no por suma: el mismo valor exacto empiece
    // donde empiece el trozo, asi que dos zonas vecinas casan punto a punto.
    for (let k = Math.max(1, Math.floor((from - this.start) / fine)); ; k += 1) {
      const at = this.start + k * fine;
      if (at >= to - 1e-9) break;
      if (at <= from + 1e-9) continue;
      const s = this.travelled(at);
      const inCap = s < this.sweep.caps[0] || this.length - s < this.sweep.caps[1];
      const onGrid = k % 3 === 0;
      const fineRange = this.sweep.fine;
      const inFine = fineRange !== undefined && at >= fineRange[0] && at <= fineRange[1];
      if (inCap || onGrid || inFine) out.push(at);
    }
    out.push(to);
    return out;
  }
}

const tubes = new Map<string, Tube>();

function tubeOf(name: SweepName, mirrored: boolean): Tube {
  // El tronco es uno solo; los demas tramos tienen uno por lado.
  const flip = name !== "column" && mirrored;
  const key = `${name}:${flip ? "right" : "left"}`;
  let tube = tubes.get(key);
  if (tube === undefined) {
    tube = new Tube(SWEEPS[name], flip);
    tubes.set(key, tube);
  }
  return tube;
}

/**
 * Punto de la superficie de un tramo, sin pasar por la rejilla. Lo usa la prueba que fija la
 * geometria: asi se puede afinar la rejilla sin perder la comprobacion bit a bit del relieve.
 */
export function surfacePoint(name: SweepName, mirrored: boolean, at: number, degrees: number): Vec3 {
  return tubeOf(name, mirrored).point(at, degrees);
}

/**
 * La superficie de un tramo cualquiera, fuera de `SWEEPS`: para probar el relieve (giro, borde,
 * espejo) con un tramo de ensayo sin tocar el cuerpo.
 */
export function sweepSurface(sweep: Sweep, mirrored = false): (at: number, degrees: number) => Vec3 {
  const tube = new Tube(sweep, mirrored);
  return (at, degrees) => tube.point(at, degrees);
}

/** Angulos del contorno de un sector, en multiplos de `step`, extremos incluidos. */
function angles(arc: readonly [number, number], step: number): number[] {
  const out: number[] = [];
  const count = Math.round((arc[1] - arc[0]) / step);
  for (let k = 0; k <= count; k += 1) out.push(arc[0] + k * step);
  return out;
}

const surfaces = new Map<string, Surface>();

/** La superficie de una zona: sus trozos de tramo, cosidos en una sola malla. */
export function surfaceOf(item: ZoneShape): Surface {
  const cached = surfaces.get(item.zone);
  if (cached !== undefined) return cached;
  const positions: number[] = [];
  const normals: number[] = [];
  const indices: number[] = [];
  for (const patch of item.patches) {
    const tube = tubeOf(patch.on, item.side === "right" || patch.mirror === true);
    const rows = tube.samples(patch.from, patch.to);
    const columns = angles(patch.arc ?? [0, 360], tube.sweep.arcStep ?? ARC_STEP);
    const base = positions.length / 3;
    for (const at of rows) {
      for (const degrees of columns) {
        positions.push(...tube.point(at, degrees));
        normals.push(...tube.normal(at, degrees));
      }
    }
    const width = columns.length;
    const vertex = (index: number): V => [
      positions[index * 3]!,
      positions[index * 3 + 1]!,
      positions[index * 3 + 2]!,
    ];
    const triangle = (a: number, b: number, c: number) => {
      const face = cross(sub(vertex(b), vertex(a)), sub(vertex(c), vertex(a)));
      // En la punta de un remate un lado del cuadro mide cero: ese triangulo no existe.
      if (Math.hypot(...face) < 1e-12) return;
      const facing: V = [normals[a * 3]!, normals[a * 3 + 1]!, normals[a * 3 + 2]!];
      // Se orienta cada triangulo hacia su normal: el espejo de un tramo invierte el giro.
      if (dot(face, facing) + dot(face, [normals[c * 3]!, normals[c * 3 + 1]!, normals[c * 3 + 2]!]) >= 0) {
        indices.push(a, b, c);
      } else {
        indices.push(a, c, b);
      }
    };
    for (let i = 0; i < rows.length - 1; i += 1) {
      for (let j = 0; j < width - 1; j += 1) {
        const a = base + i * width + j;
        const b = base + (i + 1) * width + j;
        triangle(a, b, b + 1);
        triangle(a, b + 1, a + 1);
      }
    }
    tube.forget();
  }
  const surface = {
    positions: Float32Array.from(positions),
    normals: Float32Array.from(normals),
    indices: Uint32Array.from(indices),
  };
  surfaces.set(item.zone, surface);
  return surface;
}

export interface Box {
  min: Vec3;
  max: Vec3;
}

/** Caja que contiene la superficie de la zona. Sirve para comprobar encuadre y lados. */
export function bounds(item: ZoneShape): Box {
  const { positions } = surfaceOf(item);
  const min: V = [Infinity, Infinity, Infinity];
  const max: V = [-Infinity, -Infinity, -Infinity];
  for (let k = 0; k < positions.length; k += 1) {
    const axis = k % 3;
    min[axis] = Math.min(min[axis]!, positions[k]!);
    max[axis] = Math.max(max[axis]!, positions[k]!);
  }
  return { min, max };
}

/**
 * Coordenadas de un clic en el rango [-1, 1] que usa el raycaster, con y hacia arriba.
 * En la pantalla la y crece hacia abajo: sin invertirla, un clic en el pie tocaria la cabeza.
 */
export function toNormalized(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
): { x: number; y: number } {
  return {
    x: ((clientX - rect.left) / rect.width) * 2 - 1,
    y: -(((clientY - rect.top) / rect.height) * 2 - 1),
  };
}

// Distancia en pixeles por debajo de la cual soltar el puntero es un clic y no un giro.
// Sin ella, girar el cuerpo para ver la espalda marcaba la zona donde se solto.
export const CLICK_TOLERANCE_PX = 5;

export function isClick(
  down: { x: number; y: number },
  up: { x: number; y: number },
): boolean {
  return Math.hypot(up.x - down.x, up.y - down.y) <= CLICK_TOLERANCE_PX;
}
