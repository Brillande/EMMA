import { type ReactNode, Suspense, lazy, useEffect, useState } from "react";

import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { FoldDivider, Folded } from "../components/SecondaryFold";
import { Loading, Unavailable } from "../components/Unavailable";
import { Pictogram } from "../icons";
import {
  type FhirObservation,
  type HabitatDisplayOnly,
  type HabitatExcursion,
  type HabitatParameter,
  type HabitatReading,
  type HabitatState,
  type HabitatSystems,
  api,
} from "../lib/api";
import { tr } from "../lib/i18n";
import { displayUnit, formatAge, formatNumber, formatUtc } from "../lib/format";
import { isLevel, levelStyle } from "../lib/levels";
import { MISSING_MARK, OK_MARK, UNAVAILABLE_MARK, UNKNOWN_PICTOGRAM, requestOutcome } from "../lib/marks";
import { type CorrelationSearch, outlookApi } from "../lib/outlookApi";
import { type Fetched, type HomeData } from "../dashboard/HomeBoard";
import { AreaCurve, MultiTrend, type Reading, Ring, Sparkline } from "../dashboard/HomeCharts";
import { capitalized } from "../dashboard/HazardCards";
import { IssArt } from "../dashboard/HomeArt";
import { NodesFit } from "../dashboard/NodesFit";
import { decimalsFor, limitMark, meterScale } from "../habitat/flow";
import { groupPictogram, parameterPictogram, systemPictogram } from "../habitat/pictograms";
import "../dashboard/referenceDashboard.css";
import "./environmentBoard.css";

/**
 * La sección «Entorno»: la maqueta «Panel ambiental EMMA en la ISS» (2026-11-15) con el estilo de
 * «Inicio», «Radiación» y «Aislamiento» (petición del usuario: «otra imagen de referencia que tiene
 * que seguir para crear otra pestaña; tienes que cambiarle estilos al cuerpo»). Las mismas tarjetas
 * (`ref-card`), la rejilla de 12 columnas y la ubicación de «Inicio» arriba; cada cifra es una
 * lectura del hábitat firmada en el ledger (`GET /api/habitat`) con los límites que da el backend
 * (`GET /api/habitat/parameters`).
 *
 * Lo que NO se copió de la maqueta, a propósito (invariantes 5-7 de `CLAUDE.md` y el criterio de
 * «Radiación» del 2026-11-14: «los datos no queremos copiarlos»):
 * - Sin «Índice ambiental RIDGE 94/100»: no hay fórmula validada que sume el aire, la luz y el agua.
 *   En su sitio, cuántos parámetros evaluados están hoy dentro de sus límites (los del backend).
 * - Sin analíticas de sangre y orina: EMMA no las lleva en este tablero, y las de la maqueta eran
 *   inventadas. Su hueco lo ocupa el ruido de cabina, que sí se mide y tiene límite.
 * - Agua y microbiología se muestran y no se evalúan (el backend lo dice con `limit_note`); sin
 *   lecturas, se dice «sin lectura», no «óptima» ni «no detectados».
 * - Sin «0,00 g»: el backend da el régimen de gravedad en palabras, y así se enseña.
 * - Sin tareas, puntos ni niveles: el estado declarado de los sistemas del hábitat.
 * - Las correlaciones son las que busca el backend (r de Pearson), sin pedir nada a la IA aquí.
 *
 * EL CUERPO (2026-11-15, «tienes que cambiarle estilos al cuerpo»): el render de «Inicio» en su
 * estilo `vessels` (holograma azul de `BodyArt.tsx`) con el brillo cian de la maqueta encima, por
 * CSS (`env-body`). Es adorno (§2.5 de `compliance/hmi-state-of-the-art.md`): no dice ningún nivel;
 * los niveles de músculo, hueso y equilibrio van en palabras al lado, los del motor.
 */

const ReferenceBody = lazy(() => import("../dashboard/ReferenceBody"));

const DAY_MS = 24 * 3600 * 1000;
const TREND_DAYS = 3;

/** Lo que la sección pide aparte del estado, una vez para todas sus piezas. */
export interface EnvironmentData {
  home: HomeData;
  habitat: Fetched<HabitatState>;
  parameters: Fetched<{ parameters: HabitatParameter[]; display_only?: HabitatDisplayOnly[] }>;
  systems: Fetched<HabitatSystems>;
  sleep: Fetched<Reading[]>;
  correlations: Fetched<CorrelationSearch>;
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

function readingsOf(observations: readonly FhirObservation[]): Reading[] {
  return observations
    .map((obs) => ({ at: Date.parse(obs.effectiveDateTime), value: obs.valueQuantity.value }))
    .filter((item) => Number.isFinite(item.at) && Number.isFinite(item.value))
    .sort((a, b) => a.at - b.at);
}

/** Las peticiones de la sección. Oculta, no se pide nada; al volver, se relee con el estado. */
export function useEnvironmentData(home: HomeData, active: boolean): EnvironmentData {
  const { status } = home;
  const [habitat, setHabitat] = useState<EnvironmentData["habitat"]>({ state: "loading" });
  const [parameters, setParameters] = useState<EnvironmentData["parameters"]>({ state: "loading" });
  const [systems, setSystems] = useState<EnvironmentData["systems"]>({ state: "loading" });
  const [sleep, setSleep] = useState<EnvironmentData["sleep"]>({ state: "loading" });
  const [correlations, setCorrelations] = useState<EnvironmentData["correlations"]>({ state: "loading" });
  const until = status.data.reference_time;

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    fetched(api.habitatParameters(), () => current, setParameters);
    return () => {
      current = false;
    };
  }, [active]);

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    const alive = () => current;
    const cut = new Date(until);
    fetched(api.habitat(cut), alive, setHabitat);
    fetched(api.habitatSystems(cut), alive, setSystems);
    fetched(
      api.observations("sleep-duration", 200, status.subject, until).then((body) => readingsOf(body.observations)),
      alive,
      setSleep,
    );
    fetched(outlookApi.search(status.subject, until, null), alive, setCorrelations);
    return () => {
      current = false;
    };
  }, [active, status.subject, until]);

  return { home, habitat, parameters, systems, sleep, correlations };
}

