import { type FormEvent, useEffect, useId, useState } from "react";

import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Loading, Unavailable } from "../components/Unavailable";
import { type BaselinePersonalData, baselineApi } from "../lib/api";
import {
  CREW_SEX_VALUES,
  type CrewSex,
  type CrewSexValue,
  declareCrewSex,
  getCrewSex,
} from "../lib/crewSexApi";
import { formatNumber, formatUtc } from "../lib/format";
import { type RequestOutcome, UNAVAILABLE_MARK, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import "./cycle.css";
import { tr } from "../lib/i18n";

/**
 * Declarar el sexo del tripulante (decisión del usuario, 2026-11-14, revierte la §5.36.19).
 *
 * Por qué existe: el sexo declarado decide si se ofrece el seguimiento del ciclo menstrual
 * (`CyclePanel`) y nada más; sin un sitio donde declararlo, ese seguimiento no se podía ofrecer.
 * Lo declara el propio tripulante y queda firmado en un asiento aparte (`crew-sex`) con quién lo
 * declaró; sin declaración vigente, el backend dice «no declarado» y aquí no se supone nada.
 *
 * Lo que es del backend se pinta tal cual: la palabra de «no declarado» (con la marca gris de «no
 * disponible», tabla F.5-1) y las frases de qué se guarda, para qué y cómo se borra
 * (`personal_data` de `/api/baseline-profile`). Las dos palabras de la elección son rótulos del
 * formulario, no texto clínico. Sin color en lo declarado: no es una lectura ni un aviso.
 *
 * En Tierra (`readOnly`) solo se lee, con el corte del retardo (`until`): no se declara desde allí.
 */
export const CREW_SEX_WORDS: Readonly<Record<CrewSexValue, string>> = {
  female: tr("femenino", "female"),
  male: tr("masculino", "male"),
};

export function SexForm({
  subject,
  refreshKey,
  until,
  readOnly = false,
  onDeclared,
}: {
  subject: string;
  /** Cambia cuando cambian los datos del estado: entonces se vuelve a leer. */
  refreshKey: string;
  /** El corte de reloj de Tierra; sin él, lo vigente. */
  until?: Date | undefined;
  /** Tierra: se lee y no se declara. */
  readOnly?: boolean;
  /** Tras firmar una declaración: para que el panel del ciclo vuelva a leer. */
  onDeclared?: (() => void) | undefined;
}) {
  const [sex, setSex] = useState<CrewSex | null>(null);
  const [personal, setPersonal] = useState<BaselinePersonalData | null>(null);
  const [unavailable, setUnavailable] = useState<RequestOutcome | null>(null);
  const [reads, setReads] = useState(0);
  const cut = until?.toISOString();

  // Otro tripulante: lo pintado era del anterior.
  useEffect(() => {
    setSex(null);
    setPersonal(null);
    setUnavailable(null);
  }, [subject]);

  useEffect(() => {
    let alive = true;
    const at = cut === undefined ? undefined : new Date(cut);
    getCrewSex(at, subject)
      .then((declared) => {
        if (!alive) return;
        setSex(declared);
        setUnavailable(null);
      })
      .catch((reason: unknown) => {
        if (alive) setUnavailable(requestOutcome(reason));
      });
    // Las frases de qué se guarda van aparte: si el perfil falla, declarar sigue siendo posible y
    // el plegable, simplemente, no sale.
    baselineApi
      .profile(subject, at)
      .then((profile) => {
        if (alive) setPersonal(profile.personal_data);
      })
      .catch(() => {
        // sin perfil no hay frases que enseñar; lo declarado no depende de ellas
      });
    return () => {
      alive = false;
    };
  }, [subject, refreshKey, cut, reads]);

  const declared = () => {
    setReads((count) => count + 1);
    onDeclared?.();
  };

  return (
    <SexFormView
      subject={subject}
      sex={sex}
      personal={personal}
      unavailable={unavailable}
      readOnly={readOnly}
      onDeclared={declared}
    />
  );
}

/** Solo pinta (y firma). Separado de la carga para poder probar lo que se lee en pantalla. */
export function SexFormView({
  subject,
  sex,
  personal,
  unavailable,
  readOnly,
  onDeclared,
}: {
  subject: string;
  sex: CrewSex | null;
  personal: BaselinePersonalData | null;
  unavailable: RequestOutcome | null;
  readOnly: boolean;
  onDeclared?: () => void;
}) {
  if (sex === null) {
    return (
      <section data-ui="crew-sex" className="panel" aria-label={tr("Sexo declarado", "Declared sex")}>
        <PanelTitle concept="identity">{tr("Sexo declarado", "Declared sex")}</PanelTitle>
        {unavailable !== null ? <Unavailable outcome={unavailable} /> : <Loading />}
      </section>
    );
  }
  // Si la última lectura falló, lo pintado es lo de antes: en cursiva, con el motivo.
  const stale = unavailable !== null;
  return (
    <section data-ui="crew-sex" className="panel cycle-sex" aria-label={tr("Sexo declarado", "Declared sex")} data-crew-sex>
      <PanelTitle concept="identity">{tr("Sexo declarado", "Declared sex")}</PanelTitle>
      <CurrentSex sex={sex} stale={stale} />
      {unavailable !== null && <Unavailable outcome={unavailable} />}
      {!readOnly && <DeclareForm subject={subject} sex={sex} onDeclared={onDeclared} />}
      {personal !== null && (
        <Fold data-ui="crew-sex-privacy" concept="about" label={tr("Qué se guarda y cómo se borra", "What is stored and how it is erased")}>
          <p>{personal.statement}</p>
          <p>{personal.cycle}</p>
          <p className="secondary">{personal.privacy}</p>
        </Fold>
      )}
    </section>
  );
}

/** Lo declarado vigente, con quién y cuándo; sin declaración, la palabra del backend en gris. */
function CurrentSex({ sex, stale }: { sex: CrewSex; stale: boolean }) {
  if (!sex.declared) {
    return (
      <p data-crew-sex-state="undeclared">
        <MarkOf mark={UNAVAILABLE_MARK} stale={stale}>
          {sex.status}
        </MarkOf>
      </p>
    );
  }
  return (
    <dl className={stale ? "cycle-facts stale" : "cycle-facts"} data-crew-sex-state={sex.sex}>
      <div>
        <FieldLabel as="dt" concept="identity">
          {tr("Sexo", "Sex")}
        </FieldLabel>
        <dd>{CREW_SEX_WORDS[sex.sex]}</dd>
      </div>
      <div>
        <FieldLabel as="dt" concept="person">
          {tr("Declarado por", "Declared by")}
        </FieldLabel>
        <dd>{sex.declared_by}</dd>
      </div>
      <div>
        <FieldLabel as="dt" concept="time">
          {tr("Firmado", "Signed")}
        </FieldLabel>
        <dd>
          {Number.isNaN(new Date(sex.recorded).getTime()) ? (
            <MarkOf mark={UNAVAILABLE_MARK}>{tr("no disponible", "not available")}</MarkOf>
          ) : (
            <span className="num">{formatUtc(new Date(sex.recorded))}</span>
          )}
        </dd>
      </div>
      <div>
        <FieldLabel as="dt" concept="signedLedger">
          {tr("Asiento", "Entry")}
        </FieldLabel>
        <dd>
          <span className="num">{formatNumber(sex.ledger_index)}</span>
        </dd>
      </div>
    </dl>
  );
}

/** Elegir y firmar. La elección empieza vacía: un clic no puede firmar algo que nadie eligió. */
function DeclareForm({
  subject,
  sex,
  onDeclared,
}: {
  subject: string;
  sex: CrewSex;
  onDeclared?: (() => void) | undefined;
}) {
  const id = useId();
  const [operator, setOperator] = useOperator();
  const [choice, setChoice] = useState<CrewSexValue | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);
  // Mientras va una firma no se pide otra: un doble clic cruzaba dos peticiones.
  const [sending, setSending] = useState(false);
  const current = sex.declared ? sex.sex : null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (choice === null) return;
    setError(null);
    setSending(true);
    try {
      await declareCrewSex({ subject, sex: choice, declared_by: operator.trim() });
      setChoice(null);
      onDeclared?.();
    } catch (failure) {
      setError(requestOutcome(failure));
    } finally {
      setSending(false);
    }
  };

  const ready = choice !== null && choice !== current && operator.trim() !== "" && !sending;
  return (
    <form className="cycle-sex-form" onSubmit={(event) => void submit(event)} aria-label={tr("Declarar el sexo", "Declare sex")}>
      <fieldset>
        <FieldLabel as="legend" concept="declare">
          {current === null ? tr("Declarar", "Declare") : tr("Cambiar lo declarado", "Change the declaration")}
        </FieldLabel>
        {CREW_SEX_VALUES.map((value) => (
          <label key={value} className="cycle-choice">
            <input
              type="radio"
              name={`${id}-sex`}
              value={value}
              checked={choice === value}
              onChange={() => setChoice(value)}
            />
            {CREW_SEX_WORDS[value]}
          </label>
        ))}
      </fieldset>
      <div className="cycle-sex-sign">
        <FieldLabel htmlFor={`${id}-by`} concept="person">
          {tr("Quién declara", "Who declares")}
        </FieldLabel>
        <input
          id={`${id}-by`}
          value={operator}
          maxLength={64}
          onChange={(event) => setOperator(event.target.value)}
          placeholder={tr("nombre o indicativo", "name or call sign")}
        />
        <Command concept="declare" type="submit" disabled={!ready}>
          {tr("Firmar", "Sign")}
        </Command>
      </div>
      {error !== null && (
        <p role="alert">
          <MarkOf mark={error.mark}>{error.text}</MarkOf>
        </p>
      )}
    </form>
  );
}
