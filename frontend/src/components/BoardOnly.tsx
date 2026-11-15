import { type ReactNode, createContext, useContext } from "react";

/**
 * Qué concha está montada: la de la maqueta (`"reference"`, la consola desde el 2026-11-07) o la de
 * pestañas de siempre (`"classic"`, en `#clasica`). `App` la provee una vez; los paneles la leen
 * para montar las piezas del tablero (cifras grandes, anillos, barras, curvas) solo en la nueva: la
 * clásica debe seguir siendo la consola de antes mientras exista, y una hoja de estilos no puede
 * quitar del DOM lo que un componente añade.
 *
 * Sin proveedor (las pruebas de componente, que renderizan un panel suelto) vale `"reference"`: así
 * las pruebas ven las piezas y la clásica es la que tiene que pedirlo explícitamente.
 */
export type ConsoleLook = "classic" | "reference";

export const LookContext = createContext<ConsoleLook>("reference");

export function useLook(): ConsoleLook {
  return useContext(LookContext);
}

/** Lo que solo se monta en la concha de la maqueta. */
export function BoardOnly({ children }: { children: ReactNode }) {
  return useLook() === "reference" ? <>{children}</> : null;
}