type Piece = { env: EnvironmentData };

function Pending({ item }: { item: Fetched<unknown> }) {
  if (item.state === "loading") return <Loading />;
  if (item.state === "failed") return <Unavailable outcome={item.outcome} />;
  return null;
}

// ---------------------------------------------------------------- utilidades

function habitatOf(env: EnvironmentData): HabitatState | null {
  return env.habitat.state === "ready" ? env.habitat.value : null;
}

function specOf(env: EnvironmentData, key: string): HabitatParameter | HabitatDisplayOnly | undefined {
  if (env.parameters.state !== "ready") return undefined;
  const { parameters, display_only: shown = [] } = env.parameters.value;
  return parameters.find((item) => item.key === key) ?? shown.find((item) => item.key === key);
}

function evaluated(env: EnvironmentData): HabitatParameter[] {
  return env.parameters.state === "ready" ? env.parameters.value.parameters : [];
}

function latestOf(env: EnvironmentData, key: string): HabitatReading | undefined {
  return habitatOf(env)?.latest.find((item) => item.parameter === key);
}

function seriesOf(env: EnvironmentData, key: string): Reading[] {
  const habitat = habitatOf(env);
  if (habitat === null) return [];
  return habitat.readings
    .filter((item) => item.parameter === key)
    .map((item) => ({ at: Date.parse(item.effective), value: item.value }))
    .filter((item) => Number.isFinite(item.at))
    .sort((a, b) => a.at - b.at);
}

function activeFor(env: EnvironmentData, key: string): HabitatExcursion | undefined {
  return habitatOf(env)?.active.find((item) => item.parameter === key);
}

/** Medias por tramos de `width` ms: la curva de 72 h de lecturas horarias, sin el temblor de cada hora. */
export function binned(readings: readonly Reading[], width: number): Reading[] {
  const bins = new Map<number, { sum: number; count: number }>();
  for (const item of readings) {
    const key = Math.floor(item.at / width);
    const bin = bins.get(key) ?? { sum: 0, count: 0 };
    bin.sum += item.value;
    bin.count += 1;
    bins.set(key, bin);
  }
  return [...bins.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([key, bin]) => ({ at: key * width + width / 2, value: bin.sum / bin.count }));
}

/** La cifra con los decimales que pide su tamaño y la unidad de presentación. */
function valueText(value: number, unit: string): string {
  const shown = displayUnit(unit);
  const number = formatNumber(value, decimalsFor(value));
  return shown === "" ? number : `${number} ${shown}`;
}

/** Rótulos cortos de la maqueta; el nombre entero del backend va en `title`. */
const SHORT: Record<string, string> = {
  "cabin-ppo2": tr("Oxígeno (pO₂)", "Oxygen (pO₂)"),
  "cabin-ppco2": tr("Dióxido de carbono (pCO₂)", "Carbon dioxide (pCO₂)"),
  "cabin-pressure": tr("Presión", "Pressure"),
  "cabin-humidity": tr("Humedad", "Humidity"),
  "cabin-co": tr("Monóxido de carbono", "Carbon monoxide"),
  "cabin-ammonia": tr("Amoníaco", "Ammonia"),
  "cabin-formaldehyde": tr("Formaldehído", "Formaldehyde"),
  "cabin-temperature": tr("Temperatura", "Temperature"),
  "cabin-noise": tr("Ruido", "Noise"),
  "cabin-light": tr("Iluminación", "Lighting"),
  "water-toc": tr("Carbono orgánico total", "Total organic carbon"),
  "water-silver": tr("Plata (biocida)", "Silver (biocide)"),
  "water-microbial": tr("Bacterias en agua", "Bacteria in water"),
  "air-microbial": tr("Bacterias en aire", "Bacteria in air"),
  "surface-microbial": tr("Bacterias en superficies", "Bacteria on surfaces"),
};

function nameOf(env: EnvironmentData, key: string): string {
  return SHORT[key] ?? specOf(env, key)?.display ?? key;
}

function fullName(env: EnvironmentData, key: string): string {
  return specOf(env, key)?.display ?? key;
}

/** El límite de una clase, si el parámetro lo tiene (el primero: el backend los ordena). */
function limitOf(spec: HabitatParameter | undefined, kind: string) {
  return spec?.limits.find((item) => item.kind === kind);
}

/** La palabra del estado de un parámetro evaluado, con su marca: la del backend, nada propio. */
function StateWord({ env, keyName }: { env: EnvironmentData; keyName: string }) {
  if (latestOf(env, keyName) === undefined) return <MarkOf mark={MISSING_MARK}>{tr("sin lectura", "no reading")}</MarkOf>;
  const out = activeFor(env, keyName);
  if (out !== undefined) return <MarkOf mark={limitMark(out.kind)}>{tr(`fuera de ${out.requirement}`, `outside ${out.requirement}`)}</MarkOf>;
  return <MarkOf mark={OK_MARK}>{tr("dentro", "within")}</MarkOf>;
}

// ---------------------------------------------------------------- fila 1

