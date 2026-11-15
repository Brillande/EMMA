import { useEffect, useState } from "react";

import { BoardOnly } from "../components/BoardOnly";
import { IndicatorName } from "../components/IndicatorName";
import { MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import { type RecoveryReport, api } from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { INSIDE_MARK, OUTSIDE_MARK, RETURN_MARKS, returnMark } from "./recovery";

/**
 * Recuperacion posvuelo (especificacion §10, "postflight/recovery"): cada toma posvuelo frente
 * al rango prevuelo del propio tripulante. Descriptivo: dentro o fuera del rango, con la
 * diferencia; el veredicto de recuperacion es de una persona (texto del backend). En rango lleva
 * el anillo; fuera, el rombo en azul (aviso, F.5-1): las mismas marcas que la comprobacion de
 * proyecciones. Cada indicador, con el pictograma de su familia junto a su nombre.
 *
 * La última columna (§5.37.7) dice cuándo vuelve y si vuelve: la frase del backend
 * (`recovery.return_to_range`) con la marca de la última toma (`ground/recovery.ts`). Los
 * indicadores con tomas posteriores al vuelo y sin rango propio con que compararlas van al final,
 * con el cian del dato ausente: se dicen, no se suponen ni desaparecen.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta (`BoardOnly`), encima de
 * la tabla, una píldora por estado de vuelta al rango con cuántos indicadores están en él, con la
 * misma marca que lleva su fila (`ReturnTally`).
 */
export function RecoveryPanel({ subject, refreshKey }: { subject: string; refreshKey: string }) {
  const [report, setReport] = useState<RecoveryReport | null>(null);
  useEffect(() => {
    api
      .recovery(subject)
      .then(setReport)
      .catch(() => setReport(null));
  }, [subject, refreshKey]);

  if (report === null || (report.indicators.length === 0 && report.without_preflight_range.length === 0)) {
    return null;
  }
  return (
    <section data-ui="recovery" className="panel" aria-label={tr("Recuperación posvuelo", "Postflight recovery")}>
      <PanelTitle concept="recovery">
        {tr("Recuperación posvuelo", "Postflight recovery")} <ObservationTypeBadge type="measured" context="spaceflight" />
      </PanelTitle>
      <BoardOnly>
        <ReturnTally states={[...report.indicators, ...report.without_preflight_range].map((item) => item.return_to_range.state)} />
      </BoardOnly>
      <div className="quality-table table-scroll" role="region" tabIndex={0} aria-label={tr("Recuperación por indicador", "Recovery by indicator")}>
        <table className="recovery">
          <thead>
            <tr>
              <Th concept="indicator">{tr("Indicador", "Indicator")}</Th>
              <Th concept="range">{tr("Prevuelo", "Preflight")}</Th>
              <Th concept="measured">{tr("Posvuelo (días tras el regreso)", "Postflight (days after return)")}</Th>
              <Th concept="recovery">{tr("Vuelta al rango", "Return to range")}</Th>
            </tr>
          </thead>
          <tbody>
            {report.indicators.map((item) => {
              const unit = displayUnit(item.unit);
              return (
                <tr key={item.key}>
                  <th scope="row">
                    <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
                  </th>
                  <td>
                    <span className="num">{formatNumber(item.preflight.low, 2)}</span>–
                    <span className="num">{formatNumber(item.preflight.high, 2)}</span> {unit}{" "}
                    <span className="secondary">
                      (<span className="num">{formatNumber(item.preflight.samples)}</span> {tr("tomas", "samples")})
                    </span>
                  </td>
                  <td>
                    {item.postflight.map((point) => (
                      // Por su instante: varias tomas pueden compartir R+.
                      <span key={point.at} className="recovery-point">
                        R+<span className="num">{formatNumber(point.days_after_landing)}</span>:{" "}
                        <span className="num">{formatNumber(point.value, 2)}</span>{" "}
                        {point.within_preflight_range ? (
                          <MarkOf mark={INSIDE_MARK} className="secondary">
                            {tr("en rango", "in range")}
                          </MarkOf>
                        ) : (
                          <MarkOf mark={OUTSIDE_MARK}>
                            {tr("fuera de rango", "out of range")}
                            {point.delta_pct !== null && (
                              <>
                                {" "}
                                (<span className="num">{formatNumber(point.delta_pct, 1)}</span> %)
                              </>
                            )}
                          </MarkOf>
                        )}
                      </span>
                    ))}
                  </td>
                  <td>
                    <MarkOf mark={returnMark(item.return_to_range.state)}>{item.return_to_range.text}</MarkOf>
                  </td>
                </tr>
              );
            })}
            {report.without_preflight_range.map((item) => (
              <tr key={item.key}>
                <th scope="row">
                  <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
                </th>
                <td className="secondary">
                  <span className="num">{formatNumber(item.preflight_samples)}</span>{" "}
                  {item.preflight_samples === 1 ? tr("toma", "sample") : tr("tomas", "samples")}
                </td>
                <td className="secondary">
                  R+<span className="num">{formatNumber(item.first_day)}</span>
                  {item.last_day !== item.first_day && (
                    <>
                      –R+<span className="num">{formatNumber(item.last_day)}</span>
                    </>
                  )}{" "}
                  (<span className="num">{formatNumber(item.postflight_samples)}</span>{" "}
                  {item.postflight_samples === 1 ? tr("toma", "sample") : tr("tomas", "samples")})
                </td>
                <td>
                  <MarkOf mark={returnMark(item.return_to_range.state)}>{item.return_to_range.text}</MarkOf>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="secondary">{report.basis}</p>
      {report.source !== null && (
        <p className="secondary">
          {tr("Datos:", "Data:")} <a href={report.source} target="_blank" rel="noreferrer">NASA OSDR, OSD-569</a>
        </p>
      )}
    </section>
  );
}

/**
 * La palabra corta de cada estado, para su píldora; la frase entera, con sus R+, es la del backend
 * en la fila. Son las palabras de esa frase («dentro», «dentro de nuevo», «sin volver») y la de la
 * fila sin rango propio.
 */
const RETURN_WORDS: Readonly<Record<keyof typeof RETURN_MARKS, string>> = {
  within: tr("dentro", "within"),
  "back-again": tr("dentro de nuevo", "within again"),
  "not-back": tr("sin volver", "not back"),
  "no-preflight-range": tr("sin rango previo", "no preflight range"),
};

/**
 * Cuántos indicadores hay en cada estado de vuelta al rango, en el orden de la tabla de palabras y,
 * después, los que la interfaz no conoce con su clave y la marca de «desconocido». Solo los que
 * tienen alguno.
 */
export function ReturnTally({ states }: { states: readonly string[] }) {
  const counts = new Map<string, number>();
  for (const state of states) counts.set(state, (counts.get(state) ?? 0) + 1);
  const known = Object.keys(RETURN_WORDS);
  const order = [...known, ...[...counts.keys()].filter((state) => !known.includes(state))];
  return (
    <ul className="board-tally return-tally" aria-label={tr("Indicadores por vuelta al rango", "Indicators by return to range")}>
      {order
        .filter((state) => (counts.get(state) ?? 0) > 0)
        .map((state) => {
          const look = returnMark(state);
          const word = Object.hasOwn(RETURN_WORDS, state) ? RETURN_WORDS[state as keyof typeof RETURN_WORDS] : state;
          return (
            <li key={state} className="ref-pill board-pill">
              <MarkOf mark={look}>{word}</MarkOf> <span className="num">{formatNumber(counts.get(state) ?? 0)}</span>
            </li>
          );
        })}
    </ul>
  );
}
