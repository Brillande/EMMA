import { BodyArt, type BodyLook } from "./BodyArt";
import * as male from "./referenceBody.generated";

/**
 * El varón de la maqueta, el cuerpo de partida (el pintor está en `BodyArt.tsx`). Módulo aparte y perezoso:
 * sus datos son ~1,5 MB que la consola no carga hasta abrir el tablero. La variante femenina va en
 * `ReferenceBodyFemale.tsx`, otro trozo, y quién elige es `ReferenceBody.tsx` (por `lib/avatar.ts`).
 */
export default function ReferenceBodyMale({ look = "thermal" }: { look?: BodyLook }) {
  return <BodyArt data={male} look={look} />;
}
