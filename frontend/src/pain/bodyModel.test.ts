import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  ARC_STEP,
  BODY,
  BODY_HEIGHT,
  type Bump,
  type Patch,
  SWEEPS,
  type Sweep,
  type SweepName,
  type Vec3,
  bounds,
  isClick,
  surfaceOf,
  surfacePoint,
  sweepSurface,
  toNormalized,
} from "./bodyModel";

const byZone = new Map(BODY.map((item) => [item.zone, item]));

// Las 28 claves del backend (`backend/app/pain/catalog.py`): 8 de la linea media y 10 pares.
const MIDLINE = ["head", "face", "neck", "chest", "upper-back", "abdomen", "lower-back", "pelvis"];
const PAIRED = [
  "shoulder", "upper-arm", "elbow", "forearm", "hand", "hip", "thigh", "knee", "lower-leg", "foot",
];

/** Primera zona que toca un rayo (Moller-Trumbore sobre las mallas de verdad, sin caras traseras). */
function firstHit(origin: Vec3, direction: Vec3): string | null {
  return hit(origin, direction).zone;
}

/** La zona y la distancia del primer impacto de un rayo. */
function hit(origin: Vec3, direction: Vec3): { zone: string | null; distance: number } {
  let best = Infinity;
  let zone: string | null = null;
  for (const item of BODY) {
    const { positions, indices } = surfaceOf(item);
    const at = (index: number): Vec3 => [
      positions[index * 3]!,
      positions[index * 3 + 1]!,
      positions[index * 3 + 2]!,
    ];
    for (let k = 0; k < indices.length; k += 3) {
      const a = at(indices[k]!);
      const b = at(indices[k + 1]!);
      const c = at(indices[k + 2]!);
      const e1 = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
      const e2 = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
      const p = [
        direction[1] * e2[2]! - direction[2] * e2[1]!,
        direction[2] * e2[0]! - direction[0] * e2[2]!,
        direction[0] * e2[1]! - direction[1] * e2[0]!,
      ];
      const det = e1[0]! * p[0]! + e1[1]! * p[1]! + e1[2]! * p[2]!;
      // Solo caras de frente al rayo, como el `Raycaster` con materiales `FrontSide`: si el giro
      // de un triangulo saliera al reves, el clic lo atravesaria y aqui tambien.
      if (det < 1e-12) continue;
      const s = [origin[0] - a[0], origin[1] - a[1], origin[2] - a[2]];
      const u = (s[0]! * p[0]! + s[1]! * p[1]! + s[2]! * p[2]!) / det;
      if (u < 0 || u > 1) continue;
      const q = [
        s[1]! * e1[2]! - s[2]! * e1[1]!,
        s[2]! * e1[0]! - s[0]! * e1[2]!,
        s[0]! * e1[1]! - s[1]! * e1[0]!,
      ];
      const v = (direction[0] * q[0]! + direction[1] * q[1]! + direction[2] * q[2]!) / det;
      if (v < 0 || u + v > 1) continue;
      const t = (e2[0]! * q[0]! + e2[1]! * q[1]! + e2[2]! * q[2]!) / det;
      if (t > 0 && t < best) {
        best = t;
        zone = item.zone;
      }
    }
  }
  return { zone, distance: best };
}

