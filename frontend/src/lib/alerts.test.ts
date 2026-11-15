import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons";
import {
  ACKNOWLEDGEMENT_MARKS,
  ANNUNCIATION_MARKS,
  RESOLUTION_MARKS,
  acknowledgedIds,
  acknowledgementMark,
  activeAlerts,
  annunciationMark,
  countAlerts,
  earthTimeline,
  resolutionMark,
} from "./alerts";
import type { AlertState, CommsWindow, DomainRisk } from "./api";
import { UNKNOWN_MARK } from "./marks";

const risk = (level: string, drivers: string[] = []): DomainRisk => ({ score: 0, level, drivers });

const state = (id: string): AlertState => ({
  id,
  domain: id.split(":")[0] ?? "",
  level: id.split(":")[1] ?? "",
  acknowledged: false,
  acknowledged_by: null,
  acknowledgement_index: null,
  annunciation: "normal",
  silenced_until: null,
  silenced_by: null,
  silenced_reason: null,
});

const COMMS: CommsWindow = {
  epoch: "2026-11-14",
  distance_au: 1.324,
  one_way_minutes: 11,
  round_trip_minutes: 22,
  autonomy_required: true,
  target: "499",
  description: "",
};

describe("alertas activas", () => {
  it("nominal no es una alerta", () => {
    expect(activeAlerts({ bone: risk("nominal") })).toEqual([]);
  });

  it("lo mas grave primero", () => {
    const alerts = activeAlerts({
      bone: risk("watch"),
      cardiovascular: risk("critical"),
      immune: risk("concern"),
    });
    expect(alerts.map((a) => a.level)).toEqual(["critical", "concern", "watch"]);
  });

  it("un nivel desconocido no se descarta en silencio", () => {
    expect(() => activeAlerts({ bone: risk("grave") })).toThrow(RangeError);
  });

  it("si cambia el nivel, es una alerta nueva (hay que reconocerla otra vez)", () => {
    const [before] = activeAlerts({ bone: risk("watch") });
    const [after] = activeAlerts({ bone: risk("concern") });
    expect(before?.id).not.toBe(after?.id);
  });
});

describe("F.6.4: contadores", () => {
  it("cuenta por clase y las no reconocidas", () => {
    const alerts = activeAlerts({
      cardiovascular: risk("critical"),
      immune: risk("concern"),
      bone: risk("watch"),
      behavioral: risk("watch"),
    });
    const counts = countAlerts(alerts, new Set(["bone:watch"]));
    expect(counts).toEqual({
      warning: 1, caution: 1, advisory: 2, unacknowledged: 3, suppressed: 0, inhibited: 0,
    });
  });
});

describe("lo que el retardo significa para una alerta", () => {
  it("Tierra lo sabe tras la ida; su respuesta llega, como pronto, tras ida y vuelta", () => {
    const at = new Date("2026-11-14T08:00:00Z");
    const timeline = earthTimeline(at, COMMS);
    expect(timeline?.earthKnowsAt.toISOString()).toBe("2026-11-14T08:11:00.000Z");
    expect(timeline?.earliestReplyAt.toISOString()).toBe("2026-11-14T08:22:00.000Z");
  });

  it("sin efemerides no se inventan tiempos", () => {
    expect(earthTimeline(new Date(), null)).toBeNull();
  });
});

describe("F.6.4: lo silenciado sigue activo, pero no pendiente", () => {
  it("cuenta aparte las suprimidas y las inhibidas", () => {
    const alerts = activeAlerts({
      cardiovascular: risk("critical"),
      immune: risk("concern"),
      bone: risk("watch"),
    });
    const silenced = new Map([
      ["cardiovascular:critical", "suppressed"],
      ["bone:watch", "inhibited"],
    ]);
    const counts = countAlerts(alerts, new Set(), silenced);
    // Siguen en su clase: existen.
    expect([counts.warning, counts.caution, counts.advisory]).toEqual([1, 1, 1]);
    // Solo la de inmune reclama atencion.
    expect(counts.unacknowledged).toBe(1);
    expect([counts.suppressed, counts.inhibited]).toEqual([1, 1]);
  });
});

describe("reconocimiento: lo que dice el ledger, no un clic local", () => {
  it("solo cuenta como reconocida la alerta que el backend tiene firmada", () => {
    const ids = acknowledgedIds([
      { ...state("bone:watch"), acknowledged: true, acknowledged_by: "cmd", acknowledgement_index: 7 },
      state("immune:concern"),
    ]);
    expect([...ids]).toEqual(["bone:watch"]);
  });
});

describe("el pictograma de cada estado de una alerta (F.5.10 e), sin color propio", () => {
  const tables = { ...RESOLUTION_MARKS, ...ANNUNCIATION_MARKS, ...ACKNOWLEDGEMENT_MARKS };

  it("cada estado con señal tiene un pictograma que existe, y ninguno lleva color", () => {
    for (const [name, look] of Object.entries(tables)) {
      if (look.pictogram !== null) expect(isPictogramName(look.pictogram), name).toBe(true);
      expect(look.color, name).toBeNull();
      expect(look.className, name).toBeUndefined();
    }
  });

  it("dos estados no comparten dibujo: la forma distingue", () => {
    const drawn = Object.values(tables).map((look) => look.pictogram).filter((name) => name !== null);
    expect(new Set(drawn).size).toBe(drawn.length);
  });

  it("la alerta que se anuncia no lleva señal: no hay nada que señalar", () => {
    expect(ANNUNCIATION_MARKS.normal.pictogram).toBeNull();
    expect(annunciationMark("suppressed").pictogram).toBe("bell-slash");
    expect(annunciationMark("inhibited").pictogram).toBe("bell-box");
  });

  it("detectada, en arreglo y resuelta, en ese orden de dibujos", () => {
    expect(resolutionMark("detectado").pictogram).toBe("dot-ringed");
    expect(resolutionMark("en_arreglo").pictogram).toBe("wrench");
    expect(resolutionMark("resuelto").pictogram).toBe("check");
  });

  it("reconocida lleva la pluma; sin reconocer no lleva señal propia: lo dice el parpadeo", () => {
    expect(acknowledgementMark(true).pictogram).toBe("pen");
    expect(acknowledgementMark(false).pictogram).toBeNull();
  });

  it("un estado desconocido se enseña como desconocido, sin tumbar la fila desde el render", () => {
    expect(resolutionMark("cerrado")).toBe(UNKNOWN_MARK);
    expect(annunciationMark("muted")).toBe(UNKNOWN_MARK);
    // Las propiedades heredadas de Object no son estados.
    expect(resolutionMark("toString")).toBe(UNKNOWN_MARK);
    expect(annunciationMark("constructor")).toBe(UNKNOWN_MARK);
  });
});
