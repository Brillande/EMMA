/**
 * El idioma de la interfaz: castellano o inglés, elegido en «Pantalla».
 *
 * EMMA se escribió en castellano de punta a punta y hacía falta enseñarla en inglés sin perder el
 * castellano (decisión del usuario, 2026-11-15: dos idiomas con selector, inglés por defecto).
 * Unas ciento veinte pruebas fijan el texto castellano y varias guardas leen las fuentes buscando
 * fragmentos exactos, así que **el literal castellano no se mueve**: el inglés se pone al lado,
 * `tr("Alertas activas", "Active alerts")`.
 *
 * El idioma es fijo durante toda la carga de la página. Hay tablas a nivel de módulo que se
 * evalúan una sola vez (escenarios, consolas, marcas), y casi todo el texto lo redacta el backend
 * y habría que volver a pedirlo: elegir otro idioma guarda la elección y recarga. Por eso `tr`
 * vale en cualquier sitio, también a nivel de módulo.
 *
 * El backend se entera por una cookie del mismo origen (`emma_lang`), no por una cabecera: así no
 * hay que tocar ninguno de los `fetch` de la consola, y también la llevan las imágenes y las
 * descargas. `backend/app/core/i18n.py` es la otra mitad.
 *
 * Lo que se firma no se traduce: nunca va un `tr()` en el cuerpo de un POST
 * (`compliance/record-integrity.md`, «Idioma del registro»).
 */

export type Language = "es" | "en";

export const LANGUAGES: readonly Language[] = ["es", "en"];
export const DEFAULT_LANGUAGE: Language = "en";
/** Clave de `localStorage` y nombre de la cookie que lee el backend. */
export const LANGUAGE_KEY = "emma.lang";
export const LANGUAGE_COOKIE = "emma_lang";

/** `es` o `en` de lo guardado; otra cosa (o nada) es el idioma por defecto. */
export function parseLanguage(raw: string | null | undefined): Language {
  return raw === "es" || raw === "en" ? raw : DEFAULT_LANGUAGE;
}

function stored(): Language {
  try {
    // Sin navegador (pruebas) o con el almacenamiento bloqueado, el idioma por defecto.
    return parseLanguage(globalThis.localStorage?.getItem(LANGUAGE_KEY));
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

let current: Language = stored();

/** El idioma de esta carga de la página. */
export function language(): Language {
  return current;
}

/** El texto en el idioma de la interfaz. El castellano va primero y no se toca. */
export function tr(es: string, en: string): string {
  return current === "en" ? en : es;
}

/** La cookie con que cada petición dice su idioma al backend. */
export function languageCookie(lang: Language): string {
  return `${LANGUAGE_COOKIE}=${lang}; path=/; max-age=31536000; SameSite=Strict`;
}

/** Al arrancar: el idioma en `<html lang>` (lector de pantalla, voz) y en la cookie. */
export function applyLanguage(doc: Document): void {
  doc.documentElement.lang = current;
  doc.cookie = languageCookie(current);
}

/** Elegir otro idioma: se guarda y la página se recarga con él. El mismo, nada. */
export function chooseLanguage(next: Language): void {
  if (next === current) return;
  try {
    globalThis.localStorage?.setItem(LANGUAGE_KEY, next);
  } catch {
    // Sin almacenamiento, la cookie basta para esta sesión del navegador.
  }
  document.cookie = languageCookie(next);
  window.location.reload();
}

/**
 * Solo para las pruebas: fija el idioma antes de que se importe nada más
 * (`src/test/spanish.ts`, `src/test/english.ts`).
 */
export function setLanguageForTests(lang: Language): void {
  current = lang;
}
