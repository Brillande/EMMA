import { type CSSProperties, type ReactNode, useEffect, useState } from "react";

import { Command } from "../components/Command";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { Pictogram } from "../icons";
import type { PictogramName } from "../icons/registry";
import {
  type CognitionProtocol,
  type CognitionSessions,
  type FhirObservation,
  type FoodAcceptability,
  type HabitatState,
  type Indicator,
  type RiskEntity,
  api,
  risksApi,
  cognitionApi,
  nutritionApi,
} from "../lib/api";
import { displayUnit, formatAge, formatNumber, formatUtc } from "../lib/format";
import { language, tr } from "../lib/i18n";
import { LEVEL_ORDER, isLevel, levelStyle } from "../lib/levels";
import { MISSING_MARK, OK_MARK, UNAVAILABLE_MARK, UNKNOWN_PICTOGRAM, requestOutcome } from "../lib/marks";
import { type CorrelationReading, type CorrelationSearch, outlookApi } from "../lib/outlookApi";
import { cssVar } from "../lib/palette";
import { type Fetched, type HomeData, type HomeLinks, sectionLink } from "../dashboard/HomeBoard";
import { type GroundSummary, groundSummary } from "../planner/plannerApi";
import { ImpactBar, MultiTrend, Radar, type Reading, Ring, Sparkline, levelToken } from "../dashboard/HomeCharts";
import { capitalized } from "../dashboard/HazardCards";
import { CrewTriangleArt, LightBellArt } from "../dashboard/HomeArt";
import { NodesFit } from "../dashboard/NodesFit";
import "../dashboard/referenceDashboard.css";
import "./isolationBoard.css";

/**
 * La sección «Aislamiento»: la maqueta «Panel de Aislamiento y Salud Psicosocial ISS» (2026-11-14)
 * con el estilo de «Inicio» y «Radiación» (petición del usuario, 2026-11-14: «queremos otra pestaña
 * que se vea como esta»). Las mismas tarjetas (`ref-card`, `ref-frame`), la misma rejilla de 12
 * columnas y la ubicación de «Inicio» arriba; cada pieza lee lo que el backend ya sirve.
 *
 * Lo que NO se copió de la maqueta, a propósito (invariantes 5-7 de `CLAUDE.md`, y la decisión del
 * 2026-11-14 sobre «Radiación»: «los datos no queremos copiarlos»):
 * - Sin índice psicosocial compuesto (78/100), ni «moral», «relaciones», «motivación» o «cohesión»:
 *   EMMA no tiene esos indicadores ni una fórmula validada que los sume. En su sitio, los indicadores
 *   conductuales del catálogo (ánimo autoinformado, sueño, desfase circadiano, vigilancia PVT) con su
 *   última lectura, y cuántos se han medido en las últimas 24 h.
 * - Sin «impacto estimado» de cada factor: el cambio de la media de los últimos 7 días frente a los 7
 *   anteriores, calculado aquí sobre las lecturas y dicho así. No es una evaluación.
 * - El radar no es «estado emocional»: es la precisión de la última sesión de la batería Cognition
 *   de NASA, cada prueba sobre su escala física del catálogo (sin normas ni línea base, descriptiva).
 * - Interacciones de la tripulación y exposición a la luz: EMMA no las mide; se dice, en gris.
 * - Sin XP, niveles ni «recompensas»: las sesiones registradas son las que hay.
 * - Sin probabilidad de deterioro a 7 días: el nivel del dominio conductual del estado, con su
 *   trayectoria del backend. Recomendaciones y alertas, las del backend, tal cual.
 *
 * COLORES DE ADORNO: los acentos de tarjeta son los de «Inicio» (§2.5 de
 * `compliance/hmi-state-of-the-art.md`). Las curvas de la tendencia se distinguen por trazo, no por
 * color: un color de la tabla F.5-1 en una curva diría un nivel que no tiene.
 */

const BEHAVIORAL = "behavioral";
const DAY_MS = 24 * 3600 * 1000;
const TREND_DAYS = 14;

/** Los indicadores conductuales que la sección lee, en el orden de la maqueta. */
export const ISOLATION_KEYS = [
  "mood-valence",
  "sleep-duration",
  "sleep-efficiency",
  "circadian-shift",
  "pvt-mean-rt",
  "pvt-lapses",
] as const;
export type IsolationKey = (typeof ISOLATION_KEYS)[number];

/** Lo que la sección pide aparte del estado, una vez para todas sus piezas. */
export interface IsolationData {
  home: HomeData;
  series: Fetched<Record<IsolationKey, Reading[]>>;
  energy: Fetched<Reading[]>;
  protocol: Fetched<CognitionProtocol>;
  sessions: Fetched<CognitionSessions>;
  food: Fetched<FoodAcceptability>;
  /** La búsqueda automática de pares que tocan un indicador conductual (estadística, no IA). */
  correlations: Fetched<CorrelationSearch>;
  /** La entidad Riesgo conductual (`GET /api/risks`): sus contramedidas de la biblioteca. */
  risk: Fetched<RiskEntity | null>;
  /** El hábitat: la iluminancia de cabina (se muestra y no se evalúa). */
  habitat: Fetched<HabitatState>;
  /** El resumen del planificador que ve Tierra: mensajes, ocio y recordatorios de 7 días. */
  planner: Fetched<GroundSummary>;
  links: HomeLinks | undefined;
}

function fetched<T>(promise: Promise<T>, alive: () => boolean, set: (next: Fetched<T>) => void): void {
  promise
    .then((value) => {
      if (alive()) set({ state: "ready", value });
    })
    .catch((reason: unknown) => {
      if (alive()) set({ state: "failed", outcome: requestOutcome(reason) });
    });
}

export function readingsOf(observations: readonly FhirObservation[]): Reading[] {
  return observations
    .map((obs) => ({ at: Date.parse(obs.effectiveDateTime), value: obs.valueQuantity.value }))
    .filter((item) => Number.isFinite(item.at) && Number.isFinite(item.value))
    .sort((a, b) => a.at - b.at);
}

