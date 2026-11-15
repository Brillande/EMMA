/**
 * Pictogramas de la consola de Tierra: marco de NASA, riesgos, coste de medir, proyecciones,
 * documentación, copia de Polaris y registro firmado (`ground/`).
 *
 * Tierra es un inventario denso (§4.1 del estado del arte): aquí no hay alertas, hay grados de
 * cuánto se ha ejercitado una hipótesis, el estado leído de un hueco del Roadmap, cuánto se leyó
 * de un documento, con qué se mide un indicador y de qué clase es cada asiento del ledger. Cada
 * forma que la consola ya pintaba como carácter (▱ ◔ ◑ ◎ ⦸ ↣ ▭ ⋔ ◧ ▪ ≠ ▌) conserva su dibujo; lo
 * que no tenía forma (clases de medida, dimensiones del coste, tipos de asiento, exportar y
 * buscar) la gana con un objeto reconocible a 12 px. El nombre describe el dibujo; el significado
 * lo pone la palabra del backend, que va siempre al lado.
 *
 * Rejilla de 24×24, trazo de 2, todo entre 3 y 21. Los dibujos genéricos que nacieron aquí y
 * otra área también usa (lupa, calendario, tablilla, cuadro, chip, matraz, reloj de arena, campana,
 * pluma, casa) viven en `common`; y desde la segunda pasada (2026-10-21) también el engranaje
 * (sistema), el reloj que gira hacia atrás (lo anterior, el historial) y las dos rayas tachadas
 * (difiere), que nombran conceptos de toda la interfaz (`lib/uiMarks.ts`). La hoja doblada
 * (`page-folded`) era `sheet-lines` con los renglones un punto más abajo y se retiró. Aquí quedan
 * los que solo pinta Tierra (cámara, enchufes, clases de medida…). El marco y el anillo son los de
 * `shapes`, para que `square-half` se alinee con `frame-filled` y `frame-empty` a su lado.
 */

import type { PictogramSet } from "../types";
import { FRAME, RING } from "./shapes";

