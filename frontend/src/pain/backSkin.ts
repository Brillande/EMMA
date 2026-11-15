import { BODY_HEIGHT } from "./bodyModel";

/**
 * La espalda del cuerpo térmico, dibujada a mano (Ellande, 2026-11-10: «falta darle detalle [a la
 * espalda] como en frente»).
 *
 * El frente lleva proyectado el render de «Inicio» (`thermalSkin.ts`): colores de cámara térmica y
 * el contorno de cada músculo en líneas claras. Ese render solo existe de frente; la espalda tenía
 * la copia borrosa del frente y unas líneas sacadas de la cavidad del relieve, y se veía más pobre.
 * Aquí se pinta la espalda como si existiera ese render. Es adorno, como el frente (§2.5 de
 * `compliance/hmi-state-of-the-art.md`): el verde y el amarillo no dicen nada; lo que es dato (la
 * zona marcada) se pinta aparte con la paleta.
 *
 * Por qué hay músculos y huesos y no solo trazos (Ellande, 2026-11-10, sobre la espalda de solo
 * trazos: «no veo huesos definidos, solo veo manchurrones; fíjate en el frente»). En el frente cada
 * músculo es un VOLUMEN con su color: el vientre más claro y templado, los bordes más fríos, y entre
 * músculo y músculo un surco verde oscuro o azul. Los contornos son pocos, gruesos y con un brillo
 * amarillo claro teñido del tono de debajo, y los huesos son crestas claras y nítidas. Una espalda de
 * manchas de calor grandes y suaves con muchas líneas blancas finas encima no tiene nada de eso.
 *
 * Este módulo es puro (sin WebGL ni lienzo): formato, proyección y rasterizado, para poder probarlo y
 * para que `scripts/back-preview.mjs` saque la textura a PNG sin navegador. El dibujo vive en
 * `backAnatomy/`: el calor en `heat.ts`, y los músculos, huesos y trazos de cada región en
 * `torso.ts`, `arms.ts` y `legs.ts`.
 *
 * ## Coordenadas
 *
 * **Metros, en las del cuerpo**, proyectadas de espaldas sobre el plano x/y del modelo
 * (`bodyModel.ts`): `x` es la x del modelo (+x es la IZQUIERDA del tripulante, que vista de espaldas
 * cae a la izquierda de la pantalla) e `y` es la altura (0 en las plantas, 1,73 en la coronilla). Lo
 * que se dibuja en (x, y) cae en el punto de la espalda que tiene esa x y esa altura, sin importar lo
 * hondo que esté. Por eso los costados reciben el dibujo estirado: lo útil va en lo que se ve de
 * espaldas, no en el canto. Toda curva (contorno, cresta o trazo) es una Catmull-Rom centrípeta que
 * pasa por todos sus puntos: bastan pocos, la curva se redondea sola.
 *
 * ## Las capas, en el orden en que se pintan
 *
 * 1. **Fondo, `BackHeat`**: el campo térmico que queda entre regiones. Un nivel de 0 (azul hondo) a 1
 *    (rojo) en la rampa de colores de «Inicio» (`THERMAL_RAMP`), igual en todo el cuerpo (`base`)
 *    más manchas gaussianas (`spots`). Cada mancha suma `heat` en su centro `at` (negativo enfría),
 *    con radios `radius` = [horizontal, vertical] en metros: a esa distancia queda un 37 % (e^−1).
 *    Las manchas se suman; el nivel se recorta a [0, 1]. Guía de la rampa: 0,1 azul de miembros, 0,3
 *    cian, 0,45-0,55 verde, 0,65 amarillo verdoso, 0,75 amarillo, 0,85 naranja.
 * 2. **Músculos, `BackMuscle`** (el relleno): cada uno TAPA el fondo dentro de su contorno con un
 *    degradado propio, de `edge` en el borde a `belly` en el vientre (niveles de la rampa). El
 *    vientre está, por defecto, en lo más hondo de la forma, lo más lejos del borde: un músculo
 *    alargado lo tiene a lo largo de su eje y uno redondo en su centro. Con `shape` se dice dónde: un
 *    punto, o una línea de puntos (el eje de un músculo fusiforme). El perfil es de cojín: sube
 *    deprisa desde el borde y se aplana en el vientre, que es lo que da volumen. Los músculos se
 *    pintan en el orden de la lista; el que va después tapa al de antes donde se pisan.
 * 3. **Surcos**: cada músculo lleva por su contorno una franja oscura y fría (`groove`, de 0 a 1; por
 *    defecto 1; 0 la quita), de ancho total `grooveWidth` (por defecto `MUSCLE_LOOK.grooveWidth`): el
 *    hueco entre músculos, verde oscuro o azul según lo que tenga debajo. Dos músculos vecinos que
 *    comparten borde comparten surco (se toma el más hondo, no se suman). Para que el borde sea de
 *    verdad el mismo, los dos llevan los mismos puntos del borde común y densos (cada centímetro:
 *    `smoothCurve(linea, false, 0.01)` los da): con pocos, cada curva se dobla distinto entre ellos
 *    según sus otros vecinos y salen dos brillos paralelos (ejemplo: los gemelos, `legs.ts`).
 * 4. **Huesos, `BackBone`**: una cresta clara, nítida y estrecha (`width`, 4-7 mm), más brillante que
 *    un contorno y casi sin halo, con una sombra fina desplazada `shadow` metros (por defecto, un
 *    ancho hacia abajo: luz de arriba) para que «salga» de la piel. En un hueso vertical (el cúbito)
 *    la sombra hacia abajo queda tapada por la cresta: dale `shadow: [0.005, 0]`, hacia un lado.
 *    `closed` para un relieve redondo (el olécranon, un maléolo).
 * 5. **Contornos y trazos**: el contorno de cada músculo (`rim`, brillo de 0 a 1, por defecto
 *    `MUSCLE_LOOK.rim`; 0 lo quita; núcleo de ancho `rimWidth`) y los `BackStroke` sueltos, para lo
 *    que no es un volumen (un tendón, un pliegue, la separación entre dos haces). Se aclaran como las
 *    líneas del frente: hacia un brillo claro teñido del tono de debajo, algo más templado (amarillo
 *    verdoso sobre verde, cian claro sobre azul), nunca a blanco puro.
 *
 * Los surcos, los huesos y los contornos se tiñen con el nivel del RELLENO (fondo más músculos), no
 * con lo que les deja la capa de antes: un contorno sobre un surco frío sigue siendo amarillo claro.
 *
 * ## Cómo escribir un músculo
 *
 * ```ts
 * // Infraespinoso: la fosa bajo la espina de la escápula. Contorno cerrado, en cualquier sentido.
 * {
 *   outline: [[0.082, 1.355], [0.15, 1.385], [0.17, 1.345], [0.14, 1.285], [0.105, 1.245], [0.084, 1.29]],
 *   belly: 0.66, // amarillo verdoso en el vientre
 *   edge: 0.42, // verde algo frío en el borde
 *   shape: [[0.118, 1.325]], // opcional: el vientre, algo arriba y por dentro
 * }
 * ```
 *
 * Reglas prácticas: `belly` de 0,1 a 0,25 por encima de `edge` (menos no se ve; más parece una diana);
 * `edge` algo por debajo del fondo de alrededor, para que el borde se lea frío. Los vecinos se
 * dibujan tocándose o pisándose un poco: si queda hueco entre ellos, se ve el fondo. Los contornos
 * van gruesos y pocos: un detalle dentro del músculo es mejor otro músculo o un `BackStroke` tenue
 * (`strength` 0,4-0,6) que otro contorno a plena luz.
 *
 * ## Cómo escribir un hueso
 *
 * ```ts
 * // Espina de la escápula: de la raíz, en el borde medial, sube hacia fuera hasta el acromion.
 * { points: [[0.08, 1.365], [0.12, 1.382], [0.19, 1.402]], width: 0.006 }
 * // Olécranon: un relieve redondo, con la sombra hacia fuera y abajo.
 * { points: [[0.27, 1.077], [0.284, 1.059], [0.265, 1.05]], width: 0.005, closed: true, shadow: [0.003, -0.004] }
 * ```
 *
 * ## Trazos sueltos (`BackStroke`)
 *
 * - `points`: los puntos de paso; con dos es una recta.
 * - `width`: ancho del núcleo claro, en metros. En el frente las líneas miden 1-1,5 píxeles de una
 *   imagen de 5,9 mm por píxel, unos 6-9 mm: `0.007` es un buen valor por defecto, `0.009` para un
 *   borde principal y `0.005` para un detalle. Más finas que 4 mm se pierden al reducir la textura.
 * - `glow`: radio del halo suave alrededor, en metros (por defecto, 2 veces `width`); el halo se
 *   apaga del todo a 1,6 veces ese radio.
 * - `closed`: cierra la curva (del último punto vuelve al primero, también suave).
 * - `strength`: brillo del trazo de 0 a 1 (por defecto 1): para líneas secundarias más tenues.
 *
 * Para dibujar los dos lados a la vez, `bilateral` (trazos), `bilateralMuscles`, `bilateralBones` y
 * `bilateralSpots` (manchas) añaden el espejo en x de lo que se les da. Lo que va sobre el eje
 * (x = 0) se escribe fuera de ellas, o saldría doble.
 */

