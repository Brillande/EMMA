import { useEffect, useState } from "react";

import { Command } from "../components/Command";
import { DomainName } from "../components/DomainName";
import { IndicatorName } from "../components/IndicatorName";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { Pictogram } from "../icons";
import { stateMark as resourceMark } from "../advisor/resources";
import type { CrewStatus, Prediction, ProfileMatrix } from "../lib/api";
import { displayUnit, formatMinutes, formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { domainLabel } from "../lib/levels";
import { EMPTY_MARK, MISSING_MARK, UNAVAILABLE_MARK, type StateMark, prefixedPictogram, requestOutcome } from "../lib/marks";
import { type CorrelationPair, type Correlations, outlookApi } from "../lib/outlookApi";
import { freshnessOf } from "../lib/staleness";
import { CareerMeter, careerOutside } from "../radiation/RadiationScales";
import { capitalized } from "./HazardCards";
import { type Fetched, type HomeData, type HomeLinks, sectionLink } from "./HomeBoard";
import { ScatterPlot } from "./HomeCharts";
import { routeFigures } from "./missionProfile";
import "./referenceDashboard.css";
import "./nodesOutlook.css";

/**
 * La última fila de la maqueta «Panel médico espacial EMMA para la ISS» (lote «reservas», unidad 5,
 * 2026-11-14) en la pestaña «Distancia y nodos»: «Riesgos y retos de la distancia», «Correlación de
 * variables» y «Escenarios y predicción», con las tarjetas de «Inicio» (`ref-card` en la rejilla de
 * 12 columnas de `ref-home`). Ellande: «sigue faltando cosas por integrar de la foto».
 *
 * Lo que NO se copió de la maqueta, a propósito:
 * - Los porcentajes de cada reto (72 %, 31 %, 58 %…). Solo la radiación tiene una escala del
 *   backend (la dosis de carrera frente a su límite, `status.radiation.career`), y solo ella lleva
 *   barra: el medidor de «Radiación» (`CareerMeter`). Los demás retos dicen lo que hay —el nivel de
 *   cada dominio de su peligro RIDGE, con su palabra y su forma; el retardo de las efemérides; la
 *   gravedad declarada; los recuentos de recursos declarados— y lo que el perfil elegido dice de
 *   ese aspecto en su fuente (`GET /api/mission/profiles`). Sin dato, la marca y su palabra.
 * - «Correlación de variables (IA)» con sus r inventados. Los r son los de `GET /api/correlations`
 *   (`analysis/correlations.py`): Pearson sobre medias diarias de lecturas medidas del tripulante,
 *   30 días, n mínimo, con su intervalo, sin rótulo de «IA» y con el alcance del backend:
 *   correlación no es causa y no entra en el análisis ni en las alertas. Un par sin días bastantes
 *   dice cuántos tiene; la dispersión dibuja los días reales del par elegido.
 * - «Riesgo: ↓ reservas de vitamina D (70 % en 28 d)» y la «recomendación» redactada. Los escenarios
 *   son las proyecciones PREDICHAS del estado (`status.predictions`), la dosis proyectada al fin de
 *   misión (`status.radiation.projection`), cuántas proyecciones pasadas acertaron
 *   (`status.forecast_checks`) y la primera recomendación del backend tal cual (invariante 7: la
 *   interfaz no redacta texto clínico).
 *
 * Sigue al perfil elegido: su nombre en cada título, sus frases por aspecto en los retos, y las
 * cifras de efemérides y gravedad solo si es el declarado (`routeFigures`, como «Rutas espaciales»).
 *
 * COLORES DE ADORNO: el borde de las tarjetas y los puntos de la dispersión son los de «Inicio»
 * (§2.5 de `compliance/hmi-state-of-the-art.md`); lo que es dato conserva el color de su marca.
 */

/** Nombre corto de rótulo por perfil, el mismo de «Inicio»; el del backend va en `title`. */
const PROFILE_SHORT: Record<string, string> = {
  leo: tr("Órbita baja", "Low Earth orbit"),
  cislunar: "Cislunar",
  "lunar-surface": tr("Luna", "Moon"),
  "mars-transit": tr("Tránsito a Marte", "Mars transit"),
  "mars-surface": tr("Marte", "Mars"),
};

/**
 * Cada cuánto se vuelven a pedir las correlaciones con la pestaña a la vista: son de 30 días y la
 * relectura del estado llega cada 5 s. Al cambiar de tripulante o volver a la pestaña, en el acto.
 */
const CORRELATION_REFRESH_MS = 10 * 60 * 1000;
/** Cuántas proyecciones caben en «Escenarios y predicción». */
export const SCENARIO_ROWS = 3;

type Profile = ProfileMatrix["profiles"][number];

/** Las piezas reciben lo mismo que el resto de la pestaña. */
export interface NodesOutlookProps {
  home: HomeData;
  links?: HomeLinks | undefined;
  /** El perfil de misión enseñado (la ubicación elegida); por omisión, `home.shownRoute`. */
  profileId?: string | null | undefined;
  /** Si la pestaña está a la vista: oculta, no pide nada. */
  active?: boolean | undefined;
}

/** La correlación del tripulante, pedida con la referencia del estado y releída como mucho cada diez minutos. */
export function useCorrelations(home: HomeData, active = true): Fetched<Correlations> {
  const [value, setValue] = useState<Fetched<Correlations>>({ state: "loading" });
  const subject = home.status.subject;
  const reference = home.status.data.reference_time;
  const bucket = Math.floor(Date.parse(reference) / CORRELATION_REFRESH_MS);
  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    outlookApi
      .correlations(subject, reference)
      .then((body) => {
        if (current) setValue({ state: "ready", value: body });
      })
      .catch((reason: unknown) => {
        if (current) setValue({ state: "failed", outcome: requestOutcome(reason) });
      });
    return () => {
      current = false;
    };
    // `reference` entra por su tramo (`bucket`), no por cada relectura.
  }, [active, subject, bucket]);
  return value;
}

