import { useEffect, useState } from "react";

import { FieldLabel } from "../components/FieldLabel";
import { IndicatorName } from "../components/IndicatorName";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { type CycleRecord, type CycleRowView, cycleRow, loadCycleCatalog, loadCycleRecords } from "../lib/cycleApi";
import { type CrewSex, getCrewSex } from "../lib/crewSexApi";
import { MISSING_MARK, type RequestOutcome, UNAVAILABLE_MARK, requestOutcome } from "../lib/marks";
import { CREW_SEX_WORDS } from "./SexForm";
import "./cycle.css";
import { tr } from "../lib/i18n";

/**
 * El ciclo menstrual y la anticoncepción, tal como constan en el registro firmado (lote «ciclo»,
 * 2026-11-14: «que EMMA contemple las afecciones hormonales y menstruales»).
 *
 * Por qué existe: los registros del ciclo (flujo, inicio de regla, manchado, test de ovulación,
 * anticonceptivo en uso, temperatura basal) entran como indicadores descriptivos (unidad A3) y el
 * estado no los lee; sin este panel no había dónde ver el último de cada uno junto a si la línea
 * base tiene en cuenta la fase.
 *
 * Solo se ofrece con el sexo declarado femenino. Sin declarar, o declarado masculino, el panel no
 * se esconde: dice que no aplica y cómo se declara (rótulos de interfaz, no texto clínico).
 *
 * Nada se redacta aquí: el nombre de cada indicador, la palabra de cada número (en el idioma de la
 * fuente) y la palabra de «no declarado» son del backend; las cifras y las horas, de
 * `lib/format.ts`. Sin color de nivel: un registro del ciclo no es un aviso. Lo que falta lleva la
 * marca de dato ausente (cian); lo pintado de antes, si la última lectura falló, la misma marca y
 * la cursiva (`lib/cycleApi.ts` explica por qué no hay otro «caducado»).
 *
 * La línea base por fase («ajustada por fase / sin ajuste: faltan datos») la decide el backend
 * (unidad B3). Llega por `phaseBaseline`, la frase tal cual; mientras no llegue, «no disponible»
 * en gris, nunca un valor supuesto.
 *
 * En Tierra, con `until`: lo que ya ha llegado hasta el corte del retardo, y sin mando.
 */
export function CyclePanel({
  subject,
  refreshKey,
  until,
  ground = false,
  phaseBaseline,
}: {
  subject: string;
  /** Cambia cuando cambian los datos del estado (o tras declarar el sexo): se vuelve a leer. */
  refreshKey: string;
  /** El corte de reloj de Tierra; sin él, lo vigente. */
  until?: Date | undefined;
  /** Consola de Tierra: cambia solo el rótulo de cómo se declara el sexo. */
  ground?: boolean;
  /** La frase del backend sobre la línea base por fase; `null`/ausente: no disponible. */
  phaseBaseline?: string | null | undefined;
}) {
  const [sex, setSex] = useState<CrewSex | null>(null);
  const [records, setRecords] = useState<CycleRecord[] | null>(null);
  const [unavailable, setUnavailable] = useState<RequestOutcome | null>(null);
  const cut = until?.toISOString();

  // Otro tripulante: lo pintado era del anterior.
  useEffect(() => {
    setSex(null);
    setRecords(null);
    setUnavailable(null);
  }, [subject]);

  useEffect(() => {
    let alive = true;
    const at = cut === undefined ? undefined : new Date(cut);
    // El sexo y el catálogo a la vez; las lecturas, solo cuando el seguimiento aplica.
    Promise.all([getCrewSex(at, subject), loadCycleCatalog(subject)])
      .then(async ([declared, catalog]) => {
        const found =
          declared.declared && declared.sex === "female" ? await loadCycleRecords(subject, catalog, at) : null;
        if (!alive) return;
        setSex(declared);
        setRecords(found);
        setUnavailable(null);
      })
      .catch((reason: unknown) => {
        if (alive) setUnavailable(requestOutcome(reason));
      });
    return () => {
      alive = false;
    };
  }, [subject, refreshKey, cut]);

  return (
    <CycleView sex={sex} records={records} unavailable={unavailable} ground={ground} phaseBaseline={phaseBaseline} />
  );
}

/** Rótulo de interfaz: dónde se declara el sexo, según la consola. */
export const HOW_TO_DECLARE = {
  crew: tr(
    "Se declara en el apartado «Sexo declarado», con quién lo declara.",
    "It is declared in the “Declared sex” section, along with who declares it.",
  ),
  ground: tr(
    "Lo declara el propio tripulante desde su consola; aquí llega con el retardo.",
    "The crew member declares it from their own console; it arrives here with the delay.",
  ),
} as const;

/** Rótulo de interfaz: el seguimiento no se ofrece. */
export const NOT_APPLICABLE = tr("El seguimiento del ciclo no aplica", "Cycle tracking does not apply");

