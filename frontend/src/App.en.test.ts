/**
 * La carcasa en inglés (`lib/i18n.ts`): pestañas de consola, salto al contenido, carga, escenarios,
 * almacén vacío y «acerca de». Lo que se mira es que el rótulo sale en inglés y el castellano no;
 * las reglas de forma (dibujos, regiones vivas) son las de `App.test.ts` y no cambian con el idioma.
 */
import "./test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { About } from "./About";
import { App, EmptyStore, SCENARIO_LABELS, SCENARIO_PICTOGRAMS, ScenarioSwitcher } from "./App";
import { language } from "./lib/i18n";

describe("la carcasa en inglés", () => {
  const html = renderToStaticMarkup(createElement(App));

  it("este fichero corre en inglés", () => {
    expect(language()).toBe("en");
  });

  it("las dos consolas y su grupo se nombran en inglés", () => {
    expect(html).toMatch(/data-console="crew">.*?<\/svg>Crew console<\/span>/);
    expect(html).toMatch(/data-console="ground">.*?<\/svg>Earth console<\/span>/);
    expect(html).toContain('role="tablist" aria-label="Consoles"');
    expect(html).not.toContain("Consola de tripulación");
    expect(html).not.toContain("Consola de Tierra");
  });

  it("el salto al contenido conserva su destino y cambia de palabra", () => {
    expect(html).toContain('<a class="skip-link" href="#contenido">Skip to content</a>');
    expect(html).not.toContain("Saltar al contenido");
  });

  it("mientras carga lo dice en inglés, en la página y en la franja", () => {
    expect(html).toContain("Loading status…");
    expect(html).not.toContain("Cargando");
  });

  it("el título de la franja lleva la consola en inglés", () => {
    expect(html).toMatch(/<h1 class="title">EMMA · .*?Crew console · crew-01<\/span><\/h1>/);
  });
});

describe("los escenarios en inglés", () => {
  it("cada escenario tiene nombre inglés, con las mismas claves que sus dibujos", () => {
    expect(Object.keys(SCENARIO_LABELS).sort()).toEqual(Object.keys(SCENARIO_PICTOGRAMS).sort());
    expect(SCENARIO_LABELS["co2-fatigue"]).toBe("Cabin CO2 (whole crew)");
    expect(SCENARIO_LABELS.dehydration).toBe("Dehydration");
    expect(SCENARIO_LABELS["spe-event-recovery"]).toBe("Solar particle event and return to normal (whole crew)");
    for (const label of Object.values(SCENARIO_LABELS)) expect(label).not.toMatch(/[áéíóúñ¿¡]/);
  });

  it("el cambio de escenario: rótulo, selector y mando", () => {
    const html = renderToStaticMarkup(createElement(ScenarioSwitcher, { current: "co2-fatigue", onSwitched: () => undefined }));
    expect(html).toContain("Scenario:");
    expect(html).toContain("Cabin CO2 (whole crew)");
    expect(html).toContain('aria-label="Scenario to change to"');
    expect(html).toContain('<option value="" selected="">Change to…</option>');
    expect(html).toMatch(/<\/svg>Change…<\/button>/);
    expect(html).not.toMatch(/Escenario|Cambiar/);
  });

  it("el almacén vacío dice en inglés que no hay lecturas y qué se puede hacer", () => {
    const html = renderToStaticMarkup(createElement(EmptyStore, { subject: "crew-01", onLoaded: () => undefined }));
    expect(html).toContain("No readings for this crew member");
    expect(html).toContain("EMMA does not show figures without a source.");
    expect(html).toContain("signed as simulated");
    expect(html).toContain("Real Inspiration4 lab results (NASA OSDR)");
    expect(html).not.toMatch(/No hay lecturas|Analíticas reales/);
  });
});

describe("«acerca de» en inglés", () => {
  const html = renderToStaticMarkup(createElement(About));

  it("licencia, origen del código y alcance, sin reclamar más que el castellano", () => {
    expect(html).toContain("About EMMA");
    expect(html).toContain("GNU Affero General Public License v3.0 or later, with no warranty");
    expect(html).toContain("AGPL-3.0-or-later");
    expect(html).toContain("Decision support: it does not diagnose, does not prescribe and does not replace clinical judgment.");
    expect(html).not.toMatch(/certified|validated/i);
    expect(html).not.toMatch(/Acerca de|Software libre|Código fuente/);
  });
});
