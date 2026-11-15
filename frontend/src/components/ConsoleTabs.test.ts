import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { AlertCounts } from "../lib/alerts";
import { HIGH_CONTRAST_MIN, HIGH_CONTRAST_TEXT_MIN, MIN_CONTRAST, PALETTES, contrast } from "../lib/palette";
import { uiPictogram } from "../lib/uiMarks";
import { LookContext } from "./BoardOnly";
import {
  type ConsoleSection,
  ConsoleTabs,
  RailTopContext,
  TabAlerts,
  asideAt,
  personal,
  visibleSections,
} from "./ConsoleTabs";
import { DisplayControls, DisplayModesContext, ScreenTop, activeModes } from "./DisplayControls";
import {
  DEFAULT_MODES,
  DISPLAY_KEY,
  DISPLAY_OPEN_KEY,
  LOW_VISION_ZOOM,
  type DisplayModes,
  type PreferenceStore,
  nextTabIndex,
  parseModes,
  railPlacement,
  readDisplayOpen,
  readModes,
  readSection,
  resolveSection,
  sectionKey,
  writeDisplayOpen,
  writeModes,
  writeSection,
} from "./displayModes";

/**
 * El armazón de pestañas y los modos de pantalla (§5.40). Sin navegador: la lógica (teclas,
 * persistencia, qué sección se abre) va en funciones puras, y el marcado se mira con
 * `renderToStaticMarkup` con los modos puestos por contexto.
 */

const NONE: AlertCounts = { warning: 0, caution: 0, advisory: 0, unacknowledged: 0, suppressed: 0, inhibited: 0 };

class MemoryStore implements PreferenceStore {
  readonly items = new Map<string, string>();
  getItem(key: string): string | null {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.items.set(key, value);
  }
}

class BrokenStore implements PreferenceStore {
  getItem(): string | null {
    throw new Error("sin almacén");
  }
  setItem(): void {
    throw new Error("sin almacén");
  }
}

const SECTIONS: ConsoleSection[] = [
  {
    key: "hazards",
    label: "Peligros y alertas",
    pictogram: uiPictogram("hazards"),
    essential: true,
    alerts: true,
    shared: true,
    panels: ["PANEL-ALERTAS", personal("PANEL-PERSONAL")],
  },
  { key: "body", label: "Cuerpo", pictogram: uiPictogram("body"), panels: ["PANEL-CUERPO"] },
  {
    key: "env-leo",
    label: "Órbita baja",
    pictogram: uiPictogram("compare"),
    group: "Entornos",
    shared: true,
    panels: ["PANEL-LEO"],
  },
];

const render = (
  modes: Partial<DisplayModes> = {},
  stored: string | null = null,
  counts: AlertCounts = NONE,
  sections: ConsoleSection[] = SECTIONS,
) =>
  renderToStaticMarkup(
    createElement(
      DisplayModesContext.Provider,
      { value: { modes: { ...DEFAULT_MODES, ...modes }, update: () => undefined } },
      createElement(ConsoleTabs, {
        id: "crew",
        label: "Secciones",
        sections,
        counts,
        stored,
        onChoose: () => undefined,
      }),
    ),
  );

describe("teclado del carril vertical", () => {
  it("abajo y derecha, la siguiente; arriba e izquierda, la anterior; dando la vuelta", () => {
    expect(nextTabIndex(3, 0, "ArrowDown")).toBe(1);
    expect(nextTabIndex(3, 2, "ArrowDown")).toBe(0);
    expect(nextTabIndex(3, 0, "ArrowUp")).toBe(2);
    expect(nextTabIndex(3, 1, "ArrowRight")).toBe(2);
    expect(nextTabIndex(3, 1, "ArrowLeft")).toBe(0);
  });

  it("Inicio y Fin; otra tecla no mueve nada; sin pestañas, nada", () => {
    expect(nextTabIndex(4, 2, "Home")).toBe(0);
    expect(nextTabIndex(4, 1, "End")).toBe(3);
    expect(nextTabIndex(4, 1, "Enter")).toBeNull();
    expect(nextTabIndex(4, 1, "a")).toBeNull();
    expect(nextTabIndex(0, 0, "ArrowDown")).toBeNull();
  });
});

