import { type CSSProperties, type ReactNode, Suspense, lazy, useEffect, useState } from "react";

import { AdoptControls, type BoardDecisions, BoardOperator } from "../components/AdoptControls";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { FoldDivider, Folded, setFoldOpen } from "../components/SecondaryFold";
import { Loading, Unavailable } from "../components/Unavailable";
import { Pictogram } from "../icons";
import {
  type CrewRadiation,
  type FhirObservation,
  type ImmRadiation,
  type MissionHistory,
  type RiskEntity,
  type SpaceWeatherSeries,
  type SpaceWeatherSeriesBlock,
  api,
  crewRadiationApi,
  immRadiationApi,
  risksApi,
  spaceWeatherSeriesApi,
} from "../lib/api";
import { displayUnit, formatAge, formatDay, formatNumber, formatUtc } from "../lib/format";
import { tr } from "../lib/i18n";
import { LEVEL_ORDER, isLevel, levelStyle } from "../lib/levels";
import { LOADING_MARK, MISSING_MARK, OK_MARK, UNAVAILABLE_MARK, UNKNOWN_PICTOGRAM, requestOutcome } from "../lib/marks";
import { type Token, cssVar } from "../lib/palette";
import { uiPictogram } from "../lib/uiMarks";
import { type Fetched, type HomeData, type HomeLinks, letterOf, sectionLink } from "../dashboard/HomeBoard";
import { LabArt, PlanetThumb, RouteArt, ShipArt, SpectrumWave } from "../dashboard/HomeArt";
import { RegionFigure } from "../dashboard/RegionPopover";
import { Ring, type Reading, Segments, Sparkline, levelToken } from "../dashboard/HomeCharts";
import { capitalized } from "../dashboard/HazardCards";
import "../dashboard/referenceDashboard.css";
import "./radiationBoard.css";

/**
 * La sección «Radiación»: la maqueta «Panel EMMA: Radiación y Salud Espacial» (2026-11-14) con el
 * estilo del tablero «Inicio» (petición del usuario, 2026-11-14: «intégrala respetando el estilo de
 * Inicio»). Las mismas tarjetas (`ref-card`, `ref-frame`), la misma rejilla de 12 columnas y los
 * mismos dibujos; cada pieza lee lo que el backend ya sirve.
 *
 * Lo que NO se copió de la maqueta, a propósito (invariantes 5-7 de `CLAUDE.md`):
 * - Sin cifras inventadas. La maqueta ponía dosis por ubicación (≈0,3-0,6 mSv/día en la ISS…),
 *   límites de 250/500 mSv, una dosis de 92 mSv, un pronóstico de 72 h con índice Kp y un historial
 *   de misiones. Aquí: la dosis de misión del estado (inferida, con su Q medido en vuelo), el límite
 *   de carrera de NASA-STD-3001 con su fuente, los límites a corto plazo de la Tabla 4.8-1, la
 *   proyección PREDICHA del backend, el historial declarado del tripulante y las series de iSWA.
 *   EMMA no tiene pronóstico propio: la meteorología espacial es la observada en las últimas 24 h.
 * - Sin texto clínico redactado aquí: los efectos, las contramedidas, los equipos y la detección
 *   son las frases de la entidad Riesgo (`GET /api/risks`), con su ficha.
 * - El espectro electromagnético es un dibujo de orden y nombres, sin cifras de frecuencia: la
 *   dosis del espacio es de partículas (protones e iones), que no están en ese espectro, y se dice.
 *
 * COLORES DE ADORNO: los del espectro, los planetas y los acentos de tarjeta son los de «Inicio» y
 * no significan nada (§2.5 de `compliance/hmi-state-of-the-art.md`). Lo que es dato (nivel, marcas
 * de lo que falta o falló) conserva su color, su forma y su palabra.
 */

/** Nombre corto de rótulo por perfil, el mismo de «Inicio»; el del backend va en `title`. */
const PROFILE_SHORT: Record<string, string> = {
  leo: tr("Órbita baja", "Low Earth orbit"),
  cislunar: "Cislunar",
  "lunar-surface": tr("Luna", "Moon"),
  "mars-transit": tr("Tránsito a Marte", "Mars transit"),
  "mars-surface": tr("Marte", "Mars"),
};

/** Las bandas del espectro, de más a menos energía. Solo nombres y orden: nada se mide aquí. */
const SPECTRUM = [
  { key: "gamma", label: tr("Rayos gamma", "Gamma rays"), glyph: "γ", ionizing: true },
  { key: "x", label: tr("Rayos X", "X-rays"), glyph: "X", ionizing: true },
  { key: "uv", label: tr("Ultravioleta", "Ultraviolet"), glyph: "UV", ionizing: null },
  { key: "visible", label: "Visible", glyph: "VIS", ionizing: false },
  { key: "ir", label: tr("Infrarrojo", "Infrared"), glyph: "IR", ionizing: false },
  { key: "micro", label: tr("Microondas", "Microwaves"), glyph: "MW", ionizing: false },
  { key: "radio", label: "Radio", glyph: "RF", ionizing: false },
] as const;

const RADIATION = "radiation";
const DAY_MS = 24 * 3600 * 1000;

// El cuerpo de la maqueta (pesado) se trae al abrir la sección, como en «Inicio».
const ReferenceBody = lazy(() => import("../dashboard/ReferenceBody"));

/** Lo que la sección pide aparte del estado, una vez para todas sus piezas. */
export interface RadiationData {
  home: HomeData;
  weather: Fetched<SpaceWeatherSeries>;
  crew: Fetched<CrewRadiation>;
  history: Fetched<MissionHistory>;
  risk: Fetched<RiskEntity | null>;
  doseRate: Fetched<Reading[]>;
  /** Lo que publica el IMM de NASA sobre radiación, con la misión a la que se asimila cada perfil. */
  imm: Fetched<ImmRadiation>;
  /** La última lectura de cada indicador del riesgo (su instante), o `null` si no tiene ninguna. */
  latest: Fetched<Record<string, string | null>>;
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

/**
 * Las peticiones de la sección. Oculta, no se pide nada; al volver, se relee. La serie de iSWA y la
 * entidad Riesgo no dependen del tripulante; la tasa de dosis, la tripulación y el historial, sí.
 */
export function useRadiationData(home: HomeData, active: boolean): RadiationData {
  const { status } = home;
  const [weather, setWeather] = useState<Fetched<SpaceWeatherSeries>>({ state: "loading" });
  const [crew, setCrew] = useState<Fetched<CrewRadiation>>({ state: "loading" });
  const [history, setHistory] = useState<Fetched<MissionHistory>>({ state: "loading" });
  const [risk, setRisk] = useState<Fetched<RiskEntity | null>>({ state: "loading" });
  const [doseRate, setDoseRate] = useState<Fetched<Reading[]>>({ state: "loading" });
  const [imm, setImm] = useState<Fetched<ImmRadiation>>({ state: "loading" });
  const [latest, setLatest] = useState<Fetched<Record<string, string | null>>>({ state: "loading" });
  const riskKeys = risk.state === "ready" && risk.value !== null ? risk.value.indicators.map((item) => item.key).join(",") : null;

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    const alive = () => current;
    fetched(spaceWeatherSeriesApi.get(24), alive, setWeather);
    fetched(
      risksApi.get().then((body) => body.risks.find((item) => item.risk_id === RADIATION) ?? null),
      alive,
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
    fetched(crewRadiationApi.get(), alive, setCrew);
    // El perfil declarado puede cambiar con el estado: se relee con él.
    fetched(immRadiationApi.get(), alive, setImm);
    fetched(api.missionHistory(status.subject), alive, setHistory);
    fetched(
      api.observations("absorbed-dose-rate", 600, status.subject).then((body) => readingsOf(body.observations)),
      alive,
      setDoseRate,
    );
    return () => {
      current = false;
    };
  }, [active, status.subject, status.data.reference_time]);

