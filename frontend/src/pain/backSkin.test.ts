import { describe, expect, it } from "vitest";

import { BODY_H, BODY_ONE, BODY_W } from "../dashboard/referenceBody.generated";
import { BACK_ART } from "./backAnatomy";
import { BACK_HEAT } from "./backAnatomy/heat";
import {
  BACK_PROJECTION,
  type BackArt,
  type BackMuscle,
  type BackPoint,
  backCoefficients,
  bilateral,
  bilateralBones,
  bilateralMuscles,
  glintColor,
  heatLevel,
  metersPerPixel,
  projectBack,
  rampColor,
  rasterizeBack,
  smoothCurve,
  THERMAL_RAMP,
} from "./backSkin";
import { BODY, BODY_HEIGHT, surfaceOf } from "./bodyModel";
import { decodeBody } from "./thermalSkin";

const { width, height } = BACK_PROJECTION;

/** El color (0-255) de la textura en el píxel que cae en (x, y) del cuerpo. */
function pixelAt(rgba: Uint8Array, x: number, y: number): number[] {
  const [u, v] = projectBack(x, y);
  const i = Math.floor(v * height) * width + Math.floor(u * width);
  return Array.from(rgba.slice(i * 4, i * 4 + 3));
}
const brightness = (rgb: number[]) => rgb[0]! + rgb[1]! + rgb[2]!;

describe("formato del dibujo de la espalda", () => {
  it("cada trazo tiene al menos dos puntos, ancho positivo y cae dentro de la textura", () => {
    expect(BACK_ART.strokes.length).toBeGreaterThan(0);
    for (const [index, stroke] of BACK_ART.strokes.entries()) {
      expect(stroke.points.length, `trazo ${index}`).toBeGreaterThanOrEqual(2);
      expect(stroke.width, `trazo ${index}`).toBeGreaterThan(0);
      if (stroke.glow !== undefined) expect(stroke.glow, `trazo ${index}`).toBeGreaterThan(0);
      for (const [x, y] of stroke.points) {
        const [u, v] = projectBack(x, y);
        expect(u >= 0 && u <= 1 && v >= 0 && v <= 1, `trazo ${index} en (${x}, ${y})`).toBe(true);
      }
    }
  });

  it("cada mancha de calor tiene radios positivos y cae dentro de la textura", () => {
    for (const [index, spot] of BACK_HEAT.spots.entries()) {
      expect(spot.radius[0], `mancha ${index}`).toBeGreaterThan(0);
      expect(spot.radius[1], `mancha ${index}`).toBeGreaterThan(0);
      const [u, v] = projectBack(...spot.at);
      expect(u >= 0 && u <= 1 && v >= 0 && v <= 1, `mancha ${index}`).toBe(true);
    }
  });

  it("`bilateral` añade el espejo en x de cada trazo", () => {
    const [left, right] = bilateral([{ points: [[0.1, 1], [0.2, 1.1]], width: 0.005 }]);
    expect(left!.points).toEqual([[0.1, 1], [0.2, 1.1]]);
    expect(right!.points).toEqual([[-0.1, 1], [-0.2, 1.1]]);
    expect(right!.width).toBe(0.005);
  });

  it("la curva pasa por todos los puntos y empieza y acaba en sus extremos", () => {
    const points = [[0, 0], [0.1, 0.05], [0.2, 0], [0.3, 0.1]] as const;
    const curve = smoothCurve(points, false, 0.01);
    expect(curve[0]).toEqual(points[0]);
    expect(curve.at(-1)).toEqual(points[3]);
    for (const point of points) {
      expect(curve.some(([x, y]) => x === point[0] && y === point[1]), `pasa por ${point.join(", ")}`).toBe(true);
    }
    // Suave: sin saltos mayores que el paso pedido (con algo de holgura por la curvatura).
    for (let i = 1; i < curve.length; i += 1) {
      expect(Math.hypot(curve[i]![0] - curve[i - 1]![0], curve[i]![1] - curve[i - 1]![1])).toBeLessThan(0.02);
    }
  });

  it("una curva cerrada vuelve al primer punto", () => {
    const curve = smoothCurve([[0, 0], [0.1, 0], [0.1, 0.1]], true, 0.01);
    expect(curve.at(-1)).toEqual([0, 0]);
  });
});