/** Un punto del dibujo: x del modelo (+x izquierda del tripulante) y altura, en metros. */
export type BackPoint = readonly [x: number, y: number];

export interface BackStroke {
  readonly points: readonly BackPoint[];
  /** Ancho del núcleo claro, en metros. */
  readonly width: number;
  /** Radio del halo, en metros (por defecto 2 × `width`). */
  readonly glow?: number;
  /** Curva cerrada. */
  readonly closed?: boolean;
  /** Brillo de 0 a 1 (por defecto 1). */
  readonly strength?: number;
}

/** Un músculo con volumen: relleno de `edge` en el borde a `belly` en el vientre. */
export interface BackMuscle {
  /** Contorno cerrado, en metros (Catmull-Rom; sin repetir el primer punto al final). */
  readonly outline: readonly BackPoint[];
  /** Nivel de la rampa en el vientre, el más templado. */
  readonly belly: number;
  /** Nivel de la rampa en el borde, más frío. */
  readonly edge: number;
  /** Dónde está el vientre: un punto o una línea de puntos. Por defecto, lo más lejos del borde. */
  readonly shape?: readonly BackPoint[];
  /** Hondura del surco del contorno, de 0 (sin surco) a 1 (por defecto 1). */
  readonly groove?: number;
  /** Ancho total del surco, en metros (por defecto `MUSCLE_LOOK.grooveWidth`). */
  readonly grooveWidth?: number;
  /** Brillo del contorno, de 0 (sin contorno) a 1 (por defecto `MUSCLE_LOOK.rim`). */
  readonly rim?: number;
  /** Ancho del núcleo del contorno, en metros (por defecto `MUSCLE_LOOK.rimWidth`). */
  readonly rimWidth?: number;
}

