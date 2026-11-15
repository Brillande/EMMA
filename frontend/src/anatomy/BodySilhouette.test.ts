import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { SITED_REGIONS, Silhouette, isSitedRegion, siteAnchor } from "../icons/Silhouette";
import { type AnatomyRegionState, type AnatomyState, ApiError } from "../lib/api";
import { DOMAIN_LABELS, LEVELS, adoptLevelLabels } from "../lib/levels";
import { requestOutcome } from "../lib/marks";
import { BodySilhouette, UNSITED_REGIONS } from "./BodySilhouette";
import { NO_STATE } from "./chain";
import type { AnatomyView } from "./useAnatomyState";

/**
 * La silueta del resumen: las regiones son exactamente las del backend, cada una con el
 * pictograma de su dominio y su nivel en palabra y forma, las dos sin organo propio al pie, y
 * la eleccion con `aria-pressed` y su pictograma. Se pinta a HTML estatico (sin navegador no hay
 * efectos ni red): lo que se comprueba es lo que la interfaz promete emitir.
 */

adoptLevelLabels({
  nominal: "Nominal",
  watch: "Vigilancia",
  concern: "Precaución",
  critical: "Crítico",
});

const ANATOMY_PY = fileURLToPath(new URL("../../../backend/app/anatomy.py", import.meta.url));

/**
 * Las claves de `REGIONS` en `anatomy.py`: cada `Region(` abre con su clave, su display y una
 * tupla de un dominio, o una tupla vacía y, más abajo, `level_of=Domain.X` (una región sin nivel
 * propio, como el hígado). Si el backend escribiera una region de otra forma (dos dominios, otro
 * formato), la cuenta de `Region(` dejaria de cuadrar y la prueba lo diria en vez de callarsela.
 */
function backendRegions(): { key: string; display: string; domain: string; levelOf: string | null }[] {
  const source = readFileSync(ANATOMY_PY, "utf8");
  const kebab = (name: string | undefined) => (name ?? "").toLowerCase().replace(/_/g, "-");
  const found = [
    ...source.matchAll(
      /\bRegion\(\s*"([a-z-]+)",\s*"([^"]+)",\s*\((?:Domain\.([A-Z_]+),)?\)(?:[^()]*?level_of=Domain\.([A-Z_]+))?/g,
    ),
  ].map((match) => ({
    key: match[1] ?? "",
    display: match[2] ?? "",
    domain: kebab(match[3]),
    levelOf: match[4] === undefined ? null : kebab(match[4]),
  }));
  // Una región sin dominio tiene que decir de quién es su nivel; una con dominio, no.
  for (const item of found) {
    if ((item.domain === "") !== (item.levelOf !== null)) throw new Error(`region mal leida: ${item.key}`);
  }
  // La clase `Region(` y las de las pruebas no cuentan: solo las del registro `REGIONS`.
  const opened = source.match(/\n {4}Region\(/g)?.length ?? 0;
  if (found.length === 0) throw new Error("no se encuentra ninguna Region( en anatomy.py");
  if (found.length !== opened) {
    throw new Error(`anatomy.py abre ${opened} Region( y la prueba solo entiende ${found.length}`);
  }
  return found;
}

const BACKEND = backendRegions();

/** Un estado por regiones con las claves y los textos del backend; el nivel lo da la prueba. */
function region(
  key: string,
  level: string | null,
  overrides: Partial<AnatomyRegionState> = {},
): AnatomyRegionState {
  const spec = BACKEND.find((item) => item.key === key);
  if (spec === undefined) throw new Error(`region desconocida en la prueba: ${key}`);
  const own = spec.levelOf === null;
  return {
    key,
    display: spec.display,
    domains: own ? [spec.domain] : [],
    note: "",
    level: own ? level : null,
    has_data: level !== null,
    data_note: null,
    state: own
      ? [
          {
            domain: spec.domain,
            level,
            has_data: level !== null,
            drivers: [],
            risk: {
              risk_id: spec.domain,
              display: spec.domain,
              ridge: { category: "gravity", display: "campos gravitatorios", source: { id: "", title: "", url: null } },
              hrp_risk: null,
              uncertainty_statement: "",
            },
          },
        ]
      : [],
    variables: [],
    unmeasured: [],
    evidence: [],
    recommendations: [],
    recommendations_note: null,
    context: null,
    analytes: own ? [] : ["alt"],
    level_of: spec.levelOf,
    level_note: own ? null : levelNote(spec.levelOf),
    analytes_source: null,
    note_refs: [],
    research: null,
    level_risk: null,
    function: null,
    function_refs: [],
    function_note: null,
    ...overrides,
  };
}

