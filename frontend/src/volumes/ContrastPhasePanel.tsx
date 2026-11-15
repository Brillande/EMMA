import { useEffect, useState } from "react";

import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { type ContrastPhaseVocabulary, type VolumeStudy, api } from "../lib/api";
import { MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { canDeclare, declaredBy, phaseShown } from "./contrastPhase";
import { UNAVAILABLE_MARK, phaseMark } from "./marks";

/**
 * La fase de contraste de un TAC: lo que consta y el formulario para declararla.
 *
 * Por que existe: la densidad (HU) de una lesion candidata cambia con la fase de contraste, y un
 * NIfTI no la lleva. Antes solo se podia leer el aviso de que el estudio no la declaraba; ahora
 * una persona puede declararla, firmada en el registro, y se ve junto a la densidad.
 *
 * Lo que este componente NO hace: redactar ni proponer. El nombre de cada fase, el de "sin
 * declarar", el rotulo, el motivo de que no aplique y lo que dicen la regla y el alcance son del
 * backend y se muestran tal cual. El selector empieza vacio: la interfaz no sugiere ninguna fase,
 * y nada aqui mira la imagen. Colores con su significado de F.5-1, nunca solos (pictograma y
 * palabra, `marks.ts`): cian para "sin declarar" (dato ausente), gris para un estudio en el que
 * la fase no aplica (no disponible). La fase declarada va sin color, con el dibujo de esa fase
 * junto a su nombre: no es un estado ni una alerta, es procedencia.
 *
 * Quien declara es el operador de la consola, el mismo campo que firma la subida del volumen.
 * Rotulos y mando con el signo de su concepto (§5.33.9): declarar y la nota, la pluma; quien
 * declara, la persona.
 */
export function ContrastPhasePanel({
  study,
  operator,
  onOperator,
  onDeclared,
}: {
  study: VolumeStudy;
  operator: string;
  onOperator: (value: string) => void;
  onDeclared: () => void;
}) {
  const [vocabulary, setVocabulary] = useState<ContrastPhaseVocabulary | null>(null);
  const [code, setCode] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    api.volumes
      .contrastPhases()
      .then(setVocabulary)
      .catch((reason: unknown) => setError(requestOutcome(reason)));
  }, []);

  const shown = phaseShown(study);
  if (shown === null) return null;
  if (shown.kind === "no-aplica") {
    return shown.reason === null ? null : (
      <div role="note" aria-label="Fase de contraste">
        <p>
          <MarkOf mark={UNAVAILABLE_MARK}>{shown.reason}</MarkOf>
        </p>
      </div>
    );
  }

  const declare = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.volumes.declareContrastPhase(study.ledger_index, {
        phase: code,
        declared_by: operator.trim(),
        note: note.trim(),
      });
      setCode("");
      setNote("");
      onDeclared();
    } catch (reason) {
      setError(requestOutcome(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div role="group" aria-label="Fase de contraste">
      {shown.kind === "sin-declarar" ? (
        <p>
          Fase de contraste: <MarkOf mark={MISSING_MARK}>{shown.display}</MarkOf>
        </p>
      ) : (
        <>
          <p>
            Fase de contraste:{" "}
            <Mark pictogram={phaseMark(shown.declaration.code).pictogram}>{shown.declaration.display}</Mark>{" "}
            <span className="secondary">({shown.label})</span>
          </p>
          <p className="secondary">Declarada por {declaredBy(shown.declaration)}</p>
          {shown.declaration.note !== null && <p className="secondary">Nota: {shown.declaration.note}</p>}
          {shown.earlier.length > 0 && (
            <ul className="secondary" aria-label="Declaraciones anteriores de la fase de contraste">
              {shown.earlier.map((item) => (
                <li key={item.ledger_index}>
                  Antes: <Mark pictogram={phaseMark(item.code).pictogram}>{item.display}</Mark> ·{" "}
                  {declaredBy(item)}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {vocabulary !== null && (
        <>
          <div className="silence-form">
            <FieldLabel concept="declare">
              Declarar la fase de contraste{" "}
              <select value={code} onChange={(event) => setCode(event.target.value)}>
                <option value="">—</option>
                {vocabulary.phases.map((phase) => (
                  <option key={phase.code} value={phase.code}>
                    {phase.display}
                  </option>
                ))}
              </select>
            </FieldLabel>
            <FieldLabel concept="note">
              Nota (opcional){" "}
              <input value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} />
            </FieldLabel>
            <FieldLabel concept="person" className="operator">
              Declarada por{" "}
              <input value={operator} maxLength={64} onChange={(event) => onOperator(event.target.value)} />
            </FieldLabel>
            <Command
              concept="declare"
              disabled={busy || !canDeclare(shown, vocabulary, code, operator)}
              onClick={() => void declare()}
            >
              {busy ? "Firmando…" : "Declarar fase"}
            </Command>
          </div>
          <p className="secondary">{vocabulary.rule}</p>
          <p className="secondary">{vocabulary.scope}</p>
        </>
      )}
      {error !== null && (
        <p>
          <MarkOf mark={error.mark}>{error.text}</MarkOf>
        </p>
      )}
    </div>
  );
}
