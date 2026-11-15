import { Mark, MarkOf } from "../components/Mark";
import type { EvidenceCard } from "../lib/api";
import { formatSourceDate } from "../lib/format";
import { contextLabel, contextPictogram } from "../lib/provenance";
import { EMPTY_FIELD_MARKS, emptyReason, populationMark, typeMark } from "./sourceMarks";
import { tr } from "../lib/i18n";

/**
 * Que es una fuente citada, tal como lo da el registro unico del backend
 * (`app/evidence/registry.py`): clase de documento, fecha, entorno del estudio y sobre quien se
 * midio. La interfaz no lo redacta ni lo completa.
 *
 * La especificacion del equipo (§2) pide no mezclar humanos, animales y analogos. Por eso la
 * poblacion va en amarillo cuando no son solo personas: es la advertencia de alcance, la misma
 * que el nivel preclinico de `SourceGrade`. Lo que el registro no ha verificado va en gris, que
 * en la tabla F.5-1 significa "no disponible": se dice que falta, no se calla ni se rellena. Lo
 * leido que ningun valor del enumerado cubre (un estudio que junta la ISS, el reposo en cama y
 * animales) tambien va en gris: no hay valor que mostrar, y forzar uno diria mas que la fuente.
 *
 * Cada dato lleva su dibujo junto a la palabra (`sourceMarks.ts`; el entorno, `contextPictogram`
 * de `lib/provenance.ts`): la clase de documento, el entorno con el pictograma de `provenance` y
 * la poblacion (persona, huella, o los dos).
 *
 * Segunda pasada (§5.33.5): las listas «fuera del enumerado» y «sin verificar» iban solo con su
 * palabra en gris, color sin forma. Ahora llevan su marca, y un campo vacio lleva la misma junto a
 * su palabra y en su lista (`EMPTY_FIELD_MARKS`): sin verificar, la interrogacion; no aplica, el
 * guion; fuera del enumerado, el circulo tachado. Un hecho, un signo.
 */
export function SourceFacts({ source }: { source: EvidenceCard }) {
  const type = typeMark(source.evidence_type, emptyReason(source, "evidence_type"));
  const population = populationMark(source.population, emptyReason(source, "population"));
  return (
    <p className="secondary">
      <Mark pictogram={type.pictogram} color={type.color}>
        {tr("Tipo:", "Type:")} {source.evidence_type_display}
      </Mark>
      {source.date !== null && <> · {formatSourceDate(source.date)}</>}
      {source.evidence_context !== null && (
        <>
          {tr(" · entorno: ", " · setting: ")}
          <Mark pictogram={contextPictogram(source.evidence_context)}>
            {contextLabel(source.evidence_context)}
          </Mark>
        </>
      )}
      {" · "}
      <Mark pictogram={population.pictogram} color={population.color}>
        {tr("población:", "population:")} {source.population_display}
      </Mark>
      {source.outside_enum.length > 0 && (
        <>
          {" · "}
          <MarkOf mark={EMPTY_FIELD_MARKS.outside_enum}>
            {tr("fuera del enumerado:", "outside the enumeration:")} {source.outside_enum_display.join(", ")}
          </MarkOf>
        </>
      )}
      {source.unverified.length > 0 && (
        <>
          {" · "}
          <MarkOf mark={EMPTY_FIELD_MARKS.unverified}>
            {tr("sin verificar:", "unverified:")} {source.unverified_display.join(", ")}
          </MarkOf>
        </>
      )}
    </p>
  );
}