describe("rasterizado de la textura trasera", () => {
  const flat: BackArt["heat"] = { base: 0.1, spots: [] };

  it("un trazo aclara donde pasa y no lejos de él", () => {
    const art: BackArt = { heat: flat, strokes: [{ points: [[-0.1, 1], [0.1, 1]], width: 0.008 }] };
    const rgba = rasterizeBack(art);
    const background = pixelAt(rasterizeBack({ heat: flat, strokes: [] }), 0, 1);
    // El fondo es el color de la rampa en ese nivel (a un nivel de 255 por la tabla).
    background.forEach((channel, c) => expect(Math.abs(channel - rampColor(0.1)[c]!)).toBeLessThanOrEqual(1));
    expect(pixelAt(rgba, 0, 1)).not.toEqual(background);
    expect(brightness(pixelAt(rgba, 0, 1))).toBeGreaterThan(brightness(background) + 200);
    // El halo, más tenue que el núcleo, a 1 cm.
    const near = brightness(pixelAt(rgba, 0, 1.01));
    expect(near).toBeGreaterThan(brightness(background));
    expect(near).toBeLessThan(brightness(pixelAt(rgba, 0, 1)));
    // Lejos (5 cm encima, o pasado el extremo), el fondo tal cual.
    expect(pixelAt(rgba, 0, 1.05)).toEqual(background);
    expect(pixelAt(rgba, 0.2, 1)).toEqual(background);
  });

  it("aclara conservando el tono, como las líneas de «Inicio»: sobre verde, verde claro y no blanco", () => {
    const art: BackArt = { heat: { base: 0.5, spots: [] }, strokes: [{ points: [[-0.1, 1], [0.1, 1]], width: 0.01 }] };
    const [r, g, b] = pixelAt(rasterizeBack(art), 0, 1);
    // Sobre verde, verde claro: el verde sigue mandando.
    expect(g!).toBeGreaterThan(r!);
    expect(g!).toBeGreaterThan(b!);
    expect(g!).toBeGreaterThan(rampColor(0.5)[1]);
    // Y no blanco: el azul queda muy por debajo del verde.
    expect(b!).toBeLessThan(0.7 * g!);
  });

  it("es opaca y del tamaño declarado (al menos 512×1024)", () => {
    const rgba = rasterizeBack({ heat: flat, strokes: [] });
    expect(width).toBeGreaterThanOrEqual(512);
    expect(height).toBeGreaterThanOrEqual(1024);
    expect(rgba.length).toBe(width * height * 4);
    for (let i = 3; i < rgba.length; i += 4 * 997) expect(rgba[i]).toBe(255);
  });
});

describe("calor de la espalda", () => {
  it("una mancha calienta su centro y no lejos", () => {
    const heat = { base: 0.1, spots: [{ at: [0, 1] as const, radius: [0.05, 0.05] as const, heat: 0.4 }] };
    expect(heatLevel(heat, 0, 1)).toBeCloseTo(0.5, 10);
    expect(heatLevel(heat, 0.05, 1)).toBeCloseTo(0.1 + 0.4 / Math.E, 10);
    expect(heatLevel(heat, 0.3, 1)).toBe(0.1);
  });

  it("el nivel se recorta a la rampa", () => {
    const hot = { base: 0.9, spots: [{ at: [0, 1] as const, radius: [0.1, 0.1] as const, heat: 0.9 }] };
    expect(heatLevel(hot, 0, 1)).toBe(1);
    const cold = { base: 0.1, spots: [{ at: [0, 1] as const, radius: [0.1, 0.1] as const, heat: -0.9 }] };
    expect(heatLevel(cold, 0, 1)).toBe(0);
  });

  it("los tonos de la rampa salen del cuerpo de «Inicio»", () => {
    const { data } = decodeBody(BODY_ONE, BODY_W, BODY_H);
    const colors = new Set<number>();
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] === 255) colors.add((data[i]! << 16) | (data[i + 1]! << 8) | data[i + 2]!);
    }
    const found = [...colors].map((c) => [c >> 16, (c >> 8) & 255, c & 255]);
    for (const hex of THERMAL_RAMP) {
      const target = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
      // La mediana por canal no tiene por qué ser un píxel exacto: basta uno muy parecido.
      const nearest = Math.min(...found.map((c) => Math.hypot(c[0]! - target[0]!, c[1]! - target[1]!, c[2]! - target[2]!)));
      expect(nearest, hex).toBeLessThan(12);
    }
  });

  it("la rampa va del azul al rojo", () => {
    const [r0, , b0] = rampColor(0);
    const [r1, , b1] = rampColor(1);
    expect(b0).toBeGreaterThan(r0);
    expect(r1).toBeGreaterThan(b1);
  });

  it("columna y escápulas cálidas, miembros azules, como el frente a esas alturas", () => {
    // Columna entre las escápulas: amarillo verdoso o más.
    expect(heatLevel(BACK_HEAT, 0, 1.3)).toBeGreaterThan(0.6);
    // Escápula: verde.
    expect(heatLevel(BACK_HEAT, 0.11, 1.28)).toBeGreaterThan(0.4);
    // Gemelo, muslo y cabeza: azul.
    expect(heatLevel(BACK_HEAT, 0.09, 0.35)).toBeLessThan(0.25);
    expect(heatLevel(BACK_HEAT, 0.09, 0.6)).toBeLessThan(0.15);
    expect(heatLevel(BACK_HEAT, 0, 1.65)).toBeLessThan(0.25);
    // Sin corazón: nada llega al rojo.
    for (let y = 0; y <= BODY_HEIGHT; y += 0.02) {
      for (let x = -0.4; x <= 0.4; x += 0.02) expect(heatLevel(BACK_HEAT, x, y)).toBeLessThan(0.85);
    }
  });
});

