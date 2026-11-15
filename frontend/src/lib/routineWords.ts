/**
 * La palabra de cada estado de una medida periódica que se debe, de una sola fuente.
 *
 * Por qué existe: la fila del panel de medidas (`RoutineList`) y la iniciativa propia
 * (`assistant/proactive.ts`) dicen lo mismo, una a la vista y otra en voz alta; si cada una tuviera
 * su copia, un cambio de palabra en la fila dejaría a la voz diciendo otra cosa que la pantalla.
 * Son palabras de estado de la interfaz, no texto clínico: el nombre de la medida es del backend.
 */
import { tr } from "./i18n";

/** Las claves son los estados de la API (`/api/timeline/routines`) y no se traducen; las palabras, sí. */
export const ROUTINE_WORDS: Readonly<Record<"atrasada" | "rota", string>> = {
  atrasada: tr("atrasada", "overdue"),
  rota: tr("sin lectura buena", "no good reading"),
};
