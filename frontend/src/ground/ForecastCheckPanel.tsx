import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly } from "../components/BoardOnly";
import { IndicatorName } from "../components/IndicatorName";
import { Mark } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import type { PictogramName } from "../icons";
import { RangeBar, Ring } from "../dashboard/HomeCharts";
import type { CrewStatus, ForecastCheck } from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import { UNKNOWN_MARK } from "../lib/marks";
import { tr } from "../lib/i18n";

export interface CheckKind {
  label: string;
  pictogram: PictogramName | null;
}

/**
 * Las dos clases de comprobación, con su rótulo y su pictograma: mirar atrás (reloj con la flecha
 * que gira hacia atrás) y la instantánea firmada el día que se hizo (cámara, la misma que lleva su
 * asiento en el registro).
 */
export const KIND: Readonly<Record<string, CheckKind>> = {
  hindcast: { label: tr("retrospectiva", "hindcast"), pictogram: "clock-rewind" },
  snapshot: { label: tr("instantánea firmada", "signed snapshot"), pictogram: "camera" },
};

/** Una clase que la interfaz no conoce se enseña con su clave y la marca de «desconocido»: no tumba la tabla. */
export function checkKind(kind: string): CheckKind {
  return KIND[kind] ?? { label: kind, pictogram: UNKNOWN_MARK.pictogram };
}

/**
 * ¿Acertaron las proyecciones? (conversacion de ideacion: "prediccion → resultado →
 * validacion"). Cada fila compara el cambio proyectado y su margen con el medido. Sin color
 * de alerta: es calibracion del propio modelo, no un hallazgo sobre nadie. Dentro del margen
 * lleva el anillo; fuera, el rombo en azul (aviso, F.5-1), como en la recuperacion posvuelo.
 * La base la redacta el backend.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta (`BoardOnly`), arriba el
 * anillo de cuántas comprobadas cayeron dentro de su margen (la frase de debajo, «n de m dentro de su
 * margen», le hace de leyenda), neutro como el resto del panel, y en
 * cada fila el margen proyectado como tramo con el cambio medido como marca (`MarginBar`). Las
 * cifras escritas no cambian ni de sitio ni de forma: son las que se leen.
 *
 * Una pantalla por sección (2026-11-08): la tabla medía 480 px a 7 de 12 columnas. Ahora, junto al
 * anillo, una fila por indicador con su nombre, el tramo y la marca de dentro o fuera; la tabla con
 * las cifras escritas y la base del backend, detrás de «Ver detalle» (en la clásica, como siempre).
 */
