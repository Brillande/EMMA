import { type CSSProperties, Suspense, lazy, useEffect, useId, useReducer, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Command } from "../components/Command";
import { DomainName } from "../components/DomainName";
import { IndicatorName } from "../components/IndicatorName";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { Pictogram, type PictogramName } from "../icons";
import {
  type CognitionSessions,
  type FhirObservation,
  type ImagingStudy,
  type Indicator,
  type PainReport,
  type ProtocolCatalog,
  type PvtSessions,
  type ScannedReport,
  type VolumeSegmentation,
  type VolumeStudy,
  api,
  cognitionApi,
  pvtApi,
} from "../lib/api";
import { displayUnit, formatAge, formatNumber, formatUtc } from "../lib/format";
import { tr } from "../lib/i18n";
import { cssVar } from "../lib/palette";
import { EMPTY_MARK, MISSING_MARK, UNAVAILABLE_MARK, requestOutcome } from "../lib/marks";
import { type Fetched, type HomeData, type HomeLinks, sectionLink } from "./HomeBoard";
import { type Reading, Sparkline, levelToken } from "./HomeCharts";
import { capitalized } from "./HazardCards";
import { POLARIS_PRESETS, PolarisViewer } from "../volumes/PolarisViewer";
import { SegmentationPreview } from "../volumes/SegmentationPreview";
import "./referenceDashboard.css";
import "./homeDiagnostics.css";

/**
 * «Diagnóstico integrado: pruebas y visualización», el bloque de la maqueta de la ISS (lote
 * «reservas», 2026-11-14) con el estilo de «Inicio». Por qué existe: las pruebas (ecografía,
 * analíticas, volúmenes de Polaris) ya estaban en EMMA, pero repartidas por «Imagen e informes»,
 * «Cuerpo» y «Diario y pruebas»; desde «Inicio» no se veía qué hay ni se llegaba a ellas. Aquí se
 * juntan, cada una con lo que el backend tiene de verdad, y llevan a su sección.
 *
 * Lo que NO se copió de la maqueta, a propósito:
 * - Un hígado dibujado sin dato detrás. El render 3D es el de la última segmentación registrada
 *   (`volumes/SegmentationPreview.tsx`: sus mallas firmadas, con los colores del visor de Polaris);
 *   sin segmentación, no hay dibujo. El visor completo (`volumes/PolarisViewer.tsx`, la copia
 *   literal de Polaris; `VolumeViewer.tsx` para los presets que Polaris no pinta, cargado solo al
 *   abrirlo) va en una ventana encima de la pestaña, porque «Imagen e informes» está apartada en
 *   esta versión (decisión del usuario, 2026-11-15: «que si pulso el botón pasen cosas», sin
 *   devolver las pestañas apartadas). Los rótulos (preset,
 *   estructuras, su estado «sin validar») son los del backend. Hoy no vuela ningún TAC
 *   (minas de `CLAUDE.md`): el volumen es imagen de referencia previa al vuelo o de Tierra, no un
 *   diagnóstico a bordo, y se dice.
 * - «Análisis y correlaciones (IA)», «Sin anomalías relevantes» y la correlación dieta-hígado. El
 *   análisis es el del backend: el nivel global, su resumen y los dominios fuera del nivel más bajo
 *   con sus causas, en sus palabras. Nada de `app/interpret/` (invariante 6), y no se calcula
 *   ninguna correlación aquí.
 * - ALT 28, AST 24, bilirrubina 0,8, colesterol 168. Las tendencias son las series reales de los
 *   indicadores de laboratorio del catálogo (`measurement_cost.mode === "laboratory"`) con lecturas
 *   en los 30 días antes de la referencia del estado; sin ninguna, la marca de «sin lecturas».
 *
 * Las pruebas (ecografía, biomarcadores, analíticas, otras) llevaban a pestañas que esta versión
 * aparta y se quedaron sin mando. Ahora cada una se despliega dentro de la tarjeta con lo que el
 * backend tiene registrado (estudios, lecturas, informes, sesiones de PVT y cognición, dolor); lo
 * que no tiene registro lo dice en gris, sin inventar nada.
 *
 * Se adapta a la ubicación: la frase de capacidad médica del perfil enseñado (`medical_capability`
 * de `GET /api/mission/profiles`, leída en su fuente) va bajo el título, con el perfil en él.
 *
 * COLORES DE ADORNO: el acento de la sección y la curva de las tendencias son los de «Inicio»
 * (§2.5 de `compliance/hmi-state-of-the-art.md`) y no significan nada; el nivel conserva su color.
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
 * La salvedad del volumen (minas de `CLAUDE.md`): imagen de referencia previa al vuelo o de Tierra,
 * no un diagnóstico a bordo; ni «vuela un TAC» ni «nunca volará». El inglés dice lo mismo.
 */
const REFERENCE_NOTE = tr(
  "No es un diagnóstico a bordo. Imagen de referencia previa al vuelo o de Tierra: hoy no vuela ningún TAC.",
  "Not an on-board diagnosis. Reference imaging from before flight or from Earth: no CT scanner flies today.",
);
const DATASET_NOTE = tr(
  "TAC real de un dataset público, no de este tripulante.",
  "Real CT from a public dataset, not from this crew member.",
);

const DAY_MS = 24 * 3600 * 1000;
/** La ventana de «Tendencias clave», como en la maqueta. */
export const TREND_WINDOW_MS = 30 * DAY_MS;
/** Cuántas tendencias caben en la tarjeta. */
export const TREND_ROWS = 4;
/** Lecturas pedidas por indicador de laboratorio: sobran para 30 días de analíticas. */
const LAB_LIMIT = 60;
/**
 * Cada cuánto se vuelven a pedir las series de laboratorio con el tablero a la vista. Son decenas
 * de indicadores (una petición por cada uno); con cada relectura en vivo (5 s) serían decenas de
 * peticiones cada 5 s para datos que llegan unas pocas veces al mes. Al cambiar de tripulante o
 * volver a «Inicio» se piden en el acto.
 */
