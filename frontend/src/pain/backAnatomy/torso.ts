import {
  type BackBone,
  type BackMuscle,
  type BackPoint,
  type BackStroke,
  bilateral,
  bilateralBones,
  bilateralMuscles,
  smoothCurve,
} from "../backSkin";

/**
 * El tronco por detrás y la nuca: músculos con volumen, huesos con cresta y unos pocos trazos de
 * detalle, como el frente del render de «Inicio» si existiera de espaldas. Formato en `backSkin.ts`
 * (metros, x del modelo, +x izquierda del tripulante); vista previa con
 * `npm run preview:back -- --out <png> --scale 2 --crop -0.3,0.85,0.3,1.65` (`--regions` para ver
 * los contornos y los vientres).
 *
 * Por qué volúmenes y no líneas (Ellande, 2026-11-10, sobre la espalda de solo trazos: «no veo
 * huesos definidos, solo veo manchurrones; fíjate en el frente»): en el frente cada músculo es un
 * cojín de color con su surco frío alrededor y los huesos son crestas nítidas. Aquí, igual: el
 * trapecio en sus tres porciones, el infraespinoso, los redondos, el dorsal ancho, los erectores, el oblicuo externo y la fascia lumbar (un plano casi liso); y como
 * huesos, el occipital, las apófisis espinosas de C7 a L5, la escápula (espina, borde medial y
 * ángulo inferior), la cresta ilíaca y los bordes del sacro.
 *
 * Las cotas salen de la silueta de la malla de espaldas (vista previa, rejilla de 0,1 m), no de un
 * atlas a escala: cuello ±0,065 m a 1,50 m, hombro ±0,19 a 1,40, axila ±0,18 a 1,24, cintura ±0,14
 * a 1,04 y cadera ±0,15 a 0,98. Las vértebras se reparten entre C7 (1,47 m, la que sobresale en la
 * base del cuello) y L5 (0,97 m, a la altura de la cresta ilíaca), con T12 a 1,12: ahí acaba la V
 * del trapecio y empieza el rombo de la fascia toracolumbar.
 *
 * Se dibuja el lado izquierdo (+x) y `bilateralMuscles`/`bilateralBones` sacan el derecho; lo que
 * va sobre el eje (las apófisis) se escribe aparte. Los dos erectores (y las dos mitades del
 * trapecio) acaban a 5-8 mm del eje: sus surcos se juntan ahí y marcan el surco de la columna, con
 * las apófisis encima como crestas. Lo de las nalgas es de `legs.ts` y lo del brazo, deltoides
 * posterior incluido, de `arms.ts`: lo del tronco acaba en su borde (`ARM_EDGE`).
 */

/** Un borde común con puntos cada centímetro: los dos músculos que lo comparten, un solo surco. */
const dense = (points: readonly BackPoint[]): BackPoint[] =>
  smoothCurve(points, false, 0.01);
const reversed = (points: readonly BackPoint[]): BackPoint[] =>
  [...points].reverse();

/** Junta tramos de contorno sin repetir el punto de unión. */
function chain(...parts: readonly (readonly BackPoint[])[]): BackPoint[] {
  const out: BackPoint[] = [];
  for (const point of parts.flat()) {
    const last = out[out.length - 1];
    if (
      last !== undefined &&
      Math.hypot(point[0] - last[0], point[1] - last[1]) < 1e-4
    )
      continue;
    out.push(point);
  }
  return out;
}

// --- Bordes comunes (lado izquierdo, +x) ---

/** Espina de la escápula: de la raíz, en el borde medial, al acromion. Hueso, y borde entre el
 * trapecio medio (encima) y el infraespinoso (debajo). */
const SPINE_OF_SCAPULA: readonly BackPoint[] = [
  [0.08, 1.366],
  [0.11, 1.377],
  [0.15, 1.39],
  [0.19, 1.402],
];
const SPINE_EDGE = dense(SPINE_OF_SCAPULA);

/** Entre el trapecio superior y el medio: de C7 sale hacia el acromion. */
const TRAP_UPPER_MIDDLE = dense([
  [0.006, 1.468],
  [0.045, 1.452],
  [0.1, 1.432],
  [0.15, 1.416],
  [0.19, 1.404],
]);

/** Entre el trapecio medio y el inferior: de T4 a la raíz de la espina. */
const TRAP_MIDDLE_LOWER = dense([
  [0.006, 1.33],
  [0.045, 1.348],
  [0.08, 1.366],
]);

