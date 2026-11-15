import { type CSSProperties, useEffect, useState } from "react";

import { Command } from "../components/Command";
import { DomainName } from "../components/DomainName";
import { IndicatorName } from "../components/IndicatorName";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { Pictogram, type PictogramName } from "../icons";
import {
  type FhirObservation,
  type ImagingStudy,
  type Indicator,
  type ScannedReport,
  type VolumeSegmentation,
  type VolumeStudy,
  api,
} from "../lib/api";
import { displayUnit, formatAge, formatNumber, formatUtc } from "../lib/format";
import { tr } from "../lib/i18n";
import { cssVar } from "../lib/palette";
import { EMPTY_MARK, MISSING_MARK, UNAVAILABLE_MARK, requestOutcome } from "../lib/marks";
import { type Fetched, type HomeData, type HomeLinks, sectionLink } from "./HomeBoard";
import { type Reading, Sparkline, levelToken } from "./HomeCharts";
import { capitalized } from "./HazardCards";
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
 *   sin segmentación, no hay dibujo. El visor completo (`volumes/PolarisViewer.tsx`, cortes y TAC)
 *   pesa y no se carga aquí: un mando lleva a «Imagen e informes». Los rótulos (preset,
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
export function useDiagnosticsData(home: HomeData, active = true): DiagnosticsData {
  const { status, indicators } = home;
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

  return { volumes, segmenter, ultrasound, reports, labs };
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
    .slice(0, TREND_ROWS)
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
  const data = useDiagnosticsData(home, active);
  return <HomeDiagnosticsView home={home} links={links} profileId={profileId} data={data} />;
}

/** El bloque sin peticiones: lo que se pinta con lo recibido (así se prueba sin red ni DOM). */
export function HomeDiagnosticsView({
  home,
  links,
  profileId,
  data,
}: HomeDiagnosticsProps & { data: DiagnosticsData }) {
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
        <DiagnosticTests home={home} links={links} data={data} />
        <VolumePreview links={links} data={data} />
        <StateAnalysis home={home} links={links} />
        <KeyTrends home={home} data={data} />
      </div>
    </section>
  );
}

type Part = { home: HomeData; links?: HomeLinks | undefined; data: DiagnosticsData };

/** Las pruebas, cada una con lo que consta y el acceso a la sección donde se hacen y se ven. */
function DiagnosticTests({ home, links, data }: Part) {
  const reference = home.reference;
  const tests: {
    key: string;
    label: string;
    section: string;
    pictogram: PictogramName;
    count: Fetched<number> | null;
    unit: [string, string];
    empty: string;
  }[] = [
    {
      key: "ultrasound",
      label: tr("Ecografía / ultrasonido", "Ultrasound"),
      section: "imaging",
      pictogram: "probe-arcs",
      count: mapped(data.ultrasound, (items) => items.length),
      unit: [tr("estudio", "study"), tr("estudios", "studies")],
      empty: tr("sin estudios", "no studies"),
    },
    {
      key: "biomarkers",
      label: tr("Biomarcadores", "Biomarkers"),
      section: "body",
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
      section: "imaging",
      pictogram: "clipboard",
      count: mapped(data.reports, (items) => items.filter((item) => item.kind === LAB_REPORT).length),
      unit: [tr("informe", "report"), tr("informes", "reports")],
      empty: tr("sin informes", "no reports"),
    },
    {
      key: "other",
      label: tr("Otras pruebas (PVT, cognición, dolor)", "Other tests (PVT, cognition, pain)"),
      section: "log",
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
          const link = sectionLink(links, test.section);
          const body = (
            <>
              <Pictogram name={test.pictogram} />
              <span className="dx-test-text">
                <span className="dx-test-name" title={test.label}>{test.label}</span>
                {test.count !== null && (
                  <small className="dx-test-count">
                    <Count item={test.count} unit={test.unit} empty={test.empty} />
                  </small>
                )}
              </span>
            </>
          );
          return (
            <li key={test.key} data-test={test.key}>
              {link === null ? (
                <span className="dx-test">{body}</span>
              ) : (
                <button
                  type="button"
                  className="dx-test"
                  aria-label={tr(`Abrir ${link.name}: ${test.label}`, `Open ${link.name}: ${test.label}`)}
                  title={tr(`Abrir ${link.name}`, `Open ${link.name}`)}
                  onClick={link.open}
                >
                  {body}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </article>
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
 * La vista previa del último volumen: rótulos del backend, sin el visor (pesa; está en «Imagen e
 * informes»). Sin volumen, lo dice; sin segmentador, su motivo del backend, en gris.
 */
function VolumePreview({ links, data }: { links?: HomeLinks | undefined; data: DiagnosticsData }) {
  const toImaging = sectionLink(links, "imaging");
  const { volumes, segmenter } = data;
  const latest = volumes.state === "ready" ? latestVolume(volumes.value) : null;
  const segmentation = latest?.segmentation ?? null;
  const unavailable = segmenter.state === "ready" && !segmenter.value.available ? segmenter.value.note : null;
  const openFull = toImaging === null ? "" : tr(`Abrir ${toImaging.name}: visor completo`, `Open ${toImaging.name}: full viewer`);
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
              open={toImaging === null ? undefined : { label: openFull, onClick: toImaging.open }}
            />
          )}
          <div className="dx-preview-text">
            <strong className="dx-preview-name">
              {segmentation === null ? latest.study.modality : `${segmentation.preset_nombre} (Polaris)`}
            </strong>
            <span className="secondary">
              {latest.study.modality} · <span className="num">{formatUtc(new Date(latest.study.recorded))}</span>
            </span>
            {segmentation === null ? (
              <MarkOf mark={EMPTY_MARK}>
                {tr(
                  "Sin segmentación: el volumen está registrado y firmado.",
                  "No segmentation: the volume is recorded and signed.",
                )}
              </MarkOf>
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
      {toImaging !== null && segmentation === null && (
        <div className="ref-quick-links dx-open">
          <Command pictogram="layers-stack" type="button" onClick={toImaging.open} aria-label={openFull}>
            <span>
              {segmentation === null ? tr("Abrir volúmenes", "Open volumes") : tr("Abrir visor completo", "Open full viewer")}
            </span>
          </Command>
        </div>
      )}
    </article>
  );
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