/** Las peticiones de la sección. Oculta, no se pide nada; al volver, se relee con el estado. */
export function useIsolationData(home: HomeData, active: boolean, links?: HomeLinks): IsolationData {
  const { status } = home;
  const [series, setSeries] = useState<Fetched<Record<IsolationKey, Reading[]>>>({ state: "loading" });
  const [energy, setEnergy] = useState<Fetched<Reading[]>>({ state: "loading" });
  const [protocol, setProtocol] = useState<Fetched<CognitionProtocol>>({ state: "loading" });
  const [sessions, setSessions] = useState<Fetched<CognitionSessions>>({ state: "loading" });
  const [food, setFood] = useState<Fetched<FoodAcceptability>>({ state: "loading" });
  const [correlations, setCorrelations] = useState<Fetched<CorrelationSearch>>({ state: "loading" });
  const [risk, setRisk] = useState<Fetched<RiskEntity | null>>({ state: "loading" });
  const [habitat, setHabitat] = useState<Fetched<HabitatState>>({ state: "loading" });
  const [planner, setPlanner] = useState<Fetched<GroundSummary>>({ state: "loading" });
  const until = status.data.reference_time;

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    fetched(cognitionApi.protocol(), () => current, setProtocol);
    fetched(
      risksApi.get().then((body) => body.risks.find((item) => item.risk_id === BEHAVIORAL) ?? null),
      () => current,
      setRisk,
    );
    return () => {
      current = false;
    };
  }, [active]);

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    const alive = () => current;
    fetched(
      Promise.all(
        ISOLATION_KEYS.map((key) =>
          api.observations(key, 2000, status.subject, until).then((body) => [key, readingsOf(body.observations)] as const),
        ),
      ).then((pairs) => Object.fromEntries(pairs) as Record<IsolationKey, Reading[]>),
      alive,
      setSeries,
    );
    fetched(
      api.observations("energy-intake-daily", 200, status.subject, until).then((body) => readingsOf(body.observations)),
      alive,
      setEnergy,
    );
    fetched(cognitionApi.sessions(status.subject, 1), alive, setSessions);
    fetched(nutritionApi.foodAcceptability(status.subject), alive, setFood);
    fetched(api.habitat(new Date(until)), alive, setHabitat);
    fetched(groundSummary(until, 7), alive, setPlanner);
    fetched(outlookApi.search(status.subject, until, BEHAVIORAL), alive, setCorrelations);
    return () => {
      current = false;
    };
  }, [active, status.subject, until]);

  return { home, series, energy, protocol, sessions, food, correlations, risk, habitat, planner, links };
}

type Piece = { iso: IsolationData };

function Pending({ item }: { item: Fetched<unknown> }) {
  if (item.state === "loading") return <Loading />;
  if (item.state === "failed") return <Unavailable outcome={item.outcome} />;
  return null;
}

function readingsFor(iso: IsolationData, key: IsolationKey): Reading[] {
  return iso.series.state === "ready" ? iso.series.value[key] : [];
}

function indicatorOf(iso: IsolationData, key: string): Indicator | undefined {
  return iso.home.catalog.get(key);
}

/**
 * Rótulos cortos de la maqueta para las tarjetas estrechas. Solo rótulo: el nombre entero del
 * catálogo va en `title` (`fullName`) y lo lee el lector de pantalla.
 */
/** Pictograma de cada indicador en las listas, como los iconos por fila de la maqueta. */
const ICON: Record<string, PictogramName> = {
  "mood-valence": "face-neutral",
  "sleep-duration": "moon-z",
  "sleep-efficiency": "bed",
  "circadian-shift": "clock",
  "pvt-mean-rt": "stopwatch",
  "pvt-lapses": "hourglass",
  "energy-intake-daily": "fork-knife",
};

const SHORT: Record<string, string> = {
  "mood-valence": tr("Ánimo (autoinforme)", "Mood (self-report)"),
  "sleep-duration": tr("Duración del sueño", "Sleep duration"),
  "sleep-efficiency": tr("Eficiencia del sueño", "Sleep efficiency"),
  "circadian-shift": tr("Desfase circadiano", "Circadian shift"),
  "pvt-mean-rt": tr("PVT: reacción media", "PVT: mean reaction"),
  "pvt-lapses": tr("PVT: fallos", "PVT: lapses"),
  "energy-intake-daily": tr("Energía ingerida", "Energy intake"),
};

/** El nombre de la tripulación del indicador (del backend), o la clave si el catálogo no ha llegado. */
function fullName(iso: IsolationData, key: string): string {
  return capitalized(indicatorOf(iso, key)?.display_es ?? key);
}

function nameOf(iso: IsolationData, key: string): string {
  return SHORT[key] ?? fullName(iso, key);
}

/** La media de cada día (por días enteros hasta la referencia): la curva de 14 días no es ruido. */
export function dailyMeans(readings: readonly Reading[], reference: number, days: number): Reading[] {
  return Array.from({ length: days }, (_, index) => {
    const end = reference - (days - 1 - index) * DAY_MS;
    const mean = windowMean(readings, end, 1);
    return mean === null ? null : { at: end - DAY_MS / 2, value: mean };
  }).filter((item): item is Reading => item !== null);
}

/** La cifra con los decimales y la unidad del catálogo. */
function valueText(iso: IsolationData, key: string, value: number): string {
  const indicator = indicatorOf(iso, key);
  const unit = indicator === undefined ? "" : displayUnit(indicator.unit);
  const number = formatNumber(value, indicator?.decimals ?? 1);
  return unit === "" ? number : `${number} ${unit}`;
}

/** La media de las lecturas en `(end - days, end]`, o `null` si no hay ninguna. */
export function windowMean(readings: readonly Reading[], end: number, days: number): number | null {
  const from = end - days * DAY_MS;
  const values = readings.filter((item) => item.at > from && item.at <= end).map((item) => item.value);
  return values.length === 0 ? null : values.reduce((a, b) => a + b, 0) / values.length;
}

/**
 * El cambio relativo de la media de 7 días frente a los 7 anteriores, en tanto por uno. `null` si
 * falta una de las dos ventanas o la anterior es cero (un cociente sin sentido no se enseña).
 */
export function weekChange(readings: readonly Reading[], reference: number): number | null {
  const now = windowMean(readings, reference, 7);
  const before = windowMean(readings, reference - 7 * DAY_MS, 7);
  if (now === null || before === null || before === 0) return null;
  return (now - before) / Math.abs(before);
}

/** Si un cambio va hacia el lado que el catálogo marca como preocupante (por su rango de referencia). */
function concerningChange(indicator: Indicator | undefined, change: number): boolean {
  if (indicator === undefined) return false;
  const low = indicator.reference_low !== null;
  const high = indicator.reference_high !== null;
  if (low && !high) return change < 0;
  if (high && !low) return change > 0;
  return false;
}

function signed(fraction: number): string {
  const text = formatNumber(fraction * 100, 1);
  return `${fraction > 0 ? "+" : ""}${text} %`;
}

function behavioralLevel(iso: IsolationData): string | null {
  return iso.home.status.domains[BEHAVIORAL]?.level ?? null;
}

function tint(level: string | null) {
  const token = levelToken(level ?? undefined);
  const shown = token === null ? "gray" : token === "text" ? "green" : token;
  return { "--lvl": `var(${cssVar(shown)})` } as CSSProperties;
}

// ---------------------------------------------------------------- fila 1: cabecera

/** La franja de la maqueta: título, ubicación, última actualización y tripulante. */
export function IsoHeader({ iso }: Piece) {
  const { status } = iso.home;
  return (
    <section data-ui="iso-header" className="ref-card iso-header" aria-label={tr("Aislamiento y salud psicosocial", "Isolation and psychosocial health")}>
      <h2 className="iso-title">
        <Pictogram name="ridge-isolation" />
        <span>
          {tr("Aislamiento y salud psicosocial", "Isolation and psychosocial health")}
          <span className="secondary"> · {capitalized(status.mission.profile?.display ?? tr("misión", "mission"))}</span>
        </span>
      </h2>
      <p className="iso-updated">
        <span className="ref-live" aria-hidden="true" /> {tr("Datos a", "Data as of")} <span className="num">{formatUtc(new Date(iso.home.reference))}</span>
        <LastReading iso={iso} />
      </p>
      <p className="iso-subject">
        <Pictogram name="person" />
        <span>
          {tr("Tripulante:", "Crew member:")} <strong>{status.subject}</strong>
        </span>
      </p>
    </section>
  );
}