/** Un hueso bajo la piel: una cresta clara y nítida con una sombra fina a un lado. */
export interface BackBone {
  readonly points: readonly BackPoint[];
  /** Ancho de la cresta, en metros. */
  readonly width: number;
  /** Relieve cerrado (un óvalo). */
  readonly closed?: boolean;
  /** Desplazamiento de la sombra, en metros (por defecto `[0, -width]`: hacia abajo). */
  readonly shadow?: BackPoint;
  /** Brillo de 0 a 1 (por defecto 1). */
  readonly strength?: number;
}

export interface HeatSpot {
  /** Centro, en metros. */
  readonly at: BackPoint;
  /** Radios [horizontal, vertical], en metros: a esa distancia del centro queda un 37 %. */
  readonly radius: readonly [rx: number, ry: number];
  /** Lo que suma en el centro, en niveles de la rampa (negativo enfría). */
  readonly heat: number;
}

export interface BackHeat {
  /** Nivel de todo el cuerpo antes de las manchas: el azul de los miembros. */
  readonly base: number;
  readonly spots: readonly HeatSpot[];
}

export interface BackArt {
  readonly heat: BackHeat;
  /** Se pintan en este orden: el de después tapa al de antes. */
  readonly muscles?: readonly BackMuscle[];
  readonly bones?: readonly BackBone[];
  readonly strokes: readonly BackStroke[];
}

/**
 * La rampa térmica de «Inicio», de frío a caliente: los tonos de `BODY_ONE` agrupados por matiz cada
 * 10° (de 220°, azul, a 0°, rojo), con la mediana de los píxeles saturados y claros de cada grupo
 * (saturación ≥ 0,75, valor ≥ 0,55). La prueba comprueba que cada tono está en la imagen. Repartidos
 * a partes iguales entre 0 y 1: el nivel 0,5 es el verde del abdomen y el 1, el rojo del corazón.
 */
export const THERMAL_RAMP: readonly string[] = [
  "#1b52b2",
  "#1d74ce",
  "#1e9ee4",
  "#17b9dd",
  "#1ad1d1",
  "#1adfbd",
  "#21e5a1",
  "#1ee480",
  "#20e45e",
  "#24e141",
  "#2cdc2d",
  "#44e121",
  "#5ee21c",
  "#7ce112",
  "#99e210",
  "#bdde10",
  "#dcda10",
  "#f0cb11",
  "#faac16",
  "#f68614",
  "#f15d0c",
  "#ef340a",
  "#d00701",
];

/**
 * Lo que cubre la textura trasera. Propia y no la del frente (`THERMAL_PROJECTION`, 152×310 px a
 * 5,9 mm por píxel): a esa resolución una línea de 4 mm no cabe. Aquí, 512×1024 a unos 1,8 mm por
 * píxel, la misma escala en x y en y. La columna central es el eje del cuerpo (x = 0) y, como en la
 * del frente, la columna crece con x: vista de espaldas, la imagen sale en espejo (el guion de
 * vista previa la voltea para enseñarla como se ve en la app).
 */
export const BACK_PROJECTION = {
  width: 512,
  height: 1024,
  /** Altura de la fila de arriba y de la de abajo (bordes, no centros), en metros. */
  top: BODY_HEIGHT + 0.06,
  bottom: -0.03,
} as const;

export type BackProjection = { readonly [K in keyof typeof BACK_PROJECTION]: number };

/** Metros por píxel de la textura (los mismos en x y en y). */
export function metersPerPixel(projection: BackProjection = BACK_PROJECTION): number {
  return (projection.top - projection.bottom) / projection.height;
}

/** La proyección como dos rectas, u = u0 + uScale·x y v = v0 + vScale·y, como `thermalCoefficients`. */
export function backCoefficients(projection: BackProjection = BACK_PROJECTION): {
  u0: number;
  uScale: number;
  v0: number;
  vScale: number;
} {
  const perMeter = 1 / metersPerPixel(projection);
  // v = 0 es la fila de arriba: la textura se sube sin voltear, como la del frente.
  return {
    u0: 0.5,
    uScale: perMeter / projection.width,
    v0: (projection.top * perMeter) / projection.height,
    vScale: -perMeter / projection.height,
  };
}

/** De un punto del cuerpo (x, altura, en m) a (u, v) de la textura trasera, en [0, 1]. */
export function projectBack(x: number, y: number, projection: BackProjection = BACK_PROJECTION): [number, number] {
  const { u0, uScale, v0, vScale } = backCoefficients(projection);
  return [u0 + uScale * x, v0 + vScale * y];
}

/** El centro del píxel (columna, fila) en metros. */
function pixelToBody(column: number, row: number, projection: BackProjection): [number, number] {
  const step = metersPerPixel(projection);
  return [(column + 0.5 - projection.width / 2) * step, projection.top - (row + 0.5) * step];
}

