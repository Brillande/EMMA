import { BodyArt, type BodyLook } from "./BodyArt";
import * as female from "./referenceBodyFemale.generated";

/**
 * La variante femenina del cuerpo de la maqueta (petición del usuario, 2026-11-14): el mismo render
 * deformado por `referenceBodyFemale.py` y generado por `referenceBodyMosaic.py`, con sus mismos colores
 * y su mismo trazado. Trozo aparte: solo se descarga si se elige.
 */
export default function ReferenceBodyFemale({ look = "thermal" }: { look?: BodyLook }) {
  return <BodyArt data={female} look={look} />;
}
