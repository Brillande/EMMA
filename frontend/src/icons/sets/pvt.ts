/**
 * Pictogramas de la prueba de vigilancia psicomotora (`pvt/`).
 *
 * Por qué están aquí y no en `shapes`: son los signos de comparar un valor con otro y de decir
 * de dónde sale un parámetro, que hasta el rediseño pictográfico (2026-10-20) el panel escribía
 * como caracteres («=», «≠») o no escribía (el respaldo solo tenía palabra). El nombre describe el
 * dibujo; el significado lo pone la palabra del backend al lado (`pvt/marks.ts`):
 *
 * - `tilde-double`: dos rayas onduladas, la misma cifra con otro operador. Las dos rayas de «mismo
 *   valor» (`equals`) y las tachadas de «valor distinto» (`not-equal`) viven en `common`: las
 *   comparten el dolor, los volúmenes y Tierra. La PVT dibujó su propio «difiere» (`equals-slash`,
 *   `not-equal` con la barra en otro ángulo) y se retiró en la segunda pasada (2026-10-21): un
 *   concepto, un dibujo.
 * - El respaldo de un parámetro va con dibujos de `common`: la hoja escrita (`sheet-lines`, escrito
 *   en el repositorio; la copia `document-lines` era la misma hoja y se retiró), el lápiz de
 *   «decidido por diseño» (`pencil`, también el del alta manual de una lectura) y el libro abierto
 *   (`book-open`, leído en la fuente; hoy también el dibujo de la documentación en toda la
 *   interfaz, `lib/uiMarks.ts`).
 *
 * Las formas de la sesión (□ ■ ○ ✓) y «no comparable» (–) ya estaban en `shapes`. Las cifras de la
 * prueba no viven aquí ni en el panel: las da el backend.
 */

import type { PictogramSet } from "../types";

export const pvt = {
  "tilde-double": {
    elements: [
      { kind: "path", d: "M5 9.5c2.3-2.3 4.7-2.3 7 0s4.7 2.3 7 0" },
      { kind: "path", d: "M5 15.5c2.3-2.3 4.7-2.3 7 0s4.7 2.3 7 0" },
    ],
  },
} as const satisfies PictogramSet;