/** Las tres tarjetas, con su petición. Lo coloca la consola en la pestaña «Distancia y nodos». */
export function NodesOutlook({ home, links, profileId, active = true }: NodesOutlookProps) {
  const correlations = useCorrelations(home, active);
  return <NodesOutlookView home={home} links={links} profileId={profileId} correlations={correlations} />;
}

/** Las tarjetas sin peticiones: se pintan con lo recibido (así se prueban sin red ni DOM). */
export function NodesOutlookView({
  home,
  links,
  profileId,
  correlations,
}: NodesOutlookProps & { correlations: Fetched<Correlations> }) {
  const profile = shownProfile(home, profileId);
  return (
    <>
      <DistanceRisks home={home} links={links} profile={profile} />
      <VariableCorrelations correlations={correlations} profile={profile} />
      <Scenarios home={home} links={links} profile={profile} />
    </>
  );
}

/** El perfil enseñado (el elegido o, sin elección, el de `home.shownRoute`), o `null`. */
export function shownProfile(home: HomeData, profileId: string | null | undefined): Profile | null {
  const shown = profileId === undefined ? home.shownRoute : profileId;
  return home.matrix?.profiles.find((item) => item.id === shown) ?? null;
}

function profileShort(profile: Profile | null): string | null {
  return profile === null ? null : (PROFILE_SHORT[profile.id] ?? capitalized(profile.display));
}

/** «(Tránsito a Marte)» tras un título, con el nombre del backend en `title`. */
function ProfileTag({ profile }: { profile: Profile | null }) {
  const short = profileShort(profile);
  if (short === null || profile === null) return null;
  return (
    <span className="secondary" title={capitalized(profile.display)}>
      {" "}
      ({short})
    </span>
  );
}

/** Un reto de la distancia: su peligro RIDGE, el aspecto del perfil que lo cuenta y lo que hay. */
export interface Challenge {
  key: "radiation" | "isolation" | "gravity" | "latency" | "resources";
  label: string;
  /** El peligro RIDGE cuyos dominios dan el nivel; `null` si el reto no es un peligro. */
  hazard: string | null;
  /** El aspecto de `GET /api/mission/profiles` que dice lo de este reto en el perfil elegido. */
  aspect: string;
}

