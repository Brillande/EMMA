import { type ReactNode, useEffect, useState } from "react";

import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { Th } from "../components/Th";
import { Loading, Unavailable } from "../components/Unavailable";
import { type MissionHistory as History, type MissionHistoryCheck, type PriorMissionIn, api } from "../lib/api";
import { parseValue } from "../diary/entry";
import { formatDay, formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import {
  EMPTY_MARK,
  MISSING_MARK,
  OK_MARK,
  type RequestOutcome,
  type StateMark,
  mark,
  requestOutcome,
} from "../lib/marks";

/**
 * El historial misión a misión del tripulante (especificación §3 `mission_history`; decisión del
 * usuario, 2026-10-22, §5.35.19), junto a donde se declara el perfil: nombre, fechas y dosis de
 * cada misión previa.
 *
 * Por qué existe: el perfil solo tenía dos cifras sueltas (cuántas misiones previas y la dosis de
 * carrera previa), y la dosis no se podía cotejar con nada. El historial va **al lado** de esa
 * dosis y no la sustituye: la escala de carrera la sigue leyendo del perfil. Si la suma del
 * historial, o su número de misiones, no casa con el perfil, el backend lo dice con su frase y
 * aquí se pinta tal cual: en amarillo con el triángulo («hay que mirarlo», como las dos firmas que
 * discrepan del borrador); lo que no se puede cotejar porque falta un dato, en cian con su anillo
 * (dato ausente, F.5-1); y lo que casa, con la marca de visto, sin color.
 *
 * El solape con la misión en curso (`overlap`) no es un cotejo con el perfil sino un aviso sobre lo
 * ya firmado, y no va con ellos: va justo debajo de la frase de lo declarado, en su bloque con
 * filete amarillo y el texto del backend tal cual (§5.39.20). Lo que lo separa es la clave, no
 * `matches`. Como el plegable de a bordo va cerrado, su rótulo lleva entonces el triángulo.
 *
 * Los días no se escriben: los calcula el backend entre las dos fechas y dice cómo. Se declara la
 * lista entera (vale la última), así que el formulario arranca con la vigente para corregirla.
 * Plegado: en la consola de tripulación es algo que se declara una vez, no algo que vigilar.
 */
export function MissionHistory({
  subject,
  operator,
  refreshKey,
}: {
  subject: string;
  operator: string;
  refreshKey: string;
}) {
  const [data, setData] = useState<History | null>(null);
  const [unavailable, setUnavailable] = useState<RequestOutcome | null>(null);
  const [version, setVersion] = useState(0);

  // Otro tripulante: lo pintado era del anterior.
  useEffect(() => {
    setData(null);
    setUnavailable(null);
  }, [subject]);

  useEffect(() => {
    let alive = true;
    api
      .missionHistory(subject)
      .then((body) => {
        if (!alive) return;
        setData(body);
        setUnavailable(null);
      })
      .catch((reason: unknown) => {
        if (alive) setUnavailable(requestOutcome(reason));
      });
    return () => {
      alive = false;
    };
  }, [subject, refreshKey, version]);

  return (
    <MissionHistoryView
      data={data}
      unavailable={unavailable}
      operator={operator}
      onDeclare={async (missions, by) => {
        await api.declareMissionHistory({ subject, missions, declared_by: by });
        setVersion((current) => current + 1);
      }}
    />
  );
}

/** Lo que no casa: el triángulo en amarillo, «hay que mirarlo» (F.5-1). No es una alerta. */
const DISAGREES_MARK: StateMark = mark("shape-triangle", "yellow");

/** Un aviso sobre lo declarado (`_overlap_check`), no un cotejo con el perfil: lo dice su clave. */
export function isHistoryNotice(check: MissionHistoryCheck): boolean {
  return check.key === "overlap";
}

/** La marca de un `check`, por lo que dice el backend: casa, no casa o no hay con qué cotejar. */
export function checkMark(check: MissionHistoryCheck): StateMark {
  if (check.matches === null) return MISSING_MARK;
  return check.matches ? OK_MARK : DISAGREES_MARK;
}

/** Solo pinta. Separado de la carga para poder probar lo que se lee en pantalla. */
export function MissionHistoryView({
  data,
  unavailable,
  operator,
  onDeclare,
}: {
  data: History | null;
  unavailable: RequestOutcome | null;
  operator: string;
  onDeclare: (missions: PriorMissionIn[], by: string) => Promise<void>;
}) {
  const notice = data?.declared === true && data.checks.some(isHistoryNotice);
  return (
    <Fold data-ui="radiation-mission-history"
      {...(notice ? { mark: DISAGREES_MARK } : { concept: "history" as const })}
      label={
        data?.declared
          ? tr(`Historial misión a misión (${data.missions.length})`, `Mission-by-mission history (${data.missions.length})`)
          : tr("Historial misión a misión", "Mission-by-mission history")
      }
    >
      <MissionHistoryContent data={data} unavailable={unavailable}>
        {data !== null && (
          <HistoryForm
            // Tras declarar, la vigente es otra: el formulario vuelve a arrancar con ella.
            key={data.declared ? data.ledger_index : "none"}
            initial={data.declared ? data.missions : []}
            limits={data.limits}
            operator={operator}
            onDeclare={onDeclare}
          />
        )}
      </MissionHistoryContent>
    </Fold>
  );
}

/**
 * Lo declarado y sus cotejos, de solo lectura: lo comparten la consola de tripulación (que pone
 * debajo el formulario, `children`) y la de Tierra (`ground/MissionHistoryPanel.tsx`), que no
 * declara nada. Mientras carga, la marca de carga; si falla, la de lo que fue.
 */
export function MissionHistoryContent({
  data,
  unavailable,
  children,
}: {
  data: History | null;
  unavailable: RequestOutcome | null;
  children?: ReactNode;
}) {
  if (unavailable !== null) return <Unavailable outcome={unavailable} />;
  if (data === null) return <Loading />;
  return (
    <>
      <p className="secondary">{data.scope}</p>
      {!data.declared ? (
        <p>
          <MarkOf mark={EMPTY_MARK}>{data.text}</MarkOf>
        </p>
      ) : (
        <p>{data.text}</p>
      )}
      {data.declared &&
        data.checks.filter(isHistoryNotice).map((check) => (
          <p key={check.key} className="history-notice">
            <MarkOf mark={checkMark(check)}>{check.text}</MarkOf>
          </p>
        ))}
      {data.declared && data.missions.length > 0 && (
        <>
          {/* En la columna estrecha del panel la tabla se desplaza, no se corta. */}
          <div className="limits-table">
          <table className="ledger">
            <thead>
              <tr>
                <Th concept="previous">{tr("Misión", "Mission")}</Th>
                <Th concept="date">{tr("Inicio", "Start")}</Th>
                <Th concept="date">{tr("Fin", "End")}</Th>
                <Th concept="missionDay">{tr("Días", "Days")}</Th>
                <Th concept="radiation">{tr("Dosis (mSv)", "Dose (mSv)")}</Th>
              </tr>
            </thead>
            <tbody>
              {data.missions.map((item, index) => (
                <tr key={index}>
                  <td>{item.name}</td>
                  <td>{formatDay(item.start)}</td>
                  <td>{formatDay(item.end)}</td>
                  <td>
                    <span className="num">{formatNumber(item.days)}</span>
                  </td>
                  <td>
                    {item.dose_msv === null ? (
                      <MarkOf mark={MISSING_MARK}>{tr("sin dosis declarada", "no dose declared")}</MarkOf>
                    ) : (
                      <span className="num">{formatNumber(item.dose_msv, 2)}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <p className="secondary">{tr("Días:", "Days:")} {data.days_basis}.</p>
        </>
      )}
      {data.declared && (
        <>
          {data.checks
            .filter((check) => !isHistoryNotice(check))
            .map((check) => (
              <p key={check.key}>
                <MarkOf mark={checkMark(check)}>{check.text}</MarkOf>
              </p>
            ))}
          <p className="secondary">{tr("Declarado por", "Declared by")} {data.declared_by}.</p>
        </>
      )}
      {children}
    </>
  );
}

interface Row {
  name: string;
  start: string;
  end: string;
  dose: string;
}

const EMPTY_ROW: Row = { name: "", start: "", end: "", dose: "" };

/**
 * La dosis tecleada: `null` si va vacía (no se conoce), la cifra si lo es, `undefined` si no es una
 * cifra. Con `Number` a secas «1,2,3» era `NaN`, que `JSON.stringify` manda como `null`: una errata
 * se firmaba como «dosis no conocida». La misma lectura que el diario (`diary/entry.parseValue`).
 */
export function parseDose(text: string): number | null | undefined {
  if (text.trim() === "") return null;
  return parseValue(text) ?? undefined;
}

function HistoryForm({
  initial,
  limits,
  operator,
  onDeclare,
}: {
  initial: readonly PriorMissionIn[];
  limits: History["limits"];
  operator: string;
  onDeclare: (missions: PriorMissionIn[], by: string) => Promise<void>;
}) {
  const [rows, setRows] = useState<Row[]>(() =>
    initial.map((item) => ({
      name: item.name,
      start: item.start,
      end: item.end,
      dose: item.dose_msv === null ? "" : String(item.dose_msv),
    })),
  );
  const [error, setError] = useState<RequestOutcome | null>(null);
  const who = operator.trim();
  // Sin nombre o sin fechas no se puede firmar: se espera a que esté la fila entera.
  const complete = rows.every((row) => row.name.trim() !== "" && row.start !== "" && row.end !== "");
  // Una dosis que no es una cifra no se manda: se firmaría como otra cosa.
  const badDose = rows.findIndex((row) => parseDose(row.dose) === undefined);
  const change = (index: number, field: keyof Row, value: string) =>
    setRows((current) => current.map((row, at) => (at === index ? { ...row, [field]: value } : row)));
  return (
    <form
      className="silence-form"
      onSubmit={(event) => {
        event.preventDefault();
        setError(null);
        const missions = rows.map((row) => ({
          name: row.name.trim(),
          start: row.start,
          end: row.end,
          dose_msv: parseDose(row.dose) ?? null,
        }));
        // El detalle del backend a secas; la marca, la de lo que fue (`requestOutcome`, §5.34.14).
        onDeclare(missions, who).catch((cause: unknown) => setError(requestOutcome(cause)));
      }}
    >
      {rows.map((row, index) => (
        <div key={index} className="inline-form">
          <FieldLabel concept="previous">
            {tr("Misión", "Mission")}{" "}
            <input
              value={row.name}
              maxLength={limits.name_length}
              onChange={(e) => change(index, "name", e.target.value)}
            />
          </FieldLabel>
          <FieldLabel concept="date">
            {tr("Inicio", "Start")} <input type="date" value={row.start} onChange={(e) => change(index, "start", e.target.value)} />
          </FieldLabel>
          <FieldLabel concept="date">
            {tr("Fin", "End")} <input type="date" value={row.end} onChange={(e) => change(index, "end", e.target.value)} />
          </FieldLabel>
          <FieldLabel concept="radiation">
            {tr("Dosis (mSv, vacío si no se conoce)", "Dose (mSv, blank if unknown)")}{" "}
            <input
              inputMode="decimal"
              value={row.dose}
              aria-invalid={index === badDose ? true : undefined}
              onChange={(e) => change(index, "dose", e.target.value)}
            />
          </FieldLabel>
          <Command
            concept="removeRow"
            type="button"
            onClick={() => setRows((current) => current.filter((_, at) => at !== index))}
          >
            {tr("Quitar", "Remove")}
          </Command>
        </div>
      ))}
      <Command
        concept="add"
        type="button"
        disabled={rows.length >= limits.missions}
        onClick={() => setRows((current) => [...current, EMPTY_ROW])}
      >
        {tr("Añadir misión", "Add mission")}
      </Command>
      {badDose >= 0 && <p className="secondary">{tr(`La dosis de la fila ${badDose + 1} no es una cifra.`, `The dose in row ${badDose + 1} is not a number.`)}</p>}
      {/* Sin filas lo que se firma es «ninguna misión previa»: el mando lo dice, para que un clic
          en el único botón activo no firme eso sin querer. */}
      <Command concept="declare" type="submit" disabled={who === "" || !complete || badDose >= 0}>
        {rows.length === 0 ? tr("Declarar: ninguna misión previa", "Declare: no prior missions") : tr("Declarar historial", "Declare history")}
      </Command>
      {/* El rechazo del backend, tal cual: amarillo con triángulo; la petición caída, la cruz. */}
      {error !== null && <MarkOf mark={error.mark}>{error.text}</MarkOf>}
    </form>
  );
}
