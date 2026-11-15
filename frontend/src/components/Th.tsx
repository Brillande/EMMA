import type { ComponentPropsWithoutRef, ReactNode } from "react";

import { Pictogram } from "../icons";
import { type Sign, signPictogram, withoutSign } from "../lib/uiMarks";

/**
 * Una cabecera de tabla con su signo delante (§5.32 c, §5.33): «valor», «hora», «procedencia»…
 * llevan el mismo dibujo en todas las tablas. `scope="col"` por defecto, porque casi todas las
 * cabeceras de EMMA son de columna; la de fila lo dice (`scope="row"`).
 *
 * Por qué el dibujo y la palabra van dentro de un `span.th-sign`, al contrario que en las demás
 * piezas: en una columna estrecha el navegador parte la línea entre el dibujo y la palabra, y el
 * dibujo se quedaba solo encima de su cabecera («Lesión» de la comparación, «Quién anota» del
 * diario; §5.33.7, §5.33.9). El hueco entre un dibujo y el texto que le sigue es un punto de corte
 * que solo controla su antepasado común, así que hace falta uno: el `span` es un `inline-flex`
 * (`styles.css`) en el que el dibujo no se separa de la primera línea y el texto largo se parte a
 * su derecha, sin obligar a la columna a ensancharse.
 */
export type ThProps = Sign & {
  children: ReactNode;
} & Omit<ComponentPropsWithoutRef<"th">, "children">;

export function Th(props: ThProps) {
  const { children, scope = "col", ...th } = withoutSign(props);
  return (
    <th scope={scope} {...th}>
      <span className="th-sign">
        <Pictogram name={signPictogram(props)} />
        {children}
      </span>
    </th>
  );
}
