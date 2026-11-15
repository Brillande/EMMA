import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { EphemerisCoverage, MissionProfile, ProfileAspect, ProfileCitation, SolarConjunction } from "../lib/api";
import { formatSourceDate } from "../lib/format";
import { UNKNOWN_MARK, mark } from "../lib/marks";
import { EphemerisCoverageView, MissionProfileView } from "./MissionProfileView";
import { aspectPictogram, conjunctionPictogram, profilePictogram } from "./missionPictograms";
import {
  UNKNOWN_PROFILE_MARK,
  aspectStyle,
  cachedStyle,
  conjunctionStyle,
  coverageStyle,
  ephemerisStyle,
} from "./missionProfile";

/*
 * El perfil de mision se MUESTRA: cada frase es del backend (`evidence/mission_profiles.py`).
 * Se comprueba pintandolo con un ejemplo y buscando cada frase tal cual, y leyendo su fuente
 * para ver que no redacta nada de lo que dice un perfil.
 */

const citation = (over: Partial<ProfileCitation> = {}): ProfileCitation => ({
  ref: "ficha-de-prueba",
  title: "Pagina de prueba",
  url: "https://www.nasa.gov/prueba/",
  section: "apartado de prueba",
  quote: "A literal sentence read on the page.",
  read_on: "2026-10-13",
  ...over,
});

const aspect = (over: Partial<ProfileAspect> = {}): ProfileAspect => ({
  key: "comm_delay",
  label: "rotulo del backend",
  status: "read",
  status_text: "estado leido del backend",
  statement: "frase del backend sobre el aspecto",
  citations: [citation()],
  discrepancy: null,
  searched: null,
  emma_note: null,
  reused_from: [],
  ...over,
});

const profile = (over: Partial<MissionProfile> = {}): MissionProfile => ({
  id: "perfil-de-prueba",
  known: true,
  display: "nombre del perfil segun el backend",
  note: "nota del backend: descriptivo",
  declared: "frase del backend sobre como se declara",
  unknown_text: null,
  ephemeris: { state: "consistent", target_body: "000", text: "frase del backend: casa" },
  aspects: [
    aspect(),
    aspect({
      key: "return_or_evacuation",
      label: "otro rotulo del backend",
      status: "unverified",
      status_text: "estado sin verificar del backend",
      statement: null,
      citations: [],
      searched: "lo que el backend dice que se busco",
    }),
    aspect({
      key: "distance",
      label: "tercer rotulo",
      discrepancy: {
        text: "frase del backend sobre la discrepancia",
        citations: [citation({ quote: "Another page says otherwise.", title: "Otra pagina" })],
      },
    }),
  ],
  pages_read: [
    { title: "Pagina de prueba", url: "https://www.nasa.gov/prueba/", read_on: ["2026-10-13", "2026-10-21"] },
    { title: "Pagina leida sin cita", url: "https://www.nasa.gov/otra/", read_on: ["2026-10-13"] },
  ],
  ...over,
});

const render = (value: MissionProfile) =>
  renderToStaticMarkup(createElement(MissionProfileView, { profile: value }));