const LAB_REFRESH_MS = 10 * 60 * 1000;
/** El modo del catálogo de lo que se mide en laboratorio (`app/ingest/cost.py`). */
const LABORATORY = "laboratory";
/** La clase de informe escaneado que es una analítica (`ReportKind`). */
const LAB_REPORT = "analitica";

/** Lo que dice `GET /api/volumes/segmenter` (declarado aquí: `api.ts` no lo nombra). */
export interface SegmenterStatus {
  available: boolean;
  note: string | null;
}

/** Una serie de laboratorio recibida: su clave y sus lecturas en orden. */
export interface LabSeries {
  key: string;
  readings: Reading[];
}

/** Lo que el bloque pide aparte del estado, una vez para todas sus tarjetas. */
export interface DiagnosticsData {
  volumes: Fetched<VolumeStudy[]>;
  segmenter: Fetched<SegmenterStatus>;
  ultrasound: Fetched<ImagingStudy[]>;
  reports: Fetched<ScannedReport[]>;
  labs: Fetched<LabSeries[]>;
  /** El catálogo de protocolos de ecografía, para nombrar cada estudio; se pide al abrir la prueba. */
  protocols?: Fetched<ProtocolCatalog> | undefined;
  /** PVT, cognición y dolor; se piden al abrir «Otras pruebas». Ausente: aún no se pidieron. */
  others?: OtherTestsData | undefined;
}

/** Lo registrado de «Otras pruebas», cada una con su petición: una que falla no tapa a las demás. */
export interface OtherTestsData {
  pvt: Fetched<PvtSessions>;
  cognition: Fetched<CognitionSessions>;
  pain: Fetched<PainReport[]>;
}

/** Sesiones pedidas de PVT y cognición: el backend las da de la más reciente a la más antigua, y
 * solo se enseña la última. */
const SESSION_LIMIT = 1;

/** Qué pide el bloque además de lo de siempre: lo de una prueba desplegada. */
export interface DiagnosticsWants {
  protocols: boolean;
  others: boolean;
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

/** Las claves del catálogo que se miden en laboratorio, en su orden. */
export function laboratoryKeys(indicators: readonly Indicator[]): string[] {
  return indicators.filter((item) => item.measurement_cost?.mode === LABORATORY).map((item) => item.key);
}

/**
 * Las peticiones del bloque. Oculto (`active` falso), no se pide nada. Los volúmenes, la ecografía
 * y los informes se releen con cada lectura nueva del tripulante; las series de laboratorio, como
 * mucho cada `LAB_REFRESH_MS`.
 */
export function useDiagnosticsData(
  home: HomeData,
  active = true,
  wants: DiagnosticsWants = { protocols: false, others: false },
): DiagnosticsData {
  const { status, indicators } = home;
  const [protocols, setProtocols] = useState<Fetched<ProtocolCatalog> | undefined>(undefined);
  const [pvt, setPvt] = useState<Fetched<PvtSessions>>({ state: "loading" });
  const [cognition, setCognition] = useState<Fetched<CognitionSessions>>({ state: "loading" });
  const [pain, setPain] = useState<Fetched<PainReport[]>>({ state: "loading" });
  const [othersAsked, setOthersAsked] = useState(false);
  const [volumes, setVolumes] = useState<Fetched<VolumeStudy[]>>({ state: "loading" });
  const [segmenter, setSegmenter] = useState<Fetched<SegmenterStatus>>({ state: "loading" });
  const [ultrasound, setUltrasound] = useState<Fetched<ImagingStudy[]>>({ state: "loading" });
  const [reports, setReports] = useState<Fetched<ScannedReport[]>>({ state: "loading" });
  const [labs, setLabs] = useState<Fetched<LabSeries[]>>({ state: "loading" });
  const subject = status.subject;
  const reference = status.data.reference_time;
  const labKeys = indicators.state === "ready" ? laboratoryKeys(indicators.value).join(",") : null;
  const labBucket = Math.floor(Date.parse(reference) / LAB_REFRESH_MS);

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    const alive = () => current;
    fetched(api.volumes.segmenter(), alive, setSegmenter);
    return () => {
      current = false;
    };
  }, [active]);

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    const alive = () => current;
    fetched(api.volumes.list(subject), alive, setVolumes);
    fetched(api.imaging.studies(subject), alive, setUltrasound);
    fetched(api.reports.list(subject), alive, setReports);
    return () => {
      current = false;
    };
  }, [active, subject, status.data.observations]);

  useEffect(() => {
    if (!active) return undefined;
    // El catálogo falló: las tendencias dicen lo mismo que él, no «cargando» para siempre.
    if (indicators.state === "failed") {
      setLabs({ state: "failed", outcome: indicators.outcome });
      return undefined;
    }
    if (labKeys === null) return undefined;
    let current = true;
    const keys = labKeys === "" ? [] : labKeys.split(",");
    fetched(
      Promise.all(
        keys.map((key) =>
          api.observations(key, LAB_LIMIT, subject, reference).then((body) => ({ key, readings: readingsOf(body.observations) })),
        ),
      ),
      () => current,
      setLabs,
    );
    return () => {
      current = false;
    };
    // `reference` entra por su tramo (`labBucket`), no por cada relectura.
  }, [active, subject, labKeys, labBucket, indicators.state]);

  // El catálogo de protocolos no depende del tripulante: se pide al desplegar la ecografía, y
  // recibido una vez, no se vuelve a pedir (un fallo sí se reintenta al desplegarla otra vez).
  const protocolsReady = protocols?.state === "ready";
  useEffect(() => {
    if (!active || !wants.protocols || protocolsReady) return undefined;
    let current = true;
    fetched(api.imaging.protocols(), () => current, setProtocols);
    return () => {
      current = false;
    };
  }, [active, wants.protocols, protocolsReady]);

  // «Otras pruebas», solo desplegadas; con otro tripulante, lo anterior no se enseña mientras llega.
  // Se releen al desplegarlas y, abiertas, con el tramo de las series de laboratorio: son pruebas
  // de unas pocas al día, no lecturas de cada 5 s.
  const othersSubject = useRef<string | null>(null);
  useEffect(() => {
    if (!active || !wants.others) return undefined;
    if (othersSubject.current !== subject) {
      othersSubject.current = subject;
      setPvt({ state: "loading" });
      setCognition({ state: "loading" });
      setPain({ state: "loading" });
    }
    setOthersAsked(true);
    let current = true;
    const alive = () => current;
    fetched(pvtApi.sessions(subject, SESSION_LIMIT), alive, setPvt);
    fetched(cognitionApi.sessions(subject, SESSION_LIMIT), alive, setCognition);
    fetched(api.pain.reports(subject), alive, setPain);
    return () => {
      current = false;
    };
  }, [active, wants.others, subject, labBucket]);

  const others = othersAsked && othersSubject.current === subject ? { pvt, cognition, pain } : undefined;
  return { volumes, segmenter, ultrasound, reports, labs, protocols, others };
}