  // Una lectura por indicador basta para saber si se ha medido y cuándo; se pide al llegar el riesgo.
  useEffect(() => {
    if (!active || riskKeys === null) return undefined;
    let current = true;
    const keys = riskKeys === "" ? [] : riskKeys.split(",");
    fetched(
      Promise.all(
        keys.map((key) =>
          api.observations(key, 1, status.subject).then((body) => [key, body.observations[0]?.effectiveDateTime ?? null] as const),
        ),
      ).then((pairs) => Object.fromEntries(pairs)),
      () => current,
      setLatest,
    );
    return () => {
      current = false;
    };
  }, [active, riskKeys, status.subject, status.data.reference_time]);

  return { home, weather, crew, history, risk, doseRate, imm, latest };
}

type Piece = { rad: RadiationData };

/** Lo que una petición enseña mientras no está: cargando, o cómo falló. Lista, nada. */
function Pending({ item }: { item: Fetched<unknown> }) {
  if (item.state === "loading") return <Loading />;
  if (item.state === "failed") return <Unavailable outcome={item.outcome} />;
  return null;
}

/** El token con que «Inicio» pinta un nivel: el sin color de alerta, en verde (adorno declarado). */
function shownTone(level: string | undefined): Token {
  const token = levelToken(level);
  return token === null ? "gray" : token === "text" ? "green" : token;
}

function tint(level: string | undefined): CSSProperties {
  return { "--lvl": `var(${cssVar(shownTone(level))})` } as CSSProperties;
}

function ageOf(seconds: number | null | undefined): string | null {
  return seconds === null || seconds === undefined ? null : formatAge(seconds / 60);
}

function utc(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : formatUtc(at);
}

/** Una serie de iSWA con su canal, como lecturas; vacía si no está disponible. */
function seriesReadings(block: SpaceWeatherSeriesBlock | undefined, channel: string): Reading[] {
  if (block === undefined || !block.available) return [];
  return block.samples
    .map((row) => ({ at: Date.parse(row.time), value: row[channel] }))
    .filter((item): item is Reading => Number.isFinite(item.at) && typeof item.value === "number" && Number.isFinite(item.value));
}

