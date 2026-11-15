import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { type Sharing, type SharingItem, sharingApi } from "../lib/api";
import { formatNumber } from "../lib/format";
import { LOADING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { enforcementMark, itemsByDestination } from "./sharing";
import { markTint } from "./TimelinePieces";
import { tr } from "../lib/i18n";

const TITLE = tr("Qué se comparte y qué no", "What is shared and what is not");

/**
 * Qué sale de este equipo, qué ve Tierra y qué se queda a bordo o en esta consola, por tipo de dato
 * (`GET /api/sharing`, `app/sharing.py`).
 *
 * Por qué existe: la privacidad de EMMA estaba contada en una docena de docstrings y en ninguna
 * pantalla. La tripulación tiene que poder ver, sin leer código, a dónde va cada cosa que deja en
 * la consola, y también lo que EMMA no protege (no hay notas que Tierra no vea). Va en las dos
 * consolas igual y sin corte: es una tabla del paquete, no un dato de a bordo.
 *
 * Todo el texto viene del backend tal cual; aquí solo se agrupa por destino y se elige la marca de
 * cada grado (`sharing.ts`). Inventario: no interviene en el estado de la tripulación.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta (`BoardOnly`), cada
 * destino lleva bajo su título las píldoras de recuento: cuántos tipos de dato llegan a él y, por
 * grado, cuántos impone el código, en parte o no, con la marca del grado (`enforcementMark`) y la
 * palabra del backend (`enforcement_text`) que ya llevan sus pliegues. La hoja de la sección reparte
 * los destinos en columnas (`shell/data.css`).
 *
 * Una pantalla por sección (lote «muestra», 2026-11-08): en la concha de la maqueta los cinco
 * destinos son mosaicos en una fila, con su título y sus píldoras. Lo que SALE del equipo (a
 * internet y a Tierra) sigue a la vista, categoría por categoría: es un aviso de privacidad y no se
 * pliega. Las categorías que se quedan (a bordo, en esta consola, no se guardan), los propósitos y
 * hosts, las rutas con corte y la frase de por qué existe la tabla van detrás de «Ver detalle»; la
 * frase de si ahora hay red, siempre a la vista. En la clásica, todo en su orden de antes.
 */

/**
 * Destinos cuyas categorías se quedan en el equipo: solo estas van detrás de «Ver detalle». Es la
 * lista de lo que se queda y no la de lo que sale a propósito: un destino nuevo que el backend añada
 * sale a la vista hasta que alguien decida que no sale del equipo.
 */
const STAYS = new Set(["board", "device", "nowhere"]);
export function SharingPanel() {
  const [body, setBody] = useState<Sharing | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    let current = true;
    sharingApi
      .get()
      .then((received) => {
        if (current) setBody(received);
      })
      .catch((reason: unknown) => {
        if (current) setFailure(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  if (body === null) {
    return (
      <section data-ui="sharing" className="panel" aria-label={TITLE}>
        <PanelTitle concept="privacy">{TITLE}</PanelTitle>
        {failure === null ? (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Consultando qué se comparte…", "Checking what is shared…")}</MarkOf>
          </p>
        ) : (
          <p>
            <MarkOf mark={failure.mark}>
              {tr("Qué se comparte, no disponible:", "What is shared, unavailable:")} {failure.text}
            </MarkOf>
          </p>
        )}
      </section>
    );
  }
  return <SharingView body={body} />;
}

/** La tabla ya recibida. Aparte del que consulta para poder pintarla en las pruebas sin red. */
export function SharingView({ body }: { body: Sharing }) {
  const board = useLook() === "reference";
  const note = <p className="secondary">{body.note}</p>;
  return (
    <section data-ui="sharing" className="panel sharing" aria-label={TITLE}>
      <PanelTitle concept="privacy">{TITLE}</PanelTitle>
      {!board && note}
      <p>{body.internet.offline_text}</p>
      {board && <BoardDetail label={tr("por qué esta tabla", "why this table")}>{note}</BoardDetail>}
      {itemsByDestination(body).map((group) => {
        const leaves = !STAYS.has(group.id);
        const items = group.items.map((item) => <ItemFold key={item.id} item={item} />);
        const extra = (
          <>
            {group.id === "internet" && <PurposesFold body={body} />}
            {group.id === "ground" && <CutFold body={body} />}
          </>
        );
        return (
          <div key={group.id} className="sharing-group" data-destination={group.id}>
            <h3>{group.label}</h3>
            <BoardOnly>
              <GroupTally items={group.items} />
            </BoardOnly>
            {board ? (
              <>
                {leaves && items}
                <BoardDetail label={group.label}>
                  {!leaves && items}
                  {extra}
                </BoardDetail>
              </>
            ) : (
              <>
                {items}
                {extra}
              </>
            )}
          </div>
        );
      })}
    </section>
  );
}

/**
 * Las píldoras de un destino: cuántos tipos de dato llegan a él y cuántos de cada grado, en el
 * orden en que aparecen. La palabra de cada grado es la del backend en la primera fila que lo
 * lleva (es la misma en todas); la marca, la de su pliegue. Un destino sin filas (internet o
 * Tierra sin categorías) no lleva píldoras: sus pliegues propios ya dicen su cuenta.
 */
function GroupTally({ items }: { items: SharingItem[] }) {
  if (items.length === 0) return null;
  const grades = new Map<SharingItem["enforcement"], { word: string; count: number }>();
  for (const item of items) {
    const entry = grades.get(item.enforcement);
    if (entry === undefined) grades.set(item.enforcement, { word: item.enforcement_text, count: 1 });
    else entry.count += 1;
  }
  return (
    <ul className="board-tally" aria-label={tr("Tipos de dato de este destino, por grado", "Data types for this destination, by grade")}>
      <li className="ref-pill board-pill">
        <span className="num">{formatNumber(items.length)}</span> {items.length === 1 ? tr("tipo de dato", "data type") : tr("tipos de dato", "data types")}
      </li>
      {[...grades].map(([grade, entry]) => {
        const shown = enforcementMark(grade);
        return (
          <li key={grade} className="ref-pill board-pill" style={markTint(shown)}>
            <MarkOf mark={shown}>{entry.word}</MarkOf> <span className="num">{formatNumber(entry.count)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Una categoría, plegada: su nombre y el grado en el rótulo; dentro, qué pasa y dónde se impone. */
function ItemFold({ item }: { item: SharingItem }) {
  const shown = enforcementMark(item.enforcement);
  return (
    <Fold
      data-ui="sharing-item"
      mark={shown}
      aria-label={item.title}
      label={
        <>
          <strong>{item.title}</strong> · <span className={shown.className}>{item.enforcement_text}</span>
        </>
      }
    >
      <p>{item.text}</p>
      <dl className="kv">
        {item.limit !== null && (
          <>
            <FieldLabel as="dt" concept="limits">
              {tr("Qué queda fuera", "What is left out")}
            </FieldLabel>
            <dd>{item.limit}</dd>
          </>
        )}
        {item.enforced_by.length > 0 && (
          <>
            <FieldLabel as="dt" concept="source">
              {tr("Dónde se impone", "Where it is enforced")}
            </FieldLabel>
            <dd>
              <ul className="sharing-list">
                {item.enforced_by.map((place) => (
                  <li key={place}>
                    <span className="num wrap">{place}</span>
                  </li>
                ))}
              </ul>
            </dd>
          </>
        )}
      </dl>
    </Fold>
  );
}

/** Los propósitos de la lista blanca, con lo que lleva cada consulta y sus hosts. */
function PurposesFold({ body }: { body: Sharing }) {
  const purposes = body.internet.purposes;
  return (
    <Fold
      data-ui="sharing-purposes"
      concept="detail"
      label={
        <>
          {tr("Propósitos y hosts", "Purposes and hosts")} · <span className="num">{formatNumber(purposes.length)}</span>
        </>
      }
    >
      <ul className="sharing-list">
        {purposes.map((row) => (
          <li key={row.purpose}>
            <strong className="num wrap">{row.purpose}</strong>
            <p>{row.what}</p>
            <p className="secondary">{row.carries}</p>
            <ul className="sharing-hosts">
              {row.hosts.map((host) => (
                <li key={host} className="num url">
                  {host}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </Fold>
  );
}

/** Las rutas que aceptan el corte del retardo, con su sentido. */
function CutFold({ body }: { body: Sharing }) {
  const routes = body.ground_cut.routes;
  return (
    <Fold
      data-ui="sharing-cut"
      concept="lightTime"
      label={
        <>
          {tr("Rutas con el corte del retardo", "Routes with the delay cut")} · <span className="num">{formatNumber(routes.length)}</span>
        </>
      }
    >
      <p className="secondary">{body.ground_cut.note}</p>
      <ul className="sharing-list">
        {routes.map((route) => (
          <li key={route.path}>
            <span className="num wrap">{route.path}</span> · {route.direction_text}
          </li>
        ))}
      </ul>
    </Fold>
  );
}
