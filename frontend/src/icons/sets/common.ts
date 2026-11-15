/**
 * Dibujos de cosas que comparten dos o más áreas: la campana, la casa, la chincheta, el reloj…
 *
 * Por qué existe aparte de `shapes`: `shapes` son las formas básicas de nivel y de estado (○ ◇ △
 * ■, ◌, ⊘ ✕, ✓, flechas); esto son objetos reconocibles. Cada uno nació en el conjunto del área
 * que lo necesitó primero y, al fusionar las once unidades del rediseño pictográfico (2026-10-21),
 * otras diez áreas habían dibujado el mismo nombre por su cuenta; quedó un dibujo por nombre y
 * aquí viven todos los que usa más de un área. La regla la vigila `pictograms.test.ts`: un nombre
 * de un conjunto de área solo se usa desde su área; el que necesita una segunda se sube aquí.
 *
 * El nombre es el dibujo; el significado lo pone la palabra de al lado, y es el mismo en todas las
 * áreas que lo usan (un dibujo, un significado): la campana es siempre una alerta; la pluma, que
 * alguien escribió o firmó; el matraz, un laboratorio o un ensayo de laboratorio; la lupa, buscar
 * o seguir; el reloj de arena, lo que espera o llega tarde; el cubo, un recurso o un fantoma (un
 * bloque de pruebas); la cabeza y hombros, una persona (tripulante, quien revisa un dato, operador
 * entrenado, población humana de un estudio). Rejilla de 24×24, trazo de 2, todo entre 3 y 21
 * salvo lo que asoma a propósito: el badajo de la campana (hasta 21,5) y el arco exterior de la
 * sonda de ecógrafo (hasta 21,7).
 *
 * «Área» es una carpeta de `src/`: `mission`, `timeline` y `sources` comparten casa (`dashboard`),
 * así que un dibujo que solo usan dos de ellas (el paracaídas de la fase y de la etapa posvuelo)
 * se queda en su conjunto y no sube aquí.
 *
 * `ring-dot`, un anillo con un punto en el centro como una casilla de opción marcada, es la señal
 * de «elegido / actual»: la región o la serie elegida en el modo anatómico, la fase actual de la
 * misión, la ventana elegida en Tierra, la cifra de intensidad elegida y la zona que entra por
 * primera vez en el dolor. Antes todo eso era el carácter ●, que ya es «medido» (`dot-filled`,
 * `provenance`), y un dibujo no puede significar dos cosas. No se confunde con `dot-ringed`
 * (alertas: anillo con cuatro marcas de diana, «detectada») ni con `fan-dot` (ecografía: la
 * ventana en abanico con algo dentro).
 *
 * `stairs`: una escalera de tres peldaños rellenos para la escala hedónica de la comida (rótulos
 * del 1 al 9 leídos en una fuente). Por qué rellenos y tres, y no nueve de trazo: se dibujó
 * primero con nueve (2 × 2 unidades, trazo de 1,5) y a 1 em era una raya diagonal; con cuatro de
 * trazo, una raya con bultos. Comparados a 14 px seis candidatos, solo la silueta rellena se ve
 * como escalera. El número de puntos lo dice el texto.
 *
 * La segunda pasada pictográfica (2026-10-21, `lib/uiMarks.ts`) subió aquí veinticinco dibujos más
 * que hasta entonces eran de un área y que ahora nombran un concepto de toda la interfaz (el
 * engranaje de «sistema», el libro de la documentación, la bandeja de exportar, el candado del
 * registro firmado…): el que nombra `UI_PICTOGRAMS` es compartido por definición, y la regla de
 * «lo usan dos o más áreas» lo exime (`pictograms.test.ts`). Y retiró cuatro dibujos que repetían
 * uno de aquí con otro nombre: las tres hojas escritas (`page-folded`, `document-lines`,
 * `page-lines` → `sheet-lines`) y el «difiere» de la PVT (`equals-slash` → `not-equal`), más el
 * símbolo de encendido de la crónica (`power` → `gear`: «sistema» ya tenía dibujo).
 */

import type { PictogramSet } from "../types";
import { RING } from "./shapes";

