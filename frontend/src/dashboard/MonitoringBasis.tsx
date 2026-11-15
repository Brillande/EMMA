import type { ReactNode } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { Meter } from "../components/Meter";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import type { CrewStatus } from "../lib/api";
import { formatNumber } from "../lib/format";
import { contextLabel, contextPictogram, typeStyle } from "../lib/provenance";
import { Ring } from "./HomeCharts";
import { AVAILABLE_MARK, capabilityPictogram, causeMark, isKnownCause, reducedMark } from "./monitoring";
import { markTint } from "./TimelinePieces";

/**
 * Los dos primeros paneles de «Calidad y sensores»: qué vigila el sistema («Vigilancia») y sobre qué
 * se apoya el veredicto («En qué se apoya»). Vivían dentro de `CrewConsole.tsx`; salen a su fichero
 * (tablero por secciones, 2026-11-07) para que la sección tenga dueño propio y pueda montar sus
 * piezas sin tocar la tabla de la consola.
 *
 * Tablero (decisión del usuario, 2026-11-07: cada sección como «Inicio» pero con sus apartados): bajo
 * la concha de la maqueta (`BoardOnly`), cada panel monta sus piezas con los datos que ya tenía. En
 * «Vigilancia», el anillo de cuántas capacidades están disponibles de las que hay y, al lado, una
 * píldora por causa conocida de las que faltan, con la misma marca y la misma palabra que llevan sus
 * filas (`causeWord`). El anillo va neutro, como el medidor: «disponible» no lleva color en este
 * panel (`AVAILABLE_MARK`) y el verde del anillo de «Inicio» lo pintaría de nominal (`shell/data.css`). En «En qué se apoya», dos fichas con cifra: las lecturas analizadas y la parte juzgada contra
 * la base personal, con su medidor sobre el total (la escala es 0..1, la de la propia fracción). Nada
 * nuevo se pide ni se redacta: son las cifras que ya escribían las definiciones de abajo.
 */

/**
 * La palabra de una causa conocida de una capacidad que falta, una sola vez para la fila de la
 * capacidad y para su píldora del tablero. Una causa que la interfaz no conoce no tiene palabra
 * (ni píldora): su fila la dice con la frase del backend, sin suponerle un motivo.
 */
function causeWord(cause: string): string {
  return cause === "manual" ? "restringido por decisión manual" : "sin datos";
}

/**
 * Que esta vigilando el sistema y que no. F.6.2: la tripulacion tiene que saber
 * cuando un problema queda fuera de la capacidad del sistema. Cada capacidad caida
 * dice lo que deja de vigilarse, escrito por el backend. Cada capacidad lleva su dibujo
 * junto al nombre, y delante la señal de su estado: hecho, dato ausente o decision manual
 * (`monitoring.ts`). Una causa que la interfaz no conoce va con el nombre, la marca de
 * «desconocido» y la frase del backend, sin suponerle un motivo.
 */
