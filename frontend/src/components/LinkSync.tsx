import { useState } from "react";

import { type LinkSync, api } from "../lib/api";
import { formatNumber } from "../lib/format";
import { LINK_DOWN_MARK, LINK_OFFSETS_HOURS, backlogMark, linkChange, linkInstant } from "../lib/linkSync";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { uiPictogram } from "../lib/uiMarks";
import { BoardDetail } from "./BoardDetail";
import { BoardOnly } from "./BoardOnly";
import { Command } from "./Command";
import { FieldLabel } from "./FieldLabel";
import { Fold } from "./Fold";
import { Mark, MarkOf } from "./Mark";
import { PanelTitle } from "./PanelTitle";
import { StatTile } from "./StatTile";

/**
 * El enlace con Tierra simulado, a bordo (§5.47): si está caído, cuánto queda pendiente de enviar a
 * Tierra y desde cuándo, y el mando para declararlo caído o restablecido.
 *
 * Por qué existe: la consola de Tierra solo descontaba el tiempo de luz, como si el enlace no se
 * cayera nunca. Ahora una persona lo declara caído desde un instante; lo firmado después espera a
 * bordo y, al restablecerse, baja a Tierra en el orden en que se firmó. Las frases (estado, cola,
 * qué no lo lee, que no se mide) son del backend; aquí solo se elige la marca (`lib/linkSync.ts`).
 *
 * No es la declaración del sistema Comunicaciones del panel de sistemas: esa sigue siendo solo
 * texto (decisión del usuario del 2026-10-21) y el backend lo dice en `not_read_by`.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta, lo pendiente de enviar
 * como cifra grande (`to_send.count`, en asientos del registro, como lo cuenta el aviso de Tierra;
 * un 0 es un recuento real) con la marca de lo que Tierra aún no tiene si hay algo en la cola, y el
 * estado del enlace en su píldora, con la palabra del backend (`state_display`) y la marca de caído
 * si lo está. La frase del backend sigue debajo, intacta; la clásica no monta las piezas.
 */
export function LinkSyncPanel({
  sync,
  referenceTime,
  onDeclared,
}: {
  sync: LinkSync;
  /** La última lectura de a bordo: desde ella se cuentan las horas hacia atrás del instante. */
  referenceTime: string | null;
  /** Tras firmar: relee el estado, y con él el corte de Tierra. */
  onDeclared: () => Promise<void>;
}) {
  const [operator, setOperator] = useOperator();
  const [hoursAgo, setHoursAgo] = useState<number>(0);
  const [note, setNote] = useState("");
  const [error, setError] = useState<RequestOutcome | null>(null);
  // Mientras va un cambio no se pide otro: un doble clic cruzaba dos peticiones (como §5.37.18).
  const [sending, setSending] = useState(false);
  const down = sync.state === "down";
  const pending = backlogMark(sync.to_send.count);

  const declare = async () => {
    setError(null);
    setSending(true);
    try {
      await api.setLinkSync(linkChange(sync, linkInstant(referenceTime, hoursAgo, new Date()), operator, note));
      setNote("");
      setHoursAgo(0);
      await onDeclared();
    } catch (failure) {
      setError(requestOutcome(failure));
    } finally {
      setSending(false);
    }
  };

  const controls = (
    <LinkControls
      down={down}
      sync={sync}
      operator={operator}
      setOperator={setOperator}
      hoursAgo={hoursAgo}
      setHoursAgo={setHoursAgo}
      note={note}
      setNote={setNote}
      sending={sending}
      error={error}
      declare={declare}
    />
  );

  const label = <p className="secondary">{sync.label}</p>;
  const sentence = (
    <p>
      {down ? (
        <MarkOf mark={LINK_DOWN_MARK}>{sync.crew_sentence}</MarkOf>
      ) : pending !== null ? (
        <MarkOf mark={pending}>{sync.crew_sentence}</MarkOf>
      ) : (
        sync.crew_sentence
      )}
    </p>
  );
  // Quinta ronda del lote «muestra» (2026-11-09): con el enlace arriba y nada pendiente, la ficha (0
  // asientos) y la píldora («arriba») ya dicen lo que la frase del backend cuenta en tres renglones;
  // el rótulo y la frase pasan al «Ver detalle», delante del formulario. Caído o con algo pendiente,
  // la frase lleva marca y sigue a la vista. En la clásica el orden es el de siempre: `BoardOnly` no
  // pinta nada y `BoardDetail` pinta sus hijos tal cual.
  const calm = !down && pending === null;
  return (
    <section data-ui="link-sync" className="panel" aria-label="Enlace con Tierra simulado">
      <PanelTitle concept="lightTime">Enlace con Tierra simulado</PanelTitle>
      {!calm && label}
      <BoardOnly>
        <div className="board-row link-board">
          <div className="board-stats">
            <StatTile
              concept="lightTime"
              label="Pendientes de enviar"
              value={sync.to_send.count}
              unit="asientos"
              {...(pending === null ? {} : { status: { mark: pending, word: "Tierra aún no los tiene" } })}
            />
          </div>
          <span className="ref-pill board-pill">
            {down ? (
              <MarkOf mark={LINK_DOWN_MARK}>{sync.state_display}</MarkOf>
            ) : (
              <Mark pictogram={uiPictogram("lightTime")}>{sync.state_display}</Mark>
            )}
          </span>
        </div>
      </BoardOnly>
      {!calm && sentence}
      {/* Lote «muestra» (2026-11-08): con el enlace arriba, el formulario para declararlo caído y
          cómo se cuenta, tras «Ver detalle»; el estado, lo pendiente y la frase del backend con su
          marca, a la vista. Con el enlace caído el mando de restablecerlo es la acción pendiente y
          va a la vista, sin pliegue. */}
      {down ? (
        controls
      ) : (
        <BoardDetail label="declarar el enlace y cómo se cuenta">
          {calm && label}
          {calm && sentence}
          {controls}
        </BoardDetail>
      )}
    </section>
  );
}

