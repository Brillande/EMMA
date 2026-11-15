import { useEffect, useState } from "react";

import { type AnatomyState, type CrewStatus, api } from "../lib/api";
import { type RequestOutcome, requestOutcome } from "../lib/marks";

/**
 * El estado por regiones (`/api/anatomy/state`), pedido una sola vez para quien lo pinte.
 *
 * Por qué existe fuera del panel: la cadena por regiones la enseñan ahora dos sitios de la
 * consola de tripulación —la silueta del resumen (`BodySilhouette`) y el modo anatómico
 * (`AnatomyPanel`)— y los dos tienen que ver la MISMA respuesta: si cada uno la pidiera, un TAC o
 * una lectura registrada entre una petición y otra pondría un nivel en la silueta y otro en la
 * lista. La consola llama a este gancho una vez y reparte el resultado; la región elegida vive
 * también en la consola, para que pulsar la silueta abra la cadena de esa región.
 *
 * Cuando cambia lo que `/status` ha valorado, la cadena se vuelve a pedir. El veredicto de
 * `status` (niveles, motivos y recomendaciones) solo avisa de que algo cambió —un evento solar o
 * una lectura enmendada no mueven la fecha de referencia—; no se pinta desde aquí: lo que se
 * enseña es siempre lo que devuelve el endpoint. Y si lo que hay es de otro instante o de otro
 * tripulante que el estado de la consola (mientras llega la respuesta nueva, o si no llega), se
 * dice en los dos sitios (`stale`, F.4.3.1 c). Si la peticion sale mal, `error` lleva la marca de
 * lo que fue (`requestOutcome`, §5.34.14): antes se pintaba como dato ausente, en cian.
 */
export interface AnatomyView {
  readonly state: AnatomyState | null;
  readonly error: RequestOutcome | null;
  /** El estado que hay es de otro instante o de otro tripulante que el de la consola. */
  readonly stale: boolean;
}

export function useAnatomyState(status: CrewStatus): AnatomyView {
  const [state, setState] = useState<AnatomyState | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);

  const sourcesKey = status.mission.sources.join(",");
  const verdictKey = JSON.stringify([
    Object.entries(status.domains).map(([domain, risk]) => [domain, risk.level, risk.drivers]),
    status.recommendations.map((item) => [item.domain, item.action]),
  ]);
  useEffect(() => {
    let cancelled = false;
    api
      .anatomyState(status.subject)
      .then((body) => {
        if (cancelled) return;
        setState(body);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(requestOutcome(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [
    status.subject,
    status.data.reference_time,
    status.data.observations,
    status.rules_version,
    sourcesKey,
    verdictKey,
  ]);

  const stale =
    state !== null &&
    (state.reference_time !== status.data.reference_time || state.subject !== status.subject);
  return { state, error, stale };
}
