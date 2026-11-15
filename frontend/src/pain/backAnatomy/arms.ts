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
 * El brazo por detrás, como en el frente: cada músculo un volumen con su color y cada hueso una
 * cresta clara (formato en `backSkin.ts`). Antes era un manojo de líneas finas sobre una mancha
 * verde, y Ellande (2026-11-10) no veía en la espalda «huesos definidos, solo manchurrones».
 *
 * Se dibuja el brazo izquierdo (+x) y `bilateralMuscles`/`bilateralBones`/`bilateral` sacan el
 * derecho. El brazo no cuelga a plomo: se abre unos 20° y el codo se dobla algo, así que cada pieza
 * sigue el eje de su tramo (`arm.axis` en `bodyModel.ts`: hombro 0,197/1,34, mitad del brazo
 * 0,228/1,205, codo 0,27/1,07, antebrazo 0,31/0,955, muñeca 0,342/0,845 y nudillos 0,354/0,76). En
 * la proyección de espaldas el lado de dentro (medial) queda en x menor y el de fuera (lateral) en x
 * mayor; la cara de atrás cae sobre el eje. Por eso la cabeza larga del tríceps va por dentro y la
 * lateral por fuera, el cúbito por el eje del antebrazo con el flexor cubital por dentro y los
 * extensores por fuera, y el braquiorradial asoma en el borde de fuera.
 *
 * Los músculos se TOCAN por costuras compartidas (`seam`): dos vecinos llevan los mismos puntos del
 * borde común, densos, y así su surco y su contorno son uno solo. Si cada uno llevara su propio
 * borde, saldrían dos brillos paralelos, y en un antebrazo de 7-10 cm eso se lee como una mancha.
 * Los contornos tampoco se tapan entre sí (se pintan encima de todos los rellenos), así que ningún
 * músculo se mete debajo de otro: el mosaico encaja sin solapes.
 *
 * El brazo es estrecho y la prueba (`arms.test.ts`) exige que toda curva caiga dentro de la silueta
 * de la malla: los bordes exteriores van a 6-10 mm del canto. Si se toca el eje del brazo en
 * `bodyModel.ts`, hay que revisarlo con `npm run preview:back -- --crop 0.15,0.7,0.45,1.45 --scale 3`.
 */

/** Un borde compartido entre dos músculos, con un punto por centímetro (ver `backSkin.ts`). */
const seam = (points: readonly BackPoint[]): BackPoint[] => smoothCurve(points, false, 0.01);

/** Lo mismo al revés, para recorrer el borde común en el sentido del otro músculo. */
const back = (points: readonly BackPoint[]): BackPoint[] => [...points].reverse();

/**
 * Un contorno cerrado hecho de tramos: los une quitando el punto repetido donde uno acaba y el
 * siguiente empieza (y el último si vuelve al primero), que la Catmull-Rom no quiere puntos dobles.
 */
function ring(...parts: readonly (readonly BackPoint[])[]): BackPoint[] {
  const same = (a: BackPoint, b: BackPoint) => Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-6;
  const out: BackPoint[] = [];
  for (const point of parts.flat()) {
    if (out.length === 0 || !same(out[out.length - 1]!, point)) out.push(point);
  }
  while (out.length > 1 && same(out[0]!, out[out.length - 1]!)) out.pop();
  return out;
}

// ---- Puntos donde se juntan varios músculos (brazo izquierdo) ----
/** Acromion: arriba, donde se separan la cabeza posterior y la media del deltoides. */
const ACROMION: BackPoint = [0.2, 1.394];
/** La V del deltoides: su inserción en el húmero, donde acaban sus dos cabezas. */
const DELTOID_V: BackPoint = [0.256, 1.226];
/** Bajo el deltoides, donde la cabeza larga y la lateral del tríceps se separan. */
const TRICEPS_FORK: BackPoint = [0.224, 1.26];
/** La herradura del tendón: su arco de dentro, su cima y su arco de fuera. */
const HORSESHOE_IN: BackPoint = [0.224, 1.124];
const HORSESHOE_TOP: BackPoint = [0.246, 1.152];
const HORSESHOE_OUT: BackPoint = [0.272, 1.124];
/** Borde de dentro de la cabeza larga, donde empieza a asomar la medial. */
const MEDIAL_HEAD_TOP: BackPoint = [0.212, 1.14];
/** Pie del tendón por dentro y por fuera, sobre el olécranon. */
const TENDON_FOOT_IN: BackPoint = [0.247, 1.093];
const TENDON_FOOT_OUT: BackPoint = [0.284, 1.082];
/** Origen común de los extensores, bajo el epicóndilo lateral. */
const EXTENSOR_ORIGIN: BackPoint = [0.298, 1.06];
/** El cúbito: arriba bajo el olécranon, donde acaba el ancóneo, y abajo junto a su cabeza. */
const ULNA_TOP: BackPoint = [0.272, 1.042];
const ULNA_ANCONEUS: BackPoint = [0.28, 1.0];
const ULNA_FOOT: BackPoint = [0.322, 0.895];
/** Donde el ancóneo deja de tocar al extensor de los dedos y empieza el cubital posterior. */
const ANCONEUS_TIP: BackPoint = [0.293, 1.02];
/** Pie del cubital posterior, junto a la cabeza del cúbito. */
const ECU_FOOT: BackPoint = [0.33, 0.888];
/** Punta de abajo del braquiorradial, donde se vuelve tendón y deja el borde al extensor. */
const BRACHIORADIALIS_TIP: BackPoint = [0.337, 0.94];