export const CHALLENGES: readonly Challenge[] = [
  { key: "radiation", label: tr("Radiación acumulada", "Accumulated radiation"), hazard: "radiation", aspect: "radiation_environment" },
  {
    key: "isolation",
    label: tr("Aislamiento y confinamiento", "Isolation and confinement"),
    hazard: "isolation",
    aspect: "return_or_evacuation",
  },
  { key: "gravity", label: tr("Campos gravitatorios", "Gravity fields"), hazard: "gravity", aspect: "gravity_regime" },
  { key: "latency", label: tr("Latencia de comunicación", "Communication latency"), hazard: "distance", aspect: "comm_delay" },
  { key: "resources", label: tr("Disponibilidad de recursos", "Resource availability"), hazard: null, aspect: "resupply" },
];

/** La frase del perfil para un aspecto, o `null`; la de «sin fuente» del backend se marca aparte. */
export function aspectText(profile: Profile | null, aspect: string): string | null {
  return profile?.cells.find((cell) => cell.key === aspect)?.text ?? null;
}

/** Cuántos recursos hay en cada estado declarado; el total es el vocabulario entero. */
export interface ResourceCounts {
  available: number;
  unavailable: number;
  undeclared: number;
  total: number;
}

export function resourceCounts(resources: CrewStatus["mission"]["available_resources"]): ResourceCounts | null {
  if (resources === undefined || resources === null) return null;
  const available = resources.declared.filter((row) => row.state === "available").length;
  const unavailable = resources.declared.filter((row) => row.state === "unavailable").length;
  const undeclared = resources.undeclared_count;
  return { available, unavailable, undeclared, total: resources.declared.length + undeclared };
}

