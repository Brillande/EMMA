import type { ReactNode } from "react";

import { Pictogram } from "../icons";
import { formatNumber } from "../lib/format";
import type { StateMark } from "../lib/marks";
import { type Sign, signPictogram } from "../lib/uiMarks";
import { MarkOf } from "./Mark";

/**
 * Fichas con cifra: rótulo con su signo, la cifra grande y su unidad, y si hace falta el estado
 * con su marca (§5.33). Para los recuentos y los valores que se leen de un vistazo («cuántas
 * alertas», «dosis de hoy»), que hasta ahora iban en una frase.
 *
 * Una ficha no inventa una cifra: un número pasa por `formatNumber` (F.5.6), una cadena es la que
 * dio el backend, y `null` —no hay valor— exige `status`, que es la marca y la palabra que dicen
 * por qué no hay (dato ausente, no disponible). Sin ella la ficha lanza en vez de pintar un hueco
 * que se leería como cero. `stale` pone la ficha en cursiva: la tercera señal de caducado.
 *
 * `StatTiles` las agrupa con `role="group"` y su nombre accesible, para que un lector de pantalla
 * sepa de qué son las cifras.
 */
export function StatTiles({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="stat-tiles" role="group" aria-label={label}>
      {children}
    </div>
  );
}

export type StatTileProps = Sign & {
  label: ReactNode;
  value: number | string | null;
  decimals?: number;
  unit?: string;
  status?: { mark: StateMark; word: ReactNode };
  stale?: boolean;
  /** Lo que cuelga bajo la cifra: un `Meter` con su escala, una curva pequeña (tablero, 2026-11-07). */
  children?: ReactNode;
};

export function StatTile(props: StatTileProps) {
  const { label, value, decimals = 0, unit, status, stale = false, children } = props;
  if (value === null && status === undefined) {
    throw new Error("una ficha sin valor necesita su estado: sin él, el hueco se leería como cero");
  }
  return (
    <div className={stale ? "stat-tile stale" : "stat-tile"}>
      <span className="stat-label">
        <Pictogram name={signPictogram(props)} />
        {label}
      </span>
      {value !== null && (
        <span className="stat-value">
          <span className="num">{typeof value === "number" ? formatNumber(value, decimals) : value}</span>
          {unit !== undefined && (
            <>
              {" "}
              <span className="stat-unit">{unit}</span>
            </>
          )}
        </span>
      )}
      {status !== undefined && <MarkOf mark={status.mark}>{status.word}</MarkOf>}
      {children}
    </div>
  );
}