export function ForecastCheckPanel({ checks }: { checks: CrewStatus["forecast_checks"] }) {
  if (checks.checked === 0) return null;
  return (
    <section data-ui="forecast-check" className="panel" aria-label={tr("Comprobación de proyecciones", "Projection check")}>
      <PanelTitle concept="forecastCheck">
        {tr("¿Acertaron las proyecciones?", "Did the projections hold?")}
      </PanelTitle>
      <BoardOnly>
        <div className="board-row forecast-board">
          <div className="ref-ring-col">
            <Ring done={checks.within_margin} total={checks.checked} label={tr("comprobadas dentro de su margen", "checked within their margin")}>
              <span className="num ref-ring-value">{formatNumber(checks.within_margin)}</span>
              <span className="num secondary">/ {formatNumber(checks.checked)}</span>
            </Ring>
          </div>
          <ul className="forecast-rows" aria-label={tr("Margen proyectado y lo medido, por indicador", "Projected margin and measured value, by indicator")}>
            {checks.checks.map((item) => {
              const unit = item.unit !== null ? displayUnit(item.unit) : "";
              return (
                <li key={`${item.kind}:${item.key}`}>
                  <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
                  <MarginBar item={item} unit={unit} />
                  <WithinMark within={item.within_margin} />
                </li>
              );
            })}
          </ul>
        </div>
      </BoardOnly>
      <p>
        <span className="num">{formatNumber(checks.within_margin)}</span> {tr("de", "of")}{" "}
        <span className="num">{formatNumber(checks.checked)}</span>{" "}
        {tr("dentro de su margen", "within their margin")}
      </p>
      {/* La tabla con las cifras escritas y la base del backend, detrás de «Ver detalle» en el
          tablero: arriba ya van el anillo y, por fila, el margen como tramo con su marca. */}
      <BoardDetail label={tr("cifras y base", "figures and basis")}>
      {/* Se desplaza dentro de su caja en pantalla estrecha, como las otras tablas de Tierra
          (`.quality-table`): a 390 px salía 10 px del panel (§5.37.17). */}
      <div className="quality-table table-scroll" role="region" tabIndex={0} aria-label={tr("Proyectado frente a medido", "Projected versus measured")}>
        <table className="recovery">
          <thead>
            <tr>
              <Th concept="indicator">{tr("Indicador", "Indicator")}</Th>
              <Th concept="range">{tr("Proyectado (margen)", "Projected (margin)")}</Th>
              <Th concept="measured">{tr("Medido", "Measured")}</Th>
              <Th concept="type">{tr("Tipo", "Type")}</Th>
            </tr>
          </thead>
          <tbody>
            {checks.checks.map((item) => {
              const unit = item.unit !== null ? displayUnit(item.unit) : "";
              const kind = checkKind(item.kind);
              return (
                <tr key={`${item.kind}:${item.key}`}>
                  <th scope="row">
                    <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
                  </th>
                  <td>
                    <span className="num">{formatNumber(item.projected_change, 2)}</span> {unit}{" "}
                    <span className="secondary">
                      (<span className="num">{formatNumber(item.projected_change_low, 2)}</span> {tr("a", "to")}{" "}
                      <span className="num">{formatNumber(item.projected_change_high, 2)}</span>)
                    </span>
                  </td>
                  <td>
                    <span className="num">{formatNumber(item.actual_change, 2)}</span> {unit}{" "}
                    <WithinMark within={item.within_margin} />
                  </td>
                  <td className="secondary">
                    <Mark pictogram={kind.pictogram}>{kind.label}</Mark>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="secondary">{checks.basis}</p>
      </BoardDetail>
    </section>
  );
}

/** Dentro del margen, el anillo sin color; fuera, el rombo en azul (aviso, F.5-1). */
function WithinMark({ within }: { within: boolean }) {
  return within ? (
    <Mark pictogram="shape-circle" className="secondary">
      {tr("dentro", "within")}
    </Mark>
  ) : (
    <Mark pictogram="shape-diamond" color="blue">
      {tr("fuera", "outside")}
    </Mark>
  );
}

/**
 * El margen proyectado de una fila como tramo, con el cambio medido como marca: de un vistazo, si lo
 * medido cayó dentro o fuera y hacia qué lado. La escala es simétrica alrededor del cero y la hace el
 * extremo de la propia fila (el margen y los dos cambios), como en «Proyecciones»: las filas tienen
 * unidades distintas y no se comparan entre sí. Con todo a cero o con el margen al revés no se dibuja:
 * las cifras escritas ya lo dicen. El dentro o fuera lo sigue diciendo la marca con su palabra.
 */
export function MarginBar({ item, unit }: { item: ForecastCheck; unit: string }) {
  const { projected_change_low: low, projected_change_high: high, projected_change: projected, actual_change: actual } = item;
  const extreme = Math.max(Math.abs(low), Math.abs(high), Math.abs(projected), Math.abs(actual));
  if (!(Number.isFinite(extreme) && extreme > 0 && low <= high)) return null;
  const tail = unit === "" ? "" : ` ${unit}`;
  return (
    <RangeBar
      low={low}
      high={high}
      min={-extreme}
      max={extreme}
      marker={actual}
      label={tr(
        `margen de ${formatNumber(low, 2)} a ${formatNumber(high, 2)}${tail}; medido ${formatNumber(actual, 2)}${tail}`,
        `margin from ${formatNumber(low, 2)} to ${formatNumber(high, 2)}${tail}; measured ${formatNumber(actual, 2)}${tail}`,
      )}
    />
  );
}