// ---- Bordes compartidos ----
const DELTOID_SPLIT = seam([ACROMION, [0.214, 1.37], [0.232, 1.32], [0.246, 1.272], DELTOID_V]);
const DELTOID_OVER_LATERAL = seam([DELTOID_V, [0.24, 1.246], TRICEPS_FORK]);
const DELTOID_OVER_LONG = seam([TRICEPS_FORK, [0.206, 1.281], [0.19, 1.302]]);
const LONG_LATERAL = seam([TRICEPS_FORK, [0.229, 1.22], [0.238, 1.18], HORSESHOE_TOP]);
const HORSESHOE_LONG = seam([HORSESHOE_IN, [0.235, 1.142], HORSESHOE_TOP]);
const HORSESHOE_LATERAL = seam([HORSESHOE_TOP, [0.258, 1.142], HORSESHOE_OUT]);
const LONG_MEDIAL = seam([MEDIAL_HEAD_TOP, HORSESHOE_IN]);
const TENDON_MEDIAL = seam([HORSESHOE_IN, [0.234, 1.108], TENDON_FOOT_IN]);
const TENDON_BRACHIORADIALIS = seam([HORSESHOE_OUT, [0.278, 1.1], TENDON_FOOT_OUT]);
const ULNA_HIGH = seam([ULNA_TOP, [0.276, 1.02], ULNA_ANCONEUS]);
const ULNA_LOW = seam([ULNA_ANCONEUS, [0.29, 0.96], [0.306, 0.92], ULNA_FOOT]);
const ANCONEUS_DIGITORUM = seam([EXTENSOR_ORIGIN, [0.297, 1.04], ANCONEUS_TIP]);
const ANCONEUS_ULNARIS = seam([ANCONEUS_TIP, [0.287, 1.008], ULNA_ANCONEUS]);
const ULNARIS_DIGITORUM = seam([ANCONEUS_TIP, [0.3, 0.99], [0.307, 0.96], [0.318, 0.92], ECU_FOOT]);
const DIGITORUM_BRACHIORADIALIS = seam([BRACHIORADIALIS_TIP, [0.328, 0.975], [0.318, 1.015], [0.308, 1.045], EXTENSOR_ORIGIN]);

/**
 * Los músculos del brazo, de arriba abajo. Niveles de la rampa: el hombro y el brazo verdes, con la
 * veta templada (amarillo) en la cabeza lateral del tríceps como en el frente; el tendón plano del
 * tríceps más frío que la carne que lo rodea, porque es una lámina sin vientre; y el antebrazo
 * enfriándose hacia la muñeca. Para eso, en el antebrazo el vientre (`shape`) va en el tercio de
 * arriba, donde está la carne: hacia abajo el músculo se adelgaza en tendón y se queda en su `edge`.
 */