/** De metros del cuerpo a píxeles de la textura (columna, fila; continuos, sin redondear). */
function bodyToPixel([x, y]: BackPoint, projection: BackProjection): [number, number] {
  const step = metersPerPixel(projection);
  return [x / step + projection.width / 2, (projection.top - y) / step];
}

const mirror = (points: readonly BackPoint[]): BackPoint[] => points.map(([x, y]) => [-x, y] as const);

/** Añade el espejo en x de cada trazo: se dibuja un lado y salen los dos. */
export function bilateral(strokes: readonly BackStroke[]): BackStroke[] {
  return strokes.flatMap((stroke) => [stroke, { ...stroke, points: mirror(stroke.points) }]);
}

/** Añade el espejo en x de cada músculo (contorno y vientre). */
export function bilateralMuscles(muscles: readonly BackMuscle[]): BackMuscle[] {
  return muscles.flatMap((muscle) => [
    muscle,
    {
      ...muscle,
      outline: mirror(muscle.outline),
      ...(muscle.shape === undefined ? {} : { shape: mirror(muscle.shape) }),
    },
  ]);
}

/** Añade el espejo en x de cada hueso (cresta y lado de la sombra). */
export function bilateralBones(bones: readonly BackBone[]): BackBone[] {
  return bones.flatMap((bone) => [
    bone,
    {
      ...bone,
      points: mirror(bone.points),
      ...(bone.shadow === undefined ? {} : { shadow: [-bone.shadow[0], bone.shadow[1]] as const }),
    },
  ]);
}

/** Añade el espejo en x de cada mancha. */
export function bilateralSpots(spots: readonly HeatSpot[]): HeatSpot[] {
  return spots.flatMap((spot) => [spot, { ...spot, at: [-spot.at[0], spot.at[1]] as const }]);
}

/**
 * Catmull-Rom centrípeta: una curva suave que pasa por todos los puntos sin hacer bucles ni pasarse
 * en las curvas cerradas (la uniforme los hace cuando los puntos van desigualmente espaciados).
 * `step` es la distancia aproximada entre muestras, en las mismas unidades que los puntos.
 */
export function smoothCurve(points: readonly BackPoint[], closed: boolean, step: number): BackPoint[] {
  const count = points.length;
  if (count < 2) return points.slice();
  const at = (i: number): BackPoint => {
    if (closed) return points[((i % count) + count) % count]!;
    if (i < 0) {
      // Extremo libre: un punto fantasma en la prolongación del primer tramo.
      const [a, b] = [points[0]!, points[1]!];
      return [2 * a[0] - b[0], 2 * a[1] - b[1]];
    }
    if (i >= count) {
      const [a, b] = [points[count - 1]!, points[count - 2]!];
      return [2 * a[0] - b[0], 2 * a[1] - b[1]];
    }
    return points[i]!;
  };
  const out: BackPoint[] = [points[0]!];
  const spans = closed ? count : count - 1;
  for (let i = 0; i < spans; i += 1) {
    const [p0, p1, p2, p3] = [at(i - 1), at(i), at(i + 1), at(i + 2)];
    const knot = (a: BackPoint, b: BackPoint) => Math.max(Math.sqrt(Math.hypot(b[0] - a[0], b[1] - a[1])), 1e-6);
    const t1 = knot(p0, p1);
    const t2 = t1 + knot(p1, p2);
    const t3 = t2 + knot(p2, p3);
    const lerp = (a: BackPoint, b: BackPoint, ta: number, tb: number, t: number): BackPoint => {
      const w = (t - ta) / (tb - ta);
      return [a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w];
    };
    const samples = Math.max(1, Math.ceil(Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / step));
    for (let k = 1; k <= samples; k += 1) {
      // Barry-Goldman: tres interpolaciones encajadas, de t1 (en p1) a t2 (en p2).
      const t = t1 + ((t2 - t1) * k) / samples;
      const a1 = lerp(p0, p1, 0, t1, t);
      const a2 = lerp(p1, p2, t1, t2, t);
      const a3 = lerp(p2, p3, t2, t3, t);
      const b1 = lerp(a1, a2, 0, t2, t);
      const b2 = lerp(a2, a3, t1, t3, t);
      out.push(k === samples ? p2 : lerp(b1, b2, t1, t2, t));
    }
  }
  return out;
}

/** El nivel de la rampa (0-1) en un punto del cuerpo: `base` más las manchas, recortado. */
export function heatLevel(heat: BackHeat, x: number, y: number): number {
  let level = heat.base;
  for (const { at, radius, heat: amount } of heat.spots) {
    const dx = (x - at[0]) / radius[0];
    const dy = (y - at[1]) / radius[1];
    const d2 = dx * dx + dy * dy;
    if (d2 < 9) level += amount * Math.exp(-d2);
  }
  return Math.max(0, Math.min(1, level));
}

const RAMP_RGB = THERMAL_RAMP.map((hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)));

/** El color (0-255, sRGB) de un nivel de la rampa, interpolando entre tonos vecinos. */
export function rampColor(level: number): [number, number, number] {
  const t = Math.max(0, Math.min(1, level)) * (RAMP_RGB.length - 1);
  const i = Math.min(RAMP_RGB.length - 2, Math.floor(t));
  const w = t - i;
  const [a, b] = [RAMP_RGB[i]!, RAMP_RGB[i + 1]!];
  return [0, 1, 2].map((c) => a[c]! + (b[c]! - a[c]!) * w) as [number, number, number];
}