/** La frase de `anatomy.LEVEL_OF_NOTE` para el hígado, tal cual la da el backend. */
const LEVEL_NOTE = "El nivel es del dominio nutrición.";
/** La de los pulmones (decimosexta ronda, §5.36.13). */
const LUNG_LEVEL_NOTE = "El nivel es del dominio cardiovascular.";
const LEVEL_NOTES: Record<string, string> = { nutrition: LEVEL_NOTE, cardiovascular: LUNG_LEVEL_NOTE };

function levelNote(levelOf: string | null): string {
  const note = levelOf === null ? undefined : LEVEL_NOTES[levelOf];
  if (note === undefined) throw new Error(`sin frase de nivel para ${levelOf}`);
  return note;
}

const LEVEL_OF: Record<string, string | null> = {
  brain: "nominal",
  eyes: "nominal",
  heart: "watch",
  bones: "concern",
  muscles: "nominal",
  bladder: null,
  digestive: "nominal",
  // Sin nivel propio: lo que se pase aquí no se usa como nivel.
  liver: "watch",
  lungs: "critical",
  immune: null,
  "whole-body": "critical",
};

const state: AnatomyState = {
  subject: "crew-01",
  reference_time: "2026-12-11T00:00:00+00:00",
  rules_version: "test",
  regions: BACKEND.map((item) => region(item.key, LEVEL_OF[item.key] ?? null)),
  moment: null,
  moments: { current_display: "Ahora", items: [], basis: "" },
};

const VIEW: AnatomyView = { state, error: null, stale: false };

function render(selected: string | null = null, view: AnatomyView = VIEW): string {
  return renderToStaticMarkup(
    createElement(BodySilhouette, { view, selected, onSelect: () => {} }),
  );
}

/** El boton de una region, con todo lo que contiene. */
function site(html: string, key: string): string {
  const match = new RegExp(`<button type="button" class="site site-${key}[^"]*"[^>]*>.*?</button>`).exec(html);
  if (match === null) throw new Error(`no hay boton para ${key}`);
  return match[0];
}

/** El HTML escapa las comillas y los ampersands; los textos de prueba no llevan otros. */
const shown = (text: string) => text.replaceAll("&", "&amp;").replaceAll('"', "&quot;");

