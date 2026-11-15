import { type ReactNode, useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import { Loading, Unavailable } from "../components/Unavailable";
import {
  type BaselineIndicator,
  type BaselinePersonalData,
  type BaselineProfile,
  type BaselineState,
  type FlightDirection,
  baselineApi,
} from "../lib/api";
import { displayUnit, formatNumber, formatSourceDate } from "../lib/format";
import { type RequestOutcome, UNAVAILABLE_MARK, requestOutcome } from "../lib/marks";
import { contextLabel, contextPictogram, typeStyle } from "../lib/provenance";
import { tr } from "../lib/i18n";

/**
 * Contra qué se compara cada indicador (especificación §3 `baseline_profile`, §10 «¿respecto a
 * qué baseline?»). La base solo se veía dentro de una alerta; sin alerta no había forma de saber
 * si un indicador se juzgaba contra la normalidad de esta persona o, mientras aprende, solo contra
 * un límite de peligro. Esto lo enseña por indicador y estado (reposo, sueño, actividad), con la
 * mediana y la dispersión que usó el motor, cuántas lecturas tenía y de dónde salieron. Desde la
 * decimoséptima ronda (§5.37.2), también de qué entorno y de qué tipo son esas lecturas y dónde
 * corta la base: los percentiles con que el motor gradúa, como cifra en la unidad del indicador.
 *
 * Consola de tripulación, «poco y relevante»: a la vista, el recuento y cómo es la base; la tabla,
 * plegada. Las frases y las palabras con contenido (estado, «establecida», respaldo, límites,
 * procedencia) son del backend (`app/analysis/baseline_profile.py`); aquí solo se ponen las cifras
 * con `lib/format.ts` y los rótulos de la tabla («de», «lecturas», «dispersión»). Sin
 * color: una base en aprendizaje no es un aviso. Los descriptivos, que no tienen base, llevan la
 * marca de «no disponible» (gris, tabla F.5-1) con su motivo.
 *
 * Plegado aparte, lo que se observó en otros vuelos para cada indicador (sube, baja, sin cambio,
 * discutido o sin fuente), con la frase leída y su fuente: contexto, no lo esperado en esta persona.
 *
 * El perfil no cambia el estado, así que el estado no avisa de uno nuevo: se vuelve a leer con
 * cada estado (`refreshKey`) y al cambiar de tripulante. En Tierra, con `until`, el de lo recibido.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta (`BoardOnly`), encima
 * del método va la tira con los tres parámetros del motor que el perfil ya trae como cifra
 * (`window_days`, `lag_hours`, `min_samples`): los días de la ventana, cuánto antes de la lectura
 * termina y con cuántas lecturas se da por hecha una base. Son las mismas cifras que la frase del
 * método escribe en prosa; aquí solo el rótulo y la unidad, con `lib/format.ts`. Caducada, la tira
 * entera en cursiva, como la frase de arriba (no solo las cifras). Es una lista de definiciones sin
 * rol propio: un `role` en el `dl` le quitaría a sus `dt`/`dd` el padre que esperan.
 *
 * Una pantalla por sección (lote «muestra», 2026-11-08): en la concha de la maqueta, a la vista
 * quedan la frase del recuento, el motivo si la lectura falló, la tira de parámetros y los
 * indicadores sin base con su marca de «no disponible» (eso no se pliega). Las tres frases del
 * método y los plegables (por indicador, otros vuelos, sexo y edad) van juntos detrás de «Ver
 * detalle». En la clásica, todo en su orden de antes.
 */
export function BaselineProfilePanel({
  subject,
  refreshKey,
  until,
}: {
  subject: string;
  refreshKey: string;
  until?: Date | undefined;
}) {
  const [data, setData] = useState<BaselineProfile | null>(null);
  const [unavailable, setUnavailable] = useState<RequestOutcome | null>(null);
  const cut = until?.toISOString();

  // Otro tripulante: lo pintado era del anterior.
  useEffect(() => {
    setData(null);
    setUnavailable(null);
  }, [subject]);

  useEffect(() => {
    let alive = true;
    baselineApi
      .profile(subject, cut === undefined ? undefined : new Date(cut))
      .then((body) => {
        if (!alive) return;
        setData(body);
        setUnavailable(null);
      })
      .catch((reason: unknown) => {
        if (alive) setUnavailable(requestOutcome(reason));
      });
    return () => {
      alive = false;
    };
  }, [subject, refreshKey, cut]);

  return <BaselineProfileView data={data} unavailable={unavailable} />;
}

/** Solo pinta. Separado de la carga para poder probar lo que se lee en pantalla. */
export function BaselineProfileView({
  data,
  unavailable,
}: {
  data: BaselineProfile | null;
  unavailable: RequestOutcome | null;
}) {
  if (data === null) {
    return (
      <section data-ui="baseline-profile" className="panel" aria-label={tr("Línea base personal", "Personal baseline")}>
        <PanelTitle concept="baseline">{tr("Línea base personal", "Personal baseline")}</PanelTitle>
        {unavailable !== null ? <Unavailable outcome={unavailable} /> : <Loading />}
      </section>
    );
  }
  return <BaselineProfileBody data={data} unavailable={unavailable} />;
}

function BaselineProfileBody({ data, unavailable }: { data: BaselineProfile; unavailable: RequestOutcome | null }) {
  // Si la última lectura falló, lo pintado es lo de antes: caducado (cursiva) y con el motivo.
  const stale = unavailable !== null;
  const board = useLook() === "reference";
  const descriptive = data.descriptive.length > 0 && (
    <ul>
      {data.descriptive.map((item) => (
        <li key={item.key}>
          <MarkOf mark={UNAVAILABLE_MARK}>{item.display_es}</MarkOf>{" "}
          <span className="secondary">{item.reason}</span>
        </li>
      ))}
    </ul>
  );
  const folds = (
    <>
      <BaselineFolds data={data} stale={stale} />
      {board && <PersonalDataFold block={data.personal_data} />}
    </>
  );
  const method = (
    <>
      <p className="secondary">{data.method}</p>
      <p className="secondary">{data.cuts_method}</p>
      <p className="secondary">{data.fixed_note}</p>
    </>
  );
  return (
    <section data-ui="baseline-profile" className="panel" aria-label={tr("Línea base personal", "Personal baseline")} data-baseline-profile>
      <PanelTitle concept="baseline">{tr("Línea base personal", "Personal baseline")}</PanelTitle>
      <p className={stale ? "stale" : undefined}>{data.statement}</p>
      {unavailable !== null && <Unavailable outcome={unavailable} />}
      <BoardOnly>
        <dl className={stale ? "board-strip stale" : "board-strip"}>
          <div>
            <FieldLabel as="dt" concept="time">
              {tr("Ventana", "Window")}
            </FieldLabel>
            <dd>
              <span className="num">{formatNumber(data.window_days)}</span> d
            </dd>
          </div>
          <div>
            <FieldLabel as="dt" concept="during">
              {tr("Termina", "Ends")}
            </FieldLabel>
            <dd>
              <span className="num">{formatNumber(data.lag_hours)}</span>{" "}
              {tr("h antes de la lectura", "h before the reading")}
            </dd>
          </div>
          <div>
            <FieldLabel as="dt" concept="value">
              {tr("Mínimo de lecturas", "Minimum readings")}
            </FieldLabel>
            <dd>
              <span className="num">{formatNumber(data.min_samples)}</span>
            </dd>
          </div>
        </dl>
      </BoardOnly>
      {board ? descriptive : method}
      {board ? <BoardDetail label={tr("método y tablas de la base", "method and baseline tables")}>{method}{folds}</BoardDetail> : folds}
      {!board && descriptive}
      {!board && <PersonalDataFold block={data.personal_data} />}
    </section>
  );
}

/** Los plegables de la línea base, en su orden: por indicador y estado, y otros vuelos. */
function BaselineFolds({ data, stale }: { data: BaselineProfile; stale: boolean }) {
  return (
    <>
      {data.indicators.length > 0 && (
        <Fold data-ui="baseline-by-indicator"
          concept="byIndicator"
          label={
            <>
              {tr("Por indicador y estado", "By indicator and state")} (<span className="num">{formatNumber(data.indicators.length)}</span>)
            </>
          }
        >
          <div className="quality-table">
            <table className="ledger">
              <thead>
                <tr>
                  <Th concept="indicator">{tr("Indicador", "Indicator")}</Th>
                  <Th concept="state">{tr("Estado", "State")}</Th>
                  <Th concept="baseline">{tr("Base", "Baseline")}</Th>
                  <Th concept="value">{tr("Mediana y dispersión", "Median and spread")}</Th>
                  <Th concept="limits">{tr("Respaldo", "Backing")}</Th>
                </tr>
              </thead>
              <tbody>
                {data.indicators.flatMap((item) =>
                  item.states.length === 0
                    ? [
                        // Ninguna lectura atribuible a un estado: el indicador sale igual, con el
                        // motivo del backend, para que la cuenta del rótulo no pierda una fila.
                        <tr key={item.key} data-baseline-state={`${item.key}|`}>
                          <td>
                            <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
                          </td>
                          <td colSpan={4} className="secondary">
                            {item.unattributed_display}
                          </td>
                        </tr>,
                      ]
                    : item.states.map((row, index) => (
                        <StateRow
                          key={`${item.key}|${row.context}`}
                          item={item}
                          row={row}
                          first={index === 0}
                          stale={stale}
                        />
                      )),
                )}
              </tbody>
            </table>
          </div>
          <Fold data-ui="baseline-catalog-range" concept="range" label={tr("Rango del catálogo, por indicador", "Catalog range, by indicator")}>
            <ul>
              {data.indicators.map((item) => (
                <li key={item.key}>
                  <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />{" "}
                  <span className="secondary">{item.reference.text}</span>
                </li>
              ))}
            </ul>
          </Fold>
        </Fold>
      )}
      {data.flight_direction.indicators.length > 0 && <FlightDirectionFold block={data.flight_direction} />}
    </>
  );
}

/**
 * Sexo y edad (§5.36.19, revisado el 2026-11-14): el sexo se declara aparte (`crew-sex`) y solo
 * decide si se ofrece el seguimiento del ciclo; la edad no tiene campo. El rótulo se queda en «Sexo
 * y edad» porque nombra el tema, no afirma nada de él: lo que se guarda y para qué lo dicen las
 * frases. Plegado, con el signo de la identidad: no es una lectura ni un aviso, y va sin color.
 * Las frases y la ficha son del backend; aquí solo el rótulo del plegable.
 */
function PersonalDataFold({ block }: { block: BaselinePersonalData }) {
  return (
    <Fold data-ui="baseline-personal-data" concept="identity" label={tr("Sexo y edad", "Sex and age")} data-personal-data>
      <p>{block.statement}</p>
      <p>{block.cycle}</p>
      <p>{block.radiation}</p>
      <p className="secondary">{block.elsewhere}</p>
      <p className="secondary">{block.privacy}</p>
      <p className="secondary">
        {block.source.title}
        {block.source.url !== null && <span className="num url"> · {block.source.url}</span>}
      </p>
    </Fold>
  );
}

/**
 * Lo que se observó en otros vuelos (`app/evidence/flight_direction.py`), solo aquí, junto a la
 * base, y no en la alerta (decisión del usuario, 2026-10-22). Plegado: es contexto leído, no lo
 * que se juzga. Sin color: «sube» o «discutido» no son un aviso, y «sin fuente» no es «no
 * disponible». Las palabras del sentido, las frases y su fuente son del backend; aquí solo el
 * rótulo del plegable y la cuenta.
 */
function FlightDirectionFold({ block }: { block: FlightDirection }) {
  return (
    <Fold data-ui="baseline-other-flights" concept="source" label={tr("En otros vuelos, por indicador", "In other flights, by indicator")} data-flight-direction>
      <p className="secondary">{block.note}</p>
      <p>{block.statement}</p>
      <ul>
        {block.indicators.map((item) => (
          <li key={item.key} data-flight-direction-indicator={item.key}>
            <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />: {item.direction_display}
            <div className="secondary">{item.text}</div>
            {item.scope !== null && <div className="secondary">{item.scope}</div>}
            {item.searched_display !== null && <div className="secondary">{item.searched_display}</div>}
            {item.searched_sources.map((source, index) => {
              const readOn = item.searched_read_on[index];
              const extent = item.searched_extent_text[index];
              return (
                <div key={source} className="secondary">
                  {source}
                  {readOn !== undefined && (
                    <>
                      {" "}
                      ({extent !== undefined && `${extent}, `}
                      <span className="num">{formatSourceDate(readOn)}</span>)
                    </>
                  )}
                </div>
              );
            })}
            {item.statements.length > 0 && (
              <Fold data-ui="baseline-statements"
                concept="sourceText"
                label={
                  <>
                    {tr("Frases leídas", "Statements read")} (<span className="num">{formatNumber(item.statements.length)}</span>)
                  </>
                }
              >
                <ul>
                  {item.statements.map((row) => (
                    <li key={row.id}>
                      {row.direction_display}: {row.quote_display}
                      <div className="secondary">
                        {row.compared_with_display} {row.population}.
                      </div>
                      <div className="secondary">
                        {row.where}. {row.source} ({row.extent_text},{" "}
                        <span className="num">{formatSourceDate(row.read_on)}</span>)
                      </div>
                    </li>
                  ))}
                </ul>
              </Fold>
            )}
          </li>
        ))}
      </ul>
    </Fold>
  );
}

function StateRow({
  item,
  row,
  first,
  stale,
}: {
  item: BaselineIndicator;
  row: BaselineState;
  first: boolean;
  stale: boolean;
}) {
  const num = stale ? "num stale" : "num";
  const unit = displayUnit(item.unit);
  return (
    <tr data-baseline-state={`${item.key}|${row.context}`}>
      {first && (
        <td rowSpan={item.states.length}>
          <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
          {item.unattributed_display !== null && <div className="secondary">{item.unattributed_display}</div>}
        </td>
      )}
      <td>
        {row.context_display}
        {row.latest && <span className="secondary"> · {tr("última lectura", "latest reading")}</span>}
      </td>
      <td>
        {row.status_display}
        <div className="secondary">
          <span className={num}>
            {formatNumber(row.samples)} {tr("de", "of")} {formatNumber(row.min_samples)}
          </span>{" "}
          {tr("lecturas", "readings")}
        </div>
        {row.drawn_from === "family" && <div className="secondary">{row.drawn_from_display}</div>}
        <CompositionLine row={row} stale={stale} />
      </td>
      {row.median !== null && row.spread !== null ? (
        <td>
          <span className={num}>{formatNumber(row.median, row.decimals)}</span> {unit}
          <div className="secondary">
            {tr("dispersión", "spread")} <span className={num}>{formatNumber(row.spread, row.decimals + 1)}</span> {unit}
          </div>
        </td>
      ) : (
        // En aprendizaje no hay mediana contra la que se juzgue: en su sitio, contra qué sí.
        <td className="secondary">{row.judged_against}</td>
      )}
      <td className="secondary">
        {row.established && <div>{row.judged_against}</div>}
        {row.cuts.map((cut) => (
          <div key={cut.severity} className={stale ? "stale" : undefined} data-baseline-cut={cut.severity}>
            {cut.text}
          </div>
        ))}
        {row.cuts_note !== null && <div className={stale ? "stale" : undefined}>{row.cuts_note}</div>}
        <div>{row.danger_limit.text}</div>
      </td>
    </tr>
  );
}

/**
 * De qué está hecha la base (§5.37.2, especificación §2: no mezclar entornos «sin conservar
 * evidence_context»): cuántas lecturas de cada entorno y de cada tipo, con la palabra y el dibujo
 * de `lib/provenance.ts` (rótulos, sin color: el entorno describe, no avisa). La frase, si la base
 * mezcla entornos, tiene valores no medidos o no se sabe de qué está hecha, es del backend.
 */
function CompositionLine({ row, stale }: { row: BaselineState; stale: boolean }) {
  const composition = row.composition;
  const sentence = row.composition_display !== null && (
    <div className={stale ? "stale" : undefined}>{row.composition_display}</div>
  );
  if (composition === null || composition.samples === 0) {
    return sentence === false ? null : <div className="secondary">{sentence}</div>;
  }
  const num = stale ? "num stale" : "num";
  return (
    <div className="secondary" data-baseline-composition>
      {tally(composition.evidence_context, num, (key) => (
        <Mark pictogram={contextPictogram(key)} stale={stale}>
          {contextLabel(key)}
        </Mark>
      ))}
      {" · "}
      {tally(composition.observation_type, num, (key) => (
        <Mark pictogram={typeStyle(key).pictogram} title={typeStyle(key).meaning} stale={stale}>
          {typeStyle(key).word}
        </Mark>
      ))}
      {sentence}
    </div>
  );
}

/** Cada clave con su cuenta, en el orden del backend (de la más frecuente a la menos). */
function tally(counts: Record<string, number>, num: string, name: (key: string) => ReactNode): ReactNode[] {
  return Object.entries(counts).map(([key, count], index) => (
    <span key={key}>
      {index > 0 && " · "}
      {name(key)} <span className={num}>{formatNumber(count)}</span>
    </span>
  ));
}