function LinkControls({
  down,
  sync,
  operator,
  setOperator,
  hoursAgo,
  setHoursAgo,
  note,
  setNote,
  sending,
  error,
  declare,
}: {
  down: boolean;
  sync: LinkSync;
  operator: string;
  setOperator: (value: string) => void;
  hoursAgo: number;
  setHoursAgo: (value: number) => void;
  note: string;
  setNote: (value: string) => void;
  sending: boolean;
  error: RequestOutcome | null;
  declare: () => Promise<void>;
}) {
  return (
    <>
      <div className="silence-form">
        <FieldLabel concept="person">
          Quién{" "}
          <input value={operator} maxLength={64} onChange={(event) => setOperator(event.target.value)} />
        </FieldLabel>
        <FieldLabel concept="time">
          Desde{" "}
          <select value={hoursAgo} onChange={(event) => setHoursAgo(Number(event.target.value))}>
            {LINK_OFFSETS_HOURS.map((hours) => (
              <option key={hours} value={hours}>
                {hours === 0 ? "la última lectura de a bordo" : `${formatNumber(hours, 0)} h antes de la última lectura`}
              </option>
            ))}
          </select>
        </FieldLabel>
        <FieldLabel concept="note">
          Nota <input value={note} maxLength={300} onChange={(event) => setNote(event.target.value)} />
        </FieldLabel>
        <Command concept="declare" disabled={sending || operator.trim() === ""} onClick={() => void declare()}>
          {down ? "Declarar el enlace restablecido" : "Declarar el enlace caído"}
        </Command>
      </div>
      {error !== null && (
        <p>
          <MarkOf mark={error.mark}>{error.text}</MarkOf>
        </p>
      )}
      <Fold data-ui="link-sync-rule" concept="howToRead" label="Cómo se cuenta y qué no lo lee">
        <p>{sync.rule}</p>
        <p>{sync.instant_basis}</p>
        <p>{sync.not_read_by}</p>
        <p>
          <Mark pictogram={uiPictogram("lightTime")}>{sync.not_measured}</Mark>
        </p>
      </Fold>
    </>
  );
}
