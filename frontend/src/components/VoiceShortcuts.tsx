import { DESKTOP_SHORTCUT_TEXT } from "../lib/emergencyVoice";
import { tr } from "../lib/i18n";
import { Fold } from "./Fold";

/**
 * «Atajos», el plegable de la franja con las teclas de la voz y el gesto de emergencia (§5.40,
 * franja compacta, 2026-11-04). Hasta entonces el mismo texto iba a la vista en una línea larga
 * que ocupaba su propio renglón de la franja fija, en todas las pantallas.
 *
 * Por qué sigue siendo fácil de encontrar: el plegable está junto a «Leer en voz alta», con ratón o
 * teclado se ve también al pasar por encima o al llegar a él con el tabulador, y en una pantalla
 * solo táctil se abre con un toque (`styles.css`). El lector de pantalla no depende de abrirlo: el
 * texto es la descripción del grupo de la voz (`aria-describedby` con este `id`, en `ReadAloud`), y
 * cerrado se oculta con `display: none`, que la descripción sí lee, y no con el ocultado propio
 * del plegable, que en Chromium la dejaba vacía.
 *
 * Va en su fichero, aparte de `ReadAloud.tsx`, porque la franja está fuera de las consolas: el
 * inventario del asistente (`backend/app/data/assistant_ui.json`, contrastado con el código por
 * `assistant/uiScan.ts`) cuenta los pliegues de las consolas siguiendo sus componentes, y este,
 * como el del modo seguro, no es de ninguna.
 */
export function VoiceShortcuts({ id }: { id: string }) {
  return (
    <Fold concept="howToRead" className="shortcuts strip-pop" label={tr("Atajos", "Shortcuts")}>
      <span className="secondary shortcut" id={id}>
        <kbd>{tr("Alt+Mayús+L", "Alt+Shift+L")}</kbd>
        {tr(" leer o parar · ", " read or stop · ")}
        <kbd>{tr("Alt+Mayús+R", "Alt+Shift+R")}</kbd>
        {tr(" repetir · ", " repeat · ")}
        <kbd>Esc</kbd>
        {tr(" parar · emergencia, sin ver: ", " stop · emergency, without seeing: ")}
        <kbd>Esc</kbd>
        {tr(
          " tres veces o tres dedos un segundo, activa la voz y lee (escritorio: ",
          " three times or three fingers for one second, turns the voice on and reads (desktop: ",
        )}
        <kbd>{DESKTOP_SHORTCUT_TEXT}</kbd>)
      </span>
    </Fold>
  );
}