/**
 * El brillo de las líneas, medido en las del render de «Inicio» (perfiles de color a través de sus
 * contornos): no son blancas, sino el mismo tono de debajo, aclarado. Sobre el azul, cian claro
 * (160,245,255 sobre 34,175,205: muy aclarado); sobre el verde, verde amarillento vivo (161,255,75
 * sobre 140,232,25: poco aclarado); sobre el amarillo, amarillo claro (255,218,88 sobre 255,177,33);
 * y sobre el rojo del corazón, amarillo (255,196,76), no rosa. Por eso el tono apenas se templa
 * (`warm`) pero nunca pasa del amarillo (`warmest`), y se aclara más cuanto más frío (`white`).
 * El núcleo toma ese brillo y el halo un poco.
 */
export const STROKE_LOOK = {
  /** Cuánto se acerca el núcleo al brillo (0 nada, 1 del todo). */
  core: 1,
  /** Cuánto el halo en su centro. */
  halo: 0.35,
  /** Suavizado del borde del núcleo, en píxeles. */
  feather: 0.8,
  /** Cuánto más templado que el relleno es el brillo, en niveles de la rampa. */
  warm: 0.05,
  /** Hasta dónde se templa como mucho: el amarillo de la rampa. */
  warmest: 0.72,
  /** Cuánto se aclara hacia el blanco (0 nada, 1 blanco) sobre el azul (nivel 0) y del amarillo arriba (nivel ≥ 0,7). */
  whiteCold: 0.63,
  whiteWarm: 0.3,
} as const;

/** Músculos: anchos por defecto y cómo se ve el surco. */
export const MUSCLE_LOOK = {
  /**
   * Ancho total del surco, en metros. Bastante más que el núcleo del contorno (7 mm), que lo tapa
   * por el centro: lo que se ve del surco es lo que asoma a cada lado del brillo.
   */
  grooveWidth: 0.024,
  /** Cuánto enfría el surco en su centro, en niveles de la rampa. */
  grooveCool: 0.16,
  /** Cuánto oscurece el surco en su centro (0 nada, 1 negro): el surco del frente, 85,208,13 entre
   * vientres de 140,232,25, o 12,143,189 sobre el azul. */
  grooveDark: 0.35,
  /** Brillo del contorno por defecto. */
  rim: 1,
  /** Núcleo del contorno, en metros: de los gruesos del frente. */
  rimWidth: 0.007,
  /** Radio del halo del contorno, en anchos de su núcleo. */
  rimGlow: 1,
} as const;

/** Huesos: una cresta más clara y más nítida que un contorno, con su sombra. */
export const BONE_LOOK = {
  /** Cuánto más se aclara la cresta que un contorno: lo que le queda hasta el blanco, en parte. */
  lift: 0.4,
  /** Halo: radio en anchos de la cresta y cuánto aclara en su centro. Poco: el hueso es nítido. */
  glow: 0.7,
  halo: 0.35,
  /** Cuánto oscurece la sombra (0 nada, 1 negro). */
  shadow: 0.5,
} as const;

/**
 * Un campo de líneas (0-1) en cada píxel, núcleo y halo por separado, el máximo de todas: sirve para
 * los trazos, los contornos, los surcos (solo el halo, que es gaussiano) y los huesos. Cada línea se
 * muestrea en tramos de dos píxeles y cada tramo solo recorre su caja. Con `parts` se calcula solo
 * el núcleo (la sombra de un hueso) o solo el halo (un surco); la otra parte sale vacía.
 */
export function strokeField(
  strokes: readonly BackStroke[],
  projection: BackProjection = BACK_PROJECTION,
  parts: "both" | "core" | "halo" = "both",
): { core: Float32Array; halo: Float32Array } {
  const { width, height } = projection;
  const wantCore = parts !== "halo";
  const wantHalo = parts !== "core";
  const core = new Float32Array(wantCore ? width * height : 0);
  const halo = new Float32Array(wantHalo ? width * height : 0);
  const step = metersPerPixel(projection);
  for (const stroke of strokes) {
    if (stroke.points.length === 0) continue;
    const strength = Math.max(0, Math.min(1, stroke.strength ?? 1));
    if (strength === 0) continue;
    const radius = stroke.width / step / 2;
    const glow = Math.max((stroke.glow ?? stroke.width * 2) / step, 0.5);
    // Muestras cada dos píxeles: la distancia se mide al tramo recto entre dos, y la cuerda se
    // separa de la curva menos de una décima de píxel en las curvas de este dibujo.
    const curve = smoothCurve(stroke.points, stroke.closed ?? false, step * 2).map((p) => bodyToPixel(p, projection));
    if (curve.length === 1) curve.push(curve[0]!);
    // El halo se corta a 1,6 radios (queda un 8 %), restando ese resto para que llegue a cero sin
    // escalón: cada tramo recorre una caja pequeña y el rasterizado no se dispara con muchos trazos.
    const halfReach = wantHalo ? HALO_REACH * glow : 0;
    const reach = Math.max(wantCore ? radius + STROKE_LOOK.feather : 0, halfReach);
    const tail = Math.exp(-HALO_REACH * HALO_REACH);
    for (let s = 1; s < curve.length; s += 1) {
      const [ax, ay] = curve[s - 1]!;
      const [bx, by] = curve[s]!;
      const dx = bx - ax;
      const dy = by - ay;
      const length2 = dx * dx + dy * dy;
      const x0 = Math.max(0, Math.floor(Math.min(ax, bx) - reach));
      const x1 = Math.min(width - 1, Math.ceil(Math.max(ax, bx) + reach));
      const y0 = Math.max(0, Math.floor(Math.min(ay, by) - reach));
      const y1 = Math.min(height - 1, Math.ceil(Math.max(ay, by) + reach));
      for (let row = y0; row <= y1; row += 1) {
        for (let column = x0; column <= x1; column += 1) {
          const px = column + 0.5 - ax;
          const py = row + 0.5 - ay;
          const t = length2 === 0 ? 0 : Math.max(0, Math.min(1, (px * dx + py * dy) / length2));
          const ex = px - t * dx;
          const ey = py - t * dy;
          const distance2 = ex * ex + ey * ey;
          if (distance2 > reach * reach) continue;
          const distance = Math.sqrt(distance2);
          const i = row * width + column;
          // Núcleo: lleno hasta el radio, con el borde suavizado; nunca más fino que un píxel.
          const inner = 1 - smooth(radius - STROKE_LOOK.feather, radius + STROKE_LOOK.feather, distance);
          if (wantCore) {
            const c = strength * Math.min(1, inner * Math.min(1, radius * 2 + 0.3));
            if (c > core[i]!) core[i] = c;
          }
          if (distance < halfReach) {
            const h = (strength * (Math.exp(-distance2 / (glow * glow)) - tail)) / (1 - tail);
            if (h > halo[i]!) halo[i] = h;
          }
        }
      }
    }
  }
  return { core, halo };
}

