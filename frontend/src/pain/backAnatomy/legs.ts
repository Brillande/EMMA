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
 * Glúteos y piernas por detrás: músculos con volumen, huesos con cresta y pocos trazos. Formato en
 * `backSkin.ts`; vista previa con `npm run preview:back -- --crop -0.25,0,0.25,0.95 --scale 2`
 * (con `--regions`, el contorno de cada músculo y cada hueso).
 *
 * Por qué músculos y no trazos (Ellande, 2026-11-10, sobre la espalda de solo trazos: «no veo
 * huesos definidos, solo veo manchurrones; fíjate en el frente»): en el frente cada músculo es un
 * volumen con su color y su surco. Aquí el glúteo mayor y el medio, la cintilla iliotibial, los tres
 * isquiotibiales, los aductores, los gemelos y el sóleo son volúmenes que se tocan; el surco
 * interglúteo, el pliegue glúteo y el hueco poplíteo salen de sus surcos, no de una línea suelta. El
 * tendón de Aquiles, los maléolos y el calcáneo son huesos: crestas claras y nítidas.
 *
 * Se dibuja la pierna izquierda del tripulante (+x) y `bilateral*` saca la derecha; «por dentro» es
 * hacia x = 0 y «por fuera» hacia x mayor. Las cotas salen de la silueta de la malla, no de un
 * cuerpo genérico, para que cada volumen caiga sobre su bulto: la cresta ilíaca a 0,99 m (la dibuja
 * `torso.ts`), el trocánter a 0,88 (cadera hasta x ≈ 0,17), la entrepierna a 0,78, el pliegue de la
 * rodilla a 0,49 (pierna de x ≈ 0,054 a 0,166), la panza de los gemelos a 0,35 (0,054-0,190) y el
 * tobillo a 0,13 (0,090-0,160, eje en x ≈ 0,125). La prueba (`legs.test.ts`) comprueba que todo
 * contorno y todo trazo cae sobre la malla.
 *
 * Cómo se arma: los bordes que comparten dos músculos vecinos se escriben una sola vez, como curva
 * densa (`border`, un punto por centímetro), y cada contorno se compone de tramos de esos bordes
 * (`ring` y `cut`). Así los dos vecinos llevan exactamente los mismos puntos y comparten surco y
 * contorno; con puntos distintos saldrían dos brillos paralelos (`backSkin.ts`).
 */

/** Un borde compartido, denso: pasa por todos sus puntos, y los conserva tal cual (`smoothCurve`). */
const border = (points: readonly BackPoint[]): BackPoint[] => smoothCurve(points, false, 0.01);

/** El tramo de `curve` de `from` a `to` (dos de sus puntos), en ese sentido. */
function cut(curve: readonly BackPoint[], from: BackPoint, to: BackPoint): BackPoint[] {
  const index = (point: BackPoint) => {
    const at = curve.findIndex(([x, y]) => x === point[0] && y === point[1]);
    // Un nudo que no está en su borde es un error de dibujo: mejor que falle al cargar que un
    // contorno que se cierra por donde no debe.
    if (at < 0) throw new Error(`legs.ts: (${point[0]}, ${point[1]}) no está en el borde`);
    return at;
  };
  const [a, b] = [index(from), index(to)];
  return a <= b ? curve.slice(a, b + 1) : curve.slice(b, a + 1).reverse();
}

/** Contorno cerrado hecho de tramos seguidos: quita el punto repetido donde se empalman. */
function ring(...parts: readonly (readonly BackPoint[])[]): BackPoint[] {
  const same = (p: BackPoint, q: BackPoint) => p[0] === q[0] && p[1] === q[1];
  const out: BackPoint[] = [];
  for (const part of parts) {
    for (const point of part) if (out.length === 0 || !same(out[out.length - 1]!, point)) out.push(point);
  }
  if (out.length > 1 && same(out[0]!, out[out.length - 1]!)) out.pop();
  return out;
}

