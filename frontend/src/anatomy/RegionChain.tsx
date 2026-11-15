import { useEffect, useState } from "react";

import { RecommendationList } from "../advisor/RecommendationList";
import { BoardDetail } from "../components/BoardDetail";
import { Chosen } from "../components/Chosen";
import { DomainName } from "../components/DomainName";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { ContextAnswer } from "../dashboard/AlertDetailView";
import { DensitometryBeside } from "../dashboard/DensitometryBeside";
import { EvidenceEntry } from "../evidence/EvidenceEntry";
import { EvidenceList } from "../evidence/EvidenceList";
import { emptyReason, populationMark } from "../evidence/sourceMarks";
import { originsOf } from "../ground/GroundConsole";
import { type Point, type SeriesOrigin, TrendChart } from "../ground/TrendChart";
import {
  type AnatomyRegionState,
  type AnatomyRisk,
  type AnatomyVariable,
  type CrewStatus,
  type Indicator,
  api,
} from "../lib/api";
import { displayUnit, formatMet, formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { LOADING_MARK, MISSING_MARK, prefixedPictogram, type RequestOutcome, requestOutcome } from "../lib/marks";
import { RECOMPUTED_PICTOGRAM } from "../dashboard/alertHistory";
import {
  NO_STATE,
  RESEARCH_LAYER_PICTOGRAM,
  domainPictogram,
  metOf,
  regionPictogram,
  seriesPoints,
  seriesWindowSeconds,
  stateStyle,
} from "./chain";
import { SkeletonFigure } from "./SkeletonFigure";

/**
 * El nivel que dio el backend, con la misma insignia que en el resto de la consola; sin nivel,
 * "sin datos" (cian, F.5-1), nunca nominal.
 *
 * `recomputed`: el nivel es el de un momento pasado, recalculado hoy. Va como la historia de
 * alertas (`dashboard/alertHistory.ts`): la palabra del nivel, sin su color ni su pictograma, con
 * el de lo recalculado en secundario. No es lo que el sistema enseñó entonces, y con la insignia
 * de un nivel vigente se leería como el estado de ahora.
 */
export function StateBadge({ level, recomputed = false }: { level: string | null; recomputed?: boolean }) {
  if (level !== null && recomputed) {
    return (
      <Mark pictogram={RECOMPUTED_PICTOGRAM} className="level secondary">
        <span className="c-text">{stateStyle(level).label}</span>
      </Mark>
    );
  }
  if (level !== null) return <LevelBadge level={level} />;
  return (
    <Mark pictogram={NO_STATE.pictogram} color={NO_STATE.color} className="level">
      {NO_STATE.label}
    </Mark>
  );
}

/**
 * El nivel de una región tal como se enseña en la lista, la silueta y la cadena: el de su
 * insignia o, en una región sin nivel propio (el hígado), la frase del backend que dice de qué
 * dominio es («El nivel es del dominio nutrición.»), con el dibujo de ese dominio y sin color: no
 * es un nivel, y con el cian de «sin datos» se leería como un dato que falta.
 */
export function RegionLevel({
  region,
  recomputed = false,
}: {
  region: Pick<AnatomyRegionState, "level" | "level_of" | "level_note">;
  recomputed?: boolean;
}) {
  if (region.level_of === null) return <StateBadge level={region.level} recomputed={recomputed} />;
  return (
    <Mark pictogram={domainPictogram(region.level_of)} className="level secondary">
      {region.level_note}
    </Mark>
  );
}

/**
 * La cadena de una region, entera y en el propio panel, en el orden de la base de conocimiento
 * (§11.1, que amplia la especificacion §10): estado → variables → evidencia → tendencia → riesgo
 * → contramedida, y al final lo de fuera del cuerpo (el «HABITAT TWIN» de la conversacion).
 *
 * Antes cada eslabon remitia a otro panel, y la evidencia y la tendencia no estaban. Todo lo que
 * se lee aqui lo calculo y lo redacto el backend (`app/anatomy.py`, con el mismo analisis que
 * `/status`): los motivos, la tendencia de cada variable, el alcance de cada referencia, el riesgo
 * (el de `/api/risks`), las contramedidas y el contexto externo (el mismo que el detalle de una
 * alerta). La interfaz ordena, nombra y da formato a las cifras; no decide ni redacta.
 *
 * `pastUntil`: la cadena es la de un momento pasado (recalculada, sin asiento). Ahi no se ofrece
 * adoptar nada —una contramedida se adopta sobre el estado de ahora— y la serie de cada variable
 * llega hasta ese instante.
 */
export function RegionChain({
  region,
  status,
  operator,
  following,
  onAdopt,
  pastUntil = null,
}: {
  region: AnatomyRegionState;
  status: CrewStatus;
  operator: string;
  /** Contramedidas con seguimiento abierto: no se vuelven a ofrecer para adoptar. */
  following: ReadonlySet<string>;
  onAdopt: (countermeasureId: string, by: string) => Promise<void>;
  /** El instante del estado si es el de un momento pasado; `null`, el de ahora. */
  pastUntil?: string | null;
}) {
  // La serie abierta al entrar es la de la primera variable que mueve el nivel: la tendencia
  // del hallazgo se ve sin pedirla. El panel monta este componente por region (`key`).
  const [charted, setCharted] = useState<string | null>(
    () => region.variables.find((item) => item.contributes)?.key ?? null,
  );
  // La banda inferida es la de ahora (`/status`): en un momento pasado no se enseña como suya.
  const inferred = region.key === "bones" && pastUntil === null ? status.inferred : [];
  const shown = region.variables.find((item) => item.key === charted) ?? null;
  const missionStart = status.mission.start;
  const met = (iso: string) => formatMet(metOf(missionStart, iso));

  return (
    <div className="region-detail">
      {/* El título lleva el dibujo del dominio de la región, el que la lista y la silueta ponen
          delante de su nombre. Cada región del backend tiene un dominio como mucho
          (`BodySilhouette.test.ts` lee `anatomy.py` y falla si una trajera dos); la que no tiene
          ninguno (el hígado) lleva el de su órgano (`regionPictogram`). */}
      <PanelTitle as="h3" pictogram={regionPictogram(region)}>
        {region.display}
      </PanelTitle>
      <p className="secondary">{region.note}</p>
      {/* La ficha en que se apoya la propia frase, si nombra algo que el riesgo del dominio no
          cubre (la vejiga y el riesgo de cálculos, §5.36.9). */}
      {region.note_refs.length > 0 && <EvidenceList items={region.note_refs} />}

      {/* Para qué sirve el órgano (el enunciado del reto: «its function and health status»), antes
          de su estado. La frase y sus fichas las da el backend; sin órgano que describir, la
          frase del backend que lo dice, sin color: no es un dato que falte. El backend da siempre
          una de las dos (`Region._check_function`); sin ninguna, la sección no sale vacía. */}
      {(region.function ?? region.function_note ?? null) !== null && (
        <section data-ui="region-function" aria-label={tr("Función", "Function")}>
          <PanelTitle as="h4" concept="body">
            {tr("Función", "Function")}
          </PanelTitle>
          {/* En la concha de la maqueta (muestra, 2026-11-08) la función, la evidencia y la
              investigación —lectura y citas— van tras su «Ver detalle», dentro de su propia sección:
              el título y la sección siguen a la vista, para que el asistente las encuentre (no busca
              bajo `hidden`). A la vista quedan el estado con sus niveles y motivos, las variables
              con sus cifras, la tendencia, el riesgo (que puede llevar la marca de lo que falta),
              las contramedidas con su mando y el contexto externo. */}
          <BoardDetail label={tr("función", "function")}>
            {region.function != null ? (
              <>
                <p>{region.function}</p>
                {region.function_refs.length > 0 && <EvidenceList items={region.function_refs} />}
              </>
            ) : (
              <p className="secondary">{region.function_note}</p>
            )}
          </BoardDetail>
        </section>
      )}

      <section data-ui="region-state" aria-label={tr("Estado", "State")}>
        <PanelTitle as="h4" concept="state">
          {tr("Estado", "State")}
        </PanelTitle>
        {region.data_note !== null && (
          <p>
            <Mark pictogram={NO_STATE.pictogram} color={NO_STATE.color}>
              {region.data_note}
            </Mark>
          </p>
        )}
        {region.level_note !== null && (
          <p>
            <RegionLevel region={region} />
          </p>
        )}
        {region.state.map((entry) => (
          <div key={entry.domain}>
            <p>
              <strong>
                <DomainName domain={entry.domain} />
              </strong>{" "}
              <StateBadge level={entry.level} recomputed={pastUntil !== null} />
            </p>
            {entry.drivers.length > 0 && (
              <ul className="drivers">
                {entry.drivers.map((driver) => (
                  <li key={driver}>{driver}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
        {inferred.map((item) => (
          <div key={item.key}>
            <p>
              {item.display} <ObservationTypeBadge type="inferred" />{" "}
              <span className="secondary">{tr("— ver «Estados inferidos»", "— see “Inferred states”")}</span>
            </p>
            {/* La densitometría medida en Tierra frente a esa banda: se ve también aquí, en el
                hueso, que es donde se mira la banda en el mapa del cuerpo. */}
            {item.densitometry !== undefined && <DensitometryBeside check={item.densitometry} />}
          </div>
        ))}
        {region.key === "bones" && <SkeletonFigure subject={status.subject} />}
      </section>

      <section data-ui="region-variables" aria-label="Variables">
        <PanelTitle as="h4" concept="indicator">
          Variables
        </PanelTitle>
        {region.variables.length > 0 && (
          <ul className="chain-variables">
            {region.variables.map((variable) => (
              <li key={variable.key}>
                <div className="chain-variable">
                  <strong>
                    <IndicatorName indicatorKey={variable.key} displayEs={variable.display_es} />
                  </strong>
                  {/* El ultimo valor, con su instante: una lectura antigua se ve como tal. */}
                  <span>
                    <span className="num">{formatNumber(variable.value, variable.decimals)}</span>{" "}
                    {displayUnit(variable.unit)}
                  </span>
                  <ObservationTypeBadge
                    type={variable.observation_type}
                    context={variable.evidence_context}
                  />
                  <span className="secondary num">
                    {formatMet(metOf(missionStart, variable.effective))}
                  </span>
                  {/* Nombra una decision del motor (`contributes`); no la toma. */}
                  {variable.contributes && <span className="chain-tag">{tr("cuenta en el nivel", "counts toward the level")}</span>}
                </div>
                {/* Por que cuenta, con las palabras del backend. La lectura que el motor cuenta
                    no tiene por que ser la ultima (un episodio de hace horas con el pulso ya
                    normal): va con su propio instante para que no se lea como el valor de arriba. */}
                {variable.deviation !== null && (
                  <p className="secondary">
                    {variable.deviation.description}{" "}
                    <span className="num">
                      ({formatMet(metOf(missionStart, variable.deviation.effective))})
                    </span>
                  </p>
                )}
                {variable.trend !== null && variable.trend.concerning && (
                  <p className="secondary">{variable.trend.description}</p>
                )}
              </li>
            ))}
          </ul>
        )}
        {region.unmeasured.length > 0 && (
          <Fold data-ui="region-unmeasured"
            mark={MISSING_MARK}
            label={
              <>
                {tr("Sin lectura", "No reading")} (<span className="num">{formatNumber(region.unmeasured.length)}</span>)
              </>
            }
          >
            <ul className="drivers">
              {region.unmeasured.map((item) => (
                <li key={item.key}>
                  <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
                </li>
              ))}
            </ul>
          </Fold>
        )}
      </section>

      <section data-ui="region-evidence" aria-label={tr("Evidencia", "Evidence")}>
        <PanelTitle as="h4" concept="evidence">
          {tr("Evidencia", "Evidence")}
        </PanelTitle>
        <BoardDetail label={tr("evidencia", "evidence")}>
          {region.evidence.map((block) => (
            <div key={block.domain}>
              <p className="secondary">
                <DomainName domain={block.domain} />: {block.amcl_alignment}
              </p>
              <EvidenceList items={block.items} />
            </div>
          ))}
          {/* La región sin nivel propio no tiene evidencia de dominio: lleva la fuente de qué
              analitos enseña, con su ficha del registro (para qué se cita va en `relevance`). */}
          {region.analytes_source !== null && <EvidenceList items={[region.analytes_source]} />}
        </BoardDetail>
      </section>

      {/* La capa aparte de la conversación de ideación (MEASURED / INFERRED / RESEARCH EVIDENCE,
          §5.37.16 y §5.39.16): lo observado en estudios con otras personas o con animales, no
          medido en este tripulante. Va en su propia sección, con el matraz de las fichas y la
          frase del backend delante; sin color: no es un estado ni un dato que falte. Cada ficha
          lleva encima su rótulo de población, del backend, con la marca de su clase (la persona,
          la huella o las dos; amarilla cuando no son solo personas, como en `SourceFacts`), y la
          misma entrada que toda cita de EMMA. Si la región dice dónde se hace esa investigación
          (el NSRL en el cerebro), va detrás de los estudios con su propia frase: es una
          instalación, no un estudio, y así no se cuenta entre ellos. */}
      {region.research !== null && (
        <section data-ui="region-research" aria-label={tr("Evidencia de investigación", "Research evidence")}>
          <PanelTitle as="h4" pictogram={RESEARCH_LAYER_PICTOGRAM}>
            {tr("Evidencia de investigación", "Research evidence")}
          </PanelTitle>
          <BoardDetail label={tr("investigación", "research")}>
            <p className="secondary">{region.research.note}</p>
            <ul className="evidence">
              {region.research.items.map((item, index) => (
                <li key={`${item.id}-${index}`}>
                  <p>
                    <MarkOf mark={populationMark(item.population, emptyReason(item, "population"))}>
                      {item.population_label}
                    </MarkOf>
                  </p>
                  <EvidenceEntry item={item} />
                </li>
              ))}
            </ul>
            {region.research.facility !== null && (
              <>
                <p className="secondary">{region.research.facility.note}</p>
                <EvidenceList items={[region.research.facility.item]} />
              </>
            )}
          </BoardDetail>
        </section>
      )}

      <section data-ui="region-trend" aria-label={tr("Tendencia", "Trend")}>
        <PanelTitle as="h4" concept="trends">
          {tr("Tendencia", "Trend")}
        </PanelTitle>
        {region.variables.length === 0 ? (
          <p>
            <Mark pictogram={NO_STATE.pictogram} color={NO_STATE.color}>
              {tr("Sin lecturas: no hay serie que mirar.", "No readings: there is no series to look at.")}
            </Mark>
          </p>
        ) : (
          <ul className="chain-trends">
            {region.variables.map((variable) => (
              <li key={variable.key}>
                {/* La frase es del backend (`trend.describe()`); sin ajuste, se dice que falta. */}
                {variable.trend !== null ? (
                  <span>{variable.trend.description}</span>
                ) : (
                  <span>
                    <IndicatorName indicatorKey={variable.key} displayEs={variable.display_es} />:{" "}
                    <Mark pictogram={NO_STATE.pictogram} color={NO_STATE.color}>
                      {tr("sin tendencia calculada", "no trend computed")}
                    </Mark>
                  </span>
                )}{" "}
                <button
                  className="command"
                  aria-pressed={variable.key === charted}
                  onClick={() => setCharted(variable.key === charted ? null : variable.key)}
                >
                  {/* La seleccion no se marca solo con color (F.5.10 e): la elegida lleva su pictograma. */}
                  <Chosen chosen={variable.key === charted}>{tr("Serie", "Series")}</Chosen>
                </button>
              </li>
            ))}
          </ul>
        )}
        {shown !== null && <VariableSeries variable={shown} status={status} until={pastUntil} />}
      </section>

      <section data-ui="region-risk" aria-label={tr("Riesgo", "Risk")}>
        <PanelTitle as="h4" concept="risks">
          {tr("Riesgo", "Risk")}
        </PanelTitle>
        {region.state.map((entry) => (
          <RiskStep key={entry.domain} risk={entry.risk} />
        ))}
        {/* Sin dominio no hay riesgo propio: el del dominio de su nivel, donde cuentan sus
            analitos, con la frase que lo dice (los mismos campos que `/api/risks`). */}
        {region.level_risk !== null && (
          <>
            <p>
              <RegionLevel region={region} />
            </p>
            <RiskStep risk={region.level_risk} />
          </>
        )}
      </section>

      <section data-ui="region-countermeasure" aria-label={tr("Contramedida", "Countermeasure")}>
        <PanelTitle as="h4" concept="recommendations">
          {tr("Contramedida", "Countermeasure")}
        </PanelTitle>
        {region.recommendations_note !== null && (
          <p className="secondary">{region.recommendations_note}</p>
        )}
        {/* En un momento pasado, las tarjetas con su forma y sin su color (`past`): lo pasado no
            pide atención, como el historial del hábitat. */}
        <RecommendationList
          items={region.recommendations}
          operator={operator}
          following={following}
          past={pastUntil !== null}
          {...(pastUntil === null ? { onAdopt } : {})}
        />
      </section>

      <section data-ui="region-external-context" aria-label={tr("Contexto externo", "External context")}>
        <PanelTitle as="h4" concept="habitat">
          {tr("Contexto externo", "External context")}
        </PanelTitle>
        {region.context === null ? (
          <p>
            <MarkOf mark={MISSING_MARK}>{tr("Sin contexto externo en la respuesta.", "No external context in the response.")}</MarkOf>
          </p>
        ) : (
          <ContextAnswer context={region.context} met={met} />
        )}
      </section>
    </div>
  );
}

/**
 * El paso RIESGO de un dominio (KB §11.1): el peligro RIDGE del que procede, la ficha del riesgo
 * (con su clase: no todas son del HRP) y lo que EMMA dice de su incertidumbre. Es un subconjunto
 * de `/api/risks` leído de las mismas fichas (`risk_entity.summary`), con sus textos tal cual. El
 * RIDGE se nombra como en la contramedida (`RecommendationCard`): su dibujo (`ridge-*`) delante de
 * «RIDGE: …», sin color, porque nombrar el eje no es avisar.
 */
function RiskStep({ risk }: { risk: AnatomyRisk }) {
  return (
    <ul className="drivers">
      <li>
        <Mark pictogram={prefixedPictogram("ridge", risk.ridge.category)}>RIDGE: {risk.ridge.display}</Mark>
        <span className="secondary"> · {risk.ridge.source.title}</span>
      </li>
      <li>
        <FieldLabel as="span" concept="evidence">
          {tr("Ficha del riesgo", "Risk record")}
        </FieldLabel>
        :{" "}
        {risk.hrp_risk === null ? (
          <MarkOf mark={MISSING_MARK}>{tr("Sin ficha del riesgo para este dominio.", "No risk record for this domain.")}</MarkOf>
        ) : (
          <>
            {risk.hrp_risk.title}
            <span className="secondary"> · {risk.hrp_risk.evidence_type_display}</span>
            {risk.hrp_risk.url !== null && <span className="secondary num url"> · {risk.hrp_risk.url}</span>}
          </>
        )}
      </li>
      <li className="secondary">{risk.uncertainty_statement}</li>
    </ul>
  );
}

interface Series {
  key: string;
  indicator: Indicator | null;
  points: Point[];
  origins: SeriesOrigin[];
}

/**
 * La serie de una variable, con la grafica de tendencia de la consola de Tierra en su modo de a
 * bordo: aqui no hay retardo que aplicar, todo lo dibujado esta en la nave. La ventana es la que
 * el motor uso para ajustar la tendencia. No se traza ninguna recta: el ajuste es del motor, y la
 * interfaz no calcula otro.
 */
function VariableSeries({
  variable,
  status,
  until,
}: {
  variable: AnatomyVariable;
  status: CrewStatus;
  /** Un momento pasado: la serie se corta ahí, como el estado (`TrendChart` no dibuja lo posterior). */
  until: string | null;
}) {
  const [series, setSeries] = useState<Series | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const { subject } = status;
  const missionStart = status.mission.start;

  useEffect(() => {
    let cancelled = false;
    setError(null);
    // En un momento pasado, las lecturas hasta él: las más recientes de todas podrían no llegar.
    Promise.all([api.indicators(), api.observations(variable.key, 5000, subject, until ?? undefined)])
      .then(([catalog, body]) => {
        if (cancelled) return;
        setSeries({
          key: variable.key,
          indicator: catalog.indicators.find((item) => item.key === variable.key) ?? null,
          points: seriesPoints(body.observations, missionStart),
          origins: originsOf(body.observations),
        });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(requestOutcome(reason));
      });
    return () => {
      cancelled = true;
    };
    // `effective` cambia cuando llega una lectura nueva de la variable: la serie se vuelve a pedir.
  }, [variable.key, variable.effective, subject, missionStart, until]);

  if (error !== null) {
    return (
      <p>
        <MarkOf mark={error.mark}>{tr("No se pudo cargar la serie:", "Could not load the series:")} {error.text}</MarkOf>
      </p>
    );
  }
  // Mientras llega la de la variable recien elegida no se ensena la de la anterior.
  if (series === null || series.key !== variable.key) {
    return (
      <p className="secondary">
        <MarkOf mark={LOADING_MARK}>{tr("Cargando la serie…", "Loading the series…")}</MarkOf>
      </p>
    );
  }
  if (series.indicator === null) {
    return (
      <p>
        <Mark pictogram={NO_STATE.pictogram} color={NO_STATE.color}>
          {tr("El catálogo no tiene la ficha de este indicador.", "The catalog has no record for this indicator.")}
        </Mark>
      </p>
    );
  }
  const onboardUntil = metOf(missionStart, until ?? status.data.reference_time);
  return (
    <TrendChart
      onboard
      indicator={series.indicator}
      points={series.points}
      origins={series.origins}
      receivedUntil={onboardUntil}
      onboardUntil={onboardUntil}
      windowSeconds={seriesWindowSeconds(
        variable,
        status.data.trend_window_days,
        missionStart,
        onboardUntil,
      )}
    />
  );
}
