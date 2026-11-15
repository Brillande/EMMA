import type { ReactNode } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";

import { UI_ATTRIBUTE } from "./uiTargets";

/**
 * `renderToStaticMarkup` sin los `data-ui` del inventario del asistente (`uiTargets.ts`). Solo para
 * pruebas: el atributo no se ve, y las pruebas de marcado de cada panel miran lo que se pinta, no
 * cómo lo encuentra el asistente (eso lo prueba `uiInventory.test.ts`).
 */
export function renderToStaticMarkup(element: ReactNode): string {
  return render(element).replace(new RegExp(` ${UI_ATTRIBUTE}="[^"]*"`, "g"), "");
}
