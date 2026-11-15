import { type ReactNode, useEffect, useMemo, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { useLook } from "../components/BoardOnly";
import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { type ChartLine, SeriesChart, type Span } from "../ground/TrendChart";
import {
  type CrewCompare,
  type CrewOverview,
  type HabitatParameter,
  type Indicator,
  api,
} from "../lib/api";
import { displayUnit, formatMet, formatNumber, missionElapsedSeconds } from "../lib/format";
import { tr } from "../lib/i18n";
import { LOADING_MARK, MISSING_MARK, UNAVAILABLE_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import {
  type CabinSeries,
  type CrewSeries,
  findingCounts,
  prepareComparison,
  suggestedIndicator,
  suggestedParameter,
} from "./comparison";
import { limitMark } from "./flow";
import { CABIN_AIR_PICTOGRAM, parameterPictogram } from "./pictograms";

/** Tramo que se compara: la ventana de la linea base movil del backend. */
const WINDOW_HOURS = 14 * 24;
const CHART_HEIGHT = 150;
/** Mismo cursor y mismo zoom en todas las graficas: el mismo instante se lee en vertical. */
const SYNC_KEY = "emma-crew-compare";
/** La linea base de cada tripulante es el cero de su grafica. */
const BASELINE: readonly ChartLine[] = [{ value: 0, tone: "textSecondary", dashed: true }];
const NO_SPANS: readonly Span[] = [];

/** Donde cae cada cosa en el eje de tiempo, en segundos de mision. */
interface Axis {
  receivedUntil: number;
  onboardUntil: number;
  windowSeconds: number;
}

/**
 * El mismo indicador en cada tripulante, sobre el mismo eje (especificacion del equipo §10:
 * "comparacion entre tripulantes para detectar posibles causas ambientales compartidas").
 *
 * La lista de niveles de al lado dice quien esta fuera de nominal; no deja ver si cambiaron a
 * la vez ni si coincidio con la cabina. Aqui va una grafica por persona, apiladas para que el
 * tiempo coincida en vertical, y el parametro de cabina debajo si se elige.
 *
 * Nadie se distingue por color: los de la paleta ya significan algo (tabla F.5-1), asi que
 * cada tripulante tiene su grafica y su nombre. El amarillo marca cuando el parametro de
 * cabina estuvo fuera de su limite normativo (precaucion, con el triangulo y su requisito); el
 * cian, lo que falta o esta en transito (anillo punteado; barra llena para el sombreado de la
 * grafica). El parametro de cabina lleva su pictograma junto al nombre (`pictograms.ts`). Que
 * la comparacion no se pudo cargar lo dice la marca de la peticion (`requestOutcome`: la cruz en
 * rojo si cayo, el triangulo en amarillo si el backend dijo que no, §5.34.14); el gris,
 * con el circulo tachado, que no hay con quien comparar (`UNAVAILABLE_MARK`).
 *
 * No redacta nada clinico: quien se desvia, por que y el resumen ("coincidencia temporal, no
 * causa") son texto del backend. Con `until`, lo que Tierra puede conocer.
 */
export function CrewComparison({
  missionStart,
  crew,
  parameters,
  refreshKey,
  until,
  onboardUntil,
}: {
  missionStart: string;
  crew: CrewOverview;
  parameters: HabitatParameter[];
  /** Cambia cuando cambia el estado: vuelve a pedir la comparacion. */
  refreshKey: string;
  /** Solo en Tierra: el corte del retardo. */
  until: Date | undefined;
  /** Solo en Tierra: por donde van a bordo, para marcar lo que esta en transito. */
  onboardUntil: Date | undefined;
}) {
  const board = useLook() === "reference";
  const [catalog, setCatalog] = useState<Indicator[]>([]);
  // Mientras nadie elige, se compara lo que el estado de la tripulacion señala primero.
  const [chosenKey, setChosenKey] = useState<string | null>(null);
  const [chosenParameter, setChosenParameter] = useState<string | null>(null);
  const [answer, setAnswer] = useState<{ request: string; compare: CrewCompare } | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .indicators()
      .then((payload) => {
        // Los descriptivos no se comparan: el estado no los juzga contra una linea base.
        if (!cancelled) setCatalog(payload.indicators.filter((item) => !item.descriptive_only));
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(requestOutcome(reason));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const several = crew.crew.length >= 2;
  const key =
    chosenKey ??
    suggestedIndicator(
      crew.crew,
      catalog.map((item) => item.key),
    );
  const parameter =
    chosenParameter ??
    suggestedParameter(
      crew.correlation.habitat_excursions,
      parameters.map((item) => item.key),
    ) ??
    "";
  // Lo que se pide. La respuesta se guarda con ello: una que no es de esta peticion no se pinta.
  const request = `${key ?? ""}|${parameter}|${until?.toISOString() ?? ""}`;

  useEffect(() => {
    if (!several || key === null) return;
    let cancelled = false;
    api
      .crewCompare(key, {
        parameter: parameter === "" ? undefined : parameter,
        until,
        hours: WINDOW_HOURS,
      })
      .then((compare) => {
        if (cancelled) return;
        setAnswer({ request, compare });
        setError(null);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setAnswer(null);
        setError(requestOutcome(reason));
      });
    return () => {
      cancelled = true;
    };
    // `key`, `parameter` y `until` van dentro de `request`.
  }, [several, request, refreshKey]);

  const compare = answer !== null && answer.request === request ? answer.compare : null;
  const prepared = useMemo(
    () => (compare === null ? null : prepareComparison(compare, missionStart)),
    [compare, missionStart],
  );

  if (!several) {
    return (
      <p className="compare">
        <MarkOf mark={UNAVAILABLE_MARK}>
          {tr("Comparación entre tripulantes no disponible: solo hay un tripulante con lecturas.", "Crew comparison unavailable: only one crew member has readings.")}
        </MarkOf>
      </p>
    );
  }

  const met = (at: Date) => missionElapsedSeconds(missionStart, at);
  const counts = findingCounts(crew.crew);
  const withFinding = catalog.filter((item) => counts.has(item.key));
  const rest = catalog.filter((item) => !counts.has(item.key));

  let axis: Axis | null = null;
  if (prepared !== null && prepared.referenceMet !== null) {
    // A bordo, el final del eje es la ultima lectura de la tripulacion; en Tierra, por donde
    // van a bordo, y lo recibido llega solo hasta el corte.
    const end = Math.max(
      prepared.referenceMet,
      met(onboardUntil ?? new Date(crew.reference_time)),
    );
    axis = {
      onboardUntil: end,
      receivedUntil: until === undefined ? end : Math.min(met(until), end),
      windowSeconds: Math.min(WINDOW_HOURS * 3_600, end),
    };
  }
  const spans = prepared?.cabin?.excursions ?? NO_SPANS;
  const windowLine =
    compare === null ? null : (
      <p className="secondary">
        {tr("Ventana comparada:", "Compared window:")} {compare.summary.window_basis}. {compare.summary.assumption}
      </p>
    );
  const undated =
    compare === null || compare.summary.undated_note === null ? null : (
      <p className="secondary">{compare.summary.undated_note}</p>
    );
  const help = (
    <span className="secondary">
      {tr(
        "Misma escala vertical y mismo tiempo en todos los tripulantes. Arrastre para ampliar; doble clic para volver.",
        "Same vertical scale and same time for every crew member. Drag to zoom; double-click to go back.",
      )}
    </span>
  );

  return (
    <div className="compare">
      <PanelTitle as="h3" concept="comparison">
        {tr("Comparación entre tripulantes", "Crew comparison")}
      </PanelTitle>
      <div className="compare-controls">
        <FieldLabel concept="indicator">
          <span className="secondary">{tr("Indicador", "Indicator")}</span>
          <select value={key ?? ""} onChange={(event) => setChosenKey(event.target.value)}>
            {withFinding.length > 0 && (
              <optgroup label={tr("Con hallazgo en la tripulación", "With a finding in the crew")}>
                {withFinding.map((item) => (
                  <option key={item.key} value={item.key}>
                    {tr(
                      `${item.display_es} · ${formatNumber(counts.get(item.key) ?? 0)} de ${formatNumber(crew.crew.length)}`,
                      `${item.display_es} · ${formatNumber(counts.get(item.key) ?? 0)} of ${formatNumber(crew.crew.length)}`,
                    )}
                  </option>
                ))}
              </optgroup>
            )}
            <optgroup label={withFinding.length > 0 ? tr("Resto del catálogo", "Rest of the catalog") : tr("Catálogo", "Catalog")}>
              {rest.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.display_es}
                </option>
              ))}
            </optgroup>
          </select>
        </FieldLabel>
        <FieldLabel pictogram={CABIN_AIR_PICTOGRAM}>
          <span className="secondary">{tr("Parámetro de cabina", "Cabin parameter")}</span>
          <select value={parameter} onChange={(event) => setChosenParameter(event.target.value)}>
            <option value="">{tr("Ninguno", "None")}</option>
            {parameters.map((item) => (
              <option key={item.key} value={item.key}>
                {item.display}
              </option>
            ))}
          </select>
        </FieldLabel>
      </div>

      {error !== null && (
        <p className="panel error">
          <MarkOf mark={error.mark}>{tr(`No se pudo cargar la comparación: ${error.text}`, `Could not load the comparison: ${error.text}`)}</MarkOf>
        </p>
      )}
      {error === null && compare === null && (
        <p className="secondary">
          <MarkOf mark={LOADING_MARK}>{tr("Cargando comparación…", "Loading comparison…")}</MarkOf>
        </p>
      )}

      {compare !== null && prepared !== null && (
        <>
          <div className="compare-summary">
            <span className="source-tag c-magenta">
              {tr("Resumen del sistema", "System summary")} · {compare.summary.label}
            </span>
            <p>{compare.summary.text}</p>
            {compare.summary.simultaneous_since !== null && (
              <p className="secondary">
                {tr("A la vez desde", "Simultaneous since")}{" "}
                <span className="num">
                  {formatMet(met(new Date(compare.summary.simultaneous_since)))}
                </span>{" "}
                ({compare.summary.onset_basis}).
              </p>
            )}
            {!board && undated}
            {!board && windowLine}
          </div>

          {/* Lote «muestra» (2026-11-08): las gráficas de cada tripulante, tras «Ver detalle»; el
              resumen del sistema con su magenta y la leyenda con sus marcas (lo que está en tránsito,
              la salida del límite), a la vista. Las gráficas miden su contenedor al abrirse
              (`ResizeObserver`). */}
          {/* Segunda ronda (2026-11-08): bajo la concha de la maqueta la nota de las desviaciones sin
              inicio, la ventana comparada y cómo se maneja la gráfica también van aquí; el resumen del
              sistema y la leyenda con sus marcas, a la vista. */}
          <BoardDetail label={tr("ventana comparada y las gráficas de cada tripulante", "compared window and each crew member's charts")}>
          {board && undated}
          {board && windowLine}
          {board && axis !== null && <p>{help}</p>}
          <p className="secondary">{tr("Cada serie:", "Each series:")} {compare.baseline_basis}.</p>

          <div className="compare-charts">
            {prepared.crew.map((member) => (
              <CrewRow
                key={member.subject}
                member={member}
                axisLabel={differenceLabel(displayUnit(compare.unit))}
                onsetBasis={compare.summary.onset_basis}
                range={prepared.range}
                spans={spans}
                axis={axis}
              />
            ))}
            {prepared.cabin !== null && <CabinRow cabin={prepared.cabin} axis={axis} />}
          </div>
          </BoardDetail>

          {axis !== null && (
            <p className="compare-legend">
              <span>{tr("— diferencia con su propia línea base", "— difference from their own baseline")}</span>
              <span className="secondary">{tr("- - su línea base", "- - their baseline")}</span>
              {prepared.cabin !== null && prepared.cabin.excursions.length > 0 && (
                // La barra es la muestra del sombreado, junto al parametro; la clase del limite
                // va con su marca junto a «fuera de», como en la tabla de atmosfera.
                <span>
                  <Mark pictogram="bar-filled" color="yellow">
                    {prepared.cabin.parameter.display}
                  </Mark>{" "}
                  <MarkOf mark={limitMark("health")}>
                    {tr(`fuera de ${prepared.cabin.excursionRequirements.join(" · ")}`, `outside ${prepared.cabin.excursionRequirements.join(" · ")}`)}
                  </MarkOf>
                </span>
              )}
              {axis.receivedUntil < axis.onboardUntil && (
                <Mark pictogram="bar-filled" color="cyan">
                  {tr("en tránsito: a bordo, aún no recibido", "in transit: on board, not yet received")}
                </Mark>
              )}
              {!board && help}
            </p>
          )}
        </>
      )}
    </div>
  );
}

function differenceLabel(unit: string): string {
  return unit === "" ? tr("diferencia con su base", "difference from their baseline") : tr(`diferencia con su base (${unit})`, `difference from their baseline (${unit})`);
}

/** Un tripulante: su grafica, o lo que el backend dice que falta. */
function CrewRow({
  member,
  axisLabel,
  onsetBasis,
  range,
  spans,
  axis,
}: {
  member: CrewSeries;
  axisLabel: string;
  onsetBasis: string;
  range: readonly [number, number] | null;
  spans: readonly Span[];
  axis: Axis | null;
}) {
  // Un dato que falta va en cian con el anillo punteado (tabla F.5-1); el resto, con un punto y
  // sin color de alerta: esta vista no asigna niveles, que ya estan en la lista de tripulacion.
  // Sin lecturas recientes es un dato caducado: lleva ademas la cursiva (`stale`, §5.33).
  const missing = member.state === "no_data" || member.state === "no_recent";
  const heading = (
    <>
      <Mark pictogram={uiPictogram("person")}>
        <strong>{member.subject}</strong>
      </Mark>{" "}
      {missing ? (
        <MarkOf mark={MISSING_MARK} stale={member.state === "no_recent"}>
          {member.stateText}
        </MarkOf>
      ) : (
        <Mark pictogram="dot-small" className={member.state === "deviating" ? undefined : "secondary"}>
          {member.stateText}
        </Mark>
      )}
    </>
  );
  const notes = (
    <>
      {member.drivers.map((driver) => (
        <span key={driver}>{driver}</span>
      ))}
      {member.onsetMet !== null && (
        <span className="secondary">
          {onsetBasis}: <span className="num">{formatMet(member.onsetMet)}</span>
        </span>
      )}
      {member.origins.map((origin) => (
        <ObservationTypeBadge
          key={`${origin.type}:${origin.context ?? ""}`}
          type={origin.type}
          context={origin.context}
        />
      ))}
      {member.setAsideText !== null && <span className="secondary">{member.setAsideText}</span>}
    </>
  );

  if (axis === null || range === null || member.points.length === 0) {
    return (
      <Unplotted heading={heading}>
        {member.baselineText !== null && <MarkOf mark={MISSING_MARK}>{member.baselineText}</MarkOf>}
        {notes}
      </Unplotted>
    );
  }
  return (
    <SeriesChart
      className="chart compare-chart"
      title={heading}
      axisLabel={axisLabel}
      seriesLabel={member.subject}
      points={member.points}
      lines={BASELINE}
      cautionSpans={spans}
      range={range}
      syncKey={SYNC_KEY}
      receivedUntil={axis.receivedUntil}
      onboardUntil={axis.onboardUntil}
      windowSeconds={axis.windowSeconds}
      height={CHART_HEIGHT}
    >
      {notes}
    </SeriesChart>
  );
}

/** El parametro de cabina, con su escala y sus limites normativos, en el mismo tiempo. */
function CabinRow({ cabin, axis }: { cabin: CabinSeries; axis: Axis | null }) {
  const unit = displayUnit(cabin.parameter.unit);
  const heading = (
    <>
      <Mark pictogram={parameterPictogram(cabin.parameter.key)}>
        <strong>{cabin.parameter.display}</strong>
      </Mark>{" "}
      <span className="secondary">({unit})</span>
    </>
  );
  if (axis === null || cabin.points.length === 0) {
    return (
      <Unplotted heading={heading}>
        {cabin.stateText !== null && <MarkOf mark={MISSING_MARK}>{cabin.stateText}</MarkOf>}
      </Unplotted>
    );
  }
  return (
    <SeriesChart
      className="chart compare-chart"
      title={heading}
      axisLabel={unit}
      seriesLabel={cabin.parameter.display}
      points={cabin.points}
      lines={cabin.limits}
      cautionSpans={cabin.excursions}
      syncKey={SYNC_KEY}
      receivedUntil={axis.receivedUntil}
      onboardUntil={axis.onboardUntil}
      windowSeconds={axis.windowSeconds}
      height={CHART_HEIGHT}
    >
      {cabin.limits.length > 0 && (
        // La raya es la muestra de la linea amarilla de la grafica; el triangulo, su clase.
        <MarkOf mark={limitMark("health")}>
          {tr(`— límite normativo ${cabin.limitRequirements.join(" · ")}`, `— normative limit ${cabin.limitRequirements.join(" · ")}`)}
        </MarkOf>
      )}
      {cabin.evidenceContexts.map((context) => (
        <ObservationTypeBadge key={context} type="measured" context={context} />
      ))}
    </SeriesChart>
  );
}

/** Una fila sin grafica: no hay nada que dibujar, y se dice que. */
function Unplotted({ heading, children }: { heading: ReactNode; children: ReactNode }) {
  return (
    <div className="chart compare-chart">
      <h3>{heading}</h3>
      <div className="legend">{children}</div>
    </div>
  );
}
