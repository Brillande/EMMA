import "./avatarSwitch.css";
import { Command } from "./Command";
import { AVATAR_LABEL, AVATARS, setAvatar, useAvatar } from "../lib/avatar";

/**
 * Los mandos del avatar: dos botones que se pulsan (`aria-pressed`). El mismo par sirve en el 2D y en el
 * 3D de Dolor, que leen el mismo almacén. Es presentación, no un dato del tripulante. Llevan el signo de
 * alternar entre dos vistas de lo mismo (`switchView`, §5.33.9), como Frente y Espalda: el cuerpo es uno.
 */
export function AvatarSwitch({ className }: { className?: string }) {
  const avatar = useAvatar();
  return (
    <div className={["avatar-switch", className].filter(Boolean).join(" ")} role="group" aria-label="Avatar">
      {AVATARS.map((option) => (
        <Command key={option} concept="switchView" type="button" aria-pressed={avatar === option} onClick={() => setAvatar(option)}>
          {AVATAR_LABEL[option]}
        </Command>
      ))}
    </div>
  );
}
