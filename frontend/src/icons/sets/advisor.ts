/**
 * Pictogramas de las recomendaciones, recursos y seguimiento (`advisor/`).
 *
 * Cuatro grupos, y en todos el nombre es el dibujo; lo que significa lo dice la palabra del backend
 * que va al lado (`compliance/hmi-state-of-the-art.md` §5.32.5):
 *
 * - Urgencia de una recomendación: uno, dos o tres galones hacia la derecha. La forma crece con
 *   la urgencia, como el texto «rutina / pronto / inmediata» que acompaña.
 * - Familias de recursos de a bordo (`advisor/resources.ts` reparte las claves del vocabulario
 *   `backend/app/data/resources.json`): sensor con arcos de señal, calendario con rejilla, antena
 *   parabólica, muro de ladrillos (masa de blindaje), tarjeta con pinza (dosímetro), tres ejes
 *   (acelerómetro), pulverizador, figura con un punto (mapa corporal), vaso, frasco graduado y
 *   rizos de viento (control ambiental). Las familias que ya tenían dibujo en otro conjunto lo
 *   reutilizan (`dumbbell`, `stopwatch`, `vial`, `fork-knife`; y de `common` el cuaderno, la
 *   bombilla, la sonda con arcos y la cabeza y hombros de una persona): un significado, un dibujo.
 *   El sensor con arcos y la figura con un punto nacieron aquí y pasaron a `common` en la segunda
 *   pasada (2026-10-21): son los títulos de «dispositivos» y «cuerpo» en toda la interfaz
 *   (`lib/uiMarks.ts`).
 * - Los estados del seguimiento y de la respuesta previa usan las formas básicas de `shapes`
 *   (`refresh`, `play`, `check`, `dash`, flechas): no se dibuja nada nuevo para ellos.
 * - Familias de contramedida (vocabulario cerrado del backend, `FAMILIES` en
 *   `advisor/countermeasures.py`; 2026-10-21): pesa trapezoidal con la ranura del asa (física
 *   o de masa), un recorrido con flecha (operacional), ojo abierto (comprobación o vigilancia)
 *   y cápsula partida (farmacológica, fuera del alcance de EMMA). Son dibujos nuevos: el muro de
 *   ladrillos es la masa de blindaje como RECURSO, la lupa es el seguimiento y la hoja el
 *   respaldo, y una familia es otro concepto.
 * - Las cabeceras de contraindicaciones y de efectos de la biblioteca (2026-10-22, §5.35.7): una
 *   barrera de paso con franjas y una flecha con una rama que se aparta. No son el triángulo de
 *   «hay que mirarlo» (`shape-triangle`): una columna no es un aviso.
 * - Dos contramedidas adoptadas a la vez (2026-10-31, §5.39.17): dos círculos que se solapan. Es
 *   información, no un aviso, y no son los eslabones de «vincular» (`chain-links`): nadie las
 *   vincula, coinciden en el tiempo.
 *
 * Rejilla de 24×24, trazo de 2, todo entre 3 y 21 salvo algún arco que roza el borde. Los
 * dibujos se leen a 12 px: pocas líneas y huecos de al menos dos unidades.
 */

import type { PictogramSet } from "../types";

