import { useState } from "react";

import { declineState, decisionNote, DECLINE_REASON_MAX } from "../advisor/recommendation";
import { RequestWarning } from "../advisor/RequestWarning";
import type { Recommendation } from "../lib/api";
import { tr } from "../lib/i18n";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { Command } from "./Command";
import { FieldLabel } from "./FieldLabel";
import { Mark } from "./Mark";
import { OperatorInput } from "./OperatorInput";
import "./adoptControls.css";

/**
 * «Adoptar» y «No adoptar» en las listas compactas de los tableros (Radiación, Aislamiento,
 * Gravedad, Distancia y nodos).
 *
 * Por qué existe: esas pestañas pintaban las recomendaciones del backend como filas con una marca
 * de «hecho» y ningún mando, y parecían pulsables sin serlo («que si pulso el botón pasen cosas»).
 * La decisión ya estaba resuelta en «Peligros y alertas» (`RecommendationCard`): adoptar es una
 * decisión humana firmada (especificación §14) y decir que no también, con su motivo (§2). Aquí se
 * ofrece la misma decisión con las mismas reglas —sin quien firma no hay mando; sin motivo no hay
 * «no»; lo adoptado y con seguimiento abierto no se vuelve a ofrecer— y por las mismas rutas
 * (`/countermeasures/adopt`, `/countermeasures/decline`), que firman en el ledger. La interfaz no
 * redacta nada clínico: la nota de lo decidido es el texto del backend.
 *
 * La parte con estado (`AdoptControls`) solo guarda el formulario; lo que se pinta está en
 * `AdoptControlsView`, sin ganchos, para que la prueba recorra el árbol y pulse sin DOM.
 */

/** Lo que un tablero necesita para ofrecer la decisión: lo da la consola de tripulación. */
export interface BoardDecisions {
  /** El tripulante de la consola: el formulario de cada fila va con él. */
  subject: string;
  /** Quien está en consola (el mismo de «Peligros y alertas», `useOperator`). */
  operator: string;
  setOperator: (value: string) => void;
  /** Con la privacidad, el campo de quien firma sale del foco y del lector (`OperatorInput`). */
  privacy: boolean;
  /** Las contramedidas con un seguimiento abierto. */
  following: ReadonlySet<string>;
  adopt: (countermeasureId: string, by: string) => Promise<void>;
  decline: (countermeasureId: string, by: string, reason: string) => Promise<void>;
}

/** El formulario de una fila: si se está diciendo que no, el motivo, si espera respuesta y el fallo. */
export interface AdoptFormState {
  declining: boolean;
  reason: string;
  busy: boolean;
  error: RequestOutcome | null;
}

export const ADOPT_FORM_IDLE: AdoptFormState = { declining: false, reason: "", busy: false, error: null };

type Update = (change: (previous: AdoptFormState) => AdoptFormState) => void;

/**
 * Los mandos de una recomendación, con su formulario. Sin contramedida no pinta nada.
 *
 * El formulario va con su tripulante y su contramedida (la `key` de dentro), no con el sitio de la
 * fila: si el estado releído pone otra recomendación en el mismo hueco, o la consola pasa a otro
 * tripulante, un motivo escrito para una no se firma para otra.
 */
export function AdoptControls({ item, decide }: { item: Recommendation; decide: BoardDecisions }) {
  const id = item.countermeasure?.id ?? "";
  return <AdoptControlsForm key={`${decide.subject}|${item.domain}|${id}`} item={item} decide={decide} />;
}

function AdoptControlsForm({ item, decide }: { item: Recommendation; decide: BoardDecisions }) {
  const [form, setForm] = useState<AdoptFormState>(ADOPT_FORM_IDLE);
  return <AdoptControlsView item={item} decide={decide} form={form} update={setForm} />;
}