/** «Última lectura conductual hace N min», frente a la hora de los datos. */
function LastReading({ iso }: Piece) {
  if (iso.series.state !== "ready") return null;
  const last = Math.max(...ISOLATION_KEYS.map((key) => readingsFor(iso, key).at(-1)?.at ?? -Infinity));
  if (!Number.isFinite(last)) return null;
  return (
    <span className="secondary">
      {" "}
      · {language() === "en" ? null : "hace "}
      <span className="num">{formatAge(Math.max(0, (iso.home.reference - last) / 60000))}</span>
      {language() === "en" ? " ago" : null}
    </span>
  );
}

/**
 * Los dos cambios semanales mayores que van hacia el lado que el catálogo marca como preocupante
 * («Moral en descenso (-8 % / 7 días)» en la maqueta). Descriptivo: lo calcula la interfaz sobre las
 * lecturas y lo dice; el nivel lo decide el motor, no esto.
 */
function WeekMoves({ iso }: Piece) {
  if (iso.series.state !== "ready") return null;
  const moves = ISOLATION_KEYS.map((key) => ({ key, change: weekChange(readingsFor(iso, key), iso.home.reference) }))
    .filter(
      (item): item is { key: IsolationKey; change: number } =>
        item.change !== null && concerningChange(indicatorOf(iso, item.key), item.change),
    )
    .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
    .slice(0, 2);
  if (moves.length === 0) {
    return (
      <p className="iso-moves secondary">
        <MarkOf mark={OK_MARK}>{tr("Sin cambios semanales hacia el lado preocupante.", "No weekly changes toward the concerning side.")}</MarkOf>
      </p>
    );
  }
  return (
    <ul className="iso-moves">
      {moves.map((item) => (
        <li key={item.key} data-series={item.key} title={tr("Media de 7 días frente a los 7 anteriores. Descriptivo: no evalúa.", "7-day mean against the previous 7. Descriptive: it does not evaluate.")}>
          <Pictogram name={item.change > 0 ? "arrow-up" : "arrow-down"} />
          <span>
            <strong>{nameOf(iso, item.key)}</strong> {item.change > 0 ? tr("en ascenso", "rising") : tr("en descenso", "falling")}{" "}
            <span className="num">({signed(item.change)} / {tr("7 días", "7 days")})</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Flecha de un cambio: sube o baja (pictograma, no glifo de texto). */
function Arrow({ change }: { change: number }) {
  if (change === 0) return null;
  return <Pictogram name={change > 0 ? "arrow-up" : "arrow-down"} className="iso-arrow" />;
}

/** El acceso a «Peligros y alertas», como la flecha de «Alertas y acciones» de la maqueta. */
function HazardsLink({ iso }: Piece) {
  const link = sectionLink(iso.links, "hazards");
  if (link === null) return null;
  return (
    <div className="ref-quick-links iso-go">
      <Command concept="detail" type="button" onClick={link.open} aria-label={tr(`Abrir ${link.name}: alertas y acciones`, `Open ${link.name}: alerts and actions`)}>
        <span>{tr("Alertas y acciones", "Alerts and actions")}</span>
      </Command>
    </div>
  );
}

/** Días seguidos con alguna lectura, contando hacia atrás desde el día de la referencia. */
export function streakDays(readings: readonly Reading[], reference: number): number {
  const days = new Set(readings.filter((item) => item.at <= reference).map((item) => Math.floor(item.at / DAY_MS)));
  let day = Math.floor(reference / DAY_MS);
  let count = 0;
  while (days.has(day)) {
    count += 1;
    day -= 1;
  }
  return count;
}

// ---------------------------------------------------------------- fila 2

/** En lugar del «índice psicosocial»: cuántos indicadores conductuales hay hoy y su última lectura. */
export function IsoIndicators({ iso }: Piece) {
  const { reference } = iso.home;
  const fresh = ISOLATION_KEYS.filter((key) => readingsFor(iso, key).some((item) => item.at > reference - DAY_MS && item.at <= reference));
  const shown: IsolationKey[] = ["mood-valence", "sleep-duration", "circadian-shift", "pvt-mean-rt"];
  return (
    <section data-ui="iso-indicators" className="ref-card iso-indicators" aria-label={tr("Indicadores psicosociales", "Psychosocial indicators")}>
      <PanelTitle concept="domains" className="ref-h">
        {tr("Indicadores conductuales", "Behavioral indicators")}
      </PanelTitle>
      {iso.series.state !== "ready" ? (
        <Pending item={iso.series} />
      ) : (
        <div className="iso-index">
          <Ring done={fresh.length} total={ISOLATION_KEYS.length} label={tr("indicadores medidos en 24 h", "indicators measured in 24 h")}>
            <strong className="num">{formatNumber(fresh.length)}</strong>
            <small>/{formatNumber(ISOLATION_KEYS.length)}</small>
          </Ring>
          <ul className="iso-latest">
            {shown.map((key) => {
              const last = readingsFor(iso, key).at(-1);
              return (
                <li key={key} data-series={key}>
                  <Pictogram name={ICON[key] ?? "dot-small"} />
                  <span className="ref-clamp" title={fullName(iso, key)}>
                    {nameOf(iso, key)}
                  </span>
                  {last === undefined ? (
                    <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
                  ) : (
                    <strong className="num">{valueText(iso, key, last.value)}</strong>
                  )}
                </li>
              );
            })}
          </ul>
          <small className="secondary iso-ring-caption">{tr("con lectura en 24 h", "with a reading in 24 h")}</small>
        </div>
      )}
    </section>
  );
}

/** Las curvas de 14 días: ánimo, sueño y vigilancia, cada una en su propio tramo (sin eje común). */
export function IsoTrend({ iso }: Piece) {
  const keys: IsolationKey[] = ["mood-valence", "sleep-duration", "pvt-mean-rt"];
  return (
    <section data-ui="iso-trend" className="ref-card iso-trend" aria-label={tr(`Tendencia de ${formatNumber(TREND_DAYS)} días`, `${formatNumber(TREND_DAYS)}-day trend`)}>
      <PanelTitle concept="trends" className="ref-h">
        {tr(`Tendencia (${formatNumber(TREND_DAYS)} días)`, `Trend (${formatNumber(TREND_DAYS)} days)`)}
      </PanelTitle>
      {iso.series.state !== "ready" ? (
        <Pending item={iso.series} />
      ) : (
        <>
          <MultiTrend
            series={keys.map((key) => ({ key, label: nameOf(iso, key), readings: dailyMeans(readingsFor(iso, key), iso.home.reference, TREND_DAYS) }))}
            until={iso.home.reference}
            days={TREND_DAYS}
          />
          <p className="secondary iso-note" title={tr("Medias diarias; cada curva en su propio tramo, de su mínimo a su máximo. El eje vertical es el % de ese tramo, no una puntuación.", "Daily means; each curve on its own span, from its minimum to its maximum. The vertical axis is the % of that span, not a score.")}>{tr("Eje: % del tramo de cada curva (medias diarias).", "Axis: % of each curve's span (daily means).")}</p>
        </>
      )}
    </section>
  );
}

/** En lugar del «impacto estimado»: el cambio de la media semanal de cada indicador. */
export function IsoFactors({ iso }: Piece) {
  const { reference } = iso.home;
  const rows = ISOLATION_KEYS.map((key) => ({ key, change: weekChange(readingsFor(iso, key), reference) }));
  const top = Math.max(0.01, ...rows.map((row) => Math.abs(row.change ?? 0)));
  return (
    <section data-ui="iso-factors" className="ref-card iso-factors" aria-label={tr("Factores de aislamiento", "Isolation factors")}>
      <PanelTitle concept="change" className="ref-h">
        {tr("Factores (cambio semanal)", "Factors (weekly change)")}
      </PanelTitle>
      {iso.series.state !== "ready" ? (
        <Pending item={iso.series} />
      ) : (
        <>
          <ul className="iso-bars">
            {rows.map((row) => (
              <li key={row.key} data-series={row.key}>
                <Pictogram name={ICON[row.key] ?? "dot-small"} />
                <span className="ref-clamp" title={fullName(iso, row.key)}>
                  {nameOf(iso, row.key)}
                </span>
                {row.change === null ? (
                  <MarkOf mark={MISSING_MARK}>{tr("sin 2 semanas", "under 2 weeks")}</MarkOf>
                ) : (
                  <>
                    <ImpactBar share={Math.abs(row.change) / top} concerning={concerningChange(indicatorOf(iso, row.key), row.change)} />
                    <span className="num">{signed(row.change)}</span>
                  </>
                )}
              </li>
            ))}
          </ul>
          <p className="secondary iso-note" title={tr("Media de los últimos 7 días frente a los 7 anteriores. Descriptivo: no evalúa.", "Mean of the last 7 days against the previous 7. Descriptive: it does not evaluate.")}>{tr("Media de los últimos 7 días frente a los 7 anteriores. Descriptivo: no evalúa.", "Mean of the last 7 days against the previous 7. Descriptive: it does not evaluate.")}</p>
        </>
      )}
    </section>
  );
}

/** El estado global: el nivel del dominio conductual y lo que dice el backend de él. */
export function IsoGlobal({ iso }: Piece) {
  const level = behavioralLevel(iso);
  const risk = iso.home.status.domains[BEHAVIORAL];
  const style = level !== null && isLevel(level) ? levelStyle(level) : null;
  return (
    <section data-ui="iso-global" className="ref-card iso-global" aria-label={tr("Estado global del aislamiento", "Overall isolation status")}>
      <PanelTitle concept="state" className="ref-h">
        {tr("Estado global (aislamiento)", "Overall status (isolation)")}
      </PanelTitle>
      {level === null || risk === undefined ? (
        <MarkOf mark={UNAVAILABLE_MARK}>{tr("el estado no trae el dominio conductual", "the status does not include the behavioral domain")}</MarkOf>
      ) : (
        <>
          <div className="ref-level-now iso-hero" style={tint(level)}>
            <span className="ref-hero-icon" aria-hidden="true">
              <Pictogram name={style?.pictogram ?? UNKNOWN_PICTOGRAM} />
            </span>
            <span>
              <strong>{style?.label ?? level}</strong>
              {risk.trajectory !== null && risk.trajectory !== undefined && <small className="ref-clamp-2">{risk.trajectory.display}</small>}
            </span>
          </div>
          <WeekMoves iso={iso} />
          <ul className="iso-global-facts">
            <li>
              <Pictogram name="bell" />
              <span>
                {tr("Alertas conductuales activas", "Active behavioral alerts")}{" "}
                <strong className="num">{formatNumber(iso.home.status.alerts.filter((item) => item.domain === BEHAVIORAL).length)}</strong>
              </span>
            </li>
            <li>
              <Pictogram name="list-check" />
              <span>
                {tr("Recomendaciones conductuales", "Behavioral recommendations")}{" "}
                <strong className="num">{formatNumber(iso.home.status.recommendations.filter((item) => item.domain === BEHAVIORAL).length)}</strong>
              </span>
            </li>
            <li>
              <Pictogram name="circle-i" />
              <span>
                {tr("Indicadores con lectura en 24 h", "Indicators with a reading in 24 h")}{" "}
                <strong className="num">
                  {formatNumber(
                    ISOLATION_KEYS.filter((key) =>
                      readingsFor(iso, key).some((item) => item.at > iso.home.reference - DAY_MS && item.at <= iso.home.reference),
                    ).length,
                  )}
                  /{formatNumber(ISOLATION_KEYS.length)}
                </strong>
              </span>
            </li>
          </ul>
          {/* Los motivos del motor, si los hay; sin ninguno, ya lo dice la línea de cambios de la semana. */}
          {risk.drivers.length > 0 && (
            <ul className="iso-drivers">
              {risk.drivers.slice(0, 3).map((driver) => (
                <li key={driver} className="ref-clamp-2" title={driver}>
                  {driver}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- fila 3

/** Rótulos de un eje del radar: una palabra. */
const AXIS: Record<IsolationKey, string> = {
  "mood-valence": tr("Ánimo", "Mood"),
  "sleep-duration": tr("Sueño", "Sleep"),
  "sleep-efficiency": tr("Eficiencia", "Efficiency"),
  "circadian-shift": tr("Circadiano", "Circadian"),
  "pvt-mean-rt": "PVT",
  "pvt-lapses": tr("Fallos PVT", "PVT lapses"),
};

/**
 * Dónde cae la última lectura dentro del tramo de los últimos 14 días del propio tripulante (0 = su
 * mínimo, 1 = su máximo). `null` con menos de dos lecturas o un tramo plano. Descriptivo: no dice si
 * está bien o mal, solo dónde está frente a sí mismo.
 */
export function rangePosition(readings: readonly Reading[], reference: number, days: number): number | null {
  const shown = readings.filter((item) => item.at > reference - days * DAY_MS && item.at <= reference);
  const last = shown.at(-1);
  if (last === undefined || shown.length < 2) return null;
  const values = shown.map((item) => item.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  return high === low ? null : (last.value - low) / (high - low);
}

/** El estado emocional y conductual: cada indicador, su última lectura en su tramo de 14 días. */
export function IsoMood({ iso }: Piece) {
  const { reference } = iso.home;
  const axes = ISOLATION_KEYS.map((key) => {
    const last = readingsFor(iso, key).at(-1);
    return {
      key,
      label: AXIS[key],
      title: tr(
        `${fullName(iso, key)}: última lectura dentro de su tramo de ${formatNumber(TREND_DAYS)} días`,
        `${fullName(iso, key)}: latest reading within its ${formatNumber(TREND_DAYS)}-day span`,
      ),
      share: rangePosition(readingsFor(iso, key), reference, TREND_DAYS),
      value: last === undefined ? "—" : formatNumber(last.value, indicatorOf(iso, key)?.decimals ?? 1),
    };
  });
  return (
    <section data-ui="iso-mood" className="ref-card iso-mood" aria-label={tr("Estado emocional y conductual", "Emotional and behavioral status")}>
      <PanelTitle concept="diary" className="ref-h">
        <span title={tr("Cada eje: la última lectura dentro de su tramo de 14 días (centro, su mínimo; borde, su máximo). Frente a sí mismo, no frente a una norma.", "Each axis: the latest reading within its 14-day span (center, its minimum; edge, its maximum). Against the crew member's own readings, not against a norm.")}>
          {tr("Estado emocional y conductual", "Emotional and behavioral status")}
        </span>
      </PanelTitle>
      {iso.series.state !== "ready" ? (
        <Pending item={iso.series} />
      ) : (
        <Radar axes={axes} label={tr(`Última lectura de cada indicador dentro de su tramo de ${formatNumber(TREND_DAYS)} días`, `Latest reading of each indicator within its ${formatNumber(TREND_DAYS)}-day span`)} />
      )}
    </section>
  );
}


/** Sueño y ritmo circadiano: medias de 7 días y las noches de 14 días en barras. */
export function IsoSleep({ iso }: Piece) {
  const { reference } = iso.home;
  const rows: IsolationKey[] = ["sleep-duration", "sleep-efficiency", "circadian-shift"];
  return (
    <section data-ui="iso-sleep" className="ref-card iso-sleep" aria-label={tr("Sueño y ritmo circadiano", "Sleep and circadian rhythm")}>
      <PanelTitle concept="routines" className="ref-h">
        {tr("Sueño y ritmo circadiano", "Sleep and circadian rhythm")}
      </PanelTitle>
      {iso.series.state !== "ready" ? (
        <Pending item={iso.series} />
      ) : (
        <>
          <dl className="iso-pairs">
            {rows.map((key) => {
              const mean = windowMean(readingsFor(iso, key), reference, 7);
              const change = weekChange(readingsFor(iso, key), reference);
              return (
                <div key={key}>
                  <dt className="ref-clamp">{nameOf(iso, key)} (7 d)</dt>
                  <dd className="num">
                    {mean === null ? <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf> : valueText(iso, key, mean)}
                    {change !== null && (
                      <small className="secondary">
                        {" "}
                        <Arrow change={change} />
                        {signed(change)}
                      </small>
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
          <DayBars readings={readingsFor(iso, "sleep-duration")} reference={reference} days={TREND_DAYS} label={tr("Horas de sueño por día", "Hours of sleep per day")} />
        </>
      )}
    </section>
  );
}

/** Interacciones: lo que da el planificador (mensajes, ocio, recordatorios); el triángulo es adorno. */
export function IsoInteractions({ iso }: Piece) {
  const summary = iso.planner.state === "ready" ? iso.planner.value : null;
  const days = summary?.members.flatMap((member) => member.days) ?? [];
  const sum = (pick: (day: (typeof days)[number]) => number) => days.reduce((total, day) => total + pick(day), 0);
  const rows: { label: string; icon: PictogramName; value: string }[] = [
    { label: tr("Mensajes (7 días)", "Messages (7 days)"), icon: "bubble-lines", value: formatNumber(sum((day) => day.messages)) },
    { label: tr("Eventos de ocio", "Leisure events"), icon: "calendar-day", value: formatNumber(sum((day) => day.leisure_events)) },
    { label: tr("Horas de ocio", "Leisure hours"), icon: "clock", value: formatNumber(sum((day) => day.leisure_hours), 1) },
    {
      label: tr("Recordatorios", "Reminders"),
      icon: "bell",
      value: formatNumber(summary?.members.reduce((total, member) => total + member.reminders, 0) ?? 0),
    },
  ];
  return (
    <section data-ui="iso-interactions" className="ref-card iso-interactions" aria-label={tr("Interacciones de la tripulación", "Crew interactions")}>
      <PanelTitle concept="person" className="ref-h">
        {tr("Interacciones de la tripulación", "Crew interactions")}
      </PanelTitle>
      <div className="iso-side-art">
        <div>
          {iso.planner.state !== "ready" ? (
            <Pending item={iso.planner} />
          ) : summary !== null && summary.members.length === 0 ? (
            <p>
              <MarkOf mark={MISSING_MARK}>{tr("sin registros del planificador esta semana", "no planner records this week")}</MarkOf>
            </p>
          ) : (
            <ul className="iso-latest iso-rows">
              {rows.map((row) => (
                <li key={row.label}>
                  <Pictogram name={row.icon} />
                  <span>{row.label}</span>
                  <strong className="num">{row.value}</strong>
                </li>
              ))}
            </ul>
          )}
          <p
            className="secondary iso-note"
            title={tr(
              `EMMA no mide la calidad de las interacciones ni la cohesión del equipo. ${summary?.leisure_rule ?? ""}`,
              `EMMA does not measure the quality of interactions or team cohesion. ${summary?.leisure_rule ?? ""}`,
            )}
          >
            {tr("Del planificador; la cohesión no se mide.", "From the planner; cohesion is not measured.")}
          </p>
        </div>
        <CrewTriangleArt />
      </div>
    </section>
  );
}

/** Luz: la iluminancia de CABINA del hábitat (no la del ojo, que EMMA no mide), sin evaluar. */
export function IsoLight({ iso }: Piece) {
  const { reference } = iso.home;
  const readings =
    iso.habitat.state === "ready"
      ? iso.habitat.value.readings
          .filter((item) => item.parameter === "cabin-light")
          .map((item) => ({ at: Date.parse(item.effective), value: item.value }))
          .filter((item) => Number.isFinite(item.at))
          .sort((a, b) => a.at - b.at)
      : [];
  const day = readings.filter((item) => item.at > reference - DAY_MS && item.at <= reference);
  const last = readings.at(-1);
  const mean = windowMean(readings, reference, 1);
  const top = day.length === 0 ? null : Math.max(...day.map((item) => item.value));
  const lux = displayUnit("lx");
  return (
    <section data-ui="iso-light" className="ref-card iso-light" aria-label={tr("Exposición a la luz", "Light exposure")}>
      <PanelTitle concept="lightTime" className="ref-h">
        {tr("Exposición a la luz", "Light exposure")}
      </PanelTitle>
      {iso.habitat.state !== "ready" ? (
        <Pending item={iso.habitat} />
      ) : last === undefined ? (
        <MarkOf mark={MISSING_MARK}>{tr("sin lecturas de luz de cabina", "no cabin light readings")}</MarkOf>
      ) : (
        <>
          <dl className="iso-pairs">
            <div>
              <dt>{tr("Cabina, última", "Cabin, latest")}</dt>
              <dd className="num">
                {formatNumber(last.value)} {lux}
              </dd>
            </div>
            <div>
              <dt>{tr("Media 24 h", "24 h mean")}</dt>
              <dd className="num">{mean === null ? "—" : `${formatNumber(mean)} ${lux}`}</dd>
            </div>
            <div>
              <dt>{tr("Máxima 24 h", "24 h maximum")}</dt>
              <dd className="num">{top === null ? "—" : `${formatNumber(top)} ${lux}`}</dd>
            </div>
          </dl>
          <div className="iso-light-curve">
            <LightBellArt />
            <Sparkline readings={readings} until={reference} />
          </div>
        </>
      )}
      <p
        className="secondary iso-note"
        title={tr("Iluminancia de cabina del hábitat: se muestra y no se evalúa. EMMA no mide la luz que llega a los ojos de nadie.", "Habitat cabin illuminance: shown, not evaluated. EMMA does not measure the light reaching anyone's eyes.")}
      >
        {tr("Luz de cabina, no la del ojo; no se evalúa.", "Cabin light, not light at the eye; not evaluated.")}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------- fila 4

/** Nutrición: la ingesta diaria y la aceptabilidad de la comida, con las frases del backend. */
export function IsoNutrition({ iso }: Piece) {
  const key = "energy-intake-daily";
  const readings = iso.energy.state === "ready" ? iso.energy.value : [];
  const mean = windowMean(readings, iso.home.reference, 7);
  const food = iso.food.state === "ready" ? iso.food.value : null;
  return (
    <section data-ui="iso-nutrition" className="ref-card iso-nutrition" aria-label={tr("Nutrición y menú", "Nutrition and menu")}>
      <PanelTitle concept="ratings" className="ref-h">
        {tr("Nutrición y menú", "Nutrition and menu")}
      </PanelTitle>
      {iso.energy.state !== "ready" ? (
        <Pending item={iso.energy} />
      ) : (
        <div className="iso-nutri">
        <Ring done={dayCount(readings, iso.home.reference)} total={7} label={tr("días con ingesta registrada esta semana", "days with intake recorded this week")}>
          <strong className="num">{formatNumber(dayCount(readings, iso.home.reference))}</strong>
          <small>/{formatNumber(7)}</small>
        </Ring>
        <dl className="iso-pairs">
          <div>
            <dt className="ref-clamp">{nameOf(iso, key)} (7 d)</dt>
            <dd className="num">{mean === null ? <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf> : valueText(iso, key, mean)}</dd>
          </div>
          <div>
            <dt>{tr("Platos valorados", "Dishes rated")}</dt>
            <dd className="num">{food === null ? "—" : formatNumber(food.rated)}</dd>
          </div>
          {food !== null && food.below !== null && (
            <div>
              <dt>{tr("Por debajo del criterio", "Below the criterion")}</dt>
              <dd className="num">{formatNumber(food.below)}</dd>
            </div>
          )}
        </dl>
        </div>
      )}
      {food !== null ? (
        <p className="secondary iso-note ref-clamp-2" title={food.statement}>
          {food.statement}
        </p>
      ) : (
        iso.food.state !== "ready" && <Pending item={iso.food} />
      )}
    </section>
  );
}

/** Las pruebas de la batería Cognition, en su orden, con si la última sesión las trae. */
export function IsoTests({ iso }: Piece) {
  const pvtLast = readingsFor(iso, "pvt-mean-rt").at(-1);
  return (
    <section data-ui="iso-tests" className="ref-card iso-tests" aria-label={tr("Pruebas cognitivas", "Cognitive tests")}>
      <PanelTitle concept="pvt" className="ref-h">
        {tr("Pruebas cognitivas · batería Cognition", "Cognitive tests · Cognition battery")}
        {iso.sessions.state === "ready" && iso.sessions.value.sessions[0] !== undefined && (
          <small className="secondary"> · {tr("última sesión", "latest session")} {iso.sessions.value.sessions[0].effective.slice(0, 10)}</small>
        )}
      </PanelTitle>
      {iso.protocol.state !== "ready" || iso.sessions.state !== "ready" ? (
        <Pending item={iso.protocol.state !== "ready" ? iso.protocol : iso.sessions} />
      ) : (
        <ul className="iso-test-grid">
          {iso.protocol.value.tests.map((test) => {
            const session = iso.sessions.state === "ready" ? iso.sessions.value.sessions[0] : undefined;
            const done = test.recorded_here
              ? session !== undefined && test.fields.some((field) => session.values.some((item) => item.key === field.key))
              : pvtLast !== undefined;
            const accuracyKey = test.fields.find((field) => field.measure === "accuracy")?.key;
            const accuracy = session?.values.find((item) => item.key === accuracyKey)?.value_text ?? null;
            return (
              <li key={test.abbrev} title={test.measures?.quote ?? test.measures_note ?? test.name} data-done={done ? "" : undefined}>
                <Pictogram name={TEST_ICON[test.sigla] ?? "square-outline"} />
                <span className="iso-test-name">
                  <span className="ref-clamp-2">{test.name}</span>
                  <small className="secondary">{test.sigla}</small>
                </span>
                <span className="iso-test-mark">
                  {done ? (
                    <MarkOf mark={OK_MARK}>{accuracy ?? tr("registrada", "recorded")}</MarkOf>
                  ) : (
                    <MarkOf mark={MISSING_MARK}>{tr("sin registro", "no record")}</MarkOf>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** Pictograma de cada prueba de la batería (adorno de rótulo, como los iconos de la maqueta). */
const TEST_ICON: Record<string, PictogramName> = {
  MPT: "figure-dot",
  VOLT: "cube",
  F2B: "grid-four",
  AM: "shape-diamond",
  LOT: "ruler",
  ERT: "face-neutral",
  MRT: "table-grid",
  DSST: "hash",
  BART: "balance",
  PVT: "stopwatch",
};

/** Cuántos días distintos tienen alguna lectura en los últimos 7. */
function dayCount(readings: readonly Reading[], reference: number): number {
  return new Set(readings.filter((item) => item.at > reference - 7 * DAY_MS && item.at <= reference).map((item) => Math.floor(item.at / DAY_MS))).size;
}

/** En lugar de «progreso y recompensas»: constancia de registros, sin puntos ni niveles. */
export function IsoProgress({ iso }: Piece) {
  const { reference } = iso.home;
  const days = (key: IsolationKey) =>
    new Set(readingsFor(iso, key).filter((item) => item.at > reference - 7 * DAY_MS).map((item) => Math.floor(item.at / DAY_MS))).size;
  const pvtDays = days("pvt-mean-rt");
  const streak = streakDays(readingsFor(iso, "pvt-mean-rt"), reference);
  const moodDays = days("mood-valence");
  return (
    <section data-ui="iso-progress" className="ref-card iso-progress" aria-label={tr("Constancia de registros", "Recording consistency")}>
      <PanelTitle concept="routines" className="ref-h">
        {tr("Constancia (7 días)", "Consistency (7 days)")}
      </PanelTitle>
      {iso.series.state !== "ready" ? (
        <Pending item={iso.series} />
      ) : (
        <>
          <p className="iso-progress-head">
            <span>{tr("Días con PVT", "Days with PVT")}</span>
            <strong className="num">
              {formatNumber(pvtDays)}/{formatNumber(7)}
            </strong>
          </p>
          <ImpactBar share={pvtDays / 7} />
          <ul className="iso-checklist">
            <li>
              <Pictogram name={streak > 0 ? "check" : "dash"} />
              <span>
                {tr("Racha de PVT:", "PVT streak:")} <span className="num">{formatNumber(streak)}</span>{" "}
                {streak === 1 ? tr("día seguidos", "day in a row") : tr("días seguidos", "days in a row")}
              </span>
            </li>
            <li>
              <Pictogram name={moodDays === 7 ? "check" : "dash"} />
              <span>
                {tr("Autoinforme de ánimo:", "Mood self-report:")} <span className="num">{formatNumber(moodDays)}/{formatNumber(7)}</span> {tr("días", "days")}
              </span>
            </li>
            <li>
              <Pictogram name={iso.sessions.state === "ready" && iso.sessions.value.count > 0 ? "check" : "dash"} />
              <span>
                {tr("Sesiones Cognition:", "Cognition sessions:")} <span className="num">{iso.sessions.state === "ready" ? formatNumber(iso.sessions.value.count) : "—"}</span>
              </span>
            </li>
          </ul>
        </>
      )}
      <p className="secondary iso-note" title={tr("Solo recuentos: EMMA no da puntos ni niveles.", "Counts only: EMMA gives no points or levels.")}>{tr("Solo recuentos: EMMA no da puntos ni niveles.", "Counts only: EMMA gives no points or levels.")}</p>
    </section>
  );
}

// ---------------------------------------------------------------- fila 5

/**
 * «Correlaciones Clave (IA)» de la maqueta, como lo eligió el usuario (2026-11-15: «búsqueda
 * automática + explicación IA»). Las cifras son de la búsqueda del backend (r de Pearson, con n e
 * intervalo en el `title`); la IA solo redacta, a petición, una lectura de esas cifras: un borrador
 * de Clase C que se enseña tal cual y marcado, y que nada del motor lee (invariante 6).
 */
export function IsoCorrelations({ iso }: Piece) {
  const [ask, setAsk] = useState<{ state: "idle" } | { state: "loading" } | Fetched<CorrelationReading>>({ state: "idle" });
  const search = iso.correlations.state === "ready" ? iso.correlations.value : null;
  const pairs = search?.pairs ?? [];
  // Otra referencia, otra búsqueda: la lectura de antes ya no es de estas cifras.
  const reference = iso.home.status.data.reference_time;
  useEffect(() => setAsk({ state: "idle" }), [reference, iso.home.status.subject]);
  const requestReading = () => {
    setAsk({ state: "loading" });
    outlookApi
      .reading(iso.home.status.subject, reference, BEHAVIORAL)
      .then((value) => setAsk({ state: "ready", value }))
      .catch((reason: unknown) => setAsk({ state: "failed", outcome: requestOutcome(reason) }));
  };
  return (
    <section data-ui="iso-correlations" className="ref-card iso-correlations" aria-label={tr("Correlaciones clave", "Key correlations")}>
      <PanelTitle concept="compare" className="ref-h">
        {tr("Correlaciones clave", "Key correlations")}
        <small className="secondary" title={search?.pairs_basis}>
          {" "}
          ·{" "}
          {search === null
            ? tr("búsqueda automática", "automatic search")
            : tr(`búsqueda automática de ${formatNumber(search.tested)} pares`, `automatic search of ${formatNumber(search.tested)} pairs`)}
        </small>
      </PanelTitle>
      {iso.correlations.state !== "ready" ? (
        <Pending item={iso.correlations} />
      ) : pairs.length === 0 ? (
        <MarkOf mark={MISSING_MARK}>{tr("ningún par con días suficientes", "no pair with enough days")}</MarkOf>
      ) : (
        <ul className="iso-corr">
          {pairs.slice(0, 3).map((pair) => (
            <li key={`${pair.x.key}|${pair.y.key}`} title={`${pair.text}${pair.simulated ? ` ${search?.simulated_text ?? ""}` : ""}`} data-series={pair.x.key}>
              <span className="iso-dot" aria-hidden="true" />
              <span>
                {tr(`${nameOf(iso, pair.x.key)} y ${nameOf(iso, pair.y.key).toLowerCase()}`, `${nameOf(iso, pair.x.key)} and ${nameOf(iso, pair.y.key).toLowerCase()}`)}
              </span>
              <span className="num">(r = {formatNumber(pair.r ?? 0, 2)})</span>
            </li>
          ))}
        </ul>
      )}
      <div className="iso-ai">
        {ask.state === "ready" ? (
          ask.value.text !== null ? (
            <p className="iso-ai-text" title={tr(`${ask.value.label} Modelo: ${ask.value.model}.`, `${ask.value.label} Model: ${ask.value.model}.`)}>
              <span className="iso-ai-chip">{tr("IA · borrador", "AI · draft")}</span> {ask.value.text}
            </p>
          ) : ask.value.available ? (
            <p className="secondary" title={ask.value.blocked.join(" · ") || (ask.value.note ?? "")}>
              <MarkOf mark={UNAVAILABLE_MARK}>{tr("La lectura IA no pasó las barreras y no se enseña.", "The AI reading did not pass the safeguards and is not shown.")}</MarkOf>
            </p>
          ) : (
            <p className="secondary" title={ask.value.note ?? ""}>
              <MarkOf mark={UNAVAILABLE_MARK}>{tr("Lectura IA no disponible: sin modelo local.", "AI reading unavailable: no local model.")}</MarkOf>
            </p>
          )
        ) : ask.state === "failed" ? (
          <Unavailable outcome={ask.outcome} />
        ) : (
          <Command
            concept="detail"
            type="button"
            disabled={ask.state === "loading" || pairs.length === 0}
            onClick={requestReading}
            title={tr("El modelo local lee estas cifras y redacta un borrador; no calcula nada ni entra en el análisis.", "The local model reads these figures and writes a draft; it computes nothing and does not enter the analysis.")}
          >
            <span>{ask.state === "loading" ? tr("La IA está leyendo…", "The AI is reading…") : tr("Pedir lectura a la IA", "Ask the AI for a reading")}</span>
          </Command>
        )}
      </div>
    </section>
  );
}

/** El riesgo: el nivel del dominio conductual marcado sobre la escala de niveles del motor. */
export function IsoRisk({ iso }: Piece) {
  const risk = iso.home.status.domains[BEHAVIORAL];
  const level = risk?.level ?? null;
  const style = level !== null && isLevel(level) ? levelStyle(level) : null;
  const at = level !== null && isLevel(level) ? LEVEL_ORDER.indexOf(level) : -1;
  return (
    <section data-ui="iso-risk" className="ref-card iso-risk" aria-label={tr("Riesgo del dominio conductual", "Behavioral domain risk")}>
      <PanelTitle concept="risks" className="ref-h">
        {tr("Riesgo (dominio conductual)", "Risk (behavioral domain)")}
      </PanelTitle>
      {risk === undefined ? (
        <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin dominio conductual", "no behavioral domain")}</MarkOf>
      ) : (
        <>
          <div className="iso-risk-pill" style={tint(level)}>
            <Pictogram name={style?.pictogram ?? UNKNOWN_PICTOGRAM} />
            <strong>{style?.label ?? level}</strong>
            <span className="num">({formatNumber(risk.score, 2)})</span>
          </div>
          <div className="iso-risk-scale" role="img" aria-label={tr(`Escala de niveles; marcado: ${style?.label ?? level}`, `Level scale; marked: ${style?.label ?? level}`)}>
            <span className="iso-risk-marker" aria-hidden="true" style={{ left: `${(((at + 0.5) / LEVEL_ORDER.length) * 100).toFixed(1)}%` }}>
              <Pictogram name="triangle-down-filled" />
            </span>
            <ol aria-hidden="true">
              {LEVEL_ORDER.map((item) => (
                <li key={item} style={tint(item)} title={levelStyle(item).label} />
              ))}
            </ol>
          </div>
        </>
      )}
      <p className="secondary iso-note" title={tr("Puntuación del motor de riesgo de EMMA, no una probabilidad.", "Score from EMMA's risk engine, not a probability.")}>{tr("Puntuación del motor de riesgo de EMMA, no una probabilidad.", "Score from EMMA's risk engine, not a probability.")}</p>
    </section>
  );
}

/** Las recomendaciones del backend; sin ninguna, las contramedidas conductuales de la biblioteca. */
export function IsoRecommendations({ iso }: Piece) {
  const items = iso.home.status.recommendations.filter((item) => item.domain === BEHAVIORAL);
  const library = iso.risk.state === "ready" && iso.risk.value !== null ? iso.risk.value.countermeasures.items : [];
  return (
    <section data-ui="iso-recommendations" className="ref-card iso-recommendations" aria-label={tr("Recomendaciones", "Recommendations")}>
      <PanelTitle concept="recommendations" className="ref-h">
        {items.length > 0 ? tr("Recomendaciones (EMMA)", "Recommendations (EMMA)") : tr("Contramedidas (biblioteca)", "Countermeasures (library)")}
      </PanelTitle>
      {items.length > 0 ? (
        <ul className="iso-checks">
          {items.slice(0, 4).map((item) => (
            <li key={`${item.action}-${item.urgency}`} title={item.rationale}>
              <Pictogram name="check" />
              <span className="ref-clamp">{item.action}</span>
            </li>
          ))}
        </ul>
      ) : iso.risk.state !== "ready" ? (
        <Pending item={iso.risk} />
      ) : library.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={OK_MARK}>{tr("Sin recomendaciones conductuales: nada requiere acción.", "No behavioral recommendations: nothing requires action.")}</MarkOf>
        </p>
      ) : (
        <ul className="iso-checks">
          {library.slice(0, 4).map((item) => (
            <li key={item.id} title={[item.action, item.basis_display, item.trigger_display].filter(Boolean).join(" · ")}>
              <Pictogram name="bandage" />
              <span className="ref-clamp">{item.action}</span>
            </li>
          ))}
        </ul>
      )}
      {items.length === 0 && library.length > 0 && (
        <p
          className="secondary iso-note"
          title={tr("Ninguna recomendación conductual activa: estas son las contramedidas de la biblioteca para el riesgo conductual, no órdenes.", "No active behavioral recommendation: these are the library's countermeasures for the behavioral risk, not orders.")}
        >
          {tr("Ninguna activa: las de la biblioteca para este riesgo.", "None active: the library's for this risk.")}
        </p>
      )}
    </section>
  );
}

/** Las alertas activas del dominio conductual, con su nivel. */
export function IsoAlerts({ iso }: Piece) {
  const alerts = iso.home.status.alerts.filter((item) => item.domain === BEHAVIORAL);
  const worst = alerts[0]?.level ?? null;
  return (
    <section data-ui="iso-alerts" className="ref-card iso-alerts" aria-label={tr("Alertas y acciones", "Alerts and actions")} style={tint(worst)}>
      <PanelTitle concept="alerts" className="ref-h">
        {tr("Alertas (conductual)", "Alerts (behavioral)")}
      </PanelTitle>
      {alerts.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={OK_MARK}>{tr("Sin alertas conductuales activas.", "No active behavioral alerts.")}</MarkOf>
        </p>
      ) : (
        <ul className="iso-alert-list">
          {alerts.slice(0, 3).map((alert) => {
            const style = isLevel(alert.level) ? levelStyle(alert.level) : null;
            return (
              <li key={alert.id} style={tint(alert.level)}>
                <Pictogram name={style?.pictogram ?? UNKNOWN_PICTOGRAM} />
                <span className="ref-clamp-2">
                  <strong>{style?.label ?? alert.level}</strong>
                  {alert.detail !== undefined && alert.detail.changed.length > 0 && (
                    <span className="secondary"> · {alert.detail.changed.map((item) => item.display_es).join(", ")}</span>
                  )}
                  {alert.acknowledged && <span className="secondary"> · {tr("reconocida", "acknowledged")}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <HazardsLink iso={iso} />
    </section>
  );
}

// ---------------------------------------------------------------- piezas

/** Medias diarias en barras de los últimos `days` días: lo observado, sin escala inventada. */
function DayBars({ readings, reference, days, label }: { readings: readonly Reading[]; reference: number; days: number; label: string }) {
  const values = Array.from({ length: days }, (_, index) => {
    const end = reference - (days - 1 - index) * DAY_MS;
    return { index, mean: windowMean(readings, end, 1) };
  });
  const top = Math.max(0, ...values.map((item) => item.mean ?? 0));
  return (
    <figure className="iso-days">
      <figcaption className="secondary">{label}</figcaption>
      <ol aria-hidden="true">
        {values.map((item) => (
          <li key={item.index} data-empty={item.mean === null ? "" : undefined}>
            <span style={{ height: `${top > 0 && item.mean !== null ? ((item.mean / top) * 100).toFixed(1) : 0}%` }} />
          </li>
        ))}
      </ol>
    </figure>
  );
}

/** Todas las piezas, en el orden de la rejilla. `CrewConsole` las monta tras la ubicación de «Inicio». */
export function isolationPanels(iso: IsolationData, active: boolean): ReactNode[] {
  return [
    // Cabe en la ventana, como la maqueta: el ajuste de «Distancia y nodos», siempre puesto y sin
    // botón («el botón ajustar a pantalla no lo queremos», 2026-11-15).
    <NodesFit active={active} fixed />,
    <IsoHeader iso={iso} />,
    <IsoGlobal iso={iso} />,
    <IsoIndicators iso={iso} />,
    <IsoTrend iso={iso} />,
    <IsoFactors iso={iso} />,
    <IsoMood iso={iso} />,
    <IsoInteractions iso={iso} />,
    <IsoSleep iso={iso} />,
    <IsoLight iso={iso} />,
    <IsoNutrition iso={iso} />,
    <IsoTests iso={iso} />,
    <IsoProgress iso={iso} />,
    <IsoCorrelations iso={iso} />,
    <IsoRisk iso={iso} />,
    <IsoRecommendations iso={iso} />,
    <IsoAlerts iso={iso} />,
  ];
}
