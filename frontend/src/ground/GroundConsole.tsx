import { useEffect, useState } from "react";

import { Chosen } from "../components/Chosen";
import { type ConsoleSection, ConsoleTabs, personal, pinned, useStoredSection } from "../components/ConsoleTabs";
import { UrgentHelp } from "../dashboard/HomeBoard";
import { DomainName } from "../components/DomainName";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { tr } from "../lib/i18n";
import { StatTile, StatTiles } from "../components/StatTile";
import {
  type AuditReport,
  type CrewStatus,
  type DeclaredLink,
  type FhirObservation,
  type Indicator,
  type LinkSync,
  api,
} from "../lib/api";
import { formatMet, formatMinutes, formatNumber, missionElapsedSeconds } from "../lib/format";
import { ImagingHistory } from "../imaging/ImagingHistory";
import { domainLabel } from "../lib/levels";
import { MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { fhirConfidence, fhirProvenance } from "../lib/provenance";
import { uiPictogram } from "../lib/uiMarks";
import type { AlertCounts } from "../lib/alerts";
import { BaselineProfilePanel } from "../dashboard/BaselineProfilePanel";
import { CycleSection } from "../cycle/CycleSection";
import { ActiveEnvironment, ENVIRONMENTS_GROUP, environmentSections, useProfileMatrix } from "../dashboard/Environments";
import { HazardCards } from "../dashboard/HazardCards";
import { Predictions } from "../dashboard/Predictions";
import { TwinQuestionsPanel } from "../dashboard/TwinQuestions";
import { SharingPanel } from "../dashboard/SharingPanel";
import { baselineRefreshKey, groundCut, linkedCut, twinsRefreshKey } from "../lib/crew";
import { groundLinkMark } from "../lib/linkSync";
import { HabitatPanel } from "../habitat/HabitatPanel";
import { LibraryPanel } from "../advisor/LibraryPanel";
import { GuidesPanel } from "../guides/GuidesPanel";
import { MissionModePanel } from "../components/MissionMode";
import { declaredLinkNotice } from "../habitat/systems";
import { PainHistory } from "../pain/PainHistory";
import { AuditPanel } from "./AuditPanel";
import { ForecastCheckPanel } from "./ForecastCheckPanel";
import { MeasurementCostPanel } from "./MeasurementCostPanel";
import { MissionProfilesPanel } from "./MissionProfilesPanel";
import { MissionHistoryPanel } from "./MissionHistoryPanel";
import { GroundNotesComposer } from "./GroundNotesComposer";
import { ContextSourcesPanel } from "./ContextSourcesPanel";
import { DocsPanel } from "./DocsPanel";
import { FacilitiesPanel } from "./FacilitiesPanel";
import { FrameworkPanel } from "./FrameworkPanel";
import { TestbedsPanel } from "./TestbedsPanel";
import { DatasetsPanel } from "./DatasetsPanel";
import { PeoplePanel } from "./PeoplePanel";
import { PolarisPanel } from "./PolarisPanel";
import { GroundPlannerPanel } from "../planner/GroundPlannerPanel";
import { RecoveryPanel } from "./RecoveryPanel";
import { type Point, type SeriesOrigin, TrendChart } from "./TrendChart";

/** Indicadores que se trazan: uno o dos por dominio, de los que genera el simulador o se registran. */
const CHARTED = [
  "heart-rate",
  "hrv-sdnn",
  "systolic-bp",
  "sleep-duration",
  "pvt-mean-rt",
  "cortisol-salivary",
  // Real: hemograma de Inspiration4 (OSD-569), si se ha cargado.
  "lymphocytes",
  // Autoinforme: la intensidad maxima de cada informe del mapa de dolor.
  "pain-intensity",
];

/**
 * Cuántas de `CHARTED`, en su orden, van en la primera rejilla de «Tendencias» (2026-11-15; desde el
 * 2026-11-16, la primera fila de la pestaña por páginas). Las cuatro primeras son las constantes
 * (frecuencia, VFC, tensión, sueño): la primera fila del tablero ancho. Se cuenta por `CHARTED` y no
 * por el orden del catálogo, que es el de `indicators`. Ninguna gráfica lleva aviso propio: las
 * alertas y los riesgos están en «Estado recibido» (el estado y los peligros, en su primera página).
 */
const TRENDS_ABOVE = 4;
const trendAbove = (key: string): boolean => {
  const index = CHARTED.indexOf(key);
  return index >= 0 && index < TRENDS_ABOVE;
};

const WINDOWS = [
  { label: "48 h", seconds: 2 * 86_400 },
  { label: "7 d", seconds: 7 * 86_400 },
  { label: tr("Misión", "Mission"), seconds: 400 * 86_400 },
];

/**
 * Consola de Tierra: densa, con historial, en la linea de Open MCT y de la consola
 * del ingeniero biomedico del Centro de Control de Houston.
 *
 * Y con lo que ninguno de los dos muestra: **el retardo aplicado**. Todo lo que
 * hay aqui es lo que Tierra puede tener, que es lo que habia a bordo hace un
 * tiempo de luz. Lo posterior esta en transito y no se dibuja.
 *
 * Limite declarado: en la demo las dos consolas corren en la misma maquina y el
 * retardo se aplica a partir del valor real de las efemerides de JPL. No hay un
 * enlace real con el espacio.
 */
export function GroundConsole({
  status,
  received,
  sync,
  counts,
}: {
  /** El estado a bordo: solo da el horizonte temporal, no se muestra. */
  status: CrewStatus;
  /** El estado que Tierra puede tener: calculado con las lecturas ya llegadas. */
  received: CrewStatus | null;
  /** El enlace con Tierra simulado (`GET /api/link-sync`): con él caído, el corte se queda en la caída. */
  sync: LinkSync;
  /** Los contadores de la franja de Tierra (de lo recibido): el recuento de su pestaña. */
  counts: AlertCounts;
}) {
  const [section, setSection] = useStoredSection("ground");
  // Tierra ve el entorno declarado, no lo declara (sin mando, como el nivel de misión).
  const environments = useProfileMatrix(status.mission.profile?.id);
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [catalog, setCatalog] = useState<Indicator[]>([]);
  const [series, setSeries] = useState<Record<string, Point[]>>({});
  const [origins, setOrigins] = useState<Record<string, SeriesOrigin[]>>({});
  const [audit, setAudit] = useState<AuditReport | null>(null);
  const [windowSeconds, setWindowSeconds] = useState(WINDOWS[1]?.seconds ?? 7 * 86_400);
  const [error, setError] = useState<RequestOutcome | null>(null);

  const reference = new Date(status.data.reference_time);
  const sourcesKey = status.mission.sources.join(",");
  const onboardUntil = missionElapsedSeconds(status.mission.start, reference);
  const oneWay = status.comms?.one_way_minutes ?? null;
  // El corte de Tierra, una sola cuenta (`groundCut`, §5.37.17): el mismo con que `App.tsx` pide
  // lo recibido, y el de las cinco preguntas, el hábitat, la línea base y los documentos. Antes
  // estos tres últimos lo rehacían en segundos de misión (`mission.start + receivedUntil`).
  // `null` sin efemérides y con el enlace arriba: Tierra ve hasta la última lectura de a bordo.
  // Con el enlace simulado declarado caído, el corte se queda en la caída (`linkedCut`, §5.47):
  // la misma cuenta que `App.tsx` con la misma respuesta del enlace.
  const cut = linkedCut(groundCut(status.data.reference_time, oneWay), sync);
  const receivedAt = cut ?? reference;
  const receivedUntil = missionElapsedSeconds(status.mission.start, receivedAt);
  // Lo que se vuelve a pedir con cada estado de a bordo: su última lectura y sus fuentes (dos
  // escenarios simulados pueden acabar en la misma fecha).
  const stateKey = `${status.data.reference_time}|${sourcesKey}`;

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.indicators(),
      // Las series son las del tripulante que se mira: sin sujeto, eran siempre las de crew-01.
      Promise.all(CHARTED.map((key) => api.observations(key, 5000, status.subject))),
      api.audit(8),
    ])
      .then(([catalog, observations, trail]) => {
        if (cancelled) return;
        setIndicators(catalog.indicators.filter((item) => CHARTED.includes(item.key)));
        setCatalog(catalog.indicators);
        const bySeries: Record<string, Point[]> = {};
        const byOrigin: Record<string, SeriesOrigin[]> = {};
        CHARTED.forEach((key, index) => {
          const resources = observations[index]?.observations ?? [];
          bySeries[key] = resources.map((obs) => ({
            met: missionElapsedSeconds(status.mission.start, new Date(obs.effectiveDateTime)),
            value: obs.valueQuantity.value,
            confidence: fhirConfidence(obs),
          }));
          byOrigin[key] = originsOf(resources);
        });
        setSeries(bySeries);
        setOrigins(byOrigin);
        setAudit(trail);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(requestOutcome(reason));
      });
    return () => {
      cancelled = true;
    };
    // Las fuentes van en las dependencias: dos escenarios simulados tienen la misma
    // fecha final y el mismo numero de lecturas, y sin ellas, al cambiar de
    // escenario, las graficas seguian mostrando el anterior.
  }, [
    status.subject,
    status.data.reference_time,
    status.mission.start,
    status.data.observations,
    sourcesKey,
  ]);

  // Umbral y palabra del backend: la interfaz no decide que es "baja confianza".
  const quality = status.data.quality;
  const lowConfidence = { threshold: quality.low_confidence_threshold, label: quality.labels.low };

  const onboardMet = formatMet(onboardUntil);
  const earthMet = formatMet(receivedUntil);
  // El corte de Tierra, el mismo que lleva el panel del hábitat de esta consola.
  const cutKey = receivedAt.toISOString();
  // Antes de que llegue a Tierra ninguna lectura no hay estado recibido (404) y el enlace
  // declarado no tenía de dónde leerse (lo que quedaba de §5.34.5): se lee entonces de
  // `/api/habitat/systems` con el corte, el mismo objeto que da `/api/status`. Va atado a su
  // corte: lo leído para otro corte no se pinta. Se vuelve a pedir con cada estado de a bordo.
  const [beforeAny, setBeforeAny] = useState<{
    cut: string;
    link: DeclaredLink | null;
    error: RequestOutcome | null;
  } | null>(null);
  const waiting = received === null;
  useEffect(() => {
    if (!waiting) return;
    let cancelled = false;
    api
      .habitatSystems(new Date(cutKey))
      .then((overview) => {
        if (!cancelled) setBeforeAny({ cut: cutKey, link: overview.declared_link, error: null });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setBeforeAny({ cut: cutKey, link: null, error: requestOutcome(reason) });
      });
    return () => {
      cancelled = true;
    };
  }, [waiting, cutKey, status]);
  const early = waiting && beforeAny?.cut === cutKey ? beforeAny : null;
  // El enlace con Tierra declarado degradado o caído (KB §2.1), tal y como Tierra lo puede tener:
  // lo declarado hasta su corte, lo mismo que pinta la franja en esta consola. Solo texto: el
  // corte de arriba sigue descontando solo el tiempo de luz, y la frase del backend lo dice.
  const link = declaredLinkNotice(received?.declared_link ?? early?.link ?? undefined);

  // La tabla de la consola de Tierra, como la de a bordo (§5.40): sección → paneles. La cabecera
  // del retardo queda fuera de las pestañas, siempre a la vista: es lo que define esta consola.
  // Las gráficas de «Tendencias» que van en la segunda rejilla (`trendAbove`).
  const below = indicators.filter((item) => !trendAbove(item.key));
  // Una gráfica de «Tendencias»: la misma en las dos rejillas.
  const trendChart = (indicator: Indicator) => (
    <TrendChart
      key={indicator.key}
      indicator={indicator}
      points={series[indicator.key] ?? []}
      origins={origins[indicator.key] ?? []}
      lowConfidence={lowConfidence}
      receivedUntil={receivedUntil}
      onboardUntil={onboardUntil}
      windowSeconds={Math.min(windowSeconds, onboardUntil)}
    />
  );

  const sections: ConsoleSection[] = [
    {
      key: "received",
      label: tr("Estado recibido", "Received status"),
      pictogram: uiPictogram("received"),
      essential: true,
      alerts: true,
      shared: true,
      // Por páginas de dos filas (decisión del usuario, 2026-11-16; `components/RowPages.tsx`). Con el
      // cuerpo ancho las filas son: el estado; los cinco peligros; las notas (2) con las proyecciones
      // (10); la comprobación de proyecciones. El estado y los peligros van en la primera página; las
      // proyecciones pueden traer derivas preocupantes y un aviso de riesgo no se esconde nunca (HMI
      // §2.7), así que van fijas: se ven en todas las páginas y, en la segunda, siguen junto a las notas.
      rowPages: true,
      panels: [
        <section data-ui="received-state" className="panel" aria-label={tr("Estado recibido", "Received status")}>
          <PanelTitle concept="received">{tr("Último estado recibido", "Last status received")}</PanelTitle>
          {received === null ? (
            <p>
              <MarkOf mark={MISSING_MARK}>
                {tr("Todavía no ha llegado ninguna lectura a Tierra.", "No reading has reached Earth yet.")}
              </MarkOf>
            </p>
          ) : (
            <ReceivedState received={received} />
          )}
        </section>,
        received !== null && <HazardCards status={received} />,
        // Lo único que sube (§5.38.1): una nota firmada, que llega a bordo un tiempo de luz después.
        personal(<GroundNotesComposer subject={status.subject} oneWayMinutes={oneWay} />),
        received !== null && pinned(<Predictions predictions={received.predictions} />),
        // La comprobación de lo ya proyectado, que mira atrás: a todo el ancho, en su propia fila.
        received !== null && <ForecastCheckPanel checks={received.forecast_checks} />,
        // «Ayuda urgente» de «Inicio» también en Tierra (decisión del usuario, 2026-11-16): fija, al pie.
        pinned(<UrgentHelp status={status} host />),
      ],
    },
    {
      key: "history",
      label: tr("Historial", "History"),
      pictogram: uiPictogram("history"),
      // Por páginas de dos filas (2026-11-16): las tres historias llegadas en su fila de tres y, cada
      // uno en la suya, la recuperación, el planificador, la línea base y el ciclo. Nada de esto es una
      // alerta: la recuperación es descriptiva y posvuelo.
      rowPages: true,
      panels: [
        <ImagingHistory subject={status.subject} oneWayMinutes={oneWay} />,
        <PainHistory subject={status.subject} oneWayMinutes={oneWay} />,
        // La carrera previa declarada a bordo, de solo lectura y con el corte del retardo (§5.36.4).
        // Va antes de la recuperación para que las tres historias llegadas sigan en su fila de tres.
        <MissionHistoryPanel subject={status.subject} oneWayMinutes={oneWay} />,
        <RecoveryPanel subject={status.subject} refreshKey={stateKey} />,
        // El planificador de a bordo (Marplanner), resumido para el apoyo a la salud mental y con el
        // corte del retardo (decisión del usuario, 2026-11-12; `planner/GroundPlannerPanel.tsx`).
        <GroundPlannerPanel oneWayMinutes={oneWay} />,
        // La base que Tierra puede conocer: la de las lecturas llegadas, hasta el corte del retardo.
        // La clave es la de la consola de tripulación, con lo recibido (`baselineRefreshKey`).
        received !== null && (
          <BaselineProfilePanel
            subject={status.subject}
            refreshKey={baselineRefreshKey(received)}
            until={cut ?? undefined}
          />
        ),
        // El sexo declarado y el ciclo, de solo lectura y con el corte del retardo (lote «ciclo»).
        received !== null && (
          <CycleSection
            subject={status.subject}
            refreshKey={baselineRefreshKey(received)}
            until={cut ?? undefined}
            ground
            phaseBaseline={received.cycle_phase?.reason ?? null}
          />
        ),
        // «Ayuda urgente» de «Inicio» también en Tierra (decisión del usuario, 2026-11-16): fija, al pie.
        pinned(<UrgentHelp status={status} host />),
      ],
    },
    {
      key: "trends",
      label: tr("Tendencias", "Trends"),
      pictogram: uiPictogram("trends"),
      // Por páginas de dos filas (2026-11-16): las dos rejillas de gráficas son una fila cada una, así
      // que caben en una página.
      rowPages: true,
      panels: [
        <section data-ui="trends" aria-label={tr("Tendencias", "Trends")}>
          <div className="summary mb-3" data-ui-view="">
            <PanelTitle concept="trends">{tr("Tendencias", "Trends")}</PanelTitle>
            <span className="secondary">{tr("Ventana:", "Window:")}</span>
            {WINDOWS.map((option) => (
              <button
                key={option.label}
                className="command"
                aria-pressed={windowSeconds === option.seconds}
                onClick={() => setWindowSeconds(option.seconds)}
              >
                {/* La seleccion no se marca solo con color (F.5.10 e) ni en gris, que significa
                    "no disponible" (tabla F.5-1): la ventana elegida lleva el anillo con punto de
                    «elegido» (`ring-dot`); el disco lleno es «medido». */}
                <Chosen chosen={windowSeconds === option.seconds}>{option.label}</Chosen>
              </button>
            ))}
            <span className="secondary">
              {tr("Arrastre para ampliar; doble clic para volver.", "Drag to zoom; double-click to reset.")}
            </span>
          </div>
          {error !== null && (
            <p className="panel error">
              <MarkOf mark={error.mark}>
                {tr("No se pudieron cargar las series:", "Could not load the series:")} {error.text}
              </MarkOf>
            </p>
          )}
          <div className="charts">{indicators.filter((item) => trendAbove(item.key)).map(trendChart)}</div>
        </section>,
        // Las demás gráficas, en su propia rejilla (2026-11-15). Llevan el mismo `data-ui` para vestirse
        // igual (`shell/ground-trends.css` acota la rejilla a `[data-ui="trends"] > .charts`) y la
        // misma ventana de arriba. Sin ninguna, no hay segunda rejilla.
        below.length > 0 && (
          <section data-ui="trends" aria-label={tr("Más tendencias", "More trends")}>
            <div className="charts">{below.map(trendChart)}</div>
          </section>
        ),
        // «Ayuda urgente» de «Inicio» también en Tierra (decisión del usuario, 2026-11-16): fija, al pie.
        pinned(<UrgentHelp status={status} host />),
      ],
    },
    {
      key: "habitat",
      label: tr("Hábitat", "Habitat"),
      pictogram: uiPictogram("habitat"),
      // Por páginas de dos filas (2026-11-16). Con el cuerpo ancho (`mission.css`) el nivel de misión
      // (3) y el hábitat (9, dos filas) empiezan en la primera fila y las preguntas de los gemelos caen
      // bajo el nivel: una página. Más estrecho, cada uno a todo el ancho y las preguntas, que son
      // análisis de fondo, pasan a la segunda; el nivel y el hábitat, que es el estado que Tierra
      // vigila, en la primera.
      rowPages: true,
      panels: [
        // El nivel de misión que Tierra puede conocer: el firmado hasta el corte; solo se mira.
        <MissionModePanel controls={false} until={receivedAt} />,
        // El habitat y la tripulacion que Tierra puede conocer: hasta el corte del retardo.
        <HabitatPanel
          missionStart={status.mission.start}
          refreshKey={stateKey}
          until={receivedAt}
          onboardUntil={reference}
        />,
        // Las cinco preguntas de los gemelos con lo que Tierra tiene: el corte del estado recibido
        // (el mismo que `receivedStatus`); se vuelven a pedir cuando cambia lo recibido o el día
        // (UTC) del corte, que es el «hoy» con que el registro cuenta sus días de espera. La clave
        // es la de la consola de tripulación, con el corte (`twinsRefreshKey`).
        received !== null && (
          <TwinQuestionsPanel
            subject={status.subject}
            until={cut}
            refreshKey={twinsRefreshKey(received, cut)}
          />
        ),
        // «Ayuda urgente» de «Inicio» también en Tierra (decisión del usuario, 2026-11-16): fija, al pie.
        pinned(<UrgentHelp status={status} host />),
      ],
    },
    {
      key: "framework",
      label: tr("Marco y fuentes", "Framework and sources"),
      pictogram: uiPictogram("nasaFramework"),
      // Por páginas de dos filas (2026-11-16; reparto en `shell/ground-framework-ledger.css`): el marco
      // de riesgos de la NASA (9, dos filas) con los perfiles y, debajo de ellos, el coste de medir; en
      // la segunda página, bancos y conjuntos, e instalaciones, personas y fuentes. Todo es dato fijo
      // del paquete: ninguna alerta ni estado clínico.
      rowPages: true,
      panels: [
        <FrameworkPanel />,
        // Los tres perfiles lado a lado (§5.36.7): dato fijo del paquete, sin el corte del retardo.
        <MissionProfilesPanel />,
        <MeasurementCostPanel indicators={catalog} />,
        <TestbedsPanel />,
        <DatasetsPanel />,
        <FacilitiesPanel />,
        <PeoplePanel />,
        <ContextSourcesPanel />,
        // «Ayuda urgente» de «Inicio» también en Tierra (decisión del usuario, 2026-11-16): fija, al pie.
        pinned(<UrgentHelp status={status} host />),
      ],
    },
    {
      key: "ledger",
      label: tr("Registro y documentos", "Ledger and documents"),
      pictogram: uiPictogram("signedLedger"),
      // Por páginas de dos filas (2026-11-16): la documentación con la auditoría del registro firmado
      // en la primera fila (la integridad es propiedad del sistema y un fallo suyo no se esconde
      // nunca: va en la primera página), lo que se comparte en la segunda fila y la copia de Polaris,
      // en la página siguiente.
      rowPages: true,
      panels: [
        <DocsPanel subject={status.subject} until={cut} />,
        audit !== null && <AuditPanel audit={audit} />,
        // La misma tabla que a bordo, sin corte: es del paquete, no un dato que viaje.
        <SharingPanel />,
        <PolarisPanel />,
        // «Ayuda urgente» de «Inicio» también en Tierra (decisión del usuario, 2026-11-16): fija, al pie.
        pinned(<UrgentHelp status={status} host />),
      ],
    },
    {
      key: "library",
      label: tr("Biblioteca", "Library"),
      pictogram: uiPictogram("countermeasureLibrary"),
      // La biblioteca es un dato fijo del paquete, no del estado: no lleva el corte del retardo.
      // Dos paneles lado a lado (7 + 5 columnas, `shell/library-env.css`): una fila, una página, y la
      // barra de páginas no se ve; por páginas como las demás (2026-11-16) para que la pestaña se
      // comporte igual si un día lleva más.
      rowPages: true,
      panels: [<LibraryPanel />, <GuidesPanel />, pinned(<UrgentHelp status={status} host />)],
    },
    // Una pestaña por entorno, tal y como los sirve el backend (`dashboard/Environments.tsx`); se eligen en la cabecera,
    // bajo «Entorno de la misión» (`headerGroup`), no en el carril.
    ...environmentSections(environments, undefined, status),
  ];

  return (
    <ConsoleTabs
      id="ground"
      label={tr("Secciones de la consola de Tierra", "Ground console sections")}
      sections={sections}
      counts={counts}
      header={<ActiveEnvironment profile={status.mission.profile} />}
      headerGroup={ENVIRONMENTS_GROUP}
      // El retardo encabeza la columna de los tableros, no la página: así el carril empieza donde el
      // de la tripulación y no se sale de la ventana (lote «responsivo», 2026-11-16).
      lead={
        <DelayBanner
          oneWay={oneWay}
          earthMet={earthMet}
          onboardMet={onboardMet}
          link={link}
          linkError={early?.error ?? null}
          sync={sync}
        />
      }
      stored={section}
      onChoose={setSection}
    />
  );
}