export const advisor = {
  // Urgencia: uno, dos y tres galones.
  "chevron-right": { elements: [{ kind: "polyline", points: "9,5 16,12 9,19" }] },
  "chevrons-right-double": {
    elements: [
      { kind: "polyline", points: "5,5 12,12 5,19" },
      { kind: "polyline", points: "13,5 20,12 13,19" },
    ],
  },
  "chevrons-right-triple": {
    elements: [
      { kind: "polyline", points: "3,6 9,12 3,18" },
      { kind: "polyline", points: "9,6 15,12 9,18" },
      { kind: "polyline", points: "15,6 21,12 15,18" },
    ],
  },
  // Calendario: marco con las anillas, la cabecera y la rejilla (planificación).
  "calendar-grid": {
    elements: [
      { kind: "rect", x: 3, y: 5, width: 18, height: 16 },
      { kind: "line", x1: 3, y1: 10, x2: 21, y2: 10 },
      { kind: "line", x1: 8, y1: 3, x2: 8, y2: 7 },
      { kind: "line", x1: 16, y1: 3, x2: 16, y2: 7 },
      { kind: "line", x1: 9, y1: 10, x2: 9, y2: 21 },
      { kind: "line", x1: 15, y1: 10, x2: 15, y2: 21 },
      { kind: "line", x1: 3, y1: 15.5, x2: 21, y2: 15.5 },
    ],
  },
  // Antena parabólica sobre un poste, con el alimentador (comunicaciones con Tierra).
  "antenna-dish": {
    elements: [
      { kind: "path", d: "M4 6a11 11 0 0 0 14 14" },
      { kind: "line", x1: 11, y1: 13, x2: 16.5, y2: 7.5 },
      { kind: "circle", cx: 17, cy: 7, r: 1.2, fill: true },
      { kind: "line", x1: 11, y1: 13, x2: 11, y2: 21 },
      { kind: "line", x1: 7, y1: 21, x2: 15, y2: 21 },
    ],
  },
  // Muro de ladrillos: tres hiladas alternas (masa de blindaje).
  "wall-bricks": {
    elements: [
      { kind: "rect", x: 3, y: 4, width: 18, height: 16 },
      { kind: "line", x1: 3, y1: 9.33, x2: 21, y2: 9.33 },
      { kind: "line", x1: 3, y1: 14.67, x2: 21, y2: 14.67 },
      { kind: "line", x1: 12, y1: 4, x2: 12, y2: 9.33 },
      { kind: "line", x1: 7.5, y1: 9.33, x2: 7.5, y2: 14.67 },
      { kind: "line", x1: 16.5, y1: 9.33, x2: 16.5, y2: 14.67 },
      { kind: "line", x1: 12, y1: 14.67, x2: 12, y2: 20 },
    ],
  },
  // Tarjeta con la pinza arriba y la ventana redonda (dosímetro personal).
  "badge-dot": {
    elements: [
      { kind: "rect", x: 6, y: 6, width: 12, height: 15 },
      { kind: "path", d: "M10 6V3h4v3" },
      { kind: "circle", cx: 12, cy: 13.5, r: 3 },
    ],
  },
  // Tres flechas desde un origen: los ejes de un acelerómetro.
  "arrows-three-axes": {
    elements: [
      { kind: "line", x1: 12, y1: 13, x2: 12, y2: 3 },
      { kind: "polyline", points: "9,6 12,3 15,6" },
      { kind: "line", x1: 12, y1: 13, x2: 3.5, y2: 18 },
      { kind: "polyline", points: "4.8,14.35 3.5,18 7.3,18.65" },
      { kind: "line", x1: 12, y1: 13, x2: 20.5, y2: 18 },
      { kind: "polyline", points: "19.2,14.35 20.5,18 16.7,18.65" },
    ],
  },
  // Pulverizador: cuerpo, cuello, boquilla, gatillo y una gota (material de limpieza).
  "spray-bottle": {
    elements: [
      { kind: "rect", x: 7, y: 11, width: 10, height: 10 },
      { kind: "path", d: "M10 11V5h4v6" },
      { kind: "line", x1: 14, y1: 6.5, x2: 18.5, y2: 6.5 },
      { kind: "path", d: "M10 7.5L6.5 10" },
      { kind: "circle", cx: 20.5, cy: 4, r: 0.9, fill: true },
    ],
  },
  // Vaso con la línea del agua (agua potable).
  "cup-line": {
    elements: [
      { kind: "path", d: "M5 4h14l-1.5 17h-11z" },
      { kind: "line", x1: 6.3, y1: 10, x2: 17.7, y2: 10 },
    ],
  },
  // Frasco graduado con tres marcas (recogida de orina).
  "bottle-marks": {
    elements: [
      { kind: "path", d: "M9.5 3h5v4l2 2.5V21h-9V9.5l2-2.5z" },
      { kind: "line", x1: 13, y1: 13, x2: 16.5, y2: 13 },
      { kind: "line", x1: 13, y1: 16, x2: 16.5, y2: 16 },
      { kind: "line", x1: 13, y1: 19, x2: 16.5, y2: 19 },
    ],
  },
  // Tres líneas de viento que acaban en un rizo (control ambiental, aire del módulo).
  "wind-curls": {
    elements: [
      { kind: "path", d: "M3 8h11a2.5 2.5 0 1 0-2.5-2.5" },
      { kind: "path", d: "M3 13h15a2.5 2.5 0 1 1-2.5 2.5" },
      { kind: "path", d: "M3 18h8a2 2 0 1 0-2-2" },
    ],
  },
  // Familias de contramedida (`advisor/library.ts`), una por clave del vocabulario cerrado.
  // Pesa de balanza: bloque trapezoidal ancho con la ranura del asa dentro (física o de masa).
  // Sin anilla encima: a 14 px una anilla sobre un cuerpo se leía como un candado.
  "weight-trapezoid": {
    elements: [
      { kind: "path", d: "M3 20l3.5-14h11L21 20z" },
      { kind: "rect", x: 9, y: 9, width: 6, height: 3 },
    ],
  },
  // Un recorrido que sale de un punto, da dos vueltas y acaba en flecha: la actividad que se
  // reorganiza (operacional). Dos cajas con una flecha se leían como un reloj de arena.
  "route-arrow": {
    elements: [
      { kind: "circle", cx: 5, cy: 5, r: 2 },
      { kind: "path", d: "M7 5h7a3.5 3.5 0 0 1 0 7h-4a3.5 3.5 0 0 0 0 7h8" },
      { kind: "polyline", points: "15,16 18,19 15,22" },
    ],
  },
  // Ojo abierto con la pupila: mirar y volver a mirar (comprobación o vigilancia).
  "eye-open": {
    elements: [
      { kind: "path", d: "M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12z" },
      { kind: "circle", cx: 12, cy: 12, r: 3 },
    ],
  },
  // Cápsula partida por la mitad (farmacológica: la familia que queda fuera del alcance).
  "capsule-split": {
    elements: [
      { kind: "path", d: "M8 8h8a4 4 0 0 1 0 8H8a4 4 0 0 1 0-8z" },
      { kind: "line", x1: 12, y1: 8, x2: 12, y2: 16 },
    ],
  },
  // Las dos columnas de la biblioteca que dicen qué saber antes de adoptar (§5.35.7).
  // Barrera de paso: un larguero con dos franjas sobre dos postes (contraindicaciones: cuándo
  // no conviene adoptarla). Sin color: ninguna está escrita todavía y nombrar la columna no avisa.
  "barrier-striped": {
    elements: [
      { kind: "rect", x: 3, y: 6, width: 18, height: 6 },
      { kind: "line", x1: 7, y1: 12, x2: 11, y2: 6 },
      { kind: "line", x1: 13, y1: 12, x2: 17, y2: 6 },
      { kind: "line", x1: 6, y1: 12, x2: 6, y2: 21 },
      { kind: "line", x1: 18, y1: 12, x2: 18, y2: 21 },
    ],
  },
  // Una flecha recta y una rama recta que se aparta de ella a 45° (efectos a tener en cuenta:
  // lo que la acción hace además de lo que busca). La primera rama era curva y a 14 px se leía
  // como un «4» (captura de §5.35.7).
  "arrow-side-branch": {
    elements: [
      { kind: "line", x1: 3, y1: 16, x2: 21, y2: 16 },
      { kind: "polyline", points: "17,12 21,16 17,20" },
      { kind: "line", x1: 6, y1: 16, x2: 14, y2: 8 },
      { kind: "polyline", points: "8.5,8 14,8 14,13.5" },
    ],
  },
  // Dos círculos que se solapan (dos contramedidas adoptadas a la vez, §5.39.17): coinciden en el
  // tiempo, y la zona común es lo que ninguna fuente leída describe.
  "circles-overlap": {
    elements: [
      { kind: "circle", cx: 9, cy: 12, r: 6 },
      { kind: "circle", cx: 15, cy: 12, r: 6 },
    ],
  },
} as const satisfies PictogramSet;
