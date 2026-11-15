import { type ReactNode, useEffect, useMemo, useRef } from "react";
import uPlot from "uplot";

import { BoardOnly, useLook } from "../components/BoardOnly";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import type { Indicator } from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import { MISSING_MARK } from "../lib/marks";
import { palette } from "../lib/palette";
import {
  type EvidenceContext,
  type ObservationType,
  isLowConfidence,
  qualityStyle,
} from "../lib/provenance";
import { tr } from "../lib/i18n";

export interface SeriesOrigin {
  type: ObservationType;
  context: EvidenceContext | null;
}

/** La senal de baja confianza (`lib/provenance.ts`), una vez para todas las graficas. */
const LOW_CONFIDENCE = qualityStyle("low");

export interface Point {
  /** Segundos desde el origen de mision. */
  met: number;
  value: number;
  /** Confianza de la lectura segun el ledger; `null` si el recurso no la trae. */
  confidence?: number | null;
}

/** Umbral y palabra del backend para marcar las lecturas de baja confianza. */
export interface LowConfidenceMark {
  threshold: number;
  label: string;
}

/**
 * Una linea horizontal de la grafica. El color es un token con su significado de la tabla
 * F.5-1: rojo, limite de peligro; amarillo, limite normativo (precaucion); sin significado
 * de alerta, una referencia.
 */
export interface ChartLine {
  value: number;
  tone: "textSecondary" | "red" | "yellow";
  dashed: boolean;
}

/** Un tramo del eje temporal, en segundos de mision. */
export interface Span {
  from: number;
  to: number;
}

const DEFAULT_HEIGHT = 220;
/**
 * Alto de cada gráfica de Tierra en el tablero (muestra, 2026-11-08): con 220 px, las ocho gráficas en
 * dos columnas medían ~2450 px de página, más de dos vistas y media. A 170 px, en tres columnas,
 * caben en unas dos vistas como la «Tendencia (24 h)» de la muestra; el área de trazo sigue en unos
 * 115 px porque el eje de tiempo se compacta (`compact`).
 */
const BOARD_HEIGHT = 170;
const NO_SPANS: readonly Span[] = [];
const NO_POINTS: readonly Point[] = [];

/**
 * Una serie sobre el tiempo de mision tal y como la tiene Tierra.
 *
 * Lo que la hace distinta de una grafica de telemetria corriente: los datos
 * posteriores a `receivedUntil` **no se dibujan**. Estan a bordo, pero no han
 * llegado. Su hueco se marca en cian con la leyenda "en transito": tabla F.5-1,
 * *"Missing or stale data"*. Tierra ve el pasado, y la grafica lo dice.
 *
 * F.5.8: titulo encima (a), eje con etiqueta y unidad (c), leyenda (d), valores
 * en las marcas (e), limites como lineas (f) y zoom arrastrando, doble clic para
 * volver (g).
 *
 * Es la pieza comun: `TrendChart` la usa para un indicador, y la comparacion entre
 * tripulantes para una grafica por persona con el mismo eje y la misma escala. Por eso
 * no sabe de indicadores: recibe titulo, eje, lineas y leyenda. `points`, `lines`,
 * `cautionSpans`, `doubtful` y `range` deben venir memorizados, o la grafica se reconstruye
 * en cada pintado.
 *
 * Las lecturas de baja confianza (`doubtful`) se marcan sobre la linea con un triangulo
 * hueco amarillo (especificacion §10; F.5-1, *"off-nominal"*): el analisis no las usa como
 * referencia, y quien mira la grafica tiene que poder verlo. Cuales lo son lo dice quien
 * usa la grafica, con el umbral del backend.
 */
