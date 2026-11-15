import { useCallback, useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { DomainName } from "../components/DomainName";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import { Loading, Unavailable } from "../components/Unavailable";
import { Ring } from "../dashboard/HomeCharts";
import { type DescriptiveIndicators, indicatorsApi } from "../lib/api";
import { formatNumber } from "../lib/format";
import { EMPTY_MARK, MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { type DescriptiveCard, type InstrumentView, descriptiveView } from "./descriptive";

/**
 * Indicadores descriptivos: salud conductual más allá del ánimo, síntomas visuales y forma
 * física (decisión del usuario del 2026-10-15), y la vitamina D 25-OH (2026-10-22). Se firman en
 * el registro y se enseñan aquí, pero el estado no los lee: no son alertas ni niveles, y no
 * llevan color. Cada uno va con su código y por qué es ese, con lo leído de su medida en el idioma de la fuente y con lo que consta en
 * el registro firmado. Aquí no se redacta nada: los textos y las cifras son del backend.
 *
 * Una lectura descriptiva no cambia el estado, así que el estado no avisa de que hay una nueva:
 * el panel se vuelve a leer al cambiar de tripulante, con el estado o a mano.
 *
 * Signos (§5.33.7): la regla en el título (una medida), el libro abierto en «Lo leído de su
 * medida», la flecha que gira en «Volver a leer» y el vocabulario común en las cabeceras. Lo que
 * falta lleva la marca de la tabla F.5-1 (dato ausente, no disponible), que no es de nivel.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta, junto al recuento del
 * backend va el anillo de cuántos indicadores tienen alguna lectura sobre cuántos hay
 * (`ReadingsRing`): es la única cifra que el panel tiene sin pedir nada nuevo (cada tarjeta ya dice
 * «Sin lecturas» o «N lecturas»). Sin veredicto: cuántos, no cómo. Las tarjetas a dos columnas las
 * reparte la hoja de la sección (`shell/log.css`).
 *
 * Segunda ronda (2026-11-08): con más de cuarenta indicadores, los mosaicos ocupaban vista y media.
 * Junto al anillo va el recuento por dominio (cuántos, con lecturas y sin lecturas con su marca de
 * dato ausente, que no se pliega) y los mosaicos de uno en uno, en su propio «Ver detalle».
 */
export function DescriptivePanel({
  subject,
  refreshKey,
}: {
  subject: string;
  /** Cambia cuando cambian los datos del estado: entonces se vuelve a leer. */
  refreshKey: string;
}) {
  const [data, setData] = useState<DescriptiveIndicators | null>(null);
  const [unavailable, setUnavailable] = useState<RequestOutcome | null>(null);
  const [reads, setReads] = useState(0);

  // Otro tripulante: lo pintado era del anterior. Hasta que llega lo suyo, «Cargando…», no sus
  // lecturas como si fueran de este (ni, si falla, como de este caducadas).
  useEffect(() => {
    setData(null);
    setUnavailable(null);
  }, [subject]);

  useEffect(() => {
    let alive = true;
    indicatorsApi
      .descriptive(subject)
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
  }, [subject, refreshKey, reads]);

  const reread = useCallback(() => setReads((count) => count + 1), []);
  return <DescriptiveView data={data} unavailable={unavailable} onReread={reread} />;
}

/** Los indicadores de un dominio: cuántos son y cuántos tienen alguna lectura. */
interface DomainGroup {
  key: string;
  label: string;
  total: number;
  withReadings: number;
}

/** Los dominios en el orden en que el backend sirve su primer indicador. */
function domainGroups(cards: readonly DescriptiveCard[]): DomainGroup[] {
  const groups = new Map<string, DomainGroup>();
  for (const card of cards) {
    const group = groups.get(card.domainKey) ?? { key: card.domainKey, label: card.domain, total: 0, withReadings: 0 };
    group.total += 1;
    if (!card.empty) group.withReadings += 1;
    groups.set(card.domainKey, group);
  }
  return [...groups.values()];
}

/**
 * El anillo (indicadores con alguna lectura en el registro, de los que el backend sirve) y, a su
 * lado, el recuento por dominio (2026-11-08, segunda ronda: con más de cuarenta mosaicos la sección
 * medía cinco vistas). Cada dominio con su dibujo y su palabra del backend, cuántos indicadores
 * tiene, cuántos con lecturas y, si los hay, cuántos sin ninguna con la marca de dato ausente: esa
 * marca no se pliega. Los mosaicos de uno en uno, en su «Ver detalle».
 */
function ReadingsRing({ cards, stale }: { cards: readonly DescriptiveCard[]; stale: boolean }) {
  if (cards.length === 0) return null;
  const withReadings = cards.filter((card) => !card.empty).length;
  return (
    <div className={stale ? "board-row descriptive-board stale" : "board-row descriptive-board"}>
      <div className="ref-ring-col">
        <Ring done={withReadings} total={cards.length} label="indicadores con alguna lectura">
          <span className="num ref-ring-value">{formatNumber(withReadings)}</span>
          <span className="num secondary">/ {formatNumber(cards.length)}</span>
        </Ring>
        <p className="secondary ref-ring-caption">con lecturas</p>
      </div>
      <ul className="descriptive-groups" role="list" aria-label="Indicadores por dominio">
        {domainGroups(cards).map((group) => (
          <li key={group.key} data-descriptive-group={group.key}>
            <span className="descriptive-group-name">
              <DomainName domain={group.key} label={group.label} />{" "}
              <span className="num secondary">({formatNumber(group.total)})</span>
            </span>
            <span className={stale ? "stale" : undefined}>
              con lecturas <span className="num">{formatNumber(group.withReadings)}</span>
            </span>
            {group.withReadings < group.total && (
              <MarkOf mark={MISSING_MARK} stale={stale}>
                sin lecturas <span className="num">{formatNumber(group.total - group.withReadings)}</span>
              </MarkOf>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function InstrumentBlock({ view }: { view: InstrumentView }) {
  return (
    <Fold data-ui="descriptive-instrument" concept="sourceText" label={<>Lo leído de su medida: {view.name}</>}>
      <p className="secondary">{view.scope}</p>
      {view.categories.length > 0 && (
        <>
          <ul>
            {view.categories.map((item) => (
              <li key={item.key}>
                <span className="num">{item.point}</span> ={" "}
                <span lang={view.language}>{item.literal}</span>
              </li>
            ))}
          </ul>
          {view.numbering !== null && <p className="secondary">{view.numbering}</p>}
        </>
      )}
      <ul className="evidence">
        {view.quotes.map((item) => (
          <li key={item.id}>
            {item.label}
            <div>
              <q lang={view.language}>{item.quote}</q>
            </div>
            <div>
              <span lang={view.language}>{item.origin}</span>
              {item.url !== null && <span className="num url"> · {item.url}</span>}
            </div>
          </li>
        ))}
        {view.sources.map((source) => (
          <li key={source.key}>
            <span lang={view.language}>{source.text}</span>
          </li>
        ))}
        {view.notFound.map((line) => (
          <li key={line}>Buscado y no encontrado: {line}</li>
        ))}
      </ul>
    </Fold>
  );
}

/**
 * Un indicador. En la clásica, su ficha, su recuento y su tabla, uno tras otro. En el tablero
 * (2026-11-08, una pantalla por sección; el backend sirve más de cuarenta), un mosaico pequeño: el
 * nombre y el recuento —con la marca de dato ausente si no hay lecturas, que nunca se pliega—; la
 * ficha y la tabla de todos van juntas en un solo «Ver detalle» bajo los mosaicos (`CardDetail`).
 */
function cardParts(card: DescriptiveCard, stale: boolean) {
  const numClass = stale ? "num stale" : "num";
  const ficha = (
    <>
      <p className="secondary">
        {/* `wrap`: el código propio («código propio de EMMA · urine-caox-…») salía del panel en
            tableta vertical (§5.40). */}
        <span className="num wrap">{card.code}</span> · <DomainName domain={card.domainKey} label={card.domain} /> ·{" "}
        {card.range}
        {card.equipment !== null && <> · {card.equipment}</>}
      </p>
      <p className="secondary">{card.codeBasis}</p>
      {card.searched !== null && <p className="secondary">{card.searched}</p>}
      {card.loincUrl !== null && (
        <p className="secondary">
          Ficha consultada: <span className="num url">{card.loincUrl}</span>
        </p>
      )}
      <p className="secondary">{card.how}</p>
      {card.instrument !== null && <InstrumentBlock view={card.instrument} />}
    </>
  );
  // Sin color ni pictograma de nivel: un indicador descriptivo no avisa de nada. Sin lecturas, la
  // marca de dato ausente, que no es de nivel.
  const count = card.empty ? (
    <p>
      <MarkOf mark={MISSING_MARK} stale={stale}>
        {card.count}
      </MarkOf>
    </p>
  ) : (
    <p className={stale ? "stale" : undefined}>{card.count}</p>
  );
  const table = card.rows.length > 0 && (
    <div className="quality-table">
      {card.shown !== null && <p className={stale ? "secondary stale" : "secondary"}>{card.shown}</p>}
      <table className="ledger">
        <thead>
          <tr>
            <Th concept="time">Hora</Th>
            <Th concept="value">Valor</Th>
            <Th concept="provenance">Procedencia</Th>
            <Th concept="person">Quién anota</Th>
          </tr>
        </thead>
        <tbody>
          {card.rows.map((row) => (
            <tr key={row.key}>
              <td className={numClass}>{row.when}</td>
              <td className={numClass}>{row.value}</td>
              <td>
                <ObservationTypeBadge type={row.observationType} context={row.evidenceContext} />{" "}
                · {row.source}
              </td>
              <td>
                <MarkOf mark={row.recordedByMark}>{row.recordedBy}</MarkOf>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return { ficha, count, table };
}

function Card({ card, stale, board }: { card: DescriptiveCard; stale: boolean; board: boolean }) {
  const { ficha, count, table } = cardParts(card, stale);
  return (
    <div data-descriptive={card.key}>
      <h3>
        <IndicatorName indicatorKey={card.key} displayEs={card.title} />
      </h3>
      {!board && ficha}
      {count}
      {!board && table}
    </div>
  );
}

/** En el tablero, la ficha y las lecturas de un indicador dentro del detalle común; el nombre, sin dibujo (ya va en su mosaico). */
function CardDetail({ card, stale }: { card: DescriptiveCard; stale: boolean }) {
  const { ficha, table } = cardParts(card, stale);
  return (
    <div className="descriptive-detail" data-descriptive-detail={card.key}>
      <p>
        <strong>{card.title}</strong>
      </p>
      {ficha}
      {table}
    </div>
  );
}

/** Solo pinta. Separado de la carga para poder probar lo que se lee en pantalla. */
export function DescriptiveView({
  data,
  unavailable,
  onReread,
}: {
  data: DescriptiveIndicators | null;
  unavailable: RequestOutcome | null;
  onReread?: () => void;
}) {
  // En el tablero, mosaicos pequeños y un solo detalle común (ver `Card`).
  const board = useLook() === "reference";
  const reread = onReread !== undefined && (
    <Command concept="reread" type="button" onClick={onReread}>
      Volver a leer
    </Command>
  );
  if (data === null) {
    return (
      <section data-ui="descriptive" className="panel" aria-label="Indicadores descriptivos">
        <PanelTitle concept="descriptive">Indicadores descriptivos</PanelTitle>
        {unavailable !== null ? (
          <Unavailable outcome={unavailable} />
        ) : (
          <Loading />
        )}
        {reread}
      </section>
    );
  }
  const view = descriptiveView(data);
  return (
    <section data-ui="descriptive" className="panel" aria-label="Indicadores descriptivos" data-descriptive-indicators>
      <PanelTitle concept="descriptive">Indicadores descriptivos</PanelTitle>
      {view.empty ? (
        // Ninguna lectura de ningún descriptivo: el recuento del backend con la marca de registro
        // vacío (§5.34.14), la del diario. El cian queda para la tarjeta de un indicador sin
        // lecturas, que es un dato concreto que falta.
        <p>
          <MarkOf mark={EMPTY_MARK} stale={unavailable !== null}>
            {view.statement}
          </MarkOf>
        </p>
      ) : (
        <p className={unavailable !== null ? "stale" : undefined}>{view.statement}</p>
      )}
      <BoardOnly>
        <ReadingsRing cards={view.cards} stale={unavailable !== null} />
      </BoardOnly>
      <p className="secondary">{view.scope}</p>
      {unavailable !== null && <Unavailable outcome={unavailable} />}
      {reread}
      {/* Si la última lectura falló, las tarjetas son las de antes: caducadas, con la cursiva en
          sus cifras además del «Sin datos» con la marca de la petición (§5.33, §5.34.14). */}
      {board ? (
        // Tablero: el recuento por dominio va arriba (`ReadingsRing`); los mosaicos de cada
        // indicador, con su marca de dato ausente, en su «Ver detalle».
        view.cards.length > 0 && (
          <BoardDetail label="recuento de cada indicador" className="descriptive-tiles-detail">
            <div className="descriptive-tiles">
              {view.cards.map((card) => (
                <Card key={card.key} card={card} stale={unavailable !== null} board />
              ))}
            </div>
          </BoardDetail>
        )
      ) : (
        view.cards.map((card) => <Card key={card.key} card={card} stale={unavailable !== null} board={false} />)
      )}
      {board && view.cards.length > 0 && (
        <BoardDetail label="ficha y lecturas de cada indicador" className="descriptive-details">
          {view.cards.map((card) => (
            <CardDetail key={card.key} card={card} stale={unavailable !== null} />
          ))}
        </BoardDetail>
      )}
    </section>
  );
}
