import { MISSING_MARK, scaleMark } from "../lib/marks";
import { useLook } from "../components/BoardOnly";
import { MarkOf } from "../components/Mark";
import { Meter } from "../components/Meter";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import type { CrewStatus } from "../lib/api";
import { formatNumber } from "../lib/format";

/**
 * Dosis acumulada frente al limite de carrera de NASA-STD-3001 [V1 4030], 600 mSv.
 *
 * Sin dosis facilitada no se pinta "0 de 600": se dice que falta, en cian (tabla
 * F.5-1, "Missing or stale data") y con el anillo punteado, para que el color no vaya
 * solo (F.5.10 e). La barra es neutra: el nivel de riesgo de radiacion lo decide el
 * backend y se muestra en su dominio. El trebol junto al titulo dice de que dosis se
 * habla; el limite y la cifra son del backend.
 *
 * Segunda pasada (§5.33.8): la barra es el medidor neutro del nucleo (`components/Meter.tsx`),
 * que generalizo la de aqui. Lo que cambia es lo de fuera de escala: una dosis por encima del
 * limite ya no se dibuja llena hasta el extremo (pasaria por "justo en el limite"), sino con la
 * barra vacia y la flecha junto a la cifra; y el tanto por ciento escrito es el del backend, sin
 * recortar a cien. La flecha la elige el medidor contra su escala, y el tanto por ciento va una
 * sola vez: fuera de escala, junto a la flecha y no tambien entre parentesis (§5.33.12).
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta la cifra va en una ficha
 * grande (`StatTile`) con el tanto por ciento y el mismo medidor colgando debajo; es la misma cifra
 * en otra forma, no una más, así que aquí la ficha sustituye al párrafo en vez de añadirse (por eso
 * `useLook` y no `BoardOnly`). La clásica sigue pintando el párrafo de siempre.
 */
export function DoseMeter({ dose }: { dose: CrewStatus["dose"] }) {
  return (
    <section data-ui="dose" className="panel" aria-label="Radiación">
      <PanelTitle concept="radiation">
        Dosis de carrera{" "}
        {/* Sin dosis no hay cifra que rotular: la etiqueta solo acompaña a un valor. */}
        {dose.cumulative_msv !== null && <ObservationTypeBadge type={dose.observation_type} />}
      </PanelTitle>
      {dose.cumulative_msv === null || dose.fraction === null ? (
        <p>
          <MarkOf mark={MISSING_MARK}>
            Sin dato de dosis acumulada: no se ha facilitado, y no se supone cero.
          </MarkOf>
        </p>
      ) : (
        <DoseFigure cumulative={dose.cumulative_msv} limit={dose.limit_msv} fraction={dose.fraction} />
      )}
      <p className="secondary">
        Límite de carrera de NASA-STD-3001 [V1 4030]:{" "}
        <span className="num">{formatNumber(dose.limit_msv)}</span> mSv.
      </p>
    </section>
  );
}

function DoseFigure({ cumulative, limit, fraction }: { cumulative: number; limit: number; fraction: number }) {
  const board = useLook() === "reference";
  const percent = `${formatNumber(fraction * 100, 1)} %`;
  // Fuera de escala el tanto por ciento lo dice el medidor junto a su flecha; aqui iria dos veces.
  const outside = limit > 0 && scaleMark(cumulative, 0, limit) !== null;
  // Sin límite positivo no hay escala que dibujar: queda la cifra.
  const meter = limit > 0 && (
    <Meter
      value={cumulative}
      max={limit}
      label="Dosis acumulada sobre el límite de carrera"
      outOfRange={{ word: percent }}
    />
  );
  if (board) {
    return (
      <div className="board-stats">
        <StatTile concept="radiation" label="Acumulada" value={cumulative} decimals={1} unit="mSv">
          {!outside && <span className="secondary num">({percent})</span>}
          {meter}
        </StatTile>
      </div>
    );
  }
  return (
    <>
      <p>
        <span className="num">{formatNumber(cumulative, 1)}</span> mSv
        {!outside && (
          <>
            {" "}
            <span className="secondary num">({percent})</span>
          </>
        )}
      </p>
      {meter}
    </>
  );
}