export const ARMS_MUSCLES: readonly BackMuscle[] = bilateralMuscles([
  // ---- Tríceps ----
  // Cabeza larga: por dentro, de debajo del deltoides a la herradura del tendón.
  {
    outline: ring(
      DELTOID_OVER_LONG,
      [
        [0.186, 1.262],
        [0.189, 1.215],
        [0.196, 1.178],
        [0.204, 1.155],
      ],
      LONG_MEDIAL,
      HORSESHOE_LONG,
      back(LONG_LATERAL),
    ),
    belly: 0.66,
    edge: 0.44,
    shape: [
      [0.205, 1.255],
      [0.215, 1.175],
    ],
  },
  // Cabeza lateral: por fuera, de la V del deltoides a la herradura. Es la veta templada del brazo
  // (`heat.ts`): su vientre, amarillo.
  {
    outline: ring(
      [
        DELTOID_V,
        [0.272, 1.19],
        [0.279, 1.155],
      ],
      back(HORSESHOE_LATERAL),
      back(LONG_LATERAL),
      back(DELTOID_OVER_LATERAL),
    ),
    belly: 0.76,
    edge: 0.5,
    // Fusiforme: el vientre a lo largo del eje de la cabeza.
    shape: [
      [0.24, 1.225],
      [0.262, 1.162],
    ],
  },
  // Cabeza medial: asoma por dentro del tendón, sobre el epicóndilo medial. Pequeña, con el surco
  // estrecho para que no se coma su propio relleno.
  {
    outline: ring(
      LONG_MEDIAL,
      TENDON_MEDIAL,
      [
        [0.24, 1.083],
        [0.23, 1.09],
        [0.222, 1.105],
        [0.215, 1.124],
      ],
    ),
    belly: 0.6,
    edge: 0.44,
    grooveWidth: 0.014,
  },
  // Tendón plano: la lámina de la herradura al olécranon. Sin vientre (casi el mismo nivel en el
  // borde que en el centro) y más frío que las cabezas: se lee como hueco, no como carne. Su propio
  // surco y contorno, más tenues; donde toca a las cabezas manda el de ellas.
  {
    outline: ring(
      HORSESHOE_LONG,
      HORSESHOE_LATERAL,
      TENDON_BRACHIORADIALIS,
      [
        [0.276, 1.079],
        [0.264, 1.08],
      ],
      back(TENDON_MEDIAL),
    ),
    belly: 0.42,
    edge: 0.36,
    groove: 0.5,
    grooveWidth: 0.012,
    rim: 0.55,
  },

  // ---- Antebrazo ----
  // Braquiorradial (con los radiales debajo): asoma por el borde de fuera desde encima del codo y
  // se vuelve tendón hacia la mitad del antebrazo.
  {
    outline: ring(
      TENDON_BRACHIORADIALIS,
      back(DIGITORUM_BRACHIORADIALIS),
      [
        [0.338, 0.96],
        [0.335, 0.99],
        [0.328, 1.025],
        [0.317, 1.06],
        [0.304, 1.09],
        [0.29, 1.113],
      ],
    ),
    belly: 0.42,
    edge: 0.22,
    grooveWidth: 0.018,
    shape: [
      [0.298, 1.088],
      [0.322, 1.02],
    ],
  },
  // Ancóneo: el triangulito del epicóndilo lateral al cúbito, junto al olécranon.
  {
    outline: ring([[0.285, 1.054]], ANCONEUS_DIGITORUM, ANCONEUS_ULNARIS, back(ULNA_HIGH)),
    belly: 0.4,
    edge: 0.26,
    grooveWidth: 0.014,
  },
  // Flexor cubital del carpo: por dentro del cúbito, el borde de dentro del antebrazo.
  {
    outline: ring(ULNA_HIGH, ULNA_LOW, [
      [0.312, 0.9],
      [0.3, 0.918],
      [0.282, 0.948],
      [0.263, 0.978],
      [0.246, 1.01],
      [0.241, 1.038],
      [0.25, 1.056],
      [0.262, 1.05],
    ]),
    belly: 0.3,
    edge: 0.1,
    grooveWidth: 0.018,
    shape: [
      [0.258, 1.025],
      [0.276, 0.972],
    ],
  },
  // Cubital posterior (extensor cubital del carpo): junto al cúbito, por fuera.
  {
    outline: ring(ANCONEUS_ULNARIS, ULNA_LOW, [ECU_FOOT], back(ULNARIS_DIGITORUM)),
    belly: 0.3,
    edge: 0.1,
    grooveWidth: 0.018,
    shape: [
      [0.289, 0.998],
      [0.298, 0.958],
    ],
  },
  // Extensor de los dedos: el vientre del centro, del epicóndilo lateral a la muñeca.
  {
    outline: ring(
      ANCONEUS_DIGITORUM,
      ULNARIS_DIGITORUM,
      [
        [0.336, 0.893],
        [0.34, 0.913],
      ],
      DIGITORUM_BRACHIORADIALIS,
    ),
    belly: 0.34,
    edge: 0.12,
    grooveWidth: 0.018,
    shape: [
      [0.305, 1.028],
      [0.315, 0.968],
    ],
  },

  // ---- Deltoides: al final, que es el que queda arriba en el hombro ----
  // Cabeza posterior: de la espina de la escápula, en diagonal hacia fuera, a la V.
  {
    outline: ring(
      [
        [0.168, 1.382],
        [0.182, 1.39],
      ],
      DELTOID_SPLIT,
      DELTOID_OVER_LATERAL,
      DELTOID_OVER_LONG,
      [
        [0.18, 1.33],
        [0.174, 1.358],
      ],
    ),
    belly: 0.62,
    edge: 0.42,
    shape: [
      [0.186, 1.36],
      [0.232, 1.264],
    ],
  },
  // Cabeza media: la punta del hombro, del acromion a la V por fuera.
  {
    outline: ring(
      [
        ACROMION,
        [0.222, 1.379],
        [0.245, 1.35],
        [0.262, 1.315],
        [0.268, 1.28],
        [0.266, 1.25],
      ],
      back(DELTOID_SPLIT),
    ),
    belly: 0.68,
    edge: 0.46,
    shape: [
      [0.228, 1.36],
      [0.255, 1.278],
    ],
  },
]);

