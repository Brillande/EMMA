import { BoardDetail } from "../components/BoardDetail";
import { useLook } from "../components/BoardOnly";
import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import type { AuditReport } from "../lib/api";
import { formatNumber } from "../lib/format";
import { FAILURE_MARK, OK_MARK, type StateMark } from "../lib/marks";
import { entryMark } from "./ledgerEntries";
import { tr } from "../lib/i18n";

/**
 * El registro firmado **de a bordo**. A Tierra no llega la cadena entera: llega el
 * ancla (tamano y raiz de Merkle), con la que se puede comprobar despues que nada
 * se ha reescrito. Su transmision real esta sin implementar (record-integrity §7).
 *
 * La integridad lleva marca y palabra (F.5.10 e): la de «hecho» si la cadena verifica, el aspa
 * en rojo si un asiento falla. Cada asiento lleva el pictograma de su clase (`ledgerEntries.ts`)
 * junto a su tipo, que sigue escrito tal cual lo da el backend. Título, rótulos y cabeceras llevan
 * el signo de su concepto (§5.33.6): el candado del registro firmado, la almohadilla de un valor
 * (el número de asiento, la raíz), la etiqueta del tipo, la persona que firma y el reloj.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta la integridad y el número
 * de asientos pasan de la lista a una ficha grande (`StatTile`), la cifra con el veredicto debajo con
 * su misma marca y palabra; es el mismo dato en otra forma, así que sustituye a sus dos filas en vez
 * de añadirse (por eso `useLook` y no `BoardOnly`), y la raíz de Merkle sigue entera en la lista.
 * Al lado, píldoras con cuántos de los asientos mostrados son de cada tipo: de los mostrados, no de
 * toda la cadena, y así lo dicen. La clásica sigue con sus tres filas.
 */
