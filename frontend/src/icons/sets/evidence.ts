/**
 * Pictogramas de la evidencia: nivel, clase de documento y población de cada fuente (`evidence/`).
 *
 * El backend da catorce niveles (`app/evidence/tier.py`) y trece clases de documento
 * (`app/evidence/registry.py`); dibujar uno por valor daría catorce formas que nadie distingue a
 * 12 px. Aquí hay un dibujo por lo que de verdad cambia la lectura, y `evidence/sourceMarks.ts`
 * reparte los valores:
 *
 * - Nivel, por el diseño del estudio: tres hojas apiladas (síntesis de varios estudios: guía,
 *   metaanálisis, revisión sistemática), dos barras comparadas (ensayo con grupos), hilera de
 *   puntos con flecha (cohorte seguida en el tiempo), un punto con flecha (caso o serie de casos),
 *   matraz (preclínico: animal, in vitro) y hoja a trazos (sin revisar: opinión, preprint). El
 *   desconocido lleva la interrogación de `shapes`.
 * - Clase de documento: tabla (conjunto de datos), hoja con renglones (artículo, informe,
 *   memorando, documento de programa), hoja con sello (norma y su resumen), lista con viñetas
 *   (entrada del catálogo de riesgos del HRP), hoja con cruz (ficha de condición médica), ventana
 *   de navegador (página de agencia), lupa (tarea de investigación), caballete (presentación) y
 *   hoja a trazos (preprint sin revisión por pares, el mismo dibujo que su nivel).
 * - Población: huella (animal) y persona con huella (humano y animal); la humana es la cabeza y
 *   hombros de `common` (`person`), que ya significa «una persona».
 *
 * Lo que comparte con otras áreas está en `common` (matraz, hoja con renglones, lupa, persona; y
 * desde la segunda pasada, 2026-10-21, las dos barras, la tabla, la hoja con sello y la lista con
 * viñetas, que son títulos y plegables de toda la interfaz: `lib/uiMarks.ts`); el entorno del
 * estudio usa los dibujos de `provenance` (`lib/provenance.ts`). El nombre es siempre el dibujo; el
 * significado, la palabra del backend que va al lado.
 */

import type { PictogramSet } from "../types";

/** Hoja con la esquina doblada, común a los documentos. */
const SHEET = { kind: "path", d: "M6 3h8l5 5v13H6z" } as const;
const FOLD = { kind: "path", d: "M14 3v5h5" } as const;

export const evidence = {
  // Nivel de evidencia.
  "layers-three": {
    elements: [
      { kind: "rect", x: 3, y: 9, width: 12, height: 12 },
      { kind: "path", d: "M6 9V6h12v12h-3" },
      { kind: "path", d: "M9 6V3h12v12h-3" },
    ],
  },
  "dots-arrow": {
    elements: [
      { kind: "circle", cx: 5, cy: 12, r: 1.6, fill: true },
      { kind: "circle", cx: 10, cy: 12, r: 1.6, fill: true },
      { kind: "circle", cx: 15, cy: 12, r: 1.6, fill: true },
      { kind: "polyline", points: "18,8 22,12 18,16" },
    ],
  },
  "dot-arrow": {
    elements: [
      { kind: "circle", cx: 8, cy: 12, r: 1.6, fill: true },
      { kind: "polyline", points: "13,8 17,12 13,16" },
    ],
  },
  "sheet-dashed": { elements: [{ ...SHEET, dashed: true }] },
  "sheet-plus": {
    elements: [
      SHEET,
      FOLD,
      { kind: "line", x1: 12.5, y1: 11, x2: 12.5, y2: 18 },
      { kind: "line", x1: 9, y1: 14.5, x2: 16, y2: 14.5 },
    ],
  },
  "window-bar": {
    elements: [
      { kind: "rect", x: 3, y: 4, width: 18, height: 16 },
      { kind: "line", x1: 3, y1: 9, x2: 21, y2: 9 },
      { kind: "circle", cx: 6.5, cy: 6.5, r: 0.9, fill: true },
      { kind: "circle", cx: 9.5, cy: 6.5, r: 0.9, fill: true },
    ],
  },
  easel: {
    elements: [
      { kind: "rect", x: 3, y: 4, width: 18, height: 12 },
      { kind: "path", d: "M8 21l4-5 4 5" },
    ],
  },
  // Población.
  paw: {
    elements: [
      { kind: "path", d: "M12 20c-3 0-5.5-2-5.5-4.5S9 11 12 11s5.5 2 5.5 4.5S15 20 12 20z" },
      { kind: "circle", cx: 6, cy: 9, r: 1.7, fill: true },
      { kind: "circle", cx: 10, cy: 5.5, r: 1.7, fill: true },
      { kind: "circle", cx: 14, cy: 5.5, r: 1.7, fill: true },
      { kind: "circle", cx: 18, cy: 9, r: 1.7, fill: true },
    ],
  },
  "person-paw": {
    elements: [
      { kind: "circle", cx: 8, cy: 7, r: 3 },
      { kind: "path", d: "M2.5 18a5.5 5.5 0 0 1 11 0" },
      { kind: "circle", cx: 17.5, cy: 18, r: 2.5 },
      { kind: "circle", cx: 14.5, cy: 13.5, r: 1.1, fill: true },
      { kind: "circle", cx: 17.5, cy: 12, r: 1.1, fill: true },
      { kind: "circle", cx: 20.5, cy: 13.5, r: 1.1, fill: true },
    ],
  },
} as const satisfies PictogramSet;
