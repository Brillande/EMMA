import type { EvidenceItem } from "../lib/api";
import { EvidenceEntry } from "./EvidenceEntry";

/**
 * Una lista de fuentes citadas, tal y como las declara el backend (registro unico de evidencia,
 * `app/evidence/registry.py`). Cada fuente la pinta `EvidenceEntry`: la cita, su nivel, que es
 * (tipo, fecha, entorno y sobre quien se midio), para que se cita aqui y, en amarillo porque es
 * la advertencia, hasta donde llega. El alcance va siempre con la referencia: un estudio en
 * raton que se ensenara sin decir que es de raton pasaria por lo que no es.
 *
 * Vive aparte porque la usan la tarjeta de recomendacion y la cadena del modo anatomico: si
 * cada una pintara la evidencia a su manera, una acabaria ensenandola sin su alcance.
 */
export function EvidenceList({ items }: { items: EvidenceItem[] }) {
  return (
    <ul className="evidence">
      {items.map((evidence, index) => (
        // La misma ficha puede salir dos veces: como protocolo y como riesgo del dominio.
        <li key={`${evidence.id}-${index}`}>
          <EvidenceEntry item={evidence} />
        </li>
      ))}
    </ul>
  );
}
