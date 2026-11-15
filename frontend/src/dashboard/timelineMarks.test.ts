import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons";
import { UNAVAILABLE_MARK, UNKNOWN_MARK } from "../lib/marks";
import {
  DEPENDS_MODE_MARKS,
  EVENT_KIND_MARKS,
  INCONGRUENCE_MARK,
  ROUTINE_MARKS,
  SEVERITY_MARKS,
  STAGE_MARKS,
  asOfMark,
  dependsModeMark,
  eventKindMark,
  routineMark,
  stageMark,
} from "./timelineMarks";

/**
 * Cada tipo de hecho y cada etapa que escribe `app/timeline.py` tiene su pictograma, y se leen
 * del propio fichero de Python: si el backend gana un tipo, esta prueba lo dice antes de que la
 * cronica lo pinte con el dibujo de «desconocido».
 */

const TIMELINE_PATH = fileURLToPath(new URL("../../../backend/app/timeline.py", import.meta.url));
const source = readFileSync(TIMELINE_PATH, "utf8");

/**
 * El `kind` de cada llamada a `_event(mission, at, kind, ...)` y `_signed(mission, until, item,
 * field, kind, ...)`. Se cuentan las llamadas y las capturas: una llamada cuyo `kind` no se deje
 * leer (un `at` con comas, un literal que no sea una cadena) hace fallar la prueba en vez de
 * perderse en silencio y dejar que la cronica pinte ese tipo como «desconocido».
 */
