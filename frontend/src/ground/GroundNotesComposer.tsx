import { type FormEvent, useCallback, useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { type GroundNote, type GroundNoteRules, type GroundNotes, groundNotesApi } from "../lib/api";
import { useArrivalCheck } from "../lib/arrival";
import { formatNumber, formatUtc } from "../lib/format";
import { type NoteTransit, noteKindMark, noteTransit } from "../lib/groundNotes";
import {
  EMPTY_MARK,
  LOADING_MARK,
  MISSING_MARK,
  OK_MARK,
  type RequestOutcome,
  type StateMark,
  UNAVAILABLE_MARK,
  mark,
  requestOutcome,
} from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { tr } from "../lib/i18n";

/**
 * Notas de Tierra a bordo, desde la consola de Tierra (§5.38.1): redactar y firmar una nota para
 * el tripulante que se mira o para toda la tripulación, y ver dónde está cada una firmada.
 *
 * Por qué existe: hasta aquí la consola de Tierra era de solo lectura y nada subía (la
 * conversación de ideación, L182 y L190, pide la sincronización en los dos sentidos y la
 * supervisión médica desde Tierra). Es la única escritura de esta consola, con su propia clave de
 * firma. Lo que se puede decir lo decide el backend: información o pregunta, nunca una orden; un
 * texto que manda vuelve con su motivo (422) y se enseña tal cual. Las reglas y su frase vienen
 * del backend (`/api/ground-notes/rules`): la interfaz no las redacta.
 *
 * Lo firmado no cambia nada de lo que se ve en esta consola: no es una lectura ni toca ningún
 * nivel. Llega a bordo un tiempo de luz después de firmarse (`noteTransit`).
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta (`BoardOnly`), bajo el
 * título, las píldoras de cuántas hay firmadas y dónde están (`NotesTally`), con la misma marca que
 * lleva el tránsito de cada una abajo. Sin nombres: ni quién firmó ni para quién.
 *
 * Una pantalla por sección (2026-11-08): el formulario, con las dos frases de las reglas, medía
 * 500 px de los 2725 de la pestaña. En el tablero va detrás de «Ver detalle: Escribir nota a bordo»;
 * las píldoras, lo firmado con su tránsito y los avisos de lectura siguen a la vista. En la clásica,
 * como siempre.
 */
export function GroundNotesComposer({
  subject,
  oneWayMinutes,
}: {
  subject: string;
  oneWayMinutes: number | null;
}) {
  const [rules, setRules] = useState<GroundNoteRules | null>(null);
  const [rulesError, setRulesError] = useState<RequestOutcome | null>(null);
  const [loaded, setLoaded] = useState<{ subject: string; body: GroundNotes } | null>(null);
  const [failed, setFailed] = useState<{ subject: string; outcome: RequestOutcome } | null>(null);
  const [signed, setSigned] = useState(0);
  // Cada 30 s se vuelve a pintar el tránsito («en camino» pasa a «a bordo»); la lista entera se
  // pide sin corte: es lo que Tierra ha firmado.
  const { checkKey } = useArrivalCheck(oneWayMinutes);

  // Las reglas se leen una vez; si fallan, se vuelve a probar en cada vuelta de 30 s: sin ellas
  // no hay formulario, y es la única escritura de esta consola.
  const missingRules = rules === null;
  useEffect(() => {
    if (!missingRules) return;
    let alive = true;
    groundNotesApi
      .rules()
      .then((body) => {
        if (!alive) return;
        setRules(body);
        setRulesError(null);
      })
      .catch((reason: unknown) => {
        if (alive) setRulesError(requestOutcome(reason));
      });
    return () => {
      alive = false;
    };
  }, [missingRules, checkKey]);

  useEffect(() => {
    let alive = true;
    groundNotesApi
      .list(subject)
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
  }, [subject, checkKey, signed]);

  const onSigned = useCallback(() => setSigned((count) => count + 1), []);
  const data = loaded?.subject === subject ? loaded.body : null;
  const unavailable = failed?.subject === subject ? failed.outcome : null;
  // Un solo reloj para las píldoras y las filas: una nota no puede contarse en camino arriba y
  // decirse a bordo abajo por los milisegundos entre dos lecturas.
  const now = Date.now();

  return (
    <section data-ui="ground-notes-composer" className="panel" aria-label={tr("Notas de Tierra a bordo", "Notes from Earth to the crew")}>
      <PanelTitle concept="groundNotes">{tr("Notas a bordo", "Notes to the crew")}</PanelTitle>
      {data !== null && data.notes.length + data.withheld > 0 && (
        <BoardOnly>
          <NotesTally
            notes={data.notes}
            withheld={data.withheld}
            oneWayMinutes={oneWayMinutes}
            now={now}
            stale={unavailable !== null}
          />
        </BoardOnly>
      )}
      {rules === null ? (
        <p className="secondary">
          {rulesError === null ? (
            <MarkOf mark={LOADING_MARK}>{tr("Leyendo las reglas de una nota…", "Reading the rules for a note…")}</MarkOf>
          ) : (
            <MarkOf mark={rulesError.mark}>
              {tr("No se pudieron leer las reglas:", "Could not read the rules:")} {rulesError.text}
            </MarkOf>
          )}
        </p>
      ) : (
        // Con la clave del tripulante: al cambiar de tripulante, el borrador, el destinatario y el
        // último resultado no pasan al siguiente (un borrador para uno no se firma para otro).
        // En el tablero, detrás de su mando: es un formulario secundario (no de alerta) y medía
        // 500 px; lo firmado y dónde está sigue a la vista.
        <BoardDetail label={tr("Escribir nota a bordo", "Write a note to the crew")}>
          <NoteForm key={subject} subject={subject} rules={rules} onSigned={onSigned} />
        </BoardDetail>
      )}
      <GroundNotesSent
        data={data}
        unavailable={unavailable}
        oneWayMinutes={oneWayMinutes}
        now={now}
      />
    </section>
  );
}

function NoteForm({
  subject,
  rules,
  onSigned,
}: {
  subject: string;
  rules: GroundNoteRules;
  onSigned: () => void;
}) {
  const [kind, setKind] = useState<GroundNote["kind"]>(rules.kinds[0]?.code ?? "question");
  const [toAll, setToAll] = useState(false);
  const [text, setText] = useState("");
  const [signedBy, setSignedBy] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<{ mark: StateMark; text: string } | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setOutcome(null);
    groundNotesApi
      .sign({ subject: toAll ? rules.crew_subject : subject, kind, text, signed_by: signedBy })
      .then(() => {
        setText("");
        setOutcome({ mark: OK_MARK, text: tr("Firmada en el registro: sale ahora hacia la nave.", "Signed in the ledger: it is leaving for the ship now.") });
        onSigned();
      })
      .catch((reason: unknown) => setOutcome(requestOutcome(reason)))
      .finally(() => setBusy(false));
  };

  const ready = text.trim() !== "" && signedBy.trim() !== "" && !busy;
  return (
    <form className="silence-form ground-note-form" onSubmit={submit}>
      <p className="secondary">{rules.basis}</p>
      <FieldLabel concept="type">
        {tr("Clase", "Kind")}{" "}
        <select value={kind} onChange={(event) => setKind(event.target.value as GroundNote["kind"])}>
          {rules.kinds.map((item) => (
            <option key={item.code} value={item.code}>
              {item.display}
            </option>
          ))}
        </select>
      </FieldLabel>
      <FieldLabel concept="person">
        {tr("Para", "To")}{" "}
        <select value={toAll ? "all" : "one"} onChange={(event) => setToAll(event.target.value === "all")}>
          <option value="one">{subject}</option>
          <option value="all">{rules.crew_display}</option>
        </select>
      </FieldLabel>
      <FieldLabel concept="note">
        {tr("Texto", "Text")}{" "}
        <textarea
          value={text}
          maxLength={rules.max_length}
          rows={3}
          onChange={(event) => setText(event.target.value)}
        />
      </FieldLabel>
      <p className="secondary">{rules.refused}</p>
      <FieldLabel concept="person">
        {tr("Firma en Tierra", "Signature on Earth")}{" "}
        <input
          value={signedBy}
          maxLength={64}
          onChange={(event) => setSignedBy(event.target.value)}
          placeholder={tr("nombre y puesto", "name and position")}
        />
      </FieldLabel>
      <div>
        <Command concept="register" type="submit" disabled={!ready}>
          {tr("Firmar y enviar", "Sign and send")}
        </Command>
      </div>
      {outcome !== null && (
        <p>
          <MarkOf mark={outcome.mark}>{outcome.text}</MarkOf>
        </p>
      )}
    </form>
  );
}

