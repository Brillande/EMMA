import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { type HabitatModules, type HabitatSystems, api } from "../lib/api";
import { formatMet, formatNumber, missionElapsedSeconds } from "../lib/format";
import { tr } from "../lib/i18n";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { modulePictogram, parameterPictogram, systemPictogram } from "./pictograms";
import {
  EMPTY_FORM,
  canDeclare,
  declarableStates,
  declarationBody,
  declarationInstant,
  stateMark,
  stateTally,
  systemRows,
} from "./systems";

/**
 * El estado de los sistemas del habitat, tal y como lo declaro una persona (especificacion del
 * equipo §3, `HabitatState.system_status`).
 *
 * EMMA no lee el estado de ningun sistema: lo que se ve es lo declarado en la consola y firmado
 * en el registro, y el rotulo del backend («declarado por una persona, no telemetria») va
 * arriba, junto al titulo. Nombres, estados y frases son del backend; aqui solo se elige la
 * marca (`systems.ts`): «sin declarar» es un dato ausente (cian, anillo punteado), nunca un
 * «funciona», y el color no va solo. Cada sistema, modulo y parametro lleva su pictograma junto
 * al nombre (`pictograms.ts`), sin color: nombrar no es avisar. En el historial el estado lleva
 * su pictograma y no su color: una declaracion pasada no pide atencion.
 *
 * A bordo (con operador) se puede declarar un estado: sistema, estado, modulo si la declaracion
 * habla de uno, y una nota. Se firma con el operador de la consola, como las demas firmas, y se
 * ensena a que instante se refiere. No hay borrar ni editar: se corrige declarando de nuevo. En
 * Tierra (sin operador) es de solo lectura, con lo que su corte permite conocer.
 */
