import type {
  AlertCheckCost,
  AlertConcordance,
  AlertConfidence,
  AlertContext,
  AlertCostFact,
  AlertDetail,
  AlertFlowStep,
  AlertPersistence,
  AlertState,
  CrewStatus,
} from "../lib/api";
import { FieldLabel } from "../components/FieldLabel";
import { FlowSteps } from "../components/FlowSteps";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { cabinDecimals, changeArrow, concordanceStyle, costText, groupCostFacts, sourceStyle } from "../lib/alertContext";
import { displayUnit, formatMet, formatNumber, missionElapsedSeconds } from "../lib/format";
import { tr } from "../lib/i18n";
import { levelStyle } from "../lib/levels";
import { MISSING_MARK } from "../lib/marks";
import type { Token } from "../lib/palette";
import { DependsOn } from "./TimelinePieces";

type Met = (iso: string) => string;

/**
 * Que cambio alrededor del inicio de la alerta (especificacion §3 y §10). Cada frase es del
 * backend (`analysis/alert_context.py`): el rotulo de cada elemento —que dice que coincidir en
 * el tiempo no es ser la causa—, cuando cae respecto al inicio, de donde sale, y si cada fuente
 * tenia dato. Aqui solo se ponen en su sitio las cifras (por `format.ts`) y el cian de lo que
 * falta. El rotulo no se escribe en este fichero a proposito: si el backend deja de darlo, no
 * debe seguir saliendo en pantalla como si nada.
 *
 * Lo pinta tambien el modo anatomico (`anatomy/RegionChain.tsx`): el contexto externo de una
 * region sale del mismo constructor, y se lee igual.
 */
export function ContextAnswer({ context, met }: { context: AlertContext; met: Met }) {
  return (
    <>
      <p>{context.mission.statement}</p>
      <p>
        {context.summary} <span className="secondary">{context.note}</span>
      </p>
      {context.items.length > 0 && (
        <ul className="drivers">
          {context.items.map((item) => (
            <li key={`${item.kind}:${item.start}:${item.title}:${item.detail ?? ""}`}>
              <strong>{item.title}</strong>
              {item.detail !== null && <>: {item.detail}</>}
              {item.value !== null && item.unit !== null && (
                <>
                  {" · "}
                  {item.value_label}{" "}
                  <span className="num">{formatNumber(item.value, cabinDecimals(item.value))}</span>{" "}
                  {displayUnit(item.unit)}
                </>
              )}
              <span className="secondary">
                {" · "}
                {item.timing} · <span className="num">{met(item.start)}</span>
                {item.end !== item.start && (
                  <>
                    {" – "}
                    <span className="num">{met(item.end)}</span>
                  </>
                )}
                {" · "}
                {item.source}
              </span>{" "}
              <em>{item.label}</em>
            </li>
          ))}
        </ul>
      )}
      <ul className="drivers">
        {context.sources.map((source) => {
          const style = sourceStyle(source.status);
          return (
            <li key={source.kind}>
              <Mark pictogram={style.pictogram} color={style.color}>
                {source.display}: {source.status_display}
              </Mark>{" "}
              <span className="secondary">— {source.note}</span>
            </li>
          );
        })}
      </ul>
      <p className="secondary">
        <span className="num">{met(context.window_start)}</span>
        {" – "}
        <span className="num">{met(context.window_end)}</span> · {context.window_basis}
      </p>
    </>
  );
}

/**
 * Concordancia entre señales del dominio (especificacion §6): cuantos indicadores acompañan al
 * que inicio la alerta. Describe, no puntua: por eso no lleva color de nivel. Los que no tienen
 * dato van aparte, en cian, para no enterrar a los que si lo tienen.
 */
