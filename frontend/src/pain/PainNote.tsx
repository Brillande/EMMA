import { useEffect, useState } from "react";

import { Mark, MarkOf } from "../components/Mark";
import { api } from "../lib/api";
import { UNAVAILABLE_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import type { PictogramName } from "../icons/registry";

export type NoteOrigin = "escrita" | "dictada-revisada";

/** El dibujo del origen de la nota, junto al rotulo «Nota»: pluma si se escribe, microfono si se dicto. */
export const ORIGIN_PICTOGRAM: Readonly<Record<NoteOrigin, PictogramName>> = {
  escrita: "pen",
  "dictada-revisada": "microphone",
};

/**
 * La nota del informe de dolor, escrita o dictada. Dictar pasa un audio Ogg/Opus por Whisper local
 * (Polaris `transcribe_audios.py`) y lo deja aqui como **borrador**: se lee y se corrige antes de
 * registrar, y se firma marcado como dictado. Lo que el modelo transcribe no se envia solo.
 * Sin Whisper instalado, el boton de dictar se declara no disponible en gris (F.5-1), con el
 * circulo tachado de «no disponible» junto a la frase.
 *
 * El origen que se firmara (`note_origin`) se ve en el dibujo junto al rotulo de la nota: pluma
 * mientras es escrita, microfono cuando viene de un audio; y en ese caso, ademas, el aviso en
 * amarillo con su triangulo de que es un borrador de un modelo.
 */
export function PainNote({
  note,
  origin,
  onChange,
}: {
  note: string;
  origin: NoteOrigin;
  onChange: (note: string, origin: NoteOrigin) => void;
}) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<RequestOutcome | null>(null);

  useEffect(() => {
    api.pain
      .voice()
      .then((body) => setAvailable(body.available))
      .catch(() => setAvailable(false));
  }, []);

  const dictate = (file: File) => {
    setBusy(true);
    setError(null);
    api.pain
      .transcribe(file)
      .then((body) => onChange(body.draft, "dictada-revisada"))
      .catch((reason: unknown) => setError(requestOutcome(reason)))
      .finally(() => setBusy(false));
  };

  return (
    <div className="pain-note">
      <label>
        <Mark pictogram={ORIGIN_PICTOGRAM[origin]}>Nota (opcional)</Mark>{" "}
        <textarea
          value={note}
          maxLength={1000}
          rows={3}
          cols={60}
          onChange={(event) => onChange(event.target.value, origin)}
        />
      </label>
      {available === true ? (
        <label>
          <Mark pictogram="microphone">{busy ? "Transcribiendo…" : "Dictar desde un audio (.opus, .ogg)"}</Mark>{" "}
          <input
            type="file"
            accept=".opus,.ogg,audio/ogg"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file !== undefined) dictate(file);
            }}
          />
        </label>
      ) : (
        available === false && (
          <MarkOf mark={UNAVAILABLE_MARK}>Dictado no disponible en esta máquina</MarkOf>
        )
      )}
      {origin === "dictada-revisada" && note !== "" && (
        <p>
          <Mark pictogram="shape-triangle" color="yellow">
            Borrador transcrito por un modelo: léelo y corrígelo antes de registrar.
          </Mark>
        </p>
      )}
      {error !== null && (
        <p>
          <MarkOf mark={error.mark}>{error.text}</MarkOf>
        </p>
      )}
    </div>
  );
}