describe("proyección trasera sobre la malla", () => {
  const vertices = BODY.flatMap((item) => {
    const { positions } = surfaceOf(item);
    const out: [number, number, number][] = [];
    for (let i = 0; i < positions.length; i += 3) out.push([positions[i]!, positions[i + 1]!, positions[i + 2]!]);
    return out;
  });

  it("todo el cuerpo cae dentro de la textura, con margen", () => {
    for (const [x, y] of vertices) {
      const [u, v] = projectBack(x, y);
      expect(u).toBeGreaterThan(0.02);
      expect(u).toBeLessThan(0.98);
      expect(v).toBeGreaterThan(0.01);
      expect(v).toBeLessThan(0.99);
    }
  });

  it("la coronilla de la malla cae en la fila de la coronilla y en la columna del eje", () => {
    const crown = vertices.reduce((best, p) => (p[1] > best[1] ? p : best));
    const [u, v] = projectBack(crown[0], crown[1]);
    const [, expected] = projectBack(0, BODY_HEIGHT);
    expect(Math.abs(v - expected) * height).toBeLessThan(4);
    expect(Math.abs(u - 0.5) * width).toBeLessThan(4);
  });

  it("lo que se dibuja en la mano izquierda (+x) es lo que el sombreador lee en la mano izquierda de la malla", () => {
    // El rasterizado y el sombreador calculan la posición cada uno a su manera (píxeles frente a
    // coeficientes u, v): aquí se cruzan sobre el vértice más abierto de cada lado de la malla.
    const left = vertices.reduce((best, p) => (p[0] > best[0] ? p : best));
    const right = vertices.reduce((best, p) => (p[0] < best[0] ? p : best));
    expect(left[0]).toBeGreaterThan(0.25);
    expect(right[0]).toBeLessThan(-0.25);
    const art: BackArt = {
      heat: { base: 0.1, spots: [] },
      strokes: [{ points: [[left[0], left[1] - 0.01], [left[0], left[1] + 0.01]], width: 0.01 }],
    };
    const rgba = rasterizeBack(art);
    const { u0, uScale, v0, vScale } = backCoefficients();
    const sample = ([x, y]: readonly number[]) => {
      const column = Math.floor((u0 + uScale * x!) * width);
      const row = Math.floor((v0 + vScale * y!) * height);
      const i = row * width + column;
      return brightness(Array.from(rgba.slice(i * 4, i * 4 + 3)));
    };
    const background = brightness(rampColor(0.1));
    expect(sample(left)).toBeGreaterThan(background + 200);
    expect(sample([right[0], left[1]])).toBeLessThan(background + 3);
    // Y con la misma escala: 4 mm hacia fuera del vértice (el trazo mide 1 cm), aún en el núcleo.
    expect(sample([left[0] + 0.004, left[1]])).toBeGreaterThan(background + 100);
    expect(metersPerPixel()).toBeLessThan(0.002);
  });

  it("los coeficientes del sombreador dan lo mismo que la función, en metros cuadrados", () => {
    const { u0, uScale, v0, vScale } = backCoefficients();
    for (const [x, y] of [[0.26, 1.37], [-0.35, 0.75], [0.1, 0.05]] as const) {
      const [u, v] = projectBack(x, y);
      expect(u0 + uScale * x).toBeCloseTo(u, 10);
      expect(v0 + vScale * y).toBeCloseTo(v, 10);
    }
    // La misma escala en x y en y: un círculo dibujado sale redondo en el cuerpo.
    expect(uScale * width).toBeCloseTo(-vScale * height, 10);
  });
});

