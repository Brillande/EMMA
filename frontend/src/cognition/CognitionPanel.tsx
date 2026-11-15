import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import { Loading, Unavailable } from "../components/Unavailable";
import { positionMark } from "../diary/position";
import {
  type CognitionProtocol,
  type CognitionRecordedSession,
  type CognitionSubmitted,
  type CognitionTestSpec,
  type InstrumentStatement,
  cognitionApi,
} from "../lib/api";
import { formatNumber, formatUtc } from "../lib/format";
import {
  EMPTY_MARK,
  LOADING_MARK,
  OK_MARK,
  REFUSED_MARK,
  recordedByMark,
  type RequestOutcome,
  requestOutcome,
} from "../lib/marks";
import { useOperator } from "../lib/operator";
import type { Sign } from "../lib/uiMarks";
import { cited } from "../pvt/published";
import { type Draft, check, prepare } from "./draft";

/**
 * La batería Cognition de NASA: las puntuaciones de una sesión, copiadas en la consola.
 *
 * Las pruebas las pasa y las puntúa el programa de la batería, que es de NASA: EMMA no las
 * reimplementa. Aquí se copian las cifras que ese programa da al acabar, se envían a
 * `POST /api/cognition/console`, que las firma en el registro con quién teclea, y se enseña lo
 * que quedó firmado. Qué mide cada prueba va con la frase de su fuente, en su idioma, y de la
 * que no hay frase leída se dice; todo el texto lo da el backend (`GET /api/cognition/protocol`).
 *
 * Son indicadores descriptivos: no se pintan con color según el valor ni se comparan con nada.
 * La PVT, décima prueba de la batería, tiene su propio panel; aquí solo se remite a él.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta, las puntuaciones de la
 * última sesión del registro (`sessions[0]`, la primera fila de la tabla) van además en la tira de
 * cifras de la maqueta (`.ref-stats`, la de «Rutas espaciales» de «Inicio»): la sigla de la prueba y
 * la palabra de su medida como rótulo, `value_text` tal cual como cifra. Sin color y sin comparar; en
 * cursiva (`.stale`) si la relectura falló, como la tabla.
 *
 * Una pantalla por sección (2026-11-08): en el tablero la última sesión va arriba (la tabla, en «Ver
 * detalle»), cada prueba es una tarjeta baja con sus campos —la medida como rótulo visible, el nombre
 * entero para el lector de pantalla, el rango siempre a la vista— y lo que se lee (qué es la batería,
 * qué mide cada prueba, con qué se firma) en dos «Ver detalle». La clásica conserva su orden.
 */
