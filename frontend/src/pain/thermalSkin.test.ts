import { describe, expect, it } from "vitest";

import { BODY_H, BODY_ONE, BODY_W } from "../dashboard/referenceBody.generated";
import { BODY_HEIGHT } from "./bodyModel";
import { blur, decodeBody, dilate, projectThermal, THERMAL_PROJECTION, thermalCoefficients } from "./thermalSkin";

describe("proyección de los colores de «Inicio» sobre el cuerpo", () => {
  it("el tamaño declarado es el de la imagen", () => {
    expect(THERMAL_PROJECTION.width).toBe(BODY_W);
    expect(THERMAL_PROJECTION.height).toBe(BODY_H);
  });

  it("la coronilla cae en la fila 9 y los pies en la 301, sobre el eje en la columna 73", () => {
    const [u, top] = projectThermal(0, BODY_HEIGHT);
    expect(Math.floor(u * BODY_W)).toBe(73);
    expect(Math.floor(top * BODY_H)).toBe(9);
    const [, feet] = projectThermal(0, 0);
    expect(Math.floor(feet * BODY_H)).toBe(301);
  });

  it("la escala es de unos 0,0059 m por píxel en las dos direcciones", () => {
    const [u0, v0] = projectThermal(0, 1);
    const [u1, v1] = projectThermal(0.1, 0.9);
    expect(0.1 / ((u1 - u0) * BODY_W)).toBeCloseTo(0.0059, 4);
    expect(0.1 / ((v1 - v0) * BODY_H)).toBeCloseTo(0.0059, 4);
  });

  it("la derecha del tripulante (−x) cae a la izquierda de la imagen", () => {
    expect(projectThermal(-0.2, 1)[0]).toBeLessThan(projectThermal(0.2, 1)[0]);
  });

  it("los coeficientes del sombreador dan lo mismo que la función", () => {
    const { u0, uScale, v0, vScale } = thermalCoefficients();
    for (const [x, y] of [
      [0.26, 1.37],
      [-0.35, 0.75],
      [0.1, 0.05],
    ] as const) {
      const [u, v] = projectThermal(x, y);
      expect(u0 + uScale * x).toBeCloseTo(u, 10);
      expect(v0 + vScale * y).toBeCloseTo(v, 10);
    }
  });

  it("el hombro y la mano de la tabla medida caen dentro de la silueta", () => {
    const rgba = decodeBody(BODY_ONE, BODY_W, BODY_H).data;
    const opaque = (x: number, y: number) => {
      const [u, v] = projectThermal(x, y);
      const i = Math.floor(v * BODY_H) * BODY_W + Math.floor(u * BODY_W);
      return rgba[i * 4 + 3] === 255;
    };
    expect(opaque(0, 1.2)).toBe(true); // tórax
    expect(opaque(-0.24, 1.37)).toBe(true); // hombro derecho
    expect(opaque(0.24, 1.37)).toBe(true); // hombro izquierdo
    expect(opaque(-0.35, 0.78)).toBe(true); // mano derecha
    expect(opaque(0.35, 0.78)).toBe(true); // mano izquierda
    expect(opaque(0, 0.6)).toBe(false); // entre los muslos
  });
});

/** Imagen de 5×1: rojo, verde, y tres transparentes; o la que se dé. */
function strip(pixels: readonly (readonly [number, number, number] | null)[]): Uint8Array {
  const data = new Uint8Array(pixels.length * 4);
  pixels.forEach((color, i) => {
    if (color === null) return;
    data.set([...color, 255], i * 4);
  });
  return data;
}

describe("dilatación de la silueta", () => {
  it("lo transparente toma el color del opaco más cercano y todo queda opaco", () => {
    const red = [255, 0, 0] as const;
    const green = [0, 255, 0] as const;
    const out = dilate(strip([null, red, null, null, null, green, null]), 7, 1);
    const at = (i: number) => Array.from(out.slice(i * 4, i * 4 + 4));
    expect(at(0)).toEqual([255, 0, 0, 255]);
    expect(at(2)).toEqual([255, 0, 0, 255]);
    expect(at(4)).toEqual([0, 255, 0, 255]);
    expect(at(6)).toEqual([0, 255, 0, 255]);
    for (let i = 0; i < 7; i += 1) expect(out[i * 4 + 3]).toBe(255);
  });

  it("no toca los píxeles opacos ni la imagen de entrada", () => {
    const input = strip([[10, 20, 30], null, [40, 50, 60]]);
    const copy = new Uint8Array(input);
    const out = dilate(input, 3, 1);
    expect(Array.from(input)).toEqual(Array.from(copy));
    expect(Array.from(out.slice(0, 3))).toEqual([10, 20, 30]);
    expect(Array.from(out.slice(8, 11))).toEqual([40, 50, 60]);
  });

  it("con `inset`, el contorno claro se sustituye por el color de dentro", () => {
    const rim = [250, 250, 250] as const;
    const core = [0, 0, 200] as const;
    const out = dilate(strip([null, rim, core, core, core, rim, null]), 7, 1, 1);
    for (let i = 0; i < 7; i += 1) {
      expect(Array.from(out.slice(i * 4, i * 4 + 4)), `píxel ${i}`).toEqual([0, 0, 200, 255]);
    }
  });

  it("con `inset` mayor que la figura, se usa la figura sin recortar", () => {
    const out = dilate(strip([null, [9, 9, 9], null]), 3, 1, 5);
    expect(Array.from(out)).toEqual([9, 9, 9, 255, 9, 9, 9, 255, 9, 9, 9, 255]);
  });

  it("sobre `BODY_ONE`, fuera de la silueta no queda nada negro", () => {
    const { inset } = THERMAL_PROJECTION;
    const out = dilate(decodeBody(BODY_ONE, BODY_W, BODY_H).data, BODY_W, BODY_H, inset);
    const holes: number[] = [];
    for (let i = 0; i < BODY_W * BODY_H; i += 1) {
      if (out[i * 4 + 3] !== 255 || out[i * 4]! + out[i * 4 + 1]! + out[i * 4 + 2]! === 0) holes.push(i);
    }
    expect(holes).toEqual([]);
  });
});

describe("copia borrosa para los costados y la espalda", () => {
  it("promedia con el borde repetido y conserva el alfa", () => {
    const input = strip([[0, 0, 0], [90, 90, 90], [0, 0, 0]]);
    const out = blur(input, 3, 1, 1);
    expect(Array.from(out.slice(4, 8))).toEqual([30, 30, 30, 255]);
    // En el borde se repite el propio píxel: (0 + 0 + 90) / 3.
    expect(Array.from(out.slice(0, 4))).toEqual([30, 30, 30, 255]);
  });

  it("una imagen lisa sale igual", () => {
    const flat = strip(Array.from({ length: 6 }, () => [12, 34, 56] as const));
    expect(Array.from(blur(flat, 3, 2, 2))).toEqual(Array.from(flat));
  });
});
