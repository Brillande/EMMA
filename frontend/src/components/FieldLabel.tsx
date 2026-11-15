import type { ReactNode } from "react";

import { Pictogram } from "../icons";
import { type Sign, signPictogram } from "../lib/uiMarks";

/**
 * El rótulo de un campo con su signo delante (§5.32 c, §5.33): un `<label>` de formulario, el
 * `<dt>` de una lista de definiciones, la `<legend>` de un grupo o un `<span>` que rotula una
 * lectura sin ser campo de formulario (las celdas de la franja: un `<label>` sin control lo
 * anunciaría como tal). Mismo dibujo por concepto que los títulos y las cabeceras; la palabra es
 * obligatoria.
 *
 * `htmlFor` solo tiene sentido en un `<label>`, y solo ahí se pasa.
 */
export type FieldLabelProps = Sign & {
  as?: "label" | "dt" | "legend" | "span";
  htmlFor?: string;
  className?: string;
  children: ReactNode;
};

export function FieldLabel(props: FieldLabelProps) {
  const { as = "label", htmlFor, className, children } = props;
  const content = (
    <>
      <Pictogram name={signPictogram(props)} />
      {children}
    </>
  );
  if (as === "label") {
    return (
      <label className={className} htmlFor={htmlFor}>
        {content}
      </label>
    );
  }
  const Tag = as;
  return <Tag className={className}>{content}</Tag>;
}