export function SeriesChart({
  title,
  axisLabel,
  seriesLabel,
  points,
  lines,
  cautionSpans = NO_SPANS,
  range,
  syncKey,
  receivedUntil,
  onboardUntil,
  windowSeconds,
  height = DEFAULT_HEIGHT,
  className = "panel chart",
  doubtful = NO_POINTS,
  summary,
  compact = false,
  children,
}: {
  /** Encima de la grafica (F.5.8 a). */
  title: ReactNode;
  /** Rotulo del eje vertical, con su unidad en forma de lectura (F.5.8 c). */
  axisLabel: string;
  seriesLabel: string;
  points: readonly Point[];
  lines: readonly ChartLine[];
  /** Tramos en precaucion (amarillo de F.5-1): se sombrean, y la leyenda dice que son. */
  cautionSpans?: readonly Span[];
  /** Escala vertical fijada desde fuera: varias graficas se comparan con la misma. */
  range?: readonly [number, number] | undefined;
  /** Las graficas con la misma clave comparten cursor y zoom: el mismo instante en todas. */
  syncKey?: string | undefined;
  receivedUntil: number;
  onboardUntil: number;
  windowSeconds: number;
  height?: number;
  className?: string;
  /** Lecturas de baja confianza, ya filtradas: triangulo hueco amarillo sobre cada una. */
  doubtful?: readonly Point[];
  /** Entre el titulo y el lienzo: las cifras de la ventana (tablero), si quien usa la grafica las da. */
  summary?: ReactNode;
  /**
   * Ejes compactos (tablero de Tierra): letra de 11 px y menos hueco reservado para las marcas y el
   * rótulo del eje, que a 170 px de alto se comían la mitad del lienzo. El rótulo sigue (F.5.8 c).
   */
  compact?: boolean;
  /** La leyenda (F.5.8 d). Sin ella, la pone quien agrupa varias graficas. */
  children?: ReactNode;
}) {
  const container = useRef<HTMLDivElement>(null);
  const fixedLow = range?.[0];
  const fixedHigh = range?.[1];

  useEffect(() => {
    const target = container.current;
    if (target === null) return;

    const start = onboardUntil - windowSeconds;
    const received = receivedInWindow(points, start, receivedUntil);
    const data: uPlot.AlignedData = [received.map((p) => p.met), received.map((p) => p.value)];

    const limits = lines.map((line) => ({
      value: line.value,
      color: palette[line.tone],
      dash: line.dashed ? [4, 4] : [],
    }));

    const values = [...received.map((p) => p.value), ...limits.map((l) => l.value)];
    const low = fixedLow ?? Math.min(...values);
    const high = fixedHigh ?? Math.max(...values);
    // Con la escala fijada no se añade margen: lo trae quien la calcula para todas.
    const pad = fixedLow !== undefined && fixedHigh !== undefined ? 0 : (high - low) * 0.08 || 1;

    const fontPx = compact ? 11 : 12;
    const axis = {
      stroke: palette.textSecondary,
      grid: { stroke: palette.line, width: 1 },
      ticks: { stroke: palette.line, width: 1, size: compact ? 6 : 10 },
      font: `${fontPx}px 'IBM Plex Mono', monospace`,
      labelFont: `${fontPx}px 'IBM Plex Sans', sans-serif`,
      ...(compact ? { labelSize: 18, labelGap: 0 } : {}),
    };

    const drawOverlays = (u: uPlot) => {
      const ctx = u.ctx;
      const { left, top, width, height } = u.bbox;
      ctx.save();
      ctx.beginPath();
      ctx.rect(left, top, width, height);
      ctx.clip();

      // Tramos en precaucion, debajo de todo lo demas: no tapan la serie ni los limites.
      ctx.fillStyle = `${palette.yellow}33`;
      for (const span of cautionSpans) {
        const from = u.valToPos(span.from, "x", true);
        const to = u.valToPos(span.to, "x", true);
        ctx.fillRect(from, top, Math.max(to - from, 2 * devicePixelRatio), height);
      }

      for (const limit of limits) {
        const y = u.valToPos(limit.value, "y", true);
        ctx.strokeStyle = limit.color;
        ctx.lineWidth = 1.5 * devicePixelRatio;
        ctx.setLineDash(limit.dash.map((d) => d * devicePixelRatio));
        ctx.beginPath();
        ctx.moveTo(left, y);
        ctx.lineTo(left + width, y);
        ctx.stroke();
      }

      // Lecturas de baja confianza: triangulo hueco amarillo sobre el punto.
      const side = 5 * devicePixelRatio;
      ctx.setLineDash([]);
      ctx.strokeStyle = palette.yellow;
      ctx.fillStyle = palette.surface;
      ctx.lineWidth = 1.5 * devicePixelRatio;
      for (const point of doubtful) {
        const x = u.valToPos(point.met, "x", true);
        const y = u.valToPos(point.value, "y", true);
        ctx.beginPath();
        ctx.moveTo(x, y - side);
        ctx.lineTo(x + side, y + side * 0.8);
        ctx.lineTo(x - side, y + side * 0.8);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }

      // Lo que esta a bordo y Tierra aun no tiene: franja cian rayada.
      const x0 = u.valToPos(receivedUntil, "x", true);
      const x1 = u.valToPos(onboardUntil, "x", true);
      if (x1 > x0) {
        ctx.setLineDash([]);
        ctx.fillStyle = `${palette.cyan}33`;
        ctx.fillRect(x0, top, Math.max(x1 - x0, 2 * devicePixelRatio), height);
        ctx.strokeStyle = palette.cyan;
        ctx.lineWidth = 2 * devicePixelRatio;
        ctx.beginPath();
        ctx.moveTo(x0, top);
        ctx.lineTo(x0, top + height);
        ctx.stroke();
      }
      ctx.restore();
    };

    const options: uPlot.Options = {
      width: target.clientWidth,
      height,
      legend: { show: false },
      cursor: {
        drag: { x: true, y: false },
        ...(syncKey === undefined ? {} : { sync: { key: syncKey } }),
      },
      scales: {
        x: { time: false, range: [start, onboardUntil] },
        y: { range: [low - pad, high + pad] },
      },
      axes: [
        {
          ...axis,
          label: tr("MET (día/hh:mm)", "MET (day/hh:mm)"),
          // Marcas en horas y dias enteros de mision, no en instantes arbitrarios.
          // Los 3 días están por la gráfica compacta (tablero): a ~240 px de trazo, siete días con
          // marcas cada 2 días quedaban a menos de `space` y uPlot saltaba a 7 días, una sola marca.
          incrs: [3_600, 3 * 3_600, 6 * 3_600, 12 * 3_600, 86_400, 2 * 86_400, 3 * 86_400, 7 * 86_400],
          values: (_u, ticks) => ticks.map(metTick),
          // Una marca «dd/hh:mm» mide unos 58 px en monoespaciada de 12 px: con el hueco de 50 px por
          // defecto de uPlot, a media anchura (la rejilla del tablero) se pisaban unas con otras.
          // Compacta (tablero, tres por fila con ~240 px de trazo): en 11 px la marca mide ~53 px, y
          // 66 px de hueco aún dejan aire entre dos marcas.
          space: compact ? 66 : 80,
          ...(compact ? { size: 26 } : {}),
        },
        {
          ...axis,
          label: axisLabel,
          size: compact ? 54 : 64,
          values: (_u, ticks) => ticks.map((tick) => formatNumber(tick, decimalsFor(ticks))),
        },
      ],
      series: [
        {},
        {
          label: seriesLabel,
          stroke: palette.text,
          width: 1.5,
          points: { show: false },
        },
      ],
      hooks: { draw: [drawOverlays] },
    };

    const plot = new uPlot(options, data, target);
    const resize = new ResizeObserver(() => {
      plot.setSize({ width: target.clientWidth, height });
    });
    resize.observe(target);
    return () => {
      resize.disconnect();
      plot.destroy();
    };
  }, [
    points,
    lines,
    cautionSpans,
    doubtful,
    fixedLow,
    fixedHigh,
    syncKey,
    receivedUntil,
    onboardUntil,
    windowSeconds,
    axisLabel,
    seriesLabel,
    height,
    compact,
  ]);

  return (
    <figure className={`series-chart ${className}`}>
      <h3>{title}</h3>
      {summary}
      <div ref={container} />
      {children !== undefined && <figcaption className="legend">{children}</figcaption>}
    </figure>
  );
}