export function SystemsStatus({
  missionStart,
  refreshKey,
  until,
  operator,
  referenceTime,
  modules,
}: {
  missionStart: string;
  /** Cambia cuando cambia el estado: vuelve a pedir lo declarado. */
  refreshKey: string;
  until: Date | undefined;
  /** Solo a bordo: quien declara. En Tierra (`undefined`), lectura. */
  operator: string | undefined;
  /** El instante de los datos (la ultima lectura de cabina), al que se refiere una declaracion. */
  referenceTime: string | null;
  modules: HabitatModules | null;
}) {
  const [overview, setOverview] = useState<HabitatSystems | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [declared, setDeclared] = useState(0);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const untilKey = until?.toISOString() ?? "";
  const board = useLook() === "reference";

  useEffect(() => {
    let cancelled = false;
    api
      .habitatSystems(until)
      .then((body) => {
        if (!cancelled) setOverview(body);
      })
      // Sin esta lectura el resto del panel de habitat sigue valiendo: aqui no se ensena nada.
      .catch(() => {
        if (!cancelled) setOverview(null);
      });
    return () => {
      cancelled = true;
    };
    // `until` va por su texto: una fecha nueva con el mismo instante no debe repetir la carga.
  }, [refreshKey, untilKey, declared]);

  if (overview === null) return null;
  const met = (iso: string) => formatMet(missionElapsedSeconds(missionStart, new Date(iso)));
  const rows = systemRows(overview);
  const tally = stateTally(rows);
  const attention = rows.filter((row) => row.mark.color === "yellow");
  const summary = <p className="secondary">{overview.summary}</p>;
  const foldSummary = board && tally.length > 0;
  const at = declarationInstant(referenceTime, new Date());
  const declare = () => {
    if (operator === undefined) return;
    setError(null);
    api
      .declareSystemStatus(declarationBody(form, operator, at))
      .then(() => {
        setForm(EMPTY_FORM);
        setDeclared((count) => count + 1);
      })
      .catch((cause: unknown) => setError(requestOutcome(cause)));
  };

  return (
    <div className="hypotheses" role="group" aria-label={tr("Sistemas del hábitat", "Habitat systems")}>
      <PanelTitle as="h3" concept="systems">
        {tr("Sistemas del hábitat", "Habitat systems")} <span className="secondary">· {overview.label}</span>
      </PanelTitle>
      {/* Quinta ronda del lote «muestra» (R5-8, 2026-11-09): bajo la concha de la maqueta, la frase
          del recuento («… 0 de 10. De los demás no se sabe nada …») va al detalle cuando las píldoras
          de abajo ya dan cuántos hay en cada estado, con su marca; sin píldoras, a la vista. */}
      {!foldSummary && summary}
      {/* Lote «muestra» (2026-11-08): a la vista, una píldora por estado con cuántos sistemas o
          módulos hay en él (la palabra del backend y la marca de `systems.ts`: el cian de lo sin
          declarar, el amarillo de lo degradado o fuera de servicio); la lista, cómo leerla, el
          historial y el formulario, tras «Ver detalle». */}
      <BoardOnly>
        {tally.length > 0 && (
          <ul className="board-tally" aria-label={tr("Sistemas por estado", "Systems by state")}>
            {tally.map((entry) => (
              <li key={entry.state} className="ref-pill board-pill">
                <MarkOf mark={entry.mark}>{entry.display}</MarkOf> <span className="num">{formatNumber(entry.count)}</span>
              </li>
            ))}
          </ul>
        )}
        {/* Lo degradado o fuera de servicio, con su sistema y su módulo: el recuento solo no dice
            cuál, y es lo que una hipótesis del hábitat puede señalar. */}
        {attention.length > 0 && (
          <ul className="board-tally" aria-label={tr("Sistemas que piden atención", "Systems needing attention")}>
            {attention.map((row) => (
              <li key={row.key} className="ref-pill board-pill">
                <Mark pictogram={systemPictogram(row.system)}>
                  {overview.systems.find((system) => system.key === row.system)?.display ?? row.system}
                </Mark>
                {row.where !== null && (
                  <>
                    {" "}
                    <Mark pictogram={modulePictogram(row.where.key)}>{row.where.display}</Mark>
                  </>
                )}{" "}
                <MarkOf mark={row.mark}>{row.status.state_display}</MarkOf>
              </li>
            ))}
          </ul>
        )}
      </BoardOnly>
      <BoardDetail label={tr("sistemas, historial y declarar", "systems, history and declaring")}>
      {foldSummary && summary}
      <dl className="kv">
        {overview.systems.map((system) => (
          <SystemEntry
            key={system.key}
            system={system}
            rows={rows.filter((row) => row.system === system.key)}
            met={met}
          />
        ))}
      </dl>
      <Fold data-ui="systems-how-to-read" concept="howToRead" label={tr("Cómo leerlo", "How to read it")}>
        <p className="secondary">{overview.note}</p>
        <p className="secondary">{overview.basis}</p>
        {overview.basis_sources.length > 0 && (
          <ul className="secondary" aria-label={tr("Fuentes de la base del vocabulario", "Sources for the basis of the vocabulary")}>
            {overview.basis_sources.map((source) => (
              <li key={source.id}>
                <Mark pictogram={uiPictogram("sourceText")}>
                  <span lang="en">{source.title}</span>
                </Mark>{" "}
                · {source.source}
                {source.url !== null && <div className="num url">{source.url}</div>}
              </li>
            ))}
          </ul>
        )}
        <p className="secondary">{overview.relation_basis}</p>
        <p className="secondary">
          {overview.rule} {overview.since_basis}
        </p>
      </Fold>
      {overview.history.length > 0 && (
        <Fold data-ui="systems-history"
          concept="history"
          label={tr(`Historial de declaraciones (${formatNumber(overview.history.length)})`, `Declaration history (${formatNumber(overview.history.length)})`)}
        >
          <ul className="secondary">
            {overview.history.map((item) => (
              <li key={item.ledger_index}>
                <span className="num">{met(item.at)}</span> ·{" "}
                <Mark pictogram={systemPictogram(item.system)}>{item.system_display}</Mark>
                {item.module !== null && (
                  <>
                    {" "}
                    (<Mark pictogram={modulePictogram(item.module)}>{item.module_display}</Mark>)
                  </>
                )}
                : <Mark pictogram={stateMark(item.state).pictogram}>{item.state_display}</Mark>
                {item.changed && <> ({tr("antes:", "before:")} {item.previous_state_display})</>} · {tr("declarado por", "declared by")}{" "}
                {item.declared_by} · {tr("asiento", "ledger entry")} <span className="num">{item.ledger_index}</span>
                {item.note !== null && <> · {item.note}</>}
              </li>
            ))}
          </ul>
        </Fold>
      )}
      {operator !== undefined && (
        <div className="inline-form">
          <select
            value={form.system}
            aria-label={tr("Sistema", "System")}
            onChange={(event) => setForm({ ...form, system: event.target.value })}
          >
            <option value="">{tr("Sistema…", "System…")}</option>
            {overview.systems.map((system) => (
              <option key={system.key} value={system.key}>
                {system.display}
              </option>
            ))}
          </select>
          <select
            value={form.state}
            aria-label={tr("Estado que se declara", "State being declared")}
            onChange={(event) => setForm({ ...form, state: event.target.value })}
          >
            <option value="">{tr("Estado…", "State…")}</option>
            {declarableStates(overview).map((state) => (
              <option key={state.key} value={state.key}>
                {state.display}
              </option>
            ))}
          </select>
          <select
            value={form.module}
            aria-label={tr("Módulo del que habla la declaración", "Module the declaration refers to")}
            onChange={(event) => setForm({ ...form, module: event.target.value })}
          >
            <option value="">{overview.whole_system_display}</option>
            {(modules?.modules ?? []).map((item) => (
              <option key={item.key} value={item.key}>
                {item.display}
              </option>
            ))}
          </select>
          <input
            value={form.note}
            maxLength={500}
            placeholder={tr("nota de quien declara (opcional)", "note from whoever declares (optional)")}
            aria-label={tr("Nota de la declaración", "Declaration note")}
            onChange={(event) => setForm({ ...form, note: event.target.value })}
          />
          <Command concept="declare" disabled={!canDeclare(form, operator)} onClick={declare}>
            {tr("Declarar", "Declare")}
          </Command>
          <span className="secondary">
            {tr("se refiere a", "refers to")} <span className="num">{met(at)}</span> · {tr("firma", "signed by")}{" "}
            {operator.trim() === "" ? "—" : operator.trim()}
          </span>
          {error !== null && <MarkOf mark={error.mark}>{error.text}</MarkOf>}
        </div>
      )}
      </BoardDetail>
    </div>
  );
}