function eventKinds(): string[] {
  const kinds: string[] = [];
  for (const match of source.matchAll(/_event\(\s*mission,\s*[^,]+,\s*"([a-z0-9-]+)"/g)) kinds.push(match[1] ?? "");
  for (const match of source.matchAll(/_signed\(\s*mission,\s*until,\s*item,\s*[^,]+,\s*"([a-z0-9-]+)"/g)) {
    kinds.push(match[1] ?? "");
  }
  const calls = (source.match(/\b_(?:event|signed)\(\s*mission,/g) ?? []).length;
  // `_signed` delega en `_event(mission, at, kind, ...)` con el `kind` que le llego: no es un tipo.
  const delegated = (source.match(/_event\(\s*mission,\s*at,\s*kind,/g) ?? []).length;
  if (calls - delegated !== kinds.length) {
    throw new Error(`timeline.py: ${calls - delegated} llamadas a _event/_signed, ${kinds.length} tipos leidos`);
  }
  return [...new Set(kinds)].sort();
}

/** Las claves de `STAGES`. */
function stageKeys(): string[] {
  const block = /STAGES[^=]*=\s*\(([\s\S]*?)\n\)/.exec(source);
  if (block === null || block[1] === undefined) throw new Error("no se encuentra STAGES en timeline.py");
  return [...block[1].matchAll(/\(\s*"([a-z-]+)",/g)].map((match) => match[1] ?? "");
}

const distinct = (marks: Iterable<{ pictogram: string | null }>) => {
  const drawn = [...marks].map((look) => look.pictogram).filter((name) => name !== null);
  expect(new Set(drawn).size).toBe(drawn.length);
};

describe("los tipos de hecho de la cronica (app/timeline.py)", () => {
  it("se leen del fichero, no de una lista vacia", () => {
    const kinds = eventKinds();
    expect(kinds.length).toBeGreaterThanOrEqual(10);
    expect(kinds).toContain("alerta");
    expect(kinds).toContain("sistema");
    expect(stageKeys()).toEqual(["career", "preflight", "mission-day", "intervention", "followup", "postflight", "unplaced"]);
  });

  it("cada tipo tiene su pictograma, sin color, y la tabla no tiene tipos de mas", () => {
    const kinds = eventKinds();
    for (const kind of kinds) {
      const look = eventKindMark(kind);
      expect(look, kind).not.toBe(UNKNOWN_MARK);
      expect(look.pictogram, kind).not.toBeNull();
      expect(look.color, kind).toBeNull();
    }
    expect(Object.keys(EVENT_KIND_MARKS).sort()).toEqual(kinds);
  });

  it("cada etapa de §10 tiene su pictograma, y la tabla no tiene etapas de mas", () => {
    const keys = stageKeys();
    for (const key of keys) {
      expect(stageMark(key), key).not.toBe(UNKNOWN_MARK);
      expect(stageMark(key).pictogram, key).not.toBeNull();
    }
    expect(Object.keys(STAGE_MARKS).sort()).toEqual([...keys].sort());
  });

  it("todo pictograma de las tablas existe y, dentro de cada tabla, dos claves no comparten dibujo", () => {
    for (const table of [EVENT_KIND_MARKS, STAGE_MARKS, ROUTINE_MARKS, DEPENDS_MODE_MARKS, SEVERITY_MARKS]) {
      for (const [key, look] of Object.entries(table)) {
        if (look.pictogram !== null) expect(isPictogramName(look.pictogram), key).toBe(true);
      }
    }
    distinct(Object.values(EVENT_KIND_MARKS));
    distinct(Object.values(STAGE_MARKS));
    distinct(Object.values(ROUTINE_MARKS));
    distinct(Object.values(DEPENDS_MODE_MARKS));
    // Un tipo de hecho y una etapa nunca llevan el mismo dibujo: se ven juntos en la cronica.
    distinct([...Object.values(EVENT_KIND_MARKS), ...Object.values(STAGE_MARKS)]);
  });

  it("una clave que la interfaz no conoce se enseña como desconocida, sin tumbar la cronica", () => {
    expect(eventKindMark("meteorito")).toBe(UNKNOWN_MARK);
    expect(stageMark("limbo")).toBe(UNKNOWN_MARK);
    expect(routineMark("rara")).toBe(UNKNOWN_MARK);
    expect(dependsModeMark("robot")).toBe(UNKNOWN_MARK);
    // Las propiedades heredadas de Object no son claves.
    expect(eventKindMark("toString")).toBe(UNKNOWN_MARK);
  });
});

describe("las señales con color son las de la tabla F.5-1, con su forma de siempre", () => {
  it("limite normativo: triangulo amarillo; confort y objetivo: rombo azul", () => {
    expect(SEVERITY_MARKS.health).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
    expect(SEVERITY_MARKS.performance).toEqual({ pictogram: "shape-diamond", color: "blue", className: "c-blue" });
    expect(SEVERITY_MARKS.target).toEqual(SEVERITY_MARKS.performance);
  });

  it("medidas periodicas: a su ritmo sin señal, atrasada sin color, rota en amarillo, nunca en gris", () => {
    expect(routineMark("al-dia")).toEqual({ pictogram: null, color: null, className: undefined });
    expect(routineMark("atrasada")).toEqual({ pictogram: "hourglass", color: null, className: undefined });
    expect(routineMark("rota")).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
    // «No disponible» es una sola marca en toda la interfaz (`lib/marks.ts`), no un anillo en gris.
    expect(routineMark("nunca-corrio")).toBe(UNAVAILABLE_MARK);
    expect(routineMark("nunca-corrio")).toEqual({ pictogram: "slash-circle", color: "gray", className: "c-gray" });
  });

  it("el ahora que no sale de los datos es dato ausente: anillo punteado en cian", () => {
    expect(asOfMark("data")).toEqual({ pictogram: null, color: null, className: undefined });
    for (const source of ["cut", "clock"] as const) {
      expect(asOfMark(source)).toEqual({ pictogram: "ring-dotted", color: "cyan", className: "c-cyan" });
    }
  });

  it("quien se ocupa: chip para el sistema, persona para una persona; lo que no cuadra, triangulo amarillo", () => {
    expect(dependsModeMark("auto").pictogram).toBe("chip");
    expect(dependsModeMark("humano").pictogram).toBe("person");
    expect(INCONGRUENCE_MARK).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
  });
});