/** La serie de un indicador del catalogo, con su rango de referencia y sus limites de peligro. */
export function TrendChart({
  indicator,
  points,
  receivedUntil,
  onboardUntil,
  windowSeconds,
  origins = [],
  lowConfidence = null,
  onboard = false,
}: {
  indicator: Indicator;
  points: Point[];
  /** Tipo y entorno de las lecturas de la serie (especificacion §10). */
  origins?: SeriesOrigin[];
  /** Umbral y palabra del backend para marcar las lecturas de baja confianza. */
  lowConfidence?: LowConfidenceMark | null;
  receivedUntil: number;
  onboardUntil: number;
  windowSeconds: number;
  /**
   * La grafica se ve a bordo (modo anatomico de la consola de tripulacion): no hay nada en
   * transito, y la leyenda no puede decir "recibido en Tierra" de lo que no ha salido de la nave.
   */
  onboard?: boolean;
}) {
  const unit = displayUnit(indicator.unit);
  // En Tierra y bajo la concha de la maqueta, la gráfica compacta del tablero; a bordo (anatomía) y
  // en la consola clásica, la de siempre.
  const board = useLook() === "reference" && !onboard;
  const threshold = lowConfidence?.threshold ?? null;
  // Solo lo recibido en Tierra y dentro de la ventana: lo mismo que se dibuja.
  const received = useMemo(
    () => receivedInWindow(points, onboardUntil - windowSeconds, receivedUntil),
    [points, onboardUntil, windowSeconds, receivedUntil],
  );
  const doubtful = useMemo(
    () =>
      threshold === null ? NO_POINTS : received.filter((p) => isLowConfidence(p.confidence, threshold)),
    [received, threshold],
  );
  const extent = useMemo(() => windowExtent(received), [received]);
  const { reference_low, reference_high, critical_low, critical_high } = indicator;
  const lines = useMemo(() => {
    const candidates: { value: number | null; tone: ChartLine["tone"]; dashed: boolean }[] = [
      { value: reference_low, tone: "textSecondary", dashed: true },
      { value: reference_high, tone: "textSecondary", dashed: true },
      // Un limite de peligro se traza en rojo: su cruce es un aviso (F.5-1).
      { value: critical_low, tone: "red", dashed: false },
      { value: critical_high, tone: "red", dashed: false },
    ];
    return candidates.filter((line): line is ChartLine => line.value !== null);
  }, [reference_low, reference_high, critical_low, critical_high]);

  return (
    <SeriesChart
      title={
        <>
          <IndicatorName indicatorKey={indicator.key} displayEs={indicator.display_es} />{" "}
          <span className="secondary">({unit})</span>
        </>
      }
      axisLabel={unit}
      seriesLabel={indicator.display_es}
      points={points}
      lines={lines}
      receivedUntil={receivedUntil}
      onboardUntil={onboardUntil}
      windowSeconds={windowSeconds}
      doubtful={doubtful}
      height={board ? BOARD_HEIGHT : DEFAULT_HEIGHT}
      compact={board}
      summary={
        // Solo en Tierra: a bordo (anatomia) la grafica es de otra seccion y conserva su forma.
        onboard ? undefined : (
          <BoardOnly>
            <WindowStats
              count={received.length}
              extent={extent}
              unit={unit}
              decimals={indicator.decimals}
              lowConfidence={lowConfidence}
              doubtful={doubtful.length}
            />
          </BoardOnly>
        )
      }
    >
      <span>
        {onboard ? tr("— lecturas a bordo", "— readings on board") : tr("— recibido en Tierra", "— received on Earth")}
      </span>
      <span className="secondary">{tr("- - rango de referencia", "- - reference range")}</span>
      {(critical_low !== null || critical_high !== null) && (
        <span className="c-red">{tr("— límite de peligro", "— danger limit")}</span>
      )}
      {!onboard && (
        <Mark pictogram="bar-vertical" color="cyan">
          {tr("en tránsito: a bordo, aún no recibido", "in transit: on board, not yet received")}
        </Mark>
      )}
      {lowConfidence !== null && doubtful.length > 0 && (
        <Mark pictogram={LOW_CONFIDENCE.pictogram} color={LOW_CONFIDENCE.color}>
          {lowConfidence.label} (<span className="num">{formatNumber(doubtful.length)}</span>)
        </Mark>
      )}
      {origins.map((origin) => (
        <ObservationTypeBadge
          key={`${origin.type}:${origin.context ?? ""}`}
          type={origin.type}
          context={origin.context}
        />
      ))}
    </SeriesChart>
  );
}