export const ground = {
  // --- Hipótesis de diseño: grados de cuánto se ha ejercitado, de nada a una parte ---------
  parallelogram: { elements: [{ kind: "polygon", points: "8,5 21,5 16,19 3,19" }] },
  // Un cuarto relleno, arriba a la derecha.
  "circle-quarter": { elements: [RING, { kind: "path", d: "M12 4a8 8 0 0 1 8 8h-8z", fill: true }] },
  // La mitad derecha rellena; `dot-half` (inferido) rellena la izquierda.
  "circle-half-right": { elements: [RING, { kind: "path", d: "M12 4a8 8 0 0 1 0 16z", fill: true }] },

  // --- Estado de un hueco del Roadmap ------------------------------------------------------
  "circle-double": { elements: [RING, { kind: "circle", cx: 12, cy: 12, r: 3.5 }] },
  // Barra de arriba a la izquierda a abajo a la derecha; `slash-circle` la lleva al revés.
  "circle-backslash": { elements: [RING, { kind: "line", x1: 6.34, y1: 6.34, x2: 17.66, y2: 17.66 }] },
  // Flecha a la derecha con una horquilla en la cola.
  "arrow-right-forked": {
    elements: [
      { kind: "line", x1: 5, y1: 12, x2: 19, y2: 12 },
      { kind: "polyline", points: "13,6 19,12 13,18" },
      { kind: "polyline", points: "3,8 7,12 3,16" },
    ],
  },
  "rect-wide": { elements: [{ kind: "rect", x: 3, y: 8, width: 18, height: 8 }] },
  // Tres puntas hacia arriba sobre un mango.
  pitchfork: {
    elements: [
      { kind: "path", d: "M6 4v6h12V4" },
      { kind: "line", x1: 12, y1: 4, x2: 12, y2: 21 },
    ],
  },

  // --- Alcance de lectura: la mitad izquierda del marco rellena -----------------------------
  "square-half": { elements: [FRAME, { kind: "rect", x: 4, y: 4, width: 8, height: 16, fill: true }] },

  // --- Marcas de inventario: ficha completa, clase asignada; y una discrepancia -------------
  "square-small": { elements: [{ kind: "rect", x: 8, y: 8, width: 8, height: 8, fill: true }] },

  // --- Clases de medida: onda continua, tomas sueltas, jeringa, matraz y sumatorio ----------
  "wave-smooth": { elements: [{ kind: "path", d: "M3 12c2-7 4-7 6 0s4 7 6 0s4-7 6 0" }] },
  syringe: {
    elements: [
      { kind: "rect", x: 7, y: 9, width: 9, height: 6 },
      { kind: "line", x1: 16, y1: 12, x2: 21, y2: 12 },
      { kind: "line", x1: 3, y1: 12, x2: 7, y2: 12 },
      { kind: "line", x1: 3, y1: 9, x2: 3, y2: 15 },
    ],
  },
  sigma: { elements: [{ kind: "polyline", points: "18,5 6,5 13,12 6,19 18,19" }] },

  // --- Dimensiones del coste: dónde se procesa (`chip`, en `common`), cuándo llega, consumibles --
  // Caja con una ranura y un mando: un analizador de sobremesa.
  "box-slot": {
    elements: [
      { kind: "rect", x: 3, y: 6, width: 18, height: 12 },
      { kind: "line", x1: 6, y1: 10, x2: 14, y2: 10 },
      { kind: "circle", cx: 17, cy: 14, r: 1.5 },
    ],
  },
  cartridge: {
    elements: [
      { kind: "rect", x: 5, y: 8, width: 14, height: 10 },
      { kind: "path", d: "M9 8V5h6v3" },
    ],
  },
  "cartridge-slash": {
    elements: [
      { kind: "rect", x: 5, y: 8, width: 14, height: 10 },
      { kind: "path", d: "M9 8V5h6v3" },
      { kind: "line", x1: 3, y1: 21, x2: 21, y2: 3 },
    ],
  },

  // --- Dimensiones de la base de conocimiento §9 (decimosexta ronda): masa, volumen, potencia,
  // calibración y guía del operador. Dibujos propios: los parecidos que había ya significan otra
  // cosa (la balanza es el peso corporal, la pesa trapezoidal la familia de contramedida física o
  // de masa, y el cubo, el rayo, el manómetro y los arcos de señal, lo suyo).
  // Un bulto sobre la plataforma de una báscula, con su visor: lo que pesa el equipo.
  "box-on-scale": {
    elements: [
      { kind: "rect", x: 7, y: 4, width: 10, height: 9 },
      { kind: "rect", x: 3, y: 15, width: 18, height: 5 },
      { kind: "line", x1: 9, y1: 17.5, x2: 15, y2: 17.5 },
    ],
  },
  // Caja con su cota debajo.
  "box-dimension": {
    elements: [
      { kind: "rect", x: 6, y: 3, width: 12, height: 12 },
      { kind: "line", x1: 6, y1: 20, x2: 18, y2: 20 },
      { kind: "line", x1: 6, y1: 18, x2: 6, y2: 22 },
      { kind: "line", x1: 18, y1: 18, x2: 18, y2: 22 },
    ],
  },
  // Toma de corriente redonda con dos ranuras.
  "socket-round": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 9 },
      { kind: "line", x1: 9, y1: 9, x2: 9, y2: 15 },
      { kind: "line", x1: 15, y1: 9, x2: 15, y2: 15 },
    ],
  },
  // Esfera de medio círculo con su aguja y la marca del cero.
  "dial-needle": {
    elements: [
      { kind: "path", d: "M3 17a9 9 0 0 1 18 0" },
      { kind: "line", x1: 12, y1: 17, x2: 7, y2: 11 },
      { kind: "line", x1: 3, y1: 17, x2: 6, y2: 17 },
      { kind: "circle", cx: 12, cy: 17, r: 1.5, fill: true },
    ],
  },
  // Trazo discontinuo que baja hasta un punto: lo que llega de lejos y guía la mano.
  "line-dashed-to-dot": {
    elements: [
      { kind: "path", d: "M12 3v12", dashed: true },
      { kind: "circle", cx: 12, cy: 19, r: 2.5, fill: true },
    ],
  },
  // Birrete con su borla (decimoctava ronda): quien lo usa se formó antes de la misión. El libro
  // abierto ya es el respaldo de una recomendación, y la libreta, el diario de la tripulación.
  mortarboard: {
    elements: [
      { kind: "path", d: "M2 9l10-5 10 5-10 5z" },
      { kind: "path", d: "M6 11v5c3 2.5 9 2.5 12 0v-5" },
      { kind: "line", x1: 21, y1: 9.5, x2: 21, y2: 16 },
    ],
  },
  // El mismo birrete, más arriba, sobre la línea del suelo: la formación leída en un análogo en
  // Tierra, no en vuelo.
  "mortarboard-on-ground": {
    elements: [
      { kind: "path", d: "M2 6l10-4 10 4-10 4z" },
      { kind: "path", d: "M6 8v4c3 2 9 2 12 0v-4" },
      { kind: "line", x1: 21, y1: 6.5, x2: 21, y2: 12 },
      { kind: "line", x1: 2, y1: 20, x2: 22, y2: 20 },
    ],
  },

  // --- Proyecciones comprobadas: la instantánea (mirar atrás es `clock-rewind`, en `common`) ---
  camera: {
    elements: [
      { kind: "rect", x: 3, y: 7, width: 18, height: 13 },
      { kind: "circle", cx: 12, cy: 13.5, r: 3.5 },
      { kind: "path", d: "M8 7l1.5-3h5L16 7" },
    ],
  },

  // (Las clases de asiento del ledger van todas con dibujos de `common`: campana, pluma, tablilla,
  // calendario, casa, cuadro, hoja escrita, engranaje; la cámara de arriba es la instantánea.)

  // --- Copia de Polaris: enchufe (EMMA la llama) y enchufe tachado (solo viaja con la copia) ---
  plug: {
    elements: [
      { kind: "rect", x: 8, y: 9, width: 8, height: 7 },
      { kind: "line", x1: 10, y1: 4, x2: 10, y2: 9 },
      { kind: "line", x1: 14, y1: 4, x2: 14, y2: 9 },
      { kind: "line", x1: 12, y1: 16, x2: 12, y2: 21 },
    ],
  },
  "plug-slash": {
    elements: [
      { kind: "rect", x: 8, y: 9, width: 8, height: 7 },
      { kind: "line", x1: 10, y1: 4, x2: 10, y2: 9 },
      { kind: "line", x1: 14, y1: 4, x2: 14, y2: 9 },
      { kind: "line", x1: 12, y1: 16, x2: 12, y2: 21 },
      { kind: "line", x1: 3, y1: 21, x2: 21, y2: 3 },
    ],
  },

  // --- Leyenda de la gráfica: la franja de lo que aún está en tránsito -----------------------
  "bar-vertical": { elements: [{ kind: "rect", x: 9, y: 4, width: 6, height: 16, fill: true }] },

  // --- Segunda pasada (2026-10-21, §5.33.6): los signos de los apartados del marco y de los
  // rótulos de cada riesgo que ningún concepto de `lib/uiMarks.ts` nombra -----------------------
  // El marco con una abertura arriba: un hueco (los huecos del MDA).
  // La abertura ocupa casi la mitad del lado: más estrecha, a 14 px se leía como un marco entero.
  "square-open": { elements: [{ kind: "path", d: "M8.5 4H4v16h16V4h-4.5" }] },
  // Un dado de tres puntos en diagonal: el modelo probabilista (IMM, Monte Carlo).
  dice: {
    elements: [
      FRAME,
      { kind: "circle", cx: 8.5, cy: 8.5, r: 1.2, fill: true },
      { kind: "circle", cx: 12, cy: 12, r: 1.2, fill: true },
      { kind: "circle", cx: 15.5, cy: 15.5, r: 1.2, fill: true },
    ],
  },
  // Pentágono regular: las cinco amenazas del RIDGE (radiación, aislamiento, distancia, gravedad,
  // entorno), una por lado.
  pentagon: { elements: [{ kind: "polygon", points: "12,3.5 20.6,9.7 17.3,19.8 6.7,19.8 3.4,9.7" }] },
  // Interrogación en un anillo: lo que sigue siendo hipótesis.
  "question-circle": {
    elements: [
      RING,
      { kind: "path", d: "M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.4" },
      { kind: "circle", cx: 12, cy: 16.8, r: 0.5, fill: true },
    ],
  },
  // Más arriba y menos abajo: la incertidumbre, que EMMA declara sin cuantificarla.
  "plus-minus": {
    elements: [
      { kind: "line", x1: 12, y1: 4, x2: 12, y2: 12 },
      { kind: "line", x1: 8, y1: 8, x2: 16, y2: 8 },
      { kind: "line", x1: 8, y1: 17, x2: 16, y2: 17 },
    ],
  },
  // Anillo con cuatro marcas que lo cruzan: el alcance al que apunta un riesgo.
  crosshair: {
    elements: [
      RING,
      { kind: "line", x1: 12, y1: 3, x2: 12, y2: 7 },
      { kind: "line", x1: 12, y1: 17, x2: 12, y2: 21 },
      { kind: "line", x1: 3, y1: 12, x2: 7, y2: 12 },
      { kind: "line", x1: 17, y1: 12, x2: 21, y2: 12 },
    ],
  },

  // --- Decimocuarta ronda (C9): los bancos de prueba ------------------------------------------
  // Una escalera de mano, dos largueros y tres peldaños: la escalera de evidencia y validación
  // (Tierra, ISS, Luna, Marte) en que se ordenan los bancos de prueba.
  ladder: { elements: [{ kind: "path", d: "M7 3v18M17 3v18M7 7h10M7 12h10M7 17h10" }] },
  // --- Conjuntos de datos humanos (decimoquinta ronda, D2) -------------------------------
  // Un cilindro de tres bandas: el almacén de datos de un estudio, el título del mapa.
  "cylinder-stack": {
    elements: [
      { kind: "path", d: "M5 6a7 2.5 0 0 0 14 0a7 2.5 0 0 0 -14 0" },
      { kind: "path", d: "M5 6v12a7 2.5 0 0 0 14 0V6" },
      { kind: "path", d: "M5 12a7 2.5 0 0 0 14 0" },
    ],
  },
  // El candado con el arco levantado de un lado: los ficheros se descargan sin pedir permiso.
  // Sin el punto de la cerradura, para que no se confunda con `lock` (el registro firmado).
  "padlock-open": {
    elements: [
      { kind: "rect", x: 5, y: 11, width: 14, height: 10 },
      { kind: "path", d: "M8 11V6.5a4 4 0 0 1 7.6 -1.7" },
    ],
  },
  // Una llave: hace falta un permiso (acceso controlado o una solicitud aprobada).
  "key-bit": {
    elements: [
      { kind: "circle", cx: 7.5, cy: 12, r: 3.5 },
      { kind: "path", d: "M11 12h10M17 12v3M20 12v2.5" },
    ],
  },

  // --- Matriz de riesgos: sensibilidad medida inyectando un deterioro (§5.36.2) --------------
  // Una serie con su ruido que a mitad de camino salta y sigue arriba: el deterioro de magnitud
  // conocida sumado a una serie real. No es la jeringa: no se inyecta nada a nadie.
  "zigzag-step": {
    elements: [{ kind: "polyline", points: "3,18 5,16 7,18 9,16 11,18 11,8 13,6 15,8 17,6 19,8 21,6" }],
  },
} as const satisfies PictogramSet;
