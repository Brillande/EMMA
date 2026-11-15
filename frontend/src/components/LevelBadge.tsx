import { levelStyle } from "../lib/levels";
import { Mark } from "./Mark";

/**
 * Un nivel de riesgo: pictograma, palabra y color, siempre los tres (F.5.10 e). El pictograma
 * parpadea solo si el nivel es critico y la alerta no se ha reconocido.
 */
export function LevelBadge({ level, flashing = false }: { level: string; flashing?: boolean }) {
  const style = levelStyle(level);
  return (
    <Mark pictogram={style.pictogram} color={style.color} flashing={flashing && style.flashes} className="level">
      {style.label}
    </Mark>
  );
}
