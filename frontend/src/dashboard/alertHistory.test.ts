import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons";
import type { AlertHistoryEpisode } from "../lib/api";
import { LEVELS } from "../lib/levels";
import {
  RECOMPUTED_PICTOGRAM,
  closedCount,
  episodeRows,
  eventMark,
  historyNotes,
} from "./alertHistory";

function episode(over: Partial<AlertHistoryEpisode>): AlertHistoryEpisode {
  return {
    id: "recomputed:behavioral:2026-11-10T23:00:00+00:00",
    domain: "behavioral",
    domain_display: "conductual",
    peak_level: "watch",
    peak_level_display: "palabra del backend",
    first_step_start: "2026-11-10T23:00:00+00:00",
    last_step_end: "2026-11-18T23:00:00+00:00",
    steps: 4,
    open: false,
    state_display: "cerrado",
    start_unknown: false,
    start_note: null,
    levels: [],
    signed: [],
    ...over,
  };
}

describe("la señal de un hecho de la cronica", () => {
  it("lo recalculado nunca lleva la insignia de una alerta activa, aunque traiga nivel", () => {
    expect(eventMark({ recomputed: true, level: "critical", severity: null })).toBe("recomputed");
    expect(eventMark({ recomputed: true, level: null, severity: "health" })).toBe("recomputed");
  });

  it("lo firmado y lo del estado conservan la suya", () => {
    expect(eventMark({ recomputed: false, level: "watch", severity: null })).toBe("level");
    expect(eventMark({ recomputed: false, level: null, severity: "health" })).toBe("health");
    expect(eventMark({ recomputed: false, level: null, severity: "performance" })).toBe(
      "performance",
    );
    expect(eventMark({ recomputed: false, level: null, severity: "target" })).toBe("target");
    expect(eventMark({ recomputed: false, level: null, severity: null })).toBeNull();
  });

  it("el pictograma de lo recalculado existe y no es el de ningun nivel ni el de dato ausente", () => {
    expect(isPictogramName(RECOMPUTED_PICTOGRAM)).toBe(true);
    const levels = Object.values(LEVELS).map((style) => style.pictogram);
    expect([...levels, "ring-dotted", "shape-triangle", "shape-diamond"]).not.toContain(
      RECOMPUTED_PICTOGRAM,
    );
  });
});

describe("los episodios recalculados", () => {
  const old = episode({ id: "a", last_step_end: "2026-11-08T23:00:00+00:00" });
  const recent = episode({ id: "b", last_step_end: "2026-11-18T23:00:00+00:00" });
  const active = episode({
    id: "c",
    domain: "immune",
    last_step_end: "2026-12-10T23:00:00+00:00",
    open: true,
  });

  it("van con lo ultimo arriba y sin tocar la lista que llego", () => {
    const history = { episodes: [old, active, recent] };
    expect(episodeRows(history).map((item) => item.id)).toEqual(["c", "b", "a"]);
    expect(history.episodes.map((item) => item.id)).toEqual(["a", "c", "b"]);
  });

  it("los cerrados se cuentan aparte de los que siguen abiertos", () => {
    expect(closedCount({ episodes: [old, active, recent] })).toBe(2);
    expect(closedCount({ episodes: [] })).toBe(0);
  });
});

describe("lo que se enseña siempre junto a la historia", () => {
  it("primero hasta donde llega, despues lo que es y lo que no es, tal cual", () => {
    expect(historyNotes({ coverage: "hasta aqui", basis: ["es un recalculo", "no se firma"] })).toEqual(
      ["hasta aqui", "es un recalculo", "no se firma"],
    );
  });

  it("sin su rotulo de limites no se pinta", () => {
    expect(historyNotes({ coverage: "", basis: ["es un recalculo"] })).toBeNull();
    expect(historyNotes({ coverage: "hasta aqui", basis: [] })).toBeNull();
    expect(historyNotes({ coverage: "hasta aqui", basis: ["  "] })).toBeNull();
  });
});