/** Las pruebas que se despliegan, en su orden de la tarjeta. */
export type TestKey = "ultrasound" | "biomarkers" | "lab-reports" | "other";

/** Lo que el bloque tiene abierto: una prueba desplegada (o ninguna) y la ventana del visor. */
export interface DiagnosticsUi {
  test: TestKey | null;
  viewer: boolean;
}

export const DIAGNOSTICS_CLOSED: DiagnosticsUi = { test: null, viewer: false };

export type DiagnosticsAction = { type: "toggle-test"; test: TestKey } | { type: "open-viewer" } | { type: "close-viewer" };

/** Pulsar una prueba la despliega y pliega la que estuviera abierta; pulsarla otra vez la pliega. */
export function diagnosticsReducer(state: DiagnosticsUi, action: DiagnosticsAction): DiagnosticsUi {
  switch (action.type) {
    case "toggle-test":
      return { ...state, test: state.test === action.test ? null : action.test };
    case "open-viewer":
      return { ...state, viewer: true };
    case "close-viewer":
      return { ...state, viewer: false };
  }
}

/** La tecla que cierra la ventana del visor: Escape, y ninguna otra. */
export function viewerKeyAction(key: string): DiagnosticsAction | null {
  return key === "Escape" || key === "Esc" ? { type: "close-viewer" } : null;
}

/** El último volumen del tripulante y su última segmentación (la más reciente de todas). */
export interface LatestVolume {
  study: VolumeStudy;
  segmentation: VolumeSegmentation | null;
}

/**
 * El volumen que resume la vista previa: la segmentación más reciente de cualquier estudio, con el
 * suyo; sin ninguna, el estudio más reciente sin segmentar; sin estudios, `null`.
 */
export function latestVolume(studies: readonly VolumeStudy[]): LatestVolume | null {
  let best: { at: number; study: VolumeStudy; segmentation: VolumeSegmentation } | null = null;
  for (const study of studies) {
    for (const segmentation of study.segmentations) {
      const at = Date.parse(segmentation.recorded);
      if (best === null || at > best.at) best = { at, study, segmentation };
    }
  }
  if (best !== null) return { study: best.study, segmentation: best.segmentation };
  let newest: VolumeStudy | null = null;
  for (const study of studies) {
    if (newest === null || Date.parse(study.recorded) > Date.parse(newest.recorded)) newest = study;
  }
  return newest === null ? null : { study: newest, segmentation: null };
}

/** Una fila de «Tendencias clave»: el indicador, sus lecturas de la ventana y la última. */
export interface LabTrend {
  indicator: Indicator;
  readings: Reading[];
  last: Reading;
}

/**
 * Las series de laboratorio con lecturas en los 30 días hasta `reference`, la medida más reciente
 * primero (a igualdad, el orden de llegada, que es el del catálogo), como mucho `TREND_ROWS`. Una
 * serie sin ficha en el catálogo no se enseña: sin ella no hay decimales ni unidad (lógica 6).
 */
export function labTrends(series: readonly LabSeries[], catalog: ReadonlyMap<string, Indicator>, reference: number): LabTrend[] {
  return labRows(series, catalog, reference).slice(0, TREND_ROWS);
}

/** Lo mismo que `labTrends`, sin el tope: la lista entera que despliega «Biomarcadores». */
export function labRows(series: readonly LabSeries[], catalog: ReadonlyMap<string, Indicator>, reference: number): LabTrend[] {
  const from = reference - TREND_WINDOW_MS;
  const rows: LabTrend[] = [];
  for (const item of series) {
    const indicator = catalog.get(item.key);
    if (indicator === undefined) continue;
    const readings = item.readings.filter((reading) => reading.at >= from && reading.at <= reference);
    const last = readings[readings.length - 1];
    if (last === undefined) continue;
    rows.push({ indicator, readings, last });
  }
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => b.row.last.at - a.row.last.at || a.index - b.index)
    .map(({ row }) => row);
}

/** El dibujo de la vista previa: el hígado para el preset que lo segmenta, la imagen para lo demás (el gantry es de «Imagen e informes»). */
export function previewPictogram(preset: string | undefined): PictogramName {
  return preset === "higado" ? "liver" : "picture";
}

/** Lo que una petición enseña mientras no está: cargando, o cómo falló. Lista, nada. */
function Pending({ item }: { item: Fetched<unknown> }) {
  if (item.state === "loading") return <Loading />;
  if (item.state === "failed") return <Unavailable outcome={item.outcome} />;
  return null;
}

/** Un recuento de lo recibido, o la marca de su estado (cargando, falló, vacío). */
function Count({ item, unit, empty }: { item: Fetched<number>; unit: [string, string]; empty: string }) {
  if (item.state === "loading") return <span className="secondary">{tr("Cargando…", "Loading…")}</span>;
  if (item.state === "failed") return <MarkOf mark={item.outcome.mark}>{item.outcome.text}</MarkOf>;
  if (item.value === 0) return <MarkOf mark={EMPTY_MARK}>{empty}</MarkOf>;
  return (
    <span>
      <span className="num">{formatNumber(item.value)}</span> {item.value === 1 ? unit[0] : unit[1]}
    </span>
  );
}

