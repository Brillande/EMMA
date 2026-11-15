import { useEffect, useState, useSyncExternalStore } from "react";

import { Command } from "../components/Command";
import { Toggle } from "../components/DisplayControls";
import { Mark } from "../components/Mark";
import { useVoiceAvailability } from "../components/ReadAloud";
import { formatNumber, formatUtc } from "../lib/format";
import { tr } from "../lib/i18n";
import { uiPictogram } from "../lib/uiMarks";
import { DEFAULT_SILENCE_MS, silenceFor, silencedUntil, subscribeSilence } from "./proactive";

/** Hasta cuándo dura el silencio, de la única fuente (`proactive.ts`); 0 si no hay. */
export function useSilence(): number {
  const until = useSyncExternalStore(subscribeSilence, silencedUntil, () => 0);
  // El silencio acaba solo: sin esto, el mando seguiría diciendo «en silencio» pasada la hora.
  const [, tick] = useState(0);
  useEffect(() => {
    const left = until - Date.now();
    if (left <= 0) return;
    const timer = setTimeout(() => tick((n) => n + 1), left + 50);
    return () => clearTimeout(timer);
  }, [until]);
  return until > Date.now() ? until : 0;
}

/**
 * El modo «EMMA toma la iniciativa» (`assistant/proactive.ts`) y su silencio. Los rótulos son de
 * navegación. Lleva el altavoz de la voz propia (`voice` en `lib/uiMarks.ts`): es la misma voz que
 * habla, no otro objeto; y el silencio, el altavoz tachado de «Parar la voz». Sin voz local no hay
 * mando: la marca gris de «no disponible» ya la pinta el modo voz a su lado. El mando de encender es
 * el `Toggle` de los demás modos de pantalla (`aria-pressed` y el anillo de «elegido»).
 *
 * El silencio dice a la vista que lo crítico se sigue diciendo (F.6.4: callar una alerta concreta
 * es suprimirla, con su firma; no lo hace un silencio general).
 */
export function ProactiveControls({
  on,
  onChange,
  silenced,
}: {
  on: boolean;
  onChange: (on: boolean) => void;
  /** Hasta cuándo dura el silencio (milisegundos de época), 0 si no hay. */
  silenced: number;
}) {
  const availability = useVoiceAvailability();
  // Sin voz, el modo voz ya enseña al lado la marca gris con el motivo: una vez basta.
  if (availability !== "ready") return null;
  return (
    <span className="proactive-controls">
      <Toggle on={on} onChange={onChange}>
        <Mark pictogram={uiPictogram("voice")}>{tr("EMMA toma la iniciativa", "EMMA takes the initiative")}</Mark>
      </Toggle>
      {on &&
        (silenced > 0 ? (
          <>
            <span role="status" className="secondary">
              {tr("En silencio hasta ", "Silent until ")}
              {formatUtc(new Date(silenced))}
              {tr("; las alertas que interrumpen se siguen diciendo", "; alerts that interrupt are still spoken")}
            </span>
            <Command type="button" concept="voice" onClick={() => silenceFor(0)}>
              {tr("Quitar el silencio", "End the silence")}
            </Command>
          </>
        ) : (
          <Command type="button" concept="stopVoice" onClick={() => silenceFor(DEFAULT_SILENCE_MS)}>
            {tr("Silencio ", "Silence ")}
            {formatNumber(DEFAULT_SILENCE_MS / 60_000)} min
          </Command>
        ))}
    </span>
  );
}
