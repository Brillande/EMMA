/**
 * Pictogramas de los informes escaneados: clases de informe e identidad (`reports/`).
 *
 * Cada clase de informe del backend (`app/reports`, `kind`) es una hoja con lo que la distingue:
 *
 *   - `pages-stack`: dos hojas superpuestas, los informes como conjunto (el título del panel).
 *   - `page-grid`: una hoja cuadriculada, la analítica (una tabla de cifras).
 *   - El informe de especialista lleva la hoja escrita de `common` (`sheet-lines`); la copia que
 *     había aquí (`page-lines`) se retiró en la segunda pasada (2026-10-21).
 *   - `page-arrow-right`: una hoja de la que sale una flecha, el informe de alta.
 *   - `page-blank`: una hoja sin nada dentro, «otro».
 *   - `circle-half-dashed`: medio círculo trazado y medio a trazos: una identidad que solo
 *     acredita uno de los dos datos (veredicto `parcial`). Los demás veredictos usan `shapes`.
 *
 * Las cifras leídas en una analítica se nombran con el pictograma de la familia de su indicador
 * (`components/IndicatorName.tsx`): aquí no se repite. Rejilla de 24×24, trazo de 2, sin color.
 *
 * Las hojas de clase van sobre la misma hoja que `sheet-lines` (`common`: de x = 6 a 19, la
 * esquina doblada de 5): en el selector de clase el dibujo cambia y la hoja no se mueve. Hasta la
 * segunda pasada (2026-10-21) cada una tenía su hoja —la cuadriculada sin esquina y de 5 a 19, la
 * de alta de 5 a 17, la vacía de 7 a 20— y al cambiar de clase la hoja saltaba una unidad.
 */

import type { PictogramSet } from "../types";

/** Una hoja con la esquina doblada, común a las clases de informe: la de `sheet-lines`. */
const SHEET = { kind: "path", d: "M6 3h8l5 5v13H6z" } as const;
const FOLD = { kind: "path", d: "M14 3v5h5" } as const;

export const reports = {
  "pages-stack": {
    elements: [
      { kind: "path", d: "M8 7V3h8l4 4v10h-4" },
      { kind: "path", d: "M4 7h8l4 4v10H4z" },
    ],
  },
  // La cuadrícula empieza bajo la esquina doblada (y = 9), para que el pliegue se siga leyendo.
  "page-grid": {
    elements: [
      SHEET,
      FOLD,
      { kind: "line", x1: 6, y1: 9, x2: 19, y2: 9 },
      { kind: "line", x1: 6, y1: 15, x2: 19, y2: 15 },
      { kind: "line", x1: 12, y1: 3, x2: 12, y2: 21 },
    ],
  },
  // La hoja queda abierta por la derecha bajo y = 11, por donde sale la flecha.
  "page-arrow-right": {
    elements: [
      { kind: "path", d: "M12 21H6V3h8l5 5v3" },
      FOLD,
      { kind: "line", x1: 11, y1: 16, x2: 21, y2: 16 },
      { kind: "polyline", points: "18,13 21,16 18,19" },
    ],
  },
  "page-blank": { elements: [SHEET, FOLD] },
  "circle-half-dashed": {
    elements: [
      { kind: "path", d: "M12 4a8 8 0 0 0 0 16" },
      { kind: "path", d: "M12 4a8 8 0 0 1 0 16", dashed: true },
    ],
  },
} as const satisfies PictogramSet;