/** Luminancia relativa (0-255) de un color sRGB, sin linealizar: basta para comparar claro y oscuro. */
const luma = (rgb: readonly number[]) => 0.2126 * rgb[0]! + 0.7152 * rgb[1]! + 0.0722 * rgb[2]!;

/** Matiz en grados (0 rojo, 120 verde, 240 azul) y saturación (0-1) de un color sRGB. */
function hueOf([r, g, b]: readonly number[]): { hue: number; saturation: number } {
  const max = Math.max(r!, g!, b!);
  const min = Math.min(r!, g!, b!);
  const span = max - min;
  let hue = 0;
  if (span > 0) {
    if (max === r) hue = 60 * (((g! - b!) / span) % 6);
    else if (max === g) hue = 60 * ((b! - r!) / span + 2);
    else hue = 60 * ((r! - g!) / span + 4);
  }
  return { hue: (hue + 360) % 360, saturation: max === 0 ? 0 : span / max };
}

/** Un rectángulo como contorno de músculo: puntos cada centímetro, para que los lados salgan rectos. */
function box(x0: number, y0: number, x1: number, y1: number): BackPoint[] {
  const points: BackPoint[] = [];
  const side = (a: BackPoint, b: BackPoint) => {
    const count = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 0.01);
    for (let k = 0; k < count; k += 1) {
      points.push([a[0] + ((b[0] - a[0]) * k) / count, a[1] + ((b[1] - a[1]) * k) / count]);
    }
  };
  side([x0, y0], [x1, y0]);
  side([x1, y0], [x1, y1]);
  side([x1, y1], [x0, y1]);
  side([x0, y1], [x0, y0]);
  return points;
}

/** Un círculo de radio `r` en (x, y), con doce puntos. */
function circle(x: number, y: number, r: number): BackPoint[] {
  return Array.from(
    { length: 12 },
    (_, k) => [x + r * Math.cos((k * Math.PI) / 6), y + r * Math.sin((k * Math.PI) / 6)] as const,
  );
}

