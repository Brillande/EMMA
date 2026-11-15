import { describe, expect, it } from "vitest";

import {
  CHIN,
  type FacePoint,
  LEFT_EYE,
  MIN_EYE_SPAN_PX,
  RIGHT_EYE,
  cameraIsOn,
  eyeLineAngle,
  faceHoldsView,
  faceRotation,
  faceStatusOf,
  readFaces,
} from "./faceOrientation";

/**
 * La vista que sigue la cara (§5.40, demostración): de los ojos al ángulo, del ángulo al
 * cuadrante, y qué pasa sin cara o con varias. La cámara y el detector (`faceCamera.ts`) no se
 * prueban sin navegador.
 */

const WIDTH = 320;
const HEIGHT = 240;

/**
 * Una cara de mentira con los cuatro rabillos puestos: los ojos de la persona en píxeles de la
 * imagen de la cámara (sin espejo: su ojo derecho sale a la izquierda de la imagen).
 */
function face(right: [number, number], left: [number, number], chin?: [number, number]): FacePoint[] {
  // Los puntos que no se ponen no valen: sin barbilla, el ángulo sale solo de los ojos.
  const points: FacePoint[] = Array.from({ length: 478 }, () => ({ x: Number.NaN, y: Number.NaN }));
  const put = (indexes: readonly number[], [x, y]: [number, number]) => {
    for (const index of indexes) points[index] = { x: x / WIDTH, y: y / HEIGHT };
  };
  put(RIGHT_EYE, right);
  put(LEFT_EYE, left);
  if (chin !== undefined) put([CHIN], chin);
  return points;
}

describe("de los ojos al ángulo", () => {
  it("una cara derecha delante de la pantalla da 0", () => {
    expect(eyeLineAngle(face([130, 100], [190, 100]), WIDTH, HEIGHT)).toBe(0);
  });

  it("la cabeza hacia el borde derecho de la pantalla da 90, y hacia el izquierdo 270", () => {
    // Cabeza a la derecha de la pantalla: su derecha apunta hacia abajo; en la imagen, su ojo
    // derecho queda debajo del izquierdo.
    expect(eyeLineAngle(face([160, 150], [160, 90]), WIDTH, HEIGHT)).toBeCloseTo(90);
    expect(eyeLineAngle(face([160, 90], [160, 150]), WIDTH, HEIGHT)).toBeCloseTo(270);
  });

  it("cabeza abajo da 180", () => {
    expect(eyeLineAngle(face([190, 100], [130, 100]), WIDTH, HEIGHT)).toBeCloseTo(180);
  });

  it("la imagen no lleva espejo: el mismo giro en el sentido del reloj sale positivo", () => {
    // La persona gira la cabeza 30° en el sentido del reloj (vista por ella en la pantalla): su
    // ojo derecho baja. En la imagen sin espejo ese ojo está a la izquierda.
    const angle = 30;
    const dx = 30 * Math.cos((angle * Math.PI) / 180);
    const dy = 30 * Math.sin((angle * Math.PI) / 180);
    const tilted = face([160 - dx, 120 + dy], [160 + dx, 120 - dy]);
    expect(eyeLineAngle(tilted, WIDTH, HEIGHT)).toBeCloseTo(angle);
  });

  it("las fracciones se pasan a píxeles: una imagen que no es cuadrada no tuerce el ángulo", () => {
    // 45° de verdad en píxeles; en fracciones de una imagen de 320 × 240 no lo parecería.
    expect(eyeLineAngle(face([140, 140], [180, 100]), WIDTH, HEIGHT)).toBeCloseTo(45);
  });

  it("la barbilla da el sentido: coincide con los ojos, y si los ojos salieran cambiados lo corrige", () => {
    // Derecha, con la barbilla debajo de los ojos.
    expect(eyeLineAngle(face([130, 100], [190, 100], [160, 170]), WIDTH, HEIGHT)).toBe(0);
    // Cabeza hacia la derecha de la pantalla: la barbilla, a la derecha de la imagen (sin espejo).
    expect(eyeLineAngle(face([160, 150], [160, 90], [230, 120]), WIDTH, HEIGHT)).toBeCloseTo(90);
    // Los mismos ojos con las etiquetas cambiadas: la recta diría 180, la barbilla dice 0.
    expect(eyeLineAngle(face([190, 100], [130, 100], [160, 170]), WIDTH, HEIGHT)).toBe(0);
    // Cabeza abajo de verdad: la barbilla encima de los ojos.
    expect(eyeLineAngle(face([190, 100], [130, 100], [160, 30]), WIDTH, HEIGHT)).toBeCloseTo(180);
    // Una barbilla pegada a los ojos no vale para decidir: se queda lo de los ojos.
    expect(eyeLineAngle(face([190, 100], [130, 100], [160, 102]), WIDTH, HEIGHT)).toBeCloseTo(180);
  });

  it("sin un ojo, con la recta demasiado corta o sin tamaño de imagen, no hay ángulo", () => {
    // Una malla cortada antes del rabillo interior del ojo izquierdo (362).
    expect(eyeLineAngle(face([130, 100], [190, 100]).slice(0, 300), WIDTH, HEIGHT)).toBeNull();
    const close = MIN_EYE_SPAN_PX - 1;
    expect(eyeLineAngle(face([160, 100], [160 + close, 100]), WIDTH, HEIGHT)).toBeNull();
    expect(eyeLineAngle(face([160, 100], [160 + MIN_EYE_SPAN_PX + 1, 100]), WIDTH, HEIGHT)).toBe(0);
    expect(eyeLineAngle(face([130, 100], [190, 100]), 0, HEIGHT)).toBeNull();
    expect(eyeLineAngle([{ x: Number.NaN, y: 0 }], WIDTH, HEIGHT)).toBeNull();
  });
});

