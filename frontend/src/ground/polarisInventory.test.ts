// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import type { PolarisTool } from "../lib/api";
import { LEVELS, LEVEL_ORDER } from "../lib/levels";
import { OBSERVATION_TYPES } from "../lib/provenance";
import {
  POLARIS_FILTERS,
  changeDate,
  countByFilter,
  filterTools,
  loadStyle,
  shortCommit,
  useStyle,
} from "./polarisInventory";

// Como los escribe el backend (`app/api/polaris.py`): la consola no los redacta.
const STATE = { true: "carga", false: "no carga", null: "no se importa" } as const;
const REASON = {
  true: null,
  false: "ModuleNotFoundError: No module named 'pwd'",
  null: "al importarse lanza git para preguntar por la rama de la carpeta que contiene la copia",
} as const;

const tool = (herramienta: string, carga: boolean | null, en_uso: boolean): PolarisTool => ({
  herramienta,
  carga,
  estado: STATE[`${carga}`],
  motivo: REASON[`${carga}`],
  en_uso,
  ficha: null,
});

const TOOLS = [
  tool("borde", true, true),
  tool("visor3d", true, true),
  tool("laminillas_jaulas", false, false),
  tool("_casa", true, false),
  tool("rodaje_muro", null, false),
];

describe("la copia de Polaris en la consola de Tierra", () => {
  it("cada filtro deja ver solo lo suyo y los recuentos cuadran con la lista", () => {
    const names = (filter: Parameters<typeof filterTools>[1]) =>
      filterTools(TOOLS, filter).map((item) => item.herramienta);
    expect(names("all")).toHaveLength(TOOLS.length);
    expect(names("loads")).toEqual(["borde", "visor3d", "_casa"]);
    expect(names("fails")).toEqual(["laminillas_jaulas"]);
    expect(names("skipped")).toEqual(["rodaje_muro"]);
    expect(names("used")).toEqual(["borde", "visor3d"]);
    expect(names("unused")).toEqual(["laminillas_jaulas", "_casa", "rodaje_muro"]);

    const counts = countByFilter(TOOLS);
    for (const { id } of POLARIS_FILTERS) expect(counts[id]).toBe(names(id).length);
    expect(counts.loads + counts.fails + counts.skipped).toBe(counts.all);
    expect(counts.used + counts.unused).toBe(counts.all);
  });

  it("lo que el inventario no importa no se cuenta ni como que carga ni como que no carga", () => {
    const names = (filter: Parameters<typeof filterTools>[1]) =>
      filterTools(TOOLS, filter).map((item) => item.herramienta);
    expect(names("loads")).not.toContain("rodaje_muro");
    expect(names("fails")).not.toContain("rodaje_muro");

    const skipped = loadStyle(TOOLS[4]!);
    const failing = loadStyle(TOOLS[2]!);
    // Gris ("no disponible"), nunca cian ("dato ausente"), y distinguible del fallo sin el color.
    expect(skipped.pictogram).toBe("slash-circle");
    expect(skipped.color).toBe("gray");
    expect(skipped.pictogram).not.toBe(failing.pictogram);
    expect(skipped.pictogram).not.toBe(loadStyle(TOOLS[0]!).pictogram);
    expect(skipped.word).toBe("no se importa");
  });

  it("la palabra del estado es la que da el backend, no una redactada aqui", () => {
    for (const item of TOOLS) expect(loadStyle(item).word).toBe(item.estado);
    expect(loadStyle({ ...TOOLS[4]!, estado: "texto del backend" }).word).toBe("texto del backend");
  });

  it("que una herramienta cargue no la cuenta como usada por EMMA", () => {
    expect(filterTools(TOOLS, "used").map((item) => item.herramienta)).not.toContain("_casa");
  });

  it("la busqueda por nombre se suma al filtro y no distingue mayusculas", () => {
    expect(filterTools(TOOLS, "all", " VISOR ").map((item) => item.herramienta)).toEqual(["visor3d"]);
    expect(filterTools(TOOLS, "fails", "visor")).toEqual([]);
  });

  it("no carga es 'no disponible' (gris), no 'dato ausente' (cian), y lleva pictograma y palabra", () => {
    const failing = loadStyle(TOOLS[2]!);
    expect(failing.color).toBe("gray");
    expect(failing.word).toBe("no carga");
    const loading = loadStyle(TOOLS[0]!);
    expect(loading.color).toBeNull();
    expect(loading.pictogram).toBe("check");
    expect(failing.pictogram).toBe("cross");
  });

  it("en uso y copiada sin uso se distinguen por pictograma y palabra, sin color de alerta", () => {
    const used = useStyle(TOOLS[0]!);
    const unused = useStyle(TOOLS[3]!);
    expect(used.color).toBeNull();
    expect(unused.color).toBeNull();
    expect(used.pictogram).not.toBe(unused.pictogram);
    expect(used.word).not.toBe(unused.word);
  });

  it("ningun estado de herramienta lleva la forma de un nivel de riesgo ni la de medido o inferido", () => {
    const reserved = [
      ...LEVEL_ORDER.map((level) => LEVELS[level].pictogram),
      ...Object.values(OBSERVATION_TYPES).map((type) => type.pictogram),
    ];
    for (const item of TOOLS) {
      expect(reserved).not.toContain(loadStyle(item).pictogram);
      expect(reserved).not.toContain(useStyle(item).pictogram);
    }
  });

  it("el commit se acorta como en git y su ausencia no se disimula", () => {
    expect(shortCommit("849989f348b0d63d2ff69e05fcb73b1655142468")).toBe("849989f");
    expect(shortCommit(null)).toBeNull();
    expect(shortCommit("")).toBeNull();
  });

  it("una fecha de cambio que no es ISO no se enseña ni rompe el panel", () => {
    const change = { ruta: "tools/x", motivo: "m", reemplazos: 1 };
    expect(changeDate({ ...change, fecha: "2026-09-29" })).toBe("2026-09-29");
    expect(changeDate({ ...change, fecha: "29/09/2026" })).toBeNull();
    expect(changeDate({ ...change, fecha: null })).toBeNull();
  });
});
