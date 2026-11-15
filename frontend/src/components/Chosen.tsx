import type { ReactNode } from "react";

import { uiPictogram } from "../lib/uiMarks";
import { Mark } from "./Mark";

/**
 * El rótulo de una opción de un selector: la elegida lleva delante el signo de «elegido»
 * (`chosen`, el anillo con un punto: §5.32.3), las demás solo su palabra. La elección no se marca
 * solo con el color del botón pulsado (F.5.10 e).
 *
 * Por qué existe: ocho selectores de seis áreas (ventanas de Tierra, filtros de Polaris, lados de
 * la ecografía, cifras del dolor, páginas de un informe, la serie de una variable, las regiones
 * del cuerpo) escribían cada uno `pictogram={elegido ? "ring-dot" : null}` (§5.33.10). Y en una
 * fila de botones, el anillo que aparece solo en el elegido lo ensanchaba y movía la fila al
 * elegir: cuando la opción es el hijo directo de un botón con `aria-pressed` y no lleva más
 * dibujo, la que no está elegida reserva su hueco (`styles.css`,
 * `button[aria-pressed="false"] > .mark`), así que la fila ya no se mueve. No alcanza a la lista de
 * regiones (una columna, y su opción lleva el dibujo del dominio) ni a los rótulos de la silueta (colocados uno a uno):
 * allí el anillo no mueve ninguna fila.
 */
export function Chosen({ chosen, children }: { chosen: boolean; children: ReactNode }) {
  return <Mark pictogram={chosen ? uiPictogram("chosen") : null}>{children}</Mark>;
}
