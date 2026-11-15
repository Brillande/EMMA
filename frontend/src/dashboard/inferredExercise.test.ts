import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ExerciseIndicator, ExerciseMeasured, InferredState } from "../lib/api";
import { UNKNOWN_MARK, mark } from "../lib/marks";
import { InferredPanel } from "./InferredPanel";
import {
  bandPictogram,
  indicatorNotes,
  indicatorStyle,
  recordStyle,
  singleContext,
} from "./inferredExercise";

/*
 * El panel de estados inferidos MUESTRA lo medido que acompaña a la banda: cada frase es del
 * backend (`analysis/exercise_summary.py`). Se comprueba pintándolo con un ejemplo y buscando
 * cada frase tal cual, y leyendo su fuente para ver que no redacta ni calcula nada.
 */

const indicator = (over: Partial<ExerciseIndicator> = {}): ExerciseIndicator => ({
  key: "exercise-minutes",
  display: "Resistive exercise duration",
  display_es: "Duración del ejercicio resistivo",
  unit: "min",
  observation_type: "measured",
  evidence_context: { simulated: 168 },
  readings: 168,
  first: "2026-12-03T23:00:00+00:00",
  last: "2026-12-10T23:00:00+00:00",
  latest: 71,
  lowest: 40,
  highest: 110,
  outside_expected: 3,
  baseline: { personal: true, median: 80, samples: 120, statement: "FRASE-BASE" },
  against_baseline: "FRASE-MOTOR",
  trend: "FRASE-TENDENCIA",
  trend_statement: "FRASE-TENDENCIA-COMPLETA",
  statement: "FRASE-INDICADOR",
  ...over,
});

const exercise = (over: Partial<ExerciseMeasured> = {}): ExerciseMeasured => ({
  observation_type: "measured",
  window_days: 7,
  window_start: "2026-12-03T23:00:00+00:00",
  window_end: "2026-12-10T23:00:00+00:00",
  window_basis: "FRASE-VENTANA",
  indicators: [indicator()],
  record: { state: "recorded", display: "hay registro", note: "FRASE-REGISTRO" },
  not_measured_excluded: 0,
  relation: "FRASE-RELACION",
  adherence: null,
  adherence_note: "FRASE-ADHERENCIA",
  ...over,
});

const band = (over: Partial<InferredState> = {}): InferredState => ({
  key: "bone-mineral-density-loss",
  display: "Pérdida de densidad mineral ósea en huesos de carga",
  unit: "%",
  observation_type: "inferred",
  model_version: "m@1",
  now: { mission_day: 40, loss_pct_low: 1.3, loss_pct_high: 2 },
  trajectory: [],
  basis: "FRASE-BANDA",
  source: { title: "t", source: "NASA", url: "https://example.invalid/" },
  evidence_class: "established",
  exercise_note: "NOTA-ANTIGUA",
  ...over,
});

const render = (item: InferredState) =>
  renderToStaticMarkup(createElement(InferredPanel, { inferred: [item] }));

describe("señal de lo que falta", () => {
  it("una semana sin registro va en cian con el anillo punteado; un registro de 0 es un dato", () => {
    expect(recordStyle("no_record")).toEqual(mark("ring-dotted", "cyan"));
    expect(recordStyle("recorded_zero")).toEqual(mark(null, null));
    expect(recordStyle("recorded")).toEqual(mark(null, null));
  });

  it("un estado desconocido no se pinta como registro", () => {
    expect(() => recordStyle("partial")).toThrow(RangeError);
  });

  it("un indicador sin lecturas va en cian con el anillo punteado; con lecturas, el dibujo de su familia", () => {
    expect(indicatorStyle({ key: "exercise-minutes", readings: 0 })).toEqual(mark("ring-dotted", "cyan"));
    expect(indicatorStyle({ key: "exercise-minutes", readings: 1 })).toEqual(mark("dumbbell", null));
    expect(indicatorStyle({ key: "loading-impacts", readings: 3 })).toEqual(mark("dumbbell", null));
    // Un indicador que la interfaz no conoce se enseña con su frase y el dibujo de «desconocido».
    expect(indicatorStyle({ key: "inventado", readings: 2 })).toEqual(mark(UNKNOWN_MARK.pictogram, null));
  });

  it("la banda de densidad mineral osea lleva el hueso del dominio; otra, el dibujo de desconocido", () => {
    expect(bandPictogram("bone-mineral-density-loss")).toBe("domain-bone");
    expect(bandPictogram("otra-banda")).toBe(UNKNOWN_MARK.pictogram);
  });
});

describe("entorno de las lecturas", () => {
  it("uno solo si todas son del mismo", () => {
    expect(singleContext(exercise())).toBe("simulated");
  });

  it("ninguno si no hay lecturas o vienen de varios", () => {
    expect(singleContext(exercise({ indicators: [indicator({ evidence_context: {} })] }))).toBeNull();
    const mixed = [indicator(), indicator({ key: "loading-impacts", evidence_context: { ground: 2 } })];
    expect(singleContext(exercise({ indicators: mixed }))).toBeNull();
  });

  it("un entorno que la interfaz no conoce falla en vez de inventarle nombre", () => {
    const odd = [indicator({ evidence_context: { lunar: 1 } })];
    expect(() => singleContext(exercise({ indicators: odd }))).toThrow();
  });
});