describe("músculos y huesos de la espalda", () => {
  const flat: BackArt["heat"] = { base: 0.5, spots: [] };
  const distance = (a: readonly number[], b: readonly number[]) =>
    Math.hypot(a[0]! - b[0]!, a[1]! - b[1]!, a[2]! - b[2]!);

  it("el vientre de un músculo sale más claro y más templado que su borde", () => {
    const muscle: BackMuscle = { outline: circle(0, 1, 0.05), belly: 0.66, edge: 0.36, groove: 0, rim: 0 };
    const rgba = rasterizeBack({ heat: flat, muscles: [muscle], strokes: [] });
    const center = pixelAt(rgba, 0, 1);
    const rim = pixelAt(rgba, 0.046, 1);
    expect(distance(center, rampColor(0.66))).toBeLessThan(6);
    // Junto al borde, el color del nivel del borde y no el del vientre.
    expect(distance(rim, rampColor(0.36))).toBeLessThan(distance(rim, rampColor(0.66)));
    expect(luma(center)).toBeGreaterThan(luma(rim) + 5);
    // Por fuera, el fondo tal cual: el músculo no se sale de su contorno.
    expect(distance(pixelAt(rgba, 0.06, 1), rampColor(0.5))).toBeLessThan(2);
  });

  it("con `shape`, el vientre está donde se dice y no en el centro", () => {
    const muscle: BackMuscle = {
      outline: circle(0, 1, 0.05),
      belly: 0.7,
      edge: 0.3,
      shape: [[0.025, 1]],
      groove: 0,
      rim: 0,
    };
    const rgba = rasterizeBack({ heat: flat, muscles: [muscle], strokes: [] });
    expect(distance(pixelAt(rgba, 0.025, 1), rampColor(0.7))).toBeLessThan(6);
    expect(luma(pixelAt(rgba, 0.025, 1))).toBeGreaterThan(luma(pixelAt(rgba, -0.025, 1)));
  });

  it("el que va después tapa al de antes", () => {
    const under: BackMuscle = { outline: circle(0, 1, 0.05), belly: 0.3, edge: 0.3, groove: 0, rim: 0 };
    const over: BackMuscle = { outline: circle(0, 1, 0.03), belly: 0.7, edge: 0.7, groove: 0, rim: 0 };
    const rgba = rasterizeBack({ heat: flat, muscles: [under, over], strokes: [] });
    expect(distance(pixelAt(rgba, 0, 1), rampColor(0.7))).toBeLessThan(3);
    expect(distance(pixelAt(rgba, 0.04, 1), rampColor(0.3))).toBeLessThan(3);
  });

  it("el surco entre dos músculos sale más oscuro y más frío que los dos lados", () => {
    const left: BackMuscle = { outline: box(-0.06, 0.95, 0, 1.05), belly: 0.55, edge: 0.45, rim: 0 };
    const right: BackMuscle = { outline: box(0, 0.95, 0.06, 1.05), belly: 0.55, edge: 0.45, rim: 0 };
    const rgba = rasterizeBack({ heat: flat, muscles: [left, right], strokes: [] });
    const groove = pixelAt(rgba, 0, 1);
    for (const side of [-0.02, 0.02]) {
      const beside = pixelAt(rgba, side, 1);
      expect(luma(groove), `a ${side} m`).toBeLessThan(luma(beside) - 20);
      // Más frío: más azul por cada verde.
      expect(groove[2]! / Math.max(1, groove[1]!)).toBeGreaterThan(beside[2]! / Math.max(1, beside[1]!));
    }
    // Sin surco (`groove: 0`), el borde no se oscurece.
    const plain = rasterizeBack({
      heat: flat,
      muscles: [
        { ...left, groove: 0 },
        { ...right, groove: 0 },
      ],
      strokes: [],
    });
    expect(luma(pixelAt(plain, 0, 1))).toBeGreaterThan(luma(groove) + 20);
  });

  it("con el contorno por defecto, el surco asoma oscuro a los lados del brillo", () => {
    const left: BackMuscle = { outline: box(-0.06, 0.95, 0, 1.05), belly: 0.55, edge: 0.45 };
    const right: BackMuscle = { outline: box(0, 0.95, 0.06, 1.05), belly: 0.55, edge: 0.45 };
    const rgba = rasterizeBack({ heat: flat, muscles: [left, right], strokes: [] });
    // En el borde, el brillo del contorno; a 7 mm, el surco; a 2 cm, el vientre.
    expect(luma(pixelAt(rgba, 0, 1))).toBeGreaterThan(luma(pixelAt(rgba, 0.02, 1)));
    for (const side of [-1, 1]) {
      expect(luma(pixelAt(rgba, side * 0.007, 1)), `lado ${side}`).toBeLessThan(luma(pixelAt(rgba, side * 0.02, 1)) - 10);
    }
  });

  it("un contorno que pasa junto a un hueso no apaga la cresta", () => {
    const bone = { points: [[-0.05, 1], [0.05, 1]] as BackPoint[], width: 0.006 };
    const alone = pixelAt(rasterizeBack({ heat: flat, bones: [bone], strokes: [] }), 0, 1);
    const near = rasterizeBack({ heat: flat, bones: [bone], strokes: [{ points: [[-0.05, 0.992], [0.05, 0.992]], width: 0.007 }] });
    expect(luma(pixelAt(near, 0, 1))).toBeGreaterThanOrEqual(luma(alone) - 1);
  });

  it("un hueso sale más claro que lo que le rodea, con una sombra fina debajo", () => {
    const points: BackPoint[] = [
      [-0.05, 1],
      [0.05, 1],
    ];
    const rgba = rasterizeBack({ heat: flat, bones: [{ points, width: 0.006 }], strokes: [] });
    const background = rampColor(0.5);
    const crest = pixelAt(rgba, 0, 1);
    expect(luma(crest)).toBeGreaterThan(luma(background) + 40);
    for (const dy of [0.015, -0.015]) expect(luma(crest)).toBeGreaterThan(luma(pixelAt(rgba, 0, 1 + dy)) + 40);
    // La sombra: por defecto, un ancho hacia abajo; arriba, ninguna.
    expect(luma(pixelAt(rgba, 0, 0.992))).toBeLessThan(luma(background) - 20);
    expect(luma(pixelAt(rgba, 0, 1.008))).toBeGreaterThanOrEqual(luma(background) - 1);
    // Más brillante que un contorno o un trazo del mismo ancho.
    const line = rasterizeBack({ heat: flat, strokes: [{ points, width: 0.006 }] });
    expect(luma(crest)).toBeGreaterThan(luma(pixelAt(line, 0, 1)));
  });

  it("el contorno es un brillo teñido del tono de debajo, no blanco", () => {
    for (const [level, from, to] of [
      [0.5, 60, 130], // sobre verde, amarillo verdoso
      [0.1, 150, 200], // sobre azul, cian claro
      [0.95, 40, 70], // sobre rojo, amarillo (como el corazón del frente), no rosa
    ] as const) {
      const muscle: BackMuscle = { outline: circle(0, 1, 0.05), belly: level, edge: level, groove: 0 };
      const rgba = rasterizeBack({ heat: { base: level, spots: [] }, muscles: [muscle], strokes: [] });
      // El contorno pasa por (0,05, 1), uno de sus puntos: ahí está su núcleo.
      const rim = pixelAt(rgba, 0.05, 1);
      const { hue, saturation } = hueOf(rim);
      expect(hue, `nivel ${level}`).toBeGreaterThanOrEqual(from);
      expect(hue, `nivel ${level}`).toBeLessThanOrEqual(to);
      expect(saturation, `nivel ${level}`).toBeGreaterThan(0.3);
      expect(luma(rim), `nivel ${level}`).toBeGreaterThan(luma(rampColor(level)) + 15);
      expect(distance(rim, glintColor(level))).toBeLessThan(25);
    }
  });

  it("`bilateralMuscles` y `bilateralBones` reflejan contorno, vientre y sombra", () => {
    const [, muscle] = bilateralMuscles([
      { outline: [[0.1, 1], [0.2, 1], [0.15, 1.1]], belly: 0.6, edge: 0.4, shape: [[0.15, 1.03]] },
    ]);
    expect(muscle!.outline).toEqual([[-0.1, 1], [-0.2, 1], [-0.15, 1.1]]);
    expect(muscle!.shape).toEqual([[-0.15, 1.03]]);
    const [, bone] = bilateralBones([{ points: [[0.1, 1], [0.2, 1]], width: 0.005, shadow: [0.003, -0.004] }]);
    expect(bone!.points).toEqual([[-0.1, 1], [-0.2, 1]]);
    expect(bone!.shadow).toEqual([-0.003, -0.004]);
  });

  it("los músculos y huesos del dibujo caen dentro de la textura, con el vientre más templado que el borde", () => {
    const inTexture = ([x, y]: BackPoint) => {
      const [u, v] = projectBack(x, y);
      return u >= 0 && u <= 1 && v >= 0 && v <= 1;
    };
    expect(BACK_ART.muscles?.length).toBeGreaterThan(0);
    expect(BACK_ART.bones?.length).toBeGreaterThan(0);
    for (const [index, muscle] of (BACK_ART.muscles ?? []).entries()) {
      expect(muscle.outline.length, `músculo ${index}`).toBeGreaterThanOrEqual(3);
      expect(muscle.belly, `músculo ${index}`).toBeGreaterThan(muscle.edge);
      expect([...muscle.outline, ...(muscle.shape ?? [])].every(inTexture), `músculo ${index}`).toBe(true);
    }
    for (const [index, bone] of (BACK_ART.bones ?? []).entries()) {
      expect(bone.points.length, `hueso ${index}`).toBeGreaterThanOrEqual(2);
      expect(bone.width, `hueso ${index}`).toBeGreaterThan(0);
      expect(bone.points.every(inTexture), `hueso ${index}`).toBe(true);
    }
  });
});