function ConcordanceAnswer({ concordance }: { concordance: AlertConcordance }) {
  const withData = concordance.indicators.filter((item) => item.state !== "no_data");
  const missing = concordance.indicators.filter((item) => item.state === "no_data");
  const absent = concordanceStyle("no_data");
  return (
    <>
      <p>{concordance.statement}</p>
      {withData.length > 0 && (
        <ul className="drivers">
          {withData.map((item) => (
            <li key={item.key}>
              <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />: {item.state_display}
              {item.role_display !== null && <strong> · {item.role_display}</strong>}
              {item.description !== null && <span className="secondary"> — {item.description}</span>}
            </li>
          ))}
        </ul>
      )}
      {missing.length > 0 && (
        <p>
          <Mark pictogram={absent.pictogram} color={absent.color}>
            {missing[0]?.state_display}: {missing.map((item) => item.display_es).join(" · ")}
          </Mark>
        </p>
      )}
      <p className="secondary">
        {concordance.trigger_basis} {concordance.basis}
      </p>
    </>
  );
}

/**
 * Persistencia (especificacion §6) y confianza (§3) de la alerta, tal cual las da el backend
 * (`analysis/alert_support.py`): frases y recuentos. Describen, no puntuan: sin color de nivel.
 * No hay una cifra unica de confianza y aqui no se calcula ninguna.
 */
function PersistenceAnswer({ persistence }: { persistence: AlertPersistence }) {
  return (
    <>
      <p>{persistence.statement}</p>
      {persistence.indicators.length > 0 && (
        <ul className="drivers">
          {persistence.indicators.map((item) => (
            <li key={item.key}>{item.statement}</li>
          ))}
        </ul>
      )}
      <p className="secondary">{persistence.basis}</p>
    </>
  );
}

function ConfidenceAnswer({ confidence }: { confidence: AlertConfidence }) {
  return (
    <>
      <p>{confidence.statement}</p>
      {confidence.indicators.length > 0 && (
        <ul className="drivers">
          {confidence.indicators.map((item) => (
            <li key={item.key}>{item.statement}</li>
          ))}
        </ul>
      )}
      {confidence.trend_note !== null && <p>{confidence.trend_note}</p>}
      <p className="secondary">
        {confidence.note} {confidence.basis}
      </p>
    </>
  );
}

/**
 * Un dato del coste de una comprobacion (§5.34.6): rotulo y valor, los dos del backend
 * (`analysis/alert_support.py`, que lee `ingest/cost.py`). Lo que falta —«sin clasificar», «sin
 * cifra con fuente»— va en cian con el anillo punteado (tabla F.5-1: dato ausente), porque es lo
 * contrario de un dato; lo decide `missing`, no la palabra. Un tiempo lleva detrás de dónde sale
 * (`basis`), como en la tarjeta de la recomendación.
 */
function CostFact({ fact }: { fact: AlertCostFact }) {
  return (
    <>
      {fact.label}: {fact.missing ? <MarkOf mark={MISSING_MARK}>{fact.display}</MarkOf> : costText(fact)}
      {fact.basis !== null && fact.basis !== undefined && <span className="secondary"> ({fact.basis})</span>}
    </>
  );
}

/**
 * Que cuesta una comprobacion: el tiempo de la accion y, por cada indicador que repite, su clase
 * de medida, el tiempo de medirlo, donde se procesa, cuando llega el resultado y si gasta
 * consumibles, y desde la decimosexta ronda masa, volumen, potencia, calibracion y formacion del
 * operador (lo que falta, junto por su palabra). Plegado: es el detalle de una linea que ya se lee
 * sin el. No suma ni ordena nada, y las comprobaciones salen en el orden del recomendador.
 */
