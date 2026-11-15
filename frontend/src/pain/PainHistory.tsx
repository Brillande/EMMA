import { Fragment, useEffect, useState } from "react";

import { BoardOnly } from "../components/BoardOnly";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import { DAY_SECONDS, type Reading, Sparkline } from "../dashboard/HomeCharts";
import { type PainCatalog, type PainDiscussion, type PainReport, api } from "../lib/api";
import { useArrivalCheck, useFixedRequest } from "../lib/arrival";
import { formatNumber } from "../lib/format";
import { hasIndicatorFamily, indicatorFamily } from "../lib/indicatorFamily";
import {
  type StateMark,
  EMPTY_MARK,
  OK_MARK,
  UNKNOWN_PICTOGRAM,
  mark,
  type RequestOutcome,
  requestOutcome,
} from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { characterMark } from "./characters";
import { type Change, evolution } from "./evolution";
import { tr } from "../lib/i18n";

/**
 * Evolucion por zona: la intensidad ahora, la del informe anterior y hacia donde va.
 *
 * Sin rojo ni amarillo (ver `evolution.ts`): el cambio se dice con palabras y pictogramas, y la
 * valoracion es de quien lo lee. Los nombres de zona y de carácter son los del backend; cada
 * carácter lleva el dibujo de `characters.ts` junto a su palabra. Cada cabecera, el signo de su
 * concepto (`lib/uiMarks.ts`, §5.33.9); la lista vacía, el anillo punteado sin color.
 */
