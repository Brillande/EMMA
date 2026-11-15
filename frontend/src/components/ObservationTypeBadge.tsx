import { contextLabel, contextPictogram, typeStyle } from "../lib/provenance";
import { Mark } from "./Mark";

/**
 * Rotulo MEDIDO / INFERIDO / PREDICHO, con el entorno si se conoce. Palabra y pictograma,
 * sin color propio (ver `lib/provenance.ts`); el entorno tambien va con su dibujo
 * (`EVIDENCE_CONTEXT_PICTOGRAMS`) junto a su palabra.
 */
export function ObservationTypeBadge({
  type,
  context = null,
}: {
  type: string;
  context?: string | null;
}) {
  const style = typeStyle(type);
  return (
    <Mark pictogram={style.pictogram} className="obs-type" title={style.meaning}>
      {style.word}
      {context !== null && (
        <span className="secondary">
          {" "}
          · <Mark pictogram={contextPictogram(context)}>{contextLabel(context)}</Mark>
        </span>
      )}
    </Mark>
  );
}