/** Las lecturas que Tierra ya tiene dentro de la ventana: las mismas que dibuja `SeriesChart`. */
export function receivedInWindow(points: readonly Point[], from: number, receivedUntil: number): Point[] {
  return points.filter((p) => p.met >= from && p.met <= receivedUntil);
}

/** Lo que la tira de cifras lee de la ventana; `null` cuando no hay ninguna lectura que leer. */
export interface WindowExtent {
  last: Point;
  low: Point;
  high: Point;
}

/**
 * La ultima lectura recibida (por tiempo de mision, no por orden de llegada) y las del minimo y el
 * maximo: la lectura entera, para que la tira marque la de baja confianza como la grafica. Un valor
 * que no es una cifra (`NaN`, infinito) no entra: uPlot lo salta, y aqui romperia el formato.
 */
export function windowExtent(received: readonly Point[]): WindowExtent | null {
  let extent: WindowExtent | null = null;
  for (const point of received) {
    if (!Number.isFinite(point.value)) continue;
    if (extent === null) {
      extent = { last: point, low: point, high: point };
      continue;
    }
    if (point.met >= extent.last.met) extent.last = point;
    if (point.value < extent.low.value) extent.low = point;
    if (point.value > extent.high.value) extent.high = point;
  }
  return extent;
}