/**
 * La cabecera del retardo: las dos horas en fichas (§5.33.6), lo que Tierra tiene, caducado por
 * construcción (va un tiempo de luz por detrás: cian y cursiva), y por dónde va la nave. Sin
 * efemérides no hay corte que pintar: la ficha de Tierra dice por qué, con la marca de dato
 * ausente y la frase de siempre.
 *
 * El enlace declarado (§5.34.5, §5.35.9): la ficha lleva la frase corta del backend (`headline`,
 * la de la franja) y el párrafo de debajo la entera (`sentence`: que EMMA no mide el enlace y la
 * nota de quien lo declaró), para que la nota no alargue la ficha. Sin efemérides la ficha ya
 * lleva su motivo y el enlace va solo en el párrafo. Si no se pudo leer, se dice con la marca de
 * lo que fue (`requestOutcome`).
 */
export function DelayBanner({
  oneWay,
  earthMet,
  onboardMet,
  link,
  linkError,
  sync,
}: {
  oneWay: number | null;
  earthMet: string;
  onboardMet: string;
  link: ReturnType<typeof declaredLinkNotice>;
  linkError: RequestOutcome | null;
  /** El enlace simulado: su frase para Tierra va bajo las fichas, en cian si retiene el corte. */
  sync: LinkSync;
}) {
  const held = groundLinkMark(sync);
  return (
    <section data-ui="delay" className="panel delay-banner" aria-label={tr("Retardo aplicado", "Delay applied")}>
      <StatTiles label={tr("Retardo aplicado", "Delay applied")}>
        {oneWay === null && !sync.held ? (
          <StatTile
            concept="received"
            label={tr("Tierra tiene datos hasta", "Earth has data up to")}
            value={null}
            status={{
              mark: MISSING_MARK,
              word: tr(
                "Sin efemérides: no se puede aplicar el retardo. Se muestra todo lo que hay a bordo.",
                "No ephemeris: the delay cannot be applied. Everything on board is shown.",
              ),
            }}
          />
        ) : (
          <StatTile
            concept="received"
            label={tr("Tierra tiene datos hasta", "Earth has data up to")}
            value={earthMet}
            stale
            {...(link === null ? {} : { status: { mark: link.mark, word: link.headline } })}
          />
        )}
        <StatTile concept="missionDay" label={tr("A bordo ya van por", "On board they are already at")} value={onboardMet} />
      </StatTiles>
      {oneWay !== null && (
        <p>
          {/* El signo del retardo con Tierra (`lightTime`), el mismo de la franja, la ficha del
              resumen y las frases del tránsito de la ecografía y de una alerta (§5.33.12). */}
          <Mark pictogram={uiPictogram("lightTime")}>
            {tr("Retardo de ida", "One-way delay")} <span className="num">{formatMinutes(oneWay)}</span>
            {tr(
              ". Cualquier instrucción que salga ahora llegará a bordo dentro de otros",
              ". Any instruction sent now will reach the crew in another",
            )}{" "}
            <span className="num">{formatMinutes(oneWay)}</span>
            {tr(": la tripulación decide sola.", ": the crew decides on its own.")}
          </Mark>
        </p>
      )}
      {/* En su propia fila, debajo de las fichas (`.delay-link`): al lado les quitaba el ancho y
          la cifra de la ficha se salía de ella. */}
      {link !== null && (
        <p className="delay-link">
          <MarkOf mark={link.mark}>{link.sentence}</MarkOf>
        </p>
      )}
      {/* El enlace simulado (§5.47): hasta dónde tiene Tierra y cuánto le falta, con la frase del
          backend; en cian si el enlace caído retiene el corte (dato caducado, tabla F.5-1). */}
      <p className="delay-link">
        {held === null ? sync.ground_sentence : <MarkOf mark={held}>{sync.ground_sentence}</MarkOf>}{" "}
        <span className="secondary">{sync.known_only_here}</span>
      </p>
      {linkError !== null && (
        <p className="delay-link">
          <MarkOf mark={linkError.mark}>
            {tr("No se pudo leer el enlace declarado:", "Could not read the declared link:")} {linkError.text}
          </MarkOf>
        </p>
      )}
    </section>
  );
}