describe("lo que vio la cámara", () => {
  const upright = face([130, 100], [190, 100]);

  it("ninguna cara, o una que no se ve bien, es «sin cara»", () => {
    expect(readFaces([], WIDTH, HEIGHT)).toEqual({ kind: "none" });
    expect(readFaces([face([160, 100], [162, 100])], WIDTH, HEIGHT)).toEqual({ kind: "none" });
    expect(faceStatusOf({ kind: "none" })).toBe("noFace");
  });

  it("una cara da su ángulo", () => {
    expect(readFaces([upright], WIDTH, HEIGHT)).toEqual({ kind: "one", angle: 0 });
    expect(faceStatusOf({ kind: "one", angle: 0 })).toBe("face");
  });

  it("dos caras: no se elige a nadie, y se dice cuántas", () => {
    expect(readFaces([upright, upright], WIDTH, HEIGHT)).toEqual({ kind: "several", count: 2 });
    expect(faceStatusOf({ kind: "several", count: 2 })).toBe("several");
  });
});

describe("del ángulo al cuadrante", () => {
  it("una cara mueve la vista con la histéresis del sensor, sin saltar cerca de 45°", () => {
    expect(faceRotation(0, { kind: "one", angle: 50 })).toBe(0);
    expect(faceRotation(0, { kind: "one", angle: 61 })).toBe(90);
    expect(faceRotation(90, { kind: "one", angle: 40 })).toBe(90);
    expect(faceRotation(90, { kind: "one", angle: 29 })).toBe(0);
    expect(faceRotation(0, { kind: "one", angle: 185 })).toBe(180);
    expect(faceRotation(0, { kind: "one", angle: 300 })).toBe(0);
    expect(faceRotation(0, { kind: "one", angle: 290 })).toBe(270);
  });

  it("sin cara o con varias, la vista se queda como está", () => {
    expect(faceRotation(270, { kind: "none" })).toBe(270);
    expect(faceRotation(90, { kind: "several", count: 3 })).toBe(90);
  });
});

describe("con el sensor también encendido", () => {
  it("manda la cara mientras ve una o varias; sin cara, o sin cámara, sigue el sensor", () => {
    expect(faceHoldsView("face")).toBe(true);
    expect(faceHoldsView("several")).toBe(true);
    for (const status of ["off", "starting", "noFace", "unavailable"] as const) {
      expect(faceHoldsView(status), status).toBe(false);
    }
  });
});

describe("el aviso de cámara encendida", () => {
  it("sale en cuanto la cámara está encendida, vea o no una cara, y en ningún otro estado", () => {
    for (const status of ["noFace", "face", "several"] as const) expect(cameraIsOn(status), status).toBe(true);
    for (const status of ["off", "starting", "unavailable"] as const) expect(cameraIsOn(status), status).toBe(false);
  });
});
