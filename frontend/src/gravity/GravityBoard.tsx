import { type CSSProperties, type ReactNode, Suspense, lazy, useEffect, useState } from "react";

import { AvatarSwitch } from "../components/AvatarSwitch";
import { Command } from "../components/Command";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { Pictogram } from "../icons";
import type { PictogramName } from "../icons/registry";
import { type Indicator, type RiskEntity, api, risksApi } from "../lib/api";
import { useAvatar } from "../lib/avatar";
import { displayUnit, formatAge, formatNumber, formatUtc } from "../lib/format";
import { tr } from "../lib/i18n";
import { LEVEL_ORDER, isLevel, levelStyle } from "../lib/levels";
import { MISSING_MARK, OK_MARK, UNAVAILABLE_MARK, UNKNOWN_PICTOGRAM, requestOutcome } from "../lib/marks";
import { cssVar } from "../lib/palette";
import { type Fetched, type HomeData, type HomeLinks, HomeCrew, HomeQuickHazards, sectionLink } from "../dashboard/HomeBoard";
import { ImpactBar, MultiTrend, type Reading, Ring, levelToken } from "../dashboard/HomeCharts";
import { capitalized } from "../dashboard/HazardCards";
import { BodyBonesArt, BodyMuscleArt, BodyVesselsArt } from "../dashboard/HomeArt";
import { NodesFit } from "../dashboard/NodesFit";
import { dailyMeans, readingsOf, streakDays, windowMean } from "../isolation/IsolationBoard";
import "../dashboard/referenceDashboard.css";
import "../isolation/isolationBoard.css";
import "./gravityBoard.css";

/**
 * La sección «Gravedad»: la maqueta «Panel EMMA: Salud Gravitacional de la Tripulación» (2026-11-15)
 * con el estilo de «Inicio», «Radiación» y «Aislamiento» (petición del usuario, 2026-11-15: «hazme
 * otra pestaña lo más similar posible a esta […] coger el modelo 2 femenino y masculino y darle
 * diferentes estilos»). Los cuerpos son el render 2D de siempre (varón o mujer, el avatar elegido)
 * recoloreado en tres estilos —músculo, hueso y holograma de vasos— con `BodyArt`.
 *
 * Lo que NO se copió de la maqueta, a propósito (invariantes 5-7 de `CLAUDE.md` y el criterio de
 * «Radiación»: «los datos no queremos copiarlos»):
 * - Sin porcentajes de pérdida inventados (-6,4 % de masa muscular…): cada fila es la última lectura
 *   del catálogo y su cambio frente a la primera de la misión, calculado aquí y dicho así.
 * - Sin «Adaptación estimada 2-5 d» ni readaptación en Tierra: EMMA no tiene un modelo validado de
 *   eso. La fase de misión es la del backend, con su base («diseño EMMA»).
 * - Sin «riesgo de fractura bajo», «intolerancia ortostática baja» ni volumen plasmático: no hay
 *   indicador que lo sostenga. La caída ortostática y la yugular por ecografía son las medidas.
 * - Sin días por entorno anteriores a la misión: solo el régimen declarado y el día de misión.
 * - Sin puntos ni retos: la constancia del ejercicio son los días con lectura.
 * - La predicción es la extrapolación de tendencia del backend (`predictions`), con su frase de que
 *   no es un pronóstico clínico. Recomendaciones y alertas, las del backend, tal cual.
 *
 * COLORES DE ADORNO (§2.5 de `compliance/hmi-state-of-the-art.md`): el acento de la G de RIDGE
 * (`--acc-gravity`) y los estilos de cuerpo no significan nada. Lo que es dato (`--lvl`, `data-tone`,
 * las marcas) conserva el color de su tabla.
 */

const DAY_MS = 24 * 3600 * 1000;
const TREND_DAYS = 30;
const GRAVITY_DOMAINS = ["musculoskeletal", "bone", "cardiovascular"] as const;

/** Los indicadores que la sección lee: musculoesquelético, cardiovascular y ejercicio. */
export const GRAVITY_KEYS = [
  "dxa-lean-mass",
  "bmd-dxa-lumbar-spine",
  "bmd-dxa-hip",
  "imtp-peak-force",
  "grip-strength-right",
  "grip-strength-left",
  "ntx-telopeptide",
  "tandem-walk-correct-steps",
  "recovery-from-fall-time",
  "cognition-mpt-speed",
  "heart-rate",
  "systolic-bp",
  "diastolic-bp",
  "orthostatic-drop",
  "ijv-csa-right",
  "ijv-csa-left",
  "hematocrit",
  "vo2-peak",
  "exercise-minutes",
  "loading-impacts",
] as const;
export type GravityKey = (typeof GRAVITY_KEYS)[number];

export interface GravityData {
  home: HomeData;
  series: Fetched<Record<GravityKey, Reading[]>>;
  /** Las entidades Riesgo óseo y musculoesquelético: sus contramedidas de la biblioteca. */
  risks: Fetched<RiskEntity[]>;
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

/** Las peticiones de la sección. Oculta, no se pide nada; al volver, se relee con el estado. */
export function useGravityData(home: HomeData, active: boolean): GravityData {
  const { status } = home;
  const [series, setSeries] = useState<Fetched<Record<GravityKey, Reading[]>>>({ state: "loading" });
  const [risks, setRisks] = useState<Fetched<RiskEntity[]>>({ state: "loading" });
  const until = status.data.reference_time;

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    fetched(
      risksApi.get().then((body) => body.risks.filter((item) => item.risk_id === "bone" || item.risk_id === "musculoskeletal")),
      () => current,
      setRisks,
    );
    return () => {
      current = false;
    };
  }, [active]);

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    fetched(
      Promise.all(
        GRAVITY_KEYS.map((key) =>
          api.observations(key, 3000, status.subject, until).then((body) => [key, readingsOf(body.observations)] as const),
        ),
      ).then((pairs) => Object.fromEntries(pairs) as Record<GravityKey, Reading[]>),
      () => current,
      setSeries,
    );
    return () => {
      current = false;
    };
  }, [active, status.subject, until]);

  return { home, series, risks, links: undefined };
}

