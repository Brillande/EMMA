import type { ComponentPropsWithoutRef, ReactNode } from "react";

import { Pictogram } from "../icons";
import { type Sign, signPictogram, withoutSign } from "../lib/uiMarks";

/**
 * Un mando (`<button class="command">`) con su signo delante de la palabra (§5.32 c, §5.33): el
 * dibujo de lo que hace, el mismo en toda la interfaz (`lib/uiMarks.ts`). `hazard` añade la cinta
 * de F.4.3.2 i a lo irreversible o peligroso; `className` se suma detrás.
 *
 * No fija `type`: lo decide quien lo usa (un `submit` dentro de un formulario, un `button` fuera),
 * igual que el `<button>` que sustituye. El resto de props van al botón tal cual.
 */
export type CommandProps = Sign & {
  hazard?: boolean;
  className?: string;
  children: ReactNode;
} & Omit<ComponentPropsWithoutRef<"button">, "children" | "className">;

export function Command(props: CommandProps) {
  const { hazard = false, className, children, ...button } = withoutSign(props);
  const classes = ["command", hazard ? "hazard" : undefined, className]
    .filter((item) => item !== undefined)
    .join(" ");
  return (
    <button className={classes} {...button}>
      <Pictogram name={signPictogram(props)} />
      {children}
    </button>
  );
}