describe("perfil de mision: señales", () => {
  it("lo leido no lleva señal y lo que falta va en cian con el anillo punteado", () => {
    expect(aspectStyle("read")).toEqual(mark(null, null));
    expect(aspectStyle("unverified")).toEqual(mark("ring-dotted", "cyan"));
    expect(UNKNOWN_PROFILE_MARK).toEqual(mark("ring-dotted", "cyan"));
  });

  it("un desajuste con las efemerides es una precaucion, y lo no comprobable un dato ausente", () => {
    expect(ephemerisStyle("consistent")).toEqual(mark(null, null));
    expect(ephemerisStyle("mismatch")).toEqual(mark("shape-triangle", "yellow"));
    expect(ephemerisStyle("unchecked")).toEqual(mark("ring-dotted", "cyan"));
  });

  it("un perfil sin objetivo de efemerides (2026-11-11) no es un fallo: su frase, sin señal", () => {
    expect(ephemerisStyle("no_target")).toEqual(mark(null, null));
  });

  it("un estado desconocido no se pinta como leido: falla", () => {
    expect(() => aspectStyle("proven")).toThrow(RangeError);
    expect(() => ephemerisStyle("whatever")).toThrow(RangeError);
  });

  it("cada perfil y cada aspecto del backend tienen su dibujo; uno nuevo, el de desconocido", () => {
    const profiles = ["leo", "cislunar", "lunar-surface", "mars-transit", "mars-surface"];
    const aspects = ["comm_delay", "gravity_regime", "return_or_evacuation", "resupply", "typical_duration", "distance", "radiation_environment", "surface_dust", "day_night_cycle", "medical_capability"];
    const drawn = new Set<string>();
    for (const id of profiles) {
      const pictogram = profilePictogram(id);
      expect(pictogram, id).not.toBe(UNKNOWN_MARK.pictogram);
      drawn.add(String(pictogram));
    }
    for (const key of aspects) {
      const pictogram = aspectPictogram(key);
      expect(pictogram, key).not.toBe(UNKNOWN_MARK.pictogram);
      drawn.add(String(pictogram));
    }
    // Un dibujo por cosa: ninguno se repite entre perfiles y aspectos.
    expect(drawn.size).toBe(profiles.length + aspects.length);
    expect(profilePictogram("venus-flyby")).toBe(UNKNOWN_MARK.pictogram);
    expect(aspectPictogram("crew_size")).toBe(UNKNOWN_MARK.pictogram);
  });
});

