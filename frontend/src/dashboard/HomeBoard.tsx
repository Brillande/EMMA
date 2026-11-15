import { type CSSProperties, type ReactNode, Suspense, lazy, useEffect, useRef, useState } from "react";

import { BodySilhouette } from "../anatomy/BodySilhouette";
import type { useAnatomyState } from "../anatomy/useAnatomyState";
import { Command } from "../components/Command";
import { DomainName } from "../components/DomainName";
import { FieldLabel } from "../components/FieldLabel";
import { IndicatorName } from "../components/IndicatorName";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { Pictogram } from "../icons";
import {
  type CrewStatus,
  type DiaryEntry,
  type FhirObservation,
  type Framework,
  type Indicator,
  api,
  diaryApi,
  frameworkApi,
  helpRequestsApi,
} from "../lib/api";
import { displayUnit, formatAge, formatMet, formatMinutes, formatNumber, formatUtc, missionElapsedSeconds } from "../lib/format";
import { tr } from "../lib/i18n";
import { LEVEL_ORDER, domainLabel, isLevel, levelStyle } from "../lib/levels";
import {
  LOADING_MARK,
  MISSING_MARK,
  UNAVAILABLE_MARK,
  UNKNOWN_PICTOGRAM,
  type RequestOutcome,
  prefixedPictogram,
  requestOutcome,
} from "../lib/marks";
import { type Token, cssVar } from "../lib/palette";
import { freshnessOf } from "../lib/staleness";
import { HELP_REQUESTED_EVENT, type HelpRequestedDetail } from "../lib/help";
import { useOperator } from "../lib/operator";
import { uiPictogram } from "../lib/uiMarks";
import { LocationLine } from "../habitat/LocationSource";
import { useProfileMatrix } from "./Environments";
import { capitalized, hazardGroups, hazardLetter } from "./HazardCards";
import { AstronautArt, Chevron, PlanetThumb, RouteArt, ShelterArt, StationArt } from "./HomeArt";
import { Ring, type Reading, Segments as ToneSegments, Sparkline, TrendSvg, levelToken } from "./HomeCharts";
import { profilePictogram } from "./missionPictograms";
import { type RouteFigures, routeFigures } from "./missionProfile";
import { dataKeyOf } from "./useConsoleData";
import "./referenceDashboard.css";

/**
 * El tablero «Inicio»: la maqueta «Panel EMMA: Rutas Espaciales y Salud» (2026-11-06) hecha paneles
 * de la consola (decisión del usuario, 2026-11-07: este diseño es la consola real). Cada pieza es un
 * panel con su `data-ui`, del tamaño que la privacidad tapa (`personal(…)` en la tabla de
 * `CrewConsole`), y todas leen los mismos datos (`useHomeData`): el estado que la consola ya tiene,
 * más el marco RIDGE, el catálogo, las series de las cuatro constantes, el diario y los perfiles de
 * misión. `CrewConsole` las monta en la rejilla de la maqueta como sección «Inicio».
 *
 * COLORES DE ADORNO (decisión del usuario, 2026-11-07): para parecerse a la maqueta, el tablero da
 * un color a cada letra RIDGE, a cada curva vital, a los planetas y al cuerpo. Esos colores NO
 * significan nada; se declaran como desviación consciente de F.5.10 en `compliance/`. Lo que es
 * dato (el nivel de cada dominio, los valores, las marcas de lo que falta o falló) conserva su
 * color, su forma y su palabra del backend.
 *
 * Lo que no se copió de la maqueta (decisiones del usuario, 2026-11-06): sin «Índice RIDGE 0–100»
 * (el motor no lo calcula: el anillo cuenta dominios en el nivel más bajo y cada peligro enseña los
 * niveles de sus dominios sin agregarlos, `HazardCards`); la sigla es la de NASA, la del backend;
 * sin cifras de impacto inventadas (distancia y retardo de las efemérides, proyecciones PREDICHAS del
 * estado, aspectos del perfil con sus palabras); sin foto: el backend no la da. La sububicación sí
 * (2026-11-09): el módulo de `mission.location` del estado, con quién lo puso (`ModuleLine`); desde
 * 2026-11-10, real: declarada en la consola o estimada por las anclas de módulo, nunca simulada.
 */

// El cuerpo de la maqueta (1,5 MB de píxeles y capas) se trae al abrir el tablero, no con la consola.
const ReferenceBody = lazy(() => import("./ReferenceBody"));

const VITALS = ["heart-rate", "respiratory-rate", "oxygen-saturation", "body-temperature"] as const;
type Vital = (typeof VITALS)[number];
/** Abreviaturas de rótulo; el nombre completo del catálogo va en `title`. */
const VITAL_SHORT: Record<Vital, string> = {
  "heart-rate": tr("FC", "HR"),
  "respiratory-rate": tr("FR", "RR"),
  "oxygen-saturation": "SpO₂",
  "body-temperature": "Temp.",
};
/** Nombre corto de rótulo por perfil; el nombre del backend va en `title` y en `aria-label`. */
const PROFILE_SHORT: Record<string, string> = {
  leo: tr("Órbita baja", "Low orbit"),
  cislunar: "Cislunar",
  "lunar-surface": tr("Luna", "Moon"),
  "mars-transit": tr("Tránsito a Marte", "Mars transit"),
  "mars-surface": tr("Marte", "Mars"),
};
const KM_PER_AU = 149_597_870.7;

/** Lo que se deja libre bajo «Inicio» al llenar la ventana: el relleno inferior de `main` y un respiro. */
const FILL_BOTTOM_PX = 10;

function readingsOf(observations: readonly FhirObservation[]): Reading[] {
  return observations
    .map((obs) => ({ at: Date.parse(obs.effectiveDateTime), value: obs.valueQuantity.value }))
    .filter((item) => Number.isFinite(item.at))
    .sort((a, b) => a.at - b.at);
}

/**
 * Una petición secundaria del tablero (catálogo, series, diario…): cargando, lista o fallida con la
 * marca de su fallo (`lib/marks`: un 4xx es el triángulo amarillo con el motivo del backend, un 5xx o
 * la red caída la cruz roja; nunca texto suelto).
 */
export type Fetched<T> = { state: "loading" } | { state: "ready"; value: T } | { state: "failed"; outcome: RequestOutcome };

/** Resuelve una petición en su `Fetched`, salvo que el tablero ya se haya desmontado o cambiado de tripulante. */
function fetched<T>(promise: Promise<T>, alive: () => boolean, set: (next: Fetched<T>) => void): void {
  promise
    .then((value) => {
      if (alive()) set({ state: "ready", value });
    })
    .catch((reason: unknown) => {
      if (alive()) set({ state: "failed", outcome: requestOutcome(reason) });
    });
}

/**
 * La cifra de un vital con los decimales y la unidad de su ficha del catálogo (lógica 6). Sin la
 * ficha —el catálogo aún no ha llegado, falló o no trae ese indicador— la cifra no se enseña: antes
 * salía redondeada a entero y sin unidad (36,7 °C como «37»), y se leía como la medida.
 */
export function VitalValue({
  value,
  indicator,
  catalog,
}: {
  value: number;
  indicator: Indicator | undefined;
  catalog: Fetched<unknown>;
}) {
  if (indicator === undefined) return <VitalValueMissing catalog={catalog} />;
  return (
    <>
      <span className="num">{formatNumber(value, indicator.decimals)}</span> <small>{displayUnit(indicator.unit)}</small>
    </>
  );
}