function mapped<T, U>(item: Fetched<T>, map: (value: T) => U): Fetched<U> {
  return item.state === "ready" ? { state: "ready", value: map(item.value) } : item;
}

export interface HomeDiagnosticsProps {
  home: HomeData;
  links?: HomeLinks | undefined;
  /** El perfil de misión enseñado (la ubicación elegida en «Inicio»); por omisión, `home.shownRoute`. */
  profileId?: string | null | undefined;
  /** Si el bloque está a la vista: oculto, no pide nada. */
  active?: boolean | undefined;
}

/** El bloque entero, con sus peticiones. Lo coloca la consola bajo su separador. */
export function HomeDiagnostics({ home, links, profileId, active = true }: HomeDiagnosticsProps) {
  const [ui, dispatch] = useReducer(diagnosticsReducer, DIAGNOSTICS_CLOSED);
  // Fuera de la vista (otra pestaña), la ventana del visor no se queda tapando la consola.
  useEffect(() => {
    if (!active) dispatch({ type: "close-viewer" });
  }, [active]);
  const data = useDiagnosticsData(home, active, {
    protocols: ui.test === "ultrasound",
    others: ui.test === "other",
  });
  return <HomeDiagnosticsView home={home} links={links} profileId={profileId} data={data} ui={ui} dispatch={dispatch} />;
}

/**
 * El bloque sin peticiones: lo que se pinta con lo recibido y con lo que está abierto (así se
 * prueba sin red ni DOM: `ui` dice qué se desplegó y `dispatch` recibe cada pulsación).
 */
export function HomeDiagnosticsView({
  home,
  links,
  profileId,
  data,
  ui = DIAGNOSTICS_CLOSED,
  dispatch = () => undefined,
}: HomeDiagnosticsProps & {
  data: DiagnosticsData;
  ui?: DiagnosticsUi | undefined;
  dispatch?: ((action: DiagnosticsAction) => void) | undefined;
}) {
  const shown = profileId === undefined ? home.shownRoute : profileId;
  const profile = home.matrix?.profiles.find((item) => item.id === shown) ?? null;
  const capability = profile?.cells.find((cell) => cell.key === "medical_capability") ?? null;
  const short = profile === null ? null : (PROFILE_SHORT[profile.id] ?? capitalized(profile.display));
  return (
    <section
      data-ui="home-diagnostics"
      className="ref-frame dx-frame"
      aria-label={tr("Diagnóstico integrado: pruebas y visualización", "Integrated diagnostics: tests and visualization")}
    >
      <PanelTitle pictogram="picture" className="ref-h ref-frame-h">
        {tr("Diagnóstico integrado: pruebas y visualización", "Integrated diagnostics: tests and visualization")}
        {short !== null && <span className="secondary"> ({short})</span>}
      </PanelTitle>
      {capability !== null && (
        <p className="secondary dx-capability ref-clamp-2" title={capability.text}>
          <strong>{capitalized(capability.label)}:</strong> {capability.text}
        </p>
      )}
      <div className="dx-grid">
        <DiagnosticTests home={home} data={data} open={ui.test} dispatch={dispatch} />
        <VolumePreview data={data} viewer={ui.viewer} dispatch={dispatch} />
        <StateAnalysis home={home} links={links} />
        <KeyTrends home={home} data={data} />
      </div>
    </section>
  );
}

type Dispatch = (action: DiagnosticsAction) => void;

/** Cuántas filas enseña una prueba desplegada; las demás se cuentan debajo. */
export const DETAIL_ROWS = 5;

/** Lo más reciente primero, por la fecha ISO que diga `at` (una fecha ilegible, al final). */
function newestFirst<T>(items: readonly T[], at: (item: T) => string): T[] {
  const time = (item: T) => {
    const value = Date.parse(at(item));
    return Number.isFinite(value) ? value : Number.NEGATIVE_INFINITY;
  };
  return [...items].sort((a, b) => time(b) - time(a));
}

/** Un instante del backend en UTC; ilegible, la marca de dato ausente y no una excepción. */
function When({ at }: { at: string | number }) {
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return <MarkOf mark={MISSING_MARK}>{tr("sin fecha", "no date")}</MarkOf>;
  return <span className="num">{formatUtc(date)}</span>;
}

/** Una prueba sin nada registrado: lo dice en gris, con el anillo punteado de «vacío». */
function NoRecord({ children }: { children: string }) {
  return (
    <p className="secondary dx-detail-empty">
      <MarkOf mark={EMPTY_MARK}>{children}</MarkOf>
    </p>
  );
}

/** Las filas que no caben, contadas. */
function More({ total }: { total: number }) {
  if (total <= DETAIL_ROWS) return null;
  return (
    <p className="secondary dx-detail-more">
      {tr("y", "and")} <span className="num">{formatNumber(total - DETAIL_ROWS)}</span> {tr("más", "more")}
    </p>
  );
}