export function AdoptControlsView({
  item,
  decide,
  form,
  update,
}: {
  item: Recommendation;
  decide: BoardDecisions;
  form: AdoptFormState;
  update: Update;
}) {
  const measure = item.countermeasure;
  if (measure === null) return null;
  const who = decide.operator.trim();
  const adopted = decide.following.has(measure.id);
  const note = decisionNote(item);
  const declining = declineState({
    hasHandler: true,
    adopted,
    operator: decide.operator,
    reason: form.reason,
    busy: form.busy,
  });
  const run = (request: Promise<void>, after: Partial<AdoptFormState>) => {
    update((previous) => ({ ...previous, busy: true, error: null }));
    request
      .then(() => update((previous) => ({ ...previous, ...after })))
      .catch((cause: unknown) => update((previous) => ({ ...previous, error: requestOutcome(cause) })))
      .finally(() => update((previous) => ({ ...previous, busy: false })));
  };
  if (adopted) {
    return (
      <div className="adopt-controls" inert={decide.privacy}>
        <Mark pictogram="check" className="secondary">
          {tr("Adoptada: en seguimiento.", "Adopted: in follow-up.")}
        </Mark>
      </div>
    );
  }
  // Sin quien firma, la misma frase que el formulario del «no» (`declineState`).
  const unsigned = who === "" ? (declining.missing ?? undefined) : undefined;
  return (
    // Con la privacidad, fuera del foco y del lector, como los paneles que tapa (`OperatorInput`):
    // la nota de lo decidido nombra a quien firmó y el motivo es texto libre.
    <div className="adopt-controls" inert={decide.privacy}>
      {/* Lo decidido antes, con el texto del backend: no retira la recomendación ni el mando. */}
      {note !== null && (
        <span className="adopt-note" title={note.meaning}>
          <Mark pictogram="slash-circle">{note.text}</Mark>
        </span>
      )}
      {form.declining ? (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!declining.ready) return;
            run(decide.decline(measure.id, who, form.reason.trim()), { declining: false, reason: "" });
          }}
        >
          <input
            value={form.reason}
            maxLength={DECLINE_REASON_MAX}
            onChange={(event) => {
              const reason = event.target.value;
              update((previous) => ({ ...previous, reason }));
            }}
            placeholder={tr("motivo de no adoptarla", "reason for not adopting it")}
            aria-label={tr("Motivo de no adoptarla", "Reason for not adopting it")}
          />
          <Command concept="decline" type="submit" disabled={!declining.ready} title={declining.missing ?? undefined}>
            {tr("No adoptar", "Do not adopt")}
          </Command>
          <Command
            concept="cancel"
            type="button"
            disabled={form.busy}
            onClick={() => update((previous) => ({ ...previous, declining: false, reason: "", error: null }))}
          >
            {tr("Cancelar", "Cancel")}
          </Command>
        </form>
      ) : (
        <>
          <Command
            concept="adopt"
            type="button"
            disabled={form.busy || who === ""}
            title={unsigned}
            onClick={() => run(decide.adopt(measure.id, who), {})}
          >
            {tr("Adoptar", "Adopt")}
          </Command>
          <Command
            concept="decline"
            type="button"
            disabled={form.busy || who === ""}
            title={unsigned}
            onClick={() => update((previous) => ({ ...previous, declining: true, error: null }))}
          >
            {tr("No adoptar", "Do not adopt")}
          </Command>
        </>
      )}
      {form.error !== null && <RequestWarning outcome={form.error} />}
    </div>
  );
}

/**
 * Quien firma, una vez por lista y solo si hay algo que decidir: los tableros no tenían dónde
 * escribirlo y, sin él, los mandos quedarían apagados sin remedio.
 */
export function BoardOperator({ items, decide }: { items: readonly Recommendation[]; decide: BoardDecisions }) {
  const open = items.some((item) => item.countermeasure !== null && !decide.following.has(item.countermeasure.id));
  if (!open) return null;
  return (
    <FieldLabel concept="person" className="operator adopt-operator">
      {tr("Firma", "Signed by")}{" "}
      <OperatorInput value={decide.operator} onChange={decide.setOperator} privacy={decide.privacy} />
    </FieldLabel>
  );
}