/** La V del trapecio: de la raíz de la espina baja hacia dentro hasta T12. */
const TRAP_V = dense([
  [0.08, 1.366],
  [0.074, 1.33],
  [0.06, 1.29],
  [0.04, 1.23],
  [0.022, 1.17],
  [0.006, 1.12],
]);

/**
 * Borde del brazo: el de dentro del deltoides posterior y de la cabeza larga del tríceps
 * (`arms.ts`), con sus mismos puntos. Los músculos del tronco que llegan al brazo (infraespinoso,
 * redondos, dorsal) acaban aquí, en el mismo surco, y no se meten debajo: los contornos se pintan
 * encima de todos los rellenos y un borde tapado seguiría viéndose.
 */
const ARM_EDGE = dense([
  [0.168, 1.382],
  [0.174, 1.358],
  [0.18, 1.33],
  [0.19, 1.302],
  [0.186, 1.262],
]);
/** El tramo del borde del brazo entre dos alturas, de arriba abajo. */
const armEdge = (top: number, bottom: number): BackPoint[] =>
  ARM_EDGE.filter(([, y]) => y <= top && y >= bottom);

/** Borde de fuera del infraespinoso: deja el brazo bajo el acromion y baja al ángulo inferior. */
const INFRA_LATERAL = dense([
  [0.174, 1.358],
  [0.165, 1.33],
  [0.152, 1.3],
  [0.127, 1.262],
  [0.104, 1.24],
]);

/** Entre el redondo menor (encima) y el mayor (debajo), hacia el húmero. */
const TERES_SPLIT = dense([
  [0.152, 1.3],
  [0.17, 1.308],
  [0.184, 1.316],
]);

/** Borde de abajo del redondo mayor, que sigue el de arriba del dorsal: del ángulo a la axila. */
const TERES_LOWER = dense([
  [0.1, 1.226],
  [0.13, 1.234],
  [0.16, 1.252],
  [0.188, 1.276],
]);

/** Borde de fuera del dorsal ancho: de la axila baja por el costado hasta la cresta ilíaca. */
const LAT_LATERAL = dense([
  [0.188, 1.276],
  [0.166, 1.22],
  [0.143, 1.16],
  [0.124, 1.09],
  [0.11, 1.03],
  [0.1, 0.996],
]);

/** Donde la carne del dorsal se vuelve aponeurosis (la fascia toracolumbar), de la cresta a la V. */
const LAT_APONEUROSIS = dense([
  [0.1, 0.996],
  [0.088, 1.05],
  [0.074, 1.11],
  [0.06, 1.17],
  [0.046, 1.236],
]);

/** Borde de fuera de los erectores: el cordón lumbar, más grueso abajo, que se estrecha al sacro. */
const ERECTOR_LATERAL = dense([
  [0.04, 1.3],
  [0.044, 1.236],
  [0.05, 1.17],
  [0.058, 1.11],
  [0.066, 1.05],
  [0.066, 0.995],
  [0.054, 0.955],
]);

/** Cresta ilíaca: de la espina ilíaca posterosuperior (el hoyuelo) sube y cae al costado. */
const ILIAC_CREST: readonly BackPoint[] = [
  [0.035, 0.95],
  [0.06, 0.975],
  [0.1, 0.996],
  [0.13, 0.99],
  [0.148, 0.975],
];

/**
 * Ancho de los surcos del tronco: algo más que el de por defecto (`MUSCLE_LOOK.grooveWidth`), porque
 * aquí los músculos son grandes y en la app (el cuerpo entero en ~300 px) un surco de 2,4 cm se
 * quedaba en un hilo y la espalda volvía a leerse como una mancha lisa.
 */
const TORSO_GROOVE = 0.03;

/**
 * Músculos del tronco con volumen (formato en `backSkin.ts`), en orden de pintado: el de después
 * tapa al de antes. Abajo los planos hondos (dorsal, fascia, erectores, oblicuo), luego la
 * escápula (redondos, infraespinoso) y encima el trapecio, que cubre el borde medial de la escápula
 * y lo alto de los erectores. Los niveles siguen el calor de `heat.ts`:
 * lo más templado entre las escápulas, verde en los dorsales que se enfría hacia el costado, y
 * verde-cian en la lumbar.
 */
