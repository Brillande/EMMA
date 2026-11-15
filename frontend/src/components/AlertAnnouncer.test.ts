import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AlertAnnouncer, LiveRegions } from "./AlertAnnouncer";
import { OperatorInput } from "./OperatorInput";

/**
 * El lector de pantalla del sistema (§5.41), en lo que se puede mirar sin navegador ni lector:
 * las regiones vivas existen desde el primer render y vacías, con su rol y sin releer lo guardado;
 * y lo que la privacidad tapa en pantalla tampoco se lee (el campo de quien firma y el selector
 * de tripulante, en `App.tsx`). La decisión de qué se anuncia está en `lib/announce.test.ts`.
 */

describe("regiones vivas", () => {
  it("dos, asertiva y cortés, sin `aria-atomic` implícito: el lector solo dice lo añadido", () => {
    const html = renderToStaticMarkup(
      createElement(LiveRegions, {
        assertive: [{ id: 1, text: "Crítico: Radiación. Dosis alta" }],
        polite: [{ id: 2, text: "watch: Óseo" }],
      }),
    );
    expect(html).toBe(
      '<div class="sr-only">' +
        '<div role="alert" aria-atomic="false"><p>Crítico: Radiación. Dosis alta</p></div>' +
        '<div role="status" aria-atomic="false"><p>watch: Óseo</p></div>' +
        "</div>",
    );
  });

  it("montadas y vacías desde el primer render: una región que nace con texto no se anuncia", () => {
    const html = renderToStaticMarkup(
      createElement(AlertAnnouncer, {
        ready: true,
        scope: "crew|crew-01",
        alerts: [{ id: "bone:critical", domain: "bone", level: "critical", drivers: [] }],
        annunciation: new Map<string, string>(),
        acknowledged: new Set<string>(),
        privacy: false,
      }),
    );
    // Sin efectos (render en servidor): las regiones están, sin mensajes todavía.
    expect(html).toBe(
      '<div class="sr-only"><div role="alert" aria-atomic="false"></div><div role="status" aria-atomic="false"></div></div>',
    );
  });
});

describe("privacidad: lo tapado en pantalla, tampoco en el lector", () => {
  const input = (privacy: boolean) =>
    renderToStaticMarkup(createElement(OperatorInput, { value: "CDR Vega", onChange: () => undefined, privacy }));

  it("quien firma: con la privacidad, `inert` (fuera del foco y del lector); sin ella, normal", () => {
    expect(input(true)).toMatch(/^<input [^>]*inert=""/);
    expect(input(false)).not.toContain("inert");
    // No es un campo de contraseña: el navegador no ofrece guardar el nombre como contraseña.
    expect(input(true)).not.toContain("password");
    // El nombre se conserva: lo ya escrito sigue firmando con la privacidad puesta.
    expect(input(true)).toContain('value="CDR Vega"');
  });
});
