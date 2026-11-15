import { MarkOf } from "../components/Mark";
import type { RequestOutcome } from "../lib/marks";

/**
 * El fallo de una peticion del asesor (adoptar, no adoptar, cerrar un seguimiento, declarar un
 * recurso), con el texto que devuelve, tal cual.
 *
 * Por que existe: las cuatro lo pintaban cada una con su `span` amarillo, color sin forma. La
 * segunda pasada (§5.33.5) le pone el triangulo de precaucion delante, y lo hace aqui una vez en
 * vez de en cuatro copias. Desde la decision del usuario (2026-10-21, §5.34.14) la marca es la de
 * lo que paso (`requestOutcome`, `lib/marks.ts`): el rechazo del backend (4xx, falta quien firma o
 * el motivo) en amarillo con el triangulo, `REFUSED_MARK`; la peticion caida (5xx, sin red) en
 * rojo con la cruz, `FAILURE_MARK`. Hasta entonces las dos salian en amarillo.
 */
export function RequestWarning({ outcome }: { outcome: RequestOutcome }) {
  return (
    <>
      {" "}
      <MarkOf mark={outcome.mark}>{outcome.text}</MarkOf>
    </>
  );
}
