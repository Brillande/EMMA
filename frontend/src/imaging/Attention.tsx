import type { ReactNode } from "react";

import { Mark, MarkOf } from "../components/Mark";
import { requestOutcome } from "../lib/marks";

/**
 * Un aviso del backend que hay que mirar y que no es el resultado de una peticion (texto quemado
 * en la imagen de un estudio registrado, por ejemplo): el triangulo en amarillo (tabla F.5-1,
 * *attention required*) junto a su texto, tal cual.
 *
 * Por que existe: los paneles de ecografia y de informes pintaban esos avisos como un parrafo
 * amarillo sin forma, y en EMMA un color nunca va solo (F.5.10 e). La segunda pasada (§5.33.10)
 * les dio la forma que ya llevaban los demas avisos amarillos del area. Lo que sale mal en una
 * peticion no pasa por aqui sino por `ReasonLine` (§5.34.14).
 */
export function Attention({ children }: { children: ReactNode }) {
  return (
    <p className="c-yellow">
      <Mark pictogram="shape-triangle">{children}</Mark>
    </p>
  );
}

/**
 * Lo que salio mal en una peticion, con la marca que le toca por lo que es y no por el sitio que
 * la hizo (`requestOutcome`, `lib/marks.ts`): el rechazo del backend (4xx) con `REFUSED_MARK`, el
 * fallo (5xx, sin red) con `FAILURE_MARK`. El texto es el motivo del backend tal cual, o el error
 * si no lo hay. Hasta §5.34.14 el rechazo se componia aqui a mano, con el parrafo en amarillo y el
 * triangulo escrito; ahora lleva la marca de toda la interfaz.
 */
export function ReasonLine({ reason }: { reason: unknown }) {
  const outcome = requestOutcome(reason);
  return (
    <p>
      <MarkOf mark={outcome.mark}>{outcome.text}</MarkOf>
    </p>
  );
}