export function CognitionPanel({ subject }: { subject: string }) {
  const [protocol, setProtocol] = useState<CognitionProtocol | null>(null);
  // `null` hasta que el registro se ha leído: una lista vacía es «no hay sesiones».
  const [sessions, setSessions] = useState<CognitionRecordedSession[] | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [sending, setSending] = useState(false);
  const [submitted, setSubmitted] = useState<CognitionSubmitted | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);
  // Dos lecturas, dos avisos: el éxito de una no borra el fallo de la otra.
  const [protocolDown, setProtocolDown] = useState<RequestOutcome | null>(null);
  const [sessionsDown, setSessionsDown] = useState<RequestOutcome | null>(null);
  const [operator, setOperator] = useOperator();
  // Cambia con el tripulante: una respuesta que llega tarde no se pinta a otro.
  const epoch = useRef(0);

  const loadSessions = useCallback(() => {
    const asked = epoch.current;
    const mine = () => asked === epoch.current;
    cognitionApi
      .sessions(subject)
      .then((recorded) => {
        if (!mine()) return;
        setSessions(recorded.sessions);
        setSessionsDown(null);
      })
      .catch((reason: unknown) => {
        if (mine()) setSessionsDown(requestOutcome(reason));
      });
  }, [subject]);

  useEffect(() => {
    cognitionApi
      .protocol()
      .then((offered) => {
        setProtocol(offered);
        setProtocolDown(null);
      })
      .catch((reason: unknown) => setProtocolDown(requestOutcome(reason)));
  }, []);
  useEffect(loadSessions, [loadSessions]);

  // Lo tecleado es de quien estaba en pantalla: al cambiar de tripulante se descarta.
  useEffect(() => {
    return () => {
      epoch.current += 1;
      setSessions(null);
      setSessionsDown(null);
      setDraft({});
      setSubmitted(null);
      setFailure(null);
    };
  }, [subject]);

  const submit = () => {
    if (protocol === null || sending) return;
    const { body } = prepare(protocol, draft, subject, operator);
    if (body === null) return;
    const sentAt = epoch.current;
    const mine = () => epoch.current === sentAt;
    setSending(true);
    setSubmitted(null);
    setFailure(null);
    cognitionApi
      .submit(body)
      .then((result) => {
        if (!mine()) return;
        setSubmitted(result);
        setDraft({});
      })
      // El rechazo del backend se enseña tal cual; lo que quedó lo dice la lista de abajo.
      .catch((reason: unknown) => {
        if (mine()) setFailure(requestOutcome(reason));
      })
      .finally(() => {
        setSending(false);
        if (mine()) loadSessions();
      });
  };

  return (
    <CognitionView
      protocol={protocol}
      sessions={sessions}
      draft={draft}
      onDraft={(key, value) => setDraft((current) => ({ ...current, [key]: value }))}
      subject={subject}
      operator={operator}
      onOperator={setOperator}
      sending={sending}
      submitted={submitted}
      failure={failure}
      unavailable={protocolDown ?? sessionsDown}
      onSubmit={submit}
    />
  );
}

const TITLE = "Batería Cognition (NASA)";

