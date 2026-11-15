import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { type GroundNote, type GroundNotes, groundNotesApi } from "../lib/api";
import { useArrivalCheck } from "../lib/arrival";
import { type CommsStatus, commsMark } from "../lib/commsStatus";
import { formatMinutes, formatNumber, formatUtc } from "../lib/format";
import { noteKindMark } from "../lib/groundNotes";
import {
  EMPTY_MARK,
  LOADING_MARK,
  MISSING_MARK,
  type RequestOutcome,
  UNAVAILABLE_MARK,
  requestOutcome,
} from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { markTint } from "./TimelinePieces";

/**
 * Las notas de Tierra en la consola de tripulación (§5.38.1): lo que el equipo de Tierra ha
 * firmado para este tripulante o para toda la tripulación, y que ya ha llegado.
 *
 * Por qué existe: la conversación de ideación pone una línea de ida y vuelta con Tierra (L182,
 * L190) y hasta aquí solo había la de bajada. Llega lo firmado hace más de un tiempo de luz: se
 * pide con el corte del reloj (`arrivalCut` por `useArrivalCheck`, la misma cuenta con que la
 * consola de Tierra corta lo que baja), cada 30 s; lo que va en camino no se pide ni se cuenta.
 * El texto es el firmado, tal cual: la interfaz no lo redacta ni lo resume, y no es una orden
 * (invariante 7; el backend rechaza al firmar lo que manda).
 */
export function GroundNotesPanel({
  subject,
  oneWayMinutes,
  comms,
}: {
  subject: string;
  oneWayMinutes: number | null;
  /** El estado del retardo del backend (`comms_status`): sin él, «Sin efemérides» como antes. */
  comms?: CommsStatus | undefined;
}) {
  // Lo cargado va con el tripulante del que es: al cambiar de tripulante no se pintan ni un
  // instante las notas del anterior bajo el nuevo.
  const [loaded, setLoaded] = useState<{ subject: string; body: GroundNotes } | null>(null);
  const [failed, setFailed] = useState<{ subject: string; outcome: RequestOutcome } | null>(null);
  const { checkKey, cutNow } = useArrivalCheck(oneWayMinutes);

  useEffect(() => {
    let alive = true;
    groundNotesApi
      .list(subject, cutNow())
      .then((body) => {
        if (!alive) return;
        setLoaded({ subject, body });
        setFailed(null);
      })
      .catch((reason: unknown) => {
        if (alive) setFailed({ subject, outcome: requestOutcome(reason) });
      });
    return () => {
      alive = false;
    };
  }, [subject, checkKey, cutNow]);

  const data = loaded?.subject === subject ? loaded.body : null;
  const unavailable = failed?.subject === subject ? failed.outcome : null;
  return <GroundNotesOnBoard data={data} unavailable={unavailable} oneWayMinutes={oneWayMinutes} comms={comms} />;
}

/**
 * Cuántas notas de cada clase han llegado, en el orden en que aparece cada clase, con la palabra
 * que el backend dio a la primera (`kind_display`): la interfaz no la redacta.
 */
function kindTally(notes: readonly GroundNote[]): { kind: string; display: string; count: number }[] {
  const counts = new Map<string, { display: string; count: number }>();
  for (const note of notes) {
    const entry = counts.get(note.kind);
    if (entry === undefined) counts.set(note.kind, { display: note.kind_display, count: 1 });
    else entry.count += 1;
  }
  return [...counts].map(([kind, { display, count }]) => ({ kind, display, count }));
}

/**
 * Solo pinta. Separado de la carga para poder probar lo que se lee en pantalla.
 *
 * La última firmada, arriba. Un refresco que falla no borra lo que ya había llegado: se sigue
 * viendo, con la marca de lo que falló encima.
 *
 * Tablero (decisión del usuario, 2026-11-07): sobre la lista, las píldoras de recuento —las
 * llegadas, cada clase con su signo y su palabra del backend, y las que no se enseñan con la marca
 * gris de «no disponible»—, solo en la concha de la maqueta (`BoardOnly`) y solo con cifras: a
 * quién va y quién firma siguen en cada nota, donde la privacidad ya los tapa.
 */
