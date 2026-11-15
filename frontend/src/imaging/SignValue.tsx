import type { ReactNode } from "react";

import { Mark } from "../components/Mark";
import { signValueMark } from "./findings";

/**
 * El valor de un signo anotado con su marca (`signValueMark`): la ventana con algo dentro, la
 * ventana vacia o «no disponible». La palabra es la del protocolo del backend. Va aparte del
 * formulario de a bordo porque lo pintan dos consolas: la de tripulacion (`FindingsPanel`) y la de
 * Tierra (`ImagingHistory`), y Tierra no tiene por que arrastrar un formulario con sus hooks.
 */
export function SignValue({ code, children }: { code: string; children: ReactNode }) {
  const style = signValueMark(code);
  return (
    <Mark pictogram={style.pictogram} color={style.color}>
      {children}
    </Mark>
  );
}
