import { type StateMark, scaleMark } from "../lib/marks";
import { MarkOf } from "./Mark";

/**
 * Un medidor neutro: una barra que dice dónde cae un valor entre un mínimo y un máximo, y si se
 * pide la banda de referencia (§5.33). Nació generalizando la barra del dosímetro
 * (`radiation/DoseMeter.tsx`), que desde §5.33.8 lo usa también.
 *
 * Neutro quiere decir sin color con significado: solo `--c-raised` (el fondo), `--c-line` (la
 * banda) y `--c-text-secondary` (el relleno). Si un valor preocupa lo dice el nivel del backend
 * con su marca, no el color de una barra.
 *
 * Patrón de Open MCT (Apache-2.0, citado como patrón, sin copiar código): un valor fuera de la
 * escala no se dibuja recortado en el extremo, que lo haría pasar por «justo en el límite»; se
 * señala. Aquí la barra queda vacía y con el borde discontinuo (`meter-oor`), y al lado va
 * `outOfRange`, la palabra que lo dice, obligatoria en ese caso: sin ella el medidor lanza. La
 * marca la elige el medidor contra su escala (la flecha hacia arriba por encima del máximo, hacia
 * abajo por debajo del mínimo, sin color: `scaleMark` de `lib/marks.ts`); quien tiene
 * una marca con más significado (el límite normativo del hábitat) la pasa en `outOfRange.mark`.
 * Hasta la limpieza (§5.33.12) la flecha la elegía `radiation/marks.ts`, que solo valía con
 * mínimo cero.
 *
 * `stale` pone en cursiva el bloque, como el valor caducado de Open MCT: la barra no tiene texto,
 * así que la cursiva cae en la palabra de fuera de escala, y quien escribe la cifra junto al
 * medidor la marca caducada con su propia marca (`MISSING_MARK`, `<Mark stale>`).
 *
 * Para el lector de pantalla, `aria-valuenow` tiene que caer dentro de la escala (ARIA, rol
 * `meter`): fuera de ella va el extremo que se pasó y `aria-valuetext` lleva la palabra que lo dice.
 */
export type MeterProps = {
  value: number;
  min?: number;
  max: number;
  /** El nombre accesible de la barra: qué se mide. */
  label: string;
  band?: { low: number; high: number };
  outOfRange?: { word: string; mark?: StateMark };
  stale?: boolean;
};

export function Meter({ value, min = 0, max, label, band, outOfRange, stale = false }: MeterProps) {
  if (!(max > min) || !Number.isFinite(value)) {
    throw new RangeError(`medidor sin escala o sin valor: ${value} en [${min}, ${max}]`);
  }
  if (band !== undefined && !(band.low <= band.high)) {
    throw new RangeError(`banda de referencia al revés: [${band.low}, ${band.high}]`);
  }
  const side = scaleMark(value, min, max);
  const inRange = side === null;
  if (!inRange && outOfRange === undefined) {
    throw new RangeError(`valor fuera de escala sin marca que lo diga: ${value} en [${min}, ${max}]`);
  }
  const percent = (x: number) => ((Math.min(max, Math.max(min, x)) - min) / (max - min)) * 100;
  return (
    <div className={stale ? "meter-block stale" : "meter-block"}>
      <div
        className={inRange ? "meter" : "meter meter-oor"}
        role="meter"
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={Math.min(max, Math.max(min, value))}
        aria-valuetext={inRange || outOfRange === undefined ? undefined : outOfRange.word}
      >
        {band !== undefined && (
          <div
            className="meter-band"
            style={{ left: `${percent(band.low)}%`, width: `${percent(band.high) - percent(band.low)}%` }}
          />
        )}
        {inRange && <div className="meter-fill" style={{ width: `${percent(value)}%` }} />}
      </div>
      {side !== null && outOfRange !== undefined && <MarkOf mark={outOfRange.mark ?? side}>{outOfRange.word}</MarkOf>}
    </div>
  );
}