/** Hasta dónde llega el halo, en radios de halo (`glow`). */
const HALO_REACH = 1.6;

/** Lado, en píxeles, de la rejilla en la que se calcula el calor antes de interpolarlo. */
const HEAT_CELL = 4;

function smooth(from: number, to: number, value: number): number {
  const t = Math.max(0, Math.min(1, (value - from) / (to - from)));
  return t * t * (3 - 2 * t);
}

/**
 * El nivel del fondo en cada píxel. El calor es suave (manchas de centímetros): se calcula cada
 * `HEAT_CELL` píxeles y se interpola, dieciséis veces menos exponenciales que píxel a píxel, sin
 * diferencia a la vista.
 */
function heatField(heat: BackHeat, projection: BackProjection): Float32Array {
  const { width, height } = projection;
  const cells = [Math.ceil(width / HEAT_CELL) + 1, Math.ceil(height / HEAT_CELL) + 1] as const;
  const coarse = new Float32Array(cells[0] * cells[1]);
  for (let j = 0; j < cells[1]; j += 1) {
    for (let k = 0; k < cells[0]; k += 1) {
      const [x, y] = pixelToBody(k * HEAT_CELL - 0.5, j * HEAT_CELL - 0.5, projection);
      coarse[j * cells[0] + k] = heatLevel(heat, x, y);
    }
  }
  const levels = new Float32Array(width * height);
  for (let row = 0; row < height; row += 1) {
    const fy = (row + 0.5) / HEAT_CELL;
    const j = Math.min(cells[1] - 2, Math.floor(fy));
    const wy = fy - j;
    for (let column = 0; column < width; column += 1) {
      const fx = (column + 0.5) / HEAT_CELL;
      const k = Math.min(cells[0] - 2, Math.floor(fx));
      const wx = fx - k;
      const at = (dk: number, dj: number) => coarse[(j + dj) * cells[0] + k + dk]!;
      levels[row * width + column] =
        (at(0, 0) * (1 - wx) + at(1, 0) * wx) * (1 - wy) + (at(0, 1) * (1 - wx) + at(1, 1) * wx) * wy;
    }
  }
  return levels;
}

/**
 * Transformada de distancia euclídea exacta en una dimensión (Felzenszwalb y Huttenlocher, 2012):
 * en `out`, la distancia al cuadrado de cada celda a la celda con `f` = 0 más cercana, en O(n).
 */
function distance1d(f: Float64Array, n: number, out: Float64Array, v: Int32Array, z: Float64Array): void {
  let k = 0;
  v[0] = 0;
  z[0] = -Infinity;
  z[1] = Infinity;
  // Dónde se cortan las parábolas de q y de p (z[0] = −∞ para el bucle siempre).
  const cut = (q: number, p: number) => (f[q]! + q * q - (f[p]! + p * p)) / (2 * q - 2 * p);
  for (let q = 1; q < n; q += 1) {
    let s = cut(q, v[k]!);
    while (s <= z[k]!) {
      k -= 1;
      s = cut(q, v[k]!);
    }
    k += 1;
    v[k] = q;
    z[k] = s;
    z[k + 1] = Infinity;
  }
  k = 0;
  for (let q = 0; q < n; q += 1) {
    while (z[k + 1]! < q) k += 1;
    const p = v[k]!;
    out[q] = (q - p) * (q - p) + f[p]!;
  }
}

/** Distancia de un punto a una polilínea (un solo punto vale), en las unidades de los puntos. */
function distanceToPolyline(px: number, py: number, line: readonly (readonly [number, number])[]): number {
  if (line.length === 1) return Math.hypot(px - line[0]![0], py - line[0]![1]);
  let best = Infinity;
  for (let s = 1; s < line.length; s += 1) {
    const [ax, ay] = line[s - 1]!;
    const [bx, by] = line[s]!;
    const dx = bx - ax;
    const dy = by - ay;
    const length2 = dx * dx + dy * dy;
    const t = length2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length2));
    best = Math.min(best, Math.hypot(px - ax - t * dx, py - ay - t * dy));
  }
  return best;
}

