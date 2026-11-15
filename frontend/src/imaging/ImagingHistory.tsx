import { useEffect, useState } from "react";

import {
  type ImagingStudy,
  type Indicator,
  type MeasurementRecord,
  type ProtocolCatalog,
  type RecordedFindings,
  api,
} from "../lib/api";
import { useArrivalCheck, useFixedRequest } from "../lib/arrival";
import { BoardOnly } from "../components/BoardOnly";
import { IndicatorName } from "../components/IndicatorName";
import { MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import { Loading } from "../components/Unavailable";
import { displayUnit, formatMinutes, formatNumber } from "../lib/format";
import { uiPictogram } from "../lib/uiMarks";
import { readable } from "./findings";
import { protocolPictogram } from "./protocols";
import { SignValue } from "./SignValue";
import { tr } from "../lib/i18n";

interface Row {
  study: ImagingStudy;
  measurements: MeasurementRecord[];
  findings: RecordedFindings[];
}

/**
 * Lo fijo del panel: los protocolos (para leer los hallazgos) y los indicadores (para las cifras),
 * estos ya por clave. Hecho una vez: cada vuelta reutiliza el mismo índice en vez de rehacerlo.
 */
const loadCatalogs = () =>
  Promise.all([api.imaging.protocols(), api.indicators()]).then(([protocols, catalogue]) => ({
    protocols,
    indicators: Object.fromEntries(catalogue.indicators.map((item): [string, Indicator] => [item.key, item])),
  }));

/**
 * Ecografias en la consola de Tierra: solo lo que ya puede haber llegado.
 *
 * Un estudio registrado a bordo hace menos de un tiempo de luz todavia esta en transito:
 * no se lista. El corte se toma del reloj actual y no de la ultima lectura de constantes,
 * porque un estudio viaja cuando se registra, haya o no telemetria nueva.
 *
 * La frase del transito lleva el signo del retardo con Tierra (`lightTime`), que es de lo que
 * habla; las cabeceras, el de su concepto (segunda pasada, §5.33.10).
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta (`BoardOnly`), encima de
 * la tabla, las fichas de cuántos estudios y cuántas medidas han llegado (`ArrivedBoard`), las mismas
 * filas y cifras de la tabla contadas. Sin estudios no hay fichas: la frase en cian ya lo dice.
 */
export function ImagingHistory({
  subject,
  oneWayMinutes,
}: {
  subject: string;
  oneWayMinutes: number | null;
}) {
  // `null` hasta la primera respuesta: «no ha llegado ninguno» antes de preguntar seria falso.
  // Los estudios y el fallo van con el tripulante del que son: al cambiar de tripulante no se
  // pintan ni un instante los del anterior bajo el nuevo (§5.37.17, revisión; como el historial).
  const [loaded, setLoaded] = useState<{ subject: string; rows: Row[] } | null>(null);
  const [catalog, setCatalog] = useState<ProtocolCatalog | null>(null);
  const [indicators, setIndicators] = useState<Record<string, Indicator>>({});
  const [failed, setFailed] = useState<{ subject: string; outcome: RequestOutcome } | null>(null);
  const rows = loaded?.subject === subject ? loaded.rows : null;
  const error = failed?.subject === subject ? failed.outcome : null;
  // El corte del reloj, cada 30 s y con el último tiempo de luz (`useArrivalCheck`, §5.37.17).
  const { checkKey, cutNow } = useArrivalCheck(oneWayMinutes);
  // Los dos catálogos son fijos: una vez, no en cada vuelta del reloj (§5.38.12).
  const catalogs = useFixedRequest(loadCatalogs);

  useEffect(() => {
    let cancelled = false;
    // El mismo corte para los estudios y para sus medidas y hallazgos.
    const cutoff = cutNow();
    Promise.all([catalogs(), api.imaging.studies(subject, cutoff)])
      .then(async ([fixed, studies]) => {
        const [measured, annotated] = await Promise.all([
          Promise.all(studies.map((study) => api.imaging.measurements(study.ledger_index))),
          Promise.all(studies.map((study) => api.imaging.findings(study.ledger_index))),
        ]);
        const arrived = (recorded: string) => cutoff === undefined || new Date(recorded) <= cutoff;
        if (cancelled) return;
        setFailed(null);
        setCatalog(fixed.protocols);
        setIndicators(fixed.indicators);
        setLoaded({
          subject,
          rows: studies.map((study, index) => ({
            study,
            measurements: (measured[index] ?? []).filter((record) => arrived(record.recorded)),
            findings: (annotated[index] ?? []).filter((record) => arrived(record.recorded)),
          })),
        });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setFailed({ subject, outcome: requestOutcome(reason) });
      });
    return () => {
      cancelled = true;
    };
  }, [subject, checkKey, cutNow, catalogs]);

  const protocolName = (key: string) =>
    catalog?.protocols.find((item) => item.key === key)?.display ?? key;
  const shown = (record: MeasurementRecord) => {
    const indicator = indicators[record.key];
    return indicator === undefined
      ? formatNumber(record.value, 1)
      : `${formatNumber(record.value, indicator.decimals)} ${displayUnit(indicator.unit)}`;
  };

  return (
    <section data-ui="ultrasound-received" className="panel" aria-label={tr("Ecografías recibidas", "Ultrasounds received")}>
      <PanelTitle pictogram="probe-fan">{tr("Ecografías recibidas", "Ultrasounds received")}</PanelTitle>
      {oneWayMinutes !== null && (
        <p className="secondary">
          <Mark pictogram={uiPictogram("lightTime")}>
            {tr("Lo registrado a bordo en los últimos", "What was recorded on board in the last")}{" "}
            <span className="num">{formatMinutes(oneWayMinutes)}</span> {tr("está en tránsito.", "is in transit.")}
          </Mark>
        </p>
      )}
      {catalog !== null && !catalog.alerting.active && (
        <p className="c-gray">
          <Mark pictogram="slash-circle">{catalog.alerting.note}</Mark>
        </p>
      )}
      {error !== null && (
        <p>
          <MarkOf mark={error.mark}>{error.text}</MarkOf>
        </p>
      )}
      {rows === null ? (
        // Sin respuesta todavia; si la lectura fallo, ya lo dice la cruz roja de arriba.
        error === null && (
          <Loading />
        )
      ) : rows.length === 0 ? (
        <p className="c-cyan">
          <Mark pictogram="ring-dotted">
            {tr("Todavía no ha llegado ningún estudio a Tierra.", "No study has reached Earth yet.")}
          </Mark>
        </p>
      ) : (
        <>
        <BoardOnly>
          <ArrivedBoard rows={rows} stale={error !== null} />
        </BoardOnly>
        <div className="quality-table">
        <table className="ledger">
          <thead>
            <tr>
              <Th concept="time">{tr("Adquirido (UTC)", "Acquired (UTC)")}</Th>
              <Th concept="protocol">{tr("Protocolo", "Protocol")}</Th>
              <Th concept="measure">{tr("Medidas", "Measurements")}</Th>
              <Th concept="person">{tr("Medido por", "Measured by")}</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ study, measurements, findings }) => (
              <tr key={study.ledger_index}>
                <td className="num">{study.acquired.slice(0, 16).replace("T", " ")}</td>
                <td>
                  <Mark pictogram={protocolPictogram(study.protocol)}>{protocolName(study.protocol)}</Mark>
                  {study.synthetic === true && <span className="secondary"> · {tr("fantoma simulado", "simulated phantom")}</span>}
                  {study.dataset !== undefined && <span className="secondary"> · {tr("ejemplo real de dataset", "real dataset example")}</span>}
                </td>
                <td>
                  {findings.map((record) => (
                    <SignSummary key={record.ledger_index} catalog={catalog} record={record} />
                  ))}
                  {findings.length > 0 ? null : measurements.length === 0 ? (
                    study.calibration.length === 0 ? (
                      <MarkOf mark={MISSING_MARK}>
                        {tr("sin calibración: no medible", "no calibration: not measurable")}
                      </MarkOf>
                    ) : (
                      <Mark pictogram="ring-dotted" className="secondary">
                        {tr("sin medir", "not measured")}
                      </Mark>
                    )
                  ) : (
                    measurements.map((record) => (
                      <div key={record.ledger_index}>
                        <IndicatorName
                          indicatorKey={record.key}
                          displayEs={indicators[record.key]?.display_es ?? record.key}
                        />
                        : <span className="num">{shown(record)}</span>
                      </div>
                    ))
                  )}
                </td>
                <td>
                  {[
                    ...new Set([
                      ...measurements.map((record) => record.measured_by),
                      ...findings.map((record) => record.recorded_by),
                    ]),
                  ].join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        </>
      )}
    </section>
  );
}

/**
 * Lo llegado a Tierra, contado: los estudios de la tabla y sus medidas ya llegadas (las mismas que
 * lista la columna «Medidas»; un estudio con hallazgos enseña los hallazgos, pero sus medidas
 * llegadas cuentan igual). Si la última lectura falló, las cifras son las de antes, en cursiva.
 */
export function ArrivedBoard({ rows, stale }: { rows: readonly Row[]; stale: boolean }) {
  const measured = rows.reduce((total, row) => total + row.measurements.length, 0);
  return (
    <div className="board-stats arrived-board" role="group" aria-label={tr("Ecografías llegadas a Tierra", "Ultrasounds arrived on Earth")}>
      <StatTile pictogram="probe-fan" label={tr("Estudios llegados", "Studies arrived")} value={rows.length} stale={stale} />
      <StatTile concept="measure" label={tr("Medidas llegadas", "Measurements arrived")} value={measured} stale={stale} />
    </div>
  );
}

/** Signos valorables de un registro, con su marca; los "no valorable" se cuentan, no se listan. */
export function SignSummary({
  catalog,
  record,
}: {
  catalog: ProtocolCatalog | null;
  record: RecordedFindings;
}) {
  const protocol = catalog?.protocols.find((item) => item.key === record.protocol);
  if (protocol === undefined) return null;
  const rows = readable(protocol, record);
  const assessed = rows.filter((row) => row.assessable);
  const skipped = rows.length - assessed.length;
  return (
    <div>
      {assessed.map((row) => (
        <div key={`${row.view}:${row.sign}`}>
          {row.sign} ({row.view}): <SignValue code={row.code}>{row.value}</SignValue>
        </div>
      ))}
      {skipped > 0 && (
        <div className="c-gray">
          <Mark pictogram="slash-circle">
            <span className="num">{skipped}</span> {tr("signos no valorables", "signs not assessable")}
          </Mark>
        </div>
      )}
    </div>
  );
}