describe("cuerpo del mapa de dolor", () => {
  it("estan las 28 zonas del backend, cada una una sola vez", () => {
    expect(byZone.size).toBe(BODY.length);
    expect([...byZone.keys()].sort()).toEqual(
      [...MIDLINE, ...PAIRED.flatMap((base) => [`${base}-left`, `${base}-right`])].sort(),
    );
  });

  it("cada zona tiene superficie", () => {
    for (const item of BODY) {
      const surface = surfaceOf(item);
      expect(surface.indices.length, item.zone).toBeGreaterThan(30);
      expect(surface.positions.every(Number.isFinite), item.zone).toBe(true);
      expect(surface.normals.every(Number.isFinite), item.zone).toBe(true);
    }
  });

  it("las zonas izquierdas caen en el lado izquierdo del tripulante (+x)", () => {
    // Visto de frente, la izquierda del tripulante esta a la derecha de la pantalla. Si esto
    // se invierte, el mapa apunta el lado equivocado.
    for (const item of BODY) {
      const box = bounds(item);
      if (item.zone.endsWith("-left")) {
        expect(item.position[0]).toBeGreaterThan(0);
        expect(box.max[0], item.zone).toBeGreaterThan(-box.min[0]);
      }
      if (item.zone.endsWith("-right")) {
        expect(item.position[0]).toBeLessThan(0);
        expect(-box.min[0], item.zone).toBeGreaterThan(box.max[0]);
      }
    }
  });

  it("izquierda y derecha son espejo exacto", () => {
    for (const item of BODY) {
      if (!item.zone.endsWith("-left")) continue;
      const mirror = byZone.get(item.zone.replace(/-left$/, "-right"))!;
      expect(mirror.position).toEqual([-item.position[0], item.position[1], item.position[2]]);
      const a = bounds(item);
      const b = bounds(mirror);
      expect(b.min[0]).toBeCloseTo(-a.max[0], 6);
      expect(b.max[0]).toBeCloseTo(-a.min[0], 6);
      for (const axis of [1, 2]) {
        expect(b.min[axis]).toBeCloseTo(a.min[axis]!, 6);
        expect(b.max[axis]).toBeCloseTo(a.max[axis]!, 6);
      }
    }
  });

  it("el torax queda delante de la espalda alta, y el abdomen delante de la lumbar", () => {
    for (const [front, back] of [
      ["chest", "upper-back"],
      ["abdomen", "lower-back"],
    ] as const) {
      // Las dos mitades del mismo contorno: la de delante (0 a 180 grados, hacia +z) y la de
      // detras. Se tocan en los costados, nada mas.
      const [a] = byZone.get(front)!.patches;
      const [b] = byZone.get(back)!.patches;
      expect(a?.arc).toEqual([0, 180]);
      expect(b?.arc).toEqual([180, 360]);
      expect([a?.from, a?.to]).toEqual([b?.from, b?.to]);
      const meanZ = (zone: string) => {
        const { positions } = surfaceOf(byZone.get(zone)!);
        let sum = 0;
        for (let k = 2; k < positions.length; k += 3) sum += positions[k]!;
        return sum / (positions.length / 3);
      };
      expect(meanZ(front)).toBeGreaterThan(meanZ(back) + 0.1);
    }
  });

  it("los trozos del tronco, la pelvis y las caderas reparten el tronco sin pisarse ni dejar huecos", () => {
    // Si dos trozos se solaparan, un clic en la junta podria caer en cualquiera de los dos; si
    // quedara un hueco, se veria el interior.
    const pieces: { zone: string; from: number; to: number; lo: number; hi: number }[] = [];
    const add = (zone: string, patch: Patch) => {
      const [start, end] = patch.arc ?? [0, 360];
      expect(Math.abs(start % ARC_STEP), zone).toBe(0);
      expect(Math.abs(end % ARC_STEP), zone).toBe(0);
      // El sector, llevado a [0, 360) y partido si da la vuelta.
      const lo = ((start % 360) + 360) % 360;
      const hi = lo + (end - start);
      for (const [a, b] of hi > 360 ? [[lo, 360], [0, hi - 360]] : [[lo, hi]]) {
        pieces.push({ zone, from: patch.from, to: patch.to, lo: a!, hi: b! });
      }
    };
    for (const item of BODY) {
      for (const patch of item.patches) if (patch.on === "column") add(item.zone, patch);
    }
    for (const a of pieces) {
      for (const b of pieces) {
        if (a === b) continue;
        const overlap = a.from < b.to && b.from < a.to && a.lo < b.hi && b.lo < a.hi;
        expect(overlap, `${a.zone} / ${b.zone}`).toBe(false);
      }
    }
    const area = pieces.reduce((sum, item) => sum + (item.to - item.from) * (item.hi - item.lo), 0);
    expect(area).toBeCloseTo((1.73 - 0.78) * 360, 6);
  });

  it("de frente se toca cada zona de delante, y de espalda cada zona de detras", () => {
    // Un rayo hacia el centro de la zona, como el clic de la camara de frente o de espalda.
    const hiddenFromFront = new Set(["head", "upper-back", "lower-back"]);
    const hiddenFromBack = new Set(["face", "chest", "abdomen"]);
    for (const item of BODY) {
      const [x, y] = item.position;
      if (!hiddenFromFront.has(item.zone)) {
        expect(firstHit([x, y, 5], [0, 0, -1]), `${item.zone} de frente`).toBe(item.zone);
      }
      if (!hiddenFromBack.has(item.zone)) {
        expect(firstHit([x, y, -5], [0, 0, 1]), `${item.zone} de espalda`).toBe(item.zone);
      }
    }
  });

  it("las alturas de las zonas ancladas del backend son las de este cuerpo", () => {
    // `pain_on_skeleton.py` acepta el ajuste si el error es menor que la mitad de la zona anclada
    // mas baja segun `pain_points.json`. Si el cuerpo cambia y el JSON no, el umbral sale de un
    // cuerpo que ya no existe: con una zona real mas baja, un ajuste aceptado podria dejar el
    // punto fuera de ella (paso al rehacer el cuerpo, 2026-11-09: la pelvis decia 0,14 m y mide
    // 0,19). Se compara la altura de la caja de cada malla, a tres decimales como el JSON.
    const points = JSON.parse(
      readFileSync(
        fileURLToPath(new URL("../../../backend/app/data/anatomy/pain_points.json", import.meta.url)),
        "utf-8",
      ),
    ) as { zones: Record<string, { bone?: string; height_m?: number }> };
    const anchored = Object.entries(points.zones).filter(([, item]) => item.bone);
    expect(anchored.length).toBeGreaterThan(0);
    for (const [zone, item] of anchored) {
      const box = bounds(byZone.get(zone)!);
      expect(item.height_m, zone).toBeCloseTo(box.max[1] - box.min[1], 3);
    }
    // Y solo las anclas llevan altura: la de una zona sin hueso no la lee nadie y se quedaria vieja.
    for (const [zone, item] of Object.entries(points.zones)) {
      expect("height_m" in item, zone).toBe(Boolean(item.bone));
    }
  });

  it("los dedos son de la mano y las orejas de la cabeza", () => {
    // Son tramos sueltos metidos en la palma y en el craneo: si un dedo quedara fuera de la malla
    // de la mano, tocarlo no marcaria nada (o marcaria el muslo de detras).
    for (const [side, sign] of [["left", 1], ["right", -1]] as const) {
      // Por debajo de los nudillos (0,76 m) solo hay dedos: de frente, de lado y de espalda. La
      // mano cuelga donde la de «Inicio» (Inicio 3D, 2026-11-10), a 0,35 m del centro.
      expect(firstHit([sign * 0.352, 0.72, 5], [0, 0, -1]), `dedos ${side} de frente`).toBe(`hand-${side}`);
      expect(firstHit([sign * 0.352, 0.72, -5], [0, 0, 1]), `dedos ${side} de espalda`).toBe(`hand-${side}`);
      // A la altura del dedo corazon (z = 0,08 en esa altura): entre dedo y dedo el rayo podria
      // colarse.
      expect(firstHit([sign * 5, 0.72, 0.078], [-sign, 0, 0]), `dedos ${side} de lado`).toBe(`hand-${side}`);
      // El pulgar, por delante de la palma: el rayo de frente lo toca mas adelante que cualquier
      // punto de la palma (el final del brazo), y no se queda escondido dentro de ella.
      const thumb = hit([sign * 0.365, 0.78, 5], [0, 0, -1]);
      expect(thumb.zone, `pulgar ${side}`).toBe(`hand-${side}`);
      let palmFront = -Infinity;
      for (let at = 4.85; at <= 6; at += 0.05) {
        for (let deg = 0; deg < 360; deg += 6) {
          palmFront = Math.max(palmFront, surfacePoint("arm", side === "right", at, deg)[2]);
        }
      }
      expect(5 - thumb.distance, `pulgar ${side}`).toBeGreaterThan(palmFront);
      // La oreja, de lado: se toca fuera del craneo (que a esa altura no pasa de x = 0,081).
      const ear = hit([sign * 5, 1.612, -0.012], [-sign, 0, 0]);
      expect(ear.zone, `oreja ${side}`).toBe("head");
      expect(5 - ear.distance, `oreja ${side}`).toBeGreaterThan(0.083);
    }
  });

  it("dentro de una zona no hay aristas vivas que se dibujen como borde", () => {
    // `BodyMap.tsx` traza las aristas de mas de 60 grados (`EdgesGeometry`) como borde de zona:
    // una arista viva dentro de la cara o de la oreja se veria como una zona de mas. Se comprueban
    // las zonas a la vista; las raices del brazo y de los dedos quedan dentro del tronco y la palma.
    const visible = ["head", "face", "neck", "chest", "upper-back", "abdomen", "lower-back", "pelvis"];
    for (const zone of visible) {
      const { positions, indices } = surfaceOf(byZone.get(zone)!);
      const key = (i: number) =>
        [0, 1, 2].map((axis) => Math.round(positions[i * 3 + axis]! * 1e5)).join(",");
      const faceNormals = new Map<string, number[][]>();
      for (let k = 0; k < indices.length; k += 3) {
        const [a, b, c] = [indices[k]!, indices[k + 1]!, indices[k + 2]!];
        const p = (i: number) => [positions[i * 3]!, positions[i * 3 + 1]!, positions[i * 3 + 2]!];
        const [pa, pb, pc] = [p(a), p(b), p(c)];
        const e1 = pb.map((v, axis) => v - pa[axis]!);
        const e2 = pc.map((v, axis) => v - pa[axis]!);
        const n = [
          e1[1]! * e2[2]! - e1[2]! * e2[1]!,
          e1[2]! * e2[0]! - e1[0]! * e2[2]!,
          e1[0]! * e2[1]! - e1[1]! * e2[0]!,
        ];
        const length = Math.hypot(...n);
        if (length < 1e-12) continue;
        const unitNormal = n.map((v) => v / length);
        for (const [u, v] of [[a, b], [b, c], [c, a]] as const) {
          const edge = [key(u), key(v)].sort().join("|");
          faceNormals.set(edge, [...(faceNormals.get(edge) ?? []), unitNormal]);
        }
      }
      let sharp = 0;
      for (const normals of faceNormals.values()) {
        if (normals.length !== 2) continue;
        const [m, n] = normals as [number[], number[]];
        const cosine = m[0]! * n[0]! + m[1]! * n[1]! + m[2]! * n[2]!;
        if (cosine < Math.cos((60 * Math.PI) / 180)) sharp += 1;
      }
      expect(sharp, zone).toBe(0);
    }
  });

  it("el relieve se nota: nariz, ombligo, cuadros del abdomen y planta del pie", () => {
    // De frente, la punta de la nariz queda mas cerca que la frente.
    const nose = hit([0, 1.605, 5], [0, 0, -1]);
    const brow = hit([0, 1.665, 5], [0, 0, -1]);
    expect(nose.zone).toBe("face");
    expect(brow.distance - nose.distance).toBeGreaterThan(0.01);
    // El ombligo, hundido respecto a la piel de encima y de debajo (se compara con la media de las
    // dos, porque el vientre se abomba).
    const above = hit([0, 1.016, 5], [0, 0, -1]);
    const below = hit([0, 0.984, 5], [0, 0, -1]);
    const navel = hit([0, 1.0, 5], [0, 0, -1]);
    expect(navel.zone).toBe("abdomen");
    expect(navel.distance - (above.distance + below.distance) / 2).toBeGreaterThan(0.002);
    // Y los cuadros del abdomen (Inicio 3D, 2026-11-10: la referencia vuelve a ser el varon
    // atletico de «Inicio»): sobre la columna del recto, a 3,4 cm de la linea media, cada corte
    // tendinoso queda hundido respecto al vientre de encima y al de debajo.
    for (const [cut, up, down] of [
      [1.118, 1.146, 1.09],
      [1.062, 1.09, 1.034],
    ] as const) {
      const groove = hit([0.034, cut, 5], [0, 0, -1]);
      const bellies = (hit([0.034, up, 5], [0, 0, -1]).distance + hit([0.034, down, 5], [0, 0, -1]).distance) / 2;
      expect(groove.zone, `${cut}`).toBe("abdomen");
      expect(groove.distance - bellies, `corte a ${cut}`).toBeGreaterThan(0.0015);
    }
    // La planta es plana y apoya en el suelo: muchos vertices del pie estan justo en y = 0.
    const { positions } = surfaceOf(byZone.get("foot-left")!);
    let onFloor = 0;
    for (let k = 1; k < positions.length; k += 3) if (positions[k] === 0) onFloor += 1;
    expect(onFloor).toBeGreaterThan(100);
  });

  it("el cuerpo es ligero de pintar", () => {
    // Se pinta en la consola de a bordo, que puede no tener mas que una grafica integrada.
    const triangles = BODY.reduce((sum, item) => sum + surfaceOf(item).indices.length / 3, 0);
    // Tope subido de 90 000 a 150 000 al afinar la rejilla para el relieve con forma
    // (2026-11-09): con la de antes un borde marcado o un surco estrecho caia entre dos columnas.
    // Y de 150 000 a 180 000 con la cara en filas de 2 mm (Humano 1, `Sweep.fine`): con las de 6
    // mm los labios y los parpados no cabian y la cara era una mascara de bandas.
    expect(triangles).toBeLessThan(180_000);
  });

  it("el cuerpo cabe en su altura declarada, de los pies a la cabeza", () => {
    const top = Math.max(...BODY.map((item) => bounds(item).max[1]));
    const bottom = Math.min(...BODY.map((item) => bounds(item).min[1]));
    expect(bottom).toBeCloseTo(0, 2);
    expect(top).toBeLessThanOrEqual(BODY_HEIGHT + 0.01);
    expect(top).toBeGreaterThan(BODY_HEIGHT - 0.01);
  });
});