export function PainEvolution({
  reports,
  catalog,
}: {
  reports: readonly PainReport[];
  catalog: PainCatalog;
}) {
  const names = Object.fromEntries(catalog.zones.map((zone) => [zone.key, zone.display]));
  const characters = Object.fromEntries(
    catalog.characters.map((item) => [item.key, item.display]),
  );
  const rows = evolution(reports);
  const latest = reports.at(-1);
  if (latest === undefined) {
    return (
      <p className="secondary">
        <MarkOf mark={EMPTY_MARK}>{tr("Sin informes de dolor registrados.", "No pain reports recorded.")}</MarkOf>
      </p>
    );
  }
  return (
    <>
      <p className="secondary">
        {tr("Último informe:", "Latest report:")} {latest.effective.slice(0, 16).replace("T", " ")} UTC,{" "}
        {tr("de", "by")}{" "}
        {latest.reported_by} ·{" "}
        {latest.zones.length === 0 ? (
          tr("sin dolor", "no pain")
        ) : (
          <>
            {tr("máximo", "maximum")} <span className="num">{formatNumber(latest.intensity)}</span> {tr("de", "of")}{" "}
            <span className="num">{formatNumber(catalog.scale.max)}</span>
          </>
        )}{" "}
        · <span className="num">{formatNumber(reports.length)}</span> {tr("informes", "reports")}
      </p>
      <DiscussNote discussion={latest.discuss} />
      {rows.length > 0 && (
        <div className="quality-table">
        <table className="ledger">
          <thead>
            <tr>
              <Th concept="zone">{tr("Zona", "Zone")}</Th>
              <Th concept="time">{tr("Ahora", "Now")}</Th>
              <Th concept="previous">{tr("Anterior", "Previous")}</Th>
              <Th concept="change">{tr("Cambio", "Change")}</Th>
              <Th concept="type">{tr("Tipo (último)", "Type (latest)")}</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const now = latest.zones.find((zone) => zone.zone === row.zone);
              return (
                <tr key={row.zone}>
                  <td>{names[row.zone] ?? row.zone}</td>
                  <td className="num">{formatNumber(row.latest)}</td>
                  <td className="num">
                    {row.previous === null ? "—" : formatNumber(row.previous)}
                  </td>
                  <td>
                    <ChangeMark change={row.change} />
                  </td>
                  <td>
                    <Characters keys={now?.characters ?? []} names={characters} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}
    </>
  );
}

/**
 * Palabra y pictograma de cada cambio: no se lee solo por un simbolo ni por un color (F.5.10 e).
 * Sin color (ver `evolution.ts`): triangulos llenos hacia arriba y hacia abajo y el signo igual,
 * el mismo dibujo que tenian los glifos de texto ▲ ▼ =. La zona que se marca por primera vez
 * llevaba ●, que es «medido» (`dot-filled`); lleva el anillo con punto de «elegido / actual»
 * (`ring-dot`, el concepto `chosen` del vocabulario): la que entra ahora en la serie.
 */
export const CHANGES: Readonly<Record<Change, { word: string; mark: StateMark }>> = {
  sube: { word: tr("sube", "up"), mark: mark("triangle-up-filled", null) },
  baja: { word: tr("baja", "down"), mark: mark("triangle-down-filled", null) },
  igual: { word: tr("igual", "same"), mark: mark("equals", null) },
  nueva: { word: tr("primera vez", "first time"), mark: mark(uiPictogram("chosen"), null) },
};

function ChangeMark({ change }: { change: Change }) {
  return <Mark pictogram={CHANGES[change].mark.pictogram}>{CHANGES[change].word}</Mark>;
}

/** Los caracteres de una zona, cada uno con su dibujo y su palabra del backend; «—» si no hay. */
function Characters({ keys, names }: { keys: readonly string[]; names: Record<string, string> }) {
  if (keys.length === 0) return <>—</>;
  return (
    <>
      {keys.map((key, index) => (
        // La clave lleva el indice: un informe antiguo del ledger podria repetir un caracter.
        <Fragment key={`${key}-${index}`}>
          {index > 0 && ", "}
          <Mark pictogram={characterMark(key).pictogram}>{names[key] ?? key}</Mark>
        </Fragment>
      ))}
    </>
  );
}

/**
 * Marca informativa del backend, tal cual (la interfaz no redacta texto clinico). No es una
 * alerta: no entra en el riesgo. Por eso va en texto neutro, sin rojo ni amarillo, la misma
 * regla que la intensidad del mapa (`compliance/hmi-state-of-the-art.md` §5.2).
 */
function DiscussNote({ discussion }: { discussion: PainDiscussion | undefined }) {
  if (discussion === undefined || discussion.note === null || discussion.reasons.length === 0) {
    return null;
  }
  return (
    <p className="secondary">
      {discussion.note} ({discussion.reasons.join(", ")})
    </p>
  );
}

/**
 * Dolor en la consola de Tierra: solo los informes que ya pueden haber llegado.
 *
 * Mismo corte que las ecografias: un informe registrado a bordo hace menos de un tiempo de
 * luz esta en transito y no se lista. Bajo la concha de la maqueta, encima de la evolución, las
 * fichas de lo llegado con la curva de la intensidad (`ReceivedPainBoard`).
 */
export function PainHistory({
  subject,
  oneWayMinutes,
}: {
  subject: string;
  oneWayMinutes: number | null;
}) {
  // Lo cargado y lo fallido van con el tripulante del que son, como en el historial misión a
  // misión: al cambiar de tripulante no se pintan ni un instante los informes del anterior bajo
  // el nuevo, y una lectura buena quita el aviso de una que falló antes (§5.37.17, revisión).
  const [loaded, setLoaded] = useState<{
    subject: string;
    catalog: PainCatalog;
    reports: PainReport[];
  } | null>(null);
  const [failed, setFailed] = useState<{ subject: string; outcome: RequestOutcome } | null>(null);
  // El corte del reloj, cada 30 s y con el último tiempo de luz (`useArrivalCheck`, §5.37.17).
  const { checkKey, cutNow } = useArrivalCheck(oneWayMinutes);
  // El catálogo de zonas es fijo: una vez, no en cada vuelta del reloj (§5.38.12).
  const zoneCatalog = useFixedRequest(api.pain.catalog);

  useEffect(() => {
    let cancelled = false;
    Promise.all([zoneCatalog(), api.pain.reports(subject, cutNow())])
      .then(([zones, received]) => {
        if (cancelled) return;
        setLoaded({ subject, catalog: zones, reports: received });
        setFailed(null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setFailed({ subject, outcome: requestOutcome(reason) });
      });
    return () => {
      cancelled = true;
    };
  }, [subject, checkKey, cutNow, zoneCatalog]);

  const current = loaded?.subject === subject ? loaded : null;
  const error = failed?.subject === subject ? failed.outcome : null;
  const catalog = current?.catalog ?? null;
  const reports = current?.reports ?? [];

  return (
    <section data-ui="pain-history" className="panel" aria-label={tr("Dolor referido", "Reported pain")}>
      <PanelTitle concept="pain">{tr("Dolor referido", "Reported pain")}</PanelTitle>
      {error !== null && (
        <p>
          <MarkOf mark={error.mark}>
            {tr("No se pudieron cargar los informes:", "Could not load the reports:")} {error.text}
          </MarkOf>
        </p>
      )}
      {catalog !== null && (
        <BoardOnly>
          <ReceivedPainBoard reports={reports} catalog={catalog} stale={error !== null} />
        </BoardOnly>
      )}
      {catalog !== null && <PainEvolution reports={reports} catalog={catalog} />}
    </section>
  );
}

/** Una semana: el suelo de la ventana de la curva de la intensidad. */
const WEEK_MS = 7 * DAY_SECONDS * 1000;

/**
 * Las fichas de lo llegado a Tierra (tablero, 2026-11-07): la intensidad máxima del último informe
 * llegado con su curva, las zonas y los informes. La curva es la intensidad máxima de cada informe
 * (`intensity`, la cifra que entra en el análisis) por su hora firmada, con la ventana de la propia
 * serie (del primero al último, con una semana de suelo), solo con dos o más informes y sin escala
 * propia: la cifra escrita es la que se lee. Es la misma tira que la de a bordo (`PainPanel`), que no
 * es de esta unidad y no la exporta; aquí solo con lo que ya pasó el corte del retardo. Sin informes
 * no hay fichas: la lista de abajo ya lo dice con su marca. Si la última lectura falló, las fichas
 * conservan lo que había, en cursiva (`stale`).
 */
export function ReceivedPainBoard({
  reports,
  catalog,
  stale,
}: {
  reports: readonly PainReport[];
  catalog: PainCatalog;
  stale: boolean;
}) {
  const latest = reports.at(-1);
  if (latest === undefined) return null;
  const readings: Reading[] = reports
    .map((report) => ({ at: new Date(report.effective).getTime(), value: report.intensity }))
    .filter((reading) => Number.isFinite(reading.at))
    .sort((a, b) => a.at - b.at);
  const first = readings[0];
  const last = readings.at(-1);
  const curve =
    first !== undefined && last !== undefined && readings.length >= 2 ? (
      <Sparkline readings={readings} until={last.at} windowMs={Math.max(last.at - first.at, WEEK_MS)} />
    ) : null;
  const intensity = hasIndicatorFamily("pain-intensity") ? indicatorFamily("pain-intensity") : UNKNOWN_PICTOGRAM;
  return (
    <div className="board-stats pain-board" role="group" aria-label={tr("Último informe de dolor llegado", "Latest pain report received")}>
      {latest.zones.length === 0 ? (
        <StatTile pictogram={intensity} label={tr("Intensidad máxima", "Maximum intensity")} value={null} status={{ mark: OK_MARK, word: tr("sin dolor", "no pain") }} stale={stale}>
          {curve}
        </StatTile>
      ) : (
        <StatTile
          pictogram={intensity}
          label={tr("Intensidad máxima", "Maximum intensity")}
          value={latest.intensity}
          unit={`${tr("de", "of")} ${formatNumber(catalog.scale.max)}`}
          stale={stale}
        >
          {curve}
        </StatTile>
      )}
      <StatTile concept="zone" label={tr("Zonas", "Zones")} value={latest.zones.length} stale={stale} />
      <StatTile concept="history" label={tr("Informes", "Reports")} value={reports.length} stale={stale} />
    </div>
  );
}
