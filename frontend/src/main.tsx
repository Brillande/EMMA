// Fuentes empaquetadas con la aplicacion: en vuelo no hay servidor de fuentes.
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/600.css";
// La cursiva es la tercera senal de dato caducado (`.stale`): sin ella el navegador la inventa.
import "@fontsource/ibm-plex-sans/400-italic.css";
import "@fontsource/ibm-plex-mono/400-italic.css";
import "uplot/dist/uPlot.min.css";
import "./styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App, type ConsoleLook } from "./App";
import { applyLanguage } from "./lib/i18n";
import { applyPalette } from "./lib/palette";

applyPalette(document.documentElement);
// El idioma de esta carga: en `<html lang>` y en la cookie que lee el backend, antes de pedir nada.
applyLanguage(document);

const root = document.getElementById("root");
if (root === null) throw new Error("falta #root en index.html");

// La concha de la consola se decide una vez, al arrancar, por el `hash` con que se abre: la de la
// maqueta es la consola (decisión del usuario, 2026-11-07); `#clasica` monta la de pestañas de siempre
// mientras la nueva termina de cubrirlo todo. No se sigue el `hash` después: «Saltar al contenido»
// escribe `#contenido` y no debe cambiar de concha.
const look: ConsoleLook = window.location.hash === "#clasica" ? "classic" : "reference";

createRoot(root).render(
  <StrictMode>
    <App look={look} />
  </StrictMode>,
);