/** Huella FNV-1a de 64 bits de los bits de cada coordenada: cambia con un solo bit de un punto. */
function fingerprint(): string {
  const bytes = new Uint8Array(8);
  const view = new DataView(bytes.buffer);
  let h = 0xcbf29ce484222325n;
  for (const name of Object.keys(SWEEPS) as SweepName[]) {
    const axis = SWEEPS[name].axis;
    const start = axis[0]!.at;
    const end = axis[axis.length - 1]!.at;
    for (const mirrored of name === "column" ? [false] : [false, true]) {
      for (let i = 0; i <= 137; i += 1) {
        const at = start + ((end - start) * i) / 137;
        for (let deg = -3; deg <= 363; deg += 3.7) {
          for (const v of surfacePoint(name, mirrored, at, deg)) {
            view.setFloat64(0, v);
            for (const b of bytes) h = ((h ^ BigInt(b)) * 0x100000001b3n) & 0xffffffffffffffffn;
          }
        }
      }
    }
  }
  return h.toString(16);
}

/**
 * Tramo de ensayo: un cilindro recto de 0,1 m de radio, de y = 0 a y = 2, en x = 0,2. Por defecto
 * de miembro (sin la copia espejo del tronco); con `at` en metros y el angulo 0 hacia +x.
 */
