import { useEffect, useRef, useState } from "react";

import { Ring } from "../dashboard/HomeCharts";
import { Pictogram } from "../icons";
import { type MissionLevel, type MissionMeasure, type MissionModeChange, type MissionModeState, api } from "../lib/api";
import { formatNumber, formatUtc } from "../lib/format";
import { tr } from "../lib/i18n";
import { MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { BoardOnly } from "./BoardOnly";
import { FieldLabel } from "./FieldLabel";
import { Fold } from "./Fold";
import { Mark, MarkOf } from "./Mark";

/** Cada cuánto se relee el nivel: el mismo ritmo que el modo seguro (`SAFE_MODE_REFRESH_MS`). */
export const MISSION_MODE_REFRESH_MS = 30_000;

/**
 * Si `next` es más nuevo que `shown`: de un almacén posterior, o del mismo con versión igual o
 * mayor (la misma regla que el modo seguro, §5.38.13; con la misma versión el estado es el mismo).
 */
export function isNewer(next: MissionModeState, shown: MissionModeState | null): boolean {
  if (shown === null || next.store_epoch > shown.store_epoch) return true;
  return next.store_epoch === shown.store_epoch && next.version >= shown.version;
}

/**
 * El nivel leído al montar y cada `MISSION_MODE_REFRESH_MS`; con `until`, el firmado hasta el corte
 * de Tierra. Una relectura que falla no borra lo que ya se veía: se marca sin actualizar.
 */
export function useMissionMode(until?: Date): {
  state: MissionModeState | null;
  stale: boolean;
  apply: (body: MissionModeChange) => Promise<void>;
} {
  const [state, setState] = useState<MissionModeState | null>(null);
  const [stale, setStale] = useState(false);
  const shown = useRef<MissionModeState | null>(null);
  const offer = (next: MissionModeState) => {
    if (!isNewer(next, shown.current)) return;
    shown.current = next;
    setState(next);
    setStale(false);
  };
  const cut = until?.toISOString();
  useEffect(() => {
    const load = () =>
      void api.missionMode(cut === undefined ? undefined : new Date(cut)).then(offer, () => setStale(true));
    load();
    const timer = setInterval(() => {
      if (typeof document === "undefined" || !document.hidden) load();
    }, MISSION_MODE_REFRESH_MS);
    return () => clearInterval(timer);
    // `offer` solo toca una ref y setters estables: depende del corte y de nada más.
  }, [cut]);
  return { state, stale, apply: async (body) => offer(await api.setMissionMode(body)) };
}

/**
 * El nivel con su lectura propia, para ponerlo en una consola con una línea: a bordo con
 * `controls`, en Tierra con su corte (`until`). Sin respuesta todavía, nada.
 */
export function MissionModePanel({ controls, until }: { controls: boolean; until?: Date }) {
  const { state, stale, apply } = useMissionMode(until);
  if (state === null) return null;
  return (
    <>
      {stale && (
        <p>
          <MarkOf mark={MISSING_MARK}>{tr("sin actualizar", "not updated")}</MarkOf>
        </p>
      )}
      <MissionMode state={state} controls={controls} apply={apply} />
    </>
  );
}

/**
 * El nivel de misión (desconexión progresiva, `core/mission_modes.py`): qué medidas se siguen
 * esperando cuando escasean la energía o el tiempo de la tripulación.
 *
 * Por qué existe: con recursos racionados la consola seguía esperándolo todo, y lo no tomado
 * parecía olvidado. El nivel lo firma una persona en el registro; aquí se ve cuál rige, desde
 * cuándo, qué se espera y qué no, cada medida con su porqué. **El análisis y las alertas no cambian
 * con el nivel** (invariante 5), y el aviso lo dice con las palabras del backend: la interfaz no
 * redacta nada de lo que el nivel significa, ni el nombre del nivel.
 *
 * Fuera del nivel de más medidas, amarillo con triángulo, como el modo seguro: tabla F.5-1,
 * «off-nominal, attention required». No es rojo: no ha fallado nada. En el nivel de más medidas,
 * texto secundario sin color. El mando solo a bordo (`controls`): Tierra ve el nivel, no lo cambia.
 * Quién baja y quién sube lo decide el backend; un rechazo se enseña con su motivo y su marca
 * (`requestOutcome`), como en el modo seguro.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta, el anillo de cuántas
 * medidas se esperan de las que el nivel reparte (la escala es la propia lista del backend: lo que
 * se espera más lo que no) y el nivel en su píldora, con la misma marca de arriba fuera del nivel de
 * más medidas. Vale igual en Tierra, donde no hay mando. La clásica no lo monta (`BoardOnly`).
 */
export function MissionMode({
  state,
  controls,
  apply,
}: {
  state: MissionModeState;
  controls: boolean;
  /** Firma un cambio de nivel; lanza lo que diga el backend para que se pinte su marca. */
  apply: (body: MissionModeChange) => Promise<void>;
}) {
  const [operator, setOperator] = useOperator();
  const [level, setLevel] = useState<MissionLevel>(state.level);
  // Si el nivel cambia por otra consola o por una relectura, la elección vuelve al vigente: un
  // clic no puede firmar un nivel que nadie ha elegido.
  useEffect(() => setLevel(state.level), [state.level, state.version, state.store_epoch]);
  const [reason, setReason] = useState("");
  const [cited, setCited] = useState("");
  const [error, setError] = useState<RequestOutcome | null>(null);
  // Mientras va un cambio no se pide otro: un doble clic cruzaba dos peticiones (como §5.37.18).
  const [sending, setSending] = useState(false);

  const change = async () => {
    setError(null);
    setSending(true);
    try {
      await apply({
        level,
        reason: reason.trim(),
        declared_by: operator.trim(),
        cited_system: cited === "" ? null : cited,
      });
      setReason("");
      setCited("");
    } catch (failure) {
      setError(requestOutcome(failure));
    } finally {
      setSending(false);
    }
  };

  const notice = state.notice;
  const expected = state.current.expected.length;
  const notExpected = state.current.suspended.length;
  return (
    <section data-ui="mission-level" className="mission-mode" aria-label={notice?.title ?? state.level_display}>
      <p>
        <span className="label">
          <Pictogram name="gear" />
          {tr("Nivel de misión", "Mission level")}
        </span>{" "}
        {notice === null ? (
          <Mark pictogram={null} className="secondary">
            {state.level_display}
          </Mark>
        ) : (
          <span role="status">
            <Mark pictogram="shape-triangle" color="yellow" title={state.reason ?? undefined}>
              {notice.title} · {notice.headline}
            </Mark>
          </span>
        )}
        {state.since !== null && (
          <span className="secondary num" title={notice?.since_label}>
            {" "}
            {formatUtc(new Date(state.since))}
          </span>
        )}
      </p>
      <BoardOnly>
        <div className="board-row mission-board">
          <div className="ref-ring-col">
            <Ring done={expected} total={expected + notExpected} label={tr("medidas esperadas", "measures expected")}>
              <span className="num ref-ring-value">{formatNumber(expected)}</span>
              <span className="num secondary">/ {formatNumber(expected + notExpected)}</span>
            </Ring>
            <p className="secondary ref-ring-caption">{tr("se esperan", "expected")}</p>
          </div>
          <span className="ref-pill board-pill">
            {notice === null ? (
              <Mark pictogram="gear">{state.level_display}</Mark>
            ) : (
              <Mark pictogram="shape-triangle" color="yellow">
                {state.level_display}
              </Mark>
            )}
          </span>
        </div>
      </BoardOnly>
      {notice !== null && <p>{notice.summary}</p>}
      {state.declared_by !== null && (
        <p className="secondary">
          {[state.declared_by, state.reason, state.cited_system_display, state.cited_state_display]
            .filter((item) => item !== null && item !== "")
            .join(" · ")}
        </p>
      )}
      <Fold data-ui="mission-level-how-to-read" concept="howToRead" label={notice?.details_label ?? state.current.description}>
        {notice !== null && (
          <ul>
            {notice.details.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}
        <p className="secondary">{state.label}</p>
        <p className="secondary">{state.basis}</p>
        <MeasureList title={tr("Se esperan", "Expected")} measures={state.current.expected} />
        <MeasureList title={tr("No se esperan", "Not expected")} measures={state.current.suspended} />
      </Fold>
      {controls && (
        <Fold data-ui="mission-level-change" concept="systems" label={tr("Cambiar el nivel", "Change the level")}>
          <div className="silence-form">
            <FieldLabel concept="person">
              {tr("Quién", "Who")}{" "}
              <input value={operator} maxLength={64} onChange={(event) => setOperator(event.target.value)} />
            </FieldLabel>
            <FieldLabel concept="systems">
              {tr("Nivel", "Level")}{" "}
              <select value={level} onChange={(event) => setLevel(event.target.value as MissionLevel)}>
                {state.levels.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.display} · {formatNumber(item.expected)} {tr("medidas", "measures")}
                  </option>
                ))}
              </select>
            </FieldLabel>
            <FieldLabel concept="reason">
              {tr("Motivo", "Reason")} <input value={reason} maxLength={300} onChange={(event) => setReason(event.target.value)} />
            </FieldLabel>
            <FieldLabel concept="habitat">
              {tr("Cita", "Cites")}{" "}
              <select value={cited} onChange={(event) => setCited(event.target.value)}>
                <option value="">—</option>
                {state.citable_systems.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.display}
                  </option>
                ))}
              </select>
            </FieldLabel>
            <p className="secondary">{state.rule}</p>
            <button
              className="command"
              disabled={sending || operator.trim() === "" || level === state.level}
              onClick={() => void change()}
            >
              <Mark pictogram="pen">{tr("Firmar el nivel", "Sign the level")}</Mark>
            </button>
            {error !== null && (
              <p>
                <MarkOf mark={error.mark}>{error.text}</MarkOf>
              </p>
            )}
          </div>
        </Fold>
      )}
    </section>
  );
}

/** Una lista de medidas con su nombre y el porqué que da el backend, y cuántas son. */
export function MeasureList({ title, measures }: { title: string; measures: readonly MissionMeasure[] }) {
  return (
    <>
      <p>
        {title} <span className="num">{formatNumber(measures.length)}</span>
      </p>
      {measures.length > 0 && (
        <ul>
          {measures.map((measure) => (
            <li key={measure.key}>
              {measure.name} <span className="secondary">{measure.why}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
