/**
 * Dibujos del mobiliario de la interfaz: lo que acompaña a un título de panel, a un plegable, a un
 * mando o a una cabecera de tabla como signo de qué es esa cosa (`lib/uiMarks.ts`).
 *
 * Por qué existe aparte de `common`: la segunda pasada pictográfica (2026-10-21, «la interfaz
 * vistosa») decidió que el pictograma acompaña a cada título, plegable, mando y cabecera, no solo a
 * las palabras de estado. Casi todos esos conceptos ya tenían dibujo en el núcleo (la campana de
 * las alertas, el libro de la documentación, el cronómetro de la PVT…); estos veintiuno son los que no
 * lo tenían. Es un conjunto del núcleo, como `common`: lo usa cualquier área, y cada dibujo tiene
 * su concepto en `UI_PICTOGRAMS`, o varios declarados como sinónimos (lo vigila
 * `lib/uiMarks.test.ts`: un dibujo de aquí sin concepto es un huérfano).
 *
 * El nombre es el dibujo, nunca el concepto: `signpost`, no «recomendaciones». Rejilla de 24×24,
 * trazo de 2, todo entre 3 y 21, pensado para leerse a 14 px (el cuerpo de la consola) y revisado
 * en la hoja de contactos a 12, 14, 16 y 24 px. Las fuentes abiertas (Lucide, Tabler) se miraron
 * como vocabulario y proporción —qué objeto representa cada concepto en el resto del mundo, cuánto
 * ocupa—, no se copió ningún trazo.
 *
 * Dibujos: poste con un cartel pentagonal (señal de camino); cuatro cuadrados (rejilla); faro con
 * su tejado y dos haces; dintel sobre dos columnas con su base; dos semiarcos con punta que se
 * persiguen; ejes con una línea quebrada; dos monedas, una detrás de otra; etiqueta con su ojal;
 * regla con cuatro marcas; tres renglones, el último corto; bocadillo con dos renglones; dos
 * eslabones separados (los de `chain-links`, sueltos); tira de película con sus perforaciones;
 * almohadilla; sello con su pomo; dos flechas en sentidos opuestos; interruptor de píldora con el disco; tanto por ciento; bandeja
 * con la flecha que sale (la inversa de `tray-arrow-down`); la cruz ortogonal del más (`cross`,
 * en `shapes`, es la diagonal); y tres capas apiladas, las de la tabla de la base de conocimiento §10
 * (§5.35.1). El carril de pestañas y los modos de pantalla (§5.40) añaden seis: cinco puntos en
 * pentágono (los peligros), dos letras A de dos tamaños, tres trazos cada vez más cortos, una
 * tableta con la flecha que la gira, el borde de arriba con dos galones y el ojo tachado; y el alto
 * contraste, un cuadrado partido en diagonal con una mitad llena.
 */

import type { PictogramSet } from "../types";

