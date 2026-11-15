/**
 * Evolucion de una medida ecografica: la anterior del mismo indicador y el cambio.
 *
 * Informa, no alerta. Estas medidas aun no generan alertas (no hay datos con que validar un
 * umbral: invariante 5), asi que la interfaz ensena el cambio con colores neutros y deja la
 * valoracion a quien lo lee. Nada de rojo ni amarillo aqui: seria una alerta sin validar.
 */

import type { FhirObservation } from "../lib/api";

export interface PreviousReading {
  value: number;
  effective: string;
}

/** La lectura mas reciente anterior al instante dado, o `null` si es la primera. */
export function previousReading(
  observations: readonly FhirObservation[],
  before: string,
): PreviousReading | null {
  const limit = Date.parse(before);
  let best: PreviousReading | null = null;
  for (const item of observations) {
    const at = Date.parse(item.effectiveDateTime);
    if (!(at < limit)) continue;
    if (best === null || at > Date.parse(best.effective)) {
      best = { value: item.valueQuantity.value, effective: item.effectiveDateTime };
    }
  }
  return best;
}