/**
 * Un sistema: su nombre con pictograma y, por cada estado vigente, la marca del estado con la
 * palabra del backend y el modulo si la declaracion habla de uno. Exportada solo para pintarla
 * a HTML estatico en las pruebas.
 */
export function SystemEntry({
  system,
  rows,
  met,
}: {
  system: HabitatSystems["systems"][number];
  rows: ReturnType<typeof systemRows>;
  met: (iso: string) => string;
}) {
  return (
    <>
      <dt title={system.description}>
        <Mark pictogram={systemPictogram(system.key)}>{system.display}</Mark>
      </dt>
      <dd>
        {rows.map((row) => (
          <div key={row.key}>
            <MarkOf mark={row.mark}>{row.status.state_display}</MarkOf>
            {row.where !== null && (
              <span className="secondary">
                {" "}
                · <Mark pictogram={modulePictogram(row.where.key)}>{row.where.display}</Mark>
              </span>
            )}
            {row.status.since !== null && (
              <span className="secondary">
                {" "}
                · {tr("desde", "since")} <span className="num">{met(row.status.since)}</span>
              </span>
            )}
            {row.status.declared_by !== null && (
              <span className="secondary"> · {tr("declarado por", "declared by")} {row.status.declared_by}</span>
            )}
            {row.status.note !== null && <span className="secondary"> · {row.status.note}</span>}
          </div>
        ))}
        {system.parameters.length > 0 && (
          <div className="secondary">
            {tr("Parámetros de cabina relacionados por definición:", "Cabin parameters related by definition:")}{" "}
            {system.parameters.map((item, index) => (
              <span key={item.key}>
                {index > 0 && ", "}
                <Mark pictogram={parameterPictogram(item.key)}>{item.display}</Mark>
              </span>
            ))}
          </div>
        )}
      </dd>
    </>
  );
}