function CheckCost({ cost }: { cost: AlertCheckCost }) {
  return (
    <Fold data-ui="alert-check-cost" concept="measurementCost" label={tr("Qué cuesta comprobarlo", "What checking it costs")}>
      <ul className="drivers">
        {cost.action !== null && (
          <li>
            <CostFact fact={cost.action} />
          </li>
        )}
        {cost.indicators.map((row) => {
          // Lo que falta, junto por su palabra (`groupCostFacts`): con las dimensiones de la base
          // de conocimiento §9, casi todo es «sin clasificar», y una a una tapaban lo que se sabe.
          const { shown, missing } = groupCostFacts(row.facts);
          return (
            <li key={row.key}>
              <IndicatorName indicatorKey={row.key} displayEs={row.display_es} />
              {shown.length > 0 && ": "}
              {shown.map((fact, index) => (
                <span key={fact.key}>
                  {index > 0 && " · "}
                  <CostFact fact={fact} />
                </span>
              ))}
              {missing.map((group) => (
                <div key={group.display}>
                  <MarkOf mark={MISSING_MARK}>{group.display}</MarkOf>:{" "}
                  <span className="secondary">{group.labels.join(" · ")}</span>
                </div>
              ))}
            </li>
          );
        })}
        {cost.statement !== null && <li className="secondary">{cost.statement}</li>}
      </ul>
    </Fold>
  );
}

/**
 * Los pasos del flujo de la base de conocimiento (§10) por los que va la alerta: nombre, estado y
 * frase del backend (`analysis/alert_flow.py`). La marca de cada estado es la de los pasos de una
 * hipotesis (`habitat/flow.ts`): mismos estados, mismo dibujo y color, y uno desconocido sin
 * significado. Aqui no se deduce ningun estado.
 */
function AlertFlow({ steps, basis }: { steps: AlertFlowStep[]; basis: string }) {
  return (
    <>
      <FlowSteps steps={steps} />
      <p className="secondary">{basis}</p>
    </>
  );
}

/**
 * Un cambio o una tendencia de «que cambio», con una flecha arriba o abajo segun el sentido
 * ESTRUCTURADO que da el backend (`direction`). Solo la flecha lleva el color del nivel de la
 * alerta; la frase sigue en el color del texto (`c-text`), como junto a una insignia. En amarillo
 * y rojo es la flecha de F.4.3.1 d («a yellow or red up or down arrow ... outside of upper or lower
 * thresholds»); en azul, el nivel de aviso de EMMA, que la clausula no nombra. Sin sentido
 * conocido no hay flecha ni color: la frase va tal cual, sin deducir nada de su texto.
 */
function Change({ direction, color, children }: { direction: string | undefined; color: Token; children: string }) {
  const arrow = changeArrow(direction);
  if (arrow === null) return <Mark pictogram={null}>{children}</Mark>;
  return (
    <Mark pictogram={arrow} color={color}>
      <span className="c-text">{children}</span>
    </Mark>
  );
}

/**
 * Las preguntas del detalle de alerta (especificacion del equipo §10): que cambio, desde
 * cuando, frente a que base, que contexto cambio, por que puede importar, que comprobar y que
 * evidencia lo respalda, mas la concordancia, la persistencia (§6) y la confianza (§3). Cada
 * respuesta sale del backend, compuesta: aqui no se filtra, ni se deduplica, ni se elige.
 * `level` es el de la alerta, y solo sirve para el color de las flechas de «que cambio».
 */