/** Solo pinta. Separado de la carga para poder probar lo que se lee en pantalla. */
export function CycleView({
  sex,
  records,
  unavailable,
  ground,
  phaseBaseline,
}: {
  sex: CrewSex | null;
  records: CycleRecord[] | null;
  unavailable: RequestOutcome | null;
  ground: boolean;
  phaseBaseline?: string | null | undefined;
}) {
  const title = <PanelTitle concept="descriptive">{tr("Ciclo menstrual", "Menstrual cycle")}</PanelTitle>;
  if (sex === null) {
    return (
      <section data-ui="cycle" className="panel cycle-panel" aria-label={tr("Ciclo menstrual", "Menstrual cycle")}>
        {title}
        {unavailable !== null ? <Unavailable outcome={unavailable} /> : <Loading />}
      </section>
    );
  }
  const stale = unavailable !== null;
  const applies = sex.declared && sex.sex === "female";
  return (
    <section data-ui="cycle" className="panel cycle-panel" aria-label={tr("Ciclo menstrual", "Menstrual cycle")} data-cycle={applies ? "applies" : "not-applicable"}>
      {title}
      {unavailable !== null && <Unavailable outcome={unavailable} />}
      {applies ? (
        <>
          <PhaseBaseline text={phaseBaseline} />
          <CycleRecords rows={(records ?? []).map(cycleRow)} stale={stale} />
        </>
      ) : (
        <NotApplicable sex={sex} ground={ground} stale={stale} />
      )}
    </section>
  );
}

/** Sin declarar o declarado masculino: no aplica, con lo declarado y cómo se declara. */
function NotApplicable({ sex, ground, stale }: { sex: CrewSex; ground: boolean; stale: boolean }) {
  return (
    <div className="cycle-not-applicable">
      <p>
        <FieldLabel as="span" concept="identity" className="cycle-label">
          {tr("Sexo declarado", "Declared sex")}
        </FieldLabel>{" "}
        {sex.declared ? (
          stale ? (
            // Lo de antes: la marca de dato caducado y la cursiva, como en las tarjetas.
            <MarkOf mark={MISSING_MARK} stale>
              {CREW_SEX_WORDS[sex.sex]}
            </MarkOf>
          ) : (
            <span>{CREW_SEX_WORDS[sex.sex]}</span>
          )
        ) : (
          <MarkOf mark={UNAVAILABLE_MARK} stale={stale}>
            {sex.status}
          </MarkOf>
        )}
      </p>
      <p>{NOT_APPLICABLE}.</p>
      <p className="secondary">{ground ? HOW_TO_DECLARE.ground : HOW_TO_DECLARE.crew}</p>
    </div>
  );
}

/** La frase del backend sobre la base por fase; sin ella, «no disponible» en gris. */
function PhaseBaseline({ text }: { text: string | null | undefined }) {
  return (
    <p className="cycle-phase" data-cycle-phase={text === null || text === undefined ? "unavailable" : "given"}>
      <FieldLabel as="span" concept="baseline" className="cycle-label">
        {tr("Línea base por fase", "Baseline by phase")}
      </FieldLabel>{" "}
      {text === null || text === undefined ? <MarkOf mark={UNAVAILABLE_MARK}>{tr("no disponible", "not available")}</MarkOf> : <span>{text}</span>}
    </p>
  );
}

/** El último registro de cada indicador del ciclo, en tarjetas. */
function CycleRecords({ rows, stale }: { rows: CycleRowView[]; stale: boolean }) {
  if (rows.length === 0) {
    return (
      <p>
        <MarkOf mark={MISSING_MARK} stale={stale}>
          {tr("Sin indicadores del ciclo en el catálogo", "No cycle indicators in the catalog")}
        </MarkOf>
      </p>
    );
  }
  return (
    <ul className="cycle-records" role="list" aria-label={tr("Último registro de cada indicador del ciclo", "Latest record of each cycle indicator")}>
      {rows.map((row) => (
        <li key={row.key} className="cycle-record" data-cycle-record={row.key}>
          <span className="cycle-record-name">
            <IndicatorName indicatorKey={row.key} displayEs={row.name} />
          </span>
          {row.empty ? (
            <MarkOf mark={MISSING_MARK} stale={stale}>
              {tr("Sin lecturas", "No readings")}
            </MarkOf>
          ) : (
            <RecordValue row={row} stale={stale} />
          )}
        </li>
      ))}
    </ul>
  );
}

function RecordValue({ row, stale }: { row: Extract<CycleRowView, { empty: false }>; stale: boolean }) {
  const value =
    row.word === null ? (
      <span className="num">{row.figure}</span>
    ) : (
      <>
        <span lang={row.language ?? undefined}>{row.word}</span> <span className="num secondary">({row.figure})</span>
      </>
    );
  return (
    <>
      <span className="cycle-record-value">
        {stale ? (
          // Lo de antes: la marca de dato caducado (cian, anillo punteado) y la cursiva.
          <MarkOf mark={MISSING_MARK} stale>
            {value}
          </MarkOf>
        ) : (
          value
        )}
      </span>
      <span className={stale ? "secondary stale" : "secondary"}>
        <span className="num">{row.when}</span>
      </span>
    </>
  );
}