export const TORSO_MUSCLES: readonly BackMuscle[] = bilateralMuscles(
  (
    [
      // Dorsal ancho: el abanico de la axila a la fascia lumbar. El vientre, a lo largo del eje.
      {
        outline: chain(
          reversed(TERES_LOWER),
          [[0.07, 1.226]],
          reversed(LAT_APONEUROSIS),
          reversed(LAT_LATERAL),
        ),
        belly: 0.58,
        edge: 0.3,
        shape: [
          [0.15, 1.22],
          [0.12, 1.13],
          [0.104, 1.06],
        ],
      },
      // Fascia toracolumbar: un plano tendinoso entre el dorsal y los erectores, casi liso (vientre y
      // borde parecidos) y con el surco tenue: es una lámina, no un volumen.
      {
        outline: chain(
          LAT_APONEUROSIS,
          ERECTOR_LATERAL.filter(([, y]) => y <= 1.236),
          [
            [0.06, 0.968],
            [0.082, 0.986],
          ],
        ),
        belly: 0.45,
        edge: 0.37,
        groove: 0.5,
        rim: 0.6,
      },
      // Erectores de la columna: el cordón a un lado del surco de la columna, grueso en la lumbar. Lo
      // alto queda bajo el trapecio inferior: asoman por debajo de su V, con la que comparten borde. Su
      // borde de dentro queda a 1 cm del eje: los surcos de los dos lados se juntan en el de la columna,
      // oscuro, y el contorno va algo más tenue para que el surco no se lea como dos líneas claras.
      {
        outline: chain(
          ERECTOR_LATERAL.filter(([, y]) => y <= 1.236),
          [
            [0.038, 0.935],
            [0.02, 0.93],
            [0.01, 0.945],
            [0.01, 1.05],
          ],
          reversed(TRAP_V).filter(([, y]) => y <= 1.236),
        ),
        belly: 0.62,
        edge: 0.36,
        shape: [
          [0.028, 1.24],
          [0.036, 1.1],
          [0.036, 1.0],
        ],
        grooveWidth: 0.034,
        rim: 0.7,
      },
      // Oblicuo externo: el costado entre el borde del dorsal y la cresta ilíaca, más frío.
      {
        outline: chain(
          LAT_LATERAL.filter(([, y]) => y <= 1.175),
          [
            [0.12, 0.996],
            [0.136, 0.986],
            [0.138, 1.03],
            [0.141, 1.1],
            [0.15, 1.17],
          ],
        ),
        belly: 0.45,
        edge: 0.26,
      },
      // Redondo mayor: del ángulo inferior de la escápula a la axila.
      {
        outline: chain(
          TERES_LOWER,
          reversed(armEdge(1.316, 1.276)),
          reversed(TERES_SPLIT),
          INFRA_LATERAL.filter(([, y]) => y <= 1.3),
        ),
        belly: 0.62,
        edge: 0.36,
        shape: [
          [0.12, 1.245],
          [0.17, 1.28],
        ],
      },
      // Redondo menor: la cinta corta del borde lateral de la escápula al húmero, hasta el deltoides.
      {
        outline: chain(
          INFRA_LATERAL.filter(([, y]) => y >= 1.3),
          TERES_SPLIT.slice(1),
          reversed(armEdge(1.358, 1.316)),
        ),
        belly: 0.56,
        edge: 0.34,
      },
      // Infraespinoso: la fosa bajo la espina de la escápula; el vientre, algo arriba y por dentro.
      {
        outline: chain(
          SPINE_EDGE.filter(([x]) => x <= 0.164),
          armEdge(1.382, 1.358),
          INFRA_LATERAL,
          [
            [0.09, 1.262],
            [0.082, 1.31],
          ],
        ),
        belly: 0.69,
        edge: 0.4,
        shape: [[0.118, 1.322]],
      },
      // Trapecio inferior: de la raíz de la espina baja en V hasta T12.
      {
        outline: chain(TRAP_MIDDLE_LOWER, TRAP_V, [
          [0.006, 1.2],
          [0.006, 1.27],
        ]),
        belly: 0.71,
        edge: 0.42,
        shape: [
          [0.04, 1.31],
          [0.028, 1.22],
        ],
      },
      // Trapecio medio: los haces casi horizontales de T1-T4 a la espina de la escápula; lo más
      // templado de la espalda, entre las escápulas.
      {
        outline: chain(
          TRAP_UPPER_MIDDLE,
          reversed(SPINE_EDGE),
          reversed(TRAP_MIDDLE_LOWER),
          [[0.006, 1.4]],
        ),
        belly: 0.74,
        edge: 0.44,
        shape: [
          [0.02, 1.4],
          [0.09, 1.395],
        ],
      },
      // Trapecio superior: la cuesta del occipital al acromion, por el cuello.
      {
        outline: chain(
          [
            [0.006, 1.588],
            [0.03, 1.585],
            [0.042, 1.53],
            [0.058, 1.483],
            [0.1, 1.45],
            [0.15, 1.43],
            [0.19, 1.412],
          ],
          reversed(TRAP_UPPER_MIDDLE),
          [[0.006, 1.53]],
        ),
        belly: 0.64,
        edge: 0.38,
        shape: [
          [0.022, 1.54],
          [0.05, 1.47],
          [0.12, 1.432],
        ],
      },
    ] satisfies BackMuscle[]
  ).map((muscle): BackMuscle => ({ grooveWidth: TORSO_GROOVE, ...muscle })),
);

