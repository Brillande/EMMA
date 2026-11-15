/**
 * Surcos y crestas del cuerpo del mapa de dolor, como una oclusión ambiental falsa.
 *
 * Por qué existe (modelado 2, 2026-11-09): con la luz clave, la de relleno y el Fresnel, el relieve
 * muscular apenas se leía. Una luz direccional solo distingue hacia dónde mira la superficie, no si
 * está hundida: el surco entre dos abdominales mira hacia delante igual que el abdominal. Lo que el
 * ojo lee como relieve es la sombra de las cavidades, así que aquí se mide cuánto se hunde cada
 * punto respecto a lo que lo rodea y el material oscurece los surcos y aclara las crestas.
 *
 * Cómo:
 * 1. Se sueldan los vértices de TODAS las zonas por posición: cada zona es una malla aparte y su
 *    borde se repite en la vecina. Medido zona a zona, el borde vería vecinos solo de un lado y la
 *    junta saldría como una raya clara u oscura; soldado, el valor es el mismo en las dos.
 * 2. Curvatura normal a lo largo de cada arista, `2 (pj − pi)·n / |pj − pi|²` (la del círculo que
 *    pasa por los dos puntos tangente al plano del primero), y su media en el vértice: una
 *    curvatura media aproximada, en 1/m, que no depende del tamaño de la rejilla. Positiva = hundido.
 * 3. Unas pasadas de promedio con los vecinos quitan el ruido de la rejilla y abren el surco en
 *    una sombra suave (`NOISE_PASSES`).
 * 4. Se le resta el mismo valor suavizado en un radio de unos centímetros: un brazo entero es
 *    convexo y no por eso es una cresta; lo que interesa es el surco respecto a su entorno. Cada
 *    pasada de promedio difunde más o menos una arista, así que cada vértice hace tantas pasadas
 *    como pide su propio largo de arista (`(radio / arista)²`): el radio en metros es parecido en
 *    el tronco, de rejilla gruesa, y en la mano, de rejilla fina. Con un tope de pasadas: en una
 *    rejilla mucho más fina que la de hoy el radio se queda por debajo del pedido (∝ √tope) en vez
 *    de disparar el coste.
 * 5. Se escala por un percentil del valor absoluto (sobre una muestra fija) y se recorta a [−1, 1]:
 *    el contraste no depende de la resolución ni del tamaño del modelo.
 *
 * Todo es lineal en el número de vértices (por un número acotado de pasadas) y se calcula una vez,
 * nunca por fotograma.
 */

/** Lo que hace falta de una superficie: posiciones, normales e índices de triángulos. */
export interface CavitySurface {
  positions: ArrayLike<number>;
  normals: ArrayLike<number>;
  indices: ArrayLike<number>;
}

/** Tolerancia de la soldadura, en metros: dos vértices más cerca que esto son el mismo. */
const WELD = 1e-5;
/** Radio del entorno con el que se compara cada punto, en metros. */
const SURROUND = 0.05;
/** Tope de pasadas anchas por vértice: con rejillas muy finas el coste sigue acotado. */
const MAX_WIDE_PASSES = 64;
/**
 * Pasadas de promedio que quitan el ruido de la rejilla. Cuatro y no dos (humano 6, 2026-11-09):
 * con dos, el surco se quedaba en una o dos aristas de ancho y en pantalla salía como una raya
 * pintada; con cuatro se abre en una sombra suave a los lados, como la oclusión de una piel sobre
 * el músculo.
 */
const NOISE_PASSES = 4;
/** Percentil del valor absoluto que pasa a valer 1. */
const SCALE_PERCENTILE = 0.92;
/** Curvatura máxima que se tiene en cuenta (1/m): las puntas de los remates no la disparan. */
const CURVATURE_CAP = 300;

/**
 * Celdas candidatas de una coordenada: la suya y, si cae cerca del borde de la celda, también la
 * vecina. Dos copias del mismo vértice que difieran en nanómetros a un lado y otro del borde
 * acaban así en la misma, sin mirar las 27 celdas vecinas de cada vértice.
 */
function cells(value: number): number[] {
  const scaled = value / WELD;
  const cell = Math.round(scaled);
  const offset = scaled - cell;
  if (offset > 0.4) return [cell, cell + 1];
  if (offset < -0.4) return [cell, cell - 1];
  return [cell];
}

