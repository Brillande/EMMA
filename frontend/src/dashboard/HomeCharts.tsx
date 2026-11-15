import { type CSSProperties, type ReactNode, useLayoutEffect, useMemo, useState } from "react";

import { useLook } from "../components/BoardOnly";
import { LevelBadge } from "../components/LevelBadge";
import { MarkOf } from "../components/Mark";
import type { Indicator } from "../lib/api";
import { formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { isLevel, levelStyle } from "../lib/levels";
import { MISSING_MARK } from "../lib/marks";
import { type Token, cssVar } from "../lib/palette";

/**
 * Los dibujos de datos del tablero «Inicio» (la maqueta de 2026-11-06) y, desde que cada sección es
 * un tablero (decisión del usuario, 2026-11-07), las piezas que las secciones montan con sus propios
 * datos: el anillo de proporción, la curva pequeña, la curva de 24 horas, los segmentos por elemento,
 * la barra de proporción, el tramo sobre una escala y la píldora de nivel con recuento. Son datos
 * dibujados, no pictogramas: como el calibre de la ecografía, viven fuera de `icons/` y la prueba de
 * pictogramas los exime por nombre de fichero; por eso toda pieza SVG nueva se escribe aquí y no en
 * el panel que la usa. Las cifras pasan por `formatNumber`; los colores los pone el CSS, y el único
 * con significado es el del nivel que trae el dato (`levelToken`). Cada pieza va con su texto: el
 * anillo y el tramo lo dicen ellos (`role="img"`); los segmentos y la barra son adorno (`aria-hidden`)
 * junto a la cifra o la lista que lo dice. Ninguna inventa una escala: quien la monta la trae del
 * backend o de la propia serie, y con una escala inválida la pieza lanza en vez de dibujar algo falso.
 */

export const DAY_SECONDS = 24 * 3600;

export interface Reading {
  at: number;
  value: number;
}

/** El anillo de proporción: cuántos de cuántos, y de qué («dominios», «medidas al día»). */
export function Ring({ done, total, label, children }: { done: number; total: number; label: string; children: ReactNode }) {
  const fraction = total === 0 ? 0 : done / total;
  const length = 2 * Math.PI * 42;
  return (
    <div className="ref-ring" role="img" aria-label={tr(`${formatNumber(done)} de ${formatNumber(total)} ${label}`, `${formatNumber(done)} of ${formatNumber(total)} ${label}`)}>
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle className="ref-ring-track" cx="50" cy="50" r="42" />
        <circle
          className="ref-ring-fill"
          cx="50"
          cy="50"
          r="42"
          strokeDasharray={`${fraction * length} ${length}`}
          transform="rotate(-90 50 50)"
        />
      </svg>
      <span className="ref-ring-label">{children}</span>
    </div>
  );
}

function pathOf(readings: readonly Reading[], until: number, windowMs: number, width: number, height: number): string {
  const from = until - windowMs;
  const shown = readings.filter((item) => item.at >= from && item.at <= until);
  if (shown.length < 2) return "";
  const values = shown.map((item) => item.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  return shown
    .map((item, index) => {
      const x = ((item.at - from) / (until - from)) * width;
      const y = height - ((item.value - low) / span) * (height - 4) - 2;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

/** La curva pequeña de una serie, sin ejes: acompaña a la cifra. Por defecto, las últimas 24 h. */
export function Sparkline({
  readings,
  until,
  windowMs = DAY_SECONDS * 1000,
}: {
  readings: readonly Reading[];
  until: number;
  windowMs?: number;
}) {
  const d = useMemo(() => pathOf(readings, until, windowMs, 160, 24), [readings, until, windowMs]);
  return (
    <svg className="ref-spark" viewBox="0 0 160 24" preserveAspectRatio="none" aria-hidden="true">
      {d !== "" && <path d={d} />}
    </svg>
  );
}

/**
 * El tamaño en píxeles con que se pinta un SVG, para que su `viewBox` lo copie (R5-2, 2026-11-09): la
 * curva de 24 h tenía un `viewBox` fijo de 360×190 que el tablero pinta a ~250×85, y sus cifras de eje
 * (11 unidades) salían a 5 px, ilegibles. Con el `viewBox` igual a la caja, una unidad es un píxel y
 * el eje se lee a su tamaño. Sin medida (pruebas, primer pintado) vale `fallback`.
 */
function usePixelBox<T extends Element>(fallback: { width: number; height: number }) {
  const [element, setElement] = useState<T | null>(null);
  const [box, setBox] = useState(fallback);
  useLayoutEffect(() => {
    if (element === null || typeof ResizeObserver === "undefined") return undefined;
    // La caja de maquetación (`clientWidth`), no la pintada: con el `zoom` de baja visión la pintada
    // es 1,25 veces mayor y el `viewBox` anularía el aumento (lo señaló la revisión de R5-2).
    const measure = () => {
      const width = element.clientWidth;
      const height = element.clientHeight;
      if (width > 0 && height > 0) {
        setBox((previous) => (previous.width === width && previous.height === height ? previous : { width, height }));
      }
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return [box, setElement] as const;
}

/** La caja de siempre de la curva de 24 h: la de `#clasica` y la de antes de medir. */
const FIXED_TREND_BOX = { width: 360, height: 190 } as const;

/** La curva de 24 h con sus ejes y los límites de referencia del catálogo. */
export function TrendSvg({
  readings,
  until,
  indicator,
}: {
  readings: readonly Reading[];
  until: number;
  indicator: Indicator | undefined;
}) {
  // A medida solo en la concha nueva; `#clasica` conserva su `viewBox` fijo y sus márgenes de siempre.
  const pixel = useLook() === "reference";
  const [measured, setSvg] = usePixelBox<SVGSVGElement>(FIXED_TREND_BOX);
  const { width, height } = pixel ? measured : FIXED_TREND_BOX;
  // El margen de las cifras del eje vertical, a la medida de la más ancha (≈ 7 px por carácter a 12 px).
  const left = pixel ? 34 : 30;
  const from = until - DAY_SECONDS * 1000;
  const shown = readings.filter((item) => item.at >= from && item.at <= until);
  if (shown.length < 2) return <MarkOf mark={MISSING_MARK}>{tr("Sin lecturas en las últimas 24 h", "No readings in the last 24 h")}</MarkOf>;
  const values = shown.map((item) => item.value);
  const refs = [indicator?.reference_low, indicator?.reference_high].filter(
    (value): value is number => typeof value === "number",
  );
  const low = Math.min(...values, ...refs);
  const high = Math.max(...values, ...refs);
  const span = high - low || 1;
  const bottom = height - (pixel ? 18 : 16);
  const y = (value: number) => bottom - ((value - low) / span) * (bottom - 8);
  const x = (at: number) => left + ((at - from) / (until - from)) * (width - left - 6);
  const d = shown.map((item, i) => `${i === 0 ? "M" : "L"}${x(item.at).toFixed(1)} ${y(item.value).toFixed(1)}`).join(" ");
  const first = shown[0];
  const last = shown[shown.length - 1];
  const area =
    first === undefined || last === undefined
      ? ""
      : `${d} L${x(last.at).toFixed(1)} ${bottom} L${x(first.at).toFixed(1)} ${bottom} Z`;
  // Cinco marcas con alto para ellas; en una caja baja, tres (a 12 px no caben cinco en 70 px).
  const ticks = (bottom >= 100 ? [0, 0.25, 0.5, 0.75, 1] : [0, 0.5, 1]).map((share) => low + share * span);
  const hours = [-24, -18, -12, -6, 0];
  return (
    <svg
      ref={pixel ? setSvg : undefined}
      className="ref-trend-svg"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={tr("Curva de las últimas 24 horas", "Curve of the last 24 hours")}
    >
      {ticks.map((value) => (
        <g key={value}>
          <line className="ref-grid-line" x1={left} x2={width - 6} y1={y(value)} y2={y(value)} />
          <text className="ref-axis" x="0" y={y(value) + (pixel ? 4 : 3)}>
            {formatNumber(value, indicator?.decimals ?? 0)}
          </text>
        </g>
      ))}
      {hours.map((hour) => {
        const at = until + hour * 3600 * 1000;
        return (
          <g key={hour}>
            <line className="ref-grid-line" x1={x(at)} x2={x(at)} y1={8} y2={bottom} />
            <text className="ref-axis" x={x(at)} y={height - 2} textAnchor={hour === 0 ? "end" : hour === -24 ? "start" : "middle"}>
              {hour === 0 ? tr("Ahora", "Now") : `${formatNumber(hour)} h`}
            </text>
          </g>
        );
      })}
      {refs.map((value) => (
        <line key={`ref-${value}`} className="ref-limit" x1={left} x2={width - 6} y1={y(value)} y2={y(value)} />
      ))}
      <path className="ref-trend-area" d={area} />
      <path className="ref-trend-line" d={d} />
    </svg>
  );
}

/** Token del nivel, o `null` si el backend diera uno que la interfaz no conoce (no se inventa). */
export function levelToken(level: string | undefined): Token | null {
  return level !== undefined && isLevel(level) ? levelStyle(level).color : null;
}

/**
 * Variable `--lvl` con el color real del nivel para teñir una píldora o una tarjeta: «text» para el
 * nominal y gris cuando no hay nivel conocido. («Inicio» tiñe el nominal de verde como adorno
 * declarado; las secciones, no.)
 */
export function levelTint(level: string | undefined): CSSProperties {
  return { "--lvl": `var(${cssVar(levelToken(level) ?? "gray")})` } as CSSProperties;
}

/**
 * Un segmento por elemento, con el tono que se le pasa (el color real de su nivel; `null`, gris):
 * adorno junto a la lista o la cifra que lo dice con palabras, nunca la única señal.
 */
export function Segments({ tones, titles }: { tones: readonly (Token | null)[]; titles?: readonly string[] }) {
  return (
    <span className="ref-segments" aria-hidden="true">
      {tones.map((tone, index) => (
        // eslint-disable-next-line react/no-array-index-key -- posición fija: un segmento por elemento.
        <span key={index} data-tone={tone ?? "gray"} title={titles?.[index]} />
      ))}
    </span>
  );
}

/**
 * Barra de proporción (0..1) junto a la cifra escrita, que es la que se lee; `concerning` solo si lo
 * dice el backend (amarillo). Fuera de 0..1 se recorta: la cifra escrita ya dice el valor.
 */
export function ImpactBar({ share, concerning = false }: { share: number; concerning?: boolean }) {
  if (!Number.isFinite(share)) throw new RangeError(`barra sin proporción: ${share}`);
  const width = Math.min(1, Math.max(0, share)) * 100;
  return (
    <span className="board-bar" aria-hidden="true">
      <span data-tone={concerning ? "yellow" : undefined} style={{ width: `${width.toFixed(1)}%` }} />
    </span>
  );
}

/**
 * Un tramo `low..high` sobre una escala `min..max`, con el valor real como marca si lo hay: el margen
 * de una proyección frente a lo medido, el intervalo de una pérdida estimada. Lanza con una escala o
 * un tramo inválidos, como `Meter`: no se dibuja algo falso. Dice sus cifras en `label`.
 */
export function RangeBar({
  low,
  high,
  min,
  max,
  marker,
  label,
}: {
  low: number;
  high: number;
  min: number;
  max: number;
  marker?: number;
  label: string;
}) {
  if (!(max > min) || !(low <= high) || !Number.isFinite(low) || !Number.isFinite(high)) {
    throw new RangeError(`tramo sin escala válida: [${low}, ${high}] en [${min}, ${max}]`);
  }
  const percent = (x: number) => ((Math.min(max, Math.max(min, x)) - min) / (max - min)) * 100;
  return (
    <span className="board-range" role="img" aria-label={label}>
      <span className="board-range-span" style={{ left: `${percent(low).toFixed(1)}%`, width: `${(percent(high) - percent(low)).toFixed(1)}%` }} />
      {marker !== undefined && Number.isFinite(marker) && (
        <span className="board-range-marker" style={{ left: `${percent(marker).toFixed(1)}%` }} />
      )}
    </span>
  );
}

/** Píldora de nivel con recuento: la insignia (palabra y forma del nivel) y la cifra, teñida con su color real. */
export function LevelPill({ level, count }: { level: string; count: number }) {
  return (
    <span className="ref-pill board-pill" style={levelTint(level)}>
      <LevelBadge level={level} />
      <span className="num">{formatNumber(count)}</span>
    </span>
  );
}

/** Las coordenadas de un valor dentro de `[pad, size - pad]`; una serie plana va al centro. */
export function scatterScale(value: number, min: number, max: number, size: number, pad: number): number {
  if (max === min) return size / 2;
  return pad + ((value - min) / (max - min)) * (size - 2 * pad);
}

/** Un punto de la dispersión: sus dos valores y el texto de su `title` (uno solo: React no admite más en `<title>`). */
export interface ScatterPoint {
  key: string;
  x: number;
  y: number;
  title: string;
}

const SCATTER_W = 180;
const SCATTER_H = 110;
const SCATTER_PAD = 10;

/**
 * La dispersión de dos series emparejadas («Correlación de variables», lote «reservas», 2026-11-14):
 * los puntos tal cual, en la escala de sus propios mínimos y máximos, sin recta ajustada (sería un
 * modelo que nadie validó). Lo dice ella (`role="img"`); el color de los puntos es adorno del CSS.
 */
export function ScatterPlot({ points, label }: { points: readonly ScatterPoint[]; label: string }) {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const bottom = SCATTER_H - SCATTER_PAD;
  return (
    <svg className="board-scatter" viewBox={`0 0 ${SCATTER_W} ${SCATTER_H}`} role="img" aria-label={label}>
      <line className="board-scatter-axis" x1={SCATTER_PAD} y1={bottom} x2={SCATTER_W - SCATTER_PAD} y2={bottom} />
      <line className="board-scatter-axis" x1={SCATTER_PAD} y1={SCATTER_PAD} x2={SCATTER_PAD} y2={bottom} />
      {points.map((point) => (
        <circle
          key={point.key}
          className="board-scatter-dot"
          cx={scatterScale(point.x, x0, x1, SCATTER_W, SCATTER_PAD)}
          cy={SCATTER_H - scatterScale(point.y, y0, y1, SCATTER_H, SCATTER_PAD)}
          r={2.6}
        >
          <title>{point.title}</title>
        </circle>
      ))}
    </svg>
  );
}

/** Una serie de `MultiTrend`: su clave, su nombre y sus lecturas. */
export interface TrendSeries {
  key: string;
  label: string;
  readings: readonly Reading[];
}

/** Los trazos con que se distinguen las series: por forma, no por color (un color diría un nivel). */
const TREND_DASHES = ["", "6 3", "2 3"] as const;

/**
 * Varias series en los mismos días (la «Tendencia (14 días)» de «Aislamiento»), cada una en su propio
 * tramo vertical, de su mínimo a su máximo: no comparten unidad, así que no hay eje de valores común
 * que inventar. El eje de tiempo sí es común. La leyenda dice qué trazo es cada serie.
 */
export function MultiTrend({ series, until, days }: { series: readonly TrendSeries[]; until: number; days: number }) {
  if (!(days > 0)) throw new RangeError(`tendencia sin días: ${days}`);
  const windowMs = days * DAY_SECONDS * 1000;
  const width = 300;
  const height = 60;
  const ticks = [...new Set([days, Math.round(days * 0.7), Math.round(days / 2), Math.round(days * 0.2), 0])];
  return (
    <figure className="ref-multitrend">
      <svg viewBox={`0 0 ${width} ${height + 14}`} role="img" aria-label={`${series.map((item) => item.label).join(", ")}: ${tr(`últimos ${formatNumber(days)} días`, `last ${formatNumber(days)} days`)}`}>
        {[0, 0.5, 1].map((share) => (
          <g key={share}>
            <line className="ref-multitrend-grid" x1="0" x2={width} y1={2 + share * (height - 4)} y2={2 + share * (height - 4)} />
            <text className="ref-multitrend-tick" x="1" y={share === 1 ? height - 4 : 2 + share * (height - 4) + 9}>
              {formatNumber((1 - share) * 100)}
            </text>
          </g>
        ))}
        {series.map((item, index) => {
          const d = pathOf(item.readings, until, windowMs, width, height);
          return d === "" ? null : <path key={item.key} data-series={item.key} className="ref-multitrend-line" d={d} strokeDasharray={TREND_DASHES[index % TREND_DASHES.length]} />;
        })}
        {ticks.map((tick) => (
          <text key={tick} className="ref-multitrend-tick" x={((days - tick) / days) * width} y={height + 12} textAnchor={tick === days ? "start" : tick === 0 ? "end" : "middle"}>
            {tick === 0 ? "hoy" : `${formatNumber(-tick)} d`}
          </text>
        ))}
      </svg>
      <figcaption>
        <ul className="ref-multitrend-legend">
          {series.map((item, index) => (
            <li key={item.key} data-series={item.key}>
              <svg viewBox="0 0 24 6" aria-hidden="true">
                <line x1="0" x2="24" y1="3" y2="3" strokeDasharray={TREND_DASHES[index % TREND_DASHES.length]} />
              </svg>
              <span>{item.label}</span>
              {item.readings.length < 2 && <MarkOf mark={MISSING_MARK}>{tr("sin serie", "no series")}</MarkOf>}
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}

/** Un eje del radar: su proporción sobre la escala que trae quien lo monta, o `null` sin dato. */
export interface RadarAxis {
  key: string;
  label: string;
  title: string;
  share: number | null;
  /** La cifra que se escribe bajo el rótulo; sin ella, la proporción en tanto por ciento. */
  value?: string;
}

/**
 * El radar de proporciones (la precisión de cada prueba de la batería Cognition sobre su escala
 * física). Un eje sin dato se queda en el centro y su rótulo lo dice con la marca de dato ausente.
 * Lanza con una proporción fuera de 0..1: la escala es de quien llama, y no se dibuja algo falso.
 */
export function Radar({ axes, label }: { axes: readonly RadarAxis[]; label: string }) {
  if (axes.length < 3) throw new RangeError(`radar con ${axes.length} ejes`);
  for (const axis of axes) {
    if (axis.share !== null && !(axis.share >= 0 && axis.share <= 1)) throw new RangeError(`radar fuera de escala: ${axis.key} ${axis.share}`);
  }
  const size = 180;
  const center = size / 2;
  const radius = 50;
  const at = (index: number, share: number) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * index) / axes.length;
    return [center + Math.cos(angle) * radius * share, center + Math.sin(angle) * radius * share] as const;
  };
  const ring = (share: number) => axes.map((_, index) => at(index, share).map((value) => value.toFixed(1)).join(",")).join(" ");
  const shape = axes.map((axis, index) => at(index, axis.share ?? 0).map((value) => value.toFixed(1)).join(",")).join(" ");
  const said = axes.map((axis) => `${axis.label} ${axis.share === null ? tr("sin dato", "no data") : `${formatNumber(axis.share * 100)} %`}`).join(", ");
  return (
    <svg className="ref-radar" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${said}`}>
      {[0.25, 0.5, 0.75, 1].map((share) => (
        <polygon key={share} className="ref-radar-ring" points={ring(share)} />
      ))}
      {axes.map((axis, index) => {
        const [x, y] = at(index, 1);
        return <line key={axis.key} className="ref-radar-spoke" x1={center} y1={center} x2={x} y2={y} />;
      })}
      <polygon className="ref-radar-shape" points={shape} />
      {axes.map((axis, index) => {
        const [x, y] = at(index, 1.38);
        return (
          <text key={axis.key} className="ref-radar-label" x={x} y={y - 4} textAnchor="middle" dominantBaseline="middle">
            <title>{axis.title}</title>
            {axis.label}
            <tspan className="ref-radar-value" x={x} dy="9">
              {axis.value ?? (axis.share === null ? "—" : formatNumber(axis.share * 100))}
            </tspan>
          </text>
        );
      })}
    </svg>
  );
}

/**
 * La curva de 24 h rellena por debajo («Ciclo últimas 24 h» de la pestaña «Entorno», 2026-11-15): la
 * misma serie que `Sparkline`, con el área hasta el eje y la marca del máximo. Sin eje de valores (la
 * cifra va al lado); el relleno es adorno, no un nivel. El cero del área es el mínimo de la ventana.
 */
export function AreaCurve({
  readings,
  until,
  windowMs = DAY_SECONDS * 1000,
}: {
  readings: readonly Reading[];
  until: number;
  windowMs?: number;
}) {
  const width = 200;
  const height = 60;
  const line = useMemo(() => pathOf(readings, until, windowMs, width, height), [readings, until, windowMs]);
  const peak = useMemo(() => {
    const from = until - windowMs;
    const shown = readings.filter((item) => item.at >= from && item.at <= until);
    if (shown.length < 2) return null;
    const top = shown.reduce((best, item) => (item.value > best.value ? item : best));
    return { x: ((top.at - from) / windowMs) * width, y: 2 };
  }, [readings, until, windowMs]);
  return (
    <svg className="ref-area" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      {line !== "" && (
        <>
          <path className="ref-area-fill" d={`${line} L${width} ${height} L0 ${height} Z`} />
          <path className="ref-area-line" d={line} />
        </>
      )}
      {peak !== null && <circle className="ref-area-peak" cx={peak.x} cy={peak.y + 2} r="3" />}
    </svg>
  );
}