const GROUP_CHIPS: readonly { key: string; label: string; params: readonly string[] }[] = [
  { key: "air", label: tr("Aire", "Air"), params: ["cabin-ppo2", "cabin-ppco2", "cabin-pressure", "cabin-humidity", "cabin-co", "cabin-ammonia", "cabin-formaldehyde"] },
  { key: "thermal", label: tr("Temperatura", "Temperature"), params: ["cabin-temperature"] },
  { key: "light", label: tr("Luz", "Light"), params: ["cabin-light"] },
  { key: "noise", label: tr("Ruido", "Noise"), params: ["cabin-noise"] },
  { key: "water", label: tr("Agua", "Water"), params: ["water-toc", "water-silver", "water-microbial"] },
  { key: "microbiology", label: tr("Microbios", "Microbes"), params: ["air-microbial", "surface-microbial"] },
];

/** Lleva al panel de la pestaña con ese `data-ui` (cada bloque `key` tiene su `env-key`). */
function goToPanel(target: string) {
  document.querySelector(`[data-ui="${target}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" });
}

/** La franja de la maqueta: título, hora de los datos y los bloques con su estado. */
export function EnvHeader({ env }: Piece) {
  const { status } = env.home;
  const habitat = habitatOf(env);
  const last = habitat?.latest.reduce((top, item) => Math.max(top, Date.parse(item.effective)), -Infinity) ?? -Infinity;
  return (
    <section data-ui="env-header" className="ref-card env-header" aria-label={tr("Entorno de la nave", "Spacecraft environment")}>
      <h2 className="env-title">
        <Pictogram name="ridge-environment" />
        <span title={capitalized(status.mission.profile?.display ?? tr("misión", "mission"))}>{tr("Entorno de la nave", "Spacecraft environment")}</span>
      </h2>
      <p className="env-updated">
        <span className="ref-live" aria-hidden="true" />{" "}
        <span title={Number.isFinite(last) ? tr(`Última lectura de cabina hace ${formatAge(Math.max(0, (env.home.reference - last) / 60000))}`, `Latest cabin reading ${formatAge(Math.max(0, (env.home.reference - last) / 60000))} ago`) : undefined}>
          {tr("Datos a", "Data as of")} <span className="num">{formatUtc(new Date(env.home.reference))}</span>
        </span>
      </p>
      <ul className="env-chips" aria-label={tr("Bloques del entorno", "Environment blocks")}>
        {GROUP_CHIPS.map((chip) => {
          const measured = chip.params.filter((key) => latestOf(env, key) !== undefined);
          const out = chip.params.filter((key) => activeFor(env, key) !== undefined);
          return (
            <li key={chip.key} data-chip={chip.key}>
              {/* Ancla de la maqueta: lleva a su panel, como las de «Radiación» (`RadNav`). */}
              <button type="button" onClick={() => goToPanel(`env-${chip.key}`)} title={tr(`Ir a ${chip.label}`, `Go to ${chip.label}`)}>
                <Pictogram name={parameterPictogram(chip.params[0] ?? "")} />
                <span>{chip.label}</span>
                {habitat === null ? null : measured.length === 0 ? (
                  <MarkOf mark={MISSING_MARK}>{tr("sin lectura", "no reading")}</MarkOf>
                ) : out.length > 0 ? (
                  <MarkOf mark={limitMark(activeFor(env, out[0] ?? "")?.kind ?? "")}>{tr(`${formatNumber(out.length)} fuera`, `${formatNumber(out.length)} outside`)}</MarkOf>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** «Estado ambiental global»: sin salidas activas de ningún límite, o cuáles hay. */
export function EnvGlobal({ env }: Piece) {
  const habitat = habitatOf(env);
  const active = habitat?.active ?? [];
  const health = active.filter((item) => item.kind === "health");
  return (
    <section data-ui="env-global" className="ref-card env-global" aria-label={tr("Estado ambiental global", "Overall environmental status")}>
      <PanelTitle concept="domains" className="ref-h">
        {tr("Estado ambiental global", "Overall environmental status")}
      </PanelTitle>
      {habitat === null ? (
        <Pending item={env.habitat} />
      ) : habitat.latest.length === 0 ? (
        <MarkOf mark={MISSING_MARK}>{tr("Sin telemetría de cabina.", "No cabin telemetry.")}</MarkOf>
      ) : (
        <div className="env-global-box" data-state={active.length === 0 ? "ok" : health.length > 0 ? "health" : "comfort"}>
          {active.length === 0 ? (
            <>
              <Pictogram name="check" className="env-global-icon" />
              <p>
                <strong>{tr("Entorno dentro de límites", "Environment within limits")}</strong>
                <span className="secondary">{tr("Ninguna lectura fuera de un límite ni de la zona de confort.", "No reading outside a limit or the comfort zone.")}</span>
              </p>
            </>
          ) : (
            <>
              <Pictogram name={limitMark(health.length > 0 ? "health" : "performance").pictogram ?? UNKNOWN_PICTOGRAM} className="env-global-icon" />
              <p>
                <strong>
                  {formatNumber(active.length)} {active.length === 1 ? tr("lectura fuera", "reading outside") : tr("lecturas fuera", "readings outside")}
                </strong>
                <span className="secondary">{active.map((item) => `${nameOf(env, item.parameter)}: ${item.requirement}`).join(" · ")}</span>
              </p>
            </>
          )}
        </div>
      )}
    </section>
  );
}

/** En lugar del «Índice ambiental RIDGE»: cuántos parámetros evaluados están hoy dentro. */
export function EnvIndex({ env }: Piece) {
  const params = evaluated(env);
  const measured = params.filter((item) => latestOf(env, item.key) !== undefined);
  const inside = measured.filter((item) => activeFor(env, item.key) === undefined);
  return (
    <section data-ui="env-index" className="ref-card env-index" aria-label={tr("Parámetros dentro de límites", "Parameters within limits")}>
      <PanelTitle concept="domains" className="ref-h">
        {tr("Parámetros dentro de límites", "Parameters within limits")}
      </PanelTitle>
      {env.parameters.state !== "ready" || env.habitat.state !== "ready" ? (
        <Pending item={env.parameters.state !== "ready" ? env.parameters : env.habitat} />
      ) : (
        <div className="env-index-body">
          <Ring done={inside.length} total={measured.length} label={tr("parámetros evaluados dentro de sus límites", "evaluated parameters within their limits")}>
            <strong className="num">{formatNumber(inside.length)}</strong>
            <small>/{formatNumber(measured.length)}</small>
          </Ring>
          <ul className="env-list">
            {params.slice(0, 5).map((item) => (
              <li key={item.key}>
                <Pictogram name={parameterPictogram(item.key)} />
                <span className="ref-clamp" title={item.display}>
                  {nameOf(env, item.key)}
                </span>
                <StateWord env={env} keyName={item.key} />
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="secondary env-note" title={tr("No es un índice compuesto: cuenta lecturas dentro de los límites del backend.", "Not a composite index: it counts readings within the backend's limits.")}>
        {tr("No es un índice: cuenta lecturas dentro de los límites del backend.", "Not an index: it counts readings within the backend's limits.")}
      </p>
    </section>
  );
}

/** La estación de la maqueta (adorno, §2.5): ningún dato. */
export function EnvStation() {
  return (
    <div className="ref-card env-station" aria-hidden="true">
      <IssArt />
    </div>
  );
}

/** «Tendencia (72 h)»: temperatura, humedad y CO₂ de cabina, cada una en su tramo. */
export function EnvTrend({ env }: Piece) {
  const keys = ["cabin-temperature", "cabin-humidity", "cabin-ppco2"] as const;
  return (
    <section data-ui="env-trend" className="ref-card env-trend" aria-label={tr("Tendencia de 72 horas", "72-hour trend")}>
      <PanelTitle concept="trends" className="ref-h">
        {tr("Tendencia (72 h)", "Trend (72 h)")}
      </PanelTitle>
      {env.habitat.state !== "ready" ? (
        <Pending item={env.habitat} />
      ) : (
        <MultiTrend
          series={keys.map((key) => ({ key, label: nameOf(env, key), readings: binned(seriesOf(env, key), 3 * 3600 * 1000) }))}
          until={env.home.reference}
          days={TREND_DAYS}
        />
      )}
    </section>
  );
}

/** «Estado de riesgo»: las salidas de límite de las últimas 72 h, por clase. */
export function EnvRisk({ env }: Piece) {
  const habitat = habitatOf(env);
  const from = env.home.reference - TREND_DAYS * DAY_MS;
  const recent = (habitat?.excursions ?? []).filter((item) => Date.parse(item.end) >= from);
  const health = recent.filter((item) => item.kind === "health");
  const comfort = recent.filter((item) => item.kind !== "health");
  return (
    <section data-ui="env-risk" className="ref-card env-risk" aria-label={tr("Salidas de límite en 72 horas", "Limit excursions in 72 hours")}>
      <PanelTitle concept="risks" className="ref-h">
        {tr("Salidas de límite (72 h)", "Limit excursions (72 h)")}
      </PanelTitle>
      {habitat === null ? (
        <Pending item={env.habitat} />
      ) : (
        <ul className="env-risk-list">
          <li data-state={recent.length === 0 ? "ok" : undefined}>
            {recent.length === 0 ? (
              <MarkOf mark={OK_MARK}>
                <strong>{tr("Ninguna", "None")}</strong> <span className="secondary">{tr("en las últimas 72 h", "in the last 72 h")}</span>
              </MarkOf>
            ) : (
              <MarkOf mark={OK_MARK}>
                <strong className="num">{formatNumber(recent.length)}</strong> <span className="secondary">{tr("salidas en 72 h", "excursions in 72 h")}</span>
              </MarkOf>
            )}
          </li>
          <li>
            <MarkOf mark={limitMark("performance")}>
              {tr("Confort u objetivo", "Comfort or target")} (<span className="num">{formatNumber(comfort.length)}</span>)
            </MarkOf>
            <span className="secondary ref-clamp">{comfort.length === 0 ? tr("sin salidas", "no excursions") : [...new Set(comfort.map((item) => nameOf(env, item.parameter)))].join(", ")}</span>
          </li>
          <li>
            <MarkOf mark={limitMark("health")}>
              {tr("Límite normativo", "Normative limit")} (<span className="num">{formatNumber(health.length)}</span>)
            </MarkOf>
            <span className="secondary ref-clamp">{health.length === 0 ? tr("sin salidas", "no excursions") : [...new Set(health.map((item) => nameOf(env, item.parameter)))].join(", ")}</span>
          </li>
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- fila 2

const AIR_KEYS = ["cabin-ppo2", "cabin-ppco2", "cabin-pressure", "cabin-humidity", "cabin-co", "cabin-ammonia", "cabin-formaldehyde"] as const;

/**
 * La barra de cada fila, solo donde el backend da una escala sin decidir nada (`meterScale`): un
 * límite normativo único, con techo y en unidad de razón. Las demás filas no llevan barra.
 */
function Meter({ spec, value }: { spec: HabitatParameter | undefined; value: number }) {
  const scale = spec === undefined ? null : meterScale(spec);
  if (scale === null) return <span className="env-meter" data-empty="" aria-hidden="true" />;
  const share = Math.min(1, Math.max(0, (value - scale.min) / (scale.max - scale.min)));
  const limit = (scale.band.high - scale.min) / (scale.max - scale.min);
  return (
    <span className="env-meter" aria-hidden="true">
      <span className="env-meter-fill" style={{ width: `${(share * 100).toFixed(1)}%` }} />
      <span className="env-meter-limit" style={{ left: `${(limit * 100).toFixed(1)}%` }} />
    </span>
  );
}

export function EnvAir({ env }: Piece) {
  return (
    <section
      data-ui="env-air"
      className="ref-card env-air"
      aria-label={tr("Atmósfera y calidad del aire", "Atmosphere and air quality")}
      title={tr("Barra: la lectura frente a su límite normativo (la marca), hasta dos veces el límite; sin barra donde rigen varios límites.", "Bar: the reading against its normative limit (the mark), up to twice the limit; no bar where several limits apply.")}
    >
      <PanelTitle concept="domains" className="ref-h">
        <span className="env-h-icon">
          <Pictogram name={groupPictogram("cabin")} />
        </span>
        {tr("Atmósfera y calidad del aire", "Atmosphere and air quality")}
      </PanelTitle>
      {env.habitat.state !== "ready" ? (
        <Pending item={env.habitat} />
      ) : (
        <ul className="env-rows">
          {AIR_KEYS.map((key) => {
            const last = latestOf(env, key);
            const spec = evaluated(env).find((item) => item.key === key);
            const out = activeFor(env, key);
            return (
              <li key={key} title={fullName(env, key)} data-out={out === undefined ? undefined : out.kind}>
                <Pictogram name={parameterPictogram(key)} />
                <span className="ref-clamp">{nameOf(env, key)}</span>
                {last === undefined ? (
                  <MarkOf mark={MISSING_MARK}>{tr("sin lectura", "no reading")}</MarkOf>
                ) : (
                  <>
                    <Meter spec={spec} value={last.value} />
                    <span className="num env-value">{valueText(last.value, last.unit)}</span>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** «Temperatura y confort térmico»: la lectura sobre el tramo de salud con la zona de confort. */
export function EnvThermal({ env }: Piece) {
  const key = "cabin-temperature";
  const last = latestOf(env, key);
  const spec = evaluated(env).find((item) => item.key === key);
  const health = limitOf(spec, "health");
  const comfort = limitOf(spec, "performance");
  const out = activeFor(env, key);
  const low = health?.low ?? null;
  const high = health?.high ?? null;
  const span = low !== null && high !== null ? { min: low - 2, max: high + 2 } : null;
  const at = (value: number) => (span === null ? 0 : Math.min(100, Math.max(0, ((value - span.min) / (span.max - span.min)) * 100)));
  return (
    <section data-ui="env-thermal" className="ref-card env-thermal" aria-label={tr("Temperatura y confort térmico", "Temperature and thermal comfort")}>
      <PanelTitle concept="domains" className="ref-h">
        <span className="env-h-icon">
          <Pictogram name="thermometer" />
        </span>
        {tr("Temperatura y confort térmico", "Temperature and thermal comfort")}
      </PanelTitle>
      {env.habitat.state !== "ready" || env.parameters.state !== "ready" ? (
        <Pending item={env.habitat.state !== "ready" ? env.habitat : env.parameters} />
      ) : last === undefined ? (
        <MarkOf mark={MISSING_MARK}>{tr("sin lectura de temperatura", "no temperature reading")}</MarkOf>
      ) : (
        <>
          <div className="env-thermal-top">
            <p className="env-big">
              <strong className="num">{valueText(last.value, last.unit)}</strong>
              <span>
                {tr("Confort:", "Comfort:")}{" "}
                {out === undefined ? (
                  <MarkOf mark={OK_MARK}>{tr("dentro", "within")}</MarkOf>
                ) : (
                  <MarkOf mark={limitMark(out.kind)}>{tr(`fuera de ${out.requirement}`, `outside ${out.requirement}`)}</MarkOf>
                )}
              </span>
            </p>
            {comfort !== undefined && comfort.low !== null && comfort.high !== null && (
              <p className="env-range" title={comfort.requirement}>
                <span className="secondary">{tr("Zona de confort", "Comfort zone")}</span>
                <strong className="num">
                  {formatNumber(comfort.low)} – {formatNumber(comfort.high)} {displayUnit(last.unit)}
                </strong>
              </p>
            )}
          </div>
          {span !== null && low !== null && high !== null && (
            <div className="env-thermo" role="img" aria-label={tr(`Temperatura ${valueText(last.value, last.unit)} sobre el tramo de ${formatNumber(low)} a ${formatNumber(high)}`, `Temperature ${valueText(last.value, last.unit)} on the span from ${formatNumber(low)} to ${formatNumber(high)}`)}>
              <Pictogram name="snowflake" />
              <span className="env-thermo-track">
                <span className="env-thermo-health" style={{ left: `${at(low)}%`, width: `${at(high) - at(low)}%` }} />
                {comfort?.low != null && comfort.high != null && (
                  <span className="env-thermo-comfort" style={{ left: `${at(comfort.low)}%`, width: `${at(comfort.high) - at(comfort.low)}%` }} />
                )}
                <span className="env-thermo-marker" style={{ left: `${at(last.value)}%` }} />
              </span>
              <Pictogram name="arrow-up" />
            </div>
          )}
          <div className="env-thermo-limits">
            <p>
              <Pictogram name="snowflake" />
              <span>
                {tr("Límite inferior", "Lower limit")} <span className="num">&lt; {formatNumber(low ?? Number.NaN)} {displayUnit(last.unit)}</span>
              </span>
            </p>
            <p>
              <Pictogram name="arrow-up" />
              <span>
                {tr("Límite superior", "Upper limit")} <span className="num">&gt; {formatNumber(high ?? Number.NaN)} {displayUnit(last.unit)}</span>
              </span>
            </p>
          </div>
        </>
      )}
    </section>
  );
}

/** «Luz y ciclo circadiano»: la iluminancia de cabina (no se evalúa) y el último sueño. */
export function EnvLight({ env }: Piece) {
  const key = "cabin-light";
  const last = latestOf(env, key);
  const day = seriesOf(env, key).filter((item) => item.at > env.home.reference - DAY_MS && item.at <= env.home.reference);
  const mean = day.length === 0 ? null : day.reduce((sum, item) => sum + item.value, 0) / day.length;
  const top = day.length === 0 ? null : Math.max(...day.map((item) => item.value));
  const sleep = env.sleep.state === "ready" ? env.sleep.value.at(-1) : undefined;
  const spec = specOf(env, key);
  const note = spec !== undefined && "limit_note" in spec ? spec.limit_note : null;
  const sleepUnit = env.home.catalog.get("sleep-duration")?.unit ?? "h";
  return (
    <section data-ui="env-light" className="ref-card env-light" aria-label={tr("Luz y ciclo circadiano", "Light and circadian cycle")}>
      <PanelTitle concept="domains" className="ref-h">
        <span className="env-h-icon">
          <Pictogram name="bulb" />
        </span>
        {tr("Luz y ciclo circadiano", "Light and circadian cycle")}
      </PanelTitle>
      {env.habitat.state !== "ready" ? (
        <Pending item={env.habitat} />
      ) : (
        <div className="env-light-body">
          <ul className="env-rows">
            <li>
              <Pictogram name="bulb" />
              <span>{tr("Iluminación (última)", "Lighting (latest)")}</span>
              {last === undefined ? <MarkOf mark={MISSING_MARK}>{tr("sin lectura", "no reading")}</MarkOf> : <span className="num env-value">{valueText(last.value, last.unit)}</span>}
            </li>
            <li>
              <Pictogram name="clock" />
              <span>{tr("Media de 24 h", "24 h mean")}</span>
              {mean === null || last === undefined ? <MarkOf mark={MISSING_MARK}>{tr("sin lectura", "no reading")}</MarkOf> : <span className="num env-value">{valueText(mean, last.unit)}</span>}
            </li>
            <li>
              <Pictogram name="arrow-up" />
              <span>{tr("Máxima de 24 h", "24 h maximum")}</span>
              {top === null || last === undefined ? <MarkOf mark={MISSING_MARK}>{tr("sin lectura", "no reading")}</MarkOf> : <span className="num env-value">{valueText(top, last.unit)}</span>}
            </li>
          </ul>
          <figure className="env-light-curve">
            <figcaption className="secondary">{tr("Ciclo de las últimas 24 h", "Cycle over the last 24 h")}</figcaption>
            <AreaCurve readings={binned(day, 3600 * 1000)} until={env.home.reference} />
            <div className="env-light-axis secondary" aria-hidden="true">
              <span>-24 h</span>
              <span>-12 h</span>
              <span>{tr("ahora", "now")}</span>
            </div>
          </figure>
        </div>
      )}
      <div className="env-sleep">
        <Pictogram name="moon-z" />
        <span>{tr("Sueño (última noche)", "Sleep (last night)")}</span>
        {env.sleep.state !== "ready" ? (
          <Pending item={env.sleep} />
        ) : sleep === undefined ? (
          <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
        ) : (
          <strong className="num">{valueText(sleep.value, sleepUnit)}</strong>
        )}
      </div>
      {note !== null && (
        <p className="secondary env-note" title={note}>
          {note}
        </p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- fila 3

/** El ruido de cabina, con su límite normativo y su curva de 24 h. */
export function EnvNoise({ env }: Piece) {
  const key = "cabin-noise";
  const last = latestOf(env, key);
  const spec = evaluated(env).find((item) => item.key === key);
  const limit = limitOf(spec, "health");
  const day = seriesOf(env, key).filter((item) => item.at > env.home.reference - DAY_MS && item.at <= env.home.reference);
  const top = day.length === 0 ? null : Math.max(...day.map((item) => item.value));
  return (
    <section data-ui="env-noise" className="ref-card env-noise" aria-label={tr("Ruido de cabina", "Cabin noise")}>
      <PanelTitle concept="domains" className="ref-h">
        <span className="env-h-icon">
          <Pictogram name="speaker-waves" />
        </span>
        {tr("Ruido de cabina", "Cabin noise")}
      </PanelTitle>
      {env.habitat.state !== "ready" ? (
        <Pending item={env.habitat} />
      ) : last === undefined ? (
        <MarkOf mark={MISSING_MARK}>{tr("sin lectura de ruido", "no noise reading")}</MarkOf>
      ) : (
        <>
          <p className="env-big">
            <strong className="num">{valueText(last.value, last.unit)}</strong>
            <StateWord env={env} keyName={key} />
          </p>
          <ul className="env-rows">
            <li>
              <Pictogram name="arrow-up" />
              <span>{tr("Máximo de 24 h", "24 h maximum")}</span>
              {top === null ? <MarkOf mark={MISSING_MARK}>{tr("sin lectura", "no reading")}</MarkOf> : <span className="num env-value">{valueText(top, last.unit)}</span>}
            </li>
            {limit !== undefined && limit.high !== null && (
              <li title={limit.requirement}>
                <Pictogram name="dash" />
                <span>{tr("Límite normativo", "Normative limit")}</span>
                <span className="num env-value">{valueText(limit.high, last.unit)}</span>
              </li>
            )}
          </ul>
          <Sparkline readings={day} until={env.home.reference} />
        </>
      )}
    </section>
  );
}

/** Un bloque de parámetros que se muestran y no se evalúan (agua, microbiología). */
function DisplayOnlyRows({ env, keys }: { env: EnvironmentData; keys: readonly string[] }) {
  return (
    <ul className="env-rows">
      {keys.map((key) => {
        const last = latestOf(env, key);
        return (
          <li key={key} title={fullName(env, key)}>
            <Pictogram name={parameterPictogram(key)} />
            <span className="ref-clamp">{nameOf(env, key)}</span>
            {last === undefined ? (
              <MarkOf mark={MISSING_MARK}>{tr("sin lectura", "no reading")}</MarkOf>
            ) : (
              <span className="num env-value">{valueText(last.value, last.unit)}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function limitNote(env: EnvironmentData, key: string): string | null {
  const spec = specOf(env, key);
  return spec !== undefined && "limit_note" in spec ? spec.limit_note : null;
}

export function EnvWater({ env }: Piece) {
  const keys = ["water-microbial", "water-toc", "water-silver"] as const;
  const note = limitNote(env, keys[0]);
  return (
    <section data-ui="env-water" className="ref-card env-water" aria-label={tr("Agua potable", "Drinking water")}>
      <PanelTitle concept="domains" className="ref-h">
        <span className="env-h-icon">
          <Pictogram name={groupPictogram("water")} />
        </span>
        {tr("Agua potable", "Drinking water")}
      </PanelTitle>
      {env.habitat.state !== "ready" || env.parameters.state !== "ready" ? (
        <Pending item={env.habitat.state !== "ready" ? env.habitat : env.parameters} />
      ) : (
        <DisplayOnlyRows env={env} keys={keys} />
      )}
      <p className="secondary env-note" title={note ?? tr("Se muestra y no se evalúa.", "Shown, not evaluated.")}>
        <MarkOf mark={UNAVAILABLE_MARK}>{tr("No se evalúa", "Not evaluated")}{note === null ? "" : `: ${note}`}</MarkOf>
      </p>
    </section>
  );
}

export function EnvMicrobiology({ env }: Piece) {
  const keys = ["air-microbial", "surface-microbial"] as const;
  const note = limitNote(env, keys[0]);
  return (
    <section data-ui="env-microbiology" className="ref-card env-microbiology" aria-label={tr("Microbiología", "Microbiology")}>
      <PanelTitle concept="domains" className="ref-h">
        <span className="env-h-icon">
          <Pictogram name={groupPictogram("microbiology")} />
        </span>
        {tr("Microbiología (aire y superficies)", "Microbiology (air and surfaces)")}
      </PanelTitle>
      {env.habitat.state !== "ready" || env.parameters.state !== "ready" ? (
        <Pending item={env.habitat.state !== "ready" ? env.habitat : env.parameters} />
      ) : (
        <DisplayOnlyRows env={env} keys={keys} />
      )}
      <p className="secondary env-note" title={note ?? tr("Se muestra y no se evalúa.", "Shown, not evaluated.")}>
        <MarkOf mark={UNAVAILABLE_MARK}>{tr("No se evalúa", "Not evaluated")}{note === null ? "" : `: ${note}`}</MarkOf>
      </p>
    </section>
  );
}

// ---------------------------------------------------------------- fila 4

const GRAVITY_DOMAINS: readonly { key: string; label: string }[] = [
  { key: "musculoskeletal", label: tr("Músculo", "Muscle") },
  { key: "bone", label: tr("Hueso", "Bone") },
  { key: "neuro-ocular", label: "Neuro-ocular" },
];

/** «Exposición a gravedad»: el régimen del backend, el día de misión y los dominios que dependen de ella. */
export function EnvGravity({ env }: Piece) {
  const { mission, domains } = env.home.status;
  const days = Math.floor(mission.mission_day);
  const hours = Math.floor((mission.mission_day - days) * 24);
  return (
    <section data-ui="env-gravity" className="ref-card env-gravity" aria-label={tr("Exposición a la gravedad", "Gravity exposure")}>
      <PanelTitle concept="domains" className="ref-h">
        <span className="env-h-icon">
          <Pictogram name="ridge-gravity" />
        </span>
        {tr("Exposición a gravedad", "Gravity exposure")}
      </PanelTitle>
      <div className="env-gravity-grid">
        <div className="env-gravity-now">
          <p>
            <span className="secondary">{tr("Régimen actual", "Current regime")}</span>
            <strong>{capitalized(mission.gravity_display)}</strong>
          </p>
          <p title={tr("Días de misión hasta la hora de los datos.", "Mission days up to the time of the data.")}>
            <span className="secondary">{tr("Tiempo de misión", "Mission time")}</span>
            <strong className="num">
              {tr(`${formatNumber(days)} días ${formatNumber(hours)} h`, `${formatNumber(days)} days ${formatNumber(hours)} h`)}
            </strong>
          </p>
        </div>
        <div className="env-gravity-box">
          <p className="secondary env-gravity-effects-h">{tr("Efectos monitorizados", "Monitored effects")}</p>
          <ul className="env-gravity-effects" aria-label={tr("Dominios afectados por la gravedad", "Domains affected by gravity")}>
          {GRAVITY_DOMAINS.map((item) => {
            const level = domains[item.key]?.level;
            const style = level !== undefined && isLevel(level) ? levelStyle(level) : null;
            return (
              <li key={item.key}>
                <Pictogram name={`domain-${item.key}` as "domain-bone"} />
                <span>{item.label}</span>
                {level === undefined ? (
                  <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin dominio", "no domain")}</MarkOf>
                ) : (
                  <Mark pictogram={style?.pictogram ?? UNKNOWN_PICTOGRAM}>{style?.label ?? level}</Mark>
                )}
              </li>
            );
          })}
          </ul>
        </div>
        <div className="env-body" aria-hidden="true">
          <Suspense fallback={<Loading />}>
            <ReferenceBody look="vessels" switcher={false} />
          </Suspense>
        </div>
      </div>
    </section>
  );
}

/** En lugar de «Tareas y retos»: el estado declarado de los sistemas del hábitat. */
export function EnvSystems({ env }: Piece) {
  return (
    <section data-ui="env-systems" className="ref-card env-systems" aria-label={tr("Sistemas del hábitat", "Habitat systems")}>
      <PanelTitle concept="domains" className="ref-h">
        <span className="env-h-icon">
          <Pictogram name="gear" />
        </span>
        {tr("Control del entorno: sistemas", "Environmental control: systems")}
      </PanelTitle>
      {env.systems.state !== "ready" ? (
        <Pending item={env.systems} />
      ) : (
        <>
          <ul className="env-rows env-systems-list">
            {env.systems.value.systems.slice(0, 5).map((system) => {
              const whole = system.statuses.find((item) => item.module === null) ?? system.statuses[0];
              return (
                <li key={system.key} title={system.description}>
                  <Pictogram name={systemPictogram(system.key)} />
                  <span className="ref-clamp">{capitalized(system.display)}</span>
                  {whole === undefined || !whole.declared ? (
                    <MarkOf mark={MISSING_MARK}>{tr("sin declarar", "not declared")}</MarkOf>
                  ) : (
                    <span className="env-value">{whole.state_display}</span>
                  )}
                </li>
              );
            })}
          </ul>
          <p className="secondary env-note" title={env.systems.value.note}>
            {env.systems.value.summary}
          </p>
        </>
      )}
    </section>
  );
}

/** «Análisis y correlaciones»: los pares de mayor |r| que busca el backend. */
export function EnvCorrelations({ env }: Piece) {
  const name = (key: string) => capitalized(env.home.catalog.get(key)?.display_es ?? key);
  return (
    <section data-ui="env-correlations" className="ref-card env-correlations" aria-label={tr("Análisis y correlaciones", "Analysis and correlations")}>
      <PanelTitle concept="trends" className="ref-h">
        {tr("Análisis y correlaciones", "Analysis and correlations")}
      </PanelTitle>
      {env.correlations.state !== "ready" ? (
        <Pending item={env.correlations} />
      ) : (
        <>
          {(() => {
            const pairs = env.correlations.value.pairs.filter((pair) => pair.r !== null).slice(0, 4);
            return pairs.length === 0 ? (
              <MarkOf mark={MISSING_MARK}>{tr("Sin pares con días suficientes.", "No pairs with enough days.")}</MarkOf>
            ) : (
              <ul className="env-rows env-correlation-list">
                {pairs.map((pair) => (
                  <li key={`${pair.x.key}|${pair.y.key}`} title={pair.text}>
                    <Pictogram name="check" />
                    <span className="ref-clamp">
                      {tr(`${name(pair.x.key)} y ${name(pair.y.key).toLowerCase()}`, `${name(pair.x.key)} and ${name(pair.y.key).toLowerCase()}`)}
                    </span>
                    <span className="num env-value">(r = {formatNumber(pair.r ?? 0, 2)})</span>
                  </li>
                ))}
              </ul>
            );
          })()}
          <p className="secondary env-note" title={`${env.correlations.value.multiple} ${env.correlations.value.simulated_text}`}>
            {tr(`Correlación, no causa · ${formatNumber(env.correlations.value.tested)} pares mirados.`, `Correlation, not cause · ${formatNumber(env.correlations.value.tested)} pairs examined.`)}
          </p>
        </>
      )}
    </section>
  );
}

const FOLD = "crew.environment";

/**
 * Todas las piezas, en el orden de la rejilla. `CrewConsole` las monta tras la ubicación de «Inicio».
 *
 * Bajo la raya plegable (decisión del usuario, 2026-11-15: lo secundario de cada pestaña, plegado
 * como en «Inicio») van los bloques de detalle. Arriba queda todo lo que avisa: la franja con sus
 * chips y el «Estado ambiental global» nombran cada lectura fuera de límite, y las salidas de 72 h
 * no se pliegan nunca; así, plegar el detalle no esconde ningún aviso que no se vea ya arriba.
 */
export function environmentPanels(env: EnvironmentData, active: boolean): ReactNode[] {
  const folded = (panel: ReactNode) => <Folded id={FOLD}>{panel}</Folded>;
  return [
    <NodesFit active={active} fixed />,
    <EnvHeader env={env} />,
    <EnvGlobal env={env} />,
    <EnvIndex env={env} />,
    <EnvStation />,
    <EnvTrend env={env} />,
    <EnvRisk env={env} />,
    <FoldDivider id={FOLD} what={tr("Aire, temperatura, luz, ruido, agua, microbios, gravedad, sistemas y correlaciones", "Air, temperature, light, noise, water, microbes, gravity, systems and correlations")} />,
    folded(<EnvAir env={env} />),
    folded(<EnvThermal env={env} />),
    folded(<EnvLight env={env} />),
    folded(<EnvNoise env={env} />),
    folded(<EnvWater env={env} />),
    folded(<EnvMicrobiology env={env} />),
    folded(<EnvGravity env={env} />),
    folded(<EnvSystems env={env} />),
    folded(<EnvCorrelations env={env} />),
  ];
}