/** La tira de la última sesión: una casilla por puntuación, con la sigla, la medida y la cifra del backend. */
function LastSessionStrip({ session, stale }: { session: CognitionRecordedSession; stale: boolean }) {
  if (session.values.length === 0) return null;
  return (
    <dl className={stale ? "ref-stats cognition-board stale" : "ref-stats cognition-board"} role="group" aria-label="Última sesión en el registro">
      {session.values.map((value) => (
        <div key={value.key}>
          <dt>
            <span className="cognition-sigla">{value.sigla}</span> {value.measure_display}
          </dt>
          <dd className="num">{value.value_text}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Una frase de la fuente, en su idioma, con su sección, su cita y cuándo se leyó. */
function CitedView({ statement }: { statement: InstrumentStatement }) {
  const item = cited(statement);
  return (
    <>
      <div>
        <q lang="en">{item.quote}</q>
      </div>
      <div className="secondary">
        <span lang="en">{item.origin}</span>
        {item.url !== null && <span className="num url"> · {item.url}</span>}
      </div>
    </>
  );
}

/** Solo pinta. Separado del estado para poder probar lo que se lee en pantalla. */
export function CognitionView({
  protocol,
  sessions,
  draft,
  onDraft,
  subject,
  operator,
  onOperator,
  sending,
  submitted,
  failure,
  unavailable,
  onSubmit,
}: {
  protocol: CognitionProtocol | null;
  /** Las sesiones del registro; `null` si aún no se han leído o la lectura falló. */
  sessions: CognitionRecordedSession[] | null;
  draft: Draft;
  onDraft: (key: string, value: string) => void;
  subject: string;
  /** Quién está en la consola: se firma con cada puntuación. */
  operator: string;
  onOperator: (value: string) => void;
  sending: boolean;
  submitted: CognitionSubmitted | null;
  failure: RequestOutcome | null;
  unavailable: RequestOutcome | null;
  onSubmit: () => void;
}) {
  // En el tablero: la última sesión arriba, las pruebas en tarjetas bajas a tres por fila y lo que
  // se lee (qué es la batería, sus límites, qué mide cada prueba) en «Ver detalle».
  const board = useLook() === "reference";
  if (protocol === null) {
    return (
      <section data-ui="cognition" className="panel" aria-label={TITLE}>
        <PanelTitle concept="protocol">{TITLE}</PanelTitle>
        {unavailable !== null ? <Unavailable outcome={unavailable} /> : <Loading />}
      </section>
    );
  }

  const prepared = prepare(protocol, draft, subject, operator);
  const send = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };
  // Mientras se envía, el mando enseña la marca de «cargando»; el botón es el mismo.
  const submitSign: Sign =
    sending && LOADING_MARK.pictogram !== null ? { pictogram: LOADING_MARK.pictogram } : { concept: "register" };

  // Qué es la batería y lo que quedó en el registro: en la clásica, en su sitio de siempre; en el
  // tablero, lo segundo arriba y lo primero en su «Ver detalle».
  const about = (
    <>
      <p>{protocol.identity}</p>
      <p className="secondary">{protocol.scope}</p>

      <PanelTitle as="h3" concept="limits">
        Límites de este registro
      </PanelTitle>
      <ul>
        {protocol.limits.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>

      <Fold data-ui="cognition-source" concept="sourceText" label="La batería, según lo leído">
        <ul className="evidence">
          {protocol.battery.map((statement) => (
            <li key={statement.id}>
              {statement.label}
              <CitedView statement={statement} />
            </li>
          ))}
        </ul>
        <PanelTitle as="h4" concept="searchedNotFound">
          Buscado y no encontrado, o no leído
        </PanelTitle>
        <ul className="evidence">
          {protocol.not_found.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </Fold>
    </>
  );
  const provenance = (
    <>
      <p className="secondary">
        Se firma como{" "}
        <ObservationTypeBadge
          type={protocol.provenance.observation_type}
          context={protocol.provenance.evidence_context}
        />{" "}
        · fuente: {protocol.provenance.source_display}
      </p>
      <p className="secondary">{protocol.provenance.effective_note}</p>
    </>
  );
  const operatorNote = (
    <p className="secondary" id="cognition-operator-note">
      {protocol.recorded_by.note}
    </p>
  );
  const history = (
    <>
      <PanelTitle as="h3" concept="history">
        Últimas sesiones en el registro
      </PanelTitle>
      {/* Sin leer el registro no se dice que esté vacío: lo que falló ya lo dice el aviso. */}
      {sessions === null ? null : sessions.length === 0 ? (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>Ninguna sesión de este tripulante en el registro.</MarkOf>
        </p>
      ) : (
        <>
        {/* Tablero: las puntuaciones de la última sesión en la tira de cifras, encima de la tabla;
            `sessions[0]` es la primera fila. Solo en la concha de la maqueta. */}
        {sessions[0] !== undefined && (
          <BoardOnly>
            <LastSessionStrip session={sessions[0]} stale={unavailable !== null} />
          </BoardOnly>
        )}
        <BoardDetail label="tabla de sesiones">
        <div className="quality-table">
          <table className="ledger">
            <thead>
              <tr>
                <Th concept="time">Hora</Th>
                <Th concept="value">Puntuaciones</Th>
                <Th concept="provenance">Procedencia</Th>
                <Th concept="person">{protocol.recorded_by.label}</Th>
                <Th concept="state">En el estado</Th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((item) => (
                <tr key={`${item.effective}|${item.source}|${item.observation_type}`}>
                  <th scope="row" className="num">
                    {formatUtc(new Date(item.effective))}
                  </th>
                  <td>
                    {item.values.map((value) => (
                      <div key={value.key}>
                        <IndicatorName indicatorKey={value.key} displayEs={value.display_es} />:{" "}
                        <span className="num">{value.value_text}</span>
                      </div>
                    ))}
                  </td>
                  <td>
                    <ObservationTypeBadge type={item.observation_type} context={item.evidence_context} />{" "}
                    · {item.source_display}
                  </td>
                  <td data-recorded-by={item.recorded_by === null ? "missing" : "named"}>
                    <MarkOf mark={recordedByMark(item.recorded_by)}>{item.recorded_by_display}</MarkOf>
                  </td>
                  <td data-position={item.position}>
                    <MarkOf mark={positionMark(item.position)}>{item.position_note}</MarkOf>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </BoardDetail>
        </>
      )}
    </>
  );

  const form = (
    <form className="cognition-form" onSubmit={send} noValidate>
      {protocol.tests.map((test) => (
        <TestBlock key={test.abbrev} test={test} draft={draft} onDraft={onDraft} board={board} />
      ))}

      {!board && provenance}

      <FieldLabel concept="person" className="operator">
        {protocol.recorded_by.label}{" "}
        <input
          value={operator}
          maxLength={64}
          autoComplete="off"
          aria-describedby="cognition-operator-note"
          aria-invalid={prepared.unnamed}
          onChange={(event) => onOperator(event.target.value)}
        />
      </FieldLabel>
      {!board && operatorNote}

      <div className="measure-actions">
        <Command {...submitSign} type="submit" disabled={sending || prepared.body === null}>
          {sending ? "Registrando…" : "Registrar la sesión"}
        </Command>
        {prepared.invalid > 0 && (
          <span className="secondary">
            Hay <span className="num">{formatNumber(prepared.invalid)}</span> campos que no se
            pueden enviar: no se registra ninguno hasta corregirlos.
          </span>
        )}
        {prepared.partial.length > 0 && (
          <span className="secondary" data-cognition-partial="">
            Pruebas a medias: {prepared.partial.join(", ")}. Cada prueba se registra con todas sus
            puntuaciones.
          </span>
        )}
        {prepared.empty && (
          <span className="secondary">Ninguna puntuación escrita: no hay nada que registrar.</span>
        )}
        {prepared.unnamed && (
          <span className="secondary">
            Falta el nombre de quien está en la consola: sin él no se registra nada.
          </span>
        )}
      </div>
      {/* Tablero: qué mide cada prueba y qué es cada cifra, con qué se firma y quién, al pie. */}
      {board && (
        <BoardDetail label="qué mide cada prueba y con qué se firma" className="cognition-notes">
          {protocol.tests.map((test) => (
            <TestNotes key={test.abbrev} test={test} />
          ))}
          {provenance}
          {operatorNote}
        </BoardDetail>
      )}
    </form>
  );

  return (
    <section data-ui="cognition" className="panel" aria-label={protocol.title}>
      <PanelTitle concept="protocol">{protocol.title}</PanelTitle>
      {board ? (
        <>
          {history}
          <BoardDetail label="qué es la batería, sus límites y su fuente">{about}</BoardDetail>
        </>
      ) : (
        about
      )}

      {board ? (
        // Tablero (quinta ronda, 2026-11-08): las diez tarjetas para anotar una sesión, quién está
        // en la consola y «Registrar la sesión» medían 780 px, la cuarta parte de la pestaña; es un
        // formulario secundario y se pliega entero en su «Ver detalle» (el del diario, el principal,
        // no). Lo que quedó en el registro sigue arriba, y lo que responde el backend, debajo.
        <BoardDetail label="anotar una sesión" className="cognition-entry">
          {form}
        </BoardDetail>
      ) : (
        form
      )}

      <div role="status" aria-live="polite">
        {submitted !== null && (
          <p className="secondary">
            <MarkOf mark={OK_MARK}>Registrado:</MarkOf>{" "}
            <span className="num">{formatNumber(submitted.keys.length)}</span> puntuaciones, en los
            asientos <span className="num">{submitted.recorded.map((index) => formatNumber(index)).join(", ")}</span>.
            {/* En el tablero lo registrado va encima del formulario; en la clásica, debajo. */}
            {board ? "Arriba" : "Abajo"}, tal como quedó en el registro.
          </p>
        )}
        {failure !== null && (
          <p role="alert">
            <MarkOf mark={failure.mark}>El backend no registró la sesión: {failure.text}</MarkOf>
          </p>
        )}
        {unavailable !== null && <Unavailable outcome={unavailable} />}
      </div>

      {!board && history}
    </section>
  );
}

/** Qué mide una prueba: su frase leída, o la nota del backend de que no la hay. */
function Measures({ test }: { test: CognitionTestSpec }) {
  return test.measures !== null ? (
    <CitedView statement={test.measures} />
  ) : (
    test.measures_note !== null && <p className="secondary">{test.measures_note}</p>
  );
}

/** «Qué es cada cifra»: la frase leída de cada puntuación de la prueba. */
function Figures({ test }: { test: CognitionTestSpec }) {
  if (test.fields.length === 0) return null;
  return (
    <Fold data-ui="cognition-figures" concept="sourceText" label="Qué es cada cifra">
      <ul className="evidence">
        {test.fields.map((field) => (
          <li key={field.key}>
            {field.measure_display}: {field.statement.label}
            <CitedView statement={field.statement} />
          </li>
        ))}
        {test.no_accuracy !== null && (
          <li key={test.no_accuracy.id}>
            {test.no_accuracy.label}
            <CitedView statement={test.no_accuracy} />
          </li>
        )}
      </ul>
    </Fold>
  );
}

/** En el tablero, lo que se lee de una prueba va al detalle común del pie, con su sigla delante. */
function TestNotes({ test }: { test: CognitionTestSpec }) {
  return (
    <div className="cognition-test-notes">
      <p>
        <strong>{test.sigla}</strong>{" "}
        <span className="secondary" lang="en">
          {test.name}
        </span>
      </p>
      <Measures test={test} />
      <Figures test={test} />
    </div>
  );
}

/**
 * Una prueba: qué mide, con su frase, y sus puntuaciones; o, la PVT, a dónde se va. En el tablero,
 * solo el título y sus campos (con la medida de cada uno como rótulo visible y el nombre entero para
 * el lector de pantalla); lo que se lee, en `TestNotes`.
 */
function TestBlock({
  test,
  draft,
  onDraft,
  board = false,
}: {
  test: CognitionTestSpec;
  draft: Draft;
  onDraft: (key: string, value: string) => void;
  board?: boolean;
}) {
  return (
    <article data-cognition-test={test.abbrev} style={board ? undefined : { marginTop: 12 }}>
      <PanelTitle as="h4" concept="measure">
        <span className="num">{formatNumber(test.order)}</span>. {test.sigla}{" "}
        <span className="secondary" lang="en">
          {test.name}
        </span>
      </PanelTitle>
      {!board && <Measures test={test} />}
      {!test.recorded_here && test.console_note !== null && <p>{test.console_note}</p>}
      {test.fields.map((field) => {
        const id = `cognition-${field.key}`;
        const result = check(field, draft[field.key] ?? "");
        const invalid = result.state === "invalid";
        return (
          <div key={field.key} className="field-block">
            <label htmlFor={id}>
              {board ? (
                <>
                  <span className="sr-only">{field.display_es}: </span>
                  <IndicatorName indicatorKey={field.key} displayEs={field.measure_display} />
                </>
              ) : (
                <IndicatorName indicatorKey={field.key} displayEs={field.display_es} />
              )}
              {field.unit_display !== "" && <span className="secondary"> ({field.unit_display})</span>}
            </label>{" "}
            <input
              id={id}
              type="text"
              inputMode="decimal"
              autoComplete="off"
              className="num"
              value={draft[field.key] ?? ""}
              aria-describedby={`${id}-hint${invalid ? ` ${id}-error` : ""}`}
              aria-invalid={invalid}
              onChange={(event) => onDraft(field.key, event.target.value)}
            />
            <p className="secondary" id={`${id}-hint`}>
              Rango: <span className="num">{field.range_text}</span>
            </p>
            {invalid && (
              <p id={`${id}-error`} role="alert">
                <MarkOf mark={REFUSED_MARK}>{result.reason}</MarkOf>
              </p>
            )}
          </div>
        );
      })}
      {!board && <Figures test={test} />}
    </article>
  );
}