/**
 * Los tres sitios de una nota firmada, una sola vez: su marca, la palabra corta de su píldora y la
 * frase de su fila. El visto, el signo del tiempo de luz y, sin efemérides, el cian del dato ausente.
 */
const TRANSIT: Readonly<Record<NoteTransit["state"], { mark: StateMark; short: string; long: string }>> = {
  "on-board": { mark: OK_MARK, short: tr("a bordo", "on board"), long: tr("a bordo desde", "on board since") },
  "in-transit": {
    mark: mark(uiPictogram("lightTime"), null),
    short: tr("en camino", "on its way"),
    long: tr("en camino: llega hacia", "on its way: arrives around"),
  },
  unknown: {
    mark: MISSING_MARK,
    short: tr("sin saber cuándo llega", "arrival time unknown"),
    long: tr(
      "sin efemérides no se sabe cuándo llega; a bordo, sin retardo que aplicar, ya se ve",
      "without ephemeris the arrival time is unknown; on board, with no delay to apply, it is already visible",
    ),
  },
};

/** La marca, la palabra y el instante (si se sabe) del tránsito de una nota firmada. */
export function transitMark(transit: NoteTransit): { mark: StateMark; word: string; at: Date | null } {
  const { mark: look, long } = TRANSIT[transit.state];
  return { mark: look, word: long, at: transit.state === "unknown" ? null : transit.at };
}