// ---- Nudos: donde se juntan tres músculos (pierna izquierda, +x) ----
/** Glúteo mayor, medio y sacro: el arranque del borde de arriba del glúteo mayor. */
const SACRAL: BackPoint = [0.035, 0.972];
/** Trocánter mayor: glúteo mayor, glúteo medio y el costado. */
const TROCHANTER: BackPoint = [0.16, 0.885];
/** Por fuera de la cadera: glúteo mayor, cintilla iliotibial y costado. */
const HIP_SIDE: BackPoint = [0.169, 0.83];
/** Extremo de fuera del pliegue glúteo: glúteo mayor, cintilla y bíceps femoral. */
const FOLD_OUT: BackPoint = [0.158, 0.812];
/** Extremo de dentro del pliegue glúteo, en la entrepierna. */
const FOLD_IN: BackPoint = [0.02, 0.787];
/** En el pliegue: aductores | semitendinoso. */
const FOLD_ADD: BackPoint = [0.056, 0.774];
/** En el pliegue, sobre la tuberosidad isquiática: semitendinoso | bíceps femoral. */
const ISCHIUM: BackPoint = [0.086, 0.772];
/** Vértice de arriba del hueco poplíteo, donde se separan el bíceps y el semitendinoso. */
const POP_TOP: BackPoint = [0.113, 0.565];
/** En el borde de arriba del hueco: semitendinoso | semimembranoso. */
const POP_ST: BackPoint = [0.097, 0.537];
/** Vértices de dentro, de fuera y de abajo del rombo poplíteo. */
const POP_IN: BackPoint = [0.081, 0.506];
const POP_OUT: BackPoint = [0.14, 0.506];
const POP_BOTTOM: BackPoint = [0.113, 0.452];
/** Cara externa de la rodilla, donde acaba la cintilla iliotibial. */
const KNEE_OUT: BackPoint = [0.147, 0.528];
/** Hasta dónde bajan los aductores por el borde del semimembranoso. */
const ADDUCTOR_LOW: BackPoint = [0.059, 0.62];
/** Punta de arriba del semimembranoso, que asoma bajo el semitendinoso solo en la mitad de abajo. */
const SEMIMEMBRANOSUS_TOP: BackPoint = [0.055, 0.705];
/** Gemelos y sóleo: arriba por dentro, punta de cada cabeza, el surco entre ellas y arriba por fuera. */
const CALF_IN: BackPoint = [0.072, 0.4];
const CALF_TIP_IN: BackPoint = [0.114, 0.252];
const CALF_NOTCH: BackPoint = [0.12, 0.305];
const CALF_OUT: BackPoint = [0.168, 0.385];

// ---- Bordes compartidos ----
/** Borde de arriba del glúteo mayor: del sacro, en diagonal hacia abajo y afuera, al trocánter. */
const GLUTEUS_TOP = border([SACRAL, [0.075, 0.958], [0.115, 0.935], [0.145, 0.905], TROCHANTER]);
/** Glúteo medio bajo la cresta ilíaca, que dibuja el tronco justo encima. */
const ILIAC_ARC = border([SACRAL, [0.07, 0.983], [0.105, 0.99], [0.132, 0.983], [0.146, 0.958], [0.155, 0.92], TROCHANTER]);
/** Borde de fuera del glúteo mayor, que baja a meterse en la cintilla. */
const GLUTEUS_SIDE = border([TROCHANTER, [0.167, 0.858], HIP_SIDE, FOLD_OUT]);
/** Pliegue glúteo: de la entrepierna hacia fuera, subiendo un poco. */
const GLUTEAL_FOLD = border([FOLD_IN, FOLD_ADD, ISCHIUM, [0.112, 0.777], [0.14, 0.793], FOLD_OUT]);
/**
 * Borde de dentro del glúteo mayor: el surco interglúteo. Queda a 8 mm del eje, y su espejo a otros
 * 8: entre los dos contornos claros asoma el fondo con los dos surcos encima, una raja oscura.
 */