describe("persistencia", () => {
  it("la sección se guarda por consola y se vuelve a leer", () => {
    const store = new MemoryStore();
    writeSection(store, "crew", "body");
    writeSection(store, "ground", "trends");
    expect(readSection(store, "crew")).toBe("body");
    expect(readSection(store, "ground")).toBe("trends");
    expect(store.items.get(sectionKey("crew"))).toBe("body");
  });

  it("los modos se guardan y se leen enteros", () => {
    const store = new MemoryStore();
    const modes: DisplayModes = { ...DEFAULT_MODES, lowVision: true, privacy: true, voice: true, rotation: 180, followSensor: true };
    writeModes(store, modes);
    expect(readModes(store)).toEqual(modes);
    expect(JSON.parse(store.items.get(DISPLAY_KEY) ?? "{}")).toEqual(modes);
  });

  it("lo que no se entiende queda con su valor de partida, campo a campo", () => {
    expect(parseModes(null)).toEqual(DEFAULT_MODES);
    expect(parseModes("no es json")).toEqual(DEFAULT_MODES);
    expect(parseModes("[1]")).toEqual(DEFAULT_MODES);
    expect(parseModes('{"privacy": true, "rotation": 45, "lowVision": "si"}')).toEqual({
      ...DEFAULT_MODES,
      privacy: true,
    });
  });

  it("sin almacén, o con uno que falla, la consola sigue con los valores de partida", () => {
    expect(readModes(null)).toEqual(DEFAULT_MODES);
    expect(readModes(new BrokenStore())).toEqual(DEFAULT_MODES);
    expect(() => writeModes(new BrokenStore(), DEFAULT_MODES)).not.toThrow();
    expect(readSection(new BrokenStore(), "crew")).toBeNull();
    expect(() => writeSection(new BrokenStore(), "crew", "body")).not.toThrow();
  });

  it("«Pantalla» abierto o cerrado va en su propia clave, cerrado de partida, sin tocar los modos", () => {
    const store = new MemoryStore();
    expect(readDisplayOpen(store)).toBe(false);
    writeModes(store, { ...DEFAULT_MODES, lowVision: true });
    writeDisplayOpen(store, true);
    expect(readDisplayOpen(store)).toBe(true);
    expect(store.items.get(DISPLAY_OPEN_KEY)).toBe("true");
    expect(DISPLAY_OPEN_KEY).not.toBe(DISPLAY_KEY);
    expect(readModes(store)).toEqual({ ...DEFAULT_MODES, lowVision: true });
    writeDisplayOpen(store, false);
    expect(readDisplayOpen(store)).toBe(false);
    store.items.set(DISPLAY_OPEN_KEY, "quizá");
    expect(readDisplayOpen(store)).toBe(false);
    expect(readDisplayOpen(null)).toBe(false);
    expect(readDisplayOpen(new BrokenStore())).toBe(false);
    expect(() => writeDisplayOpen(new BrokenStore(), true)).not.toThrow();
  });

  it("se abre la guardada si sigue a la vista; si no, la primera", () => {
    expect(resolveSection(["a", "b"], "b")).toBe("b");
    expect(resolveSection(["a", "b"], "c")).toBe("a");
    expect(resolveSection(["a", "b"], null)).toBe("a");
    expect(resolveSection([], "a")).toBeNull();
  });
});

describe("dónde va el carril", () => {
  it("al lado en una tableta apaisada y en escritorio; arriba en vertical y en pantalla estrecha", () => {
    expect(railPlacement(1024, 768, 0, false)).toBe("side");
    expect(railPlacement(1366, 1024, 0, false)).toBe("side");
    expect(railPlacement(1440, 900, 0, false)).toBe("side");
    expect(railPlacement(768, 1024, 0, false)).toBe("top");
    expect(railPlacement(1024, 1366, 0, false)).toBe("top");
    expect(railPlacement(700, 500, 0, false)).toBe("top");
    // Un escritorio más alto que ancho pero ancho de sobra sigue con el carril al lado.
    expect(railPlacement(1200, 1900, 0, false)).toBe("side");
  });

  it("cuenta la vista como la ve quien mira: girada de lado, y ampliada con baja visión", () => {
    expect(railPlacement(1024, 768, 90, false)).toBe("top");
    expect(railPlacement(1024, 768, 270, false)).toBe("top");
    expect(railPlacement(1024, 768, 180, false)).toBe("side");
    expect(railPlacement(768, 1024, 90, false)).toBe("side");
    // 900 px de ancho con la ampliación de 1,25 son 720 para la maqueta: estrecha.
    expect(railPlacement(900, 700, 0, true)).toBe("top");
    expect(railPlacement(900, 700, 0, false)).toBe("side");
  });
});

