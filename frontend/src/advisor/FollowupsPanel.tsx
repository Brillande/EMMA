import { useState } from "react";

import { BoardOnly } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { DomainName } from "../components/DomainName";
import { Mark } from "../components/Mark";
import { Meter } from "../components/Meter";
import { PanelTitle } from "../components/PanelTitle";
import type { CrewStatus, Followup } from "../lib/api";
import { formatMet, formatNumber, missionElapsedSeconds } from "../lib/format";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { RequestWarning } from "./RequestWarning";
import { STATE_LABEL, outcomeMark, stateLabel, statePictogram } from "./followups";

/**
 * Contramedidas adoptadas y su seguimiento (especificacion §7, §14).
 *
 * El estado y la evaluacion los calcula y redacta el backend; aqui solo se muestran y se
 * ofrece cerrar con motivo, una decision humana que queda firmada. Sin color de alerta: un
 * seguimiento no es una alarma. Cada estado lleva su pictograma junto a la palabra (F.5.10 e), el
 * dominio su dibujo y la evaluacion la flecha de su resultado (`followups.ts`).
 *
 * Segunda pasada (§5.33.5): el titulo lleva la lupa de «seguimiento» y el mando de cerrar la marca
 * de «dar algo por bueno» (`lib/uiMarks.ts`). El fallo de una peticion sigue en amarillo, ahora con
 * el triangulo delante: el color nunca va solo.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo el título, el recuento por estado en píldoras con
 * el mismo pictograma y la misma palabra que cada fila; y en cada seguimiento abierto, el medidor
 * del avance de su ventana de observación frente a la referencia del estado, rotulado con las dos
 * fechas que la fila ya escribe. Solo en la concha de la maqueta (`BoardOnly`); la escala es la
 * propia ventana, y sin ella no hay medidor.
 */
export function FollowupsPanel({
  status,
  operator,
  onClose,
}: {
  status: CrewStatus;
  operator: string;
  onClose: (adoptionIndex: number, by: string, reason: string) => Promise<void>;
}) {
  if (status.followups.length === 0) return null;
  return (
    <section data-ui="followups" className="panel" aria-label="Seguimiento de contramedidas">
      <PanelTitle concept="followUp">Seguimiento</PanelTitle>
      <BoardOnly>
        <ul className="board-tally" aria-label="Seguimientos por estado">
          {stateTally(status.followups).map((entry) => (
            <li key={entry.state} className="ref-pill board-pill">
              <Mark pictogram={statePictogram(entry.state)}>{stateLabel(entry.state)}</Mark>{" "}
              <span className="num">{formatNumber(entry.count)}</span>
            </li>
          ))}
        </ul>
      </BoardOnly>
      <ul className="followups">
        {status.followups.map((item) => (
          <FollowupRow
            key={item.adoption_index}
            item={item}
            start={status.mission.start}
            reference={status.data.reference_time}
            operator={operator}
            onClose={onClose}
          />
        ))}
      </ul>
    </section>
  );
}

/**
 * Cuántos seguimientos hay en cada estado, en el orden de la tabla de palabras (en ventana, listo
 * para revisar, cerrado) y, detrás, cualquier estado que esta versión no conozca, con su clave tal
 * cual (`stateLabel`). Solo los estados con alguno.
 */
function stateTally(items: readonly Followup[]): { state: string; count: number }[] {
  const counts = new Map<string, number>(Object.keys(STATE_LABEL).map((state) => [state, 0]));
  for (const item of items) counts.set(item.state, (counts.get(item.state) ?? 0) + 1);
  return [...counts].filter(([, count]) => count > 0).map(([state, count]) => ({ state, count }));
}

const HOUR_MS = 3_600_000;

/**
 * El avance de la ventana de observación frente a la referencia del estado, en horas: cuánto de
 * `adopted_at`..`window_ends` ha pasado, acotado a la escala (antes de adoptar, el principio;
 * pasada la ventana, el final: que ya toca revisar lo dice la palabra del estado). Con una fecha
 * ilegible o la ventana al revés no hay medidor: no se dibuja una escala falsa.
 */
function windowProgress(item: Followup, reference: string): { value: number; max: number } | null {
  const start = Date.parse(item.adopted_at);
  const end = Date.parse(item.window_ends);
  const now = Date.parse(reference);
  if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(now) || !(end > start)) return null;
  const max = (end - start) / HOUR_MS;
  return { value: Math.min(max, Math.max(0, (now - start) / HOUR_MS)), max };
}

/** La evaluacion del backend, tal cual, con la flecha de su resultado delante. */
function EvaluationLine({ evaluation }: { evaluation: NonNullable<Followup["evaluation"]> }) {
  const look = outcomeMark(evaluation.outcome);
  return (
    <p>
      <Mark pictogram={look.pictogram} color={look.color}>
        {evaluation.text}
      </Mark>
    </p>
  );
}

function FollowupRow({
  item,
  start,
  reference,
  operator,
  onClose,
}: {
  item: Followup;
  start: string;
  /** La referencia del estado (`status.data.reference_time`): el ahora de los datos, no el del reloj. */
  reference: string;
  operator: string;
  onClose: (adoptionIndex: number, by: string, reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const met = (iso: string) => formatMet(missionElapsedSeconds(start, new Date(iso)));
  const who = operator.trim();
  // Un seguimiento cerrado ya no tiene ventana que avance: el medidor es solo de los abiertos.
  const progress = item.state === "closed" ? null : windowProgress(item, reference);
  return (
    <li>
      <strong>{item.countermeasure.action}</strong>
      <p className="secondary">
        <DomainName domain={item.domain} /> · adoptada por {item.adopted_by} en{" "}
        {met(item.adopted_at)} · revisar desde {met(item.window_ends)}
        {/* Con qué reglas se firmaron la adopción y el cierre (§5.39.9): la frase del backend
            tal cual, sin color. Es información, no una señal. */}
        {item.adoption_rules ? ` · ${item.adoption_rules.text}` : ""}
      </p>
      {progress !== null && (
        <BoardOnly>
          <Meter
            value={progress.value}
            max={progress.max}
            label={`Avance de la ventana de observación: de ${met(item.adopted_at)} a ${met(item.window_ends)}`}
          />
        </BoardOnly>
      )}
      <p>
        <Mark pictogram={statePictogram(item.state)}>{stateLabel(item.state)}</Mark>
        {item.state === "closed" && item.closed_by !== null && (
          <span className="secondary">
            {" "}
            por {item.closed_by}: {item.closed_reason}
            {item.closure_rules ? ` · ${item.closure_rules.text}` : ""}
          </span>
        )}
      </p>
      {item.evaluation !== null && <EvaluationLine evaluation={item.evaluation} />}
      {item.state !== "closed" && (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            setBusy(true);
            setError(null);
            onClose(item.adoption_index, who, reason.trim())
              .then(() => setReason(""))
              .catch((cause: unknown) => setError(requestOutcome(cause)))
              .finally(() => setBusy(false));
          }}
        >
          <input
            value={reason}
            maxLength={500}
            onChange={(event) => setReason(event.target.value)}
            placeholder="motivo del cierre"
            aria-label="Motivo del cierre"
          />
          <Command
            concept="closeFollowUp"
            type="submit"
            disabled={busy || who === "" || reason.trim() === ""}
          >
            Cerrar seguimiento
          </Command>
          {error !== null && <RequestWarning outcome={error} />}
        </form>
      )}
    </li>
  );
}
