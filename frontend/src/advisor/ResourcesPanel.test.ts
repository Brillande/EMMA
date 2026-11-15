import { describe, expect, it } from "vitest";

import type { ResourcesOverview } from "../lib/api";
import { stateMark } from "./resources";
import { stateTally } from "./ResourcesPanel";

/*
 * Las píldoras del tablero: cuántos recursos hay en cada estado, con la palabra del backend y la
 * marca de `resources.ts`. Solo los estados presentes; lo declarado no disponible primero y lo sin
 * declarar al final, como las filas del panel.
 */
type Resource = ResourcesOverview["resources"][number];

const resource = (key: string, state: Resource["state"], display: string): Resource => ({
  key,
  name: `NOMBRE-${key}`,
  state,
  state_display: display,
  since: null,
  note: null,
  declared_by: null,
  ledger_index: null,
  recorded: null,
  declarations: 0,
  used_by: [],
});

describe("stateTally", () => {
  it("cuenta por estado, en el orden de las filas, con la palabra y la marca de cada uno", () => {
    const tally = stateTally({
      resources: [
        resource("a", "undeclared", "PALABRA-SIN-DECLARAR"),
        resource("b", "available", "PALABRA-DISPONIBLE"),
        resource("c", "unavailable", "PALABRA-NO-DISPONIBLE"),
        resource("d", "undeclared", "PALABRA-SIN-DECLARAR"),
      ],
    });
    expect(tally.map((entry) => [entry.state, entry.display, entry.count])).toEqual([
      ["unavailable", "PALABRA-NO-DISPONIBLE", 1],
      ["available", "PALABRA-DISPONIBLE", 1],
      ["undeclared", "PALABRA-SIN-DECLARAR", 2],
    ]);
    expect(tally[2]?.mark).toEqual(stateMark("undeclared"));
  });

  it("sin recursos no hay píldoras", () => {
    expect(stateTally({ resources: [] })).toEqual([]);
  });
});