/** Vértices soldados por posición: a qué punto va cada vértice de cada superficie y sus datos. */
export interface Welded {
  /** Por superficie, el punto soldado de cada uno de sus vértices. */
  welded: Int32Array[];
  px: number[];
  py: number[];
  pz: number[];
  /** Normal media de las copias, unitaria donde `oriented` vale 1 (y sin normalizar donde no). */
  nx: number[];
  ny: number[];
  nz: number[];
  /** 1 si las copias dan una normal con dirección; 0 si se anulan al sumarlas. */
  oriented: Uint8Array;
  total: number;
}

/**
 * Suelda los vértices de todas las superficies por posición (tolerancia `WELD`). Lo usan la
 * cavidad y los cruces entre piezas (`crossing.ts`): las dos necesitan saber qué vértices son el
 * mismo punto del cuerpo aunque vayan en zonas distintas.
 */
export function weldSurfaces(surfaces: readonly CavitySurface[]): Welded {
  const keys = new Map<string, number>();
  const welded: Int32Array[] = [];
  const px: number[] = [];
  const py: number[] = [];
  const pz: number[] = [];
  const nx: number[] = [];
  const ny: number[] = [];
  const nz: number[] = [];
  const find = (x: number, y: number, z: number): number | undefined => {
    for (const cx of cells(x)) {
      for (const cy of cells(y)) {
        for (const cz of cells(z)) {
          const id = keys.get(`${cx},${cy},${cz}`);
          if (id !== undefined) return id;
        }
      }
    }
    return undefined;
  };
  for (const surface of surfaces) {
    const count = surface.positions.length / 3;
    const map = new Int32Array(count);
    for (let v = 0; v < count; v += 1) {
      const x = surface.positions[v * 3]!;
      const y = surface.positions[v * 3 + 1]!;
      const z = surface.positions[v * 3 + 2]!;
      let id = find(x, y, z);
      if (id === undefined) {
        id = px.length;
        keys.set(`${Math.round(x / WELD)},${Math.round(y / WELD)},${Math.round(z / WELD)}`, id);
        px.push(x);
        py.push(y);
        pz.push(z);
        nx.push(0);
        ny.push(0);
        nz.push(0);
      }
      nx[id]! += surface.normals[v * 3]!;
      ny[id]! += surface.normals[v * 3 + 1]!;
      nz[id]! += surface.normals[v * 3 + 2]!;
      map[v] = id;
    }
    welded.push(map);
  }
  const total = px.length;
  // Una normal que se anula al sumar las copias (copias opuestas) no dice hacia dónde está fuera:
  // ese vértice no mide curvatura (vale 0) en vez de dar un valor de signo arbitrario.
  const oriented = new Uint8Array(total);
  for (let id = 0; id < total; id += 1) {
    const length = Math.hypot(nx[id]!, ny[id]!, nz[id]!);
    if (length < 1e-3) continue;
    oriented[id] = 1;
    nx[id] = nx[id]! / length;
    ny[id] = ny[id]! / length;
    nz[id] = nz[id]! / length;
  }
  return { welded, px, py, pz, nx, ny, nz, oriented, total };
}

/**
 * Valor de cavidad por vértice de cada superficie, en [−1, 1]: positivo en los surcos, negativo en
 * las crestas. Devuelve un `Float32Array` por superficie, en su mismo orden de vértices.
 */
