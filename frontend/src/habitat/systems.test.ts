import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { HabitatSystemStatus, HabitatSystems } from "../lib/api";
import { UNKNOWN_MARK } from "../lib/marks";
import { TEXT_TOKENS } from "../lib/palette";
import {
  EMPTY_FORM,
  canDeclare,
  declarableStates,
  declarationBody,
  declarationInstant,
  declaredLinkNotice,
  stateMark,
  stateTally,
  systemRows,
} from "./systems";

/** Las claves de estado del vocabulario del backend (`data/habitat_systems.json`). */
const vocabulary = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../backend/app/data/habitat_systems.json", import.meta.url)),
    "utf-8",
  ),
) as { default_state: string; states: { key: string; declarable: boolean }[] };
const STATES = vocabulary.states.map((state) => state.key);

const status = (over: Partial<HabitatSystemStatus>): HabitatSystemStatus => ({
  module: null,
  module_display: "sistema entero",
  state: "undeclared",
  state_display: "sin declarar",
  declared: false,
  since: null,
  last_declared_at: null,
  declarations: 0,
  note: null,
  declared_by: null,
  ledger_index: null,
  recorded: null,
  ...over,
});

describe("el enlace con Tierra declarado (§5.34.5)", () => {
  const link = (over: Partial<{ state: string; attention: boolean; headline: string | null; sentence: string }>) => ({
    state: "out-of-service",
    attention: true,
    headline: "H",
    sentence: "S",
    ...over,
  });

  it("solo hay aviso si el backend pide señalarlo, y con sus frases tal cual", () => {
    expect(declaredLinkNotice(undefined)).toBeNull();
    expect(declaredLinkNotice(link({ state: "undeclared", attention: false, headline: null }))).toBeNull();
    expect(declaredLinkNotice(link({ state: "nominal", attention: false, headline: null }))).toBeNull();
    // Sin frase corta no se inventa una.
    expect(declaredLinkNotice(link({ headline: null }))).toBeNull();
    const notice = declaredLinkNotice(link({}));
    expect(notice?.headline).toBe("H");
    expect(notice?.sentence).toBe("S");
  });

  it("lleva la marca de su estado en el panel de sistemas: un concepto, un dibujo", () => {
    expect(declaredLinkNotice(link({ state: "out-of-service" }))?.mark).toEqual(stateMark("out-of-service"));
    expect(declaredLinkNotice(link({ state: "degraded" }))?.mark).toEqual(stateMark("degraded"));
    expect(declaredLinkNotice(link({ state: "degraded" }))?.mark.color).toBe("yellow");
    // Un estado que esta versión no conoce se señala igual, sin significado propio.
    expect(declaredLinkNotice(link({ state: "intermittent" }))?.mark).toEqual(UNKNOWN_MARK);
  });
});

describe("la marca de un estado declarado", () => {
  it("cada estado del vocabulario del backend tiene marca propia: pictograma y token de texto", () => {
    expect(STATES.length).toBeGreaterThan(1);
    for (const state of STATES) {
      const mark = stateMark(state);
      expect(mark.pictogram).not.toBeNull();
      expect(mark.pictogram).not.toBe(stateMark("un-estado-que-no-existe").pictogram);
      expect(TEXT_TOKENS).toContain(mark.color);
      expect(mark.className).toBe(`c-${mark.color}`);
    }
  });

  it("los pictogramas distinguen los estados sin el color, con el dibujo del glifo que habia", () => {
    const pictograms = STATES.map((state) => stateMark(state).pictogram);
    expect(new Set(pictograms).size).toBe(STATES.length);
    // ✓ △ ⊘ ◌ : funciona, degradado, fuera de servicio, sin declarar.
    expect(stateMark("nominal").pictogram).toBe("check");
    expect(stateMark("degraded").pictogram).toBe("shape-triangle");
    expect(stateMark("out-of-service").pictogram).toBe("slash-circle");
    expect(stateMark("undeclared").pictogram).toBe("ring-dotted");
  });

  it("sin declarar es un dato ausente (cian), y ningun otro estado se pinta asi", () => {
    // Tabla F.5-1: cian es "missing or stale data". Un sistema del que nadie ha dicho nada no
    // se puede pintar como el que funciona.
    const absent = stateMark(vocabulary.default_state);
    expect(absent.color).toBe("cyan");
    for (const state of STATES.filter((key) => key !== vocabulary.default_state)) {
      expect(stateMark(state).color).not.toBe("cyan");
      expect(stateMark(state).pictogram).not.toBe(absent.pictogram);
    }
  });

  it("no usa el rojo ni el gris: una declaracion no es una alerta ni un «no disponible»", () => {
    for (const state of STATES) {
      expect(["red", "gray"]).not.toContain(stateMark(state).color);
    }
  });

  it("lo que no funciona como se espera pide atencion; lo que funciona no lleva color", () => {
    expect(stateMark("degraded").color).toBe("yellow");
    expect(stateMark("out-of-service").color).toBe("yellow");
    expect(stateMark(STATES[0] as string).color).toBe("text");
  });

  it("un estado desconocido se pinta sin significado en vez de fallar", () => {
    const mark = stateMark("en-pruebas");
    expect(mark).toEqual(UNKNOWN_MARK);
    expect(mark.color).toBe("text");
    expect(mark.className).toBe("c-text");
  });
});