describe("las regiones de la silueta son las del backend", () => {
  it("anatomy.py se lee de verdad: nueve regiones con clave, display y dominio", () => {
    expect(BACKEND.length).toBeGreaterThanOrEqual(5);
    expect(BACKEND.map((item) => item.key)).toContain("heart");
    expect(BACKEND.find((item) => item.key === "heart")?.domain).toBe("cardiovascular");
    for (const item of BACKEND) expect((item.domain || item.levelOf || "") in DOMAIN_LABELS, item.key).toBe(true);
    expect(BACKEND.find((item) => item.key === "liver")).toEqual({
      key: "liver",
      display: "Hígado",
      domain: "",
      levelOf: "nutrition",
    });
    expect(BACKEND.find((item) => item.key === "lungs")).toEqual({
      key: "lungs",
      display: "Pulmones",
      domain: "",
      levelOf: "cardiovascular",
    });
  });

  it("las que tienen sitio en la figura y las que van al pie son, juntas, exactamente las del backend", () => {
    const sited: readonly string[] = SITED_REGIONS;
    const unsited: readonly string[] = UNSITED_REGIONS;
    expect([...sited, ...unsited].sort()).toEqual(BACKEND.map((item) => item.key).sort());
    for (const key of unsited) expect(isSitedRegion(key), key).toBe(false);
  });

  it("el dibujo tiene una zona por region con sitio, y ninguna mas", () => {
    const html = renderToStaticMarkup(createElement(Silhouette, {}));
    const zones = [...html.matchAll(/<g class="zone[^"]*" data-region="([a-z-]+)"/g)].map((m) => m[1]);
    expect(zones).toEqual([...SITED_REGIONS]);
    expect(html).toContain('viewBox="0 0 200 480"');
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain('stroke="currentColor"');
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|style=/);
    expect(textNodes(html)).toEqual([]);
  });

  it("cada zona tiene su ancla dentro del lienzo y un lado por el que rotularse", () => {
    for (const key of SITED_REGIONS) {
      const anchor = siteAnchor(key);
      expect(anchor.y, key).toBeGreaterThan(0);
      expect(anchor.y, key).toBeLessThan(1);
      expect(["left", "right"], key).toContain(anchor.side);
    }
    // De arriba abajo en el cuerpo: cabeza, ojos, pulmones, corazon, higado, espalda, digestivo,
    // vejiga, piernas.
    const order = [...SITED_REGIONS].sort((a, b) => siteAnchor(a).y - siteAnchor(b).y);
    expect(order).toEqual(["brain", "eyes", "lungs", "heart", "liver", "muscles", "digestive", "bladder", "bones"]);
  });
});

describe("cada region, con su dominio y su nivel en palabra y forma", () => {
  const html = render();

  it("un boton por region, con el display del backend como aria-label y sin texto inventado", () => {
    for (const item of BACKEND) {
      const button = site(html, item.key);
      expect(button).toContain(`aria-label="${shown(item.display)}"`);
      expect(button).toContain(`data-region="${item.key}"`);
      expect(button).toContain('aria-pressed="false"');
      // El nombre es el display; la descripcion, lo que se ve (dominio y nivel): el lector de
      // pantalla oye los tres.
      expect(button).toContain(`aria-describedby="site-${item.key}-state"`);
      expect(button).toContain(`<span id="site-${item.key}-state" class="site-state">`);
    }
    const words = new Set(textNodes(html));
    const allowed = new Set([
      ...Object.values(DOMAIN_LABELS),
      ...Object.values(LEVELS).map((style) => style.label),
      NO_STATE.label,
      // La región sin dominio se nombra con su display, y su nivel con la frase del backend.
      ...BACKEND.filter((item) => item.levelOf !== null).map((item) => item.display),
      ...Object.values(LEVEL_NOTES),
    ]);
    for (const word of words) expect(allowed.has(word), `texto no previsto: «${word}»`).toBe(true);
  });

  it("el pictograma del dominio va junto a su nombre, y el nivel con su pictograma, su palabra y su color", () => {
    const heart = site(html, "heart");
    expect(heart).toContain('data-pictogram="domain-cardiovascular"');
    expect(heart).toContain(DOMAIN_LABELS.cardiovascular);
    expect(heart).toContain(`data-pictogram="${LEVELS.watch.pictogram}"`);
    expect(heart).toContain(`<span class="mark level c-${LEVELS.watch.color}">`);
    expect(heart).toContain(LEVELS.watch.label);

    const bones = site(html, "bones");
    expect(bones).toContain('data-pictogram="domain-bone"');
    expect(bones).toContain(`data-pictogram="${LEVELS.concern.pictogram}"`);
    expect(bones).toContain(LEVELS.concern.label);

    const whole = site(html, "whole-body");
    expect(whole).toContain('data-pictogram="domain-radiation"');
    expect(whole).toContain(`data-pictogram="${LEVELS.critical.pictogram}"`);
    expect(whole).toContain(LEVELS.critical.label);
  });

  it("una region sin lecturas se marca como dato ausente: anillo punteado en cian, no nominal", () => {
    for (const key of ["bladder", "immune"]) {
      const button = site(html, key);
      expect(button).toContain(`data-pictogram="${NO_STATE.pictogram}"`);
      expect(button).toContain(`<span class="mark level c-${NO_STATE.color}">`);
      expect(button).toContain(NO_STATE.label);
      expect(button).not.toContain(LEVELS.nominal.label);
    }
  });

  it("la zona del dibujo lleva el color del nivel de su region", () => {
    expect(html).toContain(`<g class="zone c-${LEVELS.watch.color}" data-region="heart"`);
    expect(html).toContain(`<g class="zone c-${LEVELS.concern.color}" data-region="bones"`);
    expect(html).toContain(`<g class="zone c-${NO_STATE.color}" data-region="bladder"`);
    expect(html).toContain(`<g class="zone c-${LEVELS.nominal.color}" data-region="brain"`);
  });

  it("las regiones sin organo propio van al pie, y las demas sobre la figura, a la altura de su zona", () => {
    const [figure = "", foot = ""] = html.split('<ul class="body-silhouette-foot">');
    expect(foot).not.toBe("");
    for (const key of UNSITED_REGIONS) {
      expect(foot).toContain(`class="site site-${key}"`);
      expect(figure).not.toContain(`site-${key}`);
      expect(site(html, key)).not.toContain("style=");
    }
    for (const key of SITED_REGIONS) {
      const anchor = siteAnchor(key);
      const button = site(figure, key);
      expect(button).toContain(`class="site site-${key} site-${anchor.side}"`);
      expect(button).toContain(`style="top:${anchor.y * 100}%;--reach:${anchor.reach}"`);
      expect(foot).not.toContain(`site-${key}`);
    }
  });

  it("los unicos estilos en linea son la altura del rotulo y su alcance; ningun color ni glifo de texto", () => {
    for (const style of html.match(/style="[^"]*"/g) ?? []) {
      expect(style).toMatch(/^style="top:[0-9.]+%;--reach:[0-9.]+"$/);
    }
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(/);
    expect(html).not.toMatch(/[○◇△■●◐▷◌⊘✕]/);
  });
});