/** Las pruebas: cada una se despliega en la tarjeta con lo que el backend tiene registrado. */
function DiagnosticTests({
  home,
  data,
  open,
  dispatch,
}: {
  home: HomeData;
  data: DiagnosticsData;
  open: TestKey | null;
  dispatch: Dispatch;
}) {
  const reference = home.reference;
  const base = useId();
  const tests: {
    key: TestKey;
    label: string;
    pictogram: PictogramName;
    count: Fetched<number> | null;
    unit: [string, string];
    empty: string;
  }[] = [
    {
      key: "ultrasound",
      label: tr("Ecografía / ultrasonido", "Ultrasound"),
      pictogram: "probe-arcs",
      count: mapped(data.ultrasound, (items) => items.length),
      unit: [tr("estudio", "study"), tr("estudios", "studies")],
      empty: tr("sin estudios", "no studies"),
    },
    {
      key: "biomarkers",
      label: tr("Biomarcadores", "Biomarkers"),
      pictogram: "vial",
      count: mapped(data.labs, (series) => countInWindow(series, home.catalog, reference)),
      unit: [
        tr("indicador con lecturas en 30 d", "indicator with readings in 30 d"),
        tr("indicadores con lecturas en 30 d", "indicators with readings in 30 d"),
      ],
      empty: tr("sin lecturas en 30 d", "no readings in 30 d"),
    },
    {
      key: "lab-reports",
      label: tr("Analíticas (sangre/orina)", "Lab tests (blood/urine)"),
      pictogram: "clipboard",
      count: mapped(data.reports, (items) => items.filter((item) => item.kind === LAB_REPORT).length),
      unit: [tr("informe", "report"), tr("informes", "reports")],
      empty: tr("sin informes", "no reports"),
    },
    {
      key: "other",
      label: tr("Otras pruebas (PVT, cognición, dolor)", "Other tests (PVT, cognition, pain)"),
      pictogram: "stopwatch",
      count: null,
      unit: ["", ""],
      empty: "",
    },
  ];
  return (
    <article className="ref-card dx-tests" aria-label={tr("Pruebas", "Tests")}>
      <h3 className="ref-h3">{tr("Pruebas", "Tests")}</h3>
      <ul>
        {tests.map((test) => {
          const expanded = open === test.key;
          const detailId = `${base}-${test.key}`;
          return (
            <li key={test.key} data-test={test.key}>
              <button
                type="button"
                className="dx-test"
                aria-expanded={expanded}
                aria-controls={expanded ? detailId : undefined}
                title={expanded ? tr("Plegar", "Collapse") : tr("Ver lo registrado", "Show what is on record")}
                onClick={() => dispatch({ type: "toggle-test", test: test.key })}
              >
                <Pictogram name={test.pictogram} />
                <span className="dx-test-text">
                  <span className="dx-test-name" title={test.label}>
                    {test.label}
                  </span>
                  {test.count !== null && (
                    <small className="dx-test-count">
                      <Count item={test.count} unit={test.unit} empty={test.empty} />
                    </small>
                  )}
                </span>
              </button>
              {expanded && (
                <div id={detailId} className="dx-detail" role="region" aria-label={test.label}>
                  <TestDetail test={test.key} home={home} data={data} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </article>
  );
}

/** Lo registrado de una prueba desplegada. */
function TestDetail({ test, home, data }: { test: TestKey; home: HomeData; data: DiagnosticsData }) {
  switch (test) {
    case "ultrasound":
      return <UltrasoundDetail studies={data.ultrasound} protocols={data.protocols} />;
    case "biomarkers":
      return <BiomarkerDetail home={home} labs={data.labs} />;
    case "lab-reports":
      return <LabReportDetail reports={data.reports} />;
    case "other":
      return <OtherDetail others={data.others} />;
  }
}

/** Los estudios de ecografía, el más reciente primero, con el nombre de protocolo del backend. */
function UltrasoundDetail({
  studies,
  protocols,
}: {
  studies: Fetched<ImagingStudy[]>;
  protocols: Fetched<ProtocolCatalog> | undefined;
}) {
  if (studies.state !== "ready") return <Pending item={studies} />;
  if (studies.value.length === 0) return <NoRecord>{tr("sin registro de ecografía", "no ultrasound on record")}</NoRecord>;
  const names = new Map<string, string>(
    protocols?.state === "ready" ? protocols.value.protocols.map((item) => [item.key, item.display]) : [],
  );
  const rows = newestFirst(studies.value, (item) => item.recorded);
  return (
    <>
      {/* Sin catálogo, cada estudio con su clave de protocolo y el motivo del fallo encima. */}
      {protocols?.state === "failed" && <Pending item={protocols} />}
      <ul className="dx-detail-list">
        {rows.slice(0, DETAIL_ROWS).map((study) => {
          const name = names.get(study.protocol) ?? study.protocol;
          return (
            <li key={study.ledger_index} data-detail-row="">
              <span className="ref-ellipsis" title={name}>
                {name}
              </span>
              <span className="secondary">
                <When at={study.recorded} /> ·{" "}
                <span className="num">{formatNumber(study.frames)}</span>{" "}
                {study.frames === 1 ? tr("fotograma", "frame") : tr("fotogramas", "frames")}
                {study.synthetic === true ? tr(" · fantoma simulado", " · simulated phantom") : ""}
                {study.dataset !== undefined ? tr(" · ejemplo de un dataset público", " · public dataset sample") : ""}
              </span>
            </li>
          );
        })}
      </ul>
      <More total={rows.length} />
    </>
  );
}

/** Los indicadores de laboratorio con lecturas en 30 días, cada uno con su última cifra. */
function BiomarkerDetail({ home, labs }: { home: HomeData; labs: Fetched<LabSeries[]> }) {
  if (labs.state !== "ready") return <Pending item={labs} />;
  const rows = labRows(labs.value, home.catalog, home.reference);
  if (rows.length === 0) return <NoRecord>{tr("sin registro en 30 d", "no record in 30 d")}</NoRecord>;
  return (
    <>
      <ul className="dx-detail-list">
        {rows.slice(0, DETAIL_ROWS).map(({ indicator, last }) => (
          <li key={indicator.key} data-detail-row="">
            <span className="ref-ellipsis" title={indicator.display_es}>
              <IndicatorName indicatorKey={indicator.key} displayEs={indicator.display_es} />
            </span>
            <span className="secondary">
              <span className="num">{formatNumber(last.value, indicator.decimals)}</span> {displayUnit(indicator.unit)} ·{" "}
              <When at={last.at} />
            </span>
          </li>
        ))}
      </ul>
      <More total={rows.length} />
    </>
  );
}

/** Los informes escaneados que son analíticas, el más reciente primero. */
function LabReportDetail({ reports }: { reports: Fetched<ScannedReport[]> }) {
  if (reports.state !== "ready") return <Pending item={reports} />;
  const rows = newestFirst(
    reports.value.filter((item) => item.kind === LAB_REPORT),
    (item) => item.recorded,
  );
  if (rows.length === 0) return <NoRecord>{tr("sin registro de analíticas", "no lab tests on record")}</NoRecord>;
  return (
    <>
      <ul className="dx-detail-list">
        {rows.slice(0, DETAIL_ROWS).map((report) => {
          const figures = report.lab_readings?.readings.length ?? null;
          return (
            <li key={report.ledger_index} data-detail-row="">
              <When at={report.recorded} />
              <span className="secondary">
                <span className="num">{formatNumber(report.pages)}</span>{" "}
                {report.pages === 1 ? tr("página", "page") : tr("páginas", "pages")}
                {figures !== null && (
                  <>
                    {" · "}
                    <span className="num">{formatNumber(figures)}</span>{" "}
                    {figures === 1 ? tr("cifra leída", "figure read") : tr("cifras leídas", "figures read")}
                  </>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      <More total={rows.length} />
    </>
  );
}

/** Una sesión de PVT o de cognición tal como la lee el backend del registro firmado. */
interface SessionLike {
  effective: string;
  values: { key: string; display: string; display_es: string; value_text: string }[];
}

/** Cuántas cifras de la última sesión caben en su línea. */
const SESSION_VALUES = 2;

/** La última sesión: su fecha y sus primeras cifras, con las palabras del backend. */
function LastSession({ item }: { item: Fetched<{ sessions: SessionLike[] }> }) {
  if (item.state !== "ready") return <Pending item={item} />;
  const last = newestFirst(item.value.sessions, (session) => session.effective)[0];
  if (last === undefined) return <NoRecord>{tr("sin registro", "no record")}</NoRecord>;
  return (
    <p>
      <When at={last.effective} />
      {last.values.slice(0, SESSION_VALUES).map((value) => (
        <span key={value.key} className="secondary">
          {" · "}
          {tr(value.display_es, value.display)}: {value.value_text}
        </span>
      ))}
    </p>
  );
}

/** El último dolor registrado: su fecha, su intensidad máxima y cuántas zonas. */
function LastPain({ item }: { item: Fetched<PainReport[]> }) {
  if (item.state !== "ready") return <Pending item={item} />;
  const last = newestFirst(item.value, (report) => report.effective)[0];
  if (last === undefined) return <NoRecord>{tr("sin registro", "no record")}</NoRecord>;
  return (
    <p>
      <When at={last.effective} />
      <span className="secondary">
        {" · "}
        {tr("intensidad máxima", "maximum intensity")} <span className="num">{formatNumber(last.intensity)}</span>
        {" · "}
        <span className="num">{formatNumber(last.zones.length)}</span>{" "}
        {last.zones.length === 1 ? tr("zona", "area") : tr("zonas", "areas")}
      </span>
    </p>
  );
}

/** PVT, cognición y dolor: lo último de cada uno, o que no hay registro. */
function OtherDetail({ others }: { others: OtherTestsData | undefined }) {
  if (others === undefined) return <Loading />;
  return (
    <dl className="dx-detail-other">
      <dt>PVT</dt>
      <dd data-other="pvt">
        <LastSession item={others.pvt} />
      </dd>
      <dt>{tr("Cognición", "Cognition")}</dt>
      <dd data-other="cognition">
        <LastSession item={others.cognition} />
      </dd>
      <dt>{tr("Dolor", "Pain")}</dt>
      <dd data-other="pain">
        <LastPain item={others.pain} />
      </dd>
    </dl>
  );
}

/** Cuántos indicadores de laboratorio tienen alguna lectura en la ventana (no solo los enseñados). */
function countInWindow(series: readonly LabSeries[], catalog: ReadonlyMap<string, Indicator>, reference: number): number {
  const from = reference - TREND_WINDOW_MS;
  return series.filter(
    (item) => catalog.has(item.key) && item.readings.some((reading) => reading.at >= from && reading.at <= reference),
  ).length;
}

/**
 * La vista previa del último volumen: rótulos del backend y, al pulsar, el visor completo en una
 * ventana encima de la pestaña. Sin volumen, lo dice; sin segmentador, su motivo del backend, en gris.
 */
function VolumePreview({ data, viewer, dispatch }: { data: DiagnosticsData; viewer: boolean; dispatch: Dispatch }) {
  const { volumes, segmenter } = data;
  const latest = volumes.state === "ready" ? latestVolume(volumes.value) : null;
  const segmentation = latest?.segmentation ?? null;
  const unavailable = segmenterNote(segmenter);
  const openViewer = () => dispatch({ type: "open-viewer" });
  const openFull = tr("Abrir el visor completo de Polaris", "Open the full Polaris viewer");
  // Las estructuras con su volumen, para el nombre accesible del render: cifras y nombres del backend.
  const structureList =
    segmentation === null
      ? ""
      : segmentation.estructuras
          .map((item) => `${item.nombre} ${formatNumber(item.volumen_ml, 1)} ${displayUnit("mL")}`)
          .join(", ");
  return (
    <article className="ref-card dx-viewer" aria-label={tr("Visor 3D de Polaris", "Polaris 3D viewer")}>
      <h3 className="ref-h3">
        {tr("Visor 3D", "3D viewer")} <span className="secondary">(Polaris)</span>
      </h3>
      <Pending item={volumes} />
      {volumes.state === "ready" && latest === null && (
        <div className="dx-preview dx-preview-empty">
          <Pictogram name="picture" />
          <p>
            <MarkOf mark={EMPTY_MARK}>{tr("Sin volúmenes registrados.", "No volumes recorded.")}</MarkOf>
          </p>
        </div>
      )}
      {latest !== null && (
        <div className={segmentation === null ? "dx-preview" : "dx-preview dx-preview-render"}>
          {segmentation === null ? (
            <Pictogram name={previewPictogram(undefined)} />
          ) : (
            <SegmentationPreview
              segmentation={segmentation}
              label={tr(
                `${segmentation.preset_nombre} (Polaris), vista de frente de la segmentación automática sin validar: ${structureList}`,
                `${segmentation.preset_nombre} (Polaris), front view of the unverified automatic segmentation: ${structureList}`,
              )}
              open={{ label: openFull, onClick: openViewer }}
            />
          )}
          <div className="dx-preview-text">
            <strong className="dx-preview-name">
              {segmentation === null ? latest.study.modality : `${segmentation.preset_nombre} (Polaris)`}
            </strong>
            <span className="secondary">
              {latest.study.modality} · <When at={latest.study.recorded} />
            </span>
            {segmentation === null ? (
              <MarkOf mark={EMPTY_MARK}>{NO_SEGMENTATION}</MarkOf>
            ) : (
              <>
                <span className="secondary">{segmentation.estado}</span>
                <ul className="dx-structures">
                  {segmentation.estructuras.slice(0, 3).map((item) => (
                    <li key={item.key}>
                      <span className="ref-ellipsis" title={item.nombre}>
                        {item.nombre}
                      </span>
                      <span className="num">
                        {formatNumber(item.volumen_ml, 1)} {displayUnit("mL")}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </div>
      )}
      {unavailable !== null && (
        <p className="dx-note dx-note-unavailable" title={unavailable}>
          <MarkOf mark={UNAVAILABLE_MARK}>{unavailable}</MarkOf>
        </p>
      )}
      {latest?.study.dataset !== undefined && (
        <p className="secondary dx-note dx-note-dataset" title={DATASET_NOTE}>
          {DATASET_NOTE}
        </p>
      )}
      <p className="secondary dx-note dx-note-reference" title={REFERENCE_NOTE}>
        {REFERENCE_NOTE}
      </p>
      {/* También con segmentación, aunque el render lleve el suyo en la esquina: el render no se pinta
          si sus mallas no llegan, y el visor de Polaris sí podría abrirse. Sin volúmenes, nada que abrir. */}
      {latest !== null && (
        <div className="ref-quick-links dx-open">
          <Command pictogram="layers-stack" type="button" onClick={openViewer} aria-haspopup="dialog" aria-expanded={viewer}>
            <span>{segmentation === null ? tr("Abrir volúmenes", "Open volumes") : tr("Abrir visor completo", "Open full viewer")}</span>
          </Command>
        </div>
      )}
      {viewer && <ViewerDialog data={data} onClose={() => dispatch({ type: "close-viewer" })} />}
    </article>
  );
}

const NO_SEGMENTATION = tr(
  "Sin segmentación: el volumen está registrado y firmado.",
  "No segmentation: the volume is recorded and signed.",
);

/** El motivo del backend por el que no hay segmentador, o `null` si lo hay (o aún no se sabe). */
function segmenterNote(segmenter: Fetched<SegmenterStatus>): string | null {
  return segmenter.state === "ready" && !segmenter.value.available ? segmenter.value.note : null;
}

/**
 * El visor de NiiVue para los presets que Polaris no pinta (los ojos): pesa (NiiVue), así que solo
 * se carga cuando una ventana lo abre. El de Polaris es un `<iframe>` y va directo.
 */
const VolumeViewer = lazy(() => import("../volumes/VolumeViewer").then((module) => ({ default: module.VolumeViewer })));

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), iframe, [tabindex]:not([tabindex="-1"])';

/**
 * Tab y Mayús+Tab dan la vuelta dentro de la ventana: con `aria-modal`, salir de ella llevaría el
 * foco a mandos tapados por el fondo, que no se ven.
 */
function keepFocusInside(container: HTMLElement, event: { shiftKey: boolean; preventDefault: () => void }): void {
  const items = [...container.querySelectorAll<HTMLElement>(FOCUSABLE)];
  const first = items[0];
  const last = items[items.length - 1];
  if (first === undefined || last === undefined) {
    event.preventDefault();
    return;
  }
  const at = document.activeElement;
  if (event.shiftKey && (at === first || at === container)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && at === last) {
    event.preventDefault();
    first.focus();
  }
}

/**
 * La ventana del visor completo, encima de la pestaña: el de Polaris donde Polaris sabe pintar el
 * órgano y el propio para el resto, como hacía «Imagen e informes»; sin segmentación, la lista de
 * volúmenes y el motivo del backend. Se cierra con Escape, con «Cerrar» o pulsando fuera; al
 * abrirse lleva el foco a la ventana y al cerrarse lo devuelve a quien la abrió. Va bajo la franja
 * de estado (que sigue a la vista con sus alertas) y se pinta dentro de la concha (`.app`), donde
 * viven sus variables; sin documento (pruebas sin DOM), en su sitio.
 */
function ViewerDialog({ data, onClose }: { data: DiagnosticsData; onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const pressedOutside = useRef(false);
  const close = useRef(onClose);
  const titleId = useId();
  useEffect(() => {
    close.current = onClose;
  }, [onClose]);
  useEffect(() => {
    const before = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    box.current?.focus();
    // Escape cierra, pero no se lo queda: sigue contando para el triple Escape de la emergencia
    // (`EmergencyVoice`) y para parar la voz, como pasa con un desplegable que se cierra.
    const onKey = (event: KeyboardEvent) => {
      if (viewerKeyAction(event.key) === null) return;
      close.current();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      before?.focus();
    };
  }, []);

  const { volumes, segmenter } = data;
  const latest = volumes.state === "ready" ? latestVolume(volumes.value) : null;
  const segmentation = latest?.segmentation ?? null;
  const unavailable = segmenterNote(segmenter);
  const dialog = (
    <div
      className="dx-modal"
      // Pulsar fuera cierra solo si la pulsación empezó fuera: un arrastre que gira el volumen y
      // se suelta más allá del borde no la cierra.
      onPointerDown={(event) => {
        pressedOutside.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        if (pressedOutside.current && event.target === event.currentTarget) onClose();
        pressedOutside.current = false;
      }}
    >
      <div
        ref={box}
        className="dx-modal-box"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={(event) => {
          if (event.key === "Tab" && box.current !== null) keepFocusInside(box.current, event);
        }}
      >
        <div className="dx-modal-head">
          <h2 id={titleId} className="dx-modal-title">
            {tr("Visor 3D", "3D viewer")} <span className="secondary">(Polaris)</span>
          </h2>
          <Command concept="cancel" type="button" onClick={onClose}>
            <span>{tr("Cerrar", "Close")}</span>
          </Command>
        </div>
        <p className="secondary">{REFERENCE_NOTE}</p>
        {latest?.study.dataset !== undefined && <p className="secondary">{DATASET_NOTE}</p>}
        <Pending item={volumes} />
        {segmentation !== null && (
          <>
            <p>
              <strong>{segmentation.preset_nombre} (Polaris)</strong>{" "}
              <span className="secondary">· {segmentation.estado}</span>
            </p>
            {POLARIS_PRESETS.has(segmentation.preset) ? (
              <PolarisViewer key={segmentation.ledger_index} segmentation={segmentation} />
            ) : (
              <Suspense fallback={<Loading />}>
                <VolumeViewer key={segmentation.ledger_index} segmentation={segmentation} />
              </Suspense>
            )}
          </>
        )}
        {volumes.state === "ready" && segmentation === null && (
          <>
            <p>
              <MarkOf mark={EMPTY_MARK}>
                {volumes.value.length === 0 ? tr("Sin volúmenes registrados.", "No volumes recorded.") : NO_SEGMENTATION}
              </MarkOf>
            </p>
            {volumes.value.length > 0 && (
              <ul className="dx-detail-list" aria-label={tr("Volúmenes", "Volumes")}>
                {newestFirst(volumes.value, (item) => item.recorded).map((study) => (
                  <li key={study.ledger_index} data-volume={study.ledger_index}>
                    <span>{study.modality}</span>
                    <span className="secondary">
                      <span className="num">{study.shape.map((n) => formatNumber(n)).join("×")}</span> ·{" "}
                      <When at={study.recorded} />
                      {study.dataset !== undefined ? tr(" · ejemplo de un dataset público", " · public dataset sample") : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        {unavailable !== null && (
          <p>
            <MarkOf mark={UNAVAILABLE_MARK}>{unavailable}</MarkOf>
          </p>
        )}
      </div>
    </div>
  );
  if (typeof document === "undefined") return dialog;
  return createPortal(dialog, document.querySelector(".app") ?? document.body);
}

/** Variable `--lvl` con el color del nivel, como «Inicio» (el sin color de alerta, en verde). */
function levelVar(level: string): CSSProperties {
  const token = levelToken(level);
  const shown = token === null ? "gray" : token === "text" ? "green" : token;
  return { "--lvl": `var(${cssVar(shown)})` } as CSSProperties;
}

/**
 * El análisis del backend: el nivel global con su resumen y los dominios que no están en el nivel
 * más bajo, con su primera causa en palabras del backend. Ningún borrador del modelo de lenguaje.
 */
function StateAnalysis({ home, links }: { home: HomeData; links?: HomeLinks | undefined }) {
  const { status, lowest } = home;
  const toHazards = sectionLink(links, "hazards");
  const raised = Object.entries(status.domains).filter(([, risk]) => risk.level !== lowest);
  return (
    <article className="ref-card dx-analysis" aria-label={tr("Análisis del estado", "Status analysis")}>
      <h3 className="ref-h3">{tr("Análisis del estado", "Status analysis")}</h3>
      <p className="dx-level">
        <span className="ref-pill" style={levelVar(status.overall_level)}>
          <LevelBadge level={status.overall_level} />
        </span>
      </p>
      <p className="ref-clamp-2 dx-summary" title={status.summary}>
        {status.summary}
      </p>
      {raised.length > 0 && (
        <ul className="dx-findings">
          {raised.slice(0, 3).map(([domain, risk]) => (
            <li key={domain} title={risk.drivers.join(" · ")}>
              <span className="dx-finding-head">
                <DomainName domain={domain} /> <LevelBadge level={risk.level} />
              </span>
              {risk.drivers[0] !== undefined && <span className="secondary ref-clamp-2">{risk.drivers[0]}</span>}
            </li>
          ))}
        </ul>
      )}
      {toHazards !== null && (
        <div className="ref-quick-links dx-open">
          <Command
            concept="detail"
            type="button"
            onClick={toHazards.open}
            aria-label={tr(`Abrir ${toHazards.name}: detalle del análisis`, `Open ${toHazards.name}: analysis detail`)}
          >
            <span>{tr("Ver detalle", "View detail")}</span>
          </Command>
        </div>
      )}
    </article>
  );
}

/** Las series de laboratorio de los últimos 30 días, cada una con su última cifra del catálogo. */
function KeyTrends({ home, data }: { home: HomeData; data: DiagnosticsData }) {
  const { reference, catalog } = home;
  const rows = data.labs.state === "ready" ? labTrends(data.labs.value, catalog, reference) : [];
  return (
    <article className="ref-card dx-trends" aria-label={tr("Tendencias clave de 30 días", "Key trends over 30 days")}>
      <h3 className="ref-h3">
        {tr("Tendencias clave", "Key trends")} <span className="secondary">(30 d)</span>
      </h3>
      <Pending item={data.labs} />
      {data.labs.state === "ready" && rows.length === 0 && (
        <p>
          <MarkOf mark={MISSING_MARK}>
            {tr("sin analíticas en los últimos 30 días", "no lab tests in the last 30 days")}
          </MarkOf>
        </p>
      )}
      {rows.length > 0 && (
        <ul>
          {rows.map(({ indicator, readings, last }) => {
            const age = (reference - last.at) / 60_000;
            return (
              <li key={indicator.key} data-lab={indicator.key}>
                <span className="ref-ellipsis dx-trend-name" title={indicator.display_es}>
                  <IndicatorName indicatorKey={indicator.key} displayEs={indicator.display_es} />
                </span>
                <Sparkline readings={readings} until={reference} windowMs={TREND_WINDOW_MS} />
                <Mark pictogram={null} className="dx-trend-value">
                  <span className="num">{formatNumber(last.value, indicator.decimals)}</span>{" "}
                  <small>{displayUnit(indicator.unit)}</small>
                  {age >= 1 && (
                    <small
                      className="secondary"
                      title={tr(
                        "Edad de la última lectura frente a la referencia del estado",
                        "Age of the last reading relative to the status reference",
                      )}
                    >
                      {" "}
                      {tr(`hace ${formatAge(age)}`, `${formatAge(age)} ago`)}
                    </small>
                  )}
                </Mark>
              </li>
            );
          })}
        </ul>
      )}
    </article>
  );
}