export const ui = {
  // --- Títulos de panel ------------------------------------------------------------------------
  // Poste con base y un cartel pentagonal que apunta a la derecha.
  signpost: {
    elements: [
      { kind: "line", x1: 7, y1: 3, x2: 7, y2: 21 },
      { kind: "line", x1: 4, y1: 21, x2: 10, y2: 21 },
      { kind: "polygon", points: "7,6 16,6 20,10 16,14 7,14" },
    ],
  },
  "grid-four": {
    elements: [
      { kind: "rect", x: 4, y: 4, width: 6, height: 6 },
      { kind: "rect", x: 14, y: 4, width: 6, height: 6 },
      { kind: "rect", x: 4, y: 14, width: 6, height: 6 },
      { kind: "rect", x: 14, y: 14, width: 6, height: 6 },
    ],
  },
  // Torre que se estrecha hacia arriba, la linterna con su tejado y un haz corto a cada lado. Los
  // haces en diagonal de la primera versión se leían como cuernos a 14 px; horizontales, como luz.
  lighthouse: {
    elements: [
      { kind: "polygon", points: "9,21 15,21 14,11 10,11" },
      { kind: "rect", x: 9.5, y: 7, width: 5, height: 4 },
      { kind: "polyline", points: "9,7 12,4 15,7" },
      { kind: "line", x1: 3, y1: 9, x2: 6.5, y2: 9 },
      { kind: "line", x1: 17.5, y1: 9, x2: 21, y2: 9 },
    ],
  },
  // Dintel, dos columnas y base: lo que sostiene.
  pillars: {
    elements: [
      { kind: "line", x1: 3, y1: 5, x2: 21, y2: 5 },
      { kind: "line", x1: 8, y1: 5, x2: 8, y2: 19 },
      { kind: "line", x1: 16, y1: 5, x2: 16, y2: 19 },
      { kind: "line", x1: 3, y1: 19, x2: 21, y2: 19 },
    ],
  },
  // Dos semiarcos de r = 6,5 que se persiguen, cada uno con su punta.
  "arrows-cycle": {
    elements: [
      { kind: "path", d: "M5.5 12a6.5 6.5 0 0 1 13 0" },
      { kind: "polyline", points: "16,9.5 18.5,12 21,9.5" },
      { kind: "path", d: "M18.5 12a6.5 6.5 0 0 1-13 0" },
      { kind: "polyline", points: "3,14.5 5.5,12 8,14.5" },
    ],
  },
  "chart-line": {
    elements: [
      { kind: "polyline", points: "4,4 4,20 20,20" },
      { kind: "polyline", points: "7,16 11,11 14,14 19,7" },
    ],
  },
  // Una moneda delante y el borde de otra que asoma detrás, arriba a la derecha.
  coins: {
    elements: [
      { kind: "circle", cx: 9.5, cy: 13.5, r: 6.5 },
      { kind: "path", d: "M9 7A6.5 6.5 0 1 1 15 17" },
    ],
  },
  ruler: {
    elements: [
      { kind: "rect", x: 3, y: 8, width: 18, height: 8 },
      { kind: "line", x1: 7, y1: 8, x2: 7, y2: 12 },
      { kind: "line", x1: 10.5, y1: 8, x2: 10.5, y2: 12 },
      { kind: "line", x1: 14, y1: 8, x2: 14, y2: 12 },
      { kind: "line", x1: 17.5, y1: 8, x2: 17.5, y2: 12 },
    ],
  },
  // Tres capas apiladas: un rombo arriba y, debajo, el borde de dos más (las capas de §10).
  "layers-stack": {
    elements: [
      { kind: "polygon", points: "12,3 21,8 12,13 3,8" },
      { kind: "polyline", points: "3,12 12,17 21,12" },
      { kind: "polyline", points: "3,16 12,21 21,16" },
    ],
  },

  // --- Plegables -------------------------------------------------------------------------------
  "text-lines": {
    elements: [
      { kind: "line", x1: 4, y1: 7, x2: 20, y2: 7 },
      { kind: "line", x1: 4, y1: 12, x2: 20, y2: 12 },
      { kind: "line", x1: 4, y1: 17, x2: 13, y2: 17 },
    ],
  },
  // Bocadillo con la cola abajo a la izquierda y dos renglones dentro.
  "bubble-lines": {
    elements: [
      { kind: "path", d: "M3 3h18v13h-9l-5 4v-4H3z" },
      { kind: "line", x1: 7, y1: 8, x2: 17, y2: 8 },
      { kind: "line", x1: 7, y1: 12, x2: 14, y2: 12 },
    ],
  },

  // --- Mandos ----------------------------------------------------------------------------------
  // Dos eslabones cerrados en diagonal, separados por un hueco: la cadena de `chain-links`, rota.
  "chain-broken": {
    elements: [
      { kind: "path", d: "M20.54 7.71A3 3 0 0 0 16.29 3.46L13.46 6.29A3 3 0 0 0 17.71 10.54z" },
      { kind: "path", d: "M10.54 17.71A3 3 0 0 0 6.29 13.46L3.46 16.29A3 3 0 0 0 7.71 20.54z" },
    ],
  },
  // Fotograma apaisado entre dos márgenes, con dos perforaciones por margen. Los agujeros como
  // puntos rellenos se fundían con el marco a 14 px y la tira se leía como un bloque.
  "film-strip": {
    elements: [
      { kind: "rect", x: 3, y: 5, width: 18, height: 14 },
      { kind: "line", x1: 7, y1: 5, x2: 7, y2: 19 },
      { kind: "line", x1: 17, y1: 5, x2: 17, y2: 19 },
      { kind: "line", x1: 3, y1: 9.5, x2: 7, y2: 9.5 },
      { kind: "line", x1: 3, y1: 14.5, x2: 7, y2: 14.5 },
      { kind: "line", x1: 17, y1: 9.5, x2: 21, y2: 9.5 },
      { kind: "line", x1: 17, y1: 14.5, x2: 21, y2: 14.5 },
    ],
  },
  "arrows-swap": {
    elements: [
      { kind: "line", x1: 4, y1: 8, x2: 20, y2: 8 },
      { kind: "polyline", points: "16,4 20,8 16,12" },
      { kind: "line", x1: 20, y1: 16, x2: 4, y2: 16 },
      { kind: "polyline", points: "8,12 4,16 8,20" },
    ],
  },
  "arrow-up-tray": {
    elements: [
      { kind: "path", d: "M3 14v6h18v-6" },
      { kind: "line", x1: 12, y1: 13, x2: 12, y2: 3 },
      { kind: "polyline", points: "8,7 12,3 16,7" },
    ],
  },
  plus: {
    elements: [
      { kind: "line", x1: 12, y1: 5, x2: 12, y2: 19 },
      { kind: "line", x1: 5, y1: 12, x2: 19, y2: 12 },
    ],
  },

  // --- Cabeceras y rótulos ---------------------------------------------------------------------
  hash: {
    elements: [
      { kind: "line", x1: 10, y1: 4, x2: 8, y2: 20 },
      { kind: "line", x1: 16, y1: 4, x2: 14, y2: 20 },
      { kind: "line", x1: 4, y1: 9.5, x2: 20, y2: 9.5 },
      { kind: "line", x1: 4, y1: 14.5, x2: 20, y2: 14.5 },
    ],
  },
  // Sello visto de lado: base, cuello y pomo.
  stamp: {
    elements: [
      { kind: "rect", x: 4, y: 16, width: 16, height: 4 },
      { kind: "path", d: "M10 16v-6h4v6" },
      { kind: "circle", cx: 12, cy: 6.5, r: 3 },
    ],
  },
  // Etiqueta con la punta a la derecha y el ojal junto al borde.
  tag: {
    elements: [
      { kind: "path", d: "M3 11V3h8l9 9-8 8z" },
      { kind: "circle", cx: 7, cy: 7, r: 1.2, fill: true },
    ],
  },
  // Píldora con el disco a la derecha.
  toggle: {
    elements: [
      { kind: "path", d: "M8 7h8a5 5 0 0 1 0 10H8a5 5 0 0 1 0-10z" },
      { kind: "circle", cx: 16, cy: 12, r: 2.5, fill: true },
    ],
  },
  percent: {
    elements: [
      { kind: "line", x1: 5, y1: 19, x2: 19, y2: 5 },
      { kind: "circle", cx: 7.5, cy: 7.5, r: 2.5 },
      { kind: "circle", cx: 16.5, cy: 16.5, r: 2.5 },
    ],
  },
  // --- Carril de secciones y modos de pantalla (§5.40) -----------------------------------------
  // Cinco puntos en pentágono: los cinco peligros RIDGE juntos.
  "dots-pentagon": {
    elements: [
      { kind: "circle", cx: 12, cy: 4.5, r: 2, fill: true },
      { kind: "circle", cx: 19.1, cy: 9.7, r: 2, fill: true },
      { kind: "circle", cx: 16.4, cy: 18.1, r: 2, fill: true },
      { kind: "circle", cx: 7.6, cy: 18.1, r: 2, fill: true },
      { kind: "circle", cx: 4.9, cy: 9.7, r: 2, fill: true },
    ],
  },
  // Dos letras A, una grande y otra pequeña: el tamaño del texto.
  "letters-two-sizes": {
    elements: [
      { kind: "polyline", points: "3,20 8.5,5 14,20" },
      { kind: "line", x1: 5.2, y1: 15, x2: 11.8, y2: 15 },
      { kind: "polyline", points: "14,20 17.5,11 21,20" },
      { kind: "line", x1: 15.3, y1: 17, x2: 19.7, y2: 17 },
    ],
  },
  // Un cuadrado partido en diagonal, una mitad llena y la otra vacía: el contraste.
  "square-split-diagonal": {
    elements: [
      { kind: "rect", x: 4, y: 4, width: 16, height: 16 },
      { kind: "polygon", points: "4,20 20,4 20,20", fill: true },
    ],
  },
  // Tres trazos cada vez más cortos: quedarse con lo esencial.
  "lines-narrowing": {
    elements: [
      { kind: "line", x1: 3, y1: 6, x2: 21, y2: 6 },
      { kind: "line", x1: 7, y1: 12, x2: 17, y2: 12 },
      { kind: "line", x1: 10.5, y1: 18, x2: 13.5, y2: 18 },
    ],
  },
  // Pantalla de tableta y la flecha curva que la gira.
  "screen-rotate": {
    elements: [
      { kind: "rect", x: 9, y: 8, width: 10, height: 13 },
      { kind: "path", d: "M4 15a8 8 0 0 1 9-11" },
      { kind: "polyline", points: "10,2 13,4 11,7" },
    ],
  },
  // El borde de arriba y dos galones que apuntan hacia él.
  "chevron-bar-up": {
    elements: [
      { kind: "line", x1: 4, y1: 4, x2: 20, y2: 4 },
      { kind: "polyline", points: "7,14 12,9 17,14" },
      { kind: "polyline", points: "7,20 12,15 17,20" },
    ],
  },
  // Ojo tachado: lo que no se deja ver.
  "eye-slash": {
    elements: [
      { kind: "path", d: "M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12z" },
      { kind: "circle", cx: 12, cy: 12, r: 3 },
      { kind: "line", x1: 4, y1: 20, x2: 20, y2: 4 },
    ],
  },
  // Contorno de una cabeza con la recta entre los dos ojos, inclinada: de esa recta sale el giro
  // de la vista cuando sigue la cara (`lib/faceOrientation.ts`).
  "head-eye-line": {
    elements: [
      { kind: "circle", cx: 12, cy: 12, r: 9 },
      { kind: "line", x1: 6.5, y1: 12.5, x2: 17.5, y2: 8.5 },
      { kind: "circle", cx: 8, cy: 12, r: 1.5, fill: true },
      { kind: "circle", cx: 16, cy: 9, r: 1.5, fill: true },
    ],
  },
  // Cámara de pantalla: el objetivo con su lente, sobre el pie. El aviso de «Cámara encendida».
  webcam: {
    elements: [
      { kind: "circle", cx: 12, cy: 10, r: 7 },
      { kind: "circle", cx: 12, cy: 10, r: 2.5, fill: true },
      { kind: "line", x1: 12, y1: 17, x2: 12, y2: 20 },
      { kind: "line", x1: 7, y1: 21, x2: 17, y2: 21 },
    ],
  },
  // Micrófono con un arco de onda a cada lado: escuchar la palabra «EMMA» (`assistant/wake/`) y el
  // aviso de «Micrófono escuchando». Distinto del micrófono solo de la nota dictada (`pain`).
  "microphone-arcs": {
    elements: [
      { kind: "path", d: "M10 5a2 2 0 0 1 4 0v6a2 2 0 0 1-4 0z" },
      { kind: "path", d: "M7.5 11a4.5 4.5 0 0 0 9 0" },
      { kind: "line", x1: 12, y1: 15.5, x2: 12, y2: 20 },
      { kind: "path", d: "M5 5a9 9 0 0 0 0 10" },
      { kind: "path", d: "M19 5a9 9 0 0 1 0 10" },
    ],
  },
} as const satisfies PictogramSet;
