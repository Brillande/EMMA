import { type ReactNode, useEffect, useId, useRef, useState } from "react";

import { useLook } from "./BoardOnly";
import { tr } from "../lib/i18n";
import { Command } from "./Command";

/**
 * «Ver detalle» del tablero (decisión del usuario, 2026-11-08: «está muy lejos todavía de la muestra»,
 * y eligió una pantalla por sección): en la concha de la maqueta, el texto largo de un panel —cómo se
 * lee, reglas, fuentes, notas de diseño, tablas cuya cifra principal ya va en una pieza— queda detrás
 * de un mando, y arriba solo las piezas. Nada se quita: abierto, el texto es el mismo y está en el
 * mismo sitio.
 *
 * No es un `<details>` ni un `Fold` a propósito: esos cuentan como pliegues en el inventario del
 * asistente (`assistant/uiScan.ts`) y uno nuevo pediría su entrada en `assistant_ui.json`. Esto es
 * presentación de un panel que ya existe, no un apartado nuevo. Por eso tampoco lleva `data-ui`.
 *
 * Lo que nunca va aquí (regla del lote): niveles, alertas y sus motivos, marcas de dato ausente,
 * caducado o no disponible, mandos de acción, la cifra principal del panel y el aviso de retardo.
 *
 * En la concha clásica (`#clasica`) pinta los hijos tal cual, sin mando: aquella consola no cambia.
 * Botón con `aria-expanded` y `aria-controls`; la región cerrada lleva `hidden` (fuera del lector de
 * pantalla y del foco, como un pliegue cerrado).
 *
 * Se ve como un enlace fino con chevrón (cuarta ronda del lote, 2026-11-08: la maqueta solo tiene
 * «Ver variables detalladas ›»), no como un mando con filete; y varios cerrados seguidos van en una
 * fila. Es solo hoja de estilo (`shell/board.css`): sigue siendo un `<button>` con su alto táctil, y
 * el marcado no cambia (lo leen las pruebas de cada panel).
 *
 * El asistente lo abre como abre un `<details>`: sin pulsar nada, quitando el `hidden` del cuerpo
 * (`assistant/uiTargets.ts`, `reveal`); aquí se observa ese atributo y el estado pasa a abierto, así
 * el mando dice «Ocultar detalle» y el siguiente render no lo vuelve a cerrar.
 */
export function BoardDetail({
  label,
  children,
  className,
}: {
  /** Qué hay dentro, para el rótulo del mando: «Ver detalle: <label>». Sin él, «Ver detalle». */
  label?: string;
  children: ReactNode;
  className?: string;
}) {
  const look = useLook();
  const [open, setOpen] = useState(false);
  const id = useId();
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = body.current;
    if (element === null || typeof MutationObserver === "undefined") return undefined;
    const observer = new MutationObserver(() => {
      if (!element.hidden) setOpen(true);
    });
    observer.observe(element, { attributes: true, attributeFilter: ["hidden"] });
    return () => observer.disconnect();
  }, [look]);
  if (look !== "reference") return <>{children}</>;
  const show = label === undefined ? tr("Ver detalle", "Show detail") : tr(`Ver detalle: ${label}`, `Show detail: ${label}`);
  const hide = label === undefined ? tr("Ocultar detalle", "Hide detail") : tr(`Ocultar detalle: ${label}`, `Hide detail: ${label}`);
  return (
    <div className={className === undefined ? "board-detail" : `board-detail ${className}`}>
      <Command
        type="button"
        concept="detail"
        className="board-detail-toggle"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? hide : show}
      </Command>
      <div ref={body} id={id} className="board-detail-body" hidden={!open}>
        {children}
      </div>
    </div>
  );
}