describe("perfil de mision: lo que se pinta", () => {
  it("enseña cada frase del backend tal cual, y la nota de que es descriptivo fuera del desplegable", () => {
    const html = render(profile());
    for (const text of [
      "nombre del perfil segun el backend",
      "nota del backend: descriptivo",
      "frase del backend: casa",
      "rotulo del backend",
      "frase del backend sobre el aspecto",
      "A literal sentence read on the page.",
      "apartado de prueba",
      "estado sin verificar del backend",
      "lo que el backend dice que se busco",
      "frase del backend sobre la discrepancia",
      "Another page says otherwise.",
      "frase del backend sobre como se declara",
      "Pagina leida sin cita",
    ]) {
      expect(html).toContain(text);
    }
    expect(html.indexOf("nota del backend: descriptivo")).toBeLessThan(html.indexOf("<details"));
    expect(html).toContain('href="https://www.nasa.gov/prueba/"');
  });

  it("lo sin verificar va en cian con el anillo punteado y la palabra, nunca solo con color", () => {
    const html = render(profile());
    expect(html).toMatch(
      /<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>estado sin verificar del backend<\/span>/,
    );
    expect(html).not.toContain("◌");
  });

  it("el perfil y cada aspecto llevan su dibujo junto al nombre del backend, sin color", () => {
    const html = render(profile({ id: "leo" }));
    expect(html).toMatch(
      /<strong><span class="mark"><svg [^>]*data-pictogram="globe-satellite"[^>]*>.*?<\/svg>nombre del perfil segun el backend<\/span><\/strong>/,
    );
    expect(html).toMatch(/<svg [^>]*data-pictogram="signal-arcs"[^>]*>.*?<\/svg>rotulo del backend<\/span>:/);
    expect(html).toMatch(/<svg [^>]*data-pictogram="arrow-u-turn"[^>]*>.*?<\/svg>otro rotulo del backend<\/span>:/);
    expect(html).toMatch(/<svg [^>]*data-pictogram="ridge-distance"[^>]*>.*?<\/svg>tercer rotulo<\/span>:/);
  });

  it("la nota de EMMA va aparte, despues de las citas, y el entorno de radiacion lleva el sol de RIDGE", () => {
    const html = render(
      profile({
        aspects: [
          aspect({
            key: "radiation_environment",
            label: "rotulo de radiacion",
            emma_note: "nota de EMMA segun el backend",
          }),
        ],
      }),
    );
    expect(html).toMatch(/<svg [^>]*data-pictogram="ridge-radiation"[^>]*>.*?<\/svg>rotulo de radiacion<\/span>:/);
    expect(html).toContain('<br/><span class="secondary">nota de EMMA segun el backend</span>');
    expect(html.indexOf("A literal sentence read on the page.")).toBeLessThan(
      html.indexOf("nota de EMMA segun el backend"),
    );
    // Sin nota, no se pinta nada de mas.
    expect(render(profile())).not.toContain("nota de EMMA");
  });

  it("la capacidad medica dice para que se leyo primero cada frase, con los sitios del backend", () => {
    const html = render(
      profile({
        aspects: [
          aspect({
            key: "medical_capability",
            reused_from: ["sitio uno segun el backend", "sitio dos segun el backend"],
          }),
        ],
      }),
    );
    expect(html).toContain(
      '<br/><span class="secondary">Leída antes para: sitio uno segun el backend · sitio dos segun el backend</span>',
    );
    // Un aspecto de lectura propia no lo lleva.
    expect(render(profile())).not.toContain("Leída antes para");
  });

  it("cada pagina lleva sus dias de lectura, no una fecha comun para todas", () => {
    const one = /Pagina leida sin cita<\/a> \(<span><span class="num">([^<]+)<\/span><\/span>\)/;
    const two =
      /Pagina de prueba<\/a> \(<span><span class="num">([^<]+)<\/span><\/span><span> y <span class="num">([^<]+)<\/span><\/span>\)/;
    const html = render(profile());
    expect(html).toMatch(one);
    expect(html).toMatch(two);
    expect(html.match(two)?.slice(1)).toEqual(["2026-10-13", "2026-10-21"].map(formatSourceDate));
    const three = render(
      profile({
        pages_read: [{ title: "P", url: null, read_on: ["2026-10-01", "2026-10-13", "2026-10-21"] }],
      }),
    );
    expect(three).toContain("<span>, <span");
    expect(three).toContain("<span> y <span");
  });

  it("el desajuste con las efemerides se ve sin abrir nada, con el triangulo en amarillo", () => {
    const html = render(
      profile({ ephemeris: { state: "mismatch", target_body: "000", text: "frase: no casan" } }),
    );
    expect(html).toMatch(
      /<p><span class="mark c-yellow"><svg [^>]*data-pictogram="shape-triangle"[^>]*>.*?<\/svg>frase: no casan<\/span><\/p>/,
    );
    expect(html.indexOf("frase: no casan")).toBeLessThan(html.indexOf("<details"));
    // Si casan, la frase va en secundario y sin señal.
    expect(render(profile())).toContain('<p class="secondary"><span class="mark">frase del backend: casa</span></p>');
  });

  it("un perfil que el backend no reconoce se dice como dato ausente y no enseña ningun aspecto", () => {
    const html = render(
      profile({
        id: "perfil-nuevo",
        known: false,
        unknown_text: "frase del backend: perfil no reconocido",
        ephemeris: null,
        aspects: [],
      }),
    );
    expect(html).toMatch(
      /<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>frase del backend: perfil no reconocido<\/span>/,
    );
    // Su nombre lleva el dibujo de «desconocido», no el de otro perfil.
    expect(html).toContain(`data-pictogram="${UNKNOWN_MARK.pictogram}"`);
    expect(html).not.toContain("<details");
  });

  it("el panel y su logica no redactan nada de lo que dice un perfil", () => {
    for (const file of ["./MissionProfileView.tsx", "./missionProfile.ts", "./missionPictograms.ts"]) {
      const source = readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf-8")
        // Las claves de la API de los perfiles no son vocabulario: se quitan tal cual, entre
        // comillas, y el resto se sigue buscando como subcadena («lunar» o «marciano» caen).
        .replace(/"(leo|cislunar|lunar-surface|mars-transit|mars-surface)"/g, '"<perfil>"');
      // Ni cifras de un perfil ni su vocabulario: eso solo puede venir del backend.
      expect(source).not.toMatch(/minutos|microgravedad|ingravidez|sexto|tercio|Marte|Luna|millas/i);
      expect(source).not.toMatch(/\d+\s*(min|d[ií]as|meses|años)/i);
    }
  });
});