function cylinder(relief: Bump[], frame: "level" | "limb" = "limb"): Sweep {
  return {
    frame,
    step: 0.01,
    caps: [0, 0],
    axis: [
      { at: 0, p: [0.2, 0, 0] },
      { at: 1, p: [0.2, 1, 0] },
      { at: 2, p: [0.2, 2, 0] },
    ],
    sections: [
      { at: 0, rx: 0.1, rz: 0.1 },
      { at: 2, rx: 0.1, rz: 0.1 },
    ],
    relief,
  };
}

/** Lo que un punto del cilindro de ensayo sobresale de su radio, con el eje vertical en x = `cx`. */
function lift(p: Vec3, cx: number): number {
  return Math.hypot(p[0] - cx, p[2]) - 0.1;
}

describe("relieve con forma (tilt y edge)", () => {
  it("la forma del cuerpo no cambia sin querer", () => {
    // Huella de los puntos de todos los tramos, los dos lados, medida en `surfacePoint` (no
    // depende de la rejilla). Se fijo primero con el motor de antes de `tilt` y `edge` (commit
    // 3069e41, huella 1d171e8f72a6bef4) para probar que el motor nuevo no movia nada; desde el
    // lote de modelado (2026-11-09) fija el cuerpo remodelado. Si cambia, cambio el cuerpo: se
    // actualiza a proposito y se dice en el commit (la ultima, el cuerpo de «Inicio» en 3D,
    // 2026-11-10; despues, Espalda 5: gluteos, isquiotibiales y gemelos de espalda; y Volumen 5:
    // el relieve de detras, movido para caer donde lo dibuja la textura trasera; y Hombro A: el
    // brazo nace del tronco con sus pliegues axilares). Que un bulto sin `tilt` ni `edge` sigue la
    // cuenta de siempre lo vigila la prueba siguiente.
    expect(fingerprint()).toBe("62054e924dbcfc87");
  });

  it("un giro casi nulo da el mismo bulto que la cuenta de siempre", () => {
    const base: Bump = { at: 1, deg: 90, d: 0.02, sAt: [0.05, 0.08], sDeg: 20 };
    const plain = sweepSurface(cylinder([base]));
    const shaped = sweepSurface(cylinder([{ ...base, tilt: 1e-9 }]));
    for (const at of [0.9, 0.97, 1, 1.04, 1.12]) {
      for (const deg of [50, 75, 90, 110, 140]) {
        const [a, b] = [plain(at, deg), shaped(at, deg)];
        for (const axis of [0, 1, 2]) expect(b[axis]!, `${at}/${deg}`).toBeCloseTo(a[axis]!, 9);
      }
    }
  });

  it("con 45 grados el bulto va en diagonal, medido en metros", () => {
    // Bulto largo (0,06 m por el eje) y estrecho (0,01 m de contorno: 5,73 grados con 0,1 m de
    // radio). Girado 45, empuja en la diagonal (subir y avanzar el angulo) y no en la otra.
    const sDeg = (0.01 / 0.1) * (180 / Math.PI);
    const surface = sweepSurface(cylinder([{ at: 1, deg: 90, d: 0.02, sAt: 0.06, sDeg, tilt: 45 }]));
    const off = 0.03; // metros, por el eje y por el contorno
    const degOff = (off / 0.1) * (180 / Math.PI);
    const along = lift(surface(1 + off, 90 + degOff), 0.2);
    const against = lift(surface(1 + off, 90 - degOff), 0.2);
    expect(along).toBeGreaterThan(0.01);
    expect(against).toBeLessThan(0.001);
    // Sin giro, las dos diagonales son iguales.
    const flat = sweepSurface(cylinder([{ at: 1, deg: 90, d: 0.02, sAt: 0.06, sDeg }]));
    expect(lift(flat(1 + off, 90 + degOff), 0.2)).toBeCloseTo(lift(flat(1 + off, 90 - degOff), 0.2), 12);
  });

  it("el borde marcado deja el vientre plano y corta antes", () => {
    const soft = sweepSurface(cylinder([{ at: 1, deg: 90, d: 0.02, sAt: 0.05, sDeg: 20 }]));
    const hard = sweepSurface(cylinder([{ at: 1, deg: 90, d: 0.02, sAt: 0.05, sDeg: 20, edge: 3 }]));
    // En el centro empujan igual; a 0,7 anchuras el duro sigue casi entero; a 2, ya no empuja.
    expect(lift(hard(1, 90), 0.2)).toBeCloseTo(lift(soft(1, 90), 0.2), 9);
    expect(lift(hard(1.035, 90), 0.2)).toBeGreaterThan(0.018);
    expect(lift(soft(1.035, 90), 0.2)).toBeLessThan(0.016);
    expect(lift(hard(1.1, 90), 0.2)).toBeLessThan(1e-6);
    expect(lift(soft(1.1, 90), 0.2)).toBeGreaterThan(0.002);
    const blunt: Bump = { at: 1, deg: 90, d: 0.02, sAt: 0.05, sDeg: 20, edge: 0.5 };
    expect(() => sweepSurface(cylinder([blunt]))).toThrow();
  });

  it("en el tronco un bulto girado sale simetrico: el espejo lleva el giro opuesto", () => {
    // El cilindro, pero centrado en x = 0, como el tronco.
    const column = (relief: Bump[]): Sweep => ({
      ...cylinder(relief, "level"),
      axis: cylinder([]).axis.map((k) => ({ ...k, p: [0, k.p[1], 0] as const })),
    });
    for (const deg of [60, 90]) {
      // Fuera de la linea media (60) y en ella (90, que tambien se duplica y sale en V).
      const surface = sweepSurface(column([{ at: 1, deg, d: 0.02, sAt: 0.05, sDeg: 12, tilt: 30, edge: 2 }]));
      for (const at of [0.96, 1, 1.03]) {
        for (const a of [40, 55, 62, 70, 85]) {
          const p = surface(at, a);
          const q = surface(at, 180 - a);
          expect(q[0], `${deg}: ${at}/${a}`).toBeCloseTo(-p[0], 12);
          expect(q[1]).toBeCloseTo(p[1], 12);
          expect(q[2]).toBeCloseTo(p[2], 12);
        }
      }
    }
    // El de la linea media va en dos copias de medio empuje: en su centro sube `d`, no el doble.
    const midline = sweepSurface(column([{ at: 1, deg: 90, d: 0.02, sAt: 0.05, sDeg: 12, tilt: 30 }]));
    expect(lift(midline(1, 90), 0)).toBeCloseTo(0.02, 9);
  });

  it("el giro de la seccion lleva el angulo 0 hacia el 90, y en espejo al reves", () => {
    // `twist` (la pronacion de la mano): el relieve gira con la seccion. Con 90 grados, el bulto
    // escrito a 0 sale donde sin giro saldria uno escrito a 90; el tramo derecho sigue siendo el
    // espejo exacto del izquierdo.
    const bump: Bump = { at: 1, deg: 0, d: 0.02, sAt: 0.1, sDeg: 20 };
    const turned = sweepSurface({ ...cylinder([bump]), twist: [{ at: 0, deg: 90 }] });
    const plain = sweepSurface(cylinder([{ ...bump, deg: 90 }]));
    for (const deg of [0, 40, 200]) {
      const [a, b] = [turned(1, deg), plain(1, deg + 90)];
      for (const axis of [0, 1, 2]) expect(a[axis]!, `${deg}`).toBeCloseTo(b[axis]!, 12);
    }
    const sweep: Sweep = { ...cylinder([{ ...bump, deg: 30 }]), twist: [{ at: 0.5, deg: 0 }, { at: 1.5, deg: 40 }] };
    const left = sweepSurface(sweep);
    const right = sweepSurface(sweep, true);
    for (const at of [0.4, 0.9, 1.2, 1.7]) {
      for (const deg of [10, 30, 75]) {
        const [p, q] = [left(at, deg), right(at, 180 - deg)];
        expect(q[0]).toBeCloseTo(-p[0], 12);
        expect(q[1]).toBeCloseTo(p[1], 12);
        expect(q[2]).toBeCloseTo(p[2], 12);
      }
    }
  });

  it("un bulto con forma mal escrito avisa en vez de desaparecer", () => {
    const ok: Bump = { at: 1, deg: 90, d: 0.02, sAt: 0.05, sDeg: 20, tilt: 10 };
    expect(() => sweepSurface(cylinder([{ ...ok, tilt: Number.NaN }]))).toThrow();
    expect(() => sweepSurface(cylinder([{ ...ok, at: 2.02 }]))).toThrow();
    expect(() => sweepSurface(cylinder([{ ...ok, sAt: [0, 0.05] }]))).toThrow();
    expect(() => sweepSurface(cylinder([ok]))).not.toThrow();
  });

  it("donde el eje no avanza igual, el bulto con forma acaba donde el de siempre", () => {
    // Tramo de miembro con el segundo tramo del eje tres veces mas largo: `at` no son metros y
    // la escala cambia en el centro. Un borde apenas marcado no debe mover los extremos.
    const sweep = (relief: Bump[]): Sweep => ({
      ...cylinder(relief),
      axis: [
        { at: 0, p: [0.2, 0, 0] },
        { at: 1, p: [0.2, 0.3, 0] },
        { at: 2, p: [0.2, 1.2, 0] },
      ],
    });
    const base: Bump = { at: 1, deg: 90, d: 0.02, sAt: [0.3, 0.3], sDeg: 20 };
    const plain = sweepSurface(sweep([base]));
    const shaped = sweepSurface(sweep([{ ...base, edge: 1 + 1e-12 }]));
    for (const at of [0.7, 1.3]) {
      expect(lift(shaped(at, 90), 0.2), `${at}`).toBeCloseTo(lift(plain(at, 90), 0.2), 3);
    }
  });

  it("en brazo y pierna el tramo derecho es el espejo exacto del izquierdo, con giro", () => {
    const bump: Bump = { at: 1, deg: 120, d: 0.02, sAt: [0.04, 0.09], sDeg: 25, tilt: 35, edge: 2 };
    const sweep = cylinder([bump]);
    const left = sweepSurface(sweep);
    const right = sweepSurface(sweep, true);
    for (const at of [0.95, 1, 1.05]) {
      for (const deg of [90, 110, 125, 150]) {
        // El angulo a del tramo derecho es el 180 - a del izquierdo.
        const p = left(at, deg);
        const q = right(at, 180 - deg);
        expect(q[0]).toBeCloseTo(-p[0], 12);
        expect(q[1]).toBeCloseTo(p[1], 12);
        expect(q[2]).toBeCloseTo(p[2], 12);
      }
    }
  });
});

describe("puntero", () => {
  const rect = { left: 100, top: 50, width: 200, height: 400 };

  it("la y de la pantalla crece hacia abajo; la del raycaster, hacia arriba", () => {
    expect(toNormalized(100, 50, rect)).toEqual({ x: -1, y: 1 });
    expect(toNormalized(300, 450, rect)).toEqual({ x: 1, y: -1 });
    expect(toNormalized(200, 250, rect)).toEqual({ x: 0, y: -0 });
  });

  it("girar el cuerpo no marca una zona", () => {
    expect(isClick({ x: 10, y: 10 }, { x: 12, y: 13 })).toBe(true);
    expect(isClick({ x: 10, y: 10 }, { x: 40, y: 10 })).toBe(false);
  });
});