/** Huesos del brazo: crestas claras con su sombra (formato en `backSkin.ts`). */
export const ARMS_BONES: readonly BackBone[] = bilateralBones([
  // Olécranon: la punta del codo, un óvalo pequeño al pie del tendón; sombra hacia fuera y abajo.
  {
    points: [
      [0.27, 1.077],
      [0.281, 1.072],
      [0.284, 1.059],
      [0.276, 1.047],
      [0.265, 1.05],
      [0.262, 1.064],
    ],
    width: 0.005,
    closed: true,
    shadow: [0.003, -0.004],
  },
  // Epicóndilos: el relieve de dentro y el de fuera del codo, a los lados del olécranon. Como
  // crestas abiertas (el lomo del relieve) y no como anillos: tres óvalos en fila parecían botones.
  // Medial: el lomo mira hacia dentro y arriba; la sombra, hacia dentro y abajo.
  {
    points: [
      [0.245, 1.082],
      [0.238, 1.077],
      [0.236, 1.067],
    ],
    width: 0.005,
    shadow: [-0.003, -0.003],
  },
  // Lateral: sobre el origen de los extensores, el lomo hacia fuera.
  {
    points: [
      [0.298, 1.082],
      [0.305, 1.076],
      [0.307, 1.065],
    ],
    width: 0.005,
    shadow: [0.003, -0.003],
  },
  // Borde del cúbito: subcutáneo del olécranon a la muñeca, en el surco entre el flexor y el
  // cubital posterior. Casi vertical: la sombra va a un lado (hacia fuera), no hacia abajo.
  {
    points: [ULNA_TOP, [0.276, 1.02], ULNA_ANCONEUS, [0.29, 0.96], [0.306, 0.92], ULNA_FOOT],
    width: 0.005,
    shadow: [0.004, -0.001],
    strength: 0.9,
  },
  // Cabeza del cúbito: el bulto de la muñeca del lado del meñique.
  {
    points: [
      [0.327, 0.885],
      [0.335, 0.889],
      [0.34, 0.881],
      [0.336, 0.873],
      [0.328, 0.875],
    ],
    width: 0.0045,
    closed: true,
    shadow: [0.003, -0.003],
  },
  // Nudillos: el arco de las cabezas de los metacarpianos.
  {
    points: [
      [0.338, 0.773],
      [0.347, 0.765],
      [0.357, 0.762],
      [0.367, 0.766],
    ],
    width: 0.005,
  },
]);

/**
 * Trazos sueltos del brazo: lo que no es un volumen ni un hueso. En el dorso de la mano (0,05 m de
 * ancho) van finos (4-5 mm) y tenues, para que cinco líneas en tan poco sitio no se fundan en una
 * mancha clara.
 */
export const ARMS: readonly BackStroke[] = bilateral([
  // Retináculo de los extensores: la banda de la muñeca, de través y algo inclinada con el eje.
  {
    points: [
      [0.32, 0.86],
      [0.338, 0.853],
      [0.356, 0.85],
    ],
    width: 0.005,
    strength: 0.75,
  },

  // ---- Dorso de la mano ----
  // Tendones extensores: cuatro cordones que se abren de la muñeca a los nudillos.
  {
    points: [
      [0.333, 0.842],
      [0.333, 0.805],
      [0.336, 0.772],
    ],
    width: 0.004,
    strength: 0.6,
  },
  {
    points: [
      [0.341, 0.842],
      [0.343, 0.805],
      [0.346, 0.766],
    ],
    width: 0.004,
    strength: 0.6,
  },
  {
    points: [
      [0.348, 0.842],
      [0.352, 0.805],
      [0.357, 0.763],
    ],
    width: 0.004,
    strength: 0.6,
  },
  {
    points: [
      [0.354, 0.842],
      [0.361, 0.806],
      [0.367, 0.767],
    ],
    width: 0.004,
    strength: 0.6,
  },
  // Separación de los dedos, bajo los nudillos.
  {
    points: [
      [0.341, 0.758],
      [0.339, 0.73],
      [0.338, 0.708],
    ],
    width: 0.004,
    strength: 0.5,
  },
  {
    points: [
      [0.351, 0.755],
      [0.349, 0.728],
      [0.346, 0.706],
    ],
    width: 0.004,
    strength: 0.5,
  },
  {
    points: [
      [0.362, 0.757],
      [0.36, 0.735],
      [0.357, 0.716],
    ],
    width: 0.004,
    strength: 0.5,
  },
]);