const CLEFT = border([FOLD_IN, [0.009, 0.81], [0.008, 0.86], [0.011, 0.91], [0.02, 0.95], SACRAL]);
/** Cintilla iliotibial | bíceps femoral. */
const ITB_INNER = border([FOLD_OUT, [0.157, 0.76], [0.16, 0.7], [0.155, 0.635], [0.145, 0.575], KNEE_OUT]);
/** Borde de fuera de la cintilla, junto al canto del muslo. */
const ITB_OUTER = border([KNEE_OUT, [0.155, 0.537], [0.16, 0.57], [0.168, 0.63], [0.177, 0.69], [0.178, 0.75], [0.175, 0.8], HIP_SIDE]);
/** Bíceps femoral | semitendinoso: de la tuberosidad isquiática al vértice del hueco poplíteo. */
const HAMSTRING_SPLIT = border([ISCHIUM, [0.104, 0.69], [0.112, 0.615], POP_TOP]);
/** Semitendinoso | semimembranoso. */
const SEMI_SPLIT = border([POP_ST, [0.088, 0.615], [0.071, 0.67], SEMIMEMBRANOSUS_TOP]);
/**
 * El borde de dentro de los isquiotibiales, de la rodilla al pliegue: abajo, semimembranoso | canto
 * de dentro del muslo; en medio, semimembranoso | aductores; arriba, semitendinoso | aductores.
 */
const MEDIAL_THIGH = border([POP_IN, [0.066, 0.56], ADDUCTOR_LOW, SEMIMEMBRANOSUS_TOP, [0.056, 0.74], FOLD_ADD]);
/** Canto de dentro de los aductores, junto a la entrepierna. */
const ADDUCTOR_INNER = border([ADDUCTOR_LOW, [0.042, 0.64], [0.036, 0.7], [0.028, 0.755], FOLD_IN]);
/** Borde de arriba del hueco poplíteo, con los tendones de los isquiotibiales. */
const POP_UPPER = border([POP_IN, POP_ST, POP_TOP, [0.129, 0.537], POP_OUT]);
/** Borde de abajo del hueco poplíteo: el arranque de las dos cabezas de los gemelos. */
const POP_LOWER = border([POP_OUT, [0.127, 0.47], POP_BOTTOM, [0.095, 0.47], POP_IN]);
/** El tendón del bíceps, del vértice de fuera del rombo a la cara externa de la rodilla. */
const BICEPS_TENDON = border([POP_OUT, KNEE_OUT]);
/** Las dos cabezas de los gemelos, de abajo arriba. */
const CALF_SPLIT = border([CALF_NOTCH, [0.117, 0.38], POP_BOTTOM]);
/** Borde de dentro de la cabeza interna, del rombo a donde asoma el sóleo. */
const CALF_INNER = border([POP_IN, [0.072, 0.46], CALF_IN]);
/** Borde de fuera de la cabeza externa. */
const CALF_OUTER = border([CALF_OUT, [0.158, 0.45], POP_OUT]);
/**
 * Gemelos | sóleo: baja por dentro, rodea la punta de la cabeza interna (la más baja), sube a la
 * escotadura entre las dos, rodea la externa y sube por fuera.
 */
const CALF_LOW = border([
  CALF_IN,
  [0.074, 0.34],
  [0.084, 0.295],
  [0.099, 0.268],
  CALF_TIP_IN,
  CALF_NOTCH,
  [0.137, 0.285],
  [0.155, 0.305],
  [0.165, 0.34],
  CALF_OUT,
]);
/** El resto del sóleo: asoma a los dos lados de los gemelos y se junta abajo, en el tendón. */
const SOLEUS_OUTER = border([
  CALF_OUT,
  [0.178, 0.36],
  [0.179, 0.31],
  [0.168, 0.25],
  [0.152, 0.21],
  [0.136, 0.195],
  [0.114, 0.195],
  [0.1, 0.212],
  [0.09, 0.25],
  [0.075, 0.29],
  [0.066, 0.33],
  [0.066, 0.37],
  CALF_IN,
]);