describe("frases de un indicador", () => {
  it("la base y la tendencia, tal cual; sin base, solo la tendencia", () => {
    expect(indicatorNotes(indicator())).toEqual(["FRASE-BASE", "FRASE-TENDENCIA-COMPLETA"]);
    expect(indicatorNotes(indicator({ baseline: null }))).toEqual(["FRASE-TENDENCIA-COMPLETA"]);
  });
});

describe("panel", () => {
  it("pinta lo medido junto a la banda con las frases del backend y los dos rótulos", () => {
    const html = render(band({ exercise: exercise() }));
    for (const text of [
      "FRASE-BANDA",
      "FRASE-RELACION",
      "FRASE-INDICADOR",
      "FRASE-BASE",
      "FRASE-TENDENCIA-COMPLETA",
      "FRASE-REGISTRO",
      "FRASE-ADHERENCIA",
      "FRASE-VENTANA",
    ]) {
      expect(html, text).toContain(text);
    }
    expect(html).toContain("INFERIDO");
    expect(html).toContain("MEDIDO");
    expect(html).toContain("simulado");
    // La nota vieja no se repite: la del registro, con sus tres casos, la sustituye.
    expect(html).not.toContain("NOTA-ANTIGUA");
    // La banda con el hueso junto a su nombre, el indicador con la mancuerna junto a su frase, el
    // entorno con su onda junto a su palabra; todo sin color.
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="domain-bone"[^>]*>.*?<\/svg>Pérdida de densidad/);
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="dumbbell"[^>]*>.*?<\/svg>FRASE-INDICADOR/);
    expect(html).toMatch(/<span class="mark"><svg [^>]*data-pictogram="wave-zigzag"[^>]*>.*?<\/svg>simulado/);
    // Con registro, la nota va con su palabra y sin señal.
    expect(html).toContain('<span class="mark">FRASE-REGISTRO</span>');
  });

  it("sin el bloque medido sigue pintando la banda y su nota", () => {
    const html = render(band());
    expect(html).toContain("NOTA-ANTIGUA");
    expect(html).not.toContain("MEDIDO");
  });

  it("un indicador sin lecturas se marca como dato ausente, con el anillo punteado en cian", () => {
    const none = indicator({ readings: 0, baseline: null, statement: "SIN-LECTURAS" });
    const html = render(
      band({
        exercise: exercise({
          indicators: [none],
          record: { state: "no_record", display: "no hay registro", note: "SIN-REGISTRO" },
        }),
      }),
    );
    expect(html).toMatch(/<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>SIN-LECTURAS/);
    expect(html).toMatch(/<span class="mark c-cyan"><svg [^>]*data-pictogram="ring-dotted"[^>]*>.*?<\/svg>SIN-REGISTRO/);
    // La señal de ausencia ocupa el sitio del dibujo de la familia: no van los dos.
    expect(html).not.toContain('data-pictogram="dumbbell"');
    // Ningun glifo de texto queda: la forma es el pictograma.
    expect(html).not.toContain("◌");
  });

  it("en posvuelo pinta el corte en el día de regreso y la recuperación tal cual, con su fuente", () => {
    const html = render(
      band({
        now: { mission_day: 180, loss_pct_low: 5.9, loss_pct_high: 8.9 },
        cut: {
          phase: "postflight",
          label: "ROTULO-CORTE",
          basis: "FRASE-CORTE",
          recovery: "FRASE-RECUPERACION",
          recovery_source: { title: "OCHMO-MTB-013", source: "NASA OCHMO", url: "https://example.invalid/mtb" },
        },
      }),
    );
    expect(html).toMatch(/ROTULO-CORTE, <span class="num">180<\/span>/);
    expect(html).not.toContain("a día");
    for (const text of ["FRASE-CORTE", "FRASE-RECUPERACION", "NASA OCHMO: OCHMO-MTB-013"]) {
      expect(html, text).toContain(text);
    }
    expect(html).toContain('href="https://example.invalid/mtb"');
    // Sin corte, el día de siempre y ninguna frase de recuperación.
    const flying = render(band());
    expect(flying).toMatch(/a día <span class="num">40<\/span>/);
    expect(flying).not.toContain("FRASE-RECUPERACION");
  });

  it("no redacta ni calcula: ni porcentaje de adherencia ni frases propias sobre el ejercicio", () => {
    const source = readFileSync(fileURLToPath(new URL("./InferredPanel.tsx", import.meta.url)), "utf8");
    expect(source).not.toMatch(/adherencia|pauta|no la modifica|sin registro/i);
    expect(source).not.toMatch(/outside_expected|\.latest|\.lowest|\.highest|\/ *item\.readings/);
  });
});