/** Alturas de las apófisis espinosas, de C7 a L5. */
const SPINOUS: readonly number[] = (() => {
  const c7 = 1.47;
  const t12 = 1.12;
  const l5 = 0.97;
  const thoracic = Array.from(
    { length: 12 },
    (_, i) => c7 - ((i + 1) * (c7 - t12)) / 12,
  );
  const lumbar = Array.from(
    { length: 5 },
    (_, i) => t12 - ((i + 1) * (t12 - l5)) / 5,
  );
  return [c7, ...thoracic, ...lumbar];
})();

/**
 * Una apófisis espinosa: un hueso corto de través en el surco de la columna, con su sombra debajo.
 * C7 (la prominente) es más ancha y más clara; las demás quedan algo hundidas entre los erectores.
 */
function spinous(y: number, index: number): BackBone {
  const half = index === 0 ? 0.011 : 0.007;
  return {
    points: [
      [-half, y],
      [half, y],
    ],
    width: index === 0 ? 0.006 : 0.005,
    strength: index === 0 ? 1 : 0.8,
  };
}

/** Huesos del tronco: crestas claras con su sombra (formato en `backSkin.ts`). */
export const TORSO_BONES: readonly BackBone[] = [
  // En el eje: van fuera de `bilateralBones` (con espejo saldrían dobles).
  ...SPINOUS.map(spinous),
  ...bilateralBones([
    // Línea nucal superior del occipital: la base del cráneo, que se curva hacia la mastoides.
    {
      points: [
        [0.004, 1.594],
        [0.035, 1.589],
        [0.06, 1.576],
        [0.072, 1.562],
      ],
      width: 0.006,
    },
    // Espina de la escápula: de la raíz en el borde medial sube hacia fuera hasta el acromion.
    { points: SPINE_OF_SCAPULA, width: 0.006 },
    // Borde medial y ángulo inferior de la escápula. Casi vertical: la sombra va hacia dentro.
    {
      points: [
        [0.08, 1.362],
        [0.081, 1.315],
        [0.088, 1.27],
        [0.097, 1.244],
        [0.106, 1.234],
        [0.115, 1.24],
      ],
      width: 0.005,
      shadow: [-0.003, -0.002],
    },
    // Cresta ilíaca.
    { points: ILIAC_CREST, width: 0.006 },
    // Bordes del sacro: convergen de las espinas ilíacas posterosuperiores al cóccix.
    {
      points: [
        [0.03, 0.944],
        [0.024, 0.915],
        [0.014, 0.887],
        [0.005, 0.868],
      ],
      width: 0.005,
      shadow: [-0.004, -0.002],
      strength: 0.8,
    },
  ]),
];

/** Trazos de detalle que no son volumen: un tendón, un cordón fino, un hoyuelo. */
export const TORSO: readonly BackStroke[] = [
  // Aponeurosis del trapecio en la base del cuello (C7-T1): el rombo tendinoso de la nuca.
  {
    points: [
      [0, 1.495],
      [0.016, 1.47],
      [0, 1.44],
      [-0.016, 1.47],
    ],
    closed: true,
    width: 0.005,
    strength: 0.6,
  },
  ...bilateral([
    // Cordón del cuello (semiespinoso y esplenio de la cabeza) bajo el trapecio superior.
    {
      points: [
        [0.016, 1.582],
        [0.021, 1.54],
        [0.024, 1.505],
      ],
      width: 0.005,
      strength: 0.5,
    },
    // El surco entre el iliocostal y el longísimo, dentro del erector: tenue.
    {
      points: [
        [0.032, 1.2],
        [0.038, 1.12],
        [0.04, 1.05],
        [0.036, 0.985],
      ],
      width: 0.004,
      strength: 0.4,
    },
    // Hoyuelo sacro (espina ilíaca posterosuperior): un punto corto.
    {
      points: [
        [0.03, 0.944],
        [0.042, 0.94],
      ],
      width: 0.006,
      strength: 0.6,
    },
  ]),
];