/**
 * Pinta un músculo sobre `levels`: rasteriza su contorno (par-impar por filas), mide la distancia
 * de cada píxel de dentro al borde con la transformada de distancia y pone el degradado de `edge` a
 * `belly`. El relleno tapa lo de debajo; el borde de un píxel queda bajo el surco y el contorno.
 */
function paintMuscle(levels: Float32Array, muscle: BackMuscle, projection: BackProjection): void {
  const { width, height } = projection;
  if (muscle.outline.length < 3) return;
  const outline = smoothCurve(muscle.outline, true, metersPerPixel(projection)).map((p) => bodyToPixel(p, projection));
  const xs = outline.map(([x]) => x);
  const ys = outline.map(([, y]) => y);
  // Caja con un píxel de margen fuera: así su borde siempre es «fuera» para la transformada. Sin
  // recortar a la textura (recortada, perdería ese margen en un músculo que llegue al borde y la
  // distancia se dispararía); lo que cae fuera de la textura no se escribe.
  const c0 = Math.floor(Math.min(...xs)) - 1;
  const c1 = Math.ceil(Math.max(...xs)) + 1;
  const r0 = Math.floor(Math.min(...ys)) - 1;
  const r1 = Math.ceil(Math.max(...ys)) + 1;
  const boxW = c1 - c0 + 1;
  const boxH = r1 - r0 + 1;
  if (boxW < 3 || boxH < 3) return;
  const inside = new Uint8Array(boxW * boxH);
  const crossings: number[] = [];
  for (let r = 0; r < boxH; r += 1) {
    const yc = r0 + r + 0.5;
    crossings.length = 0;
    for (let e = 0; e < outline.length; e += 1) {
      const [ax, ay] = outline[e]!;
      const [bx, by] = outline[(e + 1) % outline.length]!;
      if (ay <= yc !== by <= yc) crossings.push(ax + ((yc - ay) * (bx - ax)) / (by - ay));
    }
    crossings.sort((a, b) => a - b);
    for (let k = 0; k + 1 < crossings.length; k += 2) {
      const from = Math.max(0, Math.ceil(crossings[k]! - 0.5 - c0));
      const to = Math.min(boxW - 1, Math.floor(crossings[k + 1]! - 0.5 - c0));
      for (let c = from; c <= to; c += 1) inside[r * boxW + c] = 1;
    }
  }
  // Transformada de distancia en dos pasadas (columnas y luego filas) sobre la caja.
  const big = 1e12;
  const grid = new Float64Array(boxW * boxH);
  for (let i = 0; i < grid.length; i += 1) grid[i] = inside[i] ? big : 0;
  const longest = Math.max(boxW, boxH);
  const f = new Float64Array(longest);
  const out = new Float64Array(longest);
  const v = new Int32Array(longest);
  const z = new Float64Array(longest + 1);
  for (let c = 0; c < boxW; c += 1) {
    for (let r = 0; r < boxH; r += 1) f[r] = grid[r * boxW + c]!;
    distance1d(f, boxH, out, v, z);
    for (let r = 0; r < boxH; r += 1) grid[r * boxW + c] = out[r]!;
  }
  let deepest = 0;
  for (let r = 0; r < boxH; r += 1) {
    for (let c = 0; c < boxW; c += 1) f[c] = grid[r * boxW + c]!;
    distance1d(f, boxW, out, v, z);
    for (let c = 0; c < boxW; c += 1) {
      // Del centro del píxel de dentro al borde, no al centro del primer píxel de fuera.
      const d = inside[r * boxW + c] ? Math.max(0, Math.sqrt(out[c]!) - 0.5) : 0;
      grid[r * boxW + c] = d;
      if (d > deepest) deepest = d;
    }
  }
  if (deepest === 0) return;
  const shape = muscle.shape?.map((p) => bodyToPixel(p, projection));
  for (let r = 0; r < boxH; r += 1) {
    if (r0 + r < 0 || r0 + r >= height) continue;
    for (let c = 0; c < boxW; c += 1) {
      if (!inside[r * boxW + c] || c0 + c < 0 || c0 + c >= width) continue;
      const d = grid[r * boxW + c]!;
      // 0 en el borde y 1 en el vientre: lo más hondo de la forma o, con `shape`, sobre ella.
      let t: number;
      if (shape === undefined || shape.length === 0) {
        t = d / deepest;
      } else {
        const toBelly = distanceToPolyline(c0 + c + 0.5, r0 + r + 0.5, shape);
        t = d + toBelly === 0 ? 1 : d / (d + toBelly);
      }
      // Cojín: sube deprisa desde el borde y se aplana en el vientre.
      const profile = t * (2 - t);
      levels[(r0 + r) * width + c0 + c] = Math.max(0, Math.min(1, muscle.edge + (muscle.belly - muscle.edge) * profile));
    }
  }
}