describe("<ConsoleTabs>", () => {
  it("el carril es de las pestañas: los mandos de pantalla, plegados en «Pantalla» al pie", () => {
    const html = render({});
    const rail = html.slice(html.indexOf('<nav class="rail"'), html.indexOf("</nav>"));
    const tabs = rail.lastIndexOf('role="tab"');
    const fold = rail.indexOf('<details data-ui="display-controls" class="display-controls">');
    expect(fold).toBeGreaterThan(tabs);
    expect(rail.slice(fold)).toMatch(/<summary class="display-toggle">.*Pantalla/);
    // Sin ventana (sin navegador), el carril va al lado.
    expect(html).toContain('<div class="console-layout" data-rail="side">');
  });

  it("pestañas verticales con su rol, su panel y tabulación itinerante", () => {
    const html = render({}, "body");
    expect(html.match(/role="tablist" aria-orientation="vertical"/g)).toHaveLength(2);
    expect(html).toMatch(
      /<button type="button" role="tab" id="crew-tab-body" aria-controls="crew-panel-body" aria-selected="true" tabindex="0">/,
    );
    expect(html).toMatch(/id="crew-tab-hazards" aria-controls="crew-panel-hazards" aria-selected="false" tabindex="-1"/);
    expect(html).toContain('role="tabpanel" id="crew-panel-body" aria-labelledby="crew-tab-body"');
    // El grupo de entornos, sin la abierta, conserva una pestaña en el orden del tabulador.
    expect(html).toMatch(/id="crew-tab-env-leo" aria-controls="crew-panel-env-leo" aria-selected="false" tabindex="0"/);
    expect(html).toContain("PANEL-CUERPO");
    expect(html).not.toContain("PANEL-ALERTAS");
  });

  it("cada pestaña con su dibujo junto al rótulo, y el grupo de entornos con su nombre", () => {
    const html = render();
    expect(html).toMatch(new RegExp(`data-pictogram="${uiPictogram("hazards")}"[^>]*>.*?</svg>Peligros y alertas`));
    expect(html).toContain('aria-label="Entornos"');
    expect(html).toContain("Órbita baja");
  });

  it("con `headerGroup`, las pestañas de ese grupo van en la cabecera, bajo el entorno de la misión", () => {
    const html = renderToStaticMarkup(
      createElement(
        DisplayModesContext.Provider,
        { value: { modes: DEFAULT_MODES, update: () => undefined } },
        createElement(ConsoleTabs, {
          id: "crew",
          label: "Secciones",
          sections: SECTIONS,
          counts: NONE,
          header: "CABECERA",
          headerGroup: "Entornos",
          stored: null,
          onChoose: () => undefined,
        }),
      ),
    );
    const header = html.slice(html.indexOf('class="rail-header"'), html.indexOf("crew-tab-hazards"));
    // En la cabecera: el entorno de la misión y, debajo, la pestaña de cada entorno, la misma de siempre.
    expect(header).toContain("CABECERA");
    expect(header).toMatch(/role="tablist" aria-orientation="vertical" aria-label="Entornos"/);
    expect(header).toContain('id="crew-tab-env-leo"');
    // Sin el nombre del grupo a la vista: ya lo dice la cabecera.
    expect(html).not.toContain('<p class="rail-group-name secondary">Entornos</p>');
    // Y el carril no la repite.
    expect(html.match(/id="crew-tab-env-leo"/g)).toHaveLength(1);
  });

  it("sin sección guardada abre la primera; una guardada que ya no existe, también", () => {
    expect(render()).toContain("PANEL-ALERTAS");
    expect(render({}, "desaparecida")).toContain("PANEL-ALERTAS");
  });

  it("modo esencial: solo las esenciales, y lo dice con la cuenta de las ocultas", () => {
    const html = render({ essential: true }, "body");
    expect(html).not.toContain("Cuerpo");
    expect(html).not.toContain("Órbita baja");
    expect(html).toContain("PANEL-ALERTAS");
    expect(html).toMatch(/Modo esencial: solo lo necesario para actuar\.\s*<span class="num">2<\/span> secciones ocultas\./);
    expect(html).toContain("Ver todas las secciones");
    expect(visibleSections(SECTIONS, true).map((section) => section.key)).toEqual(["hazards"]);
  });

  it("privacidad: lo compartido a la vista, lo personal y lo no compartido tapado e inerte", () => {
    const shared = render({ privacy: true });
    expect(shared).toMatch(/PANEL-ALERTAS/);
    expect(shared).toMatch(/<div class="slot-body privacy-blur" inert="" aria-hidden="true">PANEL-PERSONAL<\/div>/);
    expect(shared).toMatch(/<div class="slot-body">PANEL-ALERTAS<\/div>/);
    expect(shared).toContain("Tapado por privacidad");
    expect(shared).toContain("Quitar privacidad");
    const body = render({ privacy: true }, "body");
    expect(body).toMatch(/<div class="slot-body privacy-blur" inert="" aria-hidden="true">PANEL-CUERPO<\/div>/);
    // Sin privacidad no hay tapa, y el panel está en la misma caja: ponerla no lo desmonta.
    expect(render({}, "hazards")).not.toContain("privacy-blur");
    expect(render({}, "hazards")).toMatch(/<div class="slot"><div class="slot-body">PANEL-PERSONAL<\/div><\/div>/);
  });

  it("privacidad sin poder tapar solo los nombres de las frases: se tapa también lo compartido, y se dice", () => {
    const html = renderToStaticMarkup(
      createElement(
        DisplayModesContext.Provider,
        { value: { modes: { ...DEFAULT_MODES, privacy: true }, update: () => undefined, namesMasked: false } },
        createElement(ConsoleTabs, {
          id: "crew",
          label: "Secciones",
          sections: SECTIONS,
          counts: NONE,
          stored: null,
          onChoose: () => undefined,
        }),
      ),
    );
    expect(html).toMatch(/<div class="slot-body privacy-blur" inert="" aria-hidden="true">PANEL-ALERTAS<\/div>/);
    expect(html).toContain("todas las secciones quedan tapadas");
    // Pudiendo, el aviso dice que los nombres de las frases van tapados y lo compartido a la vista.
    const masked = render({ privacy: true });
    expect(masked).toContain("también los nombres dentro de las frases");
    expect(masked).not.toContain("todas las secciones quedan tapadas");
  });

  it("un hueco de la tabla (una condición que no se cumple) no deja una tapa vacía", () => {
    const sections: ConsoleSection[] = [
      { key: "x", label: "X", pictogram: uiPictogram("body"), panels: [false, null, "PANEL-X"] },
    ];
    const html = render({ privacy: true }, null, NONE, sections);
    expect(html.match(/Tapado por privacidad/g)).toHaveLength(1);
  });

  it("la pestaña de las alertas lleva su recuento; las demás, no", () => {
    const counts = { ...NONE, caution: 2, advisory: 1, unacknowledged: 1 };
    const html = render({}, null, counts);
    expect(html.match(/class="tab-alerts"/g)).toHaveLength(1);
    expect(html).toMatch(/id="crew-tab-hazards"[\s\S]*?class="tab-alerts"[\s\S]*?<\/button>/);
  });
});