/**
 * El veredicto que Tierra puede conocer: el del backend con las lecturas llegadas.
 * El resumen y los motivos son los del backend, sin reescribir.
 */
function ReceivedState({ received }: { received: CrewStatus }) {
  return (
    <>
      <div className="summary mb-3">
        <LevelBadge level={received.overall_level} />
        <p>{received.summary}</p>
      </div>
      <div className="domains">
        {Object.entries(received.domains).map(([key, risk]) => (
          <div className="domain" data-level={risk.level} key={key}>
            <h3>
              <DomainName domain={key} label={domainLabel(key)} />
            </h3>
            <LevelBadge level={risk.level} />
            <span className="secondary num">
              {tr("puntuación", "score")} {formatNumber(risk.score, 1)}
            </span>
            {risk.drivers.length > 0 && (
              <ul className="drivers">
                {risk.drivers.map((driver) => (
                  <li key={driver}>{driver}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

/** Combinaciones distintas de tipo y entorno en una serie, para rotular la grafica. */
export function originsOf(resources: FhirObservation[]): SeriesOrigin[] {
  const seen = new Map<string, SeriesOrigin>();
  for (const resource of resources) {
    const origin = fhirProvenance(resource);
    seen.set(`${origin.type}:${origin.context ?? ""}`, origin);
  }
  return [...seen.values()];
}