/** Cuerpo de la campana con su badajo, común a la campana y a la campana tachada. */
const BELL_BODY = [
  { kind: "path", d: "M6 17v-6a6 6 0 0 1 12 0v6l2 2H4z" },
  { kind: "path", d: "M10 21.5a2 2 0 0 0 4 0" },
  { kind: "line", x1: 12, y1: 3, x2: 12, y2: 5 },
] as const;

/** Hoja con la esquina doblada, la misma que las hojas de `evidence`. */
const SHEET = { kind: "path", d: "M6 3h8l5 5v13H6z" } as const;
const FOLD = { kind: "path", d: "M14 3v5h5" } as const;

export const common = {
  // --- Elegido / actual -----------------------------------------------------------------------
  "ring-dot": { elements: [RING, { kind: "circle", cx: 12, cy: 12, r: 3, fill: true }] },

  // --- Comparar: dos rayas (mismo valor, igual) --------------------------------------------------
  equals: {
    elements: [
      { kind: "line", x1: 5, y1: 9, x2: 19, y2: 9 },
      { kind: "line", x1: 5, y1: 15, x2: 19, y2: 15 },
    ],
  },

  // --- Lugares y cosas ------------------------------------------------------------------------
  // Chincheta de mapa: dice dónde (una zona colocada sobre el esqueleto, un tripulante en un
  // módulo, el lugar de un evento), no qué pasa allí.
  pin: {
    elements: [
      { kind: "path", d: "M12 21s-6.5-6-6.5-11.5a6.5 6.5 0 0 1 13 0C18.5 15 12 21 12 21z" },
      { kind: "circle", cx: 12, cy: 9.5, r: 2 },
    ],
  },
  house: {
    elements: [
      { kind: "polyline", points: "3,11.5 12,4 21,11.5" },
      { kind: "path", d: "M6 10v10h12V10" },
      { kind: "path", d: "M10.5 20v-5h3v5" },
    ],
  },
  // Copo: frío. Nació en el hábitat (control térmico) y desde la decimonovena ronda lo usa también
  // el coste de medir (la muestra que se congela a bordo): lo compartido vive aquí.
  snowflake: {
    elements: [
      { kind: "line", x1: 12, y1: 3, x2: 12, y2: 21 },
      { kind: "line", x1: 4.2, y1: 7.5, x2: 19.8, y2: 16.5 },
      { kind: "line", x1: 4.2, y1: 16.5, x2: 19.8, y2: 7.5 },
      { kind: "polyline", points: "9.5,5.5 12,7 14.5,5.5" },
      { kind: "polyline", points: "9.5,18.5 12,17 14.5,18.5" },
    ],
  },
  flask: {
    elements: [
      { kind: "path", d: "M9.5 3v6.5L4 19a1.5 1.5 0 0 0 1.3 2h13.4a1.5 1.5 0 0 0 1.3-2L14.5 9.5V3" },
      { kind: "line", x1: 8, y1: 3, x2: 16, y2: 3 },
      { kind: "line", x1: 5.7, y1: 16, x2: 18.3, y2: 16 },
    ],
  },
  bulb: {
    elements: [
      { kind: "path", d: "M9 16c-2.3-1.6-4-3.9-4-7a7 7 0 0 1 14 0c0 3.1-1.7 5.4-4 7" },
      { kind: "line", x1: 9, y1: 16, x2: 15, y2: 16 },
      { kind: "line", x1: 10, y1: 19.5, x2: 14, y2: 19.5 },
    ],
  },
  // Cubo en perspectiva isométrica: el contorno hexagonal y las tres aristas interiores.
  cube: {
    elements: [
      { kind: "polygon", points: "12,3 20,7.5 20,16.5 12,21 4,16.5 4,7.5" },
      { kind: "polyline", points: "4,7.5 12,12 20,7.5" },
      { kind: "line", x1: 12, y1: 12, x2: 12, y2: 21 },
    ],
  },
  // Punzante en el dolor y el grado «ejercitada a fondo» de una hipótesis en Tierra: estrella de
  // cuatro puntas, con las puntas afiladas.
  "star-four": {
    elements: [{ kind: "polygon", points: "12,3 14,10 21,12 14,14 12,21 10,14 3,12 10,10" }],
  },
  stairs: {
    elements: [{ kind: "polygon", points: "3,21 3,15 9,15 9,9 15,9 15,3 21,3 21,21", fill: true }],
  },

  // --- Personas -------------------------------------------------------------------------------
  // Casco: la esfera, la visera (arco cerrado por abajo) y el anillo del cuello.
  helmet: {
    elements: [
      { kind: "circle", cx: 12, cy: 11, r: 8 },
      { kind: "path", d: "M8 13v-1.5a4 4 0 0 1 8 0V13z" },
      { kind: "line", x1: 7, y1: 21, x2: 17, y2: 21 },
    ],
  },
  // Cabeza y hombros, sin más: `domain-behavioral` lleva además una onda dentro de la cabeza, y
  // `person-paw` (evidencia) lo acompaña de una huella. El asesor y la evidencia dibujaron un
  // «busto» aparte que solo bajaba la cabeza un punto: era el mismo dibujo, y quedó este.
  person: {
    elements: [
      { kind: "circle", cx: 12, cy: 7, r: 4 },
      { kind: "path", d: "M4 21a8 8 0 0 1 16 0" },
    ],
  },

  // --- Tiempo ---------------------------------------------------------------------------------
  clock: { elements: [RING, { kind: "polyline", points: "12,7 12,12 15.5,14" }] },
  // Reloj de arena con la arena ya abajo.
  hourglass: {
    elements: [
      { kind: "path", d: "M6 3h12v2l-5 7 5 7v2H6v-2l5-7-5-7z" },
      { kind: "polygon", points: "9,19 15,19 12,15", fill: true },
    ],
  },
  calendar: {
    elements: [
      { kind: "rect", x: 3, y: 5, width: 18, height: 16 },
      { kind: "line", x1: 3, y1: 10, x2: 21, y2: 10 },
      { kind: "line", x1: 8, y1: 3, x2: 8, y2: 7 },
      { kind: "line", x1: 16, y1: 3, x2: 16, y2: 7 },
    ],
  },

  // --- Avisar ---------------------------------------------------------------------------------
  bell: { elements: [...BELL_BODY] },
  "bell-slash": {
    elements: [...BELL_BODY, { kind: "line", x1: 4, y1: 20, x2: 20, y2: 4 }],
  },

  // --- Escribir y documentar -----------------------------------------------------------------
  // Pluma en diagonal, con la línea que separa la punta: alguien escribió o firmó.
  pen: {
    elements: [
      { kind: "path", d: "M4 20l1-4 11-11 3 3-11 11-4 1z" },
      { kind: "line", x1: 14, y1: 7, x2: 17, y2: 10 },
    ],
  },
  // Lápiz en diagonal, con la virola marcada: decidido por diseño, alta manual.
  pencil: {
    elements: [
      { kind: "polygon", points: "4,20 5,16 16,5 19,8 8,19" },
      { kind: "line", x1: 14, y1: 7, x2: 17, y2: 10 },
    ],
  },
  // Cuaderno: tapa con el lomo y dos renglones (registro, diario).
  notebook: {
    elements: [
      { kind: "rect", x: 5, y: 3, width: 14, height: 18 },
      { kind: "line", x1: 8, y1: 3, x2: 8, y2: 21 },
      { kind: "line", x1: 11, y1: 9, x2: 16, y2: 9 },
      { kind: "line", x1: 11, y1: 13, x2: 16, y2: 13 },
    ],
  },
  clipboard: {
    elements: [
      { kind: "rect", x: 5, y: 5, width: 14, height: 16 },
      { kind: "path", d: "M9 5V3h6v2" },
      { kind: "line", x1: 8, y1: 11, x2: 16, y2: 11 },
      { kind: "line", x1: 8, y1: 15, x2: 14, y2: 15 },
    ],
  },
  // Hoja con la esquina doblada y dos renglones: artículo, informe, analítica, protocolo.
  "sheet-lines": {
    elements: [
      SHEET,
      FOLD,
      { kind: "line", x1: 9, y1: 12, x2: 16, y2: 12 },
      { kind: "line", x1: 9, y1: 16, x2: 16, y2: 16 },
    ],
  },
  picture: {
    elements: [
      { kind: "rect", x: 3, y: 5, width: 18, height: 14 },
      { kind: "polyline", points: "3,16 9,11 13,14 16,12 21,16" },
      { kind: "circle", cx: 16, cy: 9, r: 1.5, fill: true },
    ],
  },
  magnifier: {
    elements: [
      { kind: "circle", cx: 10, cy: 10, r: 6 },
      { kind: "line", x1: 14.5, y1: 14.5, x2: 21, y2: 21 },
    ],
  },

  // --- Instrumentos ---------------------------------------------------------------------------
  chip: {
    elements: [
      { kind: "rect", x: 7, y: 7, width: 10, height: 10 },
      { kind: "line", x1: 10, y1: 4, x2: 10, y2: 7 },
      { kind: "line", x1: 14, y1: 4, x2: 14, y2: 7 },
      { kind: "line", x1: 10, y1: 17, x2: 10, y2: 20 },
      { kind: "line", x1: 14, y1: 17, x2: 14, y2: 20 },
      { kind: "line", x1: 4, y1: 10, x2: 7, y2: 10 },
      { kind: "line", x1: 4, y1: 14, x2: 7, y2: 14 },
      { kind: "line", x1: 17, y1: 10, x2: 20, y2: 10 },
      { kind: "line", x1: 17, y1: 14, x2: 20, y2: 14 },
    ],
  },
  // Sonda de ecógrafo: mango, cabezal y dos arcos de ultrasonido que salen de la cara plana.
  "probe-arcs": {
    elements: [
      { kind: "rect", x: 10, y: 3, width: 4, height: 8 },
      { kind: "path", d: "M8 11h8l1 3.5H7z" },
      { kind: "path", d: "M9.5 17a4 4 0 0 0 5 0" },
      { kind: "path", d: "M6.5 19.5a8 8 0 0 0 11 0" },
    ],
  },
  // Sensor: caja pequeña con dos arcos de señal encima (sensor, instrumento de medida; los
  // dispositivos). Nació en el asesor.
  "sensor-arcs": {
    elements: [
      { kind: "rect", x: 8, y: 14, width: 8, height: 7 },
      { kind: "path", d: "M8 10a6 6 0 0 1 8 0" },
      { kind: "path", d: "M5 6.5a10 10 0 0 1 14 0" },
    ],
  },
  // Punto que emite dos arcos hacia arriba: una señal que viaja (el retardo con Tierra). Nació en
  // la misión.
  "signal-arcs": {
    elements: [
      { kind: "circle", cx: 12, cy: 18, r: 1.5, fill: true },
      { kind: "path", d: "M8.46 14.46A5 5 0 0 1 15.54 14.46" },
      { kind: "path", d: "M5.64 11.64A9 9 0 0 1 18.36 11.64" },
    ],
  },
  gear: {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 6.5 },
      { kind: "circle", cx: 12, cy: 12, r: 2.5 },
      { kind: "line", x1: 12, y1: 3, x2: 12, y2: 5.5 },
      { kind: "line", x1: 12, y1: 18.5, x2: 12, y2: 21 },
      { kind: "line", x1: 3, y1: 12, x2: 5.5, y2: 12 },
      { kind: "line", x1: 18.5, y1: 12, x2: 21, y2: 12 },
      { kind: "line", x1: 5.64, y1: 5.64, x2: 7.4, y2: 7.4 },
      { kind: "line", x1: 16.6, y1: 16.6, x2: 18.36, y2: 18.36 },
      { kind: "line", x1: 18.36, y1: 5.64, x2: 16.6, y2: 7.4 },
      { kind: "line", x1: 7.4, y1: 16.6, x2: 5.64, y2: 18.36 },
    ],
  },
  // Cabeza abierta arriba a la derecha (la boca de la llave) y mango hacia abajo a la izquierda.
  wrench: {
    elements: [
      { kind: "path", d: "M18.85 8.34A4.5 4.5 0 1 1 15.66 5.15" },
      { kind: "line", x1: 18.85, y1: 8.34, x2: 16.9, y2: 8.9 },
      { kind: "line", x1: 15.66, y1: 5.15, x2: 15.1, y2: 7.1 },
      { kind: "line", x1: 4, y1: 20, x2: 11.3, y2: 12.7 },
    ],
  },
  // Goma de borrar inclinada sobre su línea.
  eraser: {
    elements: [
      { kind: "polygon", points: "15,3 21,9 11,19 5,13" },
      { kind: "line", x1: 11.5, y1: 6.5, x2: 17.5, y2: 12.5 },
      { kind: "line", x1: 4, y1: 21, x2: 20, y2: 21 },
    ],
  },
  // Dos eslabones entrelazados en diagonal (vínculo); `chain-broken`, en `ui`, los separa.
  "chain-links": {
    elements: [
      { kind: "path", d: "M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5" },
      { kind: "path", d: "M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5" },
    ],
  },
  "id-card": {
    elements: [
      { kind: "rect", x: 3, y: 5, width: 18, height: 14 },
      { kind: "circle", cx: 8.5, cy: 10.5, r: 2.2 },
      { kind: "line", x1: 13, y1: 9.5, x2: 18, y2: 9.5 },
      { kind: "line", x1: 13, y1: 13.5, x2: 18, y2: 13.5 },
    ],
  },
  lock: {
    elements: [
      { kind: "rect", x: 5, y: 11, width: 14, height: 10 },
      { kind: "path", d: "M8 11V7.5a4 4 0 0 1 8 0V11" },
      { kind: "circle", cx: 12, cy: 16, r: 1.2, fill: true },
    ],
  },

  // --- Flechas con objeto -----------------------------------------------------------------------
  // Bandeja con la flecha que entra (recibir, exportar a un fichero); `arrow-up-tray`, en `ui`,
  // es la inversa.
  "tray-arrow-down": {
    elements: [
      { kind: "path", d: "M3 14v6h18v-6" },
      { kind: "line", x1: 12, y1: 3, x2: 12, y2: 13 },
      { kind: "polyline", points: "8,9 12,13 16,9" },
    ],
  },
  "arrow-u-turn": {
    elements: [
      { kind: "path", d: "M6 21V9a6 6 0 0 1 12 0v8" },
      { kind: "polyline", points: "14.5,13.5 18,17 21.5,13.5" },
    ],
  },
  // Agujas de reloj dentro de un arco que gira hacia atrás (el de `refresh`, reflejado): mirar
  // atrás, lo anterior, el historial.
  "clock-rewind": {
    elements: [
      { kind: "path", d: "M6.34 6.34A8 8 0 1 1 4.27 14.07" },
      { kind: "polyline", points: "3,6.34 6.34,6.34 6.34,9.7" },
      { kind: "polyline", points: "12,8 12,12 15,14" },
    ],
  },

  // --- Comparar: dos rayas tachadas (valor distinto, difiere) -----------------------------------
  "not-equal": {
    elements: [
      { kind: "line", x1: 5, y1: 9, x2: 19, y2: 9 },
      { kind: "line", x1: 5, y1: 15, x2: 19, y2: 15 },
      { kind: "line", x1: 15, y1: 4, x2: 9, y2: 20 },
    ],
  },
  // Dos barras de distinta altura sobre una línea: comparar grupos o tripulantes.
  "bars-two": {
    elements: [
      { kind: "rect", x: 5, y: 10, width: 5, height: 10 },
      { kind: "rect", x: 14, y: 5, width: 5, height: 15 },
      { kind: "line", x1: 3, y1: 20, x2: 21, y2: 20 },
    ],
  },
  // Barra llena a medias con un tope al final: lo acumulado frente a un límite.
  "bar-capped": {
    elements: [
      { kind: "rect", x: 3, y: 9, width: 15, height: 6 },
      { kind: "rect", x: 3, y: 9, width: 8, height: 6, fill: true },
      { kind: "line", x1: 21, y1: 6, x2: 21, y2: 18 },
    ],
  },

  // --- Documentos y listas ---------------------------------------------------------------------
  // Hoja con un círculo (un sello): norma y su resumen, el marco de NASA.
  "sheet-circle": { elements: [SHEET, FOLD, { kind: "circle", cx: 12.5, cy: 14.5, r: 3 }] },
  // Libro abierto por el lomo: la documentación, lo leído en la fuente.
  "book-open": {
    elements: [
      { kind: "path", d: "M12 6c-2-1.5-5-2-8-2v14c3 0 6 0.5 8 2 2-1.5 5-2 8-2V4c-3 0-6 0.5-8 2z" },
      { kind: "line", x1: 12, y1: 6, x2: 12, y2: 20 },
    ],
  },
  // Lista con viñetas: una entrada del catálogo, los riesgos.
  "list-lines": {
    elements: [
      { kind: "circle", cx: 5, cy: 6, r: 1.2, fill: true },
      { kind: "circle", cx: 5, cy: 12, r: 1.2, fill: true },
      { kind: "circle", cx: 5, cy: 18, r: 1.2, fill: true },
      { kind: "line", x1: 9, y1: 6, x2: 20, y2: 6 },
      { kind: "line", x1: 9, y1: 12, x2: 20, y2: 12 },
      { kind: "line", x1: 9, y1: 18, x2: 20, y2: 18 },
    ],
  },
  // Lista con dos casillas marcadas: la calidad comprobada punto por punto.
  "list-check": {
    elements: [
      { kind: "polyline", points: "3,7 5,9 8.5,5" },
      { kind: "line", x1: 11, y1: 7, x2: 21, y2: 7 },
      { kind: "polyline", points: "3,17 5,19 8.5,15" },
      { kind: "line", x1: 11, y1: 17, x2: 21, y2: 17 },
    ],
  },
  "table-grid": {
    elements: [
      { kind: "rect", x: 3, y: 4, width: 18, height: 16 },
      { kind: "line", x1: 3, y1: 9.33, x2: 21, y2: 9.33 },
      { kind: "line", x1: 3, y1: 14.67, x2: 21, y2: 14.67 },
      { kind: "line", x1: 9, y1: 4, x2: 9, y2: 20 },
      { kind: "line", x1: 15, y1: 4, x2: 15, y2: 20 },
    ],
  },
  "circle-i": {
    elements: [
      RING,
      { kind: "line", x1: 12, y1: 11, x2: 12, y2: 16.5 },
      { kind: "circle", cx: 12, cy: 8, r: 0.9, fill: true },
    ],
  },

  // --- Hechos de la crónica que también son títulos ---------------------------------------------
  // Tira en diagonal con dos agujeros en el centro: una contramedida.
  bandage: {
    elements: [
      { kind: "polygon", points: "5,15.5 15.5,5 19,8.5 8.5,19" },
      { kind: "circle", cx: 11, cy: 11, r: 1, fill: true },
      { kind: "circle", cx: 13, cy: 13, r: 1, fill: true },
    ],
  },
  // Medio disco sobre una línea, con tres rayos: el posvuelo, la recuperación.
  sunrise: {
    elements: [
      { kind: "line", x1: 3, y1: 17, x2: 21, y2: 17 },
      { kind: "path", d: "M7 17a5 5 0 0 1 10 0" },
      { kind: "line", x1: 12, y1: 5, x2: 12, y2: 8 },
      { kind: "line", x1: 5, y1: 10, x2: 7, y2: 12 },
      { kind: "line", x1: 19, y1: 10, x2: 17, y2: 12 },
    ],
  },
  // Campana más pequeña dentro de un marco: el dominio entero con la puerta cerrada (inhibida).
  "bell-box": {
    elements: [
      { kind: "rect", x: 2.5, y: 2.5, width: 19, height: 19 },
      { kind: "path", d: "M6.5 16h11l-1.2-1.6V11a4.3 4.3 0 0 0-8.6 0v3.4z" },
      { kind: "line", x1: 12, y1: 5.5, x2: 12, y2: 6.7 },
      { kind: "path", d: "M10.5 18.5a1.5 1.5 0 0 0 3 0" },
    ],
  },
  // Calendario con un día relleno: el día de misión.
  "calendar-day": {
    elements: [
      { kind: "rect", x: 3.5, y: 5, width: 17, height: 15 },
      { kind: "line", x1: 3.5, y1: 10, x2: 20.5, y2: 10 },
      { kind: "line", x1: 8, y1: 3, x2: 8, y2: 7 },
      { kind: "line", x1: 16, y1: 3, x2: 16, y2: 7 },
      { kind: "rect", x: 12, y: 13, width: 4, height: 4, fill: true },
    ],
  },
  // Figura de palo con un punto en el torso: el mapa corporal, el cuerpo.
  "figure-dot": {
    elements: [
      { kind: "circle", cx: 12, cy: 4.5, r: 2 },
      { kind: "line", x1: 12, y1: 6.5, x2: 12, y2: 15 },
      { kind: "line", x1: 6, y1: 9.5, x2: 18, y2: 9.5 },
      { kind: "line", x1: 12, y1: 15, x2: 8, y2: 21.5 },
      { kind: "line", x1: 12, y1: 15, x2: 16, y2: 21.5 },
      { kind: "circle", cx: 15, cy: 12.5, r: 1.5, fill: true },
    ],
  },
  // Dos cajas y una flecha de una a otra: los pasos de un flujo. Nació en el hábitat para los
  // pasos de una hipótesis (§5.33.4; cajas y no círculos: tres círculos unidos se leían a 14 px
  // como las moléculas de cabina) y subió aquí cuando la alerta tuvo los suyos (§5.34.6).
  "squares-arrow": {
    elements: [
      { kind: "rect", x: 3, y: 8, width: 6, height: 8 },
      { kind: "line", x1: 9, y1: 12, x2: 15, y2: 12 },
      { kind: "polyline", points: "12.5,9.5 15,12 12.5,14.5" },
      { kind: "rect", x: 15, y: 8, width: 6, height: 8 },
    ],
  },
  // Rayos desde un punto, sin disco: el evento solar, lo repentino. Nació en `radiation` (la
  // escala aguda) y sube aquí porque el hábitat lo usa para la misma cosa (decimoséptima ronda).
  burst: {
    elements: [
      { kind: "line", x1: 12, y1: 3, x2: 12, y2: 8 },
      { kind: "line", x1: 12, y1: 16, x2: 12, y2: 21 },
      { kind: "line", x1: 3, y1: 12, x2: 8, y2: 12 },
      { kind: "line", x1: 16, y1: 12, x2: 21, y2: 12 },
      { kind: "line", x1: 6, y1: 6, x2: 8.8, y2: 8.8 },
      { kind: "line", x1: 15.2, y1: 15.2, x2: 18, y2: 18 },
      { kind: "line", x1: 6, y1: 18, x2: 8.8, y2: 15.2 },
      { kind: "line", x1: 15.2, y1: 8.8, x2: 18, y2: 6 },
      { kind: "circle", cx: 12, cy: 12, r: 1.5, fill: true },
    ],
  },
  // Tres tomas sueltas en fila: lo periódico. Nació en `ground` (el modo `periodic-noninvasive`
  // de lo que cuesta medir) y sube aquí porque las rachas de las medidas periódicas la usan para
  // lo mismo: periodos seguidos (`dashboard/timelineMarks.ts`, `STREAK_MARK`).
  "dots-row": {
    elements: [
      { kind: "circle", cx: 5, cy: 12, r: 2, fill: true },
      { kind: "circle", cx: 12, cy: 12, r: 2, fill: true },
      { kind: "circle", cx: 19, cy: 12, r: 2, fill: true },
    ],
  },
  // El altavoz: con ondas, el ruido de cabina (`habitat/`) y la voz de la consola que lee en voz
  // alta (`components/ReadAloud.tsx`, §5.40); nació en `habitat` y sube aquí al usarlo la consola.
  // Tachado, callar la voz; con la flecha que vuelve, repetir lo último leído.
  "speaker-waves": {
    elements: [
      { kind: "polygon", points: "4,9 8,9 13,5 13,19 8,15 4,15" },
      { kind: "path", d: "M16 9.5a3.5 3.5 0 0 1 0 5" },
      { kind: "path", d: "M18.5 6.5a7.5 7.5 0 0 1 0 11" },
    ],
  },
  "speaker-slash": {
    elements: [
      { kind: "polygon", points: "4,9 8,9 13,5 13,19 8,15 4,15" },
      { kind: "line", x1: 16, y1: 9, x2: 21, y2: 15 },
      { kind: "line", x1: 21, y1: 9, x2: 16, y2: 15 },
    ],
  },
  "speaker-repeat": {
    elements: [
      { kind: "polygon", points: "3,9 6,9 10,6 10,18 6,15 3,15" },
      { kind: "path", d: "M14 15a4 4 0 1 0 1.5-6.5" },
      { kind: "polyline", points: "14,5 15.5,8.5 12,9.5" },
    ],
  },
  // Micrófono (nota dictada del dolor, asistente) de cápsula, con su arco, pie y base.
  microphone: {
    elements: [
      { kind: "path", d: "M9 4a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0z" },
      { kind: "path", d: "M5 11a7 7 0 0 0 14 0" },
      { kind: "line", x1: 12, y1: 18, x2: 12, y2: 21 },
      { kind: "line", x1: 8, y1: 21, x2: 16, y2: 21 },
    ],
  },
} as const satisfies PictogramSet;