describe("una region sin nivel propio: el higado (§5.35.11)", () => {
  const html = render();

  it("su rotulo es su nombre con el dibujo de su organo y la frase del backend con el de su dominio", () => {
    const liver = site(html, "liver");
    expect(liver).toContain('data-pictogram="liver"');
    expect(liver).toContain("Hígado");
    expect(liver).toContain(LEVEL_NOTE);
    expect(liver).toContain('data-pictogram="domain-nutrition"');
    expect(liver).toContain('<span class="mark level secondary">');
  });

  it("sin insignia de nivel ni color de nivel, en el rotulo y en la zona del dibujo", () => {
    const liver = site(html, "liver");
    expect(liver).not.toMatch(/class="mark level c-/);
    for (const style of Object.values(LEVELS)) expect(liver).not.toContain(style.label);
    expect(liver).not.toContain(NO_STATE.label);
    expect(html).toContain('<g class="zone" data-region="liver"');
  });

  it("tambien se elige, con su pictograma de «elegido»", () => {
    const liver = site(render("liver"), "liver");
    expect(liver).toContain('aria-pressed="true"');
    expect(liver).toContain('data-pictogram="ring-dot"');
  });
});

describe("una region sin nivel propio: los pulmones (§5.36.13)", () => {
  const html = render();

  it("su rotulo es su nombre con el dibujo de su organo y la frase del backend con el de su dominio", () => {
    const lungs = site(html, "lungs");
    expect(lungs).toContain('data-pictogram="lungs"');
    expect(lungs).toContain("Pulmones");
    expect(lungs).toContain(LUNG_LEVEL_NOTE);
    expect(lungs).toContain('data-pictogram="domain-cardiovascular"');
    expect(lungs).toContain('<span class="mark level secondary">');
  });

  it("sin insignia ni color de nivel, aunque se le pase uno: el nivel es del corazon", () => {
    const lungs = site(html, "lungs");
    expect(lungs).not.toMatch(/class="mark level c-/);
    for (const style of Object.values(LEVELS)) expect(lungs).not.toContain(style.label);
    expect(lungs).not.toContain(NO_STATE.label);
    expect(html).toContain('<g class="zone" data-region="lungs"');
  });

  it("se rotula por la derecha, junto a su zona, y se elige como las demas", () => {
    expect(site(html, "lungs")).toContain('class="site site-lungs site-right"');
    const chosen = render("lungs");
    expect(site(chosen, "lungs")).toContain('aria-pressed="true"');
    expect(chosen).toContain('data-region="lungs" data-selected="true"');
  });
});

describe("la eleccion", () => {
  it("la region elegida lleva aria-pressed y el pictograma de «elegido»; las demas, no", () => {
    const html = render("heart");
    const heart = site(html, "heart");
    expect(heart).toContain('aria-pressed="true"');
    expect(heart).toContain('data-pictogram="ring-dot"');
    expect(html).toContain('data-region="heart" data-selected="true"');
    for (const item of BACKEND.filter((entry) => entry.key !== "heart")) {
      expect(site(html, item.key)).not.toContain('data-pictogram="ring-dot"');
    }
    expect(html.match(/data-pictogram="ring-dot"/g)).toHaveLength(1);
    expect(html.match(/data-selected="true"/g)).toHaveLength(1);
  });

  it("una region del pie tambien se puede elegir", () => {
    expect(site(render("immune"), "immune")).toContain('aria-pressed="true"');
  });
});

describe("mientras no hay estado, o el que hay no es el de la consola", () => {
  it("dice que carga, sin regiones", () => {
    const html = render(null, { state: null, error: null, stale: false });
    expect(html).toContain("Cargando…");
    // Con la marca de «cargando» (§5.33): la flecha que gira, sin color.
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="refresh">.*?<\/svg>Cargando…<\/span>/);
    expect(html).not.toContain("<button");
  });

  it("un fallo se dice con la marca de la petición que cayó y el texto del error (§5.34.14)", () => {
    const html = render(null, { state: null, error: requestOutcome(new ApiError(503, "HTTP 503")), stale: false });
    expect(html).toContain('data-pictogram="cross"');
    expect(html).toContain('<span class="mark c-red">');
    expect(html).toContain("HTTP 503");
    expect(html).not.toContain("<button");
    expect(html).not.toContain("Cargando…");
  });

  it("un fallo al recargar no borra la figura del ultimo estado: se dicen los dos, como en «Cuerpo»", () => {
    const html = render(null, { state, error: requestOutcome(new ApiError(503, "HTTP 503")), stale: false });
    expect(html).toContain("HTTP 503");
    expect(html).toContain('class="body-silhouette-figure"');
    expect(site(html, "heart")).toContain(LEVELS.watch.label);
  });

  it("un estado anterior al de la consola se avisa con el mismo texto que el modo anatomico", () => {
    const html = render(null, { state, error: null, stale: true });
    expect(html).toContain("El estado por regiones es anterior al que muestra la consola; se está actualizando.");
    expect(html).toContain('class="body-silhouette-figure"');
    expect(render()).not.toContain("anterior al que muestra la consola");
  });

  it("una region que el backend añadiera sin sitio en la figura va al pie, no se pierde", () => {
    const extra: AnatomyState = {
      ...state,
      regions: [...state.regions, { ...region("heart", "watch"), key: "skin", display: "Piel" }],
    };
    const html = render(null, { state: extra, error: null, stale: false });
    const [, foot = ""] = html.split('<ul class="body-silhouette-foot">');
    expect(foot).toContain('class="site site-skin"');
    expect(foot).toContain('aria-label="Piel"');
  });
});