/**
 * Los músculos, en los niveles del calor de `heat.ts`: los glúteos en cian-verde (vientre 0,27-0,3,
 * borde 0,14-0,15), entre la lumbar y el muslo, más fríos que la lumbar como la ingle del frente lo
 * es del abdomen; el muslo y la pierna en el azul del frente con el vientre hacia el cian (0,13-0,2,
 * borde 0,04-0,07): con más, la pierna de espaldas salía turquesa al lado de la de frente, azul.
 * La cintilla iliotibial es una banda tendinosa, no un vientre: se queda en azul hondo, más fría que
 * todo lo de alrededor. El hueco poplíteo no es un músculo sino el hueco entre cuatro: se pinta como
 * uno casi sin vientre (del nivel 0 en el borde a 0,03 en el centro) con un surco ancho que lo
 * oscurece casi entero, y el contorno a media luz.
 */
export const LEGS_MUSCLES: readonly BackMuscle[] = bilateralMuscles([
  // --- Glúteos ---
  // Glúteo medio: arriba y fuera, entre la cresta ilíaca y el borde de arriba del glúteo mayor.
  {
    outline: ring(ILIAC_ARC, cut(GLUTEUS_TOP, TROCHANTER, SACRAL)),
    belly: 0.27,
    edge: 0.14,
    shape: [[0.12, 0.96]],
  },
  // Glúteo mayor: el cuadrante grande, del surco interglúteo al costado y del sacro al pliegue.
  {
    outline: ring(GLUTEUS_TOP, GLUTEUS_SIDE, cut(GLUTEAL_FOLD, FOLD_OUT, FOLD_IN), CLEFT),
    belly: 0.3,
    edge: 0.15,
    shape: [[0.085, 0.87]],
  },

  // --- Muslo ---
  // Cintilla iliotibial: la banda fría del canto de fuera, de la cadera a la rodilla.
  {
    outline: ring(cut(GLUTEUS_SIDE, HIP_SIDE, FOLD_OUT), ITB_INNER, ITB_OUTER),
    belly: 0.04,
    edge: 0.02,
    shape: [
      [0.168, 0.79],
      [0.165, 0.62],
    ],
    groove: 0.7,
    rim: 0.7,
  },
  // Bíceps femoral: el isquiotibial de fuera, de la tuberosidad a la cabeza del peroné.
  {
    outline: ring(
      cut(ITB_INNER, KNEE_OUT, FOLD_OUT),
      cut(GLUTEAL_FOLD, FOLD_OUT, ISCHIUM),
      HAMSTRING_SPLIT,
      cut(POP_UPPER, POP_TOP, POP_OUT),
      BICEPS_TENDON,
    ),
    belly: 0.19,
    edge: 0.06,
    shape: [
      [0.115, 0.73],
      [0.135, 0.62],
    ],
  },
  // Semitendinoso: el de dentro arriba, que baja hasta el borde de arriba del hueco poplíteo. Los
  // tres de dentro del muslo son estrechos: surco y contorno más finos, para que se les vea el
  // vientre y no queden en tres rayas.
  {
    outline: ring(
      HAMSTRING_SPLIT,
      cut(POP_UPPER, POP_TOP, POP_ST),
      SEMI_SPLIT,
      cut(MEDIAL_THIGH, SEMIMEMBRANOSUS_TOP, FOLD_ADD),
      cut(GLUTEAL_FOLD, FOLD_ADD, ISCHIUM),
    ),
    belly: 0.18,
    edge: 0.06,
    grooveWidth: 0.016,
    rim: 0.75,
  },
  // Semimembranoso: asoma por dentro del semitendinoso en la mitad de abajo, más ancho hacia la
  // rodilla, y cierra el rombo poplíteo por dentro.
  {
    outline: ring(
      cut(SEMI_SPLIT, SEMIMEMBRANOSUS_TOP, POP_ST),
      cut(POP_UPPER, POP_ST, POP_IN),
      cut(MEDIAL_THIGH, POP_IN, SEMIMEMBRANOSUS_TOP),
    ),
    belly: 0.16,
    edge: 0.05,
    grooveWidth: 0.016,
    rim: 0.75,
  },
  // Aductores (aductor mayor y recto interno), asomando por dentro del muslo bajo la entrepierna.
  {
    outline: ring(cut(GLUTEAL_FOLD, FOLD_IN, FOLD_ADD), cut(MEDIAL_THIGH, FOLD_ADD, ADDUCTOR_LOW), ADDUCTOR_INNER),
    belly: 0.13,
    edge: 0.04,
    grooveWidth: 0.016,
    rim: 0.75,
  },

  // --- Rodilla ---
  // Hueco poplíteo: el rombo oscuro entre los isquiotibiales (arriba) y los gemelos (abajo).
  {
    outline: ring(POP_UPPER, POP_LOWER),
    belly: 0.03,
    edge: 0,
    grooveWidth: 0.034,
    rim: 0.5,
  },

  // --- Pantorrilla ---
  // Sóleo: va antes que los gemelos, pero no se pisan; el sóleo solo ocupa lo que dejan a los lados
  // y debajo (un músculo tapado tendría su surco y su contorno pintados encima del que lo tapa).
  {
    outline: ring(CALF_LOW, SOLEUS_OUTER),
    belly: 0.13,
    edge: 0.04,
    grooveWidth: 0.018,
  },
  // Gemelos, cabeza interna: más abultada, y baja más que la externa.
  {
    outline: ring(CALF_INNER, cut(CALF_LOW, CALF_IN, CALF_NOTCH), CALF_SPLIT, cut(POP_LOWER, POP_BOTTOM, POP_IN)),
    belly: 0.2,
    edge: 0.07,
  },
  // Gemelos, cabeza externa.
  {
    outline: ring(cut(CALF_SPLIT, POP_BOTTOM, CALF_NOTCH), cut(CALF_LOW, CALF_NOTCH, CALF_OUT), CALF_OUTER, cut(POP_LOWER, POP_OUT, POP_BOTTOM)),
    belly: 0.18,
    edge: 0.07,
  },
]);