describe("<TabAlerts>", () => {
  const html = (counts: AlertCounts) => renderToStaticMarkup(createElement(TabAlerts, { counts }));

  it("sin alertas, nada", () => {
    expect(html(NONE)).toBe("");
  });

  it("con la forma y el color del nivel más alto, la palabra, y las que nadie ha reconocido", () => {
    const caution = html({ ...NONE, caution: 2, advisory: 1, unacknowledged: 1 });
    expect(caution).toMatch(/class="mark c-yellow"><svg[^>]*data-pictogram="shape-triangle"/);
    expect(caution).toContain('<span class="num">3</span> activas');
    expect(caution).toMatch(/data-pictogram="box-empty"[\s\S]*sin reconocer <span class="num">1<\/span>/);
    expect(html({ ...NONE, warning: 1 })).toMatch(/c-red"><svg[^>]*data-pictogram="shape-square"/);
    expect(html({ ...NONE, advisory: 1 })).toMatch(/c-blue"><svg[^>]*data-pictogram="shape-diamond"/);
  });

  it("no parpadea: el parpadeo es de la fila de la alerta crítica", () => {
    expect(html({ ...NONE, warning: 3, unacknowledged: 3 })).not.toContain("flash");
  });
});

describe("mandos de pantalla", () => {
  const controls = (modes: Partial<DisplayModes>) =>
    renderToStaticMarkup(
      createElement(
        DisplayModesContext.Provider,
        { value: { modes: { ...DEFAULT_MODES, ...modes }, update: () => undefined } },
        createElement(DisplayControls),
        createElement(ScreenTop),
      ),
    );

  it("cada modo dice su estado con aria-pressed y el anillo de elegido, no solo con el color", () => {
    const off = controls({});
    // Baja visión, alto contraste, esencial, tres giros sin elegir, seguir el sensor, seguir la
    // cara, privacidad, privacidad automática con otra cara y escuchar «EMMA»; y el idioma que no
    // está puesto (`LanguageChoice`, 2026-11-15). Elegidos: el giro de ahora y el idioma de ahora.
    expect(off.match(/aria-pressed="false"/g)).toHaveLength(12);
    expect(off.match(/aria-pressed="true"/g)).toHaveLength(2);
    expect(off).toMatch(/<button[^>]*lang="es"[^>]*aria-pressed="true"/);
    expect(off).toMatch(/<button[^>]*lang="en"[^>]*aria-pressed="false"/);
    const on = controls({ lowVision: true, highContrast: true, essential: true, privacy: true, rotation: 90 });
    expect(on.match(/aria-pressed="true"/g)).toHaveLength(6);
    expect(on.match(/data-pictogram="ring-dot"/g)).toHaveLength(6);
  });

  it("los rótulos con su dibujo; la privacidad puesta se quita con un mando que lo dice", () => {
    const off = controls({});
    for (const [concept, word] of [
      ["lowVision", "Baja visión"],
      ["highContrast", "Alto contraste"],
      ["essential", "Modo esencial"],
      ["orientation", "Girar"],
      ["privacy", "Privacidad"],
      ["screenTop", "Arriba"],
    ] as const) {
      // La flecha de «arriba» va dentro de su propio hueco, para poder girarla (`lib/upAngle.ts`).
      expect(off).toMatch(new RegExp(`data-pictogram="${uiPictogram(concept)}"[^>]*>.*?</svg>(?:</span>)?${word}`));
    }
    expect(controls({ privacy: true })).toContain("Quitar privacidad");
  });

  it("«Pantalla» plegado en el carril; el rótulo dice qué modos están puestos, y los mandos siguen dentro", () => {
    const folded = (modes: Partial<DisplayModes>) =>
      renderToStaticMarkup(
        createElement(
          DisplayModesContext.Provider,
          { value: { modes: { ...DEFAULT_MODES, ...modes }, update: () => undefined } },
          createElement(DisplayControls, { folded: true }),
        ),
      );
    const off = folded({});
    expect(off).toMatch(/<details data-ui="display-controls" class="display-controls">/);
    expect(off).not.toContain("display-summary");
    expect(off).toContain('<div class="display-body">');
    expect(off.match(/aria-pressed=/g)?.length).toBeGreaterThanOrEqual(10);
    const on = folded({ lowVision: true, highContrast: true, privacy: true, rotation: 90 });
    expect(on).toMatch(
      /<span class="display-summary secondary">baja visión · alto contraste · giro <span class="num">90<\/span> ° · privacidad<\/span>/,
    );
  });

  it("sin consola (sin carril), los mandos van a la vista, sin plegar", () => {
    const page = controls({});
    expect(page).not.toContain("<details");
    expect(page).toContain('class="display-controls" role="group" aria-label="Pantalla"');
  });

  it("el rótulo plegado no da por puesto lo que no funciona", () => {
    const words = (modes: Partial<DisplayModes>, voiceReady: boolean) =>
      renderToStaticMarkup(createElement("span", null, ...activeModes({ ...DEFAULT_MODES, ...modes }, voiceReady)));
    // Con la privacidad, ni cámara ni micrófono, aunque quedaran guardados.
    const privacy = words({ privacy: true, followFace: true, wakeWord: true }, true);
    expect(privacy).toContain("privacidad");
    expect(privacy).not.toContain("cara");
    expect(privacy).not.toContain("«EMMA»");
    // Sin voz local, ni voz ni iniciativa.
    expect(words({ voice: true, proactive: true }, false)).toBe("<span></span>");
    expect(words({ voice: true, proactive: true }, true)).toContain("voz");
  });

  it("la referencia de arriba dice el giro cuando lo hay", () => {
    expect(controls({ rotation: 180 })).toMatch(/vista girada <span class="num">180<\/span> °/);
    expect(controls({})).not.toContain("vista girada");
  });
});

describe("hoja de estilos de los modos", () => {
  const css = readFileSync(fileURLToPath(new URL("../styles.css", import.meta.url)), "utf8").replace(
    /\/\*[\s\S]*?\*\//g,
    "",
  );
  const rules = (attribute: string) =>
    [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(([, selector]) => selector?.includes(attribute));

  it("baja visión no pinta ningún color con significado ni cambia el de una señal", () => {
    const lowVision = rules('data-low-vision="on"');
    expect(lowVision.length).toBeGreaterThan(3);
    for (const [, selector, body] of lowVision) {
      // Ningún selector de color con significado (`.c-red`…), salvo para excluirlo.
      expect(selector?.replace(/:not\(\[class\*="c-"\]\)/g, "")).not.toMatch(/\.c-/);
      for (const color of body?.match(/var\(--c-[a-z-]+\)/g) ?? []) {
        expect(["var(--c-text)", "var(--c-text-secondary)"], `${selector}: ${color}`).toContain(color);
      }
    }
    // El texto secundario sube al color del texto, sin alcanzar lo que lleva color de significado.
    expect(css).toMatch(/\.app\[data-low-vision="on"\] \.secondary:not\(\[class\*="c-"\]\) \{\s*color: var\(--c-text\);/);
  });

  it("alto contraste no escribe colores: los cambia la paleta; añade grosor y señales sin color", () => {
    const high = rules('data-high-contrast="on"');
    expect(high.length).toBeGreaterThan(3);
    for (const [, selector, body] of high) {
      expect(body, selector).not.toMatch(/(?:^|[\s;])(?:color|background(?:-color)?|border-color|outline-color|fill|stroke):/);
      expect(body, selector).not.toMatch(/var\(--c-/);
    }
    expect(css).toMatch(/\.app\[data-high-contrast="on"\] :focus-visible \{[^}]*outline-width: 4px/);
    expect(css).toMatch(/\.app\[data-high-contrast="on"\] button\.command:disabled \{[^}]*border-style: dashed/);
  });

  it("ni baja visión ni alto contraste borran el filete del nivel (F.5.10 e)", () => {
    const framed = [...rules('data-low-vision="on"'), ...rules('data-high-contrast="on"')].filter(([, selector]) =>
      /\.panel|\.domain|article\.hazard/.test(selector ?? ""),
    );
    expect(framed.length).toBeGreaterThanOrEqual(4);
    for (const [, selector, body] of framed) {
      expect(body, selector).not.toMatch(/(?:^|[\s;])border(?:-width|-color)?:/);
      if (/border-left/.test(body ?? "")) expect(selector, selector).toMatch(/:not\(\[data-level\]\)/);
    }
  });

  it("alto contraste guardado se lee, y uno de antes de existir queda apagado", () => {
    expect(parseModes('{"highContrast": true, "lowVision": true}')).toEqual({
      ...DEFAULT_MODES,
      highContrast: true,
      lowVision: true,
    });
    expect(parseModes('{"lowVision": true}').highContrast).toBe(false);
    expect(parseModes('{"highContrast": "si"}').highContrast).toBe(false);
  });

  it("objetivos táctiles de 44 px o más en el carril y en los mandos de pantalla", () => {
    expect(css).toMatch(/\.rail-tabs > button\[role="tab"\] \{[^}]*min-height: 48px/);
    expect(css).toMatch(/\.display-controls button\.command \{[^}]*min-height: 44px/);
    // Con el dedo, 48 px; el rótulo de «Pantalla», como una pestaña.
    expect(css).toMatch(/@media \(pointer: coarse\) \{\s*\.display-controls button\.command \{\s*min-height: 48px/);
    expect(css).toMatch(/\.display-controls > summary\.display-toggle \{[^}]*min-height: 48px/);
  });

  it("los mandos de «Pantalla» no se cortan: dos columnas que se parten en líneas", () => {
    expect(css).toMatch(/\.display-body \{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
    expect(css).toMatch(/\.display-controls button\.command \{[^}]*hyphens: auto/);
    expect(css).toMatch(/\.console-layout\[data-rail="top"\] \.rail \{[^}]*position: static/);
  });

  it("la ampliación de baja visión es la misma que cuenta `railPlacement`", () => {
    expect(css).toMatch(new RegExp(`\\.app\\[data-low-vision="on"\\] \\{\\s*zoom: ${LOW_VISION_ZOOM};`));
  });

  it("los cuatro giros existen", () => {
    for (const rotation of ["90", "180", "270"]) expect(css).toContain(`.app[data-rotation="${rotation}"]`);
  });
});

describe("el carril de la concha nueva (`shell/rail.css`, lote «muestra»)", () => {
  const rail = readFileSync(fileURLToPath(new URL("../shell/rail.css", import.meta.url)), "utf8").replace(
    /\/\*[\s\S]*?\*\//g,
    "",
  );
  const hex = (value: string) => [1, 3, 5].map((at) => Number.parseInt(value.slice(at, at + 2), 16));
  // `color-mix(in srgb, a p%, b)`: la media de los valores tal cual, canal a canal.
  const mix = (a: string, b: string, share: number) => {
    const under = hex(b);
    return `#${hex(a)
      .map((channel, index) => Math.round(channel * share + (under[index] ?? 0) * (1 - share)))
      .map((channel) => channel.toString(16).padStart(2, "0"))
      .join("")}`;
  };
  // Los dos extremos del relleno de la abierta, leídos de la regla (con o sin alto contraste).
  const fillShares = (prefix: string) => {
    const at = rail.indexOf(`${prefix} .rail-tabs > button[role="tab"][aria-selected="true"]:hover {`);
    const rule = rail.slice(at, rail.indexOf("}", at));
    return [...rule.matchAll(/color-mix\(in srgb, var\(--ref-teal\) (\d+)%, var\(--c-surface\)\)/g)].map(
      (match) => Number(match[1]) / 100,
    );
  };
  const pillShare = () => {
    const rule = /\.rail-tabs > button\[role="tab"\] > \.tab-alerts \{([^}]*)\}/.exec(rail)?.[1] ?? "";
    return Number(/background: color-mix\(in srgb, var\(--ref-navy\) (\d+)%, transparent\)/.exec(rule)?.[1]) / 100;
  };
  const cases = [
    { name: "base", colors: PALETTES.base, prefix: '.app[data-look="reference"]', text: MIN_CONTRAST, signal: MIN_CONTRAST },
    {
      name: "alto contraste",
      colors: PALETTES.highContrast,
      prefix: '.app[data-look="reference"][data-high-contrast="on"]',
      text: HIGH_CONTRAST_TEXT_MIN,
      signal: HIGH_CONTRAST_MIN,
    },
  ];

  it.each(cases)("la abierta va rellena del verde azulado y se lee con su umbral ($name)", ({ colors, prefix, text, signal }) => {
    const shares = fillShares(prefix);
    expect(shares).toHaveLength(2);
    // `--ref-teal` y `--ref-navy` (`consoleShell.css`).
    const teal = mix(colors.cyan, colors.blue, 0.45);
    const navy = mix(colors.blue, colors.bg, 0.1);
    const pill = pillShare();
    expect(pill).toBeGreaterThan(0);
    for (const share of shares) {
      const fill = mix(teal, colors.surface, share);
      expect(contrast(colors.text, fill)).toBeGreaterThanOrEqual(text);
      // El recuento de alertas sobre la abierta: el color de cada nivel, sobre su píldora.
      const under = mix(navy, fill, pill);
      for (const level of [colors.red, colors.yellow, colors.blue]) {
        expect(contrast(level, under)).toBeGreaterThanOrEqual(signal);
      }
    }
  });

  it("filas de 2,8 rem y nunca por debajo del alto táctil; ninguna letra por debajo de 0,875 rem", () => {
    expect(rail).toMatch(/\.rail-tabs > button\[role="tab"\] \{[^}]*min-height: max\(var\(--touch\), 2\.8rem\)/);
    const sizes = [...rail.matchAll(/font-size: ([\d.]+)rem/g)].map((match) => Number(match[1]));
    expect(sizes.length).toBeGreaterThan(0);
    for (const size of sizes) expect(size).toBeGreaterThanOrEqual(0.875);
    expect(rail).not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(|hsl\(/i);
  });
});

describe("la franja de arriba y la Tierra del carril (lote «muestra», ronda 4)", () => {
  const rail = (look: "reference" | "classic") =>
    renderToStaticMarkup(
      createElement(
        LookContext.Provider,
        { value: look },
        createElement(
          RailTopContext.Provider,
          { value: look === "reference" ? createElement("p", null, "CONMUTADOR") : null },
          createElement(
            DisplayModesContext.Provider,
            { value: { modes: DEFAULT_MODES, update: () => undefined } },
            createElement(ConsoleTabs, {
              id: "crew",
              label: "Secciones",
              sections: SECTIONS,
              counts: NONE,
              header: createElement("p", { className: "active-environment" }, "ENTORNO"),
              headerGroup: "Entornos",
              stored: null,
              onChoose: () => undefined,
            }),
          ),
        ),
      ),
    );

  it("en la concha nueva, conmutador y entorno en una sola franja, sin perder la palabra del pliegue", () => {
    const html = rail("reference");
    const strip = html.slice(html.indexOf('<div class="rail-strip">'), html.indexOf("crew-tab-hazards"));
    expect(strip).toContain('<div class="rail-top"><p>CONMUTADOR</p></div>');
    expect(strip).toContain('class="active-environment">ENTORNO</p>');
    // El pliegue sigue siendo el mismo (`data-ui`) y su rótulo sigue en el texto y en el `title`.
    expect(strip).toMatch(/<details data-ui="environment-choices"[^>]*title="Ver o elegir otro entorno"/);
    expect(strip).toMatch(/<summary>.*<span class="rail-choices-word">Ver o elegir otro entorno<\/span><\/summary>/);
    // Cada entorno, con su propio `title`: no hereda el del pliegue.
    expect(strip).toMatch(/id="crew-tab-env-leo"[^>]*title="Órbita baja"/);
  });

  it("la Tierra de noche va en el carril, de adorno y fuera del lector de pantalla; en la clásica, nada", () => {
    const html = rail("reference");
    const nav = html.slice(html.indexOf('<nav class="rail"'), html.indexOf("</nav>"));
    expect(nav).toMatch(/<svg class="rail-earth"[^>]*aria-hidden="true"/);
    const classic = rail("classic");
    expect(classic).not.toContain("rail-earth");
    expect(classic).not.toContain("rail-strip");
    expect(classic).toContain("Ver o elegir otro entorno</summary>");
  });
});

describe("rótulos de los entornos en la cabecera", () => {
  const SITES: ConsoleSection[] = [
    { key: "home", label: "Inicio", pictogram: uiPictogram("body"), panels: ["PANEL-INICIO"] },
    {
      key: "env-leo",
      label: "Órbita baja terrestre (estación espacial)",
      pictogram: uiPictogram("compare"),
      group: "Entornos",
      panels: ["PANEL-LEO"],
    },
  ];
  const tab = (look: "reference" | "classic") => {
    const html = renderToStaticMarkup(
      createElement(
        LookContext.Provider,
        { value: look },
        createElement(
          DisplayModesContext.Provider,
          { value: { modes: DEFAULT_MODES, update: () => undefined } },
          createElement(ConsoleTabs, {
            id: "crew",
            label: "Secciones",
            sections: SITES,
            counts: NONE,
            headerGroup: "Entornos",
            stored: null,
            onChoose: () => undefined,
          }),
        ),
      ),
    );
    return /<button[^>]*id="crew-tab-env-leo"[^>]*>[\s\S]*?<\/button>/.exec(html)?.[0] ?? "";
  };

  it("la aclaración entre paréntesis, solo la última y solo si cierra el rótulo", () => {
    expect(asideAt("Órbita baja terrestre (estación espacial)")).toBe(21);
    expect(asideAt("Superficie lunar")).toBeNull();
    expect(asideAt("(nada) delante")).toBeNull();
    expect(asideAt("Marte (superficie) tras tránsito (largo)")).toBe(32);
    expect(asideAt("Espacio (a (b))")).toBeNull();
  });

  it("en la concha nueva, una línea a la vista; el nombre entero en el texto de la pestaña y en su title", () => {
    const html = tab("reference");
    expect(html).toContain('title="Órbita baja terrestre (estación espacial)"');
    expect(html).toMatch(/Órbita baja terrestre<span class="tab-aside sr-only"> \(estación espacial\)<\/span>/);
    expect(html.replace(/<[^>]+>/g, "")).toBe("Órbita baja terrestre (estación espacial)");
  });

  it("en la clásica, el rótulo como siempre", () => {
    const html = tab("classic");
    expect(html).not.toContain("title=");
    expect(html).not.toContain("tab-aside");
    expect(html).toContain("Órbita baja terrestre (estación espacial)");
  });
});