describe("las filas del panel", () => {
  const overview: Pick<HabitatSystems, "systems"> = {
    systems: [
      {
        key: "air-revitalization",
        display: "Revitalización de aire",
        description: "",
        parameters: [],
        statuses: [
          status({ state: "degraded", state_display: "degradado", declared: true }),
          status({
            module: "laboratorio",
            module_display: "Laboratorio",
            state: "out-of-service",
            state_display: "fuera de servicio",
            declared: true,
          }),
        ],
      },
      { key: "power", display: "Energía", description: "", parameters: [], statuses: [status({})] },
    ],
  };

  it("una fila por estado vigente, con el modulo solo cuando la declaracion habla de uno", () => {
    const rows = systemRows(overview);
    expect(rows.map((row) => [row.key, row.where])).toEqual([
      ["air-revitalization:", null],
      ["air-revitalization:laboratorio", { key: "laboratorio", display: "Laboratorio" }],
      ["power:", null],
    ]);
    expect(new Set(rows.map((row) => row.key)).size).toBe(rows.length);
  });

  it("un sistema sin declarar sale, y sale como dato ausente", () => {
    const [, , power] = systemRows(overview);
    expect(power?.status.declared).toBe(false);
    expect(power?.mark).toEqual(stateMark("undeclared"));
    expect(power?.mark.color).toBe("cyan");
  });

  it("las píldoras del tablero cuentan filas por estado, con la palabra y la marca de su fila", () => {
    const tally = stateTally([...systemRows(overview), ...systemRows(overview)]);
    expect(tally.map((entry) => [entry.display, entry.count])).toEqual([
      ["degradado", 2],
      ["fuera de servicio", 2],
      ["sin declarar", 2],
    ]);
    expect(tally[2]?.mark.color).toBe("cyan");
    expect(stateTally([])).toEqual([]);
  });
});

describe("declarar un estado", () => {
  const states = vocabulary.states.map((state) => ({
    ...state,
    display: state.key,
    description: "",
  }));

  it("solo se ofrecen los estados que se pueden firmar: sin declarar no es uno", () => {
    const offered = declarableStates({ states }).map((state) => state.key);
    expect(offered).not.toContain(vocabulary.default_state);
    expect(offered.length).toBe(STATES.length - 1);
  });

  it("hace falta sistema, estado y el nombre de quien declara; la nota es opcional", () => {
    const filled = { ...EMPTY_FORM, system: "power", state: "degraded" };
    expect(canDeclare(filled, "CDR")).toBe(true);
    expect(canDeclare(filled, "  ")).toBe(false);
    expect(canDeclare(filled, undefined)).toBe(false);
    expect(canDeclare({ ...filled, system: "" }, "CDR")).toBe(false);
    expect(canDeclare({ ...filled, state: "" }, "CDR")).toBe(false);
    expect(canDeclare(EMPTY_FORM, "CDR")).toBe(false);
  });

  it("el modulo solo viaja si se eligio uno, y la nota y el nombre van sin espacios", () => {
    const at = "2026-11-08T12:00:00+00:00";
    const form = { system: "power", state: "degraded", module: "", note: "  bus B  " };
    expect(declarationBody(form, " CDR ", at)).toEqual({
      system: "power",
      state: "degraded",
      at,
      note: "bus B",
      declared_by: "CDR",
    });
    expect(declarationBody({ ...form, module: "esclusa" }, "CDR", at).module).toBe("esclusa");
  });

  it("el instante es el de los datos si lo hay; si no, el reloj", () => {
    const now = new Date("2026-10-10T08:00:00.000Z");
    expect(declarationInstant("2026-11-08T12:00:00+00:00", now)).toBe("2026-11-08T12:00:00+00:00");
    expect(declarationInstant(null, now)).toBe("2026-10-10T08:00:00.000Z");
  });
});
