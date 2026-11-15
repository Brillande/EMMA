import type { ComponentPropsWithoutRef, ReactNode } from "react";

import { Pictogram } from "../icons";
import type { StateMark } from "../lib/marks";
import { type Sign, signPictogram, withoutSign } from "../lib/uiMarks";

/**
 * Un plegable (`<details>`) con el signo delante de su rótulo (§5.32 c, §5.33): el dibujo de qué
 * guarda, y la palabra, obligatoria. El resto de props van al `<details>` tal cual (`open`,
 * `className`, `onToggle`…); `summaryClassName` es la del `<summary>` (`lead` cuando el rótulo es
 * lo que hay que leer y no un rótulo).
 *
 * El pictograma va directo dentro del `<summary>`, como ya hacía «Acerca de EMMA»: el hueco lo
 * pone `summary > .pictogram`, y lo que se lee del rótulo sigue siendo solo la palabra.
 *
 * El signo puede ser, en vez de un concepto o un dibujo, la marca de un estado (`mark`, de
 * `lib/marks.ts`): lo que guarda el plegable es lo que falta («Huesos sin vóxeles», «Sin lectura»)
 * y su dibujo es el de ese estado. Entonces el color de la marca va solo en el dibujo, no en el
 * rótulo entero, y el plegable no lleva dos dibujos (el de qué guarda y el de su estado). Lo
 * pidió la silueta (§5.33.3) y lo hizo la limpieza (§5.33.12).
 */
type FoldSign = Sign | { readonly mark: StateMark; readonly concept?: never; readonly pictogram?: never };

export type FoldProps = FoldSign & {
  label: ReactNode;
  summaryClassName?: string;
  children: ReactNode;
} & Omit<ComponentPropsWithoutRef<"details">, "children">;

export function Fold(props: FoldProps) {
  let sign: ReactNode;
  let rest: Omit<FoldProps, "concept" | "pictogram" | "mark">;
  if ("mark" in props) {
    const { mark, concept: _concept, pictogram: _pictogram, ...others } = props;
    if (mark.pictogram === null) throw new RangeError("un plegable con una marca sin dibujo: le faltaría el signo");
    sign = <Pictogram name={mark.pictogram} className={mark.className} />;
    rest = others;
  } else {
    sign = <Pictogram name={signPictogram(props)} />;
    rest = withoutSign(props);
  }
  const { label, summaryClassName, children, ...details } = rest;
  return (
    <details {...details}>
      <summary className={summaryClassName}>
        {sign}
        {label}
      </summary>
      {children}
    </details>
  );
}