type Piece = { grav: GravityData };

function Pending({ item }: { item: Fetched<unknown> }) {
  if (item.state === "loading") return <Loading />;
  if (item.state === "failed") return <Unavailable outcome={item.outcome} />;
  return null;
}

function readingsFor(grav: GravityData, key: GravityKey): Reading[] {
  return grav.series.state === "ready" ? grav.series.value[key].filter((item) => item.at <= grav.home.reference) : [];
}

function indicatorOf(grav: GravityData, key: string): Indicator | undefined {
  return grav.home.catalog.get(key);
}

const SHORT: Record<string, string> = {
  "dxa-lean-mass": tr("Masa magra (DXA)", "Lean mass (DXA)"),
  "bmd-dxa-lumbar-spine": tr("Densidad ósea lumbar", "Lumbar bone density"),
  "bmd-dxa-hip": tr("Densidad ósea cadera", "Hip bone density"),
  "imtp-peak-force": tr("Fuerza (IMTP)", "Strength (IMTP)"),
  "grip-strength-right": tr("Prensión dcha.", "Grip, right"),
  "grip-strength-left": tr("Prensión izda.", "Grip, left"),
  "ntx-telopeptide": tr("Resorción (NTx)", "Resorption (NTx)"),
  "tandem-walk-correct-steps": tr("Equilibrio (marcha)", "Balance (gait)"),
  "cognition-mpt-speed": tr("Praxis motora (MPT)", "Motor praxis (MPT)"),
  "recovery-from-fall-time": tr("Levantarse del suelo", "Rising from the floor"),
  "heart-rate": tr("Frecuencia cardiaca", "Heart rate"),
  "systolic-bp": tr("Presión sistólica", "Systolic pressure"),
  "diastolic-bp": tr("Presión diastólica", "Diastolic pressure"),
  "orthostatic-drop": tr("Caída ortostática", "Orthostatic drop"),
  "ijv-csa-right": tr("Yugular dcha. (eco)", "Right jugular (ultrasound)"),
  "ijv-csa-left": tr("Yugular izda. (eco)", "Left jugular (ultrasound)"),
  hematocrit: tr("Hematocrito", "Hematocrit"),
  "vo2-peak": tr("VO2 pico", "Peak VO2"),
  "exercise-minutes": tr("Ejercicio resistivo", "Resistive exercise"),
  "loading-impacts": tr("Impactos de carga", "Loading impacts"),
};

const ICON: Record<string, PictogramName> = {
  "dxa-lean-mass": "domain-musculoskeletal",
  "bmd-dxa-lumbar-spine": "domain-bone",
  "bmd-dxa-hip": "domain-bone",
  "imtp-peak-force": "dumbbell",
  "grip-strength-right": "dumbbell",
  "grip-strength-left": "dumbbell",
  "ntx-telopeptide": "vial",
  "tandem-walk-correct-steps": "balance",
  "recovery-from-fall-time": "figure-dot",
  "heart-rate": "heart-pulse",
  "systolic-bp": "gauge",
  "diastolic-bp": "gauge",
  "orthostatic-drop": "arrow-down",
  "ijv-csa-right": "vessel-flow",
  "ijv-csa-left": "vessel-flow",
  hematocrit: "vessel-flow",
  "vo2-peak": "lungs",
  "exercise-minutes": "dumbbell",
  "loading-impacts": "wave-zigzag",
};

function fullName(grav: GravityData, key: string): string {
  return capitalized(indicatorOf(grav, key)?.display_es ?? key);
}

function nameOf(grav: GravityData, key: string): string {
  return SHORT[key] ?? fullName(grav, key);
}

function valueText(grav: GravityData, key: string, value: number): string {
  const indicator = indicatorOf(grav, key);
  const unit = indicator === undefined ? "" : displayUnit(indicator.unit);
  const number = formatNumber(value, indicator?.decimals ?? 1);
  return unit === "" ? number : `${number} ${unit}`;
}

function signed(fraction: number): string {
  const text = formatNumber(fraction * 100, 1);
  return `${fraction > 0 ? "+" : ""}${text} %`;
}

/**
 * El cambio de la última lectura frente a la primera de la misión, en tanto por uno. `null` con menos
 * de dos lecturas o una primera en cero. Descriptivo: no dice si es pérdida clínica.
 */