/**
 * Cuántas notas hay firmadas y cuántas de las que se enseñan están a bordo o todavía en camino, con
 * la marca del tránsito de su fila. «Firmadas» cuenta también las retenidas (`withheld`: llegadas y
 * no enseñadas, que la frase de abajo explica), sin sitio: no se pintan. Solo los sitios que tienen
 * alguna; en cursiva si el último refresco falló (`stale`). Sin nombres de quien firma ni de
 * destinatario.
 */
export function NotesTally({
  notes,
  withheld = 0,
  oneWayMinutes,
  now,
  stale = false,
}: {
  notes: readonly GroundNote[];
  withheld?: number;
  oneWayMinutes: number | null;
  now: number;
  stale?: boolean;
}) {
  const counts = new Map<NoteTransit["state"], number>();
  for (const note of notes) {
    const state = noteTransit(note.signed_at, oneWayMinutes, now).state;
    counts.set(state, (counts.get(state) ?? 0) + 1);
  }
  const order: NoteTransit["state"][] = ["on-board", "in-transit", "unknown"];
  return (
    <ul className="board-tally notes-tally" aria-label={tr("Notas firmadas y dónde están", "Signed notes and where they are")}>
      <li className="ref-pill board-pill">
        <Mark pictogram={uiPictogram("register")} stale={stale}>
          {tr("Firmadas", "Signed")}
        </Mark>{" "}
        <span className="num">{formatNumber(notes.length + withheld)}</span>
      </li>
      {order
        .filter((state) => (counts.get(state) ?? 0) > 0)
        .map((state) => (
          <li key={state} className="ref-pill board-pill">
            <MarkOf mark={TRANSIT[state].mark} stale={stale}>
              {TRANSIT[state].short}
            </MarkOf>{" "}
            <span className="num">{formatNumber(counts.get(state) ?? 0)}</span>
          </li>
        ))}
    </ul>
  );
}

/**
 * Solo pinta lo firmado, la última arriba, con su tránsito. Separado para poder probarlo con un
 * reloj fijo (`now`).
 */
export function GroundNotesSent({
  data,
  unavailable,
  oneWayMinutes,
  now,
}: {
  data: GroundNotes | null;
  unavailable: RequestOutcome | null;
  oneWayMinutes: number | null;
  now: number;
}) {
  return (
    <>
      {unavailable !== null && (
        <p>
          <MarkOf mark={unavailable.mark}>
            {data === null
              ? tr("No se pudieron leer las notas firmadas", "Could not read the signed notes")
              : tr("No se pudo actualizar", "Could not refresh")}
            :{" "}
            {unavailable.text}
          </MarkOf>
        </p>
      )}
      {data !== null &&
        (data.notes.length === 0 ? (
          <p className="secondary">
            <MarkOf mark={EMPTY_MARK}>
              {tr("Ninguna nota firmada para este tripulante.", "No signed note for this crew member.")}
            </MarkOf>
          </p>
        ) : (
          <ul className="ground-notes">
            {[...data.notes].reverse().map((note) => {
              const transit = transitMark(noteTransit(note.signed_at, oneWayMinutes, now));
              return (
                <li key={note.ledger_index}>
                  <p>
                    <MarkOf mark={noteKindMark(note.kind)}>{note.kind_display}</MarkOf>{" "}
                    <span className="secondary">
                      · {tr("para", "to")} {note.addressed_to_display}
                    </span>
                  </p>
                  <p className="ground-note-text">{note.text}</p>
                  <p className="secondary">
                    {tr("Firmada por", "Signed by")} {note.signed_by}, <span className="num">{formatUtc(new Date(note.signed_at))}</span>{" "}
                    ·{" "}
                    <MarkOf mark={transit.mark}>
                      {transit.word}
                      {transit.at !== null && (
                        <>
                          {" "}
                          <span className="num">{formatUtc(transit.at)}</span>
                        </>
                      )}
                    </MarkOf>
                  </p>
                </li>
              );
            })}
          </ul>
        ))}
      {data !== null && data.withheld_note !== null && (
        <p>
          <MarkOf mark={UNAVAILABLE_MARK}>{data.withheld_note}</MarkOf>
        </p>
      )}
      {oneWayMinutes !== null && (
        <p className="secondary">
          <Mark pictogram={uiPictogram("lightTime")}>
            {tr(
              "Una nota llega a bordo un tiempo de luz después de firmarse.",
              "A note reaches the crew one light time after it is signed.",
            )}
          </Mark>
        </p>
      )}
    </>
  );
}