export function AlertDetailView({
  detail,
  level,
  status,
  alertTime,
}: {
  detail: AlertDetail;
  level: string;
  status: CrewStatus;
  alertTime?: AlertState["time_to_action"];
}) {
  const met: Met = (iso) => formatMet(missionElapsedSeconds(status.mission.start, new Date(iso)));
  const color = levelStyle(level).color;
  // Lo que cambió y lo que deriva, una vez cada clave: de aquí salen las claves y sus nombres.
  const dependsNames = Object.fromEntries([...detail.changed, ...detail.trends].map((item) => [item.key, item.display_es]));
  // Que el coste no reordena las comprobaciones, y que es «sin clasificar»: frases del backend.
  const checkNotes = [detail.checks.order_note, detail.checks.unclassified_note].filter(
    (text): text is string => typeof text === "string" && text !== "",
  );

  return (
    <Fold data-ui="alert-detail" concept="detail" className="alert-detail" label={tr("Detalle: qué cambió, desde cuándo y por qué", "Detail: what changed, since when and why")}>
      <dl className="kv">
        <FieldLabel as="dt" concept="change">
          {tr("Qué cambió", "What changed")}
        </FieldLabel>
        <dd>
          {detail.changed.length === 0 && detail.trends.length === 0 ? (
            <span className="secondary">{tr("sin lecturas fuera de lo esperado en la ventana", "no readings outside the expected in the window")}</span>
          ) : (
            <ul className="drivers">
              {detail.changed.map((item) => (
                <li key={item.key}>
                  <Change direction={item.direction} color={color}>
                    {item.description}
                  </Change>
                  {/* El tipo de la lectura (§5.37.1): solo lo medido decide, y se ve. */}
                  {item.observation_type !== undefined && item.observation_type !== null && (
                    <>
                      {" "}
                      <ObservationTypeBadge type={item.observation_type} />
                    </>
                  )}
                </li>
              ))}
              {detail.trends.map((item) => (
                <li key={`t:${item.key}`}>
                  <Change direction={item.direction} color={color}>
                    {item.description}
                  </Change>
                </li>
              ))}
            </ul>
          )}
          {/* De qué tipo son las lecturas que la causaron y cuántas no decidieron: frases del
              backend. Sin cambios ni lecturas apartadas, la línea de arriba ya lo dice. */}
          {detail.readings !== undefined &&
            (detail.changed.length > 0 || Object.keys(detail.readings.set_aside).length > 0) && (
              <p className="secondary">
                {detail.readings.statement} {detail.readings.rule}
              </p>
            )}
        </dd>
        <FieldLabel as="dt" concept="time">
          {tr("Desde cuándo", "Since when")}
        </FieldLabel>
        <dd>
          {detail.onset !== null ? (
            <>
              <span className="num">{met(detail.onset)}</span>{" "}
              <span className="secondary">— {detail.onset_basis}</span>
            </>
          ) : (
            <span className="secondary">{detail.onset_basis}</span>
          )}
        </dd>
        <FieldLabel as="dt" concept="baseline">
          {tr("Frente a qué base", "Against which baseline")}
        </FieldLabel>
        <dd>
          {detail.changed.length === 0 ? (
            <span className="secondary">—</span>
          ) : (
            <ul className="drivers">
              {detail.changed.map((item) => (
                <li key={item.key}>
                  <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />: {item.compared_with}
                  {/* La mediana solo si se comparo con su base: con el rango poblacional
                      no fue la referencia, y mostrarla diria lo contrario. */}
                  {item.baseline_median !== null && item.compared_with === "línea base personal" && (
                    <>
                      {tr(", mediana ", ", median ")}<span className="num">{formatNumber(item.baseline_median, 1)}</span>{" "}
                      {displayUnit(item.unit)}{tr(" en", " in")}{" "}
                      <span className="num">{formatNumber(item.baseline_samples)}</span>{tr(" lecturas", " readings")}
                    </>
                  )}
                  {/* Cuánto cambió frente a esa mediana, o por qué no se da: frase del backend. */}
                  {item.relative_change !== undefined && (
                    <span className={item.relative_change.applies ? undefined : "secondary"}>
                      {" · "}
                      {item.relative_change.statement}
                    </span>
                  )}
                  {/* Qué corte de su propia base cruzó (percentil y valor), o por qué no hay:
                      frase del backend, con el mismo corte con que el motor la graduó. */}
                  {item.personal_cut !== undefined && (
                    <span className={item.personal_cut.applies ? undefined : "secondary"}>
                      {" · "}
                      {item.personal_cut.statement}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </dd>
        <FieldLabel as="dt" concept="compare">
          {tr("Concordancia entre señales", "Agreement between signals")}
        </FieldLabel>
        <dd>
          <ConcordanceAnswer concordance={detail.concordance} />
        </dd>
        <FieldLabel as="dt" concept="routines">
          {tr("Persistencia", "Persistence")}
        </FieldLabel>
        <dd>
          <PersistenceAnswer persistence={detail.persistence} />
        </dd>
        <FieldLabel as="dt" concept="confidence">
          {tr("Confianza de las lecturas", "Confidence in the readings")}
        </FieldLabel>
        <dd>
          <ConfidenceAnswer confidence={detail.confidence} />
        </dd>
        <FieldLabel as="dt" concept="during">
          {tr("Tiempo hasta la acción", "Time to action")}
        </FieldLabel>
        <dd>
          {alertTime === undefined || alertTime === null ? (
            <span className="secondary">—</span>
          ) : (
            <>
              {tr("reconocida", "acknowledged")}{" "}
              {alertTime.acknowledged_after_minutes === null ? (
                <span className="secondary">{tr("pendiente", "pending")}</span>
              ) : (
                <>
                  {tr("a los ", "after ")}<span className="num">{formatNumber(alertTime.acknowledged_after_minutes)}</span> min
                </>
              )}{" "}
              {tr("· contramedida", "· countermeasure")}{" "}
              {alertTime.countermeasure_after_minutes === null ? (
                <span className="secondary">{tr("pendiente", "pending")}</span>
              ) : (
                <>
                  {tr("a los ", "after ")}<span className="num">{formatNumber(alertTime.countermeasure_after_minutes)}</span>{" "}
                  min
                </>
              )}
              <p className="secondary">{alertTime.basis}</p>
            </>
          )}
        </dd>
        <FieldLabel as="dt" concept="history">
          {tr("Qué contexto cambió", "What context changed")}
        </FieldLabel>
        <dd>
          {detail.context === undefined ? (
            <span className="secondary">—</span>
          ) : (
            <ContextAnswer context={detail.context} met={met} />
          )}
        </dd>
        <FieldLabel as="dt" concept="reason">
          {tr("Por qué puede importar", "Why it may matter")}
        </FieldLabel>
        <dd>
          {detail.relevance}
          {detail.relevance_evidence !== null && (
            <span className="secondary"> {detail.relevance_evidence.text}</span>
          )}
        </dd>
        <FieldLabel as="dt" concept="followUp">
          {tr("Qué comprobar", "What to check")}
        </FieldLabel>
        <dd>
          {detail.checks.items.length === 0 ? (
            <span className="secondary">{detail.checks.statement}</span>
          ) : (
            <ul className="drivers">
              {detail.checks.items.map((item) => (
                <li key={item.id ?? item.title}>
                  {item.title}
                  {item.basis_display !== null && (
                    <span className="secondary"> — {item.basis_display}</span>
                  )}
                  {item.cost !== undefined && <CheckCost cost={item.cost} />}
                </li>
              ))}
            </ul>
          )}
          {checkNotes.length > 0 && <p className="secondary">{checkNotes.join(" ")}</p>}
        </dd>
        <FieldLabel as="dt" concept="flowSteps">
          {tr("Por qué paso va", "Which step it is at")}
        </FieldLabel>
        <dd>
          {detail.flow === undefined ? (
            <span className="secondary">—</span>
          ) : (
            <AlertFlow steps={detail.flow.steps} basis={detail.flow.basis} />
          )}
        </dd>
        <FieldLabel as="dt" pictogram="dot-tree">
          {tr("Qué depende de estos datos", "What depends on these data")}
        </FieldLabel>
        <dd>
          <DependsOn names={dependsNames} keys={Object.keys(dependsNames)} />
        </dd>
        <FieldLabel as="dt" concept="evidence">
          {tr("Evidencia", "Evidence")}
        </FieldLabel>
        <dd>
          {detail.evidence.items.length === 0 ? (
            <span className="secondary">{detail.evidence.statement}</span>
          ) : (
            <ul className="evidence">
              {detail.evidence.items.map((item) => (
                <li key={item.id}>
                  {item.url ? (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {item.title}
                    </a>
                  ) : (
                    item.title
                  )}{" "}
                  <span className="secondary">
                    — {item.source} · {item.grade.label} · {item.role_display}
                    {item.demo_display !== null && <> · {item.demo_display}</>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </dd>
      </dl>
    </Fold>
  );
}
