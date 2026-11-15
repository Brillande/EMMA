import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import type { EvidenceItem } from "../lib/api";
import { SourceFacts } from "./SourceFacts";
import { SourceGrade } from "./SourceGrade";
import { SCOPE_MARK } from "./sourceMarks";
import { tr } from "../lib/i18n";

/** Rotulo del plegable con la nota entera: dice que hay dentro, no lo resume. */
export const READING_NOTE_SUMMARY = tr(
  "Nota de lectura entera: qué se leyó de la fuente y cuándo",
  "Full reading note: what was read from the source and when",
);
/** El mismo rotulo cuando no hay alcance a la vista: entonces lo que dice la nota va dentro. */
export const SCOPE_AND_READING_SUMMARY = tr(
  "Alcance y nota de lectura: qué se leyó de la fuente y cuándo",
  "Scope and reading note: what was read from the source and when",
);

/**
 * Una fuente citada, igual en todas las listas de evidencia: la cita, su nivel, que es
 * (`SourceFacts`), para que se cita aqui y su salvedad de alcance. Todo el texto es del backend.
 *
 * Existe para que ninguna lista se deje la salvedad por el camino: una fuente con animales tiene
 * que decir que no mide en personas alli donde aparezca, no solo en las recomendaciones.
 *
 * La nota de una ficha junta lo que mide la fuente y la bitacora de su lectura (que se leyo,
 * cuando, la organizacion releida en PubMed). A la vista va `scope_in_view`, que corta el backend
 * (`app/evidence/registry.py`: lo que la nota dice antes de su primera lectura fechada, la nota
 * entera en una fuente con animales que empieza por la lectura); la nota entera, `scope_caveat`,
 * va plegada debajo, sin recortar. Si las dos coinciden no hay nada que plegar. La interfaz no
 * corta ni resume texto: solo elige cual de los dos del backend va detras de un clic.
 *
 * Segunda pasada (§5.33.5): el alcance es una advertencia, y el amarillo ya no va solo: lleva el
 * triangulo de precaucion delante, a la vista y dentro del plegable. El plegable lleva el libro
 * abierto de «lo leido en la fuente» (`sourceText`, `lib/uiMarks.ts`), que es lo que guarda.
 */
export function EvidenceEntry({ item }: { item: EvidenceItem }) {
  const inView = item.scope_in_view;
  const folded = item.scope_caveat !== null && item.scope_caveat !== inView;
  return (
    <>
      {item.url ? (
        <a href={item.url} target="_blank" rel="noreferrer">
          {item.title}
        </a>
      ) : (
        item.title
      )}{" "}
      <span className="secondary">— {item.source}</span>{" "}
      <SourceGrade grade={item.grade} />
      <SourceFacts source={item} />
      {item.relevance !== null && <p className="secondary">{item.relevance}</p>}
      {inView !== null && (
        <p>
          <MarkOf mark={SCOPE_MARK}>
            {tr("Alcance:", "Scope:")} {inView}
          </MarkOf>
        </p>
      )}
      {folded && (
        <Fold data-ui="evidence-entry"
          concept="sourceText"
          label={inView === null ? SCOPE_AND_READING_SUMMARY : READING_NOTE_SUMMARY}
        >
          <p>
            <MarkOf mark={SCOPE_MARK}>{item.scope_caveat}</MarkOf>
          </p>
        </Fold>
      )}
    </>
  );
}