/** Los dominios de un peligro con su nivel del backend, sin agregar (como «Inicio»). */
function HazardLevels({ home, hazard }: { home: HomeData; hazard: string }) {
  const group = home.groups.find((item) => item.hazard === hazard);
  if (group === undefined || group.domains.length === 0) {
    return <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin nivel", "no level")}</MarkOf>;
  }
  return (
    <ul className="no-levels">
      {group.domains.map((domain) => {
        const level = home.status.domains[domain]?.level;
        return (
          <li key={domain} title={domainLabel(domain)}>
            <span className="sr-only">
              <DomainName domain={domain} />{" "}
            </span>
            {level === undefined ? (
              <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin nivel", "no level")}</MarkOf>
            ) : (
              <LevelBadge level={level} />
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Lo que hay de cada reto: cifra del backend, o su marca y su palabra. */
function ChallengeMeasure({ challenge, home, profile }: { challenge: Challenge; home: HomeData; profile: Profile | null }) {
  const { status } = home;
  const declared = profile !== null && profile.declared;
  switch (challenge.key) {
    case "radiation": {
      const career = status.radiation.career;
      if (career.value_msv === null) {
        return (
          <span title={career.basis}>
            <MarkOf mark={MISSING_MARK}>{tr("sin dosis de carrera", "no career dose")}</MarkOf>
          </span>
        );
      }
      return (
        <span className="no-measure-figure">
          {!careerOutside(career.value_msv, career.limit_msv) && (
            <span title={career.limit_source}>
              <span className="num">{formatNumber(career.value_msv, 1)}</span> {tr("de", "of")}{" "}
              <span className="num">{formatNumber(career.limit_msv)}</span> mSv
            </span>
          )}
          <CareerMeter
            value={career.value_msv}
            limit={career.limit_msv}
            label={tr("Dosis de carrera sobre el límite de carrera", "Career dose against the career limit")}
          />
        </span>
      );
    }
    case "latency": {
      const figures = routeFigures(
        declared,
        status.comms !== null,
        freshnessOf(status.freshness?.comms),
        status.mission.profile?.ephemeris?.state,
      );
      if (figures.kind === "absent" || status.comms === null) {
        const absent = figures.kind === "absent" ? figures : { mark: MISSING_MARK, word: tr("sin efemérides", "no ephemeris") };
        return <MarkOf mark={absent.mark}>{absent.word}</MarkOf>;
      }
      const shown = (
        <>
          {formatMinutes(status.comms.one_way_minutes)} <small>{tr("ida", "one way")}</small>
        </>
      );
      return figures.stale ? (
        <MarkOf mark={MISSING_MARK} className="num">
          {shown}
        </MarkOf>
      ) : (
        <span className="num">{shown}</span>
      );
    }
    case "gravity":
      return declared ? (
        <span className="ref-clamp-2" title={status.mission.gravity_display}>
          {status.mission.gravity_display}
        </span>
      ) : (
        <MarkOf mark={MISSING_MARK}>{tr("solo del perfil declarado", "declared profile only")}</MarkOf>
      );
    case "resources": {
      const counts = resourceCounts(status.mission.available_resources);
      if (counts === null || counts.total === 0) {
        return <MarkOf mark={UNAVAILABLE_MARK}>{tr("no disponible", "not available")}</MarkOf>;
      }
      return <ResourceBar counts={counts} />;
    }
    case "isolation":
      // El aislamiento no tiene cifra propia en el backend: su nivel (a la derecha) y la frase del perfil.
      return <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin cifra propia", "no figure of its own")}</MarkOf>;
  }
}

/** Los recursos del vocabulario por estado declarado: los recuentos del backend, sin porcentaje. */
function ResourceBar({ counts }: { counts: ResourceCounts }) {
  const parts: { state: keyof Omit<ResourceCounts, "total">; word: string; mark: StateMark }[] = [
    { state: "available", word: tr("disponibles", "available"), mark: resourceMark("available") },
    { state: "unavailable", word: tr("no disponibles", "not available"), mark: resourceMark("unavailable") },
    { state: "undeclared", word: tr("sin declarar", "not declared"), mark: resourceMark("undeclared") },
  ];
  return (
    <span className="no-measure-figure">
      <span className="no-stack" aria-hidden="true">
        {parts.map((part) =>
          counts[part.state] === 0 ? null : (
            <span key={part.state} data-state={part.state} style={{ flexGrow: counts[part.state] }} />
          ),
        )}
      </span>
      <span className="no-counts">
        {parts
          .filter((part) => counts[part.state] > 0)
          .map((part) => (
            <MarkOf key={part.state} mark={part.mark}>
              <span className="num">{formatNumber(counts[part.state])}</span> {part.word}
            </MarkOf>
          ))}
      </span>
    </span>
  );
}

function DistanceRisks({ home, links, profile }: { home: HomeData; links?: HomeLinks | undefined; profile: Profile | null }) {
  const noSource = home.matrix?.no_source ?? null;
  const toHazards = sectionLink(links, "hazards");
  return (
    <section
      data-ui="nodes-distance-risks"
      className="ref-card no-risks"
      aria-label={tr("Riesgos y retos de la distancia", "Risks and challenges of distance")}
    >
      <PanelTitle pictogram={prefixedPictogram("ridge", "distance")} className="ref-h">
        {tr("Riesgos y retos de la distancia", "Risks and challenges of distance")}
        <ProfileTag profile={profile} />
      </PanelTitle>
      <ul className="no-challenges">
        {CHALLENGES.map((challenge) => {
          const text = aspectText(profile, challenge.aspect);
          return (
            <li key={challenge.key} data-challenge={challenge.key} title={text ?? undefined}>
              <span className="no-challenge-name">
                <Pictogram name={prefixedPictogram("ridge", challenge.hazard ?? "environment")} />
                <strong>{challenge.label}</strong>
              </span>
              <span className="no-challenge-measure">
                <ChallengeMeasure challenge={challenge} home={home} profile={profile} />
              </span>
              <span className="no-challenge-level">
                {challenge.hazard === null ? null : <HazardLevels home={home} hazard={challenge.hazard} />}
              </span>
              {text !== null && (
                <span className="no-challenge-aspect ref-clamp-2" title={text}>
                  {text === noSource ? <MarkOf mark={UNAVAILABLE_MARK}>{text}</MarkOf> : <span className="secondary">{text}</span>}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {profile === null && (
        <p className="secondary">
          {tr("Sin perfil de misión declarado ni ruta elegida.", "No mission profile declared and no route chosen.")}
        </p>
      )}
      {toHazards !== null && (
        <div className="ref-quick-links no-open">
          <Command
            concept="detail"
            type="button"
            onClick={toHazards.open}
            aria-label={tr(`Abrir ${toHazards.name}: niveles por peligro`, `Open ${toHazards.name}: levels by hazard`)}
          >
            <span>{tr("Ver niveles por peligro", "View levels by hazard")}</span>
          </Command>
        </div>
      )}
    </section>
  );
}

/** El primer par con r, o el primero si ninguno lo tiene. */
export function defaultPair(pairs: readonly CorrelationPair[]): number {
  const index = pairs.findIndex((pair) => pair.state === "computed");
  return index === -1 ? 0 : index;
}

/** La marca de un par sin r: pocos días es un dato ausente (cian); una serie plana, no disponible (gris). */
export function pairMark(pair: CorrelationPair): StateMark | null {
  if (pair.state === "computed") return null;
  return pair.state === "insufficient" ? MISSING_MARK : UNAVAILABLE_MARK;
}

/** Pares que se ven sin desplegar, como las tres «correlaciones relevantes» de la maqueta. */
export const PAIR_ROWS = 3;

/**
 * Los pares con r primero, de mayor a menor |r|; después los que no tienen días suficientes y al
 * final las series sin variación. Ordena para enseñar; no filtra ni decide nada (descriptivo).
 */
export function orderedPairs(pairs: readonly CorrelationPair[]): CorrelationPair[] {
  const rank = (pair: CorrelationPair) => (pair.state === "computed" ? 0 : pair.state === "insufficient" ? 1 : 2);
  return [...pairs].sort((a, b) => rank(a) - rank(b) || Math.abs(b.r ?? 0) - Math.abs(a.r ?? 0));
}

function pairKey(pair: CorrelationPair): string {
  return `${pair.x.key}|${pair.y.key}`;
}

function VariableCorrelations({ correlations, profile }: { correlations: Fetched<Correlations>; profile: Profile | null }) {
  const [chosen, setChosen] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const body = correlations.state === "ready" ? correlations.value : null;
  const pairs = orderedPairs(body?.pairs ?? []);
  const hidden = all ? 0 : Math.max(0, pairs.length - PAIR_ROWS);
  const found = pairs.findIndex((pair) => pairKey(pair) === chosen);
  const selected = pairs[found === -1 ? defaultPair(pairs) : found] ?? null;
  return (
    <section
      data-ui="nodes-correlations"
      className="ref-card no-corr"
      aria-label={tr("Correlación de variables", "Variable correlation")}
    >
      <PanelTitle concept="compare" className="ref-h">
        {tr("Correlación de variables", "Variable correlation")}
        {body !== null && (
          <span className="secondary">
            {" "}
            {tr(`(últimos ${formatNumber(body.window_days)} d)`, `(last ${formatNumber(body.window_days)} d)`)}
          </span>
        )}
        <ProfileTag profile={profile} />
      </PanelTitle>
      {correlations.state === "loading" && <Loading />}
      {correlations.state === "failed" && <Unavailable outcome={correlations.outcome} />}
      {body !== null && (
        <>
          <div className="no-corr-grid">
            <ul className="no-pairs" aria-label={tr("Pares", "Pairs")}>
              {pairs.slice(0, pairs.length - hidden).map((pair) => {
                const mark = pairMark(pair);
                const key = pairKey(pair);
                return (
                  <li key={key} data-pair={key}>
                    <button
                      type="button"
                      className="no-pair"
                      aria-pressed={pair === selected}
                      title={`${capitalized(pair.theme)}: ${pair.text}`}
                      onClick={() => setChosen(key)}
                    >
                      <span className="no-pair-names">
                        <IndicatorName indicatorKey={pair.x.key} displayEs={pair.x.display_es} /> ·{" "}
                        <IndicatorName indicatorKey={pair.y.key} displayEs={pair.y.display_es} />
                      </span>
                      {mark === null && pair.r !== null ? (
                        <span className="num no-pair-r">
                          r = {formatNumber(pair.r, 2)} <small>(n = {formatNumber(pair.n)})</small>
                        </span>
                      ) : (
                        <MarkOf mark={mark ?? UNAVAILABLE_MARK}>
                          {pair.state === "insufficient" ? (
                            <>
                              n = <span className="num">{formatNumber(pair.n)}</span> d
                            </>
                          ) : (
                            tr("sin variación", "no variation")
                          )}
                        </MarkOf>
                      )}
                    </button>
                  </li>
                );
              })}
              {pairs.length > PAIR_ROWS && (
                <li>
                  <button type="button" className="no-pair no-pair-more" aria-expanded={all} onClick={() => setAll(!all)}>
                    {all
                      ? tr("Ver menos pares", "Show fewer pairs")
                      : tr(
                          `Ver los ${formatNumber(pairs.length)} pares (${formatNumber(hidden)} más)`,
                          `Show all ${formatNumber(pairs.length)} pairs (${formatNumber(hidden)} more)`,
                        )}
                  </button>
                </li>
              )}
            </ul>
            {selected !== null && <Scatter pair={selected} />}
          </div>
          {selected !== null && (
            <p className="no-corr-text">
              {pairMark(selected) === null ? (
                <span>{selected.text}</span>
              ) : (
                <MarkOf mark={pairMark(selected) ?? MISSING_MARK}>{selected.text}</MarkOf>
              )}
              {selected.simulated && <span className="secondary"> {body.simulated_text}</span>}
            </p>
          )}
          <p className="secondary no-corr-scope ref-clamp-2" title={`${body.method} ${body.multiple} ${body.pairs_basis}`}>
            {body.scope} {body.multiple}
          </p>
        </>
      )}
    </section>
  );
}

/** La dispersión de los días reales del par (el dibujo vive en `HomeCharts`, con los demás). */
function Scatter({ pair }: { pair: CorrelationPair }) {
  if (pair.points.length === 0) {
    return (
      <div className="no-scatter no-scatter-empty">
        <MarkOf mark={EMPTY_MARK}>{tr("sin días con las dos series", "no days with both series")}</MarkOf>
      </div>
    );
  }
  const points = pair.points.map((point) => ({
    key: point.day,
    x: point.x,
    y: point.y,
    title: `${point.day}: ${formatNumber(point.x, pair.x.decimals)} ${displayUnit(pair.x.unit)} · ${formatNumber(point.y, pair.y.decimals)} ${displayUnit(pair.y.unit)}`,
  }));
  const label = tr(
    `Dispersión de ${pair.x.display_es} frente a ${pair.y.display_es}: ${formatNumber(points.length)} días`,
    `Scatter of ${pair.x.display_es} against ${pair.y.display_es}: ${formatNumber(points.length)} ${points.length === 1 ? "day" : "days"}`,
  );
  return (
    <figure className="no-scatter">
      <ScatterPlot points={points} label={label} />
      <figcaption className="secondary">
        <span title={pair.x.display_es}>x: {displayUnit(pair.x.unit)}</span> ·{" "}
        <span title={pair.y.display_es}>y: {displayUnit(pair.y.unit)}</span>
      </figcaption>
    </figure>
  );
}

/** Las proyecciones a enseñar: las que el motor juzga preocupantes primero, como mucho `SCENARIO_ROWS`. */
export function scenarioRows(predictions: readonly Prediction[]): Prediction[] {
  return predictions
    .map((item, index) => ({ item, index }))
    .sort((a, b) => Number(b.item.concerning) - Number(a.item.concerning) || a.index - b.index)
    .slice(0, SCENARIO_ROWS)
    .map(({ item }) => item);
}

function signed(value: number, decimals: number): string {
  return `${value > 0 ? "+" : ""}${formatNumber(value, decimals)}`;
}

function Scenarios({ home, links, profile }: { home: HomeData; links?: HomeLinks | undefined; profile: Profile | null }) {
  const { status } = home;
  const rows = scenarioRows(status.predictions);
  const projection = status.radiation.projection ?? null;
  const checks = status.forecast_checks;
  const recommendation = status.recommendations[0] ?? null;
  const toHazards = sectionLink(links, "hazards");
  return (
    <section
      data-ui="nodes-scenarios"
      className="ref-card no-scen"
      aria-label={tr("Escenarios y predicción", "Scenarios and prediction")}
    >
      <PanelTitle concept="predictions" className="ref-h">
        {tr("Escenarios y predicción", "Scenarios and prediction")}
        <ProfileTag profile={profile} />
      </PanelTitle>
      {profile !== null && !profile.declared && (
        <p className="secondary no-scen-note">
          {tr(
            "Del tripulante en la misión declarada: la ruta elegida no las cambia.",
            "For the crew member on the declared mission: the chosen route does not change them.",
          )}
        </p>
      )}
      {rows.length === 0 ? (
        <p>
          <MarkOf mark={EMPTY_MARK}>
            {tr("Sin proyecciones para este tripulante.", "No projections for this crew member.")}
          </MarkOf>
        </p>
      ) : (
        <ul className="no-scen-list">
          {rows.map((item) => (
            <li key={item.key} title={item.basis}>
              <Mark pictogram={null} color={item.concerning ? "yellow" : null}>
                <span className="ref-ellipsis no-scen-name">
                  <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
                </span>
              </Mark>
              <span className="num">
                {signed(item.projected_change, item.decimals)} {displayUnit(item.unit)}
              </span>
              <small className="secondary">
                {tr("en", "in")} <span className="num">{formatNumber(item.horizon_weeks)}</span> {tr("sem.", "wk")}
              </small>
            </li>
          ))}
        </ul>
      )}
      <dl className="no-scen-facts">
        <dt>{tr("Dosis al fin de misión", "Dose at end of mission")}</dt>
        <dd>
          {projection === null ? (
            <MarkOf mark={MISSING_MARK}>{tr("sin dosis que prolongar", "no dose to extend")}</MarkOf>
          ) : projection.value_msv === null ? (
            <span className="secondary ref-clamp-2" title={projection.basis}>
              {projection.basis}
            </span>
          ) : (
            <span title={projection.basis}>
              <span className="num">{formatNumber(projection.value_msv, 1)}</span> mSv{" "}
              <ObservationTypeBadge type={projection.observation_type} />
            </span>
          )}
        </dd>
        <dt>{tr("Proyecciones comprobadas", "Projections checked")}</dt>
        <dd title={checks.basis}>
          {checks.checked === 0 ? (
            <MarkOf mark={EMPTY_MARK}>{tr("ninguna aún", "none yet")}</MarkOf>
          ) : (
            <>
              <span className="num">{formatNumber(checks.within_margin)}</span> {tr("de", "of")}{" "}
              <span className="num">{formatNumber(checks.checked)}</span> {tr("dentro del margen", "within margin")}
            </>
          )}
        </dd>
      </dl>
      {recommendation !== null && (
        <p className="no-scen-rec" title={recommendation.rationale}>
          <Mark pictogram={null} color="magenta">
            <span className="ref-clamp-2">{recommendation.action}</span>
          </Mark>
        </p>
      )}
      {toHazards !== null && (
        <div className="ref-quick-links no-open">
          <Command
            concept="detail"
            type="button"
            onClick={toHazards.open}
            aria-label={tr(
              `Abrir ${toHazards.name}: escenarios y recomendaciones`,
              `Open ${toHazards.name}: scenarios and recommendations`,
            )}
          >
            <span>{tr("Ver escenarios y recomendaciones", "View scenarios and recommendations")}</span>
          </Command>
        </div>
      )}
    </section>
  );
}
