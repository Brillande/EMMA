import { useCallback, useEffect, useState } from "react";

import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { type RecordedFindings, type UltrasoundProtocol, api } from "../lib/api";
import { OK_MARK } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { ReasonLine } from "./Attention";
import { type FindingsForm, missingSigns, readable, withValue } from "./findings";
import { SignValue } from "./SignValue";

/**
 * Lista de calidad y signos anotados de un estudio.
 *
 * Los signos son observaciones del operador, no diagnosticos: "Deslizamiento pleural:
 * ausente", nunca el nombre de una enfermedad. Lo que puede elegirse lo declara el backend
 * (`/api/imaging/protocols`); aqui no se escribe ningun texto clinico. Cada valor registrado se
 * lee con su marca (`signValueMark`): la ventana con algo, la ventana vacia o no disponible.
 * Cada ventana del protocolo es una zona del cuerpo y su leyenda lleva la chincheta de «zona»
 * (`lib/uiMarks.ts`, segunda pasada §5.33.10).
 */
export function FindingsPanel({
  study,
  protocol,
  onRecorded,
}: {
  study: number;
  protocol: UltrasoundProtocol;
  onRecorded: (count: number) => void;
}) {
  const [operator, setOperator] = useOperator();
  const [checklist, setChecklist] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(protocol.checklist.map((item) => [item, false])),
  );
  const [form, setForm] = useState<FindingsForm>({});
  const [records, setRecords] = useState<RecordedFindings[]>([]);
  // Lo ultimo que paso: registrado, la lectura de lo anotado que fallo, o lo que salio mal al
  // registrar (`ReasonLine` decide si es un rechazo del backend o un fallo).
  const [message, setMessage] = useState<
    { kind: "recorded" } | { kind: "failed"; reason: unknown } | null
  >(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.imaging
      .findings(study)
      .then((items) => {
        setRecords(items);
        onRecorded(items.length);
      })
      .catch((reason: unknown) => setMessage({ kind: "failed", reason }));
  }, [study, onRecorded]);
  useEffect(load, [load]);

  const missing = missingSigns(protocol, form);
  const ready = missing === 0 && operator.trim() !== "";

  const submit = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await api.imaging.recordFindings(study, {
        checklist,
        findings: form,
        recorded_by: operator.trim(),
      });
      setMessage({ kind: "recorded" });
      load();
    } catch (reason) {
      setMessage({ kind: "failed", reason });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section data-ui="imaging-findings" className="draft-panel" aria-label="Calidad y signos">
      <PanelTitle as="h3" concept="acquisitionQuality">
        {protocol.views.length > 0 ? "Calidad y signos anotados" : "Calidad de la adquisición"}
      </PanelTitle>
      <div className="silence-form">
        {protocol.checklist.map((item) => (
          <label key={item}>
            <input
              type="checkbox"
              checked={checklist[item] ?? false}
              onChange={(event) => setChecklist({ ...checklist, [item]: event.target.checked })}
            />{" "}
            {item}
          </label>
        ))}
        {protocol.views.map((view) => (
          <fieldset key={view.key} className="view-signs">
            <FieldLabel as="legend" concept="zone">
              {view.display}
            </FieldLabel>
            {view.signs.map((sign) => (
              <label key={sign.key}>
                {sign.display}{" "}
                <select
                  value={form[view.key]?.[sign.key] ?? ""}
                  onChange={(event) =>
                    setForm(withValue(form, view.key, sign.key, event.target.value))
                  }
                >
                  <option value="" disabled>
                    — elegir —
                  </option>
                  {Object.entries(sign.values).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </fieldset>
        ))}
        <FieldLabel concept="person" className="operator">
          Anotado por{" "}
          <input
            value={operator}
            maxLength={64}
            onChange={(event) => setOperator(event.target.value)}
            placeholder="nombre o indicativo"
          />
        </FieldLabel>
        <div className="measure-actions">
          <Command concept="register" disabled={!ready || busy} onClick={() => void submit()}>
            {busy ? "Registrando…" : "Registrar"}
          </Command>
          {missing > 0 && (
            <span className="secondary">
              Faltan <span className="num">{missing}</span> signos por contestar (vale «No valorable»).
            </span>
          )}
        </div>
        {message?.kind === "recorded" && (
          <p className="secondary">
            <MarkOf mark={OK_MARK}>Registrado.</MarkOf>
          </p>
        )}
        {message?.kind === "failed" && <ReasonLine reason={message.reason} />}
      </div>

      {records.map((record) => (
        <div className="draft" key={record.ledger_index}>
          <p className="secondary">Anotado por {record.recorded_by}</p>
          {record.checklist
            .filter((point) => !point.done)
            .map((point) => (
              <p key={point.item} className="c-yellow">
                <Mark pictogram="shape-triangle">Calidad no cumplida: {point.item}</Mark>
              </p>
            ))}
          {readable(protocol, record).length > 0 && (
            <div className="quality-table">
            <table className="ledger">
              <tbody>
                {readable(protocol, record).map((row) => (
                  <tr key={`${row.view}:${row.sign}`}>
                    <td>{row.view}</td>
                    <td>{row.sign}</td>
                    <td>
                      <SignValue code={row.code}>{row.value}</SignValue>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