function latestOf(block: SpaceWeatherSeriesBlock | undefined, channel: string): number | null {
  if (block === undefined || !block.available || block.latest === null) return null;
  const value = block.latest[channel];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function unitOf(block: SpaceWeatherSeriesBlock | undefined, channel: string): string {
  if (block === undefined || !block.available) return "";
  return block.channels.find((item) => item.name === channel)?.unit ?? "";
}

/** El nivel de radiación del estado, o `null` si el backend no da ese dominio. */
function radiationLevel(rad: RadiationData): string | null {
  return rad.home.status.domains[RADIATION]?.level ?? null;
}

// ---------------------------------------------------------------- fila 2: espectro, fuentes, estado

/** El espectro electromagnético: orden y nombres, con la frontera de lo ionizante. Sin cifras. */
export function RadSpectrum() {
  return (
    <section data-ui="rad-spectrum" className="ref-card rad-spectrum" data-acc="radiation" aria-label={tr("Espectro electromagnético", "Electromagnetic spectrum")}>
      <PanelTitle concept="radiation" className="ref-h">
        {tr("Espectro electromagnético y tipos de radiación", "Electromagnetic spectrum and radiation types")}
      </PanelTitle>
      <div className="rad-split" aria-hidden="true">
        <span className="rad-ionizing">
          {tr("Ionizante", "Ionizing")} <small>{tr("(alta energía)", "(high energy)")}</small>
        </span>
        <span className="rad-nonionizing">
          {tr("No ionizante", "Non-ionizing")} <small>{tr("(baja energía)", "(low energy)")}</small>
        </span>
      </div>
      <ul className="rad-bands" aria-label={tr("Bandas, de más a menos energía", "Bands, from highest to lowest energy")}>
        {SPECTRUM.map((band) => (
          <li key={band.key} data-band={band.key} data-ionizing={band.ionizing === null ? "partly" : String(band.ionizing)}>
            <span className="rad-band-glyph" aria-hidden="true">
              {band.glyph}
            </span>
            <span className="rad-band-name">{band.label}</span>
          </li>
        ))}
      </ul>
      <SpectrumWave />
      <p className="rad-axis secondary">
        <span>{tr("Más energía y frecuencia", "Higher energy and frequency")}</span>
        <span>{tr("Más longitud de onda", "Longer wavelength")}</span>
      </p>
      <p className="ref-clamp secondary">
        {tr(
          "La dosis que EMMA sigue en el espacio es de partículas (protones e iones), que no están en este espectro: ver «Otras fuentes» y «Dosimetría».",
          "The dose EMMA tracks in space comes from particles (protons and ions), which are not on this spectrum: see “Other sources” and “Dosimetry”.",
        )}
      </p>
    </section>
  );
}


/** Otras fuentes: el evento solar de DONKI, el ciclo solar y el aviso a bordo, con sus frases. */
export function RadSources({ rad }: Piece) {
  const { status } = rad.home;
  const solar = rad.crew.state === "ready" ? rad.crew.value.solar_event : null;
  const cycle = status.radiation.solar_cycle;
  const onboard = status.radiation.acute.onboard_warning;
  return (
    <section data-ui="rad-sources" className="ref-card rad-sources" aria-label={tr("Otras fuentes relevantes", "Other relevant sources")}>
      <PanelTitle concept="source" className="ref-h">
        {tr("Otras fuentes relevantes", "Other relevant sources")}
      </PanelTitle>
      <ul className="rad-source-list">
        <li>
          <span className="rad-source-art" data-art="sun" aria-hidden="true" />
          <span>
            <strong>{solar?.display ?? tr("Partículas solares (SEP)", "Solar particles (SEP)")}</strong>
            {solar === null ? (
              <Pending item={rad.crew} />
            ) : (
              <Mark
                pictogram={solar.state === "unavailable" ? MISSING_MARK.pictogram : solar.state === "active" ? "shape-triangle" : OK_MARK.pictogram}
                color={solar.state === "unavailable" ? MISSING_MARK.color : solar.state === "active" ? "yellow" : OK_MARK.color}
              >
                <span className="ref-clamp-2" title={solar.text}>
                  {solar.text}
                </span>
              </Mark>
            )}
          </span>
        </li>
        <li>
          <span className="rad-source-art" data-art="galaxy" aria-hidden="true" />
          <span>
            <strong>{cycle?.label ?? tr("Ciclo solar", "Solar cycle")}</strong>
            {cycle === undefined ? (
              <MarkOf mark={UNAVAILABLE_MARK}>{tr("el backend no da la nota del ciclo", "the backend gives no solar cycle note")}</MarkOf>
            ) : (
              <span className="ref-clamp-2 secondary" title={cycle.text}>
                {cycle.as_of !== undefined && `${formatDay(cycle.as_of)}: `}
                {cycle.text}
              </span>
            )}
          </span>
        </li>
        <li>
          <span className="rad-source-art" data-art="belts" aria-hidden="true" />
          <span>
            <strong>{onboard?.label ?? tr("Aviso a bordo", "Onboard warning")}</strong>
            {onboard === undefined ? (
              <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin lectura del aviso a bordo", "no onboard warning reading")}</MarkOf>
            ) : (
              <span className="ref-clamp-2 secondary" title={`${onboard.text}\n${onboard.scope}`}>
                {onboard.text}
              </span>
            )}
          </span>
        </li>
      </ul>
    </section>
  );
}

/** El nivel del dominio de radiación ahora, como el «Estado de riesgo» de «Inicio». */
export function RadNow({ rad }: Piece) {
  const level = radiationLevel(rad);
  const style = level !== null && isLevel(level) ? levelStyle(level) : null;
  const risk = level === null ? null : rad.home.status.domains[RADIATION];
  return (
    <section data-ui="rad-now" className="ref-card rad-now" aria-label={tr("Estado de radiación (actual)", "Radiation status (current)")}>
      <PanelTitle concept="radiation" className="ref-h">
        {tr("Estado actual", "Current status")}
      </PanelTitle>
      {level === null ? (
        <MarkOf mark={UNAVAILABLE_MARK}>{tr("el estado no trae el dominio de radiación", "the status has no radiation domain")}</MarkOf>
      ) : (
        <div className="ref-level-now rad-hero" style={tint(level)}>
          <span className="ref-hero-icon" aria-hidden="true">
            <Pictogram name={style?.pictogram ?? UNKNOWN_PICTOGRAM} />
          </span>
          <span>
            <strong>{style?.label ?? level}</strong>
            <small className="ref-clamp-2" title={risk?.trajectory?.display ?? risk?.drivers.join(" · ")}>
              {risk?.trajectory?.display ?? (risk !== undefined && risk !== null && risk.drivers.length > 0 ? risk.drivers[0] : tr("Nivel del dominio", "Domain level"))}
            </small>
          </span>
        </div>
      )}
    </section>
  );
}

/** El entorno de partículas en las últimas 24 h, la última muestra de cada serie. No se evalúa. */
export function RadWeatherNow({ rad }: Piece) {
  if (rad.weather.state !== "ready") {
    return (
      <section data-ui="rad-weather-now" className="ref-card rad-weather-now" aria-label={tr("Entorno de partículas ahora", "Particle environment now")}>
        <PanelTitle concept="radiation" className="ref-h">
          {tr("Entorno de partículas (ahora)", "Particle environment (now)")}
        </PanelTitle>
        <Pending item={rad.weather} />
      </section>
    );
  }
  const protons = rad.weather.value.series.protons;
  const wind = rad.weather.value.series["solar-wind"];
  const flux = latestOf(protons, "flux_ge_10mev");
  const speed = latestOf(wind, "speed");
  const density = latestOf(wind, "density");
  const reference = protons.available ? protons.reference : undefined;
  return (
    <section data-ui="rad-weather-now" className="ref-card rad-weather-now" aria-label={tr("Entorno de partículas ahora", "Particle environment now")}>
      <PanelTitle concept="radiation" className="ref-h">
        {tr("Entorno de partículas (ahora)", "Particle environment (now)")}
      </PanelTitle>
      <dl className="rad-kv">
        <dt>{tr("Protones", "Protons")} {reference?.channel ?? ""}</dt>
        <dd>
          {flux === null ? (
            <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
          ) : (
            <>
              <span className="num">{formatNumber(flux, 2)}</span> <small>{unitOf(protons, "flux_ge_10mev")}</small>
            </>
          )}
        </dd>
        {reference !== undefined && (
          <>
            <dt title={reference.source}>{tr("Referencia S1 (NOAA)", "S1 reference (NOAA)")}</dt>
            <dd title={tr("Se muestra al lado; EMMA no la evalúa", "Shown alongside; EMMA does not assess it")}>
              <span className="num">{formatNumber(reference.value)}</span> <small>{reference.unit}</small>{" "}
              <small className="secondary">{tr("sin evaluar", "not assessed")}</small>
            </dd>
          </>
        )}
        <dt>{tr("Viento solar", "Solar wind")}</dt>
        <dd>
          {speed === null ? (
            <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
          ) : (
            <>
              <span className="num">{formatNumber(speed)}</span> <small>{unitOf(wind, "speed")}</small>
            </>
          )}
        </dd>
        <dt>{tr("Densidad", "Density")}</dt>
        <dd>
          {density === null ? (
            <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
          ) : (
            <>
              <span className="num">{formatNumber(density, 1)}</span> <small>{unitOf(wind, "density")}</small>
            </>
          )}
        </dd>
      </dl>
      <p className="ref-clamp secondary" title={rad.weather.value.scope}>
        {rad.weather.value.scope}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------- fila 3: ubicación, dosimetría, límites

/** Lo que dice cada perfil de su entorno de radiación, con su planeta. Frases del backend. */
export function RadExposure({ rad }: Piece) {
  const { matrix, matrixFailure } = rad.home;
  return (
    <section data-ui="rad-exposure" className="ref-card rad-exposure" aria-label={tr("Exposición por ubicación", "Exposure by location")}>
      <PanelTitle concept="compare" className="ref-h">
        {tr("Exposición por ubicación", "Exposure by location")} <small className="secondary">{tr("(lo que dicen las fuentes)", "(what the sources say)")}</small>
      </PanelTitle>
      {matrix === null ? (
        matrixFailure === null ? (
          <Loading />
        ) : (
          <Unavailable outcome={matrixFailure} />
        )
      ) : (
        <ul className="rad-places">
          {matrix.profiles.map((profile) => {
            const cell = profile.cells.find((item) => item.key === "radiation_environment");
            return (
              <li key={profile.id} aria-current={profile.declared ? "true" : undefined}>
                <PlanetThumb id={profile.id} />
                <strong title={profile.display}>{PROFILE_SHORT[profile.id] ?? capitalized(profile.display)}</strong>
                {cell === undefined ? (
                  <MarkOf mark={UNAVAILABLE_MARK}>{matrix.no_source}</MarkOf>
                ) : (
                  <span className="ref-clamp-3 secondary" title={cell.text}>
                    {cell.text}
                  </span>
                )}
                <ImmFigure rad={rad} profile={profile.id} />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** La dosis de misión (inferida), la tasa a bordo y el anillo frente al límite de carrera. */
export function RadDosimetry({ rad }: Piece) {
  const { status, reference } = rad.home;
  const { mission, career } = status.radiation;
  const rates = rad.doseRate.state === "ready" ? rad.doseRate.value : [];
  const lastRate = rates.length > 0 ? rates[rates.length - 1] : undefined;
  const day = rates.filter((item) => item.at > reference - DAY_MS && item.at <= reference).map((item) => item.value);
  const dayMean = day.length === 0 ? null : day.reduce((a, b) => a + b, 0) / day.length;
  const dayMax = day.length === 0 ? null : Math.max(...day);
  const careerValue = career.value_msv;
  return (
    <section data-ui="rad-dosimetry" className="ref-card rad-dosimetry" aria-label={tr("Dosimetría y monitorización", "Dosimetry and monitoring")}>
      <PanelTitle concept="measure" className="ref-h">
        {tr("Dosimetría y monitorización", "Dosimetry and monitoring")}
      </PanelTitle>
      <div className="rad-dose-grid">
        <dl className="rad-kv">
          <dt>{tr("Tasa de dosis absorbida", "Absorbed dose rate")}</dt>
          <dd>
            {rad.doseRate.state !== "ready" ? (
              <Pending item={rad.doseRate} />
            ) : lastRate === undefined ? (
              <MarkOf mark={MISSING_MARK}>{tr("sin lecturas", "no readings")}</MarkOf>
            ) : (
              <>
                <span className="num">{formatNumber(lastRate.value, 2)}</span> <small>{displayUnit("uGy/h")}</small>
              </>
            )}
          </dd>
          <dd className="rad-spark-row">
            <Sparkline readings={rates} until={reference} />
          </dd>
          <dt>{tr("Media · máximo (24 h)", "Mean · maximum (24 h)")}</dt>
          <dd title={tr("De las lecturas de la tasa de las últimas 24 h; no es una dosis", "From the rate readings of the last 24 h; not a dose")}>
            {dayMean === null || dayMax === null ? (
              <MarkOf mark={MISSING_MARK}>{tr("sin lecturas en 24 h", "no readings in 24 h")}</MarkOf>
            ) : (
              <>
                <span className="num">{formatNumber(dayMean, 2)}</span> · <span className="num">{formatNumber(dayMax, 2)}</span>{" "}
                <small>{displayUnit("uGy/h")}</small>
              </>
            )}
          </dd>
          <dt>{tr("Dosis de esta misión", "Dose this mission")}</dt>
          <dd>
            {mission === null ? (
              <MarkOf mark={MISSING_MARK}>{tr("sin dosis que integrar", "no dose to integrate")}</MarkOf>
            ) : (
              <>
                <span className="num">{formatNumber(mission.value_msv, 1)}</span> <small>mSv</small>{" "}
                <ObservationTypeBadge type={mission.observation_type} />
              </>
            )}
          </dd>
          {mission !== null && (
            <>
              <dt>{tr("Absorbida · factor Q", "Absorbed · Q factor")}</dt>
              <dd title={mission.basis}>
                <span className="num">{formatNumber(mission.absorbed_mgy, 1)}</span> <small>mGy</small> ·{" "}
                <span className="num">Q {formatNumber(mission.quality_factor, 2)}</span>
              </dd>
              <dt>{tr("Horas integradas", "Hours integrated")}</dt>
              <dd>
                <span className="num">{formatNumber(mission.hours_covered)}</span> <small>h</small>
              </dd>
            </>
          )}
        </dl>
        <div className="rad-ring-col">
          <span className="ref-h3">{tr("Dosis acumulada (misión)", "Cumulative dose (mission)")}</span>
          {mission === null ? (
            <MarkOf mark={MISSING_MARK}>{tr("sin dosis", "no dose")}</MarkOf>
          ) : (
            <Ring done={mission.value_msv} total={career.limit_msv} label={tr("mSv del límite de carrera", "mSv of the career limit")}>
              <strong className="num">{formatNumber(mission.value_msv)}</strong>
              <small>mSv</small>
            </Ring>
          )}
          <small className="secondary rad-ring-caption" title={career.basis}>
            {tr(`de ${formatNumber(career.limit_msv)} mSv de carrera`, `of ${formatNumber(career.limit_msv)} mSv career limit`)} ·{" "}
            {careerValue === null
              ? tr("sin dosis previa declarada", "no prior dose declared")
              : tr(`carrera ${formatNumber(careerValue, 1)} mSv`, `career ${formatNumber(careerValue, 1)} mSv`)}
          </small>
        </div>
      </div>
    </section>
  );
}

/** El límite de carrera y los de corto plazo de NASA-STD-3001 (Tabla 4.8-1), con su unidad. */
export function RadLimits({ rad }: Piece) {
  const { career, short_term_limits: limits } = rad.home.status.radiation;
  const cell = (value: { value: number | null; absent: string | null; literal: string | null }) =>
    value.value === null ? (
      <span className="secondary" title={value.absent ?? undefined}>
        {value.literal ?? "—"}
      </span>
    ) : (
      <span className="num">{formatNumber(value.value)}</span>
    );
  return (
    <section data-ui="rad-limits" className="ref-card rad-limits" aria-label={tr("Límites de dosis", "Dose limits")}>
      <PanelTitle concept="limits" className="ref-h">
        {tr("Límites (NASA-STD-3001)", "Limits (NASA-STD-3001)")}
      </PanelTitle>
      <p className="rad-limit-career" style={tint("nominal")}>
        <Pictogram name="bar-capped" />
        <span>
          <strong>{tr("Carrera (dosis efectiva)", "Career (effective dose)")}</strong>
          <small className="secondary">{career.limit_source}</small>
        </span>
        <span className="num">{formatNumber(career.limit_msv)} mSv</span>
      </p>
      {limits === undefined ? (
        <MarkOf mark={UNAVAILABLE_MARK}>{tr("el backend no da los límites a corto plazo", "the backend gives no short-term limits")}</MarkOf>
      ) : (
        <table className="rad-table">
          <caption className="secondary ref-ellipsis" title={limits.scope}>
            {tr("Corto plazo, en", "Short term, in")} {limits.rows[0]?.unit ?? tr("su unidad", "its unit")}
          </caption>
          <thead>
            <tr>
              <th scope="col">{tr("Órgano", "Organ")}</th>
              <th scope="col">{tr("30 días", "30 days")}</th>
              <th scope="col">{tr("1 año", "1 year")}</th>
            </tr>
          </thead>
          <tbody>
            {limits.rows.slice(0, 4).map((row) => (
              <tr key={row.organ} title={row.note ?? undefined}>
                <th scope="row">{row.organ_display}</th>
                <td>{cell(row.thirty_day)}</td>
                <td>{cell(row.one_year)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- fila 4: niveles, efectos, tripulante, pruebas

/** La escala de niveles del motor y dónde está el dominio; los límites de peligro de la detección. */
export function RadLevels({ rad }: Piece) {
  const level = radiationLevel(rad);
  const alerts = rad.home.status.alerts.filter((item) => item.domain === RADIATION);
  const limits = rad.risk.state === "ready" && rad.risk.value !== null ? rad.risk.value.detection.danger_limits : [];
  return (
    <section data-ui="rad-levels" className="ref-card ref-levels rad-levels" aria-label={tr("Alertas y niveles", "Alerts and levels")}>
      <PanelTitle concept="alerts" className="ref-h">
        {tr("Alertas y niveles", "Alerts and levels")}
      </PanelTitle>
      <ul>
        {LEVEL_ORDER.map((item) => (
          <li key={item} style={tint(item)} aria-current={item === level ? "true" : undefined}>
            <span className="ref-level-box" aria-hidden="true">
              <Pictogram name={levelStyle(item).pictogram} />
            </span>
            <LevelBadge level={item} />
          </li>
        ))}
      </ul>
      <p className="secondary" title={limits.map((item) => item.statement).join(" · ") || undefined}>
        {alerts.length === 0 ? (
          <MarkOf mark={OK_MARK}>{tr("Sin alertas activas.", "No active alerts.")}</MarkOf>
        ) : (
          <>
            <span className="num">{formatNumber(alerts.length)}</span> {alerts.length === 1 ? tr("alerta activa", "active alert") : tr("alertas activas", "active alerts")}
          </>
        )}
      </p>
    </section>
  );
}

/** El efecto según la ficha del riesgo y las regiones del cuerpo que el riesgo nombra. Frases del backend. */
export function RadEffects({ rad }: Piece) {
  const { status } = rad.home;
  if (rad.risk.state !== "ready" || rad.risk.value === null) {
    return (
      <section data-ui="rad-effects" className="ref-card rad-effects" aria-label={tr("Efectos sobre la salud", "Health effects")}>
        <PanelTitle concept="body" className="ref-h">
          {tr("Efectos sobre la salud", "Health effects")}
        </PanelTitle>
        {rad.risk.state === "ready" ? <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin entidad de riesgo de radiación", "no radiation risk entity")}</MarkOf> : <Pending item={rad.risk} />}
      </section>
    );
  }
  const risk = rad.risk.value;
  const level = status.domains[RADIATION]?.level;
  return (
    <section data-ui="rad-effects" className="ref-card rad-effects" aria-label={tr("Efectos sobre la salud", "Health effects")}>
      <PanelTitle concept="body" className="ref-h">
        {tr("Efectos sobre la salud", "Health effects")}
      </PanelTitle>
      <p className="rad-effect" title={risk.effect.basis}>
        {risk.effect.statement}
      </p>
      {risk.effect.source !== null && (
        <p className="secondary ref-ellipsis">
          <Pictogram name="book-open" />{" "}
          {risk.effect.source.url === null ? (
            risk.effect.source.title
          ) : (
            <a href={risk.effect.source.url} target="_blank" rel="noreferrer">
              {risk.effect.source.title}
            </a>
          )}
        </p>
      )}
      <ul className="rad-regions">
        {risk.human_system.regions.slice(0, 4).map((region) => (
          <li key={region.key}>
            <span className="ref-ellipsis" title={region.note}>
              {region.display}
            </span>
            <Segments tones={region.domains.map((domain) => levelToken(status.domains[domain]?.level))} />
          </li>
        ))}
      </ul>
      <p className="secondary ref-clamp" title={risk.amcl_alignment}>
        {level !== undefined && <LevelBadge level={level} />} {risk.amcl_alignment}
      </p>
      <ImmDeclared rad={rad} />
      <h3 className="ref-h3" title={risk.detection.basis}>
        {tr("Cómo lo detecta EMMA", "How EMMA detects it")}
      </h3>
      <ul className="rad-checks rad-detection">
        {[...risk.detection.danger_limits.map((item) => ({ key: item.key, text: item.statement })),
          ...risk.detection.environment.map((item) => ({ key: item.key, text: item.statement }))].map((item) => (
          <li key={item.key}>
            <Pictogram name="bar-capped" />
            <span className="ref-ellipsis" title={item.text}>
              {item.text}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * La pestaña de cada peligro RIDGE. Las letras de «Tripulante» parecían botones y no hacían nada
 * (lote «botones», 2026-11-15): cada una abre la pestaña de su peligro; la distancia vive en
 * «Nodos». Si esa pestaña no está a la vista (modo esencial), se cae a «Peligros».
 */
const HAZARD_TAB: Record<string, string> = {
  radiation: "radiation",
  isolation: "isolation",
  distance: "nodes",
  gravity: "gravity",
  environment: "environment",
};

/** El acceso de un peligro: su pestaña, o «Peligros» si no está a la vista; `null` sin consola. */
export function hazardLink(links: HomeLinks | undefined, hazard: string): ReturnType<typeof sectionLink> {
  const own = HAZARD_TAB[hazard];
  return (own === undefined ? null : sectionLink(links, own)) ?? sectionLink(links, "hazards");
}

/** El tripulante y sus letras RIDGE, como en «Inicio»: la R destacada. */
export function RadCrew({ rad, links }: Piece & { links?: HomeLinks | undefined }) {
  const { status, groups } = rad.home;
  const member = rad.crew.state === "ready" ? rad.crew.value.crew.find((item) => item.subject === status.subject) : undefined;
  return (
    <section data-ui="rad-crew" className="ref-card rad-crew" aria-label={tr("Tripulante: impacto RIDGE", "Crew member: RIDGE impact")}>
      <PanelTitle concept="identity" className="ref-h">
        {tr("Tripulante:", "Crew member:")} {status.subject} · RIDGE
      </PanelTitle>
      <div className="rad-crew-grid">
        {/* El cuerpo de «Inicio» (adorno) con la silueta real encima: el nivel por región es el del backend. */}
        <article className="ref-card ref-body-figure rad-body" aria-label={tr("Cuerpo", "Body")}>
          <Suspense fallback={<Loading />}>
            <ReferenceBody />
          </Suspense>
          {/* Pulsar una región abre aquí su ficha (la cadena del backend), como en «Inicio». */}
          <RegionFigure view={rad.home.anatomy} region={rad.home.region} setRegion={rad.home.setRegion} status={status} />
        </article>
        <div className="rad-crew-side">
      <ul className="rad-ridge">
        {groups.map((group) => {
          const levels = group.domains.map((domain) => status.domains[domain]?.level);
          const link = hazardLink(links, group.hazard);
          const what = capitalized(group.display);
          return (
            <li
              key={group.hazard}
              data-acc={group.hazard}
              data-current={group.hazard === RADIATION ? "true" : undefined}
              className={link === null ? undefined : "ref-linked"}
            >
              {/* El botón transparente de «Inicio» (`.ref-go`): la fila no cambia de aspecto. */}
              {link !== null && (
                <button
                  type="button"
                  className="ref-go"
                  aria-label={tr(`Abrir ${link.name}: ${what}`, `Open ${link.name}: ${what}`)}
                  title={tr(`Abrir ${link.name}: ${what}`, `Open ${link.name}: ${what}`)}
                  onClick={link.open}
                />
              )}
              <span className="ref-chip-letter" aria-hidden="true">
                {letterOf(group.hazard)}
              </span>
              <span className="ref-ellipsis" title={capitalized(group.display)}>
                {capitalized(group.display)}
              </span>
              <Segments tones={levels.map((item) => levelToken(item))} />
            </li>
          );
        })}
      </ul>
      {member !== undefined && (
        <p className="secondary ref-clamp" title={member.location_missing_text ?? undefined}>
          <Pictogram name="pin" />{" "}
          {member.location === null ? (member.location_missing_text ?? tr("ubicación sin declarar", "location not declared")) : member.location.display}
        </p>
      )}
        </div>
      </div>
    </section>
  );
}

/** Lo que mide el riesgo y con qué equipo (la entidad Riesgo); la marca dice si hay lecturas. */
export function RadTests({ rad }: Piece) {
  const counts = rad.home.status.provenance;
  if (rad.risk.state !== "ready" || rad.risk.value === null) {
    return (
      <section data-ui="rad-tests" className="ref-card rad-tests" aria-label={tr("Pruebas y control", "Tests and monitoring")}>
        <PanelTitle concept="analyte" className="ref-h">
          {tr("Pruebas y control", "Tests and monitoring")}
        </PanelTitle>
        <Pending item={rad.risk} />
      </section>
    );
  }
  const groups = rad.risk.value.equipment.groups;
  return (
    <section data-ui="rad-tests" className="ref-card rad-tests" aria-label={tr("Pruebas y control", "Tests and monitoring")}>
      <PanelTitle concept="analyte" className="ref-h">
        {tr("Pruebas y control", "Tests and monitoring")}
      </PanelTitle>
      <div className="rad-tests-grid">
        <ul className="rad-tests-list">
          {groups.map((group) => {
            const known = rad.latest.state === "ready" ? rad.latest.value : null;
            const measured = known === null ? null : group.indicators.filter((item) => known[item.key] != null).length;
            return (
              <li key={group.equipment}>
                <span className="rad-box" data-checked={measured !== null && measured > 0 ? "true" : "false"} aria-hidden="true">
                  {measured !== null && measured > 0 && <Pictogram name="check" />}
                </span>
                <span>
                  <strong>{capitalized(group.equipment)}</strong>
                  <span className="ref-clamp-2 secondary" title={group.indicators.map((item) => item.display_es).join(", ")}>
                    {group.indicators.map((item) => item.display_es).join(", ")}
                  </span>
                  {measured === null ? (
                    <MarkOf mark={LOADING_MARK}>{tr("Cargando…", "Loading…")}</MarkOf>
                  ) : measured === 0 ? (
                    <MarkOf mark={MISSING_MARK}>{tr("sin lecturas", "no readings")}</MarkOf>
                  ) : (
                    <small>
                      {tr("con lecturas:", "with readings:")} <span className="num">{formatNumber(measured)}</span> {tr("de", "of")}{" "}
                      <span className="num">{formatNumber(group.indicators.length)}</span>
                    </small>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
        <LabArt />
      </div>
      <p className="secondary ref-clamp" title={rad.risk.value.equipment.basis}>
        {rad.risk.value.indicators.length} {tr("indicadores del dominio", "domain indicators")} ·{" "}
        {Object.values(counts.observation_type).reduce((a, b) => a + b, 0)} {tr("lecturas en el veredicto", "readings in the verdict")}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------- fila 5: ruta, historial, gestión

/**
 * La ruta del perfil y la dosis: lo integrado hasta hoy (inferido) y lo proyectado al fin (PREDICHO).
 *
 * «Ruta: …» parecía un desplegable y no lo era (lote «botones», 2026-11-15): ahora elige la ruta
 * enseñada, la misma de «Ubicación» y «Rutas espaciales» de «Inicio» (`home.setRoute`). La
 * proyección de dosis del backend solo existe para el perfil declarado: con otra ruta elegida la
 * tabla no cambia y se dice con palabras, y de la ruta elegida se enseña lo que la matriz de perfiles
 * ya trae de ella (su entorno de radiación, frase del backend). No se inventa ninguna cifra.
 */
export function RadRoute({ rad }: Piece) {
  const { status, matrix, shownRoute, setRoute } = rad.home;
  const { mission, projection } = status.radiation;
  const declared = matrix?.profiles.find((item) => item.declared) ?? null;
  const profile = matrix?.profiles.find((item) => item.id === shownRoute) ?? declared;
  const nameOf = (item: { id: string; display: string }) => PROFILE_SHORT[item.id] ?? capitalized(item.display);
  const target = profile === null ? (status.mission.profile?.display ?? "—") : nameOf(profile);
  const chosenOther = profile !== null && !profile.declared;
  const declaredName = declared === null ? (status.mission.profile?.display ?? null) : nameOf(declared);
  const environment = profile?.cells.find((cell) => cell.key === "radiation_environment") ?? null;
  return (
    <section data-ui="rad-route" className="ref-frame rad-route" aria-label={tr("Ruta espacial y exposición estimada", "Space route and estimated exposure")}>
      <PanelTitle concept="compare" className="ref-h ref-frame-h">
        {tr("Ruta espacial y exposición estimada", "Space route and estimated exposure")}
      </PanelTitle>
      <ol className="rad-phases" aria-label={tr("Fases de la misión", "Mission phases")}>
        {status.mission.phases.map((phase) => (
          <li key={phase.key} aria-current={phase.key === status.mission.phase ? "step" : undefined}>
            {phase.display}
          </li>
        ))}
      </ol>
      <div className="rad-route-grid">
        <div className="rad-route-art">
          {matrix === null || matrix.profiles.length === 0 ? (
            <span className="ref-select-like">{tr("Ruta:", "Route:")} {target}</span>
          ) : (
            <label className="ref-select-like">
              {tr("Ruta:", "Route:")}
              <select value={profile?.id ?? ""} onChange={(event) => setRoute(event.target.value)}>
                {profile === null && <option value="">—</option>}
                {matrix.profiles.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.declared ? tr(`${nameOf(item)} (declarado)`, `${nameOf(item)} (declared)`) : nameOf(item)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <RouteArt target={target} targetId={profile?.id ?? status.mission.profile?.id ?? "leo"} />
        </div>
        <table className="rad-table">
          <thead>
            <tr>
              <th scope="col">{tr("Tramo", "Leg")}</th>
              <th scope="col">{tr("Días", "Days")}</th>
              <th scope="col">{tr("Dosis", "Dose")}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">{tr("Hasta hoy", "To date")}</th>
              <td className="num">{formatNumber(status.mission.mission_day)}</td>
              <td>
                {mission === null ? (
                  <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
                ) : (
                  <>
                    <span className="num">{formatNumber(mission.value_msv, 1)} mSv</span> <ObservationTypeBadge type="inferred" />
                  </>
                )}
              </td>
            </tr>
            <tr>
              <th scope="row">{tr("Resto de la misión", "Rest of the mission")}</th>
              <td className="num">
                {projection === null || projection === undefined ? "—" : formatNumber(Math.max(0, projection.end_day - status.mission.mission_day))}
              </td>
              <td className="secondary">{tr("tasa media constante", "constant mean rate")}</td>
            </tr>
            <tr className="rad-total">
              <th scope="row">{tr("Fin de misión", "End of mission")}</th>
              <td className="num">{projection === null || projection === undefined ? formatNumber(status.mission.duration_days) : formatNumber(projection.end_day)}</td>
              <td>
                {projection === null || projection === undefined || projection.value_msv === null ? (
                  <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin proyección", "no projection")}</MarkOf>
                ) : (
                  <span title={projection.basis}>
                    <span className="num">{formatNumber(projection.value_msv, 1)} mSv</span>{" "}
                    <ObservationTypeBadge type={projection.observation_type} />
                  </span>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      {chosenOther && (
        <p className="secondary ref-clamp-2" data-route-note="other">
          {declaredName === null
            ? tr(
                `La dosis de la tabla es la de la misión en curso; EMMA no proyecta dosis para ${target}.`,
                `The dose in the table is that of the current mission; EMMA does not project a dose for ${target}.`,
              )
            : tr(
                `La dosis de la tabla es la del perfil declarado (${declaredName}); EMMA no proyecta dosis para ${target}.`,
                `The dose in the table is that of the declared profile (${declaredName}); EMMA does not project a dose for ${target}.`,
              )}
        </p>
      )}
      {environment !== null && (
        <p className="secondary ref-clamp-2" title={environment.text}>
          <strong>{capitalized(environment.label)}:</strong> {environment.text}
        </p>
      )}
    </section>
  );
}

/** Las misiones previas declaradas del tripulante, con su dosis si se conoce. */
export function RadHistory({ rad }: Piece) {
  const { status } = rad.home;
  const current = status.radiation.mission;
  const now = (
    <tr className="rad-current">
      <td>
        <Pictogram name={uiPictogram("chosen")} />
      </td>
      <th scope="row" className="ref-ellipsis" title={status.mission.profile?.display}>
        {tr("En curso:", "In progress:")} {capitalized(status.mission.profile?.display ?? tr("misión", "mission"))}
      </th>
      <td className="num">{formatNumber(status.mission.mission_day)}</td>
      <td>
        {current === null ? (
          <MarkOf mark={MISSING_MARK}>{tr("sin dato", "no data")}</MarkOf>
        ) : (
          <>
            <span className="num">{formatNumber(current.value_msv, 1)} mSv</span> <ObservationTypeBadge type={current.observation_type} />
          </>
        )}
      </td>
    </tr>
  );
  const head = (
    <thead>
      <tr>
        <th scope="col">#</th>
        <th scope="col">{tr("Misión", "Mission")}</th>
        <th scope="col">{tr("Días", "Days")}</th>
        <th scope="col">{tr("Dosis", "Dose")}</th>
      </tr>
    </thead>
  );
  return (
    <section data-ui="rad-history" className="ref-frame rad-history" aria-label={tr("Historial de exposición", "Exposure history")}>
      <PanelTitle concept="history" className="ref-h ref-frame-h">
        {tr("Historial de exposición", "Exposure history")}
      </PanelTitle>
      {rad.history.state !== "ready" ? (
        <Pending item={rad.history} />
      ) : !rad.history.value.declared ? (
        <>
          <table className="rad-table">
            {head}
            <tbody>{now}</tbody>
          </table>
          <p className="secondary">
            <MarkOf mark={MISSING_MARK}>{rad.history.value.text}</MarkOf>
          </p>
          <p className="secondary ref-clamp" title={status.radiation.career.basis}>
            {tr("Carrera:", "Career:")} {status.radiation.career.value_msv === null ? status.radiation.career.basis : `${formatNumber(status.radiation.career.value_msv, 1)} mSv`}
          </p>
        </>
      ) : (
        <>
          <table className="rad-table">
            {head}
            <tbody>
              {rad.history.value.missions.slice(0, 4).map((item, index) => (
                <tr key={`${item.name}-${item.start}`}>
                  <td className="num">{formatNumber(index + 1)}</td>
                  <th scope="row" className="ref-ellipsis">
                    {item.name}
                  </th>
                  <td className="num">{formatNumber(item.days)}</td>
                  <td>{item.dose_msv === null ? <span className="secondary">{tr("sin dato", "no data")}</span> : <span className="num">{formatNumber(item.dose_msv, 1)} mSv</span>}</td>
                </tr>
              ))}
              {now}
            </tbody>
          </table>
          <p className="secondary ref-clamp" title={rad.history.value.text}>
            {rad.history.value.dose_sum_msv === null ? rad.history.value.text : tr(`Suma declarada: ${formatNumber(rad.history.value.dose_sum_msv, 1)} mSv`, `Declared total: ${formatNumber(rad.history.value.dose_sum_msv, 1)} mSv`)}
          </p>
        </>
      )}
    </section>
  );
}

/** Las contramedidas de la biblioteca para el riesgo, como en la fila de su matriz. */
export function RadManagement({ rad }: Piece) {
  const open = rad.home.status.followups.filter((item) => item.domain === RADIATION && item.state !== "closed");
  return (
    <section data-ui="rad-management" className="ref-frame rad-management" aria-label={tr("Recuperación y gestión de riesgo", "Recovery and risk management")}>
      <PanelTitle concept="recovery" className="ref-h ref-frame-h">
        {tr("Recuperación y gestión de riesgo", "Recovery and risk management")}
      </PanelTitle>
      {rad.risk.state !== "ready" || rad.risk.value === null ? (
        <Pending item={rad.risk} />
      ) : rad.risk.value.countermeasures.items.length === 0 ? (
        <p className="secondary">{rad.risk.value.countermeasures.empty}</p>
      ) : (
        <ul className="rad-checks">
          {rad.risk.value.countermeasures.items.slice(0, 5).map((item) => (
            <li key={item.id} title={[item.action, item.basis_display, item.trigger_display].filter(Boolean).join(" · ")}>
              <Pictogram name={item.on_event ? "bell" : "bandage"} />
              <span className="ref-ellipsis">{item.action}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="secondary rad-followups">
        {open.length === 0 ? (
          <MarkOf mark={OK_MARK}>{tr("Ninguna contramedida de radiación en seguimiento.", "No radiation countermeasure under follow-up.")}</MarkOf>
        ) : (
          <>
            <Pictogram name="magnifier" /> {tr("En seguimiento:", "Under follow-up:")}{" "}
            {open.map((item) => item.countermeasure.action).join(" · ")}
          </>
        )}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------- fila 6: meteorología, blindaje, recomendaciones

/** Las dos series de las últimas 24 h, con su fuente y su edad. Observado, no pronosticado. */
export function RadSpaceWeather({ rad }: Piece) {
  if (rad.weather.state !== "ready") {
    return (
      <section data-ui="rad-space-weather" className="ref-frame rad-space-weather" aria-label={tr("Meteorología espacial", "Space weather")}>
        <PanelTitle concept="trends" className="ref-h ref-frame-h">
          {tr("Meteorología espacial (24 h observadas)", "Space weather (24 h observed)")}
        </PanelTitle>
        <Pending item={rad.weather} />
      </section>
    );
  }
  const protons = rad.weather.value.series.protons;
  const wind = rad.weather.value.series["solar-wind"];
  // Las series son de ahora (reloj real), no del instante de la misión simulada.
  const until = Date.now();
  const rows: { key: string; label: string; block: SpaceWeatherSeriesBlock; channel: string }[] = [
    { key: "protons", label: `${tr("Protones", "Protons")} ${protons.available ? (protons.reference?.channel ?? "") : ""}`, block: protons, channel: "flux_ge_10mev" },
    { key: "speed", label: tr("Viento solar", "Solar wind"), block: wind, channel: "speed" },
    { key: "density", label: tr("Densidad del viento", "Wind density"), block: wind, channel: "density" },
  ];
  return (
    <section data-ui="rad-space-weather" className="ref-frame rad-space-weather" aria-label={tr("Meteorología espacial", "Space weather")}>
      <PanelTitle concept="trends" className="ref-h ref-frame-h">
        {tr("Meteorología espacial", "Space weather")} <small className="secondary">{tr("(24 h observadas, sin pronóstico)", "(24 h observed, no forecast)")}</small>
      </PanelTitle>
      <span className="rad-sun" aria-hidden="true" />
      <ul className="rad-series">
        {rows.map((row) => {
          const readings = seriesReadings(row.block, row.channel);
          const latest = latestOf(row.block, row.channel);
          return (
            <li key={row.key} data-series={row.key}>
              <span>{row.label}</span>
              <span className="rad-series-value">
                {latest === null ? (
                  <MarkOf mark={row.block.available ? MISSING_MARK : UNAVAILABLE_MARK}>{tr("sin dato", "no data")}</MarkOf>
                ) : (
                  <>
                    <span className="num">{formatNumber(latest, row.key === "protons" ? 2 : row.key === "density" ? 1 : 0)}</span>{" "}
                    <small>{unitOf(row.block, row.channel)}</small>
                  </>
                )}
              </span>
              <Sparkline readings={readings} until={until} />
            </li>
          );
        })}
      </ul>
      <WeekBars rad={rad} />
      <p className="secondary ref-ellipsis" title={rad.weather.value.licence}>
        {protons.available ? `${protons.source} · ${ageOf(protons.data_age_seconds) ?? protons.data_age ?? ""}` : (protons.reason ?? protons.title)}
      </p>
    </section>
  );
}

/** El refugio: el procedimiento con evento vigente o lo que dice la fuente del blindaje. */
export function RadShielding({ rad }: Piece) {
  const crew = rad.crew.state === "ready" ? rad.crew.value : null;
  const shelter = rad.home.status.radiation.acute.time_to_action;
  const exit = rad.home.status.radiation.acute.shelter_exit;
  return (
    <section data-ui="rad-shielding" className="ref-frame rad-shielding" aria-label={tr("Zonas de blindaje y protección", "Shielding and protection zones")}>
      <PanelTitle concept="habitat" className="ref-h ref-frame-h">
        {tr("Zonas de blindaje y protección", "Shielding and protection zones")}
      </PanelTitle>
      <div className="rad-shield-grid">
        <ShipArt />
        <ul className="rad-checks">
          {crew === null ? (
            <li>
              <Pending item={rad.crew} />
            </li>
          ) : (
            <li title={crew.shielding}>
              <Pictogram name="house" />
              <span className="ref-clamp-2">{crew.shielding}</span>
            </li>
          )}
          <li>
            {shelter === null ? (
              <>
                <Pictogram name="check" />
                <span className="ref-clamp-2">{crew?.shelter_missing_text ?? tr("Sin evento vigente: sin refugio en curso.", "No event in effect: no shelter in progress.")}</span>
              </>
            ) : (
              <>
                <Pictogram name="clock" />
                <span title={shelter.basis}>
                  {tr("Refugio listo antes de", "Shelter ready before")} <span className="num">{utc(shelter.shelter_ready_by)}</span>
                </span>
              </>
            )}
          </li>
          {exit !== undefined && (
            <li title={exit.text}>
              <Pictogram name="book-open" />
              <span className="ref-clamp-2">{exit.text}</span>
            </li>
          )}
        </ul>
      </div>
    </section>
  );
}

/**
 * Las recomendaciones del estado para el dominio de radiación, tal cual. Con `decide` (la consola de
 * tripulación) cada fila lleva «Adoptar» y «No adoptar», firmados como en «Peligros y alertas».
 */
export function RadRecommendations({ rad, decide }: Piece & { decide?: BoardDecisions | undefined }) {
  const items = rad.home.status.recommendations.filter((item) => item.domain === RADIATION);
  const shown = items.slice(0, 4);
  return (
    <section data-ui="rad-recommendations" className="ref-frame rad-recommendations" aria-label={tr("Recomendaciones de EMMA", "EMMA recommendations")}>
      <PanelTitle concept="recommendations" className="ref-h ref-frame-h">
        {tr("Recomendaciones (EMMA)", "Recommendations (EMMA)")}
      </PanelTitle>
      {items.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={OK_MARK}>{tr("Sin recomendaciones de radiación: nada requiere acción.", "No radiation recommendations: nothing requires action.")}</MarkOf>
        </p>
      ) : (
        <>
          <ul className="rad-checks">
            {shown.map((item) => (
              <li key={`${item.action}-${item.urgency}`} title={item.rationale}>
                <Pictogram name="check" />
                <span className="ref-clamp">{item.action}</span>
                {decide !== undefined && <AdoptControls item={item} decide={decide} />}
              </li>
            ))}
          </ul>
          {decide !== undefined && <BoardOperator items={shown} decide={decide} />}
        </>
      )}
      <span className="rad-ai" aria-hidden="true">
        AI
      </span>
    </section>
  );
}

/** La probabilidad del IMM en tanto por mil, con la cifra del informe en `title`. */
function perMil(probability: number): string {
  return formatNumber(probability * 1000, 2);
}

/** Bajo cada perfil: la probabilidad del IMM de su misión de referencia (la asimilación es de EMMA). */
function ImmFigure({ rad, profile }: Piece & { profile: string }) {
  if (rad.imm.state !== "ready") return rad.imm.state === "loading" ? null : <Pending item={rad.imm} />;
  const imm = rad.imm.value;
  const item = imm.profiles.find((entry) => entry.id === profile);
  const drm = imm.drms.find((entry) => entry.key === item?.drm);
  if (item === undefined || drm === undefined) return <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin misión del IMM", "no IMM mission")}</MarkOf>;
  return (
    <span
      className="rad-imm"
      title={`${imm.measure}. IMM, ${drm.display} (${drm.table}): «${drm.row_quote}». ${item.reason}. ${imm.caveat}`}
    >
      <small>IMM · SAR</small>
      <strong className="num">{perMil(item.probability)}</strong>
      <small>{tr("por mil misiones", "per thousand missions")}</small>
    </span>
  );
}

/** En «Efectos»: el síndrome agudo de radiación del perfil declarado según el IMM, y la salvedad. */
function ImmDeclared({ rad }: Piece) {
  if (rad.imm.state !== "ready") return <Pending item={rad.imm} />;
  const imm = rad.imm.value;
  const item = imm.profiles.find((entry) => entry.declared);
  const drm = imm.drms.find((entry) => entry.key === item?.drm);
  return (
    <div className="rad-imm-declared">
      <h3 className="ref-h3" title={imm.measure_quote}>
        {tr("Modelo médico integrado de NASA (IMM)", "NASA Integrated Medical Model (IMM)")}
      </h3>
      {item === undefined || drm === undefined ? (
        <MarkOf mark={UNAVAILABLE_MARK}>{tr("el perfil declarado no tiene misión de referencia del IMM", "the declared profile has no IMM reference mission")}</MarkOf>
      ) : (
        <p>
          <span className="secondary">{capitalized(imm.condition_display)}, {drm.display}:</span>{" "}
          <strong className="num" title={`«${drm.row_quote}» (${drm.table})`}>
            {perMil(item.probability)}
          </strong>{" "}
          <span className="secondary">{tr("por mil misiones de un tripulante", "per thousand missions of one crew member")}</span>
        </p>
      )}
      <p className="secondary ref-clamp-2" title={`${imm.caveat_quote} ${imm.scope}`}>
        {imm.caveat}{" "}
        {imm.source.url === null ? (
          imm.source.title
        ) : (
          <a href={imm.source.url} target="_blank" rel="noreferrer">
            {imm.source.title}
          </a>
        )}
      </p>
    </div>
  );
}

/** Las anclas de la maqueta («Radiación · Exposición · Efectos…»): llevan a su panel. */
const NAV: { label: string; target: string }[] = [
  { label: tr("Radiación", "Radiation"), target: "rad-spectrum" },
  { label: tr("Exposición", "Exposure"), target: "rad-exposure" },
  { label: tr("Efectos en la salud", "Health effects"), target: "rad-effects" },
  { label: tr("Prevención", "Prevention"), target: "rad-management" },
  { label: tr("Predicción", "Prediction"), target: "rad-route" },
  { label: tr("Historial", "History"), target: "rad-history" },
];

/** La franja de la maqueta: anclas a los paneles y la misión en curso con su fase (del backend). */
export function RadNav({ rad }: Piece) {
  const { mission } = rad.home.status;
  const go = (target: string) => {
    const find = () => document.querySelector(`[data-ui="${target}"]`);
    const panel = find();
    if (panel !== null) {
      panel.scrollIntoView({ block: "start", behavior: "smooth" });
      return;
    }
    // El ancla apunta a un panel plegado bajo la raya (2026-11-15): pedirlo es querer verlo, así que
    // se despliega lo secundario y se va a él cuando ya está pintado.
    setFoldOpen(RAD_FOLD, true);
    requestAnimationFrame(() => find()?.scrollIntoView({ block: "start", behavior: "smooth" }));
  };
  return (
    <section data-ui="rad-nav" className="ref-card rad-nav" aria-label={tr("Apartados de radiación", "Radiation sections")}>
      <nav aria-label={tr("Ir a un apartado", "Go to a section")}>
      <ul>
        {NAV.map((item) => (
          <li key={item.target}>
            <button type="button" onClick={() => go(item.target)}>
              {item.label}
            </button>
          </li>
        ))}
      </ul>
      </nav>
      <p className="rad-nav-mission">
        <Pictogram name="calendar-day" />
        <span>
          <strong>{capitalized(mission.profile?.display ?? tr("misión", "mission"))}</strong>{" "}
          <span className="secondary">
            · {tr("día", "day")} <span className="num">{formatNumber(mission.mission_day)}</span> {tr("de", "of")}{" "}
            <span className="num">{formatNumber(mission.duration_days)}</span> · {mission.phase_display}
          </span>
        </span>
      </p>
    </section>
  );
}

/**
 * La media diaria de la tasa de dosis a bordo de los últimos siete días, en barras: lo observado, no
 * una predicción (la maqueta pintaba «predicción de exposición»; EMMA no la hace).
 */
export function WeekBars({ rad }: Piece) {
  const { reference } = rad.home;
  const rates = rad.doseRate.state === "ready" ? rad.doseRate.value : [];
  const days = Array.from({ length: 7 }, (_, index) => {
    const end = reference - (6 - index) * DAY_MS;
    const values = rates.filter((item) => item.at > end - DAY_MS && item.at <= end).map((item) => item.value);
    return { index, mean: values.length === 0 ? null : values.reduce((a, b) => a + b, 0) / values.length };
  });
  const top = Math.max(0, ...days.map((item) => item.mean ?? 0));
  return (
    <figure className="rad-week">
      <figcaption>
        {tr("Tasa de dosis a bordo, media diaria (7 días observados)", "Onboard dose rate, daily mean (7 days observed)")} <small>{displayUnit("uGy/h")}</small>
      </figcaption>
      <ol>
        {days.map((item) => (
          <li key={item.index} title={item.mean === null ? tr("sin lecturas", "no readings") : `${formatNumber(item.mean, 2)} ${displayUnit("uGy/h")}`}>
            <span className="rad-week-bar" aria-hidden="true">
              <span style={{ height: `${top > 0 && item.mean !== null ? ((item.mean / top) * 100).toFixed(1) : 0}%` }} />
            </span>
            <span className="num">{item.mean === null ? "—" : formatNumber(item.mean, 1)}</span>
            <small>{item.index === 6 ? tr("hoy", "today") : `${formatNumber(item.index - 6)} d`}</small>
          </li>
        ))}
      </ol>
    </figure>
  );
}

/** La raya de lo secundario de esta sección; la usan los paneles y las anclas de `RadNav`. */
const RAD_FOLD = "crew.radiation";

/**
 * Todas las piezas, en el orden de la rejilla. `CrewConsole` las monta tras la ubicación de «Inicio».
 *
 * Arriba de la raya, lo que el tripulante mira de un vistazo (decisión del usuario, 2026-11-15:
 * cada pestaña pliega lo secundario como «Inicio», plegado de entrada): el nivel y las alertas, el
 * aviso a bordo y el evento solar, el entorno ahora, la dosis frente a sus límites, el refugio y las
 * recomendaciones. Nada de eso se pliega nunca, porque ahí aparece lo vigente (alerta, refugio con
 * evento, acción pedida). Debajo, el fondo: espectro, efectos y pruebas de la ficha, el tripulante,
 * la ruta, las contramedidas, el historial y las series de 24 h. Cada panel plegado va envuelto por
 * separado para que no ocupe celda; el reparto de columnas de ambos lados está en la CSS.
 */
export function radiationPanels(rad: RadiationData, links?: HomeLinks, decide?: BoardDecisions): ReactNode[] {
  return [
    <RadNav rad={rad} />,
    <RadSources rad={rad} />,
    <div className="ref-col rad-status-col">
      <RadNow rad={rad} />
      <RadLevels rad={rad} />
    </div>,
    <RadWeatherNow rad={rad} />,
    <RadDosimetry rad={rad} />,
    <RadExposure rad={rad} />,
    <RadLimits rad={rad} />,
    <RadShielding rad={rad} />,
    <RadRecommendations rad={rad} decide={decide} />,
    <FoldDivider
      id={RAD_FOLD}
      what={tr("Espectro, efectos, pruebas, ruta, historial y series de 24 h", "Spectrum, effects, tests, route, history and 24 h series")}
    />,
    <Folded id={RAD_FOLD}>
      <RadSpectrum />
    </Folded>,
    <Folded id={RAD_FOLD}>
      <RadEffects rad={rad} />
    </Folded>,
    <Folded id={RAD_FOLD}>
      <RadTests rad={rad} />
    </Folded>,
    <Folded id={RAD_FOLD}>
      <RadCrew rad={rad} links={links} />
    </Folded>,
    <Folded id={RAD_FOLD}>
      <RadRoute rad={rad} />
    </Folded>,
    <Folded id={RAD_FOLD}>
      <RadManagement rad={rad} />
    </Folded>,
    <Folded id={RAD_FOLD}>
      <RadHistory rad={rad} />
    </Folded>,
    <Folded id={RAD_FOLD}>
      <RadSpaceWeather rad={rad} />
    </Folded>,
  ];
}