/** El contorno de un músculo como trazo cerrado (para el brillo). */
function rimOf(muscle: BackMuscle): BackStroke {
  return {
    points: muscle.outline,
    closed: true,
    width: muscle.rimWidth ?? MUSCLE_LOOK.rimWidth,
    // Halo corto (un ancho, no dos como un trazo suelto): uno largo aclararía el surco de al lado.
    glow: (muscle.rimWidth ?? MUSCLE_LOOK.rimWidth) * MUSCLE_LOOK.rimGlow,
    strength: muscle.rim ?? MUSCLE_LOOK.rim,
  };
}

/** El surco de un músculo como trazo cerrado: solo cuenta su halo, gaussiano, de ancho total `grooveWidth`. */
function grooveOf(muscle: BackMuscle): BackStroke {
  const total = muscle.grooveWidth ?? MUSCLE_LOOK.grooveWidth;
  // El halo llega a 1,6 radios por cada lado: radio = ancho total / 3,2.
  return { points: muscle.outline, closed: true, width: 0, glow: total / (2 * HALO_REACH), strength: muscle.groove ?? 1 };
}

/** La cresta de un hueso como trazo, con poco halo. */
function crestOf(bone: BackBone): BackStroke {
  return {
    points: bone.points,
    width: bone.width,
    glow: bone.width * BONE_LOOK.glow,
    closed: bone.closed ?? false,
    strength: bone.strength ?? 1,
  };
}

/** La sombra de un hueso: la misma cresta, desplazada y algo más ancha. */
function shadowOf(bone: BackBone): BackStroke {
  const [dx, dy] = bone.shadow ?? [0, -bone.width];
  return {
    points: bone.points.map(([x, y]) => [x + dx, y + dy] as const),
    width: bone.width * 1.1,
    closed: bone.closed ?? false,
    strength: bone.strength ?? 1,
  };
}

/** Una tabla de 1024 niveles con el color de la rampa, o el brillo teñido de cada nivel. */
function levelTable(color: (level: number) => readonly number[]): Float32Array {
  const table = new Float32Array(LEVEL_STEPS * 3 + 3);
  for (let s = 0; s <= LEVEL_STEPS; s += 1) table.set(color(s / LEVEL_STEPS), s * 3);
  return table;
}
const LEVEL_STEPS = 1023;

/**
 * El brillo teñido sobre un nivel (`STROKE_LOOK`): el tono algo más templado sin pasar del amarillo,
 * aclarado hacia el blanco más cuanto más frío. `lift` lo aclara aún más (los huesos).
 */
export function glintColor(level: number, lift = 0): [number, number, number] {
  const { warm, warmest, whiteCold, whiteWarm } = STROKE_LOOK;
  const tone = Math.min(level + warm, warmest);
  const cold = Math.max(0, Math.min(1, level / warmest));
  const white = whiteCold + (whiteWarm - whiteCold) * cold;
  const share = white + (1 - white) * lift;
  return rampColor(tone).map((c) => c + (255 - c) * share) as [number, number, number];
}

/**
 * La textura trasera en RGBA (sRGB, opaca), fila 0 arriba, en el orden de capas de la cabecera:
 * fondo, músculos, surcos, huesos y contornos con trazos. Hecho una vez, perezoso (`BodyMap.tsx`).
 */
export function rasterizeBack(art: BackArt, projection: BackProjection = BACK_PROJECTION): Uint8Array {
  const { width, height } = projection;
  const muscles = art.muscles ?? [];
  const bones = art.bones ?? [];
  // 1-2. Relleno: el fondo y, encima, los músculos en orden.
  const fill = heatField(art.heat, projection);
  for (const muscle of muscles) paintMuscle(fill, muscle, projection);
  // 3-5. Los campos de las capas de encima.
  const groove = strokeField(muscles.map(grooveOf), projection, "halo").halo;
  const crest = strokeField(bones.map(crestOf), projection);
  const shadow = strokeField(bones.map(shadowOf), projection, "core").core;
  const lines = strokeField([...muscles.map(rimOf), ...art.strokes], projection);
  const ramp = levelTable(rampColor);
  const glint = levelTable((level) => glintColor(level));
  const boneGlint = levelTable((level) => glintColor(level, BONE_LOOK.lift));
  const out = new Uint8Array(width * height * 4);
  const entry = (level: number) => Math.round(Math.max(0, Math.min(1, level)) * LEVEL_STEPS) * 3;
  for (let i = 0; i < width * height; i += 1) {
    const level = fill[i]!;
    const tint = entry(level);
    // Surco: más frío en la rampa y más oscuro.
    const g = groove[i]!;
    const cooled = entry(level - g * MUSCLE_LOOK.grooveCool);
    const darken = (1 - g * MUSCLE_LOOK.grooveDark) * (1 - shadow[i]! * BONE_LOOK.shadow);
    const bone = Math.max(crest.core[i]!, crest.halo[i]! * BONE_LOOK.halo);
    // Sobre un hueso, los contornos y trazos solo cubren lo que el hueso deja: su brillo es más
    // tenue que la cresta y, mezclado encima, la apagaría donde un contorno pasa cerca.
    const light = Math.max(STROKE_LOOK.core * lines.core[i]!, STROKE_LOOK.halo * lines.halo[i]!) * (1 - bone);
    for (let c = 0; c < 3; c += 1) {
      let value = ramp[cooled + c]! * darken;
      value += (boneGlint[tint + c]! - value) * bone;
      value += (glint[tint + c]! - value) * light;
      out[i * 4 + c] = Math.round(value);
    }
    out[i * 4 + 3] = 255;
  }
  return out;
}