/** Sin la ficha del catálogo: cargando mientras llega; si no, «no disponible» (gris, tabla F.5-1). */
function VitalValueMissing({ catalog }: { catalog: Fetched<unknown> }) {
  // En línea (no `Loading`, que es un párrafo): va dentro de la fila del vital.
  if (catalog.state === "loading") return <MarkOf mark={LOADING_MARK}>{tr("Cargando…", "Loading…")}</MarkOf>;
  return <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin ficha del catálogo", "no catalogue entry")}</MarkOf>;
}

/** Lo que una petición secundaria enseña mientras no está: cargando, o cómo falló. Lista, nada. */
function Pending({ item }: { item: Fetched<unknown> }) {
  if (item.state === "loading") return <Loading />;
  if (item.state === "failed") return <Unavailable outcome={item.outcome} />;
  return null;
}

/**
 * Variable `--lvl` con el color del nivel para teñir una tarjeta. Solo en este tablero, el nivel sin
 * color de alerta («text») se tiñe de verde, como el «Estable» de la maqueta (adorno declarado); las
 * secciones usan el color real (`levelTint` de `HomeCharts`).
 */
function levelTint(level: string): CSSProperties {
  return { "--lvl": `var(${cssVar(shownTone(level))})` } as CSSProperties;
}

/** El token con que este tablero pinta un nivel: el sin color de alerta, en verde (`levelTint`). */
function shownTone(level: string | undefined): Token {
  const token = levelToken(level);
  return token === null ? "gray" : token === "text" ? "green" : token;
}

/**
 * La letra RIDGE de un peligro, la misma que en «Peligros» (`hazardLetter`): un peligro que la
 * interfaz no conoce sale sin letra. Antes «Inicio» le daba su inicial y enseñaba una letra que no
 * es de la sigla mientras la sección no la daba (lógica 6).
 */
export function letterOf(hazard: string): string {
  return hazardLetter(hazard) ?? "";
}

/** Adónde llevan los accesos del tablero cuando está dentro de la consola; sin ellos, no se enseñan. */
export interface HomeLinks {
  /** Abre una sección de la consola de tripulación por su clave (`body`, `data`, `log`…). */
  openSection?: (key: string) => void;
  /**
   * El nombre de la sección `key` si ahora se puede abrir, o `null` si no está a la vista: en modo
   * esencial solo lo están las esenciales, y abrir otra devolvía a «Inicio» sin decir nada (el
   * efecto de `ConsoleTabs` reescribe la guardada). Sin él no hay accesos: el nombre va en el
   * rótulo de cada uno («Abrir Cuerpo: …»).
   */
  sectionName?: (key: string) => string | null;
  /** Enciende el modo esencial (los mandos de «Pantalla»). */
  essential?: () => void;
}

/** Un acceso a una sección que ahora se puede abrir: su nombre y cómo abrirla. */
interface SectionLink {
  name: string;
  open: () => void;
}

/** El acceso a `key`, o `null` si el tablero no está en la consola o la sección no está a la vista. */
export function sectionLink(links: HomeLinks | undefined, key: string): SectionLink | null {
  const open = links?.openSection;
  const name = links?.sectionName?.(key) ?? null;
  if (open === undefined || name === null) return null;
  return { name, open: () => open(key) };
}

/**
 * Inicio no enlazaba sus tarjetas con las partes del programa (lo pidió el usuario, 2026-11-09): un
 * peligro, el estado de riesgo o una constante se veían pero no llevaban a su sección. El acceso es
 * un botón transparente tendido encima de la tarjeta o la fila (`.ref-go`), no la tarjeta hecha
 * botón: así la tarjeta no cambia de aspecto ni de caja, y dentro del botón no queda nada que se
 * pueda accionar. Sin acceso (fuera de la consola, o sección fuera de la vista) no se pinta nada.
 */
function GoTo({
  link,
  what,
  detail,
  pointerOnly = false,
}: {
  link: SectionLink | null;
  what: string;
  /** Lo que decían los `title` que el botón tapa: viaja en el suyo, debajo del rótulo. */
  detail?: string;
  /**
   * Fuera del orden de tabulación: cada peligro sale tres veces en «Inicio» (barras globales, letras
   * y acceso rápido) y llevan al mismo sitio; con el teclado basta el acceso rápido, que es el suyo,
   * y así no hay quince paradas iguales antes de llegar a las rutas (revisión de la unidad 2).
   */
  pointerOnly?: boolean;
}) {
  if (link === null) return null;
  const label = tr(`Abrir ${link.name}: ${what}`, `Open ${link.name}: ${what}`);
  const title = detail === undefined || detail === "" ? label : `${label}\n${detail}`;
  return (
    <button
      type="button"
      className="ref-go"
      aria-label={label}
      title={title}
      tabIndex={pointerOnly ? -1 : undefined}
      onClick={link.open}
    />
  );
}

/** «Dominio: nivel · …» de un peligro, lo que dicen los `title` de sus segmentos. */
function domainLevels(domains: readonly string[], status: CrewStatus): string {
  return domains
    .map((domain) => {
      const level = status.domains[domain]?.level;
      return `${domainLabel(domain)}: ${level !== undefined && isLevel(level) ? levelStyle(level).label : tr("sin nivel", "no level")}`;
    })
    .join(" · ");
}

/** La clase de lo que lleva un `GoTo` encima (le da la caja a la que se ciñe). */
function linked(link: SectionLink | null, className = ""): string | undefined {
  const classes = link === null ? className : `${className} ref-linked`.trim();
  return classes === "" ? undefined : classes;
}

/** Lo que las piezas del tablero comparten: el estado y las peticiones secundarias con su suerte. */
export interface HomeData {
  status: CrewStatus;
  /** La referencia del estado, en milisegundos. */
  reference: number;
  ridge: Fetched<Framework["ridge"]>;
  groups: ReturnType<typeof hazardGroups>;
  indicators: Fetched<Indicator[]>;
  catalog: Map<string, Indicator>;
  seriesOf: (key: Vital) => Fetched<Reading[]>;
  readingsFor: (key: Vital) => Reading[];
  diary: Fetched<DiaryEntry[]>;
  matrix: ReturnType<typeof useProfileMatrix>["matrix"];
  matrixFailure: RequestOutcome | null;
  /** El perfil enseñado en la ruta: el elegido a mano o el declarado. */
  shownRoute: string | null;
  setRoute: (id: string) => void;
  declaredShort: string | null;
  anatomy: ReturnType<typeof useAnatomyState>;
  region: string | null;
  setRegion: (region: string | null) => void;
  /** El nivel más bajo de la escala y cuántos dominios están en él. */
  lowest: string;
  atLowest: number;
  domainCount: number;
  overall: string;
  overallStyle: ReturnType<typeof levelStyle> | null;
  elapsed: number;
}

/** El estado por regiones y la región elegida: quien monta el tablero los posee (la consola ya los tiene). */
export interface HomeAnatomy {
  anatomy: ReturnType<typeof useAnatomyState>;
  region: string | null;
  setRegion: (region: string | null) => void;
  /** Si «Inicio» está a la vista. Oculto, no se piden sus datos: se piden al volver a él. */
  active?: boolean;
}

/**
 * Las peticiones secundarias del tablero y lo derivado del estado, una sola vez para todas las piezas.
 * La anatomía la trae quien llama: en la consola es la misma que la del modo anatómico (una sola
 * petición), y pulsar una región en la silueta de «Inicio» la elige para toda la consola.
 */