const conjunction = (over: Partial<SolarConjunction> = {}): SolarConjunction => ({
  label: "rotulo de la conjuncion del backend",
  state: "within",
  epoch: "2028-03-20",
  target_body: "000",
  elongation_deg: 0.8531,
  elongation_flag: "/T",
  threshold_deg: 2,
  text: "frase del backend sobre la conjuncion",
  note: "nota del backend: solo se dice",
  citations: [citation({ quote: "A sentence about the conjunction.", title: "Pagina de la conjuncion" })],
  ...over,
});

describe("perfil de mision: conjuncion solar", () => {
  it("dentro del umbral es una precaucion; fuera, sin señal; sin dato o sin umbral, dato ausente", () => {
    expect(conjunctionStyle("within")).toEqual(mark("shape-triangle", "yellow"));
    expect(conjunctionStyle("clear")).toEqual(mark(null, null));
    for (const state of ["no_threshold", "not_recorded", "no_ephemeris"]) {
      expect(conjunctionStyle(state), state).toEqual(mark("ring-dotted", "cyan"));
    }
    expect(() => conjunctionStyle("eclipse")).toThrow(RangeError);
  });

  it("su dibujo es suyo: ni el de un perfil ni el de un aspecto", () => {
    const others = [
      ...["leo", "cislunar", "lunar-surface", "mars-transit", "mars-surface"].map(profilePictogram),
      ...["comm_delay", "gravity_regime", "return_or_evacuation", "resupply", "typical_duration", "distance", "radiation_environment", "surface_dust", "day_night_cycle", "medical_capability"].map(aspectPictogram),
    ];
    expect(others).not.toContain(conjunctionPictogram());
    expect(conjunctionPictogram()).not.toBe(UNKNOWN_MARK.pictogram);
  });

  it("enseña la frase y la nota del backend a la vista, con su dibujo y su triangulo, y pliega las citas", () => {
    const html = render(profile({ aspects: [], solar_conjunction: conjunction() }));
    expect(html).toMatch(
      /<strong><span class="mark"><svg [^>]*data-pictogram="dot-sun-dot"[^>]*>.*?<\/svg>rotulo de la conjuncion del backend<\/span>:<\/strong>/,
    );
    expect(html).toMatch(
      /<span class="mark c-yellow"><svg [^>]*data-pictogram="shape-triangle"[^>]*>.*?<\/svg>frase del backend sobre la conjuncion<\/span>/,
    );
    expect(html.indexOf("nota del backend: solo se dice")).toBeLessThan(html.indexOf("<details"));
    expect(html.indexOf("<details")).toBeLessThan(html.indexOf("A sentence about the conjunction."));
    expect(html).toContain("Pagina de la conjuncion");
  });

  it("fuera del umbral va en secundario y sin señal; sin efemerides, en cian con su anillo", () => {
    const clear = render(profile({ solar_conjunction: conjunction({ state: "clear", text: "frase: fuera" }) }));
    expect(clear).toMatch(/<p class="secondary"><strong>.*?<span class="mark">frase: fuera<\/span><\/p>/);
    const missing = render(
      profile({ solar_conjunction: conjunction({ state: "no_ephemeris", text: "frase: sin efemerides", elongation_deg: null }) }),
    );
    expect(missing).toMatch(
      /<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>frase: sin efemerides<\/span>/,
    );
  });

  it("un backend sin el bloque no pinta nada de la conjuncion", () => {
    expect(render(profile())).not.toContain("dot-sun-dot");
    expect(render(profile({ solar_conjunction: null }))).not.toContain("dot-sun-dot");
  });
});

const coverage = (over: Partial<EphemerisCoverage> = {}): EphemerisCoverage => ({
  state: "partial",
  target: "000",
  observer: "399",
  start: "2026-11-01",
  end: "2026-11-10",
  days: 10,
  covered_days: 7,
  missing_days: 3,
  covered: [
    { start: "2026-11-01", end: "2026-11-05", days: 5 },
    { start: "2026-11-09", end: "2026-11-10", days: 2 },
  ],
  missing: [{ start: "2026-11-06", end: "2026-11-08", days: 3 }],
  day: { date: "2026-11-07", in_mission: true, covered: false },
  text: "frase del backend sobre la cobertura",
  how_to_preload: "frase del backend sobre como precargar",
  note: "nota del backend: la cobertura no decide nada",
  citations: [citation({ quote: "specifies ephemeris start time", title: "Pagina de la precarga" })],
  ...over,
});

