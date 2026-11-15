import { describe, expect, it } from "vitest";

import {
  DEAD_ZONE_RAD_S,
  HYSTERESIS_DEGREES,
  MAX_GAP_SECONDS,
  followQuadrant,
  integrateTurn,
  nearestQuadrant,
  normalizeDegrees,
  quaternionFromEuler,
  screenTwist,
  signedDelta,
  upReference,
  viewAngle,
} from "./orientation";

/**
 * El giro por sensor (§5.40): todo lo que decide a qué cuadrante va la vista es puro y se prueba
 * aquí. Lo que escucha al sensor (`watchOrientation`) no se prueba sin navegador ni sensor real.
 */

describe("ángulos", () => {
  it("se normalizan a [0, 360), sin -0 ni 360", () => {
    expect(normalizeDegrees(0)).toBe(0);
    expect(Object.is(normalizeDegrees(-0), 0)).toBe(true);
    expect(normalizeDegrees(360)).toBe(0);
    expect(normalizeDegrees(-90)).toBe(270);
    expect(normalizeDegrees(725)).toBe(5);
    expect(normalizeDegrees(-1e-14)).toBe(0);
  });

  it("la diferencia va por el camino corto, en (-180, 180]", () => {
    expect(signedDelta(350, 10)).toBe(20);
    expect(signedDelta(10, 350)).toBe(-20);
    expect(signedDelta(0, 180)).toBe(180);
    expect(signedDelta(90, 90)).toBe(0);
  });
});

describe("cuadrante más cercano", () => {
  it("cada ángulo va a 0, 90, 180 o 270", () => {
    expect(nearestQuadrant(0)).toBe(0);
    expect(nearestQuadrant(44)).toBe(0);
    expect(nearestQuadrant(46)).toBe(90);
    expect(nearestQuadrant(181)).toBe(180);
    expect(nearestQuadrant(300)).toBe(270);
    expect(nearestQuadrant(316)).toBe(0);
    expect(nearestQuadrant(-30)).toBe(0);
    expect(nearestQuadrant(-80)).toBe(270);
  });
});

describe("histéresis", () => {
  it("cerca de 45° no salta: sigue en el cuadrante actual hasta 45° + la banda", () => {
    expect(HYSTERESIS_DEGREES).toBeGreaterThan(0);
    const edge = 45 + HYSTERESIS_DEGREES;
    expect(followQuadrant(0, 46)).toBe(0);
    expect(followQuadrant(0, edge)).toBe(0);
    expect(followQuadrant(0, edge + 1)).toBe(90);
    expect(followQuadrant(0, -(edge + 1))).toBe(270);
  });

  it("al volver hay que pasar la banda del otro lado: un temblor en 45° no hace parpadear la vista", () => {
    let rotation = followQuadrant(0, 61);
    expect(rotation).toBe(90);
    for (const angle of [44, 46, 40, 50, 35, 55, 31]) {
      rotation = followQuadrant(rotation, angle);
      expect(rotation).toBe(90);
    }
    expect(followQuadrant(rotation, 29)).toBe(0);
  });

  it("un salto grande va directo al cuadrante más cercano", () => {
    expect(followQuadrant(0, 175)).toBe(180);
    expect(followQuadrant(90, 275)).toBe(270);
  });

  it("da la vuelta por 0 sin saltos raros", () => {
    expect(followQuadrant(270, 320)).toBe(270);
    expect(followQuadrant(270, 335)).toBe(0);
    expect(followQuadrant(0, 320)).toBe(0);
    expect(followQuadrant(0, 295)).toBe(270);
  });
});

describe("referencia «esto es arriba»", () => {
  it("al fijarla, la vista se queda como está", () => {
    const reading = { turn: 123, screen: 0 };
    expect(viewAngle(upReference(90, reading), reading)).toBe(90);
    expect(viewAngle(upReference(0, reading), reading)).toBe(0);
  });

  it("la tableta gira en contra del reloj y la vista gira a favor, lo mismo", () => {
    const reference = upReference(0, { turn: 10, screen: 0 });
    expect(viewAngle(reference, { turn: 100, screen: 0 })).toBe(90);
    expect(viewAngle(reference, { turn: -80, screen: 0 })).toBe(270);
    expect(viewAngle(upReference(180, { turn: 0, screen: 0 }), { turn: 90, screen: 0 })).toBe(270);
  });

  it("lo que el sistema operativo ya giró se descuenta: no se gira dos veces", () => {
    const reference = upReference(0, { turn: 0, screen: 0 });
    expect(viewAngle(reference, { turn: 90, screen: 90 })).toBe(0);
    expect(viewAngle(reference, { turn: 180, screen: 90 })).toBe(90);
  });
});

describe("integrar el giroscopio", () => {
  it("suma la velocidad sobre el eje de la pantalla, en grados", () => {
    expect(integrateTurn(0, Math.PI / 2, 0.1)).toBeCloseTo(9);
    expect(integrateTurn(10, -Math.PI, 0.1)).toBeCloseTo(-8);
  });

  it("un hueco largo, un tiempo que no avanza o una lectura rota no se suman", () => {
    expect(integrateTurn(5, 1, MAX_GAP_SECONDS + 0.01)).toBe(5);
    expect(integrateTurn(5, 1, 0)).toBe(5);
    expect(integrateTurn(5, 1, -0.1)).toBe(5);
    expect(integrateTurn(5, Number.NaN, 0.1)).toBe(5);
  });

  it("por debajo de la zona muerta no se integra: la tableta quieta no acumula ruido", () => {
    expect(DEAD_ZONE_RAD_S).toBeGreaterThan(0);
    let turn = 0;
    for (let i = 0; i < 1000; i++) turn = integrateTurn(turn, (i % 2 === 0 ? 1 : -1) * DEAD_ZONE_RAD_S * 0.9, 0.05);
    expect(turn).toBe(0);
    expect(integrateTurn(0, DEAD_ZONE_RAD_S * 2, 0.1)).toBeGreaterThan(0);
  });
});

describe("giro sobre el plano de la pantalla desde la orientación", () => {
  it("con la tableta plana es la diferencia de alfa", () => {
    expect(screenTwist(quaternionFromEuler(10, 0, 0), quaternionFromEuler(100, 0, 0))).toBeCloseTo(90);
    expect(screenTwist(quaternionFromEuler(0, 0, 0), quaternionFromEuler(-30, 0, 0))).toBeCloseTo(-30);
  });

  it("con la tableta de pie, girar en su plano también se lee como giro", () => {
    // De pie (beta 90), girar sobre el eje de la pantalla es componer un giro en z del equipo.
    const upright = quaternionFromEuler(0, 90, 0);
    const half = Math.PI / 8; // la mitad de 45°: el cuaternión lleva medio ángulo
    const turned = {
      w: upright.w * Math.cos(half) - upright.z * Math.sin(half),
      x: upright.x * Math.cos(half) + upright.y * Math.sin(half),
      y: upright.y * Math.cos(half) - upright.x * Math.sin(half),
      z: upright.z * Math.cos(half) + upright.w * Math.sin(half),
    };
    expect(screenTwist(upright, turned)).toBeCloseTo(45);
  });

  it("inclinar sin girar no es giro", () => {
    expect(screenTwist(quaternionFromEuler(0, 0, 0), quaternionFromEuler(0, 30, 0))).toBeCloseTo(0);
  });

  it("con la pantalla dada la vuelta no hay giro que leer", () => {
    expect(screenTwist(quaternionFromEuler(0, 0, 0), quaternionFromEuler(0, 180, 0))).toBeNull();
  });
});
