import { formatNumber } from "../lib/format";
import { qualityStyle } from "../lib/provenance";
import { Mark } from "./Mark";

/**
 * Confianza de una lectura junto a su valor. La palabra es la del backend; aqui solo
 * se elige la senal: triangulo y amarillo si es baja, nada en los demas estados (ver
 * `lib/provenance.ts`). Sin confianza declarada no se pinta ningun numero.
 */
export function QualityBadge({
  state,
  label,
  confidence = null,
}: {
  state: string;
  label: string;
  confidence?: number | null;
}) {
  const style = qualityStyle(state);
  return (
    <Mark pictogram={style.pictogram} color={style.color} className="obs-type">
      {label}
      {confidence !== null && <span className="num"> {formatNumber(confidence, 2)}</span>}
    </Mark>
  );
}
