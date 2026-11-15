import { useState } from "react";

import { FieldLabel } from "../components/FieldLabel";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import { type LabReading, api } from "../lib/api";
import { formatNumber } from "../lib/format";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { readingMark } from "./marks";

/**
 * Cifras leidas en una analitica (Polaris `biomarcadores`): ninguna entra en el analisis hasta que
 * una persona la confirma con el papel delante. La que exige correccion (unidad de otra familia,
 * valor censurado) se marca en amarillo con triangulo (F.5-1, "attention required") y solo se
 * confirma dando valor y unidad del catalogo. "Fuera de rango" es el rango que trae el propio
 * informe: se dice, no se colorea ni se dibuja, porque EMMA no lo interpreta. El analito se nombra
 * con el pictograma de la familia de su indicador, y el estado con la casilla por marcar o el
 * hecho (`./marks.ts`). Las cabeceras llevan el signo de su concepto (`lib/uiMarks.ts`,
 * segunda pasada §5.33.10); «Confirmar» sigue con la marca de su estado, que cambia.
 */
export function LabReadings({
  report,
  readings,
  reportDate,
  operator,
  onConfirmed,
}: {
  report: number;
  readings: LabReading[];
  reportDate: string | null;
  operator: string;
  onConfirmed: () => void;
}) {
  const [date, setDate] = useState(reportDate ?? "");
  return (
    <div className="lab-readings">
      <PanelTitle as="h3" pictogram="page-grid">
        Cifras leídas
      </PanelTitle>
      <FieldLabel concept="date">
        Fecha de extracción{" "}
        <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        {reportDate === null && <span className="secondary"> (el informe no la trae legible)</span>}
      </FieldLabel>
      <div className="quality-table">
      <table className="ledger">
        <thead>
          <tr>
            <Th concept="analyte">Analito</Th>
            <Th concept="value">Valor</Th>
            <Th concept="range">Rango del informe</Th>
            <Th concept="state">Estado</Th>
          </tr>
        </thead>
        <tbody>
          {readings.map((item, index) => (
            <Row
              key={`${item.key}:${index}`}
              report={report}
              index={index}
              item={item}
              date={date}
              operator={operator}
              onConfirmed={onConfirmed}
            />
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}

function Row({
  report,
  index,
  item,
  date,
  operator,
  onConfirmed,
}: {
  report: number;
  index: number;
  item: LabReading;
  date: string;
  operator: string;
  onConfirmed: () => void;
}) {
  const [value, setValue] = useState("");
  // Lo que salio mal al confirmar: el rechazo del backend (triangulo) o el fallo (cruz).
  const [failure, setFailure] = useState<RequestOutcome | null>(null);
  const who = operator.trim();
  const corrected = value.trim() === "" ? null : Number(value.replace(",", "."));
  const blocked =
    who === "" || date === "" || (item.requires_correction && (corrected === null || Number.isNaN(corrected)));
  const confirm = () => {
    setFailure(null);
    api.reports
      .confirmLab(report, {
        reading_index: index,
        confirmed_by: who,
        effective_date: date,
        ...(corrected !== null ? { value: corrected, unit: item.unit } : {}),
      })
      .then(onConfirmed)
      .catch((reason: unknown) => setFailure(requestOutcome(reason)));
  };
  const range =
    item.ref_low !== null && item.ref_high !== null
      ? `${formatNumber(item.ref_low, 2)}–${formatNumber(item.ref_high, 2)}`
      : "—";
  return (
    <tr>
      <td>
        <IndicatorName indicatorKey={item.key} displayEs={item.name} />
        {item.derived_from !== undefined && <span className="secondary"> ({item.derived_from})</span>}
      </td>
      <td>
        {item.comparator ?? ""}
        <span className="num">{formatNumber(item.value, 2)}</span> {item.unit}
        {item.report_unit !== "" && item.report_unit !== item.unit && (
          <span className="secondary"> (leído en {item.report_unit})</span>
        )}
      </td>
      <td>
        <span className="num">{range}</span>
        {item.out_of_range && <span className="secondary"> · fuera de rango</span>}
      </td>
      <td>
        {item.status === "confirmada" ? (
          <Mark pictogram={readingMark(item.status).pictogram} className="secondary">
            Confirmada por {item.confirmation?.confirmed_by}
            {item.confirmation?.value !== undefined && item.confirmation.value !== item.value && (
              <>
                {" "}
                (<span className="num">{formatNumber(item.confirmation.value, 2)}</span> {item.unit})
              </>
            )}
          </Mark>
        ) : (
          <>
            {item.requires_correction && (
              <span className="c-yellow">
                <Mark pictogram="shape-triangle">indica el valor del papel en {item.unit}</Mark>{" "}
              </span>
            )}
            <input
              aria-label={`Valor corregido de ${item.name}`}
              inputMode="decimal"
              placeholder={item.requires_correction ? "valor" : "corregir (opcional)"}
              value={value}
              size={8}
              onChange={(event) => setValue(event.target.value)}
            />
            <button className="command" disabled={blocked} onClick={confirm}>
              <Mark pictogram={readingMark(item.status).pictogram}>Confirmar</Mark>
            </button>
            {failure !== null && (
              <>
                {" "}
                <MarkOf mark={failure.mark}>{failure.text}</MarkOf>
              </>
            )}
          </>
        )}
      </td>
    </tr>
  );
}
