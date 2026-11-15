import { domainLabel } from "../lib/levels";
import { prefixedPictogram } from "../lib/marks";
import { Mark } from "./Mark";

/**
 * El nombre de un dominio con su pictograma (`icons/sets/domains.ts`), sin color: nombrar un
 * dominio no es avisar de nada, y el nombre hereda el color de donde esté. La palabra es
 * `domainLabel` o la que da el backend (`label`). Un dominio que la interfaz no conoce se enseña
 * con su clave y el dibujo de «desconocido» (`prefixedPictogram`), también sin color: no se le
 * supone un dibujo.
 */
export function DomainName({ domain, label }: { domain: string; label?: string | undefined }) {
  return <Mark pictogram={prefixedPictogram("domain", domain)}>{label ?? domainLabel(domain)}</Mark>;
}