export function useHomeData(status: CrewStatus, { anatomy, region, setRegion, active = true }: HomeAnatomy): HomeData {
  const [ridge, setRidge] = useState<Fetched<Framework["ridge"]>>({ state: "loading" });
  const [indicators, setIndicators] = useState<Fetched<Indicator[]>>({ state: "loading" });
  const [series, setSeries] = useState<Partial<Record<Vital, Fetched<Reading[]>>>>({});
  const [diary, setDiary] = useState<Fetched<DiaryEntry[]>>({ state: "loading" });
  const { matrix, failure: matrixFailure } = useProfileMatrix(status.mission.profile?.id);
  const [route, setRoute] = useState<string | null>(null);
  const reference = Date.parse(status.data.reference_time);
  // Al cambiar de tripulante, sus series y su diario se retiran antes de pedir los nuevos; una
  // relectura del mismo tripulante (otra referencia) los conserva mientras llegan.
  const lastSubject = useRef(status.subject);
  // Lo que mueve las series: una lectura nueva (el recuento o la última lectura) o las fuentes. Con
  // solo `reference_time`, las lecturas en vivo de la banda de pulso no redibujaban las gráficas.
  const dataKey = dataKeyOf(status);

  // El marco RIDGE y el catálogo no dependen de las lecturas: no se repiten con cada relectura en
  // vivo (cada 5 s), solo al volver a «Inicio».
  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    const alive = () => current;
    fetched(frameworkApi.get().then((body) => body.ridge), alive, setRidge);
    fetched(api.indicators().then((body) => body.indicators), alive, setIndicators);
    return () => {
      current = false;
    };
  }, [active]);

  useEffect(() => {
    let current = true;
    const alive = () => current;
    if (lastSubject.current !== status.subject) {
      lastSubject.current = status.subject;
      setSeries({});
      setDiary({ state: "loading" });
    }
    // Con «Inicio» oculto (otra sección abierta), cada relectura del estado disparaba estas peticiones
    // para nada (lo señaló la revisión de la unidad 2); al volver a la sección, `active` cambia y se
    // piden con las lecturas de entonces. Si nada ha cambiado (misma clave), no se vuelven a pedir.
    if (!active) return undefined;
    // Una petición por constante: si una falla, las demás siguen con sus curvas. Una constante que
    // el tripulante no tiene (la banda de pulso no da ni SpO2 ni temperatura) llega vacía y la
    // tarjeta pone su marca de «sin lecturas»: las series se retiran al cambiar de tripulante.
    for (const key of VITALS) {
      fetched(
        api.observations(key, 600, status.subject).then((body) => readingsOf(body.observations)),
        alive,
        (next) => setSeries((previous) => ({ ...previous, [key]: next })),
      );
    }
    fetched(diaryApi.entries(status.subject, 2).then((body) => body.entries), alive, setDiary);
    return () => {
      current = false;
    };
  }, [status.subject, dataKey, active]);

  const groups = ridge.state === "ready" ? hazardGroups(ridge.value, Object.keys(status.domains)) : [];
  const domainLevels = Object.values(status.domains).map((risk) => risk.level);
  const lowest = LEVEL_ORDER[0] ?? "nominal";
  const catalog = new Map((indicators.state === "ready" ? indicators.value : []).map((item) => [item.key, item]));
  const seriesOf = (key: Vital): Fetched<Reading[]> => series[key] ?? { state: "loading" };
  const readingsFor = (key: Vital): Reading[] => {
    const item = seriesOf(key);
    return item.state === "ready" ? item.value : [];
  };
  const declaredId = matrix?.declared_id ?? status.mission.profile?.id ?? null;
  const declaredProfile = matrix?.profiles.find((item) => item.declared) ?? null;
  const overall = status.overall_level;
  return {
    status,
    reference,
    ridge,
    groups,
    indicators,
    catalog,
    seriesOf,
    readingsFor,
    diary,
    matrix,
    matrixFailure,
    shownRoute: route ?? declaredId,
    setRoute,
    declaredShort:
      declaredProfile === null ? null : (PROFILE_SHORT[declaredProfile.id] ?? capitalized(declaredProfile.display)),
    anatomy,
    region,
    setRegion,
    lowest,
    atLowest: domainLevels.filter((level) => level === lowest).length,
    domainCount: domainLevels.length,
    overall,
    overallStyle: isLevel(overall) ? levelStyle(overall) : null,
    elapsed: missionElapsedSeconds(status.mission.start, new Date(status.data.reference_time)),
  };
}

type Piece = { home: HomeData; links?: HomeLinks | undefined };