export function GroundNotesOnBoard({
  data,
  unavailable,
  oneWayMinutes,
  comms,
}: {
  data: GroundNotes | null;
  unavailable: RequestOutcome | null;
  oneWayMinutes: number | null;
  comms?: CommsStatus | undefined;
}) {
  const board = useLook() === "reference";
  return (
    <section data-ui="ground-notes-onboard" className="panel" aria-label="Notas de Tierra">
      <PanelTitle concept="groundNotes">Notas de Tierra</PanelTitle>
      {oneWayMinutes === null && comms?.state === "not_applicable" ? (
        <p className="secondary">
          {/* Un perfil sin objetivo de efemérides (2026-11-11): no falta nada, no hay retardo que
              aplicar. Gris «no disponible» con la frase del backend, no el cian de lo ausente. */}
          <MarkOf mark={commsMark(comms.state)}>
            {comms.text} Se muestra todo lo firmado en Tierra.
          </MarkOf>
        </p>
      ) : oneWayMinutes === null ? (
        <p className="secondary">
          <MarkOf mark={MISSING_MARK}>
            {comms?.word ?? "Sin efemérides"}: no se puede aplicar el retardo. Se muestra todo lo firmado en Tierra.
          </MarkOf>
        </p>
      ) : (
        <p className="secondary">
          {/* El signo del retardo con Tierra, el de la franja y del tránsito de la ecografía. */}
          <Mark pictogram={uiPictogram("lightTime")}>
            Llega lo firmado en Tierra hace más de <span className="num">{formatMinutes(oneWayMinutes)}</span>;
            lo posterior está en camino.
          </Mark>
        </p>
      )}
      {unavailable !== null && (
        <p>
          <MarkOf mark={unavailable.mark}>
            {data === null ? "No se pudieron leer las notas" : "No se pudo actualizar"}: {unavailable.text}
          </MarkOf>
        </p>
      )}
      {data === null ? (
        unavailable === null && (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>Leyendo las notas…</MarkOf>
          </p>
        )
      ) : (
        <>
          <BoardOnly>
            {(data.notes.length > 0 || data.withheld > 0) && (
              <ul className="board-tally" aria-label="Notas por clase">
                {data.notes.length > 0 && (
                  <li className="ref-pill board-pill">
                    <Mark pictogram={uiPictogram("groundNotes")}>llegadas</Mark>{" "}
                    <span className="num">{formatNumber(data.notes.length)}</span>
                  </li>
                )}
                {kindTally(data.notes).map((entry) => (
                  <li key={entry.kind} className="ref-pill board-pill">
                    <MarkOf mark={noteKindMark(entry.kind)}>{entry.display}</MarkOf>{" "}
                    <span className="num">{formatNumber(entry.count)}</span>
                  </li>
                ))}
                {/* Lo no enseñado: el gris de «no disponible» también en el filete, como su marca (`markTint`). */}
                {data.withheld > 0 && (
                  <li className="ref-pill board-pill" style={markTint(UNAVAILABLE_MARK)}>
                    <MarkOf mark={UNAVAILABLE_MARK}>no enseñadas</MarkOf>{" "}
                    <span className="num">{formatNumber(data.withheld)}</span>
                  </li>
                )}
              </ul>
            )}
          </BoardOnly>
          {data.notes.length === 0 ? (
            <p className="secondary ground-notes-empty">
              <MarkOf mark={EMPTY_MARK}>Ninguna nota de Tierra ha llegado.</MarkOf>
            </p>
          ) : (
            // Tablero (2026-11-08): las filas de «Notas / bitácora» de la muestra, la hora de firma a
            // la izquierda y la nota a la derecha. Nada se pliega: la clase con su marca, a quién va,
            // el texto firmado tal cual y quién lo firmó siguen a la vista. En la clásica, como antes.
            <ul className={board ? "ground-notes ground-notes-board" : "ground-notes"}>
              {[...data.notes].reverse().map((note) => {
                const signedAt = <span className="num">{formatUtc(new Date(note.signed_at))}</span>;
                const lines = (
                  <>
                    <p>
                      <MarkOf mark={noteKindMark(note.kind)}>{note.kind_display}</MarkOf>{" "}
                      <span className="secondary">· para {note.addressed_to_display}</span>
                    </p>
                    <p className="ground-note-text">{note.text}</p>
                    <p className="secondary">
                      Firmada en Tierra por {note.signed_by}
                      {board ? null : <>, {signedAt}</>}
                    </p>
                  </>
                );
                return (
                  <li key={note.ledger_index}>
                    {board ? (
                      <>
                        <span className="secondary ground-note-time">{signedAt}</span>
                        <div className="ground-note-body">{lines}</div>
                      </>
                    ) : (
                      lines
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {data.withheld_note !== null && (
            <p>
              <MarkOf mark={UNAVAILABLE_MARK}>{data.withheld_note}</MarkOf>
            </p>
          )}
          {/* La base de lo que llega es una frase de regla: detrás de «Ver detalle» en el tablero. */}
          <BoardDetail label="qué llega">
            <p className="secondary">{data.basis}</p>
          </BoardDetail>
        </>
      )}
    </section>
  );
}