export function AuditPanel({ audit }: { audit: AuditReport }) {
  const board = useLook() === "reference";
  const verdict: { mark: StateMark; word: string } = audit.integrity_ok
    ? { mark: OK_MARK, word: tr("La cadena verifica", "The chain verifies") }
    : {
        mark: FAILURE_MARK,
        word: `${tr("Falla en el asiento", "Fails at entry")} ${audit.failed_index === null ? "?" : formatNumber(audit.failed_index)}: ${audit.failure_reason ?? ""}`,
      };
  const anchor = (
    <dl className="kv">
      {!board && (
        <>
          <FieldLabel as="dt" concept="signedLedger">
            {tr("Integridad", "Integrity")}
          </FieldLabel>
          <dd>
            <MarkOf mark={verdict.mark}>{verdict.word}</MarkOf>
          </dd>
          <FieldLabel as="dt" concept="value">
            {tr("Asientos", "Entries")}
          </FieldLabel>
          <dd className="num">{formatNumber(audit.total_entries)}</dd>
        </>
      )}
      <FieldLabel as="dt" concept="value">
        {tr("Raíz de Merkle", "Merkle root")}
      </FieldLabel>
      <dd className="num hash-wrap">
        {audit.merkle_root ?? tr("sin ancla: la cadena no verifica", "no anchor: the chain does not verify")}
      </dd>
    </dl>
  );
  const detail = (
    <>
      {/* Lote «muestra» (2026-11-08): la cifra, el veredicto de integridad y la raíz, a la vista;
          la tabla de asientos, tras «Ver detalle» en el tablero (su recuento por tipo va arriba). */}
      <BoardDetail
        label={`${formatNumber(audit.entries.length)} ${audit.entries.length === 1 ? tr("asiento mostrado", "entry shown") : tr("asientos mostrados", "entries shown")}`}
      >
      {/* Se desplaza dentro de su caja en pantalla estrecha (`.quality-table`): la huella y la
          hora llevaban la consola de Tierra a 581 px de ancho a 390 (§5.37.17). */}
      <div className="quality-table table-scroll mt-3 mb-0" role="region" tabIndex={0} aria-label={tr("Asientos del registro", "Ledger entries")}>
        <table className="ledger">
          <thead>
            <tr>
              <Th concept="value">{tr("Asiento", "Entry")}</Th>
              <Th concept="type">{tr("Tipo", "Type")}</Th>
              <Th concept="person">{tr("Firmante", "Signer")}</Th>
              <Th concept="time">{tr("Registrado (UTC)", "Recorded (UTC)")}</Th>
              <Th concept="signedLedger">Hash</Th>
            </tr>
          </thead>
          <tbody>
            {audit.entries.map((entry) => {
              const type = String(entry.entry_type);
              const state = entryMark(type);
              return (
                <tr key={String(entry.index)}>
                  <td className="num">{formatNumber(Number(entry.index))}</td>
                  <td>
                    <Mark pictogram={state.pictogram} color={state.color}>
                      {type}
                    </Mark>
                  </td>
                  <td>{String(entry.signer)}</td>
                  <td className="num">{String(entry.recorded).slice(0, 19).replace("T", " ")}</td>
                  <td className="num">{String(entry.content_hash).slice(0, 12)}…</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      </BoardDetail>
    </>
  );
  return (
    <section data-ui="audit" className="panel" aria-label={tr("Registro firmado", "Signed ledger")}>
      <PanelTitle concept="signedLedger">{tr("Registro firmado a bordo", "Signed ledger on board")}</PanelTitle>
      <p className="secondary mb-2">
        {tr(
          "A Tierra se enviaría el ancla: número de asientos y raíz de Merkle.",
          "The anchor would be sent to Earth: entry count and Merkle root.",
        )}
      </p>
      {/* Quinta ronda (R5-9, 2026-11-09): en el tablero, la raíz de Merkle y el «Ver detalle» de los
          asientos van a la derecha de la ficha, bajo sus píldoras, y no en dos renglones más debajo
          de ella (el panel fijaba con «Exportar» una fila de 300 px). Mismo orden de lectura: ficha,
          píldoras, raíz, detalle. En la clásica, la lista y el detalle como siempre. */}
      {board ? (
        <div className="board-row audit-board">
          <div className="board-stats" role="group" aria-label={tr("Integridad del registro", "Ledger integrity")}>
            <StatTile
              concept="signedLedger"
              label={tr("Asientos", "Entries")}
              value={audit.total_entries}
              status={{ mark: verdict.mark, word: verdict.word }}
            />
          </div>
          <div className="audit-side">
            <EntryTally entries={audit.entries} />
            {anchor}
            {detail}
          </div>
        </div>
      ) : (
        <>
          {anchor}
          {detail}
        </>
      )}
    </section>
  );
}

/**
 * Cuántos de los asientos que trae el informe (los últimos, no la cadena entera) son de cada tipo,
 * con el pictograma de su clase y el tipo escrito tal cual, en el orden en que aparecen.
 */
function EntryTally({ entries }: { entries: AuditReport["entries"] }) {
  if (entries.length === 0) return null;
  const types = new Map<string, number>();
  for (const entry of entries) {
    const type = String(entry.entry_type);
    types.set(type, (types.get(type) ?? 0) + 1);
  }
  return (
    <ul className="board-tally" aria-label={tr("Asientos mostrados, por tipo", "Entries shown, by type")}>
      <li className="ref-pill board-pill">
        <span className="num">{formatNumber(entries.length)}</span>{" "}
        {entries.length === 1 ? tr("asiento mostrado", "entry shown") : tr("asientos mostrados", "entries shown")}
      </li>
      {[...types].map(([type, count]) => {
        const state = entryMark(type);
        return (
          <li key={type} className="ref-pill board-pill">
            <Mark pictogram={state.pictogram} color={state.color}>
              {type}
            </Mark>{" "}
            <span className="num">{formatNumber(count)}</span>
          </li>
        );
      })}
    </ul>
  );
}
