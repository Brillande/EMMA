import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly } from "../components/BoardOnly";
import { IndicatorName } from "../components/IndicatorName";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import type { CrewStatus, Prediction } from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import { ImpactBar, RangeBar } from "./HomeCharts";
import { tr } from "../lib/i18n";

/**
 * Derivas reales llevadas a su horizonte: datos PREDICHOS, no recogidos. El margen y
 * el texto de que es la proyeccion los da el backend; cada indicador va con el pictograma
 * de su familia junto a su nombre (`IndicatorName`).
 *
 * En la concha de la maqueta cada fila lleva además sus dos barras (`PredictionBars`), a la derecha
 * de las cifras escritas, como «Proyecciones del estado» de «Inicio». Las cifras no cambian de sitio
 * ni de forma; el texto de la fila va envuelto en un `span` para que la fila pueda ser una rejilla.
 */
export function Predictions({
  predictions: all,
  onlyConcerning = false,
}: {
  predictions: CrewStatus["predictions"];
  /**
   * Consola de tripulacion: poco y relevante. Solo las derivas que el motor considera
   * preocupantes (reales, por encima del umbral clinico con confianza y en la direccion
   * mala); el resto se cuenta, no se lista (especificacion §10, sin fatiga de alarmas).
   * Tierra, densa, las ve todas.
   */
  onlyConcerning?: boolean;
}) {
  const predictions = onlyConcerning ? all.filter((item) => item.concerning) : all;
  const minor = all.length - predictions.length;
  if (all.length === 0) return null;
  // La barra más larga es la de la mayor deriva de las que se enseñan, no la de una que no se
  // lista (como en «Inicio», que lo aprendió de la revisión de la unidad 8).
  const widest = Math.max(1e-9, ...predictions.map((item) => Math.abs(item.projected_change)));
  return (
    <section data-ui="predictions" className="panel" aria-label={tr("Proyecciones", "Projections")}>
      <PanelTitle concept="predictions">
        {tr("Proyecciones", "Projections")} <ObservationTypeBadge type="predicted" />
      </PanelTitle>
      <ul className="predictions">
        {predictions.map((item) => {
          const unit = displayUnit(item.unit);
          return (
            <li key={item.key}>
              <span className="prediction-text">
                <strong>
                  <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
                </strong>
                :{" "}
                <span className="num">{signed(item.projected_change, item.decimals)}</span> {unit}{" "}
                {tr("en", "in")}{" "}
                <span className="num">{formatNumber(item.horizon_weeks)}</span> {tr("semanas", "weeks")}{" "}
                <span className="secondary">
                  ({tr("margen", "margin")}{" "}
                  <span className="num">{formatNumber(item.projected_change_low, item.decimals)}</span>{" "}
                  {tr("a", "to")} <span className="num">{formatNumber(item.projected_change_high, item.decimals)}</span>{" "}
                  {unit})
                </span>
              </span>
              <BoardOnly>
                <PredictionBars item={item} widest={widest} unit={unit} />
              </BoardOnly>
            </li>
          );
        })}
      </ul>
      {/* La cuenta de las que no se listan sigue a la vista: sin ella, a bordo y sin derivas
          preocupantes, el panel quedaría vacío sin decir por qué (lo señaló la revisión). La base de
          la proyección es lectura: en la concha de la maqueta va tras «Ver detalle» (muestra,
          2026-11-08). */}
      {minor > 0 && (
        <p className="secondary">
          <span className="num">{formatNumber(minor)}</span>{" "}
          {tr(
            "derivas más, reales pero que no preocupan; se ven en la consola de Tierra.",
            "more drifts, real but not worrying; they are shown in the Earth console.",
          )}
        </p>
      )}
      {all[0] !== undefined && (
        <BoardDetail label={tr("cómo se proyecta", "how it is projected")}>
          <p className="secondary">{all[0].basis}</p>
        </BoardDetail>
      )}
    </section>
  );
}

/**
 * Las dos barras de una proyección (tablero, 2026-11-07), junto a sus cifras escritas, que son las
 * que se leen. Arriba, la proporción: la mayor deriva enseñada es la barra más larga, y solo va
 * amarilla si el backend dice `concerning`. Debajo, el margen `low..high` con la proyección como
 * marca, sobre una escala simétrica alrededor del cero hecha con el extremo de la propia fila: el
 * centro es «sin cambio», así se ve de qué lado cae la deriva y si su margen cruza el cero. La escala
 * es la de cada fila, porque las filas tienen unidades distintas y no se comparan entre sí; con todo
 * a cero o con el margen al revés no se dibuja: las cifras escritas ya lo dicen.
 */
function PredictionBars({ item, widest, unit }: { item: Prediction; widest: number; unit: string }) {
  const { projected_change: change, projected_change_low: low, projected_change_high: high, decimals } = item;
  const extreme = Math.max(Math.abs(low), Math.abs(high), Math.abs(change));
  const drawable = Number.isFinite(extreme) && extreme > 0 && low <= high;
  return (
    <span className="prediction-bars">
      {Number.isFinite(change) && <ImpactBar share={Math.abs(change) / widest} concerning={item.concerning} />}
      {drawable && (
        <RangeBar
          low={low}
          high={high}
          min={-extreme}
          max={extreme}
          marker={change}
          label={tr(
            `margen de ${formatNumber(low, decimals)} a ${formatNumber(high, decimals)} ${unit}; proyección ${signed(change, decimals)} ${unit}`,
            `margin from ${formatNumber(low, decimals)} to ${formatNumber(high, decimals)} ${unit}; projection ${signed(change, decimals)} ${unit}`,
          )}
        />
      )}
    </span>
  );
}

/** Un cambio lleva su sentido escrito: "sube 3" y "baja 3" no se leen por el color. */
function signed(value: number, decimals: number): string {
  if (value === 0) return formatNumber(0, decimals);
  return `${value > 0 ? tr("sube", "up") : tr("baja", "down")} ${formatNumber(Math.abs(value), decimals)}`;
}
