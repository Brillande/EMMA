import type { ReactNode } from "react";

import { Pictogram } from "../icons";
import { type Sign, signPictogram } from "../lib/uiMarks";

/**
 * El título de un panel con su signo delante (§5.32 c, §5.33): el dibujo de qué es ese panel,
 * el mismo en toda la interfaz (`lib/uiMarks.ts`), y después la palabra, que es obligatoria.
 *
 * Por qué existe: con la segunda pasada todo título lleva pictograma, y once unidades iban a
 * escribir `<h2><Pictogram name=…/>…</h2>` cada una con su dibujo. Aquí el dibujo sale del
 * concepto y el pictograma va directo dentro del título, sin `<span>` intermedio: el hueco lo pone
 * `h2 > .pictogram` en el CSS, y el color, si lo hay, la clase del título (`c-cyan` de lo que
 * falta, por ejemplo).
 */
export type PanelTitleProps = Sign & {
  as?: "h2" | "h3" | "h4";
  className?: string;
  children: ReactNode;
};

export function PanelTitle(props: PanelTitleProps) {
  const { as: Tag = "h2", className, children } = props;
  return (
    <Tag className={className}>
      <Pictogram name={signPictogram(props)} />
      {children}
    </Tag>
  );
}
