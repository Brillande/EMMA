import { lazy } from "react";

import { AvatarSwitch } from "../components/AvatarSwitch";
import { useAvatar } from "../lib/avatar";
import type { BodyLook } from "./BodyArt";

/**
 * El cuerpo de la maqueta según el avatar elegido (`lib/avatar.ts`): el varón de partida o su variante
 * femenina. Cada uno es su propio trozo perezoso, así que solo se descarga el que se ve. Quien lo monta
 * pone el `Suspense`. Los que ya montaban `ReferenceBody` (Inicio, Cuerpo, Radiación) siguen igual.
 */
const BODIES = {
  male: lazy(() => import("./ReferenceBodyMale")),
  female: lazy(() => import("./ReferenceBodyFemale")),
} as const;

export default function ReferenceBody({ look = "thermal", switcher = true }: { look?: BodyLook; switcher?: boolean }) {
  const Body = BODIES[useAvatar()];
  // El selector va con el cuerpo 2D (petición del usuario, 2026-11-14: «en 2D no me deja cambiar de
  // avatar»): así sale en cada sitio que lo monta (Inicio, Cuerpo, Radiación) sin tocar sus tableros.
  return (
    <>
      <Body look={look} />
      {/* «Gravedad» pinta varios cuerpos y pone un solo selector para todos (2026-11-15). */}
      {switcher && <AvatarSwitch className="avatar-switch-overlay" />}
    </>
  );
}