const renderCoverage = (value: EphemerisCoverage) =>
  renderToStaticMarkup(createElement(EphemerisCoverageView, { coverage: value }));

describe("perfil de mision: cobertura de efemerides (§5.37.18)", () => {
  it("completa, sin señal; si falta algun dia, dato ausente en cian; un estado desconocido falla", () => {
    expect(coverageStyle("complete")).toEqual(mark(null, null));
    expect(coverageStyle("partial")).toEqual(mark("ring-dotted", "cyan"));
    expect(coverageStyle("none")).toEqual(mark("ring-dotted", "cyan"));
    expect(() => coverageStyle("most")).toThrow(RangeError);
    expect(cachedStyle(true)).toEqual(mark(null, null));
    expect(cachedStyle(false)).toEqual(mark("ring-dotted", "cyan"));
  });

  it("enseña a la vista la frase, el dia del estado, como precargar y la nota, tal cual del backend", () => {
    const html = renderCoverage(coverage());
    expect(html).toMatch(
      /<p><strong><span class="mark"><svg [^>]*data-pictogram="calendar"[^>]*>.*?<\/svg>Efemérides en caché<\/span>:<\/strong> <span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>frase del backend sobre la cobertura<\/span><\/p>/,
    );
    const firstFold = html.indexOf("<details");
    for (const text of [
      "frase del backend sobre la cobertura",
      "frase del backend sobre como precargar",
      "nota del backend: la cobertura no decide nada",
    ]) {
      expect(html.indexOf(text), text).toBeGreaterThan(-1);
      expect(html.indexOf(text), text).toBeLessThan(firstFold);
    }
    // El dia que enseña el estado, sin su efemeride: su fecha y el mismo dato ausente, en cian.
    expect(html).toMatch(
      /<span class="num">2026-11-07<\/span> · <span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>sin efemérides en caché<\/span>/,
    );
    expect(html).not.toContain("fuera de los días de la misión");
  });

  it("pliega los tramos en orden, los ausentes en cian, con sus fechas y su cuenta", () => {
    const html = renderCoverage(coverage());
    const tramos = html.slice(html.indexOf("Tramos de días en caché y sin ella"));
    const first = tramos.indexOf("2026-11-01");
    const gap = tramos.indexOf("2026-11-06");
    const last = tramos.indexOf("2026-11-09");
    expect(first).toBeGreaterThan(-1);
    expect(first).toBeLessThan(gap);
    expect(gap).toBeLessThan(last);
    expect(tramos).toMatch(
      /<li><span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>sin efemérides<\/span>: <span class="num">2026-11-06<\/span> a <span class="num">2026-11-08<\/span> \(<span class="num">3<\/span> días\)<\/li>/,
    );
    expect(tramos).toContain('<li><span class="mark">en caché</span>: <span class="num">2026-11-01</span>');
    // Las citas, plegadas aparte, con su pagina.
    expect(html).toContain("specifies ephemeris start time");
    expect(html).toContain("Pagina de la precarga");
  });

  it("completa: la frase en secundario y sin señal, sin como precargar; un dia suelto, sin «a»", () => {
    const html = renderCoverage(
      coverage({
        state: "complete",
        covered_days: 1,
        missing_days: 0,
        days: 1,
        covered: [{ start: "2026-11-01", end: "2026-11-01", days: 1 }],
        missing: [],
        day: { date: "2026-12-01", in_mission: false, covered: true },
        how_to_preload: null,
      }),
    );
    expect(html).toMatch(/<p class="secondary"><strong>.*?<span class="mark">frase del backend sobre la cobertura<\/span><\/p>/);
    expect(html).not.toContain("c-cyan");
    expect(html).not.toContain("frase del backend sobre como precargar");
    expect(html).toContain("fuera de los días de la misión");
    expect(html).toContain('<span class="num">2026-11-01</span> (<span class="num">1</span> día)');
  });

  it("el perfil no la pinta: va aparte, en la linea temporal", () => {
    expect(render(profile())).not.toContain("Efemérides en caché");
  });
});