export function missionChange(readings: readonly Reading[]): number | null {
  const first = readings[0];
  const last = readings.at(-1);
  if (first === undefined || last === undefined || readings.length < 2 || first.value === 0) return null;
  return (last.value - first.value) / Math.abs(first.value);
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

function tint(level: string | null) {
  const token = levelToken(level ?? undefined);
  const shown = token === null ? "gray" : token === "text" ? "green" : token;
  return { "--lvl": `var(${cssVar(shown)})` } as CSSProperties;
}

/** El peor nivel de los dominios de la gravedad, o `null` si el estado no trae ninguno. */
function worstLevel(grav: GravityData): string | null {
  const levels = GRAVITY_DOMAINS.map((domain) => grav.home.status.domains[domain]?.level).filter(
    (level): level is string => level !== undefined && isLevel(level),
  );
  if (levels.length === 0) return null;
  return levels.reduce((worst, level) =>
    LEVEL_ORDER.indexOf(level as (typeof LEVEL_ORDER)[number]) > LEVEL_ORDER.indexOf(worst as (typeof LEVEL_ORDER)[number]) ? level : worst,
  );
}

// ---------------------------------------------------------------- campos gravitatorios

/**
 * La gravedad de superficie de cada entorno, en fracciones de la terrestre (NASA Planetary Fact
 * Sheet: Luna 1,62 m/s², Marte 3,71 m/s², Tierra 9,81 m/s²). Constantes físicas, no clínicas. La
 * de órbita es «microgravedad»: no se da una cifra, la maqueta escribía 0,01 sin fuente.
 */
export const FIELDS = [
  { id: "earth", label: tr("Tierra", "Earth"), value: 1, decimals: 2, match: /tierra|terrestre|earth/i },
  { id: "iss", label: tr("Órbita (ISS)", "Orbit (ISS)"), value: null, decimals: 2, match: /micro/i },
  { id: "moon", label: tr("Luna", "Moon"), value: 1.62 / 9.81, decimals: 3, match: /lun|moon/i },
  { id: "mars", label: tr("Marte", "Mars"), value: 3.71 / 9.81, decimals: 2, match: /marte|marcian|mars|martian/i },
] as const;

/** El entorno de la gravedad del momento (`mission.gravity_now`, texto libre de configuración). */
export function fieldOf(gravityNow: string): (typeof FIELDS)[number] | null {
  return FIELDS.find((field) => field.match.test(gravityNow)) ?? null;
}

function GravityValue({ field }: { field: (typeof FIELDS)[number] }) {
  return field.value === null ? <span>micro</span> : <span className="num">{formatNumber(field.value, field.decimals)}</span>;
}

// ---------------------------------------------------------------- fila 1

/** El título de la maqueta y el resumen de exposición: el régimen del momento y los días de misión. */
export function GravExposure({ grav }: Piece) {
  const { mission } = grav.home.status;
  const field = fieldOf(mission.gravity_now);
  const inFlight = mission.phase !== "preflight" && mission.phase !== "postflight";
  const day = Math.max(0, Math.floor(mission.mission_day));
  return (
    <section data-ui="grav-exposure" className="ref-card grav-exposure" aria-label={tr("Gravedad: salud gravitacional", "Gravity: gravitational health")}>
      <h2 className="iso-title grav-title">
        <Pictogram name="ridge-gravity" />
        <span>
          {tr("Gravedad: salud gravitacional (RIDGE)", "Gravity: gravitational health (RIDGE)")}
          <span className="secondary"> · {tr("datos a", "data as of")} {formatUtc(new Date(grav.home.reference))}</span>
        </span>
      </h2>
      <div className="grav-exposure-body">
        <div className="grav-gauge">
          <Ring done={field?.value === null || field === null ? 0 : Math.round(field.value * 100)} total={100} label={tr("de la gravedad terrestre", "of Earth gravity")}>
            {field === null ? <MarkOf mark={MISSING_MARK}>{tr("sin declarar", "not declared")}</MarkOf> : <strong>{field.value === null ? "micro" : formatNumber(field.value, field.decimals)}</strong>}
            <small>{field?.value === null ? tr("gravedad", "gravity") : "g"}</small>
          </Ring>
          <small className="secondary">{capitalized(mission.gravity_now)} {tr("(ahora)", "(now)")}</small>
        </div>
        <ul className="grav-fields-mini">
          {FIELDS.map((item) => {
            const here = field?.id === item.id;
            return (
              <li key={item.id} data-here={here ? "" : undefined}>
                <span className="grav-planet" data-field={item.id} aria-hidden="true" />
                <span>
                  {item.label} (<GravityValue field={item} />)
                </span>
                <span className="num">{here && inFlight ? `${formatNumber(day)} d` : "—"}</span>
              </li>
            );
          })}
          <li className="grav-total">
            <span />
            <span>{tr("Día de misión", "Mission day")}</span>
            <strong className="num">
              {formatNumber(day)} / {formatNumber(mission.duration_days)} d
            </strong>
          </li>
        </ul>
      </div>
    </section>
  );
}

/** La fase de misión del backend y lo que queda; sin adaptaciones estimadas. */
export function GravTransition({ grav }: Piece) {
  const { mission } = grav.home.status;
  const left = Math.max(0, mission.duration_days - mission.mission_day);
  return (
    <section data-ui="grav-transition" className="ref-card grav-transition" aria-label={tr("Fase y transición", "Phase and transition")}>
      <PanelTitle concept="missionDay" className="ref-h">
        {tr("Fase y transición", "Phase and transition")}
      </PanelTitle>
      <ol className="grav-phases">
        {mission.phases.map((phase) => (
          <li key={phase.key} data-now={phase.key === mission.phase ? "" : undefined}>
            <Pictogram name={phase.key === mission.phase ? "rocket" : "dot-small"} />
            <span>{capitalized(phase.display)}</span>
          </li>
        ))}
      </ol>
      <p className="grav-left">
        {tr("Quedan", "Remaining:")} <strong className="num">{formatNumber(Math.ceil(left))} d</strong> {tr("de misión", "of mission")}
      </p>
      <p className="secondary iso-note ref-clamp-2" title={mission.phase_basis}>
        {mission.phase_basis}
      </p>
    </section>
  );
}

/** El peor nivel de los dominios que la gravedad toca, y cada uno con el suyo. */
export function GravRisk({ grav }: Piece) {
  const worst = worstLevel(grav);
  const style = worst !== null ? levelStyle(worst) : null;
  const alerts = grav.home.status.alerts.filter((item) => (GRAVITY_DOMAINS as readonly string[]).includes(item.domain));
  return (
    <section data-ui="grav-risk" className="ref-card grav-risk" aria-label={tr("Estado de riesgo (gravedad)", "Risk status (gravity)")}>
      <PanelTitle concept="state" className="ref-h">
        {tr("Estado de riesgo (gravedad)", "Risk status (gravity)")}
      </PanelTitle>
      {worst === null ? (
        <MarkOf mark={UNAVAILABLE_MARK}>{tr("el estado no trae estos dominios", "the status does not include these domains")}</MarkOf>
      ) : (
        <>
          <div className="ref-level-now iso-hero" style={tint(worst)}>
            <span className="ref-hero-icon" aria-hidden="true">
              <Pictogram name={style?.pictogram ?? UNKNOWN_PICTOGRAM} />
            </span>
            <span>
              <strong>{style?.label ?? worst}</strong>
              <small>
                {formatNumber(alerts.length)} {alerts.length === 1 ? tr("alerta activa", "active alert") : tr("alertas activas", "active alerts")}
              </small>
            </span>
          </div>
          <ul className="grav-domains">
            {GRAVITY_DOMAINS.map((domain) => {
              const risk = grav.home.status.domains[domain];
              const level = risk?.level ?? null;
              const shown = level !== null && isLevel(level) ? levelStyle(level) : null;
              return (
                <li key={domain} style={tint(level)}>
                  <Pictogram name={`domain-${domain}` as PictogramName} />
                  <span className="ref-clamp" title={risk?.drivers.join(" · ")}>
                    {DOMAIN_LABEL[domain]}
                  </span>
                  <strong>{shown?.label ?? tr("sin dato", "no data")}</strong>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

const DOMAIN_LABEL: Record<(typeof GRAVITY_DOMAINS)[number], string> = {
  musculoskeletal: tr("Musculoesquelético", "Musculoskeletal"),
  bone: tr("Óseo", "Bone"),
  cardiovascular: "Cardiovascular",
};

// ---------------------------------------------------------------- cuerpos

const ReferenceBody = lazy(() => import("../dashboard/ReferenceBody"));

/** Un cuerpo de la maqueta en un estilo, con el dibujo de encima. Adorno (§2.5). */
function StyledBody({ look, label, children }: { look: "muscle" | "bone" | "vessels"; label: string; children?: ReactNode }) {
  return (
    <figure className="grav-figure" data-look={look}>
      <div className="grav-figure-box">
        <Suspense fallback={null}>
          <ReferenceBody look={look} switcher={false} />
        </Suspense>
        {children}
      </div>
      <figcaption className="secondary">{label}</figcaption>
    </figure>
  );
}

/** Una fila de medida: icono, nombre, última lectura y cambio en la misión. */
function MeasureRow({ grav, k, change = true }: { grav: GravityData; k: GravityKey; change?: boolean }) {
  const readings = readingsFor(grav, k);
  const last = readings.at(-1);
  const delta = missionChange(readings);
  return (
    <li data-series={k}>
      <Pictogram name={ICON[k] ?? "dot-small"} />
      <span className="ref-clamp" title={fullName(grav, k)}>
        {nameOf(grav, k)}
      </span>
      {last === undefined ? (
        <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
      ) : change && delta !== null ? (
        <strong
          className="num"
          data-tone={concerningChange(indicatorOf(grav, k), delta) ? "yellow" : undefined}
          title={tr(`Última: ${valueText(grav, k, last.value)}. Cambio frente a la primera lectura de la misión; descriptivo, no evalúa.`, `Latest: ${valueText(grav, k, last.value)}. Change from the first reading of the mission; descriptive, not an assessment.`)}
        >
          {signed(delta)}
        </strong>
      ) : (
        <strong className="num">{valueText(grav, k, last.value)}</strong>
      )}
    </li>
  );
}

// ---------------------------------------------------------------- fila 2

/** Musculoesquelético: medidas, el cuerpo en músculo y en hueso, y las zonas con densitometría. */
export function GravMusculo({ grav }: Piece) {
  const figure = useAvatar();
  const zones: { key: GravityKey; label: string; mark: "lumbar" | "hip" }[] = [
    { key: "bmd-dxa-lumbar-spine", label: tr("Columna lumbar", "Lumbar spine"), mark: "lumbar" },
    { key: "bmd-dxa-hip", label: tr("Cadera", "Hip"), mark: "hip" },
  ];
  // «Detalle / visualización» de la maqueta: qué capas se ven. Presentación pura, sin guardar.
  const [show, setShow] = useState({ muscle: true, bone: true, sites: true });
  const marks = show.sites ? zones.filter((zone) => readingsFor(grav, zone.key).length > 0).map((zone) => zone.mark) : [];
  const toggle = (key: keyof typeof show) => setShow((now) => ({ ...now, [key]: !now[key] }));
  return (
    <section data-ui="grav-musculo" className="ref-card grav-musculo" aria-label={tr("Sistema musculoesquelético", "Musculoskeletal system")}>
      <PanelTitle concept="body" className="ref-h">
        {tr("Sistema musculoesquelético", "Musculoskeletal system")}
      </PanelTitle>
      {grav.series.state !== "ready" ? (
        <Pending item={grav.series} />
      ) : (
        <div className="grav-musculo-body">
          <ul className="iso-latest grav-list">
            {(["dxa-lean-mass", "bmd-dxa-lumbar-spine", "imtp-peak-force", "grip-strength-right", "ntx-telopeptide", "loading-impacts"] as const).map((k) => (
              <MeasureRow key={k} grav={grav} k={k} change={k !== "loading-impacts" && k !== "ntx-telopeptide"} />
            ))}
          </ul>
          {show.muscle && (
            <StyledBody look="muscle" label={tr("Músculo", "Muscle")}>
              <BodyMuscleArt figure={figure} />
            </StyledBody>
          )}
          {show.bone && (
            <StyledBody look="bone" label={tr("Esqueleto", "Skeleton")}>
              <BodyBonesArt figure={figure} marks={marks} />
            </StyledBody>
          )}
          <div className="grav-zones">
            <h3 className="grav-sub">{tr("Zonas con densitometría", "Sites with densitometry")}</h3>
            <ul>
              {zones.map((zone) => {
                const readings = readingsFor(grav, zone.key);
                const delta = missionChange(readings);
                return (
                  <li key={zone.key}>
                    <span>{zone.label}</span>
                    {readings.length === 0 ? (
                      <MarkOf mark={MISSING_MARK}>{tr("sin medida", "no measurement")}</MarkOf>
                    ) : delta === null ? (
                      <strong className="num">{valueText(grav, zone.key, readings.at(-1)!.value)}</strong>
                    ) : (
                      <>
                        <ImpactBar share={Math.min(1, Math.abs(delta) * 10)} concerning={delta < 0} />
                        <strong className="num">{signed(delta)}</strong>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
            <fieldset className="grav-layers">
              <legend className="grav-sub">{tr("Detalle / visualización", "Detail / display")}</legend>
              {(
                [
                  ["muscle", tr("Músculos", "Muscles")],
                  ["bone", tr("Esqueleto", "Skeleton")],
                  ["sites", tr("Densidad ósea (DXA)", "Bone density (DXA)")],
                ] as const
              ).map(([key, label]) => (
                <label key={key}>
                  <input type="checkbox" checked={show[key]} onChange={() => toggle(key)} />
                  <span>{label}</span>
                </label>
              ))}
            </fieldset>
            <AvatarSwitch className="grav-avatar" />
            <p className="secondary iso-note" title={tr("Los anillos del esqueleto marcan dónde hay medida de densitometría, no cómo está.", "The rings on the skeleton mark where there is a densitometry measurement, not its condition.")}>
              {tr("Los anillos marcan dónde hay medida, no cómo está.", "The rings mark where there is a measurement, not its condition.")}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

/** Cardiovascular y fluidos: el holograma de vasos, las medidas y la curva de la yugular u ortostatismo. */
export function GravCardio({ grav }: Piece) {
  const figure = useAvatar();
  const sys = readingsFor(grav, "systolic-bp").at(-1);
  const dia = readingsFor(grav, "diastolic-bp").at(-1);
  const chart = (["ijv-csa-right", "ijv-csa-left", "orthostatic-drop", "heart-rate"] as const)
    .filter((k) => readingsFor(grav, k).length > 1)
    .slice(0, 2);
  return (
    <section data-ui="grav-cardio" className="ref-card grav-cardio" aria-label={tr("Sistema cardiovascular y fluidos", "Cardiovascular system and fluids")}>
      <PanelTitle concept="measured" className="ref-h">
        {tr("Sistema cardiovascular y fluidos", "Cardiovascular system and fluids")}
      </PanelTitle>
      {grav.series.state !== "ready" ? (
        <Pending item={grav.series} />
      ) : (
        <div className="grav-cardio-body">
          <StyledBody look="vessels" label={tr("Circulación", "Circulation")}>
            <BodyVesselsArt figure={figure} />
          </StyledBody>
          <div className="grav-cardio-side">
            <ul className="iso-latest grav-list">
              <MeasureRow grav={grav} k="heart-rate" change={false} />
              <li data-series="systolic-bp">
                <Pictogram name="gauge" />
                <span>{tr("Presión arterial", "Blood pressure")}</span>
                {sys === undefined || dia === undefined ? (
                  <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
                ) : (
                  <strong className="num">
                    {formatNumber(sys.value, indicatorOf(grav, "systolic-bp")?.decimals ?? 0)} / {valueText(grav, "diastolic-bp", dia.value)}
                  </strong>
                )}
              </li>
              <MeasureRow grav={grav} k="orthostatic-drop" change={false} />
              <MeasureRow grav={grav} k="ijv-csa-right" change={false} />
              <MeasureRow grav={grav} k="hematocrit" change={false} />
              <MeasureRow grav={grav} k="vo2-peak" change={false} />
            </ul>
            <div className="grav-chart">
              <h3 className="grav-sub">
                {chart.some((k) => k.startsWith("ijv")) ? tr("Desplazamiento de fluidos (yugular, eco)", "Fluid shift (jugular, ultrasound)") : tr(`Ortostatismo y frecuencia (${formatNumber(TREND_DAYS)} días)`, `Orthostatic response and heart rate (${formatNumber(TREND_DAYS)} days)`)}
              </h3>
              {chart.length === 0 ? (
                <MarkOf mark={MISSING_MARK}>{tr("sin lecturas suficientes", "not enough readings")}</MarkOf>
              ) : (
                <MultiTrend
                  series={chart.map((k) => ({ key: k, label: nameOf(grav, k), readings: dailyMeans(readingsFor(grav, k), grav.home.reference, TREND_DAYS) }))}
                  until={grav.home.reference}
                  days={TREND_DAYS}
                />
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

/** Las pruebas de la maqueta que EMMA tiene en su catálogo, con la edad de la última. */
export function GravTests({ grav, links }: Piece & { links: HomeLinks | undefined }) {
  const tests: GravityKey[] = [
    "imtp-peak-force",
    "grip-strength-right",
    "bmd-dxa-lumbar-spine",
    "dxa-lean-mass",
    "tandem-walk-correct-steps",
    "recovery-from-fall-time",
    "orthostatic-drop",
    "ijv-csa-right",
    "vo2-peak",
  ];
  return (
    <section data-ui="grav-tests" className="ref-card grav-tests" aria-label={tr("Pruebas y evaluaciones", "Tests and assessments")}>
      <PanelTitle concept="measure" className="ref-h">
        {tr("Pruebas y evaluaciones", "Tests and assessments")}
      </PanelTitle>
      {grav.series.state !== "ready" ? (
        <Pending item={grav.series} />
      ) : (
        <ul className="grav-checks">
          {tests.map((k) => {
            const last = readingsFor(grav, k).at(-1);
            return (
              <li key={k} data-done={last !== undefined ? "" : undefined}>
                <Pictogram name={last !== undefined ? "check" : "square-outline"} />
                <span className="ref-clamp" title={fullName(grav, k)}>
                  {nameOf(grav, k)}
                </span>
                {last === undefined ? (
                  <MarkOf mark={MISSING_MARK}>{tr("sin hacer", "not done")}</MarkOf>
                ) : (
                  <span className="num secondary">{tr(`hace ${formatAge(Math.max(0, (grav.home.reference - last.at) / 60000))}`, `${formatAge(Math.max(0, (grav.home.reference - last.at) / 60000))} ago`)}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <GoLinks links={links} />
    </section>
  );
}

/** «Ver pruebas / resultados» y «Plan de contramedidas» de la maqueta: abren las secciones que ya lo tienen. */
function GoLinks({ links }: { links: HomeLinks | undefined }) {
  const go = [
    { link: sectionLink(links, "log"), text: tr("Ver pruebas / resultados", "View tests / results"), icon: "chart-line" as const },
    { link: sectionLink(links, "library"), text: tr("Plan de contramedidas", "Countermeasures plan"), icon: "dumbbell" as const },
  ].filter((item): item is { link: NonNullable<ReturnType<typeof sectionLink>>; text: string; icon: "chart-line" | "dumbbell" } => item.link !== null);
  if (go.length === 0) return null;
  return (
    <div className="grav-go">
      {go.map((item) => (
        <Command key={item.text} concept="detail" type="button" onClick={item.link.open} aria-label={tr(`Abrir ${item.link.name}: ${item.text}`, `Open ${item.link.name}: ${item.text}`)}>
          <Pictogram name={item.icon} />
          <span>{item.text}</span>
        </Command>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- fila 3

/** En lugar de «gamificación»: la constancia del ejercicio, con lo medido. Sin puntos ni retos. */
export function GravTraining({ grav }: Piece) {
  const { reference } = grav.home;
  const exercise = readingsFor(grav, "exercise-minutes");
  const impacts = readingsFor(grav, "loading-impacts");
  const daysWith = Array.from({ length: 7 }, (_, index) => windowMean(exercise.filter((item) => item.value > 0), reference - index * DAY_MS, 1)).filter(
    (mean) => mean !== null,
  ).length;
  const streak = streakDays(
    exercise.filter((item) => item.value > 0),
    reference,
  );
  const mean = windowMean(exercise, reference, 7);
  const impactMean = windowMean(impacts, reference, 7);
  return (
    <section data-ui="grav-training" className="ref-card grav-training" aria-label={tr("Entrenamiento y constancia", "Training and consistency")}>
      <PanelTitle concept="routines" className="ref-h">
        {tr("Entrenamiento: constancia", "Training: consistency")}
      </PanelTitle>
      {grav.series.state !== "ready" ? (
        <Pending item={grav.series} />
      ) : (
        <div className="grav-training-body">
          <div className="grav-training-progress">
            <span>
              {tr("Días con ejercicio (7 d):", "Days with exercise (7 d):")} <strong className="num">{formatNumber(daysWith)}/7</strong>
            </span>
            <ImpactBar share={daysWith / 7} />
          </div>
          <ul className="grav-badges">
            <li>
              <Pictogram name="dumbbell" />
              <span>{tr("Racha", "Streak")}</span>
              <strong className="num">{formatNumber(streak)} d</strong>
            </li>
            <li>
              <Pictogram name="stopwatch" />
              <span>{tr("Ejercicio (media 7 d)", "Exercise (7 d mean)")}</span>
              <strong className="num">{mean === null ? "—" : valueText(grav, "exercise-minutes", mean)}</strong>
            </li>
            <li>
              <Pictogram name="wave-zigzag" />
              <span>{tr("Impactos (media 7 d)", "Impacts (7 d mean)")}</span>
              <strong className="num">{impactMean === null ? "—" : valueText(grav, "loading-impacts", impactMean)}</strong>
            </li>
          </ul>
          <p className="secondary iso-note">{tr("Sin puntos ni retos: los días y medias son las lecturas del catálogo.", "No points or challenges: the days and means are the catalog readings.")}</p>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- fila 4

/** La comparativa de campos: constantes físicas y la exposición de esta misión donde toca. */
export function GravFields({ grav }: Piece) {
  const { mission } = grav.home.status;
  const field = fieldOf(mission.gravity_now);
  const inFlight = mission.phase !== "preflight" && mission.phase !== "postflight";
  return (
    <section data-ui="grav-fields" className="ref-card grav-fields" aria-label={tr("Comparativa de campos gravitatorios", "Gravity field comparison")}>
      <PanelTitle concept="compare" className="ref-h">
        {tr("Comparativa de campos gravitatorios", "Gravity field comparison")}
      </PanelTitle>
      <table className="grav-table">
        <thead>
          <tr>
            <th scope="col">{tr("Entorno", "Environment")}</th>
            <th scope="col">{tr("Gravedad (g)", "Gravity (g)")}</th>
            <th scope="col">{tr("Exposición (d)", "Exposure (d)")}</th>
          </tr>
        </thead>
        <tbody>
          {FIELDS.map((item) => (
            <tr key={item.id} data-here={field?.id === item.id ? "" : undefined}>
              <th scope="row">
                <span className="grav-planet" data-field={item.id} aria-hidden="true" />
                {item.label}
              </th>
              <td>
                <GravityValue field={item} />
              </td>
              <td className="num">{field?.id === item.id && inFlight ? formatNumber(Math.floor(mission.mission_day)) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="secondary iso-note">{tr("Gravedad de superficie (NASA Planetary Fact Sheet). Exposición: solo esta misión.", "Surface gravity (NASA Planetary Fact Sheet). Exposure: this mission only.")}</p>
    </section>
  );
}

/**
 * Los riesgos de la transición con el patrón de la maqueta: pérdida de equilibrio, coordinación
 * mano-ojo y mareo espacial. Cada fila nombra el riesgo, no la prueba; la prueba que lo mide va en el
 * título emergente. Donde la maqueta escribía «12 eventos −40 %», aquí van las lecturas de la misión y
 * el cambio de la última frente a la primera, descriptivo. El mareo no tiene indicador en el catálogo
 * y se dice así (gris, «no disponible»), sin cifra.
 */
export const TRANSITION_RISKS: readonly { id: string; label: string; icon: PictogramName; key: GravityKey | null; measuredBy: string }[] = [
  { id: "balance", label: tr("Pérdida de equilibrio", "Loss of balance"), icon: "balance", key: "tandem-walk-correct-steps", measuredBy: tr("Se mide con la marcha en tándem (pasos correctos).", "Measured with the tandem walk (correct steps).") },
  { id: "hand-eye", label: tr("Coordinación mano-ojo", "Hand-eye coordination"), icon: "figure-dot", key: "cognition-mpt-speed", measuredBy: tr("Se mide con la praxis motora (MPT) de la batería Cognition: velocidad.", "Measured with the motor praxis task (MPT) of the Cognition battery: speed.") },
  { id: "motion-sickness", label: tr("Mareo espacial", "Space motion sickness"), icon: "wave-zigzag", key: null, measuredBy: tr("El catálogo de EMMA no tiene indicador de mareo espacial.", "The EMMA catalog has no space motion sickness indicator.") },
];

export function GravTransitionRisks({ grav }: Piece) {
  const charted = TRANSITION_RISKS.filter((risk): risk is (typeof TRANSITION_RISKS)[number] & { key: GravityKey } => risk.key !== null && readingsFor(grav, risk.key).length > 1);
  return (
    <section data-ui="grav-transition-risks" className="ref-card grav-transition-risks" aria-label={tr("Riesgos por transición", "Transition risks")}>
      <PanelTitle concept="risks" className="ref-h">
        {tr("Riesgos por transición", "Transition risks")}
      </PanelTitle>
      {grav.series.state !== "ready" ? (
        <Pending item={grav.series} />
      ) : (
        <>
          <ul className="iso-latest grav-list grav-risk-rows">
            {TRANSITION_RISKS.map((risk) => {
              const readings = risk.key === null ? [] : readingsFor(grav, risk.key);
              const delta = missionChange(readings);
              return (
                <li key={risk.id} data-risk={risk.id} title={risk.measuredBy}>
                  <Pictogram name={risk.icon} />
                  <span className="ref-clamp">{risk.label}</span>
                  {risk.key === null ? (
                    <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin indicador", "no indicator")}</MarkOf>
                  ) : readings.length === 0 ? (
                    <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
                  ) : (
                    <>
                      <span className="num secondary">
                        {formatNumber(readings.length)} {readings.length === 1 ? tr("lectura", "reading") : tr("lecturas", "readings")}
                      </span>
                      {delta === null ? (
                        <strong className="num">{valueText(grav, risk.key, readings.at(-1)!.value)}</strong>
                      ) : (
                        <strong
                          className="num"
                          data-tone={concerningChange(indicatorOf(grav, risk.key), delta) ? "yellow" : undefined}
                          title={tr(`Última: ${valueText(grav, risk.key, readings.at(-1)!.value)}. Cambio frente a la primera lectura de la misión; descriptivo, no evalúa.`, `Latest: ${valueText(grav, risk.key, readings.at(-1)!.value)}. Change from the first reading of the mission; descriptive, not an assessment.`)}
                        >
                          {signed(delta)}
                        </strong>
                      )}
                    </>
                  )}
                </li>
              );
            })}
          </ul>
          {charted.length === 0 ? (
            <MarkOf mark={MISSING_MARK}>{tr("sin lecturas para la curva", "no readings for the curve")}</MarkOf>
          ) : (
            <MultiTrend
              series={charted.map((risk) => ({ key: risk.key, label: risk.label, readings: dailyMeans(readingsFor(grav, risk.key), grav.home.reference, TREND_DAYS) }))}
              until={grav.home.reference}
              days={TREND_DAYS}
            />
          )}
        </>
      )}
    </section>
  );
}

/** La extrapolación de tendencia del backend para los indicadores de la sección. */
export function GravPrediction({ grav }: Piece) {
  const items = grav.home.status.predictions.filter((item) => (GRAVITY_KEYS as readonly string[]).includes(item.key));
  return (
    <section data-ui="grav-prediction" className="ref-card grav-prediction" aria-label={tr("Simulación y predicción", "Simulation and prediction")}>
      <PanelTitle concept="predictions" className="ref-h">
        {tr("Simulación / predicción", "Simulation / prediction")}
      </PanelTitle>
      {items.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={MISSING_MARK}>{tr("Sin extrapolaciones para estos indicadores.", "No extrapolations for these indicators.")}</MarkOf>
        </p>
      ) : (
        <ul className="iso-latest grav-list">
          {items.slice(0, 5).map((item) => (
            <li key={item.key} title={item.basis}>
              <Pictogram name={ICON[item.key] ?? "chart-line"} />
              <span className="ref-clamp">
                {nameOf(grav, item.key)} (+{formatNumber(item.horizon_weeks)} {tr("sem", "wk")})
              </span>
              <strong className="num" data-tone={item.concerning ? "yellow" : undefined}>
                {item.projected_change > 0 ? "+" : ""}
                {formatNumber(item.projected_change, item.decimals)} {displayUnit(item.unit)}
              </strong>
            </li>
          ))}
        </ul>
      )}
      <p className="secondary iso-note ref-clamp-2" title={items[0]?.basis}>
        {items[0]?.basis ?? tr("Extrapolación lineal de la tendencia; no es un pronóstico clínico.", "Linear extrapolation of the trend; not a clinical forecast.")}
      </p>
    </section>
  );
}

/** Las recomendaciones del backend para estos dominios; sin ninguna, las contramedidas de la biblioteca. */
export function GravExercises({ grav }: Piece) {
  const items = grav.home.status.recommendations.filter((item) => (GRAVITY_DOMAINS as readonly string[]).includes(item.domain));
  const library = grav.risks.state === "ready" ? grav.risks.value.flatMap((risk) => risk.countermeasures.items) : [];
  return (
    <section data-ui="grav-exercises" className="ref-card grav-exercises" aria-label={tr("Ejercicios y contramedidas", "Exercises and countermeasures")}>
      <PanelTitle concept="recommendations" className="ref-h">
        {items.length > 0 ? tr("Recomendaciones (EMMA)", "Recommendations (EMMA)") : tr("Contramedidas (biblioteca)", "Countermeasures (library)")}
      </PanelTitle>
      {items.length > 0 ? (
        <ul className="iso-checks">
          {items.slice(0, 5).map((item) => (
            <li key={`${item.action}-${item.urgency}`} title={item.rationale}>
              <Pictogram name="check" />
              <span className="ref-clamp">{item.action}</span>
            </li>
          ))}
        </ul>
      ) : grav.risks.state !== "ready" ? (
        <Pending item={grav.risks} />
      ) : library.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={OK_MARK}>{tr("Sin recomendaciones: nada requiere acción.", "No recommendations: nothing requires action.")}</MarkOf>
        </p>
      ) : (
        <ul className="iso-checks grav-cm-rows">
          {library.slice(0, 5).map((item) => (
            <li key={item.id} title={[item.action, item.basis_display, item.trigger_display].filter(Boolean).join(" · ")}>
              <Pictogram name="dumbbell" />
              <span className="ref-clamp">{item.action}</span>
              {item.family_display !== null && <span className="secondary grav-cm-family ref-clamp">{capitalized(item.family_display)}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Todas las piezas, en el orden de la rejilla. `CrewConsole` las monta tras la ubicación de «Inicio». */
export function gravityPanels(grav: GravityData, active: boolean, links: HomeLinks | undefined): ReactNode[] {
  const home = grav.home;
  return [
    <NodesFit active={active} fixed />,
    <GravExposure grav={grav} />,
    <GravTransition grav={grav} />,
    <HomeCrew home={home} links={links} />,
    <GravRisk grav={grav} />,
    <GravMusculo grav={grav} />,
    <GravCardio grav={grav} />,
    <GravTests grav={grav} links={links} />,
    <HomeQuickHazards home={home} links={links} />,
    <GravTraining grav={grav} />,
    <GravFields grav={grav} />,
    <GravTransitionRisks grav={grav} />,
    <GravPrediction grav={grav} />,
    <GravExercises grav={grav} />,
  ];
}
