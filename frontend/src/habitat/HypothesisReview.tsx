import { useState } from "react";

import { Command } from "../components/Command";
import { Mark, MarkOf } from "../components/Mark";
import { type CrewHypothesis, api } from "../lib/api";
import { tr } from "../lib/i18n";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";

/**
 * Confirmacion humana de la hipotesis (especificacion §7). Solo las de causa ambiental, que son
 * las que tienen una excursion concreta que revisar. Queda firmada con motivo y operador; si se
 * confirma, el backend describe la recuperacion. En Tierra (sin operador) es de solo lectura.
 * La decision lleva su pictograma junto a la palabra, sin color: una revision firmada no es una
 * alerta. Es el mismo dibujo que el mando que la firmo (`confirm`, `reject` de `lib/uiMarks.ts`):
 * «Confirmar» y «Confirmada», «Descartar» y «Descartada» son un concepto cada par (§5.33.4).
 *
 * Un sistema de soporte vital declarado fuera de lo nominal (`declared_system`, §5.34.4) no se
 * confirma ni se descarta aquí: ya es lo que una persona firmó. En su sitio va esa declaración,
 * con la frase que compone el backend (quién, desde cuándo, qué asiento y que no es telemetría)
 * y la nota más reciente con quien la escribió, con el dibujo de declarar (`declare`, `note`).
 *
 * La radiación registrada en la ventana (`solar_event`, §5.37.5) tampoco: es lo que midió un
 * dosímetro o registró NASA DONKI. Se pinta la frase del backend tal cual, sin mandos.
 */
export function HypothesisReview({
  hypothesis,
  operator,
  onReviewed,
}: {
  hypothesis: CrewHypothesis;
  operator: string | undefined;
  onReviewed: () => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<RequestOutcome | null>(null);
  const excursion = hypothesis.excursion;
  if (excursion === null) {
    const radiation = hypothesis.radiation;
    if (radiation !== undefined) {
      return (
        <div className="hypothesis-review">
          <p>{radiation.statement}</p>
        </div>
      );
    }
    const system = hypothesis.system;
    if (system === undefined) return null;
    return (
      <div className="hypothesis-review">
        <p>
          <Mark pictogram={uiPictogram("declare")}>{system.statement}</Mark>
        </p>
        {system.note !== null && (
          <p className="secondary">
            <Mark pictogram={uiPictogram("note")}>{tr(`Nota de ${system.note_by}:`, `Note from ${system.note_by}:`)}</Mark> {system.note}
          </p>
        )}
      </div>
    );
  }
  const review = hypothesis.review;
  const who = (operator ?? "").trim();
  const decide = (decision: "confirmed" | "discarded") => {
    setError(null);
    api
      .reviewHypothesis({
        decision,
        parameter: excursion.parameter,
        excursion_start: excursion.start,
        reason: reason.trim(),
        decided_by: who,
      })
      .then(() => {
        setReason("");
        onReviewed();
      })
      .catch((cause: unknown) => setError(requestOutcome(cause)));
  };
  return (
    <div className="hypothesis-review">
      {review !== null && (
        <p>
          {review.decision === "confirmed" ? (
            <Mark pictogram={uiPictogram("confirm")}>{tr("Confirmada", "Confirmed")}</Mark>
          ) : (
            <Mark pictogram={uiPictogram("reject")}>{tr("Descartada", "Discarded")}</Mark>
          )}{" "}
          {tr("por", "by")} {review.decided_by}: {review.reason}
          {review.recovery !== undefined && (
            <span className="secondary">
              {" "}
              ·{" "}
              {review.recovery.habitat_within_limit
                ? tr("hábitat de nuevo dentro de límite", "habitat back within limit")
                : tr("hábitat todavía fuera de límite", "habitat still outside limit")}
              {review.recovery.still_affected.length > 0
                ? tr(
                    ` · siguen fuera de nominal: ${review.recovery.still_affected.join(", ")}`,
                    ` · still off nominal: ${review.recovery.still_affected.join(", ")}`,
                  )
                : tr(" · ningún afectado sigue fuera de nominal", " · no affected crew member is still off nominal")}
            </span>
          )}
        </p>
      )}
      {operator !== undefined && (
        <div className="inline-form">
          <input
            value={reason}
            maxLength={500}
            placeholder={tr("motivo (p. ej. qué dijo el segundo sensor)", "reason (e.g. what the second sensor said)")}
            aria-label={tr("Motivo de la revisión", "Reason for the review")}
            onChange={(event) => setReason(event.target.value)}
          />
          <Command
            concept="confirm"
            disabled={who === "" || reason.trim() === ""}
            onClick={() => decide("confirmed")}
          >
            {tr("Confirmar", "Confirm")}
          </Command>
          <Command
            concept="reject"
            disabled={who === "" || reason.trim() === ""}
            onClick={() => decide("discarded")}
          >
            {tr("Descartar", "Discard")}
          </Command>
          {error !== null && <MarkOf mark={error.mark}>{error.text}</MarkOf>}
        </div>
      )}
    </div>
  );
}
