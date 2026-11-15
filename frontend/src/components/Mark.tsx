import type { ReactNode } from "react";

import { Pictogram, type PictogramName } from "../icons";
import type { StateMark } from "../lib/marks";
import type { Token } from "../lib/palette";

/**
 * Pictograma junto a la palabra, con el color del significado: la pieza con la que se pinta todo
 * estado (F.5.10 e: el color nunca va solo, y aquí tampoco la forma).
 *
 * La palabra es el hijo y la da el backend o un rótulo que ya existía: este componente no redacta.
 * El hueco entre pictograma y palabra lo pone el CSS (`.mark > .pictogram`), no un espacio en el
 * texto, para que el texto visible sea la palabra y nada más. Solo el pictograma parpadea
 * (`flashing`), y solo lo pide el nivel crítico sin reconocer.
 *
 * `stale` añade la clase `stale` (cursiva, `styles.css`): la tercera señal de dato caducado,
 * junto al cian y al anillo punteado, como hace Open MCT con la cursiva del valor viejo (§5.33).
 */
export function Mark({
  pictogram,
  color = null,
  flashing = false,
  stale = false,
  className,
  title,
  children,
}: {
  pictogram: PictogramName | null;
  color?: Token | null | undefined;
  flashing?: boolean | undefined;
  stale?: boolean | undefined;
  className?: string | undefined;
  title?: string | undefined;
  /** La palabra: obligatoria, porque un pictograma solo no existe en EMMA (§5.32 a). */
  children: ReactNode;
}) {
  const classes = ["mark", className, stale ? "stale" : undefined, color === null ? undefined : `c-${color}`]
    .filter((item) => item !== undefined)
    .join(" ");
  return (
    <span className={classes} title={title}>
      {pictogram !== null && <Pictogram name={pictogram} className={flashing ? "flash" : undefined} />}
      {children}
    </span>
  );
}

/**
 * `<Mark>` a partir de una marca de tabla (`lib/marks.ts`): el pictograma y el color que decidió
 * la tabla, y como hijo la palabra, que es del backend. Existe porque un `StateMark` lleva ya la
 * clase `c-<token>` calculada y extenderlo tal cual sobre `<Mark>` la pondría dos veces; y porque
 * cinco áreas (hábitat, Tierra, volúmenes, asesor, diario) habían escrito cada una su copia de
 * estas cuatro líneas.
 */
export function MarkOf({
  mark,
  stale = false,
  className,
  title,
  children,
}: {
  mark: StateMark;
  stale?: boolean | undefined;
  className?: string | undefined;
  title?: string | undefined;
  children: ReactNode;
}) {
  return (
    <Mark pictogram={mark.pictogram} color={mark.color} stale={stale} className={className} title={title}>
      {children}
    </Mark>
  );
}
