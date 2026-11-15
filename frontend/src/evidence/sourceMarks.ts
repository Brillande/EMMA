/**
 * Que dibujo y que color acompanan a lo que el backend dice de una fuente: su nivel de evidencia
 * (`grade.tier`, `app/evidence/tier.py`), su clase de documento (`evidence_type`,
 * `app/evidence/registry.py`) y sobre quien se midio (`population`).
 *
 * Por que existe: el backend da catorce niveles y trece clases, y un dibujo por valor seria una
 * coleccion que nadie distingue a 12 px. Aqui se agrupan por lo que cambia la lectura —el diseno
 * del estudio, la clase de documento, la especie— y la paridad con los enumerados del backend
 * tiene prueba (`sourceMarks.test.ts`): un valor nuevo sin dibujo la hace fallar, y mientras
 * tanto sale con el de «desconocido». Los colores son los de siempre: amarillo si la fuente no
 * mide solo en personas (la advertencia de alcance), gris si el registro no lo sabe (tabla F.5-1,
 * «no disponible»). La palabra es siempre la del backend; aqui no se redacta nada.
 */

import type { PictogramName } from "../icons/registry";
import type { EvidenceGrade } from "../lib/api";
import { type StateMark, UNAVAILABLE_MARK, UNKNOWN_MARK, UNKNOWN_PICTOGRAM, mark } from "../lib/marks";

/**
 * La advertencia de alcance (`EvidenceEntry`): lo que la fuente no respalda. Amarillo con el
 * triangulo, la precaucion de toda la interfaz; el amarillo no va solo (§5.33.5).
 */
export const SCOPE_MARK: StateMark = mark("shape-triangle", "yellow");

/** Nivel de evidencia, por el diseno del estudio. Las claves son los `tier` de `tier.py`. */
export const TIER_PICTOGRAMS: Record<string, PictogramName> = {
  guia_clinica: "layers-three",
  metaanalisis: "layers-three",
  revision_sistematica: "layers-three",
  rct: "bars-two",
  ensayo_clinico: "bars-two",
  cohorte_prospectiva: "dots-arrow",
  cohorte_retrospectiva: "dots-arrow",
  serie_casos: "dot-arrow",
  caso_clinico: "dot-arrow",
  modelo_animal: "flask",
  in_vitro: "flask",
  revision_narrativa: "sheet-dashed",
  preprint: "sheet-dashed",
  desconocido: "question",
};

/**
 * La marca del nivel: su dibujo, y amarillo si es preclinico o gris si es desconocido, como la
 * insignia de siempre. `preclinical` lo decide el backend; aqui no se deduce del nivel.
 */
export function gradeMark(grade: Pick<EvidenceGrade, "tier" | "preclinical">): StateMark {
  const pictogram = TIER_PICTOGRAMS[grade.tier] ?? UNKNOWN_PICTOGRAM;
  if (grade.preclinical) return mark(pictogram, "yellow");
  if (grade.tier === "desconocido") return mark(pictogram, "gray");
  return mark(pictogram, null);
}

/** Clase de documento. Las claves son las de `EVIDENCE_TYPES` de `registry.py`. */
export const TYPE_PICTOGRAMS: Record<string, PictogramName> = {
  dataset: "table-grid",
  evidence_report: "sheet-lines",
  hrp_risk: "list-lines",
  medical_condition_sheet: "sheet-plus",
  journal_article: "sheet-lines",
  technical_brief: "sheet-circle",
  agency_page: "window-bar",
  research_task: "magnifier",
  program_document: "sheet-lines",
  presentation: "easel",
  technical_memorandum: "sheet-lines",
  technical_standard: "sheet-circle",
  // Un manuscrito sin revisión por pares: la hoja a trazos, la misma del nivel «preprint» (sin
  // revisar); con la hoja con renglones se dibujaría como un artículo revisado.
  preprint: "sheet-dashed",
};

/**
 * Por que un campo de la ficha esta en `null` (`registry.py`, `EvidenceItem` en `lib/api.ts`):
 * nadie lo ha leido en la fuente (`unverified`), no procede para ese documento
 * (`not_applicable`), o se leyo y ningun valor del enumerado lo cubre (`outside_enum`).
 */
export type EmptyReason = "unverified" | "not_applicable" | "outside_enum";

/**
 * Tres hechos distintos, tres marcas, las tres en gris como siempre (tabla F.5-1, «no
 * disponible»: no hay valor del enumerado que ensenar). Segunda pasada (§5.33.5): antes los tres
 * llevaban la interrogacion, y lo leido que el enumerado no cubre salia a la vez con la
 * interrogacion junto a su palabra y en gris sin forma en la lista de abajo; ahora un hecho lleva
 * un solo signo, el mismo donde aparezca. Sin verificar, la interrogacion; no aplica, el guion de
 * «no aplica» (el del respaldo demo); fuera del enumerado, el circulo tachado de `lib/marks.ts`:
 * el campo si se leyo, lo que no hay es un valor del enumerado que lo diga.
 */
export const EMPTY_FIELD_MARKS: Record<EmptyReason, StateMark> = {
  unverified: mark("question", "gray"),
  not_applicable: mark("dash", "gray"),
  outside_enum: UNAVAILABLE_MARK,
};

/** Por que esta vacio un campo de la ficha: lo dicen sus listas, no se deduce del valor. */
export function emptyReason(
  source: { readonly not_applicable: readonly string[]; readonly outside_enum: readonly string[] },
  field: string,
): EmptyReason {
  if (source.outside_enum.includes(field)) return "outside_enum";
  if (source.not_applicable.includes(field)) return "not_applicable";
  return "unverified";
}

/** La clase de documento; vacia, gris con la marca de por que lo esta. */
export function typeMark(evidenceType: string | null, empty: EmptyReason = "unverified"): StateMark {
  if (evidenceType === null) return EMPTY_FIELD_MARKS[empty];
  return mark(TYPE_PICTOGRAMS[evidenceType] ?? UNKNOWN_PICTOGRAM, null);
}

/**
 * Sobre quien se midio. Amarillo cuando no son solo personas: es la advertencia de alcance
 * (especificacion §2, no mezclar humanos, animales y analogos). Gris si no esta leido.
 */
export const POPULATION_MARKS: Record<string, StateMark> = {
  human: mark("person", null),
  animal: mark("paw", "yellow"),
  human_and_animal: mark("person-paw", "yellow"),
};

export function populationMark(population: string | null, empty: EmptyReason = "unverified"): StateMark {
  if (population === null) return EMPTY_FIELD_MARKS[empty];
  return POPULATION_MARKS[population] ?? UNKNOWN_MARK;
}
