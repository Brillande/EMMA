/**
 * Barril de los pictogramas: lo que importa un componente.
 *
 * Separado de `registry.ts` a propósito: las tablas de `lib/` importan el registro (sin React)
 * y los componentes importan este barril; si fueran el mismo módulo, `Pictogram.tsx` y `lib/`
 * se importarían en círculo.
 */

export { Pictogram } from "./Pictogram";
export {
  PICTOGRAMS,
  type PictogramName,
  SETS,
  isPictogramName,
  pictogram,
  pictogramNames,
} from "./registry";
export type { PictogramDef, PictogramElement, PictogramSet } from "./types";