export function cavityOf(
  surfaces: readonly CavitySurface[],
  weld: Welded = weldSurfaces(surfaces),
): Float32Array[] {
  // 1. Soldadura por posición redondeada (la de `weld`, si ya se tiene).
  const { welded, px, py, pz, nx, ny, nz, oriented, total } = weld;

  // Vecinos en formato comprimido (CSR): cada arista de cada triángulo, en los dos sentidos. Una
  // arista interior sale dos veces (dos triángulos) y pesa el doble; todas igual, así que da lo
  // mismo para la media. Las aristas que la soldadura deja en un solo punto no cuentan.
  const forEachEdge = (visit: (from: number, to: number) => void) => {
    surfaces.forEach((surface, s) => {
      const map = welded[s]!;
      for (let t = 0; t + 2 < surface.indices.length; t += 3) {
        const a = map[surface.indices[t]!]!;
        const b = map[surface.indices[t + 1]!]!;
        const c = map[surface.indices[t + 2]!]!;
        if (a !== b) {
          visit(a, b);
          visit(b, a);
        }
        if (b !== c) {
          visit(b, c);
          visit(c, b);
        }
        if (c !== a) {
          visit(c, a);
          visit(a, c);
        }
      }
    });
  };
  const start = new Int32Array(total + 1);
  forEachEdge((from) => {
    start[from + 1]! += 1;
  });
  for (let id = 0; id < total; id += 1) start[id + 1]! += start[id]!;
  const neighbours = new Int32Array(start[total]!);
  const fill = start.slice(0, total);
  forEachEdge((from, to) => {
    neighbours[fill[from]!] = to;
    fill[from]! += 1;
  });

  // 2. Curvatura media aproximada y, de paso, las pasadas anchas que pide cada vértice.
  const curvature = new Float32Array(total);
  const passes = new Uint8Array(total);
  for (let i = 0; i < total; i += 1) {
    let sum = 0;
    let used = 0;
    let length = 0;
    for (let k = start[i]!; k < start[i + 1]!; k += 1) {
      const j = neighbours[k]!;
      const dx = px[j]! - px[i]!;
      const dy = py[j]! - py[i]!;
      const dz = pz[j]! - pz[i]!;
      const squared = dx * dx + dy * dy + dz * dz;
      if (squared < WELD * WELD) continue;
      sum += (2 * (dx * nx[i]! + dy * ny[i]! + dz * nz[i]!)) / squared;
      length += Math.sqrt(squared);
      used += 1;
    }
    const mean = used > 0 && oriented[i] === 1 ? sum / used : 0;
    curvature[i] = Math.max(-CURVATURE_CAP, Math.min(CURVATURE_CAP, mean));
    const edge = used > 0 ? length / used : SURROUND;
    passes[i] = Math.min(MAX_WIDE_PASSES, Math.max(1, Math.round((SURROUND / edge) ** 2)));
  }

  // Promedio con los vecinos (el propio vértice cuenta como uno más), sin tocar la entrada. Cada
  // vértice deja de cambiar cuando ha hecho las pasadas que le tocan.
  const smooth = (values: Float32Array, limit: ArrayLike<number> | number): Float32Array => {
    let most = 0;
    for (let i = 0; i < total; i += 1) most = Math.max(most, typeof limit === "number" ? limit : limit[i]!);
    let current = Float32Array.from(values);
    let next = new Float32Array(total);
    for (let pass = 0; pass < most; pass += 1) {
      for (let i = 0; i < total; i += 1) {
        if (pass >= (typeof limit === "number" ? limit : limit[i]!)) {
          next[i] = current[i]!;
          continue;
        }
        let sum = current[i]!;
        for (let k = start[i]!; k < start[i + 1]!; k += 1) sum += current[neighbours[k]!]!;
        next[i] = sum / (1 + start[i + 1]! - start[i]!);
      }
      [current, next] = [next, current];
    }
    return current;
  };

  // 3. Quitar el ruido de la rejilla.
  const relief = smooth(curvature, NOISE_PASSES);
  // 4. Restar el entorno.
  const surround = smooth(relief, passes);
  for (let i = 0; i < total; i += 1) relief[i] = relief[i]! - surround[i]!;

  // 5. Escala por percentil sobre una muestra de paso fijo (lineal, sin ordenar todo).
  const stride = Math.max(1, Math.floor(total / 4096));
  const sample: number[] = [];
  for (let i = 0; i < total; i += stride) sample.push(Math.abs(relief[i]!));
  sample.sort((a, b) => a - b);
  const scale = sample.length > 0 ? sample[Math.floor((sample.length - 1) * SCALE_PERCENTILE)]! : 0;

  return welded.map((map) => {
    const out = new Float32Array(map.length);
    if (scale <= 0) return out;
    for (let v = 0; v < map.length; v += 1) {
      out[v] = Math.max(-1, Math.min(1, relief[map[v]!]! / scale));
    }
    return out;
  });
}

/**
 * Atenúa la cavidad donde `keep(x, y, z)` (en [0, 1]) lo pida, en el sitio.
 *
 * Por qué (facciones 1, 2026-11-10, «hazle la cara con facciones bonitas»): la sombra de cavidades
 * lee la cara con la misma vara que un abdominal, y en ella cada pliegue blando —el de la nariz a la
 * boca, el de bajo el labio, la ojera— salía como una arruga oscura que envejecía el rostro. La cara
 * se lee por sus volúmenes, no por sus surcos. El factor depende solo de la posición, así que el
 * mismo vértice en dos zonas vecinas recibe el mismo y la junta no se nota.
 */
export function fadeCavities(
  values: readonly Float32Array[],
  surfaces: readonly CavitySurface[],
  keep: (x: number, y: number, z: number) => number,
): void {
  values.forEach((out, s) => {
    const positions = surfaces[s]!.positions;
    for (let v = 0; v < out.length; v += 1) {
      const factor = keep(positions[v * 3]!, positions[v * 3 + 1]!, positions[v * 3 + 2]!);
      out[v] = out[v]! * Math.max(0, Math.min(1, factor));
    }
  });
}