export function MonitoringPanel({ monitoring }: { monitoring: CrewStatus["monitoring"] }) {
  const reduced = reducedMark(monitoring.capabilities);
  const total = monitoring.capabilities.length;
  const available = monitoring.capabilities.filter((item) => item.available).length;
  // Tablero: cuántas faltan por cada causa conocida, en el orden de sus filas; solo las que hay.
  const tally = new Map<string, number>();
  for (const item of monitoring.capabilities) {
    const why = item.cause ?? "";
    if (!item.available && isKnownCause(why)) tally.set(why, (tally.get(why) ?? 0) + 1);
  }
  return (
    <section data-ui="monitoring" className="panel" aria-label="Capacidad de vigilancia">
      <PanelTitle concept="monitoring">
        Vigilancia{" "}
        {monitoring.level === "full" ? (
          <span className="secondary">completa</span>
        ) : (
          <MarkOf mark={reduced}>reducida</MarkOf>
        )}
      </PanelTitle>
      {total > 0 && (
        <BoardOnly>
          <div className="board-row monitoring-board">
            <div className="ref-ring-col">
              <Ring done={available} total={total} label="capacidades">
                <span className="num ref-ring-value">{formatNumber(available)}</span>
                <span className="num secondary">/ {formatNumber(total)}</span>
              </Ring>
              <p className="secondary ref-ring-caption">disponibles</p>
            </div>
            {tally.size > 0 && (
              <ul className="board-tally" aria-label="Capacidades que faltan, por causa">
                {[...tally].map(([why, count]) => {
                  const look = causeMark(why);
                  return (
                    <li key={why} className="ref-pill board-pill" style={markTint(look)}>
                      <MarkOf mark={look}>{causeWord(why)}</MarkOf> <span className="num">{formatNumber(count)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </BoardOnly>
      )}
      <ul className="capabilities">
        {monitoring.capabilities.map((item) => {
          const name = <Mark pictogram={capabilityPictogram(item.key)}>{item.label}</Mark>;
          if (item.available) {
            return (
              <li key={item.key}>
                <Mark pictogram={AVAILABLE_MARK.pictogram} color={AVAILABLE_MARK.color}>
                  {name}
                </Mark>
              </li>
            );
          }
          const why = item.cause ?? "";
          const cause = causeMark(why);
          return (
            <li key={item.key}>
              <Mark pictogram={cause.pictogram} color={cause.color}>
                {name}
                {isKnownCause(why) && `: ${causeWord(why)}`}
              </Mark>
              <p className="secondary">{item.consequence}</p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/**
 * Sobre que se apoya el veredicto. "Nominal" sin base personal significa "no ha
 * cruzado ningun limite grave", no "esta como siempre" (backend, `data.basis`).
 * F.6.2: el operador puede comprobar la informacion que usa la automatizacion. Los tipos de
 * dato y los entornos van con su pictograma (`lib/provenance.ts`), como en los rotulos.
 */
export function Basis({ status }: { status: CrewStatus }) {
  const board = useLook() === "reference";
  const data = status.data;
  const ignored = Object.values(data.readings_ignored).reduce((a, b) => a + b, 0);
  const fraction = data.personal_baseline_fraction;
  // Las filas de la definición, en el orden de siempre. «Base» (la frase del backend que dice sobre
  // qué se apoya el veredicto), «Sin decidir» y «Apartadas» (lecturas que el veredicto no leyó) van
  // siempre a la vista, y las notas del motor también (el ajuste por aislamiento es el aviso del
  // retardo); las demás son cifras que ya llevan las fichas, reglas del motor y procedencia.
  const base = (
    <>
      <FieldLabel as="dt" concept="basis">
        Base
      </FieldLabel>
      <dd>{data.basis}</dd>
    </>
  );
  const rules = (
    <>
      <FieldLabel as="dt" concept="baseline">
        Base personal
      </FieldLabel>
      <dd className="num">{formatNumber(data.personal_baseline_fraction * 100)} %</dd>
      <FieldLabel as="dt" concept="value">
        Lecturas analizadas
      </FieldLabel>
      <dd className="num">{formatNumber(data.observations)}</dd>
      <FieldLabel as="dt" concept="time">
        Ventanas
      </FieldLabel>
      <dd>
        desviación <span className="num">{data.deviation_window_days}</span> d · tendencia{" "}
        <span className="num">{data.trend_window_days}</span> d
      </dd>
      <FieldLabel as="dt" concept="document">
        Reglas
      </FieldLabel>
      <dd className="num">{status.rules_version}</dd>
      <FieldLabel as="dt" concept="type">
        Tipo de dato
      </FieldLabel>
      <dd>
        {tally(status.provenance.observation_type, (key) => (
          <Mark pictogram={typeStyle(key).pictogram}>{typeStyle(key).word}</Mark>
        ))}
      </dd>
    </>
  );
  // Lo que el veredicto no leyó por su tipo (§5.37.1): firmado, rotulado y sin decidir.
  const undecided = status.provenance.set_aside !== undefined && Object.keys(status.provenance.set_aside).length > 0 && (
    <>
      <FieldLabel as="dt" concept="type">
        Sin decidir
      </FieldLabel>
      <dd>
        {tally(status.provenance.set_aside, (key) => (
          <Mark pictogram={typeStyle(key).pictogram}>{typeStyle(key).word}</Mark>
        ))}
        {status.provenance.rule !== undefined && <p className="secondary">{status.provenance.rule}</p>}
      </dd>
    </>
  );
  const context = (
    <>
      <FieldLabel as="dt" concept="provenance">
        Entorno
      </FieldLabel>
      <dd>
        {tally(status.provenance.evidence_context, (key) => (
          <Mark pictogram={contextPictogram(key)}>{contextLabel(key)}</Mark>
        ))}
      </dd>
    </>
  );
  const setAside = ignored > 0 && (
    <>
      <FieldLabel as="dt" concept="date">
        Apartadas
      </FieldLabel>
      <dd className="num">
        <Mark pictogram="shape-triangle" color="yellow">
          {formatNumber(ignored)} con fecha no analizable
        </Mark>
      </dd>
    </>
  );
  const notes = status.notes.map((note) => (
    <p className="secondary" key={note}>
      {note}
    </p>
  ));
  return (
    <section data-ui="verdict-basis" className="panel" aria-label="Base del veredicto">
      <PanelTitle concept="basis">En qué se apoya</PanelTitle>
      {/* Tablero: las dos cifras de la base como fichas; el medidor solo con una fracción dentro de
          su escala (fuera de 0..1 el backend habría dado algo que no es una fracción, y el medidor
          lanzaría: la definición de abajo sigue diciendo el tanto por ciento). */}
      <BoardOnly>
        <div className="board-stats" role="group" aria-label="Cifras de la base del veredicto">
          <StatTile concept="value" label="Lecturas analizadas" value={data.observations} />
          <StatTile concept="baseline" label="Base personal" value={fraction * 100} unit="%">
            {fraction >= 0 && fraction <= 1 && (
              <Meter value={fraction} max={1} label="Parte de las lecturas juzgadas contra la base personal" />
            )}
          </StatTile>
        </div>
      </BoardOnly>
      {board ? (
        // Tablero (lote «muestra», 2026-11-08: la sección medía ~2700 px): a la vista la frase de la
        // base, lo que el veredicto no leyó y las notas del motor; las cifras que ya van en las
        // fichas, las ventanas, las reglas y la procedencia, detrás de «Ver detalle». Abierto, el
        // mismo texto; en la clásica, la definición entera como siempre.
        <>
          <dl className="kv">
            {base}
            {undecided}
            {setAside}
          </dl>
          {notes}
          <BoardDetail label="base del veredicto">
            <dl className="kv">
              {rules}
              {context}
            </dl>
          </BoardDetail>
        </>
      ) : (
        <>
          <dl className="kv">
            {base}
            {rules}
            {undecided}
            {context}
            {setAside}
          </dl>
          {notes}
        </>
      )}
    </section>
  );
}

/** Cada clave con su nombre (palabra y pictograma) y su cuenta, de mas a menos, separadas por «·». */
function tally(counts: Record<string, number>, name: (key: string) => ReactNode): ReactNode[] {
  return Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .map(([key, count], index) => (
      <span key={key}>
        {index > 0 && " · "}
        {name(key)} <span className="num">{formatNumber(count)}</span>
      </span>
    ));
}