/** Ubicación: los perfiles de misión del backend, con su miniatura; el declarado, marcado. Y el módulo del estado. */
export function HomePlaces({ home }: Piece) {
  const { matrix, matrixFailure, shownRoute, setRoute, declaredShort } = home;
  return (
    <>
      {/* Los degradados de los dibujos (planetas, ruta, astronauta, pie) los define `App` una vez para
          las dos conchas, al final de su contenedor. */}
      <section data-ui="home-location" className="ref-card ref-places" aria-label={tr("Ubicación de la tripulación", "Crew location")}>
        <PanelTitle concept="domains" className="ref-h">
          {tr("Ubicación de la tripulación", "Crew location")}
        </PanelTitle>
        {matrix === null ? (
          matrixFailure === null ? <Loading /> : <Unavailable outcome={matrixFailure} />
        ) : (
          <div className="ref-place-row" role="group" aria-label={tr("Perfiles de misión", "Mission profiles")}>
            {matrix.profiles.map((profile) => (
              <button
                type="button"
                key={profile.id}
                className="ref-place"
                aria-pressed={profile.id === shownRoute}
                aria-label={capitalized(profile.display) + (profile.declared ? tr(" (declarado)", " (declared)") : "")}
                title={capitalized(profile.display)}
                onClick={() => setRoute(profile.id)}
              >
                <PlanetThumb id={profile.id} />
                <span>{PROFILE_SHORT[profile.id] ?? capitalized(profile.display)}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      <section data-ui="home-module" className="ref-card ref-subplace" aria-label={tr("Sububicación", "Sub-location")}>
        <PanelTitle concept="habitat" className="ref-h">
          {tr("Sububicación", "Sub-location")}{declaredShort !== null && <span className="secondary"> ({declaredShort})</span>}
        </PanelTitle>
        <p className="ref-select-like" title={home.status.mission.location_basis}>
          <ModuleLine mission={home.status.mission} reference={home.status.data.reference_time} />
        </p>
      </section>
    </>
  );
}

/**
 * El módulo del tripulante en el instante de referencia (`mission.location` del estado), con su
 * dibujo, el nombre del backend, desde cuándo hasta cuándo en tiempo de misión y si es declarada o
 * estimada por las anclas de módulo, con su antigüedad frente a `reference` (`LocationLine`). Sin
 * ubicación, la marca de `location_state` con el texto del backend.
 */
export function ModuleLine({ mission, reference }: { mission: CrewStatus["mission"]; reference: string }) {
  const met = (iso: string) => formatMet(missionElapsedSeconds(mission.start, new Date(iso)));
  return (
    <LocationLine
      location={mission.location}
      state={mission.location_state}
      missingText={mission.location_missing_text}
      reference={reference}
      met={met}
    />
  );
}

/** Marco global, como en la maqueta: estado, peligros, vitales, tendencia y silueta juntos. */
export function HomeGlobal({ home, links }: Piece) {
  const { status, reference, ridge, groups, indicators, catalog, seriesOf, readingsFor, declaredShort } = home;
  const { anatomy, region, setRegion, lowest, atLowest, domainCount, overall, overallStyle } = home;
  const toMission = sectionLink(links, "mission");
  const toHazards = sectionLink(links, "hazards");
  const toBody = sectionLink(links, "body");
  return (
    <section data-ui="home-global" className="ref-frame ref-global" aria-label={tr("Panel global de la tripulación", "Crew global panel")}>
      <PanelTitle concept="identity" className="ref-h ref-frame-h">
        {tr("Panel global: tripulación", "Global panel: crew")}
        {declaredShort !== null && <> ({declaredShort})</>}
        <span className="ref-updated secondary">
          <span className="ref-live" aria-hidden="true" />{tr(" Datos a", " Data as of")}{" "}
          <span className="num">{formatUtc(new Date(reference))}</span>
        </span>
      </PanelTitle>
      <div className="ref-global-grid">
        <article className={linked(toMission, "ref-card ref-mission")} style={levelTint(overall)} aria-label={tr("Estado de la misión", "Mission status")}>
          <GoTo link={toMission} what={tr("estado de la misión", "mission status")} detail={status.summary} />
          <h3 className="ref-h3">{tr("Estado de la misión", "Mission status")}</h3>
          <div className="ref-hero">
            <span className="ref-hero-icon" aria-hidden="true">
              <Pictogram name={overallStyle?.pictogram ?? UNKNOWN_PICTOGRAM} />
            </span>
            <strong className="ref-hero-word">{overallStyle?.label ?? overall}</strong>
          </div>
          <p className="ref-clamp secondary" title={status.summary}>
            {status.summary}
          </p>
        </article>

        <article className="ref-card ref-ridge" aria-label={tr("Peligros RIDGE", "RIDGE hazards")}>
          <h3 className="ref-h3">{tr("Peligros RIDGE (global)", "RIDGE hazards (global)")}</h3>
          <div className="ref-ridge-body">
            <div className="ref-ring-col">
              <Ring done={atLowest} total={domainCount} label={tr("dominios", "domains")}>
                <span className="num ref-ring-value">{formatNumber(atLowest)}</span>
                <span className="num secondary">/ {formatNumber(domainCount)}</span>
              </Ring>
              <p className="secondary ref-ring-caption">
                {tr("dominios en ", "domains at ")}<LevelBadge level={lowest} />
              </p>
            </div>
            <Pending item={ridge} />
            <ul className="ref-hazard-bars">
              {groups.map((group) => (
                <li
                  key={group.hazard}
                  className={linked(toHazards)}
                  title={toHazards === null ? capitalized(group.display) : undefined}
                  data-acc={group.hazard}
                >
                  <GoTo
                    link={toHazards}
                    what={capitalized(group.display)}
                    detail={domainLevels(group.domains, status)}
                    pointerOnly
                  />
                  <span className="ref-chip-letter" aria-hidden="true">
                    {letterOf(group.hazard)}
                  </span>
                  {/* Rótulo de dato: en la concha nueva pasa a dos líneas si no cabe, en vez de
                      cortarlo en una (R5-2, `referenceDashboard.css`); `#clasica` no cambia. El
                      nombre entero va en el `title` de la fila. */}
                  <span className="ref-ellipsis">{capitalized(group.display)}</span>
                  <Segments domains={group.domains} status={status} />
                  <span className="num">{formatNumber(group.domains.length)}</span>
                </li>
              ))}
            </ul>
          </div>
        </article>

        <article className={linked(toBody, "ref-card ref-vitals")} aria-label={tr("Signos vitales", "Vital signs")}>
          <GoTo
            link={toBody}
            what={tr("signos vitales", "vital signs")}
            detail={VITALS.map((key) => catalog.get(key)?.display_es ?? key).join(" · ")}
          />
          <h3 className="ref-h3">
            {tr("Signos vitales ", "Vital signs ")}<span className="secondary">({status.subject})</span>
          </h3>
          {indicators.state === "failed" && <Unavailable outcome={indicators.outcome} />}
          <ul>
            {VITALS.map((key) => {
              const indicator = catalog.get(key);
              const item = seriesOf(key);
              const readings = readingsFor(key);
              const last = readings[readings.length - 1];
              // Minutos desde la última lectura hasta la referencia del estado; la última de todas da 0.
              // Solo la cifra: el veredicto de «caducada» es una regla del backend (`lib/staleness.ts`)
              // y hoy no lo da por indicador.
              const age = last === undefined ? 0 : (reference - last.at) / 60_000;
              return (
                <li key={key} data-vital={key}>
                  <abbr title={indicator?.display_es ?? key}>
                    <IndicatorName indicatorKey={key} displayEs={VITAL_SHORT[key]} />
                  </abbr>
                  {item.state !== "ready" ? (
                    <Pending item={item} />
                  ) : last === undefined ? (
                    <MarkOf mark={MISSING_MARK}>{tr("sin lecturas", "no readings")}</MarkOf>
                  ) : (
                    <Mark pictogram={null} className="ref-vital-value">
                      <VitalValue value={last.value} indicator={indicator} catalog={indicators} />
                      {age >= 1 && (
                        <small className="secondary ref-vital-age" title={tr("Edad de la última lectura frente a la referencia del estado", "Age of the last reading against the status reference")}>
                          {tr(`hace ${formatAge(age)}`, `${formatAge(age)} ago`)}
                        </small>
                      )}
                    </Mark>
                  )}
                  <Sparkline readings={readings} until={reference} />
                </li>
              );
            })}
          </ul>
        </article>

        <article className={linked(toBody, "ref-card ref-trend")} aria-label={tr("Tendencia de 24 horas", "24-hour trend")}>
          <GoTo link={toBody} what={tr("tendencia de 24 horas", "24-hour trend")} />
          <h3 className="ref-h3">
            {tr("Tendencia (24 h) ", "Trend (24 h) ")}<span className="secondary">{VITAL_SHORT["heart-rate"]}</span>
          </h3>
          <Pending item={seriesOf("heart-rate")} />
          {/* La curva solo con la serie recibida: mientras carga o si falló lo dice `Pending`, y la
              marca de «sin lecturas» (cian) no se enseña por una serie que aún no llegó (revisión
              de la unidad 10). */}
          {/* Y con su ficha del catálogo: sin ella el eje se redondeaba a enteros (lógica 6). */}
          {seriesOf("heart-rate").state === "ready" &&
            (catalog.get("heart-rate") === undefined ? (
              <VitalValueMissing catalog={indicators} />
            ) : (
              <TrendSvg readings={readingsFor("heart-rate")} until={reference} indicator={catalog.get("heart-rate")} />
            ))}
        </article>

        {/* El cuerpo de la maqueta (adorno, aparte y perezoso); encima, la silueta real con los
            órganos en el color del nivel real de su dominio, solo los que tienen alerta. */}
        <article className="ref-card ref-body-figure" aria-label={tr("Cuerpo", "Body")}>
          <Suspense fallback={<Loading />}>
            <ReferenceBody />
          </Suspense>
          <BodySilhouette view={anatomy} selected={region} onSelect={setRegion} />
        </article>
      </div>
    </section>
  );
}

/** La ficha del tripulante: retrato (adorno), nivel, fase y tiempo de misión. */
export function HomeCrew({ home }: Piece) {
  const { status, overall, elapsed } = home;
  return (
    <section data-ui="home-crew" className="ref-card ref-crew-card" aria-label={tr("Tripulante", "Crew member")}>
      <PanelTitle concept="identity" className="ref-h">
        {tr("Tripulante: ", "Crew member: ")}{status.subject}
      </PanelTitle>
      <div className="ref-crew-row">
        <span className="ref-avatar" aria-hidden="true">
          <AstronautArt />
        </span>
        <div className="ref-crew-info">
          <strong className="ref-crew-id">{status.subject}</strong>
          <dl className="ref-kv">
            <dt>{tr("Estado", "Status")}</dt>
            <dd>
              <span className="ref-pill" style={levelTint(overall)}>
                <LevelBadge level={overall} />
              </span>
            </dd>
            <dt>{tr("Fase", "Phase")}</dt>
            <dd>{status.mission.phase_display}</dd>
            <dt>{tr("Tiempo", "Time")}</dt>
            <dd className="num">{formatMet(elapsed)}</dd>
          </dl>
        </div>
      </div>
    </section>
  );
}

/** Los peligros RIDGE del tripulante, por letra, con el nivel de cada dominio. */
export function HomeHazardLetters({ home, links }: Piece) {
  const { status, ridge, groups } = home;
  const toHazards = sectionLink(links, "hazards");
  return (
    <section data-ui="home-ridge-individual" className="ref-card ref-letters" aria-label={tr("Peligros RIDGE del tripulante", "Crew member's RIDGE hazards")}>
      <PanelTitle concept="hazards" className="ref-h">
        {tr("Peligros RIDGE (individual)", "RIDGE hazards (individual)")}
      </PanelTitle>
      <Pending item={ridge} />
      <ul className="ref-letter-row">
        {groups.map((group) => (
          <li
            key={group.hazard}
            className={linked(toHazards)}
            data-acc={group.hazard}
            title={toHazards === null ? capitalized(group.display) : undefined}
          >
            <GoTo
              link={toHazards}
              what={capitalized(group.display)}
              detail={domainLevels(group.domains, status)}
              pointerOnly
            />
            <span className="ref-tile-letter">{letterOf(group.hazard)}</span>
            <Segments domains={group.domains} status={status} />
            <span className="num">{formatNumber(group.domains.length)}</span>
            <span className="sr-only">{capitalized(group.display)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Las últimas notas del diario del tripulante. */
export function HomeLogbook({ home, links }: Piece) {
  const { status, diary } = home;
  // «Diario y pruebas» no es esencial: en modo esencial el «+» no se enseña (antes devolvía a «Inicio»).
  const toLog = sectionLink(links, "log");
  return (
    <section data-ui="home-logbook" className="ref-card ref-notes" aria-label={tr("Bitácora", "Logbook")}>
      <PanelTitle concept="diary" className="ref-h">
        {tr("Notas / bitácora (", "Notes / logbook (")}{status.subject})
        {toLog !== null && (
          <Command concept="add" className="ref-plus" type="button" onClick={toLog.open}>
            <span className="sr-only">{tr("Escribir en el diario", "Write in the diary")}</span>
          </Command>
        )}
      </PanelTitle>
      {diary.state !== "ready" ? (
        <Pending item={diary} />
      ) : diary.value.length === 0 ? (
        <p className="secondary">{tr("Sin entradas en el diario.", "No diary entries.")}</p>
      ) : (
        <ul>
          {diary.value.map((entry) => (
            <li key={`${entry.key}-${entry.effective}`}>
              <span className="secondary num">{metOf(status, entry.effective)}</span>
              <span className="ref-clamp-2">
                {entry.display_es}: <strong>{entry.value_text}</strong>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** El nivel de ahora, grande; los demás, debajo, con su caja de icono. */
export function HomeRisk({ home, links, notices = false }: Piece & { notices?: boolean }) {
  const { overall, overallStyle, status, lowest } = home;
  const toHazards = sectionLink(links, "hazards");
  // Con `notices` («Distancia y nodos», como la maqueta de la ISS): los dominios por encima del nivel
  // más bajo, con su primera causa en palabras del backend, en vez de la leyenda. Sin ninguno, la
  // leyenda de siempre.
  const rank = (level: string) => (isLevel(level) ? LEVEL_ORDER.indexOf(level) : -1);
  const raised = notices
    ? Object.entries(status.domains)
        .filter(([, risk]) => risk.level !== lowest)
        .sort(([, a], [, b]) => rank(b.level) - rank(a.level))
        .slice(0, 3)
    : [];
  return (
    <section data-ui="home-risk" className={linked(toHazards, "ref-card ref-levels")} aria-label={tr("Estado de riesgo", "Risk status")}>
      <GoTo link={toHazards} what={tr("estado de riesgo", "risk status")} />
      <PanelTitle concept="alerts" className="ref-h">
        {tr("Estado de riesgo", "Risk status")}
      </PanelTitle>
      <div className="ref-level-now" style={levelTint(overall)}>
        <span className="ref-hero-icon" aria-hidden="true">
          <Pictogram name={overallStyle?.pictogram ?? UNKNOWN_PICTOGRAM} />
        </span>
        <span>
          <strong>{overallStyle?.label ?? overall}</strong>
          <small>{tr("Nivel global actual", "Current overall level")}</small>
        </span>
      </div>
      {raised.length > 0 ? (
        <ul className="ref-risk-notices" aria-label={tr("Avisos", "Notices")}>
          {raised.map(([domain, risk]) => (
            <li key={domain} style={levelTint(risk.level)} title={risk.drivers.join(" · ")}>
              <span className="ref-level-box" aria-hidden="true">
                <Pictogram name={levelStyle(risk.level).pictogram} />
              </span>
              <span className="ref-risk-notice">
                <DomainName domain={domain} /> <LevelBadge level={risk.level} />
                {risk.drivers[0] !== undefined && <small className="secondary ref-ellipsis">{risk.drivers[0]}</small>}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <ul>
          {LEVEL_ORDER.filter((level) => level !== overall).map((level) => (
            <li key={level} style={levelTint(level)}>
              <span className="ref-level-box" aria-hidden="true">
                <Pictogram name={levelStyle(level).pictogram} />
              </span>
              <LevelBadge level={level} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Seguimientos abiertos y las primeras recomendaciones, tres en total. */
export function HomeNextActions({ home, links }: Piece) {
  return (
    <section data-ui="home-next-actions" className="ref-card ref-next" aria-label={tr("Próximas acciones", "Next actions")}>
      <PanelTitle concept="nextDays" className="ref-h">
        {tr("Próximas acciones", "Next actions")}
      </PanelTitle>
      <NextActions status={home.status} links={links} />
    </section>
  );
}

/** Acceso rápido por peligro: cada dominio con su nivel, sin agregar; y los accesos a otras secciones. */
export function HomeQuickHazards({ home, links }: Piece) {
  const { status, ridge, groups } = home;
  const toHazards = sectionLink(links, "hazards");
  // «Cuerpo» y «Calidad y sensores» no son esenciales: en modo esencial sus accesos no se enseñan.
  const toBody = sectionLink(links, "body");
  const toData = sectionLink(links, "data");
  return (
    <section data-ui="home-ridge-quick" className="ref-frame ref-quick" aria-label={tr("Peligros RIDGE: acceso rápido", "RIDGE hazards: quick access")}>
      <PanelTitle concept="radiation" className="ref-h ref-frame-h">
        {tr("Peligros RIDGE: acceso rápido", "RIDGE hazards: quick access")}
      </PanelTitle>
      <Pending item={ridge} />
      <div className="ref-quick-row">
        {groups.map((group) => {
          const levels = domainLevels(group.domains, status);
          // `tile-acc` (R5-2): el mosaico de color común de la concha (`shell/board.css`), con el acento de
          // su letra RIDGE; adorno §2.5, el texto en `--c-text` a ≥ 6:1. Los segmentos de nivel van
          // encima con su color real, como antes.
          return (
            <article
              key={group.hazard}
              className={linked(toHazards, `ref-hazard tile-acc acc-${group.hazard}`)}
              data-acc={group.hazard}
              aria-label={capitalized(group.display)}
            >
              <GoTo link={toHazards} what={capitalized(group.display)} detail={levels} />
              <Pictogram name={prefixedPictogram("ridge", group.hazard)} />
              <span className="ref-hazard-text">
                <span className="ref-letter" aria-hidden="true">
                  {letterOf(group.hazard)}
                </span>
                <span className="ref-hazard-name">{capitalized(group.display)}</span>
                <span className="ref-hazard-domains" title={levels}>
                  <Segments domains={group.domains} status={status} />
                  {/* Caducado, en cian como en la franja y el resumen (lógica 6): antes iba limpio. */}
                  {group.hazard === "distance" && status.comms !== null && (
                    <RouteFigure
                      figures={{ kind: "shown", stale: freshnessOf(status.freshness?.comms) !== "fresh" }}
                    >
                      {formatMinutes(status.comms.one_way_minutes)}
                    </RouteFigure>
                  )}
                </span>
              </span>
              <ul className="sr-only">
                {group.domains.map((domain) => {
                  // Un dominio sin nivel se dice así: no se le pone el nivel más bajo (lo señaló la
                  // revisión de la unidad 8); es lo mismo que dice el `title` de arriba.
                  const level = status.domains[domain]?.level;
                  return (
                    <li key={domain}>
                      <DomainName domain={domain} label={domainLabel(domain)} />{" "}
                      {level !== undefined ? <LevelBadge level={level} /> : tr("sin nivel", "no level")}
                    </li>
                  );
                })}
              </ul>
            </article>
          );
        })}
        {(toBody !== null || toData !== null) && (
          <div className="ref-quick-links">
            {toBody !== null && (
              <Command concept="compare" type="button" onClick={toBody.open}>
                <span>{tr("Ver indicadores en detalle", "View indicators in detail")}</span>
                <Chevron />
              </Command>
            )}
            {toData !== null && (
              <Command concept="dataQuality" type="button" onClick={toData.open}>
                <span>{tr("Datos brutos / fuente", "Raw data / source")}</span>
                <Chevron />
              </Command>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

/**
 * Una cifra de las efemérides en «Rutas espaciales» (`routeFigures`): sin ella, la marca y su
 * palabra; caducada, en cian con el anillo punteado, como en la franja; al día, limpia.
 */
export function RouteFigure({ figures, children }: { figures: RouteFigures; children?: ReactNode }) {
  if (figures.kind === "absent") return <MarkOf mark={figures.mark}>{figures.word}</MarkOf>;
  if (figures.stale) {
    return (
      <MarkOf mark={MISSING_MARK} className="num">
        {children}
      </MarkOf>
    );
  }
  return <span className="num">{children}</span>;
}

/** Rutas espaciales: el perfil enseñado, sus cifras de las efemérides, las proyecciones y los aspectos. */
export function HomeRoutes({ home }: Piece) {
  const { status, matrix, matrixFailure, shownRoute, setRoute } = home;
  const profile = matrix?.profiles.find((item) => item.id === shownRoute) ?? null;
  const comms = status.comms;
  const declared = profile !== null && profile.declared;
  // Se dibujan cinco como mucho, y la barra más larga es la de la mayor de esas cinco (no la de
  // una que no se enseña: lo señaló la revisión de la unidad 8).
  const predictions = status.predictions.slice(0, 5);
  const widest = Math.max(1e-9, ...predictions.map((item) => Math.abs(item.projected_change)));
  // Perfil no declarado, sin efemérides, perfil y efemérides que no casan, o caducadas (lógica 6).
  const figures = routeFigures(
    declared,
    comms !== null,
    freshnessOf(status.freshness?.comms),
    status.mission.profile?.ephemeris?.state,
  );
  return (
    <section data-ui="home-routes" className="ref-frame ref-route" aria-label={tr("Rutas espaciales: impacto en la salud", "Space routes: health impact")}>
      <PanelTitle concept="compare" className="ref-h ref-frame-h">
        {tr("Rutas espaciales: impacto en la salud", "Space routes: health impact")}
      </PanelTitle>
      <div className="ref-route-grid">
        <div className="ref-card ref-route-list">
          <h3 className="ref-h3">{tr("Ruta", "Route")}</h3>
          {matrix === null ? (
            matrixFailure === null ? <Loading /> : <Unavailable outcome={matrixFailure} />
          ) : (
            <ul role="group" aria-label={tr("Perfil mostrado", "Profile shown")}>
              {matrix.profiles.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    aria-pressed={item.id === shownRoute}
                    title={capitalized(item.display)}
                    onClick={() => setRoute(item.id)}
                  >
                    <Pictogram name={profilePictogram(item.id) ?? UNKNOWN_PICTOGRAM} />
                    <span className="ref-ellipsis">{PROFILE_SHORT[item.id] ?? capitalized(item.display)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="ref-card ref-route-mid">
          <dl className="ref-stats">
            <div data-acc="isolation">
              <FieldLabel as="dt" concept="missionDay">
                {tr("Día", "Day")}
              </FieldLabel>
              <dd className="num">
                {formatNumber(status.mission.mission_day)} / {formatNumber(status.mission.duration_days)}
              </dd>
            </div>
            <div data-acc="distance">
              <FieldLabel as="dt" pictogram={prefixedPictogram("ridge", "distance")}>
                {tr("Distancia", "Distance")}
              </FieldLabel>
              <dd>
                <RouteFigure figures={figures}>
                  {comms === null ? null : <>{formatNumber(comms.distance_au * KM_PER_AU)} km</>}
                </RouteFigure>
              </dd>
            </div>
            <div data-acc="environment">
              <FieldLabel as="dt" concept="lightTime">
                {tr("Retardo", "Delay")}
              </FieldLabel>
              <dd>
                <RouteFigure figures={figures}>{comms === null ? null : formatMinutes(comms.one_way_minutes)}</RouteFigure>
              </dd>
            </div>
            <div data-acc="radiation">
              <FieldLabel as="dt" concept="radiation">
                {tr("Dosis", "Dose")}
              </FieldLabel>
              <dd>
                {status.dose.cumulative_msv === null ? (
                  <MarkOf mark={MISSING_MARK}>{tr("no facilitada", "not provided")}</MarkOf>
                ) : (
                  <span className="num">{formatNumber(status.dose.cumulative_msv, 1)} mSv</span>
                )}
              </dd>
            </div>
            <div data-acc="gravity">
              <FieldLabel as="dt" pictogram={prefixedPictogram("ridge", "gravity")}>
                {tr("Gravedad", "Gravity")}
              </FieldLabel>
              <dd className="ref-ellipsis" title={status.mission.gravity_display}>
                {status.mission.gravity_display}
              </dd>
            </div>
          </dl>
          <RouteArt target={profile === null ? "" : capitalized(profile.display)} targetId={profile?.id ?? ""} />
        </div>

        <div className="ref-card">
          <h3 className="ref-h3">
            {tr("Proyecciones del estado ", "Status projections ")}<ObservationTypeBadge type="predicted" />
          </h3>
          {predictions.length === 0 ? (
            <p className="secondary">{tr("Sin proyecciones para este tripulante.", "No projections for this crew member.")}</p>
          ) : (
            <ul className="ref-impact">
              {predictions.map((item, index) => (
                <li key={item.key}>
                  <span className="ref-ellipsis" title={item.display_es}>
                    <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
                  </span>
                  <span className="ref-impact-bar" aria-hidden="true">
                    <span
                      data-bar={item.concerning ? "concern" : String(index)}
                      style={{ width: `${(Math.abs(item.projected_change) / widest) * 100}%` }}
                    />
                  </span>
                  <span className="num" title={item.basis}>
                    {item.projected_change > 0 ? "+" : ""}
                    {formatNumber(item.projected_change, item.decimals)} {displayUnit(item.unit)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="ref-card">
          <h3 className="ref-h3">{tr("Análisis de la ruta", "Route analysis")}</h3>
          {/* Con la matriz ya recibida y ningún perfil enseñado (nadie declaró uno ni eligió una
              ruta), se dice; antes se quedaba en «Cargando…» para siempre (revisión de la unidad 8). */}
          {matrix === null ? (
            matrixFailure === null ? <Loading /> : <Unavailable outcome={matrixFailure} />
          ) : profile === null ? (
            <p className="secondary">{tr("Sin perfil de misión declarado ni ruta elegida.", "No mission profile declared and no route chosen.")}</p>
          ) : (
            <ul className="ref-aspects">
              <li className="ref-global-risk">
                <Pictogram name={uiPictogram("resolved")} />
                <strong>{tr("Riesgo global:", "Overall risk:")}</strong>
                <span className="ref-pill" style={levelTint(status.overall_level)}>
                  <LevelBadge level={status.overall_level} />
                </span>
              </li>
              {profile.cells.slice(0, 2).map((cell) => (
                <li key={cell.key} title={cell.text}>
                  <Pictogram name={uiPictogram("resolved")} />
                  <span className="ref-clamp-2">
                    <strong>{cell.label}:</strong> <span className="secondary">{cell.text}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

/**
 * La raya que separa lo principal de «Inicio» —de «Peligros RIDGE: acceso rápido» para arriba— de lo
 * secundario —rutas espaciales y el pie— (decisión del usuario, 2026-11-14), con el mando que lo
 * pliega. Es un mando de la consola (`Command`, con su dibujo de capas) en la caja de los accesos de
 * la maqueta; la punta mira hacia donde irá lo secundario. Plegar no cambia ningún dato: solo qué se
 * pinta debajo. Lo que se pliega lo dice el propio rótulo, para no esconder nada sin nombrarlo.
 *
 * Plegado, lo principal llena la ventana (2026-11-14: «que reescale el resto para que ocupe la
 * pantalla»): aquí solo se mide cuánto alto queda desde el tablero hasta el borde inferior y se deja
 * en `--home-fill`; qué fila crece y cómo lo decide `referenceDashboard.css`. Se vuelve a medir al
 * cambiar la ventana o el tablero (al volver a «Inicio» desde otra pestaña, por ejemplo).
 */
/** Si entre las alertas de ahora hay alguna que no estaba en la vez anterior: pliega lo secundario. */
export function hasNewAlert(previous: ReadonlySet<string>, current: readonly string[]): boolean {
  return current.some((id) => !previous.has(id));
}

/**
 * El mismo separador sirve para los bloques plegables de debajo (2026-11-14, lote «reservas»):
 * «Distancia y nodos», «Diagnóstico integrado», «Reservas». Solo el primero mide `--home-fill`
 * (`fill`), porque es el que decide cuánto llena lo principal.
 */
export function HomeDivider({
  open,
  onToggle,
  name = tr("lo secundario", "the secondary content"),
  what = tr("Rutas espaciales, divulgación y extensión", "Space routes, outreach and extension"),
  fill = true,
  pictogram = "layers-stack",
}: {
  open: boolean;
  onToggle: () => void;
  name?: string;
  what?: string;
  fill?: boolean;
  pictogram?: Parameters<typeof Command>[0]["pictogram"];
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Solo una raya mide: las demás no tocan la propiedad (si la borraran, desharían lo de la primera).
    // Cuando la que mide deja de medir, la limpieza de su efecto anterior la quita.
    if (!fill) return;
    const board = ref.current?.closest<HTMLElement>(".section-body");
    if (!board) return;
    if (open) {
      board.style.removeProperty("--home-fill");
      return;
    }
    const measure = () => {
      // Escondido (otra pestaña abierta) no hay nada que medir: su `top` sería 0.
      if (board.offsetParent === null) return;
      const top = board.getBoundingClientRect().top + window.scrollY;
      board.style.setProperty("--home-fill", `${Math.max(0, Math.floor(window.innerHeight - top - FILL_BOTTOM_PX))}px`);
    };
    measure();
    window.addEventListener("resize", measure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(board);
    return () => {
      window.removeEventListener("resize", measure);
      observer?.disconnect();
      board.style.removeProperty("--home-fill");
    };
  }, [open, fill]);
  return (
    <div ref={ref} className="ref-divider" data-open={open ? "true" : "false"}>
      <span className="ref-divider-line" aria-hidden="true" />
      <Command
        pictogram={pictogram}
        type="button"
        className="ref-divider-go"
        aria-expanded={open}
        onClick={onToggle}
      >
        <span className="ref-divider-word">{open ? tr(`Ocultar ${name}`, `Hide ${name}`) : tr(`Mostrar ${name}`, `Show ${name}`)}</span>
        <span className="secondary ref-divider-what">{what}</span>
        <Chevron />
      </Command>
      <span className="ref-divider-line" aria-hidden="true" />
    </div>
  );
}

/** El pie de la maqueta: divulgación, extensión terrestre y el acceso al modo esencial. */
export function HomeFooter({ home, links, essential = true }: Piece & { essential?: boolean }) {
  return (
    <>
      <section data-ui="home-social" className="ref-card ref-foot" aria-label={tr("Conexión social y divulgación", "Social connection and outreach")}>
        <div className="ref-foot-text">
          <PanelTitle concept="groundNotes" className="ref-h">
            {tr("Conexión social y divulgación", "Social connection and outreach")}
          </PanelTitle>
          <p>{tr("Actividades, retos de salud, formación y divulgación con la comunidad.", "Activities, health challenges, training and outreach with the community.")}</p>
        </div>
        <StationArt />
      </section>
      <section data-ui="home-outreach" className="ref-card ref-foot" aria-label={tr("Extensión: Tierra y comunidades", "Extension: Earth and communities")}>
        <div className="ref-foot-text">
          <PanelTitle concept="habitat" className="ref-h">
            {tr("Extensión: Tierra y comunidades", "Extension: Earth and communities")}
          </PanelTitle>
          <p>{tr("Aplicación en poblaciones aisladas, misiones humanitarias y respuesta a catástrofes.", "Use in isolated populations, humanitarian missions and disaster response.")}</p>
        </div>
        <ShelterArt />
      </section>
      {essential && <HomeEssential home={home} links={links} />}
    </>
  );
}

/**
 * La tarjeta roja de «Inicio»: pedir ayuda urgente (decisión del usuario, 2026-11-14: el botón del
 * modo esencial «debería ser de emergencia, por si necesitas ayuda urgente», y «Tierra está muy
 * lejos: tiene que alertar a quien tengas más cerca y, obviamente, a Tierra»).
 *
 * **Un solo toque**, sin formulario ni confirmación: «solo haces que sea más probable que se muera si
 * le restas tiempo de acción por parte de los demás» (el usuario, el mismo día). Pulsar la firma en
 * el registro (`POST /api/help-requests`) con el tripulante de la consola, el nombre recordado en el
 * equipo si lo hay y el instante de los datos, y avisa a la banda (`HelpBanner`) para que la enseñe y
 * la lea al momento. No toca la pantalla: el modo esencial escondería secciones que pueden hacer
 * falta justo entonces; sigue en «Pantalla». Si falla, lo dice y se puede volver a pulsar.
 *
 * No es secundaria: con lo secundario a la vista va en el pie, como en la maqueta; plegado, se queda
 * abajo del todo y estirada a lo ancho (`wide`).
 */
export function HomeEssential({
  home,
  wide = false,
  side = false,
  children,
}: Piece & { wide?: boolean; side?: boolean; children?: ReactNode }) {
  const [operator] = useOperator();
  const [step, setStep] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    setStep("sending");
    setError(null);
    try {
      const body = {
        subject: home.status.subject,
        signed_by: operator.trim(),
        reason: "",
        at: home.status.data.reference_time,
      };
      const signed = await helpRequestsApi.ask(body);
      setStep("sent");
      const detail: HelpRequestedDetail = { ...body, ledger_index: signed.ledger_index, signed_at: signed.signed_at };
      window.dispatchEvent(new CustomEvent(HELP_REQUESTED_EVENT, { detail }));
    } catch (failure) {
      setError(requestOutcome(failure).text);
      setStep("idle");
    }
  };

  return (
    <section
      data-ui="home-essential"
      className={`ref-card ref-foot ref-emergency${wide ? " ref-emergency-wide" : ""}${side ? " ref-emergency-side" : ""}`}
      aria-label={tr("Ayuda urgente", "Urgent help")}
    >
      <span className="ref-alarm" aria-hidden="true">
        <Pictogram name={uiPictogram("alerts")} />
      </span>
      <span className="ref-foot-text">
        <strong className="ref-h">{tr("Ayuda urgente", "Urgent help")}</strong>
        <span role={error !== null || step === "sent" ? "status" : undefined}>
          {error !== null
            ? tr(
                `No se pudo pedir: ${error}. Vuelva a pulsar o use el procedimiento de la nave.`,
                `Could not request it: ${error}. Press again or use the ship's procedure.`,
              )
            : step === "sent"
              ? tr(
                  "Ayuda pedida: la tripulación ya la ve, empezando por quien está más cerca; Tierra, con el retardo de la luz.",
                  "Help requested: the crew already sees it, starting with whoever is closest; Earth, after the light-time delay.",
                )
              : tr(
                  "Un toque avisa al momento a la tripulación, primero a quien está más cerca, y a Tierra, que lo recibe un tiempo de luz después.",
                  "One touch alerts the crew at once, whoever is closest first, and Earth, which receives it one light time later.",
                )}
        </span>
      </span>
      {/* Lo que haya a mano para responder (en «Distancia y nodos», los recursos contados). */}
      {children}
      <Command
        concept="alerts"
        type="button"
        className="ref-essential-go"
        disabled={step === "sending"}
        onClick={() => void send()}
      >
        {step === "sent" ? tr("Pedir otra vez", "Request again") : tr("Pedir ayuda", "Request help")}
      </Command>
    </section>
  );
}

/** Columna del tripulante: ficha, peligros por letra y bitácora. Personal: la privacidad la tapa entera. */
export function HomeCrewColumn({ home, links }: Piece) {
  return (
    <div className="ref-col ref-crew-col">
      <HomeCrew home={home} />
      <HomeHazardLetters home={home} links={links} />
      <HomeLogbook home={home} links={links} />
    </div>
  );
}

/** Columna de riesgo: el nivel de ahora grande, los demás debajo, y las próximas acciones. */
export function HomeRiskColumn({ home, links, notices = false }: Piece & { notices?: boolean }) {
  return (
    <div className="ref-col ref-risk-col">
      <HomeRisk home={home} links={links} notices={notices} />
      <HomeNextActions home={home} links={links} />
    </div>
  );
}

/**
 * Un instante de la misión (la fecha de una entrada del diario, el fin de un seguimiento) en tiempo
 * de misión. Llegan como instante ISO completo, y `formatDay` solo admite un día entero: pasárselo
 * lanzaba y, sin barrera de errores, dejaba en blanco la consola entera.
 *
 * Por lo mismo no lanza nunca: el origen de la misión llega como día (`2026-11-01`) y, si llega como
 * instante, se cuenta desde su día UTC; sin origen o sin instante legibles no hay tiempo de misión
 * que dar, y va la raya de «sin dato» en vez de una excepción.
 */
function metOf(status: CrewStatus, iso: string): string {
  const start = typeof status.mission.start === "string" ? status.mission.start.slice(0, 10) : "";
  const at = new Date(iso);
  if (Number.isNaN(Date.parse(`${start}T00:00:00Z`)) || Number.isNaN(at.getTime())) return "—";
  return formatMet(missionElapsedSeconds(start, at));
}

/** Un segmento por dominio, en el color de su nivel (aquí, el nominal en verde): no se agrega. */
function Segments({ domains, status }: { domains: readonly string[]; status: CrewStatus }) {
  return <ToneSegments tones={domains.map((domain) => shownTone(status.domains[domain]?.level))} titles={domains.map(domainLabel)} />;
}

/**
 * Cada acción lleva adonde se trabaja: un seguimiento abierto, a «Rutinas y notas» (allí se cierra,
 * `FollowupsPanel`); una recomendación, a «Peligros y alertas» («Qué hacer», donde se adopta).
 */
function NextActions({ status, links }: { status: CrewStatus; links?: HomeLinks | undefined }) {
  const open = status.followups.filter((item) => item.state !== "closed");
  const toRoutines = sectionLink(links, "routines");
  const toHazards = sectionLink(links, "hazards");
  const items: ReactNode[] = [
    ...open.map((item) => (
      <li
        key={`f-${item.adoption_index}`}
        className={linked(toRoutines)}
        title={toRoutines === null ? tr(`Hasta ${metOf(status, item.window_ends)}`, `Until ${metOf(status, item.window_ends)}`) : undefined}
      >
        <GoTo link={toRoutines} what={item.countermeasure.action} detail={tr(`Hasta ${metOf(status, item.window_ends)}`, `Until ${metOf(status, item.window_ends)}`)} />
        <span className="ref-box" aria-hidden="true" />
        <Mark pictogram={null} color={item.state === "due" ? "yellow" : null}>
          <span className="ref-clamp-2">{item.countermeasure.action}</span>
        </Mark>
      </li>
    )),
    ...status.recommendations.slice(0, 3).map((item, index) => (
      <li key={`r-${index}`} className={linked(toHazards)} title={toHazards === null ? domainLabel(item.domain) : undefined}>
        <GoTo link={toHazards} what={item.action} detail={domainLabel(item.domain)} />
        <span className="ref-box" aria-hidden="true" />
        <Mark pictogram={null} color="magenta">
          <span className="ref-clamp-2">{item.action}</span>
        </Mark>
      </li>
    )),
  ].slice(0, 3);
  if (items.length === 0) return <p className="secondary">{tr("Sin seguimientos ni recomendaciones abiertas.", "No open follow-ups or recommendations.")}</p>;
  return <ul>{items}</ul>;
}