/** Huesos y tendón del tobillo: crestas claras con su sombra (formato en `backSkin.ts`). */
export const LEGS_BONES: readonly BackBone[] = bilateralBones([
  // Tendón de Aquiles: no es hueso, pero bajo la piel se lee igual, una cresta clara y estrecha del
  // sóleo al talón. Vertical: la sombra va a un lado, que hacia abajo la taparía la propia cresta.
  {
    points: [
      [0.125, 0.215],
      [0.125, 0.16],
      [0.124, 0.09],
    ],
    width: 0.006,
    shadow: [0.004, 0],
    strength: 0.85,
  },
  // Maléolo interno (tibia): más alto que el externo.
  {
    points: [
      [0.099, 0.104],
      [0.106, 0.096],
      [0.103, 0.084],
      [0.097, 0.091],
    ],
    width: 0.005,
    closed: true,
    shadow: [-0.003, -0.003],
  },
  // Maléolo externo (peroné): más bajo y más atrás.
  {
    points: [
      [0.151, 0.086],
      [0.157, 0.076],
      [0.153, 0.064],
      [0.147, 0.073],
    ],
    width: 0.005,
    closed: true,
    shadow: [0.003, -0.003],
  },
  // Calcáneo: la curva del talón bajo el tendón.
  {
    points: [
      [0.108, 0.062],
      [0.11, 0.032],
      [0.125, 0.016],
      [0.14, 0.032],
      [0.143, 0.062],
    ],
    width: 0.006,
  },
]);

/** Lo que no es un volumen ni un hueso. */
export const LEGS: readonly BackStroke[] = bilateral([
  // Borde externo del pie, que sale hacia fuera con la punta abierta.
  {
    points: [
      [0.158, 0.05],
      [0.178, 0.032],
      [0.196, 0.014],
    ],
    width: 0.005,
    strength: 0.6,
  },
]);