/**
 * Las cifras de la ventana, como la tira de datos de «Inicio» (`.ref-stats`; tablero, 2026-11-07):
 * la ultima lectura recibida, cuantas hay, cuantas son de baja confianza y el minimo y el maximo.
 * Todo sale de lo mismo que se dibuja (lo recibido en Tierra dentro de la ventana), con los
 * decimales y la unidad del catalogo; no se calcula nada que la grafica no ensene ya. Sin lecturas,
 * la marca de dato ausente y nunca un cero. La baja confianza solo se cuenta con el umbral del
 * backend: sin el, la casilla no aparece; con lecturas dudosas lleva el triangulo amarillo de la
 * leyenda, y con ninguna, la cifra sola. La ultima lectura, el minimo o el maximo que sean de baja
 * confianza llevan ese mismo triangulo: en la grafica lo llevan, y la cifra no puede leerse limpia.
 * La edad de lo recibido la dice la franja cian de la grafica; la tira no la repite.
 */
function WindowStats({
  count,
  extent,
  unit,
  decimals,
  lowConfidence,
  doubtful,
}: {
  count: number;
  extent: WindowExtent | null;
  unit: string;
  decimals: number;
  lowConfidence: LowConfidenceMark | null;
  doubtful: number;
}) {
  const reading = (point: Point | undefined) => {
    if (point === undefined) return <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>;
    const figure = <span className="num">{formatNumber(point.value, decimals)}</span>;
    const doubtfulPoint = lowConfidence !== null && isLowConfidence(point.confidence, lowConfidence.threshold);
    return (
      <>
        {doubtfulPoint ? (
          <Mark pictogram={LOW_CONFIDENCE.pictogram} color={LOW_CONFIDENCE.color} title={lowConfidence.label}>
            {figure}
          </Mark>
        ) : (
          figure
        )}{" "}
        {unit}
      </>
    );
  };
  return (
    <dl className="ref-stats trend-stats" role="group" aria-label={tr("Cifras de la ventana", "Window figures")}>
      <div>
        <dt>{tr("Último recibido", "Last received")}</dt>
        <dd>{reading(extent?.last)}</dd>
      </div>
      <div>
        <dt>{tr("Lecturas", "Readings")}</dt>
        <dd>
          <span className="num">{formatNumber(count)}</span>
        </dd>
      </div>
      {lowConfidence !== null && (
        <div>
          <dt>{lowConfidence.label}</dt>
          <dd>
            {doubtful > 0 ? (
              <Mark pictogram={LOW_CONFIDENCE.pictogram} color={LOW_CONFIDENCE.color}>
                <span className="num">{formatNumber(doubtful)}</span>
              </Mark>
            ) : (
              <span className="num">{formatNumber(doubtful)}</span>
            )}
          </dd>
        </div>
      )}
      <div>
        <dt>{tr("Mínimo", "Minimum")}</dt>
        <dd>{reading(extent?.low)}</dd>
      </div>
      <div>
        <dt>{tr("Máximo", "Maximum")}</dt>
        <dd>{reading(extent?.high)}</dd>
      </div>
    </dl>
  );
}

function metTick(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const days = Math.floor(total / 86_400);
  const hours = Math.floor((total % 86_400) / 3_600);
  const minutes = Math.floor((total % 3_600) / 60);
  return `${days}/${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function decimalsFor(ticks: number[]): number {
  const step = ticks.length > 1 ? Math.abs((ticks[1] ?? 0) - (ticks[0] ?? 0)) : 1;
  return step >= 1 ? 0 : step >= 0.1 ? 1 : 2;
}
